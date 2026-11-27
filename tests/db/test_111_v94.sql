-- 9.4 (094): ranks cost more and go up one a day at most, the Key Forge resets every 12 hours, hourly keys once an
-- hour, daily rewards are cases, the free spin pays more, and rb_reset_94 starts everyone again (once, with a backup).
begin;
do $$
declare a uuid := t.player('V94A', 1000, 0); b uuid := t.player('V94B', 1000, 0); bt uuid := t.player('V94Bot', 777, 3);
        r jsonb; f jsonb; err text; k0 integer;
begin
    update public.profiles set bot = true where id = bt;
    insert into public.rb_items (owner, item, origin) values (bt, 'tag:og', 'test');
    assert public.rb_cfg('tier_at_1') = 50000 and public.rb_cfg('tier_at_4') = 5000000, 'new rank prices';

    -- ranks: rich enough for Casino Legend, but one rank a day
    update public.profiles set coins = 6000000 where id = a;
    r := public.rb_tier(a);
    assert (r ->> 'tier')::int = 1 and (r ->> 'reach')::int = 4 and (r ->> 'wait')::boolean, 'one rank first: ' || r::text;
    assert public.rb_tier_keep(a) = 1, 'kept Average';
    r := public.rb_tier(a);
    assert (r ->> 'tier')::int = 1 and (r ->> 'wait')::boolean, 'no second rank today: ' || r::text;
    update public.profiles set tier_up_on = public.rb_today() - 1 where id = a;
    assert public.rb_tier_keep(a) = 2, 'next day: Investor';
    -- a rank reached stays even when the wealth goes
    update public.profiles set coins = 0, tier_up_on = public.rb_today() - 1 where id = a;
    r := public.rb_tier(a);
    assert (r ->> 'tier')::int = 2 and not (r ->> 'wait')::boolean, 'kept: ' || r::text;
    -- 25 000 is not Average any more
    update public.profiles set coins = 30000 where id = b;
    assert (public.rb_tier(b) ->> 'tier')::int = 0, '30 000 is still Poor';

    -- the Key Forge: 12 hour windows and hourly keys
    f := public.rb_forge_state(b);
    assert (f ->> 'resets')::int between 1 and 43200, 'resets within 12 h: ' || f::text;
    assert (f ->> 'hourly')::int = 3 and (f ->> 'hourly_in')::int = 0, 'hourly ready: ' || f::text;
    insert into public.rb_ledger (owner, coins, keys, reason, ref, at)
         values (b, -250, 1, 'forge', '250', public.rb_forge_from() - interval '1 minute');
    assert (public.rb_forge_state(b) ->> 'left')::int = (f ->> 'cap')::int, 'a forge before this half day does not count';
    perform t.act(b);
    k0 := (select keys from public.profiles where id = b);
    r := public.rb_hourly_keys();
    assert (r ->> 'won_keys')::int = 3 and (r ->> 'keys')::int = k0 + 3, 'hourly keys: ' || r::text;
    assert (r -> 'forge' ->> 'hourly_in')::int > 3500, 'next claim in an hour: ' || (r -> 'forge')::text;
    err := t.try('select public.rb_hourly_keys()');
    assert err like '%rb_too_soon%', 'twice in an hour: ' || err;
    reset role;
    update public.profiles set hourly_at = now() - interval '61 minutes' where id = b;
    perform t.act(b);
    r := public.rb_hourly_keys();
    assert (r ->> 'won_keys')::int = 3, 'an hour later: again';

    -- the daily reward is a case
    reset role;
    assert (select bool_and(x ? 'case') from jsonb_array_elements(public.rb_login_rewards()) x),     -- 9.5: and coins
        'a case every day: ' || public.rb_login_rewards()::text;
    k0 := coalesce((select s.n from public.rb_case_stock s where s.owner = b and s.case_id = 'starter'), 0);
    perform t.act(b);
    r := public.rb_login_claim();
    reset role;
    assert (select s.n from public.rb_case_stock s where s.owner = b and s.case_id = 'starter') = k0 + 1, 'day 1: a Starter Case';

    -- the free spin
    r := public.rb_spin_table(1);
    assert (r -> 'slots' ->> 6)::int = 7500 and (r -> 'odds' ->> 0)::int = 1200, 'better spin: ' || r::text;

    -- the reset
    insert into public.rb_items (owner, item, origin) values (a, 'tag:og', 'test'), (a, 'badge:leaf:grey', 'test'), (b, 'badge:leaf:red', 'test');
    insert into public.rb_ach (owner, id) select a, id from public.rb_ach_defs limit 1;
    update public.profiles set xp = 9999, level = 12, gold_keys = 4, streak = 5 where id = a;
    r := public.rb_reset_94();
    assert (r ->> 'players')::int >= 2, 'reset: ' || r::text;
    assert (select count(*) from public.rb_items where owner = a) = 1
       and exists (select 1 from public.rb_items where owner = a and item = 'tag:og'), 'only the OG tag stays';
    assert not exists (select 1 from public.rb_items where owner = b), 'B has nothing';
    assert exists (select 1 from public.rb_items where owner = bt and item = 'tag:og'), 'bots keep their items';
    assert not exists (select 1 from public.rb_ach where owner = a), 'trophies go';
    assert (select coins from public.profiles where id = a) = 2500 and (select keys from public.profiles where id = a) = 5,
        'starter coins and keys';
    assert (select n from public.rb_case_stock where owner = a and case_id = 'starter') = 3
       and (select n from public.rb_case_stock where owner = b and case_id = 'starter') = 3, 'starter cases (old ones gone)';
    assert (select level from public.profiles where id = a) = 0 and (select tier_floor from public.profiles where id = a) = 0
       and (select streak from public.profiles where id = a) = 0 and (select gold_keys from public.profiles where id = a) = 0,
        'level, rank, streak, gold keys';
    assert (select coins from public.profiles where id = bt) = 777, 'bots keep their coins';
    assert public.rb_cfg('stats_from') > 0 and public.rb_cfg('board_from') > 0 and public.rb_cfg('ach_from') > 0, 'boards from now';
    assert to_regclass('public.rb_bak94_profiles') is not null and to_regclass('public.rb_bak94_items') is not null, 'backup';
    assert (select count(*) from public.rb_bak94_items where owner = a) >= 2, 'backup has the old items';
    err := t.try('select public.rb_reset_94()');
    assert err like '%rb_already_done%', 'once: ' || err;
    perform t.act(a);
    err := t.try('select public.rb_reset_94()');
    assert err like '%permission denied%', 'players cannot reset: ' || err;
end $$;
rollback;
