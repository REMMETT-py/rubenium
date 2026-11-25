-- Rubenium 9.1, part 3: the Arena, fair pay without hard limits, replays for the admins, and lockdowns that never
-- lock the admins out. Safe to run twice. Undo: 080_down.sql.
--
-- 1. Lockdown: admins keep every part of Rubenium while it is on (players get rb_lockdown as before).
-- 2. Skill pay: no daily cap any more. The first rounds of each game every day pay double (the fresh bonus), then the
--    normal pay, for as long as you like. Farming with a script is caught by an integrity check instead: rounds at a
--    pace no human keeps, or a flawless run at the top level, are paid after an admin looked at them (rb_held).
-- 3. The Arena (rb_bg): Reversi and Battleships against bots from Easy to Insane, and Connect 4, Reversi and
--    Battleships duels between players (free, or for a bet). The server holds the boards, checks every move, plays
--    the bots and keeps every move with its thinking time, so every game can be replayed.
-- 4. Admin replays: every Arena game, Connect 4 game, Mini Golf match, Wave Rush run, coinflip and casino round, with
--    flags for odd patterns (one-sided pairs, inhuman pace, engine-like play).
begin;

-- ---------------------------------------------------------------- 1. lockdown: admins keep everything
create or replace function public.rb_is_admin_now() returns boolean
language sql stable security definer set search_path to '' as $$
    select coalesce((select admin from public.profiles where id = auth.uid()), false) $$;

create or replace function public.rb_need_feature(f text) returns void
language plpgsql stable security definer set search_path to '' as $$
begin
    if public.rb_is_admin_now() then return; end if;              -- 9.1: an admin plays through a lockdown
    if coalesce(public.rb_cfg('lockdown'), 0) > 0 then raise exception 'rb_lockdown'; end if;
    if not public.rb_feature_on(f) then raise exception 'rb_feature_locked'; end if;
end $$;

create or replace function public.rb_feature_open(f text) returns boolean
language sql stable security definer set search_path to '' as $$
    select public.rb_feature_on(f) or public.rb_is_admin_now() $$;

-- what players are shown (lists, live state) is open for admins too
do $patch$
declare fn text; src text;
begin
    foreach fn in array array['rb_flip_list', 'rb_jackpot_state', 'rb_live', 'rb_race_state', 'rb_advent'] loop
        for src in select pg_get_functiondef(p.oid) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                    where n.nspname = 'public' and p.proname = fn loop
            if position('public.rb_feature_on(' in src) > 0 then
                execute replace(src, 'public.rb_feature_on(', 'public.rb_feature_open(');
            end if;
        end loop;
    end loop;
end $patch$;

insert into public.rb_features (name, parent, locked) values ('arena', 'online', false) on conflict (name) do nothing;

-- ---------------------------------------------------------------- 2. fair skill pay
insert into public.rb_config (key, value) values ('skill_fresh_rounds', 8), ('skill_fresh_mult', 2), ('skill_pay_mult', 1),
    ('arena_fee', 0.05), ('arena_open_min', 10)
on conflict (key) do nothing;
insert into public.rb_config (key, value) values ('skill_day_cap', 0) on conflict (key) do update set value = 0;

create table if not exists public.rb_skill_log (
    id bigint generated always as identity primary key,
    owner uuid not null references public.profiles (id) on delete cascade,
    game text not null,
    base integer not null,
    pay integer not null,
    held boolean not null default false,
    at timestamptz not null default now());
create index if not exists rb_skill_log_owner on public.rb_skill_log (owner, game, at desc);
alter table public.rb_skill_log enable row level security;

create table if not exists public.rb_held (
    id uuid primary key default gen_random_uuid(),
    owner uuid not null references public.profiles (id) on delete cascade,
    game text not null,
    coins integer not null,
    why text not null,
    state text not null default 'held' check (state in ('held', 'paid', 'void')),
    at timestamptz not null default now(),
    by_admin uuid,
    done_at timestamptz);
create index if not exists rb_held_state on public.rb_held (state, at desc);
alter table public.rb_held enable row level security;

-- players an admin checked and trusts: their pay is never held
create table if not exists public.rb_trusted (
    owner uuid primary key references public.profiles (id) on delete cascade,
    by_admin uuid,
    at timestamptz not null default now());
alter table public.rb_trusted enable row level security;

create or replace function public.rb_skill_top(g text) returns integer
language sql immutable set search_path to '' as $$
    select case g when 'timing' then 120 when 'cups' then 150 when 'c4' then 600 when 'colour' then 90 when 'sfx' then 110
                  when 'reversi' then 700 when 'ships' then 450 else 1000000 end $$;

-- null when all is well, else why the pay waits for an admin
create or replace function public.rb_integrity(who uuid, g text, base integer) returns text
language plpgsql stable security definer set search_path to '' as $$
declare recent integer; total integer; tops integer;
        lim integer := case g when 'timing' then 90 when 'cups' then 40 when 'colour' then 60 when 'sfx' then 60 else 15 end;
begin
    if exists (select 1 from public.rb_trusted t where t.owner = who) then return null; end if;
    select count(*) into recent from public.rb_skill_log
     where owner = who and game = g and at > now() - interval '10 minutes';
    if recent >= lim then return 'pace'; end if;
    select count(*), count(*) filter (where x.base >= 0.9 * public.rb_skill_top(g)) into total, tops
      from (select l.base from public.rb_skill_log l where l.owner = who and l.game = g and l.base > 0
             order by l.at desc, l.id desc limit 29) x;
    if total >= 29 and tops >= 29 and coalesce(base, 0) >= 0.9 * public.rb_skill_top(g) then return 'flawless'; end if;
    return null;
end $$;

create or replace function public.rb_skill_window(who uuid, g text) returns jsonb
language sql stable security definer set search_path to '' as $$
    select jsonb_build_object('rounds', count(*), 'paid', coalesce(sum(l.pay) filter (where not l.held), 0),
                              'held', coalesce(sum(l.pay) filter (where l.held), 0),
                              'full', coalesce(public.rb_cfg('skill_fresh_rounds'), 8)::int,
                              'fresh_left', greatest(0, coalesce(public.rb_cfg('skill_fresh_rounds'), 8)::int - count(*)::int),
                              'fresh_mult', coalesce(public.rb_cfg('skill_fresh_mult'), 2),
                              'cap', 0)
      from public.rb_skill_log l
     where l.owner = who and l.game = g and l.at >= (public.rb_today()::timestamp at time zone 'Europe/Paris') $$;

create or replace function public.rb_skill_pay(who uuid, g text, base integer) returns integer
language plpgsql security definer set search_path to '' as $$
declare w jsonb := public.rb_skill_window(who, g); pay integer; why text;
begin
    if coalesce(base, 0) <= 0 then return 0; end if;
    pay := public.rb_scaled(round(base * coalesce(public.rb_cfg('skill_pay_mult'), 1))::int, public.rb_tier_mult(who));
    if (w ->> 'fresh_left')::int > 0 then
        pay := round(pay * coalesce(public.rb_cfg('skill_fresh_mult'), 2))::int;        -- the fresh bonus
    end if;
    why := public.rb_integrity(who, g, base);
    insert into public.rb_skill_log (owner, game, base, pay, held) values (who, g, base, pay, why is not null);
    if pay <= 0 then return 0; end if;
    if why is not null then
        insert into public.rb_held (owner, game, coins, why) values (who, g, pay, why);
        return 0;
    end if;
    perform public.rb_pay(who, pay, 0, 'skill', g);
    perform public.rb_key_find(who, g);
    return pay;
end $$;

create or replace function public.rb_skill_state() returns jsonb
language plpgsql stable security definer set search_path to '' as $$
declare me uuid := auth.uid(); out_ jsonb := '{}'::jsonb; g text;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    foreach g in array array['timing', 'cups', 'c4', 'colour', 'sfx', 'reversi', 'ships'] loop
        out_ := out_ || jsonb_build_object(g, public.rb_skill_window(me, g));
    end loop;
    return out_ || jsonb_build_object('mult', public.rb_tier_mult(me),
        'held', (select coalesce(sum(coins), 0) from public.rb_held where owner = me and state = 'held'),
        'resets', greatest(0, ceil(extract(epoch from (((public.rb_today() + 1)::timestamp at time zone 'Europe/Paris') - now()))))::int);
end $$;

