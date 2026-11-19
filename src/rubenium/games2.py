"""2.4 games: the new Beat Tap (four lanes), Memory, the scratch card and duels between friends.

Every score is worked out by the server: the app only sends what you pressed and when."""
import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QGridLayout, QWidget

from .core import S, sfx, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, mix, tr, ui
from .econ import RARITY_COLOURS, RARITY_NAMES
from .shop import CoinBar, GOLD_TEXT, clock_text
from .wallet import coins_text, paint_coin
from .widgets import Button, IconButton, Label, Segmented, SliderRow, draw_icon, hbox, vbox

TAP_MODES = [("normal", "Normal", "The classic: faster and faster."), ("rush", "Rush", "Much faster, many more notes."),
             ("holds", "Long notes", "Lots of notes to hold down."), ("chords", "Chords", "Two notes at once, very often.")]
MEM_THEMES = [("shapes", "Shapes"), ("numbers", "Numbers"), ("colours", "Colours")]
LANE_KEYS = [Qt.Key.Key_D, Qt.Key.Key_F, Qt.Key.Key_J, Qt.Key.Key_K]
LANE_NAMES = ["D", "F", "J", "K"]
LANE_COLOURS = ["#FF5C8A", "#4FC3FF", "#5BE08A", "#FFB547"]


def window_text(day: dict) -> str:
    """'Next 2 hours: 40 / 150 coins' for the mini game limits."""
    day = day or {}
    return tr("These 2 hours: {n} / {cap} coins", n=coins_text(int(day.get("paid") or 0)),
              cap=coins_text(int(day.get("cap") or 150)))


