"""3.2: Coinflip, a duel of items.

Open a coinflip: pick black or white and up to 6 of your items. It waits in the lobby. Someone joins by picking up to 6
items worth about the same (within 10%) and locking in: only then are they in (4.2: the first to lock in gets the seat,
the others are told and keep everything). Or play a bot: it is searched, found, picks its items, joins, 3-2-1, and the
usual 15 second count starts. Once both sides are in, nothing can be taken back: the coin flips and lands on black or
white. The winner takes every item. The chance follows
the share of the pot, never below 49% or above 51%. The server decides the flip the moment both sides are locked in,
keeps it secret until the coin lands, then moves the items once: nothing can be copied or undone."""
import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from .core import S, sfx, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, lang, mix, tr, ui
from .shop import GOLD_TEXT
from .wallet import coins_text, paint_coin
from .widgets import Button, IconButton, Label, Segmented, hbox

WIN_C, LOSE_C = "#35E0A1", "#FF5C6C"


def pct(x: float) -> str:
    t = f"{x * 100:.1f}%"
    return t.replace(".", ",") if lang() == "fr" else t


def side_name(side: str) -> str:
    return tr("Black") if side == "black" else tr("White")


# ================================================================ your items to put in
class ItemPicker(QWidget):
    """Your items that can go in a coinflip (tradeable, free, worth something). Click to add or take out; 6 at most."""
    changed = pyqtSignal()

    def __init__(self, page, limit: int = 6, want=None) -> None:
        super().__init__()
        self.page, self.ctx, self.limit = page, page.ctx, limit
        self.want = want                                    # (min, max) worth a joiner must reach, or None
        ec = self.ctx.econ
        rows = []
        for it in ec.items:
            info = ec.info(it["item"])
            if it.get("locked") or not info or not info.get("tradeable") or info.get("kind") in ("prog", "tag"):
                continue
            w = ec.worth(it["item"])
            if w > 0:
                rows.append((it["id"], it["item"], w))
        rows.sort(key=lambda r: -r[2])
        self.rows = rows                                    # 4.6: all of them, not the first 60
        self.picked: list = []
        self.per = 5
        self.th = S(70)
        n = max(1, (len(self.rows) + self.per - 1) // self.per)
        self.setFixedSize(page.W, n * self.th + (n - 1) * S(5) if self.rows else S(60))
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hover = -1

    def total(self) -> int:
        return sum(w for iid, _it, w in self.rows if iid in self.picked)

    def ids(self) -> list:
        return list(self.picked)

    def _tile(self, i: int) -> QRectF:
        gap = S(5)
        w = (self.width() - gap * (self.per - 1)) / self.per
        r, c = divmod(i, self.per)
        return QRectF(c * (w + gap), r * (self.th + gap), w, self.th)

    def _at(self, pos) -> int:
        return next((i for i in range(len(self.rows)) if self._tile(i).contains(pos)), -1)

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

    def mouseReleaseEvent(self, e) -> None:
        i = self._at(e.position())
        if i < 0:
            return
        iid = self.rows[i][0]
        if iid in self.picked:
            self.picked.remove(iid)
            sfx.play("off")
        elif len(self.picked) >= self.limit:
            return self.ctx.toast(tr("{n} items at most", n=self.limit), "warn")
        else:
            self.picked.append(iid)
            sfx.play("pick")
            from .bazaar import show_item_tip                # 4.6: what was just put in, up close
            show_item_tip(self.ctx, self, self._tile(i), self.rows[i][1], self.rows[i][2])
        self.update()
        self.changed.emit()

    def paintEvent(self, _e) -> None:
        from .collection import rarity_colour, show_item
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.rows:
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(11))
            p.drawText(QRectF(self.rect()), int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                       tr("No item to put in: get some from cases, the shop or the market."))
            return
        now = time.monotonic()
        for i, (iid, item, w) in enumerate(self.rows):
            r = self._tile(i).adjusted(0.5, 0.5, -0.5, -0.5)
            on = iid in self.picked
            col = rarity_colour(self.ctx, item)
            p.setPen(QPen(ui.accent if on else alpha(col, 0.35 if i == self.hover else 0.15), S(2) if on else 1))
            p.setBrush(alpha(col, 0.16 if on else 0.06))
            p.drawRoundedRect(r, S(9), S(9))
            d = min(r.width(), r.height()) * 0.52
            show_item(p, item, QRectF(r.center().x() - d / 2, r.top() + S(6), d, d), now, effects=False)
            p.setPen(QColor(GOLD_TEXT))
            p.setFont(font(9, QFont.Weight.Bold))
            p.drawText(QRectF(r.left(), r.bottom() - S(17), r.width(), S(14)), int(Qt.AlignmentFlag.AlignCenter),
                       coins_text(w))
            if on:
                k = self.picked.index(iid) + 1
                b = QRectF(r.right() - S(17), r.top() + S(3), S(14), S(14))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(ui.accent)
                p.drawEllipse(b)
                p.setPen(QColor("#06110A"))
                p.setFont(font(8.5, QFont.Weight.Black))
                p.drawText(b, int(Qt.AlignmentFlag.AlignCenter), str(k))


