"""Games tab: a lobby, then the casino (blackjack, plinko, bombs, slots and the free daily spin). Rubenium coins only.

Rules that hold everywhere: a bet is taken before a round starts and can never be more than you have (no debt);
every result comes from the system's secure random numbers; the odds slightly favour the house."""
import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import QGridLayout, QWidget

from .core import S, sfx, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, mix, tr, ui
from .pages import Page
from .shop import CoinBar, GOLD_TEXT, clock_text
from .wallet import coins_text, paint_coin
from .widgets import Button, IconButton, Label, Segmented, Tween, draw_icon, hbox, heading, vbox
from .games2 import (BeatRush, BigCard, MemoryGame, MEM_THEMES, ScratchCard, ScratchRow, TAP_MODES, build_duels,
                     build_minigames)

RNG = random.SystemRandom()
BETS = [10, 25, 50, 100, 250, 500, 1000]
WIN, LOSE = "#35E0A1", "#FF5C6C"
TABLE_H = 260


def ease_out(t: float, power: int = 3) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** power


class Game(QWidget):
    """Base of every game: a painted table that animates only while something moves."""

    def __init__(self, page) -> None:
        super().__init__()
        self.page, self.ctx, self.wallet = page, page.ctx, page.ctx.wallet
        self.setFixedSize(page.W, S(TABLE_H))
        self.stake = 0
        self.busy = False                        # a round is running: the bet is locked
        self.waiting = False                     # a request to the server is on its way
        self.econ = page.ctx.econ
        self._flash = ("", "", 0.0)
        self._frames = QTimer(self)
        self._frames.setTimerType(Qt.TimerType.PreciseTimer)
        self._frames.setInterval(16)
        self._frames.timeout.connect(self.update)
        self._until = 0.0

    # -- helpers
    def animate(self, seconds: float) -> None:
        self._until = max(self._until, time.monotonic() + seconds)
        if not self._frames.isActive():
            self._frames.start()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(r, S(12), S(12))
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor("#0C1113"))
        g.setColorAt(1, QColor("#080B0C"))
        p.fillPath(clip, g)
        p.save()
        p.setClipPath(clip)
        self.draw(p, r, time.monotonic())
        p.restore()
        p.setPen(QPen(alpha("#FFFFFF", 0.08), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, S(12), S(12))
        self._draw_flash(p, r)
        if time.monotonic() > self._until and not self.always_moving():
            self._frames.stop()

    def always_moving(self) -> bool:
        return False

    def mousePressEvent(self, e) -> None:
        e.accept()                               # pressing the table never moves the menu

    def options(self):
        """(labels, index) of the choice row above the bet, or None."""
        return None

    def set_option(self, i: int) -> None: ...

    def showEvent(self, _e) -> None:
        if self.always_moving():
            self._frames.start()

    def hideEvent(self, _e) -> None:
        self._frames.stop()

    def take(self) -> bool:
        """Take the bet for a new round (on screen; the server takes it for real with the request)."""
        bet = self.page.bet()
        if not self.econ.ready:
            self.ctx.toast(tr("No internet connection"), "warn")
            return False
        if bet <= 0 or bet > self.econ.coins:
            self.ctx.toast(tr("Not enough coins"), "warn")
            return False
        self.stake = bet
        self.busy = True
        self.econ.adjust(-bet)
        self.page.sync()
        return True

    def ask(self, fn: str, args: dict, on_ok, once: bool = False, refund: int = 0) -> None:
        """Send a move to the server. On an error the coins taken on screen are put back."""
        self.waiting = True
        self.page.sync()

        def back(ok: bool, data) -> None:
            try:
                self.waiting = False
                if ok:
                    on_ok(data)
                else:
                    if refund:
                        self.econ.adjust(refund)
                    self.failed(str(data))
                self.page.sync()
            except RuntimeError:                      # the page was closed meanwhile
                pass
        self.econ.call(fn, args, back, once=once, hold=True)

    def failed(self, message: str) -> None:
        self.busy = False
        self.ctx.toast(tr(message), "warn")

    def finish(self, payout: int) -> None:
        """End of the round: pay what was won (0 = lost) and show it."""
        payout = int(payout)
        if payout > 0:
            self.econ.adjust(payout)
        gain = payout - self.stake
        if gain > 0:
            self.flash("+" + coins_text(gain), WIN)
            sfx.play("on")
        elif gain < 0:
            self.flash("−" + coins_text(-gain), LOSE)
            sfx.play("off")
        else:
            self.flash("0", TEXT_DIM)
        self.busy = False
        self.page.sync()

    def flash(self, text: str, colour: str) -> None:
        self._flash = (text, colour, time.monotonic())
        self.animate(1.8)

    def _draw_flash(self, p: QPainter, r: QRectF) -> None:
        text, colour, born = self._flash
        age = time.monotonic() - born
        if not text or age > 1.7:
            return
        a = min(1.0, age / 0.15) * (1.0 - max(0.0, (age - 1.2) / 0.5))
        rise = S(10) * ease_out(age / 0.5)
        p.setFont(font(22, QFont.Weight.ExtraBold))
        w = p.fontMetrics().horizontalAdvance(text) + S(28)
        box = QRectF(r.center().x() - w / 2, r.center().y() - S(20) - rise, w, S(40))
        p.setOpacity(a)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(6, 8, 9, 225))
        p.drawRoundedRect(box, S(12), S(12))
        p.setPen(QColor(colour))
        p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), text)
        p.setOpacity(1.0)

    # -- for the page
    def buttons(self) -> list:
        """[(text, kind, callback, enabled)] for the row under the table."""
        return []

    def draw(self, p: QPainter, r: QRectF, now: float) -> None: ...


# --------------------------------------------------------------------------- #
# Blackjack
# --------------------------------------------------------------------------- #
SUITS = "♠♥♦♣"
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


def hand_total(cards: list) -> int:
    total, aces = 0, 0
    for c in cards:
        rank = c["rank"]
        if rank == "A":
            aces += 1
            total += 11
        else:
            total += 10 if rank in ("J", "Q", "K") else int(rank)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


class Blackjack(Game):
    """You against the dealer. Closest to 21 wins; the dealer draws to 17; blackjack pays 3 to 2."""

    def __init__(self, page) -> None:
        super().__init__(page)
        self.player: list = []
        self.dealer: list = []
        self.phase = "idle"              # idle -> player -> dealer -> idle

    def _card(self, code, hidden: bool = False, delay: float = 0.0) -> dict:
        """A card as the server names it (0..51), or a face-down one (None)."""
        rank = RANKS[code % 13] if code is not None else "A"
        suit = SUITS[code // 13] if code is not None else "♠"
        return {"rank": rank, "suit": suit, "born": time.monotonic() + delay, "hidden": hidden, "turned": 0.0}

    def deal(self) -> None:
        if self.busy or self.waiting or not self.take():
            return
        self.player, self.dealer, self.phase = [], [], "wait"
        self.ask("rb_blackjack", {"action": "start", "bet": self.stake}, self._dealt, refund=self.stake)

    def failed(self, message: str) -> None:
        if message == "Finish your round first":         # a hand from before is still open: finish it
            self.phase = "wait"
            return self.ask("rb_blackjack", {"action": "stand", "bet": None}, self._old_round)
        self.phase = "idle" if not self.player else "player"
        self.busy = bool(self.player)
        self.ctx.toast(tr(message), "warn")

    def _old_round(self, ans: dict) -> None:
        self.stake = int(ans.get("stake") or 0)
        self.player = [self._card(c) for c in ans.get("me") or []]
        self.dealer = [self._card(c) for c in ans.get("dealer") or []]
        self.phase = "idle"
        self.animate(0.6)
        self.finish(int(ans.get("paid") or 0) + 0)

    def _dealt(self, ans: dict) -> None:
        me, shown = ans["me"], ans["dealer"]
        self.player = [self._card(me[0], delay=0.0), self._card(me[1], delay=0.36)]
        self.dealer = [self._card(shown[0], delay=0.18), self._card(None, hidden=True, delay=0.54)]
        self.phase = "player"
        self.animate(1.2)
        if not ans["open"]:                              # a natural: the round is already over
            self.phase = "dealer"
            QTimer.singleShot(1000, lambda: self._reveal(ans))

    def hit(self) -> None:
        if self.phase != "player" or self.waiting:
            return
        self.ask("rb_blackjack", {"action": "hit", "bet": None}, self._drew)

    def double(self) -> None:
        if self.phase != "player" or self.waiting or len(self.player) != 2 or self.econ.coins < self.stake:
            return
        self.econ.adjust(-self.stake)
        self.ask("rb_blackjack", {"action": "double", "bet": None}, self._doubled, refund=self.stake)

    def _doubled(self, ans: dict) -> None:
        self.stake = int(ans.get("stake") or self.stake * 2)
        self._drew(ans)

    def _drew(self, ans: dict) -> None:
        self.player.append(self._card(ans["me"][-1]))
        self.animate(0.6)
        if not ans["open"]:
            self.phase = "dealer"
            QTimer.singleShot(650, lambda: self._reveal(ans))

    def stand(self) -> None:
        if self.phase != "player" or self.waiting:
            return
        self.phase = "dealer"
        self.ask("rb_blackjack", {"action": "stand", "bet": None}, self._reveal)

    def _reveal(self, ans: dict) -> None:
        """The round is over on the server: turn the hidden card, show the dealer's draws, then the result."""
        cards = ans.get("dealer") or []
        if len(self.dealer) > 1 and len(cards) > 1:
            self.dealer[1] = dict(self._card(cards[1]), born=self.dealer[1]["born"], turned=time.monotonic())
        self.animate(0.8)
        rest = [] if int(ans.get("total") or 0) > 21 else list(cards[2:])
        self._dealer_step(rest, int(ans.get("paid") or 0))

    def _dealer_step(self, rest: list, paid: int) -> None:
        if rest:
            def draw() -> None:
                self.dealer.append(self._card(rest[0]))
                self.animate(0.7)
                self._dealer_step(rest[1:], paid)
            return QTimer.singleShot(700, draw)
        QTimer.singleShot(650, lambda: self._end(paid))

    def _end(self, pay: int) -> None:
        self.phase = "idle"
        self.finish(pay)

    def buttons(self) -> list:
        if self.phase == "player":
            go = not self.waiting
            can_double = go and len(self.player) == 2 and self.econ.coins >= self.stake
            return [(tr("Hit"), "primary", self.hit, go), (tr("Stand"), "ghost", self.stand, go),
                    (tr("Double"), "ghost", self.double, can_double)]
        return [(tr("Deal"), "primary", self.deal, self.phase == "idle" and not self.busy)]

    def _draw_card(self, p: QPainter, x: float, y: float, card: dict, now: float, deck: QPointF) -> None:
        w, h = S(44), S(62)
        t = ease_out((now - card["born"]) / 0.32)
        if now < card["born"]:
            return
        cx, cy = deck.x() + (x - deck.x()) * t, deck.y() + (y - deck.y()) * t
        flip = 1.0
        face = not card["hidden"]
        if card["turned"]:
            f = min(1.0, (now - card["turned"]) / 0.3)
            flip = abs(1.0 - 2.0 * f)
            face = f >= 0.5
        p.save()
        p.translate(cx + w / 2, cy + h / 2)
        p.scale(max(0.04, flip), 1.0)
        p.setOpacity(min(1.0, t * 1.6))
        rect = QRectF(-w / 2, -h / 2, w, h)
        p.setPen(QPen(alpha("#000000", 0.5), 1))
        if face:
            p.setBrush(QColor("#F4F5F6"))
            p.drawRoundedRect(rect, S(6), S(6))
            red = card["suit"] in "♥♦"
            p.setPen(QColor("#D8314A") if red else QColor("#14181A"))
            p.setFont(font(15, QFont.Weight.Bold))
            p.drawText(QRectF(rect.left() + S(5), rect.top() + S(3), w, S(20)), int(Qt.AlignmentFlag.AlignLeft), card["rank"])
            p.setFont(font(20))
            p.drawText(QRectF(rect.left(), rect.top() + S(20), w, h - S(22)), int(Qt.AlignmentFlag.AlignCenter), card["suit"])
        else:
            p.setBrush(QColor("#151B1F"))
            p.drawRoundedRect(rect, S(6), S(6))
            p.setPen(QPen(alpha(ui.accent, 0.7), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(S(5), S(5), -S(5), -S(5)), S(4), S(4))
            p.setFont(font(16, QFont.Weight.ExtraBold))
            p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "R")
        p.restore()

    def draw(self, p: QPainter, r: QRectF, now: float) -> None:
        deck = QPointF(r.right() - S(54), r.top() + S(10))
        for cards, y, mine in ((self.dealer, r.top() + S(22), False), (self.player, r.bottom() - S(84), True)):
            n = len(cards)
            step = min(S(52), (r.width() - S(120)) / max(1, n))
            x0 = r.center().x() - (step * (n - 1) + S(44)) / 2
            for i, card in enumerate(cards):
                self._draw_card(p, x0 + i * step, y, card, now, deck)
            shown = [c for c in cards if not c["hidden"] and now >= c["born"] + 0.25]
            if shown:
                total = str(hand_total(shown))
                p.setFont(font(12, QFont.Weight.Bold))
                pill = QRectF(r.left() + S(12), y + S(20), S(34), S(22))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha(ui.accent, 0.20) if mine else alpha("#FFFFFF", 0.08))
                p.drawRoundedRect(pill, S(11), S(11))
                p.setPen(QColor(TEXT))
                p.drawText(pill, int(Qt.AlignmentFlag.AlignCenter), total)
        if not self.player:
            p.setPen(alpha(TEXT_DIM, 0.6))
            p.setFont(font(34, QFont.Weight.ExtraBold))
            p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), "21")


