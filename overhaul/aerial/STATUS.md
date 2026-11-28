# Rubenium League: status

Rubenium League (working code name "aerial") is a 1 v 1 top-down car soccer game inside Rubenium: online menu, Play,
the Rubenium League banner. 10.0 rebuilt it as a flat 2D game (see BRIEF.md). Admins can hide it from players with the
`league` lock (needs `supabase/migrations/098_league_hide.sql` on the server). It ships hidden for players in
10.0, as the owner decided, until the top bots are tuned.

All the code is in `Rubenium.py`, in the blocks that start with `# SECTION: aerial`.

## What works
- Flat pitch with rounded corners, goals with nets, team tints in blue and orange, 6 big boost orbs and 32 small pads
  with respawn rings.
- Karting physics: throttle, brake and reverse, speed-dependent steering, strong grip, powerslide that keeps momentum
  (never adds speed), boost thrust with a higher top speed while it burns.
- Car to ball contacts with the extra hit, drift flicks, wall pinches; car to car bumps; the kickoff settle.
- Match rules, points, saves, shots, clears, overtime, anti-stall kickoff, goal explosion, goal replays.
- Ranked, Private match, practice, Free Play; tracker with MMR, history, shots, pinches and flicks; saved replays
  (format v2; side-view v1 replays are refused with a message).
- English and French, help page, self-test (`--selftest --aerial`), tests in `overhaul/aerial/test_aerial.py`.

## Measured (28 Nov, full 2:30 bot matches, 40 a pair, each bot against the one below)
Tito-Milo 27, Rocco-Tito 28, Flash-Rocco 34, Viper-Flash 31, Storm-Viper 28, Vortex-Storm 25, Phantom-Vortex 30,
Oracle-Phantom 24, Ruben-Oracle 23 wins of 40. Ruben against lower bots (20 each): Phantom 16, Vortex 18, Storm 15,
Milo 20 (265-35 in goals).

What made the top bots apart: their defence (kit `guard`). Defenders used to shadow close to the ball and lose long
shots from far up the pitch; now they shadow deeper on the ball's line, keep the goal line side on when the other car
can shoot (78 of 80 long shots stopped in a drill, was 61), aim their saves out wide, and stop challenging balls they
reach second. A bot with it beats the same bot without it about 60 % of the time.

## Open
- The top steps (Vortex over Storm, Oracle over Phantom, Ruben over Oracle) are clear but smaller (58-63 %) than the
  lower ones. More would need more than the boost and speed help the owner allowed.
- Ranked and private matches against players need the online phase (server functions and netcode).
