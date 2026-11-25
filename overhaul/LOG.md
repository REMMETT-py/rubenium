# Overhaul 8.0 log

## Session 1 (25/11/2026): Phase 0, audit

Done:
- Read DECISIONS, ECONOMY, SETUP, README, the three workflows, the `c4` edge function.
- Built a local database from every migration (`overhaul/db/replay.sh`, Supabase stand-in in `overhaul/db/shim.sql`).
  Result: 67 files apply, 4 fail (048, 051, 052, 054) because objects made directly on the live server were never
  committed (Connect 4 table, Cups). Migrations 038 and 042 do not exist in the repo.
- Compared the repo with the live database (read-only): 33 functions and 9 tables exist only live, 54 functions differ.
- Reviewed every function a player can call, the client's network, updater, swap and file code, lint, translations,
  timers; ran the self-test headless on Linux (passes, 31 steps, about 35 s).
- Baseline (headless Linux, `overhaul/perf/`): 1.2 s to the event loop; idle with the ball closed 2.0 % of a core with
  the glow, 0.23 % without; logged-out welcome card 24.6 %; 306 MB.
- The full audit is in the project's private files, not here: this repository is public and the audit contains
  exploits that work on the live server until Phase 2 ships.

Next: Checkpoint 1 (waiting for answers), then Phase 1.

Open questions: see the Checkpoint 1 message.
