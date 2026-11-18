"""Notifications: a small pop-up and a very quiet beep for things that happen while you play (a trade request,
an item sold, a friend online, the free spin ready...). With the menu open they slide in at the top or bottom
of it; with only the ball showing they slide out from its side. They never take the mouse or the keyboard.
Each kind can be switched off in Settings > Notifications.

4.0: a notification can be clicked: its small green button opens what it is about (the trade, the chat, the
coinflip...). They stay above the menus. Every notification is kept: Shop > Notifications lists them all."""
import math
import os
import time

import json

from PyQt6.QtCore import QObject, QPoint, QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from . import win
from .core import DATA_DIR, S, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, mix, sfx, tr, ui

# kind -> (setting name, colour)
NOTE_KINDS = {"trade": ("Trade requests", "#E8C26A"), "friend": ("Friend requests and friends online", "#3DDC84"),
         "market": ("Market: new items, sales and offers", "#4FC3FF"), "gift": ("Gifts, giveaways and rewards", "#FF5CC8"),
         "ready": ("Free spin, daily case and quests ready", "#B36BFF"), "tips": ("Tips to keep going", "#9AA4AD"),
         "message": ("Messages from friends", "#2EE6D6"), "duel": ("Duels: Mini Golf and Coinflip", "#FF8A3D"),
         "level": ("Levels and XP", "#FFE08A"), "admin": ("Rubenium news and safety", "#FF5C5C")}
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
    """One notification. 4.0: clickable (it never takes the keyboard): the green button, or the card itself, opens
    what it is about. It stays above the menus while it shows."""
    W, H = 280, 52
    LIFE = 6.0

    def __init__(self, title: str, text: str, colour: str, action=None, on_go=None) -> None:
        super().__init__()
        self.title, self.text, self.colour = title, text, QColor(colour)
        self.action, self.on_go = action, on_go
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
                 | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(Qt.CursorShape.PointingHandCursor if action else Qt.CursorShape.ArrowCursor)
        self.setFixedSize(S(self.W), S(self.H))
        self.born = time.monotonic()
        self.finished = False
        self.hover = False
        self._paused = 0.0
        self.start, self.end = QPoint(), QPoint()
        self._t = QTimer(self)
        self._t.setInterval(16)
        self._t.timeout.connect(self._step)
        self._raised = 0.0

    def show_at(self, start: QPoint, end: QPoint) -> None:
        self.start, self.end = start, end
        self.move(start)
        self.setWindowOpacity(0.0)
        self.show()
        self._keep_on_top()
        self._t.start()

    def _keep_on_top(self) -> None:
        self.raise_()
        if win.IS_WIN:
            try:
                win.set_topmost(int(self.winId()))
            except Exception:  # noqa: BLE001
                pass

    def enterEvent(self, _e) -> None:
        self.hover = True
        self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = False
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if self.rect().contains(e.position().toPoint()):
            if self.action and self.on_go is not None:
                self.on_go(self.action)
            self.born = min(self.born, time.monotonic() - self.LIFE + 0.35)        # fades out now

    def _step(self) -> None:
        now = time.monotonic()
        if self.hover:                                   # read it calmly: it waits while the mouse is on it
            self.born += 0.016
        age = now - self.born
        if age > self.LIFE:
            self._t.stop()
            self.finished = True
            self.hide()
            return
        if now - self._raised > 0.5:                     # menus never cover it
            self._raised = now
            self._keep_on_top()
        k = min(1.0, age / 0.32)
        k = 1 - (1 - k) ** 3
        out = max(0.0, (age - (self.LIFE - 0.4)) / 0.4)
        self.move(int(self.start.x() + (self.end.x() - self.start.x()) * k),
                  int(self.start.y() + (self.end.y() - self.start.y()) * k))
        self.setWindowOpacity(min(1.0, age / 0.2) * (1 - out))
        self.update()

    def go_rect(self) -> QRectF:
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        return QRectF(r.right() - S(54), r.center().y() - S(12), S(46), S(24))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(alpha(self.colour, 0.9 if self.hover else 0.6), 1.4))
        p.setBrush(QColor(10, 13, 15, 248))
        p.drawRoundedRect(r, S(12), S(12))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.colour)
        p.drawRoundedRect(QRectF(r.left() + S(6), r.top() + S(9), S(3), r.height() - S(18)), S(1.5), S(1.5))
        right = r.width() - S(24) - (S(56) if self.action else 0)
        p.setPen(self.colour)
        p.setFont(font(10, QFont.Weight.ExtraBold, 0.4))
        p.drawText(QRectF(r.left() + S(16), r.top() + S(7), right, S(16)), int(Qt.AlignmentFlag.AlignVCenter), self.title)
        p.setPen(QColor(TEXT))
        p.setFont(font(11.5, QFont.Weight.DemiBold))
        text = p.fontMetrics().elidedText(self.text, Qt.TextElideMode.ElideRight, int(right))
        p.drawText(QRectF(r.left() + S(16), r.top() + S(24), right, S(20)), int(Qt.AlignmentFlag.AlignVCenter), text)
        if self.action:                                   # the small green button
            g = self.go_rect()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#2FC774") if self.hover else QColor("#3DDC84"))
            p.drawRoundedRect(g, g.height() / 2, g.height() / 2)
            p.setPen(QColor("#052A15"))
            p.setFont(font(10, QFont.Weight.ExtraBold))
            p.drawText(g, int(Qt.AlignmentFlag.AlignCenter), tr("See"))          # 4.6: "Go" read as "Avancer"


