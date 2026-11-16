"""2.4 screens: messages, leaderboards, trade history, collection sets, the daily login reward,
settings backups and the song history."""
import json
import time

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from .core import DATA_DIR, S, sfx, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, mix, tr, ui
from .shop import GOLD_TEXT
from .wallet import coins_text, paint_coin
from .widgets import Button, IconButton, Label, Segmented, Toggle, draw_icon, hbox, vbox

DANGER_RED = "#FF5C6C"


class FloatWindow(QWidget):
    """A small window of its own (it may take the keyboard, unlike the menu)."""

    def __init__(self, ctx, width: int = 320) -> None:
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle("Rubenium")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedWidth(S(width))

    def centre(self) -> None:
        from .window import work_area
        self.adjustSize()
        area = work_area(self.ctx.window.card_global().center())
        self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)
        self.show()
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.close()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(alpha(ui.accent, 0.45), 1.2))
        p.setBrush(QColor(12, 15, 16, 252))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), S(16), S(16))


def ago(at) -> str:
    """'5 min ago' from a server time."""
    from .friends import ago_text
    try:
        return ago_text(at)
    except Exception:  # noqa: BLE001
        return ""


# ================================================================ messages
class Bubbles(QWidget):
    """The messages of one chat, newest at the bottom."""

    def __init__(self, width: int) -> None:
        super().__init__()
        self.rows: list = []
        self.setFixedWidth(width)
        self.setFixedHeight(S(300))
        self.scroll = 0.0

    def set_rows(self, rows: list) -> None:
        self.rows = rows
        self.scroll = 0.0
        self.update()

    def wheelEvent(self, e) -> None:
        self.scroll = max(0.0, self.scroll + e.angleDelta().y() / 120 * S(40))
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = font(11.5)
        fm = QFontMetrics(f)
        p.setFont(f)
        y = self.height() + self.scroll
        maxw = int(self.width() * 0.74)
        if not self.rows:
            p.setPen(QColor(TEXT_DIM))
            p.drawText(QRectF(self.rect()), int(Qt.AlignmentFlag.AlignCenter), tr("No messages yet: say hi!"))
            return
        for m in reversed(self.rows):
            text = str(m.get("text", ""))
            box = fm.boundingRect(0, 0, maxw - S(20), 2000, int(Qt.TextFlag.TextWordWrap), text)
            h = box.height() + S(14)
            w = box.width() + S(22)
            y -= h + S(6)
            if y + h < 0:
                break
            mine = bool(m.get("mine"))
            r = QRectF(self.width() - w - S(2) if mine else S(2), y, w, h)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(ui.accent, 0.85) if mine else QColor("#232A33"))
            p.drawRoundedRect(r, S(10), S(10))
            p.setPen(QColor("#0B0E10") if mine and ui.accent.lightnessF() > 0.6 else QColor(TEXT))
            p.drawText(r.adjusted(S(11), S(7), -S(11), -S(7)), int(Qt.TextFlag.TextWordWrap), text)


