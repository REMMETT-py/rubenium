"""4.3: the pawn shop: quick sell with a face.

Quick sell asks first, then the menu fades, two shop doors slide shut and open again on the pawn shop. The
shopkeeper offers the quick-sell price: take it, or ask for more. The slider shows the chance he says yes (the
server's own formula, rb_pawn_chance); every no fills his anger bar, and the faint part of the bar shows how much
the next no would add at the price you are asking. At the top of the bar it cracks, the whole shop breaks apart,
the doors slam and you are out for 30 minutes. Coming back while you are out: the doors close on a countdown,
then open on the menu again. The price and the roll are the server's (rb_pawn_sell)."""
import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient
from PyQt6.QtWidgets import QWidget

from .core import S, TEXT, TEXT_DIM, alpha, font, mix, sfx, tr
from .wallet import coins_text
from .widgets import Button, Slider, hbox, vbox

PAWN_GOLD = QColor("#E8C26A")


def pawn_chance(ratio: float, anger: float) -> float:
    """The same as the server's rb_pawn_chance."""
    if ratio <= 1:
        return 1.0
    return max(0.0, max(0.0, 1 - (ratio - 1) / 0.75) ** 1.15 * (1 - min(100.0, anger) / 300.0))     # 4.6: kinder


def pawn_rage(ratio: float) -> float:
    """How much a no adds to his anger (the server's rb_pawn_rage)."""
    return 15 + 50 * min(1.0, max(0.0, (ratio - 1) / 0.5))


