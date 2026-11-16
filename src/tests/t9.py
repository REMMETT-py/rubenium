import os, sys, time, json, re, shutil
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["RUBENIUM_DEMO"]="1"
H="/tmp/rbhomeU"; shutil.rmtree(H, ignore_errors=True); os.makedirs(H+"/Documents"); os.environ["HOME"]=H
sys.path.insert(0,"/home/claude/release"); sys.argv=["/home/claude/release/Rubenium.py"]
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontMetrics, QColor, QPixmap
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtTest import QTest
import Rubenium as A
src=open('/home/claude/release/Rubenium.py').read(); keys=set()
for m in re.finditer(r'\btr\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+)', src): keys.add(eval("("+m.group(1)+")"))
extra=[n for _,_,n in A.TABS]+[n for _,n in A.RL_CATS]+[t["name"] for t in A.THEMES]
print("missing FR:", sorted(k for k in list(keys)+extra if k not in A.FR))
G="/tmp/fakeRL2"; shutil.rmtree(G, ignore_errors=True)
cook=os.path.join(G,"TAGame","CookedPCConsole"); os.makedirs(cook); os.makedirs(os.path.join(G,"Binaries","Win64"))
open(os.path.join(G,"Binaries","Win64","RocketLeague.exe"),"wb").write(b"v1")
for f in ["explosion_Rekt_SF.upk","Body_Octane_SF.upk","Boost_Bubble_SF.upk"]: open(os.path.join(cook,f),"wb").write(b"O"*5000)
A.setup_logging()
q=QApplication([]); q.setStyleSheet(A.APP_QSS)
a=A.App(q); w=a.window; a.cfg["rl"]["folder"]=G; a.rocket.running=lambda: False
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.005)
out="/tmp/sU"; os.makedirs(out,exist_ok=True)
class FakeCursor:
    p=QPoint(400,400)
    @staticmethod
    def pos(): return FakeCursor.p
A.QCursor=FakeCursor
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
        for t in page.findChildren(A.SwapTile):
            if t.item:
                f=A.font(12.5, A.QFont.Weight.Bold); 
                if QFontMetrics(f).horizontalAdvance("→ "+t.item["new"])>t.width()-A.S(36)-3: bad.append((k,"TILE",t.item["new"]))
    print(tag,"truncated:",bad)
pump(600); w.expand(); pump(900); FakeCursor.p=w.card_global().center()
for lang in ("fr","en"):
    a.set_language(lang); pump(500); FakeCursor.p=w.card_global().center()
    for k,_,_ in A.TABS:
        w.goto(k); pump(1100 if k=="perf" else 550)
        if lang=="fr" and k in ("rl","crosshair"): w.grab().save(f"{out}/fr_{k}.png")
    audit(lang)
# rocket flow through the UI
w.goto("rl"); pump(600); pg=w.page(); tiles=[t for t in pg.findChildren(A.SwapTile) if t.item]
print("tiles:", [(t.item["id"], t.isEnabled()) for t in tiles], "empty:", len([t for t in pg.findChildren(A.SwapTile) if not t.item]))
w.grab().save(out+"/rl_off.png")
pg._toggle(A.RL_BY_ID["octane_fennec"]); pump(250); print("busy visible:", w.busy_w.isVisible()); w.grab().save(out+"/rl_busy.png")
pump(1500); print("after:", a.cfg["rl"]["active"], w.busy_w.isVisible()); w.grab().save(out+"/rl_on.png")
pg=w.page(); pg._toggle(A.RL_BY_ID["bubbles_alpha"]); pump(1700); w.page()._toggle(A.RL_BY_ID["bubbles_dev"]); pump(1700); print("boost:", a.cfg["rl"]["active"])
a.rocket.running=lambda: True; w.page()._toggle(A.RL_BY_ID["atomizer_gentlemates"]); pump(300); print("confirm shown:", w.confirm_w.isVisible(), w.confirm_w._yes._text); w.grab().save(out+"/rl_running.png"); w.confirm_w.hide(); a.rocket.running=lambda: False
# tamper banner
open(os.path.join(cook,"Body_Octane_SF.upk"),"wb").write(b"X"*100); a.rocket.watch(); pump(500); w.grab().save(out+"/rl_changed.png"); print("state:", a.rocket.check())
w.page()._fix(); pump(1700); print("fixed:", a.rocket.check())
# crosshair slots
w.goto("crosshair"); pump(600); pg=w.page()
pg._set("color","#FF3B3B"); pg._set("length",12); pg._slot_click(pg.tiles[0]); pump(200)
print("slot1 saved:", a.cfg["crosshair_presets"]["1"]["color"], a.cfg["crosshair_slot"])
pg._set("color","#00E5FF"); pump(100); print("modified dot:", pg.tiles[0].modified)
pg._slot_click(pg.tiles[1]); pump(100); print("slot2 saved+selected:", a.cfg["crosshair_slot"], a.cfg["crosshair_presets"]["2"]["color"])
pg._slot_click(pg.tiles[0]); pump(500); pg=w.page(); print("loaded slot1:", a.cfg["crosshair"]["color"], a.cfg["crosshair"]["length"], pg.tiles[0].selected)
pg._set("thickness",4); pg._slot_save(); pump(100); print("overwrite:", a.cfg["crosshair_presets"]["1"]["thickness"], pg.tiles[0].modified)
w.grab().save(out+"/xh.png")
pg._slot_clear(); pump(100); print("cleared:", "1" in a.cfg["crosshair_presets"], a.cfg["crosshair_slot"])
# compact: header stays, chip fades
w.goto("home"); pump(600); FakeCursor.p=QPoint(5,5); pump(3300)
print("compact:", round(w.chrome.level,2), "R button visible:", w.body.to_ball.isVisible(), "chip fade:", w.page().chip.fade, "tabbar:", w.body.tabbar.isVisible())
w.grab().save(out+"/compact.png")
FakeCursor.p=w.card_global().center(); pump(800); print("back:", round(w.chrome.level,2), w.page().chip.fade, w.body.tabbar.height())
w.collapse(); pump(1300)
a.shutdown(); c=json.load(open(H+"/Documents/Rubenium/settings.json")); print("ok", c["rl"]["active"], c["crosshair_slot"], c["schema"])
