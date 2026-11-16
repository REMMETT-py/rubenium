import os, sys, time, shutil, json
os.environ["QT_QPA_PLATFORM"]="offscreen"
L=os.environ.get("L","en")
H="/tmp/h50"+L; shutil.rmtree(H,ignore_errors=True)
for d in (H+"/.rubenium/Rubenium",H+"/Documents/Rubenium"):
    os.makedirs(d); json.dump({"schema":3,"welcome":False,"seen_version":"2026.11.15.4","lang":L,"ball_style":"echo","badges":[]},open(d+"/settings.json","w"))
os.environ["HOME"]=H; os.environ["RUBENIUM_DEMO"]="1"
sys.path.insert(0,"/home/claude/release"); sys.argv=["x"]
from PyQt6.QtWidgets import QApplication
import Rubenium as A
q=QApplication([]); q.setStyleSheet(A.APP_QSS); a=A.App(q); w=a.window; W=a.wallet
O="/tmp/shots6/"; os.makedirs(O,exist_ok=True)
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.003)
def shot(n): w.grab().save(O+f"{n}_{L}.png")
print("tabs:", [t[0] for t in A.TABS], "| ball style after echo:", a.cfg["ball_style"])
print("medal blocked:", A.blocked_source("Medal.exe"), A.blocked_source("MedalTV.Medal"), "spotify:", A.blocked_source("Spotify.exe"))
W.d["coins"]=10**6; W.d["played"]=1500; W.d["inv"]=["crown/gold","star/lava","skull/titanium"]; a.cfg["badges"]=list(W.d["inv"])
for c in A.COLOURS: W.d["owned"].append("c1:"+c[0])
for st in A.R_STYLES+A.RING_STYLES: pass
W.d["owned"]+= ["r:outline","r:neon","r:whitegold","r:gold","ring:line","ring:neon","ring:whitegold","ring:gold"]
pump(900); w.expand(); pump(900)
pg=w.page(); pg.title.set_text("Hurry Up, We're Dreaming (Extended Night Version) - Remastered 2024"); pg.chip.fade=0.0; pg.set_compact(0.0); pump(600); shot("home")
w.goto("crosshair"); pump(1200); shot("screen_top")
sp=w.page(); print("screen parts:", [type(s).__name__ for s in sp.subs])
xh=sp.subs[0]; print("crosshair preset? parked:", xh.hue.slider.parked, "dots resting:", xh.sw.resting)
from PyQt6.QtWidgets import QScrollArea
sa=w.findChildren(QScrollArea)
xh._hue(200); pump(300); print("after slider: parked", xh.hue.slider.parked, "resting", xh.sw.resting)
w.grab().save(O+f"screen_slider_{L}.png")
xh._set("color", A.XH_COLORS[0]); pump(300); print("after dot: parked", xh.hue.slider.parked, "resting", xh.sw.resting)
for s in sa:
    if s.isVisible(): s.verticalScrollBar().setValue(s.verticalScrollBar().maximum()); pump(400)
shot("screen_bottom")
w.goto("perf"); pump(1200); print("pc parts:", [type(s).__name__ for s in w.page().subs])
w.goto("themes"); pump(1300); shot("shop")
pg=w.page(); print("music text:", pg.music_wait.text())
a.cfg["custom_accent"]="#FFFFFF"; pg.c1.update(); pump(200)
for s in w.findChildren(QScrollArea):
    if s.isVisible(): s.verticalScrollBar().setValue(int(s.verticalScrollBar().maximum()*0.45)); pump(400)
shot("shop_balls")
pg.c1.line._pick(pg.c1.line._bar().center().x(), False); pump(400); shot("shop_slider")
a.shutdown()
