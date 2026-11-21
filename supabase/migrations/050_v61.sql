-- Rubenium 6.1. Applied live on 21/11/2026 (backups: rb_bak60_catalog, rb_bak60_cases).
-- * Badges: weight compressed to 0.625..1 inside each rarity + finish; worth = rarity base (Common 750, Rare 1 650,
--   Epic 3 650, Legendary 8 000) x finish (Basic 1, Painted 2.4, Shiny 20, Titanium 110, Gold 600) x 0.8..1.28 (rarer
--   design / colour = more). A rarer badge is always worth more than a more common one with the same finish.
-- * Cases repriced (expected worth / 0.8); Top Tier (mythic) and Royal at 20 000: Epic / Legendary only, no Basic.
-- * rb_cups: a win no longer fails ("bet" was ambiguous in the old daily-limit query); 4 failed wins repaid.
-- * rb_jackpot_advance: real players' entries weigh x1.2 when the winner is drawn; the wheel stops inside the winner's
--   real slice; the winner picks 75% of the pool (was a third).
-- * rb_leaders: boards for every casino game (g:<game>: the biggest win in one round, rb_best_win).
-- * Connect 4: rb_c4_mult easy 1.2, medium 2.5, hard 10, pro 200; Hard and Pro move first, Medium half of the time.
--   Edge function c4 v2: solver.ts (perfect play) + book.bin (tools/c4book).
create or replace function public.rb_c4_mult(level text) returns numeric language sql immutable set search_path to '' as
$$ select case level when 'easy' then 1.2 when 'medium' then 2.5 when 'hard' then 10.0 when 'pro' then 200.0 else 0 end $$;
