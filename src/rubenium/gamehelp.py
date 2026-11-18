"""4.2: the golden "?" on every game: how to play, the best way to play, and what it pays (with the real chances).

Every number here is the server's own (the functions that decide each game). The few that an admin can change
(free spin hours, minigame limits, fees) are read from the live settings when the help opens."""
import math
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from .core import S, TEXT, TEXT_DIM, alpha, font, sfx, tr
from .widgets import Button, Label, hbox, vbox

HELP_GOLD = "#F2C14E"


def _cfg(ctx, key: str, default: float) -> float:
    try:
        return float(ctx.econ.cfg.get(key, default) or default)
    except (TypeError, ValueError, AttributeError):
        return default


def _mg_cap(ctx) -> int:
    lvl = int(getattr(ctx.econ, "level", 0) or 0)
    return int(_cfg(ctx, "game_window_cap", 300) * (1 + 0.004 * lvl))


# title, how to play, best way to play, payouts and chances. {x} values are filled from the live settings.
HELP = {
    "blackjack": ("Blackjack", [
        "Press Deal: you and the dealer get two cards; one of the dealer's stays hidden.",
        "Hit takes a card, Stand keeps your hand, Double doubles your bet for exactly one more card.",
        "Get closer to 21 than the dealer without going over. Aces count 1 or 11, faces count 10."], [
        "Always stand on 17 or more, always hit on 11 or less.",
        "From 12 to 16: stand when the dealer shows 2 to 6, hit when it shows 7 or more.",
        "Double on 10 or 11 when the dealer shows a lower card."], [
        "Win: ×2 (your bet back, plus as much).",
        "Blackjack (21 with your first two cards): ×2.5.",
        "Same total as the dealer: your bet back.",
        "The dealer draws until 17. No split."]),
    "plinko": ("Plinko", [
        "Pick a risk, then drop the ball: it bounces 10 times, left or right, and lands in a box."], [
        "The middle boxes are by far the most likely: the edges are rare.",
        "Low risk pays often but small. High risk usually pays very little and now and then a lot."], [
        "Low: ×0.5 in the middle up to ×8.5 at the edges (96.9% comes back on average).",
        "Medium: ×0.4 up to ×21 (96.4%).",
        "High: ×0.2 up to ×70 (95.9%).",
        "Middle box: 24.6% of drops. Each edge box: 0.1% (1 in 1 024)."]),
    "bombs": ("Bombs", [
        "Choose how many bombs hide among the 25 tiles, then open tiles one by one.",
        "Every gem raises the multiplier. Cash out whenever you like: a bomb loses the bet."], [
        "Few bombs: small, safer steps. Many bombs: big jumps, very risky.",
        "Decide when you will cash out before you start, and stick to it."], [
        "Multiplier = 97% ÷ the chance of finding that many gems (up to ×1 000).",
        "First gem: ×1.01 with 1 bomb, ×1.10 with 3, ×1.21 with 5, ×1.61 with 10, ×4.85 with 20."]),
    "roulette": ("Roulette", [
        "25 slots: 1 gold (0), 12 red (odd numbers) and 12 black (even numbers).",
        "Pick your bet, then spin."], [
        "Red, Black, Low and High win almost half the time.",
        "Gold and single numbers rarely win, but pay a lot."], [
        "Red or Black: ×2, 48% chance.",
        "Low (1-12) or High (13-24): ×2, 48% chance.",
        "Gold or one number: ×24, 4% chance.",
        "96% of what is bet comes back on average."]),
    "dice": ("Dice", [
        "Choose your chance to win, from 5% to 95%, then roll.",
        "A number from 0 to 99 is drawn: below your chance wins."], [
        "A high chance wins often but pays little. A low chance pays a lot but rarely wins."], [
        "Pays 97 ÷ your chance: 50% pays ×1.94, 25% pays ×3.88, 10% pays ×9.70.",
        "97% of what is bet comes back on average."]),
    "timing": ("Timing", [
        "Press Start: a needle runs along the bar. Press STOP when it is on the target.",
        "The needle speeds up a little the longer you wait. The target moves every round."], [
        "Stop early, while the needle is still slow.",
        "Watch one bounce to feel the speed, then press a little before it reaches the target."], [
        "Perfect (the centre): ×4.",
        "Good: ×1.8.",
        "Close: ×0.9 (most of your bet back).",
        "Miss, or after 9 seconds: nothing.",
        "The server keeps its own clock: slowing Rubenium down does not help."]),
    "rocket": ("Rocket", [
        "Launch: the multiplier climbs while the rocket flies.",
        "Press Cash out before it blows up to win your bet times the multiplier.",
        "Or pick an automatic cash-out (×1.5 to ×10): it cashes out by itself if the rocket gets there."], [
        "Low targets win often: ×1.5 is reached 64% of the time.",
        "The longer you wait, the bigger the win and the bigger the risk."], [
        "Chance to reach ×m = 96% ÷ m: ×2 48%, ×3 32%, ×5 19%, ×10 9.6%.",
        "Cash out from ×1.20. The rocket never flies past ×100."]),
    "hilo": ("Hi-Lo", [
        "A card is shown. Guess if the next one is higher or lower: the same rank counts as right.",
        "Every right guess raises the multiplier. Cash out whenever you like; a wrong guess loses the bet."], [
        "Bet on the side with more cards: higher on a low card, lower on a high card.",
        "Guessing against the odds pays more, and loses more often."], [
        "Each right guess multiplies by 0.985 × 13 ÷ the ranks that win.",
        "Higher on a 2: ×1.07. Higher on a Queen: ×6.40.",
        "A round stops at 50 000 coins."]),
    "tower": ("Tower", [
        "Climb 8 rows. On each row, pick a tile: a safe one takes you up, a bomb ends the round.",
        "Cash out whenever you like from the first row on."], [
        "Easy climbs slowly but safely. Expert pays enormously, but most rounds stop on the first rows."], [
        "Easy (4 tiles, 1 bomb): ×1.29 after one row, ×9.69 at the top.",
        "Medium (3 tiles, 1 bomb): ×1.46, ×24.86 at the top.",
        "Hard (2 tiles, 1 bomb): ×1.94, ×248.32 at the top.",
        "Expert (3 tiles, 2 bombs): ×2.91 after one row.",
        "A round stops at 50 000 coins."]),
    "spin": ("Free spin", [
        "Free every {h} hours: spin the wheel and win what it lands on."], [
        "It costs nothing: come back every {h} hours."], [
        "40 coins 19.5% · 75 coins 19.5% · 120 coins 18% · 180 coins 12%",
        "300 coins 7.5% · 500 coins 4% · 1 200 coins 1.8%",
        "A key 7.7% · the Golden Wheel 5% · an XP coupon 5%"]),
    "scratch": ("Scratch card", [
        "One free card every {h} hours. Scratch it (or press Reveal) to see your prize."], [
        "It is free: scratch every card as soon as it is ready."], [
        "80 to 160 coins: 30%",
        "220 to 420 coins: 27%",
        "1 key + a Common XP coupon: 20%",
        "2 keys + an Uncommon XP coupon: 14%",
        "2 500 coins + a Rare XP coupon: 6%",
        "The Golden Wheel + an Epic XP coupon: 3%"]),
    "beat": ("Beat Tap", [
        "Notes fall in 4 lanes. Hit them as they cross the line: D F J K on the keyboard, or click.",
        "Rush is much faster, with many more notes."], [
        "Use the keyboard and keep your eyes on the line, not on the notes up high.",
        "Combos raise your score: a miss breaks them."], [
        "15 to 65 coins a round.",
        "Every minigame pays up to {cap} coins every 2 hours."]),
    "memory": ("Memory", [
        "Turn two cards at a time to find the pairs. Each card is checked on the server."], [
        "Remember every card you turn, even when it is not a pair.",
        "Clear the board in as few turns as you can."], [
        "Fewer turns pay more. Medium and Hard pay more than Easy.",
        "Every minigame pays up to {cap} coins every 2 hours."]),
    "parking": ("Parking", [
        "Slide the cars along their lane to clear the way, then drive the red car out."], [
        "First look at what blocks the red car's row, then at what blocks those cars."], [
        "Fewer moves pay more. Harder levels pay more.",
        "Up to {park} coins a day from Parking."]),
    "blocks": ("Block Blast", [
        "Drag the three pieces onto the grid. A full row or column clears.",
        "When all three are placed, three more come. The game ends when none of them fits."], [
        "Keep the middle open and fill along the edges.",
        "Place the big pieces while there is room. Clearing several lines at once, or on piece after piece, "
        "scores much more."], [
        "1 point a square. Clearing L lines at once: +10 × L × L. Clearing again on the next piece: +20 a step.",
        "Classic: score ÷ 5, up to 300 coins. Relaxed: ÷ 8, up to 200. Hard: ÷ 3, up to 360.",
        "Every minigame pays up to {cap} coins every 2 hours."]),
    "sweeper": ("Minesweeper", [
        "Open every cell without a mine. A number says how many mines touch that cell.",
        "Right-click puts a flag. The first cell is always safe."], [
        "A 1 touching a single closed cell means that cell is a mine: flag it and open the others.",
        "Start in the middle: one click often opens a big area."], [
        "Easy pays 35 to 105 coins, Medium 75 to 225, Hard 140 to 420: the faster, the more.",
        "Every minigame pays up to {cap} coins every 2 hours."]),
    "duels": ("Duels", [
        "Challenge a friend to a game, with or without a bet. You both play the same round: the best score wins."], [
        "Pick the game you are best at, and a level you know well."], [
        "The winner gets both bets minus a {fee}% fee. A draw gives both bets back.",
        "The bet is at most 80% of the lower balance."]),
    "golf": ("Mini Golf", [
        "Drag back from the ball to aim and set the power, then let go to shoot.",
        "Solo: 5 holes alone, no bet and no clock.",
        "Duel: 5 holes against another player, 25 seconds a turn. Anyone can join your lobby."], [
        "Use the walls: a bank shot is often the shortest way.",
        "A short safe shot beats a long risky one."], [
        "Solo: each hole pays by strokes: 60, 35, 20, 10, 5, then nothing. Paid at the end, with the 2-hour mini game limit.",
        "Duel: fewest strokes wins both bets, minus a {golf}% fee. A draw gives both bets back.",
        "Nobody joins in 5 minutes: it closes and your bet comes back."]),
    "wave": ("Wave Rush", [
        "Hold (mouse button or Space) to rise, let go to fall. You always move at 45 degrees.",
        "Touching a wall or a spike ends the run: there is no sliding along a wall.",
        "The course gets narrower, twistier and spikier the further you go. The colour of the walls shows how hard it is."], [
        "Small, early taps beat big late ones: steer before the bend, not in it.",
        "Look ahead, not at the arrow.",
        "In a narrow zigzag, tap in rhythm with the walls."], [
        "Solo: coins from 30 m, more the further you get (100 m: 22, 300 m: 98, 600 m: 252), with the 2-hour mini game limit.",
        "The server replays your run to count the distance: it can't be faked.",
        "Duel: both players get the same course at the same time. The longer run wins both bets (5% fee); a tie gives them back."]),
    "slots": ("Slots", [
        "Pick your bet and press Spin. The three reels stop one after the other.",
        "Only the middle line counts."], [
        "Every spin is a fresh draw: nothing is due, and nothing is hot or cold.",
        "Gems and sevens are rare, cherries and lemons are common."], [
        "Three of a kind: ×5 (cherries) to ×70 (gems). The table next to the reels shows each prize.",
        "Two bells or two sevens: ×2. Two gems: ×4.",
        "About 1 spin in 4 wins something. Over time Slots returns about 96.6% of what is bet."]),
    "coinflip": ("Coinflip", [
        "Create a coinflip: pick black or white and up to 6 items. Someone joins with items worth about the same "
        "(±10%), or you play a bot.",
        "You are in once you lock in your items. When both sides are in, the coin flips after 15 seconds.",
        "Press the eye on a coinflip in the lobby to watch it flip."], [
        "Only put in items you are ready to lose."], [
        "The winner takes every item.",
        "Your chance is your share of the total worth, between 49% and 51%.",
        "Bots play by the same rules, with the same coin.",
        "There are always 5 to 10 bot coinflips open, from small to big, sized to the players online."]),
}

