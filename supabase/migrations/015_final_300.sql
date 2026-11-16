-- Rubenium 015 (3.0.0): duel bets up to 80% of the lower balance, balls and banners re-ranked, 10 new banners,
-- banners that turn gold the longer you wear them, song history friends can see, and a forced update to 3.0.0.
-- Run it once in Supabase -> SQL Editor (after 014). Running it again changes nothing.

-- ================================================================ balls: the animated ones are now the rare ones
do $$
declare
    tiers text[] := array['standard', 'rare', 'special', 'epic'];
    base_price integer[] := array[120, 360, 960, 2400];
    plan text[][] := array[['pixel', '1'], ['halo', '1'], ['bullseye', '1'],
                           ['split', '2'], ['shard', '2'], ['hex', '2'],
                           ['bubble', '3'], ['orbit', '3'],
                           ['spiral', '4'], ['ripple', '4']];
    row text[]; t integer; up integer; pr integer;
begin
    foreach row slice 1 in array plan loop
        t := row[2]::int;
        up := least(t + 1, 4);
        update public.rb_catalog set rarity = tiers[t], price = base_price[t], value = base_price[t]
         where kind = 'ball' and base = row[1] and variant = 'grey';
        pr := round(base_price[t] * 1.25);
        update public.rb_catalog set rarity = tiers[t], price = pr, value = pr
         where kind = 'ball' and base = row[1] and variant not in ('grey', 'black', 'white');
        pr := round(base_price[up] * 1.5625);
        update public.rb_catalog set rarity = tiers[up], price = pr, value = pr
         where kind = 'ball' and base = row[1] and variant in ('black', 'white');
    end loop;
end $$;

-- ================================================================ banners: re-ranked by how they look, 10 new ones
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls) values
    ('banner:carbon', 'banner', 'carbon', '', 'standard', 400, 400, true, 0),
    ('banner:dunes', 'banner', 'dunes', '', 'standard', 400, 400, true, 0),
    ('banner:honeycomb', 'banner', 'honeycomb', '', 'rare', 1200, 1200, true, 0),
    ('banner:comet', 'banner', 'comet', '', 'rare', 1200, 1200, true, 0),
    ('banner:deepsea', 'banner', 'deepsea', '', 'rare', 1200, 1200, true, 0),
    ('banner:city', 'banner', 'city', '', 'special', 3500, 3500, true, 0),
    ('banner:neon', 'banner', 'neon', '', 'special', 3500, 3500, true, 0),
    ('banner:fireflies', 'banner', 'fireflies', '', 'special', 3500, 3500, true, 0),
    ('banner:storm', 'banner', 'storm', '', 'epic', 9000, 9000, true, 0),
    ('banner:vortex', 'banner', 'vortex', '', 'epic', 9000, 9000, true, 0)
on conflict (id) do nothing;

do $$
declare
    plan text[][] := array[['dusk', 'standard'], ['mint', 'standard'], ['steel', 'standard'], ['rose', 'standard'],
                           ['stripes', 'standard'], ['dots', 'standard'], ['carbon', 'standard'], ['dunes', 'standard'],
                           ['waves', 'rare'], ['peaks', 'rare'], ['ember', 'rare'], ['circuit', 'rare'], ['sunset', 'rare'],
                           ['honeycomb', 'rare'], ['comet', 'rare'], ['deepsea', 'rare'],
                           ['grid', 'special'], ['jungle', 'special'], ['sakura', 'special'], ['lava', 'special'],
                           ['prism', 'special'], ['city', 'special'], ['neon', 'special'], ['fireflies', 'special'],
                           ['galaxy', 'epic'], ['nebula', 'epic'], ['matrix', 'epic'], ['storm', 'epic'], ['vortex', 'epic']];
    row text[]; pr integer;
begin
    foreach row slice 1 in array plan loop
        pr := case row[2] when 'standard' then 400 when 'rare' then 1200 when 'special' then 3500 else 9000 end;
        update public.rb_catalog set rarity = row[2], price = pr, value = pr
         where id = 'banner:' || row[1] and price is not null;          -- the Christmas banners stay unsold
    end loop;
end $$;

-- ================================================================ gold banners: the longer you wear one, the more gold it gets
create table if not exists public.rb_wear (
    owner uuid not null references public.profiles (id) on delete cascade, item text not null,
    minutes integer not null default 0, primary key (owner, item));
alter table public.rb_wear enable row level security;
revoke all on public.rb_wear from anon, authenticated;

-- hours to reach gold 1, 2 and 3: the rarer the banner, the longer it takes
create or replace function public.rb_gold_steps(item text) returns integer[]
language sql stable security definer set search_path = '' as $$
    select case (select c.rarity from public.rb_catalog c where c.id = item)
               when 'standard' then array[10, 30, 75]
               when 'rare' then array[15, 45, 110]
               when 'special' then array[25, 75, 180]
               else array[40, 120, 300] end $$;

