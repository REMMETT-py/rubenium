"""3.2: ONLINE mode.

The menu bar has one ONLINE button instead of Games, Shop and Social. Pressing it folds the menu into the ball, the
ball flies up off the top of the screen, and the online menu drops down from the top as a large banner: Games, Shop
and Social side by side (and the Giveaway while one is live), with the settings cog and a back arrow at the top. It
looks exactly like the small menu (theme, colours, glow, corners): it is the same menu, only bigger.

The back arrow pulls the banner into a small black hole at the top of the screen; the ball then floats back down to
where it was and the small menu opens again. Leaving online mode closes your open lobbies (Coinflip, Mini Golf) and
takes you out of a live giveaway: you are told first, in one message.

OnlineWindow is a MainWindow (pages, toasts, confirmations, small screens, the lock cover all work the same); only its
shape, its layout (columns instead of tabs) and its animations differ. While online mode is on, ctx.window is the
OnlineWindow, so every page talks to the menu it is shown in."""
import math
import random
import time

from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QPoint, QPointF, QRect, QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from . import extras, win
from .core import BD, CARD_W, GLOW, PAD, S, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, mix, sfx, tr, ui
from .widgets import IconButton, ScrollArea, Tween, align_slider_rows, draw_icon, snapshot

ONLINE_KEYS = ("games", "themes", "friends")
TITLES = {"games": ("dice", "Games"), "themes": ("gem", "Shop"), "friends": ("users", "Social"),
          "giveaway": ("gift", "Giveaway"), "settings": ("cog", "Settings")}
ORDER = ("games", "themes", "friends", "giveaway", "settings")
HEAD_H = 56                      # wordmark, cog and back arrow
COL_TITLE_H = 34                 # the name of each column
COL_GAP = 16
BOTTOM = 14


def col_width() -> int:
    """A column is exactly as wide as the small menu's page: every page looks the same in both."""
    return S(CARD_W - 2 * PAD + ScrollArea.GUTTER)


