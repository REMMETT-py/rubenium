-- Rubenium Karting update: tighter karts, faster bots, a 10 s countdown, Race again that works. Safe to run twice.
-- Run it after 091 (and 092). It only replaces Karting functions; no table changes, nothing deleted.
--
-- 1. rb_kart_cal: the circuits' calibrated bot lap times (the karts grip better and the bots drive at the real limit,
--    so every level is faster) and the grid slot the bot takes (Pine Ridge: slot 3, the racing line moved).
--    These numbers must match KART_CAL and the grid in the app (the same version).
-- 2. rb_kart_go: the lights go out 12.5 s after the start (was 7 s): a short pause, the menu opens out into the race,
--    then a 10 s countdown.
-- 3. A player who is over the line is no longer "in" that race: rb_kart_busy and the lobby's "your race" leave out a
--    seat with a finish time, so Race again (and a new room) work at once, while the bot or the others still finish.
--    The old race still settles as before (the lobby ticks every open race; 30 s after the last player at most).
begin;

create or replace function public.rb_kart_cal(track integer) returns jsonb
language sql immutable set search_path to '' as $$
    select (array[
        '{"key": "bay", "slot": 3, "min": 31.591, "cal": [[31.591, 100.0], [32.072, 99.6], [36.232, 80.0], [38.896, 65.0], [42.075, 55.0], [45.964, 42.5], [51.351, 28.0]]}',
        '{"key": "pine", "slot": 3, "min": 32.674, "cal": [[32.674, 100.0], [33.172, 99.6], [38.556, 80.0], [42.113, 65.0], [45.524, 55.0], [51.603, 42.5], [58.654, 28.0]]}',
        '{"key": "docks", "slot": 2, "min": 38.01, "cal": [[38.01, 100.0], [38.589, 99.6], [42.576, 80.0], [45.703, 65.0], [48.528, 55.0], [53.263, 42.5], [59.46, 28.0]]}'
    ])[track + 1]::jsonb $$;

create or replace function public.rb_kart_busy(who uuid) returns boolean
language sql stable security definer set search_path to '' as $$
    select exists (select 1 from public.rb_kart_seats s join public.rb_kart_rooms r on r.id = s.room
                    where s.owner = who and not s.gone and s.finish_ms is null and r.state in ('open', 'live')) $$;

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
    update public.rb_kart_rooms set state = 'live', live_at = now(), go_at = now() + interval '12.5 seconds',
           bot_slot = case when r.bot then best end, bot_driver = case when r.bot then r.host end where id = rid;
end $$;

-- the lobby's "your race": not one you already finished (patched in place, so later changes to the lobby are kept)
do $$
declare src text; old_ text := 'where s.owner = me and not s.gone and r.state in (''open'', ''live'') order by r.at desc limit 1';
begin
    src := pg_get_functiondef('public.rb_kart_lobbies()'::regprocedure);
    if position('s.finish_ms is null and r.state in (''open'', ''live'') order by r.at desc' in src) = 0 then
        if position(old_ in src) = 0 then
            raise exception 'rb_kart_lobbies: the line to patch was not found';
        end if;
        execute replace(src, old_, 'where s.owner = me and not s.gone and s.finish_ms is null and r.state in (''open'', ''live'') order by r.at desc limit 1');
    end if;
end $$;

revoke all on function public.rb_kart_busy(uuid), public.rb_kart_go(uuid) from public, anon, authenticated;
revoke all on function public.rb_kart_cal(integer) from public, anon;
grant execute on function public.rb_kart_cal(integer) to authenticated;

commit;
