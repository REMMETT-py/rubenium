"""4.0: three new casino games, all decided by the server.

Tower: climb 8 rows, one safe tile to find per row; cash out whenever you like. Four modes.
Keno: pick 1 to 10 numbers out of 40, 10 are drawn; the more you match, the more it pays (table on screen).
Limbo: choose a target multiplier; the result is drawn; reach your target and win bet x target."""
import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient

from .core import S, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, lang, mix, sfx, tr, ui
from .games import LOSE, WIN, Game, ease_out
from .shop import GOLD_TEXT
from .wallet import coins_text

RNG = random.SystemRandom()


def _num(x: float) -> str:
    t = f"{x:.2f}"
    return t.replace(".", ",") if lang() == "fr" else t


# --------------------------------------------------------------------------- #
# Tower
# --------------------------------------------------------------------------- #
class Tower(Game):
    MODES = [("Easy", 4, 1), ("Medium", 3, 1), ("Hard", 2, 1), ("Expert", 3, 2)]       # name, tiles, bombs
    ROWS = 8

    def __init__(self, page) -> None:
        super().__init__(page)
        self.mode = 1
        self.level = 0
        self.picks: list = []
        self.rows = None                          # the bombs, shown once the round is over
        self.boom = False
        self.mult = 1.0
        self.hits: list = []
        self._pop = 0.0
        self._resumed = False

    def options(self):
        return [tr(m[0]) for m in self.MODES], self.mode

    def set_option(self, i: int) -> None:
        if not self.busy:
            self.mode = i
            self.picks, self.rows, self.level, self.boom = [], None, 0, False
            self.update()

    def pass_chance(self) -> float:
        _n, tiles, bombs = self.MODES[self.mode]
        return (tiles - bombs) / tiles

    def mult_at(self, n: int) -> float:
        return 1.0 if n <= 0 else round(0.97 / self.pass_chance() ** n, 2)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        if not self.busy and not self._resumed and self.econ.ready:
            self._resumed = True

            def got(ans: dict) -> None:
                if ans.get("open"):
                    self.mode = int(ans.get("mode") or 0)
                    self.level = int(ans.get("level") or 0)
                    self.picks = list(ans.get("picks") or [])
                    self.stake = int(ans.get("bet") or 0)
                    self.busy, self.rows, self.boom = True, None, False
                    self.page.sync()
                    self.update()
            self.ask("rb_tower", {"action": "state", "bet": 0, "arg": None, "req": None}, got)

    def play(self) -> None:
        if self.busy or self.waiting or not self.take():
            return
        self.picks, self.rows, self.level, self.boom = [], None, 0, False
        self.ask("rb_tower", {"action": "start", "bet": self.stake, "arg": self.mode}, self._started, once=True,
                 refund=self.stake)

    def _started(self, ans: dict) -> None:
        self.level = 0
        sfx.play("pick")
        self.animate(0.5)

    def mouseReleaseEvent(self, e) -> None:
        if not self.busy or self.waiting:
            return
        for rect, row, col in self.hits:
            if row == self.level and rect.contains(e.position()):
                self.picks.append(col)
                self.ask("rb_tower", {"action": "pick", "bet": 0, "arg": col}, self._picked, once=True)
                return

    def _picked(self, ans: dict) -> None:
        self.picks = list(ans.get("picks") or self.picks)
        self._pop = time.monotonic()
        self.animate(0.8)
        if ans.get("boom"):
            self.boom = True
            self.rows = ans.get("rows")
            self.level = int(ans.get("level") or self.level)
            sfx.play("off")
            QTimer.singleShot(500, lambda: self.finish(0))
            return
        self.level = int(ans.get("level") or self.level)
        sfx.play("on")
        if not ans.get("open"):                            # reached the top
            self.rows = ans.get("rows")
            QTimer.singleShot(400, lambda: self.finish(int(ans.get("paid") or 0)))

    def cash(self) -> None:
        if not self.busy or self.waiting or self.level < 1:
            return

        def got(ans: dict) -> None:
            self.rows = ans.get("rows")
            self.finish(int(ans.get("paid") or 0))
        self.ask("rb_tower", {"action": "cash", "bet": 0, "arg": None}, got, once=True)

    def buttons(self) -> list:
        if not self.busy:
            return [(tr("Climb"), "primary", self.play, True)]
        return [(tr("Cash out {n}", n=coins_text(int(self.stake * self.mult_at(self.level)))) if self.level else tr("Pick a tile"),
                 "primary", self.cash, not self.waiting and self.level > 0)]

    def draw(self, p: QPainter, r: QRectF, now: float) -> None:
        _name, tiles, bombs = self.MODES[self.mode]
        self.hits = []
        bet = self.stake if self.busy else self.page.bet()
        top, bottom = r.top() + S(10), r.bottom() - S(10)
        rh = (bottom - top) / self.ROWS
        left = r.left() + S(64)
        width = r.width() - S(74)
        tw = (width - S(6) * (tiles - 1)) / tiles
        for row in range(self.ROWS):
            y = bottom - (row + 1) * rh
            m = self.mult_at(row + 1)
            current = self.busy and row == self.level
            done = row < self.level
            p.setFont(font(9.5, QFont.Weight.Bold))
            p.setPen(QColor(GOLD_TEXT) if current else QColor(TEXT if done else TEXT_FAINT))
            p.drawText(QRectF(r.left() + S(6), y, S(54), rh - S(3)), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                       "×" + _num(m))
            bomb_row = (self.rows[row] if self.rows and row < len(self.rows) else []) or []
            for col in range(tiles):
                box = QRectF(left + col * (tw + S(6)), y + S(2), tw, rh - S(5))
                picked = row < len(self.picks) and self.picks[row] == col
                is_bomb = col in bomb_row
                if picked and (not self.boom or row < len(self.picks) - 1):
                    fill = mix(QColor(WIN), QColor("#000000"), 0.35)
                elif picked and self.boom and row == len(self.picks) - 1:
                    fill = QColor(LOSE)
                elif self.rows and is_bomb:
                    fill = mix(QColor(LOSE), QColor("#000000"), 0.6)
                elif current:
                    fill = mix(ui.accent, QColor("#000000"), 0.55 - 0.1 * math.sin(now * 4))
                else:
                    fill = QColor("#1A2125")
                p.setPen(QPen(alpha("#FFFFFF", 0.12 if not current else 0.35), 1))
                p.setBrush(fill)
                p.drawRoundedRect(box, S(6), S(6))
                if picked and not (self.boom and row == len(self.picks) - 1):
                    p.setPen(QColor("#FFFFFF"))
                    p.setFont(font(12, QFont.Weight.Black))
                    p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), "◆")
                elif (self.rows and is_bomb) or (picked and self.boom):
                    p.setPen(QColor("#FFFFFF"))
                    p.setFont(font(11, QFont.Weight.Black))
                    p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), "✸")
                if current and not self.waiting:
                    self.hits.append((box, row, col))
        if not self.busy and not self.picks:
            p.setFont(font(10, QFont.Weight.DemiBold))
            p.setPen(QColor(TEXT_DIM))
            box = QRectF(left, r.top() + S(4), width, S(16))
            p.drawText(box, int(Qt.AlignmentFlag.AlignCenter),
                       tr("{t} tiles, {b} bomb a row · top pays {n}", t=tiles, b=bombs, n=coins_text(int(bet * self.mult_at(self.ROWS)))))


