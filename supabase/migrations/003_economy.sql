-- Rubenium 003: the online economy. Coins, keys, items, the catalogue, buying, selling to the vendor, equipping.
-- Everything of value is decided here, never in the app. Safe to run more than once.
-- Run it in Supabase: SQL Editor > New query > paste > Run.

-- ---------------------------------------------------------------- settings (every number in one place)
create table if not exists public.rb_config (key text primary key, value numeric not null);
insert into public.rb_config (key, value) values
    ('start_coins', 500), ('start_keys', 3),
    ('coin_every_min', 15), ('coin_amount', 10), ('coin_day_cap', 400),
    ('key_every_min', 60), ('key_cap', 48),
    ('vendor_share', 0.45), ('import_coin_cap', 2000),
    ('price_standard', 200), ('price_rare', 600), ('price_special', 1500), ('price_epic', 3500),
    ('value_exotic', 12000)
on conflict (key) do nothing;
alter table public.rb_config enable row level security;
drop policy if exists "read config" on public.rb_config;
create policy "read config" on public.rb_config for select to anon, authenticated using (true);
revoke all on public.rb_config from anon, authenticated;
grant select on public.rb_config to anon, authenticated;

create or replace function public.rb_cfg(k text) returns numeric
language sql stable security definer set search_path = '' as $$ select value from public.rb_config where key = k $$;

-- ---------------------------------------------------------------- the wallet lives on the profile
alter table public.profiles add column if not exists coins bigint not null default 500 check (coins >= 0);
alter table public.profiles add column if not exists keys integer not null default 3 check (keys >= 0);
alter table public.profiles add column if not exists coin_min integer not null default 0;
alter table public.profiles add column if not exists key_min integer not null default 0;
alter table public.profiles add column if not exists day date not null default current_date;
alter table public.profiles add column if not exists day_coins integer not null default 0;
alter table public.profiles add column if not exists equip jsonb not null default '{}'::jsonb;
alter table public.profiles add column if not exists imported boolean not null default false;

-- every change of coins or keys, for ever (append only)
create table if not exists public.rb_ledger (
    id bigserial primary key, owner uuid not null references public.profiles (id) on delete cascade,
    coins integer not null default 0, keys integer not null default 0,
    reason text not null, ref text, at timestamptz not null default now());
create index if not exists rb_ledger_owner on public.rb_ledger (owner, id desc);

-- ---------------------------------------------------------------- catalogue: everything that can be owned
create table if not exists public.rb_catalog (
    id text primary key, kind text not null, base text not null, variant text not null default '',
    rarity text not null check (rarity in ('standard', 'rare', 'special', 'epic', 'exotic')),
    price integer,                       -- coins in the shop; null = not sold
    value integer not null,              -- worth (vendor and estimates); for progression: minutes needed
    tradeable boolean not null default true);

-- every owned thing is one row with its own id: an item can never be in two places
create table if not exists public.rb_items (
    id uuid primary key default gen_random_uuid(),
    owner uuid not null references public.profiles (id) on delete cascade,
    item text not null references public.rb_catalog (id),
    origin text not null, locked text, got_at timestamptz not null default now());
create index if not exists rb_items_owner on public.rb_items (owner);

-- what an account has ever owned (stays after it is sold or traded: shown greyed out)
create table if not exists public.rb_seen (
    owner uuid not null references public.profiles (id) on delete cascade, item text not null,
    primary key (owner, item));

-- a request that was already done is never done twice (double click, resend after a network cut)
create table if not exists public.rb_requests (
    owner uuid not null references public.profiles (id) on delete cascade, req text not null,
    result jsonb not null, at timestamptz not null default now(), primary key (owner, req));

do $$ declare t text; begin
    foreach t in array array['rb_ledger', 'rb_catalog', 'rb_items', 'rb_seen', 'rb_requests'] loop
        execute format('alter table public.%I enable row level security', t);
        execute format('revoke all on public.%I from anon, authenticated', t);
    end loop;
