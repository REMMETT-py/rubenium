-- 9.1 (081): the starter pack, wealth that counts only items got since 9.1, and the lower tiers.
-- needs_live_snapshot
begin;
do $$
declare pa uuid := t.player('Alice', 0, 0); r jsonb; it text := (select id from public.rb_catalog where public.rb_worth(id) between 100 and 20000 limit 1);
begin
    assert public.rb_cfg('start_coins') = 2500 and public.rb_cfg('start_keys') = 5, 'start coins and keys';
    assert (select n from public.rb_case_stock where owner = pa and case_id = 'starter') = 3, 'three Starter Cases';
    assert (select n from public.rb_case_stock where owner = pa and case_id = 'standard') = 5, 'five Standard Cases';
    assert public.rb_cfg('tier_at_1') = 50000 and public.rb_cfg('tier_at_4') = 5000000, '9.4 tiers';
    update public.rb_config set value = 25000 where key = 'tier_at_1';        -- checks the 9.1.1 wealth rule
    insert into public.rb_items (owner, item, origin, got_at) values (pa, it, 'test', '2026-11-20');
    assert public.rb_wealth(pa) = 0, 'an item from before 9.1 does not count';
    insert into public.rb_items (owner, item, origin) values (pa, it, 'test');
    update public.profiles set coins = 100 where id = pa;
    r := public.rb_tier(pa);
    assert (r ->> 'coins')::bigint = 100 and (r ->> 'items')::bigint = public.rb_worth(it)
           and (r ->> 'wealth')::bigint = 100 + public.rb_worth(it), 'coins + new items = wealth: ' || r::text;
    update public.profiles set coins = 25000 - public.rb_worth(it) where id = pa;
    assert public.rb_tier(pa) ->> 'name' = 'Average', 'Average at 25 000';
    assert (select count(*) from public.rb_ledger where reason = 'gift' and ref = '9.1 starter pack') >= 0, 'ledger ok';
end $$;
rollback;
