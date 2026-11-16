# Economy (2.2)

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
