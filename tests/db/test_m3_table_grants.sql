begin;
do $$
declare bad text;
begin
    select string_agg(distinct table_name, ', ') into bad from information_schema.role_table_grants
     where table_schema = 'public' and grantee in ('anon', 'authenticated')
       and privilege_type in ('INSERT', 'UPDATE', 'DELETE', 'TRUNCATE');
    assert bad is null, 'API roles may write: ' || bad;
end $$;
rollback;
