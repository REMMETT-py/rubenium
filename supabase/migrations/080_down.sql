-- Undo of 080_v91_arena.sql: made by overhaul/db/make_down.py from the server as it was before it.
begin;
-- the functions 080 changed in place go back as they were
do $undo$
declare fn text; src text;
begin
    foreach fn in array array['rb_flip_list', 'rb_jackpot_state', 'rb_live', 'rb_race_state', 'rb_advent',
                              'rb_feature_cleanup', 'rb_stats', 'rb_my_stats'] loop
        for src in select pg_get_functiondef(p.oid) from pg_proc p join pg_namespace n on n.oid = p.pronamespace
                    where n.nspname = 'public' and p.proname = fn loop
            execute replace(replace(replace(replace(src,
                'public.rb_feature_open(', 'public.rb_feature_on('),
                'n := n + public.rb_bg_cleanup(f);' || chr(10) || '    ', ''),
                'public.rb_stats_real(who)::jsonb || public.rb_stats_91(who);', 'public.rb_stats_real(who)::jsonb;'),
                ', ''reversi'', ''ships'')), ''{}'')', ')), ''{}'')');
        end loop;
    end loop;
end $undo$;
drop function if exists public.c4_drop cascade;
drop function if exists public.c4_wins cascade;
drop function if exists public.rb_admin_held cascade;
drop function if exists public.rb_admin_replay cascade;
drop function if exists public.rb_admin_replays cascade;
drop function if exists public.rb_bg_apply cascade;
drop function if exists public.rb_bg_base cascade;
drop function if exists public.rb_bg_bot cascade;
drop function if exists public.rb_bg_bot_turns cascade;
drop function if exists public.rb_bg_busy cascade;
drop function if exists public.rb_bg_cancel cascade;
drop function if exists public.rb_bg_cleanup cascade;
drop function if exists public.rb_bg_create cascade;
drop function if exists public.rb_bg_duel_wins cascade;
drop function if exists public.rb_bg_end cascade;
drop function if exists public.rb_bg_join cascade;
drop function if exists public.rb_bg_json cascade;
drop function if exists public.rb_bg_lobbies cascade;
drop function if exists public.rb_bg_move cascade;
drop function if exists public.rb_bg_new_board cascade;
drop function if exists public.rb_bg_points cascade;
drop function if exists public.rb_bg_resign cascade;
drop function if exists public.rb_bg_shuffle cascade;
drop function if exists public.rb_bg_state cascade;
drop function if exists public.rb_bg_tick cascade;
drop function if exists public.rb_bg_tick_mine cascade;
drop function if exists public.rb_bg_turn_secs cascade;
drop function if exists public.rb_feature_open cascade;
drop function if exists public.rb_integrity cascade;
drop function if exists public.rb_is_admin_now cascade;
CREATE OR REPLACE FUNCTION public.rb_leaders(kind text, friends boolean)
 RETURNS json
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare me uuid := auth.uid();
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    if kind not in ('coins', 'worth', 'badges', 'hours', 'streak', 'tap', 'park', 'memory', 'level',
                    'wave', 'flips', 'golf', 'c4', 'cups', 'trophies')
       and kind not in ('g:roulette', 'g:blackjack', 'g:hilo', 'g:slots', 'g:rocket', 'g:plinko', 'g:mines', 'g:tower',
                        'g:dice', 'g:timing', 'g:colour', 'g:sfx') then raise exception 'rb_bad_choice'; end if;
    return (with who as (select p.* from public.profiles p where not p.banned
                          and (not coalesce(friends, false) or p.id = me or public.rb_is_friend(me, p.id))),
            v as (select w.id, w.username, (case kind
                when 'coins' then w.coins when 'level' then w.xp
                when 'hours' then w.minutes / 60
                when 'streak' then (case when w.streak_day >= public.rb_today() - 1 then w.streak else 0 end)
                when 'worth' then (select coalesce(sum(public.rb_worth(c.id)), 0) from public.rb_items it join public.rb_catalog c on c.id = it.item where it.owner = w.id)
                when 'badges' then (select count(distinct it.item) from public.rb_items it where it.owner = w.id and it.item like 'badge:%')
                when 'tap' then (select coalesce(max((r.secret ->> 'pct')::int), 0) from public.rb_rounds r where r.owner = w.id and r.game = 'mini')
                when 'park' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game = 'park')
                when 'memory' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game = 'memory')
                when 'wave' then greatest(public.rb_wave_best(w.id) / 100, coalesce((w.bot_cfg -> 'stats' ->> 'wave')::bigint, 0))
                when 'flips' then (select count(*) from public.rb_flips f where f.winner = w.id and f.state = 'done')
                                  + coalesce((w.bot_cfg -> 'stats' ->> 'flip')::bigint, 0)
                when 'golf' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game in ('golf', 'golf_party', 'golf_solo'))
                                 + coalesce((w.bot_cfg -> 'stats' ->> 'golf')::bigint, 0)
                when 'c4' then (select count(*) from public.rb_c4 g where g.owner = w.id and g.outcome = 'win')
                when 'cups' then (select count(*) from public.rb_rounds r where r.owner = w.id and r.game = 'cups' and r.paid > r.bet)
                when 'g:roulette' then public.rb_best_win(w.id, 'roulette') when 'g:blackjack' then public.rb_best_win(w.id, 'blackjack')
                when 'g:hilo' then public.rb_best_win(w.id, 'hilo') when 'g:slots' then public.rb_best_win(w.id, 'slots')
                when 'g:rocket' then public.rb_best_win(w.id, 'rocket') when 'g:plinko' then public.rb_best_win(w.id, 'plinko')
                when 'g:mines' then public.rb_best_win(w.id, 'mines') when 'g:tower' then public.rb_best_win(w.id, 'tower')
                when 'g:dice' then public.rb_best_win(w.id, 'dice') when 'g:timing' then public.rb_best_win(w.id, 'timing') when 'g:colour' then public.rb_best_win(w.id, 'colour') when 'g:sfx' then public.rb_best_win(w.id, 'sfx')
                else (select count(*) from public.rb_ach a where a.owner = w.id) end)::bigint as val
                  from who w),
            ranked as (select v.*, rank() over (order by val desc) rk from v where val > 0 or v.id = me)
        select json_build_object(
            'top', coalesce((select json_agg(json_build_object('rank', rk, 'name', username, 'value', val, 'me', id = me) order by rk, username)
                               from (select * from ranked order by rk, username limit 50) t), '[]'::json),
            'me', (select json_build_object('rank', rk, 'value', val) from ranked where id = me)));
