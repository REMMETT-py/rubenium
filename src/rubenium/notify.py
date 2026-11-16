"""Notifications: a small pop-up and a very quiet beep for things that happen while you play (a trade request,
an item sold, a friend online, the free spin ready...). With the menu open they slide in at the top or bottom
of it; with only the ball showing they slide out from its side. They never take the mouse or the keyboard.
Each kind can be switched off in Settings > Notifications."""
import math
import os
import time

from PyQt6.QtCore import QObject, QPoint, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from . import win
from .core import DATA_DIR, S, TEXT, alpha, font, tr

# kind -> (setting name, colour)
NOTE_KINDS = {"trade": ("Trade requests", "#E8C26A"), "friend": ("Friend requests and friends online", "#3DDC84"),
         "market": ("Market: new items, sales and offers", "#4FC3FF"), "gift": ("Gifts, giveaways and rewards", "#FF5CC8"),
         "ready": ("Free spin, daily case and quests ready", "#B36BFF"), "tips": ("Tips to keep going", "#9AA4AD"),
         "message": ("Messages from friends", "#2EE6D6"), "duel": ("Duel challenges and results", "#FF8A3D")}
DEFAULT = {k: True for k in NOTE_KINDS}


def beep(volume: int) -> None:
    """A soft two-note chime. volume 0-100 (20 = the default, very quiet)."""
    if volume <= 0 or not win.IS_WIN:
        return
    import struct
    import wave
    level = max(1, min(100, int(volume)))
    folder = DATA_DIR / "sounds"
    path = folder / f"notify_{level}_1.wav"
    try:
        if not path.is_file():
            folder.mkdir(parents=True, exist_ok=True)
            rate, frames = 44100, bytearray()
            gain = 0.12 * level / 100
            n = int(rate * 0.34)
            for i in range(n):
                t = i / rate
                v = 0.0
                for f, start, length in ((784.0, 0.0, 0.16), (1046.5, 0.09, 0.24)):
                    if start <= t < start + length:
                        k = (t - start) / length
                        env = min(1.0, (t - start) / 0.01) * math.exp(-5 * k)
                        v += math.sin(2 * math.pi * f * (t - start)) * env
                frames += struct.pack("<h", int(max(-1.0, min(1.0, v * gain)) * 32767))
            tmp = path.with_suffix(".tmp")
            with wave.open(str(tmp), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(rate)
                w.writeframes(bytes(frames))
            os.replace(tmp, path)
        win.play_sound(str(path))
    except OSError:
        pass


class Popup(QWidget):
    """One notification. Click-through: it never gets in the way of a game."""
    W, H = 250, 48

    def __init__(self, title: str, text: str, colour: str) -> None:
        super().__init__()
        self.title, self.text, self.colour = title, text, QColor(colour)
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
                 | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.WindowTransparentForInput)
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(S(self.W), S(self.H))
        self.born = time.monotonic()
        self.finished = False
        self.start, self.end = QPoint(), QPoint()
        self._t = QTimer(self)
        self._t.setInterval(16)
        self._t.timeout.connect(self._step)

    def show_at(self, start: QPoint, end: QPoint) -> None:
        self.start, self.end = start, end
        self.move(start)
        self.setWindowOpacity(0.0)
        self.show()
        self._t.start()

    LIFE = 4.0

    def _step(self) -> None:
        age = time.monotonic() - self.born
        if age > self.LIFE:
            self._t.stop()
            self.finished = True
            self.hide()
            return
        k = min(1.0, age / 0.32)
        k = 1 - (1 - k) ** 3
        out = max(0.0, (age - (self.LIFE - 0.4)) / 0.4)
        self.move(int(self.start.x() + (self.end.x() - self.start.x()) * k),
                  int(self.start.y() + (self.end.y() - self.start.y()) * k))
        self.setWindowOpacity(min(1.0, age / 0.2) * (1 - out))
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(alpha(self.colour, 0.6), 1.2))
        p.setBrush(QColor(10, 13, 15, 245))
        p.drawRoundedRect(r, S(12), S(12))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.colour)
        p.drawRoundedRect(QRectF(r.left() + S(6), r.top() + S(9), S(3), r.height() - S(18)), S(1.5), S(1.5))
        p.setPen(self.colour)
        p.setFont(font(10, QFont.Weight.ExtraBold, 0.4))
        p.drawText(QRectF(r.left() + S(16), r.top() + S(6), r.width() - S(24), S(16)), int(Qt.AlignmentFlag.AlignVCenter),
                   self.title)
        p.setPen(QColor(TEXT))
        p.setFont(font(11.5, QFont.Weight.DemiBold))
        text = p.fontMetrics().elidedText(self.text, Qt.TextElideMode.ElideRight, int(r.width() - S(24)))
        p.drawText(QRectF(r.left() + S(16), r.top() + S(22), r.width() - S(24), S(18)), int(Qt.AlignmentFlag.AlignVCenter),
                   text)


