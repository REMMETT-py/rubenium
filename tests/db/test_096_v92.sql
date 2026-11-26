-- 9.2 (082): fresh boards, quests from the reset, the 20 minute arena clock, no Reversi, an empty duel never blocks.
-- needs_live_snapshot
begin;
do $$
declare pa uuid := t.player('Alice', 5000, 0); r jsonb; err text; k bigint; a record; c0 bigint; cyc double precision;
begin
    -- an empty duel of yours no longer blocks a bot game, and its bet comes back
    perform t.act(pa);
    r := public.rb_bg_create('c4', 100);
    reset role;
    c0 := (select coins from public.profiles where id = pa);
    perform t.act(pa);
    r := public.rb_bg_bot('ships', 'easy');
    reset role;
    assert r ->> 'state' = 'live', 'bot game started: ' || r::text;
    assert (select coins from public.profiles where id = pa) = c0 + 100, 'duel bet back';
    perform t.act(pa);
    err := t.try('select public.rb_bg_bot(''reversi'', ''easy'')');
    assert err like '%rb_bad_choice%', 'no Reversi bots: ' || err;
    err := t.try('select public.rb_bg_create(''reversi'', 0)');
    assert err like '%rb_bad_choice%', 'no Reversi duels: ' || err;
    reset role;

    -- boards and quests count from the reset on
    insert into public.rb_rounds (owner, game, bet, paid, open, at, secret) values (pa, 'slots', 10, 500, false, now() - interval '1 minute', '{}');
    update public.rb_config set value = extract(epoch from now()) - 30 where key = 'board_from';
    assert public.rb_best_win(pa, 'slots') = 0, 'old round not on the board';
    perform t.act(pa);
    r := public.rb_leaders('g:slots', true)::jsonb;
    reset role;
    assert coalesce((r -> 'me' ->> 'value')::int, 0) = 0, 'board fresh: ' || r::text;
    assert (select progress from public.rb_quest_rows(pa) where quest = 'w_rounds') = 0, 'quest fresh';

    -- the arena clock: a slot opens its own kind, anchored at the slot start
    delete from public.rb_arena;
    cyc := public.rb_cfg('arena_cycle_s');
    perform public.rb_arena_tick();
    select * into a from public.rb_arena where id = 1;
    k := floor(extract(epoch from now()) / cyc)::bigint;
    if extract(epoch from now()) - k * cyc <= 60 then
        assert a.cur_kind = public.rb_arena_slot_kind(k), 'slot kind';
    else
        assert a.cur_id is null, 'late in the slot: waits for the next one';
    end if;
    assert public.rb_arena_next(case when public.rb_arena_slot_kind(k + 1) = 'race' then 'race' else 'jackpot' end)
           = (k + 1) * cyc or a.cur_kind = public.rb_arena_slot_kind(k + 1), 'next slot time';
    assert public.rb_flip_find_s(10000) < 8 and public.rb_flip_find_s(5000000) between 90 and 120, 'bot wait by value';
    assert not exists (select 1 from public.rb_catalog where id like 'font:%:white'), 'Titanium fonts gone';

    -- any player's stats, and the name picker
    perform t.player('Alicia', 0, 0);
    perform t.act(pa);
    r := public.rb_find_players('ali');
    assert jsonb_array_length(r) >= 2 and r -> 0 ->> 'name' in ('Alice', 'Alicia'), 'names found: ' || r::text;
    assert jsonb_array_length(public.rb_find_players('%')) = 0, 'no wildcard search';
    r := public.rb_player_stats('alicia', 30);
    assert r ->> 'name' = 'Alicia' and r ? 'series' and not (r ->> 'me')::boolean, 'stats of another player';
    assert public.rb_my_stats(30) ? 'series', 'own stats still there';
    err := t.try('select public.rb_player_stats(''nobodyhere'', 30)');
    assert err like '%rb_no_such_user%', 'unknown name: ' || err;
    reset role;
end $$;
rollback;
