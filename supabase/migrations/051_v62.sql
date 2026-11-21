-- 6.2: round timers (Cups, Connect 4), Colour Pick and SFX Match (server-authoritative), XP for the new games,
-- leaderboards and quests that know them. Safe to run twice.

alter table public.rb_c4 add column if not exists turn_by timestamptz;

insert into public.rb_config (key, value) values
    ('c4_turn_secs', 30), ('cups_pick_secs', 30), ('colour_day_profit', 12000), ('sfx_day_profit', 12000)
on conflict (key) do nothing;

-- ------------------------------------------------------------------------------------------------------------
-- Connect 4: the clock. rb_c4.turn_by = the moment the player's turn runs out (set here for a player who starts,
-- and by the c4 edge function after every bot move).
create or replace function public.rb_c4_json(g public.rb_c4) returns jsonb
language sql stable set search_path = '' as $$
    select jsonb_build_object('id', g.id, 'level', g.level, 'bet', g.bet, 'bot_first', g.bot_first, 'moves', to_jsonb(g.moves),
                              'state', g.state, 'outcome', g.outcome, 'paid', g.paid, 'mult', public.rb_c4_mult(g.level),
                              'secs', coalesce(public.rb_cfg('c4_turn_secs'), 30),
                              'left', case when g.turn_by is null then null
                                           else greatest(0, extract(epoch from (g.turn_by - now()))) end) $$;

