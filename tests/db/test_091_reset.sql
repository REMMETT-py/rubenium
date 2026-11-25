-- 9.0 fresh start: coins and keys to the start, cosmetics and levels kept, things in play closed, items returned,
-- needs_live_snapshot (Connect 4 and other tables exist on the live server only)
-- a backup kept, and only once.
begin;
do $$
declare a uuid := t.player('Alice', 90000, 40); b uuid := t.player('Bob', 5000, 2); r jsonb; err text; it uuid;
begin
    update public.profiles set gold_keys = 3, gold_wheels = 2, xp = 5000, level = 7, streak = 5, spin_at = now()
     where id = a;
    insert into public.rb_items (owner, item, origin, locked) values (a, 'frame:firstfrost', 'shop', 'trade:1') returning id into it;
    insert into public.rb_items (owner, item, origin) values (b, 'banner:meadow', 'shop');
    insert into public.rb_rounds (owner, game, bet, secret, open, paid) values (a, 'cups', 100, '{}', true, 0);

    -- players cannot run it
    perform t.act(a);
    err := t.try('select public.rb_reset_economy_90(1000, 3)');
    assert err like '%permission denied%', 'players cannot reset: ' || err;
    reset role;

    r := public.rb_reset_economy_90(1000, 3);
    assert (r ->> 'players')::int >= 2, 'reset ran: ' || r::text;
    assert t.coins(a) = 1000 and t.coins(b) = 1000, 'everyone starts at 1000';
    assert (select keys = 3 and gold_keys = 0 and gold_wheels = 0 and streak = 0 and spin_at is null
              and xp = 5000 and level = 7 from public.profiles where id = a), 'keys reset, level kept';
    assert (select locked is null from public.rb_items where id = it), 'trade item given back';
    assert exists (select 1 from public.rb_items where owner = b and item = 'banner:meadow'), 'cosmetics kept';
    assert not exists (select 1 from public.rb_rounds where owner = a and open), 'open rounds closed';
    assert (select coins from public.rb_bak90_profiles where id = a) = 90000, 'backup kept';
    err := t.try('select public.rb_reset_economy_90(1000, 3)');
    assert err like '%rb_already_done%', 'only once: ' || err;
end $$;
rollback;
