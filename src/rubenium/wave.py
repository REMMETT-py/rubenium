"""4.3: Wave Rush. Hold to rise, let go to fall, at 45 degrees. The course scrolls, narrows and twists the further
you get; touching a wall or a spike ends the run (there is no sliding along a wall).

Solo: coins for the distance, from 30 m. Duel: two players on the same course at the same time; the longer run wins
(with or without a bet). The course comes from a seed the server gives. The client only sends the ticks where the
player pressed or let go: the server replays the run with exactly the same whole-number maths (rb_wave_sim) and pays
for the distance it finds itself, and a run can't end sooner than the time it takes to play it."""
import bisect
import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import QWidget

from .core import S, TEXT, TEXT_DIM, alpha, font, mix, sfx, tr, ui
from .wallet import coins_text
from .widgets import Button, IconButton, Label, Segmented, SliderRow, hbox

# ================================================================ the course (the server's rb_wave_sim, line for line)
WAVE_VX = 12              # units a tick, right and up/down
WAVE_R = 10               # hit radius
WAVE_H = 1000             # course height
WAVE_SW = 48              # half width of a spike
WAVE_TPS = 60             # ticks a second
WAVE_MAX = 60 * 900


class WaveRng:
    def __init__(self, seed: int) -> None:
        self.s = seed & 0x7FFFFFFF

    def next(self, n: int) -> int:
        self.s = (self.s * 1103515245 + 12345) & 0x7FFFFFFF
        return (self.s >> 8) % n


