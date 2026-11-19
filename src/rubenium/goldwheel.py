"""The Golden Wheel. 5% of free spins and 5% of scratch cards unlock it.
4.7: it lives inside the menu like the free wheel (no more full-screen window that flashed over online mode), and it
pays a lot more: 10 000 to 250 000 coins, or an Elite, Vault, Top Tier or Royal case with a key.
Nothing is spent until you press Spin; the server picks the prize, then the wheel turns to it."""
import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient
from PyQt6.QtWidgets import QWidget

from .core import S, TEXT, TEXT_DIM, alpha, font, sfx, tr
from .widgets import Button, hbox, vbox

WHEEL_GOLD = "#E8C26A"
# 4.7: the server's slots, in the same order (rb_gold_wheel)
WHEEL_SLOTS = ["10000", "elite", "20000", "vault", "40000", "mythic", "100000", "royal", "250000"]
WHEEL_ODDS = [26, 14, 20, 10, 12, 8, 4, 5, 1]
SPIN_S = 5.5


def slot_text(slot: str) -> str:
    from .collection import CASE_NAMES
    from .wallet import coins_text
    if slot.isdigit():
        return tr("{n} coins", n=coins_text(int(slot)))
    return tr(CASE_NAMES.get(slot, "Case")) + " + " + tr("1 key")


def open_gold_wheel(ctx) -> None:
    """Show the wheel inside the menu. Nothing is spent until Spin is pressed."""
    old = getattr(ctx, "_gold_panel", None)
    try:
        if old is not None and old.isVisible():
            return
    except RuntimeError:
        pass
    ctx._gold_panel = GoldWheelPanel(ctx)
    ctx.window.embed(ctx._gold_panel)
    try:
        ctx.window.expand()
    except Exception:  # noqa: BLE001
        pass


def check_gold_wheels(ctx) -> None:
    """At login: a Golden Wheel won earlier and not spun yet: a notification that opens it."""
    def got(ok: bool, data) -> None:
        if ok and isinstance(data, int) and data > 0 and ctx.welcome is None:
            ctx.gold_wheels_left = data
            ctx.notifier.push("gift", tr("GOLDEN WHEEL"), tr("You have a Golden Wheel to spin!"), "gold_wheel")
    ctx.online.ask("rb_gold_wheels", {}, got)