class Notifier(QObject):
    """Watches what the server says (every 20 s) and shows what is new."""

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self.shown: list = []
        self.queue: list = []
        self.seen: dict = {}                        # what was already announced
        self._first = True
        self._last_tip = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._next)
        self._ready = QTimer(self)                  # free spin / daily case / quests: checked every minute
        self._ready.setInterval(60000)
        self._ready.timeout.connect(self._check_ready)
        self._ready.start()
        ctx.econ.live_changed.connect(self.on_live)
        ctx.econ.changed.connect(self._on_econ)
        self._keys = None

    # -- settings
    def on(self, kind: str) -> bool:
        cfg = self.ctx.cfg["notify"] if isinstance(self.ctx.cfg["notify"], dict) else {}
        return bool(cfg.get(kind, True))

    def push(self, kind: str, title: str, text: str) -> None:
        if not self.on(kind) or not self.ctx.online.logged_in():
            return
        self.queue.append((kind, title, text))
        if not self._timer.isActive():
            self._timer.start()

    def _next(self) -> None:
        for w in [w for w in self.shown if w.finished]:
            w.deleteLater()
        self.shown = [w for w in self.shown if not w.finished]
        if not self.queue:
            return self._timer.stop()
        if len(self.shown) >= 3:
            return
        kind, title, text = self.queue.pop(0)
        w = Popup(title, text, NOTE_KINDS[kind][1])
        start, end = self._place(w, len(self.shown))
        w.show_at(start, end)
        self.shown.append(w)
        if self.ctx.cfg["notify_sound"]:
            beep(int(self.ctx.cfg["notify_volume"]))

    def _place(self, w: QWidget, n: int):
        """Open menu: under its top edge (or above its bottom). Ball only: out of its side."""
        win_ = self.ctx.window
        gap = S(6)
        if win_.expanded:
            card = win_.card_global()
            screen = QGuiApplication.screenAt(card.center()) or QGuiApplication.primaryScreen()
            area = screen.availableGeometry()
            x = card.center().x() - w.width() // 2
            if card.top() - area.top() > w.height() * 3 + gap * 3:           # room above the menu
                y = card.top() - (w.height() + gap) * (n + 1)
                return QPoint(x, y + S(16)), QPoint(x, y)
            if area.bottom() - card.bottom() > w.height() * 3 + gap * 3:     # room below
                y = card.bottom() + gap + (w.height() + gap) * n
                return QPoint(x, y - S(16)), QPoint(x, y)
            y = card.top() + S(8) + (w.height() + gap) * n                    # over its top
            return QPoint(x, y - S(16)), QPoint(x, y)
        ball = win_.ball.frameGeometry()
        screen = QGuiApplication.screenAt(ball.center()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        right = ball.center().x() < area.center().x()
        y = min(area.bottom() - w.height(), max(area.top(), ball.center().y() - w.height() // 2 + (w.height() + gap) * n))
        if right:
            x = ball.right() + gap
            return QPoint(x - S(24), y), QPoint(x, y)
        x = ball.left() - gap - w.width()
        return QPoint(x + S(24), y), QPoint(x, y)

    # -- what the server says
    def on_live(self) -> None:
        live = self.ctx.econ.live
        first, self._first = self._first, False
        for ask in live.get("trades") or []:
            if self._new("trade", ask.get("id")) and not first:
                self.push("trade", tr("TRADE REQUEST"), tr("{name} wants to trade with you", name=ask.get("from", "?")))
        asks = int(live.get("asks") or 0)
        if asks > self.seen.get("asks", 0) and not first:
            self.push("friend", tr("FRIEND REQUEST"), tr("Someone wants to be your friend"))
        self.seen["asks"] = asks
        now_on = set(live.get("online") or [])
        before = self.seen.get("online")
        if before is not None:
            for name in sorted(now_on - before)[:3]:
                self.push("friend", tr("ONLINE"), tr("{name} is online", name=name))
        self.seen["online"] = now_on
        newest = live.get("newest") or {}
        if newest.get("id") and self._new("listing", newest["id"]) and not first:
            from .cosmetics import item_name
            self.push("market", tr("MARKET"), tr("New on the market: {what} for {n}", what=item_name(newest.get("item", "")),
                                                 n=newest.get("price", "?")))
        offers = int(live.get("offers") or 0)
        if offers > self.seen.get("offers", 0) and not first:
            self.push("market", tr("MARKET"), tr("New offer for one of your items"))
        self.seen["offers"] = offers
        for g in live.get("giveaways") or []:
            if g.get("state") == "live" and self._new("giveaway", g.get("id")):
                self.push("gift", tr("GIVEAWAY"), tr("Live giveaway: {title}. Open the Giveaway tab!", title=g.get("title", "")))
            if g.get("state") == "done" and self._new("winners", g.get("id")) and not first:
                self.push("gift", tr("GIVEAWAY"), tr("Winners of {title}: {names}", title=g.get("title", ""),
                                                     names=", ".join(g.get("result") or []) or "—"))
        for s in live.get("sales") or []:
            if self._new("sale", s.get("id")) and not first:
                self.push("market", tr("SPECIAL SALE"), tr("{p}% off in the shop for a short time!", p=s.get("pct")))

    def notice(self, kind: str, data: dict) -> None:
        """Messages kept for you by the server (sold, offers, gifts)."""
        from .cosmetics import item_name
        from .wallet import coins_text
        if kind == "sold":
            self.push("market", tr("SOLD"), tr("{what} sold: +{n} coins", what=item_name(data.get("item", "")),
                                               n=coins_text(int(data.get("got") or 0))))
        elif kind == "offer":
            self.push("market", tr("NEW OFFER"), tr("{who} offers {n} for {what}", who=data.get("from", "?"),
                                                    n=coins_text(int(data.get("price") or 0)), what=item_name(data.get("item", ""))))
        elif kind == "bought":
            self.push("market", tr("OFFER ACCEPTED"), tr("You bought {what}", what=item_name(data.get("item", ""))))
        elif kind == "refused":
            self.push("market", tr("OFFER REFUSED"), tr("Your offer for {what} was refused", what=item_name(data.get("item", ""))))
        elif kind == "message":
            self.ctx.msg_unread = int(getattr(self.ctx, "msg_unread", 0) or 0) + 1
            self.push("message", tr("MESSAGE"), f"{data.get('from', '?')}: {data.get('text', '')}")
            if hasattr(self.ctx, "messages_changed"):
                self.ctx.messages_changed(data.get("from"))
        elif kind in ("duel", "duel_yes", "duel_no", "duel_end"):
            from .games2 import DUEL_GAMES
            game, who = tr(DUEL_GAMES.get(data.get("game"), "")), data.get("from") or data.get("other", "?")
            if kind == "duel":
                bet = int(data.get("bet") or 0)
                text = tr("{name} challenges you at {game}", name=who, game=game) + (
                    "  ·  " + tr("Bet {n} coins each", n=coins_text(bet)) if bet else "")
            elif kind == "duel_yes":
                text = tr("{name} accepted your duel: play now!", name=who)
            elif kind == "duel_no":
                text = tr("{name} said no to your duel", name=who)
            elif data.get("draw"):
                text = tr("Duel with {name}: a draw", name=who)
            else:
                text = tr("You won the duel against {name}!", name=who) if data.get("won") else tr("{name} won the duel", name=who)
            self.ctx.duels_data = None
            self.push("duel", tr("DUEL"), text)
        else:
            return False
        return True

    def _new(self, kind: str, ident) -> bool:
        key = f"{kind}:{ident}"
        if key in self.seen:
            return False
        self.seen[key] = True
        return True

    def _on_econ(self) -> None:
        ec = self.ctx.econ
        if self._keys is not None and ec.keys > self._keys and ec.ready:
            self.push("ready", tr("KEY"), tr("+1 key: you can open a case"))
        self._keys = ec.keys if ec.ready else None

    def _check_ready(self) -> None:
        ec, w = self.ctx.econ, self.ctx.wallet
        if not ec.ready:
            return
        wait = w.daily_wait() if hasattr(w, "daily_wait") else None
        if wait == 0 and self._new("spin", int(time.time() // 7200)):
            self.push("ready", tr("FREE SPIN"), tr("Your free spin is ready"))
        if time.monotonic() - self._last_tip > 45 * 60:            # a little push now and then
            self._last_tip = time.monotonic()
            import random
            from .wallet import coins_text
            tips = [tr("New quests every hour: check the Games tab"),
                    tr("Beat Tap pays up to 50 coins a round"),
                    tr("Gold badges are 1 in thousands: keep opening!"),
                    tr("You have {n} coins: maybe a case?", n=coins_text(ec.coins)),
                    tr("Put items you do not wear on the market")]
            self.push("tips", tr("RUBENIUM"), random.choice(tips))


def settings_section(ctx, lay) -> None:
    """Settings > Notifications."""
    from .widgets import SliderRow, Toggle, heading, row
    cfg = ctx.cfg
    lay.addWidget(heading(tr("Notifications")))
    snd = Toggle(bool(cfg["notify_sound"]))

    def sound(v: bool) -> None:
        cfg["notify_sound"] = v
        if v:
            beep(int(cfg["notify_volume"]))
    snd.toggled_by_user.connect(sound)
    lay.addWidget(row(tr("Sound"), snd))
    vol = SliderRow(tr("Sound volume"), 5, 100, int(cfg["notify_volume"]), 5, 20, lambda v: f"{int(v)}%",
                    marks=[5, 20, 40, 60, 80, 100])

    def set_vol(v) -> None:
        cfg["notify_volume"] = int(v)
    vol.changed.connect(set_vol)
    vol.released.connect(lambda v: beep(int(v)))
    lay.addWidget(vol)
    for kind, (label, _c) in NOTE_KINDS.items():
        t = Toggle(ctx.notifier.on(kind))

        def flip(v, k=kind) -> None:
            d = dict(cfg["notify"]) if isinstance(cfg["notify"], dict) else {}
            d[k] = v
            cfg["notify"] = d
        t.toggled_by_user.connect(flip)
        lay.addWidget(row(tr(label), t))
    from .widgets import Button
    b = Button(tr("Show a test notification"), "ghost", 28)
    b.clicked.connect(lambda: ctx.notifier.push("tips", tr("RUBENIUM"), tr("Notifications look like this")))
    lay.addWidget(b)
