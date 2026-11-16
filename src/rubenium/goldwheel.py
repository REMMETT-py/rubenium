"""3.1: the Golden Wheel. 5% of free spins and 5% of scratch cards unlock it. A golden wheel spins on a dark screen with
light rays and sparks, and always lands on a good prize: coins (2 500 to 25 000), or a free case with a key.
The server picks the prize before the wheel spins."""
import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from .core import S, sfx, alpha, font, tr
from .widgets import Button

WHEEL_GOLD = "#E8C26A"
WHEEL_SLOTS = ["2500", "5000", "10000", "25000", "premium", "titan", "vault", "mythic"]
SPIN_S = 6.5


def open_gold_wheel(ctx) -> None:
    """Ask the server for the prize, then show the wheel. Nothing happens if there is no wheel to spin."""
    if getattr(ctx, "_gold_scene", None) is not None:
        return

    def got(ok: bool, data) -> None:
        if not ok or not isinstance(data, dict):
            return ctx.toast(tr(str(data)), "warn") if ok is False and "collect" not in str(data).lower() else None
        ctx.econ.absorb(data)
        ctx._gold_scene = GoldWheelScene(ctx, data)
        ctx._gold_scene.show()
        ctx._gold_scene.raise_()
    ctx.econ.call("rb_gold_wheel", {}, got, hold=True)


def check_gold_wheels(ctx) -> None:
    """At login: a Golden Wheel won earlier and not spun yet opens now."""
    def got(ok: bool, data) -> None:
        if ok and isinstance(data, int) and data > 0 and ctx.welcome is None:
            open_gold_wheel(ctx)
    ctx.online.ask("rb_gold_wheels", {}, got)


def slot_text(slot: str) -> str:
    from .collection import CASE_NAMES
    from .wallet import coins_text
    if slot.isdigit():
        return tr("{n} coins", n=coins_text(int(slot)))
    return tr(CASE_NAMES.get(slot, "Case")) + " + " + tr("1 key")


