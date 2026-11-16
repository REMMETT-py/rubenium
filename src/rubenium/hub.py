"""2.4 screens: messages, leaderboards, trade history, collection sets, the daily login reward,
settings backups and the song history."""
import datetime
import json
import time

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt, pyqtSignal
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

    wants_keys = False

    def centre(self) -> None:
        from .widgets import present
        from .window import work_area
        self.adjustSize()
        if present(self, self.ctx, keys=self.wants_keys):
            return
        area = work_area(self.ctx.window.card_global().center())
        self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)
        self.show()
        self.raise_()
        self.activateWindow()

    def close(self) -> bool:
        from .widgets import close_embedded
        return close_embedded(self) or super().close()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.close()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        inside = getattr(self, "_embedded", False)
        p.setPen(QPen(alpha(ui.accent, 0.25 if inside else 0.45), 1.2))
        p.setBrush(alpha("#FFFFFF", 0.03) if inside else QColor(12, 15, 16, 252))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), S(16), S(16))


def ago(at) -> str:
    """'5 min ago' from a server time."""
    from .friends import ago_text
    try:
        return ago_text(at)
    except Exception:  # noqa: BLE001
        return ""


# ================================================================ big, clear section buttons (shop, admin)
class NavTiles(QWidget):
    """Sections as tiles with an icon and a name, 4 per row. The one you are in is lit."""
    changed = pyqtSignal(int)

    def __init__(self, items: list, index: int = 0, per_row: int = 4, badges: dict = None, select: bool = True) -> None:
        super().__init__()
        self.items, self.index, self.per = items, index, per_row          # items: [(label, icon)]
        self.select = select                                              # False: plain action buttons
        self.badges = badges or {}                                        # index -> small number (new things)
        rows = (len(items) + per_row - 1) // per_row
        self.th = S(50)
        self.setFixedHeight(rows * self.th + (rows - 1) * S(6))
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hover = -1

    def _tile(self, i: int) -> QRectF:
        gap = S(6)
        w = (self.width() - gap * (self.per - 1)) / self.per
        r, c = divmod(i, self.per)
        return QRectF(c * (w + gap), r * (self.th + gap), w, self.th)

    def _at(self, pos) -> int:
        return next((i for i in range(len(self.items)) if self._tile(i).contains(pos)), -1)

    def mouseMoveEvent(self, e) -> None:
        h = self._at(e.position())
        if h != self.hover:
            self.hover = h
            self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = -1
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        i = self._at(e.position())
        if i >= 0 and (i != self.index or not self.select):
            sfx.play("pick")
            if self.select:
                self.index = i
            self.update()
            self.changed.emit(i)

    def set_index(self, i: int) -> None:
        self.index = i
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i, (label, icon) in enumerate(self.items):
            r = self._tile(i).adjusted(0.5, 0.5, -0.5, -0.5)
            on, hov = i == self.index, i == self.hover
            if on:
                g = QLinearGradient(r.topLeft(), r.bottomLeft())
                g.setColorAt(0, alpha(ui.accent, 0.30))
                g.setColorAt(1, alpha(ui.accent, 0.12))
                p.setPen(QPen(alpha(ui.accent, 0.85), S(1.4)))
                p.setBrush(g)
            else:
                p.setPen(QPen(alpha("#FFFFFF", 0.10 if hov else 0.06), 1))
                p.setBrush(alpha("#FFFFFF", 0.07 if hov else 0.035))
            p.drawRoundedRect(r, S(10), S(10))
            p.save()
            p.translate(r.center().x(), r.top() + S(17))
            p.scale(0.9, 0.9)
            draw_icon(p, icon, QColor(TEXT) if on or hov else QColor(TEXT_DIM))
            p.restore()
            p.setPen(QColor(TEXT) if on else QColor(TEXT_DIM))
            p.setFont(font(10, QFont.Weight.Bold if on else QFont.Weight.DemiBold))
            text = QFontMetrics(p.font()).elidedText(label, Qt.TextElideMode.ElideRight, int(r.width() - S(6)))
            p.drawText(QRectF(r.left(), r.bottom() - S(20), r.width(), S(16)), int(Qt.AlignmentFlag.AlignCenter), text)
            n = int(self.badges.get(i) or 0)
            if n:
                b = QRectF(r.right() - S(20), r.top() + S(4), S(16), S(14))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#FF5C6C"))
                p.drawRoundedRect(b, S(7), S(7))
                p.setPen(QColor("#FFFFFF"))
                p.setFont(font(8.5, QFont.Weight.ExtraBold))
                p.drawText(b, int(Qt.AlignmentFlag.AlignCenter), str(min(n, 9)))


