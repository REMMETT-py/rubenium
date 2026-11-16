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
