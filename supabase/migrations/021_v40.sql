-- 4.0 guard, first part: what everyone owns before the update. The last part of this file compares and stops the
-- whole migration (nothing is kept) if anybody would lose an item, a coin or a key.
drop table if exists pg_temp.rb_guard021;
create temp table rb_guard021 on commit drop as
    select p.id, p.coins, p.keys,
           (select coalesce(array_agg(it.id::text || ':' || it.item order by it.id), '{}') from public.rb_items it
             where it.owner = p.id) as items
      from public.profiles p;

-- Rubenium 021 (4.0): the full release.
--   * Economy rebalance: every item priced again from clear bands (grey cheaper, Shiny ~200k, Titanium ~1M,
--     Gold 2-5M, Mythic 10-25M). Open market listings go back to their owners first. Quick-sell pays 35% of worth.
--   * Lockdown and live locks for every system (server-side), with safe refunds of anything running.
--   * Levels 0-100 with XP from games, golf, coinflip, trades, quests, online time; XP coupons; OG coupon to level 5.
--   * Coinflip: lobby first, items after; fair bot offers (and admin-made ones), 1 hour long.
--   * Roulette numbers, Tower, Keno and Limbo; 2048 and Minesweeper minigames with leaderboards.
--   * Notifications history, chat reactions, market search, trade summary, more deals and more sets.
-- Everything is in one transaction. A copy of every price and listing is kept in rb_bak021_* (see 021_down.sql).
-- Run it once in Supabase -> SQL Editor (after 020). Running it again changes nothing.

-- ================================================================ settings
insert into public.rb_config (key, value) values
    ('lockdown', 0), ('xp_day_cap', 2500), ('quick_worth_share', 0.35), ('price_epoch', extract(epoch from now())),
    ('golf_hole_total', 40), ('bot_flip_min', 60), ('bot_flips_max', 3), ('flip_setup_min', 10),
    ('deal_count', 8), ('mg_window_cap', 400)
on conflict (key) do nothing;
update public.rb_config set value = 0.35 where key = 'quick_worth_share';

-- ================================================================ copies kept for undo (only the first run makes them)
do $$ begin
    if not exists (select 1 from information_schema.tables where table_schema = 'public' and table_name = 'rb_bak021_catalog') then
        create table public.rb_bak021_catalog as select id, price, worth, weight, base_worth, value from public.rb_catalog;
        create table public.rb_bak021_listings as select * from public.rb_listings where state = 'open';
        create table public.rb_bak021_config as select * from public.rb_config;
        alter table public.rb_bak021_catalog enable row level security;
        alter table public.rb_bak021_listings enable row level security;
        alter table public.rb_bak021_config enable row level security;
    end if;
end $$;

-- ================================================================ live locks: every system can be locked on its own, or all at once
create table if not exists public.rb_features (
    name text primary key,
    parent text,
    locked boolean not null default false,
    at timestamptz, by_name text, note text
);
alter table public.rb_features enable row level security;
insert into public.rb_features (name, parent) values
    ('online', null), ('trading', 'online'), ('market', null), ('coinflip', 'online'), ('roulette', null),
    ('casino', null), ('minigames', null), ('golf', 'online'), ('wheel', null), ('scratch', null), ('advent', null),
    ('notifications', null), ('cases', null), ('shop', null), ('chat', 'online'), ('giveaways', null),
    ('quests', null), ('coupons', null), ('gifts', null)
on conflict (name) do nothing;

create or replace function public.rb_feature_on(f text) returns boolean
language sql stable security definer set search_path = '' as $$
    select coalesce(public.rb_cfg('lockdown'), 0) = 0
       and not exists (select 1 from public.rb_features x where x.locked
                          and (x.name = f or x.name = (select parent from public.rb_features y where y.name = f))) $$;

create or replace function public.rb_need_feature(f text) returns void
language plpgsql stable security definer set search_path = '' as $$
begin
    if coalesce(public.rb_cfg('lockdown'), 0) > 0 then raise exception 'rb_lockdown'; end if;
    if not public.rb_feature_on(f) then raise exception 'rb_feature_locked'; end if;
end $$;

-- the locks as the app sees them
create or replace function public.rb_locks() returns json
language sql stable security definer set search_path = '' as $$
    select json_build_object('lockdown', coalesce(public.rb_cfg('lockdown'), 0) > 0,
        'locked', coalesce((select json_agg(f.name order by f.name) from public.rb_features f
                             where not public.rb_feature_on(f.name)), '[]'::json)) $$;

-- Stop whatever of a system is running, with no winner and no loser: bets and items go back to their owners.
create or replace function public.rb_feature_cleanup(f text) returns json
language plpgsql security definer set search_path = '' as $$
declare r record; n integer := 0; fl public.rb_flips%rowtype; g public.rb_golf%rowtype; casino text[];
begin
    casino := array['blackjack', 'mines', 'rocket', 'timing', 'hilo', 'tower'];
    if f in ('trading', 'online', 'all') then
        for r in select id from public.rb_trades where state in ('asked', 'open') for update loop
            perform public.rb_trade_end(r.id, 'lockdown'); n := n + 1;
        end loop;
    end if;
    if f in ('coinflip', 'online', 'all') then
        for fl in select * from public.rb_flips where state in ('setup', 'open', 'joined', 'locked') for update loop
            perform public.rb_flip_free(fl, 'lockdown'); n := n + 1;
            if fl.a is not null then perform public.rb_notice(fl.a, 'cancelled', jsonb_build_object('what', 'coinflip')); end if;
            if fl.b is not null then perform public.rb_notice(fl.b, 'cancelled', jsonb_build_object('what', 'coinflip')); end if;
        end loop;
    end if;
    if f in ('golf', 'online', 'all') then
        for g in select * from public.rb_golf where state in ('open', 'asked', 'live') for update loop
            update public.rb_golf set state = 'cancelled', why = 'lockdown', winner = null where id = g.id;
            if g.bet > 0 then
                perform public.rb_pay(g.a, g.bet, 0, 'golf_back', g.id::text);
                if g.state = 'live' and g.b is not null then perform public.rb_pay(g.b, g.bet, 0, 'golf_back', g.id::text); end if;
            end if;
            perform public.rb_notice(x, 'cancelled', jsonb_build_object('what', 'golf')) from unnest(array[g.a, g.b]) x where x is not null;
            n := n + 1;
        end loop;
    end if;
    if f in ('casino', 'roulette', 'all') then
        for r in select * from public.rb_rounds where open and game = any (casino) and bet > 0 for update loop
            update public.rb_rounds set open = false, paid = r.bet, secret = r.secret || '{"void": true}'::jsonb where id = r.id;
            perform public.rb_pay(r.owner, r.bet, 0, 'refund', r.game);
            n := n + 1;
        end loop;
    end if;
    if f in ('minigames', 'all') then
        update public.rb_mini set open = false where open;
        update public.rb_park set open = false where open;
        update public.rb_mem set open = false where open;
        update public.rb_mg set open = false, void = true where open;
        for r in select * from public.rb_duels where state in ('asked', 'on') for update loop
            update public.rb_duels set state = 'cancelled', why = 'lockdown' where id = r.id;
            if r.bet > 0 then
                perform public.rb_pay(r.a, r.bet, 0, 'duel_back', r.id::text);
                if r.state <> 'asked' and r.b is not null then perform public.rb_pay(r.b, r.bet, 0, 'duel_back', r.id::text); end if;
            end if;
            n := n + 1;
        end loop;
    end if;
    return json_build_object('stopped', n);
end $$;

-- the admin: lock or unlock one system now
create or replace function public.rb_admin_feature(name text, lock boolean, note text) returns json
language plpgsql security definer set search_path = '' as $$
declare me public.profiles%rowtype; res json := '{}'::json;
begin
    perform public.rb_need_admin();
    select * into me from public.profiles where id = auth.uid();
    if not exists (select 1 from public.rb_features f where f.name = rb_admin_feature.name) then raise exception 'rb_bad_choice'; end if;
    update public.rb_features f set locked = coalesce(lock, false), at = now(), by_name = me.username, note = left(rb_admin_feature.note, 200)
     where f.name = rb_admin_feature.name;
    if coalesce(lock, false) then res := public.rb_feature_cleanup(name); end if;
    perform public.rb_log('feature', name, jsonb_build_object('locked', lock, 'note', note, 'result', res));
    return public.rb_admin_features();
end $$;

-- LOCKDOWN: everything stops at once, running games are given back; lifting it opens everything again
create or replace function public.rb_admin_lockdown(lock boolean) returns json
language plpgsql security definer set search_path = '' as $$
declare res json := '{}'::json;
begin
    perform public.rb_need_admin();
    update public.rb_config set value = case when coalesce(lock, false) then 1 else 0 end where key = 'lockdown';
    if coalesce(lock, false) then res := public.rb_feature_cleanup('all'); end if;
    perform public.rb_log('lockdown', null, jsonb_build_object('locked', lock, 'result', res));
    return public.rb_admin_features();
end $$;

create or replace function public.rb_admin_features() returns json
language plpgsql stable security definer set search_path = '' as $$
begin
    perform public.rb_need_admin();
    return json_build_object('lockdown', coalesce(public.rb_cfg('lockdown'), 0) > 0,
        'features', (select json_agg(json_build_object('name', f.name, 'parent', f.parent, 'locked', f.locked,
                                                       'on', public.rb_feature_on(f.name), 'at', f.at, 'by', f.by_name, 'note', f.note)
                                     order by f.parent nulls first, f.name) from public.rb_features f),
        'log', coalesce((select json_agg(x) from (select a.at, a.action, a.target, a.detail,
                                                         (select username from public.profiles where id = a.admin) as who
                                                    from public.rb_audit a where a.action in ('feature', 'lockdown')
                                                   order by a.at desc limit 20) x), '[]'::json));
end $$;

-- ================================================================ economy: price bands
-- Badges are priced inside a band per rarity (Common / Rare / Epic / Legendary / Mythic) and class
-- (Basic, Painted, Shiny, Titanium, Gold, Prismatic). Inside a band, the more detailed design and the rarer colour
-- cost more. Bands never overlap the next class, so a Shiny is always worth more than any Painted of its rarity.
create table if not exists public.rb_price_bands (
    kind text not null, rarity text not null, cls integer not null, lo bigint not null, hi bigint not null,
    primary key (kind, rarity, cls)
);
alter table public.rb_price_bands enable row level security;
insert into public.rb_price_bands (kind, rarity, cls, lo, hi) values
    ('badge', 'standard', 0, 650, 1000),        ('badge', 'rare', 0, 2000, 3000),
    ('badge', 'special', 0, 5400, 8000),        ('badge', 'epic', 0, 14000, 20500),
    ('badge', 'standard', 1, 1400, 2200),       ('badge', 'rare', 1, 4200, 6500),
    ('badge', 'special', 1, 11300, 17500),      ('badge', 'epic', 1, 42000, 66000),
    ('badge', 'standard', 2, 25000, 35000),     ('badge', 'rare', 2, 45000, 65000),
    ('badge', 'special', 2, 90000, 130000),     ('badge', 'epic', 2, 170000, 240000),
    ('badge', 'special', 3, 750000, 950000),    ('badge', 'epic', 3, 1000000, 1250000),
    ('badge', 'standard', 4, 2000000, 2600000), ('badge', 'rare', 4, 2500000, 3200000),
    ('badge', 'special', 4, 3200000, 4000000),  ('badge', 'epic', 4, 4000000, 5000000),
    ('badge', 'exotic', 3, 10000000, 14000000), ('badge', 'exotic', 5, 14000000, 19000000),
    ('badge', 'exotic', 4, 20000000, 25000000)
on conflict (kind, rarity, cls) do update set lo = excluded.lo, hi = excluded.hi;

-- Every price again. Badges: from their band. Looks (balls, lines, fonts, banners, frames, themes): from their 3.2
-- price, grey a third cheaper, coloured balls and lines 10% cheaper. Items the shop sells keep price = worth.
create or replace function public.rb_price_all() returns void
language plpgsql security definer set search_path = '' as $$
declare c public.rb_catalog%rowtype; rank_d double precision; rank_v double precision; f double precision; t double precision;
        b public.rb_price_bands%rowtype; adj double precision;
        cols text[] := array['grey', 'blue', 'green', 'red', 'yellow', 'orange', 'brown', 'teal', 'lava', 'purple', 'sky',
                             'lime', 'pink', 'beam', 'hotpink', 'royal', 'black', 'white', 'gold', 'prime'];
begin
    update public.rb_catalog k set base_worth = public.rb_worth_base(k) where k.base_worth is null;
    for c in select * from public.rb_catalog where kind not in ('prog', 'tag', 'coupon') loop
        select coalesce((select count(*) from (select distinct x.base from public.rb_catalog x
                                                where x.kind = c.kind and x.rarity = c.rarity and x.cls = c.cls
                                                  and public.rb_detail(x.kind, x.base) < public.rb_detail(c.kind, c.base)) y)::double precision
                        / nullif((select count(distinct x.base) - 1 from public.rb_catalog x
                                   where x.kind = c.kind and x.rarity = c.rarity and x.cls = c.cls), 0), 0.5) into rank_d;
        rank_v := coalesce((array_position(cols, c.variant) - 1)::double precision / (array_length(cols, 1) - 1), 0.5);
        f := (0.85 + 0.40 * rank_d) * (0.95 + 0.10 * rank_v);
        select * into b from public.rb_price_bands pb where pb.kind = c.kind and pb.rarity = c.rarity and pb.cls = c.cls;
        if found then
            t := greatest(0, least(1, (f - 0.8075) / 0.505));
            update public.rb_catalog set worth = public.rb_nice(b.lo + (b.hi - b.lo) * t), weight = 1.0 / f where id = c.id;
        else
            adj := case when c.kind in ('ball', 'line') and c.variant = 'grey' then 0.65
                        when c.kind in ('ball', 'line') and c.variant not in ('black', 'white', '') then 0.9
                        else 1 end;
            update public.rb_catalog set worth = greatest(5, public.rb_nice(c.base_worth * f * adj)), weight = 1.0 / f where id = c.id;
        end if;
    end loop;
    update public.rb_catalog set worth = 0, weight = 1 where kind in ('prog', 'tag', 'coupon');
    update public.rb_catalog set price = worth where price is not null and kind not in ('prog', 'tag', 'coupon');
