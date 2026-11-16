"""3.0.0: live 1 v 1 mini golf between friends (it replaces duels).

Both players see the same course. They take turns: drag back from anywhere, let go to shoot. Every shot is sent to
the server with where the ball stopped; the other player sees it roll a moment later. 3 holes, at most 6 strokes a
hole, 25 seconds a turn. Fewest strokes wins the bet (5% fee); a draw gives both bets back."""
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
}


def simulate(hole: dict, x: float, y: float, ang: float, pw: float):
    """Roll one shot. Returns (frames at 60 fps, final x, final y, holed). Same maths on every PC."""
    vx, vy = math.cos(ang) * pw * VMAX, math.sin(ang) * pw * VMAX
    dt = 1 / 240
    frames = [(x, y)]
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

    def __init__(self, page, gid: str) -> None:
        super().__init__()
        self.page, self.ctx, self.gid = page, page.ctx, gid
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
        self._poll.setInterval(600)
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
                self.ctx.reload_page()
        self.ctx.online.ask("rb_golf_state", {"gid": self.gid}, got)

    def hole(self, n: int = 0) -> dict:
        """The layout of hole n (1-3) of this match; the current hole by default."""
        hs = list(self.g.get("holes") or [1, 2, 3])
        n = max(1, min(3, int(n or self.g.get("hole") or 1)))
        return HOLES.get(int(hs[n - 1]) if len(hs) >= n else 1, HOLES[1])

    def set_state(self, g: dict) -> None:
        old = self.g
        self.g = g
        if old and old.get("hole") != g.get("hole") and g.get("state") == "live":
            self._banner, self._banner_at = tr("Hole {n} of 3", n=g.get("hole")), time.monotonic()
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
        if g.get("state") == "done" and old.get("state") == "live":
            self._finished()

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
        won = g.get("winner") == me
        sfx.play("on" if won else "off")
        self.ctx.golf_list = None
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
                if g.pop("_wait", None):
                    self.set_state(g)
                else:
                    then()
                    self.ask()
            else:
                self.anim[2] = i
                self.balls[side] = frames[i]
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
        if g.get("state") == "done":
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
        me = g.get("me", "a")
        hole = int(g.get("hole") or 1)
        w = r.width() / 3
        for i, side in enumerate(("a", "b")):
            box = QRectF(r.left() + (0 if i == 0 else 2 * w), r.top(), w, r.height())
            strokes = list(g.get(side + "_strokes") or [0, 0, 0])
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
                   tr("Hole {n} of 3", n=hole) if g.get("state") == "live" else tr("Final score"))
        p.setFont(font(10, QFont.Weight.DemiBold))
        if g.get("state") == "live":
            left = max(0, int(float(g.get("left") or 0)))
            mine = g.get("turn") == me
            p.setPen(QColor("#3DDC84") if mine else QColor(TEXT_DIM))
            text = tr("Your turn · {s} s", s=left) if mine else tr("Waiting · {s} s", s=left)
            p.drawText(mid.adjusted(0, r.height() / 2, 0, -S(3)), int(Qt.AlignmentFlag.AlignCenter), text)


def golf_limit(ctx, name: str) -> int:
    from .games2 import duel_limit
    return duel_limit(ctx, name)


