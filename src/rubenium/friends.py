"""Social tab: your own stats and picture at the top, every Rubenium player (add them in one click), friends
online, profiles with badges and history, trade requests and the trade screen. Everything refreshes by itself."""
import base64
import time

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

from .bazaar import AskDialog, build_trade
from .core import DATA_DIR, S, sfx, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, lang, tr, ui
from .pages import Page
from .widgets import Button, IconButton, Label, Segmented, hbox, heading, vbox

GAME_NAMES = {"slots": "Slots", "plinko": "Plinko", "dice": "Dice", "mines": "Bombs", "rocket": "Rocket",
              "blackjack": "Blackjack", "daily": "Daily case", "spin": "Free spin", "mini": "Beat Tap"}
ADMIN_COLOUR = "#FF4B6E"


def played_text(minutes: int) -> str:
    text = f"{minutes / 60:.1f}"
    return (text.replace(".", ",") if lang() == "fr" else text) + " h"


def date_text(stamp) -> str:
    day = str(stamp or "")[:10]
    if len(day) == 10 and lang() == "fr":
        return f"{day[8:10]}/{day[5:7]}/{day[0:4]}"
    return day


# --------------------------------------------------------------------------- #
# Profile pictures: small JPEGs, kept in memory and on disk, asked for again only when they change
# --------------------------------------------------------------------------- #
class Faces:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.pix: dict = {}                       # lower name -> (version, QPixmap or None)
        self._asking: set = set()
        self.folder = DATA_DIR / "faces"

    def get(self, name: str, version: int):
        key = (name or "").lower()
        have = self.pix.get(key)
        if have is not None and have[0] == version:
            return have[1]
        if not version:
            self.pix[key] = (0, None)
            return None
        disk = self.folder / f"{key}_{version}.jpg"
        if disk.is_file():
            pm = QPixmap(str(disk))
            self.pix[key] = (version, pm if not pm.isNull() else None)
            try:
                disk.touch()
            except OSError:
                pass
            return self.pix[key][1]
        self._fetch(key)
        return have[1] if have else None

    def _fetch(self, key: str) -> None:
        if key in self._asking or not self.ctx.online.logged_in():
            return
        self._asking.add(key)
        QTimer.singleShot(150, self._send)

    def _send(self) -> None:
        names = sorted(self._asking)[:40]
        if not names:
            return

        def got(ok: bool, data) -> None:
            self._asking.difference_update(names)
            if not ok or not isinstance(data, dict):
                return
            self.folder.mkdir(parents=True, exist_ok=True)
            for name in names:
                info = data.get(name)
                if not info:
                    self.pix[name] = (-1, None)
                    continue
                try:
                    raw = base64.b64decode(info.get("data") or "")
                    img = QImage.fromData(raw, "JPG")
                    if img.isNull() or img.width() > 256 or img.height() > 256:
                        continue
                    v = int(info.get("v") or 0)
                    for old in self.folder.glob(f"{name}_*.jpg"):
                        old.unlink(missing_ok=True)
                    (self.folder / f"{name}_{v}.jpg").write_bytes(raw)
                    self.pix[name] = (v, QPixmap.fromImage(img))
                except (ValueError, OSError):
                    continue
            self.ctx.faces_changed()
        self.ctx.online.ask("rb_avatars_get", {"names": names}, got)

    def upload(self, path: str, done) -> None:
        img = QImage(path)
        if img.isNull():
            return done(False, tr("This picture cannot be used"))
        side = min(img.width(), img.height())
        img = img.copy((img.width() - side) // 2, (img.height() - side) // 2, side, side).scaled(
            96, 96, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        buf = QByteArray()
        dev = QBuffer(buf)
        dev.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(dev, "JPG", 82)
        text = base64.b64encode(bytes(buf)).decode()
        me = self.ctx.online.username().lower()

        def back(ok: bool, data) -> None:
            if ok:
                self.pix[me] = (int(data or 0), QPixmap.fromImage(img))
            done(ok, data)
        self.ctx.econ.call("rb_avatar_set", {"picture": text}, back)


def paint_face(p: QPainter, rect: QRectF, ctx, name: str, version: int, online=None) -> None:
    """A round profile picture (or the first letter), with a small online dot."""
    pm = ctx.faces.get(name, version) if version else None
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


class PlayerRow(QWidget):
    """One player: picture, name (and ADMIN), hours, their three badges, and a button."""
    opened = pyqtSignal(str)

    def __init__(self, page, info: dict) -> None:
        super().__init__()
        self.page, self.ctx, self.info = page, page.ctx, info
        self.setFixedHeight(S(46))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
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
        if info.get("admin"):
            nx += paint_admin_tag(p, nx, r.top() + S(13)) + S(6)
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
            sub += "  ·  " + (tr("Online") if info.get("online") else tr("Offline"))
        p.drawText(QRectF(x, r.top() + S(22), S(200), S(16)), int(Qt.AlignmentFlag.AlignVCenter), sub)


class StatsCard(QWidget):
    """Your picture, name, ADMIN tag and stats: the top of the Social tab."""
    picture = pyqtSignal()

    def __init__(self, ctx, data: dict, width: int) -> None:
        super().__init__()
        self.ctx, self.data = ctx, data
        self.setFixedSize(width, S(150))
        self.setMouseTracking(True)

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
        paint_face(p, self._face(), self.ctx, name, int(d.get("avatar_v") or self.ctx.econ.avatar_v or 0))
        p.setPen(QColor(TEXT))
        p.setFont(font(16, QFont.Weight.Bold))
        p.drawText(QRectF(S(76), S(14), S(200), S(24)), int(Qt.AlignmentFlag.AlignVCenter), name)
        nx = S(76) + p.fontMetrics().horizontalAdvance(name) + S(8)
        if d.get("admin"):
            paint_admin_tag(p, nx, S(26))
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(S(76), S(38), r.width() - S(90), S(18)), int(Qt.AlignmentFlag.AlignVCenter),
                   tr("{h} played · member since {d}", h=played_text(int(d.get("minutes") or 0)), d=date_text(d.get("since"))))
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
        yes, no = Button(tr("Open trade"), "primary", 28), Button(tr("Decline"), "ghost", 28)
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
        self._build()

    def _redo(self) -> None:
        if self.ctx.window.current == "friends" and self.ctx.window.expanded:
            self.ctx.reload_page()

    def _build(self) -> None:
        ctx = self.ctx
        if ctx.trade.trade_id:
            return build_trade(self, self.lay)
        who = getattr(ctx, "friends_profile", None)
        if who:
            return self._profile(who)
        if not ctx.online.logged_in():
            return self.lay.addWidget(Label(tr("Log in to see other players"), 12, TEXT_DIM))
        me = getattr(ctx, "social_me", None) or {}
        card = StatsCard(ctx, me, self.W)
        card.picture.connect(self._picture)
        self.lay.addWidget(card)
        line = hbox(spacing=6)
        rename = Button(tr("Change name"), "ghost", 28)
        rename.clicked.connect(self._rename)
        again = Button(tr("Refresh"), "ghost", 28, icon="refresh")
        again.clicked.connect(self._refresh_all)
        line.addWidget(rename, 1)
        line.addWidget(again, 1)
        self.lay.addLayout(line)
        live = ctx.econ.live
        if live.get("open_trade") and not ctx.trade.trade_id:
            b = Button(tr("Back to your trade"), "primary", 32)
            b.clicked.connect(lambda: self.open_trade(live["open_trade"]))
            self.lay.addWidget(b)
        for ask in live.get("trades") or []:
            self.lay.addWidget(TradeAsk(self, ask))
        tab = int(getattr(ctx, "social_tab", 0) or 0)
        seg = Segmented([tr("Friends"), tr("All players")], tab)

        def switch(i: int) -> None:
            ctx.social_tab = i
            ctx.reload_page()
        seg.changed.connect(switch)
        self.lay.addWidget(seg)
        if tab == 1:
            rows = getattr(ctx, "users_cache", None)
            if rows is None:
                return self.lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
            self.lay.addWidget(Label(tr("{n} players. Click one to see their profile.", n=len(rows)), 10.5, TEXT_DIM))
            for info in rows:
                self.lay.addWidget(PlayerRow(self, info))
            return
        if self.friends is None:
            return self.lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
        if not self.friends:
            return self.lay.addWidget(Label(tr("No friends yet. Open All players and add someone."), 12, TEXT_DIM,
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
                    self.lay.addWidget(PlayerRow(self, info))

    # -- server
    def refresh(self) -> None:
        ctx = self.ctx
        if not ctx.online.logged_in() or ctx.trade.trade_id:
            return
        if getattr(ctx, "friends_profile", None):
            return ctx.online.ask("rb_profile", {"name": ctx.friends_profile}, self._got_profile_again)
        ctx.online.ask("rb_social", {}, self._got_me)
        if int(getattr(ctx, "social_tab", 0) or 0) == 1:
            ctx.online.ask("rb_users", {"search": "", "page": 0}, self._got_users)
        else:
            ctx.online.ask("rb_friends_list", {}, self._listed)

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

    def _refresh_all(self) -> None:
        sfx.play("pick")
        self.ctx.econ.refresh()
        self.ctx.econ.poll_live()
        self.ctx.online._tick()
        self.refresh()
        self.ctx.toast(tr("Refreshed"))

    def _picture(self) -> None:
        path = self.ctx.pick_file(tr("Choose a picture"), "Pictures (*.png *.jpg *.jpeg)")
        if not path:
            return

        def done(ok: bool, data) -> None:
            if not ok:
                return self.ctx.toast(tr(str(data)), "warn")
            sfx.play("on")
            self.ctx.econ.avatar_v = int(data or 0)
            if isinstance(getattr(self.ctx, "social_me", None), dict):
                self.ctx.social_me["avatar_v"] = int(data or 0)
            self.ctx.toast(tr("Picture changed: everyone can see it"))
            self._redo()
        self.ctx.faces.upload(path, done)

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
        self._dialog = AskDialog(self.ctx, tr("Change name"), tr("New username"), tr("Next"), send, 10,
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
        again = IconButton("refresh", 30, tip=tr("Refresh"))
        again.clicked.connect(lambda: (setattr(ctx, "friends_data", None), ctx.reload_page()))
        top.addWidget(again)
        self.lay.addLayout(top)
        if data is None:
            self.lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
            return ctx.online.ask("rb_profile", {"name": name}, self._got_profile)
        prof, hist = data.get("profile") or {}, data.get("history")
        self.lay.addWidget(ProfileCard(ctx, prof))
        line = hbox(spacing=6)
        if not prof.get("me"):
            state = prof.get("state")
            if prof.get("friend"):
                rm = Button(tr("Remove friend"), "ghost", 30)
                rm.clicked.connect(lambda: ctx.window.confirm(tr("Remove {name} from your friends?", name=name),
                                   lambda: self.act("rb_friend_remove", name, lambda _ok: self.open_profile(None)),
                                   yes=tr("Remove")))
                line.addWidget(rm, 1)
            elif state == "asks":
                b = Button(tr("Accept friend"), "primary", 30)
                b.clicked.connect(lambda: self.act("rb_friend_add", name, lambda _ok: self.open_profile(name)))
                line.addWidget(b, 1)
            elif state != "asked":
                b = Button(tr("Add friend"), "primary", 30)
                b.clicked.connect(lambda: self.act("rb_friend_add", name, lambda _ok: self.open_profile(name)))
                line.addWidget(b, 1)
            trade = Button(tr("Trade"), "primary" if prof.get("can_trade") else "ghost", 30)
            trade.setToolTip(tr("Both players need 5 hours with Rubenium"))
            trade.clicked.connect(lambda: self.ask_trade(name))
            line.addWidget(trade, 1)
        self.lay.addLayout(line)
        badges = list(prof.get("badges") or [])
        self.lay.addWidget(heading(tr("Badges") + f"  ·  {len(badges)}"))
        if badges:
            worn_now = [(prof.get("equip") or {}).get(k) for k in ("badge1", "badge2", "badge3")]
            self.lay.addWidget(BadgeStrip(ctx, badges, [w for w in worn_now if w], self.W))
        else:
            self.lay.addWidget(Label(tr("No badges yet"), 12, TEXT_DIM))
        if prof.get("stats") is None:
            self.lay.addWidget(Label(tr("Become friends to see their history."), 11.5, TEXT_DIM, wrap_w=self.W))
            return
        if hist is None:
            return self.lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
        for key, title in (("trades", tr("Last 3 trades")), ("cases", tr("Last 3 cases")), ("spins", tr("Last 3 spins")),
                           ("bets", tr("Last 30 bets"))):
            rows = hist.get(key) or []
            self.lay.addWidget(heading(title))
            if not rows:
                self.lay.addWidget(Label(tr("Nothing yet"), 11, TEXT_FAINT))
            else:
                self.lay.addWidget(HistoryList(ctx, key, rows, self.W))

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

    def on_hide(self) -> None:
        self._poll.stop()


class ProfileCard(QWidget):
    """Picture, online or not, time played, member since."""

    def __init__(self, ctx, prof: dict) -> None:
        super().__init__()
        self.ctx, self.prof = ctx, prof
        self.setFixedHeight(S(64))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha("#FFFFFF", 0.08), 1))
        p.setBrush(alpha("#FFFFFF", 0.04))
        p.drawRoundedRect(r, S(11), S(11))
        prof = self.prof
        known = prof.get("friend") or prof.get("me")
        paint_face(p, QRectF(r.left() + S(10), r.center().y() - S(21), S(42), S(42)), self.ctx,
                   prof.get("username", "?"), int(prof.get("avatar_v") or 0), bool(prof.get("online")) if known else None)
        if prof.get("admin"):
            paint_admin_tag(p, r.left() + S(10), r.bottom() - S(6))
        cells = ((tr("Online") if prof.get("online") else (tr("Offline") if known else "—"), tr("Status")),
                 (played_text(int(prof.get("minutes", 0))), tr("Played")), (date_text(prof.get("since")), tr("Member since")))
        left = r.left() + S(60)
        w = (r.right() - left) / 3
        for i, (big, small) in enumerate(cells):
            box = QRectF(left + i * w, r.top(), w, r.height())
            p.setPen(QColor("#3DDC84") if (i == 0 and prof.get("online")) else QColor(TEXT))
            p.setFont(font(13, QFont.Weight.Bold))
            p.drawText(QRectF(box.left(), box.top() + S(11), box.width(), S(22)), int(Qt.AlignmentFlag.AlignCenter), big)
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(10, QFont.Weight.DemiBold))
            p.drawText(QRectF(box.left(), box.top() + S(34), box.width(), S(16)), int(Qt.AlignmentFlag.AlignCenter), small)


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
                name = tr(CASE_NAMES.get(game.split(":")[-1], "Case")) if game != "daily" else tr("Daily case")
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
