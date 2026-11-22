-- 6.3: the arena. Jackpot and Horse Racing take turns: one event, then 15 minutes, then the other one.
-- Each event opens with a 2-minute clock; the first player who joins starts a fresh 2 minutes. When the clock runs out,
-- bots take the empty seats and it plays, with or without players (no more waiting for somebody).
-- Horse Racing: 5 horses, one bettor per horse. Your chance to win is your share of all the money on the horses.
-- The winner gets their bet back plus 80% of everybody else's bets (bots' too).

insert into public.rb_features (name, parent, locked) values ('horses', 'online', false) on conflict do nothing;
insert into public.rb_config (key, value) values ('arena_gap_s', '900'), ('race_open_s', '120'), ('race_min_bet', '100'),
       ('race_share', '0.8') on conflict (key) do nothing;

create table if not exists public.rb_arena (
    id integer primary key default 1 check (id = 1),
    next_kind text not null default 'race',
    next_at timestamptz,
    cur_kind text,
    cur_id uuid,
    at timestamptz not null default now());
alter table public.rb_arena enable row level security;

create table if not exists public.rb_races (
    id uuid primary key default gen_random_uuid(),
    opened_at timestamptz not null default now(),
    state text not null default 'open',             -- open, live, done
    lock_at timestamptz not null,
    start_at timestamptz,                           -- the gun (3, 2, 1 before it)
    done_at timestamptz,                            -- everybody is past the line: paid
    map text not null,                              -- desert, forest, snow
    seed bigint not null,
    winner integer,
    total bigint not null default 0);
alter table public.rb_races enable row level security;

create table if not exists public.rb_race_bets (
    id uuid primary key default gen_random_uuid(),
    race uuid not null references public.rb_races (id) on delete cascade,
    lane integer not null check (lane between 0 and 4),
    owner uuid,
    bot_name text,
    amount bigint not null check (amount > 0),
    at timestamptz not null default now(),
    paid bigint not null default 0,
    unique (race, lane));
create unique index if not exists rb_race_bets_one_each on public.rb_race_bets (race, owner) where owner is not null;
alter table public.rb_race_bets enable row level security;

-- ------------------------------------------------------------------ races
create or replace function public.rb_race_make() returns uuid language plpgsql security definer set search_path = '' as $f$
declare nid uuid;
begin
    insert into public.rb_races (lock_at, map, seed)
        values (now() + make_interval(secs => coalesce(public.rb_cfg('race_open_s'), 120)),
                (array['desert', 'forest', 'snow'])[1 + floor(public.rb_rand() * 3)::int],
                floor(public.rb_rand() * 2000000000)::bigint)
        returning id into nid;
    return nid;
end $f$;

create or replace function public.rb_race_advance(rid uuid) returns void language plpgsql security definer set search_path = '' as $f$
declare r public.rb_races%rowtype; n integer; avg_ bigint; names text[]; k integer; lane_ integer; tgt bigint; luck double precision;
        tot bigint; roll double precision; acc bigint := 0; b record; share double precision; pay bigint;
begin
    select * into r from public.rb_races where id = rid for update;
    if not found then return; end if;
    if r.state = 'open' and now() >= r.lock_at then
        select count(*), coalesce(avg(amount), 0)::bigint into n, avg_ from public.rb_race_bets where race = r.id;
        if n = 0 then avg_ := 1000 + floor(public.rb_rand() * 9000)::bigint; end if;   -- bots race on their own
        select array_agg(x.name order by random()) into names from public.rb_flip_bots() x;
        k := 0;
        for lane_ in 0 .. 4 loop
            continue when exists (select 1 from public.rb_race_bets where race = r.id and lane = lane_);
            k := k + 1;
            luck := public.rb_rand();
            tgt := case when luck < 0.10 then avg_ * (0.10 + 0.25 * public.rb_rand())
                        when luck < 0.20 then avg_ * (1.4 + 1.6 * public.rb_rand())
                        else avg_ * (0.45 + 0.75 * public.rb_rand()) end;
            tgt := greatest(100, round(tgt / 10.0) * 10);
            insert into public.rb_race_bets (race, lane, owner, bot_name, amount, at)
                values (r.id, lane_, null, coalesce(names[k], 'Bot ' || k), tgt, r.lock_at + make_interval(secs => 0.5 * k));
        end loop;
        select sum(amount) into tot from public.rb_race_bets where race = r.id;
        roll := public.rb_rand() * tot;                  -- the winner: each horse's share of the money
        for b in select lane, amount from public.rb_race_bets where race = r.id order by lane loop
            acc := acc + b.amount;
            if roll < acc then r.winner := b.lane; exit; end if;
        end loop;
        if r.winner is null then r.winner := 4; end if;
        update public.rb_races set state = 'live', total = tot, winner = r.winner,
               start_at = r.lock_at + interval '7 seconds', done_at = r.lock_at + interval '34 seconds' where id = r.id;
        return;
    end if;
    if r.state = 'live' and now() >= r.done_at then
        share := coalesce(public.rb_cfg('race_share'), 0.8);
        for b in select * from public.rb_race_bets where race = r.id and owner is not null loop
            pay := case when b.lane = r.winner then b.amount + floor(share * (r.total - b.amount))::bigint else 0 end;
            if pay > 0 then
                perform public.rb_pay(b.owner, least(pay, 2000000000)::int, 0, 'race_win', r.id::text);
                update public.rb_race_bets set paid = pay where id = b.id;
                perform public.rb_notice(b.owner, 'race_won', jsonb_build_object('race', r.id, 'won', pay));
            end if;
            insert into public.rb_rounds (owner, game, bet, secret, open, paid)
                values (b.owner, 'horses', least(b.amount, 2000000000)::int,
                        jsonb_build_object('race', r.id, 'lane', b.lane, 'winner', r.winner, 'total', r.total), false,
                        least(pay, 2000000000)::int);
        end loop;
        update public.rb_races set state = 'done' where id = r.id;
    end if;
