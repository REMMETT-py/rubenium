import os, sys, time, json, re, shutil
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["RUBENIUM_DEMO"]="1"
shutil.rmtree("/tmp/rbhomeC", ignore_errors=True)
os.environ["HOME"]="/tmp/rbhomeC"; os.makedirs("/tmp/rbhomeC/Documents",exist_ok=True)
sys.path.insert(0,"/home/claude")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon, QPixmap, QColor, QFontMetrics
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtTest import QTest
import Rubenium as A
src=open('/home/claude/Rubenium.py').read(); keys=set()
for m in re.finditer(r'\btr\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+)', src): keys.add(eval("("+m.group(1)+")"))
extra=[n for _,_,n in A.TABS]+[n for n,_ in A.XHAIR_LIBRARY]+[n for _,n in A.RL_SWAPS]+[t["name"] for t in A.THEMES]
print("missing FR:", sorted(k for k in list(keys)+extra if k not in A.FR))
# ramp keeps calibration: defaults == base
base=[[min(65535,int(i*257*0.9)) for i in range(256)] for _ in range(3)]
pr=dict(A.DISPLAY_PROFILE); print("ramp default == base:", A.build_ramp(pr, base)==base)
A.setup_logging()
q=QApplication([]); q.setStyleSheet(A.APP_QSS)
a=A.App(q); w=a.window
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.005)
out="/tmp/sC"; os.makedirs(out,exist_ok=True)
def audit(tag):
    bad=[]
    for k,(sa,page,h) in w.pages.items():
        for lb in page.findChildren(A.Label):
            if lb._wrap_w==0 and lb.text() and lb.width()>0 and lb.text_width()>lb.width()+1: bad.append((k,lb.text()))
        for b in page.findChildren(A.Button):
            if b.width()>0 and b.isVisible() and QFontMetrics(b._font).horizontalAdvance(b._text)+(A.S(20) if b._icon else 0) > b.width()-A.S(12): bad.append((k,"BTN",b._text))
        for sg in page.findChildren(A.Segmented):
            cell=sg.width()/len(sg._labels)-A.S(6)
            for t in sg._labels:
                if QFontMetrics(sg._font).horizontalAdvance(t)>cell: bad.append((k,"SEG",t))
    print(tag,"truncated:",bad)
pump(600); w.expand(); pump(900)
for lang in ("fr","en"):
    a.set_language(lang); pump(500)
    for k,_,_ in A.TABS:
        w.goto(k); pump(1200 if k=="perf" else 550)
        if lang=="en": w.grab().save(f"{out}/{k}.png")
    audit(lang)
# slider lock-in
s=A.Slider(-50,50,10,1,0,marks=[-25,0,25]); s.resize(200,22); s.show(); pump(50)
m=A.S(7); span=200-2*m
s._from_x(m+span*0.5+3); v1=s.value(); s._from_x(m+span*0.5+20); v2=s.value(); print("snap:", v1, v2)
# crosshair
w.goto("crosshair"); pump(600); pg=w.page(); print("library tiles:", len(pg.tiles))
pg.rows["length"].slider.set_value(20); pg._set("length",20); pg._set("dot",True); pg._shape(A.XHAIR_LIBRARY[5][1]); pump(400)
pg=w.page(); print("circle selected:", [t._selected for t in pg.tiles], a.cfg["crosshair"]["style"])
pg._copy_code(); code=q.clipboard().text(); pg._reset(); pump(400); q.clipboard().setText(code); w.page()._paste_code(); pump(400); print("code roundtrip:", a.cfg["crosshair"]["style"])
w.grab().save(out+"/xh_top.png")
# light accent toggles
pm=QPixmap(64,64); pm.fill(QColor("#f2f2f2")); a.art_pixmap=pm; a.refresh_accent(); pump(700); w.goto("settings"); pump(600); w.grab().save(out+"/light_toggles.png"); print("accent:", A.ui.accent.name())
a.art_pixmap=None; a.refresh_accent(); pump(600)
# size slider
p0=w.card_global().topLeft(); a.set_scale(110); pump(900); print("scale 110 same corner:", w.card_global().topLeft()==p0, a.cfg["scale"]); w.grab().save(out+"/s110.png"); a.set_scale(100); pump(800)
# chrome autohide
w.goto("home"); pump(600)
class FakeCursor:
    p=QPoint(5,5)
    @staticmethod
    def pos(): return FakeCursor.p
A.QCursor=FakeCursor
h_full=w.card_global().height(); pump(3200); print("chrome after idle:", round(w.chrome.level,2), "card h", h_full, "->", w.card_global().height(), "tabbar visible", w.body.tabbar.isVisible())
w.grab().save(out+"/compact.png")
FakeCursor.p=w.card_global().center(); pump(800); print("chrome after hover:", round(w.chrome.level,2), w.card_global().height(), w.body.tabbar.isVisible())
FakeCursor.p=QPoint(5,5); pump(3200); print("hidden again:", round(w.chrome.level,2)); w.goto("tools"); pump(700); print("on tools chrome:", round(w.chrome.level,2), w.body.tabbar.isVisible())
pump(3000); print("tools stays:", round(w.chrome.level,2))
w.goto("home"); pump(3200); w.collapse(); pump(1300); w.expand(); pump(900); print("reopen chrome:", round(w.chrome.level,2), w.body.isVisible())
# themes
a.cfg["usage_s"]=800*3600.0
w.goto("themes"); pump(600); w.grab().save(out+"/themes.png")
for i,name in ((1,"grid"),(4,"waves"),(6,"stars"),(7,"aurora"),(8,"prism"),(9,"legend")):
    w.page()._pick(A.THEMES[i]); pump(200); w.goto("home"); FakeCursor.p=w.card_global().center(); pump(700); w.grab().save(f"{out}/home_{name}.png"); w.goto("themes"); pump(500)
# timer
w.goto("timer"); pump(600); w.grab().save(out+"/timer.png")
print("matcher:", A.AppVolume.matcher("Spotify.exe",["spotify"]) is not None, A.AppVolume.matcher("308046B0AF4A39CB",[]) is None)
w.collapse(); pump(1300)
a.shutdown(); c=json.load(open("/tmp/rbhomeC/Documents/Rubenium/settings.json")); print("ok", c["schema"], c["display"]["A"]["vibrance"], c["autohide"])