_CASINO = [("Space", "Main button"), (["2", "3"], "Other buttons"), (["Left", "Right"], "Change the bet")]
CONTROLS = {
    "blackjack": _CASINO, "plinko": _CASINO, "dice": _CASINO + [("Drag", "Set your chance")], "timing": _CASINO,
    "rocket": _CASINO, "hilo": _CASINO, "slots": _CASINO,
    "bombs": _CASINO + [("LMB", "Open a tile")], "tower": _CASINO + [("LMB", "Pick a tile")],
    "roulette": _CASINO + [("LMB", "Pick what you bet on")],
    "spin": [("LMB", "Spin the wheel")], "scratch": [("Drag", "Scratch the card")],
    "beat": [(["D", "F", "J", "K"], "Hit a lane"), ("LMB", "Hit a lane"), ("Space", "Start")],
    "memory": [("LMB", "Turn a card")], "parking": [("Drag", "Slide a car along its lane")],
    "blocks": [("Drag", "Place a piece")], "sweeper": [("LMB", "Open a cell"), ("RMB", "Flag a mine")],
    "golf": [("Drag", "Pull back from the ball to aim"), ("LMB", "Let go to shoot")],
    "wave": [(["Hold", "Space", "Up", "W"], "Hold to rise, let go to fall")],
    "coinflip": [("LMB", "Pick a side and your items")], "duels": [("LMB", "Pick a friend and a game")],
}

