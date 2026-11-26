-- Rubenium 9.1, server part. Safe to run twice. Undo: 078_down.sql.
--
-- 1. Five wealth tiers: Poor x1, Average x1.3 (10 000), Investor x1.8 (75 000), Businessman x2.6 (400 000),
--    Casino Legend x4 (2 500 000). A tier once reached is kept (profiles.tier_floor): your wealth can go up and down
--    inside it, never below it.
-- 2. The Key Forge: cheaper (0.5% of your wealth, at least 250) and more a day the higher your tier (3, 5, 8, 12, 20).
-- 3. Style cases, one kind each: Ball, Line and Font cases join the Banner, Frame and App Colour cases. The Crown Vault
--    (20 000) holds all of them, and the animations.
-- 4. Animations: Shatter and Supernova (Epic, 25 000), Rift and Phoenix (Legendary, 60 000), Eclipse (Mythic, 150 000).
--    Each has Titanium (x2), Gold (x4) and Prismatic (x8) versions, sold only to owners of the base one, never in cases.
-- 5. One account creation per PC, ever (a deleted account does not free the PC). Logging in stays open everywhere.
-- 6. rb_reset_economy_91(): the 9.1 fresh start (run once by hand, after the owner says go). See the function.
begin;

-- ---------------------------------------------------------------- 1. tiers
alter table public.profiles add column if not exists tier_floor integer not null default 0;

insert into public.rb_config (key, value) values ('remaster_91', 1), ('forge_day_0', 3), ('forge_day_1', 5),
    ('forge_day_2', 8), ('forge_day_3', 12), ('forge_day_4', 20)
on conflict (key) do nothing;
update public.rb_config set value = v.value from (values
    ('tier_at_1', 10000), ('tier_at_2', 75000), ('tier_at_3', 400000), ('tier_at_4', 2500000),
    ('tier_x_0', 1.0), ('tier_x_1', 1.3), ('tier_x_2', 1.8), ('tier_x_3', 2.6), ('tier_x_4', 4.0),
    ('forge_pct', 0.005), ('forge_min', 250)
) as v(key, value) where rb_config.key = v.key and coalesce((select value from public.rb_config where key = 'remaster_91_set'), 0) = 0;
delete from public.rb_config where key in ('tier_at_5', 'tier_x_5')
   and coalesce((select value from public.rb_config where key = 'remaster_91_set'), 0) = 0;
insert into public.rb_config (key, value) values ('remaster_91_set', 1) on conflict (key) do nothing;

create or replace function public.rb_tier(who uuid) returns jsonb
language plpgsql stable security definer set search_path to '' as $$
declare w bigint := public.rb_wealth(who); t integer := 0; i integer; fl integer;
begin
    for i in 1 .. 4 loop
        if w >= coalesce(public.rb_cfg('tier_at_' || i), 1e18) then t := i; end if;
    end loop;
    fl := least(4, greatest(0, coalesce((select tier_floor from public.profiles where id = who), 0)));
    t := greatest(t, fl);
    return jsonb_build_object('tier', t, 'name', (array['Poor', 'Average', 'Investor', 'Businessman', 'Casino Legend'])[t + 1],
                              'mult', coalesce(public.rb_cfg('tier_x_' || t), 1), 'wealth', w,
                              'at', case when t > 0 then public.rb_cfg('tier_at_' || t) else 0 end,
                              'next', case when t < 4 then public.rb_cfg('tier_at_' || (t + 1)) end,
                              'next_name', case when t < 4 then (array['Poor', 'Average', 'Investor', 'Businessman',
                                                                      'Casino Legend'])[t + 2] end,
                              'top', 4);
end $$;

-- the tier a player has reached is kept: called whenever the tier is asked for
create or replace function public.rb_tier_keep(who uuid) returns integer
language plpgsql security definer set search_path to '' as $$
declare t integer := (public.rb_tier(who) ->> 'tier')::int;
begin
    update public.profiles set tier_floor = t where id = who and tier_floor < t;
    return t;
end $$;

create or replace function public.rb_my_tier() returns jsonb
language plpgsql volatile security definer set search_path to '' as $$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_tier_keep(auth.uid());
    return public.rb_tier(auth.uid()) || jsonb_build_object('forge', public.rb_forge_state(auth.uid()));
end $$;