# ================================================================ before the server has the 2.4 update
class WaitCard(QWidget):
    """Shown instead of a new part while the server has not had its update yet: no error, just 'very soon'."""

    def __init__(self, width: int) -> None:
        super().__init__()
        self.setFixedSize(width, S(150))
        self._t = QTimer(self)
        self._t.setInterval(40)
        self._t.timeout.connect(self.update)

    def showEvent(self, _e) -> None:
        self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()

    def paintEvent(self, _e) -> None:
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha(ui.accent, 0.35), 1.2))
        p.setBrush(alpha("#FFFFFF", 0.035))
        p.drawRoundedRect(r, S(14), S(14))
        c = QPointF(r.center().x(), r.top() + S(42))
        t = time.monotonic()
        for k in range(8):                                   # a soft turning ring of dots
            a = t * 3 + k * math.tau / 8
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(ui.accent, 0.15 + 0.85 * ((k / 8 + t * 0.48) % 1.0)))
            p.drawEllipse(QPointF(c.x() + math.cos(a) * S(14), c.y() + math.sin(a) * S(14)), S(2.6), S(2.6))
        p.setPen(QColor(TEXT))
        p.setFont(font(14, QFont.Weight.Bold))
        p.drawText(QRectF(r.left(), r.top() + S(68), r.width(), S(22)), int(Qt.AlignmentFlag.AlignCenter), tr("Coming very soon"))
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(r.left() + S(16), r.top() + S(92), r.width() - S(32), S(50)),
                   int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap),
                   tr("This part is new. It opens by itself as soon as the Rubenium server gets its update."))


def server_wait(ctx, lay, width: int) -> bool:
    """True (and a 'coming very soon' card) when the server does not have this part yet."""
    if not getattr(ctx.econ, "server_old", False):
        return False
    lay.addWidget(WaitCard(width))
    return True


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
    """A chat with one friend, inside the menu (the menu takes the keyboard only while it is open)."""
    wants_keys = True

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
        self.bubbles.setFixedHeight(S(240))
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
        self.focus_me = self.edit.setFocus
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

    def on_closed(self) -> None:
        self._poll.stop()
        self.ctx.threads_data = None

    def closeEvent(self, e) -> None:
        self.on_closed()
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
    if server_wait(ctx, lay, page.W):
        return
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
        name = str(row.get("name", ""))
        p.drawText(QRectF(r.left() + S(34), r.top(), r.width() - S(140), r.height()), int(Qt.AlignmentFlag.AlignVCenter), name)
        from .collection import ECON
        tag = ECON.look_of(name).get("tag") if ECON is not None else ""
        if tag:
            from .cosmetics import paint_tag
            paint_tag(p, r.left() + S(40) + p.fontMetrics().horizontalAdvance(name), r.center().y(), tag, 0.0, 8)
        v = int(row.get("value") or 0)
        text = coins_text(v) if self.kind in ("coins", "worth") else (f"{v}%" if self.kind == "tap" else
                                                                       (tr("{n} days", n=v) if self.kind == "streak" else
                                                                        (f"{v} h" if self.kind == "hours" else str(v))))
        p.setPen(QColor(GOLD_TEXT if self.kind in ("coins", "worth") else TEXT))
        p.drawText(r.adjusted(0, 0, -S(10), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), text)


def build_leaders(page, lay) -> None:
    ctx = page.ctx
    if server_wait(ctx, lay, page.W):
        return
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
    if server_wait(ctx, lay, page.W):
        return
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
    if server_wait(ctx, lay, page.W):
        return
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
        head = hbox(spacing=10)
        nxt = streak if state.get("claimed") else streak + 1
        self.flame = StreakFlame(nxt, 70)
        head.addWidget(self.flame)
        col = vbox(spacing=2)
        col.addWidget(Label(tr("Daily reward"), 16, bold=True))
        col.addWidget(Label(tr("Your flame grows a little every day in a row."), 10.5, TEXT_DIM, wrap_w=S(210)))
        head.addLayout(col, 1)
        lay.addLayout(head)
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
            self.ctx.econ.streak, self.ctx.econ.streak_day = int(data.get("streak") or 1), datetime.date.today().isoformat()
            self.ctx.econ.refresh()
            self.flame.day = int(data.get("streak") or 1)
            self.go.set_text(tr("Done for today"))
            QTimer.singleShot(1400, self.close)
        self.ctx.econ.call("rb_login_claim", {}, done)