def wave_level(x: int) -> int:
    """0 (start) to 1000 (the hardest: from 1 100 m on)."""
    return min(1000, x // 110)


def wave_gap(d: int) -> int:
    f = d * (d + 1000) // 2000
    g = 420 - 300 * f // 1000
    return g - g % 2


class WaveCourse:
    """Segments [x0, length, c0, slope, gap, spikes]; spikes (x, side): 0 hangs from the top, 1 stands on the floor."""

    def __init__(self, seed: int) -> None:
        self.rng = WaveRng(seed)
        self.segs = [[0, 900, 500, 0, 420, []]]
        self.starts = [0]
        self.x_end, self.c_end = 900, 500

    def _add(self, length: int, slope: int, gap: int, spikes=None) -> None:
        self.segs.append([self.x_end, length, self.c_end, slope, gap, spikes or []])
        self.starts.append(self.x_end)
        self.x_end += length
        self.c_end += slope * length

    def _room(self, slope: int, gap: int) -> int:
        lo, hi = gap // 2 + 40, WAVE_H - gap // 2 - 40
        return hi - self.c_end if slope > 0 else self.c_end - lo

    def _pull(self, gap: int) -> None:
        lo, hi = gap // 2 + 40, WAVE_H - gap // 2 - 40
        if self.c_end < lo:
            self._add(lo - self.c_end, 1, gap)
        elif self.c_end > hi:
            self._add(self.c_end - hi, -1, gap)

    def grow(self) -> None:
        rnd = self.rng.next
        d = wave_level(self.x_end)
        gap = wave_gap(d)
        self._pull(gap)
        r = rnd(1000)
        p_zig = 200 + 400 * d // 1000
        p_flat = 450 - 200 * d // 1000
        if r < p_flat:
            length = 300 + rnd(500)
            n = rnd(2 + 3 * d // 1000) if d >= 20 else 0
            side = rnd(2)
            spikes = []
            if n == 1 and 120 <= d <= 650 and rnd(3) == 0:      # 4.6: a gate, a spike above and below at once
                spikes = [(self.x_end + length // 2, 0), (self.x_end + length // 2, 1)]
                n = 0
            for i in range(n):
                spikes.append((self.x_end + length * (i + 1) // (n + 1), side))
                side = 1 - side
            self._add(length, 0, gap, spikes)
        elif r < p_flat + p_zig:
            legs = 3 + rnd(4 + 4 * d // 1000)
            leg = max(100, 320 - 220 * d // 1000 + rnd(60))
            slope = 1 if self._room(1, gap) >= self._room(-1, gap) else -1
            for _ in range(legs):
                room = self._room(slope, gap)
                if room < 60:
                    slope = -slope
                    room = self._room(slope, gap)
                self._add(max(40, min(leg, room)), slope, gap)
                slope = -slope
        else:
            slope = 1 if rnd(2) else -1
            if self._room(slope, gap) < 120:
                slope = -slope
            length = max(60, min(150 + rnd(400), self._room(slope, gap)))
            spikes = [(self.x_end + length // 2, rnd(2))] if d >= 150 and length >= 200 else []    # 4.5: ramps too
            self._add(length, slope, gap, spikes)

    def ensure(self, x: int) -> None:
        while self.x_end <= x + 4000:
            self.grow()

    def index(self, x: int) -> int:
        return max(0, bisect.bisect_right(self.starts, x) - 1)

    def bounds(self, i: int, x: int):
        x0, _ln, c0, slope, gap, spikes = self.segs[i]
        c = c0 + slope * (x - x0)
        half = gap // 2
        top, bot = c - half, c + half
        hh = gap * 38 // 100
        for xs, side in spikes:
            dx = abs(x - xs)
            if dx < WAVE_SW:
                k = hh * (WAVE_SW - dx) // WAVE_SW
                if side == 0:
                    top = max(top, c - half + k)
                else:
                    bot = min(bot, c + half - k)
        return top, bot


def wave_pay(x: int) -> int:
    """Coins for a solo distance before the mini game limits (the server's rb_wave_pay_for)."""
    return 0 if x < 3000 else int(math.floor((x / 1000.0) ** 1.35))


def metres(x: int) -> int:
    return int(x) // 100


def level_colour(d: int) -> QColor:
    """The walls change colour as it gets harder: green, cyan, violet, then red."""
    stops = [(0, (0.40, 0.75)), (350, (0.52, 0.80)), (700, (0.76, 0.75)), (1000, (0.98, 0.85))]
    for (a, (ha, sa)), (b, (hb, sb)) in zip(stops, stops[1:]):
        if d <= b:
            t = (d - a) / max(1, b - a)
            return QColor.fromHsvF(ha + (hb - ha) * t, sa + (sb - sa) * t, 1.0)
    return QColor.fromHsvF(0.98, 0.85, 1.0)


WAVE_TIERS = [(0, "Easy"), (200, "Medium"), (450, "Hard"), (700, "Insane"), (900, "Extreme")]


def wave_tier_of(d: int) -> int:
    return max(i for i, (lo, _n) in enumerate(WAVE_TIERS) if d >= lo)


class WaveRunner:
    """4.5: another player's wave, rebuilt from the ticks where they pressed or let go (the server's maths). Past the
    last tick known it keeps going the same way, until newer ticks come in."""

    def __init__(self, course, name: str = "") -> None:
        self.course, self.name = course, name
        self.tg: list = []
        self.ys = [500]
        self.crash = None                    # the tick where this path hits a wall
        self.upto = 0
        self.done = False
        self.final = None                    # the last tick of a finished run
        self.shown_y = None
        self.fade_at = 0.0

    def set(self, toggles, upto: int, done: bool = False, final=None) -> None:
        tg = sorted({int(t) for t in (toggles or []) if int(t) > 0})
        if tg != self.tg:
            self.tg, self.ys, self.crash = tg, [500], None
        self.upto = max(self.upto, int(upto or 0))
        if done and not self.done:
            self.done, self.fade_at = True, time.monotonic()
        if final is not None:
            self.final = int(final)

    def y(self, t: int) -> int:
        t = max(0, int(t))
        while len(self.ys) <= t and self.crash is None:
            n = len(self.ys)
            held = bisect.bisect_right(self.tg, n) % 2 == 0
            y = self.ys[-1] + (-WAVE_VX if held else WAVE_VX)
            x = n * WAVE_VX
            self.course.ensure(x)
            top, bot = self.course.bounds(self.course.index(x), x)
            self.ys.append(y)
            if y - WAVE_R < top or y + WAVE_R > bot:
                self.crash = n
        return self.ys[min(t, len(self.ys) - 1)]

    def held(self, t: int) -> bool:
        return bisect.bisect_right(self.tg, t) % 2 == 0


# ================================================================ the game view
class WaveView(QWidget):
    """The run. ready -> (press) -> run -> dead. on_end(ticks, toggles, x) is called once when a run ends."""

    def __init__(self, page, width: int, on_end=None, on_start=None) -> None:
        super().__init__()
        self.page, self.ctx = page, page.ctx
        self.setFixedSize(width, int(width * 0.66))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.on_end, self.on_start = on_end, on_start
        self.seed = None
        self.course = None
        self.state = "wait"                  # wait (no seed yet), ready, count, run, dead
        self.count_until = 0.0
        self.best = 0
        self.message = ""                    # under the result (coins, waiting for the other player…)
        self.message_col = TEXT_DIM
        self.other = None                    # duel: the other player's WaveRunner (seen see-through)
        self.auto_start = False              # duel: both start together when the countdown ends
        self.god = False                     # duel: the other one crashed and you are past them: nothing can hit you
        self.run_t0 = 0.0                    # when tick 0 was (for the other player's position)
        self.watch = None                    # spectating: [runner a, runner b, t0]
        self.replay = None                   # dict: the last seconds before a crash, shown again
        self.can_retry = False               # solo: the next course is in, a press starts again
        self.result = None                   # duel: (title, line, colour) once it is over
        self._reset()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(8)
        self._timer.timeout.connect(self._frame)
        self._timer.start()
        from .widgets import KeyPoll                       # 4.5: Space, Up or W, even while a game has the keyboard
        self.keys = KeyPoll(["Space", "Up", "W"], self._key, lambda: self.state == "run")
        self.keys.setParent(self)

    # -- set up
    def _reset(self) -> None:
        self.t, self.x, self.y = 0, 0, 500
        self.held, self.held_in = True, False
        self.toggles: list = []
        self.trail: list = [(0, 500)]
        self.i = 0
        self.acc = 0.0
        self.last = time.monotonic()
        self.dead_at = 0.0
        self.parts: list = []

    def load(self, seed: int, count_until: float = 0.0) -> None:
        """A new course: ready to start (after a countdown in a duel)."""
        self.seed = int(seed)
        self.course = WaveCourse(self.seed)
        self.course.ensure(4000)
        self._reset()
        self.message = ""
        self.can_retry = False
        self.state = "count" if count_until > time.monotonic() else "ready"
        self.count_until = count_until
        self.update()

    def wait(self, text: str = "") -> None:
        self.state = "wait"
        self.message = text
        self.update()

    # -- input
    def _press(self, on: bool) -> None:
        self.held_in = on
        if on and self.state == "ready":
            self._go()

    def _go(self) -> None:
        self.state = "run"
        self.held, self.t = True, 0
        self.acc, self.last = 0.0, time.monotonic()
        self.run_t0 = self.last
        sfx.play("pick")
        if self.on_start:
            self.on_start()

    def finish_now(self) -> None:
        """Duel: the other player crashed and you are past them. Your run ends here, safely (no crash)."""
        if self.state != "run":
            return
        self.god = True
        self.state = "safe"
        self.dead_at = time.monotonic()
        sfx.play("on")
        if self.on_end:
            self.on_end(self.t, list(self.toggles), self.x)

    def set_other(self, name: str, toggles, upto: int, done: bool, final=None) -> None:
        if self.course is None:
            return
        if self.other is None:
            self.other = WaveRunner(self.course, name)
        self.other.set(toggles, upto, done, final)

    def start_replay(self, loser: WaveRunner, winner, title: str) -> None:
        """The last seconds before the crash, again: both waves, black bars, REPLAY."""
        end = loser.final if loser.final is not None else (loser.crash or loser.upto)
        loser.y(end + 40)
        if winner is not None:
            winner.y(end + 40)
        now = time.monotonic()
        wait = 0.0                                      # the other player first fades out where they crashed
        if self.other is not None and self.other.done and self.other.fade_at:
            wait = max(0.0, self.other.fade_at + 1.5 - now)
        rp = {"loser": loser, "winner": winner, "t0": max(0, end - 330), "t1": end, "at": now + wait + 0.5, "title": title}

        def go() -> None:
            try:
                self.replay = rp
                self.state = "replay"
                self.update()
            except RuntimeError:
                pass
        self._pending_replay = rp
        try:
            self.page.ctx.notifier.hold(wait + 0.5 + (rp["t1"] - rp["t0"]) / WAVE_TPS + 2.0)   # 4.6: no spoiler
        except AttributeError:
            pass
        QTimer.singleShot(int(wait * 1000), go)

    def mousePressEvent(self, e) -> None:
        e.accept()
        self.setFocus()
        if e.button() == Qt.MouseButton.LeftButton:
            self._press(True)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._press(False)

    def _key(self, _name: str, _down: bool) -> None:
        held = any(self.keys.down.values())
        if held != self.held_in or held:
            self._press(held)

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Space, Qt.Key.Key_Up, Qt.Key.Key_W):
            if not e.isAutoRepeat() and not self.keys.live:
                self._press(True)
            return e.accept()
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Space, Qt.Key.Key_Up, Qt.Key.Key_W):
            if not e.isAutoRepeat() and not self.keys.live:
                self._press(False)
            return e.accept()
        super().keyReleaseEvent(e)

    def hideEvent(self, _e) -> None:
        if self.state == "run":                       # no pausing in the middle of a run: hiding it ends it
            self._crash()
        self._timer.stop()

    def showEvent(self, _e) -> None:
        self._timer.start()

    # -- the run: fixed 60 ticks a second
    def _tick(self) -> bool:
        self.t += 1
        if self.held_in != self.held:
            self.toggles.append(self.t)
            self.held = self.held_in
        self.x += WAVE_VX
        self.y += -WAVE_VX if self.held else WAVE_VX
        self.course.ensure(self.x)
        segs = self.course.segs
        while self.x >= segs[self.i][0] + segs[self.i][1]:
            self.i += 1
        top, bot = self.course.bounds(self.i, self.x)
        self.trail.append((self.x, self.y))
        if len(self.trail) > 400:
            del self.trail[:100]
        if self.god:
            return True
        if self.y - WAVE_R < top or self.y + WAVE_R > bot or self.t >= WAVE_MAX:
            self._crash()
            return False
        return True

    def _crash(self) -> None:
        self.state = "dead"
        self.dead_at = time.monotonic()
        sfx.play("off")
        rnd = random.Random(self.t)
        self.parts = [(rnd.uniform(0, math.tau), rnd.uniform(90, 420), rnd.uniform(3, 7)) for _ in range(26)]
        if self.on_end:
            self.on_end(self.t, list(self.toggles), self.x)

    def _frame(self) -> None:
        now = time.monotonic()
        if self.state == "count" and now >= self.count_until:
            self.state = "ready"
            sfx.play("on")
            if self.auto_start:                   # duel: everyone starts at the same moment
                self._go()
        if self.state == "replay" and self.replay and now > self.replay["at"] + (self.replay["t1"] - self.replay["t0"]) / WAVE_TPS + 1.6:
            done, self.replay = self.replay.get("then"), None
            self.state = "wait"
            if done:
                done()
        if self.state == "run":
            self.acc += min(0.25, now - self.last)
            self.last = now
            step = 1.0 / WAVE_TPS
            while self.acc >= step and self.state == "run":
                self.acc -= step
                self._tick()
        self.update()

    # -- drawing
    def _scale(self) -> float:
        return self.height() / WAVE_H

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        r = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), S(12), S(12))
        p.setClipPath(clip)
        sc = self._scale()
        focus = self._focus(now)
        d = wave_level(focus)
        col = level_colour(d)
        bg = QLinearGradient(r.topLeft(), r.bottomLeft())
        bg.setColorAt(0, mix(QColor("#06080C"), col, 0.10))
        bg.setColorAt(1, QColor("#050608"))
        p.fillRect(r, bg)
        cam = focus - r.width() * 0.28 / sc                 # course x at the left edge
        if self.state == "dead":                            # a short shake when it crashes
            k = max(0.0, 1.0 - (now - self.dead_at) / 0.35)
            p.translate(math.sin(now * 90) * S(5) * k, math.cos(now * 70) * S(4) * k)
        p.setPen(QPen(alpha("#FFFFFF", 0.035), 1))          # a grid that scrolls slower than the course
        step = 200
        first = int((cam * 0.5) // step) * step
        gx = first
        while (gx - cam * 0.5) * sc < r.width():
            xx = (gx - cam * 0.5) * sc
            p.drawLine(QPointF(xx, 0), QPointF(xx, r.height()))
            gx += step
        if self.course is not None:
            self._paint_course(p, r, cam, sc, col)
            if self.replay is not None:
                rp = self.replay
                t = self._replay_t(now)
                if rp["winner"] is not None:
                    self._paint_runner(p, r, cam, sc, rp["winner"], t, QColor("#FFB627"), 0.45, now)
                self._paint_runner(p, r, cam, sc, rp["loser"], t, col, 1.0, now, boom=True)
            elif self.watch is not None:
                ta = self._watch_t(0, now)
                tb = self._watch_t(1, now)
                self._paint_runner(p, r, cam, sc, self.watch[0], ta, ui.accent, 0.95, now, boom=True)
                self._paint_runner(p, r, cam, sc, self.watch[1], tb, QColor("#FFB627"), 0.95, now, boom=True)
            else:
                self._paint_ghost(p, r, cam, sc, now)
                self._paint_wave(p, r, cam, sc, col, now)
        p.setClipping(False)
        p.resetTransform()
        if self.replay is not None:
            return self._paint_replay_hud(p, r, now)
        self._paint_hud(p, r, col, now)

    def _paint_course(self, p, r, cam, sc, col) -> None:
        c = self.course
        x_from, x_to = int(cam) - 20, int(cam + r.width() / sc) + 20
        c.ensure(x_to)
        xs, tops, bots = [], [], []
        i = c.index(max(0, x_from))
        x = max(0, x_from - x_from % 6)
        while x <= x_to:
            while i + 1 < len(c.segs) and x >= c.segs[i + 1][0]:
                i += 1
            t, b = c.bounds(i, x)
            xs.append((x - cam) * sc)
            tops.append(t * sc)
            bots.append(b * sc)
            x += 6
        if not xs:
            return
        if x_from < 0:                                     # before the start: a closed wall behind the wave
            p.fillRect(QRectF(0, 0, (0 - cam) * sc, r.height()), mix(QColor("#0B0F14"), col, 0.18))
        fill = QLinearGradient(QPointF(0, 0), QPointF(0, r.height()))
        fill.setColorAt(0, mix(QColor("#0B0F14"), col, 0.22))
        fill.setColorAt(0.5, mix(QColor("#0B0F14"), col, 0.10))
        fill.setColorAt(1, mix(QColor("#0B0F14"), col, 0.22))
        top_poly = QPolygonF([QPointF(xs[0], -S(4))] + [QPointF(a, b) for a, b in zip(xs, tops)] + [QPointF(xs[-1], -S(4))])
        bot_poly = QPolygonF([QPointF(xs[0], r.height() + S(4))] + [QPointF(a, b) for a, b in zip(xs, bots)] +
                             [QPointF(xs[-1], r.height() + S(4))])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawPolygon(top_poly)
        p.drawPolygon(bot_poly)
        for w, a in ((S(6), 0.18), (S(2.2), 1.0)):         # the glowing edge
            p.setPen(QPen(alpha(col, a), w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPolyline(QPolygonF([QPointF(a_, b_) for a_, b_ in zip(xs, tops)]))
            p.drawPolyline(QPolygonF([QPointF(a_, b_) for a_, b_ in zip(xs, bots)]))

    # -- the camera
    def _focus(self, now: float) -> float:
        if self.replay is not None:
            return self._replay_t(now) * WAVE_VX
        if self.watch is not None:
            return max(self._watch_t(0, now), self._watch_t(1, now)) * WAVE_VX
        return self.x

    def _replay_t(self, now: float) -> int:
        rp = self.replay
        return int(min(rp["t1"] + 30, rp["t0"] + max(0.0, now - rp["at"]) * WAVE_TPS))

    def _watch_t(self, i: int, now: float) -> int:
        """Spectating: where each player is about now (a little behind, so the path shown is the real one)."""
        a = self.watch[i]
        if a.done and a.final is not None:
            return a.final
        est = int((now - self.watch[2]) * WAVE_TPS) - 40
        return max(0, min(est, a.upto + 30))

    def _paint_runner(self, p, r, cam, sc, run: WaveRunner, t: int, col, opacity: float, now: float, boom=False) -> None:
        """Another wave: its trail and its arrow at tick t (or where it crashed)."""
        end = t
        if run.done and run.final is not None:
            end = min(end, run.final)
        if run.crash is not None and run.crash <= end + 1 and run.crash <= run.upto + 1:
            end = min(end, run.crash)
        first = max(0, end - 160)
        pts = [QPointF((k * WAVE_VX - cam) * sc, run.y(k) * sc) for k in range(first, end + 1, 2)]
        if not pts:
            return
        p.setOpacity(opacity)
        if len(pts) >= 2:
            for w, a in ((S(6), 0.12), (S(2.6), 0.8)):
                p.setPen(QPen(alpha(mix(col, QColor("#FFFFFF"), 0.45), a), w, Qt.PenStyle.SolidLine,
                              Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.MiterJoin))
                p.drawPolyline(QPolygonF(pts))
        c = QPointF((end * WAVE_VX - cam) * sc, run.y(end) * sc)
        crashed = run.done and run.final is not None and t >= run.final
        if crashed and boom:
            k = min(1.0, (t - run.final) / 25.0)
            p.setPen(Qt.PenStyle.NoPen)
            for j in range(12):
                ang = j * math.tau / 12
                q = c + QPointF(math.cos(ang) * S(26) * k, math.sin(ang) * S(26) * k)
                p.setBrush(alpha(col, max(0.0, 1.0 - k)))
                p.drawEllipse(q, S(3), S(3))
        else:
            p.save()
            p.translate(c)
            p.rotate(-45 if run.held(end) else 45)
            size = S(10)
            head = QPolygonF([QPointF(size, 0), QPointF(-size * 0.8, -size * 0.7), QPointF(-size * 0.35, 0),
                              QPointF(-size * 0.8, size * 0.7)])
            p.setPen(QPen(QColor("#FFFFFF"), S(1.2)))
            p.setBrush(mix(QColor("#FFFFFF"), col, 0.5))
            p.drawPolygon(head)
            p.restore()
        if run.name:
            p.setPen(alpha(col, 0.95))
            p.setFont(font(9, QFont.Weight.Bold))
            p.drawText(QRectF(c.x() - S(60), c.y() - S(28), S(120), S(14)), int(Qt.AlignmentFlag.AlignCenter), run.name)
        p.setOpacity(1.0)

    def _paint_ghost(self, p, r, cam, sc, now) -> None:
        """Duel: the other player, see-through. When they crash they fade out slowly where they crashed."""
        o = self.other
        if o is None or self.state not in ("run", "safe", "dead", "ready", "count"):
            return
        if o.done and o.final is not None:
            t = o.final
            fade = max(0.0, 1.0 - (now - o.fade_at) / 1.4)
            if fade <= 0:
                return
        else:
            if self.state not in ("run", "safe", "dead") or not self.run_t0:
                return
            t = min(int((now - self.run_t0) * WAVE_TPS), o.upto + 45)
            fade = 1.0
        y = o.y(t)
        o.shown_y = y if o.shown_y is None else o.shown_y + (y - o.shown_y) * 0.35   # no jump when news comes in
        first = max(0, t - 120)
        pts = [QPointF((k * WAVE_VX - cam) * sc, o.y(k) * sc) for k in range(first, t, 3)]
        pts.append(QPointF((t * WAVE_VX - cam) * sc, o.shown_y * sc))
        gold = QColor("#FFB627")
        p.setOpacity(0.38 * fade)
        if len(pts) >= 2:
            p.setPen(QPen(gold, S(2.2), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.MiterJoin))
            p.drawPolyline(QPolygonF(pts))
        c = pts[-1]
        p.save()
        p.translate(c)
        p.rotate(-45 if o.held(t) else 45)
        size = S(10)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(gold)
        p.drawPolygon(QPolygonF([QPointF(size, 0), QPointF(-size * 0.8, -size * 0.7), QPointF(-size * 0.35, 0),
                                 QPointF(-size * 0.8, size * 0.7)]))
        p.restore()
        p.setOpacity(0.6 * fade)
        p.setPen(gold)
        p.setFont(font(8.5, QFont.Weight.Bold))
        p.drawText(QRectF(c.x() - S(50), c.y() - S(24), S(100), S(12)), int(Qt.AlignmentFlag.AlignCenter), o.name)
        p.setOpacity(1.0)

    def _paint_wave(self, p, r, cam, sc, col, now) -> None:
        pts = [QPointF((tx - cam) * sc, ty * sc) for tx, ty in self.trail if (tx - cam) * sc > -S(10)]
        if len(pts) >= 2:                                  # the trail: the zigzag you drew
            for w, a in ((S(7), 0.12), (S(3), 0.85)):
                p.setPen(QPen(alpha(mix(col, QColor("#FFFFFF"), 0.55), a), w, Qt.PenStyle.SolidLine,
                              Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.MiterJoin))
                p.drawPolyline(QPolygonF(pts))
        c = QPointF((self.x - cam) * sc, self.y * sc)
        if self.state in ("wait",) and self.result:
            return
        if self.state == "dead":
            age = now - self.dead_at
            for ang, sp, sz in self.parts:
                k = min(1.0, age / 0.6)
                q = c + QPointF(math.cos(ang) * sp * sc * 0.6 * k * 2.2, math.sin(ang) * sp * sc * 0.6 * k * 2.2)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha(col if sz > 5 else QColor("#FFFFFF"), max(0.0, 1.0 - age / 0.9)))
                p.drawEllipse(q, S(sz) * (1 - 0.5 * k), S(sz) * (1 - 0.5 * k))
            return
        up = self.held if self.state == "run" else True
        p.save()
        p.translate(c)
        p.rotate(-45 if up else 45)
        size = S(11)
        head = QPolygonF([QPointF(size, 0), QPointF(-size * 0.8, -size * 0.7), QPointF(-size * 0.35, 0),
                          QPointF(-size * 0.8, size * 0.7)])
        p.setPen(QPen(alpha(col, 0.35), S(6)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(head)
        p.setPen(QPen(QColor("#FFFFFF"), S(1.4)))
        p.setBrush(mix(QColor("#FFFFFF"), col, 0.35))
        p.drawPolygon(head)
        p.restore()

    def _paint_hud(self, p, r, col, now) -> None:
        if self.state == "wait":
            p.fillRect(r, alpha("#000000", 0.55))
            return self._paint_wait(p, r)
        x = self._focus(now)
        p.setPen(QColor(TEXT))
        p.setFont(font(17, QFont.Weight.Black))
        p.drawText(QRectF(S(12), S(6), r.width() * 0.28, S(26)), int(Qt.AlignmentFlag.AlignVCenter), f"{metres(int(x))} m")
        p.setFont(font(9.5, QFont.Weight.Bold))
        p.setPen(QColor(TEXT_DIM))
        if self.best and self.watch is None:
            p.drawText(QRectF(S(12), S(30), r.width() * 0.28, S(16)), int(Qt.AlignmentFlag.AlignVCenter),
                       tr("Best {n} m", n=metres(self.best)))
        self._paint_difficulty(p, r, self._focus(now), now)
        mid = QRectF(0, r.height() * 0.30, r.width(), r.height() * 0.4)
        if self.state in ("ready", "count", "dead", "safe"):
            dim = 0.0 if self.state in ("dead", "safe") and now - self.dead_at < 0.45 else 0.55
            if dim:
                p.fillRect(r, alpha("#000000", dim))
        if self.state == "count":
            n = max(1, math.ceil(self.count_until - now))
            self._big(p, mid, str(n), "#FFFFFF", 40)
        elif self.state == "ready":
            pulse = 0.75 + 0.25 * math.sin(now * 4)
            self._big(p, mid.adjusted(0, -S(14), 0, -S(14)), tr("Hold to start"), alpha("#FFFFFF", pulse), 20)
            from .widgets import paint_keycap
            labels = ["Hold", "Space", "Up", "W"]
            x = r.width() / 2 - S(62)
            for k in labels:
                x += paint_keycap(p, QPointF(x, mid.center().y() + S(24)), k) + S(6)
        elif self.state == "safe":
            self._big(p, mid.adjusted(0, -S(10), 0, -S(10)), tr("You outlasted them!"), "#3DDC84", 18)
            if self.message:
                self._big(p, mid.adjusted(0, S(20), 0, S(20)), self.message, self.message_col, 11.5)
        elif self.state == "dead" and now - self.dead_at >= 0.45:
            self._big(p, mid.adjusted(0, -S(22), 0, -S(22)), tr("Crashed at {n} m", n=metres(self.x)), "#FFFFFF", 20)
            if self.message:
                self._big(p, mid.adjusted(0, S(12), 0, S(12)), self.message, self.message_col, 12.5)
            if self.can_retry and now - self.dead_at > 0.9:
                pulse = 0.6 + 0.4 * math.sin(now * 4)
                self._big(p, mid.adjusted(0, S(44), 0, S(44)), tr("Press to go again"), alpha("#FFFFFF", pulse), 11)

    def _paint_difficulty(self, p, r, x: float, now: float) -> None:
        """4.5: no finish line, so no progress bar: a difficulty bar that keeps climbing, with the distance riding on it
        and the distance where the next level starts."""
        d = wave_level(int(x))
        bar = QRectF(r.width() * 0.30, S(13), r.width() * 0.66, S(7))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.08))
        p.drawRoundedRect(bar, bar.height() / 2, bar.height() / 2)
        g = QLinearGradient(bar.topLeft(), bar.topRight())
        for k in range(5):
            g.setColorAt(k / 4, level_colour(k * 250))
        fill = QRectF(bar.left(), bar.top(), max(bar.height(), bar.width() * d / 1000), bar.height())
        p.setBrush(g)
        p.drawRoundedRect(fill, bar.height() / 2, bar.height() / 2)
        if d < 1000:                                         # a soft shine running along the fill
            sx = fill.left() + (now * 0.6 % 1.0) * fill.width()
            sh = QLinearGradient(QPointF(sx - S(14), 0), QPointF(sx + S(14), 0))
            sh.setColorAt(0, alpha("#FFFFFF", 0.0))
            sh.setColorAt(0.5, alpha("#FFFFFF", 0.35))
            sh.setColorAt(1, alpha("#FFFFFF", 0.0))
            p.setBrush(sh)
            p.drawRoundedRect(fill, bar.height() / 2, bar.height() / 2)
        p.setFont(font(8, QFont.Weight.Bold))
        for lo, name in WAVE_TIERS[1:]:                           # where each level starts, in metres
            tx = bar.left() + bar.width() * lo / 1000
            p.setPen(QPen(alpha("#FFFFFF", 0.55 if d >= lo else 0.25), 1))
            p.drawLine(QPointF(tx, bar.top() - S(2)), QPointF(tx, bar.bottom() + S(2)))
            p.setPen(alpha("#FFFFFF", 0.55 if d >= lo else 0.35))
            p.drawText(QRectF(tx - S(30), bar.bottom() + S(2), S(60), S(12)), int(Qt.AlignmentFlag.AlignCenter),
                       f"{lo * 110 // 100} m")
        ti = wave_tier_of(d)
        col = level_colour(d)
        p.setPen(col)
        p.setFont(font(9.5, QFont.Weight.Black))
        p.drawText(QRectF(bar.left(), bar.top() - S(13), bar.width(), S(12)), int(Qt.AlignmentFlag.AlignLeft |
                   Qt.AlignmentFlag.AlignVCenter), tr(WAVE_TIERS[ti][1]).upper())
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(8.5, QFont.Weight.Bold))
        nxt = tr("Next level at {n} m", n=WAVE_TIERS[ti + 1][0] * 110 // 100) if ti + 1 < len(WAVE_TIERS) else \
            (tr("Hardest level") if d >= 1000 else tr("Hardest at {n} m", n=1100))
        p.drawText(QRectF(bar.left(), bar.top() - S(13), bar.width(), S(12)), int(Qt.AlignmentFlag.AlignRight |
                   Qt.AlignmentFlag.AlignVCenter), nxt)

    def _paint_replay_hud(self, p, r, now: float) -> None:
        rp = self.replay
        k = min(1.0, max(0.0, (now - rp["at"] + 0.5) / 0.45))
        bh = r.height() * 0.11 * k                           # black bars slide in
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 235))
        p.drawRect(QRectF(0, 0, r.width(), bh))
        p.drawRect(QRectF(0, r.height() - bh, r.width(), bh))
        if now < rp["at"]:                                   # the fade in
            p.fillRect(r, QColor(0, 0, 0, max(0, min(255, int(255 * (rp["at"] - now) / 0.5)))))
        dot = 0.5 + 0.5 * math.sin(now * 6)
        p.setBrush(alpha("#FF3B3B", 0.4 + 0.6 * dot))
        p.drawEllipse(QPointF(S(16), bh / 2), S(4.5), S(4.5))
        p.setPen(QColor("#FFFFFF"))
        p.setFont(font(12, QFont.Weight.Black, 2.0))
        p.drawText(QRectF(S(26), 0, S(120), bh), int(Qt.AlignmentFlag.AlignVCenter), tr("REPLAY"))
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10, QFont.Weight.Bold))
        p.drawText(QRectF(0, 0, r.width() - S(12), bh), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                   rp["title"])
        span = max(1, rp["t1"] + 30 - rp["t0"])
        f = (self._replay_t(now) - rp["t0"]) / span
        line = QRectF(S(12), r.height() - bh / 2 - S(1.5), r.width() - S(24), S(3))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.15))
        p.drawRoundedRect(line, S(1.5), S(1.5))
        p.setBrush(QColor("#FF3B3B"))
        p.drawRoundedRect(QRectF(line.left(), line.top(), line.width() * min(1.0, f), line.height()), S(1.5), S(1.5))

    def _paint_wait(self, p, r) -> None:
        mid = QRectF(0, r.height() * 0.30, r.width(), r.height() * 0.4)
        if self.result:
            title, line, colour = self.result
            self._big(p, mid.adjusted(0, -S(16), 0, -S(16)), title, colour, 24)
            self._big(p, mid.adjusted(0, S(20), 0, S(20)), line, TEXT, 12.5)
        else:
            self._big(p, mid, self.message or tr("Loading…"), TEXT_DIM, 13)

    def _big(self, p, rect, text, colour, size) -> None:
        p.setPen(QColor(colour) if not isinstance(colour, QColor) else colour)
        p.setFont(font(size, QFont.Weight.Black))
        p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), text)


