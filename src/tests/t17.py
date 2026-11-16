import os, sys, time, shutil, json, hashlib
os.environ["QT_QPA_PLATFORM"]="offscreen"
HRS=float(os.environ.get("HRS","300"))
H="/tmp/h9"; shutil.rmtree(H,ignore_errors=True)
for d in (H+"/.rubenium/Rubenium",H+"/Documents/Rubenium"): os.makedirs(d); json.dump({"schema":3,"welcome":False,"seen_version":"2026.11.14.4","usage_s":3600*HRS,"accent_from_art":False,"theme":os.environ.get("TH","legend"),"ring_style":"gold","ball_style":"gold","rl":{"auto_fix":True,"platform":"epic","installs":{"epic":{"folder":"/tmp/rl9/rocketleague","app":"Sugar","manual":True,"active":{"x":"banner_electric"},"orig":{},"stamp":""}}}},open(d+"/settings.json","w"))
os.environ["HOME"]=H
G="/tmp/rl9/rocketleague"; shutil.rmtree("/tmp/rl9",ignore_errors=True)
os.makedirs(G+"/TAGame/CookedPCConsole"); os.makedirs(G+"/Binaries/Win64/EasyAntiCheat"); open(G+"/Binaries/Win64/RocketLeague.exe","w").write("x")
open(G+"/Binaries/Win64/EasyAntiCheat/SplashScreen.png","wb").write(b"ORIGINAL SPLASH")
sys.path.insert(0,"/home/claude/release"); sys.argv=["/home/claude/release/Rubenium.py"]
from PyQt6.QtWidgets import QApplication
import Rubenium as A
A.IS_WIN_FAKE=True
q=QApplication([]); q.setStyleSheet(A.APP_QSS); a=A.App(q); w=a.window
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.004)
out="/tmp/shots/"
pump(1000)
# retired banner: game has the old electric file + a backup of the original
ck=G+"/TAGame/CookedPCConsole/playerBanner_RLShield_SF.upk"
shutil.copy("/tmp/ns2/Electric banner/playerBanner_RLShield_SF.upk", ck)
store=A._rl_store()/"originals"/"epic"; store.mkdir(parents=True,exist_ok=True); open(store/"playerBanner_RLShield_SF.upk","wb").write(b"REAL ORIGINAL BANNER")
eng=a.rocket; eng.found={"epic":{"folder":G,"app":"Sugar"}}; eng._detected=True
print("active after load (old id dropped):", eng.active("epic"), "retired present:", eng._retired_present("epic"))
eng.watch(); t=time.time()
while eng.working and time.time()-t<10: pump(100)
pump(300); print("original back:", open(ck,"rb").read()==b"REAL ORIGINAL BANNER", eng._retired_present("epic"))
# splash
sp=a.splash; tg=sp._find(); print("targets:", [t.replace(G,"") for t in tg], "source:", sp.source() is not None)
print("applied:", sp.apply(True,tg), A.file_hash(A.Path(tg[0]))==A.file_hash(sp.source()), "again:", sp.apply(True,tg))
open(tg[0],"wb").write(b"GAME UPDATE SPLASH"); A._hash_cache.clear(); print("after game update re-applied:", sp.apply(True,tg))
A._hash_cache.clear(); print("off -> restored:", sp.apply(False,tg), open(tg[0],"rb").read())
# visuals
w.expand(); pump(900)
for th in ["glow","stars","starfield","constellation","comets","aurora","nova","gilded","royal","legend"]:
    a.preview_theme(th); pump(350); w.grab().copy(0,0,430,170).save(out+f"t_{th}.png")
a.preview_theme(""); w.goto("themes"); pump(900); w.grab().save(out+"g_th0.png"); sa=w.pages["themes"][0]
sa._target=sa.max_offset()*0.42; sa._pos.jump(sa._target); pump(300); w.grab().save(out+"g_th1.png")
sa._target=sa.max_offset(); sa._pos.jump(sa._target); pump(300); w.grab().save(out+"g_th2.png")
pg=w.page(); pg._second("#FF4FD8"); pump(500); print("second colour on:", A.ui.accent2 is not None)
pg._music(True); pg.t_music.set_checked(True); sa._target=0; sa._pos.jump(0); pump(400); w.grab().save(out+"g_th_music.png"); print("music on -> accent2 off:", A.ui.accent2 is None)
pg._music(False); pump(200)
w.goto("settings"); pump(900); h1=w.pages["settings"][2]; w.page().findChildren(A.Toggle)[0].toggled_by_user.emit(False); a.cfg["hold_open"]=False; a.reload_page() if hasattr(a,"reload_page") else None; pump(900); print("settings shorter without hold time:", w.pages["settings"][2] < h1); w.grab().save(out+"g_set.png")
a.set_scale(120); pump(120); w.grab().save(out+"g_zoom.png"); print("zooming:", w.zoom.busy, round(w._zoom_from,3)); pump(600); print("zoom done:", not w.zoom.busy)
w.collapse(); pump(1300); w.ball.grab().save(out+"g_ball.png")
a.shutdown()
