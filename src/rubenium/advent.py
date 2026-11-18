"""The advent calendar. A door to open every day from 1 to 24 December, and the big door on the 25th.

4.0: everyone can come in and look before 1 December (no door opens early: the server checks the date, Paris time).
The doors are in order, door 1 first (a Legendary frame for everyone), and the big door 25 on top. Snow, trees,
lights and a garland: it is Christmas. The admin can still right-click any door to peek behind it."""
import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QAbstractButton, QWidget

from .core import S, sfx, TEXT, TEXT_DIM, alpha, font, mix, tr, ui
from .shop import GOLD_TEXT
from .wallet import coins_text, paint_coin
from .widgets import IconButton, Label, Tween, draw_icon, hbox

RED, GREEN, SNOW = "#C8283D", "#1F7A4A", "#EAF6FF"
NIGHT_TOP, NIGHT_LOW = "#0A1630", "#173A5E"
BULBS = ("#FF4B5C", "#FFC94D", "#3DDC84", "#4FC3FF", "#FF7AD9")


def reward_text(rw: dict) -> str:
    from .collection import CASE_NAMES
    from .cosmetics import item_name
    parts = []
    if int(rw.get("coins") or 0):
        parts.append(tr("{n} coins", n=coins_text(int(rw["coins"]))))
    if int(rw.get("keys") or 0):
        parts.append(tr("{n} keys", n=int(rw["keys"])))
    for it in rw.get("items") or []:
        parts.append(item_name(it))
    cases: dict = {}
    for c in rw.get("cases") or []:
        cases[c] = cases.get(c, 0) + 1
    for c, n in cases.items():
        parts.append((f"{n} × " if n > 1 else "") + tr(CASE_NAMES.get(c, c)))
    return ", ".join(parts) or "?"


def load_advent(ctx, then=None) -> None:
    def got(ok: bool, data) -> None:
        if ok and isinstance(data, dict):
            data["got_at"] = time.monotonic()
            old = dict(getattr(ctx, "advent_data", None) or {})
            old.pop("got_at", None)
            changed = {k: v for k, v in data.items() if k not in ("got_at", "starts_in")} != \
                {k: v for k, v in old.items() if k != "starts_in"}
            ctx.advent_data = data
            if then is not None:
                then(changed)
    ctx.online.ask("rb_advent", {}, got)


def starts_in(data: dict) -> int:
    """Seconds until 1 December (Paris), counted down from the server's own answer."""
    s = data.get("starts_in")
    if s is None:
        return 0
    return max(0, int(s - (time.monotonic() - float(data.get("got_at") or time.monotonic()))))


def countdown_text(sec: int) -> str:
    d, rest = divmod(sec, 86400)
    h, rest = divmod(rest, 3600)
    m = rest // 60
    if d:
        return tr("{d} d {h} h", d=d, h=h)
    if h:
        return tr("{h} h {m} min", h=h, m=m)
    return tr("{m} min", m=max(1, m))


# --------------------------------------------------------------------------- #
# painting: snow, trees, lights
# --------------------------------------------------------------------------- #
class Snow:
    """Flakes that fall and sway, the same every time for one size."""

    def __init__(self, n: int, seed: int) -> None:
        rnd = random.Random(seed)
        self.flakes = [(rnd.random(), rnd.random(), rnd.uniform(0.5, 1.6), rnd.uniform(0, math.tau)) for _ in range(n)]

    def paint(self, p: QPainter, r: QRectF, now: float, opacity: float = 0.8, speed: float = 0.06) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        for x0, y0, sz, ph in self.flakes:
            y = r.top() + ((y0 + now * speed * (0.6 + sz * 0.4)) % 1.0) * r.height()
            x = r.left() + (x0 * r.width() + math.sin(now * 0.9 * sz + ph) * S(6)) % r.width()
            p.setBrush(alpha(SNOW, opacity * (0.45 + 0.35 * sz / 1.6)))
            p.drawEllipse(QPointF(x, y), S(1.1) * sz, S(1.1) * sz)


