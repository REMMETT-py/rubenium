-- Rubenium 008: THE ULTIMATE UPDATE. Trading, market, Beat Tap, new badges and cases, quests, social,
-- gifts, giveaways, sales and the admin panel.
-- Every item is one row with its own id, so an item can never exist twice. Items in a trade or on the market
-- are locked. Every move happens in one transaction: everything moves or nothing does.
-- Safe to run more than once. Needs 001 to 005 first (007 is not needed any more: it is inside this file).
-- Run it in Supabase: SQL Editor > New query > paste > Run.

insert into public.rb_config (key, value) values
    ('trade_min_minutes', 300),          -- 5 hours played before trading or the market
    ('trade_max_open', 5), ('trade_idle_min', 15), ('trade_ask_min', 5), ('trade_seen_s', 60),
    ('market_fee', 0.05), ('market_min_mult', 0.25), ('market_max_mult', 10), ('market_max_listings', 20),
    ('mini_full_rounds', 10), ('mini_day_cap', 300)
on conflict (key) do nothing;

-- ---------------------------------------------------------------- shared helpers
-- take off anything worn that this account no longer owns
create or replace function public.rb_fix_equip(who uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; e jsonb; k text; v text;
begin
    select * into p from public.profiles where id = who;
    e := coalesce(p.equip, '{}'::jsonb);
    for k, v in select key, value from jsonb_each_text(e) loop
        if not public.rb_can_wear(p, v) then e := e - k; end if;
    end loop;
    update public.profiles set equip = e where id = who;
end $$;

-- ---------------------------------------------------------------- market
create table if not exists public.rb_listings (
    id uuid primary key default gen_random_uuid(),
    seller uuid not null references public.profiles (id) on delete cascade,
    item uuid not null, what text not null, price integer not null check (price > 0),
    state text not null default 'open' check (state in ('open', 'sold', 'cancelled')),
    buyer uuid references public.profiles (id) on delete set null,
    at timestamptz not null default now(), sold_at timestamptz);
create unique index if not exists rb_listings_one_open on public.rb_listings (item) where state = 'open';
create index if not exists rb_listings_open on public.rb_listings (what, price) where state = 'open';
create index if not exists rb_listings_sold on public.rb_listings (what, sold_at desc) where state = 'sold';

-- what an item is worth: the middle of its last sales on the market, or its catalogue value
create or replace function public.rb_estimate(what text) returns integer
language sql stable security definer set search_path = '' as $$
    select coalesce((select percentile_disc(0.5) within group (order by s.price)
                       from (select l.price from public.rb_listings l
                              where l.what = rb_estimate.what and l.state = 'sold'
                              order by l.sold_at desc limit 15) s),
                    (select c.value from public.rb_catalog c where c.id = rb_estimate.what), 0)::int $$;

create or replace function public.rb_can_trade(p public.profiles) returns boolean
language sql stable security definer set search_path = '' as $$
    select p.minutes >= public.rb_cfg('trade_min_minutes') $$;

create or replace function public.rb_market_list(item_id uuid, price integer) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; it public.rb_items%rowtype; c public.rb_catalog%rowtype; est integer;
        lid uuid;
begin
    p := public.rb_lock_me();
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    select * into it from public.rb_items where id = item_id and owner = p.id for update;
    if not found then raise exception 'rb_not_yours'; end if;
    if it.locked is not null then raise exception 'rb_item_locked'; end if;
    select * into c from public.rb_catalog where id = it.item;
    if not c.tradeable then raise exception 'rb_not_tradeable'; end if;
    est := public.rb_estimate(it.item);
    if price is null or price < ceil(est * public.rb_cfg('market_min_mult'))
       or price > floor(est * public.rb_cfg('market_max_mult')) then
        raise exception 'rb_bad_price';
    end if;
    if (select count(*) from public.rb_listings where seller = p.id and state = 'open') >= public.rb_cfg('market_max_listings') then
        raise exception 'rb_too_many_listings';
    end if;
    insert into public.rb_listings (seller, item, what, price) values (p.id, it.id, it.item, price) returning id into lid;
    update public.rb_items set locked = 'market:' || lid where id = it.id;
    return jsonb_build_object('listing', lid, 'price', price);
end $$;

create or replace function public.rb_market_cancel(listing uuid) returns boolean
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; l public.rb_listings%rowtype;
begin
    p := public.rb_lock_me();
    select * into l from public.rb_listings where id = listing and seller = p.id for update;
    if not found or l.state <> 'open' then raise exception 'rb_not_listed'; end if;
    update public.rb_listings set state = 'cancelled' where id = l.id;
    update public.rb_items set locked = null where id = l.item and locked = 'market:' || l.id;
    return true;
end $$;

create or replace function public.rb_market_buy(listing uuid, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); l public.rb_listings%rowtype; buyer public.profiles%rowtype; res jsonb;
        fee integer; got integer;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into l from public.rb_listings where id = listing for update;          -- one buyer at a time
    if not found then raise exception 'rb_not_listed'; end if;
    perform 1 from public.profiles where id in (me, l.seller) order by id for update; -- always the same order
    res := public.rb_done(me, req);
    if res is not null then return res; end if;
    if l.state <> 'open' then raise exception 'rb_sold'; end if;
    if l.seller = me then raise exception 'rb_own_listing'; end if;
    select * into buyer from public.profiles where id = me;
    if not public.rb_can_trade(buyer) then raise exception 'rb_trade_locked'; end if;
    if not exists (select 1 from public.rb_items where id = l.item and owner = l.seller and locked = 'market:' || l.id) then
        update public.rb_listings set state = 'cancelled' where id = l.id;
        raise exception 'rb_not_listed';
    end if;
    fee := ceil(l.price * public.rb_cfg('market_fee'))::int;
    got := l.price - fee;
    perform public.rb_pay(me, -l.price, 0, 'market_buy', l.what);
    perform public.rb_pay(l.seller, got, 0, 'market_sell', l.what);
    update public.rb_items set owner = me, locked = null, origin = 'market' where id = l.item;
    insert into public.rb_seen (owner, item) values (me, l.what) on conflict do nothing;
    update public.rb_listings set state = 'sold', buyer = me, sold_at = now() where id = l.id;
    perform public.rb_fix_equip(l.seller);
    return public.rb_remember(me, req, jsonb_build_object('id', l.item, 'item', l.what, 'paid', l.price,
                                                          'coins', buyer.coins - l.price));
end $$;

-- open listings (newest first, or cheapest first), with an estimated value for each
create or replace function public.rb_market_browse(kind text, sort text, page integer) returns json
language sql stable security definer set search_path = '' as $$
    select coalesce(json_agg(x), '[]'::json) from (
        select l.id as listing, l.what as item, l.price, p.username as seller, l.seller = auth.uid() as mine,
               public.rb_estimate(l.what) as estimate, c.rarity
          from public.rb_listings l
          join public.profiles p on p.id = l.seller
          join public.rb_catalog c on c.id = l.what
         where l.state = 'open' and (coalesce(kind, '') = '' or c.kind = kind)
         order by case when sort = 'cheap' then l.price end asc nulls last, l.at desc
         limit 40 offset greatest(0, coalesce(page, 0)) * 40) x $$;

create or replace function public.rb_market_mine() returns json
language sql stable security definer set search_path = '' as $$
    select coalesce(json_agg(json_build_object('listing', l.id, 'item', l.what, 'price', l.price, 'state', l.state,
                                               'at', l.sold_at, 'buyer', (select username from public.profiles where id = l.buyer))
                             order by l.at desc), '[]'::json)
      from (select * from public.rb_listings where seller = auth.uid()
             and (state = 'open' or (state = 'sold' and sold_at > now() - interval '7 days'))
             order by at desc limit 40) l $$;

create or replace function public.rb_market_price(what text) returns json
language sql stable security definer set search_path = '' as $$
    select json_build_object('estimate', public.rb_estimate(what),
        'min', ceil(public.rb_estimate(what) * public.rb_cfg('market_min_mult')),
        'max', floor(public.rb_estimate(what) * public.rb_cfg('market_max_mult')),
        'sales', coalesce((select json_agg(s.price) from (select price from public.rb_listings
                            where rb_listings.what = rb_market_price.what and state = 'sold'
                            order by sold_at desc limit 10) s), '[]'::json)) $$;

-- ---------------------------------------------------------------- trading
create table if not exists public.rb_trades (
    id uuid primary key default gen_random_uuid(),
    a uuid not null references public.profiles (id) on delete cascade,          -- who asked
    b uuid not null references public.profiles (id) on delete cascade,
    a_coins integer not null default 0 check (a_coins >= 0), b_coins integer not null default 0 check (b_coins >= 0),
    a_ready boolean not null default false, b_ready boolean not null default false,
    a_ok boolean not null default false, b_ok boolean not null default false,
    ready_at timestamptz, a_seen timestamptz not null default now(), b_seen timestamptz not null default now(),
    version integer not null default 1,
    state text not null default 'asked' check (state in ('asked', 'open', 'done', 'cancelled')),
    why text, at timestamptz not null default now(), updated timestamptz not null default now(),
    check (a <> b));
create index if not exists rb_trades_a on public.rb_trades (a) where state in ('asked', 'open');
create index if not exists rb_trades_b on public.rb_trades (b) where state in ('asked', 'open');
create table if not exists public.rb_trade_items (
    trade uuid not null references public.rb_trades (id) on delete cascade,
    side text not null check (side in ('a', 'b')), item uuid not null, what text not null,
    primary key (trade, item));

do $$ declare t text; begin
    foreach t in array array['rb_listings', 'rb_trades', 'rb_trade_items'] loop
        execute format('alter table public.%I enable row level security', t);
        execute format('revoke all on public.%I from anon, authenticated', t);
    end loop;
end $$;

create or replace function public.rb_trade_end(t uuid, why text) returns void
language plpgsql security definer set search_path = '' as $$
begin
    update public.rb_items set locked = null where locked = 'trade:' || t;
    update public.rb_trades set state = 'cancelled', why = rb_trade_end.why, updated = now()
     where id = t and state in ('asked', 'open');
end $$;

-- a trade nobody looks at any more ends by itself (items go back to being free)
create or replace function public.rb_trade_expire(who uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare t public.rb_trades%rowtype;
begin
    for t in select * from public.rb_trades where (a = who or b = who) and state in ('asked', 'open') for update skip locked loop
        if (t.state = 'asked' and now() - t.at > make_interval(mins => public.rb_cfg('trade_ask_min')::int))
           or now() - t.updated > make_interval(mins => public.rb_cfg('trade_idle_min')::int)
           or (t.state = 'open' and (now() - t.a_seen > make_interval(secs => public.rb_cfg('trade_seen_s')::int)
                                  or now() - t.b_seen > make_interval(secs => public.rb_cfg('trade_seen_s')::int))) then
            perform public.rb_trade_end(t.id, 'expired');
        end if;
    end loop;
end $$;

create or replace function public.rb_trade_request(name text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; them public.profiles%rowtype; tid uuid;
begin
    p := public.rb_lock_me();
    if not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    select * into them from public.profiles where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    if them.id = p.id then raise exception 'rb_thats_you'; end if;
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
end $$;

create or replace function public.rb_trade_accept(trade uuid) returns boolean
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); t public.rb_trades%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_trade_expire(me);
    select * into t from public.rb_trades where id = trade for update;
    if not found or t.b <> me or t.state <> 'asked' then raise exception 'rb_trade_gone'; end if;
    update public.rb_trades set state = 'open', a_seen = now(), b_seen = now(), updated = now() where id = t.id;
    return true;
end $$;

create or replace function public.rb_trade_cancel(trade uuid) returns boolean
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); t public.rb_trades%rowtype;
begin
    select * into t from public.rb_trades where id = trade for update;
    if not found or me is null or (t.a <> me and t.b <> me) then raise exception 'rb_trade_gone'; end if;
    perform public.rb_trade_end(t.id, 'cancelled');
    return true;
end $$;

-- Put items and coins on my side. Any change makes both players un-ready.
create or replace function public.rb_trade_offer(trade uuid, items uuid[], coins integer) returns integer
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); t public.rb_trades%rowtype; my text; p public.profiles%rowtype; n integer;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into t from public.rb_trades where id = trade for update;
    if not found or (t.a <> me and t.b <> me) or t.state <> 'open' then raise exception 'rb_trade_gone'; end if;
    my := case when t.a = me then 'a' else 'b' end;
    items := coalesce(items, '{}');
    n := coalesce(array_length(items, 1), 0);
    if n > 8 or n <> (select count(distinct x) from unnest(items) x) then raise exception 'rb_bad_offer'; end if;
    select * into p from public.profiles where id = me;
    if coins is null or coins < 0 or coins > p.coins then raise exception 'rb_not_enough'; end if;
    -- free what was on my side, then lock what is offered now
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
           a_ready = false, b_ready = false, a_ok = false, b_ok = false, ready_at = null,
           version = version + 1, updated = now()
     where id = t.id;
    return t.version + 1;
