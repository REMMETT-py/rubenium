# Decisions

Choices made where the request left room, newest last.

## Accounts (1.7)
- The app is Python (PyQt6), not Electron. "Secure storage" is Windows data protection (DPAPI): the saved login
  can only be read by the same Windows user on the same PC. File: `Documents\Rubenium\session.dat` (corrected in 8.0; it has always been there).
- Supabase needs an e-mail, so a username becomes `<username in lower case>@users.rubenium.app`. No mail is ever
  sent. "Confirm email" must be OFF in Supabase.
- Usernames: 3 to 10 letters or numbers, unique whatever the capitals. The database refuses any account that does
  not follow this (a trigger on new users), so nobody can make an odd account by calling the server directly.
- No password recovery (there is no e-mail). The project owner can reset a password by hand in Supabase
  (Authentication > Users). An optional e-mail can be added later.
- Login rate limits are Supabase's own (per IP).
- Only the publishable key is in the app. The secret key is never used by the app or stored in this repository.
- Time played is counted by the server: one heartbeat a minute while the app is in use (music playing, or mouse /
  keyboard used in the last 10 minutes), at most one minute per minute, one PC at a time per account.
- Offline with a saved login: the app still launches and works; the time simply is not counted.
- Log out is on the welcome screen. Settings also has "Log out", which closes Rubenium (the next start asks to
  log in).
- Style is locked: strong glow, black background, round corners.
- Coins, items and games are still stored on the PC in 1.7. They move to the server in the next stages; the
  one-time import of old progress happens then.

## 1.8
- The login form lives inside the welcome card (the card grows to hold it), not under it.
- The hidden code on the Launch button was removed.
- Account deletion: its own small window (typing needs the keyboard; the menu never takes it from a game). The
  username must be typed exactly, then the button needs two clicks and a hold. The server checks the name again.
- Quit is a small link at the bottom of Settings (with a confirmation) and stays in the tray menu.
- Lantern Lift, Monsoon and Electric banner are gone for good; every version of their files is still recognised
  so the original game file is restored for anyone who had one on.

## 2.0 (the online economy)
- Hard reset: every account starts at 500 coins and 3 keys (006_fresh_start.sql). No import of old progress.
- Progression: 3 balls (Classic 0 h, White Gold 30 h, Gold 100 h), 3 rings (Line 0 h, White Gold 40 h, Gold 125 h),
  8 themes (0, 2, 12, 20, 55, 75, 150, 200 h). Not tradeable, never sold.
