-- Rubenium 9.2: Wave Rush multiplayer rooms, 2 to 4 players on the same course. Safe to run twice.
--
-- A host opens a room for 2, 3 or 4 players, free or for a bet that everyone pays to sit down. The run starts for
-- everyone 4 seconds after the room is full (or when the host starts it with at least 2). Every player sends where
-- they pressed and let go (rb_wroom_ping); everyone else rebuilds that run from the same course, so all the waves are
-- shown live. When a run ends the server checks it (rb_wave_sim, as for solo runs). The longest run wins the pot
-- (less the duel fee); equal best runs share it. A player who leaves a live room scores 0.
-- The old 1 v 1 Wave Rush duels stay for games already open; new games are rooms.
begin;

create table if not exists public.rb_wave_rooms (
    id uuid primary key default gen_random_uuid(),
    host uuid not null references public.profiles (id) on delete cascade,
    size integer not null check (size between 2 and 4),
    bet integer not null default 0,
    seed bigint not null,
    state text not null default 'open' check (state in ('open', 'live', 'done', 'cancelled')),
    why text,
    at timestamptz not null default now(),
    live_at timestamptz,
    done_at timestamptz);
create index if not exists rb_wave_rooms_state on public.rb_wave_rooms (state, at desc);
alter table public.rb_wave_rooms enable row level security;

create table if not exists public.rb_wave_seats (
    room uuid not null references public.rb_wave_rooms (id) on delete cascade,
    owner uuid not null references public.profiles (id) on delete cascade,
    seat integer not null check (seat between 0 and 3),
    run uuid,
    paid integer not null default 0,
    place integer,
    at timestamptz not null default now(),
    primary key (room, owner),
    unique (room, seat));
create index if not exists rb_wave_seats_owner on public.rb_wave_seats (owner);
alter table public.rb_wave_seats enable row level security;
revoke all on public.rb_wave_rooms, public.rb_wave_seats from anon, authenticated;

alter table public.rb_wave_runs add column if not exists room uuid;
create index if not exists rb_wave_runs_room on public.rb_wave_runs (room);

-- in an open or live room (or an old duel)
create or replace function public.rb_wroom_busy(who uuid) returns boolean
language sql stable security definer set search_path to '' as $$
    select public.rb_wave_busy(who)
        or exists (select 1 from public.rb_wave_seats s join public.rb_wave_rooms r on r.id = s.room
                    where s.owner = who and r.state in ('open', 'live')) $$;

-- the end: places, the pot
create or replace function public.rb_wroom_settle(rid uuid) returns void
language plpgsql security definer set search_path to '' as $$
declare r public.rb_wave_rooms%rowtype; best integer; winners uuid[]; pot integer; share integer; n integer; s record;
begin
    select * into r from public.rb_wave_rooms where id = rid for update;
    if not found or r.state <> 'live' then return; end if;
    update public.rb_wave_runs set state = 'done', done_at = now(), dist = 0 where room = rid and state = 'live';
    for s in select ws.owner, row_number() over (order by coalesce(wr.dist, 0) desc) k
               from public.rb_wave_seats ws left join public.rb_wave_runs wr on wr.id = ws.run where ws.room = rid loop
        update public.rb_wave_seats set place = s.k where room = rid and owner = s.owner;
    end loop;
    select max(coalesce(wr.dist, 0)) into best from public.rb_wave_seats ws left join public.rb_wave_runs wr on wr.id = ws.run
     where ws.room = rid;
    winners := array(select ws.owner from public.rb_wave_seats ws join public.rb_wave_runs wr on wr.id = ws.run
                      where ws.room = rid and wr.dist = best and best > 0);
    select count(*) into n from public.rb_wave_seats where room = rid;
    if r.bet > 0 then
        if cardinality(winners) = 0 then                           -- nobody ran: everyone gets their bet back
            for s in select owner from public.rb_wave_seats where room = rid loop
                perform public.rb_pay(s.owner, r.bet, 0, 'wave_back', rid::text);
                update public.rb_wave_seats set paid = r.bet where room = rid and owner = s.owner;
            end loop;
        else
            pot := floor(r.bet * n * (1 - coalesce(public.rb_cfg('golf_fee'), 0.05)))::int;
            share := pot / cardinality(winners);
            for s in select unnest(winners) as owner loop
                perform public.rb_pay(s.owner, share, 0, 'wave_win', rid::text);
                update public.rb_wave_seats set paid = share where room = rid and owner = s.owner;
            end loop;
        end if;
    end if;
    for s in select unnest(winners) as owner loop
        perform public.rb_xp_add(s.owner, 30, 'wave_room', rid::text);
    end loop;
    update public.rb_wave_rooms set state = 'done', done_at = now(),
           why = case when cardinality(winners) > 1 then 'tie' when cardinality(winners) = 0 then 'nobody' else 'distance' end
     where id = rid;
