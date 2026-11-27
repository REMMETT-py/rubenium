-- Rubenium 10.0 undo: no more Hoops online rooms. The reset is not undone here: every table it changed was copied
-- first to rb_bak100_* (kept by this file), which is how a player is put back by hand.
begin;

drop function if exists public.rb_hoops_ping(uuid, jsonb);
drop function if exists public.rb_hoops_room_end(uuid);
drop function if exists public.rb_hoops_room_leave(uuid);
drop function if exists public.rb_hoops_room_state(uuid);
drop function if exists public.rb_hoops_room_join(uuid);
drop function if exists public.rb_hoops_room_create(text, text, integer);
drop function if exists public.rb_hoops_rooms();
drop function if exists public.rb_hoops_busy(uuid);
drop function if exists public.rb_hoops_room_json(uuid, uuid);
drop function if exists public.rb_hoops_room_tick(uuid);
drop function if exists public.rb_reset_10();
drop table if exists public.rb_hoops_live;
drop table if exists public.rb_hoops_rooms;

commit;
