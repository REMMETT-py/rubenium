"""Friends tab: add friends by username, see who is online, look at a profile and at play history."""
from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from .core import DANGER, S, sfx, TEXT, TEXT_DIM, alpha, font, lang, tr, ui
from .pages import Page
from .widgets import Button, IconButton, Label, hbox, heading, vbox

GAME_NAMES = {"slots": "Slots", "plinko": "Plinko", "dice": "Dice", "mines": "Bombs", "rocket": "Rocket",
              "blackjack": "Blackjack", "daily": "Daily case", "spin": "Free spin"}


def played_text(minutes: int) -> str:
    text = f"{minutes / 60:.1f}"
    return (text.replace(".", ",") if lang() == "fr" else text) + " h"


class AskDialog(QWidget):
    """A small window with one text box (typing needs the keyboard, which the menu never takes from a game)."""

    def __init__(self, ctx, title: str, hint: str, button: str, on_text, max_len: int = 10) -> None:
        super().__init__()
        from PyQt6.QtWidgets import QLineEdit
        from .window import work_area
        self._on_text = on_text
        self.setWindowTitle("Rubenium")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedWidth(S(300))
        lay = vbox(self, 8, (18, 18, 18, 18))
        lay.addWidget(Label(title, 15, bold=True))
        self.edit = QLineEdit()
        self.edit.setMaxLength(max_len)
        self.edit.setPlaceholderText(hint)
        self.edit.setFixedHeight(S(34))
        self.edit.setStyleSheet(
            f"QLineEdit {{ background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10);"
            f" border-radius: {S(9)}px; padding: 0 {S(10)}px; color: {TEXT}; font-size: {S(13)}px; }}"
            f"QLineEdit:focus {{ border: 1px solid rgba(255,255,255,0.45); }}")
        self.edit.returnPressed.connect(self._go)
        lay.addWidget(self.edit)
        self.note = Label("", 11, DANGER)
        self.note.setFixedHeight(S(16))
        lay.addWidget(self.note)
        line = hbox(spacing=6)
        cancel = Button(tr("Cancel"), "ghost", 34)
        cancel.clicked.connect(self.close)
        go = Button(button, "primary", 34)
        go.clicked.connect(self._go)
        line.addWidget(cancel, 1)
        line.addWidget(go, 1)
        lay.addLayout(line)
        self.adjustSize()
        area = work_area(ctx.window.card_global().center())
        self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()

    def say(self, text: str) -> None:
        self.note.set_text(text)

    def _go(self) -> None:
        text = self.edit.text().strip()
        if text:
            self._on_text(text, self)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.close()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(alpha(ui.accent, 0.45), 1.2))
        p.setBrush(QColor(12, 15, 16, 252))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), S(16), S(16))


class FriendRow(QWidget):
    """One friend or request: online dot, name, and what can be done."""

    def __init__(self, page, info: dict) -> None:
        super().__init__()
        self.page, self.info = page, info
        self.setFixedHeight(S(40))
        lay = hbox(self, 6, (34, 0, 6, 0))
        lay.addStretch(1)
        name, state = info["username"], info["state"]
        if state == "friend":
            b = Button(tr("View"), "ghost", 28)
            b.clicked.connect(lambda: page.open_profile(name))
            lay.addWidget(b)
        elif state == "asks":
            yes, no = Button(tr("Accept"), "primary", 28), Button(tr("Decline"), "ghost", 28)
            yes.clicked.connect(lambda: page.act("rb_friend_add", name))
            no.clicked.connect(lambda: page.act("rb_friend_remove", name))
            lay.addWidget(yes)
            lay.addWidget(no)
        else:
            b = Button(tr("Cancel"), "ghost", 28)
            b.clicked.connect(lambda: page.act("rb_friend_remove", name))
            lay.addWidget(b)
        for i in range(lay.count()):
            w = lay.itemAt(i).widget()
            if w is not None:
                w.setFixedWidth(max(S(64), w.sizeHint().width()))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 2, -0.5, -2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.04))
        p.drawRoundedRect(r, S(10), S(10))
        info = self.info
        friend = info["state"] == "friend"
        p.setBrush(QColor("#3DDC84") if info.get("online") else alpha("#FFFFFF", 0.22))
        p.drawEllipse(QPointF(r.left() + S(16), r.center().y()), S(4), S(4))
        p.setPen(QColor(TEXT))
        p.setFont(font(12.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(r.left() + S(30), r.top(), S(110), r.height() / (1 if friend else 2) + (0 if friend else S(3))),
                   int(Qt.AlignmentFlag.AlignVCenter if friend else Qt.AlignmentFlag.AlignBottom), info["username"])
        if not friend:
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(10, QFont.Weight.DemiBold))
            p.drawText(QRectF(r.left() + S(30), r.center().y() + S(1), S(150), r.height() / 2),
                       int(Qt.AlignmentFlag.AlignTop), tr("Wants to be friends") if info["state"] == "asks"
                       else tr("Request sent"))


