import os, sys, time, shutil, json, subprocess
sys.path.insert(0,"/tmp"); import bridge; bridge.serve()
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["RUBENIUM_API"]="http://127.0.0.1:8766"; os.environ["NO_PROXY"]="127.0.0.1"
for k in ("HTTP_PROXY","http_proxy"): os.environ.pop(k,None)
L=os.environ.get("L","en"); H="/tmp/h100"; shutil.rmtree(H,ignore_errors=True)
for d in (H+"/.rubenium/Rubenium",H+"/Documents/Rubenium"):
    os.makedirs(d); json.dump({"schema":3,"welcome":False,"seen_version":"x","lang":L,"casino_warned":True},open(d+"/settings.json","w"))
os.environ["HOME"]=H
subprocess.run(["psql","-h","/tmp","-p","5544","-U","postgres","-q","-c","update profiles set coins=20000, keys=6, minutes=1900, equip='{}', spin_at=null, spin_prize=null, daily_at=null where username='Ruben'; delete from rb_items where owner='00000000-0000-0000-0000-000000000001'; delete from rb_seen; delete from rb_requests; delete from rb_rounds; delete from rb_case_stats; insert into rb_items(owner,item,origin) values ('00000000-0000-0000-0000-000000000001','badge:crown:gold','t'),('00000000-0000-0000-0000-000000000001','badge:galaxy:prime','t'),('00000000-0000-0000-0000-000000000001','badge:star:lava','t'); insert into rb_seen values ('00000000-0000-0000-0000-000000000001','badge:crown:gold'),('00000000-0000-0000-0000-000000000001','badge:galaxy:prime'),('00000000-0000-0000-0000-000000000001','badge:star:lava'),('00000000-0000-0000-0000-000000000001','badge:moon:blue');"])
sys.path.insert(0,"/home/claude/release"); sys.argv=["x"]
from PyQt6.QtWidgets import QApplication
import Rubenium as A
A.Online._load = lambda self: self.__dict__.update(s={"refresh_token":"R-ruben","username":"Ruben","access_token":"A-ruben","expires_at":9e12}, minutes=1900)
q=QApplication([]); q.setStyleSheet(A.APP_QSS); a=A.App(q); w=a.window; ec=a.econ; O="/tmp/shots10/"; os.makedirs(O,exist_ok=True)
a._casino_scale = lambda base: max(base, min(int(round(base*1.5)), 148))
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.003)
def shot(n): w.grab().save(O+f"{n}_{L}.png")
pump(3000); print("econ ready:", ec.ready, "coins", ec.coins, "keys", ec.keys, "items", len(ec.items))
w.expand(); pump(900); w.goto("themes"); pump(1300); shot("look")
print("progression: gold ball (100h) owned at 31h:", a.wallet.owns("r:gold"), "| white gold (30h):", a.wallet.owns("r:whitegold"), "| themes:", [t["id"] for t in A.THEMES if a.wallet.owns("theme:"+t["id"])])
sp=w.page(); sp._section(1); pump(1300); shot("badges")
w.page().open_badge("crown"); pump(1200); shot("crown")
pg=w.page(); print("crown picked:", pg.picker.var, "| button:", pg.badge_btn._text, "| sell:", pg.sell_btn._text)
pg._badge_action(); pump(900); print("worn:", ec.badges_worn())
pg=w.page(); pg._variant("blue"); pump(200); print("blue button:", pg.badge_btn._text); ec.buy("badge:crown:blue", pg._bought_item); pump(900); print("bought blue: coins", ec.coins, ec.owns("badge:crown:blue"))
shot("crown2")
w.page().open_badge("galaxy"); pump(1200); shot("galaxy")
w.page()._section(2); pump(1500); shot("cases")
w.page().open_case("vault"); pump(1300); shot("vault")
cp=w.page(); c0,k0=ec.coins,ec.keys; cp._open(cp.reel.case); pump(1500); shot("spin"); pump(7500); shot("result")
print("case: paid", c0-ec.coins, "keys", k0-ec.keys, "result", {k:cp.reel.result.get(k) for k in ("tier","item","won","pity")}, "| items now", len(ec.items))
w.page().open_case("daily"); pump(1500); cp=w.page(); cp._open(cp.reel.case); pump(8800); shot("daily"); print("daily:", {k:cp.reel.result.get(k) for k in ("tier","item","won","won_keys")}, "| wait now", cp.daily_wait())
w.goto("home"); pump(900); w.page().set_compact(0.0); w.page().chip.fade=0.0; w.page()._place_flair(); pump(400); shot("home")
a.shutdown()
