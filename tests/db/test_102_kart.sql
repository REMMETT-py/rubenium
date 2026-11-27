-- 9.2 (086): Karting rooms: solo with the line, rooms with one bot, the grid, live positions, checked finishes, the
-- score, places, the prize and the leaderboard. 093: the new calibration, the 12.5 s start, a finished player is free.
-- needs_live_snapshot
begin;
do $$
declare pa uuid := t.player('KartA', 1000, 0); pb uuid := t.player('KartB', 1000, 0); pc uuid := t.player('KartC', 1000, 0);
        pd uuid := t.player('KartD', 1000, 0); r jsonb; rid uuid; sid uuid; err text; c0 bigint; sc numeric;
begin
    -- the score: Professional's pace is 99.6, Elite's 80, slower than Rookie still above 0
    assert public.rb_kart_score(0, 3, 96216) between 99 and 100, 'pro band: ' || public.rb_kart_score(0, 3, 96216);
    assert public.rb_kart_score(0, 3, 108696) between 79 and 81, 'elite band: ' || public.rb_kart_score(0, 3, 108696);
    assert public.rb_kart_score(1, 3, 300000) between 0 and 28, 'slow: ' || public.rb_kart_score(1, 3, 300000);
    assert public.rb_kart_score(2, 3, 90000) = 100, 'capped at 100';
    -- solo, no bot: straight to the lights
    perform t.act(pd);
    r := public.rb_kart_create(1, 1, 3, 1500, false, true, true, true);
    sid := (r ->> 'id')::uuid;
    reset role;
    assert r ->> 'state' = 'live' and (r ->> 'bot')::boolean = false, 'solo live: ' || r::text;
    update public.rb_kart_rooms set go_at = now() - interval '200 seconds' where id = sid;
    perform t.act(pd);
    err := t.try(format('select public.rb_kart_finish(%L, 60000, array[20000,20000,20000], 20000, 0, 0, 0, 0, false)', sid));
    assert err like '%rb_too_fast%', 'impossible time refused: ' || err;
    err := t.try(format('select public.rb_kart_finish(%L, 150000, array[50000,50000,40000], 40000, 0, 0, 0, 0, false)', sid));
    assert err like '%rb_too_fast%', 'laps must add up: ' || err;
    c0 := t.coins(pd);
    r := public.rb_kart_finish(sid, 150000, array[52000, 49000, 49000], 49000, 0, 0, 2, 0, false);
    reset role;
    assert r ->> 'state' = 'done', 'solo settled: ' || r::text;
    assert (r -> 'players' -> 0 ->> 'place')::int = 1 and (r -> 'players' -> 0 ->> 'score')::numeric > 0, 'scored';
    assert t.coins(pd) > c0, 'solo pays something';
    -- a room for 3 with a Professional bot on Sunset Bay
    perform t.act(pa);
    r := public.rb_kart_create(3, 0, 3, 2500, false, true, true, true);
    rid := (r ->> 'id')::uuid;
    assert r ->> 'state' = 'open' and (r ->> 'bot')::boolean, 'room open, always one bot: ' || r::text;
    err := t.try('select public.rb_kart_create(1, 0, 3, 100, true, true, true, true)');
    assert err like '%rb_one_lobby%', 'one room at a time: ' || err;
    reset role;
    perform t.act(pb);
    r := public.rb_kart_lobbies();
    assert exists (select 1 from jsonb_array_elements(r -> 'rooms') e where e ->> 'id' = rid::text), 'listed';
    assert not exists (select 1 from jsonb_array_elements(r -> 'rooms') e where e ->> 'id' = sid::text), 'solo never listed';
    r := public.rb_kart_join(rid);
    reset role;
    assert r ->> 'state' = 'open', 'still open';
    perform t.act(pc);
    r := public.rb_kart_join(rid);
    reset role;
    assert r ->> 'state' = 'live', 'full: live';
    assert (r ->> 'bot_slot')::int = 3, 'the bot takes the best slot';
    assert (select count(distinct slot) from public.rb_kart_seats where room = rid and slot between 0 and 2) = 3, 'players on the other 3';
    assert (r ->> 'go_in')::numeric between 11.5 and 13, 'lights in 12.5 s';
    -- live positions: A drives the bot; B can't
    update public.rb_kart_rooms set go_at = now() - interval '130 seconds' where id = rid;
    perform t.act(pa);
    r := public.rb_kart_ping(rid, '[[0, 10.0, 1, 2, 0, 0, 0, 0, 100, 0, 0, 50, 100, 0, 0, 0], [3, 10.0, 5, 6, 0, 0, 0, 0, 100, 0, 1, 800, 100, 0, 0, 0]]'::jsonb);
    assert (r ->> 'bot_here')::boolean, 'host drives the bot';
    reset role;
    perform t.act(pb);
    r := public.rb_kart_ping(rid, '[[1, 10.0, 9, 9, 0, 0, 0, 0, 100, 0, 0, 40, 100, 0, 0, 0], [3, 10.0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 100, 0, 0, 0]]'::jsonb);
    reset role;
    assert jsonb_array_length(r -> 'karts') = 2, 'B sees A and the bot: ' || r::text;
    assert (select (snap ->> 2)::int from public.rb_kart_live where room = rid and seat = 3) = 5, 'B could not move the bot';
    perform t.act(pc);
    r := public.rb_kart_ping(rid, '[[2, 10.0, 9, 9, 0, 0, 0, 0, 100, 0, 0, 30, 100, 0, 0, 0]]'::jsonb);
    reset role;
    -- finishes: A beats the bot, B doesn't, C leaves
    perform t.act(pa);
    c0 := t.coins(pa);
    r := public.rb_kart_finish(rid, 95900, array[32600, 31650, 31650], 31650, 0, 2, 3, 0, false);
    r := public.rb_kart_finish(rid, 96300, array[32700, 31800, 31800], 31800, 0, 0, 0, 0, true);
    reset role;
    assert not public.rb_kart_busy(pa) and public.rb_kart_busy(pb), 'over the line: free for the next race (B still racing)';
    perform t.act(pa);
    assert jsonb_typeof(public.rb_kart_lobbies() -> 'mine') = 'null', 'the lobby no longer shows the race A finished';
    reset role;
    perform t.act(pb);
    r := public.rb_kart_finish(rid, 125000, array[42000, 42000, 41000], 41000, 1, 1, 0, 0, false);
    reset role;
    assert r ->> 'state' = 'live', 'C still racing';
    perform t.act(pc);
    r := public.rb_kart_leave(rid);
    r := public.rb_kart_state(rid);
    reset role;
    assert r ->> 'state' = 'done', 'all done: ' || r::text;
    assert (select place from public.rb_kart_seats where room = rid and owner = pa) = 1, 'A first';
    assert (r ->> 'bot_place')::int = 2, 'bot second';
    assert (select place from public.rb_kart_seats where room = rid and owner = pb) = 3, 'B third';
    assert (select place from public.rb_kart_seats where room = rid and owner = pc) = 4 and
           (select paid from public.rb_kart_seats where room = rid and owner = pc) = 0, 'C left: last, nothing';
    assert t.coins(pa) - c0 > (select paid from public.rb_kart_seats where room = rid and owner = pb), 'beating the pro bot pays most';
    sc := (select score from public.rb_kart_seats where room = rid and owner = pa);
    assert sc > 99, 'A score: ' || sc;
    -- the leaderboard
    perform t.act(pb);
    r := public.rb_leaders('kart', false)::jsonb;
    reset role;
    assert (r -> 'top' -> 0 ->> 'name') = 'KartA' and (r -> 'top' -> 0 ->> 'value')::int = round(sc * 10), 'board: ' || r::text;
end $$;
rollback;
