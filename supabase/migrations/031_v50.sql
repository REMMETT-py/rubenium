-- ================================================================ Rubenium 5.0 (build 2026.11.20.1)
-- THE FULL RELEASE. Run after 029_v46.sql and 030_v47.sql (the live server never had those two: run all three, in
-- order). One transaction, safe to run again: the reset only ever happens once (reset_050).
--
--   * Fresh start for everyone: coins, keys, items, levels, XP, badges, cases, quests, sets, streaks, market, trades,
--     coinflips, leaderboards, notifications and history all start again. Kept: accounts and passwords, friends,
--     messages, profile pictures, hours played (and what they unlock), the OG tag, settings and settings backups.
--     Everything taken is copied first into rb_bak50_* tables.
--   * Start: 500 coins and 3 keys, OG players 1 500 coins, 3 keys and the OG coupon (up to level 5).
--   * OG Prismatic Chest (20 and 21 November 2026, Paris time): 25 keys, 10 000 coins and a 1 000 XP coupon, given
--     only when the player presses Claim at the very end of the scene, once ever. A crash before Claim gives nothing
--     and the scene plays again; a second Claim (a resend, two PCs) gives nothing more.
--   * Mythic badges: Prismatic is now the rarest finish (above Gold) and has the highest worth; in the Top Tier Case
--     a Titanium (white / black) Mythic is about 1 in 30 000 opens, Gold 1 in 75 000, Prismatic 1 in 100 000. Every
--     other case is harder. The Rubenium R is 4 times rarer than any other Mythic.
--   * Royal Case: 30% coins (8 000 - 32 000) instead of mostly coins.
--   * Quick sell pays 55% of worth (was 35%). Wave Rush pays 5 coins for every 10 m. Mini game limits raised.
--   * Keys: a small chance (3%) of finding a key in any mini game that pays, and 50% on every quest claimed.
--   * Levels boost coin rewards more (up to +60% at level 100) and quests are boosted too.
begin;

-- ================================================================ settings
insert into public.rb_config (key, value) values
    ('start_coins', 500), ('start_keys', 3), ('og_start_coins', 1500), ('og_chest_xp', 1000),
    ('key_find_pct', 3), ('quest_key_pct', 50)
on conflict (key) do nothing;
update public.rb_config set value = 1795302000 where key = 'og_event_until';      -- 22/11/2026 00:00 Paris
update public.rb_config set value = 0.55 where key = 'quick_worth_share';
update public.rb_config set value = 500 where key = 'game_window_cap' and value < 500;
update public.rb_config set value = 600 where key = 'mg_window_cap' and value < 600;
insert into public.rb_config (key, value) values ('og_event_until', 1795302000) on conflict (key) do nothing;

-- ================================================================ the 1 000 XP coupon of the OG chest
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, worth, weight, limited, base_worth)
values ('coupon:ogchest', 'coupon', 'ogchest', '', 'exotic', null, 1000, false, 0, 0, 1, true, 0)
on conflict (id) do update set value = excluded.value, rarity = 'exotic', tradeable = false, limited = true;
update public.rb_catalog set value = (select value from public.rb_config where key = 'og_chest_xp')
 where id = 'coupon:ogchest';

-- ================================================================ Mythic: Prismatic above Gold
-- The finish order is now Titanium < Gold < Prismatic, so the worths swap (each design keeps its own numbers).
do $$ begin
    if exists (select 1 from public.rb_config where key = 'mythic_flip_050') then return; end if;
    create table if not exists public.rb_bak50_mythic as
        select id, worth, value, base_worth from public.rb_catalog where kind = 'badge' and rarity = 'exotic';
    alter table public.rb_bak50_mythic enable row level security;
    update public.rb_catalog g set worth = pr.worth, value = pr.value, base_worth = pr.base_worth
      from public.rb_bak50_mythic pr
     where g.id like 'badge:%:gold' and g.rarity = 'exotic' and pr.id = replace(g.id, ':gold', ':prime');
    update public.rb_catalog pr set worth = g.worth, value = g.value, base_worth = g.base_worth
      from public.rb_bak50_mythic g
     where pr.id like 'badge:%:prime' and pr.rarity = 'exotic' and g.id = replace(pr.id, ':prime', ':gold');
    insert into public.rb_config (key, value) values ('mythic_flip_050', 1);
end $$;

-- the R is 4 times rarer than any other Mythic design
create or replace function public.rb_pick_mythic(klass integer)
 returns text language plpgsql security definer set search_path to '' as $function$
declare names text[] := array['galaxy', 'phoenix', 'glitch', 'crystal', 'dragon', 'rubenium'];
        base text; var text;