end $$;

create or replace function public.rb_trade_ready(trade uuid, ready boolean, seen_version integer) returns boolean
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); t public.rb_trades%rowtype;
begin
    select * into t from public.rb_trades where id = trade for update;
    if not found or me is null or (t.a <> me and t.b <> me) or t.state <> 'open' then raise exception 'rb_trade_gone'; end if;
    if t.version <> seen_version then raise exception 'rb_trade_changed'; end if;     -- you must see what you accept
    if t.a = me then t.a_ready := ready; else t.b_ready := ready; end if;
    update public.rb_trades set a_ready = t.a_ready, b_ready = t.b_ready, a_ok = false, b_ok = false,
           ready_at = case when t.a_ready and t.b_ready then now() end, updated = now()
     where id = t.id;
    return true;
end $$;

-- After both are ready and 5 seconds have passed, both confirm. The second confirm makes the exchange.
create or replace function public.rb_trade_confirm(trade uuid, seen_version integer) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); t public.rb_trades%rowtype; pa public.profiles%rowtype; pb public.profiles%rowtype;
        bad boolean;
begin
    select * into t from public.rb_trades where id = trade for update;
    if not found or me is null or (t.a <> me and t.b <> me) or t.state <> 'open' then raise exception 'rb_trade_gone'; end if;
    if t.version <> seen_version then raise exception 'rb_trade_changed'; end if;
    if not (t.a_ready and t.b_ready) or t.ready_at is null then raise exception 'rb_not_ready'; end if;
    if now() < t.ready_at + interval '5 seconds' then raise exception 'rb_wait'; end if;
    if t.a = me then t.a_ok := true; else t.b_ok := true; end if;
    update public.rb_trades set a_ok = t.a_ok, b_ok = t.b_ok, updated = now() where id = t.id;
    if not (t.a_ok and t.b_ok) then return jsonb_build_object('done', false); end if;
    -- the exchange: both accounts locked in the same order every time, everything checked again
    perform 1 from public.profiles where id in (t.a, t.b) order by id for update;
    select * into pa from public.profiles where id = t.a;
    select * into pb from public.profiles where id = t.b;
    perform 1 from public.rb_items where id in (select item from public.rb_trade_items where rb_trade_items.trade = t.id)
      order by id for update;
    select exists (select 1 from public.rb_trade_items ti left join public.rb_items it on it.id = ti.item
                    where ti.trade = t.id
                      and (it.id is null or it.owner <> (case ti.side when 'a' then t.a else t.b end)
                           or it.locked is distinct from 'trade:' || t.id)) into bad;
    if bad or pa.coins < t.a_coins or pb.coins < t.b_coins then
        perform public.rb_trade_end(t.id, 'failed');
        return jsonb_build_object('done', false, 'failed', true);
    end if;
    update public.rb_items it set owner = case ti.side when 'a' then t.b else t.a end, locked = null, origin = 'trade'
      from public.rb_trade_items ti where ti.trade = t.id and ti.item = it.id;
    insert into public.rb_seen (owner, item)
        select case ti.side when 'a' then t.b else t.a end, ti.what from public.rb_trade_items ti where ti.trade = t.id
        on conflict do nothing;
    perform public.rb_pay(t.a, t.b_coins - t.a_coins, 0, 'trade', t.id::text);
    perform public.rb_pay(t.b, t.a_coins - t.b_coins, 0, 'trade', t.id::text);
    perform public.rb_fix_equip(t.a);
    perform public.rb_fix_equip(t.b);
    update public.rb_trades set state = 'done', updated = now() where id = t.id;
    return jsonb_build_object('done', true);
end $$;

-- Everything about one trade (also tells the server this player is still there).
create or replace function public.rb_trade_get(trade uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); t public.rb_trades%rowtype; mine text;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_trade_expire(me);
    select * into t from public.rb_trades where id = trade;
    if not found or (t.a <> me and t.b <> me) then raise exception 'rb_trade_gone'; end if;
    mine := case when t.a = me then 'a' else 'b' end;
    if t.state = 'open' then
        update public.rb_trades set a_seen = case when mine = 'a' then now() else a_seen end,
                                    b_seen = case when mine = 'b' then now() else b_seen end where id = t.id;
    end if;
    return json_build_object('id', t.id, 'state', t.state, 'why', t.why, 'version', t.version, 'me', mine,
        'a', (select username from public.profiles where id = t.a), 'b', (select username from public.profiles where id = t.b),
        'a_coins', t.a_coins, 'b_coins', t.b_coins, 'a_ready', t.a_ready, 'b_ready', t.b_ready,
        'a_ok', t.a_ok, 'b_ok', t.b_ok,
        'wait', case when t.ready_at is null then null
                     else greatest(0, 5 - extract(epoch from (now() - t.ready_at))) end,
        'items', coalesce((select json_agg(json_build_object('side', ti.side, 'id', ti.item, 'item', ti.what,
                                                             'estimate', public.rb_estimate(ti.what)))
                             from public.rb_trade_items ti where ti.trade = t.id), '[]'::json));
end $$;

-- My trades waiting or open, and the last ones that ended.
create or replace function public.rb_trades_list() returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_trade_expire(me);
    return coalesce((select json_agg(json_build_object('id', t.id, 'state', t.state, 'why', t.why,
               'with', (select username from public.profiles where id = case when t.a = me then t.b else t.a end),
               'mine', t.a = me, 'at', t.updated) order by t.state in ('asked', 'open') desc, t.updated desc)
       from (select * from public.rb_trades where (a = me or b = me)
              and (state in ('asked', 'open') or updated > now() - interval '7 days')
              order by updated desc limit 30) t), '[]'::json);
end $$;

-- ---------------------------------------------------------------- my coin history
create or replace function public.rb_ledger_list() returns json
language sql stable security definer set search_path = '' as $$
    select coalesce(json_agg(json_build_object('coins', l.coins, 'keys', l.keys, 'reason', l.reason, 'ref', l.ref,
                                               'at', l.at) order by l.id desc), '[]'::json)
      from (select * from public.rb_ledger where owner = auth.uid() order by id desc limit 80) l $$;

-- ---------------------------------------------------------------- Beat Tap (the minigame)
create table if not exists public.rb_mini (
    id uuid primary key default gen_random_uuid(),
    owner uuid not null references public.profiles (id) on delete cascade,
    at timestamptz not null default clock_timestamp(), pattern jsonb not null,
    open boolean not null default true, score integer not null default 0, paid integer not null default 0);
create unique index if not exists rb_mini_one_open on public.rb_mini (owner) where open;
create index if not exists rb_mini_day on public.rb_mini (owner, at desc);
alter table public.rb_mini enable row level security;
revoke all on public.rb_mini from anon, authenticated;

create or replace function public.rb_mini_day(who uuid) returns json
language sql stable security definer set search_path = '' as $$
    select json_build_object('rounds', count(*), 'paid', coalesce(sum(paid), 0),
                             'cap', public.rb_cfg('mini_day_cap'), 'full', public.rb_cfg('mini_full_rounds'))
      from public.rb_mini where owner = who and not open and at >= date_trunc('day', now()) $$;

create or replace function public.rb_mini_start() returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; pat jsonb := '[]'::jsonb; t integer := 2000; i integer; rid uuid;
begin
    p := public.rb_lock_me();
    update public.rb_mini set open = false where owner = p.id and open;      -- an unfinished round counts as 0
    for i in 1 .. 24 loop
        pat := pat || jsonb_build_object('t', t, 'x', round((0.14 + public.rb_rand() * 0.72)::numeric, 3),
                                         'y', round((0.18 + public.rb_rand() * 0.64)::numeric, 3));
        t := t + 850 + floor(public.rb_rand() * 650)::int;
    end loop;
    insert into public.rb_mini (owner, pattern) values (p.id, pat) returning id into rid;
    return json_build_object('round', rid, 'pattern', pat, 'day', public.rb_mini_day(p.id));
end $$;

-- hits: [{"i": target number, "t": milliseconds after the start}]. The server checks every hit against the
-- pattern and against its own clock, so a round cannot be finished early or replayed.
create or replace function public.rb_mini_finish(round uuid, hits jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r public.rb_mini%rowtype; elapsed double precision; last integer; n integer;
        h jsonb; i integer; dt double precision; pts integer := 0; seen integer[] := '{}'; pay integer := 0;
        day json; done_rounds integer; paid_today integer; spread double precision; dts double precision[] := '{}';
begin
    p := public.rb_lock_me();
    select * into r from public.rb_mini where id = round and owner = p.id for update;
    if not found or not r.open then raise exception 'rb_round_gone'; end if;
    elapsed := extract(epoch from (clock_timestamp() - r.at)) * 1000;
    n := jsonb_array_length(r.pattern);
    last := (r.pattern -> (n - 1) ->> 't')::int;
    update public.rb_mini set open = false where id = r.id;
    if elapsed < last - 1500 or elapsed > last + 180000 then
        return jsonb_build_object('score', 0, 'paid', 0, 'why', 'time', 'coins', p.coins);
    end if;
    for h in select * from jsonb_array_elements(coalesce(hits, '[]'::jsonb)) loop
        i := (h ->> 'i')::int;
        if i is null or i < 0 or i >= n or i = any (seen) then continue; end if;
        if (h ->> 't')::double precision > elapsed + 1500 then continue; end if;          -- a hit from the future
        dt := abs((h ->> 't')::double precision - (r.pattern -> i ->> 't')::double precision);
        if dt <= 550 then
            seen := seen || i;
            dts := dts || dt;
            pts := pts + case when dt <= 120 then 3 when dt <= 300 then 2 else 1 end;
        end if;
    end loop;
    day := public.rb_mini_day(p.id);
    done_rounds := (day ->> 'rounds')::int;
    paid_today := (day ->> 'paid')::int;
    if pts > 0 then
        pay := round(10 + 30.0 * pts / (3 * n));
        select stddev_pop(x) into spread from unnest(dts) x;
        if array_length(dts, 1) >= n - 1 and coalesce(spread, 0) < 6 then pay := 10; end if;   -- too perfect for a hand
        if done_rounds >= public.rb_cfg('mini_full_rounds') * 2 then pay := pay / 4;
        elsif done_rounds >= public.rb_cfg('mini_full_rounds') then pay := pay / 2; end if;
        pay := greatest(0, least(pay, public.rb_cfg('mini_day_cap')::int - paid_today));
    end if;
    update public.rb_mini set score = pts, paid = pay where id = r.id;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'mini', 0, jsonb_build_object('score', pts), false, pay);
    perform public.rb_pay(p.id, pay, 0, 'minigame', null);
    return jsonb_build_object('score', pts, 'max', 3 * n, 'hits', coalesce(array_length(seen, 1), 0), 'paid', pay,
                              'coins', p.coins + pay, 'day', public.rb_mini_day(p.id));
