-- ================================================================ Rubenium 5.6: Mini Golf parties (3 or 4 players)
-- Everyone plays their own ball at the same time on the same hole; you see the other balls and where the others are
-- aiming. Empty seats are bots (BOT tag). Bets are between the players only: the best player takes all the bets (5% fee),
-- ties share; bots never take or add coins. Every player also earns mini game coins by strokes (daily limit).
-- 150 seconds a hole. Safe to run again.
begin;
insert into public.rb_config (key, value) values ('party_hole_s', 150), ('party_wait_s', 90) on conflict (key) do nothing;

create table if not exists public.rb_golf_parties (
    id uuid primary key default gen_random_uuid(),
    host uuid not null references public.profiles(id) on delete cascade,
    size integer not null check (size in (3, 4)),
    bet integer not null default 0,
    holes integer[] not null,
    hole integer not null default 1,
    state text not null default 'open' check (state in ('open', 'live', 'done', 'cancelled')),
    hole_at timestamptz,
    at timestamptz not null default now(),
    done_at timestamptz);
create table if not exists public.rb_golf_party_seats (
    party uuid not null references public.rb_golf_parties(id) on delete cascade,
    seat integer not null,
    owner uuid references public.profiles(id) on delete cascade,
    bot_name text,
    skill double precision not null default 0.5,
    strokes integer[] not null,
    pos jsonb,
    holed boolean not null default false,
    plan jsonb,
    aim jsonb,
    aim_at timestamptz,
    seq integer not null default 0,
    last_at timestamptz not null default now(),
    shot jsonb,
    gone boolean not null default false,
    paid integer not null default 0,
    primary key (party, seat));
create unique index if not exists rb_golf_party_seats_owner on public.rb_golf_party_seats (party, owner) where owner is not null;
alter table public.rb_golf_parties enable row level security;
alter table public.rb_golf_party_seats enable row level security;
revoke all on public.rb_golf_parties, public.rb_golf_party_seats from anon, authenticated;

create or replace function public.rb_party_busy(who uuid) returns uuid
language sql stable security definer set search_path to '' as $$
    select p.id from public.rb_golf_parties p join public.rb_golf_party_seats s on s.party = p.id
     where s.owner = who and not s.gone and p.state in ('open', 'live') limit 1 $$;

-- a bot's plan for a hole: how many strokes and how many seconds between them
create or replace function public.rb_party_bot_plan(skill double precision) returns jsonb
language sql volatile set search_path to '' as $$
    select jsonb_build_object('n', greatest(1, least(6, round(2.2 + public.rb_rand() * 3.0 - skill * 1.2)::int)),
                              'every', 4 + public.rb_rand() * 5) $$;

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
    if humans < 2 and g.bet > 0 then                       -- one player with bots: no bet
        perform public.rb_pay(s.owner, g.bet, 0, 'golf_refund', g.id::text)
           from public.rb_golf_party_seats s where s.party = g.id and s.owner is not null;
        update public.rb_golf_parties set bet = 0 where id = g.id;
    end if;
    update public.rb_golf_party_seats set plan = public.rb_party_bot_plan(skill) where party = g.id and owner is null;
    update public.rb_golf_parties set state = 'live', hole = 1, hole_at = now() where id = g.id;
end $$;

