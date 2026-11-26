-- Rubenium 9.2, server part. Safe to run twice.
--
-- 1. Fresh leaderboards: every board counts only what was played after the 9.2 reset (config board_from). The boards
--    that show what you have now (Richest, Worth, Level, Badges) stay as they are; Hours counts from the reset. Bots' made-up stats go too.
--    One global board: the friends switch is ignored.
-- 2. Quests count progress from the reset on. The reset itself (boards, streaks, quests, coins) is 083_v92_reset.
-- 3. Trophies can be counted from a date too (config ach_from; 0 = all of them).
-- 4. Jackpot and Horse Racing take turns on a fixed 20 minute clock (config arena_cycle_s): even slots Jackpot, odd
--    slots Horse Racing. The game opens at the start of its slot whoever is online, players joining never move the
--    clock, and a database job ticks it every 5 seconds so bots play every round even when nobody is online.
-- 5. Reversi is gone (bots and duels; config reversi_on = 1 brings it back). Starting a bot game or a duel closes your own duel that nobody joined yet
--    (the bet comes back), so "You already have one going" no longer blocks you.
-- 6. Fonts: the Titanium White and Titanium Black fonts leave the shop (nobody owns one); text picks black or white by
--    itself in the app.
-- 7. Coinflip bots: far fewer big offers, and a bot takes longer to find items for an expensive flip (up to 2 min).
-- 8. Mini games pay double: the skill games and bot games (skill_pay_mult 2, it was 1) and the free coin games
--    (game_pay_mult 2, it was 1.3).
begin;

insert into public.rb_config (key, value) values ('skill_pay_mult', 2), ('game_pay_mult', 2)
on conflict (key) do update set value = excluded.value;

insert into public.rb_config (key, value) values ('arena_cycle_s', 1200), ('ach_from', 0), ('board_from', 0)
on conflict (key) do nothing;

-- the Hours board counts play time since the reset: minutes at the reset are kept here
alter table public.profiles add column if not exists board_min0 integer not null default 0;

create or replace function public.rb_board_from() returns timestamptz
language sql stable security definer set search_path to '' as $$
    select to_timestamp(coalesce(public.rb_cfg('board_from'), 0)) $$;

create or replace function public.rb_ach_from() returns timestamptz
language sql stable security definer set search_path to '' as $$
    select to_timestamp(coalesce(public.rb_cfg('ach_from'), 0)) $$;

-- ---------------------------------------------------------------- 1. boards from the reset on
create or replace function public.rb_best_win(who uuid, g text) returns bigint
language sql stable set search_path to '' as $$
    select coalesce(max(r.paid - r.bet), 0)::bigint from public.rb_rounds r
     where r.owner = who and r.game = g and r.paid > r.bet and r.at >= public.rb_board_from() $$;

create or replace function public.rb_bg_duel_wins(who uuid, k text) returns bigint
language sql stable security definer set search_path to '' as $$
    select count(*)::bigint from public.rb_bg g
     where g.b is not null and g.state = 'done' and (k is null or g.kind = k) and g.done_at >= public.rb_board_from()
       and ((g.winner = 1 and g.a = who) or (g.winner = 2 and g.b = who)) $$;

create or replace function public.rb_bg_points(who uuid, k text) returns bigint
language sql stable security definer set search_path to '' as $$
    select coalesce(sum(case g.level when 'insane' then 10 when 'hard' then 4 when 'medium' then 2 else 1 end), 0)::bigint
      from public.rb_bg g where g.a = who and g.b is null and g.kind = k and g.state = 'done' and g.winner = 1
       and g.done_at >= public.rb_board_from() $$;

create or replace function public.rb_wave_best_since(who uuid, since timestamptz) returns integer
language sql stable security definer set search_path to '' as $$
    select coalesce(max(dist), 0) from public.rb_wave_runs
     where owner = who and duel is null and state = 'done' and coalesce(done_at, started_at) >= since $$;

