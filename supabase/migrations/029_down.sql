-- 029 down: back to 4.5 / 4.5.1 (build 2026.11.18.23)
begin;

CREATE OR REPLACE FUNCTION public.rb_pawn_chance(ratio double precision, anger double precision)
 RETURNS double precision
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
    select case when ratio <= 1 then 1.0
                else greatest(0.0, power(greatest(0.0, 1 - (ratio - 1) / 0.6), 1.6) * (1 - least(100, anger) / 250.0)) end $function$;

CREATE OR REPLACE FUNCTION public.rb_pawn_rage(ratio double precision)
 RETURNS double precision
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
    select 20 + 60 * least(1.0, greatest(0.0, (ratio - 1) / 0.5)) $function$;

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
        klass := (array[3, 5, 4])[public.rb_roll(array[94300, 5300, 400]) + 1];
        item := public.rb_pick_mythic(klass);
    else
        klass := public.rb_roll(c.variants);
        if klass = 3 and tier <= 2 then klass := 2; end if;  -- no Titanium for Common and Rare badges
        item := public.rb_pick_badge(tier, klass);
    end if;
end $function$;

CREATE OR REPLACE FUNCTION public.rb_mines(action text, arg integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; r public.rb_rounds%rowtype; bombs integer[]; picked integer[]; n integer;
        pay integer := 0; hit boolean := false; done boolean := false;
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    select * into r from public.rb_rounds where owner = p.id and game = 'mines' and open for update;
    if action = 'start' then
        if found then raise exception 'rb_round_open'; end if;
        n := (arg / 10000);                                   -- arg = bombs * 10000 + bet
        if n not in (1, 3, 5, 10, 20) then raise exception 'rb_bad_choice'; end if;
        perform public.rb_bet(p, arg % 10000, 'mines');
        select array_agg(t) into bombs from (select t from generate_series(0, 24) t order by public.rb_rand() limit n) x;
        insert into public.rb_rounds (owner, game, bet, secret)
            values (p.id, 'mines', arg % 10000, jsonb_build_object('bombs', to_jsonb(bombs), 'picked', '[]'::jsonb))
            returning * into r;
        return jsonb_build_object('open', true, 'bet', r.bet, 'bombs', n, 'picked', '[]'::jsonb, 'mult', 1,
                                  'coins', p.coins - r.bet);
    end if;
    if not found then return jsonb_build_object('open', false); end if;
    select array_agg(v::int) into bombs from jsonb_array_elements_text(r.secret -> 'bombs') v;
    select coalesce(array_agg(v::int), '{}') into picked from jsonb_array_elements_text(r.secret -> 'picked') v;
    n := array_length(bombs, 1);
    if action = 'pick' then
        if arg is null or arg < 0 or arg > 24 or arg = any (picked) then raise exception 'rb_bad_choice'; end if;
        if arg = any (bombs) then
            hit := true; done := true;
        else
            picked := picked || arg;
            if coalesce(array_length(picked, 1), 0) >= 25 - n then action := 'cash'; end if;      -- every gem found
        end if;
    end if;
    if action = 'cash' then
        if coalesce(array_length(picked, 1), 0) < 1 then raise exception 'rb_bad_choice'; end if;
        pay := public.rb_win(p.id, r.bet * public.rb_mines_mult(array_length(picked, 1), n), 'mines');
        done := true;
    end if;
    update public.rb_rounds set open = not done, paid = pay,
           secret = jsonb_build_object('bombs', to_jsonb(bombs), 'picked', to_jsonb(picked)) where id = r.id;
    return jsonb_build_object('open', not done, 'bet', r.bet, 'bombs', n, 'picked', to_jsonb(picked), 'hit', hit,
        'tile', arg, 'mult', public.rb_mines_mult(coalesce(array_length(picked, 1), 0), n), 'paid', pay,
        'board', case when done then to_jsonb(bombs) end, 'coins', p.coins + pay);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_tower(action text, bet integer, arg integer, req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; res jsonb; r public.rb_rounds%rowtype; s jsonb; mode integer; lvl integer; cols integer;
        bombs integer; rows_ jsonb := '[]'::jsonb; i integer; row_b jsonb; pay integer := 0; picks jsonb;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if action = 'start' then perform public.rb_need_feature('casino'); end if;
    select * into r from public.rb_rounds where owner = p.id and game = 'tower' and open for update;
    if action = 'start' then
        if found then raise exception 'rb_round_open'; end if;
        mode := coalesce(arg, 1);
        if mode not between 0 and 3 then raise exception 'rb_bad_choice'; end if;
        cols := (array[4, 3, 2, 3])[mode + 1]; bombs := (array[1, 1, 1, 2])[mode + 1];
        perform public.rb_bet(p, bet, 'tower');
        for i in 1..8 loop
            select jsonb_agg(x) into row_b from (select x from generate_series(0, cols - 1) x order by public.rb_rand() limit bombs) t;
            rows_ := rows_ || jsonb_build_array(row_b);
        end loop;
        insert into public.rb_rounds (owner, game, bet, secret, open, paid)
            values (p.id, 'tower', bet, jsonb_build_object('mode', mode, 'rows', rows_, 'level', 0, 'picks', '[]'::jsonb), true, 0)
            returning * into r;
        return public.rb_remember(p.id, req, jsonb_build_object('open', true, 'mode', mode, 'level', 0, 'cols', cols, 'bombs', bombs,
            'mult', 1, 'next', public.rb_tower_mult(mode, 1), 'bet', bet, 'coins', p.coins - bet, 'picks', '[]'::jsonb));
    end if;
    if not found then
        if action = 'state' then return jsonb_build_object('open', false); end if;
        raise exception 'rb_round_gone';
    end if;
    s := r.secret; mode := (s ->> 'mode')::int; lvl := (s ->> 'level')::int; picks := s -> 'picks';
    cols := (array[4, 3, 2, 3])[mode + 1]; bombs := (array[1, 1, 1, 2])[mode + 1];
    if action = 'state' then
        return jsonb_build_object('open', true, 'mode', mode, 'level', lvl, 'cols', cols, 'bombs', bombs, 'picks', picks,
                                  'mult', public.rb_tower_mult(mode, lvl), 'next', public.rb_tower_mult(mode, lvl + 1), 'bet', r.bet);
    end if;
    if action = 'pick' then
        if arg is null or arg < 0 or arg >= cols then raise exception 'rb_bad_choice'; end if;
        picks := picks || to_jsonb(arg);
        if (s -> 'rows' -> lvl) @> to_jsonb(arg) then                              -- a bomb
            update public.rb_rounds set open = false, paid = 0, secret = s || jsonb_build_object('picks', picks, 'boom', true) where id = r.id;
            return public.rb_remember(p.id, req, jsonb_build_object('open', false, 'boom', true, 'level', lvl, 'picks', picks,
                'rows', s -> 'rows', 'paid', 0, 'bet', r.bet, 'coins', p.coins, 'mode', mode, 'cols', cols));
        end if;
        lvl := lvl + 1;
        if lvl < 8 then
            update public.rb_rounds set secret = s || jsonb_build_object('level', lvl, 'picks', picks) where id = r.id;
            return public.rb_remember(p.id, req, jsonb_build_object('open', true, 'level', lvl, 'picks', picks, 'mode', mode, 'cols', cols,
                'mult', public.rb_tower_mult(mode, lvl), 'next', public.rb_tower_mult(mode, lvl + 1), 'bet', r.bet, 'coins', p.coins));
        end if;
        action := 'cash';                                                        -- the top: paid at once
    end if;
    if action = 'cash' then
        if lvl < 1 then raise exception 'rb_bad_choice'; end if;
        pay := public.rb_win(p.id, r.bet * public.rb_tower_mult(mode, lvl), 'tower');
        update public.rb_rounds set open = false, paid = pay, secret = s || jsonb_build_object('level', lvl, 'picks', picks) where id = r.id;
        return public.rb_remember(p.id, req, jsonb_build_object('open', false, 'boom', false, 'level', lvl, 'picks', picks,
            'rows', s -> 'rows', 'paid', pay, 'mult', public.rb_tower_mult(mode, lvl), 'bet', r.bet, 'coins', p.coins + pay,
            'mode', mode, 'cols', cols));
    end if;
    raise exception 'rb_bad_choice';
end $function$;

CREATE OR REPLACE FUNCTION public.rb_hilo(action text, bet integer, req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; res jsonb; r public.rb_rounds%rowtype; cards jsonb; card integer; nxt integer;
        mult numeric; step numeric := coalesce(public.rb_cfg('hilo_step'), 0.985); pay integer := 0; right_ boolean;
        rank integer; hits integer; top numeric;
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into r from public.rb_rounds where owner = p.id and game = 'hilo' and open for update;
    if action = 'start' then
        if found then raise exception 'rb_round_open'; end if;
        perform public.rb_bet(p, bet, 'hilo');
        card := floor(public.rb_rand() * 52)::int;                  -- 0..51: rank = card % 13 + 1, suit = card / 13
        insert into public.rb_rounds (owner, game, bet, secret, open, paid)
            values (p.id, 'hilo', bet, jsonb_build_object('cards', jsonb_build_array(card), 'mult', 1, 'hits', 0), true, 0)
            returning * into r;
        return public.rb_remember(p.id, req, jsonb_build_object('open', true, 'cards', jsonb_build_array(card), 'mult', 1,
                                                                'hits', 0, 'bet', r.bet, 'coins', p.coins - r.bet));
    end if;
    if not found then
        if action = 'state' then return jsonb_build_object('open', false); end if;
        raise exception 'rb_round_gone';
    end if;
    cards := r.secret -> 'cards';
    mult := (r.secret ->> 'mult')::numeric;
    hits := (r.secret ->> 'hits')::int;
    card := (cards ->> (jsonb_array_length(cards) - 1))::int;
    rank := card % 13 + 1;
    if action = 'state' then
        return jsonb_build_object('open', true, 'cards', cards, 'mult', mult, 'hits', hits, 'bet', r.bet);
    end if;
    if action in ('higher', 'lower') then
        nxt := floor(public.rb_rand() * 52)::int;
        right_ := case when action = 'higher' then nxt % 13 + 1 >= rank else nxt % 13 + 1 <= rank end;
        cards := cards || to_jsonb(nxt);
        if not right_ then
            update public.rb_rounds set open = false, paid = 0,
                   secret = jsonb_build_object('cards', cards, 'mult', 0, 'hits', hits) where id = r.id;
            return public.rb_remember(p.id, req, jsonb_build_object('open', false, 'cards', cards, 'mult', 0, 'hits', hits,
                                                                    'right', false, 'paid', 0, 'bet', r.bet, 'coins', p.coins));
        end if;
        mult := round(mult * step * 13.0 / (case when action = 'higher' then 14 - rank else rank end), 4);
        hits := hits + 1;
        top := public.rb_cfg('win_max') / r.bet;
        if mult >= top then action := 'cash'; mult := top; end if;          -- the biggest prize: paid at once
        if action <> 'cash' then
            update public.rb_rounds set secret = jsonb_build_object('cards', cards, 'mult', mult, 'hits', hits) where id = r.id;
            return public.rb_remember(p.id, req, jsonb_build_object('open', true, 'cards', cards, 'mult', mult, 'hits', hits,
                                                                    'right', true, 'bet', r.bet, 'coins', p.coins));
        end if;
    end if;
    if action = 'cash' then
        if hits < 1 then raise exception 'rb_bad_choice'; end if;
        pay := public.rb_win(p.id, r.bet * mult, 'hilo');
        update public.rb_rounds set open = false, paid = pay,
               secret = jsonb_build_object('cards', cards, 'mult', mult, 'hits', hits) where id = r.id;
        return public.rb_remember(p.id, req, jsonb_build_object('open', false, 'cards', cards, 'mult', mult, 'hits', hits,
                                                                'right', true, 'paid', pay, 'bet', r.bet, 'coins', p.coins + pay));
    end if;
    raise exception 'rb_bad_choice';
end $function$;

CREATE OR REPLACE FUNCTION public.rb_blackjack(action text, bet integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; r public.rb_rounds%rowtype; deck integer[]; me integer[]; dealer integer[];
        stake integer; done boolean := false; pay integer := 0; outcome text := ''; spent integer := 0;
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    select * into r from public.rb_rounds where owner = p.id and game = 'blackjack' and open for update;
    if action = 'start' then
        if found then raise exception 'rb_round_open'; end if;
        perform public.rb_bet(p, bet, 'blackjack');
        spent := bet; stake := bet;
        select array_agg(c) into deck from (select c from generate_series(0, 51) c order by public.rb_rand()) x;
        me := array[deck[1], deck[3]]; dealer := array[deck[2], deck[4]]; deck := deck[5:52];
        insert into public.rb_rounds (owner, game, bet, secret) values (p.id, 'blackjack', bet, '{}'::jsonb) returning * into r;
        if public.rb_bj_total(me) = 21 or public.rb_bj_total(dealer) = 21 then action := 'natural'; done := true; end if;
    else
        if not found then return jsonb_build_object('open', false); end if;
        select array_agg(v::int) into deck from jsonb_array_elements_text(r.secret -> 'deck') v;
        select array_agg(v::int) into me from jsonb_array_elements_text(r.secret -> 'me') v;
        select array_agg(v::int) into dealer from jsonb_array_elements_text(r.secret -> 'dealer') v;
        stake := (r.secret ->> 'stake')::int;
        if action = 'double' then
            if array_length(me, 1) <> 2 then raise exception 'rb_bad_choice'; end if;
            perform public.rb_pay(p.id, -r.bet, 0, 'bet', 'blackjack');
            spent := r.bet; stake := stake + r.bet;
            me := me || deck[1]; deck := deck[2:];
            done := true;
        elsif action = 'hit' then
            me := me || deck[1]; deck := deck[2:];
            if public.rb_bj_total(me) >= 21 then done := true; end if;
        elsif action = 'stand' then
            done := true;
        else
            raise exception 'rb_bad_choice';
        end if;
    end if;
    if done then
        if action = 'natural' then
            if public.rb_bj_total(me) = 21 and public.rb_bj_total(dealer) = 21 then outcome := 'push'; pay := stake;
            elsif public.rb_bj_total(me) = 21 then outcome := 'blackjack'; pay := floor(stake * 2.5)::int;
            else outcome := 'lose'; end if;
        elsif public.rb_bj_total(me) > 21 then
            outcome := 'bust';
        else
            while public.rb_bj_total(dealer) < 17 loop dealer := dealer || deck[1]; deck := deck[2:]; end loop;
            if public.rb_bj_total(dealer) > 21 or public.rb_bj_total(me) > public.rb_bj_total(dealer) then
                outcome := 'win'; pay := stake * 2;
            elsif public.rb_bj_total(me) = public.rb_bj_total(dealer) then outcome := 'push'; pay := stake;
            else outcome := 'lose'; end if;
        end if;
        pay := public.rb_win(p.id, pay, 'blackjack');
    end if;
    update public.rb_rounds set open = not done, paid = pay, secret = jsonb_build_object('deck', to_jsonb(deck),
           'me', to_jsonb(me), 'dealer', to_jsonb(dealer), 'stake', stake) where id = r.id;
    return jsonb_build_object('open', not done, 'me', to_jsonb(me), 'total', public.rb_bj_total(me), 'stake', stake,
        'dealer', case when done then to_jsonb(dealer) else to_jsonb(dealer[1:1]) end,       -- the second card stays hidden
        'dealer_total', case when done then public.rb_bj_total(dealer) end,
        'outcome', outcome, 'paid', pay, 'coins', p.coins - spent + pay);
end $function$;

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
            d := least(1000, x_end / 110);
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
                if d >= 20 then
                    s := (s * 1103515245 + 12345) & 2147483647; n := (s >> 8) % (2 + 3 * d / 1000);
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
                sfrom := sfrom || (coalesce(array_length(px, 1), 0) + 1);
                if d >= 150 and ln_ >= 200 then                    -- 4.5: a spike on the longer ramps too
                    s := (s * 1103515245 + 12345) & 2147483647;
                    px := px || (x_end + ln_ / 2); pside := pside || ((s >> 8) % 2)::int; sn := sn || 1;
                else
                    sn := sn || 0;
                end if;
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
end $function$;

CREATE OR REPLACE FUNCTION public.rb_flip_bots()
 RETURNS TABLE(name text, tier text, lo double precision, hi double precision)
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
    values ('Pixel', 'low', 0.003::double precision, 0.012::double precision), ('Milo', 'low', 0.006, 0.02),
           ('Nova', 'mid', 0.02, 0.05), ('Juno', 'mid', 0.03, 0.08),
           ('Vega', 'high', 0.08, 0.16), ('Atlas', 'high', 0.12, 0.25) $function$;

drop function if exists public.rb_admin_cheat(text);
drop function if exists public.rb_trade_up(text, integer);
delete from public.rb_rigs where kind = 'cheat';
update public.rb_cases c set variants = b.variants from public.rb_cases_v45_variants b where b.id = c.id;
drop table if exists public.rb_cases_v45_variants;
delete from public.rb_config where key = 'cases_v46';
update public.rb_config set value = 25 where key = 'golf_turn_s';
update public.rb_config set value = 40 where key = 'golf_hole_total';
update public.rb_config set value = 2026111823 where key = 'min_build';

commit;
