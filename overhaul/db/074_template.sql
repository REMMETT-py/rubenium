-- Rubenium 8.0, server part 1: security. Made by overhaul/db/make_074.py (do not edit the .sql by hand: edit
-- overhaul/db/074_template.sql or overhaul/golf/sim.sql and run the script again).
-- One transaction, safe to run twice. Undo: 074_down.sql. Nothing players own is changed; no coins, items, hours,
-- streaks or levels are touched. Old apps keep working (every rb_* function keeps its name, arguments and answer),
-- except solo Mini Golf on apps older than 8.0, which asks for the update (see DECISIONS.md, 8.0).
begin;

-- ===================================================================================== golf: the server rolls the ball
-- The hole layouts (1-60, and 101-160 = the same hole mirrored), exactly as in the app.
@@SIM@@

insert into public.rb_golf_hole_defs (id, name, tee, cup, rects, circles, sand, ice, water, boost) values
@@HOLES@@
on conflict (id) do update set name = excluded.name, tee = excluded.tee, cup = excluded.cup, rects = excluded.rects,
    circles = excluded.circles, sand = excluded.sand, ice = excluded.ice, water = excluded.water, boost = excluded.boost;

-- One shot from where the server last saw the ball (null = the tee). The app's own start is used when it is the
-- same spot (it keeps more decimals than the server stores), so both roll exactly the same shot.
create or replace function public.rb_golf_roll(hid integer, pos jsonb, x0 float8, y0 float8, ang float8, pw float8,
                                               out sx float8, out sy float8, out ex float8, out ey float8, out holed boolean)
language plpgsql stable security definer set search_path = '' as $$
declare h public.rb_golf_hole_defs%rowtype; s record;
begin
    select * into h from public.rb_golf_hole_defs where id = hid;
    if not found then raise exception 'rb_bad_choice'; end if;
    if ang is null or pw is null or ang <> ang or pw <> pw or abs(ang) > 100 or pw < 0 or pw > 1 then
        raise exception 'rb_bad_choice';
    end if;
    if pos is null or jsonb_typeof(pos) <> 'array' then
        sx := h.tee[1]; sy := h.tee[2];
    else
        sx := (pos ->> 0)::float8; sy := (pos ->> 1)::float8;
    end if;
    if x0 is not null and y0 is not null and abs(x0 - sx) <= 0.0006 and abs(y0 - sy) <= 0.0006 then
        sx := x0; sy := y0;
    end if;
    select * into s from public.rb_golf_sim(hid, sx, sy, ang, pw);
    ex := s.ex; ey := s.ey; holed := s.holed;
end $$;
revoke all on function public.rb_golf_roll(integer, jsonb, float8, float8, float8, float8) from public, anon, authenticated;

-- 1 v 1: same arguments and answer as before; x, y and holed sent by the app are no longer believed.
create or replace function public.rb_golf_shot(gid uuid, n integer, x0 double precision, y0 double precision,
                                               ang double precision, pow double precision, x double precision,
                                               y double precision, holed boolean)
