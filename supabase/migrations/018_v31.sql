-- Rubenium 018 (3.1): AFK coins grow with your login streak, new quests (2 hourly, 4 daily, 6 weekly), bigger set
-- bonuses, a better daily login, the Golden Wheel (5% from the free spin or the scratch card), Timing (a skill casino
-- game), 5 new cases, Titanium badges in the shop for rich players, a choice between normal and gold banners, and
-- admin tools for bots, the Golden Wheel and test resets.
-- Run it once in Supabase -> SQL Editor (after 017). Running it again changes nothing.

insert into public.rb_config (key, value) values
    ('coin_amount', 25), ('streak_coin', 5), ('streak_coin_days', 20), ('gold_wheel_pct', 5), ('timing_on', 1), ('quick_worth_share', 0.03)
on conflict (key) do update set value = excluded.value;

-- ================================================================ AFK coins: 25 every 10 minutes + 5 for every streak day
create or replace function public.rb_streak_bonus(p public.profiles) returns integer
language sql stable security definer set search_path = '' as $$
    select (coalesce(public.rb_cfg('streak_coin'), 0) * least(
               case when p.streak_day >= public.rb_today() - 1 then coalesce(p.streak, 0) else 0 end,
               coalesce(public.rb_cfg('streak_coin_days'), 20)))::int $$;

do $$ declare src text; begin
    select pg_get_functiondef('public.rb_heartbeat(text)'::regprocedure) into src;
    if position('rb_streak_bonus' in src) = 0 then
        src := replace(src, E'if p.day_coins < public.rb_cfg(''coin_day_cap'') then',
                            E'if p.day_coins < public.rb_cfg(''coin_day_cap'') + public.rb_streak_bonus(p) * 72 then');
        src := replace(src, E'got_coins := public.rb_cfg(''coin_amount'')::int;',
                            E'got_coins := public.rb_cfg(''coin_amount'')::int + public.rb_streak_bonus(p);');
        execute src;
    end if;
end $$;

-- ================================================================ quests: 2 hourly (easy), 4 daily, 6 weekly (long, well paid)
create or replace function public.rb_quest_rows(who uuid)
returns table (quest text, kind text, goal integer, reward integer, progress integer, period timestamptz, left_s integer)
language sql stable security definer set search_path = '' as $$
    with r as (select game, bet, paid, at from public.rb_rounds
                where owner = who and not open and at >= date_trunc('week', now())),
         d as (select * from r where at >= date_trunc('day', now())),
         h as (select * from r where at >= date_trunc('hour', now())),
         casino (g) as (values ('slots'), ('plinko'), ('dice'), ('mines'), ('rocket'), ('blackjack'), ('timing')),
         pool (quest, goal, reward, progress) as (values
            ('h_rounds', 3, 25, (select count(*) from h where game in (select g from casino))::int),
            ('h_mini',   1, 25, (select count(*) from h where game in ('mini', 'park', 'memory'))::int),
            ('h_case',   1, 30, (select count(*) from h where game like 'case:%' or game = 'daily')::int),
            ('h_bet',  100, 25, (select coalesce(sum(bet), 0) from h where game in (select g from casino))::int)),
         q (quest, kind, goal, reward, progress) as (
            select pq.quest, 'hour', pq.goal, pq.reward, pq.progress from pool pq
             where pq.quest in ((array['h_rounds', 'h_mini', 'h_case', 'h_bet'])[extract(hour from now())::int % 4 + 1],
                                (array['h_rounds', 'h_mini', 'h_case', 'h_bet'])[(extract(hour from now())::int + 2) % 4 + 1])
            union all values
            ('d_rounds', 'day', 15, 150, (select count(*) from d where game in (select g from casino))::int),
            ('d_case',   'day',  2, 150, (select count(*) from d where game like 'case:%' or game = 'daily')::int),
            ('d_mini',   'day',  3, 150, (select count(*) from d where game in ('mini', 'park', 'memory'))::int),
            ('d_spin',   'day',  1, 100, (select count(*) from d where game = 'spin')::int),
            ('w_rounds', 'week', 200, 1500, (select count(*) from r where game in (select g from casino))::int),
            ('w_cases',  'week',  25, 2000, (select count(*) from r where game like 'case:%')::int),
            ('w_won',    'week', 25000, 2000, (select coalesce(sum(paid), 0) from r where game in (select g from casino))::int),
            ('w_mini',   'week',  30, 1500, (select count(*) from r where game in ('mini', 'park', 'memory'))::int),
            ('w_golf',   'week',   3, 1500, (select count(*) from public.rb_golf g where g.winner = who and g.state = 'done'
                                               and g.done_at >= date_trunc('week', now()))::int),
            ('w_scratch','week',   7, 1200, (select count(*) from r where game = 'scratch')::int))
    select q.quest, q.kind, q.goal, q.reward, least(q.progress, q.goal), date_trunc(q.kind, now()),
           ceil(extract(epoch from (date_trunc(q.kind, now()) + ('1 ' || q.kind)::interval - now())))::int
      from q $$;