end $$;
grant select on public.rb_catalog to anon, authenticated;
grant select on public.rb_ledger, public.rb_items, public.rb_seen to authenticated;
drop policy if exists "read catalog" on public.rb_catalog;
create policy "read catalog" on public.rb_catalog for select to anon, authenticated using (true);
drop policy if exists "read own ledger" on public.rb_ledger;
create policy "read own ledger" on public.rb_ledger for select to authenticated using (owner = (select auth.uid()));
drop policy if exists "read own items" on public.rb_items;
create policy "read own items" on public.rb_items for select to authenticated using (owner = (select auth.uid()));
drop policy if exists "read own seen" on public.rb_seen;
create policy "read own seen" on public.rb_seen for select to authenticated using (owner = (select auth.uid()));

-- ---------------------------------------------------------------- catalogue content (the single source of truth)
create or replace function public.rb_seed_catalog() returns void
language plpgsql security definer set search_path = '' as $$
declare
    tiers text[] := array['standard', 'rare', 'special', 'epic', 'exotic'];
    badges text[] := array['heart','drop','clover','paw','cat','fish','cherry','feather','note','dice','headset',
        'gamepad','mushroom','tree','wave',                                             -- 1-15 standard
        'ghost','spade','club','diamond','octagon','cube','eye','snowflake','mountain','moon','sun','star','bolt',
        'flame','anchor',                                                              -- 16-30 rare
        'key','pickaxe','rook','shield','sword','skull','trident','quill','hourglass','target','comet','saturn',
        'alien','rocket','shootingstar','planet','crown','trophy','goldenstar','sunburst'];   -- 31-42 special, 43-50 epic
    exotics text[] := array['galaxy', 'phoenix', 'glitch', 'crystal', 'dragon'];
    colours text[] := array['blue','green','red','yellow','orange','brown','teal','lava','purple','sky','lime','pink','beam'];
    prestige text[] := array['black', 'white', 'gold'];
    -- shop cosmetics: (kind, id, base tier 0-3)
    cosmetics text[][] := array[
        ['ball','orbit','0'],['ball','pixel','0'],['ball','split','0'],['ball','halo','1'],['ball','bubble','1'],
        ['ball','spiral','1'],['ball','bullseye','2'],['ball','hex','2'],['ball','ripple','3'],['ball','shard','3'],
        ['line','dash','0'],['line','beads','0'],['line','zigzag','0'],['line','twin','1'],['line','pulse','1'],
        ['line','chain','1'],['line','ribbon','2'],['line','steps','2'],['line','spark','3'],['line','laser','3'],
        ['font','rounded','0'],['font','mono','1'],['font','serif','1'],['font','display','2'],['font','script','3']];
    themes text[][] := array[['sunset','1'],['ocean','1'],['forest','2'],['candy','2'],['storm','3'],['retro','3']];
    -- progression: (id, minutes needed). Not tradeable, not sold: unlocked by time only.
    prog text[][] := array[['theme:1','0'],['ball:0','0'],['ring:0','0'],['font:0','0'],
        ['theme:2','120'],['ball:1','300'],['ring:1','480'],['theme:3','720'],['theme:4','1200'],['ball:2','1800'],
        ['ring:2','2400'],['theme:5','3300'],['theme:6','4500'],['ball:3','6000'],['ring:3','7500'],
        ['theme:7','9000'],['theme:8','12000']];
    b text; v text; i int; t int; p int; row text[];
    function_price int[];
