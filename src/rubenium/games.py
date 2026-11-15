"""Games tab: a lobby, then the casino (blackjack, plinko, bombs, slots and the free daily spin). Rubenium coins only.

Rules that hold everywhere: a bet is taken before a round starts and can never be more than you have (no debt);
every result comes from the system's secure random numbers; the odds slightly favour the house."""
import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import QGridLayout, QWidget

from .core import S, sfx, TEXT, TEXT_DIM, alpha, font, mix, tr, ui
from .pages import Page
from .shop import CoinBar, GOLD_TEXT, clock_text
from .wallet import KEY_EVERY, KEY_MAX, coins_text, paint_coin
from .widgets import Button, IconButton, Label, Segmented, Tween, draw_icon, hbox, vbox

RNG = random.SystemRandom()
BETS = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000]
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
        """Take the bet for a new round. False when there are not enough coins."""
        bet = self.page.bet()
        if bet <= 0 or not self.wallet.bet(bet):
            self.ctx.toast(tr("Not enough coins"), "warn")
            return False
        self.stake = bet
        self.busy = True
        self.page.sync()
        return True

    def finish(self, payout: int) -> None:
        """End of the round: pay what was won (0 = lost) and show it."""
        payout = int(payout)
        if payout > 0:
            self.wallet.add(payout)
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

    def _card(self, hidden: bool = False, delay: float = 0.0) -> dict:
        return {"rank": RNG.choice(RANKS), "suit": RNG.choice(SUITS), "born": time.monotonic() + delay,
                "hidden": hidden, "turned": 0.0}

    def deal(self) -> None:
        if self.busy or not self.take():
            return
        self.player = [self._card(delay=0.0), self._card(delay=0.36)]
        self.dealer = [self._card(delay=0.18), self._card(hidden=True, delay=0.54)]
        self.phase = "player"
        self.animate(1.2)
        self.page.sync()
        if hand_total(self.player) == 21:
            QTimer.singleShot(1000, self.stand)

    def hit(self) -> None:
        if self.phase != "player":
            return
        self.player.append(self._card())
        self.animate(0.6)
        if hand_total(self.player) > 21:
            self.phase = "dealer"
            self.page.sync()
            QTimer.singleShot(650, lambda: self._end(0))
        elif hand_total(self.player) == 21:
            self.stand()

    def double(self) -> None:
        if self.phase != "player" or len(self.player) != 2 or not self.wallet.bet(self.stake):
            return
        self.stake *= 2
        self.player.append(self._card())
        self.animate(0.6)
        if hand_total(self.player) > 21:
            self.phase = "dealer"
            self.page.sync()
            QTimer.singleShot(650, lambda: self._end(0))
        else:
            self.stand()

    def stand(self) -> None:
        if self.phase != "player":
            return
        self.phase = "dealer"
        self.page.sync()
        self.dealer[1]["hidden"] = False
        self.dealer[1]["turned"] = time.monotonic()
        self.animate(0.8)
        QTimer.singleShot(750, self._dealer_step)

    def _dealer_step(self) -> None:
        if self.phase != "dealer":
            return
        natural = len(self.player) == 2 and hand_total(self.player) == 21
        if hand_total(self.dealer) < 17 and not natural:
            self.dealer.append(self._card())
            self.animate(0.7)
            QTimer.singleShot(700, self._dealer_step)
            return
        me, house = hand_total(self.player), hand_total(self.dealer)
        house_natural = len(self.dealer) == 2 and house == 21
        if natural and not house_natural:
            pay = int(self.stake * 2.5)
        elif house > 21 or me > house:
            pay = self.stake * 2
        elif me == house and natural == house_natural:
            pay = self.stake
        else:
            pay = 0
        self._end(pay)

    def _end(self, pay: int) -> None:
        if self.dealer and self.dealer[1]["hidden"]:
            self.dealer[1]["hidden"] = False
            self.dealer[1]["turned"] = time.monotonic()
        self.phase = "idle"
        self.finish(pay)

    def buttons(self) -> list:
        if self.phase == "player":
            can_double = len(self.player) == 2 and self.wallet.balance() >= self.stake
            return [(tr("Hit"), "primary", self.hit, True), (tr("Stand"), "ghost", self.stand, True),
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
        if len(self.balls) >= self.MAX_BALLS or now - self._last < self.GAP:
            return
        if self._too_regular(now):
            self._cool = now + 20.0
            self._presses = []
            return self.ctx.toast(tr("Slow down"), "warn")
        bet = self.page.bet()
        if bet <= 0 or not self.wallet.bet(bet):
            return self.ctx.toast(tr("Not enough coins"), "warn")
        self._last = now
        path = [RNG.choice((-1, 1)) for _ in range(self.ROWS)]      # decided now, shown as it falls
        box = sum(1 for d in path if d > 0)
        self.balls.append(dict(path=path, box=box, born=now, stake=bet, risk=self.risk,
                               jit=RNG.uniform(-0.25, 0.25)))
        self.stake = bet
        self.busy = True
        self.animate(self.ROWS * self.STEP + 1.5)
        self.page.sync()
        QTimer.singleShot(int((self.ROWS * self.STEP + 0.12) * 1000), self._land)

    def _land(self) -> None:
        if not self.balls:
            return
        ball = self.balls.pop(0)
        mult = self.MULTS[ball["risk"]][ball["box"]]
        pay = int(ball["stake"] * mult)
        if pay:
            self.wallet.add(pay)
        now = time.monotonic()
        self._hits[ball["box"]] = now
        colour = WIN if mult >= 1 else (TEXT_DIM if mult >= 0.5 else LOSE)
        self._pops = [x for x in self._pops if now - x[3] < 1.2] + [(f"×{mult:g}", colour, ball["box"], now)]
        sfx.play("on" if mult >= 2 else "pick")
        self.animate(1.3)
        if not self.balls:
            self.busy = False
        self.page.sync()

    def buttons(self) -> list:
        return [(tr("Drop"), "primary", self.drop, len(self.balls) < self.MAX_BALLS)]

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
        if self.busy or not self.take():
            return
        self.board = set(RNG.sample(range(self.N), self.bombs()))
        self.shown, self.boom, self.phase = {}, -1, "play"
        self.picked = set()
        self.animate(0.5)
        self.page.sync()

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
        if e.button() != Qt.MouseButton.LeftButton or self.phase != "play":
            return
        i = self._at(e.position())
        if i < 0 or i in self.shown:
            return
        now = time.monotonic()
        self.shown[i] = now
        self.picked.add(i)
        self.animate(0.6)
        if i in self.board:                              # bomb: the round is lost, then every card is shown
            self.boom = i
            self.phase = "lost"
            sfx.play("off")
            self.page.sync()
            QTimer.singleShot(650, self._reveal_all)
            QTimer.singleShot(1100, lambda: self._end(0))
            return
        sfx.play("pick")
        if self.found() >= self.N - self.bombs():
            QTimer.singleShot(350, self.cash)
        self.page.sync()

    def _reveal_all(self) -> None:
        now = time.monotonic()
        for k in range(self.N):
            self.shown.setdefault(k, now + 0.02 * (k % 5))
        self.animate(0.8)

    def cash(self) -> None:
        if self.phase != "play" or self.found() < 1:
            return
        pay = int(self.stake * bombs_mult(self.found(), self.bombs()))
        self.phase = "won"
        self._reveal_all()
        self._end(pay)

    def _end(self, pay: int) -> None:
        self.phase = "idle"
        self.finish(pay)

    def buttons(self) -> list:
        if self.phase == "play":
            mult = bombs_mult(self.found(), self.bombs())
            return [(tr("Cash out") + f"  ×{mult:g}", "primary", self.cash, self.found() >= 1)]
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
        if self.busy or not self.take():
            return
        self.final = [RNG.choices(self.SYMBOLS, self.WEIGHTS)[0] for _ in range(3)]
        for i in range(3):
            strip = [RNG.choices(self.SYMBOLS, self.WEIGHTS)[0] for _ in range(40)]
            strip[1] = self.final[i]
            self.strips[i] = strip
        self._t0 = time.monotonic()
        self.win_at = 0.0
        self.animate(3.0)
        QTimer.singleShot(2450, self._done)

    def payout(self) -> int:
        a, b, c = self.final
        if a == b == c:
            return self.stake * self.TRIPLE[a]
        if a == b or b == c or a == c:
            return int(self.stake * self.PAIR)
        return 0

    def _done(self) -> None:
        pay = self.payout()
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
    PRIZES = [(50, 0), (100, 0), (0, 1), (250, 0), (75, 0), (150, 0), (0, 1), (500, 0), (50, 0), (1000, 0), (0, 3),
              (100, 0)]
    WEIGHTS = [18, 12, 9, 5, 16, 8, 9, 2, 18, 1, 2, 12]

    def __init__(self, page) -> None:
        super().__init__(page)
        self.angle = 0.0
        self._from = self._to = 0.0
        self._t0 = 0.0
        self.result = -1
        self.wallet.time_checked.connect(self._checked)

    def always_moving(self) -> bool:
        return True

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.wallet.check_time()

    def _checked(self) -> None:
        self.page.sync()
        self.update()

    def spin(self) -> None:
        if self.busy or self.wallet.daily_wait() != 0:
            return
        self.result = RNG.choices(range(len(self.PRIZES)), self.WEIGHTS)[0]
        coins, keys = self.PRIZES[self.result]
        if not self.wallet.claim_daily(coins, keys):              # paid at once: the wheel only shows it
            return
        self.busy = True
        self.stake = 0
        seg = 360.0 / len(self.PRIZES)
        self._from = self.angle % 360.0
        self._to = 360.0 * 5 + (self.result + 0.5 + RNG.uniform(-0.3, 0.3)) * seg
        self._t0 = time.monotonic()
        self.animate(5.0)
        self.page.sync()
        QTimer.singleShot(4700, self._done)

    def _done(self) -> None:
        self.angle = self._to % 360.0
        coins, keys = self.PRIZES[self.result]
        self.flash("+" + (coins_text(coins) if coins else f"{keys} " + (tr("key") if keys == 1 else tr("keys"))), WIN)
        sfx.play("on")
        self.busy = False
        self.page.sync()

    def buttons(self) -> list:
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
        ready = wait == 0 or self.busy
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
                   int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), f"{min(w.keys(), KEY_MAX)} / {KEY_MAX}")
        bar = QRectF(r.left() + S(46), r.top() + S(38), r.width() - S(58), S(5))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.08))
        p.drawRoundedRect(bar, bar.height() / 2, bar.height() / 2)
        p.setBrush(ui.accent)
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), max(bar.height(), bar.width() * w.key_progress()), bar.height()),
                          bar.height() / 2, bar.height() / 2)
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10, QFont.Weight.DemiBold))
        text = tr("Full: open a case in the Shop") if w.keys() >= KEY_MAX else \
            tr("1 key for every {n} coins played", n=coins_text(KEY_EVERY))
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
            self.page.enter(4)

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
                   tr("Free daily spin"))
        if wait is None:
            text, col = ("…" if w.checking() else tr("Offline")), TEXT_DIM
        elif ready:
            text, col = tr("Ready"), GOLD_TEXT
        else:
            text, col = clock_text(wait), TEXT_DIM
        p.setPen(QColor(col))
        p.setFont(font(12, QFont.Weight.Bold))
        p.drawText(r.adjusted(0, 0, -S(12), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), text)


