-- ================================================================ Rubenium 5.8: Mini Golf online, turn by turn
-- One kind of online match: 2, 3 or 4 players (bots take empty seats when the host starts or after 90 s). Players shoot one
-- at a time in seat order; 25 seconds a shot (missing the time counts a stroke). Bots take their turn after a short
-- think. A hole ends when everyone is in (6 strokes at most). Safe to run again.
begin;
alter table public.rb_golf_parties drop constraint if exists rb_golf_parties_size_check;
alter table public.rb_golf_parties add constraint rb_golf_parties_size_check check (size in (2, 3, 4));
alter table public.rb_golf_parties add column if not exists turn integer;
alter table public.rb_golf_parties add column if not exists turn_at timestamptz;
insert into public.rb_config (key, value) values ('party_turn_s', 25) on conflict (key) do nothing;

-- the next seat to play on this hole (after `after`, in seat order), or null when everyone is in
create or replace function public.rb_party_next(pid uuid, after integer) returns integer
language sql stable security definer set search_path to '' as $$
    select seat from public.rb_golf_party_seats
     where party = pid and not holed and not gone
     order by (seat <= coalesce(after, -1)), seat limit 1 $$;

-- a bot's shot: its ball moves a part of the way to the cup; it is in after its planned number of strokes
create or replace function public.rb_party_bot_shot(pid uuid, k integer) returns void
language plpgsql security definer set search_path to '' as $$
declare g public.rb_golf_parties%rowtype; s public.rb_golf_party_seats%rowtype; n integer; want integer;
begin
    select * into g from public.rb_golf_parties where id = pid;
    select * into s from public.rb_golf_party_seats where party = pid and seat = k for update;
    n := s.strokes[g.hole] + 1;
    want := coalesce((s.plan ->> 'n')::int, 3);
    update public.rb_golf_party_seats set strokes[g.hole] = n, seq = seq + 1, last_at = now(),
           holed = n >= want or n >= 6,
           pos = case when n >= want or n >= 6 then null
                      else jsonb_build_array(round((n::numeric / want), 3), round((0.6 + public.rb_rand() * 0.8)::numeric, 3)) end
     where party = pid and seat = k;
end $$;

create or replace function public.rb_party_start(pid uuid) returns void
language plpgsql security definer set search_path to '' as $$
declare g public.rb_golf_parties%rowtype; k integer; names text[]; humans integer;
begin
    select * into g from public.rb_golf_parties where id = pid for update;
    if not found or g.state <> 'open' then return; end if;
    select array_agg(b.name order by random()) into names from public.rb_flip_bots() b;
    for k in 0 .. g.size - 1 loop
        if not exists (select 1 from public.rb_golf_party_seats where party = g.id and seat = k) then
            insert into public.rb_golf_party_seats (party, seat, owner, bot_name, skill, strokes)
                values (g.id, k, null, names[k + 1], public.rb_rand(), array_fill(0, array[array_length(g.holes, 1)]));
        end if;
    end loop;
    select count(*) into humans from public.rb_golf_party_seats where party = g.id and owner is not null;
    if humans < 2 and g.bet > 0 then
        perform public.rb_pay(s.owner, g.bet, 0, 'golf_refund', g.id::text)
           from public.rb_golf_party_seats s where s.party = g.id and s.owner is not null;
        update public.rb_golf_parties set bet = 0 where id = g.id;
    end if;
    update public.rb_golf_party_seats set plan = public.rb_party_bot_plan(skill) where party = g.id and owner is null;
    update public.rb_golf_parties set state = 'live', hole = 1, hole_at = now(), turn = 0, turn_at = now() + interval '2 seconds'
     where id = g.id;
end $$;

create or replace function public.rb_party_tick(pid uuid) returns void
language plpgsql security definer set search_path to '' as $$
declare g public.rb_golf_parties%rowtype; s record; cur public.rb_golf_party_seats%rowtype; nxt integer; best integer;
        winners uuid[]; pot bigint; share integer; base integer; pay integer; i integer; humans integer; guard integer := 0;