class Notifier(QObject):
    """Watches what the server says (every few seconds) and shows what is new."""
    history_changed = pyqtSignal()

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self._hist = None
        self._dirty = False
        self._save_t = QTimer(self)
        self._save_t.setSingleShot(True)
        self._save_t.setInterval(1500)
        self._save_t.timeout.connect(self._save)
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
        if not self.ctx.cfg["notify_all"]:
            return False
        cfg = self.ctx.cfg["notify"] if isinstance(self.ctx.cfg["notify"], dict) else {}
        return bool(cfg.get(kind, True))

    # -- the history (kept on this PC: Shop > Notifications)
    def _history_path(self):
        return DATA_DIR / "notifications.json"

    def history(self) -> list:
        if self._hist is None:
            try:
                self._hist = list(json.loads(self._history_path().read_text(encoding="utf-8")))[-400:]
            except (OSError, ValueError, TypeError):
                self._hist = []
        return self._hist

    def _remember(self, kind: str, title: str, text: str, action) -> None:
        h = self.history()
        h.append({"kind": kind, "title": title, "text": text, "action": action, "at": time.time()})
        del h[:-400]
        self._dirty = True
        if not self._save_t.isActive():
            self._save_t.start()

    def _save(self) -> None:
        if not self._dirty:
            return
        self._dirty = False
        try:
            path = self._history_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.history()), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            pass

    def clear_history(self) -> None:
        self._hist = []
        self._dirty = True
        self._save()
        self.history_changed.emit()

    def push(self, kind: str, title: str, text: str, action=None) -> None:
        """Show one notification (if that kind is on) and keep it in the history (always, unless it is only a tip)."""
        if not self.ctx.online.logged_in():
            return
        if kind != "tips":
            self._remember(kind, title, text, action)
            self.history_changed.emit()
        if not self.on(kind):
            return
        self.queue.append((kind, title, text, action))
        if not self._timer.isActive():
            self._timer.start()

    def hold(self, seconds: float) -> None:
        """4.6: nothing pops up for a moment (a coin, a case or a replay is still showing its result)."""
        self.hold_until = max(getattr(self, "hold_until", 0.0), time.monotonic() + seconds)

    def _next(self) -> None:
        for w in [w for w in self.shown if w.finished]:
            w.deleteLater()
        self.shown = [w for w in self.shown if not w.finished]
        if not self.queue:
            return self._timer.stop()
        ec = self.ctx.econ                                       # 4.6: never tell a result before it is shown
        if time.monotonic() < getattr(self, "hold_until", 0.0) or ec.holding or ec.rounds_held():
            return
        if len(self.shown) >= 3:
            return
        kind, title, text, action = self.queue.pop(0)
        w = Popup(title, text, NOTE_KINDS.get(kind, ("", "#9AA4AD"))[1], action, lambda a: go(self.ctx, a))
        start, end = self._place(w, len(self.shown))
        w.show_at(start, end)
        self.shown.append(w)
        if self.ctx.cfg["notify_sound"]:
            beep(int(self.ctx.cfg["notify_volume"]))

    def _place(self, w: QWidget, n: int):
        """Open menu: next to it, never under it (beside the online banner, above or below the small menu).
        Ball only: out of its side."""
        win_ = self.ctx.window
        gap = S(6)
        if win_.expanded:
            card = win_.frameGeometry() if getattr(self.ctx, "online_mode", False) else win_.card_global()
            screen = QGuiApplication.screenAt(card.center()) or QGuiApplication.primaryScreen()
            area = screen.availableGeometry()
            step = w.height() + gap
            if getattr(self.ctx, "online_mode", False):
                y = card.top() + S(80) + step * n
                if area.right() - card.right() > w.width() + gap * 2:          # right of the banner
                    x = card.right() + gap
                    return QPoint(x + S(24), y), QPoint(x, y)
                if card.left() - area.left() > w.width() + gap * 2:             # left of it
                    x = card.left() - gap - w.width()
                    return QPoint(x - S(24), y), QPoint(x, y)
                x = card.right() - w.width() - S(24)                             # over its top right corner, raised
                return QPoint(x, y - S(16)), QPoint(x, y)
            x = card.center().x() - w.width() // 2
            if card.top() - area.top() > step * 3:           # room above the menu
                y = card.top() - step * (n + 1)
                return QPoint(x, y + S(16)), QPoint(x, y)
            if area.bottom() - card.bottom() > step * 3:     # room below
                y = card.bottom() + gap + step * n
                return QPoint(x, y - S(16)), QPoint(x, y)
            x = card.right() + gap if area.right() - card.right() > w.width() + gap else card.left() - gap - w.width()
            y = card.top() + S(40) + step * n
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
                self.push("trade", tr("TRADE REQUEST"), tr("{name} wants to trade with you", name=ask.get("from", "?")),
                          "trade:" + str(ask.get("id")))            # 4.6: See opens the trade itself
        asks = int(live.get("asks") or 0)
        if asks > self.seen.get("asks", 0) and not first:
            self.push("friend", tr("FRIEND REQUEST"), tr("Someone wants to be your friend"), "social")
        self.seen["asks"] = asks
        now_on = set(live.get("online") or [])
        before = self.seen.get("online")
        if before is not None:
            for name in sorted(now_on - before)[:3]:
                self.push("friend", tr("ONLINE"), tr("{name} is online", name=name), "chat:" + name)
        self.seen["online"] = now_on
        newest = live.get("newest") or {}
        if newest.get("id") and self._new("listing", newest["id"]) and not first:
            from .cosmetics import item_name
            self.push("market", tr("MARKET"), tr("New on the market: {what} for {n}", what=item_name(newest.get("item", "")),
                                                 n=newest.get("price", "?")), "market")
        offers = int(live.get("offers") or 0)
        if offers > self.seen.get("offers", 0) and not first:
            self.push("market", tr("MARKET"), tr("New offer for one of your items"), "market")
        self.seen["offers"] = offers
        for g in live.get("giveaways") or []:
            if g.get("state") == "live" and self._new("giveaway", g.get("id")):
                self.push("gift", tr("GIVEAWAY"), tr("Live giveaway: {title}. Open the Giveaway tab!", title=g.get("title", "")), "giveaway")
            if g.get("state") == "done" and self._new("winners", g.get("id")) and not first:
                self.push("gift", tr("GIVEAWAY"), tr("Winners of {title}: {names}", title=g.get("title", ""),
                                                     names=", ".join(g.get("result") or []) or "—"), "giveaway")
        for s in live.get("sales") or []:
            if self._new("sale", s.get("id")) and not first:
                self.push("market", tr("SPECIAL SALE"), tr("{p}% off in the shop for a short time!", p=s.get("pct")), "shop")

    def notice(self, kind: str, data: dict) -> None:
        """Messages kept for you by the server (sold, offers, gifts)."""
        from .cosmetics import item_name
        from .wallet import coins_text
        if kind == "sold":
            self.push("market", tr("SOLD"), tr("{what} sold: +{n} coins", what=item_name(data.get("item", "")),
                                               n=coins_text(int(data.get("got") or 0))), "market")
        elif kind == "offer":
            self.push("market", tr("NEW OFFER"), tr("{who} offers {n} for {what}", who=data.get("from", "?"),
                                                    n=coins_text(int(data.get("price") or 0)), what=item_name(data.get("item", ""))), "market")
        elif kind == "bought":
            self.push("market", tr("OFFER ACCEPTED"), tr("You bought {what}", what=item_name(data.get("item", ""))), "inventory")
        elif kind == "refused":
            self.push("market", tr("OFFER REFUSED"), tr("Your offer for {what} was refused", what=item_name(data.get("item", ""))), "market")
        elif kind == "message":
            self.ctx.msg_unread = int(getattr(self.ctx, "msg_unread", 0) or 0) + 1
            self.push("message", tr("MESSAGE"), f"{data.get('from', '?')}: {data.get('text', '')}", "chat:" + str(data.get("from", "")))
            if hasattr(self.ctx, "messages_changed"):
                self.ctx.messages_changed(data.get("from"))
        elif kind in ("golf", "golf_yes", "golf_no", "golf_end"):
            who = data.get("from") or data.get("other", "?")
            if kind == "golf":
                bet = int(data.get("bet") or 0)
                text = tr("{name} challenges you to Mini Golf", name=who) + (
                    "  ·  " + tr("Bet {n} coins each", n=coins_text(bet)) if bet else "")
            elif kind == "golf_yes":
                text = tr("{name} joined your Mini Golf match: it starts now!", name=who)
            elif kind == "golf_no":
                text = tr("{name} declined your Mini Golf match", name=who)
            elif data.get("draw"):
                text = tr("Mini Golf with {name}: a draw", name=who)
            else:
                text = tr("You beat {name} at Mini Golf!", name=who) if data.get("won") else tr("{name} won the Mini Golf match", name=who)
            self.ctx.golf_lobby = None
            self.push("duel", tr("MINI GOLF"), text, "golf")
            if kind in ("golf", "golf_yes") and self.ctx.window.showing("games") and \
                    getattr(self.ctx, "games_sub", None) == "duels" and not getattr(self.ctx, "golf_id", None):
                from .golf import load_golf
                page = (self.ctx.window.pages.get("games") or (None, None))[1]
                if page is not None:
                    load_golf(page)
        elif kind in ("wave_yes", "wave_end"):                     # 4.3: Wave Rush duels
            who = data.get("from") or data.get("other", "?")
            if kind == "wave_yes":
                text = tr("{name} joined your Wave Rush duel: it starts now!", name=who)
            elif data.get("draw"):
                text = tr("Wave Rush with {name}: a draw", name=who)
            else:
                text = tr("You beat {name} at Wave Rush!", name=who) if data.get("won") else tr("{name} won the Wave Rush duel", name=who)
            self.ctx.wave_lobby = None
            if kind == "wave_end" and self.ctx.window.showing("games") and getattr(self.ctx, "wave_duel", None) == data.get("id"):
                self._remember("duel", tr("WAVE RUSH"), text, "wave")      # 4.6: on screen already: no pop-up
                self.history_changed.emit()
            else:
                self.push("duel", tr("WAVE RUSH"), text, "wave")
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
            self.push("duel", tr("DUEL"), text, "minigames")
        elif kind in ("flip_join", "flip_locked", "flip_end"):         # 3.2: coinflip
            who = data.get("from", "?")
            if kind == "flip_join":
                text = tr("{name} joined your coinflip and is choosing items", name=who)
            elif kind == "flip_locked":
                text = (tr("A bot locked in: your coinflip flips in 15 seconds!") if data.get("bot") else
                        tr("{name} locked in: your coinflip flips in 15 seconds!", name=who))
            else:
                text = (tr("You won the coinflip: +{n} in items!", n=coins_text(int(data.get("value") or 0))) if data.get("won")
                        else tr("You lost the coinflip"))
                self.ctx.econ.refresh()
            self.ctx.flip_data = None
            if kind != "flip_end" and data.get("id"):
                self.ctx.flip_id = data["id"]
            if kind == "flip_end" and self.ctx.window.showing("games") and getattr(self.ctx, "games_sub", "") == "flip":
                self.hold(6.5)                                   # 4.6: after the coin has landed, not before
            self.push("duel", tr("COINFLIP"), text, "flip")
        elif kind == "level_up":                                       # 4.0
            lvl, old = int(data.get("level") or 0), int(data.get("from") or 0)
            self.ctx.econ.fetch_xp()
            if lvl > int(self.ctx.cfg["level_seen"]):
                self.ctx.cfg["level_seen"] = lvl
                from .levels import play_level_up
                try:
                    play_level_up(self.ctx, lvl, old)
                except Exception:  # noqa: BLE001
                    pass
            self.push("level", tr("LEVEL UP"), tr("You reached level {n}!", n=lvl), "levels")
        elif kind == "og_coupon":
            self.push("level", tr("OG REWARD"), tr("A free XP coupon for our OG players is in your Inventory"), "levels")
            if hasattr(self.ctx, "offer_og_coupon"):
                QTimer.singleShot(1500, self.ctx.offer_og_coupon)
        elif kind == "listing_back":
            self.push("market", tr("MARKET"), tr("{what} came back to your inventory: prices were updated, list it again "
                                                  "when you like", what=item_name(data.get("item", ""))), "inventory")
        elif kind == "cancelled":
            what = {"coinflip": tr("Coinflip"), "golf": tr("Mini Golf")}.get(data.get("what"), tr("A game"))
            self.push("admin", tr("STOPPED"), tr("{what} was stopped for a moment: nobody won or lost, everything came back",
                                                 what=what), None)
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
            self.push("ready", tr("KEY"), tr("+1 key: you can open a case"), "cases")
        self._keys = ec.keys if ec.ready else None

    def _check_ready(self) -> None:
        ec, w = self.ctx.econ, self.ctx.wallet
        if not ec.ready:
            return
        wait = w.daily_wait() if hasattr(w, "daily_wait") else None
        if wait == 0 and self._new("spin", int(time.time() // 7200)):
            self.push("ready", tr("FREE SPIN"), tr("Your free spin is ready"), "spin")
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


def go(ctx, action) -> None:
    """Open what a notification is about (its green button, or a line in the history)."""
    if not action:
        return
    action = str(action)
    key, _, arg = action.partition(":")
    for flag in ("quests_open", "mini_open", "park_open"):
        setattr(ctx, flag, False)
    target = "friends"
    if key == "social":
        ctx.social_tab, ctx.friends_profile, ctx.social_edit = 0, None, False
    elif key == "chat":
        ctx.social_tab, ctx.friends_profile, ctx.social_edit = 2, None, False
        ctx.chat_with = arg or None
    elif key == "trade":                                       # 4.6: accept (when asked) and open the trade
        ctx.friends_profile = None
        if arg:
            def open_it() -> None:
                if ctx.trade.trade_id == arg:
                    return
                ctx.econ.call("rb_trade_accept", {"trade": arg},
                              lambda ok, d: (ctx.trade.open(arg), ctx.window.reload_page("friends")) if ok or "rb_trade_gone" not in str(d)
                              else ctx.toast(tr(str(d)), "warn"))
            QTimer.singleShot(300 if getattr(ctx, "online_mode", False) else 1800, open_it)
    elif key in ("market", "inventory", "shop", "cases", "levels", "notifications"):
        target = "themes"
        ctx.shop_tab = {"market": 4, "inventory": 5, "shop": 1, "cases": 3, "levels": 5, "notifications": 0}[key]
        if key == "levels":
            ctx.inv_tab = "levels"
    elif key in ("golf", "flip", "advent", "minigames", "wave"):
        target = "games"
        ctx.casino = False
        ctx.games_sub = {"golf": "duels", "flip": "flip", "advent": "advent", "minigames": "minigames", "wave": "wave"}[key]
        if key == "wave":
            ctx.wave_mode = "duel"
    elif key == "spin":
        target = "games"
        from .games import GamesPage
        ctx.casino_pick = GamesPage.NAMES.index("Free spin")
        ctx.casino = True
    elif key == "giveaway":
        target = "giveaway"
    elif key == "daily":                                   # 4.4: the daily reward, in the Games half
        target = "games"
        from .hub import check_login_reward
        QTimer.singleShot(1500 if not getattr(ctx, "online_mode", False) else 200,
                          lambda: check_login_reward(ctx, force=True))
    sfx.play("pick")
    if getattr(ctx, "online_mode", False):
        ctx.window.goto(target)
        ctx.window.reload_page(target)
        if key == "chat" and arg:
            from .hub import open_chat
            QTimer.singleShot(150, lambda: open_chat(ctx, arg))
    else:
        ctx.enter_online(target)
        if key == "chat" and arg:
            from .hub import open_chat
            QTimer.singleShot(1800, lambda: open_chat(ctx, arg))


class NoticeRow(QWidget):
    """One line of Shop > Notifications."""

    def __init__(self, ctx, item: dict, width: int) -> None:
        super().__init__()
        self.ctx, self.item = ctx, item
        self.hover = False
        self.colour = QColor(NOTE_KINDS.get(item.get("kind"), ("", "#9AA4AD"))[1])
        self.setFixedWidth(width)
        f = font(11, QFont.Weight.DemiBold)
        from PyQt6.QtGui import QFontMetrics
        fm = QFontMetrics(f)
        self._text_w = width - S(22) - (S(54) if item.get("action") else S(8))
        lines = fm.boundingRect(0, 0, self._text_w, 2000, int(Qt.TextFlag.TextWordWrap), item.get("text", "")).height()
        self.setFixedHeight(int(S(26) + lines + S(8)))
        if item.get("action"):
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, _e) -> None:
        self.hover = True
        self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = False
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if self.item.get("action") and self.rect().contains(e.position().toPoint()):
            go(self.ctx, self.item["action"])

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 1.5, -0.5, -1.5)
        p.setPen(QPen(alpha(self.colour, 0.45 if self.hover else 0.18), 1))
        p.setBrush(alpha("#FFFFFF", 0.05 if self.hover else 0.025))
        p.drawRoundedRect(r, S(9), S(9))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.colour)
        p.drawRoundedRect(QRectF(r.left() + S(5), r.top() + S(7), S(3), r.height() - S(14)), S(1.5), S(1.5))
        p.setPen(self.colour)
        p.setFont(font(9.5, QFont.Weight.ExtraBold, 0.3))
        p.drawText(QRectF(r.left() + S(14), r.top() + S(5), r.width() * 0.6, S(16)), int(Qt.AlignmentFlag.AlignVCenter),
                   self.item.get("title", ""))
        p.setPen(QColor(TEXT_FAINT))
        p.setFont(font(9, QFont.Weight.DemiBold))
        p.drawText(QRectF(r.left(), r.top() + S(5), r.width() - S(10), S(16)),
                   int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), _ago(self.item.get("at") or 0))
        p.setPen(QColor(TEXT))
        p.setFont(font(11, QFont.Weight.DemiBold))
        p.drawText(QRectF(r.left() + S(14), r.top() + S(22), self._text_w, r.height() - S(26)),
                   int(Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), self.item.get("text", ""))
        if self.item.get("action"):
            g = QRectF(r.right() - S(48), r.center().y() - S(10) + S(6), S(40), S(20))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#2FC774") if self.hover else QColor("#3DDC84"))
            p.drawRoundedRect(g, g.height() / 2, g.height() / 2)
            p.setPen(QColor("#052A15"))
            p.setFont(font(9.5, QFont.Weight.ExtraBold))
            p.drawText(g, int(Qt.AlignmentFlag.AlignCenter), tr("See"))          # 4.6: "Go" read as "Avancer"