end $$;

-- everyone is sat down (or the host says go): the runs start in 4 seconds
create or replace function public.rb_wroom_go(rid uuid) returns void
language plpgsql security definer set search_path to '' as $$
declare r public.rb_wave_rooms%rowtype; s record; run_id uuid;
begin
    select * into r from public.rb_wave_rooms where id = rid for update;
    if not found or r.state <> 'open' then return; end if;
    for s in select owner from public.rb_wave_seats where room = rid order by seat loop
        insert into public.rb_wave_runs (owner, seed, room, started_at) values (s.owner, r.seed, rid, now() + interval '4 seconds')
            returning id into run_id;
        update public.rb_wave_seats set run = run_id where room = rid and owner = s.owner;
    end loop;
    update public.rb_wave_rooms set state = 'live', live_at = now() where id = rid;
end $$;

create or replace function public.rb_wroom_tick(rid uuid) returns void
language plpgsql security definer set search_path to '' as $$
declare r public.rb_wave_rooms%rowtype; s record;
begin
    select * into r from public.rb_wave_rooms where id = rid for update;
    if not found then return; end if;
    if r.state = 'open' and now() - r.at > make_interval(mins => coalesce(public.rb_cfg('lobby_min'), 5)::int) then
        update public.rb_wave_rooms set state = 'cancelled', why = 'expired', done_at = now() where id = rid;
        if r.bet > 0 then
            for s in select owner from public.rb_wave_seats where room = rid loop
                perform public.rb_pay(s.owner, r.bet, 0, 'wave_back', rid::text);
            end loop;
        end if;
    elsif r.state = 'live' and (now() - r.live_at > make_interval(mins => coalesce(public.rb_cfg('wave_duel_min'), 8)::int)
                                or not exists (select 1 from public.rb_wave_runs where room = rid and state = 'live')) then
        perform public.rb_wroom_settle(rid);
    end if;
end $$;

-- what a player sees of a room
create or replace function public.rb_wroom_json(rid uuid, me uuid) returns jsonb
language sql stable security definer set search_path to '' as $$
    select jsonb_build_object('id', r.id, 'state', r.state, 'size', r.size, 'bet', r.bet, 'seed', r.seed, 'why', r.why,
        'host', (select username from public.profiles where id = r.host), 'mine', r.host = me,
        'starts_in', case when r.live_at is not null then greatest(0, extract(epoch from (r.live_at + interval '4 seconds' - now())))::numeric(5, 1) end,
        'left', case when r.state = 'live' then greatest(0, ceil(extract(epoch from (r.live_at
                 + make_interval(mins => coalesce(public.rb_cfg('wave_duel_min'), 8)::int) - now()))))::int end,
        'players', coalesce((select jsonb_agg(jsonb_build_object('name', p.username, 'seat', s.seat, 'me', s.owner = me,
                        'run', case when s.owner = me then s.run end, 'x', wr.live_x, 'tg', wr.live_tg, 't', wr.live_t,
                        'done', wr.state = 'done', 'final', case when wr.state = 'done' then wr.ticks end, 'dist', wr.dist,
                        'place', s.place, 'paid', s.paid) order by s.seat)
                   from public.rb_wave_seats s join public.profiles p on p.id = s.owner
                   left join public.rb_wave_runs wr on wr.id = s.run where s.room = r.id), '[]'::jsonb))
      from public.rb_wave_rooms r where r.id = rid $$;

