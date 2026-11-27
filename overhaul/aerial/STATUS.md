# Rubenium League: status

Rubenium League (working code name "aerial") is a 1 v 1 side-view car soccer game inside Rubenium. It is hidden
until it is released: start the app with `python Rubenium.py --aerial`, open the online menu, then Play.

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
- **10 bots, one per rank** (Pip to Apex, then Ruben). Each learns more moves (flicks, air dribbles, ground and
  ceiling pinches, musty flicks, flip reset chains) and gets more hidden help (see BRIEF.md). Top bots read a
  possession play coming and wait for it in goal.
- **Ranked against bots**: 10 ranks, 5 net wins up, 5 net losses down. Kept on this PC until ranked goes online (no
  coins depend on it). Admins can close it for everyone (lock `league_ranked`: Admin > Locks or the lobby button;
  needs `supabase/migrations/096_league_lock.sql` on the server).
- **Lobby**: rank card, the 3 cars with their hitboxes, Play ranked, Free Play and drills, all 10 bots to practise.
- **Controls**: Space jump, Shift boost, mouse moves a crosshair on a ring round the car (the car points at it in the
  air), either mouse button or E air roll, Tab scoreboard. The mouse is locked to the game until Esc or Tab.
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

- **Bot calibration.** Against one fixed, human-like opponent every rank does better than the one below (12-match runs,
  goals for - against: Pip 49-61, Sprocket 72-35, Ember 84-37; 6-match runs: Halo 42-14, Vex 41-12, Nova 56-8,
  Apex 46-14, Ruben 66-7). Bot against the next bot up is still too close (about 50-80 %): with goals every few
  seconds on this pitch a bot match is chaotic. Measured: 8 % more top speed, more reach or turning hits toward goal
  do not change a bot-vs-bot result by themselves; level and the possession plays do.
- Ranked and private matches against players need the online phase (server functions and netcode).
- Key rebinding and engine sound are not built yet. Private match is a button that says it comes with the online update.
- The `database` CI job fails on `tests/db/test_111_v94.sql` on main too (4 old migrations do not apply in the test
  database, so `rb_ach` is missing). Nothing in this branch touches the database apart from the new lock row.
- What only a real Windows PC can show: feel at 144/240 Hz, mouse aim on a real desktop, sound levels.
