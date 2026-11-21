-- 5.9: jackpot of 5 players at most (bots sometimes put in something much smaller or much bigger), keys found again in
-- the casino games (a few a day, always shown), blackjack cheats that do not look like cheats.

insert into public.rb_config (key, value) values ('key_casino_pct', 2), ('key_casino_min_bet', 50), ('key_find_day', 6)
    on conflict (key) do nothing;

create or replace function public.rb_keys_today(who uuid) returns integer
    language sql stable security definer set search_path = '' as $$
    select coalesce(sum(keys), 0)::int from public.rb_ledger
     where owner = who and reason = 'key_found' and at >= date_trunc('day', now() at time zone 'Europe/Paris') at time zone 'Europe/Paris'
$$;

create or replace function public.rb_key_find(who uuid, g text) returns integer
    language plpgsql security definer set search_path = '' as $$
begin
    if public.rb_rand() * 100 >= coalesce(public.rb_cfg('key_find_pct'), 0) then return 0; end if;
    if exists (select 1 from public.profiles where id = who and bot) then return 0; end if;
    if public.rb_keys_today(who) >= coalesce(public.rb_cfg('key_find_day'), 6) then return 0; end if;
    perform public.rb_pay(who, 0, 1, 'key_found', g);
    perform public.rb_notice(who, 'key_found', jsonb_build_object('game', g, 'keys', 1));
    return 1;
end $$;

-- a casino bet of 50 coins or more has a small chance to give a key (the daily limit is shared with the mini games)
create or replace function public.rb_bet(p public.profiles, bet integer, game text) returns void
    language plpgsql security definer set search_path = '' as $$
begin
    if bet is null or bet < public.rb_cfg('bet_min') or bet > public.rb_bet_cap(p.coins) then
        raise exception 'rb_bad_bet';
    end if;
    perform public.rb_pay(p.id, -bet, 0, 'bet', game);
    if bet >= coalesce(public.rb_cfg('key_casino_min_bet'), 50)
       and public.rb_rand() * 100 < coalesce(public.rb_cfg('key_casino_pct'), 0)
       and not coalesce(p.bot, false)
       and public.rb_keys_today(p.id) < coalesce(public.rb_cfg('key_find_day'), 6) then
        perform public.rb_pay(p.id, 0, 1, 'key_found', game);
        perform public.rb_notice(p.id, 'key_found', jsonb_build_object('game', game, 'keys', 1));
    end if;
end $$;

create or replace function public.rb_fake_jackpot(who uuid) returns void
    language plpgsql security definer set search_path = '' as $$
declare j public.rb_jackpots%rowtype; n integer; minj bigint; ids uuid[]; whats text[]; val bigint; col integer;
begin
    select * into j from public.rb_jackpots where slot = public.rb_jackpot_slot(now()) and state = 'open'
       and now() < lock_at - interval '10 seconds' for update;
    if not found then return; end if;
    select count(*) into n from public.rb_jackpot_entries where jackpot = j.id;
    if n < 1 or n >= 5 or exists (select 1 from public.rb_jackpot_entries where jackpot = j.id and owner = who) then return; end if;
    minj := greatest(coalesce(public.rb_cfg('jackpot_min_worth'), 500)::bigint,
                     (select coalesce(sum(value), 0) from public.rb_jackpot_entries where jackpot = j.id) / 100);
    select array_agg(id), array_agg(item), sum(w) into ids, whats, val from (
        select i.id, i.item, public.rb_worth(i.item) w from public.rb_items i join public.rb_catalog c on c.id = i.item
         where i.owner = who and i.locked is null and c.tradeable and public.rb_worth(i.item) > 0
         order by public.rb_worth(i.item) desc limit 1 + floor(random() * 2)::int) z;
    if ids is null or val < minj or val > coalesce(public.rb_cfg('jackpot_max_worth'), 250000) then return; end if;
    select c into col from generate_series(0, 5) c
     where c not in (select colour from public.rb_jackpot_entries where jackpot = j.id) order by random() limit 1;
    update public.rb_items set locked = 'jackpot:' || j.id where id = any (ids);
    insert into public.rb_jackpot_entries (jackpot, owner, colour, item_ids, whats, value) values (j.id, who, col, ids, whats, val);
end $$;

create or replace function public.rb_jackpot_advance(jid uuid) returns void
    language plpgsql security definer set search_path = '' as $$