end $f$;

create or replace function public.rb_race_json(r public.rb_races, me uuid) returns jsonb language sql stable security definer
set search_path = '' as $f$
    select jsonb_build_object(
        'id', r.id, 'state', r.state, 'now', extract(epoch from now()), 'map', r.map, 'seed', r.seed,
        'opened_at', extract(epoch from r.opened_at), 'lock_at', extract(epoch from r.lock_at),
        'start_at', extract(epoch from r.start_at), 'done_at', extract(epoch from r.done_at),
        'winner', case when r.state <> 'open' then r.winner end,
        'share', coalesce(public.rb_cfg('race_share'), 0.8),
        'min_bet', coalesce(public.rb_cfg('race_min_bet'), 100)::bigint,
        'max_bet', (select least(p.coins, public.rb_bet_cap(p.coins)) from public.profiles p where p.id = me),
        'total', (select coalesce(sum(amount), 0) from public.rb_race_bets b where b.race = r.id and b.at <= now()),
        'bets', coalesce((select jsonb_agg(jsonb_build_object(
                     'lane', b.lane, 'name', coalesce(p.username, b.bot_name), 'bot', b.owner is null, 'me', b.owner = me,
                     'amount', b.amount, 'paid', b.paid) order by b.lane)
                   from public.rb_race_bets b left join public.profiles p on p.id = b.owner
                  where b.race = r.id and b.at <= now()), '[]'::jsonb),
        'mine', (select lane from public.rb_race_bets b where b.race = r.id and b.owner = me),
        'my_paid', (select paid from public.rb_race_bets b where b.race = r.id and b.owner = me)) $f$;

-- ------------------------------------------------------------------ jackpot pieces
create or replace function public.rb_arena_new_jackpot() returns uuid language plpgsql security definer set search_path = '' as $f$
declare o double precision := coalesce(public.rb_cfg('jackpot_open_s'), 120); nid uuid;
begin
    insert into public.rb_jackpots (slot, lock_at, spin_at, result_at, pick_until)
        values (date_trunc('second', now()), now() + make_interval(secs => o), now() + make_interval(secs => o + 12),
                now() + make_interval(secs => o + 22), now() + make_interval(secs => o + 142))
        returning id into nid;
    return nid;
end $f$;

-- ------------------------------------------------------------------ the arena
create or replace function public.rb_arena_tick() returns void language plpgsql security definer set search_path = '' as $f$
declare a public.rb_arena%rowtype; st text; fin timestamptz; nid uuid; gap double precision := coalesce(public.rb_cfg('arena_gap_s'), 900);
begin
    insert into public.rb_arena (id) values (1) on conflict do nothing;
    select * into a from public.rb_arena where id = 1 for update;
    if a.cur_id is not null then
        if a.cur_kind = 'jackpot' then
            perform public.rb_jackpot_advance(a.cur_id);
            select state into st from public.rb_jackpots where id = a.cur_id;
            if st is null or st in ('done', 'empty') then
                update public.rb_arena set cur_id = null, cur_kind = null, next_at = now() + make_interval(secs => gap), at = now()
                 where id = 1;
            end if;
        else
            perform public.rb_race_advance(a.cur_id);
            select state, done_at into st, fin from public.rb_races where id = a.cur_id;
            if st is null or st = 'done' then
                update public.rb_arena set cur_id = null, cur_kind = null,
                       next_at = coalesce(fin, now()) + make_interval(secs => gap), at = now() where id = 1;
            end if;
        end if;
        return;
    end if;
    if a.next_at is null or now() >= a.next_at then
        if a.next_kind = 'jackpot' then nid := public.rb_arena_new_jackpot(); else nid := public.rb_race_make(); end if;
        update public.rb_arena set cur_kind = a.next_kind, cur_id = nid, next_at = null, at = now(),
               next_kind = case when a.next_kind = 'jackpot' then 'race' else 'jackpot' end where id = 1;
    end if;
