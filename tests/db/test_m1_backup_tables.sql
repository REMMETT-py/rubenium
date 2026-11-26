-- The 6.3 backups had no row security (M1, fixed by 074). 9.2 (089) drops every pre-9.0 backup: then nothing to check.
begin;
do $$ begin
    if to_regclass('public.rb_bak63_cases') is null then
        return;
    end if;
    perform t.act(null);
    assert t.try('delete from public.rb_bak63_cases') <> '' or t.rows('select * from public.rb_bak63_cases') = 0,
           'anon may delete the 6.3 case backup';
    assert t.try('insert into public.rb_bak63_case_stock (owner, case_id, n) values (gen_random_uuid(), ''x'', 1)') <> '',
           'anon may write the 6.3 stock backup';
end $$;
rollback;
