-- Rubenium 006: the hard reset for the 2.0 launch. Every account goes back to the start: 500 coins, 3 keys,
-- no items, no time played. Usernames, passwords and friends are kept.
-- Run it ONCE, when 2.0 is released. Running it again later would wipe everyone's progress again.

delete from public.rb_items;
delete from public.rb_seen;
delete from public.rb_ledger;
delete from public.rb_rounds;
delete from public.rb_requests;
delete from public.rb_case_stats;
update public.profiles
   set coins = (select value from public.rb_config where key = 'start_coins'),
       keys = (select value from public.rb_config where key = 'start_keys'),
       minutes = 0, coin_min = 0, key_min = 0, day_coins = 0, day = current_date,
       equip = '{}'::jsonb, imported = true, spin_at = null, spin_prize = null, daily_at = null;