begin
    base := names[public.rb_roll(array[4, 4, 4, 4, 4, 1]) + 1];
    var := case klass when 4 then 'gold' when 5 then 'prime'
                      else (array['black', 'white'])[floor(public.rb_rand() * 2)::int + 1] end;
    return 'badge:' || base || ':' || var;
end $function$;

-- ================================================================ Mythic chances, in billionths of one open
-- The Top Tier Case ('mythic') is the best place for a Mythic: 1 in 30 000 Titanium, 1 in 75 000 Gold, 1 in 100 000
-- Prismatic (17 in 300 000 for any Mythic). Every other case is harder.
alter table public.rb_cases add column if not exists myth_ppb bigint not null default 0;
update public.rb_cases c set myth_ppb = v.ppb, odds = c.odds[1:5] || array[0]
  from (values ('mythic', 56667), ('royal', 28333), ('shiny', 14167), ('cosmos', 11333), ('vault', 8500),
               ('elite', 5667), ('titan', 3400), ('gamble', 2267), ('premium', 1133), ('standard', 567)) v(id, ppb)
 where c.id = v.id;
update public.rb_cases set myth_ppb = 0 where id not in ('mythic', 'royal', 'shiny', 'cosmos', 'vault', 'elite', 'titan',
                                                         'gamble', 'premium', 'standard');
update public.rb_cases set odds = odds[1:5] || array[0] where odds[6] <> 0;
-- odds is shown by old builds only and must still add up to 10 000
update public.rb_cases set odds = array[odds[1] + 10000 - (select sum(x) from unnest(odds) x)] || odds[2:6]
 where (select sum(x) from unnest(odds) x) <> 10000;

-- ================================================================ Royal Case: still coins, never mostly coins
do $$ begin
    if exists (select 1 from public.rb_config where key = 'royal_050') then return; end if;
    update public.rb_cases set coin_min = 8000, coin_max = 32000,
           grid = (select array_agg(round(x * 700000000.0 / (select sum(y) from unnest(grid) y))::bigint order by i)
                     from unnest(grid) with ordinality t(x, i))
     where id = 'royal' and grid is not null;
    insert into public.rb_config (key, value) values ('royal_050', 1);
end $$;

-- ================================================================ the drop reads the Mythic chance in billionths
create or replace function public.rb_case_drop(c public.rb_cases, out tier integer, out klass integer, out item text, out coins integer)
 returns record language plpgsql security definer set search_path to '' as $function$
declare r double precision; roll bigint; i integer;
begin
    tier := 0; klass := 0; coins := 0;
    roll := floor(public.rb_rand() * 1000000000)::bigint;
    if c.myth_ppb > 0 and roll < c.myth_ppb and c.mode = '' then         -- 5.0: Titanium 10, Gold 4, Prismatic 3
        tier := 5;
        klass := (array[3, 4, 5])[public.rb_roll(array[10, 4, 3]) + 1];
        item := public.rb_pick_mythic(klass);
        return;
    end if;
    if c.grid is not null and c.mode = '' then                -- 4.7: one roll over the whole table
        roll := roll - c.myth_ppb;
        for i in 1 .. 20 loop
            if roll < c.grid[i] then
                tier := (i - 1) / 5 + 1; klass := (i - 1) % 5;
                item := public.rb_pick_badge(tier, klass);
                if item is not null then return; end if;
                tier := 0; klass := 0; exit;
            end if;
            roll := roll - c.grid[i];
        end loop;
        coins := c.coin_min + floor(public.rb_rand() * (c.coin_max - c.coin_min + 1))::int;
        if public.rb_rand() * 100 < coalesce(public.rb_cfg('case_lucky_pct'), 0) then
            coins := coins * coalesce(public.rb_cfg('case_lucky_x'), 1)::int;
        end if;
        return;
    end if;
    tier := public.rb_roll(c.odds);
    if tier = 5 then tier := 0; end if;                       -- 5.0: Mythics only come from myth_ppb
    if tier > 0 and c.mode like 'kinds:%' then
        item := public.rb_pick_weighted(string_to_array(substr(c.mode, 7), ','), tier, null);
        if item is not null then return; end if;
        tier := 0;
    end if;
    if tier > 0 and c.mode like 'items:%' then
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
    else
        klass := public.rb_roll(c.variants);
        if klass = 3 and tier <= 2 then klass := 2; end if;
        item := public.rb_pick_badge(tier, klass);
    end if;
end $function$;

-- ================================================================ Wave Rush: 5 coins for every 10 m
create or replace function public.rb_wave_pay_for(x integer) returns integer
language sql immutable set search_path = '' as $$
    select (greatest(0, x) / 1000) * 5 $$;

