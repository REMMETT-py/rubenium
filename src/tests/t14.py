import os, sys, time, shutil, json
os.environ["QT_QPA_PLATFORM"]="offscreen"
H="/tmp/h6"; shutil.rmtree(H,ignore_errors=True)
for d in (H+"/.rubenium/Rubenium",H+"/Documents/Rubenium"): os.makedirs(d); json.dump({"schema":3,"welcome":False,"seen_version":"1.0.0"},open(d+"/settings.json","w"))
os.environ["HOME"]=H
sys.path.insert(0,"/home/claude/release"); sys.argv=["x"]
from PyQt6.QtWidgets import QApplication
import Rubenium as A
q=QApplication([]); q.setStyleSheet(A.APP_QSS); a=A.App(q); w=a.window
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.005)
import subprocess; burn=subprocess.Popen([sys.executable,"-c","while True: pass"])
pump(500); w.expand(); pump(800); w.goto("perf"); pump(5000)
pg=w.page(); print("rows", pg.top_list.rows[:3], pg.top_me.text())
sa=w.pages["perf"][0]; sa._target=sa.max_offset()*0.45; sa._pos.jump(sa._target); pump(400); w.grab().save("/tmp/shots/perf_cpu.png")
pg.g_ram.clicked.emit(); pump(1500); print("ram", pg.top_list.rows[:3], pg.top_seg.index(), pg.top_me.text()); w.grab().save("/tmp/shots/perf_ram.png")
burn.kill()
a.set_language("fr"); pump(600); w.goto("settings"); pump(800)
sa=w.pages["settings"][0]; sa._target=sa.max_offset()*0.3; sa._pos.jump(sa._target); pump(400); w.grab().save("/tmp/shots/set_fr.png")
w.goto("perf"); pump(2500); sa=w.pages["perf"][0]; sa._target=sa.max_offset()*0.45; sa._pos.jump(sa._target); pump(400); w.grab().save("/tmp/shots/perf_fr.png")
a.shutdown()
