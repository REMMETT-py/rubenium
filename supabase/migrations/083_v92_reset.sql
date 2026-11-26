-- Rubenium 9.2, the reset. rb_reset_92(og_keep_level) runs once (config reset_092); a copy of every table it changes
-- is kept in rb_bak92_*.
--
-- Everyone (bots too): every leaderboard starts again (config board_from, the Hours board counts from now), streaks
-- to 0, quests start again, bots' made-up board numbers go.
-- Every player (not bots): coins and keys to 0, then 2 500 coins and 5 keys (the starter pack, once: nobody gets it
-- twice). Tier back to Poor; it comes back by itself from what you own. Items, cases and trophies are kept...
-- ...except for players with the OG tag: they lose every item but the OG tag, every unopened case, gold keys and
-- wheels, and every trophy, then get the full starter pack (3 Starter and 5 Standard Cases too). They keep their
-- account, friends and the OG tag, and their level unless og_keep_level is false.
-- Anything in play that holds coins or items ends with no pay (items go back to their owners first). Bots' Jackpot
-- entries and race bets stay, so the arena never stops.
begin;

create or replace function public.rb_reset_92(og_keep_level boolean) returns jsonb
language plpgsql security definer set search_path to '' as $$
declare og uuid[]; n integer; gone integer; p record;
begin
    if coalesce(public.rb_cfg('reset_092'), 0) <> 0 then raise exception 'rb_already_done'; end if;

    create table public.rb_bak92_profiles as select *, now() as saved_at from public.profiles;
    create table public.rb_bak92_items as select * from public.rb_items;
    create table public.rb_bak92_stock as select * from public.rb_case_stock;
    create table public.rb_bak92_ach as select * from public.rb_ach;
    create table public.rb_bak92_quest_claims as select * from public.rb_quest_claims;
    create table public.rb_bak92_config as select * from public.rb_config;
    alter table public.rb_bak92_profiles enable row level security;
    alter table public.rb_bak92_items enable row level security;
    alter table public.rb_bak92_stock enable row level security;
    alter table public.rb_bak92_ach enable row level security;
    alter table public.rb_bak92_quest_claims enable row level security;
    alter table public.rb_bak92_config enable row level security;
    revoke all on public.rb_bak92_profiles, public.rb_bak92_items, public.rb_bak92_stock, public.rb_bak92_ach,
                  public.rb_bak92_quest_claims, public.rb_bak92_config from public, anon, authenticated;

    og := array(select distinct i.owner from public.rb_items i join public.profiles pr on pr.id = i.owner
                 where i.item = 'tag:og' and not pr.bot);

    -- anything players have in play ends with no pay; the items it held go back first
    update public.rb_duels set state = 'cancelled', why = 'reset' where state not in ('done', 'cancelled');
    update public.rb_flips set state = 'cancelled', why = 'reset', done_at = now() where state not in ('done', 'cancelled');
    update public.rb_trades set state = 'cancelled', why = 'reset', updated = now() where state not in ('done', 'cancelled');
    update public.rb_golf set state = 'cancelled', why = 'reset', done_at = now() where state not in ('done', 'cancelled');
    update public.rb_golf_parties set state = 'cancelled', done_at = now() where state not in ('done', 'cancelled');
    update public.rb_golf_solo set state = 'quit', done_at = now() where state not in ('done', 'quit');
    update public.rb_wave_duels set state = 'cancelled', why = 'reset', done_at = now() where state not in ('done', 'cancelled');
    update public.rb_wave_runs set state = 'quit', done_at = now() where state not in ('done', 'quit');
    if to_regclass('public.rb_c4') is not null then
        execute 'update public.rb_c4 set state = ''done'', paid = 0, updated_at = now() where state <> ''done''';
    end if;
    update public.rb_bg set state = 'cancelled', why = 'reset', done_at = now() where state in ('open', 'live');
    update public.rb_item_swaps set state = 'cancelled', done_at = now() where state = 'open';
    update public.rb_offers set state = 'gone' where state = 'open';
    update public.rb_listings set state = 'cancelled' where state = 'open';
    with gone_e as (delete from public.rb_jackpot_entries e using public.rb_jackpots j
                     where j.id = e.jackpot and j.state not in ('done', 'empty') and e.owner is not null
                    returning e.jackpot, e.value)
    update public.rb_jackpots j set total = greatest(0, j.total - s.v)
      from (select jackpot, sum(value) v from gone_e group by jackpot) s where s.jackpot = j.id;
    with gone_b as (delete from public.rb_race_bets b using public.rb_races r
                     where r.id = b.race and r.state <> 'done' and b.owner is not null
                    returning b.race, b.amount)
    update public.rb_races r set total = greatest(0, r.total - s.v)
      from (select race, sum(amount) v from gone_b group by race) s where s.race = r.id;
    update public.rb_rounds set open = false, paid = 0 where open;
    update public.rb_mg set open = false, void = true where open;
    update public.rb_items set locked = null where locked is not null;

    -- OG players: everything but the OG tag
    delete from public.rb_items i where i.owner = any(og) and i.item <> 'tag:og';
    get diagnostics gone = row_count;
    delete from public.rb_case_stock where owner = any(og);
    delete from public.rb_ach where owner = any(og);
    update public.profiles set gold_keys = 0, gold_wheels = 0, rig_gold = false, og_coupon_50 = false,
                               equip = equip - 'trophy1' - 'trophy2' - 'trophy3'
     where id = any(og);
    if not og_keep_level then
        update public.profiles set xp = 0, level = 0, xp_day = null, xp_day_gain = 0, xp_day_src = '{}'::jsonb,
                                   xp_hr = null, xp_hr_src = '{}'::jsonb
         where id = any(og);
    end if;

    -- every player: coins and keys to 0, then the starter coins and keys (once)
    update public.profiles
       set coins = 2500, keys = 5, tier_floor = 0, coin_min = 0, key_min = 0, day = current_date, day_coins = 0
     where not bot;
    get diagnostics n = row_count;
    insert into public.rb_ledger (owner, coins, keys, reason, ref)
        select id, 2500, 5, 'gift', '9.2 reset: starter pack' from public.profiles where not bot;
    for p in select unnest(og) as id loop
        perform public.rb_starter_pack(p.id);                                   -- their cases went: the cases again
    end loop;
    for p in select id from public.profiles where not bot loop
        perform public.rb_fix_equip(p.id);
    end loop;

    -- everyone, bots too: boards, streaks, quests
    update public.rb_config set value = extract(epoch from now())::bigint where key = 'board_from';
    update public.profiles set board_min0 = minutes, streak = 0, streak_day = null;
    update public.profiles set bot_cfg = bot_cfg - 'stats' where bot and bot_cfg ? 'stats';
    delete from public.rb_quest_claims;

    insert into public.rb_config (key, value) values ('reset_092', 1) on conflict (key) do update set value = 1;
    return jsonb_build_object('players', n, 'og_players', coalesce(array_length(og, 1), 0), 'og_items_removed', gone);
end $$;
revoke all on function public.rb_reset_92(boolean) from public, anon, authenticated;

commit;
