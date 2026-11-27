# Rubenium League: brief

The one place for the game's rules and decisions. Read STATUS.md for where the work stands.

## Rules that do not change
- The game lives in `Rubenium.py` as `# SECTION: aerial` blocks (prefix `aerial_` / `Aerial` / `AERIAL_`). No new
  modules and no new packages (the script updater only downloads Rubenium.py).
- The simulation has no Qt, runs at 120 steps a second and is deterministic: same seed and inputs, same state hash.
  It never reads the clock or the global random, and uses its own trig.
- Players and bots drive through the same `AerialInput`, and bots never read the other player's inputs. As the owner
  decided, bots get hidden help that grows with rank (`AERIAL_BOT_KIT`, applied in the sim so replays match): less boost
  used for the same push, the ball sticking to the car, a touch more reach on fast balls, and full-speed flicks and
  pinches off a held ball. Never extra top speed.
- Hidden until released: only shows when the app starts with `--aerial`.
- Never change VERSION, VERSION_NAME or BUILD; never merge to main; never run SQL on the live server.

## The game
1 v 1, side view, keyboard and mouse. 2:30 clock that runs only while the ball is live, 3-2-1-GO, 0:00 waits for a
floor touch, golden-goal overtime, goal replays. Points as in Rocket League, no shot points. Three cars (Comet,
Blade, Titan) differ only in hitbox. Boost refills on the ground and faster on the ball. Space jump, Shift boost,
mouse aims the car in the air (crosshair on a ring round the car), either mouse button or E air roll.

## Ranks
10 ranks: Rookie (Débutant) 1-3, Challenger 1-3, Master 1-3, Rubenite. One bot per rank, and ranked is always against
the bot of your rank. 5 more wins than losses against it and you go up; 5 more losses than wins and you go down.
Rating shown as MMR 0-1000 (100 a rank, 10 a net win). Admins can close ranked (lock `league_ranked`, Admin > Locks or
the admin button in the lobby).

## Bots (rank, level, what it adds)
Pip (Rookie 1, 0.20) basics · Dusty (Rookie 2, 0.34) jumps and flips · Sprocket (Rookie 3, 0.47) first aerials ·
Ember (Challenger 1, 0.58) fast aerials, wave dashes · Jinx (Challenger 2, 0.68) flicks · Halo (Challenger 3, 0.77) air
dribbles, ground pinches · Vex (Master 1, 0.86) ceiling pinches, musty flicks · Nova (Master 2, 0.94) flip resets ·
Apex (Master 3, 1.03) reset chains · Ruben (Rubenite, 1.35) everything, catches every touch, always reads the play.

Each bot is the same `AerialBot`; its level sets reaction time, how often it re-plans, how far and how well it reads
the ball, aim and timing error, blunders, which mechanics it tries and how often they come off. The kit adds the
possession plays (flick, ground pinch, air dribble, ceiling pinch, musty, flip resets), how often it goes for them,
how cleanly they come off, how often it waits in goal for a play coming at it, and the hidden help.

## Calibrating
`overhaul/aerial/arena.py` plays headless bot matches on all cores (`ladder N`, `pairs N a:b,...`). Goal set by the
owner: each bot all but unbeatable for the one below, and Ruben harder still. Change levels and kits, never physics.
