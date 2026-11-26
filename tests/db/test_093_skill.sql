-- 9.1: the skill games (Timing, Cups, Connect 4, Colour Pick, SFX Match) take no bet and pay by how well you did,
-- judged on the server, times the tier. 9.1 (080): the first rounds of the day pay double, there is no daily cap, and
-- a flawless run at the top level waits for an admin.
-- needs_live_snapshot
begin;
-- 9.2 doubles skill pay (skill_pay_mult 2): these rule checks use the plain bases
update public.rb_config set value = 1 where key = 'skill_pay_mult';
do $$
declare a uuid := t.player('Alice', 1000, 0); r jsonb; coin int; gid uuid; n int;
begin
    -- the pay rule
    assert public.rb_skill_base('timing', 'perfect') = 120 and public.rb_skill_base('c4', 'pro') = 600, 'bases';
    assert public.rb_skill_pay(a, 'timing', 120) = 240, 'the fresh bonus doubles the first rounds';
    insert into public.rb_skill_log (owner, game, base, pay) select a, 'timing', 50, 100 from generate_series(1, 7);
    assert public.rb_skill_pay(a, 'timing', 120) = 120, 'then the normal pay, with no cap';
    insert into public.rb_skill_log (owner, game, base, pay) select a, 'timing', 120, 120 from generate_series(1, 29);
    assert public.rb_skill_pay(a, 'timing', 120) = 0, 'a flawless run waits for an admin';
    assert exists (select 1 from public.rb_held where owner = a and game = 'timing' and coins = 120 and why = 'flawless'), 'held';
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
    assert (r ->> 'paid')::int = 100 and t.coins(a) = 1100, 'Medium win pays 50, doubled while fresh: ' || r::text;
    perform t.act(a);
    r := public.rb_cups('start', 1, 0, null, 'cups-3');
    reset role;
    update public.rb_rounds set secret = secret || jsonb_build_object('ready', extract(epoch from now()) - 1) where owner = a and game = 'cups' and open;
    coin := (select (secret ->> 'coin')::int from public.rb_rounds where owner = a and game = 'cups' and open);
    perform t.act(a);
    r := public.rb_cups('pick', 1, 0, (coin + 1) % 6, 'cups-4');
    reset role;
    assert (r ->> 'paid')::int = 0 and t.coins(a) = 1100, 'a wrong cup pays nothing and costs nothing';

    -- Connect 4: no bet, the server's own result pays
    perform t.act(a);
    r := public.rb_c4_start('hard', 700, 'c4-1');
    reset role;
    assert t.coins(a) = 1100, 'no bet on Connect 4';
    gid := (r ->> 'id')::uuid;
    r := public.rb_c4_finish(gid, 'win');
    assert (r ->> 'paid')::int = 400 and t.coins(a) = 1500, 'Hard win pays 200, doubled while fresh: ' || r::text;

    -- Timing and the matches start without a bet
    perform t.act(a);
    r := public.rb_timing('start', 900, 0, 'tm-1');
    perform public.rb_colour('start', 0, 900, null, 'co-1');
    perform public.rb_sfx('start', 0, 900, null, 'sf-1');
    r := public.rb_skill_state();
    reset role;
    assert t.coins(a) = 1500, 'no bets anywhere';
    assert (r -> 'c4' ->> 'paid')::int = 400 and (r -> 'cups' ->> 'rounds')::int = 1 and (r ->> 'held')::int = 120, 'state: ' || r::text;

    -- quests: these are mini games now, and only a round that paid counts
    delete from public.rb_rounds where owner = a and game = 'timing' and secret = '{}'::jsonb;
    select progress into n from public.rb_quest_rows(a) where quest = 'd_mini';
    assert n = 2, 'paid skill rounds count as mini games: ' || n;
    select progress into n from public.rb_quest_rows(a) where quest = 'd_rounds';
    assert n = 0, 'not casino rounds: ' || n;

    -- the Stats tab: your own numbers, the balance line ends on your coins, the rewards split by source
    insert into public.rb_ledger (owner, coins, keys, reason, ref) values (a, 30, 0, 'time', null), (a, 100, 1, 'quest', 'x');
    update public.profiles set coins = coins + 130, keys = keys + 1 where id = a;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (a, 'slots', 100, '{}', false, 300);
    perform t.act(a);
    r := public.rb_my_stats(500);
    reset role;
    assert (r ->> 'days')::int = 90 and jsonb_array_length(r -> 'series') = 90, 'at most 90 days: ' || (r ->> 'days');
    assert (r -> 'series' -> 89 ->> 'balance')::bigint = t.coins(a), 'the line ends on the balance';
    assert (r -> 'series' -> 89 -> 'r' ->> 0)::int = 30 and (r -> 'series' -> 89 -> 'r' ->> 4)::int = 100, 'rewards by source: ' || (r -> 'series' -> 89)::text;
    assert (r -> 'series' -> 89 -> 'r' ->> 5)::int = 860, 'skill pay (240 + 120 + 100 + 400) counts as mini games: ' || (r -> 'series' -> 89)::text;
    assert (r -> 'games' -> 'slots' ->> 'best')::int = 200, 'casino by game: ' || (r -> 'games')::text;
    assert (r -> 'minis' -> 'c4' ->> 'paid')::int = 400 and r -> 'games' -> 'c4' is null, 'mini games apart';
    assert (r -> 'series' -> 88 ->> 'balance')::bigint = t.coins(a) - (r -> 'series' -> 89 ->> 'net')::bigint, 'balance back in time';
end $$;
rollback;
