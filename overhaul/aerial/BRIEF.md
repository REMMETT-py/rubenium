# Rubenium League: brief

The one place for the game's rules and decisions. Read STATUS.md for where the work stands.

## Rules that do not change
- The game lives in `Rubenium.py` as `# SECTION: aerial` blocks (prefix `aerial_` / `Aerial` / `AERIAL_`). No new
  modules and no new packages (the script updater only downloads Rubenium.py).
- The simulation has no Qt, runs at 120 steps a second and is deterministic: same seed and inputs, same state hash.
  It never reads the clock or the global random, and uses its own trig.
- Players and bots drive through the same `AerialInput`. Bots never get extra speed, boost, power or hidden
  information, and never read the other player's inputs.
- Hidden until released: only shows when the app starts with `--aerial`.
- Never change VERSION, VERSION_NAME or BUILD; never merge to main; never run SQL on the live server.

## The game
1 v 1, side view, keyboard and mouse. 2:00 clock that runs only while the ball is live, 3-2-1-GO, 0:00 waits for a
floor touch, golden-goal overtime, goal replays. Points as in Rocket League, no shot points. Three cars (Comet,
Blade, Titan) differ only in hitbox. Boost refills on the ground and faster on the ball.

## Ranks
Rookie, Challenger, Elite, Champion, Rubenite; tiers 1-3; divisions I-III (45 steps). Floors / MMR per division:
0/60, 540/80, 1260/100, 2160/120, 3240/150. E = 1/(1+10^((opp-me)/400)); win +16(1-E); loss -16·E·M with M
1.00/1.05/1.10/1.18/1.25. Rank-up series: Ember bo3, Halo bo3, Vex bo5, Apex bo5. 3-match shield after a promotion.

## Bots (name, MMR, character)
Rookie: Pip 40, Dusty 130, Wobble 220, Bolt 310, Nudge 400, Sprocket 480. Challenger: Ember 590, Rattle 730,
Skid 870, Vapor 1010, Jinx 1150. Elite: Halo 1320, Torque 1500, Mirage 1680, Cinder 1860, Quartz 2040.
Champion: Vex 2240, Zenith 2460, Nova 2680, Tempest 2900, Apex 3120. Rubenite: Ruben 4600 (the only one).

Each bot is the same `AerialBot`; its level (`lv`) sets reaction time, how often it re-plans, how far and how well it
reads the ball, aim and timing error, how often it blunders, which mechanics it tries and how often they come off,
how much it presses, and how many touches it thinks through before committing. Traits lean its style.

## Calibrating
`aerial_bot_match(a, b, seed, match_s)` plays one headless match. Goal: each bot beats the one below about 60-75 %
of the time over at least 100 matches, Ruben beats Apex at least 98 of 100. Change `lv` and traits, never physics.
