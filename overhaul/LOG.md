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
- CI first run: lint and the Linux self-test passed; the Windows job looked for the log too early (from source,
  Rubenium restarts itself under pythonw; `--console` keeps it in place) and the database job tried to start its
  own server (it now uses the CI service when PGHOST is set). Both fixed.
- A local stand-in for the server (`overhaul/stub/server.py`): the app's calls go to the local test database with
  the same roles and rules, so the logged-in pages can be opened without touching the real server.
- A page crawler (`overhaul/ui/crawl.py`, `run_crawl.sh`): opens every page and every section inside it (three
  levels down), every casino game and every part of the games lobby, pictures each one and records any error.
  First full run: offline 27, player 120, admin 139 states, English and French, 0 errors; 58 server functions used,
  none refused.
- "Before" pictures of every page: offline, player, admin, French, and two small screens (1366x768, 1280x720):
  550 states, 0 errors (kept with the project files, not in the repository).
- Phase 2 server work is written and tested on the local copy of the live server, kept privately until it is live
  (this repository is public). `overhaul/db/roundtrip.py` checks any migration: it applies twice, undoes twice, and
  every function, grant, table's row security and setting is back exactly as before.

## Phase 2: security (25/11/2026)
- 074 applied to the live server in four parts (golf tables and physics; hole layouts; shot functions, request ids and
  password help; admin code, grants, backup tables and swap names). Checked afterwards against the tested copy: all 467
  functions and their grants identical, 107 tables with the same row security and grants, the saved old grants
  identical, and six sample shots rolled to the same spot. 075 (skill game daily limits) waits for approval.
- Before applying: every function on live was still identical to the snapshot the work was tested on, and no golf
  game was in progress.
- The server tests, the golf tools (`overhaul/golf`: hole layouts read from Rubenium.py, the SQL physics, and a check
  that compares 3 000 shots between the app and the database) and the client changes are now public.
- Server tests: 16 of 16 with the live snapshot, 15 of 15 (one skipped) from the repository's migrations alone.

## Phase 3: broken and unfinished things (25/11/2026)
- French: every literal passed to tr() and every What's new line now has French (`overhaul/i18n/check.py`, run in CI).
  44 keys were defined twice with different French; one value each is kept (the one players saw, except: "The ball"
  is "La boule" like "Ball", "Get ready…" uses "tu" like the rest of the app).
- One error message was defined twice ("rb_not_your_turn"); the one players saw is kept.
- `__init__` methods no longer return values (18 places), 7 stray `pass` lines and 8 unused variables removed (one
  random draw kept so a procedural picture stays the same).
- SETUP.md covers 6.1 to 8.0; DECISIONS.md has the right place of session.dat.

## Phase 5 (started) and Phase 4 quick wins (25/11/2026)
- Design system (`DS`, `paint_surface`, `field_css` in Rubenium.py): one set of corners (7 / 10 / 12), hairline
  edges and lit surfaces for every shared control. Buttons are lit from above with a crisp edge (main buttons get a
  soft shadow; an unavailable main button is a quiet dashed outline instead of a grey block), segmented switches are
  a recessed track with a raised pill, panels and section tiles share one surface, text fields one style (accent
  edge while typing), slider knobs a shadow and a hover halo.
- Settings: section titles are spaced capitals with room above them, each setting row has a hairline under it, and
  the always-highlighted UPDATE tile is now a quiet accent mark, so it no longer looks like the selected tile.
- Game picker: 14 games in two even rows of 7 (Colour Pick and SFX Match were a half row on the right).
- Wording: "100 h played · member since 25 Nov 2026" (was "100.0 h Played · Member Since 2026-11-25"),
  "1 user", coinflip waits over an hour as 3:43:17 (was 223:17).
- Designed empty states: the Jackpot between rounds and an empty inventory (with a button to the cases).
- Performance: the resting welcome screen redraws 20 times a second instead of 60 (its lights drift slowly; every
  animation keeps its own full rate). Outside online mode the jackpot / race bell asks the server every 30 s per
  kind instead of every 10 s (events stay open 2 minutes, so the bell still rings in time).
- Crawler: `ONLY=` and `MAX=` for quick runs of one set of pages.
- Designed empty states for the market, chat and trades (a glyph, a title and what to do next).
- Every row of switch buttons is even (7 leaderboards: 4 + 3, not 3 + 3 + 1).
- Reduce motion (Settings > Style): interface movements take 30% of their time. Clocks and countdowns (linear
  animations) are untouched, so no game timing changes.
- The pulsing ONLINE / giveaway tabs and the admin alert tile stop their timers while the menu is closed.
