-- Rubenium 9.2: Karting. Rooms for 1 to 3 players and always exactly one bot (or, alone, no bot and the ideal line drawn
-- on the track). Safe to run twice.
--
-- The host picks the circuit, the laps, the bot's level (100 to 2500), collisions, boost and damage. The race starts
-- 7 seconds after the room is full (or when the host starts it): 2 s to load and the 5-4-3-2-1 lights. Every PC drives
-- its own kart and sends where it is about 12 times a second (rb_kart_ping: kept in an unlogged table, nothing else is
-- written); the host's PC also drives the bot (another player takes it over if the host leaves). At the line each player
-- sends their time and laps (rb_kart_finish); the server checks them against the clock and the fastest possible lap,
-- works out the score out of 100 from the circuit's calibrated lap times, the places (the bot included) and the prize.
-- No bets: the prize depends on place, score, players and bot beaten, a clean race and the bot's level, with a daily cap.
begin;

insert into public.rb_features (name, parent) values ('kart', 'online') on conflict do nothing;
insert into public.rb_config (key, value) values ('kart_cap', 2500) on conflict do nothing;      -- prize per day
insert into public.rb_config (key, value) values ('kart_race_min', 9) on conflict do nothing;   -- a race ends after this

create table if not exists public.rb_kart_rooms (
    id uuid primary key default gen_random_uuid(),
    host uuid not null references public.profiles (id) on delete cascade,
    size integer not null check (size between 1 and 3),
    track integer not null check (track between 0 and 2),
    laps integer not null check (laps between 1 and 5),
    bot_elo integer not null check (bot_elo between 100 and 2500),
    bot boolean not null default true,
    collide boolean not null default true,
    boost boolean not null default true,
    damage boolean not null default true,
    state text not null default 'open' check (state in ('open', 'live', 'done', 'cancelled')),
    why text,
    seed bigint not null default floor(random() * 2147483647)::bigint,
    bot_driver uuid,
    bot_slot integer,
    bot_ms integer,
    bot_laps integer[],
    bot_prog real,
    bot_score numeric(4, 1),
    bot_place integer,
    at timestamptz not null default now(),
    live_at timestamptz,
    go_at timestamptz,
    done_at timestamptz);
create index if not exists rb_kart_rooms_state on public.rb_kart_rooms (state, at desc);
alter table public.rb_kart_rooms enable row level security;

create table if not exists public.rb_kart_seats (
    room uuid not null references public.rb_kart_rooms (id) on delete cascade,
    owner uuid not null references public.profiles (id) on delete cascade,
    seat integer not null check (seat between 0 and 2),
    slot integer,
    finish_ms integer,
    laps integer[],
    best_ms integer,
    blowups integer,
    hits integer,
    turbos integer,
    score numeric(4, 1),
    prog real,
    place integer,
    paid integer not null default 0,
    xp integer not null default 0,
    gone boolean not null default false,
    at timestamptz not null default now(),
    done_at timestamptz,
    primary key (room, owner),
    unique (room, seat));
create index if not exists rb_kart_seats_owner on public.rb_kart_seats (owner, at desc);
alter table public.rb_kart_seats enable row level security;

-- where each kart is right now (seat 3 is the bot): written ~12 times a second, so not worth logging
create unlogged table if not exists public.rb_kart_live (
    room uuid not null,
    seat integer not null,
    snap jsonb,
    t real,
    at timestamptz not null default now(),
    primary key (room, seat));
alter table public.rb_kart_live enable row level security;
revoke all on public.rb_kart_rooms, public.rb_kart_seats, public.rb_kart_live from anon, authenticated;

-- ---------------------------------------------------------------- the circuits' numbers (the same as the app's)
-- per circuit: the bot's grid slot (the theoretically best one), the fastest possible lap (s), and the calibrated
-- average lap times of the six bot levels (Professional, Elite, Expert, Racer, Amateur, Rookie) with their scores
create or replace function public.rb_kart_cal(track integer) returns jsonb
language sql immutable set search_path to '' as $$
    select (array[
        '{"key": "bay", "slot": 3, "min": 36.045, "cal": [[36.045, 100.0], [36.594, 99.6], [41.014, 80.0], [42.796, 65.0], [45.274, 55.0], [49.444, 42.5], [55.119, 28.0]]}',
        '{"key": "pine", "slot": 2, "min": 38.495, "cal": [[38.495, 100.0], [39.081, 99.6], [45.215, 80.0], [47.026, 65.0], [50.456, 55.0], [56.481, 42.5], [63.801, 28.0]]}',
        '{"key": "docks", "slot": 2, "min": 42.038, "cal": [[42.038, 100.0], [42.678, 99.6], [47.625, 80.0], [49.571, 65.0], [52.711, 55.0], [57.783, 42.5], [64.281, 28.0]]}'
    ])[track + 1]::jsonb $$;

