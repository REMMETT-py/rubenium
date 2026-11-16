import os, sys, time, shutil, json
sys.path.insert(0,"/tmp"); import mock; mock.serve()
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["RUBENIUM_API"]="http://127.0.0.1:8765"
os.environ.pop("HTTP_PROXY",None); os.environ.pop("http_proxy",None); os.environ["NO_PROXY"]="127.0.0.1"
L=os.environ.get("L","en"); FRESH=os.environ.get("FRESH","1")=="1"
H="/tmp/h60"
if FRESH:
    shutil.rmtree(H,ignore_errors=True)
    for d in (H+"/.rubenium/Rubenium",H+"/Documents/Rubenium"):
        os.makedirs(d); json.dump({"schema":3,"welcome":True,"seen_version":"2026.11.15.5","lang":L,"glow_power":1,"corners":2},open(d+"/settings.json","w"))
else:
    mock.USERS["ruben@users.rubenium.app"]={"pw":"Secret-pass9","name":"Ruben"}
os.environ["HOME"]=H
sys.path.insert(0,"/home/claude/release"); sys.argv=["x"]
from PyQt6.QtWidgets import QApplication
import Rubenium as A
q=QApplication([]); q.setStyleSheet(A.APP_QSS); a=A.App(q); O="/tmp/shots7/"; os.makedirs(O,exist_ok=True)
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.003)
pump(1500); wl=a.welcome; on=a.online
print("locked look:", a.cfg["glow_power"], a.cfg["backdrop"], a.cfg["corners"])
if not FRESH:
    print("RESTART: logged in from saved session:", on.logged_in(), on.username(), "| welcome shown:", wl is not None, "| panel hidden:", wl is not None and not wl.panel.isVisible())
    wl.grab().save(O+f"in_{L}.png"); wl.launch(); pump(3500); print("launched:", a.welcome is None)
    on._tick(); pump(800); print("heartbeat minutes:", on.minutes)
    a.window.expand(); pump(900); a.window.grab().save(O+f"pill_{L}.png"); a.window.goto("settings"); pump(900)
    from PyQt6.QtWidgets import QScrollArea
    a.window.grab().save(O+f"settings_{L}.png")
    raw=open(H+"/.rubenium/Rubenium/session.dat","rb").read() if os.path.exists(H+"/.rubenium/Rubenium/session.dat") else b""
    on.log_out(); pump(300); print("after logout: logged in", on.logged_in(), "| file gone:", not os.path.exists(str(A._session_path())))
    a.shutdown(); sys.exit()
print("welcome shown:", wl is not None, "| logged in:", on.logged_in(), "| panel visible:", wl.panel.isVisible())
wl.launch(); pump(300); print("launch blocked while logged out:", wl.phase=="card")
wl.grab().save(O+f"login_{L}.png")
P=wl.panel; P.seg.set_index(1); P._mode(1); P.user.setText("ab"); pump(100); print("hint short:", P.hint.text())
P.user.setText("Ruben"); pump(900); print("hint free:", P.hint.text())
P.pw.setText("abc"); pump(50); print("hint pw:", P.hint.text()); P.pw.setText("Secret-pass9"); pump(50); print("hint pw:", P.hint.text())
wl.grab().save(O+f"create_{L}.png")
P._submit(); pump(900); print("signed up:", on.logged_in(), on.username(), "| panel hidden:", not P.isVisible())
wl.grab().save(O+f"loggedin_{L}.png")
on.log_out(); pump(200); wl.panel.sync(); P.seg.set_index(1); P._mode(1); P.user.setText("RUBEN"); pump(900); print("taken:", P.hint.text())
P.seg.set_index(0); P._mode(0); P.pw.setText("wrongpass1"); P._submit(); pump(700); print("wrong pw:", P.hint.text(), on.logged_in())
P.pw.setText("Secret-pass9"); P._submit(); pump(700); print("login ok:", on.logged_in(), on.username())
print("session file sealed (no plain token):", b"R-ruben" not in open(str(A._session_path()),"rb").read() or "base64 on linux")
a.shutdown()
