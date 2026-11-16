import os, sys, time, json, re, shutil
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["RUBENIUM_DEMO"]="1"
shutil.rmtree("/tmp/rbhome8", ignore_errors=True)
os.environ["HOME"]="/tmp/rbhome8"; os.makedirs("/tmp/rbhome8/Documents",exist_ok=True)
sys.path.insert(0,"/home/claude")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon, QPixmap, QColor
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtTest import QTest
import Rubenium as A
src=open('/home/claude/Rubenium.py').read(); keys=set()
for m in re.finditer(r'\btr\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+)', src): keys.add(eval("("+m.group(1)+")"))
print("missing FR:", sorted(k for k in keys if k not in A.FR))
A.setup_logging()
q=QApplication([]); q.setStyleSheet(A.APP_QSS)
a=A.App(q); w=a.window
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.005)
out="/tmp/s8"; os.makedirs(out,exist_ok=True)
pm=QPixmap(48,48); pm.fill(QColor("#c33")); 
a._apps=[{"name":n,"path":"x","exe":e,"icon":QIcon(pm)} for n,e in [("Steam","steam.exe"),("Rocket League","rocketleague.exe"),("Discord","discord.exe"),("Spotify","spotify.exe"),("OBS Studio","obs64.exe"),("Epic Games Launcher","epicgameslauncher.exe")]]
pump(600); w.expand(); pump(900)
for k,_,_ in A.TABS:
    w.goto(k); pump(1300 if k=="perf" else 650); w.grab().save(f"{out}/{k}.png")
    sa,page,h=w.pages[k]; print(k, type(page).__name__, h, round(w.pageh.level))
# timer
w.goto("timer"); pump(600); a._on_key("timer_split"); pump(300); a._on_key("timer_split"); pump(250); a._on_key("timer_split"); a._on_key("timer_pause"); pump(100)
print("timer:", a.timer.state, [round(s,2) for s in a.timer.splits]); a.timer.finish(); print("best:", round(a.cfg["timer"]["best"],2)); w.grab().save(out+"/timer_run.png")
w.page()._set("overlay", True); pump(100); print("overlay:", a.timer_overlay.isVisible(), a.timer_overlay.geometry()); a.timer.reset()
# crosshair library + codes
w.goto("crosshair"); pump(600); pg=w.page(); pg._from_library(A.XHAIR_LIBRARY[8][1]); pump(400); print("lib:", a.cfg["crosshair"]["style"], a.cfg["crosshair"]["radius"])
w.page()._copy_code(); code=q.clipboard().text(); print("code:", code[:30], len(code)); w.page()._reset(); pump(300); q.clipboard().setText(code); w.page()._paste_code(); pump(300); print("pasted:", a.cfg["crosshair"]["style"], a.cfg["crosshair"]["radius"])
print("old/new codes:", A.xhair_decode("RBX-"+__import__("base64").urlsafe_b64encode(b'{"s":"dot","zz":9,"ds":99}').decode()), A.xhair_decode("junk"))
sa=w.pages["crosshair"][0]; sa._pos.jump(sa.max_offset()); pump(100); w.grab().save(out+"/xhair_lib.png")
# themes
w.goto("themes"); pump(600); pg=w.page(); pg._pick(A.THEMES[7]); pump(600); print("preview:", a.theme()["id"], A.ui.accent.name(), A.ui.bg_top.name(), "saved:", a.cfg["theme"]); w.grab().save(out+"/theme_preview.png")
a._end_preview("synth"); pump(600); print("after preview:", a.theme()["id"], A.ui.accent.name())
a.cfg["usage_s"]=800*3600.0; pg._pick(A.THEMES[8]); pump(900); print("prism:", a.cfg["theme"], A.ui.accent.name()); w.grab().save(out+"/theme_prism.png")
w.goto("home"); pump(600); w.grab().save(out+"/home_prism.png")
pg=None; a.set_theme("gold"); pump(600); w.goto("settings"); pump(600); w.grab().save(out+"/gold.png"); a.set_theme("boost"); pump(500)
# launcher click (not running -> open fails on linux)
w.goto("launch"); pump(600); w.page()._click(w.page().tiles[0]); pump(100)
a.set_language("fr"); pump(500)
for k in ["timer","rl","themes"]:
    w.goto(k); pump(650); w.grab().save(f"{out}/fr_{k}.png")
w.collapse(); pump(1200); w.expand(); pump(700); w.collapse(); pump(1200)
a.shutdown(); print("ok", json.load(open("/tmp/rbhome8/Documents/Rubenium/settings.json"))["theme"])
