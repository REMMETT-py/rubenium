-- 9.0 (with the 9.1 tiers and forge): wealth tiers, scaled rewards, the Key Forge, the market closed, no automatic cheat flags, the new rigs.
-- needs_live_snapshot (uses tables made on the live server only: game locks, flags, Cups)
begin;
do $$
declare a uuid := t.player('Alice', 30000, 2); b uuid := t.player('Bob', 0, 0); boss uuid := t.player('Boss', 0, 0);
        r jsonb; err text; n integer; c0 bigint;
begin
    update public.profiles set admin = true where id = boss;
    update public.rb_config set value = 25000 where key = 'tier_at_1';      -- 9.4 raised it; this checks the 9.0 rules
    -- tiers come from wealth: 30 000 coins is Average (x1.3); nothing is Poor (x1)
    assert (public.rb_tier(a) ->> 'name') = 'Average', 'Alice should be Average: ' || public.rb_tier(a)::text;
    assert public.rb_tier_mult(a) = 1.3, 'Average is x1.3';
    assert (public.rb_tier(b) ->> 'name') = 'Poor' and public.rb_tier_mult(b) = 1, 'Bob should be Poor';
    assert public.rb_scaled(100, 1.6) = 160 and public.rb_scaled(1000, 1.25) = 1250 and public.rb_scaled(30, 1.25) = 40,
        'scaled rounding';

    -- the free spin pays the scaled slot (rigged to the first slot: 100 x 1.3)
    perform t.act(boss);
    perform public.rb_admin_rig('Alice', 'wheel', '', '{"slot": 0}');
    perform t.act(a);
    c0 := t.coins(a);
    r := public.rb_spin();
    assert (r ->> 'won')::int = 130, 'spin should pay 130: ' || r::text;
    assert t.coins(a) = c0 + 130, 'spin coins paid';
    assert (public.rb_spin_odds() -> 'slots' ->> 0)::int = 130, 'the wheel shows the scaled slots';
    err := t.try('select public.rb_spin()');
    assert err like '%rb_too_soon%', 'one spin an hour: ' || err;

    -- the scratch card (rigged to standard: 150-300 x 1.3)
    reset role;
    perform t.act(boss);
    perform public.rb_admin_rig('Alice', 'scratch', '', '{"tier": "standard"}');
    perform t.act(a);
    r := public.rb_scratch();
    assert (r ->> 'coins_won')::int between 190 and 390, 'scratch scaled: ' || r::text;

    assert (public.rb_scratch_odds()::jsonb -> 0 ->> 'a')::int = 200, 'scratch chances show scaled prizes';

    -- daily reward rows are scaled for the player
    r := public.rb_login_state()::jsonb;
    assert r -> 'rewards' -> 0 ->> 'case' = 'starter', '9.4: day 1 is a Starter Case: ' || r::text;

    -- the Key Forge (9.1): 0.5% of wealth (at least 250), 3 a day for a Poor player
    reset role;
    perform t.act(b);
    err := t.try('select public.rb_key_forge()');
    assert err like '%rb_not_enough%', 'Bob has no coins: ' || err;
    reset role;
    update public.profiles set coins = 5000 where id = b;
    perform t.act(b);
    r := public.rb_key_forge();
    assert (r ->> 'paid')::int = 250 and (r ->> 'keys')::int = 1, 'forge at the 250 floor: ' || r::text;
    for n in 1 .. 4 loop perform public.rb_key_forge(); end loop;               -- 9.2.1: Poor forges 5 a day
    err := t.try('select public.rb_key_forge()');
    assert err like '%rb_too_many%', 'five a day (9.2.1): ' || err;
    assert (public.rb_my_tier() -> 'forge' ->> 'left')::int = 0, 'none left today';

    -- the market is closed
    err := t.try('select public.rb_market_mine()');
    assert err like '%rb_feature_gone%', 'market closed: ' || err;

    -- no automatic flags or locks, whatever happens
    reset role;
    perform public.rb_flag(b, 'cups', 'profit', 3, '{}'::jsonb, 72);
    assert not exists (select 1 from public.rb_game_locks where owner = b), 'nothing locked automatically';
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (b, 'cups', 10, '{"level": 2}', false, 900000);
    assert not exists (select 1 from public.rb_flags where owner = b and not reviewed), 'nothing flagged';

    -- new rigs: plinko lands in the box asked for, roulette on the pocket, rocket at the crash point
    perform t.act(boss);
    perform public.rb_admin_rig('Bob', 'plinko', '', '{"box": 10}');
    perform public.rb_admin_rig('Bob', 'roulette', '', '{"slot": 0}');
    perform public.rb_admin_rig('Bob', 'rocket', '', '{"crash": 1}');
    err := t.try($q$select public.rb_admin_rig('Bob', 'plinko', '', '{"box": 11}')$q$);
    assert err like '%rb_bad_choice%', 'plinko box 0-10: ' || err;
    perform t.act(b);
    r := public.rb_plinko(10, 0, 'p1');
    assert (r ->> 'box')::int = 10, 'rigged plinko: ' || r::text;
    r := public.rb_roulette_multi(10, array['gold'], 'r1');
    assert (r ->> 'slot')::int = 0 and (r ->> 'win')::boolean, 'rigged roulette: ' || r::text;
    r := public.rb_plinko(10, 0, 'p2');
    assert jsonb_array_length(r -> 'path') = 10, 'normal plinko after the rig';

    -- admin: set a balance, give everyone
    perform t.act(boss);
    r := public.rb_admin_set_balance('Bob', 1234, 7);
    assert t.coins(b) = 1234 and (r ->> 'keys')::int = 7, 'balance set';
    n := public.rb_admin_grant_all(100, 1);
    assert n >= 3, 'given to everyone';
    assert t.coins(b) = 1334, 'Bob got 100';
    perform t.act(a);
    err := t.try('select public.rb_admin_grant_all(1, 1)');
    assert err like '%rb_not_admin%', 'players cannot: ' || err;
    err := t.try($q$select public.rb_tier('00000000-0000-0000-0000-000000000000')$q$);
    assert err like '%permission denied%', 'helpers are not for players: ' || err;
end $$;
rollback;
