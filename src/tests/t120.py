import os, sys, time, shutil, json, subprocess
sys.path.insert(0,"/tmp"); import bridge; bridge.serve()
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["RUBENIUM_API"]="http://127.0.0.1:8766"; os.environ["NO_PROXY"]="127.0.0.1"
for k in ("HTTP_PROXY","http_proxy"): os.environ.pop(k,None)
L=os.environ.get("L","en"); H="/tmp/h120"; shutil.rmtree(H,ignore_errors=True)
for d in (H+"/.rubenium/Rubenium",H+"/Documents/Rubenium"):
    os.makedirs(d); json.dump({"schema":3,"welcome":False,"seen_version":"x","lang":L,"casino_warned":True},open(d+"/settings.json","w"))
os.environ["HOME"]=H
M="00000000-0000-0000-0000-000000000003"; R="00000000-0000-0000-0000-000000000001"
subprocess.run(["psql","-h","/tmp","-p","5544","-U","postgres","-q","-c",f"update profiles set coins=3000, keys=4, minutes=95 where username='Ruben'; delete from rb_quest_claims; delete from rb_friends; insert into rb_friends(a,b,ok) values ('{R}','{M}',true); delete from rb_items where owner='{M}'; insert into rb_items(owner,item,origin) values ('{M}','badge:crown:gold','t'),('{M}','badge:phoenix:prime','t'),('{M}','badge:star:lava','t'),('{M}','badge:heart:grey','t'),('{M}','badge:skull:white','t'); update profiles set equip='{{\"badge1\":\"badge:phoenix:prime\",\"badge2\":\"badge:crown:gold\"}}', minutes=4321, last_beat=now() where username='Max';"])
sys.path.insert(0,"/home/claude/release"); sys.argv=["x"]
from PyQt6.QtWidgets import QApplication
import Rubenium as A
A.Online._load = lambda self: self.__dict__.update(s={"refresh_token":"R-ruben","username":"Ruben","access_token":"A-ruben","expires_at":9e12}, minutes=95)
q=QApplication([]); q.setStyleSheet(A.APP_QSS); a=A.App(q); w=a.window; ec=a.econ; O="/tmp/shots12/"; os.makedirs(O,exist_ok=True)
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.003)
pump(3000); w.expand(); pump(900); w.goto("games"); pump(1200); w.page()._show_quests(True); pump(2000); w.grab().save(O+f"quests_{L}.png")
rows=w.page().findChildren(A.QuestRow); print("quests:", [(r.q["quest"], r.q["progress"], r.q["goal"], r.q["claimed"]) for r in rows])
c0=ec.coins; ready=[r.q["quest"] for r in rows if r.q["progress"]>=r.q["goal"] and not r.q["claimed"]]
if ready: w.page().claim(ready[0]); pump(1500); print("claimed", ready[0], "+", ec.coins-c0)
w.page().claim("w_rounds"); pump(900)
w.grab().save(O+f"quests2_{L}.png")
w.goto("friends"); pump(1500); w.page().open_profile("Max"); pump(2200); w.grab().save(O+f"profile_{L}.png"); print("profile badges:", len(a.friends_data["profile"]["badges"]), "online", a.friends_data["profile"]["online"])
w.page()._refresh_all(); pump(1800); print("refreshed profile:", a.friends_data is not None)
a.shutdown()
