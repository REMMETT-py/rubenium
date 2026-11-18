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

from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QPoint, QPointF, QRect, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from . import extras, win
from .core import BD, CARD_W, GLOW, ONLINE_EXTRA, PAD, S, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, mix, sfx, tr, ui
from .widgets import IconButton, ScrollArea, Tween, align_slider_rows, draw_icon, snapshot

ONLINE_KEYS = ("games", "themes", "friends", "settings")
TITLES = {"games": ("dice", "Games"), "themes": ("gem", "Shop"), "friends": ("users", "Social"),
          "giveaway": ("gift", "Giveaway"), "settings": ("cog", "Settings"), "admin": ("shield", "Admin")}
ORDER = ("games", "themes", "friends", "giveaway", "settings")
SECTIONS = ("games", "themes", "friends", "settings")           # 4.0: the four parts; two are shown side by side
LEFT = ("games", "themes", "giveaway")          # 4.1: games and shop on the left half only
RIGHT = ("friends", "settings")                 # social (with the leaderboards) and settings on the right only


def side_of(key: str) -> int:
    return 1 if key in RIGHT or key == "admin" else 0          # 4.4: the admin panel opens in the right half
HEAD_H = 64                      # wordmark, XP bar, leaderboards, back arrow
COL_TITLE_H = 46                 # 4.0: the section switch over each half
COL_GAP = 16
BOTTOM = 14


def col_width() -> int:
    """4.1: a column is wider than the small menu's page (its pages are made for that width)."""
    return S(CARD_W - 2 * PAD + ONLINE_EXTRA + ScrollArea.GUTTER)


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


class GoldButton(QWidget):
    """4.0: the Leaderboards button: gold, a trophy, easy to find."""
    clicked = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(S(32))
        self.hover = 0.0
        self.text = "🏆  " + tr("Leaderboards")
        f = font(11.5, QFont.Weight.ExtraBold)
        from PyQt6.QtGui import QFontMetrics
        self.setFixedWidth(QFontMetrics(f).horizontalAdvance(self.text) + S(28))
        self.setToolTip(tr("Leaderboards: coins, worth, levels, games"))

    def enterEvent(self, _e) -> None:
        self.hover = 1.0
        self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = 0.0
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if self.rect().contains(e.position().toPoint()):
            sfx.play("pick")
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        now = time.monotonic()
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor("#FFE38A") if self.hover else QColor("#F2CC5A"))
        g.setColorAt(1, QColor("#C8902A"))
        p.setPen(QPen(QColor("#FFF2C2"), S(1.2)))
        p.setBrush(g)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        sweep = (now * 0.4) % 2.2 - 0.6                       # a soft shine passing over it
        sg = QLinearGradient(QPointF(r.left() + sweep * r.width(), 0), QPointF(r.left() + sweep * r.width() + S(30), 0))
        sg.setColorAt(0, alpha("#FFFFFF", 0))
        sg.setColorAt(0.5, alpha("#FFFFFF", 0.35))
        sg.setColorAt(1, alpha("#FFFFFF", 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(sg)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setPen(QColor("#3A2606"))
        p.setFont(font(11.5, QFont.Weight.ExtraBold))
        p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), self.text)


class LeaveButton(QWidget):
    """4.3: leaving online mode, easy to see: an arrow and the words, in a clear pill."""
    clicked = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(S(32))
        self.hover = 0.0
        self.text = tr("Leave online")
        from PyQt6.QtGui import QFontMetrics
        self.setFixedWidth(QFontMetrics(font(11.5, QFont.Weight.Bold)).horizontalAdvance(self.text) + S(46))
        self.setToolTip(tr("Back to the small menu"))

    def enterEvent(self, _e) -> None:
        self.hover = 1.0
        self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = 0.0
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if self.rect().contains(e.position().toPoint()):
            sfx.play("pick")
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(alpha("#FFFFFF", 0.45 + 0.35 * self.hover), S(1.3)))
        p.setBrush(alpha("#FFFFFF", 0.08 + 0.10 * self.hover))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.save()
        p.translate(r.left() + S(18), r.center().y())
        p.scale(S(14) / 20, S(14) / 20)
        draw_icon(p, "back", QColor(TEXT))
        p.restore()
        p.setPen(QColor(TEXT))
        p.setFont(font(11.5, QFont.Weight.Bold))
        p.drawText(r.adjusted(S(32), 0, -S(12), 0), int(Qt.AlignmentFlag.AlignVCenter), self.text)


