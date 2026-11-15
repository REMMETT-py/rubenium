import os, sys, time, shutil, json
sys.path.insert(0,"/tmp"); import mock; mock.serve()
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["RUBENIUM_API"]="http://127.0.0.1:8765"; os.environ["NO_PROXY"]="127.0.0.1"
for k in ("HTTP_PROXY","http_proxy"): os.environ.pop(k,None)
L=os.environ.get("L","en"); H="/tmp/h70"; shutil.rmtree(H,ignore_errors=True)
for d in (H+"/.rubenium/Rubenium",H+"/Documents/Rubenium"):
    os.makedirs(d); json.dump({"schema":3,"welcome":False,"seen_version":"2026.11.15.7","lang":L},open(d+"/settings.json","w"))
os.environ["HOME"]=H; sys.path.insert(0,"/home/claude/release"); sys.argv=["x"]
from PyQt6.QtWidgets import QApplication
import Rubenium as A
mock.USERS["ruben@users.rubenium.app"]={"pw":"x","name":"Ruben"}
A.Online._load = lambda self: self.__dict__.update(s={"refresh_token":"R-ruben@users.rubenium.app","username":"Ruben","access_token":"A-ruben@users.rubenium.app","expires_at":9e12}, minutes=0)
q=QApplication([]); q.setStyleSheet(A.APP_QSS); a=A.App(q); w=a.window; O="/tmp/shots8/"; os.makedirs(O,exist_ok=True)
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.003)
pump(900); w.expand(); pump(900); w.goto("friends"); pump(1500); w.grab().save(O+f"list_{L}.png")
pg=w.page(); print("rows:", [(r.info["username"], r.info["state"]) for r in pg.findChildren(A.FriendRow)])
pg._add(); pump(300); d=pg._dialog; d.edit.setText("Nobody"); d._go(); pump(600); print("add nobody:", d.note.text()); d.grab().save(O+f"add_{L}.png")
d.edit.setText("Zoe"); d._go(); pump(900); print("added:", any(f["username"]=="Zoe" for f in mock.FRIENDS))
pump(600); w.page().act("rb_friend_add","Max"); pump(600)
w.page().open_profile("Leo"); pump(1500); w.grab().save(O+f"profile_{L}.png"); print("profile loaded:", a.friends_data is not None and a.friends_data.get("history") is not None)
w.page().open_profile(None); pump(600); print("back to list:", a.friends_profile is None)
a.shutdown()