class TotalBar(QWidget):
    """What you put in, and (for a joiner) the range it must be in."""

    def __init__(self, picker: ItemPicker, want=None, other: int = 0) -> None:
        super().__init__()
        self.picker, self.want, self.other = picker, want, int(other or 0)   # other: what the creator put in
        self.setFixedHeight(S(52) if self.other else S(38))
        picker.changed.connect(self.update)

    def ok(self) -> bool:
        t = self.picker.total()
        if not self.picker.picked:
            return False
        return self.want is None or self.want[0] <= t <= self.want[1]

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        t = self.picker.total()
        good = self.ok()
        p.setPen(QPen(alpha(WIN_C if good else "#FFFFFF", 0.5 if good else 0.1), 1.2))
        p.setBrush(alpha("#FFFFFF", 0.04))
        p.drawRoundedRect(r, S(10), S(10))
        paint_coin(p, QPointF(r.left() + S(18), r.center().y()), S(7))
        p.setPen(QColor(TEXT))
        p.setFont(font(13, QFont.Weight.Bold))
        p.drawText(r.adjusted(S(32), 0, 0, 0), int(Qt.AlignmentFlag.AlignVCenter),
                   coins_text(t) + "  ·  " + tr("{n}/{m} items", n=len(self.picker.picked), m=self.picker.limit))
        if self.want is not None:
            lo, hi = self.want
            p.setPen(QColor(WIN_C) if good else QColor("#FFB16B"))
            p.setFont(font(10, QFont.Weight.DemiBold))
            top = r.adjusted(0, 0, -S(10), -(S(16) if self.other else 0))
            p.drawText(top, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                       tr("Needs {a} to {b}", a=coins_text(lo), b=coins_text(hi)))
        if self.other:                                    # 4.6: your chance, as it would be with these items
            c = t / (t + self.other) if t else 0.0
            c = min(0.51, max(0.49, c)) if t and self.want and self.want[0] <= t <= self.want[1] else c
            bar = QRectF(r.left() + S(10), r.bottom() - S(12), r.width() - S(20), S(5))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha("#FFFFFF", 0.08))
            p.drawRoundedRect(bar, S(2.5), S(2.5))
            p.setBrush(QColor(ui.accent))
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * c, bar.height()), S(2.5), S(2.5))
            p.setPen(QColor(TEXT))
            p.setFont(font(9.5, QFont.Weight.Bold))
            p.drawText(QRectF(r.left(), r.bottom() - S(30), r.width() - S(10), S(16)),
                       int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), tr("Your chance {p}", p=pct(c)))


# ================================================================ a coinflip in the lobby
class FlipRow(QWidget):
    """One coinflip of the lobby: who, which side, the items and their worth, time left, Join."""

    def __init__(self, page, f: dict) -> None:
        super().__init__()
        self.page, self.f = page, f
        self.setFixedHeight(S(76))
        self._t0 = time.monotonic()
        lay = hbox(self, 6)
        lay.setContentsMargins(0, 0, S(8), 0)
        lay.addStretch(1)
        state = f.get("state")
        if f.get("mine") or f.get("joiner"):
            b = Button(tr("Open"), "primary", 30)
            b.clicked.connect(lambda: open_flip(page, f["id"]))
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignBottom)
        elif state == "open":
            b = Button(tr("Join"), "primary", 30)
            b.clicked.connect(lambda: join_flip(page, f))
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignBottom)
        elif state in ("locked", "done"):                  # 4.2: the eye: watch it flip
            b = IconButton("eye", 32, tip=tr("Watch"))
            b.clicked.connect(lambda: open_flip(page, f["id"]))
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignBottom)
        lay.setContentsMargins(0, 0, S(8), S(8))
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self.update)
        self._tick.start()

    def paintEvent(self, _e) -> None:
        from .collection import show_item
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = self.f
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha(ui.accent, 0.55), 1.2) if (f.get("mine") or f.get("joiner")) else Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.05))
        p.drawRoundedRect(r, S(11), S(11))
        from .games3 import paint_flip_coin
        paint_flip_coin(p, QPointF(r.left() + S(24), r.top() + S(24)), S(12), 0.0, f.get("a_side", "black"))
        p.setPen(QColor(TEXT))
        p.setFont(font(12, QFont.Weight.Bold))
        name = str(f.get("a") or "?")
        p.drawText(QRectF(r.left() + S(44), r.top() + S(8), r.width() * 0.5, S(18)), int(Qt.AlignmentFlag.AlignVCenter), name)
        if f.get("a_bot"):                                # a bot (or an offer made by Rubenium): always marked
            tx = r.left() + S(50) + p.fontMetrics().horizontalAdvance(name)
            label = tr("BOT")                         # 4.6: Rubenium's own offers look like any bot
            p.setFont(font(8.5, QFont.Weight.Black, 0.6))
            tw = p.fontMetrics().horizontalAdvance(label) + S(10)
            chip = QRectF(tx, r.top() + S(9), tw, S(16))
            col = QColor("#9AA4AD")
            p.setPen(QPen(col, 1))
            p.setBrush(alpha(col, 0.15))
            p.drawRoundedRect(chip, S(8), S(8))
            p.setPen(col)
            p.drawText(chip, int(Qt.AlignmentFlag.AlignCenter), label)
        p.setPen(QColor(GOLD_TEXT))
        p.setFont(font(11.5, QFont.Weight.ExtraBold))
        p.drawText(QRectF(r.left(), r.top() + S(8), r.width() - S(12), S(18)),
                   int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), coins_text(int(f.get("a_value") or 0)))
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(9.5, QFont.Weight.DemiBold))
        state = f.get("state")
        left = int(f.get("expires") or 0) - int(time.monotonic() - self._t0)
        sub = {"open": tr("Waiting · {t}", t=f"{max(0, left) // 60}:{max(0, left) % 60:02d}"),
               "setup": tr("Choosing items"),
               "joined": tr("{name} is choosing", name=show_name(f, "b")),
               "locked": bot_phase_text(f, time.monotonic() - self._t0) or tr("Locked in: flipping soon"),
               "done": tr("{name} won", name=f.get("winner") or "?")}.get(state, "")
        p.drawText(QRectF(r.left() + S(44), r.top() + S(26), r.width() * 0.6, S(14)), int(Qt.AlignmentFlag.AlignVCenter), sub)
        x = r.left() + S(10)
        for it in (f.get("a_items") or [])[:6]:
            show_item(p, it.get("item", ""), QRectF(x, r.bottom() - S(30), S(24), S(24)), 0, effects=False)
            x += S(28)


