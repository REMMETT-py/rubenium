-- Rubenium 9.5 undo: back to 9.4's functions.
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
        least_ms := floor((public.rb_kart_cal(r.track) ->> 'min')::float8 * r.laps * 1000 * 0.94)::int;
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


-- economy back to 9.4
insert into public.rb_config (key, value) values ('bet_max', 1000), ('bet_rich_pct', 50), ('bet_max_rich', 2000000000)
on conflict (key) do update set value = excluded.value;
delete from public.rb_config where key in ('topup_0', 'topup_1', 'topup_2', 'topup_3', 'topup_4');
drop function if exists public.rb_topup();
drop function if exists public.rb_topup_state();
drop function if exists public.rb_topup_floor(uuid);
alter table public.profiles drop column if exists topup_day;

CREATE OR REPLACE FUNCTION public.rb_login_rewards()
 RETURNS jsonb
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO ''
AS $function$
    select '[{"coins":300,"case":"starter"},{"coins":400,"case":"standard"},{"coins":500,"case":"nature"},
             {"coins":600,"case":"standard"},{"coins":800,"case":"premium"},{"coins":1000,"case":"medieval"},
             {"coins":1500,"case":"painter"}]'::jsonb $function$;

CREATE OR REPLACE FUNCTION public.rb_login_claim()
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; s integer; r jsonb; c integer; k integer;
begin
    perform public.rb_need_feature('quests');
    p := public.rb_lock_me();
    if p.streak_day = public.rb_today() then raise exception 'rb_wait'; end if;
    s := case when p.streak_day = public.rb_today() - 1 then p.streak + 1 else 1 end;
    r := public.rb_login_rewards_for(public.rb_tier_mult(p.id) * public.rb_login_streak_x(s)) -> ((s - 1) % 7);
    c := coalesce((r ->> 'coins')::int, 0); k := coalesce((r ->> 'keys')::int, 0);
    update public.profiles set streak = s, streak_day = public.rb_today() where id = p.id;
    perform public.rb_pay(p.id, c, k, 'login', s::text);
    if r ? 'case' then perform public.rb_stock_add(p.id, r ->> 'case', 1); end if;
    return jsonb_build_object('streak', s, 'reward', r, 'coins', p.coins + c, 'keys', p.keys + k);
end $function$;

CREATE OR REPLACE FUNCTION public.rb_login_state()
 RETURNS json
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; s integer; nxt integer;
begin
    select * into p from public.profiles where id = auth.uid();
    if not found then raise exception 'rb_not_logged_in'; end if;
    s := case when p.streak_day = public.rb_today() then p.streak
              when p.streak_day = public.rb_today() - 1 then p.streak else 0 end;
    nxt := case when p.streak_day = public.rb_today() then s else s + 1 end;    -- the day the tiles show
    return json_build_object('streak', s, 'claimed', p.streak_day = public.rb_today(),
                             'day', case when p.streak_day = public.rb_today() then (s - 1) % 7 else s % 7 end,
                             'bonus', round((public.rb_login_streak_x(nxt) - 1) * 100),
                             'rewards', public.rb_login_rewards_for(public.rb_tier_mult(p.id) * public.rb_login_streak_x(nxt)));
end $function$;