end $$;

-- quick-sell: 35% of what the item is worth (the market always pays more); shop items: never above half what was paid
create or replace function public.rb_quick_value(who uuid, it public.rb_items) returns integer
language plpgsql stable security definer set search_path = '' as $$
declare c public.rb_catalog%rowtype; pay bigint; paid integer;
begin
    select * into c from public.rb_catalog where id = it.item;
    if not found or not c.tradeable or c.kind in ('prog', 'tag', 'coupon') then return 0; end if;
    pay := floor(coalesce(c.worth, public.rb_worth_base(c)) * coalesce(public.rb_cfg('quick_worth_share'), 0.35));
    if it.origin = 'shop' then
        select -l.coins into paid from public.rb_ledger l
         where l.owner = who and l.reason = 'shop' and l.ref = it.item and l.at <= it.got_at + interval '1 minute'
         order by l.id desc limit 1;
        pay := least(pay, floor(coalesce(paid, c.worth) * public.rb_cfg('quick_shop_share')));
    end if;
    return greatest(1, least(2000000000, pay))::int;
end $$;

-- the market estimate only counts sales made after the new prices
create or replace function public.rb_estimate(what text) returns integer
language sql stable security definer set search_path = '' as $$
    select least(200000000, greatest(
        coalesce((select percentile_disc(0.5) within group (order by s.price)
                    from (select l.price from public.rb_listings l
                           where l.what = rb_estimate.what and l.state = 'sold'
                             and l.sold_at > to_timestamp(coalesce(public.rb_cfg('price_epoch'), 0))
                           order by l.sold_at desc limit 15) s), 0),
        coalesce(public.rb_worth(what), 0)))::int $$;

-- ================================================================ every open listing goes back to its owner, before prices move
do $$ declare l public.rb_listings%rowtype; n integer := 0; begin
    if not exists (select 1 from public.rb_config where key = 'reset_021_listings') then
        for l in select * from public.rb_listings where state = 'open' for update loop
            update public.rb_listings set state = 'cancelled' where id = l.id;
            update public.rb_items set locked = null where id = l.item and locked = 'market:' || l.id;
            update public.rb_offers set state = 'gone' where listing = l.id and state = 'open';
            perform public.rb_notice(l.seller, 'listing_back', jsonb_build_object('item', l.what, 'price', l.price));
            n := n + 1;
        end loop;
        insert into public.rb_audit (admin, action, target, detail) values (null, 'update_021', 'listings', jsonb_build_object('returned', n));
        insert into public.rb_config (key, value) values ('reset_021_listings', 1);
    end if;
end $$;

-- ================================================================ more deals of the day, more varied
create or replace function public.rb_deal_list() returns table (item text, pct integer)
language sql stable security definer set search_path = '' as $$
    with pool as (
        select c.id, c.kind, row_number() over (partition by c.kind order by md5(c.id || public.rb_today()::text)) k
          from public.rb_catalog c
         where c.price is not null and not c.limited and c.price <= 400000
           and c.kind in ('badge', 'ball', 'line', 'font', 'theme', 'banner', 'frame')
           and not (c.kind = 'badge' and (c.cls >= 4 or c.rarity = 'exotic')))
    select p.id, (15 + (abs(hashtext(p.id || public.rb_today()::text)) % 5) * 5)::int
      from pool p where p.k <= case when p.kind = 'badge' then 3 else 1 end
     order by md5(p.id || 'd' || public.rb_today()::text)
     limit coalesce(public.rb_cfg('deal_count'), 8)::int $$;

-- ================================================================ more sets (Collection)
create or replace function public.rb_set_rows(who uuid)
returns table (set_id text, goal integer, have integer, coins integer, keys integer, claimed boolean)
language sql stable security definer set search_path = '' as $$
    with mine as (select distinct c.id, c.kind, c.base, c.rarity, c.cls, c.variant, c.limited from public.rb_items it
                    join public.rb_catalog c on c.id = it.item where it.owner = who),
         b as (select * from mine where kind = 'badge'),
         sets (set_id, goal, have, coins, keys) as (values
            ('row_standard', 12, (select count(distinct base) from b where rarity = 'standard')::int, 3000, 2),
            ('row_rare',     12, (select count(distinct base) from b where rarity = 'rare')::int, 8000, 4),
            ('row_special',  12, (select count(distinct base) from b where rarity = 'special')::int, 20000, 6),
            ('row_epic',     12, (select count(distinct base) from b where rarity = 'epic')::int, 60000, 12),
            ('row_exotic',    6, (select count(distinct base) from b where rarity = 'exotic')::int, 1500000, 60),
            ('rainbow',       8, (select coalesce(max(n), 0) from (select count(distinct variant) n from b
                                    where cls = 1 group by base) x)::int, 4000, 2),
            ('shiny5',        5, (select count(*) from b where cls = 2)::int, 40000, 8),
            ('titanium3',     3, (select count(*) from b where cls = 3)::int, 150000, 15),
            ('gold1',         1, (select count(*) from b where cls = 4)::int, 300000, 20),
            ('banners6',      6, (select count(*) from mine where kind = 'banner')::int, 3000, 3),
            ('frames5',       5, (select count(*) from mine where kind = 'frame')::int, 3000, 3),
            ('themes4',       4, (select count(*) from mine where kind = 'theme')::int, 2500, 2),
            ('balls12',      12, (select count(distinct base) from mine where kind = 'ball')::int, 4000, 3),
            ('lines12',      12, (select count(distinct base) from mine where kind = 'line')::int, 4000, 3),
            ('fonts5',        5, (select count(distinct base) from mine where kind = 'font')::int, 2000, 2),
            ('winter4',       4, (select count(*) from mine where limited)::int, 6000, 5))
    select r.set_id, r.goal, least(r.have, r.goal), r.coins, r.keys,
           exists (select 1 from public.rb_set_claims s where s.owner = who and s.set_id = r.set_id)
      from sets r $$;

-- ================================================================ levels and XP
-- Level 0 to 100. Going from level L to L+1 costs 50 + 12 L + 0.6 L^2 XP: level 1 after one or two games, level 5
-- after about 400 XP, level 100 after 261 000 XP (with the daily cap of 2 500, at the very least 105 days of play).
alter table public.profiles add column if not exists xp bigint not null default 0;
alter table public.profiles add column if not exists level integer not null default 0;
alter table public.profiles add column if not exists level_badge integer not null default -1;
alter table public.profiles add column if not exists xp_day date;
alter table public.profiles add column if not exists xp_day_gain integer not null default 0;
alter table public.profiles add column if not exists xp_day_src jsonb not null default '{}'::jsonb;

create table if not exists public.rb_xp_log (
    id bigserial primary key,
    owner uuid not null references public.profiles (id) on delete cascade,
    amount integer not null, source text not null, ref text, level_after integer not null,
    at timestamptz not null default now()
);
alter table public.rb_xp_log enable row level security;
create index if not exists rb_xp_log_owner on public.rb_xp_log (owner, at desc);

create or replace function public.rb_xp_need(l integer) returns integer
language sql immutable set search_path = '' as $$ select (50 + 12 * l + floor(0.6 * l * l))::int $$;

-- the XP needed to reach level l from 0, worked out once
create table if not exists public.rb_levels (level integer primary key, total bigint not null);
alter table public.rb_levels enable row level security;
insert into public.rb_levels (level, total)
    select l, coalesce((select sum(public.rb_xp_need(k)) from generate_series(0, l - 1) k), 0) from generate_series(0, 100) l
on conflict (level) do update set total = excluded.total;

create or replace function public.rb_xp_total(l integer) returns bigint
language sql stable security definer set search_path = '' as $$
    select total from public.rb_levels where level = greatest(0, least(l, 100)) $$;

create or replace function public.rb_level_of(x bigint) returns integer
language sql stable security definer set search_path = '' as $$
    select coalesce(max(level), 0) from public.rb_levels where total <= x $$;

-- what one source may give a day (a source not listed is only held by the daily total)
create or replace function public.rb_xp_cap(src text) returns integer
language sql immutable set search_path = '' as $$
    select case src when 'casino' then 600 when 'minigames' then 900 when 'cases' then 200 when 'golf' then 600
                    when 'coinflip' then 300 when 'trading' then 150 when 'online' then 300 when 'wheel' then 60
                    when 'quests' then 600 else 100000 end $$;

-- Give XP. capped = counts towards the daily limits (all play does; coupons, the advent calendar and admins do not).
-- Returns what was really given. Level-ups are told to the player.
create or replace function public.rb_xp_add(who uuid, amount integer, src text, ref text, capped boolean default true) returns integer
language plpgsql security definer set search_path = '' as $$
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
end $$;

create or replace function public.rb_xp_json(p public.profiles) returns json
language sql stable set search_path = '' as $$
    select json_build_object('xp', p.xp, 'level', p.level,
        'into', p.xp - public.rb_xp_total(p.level),
        'need', case when p.level >= 100 then 0 else public.rb_xp_need(p.level) end,
        'badge', case when p.level_badge >= 0 and p.level_badge <= p.level then p.level_badge else (p.level / 5) * 5 end,
        'today', case when p.xp_day = current_date then p.xp_day_gain else 0 end,
        'cap', coalesce(public.rb_cfg('xp_day_cap'), 2500)) $$;

create or replace function public.rb_xp_me() returns json
language plpgsql stable security definer set search_path = '' as $$
declare p public.profiles%rowtype;
begin
    select * into p from public.profiles where id = auth.uid();
    if not found then raise exception 'rb_not_logged_in'; end if;
    return public.rb_xp_json(p);
end $$;

-- the level badge shown on the profile: any unlocked one (every 5 levels), or -1 for the newest
create or replace function public.rb_level_badge_set(which integer) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype;
begin
    p := public.rb_lock_me();
    if which is null or (which <> -1 and (which < 0 or which > 100 or which % 5 <> 0 or which > p.level)) then
        raise exception 'rb_bad_choice';
    end if;
    update public.profiles set level_badge = which where id = p.id returning * into p;
    return public.rb_xp_json(p);
end $$;

-- ---------------------------------------------------------------- where XP comes from (all decided here, never by the app)
-- every finished round: casino bets, minigames, cases, the wheel and the scratch card
create or replace function public.rb_rounds_xp() returns trigger
language plpgsql security definer set search_path = '' as $$
declare amt integer := 0; src text;
begin
    if new.open then return new; end if;
    if tg_op = 'UPDATE' and not old.open then return new; end if;               -- counted once, when it ends
    if coalesce((new.secret ->> 'void')::boolean, false) then return new; end if;
    if new.game in ('blackjack', 'mines', 'rocket', 'timing', 'hilo', 'tower', 'roulette', 'dice', 'plinko', 'keno', 'limbo') then
        if new.bet < 10 then return new; end if;
        src := 'casino'; amt := least(25, 3 + new.bet / 40);
    elsif new.game in ('mini', 'park', 'memory', 'tap', 'g2048', 'sweeper') then
        if coalesce(new.paid, 0) <= 0 then return new; end if;              -- a game thrown away gives nothing
        src := 'minigames'; amt := least(45, 10 + new.paid / 6);
    elsif new.game like 'case:%' then
        src := 'cases'; amt := 8;
    elsif new.game in ('spin', 'scratch') then
        src := 'wheel'; amt := 15;
    else
        return new;
    end if;
    perform public.rb_xp_add(new.owner, amt, src, new.game, true);
    return new;
end $$;
drop trigger if exists rb_rounds_xp on public.rb_rounds;
create trigger rb_rounds_xp after insert or update of open on public.rb_rounds for each row execute function public.rb_rounds_xp();

-- a golf match played to the end: 40 each, 30 more for the winner (a forfeit in the first hole gives nothing)
create or replace function public.rb_golf_xp() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    if new.state = 'done' and old.state = 'live' and new.b is not null and (new.why <> 'forfeit' or new.hole > 1) then
        perform public.rb_xp_add(new.a, 40 + case when new.winner = new.a then 30 else 0 end, 'golf', new.id::text, true);
        perform public.rb_xp_add(new.b, 40 + case when new.winner = new.b then 30 else 0 end, 'golf', new.id::text, true);
    end if;
    return new;
end $$;
drop trigger if exists rb_golf_xp on public.rb_golf;
create trigger rb_golf_xp after update of state on public.rb_golf for each row execute function public.rb_golf_xp();

-- a trade done: 15 each
create or replace function public.rb_trade_xp() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    if new.state = 'done' and old.state <> 'done' then
        perform public.rb_xp_add(new.a, 15, 'trading', new.id::text, true);
        perform public.rb_xp_add(new.b, 15, 'trading', new.id::text, true);
    end if;
    return new;
end $$;
drop trigger if exists rb_trade_xp on public.rb_trades;
create trigger rb_trade_xp after update of state on public.rb_trades for each row execute function public.rb_trade_xp();

-- quests and sets
create or replace function public.rb_claim_xp() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
    perform public.rb_xp_add(new.owner, case when tg_table_name = 'rb_set_claims' then 150 else 60 end, 'quests', tg_table_name, true);
    return new;
end $$;
drop trigger if exists rb_quest_xp on public.rb_quest_claims;
create trigger rb_quest_xp after insert on public.rb_quest_claims for each row execute function public.rb_claim_xp();
drop trigger if exists rb_set_xp on public.rb_set_claims;
create trigger rb_set_xp after insert on public.rb_set_claims for each row execute function public.rb_claim_xp();

