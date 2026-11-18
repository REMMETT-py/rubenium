"""4.0: two new minigames, each with three modes and its own leaderboard. Both are checked by the server.

2048: slide the tiles (arrow keys, WASD, a swipe or the buttons), merge equal ones. The server plays your moves again
with the same random tiles to count the score (it cannot be made up). Classic 4x4, Relaxed 5x5, Hard 3x3.
Minesweeper: open every safe cell. The mines stay on the server: every cell you open is asked there, so nobody can
see them in advance. The first cell is always safe. Easy, Medium, Hard; the faster, the more it pays."""
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from .core import S, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, mix, sfx, tr, ui
from .widgets import Button, Label, Segmented, hbox

MODES = {"g2048": ["Classic 4×4", "Relaxed 5×5", "Hard 3×3"], "sweeper": ["Easy", "Medium", "Hard"]}
SIZES_2048 = [4, 5, 3]


# ================================================================ 2048 (the rules are the server's, step for step)
def lcg(s: int) -> int:
    return (s * 1103515245 + 12345) % 2147483648


class Game2048:
    def __init__(self, n: int, seed: int):
        self.n, self.s, self.score = n, seed, 0
        self.b = [0] * (n * n)
        self.moves = ""
        self.spawned = -1
        self.merged: list = []
        self._spawn()
        self._spawn()

    def _spawn(self) -> int:
        empties = [i for i, v in enumerate(self.b) if v == 0]
        if not empties:
            return -1
        self.s = lcg(self.s)
        idx = empties[self.s % len(empties)]
        self.s = lcg(self.s)
        self.b[idx] = 4 if self.s % 10 == 0 else 2
        self.spawned = idx
        return idx

    def _pos(self, m: str, i: int, k: int) -> int:
        n = self.n
        return {"L": i * n + k, "R": i * n + (n - 1 - k), "U": k * n + i, "D": (n - 1 - k) * n + i}[m]

    def move(self, m: str) -> bool:
        self.moves += m
        n, nb, changed, merged = self.n, list(self.b), False, []
        for i in range(n):
            line = [self.b[self._pos(m, i, k)] for k in range(n) if self.b[self._pos(m, i, k)]]
            out, j = [], 0
            while j < len(line):
                if j + 1 < len(line) and line[j] == line[j + 1]:
                    out.append(line[j] * 2)
                    self.score += line[j] * 2
                    merged.append(self._pos(m, i, len(out) - 1))
                    j += 2
                else:
                    out.append(line[j])
                    j += 1
            for k in range(n):
                p = self._pos(m, i, k)
                v = out[k] if k < len(out) else 0
                if self.b[p] != v:
                    changed = True
                nb[p] = v
        self.merged = merged
        self.spawned = -1
        if changed:
            self.b = nb
            self._spawn()
        return changed

    def can_move(self) -> bool:
        n = self.n
        if 0 in self.b:
            return True
        for i in range(n):
            for k in range(n):
                v = self.b[i * n + k]
                if (k + 1 < n and self.b[i * n + k + 1] == v) or (i + 1 < n and self.b[(i + 1) * n + k] == v):
                    return True
        return False


TILE = {2: "#3A4650", 4: "#4A5560", 8: "#E8873A", 16: "#E86A3A", 32: "#E8503A", 64: "#E8383A", 128: "#E8C26A",
        256: "#E8B84A", 512: "#E8AE2A", 1024: "#3DDC84", 2048: "#2EC4B6", 4096: "#4FC3FF", 8192: "#B36BFF"}


