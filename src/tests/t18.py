import os, sys, time, shutil, json
os.environ["QT_QPA_PLATFORM"]="offscreen"
H="/tmp/h10"; shutil.rmtree(H,ignore_errors=True)
for d in (H+"/.rubenium/Rubenium",H+"/Documents/Rubenium"): os.makedirs(d); json.dump({"schema":3,"welcome":False,"seen_version":"2026.11.14.4","usage_s":3600*7.0,"lang":"fr","theme":"grid","accent2_on":True,"ring_style":"line"},open(d+"/settings.json","w"))
os.environ["HOME"]=H
sys.path.insert(0,"/home/claude/release"); sys.argv=["x"]
from PyQt6.QtWidgets import QApplication
import Rubenium as A
q=QApplication([]); q.setStyleSheet(A.APP_QSS); a=A.App(q); w=a.window
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.004)
pump(1000); print("old theme id ->", a.theme()["id"], "| ring:", a.ring_style(), "| accent2 before 24 h:", A.ui.accent2)
w.expand(); pump(900); w.goto("themes"); pump(1000); w.grab().save("/tmp/shots/u0.png")
sa=w.pages["themes"][0]; sa._target=sa.max_offset()*0.45; sa._pos.jump(sa._target); pump(300); w.grab().save("/tmp/shots/u1.png")
w.goto("settings"); pump(900); w.grab().save("/tmp/shots/u2.png")
a.shutdown()