create or replace function public.rb_gold_level(item text, minutes integer) returns integer
language sql stable security definer set search_path = '' as $$
    select case when item is null or item not like 'banner:%' then 0
                else (select count(*)::int from unnest(public.rb_gold_steps(item)) h where coalesce(minutes, 0) >= h * 60) end $$;

create or replace function public.rb_wear_add(who uuid, what text) returns void
language plpgsql security definer set search_path = '' as $$
begin
    if what is null or what not like 'banner:%' then return; end if;
    if not exists (select 1 from public.rb_items i where i.owner = who and i.item = what) then return; end if;
    insert into public.rb_wear as w (owner, item, minutes) values (who, what, 1)
    on conflict (owner, item) do update set minutes = w.minutes + 1;
end $$;

-- your banners: minutes worn, gold level and the hours of each step
create or replace function public.rb_wear_mine() returns json
language plpgsql stable security definer set search_path = '' as $$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    return coalesce((select json_object_agg(x.item, json_build_object(
                         'minutes', coalesce(w.minutes, 0), 'level', public.rb_gold_level(x.item, w.minutes),
                         'steps', public.rb_gold_steps(x.item)))
                       from (select distinct i.item from public.rb_items i where i.owner = auth.uid() and i.item like 'banner:%') x
                       left join public.rb_wear w on w.owner = auth.uid() and w.item = x.item), '{}'::json);
end $$;

-- every minute the heartbeat counts also counts for the banner you wear
do $$ declare src text; begin
    select pg_get_functiondef('public.rb_heartbeat(text)'::regprocedure) into src;
    if position('rb_wear_add' in src) = 0 then
        src := replace(src, E'p.minutes := p.minutes + 1;',
                       E'p.minutes := p.minutes + 1; perform public.rb_wear_add(p.id, p.equip ->> ''banner'');');
        execute src;
    end if;
end $$;

-- what everyone shows next to their name, now with the gold level of the banner
create or replace function public.rb_looks() returns json
language plpgsql stable security definer set search_path = '' as $$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    return coalesce((select json_object_agg(p.username, jsonb_strip_nulls(jsonb_build_object(
                         'tag', p.equip ->> 'tag', 'frame', p.equip ->> 'frame', 'banner', p.equip ->> 'banner',
                         'gold', nullif(public.rb_gold_level(p.equip ->> 'banner',
                                    (select w.minutes from public.rb_wear w where w.owner = p.id and w.item = p.equip ->> 'banner')), 0))))
                       from public.profiles p
                      where not p.banned and p.equip ?| array['tag', 'frame', 'banner']), '{}'::json);
end $$;

-- ================================================================ duels: any bet from 10 up to 80% of the lower balance
create or replace function public.rb_duel_cap(a bigint, b bigint) returns integer
language sql immutable as $$ select (floor(least(coalesce(a, 0), coalesce(b, 0)) * 0.8 / 10) * 10)::int $$;

create or replace function public.rb_duel_limit(name text) returns integer
language plpgsql stable security definer set search_path = '' as $$
declare me public.profiles%rowtype; o public.profiles%rowtype;
begin
    select * into me from public.profiles where id = auth.uid();
    if not found then raise exception 'rb_not_logged_in'; end if;
    select * into o from public.profiles where lower(username) = lower(name);
    if not found or o.id = me.id then raise exception 'rb_no_such_user'; end if;
    if not public.rb_is_friend(me.id, o.id) then raise exception 'rb_not_friends'; end if;
    return public.rb_duel_cap(me.coins, o.coins);
end $$;

create or replace function public.rb_duel_ask(name text, game text, tier integer, bet integer) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; o public.profiles%rowtype; seed jsonb; did uuid;
begin
    p := public.rb_lock_me();
    select * into o from public.profiles where lower(username) = lower(name);
    if not found or o.id = p.id then raise exception 'rb_no_such_user'; end if;
    if not public.rb_is_friend(p.id, o.id) then raise exception 'rb_not_friends'; end if;
    if game not in ('tap', 'memory', 'park') or tier is null or tier not between 1 and 3 then raise exception 'rb_bad_choice'; end if;
    bet := coalesce(bet, 0);
    if bet <> 0 and (bet < 10 or bet % 10 <> 0 or bet > public.rb_duel_cap(p.coins, o.coins)) then
        raise exception 'rb_bad_bet';
    end if;
    if bet > 0 and not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    if (select count(*) from public.rb_duels d where d.a = p.id and d.state = 'asked') >= 3 then raise exception 'rb_too_many'; end if;
    seed := case game when 'tap' then public.rb_tap_chart()
                      when 'memory' then to_jsonb(public.rb_mem_board(tier))
                      else (select to_jsonb(pl.id) from public.rb_park_levels pl where pl.tier = rb_duel_ask.tier
                             order by public.rb_rand() limit 1) end;
    perform public.rb_pay(p.id, -bet, 0, 'duel_bet', null);
    insert into public.rb_duels (a, b, game, tier, bet, seed) values (p.id, o.id, game, tier, bet, seed) returning id into did;
    perform public.rb_notice(o.id, 'duel', jsonb_build_object('from', p.username, 'game', game, 'bet', bet, 'id', did));
    return json_build_object('id', did, 'coins', p.coins - bet);
