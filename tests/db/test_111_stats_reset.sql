-- 9.3.2 (092): the Stats tab is all time, counted from stats_from; nothing before it shows, the history is still there.
begin;
do $$
declare a uuid := t.player('Statsy'); s jsonb;
begin
    insert into public.rb_rounds (owner, game, bet, paid, open, secret, at) values (a, 'slots', 100, 300, false, '{}', now() - interval '3 days');
    update public.rb_config set value = extract(epoch from now() - interval '1 hour')::bigint where key = 'stats_from';
    s := public.rb_stats_core(a, 0);
    assert (s ->> 'all')::boolean, 'all time';
    assert (s ->> 'days')::int between 1 and 2, 'all time starts at the reset: ' || (s ->> 'days');
    assert s -> 'games' -> 'slots' is null, 'a round before the reset is not counted';
    s := public.rb_stats_core(a, 30);
    assert s -> 'games' -> 'slots' is null, 'an older app''s 30 days stop at the reset too';
    update public.rb_config set value = 0 where key = 'stats_from';
    s := public.rb_stats_core(a, 30);
    assert (s -> 'games' -> 'slots' ->> 'rounds')::int = 1, 'undo brings it back';
    assert exists (select 1 from public.rb_rounds where owner = a), 'nothing deleted';
    if to_regprocedure('public.rb_stats(uuid)') is not null then      -- Records (live only) still answer
        assert (public.rb_stats(a)::jsonb ->> 'rounds')::int = 1, 'records count again after undo';
    end if;
end $$;
rollback;