begin
    select * into g from public.rb_golf_parties where id = pid for update;
    if not found then return; end if;
    if g.state = 'open' then
        if not exists (select 1 from public.rb_golf_party_seats where party = g.id and owner is not null and not gone) then
            update public.rb_golf_parties set state = 'cancelled', done_at = now() where id = g.id;
        elsif now() > g.at + make_interval(secs => coalesce(public.rb_cfg('party_wait_s'), 90)) then
            perform public.rb_party_start(g.id);
        end if;
        return;
    end if;
    if g.state <> 'live' then return; end if;
    if not exists (select 1 from public.rb_golf_party_seats where party = g.id and owner is not null and not gone) then
        update public.rb_golf_parties set state = 'cancelled', done_at = now() where id = g.id;
        return;
    end if;
    loop                                                   -- play out bots and missed turns
        guard := guard + 1;
        exit when guard > 40;
        select * into g from public.rb_golf_parties where id = pid;
        select * into cur from public.rb_golf_party_seats where party = pid and seat = g.turn;
        if g.turn is null or not found or cur.holed or cur.gone then
            nxt := public.rb_party_next(pid, g.turn);
        elsif cur.owner is null and now() >= g.turn_at + make_interval(secs => 1.5 + public.rb_rand() * 1.5) then
            perform public.rb_party_bot_shot(pid, cur.seat);
            nxt := public.rb_party_next(pid, cur.seat);
        elsif cur.owner is not null and now() >= g.turn_at + make_interval(secs => coalesce(public.rb_cfg('party_turn_s'), 25)) then
            update public.rb_golf_party_seats set strokes[g.hole] = strokes[g.hole] + 1, seq = seq + 1,
                   holed = strokes[g.hole] + 1 >= 6, pos = case when strokes[g.hole] + 1 >= 6 then null else pos end
             where party = pid and seat = cur.seat;                           -- out of time: a stroke
            nxt := public.rb_party_next(pid, cur.seat);
        else
            exit;                                          -- waiting for this player
        end if;
        if nxt is not null then
            update public.rb_golf_parties set turn = nxt, turn_at = now() where id = pid;
            continue;
        end if;
        -- everyone is in: the next hole, or the end
        update public.rb_golf_party_seats set holed = false, pos = null, aim = null, shot = null,
               strokes[g.hole] = case when gone then greatest(strokes[g.hole], 6) else strokes[g.hole] end,
               plan = case when owner is null then public.rb_party_bot_plan(skill) end
         where party = pid;
        if g.hole < array_length(g.holes, 1) then
            update public.rb_golf_parties set hole = g.hole + 1, hole_at = now(),
                   turn = public.rb_party_next(pid, -1), turn_at = now() + interval '2 seconds' where id = pid;
            exit;
        end if;
        update public.rb_golf_parties set state = 'done', done_at = now(), turn = null where id = pid;
        select min(t) into best from (select (select sum(x) from unnest(strokes) x) t from public.rb_golf_party_seats
                                       where party = pid and owner is not null and not gone) z;
        select array_agg(owner) into winners from public.rb_golf_party_seats
         where party = pid and owner is not null and not gone and (select sum(x) from unnest(strokes) x) = best;
        select count(*) into humans from public.rb_golf_party_seats where party = pid and owner is not null;
        if g.bet > 0 and coalesce(array_length(winners, 1), 0) > 0 then
            pot := g.bet::bigint * humans;
            share := floor(pot * (1 - coalesce(public.rb_cfg('golf_fee'), 0.05)) / array_length(winners, 1))::int;
            for i in 1 .. array_length(winners, 1) loop
                perform public.rb_pay(winners[i], share, 0, 'golf_win', pid::text);
            end loop;
        end if;
        for s in select * from public.rb_golf_party_seats where party = pid and owner is not null and not gone loop
            base := 0;
            for i in 1 .. array_length(s.strokes, 1) loop
                base := base + public.rb_golf_solo_pay(s.strokes[i]);
            end loop;
            pay := public.rb_game_pay(s.owner, 'golf_party', base);
            if pay > 0 then perform public.rb_pay(s.owner, pay, 0, 'minigame', 'golf_party'); end if;
            insert into public.rb_rounds (owner, game, bet, secret, open, paid)
                values (s.owner, 'golf_party', g.bet, jsonb_build_object('strokes', s.strokes, 'party', pid), false, pay);
            update public.rb_golf_party_seats set paid = pay + case when s.owner = any (winners) and g.bet > 0
                                                                   then coalesce(share, 0) else 0 end
             where party = pid and seat = s.seat;
            perform public.rb_notice(s.owner, 'golf_end', jsonb_build_object('party', pid, 'won', s.owner = any (winners)));
        end loop;
        exit;
    end loop;