create or replace function public.rb_leaders(kind text, friends boolean) returns json
language plpgsql stable security definer set search_path to '' as $$
declare me uuid := auth.uid(); t0 timestamptz := public.rb_board_from();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    if kind not in ('coins', 'worth', 'badges', 'hours', 'streak', 'tap', 'park', 'memory', 'level',
                    'wave', 'flips', 'golf', 'c4', 'cups', 'trophies', 'horses', 'reversi', 'ships', 'arena',
                    'a:c4', 'a:reversi', 'a:ships', 'maze', 'a:maze', 'tri', 'a:tri')
       and kind not in ('g:roulette', 'g:blackjack', 'g:hilo', 'g:slots', 'g:rocket', 'g:plinko', 'g:mines', 'g:tower',
                        'g:dice', 'g:timing', 'g:colour', 'g:sfx') then raise exception 'rb_bad_choice'; end if;
    return (with who as (select p.* from public.profiles p where not p.banned),          -- 9.2: one global board
            v as (select w.id, w.username, (case kind
                when 'coins' then w.coins when 'level' then w.xp
                when 'hours' then greatest(0, w.minutes - w.board_min0) / 60
                when 'streak' then (case when w.streak_day >= public.rb_today() - 1 then w.streak else 0 end)
                when 'worth' then (select coalesce(sum(public.rb_worth(c.id)), 0) from public.rb_items it join public.rb_catalog c on c.id = it.item where it.owner = w.id)
                when 'badges' then (select count(distinct it.item) from public.rb_items it where it.owner = w.id and it.item like 'badge:%')
                when 'tap' then (select coalesce(max((r.secret ->> 'pct')::int), 0) from public.rb_rounds r where r.owner = w.id and r.game = 'mini' and r.at >= t0)
                when 'park' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game = 'park' and r.at >= t0)
                when 'memory' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game = 'memory' and r.at >= t0)
                when 'wave' then greatest(public.rb_wave_best_since(w.id, t0) / 100, coalesce((w.bot_cfg -> 'stats' ->> 'wave')::bigint, 0))
                when 'flips' then (select count(*) from public.rb_flips f where f.winner = w.id and f.state = 'done' and f.done_at >= t0)
                                  + coalesce((w.bot_cfg -> 'stats' ->> 'flip')::bigint, 0)
                when 'golf' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game in ('golf', 'golf_party', 'golf_solo') and r.at >= t0)
                                 + coalesce((w.bot_cfg -> 'stats' ->> 'golf')::bigint, 0)
                when 'c4' then (select count(*) from public.rb_c4 g where g.owner = w.id and g.outcome = 'win' and g.updated_at >= t0)
                when 'cups' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game = 'cups' and r.paid > r.bet and r.at >= t0)
                when 'horses' then (select coalesce(max(b.paid - b.amount), 0) from public.rb_race_bets b where b.owner = w.id and b.paid > b.amount and b.at >= t0)
                when 'reversi' then public.rb_bg_points(w.id, 'reversi')
                when 'ships' then public.rb_bg_points(w.id, 'ships')
                when 'maze' then public.rb_bg_points(w.id, 'maze')
                when 'a:maze' then public.rb_bg_duel_wins(w.id, 'maze')
                when 'tri' then public.rb_bg_points(w.id, 'tri')
                when 'a:tri' then public.rb_bg_duel_wins(w.id, 'tri')
                when 'arena' then public.rb_bg_duel_wins(w.id, null)
                when 'a:c4' then public.rb_bg_duel_wins(w.id, 'c4')
                when 'a:reversi' then public.rb_bg_duel_wins(w.id, 'reversi')
                when 'a:ships' then public.rb_bg_duel_wins(w.id, 'ships')
                when 'g:roulette' then public.rb_best_win(w.id, 'roulette') when 'g:blackjack' then public.rb_best_win(w.id, 'blackjack')
                when 'g:hilo' then public.rb_best_win(w.id, 'hilo') when 'g:slots' then public.rb_best_win(w.id, 'slots')
                when 'g:rocket' then public.rb_best_win(w.id, 'rocket') when 'g:plinko' then public.rb_best_win(w.id, 'plinko')
                when 'g:mines' then public.rb_best_win(w.id, 'mines') when 'g:tower' then public.rb_best_win(w.id, 'tower')
                when 'g:dice' then public.rb_best_win(w.id, 'dice') when 'g:timing' then public.rb_best_win(w.id, 'timing')
                when 'g:colour' then public.rb_best_win(w.id, 'colour') when 'g:sfx' then public.rb_best_win(w.id, 'sfx')
                else (select count(*) from public.rb_ach a where a.owner = w.id and a.at >= t0) end)::bigint as val
                  from who w),
            ranked as (select v.*, rank() over (order by val desc) rk from v where val > 0 or v.id = me)
        select json_build_object(
            'top', coalesce((select json_agg(json_build_object('rank', rk, 'name', username, 'value', val, 'me', id = me) order by rk, username)
                               from (select * from ranked order by rk, username limit 50) t), '[]'::json),
            'me', (select json_build_object('rank', rk, 'value', val) from ranked where id = me)));
end $$;