-- ---------------------------------------------------------------- 2. the Key Forge
create or replace function public.rb_forge_state(who uuid) returns jsonb
language sql stable security definer set search_path to '' as $$
    with t as (select (public.rb_tier(who) ->> 'tier')::int as tier),
         d as (select coalesce(public.rb_cfg('forge_day_' || t.tier), public.rb_cfg('forge_day'), 5)::int as cap from t)
    select jsonb_build_object(
        'price', greatest(coalesce(public.rb_cfg('forge_min'), 250)::bigint,
                          (round(public.rb_wealth(who) * coalesce(public.rb_cfg('forge_pct'), 0.005) / 10) * 10)::bigint),
        'cap', d.cap,
        'left', greatest(0, d.cap - (select count(*)::int from public.rb_ledger l
              where l.owner = who and l.reason = 'forge' and l.at >= (public.rb_today()::timestamp at time zone 'Europe/Paris'))))
    from d $$;

-- ---------------------------------------------------------------- 3. style cases
update public.rb_cases set mode = 'kinds:ball', price = 900, coin_min = 220, coin_max = 680, pos = 24,
       odds = array[3000, 4300, 2000, 600, 100, 0]
 where id = 'style';
insert into public.rb_cases (id, pos, price, odds, coin_min, coin_max, exotics, pity_tier, pity_after, variants, mode,
                             limited, kind, min_level, grid, myth_ppb, step)
values ('lines', 25, 900, array[3000, 4300, 2000, 600, 100, 0], 220, 680, false, 9, 0, array[100000, 0, 0, 0, 0],
        'kinds:line', false, 'style', 0, null, 0, 25),
       ('fonts', 26, 1200, array[3000, 4300, 2000, 600, 100, 0], 300, 900, false, 9, 0, array[100000, 0, 0, 0, 0],
        'kinds:font', false, 'style', 0, null, 0, 25)
on conflict (id) do nothing;
update public.rb_cases set mode = 'kinds:banner,frame,theme,ball,line,font,anim', price = 20000, pos = 30,
       odds = array[1500, 0, 2600, 3600, 2000, 300], coin_min = 9000, coin_max = 18000
 where id = 'profile';

-- a case never gives an animation's Titanium, Gold or Prismatic version
create or replace function public.rb_pick_weighted(k text[], tier integer, klass integer) returns text
language sql security definer set search_path to '' as $$
    select c.id from public.rb_catalog c
     where c.kind = any (k) and c.rarity = (array['standard', 'rare', 'special', 'epic', 'exotic'])[tier]
       and (klass is null or c.cls = klass) and not c.limited
       and (c.kind = 'badge' or c.price is not null)
       and (c.kind <> 'anim' or position('-' in c.base) = 0)
     order by -ln(greatest(public.rb_rand(), 1e-12)) / c.weight limit 1 $$;

-- ---------------------------------------------------------------- 4. animations
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, worth, weight, limited)
values ('anim:eclipse', 'anim', 'eclipse', '', 'exotic', 150000, 7500, true, 0, 150000, 1, false)
on conflict (id) do nothing;
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, worth, weight, limited)
select 'anim:' || b.base || '-' || f.fin, 'anim', b.base || '-' || f.fin, '', b.rarity, b.price * f.x, b.price * f.x / 20,
       true, 0, b.price * f.x, 0.1, false
  from (values ('shatter', 'special', 25000), ('nova', 'special', 25000), ('rift', 'epic', 60000),
               ('phoenix', 'epic', 60000), ('eclipse', 'exotic', 150000)) as b(base, rarity, price),
       (values ('titanium', 2), ('gold', 4), ('prismatic', 8)) as f(fin, x)
on conflict (id) do nothing;
update public.rb_catalog c set rarity = b.rarity, price = b.price * f.x, value = b.price * f.x / 20,
       worth = b.price * f.x, weight = case when f.x = 1 then 1 else 0.1 end
  from (values ('shatter', 'special', 25000), ('nova', 'special', 25000), ('rift', 'epic', 60000),
               ('phoenix', 'epic', 60000), ('eclipse', 'exotic', 150000)) as b(base, rarity, price),
       (values ('', 1), ('-titanium', 2), ('-gold', 4), ('-prismatic', 8)) as f(fin, x)
 where c.id = 'anim:' || b.base || f.fin;
-- the two old titanium colours are no longer sold
update public.rb_catalog set price = null, weight = 0 where kind = 'anim' and (base like '%-blacktitan' or base like '%-whitetitan');