returns json language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); g public.rb_golf%rowtype; side text; done boolean; s integer; r record;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_need_feature('golf');
    perform public.rb_golf_tick(gid);
    select * into g from public.rb_golf where id = gid for update;
    if not found or (g.a <> me and g.b <> me) then raise exception 'rb_duel_gone'; end if;
    if n < g.seq then return public.rb_golf_state(gid); end if;           -- already counted (sent twice)
    if g.state <> 'live' or g.turn <> me or n <> g.seq then raise exception 'rb_not_your_turn'; end if;
    side := case when me = g.a then 'a' else 'b' end;
    select * into r from public.rb_golf_roll(g.holes[g.hole], case when side = 'a' then g.pa else g.pb end,
                                             x0, y0, ang, pow);
    s := (case when side = 'a' then g.a_strokes else g.b_strokes end)[g.hole] + 1;
    done := r.holed or s >= 6;
    if side = 'a' then
        update public.rb_golf set a_strokes[hole] = s, a_in = done, a_miss = 0,
               pa = jsonb_build_array(round(r.ex::numeric, 4), round(r.ey::numeric, 4)), seq = seq + 1 where id = g.id;
    else
        update public.rb_golf set b_strokes[hole] = s, b_in = done, b_miss = 0,
               pb = jsonb_build_array(round(r.ex::numeric, 4), round(r.ey::numeric, 4)), seq = seq + 1 where id = g.id;
    end if;
    update public.rb_golf set shots = (select coalesce(jsonb_agg(v), '[]'::jsonb) from (
               select v from jsonb_array_elements(shots) v order by (v ->> 'n')::int desc limit 11) t)
               || jsonb_build_array(jsonb_build_object('n', g.seq, 'by', side, 'hole', g.hole,
                    'x0', r.sx, 'y0', r.sy, 'ang', ang, 'pow', pow,
                    'x', round(r.ex::numeric, 4), 'y', round(r.ey::numeric, 4), 'in', r.holed))
     where id = g.id;
    perform public.rb_golf_next(g.id);
    return public.rb_golf_state(gid);
end $$;

-- Matches of 2 to 4 players: the same.
create or replace function public.rb_party_shot(pid uuid, n integer, x0 double precision, y0 double precision,
                                                ang double precision, pow double precision, x double precision,
                                                y double precision, holed boolean)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); g public.rb_golf_parties%rowtype; s public.rb_golf_party_seats%rowtype; k integer;
        nxt integer; r record; fin boolean;
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
    if now() - s.last_at < interval '700 milliseconds' then raise exception 'rb_too_fast'; end if;
    select * into r from public.rb_golf_roll(g.holes[g.hole], s.pos, x0, y0, ang, pow);
    k := s.strokes[g.hole] + 1;
    fin := r.holed or k >= 6;
    update public.rb_golf_party_seats
       set strokes[g.hole] = k, seq = s.seq + 1, last_at = now(), holed = fin,
           pos = case when fin then null else jsonb_build_array(round(r.ex::numeric, 4), round(r.ey::numeric, 4)) end,
           shot = jsonb_build_object('n', s.seq, 'hole', g.hole, 'x0', r.sx, 'y0', r.sy, 'ang', ang, 'pow', pow,
                                     'x', round(r.ex::numeric, 4), 'y', round(r.ey::numeric, 4)),
           aim = null
     where party = pid and seat = s.seat;
    nxt := public.rb_party_next(pid, s.seat);
    update public.rb_golf_parties set turn = coalesce(nxt, turn), turn_at = now() + interval '3 seconds' where id = pid;
    perform public.rb_party_tick(pid);
    return public.rb_party_json(pid, me);
end $$;

-- Solo: the 8.0 app sends the shot itself (where from, angle, power); the server rolls it.
create or replace function public.rb_golf_solo_shot(gid uuid, n integer, x0 double precision, y0 double precision,
                                                    ang double precision, pow double precision, x double precision,
                                                    y double precision, holed boolean)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); g public.rb_golf_solo%rowtype; s integer; base integer := 0; pay integer := 0; i integer;
        r record;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_need_feature('golf');
    select * into g from public.rb_golf_solo where id = gid and owner = me for update;
    if not found then raise exception 'rb_duel_gone'; end if;
    if n < g.seq or g.state <> 'live' then return public.rb_golf_solo_json(g); end if;
    if n <> g.seq then raise exception 'rb_not_your_turn'; end if;
    if now() - g.last_at < interval '700 milliseconds' then raise exception 'rb_too_fast'; end if;
    select * into r from public.rb_golf_roll(g.holes[g.hole], g.pos, x0, y0, ang, pow);
    s := g.strokes[g.hole] + 1;
    g.strokes[g.hole] := s;
    g.seq := g.seq + 1;
    g.last_at := now();
    if r.holed or s >= 6 then
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
        g.pos := jsonb_build_array(round(r.ex::numeric, 4), round(r.ey::numeric, 4));
    end if;
    update public.rb_golf_solo set strokes = g.strokes, seq = g.seq, last_at = g.last_at, state = g.state, hole = g.hole,
           pos = g.pos, paid = g.paid, done_at = g.done_at where id = g.id;
    return public.rb_golf_solo_json(g);