create or replace function public.rb_wroom_lobbies() returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); p public.profiles%rowtype; o record; cur uuid;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into p from public.profiles where id = me;
    for o in select id from public.rb_wave_rooms where state in ('open', 'live') loop
        perform public.rb_wroom_tick(o.id);
    end loop;
    select r.id into cur from public.rb_wave_seats s join public.rb_wave_rooms r on r.id = s.room
     where s.owner = me and r.state in ('open', 'live') order by r.at desc limit 1;
    return jsonb_build_object('cap', public.rb_golf_cap(p.coins), 'best', public.rb_wave_best(me),
        'mine', case when cur is not null then public.rb_wroom_json(cur, me) end,
        'rooms', coalesce((select jsonb_agg(jsonb_build_object('id', r.id, 'host', u.username, 'size', r.size, 'bet', r.bet,
                        'seated', (select count(*) from public.rb_wave_seats s where s.room = r.id),
                        'friend', public.rb_is_friend(me, r.host)) order by r.at)
                   from public.rb_wave_rooms r join public.profiles u on u.id = r.host
                  where r.state = 'open' and not u.banned), '[]'::jsonb));
end $$;

create or replace function public.rb_wroom_create(size integer, bet integer) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; rid uuid; old record;
begin
    perform public.rb_rate(auth.uid(), 'duel', 10);
    perform public.rb_need_feature('wave');
    p := public.rb_lock_me();
    for old in select s.room from public.rb_wave_seats s where s.owner = p.id loop perform public.rb_wroom_tick(old.room); end loop;
    if public.rb_wroom_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    if size is null or size not between 2 and 4 then raise exception 'rb_bad_choice'; end if;
    bet := coalesce(bet, 0);
    if bet <> 0 and (bet < 10 or bet % 10 <> 0 or bet > public.rb_golf_cap(p.coins)) then raise exception 'rb_bad_bet'; end if;
    insert into public.rb_wave_rooms (host, size, bet, seed) values (p.id, size, bet, floor(public.rb_rand() * 2147483647)::bigint)
        returning id into rid;
    if bet > 0 then perform public.rb_pay(p.id, -bet, 0, 'wave_bet', rid::text); end if;
    insert into public.rb_wave_seats (room, owner, seat) values (rid, p.id, 0);
    return public.rb_wroom_json(rid, p.id) || jsonb_build_object('coins', p.coins - bet);
end $$;

