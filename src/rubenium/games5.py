"""4.0: two minigames, each with three modes and its own leaderboard. Both are checked by the server.

Block Blast (4.1, in place of 2048): drag the three pieces onto the grid; a full row or column clears. When all
three are placed, three more come; it ends when none of them fits. The pieces come from a seed the server gives, and
the server places every piece again to count the score (it cannot be made up). Classic 8x8, Relaxed 10x10, Hard 7x7.
Minesweeper: open every safe cell. The mines stay on the server: every cell you open is asked there, so nobody can
see them in advance. The first cell is always safe. Easy, Medium, Hard; the faster, the more it pays."""
import math
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from .core import S, TEXT, TEXT_DIM, alpha, font, mix, sfx, tr
from .widgets import Button, Label, Segmented, hbox

MODES = {"blocks": ["Classic 8×8", "Relaxed 10×10", "Hard 7×7"], "sweeper": ["Easy", "Medium", "Hard"]}
SIZES_BLOCKS = [8, 10, 7]
BLOCK_PAY = [(5, 300), (8, 200), (3, 360)]          # score ÷ n, up to … coins (the server's own numbers)


# ================================================================ Block Blast (the rules are the server's, step for step)
def lcg(s: int) -> int:
    return (s * 1103515245 + 12345) % 2147483648


# every piece as (x, y) cells; the server keeps the same list in the same order (cells written y*5+x)
PIECES = [
    [(0, 0)],
    [(0, 0), (1, 0)], [(0, 0), (0, 1)],
    [(0, 0), (1, 0), (2, 0)], [(0, 0), (0, 1), (0, 2)],
    [(0, 0), (1, 0), (0, 1)], [(0, 0), (1, 0), (1, 1)], [(0, 0), (0, 1), (1, 1)], [(1, 0), (0, 1), (1, 1)],
    [(0, 0), (1, 0), (2, 0), (3, 0)], [(0, 0), (0, 1), (0, 2), (0, 3)],
    [(0, 0), (1, 0), (0, 1), (1, 1)],
    [(0, 0), (0, 1), (0, 2), (1, 2)], [(0, 0), (1, 0), (2, 0), (0, 1)], [(0, 0), (1, 0), (1, 1), (1, 2)],
    [(2, 0), (0, 1), (1, 1), (2, 1)],
    [(1, 0), (1, 1), (1, 2), (0, 2)], [(0, 0), (0, 1), (1, 1), (2, 1)], [(0, 0), (1, 0), (0, 1), (0, 2)],
    [(0, 0), (1, 0), (2, 0), (2, 1)],
    [(0, 0), (1, 0), (2, 0), (1, 1)], [(1, 0), (0, 1), (1, 1), (2, 1)], [(0, 0), (0, 1), (0, 2), (1, 1)],
    [(1, 0), (1, 1), (1, 2), (0, 1)],
    [(1, 0), (2, 0), (0, 1), (1, 1)], [(0, 0), (1, 0), (1, 1), (2, 1)], [(0, 0), (0, 1), (1, 1), (1, 2)],
    [(1, 0), (1, 1), (0, 1), (0, 2)],
    [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)], [(0, 0), (0, 1), (0, 2), (0, 3), (0, 4)],
    [(0, 0), (0, 1), (0, 2), (1, 2), (2, 2)], [(0, 0), (1, 0), (2, 0), (0, 1), (0, 2)],
    [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)], [(2, 0), (2, 1), (2, 2), (1, 2), (0, 2)],
    [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)], [(0, 0), (1, 0), (0, 1), (1, 1), (0, 2), (1, 2)],
    [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1), (0, 2), (1, 2), (2, 2)],
]
WEIGHTS = [2, 3, 3, 3, 3, 2, 2, 2, 2, 2, 2, 3] + [1] * 16 + [1, 1] + [1] * 4 + [1, 1, 1]
BAG = [i for i, w in enumerate(WEIGHTS) for _ in range(w)]


