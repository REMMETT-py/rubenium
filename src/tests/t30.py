import os, sys, time, shutil, json
os.environ["QT_QPA_PLATFORM"]="offscreen"
L=os.environ.get("L","en")
H="/tmp/h30"+L; shutil.rmtree(H,ignore_errors=True)
for d in (H+"/.rubenium/Rubenium",H+"/Documents/Rubenium"):
    os.makedirs(d); json.dump({"schema":3,"welcome":False,"seen_version":"2026.11.15.2","usage_s":3600*50.0,"lang":L,
      "theme":"aurora","ball_style":"gold","custom_accent":"#FF4B4B","badge":"star","title":"rookie"},open(d+"/settings.json","w"))
    open(d+"/wallet.dat","w").write("oldwallet.abc")
os.environ["HOME"]=H
sys.path.insert(0,"/home/claude/release"); sys.argv=["x"]
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF, Qt, QPoint
import Rubenium as A
q=QApplication([]); q.setStyleSheet(A.APP_QSS); a=A.App(q); w=a.window; W=a.wallet
O="/tmp/shots4/"
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.003)
def shot(n): w.grab().save(O+f"{n}_{L}.png")
print("FRESH: coins", W.balance(), "owned", W.d["owned"], "theme", a.cfg["theme"], "ball", a.cfg["ball_style"], "accent", repr(a.cfg["custom_accent"]), "badges", a.cfg["badges"], "music", W.owns("music"), W.music_wait())
a._casino_scale = lambda base: max(base, min(int(round(base*1.5)), 148))
pump(900); w.expand(); pump(900)
w.goto("games"); pump(1300); shot("lobby"); print("lobby scale", A.ui.scale, "page h", w.page().content_height())
pg=w.page(); pg.enter(1); pump(1200); shot("warn"); print("warning shown, scale", A.ui.scale)
w.page()._accept(); pump(1800); pg=w.page(); print("casino:", a.casino, "scale", A.ui.scale, "game", type(pg.game).__name__, "content h", pg.content_height(), "units", round(pg.content_height()/A.ui.scale))
W.d["coins"]=20000
pk=pg.games[1]; pg._step(1); pg.sync()
for k in range(5):
    pk.drop(); pump(500)
shot("plinko_fly"); pump(2500); shot("plinko"); print("plinko after 5: coins", W.balance(), "keys", W.keys(), "kprog", W.d["kprog"], "busy", pk.busy)
# autoclick guard
pk._presses=[]; t0=time.monotonic()
for k in range(12): pk._presses.append(t0+k*0.5)
print("regular detected:", pk._too_regular(t0+12*0.5))
pg.seg.set_index(2); pg._choose(2); pump(500); bm=pg.games[2]; pg.opts[2].set_index(2); bm.set_option(2); bm.start(); pump(300)
safe=[i for i in range(25) if i not in bm.board]
from PyQt6.QtGui import QMouseEvent
def click(widget, pt):
    ev=QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(pt), QPointF(widget.mapToGlobal(QPoint(int(pt.x()),int(pt.y())))), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    widget.mousePressEvent(ev)
from PyQt6.QtCore import QRectF
for i in safe[:3]:
    click(bm, bm._tile(i, QRectF(bm.rect())).center()); pump(300)