end $function$;
CREATE OR REPLACE FUNCTION public.rb_need_feature(f text)
 RETURNS void
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
begin
    if coalesce(public.rb_cfg('lockdown'), 0) > 0 then raise exception 'rb_lockdown'; end if;
    if not public.rb_feature_on(f) then raise exception 'rb_feature_locked'; end if;
end $function$;
CREATE OR REPLACE FUNCTION public.rb_skill_pay(who uuid, g text, base integer)
 RETURNS integer
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare w jsonb := public.rb_skill_window(who, g); n integer := (w ->> 'rounds')::int; fr integer := (w ->> 'full')::int;
        pay integer;
begin
    if coalesce(base, 0) <= 0 then return 0; end if;
    pay := public.rb_scaled(round(base * coalesce(public.rb_cfg('skill_pay_mult'), 1))::int, public.rb_tier_mult(who));
    if n >= fr * 2 then pay := pay / 4; elsif n >= fr then pay := pay / 2; end if;
    pay := greatest(0, least(pay, (w ->> 'cap')::int - (w ->> 'paid')::int));
    if pay > 0 then
        perform public.rb_pay(who, pay, 0, 'skill', g);
        perform public.rb_key_find(who, g);
    end if;
    return pay;
end $function$;
CREATE OR REPLACE FUNCTION public.rb_skill_state()
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare me uuid := auth.uid(); out_ jsonb := '{}'::jsonb; g text;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    foreach g in array array['timing', 'cups', 'c4', 'colour', 'sfx'] loop
        out_ := out_ || jsonb_build_object(g, public.rb_skill_window(me, g));
    end loop;
    return out_ || jsonb_build_object('mult', public.rb_tier_mult(me),
        'resets', greatest(0, ceil(extract(epoch from (((public.rb_today() + 1)::timestamp at time zone 'Europe/Paris') - now()))))::int);
end $function$;
drop function if exists public.rb_skill_top cascade;
CREATE OR REPLACE FUNCTION public.rb_skill_window(who uuid, g text)
 RETURNS jsonb
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO ''
AS $function$
    select jsonb_build_object('rounds', count(*), 'paid', coalesce(sum(paid), 0),
                              'full', coalesce(public.rb_cfg('skill_full_rounds'), 6)::int,
                              'cap', floor(coalesce(public.rb_cfg('skill_day_cap'), 900) * public.rb_tier_mult(who))::int)
      from public.rb_rounds
     where owner = who and game = g and not open and bet = 0
       and at >= (public.rb_today()::timestamp at time zone 'Europe/Paris') $function$;
drop function if exists public.rb_stats_91 cascade;
drop function if exists public.rv_bot cascade;
drop function if exists public.rv_count cascade;
drop function if exists public.rv_eval cascade;
drop function if exists public.rv_flips cascade;
drop function if exists public.rv_moves cascade;
drop function if exists public.rv_play cascade;
drop function if exists public.rv_search cascade;
drop function if exists public.sh_bot cascade;
drop function if exists public.sh_fleet cascade;
drop function if exists public.sh_shoot cascade;
delete from public.rb_config where key = 'arena_fee';
delete from public.rb_config where key = 'arena_open_min';
update public.rb_config set value = 900 where key = 'skill_day_cap';
delete from public.rb_config where key = 'skill_fresh_mult';
delete from public.rb_config where key = 'skill_fresh_rounds';
update public.rb_config set value = 1 where key = 'skill_pay_mult';
drop table if exists public.rb_bg, public.rb_held, public.rb_skill_log, public.rb_trusted cascade;
delete from public.rb_features where name = 'arena';
commit;