CREATE OR REPLACE FUNCTION public.rb_quest_rows(who uuid)
 RETURNS TABLE(quest text, kind text, goal integer, reward integer, progress integer, period timestamp with time zone, left_s integer)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    with r as (select game, bet, paid, at from public.rb_rounds
                where owner = who and not open and at >= greatest(date_trunc('week', now()), public.rb_board_from())),
         d as (select * from r where at >= date_trunc('day', now())),
         h as (select * from r where at >= date_trunc('hour', now())),
         t0 as (select greatest(date_trunc('hour', now()), public.rb_board_from()) h,
                       greatest(date_trunc('day', now()), public.rb_board_from()) d,
                       greatest(date_trunc('week', now()), public.rb_board_from()) w),
         casino (g) as (values ('slots'), ('plinko'), ('dice'), ('mines'), ('rocket'), ('blackjack'), ('roulette'), ('hilo'), ('tower')),
         skill (g) as (values ('timing'), ('cups'), ('c4'), ('colour'), ('sfx')),
         pool (quest, goal, reward, progress) as (values
            ('h_rounds', 3, 25, (select count(*) from h where game in (select g from casino))::int),
            ('h_mini',   1, 25, (select count(*) from h where (game in ('mini', 'park', 'memory', 'blocks', 'sweeper', 'golf_solo', 'golf_party', 'wave') or (game in (select g from skill) and paid > 0)))::int),
            ('h_case',   1, 30, (select count(*) from h where game like 'case:%' or game = 'daily')::int),
            ('h_bet',  100, 25, (select coalesce(sum(bet), 0) from h where game in (select g from casino))::int)),
         -- 9.5: the bot challenges, one of each length, taking turns between Karting, Hoops and the Arena
         bots (quest, kind, goal, reward, progress, turn) as (values
            ('hb_kart',  'hour', 1,   500, public.rb_bot_kart_wins(who, 500, (select h from t0)), 0),
            ('hb_hoops', 'hour', 1,   700, public.rb_bot_hoops_wins(who, array['Regional', 'National', 'Professional'], (select h from t0)), 1),
            ('hb_arena', 'hour', 1,   400, public.rb_bot_arena_wins(who, array['medium', 'hard', 'insane', 'pro'], (select h from t0)), 2),
            ('db_kart',  'day',  1,  3000, public.rb_bot_kart_wins(who, 1000, (select d from t0)), 0),
            ('db_hoops', 'day',  1,  5000, public.rb_bot_hoops_wins(who, array['National', 'Professional'], (select d from t0)), 1),
            ('db_arena', 'day',  2,  2500, public.rb_bot_arena_wins(who, array['hard', 'insane', 'pro'], (select d from t0)), 2),
            ('wb_kart',  'week', 1, 20000, public.rb_bot_kart_wins(who, 1500, (select w from t0)), 0),
            ('wb_hoops', 'week', 3, 30000, public.rb_bot_hoops_wins(who, array['Professional'], (select w from t0)), 1),
            ('wb_arena', 'week', 3, 15000, public.rb_bot_arena_wins(who, array['insane', 'pro'], (select w from t0)), 2)),
         q (quest, kind, goal, reward, progress) as (
            select pq.quest, 'hour', pq.goal, pq.reward, pq.progress from pool pq
             where pq.quest in ((array['h_rounds', 'h_mini', 'h_case', 'h_bet'])[extract(hour from now())::int % 4 + 1],
                                (array['h_rounds', 'h_mini', 'h_case', 'h_bet'])[(extract(hour from now())::int + 2) % 4 + 1])
            union all
            select b.quest, b.kind, b.goal, b.reward, b.progress from bots b
             where b.turn = (case b.kind when 'hour' then extract(epoch from date_trunc('hour', now()))::bigint / 3600
                                         when 'day' then extract(epoch from date_trunc('day', now()))::bigint / 86400
                                         else extract(epoch from date_trunc('week', now()))::bigint / 604800 end) % 3
            union all values
            ('d_rounds', 'day', 15, 150, (select count(*) from d where game in (select g from casino))::int),
            ('d_case',   'day',  2, 150, (select count(*) from d where game like 'case:%' or game = 'daily')::int),
            ('d_mini',   'day',  3, 150, (select count(*) from d where (game in ('mini', 'park', 'memory', 'blocks', 'sweeper', 'golf_solo', 'golf_party', 'wave') or (game in (select g from skill) and paid > 0)))::int),
            ('d_spin',   'day',  1, 100, (select count(*) from d where game = 'spin')::int),
            ('w_rounds', 'week', 200, 1500, (select count(*) from r where game in (select g from casino))::int),
            ('w_cases',  'week',  25, 2000, (select count(*) from r where game like 'case:%')::int),
            ('w_won',    'week', 25000, 2000, (select coalesce(sum(paid), 0) from r where game in (select g from casino))::int),
            ('w_mini',   'week',  30, 1500, (select count(*) from r where (game in ('mini', 'park', 'memory', 'blocks', 'sweeper', 'golf_solo', 'golf_party', 'wave') or (game in (select g from skill) and paid > 0)))::int),
            ('w_golf',   'week',   3, 1500, ((select count(*) from public.rb_golf g where g.winner = who and g.state = 'done'
                                               and g.done_at >= greatest(date_trunc('week', now()), public.rb_board_from()))
                                             + (select count(*) from r where game in ('golf_party', 'golf_solo')))::int),
            ('w_scratch','week',   7, 1200, (select count(*) from r where game = 'scratch')::int))
    select q.quest, q.kind, q.goal, q.reward, least(q.progress, q.goal), date_trunc(q.kind, now()),
           ceil(extract(epoch from (date_trunc(q.kind, now()) + ('1 ' || q.kind)::interval - now())))::int
      from q $function$;

