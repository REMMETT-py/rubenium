-- 9.2 (085): Wave Rush rooms for 2 to 4 players: seats, bets, the start, the checked runs, the pot.
-- needs_live_snapshot
begin;
do $$
declare pa uuid := t.player('WaveA', 1000, 0); pb uuid := t.player('WaveB', 1000, 0); pc uuid := t.player('WaveC', 1000, 0);
        pd uuid := t.player('WaveD', 1000, 0); r jsonb; rid uuid; ra uuid; rb uuid; err text;
begin
    perform t.act(pa);
    r := public.rb_wroom_create(3, 100);
    rid := (r ->> 'id')::uuid;
    assert r ->> 'state' = 'open' and jsonb_array_length(r -> 'players') = 1, 'room open: ' || r::text;
    err := t.try('select public.rb_wroom_create(2, 0)');
    assert err like '%rb_one_lobby%', 'one room at a time: ' || err;
    reset role;
    assert t.coins(pa) = 900, 'host paid the bet';
    perform t.act(pb);
    r := public.rb_wroom_lobbies();
    assert exists (select 1 from jsonb_array_elements(r -> 'rooms') e where e ->> 'id' = rid::text and (e ->> 'seated')::int = 1), 'listed';
    r := public.rb_wroom_join(rid);
    reset role;
    assert r ->> 'state' = 'open', 'still open with 2 of 3';
    -- the third one leaves before the start: bet back
    perform t.act(pc);
    r := public.rb_wroom_join(rid);
    reset role;
    assert r ->> 'state' = 'live' and jsonb_array_length(r -> 'players') = 3, 'full: live';
    -- a fourth can't join a live room
    perform t.act(pd);
    err := t.try(format('select public.rb_wroom_join(%L)', rid));
    assert err like '%rb_duel_gone%', 'room full: ' || err;
    reset role;
    update public.rb_wave_runs set started_at = now() - interval '30 seconds' where room = rid;
    ra := (select run from public.rb_wave_seats where room = rid and owner = pa);
    rb := (select run from public.rb_wave_seats where room = rid and owner = pb);
    -- live positions are shared
    perform t.act(pb);
    r := public.rb_wroom_ping(rb, 300, array[20, 40], 50);
    reset role;
    assert (select live_t from public.rb_wave_runs where id = rb) = 50, 'ping kept';
    perform t.act(pa);
    r := public.rb_wroom_state(rid);
    assert exists (select 1 from jsonb_array_elements(r -> 'players') e where e ->> 'name' = 'WaveB' and (e ->> 't')::int = 50
                   and e ->> 'run' is null), 'others seen, their run id hidden';
    err := t.try(format('select public.rb_wave_finish(%L, ''{}''::int[], 100)', ra));
    assert err like '%rb_duel_gone%', 'a room run never pays as solo: ' || err;
    r := public.rb_wroom_finish(ra, '{}', 100);
    reset role;
    perform t.act(pb);
    r := public.rb_wroom_finish(rb, '{}', 50);
    reset role;
    assert r ->> 'state' = 'live', 'one still running';
    perform t.act(pc);
    r := public.rb_wroom_leave(rid);
    reset role;
    perform t.act(pa);
    r := public.rb_wroom_state(rid);
    reset role;
    assert r ->> 'state' = 'done', 'all done: ' || r::text;
    assert t.coins(pa) = 900 + 285, 'winner takes the pot less 5%: ' || t.coins(pa);
    assert t.coins(pb) = 900 and t.coins(pc) = 900, 'the others lost their bet';
    assert (select place from public.rb_wave_seats where room = rid and owner = pa) = 1, 'first place';
    -- an open room: a guest leaving gets the bet back, the host leaving closes it for everyone
    perform t.act(pa);
    r := public.rb_wroom_create(4, 50);
    rid := (r ->> 'id')::uuid;
    reset role;
    perform t.act(pd);
    r := public.rb_wroom_join(rid);
    r := public.rb_wroom_leave(rid);
    reset role;
    assert t.coins(pd) = 1000, 'guest bet back';
    perform t.act(pd);
    r := public.rb_wroom_join(rid);
    reset role;
    perform t.act(pa);
    err := t.try(format('select public.rb_wroom_start(%L)', rid));
    reset role;
    assert err = '', 'host starts with 2: ' || err;
    assert (select state from public.rb_wave_rooms where id = rid) = 'live', 'started early';
end $$;
rollback;