class GolfRow(QWidget):
    """One match in the list: who, the bet, and what can be done now."""

    def __init__(self, page, m: dict) -> None:
        super().__init__()
        self.setFixedHeight(S(52))
        lay = hbox(self, 6)
        lay.setContentsMargins(S(10), 0, S(6), 0)
        bet = int(m.get("bet") or 0)
        title = tr("vs {name}", name=m.get("other", "?")) + ("  ·  " + coins_text(bet) if bet else "")
        state = m.get("state")
        if state == "asked":
            sub = tr("They challenge you!") if m.get("asked_me") else tr("Waiting for an answer")
        elif state == "live":
            sub = tr("Live now")
        elif state == "done":
            sub = (tr("Draw") if m.get("draw") else tr("Won") if m.get("won") else tr("Lost")) + \
                  f"  ·  {m.get('me_total', 0)} – {m.get('other_total', 0)}"
        else:
            sub = tr("Cancelled")
        name = Label(title, 12, TEXT, bold=True)
        name.setFixedWidth(name.text_width() + S(8))
        lay.addWidget(name)
        lay.addWidget(Label(sub, 10.5, "#3DDC84" if state == "live" or m.get("won") else TEXT_DIM), 1)
        if state == "asked" and m.get("asked_me"):
            yes, no = Button(tr("Play"), "primary", 30), Button(tr("Decline"), "ghost", 30)
            yes.clicked.connect(lambda: golf_answer(page, m["id"], True))
            no.clicked.connect(lambda: golf_answer(page, m["id"], False))
            lay.addWidget(yes)
            lay.addWidget(no)
        elif state == "asked":
            back = Button(tr("Cancel"), "ghost", 30)
            back.clicked.connect(lambda: golf_answer(page, m["id"], False))
            lay.addWidget(back)
        elif state == "live":
            go = Button(tr("Open"), "primary", 30)
            go.clicked.connect(lambda: golf_open(page, m["id"]))
            lay.addWidget(go)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.05))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), S(10), S(10))


def golf_open(page, gid: str) -> None:
    page.ctx.golf_id = gid
    sfx.play("on")
    page.ctx.reload_page()


def golf_answer(page, gid: str, yes: bool) -> None:
    ctx = page.ctx

    def done(ok: bool, data) -> None:
        if not ok:
            return ctx.toast(tr(str(data)), "warn")
        ctx.econ.refresh()
        ctx.golf_list = None
        if yes and isinstance(data, dict) and data.get("state") == "live":
            return golf_open(page, gid)
        sfx.play("off")
        ctx.reload_page()
    ctx.econ.call("rb_golf_answer", {"gid": gid, "yes": yes}, done)


def load_golf(page) -> None:
    """The match list (asked every 2 seconds while the screen is open). A match that just went live opens."""
    ctx = page.ctx

    def got(ok: bool, data) -> None:
        if not ok:
            if "soon" in str(data).lower():
                ctx.golf_missing = True
                if ctx.window.current == "games" and getattr(ctx, "games_sub", None) == "duels":
                    ctx.reload_page()
            return
        if not isinstance(data, list):
            return
        ctx.golf_missing = False
        old = getattr(ctx, "golf_list", None)
        live = next((m for m in data if m.get("state") == "live"), None)
        if live and not getattr(ctx, "golf_id", None) and (old is None or not any(
                o.get("id") == live["id"] and o.get("state") == "live" for o in old)):
            ctx.golf_id = live["id"]                         # your friend just said yes: straight in
            ctx.golf_list = data
            sfx.play("on")
            if ctx.window.current == "games" and getattr(ctx, "games_sub", None) == "duels":
                ctx.reload_page()
            return
        if data != old:
            ctx.golf_list = data
            if ctx.window.current == "games" and getattr(ctx, "games_sub", None) == "duels" and not getattr(ctx, "golf_id", None):
                ctx.reload_page()
    ctx.online.ask("rb_golf_list", {}, got)


