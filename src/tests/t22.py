import os, sys, time, shutil, json
os.environ["QT_QPA_PLATFORM"]="offscreen"
H="/tmp/h14"; shutil.rmtree(H,ignore_errors=True)
for d in (H+"/.rubenium/Rubenium",H+"/Documents/Rubenium"): os.makedirs(d); json.dump({"schema":3,"welcome":False,"seen_version":"2026.11.15.1","usage_s":3600*8.0,"lang":"fr"},open(d+"/settings.json","w"))
os.environ["HOME"]=H
sys.path.insert(0,"/home/claude/release"); sys.argv=["x"]
from PyQt6.QtWidgets import QApplication
import Rubenium as A
q=QApplication([]); q.setStyleSheet(A.APP_QSS); a=A.App(q); w=a.window
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.003)
pump(900); w.expand(); pump(900)
for k in ("themes","crosshair","perf","home","new","settings"):
    w.goto(k); pump(1300); w.grab().save(f"/tmp/shots/s_{k}.png")
    if k=="themes":
        from PyQt6.QtWidgets import QScrollArea; sa=w.page().findChildren(QScrollArea)
        for i,s in enumerate(sa[:1]):
            for j,f in enumerate((0.33,0.66,1.0)):
                s.verticalScrollBar().setValue(int(s.verticalScrollBar().maximum()*f)); pump(500); w.grab().save(f"/tmp/shots/s_themes{j+1}.png")
a.shutdown()