-- ================================================================ much bigger bonuses for the hardest sets
do $$ declare src text; begin
    select pg_get_functiondef('public.rb_set_rows(uuid)'::regprocedure) into src;
    if position('5000000' in src) = 0 then
        src := replace(src, '15000, 5)', '60000, 10)');                 -- 5 Shiny
        src := replace(src, '40000, 8)', '250000, 20)');                -- 3 Titanium
        src := replace(src, '25000, 10))', '500000, 25))');             -- a Gold badge
        src := replace(src, '50000, 10)', '150000, 20)');               -- every Legendary
        src := replace(src, '250000, 25)', '5000000, 100)');            -- the 6 Mythics
        execute src;
    end if;
end $$;

-- ================================================================ a better daily login
create or replace function public.rb_login_rewards() returns jsonb
language sql immutable as $$
    select '[{"coins":100},{"coins":150},{"keys":1},{"coins":250},{"keys":2},{"coins":500},{"coins":1000,"keys":1,"case":"premium"}]'::jsonb $$;

-- ================================================================ the Golden Wheel
alter table public.profiles add column if not exists gold_wheels integer not null default 0 check (gold_wheels >= 0);
alter table public.profiles add column if not exists rig_gold boolean not null default false;

-- the free spin: a 9th slice, GOLD (5%)
create or replace function public.rb_spin() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r integer; prize jsonb;
        slots integer[] := array[40, 75, 120, 180, 300, 500, 1200, -1, -2];       -- -1 = one key, -2 = the Golden Wheel
        odds  integer[] := array[2200, 2200, 1800, 1200, 750, 400, 180, 770, 500];
begin
    p := public.rb_lock_me();
    if p.spin_prize is not null then return p.spin_prize || jsonb_build_object('waiting', true); end if;
    if p.spin_at is not null and now() < p.spin_at + make_interval(hours => public.rb_cfg('spin_hours')::int) then
        raise exception 'rb_too_soon';
    end if;
    r := case when p.rig_gold then 8 else public.rb_roll(odds) end;
    if p.rig_gold then update public.profiles set rig_gold = false where id = p.id; end if;
    prize := jsonb_build_object('slot', r, 'won', greatest(slots[r + 1], 0), 'won_keys', case when slots[r + 1] = -1 then 1 else 0 end,
                                'gold', slots[r + 1] = -2);
    update public.profiles set spin_at = now(), spin_prize = prize where id = p.id;
    return prize;
end $$;

create or replace function public.rb_spin_collect() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; gold boolean;
begin
    p := public.rb_lock_me();
    if p.spin_prize is null then raise exception 'rb_nothing_to_collect'; end if;
    gold := coalesce((p.spin_prize ->> 'gold')::boolean, false);
    update public.profiles set spin_prize = null, gold_wheels = gold_wheels + case when gold then 1 else 0 end where id = p.id;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'spin', 0,
        jsonb_build_object('keys', (p.spin_prize ->> 'won_keys')::int, 'gold', gold), false, (p.spin_prize ->> 'won')::int);
    perform public.rb_pay(p.id, (p.spin_prize ->> 'won')::int, (p.spin_prize ->> 'won_keys')::int, 'spin', null);
    return jsonb_build_object('coins', p.coins + (p.spin_prize ->> 'won')::int,
                              'keys', p.keys + (p.spin_prize ->> 'won_keys')::int, 'gold_wheels', p.gold_wheels + case when gold then 1 else 0 end);
end $$;