-- ---------------------------------------------------------------- 3. the Arena
create table if not exists public.rb_bg (
    id uuid primary key default gen_random_uuid(),
    kind text not null check (kind in ('c4', 'reversi', 'ships')),
    a uuid not null references public.profiles (id) on delete cascade,
    b uuid references public.profiles (id) on delete cascade,      -- null: the bot
    level text,                                                     -- the bot's level (null in a duel)
    bet integer not null default 0,
    state text not null default 'open' check (state in ('open', 'live', 'done', 'cancelled')),
    board jsonb not null default '{}'::jsonb,
    secret jsonb not null default '{}'::jsonb,                     -- Battleships fleets: never sent to a player
    turn integer not null default 1,
    moves jsonb not null default '[]'::jsonb,                      -- [{s: side, m: move, ms: thinking time}]
    winner integer,                                                 -- 1, 2, 0 for a draw
    why text,
    paid integer not null default 0,
    at timestamptz not null default now(),
    live_at timestamptz,
    turn_at timestamptz,
    done_at timestamptz);
create index if not exists rb_bg_a on public.rb_bg (a, state);
create index if not exists rb_bg_b on public.rb_bg (b, state);
create index if not exists rb_bg_open on public.rb_bg (state, at desc);
alter table public.rb_bg enable row level security;

create or replace function public.rb_bg_turn_secs(kind text) returns integer
language sql immutable set search_path to '' as $$
    select case kind when 'reversi' then 45 when 'ships' then 30 else 30 end $$;

-- -- Connect 4 (42 cells, row 0 at the bottom, cell = row * 7 + column)
create or replace function public.c4_drop(b text, col integer) returns integer
language plpgsql immutable set search_path to '' as $$
declare r integer;
begin
    if col is null or col < 0 or col > 6 then return -1; end if;
    for r in 0 .. 5 loop
        if substr(b, r * 7 + col + 1, 1) = '.' then return r * 7 + col; end if;
    end loop;
    return -1;
end $$;

create or replace function public.c4_wins(b text, cell integer) returns boolean
language plpgsql immutable set search_path to '' as $$
declare p text := substr(b, cell + 1, 1); r0 integer := cell / 7; c0 integer := cell % 7; d integer; dr integer; dc integer;
        n integer; r integer; c integer; s integer;
begin
    if p = '.' then return false; end if;
    for d in 1 .. 4 loop
        dr := (array[0, 1, 1, 1])[d]; dc := (array[1, 0, 1, -1])[d];
        n := 1;
        foreach s in array array[1, -1] loop
            r := r0 + dr * s; c := c0 + dc * s;
            while r between 0 and 5 and c between 0 and 6 and substr(b, r * 7 + c + 1, 1) = p loop
                n := n + 1; r := r + dr * s; c := c + dc * s;
            end loop;
        end loop;
        if n >= 4 then return true; end if;
    end loop;
    return false;
end $$;

-- -- Reversi (64 cells, cell = row * 8 + column; side 1 is black and starts)
create or replace function public.rv_flips(b text, i integer, p text) returns integer[]
language plpgsql immutable set search_path to '' as $$
declare r0 integer := i / 8; c0 integer := i % 8; o text := case p when '1' then '2' else '1' end; out_ integer[] := '{}';
        d integer; dr integer; dc integer; r integer; c integer; line integer[];
begin
    if i is null or i < 0 or i > 63 or substr(b, i + 1, 1) <> '.' then return out_; end if;
    for d in 1 .. 8 loop
        dr := (array[-1, -1, -1, 0, 0, 1, 1, 1])[d]; dc := (array[-1, 0, 1, -1, 1, -1, 0, 1])[d];
        r := r0 + dr; c := c0 + dc; line := '{}';
        while r between 0 and 7 and c between 0 and 7 and substr(b, r * 8 + c + 1, 1) = o loop
            line := line || (r * 8 + c); r := r + dr; c := c + dc;
        end loop;
        if cardinality(line) > 0 and r between 0 and 7 and c between 0 and 7 and substr(b, r * 8 + c + 1, 1) = p then
            out_ := out_ || line;
        end if;
    end loop;
    return out_;
end $$;

create or replace function public.rv_moves(b text, p text) returns integer[]
language plpgsql immutable set search_path to '' as $$
declare i integer; out_ integer[] := '{}';
begin
    for i in 0 .. 63 loop
        if substr(b, i + 1, 1) = '.' and cardinality(public.rv_flips(b, i, p)) > 0 then out_ := out_ || i; end if;
    end loop;
    return out_;
end $$;

create or replace function public.rv_play(b text, i integer, p text) returns text
language plpgsql immutable set search_path to '' as $$
declare f integer[] := public.rv_flips(b, i, p); x integer;
begin
    if cardinality(f) = 0 then return null; end if;
    b := overlay(b placing p from i + 1 for 1);
    foreach x in array f loop b := overlay(b placing p from x + 1 for 1); end loop;
    return b;
end $$;

create or replace function public.rv_count(b text, p text) returns integer
language sql immutable set search_path to '' as $$ select length(b) - length(replace(b, p, '')) $$;

-- the board seen by side p: corners, edges, the squares next to an empty corner are bad, and late on every disc counts
create or replace function public.rv_eval(b text, p text) returns integer
language plpgsql immutable set search_path to '' as $$
declare w integer[] := array[100, -20, 10, 5, 5, 10, -20, 100, -20, -50, -2, -2, -2, -2, -50, -20, 10, -2, -1, -1, -1, -1, -2, 10,
                             5, -2, -1, -1, -1, -1, -2, 5, 5, -2, -1, -1, -1, -1, -2, 5, 10, -2, -1, -1, -1, -1, -2, 10,
                             -20, -50, -2, -2, -2, -2, -50, -20, 100, -20, 10, 5, 5, 10, -20, 100];
        o text := case p when '1' then '2' else '1' end; i integer; s integer := 0; ch text; corner integer; k integer;
        empty integer;
begin
    foreach corner in array array[0, 7, 56, 63] loop           -- a taken corner makes its neighbours safe
        if substr(b, corner + 1, 1) <> '.' then
            foreach k in array case corner when 0 then array[1, 8, 9] when 7 then array[6, 14, 15]
                                           when 56 then array[48, 49, 57] else array[54, 55, 62] end loop
                w[k + 1] := 8;
            end loop;
        end if;
    end loop;
    for i in 0 .. 63 loop
        ch := substr(b, i + 1, 1);
        if ch = p then s := s + w[i + 1]; elsif ch = o then s := s - w[i + 1]; end if;
    end loop;
    empty := public.rv_count(b, '.');
    if empty <= 12 then s := s + (public.rv_count(b, p) - public.rv_count(b, o)) * (14 - empty) * 2; end if;
    if empty = 0 then s := (public.rv_count(b, p) - public.rv_count(b, o)) * 1000; end if;
    return s;
end $$;

-- negamax with alpha-beta: the Insane bot looks three moves ahead (more near the end)
create or replace function public.rv_search(b text, p text, depth integer, alpha integer, beta integer) returns integer
language plpgsql immutable set search_path to '' as $$
declare o text := case p when '1' then '2' else '1' end; mv integer[]; m integer; v integer; best integer := -1000000;
begin
    if depth <= 0 then return public.rv_eval(b, p); end if;
    mv := public.rv_moves(b, p);
    if cardinality(mv) = 0 then
        if cardinality(public.rv_moves(b, o)) = 0 then
            return (public.rv_count(b, p) - public.rv_count(b, o)) * 1000;
        end if;
        return -public.rv_search(b, o, depth - 1, -beta, -alpha);
    end if;
    -- corners and edges first: they cut the search sooner
    mv := array(select x from unnest(mv) x order by case when x in (0, 7, 56, 63) then 0
                                                         when x in (1, 6, 8, 9, 14, 15, 48, 49, 54, 55, 57, 62) then 3
                                                         when x / 8 in (0, 7) or x % 8 in (0, 7) then 1 else 2 end);
    foreach m in array mv loop
        v := -public.rv_search(public.rv_play(b, m, p), o, depth - 1, -beta, -alpha);
        if v > best then best := v; end if;
        if v > alpha then alpha := v; end if;
        if alpha >= beta then exit; end if;
    end loop;
    return best;
end $$;

create or replace function public.rv_bot(b text, p text, level text) returns integer
language plpgsql volatile set search_path to '' as $$
declare o text := case p when '1' then '2' else '1' end; mv integer[] := public.rv_moves(b, p); m integer; r integer;
        b1 text; b2 text; replies integer[]; v integer; worst integer; best integer := null; pick integer;