class ChatWindow(FloatWindow):
    """A chat with one friend. Typing works here (it is its own window)."""

    def __init__(self, ctx, name: str) -> None:
        super().__init__(ctx, 330)
        from PyQt6.QtWidgets import QLineEdit
        self.name = name
        self.muted = False
        lay = vbox(self, 8, (16, 14, 16, 16))
        top = hbox(spacing=6)
        top.addWidget(Label(name, 15, bold=True), 1)
        self.mute_btn = Button(tr("Mute"), "ghost", 26)
        self.mute_btn.setToolTip(tr("Muted: no pop-ups or sounds for this friend's messages"))
        self.mute_btn.clicked.connect(self._mute)
        top.addWidget(self.mute_btn)
        close = IconButton("close", 26, tip=tr("Close"))
        close.clicked.connect(self.close)
        top.addWidget(close)
        lay.addLayout(top)
        self.bubbles = Bubbles(S(298))
        lay.addWidget(self.bubbles)
        line = hbox(spacing=6)
        self.edit = QLineEdit()
        self.edit.setMaxLength(300)
        self.edit.setPlaceholderText(tr("Write a message…"))
        self.edit.setFixedHeight(S(34))
        self.edit.setStyleSheet(
            f"QLineEdit {{ background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10);"
            f" border-radius: {S(9)}px; padding: 0 {S(10)}px; color: {TEXT}; font-size: {S(13)}px; }}"
            f"QLineEdit:focus {{ border: 1px solid rgba(255,255,255,0.45); }}")
        self.edit.returnPressed.connect(self._send)
        send = Button(tr("Send"), "primary", 34)
        send.clicked.connect(self._send)
        line.addWidget(self.edit, 1)
        line.addWidget(send)
        lay.addLayout(line)
        self._poll = QTimer(self)
        self._poll.setInterval(4000)
        self._poll.timeout.connect(self.load)
        self._poll.start()
        info = next((t for t in (getattr(ctx, "threads_data", None) or []) if t.get("name") == name), {})
        self._set_muted(bool(info.get("muted")))
        self.load()
        self.centre()
        self.edit.setFocus()

    def load(self) -> None:
        def got(ok: bool, data) -> None:
            if ok and isinstance(data, list):
                if [m.get("id") for m in data] != [m.get("id") for m in self.bubbles.rows]:
                    self.bubbles.set_rows(data)
        self.ctx.online.ask("rb_msg_get", {"name": self.name}, got)

    def _send(self) -> None:
        text = self.edit.text().strip()
        if not text:
            return
        self.edit.clear()
        self.bubbles.set_rows(self.bubbles.rows + [{"id": -1, "mine": True, "text": text}])

        def done(ok: bool, data) -> None:
            if not ok:
                self.ctx.toast(tr(str(data)), "warn")
            self.load()
        self.ctx.econ.call("rb_msg_send", {"name": self.name, "body": text}, done)

    def _set_muted(self, on: bool) -> None:
        self.muted = on
        self.mute_btn.set_text(tr("Unmute") if on else tr("Mute"))

    def _mute(self) -> None:
        want = not self.muted

        def done(ok: bool, _data) -> None:
            if ok:
                self._set_muted(want)
                self.ctx.threads_data = None
        self.ctx.online.ask("rb_msg_mute", {"name": self.name, "mute": want}, done)

    def closeEvent(self, e) -> None:
        self._poll.stop()
        self.ctx.threads_data = None
        super().closeEvent(e)


def open_chat(ctx, name: str) -> None:
    old = getattr(ctx, "_chat", None)
    try:
        if old is not None and old.isVisible():
            old.close()
    except RuntimeError:
        pass
    ctx._chat = ChatWindow(ctx, name)


class ThreadRow(QWidget):
    def __init__(self, page, t: dict) -> None:
        super().__init__()
        self.page, self.t = page, t
        self.setFixedHeight(S(46))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hover = False

    def enterEvent(self, _e) -> None:
        self.hover = True
        self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = False
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if self.rect().contains(e.position().toPoint()):
            sfx.play("pick")
            open_chat(self.page.ctx, self.t.get("name", ""))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.07 if self.hover else 0.04))
        p.drawRoundedRect(r, S(10), S(10))
        t = self.t
        p.setBrush(QColor("#3DDC84") if t.get("online") else alpha("#FFFFFF", 0.2))
        p.drawEllipse(QPointF(r.left() + S(14), r.center().y()), S(4), S(4))
        p.setPen(QColor(TEXT))
        p.setFont(font(12, QFont.Weight.Bold))
        name = t.get("name", "?") + ("  🔕" if t.get("muted") else "")
        p.drawText(QRectF(r.left() + S(26), r.top() + S(5), r.width() - S(90), S(18)), int(Qt.AlignmentFlag.AlignVCenter), name)
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10.5))
        last = str(t.get("last") or tr("No messages yet"))
        last = QFontMetrics(font(10.5)).elidedText(last, Qt.TextElideMode.ElideRight, int(r.width() - S(90)))
        p.drawText(QRectF(r.left() + S(26), r.top() + S(23), r.width() - S(90), S(16)), int(Qt.AlignmentFlag.AlignVCenter), last)
        n = int(t.get("unread") or 0)
        if n:
            badge = QRectF(r.right() - S(34), r.center().y() - S(10), S(24), S(20))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ui.accent)
            p.drawRoundedRect(badge, S(10), S(10))
            p.setPen(QColor("#0B0E10"))
            p.setFont(font(10, QFont.Weight.Bold))
            p.drawText(badge, int(Qt.AlignmentFlag.AlignCenter), str(min(n, 99)))
        elif t.get("last_at"):
            p.setPen(QColor(TEXT_FAINT))
            p.setFont(font(9.5))
            p.drawText(r.adjusted(0, 0, -S(10), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), ago(t["last_at"]))


