-- 9.1 (080): the Arena (Reversi and Battleships against bots, Connect 4 / Reversi / Battleships duels), admins
-- through a lockdown, held pay, leaderboards with every game, and the admin replays.
-- needs_live_snapshot
begin;
do $$
declare pa uuid := t.player('Alice', 5000, 0); pb uuid := t.player('Bob', 5000, 0); boss uuid := t.player('Boss', 0, 0);
        r jsonb; err text; gid uuid; m int; guard int; side int; i int; c0 bigint; c1 bigint;
begin
    -- the rules engines
    assert public.c4_drop(repeat('.', 42), 3) = 3 and public.c4_drop('...1' || repeat('.', 38), 3) = 10, 'c4 drop';
    assert public.c4_wins('1111' || repeat('.', 38), 0), 'c4 four in a row';
    assert public.c4_wins(overlay(overlay(overlay(overlay(repeat('.', 42) placing '2' from 1 for 1) placing '2' from 8 for 1)
                          placing '2' from 15 for 1) placing '2' from 22 for 1), 21), 'c4 four in a column';
    r := public.rb_bg_new_board('reversi');
    assert public.rv_moves(r ->> 'b', '1') = array[19, 26, 37, 44], 'reversi opening moves: ' || public.rv_moves(r ->> 'b', '1')::text;
    assert public.rv_count(public.rv_play(r ->> 'b', 19, '1'), '1') = 4, 'a move flips';
    assert public.rv_play(r ->> 'b', 0, '1') is null, 'an illegal move';
    r := public.sh_fleet();
    assert jsonb_array_length(r) = 5 and (select count(distinct (v #>> '{}')::int) from jsonb_array_elements(r) s,
                                          jsonb_array_elements(s) v) = 17, 'a fleet of 17 cells, no overlap';

    -- Reversi against the Insane bot, played to the end (first legal move each time)
    perform t.act(pa);
    r := public.rb_bg_bot('reversi', 'insane');
    gid := (r ->> 'id')::uuid;
    guard := 0;
    while r ->> 'state' = 'live' and guard < 80 loop
        guard := guard + 1;
        m := (r -> 'legal' ->> 0)::int;
        r := public.rb_bg_move(gid, m, (r ->> 'n')::int);
    end loop;
    reset role;
    assert r ->> 'state' = 'done' and (r ->> 'winner') is not null, 'reversi ends: ' || r::text;
    assert exists (select 1 from public.rb_rounds where owner = pa and game = 'reversi' and secret ->> 'bg' = gid::text), 'a round';
    assert (select jsonb_array_length(moves) from public.rb_bg where id = gid) > 30, 'every move kept';

    -- Battleships against the Easy bot: firing at every cell in turn always ends it
    perform t.act(pa);
    r := public.rb_bg_bot('ships', 'easy');
    gid := (r ->> 'id')::uuid;
    assert r -> 'their' is null and r -> 'fleet' is not null, 'you see only your own fleet';
    err := t.try(format('select public.rb_bg_move(%L, 0, 0)', gid));
    reset role;
    i := 0; guard := 0;
    perform t.act(pa);
    r := public.rb_bg_state(gid);
    while r ->> 'state' = 'live' and guard < 200 loop
        guard := guard + 1;
        if (r ->> 'turn')::int <> 1 then exit; end if;
        i := position('.' in r ->> 'shots') - 1;
        r := public.rb_bg_move(gid, i, (r ->> 'n')::int);
    end loop;
    reset role;
    assert r ->> 'state' = 'done', 'battleships ends: ' || left(r::text, 300);
    assert r -> 'their' is not null, 'their fleet is shown at the end';
    if (r ->> 'winner')::int = 1 then
        assert (r ->> 'paid')::int > 0, 'a win pays: ' || r::text;
    end if;

    -- a Connect 4 duel for 100: Alice wins the pot less 5%
    update public.profiles set coins = 5000 where id in (pa, pb);
    perform t.act(pa);
    r := public.rb_bg_create('c4', 100);
    gid := (r ->> 'id')::uuid;
    reset role;
    assert t.coins(pa) = 4900, 'the bet is held';
    perform t.act(pb);
    r := public.rb_bg_join(gid);
    reset role;
    assert r ->> 'state' = 'live' and t.coins(pb) = 4900, 'joined';
    side := (r ->> 'turn')::int;
    -- whoever starts, Alice plays column 0 and Bob columns 6 and 5 in turn: Alice gets four first
    guard := 0; i := 0;
    while guard < 20 loop
        guard := guard + 1;
        select * into r from public.rb_bg_json((select g from public.rb_bg g where g.id = gid), pa);
        exit when r ->> 'state' <> 'live';
        if (r ->> 'turn')::int = 1 then
            perform t.act(pa); r := public.rb_bg_move(gid, 0, (r ->> 'n')::int); reset role;
        else
            perform t.act(pb); r := public.rb_bg_move(gid, 6 - i % 2, (r ->> 'n')::int); reset role; i := i + 1;
        end if;
    end loop;
    assert (select state = 'done' and winner = 1 from public.rb_bg where id = gid), 'Alice won the duel';
    assert t.coins(pa) = 5090 and t.coins(pb) = 4900, 'the pot less 5%: ' || t.coins(pa) || ' ' || t.coins(pb);

    -- time runs out: the side to play loses
    perform t.act(pa);
    r := public.rb_bg_create('reversi', 0);
    reset role;
    gid := (r ->> 'id')::uuid;
    perform t.act(pb);
    r := public.rb_bg_join(gid);
    reset role;
    side := (r ->> 'turn')::int;
    update public.rb_bg set turn_at = now() - interval '5 minutes' where id = gid;
    perform public.rb_bg_tick(gid);
    assert (select state = 'done' and winner = 3 - side and why = 'time' from public.rb_bg where id = gid), 'time';

    -- the lockdown: players are stopped, the admin plays on; an open duel is given back
    update public.profiles set admin = true where id = boss;
    perform t.act(pb);
    r := public.rb_bg_create('ships', 50);
    reset role;
    c0 := t.coins(pb);
    update public.rb_config set value = 1 where key = 'lockdown';
    perform public.rb_bg_cleanup('all');
    assert t.coins(pb) = c0 + 50, 'the bet came back';
    perform t.act(pa);
    err := t.try('select public.rb_bg_bot(''ships'', ''easy'')');
    reset role;
    assert err like '%rb_lockdown%', 'a player is stopped: ' || err;
    perform t.act(boss);
    err := t.try('select public.rb_bg_bot(''ships'', ''easy'')');
    reset role;
    assert err = '', 'the admin plays on: ' || err;
    update public.rb_config set value = 0 where key = 'lockdown';

    -- leaderboards with the new games, and the profile numbers
    perform t.act(pa);
    r := public.rb_leaders('a:c4', false)::jsonb;
    assert (r -> 'top' -> 0 ->> 'name') = 'Alice', 'the duel board: ' || r::text;
    r := public.rb_leaders('reversi', false)::jsonb;
    r := public.rb_leaders('horses', false)::jsonb;
    reset role;
    assert (public.rb_stats_91(pa) ->> 'arena')::int >= 1, 'profile: arena wins';

    -- the admin replays: every game, with the fleets the players never saw
    perform t.act(boss);
    err := t.try('select public.rb_admin_replays(''all'', null, false, 50)');
    reset role;
    if err like '%rb_admin_step%' then
        insert into public.rb_admin_step (owner, ok_until, ok_session) values (boss, now() + interval '1 hour', '')
            on conflict do nothing;
    end if;
    perform t.act(boss);
    err := t.try('select public.rb_admin_replays(''all'', null, false, 50)');
    assert err = '', 'replays: ' || err;
    if err = '' then
        r := public.rb_admin_replays('arena', 'Alice', false, 50);
        assert jsonb_array_length(r) >= 3, 'Alice''s arena games: ' || left(r::text, 400);
        reset role;
        gid := (select id from public.rb_bg where kind = 'ships' and a = pa order by at limit 1);
        perform t.act(boss);
        r := public.rb_admin_replay('arena', gid::text);
        assert r -> 'secret' -> 'f1' is not null, 'the fleets';
    end if;
    reset role;
    perform t.act(pa);
    err := t.try('select public.rb_admin_replays(''all'', null, false, 50)');
    reset role;
    assert err like '%rb_not_admin%', 'players cannot: ' || err;

    -- a held pay: the admin pays it and trusts the player
    insert into public.rb_held (owner, game, coins, why) values (pa, 'timing', 77, 'flawless');
    c1 := t.coins(pa);
    gid := (select id from public.rb_held where owner = pa limit 1);
    perform t.act(boss);
    err := t.try(format('select public.rb_admin_held(%L, true, true)', gid));
    reset role;
    assert err = '', 'held: ' || err;
    if err = '' then
        assert t.coins(pa) = c1 + 77 and exists (select 1 from public.rb_trusted where owner = pa), 'paid and trusted';
        assert public.rb_integrity(pa, 'timing', 120) is null, 'trusted: never held';
    end if;
end $$;
rollback;
