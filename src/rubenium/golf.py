"""Live 1 v 1 mini golf (3.0.0). 3.2: open lobbies instead of invitations, 5 holes, 8 new holes.

Both players see the same course. They take turns: drag back from anywhere, let go to shoot. Every shot is sent to
the server with where the ball stopped; the other player sees it roll a moment later. 5 holes, at most 6 strokes a
hole, 25 seconds a turn. Fewest strokes wins the bet (5% fee); a draw gives both bets back. Anyone can open a lobby
(one at a time); it closes by itself after 5 minutes if nobody joins."""
import math
import time

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from .core import S, sfx, TEXT, TEXT_DIM, alpha, font, tr, ui
from .wallet import coins_text
from .widgets import Button, IconButton, Label, Segmented, SliderRow, hbox

FIELD_H = 0.62                     # the course is 1 wide and 0.62 high
BALL_R = 0.013
CUP_R = 0.022
VMAX = 1.9
BOUNCE = 0.78
TURN_S = 25

# hole number -> name, tee, cup, walls (x1, y1, x2, y2) and round bumpers (x, y, r)
HOLES = {
    1: dict(name="Warm-up", tee=(0.10, 0.31), cup=(0.88, 0.31), rects=[], circles=[(0.50, 0.31, 0.05)]),
    2: dict(name="The Gate", tee=(0.10, 0.31), cup=(0.88, 0.31),
            rects=[(0.48, 0.0, 0.52, 0.24), (0.48, 0.38, 0.52, 0.62)], circles=[]),
    3: dict(name="Dogleg", tee=(0.10, 0.50), cup=(0.86, 0.12), rects=[(0.0, 0.0, 0.62, 0.36)], circles=[]),
    4: dict(name="Pinball", tee=(0.10, 0.31), cup=(0.90, 0.31), rects=[],
            circles=[(0.35, 0.20, 0.045), (0.35, 0.42, 0.045), (0.60, 0.31, 0.045), (0.75, 0.15, 0.045), (0.75, 0.47, 0.045)]),
    5: dict(name="Zigzag", tee=(0.10, 0.10), cup=(0.90, 0.52), rects=[(0.30, 0.0, 0.36, 0.44), (0.62, 0.18, 0.68, 0.62)],
            circles=[]),
    6: dict(name="The Island", tee=(0.10, 0.31), cup=(0.50, 0.31),
            rects=[(0.38, 0.17, 0.62, 0.21), (0.38, 0.41, 0.62, 0.45), (0.38, 0.21, 0.42, 0.41)], circles=[]),
    7: dict(name="Tunnel", tee=(0.08, 0.08), cup=(0.92, 0.54), rects=[(0.25, 0.0, 0.75, 0.26), (0.25, 0.36, 0.75, 0.62)],
            circles=[]),
    8: dict(name="Diamond", tee=(0.08, 0.31), cup=(0.92, 0.31), rects=[(0.45, 0.20, 0.55, 0.42)],
            circles=[(0.30, 0.31, 0.04), (0.70, 0.31, 0.04)]),
    # sand slows the ball, ice keeps it rolling, boost pads push it, water sends it back where it was hit from
    9: dict(name="Bunker", tee=(0.10, 0.31), cup=(0.88, 0.31), rects=[], circles=[], sand=[(0.40, 0.12, 0.62, 0.50)]),
    10: dict(name="Lake", tee=(0.10, 0.50), cup=(0.88, 0.14), rects=[], circles=[], water=[(0.30, 0.0, 0.55, 0.40)]),
    11: dict(name="Ice Rink", tee=(0.10, 0.31), cup=(0.86, 0.31), rects=[(0.50, 0.0, 0.54, 0.20), (0.50, 0.42, 0.54, 0.62)],
             circles=[], ice=[(0.20, 0.0, 0.80, 0.62)]),
    12: dict(name="Launch Pad", tee=(0.08, 0.52), cup=(0.90, 0.10), rects=[(0.0, 0.0, 0.40, 0.36)], circles=[],
             boost=[(0.42, 0.40, 0.56, 0.62, 0.0, -1.6)]),
    13: dict(name="Moat", tee=(0.10, 0.31), cup=(0.70, 0.31), rects=[], circles=[],
             water=[(0.55, 0.12, 0.85, 0.18), (0.55, 0.44, 0.85, 0.50), (0.85, 0.12, 0.91, 0.50)]),
    14: dict(name="Sand Trap Alley", tee=(0.08, 0.10), cup=(0.92, 0.52), rects=[(0.30, 0.0, 0.34, 0.40), (0.64, 0.22, 0.68, 0.62)],
             circles=[], sand=[(0.36, 0.40, 0.62, 0.62)], boost=[(0.70, 0.02, 0.95, 0.16, 0.0, 1.4)]),
    15: dict(name="Bumper Lake", tee=(0.08, 0.31), cup=(0.92, 0.31), rects=[],
             circles=[(0.40, 0.31, 0.05), (0.62, 0.15, 0.04), (0.62, 0.47, 0.04)], water=[(0.45, 0.24, 0.58, 0.38)]),
    16: dict(name="Express", tee=(0.08, 0.31), cup=(0.92, 0.31), rects=[(0.30, 0.0, 0.70, 0.22), (0.30, 0.40, 0.70, 0.62)],
             circles=[], boost=[(0.32, 0.24, 0.42, 0.38, 1.8, 0.0)], ice=[(0.44, 0.22, 0.70, 0.40)],
             sand=[(0.78, 0.18, 0.86, 0.44)]),
    # 3.2: eight new holes
    17: dict(name="Horseshoe", tee=(0.10, 0.12), cup=(0.12, 0.50), rects=[(0.0, 0.28, 0.72, 0.34)], circles=[(0.86, 0.31, 0.04)],
             sand=[(0.40, 0.40, 0.56, 0.62)]),
    18: dict(name="Twin Lakes", tee=(0.08, 0.31), cup=(0.92, 0.31), rects=[], circles=[(0.50, 0.31, 0.035)],
             water=[(0.25, 0.0, 0.75, 0.20), (0.25, 0.42, 0.75, 0.62)]),
    19: dict(name="Pinball Alley", tee=(0.08, 0.31), cup=(0.92, 0.31), rects=[(0.20, 0.0, 0.80, 0.10), (0.20, 0.52, 0.80, 0.62)],
             circles=[(0.32, 0.22, 0.03), (0.32, 0.40, 0.03), (0.47, 0.31, 0.03), (0.62, 0.20, 0.03), (0.62, 0.42, 0.03),
                      (0.76, 0.31, 0.03)]),
    20: dict(name="Ice Bridge", tee=(0.08, 0.31), cup=(0.92, 0.31), rects=[], circles=[],
             water=[(0.22, 0.0, 0.78, 0.24), (0.22, 0.38, 0.78, 0.62)], ice=[(0.22, 0.24, 0.78, 0.38)]),
    21: dict(name="Fortress", tee=(0.10, 0.31), cup=(0.70, 0.31),
             rects=[(0.55, 0.16, 0.85, 0.20), (0.55, 0.42, 0.85, 0.46), (0.81, 0.20, 0.85, 0.42), (0.55, 0.20, 0.59, 0.27),
                    (0.55, 0.35, 0.59, 0.42)], circles=[(0.35, 0.31, 0.04)]),
    22: dict(name="Slalom", tee=(0.08, 0.10), cup=(0.92, 0.52),
             rects=[(0.22, 0.0, 0.26, 0.42), (0.42, 0.20, 0.46, 0.62), (0.62, 0.0, 0.66, 0.42), (0.80, 0.20, 0.84, 0.62)],
             circles=[]),
    23: dict(name="Booster Loop", tee=(0.10, 0.50), cup=(0.10, 0.12), rects=[(0.0, 0.28, 0.70, 0.34)], circles=[],
             boost=[(0.74, 0.36, 0.96, 0.60, 0.0, -1.7), (0.40, 0.04, 0.70, 0.24, -1.6, 0.0)], ice=[(0.20, 0.0, 0.40, 0.28)]),
    24: dict(name="Dunes", tee=(0.08, 0.31), cup=(0.92, 0.31), rects=[(0.48, 0.24, 0.52, 0.38)], circles=[],
             sand=[(0.18, 0.0, 0.88, 0.22), (0.18, 0.40, 0.88, 0.62)], boost=[(0.20, 0.26, 0.34, 0.36, 1.2, 0.0)]),
    # 4.0: sixteen new holes (40 in all, 80 with the mirrored ones); each was played through by the simulation
    25: dict(name="Switchback", tee=(0.08, 0.10), cup=(0.92, 0.52), circles=[],
             rects=[(0.0, 0.20, 0.80, 0.24), (0.20, 0.38, 1.0, 0.42)]),
    26: dict(name="Bullseye", tee=(0.08, 0.31), cup=(0.52, 0.31), rects=[],
             circles=[(0.52, 0.17, 0.035), (0.52, 0.45, 0.035), (0.65, 0.31, 0.035), (0.42, 0.20, 0.03), (0.42, 0.42, 0.03)]),
    27: dict(name="Frozen Pond", tee=(0.08, 0.31), cup=(0.92, 0.31), rects=[], circles=[],
             ice=[(0.15, 0.06, 0.85, 0.56)], water=[(0.40, 0.24, 0.60, 0.38)]),
    28: dict(name="Sandbox", tee=(0.08, 0.52), cup=(0.90, 0.12), rects=[], circles=[(0.62, 0.40, 0.04)],
             sand=[(0.25, 0.0, 0.75, 0.62)], boost=[(0.28, 0.44, 0.40, 0.58, 1.5, -0.9)]),
    29: dict(name="Keyhole", tee=(0.08, 0.50), cup=(0.90, 0.31), circles=[],
             rects=[(0.50, 0.0, 0.54, 0.26), (0.50, 0.36, 0.54, 0.62)], sand=[(0.58, 0.14, 0.70, 0.48)]),
    30: dict(name="Snail", tee=(0.10, 0.10), cup=(0.50, 0.34), circles=[],
             rects=[(0.25, 0.18, 0.75, 0.21), (0.72, 0.21, 0.75, 0.50), (0.25, 0.47, 0.72, 0.50), (0.25, 0.29, 0.28, 0.47)]),
    31: dict(name="Waterfalls", tee=(0.08, 0.31), cup=(0.92, 0.31), rects=[], circles=[],
             water=[(0.30, 0.0, 0.36, 0.44), (0.64, 0.18, 0.70, 0.62)]),
    32: dict(name="Sand Rocket", tee=(0.08, 0.31), cup=(0.92, 0.31), rects=[], circles=[],
             sand=[(0.28, 0.0, 0.72, 0.62)], boost=[(0.28, 0.26, 0.72, 0.36, 2.2, 0.0)]),
    33: dict(name="Ping Pong", tee=(0.08, 0.31), cup=(0.50, 0.31), circles=[],
             rects=[(0.35, 0.12, 0.38, 0.50), (0.62, 0.12, 0.65, 0.50)]),
    34: dict(name="Crossroads", tee=(0.08, 0.12), cup=(0.92, 0.50), circles=[(0.50, 0.31, 0.03)],
             rects=[(0.40, 0.0, 0.44, 0.22), (0.40, 0.40, 0.44, 0.62), (0.56, 0.0, 0.60, 0.22), (0.56, 0.40, 0.60, 0.62)]),
    35: dict(name="Frozen Moat", tee=(0.08, 0.31), cup=(0.80, 0.31), rects=[], circles=[],
             water=[(0.66, 0.12, 0.92, 0.18), (0.66, 0.44, 0.92, 0.50), (0.92, 0.12, 0.97, 0.50)], ice=[(0.20, 0.12, 0.66, 0.50)]),
    36: dict(name="Labyrinth", tee=(0.08, 0.08), cup=(0.12, 0.57), circles=[],
             rects=[(0.0, 0.16, 0.70, 0.20), (0.30, 0.32, 1.0, 0.36), (0.0, 0.48, 0.70, 0.52)]),
    37: dict(name="Comet Trail", tee=(0.08, 0.31), cup=(0.92, 0.31), rects=[],
             circles=[(0.32, 0.15, 0.04), (0.47, 0.47, 0.04), (0.62, 0.15, 0.04), (0.77, 0.47, 0.04)],
             boost=[(0.15, 0.25, 0.25, 0.37, 1.4, 0.0)]),
    38: dict(name="Oasis", tee=(0.08, 0.31), cup=(0.60, 0.31), rects=[], circles=[],
             sand=[(0.15, 0.0, 0.85, 0.62)], water=[(0.70, 0.20, 0.76, 0.42)]),
    39: dict(name="Double Dogleg", tee=(0.10, 0.52), cup=(0.90, 0.10), circles=[],
             rects=[(0.0, 0.0, 0.45, 0.40), (0.55, 0.22, 1.0, 0.62)]),
    40: dict(name="Grand Finale", tee=(0.08, 0.52), cup=(0.92, 0.12), rects=[(0.30, 0.0, 0.34, 0.38)],
             circles=[(0.80, 0.45, 0.04)], water=[(0.50, 0.32, 0.62, 0.62)], ice=[(0.62, 0.0, 0.85, 0.30)],
             boost=[(0.36, 0.04, 0.48, 0.16, 1.6, 0.0)]),
}