# ================================================================ Beat Tap 2
class BeatRush(QWidget):
    """Four lanes. Notes fall to the line: press D F J K (or click the lane) as they touch it. Long notes are held.
    Notes come faster and faster; hits in a row build a combo."""
    LEAD = 1.15                                   # seconds a note takes to fall

    def __init__(self, page, on_end=None) -> None:
        super().__init__()
        self.page, self.ctx, self.on_end = page, page.ctx, on_end
        self.setFixedSize(page.W, S(320))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.state = "idle"                       # idle -> wait -> count -> play -> send -> done
        self.chart: list = []
        self.round = ""
        self.hits: dict = {}                      # note -> {"i", "t", "u"}
        self.judged: dict = {}                    # note -> "p" / "g" / "o" / "m"
        self.holding: dict = {}                   # lane -> note being held
        self.pressed = [0.0] * 4                  # when each lane was last pressed (for the glow)
        self.pops: list = []
        self.sparks: list = []
        self.combo = self.best = 0
        self.t0 = 0.0
        self.result: dict = {}
        self.duel = False
        self._frames = QTimer(self)
        self._frames.setTimerType(Qt.TimerType.PreciseTimer)
        self._frames.setInterval(16)
        self._frames.timeout.connect(self._tick)
        from .widgets import KeyPoll                       # 4.5: D F J K and Space, read straight from the keyboard
        self.keys = KeyPoll(["D", "F", "J", "K", "Space"], self._key, lambda: self.state in ("count", "play"))
        self.keys.setParent(self)
        self.on_space = None                               # the page's Start button

    def _key(self, name: str, down: bool) -> None:
        if name == "Space":
            if down and self.state in ("idle", "done") and not self.duel:
                (self.on_space or self.start)()
            return
        lane = "DFJK".index(name)
        if down:
            self.pressed[lane] = time.monotonic()
            if self.state == "play":
                self._press(lane)
        else:
            self._release(lane)

    # -- rounds
    def start(self) -> None:
        if self.state in ("wait", "count", "play", "send"):
            return
        self.state = "wait"
        self.update()
        sent = time.monotonic()

        def got(ok: bool, data) -> None:
            if not ok or not isinstance(data, dict):
                self.state = "idle"
                self.update()
                return self.ctx.toast(tr(str(data)), "warn")
            self.begin(data, sent)
        mode = TAP_MODES[int(getattr(self.ctx, "tap_mode", 0) or 0)][0]
        self.ctx.econ.call("rb_tap_start", {"mode": mode}, got)

    def begin(self, data: dict, sent: float, duel: bool = False) -> None:
        now = time.monotonic()
        self.t0 = sent + (now - sent) / 2              # the server started its clock about half-way
        self.round, self.chart, self.duel = data["round"], list(data.get("chart") or []), duel
        self.hits, self.judged, self.holding, self.pops, self.sparks = {}, {}, {}, [], []
        self.combo = self.best = 0
        self.result = {}
        self.state = "play"
        if not self.keys.live:                         # 4.5: on Windows the keys are read directly (KeyPoll)
            self.ctx.window.allow_keys(True)
            self.setFocus(Qt.FocusReason.OtherFocusReason)
            self.grabKeyboard()
        self._frames.start()

    def abort(self) -> None:
        self._frames.stop()
        self.state = "idle"
        self.releaseKeyboard()

    def hideEvent(self, _e) -> None:
        self._frames.stop()
        self.releaseKeyboard()

    def _ms(self) -> float:
        return (time.monotonic() - self.t0) * 1000

    def _end_ms(self) -> float:
        if not self.chart:
            return 1.0
        return max(n["t"] + n["h"] for n in self.chart) + 900

    def _tick(self) -> None:
        if self.state == "play":
            ms = self._ms()
            for i, n in enumerate(self.chart):           # notes that went past without a press
                if i not in self.judged and ms > n["t"] + 260:
                    self.judged[i] = "m"
                    self.combo = 0
                    self._pop(n["l"], tr("MISS"), "#FF5C6C")
            for lane, i in list(self.holding.items()):   # holds that reached their end
                n = self.chart[i]
                if ms >= n["t"] + n["h"]:
                    self.hits[i]["u"] = int(ms)
                    del self.holding[lane]
                    self._burst(lane, LANE_COLOURS[lane], 10)
            if ms > self._end_ms():
                self._send()
        self.update()
        if self.state in ("idle", "done") and not self.pops and not self.sparks:
            self._frames.stop()

    def _send(self) -> None:
        self.state = "send"
        self.releaseKeyboard()
        for lane, i in list(self.holding.items()):
            self.hits[i]["u"] = int(self._ms())
        self.holding = {}
        hits = list(self.hits.values())

        def got(ok: bool, data) -> None:
            self.state = "done"
            if not ok:
                self.ctx.toast(tr(str(data)), "warn")
                data = {}
            self.result = data if isinstance(data, dict) else {}
            if int(self.result.get("paid") or 0):
                sfx.play("on")
            self._frames.start()
            if self.on_end:
                self.on_end(self.result)
        self.ctx.econ.call("rb_tap_finish", {"round": self.round, "hits": hits}, got)

    # -- input
    def _press(self, lane: int) -> None:
        if self.state != "play":
            return
        ms = self._ms()
        self.pressed[lane] = time.monotonic()
        best, gap = -1, 1e9
        for i, n in enumerate(self.chart):
            if n["l"] != lane or i in self.judged:
                continue
            d = abs(ms - n["t"])
            if d <= 260 and d < gap:
                best, gap = i, d
            if n["t"] > ms + 300:
                break
        if best < 0:
            return
        n = self.chart[best]
        self.hits[best] = {"i": best, "t": int(ms)}
        kind, text, col = (("p", "PERFECT", "#5BE08A") if gap <= 80 else
                           (("g", "GREAT", "#4FC3FF") if gap <= 160 else ("o", "GOOD", GOLD_TEXT)))
        self.judged[best] = kind
        self.combo += 1
        self.best = max(self.best, self.combo)
        if n["h"]:
            self.holding[lane] = best
        sfx.play("pick")
        self._pop(lane, tr(text), col)
        self._burst(lane, LANE_COLOURS[lane], 14 if kind == "p" else 8)

    def _release(self, lane: int) -> None:
        if lane in self.holding:
            i = self.holding.pop(lane)
            self.hits[i]["u"] = int(self._ms())

    def keyPressEvent(self, e) -> None:
        if e.isAutoRepeat() or self.keys.live:
            return
        if e.key() in LANE_KEYS:
            self._press(LANE_KEYS.index(e.key()))
        elif e.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return) and self.state in ("idle", "done") and not self.duel:
            self.start()
        else:
            super().keyPressEvent(e)

    def keyReleaseEvent(self, e) -> None:
        if not e.isAutoRepeat() and not self.keys.live and e.key() in LANE_KEYS:
            self._release(LANE_KEYS.index(e.key()))

    def _lane_at(self, x: float) -> int:
        return max(0, min(3, int((x - self._board().left()) / (self._board().width() / 4))))

    def mousePressEvent(self, e) -> None:
        e.accept()
        self.setFocus()
        if e.button() == Qt.MouseButton.LeftButton:
            self._mouse_lane = self._lane_at(e.position().x())
            self._press(self._mouse_lane)

    def mouseReleaseEvent(self, e) -> None:
        lane = getattr(self, "_mouse_lane", None)
        if lane is not None:
            self._release(lane)
            self._mouse_lane = None

    # -- effects
    def _pop(self, lane: int, text: str, col: str) -> None:
        self.pops.append((lane, time.monotonic(), text, col))

    def _burst(self, lane: int, col: str, n: int) -> None:
        b = self._board()
        x = b.left() + b.width() / 4 * (lane + 0.5)
        y = self._line_y()
        now = time.monotonic()
        for _ in range(n):
            a = random.uniform(math.pi * 1.05, math.pi * 1.95)
            v = random.uniform(S(60), S(170))
            self.sparks.append((x, y, math.cos(a) * v, math.sin(a) * v, now, col))

    # -- drawing
    def _board(self) -> QRectF:
        return QRectF(self.rect()).adjusted(S(6), S(6), -S(6), -S(6))

    def _line_y(self) -> float:
        return self._board().bottom() - S(44)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        b = self._board()
        now = time.monotonic()
        ms = self._ms() if self.state in ("play", "send") else 0.0
        # background: dark, with a soft pulse on the beat once it gets going
        g = QLinearGradient(b.topLeft(), b.bottomLeft())
        g.setColorAt(0, QColor("#07090C"))
        g.setColorAt(1, QColor("#10141A"))
        p.setPen(QPen(alpha("#FFFFFF", 0.08), 1))
        p.setBrush(g)
        p.drawRoundedRect(b, S(12), S(12))
        lw = b.width() / 4
        line = self._line_y()
        speed = (line - b.top()) / (self.LEAD * 1000)
        for lane in range(4):
            x = b.left() + lw * lane
            col = QColor(LANE_COLOURS[lane])
            glow = max(0.0, 1 - (now - self.pressed[lane]) / 0.25)
            lg = QLinearGradient(QPointF(0, b.top()), QPointF(0, line))
            lg.setColorAt(0, alpha(col, 0.0))
            lg.setColorAt(1, alpha(col, 0.07 + 0.22 * glow))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(lg)
            p.drawRect(QRectF(x + 1, b.top() + S(4), lw - 2, line - b.top()))
            if lane:
                p.setPen(QPen(alpha("#FFFFFF", 0.05), 1))
                p.drawLine(QPointF(x, b.top() + S(8)), QPointF(x, b.bottom() - S(8)))
            # the key under each lane
            key = QRectF(x + lw / 2 - S(16), line + S(10), S(32), S(24))
            p.setPen(QPen(alpha(col, 0.35 + 0.65 * glow), S(1.4)))
            p.setBrush(alpha(col, 0.08 + 0.35 * glow))
            p.drawRoundedRect(key, S(6), S(6))
            p.setPen(QColor(TEXT) if glow > 0.2 else alpha(col, 0.9))
            p.setFont(font(11, QFont.Weight.ExtraBold))
            p.drawText(key, int(Qt.AlignmentFlag.AlignCenter), LANE_NAMES[lane])
        # the hit line
        p.setPen(QPen(alpha(ui.accent, 0.9), S(2.2)))
        p.drawLine(QPointF(b.left() + S(6), line), QPointF(b.right() - S(6), line))
        # notes
        if self.state in ("play", "send"):
            for i, n in enumerate(self.chart):
                dt = n["t"] - ms
                if dt > self.LEAD * 1000 + 50:
                    break
                lane, col = n["l"], QColor(LANE_COLOURS[n["l"]])
                held = self.holding.get(lane) == i
                if self.judged.get(i) not in (None, "m") and not held and not (n["h"] and i in self.hits and "u" not in self.hits[i]):
                    continue
                y = line - dt * speed
                x = b.left() + lw * lane
                if n["h"]:
                    top = line - (n["t"] + n["h"] - ms) * speed
                    bottom = line if held else y
                    if bottom > b.top():
                        tail = QRectF(x + lw * 0.34, max(b.top(), top), lw * 0.32, max(0.0, bottom - max(b.top(), top)))
                        p.setPen(Qt.PenStyle.NoPen)
                        p.setBrush(alpha(col, 0.75 if held else 0.4))
                        p.drawRoundedRect(tail, S(4), S(4))
                    if held:
                        continue
                if self.judged.get(i) == "m":
                    p.setOpacity(max(0.0, 1 + dt / 260))
                head = QRectF(x + S(6), y - S(8), lw - S(12), S(16))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha(col, 0.28))
                p.drawRoundedRect(head.adjusted(-S(3), -S(3), S(3), S(3)), S(9), S(9))
                hg = QLinearGradient(head.topLeft(), head.bottomLeft())
                hg.setColorAt(0, mix(col, QColor("#FFFFFF"), 0.45))
                hg.setColorAt(1, col)
                p.setBrush(hg)
                p.drawRoundedRect(head, S(7), S(7))
                p.setOpacity(1.0)
        # sparks and words
        keep = []
        for x, y, vx, vy, born, col in self.sparks:
            age = now - born
            if age < 0.5:
                keep.append((x, y, vx, vy, born, col))
                p.setOpacity(1 - age / 0.5)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(col))
                p.drawEllipse(QPointF(x + vx * age, y + vy * age + S(220) * age * age), S(2.2), S(2.2))
        self.sparks = keep
        p.setOpacity(1.0)
        keep = []
        for lane, born, text, col in self.pops:
            age = now - born
            if age < 0.6:
                keep.append((lane, born, text, col))
                p.setOpacity(1 - age / 0.6)
                p.setPen(QColor(col))
                p.setFont(font(10, QFont.Weight.ExtraBold))
                x = b.left() + lw * lane
                p.drawText(QRectF(x - S(10), line - S(46) - S(18) * age, lw + S(20), S(16)), int(Qt.AlignmentFlag.AlignCenter), text)
        self.pops = keep
        p.setOpacity(1.0)
        if self.state in ("play", "send"):
            if self.combo >= 5:                                     # combo counter
                p.setPen(alpha("#FFFFFF", 0.85))
                p.setFont(font(24 + min(10, self.combo // 10 * 2), QFont.Weight.Black))
                p.drawText(QRectF(b.left(), b.top() + S(30), b.width(), S(40)), int(Qt.AlignmentFlag.AlignCenter), str(self.combo))
                p.setPen(alpha(ui.accent, 0.9))
                p.setFont(font(9, QFont.Weight.Bold))
                p.drawText(QRectF(b.left(), b.top() + S(68), b.width(), S(14)), int(Qt.AlignmentFlag.AlignCenter), tr("COMBO"))
            bar = QRectF(b.left() + S(10), b.top() + S(8), b.width() - S(20), S(4))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha("#FFFFFF", 0.08))
            p.drawRoundedRect(bar, S(2), S(2))
            p.setBrush(ui.accent)
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * min(1.0, ms / self._end_ms()), bar.height()), S(2), S(2))
        if self.state in ("idle", "wait", "send", "done"):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha("#000000", 0.55))
            p.drawRoundedRect(b, S(12), S(12))
            self._draw_card(p, b)

    def _draw_card(self, p: QPainter, b: QRectF) -> None:
        c = b.center()
        if self.state == "done" and self.result:
            res = self.result
            pct = int(res.get("pct") or 0)
            p.setPen(QColor(TEXT))
            p.setFont(font(26, QFont.Weight.Black))
            p.drawText(QRectF(b.left(), c.y() - S(96), b.width(), S(36)), int(Qt.AlignmentFlag.AlignCenter), f"{pct}%")
            grade = "S" if pct >= 95 else "A" if pct >= 85 else "B" if pct >= 70 else "C" if pct >= 50 else "D"
            p.setPen(QColor({"S": GOLD_TEXT, "A": "#5BE08A", "B": "#4FC3FF", "C": TEXT_DIM, "D": "#FF5C6C"}[grade]))
            p.setFont(font(13, QFont.Weight.ExtraBold))
            p.drawText(QRectF(b.left(), c.y() - S(60), b.width(), S(18)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("Grade {g}", g=grade) + "  ·  " + tr("Best combo {n}", n=res.get("combo", 0)))
            p.setFont(font(10, QFont.Weight.DemiBold))
            parts = [("PERFECT", res.get("perfect", 0), "#5BE08A"), ("GREAT", res.get("great", 0), "#4FC3FF"),
                     ("GOOD", res.get("good", 0), GOLD_TEXT), ("MISS", res.get("miss", 0), "#FF5C6C")]
            w = b.width() / 4
            for k, (name, n, col) in enumerate(parts):
                r = QRectF(b.left() + w * k, c.y() - S(34), w, S(30))
                p.setPen(QColor(col))
                p.drawText(QRectF(r.left(), r.top(), r.width(), S(14)), int(Qt.AlignmentFlag.AlignCenter), tr(name))
                p.setPen(QColor(TEXT))
                p.drawText(QRectF(r.left(), r.top() + S(14), r.width(), S(16)), int(Qt.AlignmentFlag.AlignCenter), str(n))
            paid = int(res.get("paid") or 0)
            p.setPen(QColor(GOLD_TEXT if paid else TEXT_DIM))
            p.setFont(font(20, QFont.Weight.ExtraBold))
            text = tr("Duel score sent") if res.get("duel") else ("+" + coins_text(paid) if paid else tr("No coins this time"))
            p.drawText(QRectF(b.left(), c.y() + S(6), b.width(), S(30)), int(Qt.AlignmentFlag.AlignCenter), text)
            if res.get("day"):
                p.setPen(QColor(TEXT_DIM))
                p.setFont(font(10, QFont.Weight.DemiBold))
                p.drawText(QRectF(b.left(), c.y() + S(40), b.width(), S(16)), int(Qt.AlignmentFlag.AlignCenter), window_text(res["day"]))
            return
        p.setPen(QColor(TEXT))
        p.setFont(font(15, QFont.Weight.Bold))
        text = {"wait": tr("Get ready…"), "send": tr("Counting…")}.get(self.state, tr("Press Start"))
        p.drawText(QRectF(b.left(), c.y() - S(40), b.width(), S(24)), int(Qt.AlignmentFlag.AlignCenter), text)
        if self.state == "idle":
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(10.5, QFont.Weight.DemiBold))
            p.drawText(QRectF(b.left() + S(16), c.y() - S(10), b.width() - S(32), S(60)),
                       int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap),
                       tr("Press D F J K (or click the lanes) when a note touches the line. Hold the long ones."))