end $$;


-- ================================================================ PART 2: the rest of the Ultimate Update
insert into public.rb_config (key, value) values ('spin_hours', 2), ('vendor_share', 0),
    ('coin_every_min', 10), ('coin_amount', 20), ('coin_day_cap', 1200),
    ('price_standard', 150), ('price_rare', 450), ('price_special', 1200), ('price_epic', 3000), ('value_exotic', 15000)
on conflict (key) do update set value = excluded.value;
insert into public.rb_config (key, value) values ('app_locked', 0), ('offer_min_share', 0.5), ('offers_max', 10)
on conflict (key) do nothing;
insert into public.rb_config (key, value) values
    ('rocket_min', 1.2), ('gift_day', 3), ('rename_hours', 24), ('giveaway_min_minutes', 60)
on conflict (key) do nothing;

alter table public.profiles add column if not exists admin boolean not null default false;
alter table public.profiles add column if not exists banned boolean not null default false;
alter table public.profiles add column if not exists login text;
alter table public.profiles add column if not exists renamed_at timestamptz;
alter table public.profiles add column if not exists avatar_v integer not null default 0;
update public.profiles set login = lower(username) where login is null;
create unique index if not exists profiles_login on public.profiles (login);
update public.profiles set admin = true where lower(username) = 'ruben';

alter table public.rb_catalog add column if not exists cls integer not null default 0;   -- 0 basic 1 painted 2 shiny 3 titanium 4 gold
alter table public.rb_cases add column if not exists variants integer[] not null default '{10000,0,0,0,0}';
alter table public.rb_cases add column if not exists mode text not null default '';

create table if not exists public.rb_quest_claims (
    owner uuid not null references public.profiles (id) on delete cascade,
    quest text not null, period timestamptz not null, at timestamptz not null default now(),
    primary key (owner, quest, period));
alter table public.rb_quest_claims alter column period type timestamptz using period::timestamptz;

create table if not exists public.rb_devices (                 -- one account per PC
    device text primary key, owner uuid references public.profiles (id) on delete set null,
    at timestamptz not null default now());
create table if not exists public.rb_case_stock (              -- cases received as a gift or from the admin
    owner uuid not null references public.profiles (id) on delete cascade, case_id text not null,
    n integer not null default 0 check (n >= 0), primary key (owner, case_id));
create table if not exists public.rb_avatars (
    id uuid primary key references public.profiles (id) on delete cascade,
    data text not null check (length(data) <= 40000));
create table if not exists public.rb_inbox (                   -- small messages shown once ("Max gifted you a case")
    id bigserial primary key, owner uuid not null references public.profiles (id) on delete cascade,
    kind text not null, data jsonb not null default '{}'::jsonb, at timestamptz not null default now());
create index if not exists rb_inbox_owner on public.rb_inbox (owner);
create table if not exists public.rb_audit (                   -- everything the admin does, for ever
    id bigserial primary key, admin uuid, action text not null, target text, detail jsonb,
    at timestamptz not null default now());
create table if not exists public.rb_giveaways (
    id uuid primary key default gen_random_uuid(), title text not null,
    kind text not null check (kind in ('coins', 'keys', 'item', 'case')), what text not null default '',
    amount integer not null check (amount > 0), winners integer not null check (winners between 1 and 50),
    min_minutes integer not null default 0, ends_at timestamptz not null,
    state text not null default 'live' check (state in ('live', 'done', 'cancelled')),
    result jsonb, at timestamptz not null default now());
create table if not exists public.rb_giveaway_entries (
    giveaway uuid not null references public.rb_giveaways (id) on delete cascade,
    owner uuid not null references public.profiles (id) on delete cascade, primary key (giveaway, owner));
create table if not exists public.rb_sales (
    id uuid primary key default gen_random_uuid(), what text not null,
    pct integer not null check (pct between 1 and 90), ends_at timestamptz not null,
    at timestamptz not null default now());
do $$ declare t text; begin
    foreach t in array array['rb_quest_claims', 'rb_devices', 'rb_case_stock', 'rb_avatars', 'rb_inbox', 'rb_audit',
                             'rb_giveaways', 'rb_giveaway_entries', 'rb_sales'] loop
        execute format('alter table public.%I enable row level security', t);
        execute format('revoke all on public.%I from anon, authenticated', t);
    end loop;
end $$;

-- ---------------------------------------------------------------- one time: a fresh economy (accounts, hours and friends stay)
do $$ begin
    if not exists (select 1 from public.rb_config where key = 'reset_008') then
        delete from public.rb_trade_items; delete from public.rb_trades; delete from public.rb_listings;
        delete from public.rb_items; delete from public.rb_seen; delete from public.rb_ledger;
        delete from public.rb_rounds; delete from public.rb_case_stats; delete from public.rb_requests;
        delete from public.rb_quest_claims; delete from public.rb_mini;
        update public.profiles set coins = public.rb_cfg('start_coins'), keys = public.rb_cfg('start_keys'),
               equip = '{}'::jsonb, coin_min = 0, key_min = 0, day_coins = 0, spin_at = null, spin_prize = null,
               daily_at = null;
        delete from public.rb_catalog where kind = 'badge';
        insert into public.rb_config (key, value) values ('reset_008', 1);
    end if;
end $$;

-- ---------------------------------------------------------------- the catalogue, remade
-- Badges: 12 Common, 12 Rare, 12 Epic, 12 Legendary, 6 Mythic. (Inside, the five rarities are still called
-- standard, rare, special, epic, exotic.) Each badge exists as Basic, 8 Painted, 5 Shiny, 2 Titanium and Gold.
create or replace function public.rb_seed_catalog() returns void
language plpgsql security definer set search_path = '' as $$
declare
    tiers text[] := array['standard', 'rare', 'special', 'epic', 'exotic'];
    badges text[] := array['heart','drop','clover','paw','cat','fish','cherry','feather','note','dice','headset','gamepad',
        'mushroom','tree','wave','ghost','spade','club','diamond','eye','snowflake','mountain','moon','sun',
        'star','bolt','flame','anchor','key','pickaxe','rook','shield','sword','skull','trident','quill',
        'hourglass','target','comet','saturn','alien','rocket','shootingstar','planet','crown','trophy','goldenstar','sunburst'];
    mythics text[] := array['galaxy', 'phoenix', 'glitch', 'crystal', 'dragon', 'rubenium'];
    painted text[] := array['red', 'blue', 'yellow', 'green', 'orange', 'purple', 'pink', 'brown'];
    shiny text[] := array['hotpink', 'lime', 'sky', 'royal', 'lava'];
    colours text[] := array['blue','green','red','yellow','orange','brown','teal','lava','purple','sky','lime','pink','beam'];
    prestige text[] := array['black', 'white', 'gold'];
    cosmetics text[][] := array[
        ['ball','orbit','0'],['ball','pixel','0'],['ball','split','0'],['ball','halo','1'],['ball','bubble','1'],
        ['ball','spiral','1'],['ball','bullseye','2'],['ball','hex','2'],['ball','ripple','3'],['ball','shard','3'],
        ['line','dash','0'],['line','beads','0'],['line','zigzag','0'],['line','twin','1'],['line','pulse','1'],
        ['line','chain','1'],['line','ribbon','2'],['line','steps','2'],['line','spark','3'],['line','laser','3'],
        ['font','rounded','0'],['font','mono','1'],['font','serif','1'],['font','display','2'],['font','script','3']];
    themes text[][] := array[['sunset','1'],['ocean','1'],['forest','2'],['candy','2'],['storm','3'],['retro','3']];
    prog text[][] := array[['theme:1','0'],['ball:0','0'],['ring:0','0'],['font:0','0'],
        ['theme:2','120'],['ball:1','300'],['ring:1','480'],['theme:3','720'],['theme:4','1200'],['ball:2','1800'],
        ['ring:2','2400'],['theme:5','3300'],['theme:6','4500'],['ball:3','6000'],['ring:3','7500'],
        ['theme:7','9000'],['theme:8','12000']];
    b text; v text; i int; t int; p int; row text[]; worth int[]; base int;
begin
    worth := array[public.rb_cfg('price_standard')::int, public.rb_cfg('price_rare')::int,
                   public.rb_cfg('price_special')::int, public.rb_cfg('price_epic')::int,
                   public.rb_cfg('value_exotic')::int];
    delete from public.rb_catalog c where not exists (select 1 from public.rb_items it where it.item = c.id);
    for i in 1 .. array_length(badges, 1) loop
        b := badges[i]; t := (i - 1) / 12; base := worth[t + 1];
        insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls)
            values ('badge:' || b || ':grey', 'badge', b, 'grey', tiers[t + 1], base, base, true, 0)
            on conflict (id) do update set rarity = excluded.rarity, price = excluded.price, value = excluded.value, cls = 0;
        foreach v in array painted loop
            insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls)
                values ('badge:' || b || ':' || v, 'badge', b, v, tiers[t + 1], null, (base * 1.6)::int, true, 1)
                on conflict (id) do update set rarity = excluded.rarity, price = null, value = excluded.value, cls = 1;
        end loop;
        foreach v in array shiny loop
            insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls)
                values ('badge:' || b || ':' || v, 'badge', b, v, tiers[t + 1], null, base * 8, true, 2)
                on conflict (id) do update set rarity = excluded.rarity, price = null, value = excluded.value, cls = 2;
        end loop;
        if t >= 2 then                                   -- Titanium: Epic and Legendary badges only
            foreach v in array array['black', 'white'] loop
                insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls)
                    values ('badge:' || b || ':' || v, 'badge', b, v, tiers[t + 1], null, base * 40, true, 3)
                    on conflict (id) do update set rarity = excluded.rarity, price = null, value = excluded.value, cls = 3;
            end loop;
        else
            delete from public.rb_catalog c where c.id in ('badge:' || b || ':black', 'badge:' || b || ':white')
               and not exists (select 1 from public.rb_items it where it.item = c.id);
        end if;
        insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls)
            values ('badge:' || b || ':gold', 'badge', b, 'gold', tiers[t + 1], null, base * 200, true, 4)
            on conflict (id) do update set rarity = excluded.rarity, price = null, value = excluded.value, cls = 4;
    end loop;
    foreach b in array mythics loop                      -- Mythic: cases, trading and the market only
        insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls)
            values ('badge:' || b || ':black', 'badge', b, 'black', 'exotic', null, worth[5] * (case b when 'rubenium' then 2 else 1 end), true, 3),
                   ('badge:' || b || ':white', 'badge', b, 'white', 'exotic', null, worth[5] * (case b when 'rubenium' then 2 else 1 end), true, 3),
                   ('badge:' || b || ':prime', 'badge', b, 'prime', 'exotic', null, worth[5] * (case b when 'rubenium' then 6 else 3 end), true, 5),
                   ('badge:' || b || ':gold', 'badge', b, 'gold', 'exotic', null, worth[5] * (case b when 'rubenium' then 50 else 16 end), true, 4)
            on conflict (id) do update set rarity = 'exotic', price = null, value = excluded.value, cls = excluded.cls;
    end loop;
    foreach row slice 1 in array cosmetics loop          -- balls, lines, fonts: every colour is sold
        t := row[3]::int;
        insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable)
            values (row[1] || ':' || row[2] || ':grey', row[1], row[2], 'grey', tiers[t + 1],
                    (worth[t + 1] * 0.8)::int, (worth[t + 1] * 0.8)::int, true) on conflict (id) do update set price = excluded.price, value = excluded.value, rarity = excluded.rarity;
        foreach v in array colours loop
            insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable)
                values (row[1] || ':' || row[2] || ':' || v, row[1], row[2], v, tiers[t + 1], worth[t + 1], worth[t + 1], true)
                on conflict (id) do update set price = excluded.price, value = excluded.value, rarity = excluded.rarity;
        end loop;
        foreach v in array prestige loop
            p := least(t + 1, 3);
            i := (worth[p + 1] * (case v when 'gold' then 1.6 else 1.25 end))::int;
            insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable)
                values (row[1] || ':' || row[2] || ':' || v, row[1], row[2], v, tiers[p + 1], i, i, true)
                on conflict (id) do update set price = excluded.price, value = excluded.value, rarity = excluded.rarity;
        end loop;
    end loop;
    foreach row slice 1 in array themes loop
        t := row[2]::int;
        insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable)
            values ('theme:' || row[1], 'theme', row[1], '', tiers[t + 1], (worth[t + 1] * 1.2)::int,
                    (worth[t + 1] * 1.2)::int, true) on conflict (id) do update set price = excluded.price, value = excluded.value, rarity = excluded.rarity;
    end loop;
    foreach row slice 1 in array prog loop
        insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable)
            values ('prog:' || row[1], 'prog', split_part(row[1], ':', 1), '', 'standard', null, row[2]::int, false)
            on conflict (id) do update set value = excluded.value;
    end loop;
