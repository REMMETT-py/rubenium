"""3.2: the advent calendar. A door to open every day from 1 to 24 December, and a big door on the 25th.

Behind the doors: coins, keys, limited Christmas looks (never sold in the shop) and limited cases. Only today's door
opens. The admin sees the calendar early and can right-click any door to peek at what is behind it."""
import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from .core import S, sfx, TEXT, TEXT_DIM, alpha, font, mix, tr, ui
from .shop import GOLD_TEXT
from .wallet import coins_text, paint_coin
from .widgets import IconButton, Label, Tween, draw_icon, hbox

RED, GREEN, SNOW = "#C8283D", "#1F7A4A", "#EAF6FF"


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
            changed = data != getattr(ctx, "advent_data", None)
            ctx.advent_data = data
            if then is not None:
                then(changed)
    ctx.online.ask("rb_advent", {}, got)


class AdventCard(QWidget):
    """The way in, on the Games lobby: a festive bar with today's door."""

    def __init__(self, page) -> None:
        super().__init__()
        self.page, self.ctx = page, page.ctx
        self.setFixedHeight(S(66))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = Tween(self, on_change=self.update)
        self._t = QTimer(self)
        self._t.setInterval(50)
        self._t.timeout.connect(self.update)
        rnd = random.Random(3)
        self.flakes = [(rnd.random(), rnd.random(), rnd.uniform(0.6, 1.6)) for _ in range(26)]

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
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, mix(QColor(RED), QColor("#000000"), 0.35))
        g.setColorAt(1, mix(QColor(GREEN), QColor("#000000"), 0.45))
        p.setPen(QPen(alpha(GOLD_TEXT, 0.5 + 0.4 * self._hover.level), S(1.4)))
        p.setBrush(g)
        p.drawRoundedRect(r, S(13), S(13))
        p.save()
        clip = QPainterPath()
        clip.addRoundedRect(r, S(13), S(13))
        p.setClipPath(clip)
        p.setPen(Qt.PenStyle.NoPen)
        for x0, y0, sp in self.flakes:
            y = r.top() + ((y0 + now * 0.05 * sp) % 1.0) * r.height()
            x = r.left() + x0 * r.width() + math.sin(now * sp + x0 * 9) * S(4)
            p.setBrush(alpha(SNOW, 0.55))
            p.drawEllipse(QPointF(x, y), S(1.4) * sp, S(1.4) * sp)
        p.restore()
        p.save()                                         # a small wrapped present
        c = QPointF(r.left() + S(32), r.center().y())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(SNOW))
        p.drawRoundedRect(QRectF(c.x() - S(15), c.y() - S(10), S(30), S(24)), S(4), S(4))
        p.setBrush(QColor(RED))
        p.drawRect(QRectF(c.x() - S(3), c.y() - S(10), S(6), S(24)))
        p.drawRect(QRectF(c.x() - S(15), c.y() - S(1), S(30), S(6)))
        p.setPen(QPen(QColor(GOLD_TEXT), S(2)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(c.x() - S(5), c.y() - S(14)), S(5), S(3.5))
        p.drawEllipse(QPointF(c.x() + S(5), c.y() - S(14)), S(5), S(3.5))
        p.restore()
        data = getattr(self.ctx, "advent_data", None) or {}
        today = int(data.get("today") or 0)
        p.setPen(QColor("#FFFFFF"))
        p.setFont(font(14, QFont.Weight.ExtraBold))
        p.drawText(QRectF(r.left() + S(60), r.top() + S(10), r.width() - S(70), S(22)), int(Qt.AlignmentFlag.AlignVCenter),
                   tr("Advent calendar"))
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        p.setPen(QColor("#FFE7A8"))
        if today:
            claimed = any(d.get("day") == today and d.get("claimed") for d in data.get("days") or [])
            sub = tr("Door {n} is open: come and see!", n=today) if not claimed else tr("Door {n} opened. Come back tomorrow!", n=today)
        else:
            sub = tr("Admin preview: opens on 1 December")
        p.drawText(QRectF(r.left() + S(60), r.top() + S(34), r.width() - S(70), S(18)), int(Qt.AlignmentFlag.AlignVCenter), sub)


def advent_card(page, lay) -> None:
    """On the Games lobby, in December (and for the admin all the time)."""
    ctx = page.ctx
    data = getattr(ctx, "advent_data", None)
    if data is None:
        def then(changed: bool) -> None:
            if changed and (ctx.advent_data or {}).get("open") and ctx.window.showing("games") \
                    and not getattr(ctx, "games_sub", None):
                ctx.reload_page("games")
        if ctx.online.logged_in() and not ctx.econ.server_old:
            load_advent(ctx, then)
        return
    if data.get("open"):
        lay.addWidget(AdventCard(page))


class Calendar(QWidget):
    """24 doors and a big one. Click today's door to open it; the admin can right-click any door to peek."""
    COLS = 6

    def __init__(self, page) -> None:
        super().__init__()
        self.page, self.ctx = page, page.ctx
        self.cell = (page.W - S(5) * (self.COLS - 1)) / self.COLS
        self.setFixedSize(page.W, int(4 * (self.cell + S(5)) + S(96)))
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hover = -1
        self.opening = {}                     # day -> time the door started to open
        self.peek = None                      # (day, until)
        self._t = QTimer(self)
        self._t.setInterval(33)
        self._t.timeout.connect(self.update)
        rnd = random.Random(12)
        self.order = list(range(1, 25))
        rnd.shuffle(self.order)               # the doors are mixed up, like a real calendar

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
            top = 4 * (self.cell + S(5))
            return QRectF(0, top, self.width(), S(90))
        k = self.order.index(day)
        r, c = divmod(k, self.COLS)
        return QRectF(c * (self.cell + S(5)), r * (self.cell + S(5)), self.cell, self.cell)

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
            rw = info.get("reward") or {}
            return self.ctx.toast(tr("Door {n}: {what}", n=day, what=reward_text(rw)))
        if not today:
            return self.ctx.toast(tr("The calendar opens on 1 December"), "warn")
        if day > today:
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
            QTimer.singleShot(700, lambda: (sfx.play("on"), ctx.toast(tr("Door {n}: {what}", n=day, what=reward_text(rw)))))
        self.opening[day] = time.monotonic()
        sfx.play("pick")
        ctx.econ.call("rb_advent_claim", {"which": day}, got)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        data = self.data()
        today = int(data.get("today") or 0)
        for day in range(1, 26):
            r = self.door(day).adjusted(0.5, 0.5, -0.5, -0.5)
            info = self.day_info(day)
            claimed = bool(info.get("claimed"))
            is_today = day == today
            big = day == 25
            hov = day == self.hover
            # the space behind the door
            back = QLinearGradient(r.topLeft(), r.bottomLeft())
            back.setColorAt(0, QColor("#1B1410"))
            back.setColorAt(1, QColor("#0C0A08"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(back)
            p.drawRoundedRect(r, S(8), S(8))
            rw = info.get("reward")
            peeking = self.peek is not None and self.peek[0] == day and now < self.peek[1]
            if (claimed or peeking) and rw:
                self._paint_reward(p, r, rw, now)
            opened = claimed or day in self.opening
            k = 1.0 if claimed and day not in self.opening else (min(1.0, (now - self.opening[day]) / 0.6) if day in self.opening else 0.0)
            if peeking:
                k = max(k, 0.55)
            if k < 1.0:                                     # the door itself, swinging open from its left edge
                w = r.width() * (1 - k * 0.92)
                door = QRectF(r.left(), r.top(), w, r.height())
                col = QColor(RED) if (day % 3 == 0) else QColor(GREEN) if day % 3 == 1 else QColor("#2B4C7E")
                if big:
                    col = QColor("#8C1D2C")
                g = QLinearGradient(door.topLeft(), door.bottomRight())
                g.setColorAt(0, mix(col, QColor("#FFFFFF"), 0.12 + 0.1 * hov))
                g.setColorAt(1, mix(col, QColor("#000000"), 0.35))
                p.setBrush(g)
                p.setPen(QPen(alpha(GOLD_TEXT, 0.9 if is_today else 0.35), S(2) if is_today else 1))
                p.drawRoundedRect(door, S(8), S(8))
                if k < 0.5:
                    p.setPen(QColor("#FFFFFF") if not (today and day > today) else alpha("#FFFFFF", 0.4))
                    p.setFont(font(26 if big else 15, QFont.Weight.Black))
                    p.drawText(door, int(Qt.AlignmentFlag.AlignCenter), str(day))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(GOLD_TEXT))
                    p.drawEllipse(QPointF(door.right() - S(7), door.center().y()), S(2.2), S(2.2))   # the knob
                    if big:
                        p.setPen(QColor("#FFE7A8"))
                        p.setFont(font(10, QFont.Weight.Bold, 1.0))
                        p.drawText(door.adjusted(0, 0, 0, -S(8)), int(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter),
                                   tr("THE BIG DOOR"))
                if is_today and not opened:                 # today's door shines
                    pulse = 0.5 + 0.5 * math.sin(now * 4)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.setPen(QPen(alpha(GOLD_TEXT, 0.4 + 0.5 * pulse), S(3)))
                    p.drawRoundedRect(r.adjusted(-S(1), -S(1), S(1), S(1)), S(9), S(9))
            if today and day < today and not claimed and not data.get("catchup"):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(0, 0, 0, 120))
                p.drawRoundedRect(r, S(8), S(8))

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
    lay.addWidget(Label(tr("One door a day from 1 to 24 December, and a big surprise on the 25th. Limited looks and "
                           "limited cases you cannot buy anywhere else."), 10.5, TEXT_DIM, wrap_w=page.W))
    if data.get("admin") and not today:
        lay.addWidget(Label(tr("Admin preview: right-click a door to peek behind it."), 10.5, GOLD_TEXT, wrap_w=page.W))
    lay.addWidget(Calendar(page))
    if today:
        lay.addWidget(Label(tr("Today is {n} December: open door {n}!", n=today) if today <= 25 else
                            tr("The calendar is over. Merry Christmas!"), 11.5, TEXT, wrap_w=page.W))
