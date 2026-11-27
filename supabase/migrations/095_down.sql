-- Undo of 095_v94_kart_times.sql: made by overhaul/db/make_down.py from the server as it was before it.
begin;
drop function if exists public.rb_kart_ghost cascade;
drop function if exists public.rb_kart_ghost_save cascade;
drop function if exists public.rb_kart_times cascade;
drop table if exists public.rb_kart_ghosts;
commit;