# ================================================================ the screens
def _head(page, lay, tag: str, on_back) -> None:
    from .gamehelp import HelpButton
    top = hbox(spacing=8)
    back = IconButton("back", 32, tip=tr("Back"))
    back.clicked.connect(on_back)
    top.addWidget(back)
    top.addWidget(Label(tr("Wave Rush"), 16, bold=True), 1)
    top.addWidget(HelpButton(page.ctx, "wave"))
    pill = Label(tag, 10, "#3DDC84", bold=True)
    pill.fit()
    top.addWidget(pill)
    lay.addLayout(top)


def build_wave(page, lay) -> None:
    from .hub import server_wait
    from .shop import CoinBar
    ctx = page.ctx
    did = getattr(ctx, "wave_duel", None)
    solo = not did and getattr(ctx, "wave_mode", "solo") == "solo"

    def leave_screen() -> None:
        if did:
            ctx.wave_duel = None
            ctx.wave_lobby = None
            return ctx.reload_page("games")
        page.open_sub(None)
    _head(page, lay, tr("WATCHING") if getattr(ctx, "wave_watch", None) and not did else tr("SOLO") if solo else tr("DUEL"),
          (lambda: (setattr(ctx, "wave_watch", None), ctx.reload_page("games"))) if getattr(ctx, "wave_watch", None) and not did
          else leave_screen)
    if getattr(ctx, "wave_missing", False):
        return server_wait(ctx, lay, page.W)
    if did:
        return _duel_run(page, lay, did, leave_screen)
    watching = getattr(ctx, "wave_watch", None)
    if watching:
        def stop_watching() -> None:
            ctx.wave_watch = None
            ctx.reload_page("games")
        return _watch_run(page, lay, watching, stop_watching)
    which = Segmented([tr("Solo"), tr("Duel")], 0 if solo else 1)

    def pick(i: int) -> None:
        ctx.wave_mode = "solo" if i == 0 else "duel"
        sfx.play("pick")
        ctx.reload_page("games")
    which.changed.connect(pick)
    lay.addWidget(which)
    lay.addWidget(CoinBar(ctx))
    if solo:
        return _solo(page, lay)
    _lobby(page, lay)


