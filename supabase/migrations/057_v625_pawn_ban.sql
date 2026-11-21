-- 6.2.5: the pawn shop (quick sell) ban lasts 5 minutes instead of 30. Applied live with the same text swap:
-- rb_pawn_ask and rb_pawn_trade: interval '30 minutes' -> '5 minutes', 'ban_left', 1800 -> 300.
do $$
declare f record; src text;
begin
  for f in select oid, proname from pg_proc where proname in ('rb_pawn_ask','rb_pawn_trade') and pronamespace='public'::regnamespace loop
    src := pg_get_functiondef(f.oid);
    src := replace(src, 'interval ''30 minutes''', 'interval ''5 minutes''');
    src := replace(src, '''ban_left'', 1800', '''ban_left'', 300');
    execute src;
  end loop;
end $$;
