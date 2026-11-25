-- 9.0 fresh start. This file only adds the reset; it runs once, by hand, after the owner says go:
--   select public.rb_reset_economy_90(1000, 3);
-- Everyone goes back to the same start (coins and keys given). Kept: accounts, hours, friends, every cosmetic and
-- item, what is equipped, XP and levels, achievements, scores and history. Gone: coins, keys, gold keys and wheels,
-- unopened cases, timers and streaks, rigs, and anything in play (bets, duels, flips, trades, swaps, jackpots,
-- giveaways), whose items go back to their owners. A copy of every changed table is kept in rb_bak90_*.

create or replace function public.rb_reset_economy_90(start_coins bigint, start_keys integer)
returns jsonb language plpgsql security definer set search_path to '' as $$
declare n integer;
begin
    if coalesce(public.rb_cfg('reset_090'), 0) <> 0 then raise exception 'rb_already_done'; end if;
    if start_coins is null or start_coins < 0 or start_keys is null or start_keys < 0 then
        raise exception 'rb_bad_amount';
    end if;

    create table public.rb_bak90_profiles as select *, now() as saved_at from public.profiles;
    create table public.rb_bak90_items as select * from public.rb_items;
    create table public.rb_bak90_stock as select * from public.rb_case_stock;
    create table public.rb_bak90_ledger as select * from public.rb_ledger;
    create table public.rb_bak90_play as
        select 'duels' as kind, to_jsonb(x) as row from public.rb_duels x where state not in ('done', 'cancelled')
        union all select 'flips', to_jsonb(x) from public.rb_flips x where state not in ('done', 'cancelled')
        union all select 'trades', to_jsonb(x) from public.rb_trades x where state not in ('done', 'cancelled')
        union all select 'golf', to_jsonb(x) from public.rb_golf x where state not in ('done', 'cancelled')
        union all select 'golf_parties', to_jsonb(x) from public.rb_golf_parties x where state not in ('done', 'cancelled')
        union all select 'wave_duels', to_jsonb(x) from public.rb_wave_duels x where state not in ('done', 'cancelled')
        union all select 'jackpots', to_jsonb(x) from public.rb_jackpots x where state not in ('done', 'empty')
        union all select 'jackpot_entries', to_jsonb(x) from public.rb_jackpot_entries x
        union all select 'race_bets', to_jsonb(x) from public.rb_race_bets x
        union all select 'giveaway_entries', to_jsonb(x) from public.rb_giveaway_entries x
        union all select 'rounds', to_jsonb(x) from public.rb_rounds x where open
        union all select 'rigs', to_jsonb(x) from public.rb_rigs x;
    alter table public.rb_bak90_profiles enable row level security;
    alter table public.rb_bak90_items enable row level security;
    alter table public.rb_bak90_stock enable row level security;
    alter table public.rb_bak90_ledger enable row level security;
    alter table public.rb_bak90_play enable row level security;
    revoke all on public.rb_bak90_profiles, public.rb_bak90_items, public.rb_bak90_stock, public.rb_bak90_ledger,
                  public.rb_bak90_play from public, anon, authenticated;

    -- anything in play ends with no pay; items held by it go back to their owners
    update public.rb_duels set state = 'cancelled', why = 'reset' where state not in ('done', 'cancelled');
    update public.rb_flips set state = 'cancelled', why = 'reset', done_at = now() where state not in ('done', 'cancelled');
    update public.rb_trades set state = 'cancelled', why = 'reset', updated = now() where state not in ('done', 'cancelled');
    update public.rb_golf set state = 'cancelled', why = 'reset', done_at = now() where state not in ('done', 'cancelled');
    update public.rb_golf_parties set state = 'cancelled', done_at = now() where state not in ('done', 'cancelled');
    update public.rb_golf_solo set state = 'quit', done_at = now() where state not in ('done', 'quit');
    update public.rb_wave_duels set state = 'cancelled', why = 'reset', done_at = now()
     where state not in ('done', 'cancelled');
    update public.rb_wave_runs set state = 'quit', done_at = now() where state not in ('done', 'quit');
    update public.rb_c4 set state = 'done', paid = 0, updated_at = now() where state <> 'done';
    update public.rb_item_swaps set state = 'cancelled', done_at = now() where state = 'open';
    update public.rb_offers set state = 'gone' where state = 'open';
    update public.rb_listings set state = 'cancelled' where state = 'open';
    delete from public.rb_jackpot_entries
     where jackpot in (select id from public.rb_jackpots where state not in ('done', 'empty'));
    update public.rb_jackpots set state = 'empty', total = 0 where state not in ('done', 'empty');
    delete from public.rb_race_bets where race in (select id from public.rb_races where state <> 'done');
    delete from public.rb_giveaway_entries
     where giveaway in (select id from public.rb_giveaways where state = 'live');
    update public.rb_giveaways set state = 'cancelled', ends_at = least(ends_at, now()) where state = 'live';
    update public.rb_rounds set open = false, paid = 0 where open;
    update public.rb_mg set open = false, void = true where open;
    update public.rb_items set locked = null
     where split_part(locked, ':', 1) in ('flip', 'jackpot', 'market', 'trade', 'swap');
    truncate public.rb_case_stock, public.rb_rigs, public.rb_requests, public.rb_deal_buys;

    update public.profiles
       set coins = start_coins, keys = start_keys, gold_keys = 0, gold_wheels = 0, rig_gold = false,
           coin_min = 0, key_min = 0, day = current_date, day_coins = 0,
           spin_at = null, spin_prize = null, daily_at = null, scratch_at = null, streak = 0, streak_day = null;
    get diagnostics n = row_count;

    insert into public.rb_ledger (owner, coins, keys, reason, ref)
        select id, start_coins::int, start_keys, 'reset', '9.0' from public.profiles;
    insert into public.rb_config (key, value) values ('reset_090', 1) on conflict (key) do update set value = 1;
    return jsonb_build_object('players', n, 'coins', start_coins, 'keys', start_keys);
end $$;
revoke all on function public.rb_reset_economy_90(bigint, integer) from public, anon, authenticated;