# --------------------------------------------------------------------------- #
# Plinko: drop a ball through the pins
# --------------------------------------------------------------------------- #
class Plinko(Game):
    """A ball falls through 10 rows of pins, bouncing left or right at each one, and lands in a box that
    multiplies the bet. Up to 3 balls at once. Every risk level pays back about 96% over time."""
    ROWS = 10
    RISKS = ["Low risk", "Medium risk", "High risk"]
    MULTS = [[8.5, 3, 1.4, 1.1, 0.95, 0.5, 0.95, 1.1, 1.4, 3, 8.5],
             [21, 5, 2, 1.3, 0.6, 0.4, 0.6, 1.3, 2, 5, 21],
             [70, 9, 3, 0.9, 0.3, 0.2, 0.3, 0.9, 3, 9, 70]]
    STEP = 0.13                                   # seconds per row
    MAX_BALLS = 3
    GAP = 0.45                                    # at least this long between two balls

    def __init__(self, page) -> None:
        super().__init__(page)
        self.risk = 0
        self.balls: list = []
        self._last = 0.0
        self._presses: list = []
        self._cool = 0.0
        self._hits: dict = {}                     # box -> time it was last hit
        self._pops: list = []                     # (text, colour, box, time)
        self._flying = 0                          # balls asked for and not landed yet

    def options(self):
        return [tr(n) for n in self.RISKS], self.risk

    def set_option(self, i: int) -> None:
        if not self.busy:
            self.risk = i
            self.update()

    def _too_regular(self, now: float) -> bool:
        """An auto-clicker presses at a perfectly even pace: pause it for a while."""
        self._presses = (self._presses + [now])[-12:]
        if len(self._presses) < 12:
            return False
        gaps = [b - a for a, b in zip(self._presses, self._presses[1:])]
        mean = sum(gaps) / len(gaps)
        spread = (sum((g - mean) ** 2 for g in gaps) / len(gaps)) ** 0.5
        return spread < 0.012 and mean < 2.0

    def drop(self) -> None:
        now = time.monotonic()
        if now < self._cool:
            return self.ctx.toast(tr("Slow down"), "warn")
        if self._flying >= self.MAX_BALLS or now - self._last < self.GAP:
            return
        if self._too_regular(now):
            self._cool = now + 20.0
            self._presses = []
            return self.ctx.toast(tr("Slow down"), "warn")
        bet = self.page.bet()
        if not self.econ.ready or bet <= 0 or bet > self.econ.coins:
            return self.ctx.toast(tr("Not enough coins"), "warn")
        self._last = now
        self.stake = bet
        self.busy = True
        self._flying += 1
        self.econ.adjust(-bet)
        risk = self.risk

        def dropped(ans: dict) -> None:                  # the server decided the path: the ball shows it
            path = [1 if d else -1 for d in ans["path"]]
            self.balls.append(dict(path=path, box=int(ans["box"]), born=time.monotonic(), stake=bet, risk=risk,
                                   pay=int(ans["paid"]), mult=float(ans["mult"])))
            self.animate(self.ROWS * self.STEP + 1.5)
            QTimer.singleShot(int((self.ROWS * self.STEP + 0.12) * 1000), self._land)
        self.ask("rb_plinko", {"bet": bet, "risk": risk}, dropped, once=True, refund=bet)

    def failed(self, message: str) -> None:
        self._flying = max(0, self._flying - 1)
        self.busy = self._flying > 0
        self.ctx.toast(tr(message), "warn")

    def _land(self) -> None:
        if not self.balls:
            return
        ball = self.balls.pop(0)
        mult, pay = ball["mult"], ball["pay"]
        self._flying = max(0, self._flying - 1)
        if pay:
            self.econ.adjust(pay)
        now = time.monotonic()
        self._hits[ball["box"]] = now
        colour = WIN if mult >= 1 else (TEXT_DIM if mult >= 0.5 else LOSE)
        self._pops = [x for x in self._pops if now - x[3] < 1.2] + [(f"×{mult:g}", colour, ball["box"], now)]
        sfx.play("on" if mult >= 2 else "pick")
        self.animate(1.3)
        if not self._flying:
            self.busy = False
        self.page.sync()

    def buttons(self) -> list:
        return [(tr("Drop"), "primary", self.drop, self._flying < self.MAX_BALLS)]

    def _geo(self, r: QRectF):
        top, bottom = r.top() + S(22), r.bottom() - S(40)
        dy = (bottom - top) / (self.ROWS - 1)
        dx = min((r.width() - S(16)) / (self.ROWS + 2), dy * 1.25)
        return top, dy, dx

    def draw(self, p: QPainter, r: QRectF, now: float) -> None:
        top, dy, dx = self._geo(r)
        cx = r.center().x()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.55))
        for i in range(self.ROWS):                                   # pins
            n = i + 3
            for j in range(n):
                p.drawEllipse(QPointF(cx + (j - (n - 1) / 2) * dx, top + i * dy), S(2.1), S(2.1))
        mults = self.MULTS[self.risk]
        top_mult = max(mults)
        by = top + (self.ROWS - 1) * dy + S(14)
        for k, m in enumerate(mults):                                # the boxes
            x = cx + (k - 5) * dx
            hit = self._hits.get(k, -9.0)
            bump = max(0.0, 1.0 - (now - hit) / 0.35)
            box = QRectF(x - dx / 2 + S(1.5), by + bump * S(4), dx - S(3), S(22))
            heat = (math.log(max(m, 0.2)) - math.log(0.2)) / (math.log(top_mult) - math.log(0.2))
            col = mix(QColor("#2A3238"), QColor("#E8C26A") if heat < 0.8 else QColor("#FF5C4D"), max(0.0, heat))
            p.setBrush(mix(col, QColor("#FFFFFF"), bump * 0.5))
            p.drawRoundedRect(box, S(4), S(4))
            p.setPen(QColor("#0A0D0E") if heat > 0.45 else QColor(TEXT))
            p.setFont(font(8 if m < 10 else 8.5, QFont.Weight.Bold))
            p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), f"{m:g}")
            p.setPen(Qt.PenStyle.NoPen)
        for ball in self.balls:                                      # falling balls
            t = (now - ball["born"]) / self.STEP
            i = int(max(0.0, min(self.ROWS - 0.001, t)))
            f = max(0.0, min(1.0, t - i))
            off0 = sum(ball["path"][:i]) * dx / 2
            off1 = off0 + ball["path"][i] * dx / 2
            y0 = top - dy * 0.6 if i == 0 else top + (i - 1) * dy - S(5)
            y1 = top + i * dy - S(5)
            if t < 0:
                continue
            x = cx + off0 + (off1 - off0) * f
            y = y0 + (y1 - y0) * f - math.sin(f * math.pi) * dy * 0.35
            if t >= self.ROWS:
                y = top + (self.ROWS - 1) * dy + S(4) + min(1.0, (t - self.ROWS) * 2) * S(10)
            p.setBrush(alpha(ui.accent, 0.25))
            p.drawEllipse(QPointF(x, y), S(7), S(7))
            p.setBrush(mix(ui.accent, QColor("#FFFFFF"), 0.35))
            p.drawEllipse(QPointF(x, y), S(4.6), S(4.6))
        for text, colour, k, born in self._pops:                     # what each ball made
            age = now - born
            if age > 1.1:
                continue
            p.setOpacity(1.0 - max(0.0, (age - 0.6) / 0.5))
            p.setPen(QColor(colour))
            p.setFont(font(12, QFont.Weight.ExtraBold))
            x = cx + (k - 5) * dx
            p.drawText(QRectF(x - S(30), by - S(24) - age * S(16), S(60), S(18)), int(Qt.AlignmentFlag.AlignCenter), text)
            p.setOpacity(1.0)
            p.setPen(Qt.PenStyle.NoPen)


# --------------------------------------------------------------------------- #
# Bombs: find the R gems, avoid the bombs
# --------------------------------------------------------------------------- #
def bombs_mult(found: int, bombs: int, tiles: int = 25) -> float:
    """What the bet is multiplied by after `found` safe tiles: fair odds, less 3% for the house, at most ×1000."""
    chance = 1.0
    for i in range(found):
        chance *= (tiles - bombs - i) / (tiles - i)
    return min(1000.0, math.floor(0.97 / chance * 100) / 100) if found else 1.0


