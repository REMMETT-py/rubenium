import os, sys, time, json, re, shutil, hashlib
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["RUBENIUM_DEMO"]="1"
H="/tmp/rbhomeV"; shutil.rmtree(H, ignore_errors=True); os.makedirs(H+"/Documents/Rubenium/rocket_league/originals"); os.environ["HOME"]=H
sys.path.insert(0,"/home/claude/release"); sys.argv=["/home/claude/release/Rubenium.py"]
def mk(root, tag):
    shutil.rmtree(root, ignore_errors=True)
    cook=os.path.join(root,"TAGame","CookedPCConsole"); os.makedirs(cook); os.makedirs(os.path.join(root,"Binaries","Win64"))
    open(os.path.join(root,"Binaries","Win64","RocketLeague.exe"),"wb").write(b"v1")
    for f in ["explosion_Rekt_SF.upk","Body_Octane_SF.upk","Boost_Bubble_SF.upk","explosion_splash_SF.upk","skin_grain_flames_SF.upk","skin_grain_stripes_SF.upk","skin_grain_racelines_SF.upk","Skin_Octane_Lightning_SF.upk","Skin_Octane_Stripes_SF.upk","WHEEL_Caliber_SF.upk","WHEEL_Hydra_SF.upk","Boost_Standard_SF.upk","playerBanner_RLShield_SF.upk","explosion_Dragon_SF.upk","Boost_Flamethrower_SF.upk","paintfinish_anodized_SF.upk","playerBanner_DiamondTile_SF.upk"]: open(os.path.join(cook,f),"wb").write(b"\xc1\x83\x2a\x9e"+(tag+f).encode()*700)
    return cook
EPIC="/tmp/RL/Epic Games/rocketleague"; STEAM="/tmp/RL/SteamLibrary/steamapps/common/rocketleague"
ce=mk(EPIC,"EPIC"); cs=mk(STEAM,"STEAM")
# a 2.0 settings file with the old single install, swap on, and a flat backup
old_orig=hashlib.sha256(b"\xc1\x83\x2a\x9e"+("EPICexplosion_Rekt_SF.upk").encode()*700).hexdigest()
shutil.copy(os.path.join(ce,"explosion_Rekt_SF.upk"), H+"/Documents/Rubenium/rocket_league/originals/explosion_Rekt_SF.upk")
shutil.copy("/home/claude/release/swaps/atomizer_gentlemates/explosion_Rekt_SF.upk", os.path.join(ce,"explosion_Rekt_SF.upk"))
json.dump({"schema":3,"welcome":False,"rl":{"auto_fix":True,"folder":EPIC,"app":"Sugar","active":{"goal":"atomizer_gentlemates"},"orig":{"explosion_Rekt_SF.upk":old_orig},"stamp":"2:0"}}, open(H+"/Documents/Rubenium/settings.json","w"))
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtCore import QPoint
import Rubenium as A
A.Online._load = lambda self: self.__dict__.update(s={"refresh_token":"x","username":"Test","access_token":"x","expires_at":9e12}, minutes=0)
FOUND={"epic":{"folder":EPIC,"app":"Sugar"},"steam":{"folder":STEAM,"app":""}}
A.find_installs=lambda: {k:dict(v) for k,v in FOUND.items()}
src=open('/home/claude/release/Rubenium.py').read(); keys=set()
for m in re.finditer(r'\btr\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+)', src): keys.add(eval("("+m.group(1)+")"))
extra=[n for _,_,n in A.TABS]+[n for _,n in A.RL_CATS]+[t["name"] for t in A.THEMES]
print("missing FR:", sorted(k for k in list(keys)+extra if k not in A.FR))
q=QApplication([]); q.setStyleSheet(A.APP_QSS)
a=A.App(q); w=a.window; eng=a.rocket
RUN={"epic":False,"steam":False}
eng.running=lambda plat="": RUN.get(plat or eng.platform(), False)
launched=[]; eng.launch=lambda plat="": launched.append(plat) or True
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.005)
def wait_done():
    t=time.time()
    while (eng.working or w.busy_w.isVisible()) and time.time()-t<10: pump(30)
    pump(100)