def get_hole(hid: int) -> dict:
    """Hole 1-40; 101-140 is the same hole mirrored left to right."""
    base = HOLES.get(hid % 100, HOLES[1])
    if hid < 100:
        return base

    def fx(r):
        return (1 - r[2], r[1], 1 - r[0], r[3])
    out = dict(base, tee=(1 - base["tee"][0], base["tee"][1]), cup=(1 - base["cup"][0], base["cup"][1]),
               rects=[fx(r) for r in base["rects"]], circles=[(1 - c[0], c[1], c[2]) for c in base["circles"]])
    for key in ("sand", "ice", "water"):
        out[key] = [fx(r) for r in base.get(key, [])]
    out["boost"] = [(1 - b[2], b[1], 1 - b[0], b[3], -b[4], b[5]) for b in base.get("boost", [])]
    return out


def _inside(zones, x: float, y: float) -> bool:
    return any(z[0] <= x <= z[2] and z[1] <= y <= z[3] for z in zones)


def simulate(hole: dict, x: float, y: float, ang: float, pw: float):
    """Roll one shot. Returns (frames at 60 fps, final x, final y, holed). Same maths on every PC."""
    vx, vy = math.cos(ang) * pw * VMAX, math.sin(ang) * pw * VMAX
    dt = 1 / 240
    x0, y0 = x, y
    frames = [(x, y)]
    sand, ice, water, boost = hole.get("sand", []), hole.get("ice", []), hole.get("water", []), hole.get("boost", [])
    cx, cy = hole["cup"]
    r = BALL_R
    for step in range(240 * 14):
        x += vx * dt
        y += vy * dt
        if x < r:
            x, vx = r, abs(vx) * BOUNCE
        elif x > 1 - r:
            x, vx = 1 - r, -abs(vx) * BOUNCE
        if y < r:
            y, vy = r, abs(vy) * BOUNCE
        elif y > FIELD_H - r:
            y, vy = FIELD_H - r, -abs(vy) * BOUNCE
        for (x1, y1, x2, y2) in hole["rects"]:
            qx, qy = max(x1, min(x2, x)), max(y1, min(y2, y))
            dx, dy = x - qx, y - qy
            d = math.hypot(dx, dy)
            if d < r:
                if d < 1e-9:                                   # inside the wall: out the nearest side
                    sides = ((x - x1, -1, 0), (x2 - x, 1, 0), (y - y1, 0, -1), (y2 - y, 0, 1))
                    _dist, nx, ny = min(sides)
                    x, y = (x1 - r if nx < 0 else x2 + r) if nx else x, (y1 - r if ny < 0 else y2 + r) if ny else y
                else:
                    nx, ny = dx / d, dy / d
                    x, y = qx + nx * r, qy + ny * r
                vn = vx * nx + vy * ny
                if vn < 0:
                    vx -= (1 + BOUNCE) * vn * nx
                    vy -= (1 + BOUNCE) * vn * ny
        for (bx, by, br) in hole["circles"]:
            dx, dy = x - bx, y - by
            d = math.hypot(dx, dy)
            if d < br + r and d > 1e-9:
                nx, ny = dx / d, dy / d
                x, y = bx + nx * (br + r), by + ny * (br + r)
                vn = vx * nx + vy * ny
                if vn < 0:
                    vx -= (1 + 0.95) * vn * nx                 # bumpers kick back harder
                    vy -= (1 + 0.95) * vn * ny
        if water and _inside(water, x, y):                     # splash: back to where it was hit from
            frames.append((x, y))
            frames.append((x0, y0))
            return frames, x0, y0, False
        for (x1, y1, x2, y2, px_, py_) in boost:
            if x1 <= x <= x2 and y1 <= y <= y2:
                vx += px_ * dt * 4
                vy += py_ * dt * 4
        speed = math.hypot(vx, vy)
        dc = math.hypot(x - cx, y - cy)
        if dc < CUP_R * 2.2 and speed < 0.7:                   # the cup pulls a slow ball in a little
            pull = 1.6 * dt
            vx += (cx - x) / max(dc, 1e-6) * pull
            vy += (cy - y) / max(dc, 1e-6) * pull
        if dc < CUP_R and speed < 1.05:
            frames.append((cx, cy))
            return frames, cx, cy, True
        dec = (0.42 + speed * 0.55) * dt                        # grass: slows down, more when fast
        if sand and _inside(sand, x, y):
            dec *= 4.0
        elif ice and _inside(ice, x, y):
            dec *= 0.25
        if speed <= dec or speed < 0.004:
            break
        k = (speed - dec) / speed
        vx, vy = vx * k, vy * k
        if step % 4 == 3:
            frames.append((x, y))
    frames.append((x, y))
    return frames, x, y, False