def build_messages(page, lay) -> None:
    ctx = page.ctx
    data = getattr(ctx, "threads_data", None)

    def got(ok: bool, rows) -> None:
        if ok and isinstance(rows, list) and rows != getattr(ctx, "threads_data", None):
            ctx.threads_data = rows
            ctx.msg_unread = sum(int(t.get("unread") or 0) for t in rows)
            if ctx.window.current == "friends" and int(getattr(ctx, "social_tab", 0) or 0) == 2:
                ctx.reload_page()
    ctx.online.ask("rb_msg_threads", {}, got)
    if data is None:
        return lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
    if not data:
        return lay.addWidget(Label(tr("Add friends to send them messages."), 11.5, TEXT_DIM, wrap_w=page.W))
    lay.addWidget(Label(tr("Click a friend to chat. Mute stops pop-ups for that friend."), 10.5, TEXT_DIM, wrap_w=page.W))
    for t in data:
        lay.addWidget(ThreadRow(page, t))


# ================================================================ leaderboards
BOARDS = [("coins", "Richest"), ("worth", "Worth"), ("badges", "Badges"), ("hours", "Hours"),
          ("streak", "Streak"), ("tap", "Beat Tap"), ("park", "Parking"), ("memory", "Memory")]
BOARD_NOTES = {"coins": "Most coins right now", "worth": "What their items are worth", "badges": "Different badges owned",
               "hours": "Hours with Rubenium", "streak": "Days in a row of daily rewards", "tap": "Best Beat Tap score (%)",
               "park": "Parking puzzles solved", "memory": "Memory games finished"}