h=lambda p: hashlib.sha256(open(p,"rb").read()).hexdigest()
CUST={it["id"]:h(f"/home/claude/release/swaps/{it['id']}/{it['file']}") for it in A.RL_ITEMS if os.path.exists(f"/home/claude/release/swaps/{it['id']}/{it['file']}")}
print("1 migrated:", a.cfg["rl"]["folder"]=="", eng.platform(), eng.active("epic"), os.path.isfile(H+"/Documents/Rubenium/rocket_league/originals/epic/explosion_Rekt_SF.upk"))
print("2 available:", eng.available(), "epic actual:", eng.actual("epic"), "steam actual:", eng.actual("steam"))
out="/tmp/sV"; os.makedirs(out,exist_ok=True)
class FC:
    p=QPoint(400,400)
    @staticmethod
    def pos(): return FC.p
A.QCursor=FC
pump(500); w.expand(); pump(900); FC.p=w.card_global().center()
w.goto("rl"); pump(700); w.grab().save(out+"/both_epic.png")
pg=w.page(); pg._toggle(A.RL_BY_ID["octane_fennec"]); wait_done()
print("3 epic body on:", h(os.path.join(ce,"Body_Octane_SF.upk"))==CUST["octane_fennec"], "steam untouched:", eng.actual("steam"))
w.page().seg.changed.emit(1); pump(700); pg=w.page(); print("4 now steam:", eng.platform(), [t.on for t in pg.tiles])
pg._toggle(A.RL_BY_ID["bubbles_alpha"]); wait_done()
print("5 steam boost:", eng.actual("steam"), "epic:", eng.actual("epic"), os.path.isfile(H+"/Documents/Rubenium/rocket_league/originals/steam/Boost_Bubble_SF.upk"))
w.grab().save(out+"/steam.png")
# running: changes are collected
RUN["steam"]=True
pg=w.page(); pg._toggle(A.RL_BY_ID["bubbles_dev"]); pg._toggle(A.RL_BY_ID["octane_fennec"]); pump(300)
print("6 pending:", pg.pending, "bar:", w.confirm_w.isVisible(), w.confirm_w._text, "| files unchanged:", eng.actual("steam"))
w.grab().save(out+"/pending.png")
w.goto("home"); pump(600); print("7 left tab -> bar hidden:", not w.confirm_w.isVisible(), "pending:", w.pages["rl"][1].pending)
w.goto("rl"); pump(600); pg=w.page(); print("   tiles back to real:", [(t.item["id"],t.on,t.pending) for t in pg.tiles if t.on or t.pending])
pg._toggle(A.RL_BY_ID["bubbles_dev"]); pump(200); pg._toggle(A.RL_BY_ID["bubbles_dev"]); pump(200)
print("8 toggled back -> no bar:", not w.confirm_w.isVisible(), pg.pending)
pg._toggle(A.RL_BY_ID["bubbles_dev"]); pump(200)
RUN_after=[]
def fake_close(plat): RUN["steam"]=False
eng._close_game=fake_close
w.confirm_w._accept(); pump(200); print("9 reload busy:", w.busy_w.isVisible()); wait_done()
print("   applied:", eng.actual("steam"), "launched:", launched)
# epic only -> steam locked
FOUND.pop("steam"); eng.detect(); w.reload_page(); pump(700); pg=w.page()
print("10 only epic:", eng.available(), eng.platform(), "faint:", pg.seg.faint)
pg.seg.changed.emit(1); pump(500); print("   snap back:", eng.platform(), pg.seg.index())
w.grab().save(out+"/epic_only.png")
# not detected
FOUND.clear(); eng.detect(); w.reload_page(); pump(700); pg=w.page()
print("11 none:", eng.available(), eng.platform(), "tiles enabled:", any(t.isEnabled() for t in pg.tiles))
w.grab().save(out+"/none.png")
FOUND.update({"epic":{"folder":EPIC,"app":"Sugar"},"steam":{"folder":STEAM,"app":""}}); pg._search(); pump(700); print("12 search:", eng.available(), eng.platform())
# epic off restores epic only
pg=w.page()
if eng.platform()!="epic": pg.seg.changed.emit(0); pump(600); pg=w.page()
pg._reset(); wait_done(); print("13 epic all off:", eng.actual("epic"), "epic body original:", h(os.path.join(ce,"Body_Octane_SF.upk"))==hashlib.sha256(b"\xc1\x83\x2a\x9e"+("EPICBody_Octane_SF.upk").encode()*700).hexdigest(), "steam kept:", eng.actual("steam"))
# 3.0: several swaps of one category, one per file
pg=w.page()
for i in ("splash_adidas","fennec_flames_likescraft","octane_lightning_ssg","fennec_nitty_gc"): w.page()._toggle(A.RL_BY_ID[i]); wait_done()
w.page()._toggle(A.RL_BY_ID["atomizer_gentlemates"]); wait_done()
print("14 many on:", sorted(eng.actual("epic").values()))
w.page()._toggle(A.RL_BY_ID["splash_supernova"]); wait_done()
print("15 same file swaps over:", eng.actual("epic").get("explosion_splash_sf.upk"), "| other goal kept:", eng.actual("epic").get("explosion_rekt_sf.upk"), "| file is supernova:", h(os.path.join(ce,"explosion_splash_SF.upk"))==CUST["splash_supernova"])
w.page()._toggle(A.RL_BY_ID["splash_supernova"]); wait_done()
print("16 off -> original back:", h(os.path.join(ce,"explosion_splash_SF.upk"))==hashlib.sha256(b"\xc1\x83\x2a\x9e"+("EPICexplosion_splash_SF.upk").encode()*700).hexdigest(), "others:", sorted(eng.actual("epic").values()))
print("17 no-file tile disabled:", [(t.item["id"],t.isEnabled()) for t in w.page().tiles if not t.ready])
# game update: exe changes + files restored by the launcher -> auto fix
open(os.path.join(EPIC,"Binaries","Win64","RocketLeague.exe"),"wb").write(b"v2-new")
for f in ("skin_grain_flames_SF.upk","Skin_Octane_Lightning_SF.upk"): open(os.path.join(ce,f),"wb").write(b"NEWGAME"+f.encode()*300); os.utime(os.path.join(ce,f),(time.time()-120,time.time()-120))
for it in A.RL_ITEMS:
    pth=os.path.join(ce,it["file"]); os.path.exists(pth) and os.utime(pth,(time.time()-120,time.time()-120))
