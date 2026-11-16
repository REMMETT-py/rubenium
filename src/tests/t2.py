import os, sys, time, json, re, glob, shutil
os.environ["QT_QPA_PLATFORM"]="offscreen"; os.environ["RUBENIUM_DEMO"]="1"
shutil.rmtree("/tmp/rbhome3", ignore_errors=True)
os.environ["HOME"]="/tmp/rbhome3"; os.makedirs("/tmp/rbhome3/Documents",exist_ok=True)
sys.path.insert(0,"/home/claude/Rubenium")
from PyQt6.QtWidgets import QApplication
from rubenium import app as A, core, lang_fr
keys=set()
for f in glob.glob('rubenium/*.py'):
    for m in re.finditer(r'\btr\(\s*((?:"(?:[^"\\]|\\.)*"\s*)+)', open(f).read()): keys.add(eval("("+m.group(1)+")"))
print("keys",len(keys),"missing FR:", sorted(k for k in keys if k not in lang_fr.FR))
print("unused FR:", sorted(k for k in lang_fr.FR if k not in keys)[:40])
core.setup_logging()
q=QApplication([]); q.setStyleSheet(A.APP_QSS)
a=A.App(q); w=a.window
def pump(ms):
    t=time.time()
    while time.time()-t<ms/1000: q.processEvents(); time.sleep(0.005)
out="/tmp/s4"; os.makedirs(out,exist_ok=True)
pump(700)
print("ball visible:", w.ball.isVisible() if hasattr(w,'ball') else '?', "main visible:", w.isVisible())
w.expand(); pump(900)
for k in ["home","lyrics","crosshair","display","perf","tools","rl","settings"]:
    w.goto(k); pump(1400 if k=="perf" else 700); w.grab().save(f"{out}/{k}.png")
    sa,page,h=w.pages[k]; print(k, type(page).__name__, h, round(w.pageh.level))
a.set_language("fr"); pump(500)
for k in ["tools","settings","rl"]:
    w.goto(k); pump(700); w.grab().save(f"{out}/fr_{k}.png")
w.collapse(); pump(1200); print("after collapse main visible:", w.isVisible(), "ball:", w.ball.isVisible(), w.ball.geometry()); w.ball.grab().save(out+"/ball.png")
a.shutdown(); print(os.listdir("/tmp/rbhome3/Documents"), os.listdir("/tmp/rbhome3/Documents/Rubenium"))