-- the score out of 100 for a race: the average lap against the calibrated times (the standing start counted the same)
create or replace function public.rb_kart_score(track integer, laps integer, ms integer) returns numeric
language plpgsql immutable set search_path to '' as $$
declare c jsonb := public.rb_kart_cal(track) -> 'cal'; per double precision; i integer; t0 double precision; t1 double precision;
        s0 double precision; s1 double precision; tl double precision; sl double precision;
begin
    if laps is null or laps < 1 or ms is null or ms <= 0 then return 0; end if;
    per := ms / 1000.0 / laps + 1.0 * (1.0 / 3 - 1.0 / laps);
    if per <= (c -> 0 ->> 0)::float8 then return 100; end if;
    for i in 0 .. jsonb_array_length(c) - 2 loop
        t0 := (c -> i ->> 0)::float8; s0 := (c -> i ->> 1)::float8;
        t1 := (c -> (i + 1) ->> 0)::float8; s1 := (c -> (i + 1) ->> 1)::float8;
        if per <= t1 then return round((s0 + (s1 - s0) * (per - t0) / (t1 - t0))::numeric, 1); end if;
    end loop;
    tl := (c -> -1 ->> 0)::float8; sl := (c -> -1 ->> 1)::float8;
    return round(greatest(0, sl * tl / per - (per - tl) * 0.2)::numeric, 1);
end $$;

create or replace function public.rb_kart_best(who uuid, since timestamptz) returns integer
language sql stable security definer set search_path to '' as $$
    select coalesce(round(max(s.score) * 10), 0)::int from public.rb_kart_seats s join public.rb_kart_rooms r on r.id = s.room
     where s.owner = who and s.score is not null and r.state = 'done' and s.at >= since $$;

create or replace function public.rb_kart_busy(who uuid) returns boolean
language sql stable security definer set search_path to '' as $$
    select exists (select 1 from public.rb_kart_seats s join public.rb_kart_rooms r on r.id = s.room
                    where s.owner = who and not s.gone and r.state in ('open', 'live')) $$;

create or replace function public.rb_kart_paid_today(who uuid) returns integer
language sql stable security definer set search_path to '' as $$
    select coalesce(sum(s.paid), 0)::int from public.rb_kart_seats s join public.rb_kart_rooms r on r.id = s.room
     where s.owner = who and r.done_at >= date_trunc('day', now()) $$;

-- ---------------------------------------------------------------- the end of a race
create or replace function public.rb_kart_settle(rid uuid) returns void
language plpgsql security definer set search_path to '' as $$
declare r public.rb_kart_rooms%rowtype; s record; n_h integer; k integer; pr integer; xp_ integer; cap integer;
        beat_h integer; beat_bot boolean; bot_t double precision;
