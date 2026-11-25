-- Rubenium 9.0 (Remastered), server part. Safe to run twice. Undo: 076_down.sql.
--
-- 1. Wealth tiers: every free reward (free spin, scratch card, daily reward, quests, mini games, AFK coins, the Golden
--    Wheel) is multiplied by the player's tier, worked out from everything they own (coins + the worth of their items).
--    Rookie x1, Bronze x1.25 (5 000), Silver x1.6 (25 000), Gold x2.2 (100 000), Platinum x3 (500 000), Diamond x4
--    (2 000 000). All in rb_config (tier_at_N, tier_x_N).
-- 2. Rewards remade: free spin every hour (was 2 h), scratch card every 4 h (was 12 h), new prize tables, quests now pay
--    coins too, AFK 30 coins every 10 minutes.
-- 3. Keys remade: 1 key every 20 minutes of play (was 30), earning stops at 10; the Key Forge makes a key from coins
--    (1% of your wealth, at least 500 coins, 5 a day).
-- 4. Daily limits on what free games pay (the 8.0 skill-game limits, folded in and scaled by tier): each mini game
--    3 000 x tier a day; Cups 60 000 and Connect 4 20 000 profit a day.
-- 5. Shop tax 15% (was 33%).
-- 6. The player market is closed: every market call answers rb_feature_gone (nothing is listed on the live server).
-- 7. Automatic cheat detection is removed: no more flags, no more automatic game locks; old automatic locks are lifted.
-- 8. More rigs for the admin: Plinko (the box), Roulette (the pocket) and Rocket (the crash point).
begin;

-- ---------------------------------------------------------------- 1. settings
insert into public.rb_config (key, value) values
    ('tier_at_1', 5000), ('tier_at_2', 25000), ('tier_at_3', 100000), ('tier_at_4', 500000), ('tier_at_5', 2000000),
    ('tier_x_0', 1.0), ('tier_x_1', 1.25), ('tier_x_2', 1.6), ('tier_x_3', 2.2), ('tier_x_4', 3.0), ('tier_x_5', 4.0),
    ('forge_pct', 0.01), ('forge_min', 500), ('forge_day', 5),
    ('market_on', 0), ('flags_on', 0), ('remaster_90', 1)
on conflict (key) do nothing;
update public.rb_config set value = v.value from (values
    ('spin_hours', 1), ('scratch_hours', 4), ('coin_amount', 30), ('coin_every_min', 10), ('coin_day_cap', 2400),
    ('key_every_min', 20), ('key_cap', 10), ('shop_tax', 0.15), ('start_coins', 1000), ('start_keys', 3),
    ('gold_wheel_pct', 4), ('game_day_cap', 3000), ('cups_day_profit', 60000), ('c4_day_profit', 20000)
) as v(key, value) where rb_config.key = v.key and coalesce((select value from public.rb_config where key = 'remaster_90_set'), 0) = 0;
insert into public.rb_config (key, value) values ('remaster_90_set', 1) on conflict (key) do nothing;

-- ---------------------------------------------------------------- 2. tiers
create or replace function public.rb_tier(who uuid) returns jsonb
language plpgsql stable security definer set search_path to '' as $$
declare w bigint := public.rb_wealth(who); t integer := 0; i integer; nxt numeric;
begin
    for i in 1 .. 5 loop
        if w >= coalesce(public.rb_cfg('tier_at_' || i), 1e18) then t := i; end if;
    end loop;
    nxt := case when t < 5 then public.rb_cfg('tier_at_' || (t + 1)) end;
    return jsonb_build_object('tier', t, 'name', (array['Rookie', 'Bronze', 'Silver', 'Gold', 'Platinum', 'Diamond'])[t + 1],
                              'mult', coalesce(public.rb_cfg('tier_x_' || t), 1), 'wealth', w, 'next', nxt);
end $$;

create or replace function public.rb_tier_mult(who uuid) returns numeric
language sql stable security definer set search_path to '' as $$
    select coalesce((public.rb_tier(who) ->> 'mult')::numeric, 1) $$;

-- a reward in coins, multiplied by the tier and rounded to 10 (5 under 100)
create or replace function public.rb_scaled(n integer, m numeric) returns integer
language sql immutable set search_path to '' as $$
    select case when n is null or n <= 0 then coalesce(n, 0)
                when n * m < 100 then (round(n * m / 5) * 5)::int
                else (round(n * m / 10) * 10)::int end $$;

