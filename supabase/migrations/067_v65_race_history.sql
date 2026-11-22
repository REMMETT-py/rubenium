-- 6.5: the Horse Racing history. Every finished race: when, the finishing order, the pot and what was on each horse.
create or replace function public.rb_race_history(lim integer default 400) returns jsonb language plpgsql stable security definer set search_path = '' as $f$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    return jsonb_build_object('now', extract(epoch from now()), 'races', coalesce((
        select jsonb_agg(x.j order by x.t desc) from (
            select r.done_at t, jsonb_build_object(
                'id', r.id, 't', extract(epoch from r.done_at), 'winner', r.winner, 'places', to_jsonb(r.places), 'total', r.total,
                'bets', coalesce((select jsonb_agg(jsonb_build_object('lane', b.lane, 'amount', b.amount, 'name', coalesce(p.username, b.bot_name),
                                                                  'bot', b.owner is null, 'me', b.owner = me, 'paid', coalesce(b.paid, 0)) order by b.lane)
                                    from public.rb_race_bets b left join public.profiles p on p.id = b.owner where b.race = r.id), '[]'::jsonb)) j
              from public.rb_races r where r.state = 'done' order by r.done_at desc limit greatest(1, least(coalesce(lim, 400), 1000))) x), '[]'::jsonb));
end $f$;
revoke all on function public.rb_race_history(integer) from public, anon;
grant execute on function public.rb_race_history(integer) to authenticated;