class Board2048(QWidget):
    def __init__(self, page, size: int) -> None:
        super().__init__()
        self.page = page
        self.setFixedSize(size, size)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.game = None
        self._press = None
        self._t_move = 0.0
        self._t = QTimer(self)
        self._t.setInterval(16)
        self._t.timeout.connect(self._frame)

    def _frame(self) -> None:
        self.update()
        if time.monotonic() - self._t_move > 0.25:
            self._t.stop()

    def keyPressEvent(self, e) -> None:
        k = e.key()
        m = {Qt.Key.Key_Left: "L", Qt.Key.Key_A: "L", Qt.Key.Key_Right: "R", Qt.Key.Key_D: "R",
             Qt.Key.Key_Up: "U", Qt.Key.Key_W: "U", Qt.Key.Key_Down: "D", Qt.Key.Key_S: "D"}.get(k)
        if m:
            self.page.mg_move(m)
            e.accept()
        else:
            super().keyPressEvent(e)

    def mousePressEvent(self, e) -> None:
        self._press = e.position()
        self.setFocus()

    def mouseReleaseEvent(self, e) -> None:
        if self._press is None:
            return
        d = e.position() - self._press
        self._press = None
        if max(abs(d.x()), abs(d.y())) < S(20):
            return
        self.page.mg_move(("R" if d.x() > 0 else "L") if abs(d.x()) > abs(d.y()) else ("D" if d.y() > 0 else "U"))

    def moved(self) -> None:
        self._t_move = time.monotonic()
        self._t.start()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#11171A"))
        p.drawRoundedRect(r, S(12), S(12))
        g = self.game
        if g is None:
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(12, QFont.Weight.DemiBold))
            p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), tr("Press New game"))
            return
        n = g.n
        gap = S(6)
        cell = (r.width() - gap * (n + 1)) / n
        age = time.monotonic() - self._t_move
        for i, v in enumerate(g.b):
            x = r.left() + gap + (i % n) * (cell + gap)
            y = r.top() + gap + (i // n) * (cell + gap)
            box = QRectF(x, y, cell, cell)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#1C2328"))
            p.drawRoundedRect(box, S(8), S(8))
            if not v:
                continue
            k = 1.0
            if i == g.spawned and age < 0.18:
                k = 0.4 + 0.6 * (age / 0.18)
            elif i in g.merged and age < 0.2:
                k = 1.0 + 0.12 * (1 - abs(age / 0.1 - 1))
            tile = QRectF(box.center().x() - cell * k / 2, box.center().y() - cell * k / 2, cell * k, cell * k)
            col = QColor(TILE.get(v, "#FF5CC8"))
            p.setBrush(col)
            p.drawRoundedRect(tile, S(8), S(8))
            p.setPen(QColor("#FFFFFF") if v > 4 else QColor(TEXT))
            size = max(9.0, min(22.0, cell / S(1) * (0.42 if v < 100 else 0.34 if v < 1000 else 0.27)))
            p.setFont(font(size, QFont.Weight.Black))
            p.drawText(tile, int(Qt.AlignmentFlag.AlignCenter), str(v))
        if not g.can_move():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawRoundedRect(r, S(12), S(12))
            p.setPen(QColor(TEXT))
            p.setFont(font(18, QFont.Weight.ExtraBold))
            p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), tr("No more moves"))


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
        cell = min(S(28), (self.width() - S(4)) / self.w)
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
    page._back_bar(lay, title, lambda: (page.ctx.window.allow_keys(False), page.open_sub("minigames")))
    line = hbox(spacing=6)
    seg = Segmented([tr(m) for m in MODES[game]], int(getattr(page.ctx, game + "_mode", 0) or 0))
    seg.changed.connect(lambda i: page.mg_mode(game, i))
    line.addWidget(seg, 1)
    board = Button(tr("Board"), "ghost", 30, icon="trophy")
    board.setFixedWidth(max(S(86), board.sizeHint().width()))
    board.clicked.connect(lambda: page.mg_board(game))
    line.addWidget(board)
    lay.addLayout(line)


