"""The admin panel (only the account "Ruben" sees it, and the server checks it for every action) and the
golden Giveaway tab everyone sees while a giveaway is live."""
import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QLineEdit, QWidget

from .bazaar import ItemGrid, KINDS
from .core import DANGER, S, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, sfx, tr, ui
from .cosmetics import item_name, paint_cosmetic
from .pages import Page
from .shop import GOLD_TEXT, clock_text
from .wallet import coins_text, paint_coin
from .widgets import present, close_embedded, Button, IconButton, Label, Segmented, hbox, heading, vbox


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
        cancel = Button(tr("Cancel"), "ghost", 32)
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


class AdminPage(Page):
    key = "admin"
    SECTIONS = ["Overview", "Users", "Items", "Cases", "Live", "Settings", "Log", "Help"]
    ICONS = ["perf", "users", "gem", "gift", "timer", "cog", "refresh", "key"]

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        from .games import GamePicker
        self.lay = lay = vbox(self, 6)
        top = hbox(spacing=8)
        top.addWidget(Label(tr("Admin panel"), 16, bold=True), 1)
        again = IconButton("refresh", 30, tip=tr("Refresh"))
        again.clicked.connect(self._reload)
        top.addWidget(again)
        lay.addLayout(top)
        if not ctx.econ.admin:
            return lay.addWidget(Label(tr("Admin only"), 12, TEXT_DIM))
        tab = int(getattr(ctx, "admin_tab", 0) or 0)
        from .hub import NavTiles
        pick = NavTiles([(tr(s), i) for s, i in zip(self.SECTIONS, self.ICONS)], tab)
        pick.changed.connect(self._section)
        lay.addWidget(pick)
        self._lock_row(lay)
        [self._overview, self._players, self._items, self._cases, self._live, self._settings, self._log, self._help][tab](lay)

    # -- helpers
    def _reload(self) -> None:
        self.ctx.admin_cache = {}
        self.ctx.reload_page()

    def _section(self, i: int) -> None:
        self.ctx.admin_tab = i
        self.ctx.admin_player = None
        self.ctx.reload_page()

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
                    from .econ import server_missing
                    if server_missing(data):                 # the server update was not run yet: show it once, quietly
                        cache[key] = (time.monotonic() + 3600, {} if fn != "rb_admin_audit" and fn != "rb_admin_resets" else [])
                        self.ctx.econ.server_old = True
                        return
                    return self.ctx.toast(tr(str(data)), "warn")
                old = cache.get(key)
                cache[key] = (time.monotonic(), data)
                if (old is None or old[1] != data) and self.ctx.window.current == "admin":
                    self.ctx.reload_page()
            if got is None:
                cache[key] = (time.monotonic(), None)
            self.ctx.online.ask(fn, args, back)
        return got[1] if got else None

    def do(self, fn: str, args: dict, ok_text: str = "") -> None:
        def back(ok: bool, data) -> None:
            if not ok:
                sfx.play("off")
                return self.ctx.toast(tr(str(data)), "warn")
            sfx.play("on")
            if ok_text:
                self.ctx.toast(ok_text)
            self.ctx.admin_cache = {}
            self.ctx.econ.refresh()
            self.ctx.econ.poll_live()
            QTimer.singleShot(300, self.ctx.reload_page)
        self.ctx.econ.call(fn, args, back)

    def _lock_row(self, lay) -> None:
        locked = bool(self.ctx.econ.live.get("app_locked"))
        b = Button(tr("Unlock the app for everyone") if locked else tr("Lock the app for everyone"),
                   "primary" if locked else "ghost", 32, icon="lock")

        def flip() -> None:
            text = tr("Unlock games, cases, trades and the market for everyone?") if locked else \
                tr("Lock games, cases, trades and the market for everyone (not you)? Time still counts.")
            self.ctx.window.confirm(text, lambda: self.do("rb_admin_lock", {"lock": not locked},
                                                          tr("App unlocked") if locked else tr("App locked")),
                                    yes=tr("Unlock") if locked else tr("Lock"))
        b.clicked.connect(flip)
        lay.addWidget(b)

    # -- sections
    def _overview(self, lay) -> None:
        st = self.fetch("rb_admin_stats", {})
        if st is None:
            return lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
        lay.addWidget(Numbers([(st["players"], tr("Users")), (st["online"], tr("Online now")), (st["today"], tr("Today")),
                               (coins_text(st["coins"]), tr("Coins in total")), (st["keys"], tr("Keys in total")),
                               (st["items"], tr("Items")), (st["listings"], tr("On the market")),
                               (st["trades"], tr("Trades done")), ("", "")], self.W))
        lay.addWidget(heading(tr("Games: bets and payouts")))
        rows = []
        for g in st.get("games") or []:
            bet, paid = int(g["bet"]), int(g["paid"])
            keep = f"{100 - 100 * paid / bet:.1f}%" if bet else "—"
            rows.append((g["game"], tr("{n} rounds", n=g["rounds"]), tr("house {k}", k=keep),
                         "#5BE08A" if paid <= bet else "#FF7A7A"))
        lay.addWidget(Table(rows, self.W))
        lay.addWidget(heading(tr("Coins in and out (7 days)")))
        lay.addWidget(Table([(x["reason"], tr("{n} times", n=x["n"]), ("+" if int(x["coins"]) >= 0 else "") + coins_text(int(x["coins"])),
                              "#5BE08A" if int(x["coins"]) >= 0 else "#FF7A7A") for x in st.get("ledger") or []], self.W))

    def _players(self, lay) -> None:
        name = getattr(self.ctx, "admin_player", None)
        if name:
            return self._player(lay, name)
        sort = int(getattr(self.ctx, "admin_sort", 0) or 0)
        seg = Segmented([tr("Last seen"), tr("Coins"), tr("Hours")], sort)
        seg.changed.connect(lambda i: (setattr(self.ctx, "admin_sort", i), self.ctx.reload_page()))
        lay.addWidget(seg)
        find = Button(tr("Find a user"), "ghost", 28)
        find.clicked.connect(lambda: FormDialog(self.ctx, tr("Find a user"), [("n", tr("Username"), "")], tr("Open"),
                                                lambda v, d: (d.close(), self._open(v["n"]))))
        lay.addWidget(find)
        rows = self.fetch("rb_admin_players", {"search": "", "sort": ["", "coins", "hours"][sort], "page": 0})
        if rows is None:
            return lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
        table = [(("● " if r["online"] else "") + r["username"] + (" · " + tr("blocked") if r["banned"] else ""),
                  f"{int(r['minutes']) / 60:.1f} h", coins_text(int(r["coins"])), "#5BE08A" if r["online"] else TEXT)
                 for r in rows]
        lay.addWidget(Table(table, self.W, lambda i: self._open(rows[i]["username"])))

    def _open(self, name: str) -> None:
        self.ctx.admin_player = name
        self.ctx.admin_tab = 1
        self.ctx.reload_page()

    def _player(self, lay, name: str) -> None:
        top = hbox(spacing=8)
        back = IconButton("back", 30, tip=tr("Back"))
        back.clicked.connect(lambda: (setattr(self.ctx, "admin_player", None), self.ctx.reload_page()))
        top.addWidget(back)
        top.addWidget(Label(name, 15, bold=True), 1)
        lay.addLayout(top)
        d = self.fetch("rb_admin_player", {"name": name})
        if d is None:
            return lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
        st = d.get("stats") or {}
        lay.addWidget(Numbers([(coins_text(int(d["coins"])), tr("Coins"), GOLD_TEXT), (d["keys"], tr("Keys")),
                               (f"{int(d['minutes']) / 60:.1f} h", tr("Played")),
                               (coins_text(int(st.get("bet") or 0)), tr("Bet")), (coins_text(int(st.get("won") or 0)), tr("Won")),
                               (st.get("cases", 0), tr("Cases")), (st.get("trades", 0), tr("Trades")),
                               (tr("Online") if d.get("online") else tr("Offline"), tr("Status")),
                               (tr("Blocked") if d.get("banned") else tr("OK"), tr("Account"))], self.W))
        from .hub import AmountWindow, NavTiles
        acts = [(tr("Coins"), "gem"), (tr("Keys"), "key"), (tr("Give item"), "gift"), (tr("Give case"), "folder"),
                (tr("Unblock") if d.get("banned") else tr("Block"), "lock"), (tr("Picture"), "trash"),
                (tr("Undo last"), "refresh"), (tr("Refresh"), "refresh")]
        grid = NavTiles(acts, -1, select=False)

        def act(i: int) -> None:
            ctx = self.ctx
            if i == 0:
                ctx._amount = AmountWindow(ctx, tr("Coins for {name}", name=name), [100, 1000, 10000, 100000, -100, -1000, -10000, -100000],
                                           lambda n: self.do("rb_admin_grant", {"name": name, "add_coins": n, "add_keys": 0},
                                                             tr("Done: {n} coins", n=("+" if n > 0 else "") + coins_text(n))))
            elif i == 1:
                ctx._amount = AmountWindow(ctx, tr("Keys for {name}", name=name), [1, 5, 10, 50, -1, -5, -10, -50],
                                           lambda n: self.do("rb_admin_grant", {"name": name, "add_coins": 0, "add_keys": n},
                                                             tr("Done: {n} keys", n=f"{n:+d}")))
            elif i == 2:
                self._give_dialog(name)
            elif i == 3:
                self._case_dialog(name)
            elif i == 4:
                ctx.window.confirm(
                    tr("Unblock {name}?", name=name) if d.get("banned") else tr("Block {name}? They cannot use anything online.", name=name),
                    lambda: self.do("rb_admin_ban", {"name": name, "ban": not d.get("banned")}), yes=tr("Yes"))
            elif i == 5:
                ctx.window.confirm(tr("Remove {name}'s picture?", name=name),
                                   lambda: self.do("rb_admin_avatar_clear", {"name": name}, tr("Done")), yes=tr("Remove"))
            elif i == 6:
                self._undo_last(name)
            else:
                self._reload()
        grid.changed.connect(act)
        lay.addWidget(grid)
        self._danger(lay, name, d)
        stock = d.get("stock") or {}
        if stock:
            from .collection import CASE_NAMES
            lay.addWidget(Label(tr("Gifted cases waiting: ") + ", ".join(f"{tr(CASE_NAMES.get(k, k))} ×{n}" for k, n in stock.items()),
                                10.5, TEXT_DIM, wrap_w=self.W))
        items = d.get("items") or []
        lay.addWidget(heading(tr("Items ({n}) · click one to take it back", n=len(items))))
        if items:
            grid = ItemGrid(self.ctx, [{"item": i["item"], "text": "🔒" if i.get("locked") else ""} for i in items[:80]], self.W, 6, 60)

            def take(i: int) -> None:
                it = items[i]
                self.ctx.window.confirm(tr("Take {what} from {name}? (Take all removes every copy.)", what=item_name(it["item"]), name=name),
                                        lambda: self.do("rb_admin_take", {"item_id": it["id"]}, tr("Taken")), yes=tr("Take one"),
                                        no=tr("Take all"),
                                        on_no=lambda: self.do("rb_admin_revoke", {"name": name, "what": it["item"]}, tr("Taken")))
            grid.picked.connect(take)
            lay.addWidget(grid)
        deals = self.fetch("rb_admin_deals", {"name": name})
        lay.addWidget(heading(tr("Trades and market sales · click one to undo it")))
        if deals is None:
            lay.addWidget(Label(tr("Loading…"), 11, TEXT_DIM))
        else:
            rows = []
            for t in deals.get("trades") or []:
                gave = len(t.get("a_items") or []), len(t.get("b_items") or [])
                rows.append(("trade", t, (tr("Trade") + f" {t['a']} ⇄ {t['b']}",
                                         f"{gave[0]}+{coins_text(int(t['a_coins']))} / {gave[1]}+{coins_text(int(t['b_coins']))}",
                                         tr("undone") if t.get("undone") else str(t.get("at", ""))[5:16].replace("T", " "),
                                         TEXT_DIM if t.get("undone") else TEXT)))
            for l in deals.get("sales") or []:
                rows.append(("sale", l, (tr("Sale") + f" {l['seller']} → {l.get('buyer') or '?'}", item_name(l["what"])[:14],
                                        tr("undone") if l.get("undone") else coins_text(int(l["price"])),
                                        TEXT_DIM if l.get("undone") else GOLD_TEXT)))

            def undo_deal(i: int) -> None:
                kind, d, _row = rows[i]
                if d.get("undone"):
                    return self.ctx.toast(tr("Already undone"), "warn")
                fn, arg = ("rb_admin_undo_trade", {"trade": d["id"]}) if kind == "trade" else ("rb_admin_undo_sale", {"listing": d["id"]})
                self.ctx.window.confirm(tr("Undo this? Items go back to who had them and the coins are returned."),
                                        lambda: self.do(fn, arg, tr("Undone")), yes=tr("Undo"))
            if rows:
                lay.addWidget(Table([r[2] for r in rows], self.W, undo_deal))
            else:
                lay.addWidget(Label(tr("None"), 11, TEXT_DIM))
        lay.addWidget(heading(tr("Games")))
        lay.addWidget(Table([(g["game"], tr("{n} rounds", n=g["rounds"]), f"{coins_text(int(g['bet']))} → {coins_text(int(g['paid']))}")
                             for g in d.get("games") or []], self.W))
        lay.addWidget(heading(tr("Last rounds")))
        lay.addWidget(Table([(r["game"], item_name(r["item"]) if r.get("item") else coins_text(int(r["bet"])),
                              "+" + coins_text(int(r["paid"])), "#5BE08A" if int(r["paid"]) > int(r["bet"]) else TEXT_DIM)
                             for r in (d.get("rounds") or [])[:40]], self.W))
        lay.addWidget(heading(tr("Coin history")))
        lay.addWidget(Table([(l["reason"], str(l.get("ref") or "")[:18], ("+" if int(l["coins"]) >= 0 else "") + coins_text(int(l["coins"]))
                              + (f"  {int(l['keys']):+d}🔑" if int(l.get("keys") or 0) else ""),
                              "#5BE08A" if int(l["coins"]) >= 0 else "#FF7A7A") for l in (d.get("ledger") or [])[:60]], self.W))

    RESETS = [("inventory", "Reset inventory",
               "Deletes EVERY item {name} owns: all badges, balls, lines, fonts and themes. Items on the market or in a "
               "trade are taken back first. Coins, keys and cases stay."),
              ("money", "Reset coins and keys", "Sets {name}'s coins and keys to 0. Items and cases stay."),
              ("cases", "Reset gifted cases", "Deletes every gifted case {name} has not opened yet. Nothing else changes."),
              ("all", "FULL ACCOUNT RESET",
               "{name} starts again like a new account: every item deleted, coins and keys back to the start (500 coins, "
               "3 keys), gifted cases deleted, login streak back to 0. Time played, friends and name stay.")]

    def _danger(self, lay, name: str, d: dict) -> None:
        """Big red reset buttons. Each says exactly what it deletes, asks you to type the name, and can be undone
        from the Log."""
        lay.addWidget(heading(tr("Danger zone")))
        lay.addWidget(Label(tr("Every reset is saved in the Log: click it there to undo it."), 10.5, TEXT_DIM, wrap_w=self.W))
        for what, title, text in self.RESETS:
            b = Button(tr(title), "danger", 40 if what == "all" else 34, icon="trash")
            b.clicked.connect(lambda _c=False, what=what, title=title, text=text: self._reset(name, what, title, text))
            lay.addWidget(b)

    def _reset(self, name: str, what: str, title: str, text: str) -> None:
        def go(v, dlg) -> None:
            if v["n"].strip().lower() != name.lower():
                return dlg.say(tr("Type {name} exactly to confirm", name=name))
            dlg.close()
            self.do("rb_admin_reset", {"name": name, "what": what}, tr("Done. You can undo it in the Log."))
        FormDialog(self.ctx, tr(title) + f" · {name}", [("n", tr("Type the username to confirm: {name}", name=name), "")],
                   tr("Reset"), go, note=tr(text, name=name))

    def _case_dialog(self, name: str) -> None:
        from .collection import CASE_NAMES
        cases = [c["id"] for c in self.ctx.econ.cases] or list(CASE_NAMES)
        FormDialog(self.ctx, tr("Give a case to {name}", name=name),
                   [("w", tr("Which case: ") + ", ".join(cases), cases[0] if cases else ""),
                    ("n", tr("How many (1 to 100)"), "1")], tr("Give"),
                   lambda v, dlg: (dlg.close(), self.do("rb_admin_give", {"name": name, "what": "case:" + v["w"].strip().replace("case:", ""),
                                                                         "how_many": _int(v["n"], 1)}, tr("Given: it opens for free"))))

    def _undo_last(self, name: str) -> None:
        rows = self.fetch("rb_admin_audit", {}) or []
        last = next((r for r in rows if (r.get("target") or "").lower() == name.lower() and r.get("can_undo")), None)
        if last is None:
            return self.ctx.toast(tr("Nothing to undo for {name}", name=name), "warn")
        self.ctx.window.confirm(tr("Undo “{what}” on {target}?", what=last["action"], target=name),
                                lambda: self.do("rb_admin_undo", {"entry": last["id"]}, tr("Undone")), yes=tr("Undo"))

    def _give_dialog(self, name: str) -> None:
        chosen = getattr(self.ctx, "admin_item", "") or ""
        FormDialog(self.ctx, tr("Give to {name}", name=name),
                   [("w", tr("Item or case (pick one in Items, or type e.g. badge:crown:gold, case:vault)"), chosen),
                    ("n", tr("How many (1 to 100)"), "1")], tr("Give"),
                   lambda v, dlg: (dlg.close(), self.do("rb_admin_give", {"name": name, "what": v["w"],
                                                                         "how_many": _int(v["n"], 1)}, tr("Given"))))

    def _items(self, lay) -> None:
        cat = self.ctx.econ.catalog
        kind = int(getattr(self.ctx, "admin_kind", 1) or 1)
        from .games import GamePicker
        pick = GamePicker([tr("Badges"), tr("Balls"), tr("Lines"), tr("Fonts"), tr("Themes"), tr("Cases")], kind - 1)
        pick.changed.connect(lambda i: (setattr(self.ctx, "admin_kind", i + 1), setattr(self.ctx, "admin_base", ""), self.ctx.reload_page()))
        lay.addWidget(pick)
        chosen = getattr(self.ctx, "admin_item", "") or ""
        lay.addWidget(Label(tr("Selected: {what}", what=chosen or "—"), 11.5, GOLD_TEXT, bold=True, wrap_w=self.W))
        lay.addWidget(Label(tr("Pick an item, then open a user and press Give item or case. Or use it for a giveaway or a sale."),
                            10.5, TEXT_DIM, wrap_w=self.W))
        if kind == 6:
            from .collection import CASE_NAMES
            ids = [c["id"] for c in self.ctx.econ.cases]
            lay.addWidget(Table([(tr(CASE_NAMES.get(c, c)), "case:" + c, "") for c in ids], self.W,
                                lambda i: (setattr(self.ctx, "admin_item", "case:" + ids[i]), self.ctx.reload_page())))
            return
        want = KINDS[kind]
        base = getattr(self.ctx, "admin_base", "") or ""
        if not base:
            bases, seen = [], set()
            for k in sorted(cat, key=lambda k: (-int(cat[k].get("value") or 0) if want == "badge" else 0, k)):
                info = cat[k]
                if info.get("kind") == want and info.get("base") not in seen:
                    seen.add(info.get("base"))
                    bases.append(k if want == "theme" else f"{want}:{info['base']}:{'grey' if want != 'badge' or info['base'] not in ('galaxy','phoenix','glitch','crystal','dragon','rubenium') else 'prime'}")
            grid = ItemGrid(self.ctx, [{"item": b} for b in bases], self.W, 6, 54)

            def go(i: int) -> None:
                if want == "theme":
                    self.ctx.admin_item = bases[i]
                else:
                    self.ctx.admin_base = bases[i].split(":")[1]
                self.ctx.reload_page()
            grid.picked.connect(go)
            return lay.addWidget(grid)
        back = Button(tr("Back"), "ghost", 26)
        back.clicked.connect(lambda: (setattr(self.ctx, "admin_base", ""), self.ctx.reload_page()))
        lay.addWidget(back)
        ids = sorted((k for k, v in cat.items() if v.get("kind") == want and v.get("base") == base),
                     key=lambda k: -int(cat[k].get("value") or 0))
        grid = ItemGrid(self.ctx, [{"item": k, "text": coins_text(int(cat[k].get("value") or 0))} for k in ids], self.W, 6, 64,
                        ids.index(chosen) if chosen in ids else -1)
        grid.picked.connect(lambda i: (setattr(self.ctx, "admin_item", ids[i]), self.ctx.reload_page()))
        lay.addWidget(grid)

    def _cases(self, lay) -> None:
        from .collection import CASE_NAMES
        st = self.fetch("rb_admin_stats", {})
        if st is None:
            return lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
        lay.addWidget(Label(tr("Drop odds out of 10 000: coins, Common, Rare, Epic, Legendary, Mythic. Finish odds out of "
                               "100 000: Basic, Painted, Shiny, Titanium, Gold. Click a case to change it."), 10.5, TEXT_DIM, wrap_w=self.W))
        cases = st.get("cases") or []

        def edit(i: int) -> None:
            c = cases[i]
            FormDialog(self.ctx, tr(CASE_NAMES.get(c["id"], c["id"])),
                       [("p", tr("Price"), c["price"]), ("o", tr("Drop odds (6 numbers, total 10 000)"), ",".join(map(str, c["odds"]))),
                        ("v", tr("Finish odds (5 numbers, total 100 000)"), ",".join(map(str, c["variants"]))),
                        ("a", tr("Coins: lowest"), c["coin_min"]), ("b", tr("Coins: highest"), c["coin_max"])], tr("Save"),
                       lambda v, dlg: self._save_case(c["id"], v, dlg))
        lay.addWidget(Table([(tr(CASE_NAMES.get(c["id"], c["id"])), coins_text(int(c["price"])),
                              f"L {c['odds'][4] / 100:g}% · M {c['odds'][5] / 100:g}%") for c in cases], self.W, edit))

    def _save_case(self, cid: str, v: dict, dlg) -> None:
        try:
            odds = [int(x) for x in v["o"].split(",")]
            var = [int(x) for x in v["v"].split(",")]
        except ValueError:
            return dlg.say(tr("Numbers separated by commas"))
        if len(odds) != 6 or sum(odds) != 10000 or len(var) != 5 or sum(var) != 100000:
            return dlg.say(tr("Drop odds: 6 numbers, total 10 000. Finish odds: 5 numbers, total 100 000."))
        dlg.close()
        self.do("rb_admin_case", {"which": cid, "new_price": _int(v["p"], 1), "new_odds": odds, "new_variants": var,
                                  "new_min": _int(v["a"], 0), "new_max": _int(v["b"], 0)}, tr("Saved"))

    def _live(self, lay) -> None:
        live = self.ctx.econ.live
        line = hbox(spacing=6)
        ga = Button(tr("New giveaway"), "primary", 32, icon="gift")
        ga.clicked.connect(self._new_giveaway)
        sale = Button(tr("New special sale"), "primary", 32)
        sale.clicked.connect(self._new_sale)
        line.addWidget(ga, 1)
        line.addWidget(sale, 1)
        lay.addLayout(line)
        lay.addWidget(heading(tr("Giveaways")))
        gs = live.get("giveaways") or []
        if not gs:
            lay.addWidget(Label(tr("None right now"), 11, TEXT_FAINT))
        for g in gs:
            lay.addWidget(Label(f"{g['title']} · {g['state']} · {tr('{n} joined', n=g.get('entries', 0))} · "
                                f"{clock_text(int(g.get('left') or 0))}", 11.5, TEXT, wrap_w=self.W))
            if g["state"] == "live":
                l2 = hbox(spacing=6)
                draw = Button(tr("Draw now"), "primary", 26)
                draw.clicked.connect(lambda _=False, x=g: self.do("rb_admin_giveaway_end", {"giveaway": x["id"], "draw": True}, tr("Drawn")))
                stop = Button(tr("Cancel"), "ghost", 26)
                stop.clicked.connect(lambda _=False, x=g: self.do("rb_admin_giveaway_end", {"giveaway": x["id"], "draw": False}, tr("Cancelled")))
                l2.addWidget(draw, 1)
                l2.addWidget(stop, 1)
                lay.addLayout(l2)
        lay.addWidget(heading(tr("Sales")))
        ss = live.get("sales") or []
        if not ss:
            lay.addWidget(Label(tr("None right now"), 11, TEXT_FAINT))
        for s in ss:
            l3 = hbox(spacing=6)
            l3.addWidget(Label(f"-{s['pct']}%  {s['what']}  · {clock_text(int(s.get('left') or 0))}", 11.5, TEXT), 1)
            end = Button(tr("End"), "ghost", 26)
            end.clicked.connect(lambda _=False, x=s: self.do("rb_admin_sale_end", {"sale": x["id"]}, tr("Sale ended")))
            l3.addWidget(end)
            lay.addLayout(l3)

    def _new_giveaway(self) -> None:
        chosen = getattr(self.ctx, "admin_item", "") or ""
        kind = "case" if chosen.startswith("case:") else ("item" if chosen else "coins")
        what = chosen[5:] if kind == "case" else chosen

        def send(v: dict, dlg) -> None:
            k = {"pièces": "coins", "pieces": "coins", "coin": "coins", "clés": "keys", "cles": "keys", "key": "keys",
                 "objet": "item", "caisse": "case"}.get(v["k"].lower().strip(), v["k"].lower().strip())
            if k == "item" and v["w"].startswith("case:"):
                k, v["w"] = "case", v["w"][5:]
            if k == "case" and v["w"].startswith("case:"):
                v["w"] = v["w"][5:]
            if k not in ("coins", "keys", "item", "case"):
                return dlg.say(tr("Prize type: coins, keys, item or case"))
            dlg.close()
            self.do("rb_admin_giveaway", {"title": v["t"][:40] or "Giveaway", "kind": k, "what": v["w"],
                                          "amount": _int(v["a"], 1), "winners": _int(v["n"], 1),
                                          "minutes": _int(v["m"], 30), "min_hours": _int(v["h"], 0)}, tr("Giveaway live!"))
        FormDialog(self.ctx, tr("New giveaway"),
                   [("t", tr("Title"), tr("Giveaway")), ("k", tr("Prize type: coins, keys, item or case"), kind),
                    ("w", tr("Item or case id (empty for coins and keys)"), what), ("a", tr("Amount per winner"), "1000" if kind == "coins" else "1"),
                    ("n", tr("Number of winners (1 to 50)"), "1"), ("m", tr("Lasts (minutes)"), "30"),
                    ("h", tr("Hours with Rubenium needed to join"), "0")], tr("Start"), send,
                   tr("Everyone sees a golden Giveaway tab while it runs. Winners are drawn at random by the server."))

    def _new_sale(self) -> None:
        chosen = getattr(self.ctx, "admin_item", "") or ""

        def send(v: dict, dlg) -> None:
            dlg.close()
            self.do("rb_admin_sale", {"what": v["w"], "pct": _int(v["p"], 20), "minutes": _int(v["m"], 60)}, tr("Sale live!"))
        FormDialog(self.ctx, tr("New special sale"),
                   [("w", tr("Item (e.g. ball:orbit:blue), a group (ball:orbit = every colour, theme = every theme)"),
                     chosen if chosen and not chosen.startswith("case:") else "theme"),
                    ("p", tr("Percent off (1 to 90)"), "25"), ("m", tr("Lasts (minutes)"), "120")], tr("Start"), send,
                   tr("Shop prices only. The sale shows with sparks at the top of the shop."))

    def _settings(self, lay) -> None:
        st = self.fetch("rb_admin_stats", {})
        if st is None:
            return lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
        cfg = st.get("config") or {}
        keys = sorted(k for k in cfg if k != "reset_008")
        force = Button(tr("Everyone must update to my version"), "ghost", 30, icon="refresh")
        force.setToolTip(tr("Older versions can no longer play online until they update"))
        force.clicked.connect(lambda: self.ctx.window.confirm(
            tr("Lock online play for older versions of Rubenium?"), lambda: self.do("rb_admin_force_update", {}, tr("Done")),
            yes=tr("Yes")))
        lay.addWidget(force)
        lay.addWidget(Label(tr("Click a setting to change it. Changes are live for everyone."), 10.5, TEXT_DIM, wrap_w=self.W))

        def edit(i: int) -> None:
            k = keys[i]
            FormDialog(self.ctx, k, [("v", tr("New value"), cfg[k])], tr("Save"),
                       lambda v, dlg: self._save_setting(k, v["v"], dlg))
        lay.addWidget(Table([(k, "", str(cfg[k])) for k in keys], self.W, edit))

    def _save_setting(self, key: str, text: str, dlg) -> None:
        try:
            value = float(text.replace(",", "."))
        except ValueError:
            return dlg.say(tr("A number"))
        dlg.close()
        self.do("rb_admin_set", {"setting": key, "new_value": value}, tr("Saved"))

    def _log(self, lay) -> None:
        rows = self.fetch("rb_admin_audit", {})
        if rows is None:
            return lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
        lay.addWidget(Label(tr("Everything done in the admin panel. Click a line with ↩ to undo it (coins, keys, items, "
                               "cases, blocks, settings and the lock)."), 10.5, TEXT_DIM, wrap_w=self.W))

        def undo(i: int) -> None:
            r = rows[i]
            if r.get("undone"):
                return self.ctx.toast(tr("Already undone"), "warn")
            if not r.get("can_undo"):
                return self.ctx.toast(tr("This cannot be undone"), "warn")
            self.ctx.window.confirm(tr("Undo “{what}” on {target}?", what=r["action"], target=r.get("target") or "-"),
                                    lambda: self.do("rb_admin_undo", {"entry": r["id"]}, tr("Undone")), yes=tr("Undo"))
        lay.addWidget(Table([(("↩ " if r.get("can_undo") else ("✓ " if r.get("undone") else "")) + r["action"],
                              str(r.get("target") or "")[:16], str(r["at"])[5:16].replace("T", " "),
                              TEXT_DIM if r.get("undone") else ("#FFC94D" if r.get("can_undo") else TEXT)) for r in rows],
                            self.W, undo))

    # -- forgotten passwords: is it really them?
    VERDICTS = {"real": ("Looks real: asked from the account's own PC", "#3DDC84"),
                "fake": ("Looks fake: asked from another user's PC", "#FF5C6C"),
                "unsure": ("Not sure: a PC we do not know", "#FFC94D"),
                "no_account": ("No account with this name", "#9AA4AD")}

    def _help(self, lay) -> None:
        rows = self.fetch("rb_admin_resets", {})
        if rows is None:
            return lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
        lay.addWidget(Label(tr("Forgotten passwords. Check the details, then give a new password or refuse. The user "
                               "sees the new password on the PC that asked, and must change it after."), 10.5, TEXT_DIM, wrap_w=self.W))
        if not rows:
            return lay.addWidget(Label(tr("No requests."), 12, TEXT_DIM))
        for r in rows[:30]:
            text, col = self.VERDICTS.get(r.get("verdict"), ("?", TEXT_DIM))
            lay.addWidget(heading(f"{r.get('name', '?')}  ·  {str(r.get('at', ''))[5:16].replace('T', ' ')}  ·  {tr(r.get('state', ''))}"))
            lay.addWidget(Label(tr(text), 11.5, col, bold=True, wrap_w=self.W))
            facts = [tr("Message: {m}", m=r.get("msg") or "-")]
            if r.get("exists"):
                facts.append(tr("Account: {h} h played, last seen {t}", h=f"{int(r.get('minutes') or 0) / 60:.1f}",
                                t=str(r.get("seen") or "-")[:16].replace("T", " ")))
            if r.get("pc_owner"):
                facts.append(tr("This PC belongs to: {name}", name=r["pc_owner"]))
            facts.append(tr("Requests from this PC (7 days): {a} · for this name: {b}", a=r.get("pc_asks", 0), b=r.get("name_asks", 0)))
            for f in facts:
                lay.addWidget(Label(f, 10.5, TEXT_DIM, wrap_w=self.W))
            if r.get("state") == "open":
                line = hbox(spacing=6)
                yes = Button(tr("Give new password"), "primary", 28)
                no = Button(tr("Refuse"), "ghost", 28)
                rid = r["id"]
                import secrets
                temp = "Rb-" + secrets.token_hex(4)
                yes.clicked.connect(lambda _c=False, rid=rid, temp=temp: FormDialog(
                    self.ctx, tr("New password"), [("p", tr("Temporary password (8 or more)"), temp)], tr("Give"),
                    lambda v, dlg: (dlg.close(), self.do("rb_admin_reset_do", {"rid": rid, "new_password": v["p"]}, tr("Done")))))
                no.clicked.connect(lambda _c=False, rid=rid: self.do("rb_admin_reset_do", {"rid": rid, "new_password": None}, tr("Refused")))
                line.addWidget(yes, 1)
                line.addWidget(no, 1)
                lay.addLayout(line)


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
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def showEvent(self, _e) -> None:
        self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()

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