class _ListPoll(QWidget):
    """Invisible: refreshes the match list while the golf screen is shown."""

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
    """Mini golf 1 v 1: a live match, or challenge a friend and the list of matches."""
    from .hub import server_wait
    from .shop import CoinBar
    ctx = page.ctx
    top = hbox(spacing=8)
    gid = getattr(ctx, "golf_id", None)
    back = IconButton("back", 32, tip=tr("Back"))

    def leave_screen() -> None:
        if gid:
            ctx.golf_id = None
            ctx.golf_list = None
            return ctx.reload_page()
        page.open_sub(None)
    back.clicked.connect(leave_screen)
    top.addWidget(back)
    top.addWidget(Label(tr("Mini Golf 1v1"), 16, bold=True), 1)
    lay.addLayout(top)
    if getattr(ctx, "golf_missing", False):
        server_wait(ctx, lay, page.W)
        return
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
            ctx.window.confirm(tr("Leave? Your friend wins the match."),
                               lambda: ctx.online.ask("rb_golf_leave", {"gid": gid}, done), yes=tr("Leave"))
        quit_.clicked.connect(leave)
        lay.addWidget(quit_)
        lay.addWidget(Label(tr("Drag back anywhere, then let go to shoot. 3 holes, 25 seconds a turn. Fewest strokes wins."),
                            10, TEXT_DIM, wrap_w=page.W))
        return
    lay.addWidget(CoinBar(ctx))
    lay.addWidget(_ListPoll(page))
    friends = list(getattr(ctx, "duel_friends", None) or [])
    lay.addWidget(Label(tr("CHALLENGE A FRIEND"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
    if not friends:
        lay.addWidget(Label(tr("Add friends in the Social tab to play them."), 11, TEXT_DIM, wrap_w=page.W))
    else:
        names = [f["name"] for f in friends][:6]
        pick = Segmented(names, min(int(getattr(ctx, "duel_pick", 0) or 0), len(names) - 1))
        lay.addWidget(pick)

        def who() -> str:
            return names[min(int(getattr(ctx, "duel_pick", 0) or 0), len(names) - 1)]
        top_bet = golf_limit(ctx, who())
        mode = Segmented([tr("Bet"), tr("No bet")], 1 if getattr(ctx, "duel_nobet", False) or top_bet < 10 else 0)
        lay.addWidget(mode)
        amount = None
        if top_bet >= 10:
            start = max(10, min(top_bet, int(getattr(ctx, "duel_amount", 0) or 100)))
            amount = SliderRow(tr("Bet"), 10, top_bet, start, 10, start, lambda v: coins_text(int(v)), label_w=60)
            amount._val.setFixedWidth(S(78))
            amount.changed.connect(lambda v: setattr(ctx, "duel_amount", int(v)))
            amount.setVisible(mode.index() == 0)
            lay.addWidget(amount)
            lay.addWidget(Label(tr("Maximum {n} (80% of the lower balance).", n=coins_text(top_bet)), 10, TEXT_DIM,
                                wrap_w=page.W))

        def on_mode(i: int) -> None:
            if top_bet < 10:
                return mode.set_index(1)
            ctx.duel_nobet = i == 1
            if amount is not None:
                amount.setVisible(i == 0)

        def on_pick(i: int) -> None:
            ctx.duel_pick = i
            ctx.reload_page()
        mode.changed.connect(on_mode)
        pick.changed.connect(on_pick)
        send = Button(tr("Send challenge"), "primary", 36, icon="shield")

        def ask() -> None:
            name = who()
            bet = 0 if amount is None or getattr(ctx, "duel_nobet", False) else int(amount.value())
            bet = 0 if bet < 10 else bet - bet % 10
            if bet > ctx.econ.coins:
                return ctx.toast(tr("Not enough coins"), "warn")

            def done(ok: bool, data) -> None:
                if not ok:
                    return ctx.toast(tr(str(data)), "warn")
                sfx.play("on")
                ctx.toast(tr("Challenge sent to {name}", name=name))
                ctx.econ.refresh()
                load_golf(page)
            ctx.econ.call("rb_golf_invite", {"name": name, "bet": bet}, done)
        send.clicked.connect(ask)
        lay.addWidget(send)
    lay.addWidget(Label(tr("YOUR MATCHES"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
    rows = getattr(ctx, "golf_list", None)
    if rows is None:
        lay.addWidget(Label(tr("Loading…"), 11, TEXT_DIM))
    elif not rows:
        lay.addWidget(Label(tr("No matches yet."), 11, TEXT_DIM))
    else:
        for m in rows[:10]:
            lay.addWidget(GolfRow(page, m))