class Blocks:
    def __init__(self, n: int, seed: int):
        self.n, self.s = n, seed
        self.b = [0] * (n * n)          # 0 empty, else colour 1..8
        self.score = 0
        self.streak = 0
        self.lines = 0
        self.tray: list = []           # piece index or -1 (used)
        self.moves = ""
        self.cleared: list = []        # cells cleared by the last move (for the animation)
        self.last_gain = 0
        self._deal()

    def _deal(self) -> None:
        self.tray = []
        for _ in range(3):
            self.s = lcg(self.s)
            self.tray.append(BAG[self.s % len(BAG)])

    def fits(self, piece: int, x: int, y: int) -> bool:
        n = self.n
        for cx, cy in PIECES[piece]:
            px, py = x + cx, y + cy
            if px < 0 or py < 0 or px >= n or py >= n or self.b[py * n + px]:
                return False
        return True

    def can_place(self, piece: int) -> bool:
        return any(self.fits(piece, x, y) for y in range(self.n) for x in range(self.n))

    def over(self) -> bool:
        return not any(p >= 0 and self.can_place(p) for p in self.tray)

    def place(self, k: int, x: int, y: int) -> bool:
        if not 0 <= k < 3 or self.tray[k] < 0 or not self.fits(self.tray[k], x, y):
            return False
        n, piece = self.n, self.tray[k]
        self.moves += f"{k}{x:x}{y:x}"
        for cx, cy in PIECES[piece]:
            self.b[(y + cy) * n + x + cx] = piece % 8 + 1
        rows = [r for r in range(n) if all(self.b[r * n + c] for c in range(n))]
        cols = [c for c in range(n) if all(self.b[r * n + c] for r in range(n))]
        gone = {r * n + c for r in rows for c in range(n)} | {r * n + c for c in cols for r in range(n)}
        for i in gone:
            self.b[i] = 0
        lines = len(rows) + len(cols)
        gain = len(PIECES[piece])
        if lines:
            self.streak += 1
            gain += 10 * lines * lines + (20 * (self.streak - 1) if self.streak > 1 else 0)
        else:
            self.streak = 0
        self.score += gain
        self.lines += lines
        self.last_gain = gain
        self.cleared = sorted(gone)
        self.tray[k] = -1
        if all(p < 0 for p in self.tray):
            self._deal()
        return True


BLOCK_COLOURS = ["#FF5C5C", "#FF8A3D", "#F2C14E", "#3DDC84", "#2EC5FF", "#4F7BFF", "#B36BFF", "#FF5CC8"]


def paint_block(p: QPainter, box: QRectF, colour: int, k: float = 1.0) -> None:
    """One square of a piece: a bright tile with a light top edge and a darker bottom."""
    if k <= 0.01:
        return
    c = QColor(BLOCK_COLOURS[(colour - 1) % len(BLOCK_COLOURS)])
    box = QRectF(box.center().x() - box.width() * k / 2, box.center().y() - box.height() * k / 2,
                 box.width() * k, box.height() * k)
    rad = box.width() * 0.18
    g = QLinearGradient(box.topLeft(), box.bottomLeft())
    g.setColorAt(0, mix(c, QColor("#FFFFFF"), 0.22))
    g.setColorAt(1, mix(c, QColor("#000000"), 0.22))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(box, rad, rad)
    p.setBrush(alpha("#FFFFFF", 0.22))
    p.drawRoundedRect(QRectF(box.left() + box.width() * 0.14, box.top() + box.height() * 0.1,
                             box.width() * 0.72, box.height() * 0.2), rad * 0.6, rad * 0.6)