end $f$;

-- when the next event of this kind opens (seconds since 1970); "now" if it is open
create or replace function public.rb_arena_next(kind text) returns double precision language plpgsql stable security definer
set search_path = '' as $f$
declare a public.rb_arena%rowtype; gap double precision := coalesce(public.rb_cfg('arena_gap_s'), 900); fin timestamptz;
begin
    select * into a from public.rb_arena where id = 1;
    if not found then return extract(epoch from now()); end if;
    if a.cur_id is not null then
        if a.cur_kind = kind then return extract(epoch from now()); end if;
        if a.cur_kind = 'jackpot' then
            select case when state = 'picking' then pick_until when state = 'open' then lock_at + interval '50 seconds'
                        else result_at + interval '30 seconds' end into fin from public.rb_jackpots where id = a.cur_id;
        else
            select coalesce(done_at, lock_at + interval '34 seconds') into fin from public.rb_races where id = a.cur_id;
        end if;
        return extract(epoch from coalesce(fin, now()) + make_interval(secs => gap));
    end if;
    if a.next_kind = kind then return extract(epoch from coalesce(a.next_at, now())); end if;
    return extract(epoch from coalesce(a.next_at, now())
                   + make_interval(secs => (case when a.next_kind = 'jackpot' then 175 else 155 end) + gap));
end $f$;

-- ------------------------------------------------------------------ player calls
create or replace function public.rb_race_state() returns jsonb language plpgsql security definer set search_path = '' as $f$
declare me uuid := auth.uid(); a public.rb_arena%rowtype; r public.rb_races%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_arena_tick();
    select * into a from public.rb_arena where id = 1;
    if a.cur_kind = 'race' then
        select * into r from public.rb_races where id = a.cur_id;
        if found then
            return public.rb_race_json(r, me) || jsonb_build_object('feature', public.rb_feature_on('horses'));
        end if;
    end if;
    select * into r from public.rb_races order by opened_at desc limit 1;
    if found and r.state = 'done' and now() < r.done_at + interval '25 seconds' then     -- the result stays a moment
        return public.rb_race_json(r, me) || jsonb_build_object('feature', public.rb_feature_on('horses'));
    end if;
    return jsonb_build_object('state', 'closed', 'now', extract(epoch from now()), 'next_at', public.rb_arena_next('race'),
                              'feature', public.rb_feature_on('horses'),
                              'last', case when r.id is not null then public.rb_race_json(r, me) end);
end $f$;

create or replace function public.rb_race_join(lane integer, amount bigint, req text) returns jsonb language plpgsql
security definer set search_path = '' as $f$
declare p public.profiles%rowtype; res jsonb; a public.rb_arena%rowtype; r public.rb_races%rowtype; humans integer;
begin
    perform public.rb_need_feature('horses');
    perform public.rb_rate(auth.uid(), 'race', 10);
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    perform public.rb_arena_tick();
    select * into a from public.rb_arena where id = 1;
    if a.cur_kind is distinct from 'race' then raise exception 'rb_race_closed'; end if;
    select * into r from public.rb_races where id = a.cur_id for update;
    if not found or r.state <> 'open' or now() >= r.lock_at then raise exception 'rb_race_closed'; end if;
    if exists (select 1 from public.rb_game_locks l where l.owner = p.id and l.game in ('horses', '*') and l.until > now()) then
        raise exception 'rb_game_locked';
    end if;
    if lane is null or lane not between 0 and 4 then raise exception 'rb_bad_choice'; end if;
    if exists (select 1 from public.rb_race_bets b where b.race = r.id and b.owner = p.id) then raise exception 'rb_race_in'; end if;
    if exists (select 1 from public.rb_race_bets b where b.race = r.id and b.lane = rb_race_join.lane) then
        raise exception 'rb_race_taken';
    end if;
    if amount is null or amount < coalesce(public.rb_cfg('race_min_bet'), 100) or amount > p.coins
       or amount > public.rb_bet_cap(p.coins) then
        raise exception 'rb_bad_bet';
    end if;
    select count(*) into humans from public.rb_race_bets b where b.race = r.id and b.owner is not null;
    perform public.rb_pay(p.id, -amount::int, 0, 'race_bet', r.id::text);
    insert into public.rb_race_bets (race, lane, owner, amount) values (r.id, rb_race_join.lane, p.id, amount);
    if humans = 0 then                               -- the first player starts a fresh 2 minutes
        update public.rb_races set lock_at = now() + make_interval(secs => coalesce(public.rb_cfg('race_open_s'), 120))
         where id = r.id;
    end if;
    select * into r from public.rb_races where id = r.id;
    return public.rb_remember(p.id, req, public.rb_race_json(r, p.id));