create or replace function public.rb_mg_board(game text, mode integer, friends boolean) returns json
language plpgsql stable security definer set search_path to '' as $$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    return (with best as (
                select distinct on (g.owner) g.owner, g.score, g.secs, g.at from public.rb_mg g
                 where g.game = rb_mg_board.game and g.mode = rb_mg_board.mode and not g.open and not g.void
                   and coalesce(g.score, 0) > 0 and (g.game in ('g2048', 'blocks') or g.won) and g.at >= public.rb_board_from()
                 order by g.owner, g.score desc, g.at),
            ranked as (select b.*, p.username, rank() over (order by b.score desc) rk from best b
                        join public.profiles p on p.id = b.owner
                       where not p.banned)
        select json_build_object(
            'top', coalesce((select json_agg(json_build_object('rank', rk, 'name', username, 'value', score, 'secs', round(secs, 1),
                                                               'me', owner = me) order by rk, username)
                               from (select * from ranked order by rk limit 50) t), '[]'::json),
            'me', (select json_build_object('rank', rk, 'value', score, 'secs', round(secs, 1)) from ranked where owner = me)));
end $$;

create or replace function public.rb_title_values(kind text) returns table(id uuid, username text, val bigint)
language sql stable security definer set search_path to '' as $$
    select w.id, w.username, (case kind
        when 'coins' then w.coins
        when 'level' then w.xp
        when 'hours' then greatest(0, w.minutes - w.board_min0) / 60
        when 'streak' then (case when w.streak_day >= public.rb_today() - 1 then w.streak else 0 end)
        when 'worth' then (select coalesce(sum(public.rb_worth(it.item)), 0) from public.rb_items it where it.owner = w.id)
        when 'badges' then (select count(distinct it.item) from public.rb_items it where it.owner = w.id and it.item like 'badge:%')
        when 'tap' then (select coalesce(max((r.secret ->> 'pct')::int), 0) from public.rb_rounds r where r.owner = w.id and r.game = 'mini' and r.at >= public.rb_board_from())
        when 'park' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game = 'park' and r.at >= public.rb_board_from())
        when 'memory' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game = 'memory' and r.at >= public.rb_board_from())
        when 'blocks' then (select coalesce(max(g.score), 0) from public.rb_mg g where g.owner = w.id and g.game = 'blocks'
                              and not g.open and not g.void and g.at >= public.rb_board_from())
        when 'wave' then public.rb_wave_best_since(w.id, public.rb_board_from())
        when 'flip' then (select count(*) from public.rb_flips f where f.winner = w.id and f.state = 'done' and f.done_at >= public.rb_board_from())
        when 'golf' then (select count(*) from public.rb_golf g where g.winner = w.id and g.state = 'done' and g.b is not null
                            and g.done_at >= public.rb_board_from())
        else 0 end)::bigint
      from public.profiles w where not w.banned and not w.bot $$;