class BlockBoard(QWidget):
    """The grid and, under it, the three pieces to drag on it. Everything happens here: no window drag, no lag
    (a frame is drawn only while something moves)."""

    def __init__(self, page, width: int) -> None:
        super().__init__()
        self.page = page
        self.game = None
        self.side = min(width, S(360))
        self.tray_h = S(92)
        self.setFixedSize(width, self.side + S(10) + self.tray_h)
        self.drag = -1                     # the slot being dragged
        self.mouse = QPointF()
        self.anchor = None                 # (x, y) where it would go, or None
        self.fx: list = []                 # [start, kind, data]
        self._t = QTimer(self)
        self._t.setInterval(16)
        self._t.timeout.connect(self._frame)

    # -- geometry
    def grid_rect(self) -> QRectF:
        return QRectF((self.width() - self.side) / 2, 0, self.side, self.side)

    def cell(self) -> float:
        n = self.game.n if self.game else 8
        return (self.side - S(8)) / n

    def slot_rect(self, k: int) -> QRectF:
        w = self.width() / 3
        return QRectF(k * w, self.side + S(10), w, self.tray_h)

    # -- animation
    def _kick(self) -> None:
        if not self._t.isActive():
            self._t.start()

    def _frame(self) -> None:
        now = time.monotonic()
        self.fx = [f for f in self.fx if now - f[0] < 0.6]
        if not self.fx and self.drag < 0:
            self._t.stop()
        self.update()

    def placed(self, cells: list, cleared: list, gain: int, colours: dict) -> None:
        now = time.monotonic()
        self.fx.append([now, "pop", cells])
        if cleared:
            self.fx.append([now, "clear", (cleared, colours)])
        if gain:
            self.fx.append([now, "gain", gain])
        self._kick()

    # -- mouse: press a piece, drag it, let go on the grid
    def mousePressEvent(self, e) -> None:
        e.accept()
        g = self.game
        if g is None or g.over():
            return
        for k in range(3):
            if g.tray[k] >= 0 and self.slot_rect(k).contains(e.position()):
                self.drag = k
                self.mouse = e.position()
                self._aim()
                sfx.play("pick")
                self._kick()
                return

    def mouseMoveEvent(self, e) -> None:
        e.accept()
        if self.drag < 0:
            return
        self.mouse = e.position()
        self._aim()

    def mouseReleaseEvent(self, e) -> None:
        e.accept()
        if self.drag < 0:
            return
        k, at = self.drag, self.anchor
        self.drag, self.anchor = -1, None
        if at is not None:
            self.page.blocks_place(k, at[0], at[1])
        self.update()

    def _lift(self) -> float:
        return S(46)                       # the piece floats above the finger, so you see where it goes

    def _aim(self) -> None:
        g = self.game
        piece = g.tray[self.drag]
        cells = PIECES[piece]
        pw, ph = max(c[0] for c in cells) + 1, max(c[1] for c in cells) + 1
        c = self.cell()
        gr = self.grid_rect().adjusted(S(4), S(4), -S(4), -S(4))
        x = round((self.mouse.x() - gr.left()) / c - pw / 2)
        y = round((self.mouse.y() - self._lift() - gr.top()) / c - ph / 2)
        self.anchor = (x, y) if g.fits(piece, x, y) else None
        self.update()

    def _would_clear(self) -> set:
        """The rows and columns the piece being aimed would fill: they glow before you drop it."""
        g = self.game
        if self.anchor is None or g is None:
            return set()
        n, (x, y) = g.n, self.anchor
        b = list(g.b)
        for cx, cy in PIECES[g.tray[self.drag]]:
            b[(y + cy) * n + x + cx] = 1
        out = set()
        for r in range(n):
            if all(b[r * n + q] for q in range(n)):
                out |= {r * n + q for q in range(n)}
            if all(b[q * n + r] for q in range(n)):
                out |= {q * n + r for q in range(n)}
        return out

    # -- drawing
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        gr = self.grid_rect()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#11171A"))
        p.drawRoundedRect(gr, S(12), S(12))
        g = self.game
        if g is None:
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(12, QFont.Weight.DemiBold))
            p.drawText(gr, int(Qt.AlignmentFlag.AlignCenter), tr("Press New game"))
            return
        n, c, now = g.n, self.cell(), time.monotonic()
        inner = gr.adjusted(S(4), S(4), -S(4), -S(4))
        glow = self._would_clear() if self.drag >= 0 else set()
        ghost = set()
        if self.drag >= 0 and self.anchor is not None:
            ghost = {(self.anchor[1] + cy) * n + self.anchor[0] + cx for cx, cy in PIECES[g.tray[self.drag]]}
        pops = {}
        for f in self.fx:
            if f[1] == "pop":
                for i in f[2]:
                    pops[i] = now - f[0]
        for i, v in enumerate(g.b):
            box = QRectF(inner.left() + (i % n) * c, inner.top() + (i // n) * c, c, c).adjusted(S(1), S(1), -S(1), -S(1))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#1C2328"))
            p.drawRoundedRect(box, c * 0.16, c * 0.16)
            if v:
                age = pops.get(i)
                k = 1.0 if age is None or age > 0.18 else 0.6 + 0.4 * (age / 0.18) + 0.08 * math.sin(age / 0.18 * math.pi)
                paint_block(p, box, v, k)
                if i in glow:
                    p.setBrush(alpha("#FFFFFF", 0.28 + 0.12 * math.sin(now * 10)))
                    p.drawRoundedRect(box, c * 0.16, c * 0.16)
            elif i in ghost:
                col = g.tray[self.drag] % 8 + 1
                p.setOpacity(0.45)
                paint_block(p, box, col)
                p.setOpacity(1.0)
            elif i in glow:
                p.setBrush(alpha("#FFFFFF", 0.10))
                p.drawRoundedRect(box, c * 0.16, c * 0.16)
        for f in self.fx:                                   # cleared lines: the squares burst and fade
            t = now - f[0]
            if f[1] == "clear" and t < 0.45:
                cells, colours = f[2]
                k = t / 0.45
                for i in cells:
                    box = QRectF(inner.left() + (i % n) * c, inner.top() + (i // n) * c, c, c).adjusted(S(1), S(1), -S(1), -S(1))
                    p.setOpacity(1 - k)
                    paint_block(p, box, colours.get(i, 1), 1.0 + 0.35 * k)
                    p.setOpacity((1 - k) * 0.8)
                    p.setBrush(QColor("#FFFFFF"))
                    p.drawRoundedRect(box, c * 0.16, c * 0.16)
                p.setOpacity(1.0)
            elif f[1] == "gain" and t < 0.6:
                p.setOpacity(1 - t / 0.6)
                p.setPen(QColor("#FFFFFF"))
                p.setFont(font(16 if f[2] < 30 else 20, QFont.Weight.Black))
                p.drawText(QRectF(gr.left(), gr.center().y() - S(30) - t * S(40), gr.width(), S(30)),
                           int(Qt.AlignmentFlag.AlignCenter), f"+{f[2]}")
                p.setOpacity(1.0)
        for k in range(3):                                  # the tray
            piece = g.tray[k]
            if piece < 0 or k == self.drag:
                continue
            self._paint_piece(p, piece, self.slot_rect(k).center(), min(c * 0.6, S(18)),
                              1.0 if g.can_place(piece) else 0.3)
        if self.drag >= 0:                                  # the piece in the hand, at full size
            piece = g.tray[self.drag]
            self._paint_piece(p, piece, QPointF(self.mouse.x(), self.mouse.y() - self._lift()), c * 0.92, 0.95)
        if g.over() and not self.fx:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 160))
            p.drawRoundedRect(gr, S(12), S(12))
            p.setPen(QColor(TEXT))
            p.setFont(font(18, QFont.Weight.ExtraBold))
            p.drawText(gr, int(Qt.AlignmentFlag.AlignCenter), tr("No more space"))

    def _paint_piece(self, p: QPainter, piece: int, centre: QPointF, cell: float, opacity: float) -> None:
        cells = PIECES[piece]
        pw, ph = max(x for x, _y in cells) + 1, max(y for _x, y in cells) + 1
        left, top = centre.x() - pw * cell / 2, centre.y() - ph * cell / 2
        p.setOpacity(opacity)
        for x, y in cells:
            paint_block(p, QRectF(left + x * cell, top + y * cell, cell, cell).adjusted(1, 1, -1, -1), piece % 8 + 1)
        p.setOpacity(1.0)


# ================================================================ Minesweeper
class SweeperBoard(QWidget):
    def __init__(self, page, width: int) -> None:
        super().__init__()
        self.page = page
        self.w, self.h, self.m = 9, 9, 10
        self.shown: dict = {}             # cell -> number
        self.flags: set = set()
        self.mines: list = []
        self.boom = -1
        self.setFixedWidth(width)
        self._resize()

    def setup(self, w: int, h: int, m: int) -> None:
        self.w, self.h, self.m = w, h, m
        self.shown, self.flags, self.mines, self.boom = {}, set(), [], -1
        self._resize()
        self.update()

    def _resize(self) -> None:
        cell = min(S(32), (self.width() - S(4)) / self.w)
        self.cell = cell
        self.setFixedHeight(int(cell * self.h + S(4)))

    def _at(self, pos) -> int:
        ox = (self.width() - self.cell * self.w) / 2
        x, y = int((pos.x() - ox) // self.cell), int((pos.y() - S(2)) // self.cell)
        if 0 <= x < self.w and 0 <= y < self.h:
            return y * self.w + x
        return -1

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        c = self._at(e.position())
        if c < 0:
            return
        if e.button() == Qt.MouseButton.RightButton:
            if c not in self.shown:
                self.flags ^= {c}
                sfx.play("pick")
                self.update()
                self.page.sync_sweeper()
            return
        if c in self.flags or c in self.shown:
            return
        self.page.sweep_open(c)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ox = (self.width() - self.cell * self.w) / 2
        colours = {1: "#4FC3FF", 2: "#3DDC84", 3: "#FF5C5C", 4: "#B36BFF", 5: "#E8873A", 6: "#2EC4B6", 7: "#FFFFFF", 8: "#9AA4AD"}
        mines = set(self.mines)
        for c in range(self.w * self.h):
            x, y = ox + (c % self.w) * self.cell, S(2) + (c // self.w) * self.cell
            box = QRectF(x + 1, y + 1, self.cell - 2, self.cell - 2)
            p.setPen(Qt.PenStyle.NoPen)
            if c in self.shown:
                p.setBrush(QColor("#151B1F"))
                p.drawRoundedRect(box, S(3), S(3))
                n = self.shown[c]
                if n:
                    p.setPen(QColor(colours.get(n, "#FFFFFF")))
                    p.setFont(font(max(8.0, self.cell / S(1) * 0.5), QFont.Weight.Black))
                    p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), str(n))
            elif c in mines:
                p.setBrush(QColor("#E8384F") if c == self.boom else QColor("#3A2026"))
                p.drawRoundedRect(box, S(3), S(3))
                p.setBrush(QColor("#FFFFFF") if c == self.boom else QColor("#E8384F"))
                p.drawEllipse(box.center(), self.cell * 0.2, self.cell * 0.2)
            else:
                p.setBrush(QColor("#2A3238"))
                p.drawRoundedRect(box, S(3), S(3))
                p.setBrush(alpha("#FFFFFF", 0.05))
                p.drawRoundedRect(box.adjusted(0, 0, 0, -box.height() / 2), S(3), S(3))
                if c in self.flags:
                    p.setPen(QPen(QColor("#FFFFFF"), max(1.0, S(1.2))))
                    cx, cy = box.center().x(), box.center().y()
                    p.drawLine(QPointF(cx - self.cell * 0.12, cy + self.cell * 0.25), QPointF(cx - self.cell * 0.12, cy - self.cell * 0.25))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor("#FF5C5C"))
                    from PyQt6.QtGui import QPolygonF
                    p.drawPolygon(QPolygonF([QPointF(cx - self.cell * 0.12, cy - self.cell * 0.25),
                                             QPointF(cx + self.cell * 0.22, cy - self.cell * 0.12),
                                             QPointF(cx - self.cell * 0.12, cy)]))


# ================================================================ the pages (inside Games)
def _top(page, lay, title: str, game: str) -> None:
    page._back_bar(lay, title, lambda: page.open_sub("minigames"), game)
    line = hbox(spacing=6)
    seg = Segmented([tr(m) for m in MODES[game]], int(getattr(page.ctx, game + "_mode", 0) or 0))
    seg.changed.connect(lambda i: page.mg_mode(game, i))
    line.addWidget(seg, 1)
    board = Button(tr("Board"), "ghost", 30, icon="trophy")
    board.setFixedWidth(max(S(86), board.sizeHint().width()))
    board.clicked.connect(lambda: page.mg_board(game))
    line.addWidget(board)
    lay.addLayout(line)


def build_blocks(page, lay) -> None:
    ctx = page.ctx
    _top(page, lay, tr("Block Blast"), "blocks")
    mode = int(getattr(ctx, "blocks_mode", 0) or 0)
    div, cap = BLOCK_PAY[mode]
    lay.addWidget(Label(tr("Drag the pieces onto the grid. Fill a row or a column to clear it.") + "  " +
                        tr("Score ÷ {d}, up to {n} coins", d=div, n=cap), 10, TEXT_DIM, wrap_w=page.W))
    page.mg_score = Label("", 13, TEXT, bold=True)
    lay.addWidget(page.mg_score)
    page.blocks = BlockBoard(page, page.W)
    page.blocks.game = getattr(ctx, "blocks_game", None)
    lay.addWidget(page.blocks, 0, Qt.AlignmentFlag.AlignHCenter)
    line = hbox(spacing=6)
    new = Button(tr("New game"), "primary", 34)
    new.clicked.connect(lambda: page.mg_start("blocks"))
    stop = Button(tr("Finish and get paid"), "ghost", 34)
    stop.clicked.connect(page.mg_finish_blocks)
    line.addWidget(new, 1)
    line.addWidget(stop, 1)
    lay.addLayout(line)
    page.sync_blocks()


def build_sweeper(page, lay) -> None:
    ctx = page.ctx
    _top(page, lay, tr("Minesweeper"), "sweeper")
    mode = int(getattr(ctx, "sweeper_mode", 0) or 0)
    pays = [tr("up to 105 coins"), tr("up to 225 coins"), tr("up to 420 coins")][mode]
    lay.addWidget(Label(tr("Open every safe cell. Right click: flag. The faster you clear it, the more it pays") + f" ({pays}).",
                        10, TEXT_DIM, wrap_w=page.W))
    page.sw_info = Label("", 12, TEXT, bold=True)
    lay.addWidget(page.sw_info)
    page.sweeper = SweeperBoard(page, page.W)
    st = getattr(ctx, "sweeper_state", None)
    if st:
        page.sweeper.setup(st["w"], st["h"], st["m"])
        page.sweeper.shown = dict(st.get("shown") or {})
        page.sweeper.flags = set(st.get("flags") or [])
        page.sweeper.mines = list(st.get("mines") or [])
        page.sweeper.boom = st.get("boom", -1)
    else:
        w, h, m = [(9, 9, 10), (12, 12, 24), (16, 14, 40)][mode]
        page.sweeper.setup(w, h, m)
    lay.addWidget(page.sweeper, 0, Qt.AlignmentFlag.AlignHCenter)
    new = Button(tr("New game"), "primary", 34)
    new.clicked.connect(lambda: page.mg_start("sweeper"))
    lay.addWidget(new)
    page.sync_sweeper()
    if not hasattr(page, "_sw_tick"):
        page._sw_tick = QTimer(page)
        page._sw_tick.setInterval(500)
        page._sw_tick.timeout.connect(page.sync_sweeper)
        page._sw_tick.start()


class MinigamePage:
    """Mixed into GamesPage: what the two new minigames do."""

    def mg_mode(self, game: str, i: int) -> None:
        ctx = self.ctx
        setattr(ctx, game + "_mode", i)
        if game == "blocks":
            ctx.blocks_game, ctx.blocks_round = None, None
        else:
            ctx.sweeper_state, ctx.sweeper_round = None, None
        sfx.play("pick")
        ctx.reload_page()

    def mg_board(self, game: str) -> None:
        from .hub import BOARDS
        ctx = self.ctx
        ctx.board_kind = [k for k, _n in BOARDS].index(game)
        ctx.board_mode = int(getattr(ctx, game + "_mode", 0) or 0)
        ctx.board_data = None
        if getattr(ctx, "online_mode", False):
            ctx.window.open_leaders()

    def mg_start(self, game: str) -> None:
        ctx = self.ctx
        mode = int(getattr(ctx, game + "_mode", 0) or 0)

        def got(ok: bool, data) -> None:
            if not ok or not isinstance(data, dict):
                return ctx.toast(tr(str(data)), "warn")
            sfx.play("on")
            if game == "blocks":
                ctx.blocks_round = data["id"]
                ctx.blocks_game = Blocks(int(data.get("size") or SIZES_BLOCKS[mode]), int(data["seed"]))
                if hasattr(self, "blocks"):
                    self.blocks.game = ctx.blocks_game
                    self.blocks.fx = []
                    self.blocks.update()
                self.sync_blocks()
            else:
                ctx.sweeper_round = data["id"]
                ctx.sweeper_state = {"w": int(data["w"]), "h": int(data["h"]), "m": int(data["m"]), "shown": {}, "flags": [],
                                     "mines": [], "boom": -1, "t0": None, "over": False, "paid": None}
                ctx.reload_page()
        ctx.econ.call("rb_mg_start", {"game": game, "mode": mode}, got)

    # -- Block Blast
    def blocks_place(self, k: int, x: int, y: int) -> None:
        ctx = self.ctx
        g = getattr(ctx, "blocks_game", None)
        if g is None or getattr(ctx, "blocks_round", None) is None or not 0 <= k < 3 or g.tray[k] < 0:
            return
        before, colour = list(g.b), g.tray[k] % 8 + 1
        if not g.place(k, x, y):
            return
        fresh = [i for i in range(g.n * g.n) if not before[i] and g.b[i]]      # the new squares that stayed
        colours = {i: before[i] or colour for i in g.cleared}     # what each cleared square looked like
        self.blocks.placed(fresh, g.cleared, g.last_gain, colours)
        sfx.play("on" if g.cleared else "pick")
        self.sync_blocks()
        if g.over():
            QTimer.singleShot(900, self.mg_finish_blocks)

    def sync_blocks(self) -> None:
        g = getattr(self.ctx, "blocks_game", None)
        if hasattr(self, "mg_score"):
            try:
                self.mg_score.set_text(tr("Score {n}", n=g.score) + "   ·   " + tr("Lines {n}", n=g.lines) if g else
                                       tr("Press New game to start"))
            except RuntimeError:
                pass
        if hasattr(self, "blocks"):
            try:
                self.blocks.update()
            except RuntimeError:
                pass

    def mg_finish_blocks(self) -> None:
        ctx = self.ctx
        rid, g = getattr(ctx, "blocks_round", None), getattr(ctx, "blocks_game", None)
        if rid is None or g is None:
            return
        ctx.blocks_round = None

        def got(ok: bool, data) -> None:
            if not ok or not isinstance(data, dict):
                return ctx.toast(tr(str(data)), "warn")
            paid = int(data.get("paid") or 0)
            ctx.econ.absorb(data)
            ctx.econ.changed.emit()
            ctx.toast(tr("Score {n}", n=data.get("score")) + "  ·  " + (tr("+{n} coins", n=paid) if paid else tr("No coins this time")))
            sfx.play("on" if paid else "off")
        ctx.econ.call("rb_blocks_finish", {"round": rid, "moves": g.moves}, got)

    # -- Minesweeper
    def sweep_open(self, cell: int) -> None:
        ctx = self.ctx
        st, rid = getattr(ctx, "sweeper_state", None), getattr(ctx, "sweeper_round", None)
        if st is None or rid is None or st.get("over") or getattr(self, "_sw_wait", False):
            if st is None or rid is None:
                ctx.toast(tr("Press New game to start"), "warn")
            return
        self._sw_wait = True
        if st.get("t0") is None:
            st["t0"] = time.monotonic()

        def got(ok: bool, data) -> None:
            self._sw_wait = False
            if not ok or not isinstance(data, dict):
                return ctx.toast(tr(str(data)), "warn")
            for c, n in data.get("shown") or []:
                st["shown"][int(c)] = int(n)
            if data.get("over"):
                st["over"] = True
                st["secs"] = data.get("secs")
                if data.get("won"):
                    st["paid"] = int(data.get("paid") or 0)
                    ctx.econ.absorb(data)
                    ctx.econ.changed.emit()
                    sfx.play("on")
                    ctx.toast(tr("Cleared in {s} s!", s=data.get("secs")) + "  ·  " + tr("+{n} coins", n=st["paid"]))
                else:
                    st["mines"] = list(data.get("mines") or [])
                    st["boom"] = int(data.get("boom", -1))
                    sfx.play("off")
            else:
                sfx.play("pick")
            if hasattr(self, "sweeper"):
                self.sweeper.shown = dict(st["shown"])
                self.sweeper.mines = list(st["mines"])
                self.sweeper.boom = st["boom"]
                self.sweeper.update()
            self.sync_sweeper()
        ctx.econ.call("rb_sweep_open", {"round": rid, "cell": int(cell)}, got)

    def sync_sweeper(self) -> None:
        st = getattr(self.ctx, "sweeper_state", None)
        if not hasattr(self, "sw_info"):
            return
        try:
            if st is None:
                return self.sw_info.set_text(tr("Press New game to start"))
            if hasattr(self, "sweeper"):
                st["flags"] = list(self.sweeper.flags)
            left = st["m"] - len(st.get("flags") or [])
            secs = st.get("secs") if st.get("over") else (time.monotonic() - st["t0"] if st.get("t0") else 0)
            state = (tr("Cleared! +{n} coins", n=st.get("paid") or 0) if st.get("over") and st.get("paid") is not None else
                     tr("Boom! Try again") if st.get("over") else "")
            self.sw_info.set_text(tr("Mines {n}", n=left) + "   ·   " + f"{float(secs or 0):.0f} s" + ("   ·   " + state if state else ""))
        except RuntimeError:
            pass


from .games import GamesPage  # noqa: E402
for _name, _fn in list(MinigamePage.__dict__.items()):
    if callable(_fn) and not _name.startswith("__"):
        setattr(GamesPage, _name, _fn)