CREATE OR REPLACE FUNCTION public.rb_quests()
 RETURNS json
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select coalesce(json_agg(json_build_object('quest', q.quest, 'kind', q.kind, 'goal', q.goal, 'reward', q.reward,
               'prize', public.rb_quest_prize_q(q.quest, q.kind, q.reward), 'progress', q.progress, 'left', q.left_s,
               'claimed', exists (select 1 from public.rb_quest_claims c
                                   where c.owner = auth.uid() and c.quest = q.quest and c.period = q.period))), '[]'::json)
      from public.rb_quest_rows(auth.uid()) q $function$;

CREATE OR REPLACE FUNCTION public.rb_quest_claim(which text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare p public.profiles%rowtype; q record; prize jsonb; k integer; c integer;
begin
    perform public.rb_need_feature('quests');
    p := public.rb_lock_me();
    select * into q from public.rb_quest_rows(p.id) x where x.quest = which;
    if not found then raise exception 'rb_no_quest'; end if;
    if q.progress < q.goal then raise exception 'rb_not_done'; end if;
    begin
        insert into public.rb_quest_claims (owner, quest, period) values (p.id, q.quest, q.period);
    exception when unique_violation then
        raise exception 'rb_already_claimed';
    end;
    prize := public.rb_quest_prize_q(q.quest, q.kind, q.reward);
    k := coalesce((prize ->> 'keys')::int, 0);
    c := public.rb_scaled(q.reward, public.rb_tier_mult(p.id));
    perform public.rb_pay(p.id, c, k, 'quest', q.quest);
    if prize ->> 'case' is not null then
        perform public.rb_stock_add(p.id, prize ->> 'case', 1);
    end if;
    return jsonb_build_object('paid', c, 'coins', p.coins + c, 'won_keys', k, 'keys', p.keys + k, 'key_found', true,
                              'case', prize ->> 'case');
end $function$;

drop function if exists public.rb_quest_prize_q(text, text, integer);
drop function if exists public.rb_login_streak_x(integer);
drop function if exists public.rb_bot_kart_wins(uuid, integer, timestamptz);
drop function if exists public.rb_bot_hoops_wins(uuid, text[], timestamptz);
drop function if exists public.rb_bot_arena_wins(uuid, text[], timestamptz);

-- animations back to 9.4 (the new ones are removed when nobody owns them)
delete from public.rb_catalog c where c.kind = 'anim'
   and split_part(c.base, '-', 1) in ('blackhole', 'warp', 'glitch', 'origami', 'pixel', 'ripple')
   and not exists (select 1 from public.rb_items it where it.item = c.id);
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, worth, weight, limited)
select 'anim:' || b.base || f.suf, 'anim', b.base || f.suf, '', b.rarity, b.price * f.x, b.price * f.x / 20, true, 0,
       b.price * f.x, case when f.x = 1 then 1 else 0.1 end, false
  from (values ('shatter', 'special', 25000), ('nova', 'special', 25000), ('rift', 'epic', 60000),
               ('phoenix', 'epic', 60000), ('eclipse', 'exotic', 150000)) as b(base, rarity, price),
       (values ('', 1), ('-titanium', 2), ('-gold', 4), ('-prismatic', 8)) as f(suf, x)
on conflict (id) do update set rarity = excluded.rarity, price = excluded.price, value = excluded.value,
       worth = excluded.worth, weight = excluded.weight;

CREATE OR REPLACE FUNCTION public.rb_friends_list()
 RETURNS json
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select coalesce(json_agg(json_build_object(
               'username', p.username, 'minutes', p.minutes, 'admin', p.admin, 'avatar_v', p.avatar_v,
               'state', case when f.ok then 'friend' when f.a = auth.uid() then 'asked' else 'asks' end,
               'online', f.ok and public.rb_online(p),
               'seen', case when f.ok then p.last_beat end,
               'badges', case when f.ok then json_build_array(p.equip ->> 'badge1', p.equip ->> 'badge2', p.equip ->> 'badge3') end)
               order by f.ok desc, public.rb_online(p) desc, lower(p.username)), '[]'::json)
      from public.rb_friends f
      join public.profiles p on p.id = case when f.a = auth.uid() then f.b else f.a end
     where f.a = auth.uid() or f.b = auth.uid() $function$;
drop function if exists public.rb_friend_doing(uuid);