CASINO_KEYS = {"Blackjack": "blackjack", "Plinko": "plinko", "Bombs": "bombs", "Roulette": "roulette", "Dice": "dice",
               "Timing": "timing", "Rocket": "rocket", "Hi-Lo": "hilo", "Tower": "tower", "Slots": "slots", "Free spin": "spin"}


def help_lines(ctx, key: str) -> tuple:
    title, how, best, pay = HELP[key]
    vals = {"h": int(_cfg(ctx, "spin_hours", 2)) if key == "spin" else int(_cfg(ctx, "scratch_hours", 12)),
            "cap": _mg_cap(ctx), "park": int(_cfg(ctx, "park_day_cap", 300)),
            "fee": int(round(_cfg(ctx, "duel_fee", 0.05) * 100)), "golf": int(round(_cfg(ctx, "golf_fee", 0.05) * 100))}

    def fill(lines):
        out = []
        for text in lines:
            t = tr(text)
            try:
                t = t.format(**vals)
            except (KeyError, IndexError, ValueError):
                pass
            out.append(t)
        return out
    return tr(title), fill(how), fill(best), fill(pay)


class HelpButton(QWidget):
    """A round golden "?" that glows softly, with a small HELP and an arrow pointing at it. Click: the help."""
    clicked = pyqtSignal()

    def __init__(self, ctx, key, size: int = 32) -> None:
        super().__init__()
        self.ctx, self.key = ctx, key                      # key: a HELP key, or a function giving one
        self.size_ = S(size)
        self.setFixedSize(self.size_ + S(50), self.size_)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr("How to play"))
        self._hover = 0.0
        self._t = QTimer(self)
        self._t.setInterval(50)
        self._t.timeout.connect(self.update)

    def showEvent(self, _e) -> None:
        self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()

    def enterEvent(self, _e) -> None:
        self._hover = 1.0

    def leaveEvent(self, _e) -> None:
        self._hover = 0.0

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            key = self.key() if callable(self.key) else self.key
            if key in HELP:
                sfx.play("pick")
                open_help(self.ctx, key)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        r = QRectF(self.width() - self.size_, 0, self.size_, self.size_)
        c = r.center()
        rad = r.width() / 2 - S(3)
        pulse = 0.5 + 0.5 * math.sin(now * 2.6)
        # HELP and a small arrow nudging towards the "?"
        nudge = math.sin(now * 3.0) * S(2)
        p.setPen(alpha(HELP_GOLD, 0.75 + 0.25 * self._hover))
        p.setFont(font(9.5, QFont.Weight.Black, 1.0))
        p.drawText(QRectF(0, 0, S(32), self.height()), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                   tr("HELP"))
        ax = S(36) + nudge
        p.setPen(QPen(alpha(HELP_GOLD, 0.85), S(1.5), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(ax, c.y()), QPointF(ax + S(8), c.y()))
        p.drawLine(QPointF(ax + S(8), c.y()), QPointF(ax + S(5), c.y() - S(3)))
        p.drawLine(QPointF(ax + S(8), c.y()), QPointF(ax + S(5), c.y() + S(3)))
        glow = QRadialGradient(c, r.width() / 2)
        glow.setColorAt(0.55, alpha(HELP_GOLD, 0.35 + 0.25 * pulse + 0.2 * self._hover))
        glow.setColorAt(1.0, alpha(HELP_GOLD, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, r.width() / 2, r.width() / 2)
        body = QRadialGradient(QPointF(c.x() - rad * 0.3, c.y() - rad * 0.4), rad * 1.6)
        body.setColorAt(0, QColor("#FFF1B8"))
        body.setColorAt(0.45, QColor(HELP_GOLD))
        body.setColorAt(1, QColor("#B07A12"))
        p.setBrush(body)
        p.setPen(QPen(QColor("#FFE7A0"), S(1)))
        p.drawEllipse(c, rad, rad)
        p.setPen(QColor("#3A2600"))
        p.setFont(font(rad / S(1) * 0.95, QFont.Weight.Black))
        p.drawText(QRectF(c.x() - rad, c.y() - rad, rad * 2, rad * 2), int(Qt.AlignmentFlag.AlignCenter), "?")


class HelpPreview(QWidget):
    """4.5: a small moving picture of the game, at the top of its help."""

    def __init__(self, key: str, width: int) -> None:
        super().__init__()
        self.key = key
        self.setFixedSize(width, S(118))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._t = QTimer(self)
        self._t.setInterval(33)
        self._t.timeout.connect(self.update)

    def showEvent(self, _e) -> None:
        self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()

    def paintEvent(self, _e) -> None:
        from PyQt6.QtGui import QLinearGradient, QPainterPath, QPolygonF
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        now = time.monotonic()
        clip = QPainterPath()
        clip.addRoundedRect(r, S(12), S(12))
        p.setClipPath(clip)
        bg = QLinearGradient(r.topLeft(), r.bottomLeft())
        bg.setColorAt(0, QColor("#141B20"))
        bg.setColorAt(1, QColor("#0A0E11"))
        p.fillRect(r, bg)
        c = r.center()
        u = S(1)
        k = self.key
        p.setPen(Qt.PenStyle.NoPen)
        if k in ("blackjack", "hilo"):
            cards = [("A", "#D8314A"), ("K", "#14181A")] if k == "blackjack" else [("7", "#14181A"), ("?", "#FFFFFF")]
            for i, (t, col) in enumerate(cards):
                p.save()
                p.translate(c.x() - 26 * u + i * 52 * u, c.y() + math.sin(now * 2 + i) * 3 * u)
                p.rotate(-8 + 16 * i)
                p.setBrush(QColor("#F4F5F6") if t != "?" else QColor(HELP_GOLD))
                p.drawRoundedRect(QRectF(-22 * u, -32 * u, 44 * u, 64 * u), 6 * u, 6 * u)
                p.setPen(QColor(col))
                p.setFont(font(20, QFont.Weight.Black))
                p.drawText(QRectF(-22 * u, -32 * u, 44 * u, 64 * u), int(Qt.AlignmentFlag.AlignCenter), t)
                p.setPen(Qt.PenStyle.NoPen)
                p.restore()
        elif k == "plinko":
            for row in range(6):
                for j in range(row + 3):
                    p.setBrush(alpha("#FFFFFF", 0.5))
                    p.drawEllipse(QPointF(c.x() + (j - (row + 2) / 2) * 18 * u, r.top() + 14 * u + row * 14 * u), 2 * u, 2 * u)
            ph = (now * 0.6) % 1.0
            p.setBrush(QColor(HELP_GOLD))
            p.drawEllipse(QPointF(c.x() + math.sin(ph * 9) * 20 * u * ph, r.top() + 8 * u + ph * 90 * u), 5 * u, 5 * u)
        elif k in ("bombs", "tower", "sweeper", "memory"):
            cols, rows = (5, 3) if k != "tower" else (3, 4)
            lit = int(now * 2) % (cols * rows)
            cell = 20 * u
            ox, oy = c.x() - cols * cell / 2, c.y() - rows * cell / 2
            for i in range(cols * rows):
                q = QRectF(ox + (i % cols) * cell + 2 * u, oy + (i // cols) * cell + 2 * u, cell - 4 * u, cell - 4 * u)
                p.setBrush(QColor(HELP_GOLD) if i == lit else QColor("#2A3238") if i > lit else QColor("#3DDC84"
                           if k != "sweeper" else "#151B1F"))
                p.drawRoundedRect(q, 4 * u, 4 * u)
        elif k in ("dice", "roulette", "spin", "scratch", "slots", "rocket", "timing"):
            if k == "dice":
                p.setBrush(QColor("#F4F5F6"))
                p.save()
                p.translate(c)
                p.rotate(math.sin(now * 2) * 12)
                p.drawRoundedRect(QRectF(-26 * u, -26 * u, 52 * u, 52 * u), 9 * u, 9 * u)
                p.setBrush(QColor("#14181A"))
                for dx, dy in ((-12, -12), (12, 12), (0, 0), (12, -12), (-12, 12)):
                    p.drawEllipse(QPointF(dx * u, dy * u), 4.5 * u, 4.5 * u)
                p.restore()
            elif k in ("roulette", "spin"):
                cols = ["#E8384F", "#1E2429"] * 6 if k == "roulette" else ["#4FC3FF", "#FFB547", "#5BE08A", "#B36BFF"] * 3
                p.save()
                p.translate(c)
                p.rotate(now * 60 % 360)
                for i, col in enumerate(cols):
                    p.setBrush(QColor(col))
                    p.drawPie(QRectF(-42 * u, -42 * u, 84 * u, 84 * u), int(i * 5760 / len(cols)), int(5760 / len(cols)))
                p.restore()
                p.setBrush(QColor("#FFFFFF"))
                p.drawPolygon(QPolygonF([QPointF(c.x() - 6 * u, r.top() + 6 * u), QPointF(c.x() + 6 * u, r.top() + 6 * u),
                                         QPointF(c.x(), r.top() + 18 * u)]))
            elif k == "scratch":
                card = QRectF(c.x() - 70 * u, c.y() - 34 * u, 140 * u, 68 * u)
                p.setBrush(QColor(HELP_GOLD))
                p.drawRoundedRect(card, 8 * u, 8 * u)
                p.setPen(QColor("#3A2600"))
                p.setFont(font(16, QFont.Weight.Black))
                p.drawText(card, int(Qt.AlignmentFlag.AlignCenter), "+300")
                p.setPen(Qt.PenStyle.NoPen)
                ph = (now * 0.5) % 1.0
                p.setBrush(QColor("#8E99A3"))
                p.drawRoundedRect(QRectF(card.left() + card.width() * ph, card.top(), card.width() * (1 - ph), card.height()),
                                  8 * u, 8 * u)
            elif k == "slots":
                from .games import paint_slot_symbol
                for i, sym in enumerate(("seven", "gem", "seven")):
                    q = QRectF(c.x() - 60 * u + i * 42 * u, c.y() - 30 * u, 36 * u, 60 * u)
                    p.setBrush(QColor("#1A2125"))
                    p.drawRoundedRect(q, 6 * u, 6 * u)
                    paint_slot_symbol(p, sym, q.center() + QPointF(0, math.sin(now * 5 + i) * 4 * u), 26 * u)
            elif k == "rocket":
                ph = (now * 0.4) % 1.0
                path = QPainterPath(QPointF(r.left() + 20 * u, r.bottom() - 14 * u))
                tip = QPointF(r.left() + 20 * u + ph * (r.width() - 60 * u), r.bottom() - 14 * u - ph * ph * 80 * u)
                path.quadTo(QPointF(tip.x() * 0.7, r.bottom() - 14 * u), tip)
                p.setPen(QPen(QColor("#5BE08A"), 2.6 * u))
                p.drawPath(path)
                p.setPen(QColor("#FFFFFF"))
                p.setFont(font(15, QFont.Weight.Black))
                p.drawText(r.adjusted(0, 8 * u, -12 * u, 0), int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight),
                           f"×{1 + ph * ph * 4:.2f}")
            else:
                bar = QRectF(r.left() + 30 * u, c.y() - 6 * u, r.width() - 60 * u, 12 * u)
                p.setBrush(QColor("#1A2125"))
                p.drawRoundedRect(bar, 6 * u, 6 * u)
                p.setBrush(QColor("#3DDC84"))
                p.drawRoundedRect(QRectF(bar.center().x() + 20 * u, bar.top(), 24 * u, bar.height()), 5 * u, 5 * u)
                nx = bar.left() + (0.5 + 0.5 * math.sin(now * 2.4)) * bar.width()
                p.setBrush(QColor("#FFFFFF"))
                p.drawRoundedRect(QRectF(nx - 2 * u, bar.top() - 14 * u, 4 * u, bar.height() + 28 * u), 2 * u, 2 * u)
        elif k == "beat":
            cols = ["#FF5C8A", "#4FC3FF", "#5BE08A", "#FFB547"]
            lw = 34 * u
            ox = c.x() - 2 * lw
            for i in range(4):
                p.setBrush(alpha(cols[i], 0.10))
                p.drawRect(QRectF(ox + i * lw + 2 * u, r.top(), lw - 4 * u, r.height()))
                y = r.top() + ((now * 0.8 + i * 0.27) % 1.0) * (r.height() - 20 * u)
                p.setBrush(QColor(cols[i]))
                p.drawRoundedRect(QRectF(ox + i * lw + 5 * u, y, lw - 10 * u, 9 * u), 4 * u, 4 * u)
            p.setBrush(alpha("#FFFFFF", 0.6))
            p.drawRect(QRectF(ox, r.bottom() - 20 * u, 4 * lw, 2 * u))
        elif k == "parking":
            cell = 18 * u
            ox, oy = c.x() - 3 * cell, c.y() - 3 * cell
            p.setBrush(QColor("#1A2125"))
            p.drawRoundedRect(QRectF(ox, oy, 6 * cell, 6 * cell), 6 * u, 6 * u)
            slide = (0.5 + 0.5 * math.sin(now * 1.6)) * 2 * cell
            p.setBrush(QColor("#E8384F"))
            p.drawRoundedRect(QRectF(ox + 2 * u + slide, oy + 2 * cell + 2 * u, 2 * cell - 4 * u, cell - 4 * u), 4 * u, 4 * u)
            p.setBrush(QColor("#4FC3FF"))
            p.drawRoundedRect(QRectF(ox + 4 * cell + 2 * u, oy + 2 * u, cell - 4 * u, 3 * cell - 4 * u), 4 * u, 4 * u)
        elif k == "blocks":
            cell = 14 * u
            ox, oy = c.x() - 4 * cell, c.y() - 3 * cell
            for i in range(48):
                filled = (i // 8) == 5 or i in (3, 11, 12, 20, 28)
                p.setBrush(QColor("#B36BFF") if filled else QColor("#1A2125"))
                p.drawRoundedRect(QRectF(ox + (i % 8) * cell + 1, oy + (i // 8) * cell + 1, cell - 2, cell - 2), 3 * u, 3 * u)
        elif k == "golf":
            p.setBrush(QColor("#2E9E4F"))
            p.drawRoundedRect(r.adjusted(18 * u, 14 * u, -18 * u, -14 * u), 18 * u, 18 * u)
            hole = QPointF(r.right() - 50 * u, c.y())
            p.setBrush(QColor("#0B120D"))
            p.drawEllipse(hole, 6 * u, 4 * u)
            ph = (now * 0.45) % 1.0
            ball = QPointF(r.left() + 50 * u + (hole.x() - r.left() - 50 * u) * min(1.0, ph * 1.3), c.y())
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(ball, 5 * u, 5 * u)
        elif k == "wave":
            pts = []
            for i in range(9):
                x = r.left() + i * r.width() / 8 - ((now * 60 * u) % (r.width() / 8))
                pts.append(QPointF(x, c.y() + (22 * u if i % 2 else -22 * u)))
            p.setPen(QPen(QColor("#2EE6D6"), 2.4 * u))
            p.drawPolyline(QPolygonF(pts))
            p.setPen(QPen(alpha("#2EE6D6", 0.7), 2 * u))
            p.drawLine(QPointF(r.left(), r.top() + 14 * u), QPointF(r.right(), r.top() + 14 * u))
            p.drawLine(QPointF(r.left(), r.bottom() - 14 * u), QPointF(r.right(), r.bottom() - 14 * u))
        else:                                                   # coinflip, duels
            from .games3 import paint_flip_coin
            paint_flip_coin(p, c, 34 * u, now * 2.2, None)
        p.setClipping(False)
        p.setPen(QPen(alpha("#FFFFFF", 0.08), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, S(12), S(12))


class StepRow(QWidget):
    """One numbered step of how to play."""

    def __init__(self, n: int, text: str, width: int) -> None:
        super().__init__()
        lay = hbox(self, 8)
        self.n = n
        badge = QWidget()
        badge.setFixedSize(S(22), S(22))
        badge.paintEvent = lambda _e, b=badge: self._badge(b)
        lay.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(Label(text, 11, TEXT, wrap_w=width - S(32)), 1)

    def _badge(self, b) -> None:
        p = QPainter(b)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(HELP_GOLD))
        p.drawEllipse(QRectF(b.rect()).adjusted(1, 1, -1, -1))
        p.setPen(QColor("#3A2600"))
        p.setFont(font(10.5, QFont.Weight.Black))
        p.drawText(QRectF(b.rect()), int(Qt.AlignmentFlag.AlignCenter), str(self.n))


class HelpSheet(QWidget):
    """The help of one game, shown inside the menu until it is closed: a moving preview, the steps, every control,
    then the best way to play and what it pays."""

    def __init__(self, ctx, key: str) -> None:
        super().__init__()
        from .widgets import ControlsBar
        self.ctx = ctx
        w = ctx.window.page_w()
        self.setFixedWidth(w)
        lay = vbox(self, 8)
        title, how, best, pay = help_lines(ctx, key)
        lay.addWidget(Label(title, 17, HELP_GOLD, bold=True))
        lay.addWidget(HelpPreview(key, w))
        lay.addWidget(Label(tr("HOW TO PLAY"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
        for i, text in enumerate(how, 1):
            lay.addWidget(StepRow(i, text, w))
        if key in CONTROLS:
            lay.addWidget(Label(tr("CONTROLS"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
            lay.addWidget(ControlsBar([(k, tr(t)) for k, t in CONTROLS[key]], w))
        for head, lines in ((tr("BEST WAY TO PLAY"), best), (tr("PAYOUTS AND CHANCES"), pay)):
            if not lines:
                continue
            lay.addWidget(Label(head, 10, TEXT_DIM, weight=QFont.Weight.Bold))
            for text in lines:
                lay.addWidget(Label("•  " + text, 11, TEXT, wrap_w=w))
        close = Button(tr("Got it"), "primary", 36)
        close.clicked.connect(lambda: ctx.window.unembed(self))
        lay.addSpacing(S(4))
        lay.addWidget(close)


def open_help(ctx, key: str) -> None:
    ctx.window.embed(HelpSheet(ctx, key))
