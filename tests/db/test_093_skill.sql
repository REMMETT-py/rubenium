-- 9.1: the skill games (Timing, Cups, Connect 4, Colour Pick, SFX Match) take no bet and pay by how well you did,
-- judged on the server, times the tier, fading after the first rounds and capped each day.
-- needs_live_snapshot
begin;
do $$
declare a uuid := t.player('Alice', 1000, 0); r jsonb; coin int; gid uuid; n int;
begin
    -- the pay rule
    assert public.rb_skill_base('timing', 'perfect') = 120 and public.rb_skill_base('c4', 'pro') = 600, 'bases';
    assert public.rb_skill_pay(a, 'timing', 120) = 120, 'full pay';
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        select a, 'timing', 0, '{}'::jsonb, false, 10 from generate_series(1, 6);
    assert public.rb_skill_pay(a, 'timing', 120) = 60, 'half after the first rounds';
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
        select a, 'timing', 0, '{}'::jsonb, false, 10 from generate_series(1, 6);
    assert public.rb_skill_pay(a, 'timing', 120) = 30, 'a quarter after that';
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (a, 'timing', 0, '{}'::jsonb, false, 800);
    assert public.rb_skill_pay(a, 'timing', 120) = 0, 'the daily cap: ' || public.rb_skill_window(a, 'timing')::text;
    assert public.rb_skill_pay(a, 'cups', 0) = 0, 'nothing for nothing';
    update public.profiles set coins = 1000 where id = a;

    -- Cup Game: no bet taken, paid by the level, from the server's own cup
    perform t.act(a);
    r := public.rb_cups('start', 1, 500, null, 'cups-1');
    reset role;
    assert t.coins(a) = 1000, 'no bet taken: ' || t.coins(a);
    update public.rb_rounds set secret = secret || jsonb_build_object('ready', extract(epoch from now()) - 1) where owner = a and game = 'cups' and open;
    coin := (select (secret ->> 'coin')::int from public.rb_rounds where owner = a and game = 'cups' and open);
    perform t.act(a);
    r := public.rb_cups('pick', 1, 0, coin, 'cups-2');
    reset role;
    assert (r ->> 'paid')::int = 50 and t.coins(a) = 1050, 'Medium win pays 50: ' || r::text;
    perform t.act(a);
    r := public.rb_cups('start', 1, 0, null, 'cups-3');
    reset role;
    update public.rb_rounds set secret = secret || jsonb_build_object('ready', extract(epoch from now()) - 1) where owner = a and game = 'cups' and open;
    coin := (select (secret ->> 'coin')::int from public.rb_rounds where owner = a and game = 'cups' and open);
    perform t.act(a);
    r := public.rb_cups('pick', 1, 0, (coin + 1) % 6, 'cups-4');
    reset role;
    assert (r ->> 'paid')::int = 0 and t.coins(a) = 1050, 'a wrong cup pays nothing and costs nothing';

    -- Connect 4: no bet, the server's own result pays
    perform t.act(a);
    r := public.rb_c4_start('hard', 700, 'c4-1');
    reset role;
    assert t.coins(a) = 1050, 'no bet on Connect 4';
    gid := (r ->> 'id')::uuid;
    r := public.rb_c4_finish(gid, 'win');
    assert (r ->> 'paid')::int = 200 and t.coins(a) = 1250, 'Hard win pays 200: ' || r::text;

    -- Timing and the matches start without a bet
    perform t.act(a);
    r := public.rb_timing('start', 900, 0, 'tm-1');
    perform public.rb_colour('start', 0, 900, null, 'co-1');
    perform public.rb_sfx('start', 0, 900, null, 'sf-1');
    r := public.rb_skill_state();
    reset role;
    assert t.coins(a) = 1250, 'no bets anywhere';
    assert (r -> 'c4' ->> 'paid')::int = 200 and (r -> 'cups' ->> 'rounds')::int = 2, 'state: ' || r::text;

    -- quests: these are mini games now, and only a round that paid counts
    delete from public.rb_rounds where owner = a and game = 'timing' and secret = '{}'::jsonb;
    select progress into n from public.rb_quest_rows(a) where quest = 'd_mini';
    assert n = 2, 'paid skill rounds count as mini games: ' || n;
    select progress into n from public.rb_quest_rows(a) where quest = 'd_rounds';
    assert n = 0, 'not casino rounds: ' || n;
end $$;
rollback;
