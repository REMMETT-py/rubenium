# Economy

## 9.2.1: prize limits by wealth tier

Every daily limit is worked out by the server from the player's wealth tier (rb_config, Admin > Economy). `cap_x_<tier>`
multiplies the base daily limit on top of the tier's reward multiplier; 0 means no daily limit.

| | Poor | Average | Investor | Businessman | Casino Legend |
|---|---|---|---|---|---|
| Reward multiplier (`tier_x_`) | x1 | x1.3 | x1.8 | x2.6 | x4 |
| Limit multiplier (`cap_x_`) | x2 | x3 | x4 | x6 | no limit |
| Mini game coins a day, each game (3 000 base, before the level bonus) | 6 000 | 11 700 | 21 600 | 46 800 | no limit |
| Karting prizes a day (2 500 base) | 5 000 | 9 750 | 18 000 | 39 000 | no limit |
| AFK coins a day (2 400 base + streak) | 4 800 | 9 360 | 17 280 | 37 440 | no limit |
| Keys kept from time (`key_cap_`) | 10 | 15 | 20 | 30 | 50 |
| Key Forge a day (`forge_day_`) | 5 | 8 | 12 | 20 | 40 |
| Keys found in games a day (`key_find_day_`) | 16 | 20 | 25 | 35 | 60 |
| Biggest bet in a duel or room (`duel_max_bet_`, and never above 80% of your coins) | 10 000 | 20 000 | 40 000 | 75 000 | 150 000 |

Skill games (Timing, Cups, Colour Pick, SFX Match, Connect 4 and the bot games) had no daily limit before and still have
none. Bots keep the base limits. Reaching a new tier shows a rank-up screen once (profiles.tier_seen).

## 9.0 (current)

Everything lives in the server (rb_config) and can be changed from Admin > Economy.

| What | Value |
|---|---|
| Fresh start | everyone starts again at 1 000 coins and 3 keys (rb_reset_economy_90, run once). Cosmetics, items, levels, friends stay |
| Wealth tiers | from wealth (coins plus the value of items, rb_wealth): Rookie 0 (x1), Bronze 5 000 (x1.25), Silver 25 000 (x1.6), Gold 100 000 (x2.2), Platinum 500 000 (x3), Diamond 2 000 000 (x4) |
| Scaled rewards | free spin, scratch card, daily reward, quests, mini games, AFK coins and the Golden Wheel are multiplied by the tier, rounded to 10 (5 under 100) |
| Free spin | every hour: 100, 150, 250, 400, 600, 1 000, 2 000 (x tier), a key, the Golden Wheel or an XP coupon |
| Scratch card | every 4 h: 150-300, 400-700, a key + 200, 2 keys, 3 000 (x tier) or the Golden Wheel |
| Daily reward | 7 days: 150, 250, a key, 400, 2 keys, 750, 1 500 + a key (x tier) |
| Time | 30 coins every 10 min (2 400 a day), 1 key every 20 min up to 10 |
| Key Forge | a key for 1% of your coins (at least 500), 5 a day |
| Shop tax | 15% on top of shop prices |
| Player market | gone (closed on the server: rb_feature_gone) |
| Cheat detection | off: nothing is flagged or locked automatically. Admins can still lock a game by hand |

## 2.2 (history)

Everything below lives in the server (table rb_config and rb_cases) and can be changed live from the admin panel.

| What | Value |
|---|---|
| Start | 500 coins, 3 keys (0 and 0 on a PC whose account was deleted) |
| Time | 20 coins every 10 min (max 1 200 a day), 1 key every hour (max 48) |
| Free spin | every 2 h: 40, 75, 120, 180, 300, 500, 1 200 coins or a key |
| Daily case | every 24 h |
| Quests | hourly 40-45, daily 120-150, weekly 800-900 coins |
| Beat Tap | 10-40 coins a round, half after 10 rounds, 300 a day max |
| Casino bets | 10 to 1 000, max win 50 000, house edge about 3-4% |
| Market | price 0.25x to 10x the usual price, offers from 50%, 5% fee, 20 items on sale max |
| Gifts | 3 cases a day, friends only |

Badge values (usual price): Common 150, Rare 450, Epic 1 200, Legendary 3 000 (Basic). Painted x1.6, Shiny x8,
Titanium x40, Gold x200. Mythic: Titanium 15 000, Prismatic 45 000, Gold 240 000 (the Rubenium R is worth
2x, 2x and 3x more).