def check_login_reward(ctx, force: bool = False) -> None:
    if not ctx.online.logged_in() or getattr(ctx.econ, "server_old", False):
        return

    def got(ok: bool, state) -> None:
        if ok and isinstance(state, dict) and (force or not state.get("claimed")):
            if state.get("claimed"):
                return ctx.toast(tr("Already claimed today"), "warn")
            if not ctx.window.expanded:                  # never over a game: a small note, the reward waits
                ctx.notifier.push("ready", tr("DAILY REWARD"), tr("Your daily reward is ready: open Rubenium to claim it"))
                ctx.login_pending = True
                return
            ctx.login_pending = False
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


# ================================================================ profile picture editor
FILTERS = [("normal", "Normal"), ("vivid", "Vivid"), ("warm", "Warm"), ("cool", "Cool"), ("mono", "Black & white"),
           ("dream", "Dream")]
RINGS = [("none", "No ring"), ("accent", "My colour"), ("rainbow", "Rainbow")]


def filtered(img, kind: str):
    """A copy of the picture with a colour filter (small, so it is fast)."""
    from PyQt6.QtGui import QImage
    if kind == "normal":
        return img
    out = img.convertToFormat(QImage.Format.Format_ARGB32)
    w, h = out.width(), out.height()
    for y in range(h):
        for x in range(w):
            c = out.pixelColor(x, y)
            r, g, b = c.red(), c.green(), c.blue()
            if kind == "mono":
                v = int(0.3 * r + 0.59 * g + 0.11 * b)
                r = g = b = v
            elif kind == "warm":
                r, b = min(255, int(r * 1.12 + 10)), int(b * 0.85)
            elif kind == "cool":
                r, b = int(r * 0.85), min(255, int(b * 1.15 + 10))
            elif kind == "vivid":
                m = (r + g + b) / 3
                r, g, b = (max(0, min(255, int(m + (v - m) * 1.45))) for v in (r, g, b))
            elif kind == "dream":
                r, g, b = (min(255, int(v * 0.8 + 60)) for v in (r, g, b))
                b = min(255, b + 20)
            out.setPixelColor(x, y, QColor(r, g, b, c.alpha()))
    return out


