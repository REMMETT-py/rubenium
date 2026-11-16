import os, sys, time, shutil, json
os.environ["QT_QPA_PLATFORM"]="offscreen"
H="/tmp/h7"; shutil.rmtree(H,ignore_errors=True)
for d in (H+"/.rubenium/Rubenium",H+"/Documents/Rubenium"): os.makedirs(d); json.dump({"schema":3,"welcome":True,"seen_version":"2026.11.14.5","usage_s":3600*5.0},open(d+"/settings.json","w"))
os.environ["HOME"]=H
sys.path.insert(0,"/home/claude/release"); sys.argv=["x"]
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPoint, QPointF, Qt, QEvent
from PyQt6.QtGui import QMouseEvent, QKeyEvent
import Rubenium as A
q=QApplication([]); q.setStyleSheet(A.APP_QSS); a=A.App(q); w=a.window
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.005)
out="/tmp/shots/"
pump(900); wel=a.welcome
b=wel._button().center()
ev=lambda t,pos: QMouseEvent(t,QPointF(pos),QPointF(wel.mapToGlobal(pos.toPoint())),Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
wel.mousePressEvent(ev(QEvent.Type.MouseButtonPress,b)); pump(2000)
print("after 2 s, bar:", wel.code_in.target)
pump(3300); print("after 5.3 s, bar:", wel.code_in.target, "focusable:", not bool(wel.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus))
wel.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease,b)); pump(300); print("release did not launch:", wel.phase)
for ch in "0101": wel.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_0, Qt.KeyboardModifier.NoModifier, ch))
pump(200); wel.grab().save(out+"code1.png")
for ch in "1111": wel.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_0, Qt.KeyboardModifier.NoModifier, ch))
pump(150); print("wrong code -> cleared:", wel.code=="", "unlock:", a.cfg["unlock_all"]); pump(500)
for ch in "01092008": wel.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_0, Qt.KeyboardModifier.NoModifier, ch))
pump(200); wel.grab().save(out+"code2.png"); print("right code -> unlock (this session):", a.unlocked, "saved:", a.cfg["unlock_all"])
pump(3500); print("launched:", a.welcome is None, w.ball.isVisible())
# themes all unlocked
w.expand(); pump(900); w.goto("themes"); pump(900)
sa=w.pages["themes"][0]
for n,f in enumerate([0,0.5,1.0]):
    sa._target=sa.max_offset()*f; sa._pos.jump(sa._target); pump(300); w.grab().save(out+f"th{n}.png")
print("theme mythic ok:", a.unlock_hours()>1e6)
a.cfg["ball_style"]="shine"; a.cfg["ring_style"]="comet"
# display
w.goto("display"); pump(800); pg=w.page(); print("display mode:", pg.seg.index(), a.display.manual)
w.grab().save(out+"disp0.png")
pg._set("brightness",20); pump(400); print("slider on Default ->", a.display.manual, pg.seg.index(), a.cfg["display"]["A"]["brightness"])
w.grab().save(out+"disp1.png")
pg.seg.changed.emit(0); pg.seg.set_index(0); pump(300); print("back to Default:", a.display.manual, "custom kept:", a.cfg["display"]["A"]["brightness"])
# ball: stays where the card closes, snapping
w.collapse(); pump(1200)
wa=A.work_area(w.ball.center); start=QPoint(wa.center().x()-200, wa.center().y()+100)
w.ball.set_center(start); w.save_position(); pump(100)
w.expand(); pump(900); w.collapse(); pump(1300)
print("ball back where it was:", w.ball.center==start, w.ball.center, start)
w.expand(); pump(900); A.QGuiApplication.mouseButtons=staticmethod(lambda: Qt.MouseButton.LeftButton); A.QCursor.setPos(QPoint(500,500)); w._follow_test=True; w.begin_drag(QPoint(500,500)); A.QCursor.setPos(QPoint(560,470)); pump(200); print("cursor test pos:", A.QCursor.pos()); w.end_drag(); w._follow_test=False; pump(400); w.collapse(); pump(1300)
c=w.card_pos; print("card moved -> ball at card corner:", abs(w.ball.center.y()-(c.y()+A.BD()//2))<=1, w._closed_at_card)
w.expand(); pump(900); print("reopens at the moved card:", w.card_pos==c); w.collapse(); pump(1300)
pts=w.ball.snap_points(wa); near=pts[1]+QPoint(-30,25)
w.ball.center=QPoint(near); w.ball._press_pos=QPoint(0,0); w.ball._moved=True
w.ball.mouseReleaseEvent(None); pump(700); print("dropped near top-right -> snapped:", w.ball.center==pts[1], "top spot clear of title bars:", pts[1].y()-wa.top())
far=QPoint(wa.center().x()+137, wa.center().y()-91); w.ball.center=QPoint(far); w.ball._press_pos=QPoint(0,0); w.ball._moved=True
w.ball.mouseReleaseEvent(None); pump(500); print("dropped elsewhere -> stays:", w.ball.center==far)
w.ball.grab().save(out+"ball_shine.png")
w.goto("rl"); pump(1200); sa=w.pages["rl"][0]; sa._target=sa.max_offset()*0.75; sa._pos.jump(sa._target); pump(300); w.grab().save(out+"rl_ban.png")
w.goto("perf"); pump(1500); print("perf loaded:", "perf" in w.pages); w.goto("home"); pump(900); print("perf unloaded after leaving:", "perf" not in w.pages)
a.set_language("fr"); pump(500); w.goto("display"); pump(800); w.grab().save(out+"disp_fr.png")
a.shutdown()