def snow_cap(p: QPainter, r: QRectF, depth: float, seed: int) -> None:
    """A soft cap of snow along the top of r, with a few drips."""
    rnd = random.Random(seed)
    path = QPainterPath(QPointF(r.left() - S(1), r.top() + S(2)))
    path.lineTo(r.left() - S(1), r.top() - S(1))
    path.lineTo(r.right() + S(1), r.top() - S(1))
    path.lineTo(r.right() + S(1), r.top() + depth * 0.6)
    n = max(3, int(r.width() / S(12)))
    for k in range(n, -1, -1):
        x = r.left() + r.width() * k / n
        y = r.top() + depth * (0.45 + 0.55 * rnd.random())
        path.quadTo(QPointF(x + r.width() / n / 2, y + depth * 0.5 * rnd.random()), QPointF(x, y))
    path.closeSubpath()
    g = QLinearGradient(r.topLeft(), QPointF(r.left(), r.top() + depth * 1.4))
    g.setColorAt(0, QColor("#FFFFFF"))
    g.setColorAt(1, QColor("#D6E8F7"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawPath(path)


def paint_tree(p: QPainter, base: QPointF, h: float, now: float, seed: int) -> None:
    """A fir tree with lights that twinkle and a star on top."""
    w = h * 0.62
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#5A3A22"))
    p.drawRect(QRectF(base.x() - w * 0.07, base.y() - h * 0.12, w * 0.14, h * 0.12))
    for k, (top, bottom, half) in enumerate(((0.0, 0.42, 0.30), (0.22, 0.66, 0.40), (0.42, 0.9, 0.5))):
        tri = QPainterPath(QPointF(base.x(), base.y() - h + top * h))
        tri.lineTo(base.x() + half * w, base.y() - h + bottom * h)
        tri.lineTo(base.x() - half * w, base.y() - h + bottom * h)
        tri.closeSubpath()
        g = QLinearGradient(QPointF(base.x() - half * w, 0), QPointF(base.x() + half * w, 0))
        g.setColorAt(0, QColor("#14573A"))
        g.setColorAt(1, QColor("#1F7A4A"))
        p.setBrush(g)
        p.drawPath(tri)
        p.setBrush(alpha("#FFFFFF", 0.85))                      # snow on the branches
        ledge = QPainterPath(QPointF(base.x() - half * w * 0.9, base.y() - h + bottom * h))
        ledge.quadTo(QPointF(base.x(), base.y() - h + bottom * h - h * 0.05), QPointF(base.x() + half * w * 0.9,
                                                                               base.y() - h + bottom * h))
        ledge.closeSubpath()
        p.drawPath(ledge)
    rnd = random.Random(seed)
    for i in range(11):                                          # lights
        t = rnd.uniform(0.18, 0.86)
        half = (0.30 + (t - 0.1) * 0.25) * w
        x = base.x() + rnd.uniform(-half, half) * 0.8
        y = base.y() - h + t * h
        tw = 0.3 + 0.7 * max(0.0, math.sin(now * 2.6 + i * 1.9 + seed))
        col = QColor(BULBS[i % len(BULBS)])
        p.setBrush(alpha(col, 0.3 * tw))
        p.drawEllipse(QPointF(x, y), S(3.4), S(3.4))
        p.setBrush(mix(col, QColor("#FFFFFF"), 0.3 * tw))
        p.drawEllipse(QPointF(x, y), S(1.4), S(1.4))
    star_at = QPointF(base.x(), base.y() - h - S(2))
    glow = 0.6 + 0.4 * math.sin(now * 2 + seed)
    p.setBrush(alpha("#FFE08A", 0.3 * glow))
    p.drawEllipse(star_at, S(7), S(7))
    paint_star(p, star_at, S(5.5), QColor("#FFE08A"))


def paint_star(p: QPainter, c: QPointF, r: float, col: QColor) -> None:
    pts = []
    for k in range(10):
        rr = r if k % 2 == 0 else r * 0.42
        a = k / 10 * math.tau - math.pi / 2
        pts.append(QPointF(c.x() + math.cos(a) * rr, c.y() + math.sin(a) * rr))
    path = QPainterPath(pts[0])
    for q in pts[1:]:
        path.lineTo(q)
    path.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    p.drawPath(path)


def paint_garland(p: QPainter, r: QRectF, now: float, sag: float) -> None:
    """A garland along the top with bulbs that light in turn."""
    n = 3
    seg = r.width() / n
    p.setBrush(Qt.BrushStyle.NoBrush)
    for k in range(n):
        a = QPointF(r.left() + k * seg, r.top())
        b = QPointF(r.left() + (k + 1) * seg, r.top())
        path = QPainterPath(a)
        path.quadTo(QPointF((a.x() + b.x()) / 2, r.top() + sag * 2), b)
        p.setPen(QPen(QColor("#1F7A4A"), S(3.2)))
        p.drawPath(path)
        p.setPen(QPen(QColor("#2E9E5E"), S(1.2), Qt.PenStyle.DotLine))
        p.drawPath(path)
        for j in range(1, 6):
            t = j / 6
            x = a.x() + (b.x() - a.x()) * t
            y = r.top() + 2 * t * (1 - t) * sag * 2
            on = 0.35 + 0.65 * max(0.0, math.sin(now * 3 + (k * 6 + j) * 1.3))
            col = QColor(BULBS[(k * 6 + j) % len(BULBS)])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(col, 0.32 * on))
            p.drawEllipse(QPointF(x, y + S(4)), S(4.5), S(4.5))
            p.setBrush(mix(col, QColor("#FFFFFF"), 0.25 * on))
            p.drawEllipse(QRectF(x - S(2), y + S(1.5), S(4), S(5.5)))


# --------------------------------------------------------------------------- #
# the way in, on the Games lobby
# --------------------------------------------------------------------------- #
class AdventCard(QWidget):
    """A small winter night: snow, a tree, a present, and today's news."""

    def __init__(self, page) -> None:
        super().__init__()
        self.page, self.ctx = page, page.ctx
        self.setFixedHeight(S(70))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = Tween(self, on_change=self.update)
        self._t = QTimer(self)
        self._t.setInterval(80)
        self._t.timeout.connect(self.update)
        self.snow = Snow(30, 3)

    def showEvent(self, _e) -> None:
        self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()

    def enterEvent(self, _e) -> None:
        self._hover.to(1.0, 140)

    def leaveEvent(self, _e) -> None:
        self._hover.to(0.0, 220)

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.page.open_sub("advent")

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        now = time.monotonic()
        clip = QPainterPath()
        clip.addRoundedRect(r, S(13), S(13))
        p.save()
        p.setClipPath(clip)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor(NIGHT_TOP))
        g.setColorAt(1, QColor(NIGHT_LOW))
        p.fillRect(r, g)
        hill = QPainterPath(QPointF(r.left(), r.bottom()))
        hill.lineTo(r.left(), r.bottom() - S(10))
        hill.quadTo(QPointF(r.left() + r.width() * 0.35, r.bottom() - S(22)), QPointF(r.left() + r.width() * 0.7, r.bottom() - S(9)))
        hill.quadTo(QPointF(r.left() + r.width() * 0.88, r.bottom() - S(3)), QPointF(r.right(), r.bottom() - S(12)))
        hill.lineTo(r.right(), r.bottom())
        hill.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#E3F0FA"))
        p.drawPath(hill)
        paint_tree(p, QPointF(r.right() - S(30), r.bottom() - S(8)), S(48), now, 4)
        self.snow.paint(p, r, now, 0.85)
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(alpha(GOLD_TEXT, 0.45 + 0.45 * self._hover.level), S(1.4)))
        p.drawRoundedRect(r, S(13), S(13))
        c = QPointF(r.left() + S(32), r.center().y() + S(2))         # a present that bobs a little
        c.setY(c.y() + math.sin(now * 2.2) * S(1.5) * (0.3 + self._hover.level))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(RED))
        p.drawRoundedRect(QRectF(c.x() - S(15), c.y() - S(10), S(30), S(24)), S(4), S(4))
        p.setBrush(QColor(GOLD_TEXT))
        p.drawRect(QRectF(c.x() - S(3), c.y() - S(10), S(6), S(24)))
        p.drawRect(QRectF(c.x() - S(15), c.y() - S(1), S(30), S(5)))
        p.setPen(QPen(QColor(GOLD_TEXT), S(2)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(c.x() - S(5), c.y() - S(14)), S(5), S(3.5))
        p.drawEllipse(QPointF(c.x() + S(5), c.y() - S(14)), S(5), S(3.5))
        data = getattr(self.ctx, "advent_data", None) or {}
        today = int(data.get("today") or 0)
        p.setPen(QColor("#FFFFFF"))
        p.setFont(font(14, QFont.Weight.ExtraBold))
        p.drawText(QRectF(r.left() + S(60), r.top() + S(10), r.width() - S(120), S(22)), int(Qt.AlignmentFlag.AlignVCenter),
                   tr("Advent calendar"))
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        p.setPen(QColor("#FFE7A8"))
        if 1 <= today <= 25:
            claimed = any(d.get("day") == today and d.get("claimed") for d in data.get("days") or [])
            sub = tr("Door {n} is open: come and see!", n=today) if not claimed else tr("Door {n} opened. Come back tomorrow!", n=today)
        elif today > 25:
            sub = tr("Merry Christmas! See you next year.")
        else:
            left = starts_in(data)
            sub = tr("Opens in {t} · door 1 is a gift for everyone", t=countdown_text(left)) if left else \
                tr("Opens on 1 December · door 1 is a gift for everyone")
        p.drawText(QRectF(r.left() + S(60), r.top() + S(34), r.width() - S(120), S(18)), int(Qt.AlignmentFlag.AlignVCenter),
                   p.fontMetrics().elidedText(sub, Qt.TextElideMode.ElideRight, int(r.width() - S(120))))


def advent_card(page, lay) -> None:
    """On the Games lobby: everyone sees it (4.0), from November to the end of December."""
    ctx = page.ctx
    data = getattr(ctx, "advent_data", None)
    if data is None:
        def then(changed: bool) -> None:
            if changed and (ctx.advent_data or {}).get("open") and ctx.window.showing("games") \
                    and not getattr(ctx, "games_sub", None) and not ctx.casino:
                ctx.reload_page("games")
        if ctx.online.logged_in() and not ctx.econ.server_old:
            load_advent(ctx, then)
        return
    if data.get("open"):
        lay.addWidget(AdventCard(page))


# --------------------------------------------------------------------------- #
# the calendar screen
# --------------------------------------------------------------------------- #
class Scene(QWidget):
    """The top of the calendar: a winter night, two trees, a garland, falling snow, and the countdown."""

    def __init__(self, page) -> None:
        super().__init__()
        self.ctx = page.ctx
        self.setFixedSize(page.W, S(132))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.snow = Snow(60, 7)
        rnd = random.Random(9)
        self.stars = [(rnd.random(), rnd.random() * 0.55, rnd.uniform(0, math.tau)) for _ in range(26)]
        self._t = QTimer(self)
        self._t.setInterval(40)
        self._t.timeout.connect(self.update)

    def showEvent(self, _e) -> None:
        self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(r, S(14), S(14))
        p.setClipPath(clip)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor(NIGHT_TOP))
        g.setColorAt(1, QColor(NIGHT_LOW))
        p.fillRect(r, g)
        p.setPen(Qt.PenStyle.NoPen)
        for x, y, ph in self.stars:                                  # stars that twinkle
            p.setBrush(alpha("#FFFFFF", 0.25 + 0.5 * max(0.0, math.sin(now * 1.5 + ph))))
            p.drawEllipse(QPointF(r.left() + x * r.width(), r.top() + S(14) + y * r.height()), S(0.9), S(0.9))
        moon = QPointF(r.left() + r.width() * 0.78, r.top() + S(30))
        halo = QRadialGradient(moon, S(30))
        halo.setColorAt(0, alpha("#FFF6D8", 0.35))
        halo.setColorAt(1, alpha("#FFF6D8", 0.0))
        p.setBrush(halo)
        p.drawEllipse(moon, S(30), S(30))
        p.setBrush(QColor("#FFF6D8"))
        p.drawEllipse(moon, S(11), S(11))
        p.setBrush(QColor(NIGHT_TOP))
        p.drawEllipse(QPointF(moon.x() + S(5), moon.y() - S(3)), S(9.5), S(9.5))
        for k, (x, hh) in enumerate(((0.08, 0.58), (0.17, 0.42), (0.86, 0.5), (0.94, 0.66))):
            paint_tree(p, QPointF(r.left() + r.width() * x, r.bottom() - S(10)), r.height() * hh, now, k + 1)
        hill = QPainterPath(QPointF(r.left(), r.bottom()))                # snowy ground
        hill.lineTo(r.left(), r.bottom() - S(16))
        hill.quadTo(QPointF(r.left() + r.width() * 0.3, r.bottom() - S(30)), QPointF(r.left() + r.width() * 0.55, r.bottom() - S(16)))
        hill.quadTo(QPointF(r.left() + r.width() * 0.8, r.bottom() - S(4)), QPointF(r.right(), r.bottom() - S(20)))
        hill.lineTo(r.right(), r.bottom())
        hill.closeSubpath()
        hg = QLinearGradient(QPointF(0, r.bottom() - S(30)), r.bottomLeft())
        hg.setColorAt(0, QColor("#FFFFFF"))
        hg.setColorAt(1, QColor("#BFD8EE"))
        p.setBrush(hg)
        p.drawPath(hill)
        paint_garland(p, QRectF(r.left(), r.top() - S(2), r.width(), S(10)), now, S(9))
        data = getattr(self.ctx, "advent_data", None) or {}
        today = int(data.get("today") or 0)
        p.setPen(QColor(0, 0, 0, 120))
        p.setFont(font(19, QFont.Weight.Black, 1.0))
        title = tr("Advent calendar")
        tr_ = QRectF(r.left(), r.top() + S(36), r.width(), S(30))
        p.drawText(tr_.translated(S(1), S(2)), int(Qt.AlignmentFlag.AlignCenter), title)
        tg = QLinearGradient(tr_.topLeft(), tr_.bottomLeft())
        tg.setColorAt(0, QColor("#FFF1C2"))
        tg.setColorAt(1, QColor("#E8B23A"))
        p.setPen(QPen(tg, 1))
        p.drawText(tr_, int(Qt.AlignmentFlag.AlignCenter), title)
        p.setFont(font(11, QFont.Weight.Bold))
        p.setPen(QColor("#FFFFFF"))
        if 1 <= today <= 25:
            sub = tr("Christmas Day: the big door is open!") if today == 25 else tr("{n} December · door {n} is open", n=today)
        elif today > 25:
            sub = tr("Merry Christmas! See you next year.")
        else:
            left = starts_in(data)
            sub = tr("The first door opens in {t}", t=countdown_text(left)) if left else tr("The first door opens on 1 December")
        p.drawText(QRectF(r.left(), r.top() + S(66), r.width(), S(20)), int(Qt.AlignmentFlag.AlignCenter), sub)
        self.snow.paint(p, r, now, 0.9)