begin
    if cardinality(mv) = 0 then return null; end if;
    if level = 'easy' then return mv[1 + floor(public.rb_rand() * cardinality(mv))::int]; end if;
    if level = 'medium' and public.rb_rand() < 0.35 then return mv[1 + floor(public.rb_rand() * cardinality(mv))::int]; end if;
    foreach m in array mv loop
        b1 := public.rv_play(b, m, p);
        if level = 'medium' then
            v := cardinality(public.rv_flips(b, m, p)) * 10;
        elsif level = 'hard' then
            v := public.rv_eval(b1, p) - 6 * cardinality(public.rv_moves(b1, o));
        elsif level = 'insane' then                             -- insane: three moves ahead, deeper at the end
            v := -public.rv_search(b1, o, case when public.rv_count(b, '.') <= 7 then 6 else 2 end, -1000000, 1000000);
        else                                                    -- (not used) one answer deep
            replies := public.rv_moves(b1, o);
            if cardinality(replies) = 0 then
                v := public.rv_eval(b1, p) + 60;                 -- they must pass: great
            else
                worst := null;
                foreach r in array replies loop
                    b2 := public.rv_play(b1, r, o);
                    v := public.rv_eval(b2, p);
                    if worst is null or v < worst then worst := v; end if;
                end loop;
                v := worst - 5 * cardinality(replies);
            end if;
        end if;
        v := v * 4 + floor(public.rb_rand() * 4)::int;           -- equal moves: not always the same one
        if best is null or v > best then best := v; pick := m; end if;
    end loop;
    return pick;
end $$;

-- -- Battleships (10 x 10, cell = row * 10 + column; ships 5, 4, 3, 3, 2)
create or replace function public.sh_fleet() returns jsonb
language plpgsql volatile set search_path to '' as $$
declare sizes integer[] := array[5, 4, 3, 3, 2]; L integer; used integer[] := '{}'; ship integer[]; tries integer;
        r integer; c integer; h boolean; k integer; ok boolean; out_ jsonb := '[]'::jsonb;
begin
    foreach L in array sizes loop
        tries := 0;
        loop
            tries := tries + 1;
            h := public.rb_rand() < 0.5;
            r := floor(public.rb_rand() * (case when h then 10 else 11 - L end))::int;
            c := floor(public.rb_rand() * (case when h then 11 - L else 10 end))::int;
            ship := '{}'; ok := true;
            for k in 0 .. L - 1 loop
                ship := ship || (case when h then r * 10 + c + k else (r + k) * 10 + c end);
            end loop;
            if ship && used then ok := false; end if;
            if ok then exit; end if;
            if tries > 500 then raise exception 'rb_try_again'; end if;
        end loop;
        used := used || ship;
        out_ := out_ || jsonb_build_array(to_jsonb(ship));
    end loop;
    return out_;
end $$;

-- the shots side p has fired, as seen by p: '.' unknown, 'o' miss, 'x' hit, 's' sunk
create or replace function public.sh_shoot(grid text, fleet jsonb, i integer, OUT grid_out text, OUT hit boolean,
                                           OUT sunk integer, OUT won boolean)
