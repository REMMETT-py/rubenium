-- 9.2 (084): Mazelock rules, bots and the Arena flow.
-- needs_live_snapshot
begin;
do $$
declare b jsonb := public.mz_new(); nb jsonb; pa uuid := t.player('Mazer', 1000, 0); r jsonb; g uuid; i integer; m integer;
begin
    -- steps: from the start, up, left and right
    assert public.mz_steps(b ->> 'h', b ->> 'v', 76, 4) @> array[67, 75, 77] and cardinality(public.mz_steps(b ->> 'h', b ->> 'v', 76, 4)) = 3, 'start steps';
    -- a jump straight over, and to the side when a wall is behind
    assert 49 = any(public.mz_steps(b ->> 'h', b ->> 'v', 67, 58)), 'jump over';
    nb := public.mz_play(b, 1, 100 + 5 * 8 + 4);                     -- a wall under row 5 at columns 4-5
    assert nb is not null and (nb -> 'w' ->> 0)::int = 9, 'wall placed';
    assert public.mz_steps(nb ->> 'h', nb ->> 'v', 58 + 9, 58) @> array[57, 59] and not 49 = any(public.mz_steps(nb ->> 'h', nb ->> 'v', 67, 58)), 'side jump';
    assert public.mz_play(nb, 2, 100 + 5 * 8 + 4) is null, 'no wall on a wall';
    assert public.mz_play(nb, 2, 100 + 5 * 8 + 5) is null, 'no overlapping wall';
    assert public.mz_play(nb, 2, 200 + 5 * 8 + 4) is null, 'no crossing wall';
    assert public.mz_play(nb, 2, 100 + 5 * 8 + 6) is not null, 'a wall next to it is fine';
    -- never close a pawn in: three walls round the top-left cell of side 2's way
    nb := public.mz_play(public.mz_play(b, 1, 100 + 0 * 8 + 3), 1, 100 + 0 * 8 + 5);
    nb := public.mz_play(nb, 1, 200 + 0 * 8 + 2);
    assert nb is not null, 'walls round the start';
    assert public.mz_play(nb, 1, 200 + 0 * 8 + 6) is null or public.mz_dist((public.mz_play(nb, 1, 200 + 0 * 8 + 6)) ->> 'h',
           (public.mz_play(nb, 1, 200 + 0 * 8 + 6)) ->> 'v', 4, 8) < 999, 'never walled in';
    assert public.mz_play(b, 1, 76 - 18) is null, 'no two-square step';
    -- the bot game: Easy lets you start, Professional starts itself
    perform t.act(pa);
    r := public.rb_bg_bot('maze', 'easy');
    reset role;
    assert r ->> 'state' = 'live' and (r ->> 'turn')::int = 1 and r -> 'legal' is not null, 'easy game: ' || r::text;
    g := (r ->> 'id')::uuid;
    for i in 1..200 loop
        r := public.rb_bg_json((select x from public.rb_bg x where x.id = g), pa);
        exit when r ->> 'state' <> 'live';
        m := (public.mz_path(r -> 'board' ->> 'h', r -> 'board' ->> 'v', (r -> 'board' -> 'p' ->> 0)::int, 0))[1];
        if not m = any(array(select jsonb_array_elements_text(r -> 'legal')::int)) then
            m := (r -> 'legal' ->> 0)::int;
        end if;
        perform t.act(pa);
        r := public.rb_bg_move(g, m, (r ->> 'n')::int);
        reset role;
    end loop;
    assert r ->> 'state' = 'done', 'the game ends: ' || r::text;
    perform t.act(pa);
    r := public.rb_bg_bot('maze', 'insane');
    reset role;
    assert (r ->> 'turn')::int = 1 and (r ->> 'n')::int = 1, 'the Professional bot moved first: ' || r::text;
    perform t.act(pa);
    perform public.rb_bg_resign((r ->> 'id')::uuid);
    r := public.rb_bg_create('maze', 0);
    reset role;
    assert r ->> 'state' = 'open' and r ->> 'kind' = 'maze', 'maze duel opens';
end $$;
rollback;