class Cropper(QWidget):
    """The picture inside a round window: drag it to move, scroll (or the slider) to zoom."""

    def __init__(self, img, size: int) -> None:
        super().__init__()
        self.src = img
        self.view = img
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.zoom = 1.0
        self.angle = 0
        self.mirror = False
        self.off = QPointF(0, 0)
        self.ring = "accent"
        self._drag = None
        self.changed = None

    def base_scale(self) -> float:
        w, h = (self.src.height(), self.src.width()) if self.angle % 180 else (self.src.width(), self.src.height())
        return self.width() / max(1, min(w, h))

    def mousePressEvent(self, e) -> None:
        self._drag = (e.position(), QPointF(self.off))
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e) -> None:
        if self._drag:
            start, off = self._drag
            self.off = off + (e.position() - start)
            self._clamp()
            self.update()
            if self.changed:
                self.changed()

    def mouseReleaseEvent(self, _e) -> None:
        self._drag = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def wheelEvent(self, e) -> None:
        self.set_zoom(self.zoom * (1.1 if e.angleDelta().y() > 0 else 1 / 1.1))
        e.accept()

    def set_zoom(self, z: float) -> None:
        self.zoom = max(1.0, min(5.0, z))
        self._clamp()
        self.update()
        if self.changed:
            self.changed()

    def _clamp(self) -> None:
        w, h = (self.src.height(), self.src.width()) if self.angle % 180 else (self.src.width(), self.src.height())
        sc = self.base_scale() * self.zoom
        mx, my = max(0.0, (w * sc - self.width()) / 2), max(0.0, (h * sc - self.height()) / 2)
        self.off = QPointF(max(-mx, min(mx, self.off.x())), max(-my, min(my, self.off.y())))

    def render_square(self, side: int):
        """What is inside the circle, as a square picture `side` pixels wide."""
        from PyQt6.QtGui import QImage
        out = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
        out.fill(QColor("#000000"))
        p = QPainter(out)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        k = side / self.width()
        self._draw_image(p, k)
        p.end()
        return out

    def _draw_image(self, p: QPainter, k: float = 1.0) -> None:
        sc = self.base_scale() * self.zoom * k
        p.save()
        p.translate(self.width() * k / 2 + self.off.x() * k, self.height() * k / 2 + self.off.y() * k)
        p.rotate(self.angle)
        p.scale(-sc if self.mirror else sc, sc)
        p.drawImage(QPointF(-self.view.width() / 2, -self.view.height() / 2), self.view)
        p.restore()

    def paintEvent(self, _e) -> None:
        from PyQt6.QtGui import QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#07090B"))
        self._draw_image(p)
        r = QRectF(self.rect()).adjusted(S(6), S(6), -S(6), -S(6))
        outside = QPainterPath()
        outside.addRect(QRectF(self.rect()))
        hole = QPainterPath()
        hole.addEllipse(r)
        p.fillPath(outside.subtracted(hole), QColor(6, 8, 10, 175))
        p.setPen(QPen(alpha("#FFFFFF", 0.6), S(1.2), Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(r)


class AvatarEditor(FloatWindow):
    """Choose exactly how your picture looks: move, zoom, turn, mirror, a filter, and see it at every size."""

    def __init__(self, ctx, img, on_done) -> None:
        super().__init__(ctx, 340)
        from .widgets import Slider
        self.on_done = on_done
        side = min(img.width(), img.height())
        big = img if side <= 900 else img.scaled(900 * img.width() // side, 900 * img.height() // side,
                                                 Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.small = big.scaled(min(260, big.width()), min(260, big.height()), Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
        lay = vbox(self, 8, (16, 14, 16, 16))
        top = hbox(spacing=6)
        top.addWidget(Label(tr("Your picture"), 15, bold=True), 1)
        close = IconButton("close", 26, tip=tr("Close"))
        close.clicked.connect(self.close)
        top.addWidget(close)
        lay.addLayout(top)
        lay.addWidget(Label(tr("Drag to move it, scroll to zoom."), 10.5, TEXT_DIM))
        self.crop = Cropper(big, S(220))
        self.crop.changed = self._previews
        row = hbox(spacing=10)
        row.addWidget(self.crop)
        self.prev = AvatarPreviews(self)
        row.addWidget(self.prev)
        lay.addLayout(row)
        zoom = Slider(100, 500, 100, 5)
        zoom.changed.connect(lambda v: self.crop.set_zoom(v / 100))
        line = hbox(spacing=6)
        line.addWidget(Label(tr("Zoom"), 11, TEXT_DIM))
        line.addWidget(zoom, 1)
        lay.addLayout(line)
        tools = hbox(spacing=6)
        turn = Button(tr("Turn"), "ghost", 28, icon="refresh")
        turn.clicked.connect(self._turn)
        flip = Button(tr("Mirror"), "ghost", 28)
        flip.clicked.connect(self._flip)
        tools.addWidget(turn, 1)
        tools.addWidget(flip, 1)
        lay.addLayout(tools)
        self.filt = Segmented([tr(n) for _k, n in FILTERS], 0)
        self.filt.changed.connect(self._filter)
        lay.addWidget(Label(tr("Filter"), 11, TEXT_DIM))
        lay.addWidget(self.filt)
        go = Button(tr("Use this picture"), "primary", 36)
        go.clicked.connect(self._use)
        lay.addWidget(go)
        lay.addWidget(Label(tr("Everyone can see it. Keep it friendly."), 10, TEXT_FAINT))
        self.centre()

    def _turn(self) -> None:
        self.crop.angle = (self.crop.angle + 90) % 360
        self.crop._clamp()
        self.crop.update()
        self._previews()

    def _flip(self) -> None:
        self.crop.mirror = not self.crop.mirror
        self.crop.update()
        self._previews()

    def _filter(self, i: int) -> None:
        kind = FILTERS[i][0]
        src = self.crop.src
        if kind == "normal":
            self.crop.view = src
        else:                                                  # filter a smaller copy, then show it at full size
            small = src.scaled(min(src.width(), 360), min(src.height(), 360), Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            self.crop.view = filtered(small, kind).scaled(src.width(), src.height(), Qt.AspectRatioMode.IgnoreAspectRatio,
                                                          Qt.TransformationMode.SmoothTransformation)
        self.crop.update()
        self._previews()

    def _previews(self) -> None:
        self.prev.update()

    def _use(self) -> None:
        sfx.play("pick")
        out = self.crop.render_square(192)
        self.close()
        self.on_done(out)


class AvatarPreviews(QWidget):
    """How the picture will look in the profile, the friends list and next to messages."""

    def __init__(self, editor) -> None:
        super().__init__()
        self.ed = editor
        self.setFixedSize(S(70), S(220))

    def paintEvent(self, _e) -> None:
        from PyQt6.QtGui import QPainterPath, QPixmap
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        pm = QPixmap.fromImage(self.ed.crop.render_square(128))
        y = S(4)
        for d in (S(56), S(36), S(24)):
            r = QRectF((self.width() - d) / 2, y, d, d)
            clip = QPainterPath()
            clip.addEllipse(r)
            p.save()
            p.setClipPath(clip)
            p.drawPixmap(r.toRect(), pm)
            p.restore()
            p.setPen(QPen(alpha(ui.accent, 0.8), S(1.5)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(r)
            y += d + S(18)
        p.setPen(QColor(TEXT_FAINT))
        p.setFont(font(9))
        p.drawText(QRectF(0, self.height() - S(18), self.width(), S(14)), int(Qt.AlignmentFlag.AlignCenter), tr("Preview"))


# ================================================================ the login streak flame
FLAME_STAGES = [  # (from day, outer, middle, core) — it gets hotter, bigger and fancier every day
    (1, "#FF7A1A", "#FFB238", "#FFF1B0"), (3, "#FF4D1A", "#FF9A2E", "#FFE38A"), (5, "#FF2E4D", "#FF7A3D", "#FFD36B"),
    (7, "#E8227A", "#FF5C8A", "#FFD0E0"), (10, "#9B3DFF", "#D16BFF", "#FFE0FF"), (14, "#2E7BFF", "#4FC3FF", "#E0F7FF"),
    (21, "#00C2A8", "#2EE6D6", "#E8FFFB"), (30, "#FFC94D", "#FFF1A8", "#FFFFFF")]


def flame_colours(day: int) -> tuple:
    st = FLAME_STAGES[0]
    for s in FLAME_STAGES:
        if day >= s[0]:
            st = s
    return QColor(st[1]), QColor(st[2]), QColor(st[3])


def paint_flame(p: QPainter, c: QPointF, size: float, day: int, t: float, sparks: bool = True) -> None:
    """A living flame. Day 1 is a small orange flame; each day adds a little: height, tongues, colours, glow,
    embers, a ring and at last a crown of light (day 30: a white-gold flame)."""
    import math
    from PyQt6.QtGui import QPainterPath, QRadialGradient
    day = max(0, day)
    if day == 0:
        p.save()
        p.setPen(QPen(alpha("#FFFFFF", 0.25), S(1.2), Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath()
        path.moveTo(c.x(), c.y() - size * 0.55)
        path.cubicTo(c.x() + size * 0.45, c.y() - size * 0.1, c.x() + size * 0.35, c.y() + size * 0.45, c.x(), c.y() + size * 0.45)
        path.cubicTo(c.x() - size * 0.35, c.y() + size * 0.45, c.x() - size * 0.45, c.y() - size * 0.1, c.x(), c.y() - size * 0.55)
        p.drawPath(path)
        p.restore()
        return
    outer, mid, core = flame_colours(day)
    grow = min(1.0, 0.55 + day * 0.03)                   # taller every day, full size at day 15
    h = size * grow
    p.save()
    glow = QRadialGradient(QPointF(c.x(), c.y() + h * 0.1), size * (0.6 + min(0.5, day * 0.03)))
    glow.setColorAt(0, alpha(outer, min(0.55, 0.18 + day * 0.02)))
    glow.setColorAt(1, alpha(outer, 0.0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(glow)
    p.drawEllipse(QPointF(c.x(), c.y() + h * 0.1), size * 1.1, size * 1.1)
    if day >= 12:                                         # a turning ring of light
        p.setPen(QPen(alpha(mid, 0.35), S(1.2)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        ring = size * 0.62
        p.drawArc(QRectF(c.x() - ring, c.y() + h * 0.28 - ring * 0.32, ring * 2, ring * 0.64), int(t * 400) % 5760, 3600)
        p.setPen(Qt.PenStyle.NoPen)

    def tongue(scale: float, colour: QColor, wob: float, phase: float, lean: float = 0.0) -> None:
        w = h * 0.42 * scale
        top = c.y() + h * 0.5 - h * scale
        sway = math.sin(t * (5 + phase) + phase) * w * wob
        tip = QPointF(c.x() + sway + lean * w, top)
        base = c.y() + h * 0.5
        path = QPainterPath()
        path.moveTo(tip)
        path.cubicTo(c.x() + w * 0.9 + sway * 0.5, top + h * scale * 0.45, c.x() + w, base - w * 0.4, c.x(), base)
        path.cubicTo(c.x() - w, base - w * 0.4, c.x() - w * 0.9 + sway * 0.5, top + h * scale * 0.45, tip.x(), tip.y())
        g = QLinearGradient(QPointF(0, top), QPointF(0, base))
        g.setColorAt(0, alpha(colour, 0.0 if scale > 0.6 else 0.6))
        g.setColorAt(0.35, colour)
        g.setColorAt(1, mix(colour, QColor("#FFFFFF"), 0.15))
        p.setBrush(g)
        p.drawPath(path)

    tongues = min(4, 1 + day // 4)                        # side tongues appear as the streak grows
    for k in range(1, tongues):
        side = -1 if k % 2 else 1
        tongue(0.55 + 0.05 * k, alpha(outer, 0.75), 0.25, k * 1.7, side * (0.6 + 0.15 * k))
    tongue(1.0, outer, 0.18, 0.0)
    tongue(0.72, mid, 0.22, 1.3)
    tongue(0.42, core, 0.28, 2.6)
    if day >= 7:                                          # a bright heart
        heart = QRadialGradient(QPointF(c.x(), c.y() + h * 0.32), h * 0.16)
        heart.setColorAt(0, QColor("#FFFFFF"))
        heart.setColorAt(1, alpha(core, 0.0))
        p.setBrush(heart)
        p.drawEllipse(QPointF(c.x(), c.y() + h * 0.32), h * 0.16, h * 0.16)
    if sparks:                                            # embers: more and faster every day
        n = min(16, 1 + day)
        for k in range(n):
            life = (t * (0.5 + (k % 5) * 0.12) + k * 0.37) % 1.0
            x = c.x() + math.sin(k * 12.9 + t * 2) * size * 0.32 * (0.4 + life)
            y = c.y() + h * 0.4 - life * size * (0.9 + min(0.6, day * 0.02))
            col = mid if k % 3 else core
            if day >= 20 and k % 4 == 0:
                col = QColor.fromHsvF((t * 0.2 + k * 0.13) % 1.0, 0.55, 1.0)
            p.setBrush(alpha(col, 1 - life))
            p.drawEllipse(QPointF(x, y), S(1.6) * (1 - life * 0.5), S(1.6) * (1 - life * 0.5))
    if day >= 30:                                         # the crown: a few rays over the flame
        p.setPen(QPen(alpha("#FFF6C8", 0.55), S(1.3)))
        for k in range(5):
            a = -math.pi / 2 + (k - 2) * 0.35 + math.sin(t * 2 + k) * 0.05
            r0, r1 = size * 0.7, size * (0.88 + 0.06 * math.sin(t * 4 + k))
            p.drawLine(QPointF(c.x() + math.cos(a) * r0, c.y() + math.sin(a) * r0),
                       QPointF(c.x() + math.cos(a) * r1, c.y() + math.sin(a) * r1))
    p.restore()


class StreakFlame(QWidget):
    """The flame and the number of days, alive (it moves only while it is on screen)."""

    def __init__(self, day: int, size: int = 64, label: bool = True) -> None:
        super().__init__()
        self.day, self.label = day, label
        self.setFixedSize(S(size), S(size) + (S(18) if label else 0))
        self._t = QTimer(self)
        self._t.setInterval(33)
        self._t.timeout.connect(self.update)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def showEvent(self, _e) -> None:
        self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = self.width()
        paint_flame(p, QPointF(side / 2, side * 0.52), side * 0.46, self.day, time.monotonic())
        if self.label:
            _o, mid, _c = flame_colours(max(1, self.day))
            p.setPen(mid if self.day else QColor(TEXT_DIM))
            p.setFont(font(11, QFont.Weight.ExtraBold))
            p.drawText(QRectF(0, side - S(2), side, S(18)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("{n} days", n=self.day) if self.day != 1 else tr("1 day"))


class StreakRow(QWidget):
    """Games lobby: the flame, the streak and when the next reward is ready."""

    def __init__(self, page) -> None:
        super().__init__()
        self.page, self.ctx = page, page.ctx
        self.setFixedHeight(S(44))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._t = QTimer(self)
        self._t.setInterval(40)
        self._t.timeout.connect(self.update)

    def showEvent(self, _e) -> None:
        self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()

    def _state(self):
        ec = self.ctx.econ
        today = datetime.date.today().isoformat()
        day = str(ec.streak_day or "")
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        alive = day in (today, yesterday)
        return (ec.streak if alive else 0), day == today

    def mouseReleaseEvent(self, e) -> None:
        if self.rect().contains(e.position().toPoint()):
            sfx.play("pick")
            check_login_reward(self.ctx, force=True)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        streak, claimed = self._state()
        outer, mid, _core = flame_colours(max(1, streak))
        g = QLinearGradient(r.topLeft(), r.topRight())
        g.setColorAt(0, mix(outer, QColor("#14181D"), 0.78))
        g.setColorAt(1, QColor("#14181D"))
        p.setPen(QPen(alpha(mid, 0.45 if not claimed else 0.15), 1.2))
        p.setBrush(g)
        p.drawRoundedRect(r, S(10), S(10))
        paint_flame(p, QPointF(r.left() + S(22), r.center().y()), S(17), streak, time.monotonic(), sparks=streak > 0)
        p.setPen(QColor(TEXT))
        p.setFont(font(12, QFont.Weight.Bold))
        p.drawText(QRectF(r.left() + S(44), r.top(), r.width(), r.height()), int(Qt.AlignmentFlag.AlignVCenter),
                   tr("Daily reward") + (f"  ·  {tr('{n} days', n=streak)}" if streak > 1 else ""))
        p.setPen(QColor(TEXT_DIM if claimed else mid.name()))
        p.setFont(font(11, QFont.Weight.DemiBold))
        p.drawText(r.adjusted(0, 0, -S(12), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                   tr("Done for today") if claimed else tr("Claim!"))



class AmountWindow(FloatWindow):
    """Give or take coins or keys: quick buttons for the usual amounts, or type any number."""
    wants_keys = True

    def __init__(self, ctx, title: str, presets: list, on_amount) -> None:
        super().__init__(ctx, 320)
        from PyQt6.QtWidgets import QLineEdit
        self.on_amount = on_amount
        lay = vbox(self, 8, (16, 14, 16, 16))
        top = hbox(spacing=6)
        top.addWidget(Label(title, 15, bold=True), 1)
        close = IconButton("close", 26, tip=tr("Close"))
        close.clicked.connect(self.close)
        top.addWidget(close)
        lay.addLayout(top)
        for row in (presets[:4], presets[4:8]):
            if not row:
                continue
            line = hbox(spacing=6)
            for n in row:
                b = Button(("+" if n > 0 else "−") + coins_text(abs(n)), "primary" if n > 0 else "danger", 30)
                b.clicked.connect(lambda _c=False, n=n: self._go(n))
                line.addWidget(b, 1)
            lay.addLayout(line)
        lay.addWidget(Label(tr("Or type an amount (minus to take):"), 10.5, TEXT_DIM))
        line = hbox(spacing=6)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("500 / -500")
        self.edit.setFixedHeight(S(32))
        self.edit.setStyleSheet(
            f"QLineEdit {{ background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10);"
            f" border-radius: {S(9)}px; padding: 0 {S(10)}px; color: {TEXT}; font-size: {S(13)}px; }}")
        self.edit.returnPressed.connect(self._typed)
        ok = Button(tr("Apply"), "primary", 32)
        ok.clicked.connect(self._typed)
        line.addWidget(self.edit, 1)
        line.addWidget(ok)
        lay.addLayout(line)
        self.centre()

    def _typed(self) -> None:
        text = self.edit.text().replace(" ", "").replace("−", "-")
        try:
            n = int(text)
        except ValueError:
            return self.edit.setFocus()
        if n:
            self._go(n)

    def _go(self, n: int) -> None:
        self.close()
        self.on_amount(n)



# ================================================================ daily deals
class DealCard(QWidget):
    """One deal: the item, its old and new price and how much is saved."""

    def __init__(self, page, d: dict, width: int) -> None:
        super().__init__()
        self.page, self.ctx, self.d = page, page.ctx, d
        self.setFixedSize(width, S(150))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.owned = not d["item"].startswith("badge:") and self.ctx.econ.owns(d["item"])
        self._t = QTimer(self)
        self._t.setInterval(50)
        self._t.timeout.connect(self.update)

    def showEvent(self, _e) -> None:
        self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()

    def mouseReleaseEvent(self, e) -> None:
        if not self.rect().contains(e.position().toPoint()):
            return
        ctx, ec, d = self.ctx, self.ctx.econ, self.d
        if self.owned:
            return ctx.toast(tr("You already have it"), "warn")
        if d["now"] > ec.coins:
            return ctx.toast(tr("Not enough coins: {n} more needed", n=coins_text(d["now"] - ec.coins)), "warn")
        from .cosmetics import item_name

        def bought(ok: bool, data) -> None:
            if not ok:
                return ctx.toast(tr(str(data)), "warn")
            sfx.play("on")
            ctx.toast(tr("Bought: {what}", what=item_name(d["item"])))
            ctx.reload_page()
        ctx.window.confirm(tr("Buy {what} for {n} coins?", what=item_name(d["item"]), n=coins_text(d["now"])),
                           lambda: ec.buy(d["item"], bought), yes=tr("Buy"))

    def paintEvent(self, _e) -> None:
        from .cosmetics import item_name, paint_cosmetic
        from .econ import RARITY_COLOURS
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        col = QColor(RARITY_COLOURS.get(self.ctx.econ.rarity(self.d["item"]), "#9AA4AD"))
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, mix(col, QColor("#0B0E10"), 0.75))
        g.setColorAt(1, QColor("#0B0E10"))
        p.setPen(QPen(alpha(col, 0.5), S(1.2)))
        p.setBrush(g)
        p.drawRoundedRect(r, S(12), S(12))
        paint_cosmetic(p, self.d["item"], QRectF(r.center().x() - S(26), r.top() + S(12), S(52), S(52)), time.monotonic())
        tag = QRectF(r.right() - S(46), r.top() + S(8), S(38), S(18))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FF5C6C"))
        p.drawRoundedRect(tag, S(9), S(9))
        p.setPen(QColor("#FFFFFF"))
        p.setFont(font(9.5, QFont.Weight.ExtraBold))
        p.drawText(tag, int(Qt.AlignmentFlag.AlignCenter), f"-{self.d['pct']}%")
        name = QFontMetrics(font(10.5, QFont.Weight.Bold)).elidedText(item_name(self.d["item"]), Qt.TextElideMode.ElideRight,
                                                                       int(r.width() - S(12)))
        p.setPen(QColor(TEXT))
        p.setFont(font(10.5, QFont.Weight.Bold))
        p.drawText(QRectF(r.left() + S(6), r.top() + S(70), r.width() - S(12), S(18)), int(Qt.AlignmentFlag.AlignCenter), name)
        p.setPen(QColor(TEXT_FAINT))
        p.setFont(font(10))
        old = coins_text(int(self.d["price"]))
        rect = QRectF(r.left(), r.top() + S(92), r.width(), S(16))
        p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), old)
        w = QFontMetrics(font(10)).horizontalAdvance(old)
        p.setPen(QPen(alpha(TEXT_FAINT, 0.9), 1))
        p.drawLine(QPointF(rect.center().x() - w / 2 - 2, rect.center().y()), QPointF(rect.center().x() + w / 2 + 2, rect.center().y()))
        p.setPen(QColor(GOLD_TEXT if not self.owned else TEXT_DIM))
        p.setFont(font(14, QFont.Weight.ExtraBold))
        p.drawText(QRectF(r.left(), r.top() + S(110), r.width(), S(26)), int(Qt.AlignmentFlag.AlignCenter),
                   tr("Owned") if self.owned else coins_text(int(self.d["now"])))


def build_deals(page, lay) -> None:
    ctx = page.ctx
    if server_wait(ctx, lay, page.W):
        return
    data = getattr(ctx, "deals_data", None)
    if data is None or time.monotonic() - data[0] > 60:
        def got(ok: bool, ans) -> None:
            if ok and isinstance(ans, dict):
                ctx.deals_data = (time.monotonic(), ans)
                if ctx.window.current == "themes" and int(getattr(ctx, "shop_tab", 0) or 0) == 7:
                    ctx.reload_page()
        ctx.online.ask("rb_deals", {}, got)
    if data is None:
        return lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
    ans = data[1]
    left = max(0, int(ans.get("ends_in") or 0) - int(time.monotonic() - data[0]))
    from .shop import clock_text
    lay.addWidget(Label(tr("New deals in {t}", t=clock_text(left)), 11, GOLD_TEXT, bold=True))
    from PyQt6.QtWidgets import QGridLayout
    holder = QWidget()
    grid = QGridLayout(holder)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(S(6))
    w = (page.W - S(6)) // 2
    for k, d in enumerate(ans.get("deals") or []):
        grid.addWidget(DealCard(page, d, w), k // 2, k % 2)
    lay.addWidget(holder)