end $f$;

revoke all on function public.rb_race_make(), public.rb_race_advance(uuid), public.rb_race_json(public.rb_races, uuid),
    public.rb_arena_new_jackpot(), public.rb_arena_tick(), public.rb_arena_next(text) from public, anon, authenticated;
revoke all on function public.rb_race_state(), public.rb_race_join(integer, bigint, text) from public, anon;
grant execute on function public.rb_race_state(), public.rb_race_join(integer, bigint, text) to authenticated;

-- ------------------------------------------------------------------ the Jackpot joins the arena
-- rb_jackpot_make: the arena's jackpot (or the last one). The arena opens them now, not the 15-minute slots.
create or replace function public.rb_jackpot_make(s timestamp with time zone) returns public.rb_jackpots
language plpgsql security definer set search_path = '' as $f$
declare j public.rb_jackpots; a public.rb_arena%rowtype;
begin
    perform public.rb_arena_tick();
    select * into a from public.rb_arena where id = 1;
    if a.cur_kind = 'jackpot' then
        select * into j from public.rb_jackpots where id = a.cur_id;
        if found then return j; end if;
    end if;
    select * into j from public.rb_jackpots order by slot desc limit 1;
    return j;
end $f$;
revoke all on function public.rb_jackpot_make(timestamp with time zone) from public, anon, authenticated;

create or replace function public.rb_jackpot_state() returns jsonb language plpgsql security definer set search_path = '' as $f$
declare me uuid := auth.uid(); cur public.rb_jackpots%rowtype; j public.rb_jackpots%rowtype; mine public.rb_jackpots%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    cur := public.rb_jackpot_make(now());                 -- the arena first (it moves the current one on)
    for j in select * from public.rb_jackpots where state in ('open', 'locked', 'picking') and id is distinct from cur.id
              order by slot loop
        perform public.rb_jackpot_advance(j.id);
    end loop;
    select jj.* into mine from public.rb_jackpots jj join public.rb_jackpot_entries e on e.jackpot = jj.id and e.owner = me
     where jj.state in ('locked', 'picking') or (jj.state = 'done' and jj.result_at > now() - interval '20 seconds')
     order by jj.slot desc limit 1;
    if found then
        return public.rb_jackpot_json(mine, me) || jsonb_build_object('feature', public.rb_feature_on('jackpot'));
    end if;
    select * into cur from public.rb_jackpots where id = cur.id;
    if cur.id is null or cur.state in ('empty', 'done') and now() > cur.result_at + interval '15 seconds'
       or cur.state = 'empty' then
        return jsonb_build_object('state', 'closed', 'now', extract(epoch from now()),
                                  'next_at', public.rb_arena_next('jackpot'),
                                  'feature', public.rb_feature_on('jackpot'),
                                  'last', case when cur.id is not null then public.rb_jackpot_json(cur, me) end);
    end if;
    return public.rb_jackpot_json(cur, me) || jsonb_build_object('feature', public.rb_feature_on('jackpot'));
end $f$;

-- nobody joined: the bots play it on their own (it used to end empty)
do $$ declare src text; m text := E'        if n = 0 then\n            update public.rb_jackpots set state = ''empty'' where id = j.id;\n            return;\n        end if;';
begin
    src := pg_get_functiondef('public.rb_jackpot_advance(uuid)'::regprocedure);
    if position(m in src) = 0 then raise exception 'jackpot advance marker'; end if;
    execute replace(src, m, E'        if n = 0 then                                    -- 6.3: bots play it on their own\n            avg_ := 1500 + floor(public.rb_rand() * 8500)::bigint;\n        end if;');
end $$;

-- the jackpot that was waiting for a player becomes the arena's current event (2 minutes from now)
update public.rb_jackpots set lock_at = now() + interval '120 seconds', spin_at = now() + interval '132 seconds',
       result_at = now() + interval '142 seconds', pick_until = now() + interval '262 seconds'
 where state = 'open' and lock_at > slot + interval '1 day';
insert into public.rb_arena (id, next_kind, cur_kind, cur_id)
    select 1, 'race', 'jackpot', (select id from public.rb_jackpots where state = 'open' order by slot desc limit 1)
on conflict (id) do nothing;
