"""9.2: the Mini Golf bots, worked out with the real ball physics (the app's simulate(), compiled with numba).

For every hole (1-60; 101-160 are the same holes mirrored, so they play the same) and every bot level, a bot plays the
hole many times from the four party tees: it searches a grid of shots (aim x power) with the real physics, picks the
one it judges best (Professional and Hard pick the shot that still goes in when it is hit slightly off), then hits it
with the error of its level (Easy a lot, Professional very little). The strokes it takes give the odds for that hole.
The best hole-in-one shot from each tee is kept too, so the app can show a Professional's ace as the real roll.

    python overhaul/golf/bots.py [trials]      writes overhaul/golf/bot_odds.json (a few minutes)
"""
import json
import math
import os
import sys
import time

import numpy as np
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import holes  # noqa: E402

C = holes.CONST
R, CUPR, FH, BOUNCE, DEC0, VMAX, DMAX = C["BALL_R"], C["CUP_R"], C["FIELD_H"], C["BOUNCE"], C["GOLF_DEC"], C["VMAX"], C["GOLF_DMAX"]
# level: (aim grid, power grid, aim error (rad), power error (share), how many of the best it picks from, robust window,
#         how many leaves it looks one shot further from)
LEVELS = {"easy": (36, 6, 0.085, 0.20, 6, 0, 0), "medium": (90, 10, 0.040, 0.10, 2, 0, 0),
          "hard": (180, 16, 0.016, 0.040, 1, 1, 6), "pro": (360, 28, 0.0045, 0.012, 1, 2, 24)}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_odds.json")


@njit(cache=True)
def sim(x, y, ang, pw, cup, rects, circles, sand, ice, water, boost):
    v = math.sqrt(max(0.0, min(1.0, pw))) * VMAX
    vx = math.cos(ang) * v
    vy = math.sin(ang) * v
    dt = 1.0 / 240
    x0, y0 = x, y
    cx, cy = cup[0], cup[1]
    r = R
    for step in range(240 * 14):
        x += vx * dt
        y += vy * dt
        if x < r:
            x = r
            vx = abs(vx) * BOUNCE
        elif x > 1 - r:
            x = 1 - r
            vx = -abs(vx) * BOUNCE
        if y < r:
            y = r
            vy = abs(vy) * BOUNCE
        elif y > FH - r:
            y = FH - r
            vy = -abs(vy) * BOUNCE
        for k in range(rects.shape[0]):
            x1, y1, x2, y2 = rects[k, 0], rects[k, 1], rects[k, 2], rects[k, 3]
            qx = max(x1, min(x2, x))
            qy = max(y1, min(y2, y))
            dx = x - qx
            dy = y - qy
            d = math.hypot(dx, dy)
            if d < r:
                if d < 1e-9:
                    bd, nx, ny = x - x1, -1.0, 0.0
                    if x2 - x < bd:
                        bd, nx, ny = x2 - x, 1.0, 0.0
                    if y - y1 < bd:
                        bd, nx, ny = y - y1, 0.0, -1.0
                    if y2 - y < bd:
                        bd, nx, ny = y2 - y, 0.0, 1.0
                    if nx != 0:
                        x = x1 - r if nx < 0 else x2 + r
                    if ny != 0:
                        y = y1 - r if ny < 0 else y2 + r
                else:
                    nx = dx / d
                    ny = dy / d
                    x = qx + nx * r
                    y = qy + ny * r
                vn = vx * nx + vy * ny
                if vn < 0:
                    vx -= (1 + BOUNCE) * vn * nx
                    vy -= (1 + BOUNCE) * vn * ny
        for k in range(circles.shape[0]):
            bx, by, br = circles[k, 0], circles[k, 1], circles[k, 2]
            dx = x - bx
            dy = y - by
            d = math.hypot(dx, dy)
            if d < br + r and d > 1e-9:
                nx = dx / d
                ny = dy / d
                x = bx + nx * (br + r)
                y = by + ny * (br + r)
                vn = vx * nx + vy * ny
                if vn < 0:
                    vx -= 1.95 * vn * nx
                    vy -= 1.95 * vn * ny
        for k in range(water.shape[0]):
            if water[k, 0] <= x <= water[k, 2] and water[k, 1] <= y <= water[k, 3]:
                return x0, y0, False
        for k in range(boost.shape[0]):
            if boost[k, 0] <= x <= boost[k, 2] and boost[k, 1] <= y <= boost[k, 3]:
                vx += boost[k, 4] * dt * 4
                vy += boost[k, 5] * dt * 4
        speed = math.hypot(vx, vy)
        dc = math.hypot(x - cx, y - cy)
        if dc < CUPR * 2.2 and speed < 0.7:
            pull = 1.6 * dt
            vx += (cx - x) / max(dc, 1e-6) * pull
            vy += (cy - y) / max(dc, 1e-6) * pull
        if dc < CUPR and speed < 1.05:
            return cx, cy, True
        dec = (DEC0 + speed * 0.04) * dt
        ins = False
        for k in range(sand.shape[0]):
            if sand[k, 0] <= x <= sand[k, 2] and sand[k, 1] <= y <= sand[k, 3]:
                ins = True
                break
        if ins:
            dec *= 4.0
        else:
            for k in range(ice.shape[0]):
                if ice[k, 0] <= x <= ice[k, 2] and ice[k, 1] <= y <= ice[k, 3]:
                    ins = True
                    break
            if ins:
                dec *= 0.25
        if speed <= dec or speed < 0.004:
            break
        f = (speed - dec) / speed
        vx *= f
        vy *= f
    return x, y, False


