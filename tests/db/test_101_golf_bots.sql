-- 9.2 (087): Mini Golf bots with a level picked by the room, strokes from the physics-worked odds.
-- needs_live_snapshot
begin;
do $$
declare pa uuid := t.player('Golfer', 5000, 0); r jsonb; pid uuid; pl jsonb; n integer; ones integer := 0; k integer;
begin
    assert (select count(*) from public.rb_golf_bot_odds) = 240, 'odds for 60 holes x 4 levels';
    assert not exists (select 1 from public.rb_golf_bot_odds where (select sum(x) from unnest(p) x) not between 95 and 105),
        'every row adds up to about 100%';
    -- Professional gets far more holes in one than Easy over the whole course
    assert (select sum(p[1]) from public.rb_golf_bot_odds where level = 'pro')
           > 2 * (select sum(p[1]) from public.rb_golf_bot_odds where level = 'easy'), 'Professional aces more';
    assert (select avg((select sum(i * p[i]) from generate_series(1, 6) i)) from public.rb_golf_bot_odds where level = 'pro')
           < (select avg((select sum(i * p[i]) from generate_series(1, 6) i)) from public.rb_golf_bot_odds where level = 'hard')
       and (select avg((select sum(i * p[i]) from generate_series(1, 6) i)) from public.rb_golf_bot_odds where level = 'hard')
           < (select avg((select sum(i * p[i]) from generate_series(1, 6) i)) from public.rb_golf_bot_odds where level = 'medium')
       and (select avg((select sum(i * p[i]) from generate_series(1, 6) i)) from public.rb_golf_bot_odds where level = 'medium')
           < (select avg((select sum(i * p[i]) from generate_series(1, 6) i)) from public.rb_golf_bot_odds where level = 'easy'),
        'each level plays better than the one below';
    -- a plan follows the odds: on a hole where Professional always aces, it aces (mirrored holes too)
    k := (select hole from public.rb_golf_bot_odds where level = 'pro' and p[1] = 100 order by hole limit 1);
    for i in 1 .. 20 loop
        pl := public.rb_party_bot_plan2(k + 100 * (i % 2), 3);
        if (pl ->> 'n')::int = 1 then ones := ones + 1; end if;
    end loop;
    assert ones = 20 and (pl ->> 'level')::int = 3, 'Professional aces hole ' || k;
    -- a room with Professional bots
    perform t.act(pa);
    r := public.rb_party_create(4, 0, 3, 3);
    reset role;
    pid := (r ->> 'id')::uuid;
    assert (r ->> 'bot_level')::int = 3, 'the room keeps its bot level: ' || r::text;
    perform public.rb_party_start(pid);
    assert (select count(*) from public.rb_golf_party_seats where party = pid and owner is null and skill = 3 and (plan ->> 'level')::int = 3) = 3,
        'three Professional bots with plans';
    -- the old call still opens a room (Medium bots)
    perform t.act(pa);
    perform public.rb_party_leave(pid);
    r := public.rb_party_create(2, 0, 3);
    reset role;
    assert (r ->> 'bot_level')::int = 1, 'old call: Medium bots';
end $$;
rollback;
