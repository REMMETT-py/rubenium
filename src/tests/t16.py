import os, sys, time, shutil, json
os.environ["QT_QPA_PLATFORM"]="offscreen"
H="/tmp/h8"; shutil.rmtree(H,ignore_errors=True)
for d in (H+"/.rubenium/Rubenium",H+"/Documents/Rubenium"): os.makedirs(d); json.dump({"schema":3,"welcome":False,"seen_version":"2026.11.14.5","usage_s":3600*200.0,"ball_style":"shine"},open(d+"/settings.json","w"))
os.environ["HOME"]=H
sys.path.insert(0,"/home/claude/release"); sys.argv=["x"]
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPoint, QPointF, Qt, QEvent
from PyQt6.QtGui import QMouseEvent, QIcon, QCursor
import Rubenium as A
q=QApplication([]); q.setStyleSheet(A.APP_QSS); a=A.App(q); w=a.window; b=w.ball
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.004)
out="/tmp/shots/"
def ev(wd,t,gp): return QMouseEvent(t,QPointF(wd.mapFromGlobal(gp)),QPointF(gp),Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
P,M,R=QEvent.Type.MouseButtonPress,QEvent.Type.MouseMove,QEvent.Type.MouseButtonRelease
pump(1200); print("old style falls back:", a.ball_style(), "hold default:", a.cfg["hold_open"], a.cfg["hold_ms"])
c=QPoint(b.center)
b.mousePressEvent(ev(b,P,c)); pump(150); b.mouseReleaseEvent(ev(b,R,c)); pump(600); print("quick click does not open:", not w.expanded)
b.mousePressEvent(ev(b,P,c)); pump(200); b.grab().save(out+"charge.png"); print("charging:", round(b.charge.level,2)); pump(350); print("held 0.55 s -> open:", w.expanded); pump(900)
b.mouseReleaseEvent(ev(b,R,c)); w.collapse(); pump(1200)
b.mousePressEvent(ev(b,P,c)); pump(100); b.mouseMoveEvent(ev(b,M,c+QPoint(40,30))); pump(600); b.mouseReleaseEvent(ev(b,R,c+QPoint(40,30))); pump(500)
print("drag does not open, moved:", not w.expanded, b.center!=c)
a.cfg["hold_open"]=False; c=QPoint(b.center); b.mousePressEvent(ev(b,P,c)); pump(60); b.mouseReleaseEvent(ev(b,R,c)); pump(900); print("hold off -> click opens:", w.expanded)
a.cfg["hold_open"]=True
# card hold-to-drag
body=w.body; g=body.mapToGlobal(QPoint(150,12)); pos0=w.pos()
body.mousePressEvent(ev(body,P,g)); pump(60); body.mouseMoveEvent(ev(body,M,g+QPoint(50,0))); body.mouseReleaseEvent(ev(body,R,g+QPoint(50,0))); pump(400)
print("quick flick does not move card:", w.pos()==pos0)
A.QGuiApplication.mouseButtons=staticmethod(lambda: Qt.MouseButton.LeftButton); w._follow_test=True; body.mousePressEvent(ev(body,P,g)); pump(300); print("armed:", body._armed)
start=QCursor.pos(); body.mouseMoveEvent(ev(body,M,start+QPoint(60,40))); pump(50); A.QCursor.setPos(start+QPoint(60,40)); pump(120); body.mouseReleaseEvent(ev(body,R,start+QPoint(60,40))); w._follow_test=False; pump(500)
print("held then moved -> card moved by:", w.pos()-pos0)
# apps grid
a._apps=[{"name":n,"path":"x","exe":n.lower()+".exe","icon":QIcon()} for n in ["Alpha","Bravo","Charlie","Delta","Echo","Foxtrot","Golf"]]
run={"echo.exe"}; A.running_names=lambda: set(run)
w.goto("launch"); pump(900); pg=w.page(); print("order:", [pg.tiles[i].app["name"] for i in pg.grid._order][:3])
run.add("golf.exe"); pg._poll(); pump(200); w.grab().save(out+"apps_mid.png"); pump(600); print("after Golf opens:", [pg.tiles[i].app["name"] for i in pg.grid._order][:3], pg.tiles[6].pos())
run.discard("echo.exe"); pg._poll(); pump(700); print("after Echo closes:", [pg.tiles[i].app["name"] for i in pg.grid._order][:3]); w.grab().save(out+"apps.png")
a.set_tab("new",True)
for k in ["themes","new","settings","rl"]:
    w.goto(k); pump(900); w.grab().save(out+f"f_{k}.png"); sa=w.pages[k][0]
    if k=="rl": sa._target=sa.max_offset()*0.33; sa._pos.jump(sa._target); pump(300); w.grab().save(out+"f_rl1.png")
print("tabs:", w.tab_keys())
a.set_language("fr"); pump(600); w.goto("new"); pump(900); w.grab().save(out+"f_new_fr.png"); w.goto("settings"); pump(900); w.grab().save(out+"f_set_fr.png")
# updater compare
U=A.Updater("2026.11.14.3"); v=A.version_tuple
print("newer tag:", v("2026.11.15")>v(U.current), "same:", v("2026.11.14.3")>v(U.current), "| 1.1.0 app reads title:", v("2026.11.14.3")>v("1.1.0"))
import re; print(re.search(r"Rubenium\s+v?(\d+(?:\.\d+)*)","2026.11.14.3 - Rubenium 1.0").group(1), re.search(r"\d+(?:\.\d+)+","2026.11.14.3 - Rubenium 1.0").group(0))
a.shutdown()