class Bombs(Game):
    """25 face-down cards hide R gems and bombs. Each gem raises the multiplier; cash out whenever you like.
    Hit a bomb and the bet is lost. More bombs, bigger multipliers. The board is set before you pick."""
    N = 25
    CHOICES = [1, 3, 5, 10, 20]

    def __init__(self, page) -> None:
        super().__init__(page)
        self.choice = 1                                 # index in CHOICES
        self.board: set = set()
        self.shown: dict = {}                           # tile -> time it was turned
        self.phase = "idle"                             # idle -> play -> idle
        self.boom = -1
        self.picked: set = set()                        # cards you turned yourself (stay bright after the round)
        self._hover = -1
        self.setMouseTracking(True)

    def bombs(self) -> int:
        return self.CHOICES[self.choice]

    def options(self):
        return [str(n) for n in self.CHOICES], self.choice

    def set_option(self, i: int) -> None:
        if not self.busy:
            self.choice = i
            self.shown, self.boom, self.board = {}, -1, set()
            self.update()

    def found(self) -> int:
        return sum(1 for t in self.shown if t not in self.board) if self.phase == "play" else 0

    def start(self) -> None:
        if self.busy or self.waiting or not self.take():
            return
        self.board, self.shown, self.boom, self.picked = set(), {}, -1, set()
        self.ask("rb_mines", {"action": "start", "arg": self.bombs() * 10000 + self.stake}, self._started,
                 refund=self.stake)

    def _started(self, ans: dict) -> None:
        self.phase = "play"
        self.animate(0.5)

    def failed(self, message: str) -> None:
        if message == "Finish your round first":         # a board from before is still open: carry on with it
            return self.ask("rb_mines", {"action": "look", "arg": None}, self._resumed)
        if self.phase != "play":
            self.busy = False
        self.ctx.toast(tr(message), "warn")

    def _resumed(self, ans: dict) -> None:
        if not ans.get("open"):
            self.busy = False
            return
        self.stake = int(ans["bet"])
        if int(ans["bombs"]) in self.CHOICES:
            self.choice = self.CHOICES.index(int(ans["bombs"]))
        now = time.monotonic()
        self.picked = set(ans.get("picked") or [])
        self.shown = {t: now for t in self.picked}
        self.board, self.boom, self.phase, self.busy = set(), -1, "play", True
        self.animate(0.5)

    def _grid(self, r: QRectF):
        gap = S(6)
        size = (r.height() - S(24) - 4 * gap) / 5
        left = r.left() + S(12)
        top = r.top() + S(12)
        return left, top, size, gap

    def _tile(self, i: int, r: QRectF) -> QRectF:
        left, top, size, gap = self._grid(r)
        return QRectF(left + (i % 5) * (size + gap), top + (i // 5) * (size + gap), size, size)

    def _at(self, pos) -> int:
        r = QRectF(self.rect())
        for i in range(self.N):
            if self._tile(i, r).contains(pos):
                return i
        return -1

    def mouseMoveEvent(self, e) -> None:
        i = self._at(e.position())
        if i != self._hover:
            self._hover = i
            self.setCursor(Qt.CursorShape.PointingHandCursor if (i >= 0 and self.phase == "play" and i not in self.shown)
                           else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = -1
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()
        if e.button() != Qt.MouseButton.LeftButton or self.phase != "play" or self.waiting:
            return
        i = self._at(e.position())
        if i < 0 or i in self.shown:
            return
        return self.ask("rb_mines", {"action": "pick", "arg": i}, lambda ans: self._picked(i, ans))

    def _picked(self, i: int, ans: dict) -> None:
        now = time.monotonic()
        self.shown[i] = now
        self.picked.add(i)
        self.animate(0.6)
        if ans.get("hit"):                               # bomb: the round is lost, then every card is shown
            self.board = set(ans.get("board") or [i])
            self.boom = i
            self.phase = "lost"
            sfx.play("off")
            self.page.sync()
            QTimer.singleShot(650, self._reveal_all)
            QTimer.singleShot(1100, lambda: self._end(0))
            return
        sfx.play("pick")
        if not ans.get("open"):                          # every gem found: the server paid already
            self._cashed(ans)
        self.page.sync()

    def _reveal_all(self) -> None:
        now = time.monotonic()
        for k in range(self.N):
            self.shown.setdefault(k, now + 0.02 * (k % 5))
        self.animate(0.8)

    def cash(self) -> None:
        if self.phase != "play" or self.found() < 1 or self.waiting:
            return
        self.ask("rb_mines", {"action": "cash", "arg": None}, self._cashed)

    def _cashed(self, ans: dict) -> None:
        self.board = set(ans.get("board") or [])
        self.phase = "won"
        self._reveal_all()
        self._end(int(ans.get("paid") or 0))

    def _end(self, pay: int) -> None:
        self.phase = "idle"
        self.finish(pay)

    def buttons(self) -> list:
        if self.phase == "play":
            mult = bombs_mult(self.found(), self.bombs())
            return [(tr("Cash out") + f"  ×{mult:g}", "primary", self.cash, self.found() >= 1 and not self.waiting)]
        return [(tr("Bet"), "primary", self.start, self.phase == "idle" and not self.busy)]

    def draw(self, p: QPainter, r: QRectF, now: float) -> None:
        playing = self.phase == "play"
        for i in range(self.N):
            tile = self._tile(i, r)
            turned = self.shown.get(i)
            f = 0.0 if turned is None else max(0.0, min(1.0, (now - turned) / 0.22))
            flip = abs(1.0 - 2.0 * f)
            face = f >= 0.5
            p.save()
            p.translate(tile.center())
            p.scale(max(0.05, flip) if turned is not None else 1.0, 1.0)
            box = QRectF(-tile.width() / 2, -tile.height() / 2, tile.width(), tile.height())
            hov = i == self._hover and playing and turned is None
            if not face:
                p.setPen(QPen(alpha(ui.accent, 0.55) if hov else alpha("#FFFFFF", 0.10), 1.2))
                p.setBrush(QColor("#1A2125") if hov else QColor("#141A1D"))
                p.drawRoundedRect(box.translated(0, -S(2) if hov else 0), S(7), S(7))
                p.setPen(alpha("#FFFFFF", 0.16 if not hov else 0.4))
                p.setFont(font(13, QFont.Weight.ExtraBold))
                p.drawText(box.translated(0, -S(2) if hov else 0), int(Qt.AlignmentFlag.AlignCenter), "R")
            else:
                bomb = i in self.board
                mine = i == self.boom
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#3A1418") if mine else QColor("#0E1316"))
                p.drawRoundedRect(box, S(7), S(7))
                if self.phase != "play" and not mine and i not in self.picked:
                    p.setOpacity(0.45)
                u = box.width() * 0.3
                if bomb:
                    self._bomb(p, u, now - (turned or now), mine)
                else:
                    self._gem(p, u)
                p.setOpacity(1.0)
            p.restore()
        left, top, size, gap = self._grid(r)
        side = QRectF(left + 5 * size + 4 * gap + S(12), top, r.right() - (left + 5 * size + 4 * gap + S(24)),
                      5 * size + 4 * gap)
        found = self.found()
        now_mult = bombs_mult(found, self.bombs())
        next_mult = bombs_mult(found + 1, self.bombs()) if found < self.N - self.bombs() else now_mult
        p.setPen(QColor(GOLD_TEXT if found else TEXT))
        p.setFont(font(20, QFont.Weight.ExtraBold))
        p.drawText(QRectF(side.left(), side.top() + S(18), side.width(), S(30)), int(Qt.AlignmentFlag.AlignCenter),
                   f"×{now_mult:g}")
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(side.left(), side.top() + S(50), side.width(), S(18)), int(Qt.AlignmentFlag.AlignCenter),
                   f"→ ×{next_mult:g}")
        y = side.bottom() - S(44)                       # gems found and bombs on the board
        p.save()
        p.translate(side.center().x() - S(26), y)
        self._gem(p, S(6.5))
        p.restore()
        p.save()
        p.translate(side.center().x() - S(26), y + S(24))
        self._bomb(p, S(6.5), 1.0, False)
        p.restore()
        p.setPen(QColor(TEXT))
        p.setFont(font(12, QFont.Weight.Bold))
        p.drawText(QRectF(side.center().x() - S(12), y - S(10), S(50), S(20)), int(Qt.AlignmentFlag.AlignVCenter),
                   str(found))
        p.drawText(QRectF(side.center().x() - S(12), y + S(14), S(50), S(20)), int(Qt.AlignmentFlag.AlignVCenter),
                   str(self.bombs()))

    def _gem(self, p: QPainter, u: float) -> None:
        """The R gem: a cut gem in your colour with an R on it."""
        pts = [QPointF(-u * 0.62, -u * 0.72), QPointF(u * 0.62, -u * 0.72), QPointF(u * 1.05, -u * 0.18),
               QPointF(0, u * 1.0), QPointF(-u * 1.05, -u * 0.18)]
        g = QLinearGradient(QPointF(0, -u), QPointF(0, u))
        g.setColorAt(0, mix(ui.accent, QColor("#FFFFFF"), 0.55))
        g.setColorAt(1, ui.accent)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha(ui.accent, 0.22))
        p.drawEllipse(QPointF(0, 0), u * 1.45, u * 1.45)
        p.setBrush(g)
        p.drawPolygon(QPolygonF(pts))
        p.setBrush(alpha("#FFFFFF", 0.35))
        p.drawPolygon(QPolygonF([pts[0], QPointF(0, -u * 0.18), pts[4]]))
        p.setPen(QColor("#0A0D0E"))
        f = font(10, QFont.Weight.ExtraBold)
        f.setPixelSize(max(6, int(u * 0.95)))
        p.setFont(f)
        p.drawText(QRectF(-u, -u * 0.62, u * 2, u * 1.2), int(Qt.AlignmentFlag.AlignCenter), "R")

    def _bomb(self, p: QPainter, u: float, age: float, mine: bool) -> None:
        if mine and age < 0.5:                           # a quick blast
            k = age / 0.5
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 140, 60, int(200 * (1 - k))))
            p.drawEllipse(QPointF(0, 0), u * (1.2 + 2.2 * k), u * (1.2 + 2.2 * k))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FF5C6C") if mine else QColor("#B9C0C6"))
        p.drawEllipse(QPointF(-u * 0.1, u * 0.12), u * 0.82, u * 0.82)
        p.drawRect(QRectF(u * 0.25, -u * 0.95, u * 0.38, u * 0.4))
        p.setPen(QPen(QColor("#FFB04D"), max(1.0, u * 0.14)))
        p.drawLine(QPointF(u * 0.44, -u * 0.95), QPointF(u * 0.7, -u * 1.2))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.45))
        p.drawEllipse(QPointF(-u * 0.38, -u * 0.15), u * 0.16, u * 0.12)


