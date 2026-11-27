-- Rubenium 10.0. Safe to run twice (the full reset only happens the first time). Undo: 099_down.sql (not the reset:
-- the copies kept in rb_bak100_* are how a player is put back).
--
-- Hoops online duels: a room for two players. "vs": each player with a bot team-mate, against each other.
-- "coop": the two players on one team against two bots. The host's PC runs the match; the other PC sends its
-- controls and shows the host's match. Both rows of rb_hoops_live are written ~15 times a second (unlogged).
-- Each player's prize is the usual Hoops prize for the bots' level, through rb_hoops_start / rb_hoops_finish.
begin;

create table if not exists public.rb_hoops_rooms (
    id uuid primary key default gen_random_uuid(),
    host uuid not null references public.profiles (id) on delete cascade,
    guest uuid references public.profiles (id) on delete set null,
    mode text not null check (mode in ('vs', 'coop')),
    level text not null check (level in ('Club', 'Regional', 'National', 'Professional')),
    mins integer not null check (mins between 2 and 5),
    seed integer not null default floor(random() * 1000000000)::int,
    state text not null default 'open' check (state in ('open', 'live', 'done', 'cancelled')),
    why text,
    at timestamptz not null default now(),
    go_at timestamptz,
    done_at timestamptz);
create index if not exists rb_hoops_rooms_state on public.rb_hoops_rooms (state, at);
alter table public.rb_hoops_rooms enable row level security;

create unlogged table if not exists public.rb_hoops_live (
    room uuid not null,
    side integer not null,                 -- 0 the host, 1 the guest
    data jsonb,
    at timestamptz not null default now(),
    primary key (room, side));
alter table public.rb_hoops_live enable row level security;
revoke all on public.rb_hoops_rooms, public.rb_hoops_live from anon, authenticated;

-- rooms nobody talks to any more end by themselves
create or replace function public.rb_hoops_room_tick(rid uuid) returns void
language plpgsql security definer set search_path to '' as $$
declare r public.rb_hoops_rooms%rowtype; last_at timestamptz;
begin
    select * into r from public.rb_hoops_rooms where id = rid for update;
    if not found then return; end if;
    if r.state = 'open' and r.at < now() - interval '15 minutes' then
        update public.rb_hoops_rooms set state = 'cancelled', why = 'expired', done_at = now() where id = rid;
    elsif r.state = 'live' then
        select max(l.at) into last_at from public.rb_hoops_live l where l.room = rid;
        if coalesce(last_at, r.go_at) < now() - interval '60 seconds' or r.go_at < now() - interval '40 minutes' then
            update public.rb_hoops_rooms set state = 'done', why = 'quiet', done_at = now() where id = rid;
            delete from public.rb_hoops_live where room = rid;
        end if;
    end if;
end $$;

create or replace function public.rb_hoops_room_json(rid uuid, me uuid) returns jsonb
language sql stable security definer set search_path to '' as $$
    select jsonb_build_object('id', r.id, 'mode', r.mode, 'level', r.level, 'mins', r.mins, 'seed', r.seed,
               'state', r.state, 'why', r.why, 'host', h.username, 'guest', g.username, 'me_host', r.host = me,
               'go_in', case when r.go_at is not null then extract(epoch from (r.go_at - now())) end)
      from public.rb_hoops_rooms r join public.profiles h on h.id = r.host left join public.profiles g on g.id = r.guest
     where r.id = rid $$;

create or replace function public.rb_hoops_busy(who uuid) returns uuid
language sql stable security definer set search_path to '' as $$
    select id from public.rb_hoops_rooms where (host = who or guest = who) and state in ('open', 'live')
     order by at desc limit 1 $$;

create or replace function public.rb_hoops_rooms() returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); o record; cur uuid;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    for o in select id from public.rb_hoops_rooms where state in ('open', 'live') loop
        perform public.rb_hoops_room_tick(o.id);
    end loop;
    delete from public.rb_hoops_live l using public.rb_hoops_rooms r
     where r.id = l.room and r.state in ('done', 'cancelled') and r.done_at < now() - interval '2 minutes';
    cur := public.rb_hoops_busy(me);
    return jsonb_build_object(
        'mine', case when cur is not null then public.rb_hoops_room_json(cur, me) end,
        'rooms', coalesce((select jsonb_agg(jsonb_build_object('id', r.id, 'host', u.username, 'mode', r.mode,
                        'level', r.level, 'mins', r.mins, 'friend', public.rb_is_friend(me, r.host)) order by r.at)
                   from public.rb_hoops_rooms r join public.profiles u on u.id = r.host
                  where r.state = 'open' and r.host <> me and not u.banned), '[]'::jsonb));
