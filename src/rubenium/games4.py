"""4.0: Tower, decided by the server (4.1: Keno and Limbo were removed).

Tower: climb 8 rows, one safe tile to find per row; cash out whenever you like. Four modes."""
import math
import random
import time

from PyQt6.QtCore import QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen

from .core import S, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, lang, mix, sfx, tr, ui
from .games import LOSE, WIN, Game
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
