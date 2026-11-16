import os, sys, time, shutil, json
os.environ["QT_QPA_PLATFORM"]="offscreen"
H="/tmp/h11"; shutil.rmtree(H,ignore_errors=True)
for d in (H+"/.rubenium/Rubenium",H+"/Documents/Rubenium"): os.makedirs(d); json.dump({"schema":3,"welcome":False,"seen_version":"2026.11.14.5","usage_s":3600*5.0,"unlock_all":True,"theme":"legend","ball_style":"gold","ring_style":"gold","hold_open":False},open(d+"/settings.json","w"))
os.environ["HOME"]=H
sys.path.insert(0,"/home/claude/release"); sys.argv=["x"]
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPoint, QPointF, Qt, QEvent
from PyQt6.QtGui import QMouseEvent
import Rubenium as A
q=QApplication([]); q.setStyleSheet(A.APP_QSS); a=A.App(q); w=a.window; b=w.ball
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.003)
pump(800)
print("code unlock not kept:", a.unlocked is False, a.cfg["unlock_all"] is False, "| reset to earned:", a.cfg["theme"], a.cfg["ball_style"], a.cfg["ring_style"])
wa=A.work_area(b.center)
# 1. ball dragged into top-right corner
b.center=QPoint(wa.right()-10, wa.top()+5); b.clamp(); print("drag into corner -> pushed below:", b.center.y()-wa.top(), ">= 52:", b.center.y()-A.BD()//2-wa.top()>=52)
b.center=QPoint(wa.right()-260, wa.top()+5); b.clamp(); print("top edge left of the zone allowed:", b.center.y()-wa.top() < 52)
b.glide_to(QPoint(wa.right()-30, wa.top()+30)); pump(700); print("glide target kept clear:", b.center.y()-A.BD()//2-wa.top()>=52)
# 2. card moved to top-right, collapse -> ball below zone
b.set_center(QPoint(wa.center())); w.save_position(); w.expand(); pump(900)
c=w._card_rect(); dx=(wa.right()-8) - w.mapToGlobal(c.topRight().toPoint()).x(); dy=(wa.top()+8)-w.mapToGlobal(c.topLeft().toPoint()).y()
w.move(w.pos()+QPoint(dx,dy)); w._drag_origin=w.pos(); w._drag_start=QPoint(0,0); w._follow_test=True
w._drag_origin=None; w._place(QRect:=None, None) if False else None
from PyQt6.QtCore import QRect
home=w.card_global().topLeft(); w._place(QRect(home.x(),home.y(),A.BD(),A.BD()),home); w._layout_body(); pump(200)
w.collapse(); pump(1300); print("card at top-right, closed -> ball clear of the zone:", b.center.y()-A.BD()//2-wa.top()>=52, b.center)
# 3. drag follow: fake mouse
class FakeCursor:
    p=QPoint(0,0)
    @staticmethod
    def pos(): return QPoint(FakeCursor.p)
A.QCursor=FakeCursor
w.expand(); pump(900)
start=w.pos(); press=w.body.mapToGlobal(QPoint(150,14)); FakeCursor.p=QPoint(press)
w._follow_test=True
body=w.body; body._press=press; body._armed=False
# the mouse moves 160 px during the hold
FakeCursor.p=press+QPoint(-160,90)
A.QGuiApplication.mouseButtons=staticmethod(lambda: Qt.MouseButton.LeftButton)
body._arm(press); pump(20); print("arm: card starts catching up:", w.pos()!=start)
pump(150); want=start+QPoint(-160,90); print("caught up with the grab point:", w.pos()==want, w.pos()-start)
print("screen", wa, "card", w.card_global())
for k in range(12):                          # very fast moves, back and forth, inside the screen
    FakeCursor.p=press+QPoint(-160+(k%2)*220, 90-(k%3)*40); pump(9)
pump(140); tgt=w._drag_target(FakeCursor.p); print("after fast moves: at target:", w.pos()==tgt, "| grab point under mouse (unless clamped at an edge):", w.pos()-start, FakeCursor.p-press)
A.QGuiApplication.mouseButtons=staticmethod(lambda: Qt.MouseButton.NoButton); w._follow_test=False
pump(60); print("let go anywhere -> drag ended:", w._drag_origin is None, not body._armed)
a.shutdown()
