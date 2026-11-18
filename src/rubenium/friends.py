"""Social tab: your own stats and picture at the top, every Rubenium player (add them in one click), friends
online, profiles with badges and history, trade requests and the trade screen. Everything refreshes by itself."""
import base64
import time

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

from .bazaar import AskDialog, build_trade
from .hub import NavTiles, build_leaders, build_messages, build_trade_history, open_chat
from .core import DATA_DIR, S, sfx, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, lang, mix, tr, ui
from .pages import Page
from .widgets import Button, IconButton, Label, Segmented, hbox, heading, vbox

GAME_NAMES = {"slots": "Slots", "plinko": "Plinko", "dice": "Dice", "mines": "Bombs", "rocket": "Rocket",
              "blackjack": "Blackjack", "daily": "Daily case", "spin": "Free spin", "mini": "Beat Tap",
              "roulette": "Roulette", "hilo": "Hi-Lo", "timing": "Timing", "golf": "Mini Golf", "flip": "Coinflip",
              "golf_solo": "Mini Golf", "wave": "Wave Rush", "tower": "Tower", "blocks": "Block Blast", "sweeper": "Minesweeper"}
ADMIN_COLOUR = "#FF4B6E"


def played_text(minutes: int) -> str:
    text = f"{minutes / 60:.1f}"
    return (text.replace(".", ",") if lang() == "fr" else text) + " h"


def date_text(stamp) -> str:
    day = str(stamp or "")[:10]
    if len(day) == 10 and lang() == "fr":
        return f"{day[8:10]}/{day[5:7]}/{day[0:4]}"
    return day


