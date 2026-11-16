-- Rubenium 2.4: admin undo, password help, messages, login streak, leaderboards, collection sets,
-- scratch card, Memory, new Beat Tap, duels, 2-hour game limits, badge prices, backups, update lock.
-- Run once in the Supabase SQL Editor after 009. Safe to run twice. Nobody is reset.

-- ================================================================ settings and new columns
insert into public.rb_config (key, value) values
    ('game_window_cap', 150),        -- coins one mini game can pay in 2 hours
    ('game_full_rounds', 6),         -- full pay for the first 6 rounds of a game in 2 hours, then half, then a quarter
    ('scratch_hours', 12), ('min_build', 0), ('msg_per_min', 20), ('duel_fee', 0.05), ('duel_max_bet', 5000),
    ('buy_mult_standard', 4), ('buy_mult_rare', 5), ('buy_mult_special', 6), ('buy_mult_epic', 8)
on conflict (key) do nothing;

alter table public.profiles add column if not exists build bigint not null default 0;
alter table public.profiles add column if not exists scratch_at timestamptz;
alter table public.profiles add column if not exists streak integer not null default 0;
alter table public.profiles add column if not exists streak_day date;
alter table public.profiles add column if not exists backup jsonb;
alter table public.profiles add column if not exists backup_at timestamptz;

alter table public.rb_audit add column if not exists undone_at timestamptz;
alter table public.rb_audit add column if not exists undone_by uuid;
alter table public.rb_trades add column if not exists undone_at timestamptz;
alter table public.rb_listings add column if not exists undone_at timestamptz;
alter table public.rb_mini add column if not exists kind text not null default 'tap';
alter table public.rb_mini add column if not exists duel uuid;
alter table public.rb_mini add column if not exists max_score integer not null default 0;
alter table public.rb_park add column if not exists duel uuid;

-- ================================================================ badge prices: what they are really worth
-- Basic and Painted badges can be bought (Shiny too, for a lot); Titanium, Gold and Mythic never.
update public.rb_catalog c set price = null where c.kind = 'badge' and (c.cls >= 3 or c.rarity = 'exotic');
update public.rb_catalog c
   set price = (round(c.value * public.rb_cfg('buy_mult_' || c.rarity) * (case c.cls when 2 then 1.5 else 1 end) / 50) * 50)::int
 where c.kind = 'badge' and c.cls in (0, 1, 2) and c.rarity <> 'exotic';

-- ================================================================ the account: lock, update check, state
create or replace function public.rb_lock_me() returns public.profiles
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype;
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    select * into p from public.profiles where id = auth.uid() for update;
    if not found then raise exception 'rb_no_profile'; end if;
    if p.banned then raise exception 'rb_banned'; end if;
    if public.rb_cfg('app_locked') > 0 and not p.admin then raise exception 'rb_app_locked'; end if;
    if p.build < public.rb_cfg('min_build') and not p.admin then raise exception 'rb_update_needed'; end if;
    return p;
end $$;

-- the app says hello with its PC and its version. Old versions are told to update.
create or replace function public.rb_hello2(pc text, build bigint) returns json
language plpgsql security definer set search_path = '' as $$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_hello(pc);
    update public.profiles set build = coalesce(rb_hello2.build, 0) where id = auth.uid();
    perform public.rb_fix_equip(auth.uid());
    return json_build_object('min_build', public.rb_cfg('min_build')::bigint,
                             'update', coalesce(build, 0) < public.rb_cfg('min_build'));
end $$;

create or replace function public.rb_state() returns json
language plpgsql stable security definer set search_path = '' as $$
declare p public.profiles%rowtype; e jsonb := '{}'::jsonb; k text; v text;
begin
    select * into p from public.profiles where id = auth.uid();
    if not found then raise exception 'rb_not_logged_in'; end if;
    if p.banned then raise exception 'rb_banned'; end if;
    for k, v in select key, value from jsonb_each_text(coalesce(p.equip, '{}'::jsonb)) loop
        if public.rb_can_wear(p, v) then e := e || jsonb_build_object(k, v); end if;      -- never show what is gone
    end loop;
    return json_build_object(
        'username', p.username, 'minutes', p.minutes, 'coins', p.coins, 'keys', p.keys,
        'coin_min', p.coin_min, 'key_min', p.key_min,
        'day_coins', case when p.day = current_date then p.day_coins else 0 end,
        'equip', e, 'imported', p.imported, 'admin', p.admin, 'avatar_v', p.avatar_v,
        'streak', p.streak, 'streak_day', p.streak_day,
        'scratch_in', case when p.scratch_at is null then 0 else greatest(0, ceil(extract(epoch from (p.scratch_at
                                    + make_interval(hours => public.rb_cfg('scratch_hours')::int) - now()))))::int end,
        'stock', coalesce((select json_object_agg(s.case_id, s.n) from public.rb_case_stock s
                            where s.owner = p.id and s.n > 0), '{}'::json),
        'items', coalesce((select json_agg(json_build_object('id', it.id, 'item', it.item, 'locked', it.locked,
                                                             'origin', it.origin) order by it.got_at)
                             from public.rb_items it where it.owner = p.id), '[]'::json),
        'seen', coalesce((select json_agg(s.item) from public.rb_seen s where s.owner = p.id), '[]'::json));
end $$;