class LeaderRow(QWidget):
    def __init__(self, row: dict, kind: str) -> None:
        super().__init__()
        self.row, self.kind = row, kind
        self.setFixedHeight(S(30))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        row = self.row
        rank = int(row.get("rank") or 0)
        if row.get("me"):
            p.setPen(QPen(alpha(ui.accent, 0.6), 1.2))
            p.setBrush(alpha(ui.accent, 0.10))
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha("#FFFFFF", 0.035))
        p.drawRoundedRect(r, S(8), S(8))
        medal = {1: "#FFD34D", 2: "#C9D1D9", 3: "#D98A4A"}.get(rank)
        if medal:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(medal))
            p.drawEllipse(QPointF(r.left() + S(16), r.center().y()), S(9), S(9))
            p.setPen(QColor("#0B0E10"))
        else:
            p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10.5, QFont.Weight.Bold))
        p.drawText(QRectF(r.left() + S(4), r.top(), S(24), r.height()), int(Qt.AlignmentFlag.AlignCenter), str(rank))
        p.setPen(QColor(TEXT))
        p.setFont(font(11.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(r.left() + S(34), r.top(), r.width() - S(140), r.height()), int(Qt.AlignmentFlag.AlignVCenter), str(row.get("name", "")))
        v = int(row.get("value") or 0)
        text = coins_text(v) if self.kind in ("coins", "worth") else (f"{v}%" if self.kind == "tap" else
                                                                       (tr("{n} days", n=v) if self.kind == "streak" else
                                                                        (f"{v} h" if self.kind == "hours" else str(v))))
        p.setPen(QColor(GOLD_TEXT if self.kind in ("coins", "worth") else TEXT))
        p.drawText(r.adjusted(0, 0, -S(10), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), text)


def build_leaders(page, lay) -> None:
    ctx = page.ctx
    k = int(getattr(ctx, "board_kind", 0) or 0)
    friends = bool(getattr(ctx, "board_friends", False))
    seg = Segmented([tr("Everyone"), tr("Friends")], 1 if friends else 0)
    seg.changed.connect(lambda i: (setattr(ctx, "board_friends", i == 1), setattr(ctx, "board_data", None), ctx.reload_page()))
    lay.addWidget(seg)
    from .games import GamePicker
    pick = GamePicker([tr(n) for _k, n in BOARDS], k)
    pick.changed.connect(lambda i: (setattr(ctx, "board_kind", i), setattr(ctx, "board_data", None), ctx.reload_page()))
    lay.addWidget(pick)
    kind = BOARDS[k][0]
    key = (kind, friends)
    data = getattr(ctx, "board_data", None)

    def got(ok: bool, rows) -> None:
        if ok and isinstance(rows, dict):
            if getattr(ctx, "board_data", None) != (key, rows):
                ctx.board_data = (key, rows)
                if ctx.window.current == "friends" and int(getattr(ctx, "social_tab", 0) or 0) == 3:
                    ctx.reload_page()
        elif not ok:
            ctx.toast(tr(str(rows)), "warn")
    ctx.online.ask("rb_leaders", {"kind": kind, "friends": friends}, got)
    if not data or data[0] != key:
        return lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
    rows = data[1]
    lay.addWidget(Label(tr(BOARD_NOTES[kind]), 10.5, TEXT_DIM))
    me = rows.get("me") or {}
    if me:
        lay.addWidget(Label(tr("Your rank: #{n}", n=me.get("rank", "?")), 11.5, GOLD_TEXT, bold=True))
    top = rows.get("top") or []
    if not top:
        lay.addWidget(Label(tr("Nobody here yet."), 11.5, TEXT_DIM))
    for row in top[:50]:
        lay.addWidget(LeaderRow(row, kind))


# ================================================================ trade history
class TradeCard(QWidget):
    def __init__(self, ctx, t: dict, width: int) -> None:
        super().__init__()
        self.ctx, self.t = ctx, t
        self.setFixedWidth(width)
        n = max(len(t.get("gave") or []), len(t.get("got") or []), 1)
        self.setFixedHeight(S(52) + S(26) * ((n + 3) // 4))

    def paintEvent(self, _e) -> None:
        from .badges import paint_item
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        t = self.t
        p.setPen(QPen(alpha("#FFFFFF", 0.08), 1))
        p.setBrush(alpha("#FFFFFF", 0.035))
        p.drawRoundedRect(r, S(10), S(10))
        p.setPen(QColor(TEXT))
        p.setFont(font(11.5, QFont.Weight.Bold))
        head = tr("With {name}", name=t.get("other", "?")) + ("  ·  " + tr("UNDONE BY ADMIN") if t.get("undone") else "")
        p.drawText(QRectF(r.left() + S(10), r.top() + S(6), r.width() - S(20), S(16)), int(Qt.AlignmentFlag.AlignVCenter), head)
        p.setPen(QColor(TEXT_FAINT))
        p.setFont(font(9.5))
        p.drawText(QRectF(r.left() + S(10), r.top() + S(6), r.width() - S(20), S(16)),
                   int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), ago(t.get("at")))
        half = (r.width() - S(20)) / 2
        now = time.monotonic()
        for side, (label, items, coins, col) in enumerate(((tr("You gave"), t.get("gave") or [], int(t.get("gave_coins") or 0), DANGER_RED),
                                                           (tr("You got"), t.get("got") or [], int(t.get("got_coins") or 0), "#3DDC84"))):
            x = r.left() + S(10) + side * half
            p.setPen(QColor(col))
            p.setFont(font(9.5, QFont.Weight.Bold))
            p.drawText(QRectF(x, r.top() + S(24), half, S(14)), int(Qt.AlignmentFlag.AlignVCenter), label.upper()
                       + (f"  +{coins_text(coins)}" if coins else ""))
            for k, item in enumerate(items[:12]):
                paint_item(p, item, QRectF(x + (k % 4) * S(26), r.top() + S(42) + (k // 4) * S(26), S(22), S(22)), now)
            if not items:
                p.setPen(QColor(TEXT_FAINT))
                p.setFont(font(10))
                p.drawText(QRectF(x, r.top() + S(42), half, S(20)), int(Qt.AlignmentFlag.AlignVCenter), tr("coins only") if coins else "—")


def build_trade_history(page, lay) -> None:
    ctx = page.ctx
    data = getattr(ctx, "trade_hist", None)

    def got(ok: bool, rows) -> None:
        if ok and isinstance(rows, list) and rows != getattr(ctx, "trade_hist", None):
            ctx.trade_hist = rows
            if ctx.window.current == "friends" and int(getattr(ctx, "social_tab", 0) or 0) == 4:
                ctx.reload_page()
    ctx.online.ask("rb_trade_history", {}, got)
    if data is None:
        return lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
    if not data:
        return lay.addWidget(Label(tr("No trades yet."), 11.5, TEXT_DIM))
    lay.addWidget(Label(tr("{n} trades", n=len(data)), 10.5, TEXT_DIM))
    for t in data[:60]:
        lay.addWidget(TradeCard(ctx, t, page.W))


# ================================================================ collection sets
SETS = {"row_standard": "Every Common badge (12)", "row_rare": "Every Rare badge (12)",
        "row_special": "Every Epic badge (12)", "row_epic": "Every Legendary badge (12)",
        "row_exotic": "Every Mythic badge (6)", "rainbow": "All 8 Painted colours of one badge",
        "shiny5": "5 Shiny badges", "titanium3": "3 Titanium badges", "gold1": "A Gold badge"}


class SetRow(QWidget):
    def __init__(self, page, s: dict) -> None:
        super().__init__()
        self.page, self.s = page, s
        self.setFixedHeight(S(52))
        done = int(s.get("have") or 0) >= int(s.get("goal") or 1)
        self.can = done and not s.get("claimed")
        self.setCursor(Qt.CursorShape.PointingHandCursor if self.can else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, e) -> None:
        if self.can and self.rect().contains(e.position().toPoint()):
            self.page.claim_set(self.s["set_id"])

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        s = self.s
        have, goal = int(s.get("have") or 0), max(1, int(s.get("goal") or 1))
        claimed = bool(s.get("claimed"))
        p.setPen(QPen(alpha(GOLD_TEXT, 0.7) if self.can else alpha("#FFFFFF", 0.08), 1.2))
        p.setBrush(alpha(GOLD_TEXT, 0.10) if self.can else alpha("#FFFFFF", 0.035))
        p.drawRoundedRect(r, S(10), S(10))
        p.setPen(QColor(TEXT if not claimed else TEXT_DIM))
        p.setFont(font(11.5, QFont.Weight.Bold))
        p.drawText(QRectF(r.left() + S(10), r.top() + S(6), r.width() - S(120), S(16)), int(Qt.AlignmentFlag.AlignVCenter),
                   tr(SETS.get(s.get("set_id"), s.get("set_id", ""))))
        bar = QRectF(r.left() + S(10), r.top() + S(30), r.width() - S(130), S(6))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.08))
        p.drawRoundedRect(bar, S(3), S(3))
        p.setBrush(QColor("#3DDC84") if have >= goal else ui.accent)
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * min(1.0, have / goal), bar.height()), S(3), S(3))
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(9.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(bar.right() + S(6), bar.top() - S(6), S(40), S(18)), int(Qt.AlignmentFlag.AlignVCenter), f"{have}/{goal}")
        reward = coins_text(int(s.get("coins") or 0)) + (f" + {s.get('keys')} 🔑" if int(s.get("keys") or 0) else "")
        p.setPen(QColor(GOLD_TEXT if not claimed else TEXT_FAINT))
        p.setFont(font(10.5, QFont.Weight.Bold))
        p.drawText(r.adjusted(0, S(4), -S(10), -S(22)), int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight), reward)
        p.setFont(font(9.5, QFont.Weight.Bold))
        p.setPen(QColor("#3DDC84") if claimed else (QColor(GOLD_TEXT) if self.can else QColor(TEXT_FAINT)))
        p.drawText(r.adjusted(0, 0, -S(10), -S(6)), int(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight),
                   tr("Claimed") if claimed else (tr("Click to claim!") if self.can else tr("Not yet")))