## Cases (odds out of 10 000; finish odds out of 100 000)

| Case | Price | Coins | Common | Rare | Epic | Legendary | Mythic | Coins range |
|---|---|---|---|---|---|---|---|---|
| Starter | 150 | 3 800 | 5 000 | 1 030 | 150 | 20 | 0 | 100-300 |
| Standard | 300 | 3 600 | 4 200 | 1 700 | 420 | 78 | 2 | 180-620 |
| All or Nothing | 250 | 5 600 | 0 | 3 000 | 1 150 | 245 | 5 | 10-60 |
| Painter's | 600 | 3 400 | 4 400 | 1 750 | 380 | 70 | 0 | 360-1 250 |
| Premium | 800 | 3 500 | 2 300 | 2 900 | 1 050 | 242 | 8 | 480-1 650 |
| Jackpot | 1 000 | coins only: 100-400 (70%), 1 000-1 800 (24%), 3 000-5 000 (5%), 8 000-16 000 (1%) |
| Titanium | 1 500 | 3 500 | 3 000 | 2 400 | 850 | 244 | 6 | 900-3 100 |
| Legend Vault | 2 000 | 3 400 | 0 | 3 500 | 2 300 | 775 | 25 | 1 200-4 100 |
| Mythic Hunt | 5 000 | 3 800 | 0 | 0 | 4 300 | 1 800 | 100 | 3 000-9 800 |

Finishes for a badge (most cases): Basic about 74%, Painted 25%, Shiny 0.55%, Titanium 0.03-0.09% (Epic and
Legendary only; the Titanium Case 0.36%), Gold 0.02-0.04%. A Mythic is Titanium 90%, Prismatic 9.5%, Gold 0.5%.
The Gold Rubenium R: about 1 in 220 000 Mythic Hunt openings.


## 2.4 changes

| What | Value |
|---|---|
| Mini games (Beat Tap, Parking, Memory) | 150 coins per game every 2 hours; full pay for 6 rounds, then half, then a quarter |
| Beat Tap | 12-50 coins (score worked out by the server) |
| Parking | Easy 12-25, Medium 18-38, Hard 30-50 |
| Memory | Easy 12-30, Medium 18-40, Hard 25-55 (fewer flips pay more) |
| Scratch card | every 12 h: Common 60-120 coins (55%), Rare 150-300 (27%), Epic 1 key (12%), Legendary 2 keys (5%), Mythic 2 500 coins (1%) |
| Daily login | 60, 90, 120, 1 key, 200, 300, 400 + Standard case; a missed day starts again |
| Duels | bet 0 to 5 000 each, winner takes both minus 5% |
| Badge shop | Basic/Painted cost value x4 (Common), x5 (Rare), x6 (Epic), x8 (Legendary); Shiny x1.5 more; Titanium, Gold, Mythic never sold |
| Sets (once each) | Common row 3 000 + 2 keys, Rare 8 000 + 4, Epic 20 000 + 6, Legendary 50 000 + 10, Mythic 250 000 + 25, 8 Painted of one badge 4 000 + 2, 5 Shiny 15 000 + 5, 3 Titanium 40 000 + 8, a Gold 25 000 + 10 |

## 2.5 changes

- Gifted cases (from a friend or the admin) open completely free: no coins and no key.
- Deals: every day 4 items (price 30 000 or less, never Titanium, Gold or Mythic) are 20-35% cheaper, the same for everyone.
- Beat Tap modes: Normal, Rush (faster, more notes), Long notes, Chords. Same pay and limits.
- Admin resets (inventory, coins and keys, gifted cases, full account): everything is saved in the Log and can be undone.
- Visualisers removed (none are sold).

## 2.6

- Fresh start: every account back to 500 coins and 3 keys; items, spins, cases, sets and collection history reset (backup tables rb_bak26_*). Time played, friends, streak kept.
- OG tag: free for accounts made before 17 Nov 2026 (Paris), never sold or traded, kept by admin resets. Cut-off is `og_until` in rb_config.
- Banners (16): Common 400, Rare 1 200, Epic 3 500, Legendary 9 000. Frames (12): 300, 1 000, 3 000, 8 000. In the shop, market, trades and daily deals.
- Quick sell: 25% of the value (`quick_share`), and for shop items never more than half of what was paid (`quick_shop_share`). Checked: no case and no sale (even -90%) can be farmed with it.