-- moves a party on: start after the wait, bots shoot, the next hole, the end and the payout
create or replace function public.rb_party_tick(pid uuid) returns void
language plpgsql security definer set search_path to '' as $$
declare g public.rb_golf_parties%rowtype; s record; done_ boolean; n integer; best integer; winners uuid[]; pot bigint;
        share integer; base integer; pay integer; i integer; total integer; humans integer;
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
    -- is the hole over? every player in (or gone), every bot finished, or the time is up
    done_ := now() > g.hole_at + make_interval(secs => coalesce(public.rb_cfg('party_hole_s'), 150));
    if not done_ then
        done_ := not exists (select 1 from public.rb_golf_party_seats where party = g.id and owner is not null
                               and not gone and not holed)
             and not exists (select 1 from public.rb_golf_party_seats where party = g.id and owner is null
                               and extract(epoch from now() - g.hole_at) < (plan ->> 'n')::int * (plan ->> 'every')::float + 1);
    end if;
    if not done_ then return; end if;
    for s in select * from public.rb_golf_party_seats where party = g.id loop
        n := case when s.owner is null then (s.plan ->> 'n')::int
                  when s.gone or not s.holed then greatest(s.strokes[g.hole], 6) else s.strokes[g.hole] end;
        update public.rb_golf_party_seats set strokes[g.hole] = n, holed = false, pos = null, aim = null, shot = null,
               plan = case when owner is null then public.rb_party_bot_plan(skill) end
         where party = g.id and seat = s.seat;
    end loop;
    if g.hole < array_length(g.holes, 1) then
        update public.rb_golf_parties set hole = g.hole + 1, hole_at = now() where id = g.id;
        return;
    end if;
    -- the end: the best player (fewest strokes) takes the bets; mini game coins for everyone who played to the end
    update public.rb_golf_parties set state = 'done', done_at = now() where id = g.id;
    select min(t) into best from (select (select sum(x) from unnest(strokes) x) t from public.rb_golf_party_seats
                                   where party = g.id and owner is not null and not gone) z;
    select array_agg(owner) into winners from public.rb_golf_party_seats
     where party = g.id and owner is not null and not gone and (select sum(x) from unnest(strokes) x) = best;
    select count(*) into humans from public.rb_golf_party_seats where party = g.id and owner is not null;
    if g.bet > 0 and coalesce(array_length(winners, 1), 0) > 0 then
        pot := g.bet::bigint * humans;
        share := floor(pot * (1 - coalesce(public.rb_cfg('golf_fee'), 0.05)) / array_length(winners, 1))::int;
        for i in 1 .. array_length(winners, 1) loop
            perform public.rb_pay(winners[i], share, 0, 'golf_win', g.id::text);
        end loop;
    end if;
    for s in select * from public.rb_golf_party_seats where party = g.id and owner is not null and not gone loop
        base := 0;
        for i in 1 .. array_length(s.strokes, 1) loop
            base := base + public.rb_golf_solo_pay(s.strokes[i]);
        end loop;
        pay := public.rb_game_pay(s.owner, 'golf_party', base);
        if pay > 0 then perform public.rb_pay(s.owner, pay, 0, 'minigame', 'golf_party'); end if;
        insert into public.rb_rounds (owner, game, bet, secret, open, paid)
            values (s.owner, 'golf_party', g.bet, jsonb_build_object('strokes', s.strokes, 'party', g.id), false, pay);
        update public.rb_golf_party_seats set paid = pay + case when s.owner = any (winners) and g.bet > 0
                                                               then coalesce(share, 0) else 0 end
         where party = g.id and seat = s.seat;
        perform public.rb_notice(s.owner, 'golf_end', jsonb_build_object('party', g.id, 'won', s.owner = any (winners)));
    end loop;
end $$;

