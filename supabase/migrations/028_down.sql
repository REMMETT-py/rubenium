-- 028 down: back to 4.4 (build 2026.11.18.22)
begin;
CREATE OR REPLACE FUNCTION public.rb_wave_sim(seed bigint, toggles integer[], max_ticks integer)
 RETURNS TABLE(ticks integer, x integer)
 LANGUAGE plpgsql
 IMMUTABLE
 SET search_path TO ''
AS $function$
declare
    k_vx constant integer := 12; k_r constant integer := 10; k_h constant integer := 1000; k_sw constant integer := 48;
    s bigint := seed & 2147483647;
    sx0 integer[] := array[0]; sln integer[] := array[900]; sc0 integer[] := array[500]; ssl integer[] := array[0];
    sgp integer[] := array[420]; sfrom integer[] := array[1]; sn integer[] := array[0];
    px integer[] := '{}'; pside integer[] := '{}';
    x_end integer := 900; c_end integer := 500;
    tg integer[]; k integer := 1; held boolean := true; t integer; px_ integer := 0; y integer := 500; i integer := 1;
    d integer; f integer; gap integer; r integer; p_zig integer; p_flat integer; ln_ integer; n integer; side integer;
    legs integer; leg integer; slope integer; room integer; lo integer; hi integer; j integer;
    c integer; half integer; top integer; bot integer; hh integer; dx integer; q integer;