end $$;
select public.rb_seed_catalog();

-- ---------------------------------------------------------------- helpers
-- pick one slot with the given weights (any total: 10 000 or 100 000 for very rare things)
create or replace function public.rb_roll(odds integer[]) returns integer
language plpgsql volatile set search_path = '' as $$
declare total bigint := (select sum(x) from unnest(odds) x); r bigint; i integer;
begin
    if coalesce(total, 0) <= 0 then return 0; end if;
    r := floor(public.rb_rand() * total)::bigint;
    for i in 1 .. array_length(odds, 1) loop
        if r < odds[i] then return i - 1; end if;
        r := r - odds[i];
    end loop;
    return 0;
end $$;

create or replace function public.rb_lock_me() returns public.profiles
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype;
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    select * into p from public.profiles where id = auth.uid() for update;
    if not found then raise exception 'rb_no_profile'; end if;
    if p.banned then raise exception 'rb_banned'; end if;
    if public.rb_cfg('app_locked') > 0 and not p.admin then raise exception 'rb_app_locked'; end if;
    return p;
end $$;

-- may this account wear `what`? owned, or unlocked by time; a Basic badge also when any colour of it is owned
create or replace function public.rb_can_wear(p public.profiles, what text) returns boolean
language sql stable security definer set search_path = '' as $$
    select exists (select 1 from public.rb_catalog c where c.id = what and c.kind = 'prog' and c.value <= p.minutes)
        or exists (select 1 from public.rb_items it where it.owner = p.id and it.item = what)
        or (what like 'badge:%:grey' and exists (
                select 1 from public.rb_items it join public.rb_catalog c on c.id = it.item
                 where it.owner = p.id and c.kind = 'badge' and c.base = split_part(what, ':', 2))) $$;

create or replace function public.rb_notice(who uuid, kind text, data jsonb) returns void
language sql security definer set search_path = '' as $$
    insert into public.rb_inbox (owner, kind, data) values (who, kind, data) $$;

create or replace function public.rb_stock_add(who uuid, which text, how_many integer) returns void
language sql security definer set search_path = '' as $$
    insert into public.rb_case_stock (owner, case_id, n) values (who, which, how_many)
    on conflict (owner, case_id) do update set n = public.rb_case_stock.n + excluded.n $$;

-- the best sale running on an item right now (0 = none). A sale names one item, or the start of many
-- ("ball:orbit" = every colour of that ball, "theme" = every theme).
create or replace function public.rb_sale_pct(item_id text) returns integer
language sql stable security definer set search_path = '' as $$
    select coalesce(max(s.pct), 0)::int from public.rb_sales s
     where s.ends_at > now() and (item_id = s.what or item_id like s.what || ':%') $$;

-- ---------------------------------------------------------------- one account per PC
create or replace function public.rb_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
    name text := coalesce(new.raw_user_meta_data ->> 'username', '');
    pc text := left(coalesce(new.raw_user_meta_data ->> 'device', ''), 64);
    used boolean := false;
begin
    if name !~ '^[A-Za-z0-9]{3,10}$' then raise exception 'rb_bad_username'; end if;
    if new.email is distinct from lower(name) || '@users.rubenium.app' then raise exception 'rb_bad_account'; end if;
    if exists (select 1 from public.profiles p where lower(p.username) = lower(name) or p.login = lower(name)) then
        raise exception 'rb_username_taken';
    end if;
    if pc !~ '^[a-f0-9]{32,64}$' then raise exception 'rb_update_needed'; end if;       -- an old version of the app
    if exists (select 1 from public.rb_devices d where d.device = pc and d.owner is not null) then
        raise exception 'rb_device_used';
    end if;
    used := exists (select 1 from public.rb_devices d where d.device = pc);              -- a deleted account was here
    insert into public.profiles (id, username, login, coins, keys)
        values (new.id, name, lower(name), case when used then 0 else public.rb_cfg('start_coins') end,
                case when used then 0 else public.rb_cfg('start_keys') end);
    insert into public.rb_devices (device, owner) values (pc, new.id)
        on conflict (device) do update set owner = excluded.owner, at = now();
    return new;
end $$;

create or replace function public.rb_device_free(pc text) returns json
language sql stable security definer set search_path = '' as $$
    select json_build_object('free', not exists (select 1 from public.rb_devices d where d.device = pc and d.owner is not null),
        'name', (select p.username from public.rb_devices d join public.profiles p on p.id = d.owner where d.device = pc)) $$;

create or replace function public.rb_username_free(name text) returns boolean
language sql stable security definer set search_path = '' as $$
    select name ~ '^[A-Za-z0-9]{3,10}$'
       and not exists (select 1 from public.profiles p where lower(p.username) = lower(name) or p.login = lower(name)) $$;

-- the name an account logs in with stays the one it was created with, even after a name change
create or replace function public.rb_login_for(name text) returns text
language sql stable security definer set search_path = '' as $$
    select p.login from public.profiles p where lower(p.username) = lower(name) $$;

-- the app says which PC it is on (a PC that already has an account cannot create another one)
create or replace function public.rb_hello(pc text) returns boolean
language plpgsql security definer set search_path = '' as $$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    if pc ~ '^[a-f0-9]{32,64}$' then
        insert into public.rb_devices (device, owner) values (pc, auth.uid())
            on conflict (device) do update set owner = coalesce(public.rb_devices.owner, excluded.owner);
    end if;
    return true;
end $$;

-- ---------------------------------------------------------------- my account in one answer
create or replace function public.rb_state() returns json
language plpgsql stable security definer set search_path = '' as $$
declare p public.profiles%rowtype;
begin
    select * into p from public.profiles where id = auth.uid();
    if not found then raise exception 'rb_not_logged_in'; end if;
    if p.banned then raise exception 'rb_banned'; end if;
    return json_build_object(
        'username', p.username, 'minutes', p.minutes, 'coins', p.coins, 'keys', p.keys,
        'coin_min', p.coin_min, 'key_min', p.key_min,
        'day_coins', case when p.day = current_date then p.day_coins else 0 end,
        'equip', p.equip, 'imported', p.imported, 'admin', p.admin, 'avatar_v', p.avatar_v,
        'stock', coalesce((select json_object_agg(s.case_id, s.n) from public.rb_case_stock s
                            where s.owner = p.id and s.n > 0), '{}'::json),
        'items', coalesce((select json_agg(json_build_object('id', it.id, 'item', it.item, 'locked', it.locked,
                                                             'origin', it.origin) order by it.got_at)
                             from public.rb_items it where it.owner = p.id), '[]'::json),
        'seen', coalesce((select json_agg(s.item) from public.rb_seen s where s.owner = p.id), '[]'::json));
end $$;