create or replace function public.rb_party_json(pid uuid, me uuid) returns jsonb
language sql stable security definer set search_path to '' as $$
    select jsonb_build_object('id', g.id, 'party', true, 'state', g.state, 'size', g.size, 'bet', g.bet, 'holes', to_jsonb(g.holes),
        'hole', g.hole, 'n_holes', array_length(g.holes, 1), 'host', (g.host = me),
        'starts_in', case when g.state = 'open' then greatest(0, extract(epoch from g.at - now()) + coalesce(public.rb_cfg('party_wait_s'), 90)) end,
        'left', case when g.state = 'live' then greatest(0, extract(epoch from g.hole_at - now()) + coalesce(public.rb_cfg('party_hole_s'), 150)) end,
        'me', (select seat from public.rb_golf_party_seats where party = g.id and owner = me),
        'seats', coalesce((select jsonb_agg(jsonb_build_object(
             'seat', s.seat, 'name', coalesce(p.username, s.bot_name), 'bot', s.owner is null, 'mine', s.owner = me,
             'strokes', to_jsonb(s.strokes), 'total', (select sum(x) from unnest(s.strokes) x), 'gone', s.gone, 'paid', s.paid,
             'in', case when s.owner is null then g.state = 'live' and extract(epoch from now() - g.hole_at)
                                                 >= (s.plan ->> 'n')::int * (s.plan ->> 'every')::float
                        else s.holed end,
             'done', case when s.owner is null and g.state = 'live'
                          then least((s.plan ->> 'n')::int, floor(extract(epoch from now() - g.hole_at) / (s.plan ->> 'every')::float)::int)
                          else s.strokes[g.hole] end,
             'n', case when s.owner is null then (s.plan ->> 'n')::int end,
             'pos', s.pos, 'seq', s.seq, 'shot', s.shot,
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
    if public.rb_golf_busy(p.id) or public.rb_party_busy(p.id) is not null then raise exception 'rb_one_lobby'; end if;
    if size not in (3, 4) then raise exception 'rb_bad_choice'; end if;
    bet := coalesce(bet, 0);
    if bet <> 0 and (bet < 10 or bet % 10 <> 0 or bet > public.rb_golf_cap(p.coins)) then raise exception 'rb_bad_bet'; end if;
    hs := public.rb_golf_pick(public.rb_golf_holes_ok(holes));
    perform public.rb_pay(p.id, -bet, 0, 'golf_bet', null);
    insert into public.rb_golf_parties (host, size, bet, holes) values (p.id, size, bet, hs) returning id into gid;
    insert into public.rb_golf_party_seats (party, seat, owner, strokes) values (gid, 0, p.id, array_fill(0, array[array_length(hs, 1)]));
    return public.rb_party_json(gid, p.id);
end $$;

create or replace function public.rb_party_join(pid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; g public.rb_golf_parties%rowtype; k integer;
begin
    perform public.rb_rate(auth.uid(), 'duel', 10);
    perform public.rb_need_feature('golf');
    p := public.rb_lock_me();
    if public.rb_golf_busy(p.id) or public.rb_party_busy(p.id) is not null then raise exception 'rb_one_lobby'; end if;
    select * into g from public.rb_golf_parties where id = pid for update;
    if not found or g.state <> 'open' then raise exception 'rb_duel_gone'; end if;
    if g.bet > p.coins then raise exception 'rb_not_enough'; end if;
    select min(x) into k from generate_series(0, g.size - 1) x
     where not exists (select 1 from public.rb_golf_party_seats where party = g.id and seat = x);
    if k is null then raise exception 'rb_duel_full'; end if;
    perform public.rb_pay(p.id, -g.bet, 0, 'golf_bet', g.id::text);
    insert into public.rb_golf_party_seats (party, seat, owner, strokes) values (g.id, k, p.id, array_fill(0, array[array_length(g.holes, 1)]));
    perform public.rb_notice(g.host, 'golf_yes', jsonb_build_object('from', p.username, 'party', g.id));
    if (select count(*) from public.rb_golf_party_seats where party = g.id) >= g.size then
        perform public.rb_party_start(g.id);
    end if;
    return public.rb_party_json(g.id, p.id);
end $$;

-- the host starts now: bots take the empty seats
create or replace function public.rb_party_go(pid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
begin
    if not exists (select 1 from public.rb_golf_parties where id = pid and host = auth.uid() and state = 'open') then
        raise exception 'rb_bad_choice';
    end if;
    perform public.rb_party_start(pid);
    return public.rb_party_json(pid, auth.uid());
end $$;

create or replace function public.rb_party_leave(pid uuid) returns boolean
language plpgsql security definer set search_path to '' as $$
declare g public.rb_golf_parties%rowtype; me uuid := auth.uid();
begin
    select * into g from public.rb_golf_parties where id = pid for update;
    if not found then return false; end if;
    if g.state = 'open' then
        if g.host = me then                                 -- the host leaves: everyone gets their bet back
            perform public.rb_pay(s.owner, g.bet, 0, 'golf_refund', g.id::text)
               from public.rb_golf_party_seats s where s.party = g.id and s.owner is not null;
            update public.rb_golf_parties set state = 'cancelled', done_at = now() where id = g.id;
        elsif exists (select 1 from public.rb_golf_party_seats where party = g.id and owner = me) then
            perform public.rb_pay(me, g.bet, 0, 'golf_refund', g.id::text);
            delete from public.rb_golf_party_seats where party = g.id and owner = me;
        end if;
    elsif g.state = 'live' then                             -- leaving a live party: the bet stays in the pot
        update public.rb_golf_party_seats set gone = true where party = g.id and owner = me;
        perform public.rb_party_tick(g.id);
    end if;
    return true;
end $$;

create or replace function public.rb_party_state(pid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_party_tick(pid);
    if not exists (select 1 from public.rb_golf_parties where id = pid) then raise exception 'rb_duel_gone'; end if;
    return public.rb_party_json(pid, auth.uid());
end $$;

create or replace function public.rb_party_list() returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); x record;
begin
    for x in select id from public.rb_golf_parties where state = 'open' loop
        perform public.rb_party_tick(x.id);
    end loop;
    return jsonb_build_object('mine', public.rb_party_busy(me),
        'open', coalesce((select jsonb_agg(jsonb_build_object('id', g.id, 'host', p.username, 'size', g.size, 'bet', g.bet,
                    'holes', array_length(g.holes, 1), 'players', (select count(*) from public.rb_golf_party_seats s where s.party = g.id),
                    'starts_in', greatest(0, extract(epoch from g.at - now()) + coalesce(public.rb_cfg('party_wait_s'), 90)))
                    order by g.at) from public.rb_golf_parties g join public.profiles p on p.id = g.host
                   where g.state = 'open'), '[]'::jsonb));
end $$;

create or replace function public.rb_party_shot(pid uuid, n integer, x0 double precision, y0 double precision, ang double precision,
                                                pow double precision, x double precision, y double precision, holed boolean) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); g public.rb_golf_parties%rowtype; s public.rb_golf_party_seats%rowtype; k integer;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_party_tick(pid);
    select * into g from public.rb_golf_parties where id = pid;
    if not found or g.state <> 'live' then raise exception 'rb_duel_gone'; end if;
    select * into s from public.rb_golf_party_seats where party = pid and owner = me for update;
    if not found or s.gone then raise exception 'rb_duel_gone'; end if;
    if n < s.seq or s.holed then return public.rb_party_json(pid, me); end if;      -- already counted
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
    perform public.rb_party_tick(pid);
    return public.rb_party_json(pid, me);
end $$;

create or replace function public.rb_party_aim(pid uuid, a double precision, p double precision) returns void
language sql security definer set search_path to '' as $$
    update public.rb_golf_party_seats set aim = jsonb_build_array(round(a::numeric, 3), round(p::numeric, 3)), aim_at = now()
     where party = pid and owner = auth.uid() and not gone and not holed $$;

-- a duel lobby can't be opened while in a party (and the other way round)
create or replace function public.rb_golf_busy(who uuid) returns boolean
language sql stable security definer set search_path to '' as $$
    select exists (select 1 from public.rb_golf g where (g.a = who and g.state in ('open', 'asked', 'live'))
                                                     or (g.b = who and g.state = 'live'))
        or exists (select 1 from public.rb_golf_parties p join public.rb_golf_party_seats s on s.party = p.id
                    where s.owner = who and not s.gone and p.state in ('open', 'live')) $$;

revoke all on function public.rb_party_busy(uuid), public.rb_party_bot_plan(double precision), public.rb_party_start(uuid),
    public.rb_party_tick(uuid), public.rb_party_json(uuid, uuid) from public, anon, authenticated;
revoke all on function public.rb_party_create(integer, integer, integer), public.rb_party_join(uuid), public.rb_party_go(uuid),
    public.rb_party_leave(uuid), public.rb_party_state(uuid), public.rb_party_list(),
    public.rb_party_shot(uuid, integer, double precision, double precision, double precision, double precision, double precision, double precision, boolean),
    public.rb_party_aim(uuid, double precision, double precision) from public, anon;
grant execute on function public.rb_party_create(integer, integer, integer), public.rb_party_join(uuid), public.rb_party_go(uuid),
    public.rb_party_leave(uuid), public.rb_party_state(uuid), public.rb_party_list(),
    public.rb_party_shot(uuid, integer, double precision, double precision, double precision, double precision, double precision, double precision, boolean),
    public.rb_party_aim(uuid, double precision, double precision) to authenticated;
commit;