class GamesPage(Page):
    """The lobby (normal size) and, once you go in, the casino (shown bigger)."""
    key = "games"
    NAMES = ["Blackjack", "Plinko", "Bombs", "Slots", "Daily"]

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self._bet = 2                                # index in BETS
        self.game = None
        lay = vbox(self, 8)
        if not ctx.casino:
            if getattr(ctx, "casino_ask", None) is not None and not ctx.wallet.warned():
                return self._warning(lay)
            return self._lobby(lay)
        self._casino(lay)

    # -- the lobby
    def _lobby(self, lay) -> None:
        lay.addWidget(CoinBar(self.ctx))
        lay.addWidget(KeyCard(self.ctx))
        lay.addWidget(DailyRow(self))
        grid = QWidget()
        gl = QGridLayout(grid)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(S(6))
        for i, name in enumerate(self.NAMES[:4]):
            gl.addWidget(GameTile(self, i, name), i // 2, i % 2)
        lay.addWidget(grid)
        go = Button(tr("Enter casino"), "primary", 40)
        go.clicked.connect(lambda: self.enter(None))
        lay.addWidget(go)

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
        self.seg = Segmented([tr(n) for n in self.NAMES], which)
        self.seg.changed.connect(self._choose)
        lay.addWidget(self.seg)
        self.games = [Blackjack(self), Plinko(self), Bombs(self), Slots(self), Daily(self)]
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
        if self.game is not None and self.game.busy:
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
        self.bet_row.setVisible(i != 4)
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

    def wrap_up(self) -> None:
        """You left the casino mid-round: a waiting hand stands, an open board cashes out (or gives the bet back
        if no card was turned). Rounds already running simply finish."""
        g = self.game
        if isinstance(g, Blackjack) and g.phase == "player":
            g.stand()
        elif isinstance(g, Bombs) and g.phase == "play":
            if g.found():
                g.cash()
            else:
                g.phase = "idle"
                g.board = set()
                g.wallet.add(g.stake)
                g.stake = 0
                g.busy = False
                self.sync()

    def on_show(self) -> None:
        self.sync()