language plpgsql immutable set search_path to '' as $$
declare ship jsonb; cells integer[]; x integer; all_hit boolean;
begin
    grid_out := grid; hit := false; sunk := 0; won := false;
    if i is null or i < 0 or i > 99 or substr(grid, i + 1, 1) <> '.' then grid_out := null; return; end if;
    for ship in select * from jsonb_array_elements(fleet) loop
        cells := array(select (v #>> '{}')::int from jsonb_array_elements(ship) v);
        if i = any (cells) then
            hit := true;
            grid_out := overlay(grid_out placing 'x' from i + 1 for 1);
            all_hit := true;
            foreach x in array cells loop
                if substr(grid_out, x + 1, 1) not in ('x', 's') then all_hit := false; end if;
            end loop;
            if all_hit then
                sunk := cardinality(cells);
                foreach x in array cells loop grid_out := overlay(grid_out placing 's' from x + 1 for 1); end loop;
            end if;
        end if;
    end loop;
    if not hit then grid_out := overlay(grid_out placing 'o' from i + 1 for 1); end if;
    won := length(grid_out) - length(replace(grid_out, 's', '')) = 17;
end $$;

-- where the bot fires: easy at random, medium finishes ships it hit, hard hunts on a checkerboard, insane counts
-- every place the remaining ships could still be
create or replace function public.sh_bot(grid text, left_ integer[], level text) returns integer
language plpgsql volatile set search_path to '' as $$
declare i integer; r integer; c integer; free_ integer[] := '{}'; cand integer[] := '{}'; hits integer[] := '{}';
        L integer; h boolean; k integer; ok boolean; covers_hit integer; heat integer[] := array_fill(0, array[100]);
        best integer := -1; pick integer; cell integer; ch text; dirs integer[] := array[-10, 10, -1, 1]; d integer;
begin
    for i in 0 .. 99 loop
        ch := substr(grid, i + 1, 1);
        if ch = '.' then free_ := free_ || i; elsif ch = 'x' then hits := hits || i; end if;
    end loop;
    if cardinality(free_) = 0 then return null; end if;
    if level = 'easy' then return free_[1 + floor(public.rb_rand() * cardinality(free_))::int]; end if;
    if level in ('medium', 'hard') then
        if cardinality(hits) > 0 then                           -- finish what was hit
            if level = 'hard' and cardinality(hits) >= 2 then    -- along the line the hits make
                foreach i in array hits loop
                    foreach d in array dirs loop
                        cell := i + d;
                        if cell between 0 and 99 and (abs(d) = 10 or cell / 10 = i / 10)
                           and substr(grid, cell + 1, 1) = '.' and (i - d) = any (hits) then cand := cand || cell; end if;
                    end loop;
                end loop;
            end if;
            if cardinality(cand) = 0 then
                foreach i in array hits loop
                    foreach d in array dirs loop
                        cell := i + d;
                        if cell between 0 and 99 and (abs(d) = 10 or cell / 10 = i / 10) and substr(grid, cell + 1, 1) = '.' then
                            cand := cand || cell;
                        end if;
                    end loop;
                end loop;
            end if;
            if cardinality(cand) > 0 then return cand[1 + floor(public.rb_rand() * cardinality(cand))::int]; end if;
        end if;
        if level = 'hard' then
            cand := array(select x from unnest(free_) x where (x / 10 + x % 10) % 2 = 0);
            if cardinality(cand) > 0 then return cand[1 + floor(public.rb_rand() * cardinality(cand))::int]; end if;
        end if;
        return free_[1 + floor(public.rb_rand() * cardinality(free_))::int];
    end if;
    -- insane: a heat map of every way the ships left can lie (a place over a hit counts a lot)
    foreach L in array coalesce(left_, array[5, 4, 3, 3, 2]) loop
        for r in 0 .. 9 loop
            for c in 0 .. 9 loop
                foreach h in array array[true, false] loop
                    if (h and c + L > 10) or (not h and r + L > 10) then continue; end if;
                    ok := true; covers_hit := 0;
                    for k in 0 .. L - 1 loop
                        cell := case when h then r * 10 + c + k else (r + k) * 10 + c end;
                        ch := substr(grid, cell + 1, 1);
                        if ch in ('o', 's') then ok := false; exit; end if;
                        if ch = 'x' then covers_hit := covers_hit + 1; end if;
                    end loop;
                    if not ok or (cardinality(hits) > 0 and covers_hit = 0) then continue; end if;
                    for k in 0 .. L - 1 loop
                        cell := case when h then r * 10 + c + k else (r + k) * 10 + c end;
                        if substr(grid, cell + 1, 1) = '.' then
                            heat[cell + 1] := heat[cell + 1] + 1 + covers_hit * 30;
                        end if;
                    end loop;
                end loop;
            end loop;
        end loop;
    end loop;
    foreach i in array free_ loop
        k := heat[i + 1] * 8 + floor(public.rb_rand() * 8)::int;
        if k > best then best := k; pick := i; end if;
    end loop;
    return pick;
end $$;

-- -- the game itself
create or replace function public.rb_bg_new_board(kind text) returns jsonb
language sql volatile set search_path to '' as $$
    select case kind
        when 'c4' then jsonb_build_object('b', repeat('.', 42))
        when 'reversi' then jsonb_build_object('b', repeat('.', 27) || '21......12' || repeat('.', 27))
        else jsonb_build_object('h1', repeat('.', 100), 'h2', repeat('.', 100), 'left1', jsonb_build_array(5, 4, 3, 3, 2),
                                'left2', jsonb_build_array(5, 4, 3, 3, 2)) end $$;

create or replace function public.rb_bg_busy(who uuid) returns boolean
language sql stable security definer set search_path to '' as $$
    select exists (select 1 from public.rb_bg g where (g.a = who or g.b = who) and g.state in ('open', 'live')) $$;

-- what one side sees
create or replace function public.rb_bg_json(g public.rb_bg, me uuid) returns jsonb
language plpgsql stable security definer set search_path to '' as $$
declare side integer := case when g.a = me then 1 when g.b = me then 2 else 0 end; out_ jsonb; mine jsonb;
begin
    out_ := jsonb_build_object('id', g.id, 'kind', g.kind, 'level', g.level, 'bet', g.bet, 'state', g.state,
        'side', side, 'turn', g.turn, 'n', jsonb_array_length(g.moves),
        'last', case when jsonb_array_length(g.moves) > 0 then g.moves -> (jsonb_array_length(g.moves) - 1) end,
        'winner', g.winner, 'why', g.why, 'paid', g.paid, 'bot', g.level is not null,     -- an open duel has no b yet
        'a', (select username from public.profiles where id = g.a),
        'b', case when g.b is not null then (select username from public.profiles where id = g.b)
                  when g.level is not null then initcap(g.level) || ' bot' end,
        'secs', case when g.state = 'live' then greatest(0, ceil(extract(epoch from g.turn_at
                       + make_interval(secs => public.rb_bg_turn_secs(g.kind)) - now())))::int end);
    if g.kind = 'ships' then
        mine := case when side = 2 then g.secret -> 'f2' else g.secret -> 'f1' end;
        out_ := out_ || jsonb_build_object(
            'shots', case when side = 2 then g.board -> 'h2' else g.board -> 'h1' end,          -- my shots at them
            'taken', case when side = 2 then g.board -> 'h1' else g.board -> 'h2' end,          -- their shots at me
            'fleet', case when side > 0 then mine end,
            'left', case when side = 2 then g.board -> 'left1' else g.board -> 'left2' end);   -- their ships still afloat
        if g.state = 'done' then
            out_ := out_ || jsonb_build_object('their', case when side = 2 then g.secret -> 'f1' else g.secret -> 'f2' end);
        end if;
    else
        out_ := out_ || jsonb_build_object('board', g.board -> 'b');      -- 'a' and 'b' are the names
        if g.kind = 'reversi' and g.state = 'live' and side = g.turn then
            out_ := out_ || jsonb_build_object('legal', to_jsonb(public.rv_moves(g.board ->> 'b', side::text)));
        end if;
    end if;
    return out_;
end $$;

-- what a finished game pays: bot games are free and pay by skill; duels pay the pot
create or replace function public.rb_bg_base(g public.rb_bg) returns integer
language plpgsql stable security definer set search_path to '' as $$
declare base integer; f numeric := 1; shots integer; mine integer; theirs integer;
begin
    if g.kind = 'reversi' then
        base := case g.level when 'easy' then 40 when 'medium' then 100 when 'hard' then 250 when 'insane' then 700 else 0 end;
        mine := public.rv_count(g.board ->> 'b', '1'); theirs := public.rv_count(g.board ->> 'b', '2');
        f := 1 + least(0.5, greatest(0, mine - theirs) / 64.0);          -- a bigger win pays up to half more
    elsif g.kind = 'ships' then
        base := case g.level when 'easy' then 30 when 'medium' then 80 when 'hard' then 180 when 'insane' then 450 else 0 end;
        shots := 100 - (length(g.board ->> 'h1') - length(replace(g.board ->> 'h1', '.', '')));   -- shots fired
        f := 1 + least(0.5, greatest(0, 60 - shots) / 60.0);              -- fewer shots pay up to half more
    else
        base := 0;
    end if;
    if g.winner = 0 then return base / 4; end if;
    if g.winner <> 1 then return 0; end if;
    return round(base * f)::int;
end $$;

create or replace function public.rb_bg_end(gid uuid, win integer, why text) returns void
language plpgsql security definer set search_path to '' as $$
declare g public.rb_bg%rowtype; pay integer := 0; pot integer; loser uuid; w uuid;
begin
    select * into g from public.rb_bg where id = gid for update;
    if not found or g.state <> 'live' then return; end if;
    g.winner := win;
    if g.b is null then                                           -- against the bot
        pay := public.rb_skill_pay(g.a, g.kind, public.rb_bg_base(g));
        insert into public.rb_rounds (owner, game, bet, secret, open, paid)
            values (g.a, g.kind, 0, jsonb_build_object('level', g.level, 'outcome', case win when 1 then 'win' when 0 then 'draw'
                                                        else 'loss' end, 'bg', g.id), false, pay);
        if win = 1 then perform public.rb_xp_add(g.a, case g.level when 'insane' then 60 when 'hard' then 35 else 15 end,
                                                 'arena', g.id::text); end if;
    else                                                          -- a duel
        w := case win when 1 then g.a when 2 then g.b end;
        if g.bet > 0 then
            if win = 0 then
                perform public.rb_pay(g.a, g.bet, 0, 'arena_back', g.id::text);
                perform public.rb_pay(g.b, g.bet, 0, 'arena_back', g.id::text);
            else
                pot := floor(g.bet * 2 * (1 - coalesce(public.rb_cfg('arena_fee'), 0.05)))::int;
                perform public.rb_pay(w, pot, 0, 'arena_win', g.id::text);
                pay := pot;
            end if;
        end if;
        if w is not null then perform public.rb_xp_add(w, 40, 'arena', g.id::text); end if;
        loser := case win when 1 then g.b when 2 then g.a end;
        perform public.rb_notice(x, 'arena_end', jsonb_build_object('id', g.id, 'kind', g.kind, 'won', x = w, 'draw', win = 0,
                                 'other', (select username from public.profiles where id = case when x = g.a then g.b else g.a end)))
           from unnest(array[g.a, g.b]) x;
    end if;
    update public.rb_bg set state = 'done', winner = win, why = rb_bg_end.why, paid = pay, done_at = now() where id = gid;
end $$;

-- one move by side s (already checked to be its turn). Returns false when the move is not allowed.
create or replace function public.rb_bg_apply(gid uuid, s integer, m integer) returns boolean
language plpgsql security definer set search_path to '' as $$
declare g public.rb_bg%rowtype; bd text; cell integer; p text := s::text; o text := (3 - s)::text; shot record;
        think integer; nb jsonb; lefts jsonb; key_h text; key_l text;
begin
    select * into g from public.rb_bg where id = gid for update;
    if not found or g.state <> 'live' or g.turn <> s then return false; end if;
    think := least(600000, greatest(0, floor(extract(epoch from now() - coalesce(g.turn_at, now())) * 1000)))::int;
    if g.kind = 'c4' then
        bd := g.board ->> 'b';
        cell := public.c4_drop(bd, m);
        if cell < 0 then return false; end if;
        bd := overlay(bd placing p from cell + 1 for 1);
        update public.rb_bg set board = jsonb_build_object('b', bd), turn = 3 - s, turn_at = now(),
               moves = moves || jsonb_build_array(jsonb_build_object('s', s, 'm', m, 'ms', think)) where id = gid;
        if public.c4_wins(bd, cell) then perform public.rb_bg_end(gid, s, 'four');
        elsif position('.' in bd) = 0 then perform public.rb_bg_end(gid, 0, 'full'); end if;
    elsif g.kind = 'reversi' then
        bd := public.rv_play(g.board ->> 'b', m, p);
        if bd is null then return false; end if;
        if cardinality(public.rv_moves(bd, o)) > 0 then
            update public.rb_bg set board = jsonb_build_object('b', bd), turn = 3 - s, turn_at = now(),
                   moves = moves || jsonb_build_array(jsonb_build_object('s', s, 'm', m, 'ms', think)) where id = gid;
        elsif cardinality(public.rv_moves(bd, p)) > 0 then           -- the other side has no move: it passes
            update public.rb_bg set board = jsonb_build_object('b', bd), turn = s, turn_at = now(),
                   moves = moves || jsonb_build_array(jsonb_build_object('s', s, 'm', m, 'ms', think),
                                                      jsonb_build_object('s', 3 - s, 'm', -1, 'ms', 0)) where id = gid;
        else                                                       -- nobody can move: count the discs
            update public.rb_bg set board = jsonb_build_object('b', bd),
                   moves = moves || jsonb_build_array(jsonb_build_object('s', s, 'm', m, 'ms', think)) where id = gid;
            perform public.rb_bg_end(gid, case when public.rv_count(bd, '1') > public.rv_count(bd, '2') then 1
                                               when public.rv_count(bd, '2') > public.rv_count(bd, '1') then 2 else 0 end, 'discs');
        end if;
    else
        key_h := 'h' || s; key_l := 'left' || (3 - s);
        select * into shot from public.sh_shoot(g.board ->> key_h, g.secret -> ('f' || (3 - s)), m);
        if shot.grid_out is null then return false; end if;
        lefts := g.board -> key_l;
        if shot.sunk > 0 then                                      -- that size is no longer afloat (one of them)
            lefts := coalesce((select jsonb_agg(v) from (select v, row_number() over (partition by v order by ord) rn
                                                           from jsonb_array_elements(lefts) with ordinality e(v, ord)) z
                                where not (v = to_jsonb(shot.sunk) and rn = 1)), '[]'::jsonb);
        end if;
        nb := g.board || jsonb_build_object(key_h, shot.grid_out, key_l, lefts);
        update public.rb_bg set board = nb, turn = case when shot.hit then s else 3 - s end, turn_at = now(),
               moves = moves || jsonb_build_array(jsonb_build_object('s', s, 'm', m, 'ms', think, 'hit', shot.hit,
                                                                     'sunk', shot.sunk)) where id = gid;
        if shot.won then perform public.rb_bg_end(gid, s, 'fleet'); end if;
    end if;
    return true;
end $$;

-- the bot plays until it is the player's turn again (Battleships: a hit fires again)
create or replace function public.rb_bg_bot_turns(gid uuid) returns void
language plpgsql security definer set search_path to '' as $$
declare g public.rb_bg%rowtype; m integer; n integer := 0; lefts integer[];
begin
    loop
        select * into g from public.rb_bg where id = gid;
        exit when not found or g.state <> 'live' or g.b is not null or g.turn <> 2 or n > 120;
        n := n + 1;
        if g.kind = 'reversi' then
            m := public.rv_bot(g.board ->> 'b', '2', g.level);
        elsif g.kind = 'ships' then
            lefts := array(select (v #>> '{}')::int from jsonb_array_elements(g.board -> 'left1') v);
            m := public.sh_bot(g.board ->> 'h2', lefts, g.level);
        else
            exit;
        end if;
        if m is null or not public.rb_bg_apply(gid, 2, m) then exit; end if;
    end loop;
end $$;

-- time runs out: the side whose turn it is loses (an open duel nobody joins is given back)
create or replace function public.rb_bg_tick(gid uuid) returns void
language plpgsql security definer set search_path to '' as $$
declare g public.rb_bg%rowtype;
begin
    select * into g from public.rb_bg where id = gid for update;
    if not found then return; end if;
    if g.state = 'open' and g.at < now() - make_interval(mins => coalesce(public.rb_cfg('arena_open_min'), 10)::int) then
        update public.rb_bg set state = 'cancelled', why = 'nobody', done_at = now() where id = gid;
        if g.bet > 0 then perform public.rb_pay(g.a, g.bet, 0, 'arena_back', g.id::text); end if;
    elsif g.state = 'live' and g.turn_at + make_interval(secs => public.rb_bg_turn_secs(g.kind) + 3) < now() then
        perform public.rb_bg_end(gid, 3 - g.turn, 'time');
    end if;
end $$;

create or replace function public.rb_bg_tick_mine(who uuid) returns void
language plpgsql security definer set search_path to '' as $$
declare r record;
begin
    for r in select id from public.rb_bg where (a = who or b = who) and state in ('open', 'live') loop
        perform public.rb_bg_tick(r.id);
    end loop;
end $$;

-- start a game against a bot (free; it pays by how well you play)
create or replace function public.rb_bg_bot(kind text, level text) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; g public.rb_bg%rowtype; sec jsonb := '{}'::jsonb; first_ integer := 1;
begin
    perform public.rb_rate(auth.uid(), 'arena', 20);
    perform public.rb_need_feature('minigames');
    p := public.rb_lock_me();
    if kind not in ('reversi', 'ships') or level not in ('easy', 'medium', 'hard', 'insane') then raise exception 'rb_bad_choice'; end if;
    perform public.rb_bg_tick_mine(p.id);
    update public.rb_bg set state = 'cancelled', why = 'left', done_at = now()      -- an old bot game you walked away from
     where a = p.id and b is null and state = 'live';
    if public.rb_bg_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    if kind = 'ships' then
        sec := jsonb_build_object('f1', public.sh_fleet(), 'f2', public.sh_fleet());
        first_ := case when public.rb_rand() < 0.5 then 1 else 2 end;
    end if;
    insert into public.rb_bg (kind, a, b, level, state, board, secret, turn, live_at, turn_at)
        values (kind, p.id, null, level, 'live', public.rb_bg_new_board(kind), sec, first_, now(), now()) returning * into g;
    perform public.rb_bg_bot_turns(g.id);
    select * into g from public.rb_bg where id = g.id;
    return public.rb_bg_json(g, p.id);
end $$;

-- Battleships against the bot: place your fleet again before the first shot
create or replace function public.rb_bg_shuffle(gid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); g public.rb_bg%rowtype;
begin
    select * into g from public.rb_bg where id = gid and a = me and b is null and kind = 'ships' and state = 'live' for update;
    if not found then raise exception 'rb_round_gone'; end if;
    if jsonb_array_length(g.moves) > 0 then raise exception 'rb_too_late'; end if;
    update public.rb_bg set secret = secret || jsonb_build_object('f1', public.sh_fleet()) where id = gid returning * into g;
    return public.rb_bg_json(g, me);
end $$;

-- open a duel (free or for a bet) for anyone to join
create or replace function public.rb_bg_create(kind text, bet integer) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; g public.rb_bg%rowtype;
begin
    perform public.rb_rate(auth.uid(), 'duel', 10);
    perform public.rb_need_feature('arena');
    p := public.rb_lock_me();
    if kind not in ('c4', 'reversi', 'ships') then raise exception 'rb_bad_choice'; end if;
    perform public.rb_bg_tick_mine(p.id);
    if public.rb_bg_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    bet := coalesce(bet, 0);
    if bet <> 0 and (bet < 10 or bet % 10 <> 0 or bet > public.rb_golf_cap(p.coins)) then raise exception 'rb_bad_bet'; end if;
    if bet > 0 then perform public.rb_pay(p.id, -bet, 0, 'arena_bet', kind); end if;
    insert into public.rb_bg (kind, a, bet, state, board) values (kind, p.id, bet, 'open', public.rb_bg_new_board(kind))
        returning * into g;
    return public.rb_bg_json(g, p.id) || jsonb_build_object('coins', p.coins - bet);
end $$;

create or replace function public.rb_bg_join(gid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; g public.rb_bg%rowtype; sec jsonb := '{}'::jsonb;
begin
    perform public.rb_rate(auth.uid(), 'duel', 10);
    perform public.rb_need_feature('arena');
    p := public.rb_lock_me();
    perform public.rb_bg_tick(gid);
    select * into g from public.rb_bg where id = gid for update;
    if not found or g.state <> 'open' then raise exception 'rb_duel_gone'; end if;
    if g.a = p.id then raise exception 'rb_thats_you'; end if;
    perform public.rb_bg_tick_mine(p.id);
    if public.rb_bg_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    if p.coins < g.bet then raise exception 'rb_not_enough'; end if;
    if g.bet > 0 then perform public.rb_pay(p.id, -g.bet, 0, 'arena_bet', g.kind); end if;
    if g.kind = 'ships' then sec := jsonb_build_object('f1', public.sh_fleet(), 'f2', public.sh_fleet()); end if;
    update public.rb_bg set b = p.id, state = 'live', secret = sec, live_at = now(), turn_at = now(),
           turn = case when public.rb_rand() < 0.5 then 1 else 2 end where id = gid returning * into g;
    perform public.rb_notice(g.a, 'arena_join', jsonb_build_object('from', p.username, 'id', g.id, 'kind', g.kind));
    return public.rb_bg_json(g, p.id) || jsonb_build_object('coins', p.coins - g.bet);
end $$;

create or replace function public.rb_bg_cancel(gid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); g public.rb_bg%rowtype;
begin
    select * into g from public.rb_bg where id = gid and a = me and state = 'open' for update;
    if not found then raise exception 'rb_duel_gone'; end if;
    update public.rb_bg set state = 'cancelled', why = 'cancelled', done_at = now() where id = gid;
    if g.bet > 0 then perform public.rb_pay(me, g.bet, 0, 'arena_back', g.id::text); end if;
    return jsonb_build_object('ok', true);
end $$;

-- play a move. n: how many moves you have seen (a move sent twice is not played twice)
create or replace function public.rb_bg_move(gid uuid, m integer, n integer) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); g public.rb_bg%rowtype; side integer;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_rate(me, 'arena_move', 120);
    perform public.rb_bg_tick(gid);
    select * into g from public.rb_bg where id = gid and (a = me or b = me);
    if not found then raise exception 'rb_round_gone'; end if;
    if g.state <> 'live' then return public.rb_bg_json(g, me); end if;
    if g.b is null then perform public.rb_need_feature('minigames'); else perform public.rb_need_feature('arena'); end if;
    side := case when g.a = me then 1 else 2 end;
    if n is not null and n <> jsonb_array_length(g.moves) then return public.rb_bg_json(g, me); end if;
    if g.turn <> side then raise exception 'rb_not_your_turn'; end if;
    if not public.rb_bg_apply(gid, side, m) then raise exception 'rb_bad_choice'; end if;
    perform public.rb_bg_bot_turns(gid);
    select * into g from public.rb_bg where id = gid;
    return public.rb_bg_json(g, me);
end $$;

create or replace function public.rb_bg_resign(gid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); g public.rb_bg%rowtype;
begin
    select * into g from public.rb_bg where id = gid and (a = me or b = me) for update;
    if not found then raise exception 'rb_round_gone'; end if;
    if g.state = 'live' then perform public.rb_bg_end(gid, case when g.a = me then 2 else 1 end, 'resign'); end if;
    select * into g from public.rb_bg where id = gid;
    return public.rb_bg_json(g, me);
end $$;

create or replace function public.rb_bg_state(gid uuid) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); g public.rb_bg%rowtype;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_bg_tick(gid);
    select * into g from public.rb_bg where id = gid and (a = me or b = me);
    if not found then raise exception 'rb_round_gone'; end if;
    return public.rb_bg_json(g, me);
end $$;

-- the Arena screen: open duels, your current game, your record
create or replace function public.rb_bg_lobbies() returns jsonb
language plpgsql security definer set search_path to '' as $$
declare me uuid := auth.uid(); cur public.rb_bg%rowtype; r record;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    for r in select id from public.rb_bg where state = 'open' and at < now() - interval '9 minutes' loop
        perform public.rb_bg_tick(r.id);
    end loop;
    perform public.rb_bg_tick_mine(me);
    select * into cur from public.rb_bg where (a = me or b = me) and state in ('open', 'live') order by at desc limit 1;
    return jsonb_build_object(
        'open', coalesce((select jsonb_agg(jsonb_build_object('id', g.id, 'kind', g.kind, 'bet', g.bet,
                                                              'name', p.username, 'mine', g.a = me,
                                                              'friend', public.rb_is_friend(me, g.a)) order by g.at desc)
                            from public.rb_bg g join public.profiles p on p.id = g.a
                           where g.state = 'open' and not p.banned), '[]'::jsonb),
        'mine', case when cur.id is not null then public.rb_bg_json(cur, me) end,
        'record', (select jsonb_object_agg(k, v) from (
                      select g.kind || case when g.b is null then ':' || g.level else ':duel' end k,
                             jsonb_build_object('played', count(*),
                                                'won', count(*) filter (where (g.winner = 1 and g.a = me) or (g.winner = 2 and g.b = me)))
                        v
                        from public.rb_bg g where (g.a = me or g.b = me) and g.state = 'done' group by 1) z),
        'skill', public.rb_skill_state());
end $$;

-- a lockdown (or Arena paused) stops every Arena game and gives the bets back
create or replace function public.rb_bg_cleanup(f text) returns integer
language plpgsql security definer set search_path to '' as $$
declare g public.rb_bg%rowtype; n integer := 0;
begin
    if f not in ('arena', 'online', 'all', 'minigames') then return 0; end if;
    for g in select * from public.rb_bg where state in ('open', 'live')
                                         and (f <> 'minigames' or level is not null) and (f <> 'arena' or level is null) for update loop
        update public.rb_bg set state = 'cancelled', why = 'lockdown', done_at = now() where id = g.id;
        if g.bet > 0 then
            perform public.rb_pay(g.a, g.bet, 0, 'arena_back', g.id::text);
            if g.state = 'live' and g.b is not null then perform public.rb_pay(g.b, g.bet, 0, 'arena_back', g.id::text); end if;
        end if;
        n := n + 1;
    end loop;
    return n;
end $$;

do $patch$
declare src text;
begin
    select pg_get_functiondef('public.rb_feature_cleanup(text)'::regprocedure) into src;
    if src is not null and position('rb_bg_cleanup' in src) = 0 then
        execute replace(src, 'return json_build_object(''stopped'', n);',
                        'n := n + public.rb_bg_cleanup(f);' || chr(10) || '    return json_build_object(''stopped'', n);');
    end if;
exception when undefined_function then null;
end $patch$;

-- ---------------------------------------------------------------- 4. leaderboards: every game, in four sections
create or replace function public.rb_bg_points(who uuid, k text) returns bigint
language sql stable security definer set search_path to '' as $$
    select coalesce(sum(case g.level when 'insane' then 10 when 'hard' then 4 when 'medium' then 2 else 1 end), 0)::bigint
      from public.rb_bg g where g.a = who and g.b is null and g.kind = k and g.state = 'done' and g.winner = 1 $$;

create or replace function public.rb_bg_duel_wins(who uuid, k text) returns bigint
language sql stable security definer set search_path to '' as $$
    select count(*)::bigint from public.rb_bg g
     where g.b is not null and g.state = 'done' and (k is null or g.kind = k)
       and ((g.winner = 1 and g.a = who) or (g.winner = 2 and g.b = who)) $$;

create or replace function public.rb_leaders(kind text, friends boolean) returns json
language plpgsql stable security definer set search_path to '' as $$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    if kind not in ('coins', 'worth', 'badges', 'hours', 'streak', 'tap', 'park', 'memory', 'level',
                    'wave', 'flips', 'golf', 'c4', 'cups', 'trophies', 'horses', 'reversi', 'ships', 'arena',
                    'a:c4', 'a:reversi', 'a:ships')
       and kind not in ('g:roulette', 'g:blackjack', 'g:hilo', 'g:slots', 'g:rocket', 'g:plinko', 'g:mines', 'g:tower',
                        'g:dice', 'g:timing', 'g:colour', 'g:sfx') then raise exception 'rb_bad_choice'; end if;
    return (with who as (select p.* from public.profiles p where not p.banned
                          and (not coalesce(friends, false) or p.id = me or public.rb_is_friend(me, p.id))),
            v as (select w.id, w.username, (case kind
                when 'coins' then w.coins when 'level' then w.xp
                when 'hours' then w.minutes / 60
                when 'streak' then (case when w.streak_day >= public.rb_today() - 1 then w.streak else 0 end)
                when 'worth' then (select coalesce(sum(public.rb_worth(c.id)), 0) from public.rb_items it join public.rb_catalog c on c.id = it.item where it.owner = w.id)
                when 'badges' then (select count(distinct it.item) from public.rb_items it where it.owner = w.id and it.item like 'badge:%')
                when 'tap' then (select coalesce(max((r.secret ->> 'pct')::int), 0) from public.rb_rounds r where r.owner = w.id and r.game = 'mini')
                when 'park' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game = 'park')
                when 'memory' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game = 'memory')
                when 'wave' then greatest(public.rb_wave_best(w.id) / 100, coalesce((w.bot_cfg -> 'stats' ->> 'wave')::bigint, 0))
                when 'flips' then (select count(*) from public.rb_flips f where f.winner = w.id and f.state = 'done')
                                  + coalesce((w.bot_cfg -> 'stats' ->> 'flip')::bigint, 0)
                when 'golf' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game in ('golf', 'golf_party', 'golf_solo'))
                                 + coalesce((w.bot_cfg -> 'stats' ->> 'golf')::bigint, 0)
                when 'c4' then (select count(*) from public.rb_c4 g where g.owner = w.id and g.outcome = 'win')
                when 'cups' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game = 'cups' and r.paid > r.bet)
                when 'horses' then (select coalesce(max(b.paid - b.amount), 0) from public.rb_race_bets b where b.owner = w.id and b.paid > b.amount)
                when 'reversi' then public.rb_bg_points(w.id, 'reversi')
                when 'ships' then public.rb_bg_points(w.id, 'ships')
                when 'arena' then public.rb_bg_duel_wins(w.id, null)
                when 'a:c4' then public.rb_bg_duel_wins(w.id, 'c4')
                when 'a:reversi' then public.rb_bg_duel_wins(w.id, 'reversi')
                when 'a:ships' then public.rb_bg_duel_wins(w.id, 'ships')
                when 'g:roulette' then public.rb_best_win(w.id, 'roulette') when 'g:blackjack' then public.rb_best_win(w.id, 'blackjack')
                when 'g:hilo' then public.rb_best_win(w.id, 'hilo') when 'g:slots' then public.rb_best_win(w.id, 'slots')
                when 'g:rocket' then public.rb_best_win(w.id, 'rocket') when 'g:plinko' then public.rb_best_win(w.id, 'plinko')
                when 'g:mines' then public.rb_best_win(w.id, 'mines') when 'g:tower' then public.rb_best_win(w.id, 'tower')
                when 'g:dice' then public.rb_best_win(w.id, 'dice') when 'g:timing' then public.rb_best_win(w.id, 'timing')
                when 'g:colour' then public.rb_best_win(w.id, 'colour') when 'g:sfx' then public.rb_best_win(w.id, 'sfx')
                else (select count(*) from public.rb_ach a where a.owner = w.id) end)::bigint as val
                  from who w),
            ranked as (select v.*, rank() over (order by val desc) rk from v where val > 0 or v.id = me)
        select json_build_object(
            'top', coalesce((select json_agg(json_build_object('rank', rk, 'name', username, 'value', val, 'me', id = me) order by rk, username)
                               from (select * from ranked order by rk, username limit 50) t), '[]'::json),
            'me', (select json_build_object('rank', rk, 'value', val) from ranked where id = me)));
