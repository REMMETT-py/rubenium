begin;
do $$ begin
    perform t.act(null);
    assert t.try('delete from public.rb_bak63_cases') <> '' or t.rows('select * from public.rb_bak63_cases') = 0,
           'anon may delete the 6.3 case backup';
    assert t.try('insert into public.rb_bak63_case_stock (owner, case_id, n) values (gen_random_uuid(), ''x'', 1)') <> '',
           'anon may write the 6.3 stock backup';
end $$;
rollback;
