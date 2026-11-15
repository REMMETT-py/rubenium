-- Rubenium 002: an account can delete itself (asked for twice in the app: type the username, then hold).
-- Safe to run more than once. Run it in Supabase: SQL Editor > New query > paste > Run.

create or replace function public.rb_delete_account(confirm text) returns boolean
language plpgsql security definer set search_path = '' as $$
declare
    me uuid := auth.uid();
    name text;
begin
    if me is null then
        raise exception 'rb_not_logged_in';
    end if;
    select username into name from public.profiles where id = me;
    if name is null or confirm is distinct from name then
        raise exception 'rb_confirm_mismatch';            -- the username must be typed exactly
    end if;
    delete from auth.users where id = me;                 -- the profile (and later everything owned) goes with it
    return true;
end $$;

revoke all on function public.rb_delete_account(text) from public, anon;
grant execute on function public.rb_delete_account(text) to authenticated;