def build_sets(page, lay) -> None:
    ctx = page.ctx
    lay.addWidget(Label(tr("Complete a set to get a big bonus, once. You must still own the badges when you claim."),
                        10.5, TEXT_DIM, wrap_w=page.W))
    data = getattr(ctx, "sets_data", None)

    def got(ok: bool, rows) -> None:
        if ok and isinstance(rows, list) and rows != getattr(ctx, "sets_data", None):
            ctx.sets_data = rows
            if ctx.window.current == "themes" and int(getattr(ctx, "shop_tab", 0) or 0) == 6:
                ctx.reload_page()
    ctx.online.ask("rb_sets", {}, got)
    if data is None:
        return lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
    for s in data:
        lay.addWidget(SetRow(page, s))


def claim_set(ctx, which: str) -> None:
    def done(ok: bool, data) -> None:
        if not ok:
            return ctx.toast(tr(str(data)), "warn")
        sfx.play("on")
        ctx.toast(tr("Set bonus: +{n} coins", n=coins_text(int(data.get("got_coins") or 0))))
        ctx.sets_data = None
        ctx.reload_page()
    ctx.econ.call("rb_set_claim", {"which": which}, done)


# ================================================================ daily login reward
class DayTile(QWidget):
    def __init__(self, k: int, reward: dict, state: str) -> None:
        super().__init__()
        self.k, self.reward, self.state = k, reward, state          # state: done / today / later
        self.setFixedSize(S(38), S(56))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        today = self.state == "today"
        col = QColor(GOLD_TEXT) if today else (QColor("#3DDC84") if self.state == "done" else alpha("#FFFFFF", 0.25))
        p.setPen(QPen(col, S(1.6) if today else 1))
        p.setBrush(alpha(col, 0.16 if today else 0.06))
        p.drawRoundedRect(r, S(8), S(8))
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(8.5, QFont.Weight.Bold))
        p.drawText(QRectF(r.left(), r.top() + S(3), r.width(), S(12)), int(Qt.AlignmentFlag.AlignCenter), tr("Day {n}", n=self.k + 1))
        rw = self.reward
        p.save()
        p.translate(r.center().x(), r.center().y() + S(1))
        p.scale(0.8, 0.8)
        if rw.get("case"):
            draw_icon(p, "gift", QColor(GOLD_TEXT))
        elif rw.get("keys"):
            draw_icon(p, "key", QColor(TEXT))
        else:
            paint_coin(p, QPointF(0, 0), S(8))
        p.restore()
        p.setPen(QColor(TEXT))
        p.setFont(font(8.5, QFont.Weight.Bold))
        text = str(rw.get("coins") or "") if not rw.get("keys") else f"{rw['keys']}"
        if rw.get("case"):
            text = "+" + tr("case")
        p.drawText(QRectF(r.left(), r.bottom() - S(15), r.width(), S(12)), int(Qt.AlignmentFlag.AlignCenter), text)
        if self.state == "done":
            p.setPen(QPen(QColor("#3DDC84"), S(2)))
            p.drawLine(QPointF(r.right() - S(12), r.top() + S(18)), QPointF(r.right() - S(8), r.top() + S(22)))
            p.drawLine(QPointF(r.right() - S(8), r.top() + S(22)), QPointF(r.right() - S(2), r.top() + S(14)))


