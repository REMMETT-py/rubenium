-- 4.0 follow-up: pin search_path on five pure helper functions (Supabase lint 0011).
-- They only call built-ins (pg_catalog is always searched), so behaviour is unchanged.
-- Also indexes the foreign keys Supabase lint 0001 lists (faster account deletion and market lookups).
-- Undo: ALTER FUNCTION ... RESET search_path; DROP INDEX the rb_fk_* indexes.
begin;
alter function public.rb_login_rewards() set search_path = '';
alter function public.rb_tap_max(jsonb) set search_path = '';
alter function public.rb_today() set search_path = '';
alter function public.rb_duel_cap(bigint, bigint) set search_path = '';
alter function public.rb_timing_pos(jsonb, double precision) set search_path = '';
create index if not exists rb_fk_devices_owner on public.rb_devices(owner);
create index if not exists rb_fk_giveaway_entries_owner on public.rb_giveaway_entries(owner);
create index if not exists rb_fk_items_item on public.rb_items(item);
create index if not exists rb_fk_listings_buyer on public.rb_listings(buyer);
create index if not exists rb_fk_listings_seller on public.rb_listings(seller);
create index if not exists rb_fk_mutes_who on public.rb_mutes(who);
create index if not exists rb_fk_offers_buyer on public.rb_offers(buyer);
create index if not exists rb_fk_park_level on public.rb_park(level);
create index if not exists rb_fk_reactions_who on public.rb_reactions(who);
commit;
