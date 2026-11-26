-- Rubenium 9.3.2: the Stats tab shows all time only, and every stat starts again from 0.
-- Nothing is deleted: stats count from rb_config 'stats_from' (a Unix time), set here to the moment this runs.
-- Undo (all the history comes back): update public.rb_config set value = 0 where key = 'stats_from';
-- What restarts from 0: the Stats tab (Overview, Casino, Mini games, Rewards) and the counters in Records (rounds,
-- bets, wins, cases, spins, duels, flips, Connect 4, golf, cups, board games, Arena, horses, skill games, Wave best).
-- What does not change: coins, keys, items, badges, level, tiers, trophies, friends, leaderboards and history lists.
-- Safe to run twice (it only sets stats_from the first time).
begin;

insert into public.rb_config (key, value) values ('stats_from', extract(epoch from now())::bigint)
    on conflict (key) do nothing;

create or replace function public.rb_stats_from() returns timestamptz
language sql stable security definer set search_path to '' as $$
    select to_timestamp(coalesce(public.rb_cfg('stats_from'), 0)) $$;
revoke all on function public.rb_stats_from() from public, anon, authenticated;

-- days 0 (or null): all time, from the reset; 7 to 90 (older apps): that window, never before the reset
create or replace function public.rb_stats_core(me uuid, days integer) returns jsonb
language plpgsql stable security definer set search_path to '' as $$
declare n integer; d0 date; d1 date; f timestamptz := public.rb_stats_from(); t0 timestamptz;
        p public.profiles%rowtype; series jsonb; games jsonb; minis jsonb;
begin
    if me is null then raise exception 'rb_not_logged_in'; end if;
    select * into p from public.profiles where id = me;
    d1 := public.rb_today();
    if coalesce(days, 0) <= 0 then
        n := greatest(1, least(365, d1 - (f at time zone 'Europe/Paris')::date + 1));
    else
        n := greatest(7, least(days, 90));
    end if;
    d0 := d1 - (n - 1);
    t0 := greatest(d0::timestamp at time zone 'Europe/Paris', f);
    with l as (select (at at time zone 'Europe/Paris')::date d, coins, keys, reason from public.rb_ledger
                where owner = me and at >= t0),
         x as (select (at at time zone 'Europe/Paris')::date d, amount from public.rb_xp_log
                where owner = me and at >= t0),
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
                where owner = me and not open and at >= t0),
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
    return jsonb_build_object('days', n, 'all', coalesce(days, 0) <= 0, 'series', coalesce(series, '[]'), 'games', games,
        'minis', minis,
        'now', jsonb_build_object('coins', p.coins, 'keys', p.keys, 'level', p.level, 'xp', p.xp,
                                  'tier', public.rb_tier(me)));
end $$;
revoke all on function public.rb_stats_core(uuid, integer) from public, anon, authenticated;

-- Records: the counters count from the reset too. These two functions exist only on the live server (not in a
-- repo-only replay), so they are replaced only where their tables are there.
do $do$
begin
    if to_regclass('public.rb_duels') is null or to_regclass('public.rb_ach') is null or to_regclass('public.rb_bg') is null then
        return;
    end if;
    execute $f$
create or replace function public.rb_stats_real(who uuid) returns json
language sql stable security definer set search_path to '' as $$
    with r as (select * from public.rb_rounds where owner = who and not open and at >= public.rb_stats_from()),
         g as (select * from r where game in ('slots', 'plinko', 'dice', 'mines', 'rocket', 'blackjack'))
    select json_build_object(
        'bet', (select coalesce(sum(bet), 0) from g), 'won', (select coalesce(sum(paid), 0) from g),
        'best', (select coalesce(max(paid), 0) from g), 'rounds', (select count(*) from g),
        'cases', (select count(*) from r where game like 'case:%' or game = 'daily'),
        'spins', (select count(*) from r where game = 'spin'),
        'mini', (select count(*) from r where game = 'mini'),
        'park', (select count(*) from r where game = 'park'), 'memory', (select count(*) from r where game = 'memory'),
        'duels', (select count(*) from public.rb_duels d where d.state = 'done' and d.winner = who and d.at >= public.rb_stats_from()),
        'streak', (select streak from public.profiles where id = who),
        'worth', (select coalesce(sum(public.rb_worth(c.id)), 0) from public.rb_items it join public.rb_catalog c on c.id = it.item
                   where it.owner = who),
        'first_case', (select min(at) from r where game like 'case:%'),
        'gold', (select count(*) from public.rb_items it join public.rb_catalog c on c.id = it.item
                  where it.owner = who and c.kind = 'badge' and c.cls = 4),
        'trades', (select count(*) from public.rb_trades t where t.state = 'done' and (t.a = who or t.b = who)),
        'items', (select count(*) from public.rb_items it where it.owner = who),
        'badges', (select count(distinct it.item) from public.rb_items it where it.owner = who and it.item like 'badge:%'),
        'friends', (select count(*) from public.rb_friends f where f.ok and (f.a = who or f.b = who)),
        'wave', public.rb_wave_best_since(who, public.rb_stats_from()) / 100,
        'flip', (select count(*) from public.rb_flips f where f.winner = who and f.state = 'done'
                   and coalesce(f.done_at, f.at) >= public.rb_stats_from()),
        'golf', (select count(*) from r where game in ('golf', 'golf_party', 'golf_solo')),
        'c4', (select count(*) from public.rb_c4 c where c.owner = who and c.outcome = 'win'
                 and coalesce(c.updated_at, c.created_at) >= public.rb_stats_from()),
        'cups', (select count(*) from r where game = 'cups' and paid > bet),
        'trophies', (select count(*) from public.rb_ach a where a.owner = who)) $$;
$f$;
    execute $f$
create or replace function public.rb_stats_91(who uuid) returns jsonb
language sql stable security definer set search_path to '' as $$
    select jsonb_build_object(
        'reversi', (select count(*) from public.rb_bg g where g.a = who and g.b is null and g.kind = 'reversi' and g.winner = 1
                      and coalesce(g.done_at, g.at) >= public.rb_stats_from()),
        'ships', (select count(*) from public.rb_bg g where g.a = who and g.b is null and g.kind = 'ships' and g.winner = 1
                    and coalesce(g.done_at, g.at) >= public.rb_stats_from()),
        'arena', (select count(*) from public.rb_bg g where g.b is not null and g.state = 'done'
                    and g.done_at >= greatest(public.rb_board_from(), public.rb_stats_from())
                    and ((g.winner = 1 and g.a = who) or (g.winner = 2 and g.b = who))),
        'arena_played', (select count(*) from public.rb_bg g where (g.a = who or g.b = who) and g.b is not null and g.state = 'done'
                           and g.done_at >= public.rb_stats_from()),
        'insane', (select count(*) from public.rb_bg g where g.a = who and g.b is null and g.level = 'insane' and g.winner = 1
                     and coalesce(g.done_at, g.at) >= public.rb_stats_from()),
        'horses', (select coalesce(max(b.paid - b.amount), 0) from public.rb_race_bets b where b.owner = who and b.paid > b.amount
                     and b.at >= public.rb_stats_from()),
        'skill', (select coalesce(sum(r.paid), 0) from public.rb_rounds r where r.owner = who
                   and r.game in ('timing', 'cups', 'c4', 'colour', 'sfx', 'reversi', 'ships') and r.bet = 0
                   and r.at >= public.rb_stats_from())) $$;
$f$;
end $do$;

commit;