shot("bombs_play"); print("bombs found", bm.found(), "buttons", [b[0] for b in bm.buttons()])
b0=W.balance(); bm.cash(); pump(1500); shot("bombs_won"); print("cashed +", W.balance()-b0, "stake", bm.stake)
bm.start(); pump(200); bomb=list(bm.board)[0]; click(bm, bm._tile(bomb, QRectF(bm.rect())).center()); pump(1600); shot("bombs_lost"); print("lost phase", bm.phase, bm.busy)
pg.seg.set_index(3); pg._choose(3); pump(300); sl=pg.games[3]; sl.spin(); pump(3200); shot("slots"); print("slots", sl.final, sl.win_key())
pg.seg.set_index(4); pg._choose(4); pump(300); dy=pg.games[4]; W.net_offset=A.time.time()-A.time.monotonic(); W.d["daily"]=0; pg.sync()
dy.result=-1; k0=W.keys(); c0=W.balance(); dy.spin(); pump(5300); shot("daily"); print("daily paid coins", W.balance()-c0, "keys", W.keys()-k0, "wait", W.daily_wait())
# RTP
R=A.RNG; n=200000
from math import comb
for i,m in enumerate(A.Plinko.MULTS): print("plinko", A.Plinko.RISKS[i], round(sum(comb(10,k)/1024*x for k,x in enumerate(m)),4))
for bombs in A.Bombs.CHOICES:
    best=0
    for f in range(1,26-bombs):
        ch=comb(25-bombs,f)/comb(25,f); best=max(best, ch*A.bombs_mult(f,bombs))
    print("bombs",bombs,"best RTP %.4f"%best, end="; ")
print()
# leaving mid-round
pg.seg.set_index(0); pg._choose(0); pump(300); bj=pg.games[0]; bj.deal(); pump(1300); print("bj phase", bj.phase)
w.goto("home"); pump(3000); pump(2000); print("after leaving: casino", a.casino, "scale", A.ui.scale, "cfg", a.cfg["scale"], a.cfg["scale_before_games"], "bj ended")
w.goto("games"); pump(1200); print("back to lobby:", not a.casino, type(w.page()).__name__); shot("lobby2")
# --- shop
W.d["coins"]=50000; W.d["keys"]=5; W.d["played"]=3700
w.goto("themes"); pump(1300); shot("shop_look"); print("music owned now", W.owns("music"))
sp=w.page(); sp.c1.page.buy("c1:red"); pump(300)
for wid in q.topLevelWidgets(): pass
print("colour price", W.price("c1:red"), W.price("c2:white"))
sp._section(1); pump(1200); shot("shop_badges")
w.page().open_badge("crown"); pump(1200); shot("badge_detail")
bp=w.page(); bp.picker.var="blue"; bp._variant("blue"); pump(300); shot("badge_buy")
bp._bought_badge("crown","blue"); pump(400); bp._variant("blue"); shot("badge_owned"); print("worn", a.cfg["badges"])
W.d["inv"]+= ["star/gold","skull/titanium"]; bp.set_worn(["crown/blue","star/gold","skull/titanium"]); pump(200)
w.page()._section(2); pump(1200); shot("cases")
w.page().open_case("royal"); pump(1200); shot("case_view")
cp=w.page(); c0=W.balance(); k0=W.keys(); cp._open(A.case_by_id("royal")); pump(900); shot("case_spin1"); pump(2500); shot("case_spin2"); pump(4000); shot("case_result"); pump(800)
print("case: paid", c0-W.balance(), "keys used", k0-W.keys(), "result", cp.reel.result, "inv", len(W.d["inv"]))
# force a gold result visual
cp.reel.spin(dict(badge="crown", var="gold", rarity="super", new=True, refund=0)); pump(7600); shot("case_gold"); pump(500)
cp.reel.spin(dict(badge="crown", var="lava", rarity="rare", new=False, refund=1500)); W.d["pending"]=1500; pump(7600); shot("case_dup")
# odds sim
import random
cnt={"basic":0,"rare":0,"very":0,"super":0}; W.d["coins"]=10**9
for i in range(20000):
    W.d["keys"]=5; r=W.open_case("street"); cnt[r["rarity"]]+=1
print("street odds sim", {k:round(v/200,2) for k,v in cnt.items()})
W.d["inv"]=W.d["inv"][:5]
w.goto("home"); pump(800); w.page().set_compact(0.0); pump(400); shot("home_flair")
# admin sandbox
W.d["coins"]=40; W.d["keys"]=0; W.admin=True; print("admin", W.balance(), W.keys(), W.has_badge("crown","gold")); W.open_case("royal"); W.buy_badge("eye","red"); W.admin=False
print("after admin coins", W.balance(), "keys", W.keys())
a.shutdown()
# restart: persistence
q2=None