declare j public.rb_jackpots%rowtype; n integer; avg_ bigint; k integer; tgt bigint; whats text[]; free_c integer[];
        r_ double precision; acc bigint := 0; e record; names text[]; nm text; seats integer; luck double precision;
begin
    select * into j from public.rb_jackpots where id = jid for update;
    if not found then return; end if;
    if j.state = 'open' and now() >= j.lock_at then
        select count(*), coalesce(avg(value), 0)::bigint into n, avg_ from public.rb_jackpot_entries where jackpot = j.id;
        if n = 0 then
            update public.rb_jackpots set state = 'empty' where id = j.id;
            return;
        end if;
        select array_agg(c order by random()) into free_c from generate_series(0, 5) c
         where c not in (select colour from public.rb_jackpot_entries where jackpot = j.id);
        select array_agg(b.name order by random()) into names from public.rb_flip_bots() b;
        seats := greatest(0, 5 - n);                         -- 5.9: 5 players at most
        for k in 1 .. seats loop
            luck := random();
            tgt := case when luck < 0.07 then avg_ * (0.03 + 0.12 * random())        -- rare: a tiny bit of junk
                        when luck < 0.12 then avg_ * (1.6 + 1.9 * random())          -- rare: a big item
                        else avg_ * (0.35 + 0.55 * random()) end;
            tgt := greatest(60, tgt);
            whats := public.rb_flip_bot_items(tgt, 1 + floor(random() * 2)::int);
            continue when coalesce(array_length(whats, 1), 0) = 0;
            nm := names[k];
            insert into public.rb_jackpot_entries (jackpot, owner, bot_name, colour, whats, value, join_at)
                values (j.id, null, nm, free_c[k], whats, (select sum(public.rb_worth(x)) from unnest(whats) x),
                        j.lock_at + make_interval(secs => 1.6 * k));
        end loop;
        select sum(value) into j.total from public.rb_jackpot_entries where jackpot = j.id;
        r_ := public.rb_rand() * j.total;
        for e in select id, value from public.rb_jackpot_entries where jackpot = j.id order by join_at, id loop
            acc := acc + e.value;
            if r_ < acc then j.winner_entry := e.id; exit; end if;
        end loop;
        update public.rb_jackpots set state = 'locked', total = j.total, winner_entry = j.winner_entry,
               roll = r_ / greatest(1, j.total) where id = j.id;
        return;
    end if;
    if j.state = 'locked' and now() >= j.result_at then
        if (select owner from public.rb_jackpot_entries where id = j.winner_entry) is null then
            perform public.rb_jackpot_finish(j.id, '{}');
            return;
        end if;
        n := jsonb_array_length(public.rb_jackpot_pool(j));
        if n = 0 then
            perform public.rb_jackpot_finish(j.id, '{}');
            return;
        end if;
        update public.rb_jackpots set state = 'picking', picks_allowed = greatest(1, (n + 2) / 3) where id = j.id;
        return;
    end if;
    if j.state = 'picking' and now() >= j.pick_until then
        perform public.rb_jackpot_finish(j.id, public.rb_jackpot_auto(j));
    end if;
end $$;

create or replace function public.rb_jackpot_join(items uuid[], req text) returns jsonb
    language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; j public.rb_jackpots%rowtype; n integer; val bigint; whats text[];
        minj bigint; col integer; it record;