def _controls(page, lay) -> None:
    from .widgets import ControlsBar
    lay.addWidget(ControlsBar([(["Hold", "Space", "Up", "W"], tr("Hold to rise, let go to fall"))], page.W))


# -- solo
def _solo(page, lay) -> None:
    ctx = page.ctx
    view = WaveView(page, page.W)
    run = {"id": None}

    def fetch() -> None:
        def got(ok: bool, data) -> None:
            try:
                if not ok:
                    if "soon" in str(data).lower():
                        ctx.wave_missing = True
                        return ctx.reload_page("games")
                    return view.wait(tr(str(data)))
                run["id"] = data["run"]
                view.best = max(view.best, int(data.get("best") or 0))
                if view.state != "dead":
                    view.load(int(data["seed"]))
                else:
                    run["seed"] = int(data["seed"])
                    view.can_retry = True
            except RuntimeError:
                pass
        ctx.econ.call("rb_wave_solo", {}, got)

    def ended(ticks: int, toggles: list, x: int) -> None:
        rid = run["id"]
        run["id"] = None
        view.message, view.message_col = tr("Counting…"), TEXT_DIM

        def done(ok: bool, data) -> None:
            try:
                if not ok:
                    view.message, view.message_col = tr(str(data)), "#FF5C6C"
                else:
                    paid = int(data.get("paid") or 0)
                    view.best = max(view.best, int(data.get("best") or 0))
                    if data.get("record"):
                        view.message, view.message_col = tr("New best!") + ("  +" + coins_text(paid) if paid else ""), "#E8C26A"
                        sfx.play("on")
                    elif paid:
                        view.message, view.message_col = "+" + coins_text(paid) + " " + tr("coins"), "#E8C26A"
                    elif x < 3000:
                        view.message, view.message_col = tr("Coins from 30 m"), TEXT_DIM
                    else:
                        view.message, view.message_col = tr("No coins: the 2-hour limit is reached"), TEXT_DIM
                    ctx.econ.refresh()
                QTimer.singleShot(700, fetch)                  # the next course, ready for a retry
            except RuntimeError:
                pass
        if rid:
            ctx.econ.call("rb_wave_finish", {"run": rid, "toggles": toggles, "ticks": ticks}, done)

    def retry_ready() -> None:                                 # press again once the next course is in
        if view.state == "dead" and run.get("seed") and run["id"] and time.monotonic() - view.dead_at > 0.9:
            seed = run.pop("seed")
            view.load(seed)
    view.on_end = ended
    view.wait()
    old_press = view._press

    def press(on: bool) -> None:
        if on and view.state == "dead":
            return retry_ready()
        old_press(on)
    view._press = press
    lay.addWidget(view)
    _controls(page, lay)
    fetch()