# ================================================================ effects over the whole screen
class FxOverlay(QWidget):
    """A see-through window over the whole screen for a moment: the ball flying, sparks, rings. Never takes a click."""

    def __init__(self, ctx, screen) -> None:
        super().__init__()
        from .window import WINDOW_FLAGS
        self.ctx = ctx
        self.setWindowFlags(WINDOW_FLAGS | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setGeometry(screen.geometry())
        self.fx: list = []                       # [start, duration, paint(p, k, now), done]
        self.shake = (0.0, 0.0, 0.0)             # (start, length, strength)
        self._t = QTimer(self)
        self._t.setTimerType(Qt.TimerType.PreciseTimer)
        self._t.setInterval(16)
        self._t.timeout.connect(self._step)

    def add(self, duration: float, painter, done=None, delay: float = 0.0) -> None:
        self.fx.append([time.monotonic() + delay, duration, painter, done])
        if not self.isVisible():
            self.show()
            self.raise_()
            if win.IS_WIN:
                try:
                    win.set_click_through(int(self.winId()), True)
                    win.set_topmost(int(self.winId()))
                except Exception:  # noqa: BLE001
                    pass
        self._t.start()

    def _step(self) -> None:
        now = time.monotonic()
        for f in list(self.fx):
            if now >= f[0] + f[1]:
                self.fx.remove(f)
                if f[3] is not None:
                    try:
                        f[3]()
                    except Exception:  # noqa: BLE001
                        import logging
                        logging.getLogger("rubenium.online").exception("effect end failed")
        if not self.fx:
            self._t.stop()
            self.hide()
            self.deleteLater()
            return
        self.update()

    def local(self, pt: QPoint) -> QPointF:
        return QPointF(self.mapFromGlobal(pt))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        for start, dur, painter, _done in list(self.fx):
            if now < start:
                continue
            k = max(0.0, min(1.0, (now - start) / max(0.001, dur)))
            p.save()
            painter(p, k, now)
            p.restore()

    # -- the user's own ball, with their theme, colours and R style
    def paint_ball(self, p: QPainter, c: QPointF, d: float, opacity: float = 1.0) -> None:
        from .window import paint_ball_face, paint_edge, paint_shape
        shape = QRectF(c.x() - d / 2, c.y() - d / 2, d, d)
        p.setOpacity(opacity)
        level = self.ctx.glow_level(0.6)
        paint_shape(p, self.ctx, shape, d / 2, level, self.devicePixelRatioF())
        paint_ball_face(p, self.ctx, shape, 1.0)
        paint_edge(p, self.ctx, shape, d / 2, level)
        p.setOpacity(1.0)


def ease_in_out(t: float) -> float:
    return t * t * (3 - 2 * t)


def shake(widget, strength: float = 6.0, ms: int = 320) -> None:
    """A light shake: the window trembles a few pixels and settles back exactly where it was."""
    try:
        home = widget.pos()
    except RuntimeError:
        return
    t0 = time.monotonic()
    timer = QTimer(widget)
    timer.setInterval(16)
    rnd = random.Random()

    def step() -> None:
        try:
            k = (time.monotonic() - t0) / (ms / 1000)
            if k >= 1.0:
                timer.stop()
                timer.deleteLater()
                widget.move(home)
                return
            a = S(strength) * (1 - k) ** 2
            widget.move(home + QPoint(int(rnd.uniform(-a, a)), int(rnd.uniform(-a * 0.6, a * 0.6))))
        except RuntimeError:
            timer.stop()
    timer.timeout.connect(step)
    timer.start()


def spark_burst(fx: FxOverlay, at: QPointF, colour: QColor, n: int = 26, reach: float = 140.0, dur: float = 0.8,
                delay: float = 0.0) -> None:
    rnd = random.Random()
    parts = [(rnd.uniform(0, math.tau), rnd.uniform(0.35, 1.0) * S(reach), rnd.uniform(1.5, 3.4)) for _ in range(n)]

    def paint(p: QPainter, k: float, _now: float) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        for ang, dist, size in parts:
            d = dist * (1 - (1 - k) ** 3)
            c = mix(colour, QColor("#FFFFFF"), 0.4)
            c.setAlphaF(max(0.0, 1.0 - k))
            p.setBrush(c)
            p.drawEllipse(QPointF(at.x() + math.cos(ang) * d, at.y() + math.sin(ang) * d + k * k * S(30)),
                          S(size) * (1 - k * 0.5), S(size) * (1 - k * 0.5))
    fx.add(dur, paint, delay=delay)


def ring_wave(fx: FxOverlay, at: QPointF, colour: QColor, reach: float = 220.0, dur: float = 0.7, delay: float = 0.0) -> None:
    def paint(p: QPainter, k: float, _now: float) -> None:
        r = S(20) + S(reach) * (1 - (1 - k) ** 2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(alpha(colour, 0.85 * (1 - k)), S(4) * (1 - k) + 1))
        p.drawEllipse(at, r, r * 0.55)
    fx.add(dur, paint, delay=delay)


# ================================================================ the banner
class _NoTabs:
    """The online menu has no tab row (its columns are all on show); this stands in for it."""
    fade = 1.0

    def set_current(self, _key) -> None: ...
    def setVisible(self, _on) -> None: ...
    def update(self) -> None: ...
    def show(self) -> None: ...
    def hide(self) -> None: ...
    def deleteLater(self) -> None: ...
    def set_locked(self, *_a) -> None: ...


class OnlineBody(QWidget):
    """The banner's chrome: wordmark and ONLINE, the cog and the back arrow, a title over every column."""

    def __init__(self, window) -> None:
        super().__init__(window)
        from .window import LockCover
        self.win = window
        self.tabbar = _NoTabs()
        self.to_ball = IconButton("back", 30, tip=tr("Leave online mode"), parent=self)
        self.cog = IconButton("cog", 30, tip=tr("Settings"), parent=self)
        self.stow = IconButton("rball", 30, tip=tr("Hide for now (the ball waits at the top)"), parent=self)
        self.host = QWidget(self)
        self.cover = LockCover(self.host)
        self.cover.hide()
        self.to_ball.clicked.connect(window.ask_leave)
        self.cog.clicked.connect(window.toggle_settings)
        self.stow.clicked.connect(window.collapse)
        self._press = None

    # what MainWindow expects from its body
    def set_tabs(self) -> None:
        self.win.relayout()

    def offset(self) -> int:
        return 0

    def header_rect(self) -> QRectF:
        return QRectF(0, 0, self.width(), S(HEAD_H))

    def dots_rect(self) -> QRect:
        return QRect(S(PAD), S(12), S(260), S(30))

    def release_drag(self) -> None: ...

    def col_rect(self, i: int) -> QRectF:
        """Where column i sits inside the body (title included)."""
        cw = col_width()
        return QRectF(S(PAD) + i * (cw + S(COL_GAP)), S(HEAD_H), cw, self.height() - S(HEAD_H) - S(BOTTOM))

    def resizeEvent(self, _e) -> None:
        y = (S(HEAD_H) - self.to_ball.height()) // 2 + S(2)
        x = self.width() - S(PAD) - self.to_ball.width()
        for b in (self.to_ball, self.stow, self.cog):
            b.move(x, y)
            x -= b.width() + S(6)
        top = S(HEAD_H) + S(COL_TITLE_H)
        self.host.setGeometry(0, top, self.width(), max(1, self.height() - top - S(BOTTOM)))
        self.win.place_columns()
        if self.cover.isVisible():
            self.cover.setGeometry(self.host.rect())

    def mousePressEvent(self, e) -> None:
        e.accept()
        pos = e.position()
        for i, key in enumerate(self.win.tab_keys()):
            r = self.col_rect(i)
            if QRectF(r.left(), r.top(), r.width(), S(COL_TITLE_H)).contains(pos):
                self.win.focus(key)
                return

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        st = self.win.ctx.state
        from .media import Status
        playing = st.status is Status.PLAYING
        now = time.monotonic()
        # wordmark, exactly as on the small menu, then a live ONLINE pill
        p.setFont(font(20, QFont.Weight.ExtraBold, 0.4))
        fm = p.fontMetrics()
        x, base = S(PAD), QRectF(S(PAD), S(10), self.width(), S(HEAD_H) - S(16))
        word = "Rubenium"
        full = fm.horizontalAdvance(word)
        split = x + full - fm.horizontalAdvance("ium")
        p.save()
        p.setClipRect(QRectF(0, 0, split, self.height()))
        p.setPen(QColor(TEXT))
        p.drawText(base, int(Qt.AlignmentFlag.AlignVCenter), word)
        p.setClipRect(QRectF(split, 0, self.width(), self.height()))
        p.setPen(ui.accent)
        p.drawText(base, int(Qt.AlignmentFlag.AlignVCenter), word)
        p.restore()
        x += full + S(12)
        pulse = 0.5 + 0.5 * math.sin(now * 3)
        p.setFont(font(11, QFont.Weight.Black, 1.2))
        label = tr("ONLINE")
        tw = p.fontMetrics().horizontalAdvance(label) + S(30)
        pill = QRectF(x, base.center().y() - S(12), tw, S(24))
        p.setPen(QPen(alpha("#3DDC84", 0.55 + 0.35 * pulse), S(1.3)))
        p.setBrush(alpha("#3DDC84", 0.12 + 0.06 * pulse))
        p.drawRoundedRect(pill, S(12), S(12))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#3DDC84"))
        p.drawEllipse(QPointF(pill.left() + S(12), pill.center().y()), S(3.4), S(3.4))
        p.setPen(QColor("#3DDC84"))
        p.drawText(pill.adjusted(S(20), 0, -S(6), 0), int(Qt.AlignmentFlag.AlignVCenter), label)
        x = pill.right() + S(12)
        for i in range(3):                                   # the music dots, as on the small menu
            lift = math.sin(now * 5.0 - i * 0.9) * S(2.6) if playing else 0.0
            p.setBrush(alpha(ui.accent, 1.0 if playing else 0.3))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x + i * S(6), base.center().y() + S(4) - lift), S(1.7), S(1.7))
        name = self.win.ctx.online.username()
        if name:
            p.setFont(font(11, QFont.Weight.DemiBold))
            nw = p.fontMetrics().horizontalAdvance(name) + S(24)
            right = self.cog.x() - S(12)
            pill = QRectF(right - nw, base.center().y() - S(11), nw, S(22))
            if pill.left() > x + S(30):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha("#FFFFFF", 0.06))
                p.drawRoundedRect(pill, S(11), S(11))
                p.setBrush(QColor("#3DDC84") if not self.win.ctx.online.offline else alpha("#FFFFFF", 0.3))
                p.drawEllipse(QPointF(pill.left() + S(10), pill.center().y()), S(3), S(3))
                p.setPen(QColor(TEXT_DIM))
                p.drawText(pill.adjusted(S(18), 0, -S(6), 0), int(Qt.AlignmentFlag.AlignVCenter), name)
        # column titles
        for i, key in enumerate(self.win.tab_keys()):
            r = self.col_rect(i)
            head = QRectF(r.left(), r.top(), r.width() - S(ScrollArea.GUTTER), S(COL_TITLE_H) - S(6))
            on = key == self.win.current
            p.setPen(Qt.PenStyle.NoPen)
            g = QLinearGradient(head.topLeft(), head.topRight())
            g.setColorAt(0, alpha(ui.accent, 0.20 if on else 0.07))
            g.setColorAt(1, alpha(ui.accent, 0.0))
            p.setBrush(g)
            p.drawRoundedRect(head, S(9), S(9))
            icon, title = TITLES.get(key, ("spark", key))
            p.save()
            p.translate(head.left() + S(16), head.center().y())
            p.scale(S(15) / 20, S(15) / 20)
            draw_icon(p, icon, ui.accent if on else QColor(TEXT_DIM))
            p.restore()
            p.setPen(QColor(TEXT) if on else QColor(TEXT_DIM))
            p.setFont(font(13, QFont.Weight.Bold))
            p.drawText(head.adjusted(S(32), 0, 0, 0), int(Qt.AlignmentFlag.AlignVCenter), tr(title))
            if key == "giveaway":
                p.setPen(QColor("#E8C26A"))
                p.setFont(font(9, QFont.Weight.Black, 0.8))
                p.drawText(head.adjusted(0, 0, -S(10), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                           tr("LIVE"))
            if i:                                           # a thin line between columns
                xx = r.left() - S(COL_GAP) / 2
                p.setPen(QPen(alpha("#FFFFFF", 0.06), 1))
                p.drawLine(QPointF(xx, r.top() + S(4)), QPointF(xx, r.bottom() - S(4)))


class _Focus(QObject):
    """Clicking anywhere in a column makes it the one toasts, confirmations and reloads belong to."""

    def __init__(self, win, key: str) -> None:
        super().__init__(win)
        self.win, self.key = win, key

    def eventFilter(self, obj, e) -> bool:
        if e.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.Wheel) and self.win.current != self.key:
            self.win.focus(self.key, quiet=True)
        return False