def start_pos(hole: dict, side: str):
    tx, ty = hole["tee"]
    return (tx, ty - 0.022) if side == "a" else (tx, ty + 0.022)


class GolfView(QWidget):
    """The course, both balls, the scoreboard and the aim. Asks the server every 0.6 s while a match is on."""

    def __init__(self, page, gid: str, solo: bool = False) -> None:
        super().__init__()
        self.page, self.ctx, self.gid = page, page.ctx, gid
        self.solo = solo                     # 4.3: a round alone: no opponent, no clock, coins by strokes
        w = page.W
        self.head_h = S(46)
        self.setFixedSize(w, int(self.head_h + w * FIELD_H))
        self.g: dict = {}
        self.balls = {"a": None, "b": None}
        self.anim = None                     # (side, frames, i, then)
        self.anim_hole = 0
        self.seen = -1                       # last shot number shown
        self.aim = None                      # (press point, current point) in field units
        self.sending = False
        self._asking = False
        self._banner, self._banner_at = "", 0.0
        self._poll = QTimer(self)
        self._poll.setInterval(3000 if solo else 450)   # 4.0: the other player's shot shows sooner
        self._poll.timeout.connect(self.ask)
        self._frame = QTimer(self)
        self._frame.setInterval(16)
        self._frame.timeout.connect(self._step)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.ask()

    # -- server
    def showEvent(self, _e) -> None:
        self._poll.start()
        self._frame.start()

    def hideEvent(self, _e) -> None:
        self._poll.stop()
        self._frame.stop()

    def ask(self) -> None:
        if self._asking or self.anim is not None:
            return
        self._asking = True

        def got(ok: bool, data) -> None:
            self._asking = False
            if ok and isinstance(data, dict):
                self.set_state(data)
            elif not ok and "gone" in str(data).lower():
                self.ctx.golf_id = None
                self.ctx.golf_solo_id = None
                self.ctx.reload_page()
        self.ctx.online.ask("rb_golf_solo_state" if self.solo else "rb_golf_state", {"gid": self.gid}, got)

    def n_holes(self) -> int:
        return max(1, len(self.g.get("holes") or [1, 2, 3, 4, 5]))

    def hole(self, n: int = 0) -> dict:
        """The layout of hole n of this match; the current hole by default."""
        hs = list(self.g.get("holes") or [1, 2, 3, 4, 5])
        n = max(1, min(len(hs), int(n or self.g.get("hole") or 1)))
        return get_hole(int(hs[n - 1]) if len(hs) >= n else 1)

    def set_state(self, g: dict) -> None:
        self.g = g
        seen_hole = getattr(self, "_hole_was", None)
        self._hole_was = g.get("hole")
        if seen_hole is not None and seen_hole != g.get("hole") and g.get("state") == "live":
            self._banner, self._banner_at = tr("Hole {n} of {t}", n=g.get("hole"), t=self.n_holes()), time.monotonic()
            sfx.play("on")
        shots = sorted(g.get("shots") or [], key=lambda s: int(s.get("n") or 0))
        if self.seen < 0:                                    # just opened: no replay of old shots
            self.seen = int(g.get("seq") or 0) - 1
        new = [s for s in shots if int(s.get("n") or 0) > self.seen]
        if new and self.anim is None:
            s = new[0]
            self.seen = int(s["n"])
            if s.get("by") != g.get("me") or not getattr(self, "_mine_sent", False):
                frames, _x, _y, _in = simulate(self.hole(int(s.get("hole") or 0)), float(s["x0"]), float(s["y0"]),
                                               float(s["ang"]), float(s["pow"]))
                frames[-1] = (float(s["x"]), float(s["y"]))
                self.anim_hole = int(s.get("hole") or 0)
                self.anim = [s.get("by"), frames, 0, self._settle]
                return
        if not new:
            self.seen = max(self.seen, int(g.get("seq") or 0) - 1)
        self._settle()
        if g.get("state") == "done" and getattr(self, "_was", "") == "live":     # 4.3: also when our own shot ends it
            self._finished()
        self._was = g.get("state")

    def _settle(self) -> None:
        """Balls where the server says they are."""
        g = self.g
        h = self.hole()
        for side in ("a", "b"):
            pos = g.get("p" + side)
            if g.get(side + "_in"):
                self.balls[side] = None
            elif pos:
                self.balls[side] = (float(pos[0]), float(pos[1]))
            else:
                self.balls[side] = start_pos(h, side)
        self._mine_sent = False
        self.update()

    def _finished(self) -> None:
        g = self.g
        me = g.get("me")
        won = int(g.get("paid") or 0) > 0 if self.solo else g.get("winner") == me
        sfx.play("on" if won else "off")
        self.ctx.golf_list = None
        if self.solo:
            self.ctx.econ.refresh()
            QTimer.singleShot(400, lambda: self.ctx.reload_page("games"))     # the Play again button shows
        self.update()

    # -- playing
    def my_turn(self) -> bool:
        g = self.g
        return (g.get("state") == "live" and g.get("turn") == g.get("me") and self.anim is None and not self.sending
                and not g.get(str(g.get("me")) + "_in"))

    def field(self) -> QRectF:
        return QRectF(0, self.head_h, self.width(), self.width() * FIELD_H)

    def to_field(self, pt) -> tuple:
        f = self.field()
        return ((pt.x() - f.left()) / f.width(), (pt.y() - f.top()) / f.width())

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.my_turn():
            p = self.to_field(e.position())
            self.aim = (p, p)
            self.update()

    def mouseMoveEvent(self, e) -> None:
        if self.aim is not None:
            self.aim = (self.aim[0], self.to_field(e.position()))
            self.update()

    def _shot(self):
        (px, py), (qx, qy) = self.aim
        dx, dy = px - qx, py - qy                            # pull back: the ball goes the other way
        pw = min(1.0, math.hypot(dx, dy) / 0.32)
        return math.atan2(dy, dx), pw

    def mouseReleaseEvent(self, e) -> None:
        if self.aim is None:
            return
        ang, pw = self._shot()
        self.aim = None
        me = self.g.get("me")
        ball = self.balls.get(me)
        if pw < 0.04 or not self.my_turn() or ball is None:
            return self.update()
        frames, x, y, holed = simulate(self.hole(), ball[0], ball[1], ang, pw)
        x, y = round(x, 4), round(y, 4)
        n = int(self.g.get("seq") or 0)
        self.sending, self._mine_sent = True, True
        self.seen = n
        sfx.play("pick")
        self.anim_hole = int(self.g.get("hole") or 1)
        self.anim = [me, frames, 0, self._settle]

        def done(ok: bool, data) -> None:
            self.sending = False
            if ok and isinstance(data, dict):
                self.g = data if self.anim is None else dict(data, _wait=True)
                if self.anim is None:
                    self.set_state(data)
            else:
                self.ctx.toast(tr(str(data)), "warn")
                self._mine_sent = False
                self.ask()
        if self.solo:
            return self.ctx.online.ask("rb_golf_solo_shot", {"gid": self.gid, "n": n, "x": x, "y": y, "holed": holed}, done)
        self.ctx.online.ask("rb_golf_shot", {"gid": self.gid, "n": n, "x0": ball[0], "y0": ball[1], "ang": ang,
                                             "pow": pw, "x": x, "y": y, "holed": holed}, done)

    def _step(self) -> None:
        if self.anim is not None:
            side, frames, i, then = self.anim
            i += 2 if len(frames) > 400 else 1
            if i >= len(frames) - 1:
                last = frames[-1]
                self.anim = None
                self.balls[side] = last
                cup = self.hole(self.anim_hole)["cup"]
                if math.hypot(last[0] - cup[0], last[1] - cup[1]) < 1e-3:
                    sfx.play("on")
                g = self.g
                more = any(int(s.get("n") or 0) > self.seen for s in g.get("shots") or [])
                if g.pop("_wait", None) or more:          # 4.0: shots that came in meanwhile play in order
                    self.set_state(g)
                else:
                    then()
                    self.ask()
            else:
                self.anim[2] = i
                self.balls[side] = frames[i]
            return self.update()
        # 4.0: nothing moves: no full repaint 60 times a second (the course is costly to draw). The aim line,
        # the hole banner and the turn clock still repaint when they change.
        now = time.monotonic()
        clock = int(now * 4)
        if self.aim is not None or now - self._banner_at < 2.5 or clock != getattr(self, "_clock", -1):
            self._clock = clock
            self.update()

    # -- drawing
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = self.g
        h = self.hole(self.anim_hole) if self.anim is not None else self.hole()
        now = time.monotonic()
        self._paint_head(p, g)
        f = self.field()
        u = f.width()

        def P(x, y):
            return QPointF(f.left() + x * u, f.top() + y * u)
        clip = QPainterPath()
        clip.addRoundedRect(f, S(10), S(10))
        p.save()
        p.setClipPath(clip)
        grass = QLinearGradient(f.topLeft(), f.bottomRight())
        grass.setColorAt(0, QColor("#2E9E4F"))
        grass.setColorAt(1, QColor("#1E7A3B"))
        p.fillRect(f, grass)
        p.setPen(Qt.PenStyle.NoPen)
        for k in range(0, 12, 2):                            # mowed stripes
            p.fillRect(QRectF(f.left() + k * u / 12, f.top(), u / 12, f.height()), alpha("#FFFFFF", 0.035))
        for (x1, y1, x2, y2) in h.get("sand", []):
            p.setBrush(QColor("#E3C88A"))
            p.drawRoundedRect(QRectF(P(x1, y1), P(x2, y2)), S(10), S(10))
        for (x1, y1, x2, y2) in h.get("ice", []):
            p.setBrush(alpha("#CFF4FF", 0.55))
            p.drawRoundedRect(QRectF(P(x1, y1), P(x2, y2)), S(6), S(6))
        for (x1, y1, x2, y2) in h.get("water", []):
            wr = QRectF(P(x1, y1), P(x2, y2))
            wg = QLinearGradient(wr.topLeft(), wr.bottomRight())
            wg.setColorAt(0, QColor("#2E7CF6"))
            wg.setColorAt(1, QColor("#14489E"))
            p.setBrush(wg)
            p.drawRoundedRect(wr, S(8), S(8))
        for (x1, y1, x2, y2, px_, py_) in h.get("boost", []):
            br = QRectF(P(x1, y1), P(x2, y2))
            p.setBrush(alpha("#FFB627", 0.35))
            p.drawRoundedRect(br, S(6), S(6))
            ang_ = math.atan2(py_, px_)
            p.setPen(QPen(QColor("#FFD36B"), S(2.5), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for k in range(3):
                t_ = ((now * 1.5 + k / 3) % 1.0) - 0.5
                m_ = min(br.width(), br.height()) * 0.8
                c_ = br.center() + QPointF(math.cos(ang_) * t_ * m_, math.sin(ang_) * t_ * m_)
                for sgn in (-1, 1):
                    p.drawLine(c_, c_ - QPointF(math.cos(ang_ + sgn * 0.6) * S(7), math.sin(ang_ + sgn * 0.6) * S(7)))
            p.setPen(Qt.PenStyle.NoPen)
        wood = QColor("#6B4423")
        for (x1, y1, x2, y2) in h["rects"]:
            r = QRectF(P(x1, y1), P(x2, y2))
            p.setBrush(wood)
            p.drawRoundedRect(r, S(3), S(3))
            p.setBrush(alpha("#FFFFFF", 0.12))
            p.drawRect(QRectF(r.left(), r.top(), r.width(), min(r.height(), S(3))))
        for (bx, by, br) in h["circles"]:
            glow = QRadialGradient(P(bx, by), br * u)
            glow.setColorAt(0, QColor("#FF7AD9"))
            glow.setColorAt(1, QColor("#9B2C7E"))
            p.setBrush(glow)
            p.drawEllipse(P(bx, by), br * u, br * u)
        cx, cy = h["cup"]
        p.setBrush(QColor("#0B120D"))
        p.drawEllipse(P(cx, cy), CUP_R * u, CUP_R * u)
        p.setPen(QPen(QColor("#EDEDED"), S(1.5)))
        top = P(cx, cy) - QPointF(0, S(30))
        p.drawLine(P(cx, cy), top)
        flag = QPainterPath(top)
        wave = math.sin(now * 3) * S(2)
        flag.lineTo(top + QPointF(S(16), S(5) + wave))
        flag.lineTo(top + QPointF(0, S(10)))
        flag.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FF4B4B"))
        p.drawPath(flag)
        tx, ty = h["tee"]
        p.setBrush(alpha("#FFFFFF", 0.12))
        p.drawRoundedRect(QRectF(P(tx - 0.03, ty - 0.05), P(tx + 0.03, ty + 0.05)), S(4), S(4))
        me = g.get("me", "a")
        if self.aim is not None and self.balls.get(me):        # aim line and power
            ang, pw = self._shot()
            bx, by = self.balls[me]
            end = P(bx + math.cos(ang) * (0.05 + 0.25 * pw), by + math.sin(ang) * (0.05 + 0.25 * pw))
            col = QColor.fromHsvF(max(0.0, 0.33 - 0.33 * pw), 0.85, 1.0)
            p.setPen(QPen(col, S(3), Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(P(bx, by), end)
        for side in ("a", "b"):
            pos = self.balls.get(side)
            if pos is None:
                continue
            c = P(*pos)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha("#000000", 0.3))
            p.drawEllipse(c + QPointF(S(1.5), S(2)), BALL_R * u, BALL_R * u)
            ring = ui.accent if side == me else QColor("#FFB627")
            p.setBrush(QColor("#FFFFFF"))
            p.setPen(QPen(ring, S(2.5)))
            p.drawEllipse(c, BALL_R * u, BALL_R * u)
        if self._banner and now - self._banner_at < 2.0:
            a = min(1.0, 2.0 - (now - self._banner_at))
            p.setOpacity(a)
            p.fillRect(QRectF(f.left(), f.center().y() - S(22), f.width(), S(44)), alpha("#000000", 0.55))
            p.setPen(QColor("#FFFFFF"))
            p.setFont(font(16, QFont.Weight.Black))
            p.drawText(f, int(Qt.AlignmentFlag.AlignCenter), self._banner)
            p.setOpacity(1.0)
        if g.get("state") == "done" and self.solo:
            p.fillRect(f, alpha("#000000", 0.6))
            paid = int(g.get("paid") or 0)
            total = sum(int(x or 0) for x in (g.get("a_strokes") or []))
            p.setPen(QColor("#FFFFFF"))
            p.setFont(font(20, QFont.Weight.Black))
            p.drawText(QRectF(f.left(), f.center().y() - S(34), f.width(), S(30)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("Round over: {n} strokes", n=total))
            p.setFont(font(13, QFont.Weight.Bold))
            p.setPen(QColor("#E8C26A") if paid else QColor(TEXT_DIM))
            p.drawText(QRectF(f.left(), f.center().y() + S(2), f.width(), S(24)), int(Qt.AlignmentFlag.AlignCenter),
                       ("+" + coins_text(paid) + " " + tr("coins")) if paid else tr("No coins this time (limit reached)"))
        elif g.get("state") == "done":
            p.fillRect(f, alpha("#000000", 0.6))
            won, draw = g.get("winner") == me, not g.get("winner")
            p.setPen(QColor("#3DDC84") if won else QColor("#FFFFFF"))
            p.setFont(font(20, QFont.Weight.Black))
            text = tr("Draw") if draw else (tr("You win!") if won else tr("{name} wins", name=g.get("b" if me == "a" else "a")))
            p.drawText(QRectF(f.left(), f.center().y() - S(30), f.width(), S(30)), int(Qt.AlignmentFlag.AlignCenter), text)
            bet = int(g.get("bet") or 0)
            if bet:
                p.setFont(font(12, QFont.Weight.Bold))
                p.setPen(QColor(TEXT))
                sub = (tr("Bets refunded") if draw else
                       ("+" + coins_text(int(bet * 2 * 0.95)) if won else "−" + coins_text(bet)))
                p.drawText(QRectF(f.left(), f.center().y() + S(4), f.width(), S(22)), int(Qt.AlignmentFlag.AlignCenter), sub)
        p.restore()

    def _paint_head(self, p: QPainter, g: dict) -> None:
        r = QRectF(0, 0, self.width(), self.head_h - S(6))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.05))
        p.drawRoundedRect(r, S(10), S(10))
        if self.solo:
            return self._paint_solo_head(p, g, r)
        me = g.get("me", "a")
        hole = int(g.get("hole") or 1)
        w = r.width() / 3
        for i, side in enumerate(("a", "b")):
            box = QRectF(r.left() + (0 if i == 0 else 2 * w), r.top(), w, r.height())
            strokes = list(g.get(side + "_strokes") or [0])
            active = g.get("state") == "live" and g.get("turn") == side
            p.setPen(ui.accent if side == me else QColor("#FFB627"))
            p.setFont(font(11, QFont.Weight.Bold))
            name = str(g.get(side) or "?")
            p.drawText(box.adjusted(S(8), S(3), -S(8), -r.height() / 2), int(Qt.AlignmentFlag.AlignVCenter |
                       (Qt.AlignmentFlag.AlignLeft if i == 0 else Qt.AlignmentFlag.AlignRight)), ("● " if active and i == 0 else "")
                       + name + (" ●" if active and i == 1 else ""))
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(10, QFont.Weight.DemiBold))
            p.drawText(box.adjusted(S(8), r.height() / 2, -S(8), -S(3)), int(Qt.AlignmentFlag.AlignVCenter |
                       (Qt.AlignmentFlag.AlignLeft if i == 0 else Qt.AlignmentFlag.AlignRight)),
                       (lambda n: tr("1 stroke") if n == 1 else tr("{n} strokes", n=n))(sum(int(x or 0) for x in strokes)))
        mid = QRectF(r.left() + w, r.top(), w, r.height())
        p.setPen(QColor(TEXT))
        p.setFont(font(11, QFont.Weight.Black))
        p.drawText(mid.adjusted(0, S(3), 0, -r.height() / 2), int(Qt.AlignmentFlag.AlignCenter),
                   tr("Hole {n} of {t}", n=hole, t=self.n_holes()) if g.get("state") == "live" else tr("Final score"))
        p.setFont(font(10, QFont.Weight.DemiBold))
        if g.get("state") == "live":
            left = max(0, int(float(g.get("left") or 0)))
            mine = g.get("turn") == me
            p.setPen(QColor("#3DDC84") if mine else QColor(TEXT_DIM))
            text = tr("Your turn · {s} s", s=left) if mine else tr("Waiting · {s} s", s=left)
            p.drawText(mid.adjusted(0, r.height() / 2, 0, -S(3)), int(Qt.AlignmentFlag.AlignCenter), text)


    SOLO_PAYS = (60, 35, 20, 10, 5, 0)

    def _paint_solo_head(self, p: QPainter, g: dict, r: QRectF) -> None:
        """4.3 solo: your strokes, the hole, and what holing the next shot pays."""
        w = r.width() / 3
        hole = int(g.get("hole") or 1)
        strokes = list(g.get("a_strokes") or [0])
        left, mid, right = (QRectF(r.left() + i * w, r.top(), w, r.height()) for i in range(3))
        top_half = lambda b: b.adjusted(S(8), S(3), -S(8), -r.height() / 2)
        low_half = lambda b: b.adjusted(S(8), r.height() / 2, -S(8), -S(3))
        p.setPen(ui.accent)
        p.setFont(font(11, QFont.Weight.Bold))
        p.drawText(top_half(left), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), str(g.get("a") or ""))
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10, QFont.Weight.DemiBold))
        n = sum(int(x or 0) for x in strokes)
        p.drawText(low_half(left), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                   tr("1 stroke") if n == 1 else tr("{n} strokes", n=n))
        p.setPen(QColor(TEXT))
        p.setFont(font(11, QFont.Weight.Black))
        p.drawText(top_half(mid), int(Qt.AlignmentFlag.AlignCenter),
                   tr("Hole {n} of {t}", n=hole, t=self.n_holes()) if g.get("state") == "live" else tr("Final score"))
        p.setPen(QColor("#3DDC84"))
        p.setFont(font(10, QFont.Weight.DemiBold))
        if g.get("state") == "live":
            p.drawText(low_half(mid), int(Qt.AlignmentFlag.AlignCenter), tr("Solo · no clock"))
            now_s = int(strokes[hole - 1] if len(strokes) >= hole else 0)
            pays = self.SOLO_PAYS[min(5, now_s)]
            p.setPen(QColor(TEXT_DIM))
            p.drawText(top_half(right), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), tr("Hole it now"))
            p.setPen(QColor("#E8C26A") if pays else QColor(TEXT_DIM))
            p.setFont(font(11, QFont.Weight.Bold))
            p.drawText(low_half(right), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), "+" + coins_text(pays))


