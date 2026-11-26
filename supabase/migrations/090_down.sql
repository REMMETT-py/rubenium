-- Undo of 090_v921_caps.sql: every function goes back to its 9.2 version, the new settings and functions go, and the
-- Key Forge uses a day go back to 3, 5, 8, 12, 20.
begin;
CREATE OR REPLACE FUNCTION public.rb_tier(who uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare c bigint := coalesce((select coins from public.profiles where id = who), 0);
        it bigint := public.rb_wealth_items(who); w bigint := c + it; t integer := 0; i integer; fl integer;
begin
    for i in 1 .. 4 loop
        if w >= coalesce(public.rb_cfg('tier_at_' || i), 1e18) then t := i; end if;
    end loop;
    fl := least(4, greatest(0, coalesce((select tier_floor from public.profiles where id = who), 0)));
    t := greatest(t, fl);
    return jsonb_build_object('tier', t, 'name', (array['Poor', 'Average', 'Investor', 'Businessman', 'Casino Legend'])[t + 1],
                              'mult', coalesce(public.rb_cfg('tier_x_' || t), 1), 'wealth', w, 'coins', c, 'items', it,
                              'at', case when t > 0 then public.rb_cfg('tier_at_' || t) else 0 end,
                              'next', case when t < 4 then public.rb_cfg('tier_at_' || (t + 1)) end,
                              'next_name', case when t < 4 then (array['Poor', 'Average', 'Investor', 'Businessman',
                                                                      'Casino Legend'])[t + 2] end,
                              'top', 4);
end $function$
;

CREATE OR REPLACE FUNCTION public.rb_my_tier()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_tier_keep(auth.uid());
    return public.rb_tier(auth.uid()) || jsonb_build_object('forge', public.rb_forge_state(auth.uid()));
end $function$
;

CREATE OR REPLACE FUNCTION public.rb_game_window(who uuid, g text)
 RETURNS json
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select json_build_object('rounds', count(*), 'paid', coalesce(sum(paid), 0),
                             'cap', coalesce(public.rb_cfg('game_day_cap'), 1500), 'full', public.rb_cfg('game_full_rounds'),
                             'resets', greatest(0, ceil(extract(epoch from (((public.rb_today() + 1)::timestamp at time zone 'Europe/Paris') - now()))))::int,
                             'daily', true)
      from public.rb_rounds where owner = who and game = g and not open
       and at >= (public.rb_today()::timestamp at time zone 'Europe/Paris') $function$
;

CREATE OR REPLACE FUNCTION public.rb_game_pay(who uuid, g text, pay integer)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare w json := public.rb_game_window(who, g); n integer := (w ->> 'rounds')::int; fr integer := (w ->> 'full')::int;
        m numeric := public.rb_level_mult(who) * public.rb_tier_mult(who); got integer;
begin
    pay := round(pay * coalesce(public.rb_cfg('game_pay_mult'), 1) * m);
    if n >= fr * 2 then pay := pay / 4; elsif n >= fr then pay := pay / 2; end if;
    got := greatest(0, least(pay, floor((w ->> 'cap')::int * m)::int - (w ->> 'paid')::int));
    if got > 0 then perform public.rb_key_find(who, g); end if;
    return got;
end $function$
;

CREATE OR REPLACE FUNCTION public.rb_key_find(who uuid, g text)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    if public.rb_rand() * 100 >= coalesce(public.rb_cfg('key_find_pct'), 0) then return 0; end if;
    if exists (select 1 from public.profiles where id = who and bot) then return 0; end if;
    if public.rb_keys_today(who) >= coalesce(public.rb_cfg('key_find_day'), 6) then return 0; end if;
    perform public.rb_pay(who, 0, 1, 'key_found', g);
    perform public.rb_notice(who, 'key_found', jsonb_build_object('game', g, 'keys', 1));
    return 1;
end $function$
;

CREATE OR REPLACE FUNCTION public.rb_golf_cap(coins bigint)
 RETURNS integer
 LANGUAGE sql
 STABLE
 SET search_path TO ''
AS $function$
    select (least(coalesce(public.rb_cfg('duel_max_bet'), 5000), floor(coins * 0.8)) / 10 * 10)::int $function$
;

CREATE OR REPLACE FUNCTION public.rb_heartbeat(device text)
 RETURNS json
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare
    p public.profiles%rowtype;
    credited boolean := false; elsewhere boolean := false;
    got_coins integer := 0; got_keys integer := 0; m numeric;
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_bots_tick(); perform public.rb_flip_cleanup(auth.uid());
    update public.profiles set bot_real_at = now() where id = auth.uid() and bot;
    select * into p from public.profiles where id = auth.uid() for update;
    if not found then raise exception 'rb_no_profile'; end if;
    if p.banned then raise exception 'rb_banned'; end if;
    device := left(coalesce(device, ''), 64);
    if p.last_beat is not null and p.beat_device is distinct from device
       and now() - p.last_beat < interval '150 seconds' then
        elsewhere := true;
    elsif p.last_beat is null or now() - p.last_beat >= interval '55 seconds' then
        credited := p.last_beat is not null and now() - p.last_beat < interval '150 seconds';
        if credited then
            p.minutes := p.minutes + 1; if p.minutes % 10 = 0 then perform public.rb_xp_add(p.id, 5, 'online', null, true); end if; perform public.rb_wear_add(p.id, p.equip ->> 'banner'); p.coin_min := p.coin_min + 1; p.key_min := p.key_min + 1;
            if p.day <> current_date then p.day := current_date; p.day_coins := 0; end if;
            if p.coin_min >= public.rb_cfg('coin_every_min') then
                p.coin_min := 0;
                m := public.rb_tier_mult(p.id);
                if p.day_coins < (public.rb_cfg('coin_day_cap') + public.rb_streak_bonus(p) * 72) * m then
                    got_coins := public.rb_scaled(public.rb_cfg('coin_amount')::int + public.rb_streak_bonus(p), m);
                    p.day_coins := p.day_coins + got_coins;
                end if;
            end if;
            if p.key_min >= public.rb_cfg('key_every_min') then
                p.key_min := 0;
                if p.keys < public.rb_cfg('key_cap') then got_keys := 1; end if;
            end if;
        end if;
        update public.profiles set minutes = p.minutes, coin_min = p.coin_min, key_min = p.key_min, day = p.day,
               day_coins = p.day_coins, last_beat = now(), beat_device = device where id = p.id;
        perform public.rb_pay(p.id, got_coins, got_keys, 'time', null);
    end if;
    return json_build_object('username', p.username, 'minutes', p.minutes, 'credited', credited,
                             'elsewhere', elsewhere, 'coins', p.coins + got_coins, 'keys', p.keys + got_keys,
                             'got_coins', got_coins, 'got_keys', got_keys, 'coin_min', p.coin_min, 'key_min', p.key_min,
                             'day_coins', p.day_coins);
end $function$
;

CREATE OR REPLACE FUNCTION public.rb_kart_settle(rid uuid)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare r public.rb_kart_rooms%rowtype; s record; n_h integer; k integer; pr integer; xp_ integer; cap integer;
        beat_h integer; beat_bot boolean; bot_t double precision;
begin
    select * into r from public.rb_kart_rooms where id = rid for update;
    if not found or r.state <> 'live' then return; end if;
    -- how far round the unfinished karts got (from their last live position)
    update public.rb_kart_seats ks set prog = coalesce(ks.prog, (select (l.snap ->> 11)::real from public.rb_kart_live l where l.room = rid and l.seat = ks.seat))
     where ks.room = rid and ks.finish_ms is null;
    if r.bot and r.bot_ms is null then
        r.bot_prog := (select (l.snap ->> 11)::real from public.rb_kart_live l where l.room = rid and l.seat = 3);
        update public.rb_kart_rooms set bot_prog = r.bot_prog where id = rid;
    end if;
    -- places: finished karts by time (the bot too), then the rest by how far round they got
    bot_t := case when r.bot and r.bot_ms is not null then r.bot_ms else null end;
    k := 0;
    for s in with all_ as (
                select ks.owner, ks.finish_ms::float8 ms, coalesce(ks.prog, 0) prog, ks.gone from public.rb_kart_seats ks where ks.room = rid
                union all
                select null::uuid, bot_t, coalesce(r.bot_prog, 0), false where r.bot)
             select * from all_ order by (ms is null), ms, gone, prog desc loop
        k := k + 1;
        if s.owner is null then
            update public.rb_kart_rooms set bot_place = k where id = rid;
        else
            update public.rb_kart_seats set place = k where room = rid and owner = s.owner;
        end if;
    end loop;
    select count(*) into n_h from public.rb_kart_seats where room = rid;
    select bot_place into r.bot_place from public.rb_kart_rooms where id = rid;
    for s in select * from public.rb_kart_seats where room = rid order by seat loop
        if s.finish_ms is null or s.gone then continue; end if;
        -- the prize: finishing, the score, each player and the bot beaten (the bot by its level), first place, a clean race
        beat_h := (select count(*) from public.rb_kart_seats o where o.room = rid and o.owner <> s.owner and o.place > s.place);
        beat_bot := r.bot and r.bot_place is not null and r.bot_place > s.place;
        pr := 20 + floor(coalesce(s.score, 0) * 0.8)::int + 40 * beat_h
              + case when beat_bot then floor(10 + 190 * power(r.bot_elo / 2500.0, 2))::int else 0 end
              + case when s.place = 1 and n_h + (case when r.bot then 1 else 0 end) > 1 then 40 else 0 end
              + case when coalesce(s.blowups, 0) = 0 then 20 else 0 end;
        pr := floor(pr * least(1.0, r.laps / 3.0))::int;                       -- shorter races pay less
        cap := coalesce(public.rb_cfg('kart_cap'), 2500)::int;
        pr := greatest(0, least(pr, cap - public.rb_kart_paid_today(s.owner)));
        xp_ := 20 + 10 * beat_h + case when beat_bot then 10 else 0 end;
        if pr > 0 then perform public.rb_pay(s.owner, pr, 0, 'kart', rid::text); end if;
        perform public.rb_xp_add(s.owner, xp_, 'kart', rid::text);
        update public.rb_kart_seats set paid = pr, xp = xp_ where room = rid and owner = s.owner;
    end loop;
    update public.rb_kart_rooms set state = 'done', done_at = now(), why = coalesce(why, 'finished') where id = rid;
    delete from public.rb_kart_live where room = rid;
end $function$
;

CREATE OR REPLACE FUNCTION public.rb_kart_lobbies()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare me uuid := auth.uid(); o record; cur uuid;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    for o in select id from public.rb_kart_rooms where state in ('open', 'live') loop
        perform public.rb_kart_tick(o.id);
    end loop;
    select r.id into cur from public.rb_kart_seats s join public.rb_kart_rooms r on r.id = s.room
     where s.owner = me and not s.gone and r.state in ('open', 'live') order by r.at desc limit 1;
    return jsonb_build_object(
        'mine', case when cur is not null then public.rb_kart_json(cur, me) end,
        'today', public.rb_kart_paid_today(me), 'cap', coalesce(public.rb_cfg('kart_cap'), 2500),
        'best', coalesce((select jsonb_object_agg(t, b) from (
                    select r.track t, max(s.score) b from public.rb_kart_seats s join public.rb_kart_rooms r on r.id = s.room
                     where s.owner = me and s.score is not null and r.state = 'done' group by r.track) z), '{}'::jsonb),
        'top', coalesce((select jsonb_agg(z order by z.t, z.rk) from (
                    select r.track t, p.username name, max(s.score) score, min(s.finish_ms) filter (where r.laps = 3) ms,
                           rank() over (partition by r.track order by max(s.score) desc) rk
                      from public.rb_kart_seats s join public.rb_kart_rooms r on r.id = s.room join public.profiles p on p.id = s.owner
                     where s.score is not null and r.state = 'done' and not p.banned and s.at >= public.rb_board_from()
                     group by r.track, p.username) z where z.rk <= 5), '[]'::jsonb),
        'rooms', coalesce((select jsonb_agg(jsonb_build_object('id', r.id, 'host', u.username, 'size', r.size,
                        'track', r.track, 'laps', r.laps, 'bot_elo', r.bot_elo, 'collide', r.collide,
                        'seated', (select count(*) from public.rb_kart_seats s where s.room = r.id),
                        'friend', public.rb_is_friend(me, r.host)) order by r.at)
                   from public.rb_kart_rooms r join public.profiles u on u.id = r.host
                  where r.state = 'open' and r.size > 1 and not u.banned), '[]'::jsonb));
end $function$
;

drop function if exists public.rb_tier_seen(integer);
drop function if exists public.rb_tier_perks();
drop function if exists public.rb_tier_perk(integer);
drop function if exists public.rb_kart_cap(uuid);
drop function if exists public.rb_day_cap(numeric, integer, numeric);
drop function if exists public.rb_tier_cfg(text, integer, numeric);
delete from public.rb_config where key ~ '^(cap_x|key_cap|key_find_day|duel_max_bet)_[0-4]$';
update public.rb_config c set value = v.value
  from (values ('forge_day_0', 3), ('forge_day_1', 5), ('forge_day_2', 8), ('forge_day_3', 12), ('forge_day_4', 20)) as v(key, value)
 where c.key = v.key;
alter table public.profiles drop column if exists tier_seen;
commit;