create or replace function public.rb_wroom_join(rid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; r public.rb_wave_rooms%rowtype; n integer; seat_ integer;
begin
    perform public.rb_rate(auth.uid(), 'duel', 10);
    perform public.rb_need_feature('wave');
    p := public.rb_lock_me();
    perform public.rb_wroom_tick(rid);
    select * into r from public.rb_wave_rooms where id = rid for update;
    if not found or r.state <> 'open' then raise exception 'rb_duel_gone'; end if;
    if exists (select 1 from public.rb_wave_seats where room = rid and owner = p.id) then raise exception 'rb_thats_you'; end if;
    if public.rb_wroom_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    select count(*) into n from public.rb_wave_seats where room = rid;
    if n >= r.size then raise exception 'rb_duel_gone'; end if;
    if p.coins < r.bet then raise exception 'rb_not_enough'; end if;
    if r.bet > 0 then perform public.rb_pay(p.id, -r.bet, 0, 'wave_bet', rid::text); end if;
    select min(k) into seat_ from generate_series(0, 3) k
     where not exists (select 1 from public.rb_wave_seats s where s.room = rid and s.seat = k);
    insert into public.rb_wave_seats (room, owner, seat) values (rid, p.id, seat_);
    perform public.rb_notice(r.host, 'wave_yes', jsonb_build_object('from', p.username, 'id', rid));
    if n + 1 >= r.size then perform public.rb_wroom_go(rid); end if;
    return public.rb_wroom_json(rid, p.id) || jsonb_build_object('coins', p.coins - r.bet);
end $$;

-- the host starts with who is there (2 or more)
create or replace function public.rb_wroom_start(rid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); r public.rb_wave_rooms%rowtype;
begin
    select * into r from public.rb_wave_rooms where id = rid and host = me;
    if not found or r.state <> 'open' then raise exception 'rb_duel_gone'; end if;
    if (select count(*) from public.rb_wave_seats where room = rid) < 2 then raise exception 'rb_need_players'; end if;
    perform public.rb_wroom_go(rid);
    return public.rb_wroom_json(rid, me);
end $$;

-- leave: before the start you get your bet back (the host leaving closes the room); during the run you score 0
create or replace function public.rb_wroom_leave(rid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); r public.rb_wave_rooms%rowtype; s record;
begin
    select * into r from public.rb_wave_rooms where id = rid for update;
    if not found or not exists (select 1 from public.rb_wave_seats where room = rid and owner = me) then raise exception 'rb_duel_gone'; end if;
    if r.state = 'open' then
        if r.host = me then
            update public.rb_wave_rooms set state = 'cancelled', why = 'closed', done_at = now() where id = rid;
            for s in select owner from public.rb_wave_seats where room = rid loop
                if r.bet > 0 then perform public.rb_pay(s.owner, r.bet, 0, 'wave_back', rid::text); end if;
            end loop;
        else
            delete from public.rb_wave_seats where room = rid and owner = me;
            if r.bet > 0 then perform public.rb_pay(me, r.bet, 0, 'wave_back', rid::text); end if;
        end if;
    elsif r.state = 'live' then
        update public.rb_wave_runs set state = 'done', dist = 0, done_at = now()
         where room = rid and owner = me and state = 'live';
        perform public.rb_wroom_tick(rid);
    end if;
    return jsonb_build_object('left', true);
end $$;

create or replace function public.rb_wroom_state(rid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_wroom_tick(rid);
    if not exists (select 1 from public.rb_wave_seats where room = rid and owner = me) then raise exception 'rb_duel_gone'; end if;
    return public.rb_wroom_json(rid, me);
end $$;

-- where my run is, while it runs (the same checks as the duels)
create or replace function public.rb_wroom_ping(run uuid, x integer, toggles integer[], t integer) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); r public.rb_wave_runs%rowtype; most integer;
begin
    select * into r from public.rb_wave_runs where id = run and owner = me;
    if not found or r.room is null then raise exception 'rb_duel_gone'; end if;
    if r.state = 'live' then
        most := floor(greatest(0, extract(epoch from now() - r.started_at)) * 60)::int + 120;     -- no run from the future
        if coalesce(array_length(toggles, 1), 0) <= 30000 and coalesce(t, 0) >= r.live_t then
            t := least(t, most);
            update public.rb_wave_runs set live_tg = coalesce((select array_agg(v order by v) from (select distinct v
                       from unnest(toggles) v where v > 0 and v <= t) z), '{}'), live_t = t where id = r.id;
        end if;
        update public.rb_wave_runs set live_x = greatest(live_x, least(coalesce(x, 0), most * 12 + 2000)) where id = r.id;
    end if;
    perform public.rb_wroom_tick(r.room);
    return public.rb_wroom_json(r.room, me);
end $$;

-- my run ended: the server plays it again to check it
create or replace function public.rb_wroom_finish(run uuid, toggles integer[], ticks integer) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); r public.rb_wave_runs%rowtype; sim record; need double precision;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into r from public.rb_wave_runs where id = run and owner = me for update;
    if not found or r.room is null then raise exception 'rb_duel_gone'; end if;
    if r.state = 'live' then
        if ticks is null or ticks < 1 or coalesce(array_length(toggles, 1), 0) > 30000 then raise exception 'rb_bad_choice'; end if;
        select * into sim from public.rb_wave_sim(r.seed, toggles, least(54000, ticks + 2));
        need := sim.ticks / 60.0 * 0.9 - 1.5;
        if extract(epoch from now() - r.started_at) < need then raise exception 'rb_too_fast'; end if;
        update public.rb_wave_runs set live_tg = coalesce((select array_agg(v order by v) from (select distinct v
                   from unnest(toggles) v where v > 0 and v <= sim.ticks) z), '{}'), live_t = sim.ticks,
               state = 'done', ticks = sim.ticks, dist = sim.x, live_x = sim.x, done_at = now() where id = r.id;
    end if;
    perform public.rb_wroom_tick(r.room);
    return public.rb_wroom_json(r.room, me);