class LobbyRow(QWidget):
    """One open lobby: who opened it, the bet, how long it stays, and Join (or Close for your own)."""

    def __init__(self, page, m: dict) -> None:
        super().__init__()
        self.m = m
        self.setFixedHeight(S(50))
        lay = hbox(self, 6)
        lay.setContentsMargins(S(10), 0, S(6), 0)
        bet = int(m.get("bet") or 0)
        name = Label(str(m.get("host", "?")), 12, TEXT, bold=True)
        name.setFixedWidth(name.text_width() + S(8))
        lay.addWidget(name)
        lay.addWidget(Label((coins_text(bet) + " " + tr("coins")) if bet else tr("No bet"), 10.5, "#E8C26A" if bet else TEXT_DIM), 1)
        if m.get("mine"):
            b = Button(tr("Close"), "ghost", 30)
            b.clicked.connect(lambda: golf_cancel(page, m["id"]))
        else:
            b = Button(tr("Join"), "primary", 30)
            b.clicked.connect(lambda: golf_join(page, m))
        lay.addWidget(b)
        self._t0, self._left = time.monotonic(), int(m.get("left") or 0)
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self.update)
        self._tick.start()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha(ui.accent, 0.5), 1.2) if self.m.get("mine") else Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.05))
        p.drawRoundedRect(r, S(10), S(10))
        left = max(0, self._left - int(time.monotonic() - self._t0))
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(9.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(r.left() + S(10), r.bottom() - S(15), r.width() * 0.5, S(13)), int(Qt.AlignmentFlag.AlignVCenter),
                   tr("Closes in {t}", t=f"{left // 60}:{left % 60:02d}"))