-- ================================================================ levels boost rewards more (+0.6% a level)
create or replace function public.rb_level_mult(who uuid) returns numeric
language sql stable security definer set search_path = '' as $$
    select 1 + 0.006 * coalesce((select level from public.profiles where id = who), 0) $$;

-- ================================================================ keys found in mini games
-- Called where a mini game pays. Rare (key_find_pct, 3%), never on a round that pays nothing. The player is told by a
-- notice ('key_found') that the app turns into a big key on screen.
create or replace function public.rb_key_find(who uuid, g text) returns integer
language plpgsql security definer set search_path = '' as $$
begin
    if public.rb_rand() * 100 >= coalesce(public.rb_cfg('key_find_pct'), 0) then return 0; end if;
    if exists (select 1 from public.profiles where id = who and bot) then return 0; end if;
    perform public.rb_pay(who, 0, 1, 'key_found', g);
    perform public.rb_notice(who, 'key_found', jsonb_build_object('game', g, 'keys', 1));
    return 1;
end $$;
revoke all on function public.rb_key_find(uuid, text) from public, anon, authenticated;

create or replace function public.rb_game_pay(who uuid, g text, pay integer) returns integer
language plpgsql volatile security definer set search_path = '' as $$
declare w json := public.rb_game_window(who, g); n integer := (w ->> 'rounds')::int; fr integer := (w ->> 'full')::int;
        m numeric := public.rb_level_mult(who); got integer;
begin
    pay := round(pay * coalesce(public.rb_cfg('game_pay_mult'), 1) * m);
    if n >= fr * 2 then pay := pay / 4; elsif n >= fr then pay := pay / 2; end if;
    got := greatest(0, least(pay, floor((w ->> 'cap')::int * m)::int - (w ->> 'paid')::int));
    if got > 0 then perform public.rb_key_find(who, g); end if;
    return got;
end $$;
revoke all on function public.rb_game_pay(uuid, text, integer) from public, anon, authenticated;

