-- 7.0: the horse race is longer (a 4 times longer track, the race proper lasts 120 s instead of 30 s).
-- Lock -> gun is 7 s, the rolling start 3 s, so the race is over (done_at) 134 s after the lock.
do $m$
declare s text;
begin
    s := pg_get_functiondef('public.rb_race_advance(uuid)'::regprocedure);
    if position('''134 seconds''' in s) = 0 then
        s := replace(s, 'done_at = r.lock_at + interval ''74 seconds''', 'done_at = r.lock_at + interval ''134 seconds''');
        execute s;
    end if;
end $m$;
