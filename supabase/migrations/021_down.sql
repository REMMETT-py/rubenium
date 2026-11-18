-- Undo the money side of 021 (only if something went badly wrong). Run it in Supabase -> SQL Editor.
-- Puts every price, worth and drop weight back as it was before 021, stops XP from being given, lifts all locks.
-- It does not take back XP, coupons, coinflip results or anything players did after 021.
-- The listings 021 gave back are kept in rb_bak021_listings (the items are with their owners, who can list them again).
begin;
update public.rb_catalog c set price = b.price, worth = b.worth, weight = b.weight, base_worth = b.base_worth
  from public.rb_bak021_catalog b where b.id = c.id;
update public.rb_config c set value = b.value from public.rb_bak021_config b
 where b.key = c.key and c.key in ('quick_worth_share', 'game_window_cap', 'min_build');
update public.rb_config set value = 0 where key in ('lockdown', 'price_epoch');
update public.rb_features set locked = false;
drop trigger if exists rb_rounds_xp on public.rb_rounds;
drop trigger if exists rb_golf_xp on public.rb_golf;
drop trigger if exists rb_trade_xp on public.rb_trades;
drop trigger if exists rb_quest_xp on public.rb_quest_claims;
drop trigger if exists rb_set_xp on public.rb_set_claims;
insert into public.rb_audit (admin, action, target, detail) values (null, 'update_021', 'undo', '{}'::jsonb);
commit;