def ago_text(stamp) -> str:
    """"5 min ago", "3 h ago", "2 days ago" from a server time."""
    from datetime import datetime, timezone
    try:
        then = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        secs = (datetime.now(timezone.utc) - then).total_seconds()
    except (ValueError, TypeError):
        return ""
    if secs < 120:
        return tr("just now")
    if secs < 3600:
        return tr("{n} min ago", n=int(secs // 60))
    if secs < 86400:
        return tr("{n} h ago", n=int(secs // 3600))
    return tr("{n} days ago", n=int(secs // 86400))


# --------------------------------------------------------------------------- #
# Profile pictures: small JPEGs, kept in memory and on disk, asked for again only when they change
# --------------------------------------------------------------------------- #

class Faces:
    """4.0, the root causes of pictures that came and went: (1) only the first 40 names asked were ever sent, the
    others waited forever; (2) a list showing an older version than the one already loaded asked again and again,
    and so did a player without a picture: every repaint sent a request, the requests piled up and other pictures
    failed in turn; (3) places that did not know the version showed no picture at all. Now: every name is sent
    (in batches), a picture at least as new as the one asked counts, "no picture" is remembered for that version,
    failures wait before trying again, and the last picture known is shown while a newer one loads."""
    BATCH = 100                                   # the server takes 200 names a call
    RETRY_S = 20.0                                # after a failed call
    UNKNOWN_S = 120.0                             # version unknown: ask at most every two minutes

    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.pix: dict = {}                       # lower name -> (version, QPixmap or None)
        self._asking: dict = {}                   # lower name -> version wanted (0 = not known)
        self._sent: set = set()
        self._wait: dict = {}                     # lower name -> monotonic time before which we do not ask again
        self._timer_on = False
        self.folder = DATA_DIR / "faces"

    def get(self, name: str, version: int):
        key = (name or "").lower()
        if not key:
            return None
        version = int(version or 0)
        if key == self.ctx.online.username().lower():          # yours: the newest version known
            version = max(version, int(self.ctx.econ.avatar_v or 0))
        have = self.pix.get(key)
        if have is not None and version and have[0] >= version:
            return have[1]                         # this version, or a newer one than the list knows
        if have is None:                           # first look: the last picture saved on this PC
            saved = sorted(self.folder.glob(f"{key}_*.jpg"), key=lambda f: _face_version(f.stem)) \
                if self.folder.is_dir() else []
            if saved:
                v = _face_version(saved[-1].stem)
                pm = QPixmap(str(saved[-1]))
                if not pm.isNull():
                    have = self.pix[key] = (v, pm)
                    if not version or v >= version:
                        return pm
        if not version:
            if have is None or have[0] < 0:
                self._fetch(key, 0, self.UNKNOWN_S)
            return have[1] if have else None
        self._fetch(key, version, self.RETRY_S)
        return have[1] if have else None           # the older picture stays until the new one is here

    def _fetch(self, key: str, version: int, wait: float) -> None:
        if key in self._asking or key in self._sent or not self.ctx.online.logged_in():
            return
        if time.monotonic() < self._wait.get(key, 0.0):
            return
        self._asking[key] = version
        self._wait[key] = time.monotonic() + wait
        if not self._timer_on:
            self._timer_on = True
            QTimer.singleShot(150, self._send)

    def _send(self) -> None:
        self._timer_on = False
        names = sorted(self._asking)[:self.BATCH]
        if not names:
            return
        wanted = {n: self._asking.pop(n) for n in names}
        self._sent.update(names)
        if self._asking:                           # more than one batch: the rest go right after
            self._timer_on = True
            QTimer.singleShot(250, self._send)

        def got(ok: bool, data) -> None:
            self._sent.difference_update(names)
            if not ok or not isinstance(data, dict):
                return                             # asked again after RETRY_S, never in a loop
            changed = False
            try:
                self.folder.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            for name in names:
                info = data.get(name)
                want = wanted.get(name, 0)
                if not info:                       # no picture: remembered for this version
                    old = self.pix.get(name)
                    if old is None or old[1] is not None or old[0] < want:
                        self.pix[name] = (max(want, 0) or -1, None)
                        changed = True
                    continue
                v = int(info.get("v") or 0)
                try:
                    raw = base64.b64decode(info.get("data") or "")
                except ValueError:
                    raw = b""
                img = QImage.fromData(raw, "JPG") if raw else QImage()
                if img.isNull() or img.width() > 512 or img.height() > 512:
                    self.pix[name] = (max(v, want), None)          # broken picture: the letter, no loop
                    changed = True
                    continue
                self.pix[name] = (v, QPixmap.fromImage(img))
                changed = True
                try:
                    for old in self.folder.glob(f"{name}_*.jpg"):
                        old.unlink(missing_ok=True)
                    (self.folder / f"{name}_{v}.jpg").write_bytes(raw)
                except OSError:
                    pass                           # the picture still shows; only the copy on disk is missing
            if changed:
                self.ctx.faces_changed()
        self.ctx.online.ask("rb_avatars_get", {"names": names}, got)

    def upload(self, path: str, done) -> None:
        img = QImage(path)
        if img.isNull():
            return done(False, tr("This picture cannot be used"))
        side = min(img.width(), img.height())
        self.upload_image(img.copy((img.width() - side) // 2, (img.height() - side) // 2, side, side), done)

    def upload_image(self, img: QImage, done) -> None:
        """A square picture (already cropped in the editor) goes to the server, small."""
        img = img.scaled(96, 96, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        buf = QByteArray()
        dev = QBuffer(buf)
        dev.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(dev, "JPG", 82)
        text = base64.b64encode(bytes(buf)).decode()
        me = self.ctx.online.username().lower()

        def back(ok: bool, data) -> None:
            if ok:
                v = int(data or 0)
                self.pix[me] = (v, QPixmap.fromImage(img))
                try:                                     # kept on this PC too: it shows at once next time
                    self.folder.mkdir(parents=True, exist_ok=True)
                    for old in self.folder.glob(f"{me}_*.jpg"):
                        old.unlink(missing_ok=True)
                    (self.folder / f"{me}_{v}.jpg").write_bytes(bytes(buf))
                except OSError:
                    pass
            done(ok, data)
        self.ctx.econ.call("rb_avatar_set", {"picture": text}, back)


def _face_version(stem: str) -> int:
    try:
        return int(stem.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        return 0


def paint_face(p: QPainter, rect: QRectF, ctx, name: str, version: int, online=None, frame=None, now: float = -1.0) -> None:
    """A round profile picture (or the first letter), with their frame and a small online dot."""
    if frame is None:
        frame = ctx.econ.look_of(name).get("frame", "")
    pm = ctx.faces.get(name, version)              # 4.0: also when the version is not known here
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addEllipse(rect)
    if pm is not None:
        p.setClipPath(clip)
        p.drawPixmap(rect.toRect(), pm)
        p.setClipping(False)
    else:
        hue = (sum(ord(c) for c in name.lower()) * 37 % 360) / 360
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor.fromHsvF(hue, 0.45, 0.55))
        p.drawEllipse(rect)
        p.setPen(QColor("#FFFFFF"))
        f = font(12, QFont.Weight.ExtraBold)
        f.setPixelSize(max(6, int(rect.height() * 0.48)))
        p.setFont(f)
        p.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), (name[:1] or "?").upper())
    p.setPen(QPen(alpha("#FFFFFF", 0.14), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(rect)
    if frame:
        from .cosmetics import paint_frame
        paint_frame(p, rect, frame, time.monotonic() if now < 0 else now)
    if online is not None:
        d = max(S(6), rect.width() * 0.26)
        dot = QPointF(rect.right() - d * 0.42, rect.bottom() - d * 0.42)
        p.setPen(QPen(QColor("#0B0E10"), S(1.6)))
        p.setBrush(QColor("#3DDC84") if online else QColor("#5A636B"))
        p.drawEllipse(dot, d / 2, d / 2)
    p.restore()


def paint_admin_tag(p: QPainter, x: float, cy: float) -> float:
    """The red ADMIN tag after a name. Returns its width."""
    p.save()
    p.setFont(font(8.5, QFont.Weight.ExtraBold, 0.8))
    w = p.fontMetrics().horizontalAdvance("ADMIN") + S(10)
    tag = QRectF(x, cy - S(7.5), w, S(15))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(ADMIN_COLOUR))
    p.drawRoundedRect(tag, S(4), S(4))
    p.setPen(QColor("#FFFFFF"))
    p.drawText(tag, int(Qt.AlignmentFlag.AlignCenter), "ADMIN")
    p.restore()
    return w


def paint_name_tags(p: QPainter, x: float, cy: float, ctx, name: str, admin: bool = False, size: float = 8.5) -> float:
    """ADMIN and the tag someone wears (OG...) after their name. Returns the width used."""
    w = 0.0
    if admin:
        w += paint_admin_tag(p, x, cy) + S(5)
    tag = ctx.econ.look_of(name).get("tag")
    if tag:
        from .cosmetics import paint_tag
        w += paint_tag(p, x + w, cy, tag, time.monotonic(), size) + S(5)
    return w


class Ticker(QTimer):
    """Redraws a widget a few times a second while it shows something that moves (a frame, a tag, a banner)."""

    def __init__(self, widget, ms: int = 80) -> None:
        super().__init__(widget)
        self.setInterval(ms)
        self.timeout.connect(widget.update)


class PlayerRow(QWidget):
    """One player: picture, name (and ADMIN), hours, their three badges, and a button."""
    opened = pyqtSignal(str)

    def __init__(self, page, info: dict) -> None:
        super().__init__()
        self.page, self.ctx, self.info = page, page.ctx, info
        self.setFixedHeight(S(46))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        lay = hbox(self, 6, (0, 0, 6, 0))
        lay.addStretch(1)
        name, state = info["username"], info.get("state")
        if info.get("me"):
            pass
        elif state == "asks":
            yes, no = Button(tr("Accept"), "primary", 28), Button(tr("Decline"), "ghost", 28)
            yes.clicked.connect(lambda: page.act("rb_friend_add", name))
            no.clicked.connect(lambda: page.act("rb_friend_remove", name))
            lay.addWidget(yes)
            lay.addWidget(no)
        elif state == "asked":
            b = Button(tr("Cancel"), "ghost", 28)
            b.clicked.connect(lambda: page.act("rb_friend_remove", name))
            lay.addWidget(b)
        elif state != "friend":
            b = Button(tr("Add"), "primary", 28)
            b.clicked.connect(lambda: page.act("rb_friend_add", name))
            lay.addWidget(b)
        for i in range(lay.count()):
            w = lay.itemAt(i).widget()
            if w is not None:
                w.setFixedWidth(max(S(64), w.sizeHint().width()))
        self._hover = False

    def enterEvent(self, _e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.page.open_profile(self.info["username"])

    def paintEvent(self, _e) -> None:
        from .collection import show_item
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 2, -0.5, -2)
        info = self.info
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.07 if self._hover else 0.04))
        p.drawRoundedRect(r, S(10), S(10))
        friend = info.get("state") == "friend" or info.get("me")
        paint_face(p, QRectF(r.left() + S(7), r.center().y() - S(15), S(30), S(30)), self.ctx, info["username"],
                   int(info.get("avatar_v") or 0), bool(info.get("online")) if friend else None)
        x = r.left() + S(46)
        p.setPen(QColor(TEXT))
        p.setFont(font(12.5, QFont.Weight.DemiBold))
        name = info["username"] + ("  (" + tr("you") + ")" if info.get("me") else "")
        p.drawText(QRectF(x, r.top() + S(4), S(160), S(18)), int(Qt.AlignmentFlag.AlignVCenter), name)
        nx = x + p.fontMetrics().horizontalAdvance(name) + S(6)
        nx += paint_name_tags(p, nx, r.top() + S(13), self.ctx, info["username"], bool(info.get("admin")))
        badges = [b for b in (info.get("badges") or []) if b][:3]
        for k, item in enumerate(badges):
            show_item(p, item, QRectF(nx + k * S(16), r.top() + S(6), S(13), S(13)), 0, effects=False)
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10, QFont.Weight.DemiBold))
        state = info.get("state")
        sub = played_text(int(info.get("minutes") or 0))
        if state == "asks":
            sub = tr("Wants to be friends")
        elif state == "asked":
            sub = tr("Request sent")
        elif friend and not info.get("me"):
            if info.get("online"):
                sub += "  ·  " + tr("Online")
            else:
                seen = ago_text(info.get("seen")) if info.get("seen") else ""
                sub += "  ·  " + (tr("seen {t}", t=seen) if seen else tr("Offline"))
            n = len([b for b in (info.get("badges") or []) if b])
            if n:
                sub += "  ·  " + tr("{n} on show", n=n)
        p.drawText(QRectF(x, r.top() + S(22), S(200), S(16)), int(Qt.AlignmentFlag.AlignVCenter), sub)
        if state == "friend":                         # 4.3: a blue dot on the right: this one is a friend
            c = self._dot()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha("#3D9BFF", 0.22))
            p.drawEllipse(c, S(8), S(8))
            p.setBrush(QColor("#3D9BFF"))
            p.drawEllipse(c, S(4.5), S(4.5))

    def _dot(self) -> QPointF:
        return QPointF(self.width() - S(20), self.height() / 2)

    def mouseMoveEvent(self, e) -> None:
        if self.info.get("state") == "friend":
            near = (e.position() - self._dot()).manhattanLength() < S(16)
            self.setToolTip(tr("FRIENDS") if near else "")


class StatsCard(QWidget):
    """Your picture, name, ADMIN tag and stats: the top of the Social tab."""
    picture = pyqtSignal()

    def __init__(self, ctx, data: dict, width: int) -> None:
        super().__init__()
        self.ctx, self.data = ctx, data
        self.setFixedSize(width, S(150))
        self.setMouseTracking(True)
        self._tick = Ticker(self, 80)

    def showEvent(self, _e) -> None:
        self._tick.start()

    def hideEvent(self, _e) -> None:
        self._tick.stop()

    def _face(self) -> QRectF:
        return QRectF(S(12), S(12), S(52), S(52))

    def mouseMoveEvent(self, e) -> None:
        on = self._face().contains(e.position())
        self.setCursor(Qt.CursorShape.PointingHandCursor if on else Qt.CursorShape.ArrowCursor)
        self.setToolTip(tr("Change your picture (PNG or JPG)") if on else "")

    def mousePressEvent(self, e) -> None:
        e.accept()
        if self._face().contains(e.position()):
            self.picture.emit()

    def paintEvent(self, _e) -> None:
        from .wallet import coins_text
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha(ui.accent, 0.35), 1.1))
        p.setBrush(alpha("#FFFFFF", 0.04))
        p.drawRoundedRect(r, S(12), S(12))
        d, st = self.data, self.data.get("stats") or {}
        name = d.get("username") or self.ctx.online.username()
        look = self.ctx.econ.look_of(name)
        banner = look.get("banner")
        if banner:                                         # your banner behind the top of the card
            from .cosmetics import paint_banner
            p.save()
            p.setOpacity(0.55)
            paint_banner(p, QRectF(r.left(), r.top(), r.width(), S(66)), banner, time.monotonic(), S(12), 1.0,
                         int(look.get("gold") or 0))
            p.restore()
        paint_face(p, self._face(), self.ctx, name, int(d.get("avatar_v") or self.ctx.econ.avatar_v or 0))
        p.setPen(QColor(TEXT))
        p.setFont(font(16, QFont.Weight.Bold))
        p.drawText(QRectF(S(76), S(14), S(200), S(24)), int(Qt.AlignmentFlag.AlignVCenter), name)
        nx = S(76) + p.fontMetrics().horizontalAdvance(name) + S(8)
        paint_name_tags(p, nx, S(26), self.ctx, name, bool(d.get("admin")))
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(S(76), S(38), r.width() - S(90), S(18)), int(Qt.AlignmentFlag.AlignVCenter),
                   tr("{h} Played · Member Since {d}", h=played_text(int(d.get("minutes") or 0)), d=date_text(d.get("since"))))
        bet, won = int(st.get("bet") or 0), int(st.get("won") or 0)
        cells = [(coins_text(int(d.get("coins") or 0)), tr("Coins")), (str(int(d.get("keys") or 0)), tr("Keys")),
                 (str(int(st.get("items") or 0)), tr("Items")), (str(int(st.get("badges") or 0)), tr("Badges")),
                 (str(int(st.get("cases") or 0)), tr("Cases")), (str(int(st.get("trades") or 0)), tr("Trades")),
                 (str(int(st.get("rounds") or 0)), tr("Bets")), (("+" if won >= bet else "−") + coins_text(abs(won - bet)), tr("Casino"))]
        w = (r.width() - S(16)) / 4
        for i, (big, small) in enumerate(cells):
            box = QRectF(r.left() + S(8) + (i % 4) * w, S(72) + (i // 4) * S(38), w, S(36))
            col = TEXT
            if i == 7:
                col = "#5BE08A" if won >= bet else "#FF7A7A"
            p.setPen(QColor(col))
            p.setFont(font(12.5, QFont.Weight.Bold))
            p.drawText(QRectF(box.left(), box.top(), box.width(), S(18)), int(Qt.AlignmentFlag.AlignCenter), big)
            p.setPen(QColor(TEXT_FAINT))
            p.setFont(font(9.5, QFont.Weight.DemiBold))
            p.drawText(QRectF(box.left(), box.top() + S(18), box.width(), S(14)), int(Qt.AlignmentFlag.AlignCenter), small)


class TradeAsk(QWidget):
    """Someone wants to trade with you."""

    def __init__(self, page, ask: dict) -> None:
        super().__init__()
        self.ask = ask
        self.setFixedHeight(S(44))
        lay = hbox(self, 6, (12, 0, 6, 0))
        lay.addWidget(Label(tr("{name} wants to trade", name=ask.get("from", "?")), 12, TRADE_GOLD, bold=True), 1)
        yes, no = Button(tr("Open Trade"), "primary", 28), Button(tr("Decline"), "ghost", 28)
        yes.clicked.connect(lambda: page.accept_trade(ask["id"]))
        no.clicked.connect(lambda: page.ctx.econ.call("rb_trade_cancel", {"trade": ask["id"]},
                                                      lambda _o, _d: page.ctx.econ.poll_live()))
        lay.addWidget(yes)
        lay.addWidget(no)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(alpha(TRADE_GOLD, 0.6), 1.2))
        p.setBrush(alpha(TRADE_GOLD, 0.08))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 2, -0.5, -2), S(10), S(10))


