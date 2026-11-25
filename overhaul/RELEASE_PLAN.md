# Rubenium 8.0: release plan

Everything for 8.0 is on `overhaul-8`. Nothing has been released, and BUILD, VERSION and VERSION_NAME are still the
7.0 values, so merging alone does not publish anything: release.yml skips a BUILD that already has a release
(2026.11.23.1 is 7.0).

## Already live
- `074_v80_security.sql` on the live server since 25/11/2026 (verified: functions, grants and settings match the tested
  copy; no call from the 7.0 or 8.0 app is refused, except 7.0 solo golf shots, which ask for the update).

## Waiting for the owner
- `075` (skill game daily profit limits: Cups 60 000, Connect 4 20 000, each mini game 5 000): needs an OK on the
  numbers. Kept private until then. Not needed for 8.0 to ship.

## Steps
1. Review the draft PR `overhaul-8` → `main` (checks: lint, Linux and Windows self-tests, server tests).
2. In Rubenium.py set `VERSION_NAME = "8.0"`, a new `VERSION` and the next `BUILD` (a date that only goes up), and
   check `release_notes.txt`. This is the owner's step: it is what makes release.yml build and publish.
3. Merge into `main`. release.yml builds RubeniumSetup.exe and the portable exe and publishes the release.
4. Install 8.0 yourself, open Admin > Settings > Admin code and set your code (6+ characters). When every admin has one,
   set `admin_step_all` = 1 in rb_config.
5. Set `latest_tag` / `min_build` in rb_config to the new build so everyone gets 8.0.
6. Watch for a day: Admin > Alerts, Supabase logs for `rb_update_needed` (should fall as players update), and the
   crash reports.

## Undo
- App: players can stay on 7.0 until min_build is raised; to go back, publish a 7.0 rebuild with a higher BUILD.
- Server: `074_down.sql` puts every function, grant and setting back exactly (tested twice).

## Evidence
- Server tests: 16 of 16 on a copy of the live server (15 + 1 skipped in CI, which has no live snapshot).
- UI crawl: 552 page states (offline, player, admin, French, small screens), 0 errors.
- Self-test: SELFTEST OK on Linux and Windows (CI).
- Resting CPU about 25 % → 10 % of one core (Linux, headless), same memory.