# --------------------------------------------------------------------------- #
# Slots
# --------------------------------------------------------------------------- #
class Slots(Game):
    """Three reels. Three of a kind pays big, any pair pays a little."""
    SYMBOLS = ["cherry", "lemon", "bell", "star", "diamond", "seven"]
    WEIGHTS = [6, 5, 4, 3, 2, 1]
    TRIPLE = {"cherry": 3, "lemon": 5, "bell": 8, "star": 12, "diamond": 25, "seven": 50}
    PAIR = 1.5

    def __init__(self, page) -> None:
        super().__init__(page)
        self.final = ["seven", "seven", "seven"]
        self.strips = [[RNG.choices(self.SYMBOLS, self.WEIGHTS)[0] for _ in range(40)] for _ in range(3)]
        for i in range(3):
            self.strips[i][1] = self.final[i]
        self._t0 = 0.0
        self.win_at = 0.0

    def spin(self) -> None:
        if self.busy or self.waiting or not self.take():
            return
        self.ask("rb_slots", {"bet": self.stake}, self._rolled, once=True, refund=self.stake)

    def _rolled(self, ans: dict) -> None:
        self.final = [self.SYMBOLS[int(i)] for i in ans["reels"]]
        self._paid = int(ans["paid"])
        for i in range(3):
            strip = [RNG.choices(self.SYMBOLS, self.WEIGHTS)[0] for _ in range(40)]
            strip[1] = self.final[i]
            self.strips[i] = strip
        self._t0 = time.monotonic()
        self.win_at = 0.0
        self.animate(3.0)
        QTimer.singleShot(2450, self._done)

    def _done(self) -> None:
        pay = getattr(self, "_paid", 0)
        if pay:
            self.win_at = time.monotonic()
        self.finish(pay)

    def buttons(self) -> list:
        return [(tr("Spin"), "primary", self.spin, not self.busy)]

    def win_key(self) -> str:
        """Which line of the pay table the last spin hit ('' = none)."""
        a, b, c = self.final
        if a == b == c:
            return a
        return "pair" if (a == b or b == c or a == c) else ""

    def draw(self, p: QPainter, r: QRectF, now: float) -> None:
        rw, rh = S(76), S(147)
        gap = S(10)
        x0 = r.center().x() - (3 * rw + 2 * gap) / 2
        top = r.top() + S(10)
        row_h = rh / 3
        for i in range(3):
            reel = QRectF(x0 + i * (rw + gap), top, rw, rh)
            p.setPen(QPen(alpha("#FFFFFF", 0.10), 1))
            p.setBrush(QColor("#0E1315"))
            p.drawRoundedRect(reel, S(10), S(10))
            dur = 1.2 + 0.5 * i
            t = (now - self._t0) / dur if self._t0 else 1.0
            offset = (1.0 - ease_out(t, 3)) * 30.0             # rows still to travel
            whole, frac = int(offset), offset - int(offset)
            p.save()
            clip = QPainterPath()
            clip.addRoundedRect(reel.adjusted(1, 1, -1, -1), S(9), S(9))
            p.setClipPath(clip)
            for k in range(-1, 4):
                sym = self.strips[i][(whole + k) % len(self.strips[i])]
                cy = reel.top() + (k + 0.5 + frac) * row_h
                self._symbol(p, sym, QPointF(reel.center().x(), cy), row_h * 0.32)
            shade = QLinearGradient(reel.topLeft(), reel.bottomLeft())
            shade.setColorAt(0.0, QColor(8, 11, 12, 235))
            shade.setColorAt(0.30, QColor(8, 11, 12, 0))
            shade.setColorAt(0.70, QColor(8, 11, 12, 0))
            shade.setColorAt(1.0, QColor(8, 11, 12, 235))
            p.fillRect(reel, shade)
            p.restore()
        line = QRectF(x0 - S(8), top + row_h, 3 * rw + 2 * gap + S(16), row_h)
        glow = 0.0
        if self.win_at:
            glow = max(0.0, 1.0 - (now - self.win_at) / 1.6) * (0.5 + 0.5 * math.sin((now - self.win_at) * 14))
        p.setPen(QPen(mix(alpha("#FFFFFF", 0.22), QColor(GOLD_TEXT), glow), 1.4 + glow))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(line, S(10), S(10))
        # the pay table: every way to win, best first
        hit = self.win_key() if (self.win_at and not self.busy) else ""
        entries = [(sym, self.TRIPLE[sym]) for sym in reversed(self.SYMBOLS)] + [("pair", self.PAIR)]
        cols, cell_h = 4, S(32)
        area = QRectF(r.left() + S(8), top + rh + S(12), r.width() - S(16), cell_h * 2)
        cw = area.width() / cols
        for n, (sym, mult) in enumerate(entries):
            span = 2 if sym == "pair" else 1                   # the last line fills the row
            cell = QRectF(area.left() + (n % cols) * cw, area.top() + (n // cols) * cell_h, cw * span, cell_h).adjusted(
                S(2), S(2), -S(2), -S(2))
            lit = sym == hit
            p.setPen(QPen(QColor(GOLD_TEXT), 1.3) if lit else Qt.PenStyle.NoPen)
            p.setBrush(alpha(GOLD_TEXT, 0.16) if lit else alpha("#FFFFFF", 0.035))
            p.drawRoundedRect(cell, S(7), S(7))
            u = S(5.2)
            if sym == "pair":
                p.setPen(QColor(TEXT_DIM))
                p.setFont(font(10, QFont.Weight.DemiBold))
                p.drawText(cell.adjusted(S(9), 0, 0, 0), int(Qt.AlignmentFlag.AlignVCenter), tr("Any two the same"))
            else:
                for k in range(3):
                    self._symbol(p, sym, QPointF(cell.left() + S(11) + k * S(12.5), cell.center().y()), u)
            p.setPen(QColor(GOLD_TEXT) if (lit or mult >= 25) else QColor(TEXT))
            p.setFont(font(10.5, QFont.Weight.ExtraBold))
            p.drawText(cell.adjusted(0, 0, -S(6), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                       f"×{mult:g}")

    def _symbol(self, p: QPainter, sym: str, c: QPointF, u: float) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        if sym == "cherry":
            p.setPen(QPen(QColor("#4FA35A"), max(1.2, u * 0.12)))
            p.drawLine(QPointF(c.x() - u * 0.45, c.y() + u * 0.2), QPointF(c.x() + u * 0.2, c.y() - u * 0.95))
            p.drawLine(QPointF(c.x() + u * 0.5, c.y() + u * 0.3), QPointF(c.x() + u * 0.2, c.y() - u * 0.95))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#E0354B"))
            p.drawEllipse(QPointF(c.x() - u * 0.45, c.y() + u * 0.4), u * 0.45, u * 0.45)
            p.drawEllipse(QPointF(c.x() + u * 0.5, c.y() + u * 0.5), u * 0.45, u * 0.45)
        elif sym == "lemon":
            p.setBrush(QColor("#F2D43D"))
            p.drawEllipse(c, u * 0.95, u * 0.68)
            p.setBrush(QColor("#FFF3A6"))
            p.drawEllipse(QPointF(c.x() - u * 0.3, c.y() - u * 0.2), u * 0.22, u * 0.14)
        elif sym == "bell":
            path = QPainterPath()
            path.moveTo(c.x() - u * 0.85, c.y() + u * 0.5)
            path.cubicTo(c.x() - u * 0.5, c.y() + u * 0.1, c.x() - u * 0.7, c.y() - u * 0.9, c.x(), c.y() - u * 0.9)
            path.cubicTo(c.x() + u * 0.7, c.y() - u * 0.9, c.x() + u * 0.5, c.y() + u * 0.1, c.x() + u * 0.85, c.y() + u * 0.5)
            path.closeSubpath()
            p.setBrush(QColor("#E8B23A"))
            p.drawPath(path)
            p.drawEllipse(QPointF(c.x(), c.y() + u * 0.72), u * 0.2, u * 0.2)
        elif sym == "star":
            pts = []
            for n in range(10):
                ang = math.radians(-90 + 36 * n)
                rr = u if n % 2 == 0 else u * 0.42
                pts.append(QPointF(c.x() + rr * math.cos(ang), c.y() + rr * math.sin(ang)))
            p.setBrush(QColor("#FFE27A"))
            p.drawPolygon(QPolygonF(pts))
        elif sym == "diamond":
            p.setBrush(QColor("#5FD6F2"))
            p.drawPolygon(QPolygonF([QPointF(c.x() - u * 0.55, c.y() - u * 0.7), QPointF(c.x() + u * 0.55, c.y() - u * 0.7),
                                     QPointF(c.x() + u, c.y() - u * 0.15), QPointF(c.x(), c.y() + u * 0.95),
                                     QPointF(c.x() - u, c.y() - u * 0.15)]))
            p.setBrush(alpha("#FFFFFF", 0.35))
            p.drawPolygon(QPolygonF([QPointF(c.x() - u * 0.55, c.y() - u * 0.7), QPointF(c.x(), c.y() - u * 0.15),
                                     QPointF(c.x() - u, c.y() - u * 0.15)]))
        else:                                                   # seven, drawn from two bars
            p.setBrush(QColor("#FF4B5C"))
            p.drawPolygon(QPolygonF([QPointF(c.x() - u * 0.75, c.y() - u * 0.9), QPointF(c.x() + u * 0.8, c.y() - u * 0.9),
                                     QPointF(c.x() + u * 0.8, c.y() - u * 0.55), QPointF(c.x() + u * 0.05, c.y() + u * 0.95),
                                     QPointF(c.x() - u * 0.4, c.y() + u * 0.95), QPointF(c.x() + u * 0.3, c.y() - u * 0.5),
                                     QPointF(c.x() - u * 0.75, c.y() - u * 0.5)]))


# --------------------------------------------------------------------------- #
# Daily spin: free coins once a day (the date comes from the internet)
# --------------------------------------------------------------------------- #
class Daily(Game):
    # (coins, keys) on each slice
    PRIZES = [(40, 0), (75, 0), (120, 0), (180, 0), (300, 0), (500, 0), (1200, 0), (0, 1)]      # as the server numbers them

    def __init__(self, page) -> None:
        super().__init__(page)
        self.angle = 0.0
        self._from = self._to = 0.0
        self._t0 = 0.0
        self.result = -1
        self.collect = None                      # the prize waiting for "Collect": (coins, keys)
        self.wallet.time_checked.connect(self._checked)

    def always_moving(self) -> bool:
        return True

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.wallet.check_time()

    def _checked(self) -> None:
        waiting = self.wallet.spin_waiting
        if waiting and self.collect is None and not self.busy:      # a prize from before was never collected
            self.result = int(waiting.get("slot", 0))
            self.collect = (int(waiting.get("won", 0)), int(waiting.get("won_keys", 0)))
            self.angle = (self.result + 0.5) * 360.0 / len(self.PRIZES)
        self.page.sync()
        self.update()

    def spin(self) -> None:
        if self.busy or self.waiting or self.collect is not None or self.wallet.daily_wait() != 0:
            return
        self.busy = True
        self.stake = 0
        self.ask("rb_spin", {}, self._rolled)

    def _rolled(self, ans: dict) -> None:
        self.result = int(ans.get("slot", 0))
        self._prize = (int(ans.get("won", 0)), int(ans.get("won_keys", 0)))
        self.wallet.spin_used()
        seg = 360.0 / len(self.PRIZES)
        self._from = self.angle % 360.0
        self._to = 360.0 * 5 + (self.result + 0.5 + RNG.uniform(-0.3, 0.3)) * seg
        self._t0 = time.monotonic()
        self.animate(5.0)
        QTimer.singleShot(4700, self._done)

    def _done(self) -> None:
        self.angle = self._to % 360.0
        self.collect = self._prize                       # shown, and kept by the server until collected
        sfx.play("on")
        self.busy = False
        self.page.sync()

    def take_prize(self) -> None:
        if self.collect is None or self.waiting:
            return
        coins, keys = self.collect

        def got(_ans: dict) -> None:
            self.collect = None
            self.wallet.spin_waiting = None
            self.econ.adjust(coins, keys)
            self.flash("+" + (coins_text(coins) if coins else f"{keys} " + (tr("key") if keys == 1 else tr("keys"))), WIN)
            sfx.play("on")
        self.ask("rb_spin_collect", {}, got)

    def buttons(self) -> list:
        if self.collect is not None:
            coins, keys = self.collect
            what = coins_text(coins) if coins else f"{keys} " + (tr("key") if keys == 1 else tr("keys"))
            return [(tr("Collect") + f"  +{what}", "primary", self.take_prize, not self.waiting)]
        wait = self.wallet.daily_wait()
        if wait is None:
            return [(tr("Try again"), "ghost", self.wallet.check_time, not self.wallet.checking())]
        return [(tr("Free spin"), "primary", self.spin, wait == 0 and not self.busy)]

    def draw(self, p: QPainter, r: QRectF, now: float) -> None:
        if self.busy:
            self.angle = self._from + (self._to - self._from) * ease_out((now - self._t0) / 4.6, 4)
        radius = min(r.width(), r.height()) / 2 - S(16)
        c = QPointF(r.center().x(), r.center().y() + S(4))
        n = len(self.PRIZES)
        seg = 360.0 / n
        box = QRectF(c.x() - radius, c.y() - radius, radius * 2, radius * 2)
        wait = self.wallet.daily_wait()
        ready = wait == 0 or self.busy or self.collect is not None
        p.setOpacity(1.0 if ready else 0.35)
        for i, (coins, keys) in enumerate(self.PRIZES):
            start = 90.0 - (i * seg - self.angle)
            worth = coins if coins else keys * 400                 # a key is shown about as rich as 400 coins
            col = mix(QColor("#182024"), QColor("#E8C26A"), 0.15 + 0.75 * (math.log(worth) - math.log(50)) / (math.log(1200) - math.log(50)))
            if keys:
                col = mix(QColor("#182024"), ui.accent, 0.55 + 0.15 * keys)
            p.setPen(QPen(QColor("#0A0D0E"), 1.4))
            p.setBrush(col)
            p.drawPie(box, int(start * 16), int(-seg * 16))
            mid = math.radians(start - seg / 2)
            tp = QPointF(c.x() + radius * 0.72 * math.cos(mid), c.y() - radius * 0.72 * math.sin(mid))
            p.setPen(QColor("#FFFFFF"))
            p.setFont(font(9.5, QFont.Weight.Bold))
            if keys:
                p.save()
                p.translate(tp.x() - (S(6) if keys > 1 else 0), tp.y())
                p.scale(S(13) / 20, S(13) / 20)
                draw_icon(p, "key", QColor("#FFFFFF"))
                p.restore()
                if keys > 1:
                    p.drawText(QRectF(tp.x() + S(2), tp.y() - S(9), S(16), S(18)), int(Qt.AlignmentFlag.AlignCenter), str(keys))
            else:
                p.drawText(QRectF(tp.x() - S(20), tp.y() - S(9), S(40), S(18)), int(Qt.AlignmentFlag.AlignCenter), str(coins))
        p.setOpacity(1.0)
        p.setPen(QPen(alpha("#FFFFFF", 0.14), 1.2))
        p.setBrush(QColor("#0A0D0E"))
        p.drawEllipse(c, radius * 0.42, radius * 0.42)
        mid_box = QRectF(c.x() - radius * 0.42, c.y() - S(12), radius * 0.84, S(24))
        if wait is None:
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(10, QFont.Weight.DemiBold))
            p.drawText(mid_box, int(Qt.AlignmentFlag.AlignCenter), "…" if self.wallet.checking() else tr("Offline"))
        elif wait > 0 and not self.busy:
            p.setPen(QColor(TEXT))
            p.setFont(font(12, QFont.Weight.Bold))
            p.drawText(mid_box, int(Qt.AlignmentFlag.AlignCenter), clock_text(wait))
        else:
            paint_coin(p, c, S(13))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FFFFFF"))
        p.drawPolygon(QPolygonF([QPointF(c.x() - S(7), c.y() - radius - S(9)), QPointF(c.x() + S(7), c.y() - radius - S(9)),
                                 QPointF(c.x(), c.y() - radius + S(6))]))


# --------------------------------------------------------------------------- #
# The page
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Dice: choose your chance, roll under it
# --------------------------------------------------------------------------- #
class Dice(Game):
    """Pick your chance to win. A number from 0 to 99 is rolled: below your chance wins. The lower the chance,
    the bigger the prize (3% for the house)."""
    CHANCES = [5, 10, 25, 50, 75, 90, 95]

    def __init__(self, page) -> None:
        super().__init__(page)
        self.choice = 3
        self.history: list = []                      # last rolls: (number, won)
        self.roll = -1
        self.won = False
        self._t0 = 0.0
        self._from = 50.0

    def chance(self) -> int:
        return self.CHANCES[self.choice]

    def mult(self) -> float:
        return math.floor(9700.0 / self.chance()) / 100

    def options(self):
        return [f"{c}%" for c in self.CHANCES], self.choice

    def set_option(self, i: int) -> None:
        if not self.busy:
            self.choice = i
            self.update()

    def play(self) -> None:
        if self.busy or self.waiting or not self.take():
            return
        self.ask("rb_dice", {"bet": self.stake, "chance": self.chance()}, self._rolled, once=True, refund=self.stake)

    def _rolled(self, ans: dict) -> None:
        self._from = float(self.roll if self.roll >= 0 else 50)
        self.roll, self.won, self._paid = int(ans["roll"]), bool(ans["win"]), int(ans["paid"])
        self._t0 = time.monotonic()
        QTimer.singleShot(1100, lambda r=self.roll, w=self.won: self.history.insert(0, (r, w)) or self.update())
        del self.history[11:]
        self.animate(1.6)
        QTimer.singleShot(1150, lambda: self.finish(self._paid))

    def buttons(self) -> list:
        return [(tr("Roll"), "primary", self.play, not self.busy)]

    def draw(self, p: QPainter, r: QRectF, now: float) -> None:
        chance = self.chance()
        bar = QRectF(r.left() + S(22), r.center().y() + S(8), r.width() - S(44), S(16))
        win_w = bar.width() * chance / 100
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha(LOSE, 0.35))
        p.drawRoundedRect(bar, S(8), S(8))
        p.setBrush(QColor(WIN))
        clip = QPainterPath()
        clip.addRoundedRect(bar, S(8), S(8))
        p.save()
        p.setClipPath(clip)
        p.drawRect(QRectF(bar.left(), bar.top(), win_w, bar.height()))
        p.restore()
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(9.5, QFont.Weight.DemiBold))
        for mark in (0, 25, 50, 75, 100):
            x = bar.left() + bar.width() * mark / 100
            p.drawText(QRectF(x - S(16), bar.bottom() + S(4), S(32), S(14)), int(Qt.AlignmentFlag.AlignCenter), str(mark))
        p.setPen(QColor(TEXT))
        p.setFont(font(26, QFont.Weight.ExtraBold))
        p.drawText(QRectF(r.left(), r.top() + S(22), r.width(), S(40)), int(Qt.AlignmentFlag.AlignCenter),
                   f"×{self.mult():g}")
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(11, QFont.Weight.DemiBold))
        bet = self.stake if self.busy else self.page.bet()
        p.drawText(QRectF(r.left(), r.top() + S(62), r.width(), S(18)), int(Qt.AlignmentFlag.AlignCenter),
                   tr("Win if the roll is under {n}", n=chance) + "  ·  " +
                   tr("{c}% chance", c=chance) + "  ·  " + tr("Win {n}", n=coins_text(int(bet * self.mult()))))
        if self.history:                                      # the last rolls, newest first
            x = r.left() + S(16)
            p.setFont(font(9.5, QFont.Weight.Bold))
            for val, won in self.history[:10]:
                chip = QRectF(x, r.bottom() - S(30), S(30), S(18))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha(WIN if won else LOSE, 0.22))
                p.drawRoundedRect(chip, S(9), S(9))
                p.setPen(QColor(WIN if won else LOSE))
                p.drawText(chip, int(Qt.AlignmentFlag.AlignCenter), str(val))
                x += S(34)
        if self.roll >= 0:                                    # the marker slides to the number rolled
            t = ease_out((now - self._t0) / 1.0, 4) if self._t0 else 1.0
            value = self._from + (self.roll - self._from) * t
            x = bar.left() + bar.width() * (value + 0.5) / 100
            landed = t >= 0.999
            col = QColor(WIN if self.won else LOSE) if landed else QColor("#FFFFFF")
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col)
            pin = QPainterPath()
            pin.moveTo(x, bar.top() - S(3))
            pin.lineTo(x - S(7), bar.top() - S(14))
            pin.lineTo(x + S(7), bar.top() - S(14))
            pin.closeSubpath()
            p.drawPath(pin)
            p.drawRoundedRect(QRectF(x - S(1.5), bar.top() - S(3), S(3), bar.height() + S(6)), S(1.5), S(1.5))
            p.setPen(col)
            p.setFont(font(13, QFont.Weight.ExtraBold))
            p.drawText(QRectF(x - S(24), bar.top() - S(36), S(48), S(20)), int(Qt.AlignmentFlag.AlignCenter),
                       str(int(round(value))))