create or replace function public.rb_my_tier() returns jsonb
language plpgsql stable security definer set search_path to '' as $$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    return public.rb_tier(auth.uid()) || jsonb_build_object('forge', public.rb_forge_state(auth.uid()));
end $$;

-- ---------------------------------------------------------------- 3. the Key Forge
create or replace function public.rb_forge_state(who uuid) returns jsonb
language sql stable security definer set search_path to '' as $$
    select jsonb_build_object(
        'price', greatest(coalesce(public.rb_cfg('forge_min'), 500)::bigint,
                          (round(public.rb_wealth(who) * coalesce(public.rb_cfg('forge_pct'), 0.01) / 10) * 10)::bigint),
        'left', greatest(0, coalesce(public.rb_cfg('forge_day'), 5)::int - (select count(*)::int from public.rb_ledger l
              where l.owner = who and l.reason = 'forge' and l.at >= (public.rb_today()::timestamp at time zone 'Europe/Paris')))) $$;

create or replace function public.rb_key_forge() returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; f jsonb; price integer;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('shop');
    f := public.rb_forge_state(p.id);
    if (f ->> 'left')::int < 1 then raise exception 'rb_too_many'; end if;
    price := least((f ->> 'price')::bigint, 2000000000)::int;
    if p.coins < price then raise exception 'rb_not_enough'; end if;
    perform public.rb_pay(p.id, -price, 1, 'forge', price::text);
    return jsonb_build_object('coins', p.coins - price, 'keys', p.keys + 1, 'paid', price,
                              'forge', public.rb_forge_state(p.id));
end $$;

-- ---------------------------------------------------------------- 4. free spin (hourly, scaled)
create or replace function public.rb_spin_table(m numeric) returns jsonb
language sql immutable set search_path to '' as $$
    select jsonb_build_object(
        'slots', jsonb_build_array(public.rb_scaled(100, m), public.rb_scaled(150, m), public.rb_scaled(250, m),
                                   public.rb_scaled(400, m), public.rb_scaled(600, m), public.rb_scaled(1000, m),
                                   public.rb_scaled(2000, m), -1, -2, -3),
        'odds', jsonb_build_array(1800, 1800, 1700, 1300, 900, 600, 300, 800, 400, 400)) $$;

create or replace function public.rb_spin_odds() returns json
language plpgsql stable security definer set search_path to '' as $$
begin
    return public.rb_spin_table(case when auth.uid() is null then 1 else public.rb_tier_mult(auth.uid()) end)::json;
end $$;

create or replace function public.rb_spin() returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; r integer; prize jsonb; q public.profiles%rowtype; t jsonb; slots integer[]; odds integer[];
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('wheel');
    if p.spin_prize is not null then perform public.rb_spin_pay(p, p.spin_prize); end if;     -- a prize from an old app: paid now
    if p.spin_at is not null and now() < p.spin_at + make_interval(hours => public.rb_cfg('spin_hours')::int) then
        raise exception 'rb_too_soon';
    end if;
    t := public.rb_spin_table(public.rb_tier_mult(p.id));
    select array_agg(x::int order by n) into slots from jsonb_array_elements_text(t -> 'slots') with ordinality a(x, n);
    select array_agg(x::int order by n) into odds from jsonb_array_elements_text(t -> 'odds') with ordinality a(x, n);
    r := case when p.rig_gold then 8 else public.rb_roll(odds) end;
    r := coalesce(least(9, greatest(0, (public.rb_rig_take(p.id, 'wheel', '') ->> 'slot')::int)), r);
    if p.rig_gold then update public.profiles set rig_gold = false where id = p.id; end if;
    prize := jsonb_build_object('slot', r, 'won', greatest(slots[r + 1], 0), 'won_keys', case when slots[r + 1] = -1 then 1 else 0 end,
                                'gold', slots[r + 1] = -2,
                                'coupon', case when slots[r + 1] = -3 then public.rb_coupon_pick(array[6500, 2700, 700, 100]) end);
    update public.profiles set spin_at = now() where id = p.id;
    perform public.rb_spin_pay(p, prize);
    select * into q from public.profiles where id = p.id;
    return prize || jsonb_build_object('collected', true, 'coins', q.coins, 'keys', q.keys, 'gold_wheels', q.gold_wheels,
                                       'slots', t -> 'slots');
end $$;

