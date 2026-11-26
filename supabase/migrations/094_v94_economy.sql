-- Rubenium 9.4: harder ranks (one rank a day at most), the Key Forge every 12 hours with free hourly keys, daily rewards
-- that are cases, a better free wheel, and the 9.4 reset. Safe to run twice (the reset itself runs once).
-- Run after 091 and 092. Undo of everything but the reset: 094_down.sql. The reset keeps a copy of every table it
-- changes in rb_bak94_*.
--
-- 1. Ranks: Average 50 000, Investor 250 000, Businessman 1 000 000, Casino Legend 5 000 000 (rb_config tier_at_<n>).
--    You go up at most one rank a day (Paris day): profiles.tier_up_on is the day of the last rank up. rb_tier says
--    'reach' (the rank your wealth is worth) and 'wait' (true when that is higher: the next rank comes tomorrow).
-- 2. Key Forge: the forges reset every 12 hours, at midnight and noon (Paris). rb_forge_state also says 'resets'
--    (seconds to the next reset) and the hourly keys: 'hourly' (keys a claim gives, rb_config hourly_keys = 3) and
--    'hourly_in' (seconds to the next claim, 0 = ready). rb_hourly_keys() claims them, once an hour.
-- 3. Daily reward: a case every day (Starter, Standard, Nature, Standard, Premium, Medieval, Painter), no coins.
-- 4. Free spin: 100, 200, 400, 750, 1 500, 3 000, 7 500 (times your tier), a key, the Golden Wheel and an XP coupon.
--    100 coins comes up 12% of the time (was 18%), and 750 or more 29% (was 18%).
-- 5. rb_reset_94(): everything starts again for every player (see the function).
-- 6. Bots: Easy and Medium make more mistakes, and Hard is much further from Professional (Mazelock, Trifade, Reversi).
begin;

-- ---------------------------------------------------------------- 1. ranks
insert into public.rb_config (key, value) values ('tier_at_1', 50000), ('tier_at_2', 250000), ('tier_at_3', 1000000),
    ('tier_at_4', 5000000), ('hourly_keys', 3)
on conflict (key) do update set value = excluded.value where public.rb_config.key like 'tier_at_%';

alter table public.profiles add column if not exists tier_up_on date;
alter table public.profiles add column if not exists hourly_at timestamptz;