end $$;

-- a room run never pays as a solo run
do $patch$
declare src text;
begin
    select pg_get_functiondef('public.rb_wave_finish(uuid, integer[], integer)'::regprocedure) into src;
    if position('r.room is not null' in src) = 0 then
        execute replace(src, 'if not found then raise exception ''rb_duel_gone''; end if;',
                        'if not found or r.room is not null then raise exception ''rb_duel_gone''; end if;');
    end if;
end $patch$;

-- the cleanup on a lockdown: open and live rooms end, bets back
create or replace function public.rb_wroom_cleanup() returns integer
language plpgsql security definer set search_path to '' as $$
declare r record; s record; n integer := 0;
begin
    for r in select * from public.rb_wave_rooms where state in ('open', 'live') for update loop
        update public.rb_wave_rooms set state = 'cancelled', why = 'lockdown', done_at = now() where id = r.id;
        update public.rb_wave_runs set state = 'quit', done_at = now() where room = r.id and state = 'live';
        if r.bet > 0 then
            for s in select owner from public.rb_wave_seats where room = r.id loop
                perform public.rb_pay(s.owner, r.bet, 0, 'wave_back', r.id::text);
            end loop;
        end if;
        n := n + 1;
    end loop;
    return n;
end $$;

revoke all on function public.rb_wroom_busy(uuid), public.rb_wroom_settle(uuid), public.rb_wroom_go(uuid),
              public.rb_wroom_tick(uuid), public.rb_wroom_json(uuid, uuid), public.rb_wroom_cleanup()
    from public, anon, authenticated;
revoke all on function public.rb_wroom_lobbies(), public.rb_wroom_create(integer, integer), public.rb_wroom_join(uuid),
              public.rb_wroom_start(uuid), public.rb_wroom_leave(uuid), public.rb_wroom_state(uuid),
              public.rb_wroom_ping(uuid, integer, integer[], integer), public.rb_wroom_finish(uuid, integer[], integer)
    from public, anon;
grant execute on function public.rb_wroom_lobbies(), public.rb_wroom_create(integer, integer), public.rb_wroom_join(uuid),
              public.rb_wroom_start(uuid), public.rb_wroom_leave(uuid), public.rb_wroom_state(uuid),
              public.rb_wroom_ping(uuid, integer, integer[], integer), public.rb_wroom_finish(uuid, integer[], integer)
    to authenticated;

commit;

do $patch$
declare src text;
begin
    select pg_get_functiondef('public.rb_feature_cleanup(text)'::regprocedure) into src;
    if src is not null and position('rb_wroom_cleanup' in src) = 0 then
        execute replace(src, 'return json_build_object(''stopped'', n);',
                        'if f in (''wave'', ''online'', ''all'') then n := n + public.rb_wroom_cleanup(); end if;' || chr(10)
                        || '    return json_build_object(''stopped'', n);');
    end if;
exception when undefined_function then null;
end $patch$;