begin
    perform public.rb_need_feature('jackpot');
    perform public.rb_rate(auth.uid(), 'jackpot', 10);
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    j := public.rb_jackpot_make(public.rb_jackpot_slot(now()));
    select * into j from public.rb_jackpots where id = j.id for update;
    if j.state <> 'open' or now() >= j.lock_at then raise exception 'rb_jackpot_closed'; end if;
    if exists (select 1 from public.rb_jackpot_entries where jackpot = j.id and owner = p.id) then
        raise exception 'rb_jackpot_in';
    end if;
    select count(*) into n from public.rb_jackpot_entries where jackpot = j.id;
    if n >= 5 then raise exception 'rb_jackpot_full'; end if;
    if coalesce(array_length(items, 1), 0) not between 1 and 3 or
       (select count(distinct x) from unnest(items) x) <> array_length(items, 1) then raise exception 'rb_bad_choice'; end if;
    for it in select i.* from public.rb_items i where i.id = any (items) for update loop
        if it.owner <> p.id or it.locked is not null or not coalesce((select c.tradeable from public.rb_catalog c
                                                                       where c.id = it.item), false) then
            raise exception 'rb_item_locked';
        end if;
    end loop;
    select array_agg(i.item order by i.id), sum(public.rb_worth(i.item)) into whats, val
      from public.rb_items i where i.id = any (items) and i.owner = p.id;
    if coalesce(array_length(whats, 1), 0) <> array_length(items, 1) or coalesce(val, 0) <= 0 then
        raise exception 'rb_item_locked';
    end if;
    minj := greatest(coalesce(public.rb_cfg('jackpot_min_worth'), 100)::bigint,
                     (select coalesce(sum(value), 0) from public.rb_jackpot_entries where jackpot = j.id)
                     * coalesce(public.rb_cfg('jackpot_min_pct'), 1) / 100);
    if val < minj then raise exception 'rb_jackpot_too_small'; end if;
    if val > coalesce(public.rb_cfg('jackpot_max_worth'), 250000) then raise exception 'rb_jackpot_too_big'; end if;
    select c into col from generate_series(0, 5) c
     where c not in (select colour from public.rb_jackpot_entries where jackpot = j.id) order by random() limit 1;
    update public.rb_items set locked = 'jackpot:' || j.id where id = any (items);
    insert into public.rb_jackpot_entries (jackpot, owner, colour, item_ids, whats, value)
        values (j.id, p.id, col, items, whats, val);
    return public.rb_remember(p.id, req, public.rb_jackpot_json(j, p.id));
end $$;

-- 5.9: Ruben's blackjack cheat no longer hits 21 every time. On "hit" he gets a card that does not bust him (any of
-- them); on "stand" or "double" the deck is shuffled until the dealer ends below him or busts. It looks like luck.
create or replace function public.rb_bj_rig_dealer(me integer[], dealer integer[], deck integer[]) returns integer[]
    language plpgsql volatile set search_path = '' as $$
declare k integer; d integer[]; t integer[]; dt integer;
begin
    if public.rb_bj_total(me) > 21 then return deck; end if;
    for k in 1 .. 40 loop
        select array_agg(c order by random()) into t from unnest(deck) c;
        d := dealer;
        dt := 1;
        while public.rb_bj_total(d) < 17 loop d := d || t[dt]; dt := dt + 1; end loop;
        if public.rb_bj_total(d) > 21 or public.rb_bj_total(d) < public.rb_bj_total(me) then return t; end if;
    end loop;
    return deck;
end $$;

create or replace function public.rb_blackjack(action text, bet integer) returns jsonb
    language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r public.rb_rounds%rowtype; deck integer[]; me integer[]; dealer integer[]; cheat_k integer;
        stake integer; done boolean := false; pay integer := 0; outcome text := ''; spent integer := 0; cheat boolean := false;
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
        if action in ('hit', 'double', 'stand') then
            cheat := public.rb_rig_take(p.id, 'cheat', 'blackjack') is not null;
        end if;
        if cheat and action in ('hit', 'double') then                    -- a random card that does not bust
            select i into cheat_k from generate_subscripts(deck, 1) i where public.rb_bj_total(me || deck[i]) <= 21
             order by random() limit 1;
            if cheat_k is not null and cheat_k > 1 then
                deck := deck[cheat_k:cheat_k] || deck[1:cheat_k - 1] || deck[cheat_k + 1:];
            end if;
        end if;
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
        if cheat and done and action in ('stand', 'double') then
            deck := public.rb_bj_rig_dealer(me, dealer, deck);
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
        'dealer', case when done then to_jsonb(dealer) else to_jsonb(dealer[1:1]) end,
        'dealer_total', case when done then public.rb_bj_total(dealer) end,
        'outcome', outcome, 'paid', pay, 'coins', p.coins - spent + pay);
end $$;

revoke all on function public.rb_keys_today(uuid) from public, anon, authenticated;
revoke all on function public.rb_bj_rig_dealer(integer[], integer[], integer[]) from public, anon, authenticated;