-- the 9.4 pay for beating bots
CREATE OR REPLACE FUNCTION public.rb_kart_settle(rid uuid)
 RETURNS void
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare r public.rb_kart_rooms%rowtype; s record; n_h integer; k integer; pr integer; xp_ integer; cap bigint;
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
        cap := public.rb_kart_cap(s.owner);                                     -- 9.2.1: by tier, null = no cap
        if cap is not null then
            pr := greatest(0, least(pr::bigint, cap - public.rb_kart_paid_today(s.owner)))::int;
        end if;
        xp_ := 20 + 10 * beat_h + case when beat_bot then 10 else 0 end;
        if pr > 0 then perform public.rb_pay(s.owner, pr, 0, 'kart', rid::text); end if;
        perform public.rb_xp_add(s.owner, xp_, 'kart', rid::text);
        update public.rb_kart_seats set paid = pr, xp = xp_ where room = rid and owner = s.owner;
    end loop;
    update public.rb_kart_rooms set state = 'done', done_at = now(), why = coalesce(why, 'finished') where id = rid;
    delete from public.rb_kart_live where room = rid;
end $function$;

CREATE OR REPLACE FUNCTION public.rb_hoops_finish(gid uuid, me_pts integer, opp_pts integer, ot boolean, stats jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare me uuid := auth.uid(); g public.rb_hoops_games%rowtype; won_ boolean; base integer; pr integer; cap integer;
        today integer; xp_ integer; capped boolean := false; maxp integer; fg integer; fga integer; th integer; tha integer;
        pts integer;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into g from public.rb_hoops_games where id = gid and owner = me for update;
    if not found then raise exception 'rb_bad_request'; end if;
    if g.state <> 'open' then raise exception 'rb_already_done'; end if;
    -- the match can't be over before its clock ran out, and must be sent within 2 hours
    if now() < g.started_at + make_interval(secs => g.mins * 60) or now() > g.started_at + interval '2 hours' then
        update public.rb_hoops_games set state = 'left', done_at = now() where id = gid;
        return jsonb_build_object('paid', 0, 'xp', 0, 'why', 'time');
    end if;
    -- a possible score: at most 15 points a minute for a team (+ overtime's one basket), never a tie
    maxp := g.mins * 15 + 3;
    if me_pts not between 0 and maxp or opp_pts not between 0 and maxp or me_pts = opp_pts then
        raise exception 'rb_bad_request';
    end if;
    -- your own points must add up: 2 a basket, 3 a three, and no more than your team scored
    fg := coalesce((stats ->> 'fg')::int, 0); fga := coalesce((stats ->> 'fga')::int, 0);
    th := coalesce((stats ->> 'three')::int, 0); tha := coalesce((stats ->> 'threea')::int, 0);
    pts := coalesce((stats ->> 'pts')::int, 0);
    if fg > fga or th > tha or th > fg or tha > fga or pts <> 2 * fg + th or pts > me_pts then
        raise exception 'rb_bad_request';
    end if;
    won_ := me_pts > opp_pts;
    base := case g.level when 'Club' then case when won_ then 120 else 25 end
                         when 'Regional' then case when won_ then 220 else 40 end
                         when 'National' then case when won_ then 380 else 60 end
                         else case when won_ then 650 else 90 end end;
    base := round(base * (0.55 + 0.15 * g.mins))::int;                    -- 2 min 85%, 3 min 100%, 5 min 130%
    pr := public.rb_scaled(base, public.rb_tier_mult(me));
    cap := public.rb_hoops_cap(me);
    if cap is not null then
        today := public.rb_hoops_paid_today(me);
        if pr > cap - today then
            capped := true;
            pr := greatest(0, cap - today);
        end if;
    end if;
    xp_ := 15 + case when won_ then 15 else 0 end + 5 * (array_position(array['Club', 'Regional', 'National', 'Professional'], g.level) - 1);
    if pr > 0 then perform public.rb_pay(me, pr, 0, 'hoops', gid::text); end if;
    perform public.rb_xp_add(me, xp_, 'hoops', gid::text);
    update public.rb_hoops_games set state = 'done', done_at = now(), score_me = me_pts, score_opp = opp_pts, ot = rb_hoops_finish.ot,
           won = won_, paid = pr, xp = xp_, stats = rb_hoops_finish.stats where id = gid;
    return jsonb_build_object('paid', pr, 'xp', xp_, 'won', won_, 'capped', capped, 'today', public.rb_hoops_paid_today(me),
                              'cap', cap);
end $function$;

commit;

-- ---------------------------------------------------------------- undo of 096_league_lock.sql
begin;
delete from public.rb_features where name = 'league_ranked';
commit;
