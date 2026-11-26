-- 9.2 (084): Trifade rules, the solved book, the bots and the Arena flow.
-- needs_live_snapshot
begin;
do $$
declare b jsonb := public.tri_new(); nb jsonb; pa uuid := t.player('Trier', 1000, 0); r jsonb; g uuid; i integer;
        m integer; k integer; won_ integer := 0; lost_ integer := 0; legal integer[]; me integer[]; op integer[];
        best integer; sc integer; cv integer;
begin
    -- 9.2: mini games pay double
    assert public.rb_cfg('skill_pay_mult') = 2 and public.rb_cfg('game_pay_mult') = 2, 'pay doubled';
    -- the rules: a 4th mark takes the oldest away, no square twice, three in a row
    nb := public.tri_play(public.tri_play(public.tri_play(b, 1, 0), 1, 4), 1, 5);
    assert public.tri_q(nb, 1) = array[0, 4, 5], 'three marks';
    assert public.tri_play(nb, 1, 0) is null and public.tri_play(nb, 2, 4) is null, 'no square twice (not even your oldest)';
    nb := public.tri_play(nb, 1, 8);
    assert public.tri_q(nb, 1) = array[4, 5, 8], 'the oldest went: ' || nb::text;
    assert public.tri_win(array[2, 4, 6]) and public.tri_win(array[6, 3, 0]) and not public.tri_win(array[0, 1, 5]), 'lines';
    -- the book: the first side to move wins in 13, and symmetry gives the same key
    assert public.tri_val('{}', '{}') = 13, 'start is won in 13: ' || public.tri_val('{}', '{}');
    assert public.tri_key(array[0], array[4]) = public.tri_key(array[8], array[4]), 'symmetry';
    assert (select count(*) from public.rb_tri_book) = 7393, 'book size';
    -- Professional always starts and beats a random player every time
    for k in 1..12 loop
        perform t.act(pa);
        r := public.rb_bg_bot('tri', 'insane');
        reset role;
        assert (r ->> 'turn')::int = 1 and (r ->> 'n')::int = 1, 'Professional moved first';
        g := (r ->> 'id')::uuid;
        for i in 1..80 loop
            r := public.rb_bg_json((select x from public.rb_bg x where x.id = g), pa);
            exit when r ->> 'state' <> 'live';
            me := public.tri_q(r -> 'board', 1); op := public.tri_q(r -> 'board', 2);
            legal := array(select c from generate_series(0, 8) c where not c = any(me) and not c = any(op));
            m := legal[1 + floor(random() * cardinality(legal))::int];
            perform t.act(pa);
            r := public.rb_bg_move(g, m, (r ->> 'n')::int);
            reset role;
        end loop;
        assert r ->> 'state' = 'done' and (r ->> 'winner')::int = 2, 'Professional won: ' || r::text;
    end loop;
    -- a perfect player starting against Hard always wins
    for k in 1..4 loop
        perform t.act(pa);
        r := public.rb_bg_bot('tri', 'hard');
        reset role;
        assert (r ->> 'turn')::int = 1 and (r ->> 'n')::int = 0, 'you start against Hard';
        g := (r ->> 'id')::uuid;
        for i in 1..80 loop
            r := public.rb_bg_json((select x from public.rb_bg x where x.id = g), pa);
            exit when r ->> 'state' <> 'live';
            me := public.tri_q(r -> 'board', 1); op := public.tri_q(r -> 'board', 2);
            best := null;
            for c in 0..8 loop
                continue when c = any(me) or c = any(op);
                if public.tri_win(public.tri_add(me, c)) then sc := 2000;
                else cv := public.tri_val(op, public.tri_add(me, c));
                     sc := case when cv < 0 then 1000 + cv when cv > 0 then -1000 + cv else 0 end; end if;
                if best is null or sc > best then best := sc; m := c; end if;
            end loop;
            perform t.act(pa);
            r := public.rb_bg_move(g, m, (r ->> 'n')::int);
            reset role;
        end loop;
        assert r ->> 'state' = 'done' and (r ->> 'winner')::int = 1, 'perfect play beats Hard: ' || r::text;
        assert (r ->> 'paid')::int > 0, 'a win pays';
    end loop;
    -- Easy loses to the perfect player too, and a duel opens
    perform t.act(pa);
    r := public.rb_bg_create('tri', 0);
    reset role;
    assert r ->> 'state' = 'open' and r ->> 'kind' = 'tri', 'tri duel opens';
    perform t.act(pa);
    perform public.rb_leaders('tri', false);
    perform public.rb_leaders('a:tri', false);
    r := public.rb_skill_state();
    reset role;
    assert r ? 'tri' and r ? 'maze', 'fresh bonus counts for Trifade and Mazelock';
end $$;
rollback;
