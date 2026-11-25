-- 8.0: the admin's second step.
begin;
-- Every admin function starts with rb_need_admin(); this stand-in calls it the same way (the live server's admin
-- functions are not all in the repo's old migrations).
create function t.admin_call() returns uuid language sql security definer set search_path = '' as $f$
    select public.rb_need_admin() $f$;
grant usage on schema t to authenticated;
grant execute on function t.admin_call() to authenticated;
do $$
declare boss uuid := t.player('Boss'); other uuid := t.player('Boss2'); pl uuid := t.player('Plain'); j json; i int;
begin
    update public.profiles set admin = true where id in (boss, other);
    perform t.act(boss);
    perform t.admin_call();                                   -- no code yet: as before
    assert (public.rb_admin_step_status() ->> 'set')::boolean = false;
    assert t.try('select public.rb_admin_step_set(null, ''12345'')') <> '', 'a 5-character code was accepted';
    j := public.rb_admin_step_set(null, 'correct horse');
    assert (j ->> 'ok')::boolean, j::text;
    perform t.admin_call();                                   -- just set: ok for 30 minutes
    reset role;
    update public.rb_admin_step set ok_until = now() - interval '1 second' where owner = boss;
    perform t.act(boss);
    assert t.try('select t.admin_call()') like '%rb_admin_step%', 'expired step still accepted';
    for i in 1..5 loop
        j := public.rb_admin_step_check('wrong');
        assert not (j ->> 'ok')::boolean;
    end loop;
    assert t.try('select public.rb_admin_step_check(''correct horse'')') like '%rb_slow_down%', 'no lock after 5 wrong codes';
    assert t.try('select public.rb_admin_step_set(''correct horse'', ''new code 1'')') like '%rb_slow_down%', 'change allowed while locked';
    reset role;
    update public.rb_admin_step set locked_until = now() - interval '1 second' where owner = boss;
    perform t.act(boss);
    j := public.rb_admin_step_check('correct horse');
    assert (j ->> 'ok')::boolean, j::text;
    perform t.admin_call();
    -- changing it needs the old code
    j := public.rb_admin_step_set('not it', 'another code');
    assert not (j ->> 'ok')::boolean, 'changed without the old code';
    -- another login (session) of the same admin is not covered by this step
    perform set_config('request.jwt.claims', json_build_object('sub', boss, 'role', 'authenticated', 'session_id', 'other-session')::text, true);
    assert t.try('select t.admin_call()') like '%rb_admin_step%', 'step carried over to another login';
    -- players never get in
    perform t.act(pl);
    assert t.try('select public.rb_admin_step_check(''x'')') like '%rb_not_admin%';
    assert t.try('select public.rb_admin_step_set(null, ''abcdefgh'')') like '%rb_not_admin%';
    assert t.try('select t.admin_call()') like '%rb_not_admin%';
    -- admin_step_all: admins without a code are refused
    perform t.act(other);
    perform t.admin_call();
    reset role;
    update public.rb_config set value = 1 where key = 'admin_step_all';
    perform t.act(other);
    assert t.try('select t.admin_call()') like '%rb_admin_step%', 'admin_step_all ignored';
    -- nobody reads the codes
    assert t.rows('select * from public.rb_admin_step') = 0, 'the code table can be read';
end $$;
rollback;