create or replace function public.rb_buy(what text, req text) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; c public.rb_catalog%rowtype; res jsonb; new_id uuid; cost integer; d record; sale_pct integer;
begin
    perform public.rb_need_feature('shop');
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into c from public.rb_catalog where id = what;
    if not found or c.price is null or c.kind in ('prog', 'tag') or c.limited then raise exception 'rb_not_for_sale'; end if;
    if c.kind = 'badge' and (c.cls >= 4 or c.rarity = 'exotic') then raise exception 'rb_not_for_sale'; end if;
    if c.kind = 'anim' and position('-' in c.base) > 0 then          -- 9.1: a version needs the base animation
        if split_part(c.base, '-', 2) not in ('titanium', 'gold', 'prismatic') then raise exception 'rb_not_for_sale'; end if;
        if not exists (select 1 from public.rb_items it
                        where it.owner = p.id and it.item = 'anim:' || split_part(c.base, '-', 1)) then
            raise exception 'rb_need_base';
        end if;
    end if;
    if c.kind <> 'badge' and exists (select 1 from public.rb_items it where it.owner = p.id and it.item = what) then
        raise exception 'rb_already_owned';
    end if;
    cost := public.rb_shop_price(what);
    select * into d from public.rb_deal_list() x where x.item = what limit 1;
    if found then                                          -- a deal: once per deal period (week, day or hour)
        if exists (select 1 from public.rb_deal_buys where owner = p.id and day = d.period and item = what) then
            sale_pct := coalesce((select max(s.pct) from public.rb_sales s
                                   where s.ends_at > now() and (rb_buy.what = s.what or rb_buy.what like s.what || ':%')), 0);
            cost := greatest(1, ceil(c.price * (1 + coalesce(public.rb_cfg('shop_tax'), 0)) * (100 - sale_pct) / 100.0))::int;
        else
            insert into public.rb_deal_buys (owner, day, item) values (p.id, d.period, what) on conflict do nothing;
        end if;
    end if;
    perform public.rb_pay(p.id, -cost, 0, 'shop', what);
    new_id := public.rb_give(p.id, what, 'shop');
    return public.rb_remember(p.id, req, jsonb_build_object('id', new_id, 'item', what, 'coins', p.coins - cost, 'paid', cost));
end $$;

-- ---------------------------------------------------------------- 5. one account creation per PC
create or replace function public.rb_device_free(pc text) returns json
language sql stable security definer set search_path to '' as $$
    select json_build_object('free', not exists (select 1 from public.rb_devices d where d.device = pc),
        'name', (select p.username from public.rb_devices d join public.profiles p on p.id = d.owner where d.device = pc)) $$;

create or replace function public.rb_new_user() returns trigger
language plpgsql security definer set search_path to '' as $$
declare
    name text := coalesce(new.raw_user_meta_data ->> 'username', '');
    pc text := left(coalesce(new.raw_user_meta_data ->> 'device', ''), 64);
begin
    if name !~ '^[A-Za-z0-9]{3,10}$' then raise exception 'rb_bad_username'; end if;
    if new.email is distinct from lower(name) || '@users.rubenium.app' then raise exception 'rb_bad_account'; end if;
    if exists (select 1 from public.profiles p where lower(p.username) = lower(name) or p.login = lower(name)) then
        raise exception 'rb_username_taken';
    end if;
    if pc like 'bot:%' then
        if not exists (select 1 from public.rb_bot_tickets t where t.token = substr(pc, 5)
                        and t.at > now() - interval '10 minutes') then raise exception 'rb_update_needed'; end if;
        delete from public.rb_bot_tickets where token = substr(pc, 5);
        insert into public.profiles (id, username, login, coins, keys, bot)
            values (new.id, name, lower(name), public.rb_cfg('start_coins'), public.rb_cfg('start_keys'), true);
        return new;
    end if;
    if pc !~ '^[a-f0-9]{32,64}$' then raise exception 'rb_update_needed'; end if;       -- an old version of the app
    if exists (select 1 from public.rb_devices d where d.device = pc) then             -- 9.1: one creation per PC, ever
        raise exception 'rb_device_used';
    end if;
    insert into public.profiles (id, username, login, coins, keys)
        values (new.id, name, lower(name), public.rb_cfg('start_coins'), public.rb_cfg('start_keys'));
    insert into public.rb_devices (device, owner) values (pc, new.id);
    return new;
end $$;