class GoldWheelScene(QWidget):
    def __init__(self, ctx, data: dict) -> None:
        super().__init__()
        self.ctx, self.data = ctx, data
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            self.setGeometry(screen.geometry())
        self.slot = max(0, min(len(WHEEL_SLOTS) - 1, int(data.get("slot") or 0)))
        seg = 360.0 / len(WHEEL_SLOTS)
        self.target = 360.0 * 7 + (self.slot + 0.5) * seg + random.uniform(-0.3, 0.3) * seg
        self.t0 = time.monotonic()
        self.done = False
        self._ticks = 0
        self._sparks = [(random.uniform(0, 6.28), random.uniform(0.3, 1.0), random.uniform(0.5, 1.5)) for _ in range(90)]
        self.collect = Button(tr("Collect"), "primary", 46, parent=self)
        self.collect.setFixedWidth(S(220))
        self.collect.hide()
        self.collect.clicked.connect(self._finish)
        self._t = QTimer(self)
        self._t.setInterval(16)
        self._t.timeout.connect(self._tick)
        self._t.start()
        sfx.play("on")

    def keyPressEvent(self, e) -> None:
        e.accept()

    def closeEvent(self, e) -> None:
        if not self.done:
            e.ignore()
            return
        super().closeEvent(e)

    def _finish(self) -> None:
        self.done = True
        self._t.stop()
        self.ctx._gold_scene = None
        try:
            self.ctx.econ.refresh()
            self.ctx.econ.changed.emit()
        except Exception:  # noqa: BLE001
            pass
        self.close()

    def angle(self, t: float) -> float:
        u = max(0.0, min(1.0, (t - 1.0) / SPIN_S))
        return self.target * (1 - (1 - u) ** 4)

    def _tick(self) -> None:
        t = time.monotonic() - self.t0
        seg = 360.0 / len(WHEEL_SLOTS)
        n = int(self.angle(t) / seg)
        if n != self._ticks and t < 1.0 + SPIN_S:
            self._ticks = n
            sfx.play("pick")
        if t > 1.0 + SPIN_S and not self.collect.isVisible():
            sfx.play("on")
            self.collect.move(int(self.width() / 2 - self.collect.width() / 2), int(self.height() * 0.9))
            self.collect.show()
            self.collect.raise_()
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = time.monotonic() - self.t0
        W, H = self.width(), self.height()
        fade = min(1.0, t / 0.6)
        p.fillRect(self.rect(), QColor(10, 7, 2, int(240 * fade)))
        p.setOpacity(fade)
        c = QPointF(W / 2, H * 0.47)
        R = min(W, H) * 0.25
        landed = t > 1.0 + SPIN_S
        for k in range(16):                                   # turning rays
            ang = k * math.pi / 8 + t * (0.25 if not landed else 0.6)
            ray = QPainterPath(c)
            ray.lineTo(QPointF(c.x() + math.cos(ang - 0.07) * W, c.y() + math.sin(ang - 0.07) * W))
            ray.lineTo(QPointF(c.x() + math.cos(ang + 0.07) * W, c.y() + math.sin(ang + 0.07) * W))
            ray.closeSubpath()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(WHEEL_GOLD, 0.07 if not landed else 0.13))
            p.drawPath(ray)
        glow = QRadialGradient(c, R * 1.5)
        glow.setColorAt(0, alpha("#FFD36B", 0.35))
        glow.setColorAt(1, alpha("#FFD36B", 0.0))
        p.setBrush(glow)
        p.drawEllipse(c, R * 1.5, R * 1.5)
        for a0, dist, sp in self._sparks:                     # sparks spinning around the wheel
            a = a0 + t * sp
            pt = QPointF(c.x() + math.cos(a) * R * (1.1 + 0.4 * dist), c.y() + math.sin(a) * R * (1.1 + 0.4 * dist))
            b = max(0.0, math.sin(t * 3 * sp + a0)) ** 2
            p.setBrush(alpha("#FFF1C2", 0.8 * b))
            p.drawEllipse(pt, S(2.2) * b + 0.5, S(2.2) * b + 0.5)
        # the wheel
        rot = self.angle(t)
        seg = 360.0 / len(WHEEL_SLOTS)
        box = QRectF(c.x() - R, c.y() - R, 2 * R, 2 * R)
        for i, slot in enumerate(WHEEL_SLOTS):
            start = 90.0 - (i * seg - rot)
            g = QRadialGradient(c, R)
            if slot.isdigit():
                g.setColorAt(0, QColor("#FFF1B8"))
                g.setColorAt(1, QColor("#C9922A") if i % 2 else QColor("#A8741C"))
            else:
                g.setColorAt(0, QColor("#E2C6FF"))
                g.setColorAt(1, QColor("#6B2FB8") if i % 2 else QColor("#4A1C8A"))
            p.setPen(QPen(QColor("#3A2606"), S(2)))
            p.setBrush(g)
            p.drawPie(box, int(start * 16), int(-seg * 16))
            mid = math.radians(start - seg / 2)
            tp = QPointF(c.x() + R * 0.66 * math.cos(mid), c.y() - R * 0.66 * math.sin(mid))
            p.save()
            p.translate(tp)
            p.rotate(-math.degrees(mid) + 90)
            p.setPen(QColor("#2A1A04") if slot.isdigit() else QColor("#FFFFFF"))
            p.setFont(font(12, QFont.Weight.Black))
            label = f"{int(slot):,}".replace(",", " ") if slot.isdigit() else tr(slot.capitalize())
            p.drawText(QRectF(-S(50), -S(10), S(100), S(20)), int(Qt.AlignmentFlag.AlignCenter), label)
            p.restore()
        rim = QPen(QColor(WHEEL_GOLD), S(8))
        p.setPen(rim)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, R, R)
        for k in range(24):                                   # bulbs on the rim
            a = k * math.pi / 12
            on = (k + int(t * 8)) % 2 == 0
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#FFF6D8") if on else QColor("#8A5A14"))
            p.drawEllipse(QPointF(c.x() + math.cos(a) * R, c.y() + math.sin(a) * R), S(5), S(5))
        hub = QRadialGradient(c, R * 0.2)
        hub.setColorAt(0, QColor("#FFF6D8"))
        hub.setColorAt(1, QColor("#B8862B"))
        p.setBrush(hub)
        p.drawEllipse(c, R * 0.18, R * 0.18)
        p.setBrush(QColor("#FFFFFF"))                          # the pointer
        tip = QPainterPath(QPointF(c.x(), c.y() - R + S(14)))
        tip.lineTo(QPointF(c.x() - S(16), c.y() - R - S(18)))
        tip.lineTo(QPointF(c.x() + S(16), c.y() - R - S(18)))
        tip.closeSubpath()
        p.drawPath(tip)
        # title and prize
        title = QLinearGradient(0, H * 0.05, 0, H * 0.12)
        title.setColorAt(0, QColor("#FFF1B8"))
        title.setColorAt(1, QColor("#C9922A"))
        p.setPen(QPen(title, 1))
        p.setFont(font(34, QFont.Weight.Black))
        p.drawText(QRectF(0, H * 0.04, W, S(52)), int(Qt.AlignmentFlag.AlignCenter), tr("GOLDEN WHEEL"))
        if landed:
            k = min(1.0, (t - 1.0 - SPIN_S) / 0.5)
            p.setOpacity(k)
            if t - 1.0 - SPIN_S < 0.35:
                p.fillRect(self.rect(), alpha("#FFF6D8", 0.5 * (1 - (t - 1.0 - SPIN_S) / 0.35)))
            p.setPen(QColor("#FFFFFF"))
            p.setFont(font(26, QFont.Weight.Black))
            p.drawText(QRectF(0, c.y() + R + S(26), W, S(40)), int(Qt.AlignmentFlag.AlignCenter),
                       "+ " + slot_text(WHEEL_SLOTS[self.slot]))
