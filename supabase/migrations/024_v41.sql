-- Rubenium 4.1: Block Blast replaces 2048, Keno and Limbo are removed, apps older than 4.1 must update.
-- One transaction. Safe to run again. Nothing anyone owns is touched (2048 scores stay in the history).
-- Undo: 024_down.sql.
begin;

-- ================================================================ Block Blast
alter table public.rb_mg drop constraint if exists rb_mg_game_check;
alter table public.rb_mg add constraint rb_mg_game_check check (game in ('g2048', 'sweeper', 'blocks'));

-- The pieces (cells written y*5+x) and the draw bag, in the same order as the app. Three pieces are dealt from the
-- seed; when all three are placed, three more. A placement is 3 characters: the slot (0-2), then x and y in hex.
create or replace function public.rb_blocks_replay(n integer, seed bigint, moves text,
                                                   out score integer, out lines integer, out placed integer)
language plpgsql immutable set search_path = '' as $$
declare pieces text[] := array['0', '0,1', '0,5', '0,1,2', '0,5,10', '0,1,5', '0,1,6', '0,5,6', '1,5,6', '0,1,2,3', '0,5,10,15', '0,1,5,6', '0,5,10,11', '0,1,2,5', '0,1,6,11', '2,5,6,7', '1,6,11,10', '0,5,6,7', '0,1,5,10', '0,1,2,7', '0,1,2,6', '1,5,6,7', '0,5,10,6', '1,6,11,5', '1,2,5,6', '0,1,6,7', '0,5,6,11', '1,6,5,10', '0,1,2,3,4', '0,5,10,15,20', '0,5,10,11,12', '0,1,2,5,10', '0,1,2,7,12', '2,7,12,11,10', '0,1,2,5,6,7', '0,1,5,6,10,11', '0,1,2,5,6,7,10,11,12'];
        bag integer[] := '{0,0,1,1,1,2,2,2,3,3,3,4,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36}';
        s bigint := seed; b boolean[]; tray integer[]; i integer; k integer; x integer; y integer; pc integer[];
        c integer; cx integer; cy integer; ok boolean; whole boolean; rows integer[]; cols integer[]; r integer; q integer;
        streak integer := 0; got integer; cnt integer;
begin
    if n not between 5 and 16 then raise exception 'rb_bad_choice'; end if;
    b := array_fill(false, array[n * n]); score := 0; lines := 0; placed := 0;
    tray := '{}';
    for i in 1..3 loop s := public.rb_lcg(s); tray := tray || bag[(s % array_length(bag, 1)) + 1]; end loop;
    i := 1;
    while i + 2 <= least(length(coalesce(moves, '')), 6000) loop
        k := position(substr(moves, i, 1) in '012') - 1;
        x := position(lower(substr(moves, i + 1, 1)) in '0123456789abcdef') - 1;
        y := position(lower(substr(moves, i + 2, 1)) in '0123456789abcdef') - 1;
        i := i + 3;
        if k < 0 or x < 0 or y < 0 or tray[k + 1] < 0 then continue; end if;
        pc := string_to_array(pieces[tray[k + 1] + 1], ',')::integer[];
        ok := true;
        foreach c in array pc loop
            cx := x + c % 5; cy := y + c / 5;
            if cx >= n or cy >= n or b[cy * n + cx + 1] then ok := false; exit; end if;
        end loop;
        if not ok then continue; end if;                                     -- a move that does not fit is skipped
        foreach c in array pc loop b[(y + c / 5) * n + x + c % 5 + 1] := true; end loop;
        rows := '{}'; cols := '{}';
        for r in 0..n - 1 loop
            whole := true;
            for q in 0..n - 1 loop if not b[r * n + q + 1] then whole := false; exit; end if; end loop;
            if whole then rows := rows || r; end if;
            whole := true;
            for q in 0..n - 1 loop if not b[q * n + r + 1] then whole := false; exit; end if; end loop;
            if whole then cols := cols || r; end if;
        end loop;
        foreach r in array rows loop for q in 0..n - 1 loop b[r * n + q + 1] := false; end loop; end loop;
        foreach r in array cols loop for q in 0..n - 1 loop b[q * n + r + 1] := false; end loop; end loop;
        cnt := coalesce(array_length(rows, 1), 0) + coalesce(array_length(cols, 1), 0);
        got := array_length(pc, 1);
        if cnt > 0 then
            streak := streak + 1;
            got := got + 10 * cnt * cnt + case when streak > 1 then 20 * (streak - 1) else 0 end;
        else
            streak := 0;
        end if;
        score := score + got; lines := lines + cnt; placed := placed + 1;
        tray[k + 1] := -1;
        if tray[1] < 0 and tray[2] < 0 and tray[3] < 0 then
            tray := '{}';
            for q in 1..3 loop s := public.rb_lcg(s); tray := tray || bag[(s % array_length(bag, 1)) + 1]; end loop;
        end if;
    end loop;
end $$;
revoke all on function public.rb_blocks_replay(integer, bigint, text) from public, anon, authenticated;

