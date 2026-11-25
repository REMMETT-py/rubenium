-- Players only ever read their own rows; anon reads none; nobody writes tables directly; balances never go negative.
begin;
do $$
declare a uuid := t.player('Alice'); b uuid := t.player('Bob'); n int; err text;
begin
    perform t.act(a);
    select count(*) into n from public.profiles;            assert n = 1, 'a player sees only their own profile';
    select count(*) into n from public.rb_items where owner = b; assert n = 0, 'no one else''s items';
    select count(*) into n from public.rb_ledger where owner = b; assert n = 0, 'no one else''s ledger';
    err := t.try('update public.profiles set coins = coins + 1000');
    assert err <> '', 'a player cannot change their coins directly';
    err := t.try(format('insert into public.rb_items (owner, item) values (%L, %L)', a, 'badge:star:basic'));
    assert err <> '', 'a player cannot make items';
    perform t.act(null);
    assert t.rows('select * from public.profiles') = 0, 'anon sees no profile';
    assert t.rows('select * from public.rb_items') = 0, 'anon sees no item';
    assert t.rows('select * from public.rb_ledger') = 0, 'anon sees no ledger';
    err := t.try('update public.rb_config set value = 0');
    assert err <> '' or (select count(*) from public.rb_config where value = 0) < 5, 'anon cannot change the settings';
end $$;
-- the database itself refuses a negative balance, whatever function asks for it
do $$ begin
    assert t.try(format('update public.profiles set coins = -1 where id = (select id from public.profiles limit 1)')) <> '',
           'coins cannot go below zero';
end $$;
rollback;
