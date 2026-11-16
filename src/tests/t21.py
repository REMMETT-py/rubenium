import os, sys, time, shutil, json
os.environ["QT_QPA_PLATFORM"]="offscreen"
H="/tmp/h13"; shutil.rmtree(H,ignore_errors=True)
for d in (H+"/.rubenium/Rubenium",H+"/Documents/Rubenium"): os.makedirs(d); json.dump({"schema":3,"welcome":False,"seen_version":"2026.11.15.1","usage_s":3600*50.0,"lang":os.environ.get("L","en")},open(d+"/settings.json","w"))
os.environ["HOME"]=H
sys.path.insert(0,"/home/claude/release"); sys.argv=["x"]
from PyQt6.QtWidgets import QApplication
import Rubenium as A
q=QApplication([]); q.setStyleSheet(A.APP_QSS); a=A.App(q); w=a.window; W=a.wallet
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.003)
out="/tmp/shots/"; L=os.environ.get("L","en")
pump(900); w.expand(); pump(900); w.goto("games"); pump(1500)
print("scale while warning/games:", A.ui.scale, a.cfg["scale_before_games"]); w.grab().save(out+f"g_warn_{L}.png")
pg=w.page(); print("warning shown:", pg.game is None); pg._accept(); pump(1200); pg=w.page(); print("after accept game:", type(pg.game).__name__)
w.grab().save(out+f"g_bj0_{L}.png")
bj=pg.games[0]; b0=W.balance(); bj.deal(); pump(1300); w.grab().save(out+f"g_bj1_{L}.png"); print("bet taken:", b0-W.balance(), "busy:", bj.busy, "seg locked:", not pg.seg.isEnabled())
if bj.phase=="player": bj.stand()
pump(4500); w.grab().save(out+f"g_bj2_{L}.png"); print("round over:", bj.phase, not bj.busy, "balance", W.balance())
pg.seg.changed.emit(1); pg.seg.set_index(1); pump(500); ch=pg.games[1]; ch.start(); pump(500); 
for _ in range(2):
    if ch.phase=="run": ch.go(); pump(450)
w.grab().save(out+f"g_ch_{L}.png"); 
if ch.phase=="run": ch.cash()
pump(1200); print("chicken done:", ch.phase, W.balance())
pg.seg.changed.emit(2); pg.seg.set_index(2); pump(400); wh=pg.games[2]; pg._number(1); wh.spin(); pump(2000); w.grab().save(out+f"g_wh_{L}.png"); pump(3200); print("wheel:", wh.SLOTS[wh.result], "picked", wh.choice, not wh.busy, W.balance())
pg.seg.changed.emit(3); pg.seg.set_index(3); pump(400); sl=pg.games[3]; sl.spin(); pump(900); w.grab().save(out+f"g_sl_{L}.png"); pump(2200); w.grab().save(out+f"g_sl2_{L}.png"); print("slots:", sl.final, not sl.busy, W.balance())
pg.seg.changed.emit(4); pg.seg.set_index(4); pump(400); dy=pg.games[4]
print("daily without internet:", W.daily_wait(), [b[0] for b in dy.buttons()])
W.net_offset=A.time.time()-A.time.monotonic(); pg.sync(); print("daily ready:", W.daily_wait(), [ (b[0],b[3]) for b in dy.buttons()]); b0=W.balance(); dy.spin(); pump(5200); print("daily prize:", W.balance()-b0, "| again in", W.daily_wait(), "| still locked:", W.daily_wait()>0)
w.grab().save(out+f"g_daily_{L}.png")
# no debt
W.d["coins"]=5; pg.seg.changed.emit(3); pg.seg.set_index(3); pump(300); print("bet with 5 coins:", pg.bet()); sl.spin(); pump(300); print("cannot spin:", not sl.busy, W.balance())
# leaving games restores size
w.goto("home"); pump(1800); print("scale after leaving:", A.ui.scale, a.cfg["scale"], a.cfg["scale_before_games"])
# RTP sanity (pure maths on the same code)
import random; R=A.RNG; n=200000
def slots():
    f=[R.choices(A.Slots.SYMBOLS,A.Slots.WEIGHTS)[0] for _ in range(3)]
    return A.Slots.TRIPLE[f[0]] if f[0]==f[1]==f[2] else (1.5 if len(set(f))==2 else 0)
print("slots RTP %.3f"%(sum(slots() for _ in range(n))/n))
for c in A.Wheel.NUMBERS: print("wheel", c, "RTP %.3f"%(sum((c+1) for _ in range(n) if A.Wheel.SLOTS[R.randrange(25)]==c)/n), end="; ")
print(); print("chicken RTP per lane:", [round(A.Chicken.MULT[k]*0.82**(k+1),3) for k in (0,3,7)])
# admin sandbox
W.d["coins"]=40; W.admin=True; print("admin balance:", W.balance(), "owns all:", W.owns("theme:legend")); W.spend(5000); W.add(999); W.buy("theme:legend"); W.admin=False
print("after admin: coins", W.balance(), "legend owned:", W.owns("theme:legend"))
a.shutdown()
