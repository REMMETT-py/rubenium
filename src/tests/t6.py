import os, sys, time, json, re, shutil
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["RUBENIUM_DEMO"]="1"
shutil.rmtree("/tmp/rbhomeA", ignore_errors=True)
os.environ["HOME"]="/tmp/rbhomeA"; os.makedirs("/tmp/rbhomeA/Documents",exist_ok=True)
sys.path.insert(0,"/home/claude")
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtGui import QIcon, QPixmap, QColor, QFontMetrics
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtTest import QTest
import Rubenium as A
src=open('/home/claude/Rubenium.py').read(); keys=set()
for m in re.finditer(r'\btr\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+)', src): keys.add(eval("("+m.group(1)+")"))
extra=[n for _,_,n in A.TABS]+[n for n,_ in A.XHAIR_LIBRARY]+[n for _,n in A.RL_SWAPS]+[t["name"] for t in A.THEMES]
print("missing FR:", sorted(k for k in list(keys)+extra if k not in A.FR))
A.setup_logging()
q=QApplication([]); q.setStyleSheet(A.APP_QSS)
a=A.App(q); w=a.window
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.005)
out="/tmp/sA"; os.makedirs(out,exist_ok=True)
pm=QPixmap(48,48); pm.fill(QColor("#c33"))
a._apps=[{"name":n,"path":"x","exe":e,"icon":QIcon(pm)} for n,e in [("Steam","steam.exe"),("Rocket League","rocketleague.exe"),("Discord","discord.exe")]]
def audit(tag):
    bad=[]
    for k,(sa,page,h) in w.pages.items():
        for lb in page.findChildren(A.Label):
            if lb._wrap_w==0 and lb.text() and lb.width()>0 and lb.text_width()>lb.width()+1: bad.append((k,lb.text(),lb.text_width(),lb.width()))
        for b in page.findChildren(A.Button):
            if b.width()>0 and QFontMetrics(b._font).horizontalAdvance(b._text)+(A.S(20) if b._icon else 0) > b.width()-A.S(12): bad.append((k,"BTN",b._text))
        for sg in page.findChildren(A.Segmented):
            cell=sg.width()/len(sg._labels)-A.S(6)
            for t in sg._labels:
                if QFontMetrics(sg._font).horizontalAdvance(t)>cell: bad.append((k,"SEG",t))
    print(tag,"truncated:",bad)
pump(600); w.expand(); pump(900)
for lang in ("en","fr"):
    a.set_language(lang); pump(500)
    for k,_,_ in A.TABS:
        w.goto(k); pump(1300 if k=="perf" else 600)
        if lang=="fr": w.grab().save(f"{out}/{k}.png")
    audit(lang)
a.set_language("en"); pump(500)
# position stability
w.goto("home"); pump(600); p0=w.card_global().topLeft(); print("card at", p0)
w.goto("tools"); pump(700); print("after tab:", w.card_global().topLeft()==p0)
a.set_scale(130); pump(700); print("after scale:", w.card_global().topLeft()==p0, w.card_global()); a.set_scale(100); pump(700)
w.collapse(); pump(1300); print("ball docked", w.ball.center); w.expand(); pump(1300); print("reopen same:", w.card_global().topLeft()==p0, w.expanded, w.body.isVisible())
# drag then reopen
w.begin_drag(QPoint(0,0)); w.drag_to(QPoint(-250,300)); w.end_drag(); pump(400); p1=w.card_global().topLeft(); print("dragged to", p1, "maxh", w.card_max_h)
w.goto("crosshair"); pump(700); print("tall page fits:", w.card_global().bottom()<=800, w.card_global())
w.collapse(); pump(1300); w.expand(); pump(1300); print("reopen at drag:", w.card_global().topLeft()==p1)
# move ball manually -> opens at ball
w.collapse(); pump(1300); w.ball.set_center(QPoint(300,300)); w.expand(); pump(900); print("opens at ball:", w.card_global().topLeft())
# crosshair
pg=w.page(); pg._shape(A.XHAIR_LIBRARY[9][1]); pg._set("size",200); pump(100); print("xh:", a.cfg["crosshair"]["style"], A.crosshair_extent(a.cfg["crosshair"]), [t._selected for t in pg.tiles].index(True))
pg._copy_code(); code=q.clipboard().text(); pg._reset(); pump(400); print("reset:", a.cfg["crosshair"]["color"], a.cfg["crosshair"]["length"]); q.clipboard().setText(code); w.page()._paste_code(); pump(400); print("paste:", a.cfg["crosshair"]["style"], a.cfg["crosshair"]["size"])
w.grab().save(out+"/xh.png")
# themes
w.goto("themes"); pump(600); pg=w.page(); pg._pick(A.THEMES[9]); pump(700); print("drawer:", w.drawer.isVisible(), w.drawer.geometry(), "preview", a.theme()["id"], len(w._sparks)); w.grab().save(out+"/th_card.png"); w.drawer.grab().save(out+"/drawer.png")
w.drawer.close_drawer(); pump(500); print("closed:", w.drawer.isVisible(), a.theme()["id"])
a.cfg["usage_s"]=600*3600.0
for i,name in ((4,"hex"),(7,"aurora"),(8,"prism")):
    pg._pick(A.THEMES[i]); pump(300); w.goto("home"); pump(600); w.grab().save(f"{out}/home_{name}.png"); w.goto("themes"); pump(600); pg=w.page()
w.grab().save(out+"/themes_unlocked.png"); print("theme:", a.cfg["theme"])
# confirm
w.goto("launch"); pump(600); t=w.page().tiles[0]; t.set_running(True); w.page()._click(t); pump(300); print("confirm:", w.confirm_w.isVisible()); w.grab().save(out+"/confirm.png")
QTest.mouseClick(w.confirm_w._no, Qt.MouseButton.LeftButton); pump(100); print("after no:", w.confirm_w.isVisible(), t.running)
w.collapse(); pump(1300)
a.shutdown(); c=json.load(open("/tmp/rbhomeA/Documents/Rubenium/settings.json")); print("ok", c["card"], c["opacity"])