## 2.6.1: case balance

Income: about 120 coins and 1 key per hour with Rubenium (plus mini games, daily login, scratch card). Keys cannot be
bought, so the key is the real limit on cases; a gift now costs its price and 1 key too.

| Case | Price | Pays back (items at quick sell) | Lose | Legendary+ |
|---|---|---|---|---|
| Starter (coins) | 200 | 110% | 50% | 0.05% |
| Standard (coins) | 500 | 109% | 50% | 0.15% |
| Premium (coins) | 1 200 | 106% | 51% | 0.4% |
| Jackpot (coins) | 2 000 | 104% | 72% | - |
| Titanium (coins) | 3 500 | 103% | 53% | 0.8% |
| All or Nothing (hunt) | 600 | 54% | 95% | 2.5% |
| Painter's (hunt) | 1 200 | 59% | 76% | 0.7% |
| Legend Vault (hunt) | 4 000 | 55% | 77% | 8% |
| Mythic Hunt (hunt) | 10 000 | 50% | 78% | 19% (Mythic 1%) |

- Coin cases: +20 to +110 coins per key on average, about 1 hour of income at most. 6% of coin drops are a lucky x3.
- Rare odds per open were never raised; rare hunts cost about twice as much as before, so rare badges cost more coins.
- Shop badge price = 1.5 x the coins lost on average in the best case to get one of that rarity and finish, at least 8 x
  its value: Common 1 200 / 1 900 / 80 000 (Basic / Painted / Shiny), Rare 3 600 / 5 750 / 210 000, Epic 9 600 / 15 500 /
  585 000, Legendary 24 500 / 58 000 / 2 750 000. The market can go up to the shop price.

## 2.7

- AFK: 25 coins every 10 minutes (150 an hour), up to 1 800 a day; 1 key an hour (up to 48).
- Casino return (checked by maths): Slots 96.9%, Plinko 95.9-96.9%, Dice 97%, Bombs 97%, Rocket 96%, Blackjack about 98-99%. Unchanged.
- New looks: banners Snow (Rare 1 200), Ember (Epic 3 500), Nebula (Legendary 9 000); frames Frost (Rare 1 000), Star (Epic 3 000), Halo (Legendary 8 000).

## 3.0

- Style cases (items counted at quick sell / at shop price): Style 500 (balls, lines, fonts) 70% / 106%; Theme 800 70% / 114%;
  Profile 1 500 (banners, frames) 70% / 103%. Legendary about 1 in 100. Event items (Snow, Aurora, Frost) never drop and are not sold.
- The case strip uses the real odds (no fake rare flashes) and never repeats an item close together.
- Bots: their AFK coins and keys follow the same rates as users; they open coin cases and place small bets now and then.

## 3.0.0
- Duels: any bet from 10 coins up to 80% of the lower balance of the two players, in steps of 10 (checked by the server). No bet is still possible.
- Balls re-ranked: Common = Pixel, Halo, Bullseye; Rare = Split, Shard, Hex; Epic = Bubble, Orbit; Legendary = Spiral, Ripple. Prices per rarity are unchanged (120 / 360 / 960 / 2 400 grey; colours ×1.25; black and white one rarity up).
- Banners re-ranked by look, 10 new ones. Common 400: Dusk, Mint, Steel, Rose, Stripes, Dots, Carbon, Dunes. Rare 1 200: Waves, Peaks, Ember, Circuit, Sunset, Honeycomb, Comet, Deep Sea. Epic 3 500: Grid, Jungle, Sakura, Lava, Prism, City Nights, Neon, Fireflies. Legendary 9 000: Galaxy, Nebula, Matrix, Storm, Vortex. Snow and Aurora stay unsold for Christmas.
- Gold banners: hours worn (counted with your time) for Gold I / II / III: Common 10/30/75, Rare 15/45/110, Epic 25/75/180, Legendary 40/120/300. Purely visual.
- Offline mode earns nothing: the server only counts minutes it hears about.

