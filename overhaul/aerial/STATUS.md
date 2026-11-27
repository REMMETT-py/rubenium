# Rubenium League: status

Rubenium League (working code name "aerial") is a 1 v 1 side-view car soccer game inside Rubenium: online menu, Play,
the Rubenium League banner. It is switched on for everyone (the `--aerial` flag is no longer needed).

All the code is in `Rubenium.py`, in the blocks that start with `# SECTION: aerial`. Nothing else in the app
changes, apart from a few small hooks: the banner in Play, the page, the menu widening while a match is on (as it does
for Karting), and one self-test step.

## What works

- **Physics** (no Qt, 120 steps a second, deterministic): driving, braking and turning round, boost (refills on the
  ground, much faster while touching the ball), jump with hold, double jump, flips in both directions with flip cancel,
  air roll, mouse air control (or keys), flip resets on the ball, landing on walls and the ceiling, turtle recovery,
  ball spin and bounces, Rocket League's extra hit impulse (stronger in a flip), car to car bumps.
  Own sine, cosine and arc tangent, so two PCs give the same result.
- **Pitch**: Sideswipe proportions (cars 110-160 long, ball 212 wide, pitch 3000 wide and 1150 high), rounded
  corners, goals raised off the floor with a smooth ramp in, rounded goal corners and crossbars. Rolling balls go in.
- **Match**: 3-2-1-GO with mirrored kickoffs (3 kickoff spots), 2:30 clock that only runs while the ball is live, the
  0:00 floor rule, golden-goal overtime, anti-stall kickoff after 8 s of a dead ball, goals counted once when the whole
  ball is in, goal explosion, goal replays (6 s, slow motion at the end, jump to skip).
- **Points as in Rocket League** (no shot points): goal 100, save 50, epic save 75, clear 20, first touch 10, aerial
  hit 10, aerial goal +25, long goal +20, overtime goal +50, double tap +30, flip reset goal +50, hat trick, savior.
- **10 bots, one per rank** (Milo, Tito, Rocco, Flash, Viper, Storm, Vortex, Phantom, Oracle, Ruben). Each knows
  everything the ones below know plus its own moves, and gets more hidden help (see BRIEF.md). Top bots re-think
  every step, read a possession play coming and wait for it in goal, fake challenges, play off your boost, mix one
  move into another, clear a ball caught in front of their own goal, fly home in the air, and never stay stuck.
- **Ranked against bots**: 10 ranks, 5 net wins up, 5 net losses down. Kept on this PC until ranked goes online (no
  coins depend on it). Admins can close it for everyone (lock `league_ranked`: Admin > Locks or the lobby button;
  needs `supabase/migrations/096_league_lock.sql` on the server).
- **Lobby**: rank card, the 3 cars with their hitboxes, Play ranked, Free Play and drills, all 10 bots to practise.
- **Controls**: mouse (default): W/Z drive toward the crosshair, S brake/reverse, Space jump, Shift boost, crosshair on
  a ring round the car, W/S pitch and pick the flip in the air, left/right click air roll left/right. Keys only: A/D
  (Q/D) drive and turn, Q/E (A/E on AZERTY) air roll. Tab scoreboard; the mouse is locked to the game until Esc/Tab.
- **Tracker**: totals, MMR chart, the last 200 matches, the last 10 replays (watch in the app, or save the
  `.rlreplay` file; a replay is the seed plus every input, a few kB).
- **Ladder page**: the climb from Rookie 1 to Rubenite with each rank's bot and an animated progress bar.
- English and French, help page, self-test (`--selftest --aerial`), tests in `overhaul/aerial/test_aerial.py`.

## Measured

- Physics step: about 0.03 ms (one car), bot thinking about 0.1-0.4 ms a step. A whole 2-minute bot match simulates
  in about 3-8 s on one core.
- Jump about 260 high, double jump about 500. Ladder maths: winning every match against equal opponents takes about
  70 matches to Challenger and about 420 to Rubenite.
- Self-test: `SELFTEST aerial: ... replay MATCH`, `SELFTEST OK (0 problems)`.

## Open

- **Bot calibration (27 Nov, 60 s matches).** Each bot against the one below, 16 matches a pair: Tito-Milo 50 %,
  Rocco-Tito 63-88 %, Flash-Rocco 63 %, Viper-Flash 81 %, Storm-Viper 69 %, Vortex-Storm 63 %, Phantom-Vortex 69 %,
  Oracle-Phantom 63 %, Ruben-Oracle 94 %. Against one fixed human-like opponent (8 matches each, goals for-against):
  Milo 42-41, Tito 41-38, Rocco 45-37, Flash 48-25, Viper 57-27, Storm 68-22, Vortex 84-17, Phantom 81-11,
  Oracle 103-11, Ruben 108-7. Milo and Tito are still too close to each other.
- Goals between two equal top bots came down from about 13 to about 8 a minute (own goals from possession plays near
  their own goal, defenders floating back in the air, hits bent toward goal); many of the rest are kickoff goals.
- Ranked and private matches against players need the online phase (server functions and netcode).
- Key rebinding and engine sound are not built yet. Private match is a button that says it comes with the online update.
- The `database` CI job fails on `tests/db/test_111_v94.sql` on main too (4 old migrations do not apply in the test
  database, so `rb_ach` is missing). Nothing in this branch touches the database apart from the new lock row.
- What only a real Windows PC can show: feel at 144/240 Hz, mouse aim on a real desktop, sound levels.
