-- Undo of 098_league_hide.sql.
begin;
delete from public.rb_features where name = 'league';
commit;
