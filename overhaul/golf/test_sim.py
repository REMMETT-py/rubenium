"""The server's golf roll must match the app's simulate() on every hole: random shots, same results.
Usage: python overhaul/golf/test_sim.py [shots]   (needs the local Postgres; makes and drops database rb_golfsim)"""
import math
import os
import random
import subprocess
import sys
import time

import psycopg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import holes  # noqa: E402

ENV = dict(os.environ, PGHOST=os.environ.get("PGHOST", "/var/tmp/pg"), PGPORT=os.environ.get("PGPORT", "5433"),
           PGUSER=os.environ.get("PGUSER", "postgres"))
HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    subprocess.run(["psql", "-q", "-X", "-d", "postgres", "-c", "drop database if exists rb_golfsim",
                    "-c", "create database rb_golfsim"], env=ENV, check=True)
    subprocess.run(["psql", "-q", "-X", "-v", "ON_ERROR_STOP=1", "-d", "rb_golfsim", "-c",
                    "do $$ begin create role anon; exception when duplicate_object then null; end $$;"
                    "do $$ begin create role authenticated; exception when duplicate_object then null; end $$;",
                    "-f", os.path.join(HERE, "sim.sql")], env=ENV, check=True)
    c = psycopg.connect(f"host={ENV['PGHOST']} port={ENV['PGPORT']} user={ENV['PGUSER']} dbname=rb_golfsim", autocommit=True)
    c.execute("insert into public.rb_golf_hole_defs values " + holes.sql_rows())
    rnd = random.Random(11)
    ids = holes.hole_ids()
    bad = holed = 0
    t0 = time.time()
    worst = 0.0
    for _ in range(n):
        hid = rnd.choice(ids)
        h = holes.get_hole(hid)
        x, y = h["tee"] if rnd.random() < 0.5 else (rnd.uniform(0.02, 0.98), rnd.uniform(0.02, 0.60))
        cx, cy = h["cup"]
        ang = (math.atan2(cy - y, cx - x) + rnd.gauss(0, 0.12)) if rnd.random() < 0.6 else rnd.uniform(-math.pi, math.pi)
        pw = rnd.uniform(0.02, 1.0)
        _f, px, py, ph = holes.simulate(h, x, y, ang, pw)
        sx, sy, sh = c.execute("select ex, ey, holed from public.rb_golf_sim(%s, %s, %s, %s, %s)", (hid, x, y, ang, pw)).fetchone()
        holed += ph
        gap = math.hypot(px - sx, py - sy)
        worst = max(worst, gap)
        if ph != sh or gap > 1e-9:
            bad += 1
            if bad <= 5:
                print("DIFFERENT", hid, x, y, ang, pw, (px, py, ph), (sx, sy, sh))
    ms = (time.time() - t0) / n * 1000
    print(f"{n} shots, {holed} holed by the app, {bad} different, largest gap {worst:.2e}, {ms:.1f} ms a shot")
    c.close()
    subprocess.run(["psql", "-q", "-X", "-d", "postgres", "-c", "drop database rb_golfsim"], env=ENV)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