# ================================================================ the coin
class FlipStage(QWidget):
    """The two sides, the pot, the countdown and the coin itself (it spins, slows down and lands)."""

    def __init__(self, page) -> None:
        super().__init__()
        self.page, self.ctx = page, page.ctx
        self.f: dict = {}
        self.setFixedSize(page.W, S(250))
        self._spin_t = 0.0
        self._landed = None
        self._shown_result = None
        self._t = QTimer(self)
        self._t.setTimerType(Qt.TimerType.PreciseTimer)
        self._t.setInterval(16)
        self._t.timeout.connect(self.update)
        self._sync_t = time.monotonic()
        self._confetti: list = []
        self._item_rects: list = []                       # 4.6: (rect, item dict) of the items shown: click one to see it
        self.setMouseTracking(True)

    def _item_at(self, pos):
        return next(((rc, it) for rc, it in self._item_rects if rc.contains(pos)), None)

    def mouseMoveEvent(self, e) -> None:
        self.setCursor(Qt.CursorShape.PointingHandCursor if self._item_at(e.position()) else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, e) -> None:
        hit = self._item_at(e.position())
        if hit is not None:
            from .bazaar import show_item_tip
            rc, it = hit
            w = it.get("worth")
            show_item_tip(self.ctx, self, rc, it.get("item", ""), int(w) if w is not None else None)

    def showEvent(self, _e) -> None:
        self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()

    def set_state(self, f: dict) -> None:
        old = self.f
        self.f = f
        self._sync_t = time.monotonic()
        if f.get("state") == "done" and f.get("result") and self._shown_result is None:
            self._shown_result = f["result"]
            self._spin_t = time.monotonic()               # the coin starts to spin now and lands on the result
            sfx.play("on")
            self.ctx.notifier.hold(self.SPIN_S + 1.5)     # 4.6: no pop-up telling the result before the coin lands
        elif f.get("state") == "locked" and old.get("state") != "locked":
            sfx.play("pick")
        self.update()

    SPIN_S = 3.2

    def _phase_sound(self, found_left: float, join_left: float, count_left: float, f: dict) -> None:
        """A sound when the bot is found, when it joins, and on each number of the 3-2-1."""
        if not f.get("vs_bot") or f.get("state") != "locked":
            return
        phase = ("search" if found_left > 0 else "choose" if join_left > 0 else
                 f"count{math.ceil(count_left)}" if count_left > 0 else "flip")
        last = getattr(self, "_last_phase", None)
        if phase != last:
            self._last_phase = phase
            if last is not None:
                sfx.play("on" if phase == "choose" else "pick")

    def coin_angle(self, now: float) -> float:
        if self._shown_result is None:
            if self.f.get("state") == "locked":
                return now * 1.6                          # waiting: the coin turns slowly
            return 0.0
        k = min(1.0, (now - self._spin_t) / self.SPIN_S)
        end = 2 * math.pi * 9 + (0.0 if self._shown_result == "black" else math.pi)
        e = 1 - (1 - k) ** 4
        if k >= 1.0 and self._landed is None:
            self._landed = now
            won = bool(self.f.get("won"))
            mine = self.f.get("mine") or self.f.get("joiner")
            sfx.play("on" if (won or not mine) else "off")
            if won:
                rnd = random.Random()
                self._confetti = [(rnd.uniform(0, 1), rnd.uniform(0, 1), rnd.uniform(0, math.tau), rnd.random())
                                  for _ in range(60)]
                from .onlinewin import shake
                shake(self.ctx.window, 4.0, 300)
        return end * e

    def paintEvent(self, _e) -> None:
        from .collection import show_item
        from .games3 import paint_flip_coin
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f, now = self.f, time.monotonic()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor("#0D1214"))
        g.setColorAt(1, QColor("#080B0C"))
        p.setPen(QPen(alpha("#FFFFFF", 0.08), 1))
        p.setBrush(g)
        p.drawRoundedRect(r, S(14), S(14))
        if not f:
            return
        state = f.get("state")
        landed = self._landed is not None
        winner_side = self._shown_result if landed else None
        elapsed = now - self._sync_t
        found_left, join_left, count_left = bot_phases(f, elapsed)
        searching = found_left > 0 or (join_left > 0 and not f.get("b") and f.get("vs_bot"))
        self._phase_sound(found_left, join_left, count_left, f)
        self._item_rects = []
        # the two players
        for i, who in enumerate(("a", "b")):
            box = QRectF(r.left() + S(10) if i == 0 else r.right() - S(10) - r.width() * 0.3, r.top() + S(10),
                         r.width() * 0.3, S(150))
            side = f.get(who + "_side", "black")
            win = landed and winner_side == side
            p.setPen(QPen(QColor(WIN_C), S(2)) if win else QPen(alpha("#FFFFFF", 0.08), 1))
            p.setBrush(alpha(WIN_C, 0.10) if win else alpha("#FFFFFF", 0.03))
            p.drawRoundedRect(box, S(11), S(11))
            paint_flip_coin(p, QPointF(box.left() + S(16), box.top() + S(16)), S(9), 0, side)
            name = show_name(f, who) if f.get(who) else (tr("Waiting…") if who == "b" else "?")
            if who == "b" and searching:                 # 4.2: a bot is being searched: a spinner in its seat
                name = tr("Searching…")
                c0 = QPointF(box.center().x(), box.top() + S(70))
                for k in range(8):
                    a = now * 5 + k * math.tau / 8
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(alpha(TEXT, 0.15 + 0.85 * ((k / 8 + now * 0.8) % 1.0)))
                    p.drawEllipse(QPointF(c0.x() + math.cos(a) * S(14), c0.y() + math.sin(a) * S(14)), S(2.6), S(2.6))
            elif who == "b" and f.get("vs_bot") and join_left > 0:      # found: it is picking its items
                p.setPen(QColor(TEXT_DIM))
                p.setFont(font(10, QFont.Weight.DemiBold))
                dots = "." * (1 + int(now * 2.5) % 3)
                p.drawText(QRectF(box.left(), box.top() + S(56), box.width(), S(30)), int(Qt.AlignmentFlag.AlignCenter),
                           tr("Choosing") + dots)
            p.setPen(QColor(TEXT))
            p.setFont(font(11, QFont.Weight.Bold))
            p.drawText(QRectF(box.left() + S(30), box.top() + S(6), box.width() - S(34), S(20)), int(Qt.AlignmentFlag.AlignVCenter),
                       QFontMetrics(p.font()).elidedText(str(name), Qt.TextElideMode.ElideRight, int(box.width() - S(34))))
            items = f.get(who + "_items") or []
            for k, it in enumerate(items[:6]):
                cell = QRectF(box.left() + S(8) + (k % 3) * (box.width() - S(16)) / 3, box.top() + S(32) + (k // 3) * S(40),
                              (box.width() - S(16)) / 3, S(36))
                d = min(cell.width(), cell.height()) * 0.8
                show_item(p, it.get("item", ""), QRectF(cell.center().x() - d / 2, cell.center().y() - d / 2, d, d), now,
                          effects=False)
                self._item_rects.append((cell, it))
            val = int(f.get(who + "_value") or 0)
            p.setPen(QColor(GOLD_TEXT))
            p.setFont(font(11, QFont.Weight.ExtraBold))
            p.drawText(QRectF(box.left(), box.bottom() - S(42), box.width(), S(18)), int(Qt.AlignmentFlag.AlignCenter),
                       coins_text(val) if val else "—")
            ch = f.get("chance_a")
            if ch is not None:
                c = float(ch) if who == "a" else 1 - float(ch)
                p.setPen(QColor(TEXT_DIM))
                p.setFont(font(10, QFont.Weight.DemiBold))
                p.drawText(QRectF(box.left(), box.bottom() - S(22), box.width(), S(16)), int(Qt.AlignmentFlag.AlignCenter),
                           tr("{p} chance", p=pct(c)))
        # the coin in the middle
        c = QPointF(r.center().x(), r.top() + S(85))
        ang = self.coin_angle(now)
        spinning = self._shown_result is not None and not landed
        lift = math.sin(min(1.0, (now - self._spin_t) / self.SPIN_S) * math.pi) * S(34) if spinning else 0.0
        glow = QRadialGradient(c, S(70))
        glow.setColorAt(0, alpha(ui.accent, 0.25 if spinning else 0.12))
        glow.setColorAt(1, alpha(ui.accent, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, S(70), S(70))
        if landed:
            paint_flip_coin(p, QPointF(c.x(), c.y()), S(38), 0, winner_side)
        else:
            paint_flip_coin(p, QPointF(c.x(), c.y() - lift), S(38) * (1 + lift / S(200)), ang, None)
        # what is happening, below the coin
        p.setFont(font(12.5, QFont.Weight.ExtraBold))
        line = QRectF(r.left(), r.top() + S(135), r.width(), S(22))
        if state == "locked" and (searching or join_left > 0):
            p.setPen(QColor("#FFB16B"))
            p.drawText(line, int(Qt.AlignmentFlag.AlignCenter), bot_phase_text(f, elapsed))
        elif state == "locked" and count_left > 0:          # 4.2: the bot joined: 3, 2, 1
            k = count_left - math.floor(count_left)
            p.setPen(QColor(ui.accent))
            p.setFont(font(26 + 10 * k, QFont.Weight.Black))
            p.drawText(QRectF(line.left(), line.top() - S(10), line.width(), S(42)), int(Qt.AlignmentFlag.AlignCenter),
                       str(math.ceil(count_left)))
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(10, QFont.Weight.DemiBold))
            p.drawText(QRectF(r.left(), line.bottom() + S(12), r.width(), S(16)), int(Qt.AlignmentFlag.AlignCenter),
                       bot_phase_text(f, elapsed))
        elif state == "open":
            p.setPen(QColor(TEXT_DIM))
            p.drawText(line, int(Qt.AlignmentFlag.AlignCenter), tr("Waiting for a player"))
        elif state == "joined":
            left = max(0, int(f.get("pick_left") or 0) - int(elapsed))
            p.setPen(QColor("#FFB16B"))
            p.drawText(line, int(Qt.AlignmentFlag.AlignCenter), tr("Choosing items · {s} s", s=left))
        elif state == "locked" or (state == "done" and not landed):
            left = max(0.0, float(f.get("flip_in") or 0) - elapsed)
            p.setPen(QColor(TEXT))
            if state == "locked" and left > 0.05:
                p.setFont(font(22, QFont.Weight.Black))
                p.drawText(QRectF(line.left(), line.top() - S(4), line.width(), S(30)), int(Qt.AlignmentFlag.AlignCenter),
                           f"{math.ceil(left)}")
            else:
                p.drawText(line, int(Qt.AlignmentFlag.AlignCenter), tr("Flipping…"))
        elif state == "done":
            won = f.get("won")
            mine = f.get("mine") or f.get("joiner")
            p.setPen(QColor(WIN_C) if won else (QColor(LOSE_C) if mine else QColor(TEXT)))
            text = (tr("You win {n}!", n=coins_text(int(f.get("a_value") or 0) + int(f.get("b_value") or 0))) if won else
                    tr("{name} wins", name=f.get("winner") or "?"))
            p.drawText(line, int(Qt.AlignmentFlag.AlignCenter), text)
            p.setFont(font(10, QFont.Weight.DemiBold))
            p.setPen(QColor(TEXT_DIM))
            p.drawText(QRectF(r.left(), line.bottom() + S(2), r.width(), S(16)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("The coin landed on {side}", side=side_name(winner_side or "black")))
        elif state == "cancelled":
            p.setPen(QColor(TEXT_DIM))
            p.drawText(line, int(Qt.AlignmentFlag.AlignCenter), tr("Closed: the items went back"))
        # 4.6: the chances, as one bar split between the two sides
        ch = f.get("chance_a")
        bar = QRectF(r.left() + S(16), r.bottom() - S(24), r.width() - S(32), S(10))
        if ch is not None:
            ca = float(ch)
            cols = {"black": QColor("#2A3136"), "white": QColor("#E6ECEF")}
            a_col = cols.get(f.get("a_side", "black"), cols["black"])
            b_col = cols.get(f.get("b_side", "white"), cols["white"])
            split = bar.left() + bar.width() * ca
            path = QPainterPath()
            path.addRoundedRect(bar, S(5), S(5))
            p.save()
            p.setClipPath(path)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(a_col)
            p.drawRect(QRectF(bar.left(), bar.top(), split - bar.left(), bar.height()))
            p.setBrush(b_col)
            p.drawRect(QRectF(split, bar.top(), bar.right() - split, bar.height()))
            p.restore()
            p.setPen(QPen(alpha("#FFFFFF", 0.35), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(bar, S(5), S(5))
            p.setPen(QPen(QColor(ui.accent), S(2)))
            p.drawLine(QPointF(split, bar.top() - S(3)), QPointF(split, bar.bottom() + S(3)))
            p.setFont(font(12, QFont.Weight.Black))
            lab = QRectF(bar.left(), bar.top() - S(20), bar.width(), S(17))
            for who, c, al in (("a", ca, Qt.AlignmentFlag.AlignLeft), ("b", 1 - ca, Qt.AlignmentFlag.AlignRight)):
                me = (who == "a" and f.get("mine")) or (who == "b" and f.get("joiner"))
                win = landed and winner_side == f.get(who + "_side")
                p.setPen(QColor(WIN_C) if win else QColor(ui.accent) if me else QColor(TEXT))
                p.drawText(lab, int(al | Qt.AlignmentFlag.AlignVCenter), (tr("You") + " " if me else "") + pct(c))
        elif state in ("open", "joined", "setup"):
            p.setPen(QPen(alpha("#FFFFFF", 0.12), 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(bar, S(5), S(5))
            p.setPen(QColor(TEXT_FAINT))
            p.setFont(font(9.5, QFont.Weight.DemiBold))
            p.drawText(QRectF(bar.left(), bar.top() - S(20), bar.width(), S(17)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("Chances show once both sides are in"))
        # confetti for the winner
        if self._confetti and self._landed is not None:
            age = now - self._landed
            for x0, y0, rot, hue in self._confetti:
                y = r.top() + (y0 * 0.4 + age * 0.45) % 1.0 * r.height()
                x = r.left() + x0 * r.width() + math.sin(age * 3 + rot) * S(8)
                p.save()
                p.translate(x, y)
                p.rotate(age * 220 + rot * 57)
                p.setBrush(QColor.fromHsvF(hue, 0.6, 1.0))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRect(QRectF(-S(3), -S(1.3), S(6), S(2.6)))
                p.restore()
            if age > 4:
                self._confetti = []


# ================================================================ talking to the server
VOLATILE = ("expires", "pick_left", "flip_in")


def flips_sig(data) -> str:
    """What matters for the page (who, what, which state): the seconds counting down are left out, so the lobby is
    not rebuilt every two seconds."""
    import json as _json
    if not isinstance(data, dict):
        return ""
    flips = [{k: v for k, v in f.items() if k not in VOLATILE} for f in (data.get("flips") or [])]
    return _json.dumps([flips, data.get("history"), data.get("mine"), data.get("locked")], sort_keys=True, default=str)


def show_name(f: dict, side: str) -> str:
    """A player's name, or a bot's with BOT after it (bots never look like players)."""
    name = str(f.get(side) or "?")
    if f.get(side + "_bot"):
        return name + " · " + tr("BOT")
    return name


def bot_phases(f: dict, elapsed: float) -> tuple:
    """4.2 VS bot: seconds left searching, choosing, and in the 3-2-1 (all 0 once the 15 second count runs)."""
    if not f.get("vs_bot") or f.get("state") != "locked":
        return 0.0, 0.0, 0.0
    return tuple(max(0.0, float(f.get(k) or 0) - elapsed) for k in ("found_in", "join_in", "count_in"))


def bot_phase_text(f: dict, elapsed: float) -> str:
    found, join, count = bot_phases(f, elapsed)
    if found > 0 or (join > 0 and not f.get("b")):
        return tr("Searching for a bot…")
    if join > 0:
        return tr("{name} is choosing items…", name=show_name(f, "b"))
    if count > 0:
        return tr("{name} joined", name=show_name(f, "b"))
    return ""


def load_flips(page) -> None:
    ctx = page.ctx

    def got(ok: bool, data) -> None:
        if not ok or not isinstance(data, dict):
            if not ok and "soon" in str(data).lower():
                ctx.flip_missing = True
            return
        ctx.flip_missing = False
        mine = data.get("mine")
        if mine and not getattr(ctx, "flip_id", None):
            ctx.flip_id = mine                         # you are in one: it opens
        old = getattr(ctx, "flip_data", None)
        if flips_sig(data) != flips_sig(old):
            ctx.flip_data = data
            if ctx.window.showing("games") and getattr(ctx, "games_sub", None) == "flip" and not getattr(ctx, "flip_id", None):
                ctx.reload_page("games")
            elif mine and (old is None or old.get("mine") != mine) and ctx.window.showing("games") \
                    and getattr(ctx, "games_sub", None) == "flip":
                ctx.reload_page("games")
    ctx.online.ask("rb_flip_list", {}, got)


def open_flip(page, fid: str) -> None:
    page.ctx.flip_id = fid
    sfx.play("pick")
    page.ctx.reload_page("games")


def join_flip(page, f: dict) -> None:
    """4.2: joining only opens your items: you are in once you lock in (first to lock in gets the seat)."""
    ctx = page.ctx

    def done(ok: bool, data) -> None:
        if not ok:
            ctx.flip_data = None
            load_flips(page)
            return ctx.toast(tr(str(data)), "warn")
        sfx.play("pick")
        ctx.flip_id = f["id"]
        ctx.flip_joining = f["id"]
        ctx.flip_state = data
        ctx.reload_page("games")
    ctx.econ.call("rb_flip_join", {"fid": f["id"]}, done)


def leave_view(ctx) -> None:
    ctx.flip_id = None
    ctx.flip_joining = None
    ctx.flip_data = None
    ctx.reload_page("games")


class _Poll(QWidget):
    def __init__(self, ms: int, fn) -> None:
        super().__init__()
        self.setFixedHeight(0)
        self.fn = fn
        self._t = QTimer(self)
        self._t.setInterval(ms)
        self._t.timeout.connect(fn)

    def showEvent(self, _e) -> None:
        self.fn()
        self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()


def build_flip(page, lay) -> None:
    from .hub import server_wait
    from .shop import CoinBar
    ctx = page.ctx
    top = hbox(spacing=8)
    back = IconButton("back", 32, tip=tr("Back"))
    fid = getattr(ctx, "flip_id", None)

    def leave() -> None:
        if fid:
            return leave_view(ctx)
        page.open_sub(None)
    back.clicked.connect(leave)
    top.addWidget(back)
    top.addWidget(Label(tr("Coinflip"), 16, bold=True), 1)
    from .gamehelp import HelpButton
    top.addWidget(HelpButton(ctx, "coinflip"))
    duel = Label(tr("DUEL"), 10, "#3DDC84", bold=True)
    duel.fit()
    top.addWidget(duel)
    lay.addLayout(top)
    if server_wait(ctx, lay, page.W) or getattr(ctx, "flip_missing", False):
        return
    if fid:
        return _build_view(page, lay, fid)
    lay.addWidget(_Poll(2000, lambda: load_flips(page)))
    data = getattr(ctx, "flip_data", None)
    if data is None:
        lay.addWidget(Label(tr("Loading…"), 11, TEXT_DIM))
        return
    limit = int(data.get("max_items") or 6)
    rng = float(data.get("range") or 0.1)
    lay.addWidget(Label(tr("CREATE A COINFLIP"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
    row = hbox(spacing=6)
    side = Segmented([tr("Black"), tr("White")], int(getattr(ctx, "flip_side", 0) or 0))
    side.changed.connect(lambda i: setattr(ctx, "flip_side", i))
    row.addWidget(side, 1)
    make = Button(tr("Create"), "primary", 34, icon="coin")
    make.setFixedWidth(max(S(110), make.sizeHint().width()))

    def create() -> None:
        def done(ok: bool, d) -> None:
            if not ok:
                return ctx.toast(tr(str(d)), "warn")
            sfx.play("on")
            ctx.flip_id = d.get("id")
            ctx.flip_state = d
            ctx.reload_page("games")
        ctx.econ.call("rb_flip_create", {"side": "black" if side.index() == 0 else "white", "items": None}, done)
    make.clicked.connect(create)
    row.addWidget(make)
    lay.addLayout(row)
    lay.addWidget(Label(tr("Up to {n} items, same worth on both sides (±{r}%). Your chance is your share of the pot. "
                           "The winner takes everything.", n=limit, r=int(round(rng * 100))), 10, TEXT_DIM, wrap_w=page.W))
    flips = [f for f in (data.get("flips") or []) if not f.get("mine")]
    lay.addWidget(Label(tr("OPEN COINFLIPS"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
    if not any(f.get("state") == "open" for f in flips):
        lay.addWidget(Label(tr("No open coinflip right now. Open one!"), 11, TEXT_DIM, wrap_w=page.W))
    for f in flips[:14]:
        lay.addWidget(FlipRow(page, f))
    hist = list(data.get("history") or [])
    if hist:
        lay.addWidget(Label(tr("YOUR LAST COINFLIPS"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
        for h in hist[:6]:
            text = (tr("Won {n} against {name}", n=coins_text(int(h.get("value") or 0)), name=h.get("other") or "?") if h.get("won")
                    else tr("Lost against {name}", name=h.get("other") or "?"))
            lay.addWidget(Label(text, 11, WIN_C if h.get("won") else TEXT_DIM))


def _build_view(page, lay, fid: str) -> None:
    ctx = page.ctx
    stage = FlipStage(page)
    lay.addWidget(stage)
    first = getattr(ctx, "flip_state", None)
    if isinstance(first, dict) and first.get("id") == fid:
        stage.set_state(first)
    holder = {"picker": None, "bar": None, "lock": None, "state": (first or {}).get("state")}
    area = QWidget()
    from .widgets import vbox
    al = vbox(area, 8)
    lay.addWidget(area)

    def build_controls(f: dict) -> None:
        """The buttons under the coin change with the state: picking items, waiting, or done."""
        while al.count():
            item = al.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        holder["picker"] = holder["bar"] = None
        state = f.get("state")
        if state == "setup" and f.get("mine"):           # 4.0: your lobby: now put in your items
            limit = int((getattr(ctx, "flip_data", None) or {}).get("max_items") or 6)
            al.addWidget(Label(tr("Put in 1 to {n} items, then confirm. Nobody sees your lobby until you confirm.", n=limit),
                               11, TEXT, wrap_w=page.W))
            picker = ItemPicker(page, limit)
            bar = TotalBar(picker)
            al.addWidget(bar)
            al.addWidget(picker)
            row = hbox(spacing=6)
            ok_btn = Button(tr("Confirm items"), "primary", 38)

            def confirm() -> None:
                if not picker.picked:
                    return ctx.toast(tr("Pick 1 to {n} items first", n=limit), "warn")

                def done(ok: bool, d) -> None:
                    if not ok:
                        return ctx.toast(tr(str(d)), "warn")
                    sfx.play("on")
                    ctx.econ.refresh()
                    apply(d)
                ctx.econ.call("rb_flip_put", {"fid": fid, "items": picker.ids()}, done)
            ok_btn.clicked.connect(confirm)
            close = Button(tr("Cancel"), "ghost", 38)
            close.clicked.connect(lambda: ctx.econ.call("rb_flip_cancel", {"fid": fid}, lambda ok, d: (
                setattr(ctx, "flip_id", None), setattr(ctx, "flip_data", None), ctx.reload_page("games"))))
            row.addWidget(ok_btn, 2)
            row.addWidget(close, 1)
            al.addLayout(row)
            holder["picker"], holder["bar"] = picker, bar
        elif (state == "open" and not f.get("mine") and getattr(ctx, "flip_joining", None) == fid) or \
                (state == "joined" and f.get("joiner")):
            limit = int((getattr(ctx, "flip_data", None) or {}).get("max_items") or 6)
            al.addWidget(Label(tr("Put in items worth {a} to {b}, then lock in. You are in once you lock in.",
                                  a=coins_text(int(f.get("min") or 0)), b=coins_text(int(f.get("max") or 0))),
                               11, TEXT, wrap_w=page.W))
            picker = ItemPicker(page, limit, (int(f.get("min") or 0), int(f.get("max") or 0)))
            bar = TotalBar(picker, picker.want, int(f.get("a_value") or 0))
            al.addWidget(bar)
            al.addWidget(picker)
            row = hbox(spacing=6)
            lock = Button(tr("Lock in"), "primary", 38)
            lock.clicked.connect(lambda: lock_in(f, picker, bar))
            walk = Button(tr("Leave"), "ghost", 38)
            if state == "joined":
                walk.clicked.connect(lambda: ctx.econ.call("rb_flip_leave", {"fid": fid}, lambda ok, d: leave_view(ctx)))
            else:
                walk.clicked.connect(lambda: leave_view(ctx))
            row.addWidget(lock, 2)
            row.addWidget(walk, 1)
            al.addLayout(row)
            holder["picker"], holder["bar"] = picker, bar
        elif state == "open" and f.get("mine"):
            bot = Button(tr("Play a bot"), "primary", 38, icon="robot")

            def vs_bot() -> None:
                def done(ok: bool, d) -> None:
                    if not ok:
                        return ctx.toast(tr(str(d)), "warn")
                    sfx.play("pick")
                    apply(d)
                ctx.econ.call("rb_flip_vs_bot", {"fid": fid}, done)
            bot.clicked.connect(vs_bot)
            al.addWidget(bot)
            close = Button(tr("Close it (items come back)"), "ghost", 34)

            def do_close() -> None:
                def done(ok: bool, d) -> None:
                    if not ok:
                        return ctx.toast(tr(str(d)), "warn")
                    sfx.play("off")
                    ctx.econ.refresh()
                    ctx.flip_id = None
                    ctx.flip_data = None
                    ctx.reload_page("games")
                ctx.econ.call("rb_flip_cancel", {"fid": fid}, done)
            close.clicked.connect(do_close)
            al.addWidget(close)
            al.addWidget(Label(tr("Waiting for a player, or play a bot now. Once someone is in, it cannot be cancelled."),
                               10.5, TEXT_DIM, wrap_w=page.W))
        elif state == "joined":
            al.addWidget(Label(tr("{name} joined and is choosing items.", name=show_name(f, "b")), 11, TEXT, wrap_w=page.W))
        elif state == "locked" and f.get("vs_bot") and f.get("mine"):
            al.addWidget(Label(tr("A bot is joining your coinflip. It cannot be cancelled now."), 10.5, TEXT_DIM,
                               wrap_w=page.W))
        elif state == "locked":
            al.addWidget(Label(tr("Both sides are locked in. Nothing can stop it now: the coin flips when the count ends."),
                               10.5, TEXT_DIM, wrap_w=page.W))
        elif state in ("done", "cancelled"):
            again = Button(tr("Back to the lobby"), "primary", 36)
            again.clicked.connect(lambda: leave_view(ctx))
            al.addWidget(again)

    def lock_in(f: dict, picker, bar) -> None:
        if not bar.ok():
            return ctx.toast(tr("Your items must be worth {a} to {b}", a=coins_text(int(f.get("min") or 0)),
                                b=coins_text(int(f.get("max") or 0))), "warn")

        def done(ok: bool, d) -> None:
            if not ok:
                if "rb_flip_taken" in str(d) or "first" in str(d).lower():
                    return kicked()
                return ctx.toast(tr(str(d)), "warn")
            sfx.play("on")
            ctx.flip_joining = None
            ctx.econ.refresh()
            apply(d)
        ctx.econ.call("rb_flip_lock", {"fid": fid, "items": picker.ids()}, done)

    def kicked() -> None:
        """Someone else locked in first: you were never in, nothing of yours moved."""
        sfx.play("off")
        ctx.toast(tr("Someone else locked in first. Nothing of yours was taken."), "warn")
        ctx.econ.refresh()
        leave_view(ctx)

    def apply(f: dict) -> None:
        try:
            new, old = f.get("state"), holder["state"]
            if getattr(ctx, "flip_joining", None) == fid and new != "open" and not f.get("joiner"):
                return kicked()
            if new != old and not (old == "locked" and new == "done"):
                ctx.flip_state = f                     # another state: the page is built again for it
                return ctx.reload_page("games")
            stage.set_state(f)
            if new != old or not al.count():
                holder["state"] = new
                build_controls(f)
                if new == "done":
                    QTimer.singleShot(int(FlipStage.SPIN_S * 1000) + 200, ctx.econ.refresh)
        except RuntimeError:
            pass

    def poll() -> None:
        def got(ok: bool, d) -> None:
            if ok and isinstance(d, dict):
                apply(d)
            elif not ok and "over" in str(d).lower():
                leave_view(ctx)
        ctx.online.ask("rb_flip_state", {"fid": fid}, got)
    lay.addWidget(_Poll(900, poll))
    if isinstance(first, dict) and first.get("id") == fid:
        build_controls(first)
        holder["state"] = first.get("state")
