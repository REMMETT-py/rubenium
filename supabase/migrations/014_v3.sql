-- Rubenium 014 (3.0): style cases, event looks set aside, one account created per PC (logging in anywhere is fine),
-- admin bots (fake accounts that live on their own) and admin swaps for the Rocket League tab.
-- Run it once in Supabase, after 013: SQL Editor > New query > paste everything > Run. Safe to run again.

-- ================================================================ winter looks are kept for the Christmas event
-- (not sold, not in cases, not in deals; anyone who owns one keeps it)
update public.rb_catalog set price = null where id in ('banner:snow', 'banner:aurora', 'frame:frost');
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls) values
    ('banner:jungle', 'banner', 'jungle', '', 'rare', 1200, 1200, true, 0),
    ('banner:sakura', 'banner', 'sakura', '', 'special', 3500, 3500, true, 0),
    ('frame:vine', 'frame', 'vine', '', 'rare', 1000, 1000, true, 0)
on conflict (id) do update set kind = excluded.kind, base = excluded.base, rarity = excluded.rarity,
    price = excluded.price, value = excluded.value, tradeable = excluded.tradeable;

-- ================================================================ style cases: every cosmetic can come from a case
-- mode 'kinds:a,b' = the case gives items of those kinds (only ones sold in the shop, never event items).
-- They are collection cases: counted at quick sell you get about 70% back, counted at shop price a little more
-- than you paid. Legendary items stay about 1 in 100.
insert into public.rb_cases (id, pos, price, odds, coin_min, coin_max, exotics, pity_tier, pity_after, variants, mode) values
    ('style', 10, 500, array[3500, 4000, 1900, 500, 100, 0], 200, 1280, false, 9, 0, array[100000, 0, 0, 0, 0], 'kinds:ball,line,font'),
    ('themes', 11, 800, array[5000, 0, 3500, 1200, 300, 0], 250, 1330, false, 9, 0, array[100000, 0, 0, 0, 0], 'kinds:theme'),
    ('profile', 12, 1500, array[3500, 3800, 2000, 550, 150, 0], 600, 3900, false, 9, 0, array[100000, 0, 0, 0, 0], 'kinds:banner,frame')
on conflict (id) do update set pos = excluded.pos, price = excluded.price, odds = excluded.odds,
    coin_min = excluded.coin_min, coin_max = excluded.coin_max, variants = excluded.variants, mode = excluded.mode;

create or replace function public.rb_case_drop(c public.rb_cases, out tier integer, out klass integer, out item text, out coins integer)
language plpgsql security definer set search_path = '' as $$
declare r double precision;
begin
    tier := public.rb_roll(c.odds); klass := 0; coins := 0;
    if tier > 0 and c.mode like 'kinds:%' then                -- a style case: one shop item of that rarity
        select k.id into item from public.rb_catalog k
         where k.kind = any (string_to_array(substr(c.mode, 7), ',')) and k.price is not null
           and k.rarity = (array['standard', 'rare', 'special', 'epic', 'exotic'])[tier]
         order by public.rb_rand() limit 1;
        if item is not null then return; end if;
        tier := 0;                                            -- nothing of that rarity: coins instead
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
    elsif tier = 5 then                                   -- Mythic: Titanium, rarely Prismatic, almost never Gold
        klass := (array[3, 5, 4])[public.rb_roll(array[90000, 9500, 500]) + 1];
        item := public.rb_pick_mythic(klass);
    else
        klass := public.rb_roll(c.variants);
        if klass = 3 and tier <= 2 then klass := 2; end if;  -- no Titanium for Common and Rare badges
        item := public.rb_pick_badge(tier, klass);
    end if;
end $$;

-- ================================================================ one account CREATED per PC; log in from anywhere
-- Logging in no longer ties a PC to an account: only the PC an account was made on is tied to it.
create or replace function public.rb_hello(pc text) returns boolean
language plpgsql security definer set search_path = '' as $$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    return true;
end $$;
-- PCs that were only tied by a login (not where the account was made) are free again
delete from public.rb_devices d using public.profiles p
 where d.owner = p.id and d.at > p.created_at + interval '5 minutes';

-- ================================================================ admin bots: fake accounts that live on their own
alter table public.profiles add column if not exists bot boolean not null default false;
alter table public.profiles add column if not exists bot_cfg jsonb;
alter table public.profiles add column if not exists bot_at timestamptz;
alter table public.profiles add column if not exists bot_real_at timestamptz;
create table if not exists public.rb_bot_tickets (token text primary key, by uuid, at timestamptz not null default now());
alter table public.rb_bot_tickets enable row level security;
revoke all on public.rb_bot_tickets from anon, authenticated;
insert into public.rb_config (key, value) values ('bots_tick', 0) on conflict (key) do nothing;