class GolfRow(QWidget):
    """One match of your history: who, the bet and the score."""

    def __init__(self, page, m: dict) -> None:
        super().__init__()
        self.setFixedHeight(S(44))
        lay = hbox(self, 6)
        lay.setContentsMargins(S(10), 0, S(6), 0)
        bet = int(m.get("bet") or 0)
        title = tr("vs {name}", name=m.get("other") or "?") + ("  ·  " + coins_text(bet) if bet else "")
        state = m.get("state")
        if state == "live":
            sub = tr("Live now")
        elif state == "done":
            sub = (tr("Draw") if m.get("draw") else tr("Won") if m.get("won") else tr("Lost")) + \
                  f"  ·  {m.get('me_total', 0)} – {m.get('other_total', 0)}"
        else:
            sub = tr("Cancelled")
        name = Label(title, 11.5, TEXT, bold=True)
        name.setFixedWidth(name.text_width() + S(8))
        lay.addWidget(name)
        lay.addWidget(Label(sub, 10.5, "#3DDC84" if state == "live" or m.get("won") else TEXT_DIM), 1)
        if state == "live":
            go = Button(tr("Open"), "primary", 28)
            go.clicked.connect(lambda: golf_open(page, m["id"]))
            lay.addWidget(go)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.035))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), S(10), S(10))