-- 5.9: admin bots look real: a level, a look (banner, frame, ball, trail, theme, font), numbers for every game, friends
-- and a "last seen". The numbers set by an admin are added on top of what the bot really did.
create or replace function public.rb_stats_real(who uuid) returns json
    language sql stable security definer set search_path = '' as $$
    with r as (select * from public.rb_rounds where owner = who and not open),
         g as (select * from r where game in ('slots', 'plinko', 'dice', 'mines', 'rocket', 'blackjack'))
    select json_build_object(
        'bet', (select coalesce(sum(bet), 0) from g), 'won', (select coalesce(sum(paid), 0) from g),
        'best', (select coalesce(max(paid), 0) from g), 'rounds', (select count(*) from g),
        'cases', (select count(*) from r where game like 'case:%' or game = 'daily'),
        'spins', (select count(*) from r where game = 'spin'),
        'mini', (select count(*) from r where game = 'mini'),
        'park', (select count(*) from r where game = 'park'), 'memory', (select count(*) from r where game = 'memory'),
        'duels', (select count(*) from public.rb_duels d where d.state = 'done' and d.winner = who),
        'streak', (select streak from public.profiles where id = who),
        'worth', (select coalesce(sum(public.rb_worth(c.id)), 0) from public.rb_items it join public.rb_catalog c on c.id = it.item
                   where it.owner = who),
        'first_case', (select min(at) from r where game like 'case:%'),
        'gold', (select count(*) from public.rb_items it join public.rb_catalog c on c.id = it.item
                  where it.owner = who and c.kind = 'badge' and c.cls = 4),
        'trades', (select count(*) from public.rb_trades t where t.state = 'done' and (t.a = who or t.b = who)),
        'items', (select count(*) from public.rb_items it where it.owner = who),
        'badges', (select count(distinct it.item) from public.rb_items it where it.owner = who and it.item like 'badge:%'),
        'friends', (select count(*) from public.rb_friends f where f.ok and (f.a = who or f.b = who))) $$;

create or replace function public.rb_stats(who uuid) returns json
    language plpgsql stable security definer set search_path = '' as $$