-- ================================================================ XP coupons
-- Untradeable items with real XP inside. value = the XP. The OG coupon fills up to level 5.
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls) values
    ('coupon:common', 'coupon', 'common', '', 'standard', null, 150, false, 0),
    ('coupon:uncommon', 'coupon', 'uncommon', '', 'rare', null, 400, false, 0),
    ('coupon:rare', 'coupon', 'rare', '', 'special', null, 1000, false, 0),
    ('coupon:epic', 'coupon', 'epic', '', 'epic', null, 2500, false, 0),
    ('coupon:og', 'coupon', 'og', '', 'exotic', null, 0, false, 0)
on conflict (id) do nothing;

create or replace function public.rb_coupon_pick(odds integer[]) returns text
language sql security definer set search_path = '' as $$
    select (array['coupon:common', 'coupon:uncommon', 'coupon:rare', 'coupon:epic'])[public.rb_roll(odds) + 1] $$;

create or replace function public.rb_coupon_use(item_id uuid, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; it public.rb_items%rowtype; c public.rb_catalog%rowtype; amt integer; q public.profiles%rowtype;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    perform public.rb_need_feature('coupons');
    select * into it from public.rb_items where id = item_id and owner = p.id for update;
    if not found or it.locked is not null then raise exception 'rb_item_locked'; end if;
    select * into c from public.rb_catalog where id = it.item;
    if c.kind <> 'coupon' then raise exception 'rb_bad_choice'; end if;
    amt := case when c.id = 'coupon:og' then greatest(public.rb_xp_total(5) - p.xp, 150)::int else c.value end;
    delete from public.rb_items where id = it.id;
    perform public.rb_xp_add(p.id, amt, 'coupon', c.id, false);
    select * into q from public.profiles where id = p.id;
    return public.rb_remember(p.id, req, jsonb_build_object('item', c.id, 'xp', amt, 'level_from', p.level, 'level', q.level,
                                                            'xp_from', p.xp, 'info', public.rb_xp_json(q)));
end $$;

-- the OG thank-you: every holder of the OG tag gets one OG coupon, once
do $$ declare r record; begin
    if not exists (select 1 from public.rb_config where key = 'reset_021_og') then
        for r in select distinct it.owner from public.rb_items it join public.profiles p on p.id = it.owner
                  where it.item = 'tag:og' and not p.bot loop
            perform public.rb_give(r.owner, 'coupon:og', 'og');
            perform public.rb_notice(r.owner, 'og_coupon', '{}'::jsonb);
        end loop;
        insert into public.rb_config (key, value) values ('reset_021_og', 1);
    end if;
end $$;

-- ================================================================ minigame pay grows with the level (up to +40% at level 100)
create or replace function public.rb_level_mult(who uuid) returns numeric
language sql stable security definer set search_path = '' as $$
    select 1 + 0.004 * coalesce((select level from public.profiles where id = who), 0) $$;

create or replace function public.rb_game_pay(who uuid, g text, pay integer) returns integer
language plpgsql stable security definer set search_path = '' as $$
declare w json := public.rb_game_window(who, g); n integer := (w ->> 'rounds')::int; fr integer := (w ->> 'full')::int;
        m numeric := public.rb_level_mult(who);
begin
    pay := round(pay * coalesce(public.rb_cfg('game_pay_mult'), 1) * m);
    if n >= fr * 2 then pay := pay / 4; elsif n >= fr then pay := pay / 2; end if;
    return greatest(0, least(pay, floor((w ->> 'cap')::int * m)::int - (w ->> 'paid')::int));
end $$;

-- ================================================================ the admin and XP
create or replace function public.rb_admin_xp(name text, delta integer, reason text) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; lv integer;
begin
    perform public.rb_need_admin();
    select * into p from public.profiles where lower(username) = lower(name) for update;
    if not found then raise exception 'rb_no_such_user'; end if;
    if delta is null or delta = 0 or abs(delta) > 300000 then raise exception 'rb_bad_choice'; end if;
    lv := public.rb_level_of(greatest(0, p.xp + delta));
    update public.profiles set xp = greatest(0, xp + delta), level = lv where id = p.id;
    insert into public.rb_xp_log (owner, amount, source, ref, level_after) values (p.id, delta, 'admin', left(reason, 80), lv);
    perform public.rb_log('xp', p.username, jsonb_build_object('delta', delta, 'reason', reason, 'from', p.xp, 'level', lv));
    if lv > p.level then perform public.rb_notice(p.id, 'level_up', jsonb_build_object('level', lv, 'from', p.level)); end if;
    return public.rb_admin_xp_view(p.username);
end $$;

create or replace function public.rb_admin_xp_view(name text) returns json
language plpgsql stable security definer set search_path = '' as $$
declare p public.profiles%rowtype;
begin
    perform public.rb_need_admin();
    select * into p from public.profiles where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    return json_build_object('name', p.username, 'info', public.rb_xp_json(p),
        'sources', case when p.xp_day = current_date then p.xp_day_src else '{}'::jsonb end,
        'log', coalesce((select json_agg(json_build_object('at', l.at, 'amount', l.amount, 'source', l.source, 'ref', l.ref,
                                                            'level', l.level_after) order by l.id desc)
                           from (select * from public.rb_xp_log where owner = p.id order by id desc limit 60) l), '[]'::json));
end $$;

-- who earns XP suspiciously: at the daily cap several days running, or lots of XP from admins or coupons
create or replace function public.rb_admin_xp_watch() returns json
language plpgsql stable security definer set search_path = '' as $$
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
end $$;

-- ================================================================ cases: a few big ones unlock with the first levels
alter table public.rb_cases add column if not exists min_level integer not null default 0;
update public.rb_cases set min_level = case id when 'cosmos' then 2 when 'shiny' then 3 when 'vault' then 4 when 'mythic' then 5 else 0 end;

create or replace function public.rb_case_buy(which text, how_many integer, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; c public.rb_cases%rowtype; res jsonb; cost integer; have integer;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    perform public.rb_need_feature('cases');
    select * into c from public.rb_cases where id = which;
    if not found then raise exception 'rb_no_case'; end if;
    if c.limited then raise exception 'rb_not_for_sale'; end if;
    if p.level < c.min_level then raise exception 'rb_level_needed'; end if;
    how_many := coalesce(how_many, 1);
    if how_many < 1 or how_many > coalesce(public.rb_cfg('case_buy_max'), 10) then raise exception 'rb_bad_choice'; end if;
    cost := c.price * how_many;
    perform public.rb_pay(p.id, -cost, 0, 'case_buy', c.id || ':' || how_many);
    perform public.rb_stock_add(p.id, c.id, how_many);
    select n into have from public.rb_case_stock where owner = p.id and case_id = c.id;
    return public.rb_remember(p.id, req, jsonb_build_object('case', c.id, 'stock', have, 'coins', p.coins - cost));
end $$;

-- opening: as before, plus a 4% chance of a bonus XP coupon on top of the drop
create or replace function public.rb_open_case(which text, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; c public.rb_cases%rowtype; res jsonb; d record; new_id uuid; have integer;
        key_cost integer; cp text;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    perform public.rb_need_feature('cases');
    select * into c from public.rb_cases where id = which;
    if not found then raise exception 'rb_no_case'; end if;
    select n into have from public.rb_case_stock where owner = p.id and case_id = c.id for update;
    if coalesce(have, 0) < 1 then raise exception 'rb_case_none'; end if;
    key_cost := case when public.rb_case_keyless(c) then 0 else 1 end;
    if p.keys < key_cost then raise exception 'rb_no_key'; end if;
    update public.rb_case_stock set n = n - 1 where owner = p.id and case_id = c.id;
    have := have - 1;
    perform public.rb_pay(p.id, 0, -key_cost, 'case', c.id);
    d := public.rb_case_drop(c);
    if d.tier = 0 then
        perform public.rb_pay(p.id, d.coins, 0, 'case_coins', c.id);
    else
        new_id := public.rb_give(p.id, d.item, 'case:' || c.id);
    end if;
    if public.rb_rand() < 0.04 then
        cp := public.rb_coupon_pick(array[7000, 2200, 700, 100]);
        perform public.rb_give(p.id, cp, 'case:' || c.id);
    end if;
    insert into public.rb_case_stats as st (owner, case_id, opens) values (p.id, c.id, 1)
        on conflict (owner, case_id) do update set opens = st.opens + 1;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'case:' || c.id, c.price,
        jsonb_build_object('item', d.item, 'tier', d.tier, 'coupon', cp), false,
        d.coins + coalesce((select worth from public.rb_catalog where id = d.item), 0));
    return public.rb_remember(p.id, req, jsonb_build_object('tier', d.tier, 'cls', d.klass, 'item', d.item, 'id', new_id,
        'won', d.coins, 'coins', p.coins + d.coins, 'keys', p.keys - key_cost, 'stock', have, 'case', c.id, 'coupon', cp));
end $$;

-- ================================================================ scratch card: fairer odds, prizes paid at once, odds readable by the app
create or replace function public.rb_scratch_odds() returns json
language sql immutable set search_path = '' as $$
    select json_build_array(
        json_build_object('tier', 'standard', 'pct', 30, 'prize', '80-160 coins'),
        json_build_object('tier', 'rare', 'pct', 27, 'prize', '220-420 coins'),
        json_build_object('tier', 'special', 'pct', 20, 'prize', '1 key + Common XP coupon'),
        json_build_object('tier', 'epic', 'pct', 14, 'prize', '2 keys + Uncommon XP coupon'),
        json_build_object('tier', 'exotic', 'pct', 6, 'prize', '2 500 coins + Rare XP coupon'),
        json_build_object('tier', 'golden', 'pct', 3, 'prize', 'Golden Wheel + Epic XP coupon')) $$;

create or replace function public.rb_scratch() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; roll double precision; tier text; c integer := 0; k integer := 0; g integer := 0; cp text;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('scratch');
    if p.scratch_at is not null and now() < p.scratch_at + make_interval(hours => public.rb_cfg('scratch_hours')::int) then
        raise exception 'rb_wait';
    end if;
    roll := case when p.rig_gold then 0.999 else public.rb_rand() end;
    if p.rig_gold then update public.profiles set rig_gold = false where id = p.id; end if;
    if roll < 0.30 then tier := 'standard'; c := 80 + floor(public.rb_rand() * 81)::int;
    elsif roll < 0.57 then tier := 'rare'; c := 220 + floor(public.rb_rand() * 201)::int;
    elsif roll < 0.77 then tier := 'special'; k := 1; cp := 'coupon:common';
    elsif roll < 0.91 then tier := 'epic'; k := 2; cp := 'coupon:uncommon';
    elsif roll < 0.97 then tier := 'exotic'; c := 2500; cp := 'coupon:rare';
    else tier := 'golden'; g := 1; cp := 'coupon:epic'; end if;
    update public.profiles set scratch_at = now(), gold_wheels = gold_wheels + g where id = p.id;
    perform public.rb_pay(p.id, c, k, 'scratch', tier);
    if cp is not null then perform public.rb_give(p.id, cp, 'scratch'); end if;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        values (p.id, 'scratch', 0, jsonb_build_object('tier', tier, 'keys', k, 'coupon', cp), false, c);
    return jsonb_build_object('rarity', tier, 'coins_won', c, 'keys_won', k, 'coins', p.coins + c, 'keys', p.keys + k,
                              'gold_wheel', g = 1, 'coupon', cp, 'next', public.rb_cfg('scratch_hours')::int * 3600);
end $$;

-- ================================================================ the free wheel: paid the moment it stops (nothing left to collect)
create or replace function public.rb_spin_odds() returns json
language sql immutable set search_path = '' as $$
    select json_build_object('slots', json_build_array(40, 75, 120, 180, 300, 500, 1200, -1, -2, -3),
                             'odds', json_build_array(1950, 1950, 1800, 1200, 750, 400, 180, 770, 500, 500)) $$;

create or replace function public.rb_spin_pay(p public.profiles, prize jsonb) returns void
language plpgsql security definer set search_path = '' as $$
declare gold boolean := coalesce((prize ->> 'gold')::boolean, false);
begin
    update public.profiles set spin_prize = null, gold_wheels = gold_wheels + case when gold then 1 else 0 end where id = p.id;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'spin', 0,
        jsonb_build_object('keys', (prize ->> 'won_keys')::int, 'gold', gold, 'coupon', prize ->> 'coupon'), false, (prize ->> 'won')::int);
    perform public.rb_pay(p.id, (prize ->> 'won')::int, (prize ->> 'won_keys')::int, 'spin', null);
    if prize ->> 'coupon' is not null then perform public.rb_give(p.id, prize ->> 'coupon', 'spin'); end if;
end $$;

create or replace function public.rb_spin() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r integer; prize jsonb; q public.profiles%rowtype;
        slots integer[] := array[40, 75, 120, 180, 300, 500, 1200, -1, -2, -3];   -- -1 = a key, -2 = the Golden Wheel, -3 = an XP coupon
        odds  integer[] := array[1950, 1950, 1800, 1200, 750, 400, 180, 770, 500, 500];
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('wheel');
    if p.spin_prize is not null then perform public.rb_spin_pay(p, p.spin_prize); end if;     -- a prize from an old app: paid now
    if p.spin_at is not null and now() < p.spin_at + make_interval(hours => public.rb_cfg('spin_hours')::int) then
        raise exception 'rb_too_soon';
    end if;
    r := case when p.rig_gold then 8 else public.rb_roll(odds) end;
    if p.rig_gold then update public.profiles set rig_gold = false where id = p.id; end if;
    prize := jsonb_build_object('slot', r, 'won', greatest(slots[r + 1], 0), 'won_keys', case when slots[r + 1] = -1 then 1 else 0 end,
                                'gold', slots[r + 1] = -2,
                                'coupon', case when slots[r + 1] = -3 then public.rb_coupon_pick(array[6500, 2700, 700, 100]) end);
    update public.profiles set spin_at = now() where id = p.id;
    perform public.rb_spin_pay(p, prize);
    select * into q from public.profiles where id = p.id;
    return prize || jsonb_build_object('collected', true, 'coins', q.coins, 'keys', q.keys, 'gold_wheels', q.gold_wheels);
end $$;

-- the old collect call: nothing to do any more, or pays a prize an old app left
create or replace function public.rb_spin_collect() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; q public.profiles%rowtype;
begin
    p := public.rb_lock_me();
    if p.spin_prize is not null then perform public.rb_spin_pay(p, p.spin_prize); end if;
    select * into q from public.profiles where id = p.id;
    return jsonb_build_object('coins', q.coins, 'keys', q.keys, 'gold_wheels', q.gold_wheels);
end $$;

-- prizes left waiting by an older app are paid now
do $$ declare p public.profiles%rowtype; begin
    for p in select * from public.profiles where spin_prize is not null for update loop
        perform public.rb_spin_pay(p, p.spin_prize);
    end loop;
end $$;

-- ================================================================ advent: everyone can look from today; door 1 is a gift for all
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, limited) values
    ('frame:yuletide', 'frame', 'yuletide', '', 'epic', null, 15000, true, 0, true)