create or replace function public.rb_c4_start(level text, bet integer, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; g public.rb_c4%rowtype; first_ boolean;
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if level not in ('easy', 'medium', 'hard', 'pro') then raise exception 'rb_bad_choice'; end if;
    perform public.rb_c4_close(p.id);
    perform public.rb_bet(p, bet, 'c4');
    first_ := level in ('hard', 'pro') or (level = 'medium' and public.rb_rand() < 0.5);
    insert into public.rb_c4 (owner, level, bet, bot_first, turn_by)
        values (p.id, level, bet, first_, case when first_ then null
                                               else now() + make_interval(secs => coalesce(public.rb_cfg('c4_turn_secs'), 30) + 5) end)
        returning * into g;
    return public.rb_remember(p.id, req, public.rb_c4_json(g) || jsonb_build_object('coins', p.coins - bet));
end $$;

-- ------------------------------------------------------------------------------------------------------------
-- Cups: the clock. The player has cups_pick_secs seconds once the cups stop; "pick = -1" is the client saying the
-- time is up (only accepted when it really is), a late pick counts as lost.
create or replace function public.rb_cups(action text, level integer, bet integer, pick integer, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; r public.rb_rounds%rowtype; n integer; moves integer; secs numeric;
        mult numeric; sw jsonb := '[]'::jsonb; a integer; b integer; i integer; coin integer; start_ integer;
        pay integer := 0; won boolean; dur numeric; lim numeric := coalesce(public.rb_cfg('cups_pick_secs'), 30);
        t numeric := extract(epoch from now()); ready numeric; late boolean := false;
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into r from public.rb_rounds where owner = p.id and game = 'cups' and open for update;
    if action = 'start' then
        if found then
            update public.rb_rounds set open = false where id = r.id;
        end if;
        if level is null or level not between 0 and 3 then raise exception 'rb_bad_choice'; end if;
        n := (array[3, 6, 9, 9])[level + 1];
        moves := (array[7, 12, 18, 26])[level + 1] + floor(public.rb_rand() * 4)::int;
        secs := (array[0.62, 0.42, 0.32, 0.22])[level + 1];
        mult := (array[1.4, 2.2, 3.3, 5.0])[level + 1];
        perform public.rb_bet(p, bet, 'cups');
        start_ := floor(public.rb_rand() * n)::int;
        for i in 1 .. moves loop
            a := floor(public.rb_rand() * n)::int;
            b := (a + 1 + floor(public.rb_rand() * (n - 1))::int) % n;
            sw := sw || jsonb_build_array(jsonb_build_array(a, b));
        end loop;
        coin := start_;
        for i in 0 .. jsonb_array_length(sw) - 1 loop
            a := (sw -> i ->> 0)::int; b := (sw -> i ->> 1)::int;
            if coin = a then coin := b; elsif coin = b then coin := a; end if;
        end loop;
        dur := 2.0 + moves * secs;
        insert into public.rb_rounds (owner, game, bet, secret, open, paid)
            values (p.id, 'cups', bet, jsonb_build_object('level', level, 'n', n, 'start', start_, 'swaps', sw, 'coin', coin,
                                                          'mult', mult, 'ready', t + dur - 1), true, 0);
        return public.rb_remember(p.id, req, jsonb_build_object('open', true, 'n', n, 'start', start_, 'swaps', sw,
            'secs', secs, 'mult', mult, 'bet', bet, 'pick_secs', lim, 'coins', p.coins - bet));
    end if;
    if action = 'pick' then
        if not found then raise exception 'rb_round_gone'; end if;
        n := (r.secret ->> 'n')::int;
        if pick is null or pick < -1 or pick >= n then raise exception 'rb_bad_choice'; end if;
        ready := (r.secret ->> 'ready')::numeric;
        if t < ready then raise exception 'rb_too_soon'; end if;
        if pick = -1 and t < ready + lim - 1 then raise exception 'rb_too_soon'; end if;   -- "time is up" only when it is
        late := pick = -1 or t > ready + lim + 4;                                          -- 1 s to see + the limit + 3 s of network
        coin := (r.secret ->> 'coin')::int;
        won := not late and pick = coin;
        mult := (r.secret ->> 'mult')::numeric;
        if won then
            pay := public.rb_win(p.id, r.bet * mult, 'cups');
        end if;
        update public.rb_rounds set open = false, paid = pay,
               secret = r.secret || jsonb_build_object('pick', pick, 'late', late) where id = r.id;
        return public.rb_remember(p.id, req, jsonb_build_object('open', false, 'won', won, 'coin', coin, 'paid', pay,
            'late', late, 'capped', won and mult = 1, 'coins', p.coins + pay));
    end if;
    raise exception 'rb_bad_choice';
end $$;

-- ------------------------------------------------------------------------------------------------------------
-- Colour distance (CIEDE2000, Sharma et al.) between two HSB colours, and how that becomes a payout.
create or replace function public.rb_hsb_lab(h double precision, s double precision, v double precision)
returns double precision[] language plpgsql immutable set search_path = '' as $$
declare hh double precision; ss double precision; vv double precision; c double precision; x double precision; m double precision;
        r double precision; g double precision; b double precision; sx integer;
        rl double precision; gl double precision; bl double precision; fx double precision; fy double precision; fz double precision;
        xx double precision; yy double precision; zz double precision;
begin
    hh := (h - floor(h / 360) * 360) / 60;
    ss := greatest(0, least(100, s)) / 100; vv := greatest(0, least(100, v)) / 100;
    c := vv * ss; x := c * (1 - abs((hh - floor(hh / 2) * 2) - 1)); m := vv - c; sx := floor(hh)::int;
    if sx = 0 then r := c; g := x; b := 0;
    elsif sx = 1 then r := x; g := c; b := 0;
    elsif sx = 2 then r := 0; g := c; b := x;
    elsif sx = 3 then r := 0; g := x; b := c;
    elsif sx = 4 then r := x; g := 0; b := c;
    else r := c; g := 0; b := x; end if;
    r := r + m; g := g + m; b := b + m;
    rl := case when r <= 0.04045 then r / 12.92 else power((r + 0.055) / 1.055, 2.4) end;
    gl := case when g <= 0.04045 then g / 12.92 else power((g + 0.055) / 1.055, 2.4) end;
    bl := case when b <= 0.04045 then b / 12.92 else power((b + 0.055) / 1.055, 2.4) end;
    xx := (0.4124564 * rl + 0.3575761 * gl + 0.1804375 * bl) / 0.95047;
    yy := 0.2126729 * rl + 0.7151522 * gl + 0.0721750 * bl;
    zz := (0.0193339 * rl + 0.1191920 * gl + 0.9503041 * bl) / 1.08883;
    fx := case when xx > 0.008856 then cbrt(xx) else 7.787 * xx + 16.0 / 116 end;
    fy := case when yy > 0.008856 then cbrt(yy) else 7.787 * yy + 16.0 / 116 end;
    fz := case when zz > 0.008856 then cbrt(zz) else 7.787 * zz + 16.0 / 116 end;
    return array[116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
end $$;

create or replace function public.rb_de2000(a double precision[], b double precision[])
returns double precision language plpgsql immutable set search_path = '' as $$
declare l1 double precision := a[1]; a1 double precision := a[2]; b1 double precision := a[3];
        l2 double precision := b[1]; a2 double precision := b[2]; b2 double precision := b[3];
        c1 double precision; c2 double precision; cb double precision; g double precision; a1p double precision; a2p double precision;
        c1p double precision; c2p double precision; h1p double precision; h2p double precision;
        dl double precision; dc double precision; dh double precision; dhh double precision; lb double precision; cbp double precision;
        hb double precision; t double precision; dth double precision; rc double precision; sl double precision; sc double precision;
        sh double precision; rt double precision; p7 double precision := power(25::double precision, 7);
begin
    c1 := sqrt(a1 * a1 + b1 * b1); c2 := sqrt(a2 * a2 + b2 * b2); cb := (c1 + c2) / 2;
    g := 0.5 * (1 - sqrt(power(cb, 7) / (power(cb, 7) + p7)));
    a1p := (1 + g) * a1; a2p := (1 + g) * a2;
    c1p := sqrt(a1p * a1p + b1 * b1); c2p := sqrt(a2p * a2p + b2 * b2);
    h1p := case when a1p = 0 and b1 = 0 then 0 else atan2d(b1, a1p) end; if h1p < 0 then h1p := h1p + 360; end if;
    h2p := case when a2p = 0 and b2 = 0 then 0 else atan2d(b2, a2p) end; if h2p < 0 then h2p := h2p + 360; end if;
    dl := l2 - l1; dc := c2p - c1p;
    if c1p * c2p = 0 then dh := 0;
    else dh := h2p - h1p; if dh > 180 then dh := dh - 360; elsif dh < -180 then dh := dh + 360; end if; end if;
    dhh := 2 * sqrt(c1p * c2p) * sind(dh / 2);
    lb := (l1 + l2) / 2; cbp := (c1p + c2p) / 2;
    if c1p * c2p = 0 then hb := h1p + h2p;
    elsif abs(h1p - h2p) <= 180 then hb := (h1p + h2p) / 2;
    elsif h1p + h2p < 360 then hb := (h1p + h2p + 360) / 2;
    else hb := (h1p + h2p - 360) / 2; end if;
    t := 1 - 0.17 * cosd(hb - 30) + 0.24 * cosd(2 * hb) + 0.32 * cosd(3 * hb + 6) - 0.20 * cosd(4 * hb - 63);
    dth := 30 * exp(-power((hb - 275) / 25, 2));
    rc := 2 * sqrt(power(cbp, 7) / (power(cbp, 7) + p7));
    sl := 1 + 0.015 * power(lb - 50, 2) / sqrt(20 + power(lb - 50, 2));
    sc := 1 + 0.045 * cbp; sh := 1 + 0.015 * cbp * t;
    rt := -sind(2 * dth) * rc;
    return sqrt(greatest(0, power(dl / sl, 2) + power(dc / sc, 2) + power(dhh / sh, 2) + rt * (dc / sc) * (dhh / sh)));
end $$;

-- accuracy % -> payout multiplier (the two games share the table; Easy pays least, Hard most)
create or replace function public.rb_acc_mult(lv integer, acc numeric) returns numeric
language sql immutable set search_path = '' as $$
    select case lv
        when 0 then case when acc >= 94 then 1.5 when acc >= 86 then 1.2 when acc >= 74 then 1.0 when acc >= 60 then 0.8
                         when acc >= 45 then 0.5 else 0 end
        when 1 then case when acc >= 92 then 2.2 when acc >= 80 then 1.6 when acc >= 65 then 1.2 when acc >= 50 then 0.9
                         when acc >= 35 then 0.6 else 0 end
        else        case when acc >= 88 then 3.0 when acc >= 72 then 2.0 when acc >= 55 then 1.4 when acc >= 40 then 1.0
                         when acc >= 25 then 0.6 else 0 end end $$;

create or replace function public.rb_num(v jsonb, k text, lo double precision, hi double precision)
returns double precision language plpgsql immutable set search_path = '' as $$
declare x double precision;
begin
    if v is null or jsonb_typeof(v -> k) is distinct from 'number' then raise exception 'rb_bad_choice'; end if;
    x := (v ->> k)::double precision;
    if x < lo or x > hi or x <> x then raise exception 'rb_bad_choice'; end if;
    return x;
end $$;

-- ------------------------------------------------------------------------------------------------------------
-- Colour Pick. A round is a row in rb_rounds (game 'colour'). The colour is handed out ONCE, by 'show', and never
-- again before the round has ended; 'submit' is only accepted after the viewing time and before the answer time.
create or replace function public.rb_colour(action text, level integer, bet integer, vals jsonb, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; r public.rb_rounds%rowtype; t double precision := extract(epoch from now());
        view_s numeric; ans_s numeric; h double precision; s double precision; v double precision;
        ph double precision; ps double precision; pv double precision;
        sec jsonb; de double precision; acc numeric; mult numeric; pay integer := 0; profit bigint; capped boolean := false;
        shown double precision; late boolean := false; lv integer;
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    if action <> 'show' then
        res := public.rb_done(p.id, req);
        if res is not null then return res; end if;
    end if;
    select * into r from public.rb_rounds where owner = p.id and game = 'colour' and open for update;
    if action = 'start' then
        if found then                                              -- a round left open is closed as lost (the bet is gone)
            update public.rb_rounds set open = false, secret = r.secret || jsonb_build_object('forfeit', true) where id = r.id;
        end if;
        if level is null or level not between 0 and 2 then raise exception 'rb_bad_choice'; end if;
        view_s := (array[6, 4, 2.5])[level + 1];
        ans_s := (array[45, 35, 25])[level + 1];
        h := floor(public.rb_rand() * 360);
        if level = 0 then s := 55 + floor(public.rb_rand() * 46); v := 60 + floor(public.rb_rand() * 41);     -- vivid, bright
        elsif level = 1 then s := 30 + floor(public.rb_rand() * 56); v := 35 + floor(public.rb_rand() * 56);
        else s := 20 + floor(public.rb_rand() * 56); v := 30 + floor(public.rb_rand() * 56); end if;          -- muted, darker: hard to tell apart
        perform public.rb_bet(p, bet, 'colour');
        insert into public.rb_rounds (owner, game, bet, secret, open, paid)
            values (p.id, 'colour', bet, jsonb_build_object('level', level, 'h', h, 's', s, 'v', v, 'view', view_s, 'ans', ans_s,
                                                            'started', t, 'shown', null), true, 0);
        return public.rb_remember(p.id, req, jsonb_build_object('open', true, 'phase', 'ready', 'level', level, 'view', view_s,
                                                                'ans', ans_s, 'bet', bet, 'coins', p.coins - bet));
    end if;
    if not found then
        if action = 'state' then return jsonb_build_object('open', false); end if;
        raise exception 'rb_round_gone';
    end if;
    lv := (r.secret ->> 'level')::int;
    view_s := (r.secret ->> 'view')::numeric; ans_s := (r.secret ->> 'ans')::numeric;
    shown := (r.secret ->> 'shown')::double precision;
    if action = 'show' then                                        -- the one and only look at the colour
        if shown is not null then raise exception 'rb_round_gone'; end if;
        if t > (r.secret ->> 'started')::double precision + 90 then
            update public.rb_rounds set open = false, secret = r.secret || jsonb_build_object('forfeit', true) where id = r.id;
            raise exception 'rb_round_gone';
        end if;
        update public.rb_rounds set secret = r.secret || jsonb_build_object('shown', t) where id = r.id;
        return jsonb_build_object('open', true, 'phase', 'show', 'h', (r.secret ->> 'h')::double precision,
                                  's', (r.secret ->> 's')::double precision, 'v', (r.secret ->> 'v')::double precision,
                                  'view', view_s, 'ans', ans_s);
    end if;
    if action = 'state' then                                       -- after a reconnect: no colour, only the clock
        if shown is null then
            if t > (r.secret ->> 'started')::double precision + 90 then
                update public.rb_rounds set open = false, secret = r.secret || jsonb_build_object('forfeit', true) where id = r.id;
                return jsonb_build_object('open', false);
            end if;
            return jsonb_build_object('open', true, 'phase', 'ready', 'level', lv, 'view', view_s, 'ans', ans_s, 'bet', r.bet);
        end if;
        if t > shown + view_s + ans_s + 5 then
            update public.rb_rounds set open = false, secret = r.secret || jsonb_build_object('forfeit', true) where id = r.id;
            return jsonb_build_object('open', false, 'expired', true);
        end if;
        return jsonb_build_object('open', true, 'phase', 'resume', 'level', lv, 'bet', r.bet,
                                  'wait', greatest(0, shown + view_s - t), 'left', greatest(0, shown + view_s + ans_s - t));
    end if;
    if action = 'submit' then
        if shown is null then raise exception 'rb_too_soon'; end if;
        ph := public.rb_num(vals, 'h', 0, 360); ps := public.rb_num(vals, 's', 0, 100); pv := public.rb_num(vals, 'v', 0, 100);
        if t < shown + view_s - 0.8 then raise exception 'rb_too_soon'; end if;          -- not before the colour has gone
        late := t > shown + view_s + ans_s + 5;                                           -- 5 s of network time, no more
        h := (r.secret ->> 'h')::double precision; s := (r.secret ->> 's')::double precision; v := (r.secret ->> 'v')::double precision;
        de := public.rb_de2000(public.rb_hsb_lab(h, s, v), public.rb_hsb_lab(ph, ps, pv));
        acc := case when late then 0 else round((100 * exp(-de / (array[28, 20, 14])[lv + 1]))::numeric, 1) end;
        mult := public.rb_acc_mult(lv, acc);
        select coalesce(sum(x.paid - x.bet), 0) into profit from public.rb_rounds x
         where x.owner = p.id and x.game = 'colour' and x.at >= (public.rb_today()::timestamp at time zone 'Europe/Paris');
        if profit >= coalesce(public.rb_cfg('colour_day_profit'), 12000) and mult > 1 then mult := 1; capped := true; end if;
        if mult > 0 then pay := public.rb_win(p.id, r.bet * mult, 'colour'); end if;
        update public.rb_rounds set open = false, paid = pay,
               secret = r.secret || jsonb_build_object('acc', acc, 'de', round(de::numeric, 2), 'late', late, 'mult', mult,
                                                       'pick', jsonb_build_object('h', ph, 's', ps, 'v', pv)) where id = r.id;
        return public.rb_remember(p.id, req, jsonb_build_object('open', false, 'acc', acc, 'de', round(de::numeric, 2), 'late', late,
            'mult', mult, 'paid', pay, 'capped', capped, 'h', h, 's', s, 'v', v, 'coins', p.coins + pay));
    end if;
    raise exception 'rb_bad_choice';
end $$;

-- ------------------------------------------------------------------------------------------------------------
-- SFX Match. The sound is described by parameters: pitch (Hz), duration (s), waveform 0..3 (sine, triangle, saw, square),
-- glide (semitones over the note), wobble 0..100 (vibrato) and shape 0..2 (pluck, beep, swell). Easy asks for the first
-- three, Medium adds glide and shape, Hard adds wobble. The parameters leave the server once (show), and the previews
-- of your own sound are counted here.
create or replace function public.rb_sfx(action text, level integer, bet integer, vals jsonb, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; r public.rb_rounds%rowtype; t double precision := extract(epoch from now());
        view_s numeric; ans_s numeric; plays integer; prev_max integer; used integer;
        f double precision; d double precision; w integer; g double precision; wb double precision; sh integer;
        pf double precision; pd double precision; pw double precision; pg double precision; pwb double precision; psh double precision;
        shown double precision; late boolean := false; lv integer; tol double precision[]; parts jsonb := '{}'::jsonb;
        sp double precision; sdu double precision; sw double precision; sg double precision; ss double precision; sb double precision;
        wsum double precision; tot double precision; acc numeric; mult numeric; pay integer := 0; profit bigint; capped boolean := false;
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    if action not in ('show') then
        res := public.rb_done(p.id, req);
        if res is not null then return res; end if;
    end if;
    select * into r from public.rb_rounds where owner = p.id and game = 'sfx' and open for update;
    if action = 'start' then
        if found then
            update public.rb_rounds set open = false, secret = r.secret || jsonb_build_object('forfeit', true) where id = r.id;
        end if;
        if level is null or level not between 0 and 2 then raise exception 'rb_bad_choice'; end if;
        view_s := (array[10, 7, 5])[level + 1];
        ans_s := (array[60, 45, 30])[level + 1];
        plays := (array[4, 3, 2])[level + 1];
        prev_max := (array[10, 6, 4])[level + 1];
        if level = 0 then                                           -- far-apart sounds: a few notes, sine or square
            f := 110 * power(2, (floor(public.rb_rand() * 10) * 5) / 12.0);
            d := (array[0.3, 0.6, 1.0, 1.5])[1 + floor(public.rb_rand() * 4)::int];
            w := (array[0, 3])[1 + floor(public.rb_rand() * 2)::int]; g := 0; wb := 0; sh := 1;
        elsif level = 1 then                                        -- any note, any waveform, a glide and a shape
            f := 110 * power(2, floor(public.rb_rand() * 45) / 12.0);
            d := round((0.2 + public.rb_rand() * 1.4)::numeric, 2);
            w := floor(public.rb_rand() * 4)::int; g := floor(public.rb_rand() * 15) - 7; wb := 0; sh := floor(public.rb_rand() * 3)::int;
        else                                                        -- everything free, everything close
            f := round((110 * power(2, public.rb_rand() * 45 / 12.0))::numeric, 1);
            d := round((0.15 + public.rb_rand() * 1.75)::numeric, 2);
            w := floor(public.rb_rand() * 4)::int; g := round((public.rb_rand() * 24 - 12)::numeric * 2) / 2;
            wb := floor(public.rb_rand() * 101); sh := floor(public.rb_rand() * 3)::int;
        end if;
        perform public.rb_bet(p, bet, 'sfx');
        insert into public.rb_rounds (owner, game, bet, secret, open, paid)
            values (p.id, 'sfx', bet, jsonb_build_object('level', level, 'f', f, 'd', d, 'w', w, 'g', g, 'wb', wb, 'sh', sh,
                'view', view_s, 'ans', ans_s, 'plays', plays, 'prev', prev_max, 'used', 0, 'started', t, 'shown', null), true, 0);
        return public.rb_remember(p.id, req, jsonb_build_object('open', true, 'phase', 'ready', 'level', level, 'view', view_s,
            'ans', ans_s, 'plays', plays, 'previews', prev_max, 'bet', bet, 'coins', p.coins - bet));
    end if;
    if not found then
        if action = 'state' then return jsonb_build_object('open', false); end if;
        raise exception 'rb_round_gone';
    end if;
    lv := (r.secret ->> 'level')::int;
    view_s := (r.secret ->> 'view')::numeric; ans_s := (r.secret ->> 'ans')::numeric;
    shown := (r.secret ->> 'shown')::double precision;
    prev_max := (r.secret ->> 'prev')::int; used := (r.secret ->> 'used')::int;
    if action = 'show' then
        if shown is not null then raise exception 'rb_round_gone'; end if;
        if t > (r.secret ->> 'started')::double precision + 90 then
            update public.rb_rounds set open = false, secret = r.secret || jsonb_build_object('forfeit', true) where id = r.id;
            raise exception 'rb_round_gone';
        end if;
        update public.rb_rounds set secret = r.secret || jsonb_build_object('shown', t) where id = r.id;
        return jsonb_build_object('open', true, 'phase', 'show', 'view', view_s, 'ans', ans_s, 'plays', (r.secret ->> 'plays')::int,
            'previews', prev_max, 'f', (r.secret ->> 'f')::double precision, 'd', (r.secret ->> 'd')::double precision,
            'w', (r.secret ->> 'w')::int, 'g', (r.secret ->> 'g')::double precision, 'wb', (r.secret ->> 'wb')::double precision,
            'sh', (r.secret ->> 'sh')::int);
    end if;
    if action = 'state' then
        if shown is null then
            if t > (r.secret ->> 'started')::double precision + 90 then
                update public.rb_rounds set open = false, secret = r.secret || jsonb_build_object('forfeit', true) where id = r.id;
                return jsonb_build_object('open', false);
            end if;
            return jsonb_build_object('open', true, 'phase', 'ready', 'level', lv, 'view', view_s, 'ans', ans_s,
                                      'plays', (r.secret ->> 'plays')::int, 'previews', prev_max, 'bet', r.bet);
        end if;
        if t > shown + view_s + ans_s + 5 then
            update public.rb_rounds set open = false, secret = r.secret || jsonb_build_object('forfeit', true) where id = r.id;
            return jsonb_build_object('open', false, 'expired', true);
        end if;
        return jsonb_build_object('open', true, 'phase', 'resume', 'level', lv, 'bet', r.bet, 'previews', prev_max - used,
                                  'wait', greatest(0, shown + view_s - t), 'left', greatest(0, shown + view_s + ans_s - t));
    end if;
    if action = 'preview' then                                     -- listening to your own sound costs one of a few
        if shown is null or t < shown + view_s - 0.8 then raise exception 'rb_too_soon'; end if;
        if t > shown + view_s + ans_s + 5 then raise exception 'rb_too_soon'; end if;
        if used >= prev_max then raise exception 'rb_too_soon'; end if;
        update public.rb_rounds set secret = r.secret || jsonb_build_object('used', used + 1) where id = r.id;
        return jsonb_build_object('left', prev_max - used - 1);
    end if;
    if action = 'submit' then
        if shown is null then raise exception 'rb_too_soon'; end if;
        pf := public.rb_num(vals, 'f', 100, 2000); pd := public.rb_num(vals, 'd', 0.1, 2.5); pw := public.rb_num(vals, 'w', 0, 3);
        pg := public.rb_num(vals, 'g', -12, 12); pwb := public.rb_num(vals, 'wb', 0, 100); psh := public.rb_num(vals, 'sh', 0, 2);
        if t < shown + view_s - 0.8 then raise exception 'rb_too_soon'; end if;
        late := t > shown + view_s + ans_s + 5;
        f := (r.secret ->> 'f')::double precision; d := (r.secret ->> 'd')::double precision; w := (r.secret ->> 'w')::int;
        g := (r.secret ->> 'g')::double precision; wb := (r.secret ->> 'wb')::double precision; sh := (r.secret ->> 'sh')::int;
        -- how far off each parameter is, as a share of what that level forgives (0 = exact, bigger = further)
        tol := case lv when 0 then array[5.0, 0.5, 0.6, 1, 1, 1] when 1 then array[2.4, 0.28, 0.38, 3.2, 0.4, 1]
                       else array[1.5, 0.18, 0.3, 2.2, 0.34, 0.2] end;
        sp := exp(-abs(12 * ln(pf / f) / ln(2::double precision)) / tol[1]);
        sdu := exp(-abs(ln(pd / d)) / tol[2]);
        sw := exp(-(abs(pw - w) / 3.0) / tol[3]);
        wsum := 2 + 1 + 1.5; tot := 2 * sp + 1 * sdu + 1.5 * sw;
        parts := jsonb_build_object('pitch', round((sp * 100)::numeric), 'dur', round((sdu * 100)::numeric), 'wave', round((sw * 100)::numeric));
        if lv >= 1 then
            sg := exp(-abs(pg - g) / tol[4]); ss := exp(-(abs(psh - sh) / 2.0) / tol[5]);
            wsum := wsum + 2; tot := tot + sg + ss;
            parts := parts || jsonb_build_object('glide', round((sg * 100)::numeric), 'shape', round((ss * 100)::numeric));
        end if;
        if lv >= 2 then
            sb := exp(-(abs(pwb - wb) / 100.0) / tol[6]);
            wsum := wsum + 0.7; tot := tot + 0.7 * sb;
            parts := parts || jsonb_build_object('wobble', round((sb * 100)::numeric));
        end if;
        acc := case when late then 0 else round((100 * tot / wsum)::numeric, 1) end;
        mult := public.rb_acc_mult(lv, acc);
        select coalesce(sum(x.paid - x.bet), 0) into profit from public.rb_rounds x
         where x.owner = p.id and x.game = 'sfx' and x.at >= (public.rb_today()::timestamp at time zone 'Europe/Paris');
        if profit >= coalesce(public.rb_cfg('sfx_day_profit'), 12000) and mult > 1 then mult := 1; capped := true; end if;
        if mult > 0 then pay := public.rb_win(p.id, r.bet * mult, 'sfx'); end if;
        update public.rb_rounds set open = false, paid = pay,
               secret = r.secret || jsonb_build_object('acc', acc, 'late', late, 'mult', mult,
                   'pick', jsonb_build_object('f', pf, 'd', pd, 'w', pw, 'g', pg, 'wb', pwb, 'sh', psh)) where id = r.id;
        return public.rb_remember(p.id, req, jsonb_build_object('open', false, 'acc', acc, 'late', late, 'mult', mult, 'paid', pay,
            'capped', capped, 'parts', parts, 'level', lv, 'coins', p.coins + pay,
            'f', f, 'd', d, 'w', w, 'g', g, 'wb', wb, 'sh', sh));
    end if;
    raise exception 'rb_bad_choice';
end $$;

grant execute on function public.rb_colour(text, integer, integer, jsonb, text) to authenticated;
grant execute on function public.rb_sfx(text, integer, integer, jsonb, text) to authenticated;
revoke execute on function public.rb_colour(text, integer, integer, jsonb, text) from anon, public;
revoke execute on function public.rb_sfx(text, integer, integer, jsonb, text) from anon, public;

-- ------------------------------------------------------------------------------------------------------------
-- XP for the two new games: by accuracy (a bet of 50+ and at least 50 % accuracy), a little more on Hard
create or replace function public.rb_rounds_xp() returns trigger
language plpgsql security definer set search_path = '' as $$
declare amt integer := 0; src text; acc numeric;
begin
    if new.open then return new; end if;
    if tg_op = 'UPDATE' and not old.open then return new; end if;
    if coalesce((new.secret ->> 'void')::boolean, false) then return new; end if;
    if new.game in ('blackjack', 'mines', 'rocket', 'timing', 'hilo', 'tower', 'roulette', 'dice', 'plinko', 'keno', 'limbo',
                    'slots') then
        if new.bet < 50 or coalesce(new.paid, 0) <= new.bet then return new; end if;
        src := 'casino'; amt := least(5, 1 + (new.paid - new.bet) / 300);
    elsif new.game in ('colour', 'sfx') then
        acc := coalesce((new.secret ->> 'acc')::numeric, 0);
        if new.bet < 50 or acc < 50 then return new; end if;
        src := 'casino';
        amt := least(5, (case when acc >= 95 then 4 when acc >= 85 then 3 when acc >= 70 then 2 else 1 end)
                        + (case when (new.secret ->> 'level')::int = 2 then 1 else 0 end));
    elsif new.game in ('mini', 'park', 'memory', 'tap', 'g2048', 'sweeper', 'blocks', 'wave', 'golf_solo') then
        if coalesce(new.paid, 0) <= 0 then return new; end if;
        src := case when new.game = 'wave' then 'wave' else 'minigames' end;
        amt := least(12, 3 + new.paid / 30);
    elsif new.game like 'case:%' then
        src := 'cases'; amt := 2;
    elsif new.game in ('spin', 'scratch') then
        src := 'wheel'; amt := 4;
    else
        return new;
    end if;
    perform public.rb_xp_add(new.owner, amt, src, new.game, true);
    return new;
end $$;

-- ------------------------------------------------------------------------------------------------------------
-- leaderboards (best win per game), stats and quests know the two games
do $$
declare d text; o text;
begin
    d := pg_get_functiondef('public.rb_leaders(text,boolean)'::regprocedure); o := d;
    d := replace(d, '''g:dice'', ''g:timing'')', '''g:dice'', ''g:timing'', ''g:colour'', ''g:sfx'')');
    d := replace(d, 'when ''g:timing'' then public.rb_best_win(w.id, ''timing'')',
                 'when ''g:timing'' then public.rb_best_win(w.id, ''timing'') when ''g:colour'' then public.rb_best_win(w.id, ''colour'') when ''g:sfx'' then public.rb_best_win(w.id, ''sfx'')');
    if d = o or position('g:sfx' in d) = 0 then raise exception 'rb_leaders not patched'; end if;
    execute d;

    d := pg_get_functiondef('public.rb_quest_rows(uuid)'::regprocedure); o := d;
    d := replace(d, '(''cups''), (''c4''))', '(''cups''), (''c4''), (''colour''), (''sfx''))');
    if d = o then raise exception 'rb_quest_rows not patched'; end if;
    execute d;

    d := pg_get_functiondef('public.rb_ach_stats(uuid)'::regprocedure); o := d;
    d := replace(d, '''cups'', ''c4'', ''golf''', '''cups'', ''c4'', ''colour'', ''sfx'', ''golf''');
    if d = o then raise exception 'rb_ach_stats not patched'; end if;
    execute d;
end $$;