# ================================================================ Memory
SYMBOLS = ["#FF5C8A", "#4FC3FF", "#5BE08A", "#FFB547", "#B36BFF", "#FF8A3D", "#2EE6D6", "#F4F04A",
           "#FF5CC8", "#8CFF2E", "#6A8CFF", "#E6EEF5"]


def paint_symbol(p: QPainter, kind: int, c: QPointF, r: float, theme: str = "shapes") -> None:
    """One of 12 pictures: shapes, numbers or colours (the Memory card style)."""
    col = QColor(SYMBOLS[kind % 12])
    if theme == "numbers":
        p.save()
        p.setPen(col)
        f = QFont(font(12, QFont.Weight.Black))
        f.setPixelSize(max(6, int(r * 1.5)))
        p.setFont(f)
        p.drawText(QRectF(c.x() - r * 1.5, c.y() - r * 1.5, r * 3, r * 3), int(Qt.AlignmentFlag.AlignCenter), str(kind + 1))
        p.restore()
        return
    if theme == "colours":
        p.save()
        p.setPen(QPen(QColor("#FFFFFF"), max(1.0, r * 0.08)))
        g = QRadialGradient(QPointF(c.x() - r * 0.3, c.y() - r * 0.3), r * 1.4)
        g.setColorAt(0, mix(col, QColor("#FFFFFF"), 0.35))
        g.setColorAt(1, col)
        p.setBrush(g)
        p.drawEllipse(c, r, r)
        p.restore()
        return
    p.save()
    p.translate(c)
    p.setPen(Qt.PenStyle.NoPen)
    glow = QRadialGradient(QPointF(0, 0), r * 1.6)
    glow.setColorAt(0, alpha(col, 0.35))
    glow.setColorAt(1, alpha(col, 0.0))
    p.setBrush(glow)
    p.drawEllipse(QPointF(0, 0), r * 1.6, r * 1.6)
    p.setBrush(col)
    path = QPainterPath()
    if kind == 0:
        path.addEllipse(QPointF(0, 0), r, r)
    elif kind == 1:
        path.addRoundedRect(QRectF(-r * 0.85, -r * 0.85, r * 1.7, r * 1.7), r * 0.25, r * 0.25)
    elif kind == 2:
        path.moveTo(0, -r); path.lineTo(r * 0.95, r * 0.8); path.lineTo(-r * 0.95, r * 0.8); path.closeSubpath()
    elif kind == 3:
        path.moveTo(0, -r); path.lineTo(r * 0.8, 0); path.lineTo(0, r); path.lineTo(-r * 0.8, 0); path.closeSubpath()
    elif kind == 4:
        for k in range(10):
            a = -math.pi / 2 + k * math.pi / 5
            rr = r if k % 2 == 0 else r * 0.45
            pt = QPointF(math.cos(a) * rr, math.sin(a) * rr)
            path.moveTo(pt) if k == 0 else path.lineTo(pt)
        path.closeSubpath()
    elif kind == 5:                                               # heart
        path.moveTo(0, r * 0.9)
        path.cubicTo(-r * 1.3, -r * 0.1, -r * 0.5, -r * 1.1, 0, -r * 0.35)
        path.cubicTo(r * 0.5, -r * 1.1, r * 1.3, -r * 0.1, 0, r * 0.9)
    elif kind == 6:                                               # ring
        path.addEllipse(QPointF(0, 0), r, r)
        inner = QPainterPath()
        inner.addEllipse(QPointF(0, 0), r * 0.5, r * 0.5)
        path = path.subtracted(inner)
    elif kind == 7:                                               # plus
        w = r * 0.38
        path.addRect(QRectF(-w, -r, 2 * w, 2 * r))
        path.addRect(QRectF(-r, -w, 2 * r, 2 * w))
        path = path.simplified()
    elif kind == 8:                                               # hexagon
        for k in range(6):
            a = k * math.pi / 3
            pt = QPointF(math.cos(a) * r, math.sin(a) * r)
            path.moveTo(pt) if k == 0 else path.lineTo(pt)
        path.closeSubpath()
    elif kind == 9:                                               # moon
        path.addEllipse(QPointF(0, 0), r, r)
        cut = QPainterPath()
        cut.addEllipse(QPointF(r * 0.45, -r * 0.3), r * 0.85, r * 0.85)
        path = path.subtracted(cut)
    elif kind == 10:                                              # bolt
        pts = [(0.25, -1), (-0.6, 0.15), (-0.05, 0.15), (-0.3, 1), (0.6, -0.2), (0.05, -0.2)]
        path.moveTo(pts[0][0] * r, pts[0][1] * r)
        for x, y in pts[1:]:
            path.lineTo(x * r, y * r)
        path.closeSubpath()
    else:                                                         # music note
        path.addEllipse(QPointF(-r * 0.3, r * 0.55), r * 0.42, r * 0.32)
        path.addRect(QRectF(r * 0.02, -r, r * 0.18, r * 1.55))
        path.addRect(QRectF(r * 0.02, -r, r * 0.65, r * 0.22))
        path = path.simplified()
    p.drawPath(path)
    p.restore()