-- ---------------------------------------------------------------- 5. scratch card (every 4 h, scaled)
create or replace function public.rb_scratch() returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; roll double precision; tier text; c integer := 0; k integer := 0; g integer := 0; cp text;
        m numeric;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('scratch');
    if p.scratch_at is not null and now() < p.scratch_at + make_interval(hours => public.rb_cfg('scratch_hours')::int) then
        raise exception 'rb_wait';
    end if;
    m := public.rb_tier_mult(p.id);
    roll := case when p.rig_gold then 0.999 else public.rb_rand() end;
    roll := coalesce(case public.rb_rig_take(p.id, 'scratch', '') ->> 'tier' when 'standard' then 0.15 when 'rare' then 0.45
                          when 'special' then 0.65 when 'epic' then 0.85 when 'exotic' then 0.94 when 'golden' then 0.99 end, roll);
    if p.rig_gold then update public.profiles set rig_gold = false where id = p.id; end if;
    if roll < 0.30 then tier := 'standard'; c := public.rb_scaled(150 + floor(public.rb_rand() * 151)::int, m);
    elsif roll < 0.57 then tier := 'rare'; c := public.rb_scaled(400 + floor(public.rb_rand() * 301)::int, m);
    elsif roll < 0.77 then tier := 'special'; k := 1; c := public.rb_scaled(200, m); cp := 'coupon:common';
    elsif roll < 0.91 then tier := 'epic'; k := 2; cp := 'coupon:uncommon';
    elsif roll < 0.97 then tier := 'exotic'; c := public.rb_scaled(3000, m); cp := 'coupon:rare';
    else tier := 'golden'; g := 1; cp := 'coupon:epic'; end if;
    update public.profiles set scratch_at = now(), gold_wheels = gold_wheels + g where id = p.id;
    perform public.rb_pay(p.id, c, k, 'scratch', tier);
    if cp is not null then perform public.rb_give(p.id, cp, 'scratch'); end if;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        values (p.id, 'scratch', 0, jsonb_build_object('tier', tier, 'keys', k, 'coupon', cp), false, c);
    return jsonb_build_object('rarity', tier, 'coins_won', c, 'keys_won', k, 'coins', p.coins + c, 'keys', p.keys + k,
                              'gold_wheel', g = 1, 'coupon', cp, 'next', public.rb_cfg('scratch_hours')::int * 3600,
                              'mult', m);
end $$;

-- ---------------------------------------------------------------- 6. daily reward (scaled)
create or replace function public.rb_login_rewards() returns jsonb
language sql immutable set search_path to '' as $$
    select '[{"coins":150},{"coins":250},{"keys":1},{"coins":400},{"keys":2},{"coins":750},{"coins":1500,"keys":1,"case":"premium"}]'::jsonb $$;

create or replace function public.rb_login_rewards_for(m numeric) returns jsonb
language sql immutable set search_path to '' as $$
    select jsonb_agg(case when r ? 'coins' then r || jsonb_build_object('coins', public.rb_scaled((r ->> 'coins')::int, m)) else r end
                     order by n)
      from jsonb_array_elements(public.rb_login_rewards()) with ordinality a(r, n) $$;

create or replace function public.rb_login_state() returns json
language plpgsql stable security definer set search_path to '' as $$
declare p public.profiles%rowtype; s integer;
begin
    select * into p from public.profiles where id = auth.uid();
    if not found then raise exception 'rb_not_logged_in'; end if;
    s := case when p.streak_day = public.rb_today() then p.streak
              when p.streak_day = public.rb_today() - 1 then p.streak else 0 end;
    return json_build_object('streak', s, 'claimed', p.streak_day = public.rb_today(),
                             'day', case when p.streak_day = public.rb_today() then (s - 1) % 7 else s % 7 end,
                             'rewards', public.rb_login_rewards_for(public.rb_tier_mult(p.id)));
end $$;

create or replace function public.rb_login_claim() returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; s integer; r jsonb; c integer; k integer;
begin
    perform public.rb_need_feature('quests');
    p := public.rb_lock_me();
    if p.streak_day = public.rb_today() then raise exception 'rb_wait'; end if;
    s := case when p.streak_day = public.rb_today() - 1 then p.streak + 1 else 1 end;
    r := public.rb_login_rewards_for(public.rb_tier_mult(p.id)) -> ((s - 1) % 7);
    c := coalesce((r ->> 'coins')::int, 0); k := coalesce((r ->> 'keys')::int, 0);
    update public.profiles set streak = s, streak_day = public.rb_today() where id = p.id;
    perform public.rb_pay(p.id, c, k, 'login', s::text);
    if r ? 'case' then perform public.rb_stock_add(p.id, r ->> 'case', 1); end if;
    return jsonb_build_object('streak', s, 'reward', r, 'coins', p.coins + c, 'keys', p.keys + k);