class Calendar(QWidget):
    """The big door 25 on top, then doors 1 to 24 in order. Click today's door to open it; the admin can
    right-click any door to peek."""
    COLS = 6

    def __init__(self, page) -> None:
        super().__init__()
        self.page, self.ctx = page, page.ctx
        self.gap = S(6)
        self.cell = (page.W - self.gap * (self.COLS - 1)) / self.COLS
        self.big_h = S(96)
        self.setFixedSize(page.W, int(self.big_h + S(12) + 4 * (self.cell * 1.18 + self.gap)))
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hover = -1
        self.opening = {}                     # day -> time the door started to open
        self.peek = None                      # (day, until)
        self.bursts = []                      # (day, start, sparks)
        self.snow = Snow(70, 21)
        self._t = QTimer(self)
        self._t.setInterval(45)
        self._t.timeout.connect(self.update)

    def showEvent(self, _e) -> None:
        self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()

    def data(self) -> dict:
        return getattr(self.ctx, "advent_data", None) or {}

    def day_info(self, day: int) -> dict:
        return next((d for d in self.data().get("days") or [] if d.get("day") == day), {})

    def door(self, day: int) -> QRectF:
        if day == 25:
            return QRectF(0, S(6), self.width(), self.big_h)
        r, c = divmod(day - 1, self.COLS)
        top = self.big_h + S(12)
        h = self.cell * 1.18
        return QRectF(c * (self.cell + self.gap), top + r * (h + self.gap), self.cell, h)

    def _at(self, pos) -> int:
        for day in range(1, 26):
            if self.door(day).contains(pos):
                return day
        return -1

    def mouseMoveEvent(self, e) -> None:
        h = self._at(e.position())
        if h != self.hover:
            self.hover = h
            self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = -1
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()
        day = self._at(e.position())
        if day < 0:
            return
        data = self.data()
        if e.button() == Qt.MouseButton.RightButton:
            if data.get("admin"):                    # the admin peeks behind any door
                self.peek = (day, time.monotonic() + 4.0)
                sfx.play("pick")
                rw = self.day_info(day).get("reward") or {}
                self.ctx.toast(tr("Door {n}: {what}", n=day, what=reward_text(rw)))
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        info = self.day_info(day)
        today = int(data.get("today") or 0)
        if info.get("claimed"):
            return self.ctx.toast(tr("Door {n}: {what}", n=day, what=reward_text(info.get("reward") or {})))
        if data.get("locked"):
            return self.ctx.toast(tr("The advent calendar is paused for a moment"), "warn")
        if not today:
            sfx.play("off")
            if day == 1 and info.get("reward"):
                return self.ctx.toast(tr("Door 1 opens on 1 December: {what}, for everyone!",
                                         what=reward_text(info["reward"])))
            return self.ctx.toast(tr("No peeking! Door {n} opens on {n} December", n=day), "warn")
        if day > today:
            sfx.play("off")
            return self.ctx.toast(tr("Not yet: door {n} opens on {n} December", n=day), "warn")
        if day < today and not data.get("catchup"):
            return self.ctx.toast(tr("This door was for {n} December", n=day), "warn")
        self.claim(day)

    def claim(self, day: int) -> None:
        ctx = self.ctx
        if day in self.opening:
            return

        def got(ok: bool, ans) -> None:
            if not ok:
                self.opening.pop(day, None)
                return ctx.toast(tr(str(ans)), "warn")
            for g in ans.get("given") or []:
                ctx.econ.gained(g.get("item"), g.get("id"), "advent")
            ctx.econ.refresh()
            rw = ans.get("reward") or {}
            for d in (ctx.advent_data or {}).get("days") or []:
                if d.get("day") == day:
                    d["claimed"], d["reward"] = True, rw
            rnd = random.Random()
            self.bursts.append((day, time.monotonic(), [(rnd.uniform(0, math.tau), rnd.uniform(0.5, 1.0),
                                                        rnd.choice(("#FFE08A", "#FFFFFF", RED, "#3DDC84")))
                                                       for _ in range(36 if day == 25 else 22)]))
            sfx.tune("jingle")
            QTimer.singleShot(700, lambda: ctx.toast(tr("Door {n}: {what}", n=day, what=reward_text(rw))))
        self.opening[day] = time.monotonic()
        sfx.play("pick")
        ctx.econ.call("rb_advent_claim", {"which": day}, got)

    # -- painting
    def _door_colour(self, day: int) -> QColor:
        return QColor(("#B8233A", "#1C6E45", "#23477A", "#8E2A5C")[day % 4])

    def _motif(self, p: QPainter, c: QPointF, size: float, day: int, col: QColor) -> None:
        """A small Christmas picture on each door: a tree, a bauble, a bell, a star or a snowflake."""
        kind = day % 5
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        if kind == 0:
            paint_star(p, c, size * 0.5, col)
        elif kind == 1:
            p.drawEllipse(QPointF(c.x(), c.y() + size * 0.08), size * 0.36, size * 0.36)
            p.drawRect(QRectF(c.x() - size * 0.1, c.y() - size * 0.38, size * 0.2, size * 0.12))
        elif kind == 2:
            tri = QPainterPath(QPointF(c.x(), c.y() - size * 0.48))
            tri.lineTo(c.x() + size * 0.36, c.y() + size * 0.34)
            tri.lineTo(c.x() - size * 0.36, c.y() + size * 0.34)
            tri.closeSubpath()
            p.drawPath(tri)
        elif kind == 3:
            bell = QPainterPath(QPointF(c.x() - size * 0.36, c.y() + size * 0.3))
            bell.quadTo(QPointF(c.x() - size * 0.34, c.y() - size * 0.44), QPointF(c.x(), c.y() - size * 0.44))
            bell.quadTo(QPointF(c.x() + size * 0.34, c.y() - size * 0.44), QPointF(c.x() + size * 0.36, c.y() + size * 0.3))
            bell.closeSubpath()
            p.drawPath(bell)
            p.drawEllipse(QPointF(c.x(), c.y() + size * 0.36), size * 0.09, size * 0.09)
        else:
            pen = QPen(col, max(1.0, size * 0.08))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            for k in range(3):
                a = k * math.pi / 3
                p.drawLine(QPointF(c.x() - math.cos(a) * size * 0.4, c.y() - math.sin(a) * size * 0.4),
                           QPointF(c.x() + math.cos(a) * size * 0.4, c.y() + math.sin(a) * size * 0.4))
        p.restore()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        data = self.data()
        today = int(data.get("today") or 0)
        for day in [25] + list(range(1, 25)):
            self._paint_door(p, day, today, data, now)
        for day, t0, sparks in list(self.bursts):                   # the door bursts open: gold, snow and berries
            k = (now - t0) / 1.2
            if k >= 1.0:
                self.bursts.remove((day, t0, sparks))
                continue
            c = self.door(day).center()
            reach = (S(120) if day == 25 else S(60)) * (1 - (1 - k) ** 3)
            p.setPen(Qt.PenStyle.NoPen)
            for a, sp, col in sparks:
                p.setBrush(alpha(col, 1 - k))
                p.drawEllipse(QPointF(c.x() + math.cos(a) * reach * sp, c.y() + math.sin(a) * reach * sp + S(20) * k * k),
                              S(2.2) * (1 - k * 0.5), S(2.2) * (1 - k * 0.5))
        self.snow.paint(p, QRectF(self.rect()), now, 0.55, 0.04)       # snow falls in front of the doors

    def _paint_door(self, p: QPainter, day: int, today: int, data: dict, now: float) -> None:
        r = self.door(day).adjusted(0.5, 0.5, -0.5, -0.5)
        info = self.day_info(day)
        claimed = bool(info.get("claimed"))
        is_today = day == today
        big = day == 25
        hov = day == self.hover
        future = not today or day > today
        missed = bool(today) and day < today and not claimed and not data.get("catchup")
        rad = S(12) if big else S(8)
        back = QLinearGradient(r.topLeft(), r.bottomLeft())           # the space behind the door
        back.setColorAt(0, QColor("#2A1A10"))
        back.setColorAt(1, QColor("#120B07"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(back)
        p.drawRoundedRect(r, rad, rad)
        rw = info.get("reward")
        peeking = self.peek is not None and self.peek[0] == day and now < self.peek[1]
        if (claimed or peeking) and rw:
            self._paint_reward(p, r, rw, now)
        k = 1.0 if claimed and day not in self.opening else (min(1.0, (now - self.opening[day]) / 0.7) if day in self.opening else 0.0)
        k = 1 - (1 - k) ** 2
        if peeking:
            k = max(k, 0.55)
        if k < 1.0:                                                 # the door, swinging open from its left edge
            w = r.width() * (1 - k * 0.9)
            door = QRectF(r.left(), r.top(), w, r.height())
            col = QColor("#8C1D2C") if big else self._door_colour(day)
            if future and not big:
                col = mix(col, QColor("#1A1F24"), 0.35)
            g = QLinearGradient(door.topLeft(), door.bottomRight())
            g.setColorAt(0, mix(col, QColor("#FFFFFF"), 0.14 + (0.1 if hov else 0.0)))
            g.setColorAt(1, mix(col, QColor("#000000"), 0.38))
            p.setBrush(g)
            p.setPen(QPen(alpha(GOLD_TEXT, 0.95 if is_today else 0.4), S(2.2) if is_today else S(1)))
            p.drawRoundedRect(door, rad, rad)
            if k < 0.5:
                if big:                                              # a ribbon and a bow: the present of the year
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor("#E8B23A"))
                    p.drawRect(QRectF(door.center().x() - S(7), door.top(), S(14), door.height()))
                    p.drawRect(QRectF(door.left(), door.center().y() - S(6), door.width(), S(12)))
                    bc = QPointF(door.center().x(), door.center().y())
                    for side in (-1, 1):
                        loop = QPainterPath(bc)
                        loop.cubicTo(QPointF(bc.x() + side * S(30), bc.y() - S(34)), QPointF(bc.x() + side * S(44), bc.y() + S(8)), bc)
                        p.setBrush(QColor("#FFC94D"))
                        p.drawPath(loop)
                    p.setBrush(QColor("#C8962E"))
                    p.drawEllipse(bc, S(6), S(6))
                    p.setPen(QColor("#FFFFFF"))
                    p.setFont(font(30, QFont.Weight.Black))
                    p.drawText(QRectF(door.left() + S(14), door.top(), S(70), door.height()), int(Qt.AlignmentFlag.AlignVCenter), "25")
                    p.setFont(font(10, QFont.Weight.ExtraBold, 1.5))
                    p.setPen(QColor("#FFE7A8"))
                    p.drawText(QRectF(door.right() - S(170), door.top() + S(8), S(156), door.height() / 2 - S(14)),
                               int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), tr("CHRISTMAS DAY"))
                    p.setFont(font(9, QFont.Weight.Bold))
                    p.setPen(alpha("#FFE7A8", 0.8))
                    p.drawText(QRectF(door.right() - S(170), door.center().y() + S(8), S(156), door.height() / 2 - S(14)),
                               int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), tr("The big door"))
                else:
                    self._motif(p, QPointF(door.center().x(), door.top() + door.height() * 0.62), door.width() * 0.42, day,
                                alpha("#FFFFFF", 0.16 if future else 0.22))
                    p.setPen(QColor("#FFFFFF") if not future else alpha("#FFFFFF", 0.55))
                    p.setFont(font(15, QFont.Weight.Black))
                    p.drawText(QRectF(door.left(), door.top() + S(6), door.width(), door.height() * 0.45),
                               int(Qt.AlignmentFlag.AlignCenter), str(day))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(GOLD_TEXT))
                    p.drawEllipse(QPointF(door.right() - S(6), door.center().y() + S(4)), S(2), S(2))   # the knob
                    if day == 1 and rw and not claimed:              # door 1: everyone can see the gift
                        win = QRectF(door.center().x() - door.width() * 0.3, door.top() + door.height() * 0.5,
                                     door.width() * 0.6, door.width() * 0.6)
                        p.setBrush(QColor("#120B07"))
                        p.drawEllipse(win)
                        from .collection import show_item
                        if rw.get("items"):
                            show_item(p, rw["items"][0], win.adjusted(S(2), S(2), -S(2), -S(2)), now)
                        rib = QRectF(door.left() + S(2), door.bottom() - S(13), door.width() - S(4), S(11))
                        p.setBrush(QColor("#E8B23A"))
                        p.drawRoundedRect(rib, S(5), S(5))
                        p.setPen(QColor("#2A1A10"))
                        p.setFont(font(6.5, QFont.Weight.Black))
                        p.drawText(rib, int(Qt.AlignmentFlag.AlignCenter), tr("FOR ALL"))
                    if future and not (day == 1 and rw):
                        p.save()
                        p.translate(door.left() + S(9), door.top() + S(10))
                        p.scale(S(9) / 20, S(9) / 20)
                        draw_icon(p, "lock", alpha("#FFFFFF", 0.5))
                        p.restore()
                snow_cap(p, door, S(9) if big else S(6), day)
            if is_today and not claimed:                             # today's door: a wreath of light
                pulse = 0.5 + 0.5 * math.sin(now * 4)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(alpha("#3DDC84", 0.35 + 0.45 * pulse), S(3)))
                p.drawRoundedRect(r.adjusted(-S(1.5), -S(1.5), S(1.5), S(1.5)), rad + S(1), rad + S(1))
                p.setPen(QPen(alpha(GOLD_TEXT, 0.5 + 0.5 * pulse), S(1.4), Qt.PenStyle.DotLine))
                p.drawRoundedRect(r.adjusted(-S(4), -S(4), S(4), S(4)), rad + S(3), rad + S(3))
        if missed:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 130))
            p.drawRoundedRect(r, rad, rad)

    def _paint_reward(self, p: QPainter, r: QRectF, rw: dict, now: float) -> None:
        from .collection import paint_case, show_item
        things = []
        for it in rw.get("items") or []:
            things.append(("item", it))
        for c in rw.get("cases") or []:
            things.append(("case", c))
        if int(rw.get("keys") or 0):
            things.append(("keys", int(rw["keys"])))
        if int(rw.get("coins") or 0):
            things.append(("coins", int(rw["coins"])))
        if not things:
            return
        glow = QRadialGradient(r.center(), r.width() * 0.6)
        glow.setColorAt(0, alpha(GOLD_TEXT, 0.35))
        glow.setColorAt(1, alpha(GOLD_TEXT, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(r.center(), r.width() * 0.6, r.height() * 0.6)
        n = min(len(things), 5)
        d = min(r.height() * 0.62, (r.width() - S(8)) / n)
        x0 = r.center().x() - n * d / 2
        for i, (kind, what) in enumerate(things[:n]):
            box = QRectF(x0 + i * d + d * 0.08, r.center().y() - d / 2, d * 0.84, d * 0.84)
            if kind == "item":
                show_item(p, what, box, now)
            elif kind == "case":
                paint_case(p, box, what)
            elif kind == "keys":
                p.save()
                p.translate(box.center())
                p.scale(box.width() / 26, box.width() / 26)
                draw_icon(p, "key", ui.accent)
                p.restore()
            else:
                paint_coin(p, box.center(), box.width() * 0.36)


class FestiveButton(QAbstractButton):
    """A Christmas button: red with candy-cane stripes, a gold edge, and snow on top."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text
        self.setFixedHeight(S(42))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = Tween(self, on_change=self.update)
        self._t = QTimer(self)
        self._t.setInterval(40)
        self._t.timeout.connect(self.update)

    def showEvent(self, _e) -> None:
        self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()

    def enterEvent(self, _e) -> None:
        self._hover.to(1.0, 140)

    def leaveEvent(self, _e) -> None:
        self._hover.to(0.0, 220)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, S(5), -1, -1)
        h = self._hover.level
        clip = QPainterPath()
        clip.addRoundedRect(r, S(11), S(11))
        p.save()
        p.setClipPath(clip)
        p.fillRect(r, mix(QColor(RED), QColor("#FFFFFF"), 0.08 * h))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.13))
        off = (time.monotonic() * S(14)) % S(22)
        x = r.left() - r.height() - S(22) + off
        while x < r.right() + r.height():
            band = QPainterPath(QPointF(x, r.bottom()))
            band.lineTo(x + r.height(), r.top())
            band.lineTo(x + r.height() + S(9), r.top())
            band.lineTo(x + S(9), r.bottom())
            band.closeSubpath()
            p.drawPath(band)
            x += S(22)
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor("#FFD36B"), S(1.6)))
        p.drawRoundedRect(r, S(11), S(11))
        snow_cap(p, QRectF(r.left() + S(6), r.top(), r.width() - S(12), r.height()), S(6), 77)
        p.setPen(QColor(0, 0, 0, 90))
        p.setFont(font(13, QFont.Weight.ExtraBold))
        p.drawText(r.translated(0, S(1.5)), int(Qt.AlignmentFlag.AlignCenter), self._text)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), self._text)


def build_advent(page, lay) -> None:
    ctx = page.ctx
    top = hbox(spacing=8)
    back = IconButton("back", 32, tip=tr("Back"))
    back.clicked.connect(lambda: page.open_sub(None))
    top.addWidget(back)
    top.addWidget(Label(tr("Advent calendar"), 16, bold=True), 1)
    lay.addLayout(top)
    data = getattr(ctx, "advent_data", None)
    if data is None:
        load_advent(ctx, lambda changed: ctx.reload_page("games"))
        lay.addWidget(Label(tr("Loading…"), 11, TEXT_DIM))
        return
    load_advent(ctx, lambda changed: changed and ctx.reload_page("games"))
    today = int(data.get("today") or 0)
    lay.addWidget(Scene(page))
    cal = Calendar(page)
    if 1 <= today <= 25:
        info = cal.day_info(today)
        if not info.get("claimed") and not data.get("locked"):
            go = FestiveButton(tr("Open the big door!") if today == 25 else tr("Open door {n}", n=today))
            go.clicked.connect(lambda: cal.claim(today))
            lay.addWidget(go)
    lay.addWidget(cal)
    lay.addWidget(Label(tr("One door a day from 1 to 24 December, and the big door on Christmas Day. Door 1 is a "
                           "Legendary frame for everyone. Doors open on their own day only (Paris time)."), 10.5,
                        TEXT_DIM, wrap_w=page.W))
    if data.get("admin") and not today:
        lay.addWidget(Label(tr("Admin preview: right-click a door to peek behind it."), 10.5, GOLD_TEXT, wrap_w=page.W))
