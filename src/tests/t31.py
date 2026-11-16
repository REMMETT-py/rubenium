import os, sys, json
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["HOME"]="/tmp/h30en"
sys.path.insert(0,"/home/claude/release"); sys.argv=["x"]
from PyQt6.QtWidgets import QApplication
import Rubenium as A
q=QApplication([]); a=A.App(q); W=a.wallet
print("restart keeps:", W.balance(), "keys", W.keys(), "inv", W.d["inv"], "worn", a.cfg["badges"], "played", int(W.d["played"]), "tampered", W.tampered)
a.shutdown()