end $$;

-- ---------------------------------------------------------------- 7. quests pay coins too (scaled)
create or replace function public.rb_quest_claim(which text) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; q record; prize jsonb; k integer; c integer;
begin
    perform public.rb_need_feature('quests');
    p := public.rb_lock_me();
    select * into q from public.rb_quest_rows(p.id) x where x.quest = which;
    if not found then raise exception 'rb_no_quest'; end if;
    if q.progress < q.goal then raise exception 'rb_not_done'; end if;
    begin
        insert into public.rb_quest_claims (owner, quest, period) values (p.id, q.quest, q.period);
    exception when unique_violation then
        raise exception 'rb_already_claimed';
    end;
    prize := public.rb_quest_prize(q.reward);
    k := (prize ->> 'keys')::int;
    c := public.rb_scaled(q.reward, public.rb_tier_mult(p.id));
    perform public.rb_pay(p.id, c, k, 'quest', q.quest);
    if prize ->> 'case' is not null then
        perform public.rb_stock_add(p.id, prize ->> 'case', 1);
    end if;
    return jsonb_build_object('paid', c, 'coins', p.coins + c, 'won_keys', k, 'keys', p.keys + k, 'key_found', true,
                              'case', prize ->> 'case');
end $$;

-- ---------------------------------------------------------------- 8. mini games: scaled pay, scaled daily limit
create or replace function public.rb_game_pay(who uuid, g text, pay integer) returns integer
language plpgsql security definer set search_path to '' as $$
declare w json := public.rb_game_window(who, g); n integer := (w ->> 'rounds')::int; fr integer := (w ->> 'full')::int;
        m numeric := public.rb_level_mult(who) * public.rb_tier_mult(who); got integer;
begin
    pay := round(pay * coalesce(public.rb_cfg('game_pay_mult'), 1) * m);
    if n >= fr * 2 then pay := pay / 4; elsif n >= fr then pay := pay / 2; end if;
    got := greatest(0, least(pay, floor((w ->> 'cap')::int * m)::int - (w ->> 'paid')::int));
    if got > 0 then perform public.rb_key_find(who, g); end if;
    return got;
end $$;

-- ---------------------------------------------------------------- 9. AFK coins (scaled) and keys every 20 minutes
create or replace function public.rb_heartbeat(device text) returns json
language plpgsql security definer set search_path to '' as $$
declare
    p public.profiles%rowtype;
    credited boolean := false; elsewhere boolean := false;
    got_coins integer := 0; got_keys integer := 0; m numeric;
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_bots_tick(); perform public.rb_flip_cleanup(auth.uid());
    update public.profiles set bot_real_at = now() where id = auth.uid() and bot;
    select * into p from public.profiles where id = auth.uid() for update;
    if not found then raise exception 'rb_no_profile'; end if;
    if p.banned then raise exception 'rb_banned'; end if;
    device := left(coalesce(device, ''), 64);
    if p.last_beat is not null and p.beat_device is distinct from device
       and now() - p.last_beat < interval '150 seconds' then
        elsewhere := true;
    elsif p.last_beat is null or now() - p.last_beat >= interval '55 seconds' then
        credited := p.last_beat is not null and now() - p.last_beat < interval '150 seconds';
        if credited then
            p.minutes := p.minutes + 1; if p.minutes % 10 = 0 then perform public.rb_xp_add(p.id, 5, 'online', null, true); end if; perform public.rb_wear_add(p.id, p.equip ->> 'banner'); p.coin_min := p.coin_min + 1; p.key_min := p.key_min + 1;
            if p.day <> current_date then p.day := current_date; p.day_coins := 0; end if;
            if p.coin_min >= public.rb_cfg('coin_every_min') then
                p.coin_min := 0;
                m := public.rb_tier_mult(p.id);
                if p.day_coins < (public.rb_cfg('coin_day_cap') + public.rb_streak_bonus(p) * 72) * m then
                    got_coins := public.rb_scaled(public.rb_cfg('coin_amount')::int + public.rb_streak_bonus(p), m);
                    p.day_coins := p.day_coins + got_coins;
                end if;
            end if;
            if p.key_min >= public.rb_cfg('key_every_min') then
                p.key_min := 0;
                if p.keys < public.rb_cfg('key_cap') then got_keys := 1; end if;
            end if;
        end if;
        update public.profiles set minutes = p.minutes, coin_min = p.coin_min, key_min = p.key_min, day = p.day,
               day_coins = p.day_coins, last_beat = now(), beat_device = device where id = p.id;
        perform public.rb_pay(p.id, got_coins, got_keys, 'time', null);
    end if;
    return json_build_object('username', p.username, 'minutes', p.minutes, 'credited', credited,
                             'elsewhere', elsewhere, 'coins', p.coins + got_coins, 'keys', p.keys + got_keys,
                             'got_coins', got_coins, 'got_keys', got_keys, 'coin_min', p.coin_min, 'key_min', p.key_min,
                             'day_coins', p.day_coins);
