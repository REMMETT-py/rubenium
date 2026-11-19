-- 030 down: back to 4.6 (029, build 2026.11.18.25)
begin;

CREATE OR REPLACE FUNCTION public.rb_admin_case(which text, new_price integer, new_odds integer[], new_variants integer[], new_min integer, new_max integer)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    perform public.rb_need_admin();
    if new_price < 1 or array_length(new_odds, 1) <> 6 or array_length(new_variants, 1) <> 5
       or (select sum(x) from unnest(new_odds) x) <> 10000 or (select sum(x) from unnest(new_variants) x) <> 100000
       or (select min(x) from unnest(new_odds || new_variants) x) < 0 or new_min < 0 or new_max < new_min then
        raise exception 'rb_bad_choice';
    end if;
    update public.rb_cases set price = new_price, odds = new_odds, variants = new_variants, coin_min = new_min,
           coin_max = new_max where id = which;
    if not found then raise exception 'rb_no_case'; end if;
    perform public.rb_log('case', which, jsonb_build_object('price', new_price, 'odds', new_odds, 'variants', new_variants));
    return true;
end $function$;

CREATE OR REPLACE FUNCTION public.rb_admin_cheat(game text)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare me uuid := auth.uid(); n text;
begin
    perform public.rb_need_admin();
    select username into n from public.profiles where id = me;
    if lower(coalesce(n, '')) <> 'ruben' then raise exception 'rb_not_admin'; end if;
    if game not in ('mines', 'tower', 'hilo', 'blackjack') then raise exception 'rb_bad_choice'; end if;
    insert into public.rb_rigs (owner, kind, key, data, by_name) values (me, 'cheat', game, '{}', n)
        on conflict (owner, kind, key) do update set at = now();
    return true;
end $function$;

