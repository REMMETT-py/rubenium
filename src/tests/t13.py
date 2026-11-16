import os, sys, shutil, time, subprocess
H="/tmp/h5"; shutil.rmtree(H,ignore_errors=True); os.makedirs(H+"/Documents"); os.environ["HOME"]=H; os.environ["LOCALAPPDATA"]=H+"/Local"
sys.path.insert(0,"/home/claude/release"); sys.argv=["x"]
import Rubenium as A
A._retry.__defaults__=(4,0.05)
app=H+"/Desktop"; os.makedirs(app); exe=app+"/Rubenium.exe"; open(exe,"w").write("OLD")
new=H+"/dl.exe"; open(new,"w").write("NEW")
sys.frozen=True; sys.executable=exe
print("1 in place:", A.place_exe(A.Path(new),"4.0.0")==os.path.realpath(exe), open(exe).read(), open(app+"/Rubenium.old.exe").read(), os.path.exists(app+"/Rubenium.new.exe"))
# protected folder -> side install
open(exe,"w").write("OLD"); os.chmod(app,0o555)
if os.geteuid()==0:
    real=shutil.copyfile
    def blocked(src,dst,*a,**k):
        if str(dst).startswith(app): raise PermissionError(13,"denied")
        return real(src,dst,*a,**k)
    shutil.copyfile=blocked
p=A.place_exe(A.Path(new),"4.0.0"); print("2 side:", p, open(p).read(), "old untouched:", open(exe).read(), "version:", A.side_version())
os.chmod(app,0o755)
calls=[]
class P:
    def __init__(s,a,**k): calls.append((a,k.get("env",{}).get("PYINSTALLER_RESET_ENVIRONMENT")))
A.subprocess_Popen=None
import subprocess as sp; sp.Popen=P
os.environ["_MEIPASS2"]="x"; os.environ["_PYI_APPLICATION_HOME_DIR"]="y"
print("3 handoff from old (3.0.0):", A.handoff("3.0.0"), calls[-1][0][0]==p, calls[-1][1], "env clean:", not any(k.startswith(("_MEI","_PYI")) for k in A.clean_env()))
print("4 no handoff when same/newer:", A.handoff("4.0.0"), A.handoff("5.0.0"))
sys.executable=p; print("5 no handoff from the side copy itself:", A.handoff("3.0.0"))
new2=H+"/dl2.exe"; open(new2,"w").write("NEWER"); print("6 side copy updates itself in place:", A.place_exe(A.Path(new2),"5.0.0")==os.path.realpath(p), open(p).read())
A.Updater.cleanup(); print("7 cleanup:", sorted(os.listdir(os.path.dirname(p))), sorted(os.listdir(app)))
print("8 restart args:", A.restart(p,("--selftest",)), calls[-1][0][1:])
print("9 label:", A.version_tuple("v4.0.0")>A.version_tuple("3.0.0"))