end $$;

-- ---------------------------------------------------------------- 10. Golden Wheel (re-tuned for hourly spins, scaled)
create or replace function public.rb_gold_wheel() returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; r integer;
        prizes text[] := array['2500', 'shiny', '5000', 'premium', '10000', 'mythic', '25000', 'royal', '75000'];
        odds integer[] := array[26, 14, 20, 10, 12, 8, 4, 5, 1];
        what text; c integer := 0;
begin
    perform public.rb_need_feature('wheel');
    p := public.rb_lock_me();
    if p.gold_wheels < 1 then raise exception 'rb_nothing_to_collect'; end if;
    r := public.rb_roll(odds);
    what := prizes[r + 1];
    update public.profiles set gold_wheels = gold_wheels - 1 where id = p.id;
    if what ~ '^[0-9]+$' then
        c := public.rb_scaled(what::int, public.rb_tier_mult(p.id));
        perform public.rb_pay(p.id, c, 0, 'gold_wheel', what);
    else
        perform public.rb_stock_add(p.id, what, 1);
        perform public.rb_pay(p.id, 0, 1, 'gold_wheel', what);
    end if;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'gold_wheel', 0, jsonb_build_object('prize', what), false, c);
    return jsonb_build_object('slot', r, 'prize', what, 'coins_won', c, 'case', case when c = 0 then what end,
                              'coins', p.coins + c, 'keys', p.keys + case when c = 0 then 1 else 0 end, 'left', p.gold_wheels - 1);
end $$;

