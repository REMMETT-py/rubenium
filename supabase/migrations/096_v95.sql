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
--
-- Animations: re-ranked (Shattered Shard is Mythic now), six new ones (Black Hole and Warp Mythic, Glitch and
-- Origami Legendary, Pixel Dust and Ripple Epic). Titanium is for Mythic animations only; the old Black/White Titan
-- versions are gone (nobody owns any since the 9.4 reset). The free Basic animation needs no item.
--
-- Friends: the friends list says what each friend last played (in the last 24 hours), friends only.
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
        else case when reward < 300 then jsonb_build_object('keys', 1, 'case', null)      -- rb_quest_prize(reward)
                  when reward < 1000 then jsonb_build_object('keys', 1, 'case', 'standard')
                  else jsonb_build_object('keys', 2, 'case', 'premium') end end $$;

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


-- ================================================================ animations
delete from public.rb_catalog c
 where c.kind = 'anim'
   and (c.base like '%-blacktitan' or c.base like '%-whitetitan'
        or (c.base like '%-titanium' and split_part(c.base, '-', 1) not in ('shatter', 'eclipse', 'blackhole', 'warp')))
   and not exists (select 1 from public.rb_items it where it.item = c.id);
insert into public.rb_catalog (id, kind, base, variant, rarity, price, value, tradeable, cls, worth, weight, limited)
select 'anim:' || b.base || f.suf, 'anim', b.base || f.suf, '', b.rarity, b.price * f.x, b.price * f.x / 20, true, 0,
       b.price * f.x, case when f.x = 1 then 1 else 0.1 end, false
  from (values ('nova', 'special', 25000), ('pixel', 'special', 25000), ('ripple', 'special', 25000),
               ('rift', 'epic', 60000), ('phoenix', 'epic', 60000), ('glitch', 'epic', 60000), ('origami', 'epic', 60000),
               ('shatter', 'exotic', 150000), ('eclipse', 'exotic', 150000), ('blackhole', 'exotic', 150000),
               ('warp', 'exotic', 150000)) as b(base, rarity, price),
       (values ('', 1), ('-titanium', 2), ('-gold', 4), ('-prismatic', 8)) as f(suf, x)
 where f.suf <> '-titanium' or b.rarity = 'exotic'
on conflict (id) do update set rarity = excluded.rarity, price = excluded.price, value = excluded.value,
       worth = excluded.worth, weight = excluded.weight, limited = false;

-- ================================================================ friends: what they last played
create or replace function public.rb_friend_doing(who uuid) returns jsonb
language sql stable security definer set search_path to '' as $$
    select jsonb_build_object('game', x.game, 'at', extract(epoch from x.at))
      from (select r.game, r.at from public.rb_rounds r where r.owner = who and r.at > now() - interval '1 day'
             union all
            select 'kart', s.at from public.rb_kart_seats s where s.owner = who and s.at > now() - interval '1 day'
             union all
            select 'hoops', g.started_at from public.rb_hoops_games g where g.owner = who and g.started_at > now() - interval '1 day'
            order by 2 desc limit 1) x $$;
revoke all on function public.rb_friend_doing(uuid) from public, anon, authenticated;

create or replace function public.rb_friends_list() returns json
language sql stable security definer set search_path to '' as $$
    select coalesce(json_agg(json_build_object(
               'username', p.username, 'minutes', p.minutes, 'admin', p.admin, 'avatar_v', p.avatar_v,
               'state', case when f.ok then 'friend' when f.a = auth.uid() then 'asked' else 'asks' end,
               'online', f.ok and public.rb_online(p),
               'seen', case when f.ok then p.last_beat end,
               'badges', case when f.ok then json_build_array(p.equip ->> 'badge1', p.equip ->> 'badge2', p.equip ->> 'badge3') end,
               'doing', case when f.ok then public.rb_friend_doing(p.id) end)
               order by f.ok desc, public.rb_online(p) desc, lower(p.username)), '[]'::json)
      from public.rb_friends f
      join public.profiles p on p.id = case when f.a = auth.uid() then f.b else f.a end
     where f.a = auth.uid() or f.b = auth.uid() $$;

-- ================================================================ bigger pay for beating bots (9.5)
-- Karting: beating the bot pays 20 + 1480 x (Elo / 2500)^3 (Rookie 20, Racer 115, Expert 340, Elite 780, Professional 1500)
-- instead of up to 200. Hoops wins: Club 150, Regional 350, National 900, Professional 2500 (3 min), losses a little more.
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
              + case when beat_bot then floor(20 + 1480 * power(r.bot_elo / 2500.0, 3))::int else 0 end
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
    base := case g.level when 'Club' then case when won_ then 150 else 30 end
                         when 'Regional' then case when won_ then 350 else 50 end
                         when 'National' then case when won_ then 900 else 80 end
                         else case when won_ then 2500 else 120 end end;
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

-- ================================================================ Karting and Hoops stats start again (9.5, once)
-- Every finished race (its results, its time board run) and every finished Hoops match is cleared, so the Karting time
-- boards, race stats and Hoops records start from zero. Races and matches still being played are kept. Only once:
-- running this file again does not clear them a second time.
do $$
begin
    if not exists (select 1 from public.rb_config where key = 'games_reset_95') then
        delete from public.rb_kart_rooms where state in ('done', 'cancelled');
        delete from public.rb_kart_ghosts;
        delete from public.rb_hoops_games where state <> 'open';
        insert into public.rb_config (key, value) values ('games_reset_95', extract(epoch from now())::bigint);
    end if;
end $$;

-- Rubenium League is removed: its admin switch for ranked goes too (it was added by 096_league_lock.sql)
delete from public.rb_features where name = 'league_ranked';

commit;