on conflict (id) do nothing;
update public.rb_advent set items = '{frame:yuletide}', coins = 500 where day = 1;

create or replace function public.rb_advent() returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); p public.profiles%rowtype; today integer := public.rb_advent_day();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into p from public.profiles where id = me;
    return json_build_object('today', today, 'admin', p.admin,
        'open', p.admin or now() < timestamp '2027-01-01 00:00' at time zone 'Europe/Paris',   -- until the end of December
        'locked', not public.rb_feature_on('advent'),
        'catchup', coalesce(public.rb_cfg('advent_catchup'), 0) > 0,
        'starts_in', case when today = 0 and now() < timestamp '2026-12-01 00:00' at time zone 'Europe/Paris'
                          then ceil(extract(epoch from (timestamp '2026-12-01 00:00' at time zone 'Europe/Paris' - now())))::int end,
        'days', (select json_agg(json_build_object('day', a.day, 'big', a.big,
                    'claimed', exists (select 1 from public.rb_advent_claims c where c.owner = me and c.day = a.day),
                    'reward', case when p.admin or a.day = 1
                                     or exists (select 1 from public.rb_advent_claims c where c.owner = me and c.day = a.day)
                                   then public.rb_advent_reward(a) end) order by a.day)
                 from public.rb_advent a));
end $$;

create or replace function public.rb_advent_claim(which integer) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; d public.rb_advent%rowtype; today integer := public.rb_advent_day(); it text; cs text;
        given jsonb := '[]'::jsonb; new_id uuid;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('advent');
    select * into d from public.rb_advent where day = which;
    if not found then raise exception 'rb_bad_choice'; end if;
    if today = 0 or which > today or (which < today and coalesce(public.rb_cfg('advent_catchup'), 0) = 0) then
        raise exception 'rb_too_soon';
    end if;
    insert into public.rb_advent_claims (owner, day) values (p.id, which) on conflict do nothing;
    if not found then raise exception 'rb_already_claimed'; end if;
    perform public.rb_pay(p.id, d.coins, d.keys, 'advent', which::text);
    foreach it in array d.items loop
        new_id := public.rb_give(p.id, it, 'advent');
        given := given || jsonb_build_object('id', new_id, 'item', it);
    end loop;
    foreach cs in array d.cases loop
        perform public.rb_stock_add(p.id, cs, 1);
    end loop;
    perform public.rb_xp_add(p.id, case when d.big then 500 else 100 end, 'advent', which::text, false);
    return json_build_object('reward', public.rb_advent_reward(d), 'given', given, 'coins', p.coins + d.coins, 'keys', p.keys + d.keys);
end $$;

-- ================================================================ Coinflip: lobby first, items after; fair bots
-- A bot side has no player (a or b is null) and a bot name; its items are listed in a_what / b_what. If a player
-- beats a bot, the bot's items are made for that player; if the bot wins, the player's items leave the game.
-- Bots use the same chance (share of the pot, 49% to 51%) and the same server roll as everyone.
alter table public.rb_flips alter column a drop not null;
alter table public.rb_flips add column if not exists bot_side text;
alter table public.rb_flips add column if not exists bot_name text;
alter table public.rb_flips add column if not exists admin_offer boolean not null default false;
alter table public.rb_flips add column if not exists expires_min integer;
alter table public.rb_flips add column if not exists winner_side text;
alter table public.rb_flips drop constraint if exists rb_flips_state_check;
alter table public.rb_flips add constraint rb_flips_state_check check (state in ('setup', 'open', 'joined', 'locked', 'done', 'cancelled'));
update public.rb_flips set winner_side = case when winner = a then 'a' when winner = b then 'b' end
 where winner_side is null and winner is not null;

create or replace function public.rb_flip_busy(who uuid) returns boolean
language sql stable security definer set search_path = '' as $$
    select exists (select 1 from public.rb_flips f where (f.a = who and f.state in ('setup', 'open', 'joined', 'locked'))
                                                      or (f.b = who and f.state in ('joined', 'locked'))) $$;

create or replace function public.rb_flip_name(who uuid, bot text) returns text
language sql stable security definer set search_path = '' as $$
    select coalesce((select username from public.profiles where id = who), bot) $$;

create or replace function public.rb_flip_json(f public.rb_flips, me uuid) returns json
language sql stable security definer set search_path = '' as $$
    select json_build_object('id', f.id, 'state', f.state, 'mine', f.a = me, 'joiner', f.b = me,
        'a', public.rb_flip_name(f.a, case when f.bot_side = 'a' then f.bot_name end),
        'b', public.rb_flip_name(f.b, case when f.bot_side = 'b' then f.bot_name end),
        'a_bot', f.bot_side = 'a', 'b_bot', f.bot_side = 'b', 'admin_offer', f.admin_offer,
        'a_side', f.a_side, 'b_side', case when f.a_side = 'black' then 'white' else 'black' end,
        'a_items', (select coalesce(json_agg(json_build_object('item', w, 'worth', public.rb_worth(w))), '[]'::json) from unnest(f.a_what) w),
        'b_items', (select coalesce(json_agg(json_build_object('item', w, 'worth', public.rb_worth(w))), '[]'::json) from unnest(f.b_what) w),
        'a_value', f.a_value, 'b_value', f.b_value,
        'min', floor(f.a_value * (1 - coalesce(public.rb_cfg('flip_range'), 0.1))),
        'max', ceil(f.a_value * (1 + coalesce(public.rb_cfg('flip_range'), 0.1))),
        'chance_a', f.chance_a,
        'expires', case when f.state in ('open', 'setup') then greatest(0, ceil(extract(epoch from (f.at
                         + make_interval(mins => case when f.state = 'setup' then coalesce(public.rb_cfg('flip_setup_min'), 10)::int
                                                      else coalesce(f.expires_min, public.rb_cfg('lobby_min')::int, 5) end) - now()))))::int end,
        'pick_left', case when f.state = 'joined' then greatest(0, ceil(extract(epoch from (f.joined_at
                         + make_interval(secs => coalesce(public.rb_cfg('flip_join_s'), 30)) - now()))))::int end,
        'flip_in', case when f.state = 'locked' then greatest(0, extract(epoch from (f.flip_at - now())))::numeric(6, 2) end,
        'result', case when f.state = 'done' then f.result end,
        'winner', case when f.state = 'done' then (case f.winner_side when 'a' then public.rb_flip_name(f.a, f.bot_name)
                                                                     else public.rb_flip_name(f.b, f.bot_name) end) end,
        'won', case when f.state = 'done' then f.winner = me end,
        'at', f.at) $$;

create or replace function public.rb_flip_free(f public.rb_flips, why text) returns void
language plpgsql security definer set search_path = '' as $$
begin
    update public.rb_items set locked = null where locked = 'flip:' || f.id;
    update public.rb_flips set state = 'cancelled', why = rb_flip_free.why, done_at = now() where id = f.id;
end $$;