TRADE_GOLD = "#E8C26A"


class PerkRow(QWidget):
    """One thing friends can do together: an icon, a name and a few words."""

    def __init__(self, icon: str, head: str, text: str, width: int) -> None:
        super().__init__()
        self.icon, self.head, self.text = icon, head, text
        self.setFixedSize(width, S(26))

    def paintEvent(self, _e) -> None:
        from .widgets import draw_icon
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.save()
        p.translate(S(11), self.height() / 2)
        p.scale(0.8, 0.8)
        draw_icon(p, self.icon, QColor(ui.accent))
        p.restore()
        p.setPen(QColor(TEXT))
        p.setFont(font(11, QFont.Weight.Bold))
        p.drawText(QRectF(S(28), 0, S(110), self.height()), int(Qt.AlignmentFlag.AlignVCenter), self.head)
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10.5))
        p.drawText(QRectF(S(130), 0, self.width() - S(130), self.height()), int(Qt.AlignmentFlag.AlignVCenter), self.text)


class ActivityRow(QWidget):
    """One thing waiting for you: a coloured mark, the text, a green button (and sometimes a second one)."""

    def __init__(self, colour: str, text: str, action: str, on_go, second=None, width: int = 0) -> None:
        super().__init__()
        self.colour = QColor(colour)
        self.setFixedHeight(S(40))
        lay = hbox(self, 6, (14, 0, 6, 0))
        lay.addWidget(Label(text, 11.5, TEXT, bold=True, shrink=9), 1)
        if second is not None:
            b2 = Button(second[0], "ghost", 28)
            b2.setFixedWidth(max(S(64), b2.sizeHint().width()))
            b2.clicked.connect(second[1])
            lay.addWidget(b2)
        go = Button(action, "primary", 28)
        go.setFixedWidth(max(S(64), go.sizeHint().width()))
        go.clicked.connect(on_go)
        lay.addWidget(go)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 1.5, -0.5, -1.5)
        p.setPen(QPen(alpha(self.colour, 0.45), 1.1))
        p.setBrush(alpha(self.colour, 0.07))
        p.drawRoundedRect(r, S(10), S(10))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.colour)
        p.drawRoundedRect(QRectF(r.left() + S(5), r.top() + S(9), S(3), r.height() - S(18)), S(1.5), S(1.5))