# -- duel lobby
def _load_lobby(page) -> None:
    ctx = page.ctx

    def got(ok: bool, data) -> None:
        if not ok:
            if "soon" in str(data).lower():
                ctx.wave_missing = True
                if ctx.window.showing("games") and getattr(ctx, "games_sub", None) == "wave":
                    ctx.reload_page("games")
            return
        old = getattr(ctx, "wave_lobby", None)
        live = data.get("live")
        if live and not getattr(ctx, "wave_duel", None) and (old is None or old.get("live") != live):
            ctx.wave_duel = live                                # somebody joined: straight in
            ctx.wave_lobby = data
            sfx.play("on")
            if ctx.window.showing("games") and getattr(ctx, "games_sub", None) == "wave":
                ctx.reload_page("games")
            return
        if data != old:
            ctx.wave_lobby = data
            if (ctx.window.showing("games") and getattr(ctx, "games_sub", None) == "wave"
                    and not getattr(ctx, "wave_duel", None) and getattr(ctx, "wave_mode", "solo") == "duel"):
                ctx.reload_page("games")
    ctx.online.ask("rb_wave_lobbies", {}, got)


class _LobbyPoll(QWidget):
    def __init__(self, page) -> None:
        super().__init__()
        self.page = page
        self.setFixedHeight(0)
        self._t = QTimer(self)
        self._t.setInterval(2000)
        self._t.timeout.connect(lambda: _load_lobby(page))

    def showEvent(self, _e) -> None:
        _load_lobby(self.page)
        self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()


