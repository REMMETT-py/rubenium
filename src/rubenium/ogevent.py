"""3.0.0: the OG event (16/11/2026). Once, for every user with the OG tag who logs in that day: a cutscene that cannot
be skipped. An OG chest bursts open, three rows of chests spin at the same time and all land on the MYTHIC CHEST
BUNDLE: 1 free open of every case, 10 000 coins and 10 gold keys. The server gives the rewards before the cutscene
starts, so closing the app halfway loses nothing."""
import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from .core import S, sfx, alpha, font, tr
from .widgets import Button

OG_GOLD = "#E8C26A"
ROW_SLOTS = 64
WIN_SLOT = 56
SPIN_START, SPIN_END = 2.4, 9.4


def paint_bundle(p: QPainter, r: QRectF, now: float, big: bool = False) -> None:
    """The MYTHIC CHEST BUNDLE: a gold and violet chest with a crown and a glow."""
    p.save()
    c = r.center()
    glow = QRadialGradient(c, r.width() * 0.75)
    glow.setColorAt(0, alpha("#B36BFF", 0.55 + 0.15 * math.sin(now * 3)))
    glow.setColorAt(1, alpha("#B36BFF", 0.0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(glow)
    p.drawEllipse(c, r.width() * 0.75, r.width() * 0.75)
    w, h = r.width() * 0.78, r.height() * 0.56
    body = QRectF(c.x() - w / 2, c.y() - h / 2 + r.height() * 0.08, w, h)
    g = QLinearGradient(body.topLeft(), body.bottomLeft())
    g.setColorAt(0, QColor("#7B2FD6"))
    g.setColorAt(1, QColor("#2B0B5C"))
    p.setBrush(g)
    p.setPen(QPen(QColor(OG_GOLD), max(2.0, r.width() * 0.03)))
    p.drawRoundedRect(body, r.width() * 0.06, r.width() * 0.06)
    lid = QRectF(body.left() - w * 0.04, body.top() - h * 0.36, w * 1.08, h * 0.42)
    g2 = QLinearGradient(lid.topLeft(), lid.bottomLeft())
    g2.setColorAt(0, QColor("#9B5CFF"))
    g2.setColorAt(1, QColor("#4A169C"))
    p.setBrush(g2)
    p.drawRoundedRect(lid, r.width() * 0.07, r.width() * 0.07)
    p.setBrush(QColor(OG_GOLD))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRect(QRectF(c.x() - w * 0.06, lid.top(), w * 0.12, body.bottom() - lid.top()))
    lock = QRectF(c.x() - w * 0.1, body.top() - h * 0.02, w * 0.2, h * 0.26)
    p.drawRoundedRect(lock, w * 0.03, w * 0.03)
    crown = QPainterPath(QPointF(c.x() - w * 0.2, lid.top() - h * 0.02))
    for dx, dy in ((-0.13, -0.3), (-0.06, -0.12), (0.0, -0.36), (0.06, -0.12), (0.13, -0.3), (0.2, -0.02)):
        crown.lineTo(QPointF(c.x() + w * dx, lid.top() + h * dy))
    crown.closeSubpath()
    p.drawPath(crown)
    p.setPen(QColor("#FFFFFF"))
    p.setFont(font(max(6.0, r.width() / S(1) * (0.085 if big else 0.1)), QFont.Weight.Black))
    p.drawText(QRectF(body.left(), body.top() + h * 0.3, body.width(), h * 0.6), int(Qt.AlignmentFlag.AlignCenter),
               "MYTHIC")
    p.restore()


class OgCutscene(QWidget):
    def __init__(self, ctx, gift: dict) -> None:
        super().__init__()
        self.ctx, self.gift = ctx, gift
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        screen = QGuiApplication.primaryScreen()
        self.setGeometry(screen.geometry() if screen is not None else QRectF(0, 0, 1280, 720).toRect())
        from .collection import CASE_NAMES
        ids = [k for k in CASE_NAMES if k != "daily"] or ["standard"]
        rnd = random.Random()
        self.rows = []
        for k in range(3):                                   # three rows, each with its own speed and stop time
            slots = [rnd.choice(ids) for _ in range(ROW_SLOTS)]
            for i in range(WIN_SLOT - 4, WIN_SLOT + 5):      # never a bundle next to the winner
                slots[i] = rnd.choice(ids)
            slots[WIN_SLOT] = "BUNDLE"
            for i in (11, 27, 43):                          # a few near misses on the way
                slots[i] = "BUNDLE"
            self.rows.append(dict(slots=slots, end=SPIN_END - 0.5 + 0.5 * k if k != 1 else SPIN_END + 0.4,
                                  jitter=rnd.uniform(-0.3, 0.3)))
        self.t0 = time.monotonic()
        self.done = False
        self._last_tick = [0, 0, 0]
        self._landed = set()
        self.collect = Button(tr("Collect"), "primary", 46, parent=self)
        self.collect.setFixedWidth(S(220))
        self.collect.hide()
        self.collect.clicked.connect(self._finish)
        self._t = QTimer(self)
        self._t.setInterval(16)
        self._t.timeout.connect(self._tick)
        self._t.start()
        sfx.play("on")

    # cannot be skipped
    def keyPressEvent(self, e) -> None:
        e.accept()

    def closeEvent(self, e) -> None:
        if not self.done:
            e.ignore()
            return
        super().closeEvent(e)

    def _finish(self) -> None:
        self.done = True
        sfx.play("on")
        self._t.stop()
        try:
            self.ctx.econ.refresh()
            self.ctx.econ.fetch_gold_keys()
        except Exception:  # noqa: BLE001
            pass
        self.close()

    def slot_w(self) -> float:
        return max(S(120), self.width() / 9)

    def offset(self, row: dict, t: float) -> float:
        """How far the row has moved: fast, then slowing down until the winning slot is in the middle."""
        total = WIN_SLOT * self.slot_w() + row["jitter"] * self.slot_w() * 0.0
        span = row["end"] - SPIN_START
        u = max(0.0, min(1.0, (t - SPIN_START) / span))
        ease = 1 - (1 - u) ** 4
        return total * ease

    def _tick(self) -> None:
        t = time.monotonic() - self.t0
        sw = self.slot_w()
        for k, row in enumerate(self.rows):
            if SPIN_START <= t <= row["end"]:
                i = int(self.offset(row, t) / sw)
                if i != self._last_tick[k] and k == 1:
                    sfx.play("pick")
                self._last_tick[k] = i
            elif t > row["end"] and k not in self._landed:
                self._landed.add(k)
                sfx.play("on")
        if t > SPIN_END + 3.6 and not self.collect.isVisible():
            self.collect.move(int(self.width() / 2 - self.collect.width() / 2), int(self.height() * 0.84))
            self.collect.show()
            self.collect.raise_()
        self.update()

    def paintEvent(self, _e) -> None:
        from .collection import paint_case
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = time.monotonic() - self.t0
        W, H = self.width(), self.height()
        fade = min(1.0, t / 0.8)
        bg = QLinearGradient(0, 0, 0, H)
        bg.setColorAt(0, QColor(12, 6, 26, int(245 * fade)))
        bg.setColorAt(1, QColor(4, 2, 10, int(250 * fade)))
        p.fillRect(self.rect(), bg)
        p.setOpacity(fade)
        # title
        p.setPen(QColor(OG_GOLD))
        p.setFont(font(34, QFont.Weight.Black))
        p.drawText(QRectF(0, H * 0.06, W, S(50)), int(Qt.AlignmentFlag.AlignCenter), tr("OG EVENT"))
        p.setPen(QColor("#FFFFFF"))
        p.setFont(font(14, QFont.Weight.DemiBold))
        p.drawText(QRectF(0, H * 0.06 + S(50), W, S(24)), int(Qt.AlignmentFlag.AlignCenter),
                   tr("Thank you for being one of the first. This chest is yours."))
        cx, cy = W / 2, H * 0.5
        if t < SPIN_START:                                   # the OG chest shakes, then bursts open
            k = max(0.0, (t - 0.6) / (SPIN_START - 0.6))
            shake = math.sin(t * 40) * S(8) * k
            size = S(170) * (1 + 0.15 * k)
            r = QRectF(cx - size / 2 + shake, cy - size / 2, size, size)
            paint_case(p, r, "mythic")
            p.setPen(QColor(OG_GOLD))
            p.setFont(font(16, QFont.Weight.Black))
            p.drawText(QRectF(0, r.bottom() + S(8), W, S(26)), int(Qt.AlignmentFlag.AlignCenter), tr("OG CHEST"))
            if t > SPIN_START - 0.35:
                p.fillRect(self.rect(), alpha("#FFFFFF", (t - (SPIN_START - 0.35)) / 0.35 * 0.9))
            return
        if t < SPIN_START + 0.4:
            p.fillRect(self.rect(), alpha("#FFFFFF", 0.9 * (1 - (t - SPIN_START) / 0.4)))
        sw = self.slot_w()
        row_h = min(H * 0.2, sw * 1.05)
        reveal = max(0.0, t - (SPIN_END + 1.2))
        rows_alpha = max(0.0, 1 - reveal / 0.6)
        if rows_alpha > 0:
            p.setOpacity(fade * rows_alpha)
            for k, row in enumerate(self.rows):
                y = cy + (k - 1) * (row_h + S(14)) - row_h / 2
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha("#FFFFFF", 0.04))
                p.drawRect(QRectF(0, y, W, row_h))
                off = self.offset(row, t)
                first = int(off / sw) - 6
                for i in range(max(0, first), min(ROW_SLOTS, first + 16)):
                    x = cx + i * sw - off - sw / 2
                    cell = QRectF(x + S(8), y + S(8), sw - S(16), row_h - S(16))
                    landed = t > row["end"] and i == WIN_SLOT
                    if row["slots"][i] == "BUNDLE":
                        paint_bundle(p, cell, t)
                    else:
                        paint_case(p, cell, row["slots"][i])
                    if landed:
                        p.setPen(QPen(QColor(OG_GOLD), S(3)))
                        p.setBrush(Qt.BrushStyle.NoBrush)
                        p.drawRoundedRect(cell.adjusted(-S(4), -S(4), S(4), S(4)), S(12), S(12))
            p.setPen(QPen(QColor(OG_GOLD), S(3)))                 # the line in the middle
            top = cy - 1.5 * row_h - S(24)
            p.drawLine(QPointF(cx, top), QPointF(cx, cy + 1.5 * row_h + S(24)))
            p.setOpacity(fade)
        if reveal > 0:                                       # the bundle, big, and what is inside
            a = min(1.0, reveal / 0.6)
            p.setOpacity(a)
            for k in range(14):                               # rays
                ang = k * math.pi / 7 + t * 0.4
                ray = QPainterPath(QPointF(cx, cy - H * 0.08))
                ray.lineTo(QPointF(cx + math.cos(ang - 0.06) * W, cy - H * 0.08 + math.sin(ang - 0.06) * W))
                ray.lineTo(QPointF(cx + math.cos(ang + 0.06) * W, cy - H * 0.08 + math.sin(ang + 0.06) * W))
                ray.closeSubpath()
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha("#B36BFF", 0.10))
                p.drawPath(ray)
            size = S(200)
            paint_bundle(p, QRectF(cx - size / 2, cy - H * 0.08 - size / 2, size, size), t, big=True)
            p.setPen(QColor(OG_GOLD))
            p.setFont(font(24, QFont.Weight.Black))
            p.drawText(QRectF(0, cy + S(40), W, S(36)), int(Qt.AlignmentFlag.AlignCenter), tr("MYTHIC CHEST BUNDLE"))
            lines = [tr("1 free open of every case"), tr("{n} coins", n="10 000"), tr("{n} gold keys", n=10)]
            p.setFont(font(15, QFont.Weight.Bold))
            for i, text in enumerate(lines):
                la = max(0.0, min(1.0, (reveal - 0.8 - 0.5 * i) / 0.4))
                if la <= 0:
                    continue
                p.setOpacity(la)
                p.setPen(QColor("#FFFFFF") if i != 2 else QColor(OG_GOLD))
                p.drawText(QRectF(0, cy + S(84) + i * S(30), W, S(28)), int(Qt.AlignmentFlag.AlignCenter), "+ " + text)
            p.setOpacity(1.0)
            p.setPen(alpha("#FFFFFF", 0.55))
            p.setFont(font(11, QFont.Weight.DemiBold))
            p.drawText(QRectF(0, cy + S(84) + 3 * S(30) + S(6), W, S(22)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("Gold keys are used first and disappear once used."))