-- a bot is made with the normal sign up (so it is a real account you can log into), with a one-time admin ticket
do $$ declare src text; begin
    select pg_get_functiondef('public.rb_new_user()'::regprocedure) into src;
    if position('rb_bot_tickets' in src) = 0 then
        src := replace(src, 'if pc !~ ''^[a-f0-9]{32,64}$'' then raise exception ''rb_update_needed''; end if;',
            'if pc like ''bot:%'' then
        if not exists (select 1 from public.rb_bot_tickets t where t.token = substr(pc, 5)
                        and t.at > now() - interval ''10 minutes'') then raise exception ''rb_update_needed''; end if;
        delete from public.rb_bot_tickets where token = substr(pc, 5);
        insert into public.profiles (id, username, login, coins, keys, bot)
            values (new.id, name, lower(name), public.rb_cfg(''start_coins''), public.rb_cfg(''start_keys''), true);
        return new;
    end if;
    if pc !~ ''^[a-f0-9]{32,64}$'' then raise exception ''rb_update_needed''; end if;');
        execute src;
    end if;
end $$;

create or replace function public.rb_admin_bot_ticket() returns text
language plpgsql security definer set search_path = '' as $$
declare me uuid := public.rb_need_admin(); t text := md5(random()::text || clock_timestamp()::text);
begin
    delete from public.rb_bot_tickets where at < now() - interval '1 hour';
    insert into public.rb_bot_tickets (token, by) values (t, me);
    return t;
end $$;

-- set (or change) a bot: hours played, account age, coins, keys, streak, badges, how often and when it is online
create or replace function public.rb_admin_bot_set(name text, cfg jsonb) returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := public.rb_need_admin(); p public.profiles%rowtype; want integer; have integer; i integer;
        t integer; k integer; best text[];
begin
    select * into p from public.profiles where lower(username) = lower(name) for update;
    if not found then raise exception 'rb_no_such_user'; end if;
    if not p.bot then raise exception 'rb_bad_choice'; end if;
    update public.profiles set
        minutes = greatest(0, coalesce((cfg ->> 'hours')::numeric * 60, minutes))::int,
        coins = greatest(0, coalesce((cfg ->> 'coins')::bigint, coins)),
        keys = least(48, greatest(0, coalesce((cfg ->> 'keys')::int, keys))),
        streak = greatest(0, coalesce((cfg ->> 'streak')::int, streak)),
        streak_day = case when coalesce((cfg ->> 'streak')::int, 0) > 0 then public.rb_today() else streak_day end,
        created_at = case when cfg ? 'days' then now() - make_interval(days => greatest(0, (cfg ->> 'days')::int)) else created_at end,
        bot_cfg = coalesce(bot_cfg, '{}'::jsonb) || (cfg - 'hours' - 'coins' - 'keys' - 'streak' - 'days' - 'badges'),
        bot_at = now()
     where id = p.id;
    want := least(60, greatest(0, coalesce((cfg ->> 'badges')::int, 0)));
    select count(*) into have from public.rb_items it where it.owner = p.id and it.item like 'badge:%';
    for i in 1 .. greatest(0, want - have) loop                  -- a believable collection: mostly Common
        t := public.rb_roll(array[0, 7800, 1900, 270, 30]);
        k := (array[0, 1, 2])[public.rb_roll(array[7600, 2350, 50]) + 1];
        perform public.rb_give(p.id, public.rb_pick_badge(t, k), 'case:standard');
    end loop;
    insert into public.rb_seen (owner, item) select owner, item from public.rb_items where owner = p.id on conflict do nothing;
    select array_agg(y.item order by y.value desc) into best from (select distinct it.item, c.value from public.rb_items it
              join public.rb_catalog c on c.id = it.item where it.owner = p.id and c.kind = 'badge') y;
    if best is not null and not coalesce(p.equip ? 'badge1', false) then           -- shows its 3 best badges
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
            'cfg', coalesce(p.bot_cfg, '{}'::jsonb),
            'badges', (select count(*) from public.rb_items it where it.owner = p.id and it.item like 'badge:%'))
            order by p.username) from public.profiles p where p.bot), '[]'::json);
end $$;

create or replace function public.rb_admin_bot_delete(name text) returns boolean
language plpgsql security definer set search_path = '' as $$
declare me uuid := public.rb_need_admin(); p public.profiles%rowtype; x record;
begin
    select * into p from public.profiles where lower(username) = lower(name);
    if not found or not p.bot then raise exception 'rb_bad_choice'; end if;
    for x in select id from public.rb_items where owner = p.id loop perform public.rb_free_item(x.id); end loop;
    perform public.rb_log('bot_delete', p.username, '{}'::jsonb);
    delete from auth.users where id = p.id;
    delete from public.profiles where id = p.id;
    return true;