class FriendsPage(Page):
    key = "friends"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.lay = vbox(self, 6)
        self.rows: list = []
        self.friends = getattr(ctx, "friends_cache", None)
        self._poll = QTimer(self)
        self._poll.setInterval(30000)
        self._poll.timeout.connect(self.refresh)
        self._build()

    # -- drawing the page from what we know
    def _clear(self) -> None:
        while self.lay.count():
            item = self.lay.takeAt(0)
            if item.widget() is not None:
                item.widget().setParent(None)
                item.widget().deleteLater()
            elif item.layout() is not None:
                sub = item.layout()
                while sub.count():
                    w = sub.takeAt(0).widget()
                    if w is not None:
                        w.setParent(None)
                        w.deleteLater()

    def _build(self) -> None:
        ctx = self.ctx
        self._clear()
        who = getattr(ctx, "friends_profile", None)
        if who:
            return self._profile(who)
        top = hbox(spacing=8)
        top.addWidget(Label(tr("Friends"), 16, bold=True), 1)
        again = IconButton("refresh", 30, tip=tr("Refresh"))
        again.clicked.connect(self._refresh_all)
        top.addWidget(again)
        add = Button(tr("Add friend"), "primary", 30)
        add.setFixedWidth(max(S(110), add.sizeHint().width()))
        add.clicked.connect(self._add)
        top.addWidget(add)
        self.lay.addLayout(top)
        if not ctx.online.logged_in():
            return self.lay.addWidget(Label(tr("Log in to see your friends"), 12, TEXT_DIM))
        if self.friends is None:
            return self.lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
        if not self.friends:
            return self.lay.addWidget(Label(tr("No friends yet. Add one with their username."), 12, TEXT_DIM,
                                            wrap_w=self.W))
        asks = [f for f in self.friends if f["state"] == "asks"]
        mine = [f for f in self.friends if f["state"] == "friend"]
        sent = [f for f in self.friends if f["state"] == "asked"]
        online = sum(1 for f in mine if f.get("online"))
        for title, group in ((tr("Requests"), asks), (tr("Friends") + f"  ·  {online} " + tr("online"), mine),
                             (tr("Sent"), sent)):
            if group:
                self.lay.addWidget(heading(title))
                for info in group:
                    self.lay.addWidget(FriendRow(self, info))

    def _redo(self) -> None:
        if self.ctx.window.current == "friends" and self.ctx.window.expanded:
            self.ctx.reload_page()

    def _refresh_all(self) -> None:
        """The refresh button: friends, the open profile, and your own coins, items and time played."""
        sfx.play("pick")
        self.ctx.econ.refresh()
        self.ctx.online._tick()
        if getattr(self.ctx, "friends_profile", None):
            self.ctx.friends_data = None
            self.ctx.reload_page()
        else:
            self.refresh()
            self.ctx.toast(tr("Refreshed"))

    # -- server
    def refresh(self) -> None:
        if self.ctx.online.logged_in():
            self.ctx.online.ask("rb_friends_list", {}, self._listed)

    def _listed(self, ok: bool, data) -> None:
        if ok and isinstance(data, list) and data != self.friends:
            self.friends = self.ctx.friends_cache = data
            if not getattr(self.ctx, "friends_profile", None):
                self._redo()
        elif ok and self.friends is None:
            self.friends = self.ctx.friends_cache = []
            self._redo()

    def act(self, fn: str, name: str, then=None) -> None:
        sfx.play("pick")

        def done(ok: bool, data) -> None:
            if not ok:
                self.ctx.toast(tr(data), "warn")
            if then:
                then(ok)
            self.refresh()
        self.ctx.online.ask(fn, {"name": name}, done)

    def _add(self) -> None:
        def send(name: str, dialog) -> None:
            def done(ok: bool, data) -> None:
                if ok:
                    dialog.close()
                    self.ctx.toast(tr("You are now friends") if data == "friends" else tr("Request sent"))
                    self.refresh()
                else:
                    dialog.say(tr(data))
            self.ctx.online.ask("rb_friend_add", {"name": name}, done)
        self._dialog = AskDialog(self.ctx, tr("Add friend"), tr("Username"), tr("Add"), send)

    # -- a profile
    def open_profile(self, name) -> None:
        sfx.play("pick")
        self.ctx.friends_profile = name
        self.ctx.friends_data = None
        self._redo()

    def _profile(self, name: str) -> None:
        ctx = self.ctx
        data = getattr(ctx, "friends_data", None)
        top = hbox(spacing=8)
        back = IconButton("back", 30, tip=tr("Back"))
        back.clicked.connect(lambda: self.open_profile(None))
        top.addWidget(back)
        top.addWidget(Label(name, 16, bold=True), 1)
        again = IconButton("refresh", 30, tip=tr("Refresh"))
        again.clicked.connect(self._refresh_all)
        top.addWidget(again)
        self.lay.addLayout(top)
        if data is None:
            self.lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
            return ctx.online.ask("rb_profile", {"name": name}, self._got_profile)
        prof, hist = data.get("profile") or {}, data.get("history")
        self.lay.addWidget(ProfileCard(prof))
        line = hbox(spacing=6)
        if prof.get("friend"):
            rm = Button(tr("Remove friend"), "ghost", 30)
            rm.clicked.connect(lambda: ctx.window.confirm(tr("Remove {name} from your friends?", name=name),
                               lambda: self.act("rb_friend_remove", name, lambda _ok: self.open_profile(None)),
                               yes=tr("Remove")))
            line.addWidget(rm, 1)
        self.lay.addLayout(line)
        badges = list(prof.get("badges") or [])
        self.lay.addWidget(heading(tr("Badges") + f"  ·  {len(badges)}"))
        if badges:
            worn_now = [(prof.get("equip") or {}).get(k) for k in ("badge1", "badge2", "badge3")]
            self.lay.addWidget(BadgeStrip(ctx, badges, [w for w in worn_now if w], self.W))
        else:
            self.lay.addWidget(Label(tr("No badges yet"), 12, TEXT_DIM))
        self.lay.addWidget(heading(tr("History")))
        if hist is None:
            self.lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
        elif not hist.get("rows"):
            self.lay.addWidget(Label(tr("Nothing played yet"), 12, TEXT_DIM))
        else:
            self.lay.addWidget(HistoryList(hist, self.W))

    def _got_profile(self, ok: bool, data) -> None:
        name = getattr(self.ctx, "friends_profile", None)
        if not name:
            return
        if not ok:
            self.ctx.toast(tr(data), "warn")
            return self.open_profile(None)
        self.ctx.friends_data = {"profile": data, "history": None}
        self._redo()
        self.ctx.online.ask("rb_history", {"name": name}, self._got_history)

    def _got_history(self, ok: bool, data) -> None:
        cur = getattr(self.ctx, "friends_data", None)
        if cur is None or not getattr(self.ctx, "friends_profile", None):
            return
        cur["history"] = data if ok and isinstance(data, dict) else {"rows": []}
        self._redo()

    def on_show(self) -> None:
        self.refresh()
        self._poll.start()

    def on_hide(self) -> None:
        self._poll.stop()


