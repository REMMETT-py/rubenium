import os, sys, time, json, shutil, hashlib
os.environ["QT_QPA_PLATFORM"]="offscreen"
H="/tmp/h40"; shutil.rmtree(H, ignore_errors=True); os.makedirs(H+"/Documents/Rubenium"); os.environ["HOME"]=H
sys.path.insert(0,"/home/claude/release"); sys.argv=["/home/claude/release/Rubenium.py"]
ROOT="/tmp/RL40/rocketleague"; shutil.rmtree("/tmp/RL40", ignore_errors=True)
cook=os.path.join(ROOT,"TAGame","CookedPCConsole"); os.makedirs(cook); os.makedirs(os.path.join(ROOT,"Binaries","Win64"))
open(os.path.join(ROOT,"Binaries","Win64","RocketLeague.exe"),"wb").write(b"v1")
SW="/home/claude/release/swaps"; OR="/tmp/orig/x"
# a NEW user whose game already has: the Fennec body swap (from another tool), a broken Dieci wheel file,
# the clean Dragon + DiamondTile originals, and the Alpha boost swap (no clean copy shipped for it yet)
shutil.copy(f"{SW}/octane_fennec/Body_Octane_SF.upk", cook)
open(os.path.join(cook,"WHEEL_Caliber_SF.upk"),"wb").write(b"")
shutil.copy(f"{OR}/explosion_Dragon_SF.upk", cook); shutil.copy(f"{OR}/playerBanner_DiamondTile_SF.upk", cook)
shutil.copy(f"{SW}/bubbles_alpha/Boost_Bubble_SF.upk", cook)
json.dump({"schema":3,"welcome":False}, open(H+"/Documents/Rubenium/settings.json","w"))
from PyQt6.QtWidgets import QApplication
import Rubenium as A
A.Online._load = lambda self: self.__dict__.update(s={"refresh_token":"x","username":"Test","access_token":"x","expires_at":9e12}, minutes=0)
A.find_installs=lambda: {"epic":{"folder":ROOT,"app":"Sugar"}}
q=QApplication([]); a=A.App(q); eng=a.rocket
eng.running=lambda plat="": False
eng._settled=lambda plat: True
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.005)
def wait():
    t=time.time(); pump(50)
    while eng.working and time.time()-t<15: pump(30)
    pump(100)
h=lambda p: hashlib.sha256(open(p,"rb").read()).hexdigest() if os.path.exists(p) else "none"
G=lambda f: os.path.join(cook,f)
ORIG={f:h(f"{OR}/{f}") for f in os.listdir(OR)}
pump(300); eng.ensure_detected(); print("installs:", eng.available(), "platform", eng.platform())
print("soon items left:", [i["id"] for i in A.RL_ITEMS if i.get("soon")], "| bundled originals:", sorted(A.ORIGINALS))
print("A needs repair (new user):", eng.needs_repair("epic"))
eng.watch(); wait()
print("  body back to original:", h(G("Body_Octane_SF.upk"))==ORIG["Body_Octane_SF.upk"])
print("  broken wheel repaired:", h(G("WHEEL_Caliber_SF.upk"))==ORIG["WHEEL_Caliber_SF.upk"])
print("  alpha boost left alone (no clean copy yet):", h(G("Boost_Bubble_SF.upk"))==h(f"{SW}/bubbles_alpha/Boost_Bubble_SF.upk"))
print("  needs repair now:", eng.needs_repair("epic"), "(no endless loop)")
# B: the removed swaps (a copy kept from the 1.6 release) are found in the game and the original comes back
OLD="/tmp/oldswaps"
for name,src in (("explosion_Dragon_SF.upk","dragons_monsoon"),("playerBanner_DiamondTile_SF.upk","diamond_electric")):
    shutil.copy(f"{OLD}/{src}/{name}", cook)
a.cfg["rl"]["installs"]["epic"]["active"]={"x":"dragons_monsoon","y":"diamond_electric"}
print("B removed ids ignored:", eng.active("epic"), "| found:", eng.needs_repair("epic")); eng._repair_wait.clear(); eng.watch(); wait()
print("  dragon original back:", h(G("explosion_Dragon_SF.upk"))==ORIG["explosion_Dragon_SF.upk"], "| diamond original back:", h(G("playerBanner_DiamondTile_SF.upk"))==ORIG["playerBanner_DiamondTile_SF.upk"])
print("  removed from the list:", not any(i["id"] in A.REMOVED_SWAPS for i in A.RL_ITEMS))
# E: a tampered shipped copy is never used
p=[r/"_originals"/"WHEEL_Caliber_SF.upk" for r in A._swap_roots() if (r/"_originals"/"WHEEL_Caliber_SF.upk").is_file()][0]
good=open(p,"rb").read(); open(p,"wb").write(good[:-10]+b"0123456789"); A._hash_cache.clear()
print("E tampered shipped copy refused:", A.bundled_original("WHEEL_Caliber_SF.upk") is None); open(p,"wb").write(good); A._hash_cache.clear()
print("  restored:", A.bundled_original("WHEEL_Caliber_SF.upk") is not None)
# F: Reset Swaps button
a.window.expand(); pump(800); a.window.goto("rl"); pump(800)
from PyQt6.QtWidgets import QPushButton
pg=a.window.page(); btns=[b for b in pg.findChildren(A.Button) if getattr(b,"_text","") or True]
print("F button texts:", [b.text() if hasattr(b,'text') and callable(b.text) else getattr(b,'_text','') for b in pg.findChildren(A.Button)][-3:])
a.window.grab().save("/tmp/rl15.png")
a.shutdown()