end $$;

-- the bots' life: at most once a minute, run by anyone's heartbeat. Online in their hours (in 20-minute sessions),
-- time played, AFK coins, keys, login streak, now and then a case or a casino bet. A bot someone is logged into
-- (in the last 30 minutes) is left alone.
create or replace function public.rb_bots_tick() returns void
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; cfg jsonb; h integer; f integer; t integer; inwin boolean; online boolean;
        mins integer; slot bigint; c public.rb_cases%rowtype; d record; bet integer; paid integer;
begin
    update public.rb_config set value = extract(epoch from now())
     where key = 'bots_tick' and value < extract(epoch from now()) - 60;
    if not found then return; end if;
    h := extract(hour from now() at time zone 'Europe/Paris')::int;
    slot := floor(extract(epoch from now()) / 1200)::bigint;
    for p in select * from public.profiles where bot and not banned for update skip locked loop
        cfg := coalesce(p.bot_cfg, '{}'::jsonb);
        if coalesce((cfg ->> 'paused')::boolean, false) or (p.bot_real_at is not null and p.bot_real_at > now() - interval '30 minutes') then
            update public.profiles set bot_at = now() where id = p.id;
            continue;
        end if;
        f := coalesce((cfg ->> 'from')::int, 16); t := coalesce((cfg ->> 'to')::int, 23);
        inwin := case when f <= t then h between f and t else h >= f or h <= t end;
        online := (abs(hashtext(p.id::text || slot::text)) % 100) < coalesce((cfg ->> 'active')::int, 60) * (case when inwin then 1 else 0.08 end);
        mins := least(5, greatest(0, floor(extract(epoch from (now() - coalesce(p.bot_at, now()))) / 60)))::int;
        if online and mins > 0 then
            update public.profiles set last_beat = now(), minutes = minutes + mins,
                   coins = coins + floor(mins * 2.5 * (0.6 + random() * 0.8))::int,
                   key_min = (key_min + mins) % 60, keys = least(48, keys + (key_min + mins) / 60),
                   streak = case when streak_day = public.rb_today() then streak
                                 when streak_day = public.rb_today() - 1 then streak + 1 else 1 end,
                   streak_day = public.rb_today(), bot_at = now()
             where id = p.id;
            if random() < 0.06 then                               -- opens a coin case now and then
                select * into c from public.rb_cases where id = (array['starter', 'standard', 'premium'])[1 + floor(random() * 3)::int];
                select * into p from public.profiles where id = p.id;
                if found and p.coins >= c.price then
                    d := public.rb_case_drop(c);
                    update public.profiles set coins = coins - c.price + d.coins where id = p.id;
                    if d.item is not null then perform public.rb_give(p.id, d.item, 'case:' || c.id);
                        insert into public.rb_seen (owner, item) values (p.id, d.item) on conflict do nothing; end if;
                    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'case:' || c.id, c.price,
                        jsonb_build_object('item', d.item, 'tier', d.tier), false,
                        d.coins + coalesce((select value from public.rb_catalog where id = d.item), 0));
                end if;
            elsif random() < 0.08 then                            -- a small casino bet
                bet := (array[50, 100, 100, 200, 250, 500])[1 + floor(random() * 6)::int];
                if p.coins >= bet then
                    paid := case when random() < 0.45 then floor(bet * (1.5 + random() * 1.6))::int else 0 end;
                    update public.profiles set coins = coins - bet + paid where id = p.id;
                    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id,
                        (array['slots', 'plinko', 'dice', 'mines', 'rocket'])[1 + floor(random() * 5)::int], bet, '{}'::jsonb, false, paid);
                end if;
            end if;
        else
            update public.profiles set bot_at = now() where id = p.id;
        end if;
    end loop;
end $$;

-- the heartbeat runs the bots' life; a bot someone logged into is marked as in use
do $$ declare src text; begin
    select pg_get_functiondef('public.rb_heartbeat(text)'::regprocedure) into src;
    if position('rb_bots_tick' in src) = 0 then
        src := replace(src, E'    if auth.uid() is null then raise exception ''rb_not_logged_in''; end if;',
            E'    if auth.uid() is null then raise exception ''rb_not_logged_in''; end if;\n'
            || E'    perform public.rb_bots_tick();\n'
            || E'    update public.profiles set bot_real_at = now() where id = auth.uid() and bot;');
        execute src;
    end if;
end $$;

-- ================================================================ admin swaps for the Rocket League tab
create table if not exists public.rb_swaps (
    id text primary key check (id ~ '^[a-z0-9_]{3,40}$'), cat text not null, old text not null, new text not null,
    file text not null check (file ~ '^[A-Za-z0-9_.-]{3,80}$'), sha text not null default '', orig_sha text not null default '',
    img boolean not null default false, orig boolean not null default false,
    state text not null default 'live' check (state in ('live', 'paused', 'locked')),
    at timestamptz not null default now());
