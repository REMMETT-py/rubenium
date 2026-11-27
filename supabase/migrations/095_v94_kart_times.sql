-- Rubenium 9.4: Karting time boards with ghosts. Safe to run twice. Undo: 095_down.sql.
--
-- After a 3 lap race you finished (its time is checked by rb_kart_finish as before), the app sends the run itself
-- (rb_kart_ghost_save: positions a few times a second, packed by the app, at most 400 000 characters). Each circuit has
-- a top 10 of the fastest times (rb_kart_times): one player can hold several places. Anyone can load a run from it
-- (rb_kart_ghost) and race against it as a ghost. Times count from board_from (the leaderboards' start), so the 9.4 reset
-- starts them again too. Only the 50 fastest runs of a circuit and each player's best are kept.
begin;

create table if not exists public.rb_kart_ghosts (
    id uuid primary key default gen_random_uuid(),
    room uuid not null references public.rb_kart_rooms(id) on delete cascade,
    owner uuid not null references public.profiles(id) on delete cascade,
    track integer not null check (track between 0 and 2),
    ms integer not null check (ms > 0),
    data text not null,
    at timestamptz not null default now(),
    unique (room, owner)
);
create index if not exists rb_kart_ghosts_board on public.rb_kart_ghosts (track, ms);
alter table public.rb_kart_ghosts enable row level security;
revoke all on public.rb_kart_ghosts from public, anon, authenticated;

create or replace function public.rb_kart_ghost_save(rid uuid, data text) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); r public.rb_kart_rooms%rowtype; s public.rb_kart_seats%rowtype; gid uuid; rk integer;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into r from public.rb_kart_rooms where id = rid;
    if not found then raise exception 'rb_duel_gone'; end if;
    select * into s from public.rb_kart_seats where room = rid and owner = me;
    if not found or s.finish_ms is null or s.gone or r.laps <> 3 or r.state not in ('live', 'done') then
        return jsonb_build_object('saved', false);
    end if;
    if data is null or length(data) < 16 or length(data) > 400000 then raise exception 'rb_bad_choice'; end if;
    insert into public.rb_kart_ghosts (room, owner, track, ms, data) values (rid, me, r.track, s.finish_ms, data)
    on conflict (room, owner) do nothing returning id into gid;
    -- keep the 50 fastest of this circuit and every player's best
    delete from public.rb_kart_ghosts g where g.track = r.track
       and g.id not in (select id from public.rb_kart_ghosts where track = r.track order by ms, at limit 50)
       and g.id not in (select distinct on (owner) id from public.rb_kart_ghosts where track = r.track order by owner, ms, at);
    select count(*) + 1 into rk from public.rb_kart_ghosts g join public.profiles p on p.id = g.owner
     where g.track = r.track and g.ms < s.finish_ms and g.at >= public.rb_board_from() and not p.banned;
    return jsonb_build_object('saved', gid is not null, 'rank', rk, 'ms', s.finish_ms, 'track', r.track);
end $$;

-- the top 10 of one circuit (several places per player), and your best
create or replace function public.rb_kart_times(track integer) returns jsonb
language plpgsql stable security definer set search_path to '' as $$
declare me uuid := auth.uid(); t0 timestamptz := public.rb_board_from();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    return jsonb_build_object(
        'track', track,
        'top', coalesce((select jsonb_agg(jsonb_build_object('id', z.id, 'rank', z.rk, 'name', z.username, 'ms', z.ms,
                                                             'me', z.owner = me) order by z.rk)
                           from (select g.id, g.owner, g.ms, p.username, row_number() over (order by g.ms, g.at) rk
                                   from public.rb_kart_ghosts g join public.profiles p on p.id = g.owner
                                  where g.track = rb_kart_times.track and g.at >= t0 and not p.banned
                                  order by g.ms, g.at limit 10) z), '[]'::jsonb),
        'mine', (select jsonb_build_object('id', g.id, 'ms', g.ms,
                                           'rank', (select count(*) + 1 from public.rb_kart_ghosts o join public.profiles q on q.id = o.owner
                                                     where o.track = g.track and o.at >= t0 and not q.banned
                                                       and (o.ms < g.ms or (o.ms = g.ms and o.at < g.at))))
                   from public.rb_kart_ghosts g where g.owner = me and g.track = rb_kart_times.track and g.at >= t0
                  order by g.ms, g.at limit 1));
end $$;

-- one run, to race against
create or replace function public.rb_kart_ghost(gid uuid) returns jsonb
language plpgsql stable security definer set search_path to '' as $$
declare g public.rb_kart_ghosts%rowtype;
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    select * into g from public.rb_kart_ghosts where id = gid;
    if not found then raise exception 'rb_duel_gone'; end if;
    return jsonb_build_object('id', g.id, 'name', (select username from public.profiles where id = g.owner),
                              'track', g.track, 'ms', g.ms, 'data', g.data);
end $$;

revoke all on function public.rb_kart_ghost_save(uuid, text), public.rb_kart_times(integer), public.rb_kart_ghost(uuid)
    from public, anon;
grant execute on function public.rb_kart_ghost_save(uuid, text), public.rb_kart_times(integer), public.rb_kart_ghost(uuid)
    to authenticated;

commit;