CREATE OR REPLACE FUNCTION public.rb_blackjack(action text, bet integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; r public.rb_rounds%rowtype; deck integer[]; me integer[]; dealer integer[]; cheat_k integer;
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
            if public.rb_rig_take(p.id, 'cheat', 'blackjack') is not null then
                select i into cheat_k from generate_subscripts(deck, 1) i where public.rb_bj_total(me || deck[i]) <= 21
                 order by public.rb_bj_total(me || deck[i]) desc, i limit 1;
                if cheat_k is not null and cheat_k > 1 then
                    deck := deck[cheat_k:cheat_k] || deck[1:cheat_k - 1] || deck[cheat_k + 1:];
                end if;
            end if;
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

CREATE OR REPLACE FUNCTION public.rb_buy(what text, req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; c public.rb_catalog%rowtype; res jsonb; new_id uuid; cost integer;
begin
    perform public.rb_need_feature('shop');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into c from public.rb_catalog where id = what;
    if not found or c.price is null or c.kind in ('prog', 'tag') or c.limited then raise exception 'rb_not_for_sale'; end if;
    if c.kind = 'badge' and (c.cls >= 4 or c.rarity = 'exotic') then raise exception 'rb_not_for_sale'; end if;
    if c.kind <> 'badge' and exists (select 1 from public.rb_items it where it.owner = p.id and it.item = what) then
        raise exception 'rb_already_owned';
    end if;
    cost := public.rb_shop_price(what);
    perform public.rb_pay(p.id, -cost, 0, 'shop', what);
    new_id := public.rb_give(p.id, what, 'shop');
    return public.rb_remember(p.id, req, jsonb_build_object('id', new_id, 'item', what, 'coins', p.coins - cost, 'paid', cost));
end $function$;

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
        if klass = 3 and tier <= 2 then klass := 2; end if;
        if klass in (0, 1) and tier between 1 and 4
           and public.rb_rand() < (array[0.0005, 0.0004, 0.0003, 0.0002])[tier] then klass := 4; end if;   -- gold_extra  -- no Titanium for Common and Rare badges
        item := public.rb_pick_badge(tier, klass);
    end if;
end $function$;

CREATE OR REPLACE FUNCTION public.rb_case_gift(name text, which text, req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; them public.profiles%rowtype; c public.rb_cases%rowtype; res jsonb;
begin
    perform public.rb_need_feature('gifts');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    select * into them from public.profiles where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    if them.id = p.id then raise exception 'rb_thats_you'; end if;
    if not public.rb_is_friend(p.id, them.id) then raise exception 'rb_friends_only'; end if;
    select * into c from public.rb_cases where id = which;
    if not found then raise exception 'rb_no_case'; end if;
    if c.limited then raise exception 'rb_not_for_sale'; end if;
    if (select count(*) from public.rb_ledger where owner = p.id and reason = 'gift' and at >= date_trunc('day', now()))
       >= public.rb_cfg('gift_day') then
        raise exception 'rb_gift_limit';
    end if;
    perform public.rb_pay(p.id, -c.price, 0, 'gift', c.id || ':' || them.username);
    perform public.rb_stock_add(them.id, c.id, 1);
    perform public.rb_notice(them.id, 'gift', jsonb_build_object('from', p.username, 'case', c.id));
    return public.rb_remember(p.id, req, jsonb_build_object('coins', p.coins - c.price, 'keys', p.keys));
end $function$;

CREATE OR REPLACE FUNCTION public.rb_daily_case()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; r double precision; what text; coins integer := 0; keys integer := 0; new_id uuid;
        tier integer := 0;
begin
    perform public.rb_need_feature('cases');
    p := public.rb_lock_me();
    if p.daily_at is not null and now() < p.daily_at + make_interval(hours => public.rb_cfg('daily_hours')::int) then
        raise exception 'rb_too_soon';
    end if;
    r := public.rb_rand();
    if r < 0.50 then coins := 40 + floor(public.rb_rand() * 111)::int;
    elsif r < 0.65 then keys := 1;
    else
        tier := public.rb_roll(array[0, 7800, 1900, 270, 30]);
        what := public.rb_pick_badge(tier, (array[0, 1, 2])[public.rb_roll(array[7600, 2350, 50]) + 1]);
        new_id := public.rb_give(p.id, what, 'daily');
    end if;
    update public.profiles set daily_at = now() where id = p.id;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'daily', 0,
        jsonb_build_object('item', what, 'tier', tier, 'keys', keys), false,
        coins + coalesce((select value from public.rb_catalog where id = what), 0));
    perform public.rb_pay(p.id, coins, keys, 'daily_case', null);
    return jsonb_build_object('tier', tier, 'item', what, 'id', new_id, 'won', coins, 'won_keys', keys,
                              'coins', p.coins + coins, 'keys', p.keys + keys);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_deals()
 RETURNS json
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select json_build_object('deals', coalesce((select json_agg(json_build_object('item', d.item, 'pct', d.pct,
                                 'price', ceil(c.price * (1 + coalesce(public.rb_cfg('shop_tax'), 0)))::int,
                                 'now', public.rb_shop_price(d.item), 'worth', c.worth))
                                 from public.rb_deal_list() d join public.rb_catalog c on c.id = d.item), '[]'::json),
                             'ends_in', ceil(extract(epoch from ((public.rb_today() + 1)::timestamp at time zone 'Europe/Paris' - now())))::int) $function$;

CREATE OR REPLACE FUNCTION public.rb_duel_ask(name text, game text, tier integer, bet integer)
 RETURNS json
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; o public.profiles%rowtype; seed jsonb; did uuid;
begin
    perform public.rb_need_feature('minigames');
    p := public.rb_lock_me();
    select * into o from public.profiles where lower(username) = lower(name);
    if not found or o.id = p.id then raise exception 'rb_no_such_user'; end if;
    if not public.rb_is_friend(p.id, o.id) then raise exception 'rb_not_friends'; end if;
    if game not in ('tap', 'memory', 'park') or tier is null or tier not between 1 and 3 then raise exception 'rb_bad_choice'; end if;
    bet := coalesce(bet, 0);
    if bet <> 0 and (bet < 10 or bet % 10 <> 0 or bet > public.rb_duel_cap(p.coins, o.coins)) then
        raise exception 'rb_bad_bet';
    end if;
    if bet > 0 and not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    if (select count(*) from public.rb_duels d where d.a = p.id and d.state = 'asked') >= 3 then raise exception 'rb_too_many'; end if;
    seed := case game when 'tap' then public.rb_tap_chart()
                      when 'memory' then to_jsonb(public.rb_mem_board(tier))
                      else (select to_jsonb(pl.id) from public.rb_park_levels pl where pl.tier = rb_duel_ask.tier
                             order by public.rb_rand() limit 1) end;
    perform public.rb_pay(p.id, -bet, 0, 'duel_bet', null);
    insert into public.rb_duels (a, b, game, tier, bet, seed) values (p.id, o.id, game, tier, bet, seed) returning id into did;
    perform public.rb_notice(o.id, 'duel', jsonb_build_object('from', p.username, 'game', game, 'bet', bet, 'id', did));
    return json_build_object('id', did, 'coins', p.coins - bet);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_flip_create(side text, items uuid[])
 RETURNS json
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; f public.rb_flips%rowtype; r record;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('coinflip');
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    if side not in ('black', 'white') then raise exception 'rb_bad_choice'; end if;
    for r in select id from public.rb_flips where (a = p.id or b = p.id) and state in ('setup', 'open', 'joined', 'locked') loop
        perform public.rb_flip_tick(r.id);
    end loop;
    if public.rb_flip_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    insert into public.rb_flips (a, a_side, state) values (p.id, side, 'setup') returning * into f;
    if coalesce(array_length(items, 1), 0) > 0 then return public.rb_flip_put(f.id, items); end if;
    return public.rb_flip_json(f, p.id);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_flip_join(fid uuid)
 RETURNS json
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; f public.rb_flips%rowtype;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('coinflip');
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    perform public.rb_flip_tick(fid);
    select * into f from public.rb_flips where id = fid;
    if not found or f.state <> 'open' then raise exception 'rb_flip_taken'; end if;
    if f.a = p.id then raise exception 'rb_thats_you'; end if;
    if public.rb_flip_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    return public.rb_flip_json(f, p.id);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_flip_vs_bot(fid uuid)
 RETURNS json
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; f public.rb_flips%rowtype; rng double precision; whats text[]; total bigint;
        ch double precision; a_wins boolean; found_s double precision; choose_s double precision; bot text;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('coinflip');
    perform public.rb_flip_tick(fid);
    select * into f from public.rb_flips where id = fid for update;
    if not found or f.a is distinct from p.id then raise exception 'rb_duel_gone'; end if;
    if f.state <> 'open' then raise exception 'rb_flip_taken'; end if;
    rng := coalesce(public.rb_cfg('flip_range'), 0.1);
    whats := public.rb_flip_bot_fit(f.a_value, floor(f.a_value * (1 - rng))::bigint, ceil(f.a_value * (1 + rng))::bigint);
    if whats is null then raise exception 'rb_no_bot'; end if;
    select sum(public.rb_worth(w)) into total from unnest(whats) w;
    bot := public.rb_flip_bot_for(f.a_value);
    ch := greatest(coalesce(public.rb_cfg('flip_min_chance'), 0.49),
                   least(coalesce(public.rb_cfg('flip_max_chance'), 0.51), f.a_value::double precision / (f.a_value + total)));
    a_wins := public.rb_rand() < ch;
    a_wins := coalesce((public.rb_rig_take(p.id, 'flip', '') ->> 'win')::boolean, a_wins);   -- 4.4 rig
    found_s := 3 + random() * 4;                                      -- searching…
    choose_s := 3 + random() * 3;                                     -- the bot picks its items…
    update public.rb_flips set b = null, bot_side = 'b', bot_name = bot, b_what = whats, b_value = total,
           chance_a = round(ch::numeric, 4), joined_at = now(),
           bot_found_at = now() + make_interval(secs => found_s),
           locked_at = now() + make_interval(secs => found_s + choose_s),
           flip_at = now() + make_interval(secs => found_s + choose_s + 3 + coalesce(public.rb_cfg('flip_wait_s'), 15)),
           result = case when a_wins then f.a_side else (case when f.a_side = 'black' then 'white' else 'black' end) end,
           winner_side = case when a_wins then 'a' else 'b' end, state = 'locked'
     where id = f.id returning * into f;
    return public.rb_flip_json(f, p.id);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_friend_add(name text)
 RETURNS text
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare me public.profiles%rowtype; them uuid;
begin
    me := public.rb_lock_me();
    select id into them from public.profiles where lower(username) = lower(name);
    if them is null then raise exception 'rb_no_such_user'; end if;
    if them = me.id then raise exception 'rb_thats_you'; end if;
    if public.rb_is_friend(me.id, them) then return 'friends'; end if;
    if exists (select 1 from public.rb_friends where a = them and b = me.id) then
        update public.rb_friends set ok = true, at = now() where a = them and b = me.id;
        return 'friends';
    end if;
    if (select count(*) from public.rb_friends where a = me.id or b = me.id) >= 200 then
        raise exception 'rb_too_many';
    end if;
    insert into public.rb_friends (a, b) values (me.id, them) on conflict do nothing;
    return 'asked';
end $function$;

CREATE OR REPLACE FUNCTION public.rb_gold_wheel()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; r integer;
        prizes text[] := array['2500', '5000', '10000', '25000', 'premium', 'titan', 'vault', 'mythic'];
        odds integer[] := array[30, 25, 15, 5, 12, 8, 4, 1];
        what text; c integer := 0;
begin
    perform public.rb_need_feature('wheel');
    p := public.rb_lock_me();
    if p.gold_wheels < 1 then raise exception 'rb_nothing_to_collect'; end if;
    r := public.rb_roll(odds);
    what := prizes[r + 1];
    update public.profiles set gold_wheels = gold_wheels - 1 where id = p.id;
    if what ~ '^[0-9]+$' then
        c := what::int;
        perform public.rb_pay(p.id, c, 0, 'gold_wheel', what);
    else
        perform public.rb_stock_add(p.id, what, 1);
        perform public.rb_pay(p.id, 0, 1, 'gold_wheel', what);
    end if;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'gold_wheel', 0, jsonb_build_object('prize', what), false, c);
    return jsonb_build_object('slot', r, 'prize', what, 'coins_won', c, 'case', case when c = 0 then what end,
                              'coins', p.coins + c, 'keys', p.keys + case when c = 0 then 1 else 0 end, 'left', p.gold_wheels - 1);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_golf_create(bet integer)
 RETURNS json
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; gid uuid; hs integer[]; n integer; old record;
begin
    perform public.rb_need_feature('golf');
    p := public.rb_lock_me();
    for old in select id from public.rb_golf where (a = p.id or b = p.id) and state in ('open', 'asked', 'live') loop
        perform public.rb_golf_tick(old.id);
    end loop;
    if public.rb_golf_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    bet := coalesce(bet, 0);
    if bet <> 0 and (bet < 10 or bet % 10 <> 0 or bet > public.rb_golf_cap(p.coins)) then raise exception 'rb_bad_bet'; end if;
    hs := public.rb_golf_pick();
    n := array_length(hs, 1);
    perform public.rb_pay(p.id, -bet, 0, 'golf_bet', null);
    insert into public.rb_golf (a, b, bet, holes, state, a_strokes, b_strokes)
        values (p.id, null, bet, hs, 'open', array_fill(0, array[n]), array_fill(0, array[n])) returning id into gid;
    return json_build_object('id', gid, 'coins', p.coins - bet);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_golf_join(gid uuid)
 RETURNS json
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; g public.rb_golf%rowtype;
begin
    perform public.rb_need_feature('golf');
    p := public.rb_lock_me();
    perform public.rb_golf_tick(gid);
    select * into g from public.rb_golf where id = gid for update;
    if not found or g.state <> 'open' then raise exception 'rb_duel_gone'; end if;
    if g.a = p.id then raise exception 'rb_thats_you'; end if;
    if public.rb_golf_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    if p.coins < g.bet then raise exception 'rb_not_enough'; end if;
    perform public.rb_pay(p.id, -g.bet, 0, 'golf_bet', g.id::text);
    update public.rb_golf set b = p.id, state = 'live', turn = g.a, turn_at = now() where id = g.id;
    perform public.rb_notice(g.a, 'golf_yes', jsonb_build_object('from', p.username, 'id', g.id));
    return json_build_object('state', 'live', 'id', g.id, 'coins', p.coins - g.bet);
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
        if public.rb_rig_take(p.id, 'cheat', 'hilo') is not null then
            nxt := (case when action = 'higher' then rank - 1 + floor(public.rb_rand() * (14 - rank))::int
                         else floor(public.rb_rand() * rank)::int end) + 13 * floor(public.rb_rand() * 4)::int;
        end if;
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

CREATE OR REPLACE FUNCTION public.rb_market_buy(listing uuid, req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; res jsonb;
begin
    perform public.rb_need_feature('market');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    res := public.rb_market_deal(listing, p.id, (select price from public.rb_listings where id = listing));
    return public.rb_remember(p.id, req, res);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_market_cancel(listing uuid)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; l public.rb_listings%rowtype;
begin
    p := public.rb_lock_me();
    select * into l from public.rb_listings where id = listing and seller = p.id for update;
    if not found or l.state <> 'open' then raise exception 'rb_not_listed'; end if;
    update public.rb_listings set state = 'cancelled' where id = l.id;
    update public.rb_items set locked = null where id = l.item and locked = 'market:' || l.id;
    return true;
end $function$;

CREATE OR REPLACE FUNCTION public.rb_market_deal(listing uuid, who uuid, pay integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare l public.rb_listings%rowtype; buyer public.profiles%rowtype; fee integer;
begin
    select * into l from public.rb_listings where id = listing for update;
    if not found then raise exception 'rb_not_listed'; end if;
    perform 1 from public.profiles where id in (who, l.seller) order by id for update;
    if l.state <> 'open' then raise exception 'rb_sold'; end if;
    if l.seller = who then raise exception 'rb_own_listing'; end if;
    select * into buyer from public.profiles where id = who;
    if buyer.banned then raise exception 'rb_banned'; end if;
    if not public.rb_can_trade(buyer) then raise exception 'rb_trade_locked'; end if;
    if not exists (select 1 from public.rb_items where id = l.item and owner = l.seller and locked = 'market:' || l.id) then
        update public.rb_listings set state = 'cancelled' where id = l.id;
        raise exception 'rb_not_listed';
    end if;
    fee := ceil(pay * public.rb_cfg('market_fee'))::int;
    perform public.rb_pay(who, -pay, 0, 'market_buy', l.what);
    perform public.rb_pay(l.seller, pay - fee, 0, 'market_sell', l.what);
    update public.rb_items set owner = who, locked = null, origin = 'market' where id = l.item;
    insert into public.rb_seen (owner, item) values (who, l.what) on conflict do nothing;
    update public.rb_listings set state = 'sold', buyer = who, price = pay, sold_at = now() where id = l.id;
    update public.rb_offers set state = 'gone' where rb_offers.listing = l.id and state = 'open';
    perform public.rb_fix_equip(l.seller);
    perform public.rb_notice(l.seller, 'sold', jsonb_build_object('item', l.what, 'price', pay, 'got', pay - fee,
                                                                    'buyer', buyer.username));
    return jsonb_build_object('id', l.item, 'item', l.what, 'paid', pay, 'coins', buyer.coins - pay);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_market_list(item_id uuid, price integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; it public.rb_items%rowtype; c public.rb_catalog%rowtype; est integer;
        lid uuid;
begin
    perform public.rb_need_feature('market');
    p := public.rb_lock_me();
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    select * into it from public.rb_items where id = item_id and owner = p.id for update;
    if not found then raise exception 'rb_not_yours'; end if;
    if it.locked is not null then raise exception 'rb_item_locked'; end if;
    select * into c from public.rb_catalog where id = it.item;
    if not c.tradeable then raise exception 'rb_not_tradeable'; end if;
    est := public.rb_estimate(it.item);
    if price is null or price < ceil(est * public.rb_cfg('market_min_mult'))
       or price > greatest(floor(est * public.rb_cfg('market_max_mult')), coalesce(c.price, 0)) then
        raise exception 'rb_bad_price';
    end if;
    if (select count(*) from public.rb_listings where seller = p.id and state = 'open') >= public.rb_cfg('market_max_listings') then
        raise exception 'rb_too_many_listings';
    end if;
    insert into public.rb_listings (seller, item, what, price) values (p.id, it.id, it.item, price) returning id into lid;
    update public.rb_items set locked = 'market:' || lid where id = it.id;
    return jsonb_build_object('listing', lid, 'price', price);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_market_offer(listing uuid, price integer)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; l public.rb_listings%rowtype; oid uuid;
begin
    perform public.rb_need_feature('market');
    p := public.rb_lock_me();
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    select * into l from public.rb_listings where id = listing;
    if not found or l.state <> 'open' then raise exception 'rb_not_listed'; end if;
    if l.seller = p.id then raise exception 'rb_own_listing'; end if;
    if price is null or price >= l.price or price < ceil(l.price * public.rb_cfg('offer_min_share')) then
        raise exception 'rb_bad_price';
    end if;
    if price > p.coins then raise exception 'rb_not_enough'; end if;
    if (select count(*) from public.rb_offers where buyer = p.id and state = 'open') >= public.rb_cfg('offers_max') then
        raise exception 'rb_too_many_offers';
    end if;
    update public.rb_offers set state = 'gone' where rb_offers.listing = l.id and buyer = p.id and state = 'open';
    insert into public.rb_offers (listing, buyer, price) values (l.id, p.id, price) returning id into oid;
    perform public.rb_notice(l.seller, 'offer', jsonb_build_object('item', l.what, 'price', price, 'from', p.username));
    return oid;
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
        if public.rb_rig_take(p.id, 'cheat', 'mines') is not null then        -- always used up by the move
            if arg = any (bombs) then
                bombs := array_replace(bombs, arg, coalesce((select t from generate_series(0, 24) t where t <> all (bombs)
                         and t <> all (picked) and t <> arg order by public.rb_rand() limit 1), arg));
            end if;
        end if;
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

CREATE OR REPLACE FUNCTION public.rb_msg_send(name text, body text)
 RETURNS json
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; o public.profiles%rowtype; mid bigint; last public.rb_messages%rowtype;
        gap numeric := coalesce(public.rb_cfg('chat_gap_ms'), 1500) / 1000.0;
begin
    perform public.rb_need_feature('chat');
    p := public.rb_lock_me();
    select * into o from public.profiles where lower(username) = lower(name);
    if not found or o.id = p.id then raise exception 'rb_no_such_user'; end if;
    if not public.rb_is_friend(p.id, o.id) then raise exception 'rb_not_friends'; end if;
    body := btrim(regexp_replace(coalesce(body, ''), '[\x00-\x09\x0b-\x1f]', '', 'g'));
    if length(body) = 0 then raise exception 'rb_bad_choice'; end if;
    if length(body) > coalesce(public.rb_cfg('chat_max'), 300) then raise exception 'rb_too_long'; end if;
    select * into last from public.rb_messages m where m.a = p.id order by m.id desc limit 1;
    if found and clock_timestamp() - last.at < make_interval(secs => gap) then raise exception 'rb_chat_wait'; end if;
    if (select count(*) from public.rb_messages m where m.a = p.id
          and m.at > now() - make_interval(secs => coalesce(public.rb_cfg('chat_burst_s'), 10)))
       >= coalesce(public.rb_cfg('chat_burst'), 5) then raise exception 'rb_chat_wait'; end if;
    if exists (select 1 from public.rb_messages m where m.a = p.id and m.b = o.id
                 and lower(m.body) = lower(rb_msg_send.body) and m.at > now() - make_interval(secs => coalesce(public.rb_cfg('chat_same_s'), 60))) then
        raise exception 'rb_same_message';
    end if;
    if (select count(*) from public.rb_messages m where m.a = p.id and m.at > now() - interval '1 minute')
       >= public.rb_cfg('msg_per_min') then raise exception 'rb_chat_wait'; end if;
    insert into public.rb_messages (a, b, body) values (p.id, o.id, body) returning id into mid;
    if not exists (select 1 from public.rb_mutes m where m.owner = o.id and m.who = p.id) then
        perform public.rb_notice(o.id, 'message', jsonb_build_object('from', p.username, 'text', left(body, 60)));
    end if;
    return json_build_object('id', mid);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_pawn_sell(ids uuid[], ask bigint, req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; res jsonb; r public.rb_pawn%rowtype; q jsonb; base bigint; ratio double precision;
        ch double precision; yes boolean; price bigint; it public.rb_items%rowtype; n integer := 0; out_ jsonb;
begin
    perform public.rb_need_feature('market');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if coalesce(array_length(ids, 1), 0) = 0 or array_length(ids, 1) > 200 then raise exception 'rb_bad_choice'; end if;
    r := public.rb_pawn_me(p.id);
    if r.ban_until is not null then
        return public.rb_remember(p.id, req, jsonb_build_object('result', 'banned',
               'ban_left', ceil(extract(epoch from r.ban_until - now()))::int, 'anger', 0));
    end if;
    q := public.rb_pawn_quote(p.id, ids);
    base := (q ->> 'base')::bigint;
    if (q ->> 'n')::int = 0 or base <= 0 then raise exception 'rb_not_tradeable'; end if;
    if ask is null or ask <= base then
        ratio := 1; price := base; yes := true; ch := 1;
    else
        if ask > floor(base * 1.5) then raise exception 'rb_bad_choice'; end if;
        ratio := ask::double precision / base;
        ch := public.rb_pawn_chance(ratio, r.anger);
        yes := public.rb_rand() < ch;
        price := ask;
    end if;
    if not yes then
        r.anger := r.anger + public.rb_pawn_rage(ratio);
        if r.anger >= 100 then
            update public.rb_pawn set anger = 0, anger_at = now(), ban_until = now() + interval '30 minutes' where owner = p.id;
            return public.rb_remember(p.id, req, jsonb_build_object('result', 'kicked', 'anger', 100, 'ban_left', 1800,
                                                                    'chance', round(ch::numeric, 4)));
        end if;
        update public.rb_pawn set anger = r.anger, anger_at = now() where owner = p.id;
        return public.rb_remember(p.id, req, jsonb_build_object('result', 'no', 'anger', round(r.anger::numeric, 1),
                                                                'chance', round(ch::numeric, 4), 'base', base));
    end if;
    for it in select * from public.rb_items where owner = p.id and id = any (ids) and locked is null for update loop
        if public.rb_quick_value(p.id, it) > 0 then
            delete from public.rb_items where id = it.id;
            n := n + 1;
        end if;
    end loop;
    if n = 0 then raise exception 'rb_not_tradeable'; end if;
    perform public.rb_fix_equip(p.id);
    perform public.rb_pay(p.id, price::int, 0, 'quick_sell', n::text);
    if ratio > 1 then                                          -- a deal cools him down a little
        update public.rb_pawn set anger = greatest(0, r.anger - 10), anger_at = now() where owner = p.id;
    end if;
    out_ := jsonb_build_object('result', 'yes', 'paid', price, 'n', n, 'coins', p.coins + price,
                               'anger', round(greatest(0, r.anger - case when ratio > 1 then 10 else 0 end)::numeric, 1),
                               'equip', (select equip from public.profiles where id = p.id));
    return public.rb_remember(p.id, req, out_);
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
        if public.rb_rig_take(p.id, 'cheat', 'tower') is not null then         -- always used up by the move
            if (s -> 'rows' -> lvl) @> to_jsonb(arg) then
                s := jsonb_set(s, array['rows', lvl::text], (select coalesce(jsonb_agg(x), '[]'::jsonb) from (select x
                       from generate_series(0, cols - 1) x where x <> arg order by ((s -> 'rows' -> lvl) @> to_jsonb(x)) desc,
                       public.rb_rand() limit jsonb_array_length(s -> 'rows' -> lvl)) t));
            end if;
        end if;
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

CREATE OR REPLACE FUNCTION public.rb_trade_confirm(trade uuid, seen_version integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare me uuid := auth.uid(); t public.rb_trades%rowtype; pa public.profiles%rowtype; pb public.profiles%rowtype;
        bad boolean;
begin
    perform public.rb_need_feature('trading');
    select * into t from public.rb_trades where id = trade for update;
    if not found or me is null or (t.a <> me and t.b <> me) or t.state <> 'open' then raise exception 'rb_trade_gone'; end if;
    if t.version <> seen_version then raise exception 'rb_trade_changed'; end if;
    if not (t.a_ready and t.b_ready) or t.ready_at is null then raise exception 'rb_not_ready'; end if;
    if now() < t.ready_at + interval '5 seconds' then raise exception 'rb_wait'; end if;
    if t.a = me then t.a_ok := true; else t.b_ok := true; end if;
    update public.rb_trades set a_ok = t.a_ok, b_ok = t.b_ok, updated = now() where id = t.id;
    if not (t.a_ok and t.b_ok) then return jsonb_build_object('done', false); end if;
    perform 1 from public.profiles where id in (t.a, t.b) order by id for update;
    select * into pa from public.profiles where id = t.a;
    select * into pb from public.profiles where id = t.b;
    perform 1 from public.rb_items where id in (select item from public.rb_trade_items where rb_trade_items.trade = t.id)
      order by id for update;
    select exists (select 1 from public.rb_trade_items ti left join public.rb_items it on it.id = ti.item
                    where ti.trade = t.id
                      and (it.id is null or it.owner <> (case ti.side when 'a' then t.a else t.b end)
                           or it.locked is distinct from 'trade:' || t.id)) into bad;
    if bad or pa.coins < t.a_coins or pb.coins < t.b_coins or pa.keys < t.a_keys or pb.keys < t.b_keys then
        perform public.rb_trade_end(t.id, 'failed');
        return jsonb_build_object('done', false, 'failed', true);
    end if;
    update public.rb_items it set owner = case ti.side when 'a' then t.b else t.a end, locked = null, origin = 'trade'
      from public.rb_trade_items ti where ti.trade = t.id and ti.item = it.id;
    insert into public.rb_seen (owner, item)
        select case ti.side when 'a' then t.b else t.a end, ti.what from public.rb_trade_items ti where ti.trade = t.id
        on conflict do nothing;
    perform public.rb_pay(t.a, t.b_coins - t.a_coins, t.b_keys - t.a_keys, 'trade', t.id::text);
    perform public.rb_pay(t.b, t.a_coins - t.b_coins, t.a_keys - t.b_keys, 'trade', t.id::text);
    perform public.rb_fix_equip(t.a);
    perform public.rb_fix_equip(t.b);
    update public.rb_trades set state = 'done', updated = now() where id = t.id;
    return jsonb_build_object('done', true);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_trade_offer(trade uuid, items uuid[], coins integer, keys integer)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare me uuid := auth.uid(); t public.rb_trades%rowtype; my text; p public.profiles%rowtype; n integer;
begin
    perform public.rb_need_feature('trading');
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into t from public.rb_trades where id = trade for update;
    if not found or (t.a <> me and t.b <> me) or t.state <> 'open' then raise exception 'rb_trade_gone'; end if;
    my := case when t.a = me then 'a' else 'b' end;
    items := coalesce(items, '{}');
    n := coalesce(array_length(items, 1), 0);
    if n > 8 or n <> (select count(distinct x) from unnest(items) x) then raise exception 'rb_bad_offer'; end if;
    select * into p from public.profiles where id = me;
    if coins is null or coins < 0 or coins > p.coins then raise exception 'rb_not_enough'; end if;
    keys := coalesce(keys, 0);
    if keys < 0 or keys > p.keys or keys > 99 then raise exception 'rb_not_enough'; end if;
    update public.rb_items set locked = null where owner = me and locked = 'trade:' || t.id;
    delete from public.rb_trade_items where rb_trade_items.trade = t.id and rb_trade_items.side = my;
    if n > 0 then
        perform 1 from public.rb_items where id = any (items) order by id for update;
        if (select count(*) from public.rb_items it join public.rb_catalog c on c.id = it.item
             where it.id = any (items) and it.owner = me and it.locked is null and c.tradeable) <> n then
            raise exception 'rb_item_locked';
        end if;
        update public.rb_items set locked = 'trade:' || t.id where id = any (items);
        insert into public.rb_trade_items (trade, side, item, what)
            select t.id, my, it.id, it.item from public.rb_items it where it.id = any (items);
    end if;
    update public.rb_trades set a_coins = case when my = 'a' then rb_trade_offer.coins else a_coins end,
                                b_coins = case when my = 'b' then rb_trade_offer.coins else b_coins end,
                                a_keys = case when my = 'a' then rb_trade_offer.keys else a_keys end,
                                b_keys = case when my = 'b' then rb_trade_offer.keys else b_keys end,
           a_ready = false, b_ready = false, a_ok = false, b_ok = false, ready_at = null,
           version = version + 1, updated = now()
     where id = t.id;
    return t.version + 1;
end $function$;

CREATE OR REPLACE FUNCTION public.rb_trade_ready(trade uuid, ready boolean, seen_version integer)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare me uuid := auth.uid(); t public.rb_trades%rowtype;
begin
    perform public.rb_need_feature('trading');
    select * into t from public.rb_trades where id = trade for update;
    if not found or me is null or (t.a <> me and t.b <> me) or t.state <> 'open' then raise exception 'rb_trade_gone'; end if;
    if t.version <> seen_version then raise exception 'rb_trade_changed'; end if;     -- you must see what you accept
    if t.a = me then t.a_ready := ready; else t.b_ready := ready; end if;
    update public.rb_trades set a_ready = t.a_ready, b_ready = t.b_ready, a_ok = false, b_ok = false,
           ready_at = case when t.a_ready and t.b_ready then now() end, updated = now()
     where id = t.id;
    return true;
end $function$;

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
    if not public.rb_is_friend(p.id, them.id) then raise exception 'rb_not_friends'; end if;
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
end $function$;

CREATE OR REPLACE FUNCTION public.rb_wave_create(bet integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; did uuid; old record;
begin
    perform public.rb_need_feature('wave');
    p := public.rb_lock_me();
    for old in select id from public.rb_wave_duels where (a = p.id or b = p.id) and state in ('open', 'live') loop
        perform public.rb_wave_tick(old.id);
    end loop;
    if public.rb_wave_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    bet := coalesce(bet, 0);
    if bet <> 0 and (bet < 10 or bet % 10 <> 0 or bet > public.rb_golf_cap(p.coins)) then raise exception 'rb_bad_bet'; end if;
    perform public.rb_pay(p.id, -bet, 0, 'wave_bet', null);
    insert into public.rb_wave_duels (a, bet, seed) values (p.id, bet, floor(public.rb_rand() * 2147483647)::bigint)
        returning id into did;
    return jsonb_build_object('id', did, 'coins', p.coins - bet);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_wave_join(did uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; w public.rb_wave_duels%rowtype; ra uuid; rb uuid;
begin
    perform public.rb_need_feature('wave');
    p := public.rb_lock_me();
    perform public.rb_wave_tick(did);
    select * into w from public.rb_wave_duels where id = did for update;
    if not found or w.state <> 'open' then raise exception 'rb_duel_gone'; end if;
    if w.a = p.id then raise exception 'rb_thats_you'; end if;
    if public.rb_wave_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    if p.coins < w.bet then raise exception 'rb_not_enough'; end if;
    perform public.rb_pay(p.id, -w.bet, 0, 'wave_bet', w.id::text);
    insert into public.rb_wave_runs (owner, seed, duel, started_at) values (w.a, w.seed, w.id, now() + interval '4 seconds')
        returning id into ra;
    insert into public.rb_wave_runs (owner, seed, duel, started_at) values (p.id, w.seed, w.id, now() + interval '4 seconds')
        returning id into rb;
    update public.rb_wave_duels set b = p.id, state = 'live', live_at = now(), a_run = ra, b_run = rb where id = w.id
        returning * into w;
    perform public.rb_notice(w.a, 'wave_yes', jsonb_build_object('from', p.username, 'id', w.id));
    return public.rb_wave_duel_json(w, p.id) || jsonb_build_object('coins', p.coins - w.bet);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_admin_cheat(game text)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare me uuid := auth.uid(); n text;
begin
    perform public.rb_need_admin();
    select username into n from public.profiles where id = me;
    if lower(coalesce(n, '')) <> 'ruben' then raise exception 'rb_not_admin'; end if;
    if game not in ('mines', 'tower', 'hilo', 'blackjack') then raise exception 'rb_bad_choice'; end if;
    insert into public.rb_rigs (owner, kind, key, data, by_name) values (me, 'cheat', game, '{}', n)
        on conflict (owner, kind, key) do update set at = now();
    return true;
end $function$;
revoke all on function rb_admin_cheat(text) from public, anon;
grant execute on function rb_admin_cheat(text) to authenticated;

drop function if exists rb_case_gift_n(text,text,integer,text);
drop function if exists rb_gift_left();
drop function if exists rb_pawn_ask(uuid[],bigint,text);
drop function if exists rb_pawn_key(uuid[]);
drop function if exists rb_rate(uuid,text,integer);

update public.rb_cases c set odds = b.odds, variants = b.variants, coin_min = b.coin_min, coin_max = b.coin_max
  from public.rb_cases_v46 b where b.id = c.id;
alter table public.rb_cases drop column if exists grid;
drop table if exists public.rb_cases_v46;
delete from public.rb_config where key = 'cases_v47';
alter table public.rb_pawn drop column if exists deal, drop column if exists deal_key, drop column if exists deal_at;
drop table if exists public.rb_rate_hits;
drop table if exists public.rb_deal_buys;
update public.rb_config set value = 2026111825 where key = 'min_build';

commit;
