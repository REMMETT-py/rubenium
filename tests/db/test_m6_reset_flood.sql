begin;
do $$
declare i int; err text;
begin
    perform t.act(null);
    for i in 1..300 loop
        perform public.rb_reset_ask('nobody' || i, md5('pc' || i), 'help');
    end loop;
    perform t.player('Victim');
    perform t.act(null);
    err := t.try(format('select public.rb_reset_ask(%L, %L, %L)', 'Victim', md5('victim-pc'), 'I forgot'));
    assert err = '', 'a real player cannot ask for password help: ' || err;
end $$;
rollback;
