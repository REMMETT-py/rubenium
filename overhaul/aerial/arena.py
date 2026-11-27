"""Rubenium League bot arena: headless bot matches in parallel, win shares and fitted Elo.

  python overhaul/aerial/arena.py ladder [N]        neighbours on the roster, N matches a pair (default 100)
  python overhaul/aerial/arena.py pair A B [N]      one pair
  python overhaul/aerial/arena.py curve [N]         strength of a plain bot at levels 0.0 .. 1.0

Sides alternate so neither colour has an edge. Results are appended to overhaul/aerial/arena_results.jsonl, so a run
that is stopped can be resumed (finished matches are not played again)."""
import json
import math
import multiprocessing as mp
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "arena_results.jsonl")
A = None


def code() -> str:
    src = open(os.path.join(REPO, "Rubenium.py"), encoding="utf-8").read()
    return src[src.index("# SECTION: aerial (sim)"):src.index("# SECTION: aerial (drawing)")]


VERSION = __import__("hashlib").sha1(code().encode()).hexdigest()[:10]     # results are kept per code version


def load() -> dict:
    ns = {"__name__": "aerial_arena"}
    exec(compile(code(), "Rubenium.py:aerial", "exec"), ns)
    return ns


def _init() -> None:
    global A
    A = load()


def _prof(spec):
    """'halo', 'halo@0.55' (its level changed) or 'halo@0.55+react=1+aggro=0.4' (settings changed too)."""
    base, *over = spec.split("+")
    if "@" in base:
        k, lv = base.split("@")
        p = A["aerial_bot_profile"](k, float(lv))
    else:
        p = A["aerial_bot_profile"](base)
    for o in over:
        k, v = o.split("=")
        p[k] = type(p[k])(float(v)) if not isinstance(p[k], bool) else bool(float(v))
    return p


def play(job):
    a, b, seed, secs = job
    pa, pb = _prof(a), _prof(b)
    if seed % 2 == 0:
        r = A["aerial_bot_match"](a.split("@")[0].split("+")[0], b.split("@")[0].split("+")[0], seed=seed, match_s=secs, prof_a=pa, prof_b=pb)
        win = r["winner"] == 0
    else:
        r = A["aerial_bot_match"](b.split("@")[0].split("+")[0], a.split("@")[0].split("+")[0], seed=seed, match_s=secs, prof_a=pb, prof_b=pa)
        win = r["winner"] == 1
    return {"a": a, "b": b, "seed": seed, "secs": secs, "a_won": bool(win), "score": r["score"], "v": VERSION}


def run(pairs, n, secs=60.0):
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT):
            d = json.loads(line)
            if d.get("v") == VERSION:
                done.add((d["a"], d["b"], d["seed"], d["secs"]))
    jobs = [(a, b, 1000 + i, secs) for a, b in pairs for i in range(n) if (a, b, 1000 + i, secs) not in done]
    with mp.Pool(os.cpu_count() or 2, initializer=_init) as pool, open(OUT, "a") as f:
        for res in pool.imap_unordered(play, jobs, chunksize=2):
            f.write(json.dumps(res) + "\n")
            f.flush()
    return summary(pairs, n, secs)


def summary(pairs, n, secs=60.0):
    rows = {}
    for line in open(OUT):
        d = json.loads(line)
        if d["secs"] == secs and d["seed"] < 1000 + n and d.get("v") == VERSION:
            rows.setdefault((d["a"], d["b"]), []).append(d["a_won"])
    out = []
    for a, b in pairs:
        w = rows.get((a, b), [])
        if not w:
            continue
        p = sum(w) / len(w)
        ci = 1.96 * math.sqrt(max(p * (1 - p), 0.01) / len(w))
        q = min(0.995, max(0.005, p))
        elo = 400 * math.log10(q / (1 - q))
        out.append((a, b, len(w), p, ci, elo))
        print("%-12s vs %-12s  %3d  %5.1f%% ±%4.1f  Elo gap %+5.0f" % (a, b, len(w), 100 * p, 100 * ci, elo), flush=True)
    return out


if __name__ == "__main__":
    _init()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ladder"
    if cmd == "curve":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 40
        lv = [round(0.1 * i, 1) for i in range(11)]
        run([("ember@%.1f" % lv[i + 1], "ember@%.1f" % lv[i]) for i in range(10)], n)
    elif cmd == "vs":                                       # several challengers against one base
        n = int(sys.argv[2])
        run([(c, sys.argv[3]) for c in sys.argv[4:]], n)
    elif cmd == "pairs":                                    # pairs a:b,c:d ...
        n = int(sys.argv[2])
        run([tuple(x.split(":")) for x in sys.argv[3].split(",")], n)
    elif cmd == "pair":
        n = int(sys.argv[4]) if len(sys.argv) > 4 else 100
        run([(sys.argv[2], sys.argv[3])], n)
    else:
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 100
        keys = [r[0] for r in A["AERIAL_BOT_ROSTER"]]
        run([(keys[i + 1], keys[i]) for i in range(len(keys) - 1)], n)