-- the scratch card: 5% "golden" unlocks the Golden Wheel
create or replace function public.rb_scratch() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; roll double precision; tier text; c integer := 0; k integer := 0; g integer := 0;
begin
    p := public.rb_lock_me();
    if p.scratch_at is not null and now() < p.scratch_at + make_interval(hours => public.rb_cfg('scratch_hours')::int) then
        raise exception 'rb_wait';
    end if;
    roll := case when p.rig_gold then 0.999 else public.rb_rand() end;
    if p.rig_gold then update public.profiles set rig_gold = false where id = p.id; end if;
    if roll < 0.50 then tier := 'standard'; c := 60 + floor(public.rb_rand() * 61)::int;
    elsif roll < 0.77 then tier := 'rare'; c := 150 + floor(public.rb_rand() * 151)::int;
    elsif roll < 0.89 then tier := 'special'; k := 1;
    elsif roll < 0.94 then tier := 'epic'; k := 2;
    elsif roll < 0.95 then tier := 'exotic'; c := 2500;
    else tier := 'golden'; g := 1; end if;
    update public.profiles set scratch_at = now(), gold_wheels = gold_wheels + g where id = p.id;
    perform public.rb_pay(p.id, c, k, 'scratch', tier);
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'scratch', 0, jsonb_build_object('tier', tier, 'keys', k), false, c);
    return jsonb_build_object('rarity', tier, 'coins_won', c, 'keys_won', k, 'coins', p.coins + c, 'keys', p.keys + k,
                              'gold_wheel', g = 1, 'next', public.rb_cfg('scratch_hours')::int * 3600);
end $$;

create or replace function public.rb_gold_wheels() returns integer
language sql stable security definer set search_path = '' as $$
    select coalesce((select gold_wheels from public.profiles where id = auth.uid()), 0) $$;

-- spin it: always a good prize (coins, or a free case plus a key)
create or replace function public.rb_gold_wheel() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r integer;
        prizes text[] := array['2500', '5000', '10000', '25000', 'premium', 'titan', 'vault', 'mythic'];
        odds integer[] := array[30, 25, 15, 5, 12, 8, 4, 1];
        what text; c integer := 0;
begin
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
end $$;

-- admin: the next free spin or scratch card of a user lands on the Golden Wheel; and reset their timers for tests
create or replace function public.rb_admin_rig_gold(name text, rig boolean) returns boolean
language plpgsql security definer set search_path = '' as $$
begin
    perform public.rb_need_admin();
    update public.profiles set rig_gold = coalesce(rig, false) where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    perform public.rb_log('rig_gold', name, jsonb_build_object('on', rig));
    return coalesce(rig, false);
end $$;

create or replace function public.rb_admin_reset_timers(name text) returns boolean
language plpgsql security definer set search_path = '' as $$
begin
    perform public.rb_need_admin();
    update public.profiles set spin_at = null, spin_prize = null, scratch_at = null where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    perform public.rb_log('reset_timers', name, null);
    return true;
end $$;

-- ================================================================ Timing: a skill casino game
-- A needle runs along a bar, faster and faster. Stop it on the target: perfect x4, good x1.8, close x0.9 (most of the
-- bet back). The target moves every round. Winnings from Timing are capped at 20 000 coins a day.
create or replace function public.rb_timing_pos(seed jsonb, ms double precision) returns double precision
language sql immutable as $$
    with t as (select (seed ->> 'v')::float8 * ms / 1000 + (seed ->> 'a')::float8 * (ms / 1000) ^ 2 / 2
                      + (seed ->> 'o')::float8 as x)
    select abs(x - 2 * floor(x / 2) - 1) from t $$;                  -- 0..1, bouncing between both ends