end $$;

-- the profile numbers: the Arena and the newer games too
create or replace function public.rb_stats_91(who uuid) returns jsonb
language sql stable security definer set search_path to '' as $$
    select jsonb_build_object(
        'reversi', (select count(*) from public.rb_bg g where g.a = who and g.b is null and g.kind = 'reversi' and g.winner = 1),
        'ships', (select count(*) from public.rb_bg g where g.a = who and g.b is null and g.kind = 'ships' and g.winner = 1),
        'arena', public.rb_bg_duel_wins(who, null),
        'arena_played', (select count(*) from public.rb_bg g where (g.a = who or g.b = who) and g.b is not null and g.state = 'done'),
        'insane', (select count(*) from public.rb_bg g where g.a = who and g.b is null and g.level = 'insane' and g.winner = 1),
        'horses', (select coalesce(max(b.paid - b.amount), 0) from public.rb_race_bets b where b.owner = who and b.paid > b.amount),
        'skill', (select coalesce(sum(r.paid), 0) from public.rb_rounds r where r.owner = who
                   and r.game in ('timing', 'cups', 'c4', 'colour', 'sfx', 'reversi', 'ships') and r.bet = 0)) $$;

do $patch$
declare src text;
begin
    select pg_get_functiondef('public.rb_stats(uuid)'::regprocedure) into src;
    if position('rb_stats_91' in src) = 0 then
        execute replace(src, 'public.rb_stats_real(who)::jsonb;', 'public.rb_stats_real(who)::jsonb || public.rb_stats_91(who);');
    end if;
    select pg_get_functiondef('public.rb_my_stats(integer)'::regprocedure) into src;
    if position('''reversi''' in src) = 0 then
        execute replace(src, '''timing'', ''cups'', ''c4'', ''colour'', ''sfx'')), ''{}'')',
                             '''timing'', ''cups'', ''c4'', ''colour'', ''sfx'', ''reversi'', ''ships'')), ''{}'')');
    end if;