begin
    select * into r from public.rb_kart_rooms where id = rid for update;
    if not found or r.state <> 'live' then return; end if;
    -- how far round the unfinished karts got (from their last live position)
    update public.rb_kart_seats ks set prog = coalesce(ks.prog, (select (l.snap ->> 11)::real from public.rb_kart_live l where l.room = rid and l.seat = ks.seat))
     where ks.room = rid and ks.finish_ms is null;
    if r.bot and r.bot_ms is null then
        r.bot_prog := (select (l.snap ->> 11)::real from public.rb_kart_live l where l.room = rid and l.seat = 3);
        update public.rb_kart_rooms set bot_prog = r.bot_prog where id = rid;
    end if;
    -- places: finished karts by time (the bot too), then the rest by how far round they got
    bot_t := case when r.bot and r.bot_ms is not null then r.bot_ms else null end;
    k := 0;
    for s in with all_ as (
                select ks.owner, ks.finish_ms::float8 ms, coalesce(ks.prog, 0) prog, ks.gone from public.rb_kart_seats ks where ks.room = rid
                union all
                select null::uuid, bot_t, coalesce(r.bot_prog, 0), false where r.bot)
             select * from all_ order by (ms is null), ms, gone, prog desc loop
        k := k + 1;
        if s.owner is null then
            update public.rb_kart_rooms set bot_place = k where id = rid;
        else
            update public.rb_kart_seats set place = k where room = rid and owner = s.owner;
        end if;
    end loop;
    select count(*) into n_h from public.rb_kart_seats where room = rid;
    select bot_place into r.bot_place from public.rb_kart_rooms where id = rid;
    for s in select * from public.rb_kart_seats where room = rid order by seat loop
        if s.finish_ms is null or s.gone then continue; end if;
        -- the prize: finishing, the score, each player and the bot beaten (the bot by its level), first place, a clean race
        beat_h := (select count(*) from public.rb_kart_seats o where o.room = rid and o.owner <> s.owner and o.place > s.place);
        beat_bot := r.bot and r.bot_place is not null and r.bot_place > s.place;
        pr := 20 + floor(coalesce(s.score, 0) * 0.8)::int + 40 * beat_h
              + case when beat_bot then floor(10 + 190 * power(r.bot_elo / 2500.0, 2))::int else 0 end
              + case when s.place = 1 and n_h + (case when r.bot then 1 else 0 end) > 1 then 40 else 0 end
              + case when coalesce(s.blowups, 0) = 0 then 20 else 0 end;
        pr := floor(pr * least(1.0, r.laps / 3.0))::int;                       -- shorter races pay less
        cap := coalesce(public.rb_cfg('kart_cap'), 2500)::int;
        pr := greatest(0, least(pr, cap - public.rb_kart_paid_today(s.owner)));
        xp_ := 20 + 10 * beat_h + case when beat_bot then 10 else 0 end;
        if pr > 0 then perform public.rb_pay(s.owner, pr, 0, 'kart', rid::text); end if;
        perform public.rb_xp_add(s.owner, xp_, 'kart', rid::text);
        update public.rb_kart_seats set paid = pr, xp = xp_ where room = rid and owner = s.owner;
    end loop;
    update public.rb_kart_rooms set state = 'done', done_at = now(), why = coalesce(why, 'finished') where id = rid;
    delete from public.rb_kart_live where room = rid;
end $$;

-- the lights go out in 7 s: grid slots (the bot on the best one, the players on the others, all as far from the first
-- corner), who drives the bot
create or replace function public.rb_kart_go(rid uuid) returns void
language plpgsql security definer set search_path to '' as $$
declare r public.rb_kart_rooms%rowtype; s record; best integer; free_ integer[]; k integer := 0;
begin
    select * into r from public.rb_kart_rooms where id = rid for update;
    if not found or r.state <> 'open' then return; end if;
    best := (public.rb_kart_cal(r.track) ->> 'slot')::int;
    free_ := array(select g from generate_series(0, 3) g where not (r.bot and g = best) order by abs(g - best), g);
    for s in select owner from public.rb_kart_seats where room = rid order by seat loop
        k := k + 1;
        update public.rb_kart_seats set slot = free_[k] where room = rid and owner = s.owner;
    end loop;
    update public.rb_kart_rooms set state = 'live', live_at = now(), go_at = now() + interval '7 seconds',
           bot_slot = case when r.bot then best end, bot_driver = case when r.bot then r.host end where id = rid;
end $$;

