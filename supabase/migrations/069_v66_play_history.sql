-- 6.6: every finished round of a player (game, bet, paid, when) for the stats graph. Same privacy as rb_history: yourself, friends, admins.
create or replace function public.rb_play_history(name text, lim integer default 1000) returns jsonb language plpgsql stable security definer set search_path = '' as $f$
declare me uuid := auth.uid(); who uuid;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select id into who from public.profiles where lower(username) = lower(coalesce(nullif(name, ''), (select username from public.profiles where id = me)));
    if who is null then raise exception 'rb_no_such_user'; end if;
    if who <> me and not public.rb_is_friend(me, who) and not (select admin from public.profiles where id = me) then raise exception 'rb_friends_only'; end if;
    return jsonb_build_object('now', extract(epoch from now()), 'rounds', coalesce((
        select jsonb_agg(jsonb_build_object('t', extract(epoch from r.at), 'g', r.game, 'b', r.bet, 'p', coalesce(r.paid, 0)) order by r.at desc)
          from (select * from public.rb_rounds where owner = who and not open order by at desc limit greatest(1, least(coalesce(lim, 1000), 2000))) r), '[]'::jsonb));
end $f$;
revoke all on function public.rb_play_history(text, integer) from public, anon;
grant execute on function public.rb_play_history(text, integer) to authenticated;