end $$;

create or replace function public.rb_party_json(pid uuid, me uuid) returns jsonb
language sql stable security definer set search_path to '' as $$
    select jsonb_build_object('id', g.id, 'party', true, 'state', g.state, 'size', g.size, 'bet', g.bet, 'holes', to_jsonb(g.holes),
        'hole', g.hole, 'n_holes', array_length(g.holes, 1), 'host', (g.host = me), 'now', extract(epoch from now()),
        'starts_in', case when g.state = 'open' then greatest(0, extract(epoch from g.at - now()) + coalesce(public.rb_cfg('party_wait_s'), 90)) end,
        'turn', g.turn,
        'turn_left', case when g.state = 'live' then greatest(0, extract(epoch from g.turn_at - now()) + coalesce(public.rb_cfg('party_turn_s'), 25)) end,
        'me', (select seat from public.rb_golf_party_seats where party = g.id and owner = me),
        'seats', coalesce((select jsonb_agg(jsonb_build_object(
             'seat', s.seat, 'name', coalesce(p.username, s.bot_name), 'bot', s.owner is null, 'mine', s.owner = me,
             'strokes', to_jsonb(s.strokes), 'total', (select sum(x) from unnest(s.strokes) x), 'gone', s.gone, 'paid', s.paid,
             'in', s.holed, 'now', s.strokes[g.hole], 'pos', s.pos, 'seq', s.seq, 'shot', s.shot,
             'aim', case when s.aim_at > now() - interval '2 seconds' then s.aim end)
             order by s.seat) from public.rb_golf_party_seats s left join public.profiles p on p.id = s.owner
             where s.party = g.id), '[]'::jsonb))
      from public.rb_golf_parties g where g.id = pid $$;

create or replace function public.rb_party_create(size integer, bet integer, holes integer) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; gid uuid; hs integer[];
begin
    perform public.rb_rate(auth.uid(), 'duel', 10);
    perform public.rb_need_feature('golf');
    p := public.rb_lock_me();
    if public.rb_golf_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    if size not in (2, 3, 4) then raise exception 'rb_bad_choice'; end if;
    bet := coalesce(bet, 0);
    if bet <> 0 and (bet < 10 or bet % 10 <> 0 or bet > public.rb_golf_cap(p.coins)) then raise exception 'rb_bad_bet'; end if;
    hs := public.rb_golf_pick(public.rb_golf_holes_ok(holes));
    perform public.rb_pay(p.id, -bet, 0, 'golf_bet', null);
    insert into public.rb_golf_parties (host, size, bet, holes) values (p.id, size, bet, hs) returning id into gid;
    insert into public.rb_golf_party_seats (party, seat, owner, strokes) values (gid, 0, p.id, array_fill(0, array[array_length(hs, 1)]));
    return public.rb_party_json(gid, p.id);
end $$;

create or replace function public.rb_party_shot(pid uuid, n integer, x0 double precision, y0 double precision, ang double precision,
                                                pow double precision, x double precision, y double precision, holed boolean) returns jsonb
language plpgsql security definer set search_path to '' as $$
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
    -- the turn passes once the ball has rolled (the others watch it first)
    update public.rb_golf_parties set turn = coalesce(nxt, turn), turn_at = now() + interval '3 seconds' where id = pid;
    perform public.rb_party_tick(pid);
    return public.rb_party_json(pid, me);
end $$;

-- 5.8: the online list also says how many seats there are
create or replace function public.rb_party_list() returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); x record;
begin
    for x in select id from public.rb_golf_parties where state in ('open', 'live') and at > now() - interval '3 hours' loop
        perform public.rb_party_tick(x.id);
    end loop;
    return jsonb_build_object('mine', public.rb_party_busy(me),
        'open', coalesce((select jsonb_agg(jsonb_build_object('id', g.id, 'host', p.username, 'size', g.size, 'bet', g.bet,
                    'holes', array_length(g.holes, 1), 'players', (select count(*) from public.rb_golf_party_seats s where s.party = g.id))
                    order by g.at) from public.rb_golf_parties g join public.profiles p on p.id = g.host
                   where g.state = 'open'), '[]'::jsonb));
end $$;

revoke all on function public.rb_party_next(uuid, integer), public.rb_party_bot_shot(uuid, integer) from public, anon, authenticated;
commit;
