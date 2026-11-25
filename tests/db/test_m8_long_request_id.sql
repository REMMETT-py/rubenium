begin;
do $$
declare a uuid := t.player('Dicer', 100000); r1 jsonb; r2 jsonb; req text := repeat('x', 80);
begin
    perform t.act(a);
    r1 := public.rb_dice(100, 50, req);
    r2 := public.rb_dice(100, 50, req);
    assert r1 = r2, 'the same request played twice';
end $$;
rollback;