CREATE OR REPLACE FUNCTION public.rb_tier(who uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare c bigint := coalesce((select coins from public.profiles where id = who), 0);
        it bigint := public.rb_wealth_items(who); w bigint := c + it; reach integer := 0; t integer; i integer;
        fl integer; up date;
begin
    for i in 1 .. 4 loop
        if w >= coalesce(public.rb_cfg('tier_at_' || i), 1e18) then reach := i; end if;
    end loop;
    select least(4, greatest(0, coalesce(tier_floor, 0))), tier_up_on into fl, up from public.profiles where id = who;
    fl := coalesce(fl, 0);
    -- 9.4: one rank a day at most (a rank you reached stays yours)
    t := greatest(fl, least(reach, fl + case when up is null or up < public.rb_today() then 1 else 0 end));
    return jsonb_build_object('tier', t, 'name', (array['Poor', 'Average', 'Investor', 'Businessman', 'Casino Legend'])[t + 1],
                              'mult', coalesce(public.rb_cfg('tier_x_' || t), 1), 'wealth', w, 'coins', c, 'items', it,
                              'at', case when t > 0 then public.rb_cfg('tier_at_' || t) else 0 end,
                              'next', case when t < 4 then public.rb_cfg('tier_at_' || (t + 1)) end,
                              'next_name', case when t < 4 then (array['Poor', 'Average', 'Investor', 'Businessman',
                                                                      'Casino Legend'])[t + 2] end,
                              'top', 4, 'cap_x', coalesce(public.rb_cfg('cap_x_' || t), 1),
                              'reach', reach, 'wait', reach > t);                                    -- 9.4
end $function$;

CREATE OR REPLACE FUNCTION public.rb_tier_keep(who uuid)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare t integer := (public.rb_tier(who) ->> 'tier')::int;
begin
    update public.profiles set tier_floor = t, tier_up_on = public.rb_today()
     where id = who and coalesce(tier_floor, 0) < t;
    return t;
end $function$;

-- ---------------------------------------------------------------- 2. the Key Forge, every 12 hours, and hourly keys
-- the start of this half day: midnight or noon in Paris
create or replace function public.rb_forge_from() returns timestamptz
language sql stable set search_path to '' as $$
    select (date_trunc('day', now() at time zone 'Europe/Paris')
            + case when extract(hour from now() at time zone 'Europe/Paris') >= 12 then interval '12 hours'
                   else interval '0 hours' end) at time zone 'Europe/Paris' $$;

CREATE OR REPLACE FUNCTION public.rb_forge_state(who uuid)
 RETURNS jsonb
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    with t as (select (public.rb_tier(who) ->> 'tier')::int as tier),
         d as (select coalesce(public.rb_cfg('forge_day_' || t.tier), public.rb_cfg('forge_day'), 5)::int as cap from t),
         h as (select (select hourly_at from public.profiles where id = who) as at)
    select jsonb_build_object(
        'price', greatest(coalesce(public.rb_cfg('forge_min'), 250)::bigint,
                          (round(public.rb_wealth(who) * coalesce(public.rb_cfg('forge_pct'), 0.005) / 10) * 10)::bigint),
        'cap', d.cap,
        'left', greatest(0, d.cap - (select count(*)::int from public.rb_ledger l
              where l.owner = who and l.reason = 'forge' and l.at >= public.rb_forge_from())),
        'resets', greatest(0, ceil(extract(epoch from (public.rb_forge_from() + interval '12 hours' - now()))))::int,
        'hourly', coalesce(public.rb_cfg('hourly_keys'), 3)::int,
        'hourly_in', case when h.at is null then 0
                          else greatest(0, ceil(extract(epoch from (h.at + interval '1 hour' - now()))))::int end)
    from d, h $function$;

create or replace function public.rb_hourly_keys() returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; n integer := coalesce(public.rb_cfg('hourly_keys'), 3)::int;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('shop');
    if p.hourly_at is not null and now() < p.hourly_at + interval '1 hour' then raise exception 'rb_too_soon'; end if;
    update public.profiles set hourly_at = now() where id = p.id;
    perform public.rb_pay(p.id, 0, n, 'hourly', null);
    return jsonb_build_object('coins', p.coins, 'keys', p.keys + n, 'won_keys', n, 'forge', public.rb_forge_state(p.id));
end $$;
revoke all on function public.rb_forge_from() from public, anon, authenticated;
revoke all on function public.rb_hourly_keys() from public, anon;
grant execute on function public.rb_hourly_keys() to authenticated;

-- ---------------------------------------------------------------- 3. daily reward: a case a day
CREATE OR REPLACE FUNCTION public.rb_login_rewards()
 RETURNS jsonb
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
    select '[{"case":"starter"},{"case":"standard"},{"case":"nature"},{"case":"standard"},{"case":"premium"},{"case":"medieval"},{"case":"painter"}]'::jsonb $function$;

-- ---------------------------------------------------------------- 4. the free spin
CREATE OR REPLACE FUNCTION public.rb_spin_table(m numeric)
 RETURNS jsonb
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
    select jsonb_build_object(
        'slots', jsonb_build_array(public.rb_scaled(100, m), public.rb_scaled(200, m), public.rb_scaled(400, m),
                                   public.rb_scaled(750, m), public.rb_scaled(1500, m), public.rb_scaled(3000, m),
                                   public.rb_scaled(7500, m), -1, -2, -3),
        'odds', jsonb_build_array(1200, 1900, 1800, 1500, 900, 400, 100, 1100, 500, 600)) $function$;

-- ---------------------------------------------------------------- 5. the 9.4 reset
-- Every player (not bots): every item but the OG tag (badges, mythics, cosmetics, titles), every unopened case, the
-- collection, trophies and set rewards go; coins 2 500 and keys 5 with the starter cases (3 Starter, 5 Standard);
-- level and XP to 0; rank back to Poor (and up at most one a day from tomorrow on); gold keys and wheels to 0; the free
-- spin, scratch card, daily case and hourly keys are ready again.
-- Everyone, bots too: every leaderboard, every stat and every trophy count from now (board_from, stats_from,
-- ach_from), streaks to 0, quests start again. Anything in play that holds coins or items ends with no pay (items go
-- back first). Bots' Jackpot entries and race bets stay, so the arena never stops.
create or replace function public.rb_reset_94() returns jsonb
language plpgsql security definer set search_path to '' as $$
declare n integer; gone integer; cases integer; p record; t text;
begin
    if coalesce(public.rb_cfg('reset_094'), 0) <> 0 then raise exception 'rb_already_done'; end if;

    foreach t in array array['profiles', 'rb_items', 'rb_case_stock', 'rb_ach', 'rb_quest_claims', 'rb_config',
                             'rb_seen', 'rb_set_claims', 'rb_case_week'] loop
        if to_regclass('public.' || t) is not null and to_regclass('public.rb_bak94_' || replace(t, 'rb_', '')) is null then
            execute format('create table public.%I as select * from public.%I', 'rb_bak94_' || replace(t, 'rb_', ''), t);
            execute format('alter table public.%I enable row level security', 'rb_bak94_' || replace(t, 'rb_', ''));
            execute format('revoke all on public.%I from public, anon, authenticated', 'rb_bak94_' || replace(t, 'rb_', ''));
        end if;
    end loop;

    -- anything players have in play ends with no pay; the items it held go back first
    update public.rb_duels set state = 'cancelled', why = 'reset' where state not in ('done', 'cancelled');
    update public.rb_flips set state = 'cancelled', why = 'reset', done_at = now() where state not in ('done', 'cancelled');
    update public.rb_trades set state = 'cancelled', why = 'reset', updated = now() where state not in ('done', 'cancelled');
    update public.rb_golf set state = 'cancelled', why = 'reset', done_at = now() where state not in ('done', 'cancelled');
    update public.rb_golf_parties set state = 'cancelled', done_at = now() where state not in ('done', 'cancelled');
    update public.rb_golf_solo set state = 'quit', done_at = now() where state not in ('done', 'quit');
    update public.rb_wave_duels set state = 'cancelled', why = 'reset', done_at = now() where state not in ('done', 'cancelled');
    update public.rb_wave_runs set state = 'quit', done_at = now() where state not in ('done', 'quit');
    update public.rb_wave_rooms set state = 'cancelled' where state in ('open', 'live');
    update public.rb_kart_rooms set state = 'cancelled' where state in ('open', 'live');
    update public.rb_hoops_games set state = 'left' where state = 'open';
    if to_regclass('public.rb_c4') is not null then
        execute 'update public.rb_c4 set state = ''done'', paid = 0, updated_at = now() where state <> ''done''';
    end if;
    update public.rb_bg set state = 'cancelled', why = 'reset', done_at = now() where state in ('open', 'live');
    update public.rb_item_swaps set state = 'cancelled', done_at = now() where state = 'open';
    update public.rb_offers set state = 'gone' where state = 'open';
    update public.rb_listings set state = 'cancelled' where state = 'open';
    with gone_e as (delete from public.rb_jackpot_entries e using public.rb_jackpots j
                     where j.id = e.jackpot and j.state not in ('done', 'empty') and e.owner is not null
                       and e.owner in (select id from public.profiles where not bot)
                    returning e.jackpot, e.value)
    update public.rb_jackpots j set total = greatest(0, j.total - s.v)
      from (select jackpot, sum(value) v from gone_e group by jackpot) s where s.jackpot = j.id;
    with gone_b as (delete from public.rb_race_bets b using public.rb_races r
                     where r.id = b.race and r.state <> 'done' and b.owner is not null
                       and b.owner in (select id from public.profiles where not bot)
                    returning b.race, b.amount)
    update public.rb_races r set total = greatest(0, r.total - s.v)
      from (select race, sum(amount) v from gone_b group by race) s where s.race = r.id;
    update public.rb_rounds set open = false, paid = 0 where open;
    update public.rb_mg set open = false, void = true where open;
    update public.rb_items set locked = null where locked is not null;

    -- every player: every item but the OG tag, every case, the collection, trophies, set rewards
    delete from public.rb_items i using public.profiles pr where pr.id = i.owner and not pr.bot and i.item <> 'tag:og';
    get diagnostics gone = row_count;
    delete from public.rb_case_stock s using public.profiles pr where pr.id = s.owner and not pr.bot;
    get diagnostics cases = row_count;
    delete from public.rb_case_week s using public.profiles pr where pr.id = s.owner and not pr.bot;
    delete from public.rb_seen s using public.profiles pr where pr.id = s.owner and not pr.bot;
    delete from public.rb_set_claims s using public.profiles pr where pr.id = s.owner and not pr.bot;
    delete from public.rb_ach a using public.profiles pr where pr.id = a.owner and not pr.bot;
    insert into public.rb_seen (owner, item)
        select owner, item from public.rb_items where item = 'tag:og' on conflict do nothing;

    update public.profiles
       set coins = 2500, keys = 5, coin_min = 0, key_min = 0, day = current_date, day_coins = 0,
           gold_keys = 0, gold_wheels = 0, rig_gold = false, og_coupon_50 = false,
           xp = 0, level = 0, xp_day = null, xp_day_gain = 0, xp_day_src = '{}'::jsonb, xp_hr = null, xp_hr_src = '{}'::jsonb,
           tier_floor = 0, tier_seen = 0, tier_up_on = null,
           spin_at = null, spin_prize = null, scratch_at = null, daily_at = null, hourly_at = null,
           equip = coalesce(equip, '{}'::jsonb) - 'trophy1' - 'trophy2' - 'trophy3'
     where not bot;
    get diagnostics n = row_count;
    insert into public.rb_ledger (owner, coins, keys, reason, ref)
        select id, 2500, 5, 'gift', '9.4 reset: starter pack' from public.profiles where not bot;
    for p in select id from public.profiles where not bot loop
        perform public.rb_starter_pack(p.id);
        perform public.rb_fix_equip(p.id);
    end loop;

    -- everyone, bots too: boards, stats, trophies, streaks, quests
    insert into public.rb_config (key, value) values ('board_from', extract(epoch from now())::bigint),
        ('stats_from', extract(epoch from now())::bigint), ('ach_from', extract(epoch from now())::bigint)
    on conflict (key) do update set value = excluded.value;
    update public.profiles set board_min0 = minutes, streak = 0, streak_day = null;
    update public.profiles set bot_cfg = bot_cfg - 'stats' where bot and bot_cfg ? 'stats';
    delete from public.rb_quest_claims;

    insert into public.rb_config (key, value) values ('reset_094', 1) on conflict (key) do update set value = 1;
    return jsonb_build_object('players', n, 'items_removed', gone, 'case_rows_removed', cases);
end $$;
revoke all on function public.rb_reset_94() from public, anon, authenticated;

-- ---------------------------------------------------------------- 6. bots: Easy and Medium make real mistakes, and
-- Professional is far ahead of Hard (Hard looks less far and slips more; Professional is unchanged: the best it can).
-- Mazelock: Easy wanders 45% and walls at random 30%; Medium slips 30% and sometimes just walks; Hard looks one move
-- ahead (was two) and slips 12%. Trifade: Hard slips 30%, Medium misses a quarter of its wins, Easy most of them.
-- Reversi: Medium plays at random half the time, Hard 15%.
create or replace function public.mz_bot(b jsonb, s integer, level text) returns integer
language plpgsql volatile set search_path to '' as $$
declare h text := b ->> 'h'; v text := b ->> 'v'; p1 integer := (b -> 'p' ->> 0)::int; p2 integer := (b -> 'p' ->> 1)::int;
        w1 integer := (b -> 'w' ->> 0)::int; w2 integer := (b -> 'w' ->> 1)::int;
        me integer := case when s = 1 then p1 else p2 end; op integer := case when s = 1 then p2 else p1 end;
        goal integer := case when s = 1 then 0 else 8 end; depth integer; slip numeric; deadline timestamptz;
        m integer; sc integer; nh text; nv text; n1 integer; n2 integer; nw1 integer; nw2 integer; a integer;
        scored integer[] := '{}'; moves integer[] := '{}'; best integer; i integer; k integer; path integer[];
        cands integer[]; d integer; alpha integer; best_m integer; pick integer;
begin
    path := public.mz_path(h, v, me, goal);
    if level = 'easy' then                                         -- wanders: mostly along its path, walls at random
        if (case when s = 1 then w1 else w2 end) > 0 and public.rb_rand() < 0.3 then
            for i in 1..12 loop
                m := case when public.rb_rand() < 0.5 then 100 else 200 end + floor(public.rb_rand() * 64)::int;
                if public.mz_play(b, s, m) is not null then return m; end if;
            end loop;
        end if;
        cands := public.mz_steps(h, v, me, op);
        if public.rb_rand() < 0.45 or cardinality(path) = 0 then
            return cands[1 + floor(public.rb_rand() * cardinality(cands))::int];
        end if;
        if path[1] = any(cands) then return path[1]; end if;
        return cands[1 + floor(public.rb_rand() * cardinality(cands))::int];
    end if;
    depth := case level when 'medium' then 1 when 'hard' then 1 else 4 end;          -- 9.4: Hard looks one move ahead
    slip := case level when 'medium' then 0.3 when 'hard' then 0.12 else 0 end;      -- 9.4: more slips
    deadline := clock_timestamp() + make_interval(secs => case level when 'insane' then 2.6 else 1.5 end);
    -- 9.4: Medium sometimes just walks its path without thinking
    if level = 'medium' and cardinality(path) > 0 and public.rb_rand() < 0.25 and path[1] = any(public.mz_steps(h, v, me, op)) then
        return path[1];
    end if;
    -- a sure race: just run
    if (case when s = 1 then w2 else w1 end) = 0 and cardinality(path) > 0
       and public.mz_dist(h, v, me, goal) <= public.mz_dist(h, v, op, 8 - goal) then
        if path[1] = any(public.mz_steps(h, v, me, op)) then return path[1]; end if;
    end if;
    cands := public.mz_candidates(h, v, p1, p2, w1, w2, s, case level when 'medium' then 3 when 'hard' then 5 else 7 end);
    -- Professional deepens until its time is up and keeps the last search it finished; the others look depth ahead
    for d in (case when level = 'insane' then 1 else depth end)..depth loop
        scored := '{}'; moves := '{}'; alpha := -100000;
        foreach m in array cands loop
            nh := h; nv := v; n1 := p1; n2 := p2; nw1 := w1; nw2 := w2;
            if m < 100 then
                if s = 1 then n1 := m; else n2 := m; end if;
            else
                a := m % 100;
                if m < 200 then nh := overlay(h placing s::text from a + 1 for 1); else nv := overlay(v placing s::text from a + 1 for 1); end if;
                if public.mz_dist(nh, nv, p1, 0) >= 999 or public.mz_dist(nh, nv, p2, 8) >= 999 then continue; end if;
                if s = 1 then nw1 := w1 - 1; else nw2 := w2 - 1; end if;
            end if;
            if (s = 1 and n1 / 9 = 0) or (s = 2 and n2 / 9 = 8) then return m; end if;       -- home: win now
            sc := -public.mz_search(nh, nv, n1, n2, nw1, nw2, 3 - s, d - 1, -100000,
                                    case when slip > 0 then 100000 else -alpha + 1 end, deadline);
            if sc > alpha then alpha := sc; end if;
            scored := scored || sc; moves := moves || m;
        end loop;
        exit when cardinality(moves) = 0;
        exit when d > 1 and clock_timestamp() > deadline;          -- cut short: keep the last full search
        best := -100001; best_m := null;
        for i in 1..cardinality(moves) loop                         -- ties: a step beats a wall, so it never stalls
            if scored[i] > best or (scored[i] = best and moves[i] < 100 and coalesce(best_m, 999) >= 100) then
                best := scored[i]; best_m := moves[i];
            end if;
        end loop;
        pick := best_m;
        k := array_position(cands, best_m);                         -- the next depth looks at the best move first
        if k is not null and k > 1 then cands := best_m || (cands[1:k - 1] || cands[k + 1:]); end if;
        exit when clock_timestamp() > deadline or abs(best) >= 5000;
    end loop;
    m := coalesce(pick, path[1]);
    -- Medium and Hard slip now and then: the second best move (never one that loses on the spot)
    if slip > 0 and public.rb_rand() < slip and cardinality(moves) > 1 then
        k := null; sc := -100001;
        for i in 1..cardinality(moves) loop
            if moves[i] <> m and scored[i] > sc and scored[i] > -5000 then sc := scored[i]; k := moves[i]; end if;
        end loop;
        if k is not null then m := k; end if;
    end if;
    return m;
end $$;

create or replace function public.tri_bot(b jsonb, s integer, level text) returns integer
language plpgsql stable security definer set search_path to '' as $$
declare me integer[] := public.tri_q(b, s); op integer[] := public.tri_q(b, 3 - s); nm integer[]; cv integer;
        sc integer; best integer; pick integer; nbest integer := 0; wins integer[] := '{}'; safe integer[] := '{}';
        allm integer[] := '{}'; scores integer[] := array_fill(0, array[9]); r float8 := public.rb_rand();
begin
    for m in 0..8 loop
        continue when m = any(me) or m = any(op);
        allm := allm || m;
        nm := public.tri_add(me, m);
        if public.tri_win(nm) then
            wins := wins || m; sc := 2000;
        else
            cv := public.tri_val(op, nm);                             -- the other side to move after it
            sc := case when cv < 0 then 1000 + cv when cv > 0 then -1000 + cv else 0 end;
            if cv <> 1 then safe := safe || m; end if;                -- it does not hand them a win at once
        end if;
        scores[m + 1] := sc;
        if best is null or sc > best then best := sc; pick := m; nbest := 1;
        elsif sc = best then nbest := nbest + 1; if public.rb_rand() * nbest < 1 then pick := m; end if; end if;
    end loop;
    if cardinality(allm) = 0 then return null; end if;
    if level = 'insane' then return pick; end if;
    if level = 'hard' then
        if cardinality(wins) > 0 or r >= 0.3 then return pick; end if;      -- 9.4: slips 30%
        if cardinality(safe) > 0 then return safe[1 + floor(public.rb_rand() * cardinality(safe))::int]; end if;
        return pick;
    end if;
    if level = 'medium' then
        if cardinality(wins) > 0 and public.rb_rand() < 0.75 then return wins[1]; end if;      -- 9.4: misses some wins
        if r < 0.2 then return pick; end if;
        if cardinality(safe) > 0 and public.rb_rand() < 0.65 then
            return safe[1 + floor(public.rb_rand() * cardinality(safe))::int];
        end if;
        return allm[1 + floor(public.rb_rand() * cardinality(allm))::int];
    end if;
    if cardinality(wins) > 0 and r < 0.4 then return wins[1]; end if;    -- easy
    if cardinality(safe) > 0 and public.rb_rand() < 0.3 then
        return safe[1 + floor(public.rb_rand() * cardinality(safe))::int];
    end if;
    return allm[1 + floor(public.rb_rand() * cardinality(allm))::int];
end $$;

create or replace function public.rv_bot(b text, p text, level text) returns integer
language plpgsql volatile set search_path to '' as $$
declare o text := case p when '1' then '2' else '1' end; mv integer[] := public.rv_moves(b, p); m integer; r integer;
        b1 text; b2 text; replies integer[]; v integer; worst integer; best integer := null; pick integer;
begin
    if cardinality(mv) = 0 then return null; end if;
    if level = 'easy' then return mv[1 + floor(public.rb_rand() * cardinality(mv))::int]; end if;
    if (level = 'medium' and public.rb_rand() < 0.5) or (level = 'hard' and public.rb_rand() < 0.15) then   -- 9.4
        return mv[1 + floor(public.rb_rand() * cardinality(mv))::int]; end if;
    foreach m in array mv loop
        b1 := public.rv_play(b, m, p);
        if level = 'medium' then
            v := cardinality(public.rv_flips(b, m, p)) * 10;
        elsif level = 'hard' then
            v := public.rv_eval(b1, p) - 6 * cardinality(public.rv_moves(b1, o));
        elsif level = 'insane' then                             -- insane: three moves ahead, deeper at the end
            v := -public.rv_search(b1, o, case when public.rv_count(b, '.') <= 7 then 6 else 2 end, -1000000, 1000000);
        else                                                    -- (not used) one answer deep
            replies := public.rv_moves(b1, o);
            if cardinality(replies) = 0 then
                v := public.rv_eval(b1, p) + 60;                 -- they must pass: great
            else
                worst := null;
                foreach r in array replies loop
                    b2 := public.rv_play(b1, r, o);
                    v := public.rv_eval(b2, p);
                    if worst is null or v < worst then worst := v; end if;
                end loop;
                v := worst - 5 * cardinality(replies);
            end if;
        end if;
        v := v * 4 + floor(public.rb_rand() * 4)::int;           -- equal moves: not always the same one
        if best is null or v > best then best := v; pick := m; end if;
    end loop;
    return pick;
end $$;

commit;
