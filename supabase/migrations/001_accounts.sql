-- Rubenium 001: accounts, usernames and time played.
-- Safe to run more than once. Run it in Supabase: SQL Editor > New query > paste > Run.

create table if not exists public.profiles (
    id          uuid primary key references auth.users (id) on delete cascade,
    username    text not null check (username ~ '^[A-Za-z0-9]{3,10}$'),
    minutes     integer not null default 0 check (minutes >= 0),      -- time played, counted by the server only
    last_beat   timestamptz,
    beat_device text,
    created_at  timestamptz not null default now()
);
create unique index if not exists profiles_username_lower on public.profiles (lower(username));

alter table public.profiles enable row level security;
drop policy if exists "read own profile" on public.profiles;
create policy "read own profile" on public.profiles for select to authenticated using (id = (select auth.uid()));
revoke all on public.profiles from anon, authenticated;
grant select on public.profiles to authenticated;          -- no insert / update / delete from the app, ever

-- A profile is made by the server when an account is created. An account without a valid, free username
-- cannot be created at all.
create or replace function public.rb_new_user() returns trigger
language plpgsql security definer set search_path = '' as $$
declare
    name text := coalesce(new.raw_user_meta_data ->> 'username', '');
begin
    if name !~ '^[A-Za-z0-9]{3,10}$' then
        raise exception 'rb_bad_username';
    end if;
    if new.email is distinct from lower(name) || '@users.rubenium.app' then
        raise exception 'rb_bad_account';
    end if;
    if exists (select 1 from public.profiles p where lower(p.username) = lower(name)) then
        raise exception 'rb_username_taken';
    end if;
    insert into public.profiles (id, username) values (new.id, name);
    return new;
end $$;
drop trigger if exists rb_new_user on auth.users;
create trigger rb_new_user after insert on auth.users for each row execute function public.rb_new_user();

-- Is this username still free? (Used while typing on the Create Account screen.)
create or replace function public.rb_username_free(name text) returns boolean
language sql stable security definer set search_path = '' as $$
    select name ~ '^[A-Za-z0-9]{3,10}$'
       and not exists (select 1 from public.profiles p where lower(p.username) = lower(name));
$$;

-- The app calls this once a minute while it is open and in use. The server's own clock decides what counts:
-- at most one minute per minute, and only one PC per account earns at a time.
create or replace function public.rb_heartbeat(device text) returns json
language plpgsql security definer set search_path = '' as $$
declare
    me uuid := auth.uid();
    p  public.profiles%rowtype;
    credited boolean := false;
    elsewhere boolean := false;
begin
    if me is null then
        raise exception 'rb_not_logged_in';
    end if;
    select * into p from public.profiles where id = me for update;
    if not found then
        raise exception 'rb_no_profile';
    end if;
    device := left(coalesce(device, ''), 64);
    if p.last_beat is not null and p.beat_device is distinct from device
       and now() - p.last_beat < interval '150 seconds' then
        elsewhere := true;                                   -- another PC is earning right now
    elsif p.last_beat is null or now() - p.last_beat >= interval '55 seconds' then
        -- a minute counts only if the last beat was about a minute ago (not after a long pause)
        credited := p.last_beat is not null and now() - p.last_beat < interval '150 seconds';
        update public.profiles
           set minutes = minutes + (case when credited then 1 else 0 end), last_beat = now(), beat_device = device
         where id = me
         returning * into p;
    end if;
    return json_build_object('username', p.username, 'minutes', p.minutes, 'credited', credited,
                             'elsewhere', elsewhere);
end $$;

create or replace function public.rb_me() returns json
language sql stable security definer set search_path = '' as $$
    select json_build_object('username', p.username, 'minutes', p.minutes, 'created_at', p.created_at)
      from public.profiles p where p.id = auth.uid();
$$;

revoke all on function public.rb_new_user() from public, anon, authenticated;
revoke all on function public.rb_username_free(text) from public;
revoke all on function public.rb_heartbeat(text) from public, anon;
revoke all on function public.rb_me() from public, anon;
grant execute on function public.rb_username_free(text) to anon, authenticated;
grant execute on function public.rb_heartbeat(text) to authenticated;
grant execute on function public.rb_me() to authenticated;
