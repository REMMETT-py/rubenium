"""Opens every page Rubenium has, and every section inside it, takes a picture of each, and records every error.

Runs the real Rubenium.py headless (QT_QPA_PLATFORM=offscreen) without changing it. Logged in when the home folder
holds a session (see overhaul/ui/run_crawl.sh, which starts the local stand-in server and makes the session), so
the online menu is opened too: Games, Shop, Social, Settings, Admin (for an admin), and inside each one every tile
row and switch (Shop > Inventory > Levels and so on), up to three levels down.

Usage: python overhaul/ui/crawl.py Rubenium.py --out DIR [--lang en|fr] [--online] [--max 400]
Writes DIR/NNN_<where>.png, DIR/crawl.json (every state visited, the errors, the log lines with ERROR), and exits
1 if anything raised.
"""
import argparse
import json
import os
import re
import runpy
import sys
import time
import traceback

ap = argparse.ArgumentParser()
ap.add_argument("script")
ap.add_argument("--out", required=True)
ap.add_argument("--lang", default="en")
ap.add_argument("--online", action="store_true")
ap.add_argument("--max", type=int, default=400)
ap.add_argument("--depth", type=int, default=3)
A = ap.parse_args()
os.makedirs(A.out, exist_ok=True)

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

ERRORS: list = []
SHOTS: list = []
_real_exec = QApplication.exec


def hook(t, v, tb) -> None:
    ERRORS.append({"where": SHOTS[-1]["name"] if SHOTS else "start",
                   "error": "".join(traceback.format_exception(t, v, tb))[-3000:]})


sys.excepthook = hook


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "x"


def driver(app, rb):
    """A generator: yields how long to wait (ms) before the next step."""
    seen_controls: set = set()

    def win():
        return app.window

    def shot(name: str) -> None:
        if len(SHOTS) >= A.max:
            return
        w = win()
        path = os.path.join(A.out, f"{len(SHOTS):03d}_{slug(name)}.png")
        try:
            w.grab().save(path)
        except Exception as exc:  # noqa: BLE001
            ERRORS.append({"where": name, "error": f"screenshot failed: {exc}"})
        SHOTS.append({"name": name, "file": os.path.basename(path), "size": [w.width(), w.height()]})

    def page_of(key):
        entry = getattr(win(), "pages", {}).get(key)
        return entry[1] if entry else None

    def controls(key):
        """The section switches on a page: (signature, widget, labels, faint)."""
        page = page_of(key)
        if page is None:
            return []
        out = []
        for w in page.findChildren(QWidget):
            cls = type(w).__name__
            if not w.isVisibleTo(page):              # shown on the page (the page itself may be fading in)
                continue
            if cls == "NavTiles" and getattr(w, "select", True):
                labels = [str(x[0]) for x in w.items]
            elif cls == "Segmented" and key not in ("settings",):
                labels = [str(x) for x in w._labels]
            else:
                continue
            out.append((key + ":" + cls + ":" + "|".join(labels), w, labels, set(getattr(w, "faint", ()) or ())))
        return out

    def find(key, sig):
        return next((w for s, w, _l, _f in controls(key) if s == sig), None)

    def press(w, i) -> None:
        if type(w).__name__ == "Segmented":
            w.set_index(i)
        else:
            w.index = i
        w.changed.emit(i)

    seen_popups: set = set()

    def games():
        """Every game screen: the casino games one by one, then each part of the lobby."""
        G = sys.modules["__rb__"].GamesPage
        for i, name in enumerate(G.NAMES):
            rb.enter_casino(i)
            yield 1500
            yield from clear(f"game {name}")
            shot(f"game {name}")
        rb.leave_casino()
        yield 900
        flags = {"quests": "quests_open", "beat tap": "mini_open", "parking": "park_open"}
        subs = ["minigames", "memory", "blocks", "sweeper", "duels", "wave", "flip", "jackpot", "horses", "advent",
                "scratch"]
        for name in list(flags) + subs:
            for f in flags.values():
                setattr(rb, f, False)
            rb.games_sub = None
            if name in flags:
                setattr(rb, flags[name], True)
            else:
                rb.games_sub = name
            rb.reload_page("games")
            yield 1500
            yield from clear(f"games {name}")
            shot(f"games {name}")
        for f in flags.values():
            setattr(rb, f, False)
        rb.games_sub = None
        try:
            win().allow_keys(False)
        except Exception:  # noqa: BLE001
            pass
        rb.reload_page("games")
        yield 900

    def clear(trail):
        """Something opened over the page by itself (an intro, a reward): picture it once, then close it."""
        for _ in range(5):
            sh = getattr(win(), "sheet", None)
            if sh is None:
                return
            name = type(sh).__name__
            if name not in seen_popups:
                seen_popups.add(name)
                shot(f"{trail} [{name}]")
            win().unembed(sh)                       # as the sheet's own close does
            sh.deleteLater()
            yield 900

    def explore(key, trail, depth):
        yield from clear(trail)
        if depth > A.depth:
            return
        for sig, _w, labels, faint in controls(key):
            mark = trail.split(" ")[0] + "/" + sig     # the main menu and the online menu are explored apart
            if mark in seen_controls:
                continue
            seen_controls.add(mark)
            for i, label in enumerate(labels):
                if i in faint or len(SHOTS) >= A.max:
                    continue
                w = find(key, sig)
                if w is None:                       # the page was rebuilt without this switch (another branch)
                    break
                press(w, i)
                yield 900
                yield from clear(f"{trail} > {label}")
                shot(f"{trail} > {label}")
                yield from explore(key, f"{trail} > {label}", depth + 1)

    if rb.welcome is not None:
        yield 2500
        shot("welcome")
    for _ in range(20):                             # press Launch until the welcome card has gone (as --selftest)
        if rb.welcome is None:
            break
        rb.welcome.launch(force=True)
        yield 1000
    if A.lang != (rb.cfg["lang"] or "en"):
        rb.set_language(A.lang)
        yield 800
    w = win()
    w.expand()
    yield 900
    from_tabs = [k for k, _i, _n in sys.modules["__rb__"].TABS if k != "online"]
    for key in from_tabs:
        w.goto(key)
        yield 900
        yield from clear(f"menu {key}")
        shot(f"menu {key}")
        yield from explore(key, f"menu {key}", 1)
    if A.online:
        if not rb.online.logged_in():
            ERRORS.append({"where": "online", "error": "not logged in: the online menu cannot open"})
        else:
            rb.enter_online()
            yield 4500
            ow = win()
            keys = list(sys.modules["__rb__"].SECTIONS) + sorted(sys.modules["__rb__"].LIVE_TABS)
            for key in keys:
                ow.set_pane(sys.modules["__rb__"].side_of(key), key)
                yield 1500
                yield from clear(f"online {key}")
                shot(f"online {key}")
                yield from explore(key, f"online {key}", 1)
                if key == "games":
                    yield from games()
            rb.leave_online(ask=False)
            yield 3000


