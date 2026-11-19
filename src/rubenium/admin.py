"""The admin panel (only the account "Ruben" sees it, and the server checks it for every action) and the
golden Giveaway tab everyone sees while a giveaway is live."""
import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import QAbstractButton, QLineEdit, QSizePolicy, QWidget

from .bazaar import ItemGrid, KINDS
from .core import DANGER, S, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, sfx, tr, ui
from .cosmetics import item_name, paint_cosmetic
from .pages import Page
from .shop import GOLD_TEXT, clock_text
from .wallet import coins_text, paint_coin
from .widgets import present, close_embedded, Button, IconButton, Label, Segmented, hbox, heading, vbox



def en(text: str, **kw) -> str:
    """4.4: the admin panel is English only (players' screens are still translated with tr)."""
    return text.format(**kw) if kw else text


def en_name(item: str) -> str:
    """An item's name in English (the admin panel never shows French)."""
    from .core import lang, set_lang
    old = lang()
    set_lang("en")
    try:
        return item_name(item)
    finally:
        set_lang(old)


class FormDialog(QWidget):
    """A small window with a few text boxes (typing needs the keyboard, which the menu never takes)."""

    def __init__(self, ctx, title: str, fields: list, button: str, on_send, note: str = "") -> None:
        super().__init__()
        from .window import work_area
        old = getattr(ctx, "_form", None)            # keep a reference, or the window vanishes at once
        try:
            if old is not None and old.isVisible():
                old.close()
        except RuntimeError:
            pass
        ctx._form = self
        self.ctx = ctx
        self._on_send = on_send
        self.setWindowTitle("Rubenium")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedWidth(S(340))
        lay = vbox(self, 6, (18, 16, 18, 16))
        lay.addWidget(Label(title, 15, bold=True, wrap_w=S(300)))
        if note:
            lay.addWidget(Label(note, 10.5, TEXT_DIM, wrap_w=S(300)))
        self.edits: dict = {}
        style = (f"QLineEdit {{ background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10);"
                 f" border-radius: {S(8)}px; padding: 0 {S(9)}px; color: {TEXT}; font-size: {S(12)}px; }}"
                 f"QLineEdit:focus {{ border: 1px solid rgba(255,255,255,0.45); }}")
        for key, label, default in fields:
            lay.addWidget(Label(label, 10.5, TEXT_DIM))
            e = QLineEdit(str(default))
            e.setFixedHeight(S(30))
            e.setStyleSheet(style)
            e.returnPressed.connect(self._go)
            lay.addWidget(e)
            self.edits[key] = e
        self.note = Label("", 11, DANGER, wrap_w=S(300))
        lay.addWidget(self.note)
        line = hbox(spacing=6)
        cancel = Button("Cancel", "ghost", 32)
        cancel.clicked.connect(self.close)
        go = Button(button, "primary", 32)
        go.clicked.connect(self._go)
        line.addWidget(cancel, 1)
        line.addWidget(go, 1)
        lay.addLayout(line)
        self.adjustSize()
        first = next(iter(self.edits.values()), None)
        self.focus_me = first.setFocus if first is not None else None
        if present(self, ctx, keys=True):
            return
        area = work_area(ctx.window.card_global().center())
        self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)
        self.show()
        self.raise_()
        self.activateWindow()
        if self.edits:
            next(iter(self.edits.values())).setFocus()

    def close(self) -> bool:
        return close_embedded(self) or super().close()

    def say(self, text: str) -> None:
        self.note.set_text(text)

    def _go(self) -> None:
        self._on_send({k: e.text().strip() for k, e in self.edits.items()}, self)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.close()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(alpha("#FF4B6E", 0.5), 1.2))
        p.setBrush(QColor(12, 15, 16, 252))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), S(16), S(16))


def _int(text: str, default=None):
    try:
        return int(str(text).replace(" ", "").replace("+", ""))
    except ValueError:
        return default