class LoginWindow(FloatWindow):
    """Shown once a day: the streak and today's reward."""

    def __init__(self, ctx, state: dict) -> None:
        super().__init__(ctx, 330)
        lay = vbox(self, 10, (18, 16, 18, 18))
        streak = int(state.get("streak") or 0)
        lay.addWidget(Label(tr("Daily reward"), 16, bold=True))
        lay.addWidget(Label(tr("Come back every day: day 7 gives a free case. Miss a day and it starts again."),
                            11, TEXT_DIM, wrap_w=S(294)))
        rewards = list(state.get("rewards") or [])
        today = int(state.get("day") or 0)
        row = hbox(spacing=4)
        for k, rw in enumerate(rewards[:7]):
            row.addWidget(DayTile(k, rw, "done" if k < today else ("today" if k == today else "later")))
        lay.addLayout(row)
        if streak:
            lay.addWidget(Label(tr("Streak: {n} days in a row", n=streak), 11.5, GOLD_TEXT, bold=True))
        self.go = Button(tr("Claim"), "primary", 38)
        self.go.clicked.connect(self._claim)
        later = Button(tr("Later"), "ghost", 30)
        later.clicked.connect(self.close)
        lay.addWidget(self.go)
        lay.addWidget(later)
        self.centre()

    def _claim(self) -> None:
        self.go.setEnabled(False)

        def done(ok: bool, data) -> None:
            if not ok:
                self.go.setEnabled(True)
                return self.ctx.toast(tr(str(data)) if "countdown" not in str(data) else tr("Already claimed today"), "warn")
            sfx.play("on")
            rw = data.get("reward") or {}
            parts = []
            if rw.get("coins"):
                parts.append("+" + coins_text(int(rw["coins"])))
            if rw.get("keys"):
                parts.append(tr("+{n} key(s)", n=rw["keys"]))
            if rw.get("case"):
                parts.append(tr("+1 free case"))
            self.ctx.toast("  ".join(parts) + "  ·  " + tr("Day {n}", n=data.get("streak", 1)))
            self.ctx.econ.refresh()
            self.close()
        self.ctx.econ.call("rb_login_claim", {}, done)