def _lobby(page, lay) -> None:
    from .golf import LobbyRow
    ctx = page.ctx
    lay.addWidget(_LobbyPoll(page))
    data = getattr(ctx, "wave_lobby", None)
    if data is None:
        return lay.addWidget(Label(tr("Loading…"), 11, TEXT_DIM))
    lobbies = list(data.get("lobbies") or [])
    mine = next((m for m in lobbies if m.get("mine")), None)
    if mine is None:
        lay.addWidget(Label(tr("OPEN A DUEL"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
        cap = int(data.get("cap") or 0)
        mode = Segmented([tr("Bet"), tr("No bet")], 1 if getattr(ctx, "wave_nobet", False) or cap < 10 else 0)
        lay.addWidget(mode)
        amount = None
        if cap >= 10:                                   # 4.5: round values, up to what your balance allows
            from .widgets import AmountSlider
            start = max(10, min(cap, int(getattr(ctx, "wave_amount", 0) or 100)))
            amount = AmountSlider(tr("Bet"), 10, cap, start, coins_text, label_w=40)
            amount.changed.connect(lambda v: setattr(ctx, "wave_amount", int(v)))
            amount.setVisible(mode.index() == 0)
            lay.addWidget(amount)

        def on_mode(i: int) -> None:
            if cap < 10:
                return mode.set_index(1)
            ctx.wave_nobet = i == 1
            if amount is not None:
                amount.setVisible(i == 0)
        mode.changed.connect(on_mode)
        make = Button(tr("Open a duel"), "primary", 36, icon="flag")

        def create() -> None:
            bet = 0 if amount is None or getattr(ctx, "wave_nobet", False) else int(amount.value())
            bet = 0 if bet < 10 else bet - bet % 10
            if bet > ctx.econ.coins:
                return ctx.toast(tr("Not enough coins"), "warn")

            def done(ok: bool, d) -> None:
                if not ok:
                    return ctx.toast(tr(str(d)), "warn")
                sfx.play("on")
                ctx.toast(tr("Duel open: waiting for a player"))
                ctx.econ.refresh()
                ctx.wave_lobby = None
                _load_lobby(page)
            ctx.econ.call("rb_wave_create", {"bet": bet}, done)
        make.clicked.connect(create)
        lay.addWidget(make)
    else:
        lay.addWidget(Label(tr("YOUR DUEL"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
        row = LobbyRow(page, mine)
        _rewire(row, page, mine)
        lay.addWidget(row)
    others = [m for m in lobbies if not m.get("mine")]
    lay.addWidget(Label(tr("OPEN DUELS"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
    if not others:
        lay.addWidget(Label(tr("No open duel right now. Open one!"), 11, TEXT_DIM, wrap_w=page.W))
    for m in others[:12]:
        row = LobbyRow(page, m)
        _rewire(row, page, m)
        lay.addWidget(row)
    watch = list(data.get("watch") or [])            # 4.5: duels being played right now: watch one
    if watch:
        lay.addWidget(Label(tr("LIVE NOW"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
        for m in watch[:6]:
            line = hbox(spacing=6)
            line.addWidget(Label(f"{m.get('a')}  vs  {m.get('b')}" + ("   ·   " + coins_text(int(m.get("bet") or 0)) if m.get("bet") else ""),
                                 11.5, TEXT, bold=True), 1)
            eye = Button(tr("Watch"), "ghost", 28, icon="eye")
            eye.setFixedWidth(max(S(90), eye.sizeHint().width()))
            eye.clicked.connect(lambda _c=False, wid=m["id"]: (setattr(ctx, "wave_watch", wid), sfx.play("pick"),
                                                               ctx.reload_page("games")))
            line.addWidget(eye)
            lay.addLayout(line)
    hist = list(data.get("history") or [])
    if hist:
        lay.addWidget(Label(tr("YOUR LAST DUELS"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
        for m in hist[:6]:
            lay.addWidget(_HistRow(m, page.W))


def _rewire(row, page, m: dict) -> None:
    """The golf lobby row, with Wave Rush's own Join and Close."""
    ctx = page.ctx
    for b in row.findChildren(Button):
        try:
            b.clicked.disconnect()
        except TypeError:
            pass
        if m.get("mine"):
            def close() -> None:
                def done(ok: bool, data) -> None:
                    if not ok:
                        return ctx.toast(tr(str(data)), "warn")
                    sfx.play("off")
                    ctx.econ.refresh()
                    ctx.wave_lobby = None
                    _load_lobby(page)
                ctx.econ.call("rb_wave_cancel", {"did": m["id"]}, done)
            b.clicked.connect(close)
        else:
            def join() -> None:
                bet = int(m.get("bet") or 0)
                if bet > ctx.econ.coins:
                    return ctx.toast(tr("Not enough coins"), "warn")

                def done(ok: bool, data) -> None:
                    if not ok:
                        ctx.wave_lobby = None
                        _load_lobby(page)
                        return ctx.toast(tr(str(data)), "warn")
                    ctx.econ.refresh()
                    ctx.wave_duel = m["id"]
                    sfx.play("on")
                    ctx.reload_page("games")

                def go() -> None:
                    ctx.econ.call("rb_wave_join", {"did": m["id"]}, done)
                if bet:
                    ctx.window.confirm(tr("Join {name}'s duel for {n} coins?", name=m.get("host", "?"), n=coins_text(bet)),
                                       go, yes=tr("Join"))
                else:
                    go()
            b.clicked.connect(join)


class _HistRow(QWidget):
    def __init__(self, m: dict, width: int) -> None:
        super().__init__()
        self.m = m
        self.setFixedSize(width, S(40))

    def paintEvent(self, _e) -> None:
        m = self.m
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 2, -0.5, -2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.035))
        p.drawRoundedRect(r, S(10), S(10))
        bet = int(m.get("bet") or 0)
        p.setPen(QColor(TEXT))
        p.setFont(font(11.5, QFont.Weight.Bold))
        p.drawText(r.adjusted(S(10), 0, 0, 0), int(Qt.AlignmentFlag.AlignVCenter),
                   tr("vs {name}", name=m.get("other") or "?") + ("  ·  " + coins_text(bet) if bet else ""))
        if m.get("state") == "live":
            text, col = tr("Live now"), "#3DDC84"
        else:
            text = (tr("Draw") if m.get("draw") else tr("Won") if m.get("won") else tr("Lost"))
            text += f"  ·  {int(m.get('me_m') or 0)} m – {int(m.get('other_m') or 0)} m"
            col = "#3DDC84" if m.get("won") else TEXT_DIM
        p.setPen(QColor(col))
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        p.drawText(r.adjusted(0, 0, -S(10), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), text)


# -- a live duel
class _DuelBar(QWidget):
    """Both players and how far each one is."""

    def __init__(self, width: int) -> None:
        super().__init__()
        self.st: dict = {}
        self.mine_x = 0
        self.setFixedSize(width, S(44))

    def paintEvent(self, _e) -> None:
        st = self.st
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.05))
        p.drawRoundedRect(r, S(10), S(10))
        me = st.get("me", "a")
        other = "b" if me == "a" else "a"
        w = r.width() / 3
        for i, side in enumerate((me, other)):
            box = QRectF(r.left() + (0 if i == 0 else 2 * w), r.top(), w, r.height())
            align = Qt.AlignmentFlag.AlignLeft if i == 0 else Qt.AlignmentFlag.AlignRight
            p.setPen(ui.accent if i == 0 else QColor("#FFB627"))
            p.setFont(font(11, QFont.Weight.Bold))
            p.drawText(box.adjusted(S(8), S(3), -S(8), -r.height() / 2), int(Qt.AlignmentFlag.AlignVCenter | align),
                       str(st.get(side) or "?"))
            x = max(int(st.get(side + "_x") or 0), self.mine_x if i == 0 else 0)
            done = st.get(side + "_done") and st.get("winner") != side
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(10, QFont.Weight.DemiBold))
            p.drawText(box.adjusted(S(8), r.height() / 2, -S(8), -S(3)), int(Qt.AlignmentFlag.AlignVCenter | align),
                       f"{metres(x)} m" + ("  ·  " + tr("crashed") if done else ""))
        mid = QRectF(r.left() + w, r.top(), w, r.height())
        p.setPen(QColor(TEXT))
        p.setFont(font(11, QFont.Weight.Black))
        bet = int(st.get("bet") or 0)
        p.drawText(mid.adjusted(0, S(3), 0, -r.height() / 2), int(Qt.AlignmentFlag.AlignCenter),
                   tr("Pot {n}", n=coins_text(bet * 2)) if bet else tr("No bet"))
        p.setFont(font(10, QFont.Weight.DemiBold))
        p.setPen(QColor(TEXT_DIM))
        left = int(st.get("left") or 0)
        p.drawText(mid.adjusted(0, r.height() / 2, 0, -S(3)), int(Qt.AlignmentFlag.AlignCenter),
                   tr("Final score") if st.get("state") == "done" else f"{left // 60}:{left % 60:02d}")


def _duel_titles(st: dict, me):
    """(title, line, colour, money) for a finished duel, from one side (me = 'a', 'b' or None for a spectator)."""
    bet = int(st.get("bet") or 0)
    a, b = st.get("a") or "?", st.get("b") or "?"
    win = st.get("winner")
    if me is None:
        title = tr("Draw") if not win else tr("{name} wins", name=a if win == "a" else b)
        line = f"{a} {metres(int(st.get('a_x') or 0))} m  ·  {b} {metres(int(st.get('b_x') or 0))} m"
        return title, line, "#FFFFFF", ""
    other = "b" if me == "a" else "a"
    won, draw = win == me, not win
    if draw:
        title, money = tr("Draw"), (tr("Bets refunded") if bet else "")
    elif won:
        title, money = tr("You win!"), ("+" + coins_text(int(bet * 2 * 0.95)) if bet else "")
    else:
        title, money = tr("{name} wins", name=st.get(other) or "?"), ("−" + coins_text(bet) if bet else "")
    line = f"{metres(int(st.get(me + '_x') or 0))} m  ·  {metres(int(st.get(other + '_x') or 0))} m"
    if st.get("why") == "forfeit":
        line = tr("{name} left the duel", name=st.get(other) or "?") if won else tr("You left the duel")
    return title, line, ("#3DDC84" if won else "#FFFFFF"), money


def _replay_for(view, st: dict, then) -> bool:
    """When a duel ends on distance, the last seconds before the loser crashed are shown again (both waves)."""
    if st.get("why") != "distance" or not st.get("winner") or view.course is None:
        return False
    win = st["winner"]
    lose = "b" if win == "a" else "a"
    loser = WaveRunner(view.course, st.get(lose) or "?")
    loser.set(st.get(lose + "_tg") or [], int(st.get(lose + "_ticks") or 0), True, int(st.get(lose + "_ticks") or 0))
    winner = WaveRunner(view.course, st.get(win) or "?")
    winner.set(st.get(win + "_tg") or [], int(st.get(win + "_ticks") or 0), True, int(st.get(win + "_ticks") or 0))
    if not loser.final:
        return False
    view.start_replay(loser, winner, tr("How {name} crashed", name=loser.name))
    view._pending_replay["then"] = then
    return True


def _duel_run(page, lay, did: str, leave_screen) -> None:
    ctx = page.ctx
    bar = _DuelBar(page.W)
    lay.addWidget(bar)
    view = WaveView(page, page.W)
    view.auto_start = True                                  # 4.5: both start together, when the countdown ends
    lay.addWidget(view)
    _controls(page, lay)
    info = {"run": None, "seed": None, "ended": False, "settled": False}
    seen = getattr(ctx, "wave_replayed", None) == did

    def show(st: dict) -> None:
        try:
            bar.st = st
            bar.update()
            me = st.get("me")
            other = "b" if me == "a" else "a"
            if info["seed"] is None and st.get("seed") is not None and st.get("state") in ("live", "done"):
                info["seed"], info["run"] = int(st["seed"]), st.get("run")
                if st.get("state") == "live":
                    view.load(info["seed"], time.monotonic() + float(st.get("starts_in") or 0))
                else:
                    view.load(info["seed"])
            done = bool(st.get(other + "_done"))
            view.set_other(str(st.get(other) or "?"), st.get(other + "_tg") or [], int(st.get(other + "_t") or 0), done,
                           int(st.get(other + "_ticks") or 0) if done else None)
            # they crashed and you are past them: you win, your run stops here (nothing can hit you any more)
            if done and view.state == "run" and view.x > int(st.get(other + "_x") or 0):
                view.finish_now()
            if st.get("state") == "done" and not info["settled"]:
                info["settled"] = True
                title, line, colour, money = _duel_titles(st, me)
                won = colour == "#3DDC84"

                def result() -> None:
                    try:
                        view.result = (title, line + ("  ·  " + money if money else ""), colour)
                        view.wait()
                        ctx.wave_replayed = did
                        QTimer.singleShot(200, lambda: (setattr(ctx, "wave_done", did), ctx.reload_page("games")))
                    except RuntimeError:
                        pass
                view.message, view.message_col = title + ("  " + money if money else ""), ("#3DDC84" if won else TEXT)
                sfx.play("on" if won else "off")
                ctx.econ.refresh()
                ctx.wave_lobby = None
                if seen or not _replay_for(view, st, result):
                    view.result = (title, line + ("  ·  " + money if money else ""), colour)
                    if view.state not in ("dead", "safe") or seen:
                        view.wait()
                    if not seen:
                        QTimer.singleShot(1500, result)
        except RuntimeError:
            pass

    def poll() -> None:
        def got(ok: bool, data) -> None:
            if ok and isinstance(data, dict):
                show(data)
            elif not ok and "gone" in str(data).lower():
                ctx.wave_duel = None
                ctx.reload_page("games")
        if info["run"] and view.state == "run":
            bar.mine_x = view.x
            ctx.online.ask("rb_wave_ping", {"run": info["run"], "x": view.x, "toggles": list(view.toggles), "t": view.t}, got)
        else:
            ctx.online.ask("rb_wave_state", {"did": did}, got)
    timer = QTimer(view)
    timer.setInterval(450)
    timer.timeout.connect(poll)
    timer.start()
    poll()

    def ended(ticks: int, toggles: list, x: int) -> None:
        if info["ended"] or not info["run"]:
            return
        info["ended"] = True
        bar.mine_x = x
        if view.state != "safe":
            view.message, view.message_col = tr("Waiting for the other player…"), TEXT_DIM

        def done(ok: bool, data) -> None:
            if not ok:
                ctx.toast(tr(str(data)), "warn")
            poll()
        ctx.econ.call("rb_wave_finish", {"run": info["run"], "toggles": toggles, "ticks": ticks}, done)
    view.on_end = ended
    view.wait(tr("Starting…"))
    finished = getattr(ctx, "wave_done", None) == did
    if finished:
        back = Button(tr("Back to the duels"), "primary", 34)
        back.clicked.connect(leave_screen)
        lay.addWidget(back)
    else:
        quit_ = Button(tr("Leave the duel"), "ghost", 30)

        def leave() -> None:
            if bar.st.get("state") != "live" or info["ended"]:       # your run is in: leaving loses nothing
                return leave_screen()

            def go() -> None:
                ctx.online.ask("rb_wave_leave", {"did": did}, lambda _o, _d: ctx.econ.refresh())
                leave_screen()
            ctx.window.confirm(tr("Leave? The other player wins the duel."), go, yes=tr("Leave"))
        quit_.clicked.connect(leave)
        lay.addWidget(quit_)


def _watch_run(page, lay, did: str, leave_screen) -> None:
    """4.5: watch a duel being played: both waves, a moment behind (so what you see is what really happened)."""
    ctx = page.ctx
    bar = _DuelBar(page.W)
    lay.addWidget(bar)
    view = WaveView(page, page.W)
    view.setCursor(Qt.CursorShape.ArrowCursor)
    view.keys.names = []
    lay.addWidget(view)
    info = {"settled": False}

    def show(st: dict) -> None:
        try:
            bar.st = dict(st, me="a")
            bar.update()
            if view.course is None and st.get("seed") is not None:
                view.load(int(st["seed"]))
                view.state = "watch"
                view.watch = [WaveRunner(view.course, st.get("a") or "?"), WaveRunner(view.course, st.get("b") or "?"),
                              time.monotonic() - float(st.get("since") or 0)]
            if view.watch is None:
                return
            for i, side in enumerate(("a", "b")):
                done = bool(st.get(side + "_done"))
                view.watch[i].set(st.get(side + "_tg") or [], int(st.get(side + "_t") or 0), done,
                                  int(st.get(side + "_ticks") or 0) if done else None)
            view.update()
            if st.get("state") == "done" and not info["settled"]:
                info["settled"] = True
                title, line, colour, _m = _duel_titles(st, None)

                def result() -> None:
                    try:
                        view.result = (title, line, colour)
                        view.wait()
                    except RuntimeError:
                        pass
                if not _replay_for(view, st, result):
                    result()
        except RuntimeError:
            pass

    def poll() -> None:
        def got(ok: bool, data) -> None:
            if ok and isinstance(data, dict):
                show(data)
            elif not ok:
                try:
                    if not info["settled"]:
                        view.wait(tr("This duel is over"))
                except RuntimeError:
                    pass
        if not info["settled"]:
            ctx.online.ask("rb_wave_watch", {"did": did}, got)
    timer = QTimer(view)
    timer.setInterval(600)
    timer.timeout.connect(poll)
    timer.start()
    poll()
    view.wait(tr("Loading…"))
    back = Button(tr("Back to the duels"), "ghost", 32)
    back.clicked.connect(leave_screen)
    lay.addWidget(back)