-- modes: Block Blast 0 = Classic 8x8, 1 = Relaxed 10x10, 2 = Hard 7x7. Minesweeper 0 = Easy, 1 = Medium, 2 = Hard.
-- (2048 can no longer be started: Block Blast took its place.)
create or replace function public.rb_mg_start(game text, mode integer) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r public.rb_mg%rowtype; sd bigint;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('minigames');
    if game not in ('blocks', 'sweeper') or mode not between 0 and 2 then raise exception 'rb_bad_choice'; end if;
    update public.rb_mg set open = false, void = true where owner = p.id and open;      -- one game at a time
    sd := floor(public.rb_rand() * 2147483647)::bigint;
    insert into public.rb_mg (owner, game, mode, seed, state) values (p.id, game, mode,
        case when game = 'blocks' then sd else 0 end,
        case when game = 'sweeper' then jsonb_build_object('w', (array[9, 12, 16])[mode + 1], 'h', (array[9, 12, 14])[mode + 1],
                                                           'm', (array[10, 24, 40])[mode + 1], 'seed', sd) else '{}'::jsonb end)
        returning * into r;
    return json_build_object('id', r.id, 'game', game, 'mode', mode, 'seed', r.seed,
        'w', r.state -> 'w', 'h', r.state -> 'h', 'm', r.state -> 'm',
        'size', case when game = 'blocks' then (array[8, 10, 7])[mode + 1] end);
end $$;

-- Block Blast is over (or the player stops): every placement is played again here, the score paid
create or replace function public.rb_blocks_finish(round uuid, moves text) returns json
language plpgsql security definer set search_path = '' as $$
declare p public.profiles%rowtype; r public.rb_mg%rowtype; rep record; base integer; pay integer;
begin
    p := public.rb_lock_me();
    perform public.rb_need_feature('minigames');
    select * into r from public.rb_mg where id = round and owner = p.id and game = 'blocks' for update;
    if not found or not r.open then raise exception 'rb_round_gone'; end if;
    if length(coalesce(moves, '')) > 6000 then raise exception 'rb_bad_choice'; end if;
    rep := public.rb_blocks_replay((array[8, 10, 7])[r.mode + 1], r.seed, moves);
    base := least((array[300, 200, 360])[r.mode + 1], rep.score / (array[5, 8, 3])[r.mode + 1]);
    update public.rb_mg set open = false, score = rep.score, won = rep.score > 0,
           secs = extract(epoch from now() - at), done_at = now(),
           state = jsonb_build_object('lines', rep.lines, 'placed', rep.placed)
     where id = r.id returning * into r;
    pay := public.rb_mg_pay(r, base);
    update public.rb_mg set paid = pay where id = r.id;
    return json_build_object('score', rep.score, 'lines', rep.lines, 'paid', pay, 'coins', p.coins + pay);
end $$;
revoke all on function public.rb_blocks_finish(uuid, text) from public, anon;
grant execute on function public.rb_blocks_finish(uuid, text) to authenticated;

-- leaderboards: Block Blast (and the old 2048) by score, Minesweeper by fastest clear, per mode
create or replace function public.rb_mg_board(game text, mode integer, friends boolean) returns json
language plpgsql stable security definer set search_path = '' as $$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    return (with best as (
                select distinct on (g.owner) g.owner, g.score, g.secs, g.at from public.rb_mg g
                 where g.game = rb_mg_board.game and g.mode = rb_mg_board.mode and not g.open and not g.void
                   and coalesce(g.score, 0) > 0 and (g.game in ('g2048', 'blocks') or g.won)
                 order by g.owner, g.score desc, g.at),
            ranked as (select b.*, p.username, rank() over (order by b.score desc) rk from best b
                        join public.profiles p on p.id = b.owner
                       where not p.banned and (not coalesce(friends, false) or b.owner = me or public.rb_is_friend(me, b.owner)))
        select json_build_object(
            'top', coalesce((select json_agg(json_build_object('rank', rk, 'name', username, 'value', score, 'secs', round(secs, 1),
                                                               'me', owner = me) order by rk, username)
                               from (select * from ranked order by rk limit 50) t), '[]'::json),
            'me', (select json_build_object('rank', rk, 'value', score, 'secs', round(secs, 1)) from ranked where owner = me)));
end $$;

-- XP: Block Blast counts as a minigame (Keno and Limbo stay in the list for rounds played before 4.1)
create or replace function public.rb_rounds_xp() returns trigger
language plpgsql security definer set search_path = '' as $$
declare amt integer := 0; src text;
begin
    if new.open then return new; end if;
    if tg_op = 'UPDATE' and not old.open then return new; end if;               -- counted once, when it ends
    if coalesce((new.secret ->> 'void')::boolean, false) then return new; end if;
    if new.game in ('blackjack', 'mines', 'rocket', 'timing', 'hilo', 'tower', 'roulette', 'dice', 'plinko', 'keno', 'limbo') then
        if new.bet < 10 then return new; end if;
        src := 'casino'; amt := least(25, 3 + new.bet / 40);
    elsif new.game in ('mini', 'park', 'memory', 'tap', 'g2048', 'sweeper', 'blocks') then
        if coalesce(new.paid, 0) <= 0 then return new; end if;              -- a game thrown away gives nothing
        src := 'minigames'; amt := least(45, 10 + new.paid / 6);
    elsif new.game like 'case:%' then
        src := 'cases'; amt := 8;
    elsif new.game in ('spin', 'scratch') then
        src := 'wheel'; amt := 15;
    else
        return new;
    end if;
    perform public.rb_xp_add(new.owner, amt, src, new.game, true);
    return new;
end $$;

-- ================================================================ Keno, Limbo and 2048 can no longer be played
revoke execute on function public.rb_keno(integer, integer[], text) from public, anon, authenticated;
revoke execute on function public.rb_limbo(integer, numeric, text) from public, anon, authenticated;
revoke execute on function public.rb_2048_finish(uuid, text) from public, anon, authenticated;
update public.rb_mg set open = false, void = true where game = 'g2048' and open;

-- ================================================================ apps older than 4.1 must update
insert into public.rb_config (key, value) values ('min_build', 2026111812)
    on conflict (key) do update set value = greatest(public.rb_config.value, excluded.value);

commit;