## 3.0.0 (final)
- Keys: 1 every 15 minutes, earning stops at 5. Trading and the market need no hours any more.
- Mini games: every payout x1.3; up to 200 coins every 2 hours per game.
- Rarer top drops: Mythic tier is 0.6% in the Mythic Hunt (was 1%), 0.15% in the Legend Vault, 0.03% in All or Nothing and Titanium, 0.01% in Premium and Standard. Shiny x0.8, Titanium and Gold x0.6 in every badge case. Mythic finishes: Titanium 96.5%, Prismatic 3.3%, Gold 0.185%. Rarest item (Rubenium Gold): about 1 in 1 000 000; every other item is more common.
- OG event (until 17/11/2026 00:00 Paris): OG tag owners get 10 000 coins, 10 gold keys (one use each, used before normal keys, never above the key cap) and 1 gifted open of every case.
- Mini Golf 1v1: bet 0 or 10 up to 80% of the lower balance; the winner gets both bets minus 5%; a draw refunds. 3 holes, 6 strokes max per hole, 25 s per turn (missed turn = +1 stroke, 3 in a row = loss). Invitations expire after 5 minutes.

## 3.1
- AFK: 25 coins every 10 minutes + 5 per login-streak day (counted up to 20 days, so up to +100). The daily AFK cap grows the same way (+72 x bonus).
- Quests: 2 hourly (25-30 coins), 4 daily (100-150), 6 weekly (1 200-2 000).
- Daily login: 100, 150, 1 key, 250, 2 keys, 500, then 1 000 coins + 1 key + a Premium case.
- Golden Wheel: 5% of free spins and 5% of scratch cards. Prizes: 2 500 (30%), 5 000 (25%), 10 000 (15%), 25 000 (5%), or a free Premium (12%), Titanium (8%), Legend Vault (4%) or Mythic Hunt (1%) case with a key.
- Timing: bet 10-1 000; perfect x4 (within 0.8% of the target), good x1.8 (2.5%), close x0.9 (5%), else nothing. Net winnings from Timing stop at 20 000 a day.
- New cases (return at quick sell): Pocket 100 (109%), Elite 6 000 (109%), Royal 25 000 (107%), Shiny Hunt 8 000 (80%), Banner Case 2 000 (68%, more at shop prices).
- Quick sell for badges: 3% of worth (at least 25% of base value).
- Titanium badges are sold in the shop at their worth (50 x value). Gold and Mythic are never sold.
- Sets: 5 Shiny 60 000 + 10 keys, 3 Titanium 250 000 + 20, a Gold 500 000 + 25, every Legendary 150 000 + 20, the 6 Mythics 5 000 000 + 100.

## 3.2
- Keys: 1 every 30 minutes, earning stops at 12. Every existing player was filled to 12 once. Keys can be traded.
- Cases: bought with coins (up to 10 at a time) into "Your cases", opened with 1 key (style cases need none). A gifted case costs the buyer coins only; the receiver opens it with a key.
- Worth: every item has one, from its base value x design rank (0.85-1.25) x colour rank (0.95-1.05), rounded. Shop price = worth x 1.2 (the shop tax, `shop_tax`), minus any sale. Limited items are never sold in the shop.
- Drop chances: every item of a case has its own weight (1 / worth factor), shown in the case's list.
- Coinflip: up to 6 items a side; the joiner must be within 10% of the creator's worth and has 30 s; flip 15 s after lock-in; chance = share of the pot, clamped 49-51%; no fee. One open coinflip at a time; it closes after 5 minutes with nobody in. Decided at lock-in, items moved once.
- Mini Golf: open lobbies (one per player, 5 minutes), 5 holes from 24.
- Roulette: 25 pockets, 12 red and 12 black pay x2, 1 gold pays x24 (96% return). Hi-Lo: each step pays (1 / chance) x 0.985.
- Chat: 300 characters, 1.5 s between messages, 5 per 10 s, the same text not again within 60 s.
- Advent calendar: Dec 1-24 one door a day (coins, keys, limited looks and cases), big door on the 25th: 10 000 coins, 6 keys, North Star banner and frame, 3 Winter Cases.

## 4.0 prices (021_v40.sql)

Badge prices come from bands (table `rb_price_bands`), never from one multiplier. Inside a band, a badge's place depends
on its design (more detailed = dearer) and its colour, so the same badge is always worth more Painted than Basic, and
more Shiny than Painted. `rb_price_all()` recomputes everything; admins can change a band and run it again.