-- ---------------------------------------------------------------- shop (with sales) and vendor
create or replace function public.rb_buy(what text, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; c public.rb_catalog%rowtype; res jsonb; new_id uuid; cost integer;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into c from public.rb_catalog where id = what;
    if not found or c.price is null then raise exception 'rb_not_for_sale'; end if;
    if exists (select 1 from public.rb_items it where it.owner = p.id and it.item = what) then
        raise exception 'rb_already_owned';
    end if;
    cost := greatest(1, ceil(c.price * (100 - public.rb_sale_pct(c.id)) / 100.0)::int);
    perform public.rb_pay(p.id, -cost, 0, 'shop', what);
    new_id := public.rb_give(p.id, what, 'shop');
    return public.rb_remember(p.id, req, jsonb_build_object('id', new_id, 'item', what, 'coins', p.coins - cost));
end $$;

create or replace function public.rb_sell(item_id uuid, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; it public.rb_items%rowtype; c public.rb_catalog%rowtype; res jsonb; pay integer;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into it from public.rb_items where id = item_id and owner = p.id for update;
    if not found then raise exception 'rb_not_yours'; end if;
    if it.locked is not null then raise exception 'rb_item_locked'; end if;
    select * into c from public.rb_catalog where id = it.item;
    if not c.tradeable then raise exception 'rb_not_tradeable'; end if;
    pay := greatest(1, floor(c.value * public.rb_cfg('vendor_share'))::int);
    delete from public.rb_items where id = it.id;
    perform public.rb_fix_equip(p.id);
    perform public.rb_pay(p.id, pay, 0, 'vendor', it.item);
    return public.rb_remember(p.id, req, jsonb_build_object('paid', pay, 'coins', p.coins + pay,
        'equip', (select equip from public.profiles where id = p.id)));
end $$;

-- ---------------------------------------------------------------- cases, remade
-- odds out of 10 000: coins, Common, Rare, Epic, Legendary, Mythic. variants out of 100 000: Basic, Painted,
-- Shiny, Titanium, Gold. No guaranteed drops: everything is luck.
delete from public.rb_cases;
insert into public.rb_cases (id, pos, price, odds, coin_min, coin_max, exotics, pity_tier, pity_after, variants, mode) values
    ('starter',  1,  150, array[3800, 5000, 1030,  150,   20,    0],  100,  300, false, 9, 0, array[76000, 23500, 480, 0, 20], ''),
    ('standard', 2,  300, array[3600, 4200, 1700,  420,   78,    2],  180,  620, false, 9, 0, array[74000, 25400, 550, 30, 20], ''),
    ('gamble',   3,  250, array[5600,    0, 3000, 1150,  245,    5],   10,   60, false, 9, 0, array[70000, 29300, 620, 50, 30], ''),
    ('painter',  4,  600, array[3400, 4400, 1750,  380,   70,    0],  360, 1250, false, 9, 0, array[0, 99000, 900, 70, 30], ''),
    ('premium',  5,  800, array[3500, 2300, 2900, 1050,  242,    8],  480, 1650, false, 9, 0, array[72000, 27250, 650, 70, 30], ''),
    ('jackpot',  6, 1000, array[10000,   0,    0,    0,    0,    0],    0,    0, false, 9, 0, array[100000, 0, 0, 0, 0], 'jackpot'),
    ('titan',    7, 1500, array[3500, 3000, 2400,  850,  244,    6],  900, 3100, false, 9, 0, array[69000, 29800, 800, 360, 40], ''),
    ('vault',    8, 2000, array[3400,    0, 3500, 2300,  775,   25], 1200, 4100, false, 9, 0, array[70000, 29150, 750, 70, 30], ''),
    ('mythic',   9, 5000, array[3800,    0,    0, 4300, 1800,  100], 3000, 9800, false, 9, 0, array[68000, 31050, 820, 90, 40], '');

drop function if exists public.rb_pick_badge(integer, boolean);
create or replace function public.rb_pick_badge(tier integer, klass integer) returns text
language sql volatile security definer set search_path = '' as $$
    select c.id from public.rb_catalog c
     where c.kind = 'badge' and c.rarity = (array['standard', 'rare', 'special', 'epic', 'exotic'])[tier]
       and c.cls = klass
     order by public.rb_rand() limit 1 $$;

-- a Mythic badge: the Rubenium R comes half as often as the others
create or replace function public.rb_pick_mythic(klass integer) returns text
language plpgsql volatile security definer set search_path = '' as $$
declare names text[] := array['galaxy', 'phoenix', 'glitch', 'crystal', 'dragon', 'rubenium'];
        base text; var text;
begin
    base := names[public.rb_roll(array[2, 2, 2, 2, 2, 1]) + 1];
    var := case klass when 4 then 'gold' when 5 then 'prime'
                      else (array['black', 'white'])[floor(public.rb_rand() * 2)::int + 1] end;
    return 'badge:' || base || ':' || var;
end $$;

-- one drop of a case: (tier 0 = coins, class, item, coins)
create or replace function public.rb_case_drop(c public.rb_cases, out tier integer, out klass integer, out item text,
                                               out coins integer)
language plpgsql volatile security definer set search_path = '' as $$
declare r double precision;
begin
    tier := public.rb_roll(c.odds); klass := 0; coins := 0;
    if tier = 0 then
        if c.mode = 'jackpot' then
            r := public.rb_rand();
            coins := case when r < 0.70 then 100 + floor(public.rb_rand() * 301)
                          when r < 0.94 then 1000 + floor(public.rb_rand() * 801)
                          when r < 0.99 then 3000 + floor(public.rb_rand() * 2001)
                          else 8000 + floor(public.rb_rand() * 8001) end;
        else
            coins := c.coin_min + floor(public.rb_rand() * (c.coin_max - c.coin_min + 1))::int;
        end if;
    elsif tier = 5 then                                   -- Mythic: Titanium, rarely Prismatic, almost never Gold
        klass := (array[3, 5, 4])[public.rb_roll(array[90000, 9500, 500]) + 1];
        item := public.rb_pick_mythic(klass);
    else
        klass := public.rb_roll(c.variants);
        if klass = 3 and tier <= 2 then klass := 2; end if;  -- no Titanium for Common and Rare badges
        item := public.rb_pick_badge(tier, klass);
    end if;
end $$;

drop function if exists public.rb_open_case(text, text);
create or replace function public.rb_open_case(which text, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; c public.rb_cases%rowtype; res jsonb; d record; new_id uuid; have integer;
        spent integer;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into c from public.rb_cases where id = which;
    if not found then raise exception 'rb_no_case'; end if;
    select n into have from public.rb_case_stock where owner = p.id and case_id = c.id for update;
    if coalesce(have, 0) > 0 then                               -- a gifted case: no coins, still one key
        update public.rb_case_stock set n = n - 1 where owner = p.id and case_id = c.id;
        spent := 0; have := have - 1;
    else
        spent := c.price; have := 0;
    end if;
    perform public.rb_pay(p.id, -spent, -1, 'case', c.id);
    d := public.rb_case_drop(c);
    if d.tier = 0 then
        perform public.rb_pay(p.id, d.coins, 0, 'case_coins', c.id);
    else
        new_id := public.rb_give(p.id, d.item, 'case:' || c.id);
    end if;
    insert into public.rb_case_stats as st (owner, case_id, opens) values (p.id, c.id, 1)
        on conflict (owner, case_id) do update set opens = st.opens + 1;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'case:' || c.id, spent,
        jsonb_build_object('item', d.item, 'tier', d.tier), false,
        d.coins + coalesce((select value from public.rb_catalog where id = d.item), 0));
    return public.rb_remember(p.id, req, jsonb_build_object('tier', d.tier, 'cls', d.klass, 'item', d.item, 'id', new_id,
        'won', d.coins, 'coins', p.coins - spent + d.coins, 'keys', p.keys - 1, 'stock', have));
end $$;

create or replace function public.rb_daily_case() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r double precision; what text; coins integer := 0; keys integer := 0; new_id uuid;
        tier integer := 0;
begin
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
end $$;

-- Gift a case to a friend. You pay it; they open it with one of their keys.
create or replace function public.rb_case_gift(name text, which text, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; them public.profiles%rowtype; c public.rb_cases%rowtype; res jsonb;
begin
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
    if (select count(*) from public.rb_ledger where owner = p.id and reason = 'gift' and at >= date_trunc('day', now()))
       >= public.rb_cfg('gift_day') then
        raise exception 'rb_gift_limit';
    end if;
    perform public.rb_pay(p.id, -c.price, 0, 'gift', c.id || ':' || them.username);
    perform public.rb_stock_add(them.id, c.id, 1);
    perform public.rb_notice(them.id, 'gift', jsonb_build_object('from', p.username, 'case', c.id));
    return public.rb_remember(p.id, req, jsonb_build_object('coins', p.coins - c.price));
end $$;

-- ---------------------------------------------------------------- Rocket, with a plan
-- Before launch you may set an automatic cash-out. Nobody can cash out below x1.20. 4 % for the house.
drop function if exists public.rb_rocket(text, integer);
create or replace function public.rb_rocket(action text, bet integer, target numeric) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r public.rb_rounds%rowtype; crash numeric; now_mult numeric; pay integer := 0;
        u double precision; aim numeric; past jsonb; ended jsonb;
begin
    p := public.rb_lock_me();
    select * into r from public.rb_rounds where owner = p.id and game = 'rocket' and open for update;
    if found then
        crash := (r.secret ->> 'crash')::numeric;
        aim := (r.secret ->> 'target')::numeric;
        now_mult := floor(exp(0.10 * extract(epoch from (clock_timestamp() - r.at))) * 100) / 100;
        if aim is not null and crash >= aim and now_mult >= aim then            -- the automatic cash-out was reached
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
    insert into public.rb_rounds (owner, game, bet, secret)
        values (p.id, 'rocket', bet, jsonb_build_object('crash', crash, 'target', target));
    return jsonb_build_object('open', true, 'mult', 1, 'bet', bet, 'age', 0, 'target', target, 'history', past,
                              'coins', p.coins + pay - bet);
end $$;

-- ---------------------------------------------------------------- quests: 1 every hour, 3 every day, 3 every week
drop function if exists public.rb_quest_rows(uuid);
create or replace function public.rb_quest_rows(who uuid)
returns table (quest text, kind text, goal integer, reward integer, progress integer, period timestamptz, left_s integer)
language sql stable security definer set search_path = '' as $$
    with r as (select game, bet, paid, at from public.rb_rounds
                where owner = who and not open and at >= date_trunc('week', now())),
         d as (select * from r where at >= date_trunc('day', now())),
         h as (select * from r where at >= date_trunc('hour', now())),
         casino (g) as (values ('slots'), ('plinko'), ('dice'), ('mines'), ('rocket'), ('blackjack')),
         q (quest, kind, goal, reward, progress) as (
            select * from (values
                ('h_rounds', 'hour', 5, 40, (select count(*) from h where game in (select g from casino))::int),
                ('h_mini',   'hour', 2, 40, (select count(*) from h where game = 'mini')::int),
                ('h_bet',    'hour', 150, 45, (select coalesce(sum(bet), 0) from h where game in (select g from casino))::int),
                ('h_win',    'hour', 200, 45, (select coalesce(sum(paid), 0) from h where game in (select g from casino))::int)
            ) hq (quest, kind, goal, reward, progress)
            where hq.quest = (array['h_rounds', 'h_mini', 'h_bet', 'h_win'])[extract(hour from now())::int % 4 + 1]
            union all values
            ('d_rounds', 'day', 15, 150, (select count(*) from d where game in (select g from casino))::int),
            ('d_case',   'day',  1, 120, (select count(*) from d where game like 'case:%' or game = 'daily')::int),
            ('d_mini',   'day',  3, 120, (select count(*) from d where game = 'mini')::int),
            ('w_rounds', 'week', 150, 800, (select count(*) from r where game in (select g from casino))::int),
            ('w_cases',  'week',  10, 800, (select count(*) from r where game like 'case:%')::int),
            ('w_won',    'week', 5000, 900, (select coalesce(sum(paid), 0) from r where game in (select g from casino))::int))
    select q.quest, q.kind, q.goal, q.reward, least(q.progress, q.goal), date_trunc(q.kind, now()),
           ceil(extract(epoch from (date_trunc(q.kind, now()) + ('1 ' || q.kind)::interval - now())))::int
      from q $$;

drop function if exists public.rb_quests();
create or replace function public.rb_quests() returns json
language sql stable security definer set search_path = '' as $$
    select coalesce(json_agg(json_build_object('quest', q.quest, 'kind', q.kind, 'goal', q.goal, 'reward', q.reward,
               'progress', q.progress, 'left', q.left_s,
               'claimed', exists (select 1 from public.rb_quest_claims c
                                   where c.owner = auth.uid() and c.quest = q.quest and c.period = q.period))), '[]'::json)
      from public.rb_quest_rows(auth.uid()) q $$;

create or replace function public.rb_quest_claim(which text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; q record;
begin
    p := public.rb_lock_me();
    select * into q from public.rb_quest_rows(p.id) x where x.quest = which;
    if not found then raise exception 'rb_no_quest'; end if;
    if q.progress < q.goal then raise exception 'rb_not_done'; end if;
    begin
        insert into public.rb_quest_claims (owner, quest, period) values (p.id, q.quest, q.period);
    exception when unique_violation then
        raise exception 'rb_already_claimed';
    end;
    perform public.rb_pay(p.id, q.reward, 0, 'quest', q.quest);
    return jsonb_build_object('paid', q.reward, 'coins', p.coins + q.reward);
end $$;

-- ---------------------------------------------------------------- social
create or replace function public.rb_stats(who uuid) returns json
language sql stable security definer set search_path = '' as $$
    with r as (select * from public.rb_rounds where owner = who and not open),
         g as (select * from r where game in ('slots', 'plinko', 'dice', 'mines', 'rocket', 'blackjack'))
    select json_build_object(
        'bet', (select coalesce(sum(bet), 0) from g), 'won', (select coalesce(sum(paid), 0) from g),
        'best', (select coalesce(max(paid), 0) from g), 'rounds', (select count(*) from g),
        'cases', (select count(*) from r where game like 'case:%' or game = 'daily'),
        'spins', (select count(*) from r where game = 'spin'),
        'mini', (select count(*) from r where game = 'mini'),
        'trades', (select count(*) from public.rb_trades t where t.state = 'done' and (t.a = who or t.b = who)),
        'items', (select count(*) from public.rb_items it where it.owner = who),
        'badges', (select count(distinct it.item) from public.rb_items it where it.owner = who and it.item like 'badge:%'),
        'friends', (select count(*) from public.rb_friends f where f.ok and (f.a = who or f.b = who))) $$;

create or replace function public.rb_social() returns json
language sql stable security definer set search_path = '' as $$
    select json_build_object('username', p.username, 'admin', p.admin, 'minutes', p.minutes, 'since', p.created_at,
        'coins', p.coins, 'keys', p.keys, 'avatar_v', p.avatar_v,
        'rename_wait', greatest(0, ceil(extract(epoch from (p.renamed_at
                         + make_interval(hours => public.rb_cfg('rename_hours')::int) - now()))))::int,
        'stats', public.rb_stats(p.id))
      from public.profiles p where p.id = auth.uid() $$;

-- a small profile picture (the app shrinks it to a tiny JPEG before sending). Empty text removes it.
create or replace function public.rb_avatar_set(picture text) returns integer
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype;
begin
    p := public.rb_lock_me();
    if coalesce(picture, '') = '' then
        delete from public.rb_avatars where id = p.id;
    else
        if length(picture) > 40000 or picture !~ '^[A-Za-z0-9+/=]+$' then raise exception 'rb_bad_picture'; end if;
        insert into public.rb_avatars (id, data) values (p.id, picture) on conflict (id) do update set data = excluded.data;
    end if;
    update public.profiles set avatar_v = avatar_v + 1 where id = p.id;
    return p.avatar_v + 1;
end $$;

create or replace function public.rb_avatars_get(names text[]) returns json
language sql stable security definer set search_path = '' as $$
    select coalesce(json_object_agg(lower(p.username), json_build_object('v', p.avatar_v, 'data', a.data)), '{}'::json)
      from public.profiles p join public.rb_avatars a on a.id = p.id
     where auth.uid() is not null
       and lower(p.username) in (select lower(n) from unnest(names[1:40]) n) $$;

create or replace function public.rb_rename(new_name text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype;
begin
    p := public.rb_lock_me();
    if new_name is null or new_name !~ '^[A-Za-z0-9]{3,10}$' then raise exception 'rb_bad_username'; end if;
    if new_name = p.username then raise exception 'rb_same_name'; end if;
    if p.renamed_at is not null and now() < p.renamed_at + make_interval(hours => public.rb_cfg('rename_hours')::int) then
        raise exception 'rb_rename_wait';
    end if;
    if exists (select 1 from public.profiles o where o.id <> p.id
                and (lower(o.username) = lower(new_name) or o.login = lower(new_name))) then
        raise exception 'rb_username_taken';
    end if;
    begin
        update public.profiles set username = new_name, renamed_at = now() where id = p.id;
    exception when unique_violation then
        raise exception 'rb_username_taken';
    end;
    return jsonb_build_object('username', new_name);
end $$;

-- every Rubenium player, friends first
create or replace function public.rb_users(search text, page integer) returns json
language sql stable security definer set search_path = '' as $$
    select coalesce(json_agg(x), '[]'::json) from (
        select p.username, p.minutes, p.admin, p.avatar_v,
               (case when f.ok then 'friend' when f.a = auth.uid() then 'asked' when f.b = auth.uid() then 'asks' end) as state,
               (coalesce(f.ok, false) or p.id = auth.uid()) and public.rb_online(p) as online,
               p.id = auth.uid() as me,
               json_build_array(p.equip ->> 'badge1', p.equip ->> 'badge2', p.equip ->> 'badge3') as badges
          from public.profiles p
          left join public.rb_friends f on (f.a = auth.uid() and f.b = p.id) or (f.b = auth.uid() and f.a = p.id)
         where auth.uid() is not null and not p.banned
           and (coalesce(search, '') = '' or p.username ilike '%' || regexp_replace(search, '[^A-Za-z0-9]', '', 'g') || '%')
         order by (f.b = auth.uid() and not f.ok) desc nulls last, coalesce(f.ok, false) desc,
                  (coalesce(f.ok, false) and public.rb_online(p)) desc, p.last_beat desc nulls last
         limit 40 offset greatest(0, coalesce(page, 0)) * 40) x $$;

create or replace function public.rb_friends_list() returns json
language sql stable security definer set search_path = '' as $$
    select coalesce(json_agg(json_build_object(
               'username', p.username, 'minutes', p.minutes, 'admin', p.admin, 'avatar_v', p.avatar_v,
               'state', case when f.ok then 'friend' when f.a = auth.uid() then 'asked' else 'asks' end,
               'online', f.ok and public.rb_online(p),
               'seen', case when f.ok then p.last_beat end,
               'badges', case when f.ok then json_build_array(p.equip ->> 'badge1', p.equip ->> 'badge2', p.equip ->> 'badge3') end)
               order by f.ok desc, public.rb_online(p) desc, lower(p.username)), '[]'::json)
      from public.rb_friends f
      join public.profiles p on p.id = case when f.a = auth.uid() then f.b else f.a end
     where f.a = auth.uid() or f.b = auth.uid() $$;

create or replace function public.rb_profile(name text) returns json
language plpgsql stable security definer set search_path = '' as $$
declare me uuid := auth.uid(); p public.profiles%rowtype; friend boolean; mine public.profiles%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into mine from public.profiles where id = me;
    select * into p from public.profiles where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    friend := public.rb_is_friend(me, p.id);
    return json_build_object(
        'username', p.username, 'minutes', p.minutes, 'since', p.created_at, 'equip', p.equip,
        'admin', p.admin, 'avatar_v', p.avatar_v,
        'me', p.id = me, 'friend', friend,
        'can_trade', p.id <> me and public.rb_can_trade(p) and public.rb_can_trade(mine),
        'state', (select case when f.ok then 'friend' when f.a = me then 'asked' else 'asks' end
                    from public.rb_friends f where (f.a = me and f.b = p.id) or (f.a = p.id and f.b = me)),
        'online', (friend or p.id = me) and public.rb_online(p),
        'badges', coalesce((select json_agg(x.item order by x.value desc, x.item)
                              from (select distinct it.item, c.value from public.rb_items it
                                      join public.rb_catalog c on c.id = it.item
                                     where it.owner = p.id and c.kind = 'badge') x), '[]'::json),
        'stats', case when friend or p.id = me or mine.admin then public.rb_stats(p.id) end,
        'items', (select count(*) from public.rb_items it where it.owner = p.id));
end $$;

-- what a player did lately: 3 trades, 3 cases, 3 spins, 30 bets (your own, or a friend's)
create or replace function public.rb_history(name text) returns json
language plpgsql stable security definer set search_path = '' as $$
declare me uuid := auth.uid(); who uuid;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select id into who from public.profiles where lower(username) = lower(coalesce(nullif(name, ''),
        (select username from public.profiles where id = me)));
    if who is null then raise exception 'rb_no_such_user'; end if;
    if who <> me and not public.rb_is_friend(me, who)
       and not (select admin from public.profiles where id = me) then raise exception 'rb_friends_only'; end if;
    return json_build_object(
        'trades', coalesce((select json_agg(json_build_object(
                'with', (select username from public.profiles where id = case when t.a = who then t.b else t.a end),
                'gave', coalesce((select json_agg(ti.what) from public.rb_trade_items ti
                                   where ti.trade = t.id and ti.side = case when t.a = who then 'a' else 'b' end), '[]'::json),
                'got', coalesce((select json_agg(ti.what) from public.rb_trade_items ti
                                  where ti.trade = t.id and ti.side = case when t.a = who then 'b' else 'a' end), '[]'::json),
                'gave_coins', case when t.a = who then t.a_coins else t.b_coins end,
                'got_coins', case when t.a = who then t.b_coins else t.a_coins end, 'at', t.updated) order by t.updated desc)
              from (select * from public.rb_trades where state = 'done' and (a = who or b = who)
                     order by updated desc limit 3) t), '[]'::json),
        'cases', coalesce((select json_agg(json_build_object('game', r.game, 'bet', r.bet, 'paid', r.paid,
                               'item', r.secret ->> 'item', 'keys', r.secret ->> 'keys', 'at', r.at) order by r.at desc)
              from (select * from public.rb_rounds where owner = who and not open and (game like 'case:%' or game = 'daily')
                     order by at desc limit 3) r), '[]'::json),
        'spins', coalesce((select json_agg(json_build_object('paid', r.paid, 'keys', r.secret ->> 'keys', 'at', r.at) order by r.at desc)
              from (select * from public.rb_rounds where owner = who and not open and game = 'spin'
                     order by at desc limit 3) r), '[]'::json),
        'bets', coalesce((select json_agg(json_build_object('game', r.game, 'bet', r.bet, 'paid', r.paid, 'at', r.at) order by r.at desc)
              from (select * from public.rb_rounds where owner = who and not open
                       and game in ('slots', 'plinko', 'dice', 'mines', 'rocket', 'blackjack')
                     order by at desc limit 30) r), '[]'::json));
end $$;

-- ---------------------------------------------------------------- giveaways
create or replace function public.rb_giveaway_settle() returns void
language plpgsql security definer set search_path = '' as $$
declare g public.rb_giveaways%rowtype; w record; names jsonb;
begin
    for g in select * from public.rb_giveaways where state = 'live' and ends_at <= now() for update skip locked loop
        names := '[]'::jsonb;
        for w in select e.owner, p.username from public.rb_giveaway_entries e join public.profiles p on p.id = e.owner
                  where e.giveaway = g.id and not p.banned order by public.rb_rand() limit g.winners loop
            if g.kind = 'coins' then perform public.rb_pay(w.owner, g.amount, 0, 'giveaway', g.id::text);
            elsif g.kind = 'keys' then perform public.rb_pay(w.owner, 0, g.amount, 'giveaway', g.id::text);
            elsif g.kind = 'case' then perform public.rb_stock_add(w.owner, g.what, g.amount);
            else perform public.rb_give(w.owner, g.what, 'giveaway') from generate_series(1, g.amount);
            end if;
            perform public.rb_notice(w.owner, 'giveaway', jsonb_build_object('title', g.title, 'kind', g.kind,
                                                                             'what', g.what, 'amount', g.amount));
            names := names || to_jsonb(w.username);
        end loop;
        update public.rb_giveaways set state = 'done', result = names where id = g.id;
    end loop;
end $$;

create or replace function public.rb_giveaway_join(giveaway uuid) returns boolean
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; g public.rb_giveaways%rowtype;
begin
    p := public.rb_lock_me();
    select * into g from public.rb_giveaways where id = giveaway;
    if not found or g.state <> 'live' or g.ends_at <= now() then raise exception 'rb_giveaway_over'; end if;
    if p.minutes < g.min_minutes then raise exception 'rb_giveaway_hours'; end if;
    insert into public.rb_giveaway_entries (giveaway, owner) values (g.id, p.id) on conflict do nothing;
    return true;
end $$;

-- what is happening right now (asked every few seconds while the app is open): giveaways, sales, messages,
-- trade requests. Also ends giveaways whose time is up.
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
    with gone as (delete from public.rb_inbox where owner = me returning kind, data, at)
    select coalesce(json_agg(json_build_object('kind', kind, 'data', data) order by at), '[]'::json) into notes from gone;
    return json_build_object(
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
        'minutes', p.minutes, 'coins', p.coins, 'keys', p.keys);
end $$;

-- ---------------------------------------------------------------- the admin panel (account "Ruben" only)
create or replace function public.rb_need_admin() returns uuid
language plpgsql stable security definer set search_path = '' as $$
begin
    if not coalesce((select admin from public.profiles where id = auth.uid()), false) then
        raise exception 'rb_not_admin';
    end if;
    return auth.uid();
end $$;

create or replace function public.rb_log(action text, target text, detail jsonb) returns void
language sql security definer set search_path = '' as $$
    insert into public.rb_audit (admin, action, target, detail) values (auth.uid(), action, target, detail) $$;

create or replace function public.rb_admin_stats() returns json
language plpgsql stable security definer set search_path = '' as $$
begin
    perform public.rb_need_admin();
    return json_build_object(
        'players', (select count(*) from public.profiles),
        'online', (select count(*) from public.profiles p where public.rb_online(p)),
        'today', (select count(*) from public.profiles where last_beat >= date_trunc('day', now())),
        'coins', (select coalesce(sum(coins), 0) from public.profiles),
        'keys', (select coalesce(sum(keys), 0) from public.profiles),
        'items', (select count(*) from public.rb_items),
        'listings', (select count(*) from public.rb_listings where state = 'open'),
        'trades', (select count(*) from public.rb_trades where state = 'done'),
        'games', coalesce((select json_agg(json_build_object('game', x.game, 'rounds', x.n, 'bet', x.bet, 'paid', x.paid) order by x.bet desc)
                    from (select game, count(*) n, coalesce(sum(bet), 0) bet, coalesce(sum(paid), 0) paid
                            from public.rb_rounds where not open group by game) x), '[]'::json),
        'ledger', coalesce((select json_agg(json_build_object('reason', x.reason, 'coins', x.c, 'n', x.n) order by x.c desc)
                    from (select reason, sum(coins) c, count(*) n from public.rb_ledger
                           where at >= now() - interval '7 days' group by reason) x), '[]'::json),
        'config', (select json_object_agg(key, value) from public.rb_config),
        'cases', (select json_agg(row_to_json(c) order by c.pos) from public.rb_cases c));
end $$;

create or replace function public.rb_admin_players(search text, sort text, page integer) returns json
language plpgsql stable security definer set search_path = '' as $$
begin
    perform public.rb_need_admin();
    return (select coalesce(json_agg(x), '[]'::json) from (
        select p.username, p.minutes, p.coins, p.keys, p.banned, p.admin, public.rb_online(p) as online,
               p.last_beat as seen, p.created_at as since,
               (select count(*) from public.rb_items it where it.owner = p.id) as items
          from public.profiles p
         where coalesce(search, '') = '' or p.username ilike '%' || regexp_replace(search, '[^A-Za-z0-9]', '', 'g') || '%'
         order by case sort when 'coins' then p.coins when 'hours' then p.minutes end desc nulls last,
                  p.last_beat desc nulls last
         limit 40 offset greatest(0, coalesce(page, 0)) * 40) x);
end $$;

create or replace function public.rb_admin_player(name text) returns json
language plpgsql stable security definer set search_path = '' as $$
declare p public.profiles%rowtype;
begin
    perform public.rb_need_admin();
    select * into p from public.profiles where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    return json_build_object('username', p.username, 'login', p.login, 'minutes', p.minutes, 'coins', p.coins,
        'keys', p.keys, 'banned', p.banned, 'admin', p.admin, 'since', p.created_at, 'seen', p.last_beat,
        'online', public.rb_online(p), 'equip', p.equip, 'stats', public.rb_stats(p.id),
        'stock', coalesce((select json_object_agg(s.case_id, s.n) from public.rb_case_stock s where s.owner = p.id and s.n > 0), '{}'::json),
        'items', coalesce((select json_agg(json_build_object('id', it.id, 'item', it.item, 'locked', it.locked, 'origin', it.origin)
                                           order by it.got_at desc) from public.rb_items it where it.owner = p.id), '[]'::json),
        'games', coalesce((select json_agg(json_build_object('game', x.game, 'rounds', x.n, 'bet', x.bet, 'paid', x.paid))
                    from (select game, count(*) n, coalesce(sum(bet), 0) bet, coalesce(sum(paid), 0) paid
                            from public.rb_rounds where owner = p.id and not open group by game) x), '[]'::json),
        'rounds', coalesce((select json_agg(json_build_object('game', r.game, 'bet', r.bet, 'paid', r.paid,
                               'item', r.secret ->> 'item', 'at', r.at) order by r.at desc)
                    from (select * from public.rb_rounds where owner = p.id and not open order by at desc limit 60) r), '[]'::json),
        'ledger', coalesce((select json_agg(json_build_object('coins', l.coins, 'keys', l.keys, 'reason', l.reason,
                               'ref', l.ref, 'at', l.at) order by l.id desc)
                    from (select * from public.rb_ledger where owner = p.id order by id desc limit 80) l), '[]'::json));
end $$;

-- give or take coins and keys (never below zero)
create or replace function public.rb_admin_grant(name text, add_coins integer, add_keys integer) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; dc integer; dk integer;
begin
    perform public.rb_need_admin();
    select * into p from public.profiles where lower(username) = lower(name) for update;
    if not found then raise exception 'rb_no_such_user'; end if;
    dc := greatest(coalesce(add_coins, 0), -p.coins)::int; dk := greatest(coalesce(add_keys, 0), -p.keys);
    perform public.rb_pay(p.id, dc, dk, 'admin', null);
    perform public.rb_log('grant', p.username, jsonb_build_object('coins', dc, 'keys', dk));
    if dc > 0 or dk > 0 then
        perform public.rb_notice(p.id, 'admin', jsonb_build_object('coins', greatest(dc, 0), 'keys', greatest(dk, 0)));
    end if;
    return jsonb_build_object('coins', p.coins + dc, 'keys', p.keys + dk);
end $$;

-- give an item of the catalogue, or cases (what = "case:<id>")
create or replace function public.rb_admin_give(name text, what text, how_many integer) returns boolean
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; n integer := least(greatest(coalesce(how_many, 1), 1), 100);
begin
    perform public.rb_need_admin();
    select * into p from public.profiles where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    if what like 'case:%' then
        if not exists (select 1 from public.rb_cases where id = substr(what, 6)) then raise exception 'rb_no_case'; end if;
        perform public.rb_stock_add(p.id, substr(what, 6), n);
        perform public.rb_notice(p.id, 'admin', jsonb_build_object('case', substr(what, 6), 'n', n));
    else
        if not exists (select 1 from public.rb_catalog c where c.id = what and c.kind <> 'prog') then
            raise exception 'rb_not_for_sale';
        end if;
        perform public.rb_give(p.id, what, 'admin') from generate_series(1, n);
        perform public.rb_notice(p.id, 'admin', jsonb_build_object('item', what, 'n', n));
    end if;
    perform public.rb_log('give', p.username, jsonb_build_object('what', what, 'n', n));
    return true;
end $$;

create or replace function public.rb_admin_take(item_id uuid) returns boolean
language plpgsql security definer set search_path = '' as $$
declare it public.rb_items%rowtype;
begin
    perform public.rb_need_admin();
    select * into it from public.rb_items where id = item_id for update;
    if not found then raise exception 'rb_not_yours'; end if;
    if it.locked is not null then raise exception 'rb_item_locked'; end if;
    delete from public.rb_items where id = it.id;
    perform public.rb_fix_equip(it.owner);
    perform public.rb_log('take', (select username from public.profiles where id = it.owner), jsonb_build_object('item', it.item));
    return true;
end $$;

create or replace function public.rb_admin_ban(name text, ban boolean) returns boolean
language plpgsql security definer set search_path = '' as $$
declare me uuid := public.rb_need_admin();
begin
    update public.profiles set banned = coalesce(ban, false) where lower(username) = lower(name) and id <> me;
    if not found then raise exception 'rb_no_such_user'; end if;
    perform public.rb_log('ban', name, jsonb_build_object('banned', ban));
    return true;
end $$;

create or replace function public.rb_admin_avatar_clear(name text) returns boolean
language plpgsql security definer set search_path = '' as $$
begin
    perform public.rb_need_admin();
    delete from public.rb_avatars where id = (select id from public.profiles where lower(username) = lower(name));
    update public.profiles set avatar_v = avatar_v + 1 where lower(username) = lower(name);
    perform public.rb_log('avatar', name, null);
    return true;
end $$;

-- change one number of the settings (prices, caps, timers...)
create or replace function public.rb_admin_set(setting text, new_value numeric) returns boolean
language plpgsql security definer set search_path = '' as $$
begin
    perform public.rb_need_admin();
    if setting = 'reset_008' or new_value is null or new_value < 0 then raise exception 'rb_bad_choice'; end if;
    update public.rb_config set value = new_value where key = setting;
    if not found then raise exception 'rb_bad_choice'; end if;
    perform public.rb_log('set', setting, jsonb_build_object('value', new_value));
    return true;
end $$;

-- change a case: price, drop odds (6 numbers, total 10 000), colour odds (5 numbers, total 100 000), coins
create or replace function public.rb_admin_case(which text, new_price integer, new_odds integer[], new_variants integer[],
                                                new_min integer, new_max integer) returns boolean
language plpgsql security definer set search_path = '' as $$
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
end $$;

create or replace function public.rb_admin_giveaway(title text, kind text, what text, amount integer, winners integer,
                                                    minutes integer, min_hours integer) returns uuid
language plpgsql security definer set search_path = '' as $$
declare gid uuid;
begin
    perform public.rb_need_admin();
    if kind not in ('coins', 'keys', 'item', 'case') or coalesce(amount, 0) < 1 or coalesce(winners, 0) not between 1 and 50
       or coalesce(minutes, 0) not between 1 and 10080 or length(coalesce(title, '')) not between 1 and 40 then
        raise exception 'rb_bad_choice';
    end if;
    if kind = 'item' and not exists (select 1 from public.rb_catalog c where c.id = what and c.kind <> 'prog') then
        raise exception 'rb_not_for_sale';
    end if;
    if kind = 'case' and not exists (select 1 from public.rb_cases where id = what) then raise exception 'rb_no_case'; end if;
    if kind in ('item', 'case') and amount > 20 then raise exception 'rb_bad_choice'; end if;
    insert into public.rb_giveaways (title, kind, what, amount, winners, min_minutes, ends_at)
        values (title, kind, coalesce(what, ''), amount, winners, greatest(coalesce(min_hours, 0), 0) * 60,
                now() + make_interval(mins => minutes)) returning id into gid;
    perform public.rb_log('giveaway', title, jsonb_build_object('kind', kind, 'what', what, 'amount', amount,
                                                                 'winners', winners, 'minutes', minutes));
    return gid;
end $$;

create or replace function public.rb_admin_giveaway_end(giveaway uuid, draw boolean) returns boolean
language plpgsql security definer set search_path = '' as $$
begin
    perform public.rb_need_admin();
    if coalesce(draw, false) then
        update public.rb_giveaways set ends_at = now() where id = giveaway and state = 'live';
        perform public.rb_giveaway_settle();
    else
        update public.rb_giveaways set state = 'cancelled' where id = giveaway and state = 'live';
    end if;
    perform public.rb_log('giveaway_end', giveaway::text, jsonb_build_object('draw', draw));
    return true;
end $$;

create or replace function public.rb_admin_sale(what text, pct integer, minutes integer) returns uuid
language plpgsql security definer set search_path = '' as $$
declare sid uuid;
begin
    perform public.rb_need_admin();
    if coalesce(pct, 0) not between 1 and 90 or coalesce(minutes, 0) not between 1 and 43200
       or not exists (select 1 from public.rb_catalog c where c.price is not null and (c.id = what or c.id like what || ':%')) then
        raise exception 'rb_bad_choice';
    end if;
    insert into public.rb_sales (what, pct, ends_at) values (what, pct, now() + make_interval(mins => minutes))
        returning id into sid;
    perform public.rb_log('sale', what, jsonb_build_object('pct', pct, 'minutes', minutes));
    return sid;
end $$;

create or replace function public.rb_admin_sale_end(sale uuid) returns boolean
language plpgsql security definer set search_path = '' as $$
begin
    perform public.rb_need_admin();
    delete from public.rb_sales where id = sale;
    perform public.rb_log('sale_end', sale::text, null);
    return true;
end $$;

create or replace function public.rb_admin_audit() returns json
language plpgsql stable security definer set search_path = '' as $$
begin
    perform public.rb_need_admin();
    return (select coalesce(json_agg(json_build_object('action', a.action, 'target', a.target, 'detail', a.detail, 'at', a.at)
                                     order by a.id desc), '[]'::json)
              from (select * from public.rb_audit order by id desc limit 100) a);
end $$;

-- ---------------------------------------------------------------- PART 3: time coins, free spin, market offers, live news
-- Time with Rubenium still counts while the admin has locked the app (only the online games and trades stop).
create or replace function public.rb_heartbeat(device text) returns json
language plpgsql security definer set search_path = '' as $$
declare
    p public.profiles%rowtype;
    credited boolean := false; elsewhere boolean := false;
    got_coins integer := 0; got_keys integer := 0;
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    select * into p from public.profiles where id = auth.uid() for update;
    if not found then raise exception 'rb_no_profile'; end if;
    if p.banned then raise exception 'rb_banned'; end if;
    device := left(coalesce(device, ''), 64);
    if p.last_beat is not null and p.beat_device is distinct from device
       and now() - p.last_beat < interval '150 seconds' then
        elsewhere := true;                                   -- another PC is earning right now
    elsif p.last_beat is null or now() - p.last_beat >= interval '55 seconds' then
        credited := p.last_beat is not null and now() - p.last_beat < interval '150 seconds';
        if credited then
            p.minutes := p.minutes + 1; p.coin_min := p.coin_min + 1; p.key_min := p.key_min + 1;
            if p.day <> current_date then p.day := current_date; p.day_coins := 0; end if;
            if p.coin_min >= public.rb_cfg('coin_every_min') then
                p.coin_min := 0;
                if p.day_coins < public.rb_cfg('coin_day_cap') then
                    got_coins := public.rb_cfg('coin_amount')::int; p.day_coins := p.day_coins + got_coins;
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

-- the free spin: every 2 hours, better prizes than before
create or replace function public.rb_spin() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r integer; prize jsonb;
        slots integer[] := array[40, 75, 120, 180, 300, 500, 1200, -1];       -- -1 = one key
        odds  integer[] := array[2300, 2300, 1900, 1300, 800, 450, 200, 750];
begin
    p := public.rb_lock_me();
    if p.spin_prize is not null then return p.spin_prize || jsonb_build_object('waiting', true); end if;
    if p.spin_at is not null and now() < p.spin_at + make_interval(hours => public.rb_cfg('spin_hours')::int) then
        raise exception 'rb_too_soon';
    end if;
    r := public.rb_roll(odds);
    prize := jsonb_build_object('slot', r, 'won', greatest(slots[r + 1], 0), 'won_keys', case when slots[r + 1] < 0 then 1 else 0 end);
    update public.profiles set spin_at = now(), spin_prize = prize where id = p.id;
    return prize;
end $$;

-- ---------------------------------------------------------------- market: buy now, or make an offer
-- (selling to the vendor is gone: everything is sold between players)
create table if not exists public.rb_offers (
    id uuid primary key default gen_random_uuid(),
    listing uuid not null references public.rb_listings (id) on delete cascade,
    buyer uuid not null references public.profiles (id) on delete cascade,
    price integer not null check (price > 0),
    state text not null default 'open' check (state in ('open', 'taken', 'refused', 'gone')),
    at timestamptz not null default now());
create unique index if not exists rb_offers_one on public.rb_offers (listing, buyer) where state = 'open';
alter table public.rb_offers enable row level security;
revoke all on public.rb_offers from anon, authenticated;

-- the sale itself: listing and both players locked (always in the same order), checked again, then all at once
create or replace function public.rb_market_deal(listing uuid, who uuid, pay integer) returns jsonb
language plpgsql security definer set search_path = '' as $$
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
end $$;

create or replace function public.rb_market_buy(listing uuid, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; res jsonb;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    res := public.rb_market_deal(listing, p.id, (select price from public.rb_listings where id = listing));
    return public.rb_remember(p.id, req, res);
end $$;

-- offer less than the price (at least half of it). The coins are not taken until the seller accepts.
create or replace function public.rb_market_offer(listing uuid, price integer) returns uuid
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; l public.rb_listings%rowtype; oid uuid;
begin
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
end $$;

create or replace function public.rb_market_answer(offer uuid, accept boolean) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; o public.rb_offers%rowtype; l public.rb_listings%rowtype; res jsonb;
begin
    p := public.rb_lock_me();
    select * into o from public.rb_offers where id = offer for update;
    if not found or o.state <> 'open' then raise exception 'rb_offer_gone'; end if;
    select * into l from public.rb_listings where id = o.listing;
    if l.seller <> p.id then raise exception 'rb_offer_gone'; end if;
    if not coalesce(accept, false) then
        update public.rb_offers set state = 'refused' where id = o.id;
        perform public.rb_notice(o.buyer, 'refused', jsonb_build_object('item', l.what, 'price', o.price));
        return jsonb_build_object('refused', true);
    end if;
    begin
        res := public.rb_market_deal(l.id, o.buyer, o.price);
    exception when others then
        update public.rb_offers set state = 'gone' where id = o.id;
        if sqlerrm like 'rb_not_enough%' then raise exception 'rb_buyer_poor'; end if;
        raise;
    end;
    update public.rb_offers set state = 'taken' where id = o.id;
    perform public.rb_notice(o.buyer, 'bought', jsonb_build_object('item', l.what, 'price', o.price));
    return jsonb_build_object('sold', true, 'coins', (select coins from public.profiles where id = p.id));
end $$;

create or replace function public.rb_market_offers() returns json
language sql stable security definer set search_path = '' as $$
    select json_build_object(
        'to_me', coalesce((select json_agg(json_build_object('offer', o.id, 'item', l.what, 'price', o.price,
                        'asking', l.price, 'from', b.username, 'at', o.at) order by o.at desc)
              from public.rb_offers o join public.rb_listings l on l.id = o.listing
              join public.profiles b on b.id = o.buyer
             where l.seller = auth.uid() and o.state = 'open' and l.state = 'open'), '[]'::json),
        'mine', coalesce((select json_agg(json_build_object('offer', o.id, 'item', l.what, 'price', o.price,
                        'asking', l.price, 'state', o.state, 'at', o.at) order by o.at desc)
              from (select * from public.rb_offers where buyer = auth.uid() order by at desc limit 20) o
              join public.rb_listings l on l.id = o.listing), '[]'::json)) $$;

create or replace function public.rb_market_unoffer(offer uuid) returns boolean
language plpgsql security definer set search_path = '' as $$
begin
    update public.rb_offers set state = 'gone' where id = offer and buyer = auth.uid() and state = 'open';
    return found;
end $$;

-- ---------------------------------------------------------------- what is happening right now (asked every 20 s)
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
    with gone as (delete from public.rb_inbox where owner = me returning kind, data, at)
    select coalesce(json_agg(json_build_object('kind', kind, 'data', data) order by at), '[]'::json) into notes from gone;
    return json_build_object(
        'locked', public.rb_cfg('app_locked') > 0 and not p.admin,
        'app_locked', public.rb_cfg('app_locked') > 0,
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
        'minutes', p.minutes, 'coins', p.coins, 'keys', p.keys);
end $$;

-- the admin locks or unlocks the whole app (games, cases, trades, market). Time with Rubenium still counts.
create or replace function public.rb_admin_lock(lock boolean) returns boolean
language plpgsql security definer set search_path = '' as $$
begin
    perform public.rb_need_admin();
    update public.rb_config set value = case when coalesce(lock, false) then 1 else 0 end where key = 'app_locked';
    perform public.rb_log('lock', null, jsonb_build_object('locked', lock));
    return true;
end $$;

-- the admin takes back every copy of one item from a player
create or replace function public.rb_admin_revoke(name text, what text) returns integer
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; n integer;
begin
    perform public.rb_need_admin();
    select * into p from public.profiles where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    update public.rb_listings set state = 'cancelled' where seller = p.id and state = 'open' and rb_listings.what = rb_admin_revoke.what;
    delete from public.rb_trade_items ti using public.rb_trades t
     where ti.trade = t.id and t.state in ('asked', 'open') and ti.what = rb_admin_revoke.what
       and ti.item in (select id from public.rb_items where owner = p.id);
    delete from public.rb_items where owner = p.id and item = what;
    get diagnostics n = row_count;
    perform public.rb_fix_equip(p.id);
    perform public.rb_log('revoke', p.username, jsonb_build_object('what', what, 'n', n));
    return n;
end $$;

-- every item the admin can give (for the admin panel's picker)
create or replace function public.rb_admin_catalog() returns json
language plpgsql stable security definer set search_path = '' as $$
begin
    perform public.rb_need_admin();
    return (select json_agg(c.id order by c.kind, c.base, c.variant) from public.rb_catalog c where c.kind <> 'prog');
end $$;

-- ---------------------------------------------------------------- who may call what
-- first nobody may call anything; then the app gets exactly the list below
do $$ declare f text; begin
    for f in select p.oid::regprocedure::text from pg_catalog.pg_proc p
              join pg_catalog.pg_namespace n on n.oid = p.pronamespace
             where n.nspname = 'public' and p.proname like 'rb\_%' loop
        execute format('revoke all on function %s from public, anon, authenticated', f);
    end loop;
    for f in select p.oid::regprocedure::text from pg_catalog.pg_proc p
              join pg_catalog.pg_namespace n on n.oid = p.pronamespace
             where n.nspname = 'public' and p.proname = any (array[
                'rb_me', 'rb_delete_account', 'rb_state', 'rb_heartbeat', 'rb_hello', 'rb_buy', 'rb_vendor_price',
                'rb_equip', 'rb_open_case', 'rb_daily_case', 'rb_case_gift', 'rb_spin', 'rb_spin_collect', 'rb_timers',
                'rb_slots', 'rb_plinko', 'rb_dice', 'rb_mines', 'rb_rocket', 'rb_blackjack',
                'rb_friend_add', 'rb_friend_remove', 'rb_friends_list', 'rb_profile', 'rb_history', 'rb_users',
                'rb_social', 'rb_avatar_set', 'rb_avatars_get', 'rb_rename',
                'rb_quests', 'rb_quest_claim', 'rb_mini_start', 'rb_mini_finish', 'rb_ledger_list',
                'rb_market_list', 'rb_market_cancel', 'rb_market_buy', 'rb_market_offer', 'rb_market_answer',
                'rb_market_offers', 'rb_market_unoffer', 'rb_admin_lock', 'rb_admin_revoke', 'rb_admin_catalog', 'rb_market_browse', 'rb_market_mine', 'rb_market_price',
                'rb_trade_request', 'rb_trade_accept', 'rb_trade_cancel', 'rb_trade_offer', 'rb_trade_ready',
                'rb_trade_confirm', 'rb_trade_get', 'rb_trades_list', 'rb_live', 'rb_giveaway_join',
                'rb_admin_stats', 'rb_admin_players', 'rb_admin_player', 'rb_admin_grant', 'rb_admin_give', 'rb_admin_take',
                'rb_admin_ban', 'rb_admin_avatar_clear', 'rb_admin_set', 'rb_admin_case', 'rb_admin_giveaway',
                'rb_admin_giveaway_end', 'rb_admin_sale', 'rb_admin_sale_end', 'rb_admin_audit']) loop
        execute format('grant execute on function %s to authenticated', f);
    end loop;
    grant execute on function public.rb_username_free(text) to anon, authenticated;
    grant execute on function public.rb_device_free(text) to anon, authenticated;
    grant execute on function public.rb_login_for(text) to anon, authenticated;
end $$;