def start(app) -> None:
    rb = app._rubenium
    steps = driver(rb, rb)
    t0 = time.time()

    def finish(code: int) -> None:
        log = os.path.join(rb_data_dir(), "rubenium.log")
        bad = []
        try:
            bad = [ln.rstrip() for ln in open(log, encoding="utf-8", errors="replace") if " ERROR " in ln or " CRITICAL " in ln]
        except OSError:
            pass
        json.dump({"states": SHOTS, "errors": ERRORS, "log_errors": bad[-200:], "seconds": round(time.time() - t0)},
                  open(os.path.join(A.out, "crawl.json"), "w"), indent=1)
        print(f"CRAWL {len(SHOTS)} states, {len(ERRORS)} errors, {len(bad)} error lines in the log", flush=True)
        app.exit(code)

    def step() -> None:
        try:
            wait = next(steps)
        except StopIteration:
            return finish(1 if ERRORS else 0)
        except Exception:  # noqa: BLE001
            hook(*sys.exc_info())
            return finish(1)
        QTimer.singleShot(int(wait), step)
    QTimer.singleShot(1500, step)
    QTimer.singleShot(15 * 60 * 1000, lambda: (ERRORS.append({"where": "crawl", "error": "timed out"}), finish(2)))


def rb_data_dir() -> str:
    return str(sys.modules["__rb__"].DATA_DIR)


def fake_exec(self):
    start(self)
    return _real_exec()


QApplication.exec = fake_exec
sys.argv = [A.script]
g = runpy.run_path(A.script, run_name="__rb_main__")
mod = type(sys)("__rb__")
mod.__dict__.update(g)
sys.modules["__rb__"] = mod
sys.exit(g["main"]())