create or replace function public.rb_timing(action text, bet integer, ms integer, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; rd public.rb_rounds%rowtype; seed jsonb; real_ms double precision;
        pos double precision; d double precision; mult numeric := 0; pay integer := 0; grade text;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into rd from public.rb_rounds where owner = p.id and game = 'timing' and open for update;
    if action = 'start' then
        if found then                                            -- an old round never stopped: lost
            update public.rb_rounds set open = false where id = rd.id;
        end if;
        if (select coalesce(sum(r.paid - r.bet), 0) from public.rb_rounds r where r.owner = p.id and r.game = 'timing'
              and r.at >= date_trunc('day', now())) >= 20000 then raise exception 'rb_slow_down'; end if;
        perform public.rb_bet(p, bet, 'timing');
        seed := jsonb_build_object('v', 2.0 + public.rb_rand() * 0.6, 'a', 0.35 + public.rb_rand() * 0.15,
                                   'o', public.rb_rand() * 2, 'c', round((0.2 + public.rb_rand() * 0.6)::numeric, 3));
        insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'timing', bet, seed, true, 0);
        return public.rb_remember(p.id, req, jsonb_build_object('seed', seed, 'coins', p.coins - bet));
    end if;
    if action <> 'stop' or not found then raise exception 'rb_bad_choice'; end if;
    real_ms := extract(epoch from clock_timestamp() - rd.at) * 1000;
    if ms is null or ms < 0 or abs(ms - real_ms) > 450 or real_ms > 9000 then ms := least(real_ms, 999999); end if;
    pos := public.rb_timing_pos(rd.secret, least(ms, 9000));
    d := abs(pos - (rd.secret ->> 'c')::float8);
    if real_ms > 9000 then grade := 'late';
    elsif d <= 0.008 then grade := 'perfect'; mult := 4;
    elsif d <= 0.025 then grade := 'good'; mult := 1.8;
    elsif d <= 0.05 then grade := 'close'; mult := 0.9;
    else grade := 'miss'; end if;
    if mult > 0 then pay := public.rb_win(p.id, rd.bet * mult, 'timing'); end if;
    update public.rb_rounds set open = false, paid = pay, secret = rd.secret || jsonb_build_object('pos', pos, 'grade', grade) where id = rd.id;
    return public.rb_remember(p.id, req, jsonb_build_object('pos', pos, 'grade', grade, 'mult', mult, 'paid', pay,
                                                            'coins', p.coins + pay));
end $$;

-- ================================================================ 5 new cases
insert into public.rb_cases (id, pos, price, odds, coin_min, coin_max, exotics, pity_tier, pity_after, variants, mode) values
    ('pocket', 0, 100, '{7800,1800,350,45,5,0}', 35, 175, false, 9, 0, '{76104,23500,384,0,12}', ''),
    ('elite', 13, 6000, '{7200,1500,900,300,96,4}', 2300, 13500, false, 9, 0, '{69320,29800,640,216,24}', ''),
    ('royal', 14, 25000, '{7400,0,1300,900,380,20}', 9000, 54000, false, 9, 0, '{68216,31050,656,54,24}', ''),
    ('shiny', 15, 8000, '{3000,0,3200,2600,1170,30}', 100, 700, false, 9, 0, '{0,69400,30000,420,180}', ''),
    ('banners', 16, 2000, '{3500,3800,2000,550,150,0}', 800, 5200, false, 9, 0, '{100000,0,0,0,0}', 'kinds:banner')
on conflict (id) do nothing;

-- ================================================================ rich players: Titanium badges can be bought in the shop
update public.rb_catalog set price = value * 50 where kind = 'badge' and cls = 3 and rarity <> 'exotic' and price is null;
do $$ declare src text; begin
    select pg_get_functiondef(p.oid) into src from pg_proc p join pg_namespace n on n.oid = p.pronamespace
     where n.nspname = 'public' and p.proname = 'rb_buy';
    if position('c.cls >= 3 or' in src) > 0 then
        execute replace(src, 'c.cls >= 3 or', 'c.cls >= 4 or');           -- Titanium yes; Gold and Mythic never
    end if;
end $$;

-- ================================================================ normal or gold banner: your choice
create or replace function public.rb_banner_gold(level integer) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype;
begin
    p := public.rb_lock_me();
    update public.profiles set equip = coalesce(equip, '{}'::jsonb) || jsonb_build_object('banner_gold', greatest(0, least(3, coalesce(level, 3))))
     where id = p.id;
    return json_build_object('banner_gold', greatest(0, least(3, coalesce(level, 3))));
end $$;

create or replace function public.rb_looks() returns json
language plpgsql stable security definer set search_path = '' as $$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    return coalesce((select json_object_agg(p.username, jsonb_strip_nulls(jsonb_build_object(
                         'tag', p.equip ->> 'tag', 'frame', p.equip ->> 'frame', 'banner', p.equip ->> 'banner',
                         'gold', nullif(least(coalesce((p.equip ->> 'banner_gold')::int, 3), public.rb_gold_level(p.equip ->> 'banner',
                                    (select w.minutes from public.rb_wear w where w.owner = p.id and w.item = p.equip ->> 'banner'))), 0))))
                       from public.profiles p
                      where not p.banned and p.equip ?| array['tag', 'frame', 'banner']), '{}'::json);
