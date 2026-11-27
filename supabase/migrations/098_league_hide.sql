-- Rubenium League (flat top-down mode): a switch for the admins to hide the whole game from players (Admin > Locks,
-- or the admin button in the League lobby). Admins still see it. As the owner decided for 10.0, it starts hidden for
-- players while the top bots are tuned; an admin turns it on from Admin > Locks. Safe to run twice (a second run does
-- not hide it again once an admin has turned it on). Undo: 098_league_down.sql.
begin;
insert into public.rb_features (name, parent, locked, at, note)
values ('league', 'online', true, now(), 'Hidden at release while the top bots are tuned')
on conflict (name) do nothing;
commit;