def check_login_reward(ctx, force: bool = False) -> None:
    if not ctx.online.logged_in():
        return

    def got(ok: bool, state) -> None:
        if ok and isinstance(state, dict) and (force or not state.get("claimed")):
            if state.get("claimed"):
                return ctx.toast(tr("Already claimed today"), "warn")
            ctx._login_win = LoginWindow(ctx, state)
    ctx.online.ask("rb_login_state", {}, got)


# ================================================================ settings backups
BACKUP_SKIP = {"usage_s", "page", "seen_version", "scale_before_games", "autostart"}


def backup_data(ctx) -> dict:
    return {"rubenium_backup": 1, "at": int(time.time()),
            "settings": {k: v for k, v in ctx.cfg.d.items() if k not in BACKUP_SKIP}}


def backup_to_file(ctx):
    folder = DATA_DIR / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / time.strftime("rubenium-backup-%Y-%m-%d-%H%M.json")
    path.write_text(json.dumps(backup_data(ctx), indent=1), encoding="utf-8")
    old = sorted(folder.glob("rubenium-backup-*.json"))
    for f in old[:-10]:                                    # keep the last 10
        try:
            f.unlink()
        except OSError:
            pass
    return path


def backup_to_cloud(ctx, quiet: bool = False) -> None:
    if not ctx.online.logged_in():
        return None if quiet else ctx.toast(tr("Log in to back up online"), "warn")

    def done(ok: bool, data) -> None:
        if not quiet:
            ctx.toast(tr("Backed up online") if ok else tr(str(data)), "ok" if ok else "warn")
        if ok:
            ctx.cfg.d["backup_at"] = int(time.time())
    ctx.online.ask("rb_backup_save", {"data": backup_data(ctx)}, done)


def restore(ctx, data: dict) -> bool:
    if not isinstance(data, dict) or not isinstance(data.get("settings"), dict):
        return False
    from .core import _merge, DEFAULTS
    keep = {k: ctx.cfg.d[k] for k in BACKUP_SKIP if k in ctx.cfg.d}
    merged = _merge(DEFAULTS, dict(ctx.cfg.d, **data["settings"]))
    merged.update(keep)
    ctx.cfg.d = merged
    ctx.cfg.save()
    return True


def restore_from_cloud(ctx) -> None:
    def got(ok: bool, data) -> None:
        if not ok or not isinstance(data, dict) or not data.get("data"):
            return ctx.toast(tr("No online backup yet"), "warn")
        if restore(ctx, data["data"]):
            ctx.toast(tr("Settings restored: Rubenium restarts them now"))
            QTimer.singleShot(400, ctx.apply_restored)
    ctx.online.ask("rb_backup_load", {}, got)


def restore_from_file(ctx) -> None:
    from PyQt6.QtWidgets import QFileDialog
    path, _ = QFileDialog.getOpenFileName(None, tr("Choose a Rubenium backup"), str(DATA_DIR / "backups"), "Rubenium backup (*.json)")
    if not path:
        return
    try:
        data = json.loads(open(path, encoding="utf-8").read())
    except (OSError, ValueError):
        return ctx.toast(tr("This file is not a Rubenium backup"), "warn")
    if not restore(ctx, data):
        return ctx.toast(tr("This file is not a Rubenium backup"), "warn")
    ctx.toast(tr("Settings restored: Rubenium restarts them now"))
    QTimer.singleShot(400, ctx.apply_restored)


def backup_section(ctx, lay, width: int) -> None:
    """Settings tab: back up and restore."""
    lay.addWidget(Label(tr("BACKUP"), 10, TEXT_DIM, weight=QFont.Weight.Bold))
    lay.addWidget(Label(tr("Your coins, items and friends are always safe on the server. This saves your settings, "
                           "theme, crosshair and layout too, so a new PC gets everything back."), 10.5, TEXT_DIM, wrap_w=width))
    line = hbox(spacing=6)
    a = Button(tr("Back up now"), "primary", 30)

    def now() -> None:
        try:
            path = backup_to_file(ctx)
        except OSError:
            return ctx.toast(tr("Could not save the backup file"), "warn")
        backup_to_cloud(ctx, quiet=True)
        ctx.toast(tr("Saved online and in {path}", path=path.parent.name + "/" + path.name))
    a.clicked.connect(now)
    b = Button(tr("Restore…"), "ghost", 30)

    def pick() -> None:
        from PyQt6.QtWidgets import QMenu
        m = QMenu()
        m.addAction(tr("From the online backup"), lambda: restore_from_cloud(ctx))
        m.addAction(tr("From a file…"), lambda: restore_from_file(ctx))
        from PyQt6.QtGui import QCursor
        m.exec(QCursor.pos())
    b.clicked.connect(pick)
    line.addWidget(a, 1)
    line.addWidget(b, 1)
    lay.addLayout(line)
    when = int(ctx.cfg.d.get("backup_at") or 0)
    if when:
        lay.addWidget(Label(tr("Last online backup: {t}", t=time.strftime("%d/%m/%Y %H:%M", time.localtime(when))), 10, TEXT_FAINT))


