-- Undo of 096_league_lock.sql.
begin;
delete from public.rb_features where name = 'league_ranked';
commit;