def _make_class():
    """Built on first use (MainWindow lives in window.py, which imports this file's neighbours)."""
    from .window import MainWindow, SheetPage, work_area

    class OnlineWindow(MainWindow):
        def __init__(self, ctx, main) -> None:
            self.main = main
            self.settings_open = False
            self.phase = "hidden"                  # hidden / dropping / shown / stowed / leaving
            self._filters: dict = {}
            super().__init__(ctx)
            self.ball.hide()
            self.body.hide()
            self.body.deleteLater()
            self.body = OnlineBody(self)
            self.body.hide()
            for w in (self.toast_w, self.confirm_w, self.busy_w):
                w.raise_()
            want = ctx.cfg["online_tab"]
            self.current = want if want in ONLINE_KEYS else "games"
            self.drop = Tween(self, 0.0, self._on_drop, QEasingCurve.Type.OutBack)
            self.drop.finished.connect(self._drop_done)
            self.suck = Tween(self, 0.0, self.update, QEasingCurve.Type.InCubic)
            self.suck.finished.connect(self._suck_done)
            self._pm = None
            self._leave_then = None
            self.ball.save_position = lambda: None

        # -------------------------------------------------------------- what is shown
        def max_cols(self) -> int:
            wa = self._area()
            cw, gap = col_width(), S(COL_GAP)
            return max(1, int((wa.width() * 0.96 - 2 * S(PAD) + gap) // (cw + gap)))

        def tab_keys(self) -> list:
            from .pages2 import LIVE_TABS
            keys = list(ONLINE_KEYS)
            if "giveaway" in LIVE_TABS:
                keys.append("giveaway")
            if getattr(self, "settings_open", False):
                keys.append("settings")
            room = self.max_cols() if hasattr(self, "main") else len(keys)
            if len(keys) > room:                      # a small screen: settings and the focused column come first
                cur = getattr(self, "current", "games")
                keep = [k for k in ("settings",) if k in keys] + ([cur] if cur in keys and cur != "settings" else [])
                for k in ("games", "themes", "friends", "giveaway"):
                    if k in keys and k not in keep:
                        keep.append(k)
                keys = keep[:room]
            return [k for k in ORDER if k in keys]

        def showing(self, key: str) -> bool:
            return self.expanded and key in self.pages and key in self.tab_keys()

        def _area(self) -> QRect:
            c = self.main.ball.center if self.main is not None else QPoint(0, 0)
            return work_area(c)

        # -------------------------------------------------------------- geometry
        def _place(self, ball=None, card_tl=None) -> None:
            wa = self._area()
            n = len(self.tab_keys())
            cw, gap, g = col_width(), S(COL_GAP), S(GLOW)
            w = n * cw + (n - 1) * gap + 2 * S(PAD)
            h = int(min(wa.height() * 0.86, S(HEAD_H + COL_TITLE_H + BOTTOM) + S(760)))
            x = wa.center().x() - w // 2
            y = wa.top() + S(6)
            banner = QRect(x, y, w, h)
            self.setGeometry(banner.adjusted(-g, -g, g, g))
            self._max_l = QRectF(g, g, w, h)
            self._ball_l = QRectF(g + w / 2 - BD() / 2, g, BD(), BD())
            self.card_max_h = h
            self.card_pos = QPoint(x, y)
            self._sparks = extras.theme_sparkles(self.ctx.theme(), w, h, S(160))

        def _save_card(self) -> None: ...
        def save_position(self) -> None: ...
        def _restore_position(self) -> None: ...

        def reset_position(self) -> None:
            self.ctx.leave_online(after=self.main.reset_position)

        def _card_rect(self) -> QRectF:
            m = self._max_l
            lift = (1.0 - self.drop.level) * (m.bottom() + S(40))
            return m.translated(0, -lift)

        def _shape(self):
            return self._card_rect(), S(ui.radius)

        def _card_h(self, key: str) -> float:
            return float(self._max_l.height())

        def card_global(self) -> QRect:
            """The column in use: small windows (preview drawer, dialogs) open next to it, not the whole banner."""
            keys = self.tab_keys()
            if self.current in keys and self.body is not None:
                r = self.body.col_rect(keys.index(self.current))
                tl = self.body.mapToGlobal(r.topLeft().toPoint())
                return QRect(tl, r.size().toSize())
            c = self._card_rect()
            return QRect(self.mapToGlobal(c.topLeft().toPoint()), c.size().toSize())

        def _layout_body(self) -> None:
            c = self._card_rect()
            self.body.setGeometry(int(round(c.left())), int(round(c.top())), int(c.width()), int(round(c.height())))

        def place_columns(self) -> None:
            keys = self.tab_keys()
            host = self.body.host
            for i, key in enumerate(keys):
                entry = self.pages.get(key)
                if entry is None:
                    continue
                r = self.body.col_rect(i)
                entry[0].setGeometry(int(r.left()), 0, col_width(), host.height())

        # -------------------------------------------------------------- columns
        def _ensure_page(self, key: str):
            new = key not in self.pages
            entry = super()._ensure_page(key)
            if new:
                entry[0].no_stretch = True              # a column is taller than its page: the page keeps its size
                entry[0].resizeEvent(None)
                f = _Focus(self, key)
                self._filters[key] = f
                entry[0].installEventFilter(f)
                for child in entry[0].findChildren(QWidget):
                    child.installEventFilter(f)
            return entry

        def relayout(self) -> None:
            """(Re)build the columns: pages that are on show are made, the others dropped."""
            if self.phase in ("hidden",):
                return
            keys = self.tab_keys()
            for key in list(self.pages):
                if key not in keys and key != self.current:
                    self._drop_page(key)
            if self.current not in keys:
                self.current = keys[0]
            old = self.width()
            self._place()
            if self.width() != old:
                self._layout_body()
            for key in keys:
                new = key not in self.pages
                sa, page, _h = self._ensure_page(key)
                sa.show()
                if new and self.phase == "shown":
                    page.on_show()
            self.body.resizeEvent(None)
            self.body.update()
            self.update()

        def tabs_changed(self) -> None:
            self.relayout()

        def focus(self, key: str, quiet: bool = False) -> None:
            if key not in self.tab_keys():
                return
            if key != self.current:
                self.current = key
                if key in ONLINE_KEYS:
                    self.ctx.cfg["online_tab"] = key
                if not quiet:
                    sfx.play("pick")
                self.body.update()

        def goto(self, key: str) -> None:
            if key == "settings":
                if not self.settings_open:
                    self.toggle_settings()
                return self.focus("settings")
            if key in ("games", "themes", "friends", "giveaway"):
                if key in self.tab_keys():
                    if not self.expanded:
                        self.current = key
                        return self.expand()
                    return self.focus(key)
                return
            # a part of the small menu (Home, Lyrics, Screen...): leave online mode, then open it there
            self.ctx.leave_online(after=lambda: self.main.goto(key))

        def toggle_settings(self) -> None:
            self.settings_open = not self.settings_open
            sfx.play("pick")
            if not self.settings_open and "settings" in self.pages:
                if self.current == "settings":
                    self.current = self.ctx.cfg["online_tab"] if self.ctx.cfg["online_tab"] in ONLINE_KEYS else "games"
                self._drop_page("settings")
            elif self.settings_open:
                self.current = "settings"
            self.relayout()

        def reload_page(self, key: str = None) -> None:
            key = key or self.current
            if not self.expanded or key not in self.tab_keys():
                if key in self.pages:
                    self._drop_page(key)
                return
            old = self.pages.get(key)
            offset = old[0].offset() if old else 0.0
            self._drop_page(key)
            sa, page, _h = self._ensure_page(key)
            self.place_columns()
            sa.show()
            sa._target = min(offset, max(0.0, sa.max_offset()))
            sa._pos.jump(sa._target)
            page.on_show()
            QTimer.singleShot(0, self.sync_lock)

        def page(self):
            entry = self.pages.get(self.current)
            return entry[1] if entry else None

        def _focus_rect(self) -> QRectF:
            """The focused column inside this window: toasts and questions show over it."""
            keys = self.tab_keys()
            c = self._card_rect()
            if self.current in keys:
                r = self.body.col_rect(keys.index(self.current))
                return QRectF(c.left() + r.left(), c.top() + r.top(), r.width(), r.height())
            return c

        def toast(self, text: str, kind: str = "ok") -> None:
            if self.phase == "shown":
                self.toast_w.show_text(text, kind, self._focus_rect())

        def confirm(self, text: str, on_yes, yes: str = "", no: str = "", persistent: bool = False, on_no=None) -> None:
            if self.phase == "shown":
                self.toast_w.hide()
                self.confirm_w.ask(text, on_yes, self._focus_rect(), yes, no, persistent, on_no)

        def show_busy(self, text: str) -> None:
            if self.phase == "shown":
                self.toast_w.hide()
                self.confirm_w.hide()
                self.busy_w.start(text, self._focus_rect())

        def sync_lock(self) -> None:
            """Offline, locked or out of date: the whole banner is covered (every part of it is online)."""
            ctx = self.ctx
            cover = self.body.cover
            mode = ("offmode" if ctx.cfg["offline_mode"] and ctx.online.logged_in() else
                    "locked" if ctx.econ.live.get("locked") else
                    "update" if getattr(ctx, "outdated", False) else
                    "offline" if ctx.online.logged_in() and ctx.online.offline else "")
            on = bool(mode) and self.expanded and self.phase == "shown"
            if on and mode != cover.mode:
                cover.set_mode(mode, ctx.install_update if mode == "update" and ctx.updater.latest else
                               (ctx.online.probe if mode == "offline" else
                                (lambda: ctx.set_offline_mode(False)) if mode == "offmode" else None))
            if on:
                cover.setGeometry(self.body.host.rect())
                cover.resizeEvent(None)
                if not cover.isVisible():
                    cover.take(self.body.host)
                cover.show()
                cover.raise_()
            elif cover.isVisible():
                cover.hide()

        def rebuild(self) -> None:
            """Size or language changed: rebuild every column."""
            for key in list(self.pages):
                self._drop_page(key)
            self.fade.jump(1.0)
            self.chrome.jump(1.0)
            for w in (self.toast_w, self.confirm_w):
                w.deleteLater()
            self.body.deleteLater()
            from .window import Confirm, Toast, _tiles
            _tiles.clear()
            self.body = OnlineBody(self)
            self.toast_w = Toast(self)
            self.confirm_w = Confirm(self)
            self.busy_w.raise_()
            if self.phase in ("shown", "dropping"):
                self._place()
                self._layout_body()
                self.body.show()
                self.relayout()
            self.update()

        def theme_changed(self) -> None:
            m = self._max_l
            self._sparks = extras.theme_sparkles(self.ctx.theme(), m.width(), m.height(), S(160))
            self._retime()
            self.update()
            for page in self.each_page():
                page.update()

        # the banner never moves with the mouse and its menu row never hides
        def begin_drag(self, grab) -> None: ...
        def end_drag(self) -> None: ...
        def _chrome_allowed(self) -> bool:
            return False

        def _on_morph(self) -> None:
            self.update()

        # -------------------------------------------------------------- in and out
        def open(self) -> None:
            """Drop down from the top of the screen."""
            self.phase = "dropping"
            self.expanded = True
            self.ctx.cfg["card_open"] = True
            self._place()
            self.morph.jump(1.0)
            self.chrome.jump(1.0)
            self.drop.setEasingCurve(QEasingCurve.Type.OutBack)
            self.drop.jump(0.0)
            self._layout_body()
            self.body.show()
            self.relayout()
            for key in self.tab_keys():
                sa, page, _ = self._ensure_page(key)
                page.on_show()
            self._layout_body()
            self._pm = snapshot(self.body)
            self.body.hide()
            self.show()
            if win.IS_WIN:
                win.set_topmost(int(self.winId()))
            self.drop.to(1.0, 620)
            self._retime()
            self.ctx.on_visibility()

        def _on_drop(self) -> None:
            if self.phase in ("dropping", "stowing"):
                self.update()

        def _drop_done(self) -> None:
            if self.phase == "dropping":
                self.phase = "shown"
                self._pm = None
                self._layout_body()
                self.body.show()
                self.body.resizeEvent(None)
                self._idle.stop()
                QTimer.singleShot(0, self.sync_lock)
                sfx.play("on")
                shake(self, 5.0, 300)
                fx = getattr(self.ctx, "_fx", None)
                if fx is not None:
                    try:
                        c = self.mapToGlobal(self._card_rect().center().toPoint())
                        bottom = QPoint(c.x(), self.mapToGlobal(self._card_rect().bottomLeft().toPoint()).y())
                        spark_burst(fx, fx.local(bottom), ui.accent, n=34, reach=180)
                    except RuntimeError:
                        pass
            elif self.phase == "stowing":
                self.phase = "stowed"
                self.hide()
                self._show_stowed_ball()

        def expand(self) -> None:
            if self.phase == "stowed":
                self.ball.hide()
                self.open()

        def collapse(self) -> None:
            """Hide the banner for now: it slides up and the ball waits at the top of the screen."""
            if self.phase != "shown":
                return
            self._close_sheet()
            self.toast_w.hide()
            self.confirm_w.hide()
            self.drawer.close_now()
            self._pm = snapshot(self.body)
            self.body.hide()
            self.expanded = False
            self.ctx.cfg["card_open"] = False
            self.phase = "stowing"
            self.drop.setEasingCurve(QEasingCurve.Type.InCubic)
            self.drop.to(0.0, 380)
            for page in self.each_page():
                page.on_hide()
            self.ctx.on_visibility()

        def _show_stowed_ball(self) -> None:
            wa = self._area()
            d = BD()
            self.ball.set_center(QPoint(wa.center().x(), wa.top() + d // 2 + S(10)))
            self.ball.show()
            self.ball.appear.jump(0.0)
            self.ball.appear.to(1.0, 420)
            if win.IS_WIN:
                win.set_topmost(int(self.ball.winId()))

        def toggle(self) -> None:
            if self.phase == "shown":
                self.collapse()
            elif self.phase == "stowed":
                self.expand()

        def ask_leave(self) -> None:
            self.ctx.leave_online()

        def start_leaving(self, then) -> None:
            """The black hole: the banner is pulled into it, up and away."""
            self._leave_then = then
            self._close_sheet()
            self.toast_w.hide()
            self.confirm_w.hide()
            self.busy_w.hide()
            self.drawer.close_now()
            if self.phase == "stowed":
                self.ball.hide()
                self.phase = "leaving"
                return self._suck_done()
            for page in self.each_page():
                page.on_hide()
            self._pm = snapshot(self.body)
            self.body.hide()
            self.phase = "leaving"
            self.expanded = False
            self.suck.jump(0.0)
            self.suck.to(1.0, 820)
            shake(self, 4.0, 260)
            sfx.play("off")

        def _suck_done(self) -> None:
            if self.phase != "leaving":
                return
            self.phase = "hidden"
            self.hide()
            self.ball.hide()
            self._pm = None
            for key in list(self.pages):
                self._drop_page(key)
            then, self._leave_then = self._leave_then, None
            if then is not None:
                then()

        def vortex_point(self) -> QPointF:
            m = self._max_l
            return QPointF(m.center().x(), m.top() + S(26))

        # -------------------------------------------------------------- painting
        def paintEvent(self, _e) -> None:
            from .window import paint_edge, paint_shape
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            now = time.monotonic()
            if self.phase == "leaving":
                return self._paint_vortex(p, now)
            shape, radius = self._shape()
            level = self.ctx.glow_level()
            path = paint_shape(p, self.ctx, shape, radius, level, self.devicePixelRatioF())
            th = self.ctx.theme()
            if th["layers"] or self._sparks or ui.accent2 is not None:
                m = self._max_l
                p.save()
                p.setClipPath(path)
                pm = extras.theme_pattern(th, int(m.width()), int(m.height()), self._accent_to, self.devicePixelRatioF(),
                                          ui.scale, S(160))
                if pm is not None:
                    p.drawPixmap(shape.topLeft(), pm)
                if self._sparks:
                    extras.paint_sparkles(p, self._sparks, shape.left(), shape.top(), ui.accent, now, ui.scale)
                p.restore()
            if self._pm is not None:
                p.save()
                p.setClipPath(path)
                p.drawPixmap(shape.topLeft(), self._pm)
                p.restore()
            paint_edge(p, self.ctx, shape, radius, level)

        def _paint_vortex(self, p: QPainter, now: float) -> None:
            """A small black hole at the top: it opens, swallows the banner (spinning, shrinking, pulled up) and closes."""
            from .window import paint_shape
            k = self.suck.level
            c = self.vortex_point()
            size = S(70) * math.sin(min(1.0, k * 1.15) * math.pi) ** 0.6 + S(4) * (1 - k)
            # the banner, pulled in
            if self._pm is not None and k < 0.98:
                m = self._max_l
                s = max(0.0, 1.0 - k ** 1.4)
                p.save()
                p.translate(c)
                p.rotate(-k * k * 220)
                p.scale(s, s * (1 - 0.25 * k))
                p.translate(-c.x(), -c.y() + k * S(20))
                p.setOpacity(max(0.0, 1.0 - k * 0.9))
                path = paint_shape(p, self.ctx, m, S(ui.radius), self.ctx.glow_level() * (1 - k), self.devicePixelRatioF())
                p.setClipPath(path)
                p.drawPixmap(m.topLeft(), self._pm)
                p.restore()
            # the hole: an accent ring of matter spinning around a black core
            p.setPen(Qt.PenStyle.NoPen)
            halo = QRadialGradient(c, size * 2.4)
            halo.setColorAt(0.0, alpha(ui.accent, 0.0))
            halo.setColorAt(0.35, alpha(ui.accent, 0.55))
            halo.setColorAt(1.0, alpha(ui.accent, 0.0))
            p.setBrush(halo)
            p.drawEllipse(c, size * 2.4, size * 1.3)
            rnd = random.Random(7)
            for i in range(60):
                a0 = rnd.uniform(0, math.tau)
                rad = rnd.uniform(1.05, 2.3) * size
                ang = a0 + now * (3.2 + 2.4 / max(0.3, rad / max(1.0, size)))
                pc = mix(ui.accent, QColor("#FFFFFF"), rnd.uniform(0.0, 0.6))
                pc.setAlphaF(0.75)
                p.setBrush(pc)
                p.drawEllipse(QPointF(c.x() + math.cos(ang) * rad, c.y() + math.sin(ang) * rad * 0.45), S(1.6), S(1.6))
            core = QRadialGradient(c, size)
            core.setColorAt(0.0, QColor(0, 0, 0, 255))
            core.setColorAt(0.75, QColor(0, 0, 0, 240))
            core.setColorAt(1.0, QColor(0, 0, 0, 0))
            p.setBrush(core)
            p.drawEllipse(c, size, size * 0.62)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(alpha(mix(ui.accent, QColor("#FFFFFF"), 0.4), 0.9), S(2)))
            p.drawEllipse(c, size * 1.02, size * 0.64)

        def _tick(self) -> None:
            if self.phase == "leaving" or self.drop.busy:
                return self.update()
            super()._tick()

    return OnlineWindow


_CLASS = None


def online_window(ctx, main):
    global _CLASS
    if _CLASS is None:
        _CLASS = _make_class()
    return _CLASS(ctx, main)


# ================================================================ entering and leaving (driven by the app)
def fly_up(ctx, main, then) -> None:
    """The ball rises from where it is to the middle of the top of the screen and keeps going, off screen."""
    screen = QGuiApplication.screenAt(main.ball.center) or QGuiApplication.primaryScreen()
    fx = FxOverlay(ctx, screen)
    ctx._fx = fx
    start = fx.local(main.ball.center)
    geo = screen.geometry()
    top = QPointF(geo.width() / 2, -BD() * 1.2)
    mid = QPointF(geo.width() / 2, S(60))
    d = BD()
    trail: list = []
    main.ball.hide()
    sfx.play("on")

    def paint(p: QPainter, k: float, now: float) -> None:
        e = k * k * (3 - 2 * k)
        # a curve: up and to the middle, then straight up out of the screen
        q = 1 - e
        x = q * q * start.x() + 2 * q * e * mid.x() + e * e * top.x()
        y = q * q * start.y() + 2 * q * e * (start.y() * 0.35 + mid.y() * 0.65) + e * e * top.y()
        pos = QPointF(x, y)
        trail.append((pos, now))
        while trail and now - trail[0][1] > 0.28:
            trail.pop(0)
        p.setPen(Qt.PenStyle.NoPen)
        for tp, tt in trail:                          # a streak of light behind it
            age = (now - tt) / 0.28
            col = alpha(mix(ui.accent, QColor("#FFFFFF"), 0.3), 0.35 * (1 - age))
            p.setBrush(col)
            r = d * 0.5 * (1 - age * 0.7)
            p.drawEllipse(tp, r, r)
        s = 1.0 + 0.25 * math.sin(k * math.pi) - 0.35 * k * k
        fx.paint_ball(p, pos, d * s)
    fx.add(0.72, paint, done=lambda: _arrived(ctx, fx, QPointF(geo.width() / 2, 0), then))
    spark_burst(fx, start, ui.accent, n=18, reach=70, dur=0.5)


def _arrived(ctx, fx, at, then) -> None:
    ring_wave(fx, at + QPointF(0, S(4)), ui.accent, reach=260, dur=0.6)
    spark_burst(fx, at + QPointF(0, S(8)), ui.accent, n=30, reach=160, dur=0.7)

    def flash(p: QPainter, k: float, _now: float) -> None:
        g = QRadialGradient(at, S(420))
        g.setColorAt(0, alpha(ui.accent, 0.45 * (1 - k)))
        g.setColorAt(1, alpha(ui.accent, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(at, S(420), S(240))
    fx.add(0.45, flash)
    then()


def float_down(ctx, main, then) -> None:
    """The R comes back down from the top of the screen, swaying a little, and lands where the ball lives."""
    main.ball.clamp()                                  # the ball comes back exactly where it left from
    screen = QGuiApplication.screenAt(main.ball.center) or QGuiApplication.primaryScreen()
    fx = getattr(ctx, "_fx", None)
    try:
        if fx is None or not fx.isVisible():
            raise RuntimeError
        fx.geometry()
    except RuntimeError:
        fx = FxOverlay(ctx, screen)
        ctx._fx = fx
    geo = screen.geometry()
    end = fx.local(main.ball.center)
    start = QPointF(geo.width() / 2, S(40))
    d = BD()

    def paint(p: QPainter, k: float, now: float) -> None:
        e = 1 - (1 - k) ** 3
        x = start.x() + (end.x() - start.x()) * e + math.sin(k * math.pi * 3) * S(18) * (1 - k)
        y = start.y() + (end.y() - start.y()) * e
        appear = min(1.0, k / 0.25)
        fx.paint_ball(p, QPointF(x, y), d * (0.55 + 0.45 * appear), appear)
        if int(now * 30) % 2 == 0:
            pass

    def landed() -> None:
        ring_wave(fx, end, ui.accent, reach=90, dur=0.45)
        spark_burst(fx, end, ui.accent, n=16, reach=60, dur=0.45)
        then()
    fx.add(0.85, paint, done=landed)