A._hash_cache.clear(); print("18 after update state:", eng.check("epic")); eng.watch(); wait_done(); pump(300)
print("   auto fixed:", eng.check("epic"), sorted(eng.actual("epic").values()))
w.page()._reset() if w.current=="rl" else None; wait_done()
print("19 all off, new originals back:", eng.actual("epic"), open(os.path.join(ce,"skin_grain_flames_SF.upk"),"rb").read()[:7])
def tiles_fit():
    bad=[]
    for t in w.page().tiles:
        wd=t.width()-A.S(5)-(t.height()-3-A.S(10))-A.S(10)-A.S(34)-3
        if QFontMetrics(A.font(12.5,A.QFont.Weight.Bold)).horizontalAdvance("→ "+t.item["new"])>wd or QFontMetrics(A.font(10.5,A.QFont.Weight.DemiBold)).horizontalAdvance(t.item["old"])>wd: bad.append(t.item["id"])
    return bad
print("20 tile text cut:", tiles_fit())
# 1.1: an item the game has not downloaded (no file) -> the swap adds it, switching off removes it
assert not os.path.exists(os.path.join(ce,"skin_grain_block_SF.upk"))
w.page()._toggle(A.RL_BY_ID["fennec_ribbon_affluenter"]); wait_done()
added=os.path.join(ce,"skin_grain_block_SF.upk")
print("21 absent file added:", os.path.exists(added) and h(added)==CUST["fennec_ribbon_affluenter"], eng.check("epic"), eng._entry("epic")["orig"].get("skin_grain_block_SF.upk"))
w.page()._toggle(A.RL_BY_ID["fennec_ribbon_affluenter"]); wait_done()
print("22 switched off -> removed again:", not os.path.exists(added), eng.check("epic"))
# file in a sub-folder of CookedPCConsole
sub=os.path.join(ce,"Sub"); os.makedirs(sub,exist_ok=True); os.replace(os.path.join(ce,"WHEEL_Hydra_SF.upk"), os.path.join(sub,"WHEEL_Hydra_SF.upk"))
eng._index.clear(); w.page()._toggle(A.RL_BY_ID["stern_alpha"]); wait_done()
print("23 sub-folder file swapped in place:", h(os.path.join(sub,"WHEEL_Hydra_SF.upk"))==CUST["stern_alpha"], not os.path.exists(os.path.join(ce,"WHEEL_Hydra_SF.upk")))
w.page()._toggle(A.RL_BY_ID["stern_alpha"]); wait_done()
print("24 sub-folder original back:", h(os.path.join(sub,"WHEEL_Hydra_SF.upk"))!=CUST["stern_alpha"], eng.actual("epic"))
print("25 s21 waits for its file:", [(t.item["id"],t.isEnabled()) for t in w.page().tiles if t.item["id"].startswith("banner")])
# audits
def audit(tag):
    bad=[]
    for k,(sa,page,hh) in w.pages.items():
        for lb in page.findChildren(A.Label):
            if lb._wrap_w==0 and lb.text() and lb.width()>0 and lb.text_width()>lb.width()+1: bad.append((k,lb.text()))
        for b in page.findChildren(A.Button):
            if b.width()>0 and b.isVisible() and QFontMetrics(b._font).horizontalAdvance(b._text)+(A.S(20) if b._icon else 0) > b.width()-A.S(12): bad.append((k,"BTN",b._text))
        for sg in page.findChildren(A.Segmented):
            cell=sg.width()/len(sg._labels)-A.S(6)
            for t in sg._labels:
                if QFontMetrics(sg._font).horizontalAdvance(t)>cell: bad.append((k,"SEG",t))
    cw=w.confirm_w
    if cw.isVisible():
        room=cw._yes.x()-A.S(20)
        if QFontMetrics(A.font(12, A.QFont.Weight.DemiBold)).horizontalAdvance(cw._text)>room: bad.append(("bar",cw._text))
    print(tag,"truncated:",bad)
for lang in ("fr","en"):
    a.set_language(lang); pump(500); FC.p=w.card_global().center()
    for k,_,_ in A.TABS:
        w.goto(k); pump(1000 if k=="perf" else 500)
        if lang=="fr" and k in ("rl","themes","timer","perf"): w.grab().save(f"{out}/fr_{k}.png")
    audit(lang)
    w.goto("rl"); pump(500); RUN["epic"]=True; w.page()._toggle(A.RL_BY_ID["octane_fennec"]); pump(300); audit(lang+" bar"); w.grab().save(f"{out}/bar_{lang}.png"); w.page()._cancel(); RUN["epic"]=False; pump(200)
w.collapse(); pump(1300); a.shutdown()
c=json.load(open(H+"/Documents/Rubenium/settings.json")); print("ok", c["rl"]["platform"], {k:v["active"] for k,v in c["rl"]["installs"].items()})