class Numbers(QWidget):
    """A grid of big numbers with a small label under each."""

    def __init__(self, cells: list, width: int, cols: int = 3) -> None:
        super().__init__()
        self.cells, self.cols = cells, cols
        self.setFixedSize(width, int(S(44) * math.ceil(len(cells) / cols)))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width() / self.cols
        for i, (big, small, *col) in enumerate(self.cells):
            box = QRectF((i % self.cols) * w, (i // self.cols) * S(44), w, S(44)).adjusted(S(2), S(2), -S(2), -S(2))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha("#FFFFFF", 0.04))
            p.drawRoundedRect(box, S(8), S(8))
            p.setPen(QColor(col[0] if col else TEXT))
            p.setFont(font(12.5, QFont.Weight.Bold))
            p.drawText(QRectF(box.left(), box.top() + S(3), box.width(), S(20)), int(Qt.AlignmentFlag.AlignCenter), str(big))
            p.setPen(QColor(TEXT_FAINT))
            p.setFont(font(9.5, QFont.Weight.DemiBold))
            p.drawText(QRectF(box.left(), box.top() + S(22), box.width(), S(14)), int(Qt.AlignmentFlag.AlignCenter), small)


class Table(QWidget):
    """Plain rows of text: [(left, middle, right, colour)]. Click a row when on_click is given."""

    def __init__(self, rows: list, width: int, on_click=None) -> None:
        super().__init__()
        self.rows, self.on_click = rows, on_click
        self.row_h = S(24)
        self.setFixedSize(width, max(S(24), int(self.row_h * len(rows))))
        if on_click:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e) -> None:
        e.accept()
        i = int(e.position().y() // self.row_h)
        if self.on_click and 0 <= i < len(self.rows):
            sfx.play("pick")
            self.on_click(i)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i, (left, mid, right, *col) in enumerate(self.rows):
            r = QRectF(0, i * self.row_h, self.width(), self.row_h)
            if i % 2 == 0:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha("#FFFFFF", 0.035))
                p.drawRoundedRect(r.adjusted(0, 1, 0, -1), S(6), S(6))
            p.setFont(font(11, QFont.Weight.DemiBold))
            p.setPen(QColor(TEXT))
            p.drawText(r.adjusted(S(8), 0, 0, 0), int(Qt.AlignmentFlag.AlignVCenter),
                       p.fontMetrics().elidedText(str(left), Qt.TextElideMode.ElideRight, int(r.width() * 0.45)))
            p.setPen(QColor(TEXT_DIM))
            p.drawText(QRectF(r.left() + r.width() * 0.45, r.top(), r.width() * 0.3, r.height()),
                       int(Qt.AlignmentFlag.AlignVCenter), str(mid))
            p.setPen(QColor(col[0] if col else TEXT))
            p.drawText(r.adjusted(0, 0, -S(8), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), str(right))


class Chips(QWidget):
    """A grid of buttons to click instead of typing. keys: what each one stands for; picked: the lit ones."""
    toggled = pyqtSignal(object)

    def __init__(self, labels: list, keys: list, picked, per_row: int = 4, height: int = 30) -> None:
        super().__init__()
        from PyQt6.QtWidgets import QGridLayout
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(S(4))
        picked = set(picked) if isinstance(picked, (list, set)) else {picked}
        for i, (text, key) in enumerate(zip(labels, keys)):
            b = Button(text, "primary" if key in picked else "ghost", height)
            b.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            b.clicked.connect(lambda _c=False, key=key: self.toggled.emit(key))
            grid.addWidget(b, i // per_row, i % per_row)
        for c in range(per_row):
            grid.setColumnStretch(c, 1)


class KindTabs(QWidget):
    """4.5: big outlined tabs (Coins, Keys, XP, Cases, Items): the choice of what, set apart from the options below."""
    changed = pyqtSignal(int)

    def __init__(self, labels: list, index: int) -> None:
        super().__init__()
        self.labels, self.index = labels, index
        self.setFixedHeight(S(40))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e) -> None:
        e.accept()
        i = int(e.position().x() // (self.width() / len(self.labels)))
        if 0 <= i < len(self.labels) and i != self.index:
            sfx.play("pick")
            self.changed.emit(i)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(alpha("#FFFFFF", 0.35), S(1.6)))
        p.setBrush(alpha("#FFFFFF", 0.03))
        p.drawRoundedRect(r, S(10), S(10))
        w = r.width() / len(self.labels)
        for i, text in enumerate(self.labels):
            cell = QRectF(r.left() + i * w, r.top(), w, r.height())
            if i == self.index:
                p.setPen(QPen(ui.accent, S(2)))
                p.setBrush(alpha(ui.accent, 0.22))
                p.drawRoundedRect(cell.adjusted(S(3), S(3), -S(3), -S(3)), S(8), S(8))
            elif i:
                p.setPen(QPen(alpha("#FFFFFF", 0.18), 1))
                p.drawLine(QPointF(cell.left(), cell.top() + S(9)), QPointF(cell.left(), cell.bottom() - S(9)))
            p.setPen(QColor(TEXT) if i == self.index else QColor(TEXT_DIM))
            p.setFont(font(12, QFont.Weight.Black if i == self.index else QFont.Weight.Bold))
            p.drawText(cell, int(Qt.AlignmentFlag.AlignCenter), text.upper())


class CaseGrid(QWidget):
    """Every case as a picture with its name: click one."""
    picked = pyqtSignal(str)

    def __init__(self, ids: list, width: int, selected: str = "", cols: int = 5) -> None:
        super().__init__()
        self.ids, self.selected, self.cols = ids, selected, cols
        self.cw, self.ch = width / cols, S(74)
        self.setFixedSize(width, int(self.ch * max(1, math.ceil(len(ids) / cols))))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self._hover = -1

    def _at(self, pos) -> int:
        i = int(pos.y() // self.ch) * self.cols + int(pos.x() // self.cw)
        return i if 0 <= i < len(self.ids) else -1

    def mouseMoveEvent(self, e) -> None:
        i = self._at(e.position())
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = -1
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()
        i = self._at(e.position())
        if i >= 0:
            sfx.play("pick")
            self.picked.emit(self.ids[i])

    def paintEvent(self, _e) -> None:
        from .collection import CASE_NAMES, paint_case
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i, cid in enumerate(self.ids):
            r = QRectF((i % self.cols) * self.cw, (i // self.cols) * self.ch, self.cw, self.ch).adjusted(S(2), S(2), -S(2), -S(2))
            on = cid == self.selected
            p.setPen(QPen(ui.accent if on else alpha("#FFFFFF", 0.10 if i == self._hover else 0.0), S(1.6) if on else 1))
            p.setBrush(alpha(ui.accent, 0.16) if on else alpha("#FFFFFF", 0.07 if i == self._hover else 0.035))
            p.drawRoundedRect(r, S(9), S(9))
            paint_case(p, QRectF(r.center().x() - S(22), r.top() + S(6), S(44), S(36)), cid)
            p.setPen(QColor(TEXT if on else TEXT_DIM))
            p.setFont(font(9, QFont.Weight.Bold))
            name = CASE_NAMES.get(cid, cid).replace(" Case", "")
            p.drawText(QRectF(r.left() + S(2), r.bottom() - S(26), r.width() - S(4), S(24)),
                       int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap), name)


ITEM_KINDS = [("badge", "Badges"), ("ball", "Balls"), ("line", "Lines"), ("font", "Fonts"), ("theme", "Themes"),
              ("banner", "Banners"), ("frame", "Frames"), ("tag", "Tags"), ("coupon", "XP coupons")]
SINGLE_KINDS = ("theme", "banner", "frame", "tag", "coupon")          # one item per design, no colours or finishes


def item_picker(page, lay, state: dict, multi: int = 1) -> None:
    """Pick an item by clicking: a kind, then a design, then (for colours and finishes) the exact one, all on one
    screen. state['item'] holds the pick (state['items'] when multi > 1, up to multi of them)."""
    ctx, cat = page.ctx, page.ctx.econ.catalog
    kinds = [k for k, _n in ITEM_KINDS]
    kind = state.get("ikind") if state.get("ikind") in kinds else "badge"
    ch = Chips([n for _k, n in ITEM_KINDS], kinds, kind, per_row=5, height=26)

    def set_kind(k) -> None:
        state["ikind"], state["base"] = k, ""
        ctx.reload_page(page.key)
    ch.toggled.connect(set_kind)
    lay.addWidget(ch)
    chosen = set(state.get("items") or []) if multi > 1 else {state.get("item") or ""}

    def pick(item: str) -> None:
        if multi > 1:
            items = list(state.get("items") or [])
            if item in items:
                items.remove(item)
            elif len(items) < multi:
                items.append(item)
            state["items"] = items
        else:
            state["item"] = item
        ctx.reload_page(page.key)
    if kind in SINGLE_KINDS:
        ids = sorted((k for k, v in cat.items() if v.get("kind") == kind and v.get("tradeable", True)),
                     key=lambda k: (-int(cat[k].get("value") or 0), k))
        grid = ItemGrid(ctx, [{"item": k, "text": coins_text(int(cat[k].get("worth") or cat[k].get("value") or 0)),
                               "mark": k in chosen} for k in ids], page.W, 6, 64,
                        ids.index(next(iter(chosen))) if multi == 1 and next(iter(chosen)) in ids else -1, moving=False)
        grid.picked.connect(lambda i: pick(ids[i]))
        return lay.addWidget(grid)
    plain: dict = {}                                    # 4.5: each design shows its plainest (cheapest) version,
    for k in sorted(cat, key=lambda k: (int(cat[k].get("value") or 0), k)):    # not the golden one: no particle lag
        info = cat[k]
        if info.get("kind") == kind and info.get("base") not in plain:
            plain[info.get("base")] = k
    bases = sorted(plain.items(), key=lambda bk: (-max(int(v.get("value") or 0) for v in cat.values()
                                                       if v.get("kind") == kind and v.get("base") == bk[0]), bk[0]))
    base = state.get("base") or ""
    grid = ItemGrid(ctx, [{"item": k} for _b, k in bases], page.W, 8, 50,
                    next((i for i, (b, _k) in enumerate(bases) if b == base), -1), moving=False)
    grid.picked.connect(lambda i: (state.__setitem__("base", bases[i][0]), ctx.reload_page(page.key)))
    lay.addWidget(grid)
    if base:
        ids = sorted((k for k, v in cat.items() if v.get("kind") == kind and v.get("base") == base),
                     key=lambda k: -int(cat[k].get("worth") or cat[k].get("value") or 0))
        lay.addWidget(Label(en_name(ids[0]).split(" · ")[0] if ids else base, 11, TEXT_DIM, bold=True))
        g2 = ItemGrid(ctx, [{"item": k, "text": coins_text(int(cat[k].get("worth") or cat[k].get("value") or 0)),
                             "mark": k in chosen} for k in ids], page.W, 6, 64,
                      ids.index(next(iter(chosen))) if multi == 1 and next(iter(chosen)) in ids else -1, moving=False)
        g2.picked.connect(lambda i: pick(ids[i]))
        lay.addWidget(g2)


class AdminPage(Page):
    """4.4: the admin panel, rebuilt to be clicked, not typed: pick players and things from lists, see the result
    in the list. English only."""
    key = "admin"
    SECTIONS = ["Overview", "Players", "Give", "Rig", "Live", "Coinflips", "Cases", "Settings", "Locks", "Bots", "Swaps",
                "Log"]
    ICONS = ["perf", "users", "gift", "spark", "timer", "coin", "folder", "cog", "lock", "robot", "rocket", "refresh"]

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.lay = lay = vbox(self, 6)
        if not ctx.econ.admin:
            return lay.addWidget(Label("Admin only", 12, TEXT_DIM))
        tab = int(getattr(ctx, "admin_tab", 0) or 0)
        tab = tab if 0 <= tab < len(self.SECTIONS) else 0
        from .hub import NavTiles
        pick = NavTiles(list(zip(self.SECTIONS, self.ICONS)), tab, per_row=6)
        pick.changed.connect(self._section)
        lay.addWidget(pick)
        self._lockdown_row(lay)
        [self._overview, self._players, self._give, self._rig, self._live, self._flips, self._cases, self._settings,
         self._locks, self._bots, self._swaps, self._log][tab](lay)

    # -- helpers
    def state(self, name: str) -> dict:
        """A small memory per screen (what is picked), kept while the panel is open."""
        st = getattr(self.ctx, "admin_state", None)
        if st is None:
            st = self.ctx.admin_state = {}
        return st.setdefault(name, {})

    def _reload(self) -> None:
        self.ctx.admin_cache = {}
        self.ctx.reload_page("admin")

    def _section(self, i: int) -> None:
        self.ctx.admin_tab = i
        self.ctx.admin_player = None
        self.ctx.reload_page("admin")

    def _go(self, tab: str, **picks) -> None:
        """Jump to a screen with things already picked (e.g. Give with this player)."""
        for k, v in picks.items():
            self.state(tab)[k] = v
        self.ctx.admin_tab = self.SECTIONS.index(tab.capitalize())
        self.ctx.reload_page("admin")

    def _loading(self, lay) -> None:
        lay.addWidget(Label("Loading…", 12, TEXT_DIM))

    def player_chips(self, lay, st: dict, multi: bool) -> None:
        """Players to click: online first, then the most recently seen. Find… for anyone else."""
        rows = self.fetch("rb_admin_players", {"search": "", "sort": "", "page": 0})
        if rows is None:
            return self._loading(lay)
        names = [r["username"] for r in rows if not r.get("bot")][:23]
        picked = list(st.get("to") or [])
        for n in picked:
            if n not in names:
                names.insert(0, n)
        online = {r["username"] for r in rows if r.get("online")}
        labels = [("● " if n in online else "") + n for n in names] + ["Find…"]
        ch = Chips(labels, names + ["?"], picked, per_row=4, height=28)

        def toggle(n) -> None:
            if n == "?":
                return FormDialog(self.ctx, "Find a player", [("n", "Username", "")], "Pick",
                                  lambda v, d: (d.close(), toggle(v["n"].strip()) if v["n"].strip() else None))
            cur = list(st.get("to") or [])
            if n in cur:
                cur.remove(n)
            elif multi:
                cur.append(n)
            else:
                cur = [n]
            st["to"] = cur
            self.ctx.reload_page("admin")
        ch.toggled.connect(toggle)
        lay.addWidget(ch)

    def fetch(self, fn: str, args: dict):
        """Cached answer of a server question (asked again after 15 s or after Refresh)."""
        cache = getattr(self.ctx, "admin_cache", None)
        if cache is None:
            cache = self.ctx.admin_cache = {}
        key = fn + repr(sorted(args.items()))
        got = cache.get(key)
        if got is None or time.monotonic() - got[0] > 15:
            def back(ok: bool, data) -> None:
                if not ok:
                    cache[key] = (time.monotonic(), {} if fn not in ("rb_admin_audit", "rb_admin_resets", "rb_admin_rigs") else [])
                    if self.ctx.window.current == "admin" or getattr(self.ctx.window, "showing", lambda k: False)("admin"):
                        self.ctx.reload_page("admin")
                    return self.ctx.toast(str(data), "warn")
                old = cache.get(key)
                cache[key] = (time.monotonic(), data)
                if old is None or old[1] != data:
                    self.ctx.reload_page("admin")
            if got is None:
                cache[key] = (time.monotonic(), None)
            self.ctx.online.ask(fn, args, back)
        return got[1] if got else None

    def do(self, fn: str, args: dict, ok_text: str = "", after=None) -> None:
        """One admin action. The toast only says it worked once the server said so."""
        def back(ok: bool, data) -> None:
            if not ok:
                sfx.play("off")
                return self.ctx.toast("Failed: " + str(data), "warn")
            sfx.play("on")
            if ok_text:
                self.ctx.toast(ok_text)
            self.ctx.admin_cache = {}
            self.ctx.econ.refresh()
            self.ctx.econ.poll_live()
            if after:
                after()
            QTimer.singleShot(300, lambda: self.ctx.reload_page("admin"))
        self.ctx.econ.call(fn, args, back)

    def do_many(self, jobs: list, ok_text: str) -> None:
        """Several actions (one per player): say how many really worked, and which ones failed."""
        left, bad = [len(jobs)], []

        def one(fn, args, who):
            def back(ok: bool, data) -> None:
                if not ok:
                    bad.append(f"{who}: {data}")
                left[0] -= 1
                if left[0] == 0:
                    done = len(jobs) - len(bad)
                    if bad:
                        sfx.play("off")
                        self.ctx.toast(f"{ok_text}: {done} of {len(jobs)}. Failed: " + "; ".join(bad)[:160], "warn")
                    else:
                        sfx.play("on")
                        self.ctx.toast(f"{ok_text}: {done} of {len(jobs)}")
                    self.ctx.admin_cache = {}
                    self.ctx.econ.refresh()
                    QTimer.singleShot(300, lambda: self.ctx.reload_page("admin"))
            self.ctx.econ.call(fn, args, back)
        for fn, args, who in jobs:
            one(fn, args, who)

    # -- Overview
    def _overview(self, lay) -> None:
        st = self.fetch("rb_admin_stats", {})
        if st is None:
            return self._loading(lay)
        lay.addWidget(Numbers([(st.get("players", 0), "Users"), (st.get("online", 0), "Online now"), (st.get("today", 0), "Today"),
                               (coins_text(int(st.get("coins") or 0)), "Coins in total"), (st.get("keys", 0), "Keys in total"),
                               (st.get("items", 0), "Items"), (st.get("listings", 0), "On the market"),
                               (st.get("trades", 0), "Trades done"), ("", "")], self.W))
        lay.addWidget(heading("Games: bets and payouts"))
        rows = []
        for g in st.get("games") or []:
            bet, paid = int(g["bet"]), int(g["paid"])
            keep = f"{100 - 100 * paid / bet:.1f}%" if bet else "—"
            rows.append((g["game"], f"{g['rounds']} rounds", f"house {keep}", "#5BE08A" if paid <= bet else "#FF7A7A"))
        lay.addWidget(Table(rows, self.W))
        lay.addWidget(heading("Coins in and out (7 days)"))
        lay.addWidget(Table([(x["reason"], f"{x['n']} times", ("+" if int(x["coins"]) >= 0 else "") + coins_text(int(x["coins"])),
                              "#5BE08A" if int(x["coins"]) >= 0 else "#FF7A7A") for x in st.get("ledger") or []], self.W))
        w = self.fetch("rb_admin_xp_watch", {})
        if w:
            top_day = w.get("top_day") or []
            lay.addWidget(heading("Most XP in the last 24 hours"))
            lay.addWidget(Table([(x["name"], f"level {x['level']}", f"{x['xp']} XP", TEXT) for x in top_day[:10]] or
                                [("Nobody yet", "", "")], self.W, (lambda i: self._open(top_day[i]["name"])) if top_day else None))
            sus = w.get("capped_days") or []
            if sus:
                lay.addWidget(heading("Over 1 500 XP in a day, 3+ days (14 days)"))
                lay.addWidget(Table([(x["name"], f"{x['days']} days", "", "#FF7A7A") for x in sus], self.W,
                                    lambda i: self._open(sus[i]["name"])))

    # -- Players
    def _players(self, lay) -> None:
        name = getattr(self.ctx, "admin_player", None)
        if name:
            return self._player(lay, name)
        resets = self.fetch("rb_admin_resets", {}) or []
        open_ = [r for r in resets if r.get("state") == "open"]
        if open_ or getattr(self.ctx, "admin_pw", False):
            b = Button(f"Password requests ({len(open_)})" if not getattr(self.ctx, "admin_pw", False) else "Back to players",
                       "primary" if open_ else "ghost", 30, icon="key")
            b.clicked.connect(lambda: (setattr(self.ctx, "admin_pw", not getattr(self.ctx, "admin_pw", False)),
                                       self.ctx.reload_page("admin")))
            lay.addWidget(b)
            if getattr(self.ctx, "admin_pw", False):
                return self._help(lay)
        sort = int(getattr(self.ctx, "admin_sort", 0) or 0)
        seg = Segmented(["Last seen", "Coins", "Hours"], sort)
        seg.changed.connect(lambda i: (setattr(self.ctx, "admin_sort", i), self.ctx.reload_page("admin")))
        lay.addWidget(seg)
        find = Button("Find a player", "ghost", 28, icon="search")
        find.clicked.connect(lambda: FormDialog(self.ctx, "Find a player", [("n", "Username", "")], "Open",
                                                lambda v, d: (d.close(), self._open(v["n"]))))
        lay.addWidget(find)
        rows = self.fetch("rb_admin_players", {"search": "", "sort": ["", "coins", "hours"][sort], "page": 0})
        if rows is None:
            return self._loading(lay)
        table = [(("● " if r["online"] else "") + r["username"] + (" · blocked" if r["banned"] else ""),
                  f"{int(r['minutes']) / 60:.1f} h", coins_text(int(r["coins"])), "#5BE08A" if r["online"] else TEXT)
                 for r in rows]
        lay.addWidget(Table(table, self.W, lambda i: self._open(rows[i]["username"])))

    def _open(self, name: str) -> None:
        self.ctx.admin_player = name.strip()
        self.ctx.admin_tab = 1
        self.ctx.admin_pw = False
        self.ctx.reload_page("admin")

    def _player(self, lay, name: str) -> None:
        from .hub import AmountWindow, NavTiles
        top = hbox(spacing=8)
        back = IconButton("back", 30, tip="Back")
        back.clicked.connect(lambda: (setattr(self.ctx, "admin_player", None), self.ctx.reload_page("admin")))
        top.addWidget(back)
        top.addWidget(Label(name, 15, bold=True), 1)
        lay.addLayout(top)
        d = self.fetch("rb_admin_player", {"name": name})
        if d is None:
            return self._loading(lay)
        if not d:
            return lay.addWidget(Label("No such player", 12, TEXT_DIM))
        st = d.get("stats") or {}
        xp = self.fetch("rb_admin_xp_view", {"name": name}) or {}
        info = xp.get("info") or {}
        lay.addWidget(Numbers([(coins_text(int(d["coins"])), "Coins", GOLD_TEXT), (d["keys"], "Keys"),
                               (f"{int(d['minutes']) / 60:.1f} h", "Played"),
                               (f"{info.get('level', '?')}", "Level"), (coins_text(int(info.get("xp") or 0)), "XP"),
                               (f"{int(info.get('today') or 0)}", "XP today"),
                               (coins_text(int(st.get("bet") or 0)), "Bet"), (coins_text(int(st.get("won") or 0)), "Won"),
                               ("Online" if d.get("online") else "Offline", "Blocked" if d.get("banned") else "Status")],
                              self.W))
        acts = [("Give…", "gift"), ("Rig…", "spark"), ("Coins", "coin"), ("Keys", "key"), ("XP", "trophy"),
                ("Unblock" if d.get("banned") else "Block", "lock"), ("Remove picture", "trash"), ("Reset timers", "timer"),
                ("Undo last", "refresh"), ("Refresh", "refresh")]
        grid = NavTiles(acts, -1, per_row=5, select=False)

        def act(i: int) -> None:
            ctx = self.ctx
            if i == 0:
                self._go("give", to=[name])
            elif i == 1:
                self._go("rig", to=[name])
            elif i == 2:
                ctx._amount = AmountWindow(ctx, f"Coins for {name}", [100, 1000, 10000, 100000, -100, -1000, -10000, -100000],
                                           lambda n: self.do("rb_admin_grant", {"name": name, "add_coins": n, "add_keys": 0},
                                                             f"{name}: {'+' if n > 0 else ''}{coins_text(n)} coins"))
            elif i == 3:
                ctx._amount = AmountWindow(ctx, f"Keys for {name}", [1, 5, 10, 50, -1, -5, -10, -50],
                                           lambda n: self.do("rb_admin_grant", {"name": name, "add_coins": 0, "add_keys": n},
                                                             f"{name}: {n:+d} keys"))
            elif i == 4:
                ctx._amount = AmountWindow(ctx, f"XP for {name}", [100, 1000, 5000, 20000, -100, -1000, -5000, -20000],
                                           lambda n: self.do("rb_admin_xp", {"name": name, "delta": n, "reason": "admin"},
                                                             f"{name}: {n:+d} XP"))
            elif i == 5:
                ctx.window.confirm(f"Unblock {name}?" if d.get("banned") else f"Block {name}? They can't use anything online.",
                                   lambda: self.do("rb_admin_ban", {"name": name, "ban": not d.get("banned")},
                                                   f"{name} unblocked" if d.get("banned") else f"{name} blocked"), yes="Yes")
            elif i == 6:
                ctx.window.confirm(f"Remove {name}'s picture?",
                                   lambda: self.do("rb_admin_avatar_clear", {"name": name}, "Picture removed"), yes="Remove")
            elif i == 7:
                self.do("rb_admin_reset_timers", {"name": name}, f"{name}: free spin and scratch card ready")
            elif i == 8:
                self._undo_last(name)
            else:
                self._reload()
        grid.changed.connect(act)
        lay.addWidget(grid)
        stock = d.get("stock") or {}
        if stock:
            from .collection import CASE_NAMES
            lay.addWidget(Label("Gifted cases: " + ", ".join(f"{CASE_NAMES.get(k, k)} ×{n}" for k, n in stock.items()),
                                10.5, TEXT_DIM, wrap_w=self.W))
        items = d.get("items") or []
        lay.addWidget(heading(f"Items ({len(items)})"))
        if items:
            ig = ItemGrid(self.ctx, [{"item": i["item"], "text": "🔒" if i.get("locked") else ""} for i in items[:120]],
                          self.W, 8, 56, moving=False)

            def take(i: int) -> None:
                it = items[i]
                self.ctx.window.confirm(f"Take {en_name(it['item'])} from {name}?",
                                        lambda: self.do("rb_admin_take", {"item_id": it["id"]}, "Taken"), yes="Take one",
                                        no="Take every copy",
                                        on_no=lambda: self.do("rb_admin_revoke", {"name": name, "what": it["item"]}, "Taken"))
            ig.picked.connect(take)
            lay.addWidget(ig)
        deals = self.fetch("rb_admin_deals", {"name": name})
        lay.addWidget(heading("Trades and sales"))
        if deals is None:
            self._loading(lay)
        else:
            rows = []
            for t in deals.get("trades") or []:
                gave = len(t.get("a_items") or []), len(t.get("b_items") or [])
                rows.append(("trade", t, (f"Trade {t['a']} ⇄ {t['b']}",
                                         f"{gave[0]}+{coins_text(int(t['a_coins']))} / {gave[1]}+{coins_text(int(t['b_coins']))}",
                                         "undone" if t.get("undone") else str(t.get("at", ""))[5:16].replace("T", " "),
                                         TEXT_DIM if t.get("undone") else TEXT)))
            for l_ in deals.get("sales") or []:
                rows.append(("sale", l_, (f"Sale {l_['seller']} → {l_.get('buyer') or '?'}", en_name(l_["what"])[:14],
                                         "undone" if l_.get("undone") else coins_text(int(l_["price"])),
                                         TEXT_DIM if l_.get("undone") else GOLD_TEXT)))

            def undo_deal(i: int) -> None:
                kind, dd, _row = rows[i]
                if dd.get("undone"):
                    return self.ctx.toast("Already undone", "warn")
                fn, arg = ("rb_admin_undo_trade", {"trade": dd["id"]}) if kind == "trade" else ("rb_admin_undo_sale", {"listing": dd["id"]})
                self.ctx.window.confirm("Undo this? Items and coins go back to who had them.",
                                        lambda: self.do(fn, arg, "Undone"), yes="Undo")
            lay.addWidget(Table([r[2] for r in rows], self.W, undo_deal) if rows else Label("None", 11, TEXT_DIM))
        lay.addWidget(heading("Last rounds"))
        lay.addWidget(Table([(r["game"], en_name(r["item"]) if r.get("item") else coins_text(int(r["bet"])),
                              "+" + coins_text(int(r["paid"])), "#5BE08A" if int(r["paid"]) > int(r["bet"]) else TEXT_DIM)
                             for r in (d.get("rounds") or [])[:30]], self.W))
        lay.addWidget(heading("Coin history"))
        lay.addWidget(Table([(l_["reason"], str(l_.get("ref") or "")[:18],
                              ("+" if int(l_["coins"]) >= 0 else "") + coins_text(int(l_["coins"]))
                              + (f"  {int(l_['keys']):+d} keys" if int(l_.get("keys") or 0) else ""),
                              "#5BE08A" if int(l_["coins"]) >= 0 else "#FF7A7A") for l_ in (d.get("ledger") or [])[:40]], self.W))
        self._danger(lay, name, d)

    # -- Give: players, then what, then one button
    GIVE_KINDS = [("coins", "Coins"), ("keys", "Keys"), ("xp", "XP"), ("case", "Cases"), ("item", "Items")]
    AMOUNTS = {"coins": [100, 500, 1000, 5000, 10000, 50000, 100000, 1000000], "keys": [1, 2, 3, 5, 10, 20, 50, 100],
               "xp": [100, 500, 1000, 2500, 5000, 10000, 25000, 100000]}

    def _give(self, lay) -> None:
        st = self.state("give")
        lay.addWidget(heading("To"))
        self.player_chips(lay, st, multi=True)
        lay.addWidget(heading("What"))
        kind = st.get("kind") or "case"
        keys = [k for k, _n in self.GIVE_KINDS]          # 4.5: tabs, clearly not like the buttons under them
        kc = KindTabs([n for _k, n in self.GIVE_KINDS], keys.index(kind) if kind in keys else 0)
        kc.changed.connect(lambda i: (st.__setitem__("kind", keys[i]), self.ctx.reload_page("admin")))
        lay.addWidget(kc)
        if kind in self.AMOUNTS:
            take = bool(st.get("take"))
            mode = Segmented(["Give", "Take away"], 1 if take else 0)
            mode.changed.connect(lambda i: (st.__setitem__("take", i == 1), self.ctx.reload_page("admin")))
            lay.addWidget(mode)
            amts = self.AMOUNTS[kind]
            amount = self._slide(lay, st, kind + "_n", "How much", 1, amts[-1], amts[2], coins_text)
            what = f"{'−' if take else '+'}{coins_text(amount)} {self.dict_name(kind)}"
        else:
            if kind == "case":
                ids = [c["id"] for c in self.ctx.econ.cases]
                cg = CaseGrid(ids, self.W, st.get("case") or "")
                cg.picked.connect(lambda cid: (st.__setitem__("case", cid), self.ctx.reload_page("admin")))
                lay.addWidget(cg)
                from .collection import CASE_NAMES
                thing = CASE_NAMES.get(st.get("case") or "", "") if st.get("case") else ""
            else:
                item_picker(self, lay, st)
                thing = en_name(st["item"]) if st.get("item") else ""
            n = self._slide(lay, st, "count", "How many", 1, 100, 1)
            what = f"{n} × {thing}" if thing else ""
        to = list(st.get("to") or [])
        ready = bool(to and what)
        label = (f"Give {what} to {', '.join(to) if len(to) <= 3 else str(len(to)) + ' players'}" if ready else
                 "Pick who, then what")
        if kind in self.AMOUNTS and st.get("take") and ready:
            label = f"Take {what.lstrip('−')} from {', '.join(to) if len(to) <= 3 else str(len(to)) + ' players'}"
        go = Button(label, "primary" if ready else "ghost", 40, icon="gift")
        go.setEnabled(ready)
        go.clicked.connect(lambda: self._give_now(st))
        lay.addWidget(go)

    @staticmethod
    def dict_name(kind: str) -> str:
        return {"coins": "coins", "keys": "keys", "xp": "XP"}.get(kind, kind)

    def _give_now(self, st: dict) -> None:
        kind, to = st.get("kind") or "case", list(st.get("to") or [])
        jobs = []
        if kind in self.AMOUNTS:
            amts = self.AMOUNTS[kind]
            v = st.get(kind + "_n")
            n = (v if isinstance(v, int) and 1 <= v <= amts[-1] else amts[2]) * (-1 if st.get("take") else 1)
            for name in to:
                if kind == "coins":
                    jobs.append(("rb_admin_grant", {"name": name, "add_coins": n, "add_keys": 0}, name))
                elif kind == "keys":
                    jobs.append(("rb_admin_grant", {"name": name, "add_coins": 0, "add_keys": n}, name))
                else:
                    jobs.append(("rb_admin_xp", {"name": name, "delta": n, "reason": "admin"}, name))
            text = "Done"
        else:
            what = ("case:" + st["case"]) if kind == "case" else st.get("item")
            count = st.get("count") or 1
            for name in to:
                jobs.append(("rb_admin_give", {"name": name, "what": what, "how_many": count}, name))
            text = "Given"
        self.do_many(jobs, text)

    # -- Rig: the next result of one player
    RIG_KINDS = [("wheel", "Free spin"), ("scratch", "Scratch card"), ("case", "Case"), ("slots", "Slots"),
                 ("dice", "Dice"), ("flip", "Coinflip vs bot")]
    WHEEL = ["40 coins", "75 coins", "120 coins", "180 coins", "300 coins", "500 coins", "1 200 coins", "A key",
             "Golden Wheel", "XP coupon"]
    SCRATCH = [("standard", "80-160 coins"), ("rare", "220-420 coins"), ("special", "Key + XP coupon"),
               ("epic", "2 keys + coupon"), ("exotic", "2 500 coins + coupon"), ("golden", "Golden Wheel")]
    SLOTS = [(("gem",) * 3, "3 gems ×70"), (("seven",) * 3, "3 sevens ×30"), (("bell",) * 3, "3 bells ×15"),
             (("lemon",) * 3, "3 lemons ×8"), (("cherry",) * 3, "3 cherries ×5"), (("gem", "gem", "lemon"), "2 gems ×4"),
             (("seven", "cherry", "seven"), "2 sevens ×2"), (("lemon", "bell", "bell"), "2 bells ×2"),
             (("cherry", "lemon", "bell"), "Lose")]

    def _rig(self, lay) -> None:
        st = self.state("rig")
        lay.addWidget(heading("Player"))
        self.player_chips(lay, st, multi=False)
        lay.addWidget(heading("Game"))
        kind = st.get("kind") or "wheel"
        kc = Chips([n for _k, n in self.RIG_KINDS], [k for k, _n in self.RIG_KINDS], kind, per_row=3)
        kc.toggled.connect(lambda k: (st.__setitem__("kind", k), st.__setitem__("pick", None), self.ctx.reload_page("admin")))
        lay.addWidget(kc)
        lay.addWidget(heading("Next result"))
        pick = st.get("pick")
        key, data, what = "", None, ""
        set_pick = (lambda v: (st.__setitem__("pick", v), self.ctx.reload_page("admin")))
        if kind == "wheel":
            ch = Chips(self.WHEEL, list(range(10)), pick, per_row=5)
            ch.toggled.connect(set_pick)
            lay.addWidget(ch)
            if isinstance(pick, int):
                data, what = {"slot": pick}, self.WHEEL[pick]
        elif kind == "scratch":
            ch = Chips([n for _k, n in self.SCRATCH], [k for k, _n in self.SCRATCH], pick, per_row=3)
            ch.toggled.connect(set_pick)
            lay.addWidget(ch)
            if pick in dict(self.SCRATCH):
                data, what = {"tier": pick}, dict(self.SCRATCH)[pick]
        elif kind == "case":
            cases = [c for c in self.ctx.econ.cases]
            ids = [c["id"] for c in cases]
            cg = CaseGrid(ids, self.W, st.get("case") or "")
            cg.picked.connect(lambda cid: (st.__setitem__("case", cid), st.__setitem__("pick", None), self.ctx.reload_page("admin")))
            lay.addWidget(cg)
            case = next((c for c in cases if c["id"] == st.get("case")), None)
            if case is not None:
                from .collection import CASE_NAMES, case_drops
                key = case["id"]
                lo, hi = int(case.get("coin_min") or 0), int(case.get("coin_max") or 0)
                if hi:
                    coin_opts = sorted({lo, (lo + hi) // 2, hi, hi * 3})
                    lay.addWidget(Label("Coins", 10.5, TEXT_DIM, bold=True))
                    cc = Chips([coins_text(v) + (" (lucky ×3)" if v == hi * 3 else "") for v in coin_opts],
                               [("coins", v) for v in coin_opts], pick if isinstance(pick, tuple) else None, per_row=4)
                    cc.toggled.connect(set_pick)
                    lay.addWidget(cc)
                drops = case_drops(self.ctx.econ, case, exact=True)
                drops.sort(key=lambda x: x[1])
                # 4.6: every design the case can drop, then every exact version of it (colour, finish)
                chance = dict(drops)
                cat = self.ctx.econ.catalog
                groups: dict = {}
                for it, _c in drops:
                    info = cat.get(it) or {}
                    groups.setdefault((info.get("kind"), info.get("base")), []).append(it)
                order = sorted(groups, key=lambda g: min(chance[i] for i in groups[g]))
                firsts = [min(groups[g], key=lambda i: int((cat.get(i) or {}).get("value") or 0)) for g in order]
                sel = st.get("rig_base")
                sel = tuple(sel) if isinstance(sel, (list, tuple)) and tuple(sel) in groups else None
                lay.addWidget(Label(f"Design ({len(order)})", 10.5, TEXT_DIM, bold=True))
                bg = ItemGrid(self.ctx, [{"item": it, "mark": sel == g} for it, g in zip(firsts, order)], self.W, 8, 56,
                              order.index(sel) if sel in order else -1, moving=False)
                bg.picked.connect(lambda i: (st.__setitem__("rig_base", order[i]), st.__setitem__("pick", None),
                                             self.ctx.reload_page("admin")))
                lay.addWidget(bg)
                if sel is not None:
                    vs = sorted(groups[sel], key=lambda i: chance[i])
                    lay.addWidget(Label(f"Exact version ({len(vs)})", 10.5, TEXT_DIM, bold=True))
                    ig = ItemGrid(self.ctx, [{"item": it, "text": f"{chance[it] * 100:.3g}%", "mark": pick == ("item", it)}
                                             for it in vs], self.W, 8, 60,
                                  next((i for i, it in enumerate(vs) if pick == ("item", it)), -1), moving=False)
                    ig.picked.connect(lambda i: set_pick(("item", vs[i])))
                    lay.addWidget(ig)
                if isinstance(pick, tuple):
                    if pick[0] == "coins":
                        data, what = {"coins": pick[1]}, f"{coins_text(pick[1])} coins from a {CASE_NAMES.get(key, key)}"
                    else:
                        data, what = {"item": pick[1]}, f"{en_name(pick[1])} from a {CASE_NAMES.get(key, key)}"
        elif kind == "slots":
            ch = Chips([n for _r, n in self.SLOTS], list(range(len(self.SLOTS))), pick, per_row=3)
            ch.toggled.connect(set_pick)
            lay.addWidget(ch)
            if isinstance(pick, int):
                data, what = {"reels": list(self.SLOTS[pick][0])}, "Slots: " + self.SLOTS[pick][1]
        else:
            ch = Chips(["Win", "Lose"], [True, False], pick, per_row=2)
            ch.toggled.connect(set_pick)
            lay.addWidget(ch)
            if isinstance(pick, bool):
                data, what = {"win": pick}, ("Dice: " if kind == "dice" else "Coinflip vs bot: ") + ("win" if pick else "lose")
        to = (st.get("to") or [None])[0]
        ready = bool(to and data is not None)
        go = Button(f"Rig {to}'s next: {what}" if ready else "Pick a player and a result", "primary" if ready else "ghost",
                    40, icon="spark")
        go.setEnabled(ready)
        go.clicked.connect(lambda: self.do("rb_admin_rig", {"name": to, "kind": kind, "key": key, "data": data},
                                           f"Rigged: {to}'s next {what}",
                                           after=lambda: st.__setitem__("pick", None)))
        lay.addWidget(go)
        rigs = self.fetch("rb_admin_rigs", {})
        lay.addWidget(heading("Waiting rigs"))
        if rigs is None:
            return self._loading(lay)
        if not rigs:
            return lay.addWidget(Label("None", 11, TEXT_DIM))

        def describe(r: dict) -> str:
            k, dd = r.get("kind"), r.get("data") or {}
            if k == "wheel":
                return "Free spin: " + self.WHEEL[int(dd.get("slot", 0))]
            if k == "scratch":
                return "Scratch: " + dict(self.SCRATCH).get(dd.get("tier"), "?")
            if k == "case":
                from .collection import CASE_NAMES
                c = CASE_NAMES.get(r.get("key"), r.get("key"))
                return f"{c}: " + (en_name(dd["item"]) if dd.get("item") else f"{coins_text(int(dd.get('coins') or 0))} coins")
            if k == "slots":
                return "Slots: " + next((n for rr, n in self.SLOTS if list(rr) == dd.get("reels")), "/".join(dd.get("reels") or []))
            if k == "gold":
                return "Free spin or scratch: Golden Wheel"
            return ("Dice: " if k == "dice" else "Coinflip: ") + ("win" if dd.get("win") else "lose")

        def remove(i: int) -> None:
            r = rigs[i]
            if r.get("kind") == "gold":
                return self.do("rb_admin_rig_gold", {"name": r["name"], "rig": False}, "Rig removed")
            self.do("rb_admin_rig", {"name": r["name"], "kind": r["kind"], "key": r.get("key") or "", "data": None}, "Rig removed")
        lay.addWidget(Table([(r["name"], describe(r)[:40], "remove", "#FF7A7A") for r in rigs], self.W, remove))

    # -- Live: giveaways and sales, set up by clicking
    def _live(self, lay) -> None:
        live = self.ctx.econ.live
        st = self.state("live")
        mode = st.get("mode") or "giveaway"
        seg = Segmented(["New giveaway", "New sale"], 0 if mode == "giveaway" else 1)
        seg.changed.connect(lambda i: (st.__setitem__("mode", "giveaway" if i == 0 else "sale"), self.ctx.reload_page("admin")))
        lay.addWidget(seg)
        if mode == "giveaway":
            self._giveaway_form(lay, self.state("giveaway"))
        else:
            self._sale_form(lay, self.state("sale"))
        lay.addWidget(heading("Giveaways now"))
        gs = live.get("giveaways") or []
        if not gs:
            lay.addWidget(Label("None", 11, TEXT_FAINT))
        for g in gs:
            lay.addWidget(Label(f"{g['title']} · {g['state']} · {g.get('entries', 0)} joined · {clock_text(int(g.get('left') or 0))}",
                                11.5, TEXT, wrap_w=self.W))
            if g["state"] == "live":
                l2 = hbox(spacing=6)
                draw = Button("Draw now", "primary", 28)
                draw.clicked.connect(lambda _=False, x=g: self.do("rb_admin_giveaway_end", {"giveaway": x["id"], "draw": True}, "Drawn"))
                stop = Button("Cancel", "ghost", 28)
                stop.clicked.connect(lambda _=False, x=g: self.do("rb_admin_giveaway_end", {"giveaway": x["id"], "draw": False}, "Cancelled"))
                l2.addWidget(draw, 1)
                l2.addWidget(stop, 1)
                lay.addLayout(l2)
        lay.addWidget(heading("Sales now"))
        ss = live.get("sales") or []
        if not ss:
            lay.addWidget(Label("None", 11, TEXT_FAINT))
        for s in ss:
            l3 = hbox(spacing=6)
            l3.addWidget(Label(f"-{s['pct']}%  {s['what']}  · {clock_text(int(s.get('left') or 0))}", 11.5, TEXT), 1)
            end = Button("End", "ghost", 28)
            end.clicked.connect(lambda _=False, x=s: self.do("rb_admin_sale_end", {"sale": x["id"]}, "Sale ended"))
            l3.addWidget(end)
            lay.addLayout(l3)

    def _choice(self, lay, st: dict, key: str, title: str, opts: list, default, fmt=str, per_row: int = 5):
        if len(opts) > 3 and all(isinstance(o, int) and not isinstance(o, bool) for o in opts):
            return self._slide(lay, st, key, title, min(opts), max(opts), default, fmt)
        lay.addWidget(Label(title, 10.5, TEXT_DIM, bold=True))
        cur = st.get(key) if st.get(key) in opts else default
        ch = Chips([fmt(o) for o in opts], opts, cur, per_row=per_row, height=28)
        ch.toggled.connect(lambda v: (st.__setitem__(key, v), self.ctx.reload_page("admin")))
        lay.addWidget(ch)
        return cur

    def _slide(self, lay, st: dict, key: str, title: str, lo: int, hi: int, default: int, fmt=str) -> int:
        """4.5: a value is picked on a slider of round numbers, not from a row of buttons."""
        from .widgets import AmountSlider
        cur = st.get(key)
        cur = cur if isinstance(cur, int) and lo <= cur <= hi else default
        sl = AmountSlider(title, lo, hi, cur, lambda v: str(fmt(v)), label_w=110)
        sl.released.connect(lambda v: (st.__setitem__(key, int(v)), self.ctx.reload_page("admin")))
        lay.addWidget(sl)
        return sl.value()

    def _giveaway_form(self, lay, st: dict) -> None:
        kind = self._choice(lay, st, "kind", "Prize", ["coins", "keys", "case", "item"], "coins",
                            lambda k: {"coins": "Coins", "keys": "Keys", "case": "A case", "item": "An item"}[k], 4)
        what, thing = "", ""
        if kind in ("coins", "keys"):
            opts = [500, 1000, 5000, 10000, 50000, 100000] if kind == "coins" else [1, 2, 5, 10, 20, 50]
            amount = self._choice(lay, st, kind + "_n", "Each winner gets", opts, opts[1], coins_text, 6)
            thing = f"{coins_text(amount)} {kind}"
        else:
            if kind == "case":
                cg = CaseGrid([c["id"] for c in self.ctx.econ.cases], self.W, st.get("case") or "")
                cg.picked.connect(lambda cid: (st.__setitem__("case", cid), self.ctx.reload_page("admin")))
                lay.addWidget(cg)
                what = st.get("case") or ""
                from .collection import CASE_NAMES
                thing = CASE_NAMES.get(what, "")
            else:
                item_picker(self, lay, st)
                what = st.get("item") or ""
                thing = en_name(what) if what else ""
            amount = self._choice(lay, st, "count", "Each winner gets", [1, 2, 3, 5, 10], 1, str, 5)
        winners = self._choice(lay, st, "winners", "Winners", [1, 2, 3, 5, 10, 20], 1, str, 6)
        minutes = self._choice(lay, st, "minutes", "Lasts", [5, 15, 30, 60, 120, 240], 30, lambda m: f"{m} min", 6)
        hours = self._choice(lay, st, "hours", "Only for players with at least", [0, 1, 5, 10, 25, 50], 0,
                             lambda h: "anyone" if h == 0 else f"{h} h", 6)
        ready = bool(thing)
        prize = f"{amount} × {thing}" if kind in ("case", "item") else thing
        go = Button(f"Start: {prize} for {winners} winner{'s' if winners > 1 else ''}, {minutes} min"
                    if ready else "Pick a prize", "primary" if ready else "ghost", 40, icon="gift")
        go.setEnabled(ready)
        go.clicked.connect(lambda: self.do("rb_admin_giveaway", {
            "title": "Giveaway", "kind": kind, "what": what, "amount": int(amount), "winners": int(winners),
            "minutes": int(minutes), "min_hours": int(hours)}, "Giveaway live"))
        lay.addWidget(go)

    def _sale_form(self, lay, st: dict) -> None:
        cat = self.ctx.econ.catalog
        scope = self._choice(lay, st, "scope", "On sale", ["all", "one"], "all",
                             lambda s: "A whole kind or design" if s == "all" else "One exact item", 2)
        if scope == "all":
            kinds = [k for k, _n in ITEM_KINDS if k not in ("tag", "coupon")]
            kind = self._choice(lay, st, "skind", "Kind", kinds, "theme", lambda k: dict(ITEM_KINDS)[k], 4)
            bases = []
            for k in sorted(cat, key=lambda k: (int(cat[k].get("value") or 0), k)):     # 4.5: plainest version as the icon
                v = cat[k]
                if v.get("kind") == kind and v.get("price") is not None and (kind, v.get("base")) not in [(kind, b) for b, _ in bases]:
                    bases.append((v.get("base"), k))
            lay.addWidget(Label("Design", 10.5, TEXT_DIM, bold=True))
            base = st.get("sbase") or ""
            grid = ItemGrid(self.ctx, [{"item": k} for _b, k in bases], self.W, 8, 50,
                            next((i for i, (b, _k) in enumerate(bases) if b == base), -1), moving=False)
            grid.picked.connect(lambda i: (st.__setitem__("sbase", "" if bases[i][0] == base else bases[i][0]), self.ctx.reload_page("admin")))
            lay.addWidget(grid)
            what = f"{kind}:{base}" if base else kind
            thing = (en_name(next(k for b, k in bases if b == base)).split(" · ")[0] + " (every colour)") if base else \
                f"every {dict(ITEM_KINDS)[kind].lower()[:-1]}"
        else:
            item_picker(self, lay, st)
            what = st.get("item") or ""
            thing = en_name(what) if what else ""
        pct = self._choice(lay, st, "pct", "Off", [10, 20, 25, 30, 40, 50], 25, lambda p: f"-{p}%", 6)
        minutes = self._choice(lay, st, "minutes", "Lasts", [30, 60, 120, 240, 480, 1440], 120,
                               lambda m: f"{m // 60} h" if m >= 60 else f"{m} min", 6)
        ready = bool(what)
        go = Button(f"Start: -{pct}% on {thing}" if ready else "Pick what goes on sale", "primary" if ready else "ghost", 40)
        go.setEnabled(ready)
        go.clicked.connect(lambda: self.do("rb_admin_sale", {"what": what, "pct": int(pct), "minutes": int(minutes)}, "Sale live"))
        lay.addWidget(go)

    # -- Coinflips: Rubenium offers, picked by clicking
    def _flips(self, lay) -> None:
        st = self.state("flip")
        lay.addWidget(heading("New Rubenium offer"))
        how = self._choice(lay, st, "how", "Stake", ["value", "items"], "value",
                           lambda h: "A value (items picked for it)" if h == "value" else "Items I pick", 2)
        if how == "value":
            val = self._choice(lay, st, "val", "Worth about", [1000, 5000, 10000, 25000, 50000, 100000, 500000, 1000000],
                               10000, coins_text, 4)
            items = []
        else:
            item_picker(self, lay, st, multi=6)
            items = list(st.get("items") or [])
            val = 0
            lay.addWidget(Label(f"{len(items)} of 6 picked: " + ", ".join(en_name(i) for i in items) if items else
                                "", 10.5, GOLD_TEXT if items else TEXT_DIM, wrap_w=self.W))
        bot = self._choice(lay, st, "bot", "Shown as", ["", "Pixel", "Milo", "Biscuit", "Tango", "Pebble", "Nova", "Juno", "Orbit", "Kiwi", "Rocket", "Vega", "Atlas", "Titan", "Onyx", "Blaze"], "",
                           lambda b: b or "Random bot", 4)
        side = self._choice(lay, st, "side", "Side", ["", "black", "white"], "", lambda s: s.capitalize() or "Random", 3)
        minutes = self._choice(lay, st, "minutes", "Open for", [15, 30, 60, 120, 240, 1440], 60,
                               lambda m: f"{m // 60} h" if m >= 60 else f"{m} min", 6)
        ready = bool(items) or how == "value"
        go = Button("Publish the offer" if ready else "Pick items", "primary" if ready else "ghost", 40, icon="coin")
        go.setEnabled(ready)
        go.clicked.connect(lambda: self.do("rb_admin_flip_offer", {"bot": bot, "items": items, "val": int(val),
                                                                   "side": side or None, "minutes": int(minutes)},
                                           "Offer published", after=lambda: st.__setitem__("items", [])))
        lay.addWidget(go)
        rows = self.fetch("rb_admin_flips", {})
        if rows is None:
            return self._loading(lay)
        if not isinstance(rows, list) or not rows:
            return lay.addWidget(Label("No bot coinflips right now", 11, TEXT_FAINT))
        live = [r for r in rows if r.get("state") in ("setup", "open", "joined", "locked")]
        old = [r for r in rows if r not in live]
        lay.addWidget(heading(f"Open now · {len(live)}"))
        for r in live:
            self._flip_row(lay, r)
        if old:
            lay.addWidget(heading("Last 24 hours"))
            lay.addWidget(Table([((r.get("a") or "?") + " · " + (r.get("b") or "-"), r.get("state") or "",
                                  (f"won by {r['winner']}" if r.get("winner") else ""), TEXT_DIM) for r in old[:30]], self.W))

    def _lockdown_row(self, lay) -> None:
        """4.0: the big LOCKDOWN button (it took the place of the old lock). Everything stops on the server at once:
        open trades, coinflips, golf matches and casino rounds are cancelled with no winner and no loser."""
        on = bool(self.ctx.econ.locks.get("lockdown"))
        bar = LockdownBar(on)

        def flip() -> None:
            if on:
                text = en("Lift the lockdown? Everything that is not locked on its own opens again for everyone.")
                return self.ctx.window.confirm(text, lambda: self._lockdown(False), yes=en("Lift lockdown"))
            text = en("LOCKDOWN: stop everything for everyone now? Open trades, coinflips, Mini Golf matches and "
                      "casino rounds are cancelled and given back. Nobody wins or loses anything.")
            self.ctx.window.confirm(text, lambda: self._lockdown(True), yes=en("LOCKDOWN"))
        bar.clicked.connect(flip)
        lay.addWidget(bar)

    def _lockdown(self, lock: bool) -> None:
        def back(ok: bool, data) -> None:
            if not ok:
                sfx.play("off")
                return self.ctx.toast(en(str(data)), "warn")
            sfx.play("on")
            self.ctx.toast(en("Lockdown on: everything is stopped") if lock else en("Lockdown lifted"),
                           "warn" if lock else "ok")
            self.ctx.admin_cache = {}
            self.ctx.econ.take_locks({"lockdown": lock, "locked": [f["name"] for f in (data or {}).get("features") or []
                                                                  if not f.get("on")]})
            self.ctx.econ.poll_live()
            QTimer.singleShot(200, lambda: self.ctx.reload_page("admin"))
        self.ctx.econ.call("rb_admin_lockdown", {"lock": lock}, back)

    # -- sections

    RESETS = [("inventory", "Reset inventory",
               "Deletes EVERY item {name} owns: all badges, balls, lines, fonts, themes, banners and frames. Items on the "
               "market or in a trade are taken back first. Coins, keys, cases and the OG tag stay."),
              ("money", "Reset coins and keys", "Sets {name}'s coins and keys to 0. Items and cases stay."),
              ("cases", "Reset gifted cases", "Deletes every gifted case {name} has not opened yet. Nothing else changes."),
              ("all", "FULL ACCOUNT RESET",
               "{name} starts again like a new account: every item deleted, coins and keys back to the start (500 coins, "
               "3 keys), gifted cases deleted, login streak back to 0. Time played, friends, name and the OG tag stay.")]

    def _danger(self, lay, name: str, d: dict) -> None:
        """Big red reset buttons. Each says exactly what it deletes, asks you to type the name, and can be undone
        from the Log."""
        lay.addWidget(heading("Danger zone"))
        for what, title, text in self.RESETS:
            b = Button(en(title), "danger", 40 if what == "all" else 34, icon="trash")
            b.clicked.connect(lambda _c=False, what=what, title=title, text=text: self._reset(name, what, title, text))
            lay.addWidget(b)

    def _reset(self, name: str, what: str, title: str, text: str) -> None:
        def go(v, dlg) -> None:
            if v["n"].strip().lower() != name.lower():
                return dlg.say(en("Type {name} exactly to confirm", name=name))
            dlg.close()
            self.do("rb_admin_reset", {"name": name, "what": what}, en("Done. You can undo it in the Log."))
        FormDialog(self.ctx, en(title) + f" · {name}", [("n", en("Type the username to confirm: {name}", name=name), "")],
                   en("Reset"), go, note=en(text, name=name))

    def _undo_last(self, name: str) -> None:
        rows = self.fetch("rb_admin_audit", {}) or []
        last = next((r for r in rows if (r.get("target") or "").lower() == name.lower() and r.get("can_undo")), None)
        if last is None:
            return self.ctx.toast(en("Nothing to undo for {name}", name=name), "warn")
        self.ctx.window.confirm(en("Undo “{what}” on {target}?", what=last["action"], target=name),
                                lambda: self.do("rb_admin_undo", {"entry": last["id"]}, en("Undone")), yes=en("Undo"))

    def _cases(self, lay) -> None:
        from .collection import CASE_NAMES
        st = self.fetch("rb_admin_stats", {})
        if st is None:
            return lay.addWidget(Label(en("Loading…"), 12, TEXT_DIM))
        cases = st.get("cases") or []

        def edit(i: int) -> None:
            c = cases[i]
            fields = [("p", en("Price"), c["price"])]
            if not c.get("grid"):                         # 4.7: badge cases follow the fixed odds table
                fields += [("o", en("Drop odds (6 numbers, total 10 000)"), ",".join(map(str, c["odds"]))),
                           ("v", en("Finish odds (5 numbers, total 100 000)"), ",".join(map(str, c["variants"])))]
            fields += [("a", en("Coins: lowest"), c["coin_min"]), ("b", en("Coins: highest"), c["coin_max"])]
            FormDialog(self.ctx, en(CASE_NAMES.get(c["id"], c["id"])), fields, en("Save"),
                       lambda v, dlg: self._save_case(c, v, dlg))
        lay.addWidget(Table([(en(CASE_NAMES.get(c["id"], c["id"])), coins_text(int(c["price"])),
                              f"L {c['odds'][4] / 100:g}% · M {c['odds'][5] / 100:g}%") for c in cases], self.W, edit))

    def _save_case(self, c: dict, v: dict, dlg) -> None:
        cid = c["id"]
        try:
            odds = [int(x) for x in v["o"].split(",")] if "o" in v else list(c["odds"])
            var = [int(x) for x in v["v"].split(",")] if "v" in v else list(c["variants"])
        except ValueError:
            return dlg.say(en("Numbers separated by commas"))
        if len(odds) != 6 or sum(odds) != 10000 or len(var) != 5 or sum(var) != 100000:
            return dlg.say(en("Drop odds: 6 numbers, total 10 000. Finish odds: 5 numbers, total 100 000."))
        dlg.close()
        self.do("rb_admin_case", {"which": cid, "new_price": _int(v["p"], 1), "new_odds": odds, "new_variants": var,
                                  "new_min": _int(v["a"], 0), "new_max": _int(v["b"], 0)}, en("Saved"))

    def _settings(self, lay) -> None:
        st = self.fetch("rb_admin_stats", {})
        if st is None:
            return lay.addWidget(Label(en("Loading…"), 12, TEXT_DIM))
        cfg = st.get("config") or {}
        keys = sorted(k for k in cfg if k != "reset_008")
        force = Button(en("Everyone must update to my version"), "ghost", 30, icon="refresh")
        force.setToolTip(en("Older versions can no longer play online until they update"))
        force.clicked.connect(lambda: self.ctx.window.confirm(
            en("Lock online play for older versions of Rubenium?"), lambda: self.do("rb_admin_force_update", {}, en("Done")),
            yes=en("Yes")))
        lay.addWidget(force)

        def edit(i: int) -> None:
            k = keys[i]
            FormDialog(self.ctx, k, [("v", en("New value"), cfg[k])], en("Save"),
                       lambda v, dlg: self._save_setting(k, v["v"], dlg))
        lay.addWidget(Table([(k, "", str(cfg[k])) for k in keys], self.W, edit))

    def _save_setting(self, key: str, text: str, dlg) -> None:
        try:
            value = float(text.replace(",", "."))
        except ValueError:
            return dlg.say(en("A number"))
        dlg.close()
        self.do("rb_admin_set", {"setting": key, "new_value": value}, en("Saved"))

    def _log(self, lay) -> None:
        rows = self.fetch("rb_admin_audit", {})
        if rows is None:
            return lay.addWidget(Label(en("Loading…"), 12, TEXT_DIM))

        def undo(i: int) -> None:
            r = rows[i]
            if r.get("undone"):
                return self.ctx.toast(en("Already undone"), "warn")
            if not r.get("can_undo"):
                return self.ctx.toast(en("This cannot be undone"), "warn")
            self.ctx.window.confirm(en("Undo “{what}” on {target}?", what=r["action"], target=r.get("target") or "-"),
                                    lambda: self.do("rb_admin_undo", {"entry": r["id"]}, en("Undone")), yes=en("Undo"))
        lay.addWidget(Table([(("↩ " if r.get("can_undo") else ("✓ " if r.get("undone") else "")) + r["action"],
                              str(r.get("target") or "")[:16], str(r["at"])[5:16].replace("T", " "),
                              TEXT_DIM if r.get("undone") else ("#FFC94D" if r.get("can_undo") else TEXT)) for r in rows],
                            self.W, undo))

    # -- forgotten passwords: is it really them?

    VERDICTS = {"real": ("Looks real: asked from the account's own PC", "#3DDC84"),
                "fake": ("Looks fake: asked from another user's PC", "#FF5C6C"),
                "unsure": ("Not sure: a PC we do not know", "#FFC94D"),
                "no_account": ("No account with this name", "#9AA4AD")}

    # -- Bots: fake accounts that live on their own

    BOT_FIELDS = [("hours", "Hours played", "40"), ("days", "Account age in days", "30"), ("coins", "Coins", "8000"),
                  ("keys", "Keys", "6"), ("streak", "Login streak (days)", "5"), ("badges", "Badges to own (0 to 60)", "12"),
                  ("active", "How often online, % (0 to 100)", "60"), ("from", "Online from (hour, 0 to 23)", "16"),
                  ("to", "Online until (hour, 0 to 23)", "23")]

    def _bot_cfg(self, v: dict, dlg) -> dict:
        cfg = {}
        limits = {"hours": (0, 20000), "days": (0, 3650), "coins": (0, 10000000), "keys": (0, 48), "streak": (0, 3650),
                  "badges": (0, 60), "active": (0, 100), "from": (0, 23), "to": (0, 23)}
        for key, (lo, hi) in limits.items():
            n = _int(v.get(key, ""), None)
            if n is None or not lo <= n <= hi:
                dlg.say(en("{what}: a number from {a} to {b}", what=en(dict((k, t) for k, t, _d in self.BOT_FIELDS)[key]),
                           a=lo, b=hi))
                return {}
            cfg[key] = n
        return cfg

    def _bots(self, lay) -> None:
        make = Button(en("Create a bot"), "primary", 34, icon="plus")
        make.clicked.connect(self._bot_new)
        lay.addWidget(make)
        rows = self.fetch("rb_admin_bots", {})
        if rows is None:
            return lay.addWidget(Label(en("Loading…"), 12, TEXT_DIM))
        if not isinstance(rows, list) or not rows:
            return lay.addWidget(Label(en("No bots yet."), 11, TEXT_FAINT))
        pick = getattr(self.ctx, "admin_bot", "") or ""
        lay.addWidget(heading(en("Bots") + f"  ·  {len(rows)}"))
        lay.addWidget(Table([(("● " if b.get("online") else "○ ") + b["username"],
                              f"{int(b.get('minutes') or 0) // 60} h",
                              coins_text(int(b.get("coins") or 0)), "#3DDC84" if b.get("online") else TEXT_DIM)
                             for b in rows], self.W,
                            lambda i: (setattr(self.ctx, "admin_bot", rows[i]["username"]), self.ctx.reload_page("admin"))))
        b = next((r for r in rows if r["username"] == pick), None)
        if b is None:
            return
        cfg = b.get("cfg") or {}
        paused = bool(cfg.get("paused"))
        lay.addWidget(heading(b["username"] + ("  ·  " + en("Paused") if paused else "")))
        lay.addWidget(Label(en("{h} h played · {c} coins · {k} keys · {s}-day streak · {n} badges · online {a}% from {f}:00 to {t}:00",
                               h=int(b.get("minutes") or 0) // 60, c=coins_text(int(b.get("coins") or 0)),
                               k=int(b.get("keys") or 0), s=int(b.get("streak") or 0), n=int(b.get("badges") or 0),
                               a=int(cfg.get("active", 60)), f=int(cfg.get("from", 16)), t=int(cfg.get("to", 23))),
                            10.5, TEXT_DIM, wrap_w=self.W))
        line = hbox(spacing=6)
        edit = Button(en("Change"), "primary", 30)
        edit.clicked.connect(lambda: self._bot_edit(b))
        stop = Button(en("Resume") if paused else en("Pause"), "ghost", 30)
        stop.clicked.connect(lambda: self.do("rb_admin_bot_set", {"name": b["username"], "cfg": {"paused": not paused}},
                                             en("Saved")))
        gone = Button(en("Delete"), "danger", 30)
        gone.clicked.connect(lambda: self.ctx.window.confirm(
            en("Delete the bot {name} for good?", name=b["username"]),
            lambda: self.do("rb_admin_bot_delete", {"name": b["username"]}, en("Deleted")), yes=en("Delete")))
        for w in (edit, stop, gone):
            line.addWidget(w, 1)
        lay.addLayout(line)
        line = hbox(spacing=6)
        pic = Button(en("Picture"), "ghost", 30)
        pic.clicked.connect(lambda: self._bot_picture(b["username"]))
        rnd = Button(en("Random stats"), "ghost", 30)
        rnd.clicked.connect(lambda: self.do("rb_admin_bot_set", {"name": b["username"], "cfg": self._bot_random()},
                                            en("Saved")))
        past = Button(en("Add history"), "ghost", 30)
        past.clicked.connect(lambda: self.do("rb_admin_bot_history", {"name": b["username"], "n": 60},
                                             en("60 past cases, bets and spins added")))
        for w in (pic, rnd, past):
            line.addWidget(w, 1)
        lay.addLayout(line)

    @staticmethod
    def _bot_random() -> dict:
        """Believable random numbers for a bot."""
        import random
        hours = int(random.triangular(5, 600, 60))
        start = random.choice([8, 12, 14, 16, 17, 18, 19, 20])
        return {"hours": hours, "days": max(1, int(hours / random.uniform(1.5, 5))), "coins": int(random.triangular(200, 80000, 6000)),
                "keys": random.randint(0, 5), "streak": random.choice([0, 1, 2, 3, 4, 5, 7, 9, 12, 15, 21, 30]),
                "badges": random.randint(3, 30), "active": random.randint(35, 90), "from": start,
                "to": min(23, start + random.randint(3, 7))}

    def _bot_picture(self, name: str) -> None:
        import base64
        from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
        from PyQt6.QtGui import QImage
        path = self.ctx.pick_file(en("Choose a picture"), "Pictures (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            return self.ctx.toast(en("This picture cannot be used"), "warn")
        side = min(img.width(), img.height())
        img = img.copy((img.width() - side) // 2, (img.height() - side) // 2, side, side).scaled(
            96, 96, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        buf = QByteArray()
        dev = QBuffer(buf)
        dev.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(dev, "JPG", 82)
        self.do("rb_admin_bot_avatar", {"name": name, "picture": base64.b64encode(bytes(buf)).decode()}, en("Picture saved"))

    def _bot_new(self) -> None:
        fields = [("name", en("Username (3 to 10 letters or numbers)"), ""), ("pw", en("Password (8 characters at least)"), "")]
        rand = self._bot_random()                      # random, believable numbers to start from
        fields += [(k, en(t), str(rand.get(k, d))) for k, t, d in self.BOT_FIELDS]

        def go(v: dict, dlg) -> None:
            import re
            name, pw = v["name"], v["pw"]
            if not re.fullmatch(r"[A-Za-z0-9]{3,10}", name):
                return dlg.say(en("3 to 10 letters or numbers"))
            if len(pw) < 8:
                return dlg.say(en("8 characters at least"))
            cfg = self._bot_cfg(v, dlg)
            if not cfg:
                return
            dlg.say(en("Creating…"))

            def ticket(ok: bool, tk) -> None:
                if not ok:
                    return dlg.say(en(str(tk)))

                def made(ok2: bool, d) -> None:
                    if not ok2:
                        return dlg.say(en(str(d)) if "taken" not in str(d).lower() else en("This username is taken"))

                    def set_done(ok3: bool, d3) -> None:
                        if not ok3:
                            return dlg.say(en(str(d3)))
                        dlg.close()
                        sfx.play("on")
                        self.ctx.toast(en("Bot {name} created", name=name))
                        self.ctx.admin_bot = name
                        self.ctx.admin_cache = {}
                        QTimer.singleShot(300, lambda: self.ctx.reload_page("admin"))
                    self.ctx.econ.call("rb_admin_bot_set", {"name": name, "cfg": cfg}, set_done)
                self.ctx.online.make_bot(name, pw, str(tk), made)
            self.ctx.econ.call("rb_admin_bot_ticket", {}, ticket)
        FormDialog(self.ctx, en("Create a bot"), fields, en("Create"), go)

    def _bot_edit(self, b: dict) -> None:
        cfg = dict(b.get("cfg") or {})
        now = {"hours": int(b.get("minutes") or 0) // 60, "coins": int(b.get("coins") or 0), "keys": int(b.get("keys") or 0),
               "streak": int(b.get("streak") or 0), "badges": int(b.get("badges") or 0), "days": 30}
        try:
            from datetime import datetime, timezone
            since = datetime.fromisoformat(str(b.get("since")).replace("Z", "+00:00"))
            now["days"] = max(0, (datetime.now(timezone.utc) - since).days)
        except (TypeError, ValueError):
            pass
        fields = [(k, en(t), now.get(k, cfg.get(k, d))) for k, t, d in self.BOT_FIELDS]

        def go(v: dict, dlg) -> None:
            new = self._bot_cfg(v, dlg)
            if new:
                dlg.close()
                self.do("rb_admin_bot_set", {"name": b["username"], "cfg": new}, en("Saved"))
        FormDialog(self.ctx, en("Change {name}", name=b["username"]), fields, en("Save"), go)

    # -- Swaps: add Rocket League swaps for everyone

    def _swaps(self, lay) -> None:
        from .extras import ONLINE_STATES, RL_CATS
        rows = self.fetch("rb_swaps_list", {})
        if isinstance(rows, list) and rows:
            lay.addWidget(heading(en("Swaps you added") + f"  ·  {len(rows)}"))
            names = dict(RL_CATS)
            lay.addWidget(Table([(r["new"], en(names.get(r["cat"], r["cat"])),
                                  en(ONLINE_STATES.get(r["state"], "Live")),
                                  {"live": "#3DDC84", "paused": "#FFC94D"}.get(r["state"], "#FF7A7A")) for r in rows], self.W,
                                lambda i: (setattr(self.ctx, "admin_swap", rows[i]["id"]), self.ctx.reload_page("admin"))))
            cur = next((r for r in rows if r["id"] == getattr(self.ctx, "admin_swap", "")), None)
            if cur is not None:
                lay.addWidget(Label(f"{cur['old']} → {cur['new']}  ·  {cur['file']}", 11, TEXT, bold=True, wrap_w=self.W))
                line = hbox(spacing=6)
                for st, text, kind in (("live", "Live", "primary"), ("paused", "Pause", "ghost"), ("locked", "Lock", "ghost"),
                                       ("delete", "Delete", "danger")):
                    b = Button(en(text), kind, 30)
                    b.setEnabled(st != cur["state"])
                    b.clicked.connect(lambda _c=False, st=st: self.do("rb_admin_swap_state", {"sid": cur["id"], "st": st}, en("Saved")))
                    line.addWidget(b, 1)
                lay.addLayout(line)
        lay.addWidget(heading(en("Add a swap for everyone")))
        cats = [c for c, _n in RL_CATS]
        ci = cats.index(getattr(self.ctx, "swap_cat", cats[0])) if getattr(self.ctx, "swap_cat", cats[0]) in cats else 0
        from PyQt6.QtWidgets import QGridLayout
        grid = QGridLayout()                                 # 3 per row: every category name fits
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(S(4))
        for i, (_c, n) in enumerate(RL_CATS):
            b = Button(en(n), "primary" if i == ci else "ghost", 28)
            b.clicked.connect(lambda _x=False, i=i: (setattr(self.ctx, "swap_cat", cats[i]), self.ctx.reload_page("admin")))
            grid.addWidget(b, i // 3, i % 3)
        lay.addLayout(grid)
        files = getattr(self.ctx, "swap_files", None) or {}
        self.ctx.swap_files = files
        import os
        for key, text, filt in (("img", "Picture (PNG or JPG, made 300×300)", "Images (*.png *.jpg *.jpeg)"),
                                ("swap", "Swap file (.upk)", "Rocket League files (*.upk)"),
                                ("orig", "Original game file (.upk, optional)", "Rocket League files (*.upk)")):
            chosen = files.get(key)
            b = Button((en(text) + ": " + os.path.basename(chosen)) if chosen else en(text), "ghost", 30, icon="folder")

            def choose(_c=False, key=key, text=text, filt=filt) -> None:
                path = self.ctx.pick_file(en(text), filt)     # 4.0: the window steps aside (it covered the dialog)
                if path:
                    self.ctx.swap_files[key] = path
                    self.ctx.reload_page("admin")
            b.clicked.connect(choose)
            lay.addWidget(b)
        add = Button(en("Add the swap"), "primary", 34, icon="plus")
        add.setEnabled(bool(files.get("swap")))
        add.clicked.connect(lambda: self._swap_form(cats[ci]))
        lay.addWidget(add)

    def _swap_form(self, cat: str) -> None:
        import hashlib
        import os
        import re
        files = dict(getattr(self.ctx, "swap_files", None) or {})
        swap = files.get("swap", "")
        fname = os.path.basename(swap)
        if not re.fullmatch(r"[A-Za-z0-9_.-]{3,80}", fname) or not fname.lower().endswith(".upk"):
            return self.ctx.toast(en("The swap file must be a .upk file with a simple name"), "warn")
        if files.get("orig") and os.path.basename(files["orig"]).lower() != fname.lower():
            return self.ctx.toast(en("The original file must have the same name as the swap file"), "warn")

        def go(v: dict, dlg) -> None:
            old, new = v["old"].strip(), v["new"].strip()
            if not old or not new:
                return dlg.say(en("Fill in both names"))
            sid = "o_" + (re.sub(r"[^a-z0-9]+", "_", (old + "_" + new).lower()).strip("_"))[:36]
            try:
                data = open(swap, "rb").read()
                orig = open(files["orig"], "rb").read() if files.get("orig") else b""
            except OSError:
                return dlg.say(en("This file cannot be read"))
            if not data.startswith(b"\xc1\x83\x2a\x9e"):
                return dlg.say(en("This is not a Rocket League file"))
            png = b""
            if files.get("img"):
                from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
                from PyQt6.QtGui import QImage
                img = QImage(files["img"])
                if img.isNull():
                    return dlg.say(en("This picture cannot be used"))
                img = img.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                img = img.copy((img.width() - 300) // 2, (img.height() - 300) // 2, 300, 300)
                ba = QByteArray()
                buf = QBuffer(ba)
                buf.open(QIODevice.OpenModeFlag.WriteOnly)
                img.save(buf, "PNG")
                png = bytes(ba)
            dlg.say(en("Uploading…"))
            jobs = [(f"swaps/{sid}/{fname}", data, "application/octet-stream")]
            if png:
                jobs.append((f"swaps/{sid}/preview.png", png, "image/png"))
            if orig:
                jobs.append((f"swaps/{sid}/original/{fname}", orig, "application/octet-stream"))

            def next_job(ok: bool = True, d=None) -> None:
                if not ok:
                    return dlg.say(en("Upload failed: {why}", why=en(str(d))))
                if jobs:
                    path, blob, kind = jobs.pop(0)
                    return self.ctx.online.upload(path, blob, kind, next_job)

                def saved(ok2: bool, d2) -> None:
                    if not ok2:
                        return dlg.say(en(str(d2)))
                    dlg.close()
                    sfx.play("on")
                    self.ctx.toast(en("Swap added for everyone"))
                    self.ctx.swap_files = {}
                    self.ctx.admin_cache = {}
                    self.ctx.swaps_at = -999
                    QTimer.singleShot(300, lambda: self.ctx.reload_page("admin"))
                self.ctx.econ.call("rb_admin_swap_save", {"sid": sid, "cat": cat, "old": old, "new": new, "file": fname,
                                                          "sha": hashlib.sha256(data).hexdigest(),
                                                          "orig_sha": hashlib.sha256(orig).hexdigest() if orig else "",
                                                          "img": bool(png), "orig": bool(orig)}, saved)
            next_job()
        FormDialog(self.ctx, en("Add a swap"), [("old", en("The item you equip in the game (e.g. Octane)"), ""),
                                               ("new", en("What it becomes (the title)"), "")], en("Upload"), go)

    # -- 4.0: every part of Rubenium, locked or unlocked live

    FEATURES = {"online": ("Online mode", "Everything online: trades, chat, coinflips, Mini Golf"),
                "trading": ("Trading", "New trades; open trades are cancelled"),
                "market": ("Market", "Buying, selling and listing"),
                "coinflip": ("Coinflip", "Open coinflips are cancelled, items go back"),
                "roulette": ("Roulette", ""),
                "casino": ("Other casino games", "Blackjack, Plinko, Bombs, Dice, Timing, Rocket, Hi-Lo, Tower"),
                "minigames": ("Mini games", "Beat Tap, Memory, Block Blast, Minesweeper and the others"),
                "golf": ("Mini Golf", "Running matches are cancelled and bets given back"),
                "wheel": ("Free spin wheel", ""), "scratch": ("Scratch cards", ""), "advent": ("Advent calendar", ""),
                "notifications": ("Notifications", "Gift and system messages"),
                "cases": ("Cases", "Buying and opening"), "shop": ("Shop", "Buying in the shop and Bon Plan"),
                "chat": ("Chat", "Messages and reactions"), "giveaways": ("Giveaways", "Joining"),
                "quests": ("Quests", "Claiming rewards"), "coupons": ("XP coupons", "Using coupons"),
                "gifts": ("Gifts", "Sending items to friends")}

    def _locks(self, lay) -> None:
        d = self.fetch("rb_admin_features", {})
        if d is None:
            return lay.addWidget(Label(en("Loading…"), 12, TEXT_DIM))
        if not d:
            return lay.addWidget(Label(en("Run the 4.0 server update first."), 11, TEXT_DIM, wrap_w=self.W))
        down = bool(d.get("lockdown"))
        feats = d.get("features") or []
        locked = {f["name"] for f in feats if f.get("locked")}
        order = list(self.FEATURES)
        feats.sort(key=lambda f: order.index(f["name"]) if f["name"] in order else len(order))
        for f in feats:
            name, note = self.FEATURES.get(f["name"], (f["name"], ""))
            if f.get("locked"):
                state, why = "locked", en("Locked by {who} · {at}", who=f.get("by") or "?",
                                          at=str(f.get("at") or "")[5:16].replace("T", " "))
                if f.get("note"):
                    why += " · " + f["note"]
            elif down:
                state, why = "held", en("Stopped by the lockdown")
            elif f.get("parent") in locked:
                state, why = "held", en("Stopped because {name} is locked",
                                        name=en(self.FEATURES.get(f["parent"], (f["parent"],))[0]))
            else:
                state, why = "on", en(note) if note else en("Working")
            row = FeatureRow(en(name), why, state, False)
            row.clicked.connect(lambda _c=False, f=f, name=name: self._feature(f["name"], en(name), not f.get("locked")))
            lay.addWidget(row)
        log = d.get("log") or []
        if log:
            lay.addWidget(heading(en("Last changes")))
            rows = []
            for x in log:
                det = x.get("detail") or {}
                what = en("LOCKDOWN") if x.get("action") == "lockdown" else \
                    en(self.FEATURES.get(x.get("target") or "", (x.get("target") or "?",))[0])
                lock = bool(det.get("locked"))
                stopped = int((det.get("result") or {}).get("stopped") or 0)
                rows.append((what, (en("locked") if lock else en("unlocked")) + (f" · {stopped}" if stopped else ""),
                             f"{x.get('who') or '?'} · {str(x.get('at') or '')[5:16].replace('T', ' ')}",
                             "#FF7A7A" if lock else "#5BE08A"))
            lay.addWidget(Table(rows, self.W))

    def _feature(self, key: str, name: str, lock: bool) -> None:
        def go(v: dict, dlg) -> None:
            dlg.close()
            self.do("rb_admin_feature", {"name": key, "lock": lock, "note": (v.get("n") or "").strip()},
                    en("{name} locked", name=name) if lock else en("{name} unlocked", name=name))
        if lock:
            FormDialog(self.ctx, en("Lock {name}", name=name), [("n", en("Reason (players don't see it)"), "")],
                       en("Lock"), go, en("Running games in it are cancelled and given back."))
        else:
            self.ctx.window.confirm(en("Unlock {name} for everyone?", name=name),
                                    lambda: go({}, type("D", (), {"close": lambda _s: None})()), yes=en("Unlock"))

    # -- 4.0: levels and XP

    def _flip_row(self, lay, r: dict) -> None:
        bot = r.get("a") if r.get("a_bot") else r.get("b")
        val = int(r.get("a_value") or 0) if r.get("a_bot") else int(r.get("b_value") or 0)
        tag = en("RUBENIUM OFFER") if r.get("admin_offer") else en("BOT")
        exp = r.get("expires")
        line = hbox(spacing=6)
        text = f"{tag} · {bot} · {coins_text(val)}"
        if r.get("b") and not r.get("b_bot") and r.get("a_bot"):
            text += " · " + en("vs {name}", name=r["b"])
        if exp is not None:
            text += " · " + en("{m} min left", m=max(0, int(exp) // 60))
        line.addWidget(Label(text, 11, GOLD_TEXT if r.get("admin_offer") else TEXT, bold=True), 1)
        if r.get("state") in ("setup", "open", "joined"):
            stop = Button(en("Cancel"), "ghost", 26)
            stop.clicked.connect(lambda _c=False, fid=r["id"]: self.ctx.window.confirm(
                en("Cancel this coinflip? Any items in it go back to their owner."),
                lambda: self.do("rb_admin_flip_cancel", {"fid": fid}, en("Cancelled")), yes=en("Cancel it")))
            line.addWidget(stop)
        lay.addLayout(line)
        items = (r.get("a_items") if r.get("a_bot") else r.get("b_items")) or []
        if items:
            lay.addWidget(ItemGrid(self.ctx, [{"item": i["item"], "text": coins_text(int(i.get("worth") or 0))}
                                              for i in items], self.W, 6, 60, moving=False))

    def _help(self, lay) -> None:
        rows = self.fetch("rb_admin_resets", {})
        if rows is None:
            return lay.addWidget(Label(en("Loading…"), 12, TEXT_DIM))
        if not rows:
            return lay.addWidget(Label(en("No requests."), 12, TEXT_DIM))
        for r in rows[:30]:
            text, col = self.VERDICTS.get(r.get("verdict"), ("?", TEXT_DIM))
            lay.addWidget(heading(f"{r.get('name', '?')}  ·  {str(r.get('at', ''))[5:16].replace('T', ' ')}  ·  {en(r.get('state', ''))}"))
            lay.addWidget(Label(en(text), 11.5, col, bold=True, wrap_w=self.W))
            facts = [en("Message: {m}", m=r.get("msg") or "-")]
            if r.get("exists"):
                facts.append(en("Account: {h} h played, last seen {t}", h=f"{int(r.get('minutes') or 0) / 60:.1f}",
                                t=str(r.get("seen") or "-")[:16].replace("T", " ")))
            if r.get("pc_owner"):
                facts.append(en("This PC belongs to: {name}", name=r["pc_owner"]))
            facts.append(en("Requests from this PC (7 days): {a} · for this name: {b}", a=r.get("pc_asks", 0), b=r.get("name_asks", 0)))
            for f in facts:
                lay.addWidget(Label(f, 10.5, TEXT_DIM, wrap_w=self.W))
            if r.get("state") == "open":
                line = hbox(spacing=6)
                yes = Button(en("Give new password"), "primary", 28)
                no = Button(en("Refuse"), "ghost", 28)
                rid = r["id"]
                import secrets
                temp = "Rb-" + secrets.token_hex(4)
                yes.clicked.connect(lambda _c=False, rid=rid, temp=temp: FormDialog(
                    self.ctx, en("New password"), [("p", en("Temporary password (8 or more)"), temp)], en("Give"),
                    lambda v, dlg: (dlg.close(), self.do("rb_admin_reset_do", {"rid": rid, "new_password": v["p"]}, en("Done")))))
                no.clicked.connect(lambda _c=False, rid=rid: self.do("rb_admin_reset_do", {"rid": rid, "new_password": None}, en("Refused")))
                line.addWidget(yes, 1)
                line.addWidget(no, 1)
                lay.addLayout(line)


# --------------------------------------------------------------------------- #
# 4.0: the LOCKDOWN button and a row of the live locks
# --------------------------------------------------------------------------- #
class LockdownBar(QAbstractButton):
    """Off: a red bar with hazard stripes. On: it pulses, and says how to lift it."""

    def __init__(self, on: bool) -> None:
        super().__init__()
        self.on = on
        self.setFixedHeight(S(44))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self.update)

    def showEvent(self, _e) -> None:
        if self.on:
            self._timer.start()

    def hideEvent(self, _e) -> None:
        self._timer.stop()

    def enterEvent(self, _e) -> None:
        self._hover = 1.0
        self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = 0.0
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(S(1), S(1), -S(1), -S(1))
        path = QPainterPath()
        path.addRoundedRect(r, S(11), S(11))
        p.setClipPath(path)
        if self.on:
            pulse = 0.5 + 0.5 * math.sin(time.monotonic() * 4.0)
            p.fillRect(r, QColor.fromHsvF(0.0, 0.85, 0.55 + 0.25 * pulse))
        else:
            p.fillRect(r, QColor("#3A0D12" if not self._hover else "#521219"))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 60, 60, 46 if not self._hover else 70))
            step = S(18)
            x = -r.height()
            while x < r.width() + r.height():
                p.drawPolygon(QPolygonF([QPointF(x, r.bottom()), QPointF(x + r.height(), r.top()),
                                         QPointF(x + r.height() + step / 2, r.top()), QPointF(x + step / 2, r.bottom())]))
                x += step
        p.setClipping(False)
        p.setPen(QPen(QColor("#FF5C5C"), S(1.6)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, S(11), S(11))
        p.setPen(QColor("#FFFFFF"))
        p.setFont(font(14, QFont.Weight.Black))
        title = en("LOCKDOWN ACTIVE") if self.on else en("LOCKDOWN")
        p.drawText(r.adjusted(S(14), 0, -S(14), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), title)
        p.setFont(font(10, QFont.Weight.DemiBold))
        p.setPen(QColor("#FFD6D6"))
        p.drawText(r.adjusted(S(14), 0, -S(14), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                   en("Click to lift it") if self.on else en("Stop everything now"))


class FeatureRow(QAbstractButton):
    """One part of Rubenium: a status light, its name, why, and LOCK / UNLOCK on the right."""
    STATES = {"on": ("#3DDC84", "ON"), "locked": ("#FF5C5C", "LOCKED"), "held": ("#FFB020", "STOPPED")}

    def __init__(self, name: str, why: str, state: str, child: bool) -> None:
        super().__init__()
        self.name, self.why, self.state, self.child = name, why, state, child
        self.setFixedHeight(S(46))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False

    def enterEvent(self, _e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = False
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        col, word = self.STATES.get(self.state, self.STATES["on"])
        r = QRectF(self.rect()).adjusted(S(16) if self.child else S(1), S(2), -S(1), -S(2))
        p.setPen(QPen(alpha(col, 0.55 if self.state != "on" else 0.22), S(1.2)))
        p.setBrush(QColor("#151A1D" if self._hover else "#101416"))
        p.drawRoundedRect(r, S(9), S(9))
        dot = QPointF(r.left() + S(14), r.center().y())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha(col, 0.25))
        p.drawEllipse(dot, S(7), S(7))
        p.setBrush(QColor(col))
        p.drawEllipse(dot, S(4), S(4))
        bw = S(74)
        btn = QRectF(r.right() - bw - S(6), r.center().y() - S(13), bw, S(26))
        p.setBrush(QColor("#2A1013") if self.state != "locked" else QColor("#0F2A1A"))
        p.setPen(QPen(QColor("#FF5C5C") if self.state != "locked" else QColor("#3DDC84"), S(1.2)))
        p.drawRoundedRect(btn, S(8), S(8))
        p.setFont(font(9.5, QFont.Weight.ExtraBold))
        p.setPen(QColor("#FFB3B3") if self.state != "locked" else QColor("#A8F5C8"))
        p.drawText(btn, int(Qt.AlignmentFlag.AlignCenter), en("UNLOCK") if self.state == "locked" else en("LOCK"))
        tx = dot.x() + S(14)
        tw = btn.left() - tx - S(8)
        p.setFont(font(11.5, QFont.Weight.Bold))
        p.setPen(QColor(TEXT))
        fm = p.fontMetrics()
        name = fm.elidedText(self.name, Qt.TextElideMode.ElideRight, int(tw * 0.62))
        p.drawText(QRectF(tx, r.top() + S(5), tw, S(18)), int(Qt.AlignmentFlag.AlignVCenter), name)
        sw = fm.horizontalAdvance(name) + S(8)
        p.setFont(font(8.5, QFont.Weight.ExtraBold))
        p.setPen(QColor(col))
        p.drawText(QRectF(tx + sw, r.top() + S(5), tw - sw, S(18)), int(Qt.AlignmentFlag.AlignVCenter), en(word))
        p.setFont(font(9.5))
        p.setPen(QColor(TEXT_DIM))
        p.drawText(QRectF(tx, r.top() + S(23), tw, S(16)), int(Qt.AlignmentFlag.AlignVCenter),
                   p.fontMetrics().elidedText(self.why, Qt.TextElideMode.ElideRight, int(tw)))


# --------------------------------------------------------------------------- #
# Giveaways (the golden tab)
# --------------------------------------------------------------------------- #
class GiveawayCard(QWidget):
    def __init__(self, ctx, g: dict, width: int) -> None:
        super().__init__()
        self.ctx, self.g = ctx, g
        self.setFixedSize(width, S(150))
        self._until = time.monotonic() + int(g.get("left") or 0)
        rnd = random.Random(str(g.get("id")))
        self._bits = [(rnd.random(), rnd.random(), rnd.uniform(0.6, 1.6)) for _ in range(26)]
        self._t = QTimer(self)
        self._t.setInterval(40)
        self._t.timeout.connect(self.update)
        self._ask = QTimer(self)                         # time is up: ask for the winner every second until drawn
        self._ask.setInterval(1000)
        self._ask.timeout.connect(self._check_end)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def _check_end(self) -> None:
        if self.g.get("state") == "live" and time.monotonic() >= self._until - 0.5:
            self.ctx.econ.poll_live()

    def showEvent(self, _e) -> None:
        self._ask.start()
        self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()
        self._ask.stop()

    def paintEvent(self, _e) -> None:
        from .collection import CASE_NAMES, paint_case
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        g = self.g
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        bg = QLinearGradient(r.topLeft(), r.bottomRight())
        bg.setColorAt(0, QColor("#2B2210"))
        bg.setColorAt(1, QColor("#120E06"))
        p.setPen(QPen(QColor(GOLD_TEXT), S(1.6)))
        p.setBrush(bg)
        p.drawRoundedRect(r, S(14), S(14))
        p.save()
        p.setClipRect(r)
        p.setPen(Qt.PenStyle.NoPen)
        for x, ph, sp in self._bits:
            t = (now / (3 * sp) + ph) % 1.0
            c = QColor(GOLD_TEXT)
            c.setAlphaF(0.5 * math.sin(t * math.pi))
            p.setBrush(c)
            p.drawEllipse(QPointF(r.left() + x * r.width(), r.top() + t * r.height()), S(1.8), S(1.8))
        p.restore()
        pic = QRectF(r.left() + S(16), r.top() + S(28), S(70), S(70))
        kind = g.get("kind")
        if kind == "coins":
            paint_coin(p, pic.center(), S(26))
            prize = tr("{n} coins", n=coins_text(int(g.get("amount") or 0)))
        elif kind == "keys":
            p.save()
            p.translate(pic.center())
            p.scale(S(50) / 20, S(50) / 20)
            from .widgets import draw_icon
            draw_icon(p, "key", QColor(GOLD_TEXT))
            p.restore()
            prize = tr("{n} keys", n=g.get("amount"))
        elif kind == "case":
            paint_case(p, pic, g.get("what", ""))
            prize = tr(CASE_NAMES.get(g.get("what"), "Case")) + (f" ×{g['amount']}" if int(g.get("amount") or 1) > 1 else "")
        else:
            paint_cosmetic(p, g.get("what", ""), pic, now)
            prize = item_name(g.get("what", "")) + (f" ×{g['amount']}" if int(g.get("amount") or 1) > 1 else "")
        x = r.left() + S(100)
        p.setPen(QColor(GOLD_TEXT))
        p.setFont(font(9.5, QFont.Weight.ExtraBold, 1.2))
        p.drawText(QRectF(x, r.top() + S(14), r.width() - S(110), S(14)), int(Qt.AlignmentFlag.AlignVCenter), tr("LIVE GIVEAWAY")
                   if g.get("state") == "live" else tr("GIVEAWAY OVER"))
        p.setPen(QColor(TEXT))
        p.setFont(font(15, QFont.Weight.Bold))
        p.drawText(QRectF(x, r.top() + S(30), r.width() - S(110), S(22)), int(Qt.AlignmentFlag.AlignVCenter), g.get("title", ""))
        p.setFont(font(12, QFont.Weight.DemiBold))
        p.drawText(QRectF(x, r.top() + S(54), r.width() - S(110), S(18)), int(Qt.AlignmentFlag.AlignVCenter),
                   p.fontMetrics().elidedText(prize, Qt.TextElideMode.ElideRight, int(r.width() - S(110))))
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        n = int(g.get("winners") or 1)
        sub = tr("{w} winner(s) · {e} joined", w=n, e=g.get("entries", 0))
        if int(g.get("min_minutes") or 0):
            sub += " · " + tr("{h} h needed", h=int(g["min_minutes"]) // 60)
        p.drawText(QRectF(x, r.top() + S(74), r.width() - S(110), S(16)), int(Qt.AlignmentFlag.AlignVCenter), sub)
        if g.get("state") == "live":
            left = max(0, int(self._until - now))
            p.setPen(QColor(GOLD_TEXT))
            p.setFont(font(20, QFont.Weight.ExtraBold))
            p.drawText(QRectF(x, r.top() + S(94), r.width() - S(110), S(30)), int(Qt.AlignmentFlag.AlignVCenter), clock_text(left))
        else:
            p.setPen(QColor(TEXT))
            p.setFont(font(11.5, QFont.Weight.Bold))
            p.drawText(QRectF(x, r.top() + S(96), r.width() - S(110), S(40)), int(Qt.TextFlag.TextWordWrap),
                       tr("Winners: {names}", names=", ".join(g.get("result") or []) or "—"))


class GiveawayPage(Page):
    key = "giveaway"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        lay = vbox(self, 8)
        lay.addWidget(Label(tr("Giveaway"), 16, GOLD_TEXT, bold=True))
        gs = ctx.econ.live.get("giveaways") or []
        if not gs:
            lay.addWidget(Label(tr("No giveaway right now."), 12, TEXT_DIM))
        for g in gs:
            lay.addWidget(GiveawayCard(ctx, g, self.W))
            if g.get("state") != "live":
                continue
            if g.get("joined"):
                b = Button(tr("You are in! Good luck"), "ghost", 36)
                b.setEnabled(False)
            else:
                b = Button(tr("Join the giveaway"), "primary", 38)
                b.clicked.connect(lambda _=False, x=g: self._join(x))
            lay.addWidget(b)
        lay.addWidget(Label(tr("Free to join. Winners are drawn at random by the server when the time is up."), 10.5,
                            TEXT_DIM, wrap_w=self.W))

    def _join(self, g: dict) -> None:
        def done(ok: bool, data) -> None:
            if not ok:
                sfx.play("off")
                return self.ctx.toast(tr(str(data)), "warn")
            sfx.play("on")
            self.ctx.toast(tr("You joined: {title}", title=g.get("title", "")))
            g["joined"] = True
            self.ctx.econ.poll_live()
            QTimer.singleShot(400, self.ctx.reload_page)
        self.ctx.econ.call("rb_giveaway_join", {"giveaway": g["id"]}, done)