create or replace function public.rb_kart_tick(rid uuid) returns void
language plpgsql security definer set search_path to '' as $$
declare r public.rb_kart_rooms%rowtype; drv uuid; lim interval;
begin
    select * into r from public.rb_kart_rooms where id = rid for update;
    if not found then return; end if;
    lim := make_interval(mins => coalesce(public.rb_cfg('kart_race_min'), 9)::int);
    if r.state = 'open' and now() - r.at > make_interval(mins => coalesce(public.rb_cfg('lobby_min'), 5)::int) then
        update public.rb_kart_rooms set state = 'cancelled', why = 'expired', done_at = now() where id = rid;
    elsif r.state = 'live' then
        -- a player whose PC went quiet for 20 s has left
        update public.rb_kart_seats s set gone = true, done_at = now()
         where s.room = rid and not s.gone and s.finish_ms is null and now() > r.go_at + interval '15 seconds'
           and not exists (select 1 from public.rb_kart_live l where l.room = rid and l.seat = s.seat and l.at > now() - interval '20 seconds');
        -- the bot's PC went quiet (or its player left): the next PC still sending takes the bot over
        if r.bot and r.bot_ms is null and now() > r.go_at - interval '4 seconds'
           and not exists (select 1 from public.rb_kart_seats s join public.rb_kart_live l on l.room = rid and l.seat = s.seat
                            where s.room = rid and s.owner = r.bot_driver and not s.gone and l.at > now() - interval '4 seconds') then
            select s.owner into drv from public.rb_kart_seats s join public.rb_kart_live l on l.room = rid and l.seat = s.seat
             where s.room = rid and not s.gone and l.at > now() - interval '4 seconds' order by s.seat limit 1;
            if drv is not null and drv is distinct from r.bot_driver then
                update public.rb_kart_rooms set bot_driver = drv where id = rid;
            end if;
        end if;
        if now() - r.go_at > lim then
            perform public.rb_kart_settle(rid);
        elsif not exists (select 1 from public.rb_kart_seats where room = rid and not gone and finish_ms is null) then
            -- every player is over the line (or gone): settle once the bot is too, or 30 s after the last player
            if not r.bot or r.bot_ms is not null
               or not exists (select 1 from public.rb_kart_seats where room = rid and not gone)
               or now() - coalesce((select max(done_at) from public.rb_kart_seats where room = rid), now()) > interval '30 seconds' then
                perform public.rb_kart_settle(rid);
            end if;
        end if;
    end if;
end $$;

create or replace function public.rb_kart_json(rid uuid, me uuid) returns jsonb
language sql stable security definer set search_path to '' as $$
    select jsonb_build_object('id', r.id, 'state', r.state, 'size', r.size, 'track', r.track, 'laps', r.laps,
        'bot', r.bot, 'bot_elo', r.bot_elo, 'collide', r.collide, 'boost', r.boost, 'damage', r.damage, 'seed', r.seed,
        'why', r.why, 'host', (select username from public.profiles where id = r.host), 'mine', r.host = me,
        'bot_here', r.bot_driver = me, 'bot_slot', r.bot_slot, 'bot_ms', r.bot_ms, 'bot_laps', to_jsonb(r.bot_laps),
        'bot_score', r.bot_score, 'bot_place', r.bot_place,
        'go_in', case when r.go_at is not null then round(extract(epoch from (r.go_at - now()))::numeric, 3) end,
        'players', coalesce((select jsonb_agg(jsonb_build_object('name', p.username, 'seat', s.seat, 'slot', s.slot,
                        'me', s.owner = me, 'ms', s.finish_ms, 'laps', to_jsonb(s.laps), 'best', s.best_ms,
                        'blowups', s.blowups, 'hits', s.hits, 'turbos', s.turbos, 'score', s.score, 'place', s.place,
                        'paid', s.paid, 'xp', s.xp, 'gone', s.gone) order by s.seat)
                   from public.rb_kart_seats s join public.profiles p on p.id = s.owner where s.room = r.id), '[]'::jsonb))
      from public.rb_kart_rooms r where r.id = rid $$;