class ProfileCard(QWidget):
    """Online or not, time played, member since."""

    def __init__(self, prof: dict) -> None:
        super().__init__()
        self.prof = prof
        self.setFixedHeight(S(58))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha("#FFFFFF", 0.08), 1))
        p.setBrush(alpha("#FFFFFF", 0.04))
        p.drawRoundedRect(r, S(11), S(11))
        prof = self.prof
        since = str(prof.get("since", ""))[:10]
        if len(since) == 10 and lang() == "fr":
            since = f"{since[8:10]}/{since[5:7]}/{since[0:4]}"
        cells = ((tr("Online") if prof.get("online") else tr("Offline"), tr("Status")),
                 (played_text(int(prof.get("minutes", 0))), tr("Played")), (since, tr("Member since")))
        w = r.width() / 3
        for i, (big, small) in enumerate(cells):
            box = QRectF(r.left() + i * w, r.top(), w, r.height())
            p.setPen(QColor("#3DDC84") if (i == 0 and prof.get("online")) else QColor(TEXT))
            p.setFont(font(13, QFont.Weight.Bold))
            p.drawText(QRectF(box.left(), box.top() + S(9), box.width(), S(22)), int(Qt.AlignmentFlag.AlignCenter), big)
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(10, QFont.Weight.DemiBold))
            p.drawText(QRectF(box.left(), box.top() + S(32), box.width(), S(16)), int(Qt.AlignmentFlag.AlignCenter), small)


