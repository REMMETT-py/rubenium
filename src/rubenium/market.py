"""4.6: selling on the market, as a place: the menu fades, a metal shutter rolls down and up again on a night market
stall. Your item sits on the counter under a lamp; a slider sets the price (round numbers between the lowest and
highest the server allows, the usual price marked), with what you get after the 5% fee. List it: a LISTED stamp
lands on the item, the shutter rolls down and opens on the menu again. The prices are the server's
(rb_market_price, rb_market_list)."""
import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient
from PyQt6.QtWidgets import QWidget

from .core import S, TEXT, TEXT_DIM, alpha, font, mix, sfx, tr
from .wallet import coins_text
from .widgets import AmountSlider, Button, hbox, vbox

STALL_TEAL = QColor("#2EC5B6")
STALL_GOLD = QColor("#F2C14E")


def stall_ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def stall_bounce(t: float) -> float:
    """The shutter hits the floor and settles."""
    t = max(0.0, min(1.0, t))
    if t < 0.8:
        return stall_ease(t / 0.8)
    k = (t - 0.8) / 0.2
    return 1 - 0.04 * math.sin(k * math.pi)


class MarketStall(QWidget):
    """Covers the menu while you price your item. Phases: fade 0.3 · close 0.5 · hold · open 0.7 · shop ·
    listed (stamp 1.1) · leave_close 0.45 · leave_open 0.55."""

    def __init__(self, ctx, item: str, ids: list) -> None:
        win = ctx.window
        super().__init__(win)
        self.ctx, self.win, self.item, self.ids = ctx, win, item, list(ids)
        self.lo = self.hi = self.est = 0
        self.price = 0
        self.busy = False
        self.loaded = False
        self.failed = False
        self.listed_at = 0.0
        self.phase, self.t0 = "fade", time.monotonic()
        self.lights = [random.Random(k).random() for k in range(24)]
        self._build_controls()
        self._place()
        self.show()
        self.raise_()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._frame)
        self._timer.start()
        ctx.econ.online.ask("rb_market_price", {"what": item}, self._priced)

    # -- geometry
    def _place(self) -> None:
        try:
            r = self.win._card_rect() if hasattr(self.win, "_card_rect") else QRectF(self.win.rect())
        except RuntimeError:
            return
        g = r.toRect()
        if self.geometry() != g:
            self.setGeometry(g)
            self._layout_controls()

    def _panel(self) -> QRectF:
        w = min(float(self.width()) - S(40), S(560))
        return QRectF((self.width() - w) / 2, 0, w, self.height())

    def _counter_y(self) -> float:
        return self.height() * 0.48

    # -- controls
    def _build_controls(self) -> None:
        self.box = QWidget(self)
        self.box_lay = vbox(self.box, 8)
        self.slider = None
        row = QWidget()
        r = hbox(row, 8)
        self.list_btn = Button("", "primary", 42, icon="chip")
        self.list_btn.clicked.connect(self._list)
        r.addWidget(self.list_btn, 1)
        self.box_lay.addWidget(row)
        self.leave_btn = Button(tr("Leave the market"), "ghost", 32, icon="back", parent=self)
        self.leave_btn.clicked.connect(self.leave)
        self.box.hide()
        self.leave_btn.hide()

    def _layout_controls(self) -> None:
        pn = self._panel()
        top = self._counter_y() + S(150)
        self.box.setGeometry(int(pn.left()), int(top), int(pn.width()), int(S(28) + S(8) + S(42)))
        self.leave_btn.setFixedWidth(max(S(170), self.leave_btn.sizeHint().width() + S(20)))
        self.leave_btn.move(int(S(16)), int(S(16)))

    def _controls(self, on: bool) -> None:
        self.box.setVisible(on)
        self.leave_btn.setVisible(on)
        if on:
            self._texts()

    def _texts(self) -> None:
        self.list_btn.set_text(tr("Put on sale for {n}", n=coins_text(self.price)))
        for b in (self.list_btn, self.leave_btn):
            b.setEnabled(not self.busy)

    # -- the server
    def _priced(self, ok: bool, info) -> None:
        if not ok or not isinstance(info, dict):
            self.failed = True
            self.ctx.toast(tr(str(info)) if not ok else tr("Something went wrong: try again"), "warn")
        else:
            self.lo, self.hi = int(info.get("min") or 1), int(info.get("max") or 1)
            self.est = max(self.lo, min(self.hi, int(info.get("estimate") or self.lo)))
            self.price = self.est
            self.slider = AmountSlider(tr("Price"), self.lo, self.hi, self.est, coins_text, label_w=50)
            vals = self.slider.values                      # the usual price is one of the stops
            if self.est not in vals:
                vals.append(self.est)
                vals.sort()
                self.slider.deleteLater()
                self.slider = AmountSlider(tr("Price"), self.lo, self.hi, self.est, coins_text, label_w=50, values=vals)
            self.slider.changed.connect(self._slid)
            self.box_lay.insertWidget(0, self.slider)
        self.loaded = True

    def _slid(self, v: int) -> None:
        self.price = int(v)
        self._texts()
        self.update()

    def _list(self) -> None:
        if self.busy or self.phase != "shop":
            return
        self.busy = True
        self._texts()
        ctx, ec, n = self.ctx, self.ctx.econ, self.price

        def done(ok: bool, d) -> None:
            try:
                self.busy = False
                if not ok:
                    sfx.play("off")
                    ctx.toast(tr(str(d)), "warn")
                    return self._texts()
                sfx.play("on")
                self.listed_at = time.monotonic()
                self._go("listed")
                ec.refresh()
                ctx.mk_at = 0
            except RuntimeError:
                pass
        ec.call("rb_market_list", {"item_id": self.ids[-1], "price": n}, done)

    # -- phases
    def _go(self, phase: str) -> None:
        self.phase, self.t0 = phase, time.monotonic()
        if phase in ("close", "leave_close"):
            sfx.play("pick")
        if phase != "shop":
            self._controls(False)

    def leave(self) -> None:
        if self.phase == "shop" and not self.busy:
            self._go("leave_close")

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            return self.leave()
        super().keyPressEvent(e)

    def mousePressEvent(self, e) -> None:
        e.accept()

    def _frame(self) -> None:
        self._place()
        t = time.monotonic() - self.t0
        ph = self.phase
        if ph == "fade" and t >= 0.3:
            self._go("close")
        elif ph == "close" and t >= 0.5:
            self._go("hold")
            sfx.play("off")
        elif ph == "hold" and t >= 0.25 and self.loaded:
            self._go("leave_open" if self.failed else "open")
        elif ph == "open" and t >= 0.7:
            self._go("shop")
            self._controls(True)
        elif ph == "listed" and t >= 1.6:
            self._go("leave_close")
        elif ph == "leave_close" and t >= 0.45:
            self._go("leave_open")
        elif ph == "leave_open" and t >= 0.55:
            self._timer.stop()
            self.hide()
            self.deleteLater()
            QTimer.singleShot(50, self.ctx.reload_page)
            return
        self.update()

    def _shutter(self) -> float:
        """0: rolled up out of sight, 1: down to the floor."""
        t = time.monotonic() - self.t0
        ph = self.phase
        if ph in ("close", "leave_close"):
            return stall_bounce(t / (0.5 if ph == "close" else 0.45))
        if ph == "hold":
            return 1.0
        if ph == "open":
            return 1 - stall_ease(t / 0.7)
        if ph == "leave_open":
            return 1 - stall_ease(t / 0.55)
        return 0.0

    def _veil(self) -> float:
        t = time.monotonic() - self.t0
        if self.phase == "fade":
            return 0.9 * stall_ease(t / 0.3)
        if self.phase == "leave_open":
            return 0.9 * (1 - stall_ease(t / 0.55))
        return 0.9

    # -- drawing
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(r, S(14), S(14))
        p.setClipPath(clip)
        now = time.monotonic()
        p.fillRect(r, alpha("#000000", self._veil()))
        if self.phase in ("open", "shop", "listed", "leave_close"):
            self._paint_scene(p, r, now)
        d = self._shutter()
        if d > 0.001:
            self._paint_shutter(p, r, d)

    def _paint_scene(self, p, r, now) -> None:
        sky = QLinearGradient(r.topLeft(), r.bottomLeft())
        sky.setColorAt(0, QColor("#0A1630"))
        sky.setColorAt(0.5, QColor("#14213D"))
        sky.setColorAt(1, QColor("#0B0F17"))
        p.fillRect(r, sky)
        pn = self._panel()
        cy = self._counter_y()
        rnd = random.Random(3)
        p.setPen(Qt.PenStyle.NoPen)
        for _ in range(40):                                      # a few stars
            p.setBrush(alpha("#FFFFFF", rnd.uniform(0.15, 0.6)))
            p.drawEllipse(QPointF(rnd.uniform(0, r.width()), rnd.uniform(0, r.height() * 0.3)), S(0.9), S(0.9))
        self._paint_far_stalls(p, r, cy, now)
        self._paint_lights(p, r, now)
        self._paint_awning(p, pn, now)
        self._paint_counter(p, r, pn, cy, now)
        self._paint_texts(p, pn, cy, now)

    def _paint_far_stalls(self, p, r, cy, now) -> None:
        """Other stalls in the distance, soft and dark, each with a warm glow."""
        rnd = random.Random(11)
        x = r.left() - S(20)
        while x < r.right():
            w = S(rnd.choice([70, 90, 110]))
            h = S(rnd.choice([60, 80, 100]))
            if abs(x + w / 2 - r.center().x()) > self._panel().width() * 0.36:
                base = cy - S(10)
                glow = QRadialGradient(QPointF(x + w / 2, base - h * 0.4), w)
                glow.setColorAt(0, alpha(rnd.choice(["#FF9A4A", "#FFD27A", "#7AD8FF"]), 0.18))
                glow.setColorAt(1, alpha("#000000", 0.0))
                p.setBrush(glow)
                p.drawRect(QRectF(x - w / 2, base - h * 1.4, w * 2, h * 1.6))
                p.setBrush(QColor("#0E1626"))
                p.drawRect(QRectF(x, base - h, w, h))
                roof = QPolygonF([QPointF(x - S(6), base - h), QPointF(x + w / 2, base - h - S(18)), QPointF(x + w + S(6), base - h)])
                p.setBrush(QColor("#152038"))
                p.drawPolygon(roof)
            x += w + S(rnd.choice([18, 30, 44]))

    def _paint_lights(self, p, r, now) -> None:
        """A string of bulbs across the top, each breathing at its own pace."""
        n = len(self.lights)
        pts = []
        for k in range(n + 1):
            x = r.left() + r.width() * k / n
            y = S(30) + math.sin(k / n * math.pi) * S(26)
            pts.append(QPointF(x, y))
        p.setPen(QPen(alpha("#000000", 0.6), S(1.2)))
        p.drawPolyline(QPolygonF(pts))
        cols = ["#FFD27A", "#FF7A8A", "#7AD8FF", "#9BFFB0"]
        for k in range(n):
            c = (pts[k] + pts[k + 1]) / 2 + QPointF(0, S(6))
            on = 0.6 + 0.4 * math.sin(now * (1.2 + self.lights[k]) + k)
            col = QColor(cols[k % 4])
            g = QRadialGradient(c, S(14))
            g.setColorAt(0, alpha(col, 0.45 * on))
            g.setColorAt(1, alpha(col, 0.0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawEllipse(c, S(14), S(14))
            p.setBrush(mix(col, QColor("#FFFFFF"), 0.4 * on))
            p.drawEllipse(c, S(3.2), S(4))

    def _paint_awning(self, p, pn, now) -> None:
        top, h = S(70), S(52)
        aw = QRectF(pn.left() - S(10), top, pn.width() + S(20), h)
        n = 10
        sw = aw.width() / n
        for k in range(n):
            p.setBrush(STALL_TEAL if k % 2 == 0 else QColor("#F4EBDD"))
            p.drawRect(QRectF(aw.left() + k * sw, aw.top(), sw + 0.5, aw.height()))
        for k in range(n):                                       # the scalloped edge
            p.setBrush(STALL_TEAL if k % 2 == 0 else QColor("#F4EBDD"))
            p.drawChord(QRectF(aw.left() + k * sw, aw.bottom() - sw / 2, sw, sw), 180 * 16, 180 * 16)
        shade = QLinearGradient(aw.topLeft(), aw.bottomLeft())
        shade.setColorAt(0, alpha("#000000", 0.0))
        shade.setColorAt(1, alpha("#000000", 0.25))
        p.setBrush(shade)
        p.drawRect(aw)
        sign = QRectF(pn.center().x() - S(120), aw.bottom() + S(22), S(240), S(40))
        glow = QRadialGradient(sign.center(), S(140))
        glow.setColorAt(0, alpha(STALL_GOLD, 0.25 + 0.05 * math.sin(now * 2)))
        glow.setColorAt(1, alpha(STALL_GOLD, 0.0))
        p.setBrush(glow)
        p.drawEllipse(sign.center(), S(140), S(50))
        p.setPen(QPen(STALL_GOLD, S(1.6)))
        p.setBrush(QColor("#101826"))
        p.drawRoundedRect(sign, S(20), S(20))
        p.setPen(STALL_GOLD)
        p.setFont(font(16, QFont.Weight.Black, 3.0))
        p.drawText(sign, int(Qt.AlignmentFlag.AlignCenter), tr("MARKET"))
        p.setPen(Qt.PenStyle.NoPen)

    def _paint_counter(self, p, r, pn, cy, now) -> None:
        top = QRectF(r.left(), cy, r.width(), S(14))
        g = QLinearGradient(top.topLeft(), top.bottomLeft())
        g.setColorAt(0, QColor("#B27A45"))
        g.setColorAt(1, QColor("#7A4E28"))
        p.setBrush(g)
        p.drawRect(top)
        front = QRectF(r.left(), cy + S(14), r.width(), r.height() - cy - S(14))
        g2 = QLinearGradient(front.topLeft(), front.bottomLeft())
        g2.setColorAt(0, QColor("#4A2E18"))
        g2.setColorAt(1, QColor("#1A110A"))
        p.setBrush(g2)
        p.drawRect(front)
        p.setPen(QPen(alpha("#000000", 0.3), 1))
        for k in range(1, 7):
            y = front.top() + front.height() * k / 7
            p.drawLine(QPointF(front.left(), y), QPointF(front.right(), y))
        p.setPen(Qt.PenStyle.NoPen)
        # the lamp over the item, the cloth, the item turning slowly
        c = QPointF(pn.center().x(), cy - S(52))
        beam = QPolygonF([QPointF(c.x() - S(10), S(150)), QPointF(c.x() + S(10), S(150)),
                          QPointF(c.x() + S(90), cy), QPointF(c.x() - S(90), cy)])
        bg = QLinearGradient(QPointF(0, S(150)), QPointF(0, cy))
        bg.setColorAt(0, alpha("#FFE8B0", 0.18))
        bg.setColorAt(1, alpha("#FFE8B0", 0.04))
        p.setBrush(bg)
        p.drawPolygon(beam)
        cloth = QRectF(c.x() - S(70), cy - S(10), S(140), S(18))
        p.setBrush(QColor("#1E3A5A"))
        p.drawRoundedRect(cloth, S(8), S(8))
        if self.item:
            from .collection import show_item
            bob = math.sin(now * 1.8) * S(3)
            box = QRectF(c.x() - S(46), c.y() - S(46) + bob, S(92), S(92))
            glow = QRadialGradient(box.center(), S(80))
            glow.setColorAt(0, alpha(STALL_GOLD, 0.22))
            glow.setColorAt(1, alpha(STALL_GOLD, 0.0))
            p.fillRect(box.adjusted(-S(40), -S(40), S(40), S(40)), glow)
            show_item(p, self.item, box, now)
            if self.listed_at:                                   # the stamp lands
                k = min(1.0, (now - self.listed_at) / 0.35)
                s = 1.8 - 0.8 * stall_ease(k)
                p.save()
                p.translate(box.center())
                p.rotate(-14)
                p.scale(s, s)
                p.setOpacity(min(1.0, k * 1.5))
                st = QRectF(-S(62), -S(20), S(124), S(40))
                p.setPen(QPen(QColor("#3DDC84"), S(3)))
                p.setBrush(alpha("#0B1A12", 0.75))
                p.drawRoundedRect(st, S(6), S(6))
                p.setPen(QColor("#3DDC84"))
                p.setFont(font(16, QFont.Weight.Black, 2.5))
                p.drawText(st, int(Qt.AlignmentFlag.AlignCenter), tr("LISTED"))
                p.restore()
                p.setOpacity(1.0)
                p.setPen(Qt.PenStyle.NoPen)

    def _paint_texts(self, p, pn, cy, now) -> None:
        if self.phase not in ("shop", "open", "listed", "leave_close"):
            return
        from .cosmetics import item_name
        y = cy + S(28)
        p.setPen(QColor(TEXT))
        p.setFont(font(15, QFont.Weight.Black))
        p.drawText(QRectF(pn.left(), y, pn.width(), S(24)), int(Qt.AlignmentFlag.AlignCenter), item_name(self.item))
        if not self.hi:
            return
        p.setFont(font(11.5, QFont.Weight.Bold))
        p.setPen(STALL_GOLD)
        p.drawText(QRectF(pn.left(), y + S(28), pn.width(), S(20)), int(Qt.AlignmentFlag.AlignCenter),
                   tr("Usual price: about {v}", v=coins_text(self.est)))
        get = self.price - self.price * 5 // 100
        p.setPen(QColor("#3DDC84"))
        p.drawText(QRectF(pn.left(), y + S(50), pn.width(), S(20)), int(Qt.AlignmentFlag.AlignCenter),
                   tr("You get {n} when it sells (5% fee)", n=coins_text(get)))
        p.setPen(alpha(TEXT_DIM, 0.85))
        p.setFont(font(10, QFont.Weight.DemiBold))
        p.drawText(QRectF(pn.left(), y + S(72), pn.width(), S(20)), int(Qt.AlignmentFlag.AlignCenter),
                   tr("Players buy it at your price or make you an offer"))

    def _paint_shutter(self, p, r, d) -> None:
        """A metal roller shutter: slats, a bottom bar with a handle and a padlock."""
        h = r.height() * d
        body = QRectF(r.left(), r.top(), r.width(), h)
        slat = S(16)
        y = body.bottom() - slat
        k = 0
        while y > body.top() - slat:
            sr = QRectF(r.left(), y, r.width(), slat)
            g = QLinearGradient(sr.topLeft(), sr.bottomLeft())
            g.setColorAt(0, QColor("#6E7A84"))
            g.setColorAt(0.45, QColor("#9AA6B0"))
            g.setColorAt(1, QColor("#4E5862"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawRect(sr)
            p.setPen(QPen(alpha("#000000", 0.45), S(1)))
            p.drawLine(QPointF(sr.left(), sr.bottom()), QPointF(sr.right(), sr.bottom()))
            y -= slat
            k += 1
        bar = QRectF(r.left(), body.bottom() - S(18), r.width(), S(18))
        g = QLinearGradient(bar.topLeft(), bar.bottomLeft())
        g.setColorAt(0, QColor("#3A424A"))
        g.setColorAt(1, QColor("#1E2328"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRect(bar)
        for side in (-1, 1):
            hx = r.center().x() + side * r.width() * 0.22
            p.setBrush(QColor("#C9CFD4"))
            p.drawRoundedRect(QRectF(hx - S(22), bar.top() - S(10), S(44), S(8)), S(4), S(4))
        if d > 0.95:
            lc = QPointF(r.center().x(), bar.center().y())
            p.setPen(QPen(QColor("#B8902E"), S(3)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(QRectF(lc.x() - S(9), lc.y() - S(22), S(18), S(22)), 0, 180 * 16)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(STALL_GOLD)
            p.drawRoundedRect(QRectF(lc.x() - S(12), lc.y() - S(10), S(24), S(20)), S(4), S(4))
        sign = QRectF(r.center().x() - S(110), body.bottom() - S(120), S(220), S(56))
        if sign.top() > r.top():
            p.setPen(QPen(alpha("#000000", 0.55), S(2)))
            p.setBrush(alpha("#0E1626", 0.85))
            p.drawRoundedRect(sign, S(8), S(8))
            p.setPen(STALL_GOLD)
            p.setFont(font(15, QFont.Weight.Black, 3.0))
            p.drawText(sign, int(Qt.AlignmentFlag.AlignCenter), tr("MARKET"))


def open_market_stall(ctx, item: str) -> None:
    """Sell = put it on the market, at the stall."""
    ec = ctx.econ
    free = [i for i in ec.items if i["item"] == item and not i.get("locked")]
    if not free:
        return ctx.toast(tr("This item is already on the market or in a trade"), "warn")
    if not ec.can_trade():
        return ctx.toast(tr("The market opens after 5 hours with Rubenium"), "warn")
    old = getattr(ctx, "_stall", None)
    try:
        if old is not None and old.isVisible():
            return
    except RuntimeError:
        pass
    ctx._stall = MarketStall(ctx, item, [i["id"] for i in free])
