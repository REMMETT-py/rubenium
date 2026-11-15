import os, sys, time, shutil, json, subprocess
sys.path.insert(0,"/tmp"); import bridge; bridge.serve()
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["RUBENIUM_API"]="http://127.0.0.1:8766"; os.environ["NO_PROXY"]="127.0.0.1"
for k in ("HTTP_PROXY","http_proxy"): os.environ.pop(k,None)
L=os.environ.get("L","en"); H="/tmp/h110"; shutil.rmtree(H,ignore_errors=True)
for d in (H+"/.rubenium/Rubenium",H+"/Documents/Rubenium"):
    os.makedirs(d); json.dump({"schema":3,"welcome":False,"seen_version":"x","lang":L,"casino_warned":True},open(d+"/settings.json","w"))
os.environ["HOME"]=H
subprocess.run(["psql","-h","/tmp","-p","5544","-U","postgres","-q","-c","update profiles set coins=5000, keys=2, minutes=100, spin_at=null, spin_prize=null where username='Ruben'; delete from rb_rounds; delete from rb_requests;"])
sys.path.insert(0,"/home/claude/release"); sys.argv=["x"]
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF, QPoint, Qt, QRectF
from PyQt6.QtGui import QMouseEvent
import Rubenium as A
A.Online._load = lambda self: self.__dict__.update(s={"refresh_token":"R-ruben","username":"Ruben","access_token":"A-ruben","expires_at":9e12}, minutes=100)
q=QApplication([]); q.setStyleSheet(A.APP_QSS); a=A.App(q); w=a.window; ec=a.econ; O="/tmp/shots11/"; os.makedirs(O,exist_ok=True)
a._casino_scale = lambda base: max(base, min(int(round(base*1.5)), 148))
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.003)
def shot(n): w.grab().save(O+f"{n}_{L}.png")
def server(): return int(subprocess.run(["psql","-h","/tmp","-p","5544","-U","postgres","-t","-A","-c","select coins from profiles where username='Ruben'"],capture_output=True,text=True).stdout)
pump(3000); w.expand(); pump(900); w.goto("games"); pump(1300); shot("lobby")
w.page().enter(0); pump(2200); pg=w.page(); print("casino:", a.casino, [type(g).__name__ for g in pg.games])
bj=pg.games[0]; bj.deal(); pump(1800); shot("bj"); print("bj:", bj.phase, len(bj.player), len(bj.dealer), "coins", ec.coins)
if bj.phase=="player": bj.stand()
pump(5000); print("bj end:", bj.phase, bj.busy, "| screen", ec.coins, "server", server())
def choose(i): pg.seg.set_index(i); pg._choose(i); pump(400)
choose(1); pk=pg.games[1]
for k in range(3): pk.drop(); pump(550)
shot("plinko"); pump(3200); print("plinko:", pk.busy, "| screen", ec.coins, "server", server())
choose(2); bm=pg.games[2]; bm.start(); pump(900)
def click(g,i):
    pt=g._tile(i, QRectF(g.rect())).center()
    g.mousePressEvent(QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(pt), QPointF(pt), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
for i in (0,6,12):
    if bm.phase=="play": click(bm,i); pump(800)
shot("bombs"); print("bombs:", bm.phase, "found", bm.found(), sorted(bm.shown)[:5])
if bm.phase=="play": bm.cash(); pump(1500)
print("bombs end:", bm.phase, bm.busy, "| screen", ec.coins, "server", server())
choose(3); sl=pg.games[3]; sl.spin(); pump(3400); shot("slots"); print("slots:", sl.final, "| screen", ec.coins, "server", server())
choose(4); dc=pg.games[4]; dc.play(); pump(700); shot("dice0"); pump(1500); shot("dice"); print("dice: roll", dc.roll, dc.won, "| screen", ec.coins, "server", server())
choose(5); rk=pg.games[5]; rk.start(); pump(2500); shot("rocket"); print("rocket:", rk.phase, round(rk.mult_now(),2), [b[0] for b in rk.buttons()])
if rk.phase=="fly": rk.cash(); pump(1200)
shot("rocket2"); print("rocket end:", rk.phase, rk.crashed, rk.end_mult, "| screen", ec.coins, "server", server())
choose(6); fs=pg.games[6]; pump(1200); print("spin wait:", a.wallet.daily_wait(), [b[0] for b in fs.buttons()]); fs.spin(); pump(5600); shot("spin"); print("spin prize waiting:", fs.collect, [b[0] for b in fs.buttons()], "| screen", ec.coins, "server", server())
fs.take_prize(); pump(900); print("collected: screen", ec.coins, "server", server(), "keys", ec.keys, "| next spin in", a.wallet.daily_wait())
a.leave_casino(); pump(1800); print("left: scale", A.ui.scale)
a.shutdown()
