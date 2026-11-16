import os, sys, time, shutil
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["RUBENIUM_DEMO"]="1"
H="/tmp/rbhomeX"; shutil.rmtree(H, ignore_errors=True); os.makedirs(H+"/Documents"); os.environ["HOME"]=H
sys.path.insert(0,"/home/claude/release"); sys.argv=["/home/claude/release/Rubenium.py"]
from PyQt6.QtWidgets import QApplication
import Rubenium as A
q=QApplication([]); a=A.App(q); w=a.window
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.005)
pump(500); w.expand(); pump(900); w.goto("settings"); pump(600); w.grab().save("/tmp/set1.png")
a.updater.latest={"version":"2.3.0","page":"x","assets":{}}; a._update_found(a.updater.latest); pump(800)
print("prompt:", w.confirm_w.isVisible(), w.confirm_w._text, "|", w.confirm_w._yes._text); w.grab().save("/tmp/set2.png")
a.set_language("fr"); pump(600); w.goto("settings"); pump(600); w.grab().save("/tmp/set3.png"); a.shutdown()
