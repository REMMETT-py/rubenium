# Rubenium

A glowing ball for Windows 10 / 11 that opens into a gamer command centre: music for any app, lyrics,
crosshair, screen colours, stats, timer, app launcher, themes and Rocket League item swaps.

**Download:** [RubeniumSetup.exe (latest)](https://github.com/REMMETT-py/rubenium/releases/latest/download/RubeniumSetup.exe)

It installs for your Windows account only (no admin rights), adds Rubenium to the Start menu, and can be removed from Settings → Apps.

Rubenium checks this repository for new versions and offers to install them (Settings → Updates).

## Publishing an update

1. Change `VERSION = "..."` and `VERSION_NAME = "..."` near the top of the CORE section in `Rubenium.py` (for example `1.0.0` / `1.0` → `1.0.1` / `1.0.1`). `VERSION` must always go up: it is what the updater compares.
2. Write what changed in `release_notes.txt`.
3. Commit / upload both files to `main`.

GitHub then builds the app and `RubeniumSetup.exe` on Windows, tests installing, updating and uninstalling it, and publishes the release by itself (Actions tab, about 10 minutes).
Every running Rubenium sees it within 6 hours, or straight away from Settings → Updates.
Downloads are checked against their SHA-256 file before anything is replaced.

## Adding a Rocket League swap

1. Make a folder `swaps/<id>/` and put the replacement file in it, named exactly like the game file
   (for example `swaps/fennec_flames_blacklunation/skin_grain_flames_SF.upk`).
2. Optional: add a square picture of the result as `swaps/<id>/preview.png`. It shows on the swap's tile.
3. Add one line for it to `RL_ITEMS` in `Rubenium.py` (only needed for a swap that is not listed yet).

Several swaps can be on at once. Two swaps that replace the same game file cannot.

## Files

| File | What it is |
| --- | --- |
| `Rubenium.py` | The whole app |
| `swaps/` | Rocket League replacement files, packed into the .exe |
| `Rubenium.spec`, `installer.iss`, `build.bat`, `make_icon.py`, `make_version_info.py` | Building the app and its setup |
| `.github/workflows/release.yml` | Automatic build and release |

Modding Rocket League's files goes against its rules. The swaps are local and visual only: use at your own risk.
