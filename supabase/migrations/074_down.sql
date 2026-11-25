-- Undoes 074_v80_security.sql: the functions as they were, the grants as they were (kept in rb_bak74_grants).
-- One transaction, safe to run twice. Made by overhaul/db/make_074.py.
begin;
CREATE OR REPLACE FUNCTION public.rb_golf_shot(gid uuid, n integer, x0 double precision, y0 double precision, ang double precision, pow double precision, x double precision, y double precision, holed boolean)
 RETURNS json
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare me uuid := auth.uid(); g public.rb_golf%rowtype; side text; done boolean; s integer;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_need_feature('golf');
    perform public.rb_golf_tick(gid);
    select * into g from public.rb_golf where id = gid for update;
    if not found or (g.a <> me and g.b <> me) then raise exception 'rb_duel_gone'; end if;
    if n < g.seq then return public.rb_golf_state(gid); end if;           -- already counted (sent twice)
    if g.state <> 'live' or g.turn <> me or n <> g.seq then raise exception 'rb_not_your_turn'; end if;
    if pow is null or pow < 0 or pow > 1 or x is null or y is null or x not between 0 and 1 or y not between 0 and 0.62
       or x0 not between 0 and 1 or y0 not between 0 and 0.62 then raise exception 'rb_bad_choice'; end if;
    side := case when me = g.a then 'a' else 'b' end;
    s := (case when side = 'a' then g.a_strokes else g.b_strokes end)[g.hole] + 1;
    done := coalesce(holed, false) or s >= 6;
    if side = 'a' then
        update public.rb_golf set a_strokes[hole] = s, a_in = done, a_miss = 0, pa = jsonb_build_array(round(x::numeric, 4), round(y::numeric, 4)),
               seq = seq + 1 where id = g.id;
    else
        update public.rb_golf set b_strokes[hole] = s, b_in = done, b_miss = 0, pb = jsonb_build_array(round(x::numeric, 4), round(y::numeric, 4)),
               seq = seq + 1 where id = g.id;
    end if;
    update public.rb_golf set shots = (select coalesce(jsonb_agg(v), '[]'::jsonb) from (
               select v from jsonb_array_elements(shots) v order by (v ->> 'n')::int desc limit 11) t)
               || jsonb_build_array(jsonb_build_object('n', g.seq, 'by', side, 'hole', g.hole,
                    'x0', round(x0::numeric, 4), 'y0', round(y0::numeric, 4), 'ang', round(ang::numeric, 5),
                    'pow', round(pow::numeric, 4), 'x', round(x::numeric, 4), 'y', round(y::numeric, 4), 'in', coalesce(holed, false)))
     where id = g.id;
    perform public.rb_golf_next(g.id);
    return public.rb_golf_state(gid);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_party_shot(pid uuid, n integer, x0 double precision, y0 double precision, ang double precision, pow double precision, x double precision, y double precision, holed boolean)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare me uuid := auth.uid(); g public.rb_golf_parties%rowtype; s public.rb_golf_party_seats%rowtype; k integer; nxt integer;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_party_tick(pid);
    select * into g from public.rb_golf_parties where id = pid for update;
    if not found or g.state <> 'live' then raise exception 'rb_duel_gone'; end if;
    select * into s from public.rb_golf_party_seats where party = pid and owner = me for update;
    if not found or s.gone then raise exception 'rb_duel_gone'; end if;
    if n < s.seq or s.holed then return public.rb_party_json(pid, me); end if;
    if g.turn is distinct from s.seat then raise exception 'rb_not_your_turn'; end if;
    if n <> s.seq then raise exception 'rb_not_your_turn'; end if;
    if x is null or y is null or x not between 0 and 1 or y not between 0 and 0.62 then raise exception 'rb_bad_choice'; end if;
    if now() - s.last_at < interval '700 milliseconds' then raise exception 'rb_too_fast'; end if;
    k := s.strokes[g.hole] + 1;
    update public.rb_golf_party_seats
       set strokes[g.hole] = k, seq = s.seq + 1, last_at = now(),
           holed = coalesce(rb_party_shot.holed, false) or k >= 6,
           pos = case when coalesce(rb_party_shot.holed, false) or k >= 6 then null else jsonb_build_array(round(x::numeric, 4), round(y::numeric, 4)) end,
           shot = jsonb_build_object('n', s.seq, 'hole', g.hole, 'x0', x0, 'y0', y0, 'ang', ang, 'pow', pow, 'x', x, 'y', y),
           aim = null
     where party = pid and seat = s.seat;
    nxt := public.rb_party_next(pid, s.seat);
    update public.rb_golf_parties set turn = coalesce(nxt, turn), turn_at = now() + interval '3 seconds' where id = pid;
    perform public.rb_party_tick(pid);
    return public.rb_party_json(pid, me);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_golf_solo_shot(gid uuid, n integer, x double precision, y double precision, holed boolean)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare me uuid := auth.uid(); g public.rb_golf_solo%rowtype; s integer; base integer := 0; pay integer := 0; i integer;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_need_feature('golf');
    select * into g from public.rb_golf_solo where id = gid and owner = me for update;
    if not found then raise exception 'rb_duel_gone'; end if;
    if n < g.seq or g.state <> 'live' then return public.rb_golf_solo_json(g); end if;
    if n <> g.seq then raise exception 'rb_not_your_turn'; end if;
    if x is null or y is null or x not between 0 and 1 or y not between 0 and 0.62 then raise exception 'rb_bad_choice'; end if;
    if now() - g.last_at < interval '700 milliseconds' then raise exception 'rb_too_fast'; end if;
    s := g.strokes[g.hole] + 1;
    g.strokes[g.hole] := s;
    g.seq := g.seq + 1;
    g.last_at := now();
    if coalesce(holed, false) or s >= 6 then
        if g.hole >= array_length(g.holes, 1) then
            g.state := 'done';
            g.done_at := now();
            g.pos := null;
            if now() - g.at >= interval '15 seconds' then
                for i in 1..array_length(g.strokes, 1) loop
                    base := base + public.rb_golf_solo_pay(g.strokes[i]);
                end loop;
            end if;
            pay := public.rb_game_pay(me, 'golf_solo', base);
            if pay > 0 then perform public.rb_pay(me, pay, 0, 'minigame', 'golf_solo'); end if;
            g.paid := pay;
            insert into public.rb_rounds (owner, game, bet, secret, open, paid)
                values (me, 'golf_solo', 0, jsonb_build_object('strokes', g.strokes, 'solo', g.id), false, pay);
        else
            g.hole := g.hole + 1;
            g.pos := null;
        end if;
    else
        g.pos := jsonb_build_array(round(x::numeric, 4), round(y::numeric, 4));
    end if;
    update public.rb_golf_solo set strokes = g.strokes, seq = g.seq, last_at = g.last_at, state = g.state, hole = g.hole,
           pos = g.pos, paid = g.paid, done_at = g.done_at where id = g.id;
    return public.rb_golf_solo_json(g);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_done(who uuid, r text)
 RETURNS jsonb
 LANGUAGE sql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select result from public.rb_requests where owner = who and req = r $function$;