def build_2048(page, lay) -> None:
    ctx = page.ctx
    _top(page, lay, "2048", "g2048")
    mode = int(getattr(ctx, "g2048_mode", 0) or 0)
    pays = [tr("Score ÷ 40, up to 320 coins"), tr("Score ÷ 80, up to 200 coins"), tr("Score ÷ 14, up to 360 coins")][mode]
    lay.addWidget(Label(tr("Slide with the arrow keys, WASD or a swipe. Equal tiles merge.") + "  " + pays, 10, TEXT_DIM,
                        wrap_w=page.W))
    page.mg_score = Label("", 13, TEXT, bold=True)
    lay.addWidget(page.mg_score)
    side = min(page.W, S(330))
    page.board2048 = Board2048(page, side)
    page.board2048.game = getattr(ctx, "g2048_game", None)
    lay.addWidget(page.board2048, 0, Qt.AlignmentFlag.AlignHCenter)
    arrows = hbox(spacing=4)
    for m, label in (("L", "←"), ("U", "↑"), ("D", "↓"), ("R", "→")):
        b = Button(label, "ghost", 30)
        b.clicked.connect(lambda _=False, m=m: page.mg_move(m))
        arrows.addWidget(b)
    lay.addLayout(arrows)
    line = hbox(spacing=6)
    new = Button(tr("New game"), "primary", 34)
    new.clicked.connect(lambda: page.mg_start("g2048"))
    stop = Button(tr("Finish and get paid"), "ghost", 34)
    stop.clicked.connect(page.mg_finish_2048)
    line.addWidget(new, 1)
    line.addWidget(stop, 1)
    lay.addLayout(line)
    page.sync_2048()
    ctx.window.allow_keys(True)                     # the arrows reach the board while it is open
    page.board2048.setFocus()


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
        if game == "g2048":
            ctx.g2048_game, ctx.g2048_round = None, None
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
            if game == "g2048":
                ctx.g2048_round = data["id"]
                ctx.g2048_game = Game2048(int(data.get("size") or SIZES_2048[mode]), int(data["seed"]))
                if hasattr(self, "board2048"):
                    self.board2048.game = ctx.g2048_game
                    self.board2048.moved()
                    self.board2048.setFocus()
                self.sync_2048()
            else:
                ctx.sweeper_round = data["id"]
                ctx.sweeper_state = {"w": int(data["w"]), "h": int(data["h"]), "m": int(data["m"]), "shown": {}, "flags": [],
                                     "mines": [], "boom": -1, "t0": None, "over": False, "paid": None}
                ctx.reload_page()
        ctx.econ.call("rb_mg_start", {"game": game, "mode": mode}, got)

    # -- 2048
    def mg_move(self, m: str) -> None:
        g = getattr(self.ctx, "g2048_game", None)
        if g is None or not g.can_move() or getattr(self.ctx, "g2048_round", None) is None:
            return
        if g.move(m):
            self.board2048.moved()
            if g.merged:
                sfx.play("pick")
        self.sync_2048()
        if not g.can_move():
            QTimer.singleShot(600, self.mg_finish_2048)

    def sync_2048(self) -> None:
        g = getattr(self.ctx, "g2048_game", None)
        if hasattr(self, "mg_score"):
            self.mg_score.set_text(tr("Score {n}", n=g.score) + "   ·   " + tr("Best tile {n}", n=max(g.b)) if g else
                                   tr("Press New game to start"))
        if hasattr(self, "board2048"):
            self.board2048.update()

    def mg_finish_2048(self) -> None:
        ctx = self.ctx
        rid, g = getattr(ctx, "g2048_round", None), getattr(ctx, "g2048_game", None)
        if rid is None or g is None:
            return
        ctx.g2048_round = None

        def got(ok: bool, data) -> None:
            if not ok or not isinstance(data, dict):
                return ctx.toast(tr(str(data)), "warn")
            paid = int(data.get("paid") or 0)
            ctx.econ.absorb(data)
            ctx.econ.changed.emit()
            ctx.toast(tr("Score {n}", n=data.get("score")) + "  ·  " + (tr("+{n} coins", n=paid) if paid else tr("No coins this time")))
            sfx.play("on" if paid else "off")
        ctx.econ.call("rb_2048_finish", {"round": rid, "moves": g.moves}, got)

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
