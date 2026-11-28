# Rubenium League: brief

The one place for the game's rules and decisions. Read STATUS.md for where the work stands.

## Rules that do not change
- The game lives in `Rubenium.py` as `# SECTION: aerial` blocks (prefix `aerial_` / `Aerial` / `AERIAL_`). No new
  modules and no new packages (the script updater only downloads Rubenium.py).
- The simulation has no Qt, runs at 120 steps a second and is deterministic: same seed and inputs, same state hash.
  It never reads the clock or the global random, and uses its own trig.
- Players and bots drive through the same `AerialInput`, and bots never read the other player's inputs.
- The name is "Rubenium League", in English and French.
- Never change VERSION, VERSION_NAME or BUILD; never merge to main; never run SQL on the live server.

## The game (10.0: flat and top-down)
1 v 1 car soccer on a flat pitch seen from above. No jumps, no air: everything happens on the ground (dribbles, drift
flicks, wall pinches, fakes, saves). 2:30 clock that runs only while the ball is live, 3-2-1-GO, mirrored kickoffs
(3 spots, the same for both sides turned half round the centre) with a 1 s settle after the first touch that caps the
ball speed, so a kickoff cannot go straight in. Golden-goal overtime, goal explosion, goal replays. Points as in
Rocket League (no shot points), plus Pinch Goal and Flick Goal bonuses.

Boost only from the pitch: 6 big orbs along the sides (full tank, back after 10 s) and 32 small pads (12, back after
4 s). A used pad shows a ring that fills until it is back.

Cars: Comet balanced, Blade sleek and agile (turns and drifts best, lightest), Titan compact and sturdy (heaviest,
hits hardest, wins 50/50s). Same top speed and boost for all. The bot always drives a different car from yours.

Controls: W/Z or Up drive, S or Down brake then reverse, A/Q or Left and D or Right steer (WASD and ZQSD both work at
the same time), Shift or left click boost, Ctrl or right click powerslide (no right-click menu while playing), Space
or Enter skips a goal replay. Free Play: infinite boost (B), R reset, T ball in front, G slow motion, H hitbox.

Modes: Ranked 1 v 1 (against the bot of your rank), Private match (any bot up to one rank above yours, its car, 2:30
or 5:00, no MMR), practice, Free Play. Private matches against friends need the online update.

## Ranks
10 ranks: Rookie (Débutant) 1-3, Challenger 1-3, Master 1-3, Rubenite. One bot per rank, and ranked is always against
the bot of your rank. 5 more wins than losses against it and you go up; 5 more losses than wins and you go down.
Rating shown as MMR 0-1000. Admins can close ranked (lock `league_ranked`) or hide the whole game from players (lock
`league`), in Admin > Locks or with the admin buttons in the lobby.

## Bots
Milo, Tito, Rocco, Flash, Viper, Storm, Vortex, Phantom, Oracle, Ruben (internal keys pip ... apex, ruben, so saved
history keeps working). Each is the same `AerialBot`; its level sets reaction, re-planning, how far and how well it
reads the ball, aim and line error, randomness in choices and blunders. It weighs its options each time it thinks
(save, carry, shoot at a post or the middle, bank off a wall, pinch, clear, shadow, fake, pads, boost denial) and
holds a plan for a moment instead of flickering. Its defence (`guard` in the kit, 0 for Milo up to 1 for Ruben) sets
how deep and disciplined it shadows, when it keeps the goal line side on, and how well it saves. The kit (`AERIAL_BOT_KIT`) adds plays by rank and a touch-precision
help that grows with rank (where its touch goes, and the power of a touch it means as a shot). As the owner decided:
fair boost and speed up to Master 1; Phantom 1.15x boost and 1.03x speed, Oracle 1.3x and 1.06x, Ruben 1.5x and 1.10x.
All of it lives in the sim through the inputs, so replays play back the same.

## Calibrating
`overhaul/aerial/arena.py` plays headless bot matches on all cores (`ladder N`, `pairs N a:b,...`). Goal set by the
owner: each bot clearly stronger than the one below, Milo already like a Challenger 2, Ruben practically unbeatable.