end $$;
revoke all on function public.rb_golf_solo_shot(uuid, integer, double precision, double precision, double precision,
                                                double precision, double precision, double precision, boolean) from public, anon;
grant execute on function public.rb_golf_solo_shot(uuid, integer, double precision, double precision, double precision,
                                                   double precision, double precision, double precision, boolean) to authenticated;

-- The old solo call (where the ball stopped and whether it went in, from the app) cannot be checked: it asks for
-- the update, which every app since 4.x shows as "Update Rubenium to keep playing online".
create or replace function public.rb_golf_solo_shot(gid uuid, n integer, x double precision, y double precision,
                                                    holed boolean)
returns jsonb language plpgsql security definer set search_path = '' as $$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    raise exception 'rb_update_needed';
end $$;

-- ===================================================================================== request ids (resent calls)
-- rb_remember keeps the first 64 characters of a request id: look it up the same way, so a resend of a long id
-- gets the first answer instead of playing again.
create or replace function public.rb_done(who uuid, r text)
returns jsonb language sql security definer set search_path = '' as $$
    select result from public.rb_requests where owner = who and req = left(r, 64) $$;

-- ===================================================================================== password help
-- Before: 300 asks a day for everyone together, so anyone could use them up. Now: 3 a day per PC and per name, and
-- the shared limit only counts asks for names that do not exist (so they cannot crowd out real players).
create or replace function public.rb_reset_ask(name text, pc text, msg text)
returns uuid language plpgsql security definer set search_path = '' as $$
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
end $$;

-- ===================================================================================== admin: a second step
-- An admin can set a second code (at least 6 characters, kept as a bcrypt hash). Once it is set, every admin
-- action needs it to have been typed in the last 30 minutes, in this login. 5 wrong codes lock it for 15 minutes.
-- admin_step_all = 1 (rb_config) also refuses admins who have not set one yet: turn it on once 8.0 is out.
create table if not exists public.rb_admin_step (
    owner uuid primary key references public.profiles(id) on delete cascade,
    code_hash text not null,
    fails integer not null default 0,
    locked_until timestamptz,
    ok_until timestamptz,
    ok_session text,
    set_at timestamptz not null default now());
alter table public.rb_admin_step enable row level security;
revoke all on public.rb_admin_step from public, anon, authenticated;
insert into public.rb_config (key, value) values ('admin_step_all', 0) on conflict (key) do nothing;

create or replace function public.rb_admin_step_session() returns text
language sql stable security definer set search_path = '' as $$
    select coalesce(auth.jwt() ->> 'session_id', '') $$;
revoke all on function public.rb_admin_step_session() from public, anon, authenticated;

create or replace function public.rb_need_admin()
returns uuid language plpgsql stable security definer set search_path = '' as $$
declare st public.rb_admin_step%rowtype;
begin
    if not coalesce((select admin from public.profiles where id = auth.uid()), false) then
        raise exception 'rb_not_admin';
    end if;
    select * into st from public.rb_admin_step where owner = auth.uid();
    if found then
        if st.ok_until is null or st.ok_until < now()
           or coalesce(st.ok_session, '') <> public.rb_admin_step_session() then
            raise exception 'rb_admin_step';
        end if;
    elsif coalesce(public.rb_cfg('admin_step_all'), 0) > 0 then
        raise exception 'rb_admin_step';
    end if;
    return auth.uid();
end $$;

