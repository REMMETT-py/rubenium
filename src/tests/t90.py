import os, sys, time, shutil, json
sys.path.insert(0,"/tmp"); import mock; mock.serve()
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["RUBENIUM_API"]="http://127.0.0.1:8765"; os.environ["NO_PROXY"]="127.0.0.1"
for k in ("HTTP_PROXY","http_proxy"): os.environ.pop(k,None)
H="/tmp/h90"; shutil.rmtree(H,ignore_errors=True)
for d in (H+"/.rubenium/Rubenium",H+"/Documents/Rubenium"):
    os.makedirs(d); json.dump({"schema":3,"welcome":True,"seen_version":"2026.11.15.8","lang":"en"},open(d+"/settings.json","w"))
os.environ["HOME"]=H; sys.path.insert(0,"/home/claude/release"); sys.argv=["x"]
from PyQt6.QtWidgets import QApplication
import Rubenium as A
mock.USERS["ruben@users.rubenium.app"]={"pw":"Secret-pass9","name":"Ruben"}
LOGGED=os.environ.get("IN","1")=="1"
if LOGGED: A.Online._load = lambda self: self.__dict__.update(s={"refresh_token":"R-ruben@users.rubenium.app","username":"Ruben","access_token":"A-ruben@users.rubenium.app","expires_at":9e12}, minutes=0)
A.Welcome.COUNT_MS=2500
q=QApplication([]); q.setStyleSheet(A.APP_QSS); a=A.App(q); O="/tmp/shots9/"; os.makedirs(O,exist_ok=True)
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.003)
pump(1800); wl=a.welcome
if LOGGED:
    pump(900); print("counting:", round(wl.count.level,2)); wl.grab().save(O+"count.png")
    pump(2200); print("launched by itself:", wl.phase != "card"); pump(3000); print("done:", a.welcome is None)
else:
    print("logged out: no countdown", wl.count.level, "| form:", wl.panel.isVisible()); pump(3000); print("still waiting:", wl.phase=="card")
    P=wl.panel; P.user.setText("Ruben"); P.pw.setText("Secret-pass9"); P._submit(); pump(1200); print("logged in, counting:", wl.count.level>0, wl.phase)
    wl.grab().save(O+"after_login.png"); wl.ctx.online.log_out(); pump(300); print("log out stops it:", wl.count.level, wl.phase); 
a.shutdown()