def golf_open(page, gid: str) -> None:
    page.ctx.golf_id = gid
    sfx.play("on")
    page.ctx.reload_page()


def golf_cancel(page, gid: str) -> None:
    ctx = page.ctx

    def done(ok: bool, data) -> None:
        if not ok:
            return ctx.toast(tr(str(data)), "warn")
        sfx.play("off")
        ctx.econ.refresh()
        ctx.golf_lobby = None
        load_golf(page)
    ctx.econ.call("rb_golf_cancel", {"gid": gid}, done)


def golf_join(page, m: dict) -> None:
    ctx = page.ctx
    bet = int(m.get("bet") or 0)
    if bet > ctx.econ.coins:
        return ctx.toast(tr("Not enough coins"), "warn")

    def done(ok: bool, data) -> None:
        if not ok:
            ctx.golf_lobby = None
            load_golf(page)
            return ctx.toast(tr(str(data)), "warn")
        ctx.econ.refresh()
        golf_open(page, m["id"])

    def go() -> None:
        ctx.econ.call("rb_golf_join", {"gid": m["id"]}, done)
    if bet:
        ctx.window.confirm(tr("Join {name}'s match for {n} coins?", name=m.get("host", "?"), n=coins_text(bet)), go,
                           yes=tr("Join"))
    else:
        go()


