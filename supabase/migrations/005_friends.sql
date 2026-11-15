-- Rubenium 005: friends, profiles and play history. Safe to run more than once. Needs 003 and 004 first.
-- Run it in Supabase: SQL Editor > New query > paste > Run.

create table if not exists public.rb_friends (
    a uuid not null references public.profiles (id) on delete cascade,      -- who asked
    b uuid not null references public.profiles (id) on delete cascade,      -- who was asked
    ok boolean not null default false, at timestamptz not null default now(),
    primary key (a, b), check (a <> b));
create index if not exists rb_friends_b on public.rb_friends (b);
alter table public.rb_friends enable row level security;
revoke all on public.rb_friends from anon, authenticated;

create or replace function public.rb_is_friend(x uuid, y uuid) returns boolean
language sql stable security definer set search_path = '' as $$
    select exists (select 1 from public.rb_friends f where f.ok and ((f.a = x and f.b = y) or (f.a = y and f.b = x))) $$;

create or replace function public.rb_online(p public.profiles) returns boolean
language sql stable set search_path = '' as $$
    select p.last_beat is not null and now() - p.last_beat < interval '150 seconds' $$;

-- Ask someone to be friends (or accept, if they already asked you).
create or replace function public.rb_friend_add(name text) returns text
language plpgsql security definer set search_path = '' as $$
declare me public.profiles%rowtype; them uuid;
begin
    me := public.rb_lock_me();
    select id into them from public.profiles where lower(username) = lower(name);
    if them is null then raise exception 'rb_no_such_user'; end if;
    if them = me.id then raise exception 'rb_thats_you'; end if;
    if public.rb_is_friend(me.id, them) then return 'friends'; end if;
    if exists (select 1 from public.rb_friends where a = them and b = me.id) then
        update public.rb_friends set ok = true, at = now() where a = them and b = me.id;
        return 'friends';
    end if;
    if (select count(*) from public.rb_friends where a = me.id or b = me.id) >= 200 then
        raise exception 'rb_too_many';
    end if;
    insert into public.rb_friends (a, b) values (me.id, them) on conflict do nothing;
    return 'asked';
end $$;

-- Remove a friend, cancel what you asked, or decline what they asked.
create or replace function public.rb_friend_remove(name text) returns boolean
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); them uuid;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select id into them from public.profiles where lower(username) = lower(name);
    delete from public.rb_friends where (a = me and b = them) or (a = them and b = me);
    return true;
end $$;

-- My friends and requests, with who is online.
create or replace function public.rb_friends_list() returns json
language sql stable security definer set search_path = '' as $$
    select coalesce(json_agg(json_build_object(
               'username', p.username,
               'state', case when f.ok then 'friend' when f.a = auth.uid() then 'asked' else 'asks' end,
               'online', f.ok and public.rb_online(p),
               'seen', case when f.ok then p.last_beat end,
               'badges', case when f.ok then json_build_array(p.equip ->> 'badge1', p.equip ->> 'badge2', p.equip ->> 'badge3') end)
               order by f.ok desc, public.rb_online(p) desc, lower(p.username)), '[]'::json)
      from public.rb_friends f
      join public.profiles p on p.id = case when f.a = auth.uid() then f.b else f.a end
     where f.a = auth.uid() or f.b = auth.uid() $$;

-- Anyone's public profile: name, time played, what they wear, and their badges.
create or replace function public.rb_profile(name text) returns json
language plpgsql stable security definer set search_path = '' as $$
declare me uuid := auth.uid(); p public.profiles%rowtype; friend boolean;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into p from public.profiles where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    friend := public.rb_is_friend(me, p.id);
    return json_build_object(
        'username', p.username, 'minutes', p.minutes, 'since', p.created_at, 'equip', p.equip,
        'me', p.id = me, 'friend', friend,
        'state', (select case when f.ok then 'friend' when f.a = me then 'asked' else 'asks' end
                    from public.rb_friends f where (f.a = me and f.b = p.id) or (f.a = p.id and f.b = me)),
        'online', (friend or p.id = me) and public.rb_online(p),
        'badges', coalesce((select json_agg(x.item order by x.value desc, x.item)
                              from (select distinct it.item, c.value from public.rb_items it
                                      join public.rb_catalog c on c.id = it.item
                                     where it.owner = p.id and c.kind = 'badge') x), '[]'::json),
        'items', (select count(*) from public.rb_items it where it.owner = p.id));
end $$;

-- Play history (casino, cases, spins): your own, or a friend's.
create or replace function public.rb_history(name text) returns json
language plpgsql stable security definer set search_path = '' as $$
declare me uuid := auth.uid(); who uuid;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select id into who from public.profiles where lower(username) = lower(coalesce(nullif(name, ''),
        (select username from public.profiles where id = me)));
    if who is null then raise exception 'rb_no_such_user'; end if;
    if who <> me and not public.rb_is_friend(me, who) then raise exception 'rb_friends_only'; end if;
    return json_build_object(
        'rows', coalesce((select json_agg(json_build_object('game', r.game, 'bet', r.bet, 'paid', r.paid,
                                   'item', r.secret ->> 'item', 'keys', r.secret ->> 'keys', 'at', r.at) order by r.at desc)
                            from (select * from public.rb_rounds where owner = who and not open
                                   order by at desc limit 60) r), '[]'::json),
        'bet', (select coalesce(sum(bet), 0) from public.rb_rounds where owner = who and not open and game not like 'case:%'),
        'won', (select coalesce(sum(paid), 0) from public.rb_rounds where owner = who and not open and game not like 'case:%'
                   and game not in ('daily', 'spin')),
        'best', (select coalesce(max(paid), 0) from public.rb_rounds where owner = who and not open
                    and game not like 'case:%' and game not in ('daily', 'spin')),
        'cases', (select count(*) from public.rb_rounds where owner = who and game like 'case:%'));
end $$;

do $$ declare f text; begin
    foreach f in array array['rb_is_friend(uuid, uuid)', 'rb_online(public.profiles)', 'rb_friend_add(text)',
        'rb_friend_remove(text)', 'rb_friends_list()', 'rb_profile(text)', 'rb_history(text)'] loop
        execute format('revoke all on function public.%s from public, anon, authenticated', f);
    end loop;
    foreach f in array array['rb_friend_add(text)', 'rb_friend_remove(text)', 'rb_friends_list()', 'rb_profile(text)',
        'rb_history(text)'] loop
        execute format('grant execute on function public.%s to authenticated', f);
    end loop;
end $$;