begin
    select coalesce(array_agg(v order by v), '{}') into tg
      from (select distinct v from unnest(coalesce(toggles, '{}')) v where v > 0 and v < max_ticks) z;
    for t in 1..max_ticks loop
        while k <= coalesce(array_length(tg, 1), 0) and tg[k] <= t loop
            held := not held; k := k + 1;
        end loop;
        px_ := px_ + k_vx;
        y := y + case when held then -k_vx else k_vx end;
        -- grow the course ahead of the wave
        while x_end <= px_ + 4000 loop
            d := least(1000, x_end / 150);
            f := d * (d + 1000) / 2000;
            gap := 420 - 300 * f / 1000;
            gap := gap - gap % 2;
            lo := gap / 2 + 40; hi := k_h - gap / 2 - 40;
            if c_end < lo then                                   -- pull the centre back in first
                sx0 := sx0 || x_end; sln := sln || (lo - c_end); sc0 := sc0 || c_end; ssl := ssl || 1; sgp := sgp || gap;
                sfrom := sfrom || (coalesce(array_length(px, 1), 0) + 1); sn := sn || 0;
                x_end := x_end + (lo - c_end); c_end := lo;
            elsif c_end > hi then
                sx0 := sx0 || x_end; sln := sln || (c_end - hi); sc0 := sc0 || c_end; ssl := ssl || -1; sgp := sgp || gap;
                sfrom := sfrom || (coalesce(array_length(px, 1), 0) + 1); sn := sn || 0;
                x_end := x_end + (c_end - hi); c_end := hi;
            end if;
            s := (s * 1103515245 + 12345) & 2147483647; r := (s >> 8) % 1000;
            p_zig := 200 + 400 * d / 1000;
            p_flat := 450 - 200 * d / 1000;
            if r < p_flat then
                s := (s * 1103515245 + 12345) & 2147483647; ln_ := 300 + (s >> 8) % 500;
                if d >= 50 then
                    s := (s * 1103515245 + 12345) & 2147483647; n := (s >> 8) % (2 + 2 * d / 1000);
                else
                    n := 0;
                end if;
                s := (s * 1103515245 + 12345) & 2147483647; side := (s >> 8) % 2;
                sx0 := sx0 || x_end; sln := sln || ln_; sc0 := sc0 || c_end; ssl := ssl || 0; sgp := sgp || gap;
                sfrom := sfrom || (coalesce(array_length(px, 1), 0) + 1); sn := sn || n;
                for j in 0..n - 1 loop
                    px := px || (x_end + ln_ * (j + 1) / (n + 1)); pside := pside || side;
                    side := 1 - side;
                end loop;
                x_end := x_end + ln_;
            elsif r < p_flat + p_zig then
                s := (s * 1103515245 + 12345) & 2147483647; legs := 3 + (s >> 8) % (4 + 4 * d / 1000);
                s := (s * 1103515245 + 12345) & 2147483647; leg := greatest(100, 320 - 220 * d / 1000 + (s >> 8) % 60);
                slope := case when (hi - c_end) >= (c_end - lo) then 1 else -1 end;
                for j in 1..legs loop
                    room := case when slope > 0 then hi - c_end else c_end - lo end;
                    if room < 60 then
                        slope := -slope;
                        room := case when slope > 0 then hi - c_end else c_end - lo end;
                    end if;
                    ln_ := greatest(40, least(leg, room));
                    sx0 := sx0 || x_end; sln := sln || ln_; sc0 := sc0 || c_end; ssl := ssl || slope; sgp := sgp || gap;
                    sfrom := sfrom || (coalesce(array_length(px, 1), 0) + 1); sn := sn || 0;
                    x_end := x_end + ln_; c_end := c_end + slope * ln_;
                    slope := -slope;
                end loop;
            else
                s := (s * 1103515245 + 12345) & 2147483647;
                slope := case when (s >> 8) % 2 = 1 then 1 else -1 end;
                room := case when slope > 0 then hi - c_end else c_end - lo end;
                if room < 120 then
                    slope := -slope;
                    room := case when slope > 0 then hi - c_end else c_end - lo end;
                end if;
                s := (s * 1103515245 + 12345) & 2147483647;
                ln_ := greatest(60, least(150 + (s >> 8) % 400, room));
                sx0 := sx0 || x_end; sln := sln || ln_; sc0 := sc0 || c_end; ssl := ssl || slope; sgp := sgp || gap;
                sfrom := sfrom || (coalesce(array_length(px, 1), 0) + 1); sn := sn || 0;
                x_end := x_end + ln_; c_end := c_end + slope * ln_;
            end if;
        end loop;
        while px_ >= sx0[i] + sln[i] loop i := i + 1; end loop;
        c := sc0[i] + ssl[i] * (px_ - sx0[i]);
        half := sgp[i] / 2;
        top := c - half; bot := c + half;
        if sn[i] > 0 then
            hh := sgp[i] * 38 / 100;
            for j in sfrom[i]..sfrom[i] + sn[i] - 1 loop
                dx := abs(px_ - px[j]);
                if dx < k_sw then
                    q := hh * (k_sw - dx) / k_sw;
                    if pside[j] = 0 then top := greatest(top, c - half + q); else bot := least(bot, c + half - q); end if;
                end if;
            end loop;
        end if;
        if y - k_r < top or y + k_r > bot then
            ticks := t; x := px_; return next; return;
        end if;
    end loop;
    ticks := max_ticks; x := px_; return next;
end $function$
;