def build_activity(page, lay) -> None:
    """4.0: Online Activity: requests to answer, games to join, unread messages, your open trade. One place."""
    from .core import TEXT_FAINT
    ctx = page.ctx
    live = ctx.econ.live
    act = live.get("activity") or {}
    rows = []
    for ask in live.get("trades") or []:
        rows.append(("#E8C26A", tr("{name} wants to trade", name=ask.get("from", "?")), tr("Open"),
                     lambda a=ask: page.accept_trade(a["id"]),
                     (tr("No"), lambda a=ask: ctx.econ.call("rb_trade_cancel", {"trade": a["id"]},
                                                            lambda _o, _d: ctx.econ.poll_live()))))
    if live.get("open_trade") and not ctx.trade.trade_id:
        rows.append(("#E8C26A", tr("Your trade is waiting"), tr("Back to it"), lambda: page.open_trade(live["open_trade"]), None))
    asks = int(live.get("asks") or 0)
    if asks:
        rows.append(("#3DDC84", tr("{n} friend requests", n=asks) if asks > 1 else tr("1 friend request"), tr("See"),
                     lambda: (setattr(ctx, "social_tab", 0), ctx.reload_page()), None))
    unread = int(act.get("unread") or getattr(ctx, "msg_unread", 0) or 0)
    if unread:
        rows.append(("#2EE6D6", tr("{n} unread messages", n=unread) if unread > 1 else tr("1 unread message"), tr("Read"),
                     lambda: (setattr(ctx, "social_tab", 2), ctx.reload_page()), None))
    golf, flip = int(act.get("golf_open") or 0), int(act.get("flip_open") or 0)
    from .notify import go
    if golf:
        rows.append(("#3DDC84", tr("{n} Mini Golf matches to join", n=golf) if golf > 1 else tr("1 Mini Golf match to join"),
                     tr("Join"), lambda: go(ctx, "golf"), None))
    if flip:
        rows.append(("#FF8A3D", tr("{n} coinflips to join", n=flip) if flip > 1 else tr("1 coinflip to join"),
                     tr("Join"), lambda: go(ctx, "flip"), None))
    for g in live.get("giveaways") or []:
        if g.get("state") == "live" and not g.get("joined"):
            rows.append(("#FF5CC8", tr("Live giveaway: {title}", title=g.get("title", "")), tr("Open"), lambda: go(ctx, "giveaway"), None))
            break
    if not rows:                                    # 4.1: nothing going on: no heading, no filler row
        return
    lay.addWidget(Label(tr("ONLINE ACTIVITY"), 9.5, TEXT_FAINT, weight=QFont.Weight.Bold))
    for colour, text, action, fn, second in rows[:6]:
        lay.addWidget(ActivityRow(colour, text, action, fn, second))


