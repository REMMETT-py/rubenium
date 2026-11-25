-- Minimal stand-in for what a Supabase project provides before any migration runs.
do $$ begin
  if not exists (select 1 from pg_roles where rolname='anon') then
    create role anon nologin noinherit; create role authenticated nologin noinherit;
    create role service_role nologin noinherit bypassrls; create role authenticator login noinherit;
    grant anon, authenticated, service_role to authenticator; create role supabase_storage_admin nologin;
  end if; end $$;
create schema extensions;
create extension pgcrypto with schema extensions;
create extension "uuid-ossp" with schema extensions;
create schema auth;
create table auth.users (
  instance_id uuid, id uuid primary key default gen_random_uuid(), aud text, role text, email text unique,
  encrypted_password text, email_confirmed_at timestamptz, raw_app_meta_data jsonb default '{}', raw_user_meta_data jsonb default '{}',
  created_at timestamptz default now(), updated_at timestamptz default now(), last_sign_in_at timestamptz, is_anonymous boolean default false);
create table auth.sessions (id uuid primary key default gen_random_uuid(), user_id uuid references auth.users(id) on delete cascade, created_at timestamptz default now());
create table auth.refresh_tokens (id bigserial primary key, token text, user_id text, session_id uuid, revoked boolean, created_at timestamptz default now());
create function auth.uid() returns uuid language sql stable as $$
  select nullif(coalesce(current_setting('request.jwt.claim.sub', true), (nullif(current_setting('request.jwt.claims', true),'')::jsonb ->> 'sub')), '')::uuid $$;
create function auth.role() returns text language sql stable as $$
  select coalesce(current_setting('request.jwt.claim.role', true), (nullif(current_setting('request.jwt.claims', true),'')::jsonb ->> 'role')) $$;
create function auth.jwt() returns jsonb language sql stable as $$ select coalesce(nullif(current_setting('request.jwt.claims', true),'')::jsonb, '{}'::jsonb) $$;
grant usage on schema auth to anon, authenticated, service_role;
grant execute on all functions in schema auth to anon, authenticated, service_role;
create schema storage;
create table storage.buckets (id text primary key, name text unique, owner uuid, public boolean default false, created_at timestamptz default now(), updated_at timestamptz default now(), file_size_limit bigint, allowed_mime_types text[]);
create table storage.objects (id uuid primary key default gen_random_uuid(), bucket_id text references storage.buckets(id), name text, owner uuid, created_at timestamptz default now(), updated_at timestamptz default now(), last_accessed_at timestamptz, metadata jsonb, path_tokens text[]);
alter table storage.objects enable row level security;
create function storage.foldername(name text) returns text[] language sql immutable as $$ select (string_to_array(name, '/'))[1:array_length(string_to_array(name,'/'),1)-1] $$;
create function storage.filename(name text) returns text language sql immutable as $$ select (string_to_array(name, '/'))[array_length(string_to_array(name,'/'),1)] $$;
create function storage.extension(name text) returns text language sql immutable as $$ select reverse(split_part(reverse(name), '.', 1)) $$;
grant usage on schema storage to anon, authenticated, service_role;
grant all on storage.objects, storage.buckets to anon, authenticated, service_role;
-- Supabase's defaults for the public schema: every new table, sequence and function is reachable by the API roles
grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