class HistoryList(QWidget):
    """The last rounds played: game, bet, what came back."""

    def __init__(self, hist: dict, width: int) -> None:
        super().__init__()
        self.rows = (hist.get("rows") or [])[:40]
        self.hist = hist
        self.row_h = S(24)
        self.setFixedSize(width, int(S(30) + self.row_h * len(self.rows)))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        from .wallet import coins_text
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.hist
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(0, 0, self.width(), S(22)), int(Qt.AlignmentFlag.AlignVCenter),
                   tr("Bet {a} · Won {b} · Best win {c} · Cases {d}", a=coins_text(int(h.get("bet", 0))),
                      b=coins_text(int(h.get("won", 0))), c=coins_text(int(h.get("best", 0))), d=int(h.get("cases", 0))))
        for i, row in enumerate(self.rows):
            r = QRectF(0, S(30) + i * self.row_h, self.width(), self.row_h)
            if i % 2 == 0:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha("#FFFFFF", 0.035))
                p.drawRoundedRect(r.adjusted(0, 1, 0, -1), S(6), S(6))
            game = str(row.get("game", ""))
            name = tr("Case") if game.startswith("case:") else tr(GAME_NAMES.get(game, game))
            bet, paid = int(row.get("bet") or 0), int(row.get("paid") or 0)
            p.setPen(QColor(TEXT))
            p.setFont(font(11.5, QFont.Weight.DemiBold))
            p.drawText(r.adjusted(S(8), 0, 0, 0), int(Qt.AlignmentFlag.AlignVCenter), name)
            p.setPen(QColor(TEXT_DIM))
            p.drawText(QRectF(r.left() + r.width() * 0.42, r.top(), r.width() * 0.25, r.height()),
                       int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), coins_text(bet) if bet else "")
            good = paid > bet
            p.setPen(QColor("#3DDC84") if good else (QColor(TEXT_DIM) if paid else QColor("#FF5C6C")))
            p.setFont(font(11.5, QFont.Weight.Bold))
            p.drawText(r.adjusted(0, 0, -S(8), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                       ("+" if paid else "") + coins_text(paid))



class BadgeStrip(QWidget):
    """A player's badges, best first; the three they have on show come first with a light ring."""
    COLS = 9

    def __init__(self, ctx, items: list, worn: list, width: int) -> None:
        super().__init__()
        self.ctx = ctx
        self.items = (worn + [i for i in items if i not in worn])[:36]
        self.worn = set(worn)
        self.cell = width / self.COLS
        rows = (len(self.items) + self.COLS - 1) // self.COLS
        self.setFixedSize(width, int(rows * self.cell))
        self.setMouseTracking(True)
        self._tick = QTimer(self)
        self._tick.setInterval(50)
        self._tick.timeout.connect(self.update)

    def showEvent(self, _e) -> None:
        from .badges import item_animated
        if any(item_animated(i) for i in self.items):
            self._tick.start()

    def hideEvent(self, _e) -> None:
        self._tick.stop()

    def mouseMoveEvent(self, e) -> None:
        from .collection import badge_label
        i = int(e.position().y() // self.cell) * self.COLS + int(e.position().x() // self.cell)
        self.setToolTip(badge_label(self.items[i]) if 0 <= i < len(self.items) else "")

    def paintEvent(self, _e) -> None:
        import time
        from .badges import paint_item
        from .econ import RARITY_COLOURS
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        for i, item in enumerate(self.items):
            c = QPointF((i % self.COLS + 0.5) * self.cell, (i // self.COLS + 0.5) * self.cell)
            col = QColor(RARITY_COLOURS.get(self.ctx.econ.rarity(item), "#9AA4AD"))
            d = self.cell - S(6)
            p.setPen(QPen(QColor("#FFFFFF") if item in self.worn else alpha(col, 0.5), 1.2))
            p.setBrush(alpha(col, 0.10))
            p.drawEllipse(c, d / 2, d / 2)
            g = d * 0.5
            paint_item(p, item, QRectF(c.x() - g / 2, c.y() - g / 2, g, g), now)
