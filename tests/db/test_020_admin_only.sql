-- Every admin function refuses a normal player, whatever arguments it gets.
begin;
create temp table r (f text, err text);
grant all on r to authenticated;
do $$
declare a uuid := t.player('Alice'); f record; args text;
begin
    perform t.act(a);
    for f in select p.oid::regprocedure::text sig, p.proname, p.pronargs from pg_proc p
              where p.pronamespace = 'public'::regnamespace and p.proname like 'rb\_admin\_%'
                and has_function_privilege('authenticated', p.oid, 'execute') loop
        select string_agg('null', ', ') into args from generate_series(1, f.pronargs);
        insert into r values (f.sig, t.try(format('select public.%I(%s)', f.proname, coalesce(args, ''))));
    end loop;
end $$;
reset role;
do $$
declare bad text;
begin
    select string_agg(f || ' -> ' || coalesce(nullif(err, ''), 'WORKED'), '; ') into bad from r where err not like '%rb_not_admin%';
    assert bad is null, 'admin functions open to players: ' || bad;
    assert (select count(*) from r) >= 50, 'expected the admin functions to be found';
end $$;
rollback;