create or replace function public.rb_admin_step_status() returns json
language plpgsql stable security definer set search_path = '' as $$
declare st public.rb_admin_step%rowtype;
begin
    if not coalesce((select admin from public.profiles where id = auth.uid()), false) then
        raise exception 'rb_not_admin';
    end if;
    select * into st from public.rb_admin_step where owner = auth.uid();
    return json_build_object('set', found, 'required', found or coalesce(public.rb_cfg('admin_step_all'), 0) > 0,
        'ok', found and st.ok_until > now() and coalesce(st.ok_session, '') = public.rb_admin_step_session(),
        'ok_until', st.ok_until, 'locked_until', case when st.locked_until > now() then st.locked_until end);
end $$;

create or replace function public.rb_admin_step_check(code text) returns json
language plpgsql security definer set search_path = '' as $$
declare st public.rb_admin_step%rowtype;
begin
    if not coalesce((select admin from public.profiles where id = auth.uid()), false) then
        raise exception 'rb_not_admin';
    end if;
    select * into st from public.rb_admin_step where owner = auth.uid() for update;
    if not found then raise exception 'rb_admin_step_unset'; end if;
    if st.locked_until > now() then raise exception 'rb_slow_down'; end if;
    if extensions.crypt(coalesce(code, ''), st.code_hash) <> st.code_hash then
        update public.rb_admin_step
           set fails = case when st.fails + 1 >= 5 then 0 else st.fails + 1 end,
               locked_until = case when st.fails + 1 >= 5 then now() + interval '15 minutes' else locked_until end
         where owner = st.owner;
        return json_build_object('ok', false, 'left', greatest(0, 4 - st.fails));
    end if;
    update public.rb_admin_step set fails = 0, locked_until = null, ok_until = now() + interval '30 minutes',
           ok_session = public.rb_admin_step_session() where owner = st.owner;
    return json_build_object('ok', true, 'ok_until', now() + interval '30 minutes');
end $$;

create or replace function public.rb_admin_step_set(old_code text, new_code text) returns json
language plpgsql security definer set search_path = '' as $$
declare st public.rb_admin_step%rowtype;
begin
    if not coalesce((select admin from public.profiles where id = auth.uid()), false) then
        raise exception 'rb_not_admin';
    end if;
    if length(coalesce(new_code, '')) < 6 or length(new_code) > 72 then raise exception 'rb_bad_choice'; end if;
    select * into st from public.rb_admin_step where owner = auth.uid() for update;
    if found then
        if st.locked_until > now() then raise exception 'rb_slow_down'; end if;
        if extensions.crypt(coalesce(old_code, ''), st.code_hash) <> st.code_hash then
            update public.rb_admin_step
               set fails = case when st.fails + 1 >= 5 then 0 else st.fails + 1 end,
                   locked_until = case when st.fails + 1 >= 5 then now() + interval '15 minutes' else locked_until end
             where owner = st.owner;
            return json_build_object('ok', false, 'left', greatest(0, 4 - st.fails));
        end if;
    end if;
    insert into public.rb_admin_step (owner, code_hash, ok_until, ok_session)
        values (auth.uid(), extensions.crypt(new_code, extensions.gen_salt('bf', 10)), now() + interval '30 minutes',
                public.rb_admin_step_session())
    on conflict (owner) do update set code_hash = excluded.code_hash, fails = 0, locked_until = null,
        ok_until = excluded.ok_until, ok_session = excluded.ok_session, set_at = now();
    return json_build_object('ok', true);
end $$;
revoke all on function public.rb_admin_step_status(), public.rb_admin_step_check(text),
                       public.rb_admin_step_set(text, text) from public, anon;
grant execute on function public.rb_admin_step_status(), public.rb_admin_step_check(text),
                          public.rb_admin_step_set(text, text) to authenticated;

