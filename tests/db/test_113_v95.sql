-- 9.5 (096): bet cap 20 % (1 000 to 250 000), the comeback top-up (up TO the floor, once a day), daily login coins AND
-- a case growing with the streak, the bot challenges in the quests, a case on every weekly quest.
begin;
do $$
declare pa uuid := t.player('Topper', 800, 0); pb uuid := t.player('Richie', 5000, 0); r jsonb; j json; err text;
        cnt integer; c0 bigint; k0 integer;
begin
    assert public.rb_bet_cap(100000) = 20000, 'cap 20 %: ' || public.rb_bet_cap(100000);
    assert public.rb_bet_cap(2000) = 1000, 'never below 1 000';
    assert public.rb_bet_cap(50000000) = 250000, 'never above 250 000';

    -- the top-up brings you up TO the floor, once a day
    perform t.act(pa);
    r := public.rb_topup_state();
    assert (r ->> 'floor')::int = 1000 and not (r ->> 'used')::boolean, 'state: ' || r::text;
    r := public.rb_topup();
    assert (r ->> 'got')::int = 200 and (r ->> 'coins')::int = 1000, '800 -> 1 000: ' || r::text;
    reset role;
    assert t.coins(pa) = 1000, 'paid';
    update public.profiles set coins = 100 where id = pa;
    perform t.act(pa);
    err := t.try('select public.rb_topup()');
    assert err like '%rb_wait%', 'once a day: ' || err;
    reset role;
    perform t.act(pb);
    err := t.try('select public.rb_topup()');
    assert err like '%rb_not_needed%', 'above the floor: ' || err;
    reset role;

    -- daily login: coins and a case
    c0 := t.coins(pb);
    k0 := coalesce((select s.n from public.rb_case_stock s where s.owner = pb and s.case_id = 'starter'), 0);
    perform t.act(pb);
    j := public.rb_login_state();
    assert (j ->> 'bonus')::int = 0 and (j -> 'rewards' -> 0 ->> 'coins')::int > 0, 'state: ' || j::text;
    r := public.rb_login_claim();
    assert (r -> 'reward' ->> 'coins')::int = 300 and r -> 'reward' ->> 'case' = 'starter', 'day 1: ' || r::text;
    reset role;
    assert t.coins(pb) = c0 + 300, 'coins paid';
    assert (select s.n from public.rb_case_stock s where s.owner = pb and s.case_id = 'starter') = k0 + 1, 'case given';
    -- three weeks in: +30 % on day 22
    update public.profiles set streak = 21, streak_day = public.rb_today() - 1 where id = pb;
    perform t.act(pb);
    j := public.rb_login_state();
    assert (j ->> 'bonus')::int = 30, 'day 22 is in week 4: +30 %: ' || j::text;
    r := public.rb_login_claim();
    assert (r ->> 'streak')::int = 22 and (r -> 'reward' ->> 'coins')::int = 390, 'day 22 = day 1 x 1.3: ' || r::text;
    reset role;

    -- quests: one bot challenge of each length, every weekly quest gives a case
    perform t.act(pb);
    j := public.rb_quests();
    select count(*) into cnt from json_array_elements(j) x where x ->> 'quest' ~ '^[hdw]b_';
    assert cnt = 3, 'three bot challenges: ' || j::text;
    select count(*) into cnt from json_array_elements(j) x where x ->> 'kind' = 'week' and x -> 'prize' ->> 'case' is null;
    assert cnt = 0, 'a case on every weekly quest';
    reset role;
    insert into public.rb_hoops_games (owner, level, mins, state, done_at, won) values
        (pb, 'Professional', 3, 'done', now(), true), (pb, 'Club', 3, 'done', now(), true);
    assert public.rb_bot_hoops_wins(pb, array['National', 'Professional'], now() - interval '1 hour') = 1, 'hoops wins by level';
end $$;
rollback;
