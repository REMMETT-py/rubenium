import os, sys, time, shutil, json
os.environ["QT_QPA_PLATFORM"]="offscreen"
H="/tmp/h12"; shutil.rmtree(H,ignore_errors=True)
for d in (H+"/.rubenium/Rubenium",H+"/Documents/Rubenium"): os.makedirs(d); json.dump({"schema":3,"welcome":False,"seen_version":"2026.11.15.1","usage_s":3600*30.0,"theme":"comets","ball_style":"echo","ring_style":"line","accent_from_art":True,"custom_accent":"#123456","lang":os.environ.get("L","en")},open(d+"/settings.json","w"))
os.environ["HOME"]=H
sys.path.insert(0,"/home/claude/release"); sys.argv=["x"]
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPoint, QPointF, Qt, QEvent
import Rubenium as A
q=QApplication([]); q.setStyleSheet(A.APP_QSS); a=A.App(q); w=a.window; W=a.wallet
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.003)
out="/tmp/shots/"; L=os.environ.get("L","en")
pump(900)
print("migrated: coins", W.balance(), "owned", sorted(W.d["owned"]))
print("worn kept:", a.cfg["theme"], a.cfg["ball_style"], a.cfg["ring_style"], "| unowned colour dropped:", repr(a.cfg["custom_accent"]), "| accent", A.ui.accent.name())
print("file exists:", os.path.exists(A._file()), "| reload ok:", A._unpack(A._read_file())["coins"]==W.balance())
# no debt, buy rules
print("spend too much:", W.spend(10**7), "| spend 100:", W.spend(100), W.balance())
print("theme order: aurora blocked by", W.blocked_by("theme:aurora"), "| c2 blocked:", W.blocked_by("c2:red"))
print("buy red:", W.buy("c1:red"), W.owns("c1:red"), W.balance())
# tamper
t=A._read_file(); body,sig=t.rsplit(".",1); import base64
d=json.loads(base64.b64decode(body)); d["coins"]=999999; fake=base64.b64encode(json.dumps(d).encode()).decode()+"."+sig
print("edited wallet rejected:", A._unpack(fake) is None)
# time drop
W._last=time.monotonic()-1.0; W.d["progress"]=899.5; b=W.balance(); W._second(); print("drop +25:", W.balance()-b, "next in", W.next_drop())
W._last=time.monotonic()-500; b=W.balance(); W._second(); print("sleep gap ignored:", W.balance()==b)
# shop page
w.expand(); pump(900); w.goto("themes"); pump(1000); w.grab().save(out+f"s0_{L}.png")
pg=w.page(); sa=w.pages["themes"][0]
for n,f in enumerate((0.33,0.66,1.0)):
    sa._target=sa.max_offset()*f; sa._pos.jump(sa._target); pump(300); w.grab().save(out+f"s{n+1}_{L}.png")
W.d["coins"]=200000
for ident,_n,_h in A.COLOURS[:-1]: W.buy(f"c1:{ident}")
pg._bought("c1:rose") if not W.owns("c1:rose") else None
sa._target=0; sa._pos.jump(0); pump(450); w.grab().save(out+f"melt_{L}.png"); pump(700); print("melted -> line:", pg.c1.fused, "c2 open:", W.blocked_by("c2:red")=="")
pg._bought("c2:pink"); pg._bought("badge:crown"); pg._bought("title:legend"); pump(400); w.grab().save(out+f"s_after_{L}.png")
print("second colour on:", A.ui.accent2 is not None, "badge/title:", a.cfg["badge"], a.cfg["title"])
# flair on home when chrome hides
w.goto("home"); pump(900); hp=w.page(); hp.set_compact(0.0); pump(100); w.grab().save(out+f"home_flair_{L}.png"); print("flair visible:", hp.flair.isVisible(), hp.flair.fade)
hp.set_compact(1.0)
# merged pages
for k in ("crosshair","perf"):
    w.goto(k); pump(1100); w.grab().save(out+f"m_{k}_{L}.png"); print(k, type(w.page()).__name__, [type(x).__name__ for x in w.page().subs])
# settings hold button
w.goto("settings"); pump(900); hb=[c for c in w.page().findChildren(A.HoldButton)][0]
from PyQt6.QtGui import QMouseEvent
def click(wd, hold=0):
    pos=QPointF(10,10); 
    wd.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress,pos,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)); pump(hold or 30)
    wd.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease,pos,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier)); pump(60)
fired=[]; hb.confirmed.connect(lambda: fired.append(1))
click(hb); click(hb); print("after 2 clicks stage:", hb.stage, fired); click(hb,400); print("short hold:", fired); click(hb,1800); print("long hold fired:", fired)
pump(600); print("reset kept worn + coins:", a.cfg["badge"], a.cfg["title"], W.balance()>0)
a.shutdown()
