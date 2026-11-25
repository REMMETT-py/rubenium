-- The helpers work: a player can be made, acts as themselves, and anon is anonymous.
begin;
do $$
declare a uuid := t.player('Alice'); me jsonb;
begin
    assert (select coins from public.profiles where id = a) = public.rb_cfg('start_coins'), 'start coins';
    perform t.act(a);
    assert auth.uid() = a, 'auth.uid() is the player';
    assert current_user = 'authenticated', 'runs as authenticated';
    perform t.act(null);
    assert auth.uid() is null and current_user = 'anon', 'anon';
end $$;
rollback;