-- buying: Titanium, Gold and Mythic badges can never be bought, whatever the catalogue says
create or replace function public.rb_buy(what text, req text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; c public.rb_catalog%rowtype; res jsonb; new_id uuid; cost integer;
begin
    p := public.rb_lock_me();
    res := public.rb_done(p.id, req);
    if res is not null then return res; end if;
    select * into c from public.rb_catalog where id = what;
    if not found or c.price is null or c.kind = 'prog' then raise exception 'rb_not_for_sale'; end if;
    if c.kind = 'badge' and (c.cls >= 3 or c.rarity = 'exotic') then raise exception 'rb_not_for_sale'; end if;
    if c.kind <> 'badge' and exists (select 1 from public.rb_items it where it.owner = p.id and it.item = what) then
        raise exception 'rb_already_owned';
    end if;
    cost := greatest(1, ceil(c.price * (100 - public.rb_sale_pct(what)) / 100.0))::int;
    perform public.rb_pay(p.id, -cost, 0, 'shop', what);
    new_id := public.rb_give(p.id, what, 'shop');
    return public.rb_remember(p.id, req, jsonb_build_object('id', new_id, 'item', what, 'coins', p.coins - cost));
end $$;

-- ================================================================ mini games: limits per 2 hours
create or replace function public.rb_game_window(who uuid, g text) returns json
language sql stable security definer set search_path = '' as $$
    select json_build_object('rounds', count(*), 'paid', coalesce(sum(paid), 0),
                             'cap', public.rb_cfg('game_window_cap'), 'full', public.rb_cfg('game_full_rounds'),
                             'resets', coalesce(ceil(extract(epoch from (min(at) + interval '2 hours' - now())))::int, 0))
      from public.rb_rounds where owner = who and game = g and not open and at > now() - interval '2 hours' $$;

create or replace function public.rb_mini_day(who uuid) returns json
language sql stable security definer set search_path = '' as $$ select public.rb_game_window(who, 'mini') $$;
create or replace function public.rb_park_day(who uuid) returns json
language sql stable security definer set search_path = '' as $$ select public.rb_game_window(who, 'park') $$;

-- what a round pays after the 2-hour limits
create or replace function public.rb_game_pay(who uuid, g text, pay integer) returns integer
language plpgsql stable security definer set search_path = '' as $$
declare w json := public.rb_game_window(who, g); n integer := (w ->> 'rounds')::int; fr integer := (w ->> 'full')::int;
begin
    if n >= fr * 2 then pay := pay / 4; elsif n >= fr then pay := pay / 2; end if;
    return greatest(0, least(pay, (w ->> 'cap')::int - (w ->> 'paid')::int));
end $$;

-- ================================================================ duels (declared first: the games report to them)
create table if not exists public.rb_duels (
    id uuid primary key default gen_random_uuid(),
    a uuid not null references public.profiles (id) on delete cascade,        -- who asked
    b uuid not null references public.profiles (id) on delete cascade,
    game text not null check (game in ('tap', 'memory', 'park')), tier integer not null default 2,
    bet integer not null default 0 check (bet >= 0), seed jsonb not null,
    state text not null default 'asked' check (state in ('asked', 'on', 'done', 'cancelled')),
    a_score numeric, b_score numeric, a_secs numeric, b_secs numeric, a_played boolean not null default false,
    b_played boolean not null default false, winner uuid, why text,
    at timestamptz not null default now(), ends_at timestamptz);
create index if not exists rb_duels_a on public.rb_duels (a, at desc);
create index if not exists rb_duels_b on public.rb_duels (b, at desc);
alter table public.rb_duels enable row level security;
revoke all on public.rb_duels from anon, authenticated;

-- ends a duel when both have played, or when time is up. Pays the winner; a draw gives the bets back.
create or replace function public.rb_duel_settle(duel uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare d public.rb_duels%rowtype; w uuid; pot integer; fee integer; better boolean;
begin
    select * into d from public.rb_duels where id = duel for update;
    if not found then return; end if;
    if d.state = 'asked' and now() > d.at + interval '5 minutes' then
        update public.rb_duels set state = 'cancelled', why = 'expired' where id = d.id;
        perform public.rb_pay(d.a, d.bet, 0, 'duel_back', d.id::text);
        return;
    end if;
    if d.state <> 'on' then return; end if;
    if not ((d.a_score is not null and d.b_score is not null) or now() > d.ends_at) then return; end if;
    if d.a_score is not null and d.b_score is null then w := d.a;
    elsif d.b_score is not null and d.a_score is null then w := d.b;
    elsif d.a_score is not null and d.b_score is not null then
        if d.a_score = d.b_score then
            if abs(d.a_secs - d.b_secs) >= 0.5 then w := case when d.a_secs < d.b_secs then d.a else d.b end; end if;
        else
            better := case when d.game = 'tap' then d.a_score > d.b_score else d.a_score < d.b_score end;
            w := case when better then d.a else d.b end;
        end if;
    end if;
    perform 1 from public.profiles where id in (d.a, d.b) order by id for update;
    if w is null then
        perform public.rb_pay(d.a, d.bet, 0, 'duel_back', d.id::text);
        perform public.rb_pay(d.b, d.bet, 0, 'duel_back', d.id::text);
    else
        pot := d.bet * 2; fee := floor(pot * public.rb_cfg('duel_fee'))::int;
        perform public.rb_pay(w, pot - fee, 0, 'duel_win', d.id::text);
    end if;
    update public.rb_duels set state = 'done', winner = w, why = case when w is null then 'draw' else 'won' end
     where id = d.id;
    perform public.rb_notice(d.a, 'duel_end', jsonb_build_object('won', w = d.a, 'draw', w is null, 'bet', d.bet,
        'game', d.game, 'other', (select username from public.profiles where id = d.b)));
    perform public.rb_notice(d.b, 'duel_end', jsonb_build_object('won', w = d.b, 'draw', w is null, 'bet', d.bet,
        'game', d.game, 'other', (select username from public.profiles where id = d.a)));
end $$;

create or replace function public.rb_duel_score(duel uuid, who uuid, score numeric, secs double precision) returns void
language plpgsql security definer set search_path = '' as $$
begin
    update public.rb_duels set a_score = case when a = who then score else a_score end,
                               a_secs = case when a = who then secs else a_secs end,
                               b_score = case when b = who then score else b_score end,
                               b_secs = case when b = who then secs else b_secs end
     where id = duel and state = 'on';
    perform public.rb_duel_settle(duel);
end $$;

-- ================================================================ Beat Tap 2: four lanes, holds, chords, speed-up
create or replace function public.rb_tap_chart() returns jsonb
language plpgsql volatile security definer set search_path = '' as $$
declare pat jsonb := '[]'::jsonb; t integer := 1800; lane integer; last integer := -1; hold integer; gap integer;
begin
    while t < 40000 loop
        gap := greatest(290, 700 - t / 90);                                   -- faster and faster
        lane := floor(public.rb_rand() * 4)::int;
        if lane = last and public.rb_rand() < 0.6 then lane := (lane + 1 + floor(public.rb_rand() * 3)::int) % 4; end if;
        hold := case when t > 6000 and public.rb_rand() < 0.14 then 400 + floor(public.rb_rand() * 5)::int * 100 else 0 end;
        pat := pat || jsonb_build_object('t', t, 'l', lane, 'h', hold);
        if t > 12000 and hold = 0 and public.rb_rand() < 0.16 then
            pat := pat || jsonb_build_object('t', t, 'l', (lane + 2) % 4, 'h', 0);   -- two at once
        end if;
        last := lane;
        t := t + gap + hold + floor(public.rb_rand() * 120)::int;
    end loop;
    return pat;
end $$;

create or replace function public.rb_tap_max(pat jsonb) returns integer
language sql immutable as $$
    select (3 * jsonb_array_length(pat) + (select count(*) from jsonb_array_elements(pat) e where (e ->> 'h')::int > 0)
            + 2 * (jsonb_array_length(pat) / 10))::int $$;

create or replace function public.rb_tap_start() returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; pat jsonb := public.rb_tap_chart(); rid uuid;
begin
    p := public.rb_lock_me();
    update public.rb_mini set open = false where owner = p.id and open;
    insert into public.rb_mini (owner, pattern, kind, max_score) values (p.id, pat, 'tap2', public.rb_tap_max(pat))
        returning id into rid;
    return json_build_object('round', rid, 'chart', pat, 'max', public.rb_tap_max(pat), 'day', public.rb_mini_day(p.id));
end $$;

-- hits: [{"i": note, "t": ms when pressed, "u": ms when released (holds)}]. Scored here, not in the app.
create or replace function public.rb_tap_finish(round uuid, hits jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r public.rb_mini%rowtype; elapsed double precision; n integer; lastt integer;
        h jsonb; i integer; dt double precision; nt double precision; hold integer; pts integer := 0;
        got boolean[]; run integer := 0; perfect integer := 0; great integer := 0; good integer := 0;
        pay integer := 0; spread double precision; dts double precision[] := '{}'; best_run integer := 0; pct integer;
begin
    p := public.rb_lock_me();
    select * into r from public.rb_mini where id = round and owner = p.id for update;
    if not found or not r.open or r.kind <> 'tap2' then raise exception 'rb_round_gone'; end if;
    update public.rb_mini set open = false where id = r.id;
    elapsed := extract(epoch from (clock_timestamp() - r.at)) * 1000;
    n := jsonb_array_length(r.pattern);
    lastt := (r.pattern -> (n - 1) ->> 't')::int + (r.pattern -> (n - 1) ->> 'h')::int;
    got := array_fill(false, array[n]);
    if elapsed < lastt - 1500 or elapsed > lastt + 300000 then
        if r.duel is not null then perform public.rb_duel_score(r.duel, p.id, 0, 9999); end if;
        return jsonb_build_object('score', 0, 'paid', 0, 'why', 'time', 'coins', p.coins);
    end if;
    for h in select * from jsonb_array_elements(coalesce(hits, '[]'::jsonb)) loop
        i := (h ->> 'i')::int;
        if i is null or i < 0 or i >= n or got[i + 1] then continue; end if;
        if (h ->> 't')::double precision > elapsed + 1500 then continue; end if;
        nt := (r.pattern -> i ->> 't')::double precision;
        dt := abs((h ->> 't')::double precision - nt);
        if dt > 260 then continue; end if;
        got[i + 1] := true; dts := dts || dt;
        if dt <= 80 then pts := pts + 3; perfect := perfect + 1;
        elsif dt <= 160 then pts := pts + 2; great := great + 1;
        else pts := pts + 1; good := good + 1; end if;
        hold := (r.pattern -> i ->> 'h')::int;
        if hold > 0 and (h ->> 'u') is not null and (h ->> 'u')::double precision >= nt + hold - 150
           and (h ->> 'u')::double precision <= elapsed + 1500 then pts := pts + 1; end if;
    end loop;
    for i in 1 .. n loop                                         -- combo bonus: +2 for every 10 in a row
        if got[i] then run := run + 1; best_run := greatest(best_run, run);
        else pts := pts + 2 * (run / 10); run := 0; end if;
    end loop;
    pts := pts + 2 * (run / 10);
    pct := round(100.0 * pts / greatest(r.max_score, 1));
    update public.rb_mini set score = pts, paid = 0 where id = r.id;
    if r.duel is not null then
        perform public.rb_duel_score(r.duel, p.id, pts, elapsed / 1000);
        return jsonb_build_object('score', pts, 'max', r.max_score, 'pct', pct, 'duel', r.duel, 'paid', 0,
            'perfect', perfect, 'great', great, 'good', good, 'miss', n - perfect - great - good, 'combo', best_run,
            'coins', p.coins);
    end if;
    if pts > 0 then
        pay := round(12 + 38.0 * pts / greatest(r.max_score, 1));
        select stddev_pop(x) into spread from unnest(dts) x;
        if array_length(dts, 1) >= n - 1 and coalesce(spread, 0) < 6 then pay := 10; end if;   -- too perfect for a hand
        pay := public.rb_game_pay(p.id, 'mini', pay);
    end if;
    update public.rb_mini set paid = pay where id = r.id;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        values (p.id, 'mini', 0, jsonb_build_object('score', pts, 'pct', pct), false, pay);
    perform public.rb_pay(p.id, pay, 0, 'minigame', null);
    return jsonb_build_object('score', pts, 'max', r.max_score, 'pct', pct, 'paid', pay, 'coins', p.coins + pay,
        'perfect', perfect, 'great', great, 'good', good, 'miss', n - perfect - great - good, 'combo', best_run,
        'day', public.rb_mini_day(p.id));
end $$;

-- the old Beat Tap (2.3 and older) keeps working, with the new limits and a little more pay
create or replace function public.rb_mini_finish(round uuid, hits jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r public.rb_mini%rowtype; elapsed double precision; last integer; n integer;
        h jsonb; i integer; dt double precision; pts integer := 0; seen integer[] := '{}'; pay integer := 0;
        spread double precision; dts double precision[] := '{}';
begin
    p := public.rb_lock_me();
    select * into r from public.rb_mini where id = round and owner = p.id for update;
    if not found or not r.open or r.kind <> 'tap' then raise exception 'rb_round_gone'; end if;
    elapsed := extract(epoch from (clock_timestamp() - r.at)) * 1000;
    n := jsonb_array_length(r.pattern);
    last := (r.pattern -> (n - 1) ->> 't')::int;
    update public.rb_mini set open = false where id = r.id;
    if elapsed < last - 1500 or elapsed > last + 180000 then
        return jsonb_build_object('score', 0, 'paid', 0, 'why', 'time', 'coins', p.coins);
    end if;
    for h in select * from jsonb_array_elements(coalesce(hits, '[]'::jsonb)) loop
        i := (h ->> 'i')::int;
        if i is null or i < 0 or i >= n or i = any (seen) then continue; end if;
        if (h ->> 't')::double precision > elapsed + 1500 then continue; end if;
        dt := abs((h ->> 't')::double precision - (r.pattern -> i ->> 't')::double precision);
        if dt <= 550 then
            seen := seen || i; dts := dts || dt;
            pts := pts + case when dt <= 120 then 3 when dt <= 300 then 2 else 1 end;
        end if;
    end loop;
    if pts > 0 then
        pay := round(12 + 38.0 * pts / (3 * n));
        select stddev_pop(x) into spread from unnest(dts) x;
        if array_length(dts, 1) >= n - 1 and coalesce(spread, 0) < 6 then pay := 10; end if;
        pay := public.rb_game_pay(p.id, 'mini', pay);
    end if;
    update public.rb_mini set score = pts, paid = pay where id = r.id;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        values (p.id, 'mini', 0, jsonb_build_object('score', pts, 'pct', round(100.0 * pts / (3 * n))), false, pay);
    perform public.rb_pay(p.id, pay, 0, 'minigame', null);
    return jsonb_build_object('score', pts, 'max', 3 * n, 'hits', coalesce(array_length(seen, 1), 0), 'paid', pay,
                              'coins', p.coins + pay, 'day', public.rb_mini_day(p.id));
end $$;

-- ================================================================ Memory: find the pairs. The server shows one card at a time.
create table if not exists public.rb_mem (
    id uuid primary key default gen_random_uuid(),
    owner uuid not null references public.profiles (id) on delete cascade,
    tier integer not null, board integer[] not null, found integer[] not null default '{}', shown integer,
    flips integer not null default 0, open boolean not null default true, paid integer not null default 0,
    duel uuid, at timestamptz not null default clock_timestamp());
create unique index if not exists rb_mem_one_open on public.rb_mem (owner) where open;
alter table public.rb_mem enable row level security;
revoke all on public.rb_mem from anon, authenticated;

create or replace function public.rb_mem_board(tier integer) returns integer[]
language sql volatile security definer set search_path = '' as $$
    select array_agg(s order by public.rb_rand())
      from (select generate_series(0, (array[8, 10, 12])[tier] - 1) s
            union all select generate_series(0, (array[8, 10, 12])[tier] - 1)) x $$;

create or replace function public.rb_mem_go(p public.profiles, t integer, board integer[], duel uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare rid uuid;
begin
    update public.rb_mem set open = false where owner = p.id and open;
    insert into public.rb_mem (owner, tier, board, duel) values (p.id, t, board, duel) returning id into rid;
    return json_build_object('round', rid, 'cards', array_length(board, 1), 'cols', (array[4, 5, 6])[t], 'tier', t,
                             'day', public.rb_game_window(p.id, 'memory'));
end $$;

create or replace function public.rb_mem_start(tier integer) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype;
begin
    p := public.rb_lock_me();
    if tier is null or tier not between 1 and 3 then raise exception 'rb_bad_choice'; end if;
    return public.rb_mem_go(p, tier, public.rb_mem_board(tier), null);
end $$;

create or replace function public.rb_mem_flip(round uuid, card integer) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r public.rb_mem%rowtype; n integer; sym integer; other integer; matched boolean;
        pairs integer; secs double precision; pay integer := 0; base integer; top integer;
begin
    p := public.rb_lock_me();
    select * into r from public.rb_mem where id = round and owner = p.id for update;
    if not found or not r.open then raise exception 'rb_round_gone'; end if;
    n := array_length(r.board, 1);
    if card is null or card < 0 or card >= n or card = any (r.found) then raise exception 'rb_bad_choice'; end if;
    sym := r.board[card + 1];
    if r.shown is null or r.shown = card then
        if r.shown is null then update public.rb_mem set shown = card, flips = flips + 1 where id = r.id; end if;
        return jsonb_build_object('card', card, 'sym', sym, 'first', true);
    end if;
    other := r.shown;
    matched := r.board[other + 1] = sym;
    r.flips := r.flips + 1;
    if matched then r.found := r.found || other || card; end if;
    update public.rb_mem set shown = null, flips = r.flips, found = r.found where id = r.id;
    if coalesce(array_length(r.found, 1), 0) < n then
        return jsonb_build_object('card', card, 'sym', sym, 'other', other, 'match', matched, 'flips', r.flips);
    end if;
    -- all pairs found
    update public.rb_mem set open = false where id = r.id;
    secs := extract(epoch from (clock_timestamp() - r.at));
    pairs := n / 2;
    if r.duel is not null then
        perform public.rb_duel_score(r.duel, p.id, r.flips, secs);
        return jsonb_build_object('card', card, 'sym', sym, 'other', other, 'match', true, 'flips', r.flips,
                                  'done', true, 'paid', 0, 'duel', r.duel, 'secs', round(secs::numeric, 1), 'coins', p.coins);
    end if;
    base := (array[12, 18, 25])[r.tier]; top := (array[30, 40, 55])[r.tier];
    pay := base + round((top - base) * greatest(0.0, least(1.0, (3.5 * pairs - r.flips) / (1.5 * pairs))));
    if secs < 0.35 * r.flips then pay := 0; end if;                          -- faster than a hand can click
    pay := public.rb_game_pay(p.id, 'memory', pay);
    update public.rb_mem set paid = pay where id = r.id;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        values (p.id, 'memory', 0, jsonb_build_object('flips', r.flips, 'pairs', pairs, 'secs', round(secs::numeric, 1)), false, pay);
    perform public.rb_pay(p.id, pay, 0, 'memory', null);
    return jsonb_build_object('card', card, 'sym', sym, 'other', other, 'match', true, 'flips', r.flips, 'done', true,
                              'paid', pay, 'perfect', 2 * pairs, 'secs', round(secs::numeric, 1), 'coins', p.coins + pay,
                              'day', public.rb_game_window(p.id, 'memory'));
end $$;

-- ================================================================ Parking: a little more pay, 2-hour limits, duels
create or replace function public.rb_park_finish(round uuid, moves jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r public.rb_park%rowtype; l public.rb_park_levels%rowtype; n integer;
        secs double precision; pay integer := 0; base integer; top integer;
begin
    p := public.rb_lock_me();
    select * into r from public.rb_park where id = round and owner = p.id for update;
    if not found or not r.open then raise exception 'rb_round_gone'; end if;
    update public.rb_park set open = false where id = r.id;
    select * into l from public.rb_park_levels where id = r.level;
    n := public.rb_park_play(l.layout, moves);
    secs := extract(epoch from (clock_timestamp() - r.at));
    if n < 0 then
        if r.duel is not null then perform public.rb_duel_score(r.duel, p.id, 9999, secs); end if;
        return jsonb_build_object('paid', 0, 'why', 'moves', 'coins', p.coins);
    end if;
    if secs < 2 + 0.3 * n or secs > 3600 then
        update public.rb_park set moves = n where id = r.id;
        if r.duel is not null then perform public.rb_duel_score(r.duel, p.id, 9999, secs); end if;
        return jsonb_build_object('paid', 0, 'why', 'time', 'moves', n, 'coins', p.coins);
    end if;
    if r.duel is not null then
        update public.rb_park set moves = n where id = r.id;
        perform public.rb_duel_score(r.duel, p.id, n, secs);
        return jsonb_build_object('paid', 0, 'moves', n, 'best', l.best, 'duel', r.duel, 'coins', p.coins,
                                  'secs', round(secs::numeric, 1));
    end if;
    base := (array[12, 18, 30])[l.tier]; top := (array[25, 38, 50])[l.tier];
    pay := base + round((top - base) * least(1.0, l.best::numeric / greatest(n, 1)));
    pay := public.rb_game_pay(p.id, 'park', pay);
    update public.rb_park set moves = n, paid = pay where id = r.id;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        values (p.id, 'park', 0, jsonb_build_object('moves', n, 'best', l.best), false, pay);
    perform public.rb_pay(p.id, pay, 0, 'park', l.id::text);
    return jsonb_build_object('paid', pay, 'moves', n, 'best', l.best, 'coins', p.coins + pay,
                              'secs', round(secs::numeric, 1), 'day', public.rb_park_day(p.id));
end $$;

-- ================================================================ duels: ask, answer, play
create or replace function public.rb_duel_ask(name text, game text, tier integer, bet integer) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; o public.profiles%rowtype; seed jsonb; did uuid; lv public.rb_park_levels%rowtype;
begin
    p := public.rb_lock_me();
    select * into o from public.profiles where lower(username) = lower(name);
    if not found or o.id = p.id then raise exception 'rb_no_such_user'; end if;
    if not public.rb_is_friend(p.id, o.id) then raise exception 'rb_not_friends'; end if;
    if game not in ('tap', 'memory', 'park') or tier is null or tier not between 1 and 3 then raise exception 'rb_bad_choice'; end if;
    bet := coalesce(bet, 0);
    if bet < 0 or bet > public.rb_cfg('duel_max_bet') then raise exception 'rb_bad_bet'; end if;
    if bet > 0 and not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    if (select count(*) from public.rb_duels d where d.a = p.id and d.state = 'asked') >= 3 then raise exception 'rb_too_many'; end if;
    seed := case game when 'tap' then public.rb_tap_chart()
                      when 'memory' then to_jsonb(public.rb_mem_board(tier))
                      else (select to_jsonb(pl.id) from public.rb_park_levels pl where pl.tier = rb_duel_ask.tier
                             order by public.rb_rand() limit 1) end;
    perform public.rb_pay(p.id, -bet, 0, 'duel_bet', null);
    insert into public.rb_duels (a, b, game, tier, bet, seed) values (p.id, o.id, game, tier, bet, seed) returning id into did;
    perform public.rb_notice(o.id, 'duel', jsonb_build_object('from', p.username, 'game', game, 'bet', bet, 'id', did));
    return json_build_object('id', did, 'coins', p.coins - bet);
end $$;

create or replace function public.rb_duel_answer(duel uuid, yes boolean) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; d public.rb_duels%rowtype;
begin
    p := public.rb_lock_me();
    perform public.rb_duel_settle(duel);                     -- too old? it is cancelled first
    select * into d from public.rb_duels where id = duel for update;
    if not found or d.state <> 'asked' or (d.b <> p.id and d.a <> p.id) then raise exception 'rb_duel_gone'; end if;
    if not coalesce(yes, false) or d.a = p.id then             -- no, or the one who asked takes it back
        update public.rb_duels set state = 'cancelled', why = case when d.a = p.id then 'taken back' else 'declined' end where id = d.id;
        perform public.rb_pay(d.a, d.bet, 0, 'duel_back', d.id::text);
        if d.a <> p.id then perform public.rb_notice(d.a, 'duel_no', jsonb_build_object('from', p.username)); end if;
        return json_build_object('state', 'cancelled', 'coins', (select coins from public.profiles where id = p.id));
    end if;
    if d.bet > 0 and not public.rb_can_trade(p) then raise exception 'rb_trade_locked'; end if;
    perform public.rb_pay(p.id, -d.bet, 0, 'duel_bet', d.id::text);
    update public.rb_duels set state = 'on', ends_at = now() + interval '15 minutes' where id = d.id;
    perform public.rb_notice(d.a, 'duel_yes', jsonb_build_object('from', p.username, 'id', d.id, 'game', d.game));
    return json_build_object('state', 'on', 'coins', p.coins - d.bet);
end $$;

create or replace function public.rb_duel_play(duel uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; d public.rb_duels%rowtype; rid uuid; lv public.rb_park_levels%rowtype; res json;
begin
    p := public.rb_lock_me();
    perform public.rb_duel_settle(duel);
    select * into d from public.rb_duels where id = duel for update;
    if not found or d.state <> 'on' or (d.a <> p.id and d.b <> p.id) then raise exception 'rb_duel_gone'; end if;
    if (d.a = p.id and d.a_played) or (d.b = p.id and d.b_played) then raise exception 'rb_already_played'; end if;
    update public.rb_duels set a_played = a_played or a = p.id, b_played = b_played or b = p.id where id = d.id;
    if d.game = 'tap' then
        update public.rb_mini set open = false where owner = p.id and open;
        insert into public.rb_mini (owner, pattern, kind, max_score, duel)
            values (p.id, d.seed, 'tap2', public.rb_tap_max(d.seed), d.id) returning id into rid;
        res := json_build_object('round', rid, 'chart', d.seed, 'max', public.rb_tap_max(d.seed));
    elsif d.game = 'memory' then
        res := public.rb_mem_go(p, d.tier, array(select jsonb_array_elements_text(d.seed)::int), d.id);
    else
        select * into lv from public.rb_park_levels where id = (d.seed #>> '{}')::int;
        update public.rb_park set open = false where owner = p.id and open;
        insert into public.rb_park (owner, level, duel) values (p.id, lv.id, d.id) returning id into rid;
        res := json_build_object('round', rid, 'layout', lv.layout, 'best', lv.best, 'tier', lv.tier);
    end if;
    return json_build_object('game', d.game, 'data', res, 'ends_at', d.ends_at);
end $$;

create or replace function public.rb_duels() returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); d record;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    for d in select id from public.rb_duels where (a = me or b = me) and state in ('asked', 'on') loop
        perform public.rb_duel_settle(d.id);
    end loop;
    return coalesce((select json_agg(json_build_object(
        'id', x.id, 'game', x.game, 'tier', x.tier, 'bet', x.bet, 'state', x.state, 'asked_me', x.b = me and x.state = 'asked',
        'other', (select username from public.profiles where id = case when x.a = me then x.b else x.a end),
        'played', case when x.a = me then x.a_played else x.b_played end,
        'other_played', case when x.a = me then x.b_played else x.a_played end,
        'my_score', case when x.a = me then x.a_score else x.b_score end,
        'other_score', case when x.state = 'done' then (case when x.a = me then x.b_score else x.a_score end) end,
        'won', x.winner = me, 'draw', x.state = 'done' and x.winner is null, 'why', x.why,
        'ends_at', x.ends_at, 'at', x.at) order by x.at desc)
        from (select * from public.rb_duels where a = me or b = me order by at desc limit 20) x), '[]'::json);
end $$;

-- ================================================================ scratch card (every 12 hours)
create or replace function public.rb_scratch() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; roll double precision; tier text; c integer := 0; k integer := 0;
begin
    p := public.rb_lock_me();
    if p.scratch_at is not null and now() < p.scratch_at + make_interval(hours => public.rb_cfg('scratch_hours')::int) then
        raise exception 'rb_wait';
    end if;
    roll := public.rb_rand();
    if roll < 0.55 then tier := 'standard'; c := 60 + floor(public.rb_rand() * 61)::int;
    elsif roll < 0.82 then tier := 'rare'; c := 150 + floor(public.rb_rand() * 151)::int;
    elsif roll < 0.94 then tier := 'special'; k := 1;
    elsif roll < 0.99 then tier := 'epic'; k := 2;
    else tier := 'exotic'; c := 2500; end if;
    update public.profiles set scratch_at = now() where id = p.id;
    perform public.rb_pay(p.id, c, k, 'scratch', tier);
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (p.id, 'scratch', 0, jsonb_build_object('tier', tier, 'keys', k), false, c);
    return jsonb_build_object('rarity', tier, 'coins_won', c, 'keys_won', k, 'coins', p.coins + c, 'keys', p.keys + k,
                              'next', public.rb_cfg('scratch_hours')::int * 3600);
end $$;

-- ================================================================ daily login streak
create or replace function public.rb_today() returns date
language sql stable as $$ select (now() at time zone 'Europe/Paris')::date $$;

create or replace function public.rb_login_rewards() returns jsonb
language sql immutable as $$
    select '[{"coins":60},{"coins":90},{"coins":120},{"keys":1},{"coins":200},{"coins":300},{"coins":400,"case":"standard"}]'::jsonb $$;

create or replace function public.rb_login_state() returns json
language plpgsql stable security definer set search_path = '' as $$
declare p public.profiles%rowtype; s integer;
begin
    select * into p from public.profiles where id = auth.uid();
    if not found then raise exception 'rb_not_logged_in'; end if;
    s := case when p.streak_day = public.rb_today() then p.streak
              when p.streak_day = public.rb_today() - 1 then p.streak else 0 end;   -- missed a day: back to day 1
    return json_build_object('streak', s, 'claimed', p.streak_day = public.rb_today(),
                             'day', case when p.streak_day = public.rb_today() then (s - 1) % 7 else s % 7 end,
                             'rewards', public.rb_login_rewards());
end $$;

create or replace function public.rb_login_claim() returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; s integer; r jsonb; c integer; k integer;
begin
    p := public.rb_lock_me();
    if p.streak_day = public.rb_today() then raise exception 'rb_wait'; end if;
    s := case when p.streak_day = public.rb_today() - 1 then p.streak + 1 else 1 end;
    r := public.rb_login_rewards() -> ((s - 1) % 7);
    c := coalesce((r ->> 'coins')::int, 0); k := coalesce((r ->> 'keys')::int, 0);
    update public.profiles set streak = s, streak_day = public.rb_today() where id = p.id;
    perform public.rb_pay(p.id, c, k, 'login', s::text);
    if r ? 'case' then perform public.rb_stock_add(p.id, r ->> 'case', 1); end if;
    return jsonb_build_object('streak', s, 'reward', r, 'coins', p.coins + c, 'keys', p.keys + k);
end $$;

-- ================================================================ collection sets (one big bonus each, once)
create table if not exists public.rb_set_claims (
    owner uuid not null references public.profiles (id) on delete cascade, set_id text not null,
    at timestamptz not null default now(), primary key (owner, set_id));
alter table public.rb_set_claims enable row level security;
revoke all on public.rb_set_claims from anon, authenticated;

create or replace function public.rb_set_rows(who uuid)
returns table (set_id text, goal integer, have integer, coins integer, keys integer, claimed boolean)
language sql stable security definer set search_path = '' as $$
    with mine as (select distinct c.base, c.rarity, c.cls, c.variant from public.rb_items it
                    join public.rb_catalog c on c.id = it.item where it.owner = who and c.kind = 'badge'),
         sets (set_id, goal, have, coins, keys) as (values
            ('row_standard', 12, (select count(distinct base) from mine where rarity = 'standard')::int, 3000, 2),
            ('row_rare',     12, (select count(distinct base) from mine where rarity = 'rare')::int, 8000, 4),
            ('row_special',  12, (select count(distinct base) from mine where rarity = 'special')::int, 20000, 6),
            ('row_epic',     12, (select count(distinct base) from mine where rarity = 'epic')::int, 50000, 10),
            ('row_exotic',    6, (select count(distinct base) from mine where rarity = 'exotic')::int, 250000, 25),
            ('rainbow',       8, (select coalesce(max(n), 0) from (select count(distinct variant) n from mine
                                    where cls = 1 group by base) x)::int, 4000, 2),
            ('shiny5',        5, (select count(*) from mine where cls = 2)::int, 15000, 5),
            ('titanium3',     3, (select count(*) from mine where cls = 3)::int, 40000, 8),
            ('gold1',         1, (select count(*) from mine where cls = 4)::int, 25000, 10))
    select r.set_id, r.goal, least(r.have, r.goal), r.coins, r.keys,
           exists (select 1 from public.rb_set_claims s where s.owner = who and s.set_id = r.set_id)
      from sets r $$;

create or replace function public.rb_sets() returns json
language sql stable security definer set search_path = '' as $$
    select coalesce(json_agg(row_to_json(r)), '[]'::json) from public.rb_set_rows(auth.uid()) r $$;

create or replace function public.rb_set_claim(which text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r record;
begin
    p := public.rb_lock_me();
    select * into r from public.rb_set_rows(p.id) s where s.set_id = which;
    if not found then raise exception 'rb_bad_choice'; end if;
    if r.claimed then raise exception 'rb_already_claimed'; end if;
    if r.have < r.goal then raise exception 'rb_not_done'; end if;
    insert into public.rb_set_claims (owner, set_id) values (p.id, which);
    perform public.rb_pay(p.id, r.coins, r.keys, 'set', which);
    return jsonb_build_object('coins', p.coins + r.coins, 'keys', p.keys + r.keys, 'got_coins', r.coins, 'got_keys', r.keys);
end $$;

-- ================================================================ leaderboards
create or replace function public.rb_leaders(kind text, friends boolean) returns json
language plpgsql stable security definer set search_path = '' as $$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    if kind not in ('coins', 'worth', 'badges', 'hours', 'streak', 'tap', 'park', 'memory') then raise exception 'rb_bad_choice'; end if;
    return (with who as (select p.* from public.profiles p where not p.banned
                          and (not coalesce(friends, false) or p.id = me or public.rb_is_friend(me, p.id))),
            v as (select w.id, w.username, (case kind
                when 'coins' then w.coins
                when 'hours' then w.minutes / 60
                when 'streak' then (case when w.streak_day >= public.rb_today() - 1 then w.streak else 0 end)
                when 'worth' then (select coalesce(sum(c.value), 0) from public.rb_items it join public.rb_catalog c on c.id = it.item where it.owner = w.id)
                when 'badges' then (select count(distinct it.item) from public.rb_items it where it.owner = w.id and it.item like 'badge:%')
                when 'tap' then (select coalesce(max((r.secret ->> 'pct')::int), 0) from public.rb_rounds r where r.owner = w.id and r.game = 'mini')
                when 'park' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game = 'park')
                else (select count(*) from public.rb_rounds r where r.owner = w.id and r.game = 'memory') end)::bigint as val
                  from who w),
            ranked as (select v.*, rank() over (order by val desc) rk from v where val > 0 or v.id = me)
        select json_build_object(
            'top', coalesce((select json_agg(json_build_object('rank', rk, 'name', username, 'value', val, 'me', id = me) order by rk, username)
                               from (select * from ranked order by rk, username limit 50) t), '[]'::json),
            'me', (select json_build_object('rank', rk, 'value', val) from ranked where id = me)));
end $$;

-- ================================================================ messages between friends (with mute)
create table if not exists public.rb_messages (
    id bigserial primary key, a uuid not null references public.profiles (id) on delete cascade,
    b uuid not null references public.profiles (id) on delete cascade,
    body text not null check (length(body) between 1 and 300), at timestamptz not null default now(),
    read boolean not null default false);
create index if not exists rb_messages_ab on public.rb_messages (a, b, id desc);
create index if not exists rb_messages_b on public.rb_messages (b, read);
create table if not exists public.rb_mutes (
    owner uuid not null references public.profiles (id) on delete cascade,
    who uuid not null references public.profiles (id) on delete cascade, primary key (owner, who));
do $$ declare t text; begin
    foreach t in array array['rb_messages', 'rb_mutes'] loop
        execute format('alter table public.%I enable row level security', t);
        execute format('revoke all on public.%I from anon, authenticated', t);
    end loop;
end $$;

create or replace function public.rb_msg_send(name text, body text) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; o public.profiles%rowtype; mid bigint;
begin
    p := public.rb_lock_me();
    select * into o from public.profiles where lower(username) = lower(name);
    if not found or o.id = p.id then raise exception 'rb_no_such_user'; end if;
    if not public.rb_is_friend(p.id, o.id) then raise exception 'rb_not_friends'; end if;
    body := btrim(regexp_replace(coalesce(body, ''), '[\x00-\x09\x0b-\x1f]', '', 'g'));
    if length(body) = 0 then raise exception 'rb_bad_choice'; end if;
    body := left(body, 300);
    if (select count(*) from public.rb_messages m where m.a = p.id and m.at > now() - interval '1 minute')
       >= public.rb_cfg('msg_per_min') then raise exception 'rb_slow_down'; end if;
    insert into public.rb_messages (a, b, body) values (p.id, o.id, body) returning id into mid;
    if not exists (select 1 from public.rb_mutes m where m.owner = o.id and m.who = p.id) then
        perform public.rb_notice(o.id, 'message', jsonb_build_object('from', p.username, 'text', left(body, 60)));
    end if;
    return json_build_object('id', mid);
end $$;

create or replace function public.rb_msg_threads() returns json
language sql stable security definer set search_path = '' as $$
    with me as (select auth.uid() id),
         fr as (select case when f.a = me.id then f.b else f.a end as who from public.rb_friends f, me
                 where f.ok and (f.a = me.id or f.b = me.id))
    select coalesce(json_agg(x order by x.last_at desc nulls last, x.name), '[]'::json) from (
        select p.username as name, public.rb_online(p) as online,
               exists (select 1 from public.rb_mutes m, me where m.owner = me.id and m.who = p.id) as muted,
               (select count(*) from public.rb_messages m, me where m.a = p.id and m.b = me.id and not m.read) as unread,
               (select m.body from public.rb_messages m, me where (m.a = p.id and m.b = me.id) or (m.a = me.id and m.b = p.id) order by m.id desc limit 1) as last,
               (select m.at from public.rb_messages m, me where (m.a = p.id and m.b = me.id) or (m.a = me.id and m.b = p.id) order by m.id desc limit 1) as last_at
          from fr join public.profiles p on p.id = fr.who) x $$;

create or replace function public.rb_msg_get(name text) returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); o uuid;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select id into o from public.profiles where lower(username) = lower(name);
    if o is null then raise exception 'rb_no_such_user'; end if;
    update public.rb_messages set read = true where a = o and b = me and not read;
    return coalesce((select json_agg(json_build_object('id', m.id, 'mine', m.a = me, 'text', m.body, 'at', m.at) order by m.id)
                       from (select * from public.rb_messages where (a = o and b = me) or (a = me and b = o)
                              order by id desc limit 80) m), '[]'::json);
end $$;

create or replace function public.rb_msg_mute(name text, mute boolean) returns boolean
language plpgsql security definer set search_path = '' as $$
declare me uuid := auth.uid(); o uuid;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select id into o from public.profiles where lower(username) = lower(name);
    if o is null then raise exception 'rb_no_such_user'; end if;
    if coalesce(mute, false) then insert into public.rb_mutes (owner, who) values (me, o) on conflict do nothing;
    else delete from public.rb_mutes where owner = me and who = o; end if;
    return coalesce(mute, false);
end $$;

-- ================================================================ trade history
create or replace function public.rb_trade_history() returns json
language sql stable security definer set search_path = '' as $$
    select coalesce(json_agg(x order by x.at desc), '[]'::json) from (
        select t.id, t.updated as at, t.undone_at is not null as undone,
               (select username from public.profiles where id = case when t.a = auth.uid() then t.b else t.a end) as other,
               case when t.a = auth.uid() then t.a_coins else t.b_coins end as gave_coins,
               case when t.a = auth.uid() then t.b_coins else t.a_coins end as got_coins,
               coalesce((select json_agg(ti.what) from public.rb_trade_items ti
                          where ti.trade = t.id and ti.side = case when t.a = auth.uid() then 'a' else 'b' end), '[]'::json) as gave,
               coalesce((select json_agg(ti.what) from public.rb_trade_items ti
                          where ti.trade = t.id and ti.side = case when t.a = auth.uid() then 'b' else 'a' end), '[]'::json) as got
          from public.rb_trades t where t.state = 'done' and (t.a = auth.uid() or t.b = auth.uid())
         order by t.updated desc limit 100) x $$;

-- ================================================================ settings backup in the cloud
create or replace function public.rb_backup_save(data jsonb) returns timestamptz
language plpgsql security definer set search_path = '' as $$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    if data is null or length(data::text) > 65536 then raise exception 'rb_too_big'; end if;
    update public.profiles set backup = data, backup_at = now() where id = auth.uid();
    return now();
end $$;

create or replace function public.rb_backup_load() returns json
language sql stable security definer set search_path = '' as $$
    select json_build_object('data', backup, 'at', backup_at) from public.profiles where id = auth.uid() $$;

-- ================================================================ forgotten password: a request the admin checks
create table if not exists public.rb_resets (
    id uuid primary key default gen_random_uuid(), name text not null, uid uuid, device text not null,
    msg text not null default '', state text not null default 'open' check (state in ('open', 'done', 'refused')),
    temp text, at timestamptz not null default now(), done_at timestamptz);
alter table public.rb_resets enable row level security;
revoke all on public.rb_resets from anon, authenticated;

-- anyone (not logged in) may ask; a PC can ask 3 times a day
create or replace function public.rb_reset_ask(name text, pc text, msg text) returns uuid
language plpgsql security definer set search_path = '' as $$
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
end $$;

-- the PC that asked can see the answer (and the new password) for one day
create or replace function public.rb_reset_status(rid uuid, pc text) returns json
language sql stable security definer set search_path = '' as $$
    select json_build_object('state', r.state,
                             'password', case when r.state = 'done' and r.done_at > now() - interval '1 day' then r.temp end)
      from public.rb_resets r where r.id = rid and r.device = pc $$;

create or replace function public.rb_admin_resets() returns json
language plpgsql stable security definer set search_path = '' as $$
begin
    perform public.rb_need_admin();
    return coalesce((select json_agg(json_build_object(
        'id', r.id, 'name', r.name, 'msg', r.msg, 'state', r.state, 'at', r.at,
        'exists', r.uid is not null,
        'same_pc', exists (select 1 from public.rb_devices d where d.device = r.device and d.owner = r.uid),
        'pc_owner', (select p.username from public.rb_devices d join public.profiles p on p.id = d.owner
                      where d.device = r.device and d.owner is distinct from r.uid),
        'pc_asks', (select count(*) from public.rb_resets x where x.device = r.device and x.at > now() - interval '7 days'),
        'name_asks', (select count(*) from public.rb_resets x where lower(x.name) = lower(r.name) and x.at > now() - interval '7 days'),
        'seen', (select p.last_beat from public.profiles p where p.id = r.uid),
        'minutes', (select p.minutes from public.profiles p where p.id = r.uid),
        'verdict', case when r.uid is null then 'no_account'
                        when exists (select 1 from public.rb_devices d where d.device = r.device and d.owner = r.uid) then 'real'
                        when exists (select 1 from public.rb_devices d where d.device = r.device and d.owner is not null) then 'fake'
                        else 'unsure' end) order by r.state = 'open' desc, r.at desc)
        from (select * from public.rb_resets order by at desc limit 60) r), '[]'::json);
end $$;

-- the admin answers: a new password (8+ letters) for the account, or no
create or replace function public.rb_admin_reset_do(rid uuid, new_password text) returns boolean
language plpgsql security definer set search_path = '' as $$
declare r public.rb_resets%rowtype;
begin
    perform public.rb_need_admin();
    select * into r from public.rb_resets where id = rid for update;
    if not found or r.state <> 'open' then raise exception 'rb_bad_choice'; end if;
    if new_password is null then
        update public.rb_resets set state = 'refused', done_at = now() where id = r.id;
        perform public.rb_log('reset_no', r.name, null);
        return false;
    end if;
    if r.uid is null then raise exception 'rb_no_such_user'; end if;
    if length(new_password) < 8 then raise exception 'rb_weak_password'; end if;
    update auth.users set encrypted_password = extensions.crypt(new_password, extensions.gen_salt('bf')) where id = r.uid;
    if to_regclass('auth.refresh_tokens') is not null then        -- whoever was logged in is logged out
        execute 'delete from auth.refresh_tokens where user_id = $1::text' using r.uid;
    end if;
    if to_regclass('auth.sessions') is not null then
        execute 'delete from auth.sessions where user_id = $1' using r.uid;
    end if;
    update public.rb_resets set state = 'done', temp = new_password, done_at = now() where id = r.id;
    update public.rb_resets set state = 'refused', done_at = now() where uid = r.uid and state = 'open' and id <> r.id;
    perform public.rb_log('reset', r.name, null);
    return true;
end $$;

-- ================================================================ admin: everything can be undone
create or replace function public.rb_free_item(item_id uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare l text; t text;
begin
    select locked into l from public.rb_items where id = item_id;
    if l like 'market:%' then
        update public.rb_listings set state = 'cancelled' where id = substr(l, 8)::uuid and state = 'open';
        update public.rb_offers set state = 'gone' where listing = substr(l, 8)::uuid and state = 'open';
    elsif l like 'trade:%' then
        perform public.rb_trade_end(substr(l, 7)::uuid, 'admin');
    end if;
    update public.rb_items set locked = null where id = item_id;
end $$;

-- moves an item back to `who` from wherever it is now (or makes it again if it no longer exists)
create or replace function public.rb_move_back(item_id uuid, what text, who uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare was uuid;
begin
    select owner into was from public.rb_items where id = item_id for update;
    if not found then perform public.rb_give(who, what, 'undo'); return; end if;
    perform public.rb_free_item(item_id);
    update public.rb_items set owner = who, origin = 'undo' where id = item_id;
    insert into public.rb_seen (owner, item) values (who, what) on conflict do nothing;
    perform public.rb_fix_equip(was);
end $$;

create or replace function public.rb_admin_grant(name text, add_coins integer, add_keys integer) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; dc integer; dk integer;
begin
    perform public.rb_need_admin();
    select * into p from public.profiles where lower(username) = lower(name) for update;
    if not found then raise exception 'rb_no_such_user'; end if;
    dc := greatest(coalesce(add_coins, 0), -p.coins)::int; dk := greatest(coalesce(add_keys, 0), -p.keys);
    perform public.rb_pay(p.id, dc, dk, 'admin', null);
    perform public.rb_log('grant', p.username, jsonb_build_object('coins', dc, 'keys', dk, 'uid', p.id));
    if dc > 0 or dk > 0 then
        perform public.rb_notice(p.id, 'admin', jsonb_build_object('coins', greatest(dc, 0), 'keys', greatest(dk, 0)));
    end if;
    return jsonb_build_object('coins', p.coins + dc, 'keys', p.keys + dk);
end $$;

create or replace function public.rb_admin_give(name text, what text, how_many integer) returns boolean
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; n integer := least(greatest(coalesce(how_many, 1), 1), 100); ids uuid[] := '{}'; i integer;
begin
    perform public.rb_need_admin();
    select * into p from public.profiles where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    if what like 'case:%' then
        if not exists (select 1 from public.rb_cases where id = substr(what, 6)) then raise exception 'rb_no_case'; end if;
        perform public.rb_stock_add(p.id, substr(what, 6), n);
        perform public.rb_notice(p.id, 'admin', jsonb_build_object('case', substr(what, 6), 'n', n));
    else
        if not exists (select 1 from public.rb_catalog c where c.id = what and c.kind <> 'prog') then
            raise exception 'rb_not_for_sale';
        end if;
        for i in 1 .. n loop ids := ids || public.rb_give(p.id, what, 'admin'); end loop;
        perform public.rb_notice(p.id, 'admin', jsonb_build_object('item', what, 'n', n));
    end if;
    perform public.rb_log('give', p.username, jsonb_build_object('what', what, 'n', n, 'uid', p.id, 'ids', to_jsonb(ids)));
    return true;
end $$;

create or replace function public.rb_admin_take(item_id uuid) returns boolean
language plpgsql security definer set search_path = '' as $$
declare it public.rb_items%rowtype;
begin
    perform public.rb_need_admin();
    select * into it from public.rb_items where id = item_id for update;
    if not found then raise exception 'rb_not_yours'; end if;
    perform public.rb_free_item(it.id);
    delete from public.rb_items where id = it.id;
    perform public.rb_fix_equip(it.owner);
    perform public.rb_log('take', (select username from public.profiles where id = it.owner),
                          jsonb_build_object('item', it.item, 'uid', it.owner, 'id', it.id));
    return true;
end $$;

create or replace function public.rb_admin_revoke(name text, what text) returns integer
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; n integer; x record;
begin
    perform public.rb_need_admin();
    select * into p from public.profiles where lower(username) = lower(name);
    if not found then raise exception 'rb_no_such_user'; end if;
    for x in select id from public.rb_items where owner = p.id and item = rb_admin_revoke.what loop
        perform public.rb_free_item(x.id);
    end loop;
    delete from public.rb_items where owner = p.id and item = what;
    get diagnostics n = row_count;
    perform public.rb_fix_equip(p.id);
    perform public.rb_log('revoke', p.username, jsonb_build_object('what', what, 'n', n, 'uid', p.id));
    return n;
end $$;

create or replace function public.rb_admin_ban(name text, ban boolean) returns boolean
language plpgsql security definer set search_path = '' as $$
declare me uuid := public.rb_need_admin(); p public.profiles%rowtype;
begin
    select * into p from public.profiles where lower(username) = lower(name) and id <> me;
    if not found then raise exception 'rb_no_such_user'; end if;
    update public.profiles set banned = coalesce(ban, false) where id = p.id;
    perform public.rb_log('ban', p.username, jsonb_build_object('banned', ban, 'was', p.banned, 'uid', p.id));
    return true;
end $$;

create or replace function public.rb_admin_set(setting text, new_value numeric) returns boolean
language plpgsql security definer set search_path = '' as $$
declare old numeric;
begin
    perform public.rb_need_admin();
    if setting = 'reset_008' or new_value is null or new_value < 0 then raise exception 'rb_bad_choice'; end if;
    select value into old from public.rb_config where key = setting for update;
    if not found then raise exception 'rb_bad_choice'; end if;
    update public.rb_config set value = new_value where key = setting;
    perform public.rb_log('set', setting, jsonb_build_object('value', new_value, 'old', old));
    return true;
end $$;

create or replace function public.rb_admin_lock(lock boolean) returns boolean
language plpgsql security definer set search_path = '' as $$
declare old numeric;
begin
    perform public.rb_need_admin();
    select value into old from public.rb_config where key = 'app_locked';
    update public.rb_config set value = case when coalesce(lock, false) then 1 else 0 end where key = 'app_locked';
    perform public.rb_log('lock', null, jsonb_build_object('locked', lock, 'old', old));
    return true;
end $$;

-- everyone must update to the admin's version (the admin's own app sends its version)
create or replace function public.rb_admin_force_update() returns bigint
language plpgsql security definer set search_path = '' as $$
declare b bigint;
begin
    perform public.rb_need_admin();
    select build into b from public.profiles where id = auth.uid();
    perform public.rb_admin_set('min_build', b);
    return b;
end $$;

create or replace function public.rb_admin_audit() returns json
language plpgsql stable security definer set search_path = '' as $$
begin
    perform public.rb_need_admin();
    return (select coalesce(json_agg(json_build_object('id', a.id, 'action', a.action, 'target', a.target, 'detail', a.detail,
                                                       'at', a.at, 'undone', a.undone_at is not null,
                                                       'can_undo', a.undone_at is null and (
                                                           (a.action in ('grant', 'take', 'revoke', 'ban') and a.detail ? 'uid')
                                                           or (a.action = 'give' and a.detail ? 'uid')
                                                           or (a.action in ('set', 'lock') and a.detail ? 'old')))
                                     order by a.id desc), '[]'::json)
              from (select * from public.rb_audit order by id desc limit 150) a);
end $$;

create or replace function public.rb_admin_undo(entry bigint) returns text
language plpgsql security definer set search_path = '' as $$
declare me uuid := public.rb_need_admin(); a public.rb_audit%rowtype; d jsonb; uid uuid; pc bigint; pk integer;
        dc integer; dk integer; cnt integer := 0; note text; x record; i integer;
begin
    select * into a from public.rb_audit where id = entry for update;
    if not found then raise exception 'rb_cant_undo'; end if;
    if a.undone_at is not null then raise exception 'rb_already_undone'; end if;
    d := coalesce(a.detail, '{}'::jsonb); uid := (d ->> 'uid')::uuid;
    if a.action in ('grant', 'give', 'take', 'revoke', 'ban') and uid is null then raise exception 'rb_cant_undo'; end if;
    if a.action = 'grant' then
        select coins, keys into pc, pk from public.profiles where id = uid for update;
        dc := greatest(-(d ->> 'coins')::int, -pc)::int; dk := greatest(-(d ->> 'keys')::int, -pk);
        perform public.rb_pay(uid, dc, dk, 'admin_undo', a.id::text);
        note := format('%s coins, %s keys', dc, dk);
    elsif a.action = 'give' and d ->> 'what' like 'case:%' then
        update public.rb_case_stock set n = greatest(0, rb_case_stock.n - (d ->> 'n')::int)
         where owner = uid and case_id = substr(d ->> 'what', 6);
        note := d ->> 'what';
    elsif a.action = 'give' then
        for x in select it.id from public.rb_items it
                  where it.id in (select jsonb_array_elements_text(d -> 'ids')::uuid) loop
            perform public.rb_free_item(x.id);
            delete from public.rb_items where id = x.id; cnt := cnt + 1;
        end loop;
        perform public.rb_fix_equip(uid);
        note := format('%s x %s', cnt, d ->> 'what');
    elsif a.action = 'take' then
        perform public.rb_give(uid, d ->> 'item', 'undo'); note := d ->> 'item';
    elsif a.action = 'revoke' then
        for i in 1 .. coalesce((d ->> 'n')::int, 0) loop perform public.rb_give(uid, d ->> 'what', 'undo'); end loop;
        note := format('%s x %s', d ->> 'n', d ->> 'what');
    elsif a.action = 'ban' then
        update public.profiles set banned = coalesce((d ->> 'was')::boolean, false) where id = uid;
    elsif a.action = 'set' and d ? 'old' then
        update public.rb_config set value = (d ->> 'old')::numeric where key = a.target;
        note := format('%s = %s', a.target, d ->> 'old');
    elsif a.action = 'lock' and d ? 'old' then
        update public.rb_config set value = (d ->> 'old')::numeric where key = 'app_locked';
    else
        raise exception 'rb_cant_undo';
    end if;
    update public.rb_audit set undone_at = now(), undone_by = me where id = a.id;
    perform public.rb_log('undo', a.target, jsonb_build_object('entry', a.id, 'action', a.action, 'note', note));
    return coalesce(note, a.action);
end $$;

-- a player's trades and market sales, so one can be undone (a scam, a hacked account)
create or replace function public.rb_admin_deals(name text) returns json
language plpgsql stable security definer set search_path = '' as $$
declare u uuid;
begin
    perform public.rb_need_admin();
    select id into u from public.profiles where lower(username) = lower(name);
    if u is null then raise exception 'rb_no_such_user'; end if;
    return json_build_object(
        'trades', coalesce((select json_agg(json_build_object('id', t.id, 'at', t.updated, 'undone', t.undone_at is not null,
                'a', (select username from public.profiles where id = t.a), 'b', (select username from public.profiles where id = t.b),
                'a_coins', t.a_coins, 'b_coins', t.b_coins,
                'a_items', coalesce((select json_agg(ti.what) from public.rb_trade_items ti where ti.trade = t.id and ti.side = 'a'), '[]'::json),
                'b_items', coalesce((select json_agg(ti.what) from public.rb_trade_items ti where ti.trade = t.id and ti.side = 'b'), '[]'::json))
                order by t.updated desc)
            from (select * from public.rb_trades where state = 'done' and (a = u or b = u) order by updated desc limit 30) t), '[]'::json),
        'sales', coalesce((select json_agg(json_build_object('id', l.id, 'at', l.sold_at, 'undone', l.undone_at is not null,
                'what', l.what, 'price', l.price, 'seller', (select username from public.profiles where id = l.seller),
                'buyer', (select username from public.profiles where id = l.buyer)) order by l.sold_at desc)
            from (select * from public.rb_listings where state = 'sold' and (seller = u or buyer = u) order by sold_at desc limit 30) l), '[]'::json));
end $$;

create or replace function public.rb_admin_undo_trade(trade uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := public.rb_need_admin(); t public.rb_trades%rowtype; x record; net integer; giver uuid; taker uuid;
        have bigint; took integer := 0;
begin
    select * into t from public.rb_trades where id = trade for update;
    if not found or t.state <> 'done' then raise exception 'rb_cant_undo'; end if;
    if t.undone_at is not null then raise exception 'rb_already_undone'; end if;
    perform 1 from public.profiles where id in (t.a, t.b) order by id for update;
    for x in select * from public.rb_trade_items where rb_trade_items.trade = t.id loop
        perform public.rb_move_back(x.item, x.what, case x.side when 'a' then t.a else t.b end);
    end loop;
    net := t.a_coins - t.b_coins;                  -- coins that went from a to b
    if net <> 0 then
        giver := case when net > 0 then t.a else t.b end; taker := case when net > 0 then t.b else t.a end;
        select coins into have from public.profiles where id = taker;
        took := least(abs(net), have)::int;
        perform public.rb_pay(taker, -took, 0, 'trade_undo', t.id::text);
        perform public.rb_pay(giver, abs(net), 0, 'trade_undo', t.id::text);
    end if;
    perform public.rb_fix_equip(t.a); perform public.rb_fix_equip(t.b);
    update public.rb_trades set undone_at = now() where id = t.id;
    perform public.rb_log('trade_undo', t.id::text, jsonb_build_object('coins', abs(net), 'taken', took));
    perform public.rb_notice(t.a, 'admin', jsonb_build_object('undo', 'trade'));
    perform public.rb_notice(t.b, 'admin', jsonb_build_object('undo', 'trade'));
    return json_build_object('coins', abs(net), 'taken', took);
end $$;

create or replace function public.rb_admin_undo_sale(listing uuid) returns json
language plpgsql security definer set search_path = '' as $$
declare me uuid := public.rb_need_admin(); l public.rb_listings%rowtype; have bigint; took integer; got integer;
begin
    select * into l from public.rb_listings where id = listing for update;
    if not found or l.state <> 'sold' or l.buyer is null then raise exception 'rb_cant_undo'; end if;
    if l.undone_at is not null then raise exception 'rb_already_undone'; end if;
    perform 1 from public.profiles where id in (l.seller, l.buyer) order by id for update;
    perform public.rb_move_back(l.item, l.what, l.seller);
    got := l.price - ceil(l.price * public.rb_cfg('market_fee'))::int;
    select coins into have from public.profiles where id = l.seller;
    took := least(got, have)::int;
    perform public.rb_pay(l.seller, -took, 0, 'sale_undo', l.id::text);
    perform public.rb_pay(l.buyer, l.price, 0, 'sale_undo', l.id::text);
    perform public.rb_fix_equip(l.buyer);
    update public.rb_listings set undone_at = now() where id = l.id;
    perform public.rb_log('sale_undo', l.what, jsonb_build_object('price', l.price, 'taken', took));
    return json_build_object('price', l.price, 'taken', took);
end $$;

-- ================================================================ quests count every mini game; profile stats
do $$ declare src text; begin
    select pg_get_functiondef('public.rb_quest_rows(uuid)'::regprocedure) into src;
    src := replace(src, 'game in (''mini'', ''park'')', 'game in (''mini'', ''park'', ''memory'')');
    execute src;
    select pg_get_functiondef('public.rb_stats(uuid)'::regprocedure) into src;
    if position('''memory''' in src) = 0 then
        src := replace(src, '''park'', (select count(*) from r where game = ''park''),',
                       '''park'', (select count(*) from r where game = ''park''), ''memory'', (select count(*) from r where game = ''memory''), ''duels'', (select count(*) from public.rb_duels d where d.state = ''done'' and d.winner = who), ''streak'', (select streak from public.profiles where id = who),');
        execute src;
    end if;
end $$;

-- ================================================================ who may call what
do $$ declare f text; begin
    for f in select p.oid::regprocedure::text from pg_catalog.pg_proc p
              join pg_catalog.pg_namespace n on n.oid = p.pronamespace
             where n.nspname = 'public' and p.proname like 'rb\_%' loop
        execute format('revoke all on function %s from public, anon, authenticated', f);
    end loop;
    for f in select p.oid::regprocedure::text from pg_catalog.pg_proc p
              join pg_catalog.pg_namespace n on n.oid = p.pronamespace
             where n.nspname = 'public' and p.proname = any (array[
                'rb_me', 'rb_delete_account', 'rb_state', 'rb_heartbeat', 'rb_hello', 'rb_hello2', 'rb_buy', 'rb_vendor_price',
                'rb_equip', 'rb_open_case', 'rb_daily_case', 'rb_case_gift', 'rb_spin', 'rb_spin_collect', 'rb_timers',
                'rb_slots', 'rb_plinko', 'rb_dice', 'rb_mines', 'rb_rocket', 'rb_blackjack',
                'rb_friend_add', 'rb_friend_remove', 'rb_friends_list', 'rb_profile', 'rb_history', 'rb_users',
                'rb_social', 'rb_avatar_set', 'rb_avatars_get', 'rb_rename',
                'rb_quests', 'rb_quest_claim', 'rb_mini_start', 'rb_mini_finish', 'rb_ledger_list',
                'rb_park_start', 'rb_park_finish', 'rb_tap_start', 'rb_tap_finish', 'rb_mem_start', 'rb_mem_flip',
                'rb_duel_ask', 'rb_duel_answer', 'rb_duel_play', 'rb_duels', 'rb_scratch', 'rb_login_state', 'rb_login_claim',
                'rb_sets', 'rb_set_claim', 'rb_leaders', 'rb_msg_send', 'rb_msg_threads', 'rb_msg_get', 'rb_msg_mute',
                'rb_trade_history', 'rb_backup_save', 'rb_backup_load',
                'rb_market_list', 'rb_market_cancel', 'rb_market_buy', 'rb_market_offer', 'rb_market_answer',
                'rb_market_offers', 'rb_market_unoffer', 'rb_admin_lock', 'rb_admin_revoke', 'rb_admin_catalog', 'rb_market_browse', 'rb_market_mine', 'rb_market_price',
                'rb_trade_request', 'rb_trade_accept', 'rb_trade_cancel', 'rb_trade_offer', 'rb_trade_ready',
                'rb_trade_confirm', 'rb_trade_get', 'rb_trades_list', 'rb_live', 'rb_giveaway_join',
                'rb_admin_stats', 'rb_admin_players', 'rb_admin_player', 'rb_admin_grant', 'rb_admin_give', 'rb_admin_take',
                'rb_admin_ban', 'rb_admin_avatar_clear', 'rb_admin_set', 'rb_admin_case', 'rb_admin_giveaway',
                'rb_admin_giveaway_end', 'rb_admin_sale', 'rb_admin_sale_end', 'rb_admin_audit',
                'rb_admin_undo', 'rb_admin_deals', 'rb_admin_undo_trade', 'rb_admin_undo_sale', 'rb_admin_resets',
                'rb_admin_reset_do', 'rb_admin_force_update']) loop
        execute format('grant execute on function %s to authenticated', f);
    end loop;
    grant execute on function public.rb_username_free(text) to anon, authenticated;
    grant execute on function public.rb_device_free(text) to anon, authenticated;
    grant execute on function public.rb_login_for(text) to anon, authenticated;
    grant execute on function public.rb_reset_ask(text, text, text) to anon, authenticated;
    grant execute on function public.rb_reset_status(uuid, text) to anon, authenticated;
end $$;