# ================================================================ song history
HISTORY_FILE = "history.json"


def history_load() -> list:
    try:
        rows = json.loads((DATA_DIR / HISTORY_FILE).read_text(encoding="utf-8"))
        return [r for r in rows if isinstance(r, dict)][:50]
    except (OSError, ValueError, TypeError):
        return []


def history_add(title: str, artist: str, source: str = "") -> None:
    if not title:
        return
    rows = history_load()
    if rows and rows[0].get("title") == title and rows[0].get("artist") == artist:
        return
    rows.insert(0, {"title": title, "artist": artist, "source": source, "at": int(time.time())})
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = DATA_DIR / (HISTORY_FILE + ".tmp")
        tmp.write_text(json.dumps(rows[:50], ensure_ascii=False), encoding="utf-8")
        tmp.replace(DATA_DIR / HISTORY_FILE)
    except OSError:
        pass


class HistoryRow(QWidget):
    def __init__(self, row: dict, width: int) -> None:
        super().__init__()
        self.row = row
        self.setFixedSize(width, S(38))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr("Click to copy"))
        self.copied = 0.0

    def mouseReleaseEvent(self, e) -> None:
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(f"{self.row.get('title', '')} - {self.row.get('artist', '')}".strip(" -"))
        self.copied = time.monotonic()
        sfx.play("pick")
        self.update()
        QTimer.singleShot(1200, self.update)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.04))
        p.drawRoundedRect(r, S(8), S(8))
        fm = QFontMetrics(font(11, QFont.Weight.Bold))
        p.setPen(QColor(TEXT))
        p.setFont(font(11, QFont.Weight.Bold))
        p.drawText(QRectF(r.left() + S(10), r.top() + S(3), r.width() - S(80), S(16)), int(Qt.AlignmentFlag.AlignVCenter),
                   fm.elidedText(self.row.get("title", ""), Qt.TextElideMode.ElideRight, int(r.width() - S(80))))
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10))
        p.drawText(QRectF(r.left() + S(10), r.top() + S(19), r.width() - S(80), S(15)), int(Qt.AlignmentFlag.AlignVCenter),
                   self.row.get("artist", ""))
        p.setPen(QColor("#3DDC84") if time.monotonic() - self.copied < 1.1 else QColor(TEXT_FAINT))
        p.setFont(font(9.5))
        text = tr("Copied") if time.monotonic() - self.copied < 1.1 else time.strftime("%H:%M", time.localtime(int(self.row.get("at") or 0)))
        p.drawText(r.adjusted(0, 0, -S(10), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), text)


class HistoryWindow(FloatWindow):
    def __init__(self, ctx) -> None:
        super().__init__(ctx, 330)
        from .widgets import ScrollArea
        lay = vbox(self, 8, (16, 14, 16, 16))
        top = hbox(spacing=6)
        top.addWidget(Label(tr("Song history"), 15, bold=True), 1)
        close = IconButton("close", 26, tip=tr("Close"))
        close.clicked.connect(self.close)
        top.addWidget(close)
        lay.addLayout(top)
        rows = history_load()
        if not rows:
            lay.addWidget(Label(tr("Songs you play show up here."), 11, TEXT_DIM))
        else:
            lay.addWidget(Label(tr("The last {n} songs. Click one to copy its name.", n=len(rows)), 10.5, TEXT_DIM, wrap_w=S(298)))
            inner = QWidget()
            col = vbox(inner, 4)
            for r in rows:
                col.addWidget(HistoryRow(r, S(290)))
            h = len(rows) * (S(38) + S(4))
            area = ScrollArea(inner, h)
            area.setFixedSize(S(298), min(S(380), h))
            lay.addWidget(area)
        self.centre()