begin
    function_price := array[public.rb_cfg('price_standard')::int, public.rb_cfg('price_rare')::int,
                            public.rb_cfg('price_special')::int, public.rb_cfg('price_epic')::int,
                            public.rb_cfg('value_exotic')::int];
    delete from public.rb_catalog c where not exists (select 1 from public.rb_items it where it.item = c.id);
    for i in 1 .. array_length(badges, 1) loop
        b := badges[i];
        t := case when i <= 15 then 0 when i <= 30 then 1 when i <= 42 then 2 else 3 end;
        insert into public.rb_catalog values ('badge:' || b || ':grey', 'badge', b, 'grey', 'standard',
            function_price[1], function_price[1], true) on conflict (id) do nothing;
        foreach v in array colours loop
            insert into public.rb_catalog values ('badge:' || b || ':' || v, 'badge', b, v, tiers[t + 1],
                function_price[t + 1], function_price[t + 1], true) on conflict (id) do nothing;
        end loop;
        foreach v in array prestige loop                -- black / white / gold: one tier higher, cases only
            p := least(t + 1, 3);
            insert into public.rb_catalog values ('badge:' || b || ':' || v, 'badge', b, v, tiers[p + 1], null,
                (function_price[p + 1] * (case v when 'gold' then 1.6 else 1.2 end))::int, true)
                on conflict (id) do nothing;
        end loop;
    end loop;
    foreach b in array exotics loop                      -- the five Exotic badges: cases and trading only
        insert into public.rb_catalog values ('badge:' || b || ':prime', 'badge', b, 'prime', 'epic', null, 5000, true)
            on conflict (id) do nothing;
        foreach v in array prestige loop
            insert into public.rb_catalog values ('badge:' || b || ':' || v, 'badge', b, v, 'exotic', null,
                (function_price[5] * (case v when 'gold' then 1.6 else 1.0 end))::int, true) on conflict (id) do nothing;
        end loop;
    end loop;
    foreach row slice 1 in array cosmetics loop          -- balls, lines, fonts: every colour is sold
        t := row[3]::int;
        insert into public.rb_catalog values (row[1] || ':' || row[2] || ':grey', row[1], row[2], 'grey', tiers[t + 1],
            (function_price[t + 1] * 0.8)::int, (function_price[t + 1] * 0.8)::int, true) on conflict (id) do nothing;
        foreach v in array colours loop
            insert into public.rb_catalog values (row[1] || ':' || row[2] || ':' || v, row[1], row[2], v, tiers[t + 1],
                function_price[t + 1], function_price[t + 1], true) on conflict (id) do nothing;
        end loop;
        foreach v in array prestige loop
            p := least(t + 1, 3);
            i := (function_price[p + 1] * (case v when 'gold' then 1.6 else 1.25 end))::int;
            insert into public.rb_catalog values (row[1] || ':' || row[2] || ':' || v, row[1], row[2], v, tiers[p + 1],
                i, i, true) on conflict (id) do nothing;
        end loop;
    end loop;
    foreach row slice 1 in array themes loop
        t := row[2]::int;
        insert into public.rb_catalog values ('theme:' || row[1], 'theme', row[1], '', tiers[t + 1],
            (function_price[t + 1] * 1.2)::int, (function_price[t + 1] * 1.2)::int, true) on conflict (id) do nothing;
    end loop;
    foreach row slice 1 in array prog loop
        insert into public.rb_catalog values ('prog:' || row[1], 'prog', split_part(row[1], ':', 1), '', 'standard',
            null, row[2]::int, false) on conflict (id) do update set value = excluded.value;
    end loop;
end $$;
revoke all on function public.rb_seed_catalog() from public, anon, authenticated;
select public.rb_seed_catalog();

-- ---------------------------------------------------------------- helpers (not callable from the app)
create or replace function public.rb_lock_me() returns public.profiles
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype;
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    select * into p from public.profiles where id = auth.uid() for update;       -- one action at a time per account
    if not found then raise exception 'rb_no_profile'; end if;
    return p;
end $$;

create or replace function public.rb_pay(who uuid, d_coins integer, d_keys integer, why text, ref text) returns void
language plpgsql security definer set search_path = '' as $$
begin
    if d_coins = 0 and d_keys = 0 then return; end if;
    begin
        update public.profiles set coins = coins + d_coins, keys = keys + d_keys where id = who;
    exception when check_violation then
        raise exception 'rb_not_enough';                 -- never below zero
    end;
    insert into public.rb_ledger (owner, coins, keys, reason, ref) values (who, d_coins, d_keys, why, ref);