exception when undefined_function then null;
end $patch$;

-- ---------------------------------------------------------------- 5. replays and odd patterns, for the admins
-- every game in one list: newest first. flags: why it may need a look
create or replace function public.rb_admin_replays(kind text, name text, flagged boolean, lim integer) returns jsonb
language plpgsql stable security definer set search_path to '' as $$
declare who uuid; lim_n integer := greatest(10, least(coalesce(lim, 100), 300)); out_ jsonb;
begin
    perform public.rb_need_admin();
    if coalesce(name, '') <> '' then
        select id into who from public.profiles where lower(username) = lower(name);
        if who is null then raise exception 'rb_no_such_user'; end if;
    end if;
    with
    arena as (
        select 'arena' k, g.id::text id, coalesce(g.done_at, g.at) at, array_remove(array[g.a, g.b], null) ids,
               g.kind || case when g.level is not null then ' vs ' || g.level || ' bot' else ' duel' end
                      || case when g.bet > 0 then ' · bet ' || g.bet else '' end what,
               case g.winner when 1 then 'won by side 1' when 2 then 'won by side 2' when 0 then 'draw' else g.state end
                      || coalesce(' (' || g.why || ')', '') res,
               array_remove(array[
                   case when g.b is null and g.level = 'insane' and g.winner = 1 then 'insane win' end,
                   case when (select count(*) from jsonb_array_elements(g.moves) m where (m ->> 's')::int = 1) >= 8
                         and (select avg((m ->> 'ms')::int) from jsonb_array_elements(g.moves) m where (m ->> 's')::int = 1) < 700
                        then 'too fast (side 1)' end,
                   case when g.b is not null and (select count(*) from jsonb_array_elements(g.moves) m where (m ->> 's')::int = 2) >= 8
                         and (select avg((m ->> 'ms')::int) from jsonb_array_elements(g.moves) m where (m ->> 's')::int = 2) < 700
                        then 'too fast (side 2)' end,
                   case when g.b is not null and g.bet > 0 and (select count(*) from public.rb_bg x
                         where x.b is not null and x.state = 'done' and x.at > g.at - interval '24 hours' and x.at <= g.at
                           and least(x.a, x.b) = least(g.a, g.b) and greatest(x.a, x.b) = greatest(g.a, g.b)
                           and (case x.winner when 1 then x.a when 2 then x.b end) = (case g.winner when 1 then g.a when 2 then g.b end)) >= 4
                        then 'same pair, same winner' end], null) flags
          from public.rb_bg g where g.state in ('done', 'cancelled') and (who is null or g.a = who or g.b = who)
         order by g.at desc limit lim_n),
    c4 as (
        select 'c4' k, g.id::text, coalesce(g.updated_at, g.created_at), array[g.owner], 'Connect 4 vs ' || g.level || ' bot',
               coalesce(g.outcome, g.state), array_remove(array[case when g.level = 'pro' and g.outcome = 'win' then 'pro win' end], null)
          from public.rb_c4 g where g.state = 'done' and (who is null or g.owner = who) order by g.created_at desc limit lim_n),
    golf as (
        select 'golf' k, g.id::text, coalesce(g.done_at, g.at), array_remove(array[g.a, g.b], null),
               'Mini Golf duel' || case when g.bet > 0 then ' · bet ' || g.bet else '' end,
               coalesce(g.why, g.state),
               array_remove(array[case when g.bet > 0 and g.winner is not null and (select count(*) from public.rb_golf x
                     where x.state = 'done' and x.at > g.at - interval '24 hours' and x.at <= g.at and x.winner = g.winner
                       and least(x.a, x.b) = least(g.a, g.b) and greatest(x.a, x.b) = greatest(g.a, g.b)) >= 4
                    then 'same pair, same winner' end], null)
          from public.rb_golf g where g.state in ('done', 'cancelled') and (who is null or g.a = who or g.b = who)
         order by g.at desc limit lim_n),
    wave as (
        select 'wave' k, r.id::text, coalesce(r.done_at, r.started_at), array[r.owner],
               'Wave Rush ' || case when r.duel is null then 'solo' else 'duel' end, (r.dist / 100) || ' m',
               array_remove(array[case when r.ticks > 0 and coalesce(cardinality(r.live_tg), 0) * 3600.0 / r.ticks > 400
                                       then 'inhuman tapping' end], null)
          from public.rb_wave_runs r where r.state = 'done' and (who is null or r.owner = who) order by r.started_at desc limit lim_n),
    flip as (
        select 'flip' k, f.id::text, coalesce(f.done_at, f.at), array_remove(array[f.a, f.b], null),
               'Coinflip · ' || coalesce(f.a_value, 0) || ' vs ' || coalesce(f.b_value, 0) || coalesce(' · bot ' || f.bot_name, ''),
               coalesce(f.result, f.state),
               array_remove(array[case when f.b is not null and f.a is not null and (select count(*) from public.rb_flips x
                     where x.state = 'done' and x.at > f.at - interval '24 hours' and x.at <= f.at
                       and least(x.a, x.b) = least(f.a, f.b) and greatest(x.a, x.b) = greatest(f.a, f.b)) >= 3
                    then 'same pair again' end], null)
          from public.rb_flips f where f.state = 'done' and (who is null or f.a = who or f.b = who) order by f.at desc limit lim_n),
    casino as (                                                   -- casino bets, and the mini games that pay by skill
        select case when r.bet > 0 then 'casino' else 'mini' end k, r.id::text, r.at, array[r.owner],
               r.game || case when r.bet > 0 then ' · bet ' || r.bet else ' · ' || coalesce(r.secret ->> 'level', '') end,
               'paid ' || r.paid,
               array_remove(array[case when r.bet > 0 and r.paid >= r.bet * 50 then 'huge win' end], null)
          from public.rb_rounds r where not r.open and (r.bet > 0 or r.game in ('timing', 'cups', 'colour', 'sfx'))
           and (who is null or r.owner = who)
         order by r.at desc limit lim_n),
    held as (
        select 'held' k, h.id::text, h.at, array[h.owner], h.game || ' · ' || h.coins || ' coins waiting', h.state, array[h.why]
          from public.rb_held h where (who is null or h.owner = who) order by h.at desc limit lim_n),
    allr as (select * from arena union all select * from c4 union all select * from golf union all select * from wave
             union all select * from flip union all select * from casino union all select * from held)
    select coalesce(jsonb_agg(jsonb_build_object('kind', x.k, 'id', x.id, 'at', x.at, 'what', x.what, 'result', x.res,
                                                 'flags', to_jsonb(x.flags),
                                                 'who', (select jsonb_agg(p.username order by array_position(x.ids, p.id)) from public.profiles p
                                                        where p.id = any (x.ids)))
                              order by x.at desc), '[]'::jsonb)
      into out_
      from (select * from allr a(k, id, at, ids, what, res, flags)
             where (coalesce(kind, 'all') = 'all' or a.k = kind) and (not coalesce(flagged, false) or cardinality(a.flags) > 0)
             order by a.at desc limit lim_n) x;
    return out_;
