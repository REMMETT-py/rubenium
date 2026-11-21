-- Rubenium 5.15 (the final version). Applied on the live server on 21/11/2026.
-- The pawn shop, quests, daily case prices, deals and case lineup changes of 5.15 were run live earlier the same day.
-- Run the reset block (bottom) only once the 5.15 release is out and min_build points at it.

-- ================================================================ no more XP or casino limits
create or replace function public.rb_xp_cap(src text) returns integer language sql immutable set search_path to ''
as $$ select 100000000 $$;
update public.rb_config set value = 1000000000
 where key in ('cups_day_profit', 'c4_day_profit', 'mini_day_cap', 'park_day_cap', 'game_window_cap', 'mg_window_cap',
               'game_day_cap');

-- ================================================================ the free spin pays more (applied live with replace())
-- rb_spin and rb_spin_odds: slots 120, 200, 300, 450, 700, 1 200, 2 500, key, Golden Wheel, XP coupon;
-- odds 1730, 1700, 1700, 1300, 900, 600, 300, 770, 500, 500 (out of 10 000)
do $$
declare src text;
begin
  select pg_get_functiondef('public.rb_spin()'::regprocedure) into src;
  src := replace(src, 'array[40, 75, 120, 180, 300, 500, 1200, -1, -2, -3]', 'array[120, 200, 300, 450, 700, 1200, 2500, -1, -2, -3]');
  src := replace(src, 'array[1950, 1950, 1800, 1200, 750, 400, 180, 770, 500, 500]', 'array[1730, 1700, 1700, 1300, 900, 600, 300, 770, 500, 500]');
  execute src;
  select pg_get_functiondef('public.rb_spin_odds()'::regprocedure) into src;
  src := replace(src, 'json_build_array(40, 75, 120, 180, 300, 500, 1200, -1, -2, -3)', 'json_build_array(120, 200, 300, 450, 700, 1200, 2500, -1, -2, -3)');
  src := replace(src, 'json_build_array(1950, 1950, 1800, 1200, 750, 400, 180, 770, 500, 500)', 'json_build_array(1730, 1700, 1700, 1300, 900, 600, 300, 770, 500, 500)');
  execute src;
end $$;

-- ================================================================ admin: bots sell on the market
create or replace function public.rb_admin_bot_market(name text, action text, item_id uuid default null,
                                                      price integer default null, n integer default 3)
returns jsonb language plpgsql security definer set search_path to '' as $f$
declare me uuid := public.rb_need_admin(); p public.profiles%rowtype; it public.rb_items%rowtype; c public.rb_catalog%rowtype;
        est integer; lid uuid; x record; made integer := 0; out jsonb;
begin
    select * into p from public.profiles where lower(username) = lower(name);
    if not found or not p.bot then raise exception 'rb_bad_choice'; end if;
    if action = 'items' then
        select coalesce(jsonb_agg(jsonb_build_object('id', i.id, 'item', i.item, 'locked', i.locked,
                   'est', public.rb_estimate(i.item), 'tradeable', coalesce(k.tradeable, false),
                   'listing', l.id, 'price', l.price) order by i.got_at desc), '[]'::jsonb)
          into out
          from public.rb_items i left join public.rb_catalog k on k.id = i.item
          left join public.rb_listings l on l.item = i.id and l.state = 'open'
         where i.owner = p.id;
        return jsonb_build_object('items', out);
    elsif action = 'list' then
        select * into it from public.rb_items where id = item_id and owner = p.id for update;
        if not found then raise exception 'rb_not_yours'; end if;
        if it.locked is not null then raise exception 'rb_item_locked'; end if;
        select * into c from public.rb_catalog where id = it.item;
        if not coalesce(c.tradeable, false) then raise exception 'rb_not_tradeable'; end if;
        est := public.rb_estimate(it.item);
        if price is null or price < ceil(est * public.rb_cfg('market_min_mult'))
           or price > greatest(floor(est * public.rb_cfg('market_max_mult')), coalesce(c.price, 0)) then
            raise exception 'rb_bad_price';
        end if;
        insert into public.rb_listings (seller, item, what, price) values (p.id, it.id, it.item, price) returning id into lid;
        update public.rb_items set locked = 'market:' || lid where id = it.id;
        perform public.rb_log('bot_market', p.username, jsonb_build_object('item', it.item, 'price', price));
        return jsonb_build_object('listing', lid, 'price', price);
    elsif action = 'auto' then              -- list a few free, tradeable items near their worth
        for x in select i.id, i.item from public.rb_items i join public.rb_catalog k on k.id = i.item
                  where i.owner = p.id and i.locked is null and k.tradeable
                  order by public.rb_rand() limit greatest(1, least(coalesce(n, 3), 20)) loop
            est := public.rb_estimate(x.item);
            select * into c from public.rb_catalog where id = x.item;
            price := least(greatest(ceil(est * public.rb_cfg('market_min_mult'))::int,
                           round(est * (0.92 + public.rb_rand() * 0.33))::int),
                           greatest(floor(est * public.rb_cfg('market_max_mult'))::int, coalesce(c.price, 0)));
            insert into public.rb_listings (seller, item, what, price) values (p.id, x.id, x.item, greatest(1, price))
                returning id into lid;
            update public.rb_items set locked = 'market:' || lid where id = x.id;
            made := made + 1;
        end loop;
        perform public.rb_log('bot_market', p.username, jsonb_build_object('auto', made));
        return jsonb_build_object('listed', made);
    elsif action = 'cancel' then
        for x in select l.id, l.item from public.rb_listings l join public.rb_items i on i.id = l.item
                  where l.seller = p.id and l.state = 'open' and (item_id is null or l.item = item_id or l.id = item_id) loop
            update public.rb_listings set state = 'cancelled' where id = x.id;
            update public.rb_items set locked = null where id = x.item and locked = 'market:' || x.id;
            made := made + 1;
        end loop;
        return jsonb_build_object('cancelled', made);
    end if;
    raise exception 'rb_bad_choice';