class MemoryGame(QWidget):
    """Find the pairs. The server keeps the board and shows one card at a time, so nothing can be peeked."""

    def __init__(self, page, on_end=None) -> None:
        super().__init__()
        self.page, self.ctx, self.on_end = page, page.ctx, on_end
        self.setFixedSize(page.W, S(300))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.state = "idle"                       # idle -> busy -> play -> done
        self.round = ""
        self.n, self.cols = 16, 4
        self.faces: dict = {}                     # card -> symbol shown now
        self.found: set = set()
        self.flip_at: dict = {}                   # card -> when it turned (for the animation)
        self.wait = False
        self.flips = 0
        self.t0 = 0.0
        self.result: dict = {}
        self.duel = False
        self._t = QTimer(self)
        self._t.setInterval(16)
        self._t.timeout.connect(self._tick)

    def start(self) -> None:
        if self.state == "busy":
            return
        self.state = "busy"
        tier = int(getattr(self.ctx, "mem_tier", 0) or 0) + 1

        def got(ok: bool, data) -> None:
            if not ok or not isinstance(data, dict):
                self.state = "idle"
                self.update()
                return self.ctx.toast(tr(str(data)), "warn")
            self.begin(data)
        self.ctx.econ.call("rb_mem_start", {"tier": tier}, got)

    def begin(self, data: dict, duel: bool = False) -> None:
        self.round, self.n, self.cols, self.duel = data["round"], int(data["cards"]), int(data["cols"]), duel
        self.faces, self.found, self.flip_at, self.wait, self.flips, self.result = {}, set(), {}, False, 0, {}
        self.t0 = time.monotonic()
        self.state = "play"
        self._t.start()
        self.update()

    def _rows(self) -> int:
        return math.ceil(self.n / self.cols)

    def _cell(self, i: int) -> QRectF:
        rows = self._rows()
        gap = S(6)
        w = min((self.width() - gap * (self.cols + 1)) / self.cols, (self.height() - S(24) - gap * (rows + 1)) / rows)
        ox = (self.width() - (w * self.cols + gap * (self.cols - 1))) / 2
        r, c = divmod(i, self.cols)
        return QRectF(ox + c * (w + gap), S(22) + gap + r * (w + gap), w, w)

    def mousePressEvent(self, e) -> None:
        e.accept()
        if self.state != "play" or self.wait or e.button() != Qt.MouseButton.LeftButton:
            return
        for i in range(self.n):
            if self._cell(i).contains(e.position()):
                if i in self.found or i in self.faces:
                    return
                return self._flip(i)

    def _flip(self, i: int) -> None:
        self.wait = True

        def got(ok: bool, data) -> None:
            self.wait = False
            if not ok or not isinstance(data, dict):
                self.ctx.toast(tr(str(data)), "warn")
                return self.update()
            self.faces[i] = int(data["sym"])
            self.flip_at[i] = time.monotonic()
            sfx.play("pick")
            if data.get("first"):
                return self.update()
            self.flips = int(data.get("flips") or self.flips + 2)
            other = int(data.get("other", -1))
            if data.get("match"):
                self.found |= {i, other}
                sfx.play("on")
                if data.get("done"):
                    self.state = "done"
                    self.result = data
                    if self.on_end:
                        self.on_end(data)
                    QTimer.singleShot(250, self.update)
            else:
                self.wait = True                              # look at both for a moment, then turn them back

                def hide() -> None:
                    for k in (i, other):
                        self.faces.pop(k, None)
                        self.flip_at[k] = time.monotonic()
                    self.wait = False
                    self.update()
                QTimer.singleShot(700, hide)
            self.update()
        self.ctx.econ.call("rb_mem_flip", {"round": self.round, "card": i}, got)

    def _tick(self) -> None:
        self.update()
        if self.state != "play" and not any(time.monotonic() - t < 0.3 for t in self.flip_at.values()):
            self._t.stop()

    def hideEvent(self, _e) -> None:
        self._t.stop()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        if self.state in ("play", "done"):
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(10.5, QFont.Weight.DemiBold))
            secs = (now - self.t0) if self.state == "play" else float(self.result.get("secs") or 0)
            p.drawText(QRectF(S(4), 0, self.width() - S(8), S(18)), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                       tr("Pairs {a} / {b}", a=len(self.found) // 2, b=self.n // 2))
            p.drawText(QRectF(S(4), 0, self.width() - S(8), S(18)), int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                       tr("{n} flips", n=self.flips) + f"  ·  {int(secs)} s")
            for i in range(self.n):
                r = self._cell(i)
                k = min(1.0, (now - self.flip_at.get(i, 0)) / 0.25)
                face = i in self.faces or i in self.found
                squeeze = abs(math.cos(k * math.pi)) if k < 1 else 1.0
                showing = face if k >= 0.5 else not face
                rr = QRectF(r.center().x() - r.width() / 2 * squeeze, r.top(), r.width() * squeeze, r.height())
                if showing:
                    sym = self.faces.get(i)
                    col = QColor(SYMBOLS[sym % 12]) if sym is not None else QColor(TEXT_DIM)
                    p.setPen(QPen(alpha(col, 0.9 if i in self.found else 0.5), S(1.6)))
                    p.setBrush(QColor("#12161C"))
                    p.drawRoundedRect(rr, S(8), S(8))
                    if sym is not None and squeeze > 0.2:
                        p.save()
                        p.translate(rr.center())
                        p.scale(squeeze, 1)
                        paint_symbol(p, sym, QPointF(0, 0), r.width() * 0.26,
                                     MEM_THEMES[int(getattr(self.ctx, "mem_theme", 0) or 0)][0])
                        p.restore()
                else:
                    g = QLinearGradient(rr.topLeft(), rr.bottomRight())
                    g.setColorAt(0, mix(ui.accent, QColor("#1A1F26"), 0.55))
                    g.setColorAt(1, QColor("#1A1F26"))
                    p.setPen(QPen(alpha(ui.accent, 0.35), S(1.2)))
                    p.setBrush(g)
                    p.drawRoundedRect(rr, S(8), S(8))
                    if squeeze > 0.5:
                        p.setPen(alpha("#FFFFFF", 0.25))
                        p.setFont(font(14, QFont.Weight.Black))
                        p.drawText(rr, int(Qt.AlignmentFlag.AlignCenter), "R")
        if self.state == "done" and self.result:
            b = QRectF(self.rect()).adjusted(S(20), S(70), -S(20), -S(70))
            p.setPen(QPen(alpha(ui.accent, 0.6), S(1.4)))
            p.setBrush(alpha("#07090C", 0.92))
            p.drawRoundedRect(b, S(12), S(12))
            res = self.result
            p.setPen(QColor(TEXT))
            p.setFont(font(14, QFont.Weight.Bold))
            p.drawText(QRectF(b.left(), b.top() + S(12), b.width(), S(22)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("All pairs in {n} flips", n=res.get("flips", 0)))
            paid = int(res.get("paid") or 0)
            p.setPen(QColor(GOLD_TEXT if paid else TEXT_DIM))
            p.setFont(font(20, QFont.Weight.ExtraBold))
            text = tr("Duel score sent") if res.get("duel") else ("+" + coins_text(paid) if paid else tr("No coins this time"))
            p.drawText(QRectF(b.left(), b.top() + S(40), b.width(), S(30)), int(Qt.AlignmentFlag.AlignCenter), text)
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(10, QFont.Weight.DemiBold))
            line = tr("Perfect is {n} flips", n=res.get("perfect", self.n)) if not res.get("duel") else tr("{s} seconds", s=res.get("secs", 0))
            if res.get("day"):
                line += "  ·  " + window_text(res["day"])
            p.drawText(QRectF(b.left(), b.top() + S(74), b.width(), S(18)), int(Qt.AlignmentFlag.AlignCenter), line)
        elif self.state in ("idle", "busy"):
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(13, QFont.Weight.Bold))
            p.drawText(QRectF(self.rect()), int(Qt.AlignmentFlag.AlignCenter),
                       tr("Loading…") if self.state == "busy" else tr("Press Start"))


# ================================================================ scratch card (every 12 hours)
class ScratchCard(QWidget):
    """A silver card. Scratch it with the mouse: it is hard at first, then easier and easier. Under it: a rarity
    colour and the prize (coins or keys). The server decides the prize when you start scratching."""
    COLS, ROWS = 30, 16

    def __init__(self, page) -> None:
        super().__init__()
        self.page, self.ctx = page, page.ctx
        self.setFixedSize(page.W, S(170))
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.prize: dict = {}
        self.asked = False
        self.cleared = 0
        self.done = False
        self.grid = [[False] * self.COLS for _ in range(self.ROWS)]
        self.cover = None
        self.last = None
        self.done_at = 0.0
        self._t = QTimer(self)
        self._t.setInterval(16)
        self._t.timeout.connect(self.update)

    def _card(self) -> QRectF:
        return QRectF(self.rect()).adjusted(S(4), S(4), -S(4), -S(4))

    def _make_cover(self) -> None:
        r = self._card()
        img = QImage(int(r.width()), int(r.height()), QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, r.width(), r.height())
        for k, c in enumerate(["#9AA3AD", "#D9DEE3", "#8B949E", "#C9CFD6", "#9AA3AD"]):
            g.setColorAt(k / 4, QColor(c))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(QRectF(0, 0, r.width(), r.height()), S(12), S(12))
        rnd = random.Random(7)
        p.setPen(QPen(alpha("#FFFFFF", 0.18), 1))
        for _ in range(140):
            x, y = rnd.uniform(0, r.width()), rnd.uniform(0, r.height())
            p.drawLine(QPointF(x, y), QPointF(x + rnd.uniform(-6, 6), y + rnd.uniform(-6, 6)))
        p.setPen(QColor("#5C6670"))
        p.setFont(font(15, QFont.Weight.Black))
        p.drawText(QRectF(0, 0, r.width(), r.height()), int(Qt.AlignmentFlag.AlignCenter), tr("SCRATCH ME"))
        p.end()
        self.cover = img

    def ready(self) -> bool:
        return int(getattr(self.ctx.econ, "scratch_in", 0) or 0) <= 0

    def _brush(self) -> float:
        frac = self.cleared / (self.COLS * self.ROWS)
        return S(6) + S(34) * frac ** 1.3                   # small at first, then bigger and bigger

    def mousePressEvent(self, e) -> None:
        e.accept()
        if self.done or not self.ready() and not self.prize:
            return
        if not self.asked:
            self.asked = True

            def got(ok: bool, data) -> None:
                if not ok or not isinstance(data, dict):
                    self.asked = False
                    return self.ctx.toast(tr(str(data)) if "countdown" not in str(data) else tr("Not ready yet"), "warn")
                self.prize = data
                self.ctx.econ.scratch_in = int(data.get("next") or 43200)
                self.update()
            self.ctx.econ.call("rb_scratch", {}, got, hold=True)
        self.last = e.position()
        self._scratch(e.position())

    def mouseMoveEvent(self, e) -> None:
        if self.last is None or self.done:
            return
        a, b = self.last, e.position()
        steps = max(1, int(math.hypot(b.x() - a.x(), b.y() - a.y()) / S(3)))
        for k in range(1, steps + 1):
            self._scratch(QPointF(a.x() + (b.x() - a.x()) * k / steps, a.y() + (b.y() - a.y()) * k / steps))
        self.last = b

    def mouseReleaseEvent(self, _e) -> None:
        self.last = None

    def _scratch(self, pos: QPointF) -> None:
        if self.cover is None or not self.prize and self.cleared > self.COLS * self.ROWS * 0.25:
            return                                               # wait for the server before showing too much
        r = self._card()
        x, y = pos.x() - r.left(), pos.y() - r.top()
        rad = self._brush()
        p = QPainter(self.cover)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 255))
        p.drawEllipse(QPointF(x, y), rad, rad)
        p.end()
        cw, ch = r.width() / self.COLS, r.height() / self.ROWS
        for row in range(max(0, int((y - rad) / ch)), min(self.ROWS, int((y + rad) / ch) + 1)):
            for col in range(max(0, int((x - rad) / cw)), min(self.COLS, int((x + rad) / cw) + 1)):
                if not self.grid[row][col] and math.hypot((col + 0.5) * cw - x, (row + 0.5) * ch - y) <= rad:
                    self.grid[row][col] = True
                    self.cleared += 1
        if self.prize and self.cleared >= self.COLS * self.ROWS * 0.62:
            self._finish()
        self.update()

    def _finish(self) -> None:
        self.done = True
        self.done_at = time.monotonic()
        self._t.start()
        QTimer.singleShot(1500, self._t.stop)
        self.ctx.econ.absorb(self.prize)
        self.ctx.econ.changed.emit()
        sfx.play("on")
        c, k = int(self.prize.get("coins_won") or 0), int(self.prize.get("keys_won") or 0)
        cp = self.prize.get("coupon")
        if cp:                                                   # 4.0: an XP coupon too (already in your items)
            from .levels import COUPONS
            self.ctx.econ.refresh()
            QTimer.singleShot(600, lambda: sfx.tune("coupon"))
        if self.prize.get("gold_wheel"):                         # 3.1: the Golden Wheel opens
            from .goldwheel import open_gold_wheel
            QTimer.singleShot(900, lambda: open_gold_wheel(self.ctx))
            return
        text = ("+" + coins_text(c)) if c else tr("+{n} key(s)", n=k)
        if cp:
            text += "  ·  " + tr("+ {what}", what=tr(COUPONS.get(cp, ("XP coupon",))[0]))
        self.ctx.toast(text)

    def reset(self) -> None:
        self.prize, self.asked, self.cleared, self.done, self.last = {}, False, 0, False, None
        self.grid = [[False] * self.COLS for _ in range(self.ROWS)]
        self.cover = None
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._card()
        if not self.ready() and not self.prize:
            p.setPen(QPen(alpha("#FFFFFF", 0.1), 1))
            p.setBrush(QColor("#11151A"))
            p.drawRoundedRect(r, S(12), S(12))
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(13, QFont.Weight.Bold))
            p.drawText(r, int(Qt.AlignmentFlag.AlignCenter),
                       tr("Next scratch card in {t}", t=clock_text(int(self.ctx.econ.scratch_in or 0))))
            return
        rar = self.prize.get("rarity", "standard")
        col = (QColor("#E8B23A") if rar == "golden" else QColor(RARITY_COLOURS.get(rar, "#9AA4AD"))) if self.prize else QColor("#2A3038")
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, mix(col, QColor("#000000"), 0.15))
        g.setColorAt(1, mix(col, QColor("#000000"), 0.6))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(r, S(12), S(12))
        if self.prize:
            if self.done:                                        # a little shine once it is all off
                k = min(1.0, (time.monotonic() - self.done_at) / 1.2)
                x = r.left() + r.width() * (k * 1.6 - 0.3)
                sh = QLinearGradient(QPointF(x - S(40), 0), QPointF(x + S(40), 0))
                sh.setColorAt(0, alpha("#FFFFFF", 0))
                sh.setColorAt(0.5, alpha("#FFFFFF", 0.35 * (1 - k)))
                sh.setColorAt(1, alpha("#FFFFFF", 0))
                p.setBrush(sh)
                p.drawRoundedRect(r, S(12), S(12))
            p.setPen(QColor("#FFFFFF"))
            p.setFont(font(11, QFont.Weight.ExtraBold))
            p.drawText(QRectF(r.left(), r.top() + S(18), r.width(), S(18)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("GOLDEN") if rar == "golden" else tr(RARITY_NAMES.get(rar, "Common")).upper())
            c, k = int(self.prize.get("coins_won") or 0), int(self.prize.get("keys_won") or 0)
            p.setFont(font(26, QFont.Weight.Black))
            p.drawText(QRectF(r.left(), r.center().y() - S(20), r.width(), S(40)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("Golden Wheel!") if rar == "golden" else
                       coins_text(c) + " " + tr("coins") if c else tr("{n} key(s)", n=k))
            if self.prize.get("coupon"):                          # 4.0: and an XP coupon
                from .levels import COUPONS
                p.setFont(font(11, QFont.Weight.Bold))
                p.drawText(QRectF(r.left(), r.bottom() - S(34), r.width(), S(20)), int(Qt.AlignmentFlag.AlignCenter),
                           "+ " + tr(COUPONS.get(self.prize["coupon"], ("XP coupon",))[0]))
        if self.cover is None:
            self._make_cover()
        if not self.done:
            p.drawImage(r.topLeft(), self.cover)
        elif time.monotonic() - self.done_at < 0.4:
            p.setOpacity(1 - (time.monotonic() - self.done_at) / 0.4)
            p.drawImage(r.topLeft(), self.cover)
            p.setOpacity(1.0)


class ScratchOdds(QWidget):
    """4.0: the scratch card's real odds, as the server sends them (the same numbers it rolls with)."""
    COLOURS = {"golden": "#E8B23A"}

    def __init__(self, rows: list, width: int) -> None:
        super().__init__()
        self.rows = rows
        self.setFixedSize(width, S(25) * len(rows) + S(2))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for k, row in enumerate(reversed(self.rows)):
            tier = row.get("tier", "standard")
            col = QColor(self.COLOURS.get(tier) or RARITY_COLOURS.get(tier, "#9AA4AD"))
            r = QRectF(0, k * S(25), self.width(), S(23))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(col, 0.09))
            p.drawRoundedRect(r, S(6), S(6))
            p.setBrush(col)
            p.drawEllipse(QPointF(r.left() + S(12), r.center().y()), S(4), S(4))
            p.setPen(col)
            p.setFont(font(11, QFont.Weight.Bold))
            name = tr("Golden") if tier == "golden" else tr(RARITY_NAMES.get(tier, tier))
            p.drawText(r.adjusted(S(24), 0, 0, 0), int(Qt.AlignmentFlag.AlignVCenter), name)
            nw = p.fontMetrics().horizontalAdvance(name) + S(34)
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(10, QFont.Weight.DemiBold))
            p.drawText(QRectF(r.left() + nw, r.top(), r.width() - nw - S(56), r.height()), int(Qt.AlignmentFlag.AlignVCenter),
                       p.fontMetrics().elidedText(tr(str(row.get("prize", ""))), Qt.TextElideMode.ElideRight,
                                                  int(r.width() - nw - S(56))))
            p.setPen(QColor(TEXT))
            p.setFont(font(11, QFont.Weight.Bold))
            p.drawText(r.adjusted(0, 0, -S(10), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                       f"{row.get('pct', 0)}%")


def paint_freebie(widget, p, title: str, status: str, ready: bool, accent, icon) -> None:
    """4.3: the three freebies (daily reward, free spin, scratch card) as equal tiles in one row:
    the icon on top, the name under it, then ready or how long to wait."""
    r = QRectF(widget.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
    accent = QColor(accent)
    hover = 1.0 if widget.underMouse() else 0.0
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    g.setColorAt(0, mix(accent, QColor("#12161B"), 0.80 - 0.06 * hover) if ready else alpha("#FFFFFF", 0.05 + 0.02 * hover))
    g.setColorAt(1, QColor("#12161B") if ready else alpha("#FFFFFF", 0.025 + 0.02 * hover))
    p.setPen(QPen(alpha(accent, 0.55) if ready else alpha("#FFFFFF", 0.08 + 0.05 * hover), 1.2))
    p.setBrush(g)
    p.drawRoundedRect(r, S(11), S(11))
    icon(p, QPointF(r.center().x(), r.top() + S(21)))
    fm = QFontMetrics(font(11.5, QFont.Weight.Bold))
    p.setPen(QColor(TEXT))
    p.setFont(font(11.5, QFont.Weight.Bold))
    p.drawText(QRectF(r.left() + S(6), r.top() + S(35), r.width() - S(12), S(18)), int(Qt.AlignmentFlag.AlignCenter),
               fm.elidedText(title, Qt.TextElideMode.ElideRight, int(r.width() - S(12))))
    p.setPen(QColor(accent if ready else QColor(TEXT_DIM)))
    p.setFont(font(10.5, QFont.Weight.DemiBold))
    p.drawText(QRectF(r.left() + S(6), r.top() + S(52), r.width() - S(12), S(16)), int(Qt.AlignmentFlag.AlignCenter), status)


FREEBIE_H = 72


class ScratchRow(QWidget):
    """A tile in the games lobby: the scratch card is ready, or the time until the next one."""

    def __init__(self, page) -> None:
        super().__init__()
        self.page, self.ctx = page, page.ctx
        self.setFixedHeight(S(FREEBIE_H))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._t = QTimer(self)
        self._t.setInterval(1000)
        self._t.timeout.connect(self._step)

    def _step(self) -> None:
        econ = self.ctx.econ
        if int(getattr(econ, "scratch_in", 0) or 0) > 0:
            econ.scratch_in -= 1
        self.update()

    def showEvent(self, _e) -> None:
        self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()

    def mouseReleaseEvent(self, e) -> None:
        if self.rect().contains(e.position().toPoint()):
            self.page.open_sub("scratch")

    def enterEvent(self, _e) -> None:
        self.update()

    def leaveEvent(self, _e) -> None:
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        left = int(getattr(self.ctx.econ, "scratch_in", 0) or 0)
        ready = left <= 0 and not self.ctx.econ.server_old

        def icon(p, c):
            p.save()
            p.translate(c)
            p.scale(1.15, 1.15)
            draw_icon(p, "gift", QColor(TEXT) if ready else QColor(TEXT_DIM))
            p.restore()
        paint_freebie(self, p, tr("Scratch card"), tr("Ready!") if ready else (tr("Soon") if self.ctx.econ.server_old
                                                                               else clock_text(left)),
                      ready, "#D5DBE2", icon)


# ================================================================ duels
DUEL_GAMES = {"tap": "Beat Tap", "memory": "Memory", "park": "Parking"}


def duel_limit(ctx, name: str, page=None) -> int:
    """Highest duel bet with this friend: 80% of the lower of the two balances, in tens. Asked to the server
    once a minute per friend; until it answers (or on an older server) only your own balance counts."""
    cache = getattr(ctx, "duel_limits", None)
    if cache is None:
        cache = ctx.duel_limits = {}
    mine = int(int(ctx.econ.coins) * 0.8) // 10 * 10
    got = cache.get(name)
    if got is None or time.monotonic() - got[1] > 60:
        cache[name] = (got[0] if got else None, time.monotonic())

        def done(ok: bool, data) -> None:
            if ok and isinstance(data, (int, float)):
                old = cache.get(name, (None, 0))[0]
                cache[name] = (int(data), time.monotonic())
                if old != int(data) and ctx.window.showing("games") and getattr(ctx, "games_sub", None) == "duels":
                    ctx.reload_page("games")
        ctx.online.ask("rb_duel_limit", {"name": name}, done)
    top = cache.get(name, (None, 0))[0]
    return max(0, min(mine, top) if top is not None else mine)



class DuelRow(QWidget):
    """One duel: who, which game, the bet in big gold, and what can be done now (4.6: easier to read and to join)."""

    def __init__(self, page, d: dict) -> None:
        super().__init__()
        self.page, self.d = page, d
        lay = hbox(self, 8)
        lay.setContentsMargins(S(12), S(8), S(10), S(8))
        st = d.get("state")
        self.urgent = (st == "asked" and d.get("asked_me")) or (st == "on" and not d.get("played"))
        bet = int(d.get("bet") or 0)
        title = tr("{game} vs {name}", game=tr(DUEL_GAMES.get(d.get("game"), "")), name=d.get("other", "?"))
        col = vbox(spacing=1)
        col.addWidget(Label(title, 12, TEXT, bold=True))
        col.addWidget(Label(self._state_text(), 10, ui.accent.name() if self.urgent else TEXT_DIM, bold=bool(self.urgent)))
        lay.addLayout(col, 1)
        pot = vbox(spacing=0)
        pot.addWidget(Label(coins_text(bet) if bet else tr("No bet"), 13 if bet else 10.5, GOLD_TEXT if bet else TEXT_DIM,
                            bold=True, align=Qt.AlignmentFlag.AlignRight).fit(), 0, Qt.AlignmentFlag.AlignRight)
        if bet:
            pot.addWidget(Label(tr("each · pot {n}", n=coins_text(bet * 2)), 8.5, TEXT_DIM, align=Qt.AlignmentFlag.AlignRight).fit(), 0, Qt.AlignmentFlag.AlignRight)
        lay.addLayout(pot)
        if st == "asked" and d.get("asked_me"):
            yes = Button(tr("Accept & play"), "primary", 30, icon="play")
            yes.clicked.connect(lambda: page.duel_answer(d["id"], True, dict(d, state="on")))
            no = Button(tr("No"), "ghost", 30)
            no.clicked.connect(lambda: page.duel_answer(d["id"], False))
            lay.addWidget(yes)
            lay.addWidget(no)
        elif st == "asked":
            back = Button(tr("Take back"), "ghost", 30)
            back.clicked.connect(lambda: page.duel_answer(d["id"], False))
            lay.addWidget(back)
        elif st == "on" and not d.get("played"):
            go = Button(tr("Play"), "primary", 30, icon="play")
            go.clicked.connect(lambda: page.duel_play(d))
            lay.addWidget(go)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(alpha(ui.accent, 0.10) if self.urgent else alpha("#FFFFFF", 0.04))
        p.setPen(QPen(alpha(ui.accent, 0.7), 1.2) if self.urgent else Qt.PenStyle.NoPen)
        p.drawRoundedRect(r, S(10), S(10))

    def _state_text(self) -> str:
        d = self.d
        st = d.get("state")
        if st == "asked":
            return tr("Waiting for an answer") if not d.get("asked_me") else tr("They challenge you!")
        if st == "on":
            if d.get("played"):
                return tr("Your score is in: waiting for them") if not d.get("other_played") else tr("Counting…")
            return tr("Your turn: play within 15 minutes")
        if st == "cancelled":
            return {"declined": tr("Declined"), "expired": tr("No answer"), "taken back": tr("Taken back")}.get(d.get("why"), tr("Cancelled"))
        if d.get("draw"):
            return tr("Draw: bets given back")
        return tr("You won!") if d.get("won") else tr("You lost")


def build_duels(page, lay) -> None:
    """The duel screen: challenge a friend, and the list of duels."""
    ctx = page.ctx
    top = hbox(spacing=8)
    back = IconButton("back", 32, tip=tr("Back"))
    back.clicked.connect(lambda: page.open_sub(None))
    top.addWidget(back)
    top.addWidget(Label(tr("Duels"), 16, bold=True), 1)
    from .gamehelp import HelpButton
    top.addWidget(HelpButton(ctx, "duels"))
    lay.addLayout(top)
    lay.addWidget(CoinBar(ctx))
    duels = getattr(ctx, "duels_data", None)
    waiting = [d for d in (duels or []) if (d.get("state") == "asked" and d.get("asked_me"))
               or (d.get("state") == "on" and not d.get("played"))]
    if waiting:                                       # 4.6: duels waiting for me come first, before the challenge form
        lay.addWidget(Label(tr("WAITING FOR YOU"), 10, ui.accent.name(), weight=QFont.Weight.Bold))
        for d in waiting:
            lay.addWidget(DuelRow(page, d))
    friends = [f for f in (getattr(ctx, "duel_friends", None) or [])]
    lay.addWidget(Label(tr("CHALLENGE A FRIEND"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
    if not friends:
        lay.addWidget(Label(tr("Add friends in the Social tab to duel them."), 11, TEXT_DIM, wrap_w=page.W))
    else:
        names = [f["name"] for f in friends][:6]
        pick = Segmented(names, min(int(getattr(ctx, "duel_pick", 0) or 0), len(names) - 1))
        lay.addWidget(pick)
        games = ["tap", "memory", "park"]
        g = Segmented([tr(DUEL_GAMES[k]) for k in games], int(getattr(ctx, "duel_game", 0) or 0))
        g.changed.connect(lambda i: setattr(ctx, "duel_game", i))
        lay.addWidget(g)
        lv = Segmented([tr("Easy"), tr("Medium"), tr("Hard")], int(getattr(ctx, "duel_tier", 1)))
        lv.changed.connect(lambda i: setattr(ctx, "duel_tier", i))
        lay.addWidget(lv)

        def who() -> str:
            return names[min(int(getattr(ctx, "duel_pick", 0) or 0), len(names) - 1)]
        top_bet = duel_limit(ctx, who(), page)
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
            lay.addWidget(Label(tr("Maximum {n} (80% of the lower balance).", n=coins_text(top_bet)),
                                10, TEXT_DIM, wrap_w=page.W))
        else:
            lay.addWidget(Label(tr("Not enough coins for a bet."), 10, TEXT_DIM, wrap_w=page.W))

        def on_mode(i: int) -> None:
            if top_bet < 10:
                return mode.set_index(1)
            ctx.duel_nobet = i == 1
            if amount is not None:
                amount.setVisible(i == 0)

        def on_pick(i: int) -> None:
            ctx.duel_pick = i
            ctx.reload_page()                       # the highest bet depends on the friend
        mode.changed.connect(on_mode)
        pick.changed.connect(on_pick)
        send = Button(tr("Send challenge"), "primary", 36, icon="shield")

        def ask() -> None:
            name = who()
            game = games[int(getattr(ctx, "duel_game", 0) or 0)]
            bet = 0 if amount is None or getattr(ctx, "duel_nobet", False) else int(amount.value())
            bet = 0 if bet < 10 else bet - bet % 10
            if bet > ctx.econ.coins:
                return ctx.toast(tr("Not enough coins"), "warn")

            def done(ok: bool, data) -> None:
                if not ok:
                    return ctx.toast(tr(str(data)), "warn")
                sfx.play("on")
                ctx.toast(tr("Challenge sent to {name}", name=name))
                page.load_duels()
            ctx.econ.call("rb_duel_ask", {"name": name, "game": game, "tier": int(getattr(ctx, "duel_tier", 1)) + 1, "bet": bet}, done)
        send.clicked.connect(ask)
        lay.addWidget(send)
        lay.addWidget(Label(tr("Same level for both players. Best score wins the pot (5% fee). A draw refunds both bets."),
                            10, TEXT_DIM, wrap_w=page.W))
    lay.addWidget(Label(tr("YOUR DUELS") if not waiting else tr("OTHER DUELS"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
    if duels is None:
        lay.addWidget(Label(tr("Loading…"), 11, TEXT_DIM))
    elif not duels:
        lay.addWidget(Label(tr("No duels yet."), 11, TEXT_DIM))
    else:
        for d in [d for d in duels if d not in waiting][:10]:
            lay.addWidget(DuelRow(page, d))
    page.load_duels(quiet=True)



# ================================================================ the lobby: two big cards, and the mini game list
class BigCard(QWidget):
    """A big clickable card: an icon, a title and one line saying what it is."""

    def __init__(self, title: str, sub: str, icon: str, colours: tuple, on_click, height: int = 74) -> None:
        super().__init__()
        self.title, self.sub, self.icon, self.colours, self.on_click = title, sub, icon, colours, on_click
        self.setFixedHeight(S(height))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hover = 0.0
        self.extra = ""                               # small text on the right (e.g. coins left)

    def enterEvent(self, _e) -> None:
        self.hover = 1.0
        self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = 0.0
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if self.rect().contains(e.position().toPoint()):
            sfx.play("pick")
            self.on_click()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        a, b = QColor(self.colours[0]), QColor(self.colours[1])
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, mix(a, QColor("#0B0E10"), 0.55 - 0.1 * self.hover))
        g.setColorAt(1, mix(b, QColor("#0B0E10"), 0.8))
        p.setPen(QPen(alpha(a, 0.55 + 0.3 * self.hover), S(1.3)))
        p.setBrush(g)
        p.drawRoundedRect(r, S(14), S(14))
        glow = QRadialGradient(QPointF(r.left() + S(34), r.center().y()), S(40))
        glow.setColorAt(0, alpha(a, 0.45))
        glow.setColorAt(1, alpha(a, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(r.left() + S(34), r.center().y()), S(40), S(40))
        p.save()
        p.translate(r.left() + S(34), r.center().y())
        p.scale(1.5, 1.5)
        draw_icon(p, self.icon, QColor("#FFFFFF"))
        p.restore()
        p.setPen(QColor(TEXT))
        size = 15.0
        while size > 10 and QFontMetrics(font(size, QFont.Weight.ExtraBold)).horizontalAdvance(self.title) > r.width() - S(76):
            size -= 0.5                                   # long names (in French) get smaller, never cut
        p.setFont(font(size, QFont.Weight.ExtraBold))
        p.drawText(QRectF(r.left() + S(66), r.top() + S(10), r.width() - S(76), S(24)), int(Qt.AlignmentFlag.AlignVCenter), self.title)
        p.setPen(alpha("#FFFFFF", 0.75))
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(r.left() + S(66), r.top() + S(34), r.width() - S(80), r.height() - S(38)),
                   int(Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), self.sub)
        if self.extra:
            p.setPen(QColor(GOLD_TEXT))
            p.setFont(font(10, QFont.Weight.Bold))
            p.drawText(r.adjusted(0, S(8), -S(12), 0), int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight), self.extra)


def build_minigames(page, lay) -> None:
    """Earn coins: the free mini games, each with what it pays."""
    page._back_bar(lay, tr("Earn coins"))
    cap = int(float(page.ctx.econ.cfg.get("game_window_cap", 300) or 300) * (1 + 0.004 * page.ctx.econ.level))
    del cap
    games = [
        ("Beat Tap", tr("Hit the notes on the beat. 4 modes: Normal, Rush, Long notes, Chords."), "note",
         ("#FF5C8A", "#7A1FFF"), "12-50", lambda: page._show_mini(True)),
        ("Parking", tr("Slide the cars and get the red one out. Easy, Medium or Hard."), "grid",
         ("#FF8A3D", "#C2271F"), "12-50", lambda: page._show_park(True)),
        ("Memory", tr("Find the pairs in as few flips as you can. 3 sizes, 3 card styles."), "gem",
         ("#4FC3FF", "#2E5BFF"), "12-55", lambda: page.open_sub("memory")),
        ("Block Blast", tr("Place the pieces, clear rows and columns. Classic, Relaxed or Hard. Leaderboard for each."),
         "blocks", ("#FFB547", "#E8503A"), "5-360", lambda: page.open_sub("blocks")),
        ("Minesweeper", tr("Open every safe cell, as fast as you can. Easy, Medium, Hard. Leaderboard for each."), "flag",
         ("#3DDC84", "#0F6B3A"), "35-420", lambda: page.open_sub("sweeper")),
    ]
    for name, sub, icon, cols, pay, go in games:
        card = BigCard(tr(name), sub, icon, cols, go, 78)
        card.extra = tr("{n} coins", n=pay)
        lay.addWidget(card)