# --------------------------------------------------------------------------- #
# Rocket: cash out before it blows up
# --------------------------------------------------------------------------- #
class Rocket(Game):
    """The multiplier climbs while the rocket flies. Cash out to win the bet times the multiplier; if it blows
    up first, the bet is lost. The moment it blows up is decided by the server when the round starts."""
    RATE = 0.10                                          # the multiplier is e^(RATE x seconds), as on the server
    TARGETS = [0, 1.5, 2, 3, 5, 10]                      # automatic cash-out (0 = by hand)

    def __init__(self, page) -> None:
        super().__init__(page)
        self.phase = "idle"                              # idle -> fly -> idle
        self._t0 = 0.0
        self.end_mult = 1.0
        self.crashed = False
        self.target = 0
        self.history: list = []
        self._poll = QTimer(self)
        self._poll.setInterval(700)
        self._poll.timeout.connect(self._look)

    def mult_now(self) -> float:
        if self.phase != "fly":
            return self.end_mult
        return math.floor(math.exp(self.RATE * (time.monotonic() - self._t0)) * 100) / 100

    def always_moving(self) -> bool:
        return self.phase == "fly"

    def options(self):
        return [tr("By hand") if t == 0 else f"×{t:g}" for t in self.TARGETS], self.target

    def set_option(self, i: int) -> None:
        if not self.busy:
            self.target = i
            self.update()

    def aim(self):
        t = self.TARGETS[self.target]
        return t or None

    def start(self) -> None:
        if self.busy or self.waiting or not self.take():
            return
        self.ask("rb_rocket", {"action": "start", "bet": self.stake, "target": self.aim()}, self._started,
                 refund=self.stake)

    def _started(self, ans: dict) -> None:
        if isinstance(ans.get("history"), list):
            self.history = [float(x) for x in ans["history"]]
        self._t0 = time.monotonic() - float(ans.get("age") or 0)
        self.phase, self.crashed, self.end_mult = "fly", False, 1.0
        self._frames.start()
        self._poll.start()

    def failed(self, message: str) -> None:
        if message == "Finish your round first":         # a flight from before: see how it ended
            return self.ask("rb_rocket", {"action": "cash", "bet": None, "target": None}, self._ended)
        if message == "Too early: wait for x1.20":
            return self.ctx.toast(tr(message), "warn")
        if self.phase != "fly":
            self.busy = False
        self.ctx.toast(tr(message), "warn")

    def _look(self) -> None:
        if self.phase == "fly" and not self.waiting:
            self.ask("rb_rocket", {"action": "look", "bet": None, "target": None},
                     lambda ans: None if ans.get("open") else self._ended(ans))

    def cash(self) -> None:
        if self.phase == "fly" and not self.waiting:
            if self.mult_now() < 1.2:
                return self.ctx.toast(tr("Too early: wait for x1.20"), "warn")
            self.ask("rb_rocket", {"action": "cash", "bet": None, "target": None}, self._ended)

    def _ended(self, ans: dict) -> None:
        if self.phase != "fly" and not self.busy:
            return
        self._poll.stop()
        self.crashed = bool(ans.get("crashed", True))
        self.end_mult = float(ans.get("crash") or 1.0) if self.crashed else float(ans.get("mult") or 1.0)
        if isinstance(ans.get("history"), list):
            self.history = [float(x) for x in ans["history"]]
        elif ans.get("crash"):
            self.history.insert(0, float(ans["crash"]))
        self.phase = "idle"
        self.animate(1.8)
        self.finish(int(ans.get("paid") or 0))

    def buttons(self) -> list:
        if self.phase == "fly":
            pay = int(self.stake * self.mult_now())
            return [(tr("Cash out") + f"  {coins_text(pay)}", "primary", self.cash,
                     not self.waiting and self.mult_now() >= 1.2)]
        return [(tr("Launch"), "primary", self.start, not self.busy)]

    def hideEvent(self, e) -> None:
        super().hideEvent(e)
        self._poll.stop()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        if self.phase == "fly":
            self._poll.start()
        elif not self.history and not self.waiting:
            self.econ.call("rb_rocket", {"action": "look", "bet": None, "target": None}, self._resume, hold=True)

    def _resume(self, ok: bool, ans) -> None:
        """Opening the game: the last flights, or a flight still in the air."""
        if not ok or not isinstance(ans, dict):
            return
        if isinstance(ans.get("history"), list):
            self.history = [float(x) for x in ans["history"]]
        if ans.get("open"):
            self.stake, self.busy = int(ans.get("bet") or 0), True
            self._started(ans)
            self.page.sync()
        self.update()

    def draw(self, p: QPainter, r: QRectF, now: float) -> None:
        flying = self.phase == "fly"
        m = self.mult_now()
        if flying:
            self.page.sync_labels()
        area = r.adjusted(S(22), S(54), -S(22), -S(22))
        p.setPen(QPen(alpha("#FFFFFF", 0.07), 1))
        for k in range(4):
            y = area.bottom() - area.height() * k / 3
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
        top = max(2.0, m * 1.15)                             # the view grows with the multiplier
        t_end = math.log(max(m, 1.0001)) / self.RATE
        span = max(4.0, t_end * 1.15)
        path = QPainterPath()
        steps = 48
        for k in range(steps + 1):
            t = t_end * k / steps
            val = math.exp(self.RATE * t)
            pt = QPointF(area.left() + area.width() * t / span,
                         area.bottom() - area.height() * (val - 1.0) / (top - 1.0))
            path.lineTo(pt) if k else path.moveTo(pt)
        col = QColor(LOSE) if (self.crashed and not flying) else ui.accent
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(alpha(col, 0.25), S(7)))
        p.drawPath(path)
        p.setPen(QPen(col, S(2.6)))
        p.drawPath(path)
        head = path.currentPosition()
        p.setPen(Qt.PenStyle.NoPen)
        if self.crashed and not flying:
            for k in range(8):
                ang = k * math.pi / 4
                p.setBrush(alpha("#FFB04D", 0.85))
                p.drawEllipse(QPointF(head.x() + S(11) * math.cos(ang), head.y() + S(11) * math.sin(ang)), S(2.6), S(2.6))
        else:
            p.setBrush(alpha(col, 0.3))
            p.drawEllipse(head, S(9), S(9))
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(head, S(4.2), S(4.2))
        aim = self.aim()
        if aim:                                              # the automatic cash-out line
            y = area.bottom() - area.height() * (aim - 1.0) / (top - 1.0)
            if y > area.top():
                p.setPen(QPen(alpha(GOLD_TEXT, 0.55), 1, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
                p.setPen(QColor(GOLD_TEXT))
                p.setFont(font(9.5, QFont.Weight.Bold))
                p.drawText(QRectF(area.right() - S(80), y - S(16), S(80), S(14)),
                           int(Qt.AlignmentFlag.AlignRight), tr("auto ×{m}", m=f"{aim:g}"))
        p.setPen(QColor(LOSE) if (self.crashed and not flying) else QColor(TEXT))
        p.setFont(font(28, QFont.Weight.ExtraBold))
        p.drawText(QRectF(r.left(), r.top() + S(10), r.width(), S(40)), int(Qt.AlignmentFlag.AlignCenter), f"×{m:.2f}")
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10, QFont.Weight.DemiBold))
        if not flying:
            hint = tr("Chance to reach ×{m}: {c}%", m=f"{aim:g}", c=int(96 / aim)) if aim else \
                tr("Cash out from ×1.20. The higher, the riskier.")
            p.drawText(QRectF(r.left(), r.top() + S(46), r.width(), S(16)), int(Qt.AlignmentFlag.AlignCenter), hint)
        x = r.left() + S(14)                                  # the last flights
        p.setFont(font(9, QFont.Weight.Bold))
        for c in self.history[:8]:
            col2 = QColor(WIN) if c >= 2 else (QColor(GOLD_TEXT) if c >= 1.2 else QColor(LOSE))
            chip = QRectF(x, r.bottom() - S(24), S(42), S(16))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(col2, 0.2))
            p.drawRoundedRect(chip, S(8), S(8))
            p.setPen(col2)
            p.drawText(chip, int(Qt.AlignmentFlag.AlignCenter), f"×{c:.2f}")
            x += S(46)


