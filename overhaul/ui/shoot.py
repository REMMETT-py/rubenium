"""Quick pictures of chosen screens (for working on the look), using the same set-up as crawl.py.

  python overhaul/ui/shoot.py Rubenium.py --out DIR [--online] STEP...
A STEP is `name=python code` run with `rb` (the app context) and `w` (the window in front); a picture is taken after
each one. `name=` alone just takes a picture. Example: "games=w.goto('games')".
"""
import argparse, os, runpy, sys, time, traceback
ap = argparse.ArgumentParser()
ap.add_argument("script"); ap.add_argument("--out", required=True); ap.add_argument("--online", action="store_true")
ap.add_argument("--wait", type=int, default=1300); ap.add_argument("--lang", default="en")
ap.add_argument("steps", nargs="*")
A = ap.parse_args()
os.makedirs(A.out, exist_ok=True)
from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
ERR = []
sys.excepthook = lambda t, v, tb: ERR.append("".join(traceback.format_exception(t, v, tb))[-2500:])
_real = QApplication.exec


def driver(rb):
    yield 2000
    for _ in range(20):
        if rb.welcome is None:
            break
        if os.environ.get("SHOOT_WELCOME"):
            rb.window.grab().save(os.path.join(A.out, "welcome.png"))
            os.environ.pop("SHOOT_WELCOME")
        rb.welcome.launch(force=True)
        yield 1000
    if A.lang != (rb.cfg["lang"] or "en"):
        rb.set_language(A.lang)
        yield 800
    rb.window.expand()
    yield 900
    if A.online:
        rb.enter_online()
        yield 4500
    for i, st in enumerate(A.steps):
        name, _, code = st.partition("=")
        if code:
            try:
                exec(code, {"rb": rb, "w": rb.window, "M": sys.modules["__rb__"]})
            except Exception:  # noqa: BLE001
                ERR.append(name + ": " + traceback.format_exc()[-2500:])
            yield A.wait
        try:
            rb.window.grab().save(os.path.join(A.out, f"{i:02d}_{name}.png"))
        except Exception as e:  # noqa: BLE001
            ERR.append(f"{name}: shot {e}")


def fake_exec(app):
    rb = app._rubenium
    it = driver(rb)

    def step():
        try:
            QTimer.singleShot(int(next(it)), step)
        except StopIteration:
            print("SHOOT done, errors:", len(ERR)); [print(e) for e in ERR]
            app.exit(1 if ERR else 0)
    QTimer.singleShot(1500, step)
    return _real()


QApplication.exec = fake_exec
sys.argv = [A.script]
g = runpy.run_path(A.script, run_name="__rb_main__")
mod = type(sys)("__rb__"); mod.__dict__.update(g); sys.modules["__rb__"] = mod
sys.exit(g["main"]())
