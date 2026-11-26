-- 9.4 (095): Karting time boards: a finished 3 lap race can save its run, the top 10 per circuit allows several places
-- per player, anyone can load a run, a run without a checked finish is never saved.
-- needs_live_snapshot
begin;
do $$
declare pa uuid := t.player('GhostA', 1000, 0); pb uuid := t.player('GhostB', 1000, 0); r jsonb; rid uuid; k integer;
        err text; gid text;
begin
    for k in 1 .. 3 loop
        perform t.act(case when k = 2 then pb else pa end);
        r := public.rb_kart_create(1, 1, 3, 1500, false, true, true, true);
        rid := (r ->> 'id')::uuid;
        reset role;
        update public.rb_kart_rooms set go_at = now() - interval '300 seconds' where id = rid;
        perform t.act(case when k = 2 then pb else pa end);
        -- before the finish: nothing is saved
        r := public.rb_kart_ghost_save(rid, repeat('A', 64));
        assert not (r ->> 'saved')::boolean, 'no finish, no run: ' || r::text;
        r := public.rb_kart_finish(rid, 150000 + k * 1000, array[50000 + k * 1000, 50000, 50000], 50000, 0, 0, 0, 0, false);
        r := public.rb_kart_ghost_save(rid, repeat('B', 64));
        assert (r ->> 'saved')::boolean and (r ->> 'track')::int = 1, 'saved: ' || r::text;
        err := t.try(format('select public.rb_kart_ghost_save(%L, %L)', rid, repeat('C', 500000)));
        assert err like '%rb_bad_choice%', 'a run too big is refused: ' || err;
        reset role;
    end loop;
    perform t.act(pb);
    r := public.rb_kart_times(1);
    assert jsonb_array_length(r -> 'top') = 3, 'three runs: ' || r::text;
    assert r -> 'top' -> 0 ->> 'name' = 'GhostA' and r -> 'top' -> 2 ->> 'name' = 'GhostA', 'A holds two places: ' || r::text;
    assert (r -> 'top' -> 0 ->> 'ms')::int = 151000, 'fastest first';
    assert (r -> 'mine' ->> 'rank')::int = 2 and (r -> 'mine' ->> 'ms')::int = 152000, 'my best: ' || (r -> 'mine')::text;
    gid := r -> 'top' -> 0 ->> 'id';
    r := public.rb_kart_ghost(gid::uuid);
    assert r ->> 'name' = 'GhostA' and r ->> 'data' = repeat('B', 64) and (r ->> 'ms')::int = 151000, 'load a run: ' || (r - 'data')::text;
    assert jsonb_array_length(public.rb_kart_times(0) -> 'top') = 0, 'other circuits are empty';
    reset role;
end $$;
rollback;