def _ago(t: float) -> str:
    d = max(0, int(time.time() - float(t)))
    if d < 60:
        return tr("now")
    if d < 3600:
        return tr("{n} min", n=d // 60)
    if d < 86400:
        return tr("{n} h", n=d // 3600)
    return time.strftime("%d/%m", time.localtime(float(t)))


class MasterSwitch(QWidget):
    """All notifications on or off: a bright outline when on, a dark one when off."""

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self.setFixedHeight(S(40))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if self.rect().contains(e.position().toPoint()):
            self.ctx.cfg["notify_all"] = not self.ctx.cfg["notify_all"]
            sfx.play("on" if self.ctx.cfg["notify_all"] else "off")
            self.update()

    def paintEvent(self, _e) -> None:
        from .widgets import draw_icon
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = bool(self.ctx.cfg["notify_all"])
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(mix(ui.accent, QColor("#FFFFFF"), 0.35) if on else QColor("#2A3036"), S(2) if on else S(1.2)))
        p.setBrush(alpha(ui.accent, 0.12) if on else alpha("#000000", 0.25))
        p.drawRoundedRect(r, S(11), S(11))
        p.save()
        p.translate(r.left() + S(22), r.center().y())
        p.scale(S(16) / 20, S(16) / 20)
        draw_icon(p, "bell", ui.accent if on else QColor(TEXT_FAINT))
        p.restore()
        p.setPen(QColor(TEXT) if on else QColor(TEXT_DIM))
        p.setFont(font(12, QFont.Weight.Bold))
        p.drawText(r.adjusted(S(42), 0, 0, 0), int(Qt.AlignmentFlag.AlignVCenter),
                   tr("Notifications on") if on else tr("Notifications off"))
        p.setPen(QColor(TEXT_FAINT))
        p.setFont(font(10, QFont.Weight.DemiBold))
        p.drawText(r.adjusted(0, 0, -S(12), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                   tr("Click to turn off") if on else tr("Click to turn on"))


def build_history(page, lay) -> None:
    """Shop > Notifications: every notification received, newest first, grouped by day."""
    from .widgets import Button, Label, heading, hbox
    ctx = page.ctx
    top = hbox(spacing=6)
    top.addWidget(MasterSwitch(ctx), 1)
    clear = Button(tr("Clear"), "ghost", 40)
    clear.setFixedWidth(S(80))
    clear.clicked.connect(lambda: ctx.window.confirm(tr("Clear the whole list?"), lambda: (ctx.notifier.clear_history(),
                                                                                           ctx.reload_page()), yes=tr("Clear")))
    top.addWidget(clear)
    lay.addLayout(top)
    items = list(reversed(ctx.notifier.history()))
    if not items:
        return lay.addWidget(Label(tr("Nothing yet."), 11,
                                   TEXT_DIM, wrap_w=page.W))
    day0 = time.localtime()
    last = None
    for it in items[:200]:
        t = time.localtime(float(it.get("at") or 0))
        if (t.tm_year, t.tm_yday) == (day0.tm_year, day0.tm_yday):
            label = tr("Today")
        elif (t.tm_year, t.tm_yday) == (day0.tm_year, day0.tm_yday - 1):
            label = tr("Yesterday")
        else:
            label = time.strftime("%d/%m/%Y", t)
        if label != last:
            lay.addWidget(heading(label))
            last = label
        lay.addWidget(NoticeRow(ctx, it, page.W))


class KindRow(QWidget):
    """Settings > Notifications: one kind, on (bright outline) or off (dark outline)."""

    def __init__(self, ctx, kind: str) -> None:
        super().__init__()
        self.ctx, self.kind = ctx, kind
        self.setFixedHeight(S(34))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def is_on(self) -> bool:
        d = self.ctx.cfg["notify"] if isinstance(self.ctx.cfg["notify"], dict) else {}
        return bool(d.get(self.kind, True))

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if self.rect().contains(e.position().toPoint()):
            d = dict(self.ctx.cfg["notify"]) if isinstance(self.ctx.cfg["notify"], dict) else {}
            d[self.kind] = not self.is_on()
            self.ctx.cfg["notify"] = d
            sfx.play("on" if d[self.kind] else "off")
            self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.is_on() and bool(self.ctx.cfg["notify_all"])
        col = QColor(NOTE_KINDS[self.kind][1])
        r = QRectF(self.rect()).adjusted(1, 2, -1, -2)
        p.setPen(QPen(mix(col, QColor("#FFFFFF"), 0.25) if on else QColor("#262B30"), S(1.6) if on else 1))
        p.setBrush(alpha(col, 0.10) if on else alpha("#000000", 0.25))
        p.drawRoundedRect(r, S(9), S(9))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col if on else alpha(col, 0.3))
        p.drawEllipse(QPointF(r.left() + S(14), r.center().y()), S(4), S(4))
        p.setPen(QColor(TEXT) if on else QColor(TEXT_FAINT))
        p.setFont(font(11, QFont.Weight.DemiBold))
        p.drawText(r.adjusted(S(26), 0, -S(50), 0), int(Qt.AlignmentFlag.AlignVCenter), tr(NOTE_KINDS[self.kind][0]))
        p.setPen(QColor("#3DDC84") if on else QColor(TEXT_FAINT))
        p.setFont(font(9.5, QFont.Weight.ExtraBold))
        p.drawText(r.adjusted(0, 0, -S(10), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                   tr("ON") if on else tr("OFF"))


def settings_section(ctx, lay) -> None:
    """Settings > Notifications."""
    from .widgets import Button, SliderRow, Toggle, heading, row
    cfg = ctx.cfg
    lay.addWidget(heading(tr("Notifications")))
    lay.addWidget(MasterSwitch(ctx))
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
    for kind in NOTE_KINDS:
        lay.addWidget(KindRow(ctx, kind))
    b = Button(tr("Show a test notification"), "ghost", 28)
    b.clicked.connect(lambda: ctx.notifier.push("tips", tr("RUBENIUM"), tr("Notifications look like this"), "notifications"))
    lay.addWidget(b)
