-- Rubenium 9.5. Safe to run twice. Undo: 096_down.sql.
--
-- Karting: the bot ladder moved up (9.4's Professional is now Expert); Elite and Professional lap faster than the
-- players' fastest possible lap, so the bot's time floor in rb_kart_finish is 80 % of the record (players stay at 94 %).
--
-- Economy:
--  * Bet cap: 20 % of your coins (was 50 %), never below 1 000, never above 250 000 (rb_config, change it there).
--  * Comeback top-up: once a day, under your floor, rb_topup brings you UP TO it (800 -> 1 000, not +1 000). The floor
--    grows with your casino rank: Poor 1 000, Average 2 500, Investor 5 000, Businessman 12 000, Casino Legend 30 000.
--  * Daily login: coins AND a case every day; the coins grow by 10 % for each full week of streak (up to +100 %).
--  * Quests: one bot challenge an hour (300-800), a day (2 000-5 000) and a week (15 000-30 000 + a case), rotating
--    between Karting, Hoops and the Arena; every weekly quest gives a case, a different one each week.
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

-- ================================================================ bet cap
insert into public.rb_config (key, value) values ('bet_max', 1000), ('bet_rich_pct', 20), ('bet_max_rich', 250000)
on conflict (key) do update set value = excluded.value;

-- ================================================================ comeback top-up
alter table public.profiles add column if not exists topup_day date;
insert into public.rb_config (key, value) values ('topup_0', 1000), ('topup_1', 2500), ('topup_2', 5000), ('topup_3', 12000),
                                               ('topup_4', 30000)
on conflict (key) do nothing;

create or replace function public.rb_topup_floor(who uuid) returns integer
language sql stable security definer set search_path to '' as $$
    select coalesce(public.rb_cfg('topup_' || ((public.rb_tier(who) ->> 'tier')::int)), 1000)::int $$;

-- what the app shows: your floor, and whether today's top-up is still there
create or replace function public.rb_topup_state() returns jsonb
language plpgsql stable security definer set search_path to '' as $$
declare p public.profiles%rowtype;
begin
    select * into p from public.profiles where id = auth.uid();
    if not found then raise exception 'rb_not_logged_in'; end if;
    return jsonb_build_object('floor', public.rb_topup_floor(p.id), 'coins', p.coins,
                              'used', p.topup_day is not distinct from public.rb_today());
end $$;

create or replace function public.rb_topup() returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; fl integer; add integer;
begin
    p := public.rb_lock_me();
    if p.topup_day is not distinct from public.rb_today() then raise exception 'rb_wait'; end if;
    -- never in the middle of a round: the coins on the table come back first
    if exists (select 1 from public.rb_rounds r where r.owner = p.id and r.open) then raise exception 'rb_wait'; end if;
    fl := public.rb_topup_floor(p.id);
    if p.coins >= fl then raise exception 'rb_not_needed'; end if;
    add := fl - p.coins;
    update public.profiles set topup_day = public.rb_today() where id = p.id;
    perform public.rb_pay(p.id, add, 0, 'topup', fl::text);
    return jsonb_build_object('got', add, 'floor', fl, 'coins', p.coins + add);
end $$;

revoke all on function public.rb_topup_floor(uuid), public.rb_topup_state(), public.rb_topup() from public, anon;
grant execute on function public.rb_topup_state(), public.rb_topup() to authenticated;

-- ================================================================ daily login: coins and a case, growing with the streak
create or replace function public.rb_login_rewards() returns jsonb
language sql immutable set search_path to '' as $$
    select '[{"coins":300,"case":"starter"},{"coins":400,"case":"standard"},{"coins":500,"case":"nature"},
             {"coins":600,"case":"standard"},{"coins":800,"case":"premium"},{"coins":1000,"case":"medieval"},
             {"coins":1500,"case":"painter"}]'::jsonb $$;

-- +10 % for each full week of streak, up to +100 %
create or replace function public.rb_login_streak_x(s integer) returns numeric
language sql immutable set search_path to '' as $$ select 1 + 0.1 * least(10, greatest(0, (coalesce(s, 1) - 1) / 7)) $$;