-- ===================================================================================== who may call and write what
-- What the API roles may do before this migration is kept (rb_bak74_grants), so 074_down.sql can put it back.
create table if not exists public.rb_bak74_grants (kind text, obj text, role text, priv text);
alter table public.rb_bak74_grants enable row level security;
revoke all on public.rb_bak74_grants from public, anon, authenticated;
do $g$
declare f record; t record;
begin
    if not exists (select 1 from public.rb_bak74_grants) then          -- the first run only
        insert into public.rb_bak74_grants
        select 'function', p.oid::regprocedure::text, r.role, 'EXECUTE'
          from pg_proc p cross join (values ('public'), ('anon'), ('authenticated'), ('service_role')) r(role)
         where p.pronamespace = 'public'::regnamespace and p.prokind = 'f'
           and case when r.role = 'public' then exists (select 1 from aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
                                                         where a.grantee = 0 and a.privilege_type = 'EXECUTE')
                    else has_function_privilege(r.role, p.oid, 'EXECUTE') end;
        insert into public.rb_bak74_grants
        select 'table', format('%I.%I', table_schema, table_name), grantee, privilege_type
          from information_schema.role_table_grants
         where table_schema = 'public' and grantee in ('anon', 'authenticated');
    end if;
    -- Functions: players (authenticated) and the server (service_role) keep exactly what they could call;
    -- without a login only the sign-in page's calls are left.
    for f in select p.oid::regprocedure::text sig, has_function_privilege('authenticated', p.oid, 'EXECUTE') a,
                    has_function_privilege('service_role', p.oid, 'EXECUTE') s
               from pg_proc p where p.pronamespace = 'public'::regnamespace and p.prokind = 'f' loop
        if f.a then execute format('grant execute on function %s to authenticated', f.sig); end if;
        if f.s then execute format('grant execute on function %s to service_role', f.sig); end if;
        execute format('revoke execute on function %s from public, anon', f.sig);
    end loop;
    for f in select p.oid::regprocedure::text sig from pg_proc p
              where p.pronamespace = 'public'::regnamespace and p.prokind = 'f'
                and p.proname in ('rb_username_free', 'rb_device_free', 'rb_login_for', 'rb_reset_ask', 'rb_reset_status',
                                  'rb_swaps_list') loop
        execute format('grant execute on function %s to anon', f.sig);
    end loop;
    -- Tables: reading stays as it was (row level security decides what each player sees); writing only ever
    -- happens through the rb_* functions, so the API roles lose insert, update, delete and the rest.
    for t in select format('%I.%I', schemaname, tablename) tn from pg_tables where schemaname = 'public' loop
        execute format('revoke insert, update, delete, truncate, references, trigger on %s from anon, authenticated', t.tn);
    end loop;
end $g$;
-- New functions and tables made later get the same rules.
alter default privileges in schema public revoke execute on functions from public;
alter default privileges in schema public revoke execute on functions from anon;
alter default privileges in schema public grant execute on functions to authenticated, service_role;
alter default privileges in schema public revoke insert, update, delete, truncate, references, trigger on tables from anon, authenticated;

-- Two backup tables from 6.3 had no row level security.
do $b$
begin
    if to_regclass('public.rb_bak63_cases') is not null then
        execute 'alter table public.rb_bak63_cases enable row level security';
        execute 'revoke all on public.rb_bak63_cases from anon, authenticated';
    end if;
    if to_regclass('public.rb_bak63_case_stock') is not null then
        execute 'alter table public.rb_bak63_case_stock enable row level security';
        execute 'revoke all on public.rb_bak63_case_stock from anon, authenticated';
    end if;
end $b$;

-- Swaps: the app saves each swap under its id and file name, so both must be plain names (no folders).
do $s$
begin
    if not exists (select 1 from pg_constraint where conname = 'rb_swaps_safe_names') then
        alter table public.rb_swaps add constraint rb_swaps_safe_names
            check (id ~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$' and file ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$'
                   and file !~ '\.\.' and lower(file) ~ '\.(upk|bnk|tfc|pck|wem)$');
    end if;
end $s$;

-- The new tables are read only through functions.
revoke all on public.rb_golf_hole_defs, public.rb_admin_step, public.rb_bak74_grants from anon, authenticated;

commit;