class FriendsPage(Page):
    """The Social tab."""
    key = "friends"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.lay = vbox(self, 6)
        self.friends = getattr(ctx, "friends_cache", None)
        self._poll = QTimer(self)
        self._poll.setInterval(10000)                 # live: hours, coins, online, trades
        self._poll.timeout.connect(self.refresh)
        self._anim = QTimer(self)                     # frames and tags that move, in the lists
        self._anim.setInterval(90)
        self._anim.timeout.connect(self._redraw_rows)
        ctx.econ.looks_changed.connect(self._redraw_rows)
        self._build()

    def _redraw_rows(self) -> None:
        for row in self.findChildren(PlayerRow):
            row.update()

    def _redo(self) -> None:
        if self.ctx.window.showing("friends") and self.ctx.window.expanded:
            self.ctx.reload_page("friends")

    def _build(self) -> None:
        ctx = self.ctx
        if ctx.trade.trade_id:
            return build_trade(self, self.lay)
        who = getattr(ctx, "friends_profile", None)
        if who:
            return self._profile(who)
        if not ctx.online.logged_in():
            return self.lay.addWidget(Label(tr("Log in to see other users"), 12, TEXT_DIM))
        if getattr(ctx, "social_edit", False):            # quick profile editing: banner, frame, tag, showcase
            return self._edit_profile()
        me = getattr(ctx, "social_me", None) or {}
        card = StatsCard(ctx, me, self.W)
        card.picture.connect(self._picture_menu)
        self.lay.addWidget(card)
        line = hbox(spacing=6)                       # 4.0: one row, the three things you do with your profile
        edit = Button(tr("Edit Profile"), "primary", 30, icon="spark")

        def open_edit() -> None:
            ctx.social_edit = True
            ctx.reload_page()
        edit.clicked.connect(open_edit)
        stats = Button(tr("My Stats"), "ghost", 30, icon="perf")
        stats.clicked.connect(lambda: self.open_profile(ctx.online.username()))
        songs = Button(tr("Songs"), "ghost", 30, icon="note")

        def open_songs() -> None:
            from .hub import HistoryWindow
            ctx._hist = HistoryWindow(ctx)
        songs.clicked.connect(open_songs)
        line.addWidget(edit, 1)
        line.addWidget(stats, 1)
        line.addWidget(songs, 1)
        self.lay.addLayout(line)
        build_activity(self, self.lay)               # 4.0: everything waiting for you, in one place
        tab = int(getattr(ctx, "social_tab", 0) or 0)
        unread = int(getattr(ctx, "msg_unread", 0) or 0)
        asks_n = int(ctx.econ.live.get("asks") or 0)
        if tab == 1:                                     # 4.3: Users and Friends are one tab now
            tab = ctx.social_tab = 0
        nav = NavTiles([(tr("Users"), "users"), (tr("Leaderboards"), "trophy"), (tr("Chat"), "chat"), (tr("Trades"), "swap")],
                       {0: 0, 3: 1, 2: 2, 4: 3}.get(tab, -1), per_row=4, badges={0: asks_n, 2: unread})

        def switch(i: int) -> None:
            ctx.social_tab = [0, 3, 2, 4][i]
            ctx.reload_page()
        nav.changed.connect(switch)
        self.lay.addWidget(nav)
        if tab == 2:
            return build_messages(self, self.lay)
        if tab == 3:
            return build_leaders(self, self.lay)
        if tab == 4:
            return build_trade_history(self, self.lay)
        self._users()

    def _users(self) -> None:
        """4.3: one Users tab: requests and friends first, then everyone else (a blue dot marks a friend)."""
        ctx = self.ctx
        if self.friends is None:
            return self.lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
        asks = [f for f in self.friends if f["state"] == "asks"]
        mine = [f for f in self.friends if f["state"] == "friend"]
        sent = [f for f in self.friends if f["state"] == "asked"]
        mine.sort(key=lambda f: (not f.get("online"), f["username"].lower()))
        online = sum(1 for f in mine if f.get("online"))
        if asks:
            self.lay.addWidget(heading(tr("Requests")))
            for info in asks:
                self.lay.addWidget(PlayerRow(self, info))
        self.lay.addWidget(heading(tr("Friends") + f"  ·  {online} " + tr("online")))
        if not mine:
            self.lay.addWidget(Label(tr("No friends yet. Press Add next to someone below."), 11, TEXT_DIM, wrap_w=self.W))
        for info in mine:
            self.lay.addWidget(PlayerRow(self, info))
        if sent:
            self.lay.addWidget(heading(tr("Sent")))
            for info in sent:
                self.lay.addWidget(PlayerRow(self, info))
        rows = getattr(ctx, "users_cache", None)
        known = {f["username"] for f in self.friends}
        self.lay.addWidget(heading(tr("Other users")))
        if rows is None:
            return self.lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
        others = [r for r in rows if r.get("username") not in known and not r.get("me")]
        if not others:
            return self.lay.addWidget(Label(tr("Nobody else yet"), 11, TEXT_DIM))
        self.lay.addWidget(Label(tr("{n} users. Click one to see their profile.", n=len(others)), 10.5, TEXT_DIM))
        for info in others:
            self.lay.addWidget(PlayerRow(self, info))

    def _duel(self, name: str) -> None:
        """3.2: no more invitations: open the Mini Golf lobby (open a match there and your friend joins it)."""
        ctx = self.ctx
        ctx.games_sub = "duels"
        ctx.golf_id = None
        ctx.toast(tr("Open a match: {name} can join it from the Mini Golf lobby", name=name))
        for flag in ("quests_open", "mini_open", "park_open"):
            setattr(ctx, flag, False)
        ctx.window._drop_page("games")
        ctx.window.goto("games")

    # -- server
    def refresh(self) -> None:
        ctx = self.ctx
        if not ctx.online.logged_in() or ctx.trade.trade_id:
            return
        if getattr(ctx, "friends_profile", None):
            cur = getattr(ctx, "friends_data", None) or {}
            if (cur.get("profile") or {}).get("stats") is not None:
                self._ask_songs(ctx.friends_profile)
            return ctx.online.ask("rb_profile", {"name": ctx.friends_profile}, self._got_profile_again)
        ctx.online.ask("rb_social", {}, self._got_me)
        tab = int(getattr(ctx, "social_tab", 0) or 0)
        if tab in (2, 3, 4):
            return
        ctx.online.ask("rb_friends_list", {}, self._listed)
        ctx.online.ask("rb_users", {"search": "", "page": 0}, self._got_users)

    def _got_me(self, ok: bool, data) -> None:
        if ok and isinstance(data, dict) and data != getattr(self.ctx, "social_me", None):
            self.ctx.social_me = data
            self._redo()

    def _got_users(self, ok: bool, data) -> None:
        if ok and isinstance(data, list) and data != getattr(self.ctx, "users_cache", None):
            self.ctx.users_cache = data
            self._redo()

    def _listed(self, ok: bool, data) -> None:
        if ok and isinstance(data, list) and data != self.friends:
            self.friends = self.ctx.friends_cache = data
            self._redo()

    def act(self, fn: str, name: str, then=None) -> None:
        sfx.play("pick")

        def done(ok: bool, data) -> None:
            if not ok:
                self.ctx.toast(tr(str(data)), "warn")
            elif fn == "rb_friend_add":
                self.ctx.toast(tr("You are now friends") if data == "friends" else tr("Request sent"))
            if then:
                then(ok)
            self.ctx.users_cache = None if fn == "rb_friend_add" and self.ctx.users_cache is None else self.ctx.users_cache
            self.refresh()
            self.ctx.online.ask("rb_users", {"search": "", "page": 0}, self._got_users)
        self.ctx.econ.call(fn, {"name": name}, done)

    def _edit_profile(self) -> None:
        from .bazaar import build_profile_style
        top = hbox(spacing=8)
        back = IconButton("back", 30, tip=tr("Back"))

        def leave() -> None:
            self.ctx.social_edit = False
            self.ctx.reload_page()
        back.clicked.connect(leave)
        top.addWidget(back)
        top.addWidget(Label(tr("Edit Profile"), 16, bold=True), 1)
        self.lay.addLayout(top)
        line = hbox(spacing=6)
        pic = Button(tr("Change Picture"), "ghost", 30)
        pic.setToolTip(tr("PNG or JPG"))
        pic.clicked.connect(self._picture_menu)
        rename = Button(tr("Change Name"), "ghost", 30)
        rename.clicked.connect(self._rename)
        line.addWidget(pic, 1)
        line.addWidget(rename, 1)
        self.lay.addLayout(line)
        build_profile_style(self, self.lay)

    def _picture_menu(self) -> None:
        """4.5: a click on your picture asks what to do: a new picture, move the one you have, or remove it."""
        from PyQt6.QtGui import QAction, QCursor
        from PyQt6.QtWidgets import QMenu
        ctx = self.ctx
        has = bool(int(ctx.econ.avatar_v or 0)) and ctx.faces.get(ctx.online.username(), int(ctx.econ.avatar_v or 0)) is not None
        m = QMenu()
        m.setStyleSheet(f"QMenu {{ background: #14191C; color: #E9EDF0; border: 1px solid #2A3136; border-radius: 8px;"
                        f" padding: 4px; font-size: {S(12)}px; }} QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}"
                        f" QMenu::item:selected {{ background: #232B30; }} QMenu::item:disabled {{ color: #5A6369; }}")
        for text, fn, on in ((tr("Change profile picture"), self._picture, True),
                             (tr("Edit (move and zoom)"), self._picture_edit, has),
                             (tr("Remove profile picture"), self._picture_remove, has)):
            a = QAction(text, m)
            a.setEnabled(on)
            a.triggered.connect(lambda _c=False, fn=fn: QTimer.singleShot(0, fn))
            m.addAction(a)
        m.exec(QCursor.pos())

    def _picture_remove(self) -> None:
        ctx = self.ctx

        def go() -> None:
            def done(ok: bool, data) -> None:
                if not ok:
                    return ctx.toast(tr(str(data)), "warn")
                ctx.econ.avatar_v = int(data or 0)
                me = ctx.online.username().lower()
                ctx.faces.pix[me] = (int(data or 0), None)
                try:
                    for old in ctx.faces.folder.glob(f"{me}_*.jpg"):
                        old.unlink(missing_ok=True)
                except OSError:
                    pass
                if isinstance(getattr(ctx, "social_me", None), dict):
                    ctx.social_me["avatar_v"] = int(data or 0)
                sfx.play("off")
                ctx.toast(tr("Picture removed"))
                ctx.faces_changed()
                self._redo()
            ctx.econ.call("rb_avatar_set", {"picture": ""}, done)
        ctx.window.confirm(tr("Remove your profile picture?"), go, yes=tr("Remove"))

    def _picture_edit(self) -> None:
        """Move or zoom the picture you already have (the full picture you chose, when this PC still has it)."""
        ctx = self.ctx
        orig = ctx.faces.folder / "my_original.png"
        img = QImage(str(orig)) if orig.exists() else QImage()
        if img.isNull():
            pm = ctx.faces.get(ctx.online.username(), int(ctx.econ.avatar_v or 0))
            img = pm.toImage() if pm is not None else QImage()
        if img.isNull():
            return self._picture()
        self._picture_open(img, keep=False)

    def _picture(self) -> None:
        path = self.ctx.pick_file(tr("Choose a picture"), "Pictures (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        img = QImage(path)
        if img.isNull():
            return self.ctx.toast(tr("This picture cannot be used"), "warn")
        self._picture_open(img, keep=True)

    def _picture_open(self, img, keep: bool) -> None:
        if keep:                                       # the full picture stays on this PC, to move it again later
            try:
                self.ctx.faces.folder.mkdir(parents=True, exist_ok=True)
                side = max(img.width(), img.height())
                small = img if side <= 900 else img.scaled(900, 900, Qt.AspectRatioMode.KeepAspectRatio,
                                                           Qt.TransformationMode.SmoothTransformation)
                small.save(str(self.ctx.faces.folder / "my_original.png"), "PNG")
            except OSError:
                pass

        def done(ok: bool, data) -> None:
            if not ok:
                return self.ctx.toast(tr(str(data)), "warn")
            sfx.play("on")
            self.ctx.econ.avatar_v = int(data or 0)
            if isinstance(getattr(self.ctx, "social_me", None), dict):
                self.ctx.social_me["avatar_v"] = int(data or 0)
            self.ctx.toast(tr("Picture changed: everyone can see it"))
            self._redo()
        from .hub import AvatarEditor
        self.ctx._avatar = AvatarEditor(self.ctx, img, lambda out: self.ctx.faces.upload_image(out, done))

    def _rename(self) -> None:
        me = getattr(self.ctx, "social_me", None) or {}
        wait = int(me.get("rename_wait") or 0)
        if wait > 0:
            from .shop import clock_text
            return self.ctx.toast(tr("You can change your name again in {t}", t=clock_text(wait)), "warn")

        def send(name: str, dlg) -> None:
            if not name.isalnum() or not 3 <= len(name) <= 10:
                return dlg.say(tr("3 to 10 letters or numbers"))

            def go() -> None:
                def done(ok: bool, data) -> None:
                    if not ok:
                        return self.ctx.toast(tr(str(data)), "warn")
                    sfx.play("on")
                    self.ctx.online.s["username"] = name
                    self.ctx.online._save()
                    self.ctx.social_me = None
                    self.ctx.toast(tr("You are now {name}", name=name))
                    self.ctx.window.update()
                    self.refresh()
                self.ctx.econ.call("rb_rename", {"new_name": name}, done)
            dlg.close()
            self.ctx.window.confirm(tr("Change your name to {name}? You can only do it once every 24 hours. "
                                       "Log in with your new name from now on.", name=name), go, yes=tr("Change"))
        self._dialog = AskDialog(self.ctx, tr("Change Name"), tr("New username"), tr("Next"), send, 10,
                                 tr("Once every 24 hours. Friends, items and hours stay the same."))

    # -- trades
    def open_trade(self, trade_id: str) -> None:
        sfx.play("pick")
        self.ctx.friends_profile = None
        self.ctx.trade.open(trade_id)
        self.ctx.reload_page()

    def accept_trade(self, trade_id: str) -> None:
        def done(ok: bool, data) -> None:
            if not ok:
                return self.ctx.toast(tr(str(data)), "warn")
            self.open_trade(trade_id)
        self.ctx.econ.call("rb_trade_accept", {"trade": trade_id}, done)

    def ask_trade(self, name: str) -> None:
        if not self.ctx.econ.can_trade():
            return self.ctx.toast(tr("Trading unlocks after 5 hours with Rubenium"), "warn")

        def done(ok: bool, data) -> None:
            if not ok:
                return self.ctx.toast(tr(str(data)), "warn")
            self.ctx.toast(tr("Trade request sent to {name}", name=name))
            self.open_trade(str(data))
        self.ctx.econ.call("rb_trade_request", {"name": name}, done)

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
        self.lay.addLayout(top)
        if data is None:
            self.lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
            return ctx.online.ask("rb_profile", {"name": name}, self._got_profile)
        prof, hist = data.get("profile") or {}, data.get("history")
        self.lay.addWidget(ProfileCard(ctx, prof, self.W))
        badges = list(prof.get("badges") or [])
        owned = set(badges)
        worn_now = [w for w in ((prof.get("equip") or {}).get(k) for k in ("badge1", "badge2", "badge3")) if w and
                    (w in owned or (w.endswith(":grey") and any(b.startswith(w[:-4]) for b in owned)))]
        self.lay.addWidget(Showcase3(ctx, worn_now, self.W, prof.get("me")))
        if not prof.get("me"):
            self._relation(prof, name)
        self.lay.addWidget(heading(tr("Badges") + f"  ·  {len(badges)}"))
        if badges:
            self.lay.addWidget(BadgeStrip(ctx, badges, worn_now, self.W))
        else:
            self.lay.addWidget(Label(tr("No badges yet"), 12, TEXT_DIM))
        if prof.get("stats") is None:
            return
        self._details(prof)
        songs = data.get("songs")
        if songs is not None and (songs.get("rows") or not songs.get("shared", True)):
            self.lay.addWidget(heading(tr("Recently Played")))
            if not songs.get("shared", True):
                self.lay.addWidget(Label(tr("Hidden by this user"), 11, TEXT_FAINT))
            else:
                from .hub import HistoryRow
                for row in (songs.get("rows") or [])[:10]:
                    self.lay.addWidget(HistoryRow(row, self.W))
        if hist is None:
            return self.lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
        for key, title in (("trades", tr("Last 3 Trades")), ("cases", tr("Last 3 Cases")), ("spins", tr("Last 3 Spins")),
                           ("bets", tr("Last 30 Bets"))):
            rows = hist.get(key) or []
            self.lay.addWidget(heading(title))
            if not rows:
                self.lay.addWidget(Label(tr("Nothing yet"), 11, TEXT_FAINT))
            else:
                self.lay.addWidget(HistoryList(ctx, key, rows, self.W))

    PERKS = [("users", "Chat", "Send messages"), ("swap", "Trading", "Swap items and coins"),
             ("gift", "Gifts", "Send cases to each other"), ("perf", "Full profile", "Stats, history, last seen"),
             ("spark", "Online", "See when they are on"), ("chip", "Leaderboard", "Compare in the Friends top")]

    def _relation(self, prof: dict, name: str) -> None:
        """Friends and not-friends see different things: friends get actions, others see why to add them."""
        ctx = self.ctx
        from .hub import NavTiles
        state = prof.get("state")
        if prof.get("friend"):
            self.lay.addWidget(Label("✓ " + tr("You are friends"), 12, "#3DDC84", bold=True))
            acts = [(tr("Message"), "users"), (tr("Mini Golf"), "shield"), (tr("Trade"), "chip"), (tr("Gift a Case"), "gift")]
            grid = NavTiles(acts, -1, select=False)

            def act(i: int) -> None:
                if i == 0:
                    open_chat(ctx, name)
                elif i == 1:
                    self._duel(name)
                elif i == 2:
                    self.ask_trade(name)
                else:
                    ctx.shop_tab, ctx.shop_case = 3, None
                    ctx.toast(tr("Pick a case, then press “Gift this case to a friend”"))
                    ctx.window._drop_page("themes")
                    ctx.window.goto("themes")
            grid.changed.connect(act)
            self.lay.addWidget(grid)
            rm = Button(tr("Remove friend"), "quiet", 24)
            rm._font.setUnderline(True)
            rm.clicked.connect(lambda: ctx.window.confirm(tr("Remove {name} from your friends?", name=name),
                               lambda: self.act("rb_friend_remove", name, lambda _ok: self.open_profile(None)), yes=tr("Remove")))
            self.lay.addWidget(rm, 0, Qt.AlignmentFlag.AlignRight)
            return
        # not friends (yet): what you get by adding them, and one clear button
        card = QWidget()
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(f"background: rgba(255,255,255,0.04); border-radius: {S(12)}px;")
        cl = vbox(card, 6, (12, 10, 12, 12))
        title = {"asks": tr("{name} wants to be your friend", name=name),
                 "asked": tr("Friend request sent to {name}", name=name)}.get(state, tr("Add {name} as a friend to:", name=name))
        cl.addWidget(Label(title, 12.5, TEXT, bold=True, wrap_w=self.W - S(24)))
        for icon, head, text in self.PERKS:
            cl.addWidget(PerkRow(icon, tr(head), tr(text), self.W - S(24)))
        if state == "asks":
            b = Button(tr("Accept Friend"), "primary", 34)
            b.clicked.connect(lambda: self.act("rb_friend_add", name, lambda _ok: self.open_profile(name)))
            cl.addWidget(b)
        elif state == "asked":
            cl.addWidget(Label(tr("Waiting for them to accept."), 11, TEXT_DIM))
        else:
            b = Button(tr("Add Friend"), "primary", 34, icon="plus")
            b.clicked.connect(lambda: self.act("rb_friend_add", name, lambda _ok: self.open_profile(name)))
            cl.addWidget(b)
        self.lay.addWidget(card)                       # 4.5: trading is for friends only

    def _details(self, prof: dict) -> None:
        """A friend's numbers and what they are wearing."""
        from .admin import Numbers
        from .bazaar import ItemGrid
        from .wallet import coins_text
        st = prof.get("stats") or {}
        bet, won = int(st.get("bet") or 0), int(st.get("won") or 0)
        seen = tr("Online") if prof.get("online") else (ago_text(prof.get("seen")) or "—")
        self.lay.addWidget(heading(tr("Stats")))
        self.lay.addWidget(Numbers([
            (played_text(int(prof.get("minutes") or 0)), tr("Played")), (seen, tr("Last Seen")),
            (int(st.get("friends") or 0), tr("Friends")),
            (int(st.get("items") or 0), tr("Items")), (coins_text(int(st.get("worth") or 0)), tr("Collection Worth")),
            (int(st.get("badges") or 0), tr("Badges")),
            (int(st.get("gold") or 0), tr("Gold Badges"), "#E8C26A"), (int(st.get("cases") or 0), tr("Cases Opened")),
            (int(st.get("trades") or 0), tr("Trades")),
            (int(st.get("rounds") or 0), tr("Casino Bets")), (coins_text(int(st.get("best") or 0)), tr("Best Win")),
            (("+" if won >= bet else "−") + coins_text(abs(won - bet)), tr("Casino Result"),
             "#5BE08A" if won >= bet else "#FF7A7A"),
            (int(st.get("mini") or 0), tr("Beat Tap")), (int(st.get("park") or 0), tr("Parking")),
            (int(st.get("spins") or 0), tr("Free Spins"))], self.W))
        eq = prof.get("equip") or {}
        wearing = [eq.get(k) for k in ("ball", "ring", "theme", "font")]
        wearing = [w for w in wearing if w and w.split(":")[0] in ("ball", "line", "theme", "font")]
        if wearing:
            self.lay.addWidget(heading(tr("Wearing")))
            grid = ItemGrid(self.ctx, [{"item": w, "text": ""} for w in wearing], self.W, 6, 58)
            grid.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.lay.addWidget(grid)

    def _got_profile(self, ok: bool, data) -> None:
        name = getattr(self.ctx, "friends_profile", None)
        if not name:
            return
        if not ok:
            self.ctx.toast(tr(str(data)), "warn")
            return self.open_profile(None)
        self.ctx.friends_data = {"profile": data, "history": None}
        self._redo()
        if data.get("stats") is not None:
            self.ctx.online.ask("rb_history", {"name": name}, self._got_history)
            self._ask_songs(name)

    def _ask_songs(self, name: str) -> None:
        """The songs a friend played lately (3.0.0 server; nothing is shown on an older one)."""
        def got(ok: bool, data) -> None:
            cur = getattr(self.ctx, "friends_data", None)
            if cur is None or getattr(self.ctx, "friends_profile", None) != name or not ok or not isinstance(data, dict):
                return
            if data != cur.get("songs"):
                cur["songs"] = data
                self._redo()
        self.ctx.online.ask("rb_songs", {"name": name}, got)

    def _got_profile_again(self, ok: bool, data) -> None:
        cur = getattr(self.ctx, "friends_data", None)
        if ok and isinstance(data, dict) and cur is not None and data != cur.get("profile"):
            cur["profile"] = data
            if data.get("stats") is not None:
                return self.ctx.online.ask("rb_history", {"name": self.ctx.friends_profile}, self._got_history)
            self._redo()

    def _got_history(self, ok: bool, data) -> None:
        cur = getattr(self.ctx, "friends_data", None)
        if cur is None or not getattr(self.ctx, "friends_profile", None):
            return
        new = data if ok and isinstance(data, dict) else {}
        if new != cur.get("history"):
            cur["history"] = new
            self._redo()

    def on_show(self) -> None:
        self.refresh()
        self._poll.start()
        self._anim.start()
        self.ctx.econ.fetch_looks(force=True)

    def on_hide(self) -> None:
        self._poll.stop()
        self._anim.stop()
        if self.ctx.trade.finished():            # 4.0: a trade summary closes when you leave it (not on a rebuild)
            QTimer.singleShot(0, self.ctx.trade.close_if_left)


class ProfileCard(QWidget):
    """The top of a profile: their banner, their picture in its frame, name and tags, online, time played, member since."""

    def __init__(self, ctx, prof: dict, width: int) -> None:
        super().__init__()
        self.ctx, self.prof = ctx, prof
        self.setFixedSize(width, S(132))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._tick = Ticker(self, 60)

    def showEvent(self, _e) -> None:
        self._tick.start()

    def hideEvent(self, _e) -> None:
        self._tick.stop()

    def paintEvent(self, _e) -> None:
        from .cosmetics import paint_banner
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        prof = self.prof
        name = prof.get("username", "?")
        eq = prof.get("equip") or {}
        now = time.monotonic()
        p.setPen(QPen(alpha("#FFFFFF", 0.08), 1))
        p.setBrush(alpha("#FFFFFF", 0.04))
        p.drawRoundedRect(r, S(12), S(12))
        top = QRectF(r.left(), r.top(), r.width(), S(70))
        if eq.get("banner"):
            look = self.ctx.econ.look_of(name)
            gold = int(look.get("gold") or 0) if look.get("banner") == eq["banner"] else 0
            paint_banner(p, top, eq["banner"], now, S(12), 1.0, gold)
        else:                                               # no banner: a soft band in their own colour
            hue = (sum(ord(c) for c in name.lower()) * 37 % 360) / 360
            g = QLinearGradient(top.topLeft(), top.bottomRight())
            g.setColorAt(0, QColor.fromHsvF(hue, 0.35, 0.22))
            g.setColorAt(1, QColor.fromHsvF((hue + 0.12) % 1, 0.35, 0.12))
            path = QPainterPath()
            path.addRoundedRect(top, S(12), S(12))
            p.fillPath(path, g)
        known = prof.get("friend") or prof.get("me")
        face = QRectF(r.left() + S(16), top.bottom() - S(30), S(56), S(56))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#0B0E10"))
        p.drawEllipse(face.adjusted(-S(3), -S(3), S(3), S(3)))
        paint_face(p, face, self.ctx, name, int(prof.get("avatar_v") or 0), bool(prof.get("online")) if known else None,
                   eq.get("frame", ""), now)
        x = face.right() + S(14)
        p.setPen(QColor("#FFFFFF"))
        p.setFont(font(16, QFont.Weight.ExtraBold))
        p.drawText(QRectF(x, top.bottom() - S(30), S(220), S(26)), int(Qt.AlignmentFlag.AlignVCenter), name)
        nx = x + p.fontMetrics().horizontalAdvance(name) + S(8)
        if prof.get("admin"):
            nx += paint_admin_tag(p, nx, top.bottom() - S(17)) + S(5)
        if eq.get("tag"):
            from .cosmetics import paint_tag
            paint_tag(p, nx, top.bottom() - S(17), eq["tag"], now, 9)
        lv = prof.get("level")                              # 4.0: their level badge, on the banner
        if isinstance(lv, dict):
            from .levels import paint_level_badge
            n = int(lv.get("level") or 0)
            c = QPointF(top.right() - S(30), top.top() + S(30))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 110))
            p.drawEllipse(c, S(24), S(24))
            paint_level_badge(p, c, S(38), int(lv.get("badge") or 0), now)
            text = tr("Level {n}", n=n)
            p.setFont(font(9, QFont.Weight.ExtraBold))
            tw = p.fontMetrics().horizontalAdvance(text) + S(12)
            pill = QRectF(c.x() - tw / 2, c.y() + S(20), tw, S(15))
            p.setBrush(QColor(0, 0, 0, 170))
            p.drawRoundedRect(pill, S(7), S(7))
            p.setPen(QColor("#FFE7A8"))
            p.drawText(pill, int(Qt.AlignmentFlag.AlignCenter), text)
        cells = ((tr("Online") if prof.get("online") else (tr("Offline") if known else "—"), tr("Status")),
                 (played_text(int(prof.get("minutes", 0))), tr("Played")), (date_text(prof.get("since")), tr("Member Since")))
        left = face.right() + S(6)
        w = (r.right() - left - S(6)) / 3
        for i, (big, small) in enumerate(cells):
            box = QRectF(left + i * w, top.bottom() + S(8), w, r.bottom() - top.bottom() - S(8))
            p.setPen(QColor("#3DDC84") if (i == 0 and prof.get("online")) else QColor(TEXT))
            p.setFont(font(12.5, QFont.Weight.Bold))
            p.drawText(QRectF(box.left(), box.top() + S(4), box.width(), S(20)), int(Qt.AlignmentFlag.AlignCenter), big)
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(9.5, QFont.Weight.DemiBold))
            p.drawText(QRectF(box.left(), box.top() + S(25), box.width(), S(15)), int(Qt.AlignmentFlag.AlignCenter), small)