end $$;

create or replace function public.rb_hoops_room_create(mode text, level text, mins integer) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; rid uuid; old uuid;
begin
    perform public.rb_rate(auth.uid(), 'duel', 10);
    perform public.rb_need_feature('hoops');
    p := public.rb_lock_me();
    old := public.rb_hoops_busy(p.id);
    if old is not null then perform public.rb_hoops_room_tick(old); end if;
    if public.rb_hoops_busy(p.id) is not null then raise exception 'rb_one_lobby'; end if;
    if mode not in ('vs', 'coop') or level not in ('Club', 'Regional', 'National', 'Professional')
       or mins is null or mins not between 2 and 5 then raise exception 'rb_bad_choice'; end if;
    insert into public.rb_hoops_rooms (host, mode, level, mins) values (p.id, mode, level, mins) returning id into rid;
    return public.rb_hoops_room_json(rid, p.id);
end $$;

create or replace function public.rb_hoops_room_join(rid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; r public.rb_hoops_rooms%rowtype;
begin
    perform public.rb_rate(auth.uid(), 'duel', 10);
    perform public.rb_need_feature('hoops');
    p := public.rb_lock_me();
    perform public.rb_hoops_room_tick(rid);
    select * into r from public.rb_hoops_rooms where id = rid for update;
    if not found or r.state <> 'open' or r.guest is not null then raise exception 'rb_duel_gone'; end if;
    if r.host = p.id then raise exception 'rb_thats_you'; end if;
    if public.rb_hoops_busy(p.id) is not null then raise exception 'rb_one_lobby'; end if;
    update public.rb_hoops_rooms set guest = p.id, state = 'live', go_at = now() + interval '4 seconds' where id = rid;
    perform public.rb_notice(r.host, 'hoops_yes', jsonb_build_object('from', p.username, 'id', rid));
    return public.rb_hoops_room_json(rid, p.id);
end $$;

create or replace function public.rb_hoops_room_state(rid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_hoops_room_tick(rid);
    if not exists (select 1 from public.rb_hoops_rooms where id = rid and (host = me or guest = me)) then
        raise exception 'rb_duel_gone';
    end if;
    return public.rb_hoops_room_json(rid, me);
end $$;

create or replace function public.rb_hoops_room_leave(rid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); r public.rb_hoops_rooms%rowtype;
begin
    select * into r from public.rb_hoops_rooms where id = rid for update;
    if not found or me not in (r.host, coalesce(r.guest, r.host)) then raise exception 'rb_duel_gone'; end if;
    if r.state = 'open' then
        update public.rb_hoops_rooms set state = 'cancelled', why = 'closed', done_at = now() where id = rid;
    elsif r.state = 'live' then
        -- the other PC sees the silence; the room ends when the host says so (or goes quiet)
        insert into public.rb_hoops_live (room, side, data, at) values (rid, case when me = r.host then 0 else 1 end, '{"left": true}', now())
            on conflict (room, side) do update set data = excluded.data, at = excluded.at;
        if me = r.host then
            update public.rb_hoops_rooms set state = 'done', why = 'host_left', done_at = now() where id = rid;
        end if;
    end if;
    return jsonb_build_object('left', true);
end $$;

-- the host's PC: the match is over
create or replace function public.rb_hoops_room_end(rid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid();
begin
    update public.rb_hoops_rooms set state = 'done', why = coalesce(why, 'over'), done_at = now()
     where id = rid and host = me and state = 'live';
    return jsonb_build_object('ok', true);
end $$;

-- the live match: my side in, the other side out (with how old it is)
create or replace function public.rb_hoops_ping(rid uuid, data jsonb) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); r public.rb_hoops_rooms%rowtype; side_ integer; o public.rb_hoops_live%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into r from public.rb_hoops_rooms where id = rid;
    if not found or me not in (r.host, coalesce(r.guest, r.host)) then raise exception 'rb_duel_gone'; end if;
    side_ := case when me = r.host then 0 else 1 end;
    -- the host keeps sending for a few seconds after the final whistle, so the guest sees the end too
    if (r.state = 'live' or (r.state = 'done' and r.why = 'over' and r.done_at > now() - interval '20 seconds'))
       and data is not null and length(data::text) < 16000 then
        insert into public.rb_hoops_live (room, side, data, at) values (rid, side_, data, now())
            on conflict (room, side) do update set data = excluded.data, at = excluded.at;
    end if;
    select * into o from public.rb_hoops_live where room = rid and side = 1 - side_;
    return jsonb_build_object('state', r.state, 'why', r.why, 'other', o.data,
                              'age', case when o.at is not null then extract(epoch from (now() - o.at)) end,
                              'go_in', case when r.go_at is not null then extract(epoch from (r.go_at - now())) end);
end $$;

revoke all on function public.rb_hoops_room_tick(uuid), public.rb_hoops_room_json(uuid, uuid), public.rb_hoops_busy(uuid)
    from public, anon, authenticated;
revoke all on function public.rb_hoops_rooms(), public.rb_hoops_room_create(text, text, integer), public.rb_hoops_room_join(uuid),
    public.rb_hoops_room_state(uuid), public.rb_hoops_room_leave(uuid), public.rb_hoops_room_end(uuid),
    public.rb_hoops_ping(uuid, jsonb) from public, anon;
grant execute on function public.rb_hoops_rooms(), public.rb_hoops_room_create(text, text, integer), public.rb_hoops_room_join(uuid),
    public.rb_hoops_room_state(uuid), public.rb_hoops_room_leave(uuid), public.rb_hoops_room_end(uuid),
    public.rb_hoops_ping(uuid, jsonb) to authenticated;

-- ================================================================ the 10.0 reset (once)
-- Everything starts again for every player, as in 9.4: every item but the OG tag, every unopened case, the collection,
-- trophies and set rewards go; coins 2 500 and keys 5 with the starter cases; level and XP to 0; rank back to Poor;
-- gold keys and wheels to 0; the free spin, scratch card, daily case, hourly keys and top-up are ready again. Everyone,
-- bots too: every leaderboard, stat and trophy counts from now, streaks to 0, quests start again, and the Karting and
-- Hoops records are cleared. Anything in play that holds coins or items ends with no pay (items go back first).
-- Before anything changes, a full copy of every table it touches is kept (rb_bak100_*, readable by nobody but the
-- server), so any player can be put back by hand.
create or replace function public.rb_reset_10() returns jsonb
language plpgsql security definer set search_path to '' as $$
declare n integer; gone integer; cases integer; p record; t text; kept integer := 0;
begin
    if coalesce(public.rb_cfg('reset_100'), 0) <> 0 then raise exception 'rb_already_done'; end if;

    foreach t in array array['profiles', 'rb_items', 'rb_case_stock', 'rb_ach', 'rb_quest_claims', 'rb_config',
                             'rb_seen', 'rb_set_claims', 'rb_case_week', 'rb_ledger', 'rb_hoops_games', 'rb_kart_rooms',
                             'rb_kart_seats', 'rb_kart_ghosts', 'rb_xp_log'] loop
        if to_regclass('public.' || t) is not null and to_regclass('public.rb_bak100_' || replace(t, 'rb_', '')) is null then
            execute format('create table public.%I as select * from public.%I', 'rb_bak100_' || replace(t, 'rb_', ''), t);
            execute format('alter table public.%I enable row level security', 'rb_bak100_' || replace(t, 'rb_', ''));
            execute format('revoke all on public.%I from public, anon, authenticated', 'rb_bak100_' || replace(t, 'rb_', ''));
            kept := kept + 1;
        end if;
    end loop;

    -- anything players have in play ends with no pay; the items it held go back first
    update public.rb_duels set state = 'cancelled', why = 'reset' where state not in ('done', 'cancelled');
    update public.rb_flips set state = 'cancelled', why = 'reset', done_at = now() where state not in ('done', 'cancelled');
    update public.rb_trades set state = 'cancelled', why = 'reset', updated = now() where state not in ('done', 'cancelled');
    update public.rb_golf set state = 'cancelled', why = 'reset', done_at = now() where state not in ('done', 'cancelled');
    update public.rb_golf_parties set state = 'cancelled', done_at = now() where state not in ('done', 'cancelled');
    update public.rb_golf_solo set state = 'quit', done_at = now() where state not in ('done', 'quit');
    update public.rb_wave_duels set state = 'cancelled', why = 'reset', done_at = now() where state not in ('done', 'cancelled');
    update public.rb_wave_runs set state = 'quit', done_at = now() where state not in ('done', 'quit');
    update public.rb_wave_rooms set state = 'cancelled' where state in ('open', 'live');
    update public.rb_kart_rooms set state = 'cancelled' where state in ('open', 'live');
    update public.rb_hoops_games set state = 'left' where state = 'open';
    update public.rb_hoops_rooms set state = 'cancelled', why = 'reset', done_at = now() where state in ('open', 'live');
    if to_regclass('public.rb_c4') is not null then
        execute 'update public.rb_c4 set state = ''done'', paid = 0, updated_at = now() where state <> ''done''';
    end if;
    update public.rb_bg set state = 'cancelled', why = 'reset', done_at = now() where state in ('open', 'live');
    update public.rb_item_swaps set state = 'cancelled', done_at = now() where state = 'open';
    update public.rb_offers set state = 'gone' where state = 'open';
    update public.rb_listings set state = 'cancelled' where state = 'open';
    with gone_e as (delete from public.rb_jackpot_entries e using public.rb_jackpots j
                     where j.id = e.jackpot and j.state not in ('done', 'empty') and e.owner is not null
                       and e.owner in (select id from public.profiles where not bot)
                    returning e.jackpot, e.value)
    update public.rb_jackpots j set total = greatest(0, j.total - s.v)
      from (select jackpot, sum(value) v from gone_e group by jackpot) s where s.jackpot = j.id;
    with gone_b as (delete from public.rb_race_bets b using public.rb_races r
                     where r.id = b.race and r.state <> 'done' and b.owner is not null
                       and b.owner in (select id from public.profiles where not bot)
                    returning b.race, b.amount)
    update public.rb_races r set total = greatest(0, r.total - s.v)
      from (select race, sum(amount) v from gone_b group by race) s where s.race = r.id;
    update public.rb_rounds set open = false, paid = 0 where open;
    update public.rb_mg set open = false, void = true where open;
    update public.rb_items set locked = null where locked is not null;

    -- every player: every item but the OG tag, every case, the collection, trophies, set rewards
    delete from public.rb_items i using public.profiles pr where pr.id = i.owner and not pr.bot and i.item <> 'tag:og';
    get diagnostics gone = row_count;
    delete from public.rb_case_stock s using public.profiles pr where pr.id = s.owner and not pr.bot;
    get diagnostics cases = row_count;
    delete from public.rb_case_week s using public.profiles pr where pr.id = s.owner and not pr.bot;
    delete from public.rb_seen s using public.profiles pr where pr.id = s.owner and not pr.bot;
    delete from public.rb_set_claims s using public.profiles pr where pr.id = s.owner and not pr.bot;
    if to_regclass('public.rb_ach') is not null then
        execute 'delete from public.rb_ach a using public.profiles pr where pr.id = a.owner and not pr.bot';
    end if;
    insert into public.rb_seen (owner, item)
        select owner, item from public.rb_items where item = 'tag:og' on conflict do nothing;

    update public.profiles
       set coins = 2500, keys = 5, coin_min = 0, key_min = 0, day = current_date, day_coins = 0,
           gold_keys = 0, gold_wheels = 0, rig_gold = false, og_coupon_50 = false,
           xp = 0, level = 0, xp_day = null, xp_day_gain = 0, xp_day_src = '{}'::jsonb, xp_hr = null, xp_hr_src = '{}'::jsonb,
           tier_floor = 0, tier_seen = 0, tier_up_on = null, topup_day = null,
           spin_at = null, spin_prize = null, scratch_at = null, daily_at = null, hourly_at = null,
           equip = coalesce(equip, '{}'::jsonb) - 'trophy1' - 'trophy2' - 'trophy3'
     where not bot;
    get diagnostics n = row_count;
    insert into public.rb_ledger (owner, coins, keys, reason, ref)
        select id, 2500, 5, 'gift', '10.0 reset: starter pack' from public.profiles where not bot;
    for p in select id from public.profiles where not bot loop
        perform public.rb_starter_pack(p.id);
        perform public.rb_fix_equip(p.id);
    end loop;

    -- everyone, bots too: boards, stats, trophies, streaks, quests, Karting and Hoops records
    insert into public.rb_config (key, value) values ('board_from', extract(epoch from now())::bigint),
        ('stats_from', extract(epoch from now())::bigint), ('ach_from', extract(epoch from now())::bigint)
    on conflict (key) do update set value = excluded.value;
    update public.profiles set board_min0 = minutes, streak = 0, streak_day = null;
    update public.profiles set bot_cfg = bot_cfg - 'stats' where bot and bot_cfg ? 'stats';
    delete from public.rb_quest_claims;
    delete from public.rb_kart_rooms where state in ('done', 'cancelled');
    delete from public.rb_kart_ghosts;
    delete from public.rb_hoops_games where state <> 'open';

    insert into public.rb_config (key, value) values ('reset_100', extract(epoch from now())::bigint)
    on conflict (key) do update set value = excluded.value;
    return jsonb_build_object('players', n, 'items_removed', gone, 'case_rows_removed', cases, 'tables_backed_up', kept);
end $$;
revoke all on function public.rb_reset_10() from public, anon, authenticated;

do $$
begin
    if coalesce(public.rb_cfg('reset_100'), 0) = 0 then
        raise notice '10.0 reset: %', public.rb_reset_10();
    end if;
end $$;

commit;
