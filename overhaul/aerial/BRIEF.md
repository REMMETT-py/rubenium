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
Blade, Titan) differ only in hitbox. Boost refills on the ground and faster on the ball.

Controls (mouse, the default): W/Z drive toward the crosshair, S brake then reverse, Space jump, Shift boost; the
crosshair rides on a ring round the car (put it behind the car to turn round, the car points at it in the air);
W/S in the air pitch forward/back and pick a front/back flip; left click air roll left, right click air roll right.
Keys only: A/D (Q/D on AZERTY) drive and turn in the air, Q/E (A/E on AZERTY) air roll left/right.

## Ranks
10 ranks: Rookie (Débutant) 1-3, Challenger 1-3, Master 1-3, Rubenite. One bot per rank, and ranked is always against
the bot of your rank. 5 more wins than losses against it and you go up; 5 more losses than wins and you go down.
Rating shown as MMR 0-1000 (100 a rank, 10 a net win). Admins can close ranked (lock `league_ranked`, Admin > Locks or
the admin button in the lobby).

## Bots (rank, level; each knows everything the ones below know, plus its own)
Milo (Rookie 1) basics · Tito (Rookie 2) + double jumps, flips · Rocco (Rookie 3) + aerials, wall clears · Flash
(Challenger 1) + fast aerials, wave dashes · Viper (Challenger 2) + carries and flicks · Storm (Challenger 3) + air
dribbles, ground pinches, fake challenges · Vortex (Master 1) + ceiling pinches, musty flicks · Phantom (Master 2) +
flip resets, reads your boost · Oracle (Master 3) + reset chains · Ruben (Rubenite) everything, catches every touch.
(Internal keys stay pip ... apex, ruben, so saved history keeps working.)

Each bot is the same `AerialBot`; its level sets reaction time, how often it re-plans, how far and how well it reads
the ball, aim and timing error, blunders, which mechanics it tries and how often they come off. The kit adds the
possession plays, how often it goes for them and mixes one into another, how cleanly they come off, how often it waits
in goal for a play coming at it, fakes (brakes in front of you), reading the other car's boost, thinking every 1-4
steps at the top, and the hidden help (less boost used, ball sticking to the car, reach on fast balls and more on shots
at its own goal, flicks and pinches that reach the goal in a time set by rank).

## Calibrating
`overhaul/aerial/arena.py` plays headless bot matches on all cores (`ladder N`, `pairs N a:b,...`). Goal set by the
owner: each bot all but unbeatable for the one below, and Ruben harder still. Change levels and kits, never physics.
