# Setup (for the project owner)

1. Supabase > Authentication > Sign In / Providers > Email: switch **Confirm email** OFF, Save.
2. Supabase > SQL Editor > New query: paste the whole content of each file in `supabase/migrations/`
   (in number order) and press **Run**. Running a file twice does no harm.
3. Never share the secret key (`sb_secret_...`). If it was shared, Settings > API Keys > delete it and create a new one.
4. Updating from 2.1: run only `008_ultimate_update.sql` (it already contains 007). Do not run 006 again.
5. Updating from 2.2: run only `009_parking_no_gold.sql`.
6. Updating from 2.3: run only `010_big_update.sql` (once, before opening 2.4).
7. Updating to 2.6: run `011_profiles_fresh_start.sql` once, after 010. It resets every account's coins, keys, items, spins and cases (saved first in the rb_bak26_* tables), gives the OG tag to every account made before 17 November, and makes apps older than 2.6 update before playing online. Running it again never resets a second time.
8. Then run `012_case_balance.sql` once (2.6.1: the case balance and shop prices). Safe to run again.
9. Then run `013_final.sql` once (2.7: AFK money, new banners and frames). Safe to run again.
10. Then run `014_v3.sql` once (3.0: style cases, device rule, bots, admin swaps with the "swaps" storage bucket). Safe to run again. Apps older than 3.0 must update.
11. Then run `015_final_300.sql` once (3.0.0: duel bet slider rule, balls and banners re-ranked, 10 new banners, gold banners, song history for friends). Safe to run again. Apps older than 3.0.0 must update.
12. Then run `016_live_golf.sql` once (3.0.0 final: live Mini Golf 1v1, OG event of 16/11/2026 with gold keys, rarer top drops, 1 key every 15 minutes up to 5, market open from the start, better mini game pay). Safe to run again. To move the OG event end, change `og_event_until` in the `rb_config` table (a Unix time).
13. Then run `017_quick_fixes.sql` once (closes the OG tag and the OG event, worth = shop price everywhere, better quick sell for badges, 16 golf holes). Safe to run again.
14. Then run `018_v31.sql` once (3.1: streak AFK bonus, new quests, Golden Wheel, Timing, 5 new cases, Titanium in the shop, gold banner choice, admin test tools). Safe to run again. Apps older than 3.1 must update.
15. Then run `019_fixes31.sql` once (Royal Case nerf, style cases without a key, market usual price fixed). Safe to run again.
16. Then run `020_v32.sql` once (3.2: ONLINE mode, Coinflip, golf and coinflip lobbies, 5 golf holes, Roulette and Hi-Lo, cases bought with coins and opened with a key, tradeable keys, 1 key every 30 min up to 12 and a full key wallet for everyone, item worth and 20% shop tax, new cosmetics and cases, advent calendar, chat limits). Safe to run again. Apps older than 3.2 must update.
17. Then run `021_v40.sql` once (4.0: levels and XP, XP coupons and the OG coupon, LOCKDOWN and live feature locks, economy prices, every open market listing given back to its owner, Tower, Keno, Limbo, roulette numbers, 2048 and Minesweeper, coinflip bots and admin offers, 40 golf holes, advent for everyone, chat reactions, market search, trade inventory and summary, the storage read rule that RL Swap uploads need). It is one transaction and safe to run again. `021_down.sql` puts the old prices and settings back if ever needed (items and coins are never touched). Apps older than 4.0 must update.
