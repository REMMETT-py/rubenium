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

## Measured (27 Nov, 60 s bot matches, 40 a pair, each bot against the one below)
Tito-Milo 27, Rocco-Tito 23, Flash-Rocco 31, Viper-Flash 27, Storm-Viper 25, Vortex-Storm 15, Phantom-Vortex 27,
Oracle-Phantom 17, Ruben-Oracle 20 wins of 40.

## Open
- The top four bots (Vortex to Ruben) are not yet clearly apart: both sides score almost at will, so results there are
  close to a coin flip. Reactions, aim, shot power, the allowed boost and speed help and the play lists each move it by
  only a few wins in 40. Their defence needs reworking.
- Ranked and private matches against players need the online phase (server functions and netcode).