CREATE OR REPLACE FUNCTION public.rb_reset_ask(name text, pc text, msg text)
 RETURNS uuid
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare rid uuid; u uuid;
begin
    if coalesce(pc, '') !~ '^[a-f0-9]{32,64}$' then raise exception 'rb_update_needed'; end if;
    if (select count(*) from public.rb_resets r where r.device = pc and r.at > now() - interval '1 day') >= 3
       or (select count(*) from public.rb_resets r where r.at > now() - interval '1 day') >= 300 then
        raise exception 'rb_slow_down';
    end if;
    select id into u from public.profiles where lower(username) = lower(btrim(coalesce(name, '')));
    insert into public.rb_resets (name, uid, device, msg)
        values (left(btrim(coalesce(name, '')), 20), u, pc, left(coalesce(msg, ''), 400)) returning id into rid;
    return rid;
end $function$;

CREATE OR REPLACE FUNCTION public.rb_need_admin()
 RETURNS uuid
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    if not coalesce((select admin from public.profiles where id = auth.uid()), false) then
        raise exception 'rb_not_admin';
    end if;
    return auth.uid();
end $function$;

drop function if exists public.rb_golf_solo_shot(uuid, integer, double precision, double precision, double precision,
                                                 double precision, double precision, double precision, boolean);
drop function if exists public.rb_golf_roll(integer, jsonb, float8, float8, float8, float8);
drop function if exists public.rb_golf_sim(integer, float8, float8, float8, float8);
drop table if exists public.rb_golf_hole_defs;
drop function if exists public.rb_admin_step_status();
drop function if exists public.rb_admin_step_check(text);
drop function if exists public.rb_admin_step_set(text, text);
drop function if exists public.rb_admin_step_session();
drop table if exists public.rb_admin_step;
delete from public.rb_config where key = 'admin_step_all';

alter default privileges in schema public grant execute on functions to anon;
alter default privileges in schema public grant insert, update, delete, truncate, references, trigger on tables to anon, authenticated;
do $g$
declare r record;
begin
    if to_regclass('public.rb_bak74_grants') is null then return; end if;
    for r in select * from public.rb_bak74_grants where kind = 'function' and role in ('public', 'anon')
               and to_regprocedure(obj) is not null loop
        execute format('grant execute on function %s to %s', r.obj, r.role);
    end loop;
    for r in select * from public.rb_bak74_grants where kind = 'table' and to_regclass(obj) is not null loop
        execute format('grant %s on %s to %I', r.priv, r.obj, r.role);
    end loop;
    if to_regclass('public.rb_bak63_cases') is not null then
        execute 'alter table public.rb_bak63_cases disable row level security';
    end if;
    if to_regclass('public.rb_bak63_case_stock') is not null then
        execute 'alter table public.rb_bak63_case_stock disable row level security';
    end if;
end $g$;
alter table public.rb_swaps drop constraint if exists rb_swaps_safe_names;
drop table if exists public.rb_bak74_grants;
commit;