-- the coin has landed: move the items once
create or replace function public.rb_flip_settle(fid uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare f public.rb_flips%rowtype; human_w uuid; human_l uuid; w text; lost jsonb;
begin
    select * into f from public.rb_flips where id = fid for update;
    if not found or f.state <> 'locked' or now() < f.flip_at then return; end if;
    human_w := case f.winner_side when 'a' then f.a else f.b end;
    human_l := case f.winner_side when 'a' then f.b else f.a end;
    perform 1 from public.rb_items where locked = 'flip:' || f.id order by id for update;
    if human_w is not null and human_l is not null then                        -- player against player
        update public.rb_items set owner = human_w, locked = null, origin = 'flip' where locked = 'flip:' || f.id and owner = human_l;
        update public.rb_items set locked = null where locked = 'flip:' || f.id;
        insert into public.rb_seen (owner, item) select human_w, x from unnest(f.a_what || f.b_what) x on conflict do nothing;
        perform public.rb_fix_equip(human_l);
    elsif human_w is not null then                                             -- a player beat a bot: the bot's items are made for them
        update public.rb_items set locked = null where locked = 'flip:' || f.id;
        foreach w in array (case when f.bot_side = 'a' then f.a_what else f.b_what end) loop
            perform public.rb_give(human_w, w, 'flip');
        end loop;
    else                                                                       -- a bot won: the player's items leave the game
        select coalesce(jsonb_agg(it.item), '[]'::jsonb) into lost from public.rb_items it where it.locked = 'flip:' || f.id;
        delete from public.rb_items where locked = 'flip:' || f.id;
        insert into public.rb_audit (admin, action, target, detail) values (null, 'flip_bot_win', f.id::text,
            jsonb_build_object('player', human_l, 'items', lost, 'bot', f.bot_name));
        perform public.rb_fix_equip(human_l);
    end if;
    update public.rb_flips set state = 'done', done_at = now(), winner = human_w where id = f.id;
    if human_w is not null then
        perform public.rb_notice(human_w, 'flip_end', jsonb_build_object('id', f.id, 'won', true, 'value', f.a_value + f.b_value));
        perform public.rb_xp_add(human_w, 25, 'coinflip', f.id::text, true);
    end if;
    if human_l is not null then
        perform public.rb_notice(human_l, 'flip_end', jsonb_build_object('id', f.id, 'won', false, 'value', f.a_value + f.b_value));
        perform public.rb_xp_add(human_l, 25, 'coinflip', f.id::text, true);
    end if;
end $$;

create or replace function public.rb_flip_tick(fid uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare f public.rb_flips%rowtype;
begin
    select * into f from public.rb_flips where id = fid for update;
    if not found then return; end if;
    if f.state = 'joined' and now() - f.joined_at > make_interval(secs => coalesce(public.rb_cfg('flip_join_s'), 30) + 2) then
        update public.rb_flips set state = 'open', b = null, joined_at = null where id = f.id;
        f.state := 'open';
    end if;
    if f.state = 'setup' and now() - f.at > make_interval(mins => coalesce(public.rb_cfg('flip_setup_min'), 10)::int) then
        perform public.rb_flip_free(f, 'expired');
    elsif f.state = 'open' and now() - f.at > make_interval(mins => coalesce(f.expires_min, public.rb_cfg('lobby_min')::int, 5)) then
        perform public.rb_flip_free(f, 'expired');
    elsif f.state = 'locked' and now() >= f.flip_at then
        perform public.rb_flip_settle(f.id);
    end if;
end $$;

create or replace function public.rb_flip_cleanup(who uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare r record;
begin
    for r in select distinct substr(it.locked, 6)::uuid fid from public.rb_items it
              where it.owner = who and it.locked like 'flip:%' loop
        perform public.rb_flip_tick(r.fid);
    end loop;
    for r in select id from public.rb_flips where a = who and state = 'setup' loop
        perform public.rb_flip_tick(r.id);
    end loop;
    update public.rb_items it set locked = null
     where it.owner = who and it.locked like 'flip:%'
       and not exists (select 1 from public.rb_flips f where 'flip:' || f.id = it.locked and f.state in ('open', 'joined', 'locked'));
end $$;

-- 1. create a lobby (pick black or white). Items come next, in the lobby. (Old apps still send items at once.)
create or replace function public.rb_flip_create(side text, items uuid[]) returns json
language plpgsql security definer set search_path = '' as $$
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
end $$;

-- 2. the creator puts in items and confirms: the lobby opens to everyone
create or replace function public.rb_flip_put(fid uuid, items uuid[]) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; f public.rb_flips%rowtype; chk record;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('coinflip');
    perform public.rb_flip_tick(fid);
    select * into f from public.rb_flips where id = fid for update;
    if not found or f.a is distinct from p.id or f.state <> 'setup' then raise exception 'rb_duel_gone'; end if;
    chk := public.rb_flip_check(p.id, items);
    update public.rb_items set locked = 'flip:' || f.id where id = any (items);
    update public.rb_flips set a_items = items, a_what = chk.whats, a_value = chk.total, state = 'open', at = now()
     where id = f.id returning * into f;
    return public.rb_flip_json(f, p.id);
end $$;

create or replace function public.rb_flip_cancel(fid uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); f public.rb_flips%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_flip_tick(fid);
    select * into f from public.rb_flips where id = fid for update;
    if not found or f.a is distinct from me then raise exception 'rb_duel_gone'; end if;
    if f.state not in ('setup', 'open') then raise exception 'rb_flip_locked'; end if;
    perform public.rb_flip_free(f, 'taken back');
    return json_build_object('state', 'cancelled');
end $$;

create or replace function public.rb_flip_join(fid uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; f public.rb_flips%rowtype; r record;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('coinflip');
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    for r in select id from public.rb_flips where (a = p.id or b = p.id) and state in ('setup', 'open', 'joined', 'locked') loop
        perform public.rb_flip_tick(r.id);
    end loop;
    perform public.rb_flip_tick(fid);
    select * into f from public.rb_flips where id = fid for update;
    if not found or f.state <> 'open' then raise exception 'rb_duel_gone'; end if;
    if f.a = p.id then raise exception 'rb_thats_you'; end if;
    if public.rb_flip_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    update public.rb_flips set b = p.id, state = 'joined', joined_at = now() where id = f.id returning * into f;
    if f.a is not null then perform public.rb_notice(f.a, 'flip_join', jsonb_build_object('from', p.username, 'id', f.id)); end if;
    return public.rb_flip_json(f, p.id);
end $$;

-- the joiner locks in: decided now by the server, lands 15 seconds later, cannot be undone
create or replace function public.rb_flip_lock(fid uuid, items uuid[]) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; f public.rb_flips%rowtype; chk record; rng double precision; ch double precision; a_wins boolean;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('coinflip');
    perform public.rb_flip_tick(fid);
    select * into f from public.rb_flips where id = fid for update;
    if not found or f.b is distinct from p.id or f.state <> 'joined' then raise exception 'rb_duel_gone'; end if;
    chk := public.rb_flip_check(p.id, items);
    rng := coalesce(public.rb_cfg('flip_range'), 0.1);
    if chk.total < floor(f.a_value * (1 - rng)) or chk.total > ceil(f.a_value * (1 + rng)) then raise exception 'rb_flip_range'; end if;
    ch := greatest(coalesce(public.rb_cfg('flip_min_chance'), 0.49),
                   least(coalesce(public.rb_cfg('flip_max_chance'), 0.51), f.a_value::double precision / (f.a_value + chk.total)));
    a_wins := public.rb_rand() < ch;
    update public.rb_items set locked = 'flip:' || f.id where id = any (items);
    update public.rb_flips set b_items = items, b_what = chk.whats, b_value = chk.total, chance_a = round(ch::numeric, 4),
           result = case when a_wins then f.a_side else (case when f.a_side = 'black' then 'white' else 'black' end) end,
           winner_side = case when a_wins then 'a' else 'b' end, state = 'locked', locked_at = now(),
           flip_at = now() + make_interval(secs => coalesce(public.rb_cfg('flip_wait_s'), 15))
     where id = f.id returning * into f;
    if f.a is not null then perform public.rb_notice(f.a, 'flip_locked', jsonb_build_object('from', p.username, 'id', f.id)); end if;
    return public.rb_flip_json(f, p.id);
end $$;

create or replace function public.rb_flip_list() returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); r record;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    for r in select id from public.rb_flips where state in ('setup', 'open', 'joined', 'locked')
               and (now() - at > make_interval(mins => case when state = 'setup' then coalesce(public.rb_cfg('flip_setup_min'), 10)::int
                                                            else coalesce(expires_min, public.rb_cfg('lobby_min')::int, 5) end)
                    or (state = 'joined' and now() - joined_at > make_interval(secs => coalesce(public.rb_cfg('flip_join_s'), 30)))
                    or (state = 'locked' and now() >= flip_at)) loop
        perform public.rb_flip_tick(r.id);
    end loop;
    perform public.rb_flip_cleanup(me);
    return json_build_object(
        'flips', coalesce((select json_agg(public.rb_flip_json(f, me) order by (f.a = me or f.b = me) desc, f.state = 'open' desc, f.at desc)
                   from (select * from public.rb_flips where (state in ('open', 'joined', 'locked') or (state = 'setup' and a = me))
                         or (state = 'done' and done_at > now() - interval '90 seconds') order by at desc limit 40) f), '[]'::json),
        'mine', (select f.id from public.rb_flips f where ((f.a = me and f.state in ('setup', 'open', 'joined', 'locked'))
                   or (f.b = me and f.state in ('joined', 'locked'))) limit 1),
        'max_items', coalesce(public.rb_cfg('flip_max_items'), 6), 'range', coalesce(public.rb_cfg('flip_range'), 0.1),
        'locked', not public.rb_feature_on('coinflip'),
        'history', coalesce((select json_agg(json_build_object('id', f.id, 'won', f.winner = me, 'value', f.a_value + f.b_value,
                     'other', case when f.a = me then public.rb_flip_name(f.b, f.bot_name) else public.rb_flip_name(f.a, f.bot_name) end,
                     'bot', f.bot_side is not null, 'result', f.result, 'at', f.done_at) order by f.done_at desc)
                   from (select * from public.rb_flips where (a = me or b = me) and state = 'done' order by done_at desc limit 8) f), '[]'::json));
end $$;

create or replace function public.rb_online_status() returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    return json_build_object(
        'flip_open', exists (select 1 from public.rb_flips where a = me and state in ('setup', 'open')),
        'flip_host_joined', exists (select 1 from public.rb_flips where a = me and state = 'joined'),
        'flip_joined', exists (select 1 from public.rb_flips where b = me and state = 'joined'),
        'flip_locked', exists (select 1 from public.rb_flips where (a = me or b = me) and state = 'locked'),
        'golf_open', exists (select 1 from public.rb_golf where a = me and state in ('open', 'asked')),
        'golf_live', exists (select 1 from public.rb_golf where (a = me or b = me) and state = 'live'),
        'giveaways', coalesce((select json_agg(g.title) from public.rb_giveaways g join public.rb_giveaway_entries e
                                 on e.giveaway = g.id and e.owner = me where g.state = 'live' and g.ends_at > now()), '[]'::json));
end $$;

create or replace function public.rb_online_leave() returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); f public.rb_flips%rowtype; g record; n_flip integer := 0; n_golf integer := 0; n_give integer := 0;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    for f in select * from public.rb_flips where a = me and state in ('setup', 'open') for update loop
        perform public.rb_flip_free(f, 'left'); n_flip := n_flip + 1;
    end loop;
    for f in select * from public.rb_flips where b = me and state = 'joined' for update loop
        update public.rb_flips set state = 'open', b = null, joined_at = null where id = f.id; n_flip := n_flip + 1;
    end loop;
    for g in select id from public.rb_golf where a = me and state in ('open', 'asked') loop
        perform public.rb_golf_cancel(g.id); n_golf := n_golf + 1;
    end loop;
    for g in select id from public.rb_golf where (a = me or b = me) and state = 'live' loop
        perform public.rb_golf_end(g.id, me); n_golf := n_golf + 1;
    end loop;
    delete from public.rb_giveaway_entries e using public.rb_giveaways gw
     where e.owner = me and e.giveaway = gw.id and gw.state = 'live' and gw.ends_at > now();
    get diagnostics n_give = row_count;
    return json_build_object('flips', n_flip, 'golf', n_golf, 'giveaways', n_give);
end $$;

-- ---------------------------------------------------------------- bots
-- items for a bot, worth close to a target: a few real catalog items, never limited ones
create or replace function public.rb_flip_bot_items(target bigint, n integer) returns text[]
language plpgsql security definer set search_path = '' as $$
declare res text[] := '{}'; left_ bigint := target; per bigint; pick text; i integer;
begin
    for i in 1..greatest(1, least(6, n)) loop
        per := left_ / (n - i + 1);
        exit when per < 50;
        select c.id into pick from public.rb_catalog c
         where c.tradeable and not c.limited and c.kind in ('badge', 'ball', 'line', 'font', 'banner', 'frame', 'theme')
           and coalesce(c.worth, 0) between greatest(5, per * 0.4) and per * 1.6
           and not (c.kind <> 'badge' and c.id = any (res))
         order by abs(ln(c.worth::double precision / per)) + random() * 0.35 limit 1;
        exit when pick is null;
        res := res || pick;
        left_ := left_ - public.rb_worth(pick);
    end loop;
    return res;
end $$;

create or replace function public.rb_flip_bot_name() returns text
language sql volatile set search_path = '' as $$
    select (array['Nova', 'Pixel', 'Echo', 'Atlas', 'Juno', 'Orion', 'Kira', 'Milo', 'Vega', 'Rook', 'Luma', 'Sable'])[1 + floor(random() * 12)::int] $$;

-- make one bot offer (value: rare big ones, some poor ones, mostly average)
create or replace function public.rb_flip_bot_offer(val bigint, admin_made boolean, bot text, side text, minutes integer, items text[]) returns uuid
language plpgsql security definer set search_path = '' as $$
declare r double precision := random(); whats text[]; total bigint; fid uuid;
begin
    if items is not null and array_length(items, 1) > 0 then
        whats := items;
    else
        if val is null then
            val := case when r < 0.03 then 150000 + floor(random() * 450000)
                        when r < 0.13 then 25000 + floor(random() * 125000)
                        when r < 0.33 then 300 + floor(random() * 1700)
                        else 2000 + floor(random() * 23000) end;
        end if;
        whats := public.rb_flip_bot_items(val, 1 + floor(random() * 4)::int);
    end if;
    if coalesce(array_length(whats, 1), 0) = 0 then return null; end if;
    select sum(public.rb_worth(w)) into total from unnest(whats) w;
    insert into public.rb_flips (a, a_side, state, a_what, a_value, bot_side, bot_name, admin_offer, expires_min)
        values (null, coalesce(side, case when random() < 0.5 then 'black' else 'white' end), 'open', whats, total, 'a',
                coalesce(bot, public.rb_flip_bot_name()), admin_made,
                coalesce(minutes, public.rb_cfg('bot_flip_min')::int, 60))
        returning id into fid;
    return fid;
end $$;

-- every minute (from the heartbeat): 0 to 3 bot offers depending on the hour, and now and then a bot joins a player's lobby
create or replace function public.rb_flip_bots_tick() returns void
language plpgsql security definer set search_path = '' as $$
declare tgt integer; cur integer; f public.rb_flips%rowtype; whats text[]; total bigint; tries integer;
        rng double precision := coalesce(public.rb_cfg('flip_range'), 0.1); ch double precision; a_wins boolean;
begin
    if not public.rb_feature_on('coinflip') then return; end if;
    tgt := least(coalesce(public.rb_cfg('bot_flips_max'), 3)::int,
                 abs(hashtext('flipbots' || floor(extract(epoch from now()) / 2400)::text)) % 4);
    select count(*) into cur from public.rb_flips where bot_side = 'a' and not admin_offer and state in ('open', 'joined', 'locked');
    if cur < tgt and random() < 0.35 then perform public.rb_flip_bot_offer(null, false, null, null, null, null); end if;
    -- a bot joins one waiting player lobby (after a minute and a half at least)
    for f in select * from public.rb_flips where state = 'open' and a is not null and bot_side is null
               and now() - at > interval '90 seconds' order by random() limit 1 for update skip locked loop
        if random() >= 0.12 then exit; end if;
        tries := 0;
        loop
            tries := tries + 1;
            whats := public.rb_flip_bot_items(f.a_value, 1 + floor(random() * 3)::int);
            select coalesce(sum(public.rb_worth(w)), 0) into total from unnest(whats) w;
            exit when (total between floor(f.a_value * (1 - rng)) and ceil(f.a_value * (1 + rng))) or tries >= 6;
        end loop;
        if total between floor(f.a_value * (1 - rng)) and ceil(f.a_value * (1 + rng)) then
            ch := greatest(coalesce(public.rb_cfg('flip_min_chance'), 0.49),
                           least(coalesce(public.rb_cfg('flip_max_chance'), 0.51), f.a_value::double precision / (f.a_value + total)));
            a_wins := public.rb_rand() < ch;
            update public.rb_flips set b = null, bot_side = 'b', bot_name = public.rb_flip_bot_name(), b_what = whats, b_value = total,
                   chance_a = round(ch::numeric, 4), joined_at = now(),
                   result = case when a_wins then f.a_side else (case when f.a_side = 'black' then 'white' else 'black' end) end,
                   winner_side = case when a_wins then 'a' else 'b' end, state = 'locked', locked_at = now(),
                   flip_at = now() + make_interval(secs => coalesce(public.rb_cfg('flip_wait_s'), 15))
             where id = f.id;
            perform public.rb_notice(f.a, 'flip_locked', jsonb_build_object('from', 'BOT', 'id', f.id, 'bot', true));
        end if;
    end loop;
end $$;

do $$ declare src text; begin
    select pg_get_functiondef('public.rb_bots_tick()'::regprocedure) into src;
    if position('rb_flip_bots_tick' in src) = 0 then
        execute replace(src, 'if not found then return; end if;', 'if not found then return; end if;
    perform public.rb_flip_bots_tick();');
    end if;
end $$;

-- the admin: make a bot offer (items or a value), see them, take one back while nobody has locked in
create or replace function public.rb_admin_flip_offer(bot text, items text[], val bigint, side text, minutes integer) returns json
language plpgsql security definer set search_path = '' as $$
declare fid uuid; w text;
begin
    perform public.rb_need_admin();
    if side is not null and side not in ('black', 'white') then raise exception 'rb_bad_choice'; end if;
    if coalesce(array_length(items, 1), 0) > 6 then raise exception 'rb_bad_offer'; end if;
    foreach w in array coalesce(items, '{}') loop
        if not exists (select 1 from public.rb_catalog c where c.id = w and c.tradeable and coalesce(c.worth, 0) > 0
                         and c.kind not in ('prog', 'tag', 'coupon')) then raise exception 'rb_bad_offer'; end if;
    end loop;
    if coalesce(array_length(items, 1), 0) = 0 and (val is null or val < 100 or val > 50000000) then raise exception 'rb_bad_offer'; end if;
    fid := public.rb_flip_bot_offer(val, true, nullif(btrim(left(bot, 20)), ''), side, greatest(5, least(1440, coalesce(minutes, 60))), items);
    if fid is null then raise exception 'rb_bad_offer'; end if;
    perform public.rb_log('flip_offer', fid::text, jsonb_build_object('items', items, 'value', val, 'minutes', minutes));
    return public.rb_admin_flips();
end $$;

create or replace function public.rb_admin_flip_cancel(fid uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare f public.rb_flips%rowtype;
begin
    perform public.rb_need_admin();
    select * into f from public.rb_flips where id = fid for update;
    if not found or f.bot_side is null then raise exception 'rb_duel_gone'; end if;
    if f.state not in ('setup', 'open', 'joined') then raise exception 'rb_flip_locked'; end if;
    perform public.rb_flip_free(f, 'admin');
    if f.b is not null then perform public.rb_notice(f.b, 'cancelled', jsonb_build_object('what', 'coinflip')); end if;
    perform public.rb_log('flip_cancel', fid::text, '{}'::jsonb);
    return public.rb_admin_flips();
end $$;

create or replace function public.rb_admin_flips() returns json
language plpgsql stable security definer set search_path = '' as $$
begin
    perform public.rb_need_admin();
    return coalesce((select json_agg(public.rb_flip_json(f, auth.uid()) order by f.at desc)
                       from (select * from public.rb_flips where bot_side is not null
                               and (state in ('setup', 'open', 'joined', 'locked') or done_at > now() - interval '1 day')
                             order by at desc limit 60) f), '[]'::json);
end $$;

-- ================================================================ casino
-- Roulette: 25 pockets, 0 is gold. Colours and halves pay x2, gold or one number pays x24 (96% return on every bet).
create or replace function public.rb_roulette(bet integer, pick text, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; slot integer; colour text; pay integer := 0; win boolean; num integer;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    perform public.rb_need_feature('roulette');
    if pick ~ '^n:[0-9]{1,2}$' then
        num := substr(pick, 3)::int;
        if num > 24 then raise exception 'rb_bad_choice'; end if;
    elsif pick not in ('red', 'black', 'gold', 'low', 'high') then
        raise exception 'rb_bad_choice';
    end if;
    perform public.rb_bet(p, bet, 'roulette');
    slot := floor(public.rb_rand() * 25)::int;                     -- 0 = gold, odd = red, even = black
    colour := case when slot = 0 then 'gold' when slot % 2 = 1 then 'red' else 'black' end;
    win := case when num is not null then slot = num
                when pick = 'low' then slot between 1 and 12
                when pick = 'high' then slot between 13 and 24
                else colour = pick end;
    if win then
        pay := public.rb_win(p.id, bet * case when pick in ('gold') or num is not null then 24 else 2 end, 'roulette');
    end if;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        values (p.id, 'roulette', bet, jsonb_build_object('slot', slot, 'pick', pick), false, pay);
    return public.rb_remember(p.id, req, jsonb_build_object('slot', slot, 'colour', colour, 'win', win,
                                                            'paid', pay, 'coins', p.coins - bet + pay));
end $$;

-- Tower: climb 8 rows, pick one tile a row; a bomb ends it. Cash out any time after the first row.
-- Modes: 0 easy (4 tiles, 1 bomb), 1 medium (3 tiles, 1 bomb), 2 hard (2 tiles, 1 bomb), 3 expert (3 tiles, 2 bombs).
-- Prize after n rows = bet x 0.97 / (chance to pass a row)^n.
create or replace function public.rb_tower_mult(mode integer, n integer) returns numeric
language sql immutable set search_path = '' as $$
    select case when n <= 0 then 1 else round(0.97 / power((array[0.75, 2.0 / 3, 0.5, 1.0 / 3])[mode + 1], n)::numeric, 2) end $$;

create or replace function public.rb_tower(action text, bet integer, arg integer, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
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
end $$;

-- Keno: pick 1 to 10 numbers out of 40; 10 are drawn. The prize table (x bet) returns about 94-95%.
create or replace function public.rb_keno_table() returns jsonb
language sql immutable set search_path = '' as $$
    select '{"1":[0,3.8],"2":[0,1.7,5],"3":[0,1,2.4,15],"4":[0,0,2.3,8.7,47],"5":[0,0,1.5,4,18,90],
             "6":[0,0,0.83,3,8.3,44,260],"7":[0,0,0.53,2.1,5.3,19,110,530],"8":[0,0,0,1.7,4.4,12,50,220,1100],
             "9":[0,0,0,1.3,2.9,7.3,24,97,430,2400],"10":[0,0,0,1.1,2.1,4.6,12,46,190,930,4600]}'::jsonb $$;

create or replace function public.rb_keno(bet integer, picks integer[], req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; k integer; drawn integer[]; hits integer; mult numeric; pay integer := 0;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    perform public.rb_need_feature('casino');
    k := coalesce(array_length(picks, 1), 0);
    if k < 1 or k > 10 or k <> (select count(distinct x) from unnest(picks) x)
       or exists (select 1 from unnest(picks) x where x < 1 or x > 40) then raise exception 'rb_bad_choice'; end if;
    perform public.rb_bet(p, bet, 'keno');
    select array_agg(x order by o) into drawn from (select x, public.rb_rand() o from generate_series(1, 40) x order by o limit 10) t;
    select count(*) into hits from unnest(picks) x where x = any (drawn);
    mult := (public.rb_keno_table() -> k::text ->> hits)::numeric;
    if mult > 0 then pay := public.rb_win(p.id, bet * mult, 'keno'); end if;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        values (p.id, 'keno', bet, jsonb_build_object('picks', picks, 'drawn', drawn, 'hits', hits), false, pay);
    return public.rb_remember(p.id, req, jsonb_build_object('drawn', drawn, 'hits', hits, 'mult', mult, 'paid', pay,
                                                            'coins', p.coins - bet + pay));
end $$;

-- Limbo: choose a target (x1.01 to x1000). The result is drawn with 97% fairness; reach the target and win bet x target.
create or replace function public.rb_limbo(bet integer, target numeric, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb; u double precision; result numeric; pay integer := 0;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    perform public.rb_need_feature('casino');
    target := round(coalesce(target, 0), 2);
    if target < 1.01 or target > 1000 then raise exception 'rb_bad_choice'; end if;
    perform public.rb_bet(p, bet, 'limbo');
    u := public.rb_rand();
    result := greatest(1.00, least(10000, floor(0.97 / greatest(1 - u, 1e-9) * 100) / 100));
    if result >= target then pay := public.rb_win(p.id, bet * target, 'limbo'); end if;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        values (p.id, 'limbo', bet, jsonb_build_object('target', target, 'result', result), false, pay);
    return public.rb_remember(p.id, req, jsonb_build_object('result', result, 'target', target, 'win', result >= target,
                                                            'paid', pay, 'coins', p.coins - bet + pay));
end $$;

-- ================================================================ new minigames: 2048 and Minesweeper, with leaderboards
create table if not exists public.rb_mg (
    id uuid primary key default gen_random_uuid(),
    owner uuid not null references public.profiles (id) on delete cascade,
    game text not null check (game in ('g2048', 'sweeper')),
    mode integer not null,
    seed bigint not null,
    state jsonb not null default '{}'::jsonb,
    open boolean not null default true,
    void boolean not null default false,
    score integer, won boolean, secs numeric, paid integer not null default 0,
    at timestamptz not null default now(), first_at timestamptz, done_at timestamptz
);
alter table public.rb_mg enable row level security;
create index if not exists rb_mg_board on public.rb_mg (game, mode, score desc) where not open and not void;
create index if not exists rb_mg_owner on public.rb_mg (owner, at desc);

create or replace function public.rb_lcg(s bigint) returns bigint
language sql immutable set search_path = '' as $$ select (s * 1103515245 + 12345) % 2147483648 $$;

-- 2048 played again here from the moves (U D L R), with the same random tiles as the app: the score cannot be made up
create or replace function public.rb_2048_replay(n integer, seed bigint, moves text, out score integer, out best integer, out board integer[])
language plpgsql immutable set search_path = '' as $$
declare s bigint := seed; b integer[]; i integer; m text; line integer[]; outl integer[]; k integer; j integer; changed boolean;
        empties integer[]; idx integer; nb integer[]; cell integer; pos integer; spawn integer; mv integer;
begin
    b := array_fill(0, array[n * n]); score := 0;
    for spawn in 1..2 loop
        select array_agg(x - 1) into empties from generate_series(1, n * n) x where b[x] = 0;
        s := public.rb_lcg(s); idx := empties[(s % array_length(empties, 1)) + 1];
        s := public.rb_lcg(s); b[idx + 1] := case when s % 10 = 0 then 4 else 2 end;
    end loop;
    for mv in 1..least(length(coalesce(moves, '')), 6000) loop
        m := substr(moves, mv, 1);
        if m not in ('U', 'D', 'L', 'R') then continue; end if;
        nb := b; changed := false;
        for i in 0..n - 1 loop
            line := '{}';
            for k in 0..n - 1 loop                                              -- read the line towards the move
                pos := case m when 'L' then i * n + k when 'R' then i * n + (n - 1 - k)
                              when 'U' then k * n + i else (n - 1 - k) * n + i end;
                if b[pos + 1] <> 0 then line := line || b[pos + 1]; end if;
            end loop;
            outl := '{}'; j := 1;
            while j <= coalesce(array_length(line, 1), 0) loop
                if j < array_length(line, 1) and line[j] = line[j + 1] then
                    outl := outl || (line[j] * 2); score := score + line[j] * 2; j := j + 2;
                else
                    outl := outl || line[j]; j := j + 1;
                end if;
            end loop;
            for k in 0..n - 1 loop
                pos := case m when 'L' then i * n + k when 'R' then i * n + (n - 1 - k)
                              when 'U' then k * n + i else (n - 1 - k) * n + i end;
                cell := coalesce(outl[k + 1], 0);
                if nb[pos + 1] <> cell then nb[pos + 1] := cell; end if;
                if b[pos + 1] <> cell then changed := true; end if;
            end loop;
        end loop;
        if changed then
            b := nb;
            select array_agg(x - 1) into empties from generate_series(1, n * n) x where b[x] = 0;
            if empties is not null then
                s := public.rb_lcg(s); idx := empties[(s % array_length(empties, 1)) + 1];
                s := public.rb_lcg(s); b[idx + 1] := case when s % 10 = 0 then 4 else 2 end;
            end if;
        end if;
    end loop;
    best := (select max(x) from unnest(b) x); board := b;
end $$;

-- modes: 2048 0 = 4x4 Classic, 1 = 5x5 Relaxed, 2 = 3x3 Hard. Minesweeper 0 = Easy, 1 = Medium, 2 = Hard.
create or replace function public.rb_mg_start(game text, mode integer) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r public.rb_mg%rowtype; sd bigint;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('minigames');
    if game not in ('g2048', 'sweeper') or mode not between 0 and 2 then raise exception 'rb_bad_choice'; end if;
    update public.rb_mg set open = false, void = true where owner = p.id and open;      -- one game at a time
    sd := floor(public.rb_rand() * 2147483647)::bigint;
    insert into public.rb_mg (owner, game, mode, seed, state) values (p.id, game, mode,
        case when game = 'g2048' then sd else 0 end,
        case when game = 'sweeper' then jsonb_build_object('w', (array[9, 12, 16])[mode + 1], 'h', (array[9, 12, 14])[mode + 1],
                                                           'm', (array[10, 24, 40])[mode + 1], 'seed', sd) else '{}'::jsonb end)
        returning * into r;
    return json_build_object('id', r.id, 'game', game, 'mode', mode, 'seed', r.seed,
        'w', r.state -> 'w', 'h', r.state -> 'h', 'm', r.state -> 'm',
        'size', case when game = 'g2048' then (array[4, 5, 3])[mode + 1] end);
end $$;

create or replace function public.rb_mg_pay(r public.rb_mg, base integer) returns integer
language plpgsql security definer set search_path = '' as $$
declare pay integer;
begin
    pay := public.rb_game_pay(r.owner, r.game, base);
    if pay > 0 then perform public.rb_pay(r.owner, pay, 0, 'minigame', r.game); end if;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        values (r.owner, r.game, 0, jsonb_build_object('mode', r.mode, 'score', r.score, 'mg', r.id), false, pay);
    return pay;
end $$;

-- 2048 is over (or the player stops): the moves are played again here, the score paid
create or replace function public.rb_2048_finish(round uuid, moves text) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r public.rb_mg%rowtype; rep record; base integer; pay integer;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('minigames');
    select * into r from public.rb_mg where id = round and owner = p.id and game = 'g2048' for update;
    if not found or not r.open then raise exception 'rb_round_gone'; end if;
    if length(coalesce(moves, '')) > 6000 then raise exception 'rb_bad_choice'; end if;
    rep := public.rb_2048_replay((array[4, 5, 3])[r.mode + 1], r.seed, moves);
    base := least((array[320, 200, 360])[r.mode + 1], rep.score / (array[40, 80, 14])[r.mode + 1]);
    update public.rb_mg set open = false, score = rep.score, won = rep.best >= (array[2048, 2048, 256])[r.mode + 1],
           secs = extract(epoch from now() - at), done_at = now(), state = jsonb_build_object('best', rep.best, 'moves', length(moves))
     where id = r.id returning * into r;
    pay := public.rb_mg_pay(r, base);
    update public.rb_mg set paid = pay where id = r.id;
    return json_build_object('score', rep.score, 'best', rep.best, 'paid', pay, 'coins', p.coins + pay);
end $$;

-- Minesweeper: the mines stay here. The first cell opened is always safe (mines are placed after it).
create or replace function public.rb_sweep_open(round uuid, cell integer) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r public.rb_mg%rowtype; st jsonb; w integer; h integer; m integer; mines integer[];
        opened integer[]; q integer[]; c integer; cx integer; cy integer; dx integer; dy integer; nx integer; ny integer; nn integer;
        cnt integer; shown jsonb := '[]'::jsonb; total_open integer; base integer; pay integer := 0; s bigint; el numeric; tgt numeric;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('minigames');
    select * into r from public.rb_mg where id = round and owner = p.id and game = 'sweeper' for update;
    if not found or not r.open then raise exception 'rb_round_gone'; end if;
    st := r.state; w := (st ->> 'w')::int; h := (st ->> 'h')::int; m := (st ->> 'm')::int;
    if cell is null or cell < 0 or cell >= w * h then raise exception 'rb_bad_choice'; end if;
    if st ? 'mines' then
        select array_agg(x::int) into mines from jsonb_array_elements_text(st -> 'mines') x;
        select coalesce(array_agg(x::int), '{}') into opened from jsonb_array_elements_text(st -> 'open') x;
    else                                                                     -- the first click: place the mines away from it
        s := (st ->> 'seed')::bigint; mines := '{}';
        while coalesce(array_length(mines, 1), 0) < m loop
            s := public.rb_lcg(s); c := (s % (w * h))::int;
            if abs(c % w - cell % w) <= 1 and abs(c / w - cell / w) <= 1 then continue; end if;
            if c = any (mines) then continue; end if;
            mines := mines || c;
        end loop;
        opened := '{}';
        update public.rb_mg set first_at = now() where id = r.id;
        r.first_at := now();
    end if;
    if cell = any (opened) then return json_build_object('shown', '[]'::json, 'over', false); end if;
    if cell = any (mines) then
        update public.rb_mg set open = false, won = false, score = 0, done_at = now(),
               secs = extract(epoch from now() - coalesce(r.first_at, r.at)),
               state = st || jsonb_build_object('mines', to_jsonb(mines), 'open', to_jsonb(opened), 'boom', cell)
         where id = r.id returning * into r;
        pay := public.rb_mg_pay(r, 0);
        return json_build_object('over', true, 'won', false, 'boom', cell, 'mines', to_jsonb(mines), 'paid', 0);
    end if;
    q := array[cell];                                                         -- open the cell, and the area around a zero
    while coalesce(array_length(q, 1), 0) > 0 loop
        c := q[1]; q := q[2:];
        if c = any (opened) then continue; end if;
        opened := opened || c;
        cx := c % w; cy := c / w; cnt := 0;
        for dy in -1..1 loop for dx in -1..1 loop
            nx := cx + dx; ny := cy + dy;
            if (dx <> 0 or dy <> 0) and nx between 0 and w - 1 and ny between 0 and h - 1 and (ny * w + nx) = any (mines) then cnt := cnt + 1; end if;
        end loop; end loop;
        shown := shown || jsonb_build_array(jsonb_build_array(c, cnt));
        if cnt = 0 then
            for dy in -1..1 loop for dx in -1..1 loop
                nx := cx + dx; ny := cy + dy; nn := ny * w + nx;
                if (dx <> 0 or dy <> 0) and nx between 0 and w - 1 and ny between 0 and h - 1 and not nn = any (opened) then q := q || nn; end if;
            end loop; end loop;
        end if;
    end loop;
    total_open := array_length(opened, 1);
    if total_open >= w * h - m then                                           -- cleared: faster pays more
        el := extract(epoch from now() - coalesce(r.first_at, r.at));
        tgt := (array[70, 180, 360])[r.mode + 1];
        base := floor((array[70, 150, 280])[r.mode + 1] * greatest(0.5, least(1.5, tgt / greatest(el, 1))))::int;
        update public.rb_mg set open = false, won = true, secs = el, done_at = now(),
               score = greatest(1, (100000 / greatest(el, 1))::int),
               state = st || jsonb_build_object('mines', to_jsonb(mines), 'open', to_jsonb(opened))
         where id = r.id returning * into r;
        pay := public.rb_mg_pay(r, base);
        update public.rb_mg set paid = pay where id = r.id;
        return json_build_object('over', true, 'won', true, 'shown', shown, 'secs', round(el, 1), 'paid', pay,
                                 'coins', (select coins from public.profiles where id = p.id));
    end if;
    update public.rb_mg set state = st || jsonb_build_object('mines', to_jsonb(mines), 'open', to_jsonb(opened)) where id = r.id;
    return json_build_object('over', false, 'shown', shown, 'left', w * h - m - total_open);
end $$;

-- leaderboards: 2048 by score, Minesweeper by fastest clear (score = 100000 / seconds), per mode
create or replace function public.rb_mg_board(game text, mode integer, friends boolean) returns json
language plpgsql stable security definer set search_path = '' as $$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    return (with best as (
                select distinct on (g.owner) g.owner, g.score, g.secs, g.at from public.rb_mg g
                 where g.game = rb_mg_board.game and g.mode = rb_mg_board.mode and not g.open and not g.void
                   and coalesce(g.score, 0) > 0 and (g.game = 'g2048' or g.won)
                 order by g.owner, g.score desc, g.at),
            ranked as (select b.*, p.username, rank() over (order by b.score desc) rk from best b
                        join public.profiles p on p.id = b.owner
                       where not p.banned and (not coalesce(friends, false) or b.owner = me or public.rb_is_friend(me, b.owner)))
        select json_build_object(
            'top', coalesce((select json_agg(json_build_object('rank', rk, 'name', username, 'value', score, 'secs', round(secs, 1),
                                                               'me', owner = me) order by rk, username)
                               from (select * from ranked order by rk limit 50) t), '[]'::json),
            'me', (select json_build_object('rank', rk, 'value', score, 'secs', round(secs, 1)) from ranked where owner = me)));
end $$;

update public.rb_config set value = 300 where key = 'game_window_cap' and value < 300;

-- ================================================================ notifications: kept as a history, delivered once
alter table public.rb_inbox add column if not exists delivered boolean not null default false;
create index if not exists rb_inbox_owner on public.rb_inbox (owner, id desc);

create or replace function public.rb_notices(before_id bigint) returns json
language plpgsql stable security definer set search_path = '' as $$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    return coalesce((select json_agg(json_build_object('id', n.id, 'kind', n.kind, 'data', n.data, 'at', n.at) order by n.id desc)
                       from (select * from public.rb_inbox where owner = me and delivered
                               and (before_id is null or id < before_id) order by id desc limit 100) n), '[]'::json);
end $$;

create or replace function public.rb_notices_clear() returns boolean
language plpgsql security definer set search_path = '' as $$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    delete from public.rb_inbox where owner = auth.uid() and delivered;
    return true;
end $$;

-- ================================================================ the poll: new notices (kept), locks, level
create or replace function public.rb_live() returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); notes json; p public.profiles%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into p from public.profiles where id = me;
    if p.banned then raise exception 'rb_banned'; end if;
    if exists (select 1 from public.rb_giveaways where state = 'live' and ends_at <= now()) then
        perform public.rb_giveaway_settle();
    end if;
    if public.rb_feature_on('notifications') then
        with got as (update public.rb_inbox set delivered = true where owner = me and not delivered returning id, kind, data, at)
        select coalesce(json_agg(json_build_object('id', id, 'kind', kind, 'data', data, 'at', at) order by id), '[]'::json) into notes from got;
        delete from public.rb_inbox where owner = me and delivered
           and id < (select min(id) from (select id from public.rb_inbox where owner = me order by id desc limit 300) x);
    else
        notes := '[]'::json;
    end if;
    return json_build_object(
        'locked', public.rb_cfg('app_locked') > 0 and not p.admin,
        'app_locked', public.rb_cfg('app_locked') > 0,
        'locks', public.rb_locks(),
        'xp', public.rb_xp_json(p),
        'giveaways', coalesce((select json_agg(json_build_object('id', g.id, 'title', g.title, 'kind', g.kind,
                'what', g.what, 'amount', g.amount, 'winners', g.winners, 'min_minutes', g.min_minutes,
                'state', g.state, 'result', g.result,
                'left', greatest(0, ceil(extract(epoch from (g.ends_at - now()))))::int,
                'entries', (select count(*) from public.rb_giveaway_entries e where e.giveaway = g.id),
                'joined', exists (select 1 from public.rb_giveaway_entries e where e.giveaway = g.id and e.owner = me))
                order by g.ends_at)
              from public.rb_giveaways g
             where g.state = 'live' or (g.state = 'done' and g.ends_at > now() - interval '10 minutes')), '[]'::json),
        'sales', coalesce((select json_agg(json_build_object('id', s.id, 'what', s.what, 'pct', s.pct,
                'left', ceil(extract(epoch from (s.ends_at - now())))::int) order by s.pct desc)
              from public.rb_sales s where s.ends_at > now()), '[]'::json),
        'notices', notes,
        'trades', coalesce((select json_agg(json_build_object('id', t.id,
                'from', (select username from public.profiles where id = t.a)))
              from public.rb_trades t where t.b = me and t.state = 'asked'
               and now() - t.at <= make_interval(mins => public.rb_cfg('trade_ask_min')::int)), '[]'::json),
        'open_trade', (select t.id from public.rb_trades t where (t.a = me or t.b = me) and t.state = 'open'
                        order by t.updated desc limit 1),
        'asks', (select count(*) from public.rb_friends f where f.b = me and not f.ok),
        'online', coalesce((select json_agg(o.username) from public.rb_friends f
                  join public.profiles o on o.id = case when f.a = me then f.b else f.a end
                 where f.ok and (f.a = me or f.b = me) and public.rb_online(o)), '[]'::json),
        'newest', (select json_build_object('id', l.id, 'item', l.what, 'price', l.price, 'seller', s.username)
                     from public.rb_listings l join public.profiles s on s.id = l.seller
                    where l.state = 'open' and l.seller <> me order by l.at desc limit 1),
        'offers', (select count(*) from public.rb_offers o join public.rb_listings l on l.id = o.listing
                    where l.seller = me and o.state = 'open' and l.state = 'open'),
        'activity', json_build_object(
            'golf_open', (select count(*) from public.rb_golf where state = 'open'),
            'flip_open', (select count(*) from public.rb_flips where state = 'open'),
            'unread', (select count(*) from public.rb_messages where b = me and not read)),
        'minutes', p.minutes, 'coins', p.coins, 'keys', p.keys);
end $$;

-- ================================================================ online time gives XP (10 every 10 minutes of real use)
do $$ declare src text; begin
    select pg_get_functiondef('public.rb_heartbeat(text)'::regprocedure) into src;
    if position('rb_xp_add' in src) = 0 then
        execute replace(src, 'p.minutes := p.minutes + 1;',
                        'p.minutes := p.minutes + 1; if p.minutes % 10 = 0 then perform public.rb_xp_add(p.id, 10, ''online'', null, true); end if;');
    end if;
end $$;

-- ================================================================ chat reactions: exactly five
create table if not exists public.rb_reactions (
    msg bigint not null references public.rb_messages (id) on delete cascade,
    who uuid not null references public.profiles (id) on delete cascade,
    emoji text not null check (emoji in ('fire', 'heart', 'cry', 'laugh', 'happy')),
    at timestamptz not null default now(),
    primary key (msg, who, emoji)
);
alter table public.rb_reactions enable row level security;

create or replace function public.rb_msg_react(mid bigint, emoji text) returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); m public.rb_messages%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_need_feature('chat');
    select * into m from public.rb_messages where id = mid;
    if not found or (m.a <> me and m.b <> me) then raise exception 'rb_bad_choice'; end if;
    if emoji not in ('fire', 'heart', 'cry', 'laugh', 'happy') then raise exception 'rb_bad_choice'; end if;
    if exists (select 1 from public.rb_reactions r where r.msg = mid and r.who = me and r.emoji = rb_msg_react.emoji) then
        delete from public.rb_reactions r where r.msg = mid and r.who = me and r.emoji = rb_msg_react.emoji;
    else
        insert into public.rb_reactions (msg, who, emoji) values (mid, me, emoji);
    end if;
    return public.rb_msg_reacts(mid, me);
end $$;

create or replace function public.rb_msg_reacts(mid bigint, me uuid) returns json
language sql stable security definer set search_path = '' as $$
    select coalesce(json_object_agg(e, json_build_object('n', n, 'mine', mine)), '{}'::json) from (
        select r.emoji e, count(*) n, bool_or(r.who = me) mine from public.rb_reactions r where r.msg = mid group by r.emoji) x $$;

create or replace function public.rb_msg_get(name text) returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); o uuid;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select id into o from public.profiles where lower(username) = lower(name);
    if o is null then raise exception 'rb_no_such_user'; end if;
    update public.rb_messages set read = true where a = o and b = me and not read;
    return coalesce((select json_agg(json_build_object('id', m.id, 'mine', m.a = me, 'text', m.body, 'at', m.at,
                                                       'reacts', public.rb_msg_reacts(m.id, me)) order by m.id)
                       from (select * from public.rb_messages where (a = o and b = me) or (a = me and b = o)
                              order by id desc limit 80) m), '[]'::json);
end $$;

-- ================================================================ market search: item ids the app matched from names, plus filters
create or replace function public.rb_market_search(ids text[], kind text, rarity text, cls integer, sort text, page integer) returns json
language sql stable security definer set search_path = '' as $$
    select coalesce(json_agg(x), '[]'::json) from (
        select l.id as listing, l.what as item, l.price, p.username as seller, l.seller = auth.uid() as mine,
               public.rb_estimate(l.what) as estimate, c.rarity, c.worth
          from public.rb_listings l
          join public.profiles p on p.id = l.seller
          join public.rb_catalog c on c.id = l.what
         where l.state = 'open'
           and (rb_market_search.ids is null or l.what = any (rb_market_search.ids))
           and (coalesce(rb_market_search.kind, '') = '' or c.kind = rb_market_search.kind)
           and (coalesce(rb_market_search.rarity, '') = '' or c.rarity = rb_market_search.rarity)
           and (rb_market_search.cls is null or (c.kind = 'badge' and c.cls = rb_market_search.cls))
         order by case when rb_market_search.sort = 'cheap' then l.price end asc nulls last,
                  case when rb_market_search.sort = 'dear' then l.price end desc nulls last,
                  case when rb_market_search.sort = 'deal' then l.price::numeric / greatest(1, c.worth) end asc nulls last,
                  l.at desc
         limit 40 offset greatest(0, coalesce(rb_market_search.page, 0)) * 40) x $$;

-- ================================================================ the trade summary, from what really moved
create or replace function public.rb_trade_summary(trade uuid) returns json
language plpgsql stable security definer set search_path = '' as $$
declare me uuid := auth.uid(); t public.rb_trades%rowtype; mine text; other text;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into t from public.rb_trades where id = trade;
    if not found or (t.a <> me and t.b <> me) then raise exception 'rb_trade_gone'; end if;
    mine := case when t.a = me then 'a' else 'b' end; other := case when mine = 'a' then 'b' else 'a' end;
    return json_build_object('id', t.id, 'state', t.state, 'at', t.updated, 'undone', t.undone_at is not null,
        'other', (select username from public.profiles where id = case when mine = 'a' then t.b else t.a end),
        'got', coalesce((select json_agg(json_build_object('item', ti.what, 'worth', public.rb_worth(ti.what)) order by ti.what)
                           from public.rb_trade_items ti where ti.trade = t.id and ti.side = other), '[]'::json),
        'gave', coalesce((select json_agg(json_build_object('item', ti.what, 'worth', public.rb_worth(ti.what)) order by ti.what)
                            from public.rb_trade_items ti where ti.trade = t.id and ti.side = mine), '[]'::json),
        'coins_got', case when mine = 'a' then t.b_coins else t.a_coins end,
        'coins_gave', case when mine = 'a' then t.a_coins else t.b_coins end,
        'keys_got', case when mine = 'a' then t.b_keys else t.a_keys end,
        'keys_gave', case when mine = 'a' then t.a_keys else t.b_keys end);
end $$;

-- the other trader's items you can see while you trade (only the two people of an open trade; looking, never taking)
create or replace function public.rb_trade_inventory(trade uuid) returns json
language plpgsql stable security definer set search_path = '' as $$
declare me uuid := auth.uid(); t public.rb_trades%rowtype; other uuid;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into t from public.rb_trades where id = trade;
    if not found or (t.a <> me and t.b <> me) or t.state <> 'open' then raise exception 'rb_trade_gone'; end if;
    other := case when t.a = me then t.b else t.a end;
    return json_build_object('name', (select username from public.profiles where id = other),
        'items', coalesce((select json_agg(json_build_object('id', it.id, 'item', it.item, 'worth', public.rb_worth(it.item),
                                                             'offered', it.locked = 'trade:' || t.id)
                                           order by coalesce(c.worth, 0) desc, it.item)
                             from public.rb_items it join public.rb_catalog c on c.id = it.item
                            where it.owner = other and c.tradeable and c.kind not in ('prog', 'tag', 'coupon')
                              and (it.locked is null or it.locked = 'trade:' || t.id)), '[]'::json));
end $$;

-- ================================================================ level on profiles and boards
do $$ declare src text; begin
    select pg_get_functiondef('public.rb_profile(text)'::regprocedure) into src;
    if position('rb_xp_json' in src) = 0 then
        execute replace(src, '''admin'', p.admin, ''avatar_v'', p.avatar_v,', '''admin'', p.admin, ''avatar_v'', p.avatar_v, ''level'', public.rb_xp_json(p),');
    end if;
    select pg_get_functiondef('public.rb_state()'::regprocedure) into src;
    if position('rb_xp_json' in src) = 0 then
        execute replace(src, '''streak'', p.streak,', '''xp'', public.rb_xp_json(p), ''streak'', p.streak,');
    end if;
    select pg_get_functiondef('public.rb_leaders(text, boolean)'::regprocedure) into src;
    if position('''level''' in src) = 0 then
        src := replace(src, '''tap'', ''park'', ''memory'')', '''tap'', ''park'', ''memory'', ''level'')');
        src := replace(src, 'when ''coins'' then w.coins', 'when ''coins'' then w.coins when ''level'' then w.xp');
        execute src;
    end if;
end $$;

-- the avatars of up to 200 players at once (the app asks in batches)
create or replace function public.rb_avatars_get(names text[]) returns json
language sql stable security definer set search_path = '' as $$
    select coalesce(json_object_agg(lower(p.username), json_build_object('v', p.avatar_v, 'data', a.data)), '{}'::json)
      from public.profiles p join public.rb_avatars a on a.id = p.id
     where auth.uid() is not null
       and lower(p.username) in (select lower(n) from unnest(names[1:200]) n) $$;

-- the level badge of many players at once (friends lists, chat, boards)
create or replace function public.rb_levels_get(names text[]) returns json
language sql stable security definer set search_path = '' as $$
    select coalesce(json_object_agg(lower(p.username), json_build_object('level', p.level,
               'badge', case when p.level_badge >= 0 and p.level_badge <= p.level then p.level_badge else (p.level / 5) * 5 end)), '{}'::json)
      from public.profiles p
     where auth.uid() is not null and lower(p.username) in (select lower(n) from unnest(names[1:200]) n) $$;

-- RL Swap "Add" (admin): uploads use upsert, which Storage only allows with a SELECT policy too. Without it every
-- upload was refused by row level security.
do $$ begin
    if exists (select 1 from pg_namespace where nspname = 'storage') then
        drop policy if exists "rb swaps admin select" on storage.objects;
        create policy "rb swaps admin select" on storage.objects for select to authenticated
            using (bucket_id = 'swaps' and exists (select 1 from public.profiles p where p.id = auth.uid() and p.admin));
    end if;
end $$;

-- ================================================================ every action checks its lock (added at the start of each function)
do $$ declare r record; src text; fn regprocedure; pos integer; begin
    for r in select * from (values
        ('rb_trade_request(text)', 'trading'), ('rb_trade_accept(uuid)', 'trading'),
        ('rb_trade_offer(uuid, uuid[], integer, integer)', 'trading'), ('rb_trade_ready(uuid, boolean, integer)', 'trading'),
        ('rb_trade_confirm(uuid, integer)', 'trading'),
        ('rb_market_list(uuid, integer)', 'market'), ('rb_market_buy(uuid, text)', 'market'), ('rb_market_offer(uuid, integer)', 'market'),
        ('rb_market_answer(uuid, boolean)', 'market'), ('rb_quick_sell(uuid[], text)', 'market'), ('rb_sell(uuid, text)', 'market'),
        ('rb_blackjack(text, integer)', 'casino'), ('rb_dice(integer, integer, text)', 'casino'), ('rb_plinko(integer, integer, text)', 'casino'),
        ('rb_mines(text, integer)', 'casino'), ('rb_rocket(text, integer, numeric)', 'casino'), ('rb_timing(text, integer, integer, text)', 'casino'),
        ('rb_hilo(text, integer, text)', 'casino'),
        ('rb_mini_start()', 'minigames'), ('rb_mini_finish(uuid, jsonb)', 'minigames'), ('rb_tap_start(text)', 'minigames'),
        ('rb_tap_finish(uuid, jsonb)', 'minigames'), ('rb_park_start(integer)', 'minigames'), ('rb_park_finish(uuid, jsonb)', 'minigames'),
        ('rb_mem_start(integer)', 'minigames'), ('rb_mem_flip(uuid, integer)', 'minigames'),
        ('rb_duel_ask(text, text, integer, integer)', 'minigames'), ('rb_duel_play(uuid)', 'minigames'),
        ('rb_golf_create(integer)', 'golf'), ('rb_golf_join(uuid)', 'golf'),
        ('rb_gold_wheel()', 'wheel'),
        ('rb_open_case_gold(text, text)', 'cases'), ('rb_daily_case()', 'cases'), ('rb_case_gift(text, text, text)', 'gifts'),
        ('rb_buy(text, text)', 'shop'),
        ('rb_msg_send(text, text)', 'chat'),
        ('rb_giveaway_join(uuid)', 'giveaways'),
        ('rb_quest_claim(text)', 'quests'), ('rb_set_claim(text)', 'quests'),
        ('rb_login_claim()', 'quests')) v(sig, feat) loop
        fn := to_regprocedure('public.' || r.sig);
        if fn is null then continue; end if;
        select pg_get_functiondef(fn) into src;
        if position('rb_need_feature' in src) > 0 or position('LANGUAGE plpgsql' in src) = 0 then continue; end if;
        pos := position(E'\nbegin\n' in src);
        if pos = 0 then continue; end if;
        src := substr(src, 1, pos + 6) || '    perform public.rb_need_feature(''' || r.feat || ''');' || E'\n' || substr(src, pos + 7);
        execute src;
    end loop;
end $$;

-- golf shots: a lock ends the match (with refunds) and stops new shots
do $$ declare src text; begin
    select pg_get_functiondef('public.rb_golf_shot(uuid, integer, double precision, double precision, double precision, double precision, double precision, double precision, boolean)'::regprocedure) into src;
    if position('rb_need_feature' in src) = 0 then
        execute replace(src, 'if me is null then raise exception ''rb_not_logged_in''; end if;',
                        'if me is null then raise exception ''rb_not_logged_in''; end if;
    perform public.rb_need_feature(''golf'');');
    end if;
end $$;

-- golf holes: more of them (the app draws 40)
create or replace function public.rb_golf_pick() returns integer[]
language sql security definer set search_path = '' as $$
    select array_agg(h) from (
        select h + case when public.rb_rand() < 0.5 then 100 else 0 end as h
          from generate_series(1, coalesce(public.rb_cfg('golf_hole_total'), 24)::int) h order by public.rb_rand()
         limit greatest(1, least(9, coalesce(public.rb_cfg('golf_holes'), 5)::int))) x $$;

-- ================================================================ who may call what
do $$ declare f text; begin
    foreach f in array array['rb_feature_on(text)', 'rb_need_feature(text)', 'rb_feature_cleanup(text)', 'rb_xp_add(uuid, integer, text, text, boolean)',
                             'rb_xp_json(public.profiles)', 'rb_xp_cap(text)', 'rb_rounds_xp()', 'rb_golf_xp()', 'rb_trade_xp()', 'rb_claim_xp()',
                             'rb_coupon_pick(integer[])', 'rb_level_mult(uuid)', 'rb_spin_pay(public.profiles, jsonb)',
                             'rb_flip_name(uuid, text)', 'rb_flip_bot_items(bigint, integer)', 'rb_flip_bot_name()',
                             'rb_flip_bot_offer(bigint, boolean, text, text, integer, text[])', 'rb_flip_bots_tick()',
                             'rb_mg_pay(public.rb_mg, integer)', 'rb_msg_reacts(bigint, uuid)', 'rb_2048_replay(integer, bigint, text)',
                             'rb_lcg(bigint)', 'rb_tower_mult(integer, integer)', 'rb_xp_need(integer)', 'rb_xp_total(integer)', 'rb_level_of(bigint)',
                             'rb_quick_value(uuid, public.rb_items)', 'rb_estimate(text)', 'rb_price_all()',
                             'rb_admin_feature(text, boolean, text)', 'rb_admin_lockdown(boolean)', 'rb_admin_features()',
                             'rb_admin_xp(text, integer, text)', 'rb_admin_xp_view(text)', 'rb_admin_xp_watch()',
                             'rb_admin_flip_offer(text, text[], bigint, text, integer)', 'rb_admin_flip_cancel(uuid)', 'rb_admin_flips()',
                             'rb_locks()', 'rb_xp_me()', 'rb_level_badge_set(integer)', 'rb_coupon_use(uuid, text)',
                             'rb_scratch_odds()', 'rb_spin_odds()', 'rb_flip_put(uuid, uuid[])', 'rb_tower(text, integer, integer, text)',
                             'rb_keno(integer, integer[], text)', 'rb_keno_table()', 'rb_limbo(integer, numeric, text)', 'rb_mg_start(text, integer)',
                             'rb_2048_finish(uuid, text)', 'rb_sweep_open(uuid, integer)', 'rb_mg_board(text, integer, boolean)',
                             'rb_notices(bigint)', 'rb_notices_clear()', 'rb_msg_react(bigint, text)', 'rb_market_search(text[], text, text, integer, text, integer)',
                             'rb_trade_summary(uuid)', 'rb_levels_get(text[])', 'rb_trade_inventory(uuid)'] loop
        execute format('revoke all on function public.%s from public, anon, authenticated', f);
    end loop;
    -- the app (signed in) may call these; the admin ones check for an admin inside
    foreach f in array array['rb_locks()', 'rb_xp_me()', 'rb_level_badge_set(integer)', 'rb_coupon_use(uuid, text)',
                             'rb_scratch_odds()', 'rb_spin_odds()', 'rb_flip_put(uuid, uuid[])', 'rb_tower(text, integer, integer, text)',
                             'rb_keno(integer, integer[], text)', 'rb_keno_table()', 'rb_limbo(integer, numeric, text)', 'rb_mg_start(text, integer)',
                             'rb_2048_finish(uuid, text)', 'rb_sweep_open(uuid, integer)', 'rb_mg_board(text, integer, boolean)',
                             'rb_notices(bigint)', 'rb_notices_clear()', 'rb_msg_react(bigint, text)', 'rb_market_search(text[], text, text, integer, text, integer)',
                             'rb_trade_summary(uuid)', 'rb_levels_get(text[])', 'rb_trade_inventory(uuid)',
                             'rb_admin_feature(text, boolean, text)', 'rb_admin_lockdown(boolean)', 'rb_admin_features()',
                             'rb_admin_xp(text, integer, text)', 'rb_admin_xp_view(text)', 'rb_admin_xp_watch()',
                             'rb_admin_flip_offer(text, text[], bigint, text, integer)', 'rb_admin_flip_cancel(uuid)', 'rb_admin_flips()'] loop
        execute format('grant execute on function public.%s to authenticated', f);
    end loop;
end $$;

-- every price again, now that the bands and the new items are in
select public.rb_price_all();

-- apps older than 4.0 must update
insert into public.rb_config (key, value) values ('min_build', 2026111800)
on conflict (key) do update set value = greatest(public.rb_config.value, excluded.value);

-- 4.0 guard, last part: nobody lost anything (new XP coupons are the only new items; old spin prizes were paid).
do $$ declare bad int; begin
    select count(*) into bad from pg_temp.rb_guard021 g join public.profiles p on p.id = g.id
     where p.coins < g.coins or p.keys < g.keys
        or not (g.items <@ (select coalesce(array_agg(it.id::text || ':' || it.item), '{}') from public.rb_items it
                             where it.owner = p.id));
    if bad > 0 then raise exception 'rb_guard021: % accounts would lose something, nothing was changed', bad; end if;
    if exists (select 1 from public.rb_listings where state = 'open') then raise exception 'rb_guard021: listings left open'; end if;
    if exists (select 1 from public.rb_items where locked like 'market:%') then raise exception 'rb_guard021: items still locked'; end if;
    if (select count(*) from public.profiles) <> (select count(*) from pg_temp.rb_guard021) then
        raise exception 'rb_guard021: accounts changed';
    end if;
end $$;
