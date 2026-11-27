-- Rubenium 9.5. Safe to run twice. Undo: 096_down.sql.
--
-- Karting: the bot ladder moved up (9.4's Professional is now Expert); Elite and Professional lap faster than the
-- players' fastest possible lap, so the bot's time floor in rb_kart_finish is 80 % of the record (players stay at 94 %).
begin;

create or replace function public.rb_kart_finish(rid uuid, ms integer, laps integer[], best integer, blowups integer,
                                                 hits integer, turbos integer, prog real, is_bot boolean) returns jsonb
language plpgsql security definer set search_path to '' as $$
#variable_conflict use_column
declare me uuid := auth.uid(); r public.rb_kart_rooms%rowtype; s public.rb_kart_seats%rowtype; least_ms integer;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into r from public.rb_kart_rooms where id = rid for update;
    if not found then raise exception 'rb_duel_gone'; end if;
    select * into s from public.rb_kart_seats where room = rid and owner = me;
    if not found then raise exception 'rb_duel_gone'; end if;
    if r.state = 'live' then
        -- 9.5: Elite and Professional bots are faster than any player (stronger engine, more grip): their floor is lower
        least_ms := floor((public.rb_kart_cal(r.track) ->> 'min')::float8 * r.laps * 1000
                          * case when coalesce(is_bot, false) then 0.80 else 0.94 end)::int;
        if ms is not null then
            if ms < least_ms or coalesce(cardinality(rb_kart_finish.laps), 0) <> r.laps
               or abs((select sum(v) from unnest(rb_kart_finish.laps) v) - ms) > 50
               or extract(epoch from (now() - r.go_at)) * 1000 < ms - 2500 then raise exception 'rb_too_fast'; end if;
        end if;
        if coalesce(is_bot, false) then
            if r.bot and r.bot_driver = me and r.bot_ms is null then
                update public.rb_kart_rooms set bot_ms = ms, bot_laps = rb_kart_finish.laps, bot_prog = rb_kart_finish.prog,
                       bot_score = case when ms is not null then public.rb_kart_score(r.track, r.laps, ms) end where id = rid;
            end if;
        elsif s.finish_ms is null and not s.gone then
            update public.rb_kart_seats set finish_ms = ms, laps = rb_kart_finish.laps, best_ms = rb_kart_finish.best, blowups = rb_kart_finish.blowups,
                   hits = rb_kart_finish.hits, turbos = rb_kart_finish.turbos, prog = rb_kart_finish.prog,
                   score = case when ms is not null then public.rb_kart_score(r.track, r.laps, ms) end,
                   gone = ms is null, done_at = now()
             where room = rid and owner = me;
        end if;
        perform public.rb_kart_tick(rid);
    end if;
    return public.rb_kart_json(rid, me);
end $$;

commit;