class Parking(QWidget):
    """The car park puzzle. The server picks the level and checks every move when the red car is out."""
    COLOURS = ["#4B6BFF", "#2ECC71", "#FF8A3D", "#9B5CFF", "#1ABC9C", "#FF5CB8", "#A8744C", "#2EC5FF", "#8CFF2E",
               "#B0B8C0", "#6A5ACD", "#00B3A4", "#E67E22", "#7F8C8D", "#16A085", "#D35400"]

    def __init__(self, page) -> None:
        super().__init__()
        self.page, self.ctx = page, page.ctx
        side = min(page.W, S(330))
        self.setFixedSize(page.W, side + S(22))
        self.cell = (side - S(16)) / 6
        self.ox = (page.W - self.cell * 6) / 2
        self.oy = S(8)
        self.layout_ = ""
        self.grid: list = []
        self.moves: list = []
        self.best = 0
        self.round = ""
        self.state = "wait"                       # wait -> play -> out -> sent
        self.drag = None                          # (car, start mouse, start offset, lo, hi)
        self.offset = 0.0
        self.result: dict = {}
        self.duel = False
        self._exit = 0.0
        self.setMouseTracking(True)
        self._t = QTimer(self)
        self._t.setInterval(16)
        self._t.timeout.connect(self._tick)

    # -- rounds
    def new(self) -> None:
        if self.state == "busy":
            return
        self.state = "busy"
        tier = int(getattr(self.ctx, "park_tier", 0) or 0) + 1

        def got(ok: bool, data) -> None:
            if not ok or not isinstance(data, dict):
                self.state = "wait"
                self.update()
                return self.ctx.toast(tr(str(data)), "warn")
            self.round, self.layout_, self.best = data["round"], data["layout"], int(data.get("best") or 0)
            self.restart()
        self.ctx.econ.call("rb_park_start", {"tier": tier}, got)

    def restart(self) -> None:
        if not self.layout_:
            return
        if self.state in ("out", "sent"):
            return None if self.duel else self.new()
        self.grid = list(self.layout_)
        self.moves, self.result, self.state, self.drag = [], {}, "play", None
        self.update()

    # -- the board
    def cars(self) -> dict:
        out: dict = {}
        for i, ch in enumerate(self.grid):
            if ch != ".":
                out.setdefault(ch, []).append(i)
        return out

    def _room(self, car: str, cells: list) -> tuple:
        """How far the car can slide back (negative) and forward."""
        horiz = cells[1] - cells[0] == 1
        step = 1 if horiz else 6
        lo = hi = 0
        while True:
            t = cells[0] - step * (lo + 1)
            if t < 0 or (horiz and t // 6 != cells[0] // 6) or self.grid[t] != ".":
                break
            lo += 1
        while True:
            t = cells[-1] + step * (hi + 1)
            if t > 35 or (horiz and t // 6 != cells[0] // 6) or self.grid[t] != ".":
                break
            hi += 1
        return horiz, -lo, hi

    def _cell_at(self, pos) -> int:
        c = int((pos.x() - self.ox) // self.cell)
        r = int((pos.y() - self.oy) // self.cell)
        return r * 6 + c if 0 <= c < 6 and 0 <= r < 6 else -1

    def mousePressEvent(self, e) -> None:
        e.accept()
        if self.state != "play" or e.button() != Qt.MouseButton.LeftButton:
            return
        i = self._cell_at(e.position())
        if i < 0 or self.grid[i] == ".":
            return
        car = self.grid[i]
        cells = self.cars()[car]
        horiz, lo, hi = self._room(car, cells)
        self.drag = (car, e.position(), horiz, lo, hi)
        self.offset = 0.0
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e) -> None:
        if self.drag is None:
            i = self._cell_at(e.position())
            self.setCursor(Qt.CursorShape.OpenHandCursor if self.state == "play" and i >= 0 and self.grid[i] != "."
                           else Qt.CursorShape.ArrowCursor)
            return
        car, start, horiz, lo, hi = self.drag
        d = (e.position().x() - start.x()) if horiz else (e.position().y() - start.y())
        self.offset = max(lo * self.cell, min(hi * self.cell, d))
        self.update()

    def mouseReleaseEvent(self, _e) -> None:
        if self.drag is None:
            return
        car, _start, horiz, _lo, _hi = self.drag
        d = int(round(self.offset / self.cell))
        self.drag, self.offset = None, 0.0
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if d:
            cells = self.cars()[car]
            step = 1 if horiz else 6
            for c in cells:
                self.grid[c] = "."
            for c in cells:
                self.grid[c + d * step] = car
            if self.moves and self.moves[-1]["c"] == car:          # the same car again: still one move
                self.moves[-1]["d"] += d
                if self.moves[-1]["d"] == 0:
                    self.moves.pop()
            else:
                self.moves.append({"c": car, "d": d})
            sfx.play("pick")
            if self.grid[16] == "A" and self.grid[17] == "A":
                self._out()
        self.update()

    def _out(self) -> None:
        self.state = "out"
        self._exit = time.monotonic()
        self._t.start()

        def got(ok: bool, data) -> None:
            self.state = "sent"
            if not ok:
                self.ctx.toast(tr(str(data)), "warn")
                data = {}
            self.result = data if isinstance(data, dict) else {}
            if int(self.result.get("paid") or 0):
                sfx.play("on")
            if self.duel:
                self.page.ctx.duels_data = None
                self.page.load_duels(quiet=True)
            self.update()
        self.ctx.econ.call("rb_park_finish", {"round": self.round, "moves": self.moves}, got)

    def _tick(self) -> None:
        self.update()
        if time.monotonic() - self._exit > 1.2:
            self._t.stop()

    def hideEvent(self, _e) -> None:
        self._t.stop()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cs, ox, oy = self.cell, self.ox, self.oy
        board = QRectF(ox, oy, cs * 6, cs * 6)
        p.setPen(QPen(alpha("#FFFFFF", 0.10), 1.2))
        p.setBrush(QColor("#0E1214"))
        p.drawRoundedRect(board.adjusted(-S(5), -S(5), S(5), S(5)), S(12), S(12))
        p.setPen(QPen(alpha("#FFFFFF", 0.05), 1))
        for k in range(1, 6):
            p.drawLine(QPointF(ox + k * cs, oy), QPointF(ox + k * cs, oy + 6 * cs))
            p.drawLine(QPointF(ox, oy + k * cs), QPointF(ox + 6 * cs, oy + k * cs))
        exit_r = QRectF(ox + 6 * cs, oy + 2 * cs + S(4), S(8), cs - S(8))           # the way out
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FF4B4B"))
        p.drawRoundedRect(exit_r, S(3), S(3))
        if not self.grid:
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(13, QFont.Weight.DemiBold))
            p.drawText(board, int(Qt.AlignmentFlag.AlignCenter), tr("Loading…"))
            return
        now = time.monotonic()
        for car, cells in sorted(self.cars().items()):
            horiz = cells[1] - cells[0] == 1
            r0, c0 = divmod(cells[0], 6)
            w = (len(cells) if horiz else 1) * cs
            h = (1 if horiz else len(cells)) * cs
            x, y = ox + c0 * cs, oy + r0 * cs
            if self.drag is not None and self.drag[0] == car:
                if horiz:
                    x += self.offset
                else:
                    y += self.offset
            if car == "A" and self.state in ("out", "sent"):
                x += min(1.0, (now - self._exit) / 1.0) ** 2 * cs * 3
            body = QRectF(x, y, w, h).adjusted(S(4), S(4), -S(4), -S(4))
            col = QColor("#FF3B3B") if car == "A" else QColor(self.COLOURS[(ord(car) - 66) % len(self.COLOURS)])
            g = QLinearGradient(body.topLeft(), body.bottomLeft())
            g.setColorAt(0, col.lighter(125))
            g.setColorAt(1, col.darker(115))
            p.setPen(QPen(col.darker(160), S(1.2)))
            p.setBrush(g)
            p.drawRoundedRect(body, S(9), S(9))
            p.setPen(Qt.PenStyle.NoPen)                              # windows of the car
            p.setBrush(QColor(0, 0, 0, 90))
            if horiz:
                p.drawRoundedRect(QRectF(body.right() - S(18), body.top() + S(6), S(9), body.height() - S(12)), S(3), S(3))
                p.drawRoundedRect(QRectF(body.left() + S(9), body.top() + S(6), S(7), body.height() - S(12)), S(3), S(3))
            else:
                p.drawRoundedRect(QRectF(body.left() + S(6), body.top() + S(9), body.width() - S(12), S(7)), S(3), S(3))
                p.drawRoundedRect(QRectF(body.left() + S(6), body.bottom() - S(18), body.width() - S(12), S(9)), S(3), S(3))
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        info = tr("Moves: {n}", n=len(self.moves)) + "  ·  " + tr("Best possible: {n}", n=self.best)
        p.drawText(QRectF(0, oy + 6 * cs + S(8), self.width(), S(16)), int(Qt.AlignmentFlag.AlignCenter), info)
        if self.state == "sent":
            res = self.result
            box = board.adjusted(cs * 0.6, cs * 1.8, -cs * 0.6, -cs * 1.8)
            p.setPen(QPen(alpha(GOLD_TEXT, 0.6), 1.2))
            p.setBrush(QColor(8, 10, 12, 235))
            p.drawRoundedRect(box, S(12), S(12))
            paid = int(res.get("paid") or 0)
            p.setPen(QColor(GOLD_TEXT if paid else TEXT_DIM))
            p.setFont(font(20, QFont.Weight.ExtraBold))
            p.drawText(QRectF(box.left(), box.top() + S(10), box.width(), S(30)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("Duel score sent") if res.get("duel") else ("+" + coins_text(paid) if paid else tr("No coins this time")))
            p.setPen(QColor(TEXT))
            p.setFont(font(11, QFont.Weight.DemiBold))
            text = tr("{n} moves (best possible: {b})", n=res.get("moves", len(self.moves)), b=self.best)
            if res.get("why") == "time":
                text = tr("Too fast to be real: no coins")
            p.drawText(QRectF(box.left(), box.top() + S(44), box.width(), S(18)), int(Qt.AlignmentFlag.AlignCenter), text)


class GamePicker(QWidget):
    """Which game: two rows of small buttons (one is lit)."""
    changed = pyqtSignal(int)

    def __init__(self, labels: list, index: int = 0) -> None:
        super().__init__()
        self._index = index
        self.buttons: list = []
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(S(4))
        per_row = (len(labels) + 1) // 2
        for i, text in enumerate(labels):
            b = Button(text, "primary" if i == index else "ghost", 26)
            b.clicked.connect(lambda _=False, n=i: self._pick(n))
            grid.addWidget(b, i // per_row, i % per_row)
            self.buttons.append(b)
        self.setFixedHeight(S(26) * 2 + S(4))

    def index(self) -> int:
        return self._index

    def set_index(self, i: int) -> None:
        self._index = i
        for n, b in enumerate(self.buttons):
            b.set_kind("primary" if n == i else "ghost")

    def _pick(self, i: int) -> None:
        if i != self._index:
            sfx.play("pick")
            self.set_index(i)
            self.changed.emit(i)


class BetBox(QWidget):
    """The bet: a coin and an amount."""

    def __init__(self, page) -> None:
        super().__init__()
        self.page = page
        self.setFixedHeight(S(34))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha("#FFFFFF", 0.10), 1))
        p.setBrush(alpha("#FFFFFF", 0.04))
        p.drawRoundedRect(r, S(10), S(10))
        text = coins_text(self.page.bet())
        p.setFont(font(14, QFont.Weight.Bold))
        tw = p.fontMetrics().horizontalAdvance(text)
        x = r.center().x() - (tw + S(22)) / 2
        paint_coin(p, QPointF(x + S(8), r.center().y()), S(7))
        p.setPen(QColor(TEXT))
        p.drawText(QRectF(x + S(22), r.top(), tw + S(4), r.height()), int(Qt.AlignmentFlag.AlignVCenter), text)


class KeyCard(QWidget):
    """Your keys (they open badge cases in the Shop) and how far you are from the next one."""

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self.setFixedHeight(S(64))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        ctx.wallet.changed.connect(self.update)

    def paintEvent(self, _e) -> None:
        w = self.ctx.wallet
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha("#FFFFFF", 0.08), 1))
        p.setBrush(alpha("#FFFFFF", 0.04))
        p.drawRoundedRect(r, S(11), S(11))
        c = QPointF(r.left() + S(24), r.top() + S(22))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha(ui.accent, 0.16))
        p.drawEllipse(c, S(13), S(13))
        p.save()
        p.translate(c)
        p.scale(S(15) / 20, S(15) / 20)
        draw_icon(p, "key", ui.accent)
        p.restore()
        p.setPen(QColor(TEXT))
        p.setFont(font(13, QFont.Weight.Bold))
        p.drawText(QRectF(r.left() + S(46), r.top() + S(10), r.width() / 2, S(24)), int(Qt.AlignmentFlag.AlignVCenter),
                   tr("Keys"))
        p.setFont(font(13, QFont.Weight.Bold))
        p.drawText(QRectF(r.center().x(), r.top() + S(10), r.width() / 2 - S(12), S(24)),
                   int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), str(w.keys()))
        bar = QRectF(r.left() + S(46), r.top() + S(38), r.width() - S(58), S(5))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.08))
        p.drawRoundedRect(bar, bar.height() / 2, bar.height() / 2)
        p.setBrush(ui.accent)
        ec = self.ctx.econ
        every = max(1, int(ec.cfg.get("key_every_min", 60)))
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), max(bar.height(), bar.width() * min(1.0, ec.key_min / every)), bar.height()),
                          bar.height() / 2, bar.height() / 2)
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10, QFont.Weight.DemiBold))
        text = tr("1 key for every hour with Rubenium")
        p.drawText(QRectF(bar.left(), bar.bottom() + S(2), bar.width(), S(16)), int(Qt.AlignmentFlag.AlignVCenter), text)


