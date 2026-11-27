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
- **Pitch**: Sideswipe proportions (car 118 long, ball 184 wide, pitch 3400 wide and 1200 high), rounded top corners,
  goals a little above the floor with a smooth ramp in, rounded goal corners and crossbars. Rolling balls go in.
- **Match**: 3-2-1-GO with mirrored kickoffs (3 kickoff spots), 2:00 clock that only runs while the ball is live, the
  0:00 floor rule, golden-goal overtime, anti-stall kickoff after 8 s of a dead ball, goals counted once when the whole
  ball is in, goal explosion, goal replays (6 s, slow motion at the end, jump to skip).
- **Points as in Rocket League** (no shot points): goal 100, save 50, epic save 75, clear 20, first touch 10, aerial
  hit 10, aerial goal +25, long goal +20, overtime goal +50, double tap +30, flip reset goal +50, hat trick, savior.
- **22 bots**, Pip to Apex plus Ruben, each with its own limits and character (see BRIEF.md).
- **Ranked against bots** with the exact ladder rules (45 steps, MMR formula with the loss multiplier, rank-up series
  against the gatekeepers, 3-match shield). Kept on this PC until ranked goes online (no coins depend on it).
- **Lobby**: rank card, the 3 cars with their hitboxes, Play ranked, Free Play and drills, all 22 bots to practise.
- **Tracker**: totals, MMR chart, the last 200 matches, the last 10 replays (watch in the app, or save the
  `.rlreplay` file; a replay is the seed plus every input, a few kB).
- **Ladder page** with all five emblems, floors and gatekeepers.
- English and French, help page, self-test (`--selftest --aerial`), tests in `overhaul/aerial/test_aerial.py`.

## Measured

- Physics step: about 0.03 ms (one car), bot thinking about 0.1-0.4 ms a step. A whole 2-minute bot match simulates
  in about 3-8 s on one core.
- Jump about 260 high, double jump about 500. Ladder maths: winning every match against equal opponents takes about
  70 matches to Challenger and about 420 to Rubenite.
- Self-test: `SELFTEST aerial: ... replay MATCH`, `SELFTEST OK (0 problems)`.

## Open

- **Bot calibration is not finished.** Neighbouring bots now mostly beat the one below (8-match samples), Apex beats
  Pip about 10 times in 12 and Ruben beat Apex 7 of 8, but the order is not yet strict everywhere and Ruben is not yet
  at 98 of 100. Lessons so far: a boosted kickoff on this short pitch rebounds into your own goal, so most bots now
  arrive under control and the top ones contest a hard kickoff when they see one coming; bots wait in front of their
  goal while the ball is up the other end; they check where the ball goes after each planned touch.
- Ranked and private matches against players need the online phase (server functions and netcode).
- Key rebinding and engine sound are not built yet. Private match is a button that says it comes with the online update.
- The `database` CI job fails on `tests/db/test_111_v94.sql` on main too (4 old migrations do not apply in the test
  database, so `rb_ach` is missing). Nothing in this branch touches the database.
- What only a real Windows PC can show: feel at 144/240 Hz, mouse aim on a real desktop, sound levels.