-- ---------------------------------------------------------------- 6. the 9.1 fresh start
-- Everyone: 0 coins, 0 keys, tier back to Poor. Kept: accounts, levels and XP, friends, hours, achievements, history,
-- the OG tag, and Common and Rare items in their basic look (grey or no colour). Gone: every Epic, Legendary and Mythic
-- item, every coloured, Titanium, Gold or Prismatic version, unopened cases, the OG chest (and its coupon), gold keys
-- and wheels, timers and streaks, rigs, and anything in play (it ends with no pay; items held go back first).
-- What was equipped and is gone is taken off. A copy of every changed table is kept in rb_bak91_*.
create or replace function public.rb_reset_economy_91() returns jsonb
language plpgsql security definer set search_path to '' as $$
declare n integer; gone integer; p record;
begin
    if coalesce(public.rb_cfg('reset_091'), 0) <> 0 then raise exception 'rb_already_done'; end if;

    create table public.rb_bak91_profiles as select *, now() as saved_at from public.profiles;
    create table public.rb_bak91_items as select * from public.rb_items;
    create table public.rb_bak91_stock as select * from public.rb_case_stock;
    create table public.rb_bak91_ledger as select * from public.rb_ledger;
    alter table public.rb_bak91_profiles enable row level security;
    alter table public.rb_bak91_items enable row level security;
    alter table public.rb_bak91_stock enable row level security;
    alter table public.rb_bak91_ledger enable row level security;
    revoke all on public.rb_bak91_profiles, public.rb_bak91_items, public.rb_bak91_stock, public.rb_bak91_ledger
        from public, anon, authenticated;

    -- anything in play ends with no pay; items held by it go back to their owners
    update public.rb_duels set state = 'cancelled', why = 'reset' where state not in ('done', 'cancelled');
    update public.rb_flips set state = 'cancelled', why = 'reset', done_at = now() where state not in ('done', 'cancelled');
    update public.rb_trades set state = 'cancelled', why = 'reset', updated = now() where state not in ('done', 'cancelled');
    update public.rb_golf set state = 'cancelled', why = 'reset', done_at = now() where state not in ('done', 'cancelled');
    update public.rb_golf_parties set state = 'cancelled', done_at = now() where state not in ('done', 'cancelled');
    update public.rb_golf_solo set state = 'quit', done_at = now() where state not in ('done', 'quit');
    update public.rb_wave_duels set state = 'cancelled', why = 'reset', done_at = now()
     where state not in ('done', 'cancelled');
    update public.rb_wave_runs set state = 'quit', done_at = now() where state not in ('done', 'quit');
    if to_regclass('public.rb_c4') is not null then
        execute 'update public.rb_c4 set state = ''done'', paid = 0, updated_at = now() where state <> ''done''';
    end if;
    update public.rb_item_swaps set state = 'cancelled', done_at = now() where state = 'open';
    update public.rb_offers set state = 'gone' where state = 'open';
    update public.rb_listings set state = 'cancelled' where state = 'open';
    delete from public.rb_jackpot_entries
     where jackpot in (select id from public.rb_jackpots where state not in ('done', 'empty'));
    update public.rb_jackpots set state = 'empty', total = 0 where state not in ('done', 'empty');
    delete from public.rb_race_bets where race in (select id from public.rb_races where state <> 'done');
    delete from public.rb_giveaway_entries
     where giveaway in (select id from public.rb_giveaways where state = 'live');
    update public.rb_giveaways set state = 'cancelled', ends_at = least(ends_at, now()) where state = 'live';
    update public.rb_rounds set open = false, paid = 0 where open;
    update public.rb_mg set open = false, void = true where open;
    update public.rb_items set locked = null where locked is not null;
    truncate public.rb_case_stock, public.rb_rigs, public.rb_requests, public.rb_deal_buys;

    -- items: Common and Rare in their basic look, and the OG tag
    delete from public.rb_items i
     where i.item <> 'tag:og'
       and not exists (select 1 from public.rb_catalog c where c.id = i.item and c.rarity in ('standard', 'rare')
                          and coalesce(c.variant, '') in ('', 'grey') and coalesce(c.cls, 0) = 0
                          and c.kind not in ('anim'));
    get diagnostics gone = row_count;

    update public.profiles
       set coins = 0, keys = 0, gold_keys = 0, gold_wheels = 0, rig_gold = false, tier_floor = 0,
           coin_min = 0, key_min = 0, day = current_date, day_coins = 0, og_event_at = coalesce(og_event_at, now()),
           spin_at = null, spin_prize = null, daily_at = null, scratch_at = null, streak = 0, streak_day = null;
    get diagnostics n = row_count;
    for p in select id from public.profiles loop
        perform public.rb_fix_equip(p.id);
    end loop;
    update public.rb_config set value = 0 where key = 'og_event_until';

    insert into public.rb_ledger (owner, coins, keys, reason, ref) select id, 0, 0, 'reset', '9.1' from public.profiles;
    insert into public.rb_config (key, value) values ('reset_091', 1) on conflict (key) do update set value = 1;
    return jsonb_build_object('players', n, 'items_removed', gone,
                              'items_kept', (select count(*) from public.rb_items));
end $$;

-- ---------------------------------------------------------------- grants
revoke all on function public.rb_tier(uuid), public.rb_tier_keep(uuid), public.rb_forge_state(uuid),
              public.rb_pick_weighted(text[], integer, integer), public.rb_reset_economy_91()
    from public, anon, authenticated;
revoke all on function public.rb_my_tier(), public.rb_buy(text, text) from public, anon;
grant execute on function public.rb_my_tier(), public.rb_buy(text, text) to authenticated;
revoke all on function public.rb_device_free(text) from public;
grant execute on function public.rb_device_free(text) to anon, authenticated;

commit;
