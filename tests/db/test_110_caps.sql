-- needs_live_snapshot
-- 9.2.1 (091): the daily caps follow the wealth tier (Casino Legend has none), the biggest duel bet and the keys follow
-- it too, nothing the app sends can raise a cap, and the rank-up screen's 'seen' tier never goes above the real tier.
begin;
do $$
declare poor uuid := t.player('CapPoor', 1000, 0); leg uuid := t.player('CapLegend', 1000, 0);
        r jsonb; w json; perks jsonb; got integer; err text; k0 integer; c0 bigint;
begin
    update public.profiles set tier_floor = 4 where id = leg;

    -- what every tier gets: five rows, caps grow with the tier, Casino Legend has no daily cap
    perks := public.rb_tier_perks();
    assert jsonb_array_length(perks) = 5, 'five tiers: ' || perks::text;
    assert (perks -> 0 ->> 'mini_cap')::bigint = 6000, 'Poor: 3 000 x2 a game a day: ' || (perks -> 0)::text;
    assert (perks -> 0 ->> 'kart_cap')::bigint = 5000, 'Poor: kart 2 500 x2: ' || (perks -> 0)::text;
    assert (perks -> 1 ->> 'mini_cap')::bigint > (perks -> 0 ->> 'mini_cap')::bigint
       and (perks -> 2 ->> 'mini_cap')::bigint > (perks -> 1 ->> 'mini_cap')::bigint
       and (perks -> 3 ->> 'mini_cap')::bigint > (perks -> 2 ->> 'mini_cap')::bigint, 'mini caps grow: ' || perks::text;
    assert perks -> 4 ->> 'mini_cap' is null and perks -> 4 ->> 'kart_cap' is null and perks -> 4 ->> 'afk_cap' is null,
        'Casino Legend: no daily caps: ' || (perks -> 4)::text;
    assert (perks -> 4 ->> 'key_cap')::int = 50 and (perks -> 4 ->> 'forge')::int = 40
       and (perks -> 4 ->> 'duel_max')::int = 150000, 'Legend keys, forge and duel bet: ' || (perks -> 4)::text;
    assert (select bool_and((perks -> i ->> 'duel_max')::int < (perks -> (i + 1) ->> 'duel_max')::int) from generate_series(0, 3) i),
        'duel bets grow';

    -- mini games: Poor is capped at 6 000 a game a day (x level x tier), Casino Legend never is
    w := public.rb_game_window(poor, 'tap');
    assert (w ->> 'cap')::bigint = 6000, 'Poor window cap: ' || w::text;
    w := public.rb_game_window(leg, 'tap');
    assert (w ->> 'cap')::bigint >= 1000000000, 'Legend: no cap (the app shows "no daily limit"): ' || w::text;
    insert into public.rb_rounds (owner, game, bet, secret, open, paid)
         values (poor, 'tap', 0, '{}'::jsonb, false, 6000), (leg, 'tap', 0, '{}'::jsonb, false, 500000);
    got := public.rb_game_pay(poor, 'tap', 100);
    assert got = 0, 'Poor over the cap: nothing: ' || got;
    got := public.rb_game_pay(leg, 'tap', 100);
    assert got > 0, 'Legend after 500 000 today: still paid: ' || got;

    -- the app cannot call the cap helpers
    perform t.act(poor);
    err := t.try('select public.rb_day_cap(1, 0, 1)');
    assert err like '%permission denied%', 'rb_day_cap is server only: ' || err;
    err := t.try('select public.rb_kart_cap(auth.uid())');
    assert err like '%permission denied%', 'rb_kart_cap is server only: ' || err;
    -- the biggest duel bet follows your tier (and 80% of your coins)
    reset role;
    update public.profiles set coins = 20000 where id = poor;
    update public.profiles set coins = 1000000 where id = leg;
    perform t.act(poor);
    assert (public.rb_wroom_lobbies() ->> 'cap')::int = 10000, 'Poor duel cap: ' || public.rb_wroom_lobbies()::text;
    r := public.rb_kart_lobbies();
    assert (r ->> 'cap')::bigint = 5000 and not (r ->> 'nocap')::boolean, 'Poor kart cap: ' || (r - 'top' - 'rooms')::text;
    -- the rank-up screen: never above the real tier
    r := public.rb_tier_seen(4);
    assert (r ->> 'seen')::int = 0, 'Poor cannot mark Casino Legend seen: ' || r::text;
    r := public.rb_my_tier();
    assert (r ->> 'seen')::int = 0 and jsonb_array_length(r -> 'perks') = 5 and (r ->> 'cap_x')::numeric = 2,
        'my tier says seen, cap_x and perks: ' || (r - 'perks')::text;
    reset role;
    perform t.act(leg);
    assert (public.rb_wroom_lobbies() ->> 'cap')::int = 150000, 'Legend duel cap: ' || public.rb_wroom_lobbies()::text;
    r := public.rb_kart_lobbies();
    assert r -> 'cap' = 'null'::jsonb and (r ->> 'nocap')::boolean, 'Legend kart: no cap: ' || (r - 'top' - 'rooms')::text;
    r := public.rb_tier_seen(4);
    assert (r ->> 'seen')::int = 4, 'Legend seen: ' || r::text;
    reset role;
    perform set_config('request.jwt.claims', '{}', true);                  -- nobody, as in the bots' tick
    assert public.rb_golf_cap(1000000) = 5000, 'nobody (bots): the base cap';
    assert public.rb_golf_cap(5000) = 4000, '80% of the coins still holds: ' || public.rb_golf_cap(5000);

    -- AFK: a Legend gets coins and keys well past the old caps; Poor stops at its own
    update public.profiles set last_beat = now() - interval '60 seconds', beat_device = 'pc', day = current_date,
           coin_min = 100, key_min = 100, day_coins = 50000, keys = 40 where id in (poor, leg);
    perform t.act(leg);
    k0 := (select keys from public.profiles where id = leg);
    c0 := t.coins(leg);
    r := public.rb_heartbeat('pc')::jsonb;
    reset role;
    assert (r ->> 'got_coins')::int > 0 and (r ->> 'got_keys')::int = 1, 'Legend AFK uncapped: ' || r::text;
    perform t.act(poor);
    r := public.rb_heartbeat('pc')::jsonb;
    reset role;
    assert (r ->> 'got_coins')::int = 0 and (r ->> 'got_keys')::int = 0, 'Poor AFK capped: ' || r::text;
    update public.profiles set last_beat = now() - interval '60 seconds', coin_min = 100, key_min = 100, day_coins = 4000,
           keys = 12 where id = poor;
    perform t.act(poor);
    r := public.rb_heartbeat('pc')::jsonb;
    reset role;
    assert (r ->> 'got_coins')::int > 0 and (r ->> 'got_keys')::int = 0,
        'Poor: 4 000 AFK coins is under the new 4 800 cap; 12 keys is over 10: ' || r::text;
end $$;
rollback;