end $$;

create or replace function public.rb_give(who uuid, what text, origin text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare new_id uuid;
begin
    insert into public.rb_items (owner, item, origin) values (who, what, origin) returning id into new_id;
    insert into public.rb_seen (owner, item) values (who, what) on conflict do nothing;
    return new_id;
end $$;

create or replace function public.rb_done(who uuid, r text) returns jsonb
language sql security definer set search_path = '' as $$
    select result from public.rb_requests where owner = who and req = r $$;

create or replace function public.rb_remember(who uuid, r text, res jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
    if r is not null and r <> '' then
        insert into public.rb_requests (owner, req, result) values (who, left(r, 64), res) on conflict do nothing;
        delete from public.rb_requests where owner = who and at < now() - interval '2 days';
    end if;
    return res;
end $$;

-- does this account have the right to wear `what`? (an owned item, or a progression unlock by time played)
create or replace function public.rb_can_wear(p public.profiles, what text) returns boolean
language sql stable security definer set search_path = '' as $$
    select exists (select 1 from public.rb_catalog c where c.id = what and c.kind = 'prog' and c.value <= p.minutes)
        or exists (select 1 from public.rb_items it where it.owner = p.id and it.item = what) $$;

-- ---------------------------------------------------------------- what the app may call
-- Everything about my account in one answer.
create or replace function public.rb_state() returns json
language plpgsql stable security definer set search_path = '' as $$
declare p public.profiles%rowtype;
begin
    select * into p from public.profiles where id = auth.uid();
    if not found then raise exception 'rb_not_logged_in'; end if;
    return json_build_object(
        'username', p.username, 'minutes', p.minutes, 'coins', p.coins, 'keys', p.keys,
        'coin_min', p.coin_min, 'key_min', p.key_min,
        'day_coins', case when p.day = current_date then p.day_coins else 0 end,
        'equip', p.equip, 'imported', p.imported,
        'items', coalesce((select json_agg(json_build_object('id', it.id, 'item', it.item, 'locked', it.locked,
                                                             'origin', it.origin) order by it.got_at)
                             from public.rb_items it where it.owner = p.id), '[]'::json),
        'seen', coalesce((select json_agg(s.item) from public.rb_seen s where s.owner = p.id), '[]'::json));
end $$;

-- Heartbeat: time played, and with it the coins and keys that come with time. Server clock only.
create or replace function public.rb_heartbeat(device text) returns json
language plpgsql security definer set search_path = '' as $$
declare
    p public.profiles%rowtype;
    credited boolean := false; elsewhere boolean := false;
    got_coins integer := 0; got_keys integer := 0;
begin
    p := public.rb_lock_me();
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
                             'got_coins', got_coins, 'got_keys', got_keys, 'coin_min', p.coin_min, 'key_min', p.key_min);
end $$;

-- Buy from the shop.
create or replace function public.rb_buy(what text, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; c public.rb_catalog%rowtype; res jsonb; new_id uuid;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into c from public.rb_catalog where id = what;
    if not found or c.price is null then raise exception 'rb_not_for_sale'; end if;
    if exists (select 1 from public.rb_items it where it.owner = p.id and it.item = what) then
        raise exception 'rb_already_owned';
    end if;
    perform public.rb_pay(p.id, -c.price, 0, 'shop', what);
    new_id := public.rb_give(p.id, what, 'shop');
    return public.rb_remember(p.id, req, jsonb_build_object('id', new_id, 'item', what, 'coins', p.coins - c.price));
end $$;

-- Sell an item to the vendor for quick coins.
create or replace function public.rb_sell(item_id uuid, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; it public.rb_items%rowtype; c public.rb_catalog%rowtype; res jsonb; pay integer;
        slot text;
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
    if not exists (select 1 from public.rb_items x where x.owner = p.id and x.item = it.item) then
        for slot in select key from jsonb_each_text(p.equip) where value = it.item loop     -- no longer owned: take it off
            p.equip := p.equip - slot;
        end loop;
        update public.profiles set equip = p.equip where id = p.id;
    end if;
    perform public.rb_pay(p.id, pay, 0, 'vendor', it.item);
    return public.rb_remember(p.id, req, jsonb_build_object('paid', pay, 'coins', p.coins + pay, 'equip', p.equip));
end $$;

-- What the vendor would pay for an item of the catalogue.
create or replace function public.rb_vendor_price(what text) returns integer
language sql stable security definer set search_path = '' as $$
    select greatest(1, floor(c.value * public.rb_cfg('vendor_share'))::int)
      from public.rb_catalog c where c.id = what and c.tradeable $$;

-- Wear something (or take it off with an empty text).
create or replace function public.rb_equip(slot text, what text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; kind text; want text;
begin
    p := public.rb_lock_me();
    want := case slot when 'theme' then 'theme' when 'ball' then 'ball' when 'ring' then 'line' when 'font' then 'font'
                      when 'badge1' then 'badge' when 'badge2' then 'badge' when 'badge3' then 'badge' end;
    if want is null then raise exception 'rb_bad_slot'; end if;
    if coalesce(what, '') = '' then
        p.equip := p.equip - slot;
    else
        select case when c.kind = 'prog' then (case c.base when 'ring' then 'line' else c.base end) else c.kind end
          into kind from public.rb_catalog c where c.id = what;
        if kind is distinct from want then raise exception 'rb_wrong_kind'; end if;
        if not public.rb_can_wear(p, what) then raise exception 'rb_not_yours'; end if;
        if want = 'badge' and exists (select 1 from jsonb_each_text(p.equip) e
                                       where e.key like 'badge%' and e.key <> slot and e.value = what) then
            raise exception 'rb_already_worn';
        end if;
        p.equip := p.equip || jsonb_build_object(slot, what);
    end if;
    update public.profiles set equip = p.equip where id = p.id;
    return p.equip;
end $$;

-- One time only: bring old progress from the PC. Coins are capped, so edited files gain nothing.
create or replace function public.rb_import(old_coins integer) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; add integer;
begin
    p := public.rb_lock_me();
    if p.imported then return jsonb_build_object('imported', false, 'coins', p.coins); end if;
    add := greatest(0, least(coalesce(old_coins, 0), public.rb_cfg('import_coin_cap')::int));
    update public.profiles set imported = true where id = p.id;
    perform public.rb_pay(p.id, add, 0, 'import', null);
    return jsonb_build_object('imported', true, 'added', add, 'coins', p.coins + add);
end $$;

-- ---------------------------------------------------------------- who may call what
do $$ declare f text; begin
    foreach f in array array['rb_cfg(text)', 'rb_lock_me()', 'rb_pay(uuid, integer, integer, text, text)',
        'rb_give(uuid, text, text)', 'rb_done(uuid, text)', 'rb_remember(uuid, text, jsonb)',
        'rb_can_wear(public.profiles, text)', 'rb_state()', 'rb_heartbeat(text)', 'rb_buy(text, text)',
        'rb_sell(uuid, text)', 'rb_vendor_price(text)', 'rb_equip(text, text)', 'rb_import(integer)'] loop
        execute format('revoke all on function public.%s from public, anon, authenticated', f);
    end loop;
    foreach f in array array['rb_state()', 'rb_heartbeat(text)', 'rb_buy(text, text)', 'rb_sell(uuid, text)',
        'rb_vendor_price(text)', 'rb_equip(text, text)', 'rb_import(integer)'] loop
        execute format('grant execute on function public.%s to authenticated', f);
    end loop;
end $$;
