-- Rubenium League: a switch for the admins to close ranked (Admin > Locks, or the admin button in the League lobby).
-- Ranked is played against bots and kept on the player's PC for now, so the app is what honours the lock; practice and
-- Free Play stay open. Safe to run twice. Undo: 096_down.sql.
begin;
insert into public.rb_features (name, parent) values ('league_ranked', 'online') on conflict (name) do nothing;
commit;
