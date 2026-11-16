import os, sys, time, json, re, glob, shutil
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["RUBENIUM_DEMO"]="1"
shutil.rmtree("/tmp/rbhome6", ignore_errors=True)
os.environ["HOME"]="/tmp/rbhome6"; os.makedirs("/tmp/rbhome6/Documents",exist_ok=True)
sys.path.insert(0,"/home/claude")
from PyQt6.QtWidgets import QApplication
import Rubenium as A; core=A; lang_fr=A
keys=set()
for f in ['/home/claude/Rubenium.py']:
    for m in re.finditer(r'\btr\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+)', open(f).read()): keys.add(eval("("+m.group(1)+")"))
print("keys",len(keys),"missing FR:", sorted(k for k in keys if k not in lang_fr.FR))
print("unused FR:", sorted(k for k in lang_fr.FR if k not in keys)[:40])
core.setup_logging()
q=QApplication([]); q.setStyleSheet(A.APP_QSS)
a=A.App(q); w=a.window
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.005)
out="/tmp/s6"; os.makedirs(out,exist_ok=True)
pump(700)
print("ball visible:", w.ball.isVisible() if hasattr(w,'ball') else '?', "main visible:", w.isVisible())
w.expand(); pump(900)
for k in ["home","lyrics","crosshair","display","perf","tools","rl","settings"]:
    w.goto(k); pump(1400 if k=="perf" else 700); w.grab().save(f"{out}/{k}.png")
    sa,page,h=w.pages[k]; print(k, type(page).__name__, h, round(w.pageh.level))
a.set_language("fr"); pump(500)
for k in ["tools","settings","rl"]:
    w.goto(k); pump(700); w.grab().save(f"{out}/fr_{k}.png")
w.goto("tools"); pump(700); pg=w.page(); pg._test(); pump(3200); pg._dns(); pg._memory(); pump(100)
a.cfg["hud"]["clock"]=True; a.set_hud(True); pump(1300); print("hud:", a.hud._items)
a.set_language("en"); pump(400); w.goto("tools"); pump(700); w.grab().save(out+"/tools_en.png")
w.begin_drag(w.pos()); from PyQt6.QtCore import QPoint; w.drag_to(w.pos()+QPoint(5000,5000)); w.end_drag(); print("clamped card:", w.geometry())
w.goto("home"); pump(600)
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt
pm=QPixmap(64,64); pm.fill(QColor("#101010")); a.art_pixmap=pm; a.refresh_accent(); pump(700); print("grey accent:", A.ui.accent.name()); w.grab().save(out+"/grey.png")
pm.fill(QColor("#c8e020")); a.refresh_accent(); pump(700); print("lime accent:", A.ui.accent.name()); w.goto("settings"); pump(700); w.grab().save(out+"/lime.png")
a.art_pixmap=None; a.refresh_accent(); pump(700); print("default:", A.ui.accent.name()); w.goto("home"); pump(600); w.grab().save(out+"/home.png")
# drag from the page body
pg=w.page(); p0=w.pos(); QTest.mousePress(pg, Qt.MouseButton.LeftButton, pos=QPoint(200,60)); 
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtCore import QEvent, QPointF
gp=pg.mapToGlobal(QPoint(200,60))
ev=QMouseEvent(QEvent.Type.MouseMove, QPointF(150,60), QPointF(gp+QPoint(-50,0)), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier); q.sendEvent(w.body, ev)
QTest.mouseRelease(w.body, Qt.MouseButton.LeftButton); print("dragged by:", w.pos()-p0)
w.collapse(); pump(1200); w.expand()
for ms,name in ((90,"m1"),(110,"m2"),(110,"m3"),(400,"m4")): pump(ms); print(name, round(w.morph.level,2)); w.grab().save(f"{out}/{name}.png")
w.collapse(); pump(1200); print("after collapse main visible:", w.isVisible(), "ball:", w.ball.isVisible(), w.ball.geometry()); w.ball.grab().save(out+"/ball.png")
a.shutdown(); print(os.listdir("/tmp/rbhome6/Documents"), os.listdir("/tmp/rbhome6/Documents/Rubenium"))