-- ---------------------------------------------------------------- what players call
create or replace function public.rb_kart_lobbies() returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); o record; cur uuid;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    for o in select id from public.rb_kart_rooms where state in ('open', 'live') loop
        perform public.rb_kart_tick(o.id);
    end loop;
    select r.id into cur from public.rb_kart_seats s join public.rb_kart_rooms r on r.id = s.room
     where s.owner = me and not s.gone and r.state in ('open', 'live') order by r.at desc limit 1;
    return jsonb_build_object(
        'mine', case when cur is not null then public.rb_kart_json(cur, me) end,
        'today', public.rb_kart_paid_today(me), 'cap', coalesce(public.rb_cfg('kart_cap'), 2500),
        'best', coalesce((select jsonb_object_agg(t, b) from (
                    select r.track t, max(s.score) b from public.rb_kart_seats s join public.rb_kart_rooms r on r.id = s.room
                     where s.owner = me and s.score is not null and r.state = 'done' group by r.track) z), '{}'::jsonb),
        'top', coalesce((select jsonb_agg(z order by z.t, z.rk) from (
                    select r.track t, p.username name, max(s.score) score, min(s.finish_ms) filter (where r.laps = 3) ms,
                           rank() over (partition by r.track order by max(s.score) desc) rk
                      from public.rb_kart_seats s join public.rb_kart_rooms r on r.id = s.room join public.profiles p on p.id = s.owner
                     where s.score is not null and r.state = 'done' and not p.banned and s.at >= public.rb_board_from()
                     group by r.track, p.username) z where z.rk <= 5), '[]'::jsonb),
        'rooms', coalesce((select jsonb_agg(jsonb_build_object('id', r.id, 'host', u.username, 'size', r.size,
                        'track', r.track, 'laps', r.laps, 'bot_elo', r.bot_elo, 'collide', r.collide,
                        'seated', (select count(*) from public.rb_kart_seats s where s.room = r.id),
                        'friend', public.rb_is_friend(me, r.host)) order by r.at)
                   from public.rb_kart_rooms r join public.profiles u on u.id = r.host
                  where r.state = 'open' and r.size > 1 and not u.banned), '[]'::jsonb));
end $$;

create or replace function public.rb_kart_create(size integer, track integer, laps integer, bot_elo integer, bot boolean,
                                                 collide boolean, boost boolean, damage boolean) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; rid uuid; old record;
begin
    perform public.rb_rate(auth.uid(), 'duel', 10);
    perform public.rb_need_feature('kart');
    p := public.rb_lock_me();
    for old in select s.room from public.rb_kart_seats s where s.owner = p.id loop perform public.rb_kart_tick(old.room); end loop;
    if public.rb_kart_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    if size is null or size not between 1 and 3 or track is null or track not between 0 and 2 or laps is null
       or laps not between 1 and 5 or bot_elo is null or bot_elo not between 100 and 2500 then raise exception 'rb_bad_choice'; end if;
    bot := coalesce(bot, true) or size > 1;                       -- with other players there is always exactly one bot
    insert into public.rb_kart_rooms (host, size, track, laps, bot_elo, bot, collide, boost, damage)
         values (p.id, size, track, laps, bot_elo, bot, coalesce(collide, true), coalesce(boost, true), coalesce(damage, true))
      returning id into rid;
    insert into public.rb_kart_seats (room, owner, seat) values (rid, p.id, 0);
    if size = 1 then perform public.rb_kart_go(rid); end if;     -- alone: straight to the lights
    return public.rb_kart_json(rid, p.id);
end $$;

