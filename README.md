# Rubenium

A glowing ball for Windows 10 / 11 that opens into a gamer command centre: music for any app, lyrics,
crosshair, screen colours, stats, timer, app launcher, themes and Rocket League item swaps.

**Download:** [Rubenium.exe (latest)](https://github.com/REMMETT-py/rubenium/releases/latest/download/Rubenium.exe)

Rubenium checks this repository for new versions and offers to install them (Settings → Updates).

## Publishing an update

1. Change `VERSION = "..."` near the top of the CORE section in `Rubenium.py` (for example `2.2.0` → `2.3.0`).
2. Write what changed in `release_notes.txt`.
3. Commit / upload both files to `main`.

GitHub then builds `Rubenium.exe` on Windows and publishes the release by itself (Actions tab, about 5 minutes).
Every running Rubenium sees it within 6 hours, or straight away from Settings → Updates.
Downloads are checked against their SHA-256 file before anything is replaced.

## Files

| File | What it is |
| --- | --- |
| `Rubenium.py` | The whole app |
| `swaps/` | Rocket League replacement files, packed into the .exe |
| `Rubenium.spec`, `build.bat`, `make_icon.py`, `make_version_info.py` | Building the .exe |
| `.github/workflows/release.yml` | Automatic build and release |
| `docs/index.html` | The download page |

Modding Rocket League's files goes against its rules. The swaps are local and visual only: use at your own risk.
