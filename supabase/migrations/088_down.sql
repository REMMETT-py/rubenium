-- Undo of 088_v92_privacy.sql: rb_delete_account and rb_reset_ask go back as they were, the new functions, trigger
-- and consent table go, and rv_search is callable by everyone again (as before).
begin;
CREATE OR REPLACE FUNCTION public.rb_delete_account(confirm text)
 RETURNS boolean
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
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
end $function$

;
CREATE OR REPLACE FUNCTION public.rb_reset_ask(name text, pc text, msg text)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare rid uuid; u uuid; nm text := left(btrim(coalesce(name, '')), 20);
begin
    if coalesce(pc, '') !~ '^[a-f0-9]{32,64}$' then raise exception 'rb_update_needed'; end if;
    select id into u from public.profiles where lower(username) = lower(nm);
    if (select count(*) from public.rb_resets r where r.device = pc and r.at > now() - interval '1 day') >= 3
       or (select count(*) from public.rb_resets r where lower(r.name) = lower(nm) and r.at > now() - interval '1 day') >= 3
       or (u is null and (select count(*) from public.rb_resets r where r.uid is null and r.at > now() - interval '1 day') >= 300) then
        raise exception 'rb_slow_down';
    end if;
    insert into public.rb_resets (name, uid, device, msg) values (nm, u, pc, left(coalesce(msg, ''), 400)) returning id into rid;
    return rid;
end $function$

;
drop trigger if exists rb_consent_signup on auth.users;
drop function if exists public.rb_consent_signup();
drop function if exists public.rb_terms_state();
drop function if exists public.rb_accept_terms(numeric, boolean);
drop function if exists public.rb_my_data();
drop function if exists public.rb_forget(uuid, text);
drop table if exists public.rb_consent;
delete from public.rb_config where key in ('terms_version', 'min_age');
grant execute on function public.rv_search(text, text, integer, integer, integer) to public, authenticated;
commit;