create or replace function public.rb_kart_join(rid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; r public.rb_kart_rooms%rowtype; n integer; seat_ integer;
begin
    perform public.rb_rate(auth.uid(), 'duel', 10);
    perform public.rb_need_feature('kart');
    p := public.rb_lock_me();
    perform public.rb_kart_tick(rid);
    select * into r from public.rb_kart_rooms where id = rid for update;
    if not found or r.state <> 'open' then raise exception 'rb_duel_gone'; end if;
    if exists (select 1 from public.rb_kart_seats where room = rid and owner = p.id) then raise exception 'rb_thats_you'; end if;
    if public.rb_kart_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    select count(*) into n from public.rb_kart_seats where room = rid;
    if n >= r.size then raise exception 'rb_duel_gone'; end if;
    select min(k) into seat_ from generate_series(0, 2) k where not exists (select 1 from public.rb_kart_seats s where s.room = rid and s.seat = k);
    insert into public.rb_kart_seats (room, owner, seat) values (rid, p.id, seat_);
    perform public.rb_notice(r.host, 'kart_yes', jsonb_build_object('from', p.username, 'id', rid));
    if n + 1 >= r.size then perform public.rb_kart_go(rid); end if;
    return public.rb_kart_json(rid, p.id);
end $$;

-- the host starts with whoever is there (a room alone with the bot is fine too)
create or replace function public.rb_kart_start(rid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid();
begin
    if not exists (select 1 from public.rb_kart_rooms where id = rid and host = me and state = 'open') then raise exception 'rb_duel_gone'; end if;
    perform public.rb_kart_go(rid);
    return public.rb_kart_json(rid, me);
end $$;

create or replace function public.rb_kart_leave(rid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); r public.rb_kart_rooms%rowtype;
begin
    select * into r from public.rb_kart_rooms where id = rid for update;
    if not found or not exists (select 1 from public.rb_kart_seats where room = rid and owner = me) then raise exception 'rb_duel_gone'; end if;
    if r.state = 'open' then
        if r.host = me then
            update public.rb_kart_rooms set state = 'cancelled', why = 'closed', done_at = now() where id = rid;
        else
            delete from public.rb_kart_seats where room = rid and owner = me;
        end if;
    elsif r.state = 'live' then
        update public.rb_kart_seats set gone = true, done_at = now() where room = rid and owner = me and finish_ms is null;
        perform public.rb_kart_tick(rid);
    end if;
    return jsonb_build_object('left', true);
end $$;

create or replace function public.rb_kart_state(rid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_kart_tick(rid);
    if not exists (select 1 from public.rb_kart_seats where room = rid and owner = me) then raise exception 'rb_duel_gone'; end if;
    return public.rb_kart_json(rid, me);
end $$;

-- the live race: my kart (and the bot if my PC drives it) in, everyone else's out. snaps: [[seat, race_t, ...kart], ...]
create or replace function public.rb_kart_ping(rid uuid, snaps jsonb) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); r public.rb_kart_rooms%rowtype; my integer; e jsonb; seat_ integer; t_ real; now_t real;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into r from public.rb_kart_rooms where id = rid;
    select seat into my from public.rb_kart_seats where room = rid and owner = me and not gone;
    if not found or my is null then raise exception 'rb_duel_gone'; end if;
    if r.state = 'live' and jsonb_typeof(snaps) = 'array' and jsonb_array_length(snaps) <= 2 and length(snaps::text) < 2000 then
        now_t := extract(epoch from (now() - r.go_at));
        for e in select * from jsonb_array_elements(snaps) loop
            seat_ := (e ->> 0)::int;
            t_ := least((e ->> 1)::real, now_t + 1.0);
            if seat_ = my or (seat_ = 3 and r.bot and r.bot_driver = me) then
                insert into public.rb_kart_live (room, seat, snap, t, at) values (rid, seat_, e, t_, now())
                    on conflict (room, seat) do update set snap = excluded.snap, t = excluded.t, at = excluded.at;
            end if;
        end loop;
    end if;
    return jsonb_build_object('state', r.state, 'now', round(extract(epoch from (now() - r.go_at))::numeric, 3),
        'bot_here', r.bot and r.bot_driver = me,
        'gone', coalesce((select jsonb_agg(seat) from public.rb_kart_seats where room = rid and gone), '[]'::jsonb),
        'karts', coalesce((select jsonb_agg(l.snap) from public.rb_kart_live l where l.room = rid and l.seat <> my
                              and not (l.seat = 3 and r.bot_driver = me)), '[]'::jsonb));
end $$;

-- over the line: my time, laps and how the race went. The bot's driver also sends the bot's.
create or replace function public.rb_kart_finish(rid uuid, ms integer, laps integer[], best integer, blowups integer,
                                                 hits integer, turbos integer, prog real, is_bot boolean) returns jsonb
language plpgsql security definer set search_path to '' as $$
#variable_conflict use_column
declare me uuid := auth.uid(); r public.rb_kart_rooms%rowtype; s public.rb_kart_seats%rowtype; least_ms integer;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into r from public.rb_kart_rooms where id = rid for update;
    if not found then raise exception 'rb_duel_gone'; end if;
    select * into s from public.rb_kart_seats where room = rid and owner = me;
    if not found then raise exception 'rb_duel_gone'; end if;
    if r.state = 'live' then
        least_ms := floor((public.rb_kart_cal(r.track) ->> 'min')::float8 * r.laps * 1000 * 0.94)::int;
        if ms is not null then
            if ms < least_ms or coalesce(cardinality(rb_kart_finish.laps), 0) <> r.laps
               or abs((select sum(v) from unnest(rb_kart_finish.laps) v) - ms) > 50
               or extract(epoch from (now() - r.go_at)) * 1000 < ms - 2500 then raise exception 'rb_too_fast'; end if;
        end if;
        if coalesce(is_bot, false) then
            if r.bot and r.bot_driver = me and r.bot_ms is null then
                update public.rb_kart_rooms set bot_ms = ms, bot_laps = rb_kart_finish.laps, bot_prog = rb_kart_finish.prog,
                       bot_score = case when ms is not null then public.rb_kart_score(r.track, r.laps, ms) end where id = rid;
            end if;
        elsif s.finish_ms is null and not s.gone then
            update public.rb_kart_seats set finish_ms = ms, laps = rb_kart_finish.laps, best_ms = rb_kart_finish.best, blowups = rb_kart_finish.blowups,
                   hits = rb_kart_finish.hits, turbos = rb_kart_finish.turbos, prog = rb_kart_finish.prog,
                   score = case when ms is not null then public.rb_kart_score(r.track, r.laps, ms) end,
                   gone = ms is null, done_at = now()
             where room = rid and owner = me;
        end if;
        perform public.rb_kart_tick(rid);
    end if;
    return public.rb_kart_json(rid, me);
end $$;

-- the Leaderboards tab: 'kart' is each player's best score (tenths of a %), on any circuit
do $patch$
declare src text;
begin
    select pg_get_functiondef('public.rb_leaders(text, boolean)'::regprocedure) into src;
    if src is not null and position('''kart''' in src) = 0 then
        src := replace(src, '''tri'', ''a:tri'')', '''tri'', ''a:tri'', ''kart'')');
        src := replace(src, 'when ''a:tri'' then public.rb_bg_duel_wins(w.id, ''tri'')',
                       'when ''a:tri'' then public.rb_bg_duel_wins(w.id, ''tri'')' || chr(10)
                       || '                when ''kart'' then public.rb_kart_best(w.id, t0)');
        execute src;
    end if;
end $patch$;

create or replace function public.rb_kart_cleanup() returns integer
language plpgsql security definer set search_path to '' as $$
declare r record; n integer := 0;
begin
    for r in select id, state from public.rb_kart_rooms where state in ('open', 'live') loop
        if r.state = 'live' then
            update public.rb_kart_seats set gone = true where room = r.id and finish_ms is null;
            perform public.rb_kart_settle(r.id);
        else
            update public.rb_kart_rooms set state = 'cancelled', why = 'stopped', done_at = now() where id = r.id;
        end if;
        n := n + 1;
    end loop;
    return n;
end $$;

revoke all on function public.rb_kart_settle(uuid), public.rb_kart_go(uuid), public.rb_kart_tick(uuid),
              public.rb_kart_json(uuid, uuid), public.rb_kart_busy(uuid), public.rb_kart_paid_today(uuid),
              public.rb_kart_best(uuid, timestamptz), public.rb_kart_cleanup()
    from public, anon, authenticated;
revoke all on function public.rb_kart_lobbies(), public.rb_kart_create(integer, integer, integer, integer, boolean, boolean, boolean, boolean),
              public.rb_kart_join(uuid), public.rb_kart_start(uuid), public.rb_kart_leave(uuid), public.rb_kart_state(uuid),
              public.rb_kart_ping(uuid, jsonb), public.rb_kart_finish(uuid, integer, integer[], integer, integer, integer, integer, real, boolean),
              public.rb_kart_cal(integer), public.rb_kart_score(integer, integer, integer)
    from public, anon;
grant execute on function public.rb_kart_lobbies(), public.rb_kart_create(integer, integer, integer, integer, boolean, boolean, boolean, boolean),
              public.rb_kart_join(uuid), public.rb_kart_start(uuid), public.rb_kart_leave(uuid), public.rb_kart_state(uuid),
              public.rb_kart_ping(uuid, jsonb), public.rb_kart_finish(uuid, integer, integer[], integer, integer, integer, integer, real, boolean),
              public.rb_kart_cal(integer), public.rb_kart_score(integer, integer, integer)
    to authenticated;

commit;

do $patch$
declare src text;
begin
    select pg_get_functiondef('public.rb_feature_cleanup(text)'::regprocedure) into src;
    if src is not null and position('rb_kart_cleanup' in src) = 0 then
        execute replace(src, 'return json_build_object(''stopped'', n);',
                        'if f in (''kart'', ''online'', ''all'') then n := n + public.rb_kart_cleanup(); end if;' || chr(10)
                        || '    return json_build_object(''stopped'', n);');
    end if;
exception when undefined_function then null;
end $patch$;
