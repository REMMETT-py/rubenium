import os, sys, time
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["RUBENIUM_DEMO"]="1"; os.environ["HOME"]="/tmp/rbhomeD"
os.makedirs("/tmp/rbhomeD/Documents",exist_ok=True); sys.path.insert(0,"/home/claude")
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPoint
import Rubenium as A
q=QApplication([]); a=A.App(q); w=a.window
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.005)
pump(500); w.expand(); pump(900)
print("screen", q.primaryScreen().availableGeometry())
w.begin_drag(QPoint(0,0)); w.drag_to(QPoint(-300,40)); w.end_drag(); pump(400)
p0=w.card_global().topLeft(); print("before", p0)
for sc in (110,150,70,100):
    a.set_scale(sc); pump(900); print(sc, w.card_global().topLeft())
w.collapse(); pump(1300); w.expand(); pump(1300); print("reopen", w.card_global().topLeft())
a.shutdown()