-- ---------------------------------------------------------------- 2. quests from the reset on
create or replace function public.rb_quest_rows(who uuid)
returns table(quest text, kind text, goal integer, reward integer, progress integer, period timestamptz, left_s integer)
language sql stable security definer set search_path to '' as $$
    with r as (select game, bet, paid, at from public.rb_rounds
                where owner = who and not open and at >= greatest(date_trunc('week', now()), public.rb_board_from())),
         d as (select * from r where at >= date_trunc('day', now())),
         h as (select * from r where at >= date_trunc('hour', now())),
         casino (g) as (values ('slots'), ('plinko'), ('dice'), ('mines'), ('rocket'), ('blackjack'), ('roulette'), ('hilo'), ('tower')),
         skill (g) as (values ('timing'), ('cups'), ('c4'), ('colour'), ('sfx')),
         pool (quest, goal, reward, progress) as (values
            ('h_rounds', 3, 25, (select count(*) from h where game in (select g from casino))::int),
            ('h_mini',   1, 25, (select count(*) from h where (game in ('mini', 'park', 'memory', 'blocks', 'sweeper', 'golf_solo', 'golf_party', 'wave') or (game in (select g from skill) and paid > 0)))::int),
            ('h_case',   1, 30, (select count(*) from h where game like 'case:%' or game = 'daily')::int),
            ('h_bet',  100, 25, (select coalesce(sum(bet), 0) from h where game in (select g from casino))::int)),
         q (quest, kind, goal, reward, progress) as (
            select pq.quest, 'hour', pq.goal, pq.reward, pq.progress from pool pq
             where pq.quest in ((array['h_rounds', 'h_mini', 'h_case', 'h_bet'])[extract(hour from now())::int % 4 + 1],
                                (array['h_rounds', 'h_mini', 'h_case', 'h_bet'])[(extract(hour from now())::int + 2) % 4 + 1])
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

-- ---------------------------------------------------------------- 3. trophies count from ach_from on
create or replace function public.rb_ach_stats(who uuid) returns jsonb
language sql stable security definer set search_path to '' as $$
    with r as (
        select case game when 'mines' then 'bombs' when 'c4' then 'connect4' when 'golf_party' then 'golf'
                         when 'golf_solo' then 'golf' else game end g, bet, paid
          from public.rb_rounds where owner = who and not open and at >= public.rb_ach_from()
           and game in ('blackjack', 'roulette', 'mines', 'plinko', 'slots', 'hilo', 'cups', 'c4', 'colour', 'sfx', 'golf', 'golf_party',
                        'golf_solo', 'wave')),
    s as (select g, count(*) rounds, count(*) filter (where paid > bet) wins,
                 coalesce(max(case when bet > 0 then paid::numeric / bet end), 0) bigx from r group by g),
    f as (select count(*) rounds, count(*) filter (where winner = who) wins,
                 coalesce(max(case when winner = who then coalesce(a_value, 0) + coalesce(b_value, 0) end), 0) bigwin
            from public.rb_flips where (a = who or b = who) and state = 'done' and done_at >= public.rb_ach_from())
    select coalesce((select jsonb_object_agg(g, jsonb_build_object('rounds', rounds, 'wins', wins, 'bigx', round(bigx, 2))) from s),
                    '{}'::jsonb)
           || jsonb_build_object('coinflip', (select jsonb_build_object('rounds', rounds, 'wins', wins, 'bigwin', bigwin) from f))
           || jsonb_build_object('wave', coalesce((select jsonb_build_object('rounds', rounds, 'wins', wins) from s where g = 'wave'),
                                                  '{}'::jsonb) || jsonb_build_object('best', public.rb_wave_best_since(who, public.rb_ach_from()) / 100)) $$;

-- ---------------------------------------------------------------- 4. Jackpot and Horse Racing on a fixed clock
create or replace function public.rb_arena_slot_kind(k bigint) returns text
language sql immutable set search_path to '' as $$ select case when k % 2 = 0 then 'jackpot' else 'race' end $$;

create or replace function public.rb_arena_tick() returns void
language plpgsql security definer set search_path to '' as $$
declare a public.rb_arena%rowtype; st text; nid uuid; cyc double precision := coalesce(public.rb_cfg('arena_cycle_s'), 1200);
        k bigint; s0 timestamptz; kind_ text; o double precision; late double precision;
begin
    insert into public.rb_arena (id) values (1) on conflict do nothing;
    select * into a from public.rb_arena where id = 1 for update;
    if a.cur_id is not null then
        if a.cur_kind = 'jackpot' then
            perform public.rb_jackpot_advance(a.cur_id);
            select state into st from public.rb_jackpots where id = a.cur_id;
            if st is null or st in ('done', 'empty') then
                update public.rb_arena set cur_id = null, cur_kind = null, at = now() where id = 1;
            end if;
        else
            perform public.rb_race_advance(a.cur_id);
            select state into st from public.rb_races where id = a.cur_id;
            if st is null or st = 'done' then
                update public.rb_arena set cur_id = null, cur_kind = null, at = now() where id = 1;
            end if;
        end if;
        return;
    end if;
    k := floor(extract(epoch from now()) / cyc)::bigint;
    s0 := to_timestamp(k * cyc);
    kind_ := public.rb_arena_slot_kind(k);
    late := extract(epoch from now() - s0);
    -- each slot plays once, at its start; a slot already played (or more than 60 s gone) waits for the next one
    if (a.next_at is null or a.next_at <= s0) and late <= 60 then
        if kind_ = 'jackpot' then
            o := coalesce(public.rb_cfg('jackpot_open_s'), 120);
            insert into public.rb_jackpots (slot, lock_at, spin_at, result_at, pick_until)
                values (s0, s0 + make_interval(secs => o), s0 + make_interval(secs => o + 12),
                        s0 + make_interval(secs => o + 22), s0 + make_interval(secs => o + 142))
                on conflict (slot) do nothing returning id into nid;
            if nid is null then select id into nid from public.rb_jackpots where slot = s0; end if;
        else
            nid := public.rb_race_make();
            update public.rb_races set lock_at = s0 + make_interval(secs => coalesce(public.rb_cfg('race_open_s'), 120))
             where id = nid;
        end if;
        update public.rb_arena set cur_kind = kind_, cur_id = nid, at = now(),
               next_at = s0 + make_interval(secs => cyc), next_kind = public.rb_arena_slot_kind(k + 1) where id = 1;
    end if;
end $$;

-- when the next game of this kind opens (epoch seconds); now while it runs
create or replace function public.rb_arena_next(kind text) returns double precision
language plpgsql stable security definer set search_path to '' as $$
declare a public.rb_arena%rowtype; cyc double precision := coalesce(public.rb_cfg('arena_cycle_s'), 1200); k bigint;
begin
    select * into a from public.rb_arena where id = 1;
    if found and a.cur_id is not null and a.cur_kind = kind then return extract(epoch from now()); end if;
    k := floor(extract(epoch from now()) / cyc)::bigint + 1;
    if public.rb_arena_slot_kind(k) <> kind then k := k + 1; end if;
    return k * cyc;
end $$;

-- the jackpot screen asks the same arena (rb_jackpot_make picks the current one)
create or replace function public.rb_arena_now() returns jsonb
language plpgsql security definer set search_path to '' as $$
declare a public.rb_arena%rowtype; cyc double precision := coalesce(public.rb_cfg('arena_cycle_s'), 1200); k bigint;
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    perform public.rb_arena_tick();
    select * into a from public.rb_arena where id = 1;
    k := floor(extract(epoch from now()) / cyc)::bigint;
    return jsonb_build_object('now', extract(epoch from now()), 'cur', a.cur_kind, 'slot_kind', public.rb_arena_slot_kind(k),
                              'next_kind', public.rb_arena_slot_kind(k + 1), 'next_at', (k + 1) * cyc, 'cycle', cyc);
end $$;
revoke all on function public.rb_arena_now() from public, anon;
grant execute on function public.rb_arena_now() to authenticated;
revoke all on function public.rb_arena_slot_kind(bigint), public.rb_wave_best_since(uuid, timestamptz),
                       public.rb_board_from(), public.rb_ach_from() from public, anon, authenticated;

-- ---------------------------------------------------------------- 5. Reversi gone, your own empty duel never blocks
create or replace function public.rb_bg_close_my_lobby(who uuid) returns void
language plpgsql security definer set search_path to '' as $$
declare g record;
begin
    for g in select id, bet from public.rb_bg where a = who and b is null and level is null and state = 'open' for update loop
        update public.rb_bg set state = 'cancelled', why = 'cancelled', done_at = now() where id = g.id;
        if g.bet > 0 then perform public.rb_pay(who, g.bet, 0, 'arena_back', g.id::text); end if;
    end loop;
end $$;
revoke all on function public.rb_bg_close_my_lobby(uuid) from public, anon, authenticated;

create or replace function public.rb_bg_bot(kind text, level text) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; g public.rb_bg%rowtype; sec jsonb := '{}'::jsonb; first_ integer := 1;
begin
    perform public.rb_rate(auth.uid(), 'arena', 20);
    perform public.rb_need_feature('minigames');
    p := public.rb_lock_me();
    if not (kind = 'ships' or kind = 'reversi' and coalesce(public.rb_cfg('reversi_on'), 0) = 1) or level not in ('easy', 'medium', 'hard', 'insane') then raise exception 'rb_bad_choice'; end if;
    perform public.rb_bg_tick_mine(p.id);
    update public.rb_bg set state = 'cancelled', why = 'left', done_at = now()      -- an old bot game you walked away from
     where a = p.id and b is null and rb_bg.level is not null and state = 'live';
    perform public.rb_bg_close_my_lobby(p.id);                                       -- 9.2: your duel nobody joined
    if public.rb_bg_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    if kind = 'ships' then
        sec := jsonb_build_object('f1', public.sh_fleet(), 'f2', public.sh_fleet());
        first_ := case when public.rb_rand() < 0.5 then 1 else 2 end;
    end if;
    insert into public.rb_bg (kind, a, b, level, state, board, secret, turn, live_at, turn_at)
        values (kind, p.id, null, level, 'live', public.rb_bg_new_board(kind), sec, first_, now(), now()) returning * into g;
    perform public.rb_bg_bot_turns(g.id);
    select * into g from public.rb_bg where id = g.id;
    return public.rb_bg_json(g, p.id);
end $$;

create or replace function public.rb_bg_create(kind text, bet integer) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; g public.rb_bg%rowtype;
begin
    perform public.rb_rate(auth.uid(), 'duel', 10);
    perform public.rb_need_feature('arena');
    p := public.rb_lock_me();
    if not (kind in ('c4', 'ships') or kind = 'reversi' and coalesce(public.rb_cfg('reversi_on'), 0) = 1) then raise exception 'rb_bad_choice'; end if;
    perform public.rb_bg_tick_mine(p.id);
    perform public.rb_bg_close_my_lobby(p.id);                                       -- 9.2: a new duel replaces your empty one
    select * into p from public.profiles where id = p.id;
    if public.rb_bg_busy(p.id) then raise exception 'rb_one_lobby'; end if;
    bet := coalesce(bet, 0);
    if bet <> 0 and (bet < 10 or bet % 10 <> 0 or bet > public.rb_golf_cap(p.coins)) then raise exception 'rb_bad_bet'; end if;
    if bet > 0 then perform public.rb_pay(p.id, -bet, 0, 'arena_bet', kind); end if;
    insert into public.rb_bg (kind, a, bet, state, board) values (kind, p.id, bet, 'open', public.rb_bg_new_board(kind))
        returning * into g;
    return public.rb_bg_json(g, p.id) || jsonb_build_object('coins', p.coins - bet);
end $$;

do $$
declare g record;
begin
    for g in select id, a, bet from public.rb_bg where kind = 'reversi' and state = 'open' loop
        update public.rb_bg set state = 'cancelled', why = 'cancelled', done_at = now() where id = g.id;
        if g.bet > 0 then perform public.rb_pay(g.a, g.bet, 0, 'arena_back', g.id::text); end if;
    end loop;
    update public.rb_bg set state = 'cancelled', why = 'left', done_at = now()
     where kind = 'reversi' and state = 'live' and b is null;
end $$;

-- ---------------------------------------------------------------- 6. no Titanium fonts in the shop
do $$
begin
    if not exists (select 1 from public.rb_items where item like 'font:%:white' or item like 'font:%:black') then
        delete from public.rb_catalog where id like 'font:%:white' or id like 'font:%:black';
    end if;
end $$;

-- ---------------------------------------------------------------- 7. coinflip bots
update public.rb_config set value = 600000 where key = 'flip_bot_max' and value > 600000;

create or replace function public.rb_flip_bots_tick() returns void
language plpgsql security definer set search_path to '' as $$
declare lo_ integer; hi_ integer; tgt integer; cur integer; fid uuid; tier_ text; tries integer := 0; x double precision;
begin
    if not public.rb_feature_on('coinflip') then return; end if;
    for fid in select id from public.rb_flips where bot_side = 'a' and state in ('open', 'joined', 'locked') loop
        perform public.rb_flip_tick(fid);
    end loop;
    lo_ := coalesce(public.rb_cfg('bot_flips_min'), 5)::int;
    hi_ := greatest(lo_, coalesce(public.rb_cfg('bot_flips_max'), 10)::int);
    tgt := lo_ + abs(hashtext('flipbots' || floor(extract(epoch from now()) / 1200)::text)) % (hi_ - lo_ + 1);
    loop
        select count(*) into cur from public.rb_flips where bot_side = 'a' and not admin_offer and state = 'open';
        exit when cur >= tgt or tries >= 6;
        exit when cur >= lo_ and random() > 0.4;
        tries := tries + 1;
        -- 9.2: mostly small and mid offers; a big one only now and then, and never two at once
        x := random();
        tier_ := case when x < 0.58 then 'low' when x < 0.93 then 'mid' else 'high' end;
        if tier_ = 'high' and exists (select 1 from public.rb_flips f join public.rb_flip_bots() b on b.name = f.bot_name
                                       where f.bot_side = 'a' and not f.admin_offer and f.state = 'open' and b.tier = 'high') then
            tier_ := 'mid';
        end if;
        perform public.rb_flip_bot_offer(null, false,
                    (select b.name from public.rb_flip_bots() b where b.tier = tier_ order by random() limit 1), null, null, null);
    end loop;
end $$;

-- how long a bot takes to find items for a flip of this value: a few seconds for small ones, up to 2 minutes
create or replace function public.rb_flip_find_s(v bigint) returns double precision
language sql volatile set search_path to '' as $$
    select case when v <= 50000 then 3 + random() * 4
                else least(120, (4 + 116 * least(1.0, (ln(v::double precision) - ln(50000)) / (ln(2000000) - ln(50000))))
                                * (0.8 + 0.2 * random())) end $$;
revoke all on function public.rb_flip_find_s(bigint) from public, anon, authenticated;

create or replace function public.rb_flip_vs_bot(fid uuid) returns json
language plpgsql security definer set search_path to '' as $$
declare p public.profiles%rowtype; f public.rb_flips%rowtype; rng double precision; whats text[]; total bigint;
        ch double precision; a_wins boolean; found_s double precision; choose_s double precision; bot text;
begin
    perform public.rb_rate(auth.uid(), 'flip', 15);
    p := public.rb_lock_me();
    perform public.rb_need_feature('coinflip');
    perform public.rb_flip_tick(fid);
    select * into f from public.rb_flips where id = fid for update;
    if not found or f.a is distinct from p.id then raise exception 'rb_duel_gone'; end if;
    if f.state <> 'open' then raise exception 'rb_flip_taken'; end if;
    rng := coalesce(public.rb_cfg('flip_range'), 0.1);
    whats := public.rb_flip_bot_fit(f.a_value, floor(f.a_value * (1 - rng))::bigint, ceil(f.a_value * (1 + rng))::bigint);
    if whats is null then raise exception 'rb_no_bot'; end if;
    select sum(public.rb_worth(w)) into total from unnest(whats) w;
    bot := public.rb_flip_bot_for(f.a_value);
    ch := greatest(coalesce(public.rb_cfg('flip_min_chance'), 0.49),
                   least(coalesce(public.rb_cfg('flip_max_chance'), 0.51), f.a_value::double precision / (f.a_value + total)));
    a_wins := public.rb_rand() < ch;
    a_wins := coalesce((public.rb_rig_take(p.id, 'flip', '') ->> 'win')::boolean, a_wins);   -- 4.4 rig
    found_s := public.rb_flip_find_s(f.a_value);                                            -- 9.2: longer for big flips
    choose_s := 3 + random() * 3;
    update public.rb_flips set b = null, bot_side = 'b', bot_name = bot, b_what = whats, b_value = total,
           chance_a = round(ch::numeric, 4), joined_at = now(),
           bot_found_at = now() + make_interval(secs => found_s),
           locked_at = now() + make_interval(secs => found_s + choose_s),
           flip_at = now() + make_interval(secs => found_s + choose_s + 3 + coalesce(public.rb_cfg('flip_wait_s'), 15)),
           result = case when a_wins then f.a_side else (case when f.a_side = 'black' then 'white' else 'black' end) end,
           winner_side = case when a_wins then 'a' else 'b' end, state = 'locked'
     where id = f.id returning * into f;
    return public.rb_flip_json(f, p.id);
end $$;

-- ---------------------------------------------------------------- 8. Stats of any player (9.2), and a name search
create or replace function public.rb_stats_core(me uuid, days integer) returns jsonb
language plpgsql stable security definer set search_path to '' as $$
declare n integer := greatest(7, least(coalesce(days, 30), 90)); d0 date; d1 date;
        p public.profiles%rowtype; series jsonb; games jsonb; minis jsonb;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into p from public.profiles where id = me;
    d1 := public.rb_today();
    d0 := d1 - (n - 1);
    with l as (select (at at time zone 'Europe/Paris')::date d, coins, keys, reason from public.rb_ledger
                where owner = me and at >= (d0::timestamp at time zone 'Europe/Paris')),
         x as (select (at at time zone 'Europe/Paris')::date d, amount from public.rb_xp_log
                where owner = me and at >= (d0::timestamp at time zone 'Europe/Paris')),
         dd as (select g::date d from generate_series(d0::timestamp, d1::timestamp, interval '1 day') g),
         per as (select dd.d,
                    coalesce(sum(l.coins), 0) net,
                    coalesce(sum(l.coins) filter (where l.reason = 'time'), 0) r_time,
                    coalesce(sum(l.coins) filter (where l.reason in ('login', 'daily_case')), 0) r_daily,
                    coalesce(sum(l.coins) filter (where l.reason in ('spin', 'gold_wheel')), 0) r_spin,
                    coalesce(sum(l.coins) filter (where l.reason = 'scratch'), 0) r_scratch,
                    coalesce(sum(l.coins) filter (where l.reason = 'quest'), 0) r_quest,
                    coalesce(sum(l.coins) filter (where l.reason in ('minigame', 'park', 'skill', 'golf_solo', 'golf_party',
                                                                     'wave', 'memory')), 0) r_games,
                    coalesce(sum(l.keys) filter (where l.keys > 0 and l.reason not in ('admin', 'admin_undo', 'trade',
                                                                                       'trade_undo', 'reset')), 0) keys_in,
                    coalesce(-sum(l.coins) filter (where l.reason in ('bet', 'race_bet')), 0) bet,
                    coalesce(sum(l.coins) filter (where l.reason in ('win', 'race_win')), 0) won
                   from dd left join l on l.d = dd.d group by dd.d),
         xp as (select x.d, sum(x.amount) xp from x group by x.d),
         bal as (select per.*, coalesce(xp.xp, 0) xp,
                        p.coins - coalesce(sum(per.net) over (order by per.d desc rows between unbounded preceding and 1 preceding), 0) balance
                   from per left join xp on xp.d = per.d)
    select jsonb_agg(jsonb_build_object('d', d, 'net', net, 'balance', balance, 'xp', xp, 'keys', keys_in,
                                        'bet', bet, 'won', won,
                                        'r', jsonb_build_array(r_time, r_daily, r_spin, r_scratch, r_quest, r_games))
                     order by d) into series from bal;
    with r as (select game, bet, paid, at from public.rb_rounds
                where owner = me and not open and at >= (d0::timestamp at time zone 'Europe/Paris')),
         g as (select game, count(*) rounds, sum(bet) bet, sum(paid) paid, count(*) filter (where paid > bet) wins,
                      max(paid - bet) best,
                      (select jsonb_agg(v order by at) from (select r2.paid - r2.bet v, r2.at from r r2 where r2.game = r.game
                                                             order by r2.at desc limit 40) z) last
                 from r group by game)
    select coalesce(jsonb_object_agg(game, jsonb_build_object('rounds', rounds, 'bet', bet, 'paid', paid, 'wins', wins,
                                                              'best', best, 'last', last))
                    filter (where game in ('slots', 'plinko', 'dice', 'mines', 'rocket', 'blackjack', 'roulette', 'hilo', 'tower')), '{}'),
           coalesce(jsonb_object_agg(game, jsonb_build_object('rounds', rounds, 'paid', paid, 'best', best + bet, 'last', last))
                    filter (where game in ('mini', 'park', 'memory', 'blocks', 'sweeper', 'golf_solo', 'golf_party', 'wave',
                                           'timing', 'cups', 'c4', 'colour', 'sfx')), '{}')
      into games, minis from g;
    return jsonb_build_object('days', n, 'series', coalesce(series, '[]'), 'games', games, 'minis', minis,
        'now', jsonb_build_object('coins', p.coins, 'keys', p.keys, 'level', p.level, 'xp', p.xp,
                                  'tier', public.rb_tier(me)));
end $$;
revoke all on function public.rb_stats_core(uuid, integer) from public, anon, authenticated;

create or replace function public.rb_my_stats(days integer) returns jsonb
language sql stable security definer set search_path to '' as $$
    select public.rb_stats_core(auth.uid(), days) $$;

create or replace function public.rb_player_stats(name text, days integer) returns jsonb
language plpgsql stable security definer set search_path to '' as $$
declare who uuid; nm text;
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    select id, username into who, nm from public.profiles where lower(username) = lower(name) and not banned;
    if who is null then raise exception 'rb_no_such_user'; end if;
    return public.rb_stats_core(who, days) || jsonb_build_object('name', nm, 'me', who = auth.uid());
end $$;

-- names that start with (then contain) what was typed, for the picker under the search box
create or replace function public.rb_find_players(q text) returns jsonb
language plpgsql stable security definer set search_path to '' as $$
declare s text := lower(left(coalesce(q, ''), 20));
begin
    if auth.uid() is null then raise exception 'rb_not_logged_in'; end if;
    s := replace(replace(replace(s, '\', ''), '%', ''), '_', '');
    if length(s) < 1 then return '[]'::jsonb; end if;
    return coalesce((select jsonb_agg(jsonb_build_object('name', username, 'level', lv, 'bot', bot) order by pre desc, lv desc, username)
                       from (select p.username, p.bot, public.rb_level_of(p.xp) lv, p.login like s || '%' pre
                               from public.profiles p where not p.banned and p.login like '%' || s || '%'
                              order by p.login like s || '%' desc, p.xp desc limit 8) z), '[]'::jsonb);
end $$;
revoke all on function public.rb_player_stats(text, integer), public.rb_find_players(text) from public, anon;
grant execute on function public.rb_player_stats(text, integer), public.rb_find_players(text) to authenticated;

-- the clock ticks on its own every 5 seconds (only where the database has pg_cron)
do $$
begin
    if exists (select 1 from pg_extension where extname = 'pg_cron') then
        perform cron.unschedule(jobid) from cron.job where jobname = 'rubenium-arena';
        perform cron.schedule('rubenium-arena', '5 seconds', 'select public.rb_arena_tick(); select public.rb_flip_bots_tick();');
    end if;
end $$;

commit;