class Showcase3(QWidget):
    """Their 3 favourite badges, big (the 3 badges they have on show)."""

    def __init__(self, ctx, items: list, width: int, mine: bool = False) -> None:
        super().__init__()
        self.ctx, self.items, self.mine = ctx, (list(items) + ["", "", ""])[:3], mine
        self.setFixedSize(width, S(96))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._tick = Ticker(self, 60)

    def showEvent(self, _e) -> None:
        self._tick.start()

    def hideEvent(self, _e) -> None:
        self._tick.stop()

    def paintEvent(self, _e) -> None:
        from .collection import badge_label, show_item
        from .econ import RARITY_COLOURS
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        p.setPen(QColor(TEXT_FAINT))
        p.setFont(font(9.5, QFont.Weight.Bold, 0.6))
        p.drawText(QRectF(S(2), 0, self.width(), S(16)), int(Qt.AlignmentFlag.AlignVCenter), tr("SHOWCASE"))
        w = self.width() / 3
        for i, item in enumerate(self.items):
            cell = QRectF(i * w + S(3), S(18), w - S(6), self.height() - S(20))
            if not item:
                p.setPen(QPen(alpha("#FFFFFF", 0.10), 1, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(cell, S(10), S(10))
                p.setPen(QColor(TEXT_FAINT))
                p.setFont(font(9.5, QFont.Weight.DemiBold))
                p.drawText(cell, int(Qt.AlignmentFlag.AlignCenter), tr("Empty"))
                continue
            col = QColor(RARITY_COLOURS.get(self.ctx.econ.rarity(item), "#9AA4AD"))
            g = QLinearGradient(cell.topLeft(), cell.bottomLeft())
            g.setColorAt(0, mix(QColor("#0E1316"), col, 0.25))
            g.setColorAt(1, QColor("#0E1316"))
            p.setPen(QPen(alpha(col, 0.7), 1.2))
            p.setBrush(g)
            p.drawRoundedRect(cell, S(10), S(10))
            d = S(46)
            show_item(p, item, QRectF(cell.center().x() - d / 2, cell.top() + S(6), d, d), now)
            p.setPen(QColor(TEXT))
            p.setFont(font(9, QFont.Weight.DemiBold))
            p.drawText(QRectF(cell.left() + S(4), cell.bottom() - S(20), cell.width() - S(8), S(16)),
                       int(Qt.AlignmentFlag.AlignCenter),
                       p.fontMetrics().elidedText(badge_label(item), Qt.TextElideMode.ElideRight, int(cell.width() - S(8))))


class HistoryList(QWidget):
    """Last trades, cases, spins or bets."""

    def __init__(self, ctx, kind: str, rows: list, width: int) -> None:
        super().__init__()
        self.ctx, self.kind, self.rows = ctx, kind, rows[:30]
        self.row_h = S(30) if kind in ("trades", "cases") else S(24)
        self.setFixedSize(width, int(self.row_h * len(self.rows)))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        from .collection import CASE_NAMES, show_item
        from .wallet import coins_text
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i, row in enumerate(self.rows):
            r = QRectF(0, i * self.row_h, self.width(), self.row_h)
            if i % 2 == 0:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha("#FFFFFF", 0.035))
                p.drawRoundedRect(r.adjusted(0, 1, 0, -1), S(6), S(6))
            p.setPen(QColor(TEXT))
            p.setFont(font(11.5, QFont.Weight.DemiBold))
            right = ""
            colour = TEXT_DIM
            if self.kind == "trades":
                p.drawText(r.adjusted(S(8), 0, 0, 0), int(Qt.AlignmentFlag.AlignVCenter), tr("with {name}", name=row.get("with", "?")))
                x = r.left() + S(120)
                for item in (row.get("gave") or [])[:4]:
                    show_item(p, item, QRectF(x, r.top() + S(6), S(18), S(18)), 0, effects=False)
                    x += S(20)
                p.setPen(QColor(TEXT_DIM))
                p.drawText(QRectF(x + S(2), r.top(), S(20), r.height()), int(Qt.AlignmentFlag.AlignVCenter), "→")
                x += S(22)
                for item in (row.get("got") or [])[:4]:
                    show_item(p, item, QRectF(x, r.top() + S(6), S(18), S(18)), 0, effects=False)
                    x += S(20)
                gave, got = int(row.get("gave_coins") or 0), int(row.get("got_coins") or 0)
                right = (f"−{coins_text(gave)} " if gave else "") + (f"+{coins_text(got)}" if got else "")
            elif self.kind == "cases":
                game = str(row.get("game", ""))
                name = tr(CASE_NAMES.get(game.split(":")[-1], "Case")) if game != "daily" else tr("Daily Case")
                p.drawText(r.adjusted(S(8), 0, 0, 0), int(Qt.AlignmentFlag.AlignVCenter), name)
                if row.get("item"):
                    show_item(p, row["item"], QRectF(r.right() - S(30), r.top() + S(5), S(20), S(20)), 0, effects=False)
                else:
                    right = "+" + coins_text(int(row.get("paid") or 0)) if not row.get("keys") else "+1 " + tr("key")
                    colour = TRADE_GOLD
            elif self.kind == "spins":
                p.drawText(r.adjusted(S(8), 0, 0, 0), int(Qt.AlignmentFlag.AlignVCenter), date_text(row.get("at")))
                right = "+1 " + tr("key") if int(row.get("keys") or 0) else "+" + coins_text(int(row.get("paid") or 0))
                colour = TRADE_GOLD
            else:
                game = str(row.get("game", ""))
                bet, paid = int(row.get("bet") or 0), int(row.get("paid") or 0)
                p.drawText(r.adjusted(S(8), 0, 0, 0), int(Qt.AlignmentFlag.AlignVCenter), tr(GAME_NAMES.get(game, game)))
                p.setPen(QColor(TEXT_DIM))
                p.drawText(QRectF(r.left() + r.width() * 0.4, r.top(), r.width() * 0.25, r.height()),
                           int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), coins_text(bet))
                right = ("+" if paid > bet else "−") + coins_text(abs(paid - bet))
                colour = "#3DDC84" if paid > bet else "#FF5C6C"
            if right:
                p.setPen(QColor(colour))
                p.setFont(font(11.5, QFont.Weight.Bold))
                p.drawText(r.adjusted(0, 0, -S(8), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), right)


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
        from .collection import show_item
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
            show_item(p, item, QRectF(c.x() - g / 2, c.y() - g / 2, g, g), now)
