-- Rubenium 9.2: Mazelock, a wall maze duel (kind 'maze' in rb_bg), and Trifade, endless noughts and crosses (kind
-- 'tri', further down). Safe to run twice.
--
-- A 9 x 9 board. You start at the bottom middle and race to the top row; the other side races down. On your turn you
-- either step one square (jumping over the other pawn when it is in the way, or to its side when a wall is behind it),
-- or place one of your 10 walls. A wall is two squares long and lies in the grooves between squares. Walls may not
-- overlap or cross, and must always leave both pawns a way to their goal.
--
-- Board (rb_bg.board): {"p": [cell1, cell2], "w": [walls1, walls2], "h": 64 chars, "v": 64 chars}
--   cell = row * 9 + column (row 0 at the top). Side 1 starts at 76 and goes to row 0, side 2 starts at 4 and goes to row 8.
--   h / v: one char per wall slot a = row * 8 + column (0..7 each): '.' empty, '1' or '2' whose wall it is.
--   A horizontal wall at (r, c) lies under squares (r, c) and (r, c + 1); a vertical one right of (r, c) and (r + 1, c).
-- Moves: 0..80 step to that square, 100 + a horizontal wall, 200 + a vertical wall.
--
-- The bots play on the server: Easy wanders and walls at random, Medium looks one move ahead and slips now and then,
-- Hard looks two moves ahead and rarely slips, Professional always starts, searches three or four moves ahead with
-- alpha-beta and never slips.
begin;

alter table public.rb_bg drop constraint if exists rb_bg_kind_check;
alter table public.rb_bg add constraint rb_bg_kind_check check (kind in ('c4', 'reversi', 'ships', 'maze', 'tri'));

-- ---------------------------------------------------------------- the rules
-- can a pawn step from cell in direction d (0 up, 1 down, 2 left, 3 right)?
create or replace function public.mz_open(h text, v text, cell integer, d integer) returns boolean
language plpgsql immutable set search_path to '' as $$
declare r integer := cell / 9; c integer := cell % 9;
begin
    if d = 0 then
        return r > 0 and (c > 7 or substr(h, (r - 1) * 8 + c + 1, 1) = '.') and (c < 1 or substr(h, (r - 1) * 8 + c, 1) = '.');
    elsif d = 1 then
        return r < 8 and (c > 7 or substr(h, r * 8 + c + 1, 1) = '.') and (c < 1 or substr(h, r * 8 + c, 1) = '.');
    elsif d = 2 then
        return c > 0 and (r > 7 or substr(v, r * 8 + c, 1) = '.') and (r < 1 or substr(v, (r - 1) * 8 + c, 1) = '.');
    else
        return c < 8 and (r > 7 or substr(v, r * 8 + c + 1, 1) = '.') and (r < 1 or substr(v, (r - 1) * 8 + c + 1, 1) = '.');
    end if;
end $$;

create or replace function public.mz_step(cell integer, d integer) returns integer
language sql immutable set search_path to '' as $$
    select cell + case d when 0 then -9 when 1 then 9 when 2 then -1 else 1 end $$;

-- the fewest steps from cell to goal_row (walls only, pawns ignored); 999 when walled in
create or replace function public.mz_dist(h text, v text, start integer, goal_row integer) returns integer
language plpgsql immutable set search_path to '' as $$
declare dist integer[] := array_fill(-1, array[81]); q integer[] := array[start]; head integer := 1; cur integer;
        r integer; c integer; n integer;
begin
    if start / 9 = goal_row then return 0; end if;
    dist[start + 1] := 0;
    while head <= cardinality(q) loop
        cur := q[head]; head := head + 1;
        r := cur / 9; c := cur % 9;
        -- up
        if r > 0 and (c > 7 or substr(h, (r - 1) * 8 + c + 1, 1) = '.') and (c < 1 or substr(h, (r - 1) * 8 + c, 1) = '.') then
            n := cur - 9;
            if dist[n + 1] < 0 then
                dist[n + 1] := dist[cur + 1] + 1;
                if n / 9 = goal_row then return dist[n + 1]; end if;
                q := q || n;
            end if;
        end if;
        -- down
        if r < 8 and (c > 7 or substr(h, r * 8 + c + 1, 1) = '.') and (c < 1 or substr(h, r * 8 + c, 1) = '.') then
            n := cur + 9;
            if dist[n + 1] < 0 then
                dist[n + 1] := dist[cur + 1] + 1;
                if n / 9 = goal_row then return dist[n + 1]; end if;
                q := q || n;
            end if;
        end if;
        -- left
        if c > 0 and (r > 7 or substr(v, r * 8 + c, 1) = '.') and (r < 1 or substr(v, (r - 1) * 8 + c, 1) = '.') then
            n := cur - 1;
            if dist[n + 1] < 0 then dist[n + 1] := dist[cur + 1] + 1; q := q || n; end if;
        end if;
        -- right
        if c < 8 and (r > 7 or substr(v, r * 8 + c + 1, 1) = '.') and (r < 1 or substr(v, (r - 1) * 8 + c + 1, 1) = '.') then
            n := cur + 1;
            if dist[n + 1] < 0 then dist[n + 1] := dist[cur + 1] + 1; q := q || n; end if;
        end if;
    end loop;
    return 999;
end $$;

-- one shortest path from start to goal_row, as the list of cells after start
create or replace function public.mz_path(h text, v text, start integer, goal_row integer) returns integer[]
language plpgsql immutable set search_path to '' as $$
declare par integer[] := array_fill(-2, array[81]); q integer[] := array[start]; head integer := 1; cur integer;
        n integer; d integer; out_ integer[] := '{}';
begin
    if start / 9 = goal_row then return out_; end if;
    par[start + 1] := -1;
    while head <= cardinality(q) loop
        cur := q[head]; head := head + 1;
        foreach d in array array[case when goal_row = 0 then 0 else 1 end, 2, 3, case when goal_row = 0 then 1 else 0 end] loop
            if public.mz_open(h, v, cur, d) then
                n := public.mz_step(cur, d);
                if par[n + 1] = -2 then
                    par[n + 1] := cur;
                    if n / 9 = goal_row then
                        while n <> start loop out_ := n || out_; n := par[n + 1]; end loop;
                        return out_;
                    end if;
                    q := q || n;
                end if;
            end if;
        end loop;
    end loop;
    return out_;
end $$;

-- the squares a pawn at me can step to, with the other pawn at op
create or replace function public.mz_steps(h text, v text, me integer, op integer) returns integer[]
language plpgsql immutable set search_path to '' as $$
declare out_ integer[] := '{}'; d integer; n integer; s integer;
begin
    for d in 0..3 loop
        if public.mz_open(h, v, me, d) then
            n := public.mz_step(me, d);
            if n <> op then
                out_ := out_ || n;
            elsif public.mz_open(h, v, op, d) then                 -- jump straight over
                out_ := out_ || public.mz_step(op, d);
            else                                                   -- a wall or the edge behind it: to its sides
                foreach s in array case when d < 2 then array[2, 3] else array[0, 1] end loop
                    if public.mz_open(h, v, op, s) then out_ := out_ || public.mz_step(op, s); end if;
                end loop;
            end if;
        end if;
    end loop;
    return out_;
end $$;

-- does a wall fit there (not over or across another one)? Paths are checked apart.
create or replace function public.mz_fits(h text, v text, horiz boolean, a integer) returns boolean
language plpgsql immutable set search_path to '' as $$
declare r integer := a / 8; c integer := a % 8;
begin
    if a < 0 or a > 63 then return false; end if;
    if horiz then
        return substr(h, a + 1, 1) = '.' and substr(v, a + 1, 1) = '.'
           and (c = 0 or substr(h, a, 1) = '.') and (c = 7 or substr(h, a + 2, 1) = '.');
    end if;
    return substr(v, a + 1, 1) = '.' and substr(h, a + 1, 1) = '.'
       and (r = 0 or substr(v, a - 7, 1) = '.') and (r = 7 or substr(v, a + 9, 1) = '.');
end $$;

-- play move m for side s on board b; null when it is not allowed
create or replace function public.mz_play(b jsonb, s integer, m integer) returns jsonb
language plpgsql immutable set search_path to '' as $$
declare h text := b ->> 'h'; v text := b ->> 'v'; p1 integer := (b -> 'p' ->> 0)::int; p2 integer := (b -> 'p' ->> 1)::int;
        me integer; op integer; w integer := (b -> 'w' ->> (s - 1))::int; a integer;
begin
    me := case when s = 1 then p1 else p2 end; op := case when s = 1 then p2 else p1 end;
    if m between 0 and 80 then
        if not m = any(public.mz_steps(h, v, me, op)) then return null; end if;
        return jsonb_set(b, array['p', (s - 1)::text], to_jsonb(m));
    end if;
    if w <= 0 or not (m between 100 and 163 or m between 200 and 263) then return null; end if;
    a := m % 100;
    if not public.mz_fits(h, v, m < 200, a) then return null; end if;
    if m < 200 then h := overlay(h placing s::text from a + 1 for 1); else v := overlay(v placing s::text from a + 1 for 1); end if;
    if public.mz_dist(h, v, p1, 0) >= 999 or public.mz_dist(h, v, p2, 8) >= 999 then return null; end if;
    return b || jsonb_build_object('h', h, 'v', v, 'w', jsonb_set(b -> 'w', array[(s - 1)::text], to_jsonb(w - 1)));
end $$;

create or replace function public.mz_new() returns jsonb
language sql immutable set search_path to '' as $$
    select jsonb_build_object('p', jsonb_build_array(76, 4), 'w', jsonb_build_array(10, 10),
                              'h', repeat('.', 64), 'v', repeat('.', 64)) $$;

-- ---------------------------------------------------------------- the bots
-- the wall slots that cut one of the next steps of a path (from cell along cells)
create or replace function public.mz_cut_walls(start integer, path integer[], depth integer) returns integer[]
language plpgsql immutable set search_path to '' as $$
declare out_ integer[] := '{}'; prev integer := start; n integer; r integer; c integer; i integer := 0; a integer;
begin
    foreach n in array path loop
        i := i + 1;
        exit when i > depth;
        if abs(n - prev) = 9 then                                  -- a vertical step: horizontal walls
            r := least(n, prev) / 9; c := n % 9;
            foreach a in array array[r * 8 + c, r * 8 + c - 1] loop
                if (a = r * 8 + c and c <= 7) or (a = r * 8 + c - 1 and c >= 1) then out_ := out_ || (100 + a); end if;
            end loop;
        else                                                       -- a sideways step: vertical walls
            r := n / 9; c := least(n, prev) % 9;
            if r <= 7 then out_ := out_ || (200 + r * 8 + c); end if;
            if r >= 1 then out_ := out_ || (200 + (r - 1) * 8 + c); end if;
        end if;
        prev := n;
    end loop;
    return out_;
end $$;

-- the score of a position for side s (higher is better for s), s to move next = tomove
create or replace function public.mz_score(h text, v text, p1 integer, p2 integer, w1 integer, w2 integer, s integer,
                                           tomove integer) returns integer
language plpgsql immutable set search_path to '' as $$
declare d1 integer := public.mz_dist(h, v, p1, 0); d2 integer := public.mz_dist(h, v, p2, 8); mine integer; theirs integer;
        mw integer; tw integer; sc integer;
begin
    if s = 1 then mine := d1; theirs := d2; mw := w1; tw := w2; else mine := d2; theirs := d1; mw := w2; tw := w1; end if;
    if mine = 0 then return 10000; end if;
    if theirs = 0 then return -10000; end if;
    -- a pure race when nobody has walls left: whoever needs fewer moves (counting who moves next) wins
    if mw = 0 and tw = 0 then
        if (case when tomove = s then mine <= theirs else mine < theirs end) then return 5000 - mine; end if;
        return -5000 + theirs;
    end if;
    sc := (theirs - mine) * 100 + (mw - tw) * 18 + case when tomove = s then 50 else -50 end;
    -- walls are worth less once the race is long; being far behind with no walls is very bad
    if mw = 0 and theirs < mine then sc := sc - 400; end if;
    if tw = 0 and mine < theirs then sc := sc + 400; end if;
    return sc;
end $$;

-- the moves worth looking at for side s: every step, and the walls that cut the other side's shortest path
create or replace function public.mz_candidates(h text, v text, p1 integer, p2 integer, w1 integer, w2 integer, s integer,
                                                reach integer) returns integer[]
language plpgsql immutable set search_path to '' as $$
declare me integer := case when s = 1 then p1 else p2 end; op integer := case when s = 1 then p2 else p1 end;
        out_ integer[]; w integer := case when s = 1 then w1 else w2 end; path integer[];
