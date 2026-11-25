# measure.py: start Rubenium headless, wait, then sample its CPU and memory (Linux offscreen proxy, not Windows numbers)
import os, subprocess, sys, time, psutil
env = dict(os.environ, QT_QPA_PLATFORM="offscreen", HOME=sys.argv[1], RUBENIUM_DEBUG="1")
t0 = time.time()
p = subprocess.Popen([sys.executable, sys.argv[2]] + sys.argv[4:], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
pp = psutil.Process(p.pid)
time.sleep(float(sys.argv[3]))
pp.cpu_percent(None); c0 = pp.cpu_times(); t1 = time.time()
time.sleep(30)
c1 = pp.cpu_times(); dt = time.time() - t1
cpu = (c1.user + c1.system - c0.user - c0.system) / dt * 100
print(f"idle CPU {cpu:.2f}% of one core over {dt:.0f}s, RSS {pp.memory_info().rss/1e6:.0f} MB, threads {pp.num_threads()}")
p.kill()