def pawn_ease(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def pawn_ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def pawn_ease_in(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * t


def pawn_clock(s: int) -> str:
    s = max(0, int(s))
    return f"{s // 60}:{s % 60:02d}"


# ---------------------------------------------------------------- the overlay
class PawnShop(QWidget):
    """Covers the whole menu while you are in the shop. Phases (seconds): fade 0.3 · close 0.45 · hold · open 0.6 ·
    shop · leave (close 0.4, open 0.5) · crack 1.5 · slam 0.25 + plaque 1.6 · banned (close 0.45, plaque 2.6, open 0.5)."""

    def __init__(self, ctx, ids: list, item: str, what: str) -> None:
        win = ctx.window
        super().__init__(win)
        self.ctx, self.win = ctx, win
        self.ids, self.item, self.what = list(ids), item, what
        self.base, self.anger, self.ban_left, self.max_ratio = 0, 0.0, 0, 1.5
        self.shown_anger = 0.0                      # the bar moves to the new level smoothly
        self.ask_mode = False
        self.ask = 0
        self.busy = False
        self.line = tr("Let's see what you've got.")
        self.line_at = time.monotonic()
        self.phase, self.t0 = "fade", time.monotonic()
        self.loaded = False
        self.after = None                           # what happens when the doors have opened on the menu again
        self.shards: list = []
        self.snap = None
        self.sold_at = 0.0
        self.ban_end = 0.0
        self.setMouseTracking(True)
        self._build_controls()
        self._place()
        self.show()
        self.raise_()
        self.setFocus()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._frame)
        self._timer.start()
        ctx.econ.call("rb_pawn_enter", {"ids": self.ids}, self._entered)

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
        """The middle column everything in the shop lines up on."""
        w = min(float(self.width()) - S(40), S(560))
        return QRectF((self.width() - w) / 2, 0, w, self.height())

    def _counter_y(self) -> float:
        return self.height() * 0.50

    # -- controls (real buttons, shown only while you are in the shop)
    def _build_controls(self) -> None:
        self.box = QWidget(self)
        lay = vbox(self.box, 8)
        self.row_offer = QWidget()
        r1 = hbox(self.row_offer, 8)
        self.take = Button("", "primary", 40, icon="check")
        self.take.clicked.connect(lambda: self._sell(None))
        self.more = Button(tr("Ask for more"), "ghost", 40)
        self.more.clicked.connect(lambda: self._set_ask(True))
        r1.addWidget(self.take, 3)
        r1.addWidget(self.more, 2)
        lay.addWidget(self.row_offer)
        self.row_ask = QWidget()
        r2 = vbox(self.row_ask, 8)
        self.slider = Slider(0, 1, 0, 1)
        self.slider.changed.connect(self._slid)
        r2.addWidget(self.slider)
        btns = QWidget()
        r3 = hbox(btns, 8)
        self.offer = Button("", "primary", 40)
        self.offer.clicked.connect(lambda: self._sell(self.ask))
        self.back = Button(tr("Back"), "ghost", 40)
        self.back.clicked.connect(lambda: self._set_ask(False))
        r3.addWidget(self.offer, 3)
        r3.addWidget(self.back, 2)
        r2.addWidget(btns)
        lay.addWidget(self.row_ask)
        self.leave_btn = Button(tr("Leave the shop"), "ghost", 32, icon="back", parent=self)
        self.leave_btn.clicked.connect(self.leave)
        self.box.hide()
        self.leave_btn.hide()
        self.row_ask.hide()

    def _layout_controls(self) -> None:
        pn = self._panel()
        top = self._counter_y() + S(124)
        h = S(40) + S(8) + S(26) + S(8) + S(40)
        self.box.setGeometry(int(pn.left()), int(top), int(pn.width()), int(h))
        self.leave_btn.adjustSize()
        self.leave_btn.setFixedWidth(max(S(150), self.leave_btn.sizeHint().width() + S(20)))
        self.leave_btn.move(int(S(16)), int(S(16)))

    def _controls(self, on: bool) -> None:
        self.box.setVisible(on)
        self.leave_btn.setVisible(on)
        if on:
            self._refresh_texts()

    def _refresh_texts(self) -> None:
        self.take.set_text(tr("Accept {n}", n=coins_text(self.base)))
        self.row_offer.setVisible(not self.ask_mode)
        self.row_ask.setVisible(self.ask_mode)
        self.offer.set_text(tr("Ask {n}", n=coins_text(self.ask)))
        for b in (self.take, self.more, self.offer, self.back, self.leave_btn):
            b.setEnabled(not self.busy)

    def _set_ask(self, on: bool) -> None:
        if self.busy:
            return
        sfx.play("pick")
        self.ask_mode = on
        if on:
            lo, hi = self._ask_range()
            step = max(1, (hi - lo) // 100)
            self.slider.deleteLater()
            self.slider = Slider(lo, hi, lo + (hi - lo) // 3, step)
            self.slider.changed.connect(self._slid)
            self.row_ask.layout().insertWidget(0, self.slider)
            self.ask = int(self.slider.value())
        self._refresh_texts()
        self.update()

    def _ask_range(self):
        lo = self.base + max(1, self.base // 100)
        hi = max(lo, int(math.floor(self.base * self.max_ratio)))
        return lo, hi

    def _slid(self, v: float) -> None:
        self.ask = int(v)
        self._refresh_texts()
        self.update()

    # -- the server
    def _entered(self, ok: bool, data) -> None:
        if not ok or not isinstance(data, dict):
            self.ctx.toast(tr(str(data)) if not ok else tr("Something went wrong: try again"), "warn")
            return self._go("leave_close")
        self.base = int(data.get("base") or 0)
        self.anger = self.shown_anger = float(data.get("anger") or 0)
        self.ban_left = int(data.get("ban_left") or 0)
        self.max_ratio = float(data.get("max_ratio") or 1.5)
        self.loaded = True
        if self.ban_left > 0:
            self.ban_end = time.monotonic() + self.ban_left
            self.ctx.pawn_ban_until = time.time() + self.ban_left
        elif int(data.get("n") or 0) == 0:
            self.ctx.toast(tr("This cannot be sold"), "warn")
            self.ban_left = -1                                    # nothing to sell: just open back on the menu
        self.line = tr("I'll give you {n} coins for {what}.", n=coins_text(self.base), what=self.what)
        self.line_at = time.monotonic()

    def _sell(self, ask) -> None:
        if self.busy or self.phase != "shop":
            return
        self.busy = True
        self._refresh_texts()
        sfx.play("pick")

        def done(ok: bool, data) -> None:
            self.busy = False
            try:
                if not ok or not isinstance(data, dict):
                    self.ctx.toast(tr(str(data)), "warn")
                    return self._refresh_texts()
                res = data.get("result")
                self.anger = float(data.get("anger") or 0)
                if res == "yes":
                    sfx.play("on")
                    self.line, self.line_at = tr("Deal. Pleasure doing business."), time.monotonic()
                    self.sold_at = time.monotonic()
                    self.paid = int(data.get("paid") or 0)
                    ec = self.ctx.econ
                    gone = set(self.ids)
                    ec.items = [i for i in ec.items if i["id"] not in gone]
                    ec._index()
                    ec.refresh()
                    self.after = lambda: (self.ctx.toast(tr("Sold for {n} coins", n=coins_text(self.paid))),
                                          setattr(self.ctx, "inv_pick", ""), self.ctx.reload_page())
                    self._controls(False)
                    QTimer.singleShot(1500, lambda: self._go("leave_close"))
                elif res == "kicked":
                    self.anger = 100.0
                    self.line, self.line_at = tr("That's it. GET OUT!"), time.monotonic()
                    self.after = lambda: self.ctx.toast(tr("Thrown out of the pawn shop for 30 minutes"), "warn")
                    self._controls(False)
                    sfx.play("off")
                    QTimer.singleShot(500, self._crack)
                elif res == "banned":
                    self.ban_left = int(data.get("ban_left") or 0)
                    self.ban_end = time.monotonic() + self.ban_left
                    self.ctx.pawn_ban_until = time.time() + self.ban_left
                    self._controls(False)
                    self._go("ban_close")
                else:
                    sfx.play("off")
                    self.line = (tr("No way.") if self.anger < 45 else tr("You're pushing it.") if self.anger < 75
                                 else tr("One more and you're out."))
                    self.line_at = time.monotonic()
                    lo, hi = self._ask_range()
                    self.slider.set_value(max(lo, min(self.ask, hi)))
                    self._refresh_texts()
            except RuntimeError:
                pass
        self.ctx.econ.call("rb_pawn_sell", {"ids": self.ids, "ask": ask}, done, once=True)

    # -- phases
    def _go(self, phase: str) -> None:
        self.phase, self.t0 = phase, time.monotonic()
        if phase in ("close", "leave_close", "ban_close"):
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
        e.accept()                                     # nothing under the shop can be clicked

    def _crack(self) -> None:
        """The bar cracks, then the whole shop breaks into pieces that fall away."""
        self._go("crack")
        self.snap = None
        rnd = random.Random(int(time.time()))
        self.crack_seed = rnd.randrange(1 << 30)
        bar = self._bar_rect()
        self.crack_at = QPointF(bar.left() + bar.width() * rnd.uniform(0.55, 0.9), bar.center().y())

    def _make_shards(self) -> None:
        self.snap = self.grab()
        rnd = random.Random(self.crack_seed)
        c = self.crack_at
        n = 14
        angs = sorted(rnd.uniform(0, math.tau) for _ in range(n))
        far = math.hypot(self.width(), self.height()) * 1.2
        self.shards = []
        for i in range(n):
            a1, a2 = angs[i], angs[(i + 1) % n] + (math.tau if i == n - 1 else 0)
            mid = (a1 + a2) / 2
            poly = QPolygonF([c, c + QPointF(math.cos(a1) * far, math.sin(a1) * far),
                              c + QPointF(math.cos(mid) * far * 1.1, math.sin(mid) * far * 1.1),
                              c + QPointF(math.cos(a2) * far, math.sin(a2) * far)])
            self.shards.append((poly, math.cos(mid) * rnd.uniform(60, 220), rnd.uniform(-260, -40),
                                rnd.uniform(-90, 90), rnd.uniform(0, 0.15)))

    def _frame(self) -> None:
        self._place()
        now = time.monotonic()
        t = now - self.t0
        ph = self.phase
        if ph == "fade" and t >= 0.3:
            self._go("close")
        elif ph == "close" and t >= 0.45:
            self._go("hold")
            sfx.play("off")
        elif ph == "hold" and t >= 0.25 and self.loaded:
            if self.ban_left > 0:
                self._go("ban_close")
                self.t0 -= 0.45                              # the doors are shut already: straight to the plaque
            elif self.ban_left < 0:
                self._go("leave_open")
            else:
                self._go("open")
        elif ph == "open" and t >= 0.6:
            self._go("shop")
            self._controls(True)
        elif ph == "leave_close" and t >= 0.4:
            self._go("leave_open")
        elif ph == "ban_close" and t >= 0.45 + 2.6:
            self._go("leave_open")
        elif ph == "crack":
            if t >= 0.55 and self.snap is None:
                self._make_shards()
            if t >= 1.5:
                self._go("slam")
                self.ban_end = time.monotonic() + 1800
                self.ctx.pawn_ban_until = time.time() + 1800
        elif ph == "slam" and t >= 0.25 + 1.6:
            self._go("leave_open")
        elif ph == "leave_open" and t >= 0.5:
            return self._finish()
        self.shown_anger += (self.anger - self.shown_anger) * 0.12
        self.update()

    def _finish(self) -> None:
        self._timer.stop()
        after = self.after
        self.hide()
        self.deleteLater()
        if after:
            after()

    # -- drawing
    def _doors(self) -> float:
        """0: open (out of sight), 1: shut."""
        t = time.monotonic() - self.t0
        ph = self.phase
        if ph == "fade":
            return 0.0
        if ph in ("close", "leave_close", "ban_close"):
            return pawn_ease(t / (0.45 if ph != "leave_close" else 0.4))
        if ph in ("hold",):
            return 1.0
        if ph == "open":
            return 1 - pawn_ease(t / 0.6)
        if ph == "slam":
            return pawn_ease_in(t / 0.25)
        if ph == "leave_open":
            return 1 - pawn_ease(t / 0.5)
        return 0.0

    def _veil(self) -> float:
        """How dark the menu behind is."""
        t = time.monotonic() - self.t0
        if self.phase == "fade":
            return 0.9 * pawn_ease(t / 0.3)
        if self.phase == "leave_open":
            return 0.9 * (1 - pawn_ease(t / 0.5))
        return 0.9

    def _scene_on(self) -> bool:
        """The shop behind the doors: there while you are in it (and while it falls apart)."""
        return self.phase in ("open", "shop", "leave_close", "crack")

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(r, S(14), S(14))
        p.setClipPath(clip)
        now = time.monotonic()
        p.fillRect(r, alpha("#000000", self._veil()))
        if self.phase == "crack" and self.snap is not None:
            p.fillRect(r, QColor("#000000"))
            self._paint_shards(p, now)
        elif self._scene_on():
            self._paint_scene(p, r, now)
            if self.phase == "crack":
                self._paint_cracks(p, now)
        d = self._doors()
        if d > 0.001:
            self._paint_doors(p, r, d, now)

    # the shop
    def _paint_scene(self, p, r, now) -> None:
        wall = QLinearGradient(r.topLeft(), r.bottomLeft())
        wall.setColorAt(0, QColor("#2A1C14"))
        wall.setColorAt(1, QColor("#120C09"))
        p.fillRect(r, wall)
        lamp = QRadialGradient(QPointF(r.center().x(), r.top() + r.height() * 0.18), r.width() * 0.55)
        lamp.setColorAt(0, alpha("#FFC874", 0.22))
        lamp.setColorAt(1, alpha("#FFC874", 0.0))
        p.fillRect(r, lamp)
        pn = self._panel()
        cy = self._counter_y()
        self._paint_shelves(p, r, cy)
        self._paint_sign(p, pn)
        self._paint_keeper(p, pn, cy, now)
        self._paint_counter(p, r, cy, now)
        self._paint_bar(p, now)
        self._paint_texts(p, pn, cy, now)

    def _paint_shelves(self, p, r, cy) -> None:
        rnd = random.Random(7)
        p.setPen(Qt.PenStyle.NoPen)
        for row in range(3):
            y = r.top() + r.height() * (0.20 + row * 0.10)
            p.setBrush(QColor("#3B2819"))
            p.drawRect(QRectF(r.left(), y, r.width(), S(6)))
            x = r.left() + S(10)
            while x < r.right() - S(30):
                w = S(rnd.choice([14, 18, 22, 26]))
                h = S(rnd.choice([18, 24, 30, 36]))
                if abs((x + w / 2) - r.center().x()) > self._panel().width() * 0.42:     # keep the middle clear
                    p.setBrush(alpha(rnd.choice(["#7A5A3A", "#5C6B73", "#8C7A4A", "#6E4A5A", "#4A6A5A"]), 0.55))
                    if rnd.random() < 0.4:
                        p.drawEllipse(QRectF(x, y - h, w, h))
                    else:
                        p.drawRoundedRect(QRectF(x, y - h, w, h), S(3), S(3))
                x += w + S(rnd.choice([6, 10, 16]))

    def _paint_sign(self, p, pn) -> None:
        sign = QRectF(pn.center().x() - S(150), S(58), S(300), S(46))
        g = QLinearGradient(sign.topLeft(), sign.bottomLeft())
        g.setColorAt(0, QColor("#5A3A22"))
        g.setColorAt(1, QColor("#3A2414"))
        p.setPen(QPen(QColor("#2A190D"), S(2)))
        p.setBrush(g)
        p.drawRoundedRect(sign, S(6), S(6))
        p.setPen(PAWN_GOLD)
        p.setFont(font(17, QFont.Weight.Black, 2.0))
        p.drawText(sign, int(Qt.AlignmentFlag.AlignCenter), tr("PAWN SHOP"))
        p.setPen(QPen(alpha("#000000", 0.5), S(1.5)))
        p.drawLine(QPointF(sign.left() + S(30), sign.top()), QPointF(sign.left() + S(30), sign.top() - S(20)))
        p.drawLine(QPointF(sign.right() - S(30), sign.top()), QPointF(sign.right() - S(30), sign.top() - S(20)))

    def _paint_keeper(self, p, pn, cy, now) -> None:
        a = min(1.0, self.shown_anger / 100)
        c = QPointF(pn.center().x() + pn.width() * 0.26, cy - S(62))
        shake = math.sin(now * 40) * S(2) * max(0.0, a - 0.75) * 4
        c += QPointF(shake, 0)
        p.setPen(Qt.PenStyle.NoPen)
        body = QPainterPath()                              # shoulders
        body.moveTo(c.x() - S(62), cy)
        body.cubicTo(c.x() - S(58), c.y() + S(30), c.x() - S(30), c.y() + S(26), c.x(), c.y() + S(26))
        body.cubicTo(c.x() + S(30), c.y() + S(26), c.x() + S(58), c.y() + S(30), c.x() + S(62), cy)
        body.closeSubpath()
        p.setBrush(QColor("#3C4A3A"))
        p.drawPath(body)
        skin = mix(QColor("#D9A57A"), QColor("#E0523C"), a * 0.85)
        p.setBrush(skin)
        p.drawEllipse(c, S(30), S(34))
        p.setBrush(QColor("#2A1C14"))                      # hair and a cap
        p.drawChord(QRectF(c.x() - S(31), c.y() - S(36), S(62), S(40)), 0, 180 * 16)
        eye_y = c.y() - S(2)
        for sx in (-1, 1):
            e = QPointF(c.x() + sx * S(11), eye_y)
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(e, S(5), S(4.2) * (1 - 0.35 * a))
            p.setBrush(QColor("#1A1210"))
            p.drawEllipse(e + QPointF(sx * -S(1), S(0.5)), S(2.2), S(2.2))
            p.setPen(QPen(QColor("#2A1C14"), S(2.6), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            outer = QPointF(e.x() + sx * S(7), eye_y - S(10))       # the inner ends drop as he gets angry
            inner = QPointF(e.x() - sx * S(5), eye_y - S(9) + S(6) * a)
            p.drawLine(outer, inner)
            p.setPen(Qt.PenStyle.NoPen)
        mouth = QPainterPath()
        my = c.y() + S(16)
        bend = S(5) * (1 - 2 * a)                           # a smile, then a flat line, then a frown
        mouth.moveTo(c.x() - S(10), my)
        mouth.quadTo(QPointF(c.x(), my + bend), QPointF(c.x() + S(10), my))
        p.setPen(QPen(QColor("#5A2A1E"), S(2.4), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(mouth)
        # his speech bubble, to his left
        age = now - self.line_at
        if self.line:
            p.setFont(font(12, QFont.Weight.Bold))
            fm = p.fontMetrics()
            maxw = pn.width() * 0.52
            br = fm.boundingRect(0, 0, int(maxw), 400, int(Qt.TextFlag.TextWordWrap), self.line)
            bw, bh = br.width() + S(30), br.height() + S(22)      # 4.6: room for every line (no half-hidden words)
            b = QRectF(c.x() - S(46) - bw, c.y() - S(40), bw, bh)
            b.moveLeft(max(pn.left(), b.left()))
            k = pawn_ease_out(age / 0.25)
            p.save()
            p.translate(b.right(), b.bottom())
            p.scale(0.85 + 0.15 * k, 0.85 + 0.15 * k)
            p.translate(-b.right(), -b.bottom())
            p.setOpacity(k)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#F4EBDD"))
            p.drawRoundedRect(b, S(10), S(10))
            tail = QPolygonF([QPointF(b.right() - S(4), b.top() + S(12)), QPointF(b.right() + S(14), b.top() + S(20)),
                              QPointF(b.right() - S(4), b.top() + S(24))])
            p.drawPolygon(tail)
            p.setPen(QColor("#B3261E") if a > 0.7 else QColor("#2A1C14"))
            p.drawText(b.adjusted(S(13), S(8), -S(13), -S(8)), int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignCenter),
                       self.line)
            p.restore()

    def _paint_counter(self, p, r, cy, now) -> None:
        top = QRectF(r.left(), cy, r.width(), S(14))
        g = QLinearGradient(top.topLeft(), top.bottomLeft())
        g.setColorAt(0, QColor("#8A5A34"))
        g.setColorAt(1, QColor("#5A3A20"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRect(top)
        front = QRectF(r.left(), cy + S(14), r.width(), r.height() - cy - S(14))
        g2 = QLinearGradient(front.topLeft(), front.bottomLeft())
        g2.setColorAt(0, QColor("#3E2716"))
        g2.setColorAt(1, QColor("#1E130B"))
        p.setBrush(g2)
        p.drawRect(front)
        p.setPen(QPen(alpha("#000000", 0.35), 1))
        for k in range(1, 8):
            x = r.left() + r.width() * k / 8
            p.drawLine(QPointF(x, front.top()), QPointF(x, front.bottom()))
        # the item on a velvet pad (it slides away once he buys it)
        pn = self._panel()
        pad = QRectF(pn.center().x() - pn.width() * 0.26 - S(56), cy - S(20), S(112), S(26))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#5A1E2A"))
        p.drawRoundedRect(pad, S(8), S(8))
        if self.item:
            from .collection import show_item
            k = pawn_ease_in((now - self.sold_at) / 0.8) if self.sold_at else 0.0
            box = QRectF(pad.center().x() - S(36), pad.top() - S(62), S(72), S(72))
            box.translate(pn.width() * 0.5 * k, -S(10) * math.sin(k * math.pi))
            p.setOpacity(1 - k)
            glow = QRadialGradient(box.center(), S(60))
            glow.setColorAt(0, alpha(PAWN_GOLD, 0.25))
            glow.setColorAt(1, alpha(PAWN_GOLD, 0.0))
            p.fillRect(box.adjusted(-S(30), -S(30), S(30), S(30)), glow)
            show_item(p, self.item, box, now)
            p.setOpacity(1.0)
            if len(self.ids) > 1:
                p.setPen(QColor(TEXT))
                p.setFont(font(12, QFont.Weight.Black))
                p.drawText(QRectF(box.right() - S(6), box.bottom() - S(20), S(50), S(20)), int(Qt.AlignmentFlag.AlignVCenter),
                           f"×{len(self.ids)}")

    def _bar_rect(self) -> QRectF:
        pn = self._panel()
        return QRectF(pn.left() + S(80), S(126), pn.width() - S(160), S(16))

    def _paint_bar(self, p, now) -> None:
        bar = self._bar_rect()
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(9.5, QFont.Weight.Black, 1.2))
        p.drawText(QRectF(bar.left(), bar.top() - S(18), bar.width(), S(16)), int(Qt.AlignmentFlag.AlignCenter),
                   tr("HIS PATIENCE RUNS OUT"))
        shake = 0.0
        if self.phase == "crack":
            shake = math.sin(now * 60) * S(3) * min(1.0, (now - self.t0) / 0.2)
        bar = bar.translated(shake, 0)
        path = QPainterPath()
        path.addRoundedRect(bar, bar.height() / 2, bar.height() / 2)
        p.setPen(QPen(alpha("#000000", 0.6), S(1.5)))
        p.setBrush(QColor("#1A120C"))
        p.drawPath(path)
        grad = QLinearGradient(bar.topLeft(), bar.topRight())
        grad.setColorAt(0, QColor("#3DDC84"))
        grad.setColorAt(0.5, QColor("#F2C94C"))
        grad.setColorAt(1, QColor("#FF3B3B"))
        p.save()
        p.setClipPath(path)
        a = max(0.0, min(100.0, self.shown_anger)) / 100
        p.setPen(Qt.PenStyle.NoPen)
        if self.ask_mode and self.phase == "shop" and self.base:           # the next no, if he says no at this price
            nxt = min(1.0, a + pawn_rage(self.ask / self.base) / 100)
            p.setOpacity(0.32 + 0.1 * math.sin(now * 5))
            p.setBrush(grad)
            p.drawRect(QRectF(bar.left(), bar.top(), bar.width() * nxt, bar.height()))
            p.setOpacity(1.0)
        p.setBrush(grad)
        p.drawRect(QRectF(bar.left(), bar.top(), bar.width() * a, bar.height()))
        p.restore()
        if self.phase == "crack":                                      # the crack, then it splits
            self._paint_bar_crack(p, bar, now)

    def _paint_bar_crack(self, p, bar, now) -> None:
        k = min(1.0, (now - self.t0) / 0.35)
        rnd = random.Random(self.crack_seed)
        c = QPointF(self.crack_at.x(), bar.center().y())
        p.setPen(QPen(QColor("#FFFFFF"), S(1.6)))
        for _ in range(5):
            ang = rnd.uniform(0, math.tau)
            pt = QPointF(c)
            path = QPainterPath(pt)
            for _s in range(4):
                ang += rnd.uniform(-0.6, 0.6)
                pt = pt + QPointF(math.cos(ang) * S(9) * k, math.sin(ang) * S(5) * k)
                path.lineTo(pt)
            p.drawPath(path)

    def _paint_cracks(self, p, now) -> None:
        """Before it breaks: cracks run out from the bar across everything."""
        t = now - self.t0
        k = max(0.0, min(1.0, (t - 0.25) / 0.3))
        if k <= 0:
            return
        rnd = random.Random(self.crack_seed + 1)
        c = self.crack_at
        far = math.hypot(self.width(), self.height())
        for _ in range(14):
            ang = rnd.uniform(0, math.tau)
            pt = QPointF(c)
            path = QPainterPath(pt)
            n = 9
            for s in range(n):
                if s / n > k:
                    break
                ang += rnd.uniform(-0.35, 0.35)
                step = far / n * rnd.uniform(0.6, 1.2)
                pt = pt + QPointF(math.cos(ang) * step, math.sin(ang) * step)
                path.lineTo(pt)
            p.setPen(QPen(alpha("#FFFFFF", 0.85), S(1.4)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            p.setPen(QPen(alpha("#000000", 0.5), S(3)))
            p.drawPath(path.translated(S(1), S(1)))

    def _paint_shards(self, p, now) -> None:
        t = max(0.0, now - self.t0 - 0.55)
        for poly, vx, vy, spin, delay in self.shards:
            tt = max(0.0, t - delay)
            dx, dy = vx * tt * S(1), (vy * tt + 0.5 * 1800 * tt * tt) * S(1) / 2
            p.save()
            c = poly.boundingRect().center()
            p.translate(c.x() + dx, c.y() + dy)
            p.rotate(spin * tt)
            p.translate(-c.x(), -c.y())
            path = QPainterPath()
            path.addPolygon(poly)
            path.closeSubpath()
            p.setClipPath(path)
            p.setOpacity(max(0.0, 1 - tt / 0.95))
            p.drawPixmap(0, 0, self.snap)
            p.restore()

    def _paint_texts(self, p, pn, cy, now) -> None:
        if self.phase not in ("shop", "open", "leave_close"):
            return
        y = cy + S(34)
        p.setPen(QColor(TEXT))
        p.setFont(font(15, QFont.Weight.Black))
        p.drawText(QRectF(pn.left(), y, pn.width(), S(26)), int(Qt.AlignmentFlag.AlignCenter), self.what)
        p.setFont(font(12, QFont.Weight.Bold))
        if self.sold_at:
            p.setPen(QColor("#3DDC84"))
            p.drawText(QRectF(pn.left(), y + S(32), pn.width(), S(22)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("Sold for {n} coins", n=coins_text(getattr(self, "paid", 0))))
        elif self.ask_mode and self.base:
            ch = pawn_chance(self.ask / self.base, self.anger)
            col = QColor("#3DDC84") if ch >= 0.6 else QColor("#F2C94C") if ch >= 0.3 else QColor("#FF6B5C")
            p.setPen(col)
            p.drawText(QRectF(pn.left(), y + S(32), pn.width(), S(22)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("Chance he says yes: {p}%", p=int(round(ch * 100))))
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(10.5, QFont.Weight.DemiBold))
            p.drawText(QRectF(pn.left(), y + S(56), pn.width(), S(20)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("If he says no, the faint part of the bar is how angry he gets"))
        else:
            p.setPen(PAWN_GOLD)
            p.drawText(QRectF(pn.left(), y + S(32), pn.width(), S(22)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("His offer: {n} coins", n=coins_text(self.base)) if self.base else "…")
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(10.5, QFont.Weight.DemiBold))
            p.drawText(QRectF(pn.left(), y + S(56), pn.width(), S(20)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("Take it, or ask for more (up to +50%)"))
        # how it works, under the buttons
        foot = QRectF(pn.left(), self.box.geometry().bottom() + S(14), pn.width(), S(60))
        p.setPen(alpha(TEXT_DIM, 0.85))
        p.setFont(font(10, QFont.Weight.DemiBold))
        p.drawText(foot, int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop),
                   tr("The more you ask, the less likely he says yes. Every no makes him angrier (he calms down over "
                      "time). If his patience runs out, he throws you out for 30 minutes."))

    # the doors
    def _paint_doors(self, p, r, d, now) -> None:
        half = r.width() / 2
        off = (1 - d) * (half + S(20))
        for side in (0, 1):
            x = (r.left() - off) if side == 0 else (r.center().x() + off)
            door = QRectF(x, r.top(), half, r.height())
            g = QLinearGradient(door.topLeft(), door.topRight())
            g.setColorAt(0, QColor("#4A2E1A") if side == 0 else QColor("#3A2414"))
            g.setColorAt(1, QColor("#3A2414") if side == 0 else QColor("#4A2E1A"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(g)
            p.drawRect(door)
            p.setPen(QPen(alpha("#000000", 0.35), S(1.2)))                 # planks
            for k in range(1, 6):
                xx = door.left() + door.width() * k / 6
                p.drawLine(QPointF(xx, door.top()), QPointF(xx, door.bottom()))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#2A2A2E"))                                    # iron bands with rivets
            for fy in (0.14, 0.86):
                band = QRectF(door.left(), door.top() + door.height() * fy - S(9), door.width(), S(18))
                p.drawRect(band)
                p.setBrush(QColor("#55555C"))
                for k in range(1, 8):
                    p.drawEllipse(QPointF(band.left() + band.width() * k / 8, band.center().y()), S(2.6), S(2.6))
                p.setBrush(QColor("#2A2A2E"))
            edge = door.right() if side == 0 else door.left()                # the handles meet in the middle
            hc = QPointF(edge + (-S(26) if side == 0 else S(26)), door.center().y())
            p.setBrush(QColor("#C9A24A"))
            p.drawEllipse(hc, S(9), S(9))
            p.setBrush(QColor("#7A5A20"))
            p.drawEllipse(hc, S(4), S(4))
            p.setPen(QPen(alpha("#000000", 0.6), S(3)))
            p.drawLine(QPointF(edge, door.top()), QPointF(edge, door.bottom()))
        if d > 0.98 and self.phase in ("ban_close", "slam") and self.ban_end:
            self._paint_plaque(p, r, now)

    def _paint_plaque(self, p, r, now) -> None:
        """4.6: a big plaque with a big countdown, easy to read from across the room."""
        left = max(0, int(math.ceil(self.ban_end - now)))
        pl = QRectF(r.center().x() - S(190), r.center().y() - S(190), S(380), S(170))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#000000", 0.45))
        p.drawRoundedRect(pl.translated(0, S(5)), S(10), S(10))
        p.setPen(QPen(QColor("#2A190D"), S(3)))
        p.setBrush(QColor("#EFE5CF"))
        p.drawRoundedRect(pl, S(10), S(10))
        p.setPen(QPen(alpha("#8A1C14", 0.5), S(1.5)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(pl.adjusted(S(7), S(7), -S(7), -S(7)), S(6), S(6))
        p.setPen(QColor("#8A1C14"))
        p.setFont(font(16, QFont.Weight.Black, 2.0))
        p.drawText(QRectF(pl.left(), pl.top() + S(16), pl.width(), S(26)), int(Qt.AlignmentFlag.AlignCenter),
                   tr("CLOSED TO YOU"))
        pulse = 0.85 + 0.15 * math.sin(now * 3)
        p.setPen(QColor(int(178 * pulse), 30, 24))
        p.setFont(font(40, QFont.Weight.Black))
        p.drawText(QRectF(pl.left(), pl.top() + S(46), pl.width(), S(62)), int(Qt.AlignmentFlag.AlignCenter),
                   pawn_clock(left))
        p.setFont(font(11.5, QFont.Weight.Bold))
        p.setPen(QColor("#4A3A2A"))
        p.drawText(QRectF(pl.left(), pl.top() + S(112), pl.width(), S(20)), int(Qt.AlignmentFlag.AlignCenter),
                   tr("before you can come back in"))
        p.setFont(font(10, QFont.Weight.DemiBold))
        p.setPen(QColor("#6A5A4A"))
        p.drawText(QRectF(pl.left(), pl.top() + S(136), pl.width(), S(20)), int(Qt.AlignmentFlag.AlignCenter),
                   tr("You made him too angry"))


def open_pawn(ctx, ids: list, item: str, what: str) -> None:
    """Quick sell: ask first, then walk into the pawn shop."""
    if not ids:
        return
    old = getattr(ctx, "_pawn", None)
    try:
        if old is not None and old.isVisible():
            return
    except RuntimeError:
        pass

    def go() -> None:
        ctx._pawn = PawnShop(ctx, ids, item, what)
    ctx.window.confirm(tr("Go to the pawn shop to sell {what}?", what=what), go, yes=tr("Yes"), no=tr("No"))