CREATE OR REPLACE FUNCTION public.rb_wave_ping(run uuid, x integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare me uuid := auth.uid(); r public.rb_wave_runs%rowtype;
begin
    select * into r from public.rb_wave_runs where id = run and owner = me;
    if not found or r.duel is null then raise exception 'rb_duel_gone'; end if;
    if r.state = 'live' then
        update public.rb_wave_runs set live_x = greatest(live_x, least(coalesce(x, 0),
               floor(greatest(0, extract(epoch from now() - started_at)) * 60 * 12)::int + 2000)) where id = r.id;
    end if;
    return public.rb_wave_state(r.duel);
end $function$
;

CREATE OR REPLACE FUNCTION public.rb_wave_finish(run uuid, toggles integer[], ticks integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare me uuid := auth.uid(); r public.rb_wave_runs%rowtype; sim record; need double precision; base integer;
        pay integer := 0; best integer; w public.rb_wave_duels%rowtype; other public.rb_wave_runs%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_need_feature('wave');
    select * into r from public.rb_wave_runs where id = run and owner = me for update;
    if not found then raise exception 'rb_duel_gone'; end if;
    if r.state <> 'live' then
        return jsonb_build_object('dist', r.dist, 'paid', r.paid, 'best', public.rb_wave_best(me), 'again', true);
    end if;
    if ticks is null or ticks < 1 or coalesce(array_length(toggles, 1), 0) > 30000 then raise exception 'rb_bad_choice'; end if;
    select * into sim from public.rb_wave_sim(r.seed, toggles, least(54000, ticks + 2));
    need := sim.ticks / 60.0 * 0.9 - 1.5;                      -- the run takes real time to play
    if extract(epoch from now() - r.started_at) < need then raise exception 'rb_too_fast'; end if;
    best := public.rb_wave_best(me);
    if r.duel is null then
        base := public.rb_wave_pay_for(sim.x);
        pay := public.rb_game_pay(me, 'wave', base);
        if pay > 0 then perform public.rb_pay(me, pay, 0, 'minigame', 'wave'); end if;
        insert into public.rb_rounds (owner, game, bet, secret, open, paid)
            values (me, 'wave', 0, jsonb_build_object('x', sim.x, 'ticks', sim.ticks, 'run', r.id), false, pay);
    end if;
    update public.rb_wave_runs set state = 'done', ticks = sim.ticks, dist = sim.x, live_x = sim.x, paid = pay,
           done_at = now() where id = r.id;
    if r.duel is not null then
        select * into w from public.rb_wave_duels where id = r.duel for update;
        select * into other from public.rb_wave_runs where id = case when w.a_run = r.id then w.b_run else w.a_run end;
        if found and other.state = 'done' then perform public.rb_wave_settle(w.id, null); end if;
    end if;
    return jsonb_build_object('dist', sim.x, 'ticks', sim.ticks, 'paid', pay, 'best', greatest(best, sim.x),
                              'record', r.duel is null and sim.x > best and best > 0);
end $function$
;

CREATE OR REPLACE FUNCTION public.rb_wave_duel_json(w rb_wave_duels, me uuid)
 RETURNS jsonb
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select jsonb_build_object('id', w.id, 'state', w.state, 'bet', w.bet, 'seed', w.seed,
        'me', case when me = w.a then 'a' else 'b' end,
        'a', (select username from public.profiles where id = w.a), 'b', (select username from public.profiles where id = w.b),
        'run', case when me = w.a then w.a_run else w.b_run end,
        'a_x', ra.live_x, 'b_x', rb.live_x, 'a_done', ra.state = 'done', 'b_done', rb.state = 'done',
        'starts_in', case when w.live_at is not null then greatest(0, extract(epoch from (w.live_at + interval '4 seconds' - now())))::numeric(5, 1) end,
        'left', case when w.state = 'live' then greatest(0, ceil(extract(epoch from (w.live_at
                 + make_interval(mins => coalesce(public.rb_cfg('wave_duel_min'), 8)::int) - now()))))::int end,
        'winner', case when w.winner = w.a then 'a' when w.winner = w.b then 'b' end, 'why', w.why)
      from (select 1) one
      left join public.rb_wave_runs ra on ra.id = w.a_run
      left join public.rb_wave_runs rb on rb.id = w.b_run $function$
;

CREATE OR REPLACE FUNCTION public.rb_wave_lobbies()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare me uuid := auth.uid(); p public.profiles%rowtype; o record; live uuid;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into p from public.profiles where id = me;
    for o in select id from public.rb_wave_duels where state in ('open', 'live') and (state = 'open' or a = me or b = me) loop
        perform public.rb_wave_tick(o.id);
    end loop;
    select id into live from public.rb_wave_duels where state = 'live' and (a = me or b = me) order by live_at desc limit 1;
    return jsonb_build_object(
        'live', live, 'cap', public.rb_golf_cap(p.coins), 'best', public.rb_wave_best(me),
        'lobbies', coalesce((select jsonb_agg(jsonb_build_object('id', w.id, 'host', u.username, 'bet', w.bet, 'mine', w.a = me,
                     'left', greatest(0, ceil(extract(epoch from (w.at + make_interval(mins => coalesce(public.rb_cfg('lobby_min'), 5)::int)
                     - now()))))::int) order by w.at)
                   from public.rb_wave_duels w join public.profiles u on u.id = w.a where w.state = 'open'), '[]'::jsonb),
        'history', coalesce((select jsonb_agg(h order by (h ->> 'at') desc) from (
                   select jsonb_build_object('id', w.id, 'at', w.at, 'bet', w.bet, 'state', w.state,
                          'other', (select username from public.profiles where id = case when w.a = me then w.b else w.a end),
                          'won', w.winner = me, 'draw', w.state = 'done' and w.winner is null,
                          'me_m', (select dist / 100 from public.rb_wave_runs where id = case when w.a = me then w.a_run else w.b_run end),
                          'other_m', (select dist / 100 from public.rb_wave_runs where id = case when w.a = me then w.b_run else w.a_run end)) h
                     from public.rb_wave_duels w where (w.a = me or w.b = me) and w.state in ('live', 'done')
                    order by w.at desc limit 6) z), '[]'::jsonb));
end $function$
;

CREATE OR REPLACE FUNCTION public.rb_case_drop(c rb_cases, OUT tier integer, OUT klass integer, OUT item text, OUT coins integer)
 RETURNS record
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare r double precision;
begin
    tier := public.rb_roll(c.odds); klass := 0; coins := 0;
    if tier > 0 and c.mode like 'kinds:%' then                -- a style case: one item of that rarity, by weight
        item := public.rb_pick_weighted(string_to_array(substr(c.mode, 7), ','), tier, null);
        if item is not null then return; end if;
        tier := 0;                                            -- nothing of that rarity: coins instead
    end if;
    if tier > 0 and c.mode like 'items:%' then                -- a limited case: its own list, by rarity and weight
        select k.id into item from public.rb_catalog k
         where k.id = any (string_to_array(substr(c.mode, 7), ','))
           and k.rarity = (array['standard', 'rare', 'special', 'epic', 'exotic'])[tier]
         order by -ln(greatest(public.rb_rand(), 1e-12)) / k.weight limit 1;
        if item is not null then return; end if;
        tier := 0;
    end if;
    if tier = 0 then
        if c.mode = 'jackpot' then
            r := public.rb_rand();
            coins := floor(c.price * case when r < 0.66 then 0.12 + public.rb_rand() * 0.33
                                          when r < 0.90 then 0.8 + public.rb_rand() * 0.8
                                          when r < 0.97 then 2.5 + public.rb_rand() * 1.5
                                          when r < 0.995 then 6.5 + public.rb_rand() * 3.5
                                          else 20 + public.rb_rand() * 12 end)::int;
        else
            coins := c.coin_min + floor(public.rb_rand() * (c.coin_max - c.coin_min + 1))::int;
            if public.rb_rand() * 100 < coalesce(public.rb_cfg('case_lucky_pct'), 0) then
                coins := coins * coalesce(public.rb_cfg('case_lucky_x'), 1)::int;
            end if;
        end if;
    elsif tier = 5 then                                   -- Mythic: Titanium, rarely Prismatic, almost never Gold
        klass := (array[3, 5, 4])[public.rb_roll(array[96515, 3300, 185]) + 1];
        item := public.rb_pick_mythic(klass);
    else
        klass := public.rb_roll(c.variants);
        if klass = 3 and tier <= 2 then klass := 2; end if;  -- no Titanium for Common and Rare badges
        item := public.rb_pick_badge(tier, klass);
    end if;
end $function$
;

CREATE OR REPLACE FUNCTION public.rb_xp_cap(src text)
 RETURNS integer
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
    select case src when 'casino' then 120 when 'minigames' then 300 when 'cases' then 40 when 'golf' then 150
                    when 'coinflip' then 60 when 'trading' then 48 when 'online' then 120 when 'wheel' then 20
                    when 'quests' then 200 when 'wave' then 150 else 100000 end $function$
;

CREATE OR REPLACE FUNCTION public.rb_xp_add(who uuid, amount integer, src text, ref text, capped boolean DEFAULT true)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; day_src jsonb; used integer; give integer; lv integer; tot integer;
begin
    if amount is null or amount <= 0 then return 0; end if;
    select * into p from public.profiles where id = who for update;
    if not found or p.bot then return 0; end if;
    if p.xp_day is distinct from current_date then p.xp_day_gain := 0; p.xp_day_src := '{}'::jsonb; end if;
    give := amount;
    if capped then
        used := coalesce((p.xp_day_src ->> src)::int, 0);
        give := least(give, public.rb_xp_cap(src) - used, coalesce(public.rb_cfg('xp_day_cap'), 2500)::int - p.xp_day_gain);
        if give <= 0 then
            update public.profiles set xp_day = current_date, xp_day_gain = p.xp_day_gain, xp_day_src = p.xp_day_src where id = who;
            return 0;
        end if;
        tot := p.xp_day_gain + give;
        day_src := p.xp_day_src || jsonb_build_object(src, used + give);
    else
        tot := p.xp_day_gain; day_src := p.xp_day_src;
    end if;
    lv := public.rb_level_of(p.xp + give);
    update public.profiles set xp = xp + give, level = lv, xp_day = current_date, xp_day_gain = tot, xp_day_src = day_src
     where id = who;
    insert into public.rb_xp_log (owner, amount, source, ref, level_after) values (who, give, src, left(ref, 80), lv);
    if lv > p.level then
        perform public.rb_notice(who, 'level_up', jsonb_build_object('level', lv, 'from', p.level));
    end if;
    return give;
end $function$
;

CREATE OR REPLACE FUNCTION public.rb_rounds_xp()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare amt integer := 0; src text;
begin
    if new.open then return new; end if;
    if tg_op = 'UPDATE' and not old.open then return new; end if;               -- counted once, when it ends
    if coalesce((new.secret ->> 'void')::boolean, false) then return new; end if;
    if new.game in ('blackjack', 'mines', 'rocket', 'timing', 'hilo', 'tower', 'roulette', 'dice', 'plinko', 'keno', 'limbo',
                    'slots') then
        if new.bet < 10 or coalesce(new.paid, 0) <= new.bet then return new; end if;     -- 4.3: a loss gives nothing
        src := 'casino'; amt := least(5, 1 + (new.paid - new.bet) / 300);
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
end $function$
;

CREATE OR REPLACE FUNCTION public.rb_trade_xp()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    if new.state = 'done' and old.state <> 'done' then
        perform public.rb_xp_add(new.a, 8, 'trading', new.id::text, true);
        perform public.rb_xp_add(new.b, 8, 'trading', new.id::text, true);
    end if;
    return new;
end $function$
;

CREATE OR REPLACE FUNCTION public.rb_xp_json(p profiles)
 RETURNS json
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
    select json_build_object('xp', p.xp, 'level', p.level,
        'into', p.xp - public.rb_xp_total(p.level),
        'need', case when p.level >= 100 then 0 else public.rb_xp_need(p.level) end,
        'badge', case when p.level_badge >= 0 and p.level_badge <= p.level then p.level_badge else (p.level / 5) * 5 end,
        'today', case when p.xp_day = current_date then p.xp_day_gain else 0 end,
        'cap', coalesce(public.rb_cfg('xp_day_cap'), 2500)) $function$
;

CREATE OR REPLACE FUNCTION public.rb_admin_xp_watch()
 RETURNS json
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    perform public.rb_need_admin();
    return json_build_object(
        'top_day', coalesce((select json_agg(x) from (
            select p.username as name, p.level, sum(l.amount) as xp, count(*) as events,
                   count(distinct date_trunc('day', l.at)) filter (where l.at > now() - interval '7 days') as days
              from public.rb_xp_log l join public.profiles p on p.id = l.owner
             where l.at > now() - interval '24 hours' group by p.username, p.level order by sum(l.amount) desc limit 20) x), '[]'::json),
        'capped_days', coalesce((select json_agg(x) from (
            select p.username as name, count(*) as days from (
                select owner, date_trunc('day', at) d, sum(amount) s from public.rb_xp_log
                 where source not in ('coupon', 'admin', 'advent') and at > now() - interval '14 days' group by 1, 2) t
              join public.profiles p on p.id = t.owner
             where t.s >= coalesce(public.rb_cfg('xp_day_cap'), 2500) group by p.username having count(*) >= 3
             order by count(*) desc) x), '[]'::json),
        'curve', (select json_agg(json_build_object('level', l, 'total', public.rb_xp_total(l), 'next', public.rb_xp_need(l)) order by l)
                    from generate_series(0, 100, 5) l),
        'caps', json_build_object('day', public.rb_cfg('xp_day_cap'), 'casino', public.rb_xp_cap('casino'), 'minigames', public.rb_xp_cap('minigames'),
                                  'golf', public.rb_xp_cap('golf'), 'coinflip', public.rb_xp_cap('coinflip'), 'trading', public.rb_xp_cap('trading'),
                                  'online', public.rb_xp_cap('online'), 'cases', public.rb_xp_cap('cases'), 'quests', public.rb_xp_cap('quests')));
end $function$
;

CREATE OR REPLACE FUNCTION public.rb_bet(p profiles, bet integer, game text)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    if bet is null or bet < public.rb_cfg('bet_min') or bet > public.rb_cfg('bet_max') then
        raise exception 'rb_bad_bet';
    end if;
    perform public.rb_pay(p.id, -bet, 0, 'bet', game);
end $function$
;

CREATE OR REPLACE FUNCTION public.rb_trade_request(name text)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; them public.profiles%rowtype; tid uuid;
begin
    perform public.rb_need_feature('trading');
    p := public.rb_lock_me();
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    select * into them from public.profiles where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    if them.id = p.id then raise exception 'rb_thats_you'; end if;
    if not public.rb_can_trade(them) then raise exception 'rb_they_cannot_trade'; end if;
    perform public.rb_trade_expire(p.id);
    select id into tid from public.rb_trades
     where state in ('asked', 'open') and ((a = p.id and b = them.id) or (a = them.id and b = p.id));
    if tid is not null then return tid; end if;
    if (select count(*) from public.rb_trades where (a = p.id or b = p.id) and state in ('asked', 'open'))
       >= public.rb_cfg('trade_max_open') then
        raise exception 'rb_too_many_trades';
    end if;
    insert into public.rb_trades (a, b) values (p.id, them.id) returning id into tid;
    return tid;
end $function$
;

CREATE OR REPLACE FUNCTION public.rb_trade_accept(trade uuid)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare me uuid := auth.uid(); t public.rb_trades%rowtype;
begin
    perform public.rb_need_feature('trading');
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_trade_expire(me);
    select * into t from public.rb_trades where id = trade for update;
    if not found or t.b <> me or t.state <> 'asked' then raise exception 'rb_trade_gone'; end if;
    update public.rb_trades set state = 'open', a_seen = now(), b_seen = now(), updated = now() where id = t.id;
    return true;
end $function$
;

drop function if exists public.rb_wave_ping(uuid, integer, integer[], integer);
drop function if exists public.rb_wave_watch(uuid);
alter table public.rb_wave_runs drop column if exists live_tg;
alter table public.rb_wave_runs drop column if exists live_t;
drop function if exists public.rb_bet_cap(bigint);
delete from public.rb_config where key in ('bet_max_rich', 'bet_rich_pct', 'cases_v45');
update public.rb_config set value = 1000 where key = 'xp_day_cap';
alter table public.profiles drop column if exists xp_hr;
alter table public.profiles drop column if exists xp_hr_src;
-- the new looks leave the shop (copies people own stay in the catalogue, so nothing is lost)
update public.rb_catalog set price = null
 where id in ('theme:glacier', 'theme:jade', 'theme:mirage', 'theme:nebula', 'theme:obsidian', 'theme:prism', 'banner:mosaic',
              'banner:reef', 'banner:thunder', 'banner:blackhole', 'banner:crystal', 'frame:chrome', 'frame:ripple', 'frame:comet',
              'frame:eclipse') or (kind = 'ball' and base = 'eclipse') or (kind = 'line' and base = 'comet');
update public.rb_cases set odds = '{8894,904,176,23,3,0}', variants = '{76104,23500,384,0,12}' where id = 'pocket';
update public.rb_cases set odds = '{8379,1318,270,30,3,0}', variants = '{76104,23500,384,0,12}' where id = 'starter';
update public.rb_cases set odds = '{7474,1894,541,77,13,1}', variants = '{74130,25400,440,18,12}' where id = 'standard';
update public.rb_cases set odds = '{6839,2141,836,143,40,1}', variants = '{72170,27250,520,42,18}' where id = 'premium';
update public.rb_cases set odds = '{10000,0,0,0,0,0}', variants = '{100000,0,0,0,0}' where id = 'jackpot';
update public.rb_cases set odds = '{6168,2172,1278,281,98,3}', variants = '{69320,29800,640,216,24}' where id = 'titan';
update public.rb_cases set odds = '{7788,0,1507,578,124,3}', variants = '{70156,29300,496,30,18}' where id = 'gamble';
update public.rb_cases set odds = '{4893,3405,1354,294,54,0}', variants = '{0,99220,720,42,18}' where id = 'painter';
update public.rb_cases set odds = '{2968,0,3730,2451,836,15}', variants = '{70190,29150,600,42,18}' where id = 'vault';
update public.rb_cases set odds = '{2316,0,0,5339,2285,60}', variants = '{68216,31050,656,54,24}' where id = 'mythic';
update public.rb_cases set odds = '{3500,4000,1900,500,100,0}', variants = '{100000,0,0,0,0}' where id = 'style';
update public.rb_cases set odds = '{5000,0,3500,1200,300,0}', variants = '{100000,0,0,0,0}' where id = 'themes';
update public.rb_cases set odds = '{3500,3800,2000,550,150,0}', variants = '{100000,0,0,0,0}' where id = 'profile';
update public.rb_cases set odds = '{6383,1938,1163,388,124,4}', variants = '{69320,29800,640,216,24}' where id = 'elite';
update public.rb_cases set odds = '{6208,0,2014,1343,425,10}', variants = '{68216,31050,656,54,24}' where id = 'royal';
update public.rb_cases set odds = '{5405,0,2096,1703,766,30}', variants = '{0,69400,30000,420,180}' where id = 'shiny';
update public.rb_cases set odds = '{3500,3800,2000,550,150,0}', variants = '{100000,0,0,0,0}' where id = 'banners';
update public.rb_cases set odds = '{8353,1281,302,55,9,0}', variants = '{76104,23500,384,0,12}' where id = 'lucky';
update public.rb_cases set odds = '{3500,3800,2000,550,150,0}', variants = '{100000,0,0,0,0}' where id = 'frames';
update public.rb_cases set odds = '{1885,0,4064,2921,1080,50}', variants = '{70190,29150,600,42,18}' where id = 'cosmos';
update public.rb_cases set odds = '{3500,0,4500,2000,0,0}', variants = '{100000,0,0,0,0}' where id = 'winter';
update public.rb_cases set odds = '{8000,1200,600,160,40,0}', variants = '{72170,27250,520,42,18}' where id = 'giftbox';
update public.rb_config set value = 2026111822 where key = 'min_build';
commit;