end $$;

-- one game in full: every move, with the hidden parts (fleets, seeds) the players never saw
create or replace function public.rb_admin_replay(kind text, rid text) returns jsonb
language plpgsql stable security definer set search_path to '' as $$
begin
    perform public.rb_need_admin();
    return case kind
        when 'arena' then (select to_jsonb(g) - 'a' - 'b' || jsonb_build_object(
                               'names', jsonb_build_array((select username from public.profiles where id = g.a),
                                                          coalesce((select username from public.profiles where id = g.b),
                                                                   initcap(coalesce(g.level, '')) || ' bot')))
                             from public.rb_bg g where g.id::text = rid)
        when 'c4' then (select to_jsonb(g) || jsonb_build_object('name', (select username from public.profiles where id = g.owner))
                          from public.rb_c4 g where g.id::text = rid)
        when 'golf' then (select to_jsonb(g) || jsonb_build_object('names', jsonb_build_array(
                                 (select username from public.profiles where id = g.a), (select username from public.profiles where id = g.b)))
                            from public.rb_golf g where g.id::text = rid)
        when 'wave' then (select to_jsonb(r) || jsonb_build_object('name', (select username from public.profiles where id = r.owner))
                            from public.rb_wave_runs r where r.id::text = rid)
        when 'flip' then (select to_jsonb(f) || jsonb_build_object('names', jsonb_build_array(
                                 (select username from public.profiles where id = f.a), (select username from public.profiles where id = f.b)))
                            from public.rb_flips f where f.id::text = rid)
        when 'casino' then (select to_jsonb(r) || jsonb_build_object('name', (select username from public.profiles where id = r.owner))
                              from public.rb_rounds r where r.id::text = rid)
        when 'mini' then (select to_jsonb(r) || jsonb_build_object('name', (select username from public.profiles where id = r.owner))
                            from public.rb_rounds r where r.id::text = rid)
        when 'held' then (select to_jsonb(h) || jsonb_build_object('name', (select username from public.profiles where id = h.owner),
                                 'recent', (select jsonb_agg(jsonb_build_object('base', l.base, 'pay', l.pay, 'held', l.held, 'at', l.at)
                                                             order by l.at desc)
                                              from (select * from public.rb_skill_log l where l.owner = h.owner and l.game = h.game
                                                     order by l.at desc limit 40) l))
                            from public.rb_held h where h.id::text = rid)
    end;