-- ================================================================ quests: level boost and a 50% key
create or replace function public.rb_quest_claim(which text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; q record; pay integer; k integer := 0;
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
    pay := round(q.reward * public.rb_level_mult(p.id))::int;
    if public.rb_rand() * 100 < coalesce(public.rb_cfg('quest_key_pct'), 0) then k := 1; end if;
    perform public.rb_pay(p.id, pay, k, 'quest', q.quest);
    return jsonb_build_object('paid', pay, 'coins', p.coins + pay, 'won_keys', k, 'keys', p.keys + k,
                              'key_found', k > 0);
end $$;
revoke all on function public.rb_quest_claim(text) from public, anon;
grant execute on function public.rb_quest_claim(text) to authenticated;

-- ================================================================ the OG Prismatic Chest
-- rb_og_chest(): is the chest waiting for me? Nothing is given here, so the scene can play as many times as needed.
create or replace function public.rb_og_chest() returns json
language plpgsql stable security definer set search_path = '' as $$
declare p public.profiles%rowtype; ends double precision := coalesce(public.rb_cfg('og_event_until'), 0);
begin
    select * into p from public.profiles where id = auth.uid();
    if not found then return json_build_object('due', false); end if;
    return json_build_object(
        'due', p.og_event_at is null and extract(epoch from now()) < ends
               and exists (select 1 from public.rb_items i where i.owner = p.id and i.item = 'tag:og'),
        'claimed', p.og_event_at is not null, 'ends', ends,
        'coins', 10000, 'keys', 25, 'xp', coalesce(public.rb_cfg('og_chest_xp'), 1000));
end $$;
revoke all on function public.rb_og_chest() from public, anon;
grant execute on function public.rb_og_chest() to authenticated;

-- rb_og_chest_claim(req): the Claim button. Once ever per account, under the row lock; a resend of the same req
-- gets the same answer, a second claim gets 'already'.
create or replace function public.rb_og_chest_claim(req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; new_id uuid;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    if p.og_event_at is not null then
        return jsonb_build_object('claimed', true, 'already', true, 'coins', p.coins, 'keys', p.keys);
    end if;
    if extract(epoch from now()) >= coalesce(public.rb_cfg('og_event_until'), 0) then raise exception 'rb_og_over'; end if;
    if not exists (select 1 from public.rb_items i where i.owner = p.id and i.item = 'tag:og') then
        raise exception 'rb_og_only';
    end if;
    update public.profiles set og_event_at = now() where id = p.id;
    perform public.rb_pay(p.id, 10000, 25, 'og_chest', null);
    new_id := public.rb_give(p.id, 'coupon:ogchest', 'og_chest');
    perform public.rb_log('og_chest', p.username, jsonb_build_object('coins', 10000, 'keys', 25, 'coupon', new_id));
    return public.rb_remember(p.id, req, jsonb_build_object('claimed', true, 'coins', p.coins + 10000,
                              'keys', p.keys + 25, 'id', new_id, 'item', 'coupon:ogchest'));
end $$;
revoke all on function public.rb_og_chest_claim(text) from public, anon;
grant execute on function public.rb_og_chest_claim(text) to authenticated;

-- the old OG event (3.0.0) gives nothing any more
create or replace function public.rb_og_event() returns json
language sql security definer set search_path = '' as $$ select json_build_object('given', false) $$;

-- ================================================================ the 5.0 fresh start (happens once, ever)
do $$
declare og uuid[];
begin
    if coalesce(public.rb_cfg('reset_050'), 0) <> 0 then return; end if;

    -- copies of everything taken
    create table if not exists public.rb_bak50_profiles as select *, now() as saved_at from public.profiles;
    create table if not exists public.rb_bak50_items as select * from public.rb_items;
    create table if not exists public.rb_bak50_stock as select * from public.rb_case_stock;
    create table if not exists public.rb_bak50_listings as select * from public.rb_listings;
    create table if not exists public.rb_bak50_ledger as select * from public.rb_ledger;
    create table if not exists public.rb_bak50_xp_log as select * from public.rb_xp_log;
    alter table public.rb_bak50_profiles enable row level security;
    alter table public.rb_bak50_items enable row level security;
    alter table public.rb_bak50_stock enable row level security;
    alter table public.rb_bak50_listings enable row level security;
    alter table public.rb_bak50_ledger enable row level security;
    alter table public.rb_bak50_xp_log enable row level security;
    revoke all on public.rb_bak50_profiles, public.rb_bak50_items, public.rb_bak50_stock, public.rb_bak50_listings,
                  public.rb_bak50_ledger, public.rb_bak50_xp_log from anon, authenticated;

    select coalesce(array_agg(distinct owner), '{}') into og from public.rb_items where item = 'tag:og';

    -- everything in progress and every bit of progress goes (one statement: nothing half done)
    truncate public.rb_offers, public.rb_listings, public.rb_trade_items, public.rb_trades, public.rb_duels,
             public.rb_rounds, public.rb_mem, public.rb_park, public.rb_mini, public.rb_mg, public.rb_flips,
             public.rb_golf, public.rb_golf_solo, public.rb_wave_runs, public.rb_wave_duels, public.rb_pawn,
             public.rb_rigs, public.rb_giveaway_entries, public.rb_items, public.rb_seen, public.rb_case_stock,
             public.rb_case_stats, public.rb_set_claims, public.rb_quest_claims, public.rb_requests, public.rb_inbox,
             public.rb_advent_claims, public.rb_xp_log, public.rb_wear, public.rb_ledger;
    if to_regclass('public.rb_deal_buys') is not null then execute 'truncate public.rb_deal_buys'; end if;
    if to_regclass('public.rb_rate_hits') is not null then execute 'truncate public.rb_rate_hits'; end if;
    update public.rb_giveaways set state = 'cancelled', ends_at = least(ends_at, now()) where state = 'live';

    update public.profiles
       set coins = public.rb_cfg('start_coins')::bigint, keys = public.rb_cfg('start_keys')::int,
           coin_min = 0, key_min = 0, day = current_date, day_coins = 0,
           spin_at = null, spin_prize = null, daily_at = null, scratch_at = null,
           streak = 0, streak_day = null, gold_keys = 0, og_event_at = null, gold_wheels = 0, rig_gold = false,
           xp = 0, level = 0, level_badge = -1, xp_day = null, xp_day_gain = 0, xp_day_src = '{}'::jsonb,
           xp_hr = null, xp_hr_src = '{}'::jsonb,
           equip = coalesce((select jsonb_object_agg(e.key, e.value) from jsonb_each(coalesce(equip, '{}'::jsonb)) e
                              where e.value #>> '{}' like 'prog:%'), '{}'::jsonb);

    -- OG players: the tag back, 1 500 coins and the coupon to level 5
    perform public.rb_og_give(x) from unnest(og) x;
    update public.profiles set coins = public.rb_cfg('og_start_coins')::bigint where id = any (og) and not bot;
    insert into public.rb_items (owner, item, origin) select x, 'coupon:og', 'og' from unnest(og) x
        join public.profiles p on p.id = x and not p.bot;
    insert into public.rb_seen (owner, item) select x, 'coupon:og' from unnest(og) x on conflict do nothing;

    insert into public.rb_ledger (owner, coins, keys, reason, ref)
        select id, coins::int, keys, 'reset', '5.0' from public.profiles;
    insert into public.rb_config (key, value) values ('reset_050', 1) on conflict (key) do update set value = 1;
end $$;

update public.rb_config set value = 2026112001 where key = 'min_build';

commit;