class PaneSwitch(QWidget):
    """4.0: over each half of the online menu: Games, Shop, Social, Settings (and the live Giveaway). The other half's
    choice is marked with a dot; picking it swaps the two halves."""
    picked = pyqtSignal(str)

    def __init__(self, win, index: int, parent=None) -> None:
        super().__init__(parent)
        self.win, self.index = win, index
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rects: list = []
        self.hover = None
        self.setMouseTracking(True)

    def keys(self) -> list:
        """Two halves: each one switches between its own parts. One half (a small screen): every part."""
        from .pages2 import LIVE_TABS
        live = ["giveaway"] if "giveaway" in LIVE_TABS else []
        if len(self.win.tab_keys()) < 2:
            return list(SECTIONS) + live + (["admin"] if "admin" in LIVE_TABS else [])
        admin = ["admin"] if "admin" in LIVE_TABS else []           # 4.4: admins get their panel here, full size
        return [k for k in LEFT if k != "giveaway"] + live if self.index == 0 else list(RIGHT) + admin

    def _layout(self) -> None:
        keys = self.keys()
        r = QRectF(self.rect()).adjusted(0, S(4), -S(ScrollArea.GUTTER), -S(4))
        w = (r.width() - S(4) * (len(keys) - 1)) / len(keys)
        self.rects = [(QRectF(r.left() + i * (w + S(4)), r.top(), w, r.height()), k) for i, k in enumerate(keys)]

    def mouseMoveEvent(self, e) -> None:
        self._layout()
        h = next((k for rr, k in self.rects if rr.contains(e.position())), None)
        if h != self.hover:
            self.hover = h
            self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = None
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        self._layout()
        for rr, k in self.rects:
            if rr.contains(e.position()):
                self.picked.emit(k)
                return

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._layout()
        panes = self.win.tab_keys()
        mine = panes[self.index] if self.index < len(panes) else None
        focused = self.win.current == mine
        for rr, k in self.rects:
            on = k == mine
            other = k in panes and not on
            hov = self.hover == k
            p.setPen(QPen(ui.accent if on else alpha("#FFFFFF", 0.14 if hov else 0.07), S(1.6) if on else 1))
            if on:
                g = QLinearGradient(rr.topLeft(), rr.bottomLeft())
                g.setColorAt(0, alpha(ui.accent, 0.34 if focused else 0.22))
                g.setColorAt(1, alpha(ui.accent, 0.12))
                p.setBrush(g)
            else:
                p.setBrush(alpha("#FFFFFF", 0.07 if hov else 0.03))
            p.drawRoundedRect(rr, S(10), S(10))
            icon, title = TITLES.get(k, ("spark", k))
            text = tr(title)
            p.setFont(font(11.5, QFont.Weight.Bold if on else QFont.Weight.DemiBold))
            fm = p.fontMetrics()
            iw = S(15)
            show_text = fm.horizontalAdvance(text) + iw + S(14) <= rr.width()
            if not show_text:                            # too narrow: shrink the text, then keep the icon only
                p.setFont(font(10, QFont.Weight.Bold if on else QFont.Weight.DemiBold))
                fm = p.fontMetrics()
                show_text = fm.horizontalAdvance(text) + iw + S(12) <= rr.width()
            total = iw + (S(6) + fm.horizontalAdvance(text) if show_text else 0)
            x = rr.center().x() - total / 2
            p.save()
            p.translate(x + iw / 2, rr.center().y())
            p.scale(iw / 20, iw / 20)
            draw_icon(p, icon, ui.accent if on else QColor(TEXT if hov else TEXT_DIM))
            p.restore()
            if show_text:
                box = QRectF(x + iw + S(6), rr.top(), rr.right() - x - iw - S(6), rr.height())
                if k == "admin":                         # 4.5: the admin tab glows softly, unlike the others
                    glow = QRadialGradient(QPointF(box.left() + fm.horizontalAdvance(text) / 2, rr.center().y()),
                                           fm.horizontalAdvance(text) * 0.8)
                    glow.setColorAt(0, alpha("#FF6A5C", 0.32))
                    glow.setColorAt(1, alpha("#FF6A5C", 0.0))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(glow)
                    p.drawRoundedRect(rr, S(10), S(10))
                    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        p.setPen(alpha("#FF6A5C", 0.35))
                        p.drawText(box.translated(dx * S(0.8), dy * S(0.8)), int(Qt.AlignmentFlag.AlignVCenter), text)
                    p.setPen(QColor("#FFD9D4"))
                else:
                    p.setPen(QColor(TEXT) if on else QColor(TEXT_DIM))
                p.drawText(box, int(Qt.AlignmentFlag.AlignVCenter), text)
            if other:                                    # shown in the other half
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha(ui.accent, 0.8))
                p.drawEllipse(QPointF(rr.right() - S(7), rr.top() + S(7)), S(2.6), S(2.6))
            if k == "giveaway":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#E8C26A"))
                p.drawEllipse(QPointF(rr.left() + S(7), rr.top() + S(7)), S(2.6), S(2.6))