declare real_ jsonb := public.rb_stats_real(who)::jsonb; extra jsonb;
begin
    select bot_cfg -> 'stats' into extra from public.profiles where id = who and bot;
    if extra is null or jsonb_typeof(extra) <> 'object' then return real_::json; end if;
    return (real_ || coalesce((select jsonb_object_agg(e.key, coalesce((real_ ->> e.key)::numeric, 0) + (e.value #>> '{}')::numeric)
                                 from jsonb_each(extra) e where jsonb_typeof(e.value) = 'number'), '{}'::jsonb))::json;
end $$;

create or replace function public.rb_bot_look(who uuid) returns void
    language plpgsql security definer set search_path = '' as $$
declare k text; it text; eq jsonb := '{}'::jsonb; slot text;
begin
    foreach k in array array['banner', 'frame', 'ball', 'line', 'theme', 'font'] loop
        continue when random() < 0.25;                                   -- not everybody wears everything
        select c.id into it from public.rb_catalog c where c.kind = k and c.tradeable and c.value > 0
         order by random() * (1 + ln(1 + c.value)) / (1 + c.value / 4000.0) desc limit 1;   -- mostly cheaper things
        continue when it is null;
        if not exists (select 1 from public.rb_items x where x.owner = who and x.item = it) then
            perform public.rb_give(who, it, 'case:standard');
        end if;
        slot := case k when 'line' then 'ring' else k end;
        eq := eq || jsonb_build_object(slot, it);
    end loop;
    update public.profiles set equip = coalesce(equip, '{}'::jsonb) - 'banner' - 'frame' - 'ball' - 'ring' - 'theme' - 'font' || eq
     where id = who;
    insert into public.rb_seen (owner, item) select owner, item from public.rb_items where owner = who on conflict do nothing;
end $$;

create or replace function public.rb_admin_bot_set(name text, cfg jsonb) returns json
    language plpgsql security definer set search_path = '' as $$
declare me uuid := public.rb_need_admin(); p public.profiles%rowtype; want integer; have integer; i integer;
        t integer; k integer; best text[]; lv integer; st jsonb := '{}'::jsonb; e record;
begin
    select * into p from public.profiles where lower(username) = lower(name) for update;
    if not found then raise exception 'rb_no_such_user'; end if;
    if not p.bot then raise exception 'rb_bad_choice'; end if;
    if jsonb_typeof(cfg -> 'stats') = 'object' then                     -- only whole numbers, never below 0
        for e in select * from jsonb_each(cfg -> 'stats') loop
            continue when e.key !~ '^[a-z_0-9]{1,24}$' or jsonb_typeof(e.value) <> 'number';
            st := st || jsonb_build_object(e.key, greatest(0, least(100000000, floor((e.value #>> '{}')::numeric)))::bigint);
        end loop;
    end if;
    update public.profiles set
        minutes = greatest(0, coalesce((cfg ->> 'hours')::numeric * 60, minutes))::int,
        coins = greatest(0, coalesce((cfg ->> 'coins')::bigint, coins)),
        keys = least(48, greatest(0, coalesce((cfg ->> 'keys')::int, keys))),
        streak = greatest(0, coalesce((cfg ->> 'streak')::int, streak)),
        streak_day = case when coalesce((cfg ->> 'streak')::int, 0) > 0 then public.rb_today() else streak_day end,
        created_at = case when cfg ? 'days' then now() - make_interval(days => greatest(0, (cfg ->> 'days')::int)) else created_at end,
        bot_cfg = coalesce(bot_cfg, '{}'::jsonb) || (cfg - 'hours' - 'coins' - 'keys' - 'streak' - 'days' - 'badges' - 'level'
                                                         - 'look' - 'stats')
                  || case when cfg ? 'stats' then jsonb_build_object('stats', coalesce(bot_cfg -> 'stats', '{}'::jsonb) || st)
                          else '{}'::jsonb end,
        last_beat = coalesce(last_beat, now() - make_interval(mins => (30 + random() * 2000)::int)),
        bot_at = now()
     where id = p.id;
    if cfg ? 'level' then
        lv := least(100, greatest(0, (cfg ->> 'level')::int));
        update public.profiles set level = lv,
               xp = public.rb_xp_total(lv) + case when lv >= 100 then 0
                    else floor(random() * 0.8 * (public.rb_xp_total(lv + 1) - public.rb_xp_total(lv)))::bigint end
         where id = p.id;
    end if;
    if cfg ->> 'look' = 'random' then
        perform public.rb_bot_look(p.id);
    end if;
    if cfg ? 'force' then
        update public.profiles set last_beat = case when cfg ->> 'force' = 'on' then now()
                                                     when cfg ->> 'force' = 'off' then now() - make_interval(mins => (5 + random() * 90)::int)
                                                     else last_beat end,
               bot_at = now()
         where id = p.id;
        if jsonb_typeof(cfg -> 'force') = 'null' then
            update public.profiles set bot_cfg = bot_cfg - 'force' where id = p.id;
        end if;
    end if;
    want := least(60, greatest(0, coalesce((cfg ->> 'badges')::int, 0)));
    select count(*) into have from public.rb_items it where it.owner = p.id and it.item like 'badge:%';
    for i in 1 .. greatest(0, want - have) loop
        t := public.rb_roll(array[0, 7800, 1900, 270, 30]);
        k := (array[0, 1, 2])[public.rb_roll(array[7600, 2350, 50]) + 1];
        perform public.rb_give(p.id, public.rb_pick_badge(t, k), 'case:standard');
    end loop;
    insert into public.rb_seen (owner, item) select owner, item from public.rb_items where owner = p.id on conflict do nothing;
    select array_agg(y.item order by y.value desc) into best from (select distinct it.item, c.value from public.rb_items it
              join public.rb_catalog c on c.id = it.item where it.owner = p.id and c.kind = 'badge') y;
    if best is not null and not coalesce(p.equip ? 'badge1', false) then
        update public.profiles set equip = equip || jsonb_strip_nulls(jsonb_build_object('badge1', best[1], 'badge2', best[2],
                                                                                          'badge3', best[3]))
         where id = p.id;
    end if;
    perform public.rb_log('bot', p.username, cfg);
    return json_build_object('ok', true, 'badges', greatest(have, want));
end $$;

create or replace function public.rb_admin_bots() returns json
    language plpgsql stable security definer set search_path = '' as $$
declare me uuid := public.rb_need_admin();
begin
    return coalesce((select json_agg(json_build_object('username', p.username, 'online', public.rb_online(p),
            'minutes', p.minutes, 'coins', p.coins, 'keys', p.keys, 'streak', p.streak, 'since', p.created_at,
            'cfg', coalesce(p.bot_cfg, '{}'::jsonb), 'level', p.level, 'seen', p.last_beat, 'equip', p.equip,
            'stats', public.rb_stats(p.id),
            'badges', (select count(*) from public.rb_items it where it.owner = p.id and it.item like 'badge:%'))
            order by p.username) from public.profiles p where p.bot), '[]'::json);
end $$;

revoke all on function public.rb_stats_real(uuid) from public, anon, authenticated;
revoke all on function public.rb_bot_look(uuid) from public, anon, authenticated;
update public.profiles set last_beat = now() - make_interval(mins => (60 + random() * 3000)::int) where bot and last_beat is null;