class _Wheel(QWidget):
    """The golden wheel itself, drawn like the free wheel."""

    def __init__(self, panel) -> None:
        super().__init__()
        self.panel = panel
        self.angle = 0.0
        self._from = self._to = 0.0
        self._t0 = 0.0
        self.spinning = False
        self.landed_at = 0.0
        self._last_seg = 0
        self._sparks = [(random.uniform(0, 6.28), random.uniform(0.2, 1.0), random.uniform(0.4, 1.4)) for _ in range(60)]
        self.setMinimumHeight(S(330))
        self._t = QTimer(self)
        self._t.setInterval(16)
        self._t.timeout.connect(self._tick)
        self._t.start()

    def spin_to(self, slot: int) -> None:
        seg = 360.0 / len(WHEEL_SLOTS)
        self._from = self.angle % 360.0
        self._to = self._from + 360.0 * 6 + ((slot + 0.5) * seg - self._from % 360.0) % 360.0 \
            + random.uniform(-0.32, 0.32) * seg
        self._t0 = time.monotonic()
        self.spinning = True

    def _tick(self) -> None:
        if self.spinning:
            u = min(1.0, (time.monotonic() - self._t0) / SPIN_S)
            self.angle = self._from + (self._to - self._from) * (1 - (1 - u) ** 4)
            seg = int(self.angle / (360.0 / len(WHEEL_SLOTS)))
            if seg != self._last_seg:
                self._last_seg = seg
                sfx.play("pick")
            if u >= 1.0:
                self.spinning = False
                self.landed_at = time.monotonic()
                self.panel.landed()
        if not self.isVisible():
            return
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        r = QRectF(self.rect())
        radius = min(r.width(), r.height()) / 2 - S(22)
        c = QPointF(r.center().x(), r.center().y() + S(6))
        landed = self.landed_at and not self.spinning
        glow = QRadialGradient(c, radius * 1.45)
        glow.setColorAt(0, alpha("#FFD36B", 0.28 if not landed else 0.42))
        glow.setColorAt(1, alpha("#FFD36B", 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, radius * 1.45, radius * 1.45)
        for a0, dist, sp in self._sparks:                     # sparks turning around the wheel
            a = a0 + now * sp * 0.6
            pt = QPointF(c.x() + math.cos(a) * radius * (1.06 + 0.3 * dist), c.y() + math.sin(a) * radius * (1.06 + 0.3 * dist))
            b = max(0.0, math.sin(now * 3 * sp + a0)) ** 2
            p.setBrush(alpha("#FFF1C2", 0.75 * b))
            p.drawEllipse(pt, S(1.8) * b + 0.4, S(1.8) * b + 0.4)
        n = len(WHEEL_SLOTS)
        seg = 360.0 / n
        box = QRectF(c.x() - radius, c.y() - radius, 2 * radius, 2 * radius)
        win = self.panel.slot if landed else -1
        for i, slot in enumerate(WHEEL_SLOTS):
            start = 90.0 - (i * seg - self.angle)
            g = QRadialGradient(c, radius)
            if slot.isdigit():
                big = int(slot) >= 100000
                g.setColorAt(0, QColor("#FFF6D8" if big else "#FFF1B8"))
                g.setColorAt(1, QColor("#E0A93A" if big else ("#C9922A" if i % 2 else "#A8741C")))
            else:
                g.setColorAt(0, QColor("#E2C6FF"))
                g.setColorAt(1, QColor("#6B2FB8") if i % 2 else QColor("#4A1C8A"))
            p.setPen(QPen(QColor("#3A2606"), S(1.6)))
            p.setBrush(g)
            p.drawPie(box, int(start * 16), int(-seg * 16))
            if i == win:                                     # the prize slot shines
                k = 0.5 + 0.5 * math.sin(now * 8)
                p.setBrush(alpha("#FFFFFF", 0.18 + 0.2 * k))
                p.drawPie(box, int(start * 16), int(-seg * 16))
            mid = math.radians(start - seg / 2)
            tp = QPointF(c.x() + radius * 0.66 * math.cos(mid), c.y() - radius * 0.66 * math.sin(mid))
            p.save()
            p.translate(tp)
            p.rotate(-math.degrees(mid) + 90)
            if slot.isdigit():
                v = int(slot)
                label = f"{v // 1000}K" if v >= 1000 else str(v)
                p.setPen(QColor("#2A1A04"))
                p.setFont(font(12.5 if v >= 100000 else 11.5, QFont.Weight.Black))
            else:
                from .collection import CASE_NAMES
                label = tr(CASE_NAMES.get(slot, slot)).replace(tr("Case"), "").strip().upper()
                p.setPen(QColor("#FFFFFF"))
                p.setFont(font(8.5 if len(label) <= 7 else 7, QFont.Weight.Black))
            p.drawText(QRectF(-S(42), -S(9), S(84), S(18)), int(Qt.AlignmentFlag.AlignCenter), label)
            p.restore()
        p.setPen(QPen(QColor(WHEEL_GOLD), S(6)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, radius, radius)
        for k in range(24):                                   # bulbs on the rim
            a = k * math.pi / 12
            on = (k + int(now * (14 if self.spinning else 5))) % 2 == 0
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#FFF6D8") if on else QColor("#8A5A14"))
            p.drawEllipse(QPointF(c.x() + math.cos(a) * radius, c.y() + math.sin(a) * radius), S(3.6), S(3.6))
        hub = QRadialGradient(c, radius * 0.22)
        hub.setColorAt(0, QColor("#FFF6D8"))
        hub.setColorAt(1, QColor("#B8862B"))
        p.setBrush(hub)
        p.drawEllipse(c, radius * 0.2, radius * 0.2)
        p.setPen(QColor("#3A2606"))
        p.setFont(font(9, QFont.Weight.Black))
        p.drawText(QRectF(c.x() - radius * 0.2, c.y() - S(9), radius * 0.4, S(18)), int(Qt.AlignmentFlag.AlignCenter), "GOLD")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FFFFFF"))
        p.drawPolygon(QPolygonF([QPointF(c.x() - S(9), c.y() - radius - S(12)), QPointF(c.x() + S(9), c.y() - radius - S(12)),
                                 QPointF(c.x(), c.y() - radius + S(8))]))
        if landed and now - self.landed_at < 0.4:            # a flash as it lands
            p.setBrush(alpha("#FFF6D8", 0.45 * (1 - (now - self.landed_at) / 0.4)))
            path = QPainterPath()
            path.addEllipse(c, radius * 1.1, radius * 1.1)
            p.drawPath(path)


class GoldWheelPanel(QWidget):
    """Inside the menu: title, the wheel, what it can give, and Spin / Collect."""

    def __init__(self, ctx) -> None:
        super().__init__()
        from .widgets import Label
        self.ctx = ctx
        self.slot = -1
        self.prize = None
        self.waiting = False
        self.setFixedWidth(ctx.window.page_w())
        lay = vbox(self, 8)
        lay.addWidget(Label(tr("GOLDEN WHEEL"), 18, WHEEL_GOLD, bold=True, align=Qt.AlignmentFlag.AlignCenter))
        self.sub = Label(tr("Every slot is a big prize. Spin when you're ready."), 10.5, TEXT_DIM,
                         align=Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.sub)
        self.wheel = _Wheel(self)
        lay.addWidget(self.wheel)
        self.result = Label("", 16, TEXT, bold=True, align=Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.result)
        row = hbox(spacing=8)
        self.go = Button(tr("Spin"), "primary", 40, icon="play")
        self.go.clicked.connect(self.spin)
        self.later = Button(tr("Later"), "ghost", 40)
        self.later.clicked.connect(self.close_panel)
        row.addStretch(1)
        row.addWidget(self.later)
        row.addWidget(self.go)
        row.addStretch(1)
        lay.addLayout(row)
        for line in (tr("Coins: 10K 26% · 20K 20% · 40K 12% · 100K 4% · 250K 1%"),
                     tr("Cases with a key: Elite 14% · Vault 10% · Top Tier 8% · Royal 5%")):
            lay.addWidget(Label(line, 9, TEXT_DIM, align=Qt.AlignmentFlag.AlignCenter, wrap_w=self.width()))

    def spin(self) -> None:
        if self.waiting or self.wheel.spinning:
            return
        if self.prize is not None:                          # spin again (another wheel waiting)
            self.prize, self.slot = None, -1
            self.result.set_text("")
        self.waiting = True
        self.go.setEnabled(False)
        self.later.setEnabled(False)

        def got(ok: bool, data) -> None:
            self.waiting = False
            if not ok or not isinstance(data, dict):
                self.go.setEnabled(True)
                self.later.setEnabled(True)
                if "collect" in str(data).lower():
                    self.result.set_text(tr("No Golden Wheel left to spin"))
                    self.go.hide()
                    self.later.set_text(tr("Close"))
                    return
                return self.ctx.toast(tr(str(data)), "warn")
            self.prize = data
            self.slot = max(0, min(len(WHEEL_SLOTS) - 1, int(data.get("slot") or 0)))
            self.ctx.notifier.hold(SPIN_S + 1.5)               # no spoiler before it lands
            self.wheel.spin_to(self.slot)
            sfx.play("on")
        self.ctx.econ.call("rb_gold_wheel", {}, got, hold=True)

    def landed(self) -> None:
        if self.prize is None:
            return
        self.ctx.econ.absorb(self.prize)
        try:
            self.ctx.econ.refresh()
            self.ctx.econ.changed.emit()
        except Exception:  # noqa: BLE001
            pass
        sfx.play("on")
        try:
            from .onlinewin import shake
            shake(self.ctx.window, 3.0, 250)
        except Exception:  # noqa: BLE001
            pass
        self.result.set_text("+ " + slot_text(WHEEL_SLOTS[self.slot]))
        left = int(self.prize.get("left") or 0)
        self.later.setEnabled(True)
        self.later.set_text(tr("Collect"))
        if left > 0:
            self.go.setEnabled(True)
            self.go.set_text(tr("Spin again ({n} left)", n=left))
        else:
            self.go.hide()

    def close_panel(self) -> None:
        if self.wheel.spinning or self.waiting:
            return
        self.ctx._gold_panel = None
        self.ctx.window.unembed(self)

    def on_closed(self) -> None:
        """The menu closed the panel (tab changed) while the wheel was turning: say what was won."""
        self.ctx._gold_panel = None
        if self.prize is not None and self.wheel.spinning:
            self.ctx.econ.absorb(self.prize)
            self.ctx.toast("+ " + slot_text(WHEEL_SLOTS[self.slot]), "good")
