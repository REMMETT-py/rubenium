import os, sys, time, json, shutil
os.environ["QT_QPA_PLATFORM"]="offscreen"
mode=sys.argv[1]
H="/tmp/h3"; shutil.rmtree(H,ignore_errors=True); os.makedirs(H+"/Documents/Rubenium"); os.environ["HOME"]=H
cfg={"schema":3,"usage_s":7200.0,"theme":"grid"}
if mode=="open": cfg.update(card_open=True, seen_version="4.0.0", welcome=False, tabs_off={"perf":True}, page="perf", ball_size=130)
if mode=="news": cfg.update(welcome=True)
json.dump(cfg,open(H+"/Documents/Rubenium/settings.json","w"))
sys.path.insert(0,"/home/claude/release"); sys.argv=["/home/claude/release/Rubenium.py"]
from PyQt6.QtWidgets import QApplication
import Rubenium as A
q=QApplication([]); a=A.App(q)
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.005)
pump(1200)
if mode=="news":
    print("welcome up:", a.welcome is not None, "ball hidden:", not a.window.ball.isVisible()); a.window.toggle(); pump(200); print("toggle ignored:", not a.window.expanded)
    a.welcome.close(); pump(100); print("cannot close:", a.welcome.isVisible()); a.welcome.launch(); pump(3200)
print(mode, "expanded:", a.window.expanded, "page:", a.window.current, "theme:", a.theme()["id"], "BD:", A.BD(), "tabs:", len(a.window.tab_keys()))
a._on_state(a.state); print("usage timer alive:", a._usage.isActive(), "rocket timer:", a.rocket._timer.isActive())
a.shutdown(); print(json.load(open(H+"/Documents/Rubenium/settings.json")).get("seen_version"))