-- ---------------------------------------------------------------- 11. the player market is closed
do $$
declare f record;
begin
    for f in select p.oid, p.proname, pg_get_function_identity_arguments(p.oid) args, pg_get_function_result(p.oid) res
               from pg_proc p where p.pronamespace = 'public'::regnamespace
                and p.proname in ('rb_market_list', 'rb_market_buy', 'rb_market_offer', 'rb_market_answer',
                                  'rb_market_search', 'rb_market_browse', 'rb_market_price', 'rb_market_mine',
                                  'rb_market_offers', 'rb_market_cancel', 'rb_market_unoffer')
    loop
        execute format('create or replace function public.%I(%s) returns %s language plpgsql security definer '
                       'set search_path to '''' as $f$ begin raise exception ''rb_feature_gone''; end $f$',
                       f.proname, f.args, f.res);
    end loop;
end $$;
update public.rb_items set locked = null where locked like 'market:%';
delete from public.rb_offers where listing in (select id from public.rb_listings where state = 'open');
delete from public.rb_listings where state = 'open';

-- ---------------------------------------------------------------- 12. no automatic cheat detection
drop trigger if exists rb_rounds_scan on public.rb_rounds;
create or replace function public.rb_flag(who uuid, g text, k text, sev integer, det jsonb, lock_h integer default 0) returns void
language plpgsql security definer set search_path to '' as $$
begin
    return;                                   -- 9.0: nothing is flagged or locked automatically any more
end $$;
delete from public.rb_game_locks where reason is distinct from 'admin';
update public.rb_flags set reviewed = true where not reviewed;

-- ---------------------------------------------------------------- 13. more rigs: Plinko, Roulette, Rocket
create or replace function public.rb_admin_rig(name text, kind text, key text, data jsonb) returns boolean
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; me text;
begin
    perform public.rb_need_admin();
    select * into p from public.profiles where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    if kind not in ('wheel', 'scratch', 'case', 'slots', 'dice', 'flip', 'plinko', 'roulette', 'rocket') then
        raise exception 'rb_bad_choice';
    end if;
    key := case when kind = 'case' then coalesce(key, '') else '' end;
    if kind = 'case' and not exists (select 1 from public.rb_cases where id = key) then raise exception 'rb_no_case'; end if;
    if data is not null then
        if kind = 'wheel' and coalesce((data ->> 'slot')::int, -1) not between 0 and 9 then raise exception 'rb_bad_choice'; end if;
        if kind = 'scratch' and coalesce(data ->> 'tier', '') not in ('standard', 'rare', 'special', 'epic', 'exotic', 'golden') then
            raise exception 'rb_bad_choice';
        end if;
        if kind = 'case' and not ((data ? 'item' and exists (select 1 from public.rb_catalog where id = data ->> 'item'))
                                  or (data ? 'coins' and (data ->> 'coins')::int between 0 and 10000000)) then
            raise exception 'rb_bad_choice';
        end if;
        if kind = 'slots' and (jsonb_array_length(coalesce(data -> 'reels', '[]'::jsonb)) <> 3 or exists (
               select 1 from jsonb_array_elements_text(data -> 'reels') r where r not in ('cherry', 'lemon', 'bell', 'seven', 'gem'))) then
            raise exception 'rb_bad_choice';
        end if;
        if kind in ('dice', 'flip') and jsonb_typeof(data -> 'win') <> 'boolean' then raise exception 'rb_bad_choice'; end if;
        if kind = 'plinko' and coalesce((data ->> 'box')::int, -1) not between 0 and 10 then raise exception 'rb_bad_choice'; end if;
        if kind = 'roulette' and coalesce((data ->> 'slot')::int, -1) not between 0 and 24 then raise exception 'rb_bad_choice'; end if;
        if kind = 'rocket' and coalesce((data ->> 'crash')::numeric, 0) not between 1 and 100 then raise exception 'rb_bad_choice'; end if;
    end if;
    select username into me from public.profiles where id = auth.uid();
    delete from public.rb_rigs r where r.owner = p.id and r.kind = rb_admin_rig.kind and r.key = rb_admin_rig.key;
    if data is not null then
        insert into public.rb_rigs (owner, kind, key, data, by_name) values (p.id, rb_admin_rig.kind, rb_admin_rig.key, data, me);
    end if;
    perform public.rb_log(case when data is null then 'rig_clear' else 'rig' end, p.username,
                          jsonb_build_object('kind', kind, 'key', key, 'data', data));
    return true;
end $$;

create or replace function public.rb_plinko(bet integer, risk integer, req text) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; res jsonb; path integer[] := '{}'; box integer := 0; i integer; d integer;
        mult numeric; pay integer; want integer; rest integer;
        tables numeric[][] := array[[8.5, 3, 1.4, 1.1, 0.95, 0.5, 0.95, 1.1, 1.4, 3, 8.5],
                                    [21, 5, 2, 1.3, 0.6, 0.4, 0.6, 1.3, 2, 5, 21],
                                    [70, 9, 3, 0.9, 0.3, 0.2, 0.3, 0.9, 3, 9, 70]];
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if risk is null or risk < 0 or risk > 2 then raise exception 'rb_bad_choice'; end if;
    perform public.rb_bet(p, bet, 'plinko');
    want := (public.rb_rig_take(p.id, 'plinko', '') ->> 'box')::int;            -- 9.0 rig: the box it lands in
    for i in 1 .. 10 loop
        if want is not null then
            rest := want - box;                                                 -- rights still needed
            d := case when rest >= 11 - i then 1 when rest <= 0 then 0 when public.rb_rand() < rest::numeric / (11 - i) then 1 else 0 end;
        else
            d := case when public.rb_rand() < 0.5 then 0 else 1 end;
        end if;
        path := path || d; box := box + d;
    end loop;
    mult := tables[risk + 1][box + 1];
    pay := public.rb_win(p.id, bet * mult, 'plinko');
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'plinko', bet, '{}'::jsonb, false, pay);
    return public.rb_remember(p.id, req, jsonb_build_object('path', to_jsonb(path), 'box', box, 'mult', mult,
                                                            'paid', pay, 'coins', p.coins - bet + pay));
end $$;

create or replace function public.rb_roulette_multi(bet integer, picks text[], req text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; res jsonb; slot integer; colour text; pay bigint := 0; x text; num integer;
        n integer; wins jsonb := '[]'::jsonb; m integer; total integer;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    perform public.rb_need_feature('roulette');
    n := coalesce(array_length(picks, 1), 0);
    if n < 1 or n > 6 or (select count(distinct v) from unnest(picks) v) <> n then raise exception 'rb_bad_choice'; end if;
    -- 5.15: no opposite bets (red with black, low with high): you can't cover the whole table
    if ('red' = any (picks) and 'black' = any (picks)) or ('low' = any (picks) and 'high' = any (picks)) then
        raise exception 'rb_roulette_opposite';
    end if;
    foreach x in array picks loop
        if x ~ '^n:[0-9]{1,2}$' then
            if substr(x, 3)::int not between 1 and 24 then raise exception 'rb_bad_choice'; end if;
        elsif x not in ('red', 'black', 'gold', 'low', 'high') then
            raise exception 'rb_bad_choice';
        end if;
    end loop;
    if bet is null or bet < public.rb_cfg('bet_min') then raise exception 'rb_bad_bet'; end if;
    total := bet * n;
    perform public.rb_bet(p, total, 'roulette');
    slot := floor(public.rb_rand() * 25)::int;
    slot := coalesce(least(24, greatest(0, (public.rb_rig_take(p.id, 'roulette', '') ->> 'slot')::int)), slot);   -- 9.0 rig
    colour := case when slot = 0 then 'gold' when slot % 2 = 1 then 'red' else 'black' end;
    foreach x in array picks loop
        num := case when x like 'n:%' then substr(x, 3)::int end;
        m := case when num is not null and slot = num then 24
                  when x = 'gold' and slot = 0 then 25
                  when x = 'low' and slot between 1 and 12 then 2
                  when x = 'high' and slot between 13 and 24 then 2
                  when x in ('red', 'black') and colour = x then 2
                  else 0 end;
        if m > 0 then
            pay := pay + bet::bigint * m;
            wins := wins || to_jsonb(x);
        end if;
    end loop;
    if pay > 0 then pay := public.rb_win(p.id, pay, 'roulette'); end if;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        values (p.id, 'roulette', total, jsonb_build_object('slot', slot, 'picks', to_jsonb(picks)), false, pay);
    return public.rb_remember(p.id, req, jsonb_build_object('slot', slot, 'colour', colour, 'win', pay > 0, 'wins', wins,
                                                            'paid', pay, 'coins', p.coins - total + pay));
end $function$;

create or replace function public.rb_rocket(action text, bet integer, target numeric) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; r public.rb_rounds%rowtype; crash numeric; now_mult numeric; pay integer := 0;
        u double precision; aim numeric; past jsonb; ended jsonb;
begin
    perform public.rb_need_feature('casino');
    p := public.rb_lock_me();
    select * into r from public.rb_rounds where owner = p.id and game = 'rocket' and open for update;
    if found then
        crash := (r.secret ->> 'crash')::numeric;
        aim := (r.secret ->> 'target')::numeric;
        now_mult := floor(exp(0.10 * extract(epoch from (clock_timestamp() - r.at))) * 100) / 100;
        if aim is not null and crash >= aim and now_mult >= aim then
            pay := public.rb_win(p.id, r.bet * aim, 'rocket');
            update public.rb_rounds set open = false, paid = pay where id = r.id;
            ended := jsonb_build_object('open', false, 'crashed', false, 'auto', true, 'mult', aim, 'crash', crash,
                                        'paid', pay, 'coins', p.coins + pay);
        elsif now_mult >= crash then
            update public.rb_rounds set open = false where id = r.id;
            ended := jsonb_build_object('open', false, 'crashed', true, 'crash', crash, 'paid', 0, 'coins', p.coins);
        elsif action = 'cash' then
            if now_mult < public.rb_cfg('rocket_min') then raise exception 'rb_too_early'; end if;
            pay := public.rb_win(p.id, r.bet * now_mult, 'rocket');
            update public.rb_rounds set open = false, paid = pay where id = r.id;
            ended := jsonb_build_object('open', false, 'crashed', false, 'mult', now_mult, 'crash', crash, 'paid', pay,
                                        'coins', p.coins + pay);
        elsif action = 'look' then
            return jsonb_build_object('open', true, 'mult', now_mult, 'bet', r.bet, 'target', aim,
                                      'age', extract(epoch from (clock_timestamp() - r.at)));
        else
            raise exception 'rb_round_open';
        end if;
    end if;
    select coalesce(jsonb_agg(x.c), '[]'::jsonb) into past from (
        select (secret ->> 'crash')::numeric as c from public.rb_rounds
         where owner = p.id and game = 'rocket' and not open order by at desc limit 10) x;
    if ended is not null and action <> 'start' then return ended || jsonb_build_object('history', past); end if;
    if action <> 'start' then return jsonb_build_object('open', false, 'history', past); end if;
    if target is not null and (target < public.rb_cfg('rocket_min') or target > 100) then raise exception 'rb_bad_choice'; end if;
    perform public.rb_bet(p, bet, 'rocket');
    u := public.rb_rand();
    crash := greatest(1.00, least(100, floor(96 / (1 - u)) / 100));
    crash := coalesce(least(100, greatest(1, (public.rb_rig_take(p.id, 'rocket', '') ->> 'crash')::numeric)), crash);   -- 9.0 rig
    insert into public.rb_rounds (owner, game, bet, secret)
        values (p.id, 'rocket', bet, jsonb_build_object('crash', crash, 'target', target));
    return jsonb_build_object('open', true, 'mult', 1, 'bet', bet, 'age', 0, 'target', target, 'history', past,
                              'coins', p.coins + pay - bet);
end $$;

-- ---------------------------------------------------------------- 14. admin: set a balance, give to everyone
create or replace function public.rb_admin_set_balance(name text, new_coins integer, new_keys integer) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; dc integer; dk integer;
begin
    perform public.rb_need_admin();
    select * into p from public.profiles where lower(username) = lower(name) for update;
    if not found then raise exception 'rb_no_such_user'; end if;
    dc := coalesce(greatest(0, new_coins), p.coins) - p.coins;
    dk := coalesce(greatest(0, new_keys), p.keys) - p.keys;
    perform public.rb_pay(p.id, dc, dk, 'admin', 'set');
    perform public.rb_log('set_balance', p.username, jsonb_build_object('coins', dc, 'keys', dk, 'uid', p.id));
    return jsonb_build_object('coins', p.coins + dc, 'keys', p.keys + dk);
end $$;

create or replace function public.rb_admin_grant_all(add_coins integer, add_keys integer) returns integer
language plpgsql security definer set search_path to '' as $$
declare n integer := 0; r record;
begin
    perform public.rb_need_admin();
    if coalesce(add_coins, 0) < 0 or coalesce(add_keys, 0) < 0 or coalesce(add_coins, 0) > 10000000 or coalesce(add_keys, 0) > 1000 then
        raise exception 'rb_bad_choice';
    end if;
    for r in select id from public.profiles where not coalesce(bot, false) and not banned loop
        perform public.rb_pay(r.id, coalesce(add_coins, 0), coalesce(add_keys, 0), 'admin', 'everyone');
        perform public.rb_notice(r.id, 'admin', jsonb_build_object('coins', coalesce(add_coins, 0), 'keys', coalesce(add_keys, 0)));
        n := n + 1;
    end loop;
    perform public.rb_log('grant_all', 'everyone', jsonb_build_object('coins', add_coins, 'keys', add_keys, 'n', n));
    return n;
end $$;

-- who may call what (players: their own calls; the admin functions check rb_need_admin themselves)
revoke all on function public.rb_tier(uuid), public.rb_tier_mult(uuid), public.rb_forge_state(uuid),
    public.rb_scaled(integer, numeric), public.rb_spin_table(numeric), public.rb_login_rewards_for(numeric) from public, anon, authenticated;
grant execute on function public.rb_my_tier(), public.rb_key_forge(), public.rb_admin_set_balance(text, integer, integer),
    public.rb_admin_grant_all(integer, integer) to authenticated;
revoke all on function public.rb_my_tier(), public.rb_key_forge(), public.rb_admin_set_balance(text, integer, integer),
    public.rb_admin_grant_all(integer, integer) from public, anon;
grant execute on function public.rb_tier(uuid), public.rb_tier_mult(uuid), public.rb_forge_state(uuid),
    public.rb_scaled(integer, numeric), public.rb_spin_table(numeric), public.rb_login_rewards_for(numeric) to service_role;

commit;