begin
    out_ := public.mz_steps(h, v, me, op);
    if w > 0 then
        path := public.mz_path(h, v, op, case when s = 1 then 8 else 0 end);
        out_ := out_ || array(select distinct x from unnest(public.mz_cut_walls(op, path, reach)) x
                               where public.mz_fits(h, v, x < 200, x % 100));
        -- and walls that guard my own next steps from being cut (a wall in my lane that their wall can't cross)
    end if;
    return out_;
end $$;

-- negamax with alpha-beta; returns the score for side s to move
create or replace function public.mz_search(h text, v text, p1 integer, p2 integer, w1 integer, w2 integer, s integer,
                                            depth integer, alpha integer, beta integer, deadline timestamptz) returns integer
language plpgsql volatile set search_path to '' as $$
declare m integer; nh text; nv text; n1 integer; n2 integer; nw1 integer; nw2 integer; sc integer; best integer := -100000;
        a integer; d1 integer; d2 integer;
begin
    d1 := public.mz_dist(h, v, p1, 0); d2 := public.mz_dist(h, v, p2, 8);
    if (s = 1 and d2 = 0) or (s = 2 and d1 = 0) then return -10000 - depth; end if;      -- the other side got home
    if depth <= 0 or clock_timestamp() > deadline then
        return public.mz_score(h, v, p1, p2, w1, w2, s, s);
    end if;
    foreach m in array public.mz_candidates(h, v, p1, p2, w1, w2, s, 6) loop
        nh := h; nv := v; n1 := p1; n2 := p2; nw1 := w1; nw2 := w2;
        if m < 100 then
            if s = 1 then n1 := m; else n2 := m; end if;
        else
            a := m % 100;
            if m < 200 then nh := overlay(h placing s::text from a + 1 for 1); else nv := overlay(v placing s::text from a + 1 for 1); end if;
            if public.mz_dist(nh, nv, p1, 0) >= 999 or public.mz_dist(nh, nv, p2, 8) >= 999 then continue; end if;
            if s = 1 then nw1 := w1 - 1; else nw2 := w2 - 1; end if;
        end if;
        sc := -public.mz_search(nh, nv, n1, n2, nw1, nw2, 3 - s, depth - 1, -beta, -alpha, deadline);
        if sc > best then best := sc; end if;
        if sc > alpha then alpha := sc; end if;
        exit when alpha >= beta;
    end loop;
    return best;
end $$;

-- the bot's move for side s
create or replace function public.mz_bot(b jsonb, s integer, level text) returns integer
language plpgsql volatile set search_path to '' as $$
declare h text := b ->> 'h'; v text := b ->> 'v'; p1 integer := (b -> 'p' ->> 0)::int; p2 integer := (b -> 'p' ->> 1)::int;
        w1 integer := (b -> 'w' ->> 0)::int; w2 integer := (b -> 'w' ->> 1)::int;
        me integer := case when s = 1 then p1 else p2 end; op integer := case when s = 1 then p2 else p1 end;
        goal integer := case when s = 1 then 0 else 8 end; depth integer; slip numeric; deadline timestamptz;
        m integer; sc integer; nh text; nv text; n1 integer; n2 integer; nw1 integer; nw2 integer; a integer;
        scored integer[] := '{}'; moves integer[] := '{}'; best integer; i integer; k integer; path integer[];
        cands integer[]; d integer; alpha integer; best_m integer; pick integer;
begin
    path := public.mz_path(h, v, me, goal);
    if level = 'easy' then                                         -- wanders: mostly along its path, walls at random
        if (case when s = 1 then w1 else w2 end) > 0 and public.rb_rand() < 0.22 then
            for i in 1..12 loop
                m := case when public.rb_rand() < 0.5 then 100 else 200 end + floor(public.rb_rand() * 64)::int;
                if public.mz_play(b, s, m) is not null then return m; end if;
            end loop;
        end if;
        cands := public.mz_steps(h, v, me, op);
        if public.rb_rand() < 0.3 or cardinality(path) = 0 then
            return cands[1 + floor(public.rb_rand() * cardinality(cands))::int];
        end if;
        if path[1] = any(cands) then return path[1]; end if;
        return cands[1 + floor(public.rb_rand() * cardinality(cands))::int];
    end if;
    depth := case level when 'medium' then 1 when 'hard' then 2 else 4 end;
    slip := case level when 'medium' then 0.14 when 'hard' then 0.05 else 0 end;
    deadline := clock_timestamp() + make_interval(secs => case level when 'insane' then 2.6 else 1.5 end);
    -- a sure race: just run
    if (case when s = 1 then w2 else w1 end) = 0 and cardinality(path) > 0
       and public.mz_dist(h, v, me, goal) <= public.mz_dist(h, v, op, 8 - goal) then
        if path[1] = any(public.mz_steps(h, v, me, op)) then return path[1]; end if;
    end if;
    cands := public.mz_candidates(h, v, p1, p2, w1, w2, s, case when level = 'medium' then 3 else 7 end);
    -- Professional deepens until its time is up and keeps the last search it finished; the others look depth ahead
    for d in (case when level = 'insane' then 1 else depth end)..depth loop
        scored := '{}'; moves := '{}'; alpha := -100000;
        foreach m in array cands loop
            nh := h; nv := v; n1 := p1; n2 := p2; nw1 := w1; nw2 := w2;
            if m < 100 then
                if s = 1 then n1 := m; else n2 := m; end if;
            else
                a := m % 100;
                if m < 200 then nh := overlay(h placing s::text from a + 1 for 1); else nv := overlay(v placing s::text from a + 1 for 1); end if;
                if public.mz_dist(nh, nv, p1, 0) >= 999 or public.mz_dist(nh, nv, p2, 8) >= 999 then continue; end if;
                if s = 1 then nw1 := w1 - 1; else nw2 := w2 - 1; end if;
            end if;
            if (s = 1 and n1 / 9 = 0) or (s = 2 and n2 / 9 = 8) then return m; end if;       -- home: win now
            sc := -public.mz_search(nh, nv, n1, n2, nw1, nw2, 3 - s, d - 1, -100000,
                                    case when slip > 0 then 100000 else -alpha + 1 end, deadline);
            if sc > alpha then alpha := sc; end if;
            scored := scored || sc; moves := moves || m;
        end loop;
        exit when cardinality(moves) = 0;
        exit when d > 1 and clock_timestamp() > deadline;          -- cut short: keep the last full search
        best := -100001; best_m := null;
        for i in 1..cardinality(moves) loop                         -- ties: a step beats a wall, so it never stalls
            if scored[i] > best or (scored[i] = best and moves[i] < 100 and coalesce(best_m, 999) >= 100) then
                best := scored[i]; best_m := moves[i];
            end if;
        end loop;
        pick := best_m;
        k := array_position(cands, best_m);                         -- the next depth looks at the best move first
        if k is not null and k > 1 then cands := best_m || (cands[1:k - 1] || cands[k + 1:]); end if;
        exit when clock_timestamp() > deadline or abs(best) >= 5000;
    end loop;
    m := coalesce(pick, path[1]);
    -- Medium and Hard slip now and then: the second best move (never one that loses on the spot)
    if slip > 0 and public.rb_rand() < slip and cardinality(moves) > 1 then
        k := null; sc := -100001;
        for i in 1..cardinality(moves) loop
            if moves[i] <> m and scored[i] > sc and scored[i] > -5000 then sc := scored[i]; k := moves[i]; end if;
        end loop;
        if k is not null then m := k; end if;
    end if;
    return m;
end $$;

-- ================================================================ 9.2: Trifade, endless noughts and crosses (kind 'tri')
-- A 3 x 3 board. Each side has at most 3 marks: placing a 4th takes your oldest away (it can't go back on that square on
-- the same turn). Three in a row wins, so the game goes on until someone wins (or 300 moves: a draw).
-- Board (rb_bg.board): {"q": [[cells of side 1, oldest first], [cells of side 2]]}, cell = row * 3 + column.
-- Moves: 0..8, the square.
--
-- The game is small enough to be solved completely: rb_tri_book holds every position that is won or lost for the side
-- to move (and in how many moves), folded by the board's 8 symmetries; every other position is a draw. The first side
-- to move can always force a win. Professional plays from the book without error and always starts, so it never loses.
-- Hard plays from the book and slips now and then, Medium only sees one move ahead and sometimes more, Easy mostly
-- plays at random.
create table if not exists public.rb_tri_book (k integer primary key, v smallint not null);
alter table public.rb_tri_book enable row level security;
revoke all on public.rb_tri_book from public, anon, authenticated;
truncate public.rb_tri_book;
insert into public.rb_tri_book (k, v)
    select split_part(x, ':', 1)::int, split_part(x, ':', 2)::smallint
      from unnest(string_to_array(
        '0:13,2:-12,1002:7,1003:7,1006:7,1009:7,1023:7,1024:5,1025:-6,1026:15,1027:5,1028:-10,1029:7,1032:5,1034:5,' ||
        '1036:-8,1038:5,1039:-6,1053:7,1059:5,1062:5,1065:-10,1067:5,1068:7,1069:7,1092:5,1093:-6,1095:11,1096:7,2001:7,' ||
        '2004:7,2005:9,2007:11,2008:7,2013:5,2014:-6,2016:5,2017:-6,2019:11,2041:-6,2043:5,2045:-6,2046:7,2048:5,2049:11,' ||
        '2051:-8,2054:-6,2057:-8,2058:5,2071:-6,2073:7,2074:7,2075:9,2076:5,2084:7,2085:9,2087:-6,5002:7,5012:9,5016:5,' ||
        '5021:-8,5024:5,5028:7,12034:5,12035:-4,12036:-6,12037:11,12039:-4,12043:5,12045:1,12046:1,12047:1,12048:1,' ||
        '12049:1,12053:-8,12054:1,12056:1,12057:1,12058:1,12059:1,12063:-6,12064:1,12065:1,12067:1,12068:1,12069:1,' ||
        '12073:7,12074:1,12075:1,12076:1,12078:1,12079:1,12084:1,12085:1,12086:1,12087:1,12089:1,12093:-6,12094:1,' ||
        '12095:1,12096:1,12097:1,12098:1,12345:-4,12346:7,12347:11,12348:-12,12349:11,12354:-4,12356:-8,12358:5,12359:5,' ||
        '12364:7,12365:-4,12367:11,12368:5,12374:5,12376:5,12379:-4,12384:-8,12386:-12,12387:-4,12389:-4,12394:7,12395:5,' ||
        '12435:-4,12436:-6,12437:11,12439:-4,12453:-8,12457:1,12458:1,12459:1,12463:-6,12467:1,12468:1,12469:1,12473:7,' ||
        '12475:1,12476:1,12478:1,12479:1,12483:13,12485:1,12486:1,12487:1,12489:1,12493:-6,12495:1,12496:1,12497:1,' ||
        '12498:1,12534:3,12536:-12,12538:5,12539:-6,12543:3,12547:1,12548:1,12549:1,12567:1,12568:1,12569:1,12574:1,' ||
        '12576:1,12578:1,12579:1,12584:1,12586:1,12587:1,12589:1,12594:1,12596:1,12597:1,12598:1,12634:5,12635:-4,' ||
        '12637:11,12638:5,12643:5,12647:1,12648:1,12649:1,12653:-8,12657:1,12658:1,12659:1,12673:7,12674:1,12675:1,' ||
        '12678:1,12679:1,12684:1,12685:1,12687:1,12689:1,12694:1,12695:1,12697:1,12698:1,12734:5,12736:-6,12738:5,' ||
        '12739:-4,12743:5,12745:1,12746:1,12748:1,12749:1,12754:1,12756:1,12758:1,12759:1,12763:-6,12764:1,12765:1,' ||
        '12768:1,12769:1,12783:5,12784:1,12785:1,12786:1,12793:-6,12794:1,12795:1,12796:1,12834:3,12835:-4,12836:-6,' ||
        '12837:3,12839:-4,12843:3,12845:1,12846:1,12847:1,12849:1,12853:-8,12854:1,12856:1,12857:1,12859:1,12863:-6,' ||
        '12864:1,12865:1,12867:1,12869:1,12873:3,12874:1,12875:1,12876:1,12893:-6,12894:1,12895:1,12896:1,12934:5,' ||
        '12937:11,12938:5,12943:5,12945:1,12946:1,12947:1,12948:1,12953:9,12954:1,12956:1,12957:1,12958:1,12964:1,' ||
        '12965:1,12967:1,12968:1,12973:7,12974:1,12975:1,12976:1,12983:5,12984:1,12985:1,12986:1,13024:15,13025:-4,' ||
        '13026:5,13028:-10,13029:5,13042:5,13045:1,13046:1,13047:1,13048:1,13049:1,13054:1,13056:1,13057:1,13058:1,' ||
        '13059:1,13062:5,13064:1,13065:1,13067:1,13068:1,13069:1,13072:5,13074:1,13075:1,13076:1,13078:1,13079:1,13084:1,' ||
        '13085:1,13086:1,13087:1,13089:1,13092:5,13094:1,13095:1,13096:1,13097:1,13098:1,13245:-4,13248:7,13257:11,' ||
        '13259:5,13264:-4,13265:-4,13267:-8,13268:-10,13276:-12,13278:7,13279:-4,13286:5,13289:-4,13294:-8,13297:-4,' ||
        '13298:-8,13425:-4,13426:5,13428:-10,13429:5,13457:1,13458:1,13459:1,13462:5,13467:1,13468:1,13469:1,13472:5,' ||
        '13475:1,13476:1,13478:1,13479:1,13485:1,13486:1,13487:1,13489:1,13492:5,13495:1,13496:1,13497:1,13498:1,13524:3,' ||
        '13526:3,13529:3,13542:3,13547:1,13548:1,13549:1,13562:3,13567:1,13568:1,13569:1,13572:5,13574:1,13576:1,13578:1,' ||
        '13579:1,13584:1,13586:1,13587:1,13589:1,13592:3,13594:1,13596:1,13597:1,13598:1,13624:3,13625:-4,13627:3,' ||
        '13628:-10,13629:5,13642:3,13647:1,13648:1,13649:1,13657:1,13658:1,13659:1,13672:3,13674:1,13675:1,13678:1,' ||
        '13679:1,13684:1,13685:1,13687:1,13689:1,13692:5,13694:1,13695:1,13697:1,13698:1,13724:3,13725:-4,13726:3,' ||
        '13728:3,13729:3,13742:3,13745:1,13746:1,13748:1,13749:1,13754:1,13756:1,13758:1,13759:1,13762:3,13764:1,13765:1,' ||
        '13768:1,13769:1,13782:3,13784:1,13785:1,13786:1,13792:3,13794:1,13795:1,13796:1,13824:15,13826:5,13829:5,' ||
        '13842:5,13845:1,13846:1,13847:1,13849:1,13854:1,13856:1,13857:1,13859:1,13862:5,13864:1,13865:1,13867:1,13869:1,' ||
        '13872:5,13874:1,13875:1,13876:1,13892:5,13894:1,13895:1,13896:1,13924:3,13925:-6,13926:5,13927:3,13928:-10,' ||
        '13942:3,13945:1,13946:1,13947:1,13948:1,13954:1,13956:1,13957:1,13958:1,13962:5,13964:1,13965:1,13967:1,13968:1,' ||
        '13972:3,13974:1,13975:1,13976:1,13984:1,13985:1,13986:1,15023:1,15024:1,15026:1,15027:1,15028:1,15032:1,15034:1,' ||
        '15036:1,15037:1,15038:1,15062:1,15063:1,15064:1,15067:1,15068:1,15069:-8,15092:5,15096:-10,15234:1,15236:1,' ||
        '15237:1,15238:1,15243:1,15246:1,15247:1,15248:1,15249:3,15263:1,15264:1,15267:1,15268:1,15269:-8,15273:1,' ||
        '15274:1,15276:1,15278:1,15279:3,15283:1,15284:1,15286:1,15287:1,15289:-8,15294:3,15296:-10,15297:3,15298:-10,' ||
        '15324:1,15326:1,15327:1,15328:1,15329:3,15342:1,15346:1,15347:1,15348:1,15349:3,15362:1,15364:1,15367:1,15368:1,' ||
        '15372:1,15374:1,15376:1,15378:1,15382:1,15384:1,15386:1,15387:1,15389:3,15392:3,15394:3,15398:3,15623:1,15624:1,' ||
        '15627:1,15628:1,15629:3,15632:1,15634:1,15637:1,15638:1,15642:1,15643:1,15647:1,15648:1,15672:1,15673:1,15674:1,' ||
        '15678:1,15682:1,15683:1,15684:1,15687:1,15689:-8,15692:3,15694:5,15698:-10,15924:9,15926:9,15928:7,15932:5,' ||
        '15934:7,15938:5,15962:5,15964:7,15968:5,16023:5,16024:7,16025:-4,16028:7,16029:5,16032:5,16035:-4,16037:-4,' ||
        '16038:5,16039:5,16042:7,16045:9,16048:7,16052:-4,16053:-4,16054:5,16057:-8,16058:-6,16059:15,16072:5,16073:7,' ||
        '16074:5,16075:-4,16078:7,16079:-4,16082:7,16083:5,16084:5,16085:-4,16089:-4,16092:7,16093:7,16097:-4,16098:-6,' ||
        '16235:-4,16237:-4,16238:5,16239:5,16243:11,16245:9,16247:13,16248:7,16253:11,16254:5,16257:-8,16259:5,16273:7,' ||
        '16274:5,16275:-4,16278:7,16279:-4,16283:5,16284:5,16289:-4,16293:7,16297:-4,16298:-6,16324:3,16325:-4,16327:3,' ||
        '16328:7,16329:5,16342:3,16345:3,16347:3,16348:3,16354:3,16358:-6,16359:5,16372:3,16374:3,16378:3,16379:-4,' ||
        '16382:7,16384:3,16385:-4,16387:3,16389:-4,16392:7,16397:-4,16398:-6,16423:3,16425:-4,16427:3,16428:3,16429:3,' ||
        '16432:3,16435:-4,16437:3,16438:3,16439:3,16452:-4,16453:-4,16457:-8,16458:-6,16459:15,16472:3,16473:3,16475:-4,' ||
        '16478:7,16479:-4,16482:3,16483:3,16485:-4,16489:-4,16492:3,16493:3,16497:-6,16498:-6,16523:3,16524:7,16527:3,' ||
        '16529:3,16532:3,16534:5,16538:3,16539:3,16542:7,16548:7,16549:15,16572:3,16574:5,16578:7,16579:-14,16583:3,' ||
        '16584:5,16589:15,16592:3,16593:3,16597:-4,16598:-12,16723:5,16724:7,16725:-4,16728:7,16729:5,16732:5,16734:5,' ||
        '16738:5,16739:5,16742:7,16745:9,16748:7,16752:-4,16754:5,16758:-6,16759:5,16782:7,16783:5,16784:5,16785:-4,' ||
        '16792:7,16793:7,16794:5,16795:5,16823:5,16824:7,16829:5,16832:5,16835:-4,16837:-4,16839:5,16842:7,16843:13,' ||
        '16845:9,16853:-4,16854:5,16857:-8,16859:5,16872:5,16873:7,16874:5,16875:-4,16892:7,16893:7,16894:5,16895:5,' ||
        '16923:5,16924:3,16925:-6,16927:3,16928:7,16932:5,16937:-4,16938:5,16942:3,16945:3,16947:3,16948:3,16952:-4,' ||
        '16953:-4,16954:3,16957:3,16958:-8,16972:3,16973:7,16974:3,16975:3,16982:7,16983:5,16984:3,16985:-6,19023:1,' ||
        '19024:1,19025:-10,19026:1,19027:1,19028:1,19032:1,19034:1,19036:1,19037:1,19038:1,19053:9,19062:1,19063:1,' ||
        '19064:1,19065:-6,19067:1,19068:1,19234:1,19236:1,19237:1,19238:1,19243:1,19245:-10,19246:1,19247:1,19248:1,' ||
        '19253:9,19257:9,19263:1,19264:1,19265:-6,19267:1,19268:1,19273:1,19274:1,19276:1,19278:1,19283:1,19284:1,' ||
        '19286:1,19287:1,19324:1,19325:-10,19326:1,19327:1,19328:1,19342:1,19345:3,19346:1,19347:1,19348:1,19354:3,' ||
        '19362:1,19364:1,19365:-6,19367:1,19368:1,19372:1,19374:1,19376:1,19378:1,19382:1,19384:1,19385:-6,19386:1,' ||
        '19387:1,19523:5,19524:7,19526:5,19527:9,19532:5,19534:5,19536:5,19538:5,19562:15,19563:9,19567:5,19568:5,' ||
        '19623:1,19624:1,19625:-10,19627:1,19628:1,19632:1,19634:1,19637:1,19638:1,19642:1,19643:1,19647:1,19648:1,' ||
        '19653:9,19657:3,19672:1,19673:1,19674:1,19675:3,19678:1,19682:1,19683:1,19684:1,19685:-6,19687:1,21034:5,' ||
        '21036:-8,21038:5,21039:-6,21043:5,21045:1,21046:1,21047:1,21048:1,21049:1,21053:7,21054:1,21056:1,21057:1,' ||
        '21058:1,21059:1,21064:1,21065:1,21067:1,21068:1,21069:1,21074:1,21075:1,21076:1,21078:1,21079:1,21083:5,21084:1,' ||
        '21085:1,21086:1,21087:1,21089:1,21093:-6,21094:1,21095:1,21096:1,21097:1,21098:1,21345:-4,21346:-10,21348:-10,' ||
        '21349:-12,21358:5,21359:5,21365:-10,21367:5,21368:7,21374:5,21376:5,21378:-4,21379:-8,21389:7,21394:5,21395:11,' ||
        '21398:7,21435:3,21436:-8,21438:3,21439:-6,21453:3,21457:1,21458:1,21459:1,21467:1,21468:1,21469:1,21475:1,' ||
        '21476:1,21478:1,21479:1,21483:3,21485:1,21486:1,21487:1,21489:1,21493:-6,21495:1,21496:1,21497:1,21498:1,' ||
        '21534:3,21536:3,21538:3,21539:-6,21543:3,21547:1,21548:1,21549:1,21563:3,21567:1,21568:1,21569:1,21574:1,' ||
        '21576:1,21578:1,21579:1,21583:3,21584:1,21586:1,21587:1,21589:1,21593:-6,21594:1,21596:1,21597:1,21598:1,' ||
        '21634:5,21638:5,21643:5,21647:1,21648:1,21649:1,21653:7,21657:1,21658:1,21659:1,21674:1,21675:1,21678:1,21679:1,' ||
        '21683:5,21684:1,21685:1,21687:1,21689:1,21694:1,21695:1,21697:1,21698:1,21734:5,21736:-8,21738:3,21739:-8,' ||
        '21743:5,21745:1,21746:1,21748:1,21749:1,21754:1,21756:1,21758:1,21759:1,21764:1,21765:1,21768:1,21769:1,21783:3,' ||
        '21784:1,21785:1,21786:1,21794:1,21795:1,21796:1,21834:5,21836:-8,21839:-6,21843:5,21845:1,21846:1,21847:1,' ||
        '21849:1,21853:7,21854:1,21856:1,21857:1,21859:1,21864:1,21865:1,21867:1,21869:1,21874:1,21875:1,21876:1,' ||
        '21893:-6,21894:1,21895:1,21896:1,21934:3,21937:3,21938:3,21943:3,21945:1,21946:1,21947:1,21948:1,21953:7,' ||
        '21954:1,21956:1,21957:1,21958:1,21964:1,21965:1,21967:1,21968:1,21973:3,21974:1,21975:1,21976:1,21983:3,21984:1,' ||
        '21985:1,21986:1,24013:5,24015:-4,24017:5,24018:5,24019:11,24031:5,24035:9,24036:-14,24037:7,24038:5,24051:-4,' ||
        '24053:-4,24056:5,24057:-8,24058:5,24059:-8,24063:-4,24065:9,24067:13,24068:7,24069:-6,24071:5,24073:11,24075:-4,' ||
        '24078:-4,24079:-6,24081:7,24083:11,24085:5,24086:5,24087:-6,24091:7,24095:9,24097:-6,24098:7,24135:3,24136:-14,' ||
        '24137:7,24138:3,24153:3,24156:3,24157:-8,24158:3,24163:-6,24165:3,24167:13,24168:3,24169:-6,24173:11,24175:-4,' ||
        '24178:-4,24179:-6,24183:3,24185:3,24186:3,24187:-6,24189:3,24197:-6,24198:3,24315:-4,24317:5,24318:5,24319:11,' ||
        '24351:9,24356:5,24358:5,24359:-8,24361:5,24365:9,24367:5,24368:7,24371:5,24376:5,24378:-4,24379:-6,24381:7,' ||
        '24385:5,24386:5,24387:-6,24391:7,24395:9,24397:-6,24398:7,24513:3,24516:5,24517:3,24518:3,24531:3,24536:-14,' ||
        '24538:3,24539:3,24563:-4,24567:13,24568:7,24569:-6,24571:3,24576:5,24578:9,24579:-6,24581:3,24583:3,24586:5,' ||
        '24593:3,24597:13,24598:7,24613:3,24615:-4,24617:3,24618:3,24619:3,24631:3,24635:9,24637:3,24638:3,24651:-4,' ||
        '24653:-4,24657:-8,24658:5,24659:-8,24671:3,24673:3,24675:-4,24678:-4,24679:-6,24681:3,24683:3,24685:5,24687:-6,' ||
        '24691:3,24695:9,24697:-6,24698:7,24713:5,24715:-4,24718:5,24719:11,24731:5,24736:-14,24738:3,24751:-4,24756:3,' ||
        '24758:3,24759:3,24763:-4,24765:3,24768:3,24769:-6,24781:7,24783:3,24785:3,24786:3,24791:7,24795:3,24813:5,' ||
        '24815:9,24817:5,24819:11,24831:5,24835:9,24837:7,24851:-4,24853:-4,24856:5,24857:-8,24859:-8,24863:-4,24865:9,' ||
        '24869:-6,24871:5,24873:11,24875:9,24876:5,24891:7,24895:9,24913:5,24916:5,24917:5,24918:5,24931:5,24935:9,' ||
        '24937:7,24938:5,24953:-4,24956:5,24957:9,24958:5,24961:5,24965:9,24967:5,24968:7,24971:5,24973:11,24975:-4,' ||
        '24976:5,24981:7,24983:11,24985:5,24986:5,25013:1,25014:1,25016:1,25017:1,25018:5,25019:1,25041:1,25043:1,' ||
        '25046:1,25047:1,25048:5,25049:1,25071:1,25073:1,25074:1,25076:1,25078:9,25079:1,25084:5,25087:-8,25134:1,' ||
        '25136:1,25137:1,25138:3,25139:1,25143:1,25146:1,25148:3,25149:1,25163:1,25164:1,25167:1,25168:3,25169:1,25173:1,' ||
        '25176:1,25178:3,25179:1,25183:3,25184:3,25186:3,25187:3,25189:-8,25193:1,25194:1,25196:1,25197:1,25198:9,' ||
        '25413:1,25416:1,25418:3,25419:1,25431:1,25436:1,25437:1,25438:3,25439:1,25461:1,25463:1,25467:1,25468:5,25469:1,' ||
        '25473:1,25476:1,25478:9,25479:1,25481:3,25483:3,25486:5,25487:-8,25489:-8,25491:1,25493:1,25496:1,25497:1,' ||
        '25498:9,25713:1,25716:1,25718:3,25719:1,25731:1,25734:1,25736:1,25738:5,25739:1,25743:1,25746:1,25748:3,25749:1,' ||
        '25761:1,25763:1,25764:1,25768:3,25769:1,25781:3,25784:3,25786:3,25791:1,25793:1,25794:1,25796:1,25814:9,25816:9,' ||
        '25841:-4,25843:-8,25846:9,25847:-8,25849:-8,25874:9,25876:5,27013:5,27014:5,27015:-4,27016:5,27018:5,27031:5,' ||
        '27034:5,27035:11,27036:7,27038:7,27039:-6,27041:7,27043:7,27045:-4,27046:-10,27048:5,27049:5,27051:7,27053:5,' ||
        '27058:5,27059:7,27061:5,27063:7,27065:-10,27068:5,27083:7,27089:7,27091:-4,27093:-4,27094:5,27096:-8,27098:5,' ||
        '27134:5,27135:3,27136:7,27138:3,27143:7,27145:-4,27146:-10,27148:5,27149:5,27153:3,27156:3,27158:3,27163:7,' ||
        '27165:3,27168:3,27183:3,27185:3,27186:3,27189:3,27194:5,27196:-8,27198:3,27314:3,27315:-4,27316:3,27318:3,' ||
        '27319:3,27341:3,27345:-4,27346:3,27348:3,27349:3,27351:7,27358:5,27359:7,27361:3,27364:3,27365:-10,27368:3,' ||
        '27381:3,27384:3,27386:3,27389:3,27391:3,27394:3,27398:3,27413:5,27415:-4,27416:5,27418:5,27431:5,27435:3,' ||
        '27436:7,27438:3,27439:-6,27451:7,27453:3,27458:3,27459:3,27461:5,27463:7,27468:3,27483:3,27485:3,27486:3,' ||
        '27489:3,27491:-4,27493:-4,27495:3,27496:-8,27498:3,27513:5,27514:3,27516:3,27518:3,27531:5,27534:5,27536:7,' ||
        '27538:7,27539:-6,27541:3,27543:7,27548:3,27549:3,27561:3,27563:7,27568:3,27569:3,27581:3,27583:7,27584:3,' ||
        '27586:3,27589:3,27593:-4,27594:3,27596:3,27598:3,27613:5,27614:5,27615:-4,27618:5,27631:5,27634:5,27635:11,' ||
        '27638:7,27641:7,27643:7,27648:5,27649:5,27651:7,27653:5,27658:5,27659:7,27683:7,27684:-12,27689:7,27691:-4,' ||
        '27694:5,27698:5,27813:3,27814:3,27815:3,27816:3,27831:3,27834:3,27835:3,27836:3,27839:-6,27841:3,27843:3,' ||
        '27845:-6,27846:-10,27849:5,27851:3,27853:3,27859:7,27861:3,27863:3,27865:-10,27891:-4,27893:-4,27894:5,27896:-8,' ||
        '27913:3,27914:3,27916:3,27918:5,27931:3,27934:3,27935:3,27938:7,27941:3,27943:3,27945:-4,27946:-10,27948:5,' ||
        '27953:3,27958:5,27961:3,27965:-10,27968:5,27983:7,28013:1,28014:1,28015:9,28016:1,28017:1,28019:1,28041:1,' ||
        '28043:1,28045:-6,28046:1,28047:1,28049:1,28051:-8,28054:-6,28057:-8,28071:1,28073:1,28074:1,28076:1,28079:1,' ||
        '28134:1,28135:9,28136:1,28137:1,28139:1,28143:1,28145:-6,28146:1,28149:1,28153:-8,28154:-6,28156:-6,28157:9,' ||
        '28163:1,28164:1,28165:-6,28167:1,28169:1,28173:1,28176:1,28179:1,28193:1,28194:1,28196:1,28197:1,28413:1,' ||
        '28415:9,28416:1,28419:1,28431:1,28435:9,28436:1,28437:1,28439:1,28451:-8,28453:-8,28457:-8,28459:-8,28461:1,' ||
        '28463:1,28467:1,28469:1,28473:1,28476:1,28479:1,28491:1,28493:1,28496:1,28497:1,28513:5,28514:7,28516:5,28549:5,' ||
        '28571:-4,28574:-12,28576:5,28579:5,28713:1,28715:3,28716:1,28719:1,28731:1,28734:1,28736:1,28739:1,28743:1,' ||
        '28745:-6,28746:1,28749:1,28751:3,28754:-8,28756:-6,28759:-8,28761:1,28763:1,28764:1,28765:-6,28769:1,28791:1,' ||
        '28793:1,28794:1,28796:1,51023:1,51024:1,51026:1,51027:1,51028:1,51029:7,51032:1,51034:1,51036:1,51037:1,51038:1,' ||
        '51039:-6,51062:1,51063:1,51064:1,51067:1,51068:1,51069:7,51092:5,51093:-4,51234:1,51236:1,51237:1,51238:1,' ||
        '51239:-6,51243:1,51246:1,51247:1,51248:1,51249:3,51263:1,51264:1,51267:1,51268:1,51269:3,51273:1,51274:1,' ||
        '51276:1,51278:1,51279:-6,51283:1,51284:1,51286:1,51287:1,51289:7,51293:-4,51294:3,51296:3,51297:-4,51324:1,' ||
        '51326:1,51327:1,51328:1,51329:7,51342:1,51346:1,51347:1,51348:1,51349:3,51362:1,51364:1,51367:1,51368:1,51372:1,' ||
        '51374:1,51376:1,51378:1,51379:-8,51382:1,51384:1,51386:1,51387:1,51389:7,51392:5,51394:3,51397:-10,51623:1,' ||
        '51624:1,51627:1,51628:1,51629:7,51632:1,51634:1,51637:1,51638:1,51642:1,51643:1,51647:1,51648:1,51649:7,51672:1,' ||
        '51673:1,51674:1,51678:1,51679:-6,51682:1,51683:1,51684:1,51687:1,51689:7,51692:5,51694:5,51697:-4,51923:7,' ||
        '51924:15,51926:15,51927:-14,51932:7,51934:5,51937:5,51938:15,51962:7,51964:5,51967:5,52013:1,52014:1,52016:1,' ||
        '52017:1,52019:1,52041:1,52043:1,52046:1,52047:1,52048:5,52049:1,52071:1,52073:1,52074:1,52076:1,52079:1,' ||
        '52081:-8,52087:-4,52134:1,52136:1,52137:1,52139:1,52143:1,52146:1,52148:3,52149:1,52163:1,52164:1,52167:1,' ||
        '52168:3,52169:1,52173:1,52176:1,52179:1,52183:-8,52184:3,52186:3,52187:-4,52189:-6,52193:1,52194:1,52196:1,' ||
        '52197:1,52413:1,52416:1,52418:5,52419:1,52431:1,52436:1,52437:1,52439:1,52461:1,52463:1,52467:1,52468:5,52469:1,' ||
        '52473:1,52476:1,52479:1,52481:-8,52483:-8,52487:-4,52489:-4,52491:1,52493:1,52496:1,52497:1,52713:1,52716:1,' ||
        '52718:5,52719:1,52731:1,52734:1,52736:1,52739:1,52743:1,52746:1,52748:5,52749:1,52761:1,52763:1,52764:1,52768:5,' ||
        '52769:1,52781:5,52783:5,52791:1,52793:1,52794:1,52796:1,52814:-4,52816:-8,52817:-4,52819:-10,52841:-4,52843:-8,' ||
        '52847:-4,52849:-8,52871:-4,52873:5,124356:5,124358:5,124359:-2,124365:9,124367:5,124368:7,124376:5,124378:-4,' ||
        '124379:-6,124385:5,124386:5,124387:-6,124395:-2,124397:-6,124398:7,124536:-14,124538:3,124539:3,124563:-4,' ||
        '124567:13,124568:7,124569:-6,124576:5,124578:9,124579:-6,124583:3,124586:5,124593:3,124597:13,124598:7,124635:9,' ||
        '124637:3,124638:3,124653:-4,124657:-8,124658:5,124659:-2,124673:3,124675:-4,124678:-4,124679:-6,124683:3,' ||
        '124685:5,124687:-6,124695:-2,124697:-6,124698:7,124736:-14,124738:5,124756:5,124758:5,124759:-2,124763:-4,' ||
        '124765:-6,124768:-10,124769:-6,124783:11,124785:5,124786:5,124795:-2,124835:9,124837:7,124853:-4,124856:5,' ||
        '124857:-8,124859:-2,124863:-4,124865:9,124869:-6,124873:11,124875:9,124876:5,124895:-2,124935:9,124937:7,' ||
        '124938:5,124953:-4,124956:5,124957:9,124958:5,124965:9,124967:5,124968:7,124973:11,124975:-4,124976:5,124983:11,' ||
        '124985:5,124986:5,125346:1,125347:1,125348:3,125349:1,125364:1,125367:1,125368:3,125374:1,125376:1,125378:9,' ||
        '125379:1,125384:3,125386:3,125387:-8,125389:3,125394:1,125397:1,125398:3,125436:1,125437:1,125438:3,125439:1,' ||
        '125463:1,125467:1,125468:5,125469:1,125473:1,125476:1,125478:9,125479:1,125483:3,125486:5,125487:-8,125489:-8,' ||
        '125493:1,125496:1,125497:1,125498:9,125634:1,125637:1,125638:3,125643:1,125647:1,125648:5,125649:1,125673:1,' ||
        '125674:1,125678:9,125679:1,125683:3,125684:5,125687:-8,125689:-8,125694:1,125697:1,125698:9,125734:1,125736:1,' ||
        '125738:5,125739:1,125743:1,125746:1,125748:3,125749:1,125763:1,125764:1,125768:3,125769:1,125784:3,125786:3,' ||
        '125793:1,125794:1,125796:1,125834:9,125836:9,125843:-4,125846:9,125847:-2,125849:-8,125863:-4,125864:9,' ||
        '125867:-8,125869:-8,125874:-2,125876:5,125894:5,125896:9,125934:1,125937:1,125938:5,125943:1,125946:1,125947:1,' ||
        '125948:5,125964:1,125967:1,125968:5,125973:1,125974:1,125976:1,125984:5,125986:5,126345:3,126347:-2,126348:3,' ||
        '126349:13,126354:3,126358:3,126359:-2,126374:-2,126378:3,126379:-6,126384:3,126385:3,126387:3,126389:-6,' ||
        '126394:-14,126395:-2,126397:-6,126398:-4,126435:-4,126437:3,126438:3,126439:3,126453:-4,126457:-8,126458:5,' ||
        '126459:-2,126473:3,126475:9,126478:7,126479:-6,126483:3,126485:5,126489:-6,126493:3,126495:-2,126497:-6,' ||
        '126498:-4,126534:5,126538:3,126539:3,126543:-4,126547:-2,126548:7,126549:13,126574:-2,126578:7,126579:13,' ||
        '126583:3,126584:5,126593:3,126597:-6,126598:9,126734:5,126738:5,126739:5,126743:-4,126745:9,126748:7,126749:13,' ||
        '126754:5,126758:5,126759:-2,126783:7,126784:5,126785:5,126793:5,126794:5,126795:-2,126835:9,126837:11,126839:5,' ||
        '126843:-4,126845:9,126847:-2,126853:-4,126854:5,126857:-8,126859:-2,126873:7,126874:-2,126875:9,126893:5,' ||
        '126894:5,126895:-2,126935:-4,126937:11,126938:5,126943:-4,126945:3,126947:-2,126948:3,126953:-4,126954:3,' ||
        '126957:3,126958:3,126973:7,126974:-2,126975:3,126983:7,126984:3,126985:3,127345:-4,127346:3,127348:3,127349:3,' ||
        '127358:5,127359:-2,127364:3,127365:-10,127368:3,127384:3,127386:3,127389:3,127394:3,127395:-2,127398:3,' ||
        '127435:11,127436:7,127439:-6,127453:5,127458:5,127459:-2,127463:7,127468:5,127483:-4,127486:-10,127493:-4,' ||
        '127495:-2,127496:-8,127498:5,127534:5,127536:7,127538:7,127539:-6,127543:7,127548:3,127549:3,127563:7,127568:3,' ||
        '127569:3,127583:-4,127584:3,127586:3,127589:3,127593:-4,127594:3,127596:3,127598:3,127634:5,127635:11,127638:7,' ||
        '127643:7,127648:5,127649:5,127653:5,127658:5,127659:-2,127683:-4,127684:-12,127689:9,127694:5,127695:-2,' ||
        '127698:5,127834:3,127835:3,127836:3,127839:-6,127843:3,127845:-6,127846:-10,127849:5,127853:3,127859:-2,' ||
        '127863:3,127865:-10,127893:-4,127894:5,127895:-2,127896:-8,127934:3,127935:3,127938:7,127943:3,127945:-4,' ||
        '127946:-10,127948:5,127953:3,127958:5,127965:-10,127968:5,127983:-4,128345:-6,128346:1,128347:1,128349:1,' ||
        '128354:-6,128356:-6,128359:-2,128364:1,128365:-6,128367:1,128374:1,128376:1,128379:1,128394:1,128395:-2,' ||
        '128397:1,128435:9,128436:1,128437:1,128439:1,128453:-8,128457:-8,128459:-2,128463:1,128467:1,128469:1,128473:1,' ||
        '128476:1,128479:1,128493:1,128495:-2,128496:1,128497:1,128534:5,128536:7,128547:-2,128549:5,128567:5,128574:-2,' ||
        '128576:5,128579:5,128593:-4,128596:-12,128634:1,128635:9,128637:1,128643:1,128647:1,128649:1,128653:-8,' ||
        '128657:-8,128659:-2,128673:1,128674:1,128679:1,128694:1,128695:-2,128697:1,128734:1,128736:1,128739:1,128743:1,' ||
        '128745:-6,128746:1,128749:1,128754:-8,128756:-6,128759:-2,128763:1,128764:1,128765:-6,128769:1,128793:1,' ||
        '128794:1,128795:-2,128796:1,128934:1,128935:3,128937:1,128943:1,128945:-6,128946:1,128947:1,128953:3,128954:-6,' ||
        '128956:-8,128957:-8,128964:1,128965:-6,128967:1,128973:1,128974:1,128976:1,129345:3,129347:-2,129348:3,129354:3,' ||
        '129358:3,129364:-10,129365:-4,129367:5,129368:5,129374:-2,129376:5,129378:3,129384:3,129385:3,129387:3,' ||
        '129435:-4,129436:5,129438:5,129453:7,129457:7,129458:5,129463:7,129467:5,129468:5,129473:-4,129476:5,129478:5,' ||
        '129483:-4,129486:-10,129487:7,129534:5,129536:5,129538:5,129543:5,129547:-2,129548:5,129563:7,129567:5,129568:5,' ||
        '129574:-2,129576:5,129578:5,129583:-4,129587:7,129634:5,129635:-4,129638:5,129643:5,129647:-2,129648:3,129653:7,' ||
        '129657:3,129658:3,129673:-4,129674:-2,129675:3,129678:3,129683:-4,129684:3,129685:3,129687:3,129734:3,129736:3,' ||
        '129738:5,129743:3,129745:-10,129748:5,129758:5,129763:3,129764:-10,129765:-4,129768:5,129783:-4,129834:3,' ||
        '129835:3,129836:3,129843:3,129845:-10,129847:-2,129853:3,129857:7,129863:3,129864:-10,129865:-6,129867:5,' ||
        '129873:-4,129874:-2,129876:5,134256:7,134257:5,134259:-2,134265:9,134268:7,134269:13,134278:-6,134279:-4,' ||
        '134286:5,134287:-4,134295:-2,134296:5,134297:-4,134298:7,134526:7,134527:3,134529:3,134562:-4,134567:15,' ||
        '134568:7,134572:3,134578:-12,134579:-4,134586:5,134587:15,134592:3,134596:5,134597:-14,134598:7,134625:-4,' ||
        '134627:3,134628:3,134629:3,134652:-4,134657:15,134658:-6,134659:-2,134672:3,134678:-6,134679:-6,134682:3,' ||
        '134685:-4,134687:-4,134692:3,134695:-2,134697:-4,134698:7,134725:-6,134726:-14,134728:7,134752:-4,134756:9,' ||
        '134758:-8,134759:-2,134762:-4,134768:-10,134782:7,134785:-6,134786:5,134792:5,134795:-2,134796:5,134826:7,' ||
        '134827:5,134856:7,134857:5,134859:-2,134862:-4,134865:9,134872:7,134875:5,134876:5,134892:5,134895:-2,134896:5,' ||
        '134925:-4,134926:7,134927:5,134928:7,134952:-4,134956:7,134958:-6,134962:-4,134965:9,134968:7,134972:7,134975:5,' ||
        '134976:5,134982:7,134985:-4,134986:5,135246:1,135247:-2,135248:1,135249:1,135264:1,135267:3,135268:1,135269:1,' ||
        '135274:-2,135276:3,135278:-10,135279:3,135284:1,135286:1,135287:-8,135289:1,135294:1,135296:1,135297:3,135298:1,' ||
        '135426:1,135427:3,135428:1,135429:1,135462:1,135468:1,135469:1,135472:3,135476:5,135478:-10,135482:1,135486:1,' ||
        '135487:-8,135489:1,135492:1,135496:1,135498:1,135624:1,135627:3,135628:1,135629:1,135642:1,135647:-2,135648:1,' ||
        '135649:1,135672:3,135674:-2,135678:-10,135682:1,135684:1,135687:-8,135689:1,135692:1,135694:1,135698:1,135724:9,' ||
        '135726:9,135728:7,135742:-4,135746:7,135748:-10,135762:-4,135764:7,135768:-10,135782:7,135784:5,135786:5,' ||
        '135792:7,135794:5,135796:5,135824:1,135826:1,135829:1,135842:1,135846:1,135847:-2,135849:1,135862:1,135864:1,' ||
        '135867:3,135869:1,135872:5,135874:-2,135876:3,135892:1,135894:1,135896:1,135924:1,135926:1,135928:1,135942:1,' ||
        '135946:1,135947:-2,135948:1,135962:1,135964:1,135968:1,135972:5,135974:-2,135976:5,135982:1,135984:1,135986:1,' ||
        '136245:1,136247:1,136248:1,136249:13,136254:1,136257:1,136259:-2,136274:1,136275:1,136278:1,136279:-6,136284:1,' ||
        '136287:1,136289:-6,136295:-2,136297:-4,136298:-6,136425:1,136427:1,136428:1,136429:3,136452:1,136457:1,136458:1,' ||
        '136459:-2,136472:1,136475:1,136478:1,136479:-6,136482:1,136485:1,136487:1,136489:-6,136492:3,136495:-2,' ||
        '136497:-4,136498:-6,136524:1,136527:1,136529:3,136542:1,136547:1,136548:1,136572:1,136574:1,136578:1,136584:1,' ||
        '136587:1,136592:3,136597:-6,136598:-12,136724:1,136725:1,136728:1,136729:5,136742:1,136745:1,136748:1,136752:1,' ||
        '136754:1,136758:1,136759:-2,136782:1,136784:1,136785:1,136792:5,136794:5,136795:-2,136824:1,136827:1,136829:5,' ||
        '136842:1,136845:1,136847:1,136854:1,136857:1,136859:-2,136872:1,136874:1,136875:1,136892:5,136894:5,136895:-2,' ||
        '136924:-12,136925:-4,136927:11,136928:7,136942:-4,136947:-2,136948:-10,136952:-4,136958:-8,136972:7,136974:-2,' ||
        '136975:5,136982:7,136984:5,136985:-4,137245:-6,137246:1,137248:1,137249:1,137259:-2,137264:1,137265:-10,' ||
        '137268:1,137269:1,137284:1,137286:1,137289:1,137294:1,137295:-2,137296:1,137298:1,137425:-10,137426:1,137428:1,' ||
        '137429:1,137459:-2,137462:1,137468:1,137469:1,137482:1,137485:-6,137486:1,137489:1,137492:1,137495:-2,137496:1,' ||
        '137498:1,137524:5,137526:7,137529:9,137542:15,137548:5,137549:5,137568:5,137569:5,137584:5,137586:15,137589:9,' ||
        '137592:-4,137594:9,137596:9,137598:7,137624:1,137625:-10,137628:1,137629:1,137642:1,137648:1,137649:1,137659:-2,' ||
        '137682:1,137684:1,137685:-6,137689:1,137692:1,137694:1,137695:-2,137698:1,137824:1,137826:1,137829:1,137842:1,' ||
        '137845:-6,137846:1,137849:1,137859:-2,137862:1,137864:1,137865:-10,137869:1,137892:1,137894:1,137895:-2,' ||
        '137896:1,137924:1,137925:3,137926:1,137928:1,137942:1,137945:-6,137946:1,137948:1,137952:3,137962:1,137964:1,' ||
        '137965:-10,137968:1,137982:1,137984:1,137985:-6,137986:1,138245:-4,138246:3,138247:-2,138249:3,138254:-6,' ||
        '138256:-4,138257:-16,138259:-2,138264:3,138265:-4,138267:3,138269:3,138274:-2,138276:3,138279:3,138294:3,' ||
        '138295:-2,138296:3,138297:3,138425:9,138426:7,138429:13,138452:5,138457:5,138459:-2,138462:7,138467:5,138469:5,' ||
        '138472:-4,138476:7,138479:7,138492:-4,138495:-2,138496:5,138497:5,138524:7,138526:7,138542:5,138547:-2,138549:3,' ||
        '138562:7,138567:3,138569:3,138572:-4,138574:-2,138576:3,138579:3,138592:-4,138594:3,138596:3,138597:3,138624:7,' ||
        '138625:9,138629:11,138642:5,138647:-2,138649:5,138652:5,138657:5,138659:-2,138672:-4,138674:-2,138679:7,' ||
        '138692:-4,138694:5,138695:-2,138697:5,138724:3,138725:3,138726:3,138742:3,138745:-6,138746:7,138749:5,138752:3,' ||
        '138754:-8,138756:-4,138759:-2,138762:3,138764:7,138765:-6,138769:5,138792:-4,138794:5,138795:-2,138796:5,' ||
        '138924:3,138925:3,138926:3,138942:3,138945:-4,138946:7,138947:-2,138952:3,138954:-6,138962:3,138964:7,138965:-4,' ||
        '138967:5,138972:-4,138974:-2,138975:-10,138976:7,139245:1,139247:1,139248:1,139254:1,139257:1,139264:-10,' ||
        '139265:-4,139267:5,139268:5,139274:1,139275:1,139278:1,139284:1,139286:5,139287:1,139425:1,139426:5,139427:1,' ||
        '139428:1,139452:1,139457:1,139458:1,139462:15,139467:5,139468:5,139472:1,139475:1,139478:1,139482:1,139485:1,' ||
        '139486:5,139487:1,139524:1,139526:5,139527:1,139542:1,139547:1,139548:1,139562:15,139567:5,139568:5,139572:1,' ||
        '139574:1,139576:9,139578:1,139584:1,139586:5,139587:1,139624:7,139625:-4,139647:-2,139648:5,139657:5,139672:-4,' ||
        '139674:-2,139675:-10,139682:-4,139684:-10,139685:-4,139724:1,139725:1,139726:3,139728:1,139742:1,139745:1,' ||
        '139748:1,139752:1,139754:1,139758:1,139762:3,139764:-10,139765:-6,139768:5,139782:1,139784:1,139785:1,139786:5,' ||
        '139824:1,139826:3,139827:1,139842:1,139845:1,139847:1,139854:1,139857:1,139862:3,139864:-10,139865:-4,139867:5,' ||
        '139872:1,139874:1,139875:1,152346:1,152347:1,152349:1,152364:1,152367:1,152368:5,152374:1,152376:1,152379:1,' ||
        '152384:-6,152386:-8,152387:-6,152389:-4,152394:1,152397:1,152436:1,152437:1,152439:1,152463:1,152467:1,152468:5,' ||
        '152469:1,152473:1,152476:1,152479:1,152483:-8,152487:-4,152489:-4,152493:1,152496:1,152497:1,152634:1,152637:1,' ||
        '152638:5,152643:1,152647:1,152648:7,152649:1,152673:1,152674:1,152679:1,152683:-8,152687:-4,152689:-4,152694:1,' ||
        '152697:1,152734:1,152736:1,152739:1,152743:1,152746:1,152748:7,152749:1,152763:1,152764:1,152768:5,152769:1,' ||
        '152783:5,152793:1,152794:1,152796:1,152834:-8,152836:-4,152837:-10,152839:-4,152843:-8,152847:-2,152849:-4,' ||
        '152863:-4,152867:-8,152869:-4,152873:5,152874:-2,152876:-16,152893:-4,152934:1,152937:1,152938:5,152943:1,' ||
        '152946:1,152947:1,152948:7,152964:1,152967:1,152968:5,152973:1,152974:1,152976:1,152983:5,153246:1,153247:-2,' ||
        '153248:1,153249:1,153264:1,153267:-8,153268:1,153269:1,153274:-2,153279:-4,153284:1,153286:1,153287:7,153289:1,' ||
        '153294:1,153296:1,153297:-6,153298:1,153426:1,153427:7,153428:1,153429:1,153462:1,153467:-8,153468:1,153469:1,' ||
        '153472:5,153476:13,153479:-4,153482:1,153486:1,153487:7,153489:1,153492:1,153496:1,153497:-6,153498:1,153624:1,' ||
        '153627:3,153628:1,153629:1,153642:1,153647:-2,153648:1,153649:1,153672:3,153674:-2,153678:3,153679:-4,153682:1,' ||
        '153684:1,153687:3,153689:1,153692:1,153694:1,153697:-6,153698:1,153724:15,153726:15,153729:-4,153742:7,' ||
        '153746:13,153749:-4,153762:15,153768:15,153769:-4,153782:5,153792:5,153794:-8,153796:13,153824:1,153826:1,' ||
        '153827:7,153829:1,153842:1,153846:1,153847:-2,153849:1,153862:1,153864:1,153867:-8,153869:1,153872:5,153874:-2,' ||
        '153876:13,153892:1,153894:1,153896:1,153924:1,153926:1,153927:3,153928:1,153942:1,153946:1,153947:-2,153948:1,' ||
        '153962:1,153964:1,153967:-8,153968:1,153972:3,153974:-2,153976:13,153982:1,153984:1,153986:1,156237:1,156238:1,' ||
        '156239:1,156243:-8,156247:-2,156249:-4,156273:1,156274:-2,156278:1,156279:1,156283:1,156284:5,156287:1,156289:1,' ||
        '156293:1,156297:1,156298:1,156324:3,156327:1,156328:1,156329:1,156342:3,156347:-2,156348:3,156349:-4,156372:1,' ||
        '156374:-2,156378:1,156379:1,156382:1,156384:3,156387:1,156389:1,156392:1,156397:1,156398:1,156423:-2,156427:-8,' ||
        '156429:-4,156432:-2,156437:-10,156438:-8,156439:-4,156479:-4,156483:-8,156487:-4,156489:-4,156492:-8,156497:-4,' ||
        '156498:-4,156723:1,156724:5,156728:1,156729:1,156732:1,156738:1,156739:1,156749:-4,156782:1,156783:1,156784:5,' ||
        '156792:1,156793:1,156794:5,156823:1,156824:5,156827:1,156829:1,156832:1,156837:1,156839:1,156843:-8,156847:-2,' ||
        '156849:-4,156872:1,156873:1,156874:-2,156892:1,156893:1,156894:5,156923:1,156924:3,156927:1,156928:1,156932:1,' ||
        '156937:1,156938:1,156942:3,156943:-8,156947:-2,156948:3,156972:1,156973:1,156974:-2,156982:1,156983:1,156984:3,' ||
        '162345:9,162347:-2,162349:11,162354:5,162358:5,162359:-2,162374:-2,162384:-6,162385:-6,162387:-6,162389:-6,' ||
        '162394:5,162395:-2,162398:-14,162435:9,162437:11,162439:5,162453:-4,162457:-8,162458:5,162459:-2,162473:7,' ||
        '162475:9,162485:9,162487:-6,162489:-4,162493:5,162495:-2,162534:3,162538:5,162539:3,162543:3,162547:-2,162548:7,' ||
        '162549:3,162574:-2,162579:3,162584:7,162587:-6,162589:-4,162593:3,162594:3,162597:3,162598:-14,162734:5,' ||
        '162738:5,162739:5,162743:7,162745:9,162748:7,162749:11,162754:5,162758:5,162759:-2,162783:5,162785:9,162793:5,' ||
        '162794:5,162795:-2,162834:3,162835:-4,162837:3,162839:3,162843:3,162845:9,162847:-2,162849:3,162853:-4,162854:5,' ||
        '162857:-8,162859:-2,162873:3,162874:-2,162875:9,162893:3,162894:3,162895:-2,162934:5,162935:-4,162937:11,' ||
        '162943:7,162945:9,162947:-2,162948:7,162953:9,162954:5,162957:-8,162958:5,162973:7,162974:-2,162975:9,162983:5,' ||
        '162985:9,163245:1,163247:1,163248:1,163249:5,163254:1,163257:1,163259:-2,163274:1,163275:1,163278:1,163279:-6,' ||
        '163284:1,163287:1,163294:5,163295:-2,163297:-6,163298:-8,163425:1,163427:1,163428:1,163429:5,163452:1,163457:1,' ||
        '163458:1,163459:-2,163472:1,163475:1,163478:1,163479:-6,163482:1,163485:1,163487:1,163492:5,163495:-2,163497:-6,' ||
        '163498:-8,163524:1,163527:1,163529:3,163542:1,163547:1,163548:1,163549:3,163572:1,163574:1,163578:1,163579:-6,' ||
        '163584:1,163587:1,163589:3,163592:3,163594:3,163597:-6,163598:3,163724:1,163725:1,163728:1,163729:3,163742:1,' ||
        '163745:1,163748:1,163749:3,163752:1,163754:1,163758:1,163759:-2,163782:1,163784:1,163785:1,163792:3,163794:3,' ||
        '163795:-2,163824:1,163827:1,163829:5,163842:1,163845:1,163847:1,163849:5,163854:1,163857:1,163859:-2,163872:1,' ||
        '163874:1,163875:1,163892:5,163894:5,163895:-2,163924:-10,163925:-4,163927:-12,163928:-10,163947:-2,163972:5,' ||
        '163974:-2,163975:11,163984:-10,163985:-10,164235:9,164237:1,164238:1,164239:1,164253:-8,164257:-8,164259:-2,' ||
        '164273:1,164278:1,164279:1,164283:1,164287:1,164289:1,164293:1,164295:-2,164297:1,164298:1,164325:-6,164327:1,' ||
        '164328:1,164329:1,164352:-6,164358:-6,164359:-2,164372:1,164378:1,164379:1,164382:1,164385:-6,164387:1,164389:1,' ||
        '164392:1,164395:-2,164397:1,164398:1,164523:-2,164527:5,164532:-2,164538:5,164539:5,164572:5,164578:-12,' ||
        '164579:-4,164583:-8,164598:7,164723:1,164725:-6,164728:1,164729:1,164732:1,164738:1,164739:1,164752:-6,' ||
        '164758:-8,164759:-2,164782:1,164783:1,164785:-6,164792:1,164793:1,164795:-2,164823:1,164827:1,164829:1,164832:1,' ||
        '164835:9,164837:1,164839:1,164853:-8,164857:-8,164859:-2,164872:1,164873:1,164892:1,164893:1,164895:-2,164923:1,' ||
        '164925:-6,164927:1,164928:1,164932:1,164935:9,164937:1,164938:1,164952:-6,164953:-8,164957:9,164958:-6,164972:1,' ||
        '164973:1,164982:1,164983:1,164985:-6,165234:3,165237:1,165238:1,165239:1,165243:3,165247:-2,165248:5,165249:3,' ||
        '165273:1,165274:-2,165278:1,165279:1,165283:1,165284:5,165287:1,165289:1,165293:1,165294:3,165297:1,165298:1,' ||
        '165324:3,165327:1,165328:1,165329:1,165342:3,165347:-2,165348:3,165349:3,165372:1,165374:-2,165378:1,165379:1,' ||
        '165382:1,165384:3,165387:1,165389:1,165392:1,165394:3,165397:1,165398:1,165423:-2,165427:-8,165428:9,165429:-8,' ||
        '165432:-2,165438:-16,165472:9,165478:9,165482:9,165483:-8,165487:-8,165489:-4,165492:9,165498:9,165723:1,' ||
        '165724:3,165728:1,165729:1,165732:1,165734:5,165738:1,165739:1,165742:3,165748:3,165749:3,165782:1,165783:1,' ||
        '165784:3,165792:1,165793:1,165794:3,165823:1,165824:5,165827:1,165829:1,165832:1,165834:3,165837:1,165839:1,' ||
        '165842:5,165843:3,165847:-2,165849:3,165872:1,165873:1,165874:-2,165892:1,165893:1,165894:3,165923:1,165924:5,' ||
        '165927:1,165928:1,165932:1,165934:5,165937:1,165938:1,165942:5,165947:-2,165948:5,165972:1,165973:1,165974:-2,' ||
        '165982:1,165983:1,165984:5,167234:7,167235:11,167238:7,167239:9,167243:7,167248:-12,167253:5,167254:5,167259:-2,' ||
        '167283:-8,167284:5,167289:9,167294:5,167295:-2,167298:5,167324:3,167325:-10,167328:3,167329:3,167342:3,167348:3,' ||
        '167349:3,167354:5,167359:-2,167382:3,167384:3,167385:-4,167389:3,167392:3,167394:3,167395:-2,167398:3,167423:-2,' ||
        '167425:-10,167429:5,167432:-2,167435:11,167439:9,167453:5,167459:-2,167482:-10,167483:-6,167485:-6,167492:5,' ||
        '167493:13,167495:-2,167498:5,167523:-2,167524:3,167529:3,167532:-2,167534:7,167538:7,167539:9,167542:3,167543:7,' ||
        '167548:3,167549:3,167583:-8,167584:3,167589:3,167592:3,167593:13,167594:3,167598:3,167823:-2,167824:3,167829:5,' ||
        '167832:-2,167834:3,167835:3,167839:9,167842:3,167843:3,167845:3,167853:3,167854:3,167859:-2,167892:5,167893:13,' ||
        '167894:5,167895:-2,167923:-2,167924:3,167925:3,167932:-2,167934:3,167935:3,167938:7,167942:3,167943:3,167945:3,' ||
        '167952:3,167953:3,167954:3,167982:-10,167984:5,167985:-4,168234:3,168235:9,168237:3,168239:3,168243:3,168245:5,' ||
        '168247:-2,168249:3,168253:-4,168254:5,168257:-8,168259:-2,168273:3,168274:-2,168275:-4,168279:3,168293:3,' ||
        '168294:3,168295:-2,168297:3,168324:7,168325:9,168327:11,168329:11,168342:5,168345:5,168347:-2,168349:7,168352:5,' ||
        '168354:5,168359:-2,168372:5,168374:-2,168379:5,168392:-14,168394:5,168395:-2,168397:5,168423:-2,168425:9,' ||
        '168432:-2,168435:9,168437:7,168439:5,168452:5,168453:-4,168457:-8,168459:-2,168473:11,168475:9,168479:5,' ||
        '168493:5,168495:-2,168497:5,168523:-2,168524:7,168527:13,168532:-2,168534:3,168539:3,168542:5,168543:3,' ||
        '168547:-2,168549:3,168572:5,168574:-2,168579:3,168592:-14,168593:3,168594:3,168597:3,168723:-2,168724:3,' ||
        '168725:3,168732:-2,168734:3,168739:5,168742:3,168743:3,168745:3,168749:7,168752:3,168754:3,168759:-2,168792:-12,' ||
        '168793:5,168794:5,168795:-2,168923:-2,168924:3,168925:3,168927:13,168932:-2,168934:3,168935:3,168937:7,168942:3,' ||
        '168943:3,168945:3,168947:-2,168952:3,168953:3,168954:3,168957:-8,168973:11,168974:-2,168975:-4,169234:5,' ||
        '169238:5,169243:5,169245:1,169247:1,169248:1,169253:7,169254:1,169257:1,169274:1,169275:1,169278:1,169283:5,' ||
        '169284:1,169287:1,169324:7,169325:-10,169347:-2,169354:5,169372:5,169374:-2,169378:5,169382:-10,169384:-10,' ||
        '169385:-4,169423:-2,169425:1,169427:1,169428:1,169432:-2,169438:5,169452:1,169453:7,169457:1,169458:1,169472:1,' ||
        '169475:1,169478:1,169482:1,169483:5,169485:1,169487:1,169523:-2,169524:1,169527:1,169532:-2,169534:5,169538:5,' ||
        '169542:1,169543:5,169547:1,169548:1,169572:1,169574:1,169578:1,169583:5,169584:1,169587:1,169723:-2,169724:1,' ||
        '169725:1,169728:1,169732:-2,169734:3,169738:5,169742:1,169743:3,169745:1,169748:1,169752:1,169754:1,169758:1,' ||
        '169782:1,169783:5,169784:1,169785:1,169823:-2,169824:1,169827:1,169832:-2,169834:3,169835:3,169842:1,169843:3,' ||
        '169845:1,169847:1,169853:3,169854:1,169857:1,169872:1,169874:1,169875:1,192345:-4,192346:7,192347:-2,192354:-6,' ||
        '192358:5,192364:7,192365:-4,192368:-14,192374:-2,192376:5,192378:5,192384:-8,192385:-4,192435:-4,192436:5,' ||
        '192437:-4,192453:-4,192457:-8,192458:5,192463:5,192468:7,192473:7,192475:-4,192476:5,192478:5,192483:13,' ||
        '192485:-4,192486:7,192534:3,192536:3,192538:5,192543:3,192547:-2,192548:7,192563:3,192567:3,192568:7,192574:-2,' ||
        '192576:3,192578:5,192586:7,192634:5,192635:-4,192637:-4,192643:5,192647:-2,192648:7,192653:11,192657:-8,' ||
        '192658:5,192673:7,192674:-2,192675:-4,192678:5,192683:11,192685:-4,192687:13,192734:5,192736:5,192738:5,' ||
        '192743:5,192745:-4,192746:7,192748:7,192754:-6,192756:-4,192758:5,192763:5,192764:7,192765:-4,192768:7,' ||
        '192785:-4,192786:7,192834:3,192835:-4,192836:3,192837:3,192843:3,192845:-4,192846:3,192847:-2,192853:-4,' ||
        '192854:-6,192856:-4,192857:-8,192863:3,192864:3,192865:-4,192867:3,192873:3,192874:-2,192875:-4,192876:3,' ||
        '193245:1,193247:1,193248:1,193254:1,193257:1,193264:-10,193265:-4,193267:-6,193268:-8,193274:1,193275:1,' ||
        '193278:1,193284:1,193286:5,193287:1,193425:1,193426:5,193427:1,193428:1,193452:1,193457:1,193458:1,193462:5,' ||
        '193467:-8,193468:15,193472:1,193475:1,193476:7,193478:1,193482:1,193485:1,193486:5,193487:1,193524:1,193526:3,' ||
        '193527:1,193542:1,193547:1,193548:1,193562:3,193567:-8,193568:3,193572:1,193574:1,193576:7,193578:1,193584:1,' ||
        '193586:3,193587:1,193624:-10,193625:-4,193627:-8,193628:-4,193642:5,193647:-2,193672:-12,193674:-2,193675:-4,' ||
        '193684:-10,193685:-4,193724:1,193725:1,193726:3,193728:1,193742:1,193745:1,193746:3,193748:1,193752:1,193754:1,' ||
        '193758:1,193762:3,193764:3,193765:-4,193768:3,193782:1,193784:1,193785:1,193786:3,193824:1,193826:5,193827:1,' ||
        '193842:1,193845:1,193847:1,193854:1,193857:1,193862:5,193864:-10,193865:-4,193872:1,193874:1,193875:1,193876:7,' ||
        '196235:-4,196237:11,196238:5,196245:1,196247:1,196248:1,196253:-8,196254:1,196257:1,196273:7,196274:1,196275:1,' ||
        '196278:1,196283:5,196284:1,196287:1,196324:-14,196325:-4,196327:11,196328:7,196342:-12,196345:-4,196347:-2,' ||
        '196348:-8,196352:-8,196354:5,196358:-4,196372:5,196374:-2,196378:5,196382:7,196384:-12,196385:-4,196387:11,' ||
        '196423:-2,196425:1,196427:1,196428:1,196432:-2,196435:-4,196437:3,196438:3,196452:1,196453:-8,196457:1,196458:1,' ||
        '196472:1,196473:3,196475:1,196478:1,196482:1,196483:3,196485:1,196487:1,196523:-2,196524:1,196527:1,196532:-2,' ||
        '196534:5,196538:3,196542:1,196547:1,196548:1,196572:1,196574:1,196578:1,196583:3,196584:1,196587:1,196723:-2,' ||
        '196724:1,196725:1,196728:1,196732:-2,196734:5,196738:5,196742:1,196745:1,196748:1,196752:1,196754:1,196758:1,' ||
        '196782:1,196783:5,196784:1,196785:1,196823:-2,196824:1,196827:1,196832:-2,196835:-4,196837:11,196842:1,' ||
        '196843:13,196845:1,196847:1,196853:-8,196854:1,196857:1,196872:1,196873:7,196874:1,196875:1,214356:1,214358:1,' ||
        '214359:1,214365:1,214367:5,214368:1,214376:5,214378:-6,214379:-4,214385:1,214386:1,214387:-6,214389:1,214395:1,' ||
        '214397:-6,214398:1,214536:1,214538:1,214539:1,214563:1,214568:1,214569:1,214576:5,214578:-12,214579:-6,214583:1,' ||
        '214586:1,214589:1,214593:1,214596:1,214598:1,214635:1,214637:3,214638:1,214653:1,214657:-8,214658:1,214659:1,' ||
        '214673:3,214675:-4,214678:-6,214679:-4,214683:1,214685:1,214687:-6,214689:1,214695:1,214697:-6,214698:1,' ||
        '214738:5,214739:-4,214756:5,214758:-2,214759:5,214763:-4,214768:-12,214769:-4,214783:11,214785:-2,214786:5,' ||
        '214795:5,214835:1,214836:1,214837:7,214839:1,214853:1,214856:1,214857:-8,214859:1,214863:1,214865:1,214869:1,' ||
        '214873:11,214875:-4,214876:5,214893:1,214895:1,214896:1,214935:1,214937:7,214938:1,214953:1,214956:1,214957:9,' ||
        '214958:1,214965:1,214967:5,214968:1,214973:11,214976:5,214983:1,214985:1,214986:1,215346:1,215347:1,215348:1,' ||
        '215349:3,215364:1,215367:1,215368:1,215374:1,215376:1,215378:1,215384:1,215386:1,215387:1,215389:3,215394:3,' ||
        '215398:3,215436:1,215437:1,215438:1,215439:3,215463:1,215467:1,215468:1,215469:-8,215473:1,215476:1,215478:1,' ||
        '215483:1,215486:1,215487:1,215489:-8,215493:3,215496:-10,215498:-10,215634:1,215637:1,215638:1,215643:1,' ||
        '215647:1,215648:1,215673:1,215674:1,215678:1,215683:1,215684:1,215687:1,215689:-8,215694:5,215698:-10,215734:1,' ||
        '215736:1,215738:1,215743:1,215746:1,215748:1,215749:3,215763:1,215764:1,215768:1,215769:3,215783:1,215784:1,' ||
        '215786:1,215794:3,215796:3,215834:1,215836:1,215837:1,215843:1,215846:1,215847:1,215849:-8,215863:1,215864:1,' ||
        '215867:1,215869:-8,215873:1,215874:1,215876:1,215894:5,215896:-10,215934:7,215938:5,215943:-4,215946:7,215948:9,' ||
        '215964:7,215968:5,215974:5,215976:5,215984:5,215986:5,216345:3,216347:3,216348:3,216354:3,216358:-2,216359:5,' ||
        '216374:3,216378:3,216379:-4,216384:3,216385:-2,216387:3,216389:-4,216397:-4,216398:-6,216435:-4,216437:3,' ||
        '216438:3,216439:3,216453:-4,216457:-8,216458:-2,216459:15,216473:3,216475:-4,216478:7,216479:-4,216483:3,' ||
        '216485:-2,216489:-4,216493:3,216497:-6,216498:-6,216534:5,216538:3,216539:3,216543:-4,216548:7,216549:15,' ||
        '216574:5,216578:7,216579:-14,216583:3,216584:5,216589:15,216593:3,216597:-4,216598:-12,216734:5,216738:5,' ||
        '216739:5,216743:-4,216745:9,216748:7,216754:5,216758:-2,216759:5,216783:5,216784:5,216785:-2,216793:7,216794:5,' ||
        '216795:5,216835:-4,216837:-4,216839:5,216843:-4,216845:9,216853:-4,216854:5,216857:-8,216859:15,216873:7,' ||
        '216874:5,216875:-4,216893:7,216894:5,216895:5,216937:-4,216938:5,216943:-4,216945:3,216947:3,216948:3,216953:-4,' ||
        '216954:3,216957:3,216958:-2,216973:7,216974:3,216975:3,216983:5,216984:3,216985:-2,217345:-4,217346:3,217348:3,' ||
        '217349:3,217356:1,217358:1,217359:1,217364:3,217365:1,217368:1,217384:3,217385:1,217386:1,217389:1,217394:3,' ||
        '217395:1,217398:1,217436:7,217438:-12,217439:-4,217453:11,217458:-2,217459:5,217468:5,217469:-4,217483:-4,' ||
        '217485:-2,217486:-10,217493:-4,217496:-8,217534:5,217536:1,217538:1,217539:1,217548:3,217549:3,217563:1,' ||
        '217568:1,217569:1,217583:1,217584:3,217586:1,217589:1,217593:1,217594:3,217596:1,217598:1,217634:5,217635:1,' ||
        '217638:1,217648:5,217649:5,217653:1,217658:1,217659:1,217683:1,217684:5,217685:1,217689:1,217694:5,217695:1,' ||
        '217698:1,217834:3,217835:1,217836:1,217839:1,217843:3,217845:-4,217846:-10,217849:5,217853:1,217856:1,217859:1,' ||
        '217863:1,217865:1,217869:1,217893:1,217894:5,217895:1,217896:1,217934:3,217935:1,217938:1,217943:3,217945:-6,' ||
        '217946:-10,217948:5,217953:1,217956:1,217958:1,217965:1,217968:1,217983:1,217984:5,217985:1,217986:1,218345:-4,' ||
        '218346:7,218347:5,218349:5,218354:-4,218356:-6,218359:5,218364:7,218365:-4,218367:5,218374:5,218376:5,218379:5,' ||
        '218394:7,218395:5,218397:7,218435:-4,218436:7,218437:7,218439:-4,218453:-8,218457:11,218459:5,218467:5,' ||
        '218469:-4,218473:-4,218475:-4,218476:5,218479:5,218493:-4,218496:-6,218497:7,218534:5,218536:7,218539:-14,' ||
        '218547:5,218549:5,218567:5,218569:15,218574:5,218576:5,218579:5,218593:-4,218594:-12,218596:-12,218634:5,' ||
        '218635:-4,218637:7,218647:5,218649:5,218653:-8,218657:-4,218659:5,218673:-4,218674:5,218675:-4,218679:5,' ||
        '218694:7,218695:5,218697:7,218734:3,218736:3,218739:-4,218743:3,218745:-4,218746:7,218749:5,218756:-6,218759:5,' ||
        '218763:3,218764:7,218765:-4,218769:-4,218793:-4,218794:7,218796:-6,218934:3,218935:3,218937:7,218943:3,' ||
        '218945:-6,218946:7,218947:5,218953:3,218954:-4,218956:-8,218957:-4,218964:7,218965:-6,218967:5,218973:-4,' ||
        '218974:5,218976:5,219345:3,219346:1,219347:1,219348:1,219354:3,219358:-2,219364:1,219365:-6,219367:1,219368:1,' ||
        '219374:1,219376:1,219378:1,219384:1,219385:-2,219386:1,219387:1,219436:1,219437:1,219438:1,219453:9,219457:9,' ||
        '219458:-2,219463:1,219467:1,219468:1,219473:1,219476:1,219478:1,219483:1,219485:-2,219486:1,219487:1,219534:5,' ||
        '219536:5,219538:5,219543:9,219547:5,219548:5,219563:9,219567:5,219568:5,219574:5,219576:5,219578:5,219583:-4,' ||
        '219584:15,219587:9,219634:1,219637:1,219638:1,219643:1,219647:1,219648:1,219653:9,219657:3,219658:-2,219673:1,' ||
        '219674:1,219675:3,219678:1,219683:1,219684:1,219685:-2,219687:1,219734:1,219736:1,219738:1,219743:1,219745:-10,' ||
        '219746:1,219748:1,219758:-2,219763:1,219764:1,219765:-6,219768:1,219783:1,219784:1,219785:-2,219786:1,219834:1,' ||
        '219835:3,219836:1,219837:1,219843:1,219845:-10,219846:1,219847:1,219853:3,219857:9,219863:1,219864:1,219865:-6,' ||
        '219867:1,219873:1,219874:1,219876:1,241356:1,241358:1,241359:1,241365:1,241367:5,241368:1,241376:5,241378:-8,' ||
        '241379:-8,241385:1,241386:1,241389:1,241395:1,241398:1,241536:1,241538:1,241539:1,241563:1,241567:3,241568:1,' ||
        '241569:1,241576:3,241578:3,241579:-6,241583:1,241586:1,241587:3,241589:1,241593:1,241596:1,241597:-6,241598:1,' ||
        '241635:1,241638:1,241653:1,241657:7,241658:1,241659:1,241678:-8,241679:-6,241683:1,241685:1,241689:1,241695:1,' ||
        '241697:-6,241698:1,241736:-4,241738:5,241739:-8,241756:5,241758:-2,241759:5,241769:7,241783:5,241785:-2,' ||
        '241786:7,241796:7,241835:1,241836:1,241839:1,241853:1,241856:1,241857:7,241859:1,241863:1,241865:1,241867:5,' ||
        '241869:1,241876:5,241893:1,241895:1,241896:1,241935:1,241937:3,241938:1,241953:1,241956:1,241957:7,241958:1,' ||
        '241965:1,241967:3,241968:1,241973:3,241976:3,241983:1,241985:1,241986:1,243156:5,243157:5,243158:-2,243165:17,' ||
        '243168:-10,243175:11,243178:7,243185:-2,243186:5,243187:7,243196:5,243198:-8,243516:3,243517:5,243518:3,' ||
        '243561:3,243567:7,243568:3,243569:3,243571:5,243576:7,243578:7,243579:-6,243581:3,243586:3,243587:7,243589:3,' ||
        '243596:3,243597:-4,243598:3,243615:3,243617:3,243618:3,243651:3,243657:3,243658:-2,243659:7,243671:3,243675:3,' ||
        '243678:3,243679:-6,243681:3,243685:-2,243687:3,243691:-4,243697:-4,243698:-8,243715:-4,243716:3,243718:3,' ||
        '243719:3,243751:7,243756:5,243758:-2,243759:7,243761:3,243768:3,243769:3,243781:3,243785:-2,243786:3,243791:3,' ||
        '243796:3,243815:-4,243816:5,243817:5,243851:7,243856:5,243857:5,243859:7,243867:7,243869:7,243871:5,243875:11,' ||
        '243876:7,243891:-4,243896:5,243916:5,243917:3,243918:3,243956:5,243957:3,243958:-2,243967:7,243971:3,243975:3,' ||
        '243976:7,243981:3,243985:-2,243986:5,245136:3,245137:1,245138:1,245139:1,245163:3,245167:3,245168:3,245169:-8,' ||
        '245173:1,245176:3,245178:1,245179:1,245183:1,245186:3,245187:1,245189:1,245193:1,245196:9,245197:1,245198:1,' ||
        '245316:3,245317:1,245318:1,245319:1,245361:3,245368:3,245371:1,245376:5,245378:1,245379:1,245381:1,245386:3,' ||
        '245387:1,245389:1,245391:1,245397:1,245398:1,245613:-2,245618:9,245631:-2,245638:5,245678:9,245681:-8,245683:-8,' ||
        '245687:-4,245689:-8,245698:9,245713:1,245716:3,245718:1,245719:1,245731:1,245736:9,245738:1,245739:1,245761:3,' ||
        '245763:-8,245768:3,245769:3,245781:1,245783:1,245786:3,245791:1,245793:1,245796:3,245813:1,245816:5,245817:1,' ||
        '245819:1,245831:1,245836:9,245837:1,245839:1,245861:-8,245863:-8,245867:-8,245869:-8,245871:1,245873:1,245876:5,' ||
        '245891:1,245893:1,245896:9,245913:1,245916:5,245917:1,245918:1,245931:1,245937:1,245938:1,245967:3,245968:3,' ||
        '245971:1,245973:1,245976:3,245981:1,245983:1,245986:3,246137:1,246138:1,246139:1,246153:9,246157:-8,246158:-2,' ||
        '246173:1,246175:9,246178:1,246179:1,246183:1,246185:-2,246187:1,246189:1,246193:1,246197:1,246198:1,246315:3,' ||
        '246317:1,246318:1,246319:1,246351:3,246358:-2,246359:-8,246371:1,246378:1,246379:1,246381:1,246385:-2,246387:1,' ||
        '246389:1,246391:1,246397:1,246398:1,246513:-2,246517:5,246518:5,246531:-2,246538:5,246539:5,246571:5,246578:7,' ||
        '246593:5,246597:-4,246598:-12,246713:1,246715:9,246718:1,246719:1,246731:1,246738:1,246739:1,246751:-8,' ||
        '246758:-2,246759:9,246781:1,246783:1,246785:-2,246791:1,246793:1,246813:1,246815:9,246817:1,246819:1,246831:1,' ||
        '246837:1,246839:1,246851:-8,246853:-8,246857:-8,246859:-8,246871:1,246873:1,246875:9,246891:1,246893:1,246913:1,' ||
        '246917:1,246918:1,246931:1,246937:1,246938:1,246953:-8,246957:3,246958:-2,246971:1,246973:1,246975:3,246981:1,' ||
        '246983:1,246985:-2,247135:11,247136:7,247153:5,247156:5,247158:-2,247163:7,247168:-12,247183:-12,247185:-2,' ||
        '247186:-10,247193:-8,247196:-4,247198:5,247316:3,247318:3,247319:3,247351:7,247356:1,247358:1,247359:1,247361:3,' ||
        '247365:1,247368:1,247381:3,247385:1,247386:1,247389:1,247391:3,247395:1,247398:1,247513:-2,247516:3,247518:3,' ||
        '247531:-2,247536:1,247538:1,247539:1,247561:3,247563:1,247568:1,247569:1,247581:3,247583:1,247586:1,247589:1,' ||
        '247593:1,247596:1,247598:1,247613:-2,247618:5,247631:-2,247635:1,247638:1,247651:7,247653:1,247658:1,247659:1,' ||
        '247681:5,247683:1,247685:1,247689:1,247695:1,247698:1,247813:-2,247815:3,247816:3,247831:-2,247835:1,247836:1,' ||
        '247839:1,247851:3,247853:1,247856:1,247859:1,247861:3,247863:1,247865:1,247869:1,247893:1,247895:1,247896:1,' ||
        '247913:-2,247916:3,247918:5,247931:-2,247935:1,247938:1,247953:1,247956:1,247958:1,247961:3,247965:1,247968:1,' ||
        '247981:5,247983:1,247985:1,247986:1,248135:9,248136:7,248137:7,248139:-6,248153:-8,248156:5,248157:9,248165:5,' ||
        '248167:7,248169:-6,248173:11,248175:-4,248176:5,248179:5,248193:-6,248196:-4,248197:5,248315:9,248316:5,' ||
        '248317:5,248319:7,248351:-4,248356:5,248359:9,248361:11,248365:5,248367:7,248371:5,248376:5,248379:5,248391:11,' ||
        '248395:-4,248397:5,248513:-2,248516:5,248517:5,248531:-2,248536:7,248539:13,248571:5,248576:5,248579:5,' ||
        '248593:-6,248596:9,248597:5,248613:-2,248615:9,248617:5,248619:7,248631:-2,248635:9,248637:7,248651:-4,' ||
        '248653:-8,248657:-4,248659:-8,248671:5,248673:11,248675:9,248679:5,248691:11,248695:9,248697:5,248713:-2,' ||
        '248715:3,248716:3,248719:7,248731:-2,248736:3,248739:-6,248751:3,248756:3,248759:-8,248761:3,248763:3,248765:3,' ||
        '248769:-6,248791:11,248793:-6,248795:-4,248796:-4,248913:-2,248916:3,248917:5,248931:-2,248935:3,248937:7,' ||
        '248953:3,248956:3,248957:-4,248961:3,248965:3,248967:7,248971:5,248973:11,248975:-4,248976:5,249136:3,249137:3,' ||
        '249138:3,249153:7,249156:5,249157:7,249158:-2,249163:3,249167:3,249168:3,249173:3,249175:-4,249176:3,249178:3,' ||
        '249183:3,249185:-2,249186:3,249187:3,249315:3,249316:7,249317:3,249318:3,249351:3,249356:5,249358:-2,249361:7,' ||
        '249368:-12,249371:3,249376:5,249378:3,249381:3,249385:-2,249386:5,249387:3,249513:-2,249516:7,249517:5,249518:5,' ||
        '249531:-2,249536:3,249538:3,249561:7,249563:3,249567:3,249568:3,249571:5,249576:3,249578:3,249581:7,249583:3,' ||
        '249586:3,249587:3,249613:-2,249615:3,249617:3,249618:3,249631:-2,249637:-4,249638:5,249651:3,249653:7,249657:3,' ||
        '249658:-2,249671:3,249675:3,249678:3,249681:3,249683:5,249685:-2,249687:3,249713:-2,249715:3,249716:3,249718:5,' ||
        '249731:-2,249736:3,249738:5,249751:3,249756:3,249758:-2,249761:3,249763:3,249765:3,249768:-12,249781:7,249783:5,' ||
        '249785:-2,249786:5,249813:-2,249815:3,249816:3,249817:5,249831:-2,249835:3,249836:3,249837:-4,249851:3,249853:3,' ||
        '249856:3,249857:7,249861:3,249863:3,249865:3,249871:5,249875:-4,249876:5,251346:1,251347:1,251348:1,251349:-10,' ||
        '251364:1,251367:1,251368:1,251374:1,251376:1,251378:1,251379:-8,251384:1,251386:1,251387:1,251389:7,251394:5,' ||
        '251397:-10,251436:1,251437:1,251438:1,251439:-6,251463:1,251467:1,251468:1,251469:7,251473:1,251476:1,251478:1,' ||
        '251479:-6,251483:1,251486:1,251487:1,251489:3,251493:-4,251497:-4,251498:3,251634:1,251637:1,251638:1,251643:1,' ||
        '251647:1,251648:1,251649:7,251673:1,251674:1,251678:1,251679:-6,251683:1,251684:1,251687:1,251689:7,251694:5,' ||
        '251697:-4,251734:1,251736:1,251738:1,251739:-8,251743:1,251746:1,251748:1,251749:7,251763:1,251764:1,251768:1,' ||
        '251769:7,251783:1,251784:1,251786:1,251793:-10,251794:5,251834:1,251836:1,251837:1,251839:-6,251843:1,251846:1,' ||
        '251847:1,251849:7,251863:1,251864:1,251867:1,251869:7,251873:1,251874:1,251876:1,251893:-4,251894:5,251934:5,' ||
        '251937:5,251938:15,251943:-14,251947:7,251948:-4,251964:5,251967:5,251968:-14,251973:5,251974:7,251976:15,' ||
        '251983:5,251984:7,254137:1,254138:1,254139:1,254163:-4,254167:-8,254168:3,254169:-6,254173:1,254178:1,254179:1,' ||
        '254183:1,254186:3,254187:1,254189:1,254193:1,254197:1,254198:1,254317:1,254318:1,254319:1,254361:5,254367:5,' ||
        '254371:1,254378:1,254379:1,254381:1,254386:5,254387:1,254389:1,254391:1,254397:1,254398:1,254613:-2,254618:-4,' ||
        '254619:-10,254631:-2,254637:5,254673:-10,254678:-4,254679:-4,254681:-8,254683:-8,254687:-4,254689:-4,254691:5,' ||
        '254697:-4,254713:1,254718:1,254719:1,254731:1,254738:1,254739:1,254761:-8,254763:-6,254768:3,254769:-4,254781:1,' ||
        '254783:1,254786:3,254791:1,254793:1,254813:1,254817:1,254819:1,254831:1,254837:1,254839:1,254861:-8,254863:-4,' ||
        '254867:-8,254869:-4,254871:1,254873:1,254876:5,254891:1,254893:1,254913:1,254917:1,254918:1,254931:1,254937:1,' ||
        '254938:1,254961:5,254967:5,254971:1,254973:1,254976:5,254981:1,254983:1,254986:5,257134:5,257138:3,257139:-10,' ||
        '257143:7,257146:1,257148:1,257149:1,257163:7,257164:1,257168:1,257169:1,257183:3,257184:1,257186:1,257189:1,' ||
        '257193:-8,257194:1,257196:1,257198:1,257314:7,257316:15,257318:-4,257319:-10,257341:7,257348:-4,257349:-14,' ||
        '257361:5,257364:5,257368:7,257381:-14,257384:15,257386:15,257389:7,257391:5,257394:5,257398:7,257413:-2,' ||
        '257416:1,257418:1,257419:1,257431:-2,257438:3,257439:-4,257461:1,257463:7,257468:1,257469:1,257481:1,257483:3,' ||
        '257486:1,257489:1,257491:1,257493:-6,257496:1,257498:1,257613:-2,257614:1,257618:1,257619:1,257631:-2,257634:5,' ||
        '257638:5,257641:1,257643:7,257648:1,257649:1,257681:1,257683:7,257684:1,257689:1,257691:1,257694:1,257698:1,' ||
        '257813:-2,257814:1,257816:1,257819:1,257831:-2,257834:3,257836:3,257839:-4,257841:1,257843:3,257846:1,257849:1,' ||
        '257861:1,257863:3,257864:1,257869:1,257891:1,257893:-6,257894:1,257896:1,257913:-2,257914:1,257916:1,257918:1,' ||
        '257931:-2,257934:3,257938:5,257941:1,257943:3,257946:1,257948:1,257961:1,257964:1,257968:1,257981:1,257983:7,' ||
        '257984:1,257986:1,271345:-6,271346:-10,271348:-8,271349:-8,271356:1,271358:1,271359:1,271365:1,271368:1,' ||
        '271384:5,271385:1,271386:1,271389:1,271394:5,271395:1,271398:1,271436:-8,271438:-8,271439:-4,271453:5,271458:-2,' ||
        '271459:11,271463:-4,271485:-2,271486:7,271493:-4,271496:7,271534:3,271536:1,271538:1,271539:1,271543:3,271548:3,' ||
        '271563:1,271568:1,271569:1,271583:1,271584:3,271586:1,271589:1,271593:1,271594:5,271596:1,271598:1,271634:5,' ||
        '271635:1,271638:1,271643:5,271653:1,271658:1,271659:1,271683:1,271684:5,271685:1,271689:1,271694:5,271695:1,' ||
        '271698:1,271834:5,271835:1,271836:1,271839:1,271843:5,271845:-4,271846:-10,271853:1,271856:1,271859:1,271863:1,' ||
        '271865:1,271869:1,271893:1,271894:5,271895:1,271896:1,271934:3,271935:1,271938:1,271943:3,271945:-4,271946:3,' ||
        '271948:3,271953:1,271956:1,271958:1,271964:3,271965:1,271968:1,271983:1,271984:3,271985:1,271986:1,273145:-10,' ||
        '273146:1,273148:1,273149:1,273158:-2,273164:1,273165:-6,273168:1,273169:1,273184:1,273185:-2,273186:1,273189:1,' ||
        '273194:1,273196:1,273198:1,273416:1,273418:1,273419:1,273451:9,273458:-2,273459:9,273461:1,273468:1,273469:1,' ||
        '273481:1,273485:-2,273486:1,273489:1,273491:1,273496:1,273498:1,273514:5,273516:5,273518:5,273541:5,273548:7,' ||
        '273561:5,273569:9,273581:9,273584:7,273586:7,273589:9,273594:5,273596:5,273598:5,273614:1,273615:3,273618:1,' ||
        '273619:1,273641:1,273648:1,273649:1,273651:3,273658:-2,273659:9,273681:1,273684:1,273685:-2,273689:1,273691:1,' ||
        '273694:1,273698:1,273814:1,273816:1,273819:1,273841:1,273845:-10,273846:1,273849:1,273851:9,273859:9,273861:1,' ||
        '273864:1,273865:-6,273869:1,273891:1,273894:1,273896:1,273914:1,273916:1,273918:1,273941:1,273945:3,273946:1,' ||
        '273948:1,273954:3,273958:-2,273961:1,273964:1,273965:-6,273968:1,273981:1,273984:1,273985:-2,273986:1,274135:11,' ||
        '274138:7,274153:5,274156:5,274158:-2,274163:-4,274168:-8,274169:-4,274183:11,274185:-2,274186:-12,274189:11,' ||
        '274193:-4,274198:5,274318:5,274319:11,274351:9,274356:1,274358:1,274359:1,274361:5,274365:1,274368:1,274381:5,' ||
        '274385:1,274386:1,274389:1,274391:7,274395:1,274398:1,274513:-2,274516:5,274518:3,274531:-2,274536:1,274538:1,' ||
        '274539:1,274563:1,274568:1,274569:1,274581:3,274583:1,274586:1,274589:1,274593:1,274596:1,274598:1,274613:-2,' ||
        '274615:-4,274618:3,274619:3,274631:-2,274635:1,274638:1,274651:-8,274653:1,274658:1,274659:1,274681:3,274683:1,' ||
        '274685:1,274689:1,274691:3,274695:1,274698:1,274813:-2,274815:-4,274819:11,274831:-2,274835:1,274836:1,274839:1,' ||
        '274851:-8,274853:1,274856:1,274859:1,274863:1,274865:1,274869:1,274891:7,274893:1,274895:1,274896:1,274913:-2,' ||
        '274916:5,274918:5,274931:-2,274935:1,274938:1,274953:1,274956:1,274958:1,274961:5,274965:1,274968:1,274981:5,' ||
        '274983:1,274985:1,274986:1,275134:3,275136:3,275138:3,275143:3,275146:1,275148:1,275149:1,275163:3,275164:1,' ||
        '275168:1,275169:1,275183:3,275184:1,275186:1,275189:1,275194:1,275196:1,275198:1,275314:9,275316:7,275318:7,' ||
        '275346:7,275348:9,275364:9,275368:5,275384:9,275386:9,275398:5,275413:-2,275416:1,275418:1,275419:1,275431:-2,' ||
        '275436:-10,275438:3,275439:3,275461:1,275463:-8,275468:1,275469:1,275481:1,275483:3,275486:1,275489:1,275491:1,' ||
        '275493:3,275496:1,275498:1,275613:-2,275614:1,275618:1,275619:1,275631:-2,275634:5,275638:3,275641:1,275648:1,' ||
        '275649:1,275681:1,275683:3,275684:1,275689:1,275691:1,275694:1,275698:1,275813:-2,275814:1,275816:1,275819:1,' ||
        '275831:-2,275834:5,275836:-10,275841:1,275843:-8,275846:1,275849:1,275861:1,275863:-8,275864:1,275869:1,' ||
        '275891:1,275894:1,275896:1,275913:-2,275914:1,275916:1,275918:1,275931:-2,275934:3,275938:3,275941:1,275943:3,' ||
        '275946:1,275948:1,275961:1,275964:1,275968:1,275981:1,275983:3,275984:1,275986:1,276134:11,276135:11,276138:7,' ||
        '276139:7,276145:9,276148:7,276153:5,276154:5,276158:-2,276183:5,276184:7,276185:-2,276189:5,276193:5,276194:5,' ||
        '276198:5,276314:3,276315:3,276318:3,276319:7,276341:3,276345:3,276348:3,276351:3,276354:3,276358:-2,276359:-4,' ||
        '276381:3,276384:3,276385:-2,276389:5,276391:-4,276398:5,276413:-2,276415:-4,276418:3,276419:3,276431:-2,' ||
        '276438:3,276439:3,276451:-8,276453:15,276458:-2,276459:-4,276481:3,276483:3,276485:-2,276489:3,276491:3,' ||
        '276493:3,276495:-4,276498:3,276513:-2,276514:5,276518:3,276531:-2,276538:3,276539:3,276543:15,276548:7,276581:3,' ||
        '276583:3,276584:7,276589:3,276593:3,276594:5,276598:3,276813:-2,276814:5,276815:-4,276819:7,276831:-2,276839:7,' ||
        '276845:9,276851:-8,276853:15,276854:5,276859:11,276891:-4,276893:5,276895:-4,276913:-2,276914:3,276918:3,' ||
        '276931:-2,276938:7,276941:3,276945:3,276948:3,276953:5,276954:3,276958:-2,276981:3,276983:5,276984:3,276985:-2,' ||
        '278134:1,278135:1,278136:1,278139:-6,278143:1,278145:1,278146:1,278149:5,278153:1,278154:1,278156:1,278163:1,' ||
        '278164:1,278165:1,278169:-6,278193:-4,278194:5,278196:-6,278314:1,278315:1,278316:1,278319:7,278341:1,278345:1,' ||
        '278346:1,278349:5,278351:1,278354:1,278356:1,278359:9,278361:1,278364:1,278365:1,278391:11,278394:5,278413:1,' ||
        '278415:1,278416:1,278419:7,278431:1,278435:1,278436:1,278439:-6,278451:1,278453:1,278459:-8,278461:1,278463:1,' ||
        '278469:-6,278491:11,278493:-4,278495:-4,278496:-6,278513:1,278514:1,278516:1,278531:1,278534:1,278536:1,' ||
        '278541:1,278543:1,278549:5,278561:1,278563:1,278593:-6,278594:5,278596:-12,278613:1,278614:1,278615:1,278619:7,' ||
        '278631:1,278634:1,278635:1,278641:1,278643:1,278649:5,278651:1,278653:1,278659:-8,278691:11,278694:5,278695:-4,' ||
        '278913:-2,278914:5,278916:5,278931:-2,278934:7,278935:5,278941:11,278943:11,278945:-4,278946:7,278953:5,' ||
        '278954:-4,278956:-8,278961:11,278964:7,278965:-4,279134:1,279135:1,279136:1,279138:3,279143:1,279145:1,279146:1,' ||
        '279148:3,279153:1,279154:1,279156:1,279158:-2,279163:1,279164:1,279165:1,279168:3,279183:3,279184:3,279185:-2,' ||
        '279186:3,279314:1,279315:1,279316:1,279318:3,279341:1,279345:1,279346:1,279348:3,279351:1,279354:1,279356:1,' ||
        '279358:-2,279361:1,279364:1,279365:1,279368:5,279381:3,279384:3,279385:-2,279386:5,279413:1,279415:1,279416:1,' ||
        '279418:5,279431:1,279435:1,279436:1,279438:5,279451:1,279453:1,279458:-2,279461:1,279463:1,279468:5,279483:5,' ||
        '279485:-2,279486:5,279513:1,279514:1,279516:1,279518:5,279531:1,279534:1,279536:1,279538:3,279541:1,279543:1,' ||
        '279548:3,279561:1,279563:1,279568:3,279583:3,279584:3,279586:3,279613:1,279614:1,279615:1,279618:3,279631:1,' ||
        '279634:1,279635:1,279638:5,279641:1,279643:1,279648:3,279651:1,279653:1,279658:-2,279681:3,279683:5,279684:3,' ||
        '279685:-2,279813:-2,279816:-12,279831:-2,279834:-8,279845:-4,279851:11,279853:11,279861:-8,279864:-4,279865:-4,' ||
        '281345:-4,281346:-10,281349:-10,281359:5,281365:-10,281367:5,281374:5,281376:5,281379:5,281394:5,281395:11,' ||
        '281397:5,281435:3,281436:-8,281437:-4,281439:-4,281453:3,281457:7,281459:3,281467:5,281469:7,281475:-4,281476:5,' ||
        '281479:5,281493:-6,281495:3,281496:7,281497:5,281534:3,281536:3,281539:-4,281543:3,281547:3,281549:7,281563:3,' ||
        '281567:3,281569:7,281574:3,281576:3,281579:5,281593:-6,281594:5,281596:7,281597:5,281634:5,281637:-4,281643:5,' ||
        '281647:7,281649:7,281653:7,281657:7,281659:5,281674:5,281675:-4,281679:5,281694:5,281695:11,281697:5,281734:5,' ||
        '281736:-8,281743:5,281745:-4,281746:-10,281749:7,281756:3,281759:3,281765:3,281769:7,281794:5,281795:3,281796:7,' ||
        '281934:3,281937:3,281943:3,281945:-4,281946:3,281947:3,281953:7,281957:7,281964:3,281965:-10,281967:3,281973:3,' ||
        '281974:3,281975:-4,281976:3,284135:3,284137:7,284153:3,284156:3,284157:-4,284163:-6,284165:3,284169:-4,' ||
        '284173:11,284175:-4,284179:5,284196:-14,284197:5,284315:-4,284317:5,284319:11,284351:9,284356:5,284359:-4,' ||
        '284361:5,284365:9,284367:5,284371:5,284376:5,284379:5,284391:7,284395:9,284397:5,284513:-2,284516:5,284517:3,' ||
        '284531:-2,284539:3,284563:-6,284569:-4,284571:3,284576:5,284579:3,284593:3,284596:-14,284597:3,284613:-2,' ||
        '284615:-4,284617:3,284619:3,284631:-2,284635:9,284637:3,284651:-8,284653:-8,284657:-4,284659:-4,284671:3,' ||
        '284673:3,284675:-4,284679:3,284691:3,284695:9,284697:3,284713:-2,284715:-4,284719:11,284731:-2,284751:-8,' ||
        '284756:3,284759:3,284763:-6,284765:3,284769:-6,284791:7,284795:3,284796:-14,284913:-2,284916:5,284917:5,' ||
        '284931:-2,284935:9,284937:7,284953:-8,284956:5,284957:9,284961:5,284965:9,284967:5,284971:5,284973:11,284975:-4,' ||
        '287134:1,287135:1,287136:1,287143:1,287145:1,287146:1,287149:5,287153:1,287154:1,287156:1,287163:1,287164:1,' ||
        '287165:1,287193:-8,287194:5,287196:-8,287314:1,287315:1,287316:1,287319:3,287341:1,287345:1,287346:1,287349:3,' ||
        '287351:1,287354:1,287356:1,287359:7,287361:1,287364:1,287365:1,287391:3,287394:3,287413:1,287415:1,287416:1,' ||
        '287431:1,287435:1,287436:1,287439:-6,287451:1,287453:1,287459:3,287461:1,287463:1,287493:-6,287495:3,287496:-8,' ||
        '287513:1,287514:1,287516:1,287531:1,287534:1,287536:1,287539:-6,287541:1,287543:1,287549:3,287561:1,287563:1,' ||
        '287569:3,287593:-6,287594:3,287596:3,287613:1,287614:1,287615:1,287631:1,287634:1,287635:1,287641:1,287643:1,' ||
        '287649:5,287651:1,287653:1,287659:7,287694:5,287913:-2,287914:5,287916:5,287931:-2,287934:5,287935:11,' ||
        '287943:-12,287945:-4,287946:-10,287953:5,287961:5,287965:-10,512346:-2,512348:-12,512349:-4,512364:-2,512368:5,' ||
        '512374:15,512376:-8,512379:-4,512384:-8,512386:-12,512387:-4,512389:-4,512394:-8,512436:-6,512437:-2,512439:-4,' ||
        '512463:-6,512467:1,512468:1,512469:1,512473:-2,512476:1,512478:1,512479:1,512483:13,512486:1,512487:1,512489:1,' ||
        '512493:-6,512496:1,512497:1,512498:1,512634:-8,512637:-2,512638:5,512643:11,512647:1,512648:1,512649:1,' ||
        '512673:-2,512674:1,512678:1,512679:1,512684:1,512687:1,512689:1,512694:1,512697:1,512698:1,512734:15,512736:-6,' ||
        '512739:-4,512743:11,512746:1,512748:1,512749:1,512763:-6,512764:1,512768:1,512769:1,512783:5,512784:1,512786:1,' ||
        '512793:-6,512794:1,512796:1,512834:-6,512836:-6,512837:-2,512839:-4,512843:-8,512846:1,512847:1,512849:1,' ||
        '512863:-6,512864:1,512867:1,512869:1,512873:-2,512874:1,512876:1,512893:-6,512894:1,512896:1,512934:-8,' ||
        '512937:-2,512938:5,512943:11,512946:1,512947:1,512948:1,512964:1,512967:1,512968:1,512973:-2,512974:1,512976:1,' ||
        '512983:5,512984:1,512986:1,513246:-2,513248:7,513249:-4,513264:-2,513267:-8,513268:-8,513269:-4,513276:-12,' ||
        '513278:7,513279:-4,513289:-4,513294:-8,513297:-4,513298:-8,513426:-12,513428:-2,513429:-4,513467:1,513468:1,' ||
        '513469:1,513472:5,513476:1,513478:1,513479:1,513482:-2,513486:1,513487:1,513489:1,513492:5,513496:1,513497:1,' ||
        '513498:1,513624:3,513627:3,513628:-2,513629:-4,513642:3,513647:1,513648:1,513649:1,513672:3,513674:1,513678:1,' ||
        '513679:1,513682:-2,513684:1,513687:1,513689:1,513692:5,513694:1,513697:1,513698:1,513724:15,513726:15,513728:-2,' ||
        '513729:-4,513742:5,513746:1,513748:1,513749:1,513762:13,513764:1,513768:1,513769:1,513782:-2,513784:1,513786:1,' ||
        '513792:5,513794:1,513796:1,513824:15,513829:-4,513842:5,513846:1,513847:1,513849:1,513862:-12,513864:1,513867:1,' ||
        '513869:1,513872:5,513874:1,513876:1,513892:5,513894:1,513896:1,513924:3,513927:3,513928:-2,513942:3,513946:1,' ||
        '513947:1,513948:1,513964:1,513967:1,513968:1,513972:3,513974:1,513976:1,513982:-2,513984:1,513986:1,516237:-2,' ||
        '516238:-8,516239:-4,516243:11,516247:13,516248:7,516249:-4,516273:-2,516274:5,516278:7,516279:-4,516283:11,' ||
        '516284:5,516289:-4,516293:9,516297:-4,516298:-6,516324:3,516327:3,516328:-2,516329:-4,516342:3,516347:3,' ||
        '516348:3,516349:-4,516372:3,516374:3,516378:3,516379:-4,516382:-2,516384:3,516387:3,516389:-4,516392:15,' ||
        '516397:-4,516398:-6,516423:11,516428:-2,516429:-4,516432:13,516437:-2,516438:-8,516439:-4,516472:5,516473:-2,' ||
        '516478:7,516479:-4,516482:-2,516483:-6,516489:-4,516492:-6,516493:-6,516497:-6,516498:-6,516723:11,516724:7,' ||
        '516728:-2,516729:-4,516732:13,516734:9,516738:-8,516739:-4,516742:7,516748:7,516749:-4,516782:-2,516783:11,' ||
        '516784:5,516792:-8,516793:11,516794:5,516823:11,516824:7,516829:-4,516832:-12,516837:-2,516839:-4,516842:7,' ||
        '516843:13,516849:-4,516872:5,516873:-2,516874:5,516892:-8,516893:11,516894:5,516923:11,516924:3,516927:3,' ||
        '516928:-2,516932:13,516937:-2,516938:-8,516942:3,516947:3,516948:3,516972:3,516973:-2,516974:3,516982:-2,' ||
        '516983:11,516984:3,521346:-2,521348:-4,521349:-10,521364:-2,521367:5,521368:7,521376:-8,521378:-4,521379:-8,' ||
        '521389:7,521394:5,521398:7,521436:-8,521437:-2,521438:3,521439:-6,521467:1,521468:1,521469:1,521473:-2,521476:1,' ||
        '521478:1,521479:1,521483:3,521486:1,521487:1,521489:1,521493:-6,521496:1,521497:1,521498:1,521634:5,521637:-2,' ||
        '521638:5,521647:1,521648:1,521649:1,521673:-2,521674:1,521678:1,521679:1,521683:5,521684:1,521687:1,521689:1,' ||
        '521694:1,521697:1,521698:1,521734:5,521736:-8,521738:3,521739:-8,521746:1,521748:1,521749:1,521764:1,521768:1,' ||
        '521769:1,521783:3,521784:1,521786:1,521794:1,521796:1,521834:5,521836:-8,521837:-2,521839:-6,521846:1,521847:1,' ||
        '521849:1,521864:1,521867:1,521869:1,521873:-2,521874:1,521876:1,521893:-6,521894:1,521896:1,521934:5,521937:-2,' ||
        '521938:5,521943:-14,521946:1,521947:1,521948:1,521964:1,521967:1,521968:1,521973:-2,521974:1,521976:1,521983:5,' ||
        '521984:1,521986:1,524136:-14,524137:-2,524138:3,524163:-6,524167:13,524168:3,524169:-6,524173:-2,524178:-4,' ||
        '524179:-6,524183:3,524186:3,524187:-6,524189:3,524197:-6,524198:3,524317:11,524318:-4,524319:-2,524361:5,' ||
        '524367:5,524368:7,524371:7,524378:-4,524379:-6,524381:7,524386:5,524387:-6,524391:-2,524397:-6,524398:7,' ||
        '524618:-4,524619:-2,524631:5,524637:-2,524638:5,524671:-6,524673:-2,524678:-4,524679:-6,524681:-6,524687:-6,' ||
        '524691:-2,524697:-6,524698:7,524718:-4,524719:-2,524731:5,524736:-14,524738:3,524763:-4,524768:3,524769:-6,' ||
        '524781:11,524783:3,524786:3,524791:-2,524817:11,524819:-2,524831:5,524837:-2,524863:-4,524869:-6,524871:11,' ||
        '524873:-2,524876:5,524891:-2,524913:11,524917:11,524918:-4,524931:5,524937:-2,524938:5,524961:5,524967:5,' ||
        '524968:7,524971:11,524973:-2,524976:5,524981:11,524986:5,527134:5,527136:7,527138:3,527143:7,527146:-2,' ||
        '527148:-4,527163:7,527164:-2,527168:3,527183:3,527186:3,527189:3,527194:5,527196:-8,527198:3,527314:5,527316:5,' ||
        '527318:-4,527319:-2,527341:7,527346:-2,527348:-4,527361:5,527364:-2,527368:5,527381:-14,527389:7,527391:-2,' ||
        '527394:5,527398:5,527413:5,527416:5,527418:-4,527419:-2,527431:5,527436:7,527438:3,527439:-6,527461:5,527463:7,' ||
        '527468:3,527483:3,527486:3,527489:3,527491:-2,527493:-4,527496:-8,527498:3,527613:5,527614:5,527618:-4,' ||
        '527619:-2,527631:5,527634:5,527638:7,527641:7,527643:7,527648:-4,527683:7,527684:-12,527689:7,527691:-2,' ||
        '527694:5,527698:5,527813:3,527814:3,527816:3,527819:-2,527831:3,527834:3,527836:3,527839:-6,527841:3,527843:3,' ||
        '527846:-2,527861:3,527863:3,527864:-2,527891:-2,527893:-4,527894:5,527896:-8,527913:3,527914:3,527916:3,' ||
        '527918:-4,527931:3,527934:3,527938:7,527941:3,527943:3,527946:-2,527948:-4,527961:3,527964:-2,527968:5,527983:7', ',')) x;

create or replace function public.tri_win(q integer[]) returns boolean
language sql immutable set search_path to '' as $$
    select coalesce(cardinality(q), 0) = 3 and exists (
        select 1 from (values (0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)) l(a, b, c)
         where l.a = any(q) and l.b = any(q) and l.c = any(q)) $$;

-- the book's key of a position (me to move): the smallest over the 8 symmetries of the two lists written as digits
create or replace function public.tri_key(me integer[], op integer[]) returns integer
language plpgsql immutable set search_path to '' as $$
declare perms integer[] := array[0,1,2,3,4,5,6,7,8, 6,3,0,7,4,1,8,5,2, 8,7,6,5,4,3,2,1,0, 2,5,8,1,4,7,0,3,6,
                                 2,1,0,5,4,3,8,7,6, 0,3,6,1,4,7,2,5,8, 6,7,8,3,4,5,0,1,2, 8,5,2,7,4,1,6,3,0];
        best integer; k integer; a integer; b integer; c integer;
begin
    for t in 0..7 loop
        a := 0; b := 0;
        foreach c in array coalesce(me, '{}') loop a := a * 10 + perms[t * 9 + c + 1] + 1; end loop;
        foreach c in array coalesce(op, '{}') loop b := b * 10 + perms[t * 9 + c + 1] + 1; end loop;
        k := a * 1000 + b;
        if best is null or k < best then best := k; end if;
    end loop;
    return best;
end $$;

-- won (> 0: the side to move wins in that many moves), lost (< 0) or a draw (0)
create or replace function public.tri_val(me integer[], op integer[]) returns integer
language sql stable security definer set search_path to '' as $$
    select coalesce((select v from public.rb_tri_book where k = public.tri_key(me, op)), 0) $$;

create or replace function public.tri_add(q integer[], m integer) returns integer[]
language sql immutable set search_path to '' as $$
    select case when coalesce(cardinality(q), 0) >= 3 then q[2:3] || m else coalesce(q, '{}') || m end $$;

create or replace function public.tri_q(b jsonb, s integer) returns integer[]
language sql immutable set search_path to '' as $$
    select coalesce(array(select (x #>> '{}')::int from jsonb_array_elements(b -> 'q' -> (s - 1)) with ordinality e(x, o)
                          order by o), '{}') $$;

create or replace function public.tri_play(b jsonb, s integer, m integer) returns jsonb
language plpgsql immutable set search_path to '' as $$
declare me integer[] := public.tri_q(b, s); op integer[] := public.tri_q(b, 3 - s);
begin
    if m is null or m < 0 or m > 8 or m = any(me) or m = any(op) then return null; end if;
    return jsonb_set(b, array['q', (s - 1)::text], to_jsonb(public.tri_add(me, m)));
end $$;

create or replace function public.tri_new() returns jsonb
language sql immutable set search_path to '' as $$
    select jsonb_build_object('q', jsonb_build_array('[]'::jsonb, '[]'::jsonb)) $$;

-- the bot's move for side s
create or replace function public.tri_bot(b jsonb, s integer, level text) returns integer
language plpgsql stable security definer set search_path to '' as $$
declare me integer[] := public.tri_q(b, s); op integer[] := public.tri_q(b, 3 - s); nm integer[]; cv integer;
        sc integer; best integer; pick integer; nbest integer := 0; wins integer[] := '{}'; safe integer[] := '{}';
        allm integer[] := '{}'; scores integer[] := array_fill(0, array[9]); r float8 := public.rb_rand();
begin
    for m in 0..8 loop
        continue when m = any(me) or m = any(op);
        allm := allm || m;
        nm := public.tri_add(me, m);
        if public.tri_win(nm) then
            wins := wins || m; sc := 2000;
        else
            cv := public.tri_val(op, nm);                             -- the other side to move after it
            sc := case when cv < 0 then 1000 + cv when cv > 0 then -1000 + cv else 0 end;
            if cv <> 1 then safe := safe || m; end if;                -- it does not hand them a win at once
        end if;
        scores[m + 1] := sc;
        if best is null or sc > best then best := sc; pick := m; nbest := 1;
        elsif sc = best then nbest := nbest + 1; if public.rb_rand() * nbest < 1 then pick := m; end if; end if;
    end loop;
    if cardinality(allm) = 0 then return null; end if;
    if level = 'insane' then return pick; end if;
    if level = 'hard' then
        if cardinality(wins) > 0 or r >= 0.14 then return pick; end if;
        if cardinality(safe) > 0 then return safe[1 + floor(public.rb_rand() * cardinality(safe))::int]; end if;
        return pick;
    end if;
    if level = 'medium' then
        if cardinality(wins) > 0 then return wins[1]; end if;
        if r < 0.3 then return pick; end if;
        if cardinality(safe) > 0 and public.rb_rand() < 0.85 then
            return safe[1 + floor(public.rb_rand() * cardinality(safe))::int];
        end if;
        return allm[1 + floor(public.rb_rand() * cardinality(allm))::int];
    end if;
    if cardinality(wins) > 0 and r < 0.55 then return wins[1]; end if;   -- easy
    if cardinality(safe) > 0 and public.rb_rand() < 0.4 then
        return safe[1 + floor(public.rb_rand() * cardinality(safe))::int];
    end if;
    return allm[1 + floor(public.rb_rand() * cardinality(allm))::int];
end $$;

-- ---------------------------------------------------------------- the Arena knows Mazelock and Trifade
create or replace function public.rb_bg_turn_secs(kind text) returns integer
language sql immutable set search_path to '' as $$
    select case kind when 'reversi' then 45 when 'ships' then 30 when 'maze' then 60 when 'tri' then 30 else 30 end $$;

create or replace function public.rb_skill_top(g text) returns integer
language sql immutable set search_path to '' as $$
    select case g when 'timing' then 120 when 'cups' then 150 when 'c4' then 600 when 'colour' then 90 when 'sfx' then 110
                  when 'reversi' then 700 when 'ships' then 450 when 'maze' then 2250 when 'tri' then 3000 else 1000000 end $$;

create or replace function public.rb_bg_new_board(kind text) returns jsonb
language sql volatile set search_path to '' as $$
    select case kind
        when 'c4' then jsonb_build_object('b', repeat('.', 42))
        when 'maze' then public.mz_new()
        when 'tri' then public.tri_new()
        when 'reversi' then jsonb_build_object('b', repeat('.', 27) || '21......12' || repeat('.', 27))
        else jsonb_build_object('h1', repeat('.', 100), 'h2', repeat('.', 100), 'left1', jsonb_build_array(5, 4, 3, 3, 2),
                                'left2', jsonb_build_array(5, 4, 3, 3, 2)) end $$;

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
                  when g.level is not null then case when g.level = 'insane' then 'Professional'
                                                     else initcap(g.level) end || ' bot' end,
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
    elsif g.kind = 'tri' then                                     -- 9.2: Trifade, the board is public
        out_ := out_ || jsonb_build_object('board', g.board);
    elsif g.kind = 'maze' then                                    -- 9.2: the whole board is public
        out_ := out_ || jsonb_build_object('board', g.board);
        if g.state = 'live' and side = g.turn then
            out_ := out_ || jsonb_build_object('legal', to_jsonb(public.mz_steps(g.board ->> 'h', g.board ->> 'v',
                (g.board -> 'p' ->> (side - 1))::int, (g.board -> 'p' ->> (2 - side))::int)));
        end if;
    else
        out_ := out_ || jsonb_build_object('board', g.board -> 'b');      -- 'a' and 'b' are the names
        if g.kind = 'reversi' and g.state = 'live' and side = g.turn then
            out_ := out_ || jsonb_build_object('legal', to_jsonb(public.rv_moves(g.board ->> 'b', side::text)));
        end if;
    end if;
    return out_;
end $$;

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
    elsif g.kind = 'maze' then                                    -- 9.2: the further the bot still had to go, the more
        base := case g.level when 'easy' then 25 when 'medium' then 80 when 'hard' then 220 when 'insane' then 1500 else 0 end;
        f := 1 + least(0.5, greatest(0, public.mz_dist(g.board ->> 'h', g.board ->> 'v', (g.board -> 'p' ->> 1)::int, 8)) / 16.0);
    elsif g.kind = 'tri' then                                     -- 9.2: a quicker win pays up to half more
        base := case g.level when 'easy' then 20 when 'medium' then 60 when 'hard' then 180 when 'insane' then 2000 else 0 end;
        f := 1 + least(0.5, greatest(0, 30 - jsonb_array_length(g.moves)) / 40.0);
    else
        base := 0;
    end if;
    if g.winner = 0 then return base / 4; end if;
    if g.winner <> 1 then return 0; end if;
    return round(base * f)::int;
end $$;

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
    elsif g.kind = 'tri' then                                     -- 9.2: Trifade
        nb := public.tri_play(g.board, s, m);
        if nb is null then return false; end if;
        update public.rb_bg set board = nb, turn = 3 - s, turn_at = now(),
               moves = moves || jsonb_build_array(jsonb_build_object('s', s, 'm', m, 'ms', think)) where id = gid;
        if public.tri_win(public.tri_q(nb, s)) then perform public.rb_bg_end(gid, s, 'three');
        elsif jsonb_array_length(g.moves) >= 299 then perform public.rb_bg_end(gid, 0, 'long'); end if;
    elsif g.kind = 'maze' then                                    -- 9.2: Mazelock
        nb := public.mz_play(g.board, s, m);
        if nb is null then return false; end if;
        update public.rb_bg set board = nb, turn = 3 - s, turn_at = now(),
               moves = moves || jsonb_build_array(jsonb_build_object('s', s, 'm', m, 'ms', think)) where id = gid;
        if (nb -> 'p' ->> 0)::int / 9 = 0 then perform public.rb_bg_end(gid, 1, 'home');
        elsif (nb -> 'p' ->> 1)::int / 9 = 8 then perform public.rb_bg_end(gid, 2, 'home');
        elsif jsonb_array_length(g.moves) >= 400 then perform public.rb_bg_end(gid, 0, 'long'); end if;
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
        elsif g.kind = 'maze' then
            m := public.mz_bot(g.board, 2, g.level);
        elsif g.kind = 'tri' then
            m := public.tri_bot(g.board, 2, g.level);
        else
            exit;
        end if;
        if m is null or not public.rb_bg_apply(gid, 2, m) then exit; end if;
    end loop;
end $$;

create or replace function public.rb_bg_bot(kind text, level text) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; g public.rb_bg%rowtype; sec jsonb := '{}'::jsonb; first_ integer := 1;
begin
    perform public.rb_rate(auth.uid(), 'arena', 20);
    perform public.rb_need_feature('minigames');
    p := public.rb_lock_me();
    if not (kind in ('ships', 'maze', 'tri') or kind = 'reversi' and coalesce(public.rb_cfg('reversi_on'), 0) = 1) or level not in ('easy', 'medium', 'hard', 'insane') then raise exception 'rb_bad_choice'; end if;
    perform public.rb_bg_tick_mine(p.id);
    update public.rb_bg set state = 'cancelled', why = 'left', done_at = now()      -- an old bot game you walked away from
     where a = p.id and b is null and rb_bg.level is not null and state = 'live';
    perform public.rb_bg_close_my_lobby(p.id);                                       -- 9.2: your duel nobody joined
    if public.rb_bg_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    if kind = 'ships' then
        sec := jsonb_build_object('f1', public.sh_fleet(), 'f2', public.sh_fleet());
        first_ := case when public.rb_rand() < 0.5 then 1 else 2 end;
    elsif kind in ('maze', 'tri') and level = 'insane' then
        first_ := 2;                                              -- 9.2: the Professional bot always starts
    end if;
    insert into public.rb_bg (kind, a, b, level, state, board, secret, turn, live_at, turn_at)
        values (kind, p.id, null, level, 'live', public.rb_bg_new_board(kind), sec, first_, now(), now()) returning * into g;
    perform public.rb_bg_bot_turns(g.id);
    select * into g from public.rb_bg where id = g.id;
    return public.rb_bg_json(g, p.id);
end $$;

create or replace function public.rb_bg_create(kind text, bet integer) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; g public.rb_bg%rowtype;
begin
    perform public.rb_rate(auth.uid(), 'duel', 10);
    perform public.rb_need_feature('arena');
    p := public.rb_lock_me();
    if not (kind in ('c4', 'ships', 'maze', 'tri') or kind = 'reversi' and coalesce(public.rb_cfg('reversi_on'), 0) = 1) then raise exception 'rb_bad_choice'; end if;
    perform public.rb_bg_tick_mine(p.id);
    perform public.rb_bg_close_my_lobby(p.id);                                       -- 9.2: a new duel replaces your empty one
    select * into p from public.profiles where id = p.id;
    if public.rb_bg_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    bet := coalesce(bet, 0);
    if bet <> 0 and (bet < 10 or bet % 10 <> 0 or bet > public.rb_golf_cap(p.coins)) then raise exception 'rb_bad_bet'; end if;
    if bet > 0 then perform public.rb_pay(p.id, -bet, 0, 'arena_bet', kind); end if;
    insert into public.rb_bg (kind, a, bet, state, board) values (kind, p.id, bet, 'open', public.rb_bg_new_board(kind))
        returning * into g;
    return public.rb_bg_json(g, p.id) || jsonb_build_object('coins', p.coins - bet);
end $$;

-- the fresh-bonus counters for every bot game, Mazelock and Trifade too
create or replace function public.rb_skill_state() returns jsonb
language plpgsql stable security definer set search_path to '' as $$
declare me uuid := auth.uid(); out_ jsonb := '{}'::jsonb; g text;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    foreach g in array array['timing', 'cups', 'c4', 'colour', 'sfx', 'reversi', 'ships', 'maze', 'tri'] loop
        out_ := out_ || jsonb_build_object(g, public.rb_skill_window(me, g));
    end loop;
    return out_ || jsonb_build_object('mult', public.rb_tier_mult(me),
        'held', (select coalesce(sum(coins), 0) from public.rb_held where owner = me and state = 'held'),
        'resets', greatest(0, ceil(extract(epoch from (((public.rb_today() + 1)::timestamp at time zone 'Europe/Paris') - now()))))::int);
end $$;

revoke all on function public.tri_win(integer[]), public.tri_key(integer[], integer[]), public.tri_val(integer[], integer[]),
              public.tri_add(integer[], integer), public.tri_q(jsonb, integer), public.tri_play(jsonb, integer, integer),
              public.tri_new(), public.tri_bot(jsonb, integer, text)
    from public, anon, authenticated;
revoke all on function public.mz_open(text, text, integer, integer), public.mz_step(integer, integer),
              public.mz_dist(text, text, integer, integer), public.mz_path(text, text, integer, integer),
              public.mz_steps(text, text, integer, integer), public.mz_fits(text, text, boolean, integer),
              public.mz_play(jsonb, integer, integer), public.mz_new(), public.mz_cut_walls(integer, integer[], integer),
              public.mz_score(text, text, integer, integer, integer, integer, integer, integer),
              public.mz_candidates(text, text, integer, integer, integer, integer, integer, integer),
              public.mz_search(text, text, integer, integer, integer, integer, integer, integer, integer, integer, timestamptz),
              public.mz_bot(jsonb, integer, text)
    from public, anon, authenticated;

commit;