class GameTile(QWidget):
    """One game in the lobby: a small picture and its name. Click to go straight to it."""

    def __init__(self, page, index: int, name: str) -> None:
        super().__init__()
        self.page, self.index, self.name = page, index, name
        self.setFixedHeight(S(76))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = Tween(self, on_change=self.update)

    def enterEvent(self, _e) -> None:
        self._hover.to(1.0, 140)

    def leaveEvent(self, _e) -> None:
        self._hover.to(0.0, 220)

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.page.enter(self.index)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self._hover.level
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        p.setPen(QPen(mix(alpha("#FFFFFF", 0.08), ui.accent, h * 0.8), 1.2))
        p.setBrush(QColor("#0C1113"))
        p.drawRoundedRect(r, S(11), S(11))
        art = QPointF(r.left() + S(34), r.center().y())
        p.setPen(Qt.PenStyle.NoPen)
        if self.index == 0:                                    # two cards
            for k, (dx, rot) in enumerate(((-S(6), -10), (S(6), 8))):
                p.save()
                p.translate(art.x() + dx, art.y())
                p.rotate(rot)
                p.setBrush(QColor("#F4F5F6") if k else QColor("#151B1F"))
                p.setPen(QPen(alpha(ui.accent, 0.7) if not k else alpha("#000000", 0.4), 1))
                p.drawRoundedRect(QRectF(-S(10), -S(14), S(20), S(28)), S(3), S(3))
                if k:
                    p.setPen(QColor("#D8314A"))
                    p.setFont(font(10, QFont.Weight.Bold))
                    p.drawText(QRectF(-S(10), -S(14), S(20), S(28)), int(Qt.AlignmentFlag.AlignCenter), "A")
                p.restore()
        elif self.index == 1:                                  # pins and a ball
            p.setBrush(alpha("#FFFFFF", 0.55))
            for i in range(4):
                for j in range(i + 2):
                    p.drawEllipse(QPointF(art.x() + (j - (i + 1) / 2) * S(9), art.y() - S(13) + i * S(8)), S(1.6), S(1.6))
            p.setBrush(ui.accent)
            p.drawEllipse(QPointF(art.x() + S(4), art.y() - S(1)), S(3.6), S(3.6))
            for k in range(5):
                p.setBrush(QColor("#E8C26A") if k in (0, 4) else QColor("#2A3238"))
                p.drawRoundedRect(QRectF(art.x() - S(22) + k * S(9), art.y() + S(15), S(8), S(5)), S(1.5), S(1.5))
        elif self.index == 2:                                  # cards and a gem
            for i in range(9):
                cell = QRectF(art.x() - S(17) + (i % 3) * S(12), art.y() - S(17) + (i // 3) * S(12), S(10), S(10))
                p.setBrush(alpha(ui.accent, 0.85) if i == 4 else QColor("#1A2125"))
                p.drawRoundedRect(cell, S(2.5), S(2.5))
        elif self.index == 4:                                  # a die
            p.setBrush(QColor("#F4F5F6"))
            p.drawRoundedRect(QRectF(art.x() - S(14), art.y() - S(14), S(28), S(28)), S(6), S(6))
            p.setBrush(QColor("#14181A"))
            for dx, dy in ((-7, -7), (7, 7), (0, 0), (7, -7), (-7, 7)):
                p.drawEllipse(QPointF(art.x() + S(dx), art.y() + S(dy)), S(2.3), S(2.3))
        elif self.index == 5:                                  # a climbing line
            line = QPainterPath()
            line.moveTo(art.x() - S(20), art.y() + S(14))
            line.cubicTo(art.x() - S(4), art.y() + S(12), art.x() + S(8), art.y() + S(2), art.x() + S(18), art.y() - S(15))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(ui.accent, S(2.4)))
            p.drawPath(line)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(QPointF(art.x() + S(18), art.y() - S(15)), S(3.4), S(3.4))
        else:                                                  # 777
            p.setPen(QColor("#FF4B5C"))
            p.setFont(font(16, QFont.Weight.ExtraBold))
            p.drawText(QRectF(art.x() - S(26), art.y() - S(14), S(52), S(28)), int(Qt.AlignmentFlag.AlignCenter), "777")
        p.setPen(mix(QColor(TEXT_DIM), QColor(TEXT), 0.6 + 0.4 * h))
        p.setFont(font(12.5, QFont.Weight.Bold))
        p.drawText(QRectF(r.left() + S(64), r.top(), r.width() - S(70), r.height()), int(Qt.AlignmentFlag.AlignVCenter),
                   tr(self.name))


class DailyRow(QWidget):
    """The free daily spin: ready, or how long until it is."""

    def __init__(self, page) -> None:
        super().__init__()
        self.page, self.ctx = page, page.ctx
        self.setFixedHeight(S(40))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self.update)
        self.ctx.wallet.time_checked.connect(self.update)

    def showEvent(self, _e) -> None:
        self._tick.start()
        if self.ctx.wallet.daily_wait() is None:
            self.ctx.wallet.check_time()

    def hideEvent(self, _e) -> None:
        self._tick.stop()

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.page.enter(6)

    def paintEvent(self, _e) -> None:
        w = self.ctx.wallet
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        wait = w.daily_wait()
        ready = wait == 0
        p.setPen(QPen(alpha(GOLD_TEXT, 0.6) if ready else alpha("#FFFFFF", 0.08), 1.2))
        p.setBrush(alpha(GOLD_TEXT, 0.08) if ready else alpha("#FFFFFF", 0.04))
        p.drawRoundedRect(r, S(11), S(11))
        paint_coin(p, QPointF(r.left() + S(20), r.center().y()), S(8))
        p.setPen(QColor(TEXT))
        p.setFont(font(12.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(r.left() + S(36), r.top(), r.width() * 0.6, r.height()), int(Qt.AlignmentFlag.AlignVCenter),
                   tr("Free spin"))
        if wait is None:
            text, col = ("…" if w.checking() else tr("Offline")), TEXT_DIM
        elif ready:
            text, col = tr("Ready"), GOLD_TEXT
        else:
            text, col = clock_text(wait), TEXT_DIM
        p.setPen(QColor(col))
        p.setFont(font(12, QFont.Weight.Bold))
        p.drawText(r.adjusted(0, 0, -S(12), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), text)


class QuestRow(QWidget):
    """One quest: what to do, how far you are, and the reward (a Claim button once it is done)."""

    def __init__(self, page, q: dict) -> None:
        super().__init__()
        self.q = q
        self.setFixedHeight(S(46))
        lay = hbox(self, 0, (0, 0, 8, 0))
        lay.addStretch(1)
        done = int(q.get("progress", 0)) >= int(q.get("goal", 1))
        if done and not q.get("claimed"):
            b = Button(tr("Claim") + f"  +{coins_text(int(q['reward']))}", "primary", 30)
            b.setFixedWidth(max(S(100), b.sizeHint().width()))
            b.clicked.connect(lambda: page.claim(q["quest"]))
            lay.addWidget(b)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        q = self.q
        r = QRectF(self.rect()).adjusted(0.5, 2, -0.5, -2)
        goal, prog = int(q.get("goal", 1)), int(q.get("progress", 0))
        done, claimed = prog >= goal, bool(q.get("claimed"))
        p.setPen(QPen(alpha(GOLD_TEXT, 0.5) if (done and not claimed) else alpha("#FFFFFF", 0.08), 1.1))
        p.setBrush(alpha("#FFFFFF", 0.04))
        p.drawRoundedRect(r, S(10), S(10))
        p.setOpacity(0.45 if claimed else 1.0)
        p.setPen(QColor(TEXT))
        p.setFont(font(12, QFont.Weight.DemiBold))
        text = tr(GamesPage.QUESTS.get(q.get("quest"), ""), n=coins_text(goal))
        p.drawText(QRectF(r.left() + S(12), r.top() + S(5), r.width() * 0.62, S(18)), int(Qt.AlignmentFlag.AlignVCenter), text)
        bar = QRectF(r.left() + S(12), r.bottom() - S(13), r.width() * 0.56, S(5))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.08))
        p.drawRoundedRect(bar, S(2.5), S(2.5))
        p.setBrush(QColor(GOLD_TEXT) if done else ui.accent)
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), max(bar.height(), bar.width() * min(1.0, prog / max(1, goal))),
                                 bar.height()), S(2.5), S(2.5))
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10, QFont.Weight.DemiBold))
        if claimed or not done:                       # (when it can be claimed, the button sits here)
            p.drawText(QRectF(bar.right() + S(8), bar.top() - S(6), S(90), S(16)), int(Qt.AlignmentFlag.AlignVCenter),
                       f"{coins_text(prog)} / {coins_text(goal)}")
        if claimed or not done:
            right = r.adjusted(0, 0, -S(12), 0)
            if claimed:
                p.drawText(right, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), tr("Done"))
            else:
                paint_coin(p, QPointF(right.right() - p.fontMetrics().horizontalAdvance(coins_text(int(q["reward"]))) - S(12),
                                      right.center().y()), S(6))
                p.setPen(QColor(GOLD_TEXT))
                p.setFont(font(11.5, QFont.Weight.Bold))
                p.drawText(right, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), coins_text(int(q["reward"])))