| Badge | Common | Rare | Epic | Legendary |
|---|---|---|---|---|
| Basic (grey) | 650-1 000 | 2 000-3 000 | 5 400-8 000 | 14 000-20 500 |
| Painted | 1 400-2 200 | 4 200-6 500 | 11 300-17 500 | 42 000-66 000 |
| Shiny ("Brilliant") | 25 000-35 000 | 45 000-65 000 | 90 000-130 000 | 170 000-240 000 |
| Titanium | – | – | 750 000-950 000 | 1 000 000-1 250 000 |
| Gold | 2 000 000-2 600 000 | 2 500 000-3 200 000 | 3 200 000-4 000 000 | 4 000 000-5 000 000 |

Mythic: Titanium 10-14 M, Prismatic 14-19 M, Gold 20-25 M. Looks (balls, lines, fonts, banners, frames, themes): their
3.2 price, grey looks a third cheaper, coloured balls and lines 10% cheaper. Quick sell pays 35% of an item's worth.
The market "usual price" only counts sales made after the 4.0 prices (`price_epoch`).

Every open listing was given back to its seller when 021 ran (a notice tells them); no item, coin or key moved
otherwise. Backups: `rb_bak021_catalog`, `rb_bak021_listings`, `rb_bak021_config`; `021_down.sql` restores prices and
settings.

## 4.0 levels and XP

XP to reach a level: 50 + 12 L + 0.6 L² per level. Level 1 = 50 XP, 5 = 386, 10 = 1 207, 20 = 4 754, 50 = 41 435,
100 = 261 370 (months of regular play with the daily cap of 2 500 XP from playing).

| Source | XP | Daily cap |
|---|---|---|
| Casino bet (10 coins or more) | 3 + bet / 40, at most 25 | 600 |
| Minigame that pays | 10 + pay / 6, at most 45 | 900 |
| Mini Golf match | 40, +30 for the winner | 600 |
| Coinflip | 25 each | 300 |
| Trade done | 15 each | 150 |
| Online | 10 every 10 minutes | 300 |
| Case opened | 8 | 200 |
| Free spin, scratch card | 15 | 60 |
| Quest / set claimed | 60 / 150 | 600 |
| Advent door | 100 (500 on the 25th) | not capped |
| XP coupons | Common 150, Uncommon 400, Rare 1 000, Epic 2 500; OG: up to level 5 | not capped |

Minigame pay is multiplied by 1 + 0.004 × level (level 100: +40%), inside the same window caps. Cases unlock at
levels 2 (Cosmic Hunt), 3 (Shiny Hunt), 4 (Epic Vault) and 5 (Mythic Hunt); nothing is locked after level 5.

## 4.1 (024_v41.sql)

- Block Blast replaces 2048 as a minigame. Pay = score ÷ 5 up to 300 coins (Classic 8x8), score ÷ 8 up to 200 (Relaxed 10x10),
  score ÷ 3 up to 360 (Hard 7x7), then the usual minigame window (game_window_cap every 2 hours, level multiplier).
  A bot that plays like a casual player scores a median of about 550 / 530 / 410, so a typical game pays 70 to 140 coins.
- Score: 1 point per square placed; clearing L lines at once adds 10 x L x L; clearing again on the next piece adds 20 per
  step of the streak.
- Keno and Limbo are removed (their functions can no longer be called). The house edge table above no longer lists them.

## 4.2 (025_v42.sql)

- Coinflip bots: Pixel 50 to 3 000, Milo 500 to 15 000, Nova 5 000 to 150 000, Vega 25 000 to 1 000 000,
  Atlas 250 000 to 100 000 000 (worth of the lobby). VS bot uses the bot whose range holds your lobby's worth; the
  bot's items are real catalog items (never limited) within ±10%; the same 49-51% chance and server roll as players.
  Bots no longer join player lobbies on their own.
- Timing: acceleration 0.08-0.14 (was 0.35-0.50). The stop time from the app is used only if it is between 40 ms ahead
  and 400 ms behind the server's clock and the round's clock ran at least 94% of real speed; otherwise the server's
  time minus 80 ms. Payouts unchanged (×4 / ×1.8 / ×0.9).
- Advent door 1: frame:firstfrost, Legendary (epic), limited, worth 20 000, never sold or in a case.