# --------------------------------------------------------------------------- #
# Keno
# --------------------------------------------------------------------------- #
KENO = {1: [0, 3.8], 2: [0, 1.7, 5], 3: [0, 1, 2.4, 15], 4: [0, 0, 2.3, 8.7, 47], 5: [0, 0, 1.5, 4, 18, 90],
        6: [0, 0, 0.83, 3, 8.3, 44, 260], 7: [0, 0, 0.53, 2.1, 5.3, 19, 110, 530], 8: [0, 0, 0, 1.7, 4.4, 12, 50, 220, 1100],
        9: [0, 0, 0, 1.3, 2.9, 7.3, 24, 97, 430, 2400], 10: [0, 0, 0, 1.1, 2.1, 4.6, 12, 46, 190, 930, 4600]}


class Keno(Game):
    def __init__(self, page) -> None:
        super().__init__(page)
        self.picks: list = [3, 11, 17, 24, 32]
        self.drawn: list = []
        self.shown = 0
        self.hits = 0
        self._t0 = 0.0
        self.cells: list = []

    def mouseReleaseEvent(self, e) -> None:
        if self.busy:
            return
        for rect, n in self.cells:
            if rect.contains(e.position()):
                if n in self.picks:
                    self.picks.remove(n)
                elif len(self.picks) < 10:
                    self.picks.append(n)
                else:
                    return self.ctx.toast(tr("10 numbers at most"), "warn")
                self.drawn = []
                sfx.play("pick")
                self.page.sync()
                self.update()
                return

    def random_pick(self) -> None:
        if self.busy:
            return
        k = len(self.picks) or 5
        self.picks = RNG.sample(range(1, 41), k)
        self.drawn = []
        sfx.play("pick")
        self.update()

    def clear(self) -> None:
        if not self.busy:
            self.picks, self.drawn = [], []
            self.page.sync()
            self.update()

    def play(self) -> None:
        if not self.picks:
            return self.ctx.toast(tr("Pick 1 to 10 numbers"), "warn")
        if self.busy or self.waiting or not self.take():
            return
        self.drawn = []
        self.ask("rb_keno", {"bet": self.stake, "picks": sorted(self.picks)}, self._drawn, once=True, refund=self.stake)

    def _drawn(self, ans: dict) -> None:
        self.drawn = list(ans.get("drawn") or [])
        self.hits = int(ans.get("hits") or 0)
        self._paid = int(ans.get("paid") or 0)
        self._t0 = time.monotonic()
        self.animate(10 * 0.22 + 0.6)
        QTimer.singleShot(int(10 * 220 + 300), lambda: self.finish(self._paid))

    def buttons(self) -> list:
        return [(tr("Random"), "ghost", self.random_pick, not self.busy), (tr("Clear"), "ghost", self.clear, not self.busy),
                (tr("Draw"), "primary", self.play, not self.busy and bool(self.picks))]

    def draw(self, p: QPainter, r: QRectF, now: float) -> None:
        self.cells = []
        shown = len(self.drawn) if not self._t0 else min(len(self.drawn), int((now - self._t0) / 0.22))
        if shown != self.shown and shown > self.shown:
            sfx.play("pick")
        self.shown = shown
        visible = set(self.drawn[:shown])
        grid_w = r.width() * 0.66
        cw = (grid_w - S(14) - S(3) * 7) / 8
        ch = (r.height() - S(20) - S(3) * 4) / 5
        for n in range(1, 41):
            row, col = (n - 1) // 8, (n - 1) % 8
            box = QRectF(r.left() + S(8) + col * (cw + S(3)), r.top() + S(10) + row * (ch + S(3)), cw, ch)
            mine, out = n in self.picks, n in visible
            if mine and out:
                fill, pen = QColor(WIN), QColor("#FFFFFF")
            elif out:
                fill, pen = mix(QColor(GOLD_TEXT), QColor("#000000"), 0.45), QColor("#FFFFFF")
            elif mine:
                fill, pen = mix(ui.accent, QColor("#000000"), 0.35), QColor("#FFFFFF")
            else:
                fill, pen = QColor("#1A2125"), QColor(TEXT_DIM)
            p.setPen(QPen(alpha("#FFFFFF", 0.1), 1))
            p.setBrush(fill)
            p.drawRoundedRect(box, S(5), S(5))
            p.setPen(pen)
            p.setFont(font(10, QFont.Weight.Bold))
            p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), str(n))
            self.cells.append((box, n))
        # the prize table for this many picks
        k = len(self.picks)
        tx = r.left() + grid_w + S(4)
        tw = r.right() - tx - S(8)
        p.setFont(font(10, QFont.Weight.Bold))
        p.setPen(QColor(TEXT))
        p.drawText(QRectF(tx, r.top() + S(8), tw, S(16)), int(Qt.AlignmentFlag.AlignCenter), tr("{n} picked", n=k))
        if k:
            bet = self.stake if self.busy else self.page.bet()
            table = KENO[k]
            rows = [(h, m) for h, m in enumerate(table) if m > 0]
            y = r.top() + S(28)
            rh = min(S(18), (r.height() - S(60)) / max(1, len(rows)))
            got = self.hits if self.drawn and shown >= len(self.drawn) else -1
            for h, m in reversed(rows):
                box = QRectF(tx, y, tw, rh - S(2))
                if h == got:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(alpha(WIN, 0.3))
                    p.drawRoundedRect(box, S(4), S(4))
                p.setFont(font(9, QFont.Weight.DemiBold))
                p.setPen(QColor(TEXT_DIM))
                p.drawText(box.adjusted(S(4), 0, 0, 0), int(Qt.AlignmentFlag.AlignVCenter), tr("{h} hits", h=h))
                p.setPen(QColor(GOLD_TEXT))
                p.drawText(box.adjusted(0, 0, -S(4), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                           "×" + _num(m).rstrip("0").rstrip(",.") if m != int(m) else f"×{int(m)}")
                y += rh
            p.setFont(font(8.5, QFont.Weight.DemiBold))
            p.setPen(QColor(TEXT_FAINT))
            p.drawText(QRectF(tx, r.bottom() - S(30), tw, S(26)), int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                       tr("Best prize {n}", n=coins_text(int(bet * table[-1]))))
        else:
            p.setFont(font(9.5, QFont.Weight.DemiBold))
            p.setPen(QColor(TEXT_DIM))
            p.drawText(QRectF(tx, r.top() + S(30), tw, S(80)), int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                       tr("Click 1 to 10 numbers"))


# --------------------------------------------------------------------------- #
# Limbo
# --------------------------------------------------------------------------- #
class Limbo(Game):
    TARGETS = [1.5, 2.0, 3.0, 5.0, 10.0, 25.0, 100.0]

    def __init__(self, page) -> None:
        super().__init__(page)
        self.choice = 1
        self.result = None
        self.history: list = []
        self._t0 = 0.0

    def options(self):
        return ["×" + (f"{t:g}".replace(".", ",") if lang() == "fr" else f"{t:g}") for t in self.TARGETS], self.choice

    def set_option(self, i: int) -> None:
        if not self.busy:
            self.choice = i
            self.update()

    def target(self) -> float:
        return self.TARGETS[self.choice]

    def play(self) -> None:
        if self.busy or self.waiting or not self.take():
            return
        self.result = None
        self.ask("rb_limbo", {"bet": self.stake, "target": self.target()}, self._got, once=True, refund=self.stake)

    def _got(self, ans: dict) -> None:
        self.result = float(ans.get("result") or 1)
        self._win = bool(ans.get("win"))
        self._paid = int(ans.get("paid") or 0)
        self._t0 = time.monotonic()
        self.animate(1.6)
        QTimer.singleShot(1300, self._done)

    def _done(self) -> None:
        self.history.insert(0, (self.result, self._win))
        del self.history[10:]
        self.finish(self._paid)

    def buttons(self) -> list:
        return [(tr("Play  ·  target ×{t}", t=_num(self.target()).rstrip("0").rstrip(",.")), "primary", self.play, not self.busy)]

    def draw(self, p: QPainter, r: QRectF, now: float) -> None:
        bet = self.stake if self.busy else self.page.bet()
        tgt = self.target()
        p.setFont(font(10.5, QFont.Weight.Bold))
        p.setPen(QColor(TEXT_DIM))
        chance = 97 / tgt
        p.drawText(QRectF(r.left(), r.top() + S(10), r.width(), S(18)), int(Qt.AlignmentFlag.AlignCenter),
                   tr("Target ×{t} · chance {c}% · wins {n}", t=_num(tgt).rstrip("0").rstrip(",."),
                      c=_num(chance).rstrip("0").rstrip(",."), n=coins_text(int(bet * tgt))))
        c = QPointF(r.center().x(), r.center().y() - S(6))
        shown = None
        if self.result is not None:
            k = min(1.0, (now - self._t0) / 1.2) if self._t0 else 1.0
            shown = 1 + (self.result - 1) * ease_out(k, 3)
        # a gauge: rising number, ring filling towards the target
        rad = S(70)
        p.setPen(QPen(alpha("#FFFFFF", 0.08), S(10)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, rad, rad)
        if shown is not None:
            frac = min(1.0, math.log(max(shown, 1)) / math.log(max(tgt, 1.01)))
            done = self.result is not None and (now - self._t0) > 1.2
            col = QColor(WIN) if done and self._win else QColor(LOSE) if done else ui.accent
            p.setPen(QPen(col, S(10), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(QRectF(c.x() - rad, c.y() - rad, 2 * rad, 2 * rad), 90 * 16, int(-360 * 16 * frac))
            p.setPen(col)
        else:
            p.setPen(QColor(TEXT))
        p.setFont(font(30, QFont.Weight.Black))
        p.drawText(QRectF(c.x() - rad, c.y() - S(24), 2 * rad, S(40)), int(Qt.AlignmentFlag.AlignCenter),
                   "×" + _num(shown if shown is not None else 1.0))
        p.setFont(font(9.5, QFont.Weight.Bold))
        p.setPen(QColor(GOLD_TEXT))
        p.drawText(QRectF(c.x() - rad, c.y() + S(16), 2 * rad, S(16)), int(Qt.AlignmentFlag.AlignCenter),
                   tr("target ×{t}", t=_num(tgt).rstrip("0").rstrip(",.")))
        x = r.left() + S(12)
        for res, won in self.history:
            txt = "×" + _num(res)
            p.setFont(font(9, QFont.Weight.Bold))
            w = p.fontMetrics().horizontalAdvance(txt) + S(12)
            if x + w > r.right() - S(8):
                break
            box = QRectF(x, r.bottom() - S(26), w, S(18))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(WIN if won else LOSE, 0.25))
            p.drawRoundedRect(box, S(9), S(9))
            p.setPen(QColor(WIN if won else LOSE))
            p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), txt)
            x += w + S(4)
