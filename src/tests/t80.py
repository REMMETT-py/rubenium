import os, sys, time, shutil, subprocess
sys.path.insert(0,"/tmp"); import bridge; bridge.serve()
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["RUBENIUM_API"]="http://127.0.0.1:8766"; os.environ["NO_PROXY"]="127.0.0.1"
for k in ("HTTP_PROXY","http_proxy"): os.environ.pop(k,None)
H="/tmp/h80"; shutil.rmtree(H,ignore_errors=True); os.makedirs(H); os.environ["HOME"]=H
subprocess.run(["psql","-h","/tmp","-p","5544","-U","postgres","-q","-c","update profiles set coins=1000, keys=3, minutes=130, equip='{}', imported=false where username='Ruben'; delete from rb_items where owner='00000000-0000-0000-0000-000000000001'; delete from rb_seen; delete from rb_requests;"])
sys.path.insert(0,"/home/claude/Rubenium")
from PyQt6.QtWidgets import QApplication
q=QApplication([])
from rubenium import online, econ
class Ctx: state=None
ctx=Ctx(); on=online.Online(ctx); ctx.online=on
on.s={"refresh_token":"R-ruben","username":"Ruben","access_token":"A-ruben","expires_at":9e12}
ec=econ.Econ(ctx)
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.003)
got=[]
ec.start(); pump(2500)
print("ready:", ec.ready, "coins", ec.coins, "keys", ec.keys, "minutes", ec.minutes, "catalog", len(ec.catalog), "cases", [c["id"] for c in ec.cases], "cfg vendor", ec.cfg.get("vendor_share"))
print("price heart grey:", ec.price("badge:heart:grey"), "| gold not sold:", ec.price("badge:crown:gold"), "| rarity crown gold:", ec.rarity("badge:crown:gold"), "| vendor:", ec.vendor_price("badge:heart:grey"))
print("progress: theme2 unlocked", ec.unlocked("prog:theme:2"), "| ball1 (5h) locked", not ec.unlocked("prog:ball:1"))
ec.buy("badge:heart:grey", lambda ok,d: got.append(("buy",ok))); pump(900)
print(got[-1], "coins", ec.coins, "owns", ec.owns("badge:heart:grey"), "copies", len(ec.copies("badge:heart:grey")))
ec.buy("badge:crown:blue", lambda ok,d: got.append(("buy epic",ok,d))); pump(900); print(got[-1])
ec.wear("badge1","badge:heart:grey", lambda ok,d: got.append(("wear",ok))); pump(900); print(got[-1], ec.badges_worn())
ec.wear("theme","prog:theme:2", lambda ok,d: got.append(("theme",ok))); pump(900); print(got[-1], ec.worn("theme"))
ec.sell(ec.copies("badge:heart:grey")[0], lambda ok,d: got.append(("sell",ok,d.get("paid") if ok else d))); pump(900)
print(got[-1], "coins", ec.coins, "owns", ec.owns("badge:heart:grey"), "had", ec.had("badge:heart:grey"), "worn", ec.badges_worn())
ec.call("rb_slots", {"bet":100}, lambda ok,d: got.append(("slots",ok,d.get("reels") if ok else d)), once=True); pump(900); print(got[-1], "coins", ec.coins)
ec.call("rb_slots", {"bet":5}, lambda ok,d: got.append(("bad bet",ok,d)), once=True); pump(900); print(got[-1])
ec.refresh(); pump(900); print("after refresh: coins", ec.coins, "items", len(ec.items), "seen", sorted(ec.seen))
print("catalog cached on disk:", os.path.exists(str(ec._catalog_path())))
