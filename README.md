# Rubenium

A glowing ball for Windows 10 / 11 that opens into a gamer command centre: music for any app, lyrics,
crosshair, screen colours, stats, timer, app launcher, themes and Rocket League item swaps.

**Download:** [Rubenium.exe (latest)](https://github.com/REMMETT-py/rubenium/releases/latest/download/Rubenium.exe)

Rubenium checks this repository for new versions and offers to install them (Settings → Updates).

## Publishing an update

1. Change `VERSION = "..."` near the top of the CORE section in `Rubenium.py` (for example `3.0.0` → `3.1.0`).
2. Write what changed in `release_notes.txt`.
3. Commit / upload both files to `main`.

GitHub then builds `Rubenium.exe` on Windows and publishes the release by itself (Actions tab, about 5 minutes).
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
| `Rubenium.spec`, `build.bat`, `make_icon.py`, `make_version_info.py` | Building the .exe |
| `.github/workflows/release.yml` | Automatic build and release |

Modding Rocket League's files goes against its rules. The swaps are local and visual only: use at your own risk.
