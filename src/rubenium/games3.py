"""3.2: two new casino games (Roulette and Hi-Lo) and the DUEL tiles of the lobby (Mini Golf and Coinflip)."""
import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from .core import S, sfx, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, lang, mix, tr, ui
from .games import LOSE, WIN, Game, ease_out
from .shop import GOLD_TEXT
from .wallet import coins_text, paint_coin
from .widgets import Tween

RNG = random.SystemRandom()


# --------------------------------------------------------------------------- #
# Roulette: 25 pockets on a strip. Red or black pays x2, the gold pocket x24.
# --------------------------------------------------------------------------- #
POCKET = {"red": "#E8384F", "black": "#1E2429", "gold": "#E8C26A"}


def pocket_colour(slot: int) -> str:
    return "gold" if slot == 0 else ("red" if slot % 2 else "black")


class Roulette(Game):
    """Pick a colour, the strip spins and stops on a pocket. 12 red and 12 black (x2), 1 gold (x24): 96% back."""
    PICKS = ["red", "black", "gold"]
    MULT = {"red": 2, "black": 2, "gold": 24}
    CELL = 46

    def __init__(self, page) -> None:
        super().__init__(page)
        self.choice = 0
        self.history: list = []
        self.slot = 0
        self.offset = 0.0
        self._from = self._to = 0.0
        self._t0 = 0.0
        self.won = None
        self.order = [(k * 7) % 25 for k in range(25)]            # the pockets around the wheel, mixed

    def options(self):
        return [tr("Red ×2"), tr("Black ×2"), tr("Gold ×24")], self.choice

    def set_option(self, i: int) -> None:
        if not self.busy:
            self.choice = i
            self.update()

    def pick(self) -> str:
        return self.PICKS[self.choice]

    def play(self) -> None:
        if self.busy or self.waiting or not self.take():
            return
        self.won = None
        self.ask("rb_roulette", {"bet": self.stake, "pick": self.pick()}, self._rolled, once=True, refund=self.stake)

    def _rolled(self, ans: dict) -> None:
        self.slot = int(ans.get("slot", 0))
        self._paid = int(ans.get("paid", 0))
        self._win = bool(ans.get("win"))
        idx = self.order.index(self.slot)
        laps = 4
        self._from = self.offset % (25 * self.CELL)
        self._to = (laps * 25 + idx) * self.CELL + RNG.uniform(-0.32, 0.32) * self.CELL
        self._t0 = time.monotonic()
        self._last_cell = -1
        self.animate(5.0)
        QTimer.singleShot(4300, self._done)

    def _done(self) -> None:
        self.offset = self._to
        self.won = self._win
        self.history.insert(0, pocket_colour(self.slot))
        del self.history[14:]
        self.finish(self._paid)

    def buttons(self) -> list:
        return [(tr("Spin"), "primary", self.play, not self.busy)]

    def draw(self, p: QPainter, r: QRectF, now: float) -> None:
        cell = S(self.CELL)
        if self._t0 and now - self._t0 < 4.3:
            t = ease_out((now - self._t0) / 4.2, 4)
            self.offset = self._from + (self._to - self._from) * t
            cur = int(self.offset // self.CELL)
            if cur != getattr(self, "_last_cell", -1):
                self._last_cell = cur
                sfx.play("pick")
        strip = QRectF(r.left(), r.top() + S(58), r.width(), S(70))
        cx = strip.center().x()
        off = self.offset / self.CELL * cell
        first = int((off - cx) // cell) - 1
        for k in range(first, first + int(r.width() // cell) + 4):
            slot = self.order[k % 25]
            col = POCKET[pocket_colour(slot)]
            x = cx - off + k * cell
            box = QRectF(x - cell / 2 + S(2), strip.top(), cell - S(4), strip.height())
            g = QLinearGradient(box.topLeft(), box.bottomLeft())
            g.setColorAt(0, mix(QColor(col), QColor("#FFFFFF"), 0.18))
            g.setColorAt(1, mix(QColor(col), QColor("#000000"), 0.35))
            p.setPen(QPen(alpha("#FFFFFF", 0.10), 1))
            p.setBrush(g)
            p.drawRoundedRect(box, S(7), S(7))
            p.setPen(QColor("#2A1B04") if slot == 0 else QColor("#FFFFFF"))
            p.setFont(font(13, QFont.Weight.ExtraBold))
            p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), "★" if slot == 0 else str(slot))
        fade = QLinearGradient(strip.topLeft(), strip.topRight())
        for at, a in ((0.0, 245), (0.2, 0), (0.8, 0), (1.0, 245)):
            fade.setColorAt(at, QColor(9, 12, 13, a))
        p.fillRect(strip.adjusted(-1, -1, 1, 1), fade)
        p.setPen(QPen(QColor(GOLD_TEXT), S(2.4)))
        p.drawLine(QPointF(cx, strip.top() - S(8)), QPointF(cx, strip.bottom() + S(8)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(GOLD_TEXT))
        for y, d in ((strip.top() - S(10), 1), (strip.bottom() + S(10), -1)):
            tri = QPainterPath()
            tri.moveTo(cx - S(7), y)
            tri.lineTo(cx + S(7), y)
            tri.lineTo(cx, y + d * S(9))
            tri.closeSubpath()
            p.drawPath(tri)
        # the pick and what it pays
        pick = self.pick()
        bet = self.stake if self.busy else self.page.bet()
        p.setFont(font(12, QFont.Weight.Bold))
        p.setPen(QColor(TEXT))
        title = {"red": tr("Red"), "black": tr("Black"), "gold": tr("Gold")}[pick]
        p.drawText(QRectF(r.left(), r.top() + S(12), r.width(), S(20)), int(Qt.AlignmentFlag.AlignCenter),
                   tr("Your pick: {c}", c=title) + "  ·  " + tr("Win {n}", n=coins_text(bet * self.MULT[pick])))
        p.setFont(font(10, QFont.Weight.DemiBold))
        p.setPen(QColor(TEXT_DIM))
        chance = "1/25 (4%)" if pick == "gold" else "12/25 (48%)"
        p.drawText(QRectF(r.left(), r.top() + S(32), r.width(), S(16)), int(Qt.AlignmentFlag.AlignCenter),
                   tr("Chance {c}", c=chance.replace(".", ",") if lang() == "fr" else chance))
        if self.won is not None and not self.busy:
            col = POCKET[pocket_colour(self.slot)]
            p.setPen(QColor(WIN if self.won else LOSE))
            p.setFont(font(14, QFont.Weight.ExtraBold))
            p.drawText(QRectF(r.left(), strip.bottom() + S(14), r.width(), S(22)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("You win!") if self.won else tr("Not this time"))
            del col
        x = r.left() + S(14)                                    # the last pockets, newest first
        for c in self.history[:13]:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(POCKET[c]))
            p.drawEllipse(QPointF(x + S(8), r.bottom() - S(20)), S(8), S(8))
            if c == "black":
                p.setPen(QPen(alpha("#FFFFFF", 0.3), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(x + S(8), r.bottom() - S(20)), S(8), S(8))
            x += S(22)


# --------------------------------------------------------------------------- #
# Hi-Lo: higher or lower, cash out when you like
# --------------------------------------------------------------------------- #
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
SUITS = "♠♥♦♣"


def card_rank(card: int) -> int:
    return card % 13 + 1


class HiLo(Game):
    """A card is shown. Is the next one higher or the same, or lower or the same? Every right guess multiplies the
    prize; a wrong one loses the bet. Cash out at any time after your first right guess."""

    def __init__(self, page) -> None:
        super().__init__(page)
        self.cards: list = []
        self.mult = 1.0
        self.hits = 0
        self.lost = False
        self._flip_t = 0.0
        self._resumed = False

    def step(self) -> float:
        try:
            return float(self.econ.cfg.get("hilo_step", 0.985) or 0.985)
        except (TypeError, ValueError):
            return 0.985

    def chances(self):
        """(chance higher-or-same, chance lower-or-same) for the card on show."""
        if not self.cards:
            return 0.0, 0.0
        r = card_rank(self.cards[-1])
        return (14 - r) / 13, r / 13

    def next_mult(self, guess: str) -> float:
        hi, lo = self.chances()
        ch = hi if guess == "higher" else lo
        return round(self.mult * self.step() / max(ch, 1e-9), 4)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        if not self.busy and not self._resumed and self.econ.ready:
            self._resumed = True                  # a round left open earlier carries on

            def got(ans: dict) -> None:
                if ans.get("open"):
                    self.cards = list(ans.get("cards") or [])
                    self.mult = float(ans.get("mult") or 1)
                    self.hits = int(ans.get("hits") or 0)
                    self.stake = int(ans.get("bet") or 0)
                    self.busy, self.lost = True, False
                    self.page.sync()
                    self.update()
            self.ask("rb_hilo", {"action": "state", "bet": 0, "req": None}, got)

    def play(self) -> None:
        if self.busy or self.waiting or not self.take():
            return
        self.lost = False
        self.ask("rb_hilo", {"action": "start", "bet": self.stake}, self._started, once=True, refund=self.stake)

    def _started(self, ans: dict) -> None:
        self.cards = list(ans.get("cards") or [])
        self.mult, self.hits = 1.0, 0
        self._flip_t = time.monotonic()
        self.animate(0.6)
        sfx.play("pick")

    def guess(self, which: str) -> None:
        if not self.busy or self.waiting or not self.cards:
            return
        self.ask("rb_hilo", {"action": which, "bet": 0}, self._answered, once=True)

    def _answered(self, ans: dict) -> None:
        self.cards = list(ans.get("cards") or self.cards)
        self._flip_t = time.monotonic()
        self.animate(0.8)
        if not ans.get("right"):
            self.lost = True
            self.mult = 0.0
            QTimer.singleShot(450, lambda: self.finish(0))
            return
        self.mult = float(ans.get("mult") or self.mult)
        self.hits = int(ans.get("hits") or self.hits)
        sfx.play("on")
        if not ans.get("open"):                       # the biggest prize: paid at once
            QTimer.singleShot(450, lambda: self.finish(int(ans.get("paid") or 0)))

    def cash(self) -> None:
        if not self.busy or self.waiting or self.hits < 1:
            return
        self.ask("rb_hilo", {"action": "cash", "bet": 0}, lambda ans: self.finish(int(ans.get("paid") or 0)), once=True)

    def tutorial(self) -> bool:
        return not self.ctx.cfg["hilo_help"]

    def _got_it(self) -> None:
        self.ctx.cfg["hilo_help"] = True
        sfx.play("pick")
        self.page.sync()
        self.update()

    def buttons(self) -> list:
        if self.tutorial():
            return [(tr("Got it"), "primary", self._got_it, True)]
        if not self.busy:
            return [(tr("Deal"), "primary", self.play, True)]
        hi, lo = self.chances()
        cash_txt = tr("Cash out {n}", n=coins_text(int(self.stake * self.mult))) if self.hits else tr("Cash out")
        return [(tr("Higher ×{m}", m=f"{self.next_mult('higher'):.2f}"), "ghost", lambda: self.guess("higher"),
                 not self.waiting and hi > 0),
                (tr("Lower ×{m}", m=f"{self.next_mult('lower'):.2f}"), "ghost", lambda: self.guess("lower"),
                 not self.waiting and lo > 0),
                (cash_txt, "primary", self.cash, not self.waiting and self.hits > 0)]

    def _card(self, p: QPainter, rect: QRectF, card: int, face: bool = True) -> None:
        p.setPen(QPen(alpha("#000000", 0.4), 1))
        if not face:
            g = QLinearGradient(rect.topLeft(), rect.bottomRight())
            g.setColorAt(0, mix(ui.accent, QColor("#000000"), 0.45))
            g.setColorAt(1, mix(ui.accent, QColor("#000000"), 0.75))
            p.setBrush(g)
            p.drawRoundedRect(rect, S(8), S(8))
            p.setPen(QPen(alpha("#FFFFFF", 0.25), S(1.2)))
            p.drawRoundedRect(rect.adjusted(S(5), S(5), -S(5), -S(5)), S(5), S(5))
            return
        p.setBrush(QColor("#F4F5F6"))
        p.drawRoundedRect(rect, S(8), S(8))
        red = (card // 13) in (1, 2)
        p.setPen(QColor("#D8314A") if red else QColor("#14181A"))
        big = rect.height() > S(80)
        p.setFont(font(28 if big else 13, QFont.Weight.ExtraBold))
        p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), RANKS[card % 13])
        p.setFont(font(13 if big else 8, QFont.Weight.Bold))
        p.drawText(rect.adjusted(S(6), S(4), 0, 0), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                   SUITS[card // 13])
        p.drawText(rect.adjusted(0, 0, -S(6), -S(4)), int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom),
                   SUITS[card // 13])

    def draw(self, p: QPainter, r: QRectF, now: float) -> None:
        if self.tutorial():
            p.setPen(QColor(TEXT))
            p.setFont(font(15, QFont.Weight.Bold))
            p.drawText(QRectF(r.left(), r.top() + S(14), r.width(), S(24)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("How to play Hi-Lo"))
            p.setFont(font(11, QFont.Weight.DemiBold))
            p.setPen(QColor(TEXT_DIM))
            lines = [tr("1. Choose your bet and press Deal: a card is shown."),
                     tr("2. Will the next card be higher (or the same), or lower (or the same)?"),
                     tr("3. Every right guess multiplies your prize. The less likely, the bigger."),
                     tr("4. Cash out whenever you like. One wrong guess loses the bet."),
                     tr("A is the lowest card, K the highest.")]
            y = r.top() + S(48)
            for text in lines:
                box = p.fontMetrics().boundingRect(0, 0, int(r.width() - S(36)), 1000, int(Qt.TextFlag.TextWordWrap), text)
                p.drawText(QRectF(r.left() + S(18), y, r.width() - S(36), box.height() + S(2)),
                           int(Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap), text)
                y += box.height() + S(6)
            return
        cw, ch = S(78), S(110)
        c = QPointF(r.center().x(), r.top() + S(18) + ch / 2)
        if not self.cards:
            self._card(p, QRectF(c.x() - cw / 2, c.y() - ch / 2, cw, ch), 0, face=False)
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(11, QFont.Weight.DemiBold))
            p.drawText(QRectF(r.left(), c.y() + ch / 2 + S(10), r.width(), S(18)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("Press Deal to start"))
            return
        k = min(1.0, (now - self._flip_t) / 0.35) if self._flip_t else 1.0
        sx = abs(math.cos(k * math.pi)) if k < 1 else 1.0         # the card turns over
        face = k >= 0.5
        rect = QRectF(c.x() - cw / 2 * sx, c.y() - ch / 2, cw * sx, ch)
        self._card(p, rect, self.cards[-1], face)
        if self.lost and face:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(LOSE, 0.35))
            p.drawRoundedRect(rect, S(8), S(8))
        # the earlier cards, small, on the left
        x = r.left() + S(12)
        for card in self.cards[-6:-1][::-1]:
            self._card(p, QRectF(x, r.top() + S(14), S(28), S(40)), card)
            x += S(32)
        # multiplier and chances
        p.setFont(font(18, QFont.Weight.ExtraBold))
        p.setPen(QColor(LOSE) if self.lost else (QColor(WIN) if self.hits else QColor(TEXT)))
        p.drawText(QRectF(r.right() - S(110), r.top() + S(16), S(100), S(26)), int(Qt.AlignmentFlag.AlignRight),
                   f"×{self.mult:.2f}")
        hi, lo = self.chances()
        p.setFont(font(10, QFont.Weight.DemiBold))
        p.setPen(QColor(TEXT_DIM))
        line = tr("Higher or same {a}%  ·  Lower or same {b}%", a=round(hi * 100), b=round(lo * 100))
        p.drawText(QRectF(r.left(), c.y() + ch / 2 + S(10), r.width(), S(18)), int(Qt.AlignmentFlag.AlignCenter), line)
        if self.busy and self.hits:
            p.setPen(QColor(GOLD_TEXT))
            p.setFont(font(11, QFont.Weight.Bold))
            p.drawText(QRectF(r.left(), c.y() + ch / 2 + S(30), r.width(), S(18)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("{n} right in a row", n=self.hits))


# --------------------------------------------------------------------------- #
# DUEL tiles at the bottom of the lobby: online games against other players
# --------------------------------------------------------------------------- #
class DuelTile(QWidget):
    """Mini Golf or Coinflip: a bigger tile with a DUEL tag (played live against other users)."""

    def __init__(self, page, kind: str) -> None:
        super().__init__()
        self.page, self.kind = page, kind
        self.setFixedHeight(S(84))
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

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.page.open_sub("duels" if self.kind == "golf" else "flip")

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self._hover.level
        now = time.monotonic()
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        col = QColor("#2E9E4F") if self.kind == "golf" else QColor("#C9CED3")
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, mix(QColor("#0C1113"), col, 0.22 + 0.1 * h))
        g.setColorAt(1, QColor("#0A0D0E"))
        p.setPen(QPen(mix(alpha("#FFFFFF", 0.10), ui.accent, 0.3 + 0.6 * h), 1.4))
        p.setBrush(g)
        p.drawRoundedRect(r, S(13), S(13))
        art = QPointF(r.left() + S(40), r.center().y())
        if self.kind == "golf":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#2E9E4F"))
            p.drawRoundedRect(QRectF(art.x() - S(24), art.y() - S(4), S(48), S(20)), S(10), S(10))
            p.setBrush(QColor("#0B120D"))
            p.drawEllipse(QPointF(art.x() + S(8), art.y() + S(6)), S(4), S(2.5))
            p.setPen(QPen(QColor("#EDEDED"), S(1.5)))
            p.drawLine(QPointF(art.x() + S(8), art.y() + S(6)), QPointF(art.x() + S(8), art.y() - S(20)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#FF4B4B"))
            wave = math.sin(now * 4) * S(1.5)
            flag = QPainterPath(QPointF(art.x() + S(8), art.y() - S(20)))
            flag.lineTo(art.x() + S(20), art.y() - S(15) + wave)
            flag.lineTo(art.x() + S(8), art.y() - S(10))
            p.drawPath(flag)
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(QPointF(art.x() - S(12), art.y() + S(7)), S(3.4), S(3.4))
        else:
            paint_flip_coin(p, art, S(22), now * 2.2, None)
        p.setPen(QColor(TEXT))
        p.setFont(font(14, QFont.Weight.ExtraBold))
        name = tr("Mini Golf") if self.kind == "golf" else tr("Coinflip")
        p.drawText(QRectF(r.left() + S(80), r.top() + S(14), r.width() - S(150), S(24)), int(Qt.AlignmentFlag.AlignVCenter), name)
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        sub = (tr("1v1 live, 5 holes. Bet coins.") if self.kind == "golf" else tr("Items against items. Black or white."))
        p.drawText(QRectF(r.left() + S(80), r.top() + S(40), r.width() - S(100), S(20)), int(Qt.AlignmentFlag.AlignVCenter), sub)
        tag = tr("DUEL")
        p.setFont(font(9.5, QFont.Weight.Black, 1.0))
        tw = p.fontMetrics().horizontalAdvance(tag) + S(22)
        pill = QRectF(r.right() - tw - S(12), r.top() + S(12), tw, S(20))
        pulse = 0.5 + 0.5 * math.sin(now * 3)
        p.setPen(QPen(alpha("#3DDC84", 0.6 + 0.3 * pulse), S(1.2)))
        p.setBrush(alpha("#3DDC84", 0.14 + 0.08 * pulse))
        p.drawRoundedRect(pill, S(10), S(10))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#3DDC84"))
        p.drawEllipse(QPointF(pill.left() + S(10), pill.center().y()), S(3), S(3))
        p.setPen(QColor("#3DDC84"))
        p.drawText(pill.adjusted(S(14), 0, 0, 0), int(Qt.AlignmentFlag.AlignCenter), tag)


def paint_flip_coin(p: QPainter, c: QPointF, radius: float, angle: float, side) -> None:
    """The coinflip coin: black on one face, white on the other. `angle` turns it (radians); `side` forces a face."""
    k = math.cos(angle)
    face = side if side is not None else ("black" if k >= 0 else "white")
    sx = max(0.06, abs(k)) if side is None else 1.0
    p.save()
    p.translate(c)
    p.scale(sx, 1.0)
    edge = QColor("#8C939A")
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(alpha("#000000", 0.35))
    p.drawEllipse(QPointF(0, radius * 0.12), radius, radius)
    g = QRadialGradient(QPointF(-radius * 0.35, -radius * 0.35), radius * 1.6)
    if face == "black":
        g.setColorAt(0, QColor("#4A5157"))
        g.setColorAt(1, QColor("#0B0D0F"))
    else:
        g.setColorAt(0, QColor("#FFFFFF"))
        g.setColorAt(1, QColor("#BFC6CC"))
    p.setPen(QPen(edge, max(1.0, radius * 0.08)))
    p.setBrush(g)
    p.drawEllipse(QPointF(0, 0), radius, radius)
    p.setPen(QPen(alpha("#FFFFFF" if face == "black" else "#000000", 0.22), max(1.0, radius * 0.05)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(0, 0), radius * 0.78, radius * 0.78)
    p.setPen(QColor("#FFFFFF") if face == "black" else QColor("#0B0D0F"))
    f = font(1)
    f.setPixelSize(max(6, int(radius * 0.95)))
    f.setWeight(QFont.Weight.Black)
    p.setFont(f)
    p.drawText(QRectF(-radius, -radius, radius * 2, radius * 2), int(Qt.AlignmentFlag.AlignCenter), "R")
    p.restore()
