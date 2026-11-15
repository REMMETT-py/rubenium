import ast, sys, re
ORDER=["win","core","online","lang_fr","widgets","media","lyrics","engines","extras","wallet","badges","pages","shop","collection","games","friends","pages2","window","app"]
HEADER = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rubenium 1.4 - gamer command centre for Windows 10 / 11.  One file.

HOW TO RUN
  1. Install Python 3.10 - 3.13 from python.org (tick "Add python.exe to PATH").
  2. Double-click this file. The first time it installs what it needs (about a minute),
     then the glowing ball appears. Click it. After that it starts with Windows.

  Needs: PyQt6, psutil and the winrt-Windows.* packages (installed automatically).
  Settings live in Documents/Rubenium/settings.json.
  Keys: Ctrl+Alt+Shift+R = normal screen colours.  Ctrl+F1 / F2 / F3 = timer start-split / pause / reset.

The app never injects into, hooks or reads the memory of a game. Its overlays are normal
click-through windows, so they do not show over EXCLUSIVE fullscreen (use borderless).
"""
from __future__ import annotations

import os
import sys

_PACKAGES = ["PyQt6>=6.6", "psutil>=5.9"]
_WIN_PACKAGES = ["winrt-runtime>=2.3", "winrt-Windows.Foundation>=2.3", "winrt-Windows.Foundation.Collections>=2.3",
                 "winrt-Windows.Media>=2.3", "winrt-Windows.Media.Control>=2.3", "winrt-Windows.Storage.Streams>=2.3"]


def _bootstrap() -> None:
    """Install missing packages once, then restart without a console window."""
    if getattr(sys, "frozen", False):
        return
    import importlib.util
    import subprocess

    def has(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            return False

    missing = [p for p, mod in zip(_PACKAGES, ("PyQt6", "psutil")) if not has(mod)]
    if sys.platform == "win32" and not (has("winrt.windows.media.control") and has("winrt.windows.storage.streams")
                                         and has("winrt.windows.foundation") and has("winrt.windows.media")):
        missing += _WIN_PACKAGES
    if missing and not os.environ.get("RUBENIUM_BOOT"):
        os.environ["RUBENIUM_BOOT"] = "1"
        print("Rubenium: installing what it needs (first start only)...")
        cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *missing]
        try:
            ok = subprocess.call(cmd) == 0
        except OSError:
            ok = False
        if not ok or not has("PyQt6"):
            text = "Rubenium could not install its packages.\\n\\nOpen a command prompt and run:\\n\\npip install " + " ".join(
                p.split(">=")[0] for p in missing)
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, text, "Rubenium", 0x10)
            except Exception:
                print(text)
            raise SystemExit(1)
    exe = sys.executable or ""
    if (sys.platform == "win32" and os.path.basename(exe).lower() == "python.exe" and "--console" not in sys.argv
            and not os.environ.get("RUBENIUM_DEBUG")):
        pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(pyw):                      # no black console window left open behind the app
            subprocess.Popen([pyw, os.path.abspath(sys.argv[0]), *sys.argv[1:]], close_fds=True)
            raise SystemExit(0)


if __name__ == "__main__":
    _bootstrap()

win = engines = extras = sys.modules[__name__]        # the sections below call each other as win.x / engines.x
'''
defs={}
out=[HEADER]
for m in ORDER:
    src=open(f"rubenium/{m}.py").read()
    tree=ast.parse(src)
    lines=src.split("\n")
    kill=set(); passes={}
    body=tree.body
    if body and isinstance(body[0],ast.Expr) and isinstance(getattr(body[0],'value',None),ast.Constant) and isinstance(body[0].value.value,str):
        kill.update(range(body[0].lineno-1, body[0].end_lineno))
    for node in ast.walk(tree):
        if isinstance(node,ast.ImportFrom) and (node.level>0 or node.module=="__future__"):
            rng=range(node.lineno-1,node.end_lineno)
            if node.col_offset>0: passes[node.lineno-1]=" "*node.col_offset+"pass"
            kill.update(rng)
    for node in body:
        names=[]
        if isinstance(node,(ast.FunctionDef,ast.ClassDef,ast.AsyncFunctionDef)): names=[node.name]
        elif isinstance(node,ast.Assign):
            for t in node.targets:
                for n in ast.walk(t):
                    if isinstance(n,ast.Name): names.append(n.id)
        elif isinstance(node,ast.AnnAssign) and isinstance(node.target,ast.Name): names=[node.target.id]
        elif isinstance(node,(ast.Import,ast.ImportFrom)) and not (isinstance(node,ast.ImportFrom) and node.level>0):
            for a in node.names:
                nm=(a.asname or a.name).split(".")[0]
                origin=("import", getattr(node,'module',None), a.name)
                prev=defs.get(nm)
                if prev and prev[0]!=origin: print("IMPORT CLASH", nm, prev, m, origin)
                defs.setdefault(nm,(origin,m))
            continue
        for nm in names:
            if nm=="log": continue
            if nm in defs: print("CLASH", nm, defs[nm][1], m)
            defs[nm]=(("def",m,nm),m)
    new=[]
    for i,l in enumerate(lines):
        if i in passes: new.append(passes[i])
        elif i in kill: continue
        elif l.startswith("# -*- coding") or l.startswith("#!"): continue
        else: new.append(l)
    text="\n".join(new).strip("\n")
    bar="# "+"="*98
    out.append(f"\n\n{bar}\n# SECTION: {m}\n{bar}\n{text}\n")
out.append('\n\nif __name__ == "__main__":\n    sys.exit(main())\n')
open("/home/claude/release/Rubenium.py","w").write("".join(out))