end $$;

-- a held pay: pay it (and maybe trust the player from now on) or void it
create or replace function public.rb_admin_held(hid uuid, pay boolean, trust boolean) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare adm uuid := public.rb_need_admin(); h public.rb_held%rowtype; who uuid;
begin
    select * into h from public.rb_held where id = hid for update;
    if not found or h.state <> 'held' then raise exception 'rb_round_gone'; end if;
    who := h.owner;
    if coalesce(pay, false) then
        perform public.rb_pay(h.owner, h.coins, 0, 'skill', h.game);
        update public.rb_held set state = 'paid', by_admin = adm, done_at = now() where id = hid;
    else
        update public.rb_held set state = 'void', by_admin = adm, done_at = now() where id = hid;
    end if;
    if coalesce(trust, false) then
        insert into public.rb_trusted (owner, by_admin) values (h.owner, adm) on conflict (owner) do nothing;
        for h in select * from public.rb_held where owner = who and state = 'held' for update loop
            perform public.rb_pay(h.owner, h.coins, 0, 'skill', h.game);
            update public.rb_held set state = 'paid', by_admin = adm, done_at = now() where id = h.id;
        end loop;
    end if;
    perform public.rb_log('held', hid::text, jsonb_build_object('pay', pay, 'trust', trust));
    perform public.rb_notice(who, 'held_done', jsonb_build_object('paid', coalesce(pay, false) or coalesce(trust, false)));
    return jsonb_build_object('ok', true, 'waiting', (select count(*) from public.rb_held where state = 'held'));
end $$;

-- ---------------------------------------------------------------- grants
revoke all on table public.rb_bg, public.rb_skill_log, public.rb_held, public.rb_trusted from anon, authenticated;
revoke all on function public.rb_is_admin_now(), public.rb_feature_open(text), public.rb_skill_top(text),
    public.rb_integrity(uuid, text, integer), public.rb_skill_window(uuid, text), public.rb_skill_pay(uuid, text, integer),
    public.rb_bg_turn_secs(text), public.c4_drop(text, integer), public.c4_wins(text, integer),
    public.rv_flips(text, integer, text), public.rv_moves(text, text), public.rv_play(text, integer, text),
    public.rv_count(text, text), public.rv_eval(text, text), public.rv_bot(text, text, text), public.sh_fleet(),
    public.sh_shoot(text, jsonb, integer), public.sh_bot(text, integer[], text), public.rb_bg_new_board(text),
    public.rb_bg_busy(uuid), public.rb_bg_json(public.rb_bg, uuid), public.rb_bg_base(public.rb_bg),
    public.rb_bg_end(uuid, integer, text), public.rb_bg_apply(uuid, integer, integer), public.rb_bg_bot_turns(uuid),
    public.rb_bg_tick(uuid), public.rb_bg_tick_mine(uuid), public.rb_bg_cleanup(text), public.rb_bg_points(uuid, text),
    public.rb_bg_duel_wins(uuid, text), public.rb_stats_91(uuid)
    from public, anon, authenticated;
grant execute on function public.rb_skill_state(), public.rb_bg_bot(text, text), public.rb_bg_shuffle(uuid),
    public.rb_bg_create(text, integer), public.rb_bg_join(uuid), public.rb_bg_cancel(uuid),
    public.rb_bg_move(uuid, integer, integer), public.rb_bg_resign(uuid), public.rb_bg_state(uuid), public.rb_bg_lobbies(),
    public.rb_leaders(text, boolean), public.rb_admin_replays(text, text, boolean, integer), public.rb_admin_replay(text, text),
    public.rb_admin_held(uuid, boolean, boolean)
    to authenticated;
revoke all on function public.rb_bg_bot(text, text), public.rb_bg_shuffle(uuid), public.rb_bg_create(text, integer),
    public.rb_bg_join(uuid), public.rb_bg_cancel(uuid), public.rb_bg_move(uuid, integer, integer), public.rb_bg_resign(uuid),
    public.rb_bg_state(uuid), public.rb_bg_lobbies(), public.rb_admin_replays(text, text, boolean, integer),
    public.rb_admin_replay(text, text), public.rb_admin_held(uuid, boolean, boolean) from public, anon;

commit;