end $$;

-- ================================================================ bots: a picture and a past
create or replace function public.rb_admin_bot_avatar(name text, picture text) returns integer
language plpgsql security definer set search_path = '' as $$
declare b public.profiles%rowtype;
begin
    perform public.rb_need_admin();
    select * into b from public.profiles where lower(username) = lower(name) and bot for update;
    if not found then raise exception 'rb_bad_choice'; end if;
    if coalesce(picture, '') = '' then
        delete from public.rb_avatars where id = b.id;
    else
        if length(picture) > 40000 or picture !~ '^[A-Za-z0-9+/=]+$' then raise exception 'rb_bad_picture'; end if;
        insert into public.rb_avatars (id, data) values (b.id, picture) on conflict (id) do update set data = excluded.data;
    end if;
    update public.profiles set avatar_v = avatar_v + 1 where id = b.id;
    return b.avatar_v + 1;
end $$;

-- a believable history: cases opened, casino rounds and free spins over the last weeks
create or replace function public.rb_admin_bot_history(name text, n integer) returns integer
language plpgsql security definer set search_path = '' as $$
declare b public.profiles%rowtype; i integer; g text; bet integer; paid integer; c public.rb_cases%rowtype; d record; at timestamptz;
begin
    perform public.rb_need_admin();
    select * into b from public.profiles where lower(username) = lower(name) and bot;
    if not found then raise exception 'rb_bad_choice'; end if;
    for i in 1..greatest(1, least(coalesce(n, 40), 300)) loop
        at := now() - make_interval(secs => public.rb_rand() * 86400 * 30);
        if public.rb_rand() < 0.25 then
            select * into c from public.rb_cases where mode = '' order by public.rb_rand() limit 1;
            d := public.rb_case_drop(c);
            insert into public.rb_rounds (owner, game, bet, secret, open, paid, at)
                values (b.id, 'case:' || c.id, c.price, jsonb_build_object('item', d.item), false, d.coins, at);
        elsif public.rb_rand() < 0.15 then
            insert into public.rb_rounds (owner, game, bet, secret, open, paid, at)
                values (b.id, 'spin', 0, '{}'::jsonb, false, (array[40, 75, 120, 180, 300])[1 + floor(public.rb_rand() * 5)::int], at);
        else
            g := (array['slots', 'plinko', 'dice', 'mines', 'rocket', 'blackjack'])[1 + floor(public.rb_rand() * 6)::int];
            bet := (array[10, 25, 50, 100, 250, 500])[1 + floor(public.rb_rand() * 6)::int];
            paid := case when public.rb_rand() < 0.45 then floor(bet * (1.2 + public.rb_rand() * 2.5))::int else 0 end;
            insert into public.rb_rounds (owner, game, bet, secret, open, paid, at) values (b.id, g, bet, '{}'::jsonb, false, paid, at);
        end if;
    end loop;
    return n;
end $$;

-- ================================================================ who may call the new functions
do $$ declare f text; begin
    foreach f in array array['rb_streak_bonus(public.profiles)', 'rb_gold_wheels()', 'rb_gold_wheel()',
                             'rb_admin_rig_gold(text, boolean)', 'rb_admin_reset_timers(text)',
                             'rb_timing_pos(jsonb, double precision)', 'rb_timing(text, integer, integer, text)',
                             'rb_banner_gold(integer)', 'rb_admin_bot_avatar(text, text)', 'rb_admin_bot_history(text, integer)',
                             'rb_spin()', 'rb_spin_collect()', 'rb_scratch()', 'rb_looks()'] loop
        execute format('revoke all on function public.%s from public, anon, authenticated', f);
    end loop;
    foreach f in array array['rb_gold_wheels()', 'rb_gold_wheel()', 'rb_admin_rig_gold(text, boolean)',
                             'rb_admin_reset_timers(text)', 'rb_timing(text, integer, integer, text)', 'rb_banner_gold(integer)',
                             'rb_admin_bot_avatar(text, text)', 'rb_admin_bot_history(text, integer)',
                             'rb_spin()', 'rb_spin_collect()', 'rb_scratch()', 'rb_looks()'] loop
        execute format('grant execute on function public.%s to authenticated', f);
    end loop;
end $$;

insert into public.rb_config (key, value) values ('min_build', 2026111711)
on conflict (key) do update set value = greatest(public.rb_config.value, excluded.value);