class OnlineBody(QWidget):
    """The banner's chrome: wordmark, the XP bar, Leaderboards, the back arrow; a section switch over each half."""

    def __init__(self, window) -> None:
        super().__init__(window)
        from .levels import XPBar
        from .window import LockCover
        self.win = window
        self.tabbar = _NoTabs()
        self.to_ball = LeaveButton(self)                # 4.3: a clear "Leave online" pill
        self.stow = IconButton("rball", 30, tip=tr("Hide for now (click the R to bring it back)"), parent=self)
        self.top = GoldButton(self)                     # 4.3: Leaderboards moved into Social; kept hidden
        self.top.hide()
        self.xp = XPBar(window.ctx, self)
        self.xp.clicked.connect(window.open_levels)
        self.switches = [PaneSwitch(window, i, self) for i in range(2)]
        for sw in self.switches:
            sw.picked.connect(lambda key, sw=sw: window.set_pane(sw.index, key))
        self.host = QWidget(self)
        self.cover = LockCover(self.host)
        self.cover.hide()
        self.to_ball.clicked.connect(window.ask_leave)
        self.stow.clicked.connect(window.collapse)
        self.top.clicked.connect(window.open_leaders)
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
        """Where half i sits inside the body (switch included)."""
        n = max(1, len(self.win.tab_keys()))
        cw = col_width()
        gap = S(COL_GAP)
        total = n * cw + (n - 1) * gap
        left = (self.width() - total) / 2
        return QRectF(left + i * (cw + gap), S(HEAD_H), cw, self.height() - S(HEAD_H) - S(BOTTOM))

    def resizeEvent(self, _e) -> None:
        x = self.width() - S(PAD)
        for b in (self.to_ball, self.stow):
            x -= b.width()
            b.move(x, (S(HEAD_H) - b.height()) // 2)
            x -= S(8)
        left_end = x                                     # the buttons start here
        xw = min(S(460), max(S(200), self.width() - S(PAD) * 2 - S(250) - (self.width() - left_end)))
        self.xp.setGeometry(int(self.width() / 2 - xw / 2), (S(HEAD_H) - self.xp.height()) // 2, int(xw), self.xp.height())
        if self.xp.geometry().right() > left_end - S(12):              # a narrow banner: the bar moves left
            self.xp.move(left_end - S(12) - xw, self.xp.y())
        n = len(self.win.tab_keys())
        for i, sw in enumerate(self.switches):
            sw.setVisible(i < n)
            if i < n:
                r = self.col_rect(i)
                sw.setGeometry(int(r.left()), int(r.top()), int(r.width()), S(COL_TITLE_H) - S(4))
                sw.update()
        top = S(HEAD_H) + S(COL_TITLE_H)
        self.host.setGeometry(0, top, self.width(), max(1, self.height() - top - S(BOTTOM)))
        self.win.place_columns()
        if self.cover.isVisible():
            self.cover.setGeometry(self.host.rect())

    def mousePressEvent(self, e) -> None:
        e.accept()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        st = self.win.ctx.state
        from .media import Status
        playing = st.status is Status.PLAYING
        now = time.monotonic()
        # wordmark, exactly as on the small menu, then a live dot (online)
        p.setFont(font(20, QFont.Weight.ExtraBold, 0.4))
        fm = p.fontMetrics()
        x, base = S(PAD), QRectF(S(PAD), S(10), self.width(), S(HEAD_H) - S(20))
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
        x += full + S(10)
        pulse = 0.5 + 0.5 * math.sin(now * 3)
        off = self.win.ctx.online.offline
        col = alpha("#FFFFFF", 0.35) if off else QColor("#3DDC84")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha(col, 0.25 + 0.2 * pulse))
        p.drawEllipse(QPointF(x + S(5), base.center().y()), S(6), S(6))
        p.setBrush(col)
        p.drawEllipse(QPointF(x + S(5), base.center().y()), S(3.4), S(3.4))
        x += S(16)
        for i in range(3):                                   # the music dots, as on the small menu
            lift = math.sin(now * 5.0 - i * 0.9) * S(2.6) if playing else 0.0
            p.setBrush(alpha(ui.accent, 1.0 if playing else 0.3))
            p.drawEllipse(QPointF(x + i * S(6), base.center().y() + S(4) - lift), S(1.7), S(1.7))
        # a thin line between the halves
        keys = self.win.tab_keys()
        if len(keys) > 1:
            r0, r1 = self.col_rect(0), self.col_rect(1)
            xx = (r0.right() + r1.left()) / 2
            p.setPen(QPen(alpha("#FFFFFF", 0.07), 1))
            p.drawLine(QPointF(xx, r0.top() + S(8)), QPointF(xx, r0.bottom() - S(4)))


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
            self._was_down = False
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
            panes = list(ctx.cfg["online_panes"] or ["games", "friends"])
            self.current = want if want in panes else (panes[0] if panes else "games")
            if self.current not in LEFT + RIGHT:
                self.current = "games"
            self.drop = Tween(self, 0.0, self._on_drop, QEasingCurve.Type.OutBack)
            self.drop.finished.connect(self._drop_done)
            self.suck = Tween(self, 0.0, self.update, QEasingCurve.Type.InCubic)
            self.suck.finished.connect(self._suck_done)
            self._pm = None
            self._leave_then = None
            self.ball.save_position = lambda: None
            self._watch = QTimer(self)
            self._watch.setInterval(60)
            self._watch.timeout.connect(self._watch_outside)

        # -------------------------------------------------------------- what is shown
        def max_cols(self) -> int:
            wa = self._area()
            cw, gap = col_width(), S(COL_GAP)
            return max(1, int((wa.width() * 0.96 - 2 * S(PAD) + gap) // (cw + gap)))

        def panes(self) -> list:
            """4.0: the two parts shown side by side (picked by the player, kept in the settings)."""
            from .pages2 import LIVE_TABS
            ok = list(SECTIONS) + (["giveaway"] if "giveaway" in LIVE_TABS else []) + (["admin"] if "admin" in LIVE_TABS else [])
            want = [k for k in (self.ctx.cfg["online_panes"] or []) if k in ok]
            left = next((k for k in want if k in LEFT), "games")          # 4.1: each part on its own side
            right = next((k for k in want if side_of(k) == 1), "friends")
            return [left, right]

        def tab_keys(self) -> list:
            keys = self.panes()
            room = self.max_cols() if hasattr(self, "main") else 2
            if room < 2:                                   # a small screen: one half, the one in use
                cur = getattr(self, "current", keys[0])
                return [cur if cur in keys else keys[0]]
            return keys

        def set_pane(self, index: int, key: str) -> None:
            """Show `key` in its own half (4.1: games and shop left, social and settings right; `index` is kept for
            the callers but the side always follows the part). A small screen shows one half: the one picked."""
            panes = self.panes()
            index = side_of(key)
            if panes[index] == key and len(self.tab_keys()) > 1:
                return self.focus(key)
            panes[index] = key
            self.ctx.cfg["online_panes"] = list(panes)
            sfx.play("pick")
            self.current = key
            self.relayout()
            self.body.resizeEvent(None)
            for sw in self.body.switches:
                sw.update()

        def open_leaders(self) -> None:
            """The gold button: the leaderboards, in the Social half (brought in if it is not shown)."""
            self.ctx.social_tab = 3
            self.ctx.friends_profile = None
            self.ctx.social_edit = False
            if "friends" not in self.tab_keys():
                self.set_pane(side_of("friends"), "friends")
            self.focus("friends", quiet=True)
            self.reload_page("friends")

        def open_levels(self) -> None:
            """The XP bar: Inventory > Levels, in the Shop half."""
            self.ctx.shop_tab = 5
            self.ctx.inv_tab = "levels"
            if "themes" not in self.tab_keys():
                self.set_pane(side_of("themes"), "themes")
            self.focus("themes", quiet=True)
            self.reload_page("themes")

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
            h = int(min(wa.height() - S(18), S(HEAD_H + COL_TITLE_H + BOTTOM) + S(980)))   # 4.3: taller, less scrolling
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
        def page_w(self) -> int:
            return S(CARD_W - 2 * PAD + ONLINE_EXTRA)

        def _ensure_page(self, key: str):
            from .core import wide_pages
            new = key not in self.pages
            with wide_pages():                          # 4.1: its pages are made for the wider halves
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
                for sw in self.body.switches:
                    sw.update()

        def goto(self, key: str) -> None:
            if key in ("games", "themes", "friends", "giveaway", "settings", "admin"):
                if key not in self.tab_keys():                # brought into its own half
                    self.set_pane(side_of(key), key)
                if not self.expanded:
                    self.current = key
                    return self.expand()
                return self.focus(key)
            # a part of the small menu (Home, Lyrics, Screen...): leave online mode, then open it there
            self.ctx.leave_online(after=lambda: self.main.goto(key))

        def toggle_settings(self) -> None:
            self.goto("settings")

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
                    "lockdown" if ctx.econ.lockdown_cover() else
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
                self._was_down = True
                self._watch.start()
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
            """4.0: hide for now. The banner shoots up into a wide black hole at the top of the screen, which closes
            on the R; click the R to bring the banner back down. Also when you click outside it (on the desktop or a
            game)."""
            if self.phase != "shown":
                return
            self._close_sheet()
            self.toast_w.hide()
            self.confirm_w.hide()
            self.drawer.close_now()
            self._watch.stop()
            self._pm = snapshot(self.body)
            self.body.hide()
            self.expanded = False
            self.ctx.cfg["card_open"] = False
            self.phase = "stowing"
            self.suck.setEasingCurve(QEasingCurve.Type.Linear)
            self.suck.jump(0.0)
            self.suck.to(1.0, 560)
            for page in self.each_page():
                page.on_hide()
            sfx.play("off")
            self.ctx.on_visibility()

        def _show_stowed_ball(self) -> None:
            wa = self._area()
            d = BD()
            self.ball.set_center(QPoint(wa.center().x(), wa.top() + d // 2 + S(10)))
            self.ball.show()
            self.ball.appear.jump(0.6)
            self.ball.appear.to(1.0, 260)
            if win.IS_WIN:
                win.set_topmost(int(self.ball.winId()))

        def pick_file(self, title: str, pattern: str) -> str:
            """4.5: choosing a file (a profile picture, say) never sends the banner away or leaves it blank: it steps
            aside while the dialog is open, then comes back exactly as it was."""
            from PyQt6.QtWidgets import QFileDialog
            if win.fullscreen_state() == 2:
                self.toast(tr("Leave your game first"), "warn")
                return ""
            self.modal = True
            self._watch.stop()
            self.hide()
            try:
                path, _ = QFileDialog.getOpenFileName(None, title, "", pattern)
            finally:
                self.modal = False
                self._was_down = True
                self.heal(force=True)
                if self.phase == "shown":
                    self._watch.start()
            return path or ""

        def heal(self, force: bool = False) -> None:
            """4.5: never stuck half drawn: shown means the banner, its pages and its place on the screen are right."""
            if getattr(self, "modal", False):
                return
            if self.phase == "shown":
                if not self.isVisible():
                    self.show()
                    if win.IS_WIN:
                        win.set_topmost(int(self.winId()))
                wa = self._area()
                if force or not wa.contains(self.geometry().adjusted(S(GLOW), S(GLOW), -S(GLOW), -S(GLOW))) \
                        or abs(self.drop.level - 1.0) > 0.01:
                    self.drop.jump(1.0)
                    self._place()
                    self._pm = None
                if force or not self.body.isVisible() or self.body.geometry().height() < S(100):
                    self._pm = None
                    self._layout_body()
                    self.body.show()
                    self.relayout()
                self.update()
            elif self.phase == "stowed" and self.isVisible():
                self.hide()
                self._show_stowed_ball()

        def _mouse_guard(self) -> None:
            """4.5: while the banner is open, every click on it is for Rubenium, never for the game behind."""
            if self.phase in ("shown", "dropping"):
                if self._through:
                    for w in (self, self.drawer):
                        hwnd = int(w.internalWinId() or 0)
                        if hwnd:
                            win.set_click_through(hwnd, False)
                    self._through = False
                return
            super()._mouse_guard()

        def _watch_outside(self) -> None:
            """A click anywhere outside the banner (the desktop, a game) sends it up into the R."""
            if self.phase != "shown" or getattr(self, "modal", False):
                return
            down = win.key_down(0x01) if win.IS_WIN else False
            if down and not self._was_down:
                from PyQt6.QtGui import QCursor
                from PyQt6.QtWidgets import QApplication
                pos = QCursor.pos()
                inside = self.frameGeometry().contains(pos) or QApplication.topLevelAt(pos) is not None
                if not inside and getattr(self, "sheet", None) is None and not self.confirm_w.isVisible():
                    self.collapse()
            self._was_down = down

        def toggle(self) -> None:
            if self.phase == "shown":
                self.collapse()
            elif self.phase == "stowed":
                self.expand()

        def ask_leave(self) -> None:
            self.ctx.leave_online()

        def start_leaving(self, then) -> None:
            """4.0: leaving is calm: the banner lifts away and fades in one smooth move, then the R floats down."""
            self._leave_then = then
            self._close_sheet()
            self.toast_w.hide()
            self.confirm_w.hide()
            self.busy_w.hide()
            self.drawer.close_now()
            self._watch.stop()
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
            self.suck.setEasingCurve(QEasingCurve.Type.InOutCubic)
            self.suck.jump(0.0)
            self.suck.to(1.0, 420)
            sfx.play("off")

        def _suck_done(self) -> None:
            if self.phase == "stowing":
                self.phase = "stowed"
                self.hide()
                self._pm = None
                return self._show_stowed_ball()
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


        # -------------------------------------------------------------- painting
        def paintEvent(self, _e) -> None:
            from .window import paint_edge, paint_shape
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            now = time.monotonic()
            if self.phase == "leaving":
                return self._paint_leave(p)
            if self.phase == "stowing":
                return self._paint_stow(p, now)
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

        def _banner(self, p: QPainter, m: QRectF, opacity: float) -> None:
            from .window import paint_shape
            p.setOpacity(max(0.0, opacity))
            path = paint_shape(p, self.ctx, m, S(ui.radius), self.ctx.glow_level() * opacity, self.devicePixelRatioF())
            if self._pm is not None:
                p.save()
                p.setClipPath(path)
                p.drawPixmap(m, self._pm, QRectF(self._pm.rect()))
                p.restore()
            p.setOpacity(1.0)

        def _paint_leave(self, p: QPainter) -> None:
            """Lifts, shrinks very slightly and fades: no spinning."""
            k = self.suck.level
            m = self._max_l
            s = 1.0 - 0.04 * k
            lift = S(70) * k * k
            w, h = m.width() * s, m.height() * s
            box = QRectF(m.center().x() - w / 2, m.top() - lift + (m.height() - h) * 0.15, w, h)
            self._banner(p, box, 1.0 - k)

        def _paint_stow(self, p: QPainter, now: float) -> None:
            """Shoots up into a wide black hole (an accretion band across the top), which closes on the R."""
            k = self.suck.level
            m = self._max_l
            hole = QPointF(m.center().x(), m.top() + S(30))
            e = min(1.0, k / 0.55) ** 2                               # fast: most of the move in the first half
            if e < 1.0:
                h = m.height() * (1 - 0.88 * e)
                w = m.width() * (1 - 0.15 * e)
                box = QRectF(m.center().x() - w / 2, m.top() - (m.height() * 0.15) * e, w, h)
                self._banner(p, box, 1.0 - e * 0.8)
            # the wide black hole: opens fast, holds, closes onto the R
            open_k = math.sin(min(1.0, k / 0.9) * math.pi) ** 0.7
            hw, hh = m.width() * 0.46 * open_k, S(22) * open_k
            if hw > 1:
                p.setPen(Qt.PenStyle.NoPen)
                halo = QRadialGradient(hole, hw)
                halo.setColorAt(0, alpha(ui.accent, 0.0))
                halo.setColorAt(0.55, alpha(ui.accent, 0.38 * open_k))
                halo.setColorAt(1, alpha(ui.accent, 0.0))
                p.save()
                p.translate(hole)
                p.scale(1.0, max(0.05, hh * 2.6 / max(1.0, hw)))
                p.setBrush(halo)
                p.drawEllipse(QPointF(0, 0), hw, hw)
                p.restore()
                rnd = random.Random(11)                               # matter streaming along the band
                for i in range(70):
                    a0 = rnd.uniform(0, math.tau)
                    rad = rnd.uniform(0.35, 1.0)
                    ang = a0 + now * (4.0 / max(0.4, rad))
                    pc = mix(ui.accent, QColor("#FFFFFF"), rnd.uniform(0.0, 0.7))
                    pc.setAlphaF(0.8 * open_k)
                    p.setBrush(pc)
                    p.drawEllipse(QPointF(hole.x() + math.cos(ang) * hw * rad, hole.y() + math.sin(ang) * hh * rad * 1.6),
                                  S(1.5), S(1.5))
                core = QRadialGradient(hole, hw * 0.55)
                core.setColorAt(0, QColor(0, 0, 0, 255))
                core.setColorAt(0.8, QColor(0, 0, 0, 230))
                core.setColorAt(1, QColor(0, 0, 0, 0))
                p.save()
                p.translate(hole)
                p.scale(1.0, max(0.05, hh / max(1.0, hw * 0.55)))
                p.setBrush(core)
                p.drawEllipse(QPointF(0, 0), hw * 0.55, hw * 0.55)
                p.restore()
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(QPen(alpha(mix(ui.accent, QColor("#FFFFFF"), 0.45), 0.85 * open_k), S(1.6)))
                p.drawEllipse(hole, hw * 0.56, hh * 1.02)
            # the R appears in the middle as the hole closes
            if k > 0.55:
                from .window import paint_ball_face, paint_edge, paint_shape
                r_k = min(1.0, (k - 0.55) / 0.45)
                d = BD() * (0.4 + 0.6 * r_k)
                shape = QRectF(hole.x() - d / 2, hole.y() - d / 2, d, d)
                p.setOpacity(r_k)
                level = self.ctx.glow_level(0.6)
                paint_shape(p, self.ctx, shape, d / 2, level, self.devicePixelRatioF())
                paint_ball_face(p, self.ctx, shape, 1.0)
                paint_edge(p, self.ctx, shape, d / 2, level)
                p.setOpacity(1.0)

        def _tick(self) -> None:
            if self.phase in ("leaving", "stowing") or self.drop.busy:
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