@njit(cache=True)
def grid_eval(x, y, na, npw, direct, cup, rects, circles, sand, ice, water, boost, field):
    """Every shot of an aim x power grid (half the aims fanned round the straight line, half all round):
    0 when it goes in, else how far the ball is left from the cup going round the walls."""
    out = np.empty((na, npw))
    ends = np.empty((na, npw, 2))
    for i in range(na):
        if i < na // 2:
            ang = direct + (i - na // 4) * (0.9 / (na // 2))
        else:
            ang = -math.pi + (i - na // 2) * (2 * math.pi / (na - na // 2))
        for j in range(npw):
            pw = 0.03 + 0.97 * ((j + 0.5) / npw) ** 1.6
            ex, ey, holed = sim(x, y, ang, pw, cup, rects, circles, sand, ice, water, boost)
            ends[i, j, 0] = ex
            ends[i, j, 1] = ey
            if holed:
                out[i, j] = 0.0
            else:
                gx = min(field.shape[0] - 1, max(0, int(ex / 0.01)))
                gy = min(field.shape[1] - 1, max(0, int(ey / 0.01)))
                out[i, j] = field[gx, gy]
                if abs(ex - x) + abs(ey - y) < 0.01:
                    out[i, j] += 5.0                     # back where it was (water) or barely moved
    return out, ends


def grid_shot(i, j, na, npw, direct):
    ang = direct + (i - na // 4) * (0.9 / (na // 2)) if i < na // 2 else -math.pi + (i - na // 2) * (2 * math.pi / (na - na // 2))
    return ang, 0.03 + 0.97 * ((j + 0.5) / npw) ** 1.6


def field_of(h):
    """Distance to the cup going round walls and water, on a 1 cm grid (Dijkstra, 8 neighbours)."""
    import heapq
    nx, ny = 100, int(FH / 0.01) + 1
    block = np.zeros((nx, ny), bool)
    for gx in range(nx):
        for gy in range(ny):
            x, y = (gx + 0.5) * 0.01, (gy + 0.5) * 0.01
            if any(x1 - R <= x <= x2 + R and y1 - R <= y <= y2 + R for x1, y1, x2, y2 in h["rects"]):
                block[gx, gy] = True
            elif any(math.hypot(x - bx, y - by) <= br + R for bx, by, br in h["circles"]):
                block[gx, gy] = True
            elif any(x1 <= x <= x2 and y1 <= y <= y2 for x1, y1, x2, y2 in h.get("water", [])):
                block[gx, gy] = True
    dist = np.full((nx, ny), 9.0)
    cx, cy = int(h["cup"][0] / 0.01), int(h["cup"][1] / 0.01)
    dist[cx, cy] = 0.0
    pq = [(0.0, cx, cy)]
    while pq:
        d, a, b = heapq.heappop(pq)
        if d > dist[a, b]:
            continue
        for da in (-1, 0, 1):
            for db in (-1, 0, 1):
                if da == db == 0:
                    continue
                u, w = a + da, b + db
                if 0 <= u < nx and 0 <= w < ny and not block[u, w]:
                    nd = d + 0.01 * math.hypot(da, db)
                    if nd < dist[u, w]:
                        dist[u, w] = nd
                        heapq.heappush(pq, (nd, u, w))
    dist[block] = np.minimum(dist[block], 9.0)
    return dist


def arrs(h):
    a = lambda rs, n: np.array(rs, dtype=np.float64).reshape(-1, n) if rs else np.zeros((0, n))   # noqa: E731
    return (np.array(h["cup"], dtype=np.float64), a(h["rects"], 4), a(h["circles"], 3), a(h.get("sand", []), 4),
            a(h.get("ice", []), 4), a(h.get("water", []), 4), a(h.get("boost", []), 6))


def tee(h, seat):
    tx, ty = h["tee"]
    return tx, max(0.02, min(0.6, ty + (seat - 1.5) * 0.022))


def choose(score, rng, pick_from, window):
    """The shot a bot goes for: the best of the grid, judged over its neighbours when it plays safe (window)."""
    s = score
    if window:
        holed = (score == 0.0).astype(float)
        k = window
        pad = np.pad(holed, ((k, k), (k, k)), mode="wrap")
        ok = sum(pad[k + di:k + di + s.shape[0], k + dj:k + dj + s.shape[1]] for di in range(-k, k + 1)
                 for dj in range(-k, k + 1)) / (2 * k + 1) ** 2
        s = score - ok                                    # a wide window of shots that go in beats a lucky one
    flat = np.argsort(s, axis=None)
    pick = flat[rng.integers(0, pick_from)] if pick_from > 1 else flat[0]
    return np.unravel_index(pick, s.shape)


def holed_window(score, k):
    """The share of shots round the best one that still go in (how safe the best shot is)."""
    holed = (score == 0.0).astype(float)
    pad = np.pad(holed, ((k, k), (k, k)), mode="wrap")
    ok = sum(pad[k + di:k + di + score.shape[0], k + dj:k + dj + score.shape[1]] for di in range(-k, k + 1)
             for dj in range(-k, k + 1)) / (2 * k + 1) ** 2
    return float(ok.max())


def look_ahead(pos, score, ends, A, field, h, m, k):
    """No shot goes in from here: of the m best leaves, the one with the safest next shot into the cup."""
    order = np.argsort(score, axis=None)[: m * 4]
    seen, best, pick = [], -1.0, None
    for f in order:
        i, j = np.unravel_index(f, score.shape)
        e = ends[i, j]
        if any(abs(e[0] - a) + abs(e[1] - b) < 0.015 for a, b in seen):
            continue
        seen.append((e[0], e[1]))
        d2 = math.atan2(h["cup"][1] - e[1], h["cup"][0] - e[0])
        s2, _e2 = grid_eval(e[0], e[1], 120, 16, d2, *A, field)
        v = holed_window(s2, k) - 0.02 * score[i, j]
        if v > best:
            best, pick = v, (i, j)
        if len(seen) >= m:
            break
    return pick


def play(h, A, field, level, seat, rng, cache):
    na, npw, ea, ep, pick_from, window, ahead = LEVELS[level]
    pos, n = tee(h, seat), 0
    while n < 6:
        n += 1
        direct = math.atan2(h["cup"][1] - pos[1], h["cup"][0] - pos[0])
        key = (n == 1, seat)
        if n == 1 and key in cache:
            score, plan = cache[key]
        else:
            a, p = (na, npw) if n == 1 else (max(24, na * 2 // 3), max(6, npw * 2 // 3))
            score, ends = grid_eval(pos[0], pos[1], a, p, direct, *A, field)
            plan = look_ahead(pos, score, ends, A, field, h, ahead, max(1, window)) \
                if ahead and not (score == 0.0).any() else None
            if n == 1:
                cache[key] = (score, plan)
        i, j = plan if plan is not None else choose(score, rng, pick_from, window)
        ang, pw = grid_shot(i, j, score.shape[0], score.shape[1], direct)
        ang += rng.normal(0, ea)
        pw = max(0.02, min(1.0, pw * (1 + rng.normal(0, ep))))
        ex, ey, holed = sim(pos[0], pos[1], ang, pw, *A)
        if holed:
            return n
        pos = (ex, ey)
    return 6


def ace(h, A, field, seat):
    """The Professional's hole-in-one from this tee, when there is one: the middle of the widest band of shots that go in."""
    na, npw = 720, 48
    direct = math.atan2(h["cup"][1] - tee(h, seat)[1], h["cup"][0] - tee(h, seat)[0])
    x, y = tee(h, seat)
    score, _e = grid_eval(x, y, na, npw, direct, *A, field)
    if not (score == 0.0).any():
        return None
    i, j = choose(score, np.random.default_rng(0), 1, 2)
    if score[i, j] != 0.0:
        return None
    ang, pw = grid_shot(i, j, na, npw, direct)
    _x, _y, holed = sim(x, y, ang, pw, *A)
    return [round(ang, 6), round(pw, 6)] if holed else None


def main() -> None:
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 48
    ids = sorted(holes.HOLES)
    only = [int(a) for a in sys.argv[2:]]
    if only:
        ids = only
    out = {"trials": trials, "odds": {}, "ace": {}}
    t0 = time.time()
    for hid in ids:
        h = holes.get_hole(hid)
        A = arrs(h)
        field = field_of(h)
        out["odds"][hid] = {}
        for level in LEVELS:
            rng = np.random.default_rng(hid * 7 + len(level))
            cache: dict = {}
            got = [play(h, A, field, level, t % 4, rng, cache) for t in range(trials)]
            out["odds"][hid][level] = [round(100 * got.count(k) / trials) for k in range(1, 7)]
        out["ace"][hid] = [ace(h, A, field, s) for s in range(4)]
        print(hid, h["name"], {k: v for k, v in out["odds"][hid].items()}, "aces", sum(a is not None for a in out["ace"][hid]),
              f"{time.time() - t0:.0f}s", flush=True)
    if not only:
        json.dump(out, open(OUT, "w"), indent=0)


if __name__ == "__main__":
    main()