alter table public.rb_swaps enable row level security;
revoke all on public.rb_swaps from anon, authenticated;

create or replace function public.rb_swaps_list() returns json
language sql stable security definer set search_path = '' as $$
    select coalesce(json_agg(json_build_object('id', s.id, 'cat', s.cat, 'old', s.old, 'new', s.new, 'file', s.file,
           'sha', s.sha, 'orig_sha', s.orig_sha, 'img', s.img, 'orig', s.orig, 'state', s.state) order by s.at), '[]'::json)
      from public.rb_swaps s $$;

create or replace function public.rb_admin_swap_save(sid text, cat text, old text, new text, file text, sha text,
                                                     orig_sha text, img boolean, orig boolean) returns boolean
language plpgsql security definer set search_path = '' as $$
declare me uuid := public.rb_need_admin();
begin
    insert into public.rb_swaps (id, cat, old, new, file, sha, orig_sha, img, orig)
        values (sid, cat, left(old, 40), left(new, 40), file, coalesce(sha, ''), coalesce(orig_sha, ''), img, orig)
        on conflict (id) do update set cat = excluded.cat, old = excluded.old, new = excluded.new, file = excluded.file,
            sha = excluded.sha, orig_sha = case when excluded.orig then excluded.orig_sha else public.rb_swaps.orig_sha end,
            img = public.rb_swaps.img or excluded.img, orig = public.rb_swaps.orig or excluded.orig, at = now();
    perform public.rb_log('swap', sid, jsonb_build_object('new', new));
    return true;
end $$;

create or replace function public.rb_admin_swap_state(sid text, st text) returns boolean
language plpgsql security definer set search_path = '' as $$
declare me uuid := public.rb_need_admin();
begin
    if st = 'delete' then
        delete from public.rb_swaps where id = sid;
    else
        update public.rb_swaps set state = st where id = sid;
        if not found then raise exception 'rb_bad_choice'; end if;
    end if;
    perform public.rb_log('swap_' || st, sid, '{}'::jsonb);
    return true;
end $$;

-- the files live in Supabase Storage (bucket "swaps"): everyone can download, only the admin can upload
do $$ begin
    if exists (select 1 from pg_namespace where nspname = 'storage') then
        insert into storage.buckets (id, name, public) values ('swaps', 'swaps', true) on conflict (id) do update set public = true;
        drop policy if exists "rb swaps admin insert" on storage.objects;
        drop policy if exists "rb swaps admin update" on storage.objects;
        drop policy if exists "rb swaps admin delete" on storage.objects;
        create policy "rb swaps admin insert" on storage.objects for insert to authenticated
            with check (bucket_id = 'swaps' and exists (select 1 from public.profiles p where p.id = auth.uid() and p.admin));
        create policy "rb swaps admin update" on storage.objects for update to authenticated
            using (bucket_id = 'swaps' and exists (select 1 from public.profiles p where p.id = auth.uid() and p.admin));
        create policy "rb swaps admin delete" on storage.objects for delete to authenticated
            using (bucket_id = 'swaps' and exists (select 1 from public.profiles p where p.id = auth.uid() and p.admin));
    end if;
end $$;

-- ================================================================ who may call the new functions
do $$ declare f text; begin
    foreach f in array array['rb_admin_bot_ticket()', 'rb_admin_bot_set(text, jsonb)', 'rb_admin_bots()',
                             'rb_admin_bot_delete(text)', 'rb_bots_tick()', 'rb_swaps_list()',
                             'rb_admin_swap_save(text, text, text, text, text, text, text, boolean, boolean)',
                             'rb_admin_swap_state(text, text)', 'rb_hello(text)', 'rb_case_drop(public.rb_cases)'] loop
        execute format('revoke all on function public.%s from public, anon, authenticated', f);
    end loop;
    foreach f in array array['rb_admin_bot_ticket()', 'rb_admin_bot_set(text, jsonb)', 'rb_admin_bots()',
                             'rb_admin_bot_delete(text)', 'rb_swaps_list()', 'rb_hello(text)',
                             'rb_admin_swap_save(text, text, text, text, text, text, text, boolean, boolean)',
                             'rb_admin_swap_state(text, text)'] loop
        execute format('grant execute on function public.%s to authenticated', f);
    end loop;
    grant execute on function public.rb_swaps_list() to anon;
end $$;

-- ================================================================ every app older than 3.0 must update before playing online
insert into public.rb_config (key, value) values ('min_build', 2026111707)
on conflict (key) do update set value = greatest(public.rb_config.value, excluded.value);