end $$;

-- ================================================================ song history: your friends can see what you played
alter table public.profiles add column if not exists share_songs boolean not null default true;

create table if not exists public.rb_songs (
    id bigserial primary key, owner uuid not null references public.profiles (id) on delete cascade,
    title text not null check (length(title) between 1 and 120), artist text not null default '' check (length(artist) <= 120),
    at timestamptz not null default now());
create index if not exists rb_songs_owner on public.rb_songs (owner, id desc);
alter table public.rb_songs enable row level security;
revoke all on public.rb_songs from anon, authenticated;
revoke all on sequence public.rb_songs_id_seq from anon, authenticated;

create or replace function public.rb_song_add(title text, artist text) returns boolean
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); last public.rb_songs%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    title := left(btrim(regexp_replace(coalesce(title, ''), '[\x00-\x1f]', '', 'g')), 120);
    artist := left(btrim(regexp_replace(coalesce(artist, ''), '[\x00-\x1f]', '', 'g')), 120);
    if length(title) = 0 then return false; end if;
    if not coalesce((select share_songs from public.profiles where id = me), false) then return false; end if;
    select * into last from public.rb_songs s where s.owner = me order by s.id desc limit 1;
    if found and (last.title = title and last.artist = artist) then return false; end if;
    if (select count(*) from public.rb_songs s where s.owner = me and s.at > now() - interval '1 minute') >= 6 then
        return false;                                         -- skipping fast through songs: not every one is kept
    end if;
    insert into public.rb_songs (owner, title, artist) values (me, title, artist);
    delete from public.rb_songs s where s.owner = me
       and s.id < (select x.id from public.rb_songs x where x.owner = me order by x.id desc offset 29 limit 1);
    return true;
end $$;

create or replace function public.rb_song_share(share boolean) returns boolean
language plpgsql security definer set search_path = '' as $$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    update public.profiles set share_songs = coalesce(share, true) where id = auth.uid();
    if not coalesce(share, true) then delete from public.rb_songs where owner = auth.uid(); end if;
    return coalesce(share, true);
end $$;

-- the last 30 songs of yourself or a friend (only if they share them)
create or replace function public.rb_songs(name text) returns json
language plpgsql stable security definer set search_path = '' as $$
declare me uuid := auth.uid(); o public.profiles%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into o from public.profiles where lower(username) = lower(coalesce(nullif(name, ''),
        (select username from public.profiles where id = me)));
    if not found then raise exception 'rb_no_such_user'; end if;
    if o.id <> me and not public.rb_is_friend(me, o.id) then raise exception 'rb_friends_only'; end if;
    return json_build_object('shared', o.share_songs,
        'rows', case when o.share_songs or o.id = me then coalesce((select json_agg(json_build_object(
                    'title', s.title, 'artist', s.artist, 'at', s.at) order by s.id desc)
                 from (select * from public.rb_songs where owner = o.id order by id desc limit 30) s), '[]'::json)
                 else '[]'::json end);
end $$;

-- ================================================================ who may call the new functions
do $$ declare f text; begin
    foreach f in array array['rb_gold_steps(text)', 'rb_gold_level(text, integer)', 'rb_wear_add(uuid, text)',
                             'rb_wear_mine()', 'rb_looks()', 'rb_duel_cap(bigint, bigint)', 'rb_duel_limit(text)',
                             'rb_duel_ask(text, text, integer, integer)', 'rb_song_add(text, text)',
                             'rb_song_share(boolean)', 'rb_songs(text)'] loop
        execute format('revoke all on function public.%s from public, anon, authenticated', f);
    end loop;
    foreach f in array array['rb_wear_mine()', 'rb_looks()', 'rb_duel_limit(text)',
                             'rb_duel_ask(text, text, integer, integer)', 'rb_song_add(text, text)',
                             'rb_song_share(boolean)', 'rb_songs(text)'] loop
        execute format('grant execute on function public.%s to authenticated', f);
    end loop;
end $$;

-- ================================================================ every app older than 3.0.0 must update before playing online
insert into public.rb_config (key, value) values ('min_build', 2026111708)
on conflict (key) do update set value = greatest(public.rb_config.value, excluded.value);
