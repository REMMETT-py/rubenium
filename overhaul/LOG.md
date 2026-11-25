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

## Session 1, later (25/11/2026)

- With daksh's explicit OK (one-off exception to "no live writes"): ran `073_v70_longer_race.sql` on live and set
  `latest_tag` / `min_build` to 2026112301 so 6.9.1 players update to 7.0. Verified both on live.
- Phase 1 started: `overhaul/db/run_tests.py` (a fresh database copy per test, `.sql` tests with `assert`, `.py`
  tests for calls at the same time), fixtures in `tests/db/_fixtures.sql`.
- The live snapshot used as the test server (`RB_BASELINE`) is kept privately (the repository is public); without
  it the runner falls back to replaying the repo migrations (048, 051, 052, 054 fail there, see the audit).
- Server tests so far (`tests/db/`): fixtures, rows stay private, admin-only functions refuse players, double claims
  (the same request sent twice at once pays once), and old apps keep working (every call the 7.0 app makes, and
  every player-callable function's arguments and return type). Tests that reproduce live problems are kept
  privately until the fixes are live.
- One suspected race from the audit (a coupon given twice) was tested with six calls at once and is not real: the
  function locks the profile row first. Withdrawn.
- CI: `.github/workflows/overhaul.yml` runs on `overhaul-8` only: compile + ruff (real errors only), the self-test
  on Linux (headless) and Windows (from source), and the server tests on a Postgres 16 service. It never builds,
  publishes, or touches releases or tags.