create or replace function public.rb_login_claim() returns jsonb
language plpgsql security definer set search_path to '' as $$
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
end $$;

create or replace function public.rb_login_state() returns json
language plpgsql stable security definer set search_path to '' as $$
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
end $$;

-- ================================================================ quests: bot challenges, a case on every weekly quest
-- Karting: races (2 laps or more) where you crossed the line ahead of a bot of at least that Elo
create or replace function public.rb_bot_kart_wins(who uuid, elo integer, since timestamptz) returns integer
language sql stable security definer set search_path to '' as $$
    select count(*)::int from public.rb_kart_seats s join public.rb_kart_rooms r on r.id = s.room
     where s.owner = who and r.bot and r.state = 'done' and r.bot_elo >= elo and r.laps >= 2
       and s.finish_ms is not null and not s.gone and s.place is not null and s.place < coalesce(r.bot_place, 99)
       and s.done_at >= since $$;

create or replace function public.rb_bot_hoops_wins(who uuid, levels text[], since timestamptz) returns integer
language sql stable security definer set search_path to '' as $$
    select count(*)::int from public.rb_hoops_games g
     where g.owner = who and g.state = 'done' and g.won and g.level = any (levels) and g.done_at >= since $$;

create or replace function public.rb_bot_arena_wins(who uuid, levels text[], since timestamptz) returns integer
language sql stable security definer set search_path to '' as $$
    select count(*)::int from public.rb_rounds r
     where r.owner = who and not r.open and r.game in ('c4', 'reversi', 'ships', 'maze', 'tri')
       and r.secret ->> 'outcome' = 'win' and r.secret ->> 'level' = any (levels) and r.at >= since $$;

create or replace function public.rb_quest_rows(who uuid)
 returns table(quest text, kind text, goal integer, reward integer, progress integer, period timestamp with time zone, left_s integer)
language sql stable security definer set search_path to '' as $$
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
      from q $$;

-- the keys and case of a quest: every weekly quest gives a case, a different one each week (the bot challenge of the
-- week a better one); the bot challenges of the hour give a key, of the day a key and a case
create or replace function public.rb_quest_prize_q(quest text, kind text, reward integer) returns jsonb
language sql stable set search_path to '' as $$
    select case
        when kind = 'week' and quest like 'wb\_%' then jsonb_build_object('keys', 3,
             'case', (array['shiny', 'winter', 'themes'])[(extract(epoch from date_trunc('week', now()))::bigint / 604800) % 3 + 1])
        when kind = 'week' then jsonb_build_object('keys', 2,
             'case', (array['premium', 'medieval', 'painter', 'cosmos', 'frames', 'banners', 'nature', 'arcade'])
                     [(extract(epoch from date_trunc('week', now()))::bigint / 604800 + length(quest) + ascii(right(quest, 1))) % 8 + 1])
        when quest like 'db\_%' then jsonb_build_object('keys', 1, 'case', 'standard')
        when quest like 'hb\_%' then jsonb_build_object('keys', 1, 'case', null)
        else public.rb_quest_prize(reward) end $$;

create or replace function public.rb_quests() returns json
language sql stable security definer set search_path to '' as $$
    select coalesce(json_agg(json_build_object('quest', q.quest, 'kind', q.kind, 'goal', q.goal, 'reward', q.reward,
               'prize', public.rb_quest_prize_q(q.quest, q.kind, q.reward), 'progress', q.progress, 'left', q.left_s,
               'claimed', exists (select 1 from public.rb_quest_claims c
                                   where c.owner = auth.uid() and c.quest = q.quest and c.period = q.period))), '[]'::json)
      from public.rb_quest_rows(auth.uid()) q $$;

create or replace function public.rb_quest_claim(which text) returns jsonb
language plpgsql security definer set search_path to '' as $$
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
end $$;

revoke all on function public.rb_bot_kart_wins(uuid, integer, timestamptz), public.rb_bot_hoops_wins(uuid, text[], timestamptz),
    public.rb_bot_arena_wins(uuid, text[], timestamptz), public.rb_login_streak_x(integer),
    public.rb_quest_prize_q(text, text, integer) from public, anon, authenticated;


commit;