class GamesPage(Page):
    """The lobby (normal size) and, once you go in, the casino (shown bigger)."""
    key = "games"
    NAMES = ["Blackjack", "Plinko", "Bombs", "Slots", "Dice", "Rocket", "Free spin"]

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self._bet = 2                                # index in BETS
        self.game = None
        lay = vbox(self, 8)
        if not ctx.casino:
            if getattr(ctx, "casino_ask", None) is not None and not ctx.wallet.warned():
                return self._warning(lay)
            if getattr(ctx, "quests_open", False):
                return self._quests(lay)
            if getattr(ctx, "mini_open", False):
                return self._mini(lay)
            if getattr(ctx, "park_open", False):
                return self._park(lay)
            sub = getattr(ctx, "games_sub", None)
            if sub in ("memory", "duels", "duel_run", "scratch"):
                from .hub import server_wait
                if ctx.econ.server_old:
                    self._back_bar(lay, tr({"memory": "Memory", "scratch": "Scratch card"}.get(sub, "Duels")))
                    server_wait(ctx, lay, self.W)
                    return
            if sub == "minigames":
                return build_minigames(self, lay)
            if sub == "memory":
                return self._memory(lay)
            if sub == "duels":
                return build_duels(self, lay)
            if sub == "duel_run":
                return self._duel_run(lay)
            if sub == "scratch":
                return self._scratch(lay)
            return self._lobby(lay)
        self._casino(lay)

    # -- the lobby
    def _lobby(self, lay) -> None:
        quests = Button(tr("Quests"), "primary", 36, icon="spark")      # across the top
        quests.clicked.connect(lambda: self._show_quests(True))
        lay.addWidget(quests)
        lay.addWidget(CoinBar(self.ctx))
        lay.addWidget(KeyCard(self.ctx))
        from .hub import StreakRow
        if not self.ctx.econ.server_old:
            lay.addWidget(StreakRow(self))
        lay.addWidget(DailyRow(self))
        lay.addWidget(ScratchRow(self))
        line = hbox(spacing=6)
        earn = BigCard(tr("Earn coins"), tr("3 free mini games"), "spark",
                       ("#35E0A1", "#12806A"), lambda: self.open_sub("minigames"))
        duel = BigCard(tr("Duels"), tr("1 vs 1 with friends"), "shield",
                       ("#FF5C6C", "#8A1F7A"), lambda: self.open_sub("duels"))
        line.addWidget(earn, 1)
        line.addWidget(duel, 1)
        lay.addLayout(line)
        lay.addWidget(heading(tr("Casino")))
        grid = QWidget()
        gl = QGridLayout(grid)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(S(6))
        for i, name in enumerate(self.NAMES[:6]):
            gl.addWidget(GameTile(self, i, name), i // 2, i % 2)
        lay.addWidget(grid)
        go = Button(tr("Enter casino"), "primary", 40)
        go.clicked.connect(lambda: self.enter(None))
        lay.addWidget(go)

    # -- quests: small goals for coins, counted by the server
    QUESTS = {"h_rounds": "Play {n} casino rounds", "h_mini": "Play mini games {n} times", "h_bet": "Bet {n} coins in the casino",
              "h_win": "Win {n} coins in the casino", "d_rounds": "Play {n} casino rounds", "d_case": "Open a case",
              "d_mini": "Play mini games {n} times", "d_spin": "Collect a free spin",
              "w_rounds": "Play {n} casino rounds", "w_cases": "Open {n} cases", "w_won": "Win {n} coins in the casino"}

    def _show_mini(self, on: bool) -> None:
        sfx.play("pick")
        self.ctx.mini_open = on
        self.ctx.games_sub = None if on else "minigames"
        self.ctx.reload_page()

    def _mini(self, lay) -> None:
        top = hbox(spacing=8)
        back = IconButton("back", 32, tip=tr("Back"))
        top.addWidget(back)
        top.addWidget(Label(tr("Beat Tap"), 16, bold=True), 1)
        lay.addLayout(top)
        lay.addWidget(CoinBar(self.ctx))
        from .hub import server_wait
        if server_wait(self.ctx, lay, self.W):
            return
        mode = int(getattr(self.ctx, "tap_mode", 0) or 0)
        modes = Segmented([tr(n) for _k, n, _d in TAP_MODES], mode)
        modes.changed.connect(lambda i: (setattr(self.ctx, "tap_mode", i), self.ctx.reload_page()))
        lay.addWidget(modes)
        lay.addWidget(Label(tr(TAP_MODES[mode][2]), 10.5, TEXT_DIM))
        self.beat = BeatRush(self, lambda _r: (self.beat_btn.setEnabled(True), self.beat_btn.set_text(tr("Play again"))))
        back.clicked.connect(lambda: (self.beat.abort(), self._show_mini(False)))
        lay.addWidget(self.beat)
        self.beat_btn = Button(tr("Start"), "primary", 38)
        self.beat_btn.clicked.connect(lambda: (self.beat_btn.setEnabled(False), self.beat.start()))
        lay.addWidget(self.beat_btn)
        lay.addWidget(Label(tr("Four lanes, about 40 seconds, faster and faster. Hits in a row build a combo. 12 to 50 coins "
                               "a round; after 6 rounds in 2 hours it pays less (150 every 2 hours at most)."), 10.5, TEXT_DIM,
                            wrap_w=self.W))

    # -- 2.4: sub-screens (Memory, duels, scratch card)
    def open_sub(self, name) -> None:
        sfx.play("pick")
        for flag in ("quests_open", "mini_open", "park_open"):
            setattr(self.ctx, flag, False)
        self.ctx.games_sub = name
        self.ctx.reload_page()

    def _back_bar(self, lay, title: str, on_back=None) -> None:
        top = hbox(spacing=8)
        back = IconButton("back", 32, tip=tr("Back"))
        back.clicked.connect(on_back or (lambda: self.open_sub(None)))
        top.addWidget(back)
        top.addWidget(Label(title, 16, bold=True), 1)
        lay.addLayout(top)
        lay.addWidget(CoinBar(self.ctx))

    def _memory(self, lay) -> None:
        self._back_bar(lay, tr("Memory"), lambda: self.open_sub("minigames"))
        tier = int(getattr(self.ctx, "mem_tier", 0) or 0)
        seg = Segmented([tr("Easy"), tr("Medium"), tr("Hard")], tier)
        lay.addWidget(seg)
        style = Segmented([tr(n) for _k, n in MEM_THEMES], int(getattr(self.ctx, "mem_theme", 0) or 0))
        lay.addWidget(style)
        self.mem = MemoryGame(self)
        style.changed.connect(lambda i: (setattr(self.ctx, "mem_theme", i), self.mem.update()))
        seg.changed.connect(lambda i: (setattr(self.ctx, "mem_tier", i), self.mem.start()))
        lay.addWidget(self.mem)
        go = Button(tr("New game"), "primary", 36)
        go.clicked.connect(self.mem.start)
        lay.addWidget(go)
        lay.addWidget(Label(tr("Turn two cards: same picture, they stay. Easy 16 cards 12-30, Medium 20 cards 18-40, "
                               "Hard 24 cards 25-55 coins: fewer flips pay more. 150 every 2 hours at most."),
                            10.5, TEXT_DIM, wrap_w=self.W))
        QTimer.singleShot(50, self.mem.start)

    def _scratch(self, lay) -> None:
        self._back_bar(lay, tr("Scratch card"))
        card = ScratchCard(self)
        lay.addWidget(card)
        lay.addWidget(Label(tr("One card every 12 hours. Scratch it with the mouse: hard at first, then easier and easier. "
                               "The colour shows how lucky you were: Common or Rare give coins, Epic 1 key, Legendary 2 keys, "
                               "Mythic 2 500 coins."), 10.5, TEXT_DIM, wrap_w=self.W))

    def load_duels(self, quiet: bool = False) -> None:
        ctx = self.ctx

        def got(ok: bool, data) -> None:
            if ok and isinstance(data, list) and data != getattr(ctx, "duels_data", None):
                ctx.duels_data = data
                ctx.econ.refresh()                      # a duel ended: the pot (or the bet back) is in the balance
                if ctx.window.current == "games" and getattr(ctx, "games_sub", None) == "duels":
                    ctx.reload_page()

        def friends(ok: bool, data) -> None:
            if ok and isinstance(data, list):
                rows = [{"name": f.get("username") or f.get("name"), "online": f.get("online")} for f in data
                        if f.get("state", "friend") == "friend" and (f.get("username") or f.get("name"))]
                rows.sort(key=lambda f: (not f.get("online"), str(f["name"]).lower()))
                if rows != getattr(ctx, "duel_friends", None):
                    ctx.duel_friends = rows
                    if ctx.window.current == "games" and getattr(ctx, "games_sub", None) == "duels":
                        ctx.reload_page()
        ctx.econ.call("rb_duels", {}, got)
        if not quiet or getattr(ctx, "duel_friends", None) is None:
            ctx.online.ask("rb_friends_list", {}, friends)

    def duel_answer(self, did: str, yes: bool) -> None:
        def done(ok: bool, data) -> None:
            if not ok:
                return self.ctx.toast(tr(str(data)), "warn")
            sfx.play("on" if yes else "off")
            self.load_duels()
        self.ctx.econ.call("rb_duel_answer", {"duel": did, "yes": yes}, done)

    def duel_play(self, d: dict) -> None:
        sent = time.monotonic()

        def done(ok: bool, data) -> None:
            if not ok or not isinstance(data, dict):
                return self.ctx.toast(tr(str(data)), "warn")
            self.ctx.duel_run = dict(data, id=d["id"], other=d.get("other"), sent=sent)
            self.open_sub("duel_run")
        self.ctx.econ.call("rb_duel_play", {"duel": d["id"]}, done)

    def _duel_run(self, lay) -> None:
        run = getattr(self.ctx, "duel_run", None) or {}
        game, data = run.get("game"), run.get("data") or {}
        self._back_bar(lay, tr("Duel vs {name}", name=run.get("other", "?")), lambda: self.open_sub("duels"))

        def ended(_res) -> None:
            self.ctx.duels_data = None
            self.load_duels(quiet=True)
        if game == "tap":
            w = BeatRush(self, ended)
            lay.addWidget(w)
            QTimer.singleShot(300, lambda: w.begin(data, run.get("sent", time.monotonic()), duel=True))
        elif game == "memory":
            w = MemoryGame(self, ended)
            lay.addWidget(w)
            w.begin(data, duel=True)
        elif game == "park":
            self.park = w = Parking(self)
            w.round, w.layout_, w.best = data.get("round", ""), data.get("layout", ""), int(data.get("best") or 0)
            w.duel = True
            lay.addWidget(w)
            again = Button(tr("Start over"), "ghost", 34)
            again.clicked.connect(w.restart)
            lay.addWidget(again)
            QTimer.singleShot(30, w.restart)
        lay.addWidget(Label(tr("One try. Your score is sent when you finish; the winner is shown in Duels."), 10.5,
                            TEXT_DIM, wrap_w=self.W))

    def _show_park(self, on: bool) -> None:
        sfx.play("pick")
        self.ctx.park_open = on
        self.ctx.games_sub = None if on else "minigames"
        self.ctx.reload_page()

    def _park(self, lay) -> None:
        top = hbox(spacing=8)
        back = IconButton("back", 32, tip=tr("Back"))
        top.addWidget(back)
        top.addWidget(Label(tr("Parking"), 16, bold=True), 1)
        lay.addLayout(top)
        lay.addWidget(CoinBar(self.ctx))
        tier = int(getattr(self.ctx, "park_tier", 0) or 0)
        seg = Segmented([tr("Easy"), tr("Medium"), tr("Hard")], tier)
        lay.addWidget(seg)
        self.park = Parking(self)
        seg.changed.connect(lambda i: (setattr(self.ctx, "park_tier", i), self.park.new()))
        back.clicked.connect(lambda: self._show_park(False))
        lay.addWidget(self.park)
        line = hbox(spacing=6)
        again = Button(tr("Start over"), "ghost", 34)
        again.clicked.connect(self.park.restart)
        new = Button(tr("New puzzle"), "primary", 34)
        new.clicked.connect(self.park.new)
        line.addWidget(again, 1)
        line.addWidget(new, 1)
        lay.addLayout(line)
        lay.addWidget(Label(tr("Drag the cars along their lane to make way, then drive the red car out on the right. "
                               "Easy 12-25, Medium 18-38, Hard 30-50 coins: fewer moves pay more. 150 every 2 hours at most."),
                            10.5, TEXT_DIM, wrap_w=self.W))
        QTimer.singleShot(50, self.park.new)

    def _show_quests(self, on: bool) -> None:
        sfx.play("pick")
        self.ctx.quests_open = on
        self.ctx.games_sub = None
        self.ctx.reload_page()

    def _quests(self, lay) -> None:
        ctx = self.ctx
        top = hbox(spacing=8)
        back = IconButton("back", 32, tip=tr("Back"))
        back.clicked.connect(lambda: self._show_quests(False))
        top.addWidget(back)
        top.addWidget(Label(tr("Quests"), 16, bold=True), 1)
        lay.addLayout(top)
        lay.addWidget(CoinBar(ctx))
        data = getattr(ctx, "quests_data", None)
        if data is None:
            lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
        else:
            for kind, title in (("hour", tr("This hour")), ("day", tr("Today")), ("week", tr("This week"))):
                rows = [x for x in data if x.get("kind") == kind]
                if not rows:
                    continue
                left = int(rows[0].get("left") or 0)
                head = hbox(spacing=6)
                head.addWidget(Label(title.upper(), 10, TEXT_DIM, weight=QFont.Weight.Bold), 1)
                head.addWidget(Label(tr("New in {t}", t=clock_text(left)), 10, TEXT_FAINT))
                lay.addLayout(head)
                for q in rows:
                    lay.addWidget(QuestRow(self, q))
        ctx.econ.call("rb_quests", {}, self._got_quests)

    def _got_quests(self, ok: bool, data) -> None:
        if ok and isinstance(data, list) and data != getattr(self.ctx, "quests_data", None):
            self.ctx.quests_data = data
            if self.ctx.window.current == "games" and getattr(self.ctx, "quests_open", False):
                self.ctx.reload_page()

    def claim(self, quest: str) -> None:
        def done(ok: bool, data) -> None:
            if ok:
                sfx.play("on")
                self.ctx.toast("+" + coins_text(int(data.get("paid", 0))))
                self.ctx.quests_data = None
                if self.ctx.window.current == "games" and getattr(self.ctx, "quests_open", False):
                    self.ctx.reload_page()
            else:
                self.ctx.toast(tr(str(data)), "warn")
        self.ctx.econ.call("rb_quest_claim", {"which": quest}, done)

    def enter(self, game) -> None:
        sfx.play("pick")
        if not self.ctx.wallet.warned():
            self.ctx.casino_ask = game
            return self.ctx.reload_page()
        self.ctx.enter_casino(game)

    # -- first time: a plain warning to accept
    def _warning(self, lay) -> None:
        lay.addSpacing(S(6))
        lay.addWidget(Label(tr("Before you play"), 16, bold=True))
        for text in ("These games use Rubenium coins only. Coins are not money: they cannot be bought, sold or cashed out.",
                     "The odds favour the house. Over time you lose more than you win.",
                     "Gambling with real money can be addictive and is for adults only. If it stops being fun, stop."):
            lay.addWidget(Label(tr(text), 12.5, TEXT, wrap_w=self.W))
        lay.addSpacing(S(6))
        ok = Button(tr("I understand"), "primary", 38)
        ok.clicked.connect(self._accept)
        lay.addWidget(ok)

    def _accept(self) -> None:
        self.ctx.wallet.accept_warning()
        game, self.ctx.casino_ask = self.ctx.casino_ask, None
        self.ctx.enter_casino(game)

    # -- the casino
    def _casino(self, lay) -> None:
        ctx = self.ctx
        top = hbox(spacing=6)
        back = IconButton("back", 40, tip=tr("Back"))
        back.clicked.connect(ctx.leave_casino)
        self.back = back
        top.addWidget(back)
        top.addWidget(CoinBar(ctx, keys=True), 1)
        lay.addLayout(top)
        which = ctx.cfg["game"] if 0 <= ctx.cfg["game"] < len(self.NAMES) else 0
        self.seg = GamePicker([tr(n) for n in self.NAMES], which)
        self.seg.changed.connect(self._choose)
        lay.addWidget(self.seg)
        self.games = [Blackjack(self), Plinko(self), Bombs(self), Slots(self), Dice(self), Rocket(self), Daily(self)]
        for g in self.games:
            g.setVisible(False)
            lay.addWidget(g)
        controls = QWidget()                         # same height for every game: the card never jumps
        controls.setFixedHeight(S(76))
        cl = vbox(controls, 8)
        self.opts = []
        for g in self.games:
            spec = g.options()
            seg = None
            if spec:
                seg = Segmented(spec[0], spec[1])
                seg.changed.connect(lambda i, game=g: (game.set_option(i), self.sync()))
                seg.hide()
                cl.addWidget(seg)
            self.opts.append(seg)
        self.bet_row = QWidget()
        self.bet_row.setFixedHeight(S(34))
        br = hbox(self.bet_row, 6)
        self.b_less, self.b_more, self.b_max = Button("−", "ghost", 34), Button("+", "ghost", 34), Button(tr("Max"), "ghost", 34)
        for b, w in ((self.b_less, 44), (self.b_more, 44), (self.b_max, 62)):
            b.setFixedWidth(S(w))
        self.bet_box = BetBox(self)
        self.b_less.clicked.connect(lambda: self._step(-1))
        self.b_more.clicked.connect(lambda: self._step(1))
        self.b_max.clicked.connect(self._max)
        br.addWidget(self.b_less)
        br.addWidget(self.bet_box, 1)
        br.addWidget(self.b_more)
        br.addWidget(self.b_max)
        cl.addStretch(1)
        cl.addWidget(self.bet_row)
        lay.addWidget(controls)
        self.actions = QWidget()
        self.actions.setFixedHeight(S(38))
        self.act_lay = hbox(self.actions, 6)
        self.act_buttons: list = []
        lay.addWidget(self.actions)
        self._choose(which)
        ctx.wallet.changed.connect(self.sync)

    # -- bet
    def bet(self) -> int:
        """The bet, never more than you have."""
        bal = self.ctx.wallet.balance()
        want = BETS[self._bet]
        if self.game is not None and self.game.busy and not isinstance(self.game, Plinko):
            return self.game.stake
        return want if want <= bal else max([b for b in BETS if b <= bal], default=0)

    def _step(self, d: int) -> None:
        bal = self.ctx.wallet.balance()
        i = max(0, min(len(BETS) - 1, self._bet + d))
        while i > 0 and BETS[i] > bal:
            i -= 1
        if i != self._bet:
            self._bet = i
            sfx.play("pick")
        self.sync()

    def _max(self) -> None:
        bal = self.ctx.wallet.balance()
        self._bet = max([i for i, b in enumerate(BETS) if b <= bal], default=0)
        sfx.play("pick")
        self.sync()

    # -- which game
    def _choose(self, i: int) -> None:
        if self.game is not None and self.game.busy:              # finish the round first
            return self.seg.set_index(self.games.index(self.game))
        self.ctx.cfg["game"] = i
        for n, g in enumerate(self.games):
            g.setVisible(n == i)
            if self.opts[n] is not None:
                self.opts[n].setVisible(n == i)
        self.game = self.games[i]
        self.bet_row.setVisible(i != 6)
        self.sync()

    def sync(self) -> None:
        """Buttons and bet follow the state of the game."""
        if self.game is None:
            return
        busy = self.game.busy
        for b in (self.b_less, self.b_more, self.b_max):
            b.setEnabled(not busy)
        self.seg.setEnabled(not busy)
        self.back.setEnabled(not busy)
        for seg in self.opts:
            if seg is not None:
                seg.setEnabled(not busy)
        self.bet_box.update()
        spec = self.game.buttons()
        if [s[0] for s in spec] != [b.text_key for b in self.act_buttons]:
            for b in self.act_buttons:
                b.hide()
                b.deleteLater()
            self.act_buttons = []
            for text, kind, call, _on in spec:
                b = Button(text, kind, 38)
                b.text_key = text
                b.clicked.connect(call)
                self.act_lay.addWidget(b)
                self.act_buttons.append(b)
        for b, (_t, _k, _c, on) in zip(self.act_buttons, spec):
            b.setEnabled(bool(on))

    def busy(self) -> bool:
        return self.game is not None and self.game.busy

    def sync_labels(self) -> None:
        """While the rocket flies its button shows the growing prize: refresh the text only."""
        for b, (text, _k, _c, on) in zip(self.act_buttons, self.game.buttons()):
            if b._text != text:
                b._text = text
                b.text_key = text
                b.update()
            b.setEnabled(bool(on))

    def wrap_up(self) -> None:
        """You left the casino mid-round: a waiting hand stands, an open board cashes out (or gives the bet back
        if no card was turned). Rounds already running simply finish."""
        g = self.game
        if isinstance(g, Blackjack) and g.phase == "player":
            g.stand()
        elif isinstance(g, Bombs) and g.phase == "play":
            if g.found():
                g.cash()
            else:                                   # nothing turned yet: the board waits on the server and
                g.phase = "idle"                    # comes back the next time Bombs is started
                g.busy = False
                self.sync()
        elif isinstance(g, Rocket) and g.phase == "fly":
            g.cash()

    def on_show(self) -> None:
        self.sync()