- Colours of the menu (colour 1, colour 2, the music's colours) are free for everyone.
- Black / White / Gold badges and the 5 Exotic badges only come from cases (and, later, trading).
- The casino shows the bet leaving at once and the prize when the animation ends; the server did both already.
- A round left open (app closed mid-hand) is picked up again the next time that game is started.
- Not in 2.0 yet: the 10 balls / 10 lines / 5 fonts / shop themes, quests, the minigame, trading, the market.

## 2.2 (the Ultimate Update)
- One more economy reset (inside 008, runs once): coins, keys, items, market, trades and history start again.
  Accounts, hours played and friends stay.
- Badges: 12 Common, 12 Rare, 12 Epic, 12 Legendary, 6 Mythic (the 6th is the Rubenium R, the rarest).
  Finishes, from easiest: Basic (grey), Painted (8 colours), Shiny (5 bright colours, no glow), Titanium
  (black / white, a little glow, Epic and Legendary only), Gold (a lot of glow). Mythic: Titanium, then the
  multi-colour Prismatic, then Gold. A Basic badge can be worn as soon as any colour of it is owned.
- Odds: Gold is about 1 badge in 5 000; the Gold Rubenium R is about 1 in 220 000 Mythic Hunt openings.
  No guaranteed drops and no "Epic within 10" text: everything is luck. When a case gives coins, they beat
  the price about 72% of the time (Jackpot Case is coins only, a real gamble).
- Mythic badges are a glowing "?" everywhere (cases, profiles, market, collection) until the account has
  owned one. The admin sees them.
- The vendor (quick sell) is gone: selling = the market. Price between 0.25x and 10x the usual price; buyers
  buy at the price or offer at least half; the coins only move when the seller accepts. 5% fee.
- Trading and the market need 5 hours played on both sides. Items in a trade or on sale are locked by the
  server. Any change un-readies both; 5 s countdown checked by the server; one atomic swap; a trade ends
  by itself if a player is gone for a minute or after 15 minutes.
- One account per PC: the app sends a fingerprint of the Windows install (hashed, nothing personal). A PC
  that had an account which was deleted gets a new account with 0 coins and 0 keys.
- Coins with time: 20 every 10 minutes (1 200 a day at most). Free spin every 2 hours, better prizes.
- Quests: 1 every hour, 3 every day, 3 every week. Beat Tap: 10 to 40 coins a round, 300 a day at most.
- Rocket: automatic cash-out (x1.5 to x10) or by hand from x1.20; the last flights are shown.
- Admin (account "Ruben", checked by the server on every call, everything written to an audit log): stats,
  every player (coins, keys, items, rounds, history), give / take anything, block, change cases and settings,
  live giveaways (golden tab for everyone), special sales, and Lock the app (online tabs show a blur and a
  padlock; time still counts).
- Notifications: pop-ups from the menu's top or bottom, or from the side of the ball, never taking the mouse.
  Six kinds, each can be switched off. Sound on, very quiet (20%) by default.
- "Use screen colours": a 64 x 36 picture of the screen every 2.5 s. Only one of music / screen colours at once.
- On start: old lyrics (30 days, 400 at most), old pictures and leftover temporary files are removed.


## 2.3 and 2.4

- Parking and Memory are checked move by move by the server; Memory never sends the board, only one card at a time.
- Beat Tap 2: the server sends the chart and scores the presses itself; too-perfect timing pays the minimum.
- Duels use the same level for both players; bets are held by the server and settled when both played or after 15 minutes.
- Admin undo: every admin action stores what is needed to reverse it; trades and market sales can be undone (items go back
  from wherever they are now, the victim is paid back in full).
- Password help: requests carry the PC id; the admin sees if it came from the account's own PC. The new password is shown
  only to the PC that asked, for one day, and every session of the account is logged out.
- Update lock: the app sends its build number; the admin can make older builds unable to play online.

## 3.2

- ONLINE mode is the same MainWindow with columns: every page is reused, nothing is drawn twice.
- Coinflip result is picked by the server at lock-in and hidden until the coin lands; items move once in `rb_flip_settle`, so a crash or a reload can never copy or undo anything. Closing or leaving before lock-in gives the items back.
- Leaving online mode (or quitting) calls `rb_online_leave`: open lobbies close, a joined coinflip that is not locked is left, a live giveaway entry is dropped. The user is told first in one message.
- Old apps calling `rb_golf_invite` or `rb_slots` get "update needed".

## 4.0

- Every server change is in one transaction (`021_v40.sql`), tested twice in a row on a copy of the production schema
  and once on a copy of production data before it ran for real.
- LOCKDOWN and feature locks are checked by the server in every function they cover (`rb_need_feature`), not by the
  app. Locking cancels what runs in that part with no winner and no loser (trades, coinflips, golf bets, open casino
  rounds, minigame rounds, duels) and gives everything back.
- XP is only given by the server (triggers on rounds, golf, trades and claims), with a cap per source and per day.
  Coupons and the advent calendar are outside the cap.
- Coinflip bots never change the odds: the coin is the same 49-51% share of the pot for everyone. Bot and admin flips
  are labelled BOT and RUBENIUM OFFER. A player who beats a bot gets the bot's items minted; one who loses gives theirs
  up (logged in the audit).
- Profile pictures: the client sends every name it needs (it used to send only 40), remembers "no picture" for that
  version, never asks in a loop, and keeps the last picture while a newer one loads.
- Network: one SSL context, kept-alive connections and a pool of six network threads instead of a new thread and a new
  TLS handshake for every call (the main cause of the online lag).

## 4.1

- Block Blast instead of 2048: the pieces come from the round's seed (same LCG as before) and the server places every piece
  again (`rb_blocks_replay`), so a score cannot be made up. A move that does not fit is skipped, never an error, so a bad
  client can only lose points. Over 6000 characters (2000 placements) is refused.
- Keno and Limbo: EXECUTE revoked instead of dropping the functions, so `024_down.sql` can bring them back exactly.
- Online menu: the halves are 150 px wider (ONLINE_EXTRA). Pages read their width from `page_width()` while the online
  menu builds them, and small screens ask `window.page_w()`, so the small menu is unchanged.
- Sides are fixed: Games, Shop and the live Giveaway on the left; Social and Settings on the right. On a screen too small
  for two halves the single half still offers every part.
- Leaving or entering online mode has a 4-second watchdog: whatever fails on the way, the R always comes back.
- Removed swap (Sparkles): its file's fingerprint is in RETIRED, so an installed copy is replaced by the player's own
  original automatically, like the swaps removed in 1.8.

## 4.2

- Coinflip join: nothing is reserved. rb_flip_lock checks the lobby is still open, locks your items and takes the seat
  in one transaction under the row lock, so two players can never both be in, and the one who loses the race gets
  rb_flip_taken with nothing touched.
- VS bot: the server picks the bot, its items and the result at the press, and fixes the times (found 3-7 s, joins
  3-6 s later, 3-2-1, 15 s). rb_flip_json hides the bot's name until found and its items, worth and chances until it
  joins, so neither the app nor anyone watching learns anything early. It cannot be cancelled once called.
- Mythic badges in cases are hidden for everyone (admins included): only the drop you win is shown, once the strip
  has stopped.
- The game help reads the few numbers an admin can change (free spin hours, minigame limits, fees) from the live
  settings; the rest are the fixed numbers of the server functions.
- Casino: closing or hiding the online menu, going into a game or leaving online mode keeps the casino game; only
  switching the left half away from Games goes back to the lobby.

## 5.0

- The reset (031, once, `reset_050`) wipes every bit of progress and everything in progress in one `truncate`. Kept: accounts and
  passwords, friends, messages, profile pictures, hours played (their unlocks), the OG tag, settings and their cloud backups.
  Copies of everything taken are in rb_bak50_*. On each PC the app also starts again at the first opening (tutorial, daily
  reward, welcome), settings kept (`v5_fresh`).
- OG Prismatic Chest: `rb_og_chest()` only says whether it is waiting; `rb_og_chest_claim(req)` gives 25 keys, 10 000 coins and a
  1 000 XP coupon under the row lock, once ever (og_event_at), and a resend of the same req returns the same answer. So a crash
  anywhere before Claim gives nothing and the scene plays again; after Claim nothing more can be had. The wheels are fixed (always
  those three rewards), so there is nothing to reroll. The XP coupon is 1 000 XP (1 000 000 would have been 4 times level 100).
- The scene plays behind garage doors when the online menu has finished dropping (the menu shows the shut doors while it drops).
  Without the chest, the doors open once per start of Rubenium. Leaving online mode waits until the doors are open and the chest
  is claimed, unless the claim failed (no trap).
- Mythic: the chance per open is now `myth_ppb` (billionths) on each case, since 1 in 30 000 cannot be written out of 10 000.
  Top Tier Case 17 in 300 000 (Titanium 10, Gold 4, Prismatic 3); every other case lower, the Royal Case half. "Cases above make it
  even harder" was read as: no other case is better for Mythics than the Top Tier Case. Gold and Prismatic swapped worths.
- Keys in mini games: 3% on any round that pays (`key_find_pct`), told with a notice the app turns into a big key on screen; quests
  50% (`quest_key_pct`). Not shown inside the course itself yet.
- Royal Case: 30% coins between 8 000 and 32 000 (its badge table scaled to 70%).
- In a live golf or Wave Rush match the top-left arrow is hidden and a red Leave button takes its place.

## 5.3 (21/11/2026): luck fixed, fresh start again
- Odds: one roll over the case's table, now built as item chance x rarity x finish (finish rolled apart from the design). Per open:
  Shiny about 1 in 500 (Top Tier) to 1 in 6 000 (Standard), 1 in 60 in the Shiny Case; Titanium 1 in 3 000 to 1 in 150 000; Gold
  1 in 25 000 to 1 in 600 000. Each case pays back about 70-90% of its price on average (simulated 10 000 opens each) and more than
  its price about 1 open in 7 to 1 in 10. Mythic chances unchanged.
- Every badge design has its own rarity: inside each rarity the designs are ranked by worth, the best is 10 times rarer than the most
  common (Sunburst is about 2% of Legendary drops), and worth follows (x (1/share)^0.4, the rarity's average kept).
- Cosmetics: each kind and rarity has a price ladder (e.g. banners Common 2 500-4 000 ... Legendary 50 000-80 000), designs in their
  old order, colours keep their premium; worth = 60% of the shop price. Cosmetic cases repriced to about 80% back. Shop tax 33%.
- Reset keeps: accounts, friends, messages, hours, streaks, finished game rounds (mini game leaderboards), Block Blast and Wave Rush
  runs, OG tag. Levels and XP were reset with the economy (XP came partly from coupons won in cases).
- Jackpot: the app follows the server's clock and state (PC clocks were minutes off). Bots: 1-2 seats at 35-90% of the average stake.
  The winner picks up to a third of the pot (at least 1); bot items taken are capped at 2x the winner's stake. Entries 500-250 000.
- The menu does not open before the tutorial is done; the tutorial only asks language, show/hide key, notifications and sounds.
- God mode in Wave Rush plays the practice bot's path as real inputs, so the server's replay agrees with it.

## 8.0 (overhaul): security (074, live since 25/11/2026)
- Golf: the server rolls every shot with the app's own maths (`rb_golf_sim`, a step-for-step copy of `simulate()`:
  1/240 s steps, at most 14 s). 3 000 random shots on all 120 holes give the same result in the app and on the
  server (largest gap 4e-15); about 1.5 ms a shot. The app's own start point is used when it is within 0.0006 of where
  the server last saw the ball (the server stores 4 decimals); otherwise the server's point. What the app says about
  where the ball stopped and whether it went in is no longer used. The hole layouts live in `rb_golf_hole_defs`,
  made from `HOLES` in Rubenium.py by `overhaul/db/make_074.py` (never copied by hand).
- Solo golf: a new call with the shot itself (`rb_golf_solo_shot(gid, n, x0, y0, ang, pow, x, y, holed)`); the old
  5-argument call asks for the update (`rb_update_needed`), so until 8.0 is out, solo golf online on 7.0 asks for the update (chosen at checkpoint 2; 1 v 1 and group golf keep working).
- API roles: players keep exactly the functions they could call; without a login only the six sign-in calls
  (`rb_username_free`, `rb_device_free`, `rb_login_for`, `rb_reset_ask`, `rb_reset_status`, `rb_swaps_list`).
  Tables: reading unchanged (row level security), no writes for anon or players (all writes go through rb_*
  functions; none of them runs as the caller). Default privileges follow, so new functions are not public by
  accident; a new function a player may call is granted to `authenticated` by default. The grants before 074 are
  kept in `rb_bak74_grants` for 074_down.sql.
- Password help: 3 asks a day per PC and per name; the shared limit of 300 a day only counts names that do not
  exist, so made-up names cannot use up the help for real players.
- Request ids: looked up by their first 64 characters, as they are stored.
- Swaps: id and file must be plain names (letters, digits, `_`, `-`, `.`; no `..`; .upk/.bnk/.tfc/.pck/.wem), in the
  database and in the app (an id cannot start with `_`, so it can never be the `_originals` folder).
- Admin second step: a code (6 to 72 characters, bcrypt) per admin. Once set, every admin function (all of them go
  through `rb_need_admin`) needs it typed in the last 30 minutes in the same login (the token's session id). 5 wrong
  codes lock it for 15 minutes; changing it needs the old one. `admin_step_all = 1` refuses admins without a code
  (off by default so the 7.0 admin panel keeps working until 8.0 is out). The admin panel is English only, as before.
- Skill games (075, not applied: waiting for approval of the numbers): daily profit limits back on, each above the best real day in the 14 days
  before 25/11/2026 (Cups 60 000, Connect 4 20 000, each mini game 5 000; Colour Pick and SFX Match keep 12 000,
  Timing its 20 000). Reaction limits: none added. Timing already refuses stop times that do not match the server's
  clock; the other skill games have no reaction step a limit would protect.
