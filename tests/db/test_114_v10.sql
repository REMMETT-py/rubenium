-- 10.0 (099): Hoops online rooms (make, list, join, ping both ways, the final whistle, leave), and the reset ran once
-- with its backups.
begin;
do $$
declare ha uuid := t.player('Hosty', 4000, 0); gb uuid := t.player('Guesty', 4000, 0); r jsonb; rid uuid; err text;
begin
    assert coalesce(public.rb_cfg('reset_100'), 0) <> 0, 'the reset ran with the migration';
    assert to_regclass('public.rb_bak100_profiles') is not null and to_regclass('public.rb_bak100_items') is not null,
           'backups kept';
    err := t.try('select public.rb_reset_10()');
    assert err like '%rb_already_done%', 'only once: ' || err;

    perform t.act(ha);
    r := public.rb_hoops_room_create('vs', 'National', 3);
    rid := (r ->> 'id')::uuid;
    assert r ->> 'state' = 'open' and (r ->> 'me_host')::boolean, 'made: ' || r::text;
    err := t.try('select public.rb_hoops_room_create(''coop'', ''Club'', 2)');
    assert err like '%rb_one_lobby%', 'one room at a time: ' || err;
    err := t.try('select public.rb_hoops_room_join(''' || rid || ''')');
    assert err like '%rb_thats_you%', 'not your own: ' || err;
    reset role;

    perform t.act(gb);
    r := public.rb_hoops_rooms();
    assert jsonb_array_length(r -> 'rooms') = 1 and r -> 'rooms' -> 0 ->> 'host' = 'Hosty', 'listed: ' || r::text;
    r := public.rb_hoops_room_join(rid);
    assert r ->> 'state' = 'live' and not (r ->> 'me_host')::boolean and r ->> 'host' = 'Hosty', 'joined: ' || r::text;
    r := public.rb_hoops_ping(rid, '{"i": [1, 0]}');
    assert r -> 'other' = 'null'::jsonb or r ->> 'other' is null, 'nothing from the host yet: ' || r::text;
    reset role;

    perform t.act(ha);
    r := public.rb_hoops_rooms();
    assert r -> 'mine' ->> 'state' = 'live' and r -> 'mine' ->> 'guest' = 'Guesty', 'host sees it live: ' || r::text;
    r := public.rb_hoops_ping(rid, '{"s": {"ph": "play"}}');
    assert r -> 'other' -> 'i' ->> 0 = '1' and (r ->> 'age')::float < 5, 'host hears the guest: ' || r::text;
    perform public.rb_hoops_room_end(rid);
    r := public.rb_hoops_ping(rid, '{"s": {"ph": "over"}}');        -- the final whistle still goes out
    assert r ->> 'state' = 'done', 'over: ' || r::text;
    reset role;

    perform t.act(gb);
    r := public.rb_hoops_ping(rid, '{"i": [0, 0]}');
    assert r -> 'other' -> 's' ->> 'ph' = 'over', 'guest sees the end: ' || r::text;
    r := public.rb_hoops_rooms();
    assert r -> 'mine' = 'null'::jsonb or r ->> 'mine' is null, 'free again: ' || r::text;
    r := public.rb_hoops_room_create('coop', 'Club', 2);
    reset role;

    -- an open room closed by its host; a live room the host leaves
    perform t.act(gb);
    perform public.rb_hoops_room_leave((r ->> 'id')::uuid);
    reset role;
    assert (select state from public.rb_hoops_rooms where id = (r ->> 'id')::uuid) = 'cancelled', 'closed';

    perform t.act(ha);
    rid := (public.rb_hoops_room_create('coop', 'Club', 2) ->> 'id')::uuid;
    reset role;
    perform t.act(gb);
    perform public.rb_hoops_room_join(rid);
    reset role;
    perform t.act(ha);
    perform public.rb_hoops_room_leave(rid);
    reset role;
    perform t.act(gb);
    r := public.rb_hoops_ping(rid, '{"i": []}');
    assert r ->> 'why' = 'host_left' and (r -> 'other' ->> 'left')::boolean, 'guest told the host left: ' || r::text;
    reset role;

    -- nobody else can read or write a room
    perform t.act(ha);
    assert t.try('select * from public.rb_hoops_live') <> '', 'live rows are private';
    reset role;
end $$;
rollback;
