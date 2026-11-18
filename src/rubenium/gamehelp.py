"""4.2: the golden "?" on every game: how to play, the best way to play, and what it pays (with the real chances).

Every number here is the server's own (the functions that decide each game). The few that an admin can change
(free spin hours, minigame limits, fees) are read from the live settings when the help opens."""
import math
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from .core import S, TEXT, TEXT_DIM, alpha, font, sfx, tr
from .widgets import Button, Label, vbox

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
        "5 holes, 25 seconds a turn. Anyone can join your lobby."], [
        "Use the walls: a bank shot is often the shortest way.",
        "A short safe shot beats a long risky one."], [
        "Fewest strokes wins both bets, minus a {golf}% fee. A draw gives both bets back.",
        "Nobody joins in 5 minutes: it closes and your bet comes back."]),
    "coinflip": ("Coinflip", [
        "Create a coinflip: pick black or white and up to 6 items. Someone joins with items worth about the same "
        "(±10%), or you play a bot.",
        "You are in once you lock in your items. When both sides are in, the coin flips after 15 seconds.",
        "Press the eye on a coinflip in the lobby to watch it flip."], [
        "Only put in items you are ready to lose."], [
        "The winner takes every item.",
        "Your chance is your share of the total worth, between 49% and 51%.",
        "Bots play by the same rules, with the same coin."]),
}

CASINO_KEYS = {"Blackjack": "blackjack", "Plinko": "plinko", "Bombs": "bombs", "Roulette": "roulette", "Dice": "dice",
               "Timing": "timing", "Rocket": "rocket", "Hi-Lo": "hilo", "Tower": "tower", "Free spin": "spin"}


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
    """A round golden "?" that glows softly. Click: the help of its game."""
    clicked = pyqtSignal()

    def __init__(self, ctx, key, size: int = 32) -> None:
        super().__init__()
        self.ctx, self.key = ctx, key                      # key: a HELP key, or a function giving one
        self.setFixedSize(S(size), S(size))
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
        r = QRectF(self.rect())
        c = r.center()
        rad = r.width() / 2 - S(3)
        pulse = 0.5 + 0.5 * math.sin(time.monotonic() * 2.6)
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


class HelpSheet(QWidget):
    """The help of one game, shown inside the menu until it is closed."""

    def __init__(self, ctx, key: str) -> None:
        super().__init__()
        self.ctx = ctx
        w = ctx.window.page_w()
        self.setFixedWidth(w)
        lay = vbox(self, 8)
        title, how, best, pay = help_lines(ctx, key)
        lay.addWidget(Label(title, 17, HELP_GOLD, bold=True))
        for head, lines in ((tr("HOW TO PLAY"), how), (tr("BEST WAY TO PLAY"), best), (tr("PAYOUTS AND CHANCES"), pay)):
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
