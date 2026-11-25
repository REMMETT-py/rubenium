-- Test helpers, loaded into every test database (never into the real server).
create schema if not exists t;
grant usage on schema t to anon, authenticated;

-- A new player made the way the app signs up (auth.users row -> rb_new_user trigger), on the current build.
create or replace function t.player(name text, coins bigint default null, keys integer default null) returns uuid
language plpgsql security definer set search_path = '' as $$
declare uid uuid := gen_random_uuid();
begin
    insert into auth.users (id, email, raw_user_meta_data)
        values (uid, lower(name) || '@users.rubenium.app',
                jsonb_build_object('username', name, 'device', md5(name || clock_timestamp()::text)));
    update public.profiles set build = public.rb_cfg('min_build')::bigint, minutes = 6000,
           coins = coalesce(player.coins, profiles.coins), keys = coalesce(player.keys, profiles.keys)
     where profiles.id = uid;
    return uid;
end $$;

-- Act as a player (or anon with null) for the rest of the transaction, as PostgREST does.
create or replace function t.act(who uuid) returns void language plpgsql as $$
begin
    perform set_config('request.jwt.claims', coalesce(jsonb_build_object('sub', who, 'role', 'authenticated')::text, '{"role":"anon"}'), true);
    perform set_config('role', case when who is null then 'anon' else 'authenticated' end, true);
end $$;
grant execute on function t.act(uuid) to anon, authenticated;

create or replace function t.coins(who uuid) returns bigint language sql security definer set search_path = '' as
$$ select coins from public.profiles where id = who $$;
grant execute on function t.coins(uuid) to anon, authenticated;

-- Runs a statement as the current role and returns the error text ('' when it worked).
create or replace function t.try(stmt text) returns text language plpgsql as $$
begin
    execute stmt;
    return '';
exception when others then
    return sqlerrm;
end $$;
grant execute on function t.try(text) to anon, authenticated;

-- Rows a query returns as the current role; 0 when the role may not read the table at all.
create or replace function t.rows(q text) returns bigint language plpgsql as $$
declare n bigint;
begin
    execute 'select count(*) from (' || q || ') x' into n;
    return n;
exception when insufficient_privilege then
    return 0;
end $$;
grant execute on function t.rows(text) to anon, authenticated;