def load_golf(page) -> None:
    """The lobby (asked every 2 seconds while the screen is open). Your own match going live opens it."""
    ctx = page.ctx

    def got(ok: bool, data) -> None:
        if not ok:
            if "soon" in str(data).lower():
                ctx.golf_missing = True
                if ctx.window.showing("games") and getattr(ctx, "games_sub", None) == "duels":
                    ctx.reload_page("games")
            return
        if not isinstance(data, dict):
            return
        ctx.golf_missing = False
        old = getattr(ctx, "golf_lobby", None)
        live = data.get("live")
        if live and not getattr(ctx, "golf_id", None) and (old is None or old.get("live") != live):
            ctx.golf_id = live                               # somebody joined your lobby: straight in
            ctx.golf_lobby = data
            sfx.play("on")
            if ctx.window.showing("games") and getattr(ctx, "games_sub", None) == "duels":
                ctx.reload_page("games")
            return
        if data != old:
            ctx.golf_lobby = data
            if ctx.window.showing("games") and getattr(ctx, "games_sub", None) == "duels" and not getattr(ctx, "golf_id", None):
                ctx.reload_page("games")
    ctx.online.ask("rb_golf_lobbies", {}, got)


def build_golf_solo(page, lay, sid, leave_screen) -> None:
    """4.3: Mini Golf alone. No bet and no clock: coins by strokes, paid at the end of the round."""
    from .shop import CoinBar
    ctx = page.ctx

    def start() -> None:
        def done(ok: bool, data) -> None:
            if not ok:
                return ctx.toast(tr(str(data)), "warn")
            sfx.play("on")
            ctx.golf_solo_id = data.get("id")
            ctx.reload_page("games")
        ctx.econ.call("rb_golf_solo_start", {}, done)
    if sid:
        view = GolfView(page, sid, solo=True)
        lay.addWidget(view)
        if view.g.get("state") == "done" or getattr(ctx, "golf_solo_done", None) == sid:
            row = hbox(spacing=6)
            again = Button(tr("Play again"), "primary", 34, icon="flag")
            again.clicked.connect(start)
            out = Button(tr("Back"), "ghost", 34)
            out.clicked.connect(leave_screen)
            row.addWidget(again, 2)
            row.addWidget(out, 1)
            lay.addLayout(row)
        else:
            quit_ = Button(tr("Leave the round"), "ghost", 30)

            def leave() -> None:
                if view.g.get("state") != "live":
                    return leave_screen()

                def go() -> None:
                    ctx.online.ask("rb_golf_solo_quit", {"gid": sid}, lambda _o, _d: None)
                    leave_screen()
                ctx.window.confirm(tr("Leave? This round pays nothing."), go, yes=tr("Leave"))
            quit_.clicked.connect(leave)
            lay.addWidget(quit_)

        def watch(g=None) -> None:                       # the round ends: Play again replaces Leave
            if view.g.get("state") == "done" and getattr(ctx, "golf_solo_done", None) != sid:
                ctx.golf_solo_done = sid
        old = view.set_state

        def set_state(g: dict) -> None:
            old(g)
            watch()
        view.set_state = set_state
        lay.addWidget(Label(tr("Drag back anywhere, then let go to shoot. Holing it sooner pays more."),
                            10, TEXT_DIM, wrap_w=page.W))
        return
    lay.addWidget(CoinBar(ctx))
    lay.addWidget(Label(tr("PLAY ALONE"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
    go = Button(tr("Start a round"), "primary", 36, icon="flag")
    go.clicked.connect(start)
    lay.addWidget(go)
    holes = int(float(ctx.econ.cfg.get("golf_holes", 5) or 5))
    lay.addWidget(Label(tr("{n} holes, no bet and no clock. Each hole pays by strokes:", n=holes), 10.5, TEXT, wrap_w=page.W))
    lay.addWidget(Label(tr("1 stroke: 60 · 2: 35 · 3: 20 · 4: 10 · 5: 5 · 6: nothing"), 11, "#E8C26A", bold=True,
                        wrap_w=page.W))
    lay.addWidget(Label(tr("Coins are paid at the end of the round. Like the other mini games, what you can earn is "
                           "limited every 2 hours."), 10, TEXT_DIM, wrap_w=page.W))
    lay.addWidget(Label(tr("Want to bet against someone? Pick Duel above."), 10, TEXT_DIM, wrap_w=page.W))


class _ListPoll(QWidget):
    """Invisible: refreshes the lobby while the golf screen is shown."""

    def __init__(self, page) -> None:
        super().__init__()
        self.page = page
        self.setFixedHeight(0)
        self._t = QTimer(self)
        self._t.setInterval(2000)
        self._t.timeout.connect(lambda: load_golf(page))

    def showEvent(self, _e) -> None:
        load_golf(self.page)
        self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()


def build_golf(page, lay) -> None:
    """Mini golf 1 v 1: a live match, or the lobby (open a match, or join one)."""
    from .hub import server_wait
    from .shop import CoinBar
    ctx = page.ctx
    top = hbox(spacing=8)
    gid = getattr(ctx, "golf_id", None)
    solo = bool(getattr(ctx, "golf_solo", False)) and not gid       # 4.3: Solo or Duel
    sid = getattr(ctx, "golf_solo_id", None) if solo else None
    back = IconButton("back", 32, tip=tr("Back"))

    def leave_screen() -> None:
        if gid or sid:
            ctx.golf_id = None
            ctx.golf_solo_id = None
            ctx.golf_lobby = None
            return ctx.reload_page("games")
        page.open_sub(None)
    back.clicked.connect(leave_screen)
    top.addWidget(back)
    top.addWidget(Label(tr("Mini Golf"), 16, bold=True), 1)
    from .gamehelp import HelpButton
    top.addWidget(HelpButton(ctx, "golf"))
    duel = Label(tr("SOLO") if solo else tr("DUEL"), 10, "#3DDC84", bold=True)
    duel.fit()
    top.addWidget(duel)
    lay.addLayout(top)
    if getattr(ctx, "golf_missing", False):
        server_wait(ctx, lay, page.W)
        return
    if not gid and not sid:
        which = Segmented([tr("Solo"), tr("Duel")], 0 if solo else 1)

        def pick(i: int) -> None:
            ctx.golf_solo = i == 0
            sfx.play("pick")
            ctx.reload_page("games")
        which.changed.connect(pick)
        lay.addWidget(which)
    if solo:
        return build_golf_solo(page, lay, sid, leave_screen)
    if gid:
        view = GolfView(page, gid)
        lay.addWidget(view)
        quit_ = Button(tr("Leave the match"), "ghost", 30)

        def leave() -> None:
            def done(_ok, _d) -> None:
                ctx.econ.refresh()
                view.ask()
            if view.g.get("state") != "live":
                return leave_screen()
            ctx.window.confirm(tr("Leave? The other player wins the match."),
                               lambda: ctx.online.ask("rb_golf_leave", {"gid": gid}, done), yes=tr("Leave"))
        quit_.clicked.connect(leave)
        lay.addWidget(quit_)
        lay.addWidget(Label(tr("Drag back anywhere, then let go to shoot. {n} holes, 25 seconds a turn. Fewest strokes wins.",
                               n=view.n_holes() if view.g else int(float(ctx.econ.cfg.get("golf_holes", 5) or 5))),
                            10, TEXT_DIM, wrap_w=page.W))
        return
    lay.addWidget(CoinBar(ctx))
    lay.addWidget(_ListPoll(page))
    data = getattr(ctx, "golf_lobby", None)
    if data is None:
        lay.addWidget(Label(tr("Loading…"), 11, TEXT_DIM))
        return
    lobbies = list(data.get("lobbies") or [])
    mine = next((m for m in lobbies if m.get("mine")), None)
    holes = int(data.get("holes") or 5)
    if mine is None:
        lay.addWidget(Label(tr("OPEN A MATCH"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
        cap = int(data.get("cap") or 0)
        mode = Segmented([tr("Bet"), tr("No bet")], 1 if getattr(ctx, "duel_nobet", False) or cap < 10 else 0)
        lay.addWidget(mode)
        amount = None
        if cap >= 10:
            start = max(10, min(cap, int(getattr(ctx, "duel_amount", 0) or 100)))
            amount = SliderRow(tr("Bet"), 10, cap, start, 10, start, lambda v: coins_text(int(v)), label_w=60)
            amount._val.setFixedWidth(S(78))
            amount.changed.connect(lambda v: setattr(ctx, "duel_amount", int(v)))
            amount.setVisible(mode.index() == 0)
            lay.addWidget(amount)

        def on_mode(i: int) -> None:
            if cap < 10:
                return mode.set_index(1)
            ctx.duel_nobet = i == 1
            if amount is not None:
                amount.setVisible(i == 0)
        mode.changed.connect(on_mode)
        make = Button(tr("Open a match"), "primary", 36, icon="flag")

        def create() -> None:
            bet = 0 if amount is None or getattr(ctx, "duel_nobet", False) else int(amount.value())
            bet = 0 if bet < 10 else bet - bet % 10
            if bet > ctx.econ.coins:
                return ctx.toast(tr("Not enough coins"), "warn")

            def done(ok: bool, d) -> None:
                if not ok:
                    return ctx.toast(tr(str(d)), "warn")
                sfx.play("on")
                ctx.toast(tr("Match open: waiting for a player"))
                ctx.econ.refresh()
                ctx.golf_lobby = None
                load_golf(page)
            ctx.econ.call("rb_golf_create", {"bet": bet}, done)
        make.clicked.connect(create)
        lay.addWidget(make)
        lay.addWidget(Label(tr("{n} holes. The winner gets both bets (5% fee). Closes after 5 minutes if nobody joins.", n=holes),
                            10, TEXT_DIM, wrap_w=page.W))
    else:
        lay.addWidget(Label(tr("YOUR MATCH"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
        lay.addWidget(LobbyRow(page, mine))
        lay.addWidget(Label(tr("Waiting for a player. It starts as soon as someone joins."), 10.5, TEXT_DIM, wrap_w=page.W))
    others = [m for m in lobbies if not m.get("mine")]
    lay.addWidget(Label(tr("OPEN MATCHES"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
    if not others:
        lay.addWidget(Label(tr("No open match right now. Open one!"), 11, TEXT_DIM, wrap_w=page.W))
    for m in others[:12]:
        lay.addWidget(LobbyRow(page, m))
    hist = list(data.get("history") or [])
    if hist:
        lay.addWidget(Label(tr("YOUR LAST MATCHES"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
        for m in hist[:6]:
            lay.addWidget(GolfRow(page, m))