end $f$;
revoke all on function public.rb_admin_bot_market(text, text, uuid, integer, integer) from public, anon;
grant execute on function public.rb_admin_bot_market(text, text, uuid, integer, integer) to authenticated;

-- ================================================================ the OG Prismatic Case: only on 5.15 (the remastered scene)
create or replace function public.rb_og_chest() returns json
language plpgsql stable security definer set search_path to '' as $function$
declare p public.profiles%rowtype; ends double precision := coalesce(public.rb_cfg('og_event_until'), 0);
begin
    select * into p from public.profiles where id = auth.uid();
    if not found then return json_build_object('due', false); end if;
    return json_build_object(
        'due', p.og_event_at is null and extract(epoch from now()) < ends and coalesce(p.build, 0) >= 2026112116
               and exists (select 1 from public.rb_items i where i.owner = p.id and i.item = 'tag:og'),
        'claimed', p.og_event_at is not null, 'ends', ends,
        'coins', coalesce(public.rb_cfg('og_chest_coins'), 5000)::int, 'keys', coalesce(public.rb_cfg('og_chest_keys'), 25)::int,
        'xp', coalesce(public.rb_cfg('og_chest_xp'), 750));
end $function$;

-- ================================================================ the 5.15 fresh start (once, ever). Game scores stay.
do $$
declare og uuid[];
begin
    if coalesce(public.rb_cfg('reset_515'), 0) <> 0 then return; end if;
    create table if not exists public.rb_bak515_profiles as select *, now() as saved_at from public.profiles;
    create table if not exists public.rb_bak515_items as select * from public.rb_items;
    create table if not exists public.rb_bak515_stock as select * from public.rb_case_stock;
    create table if not exists public.rb_bak515_listings as select * from public.rb_listings;
    create table if not exists public.rb_bak515_ledger as select * from public.rb_ledger;
    create table if not exists public.rb_bak515_xp_log as select * from public.rb_xp_log;
    alter table public.rb_bak515_profiles enable row level security;
    alter table public.rb_bak515_items enable row level security;
    alter table public.rb_bak515_stock enable row level security;
    alter table public.rb_bak515_listings enable row level security;
    alter table public.rb_bak515_ledger enable row level security;
    alter table public.rb_bak515_xp_log enable row level security;
    revoke all on public.rb_bak515_profiles, public.rb_bak515_items, public.rb_bak515_stock, public.rb_bak515_listings,
                  public.rb_bak515_ledger, public.rb_bak515_xp_log from anon, authenticated;

    select coalesce(array_agg(distinct owner), '{}') into og from public.rb_items where item = 'tag:og';

    delete from public.rb_rounds where open or game like 'case%' or game in ('scratch', 'spin', 'wheel', 'gold_wheel');
    delete from public.rb_mg where open;
    truncate public.rb_offers, public.rb_listings, public.rb_trade_items, public.rb_trades, public.rb_duels,
             public.rb_mem, public.rb_park, public.rb_mini, public.rb_flips,
             public.rb_golf, public.rb_golf_solo, public.rb_wave_duels, public.rb_pawn, public.rb_c4,
             public.rb_rigs, public.rb_giveaway_entries, public.rb_jackpot_entries, public.rb_jackpots,
             public.rb_items, public.rb_seen, public.rb_case_stock, public.rb_case_week, public.rb_deal_buys,
             public.rb_case_stats, public.rb_set_claims, public.rb_quest_claims, public.rb_requests, public.rb_inbox,
             public.rb_advent_claims, public.rb_xp_log, public.rb_wear, public.rb_ledger, public.rb_rate_hits;
    delete from public.rb_golf_party_seats;
    delete from public.rb_golf_parties;
    if to_regclass('public.rb_trash') is not null then execute 'truncate public.rb_trash'; end if;
    update public.rb_giveaways set state = 'cancelled', ends_at = least(ends_at, now()) where state = 'live';

    update public.profiles
       set coins = public.rb_cfg('start_coins')::bigint, keys = public.rb_cfg('start_keys')::int,
           coin_min = 0, key_min = 0, day = current_date, day_coins = 0,
           spin_at = null, spin_prize = null, daily_at = null, scratch_at = null,
           gold_keys = 0, og_event_at = null, gold_wheels = 0, rig_gold = false, og_coupon_50 = false,
           xp = 0, level = 0, level_badge = -1, xp_day = null, xp_day_gain = 0, xp_day_src = '{}'::jsonb,
           xp_hr = null, xp_hr_src = '{}'::jsonb,
           equip = coalesce((select jsonb_object_agg(e.key, e.value) from jsonb_each(coalesce(equip, '{}'::jsonb)) e
                              where e.value #>> '{}' like 'prog:%'), '{}'::jsonb);

    perform public.rb_og_give(x) from unnest(og) x;
    update public.profiles set coins = public.rb_cfg('og_start_coins')::bigint where id = any (og) and not bot;

    insert into public.rb_ledger (owner, coins, keys, reason, ref)
        select id, coins::int, keys, 'reset', '5.15' from public.profiles;
    insert into public.rb_config (key, value) values ('reset_515', 1) on conflict (key) do update set value = 1;
end $$;
update public.rb_config set value = 1796079600 where key = 'og_event_until';      -- 1/12/2026 00:00 Paris
