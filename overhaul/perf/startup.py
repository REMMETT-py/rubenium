# startup.py: time from process start to Rubenium entering its event loop (ball ready), headless
import os, sys, time, runpy
t0 = time.perf_counter()
from PyQt6.QtWidgets import QApplication
def fake_exec(self):
    print(f"STARTUP {time.perf_counter() - t0:.2f}s to event loop"); return 0
QApplication.exec = fake_exec
sys.argv = [sys.argv[1]]
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
except SystemExit:
    pass
