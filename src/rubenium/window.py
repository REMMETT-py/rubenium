# -*- coding: utf-8 -*-
"""The ball and the card.

Rendering architecture
  * Two frameless, translucent, always-on-top tool windows that never take focus:
      BallWindow  - tiny; the only thing on screen while collapsed. It glides by moving, never repainting.
      MainWindow  - the card canvas (largest card + glow); it exists on screen only while expanded.
  * Hand-over is invisible by construction: the canvas is laid out while hidden and first paints the ball
    exactly where the real ball is, so swapping the two windows never shows a jump.
  * One master animation morphs ball <-> card purely by painting inside the fixed canvas.
  * Glow is a cached nine-slice pixmap (no strokes per frame, no QGraphicsEffect).
  * During a morph or page change the live widgets are hidden and cached snapshots are painted.
"""
from __future__ import annotations

import time

from PyQt6.QtCore import QEasingCurve, QPoint, QPointF, QRect, QRectF, QTimer, Qt
from PyQt6.QtGui import (QCursor, QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                         QRadialGradient, QRegion)
from PyQt6.QtWidgets import QFileDialog, QWidget

import math

from . import extras, win
from .core import (BD, GLOW_POWER, sfx, BG_BOTTOM, BG_TOP, CARD_W, DANGER, GLOW, PAD, RADIUS, S, TEXT, TEXT_DIM, WARN, alpha, font, mix, tr,
                   ui)
from .media import Status
from .pages2 import TEMP_TABS, make_page, visible_tabs
from .widgets import (Button, IconButton, Label, ScrollArea, Segmented, TabBar, Tween, align_slider_rows, draw_icon,
                      hbox, snapshot, vbox)

HEADER_TOP, HEADER_H, TAB_H = 12, 26, 30
CHROME_TOP = HEADER_TOP + HEADER_H + 8 + TAB_H + 10
CHROME_BOTTOM = 14
COMPACT = TAB_H + 10           # the tab row squashes away; the title and the R button stay
MUSIC_PAGES = ("home", "lyrics")
MAX_CONTENT = 540
MIN_CARD = 250
BAND = 120                 # themes decorate only this top part of the card
WINDOW_FLAGS = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
                | Qt.WindowType.NoDropShadowWindowHint
                | Qt.WindowType.WindowDoesNotAcceptFocus)      # clicking never steals focus from a game


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


# --------------------------------------------------------------------------- #
# Shared painting
# --------------------------------------------------------------------------- #
_tiles: dict = {}


def _glow_tile(radius: int, dpr: float):
    """Pre-rendered glow for a rounded square of `radius`, in physical pixels: (pixmap, cap px)."""
    key = (radius, round(dpr * 100), ui.accent.rgb(), S(GLOW))
    hit = _tiles.get(key)
    if hit is None:
        if len(_tiles) > 48:
            _tiles.clear()
        g = S(GLOW)
        cap = int(round((radius + g) * dpr))
        mid = 4
        pm = QPixmap(2 * cap + mid, 2 * cap + mid)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(dpr, dpr)
        inner = 2 * radius + mid / dpr
        rect = QRectF(g, g, inner, inner)
        layers, reach = 16, g - 1.0                 # many faint rings: bright at the edge, fading to nothing
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(layers, 0, -1):
            a = 0.013 + 0.062 * ((layers - i) / layers) ** 2
            pen = QPen(alpha(ui.accent, a), 2.0 * reach * i / layers)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawRoundedRect(rect, radius, radius)
        p.end()
        hit = _tiles[key] = (pm, cap, mid)
    return hit


def draw_glow(p: QPainter, shape: QRectF, radius: float, level: float, dpr: float) -> None:
    """Nine-slice the cached glow around `shape`."""
    r = int(max(2, round(min(radius, shape.width() / 2, shape.height() / 2))))
    pm, cap, mid = _glow_tile(r, dpr)
    g = S(GLOW)
    c = cap / dpr                                   # corner size in logical pixels
    x0, y0 = shape.left() - g, shape.top() - g
    w, h = shape.width() + 2 * g, shape.height() + 2 * g
    mw, mh = max(0.0, w - 2 * c), max(0.0, h - 2 * c)
    xs = [(x0, c, 0, cap), (x0 + c, mw, cap, mid), (x0 + c + mw, c, cap + mid, cap)]
    ys = [(y0, c, 0, cap), (y0 + c, mh, cap, mid), (y0 + c + mh, c, cap + mid, cap)]
    old = p.opacity()
    p.setOpacity(old * max(0.0, min(1.0, level)))
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    for ty, th, sy, sh in ys:
        for tx, tw, sx, sw in xs:
            if tw > 0.01 and th > 0.01 and not (sx == cap and sy == cap):
                p.drawPixmap(QRectF(tx, ty, tw, th), pm, QRectF(sx, sy, sw, sh))
    p.setOpacity(old)


def paint_shape(p: QPainter, ctx, shape: QRectF, radius: float, level: float, dpr: float) -> QPainterPath:
    """Glow + dark glass body. Returns the body path (for clipping content)."""
    if ctx.cfg["halo"]:
        power = GLOW_POWER[ctx.cfg["glow_power"] if 0 <= ctx.cfg["glow_power"] < 3 else 1]
        power = max(1.0, power)                             # two strengths: normal and strong
        draw_glow(p, shape, radius, level * min(1.0, power), dpr)
        if power > 1.0:
            draw_glow(p, shape, radius, level * (power - 1.0), dpr)
        extra = ctx.theme().get("glow", 1.0) - 1.0          # richer themes get a stronger halo
        if extra > 0.01:
            draw_glow(p, shape, radius, level * extra, dpr)
    path = QPainterPath()
    path.addRoundedRect(shape, radius, radius)
    grad = QLinearGradient(shape.topLeft(), shape.bottomLeft())
    grad.setColorAt(0.0, ui.bg_top)
    grad.setColorAt(1.0, ui.bg_bottom)
    p.fillPath(path, grad)
    tint = QLinearGradient(shape.topLeft(), QPointF(shape.left(), shape.top() + min(shape.height(), S(110))))
    tint.setColorAt(0.0, alpha(ui.accent, 0.08))
    tint.setColorAt(1.0, alpha(ui.accent, 0.0))
    p.fillPath(path, tint)
    return path


def paint_edge(p: QPainter, ctx, shape: QRectF, radius: float, level: float) -> None:
    extras.paint_theme_edge(p, ctx.theme(), shape, radius, level, ctx.cfg["halo"], time.monotonic())


def paint_ball_face(p: QPainter, ctx, shape: QRectF, opacity: float) -> None:
    p.save()
    p.setOpacity(p.opacity() * opacity)
    d = min(shape.width(), shape.height())
    c = QPointF(shape.left() + d / 2, shape.top() + d / 2)
    st = ctx.state
    if ctx.cfg["ring"] and st.has_track and st.duration_ms > 0:
        frac = max(0.0, min(1.0, ctx.position_ms() / st.duration_ms))
        ring = QRectF(c.x() - d / 2, c.y() - d / 2, d, d).adjusted(S(5), S(5), -S(5), -S(5))
        extras.paint_ring(p, ring, ctx.ring_style(), frac, ui.accent, S(2.2))
    box = QRectF(c.x() - d / 2, c.y() - d / 2 - d * 0.02, d, d)
    extras.paint_r(p, box, d, ctx.ball_style(), ui.accent, time.monotonic())
    if ctx.overlay_active():
        p.setPen(QPen(ui.bg_top, S(1.5)))
        p.setBrush(ui.accent)
        p.drawEllipse(QPointF(c.x() + d * 0.33, c.y() - d * 0.33), S(4), S(4))
    p.restore()


def work_area(point: QPoint) -> QRect:
    screen = QGuiApplication.screenAt(point) or QGuiApplication.primaryScreen()
    return screen.availableGeometry()


# --------------------------------------------------------------------------- #
# The ball
# --------------------------------------------------------------------------- #
class BallWindow(QWidget):
    def __init__(self, owner: "MainWindow") -> None:
        super().__init__()
        self.owner, self.ctx = owner, owner.ctx
        self.setWindowTitle("Rubenium")
        self.setWindowFlags(WINDOW_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.center = QPoint(200, 200)
        self.hover = Tween(self, 0.0, self.update, QEasingCurve.Type.OutBack)
        self.press = Tween(self, 0.0, self.update)
        self.appear = Tween(self, 0.0, self.update, QEasingCurve.Type.OutBack)
        self._glide = Tween(self, 1.0, self._on_glide, QEasingCurve.Type.InOutCubic)
        self._glide.finished.connect(self._glide_done)
        self._then = None
        self._from, self._to = QPoint(), QPoint()
        self._press_pos = None
        self._moved = False
        self.charge = Tween(self, 0.0, self.update, QEasingCurve.Type.Linear)     # hold-to-open progress
        self.charge.finished.connect(self._charged)

    # -- hold to open
    def _charged(self) -> None:
        if self._press_pos is None or self._moved or self.charge.target < 1.0 or self.charge.level < 0.999:
            return
        self._press_pos = None
        self.press.to(0.0, 200)
        sfx.play("on")
        self.owner.expand()
        QTimer.singleShot(450, lambda: self.charge.jump(0.0))      # reset once the ball is out of sight

    def cancel_press(self) -> None:
        """Drop a press in progress (a game took the mouse)."""
        if self._press_pos is not None and not self._moved:
            self._press_pos = None
            self.press.to(0.0, 150)
            self.charge.to(0.0, 150)

    # -- geometry
    def rect_global(self) -> QRect:
        d = BD()
        return QRect(self.center.x() - d // 2, self.center.y() - d // 2, d, d)

    def place(self) -> None:
        g = S(GLOW)
        self.setGeometry(self.rect_global().adjusted(-g, -g, g, g))

    def set_center(self, c: QPoint) -> None:
        self.center = QPoint(c)
        self.place()

    def clamp(self) -> None:
        wa = work_area(self.center)
        r = BD() // 2 + S(6)
        self.center = self.keep_clear(QPoint(max(wa.left() + r, min(wa.right() - r, self.center.x())),
                                             max(wa.top() + r, min(wa.bottom() - r, self.center.y()))))

    @staticmethod
    def _clear_h() -> int:
        """Height of the strip at the top of the screen where windows have their close / minimise buttons."""
        return max(52, S(52))

    @classmethod
    def keep_clear(cls, c: QPoint) -> QPoint:
        """The ball may never sit in the top-right corner of a screen, over the close buttons of windows:
        anywhere in that area it is moved straight down, just below it."""
        wa = work_area(c)
        r = BD() // 2
        zone_w = max(200, S(200))
        if c.x() + r > wa.right() - zone_w and c.y() - r < wa.top() + cls._clear_h():
            return QPoint(c.x(), wa.top() + cls._clear_h() + r)
        return QPoint(c)

    @classmethod
    def _top_y(cls, wa: QRect) -> int:
        """Top spots sit a little lower, clear of the close / minimise buttons of windows under them."""
        return wa.top() + cls._clear_h() + BD() // 2

    @classmethod
    def corner_point(cls, wa: QRect, left: bool, top: bool) -> QPoint:
        m = S(14) + BD() // 2
        return QPoint(wa.left() + m if left else wa.right() - m, cls._top_y(wa) if top else wa.bottom() - m)

    @classmethod
    def snap_points(cls, wa: QRect) -> list:
        """The four corners and the middle of each edge."""
        m = S(14) + BD() // 2
        top, bottom = cls._top_y(wa), wa.bottom() - m
        left, right = wa.left() + m, wa.right() - m
        cx, cy = wa.center().x(), (top + bottom) // 2
        return [QPoint(left, top), QPoint(right, top), QPoint(left, bottom), QPoint(right, bottom),
                QPoint(cx, top), QPoint(cx, bottom), QPoint(left, cy), QPoint(right, cy)]

    def snap_target(self):
        """The spot the ball locks into when it is dropped close to one, else None (it stays where dropped)."""
        best, reach = None, S(64)
        for pt in self.snap_points(work_area(self.center)):
            dist = math.hypot(pt.x() - self.center.x(), pt.y() - self.center.y())
            if dist <= reach:
                best, reach = pt, dist
        return best

    # -- glide (the window only moves: nothing is repainted, so it is perfectly smooth)
    @property
    def gliding(self) -> bool:
        return self._glide.busy

    def _glide_done(self) -> None:
        then, self._then = self._then, None
        if then is not None:
            then()
        else:
            self.owner.save_position()

    def glide_to(self, target: QPoint, then=None, fast: bool = False) -> None:
        target = self.keep_clear(target)
        self._from, self._to = QPoint(self.center), QPoint(target)
        self._then = then
        dist = (target - self.center).manhattanLength()
        if dist < 3:
            self.set_center(target)
            self._glide_done()
            return
        self._glide.jump(0.0)
        self._glide.to(1.0, int(min(300, 150 + dist * 0.18)) if fast else int(min(520, 260 + dist * 0.35)))

    def _on_glide(self) -> None:
        t = self._glide.level
        ex, ey = t ** 0.7, t ** 1.6                         # x leads, y follows: a soft curve into the corner
        dx, dy = self._to.x() - self._from.x(), self._to.y() - self._from.y()
        if abs(dy) > abs(dx):
            ex, ey = ey, ex
        self.set_center(QPoint(round(self._from.x() + dx * ex), round(self._from.y() + dy * ey)))

    # -- painting
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        a = self.appear.level
        if a < 1.0:
            p.setOpacity(max(0.0, min(1.0, a)))
        k = (0.6 + 0.4 * min(1.15, a)) * (1 + 0.07 * self.hover.level - 0.06 * self.press.level)
        g, d = S(GLOW), BD()
        w = d * k
        shape = QRectF(g + d / 2 - w / 2, g + d / 2 - w / 2, w, w)
        level = self.ctx.glow_level(max(0.0, self.hover.level))
        paint_shape(p, self.ctx, shape, w / 2, level, self.devicePixelRatioF())
        paint_ball_face(p, self.ctx, shape, 1.0)
        paint_edge(p, self.ctx, shape, w / 2, level)
        c = max(0.0, min(1.0, self.charge.level))
        if c > 0.0:                                         # hold to open: a circle fills around the edge
            ring = shape.adjusted(S(1.5), S(1.5), -S(1.5), -S(1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            for width, a in ((S(6), 0.18), (S(3), 1.0)):
                pen = QPen(alpha(mix(ui.accent, QColor("#FFFFFF"), 0.55), a), width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawArc(ring, 90 * 16, int(-360 * 16 * c))

    # -- mouse: hold (or click) opens, drag moves (kept on screen)
    def enterEvent(self, e) -> None:
        self.hover.to(1.0, 260)

    def leaveEvent(self, e) -> None:
        self.hover.to(0.0, 320)

    def mousePressEvent(self, e) -> None:
        if win.mouse_captured():               # a game has the mouse: this click was not meant for Rubenium
            return
        if e.button() == Qt.MouseButton.LeftButton and not self.gliding:
            self._press_pos = e.globalPosition().toPoint()
            self._origin = QPoint(self.center)
            self._moved = False
            self.press.to(1.0, 80)
            if self.ctx.cfg["hold_open"]:
                self.charge.jump(0.0)
                self.charge.to(1.0, max(200, min(1000, int(self.ctx.cfg["hold_ms"]))))

    def mouseMoveEvent(self, e) -> None:
        if self._press_pos is None:
            return
        pos = e.globalPosition().toPoint()
        if not self._moved and (pos - self._press_pos).manhattanLength() >= 5:
            self._moved = True
            self.charge.to(0.0, 120)                        # dragging, not opening
        if self._moved:
            self.center = self._origin + (pos - self._press_pos)      # stored origin + total delta: no drift
            self.clamp()
            self.place()

    def mouseReleaseEvent(self, e) -> None:
        if self._press_pos is None:
            return
        self._press_pos = None
        self.press.to(0.0, 200)
        if self._moved:
            target = self.snap_target()
            if target is not None:
                self.glide_to(target, fast=True)           # saves the position when it arrives
            else:
                self.owner.save_position()
        elif self.ctx.cfg["hold_open"]:
            self.charge.to(0.0, 160)                        # let go too early: nothing opens
        else:
            self.owner.expand()


class Toast(QWidget):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._text, self._kind = "", "ok"
        self._fade = Tween(self, 0.0, self._changed)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._fade.to(0.0, 260))
        self.hide()

    def _changed(self) -> None:
        if self._fade.level <= 0.001 and self._fade.target == 0.0:
            self.hide()
        self.update()

    def show_text(self, text: str, kind: str, card: QRectF) -> None:
        self._text, self._kind = text, kind
        from PyQt6.QtGui import QFontMetrics
        fm = QFontMetrics(font(11.5, QFont.Weight.DemiBold))
        max_w = int(card.width() - S(28))
        br = fm.boundingRect(0, 0, max_w - S(34), 1000, int(Qt.TextFlag.TextWordWrap), text)
        w, h = min(max_w, br.width() + S(38)), br.height() + S(16)
        self.setGeometry(int(card.center().x() - w / 2), int(card.bottom() - h - S(12)), int(w), int(h))
        self.show()
        self.raise_()
        self._fade.to(1.0, 180)
        self._timer.start(2400 + 30 * len(text))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._fade.level
        p.setOpacity(t)
        p.translate(0, (1 - t) * S(8))
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        col = {"ok": ui.accent, "warn": QColor(WARN), "error": QColor(DANGER)}.get(self._kind, ui.accent)
        p.setPen(QPen(alpha(col, 0.55), 1))
        p.setBrush(QColor(22, 27, 28, 250))
        p.drawRoundedRect(r, S(10), S(10))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(S(14), r.center().y()), S(3.5), S(3.5))
        p.setPen(QColor(TEXT))
        p.setFont(font(11.5, QFont.Weight.DemiBold))
        p.drawText(r.adjusted(S(26), 0, -S(8), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap), self._text)


class Confirm(QWidget):
    """A short question with Yes / No, shown on the card itself."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self._text = ""
        self._yes_cb = None
        self._yes = Button(tr("Yes"), "primary", 28, parent=self)
        self._no = Button(tr("No"), "ghost", 28, parent=self)
        self._no_cb = None
        self._yes.clicked.connect(self._accept)
        self._no.clicked.connect(self._decline)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self._rise = Tween(self, 1.0, self.update)
        self.hide()

    def ask(self, text: str, on_yes, card: QRectF, yes: str = "", no: str = "", persistent: bool = False,
            on_no=None) -> None:
        again = self.isVisible() and persistent
        self._text, self._yes_cb, self._no_cb = text, on_yes, on_no
        self._yes.set_text(yes or tr("Yes"))
        self._no.set_text(no or tr("No"))
        w, h = int(card.width() - S(28)), S(46)
        self.setGeometry(int(card.left() + S(14)), int(card.bottom() - h - S(12)), w, h)
        yw = max(S(58), self._yes.sizeHint().width())
        nw = max(S(58), self._no.sizeHint().width())
        self._no.setGeometry(w - nw - S(9), S(9), nw, S(28))
        self._yes.setGeometry(w - nw - yw - S(15), S(9), yw, S(28))
        self.show()
        self.raise_()
        if not again:
            self._rise.jump(0.0)
            self._rise.to(1.0, 180)
        self.update()
        if persistent:
            self._timer.stop()                  # stays until the user answers
        else:
            self._timer.start(7000)

    def _accept(self) -> None:
        cb, self._yes_cb, self._no_cb = self._yes_cb, None, None
        self.hide()
        if cb:
            cb()

    def _decline(self) -> None:
        cb, self._yes_cb, self._no_cb = self._no_cb, None, None
        self.hide()
        if cb:
            cb()

    def mousePressEvent(self, e) -> None:
        e.accept()                      # never drags the card

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._rise.level)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha(WARN, 0.6), 1))
        p.setBrush(QColor(22, 27, 28, 252))
        p.drawRoundedRect(r, S(10), S(10))
        p.setPen(QColor(TEXT))
        p.setFont(font(12, QFont.Weight.DemiBold))
        room = self._yes.x() - S(20)
        box = QRectF(S(12), 0, room, self.height())
        if p.fontMetrics().horizontalAdvance(self._text) <= room:
            p.drawText(box, int(Qt.AlignmentFlag.AlignVCenter), self._text)
        else:                                   # too long for one line: two smaller lines, nothing cut
            p.setFont(font(10.5, QFont.Weight.DemiBold))
            p.drawText(box, int(Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap), self._text)


class Busy(QWidget):
    """A short loading screen over the card: fades in, spins, fades out. Blocks clicks while it shows."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self._text = ""
        self._fade = Tween(self, 0.0, self._faded)
        self._spin = QTimer(self)
        self._spin.setInterval(16)
        self._spin.timeout.connect(self.update)
        self._since = 0.0
        self._then = None
        self.hide()

    def start(self, text: str, card: QRectF) -> None:
        self._text = text
        self.setGeometry(card.toAlignedRect())
        if not self.isVisible() or self._fade.target < 0.5:
            self._since = time.monotonic()
            self.show()
            self.raise_()
            self._fade.to(1.0, 180)
            self._spin.start()
        self.update()

    def finish(self, then=None) -> None:
        if not self.isVisible():
            if then:
                then()
            return
        self._then = then
        wait = max(0, int((0.7 - (time.monotonic() - self._since)) * 1000))   # never just a flash
        QTimer.singleShot(wait, lambda: self._fade.to(0.0, 240))

    def _faded(self) -> None:
        if self._fade.level <= 0.001 and self._fade.target == 0.0:
            self._spin.stop()
            self.hide()
            then, self._then = self._then, None
            if then:
                then()
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()

    def wheelEvent(self, e) -> None:
        e.accept()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._fade.level
        r = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(r, S(ui.radius), S(ui.radius))
        p.fillPath(path, QColor(ui.bg_top.red(), ui.bg_top.green(), ui.bg_top.blue(), int(232 * t)))
        p.setOpacity(t)
        c = QPointF(r.center().x(), r.center().y() - S(10))
        rad = S(15)
        pen = QPen(alpha("#FFFFFF", 0.12), S(3))
        p.setPen(pen)
        p.drawEllipse(c, rad, rad)
        pen = QPen(ui.accent, S(3))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        start = int((time.monotonic() * 360) % 360)
        p.drawArc(QRectF(c.x() - rad, c.y() - rad, 2 * rad, 2 * rad), -start * 16, 100 * 16)
        p.setPen(QColor(TEXT))
        p.setFont(font(12.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(r.left(), c.y() + rad + S(10), r.width(), S(22)), int(Qt.AlignmentFlag.AlignCenter), self._text)


class PreviewDrawer(QWidget):
    """A small black panel that slides out beside the card to preview a locked theme."""

    def __init__(self, owner: "MainWindow") -> None:
        super().__init__()
        self.owner, self.ctx = owner, owner.ctx
        self.setWindowFlags(WINDOW_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.theme = extras.THEMES[0]
        self._side = 1                                   # 1 = right of the card, -1 = left
        self._slide = Tween(self, 0.0, self._moved, QEasingCurve.Type.OutCubic)
        self._close = Button(tr("Close"), "ghost", 28, parent=self)
        self._close.clicked.connect(self.close_drawer)
        self._buy = Button(tr("Buy"), "primary", 30, parent=self)
        self._buy.clicked.connect(self._buy_theme)
        self._buy.hide()                              # themes unlock with time: nothing to buy
        self._frame = QTimer(self)
        self._frame.setInterval(33)
        self._frame.timeout.connect(self.update)
        self._auto = QTimer(self)
        self._auto.setSingleShot(True)
        self._auto.timeout.connect(self.close_drawer)
        self._sparks: list = []

    def is_open(self) -> bool:
        return self.isVisible() and self._slide.target > 0.5

    def open_for(self, theme: dict) -> None:
        self.theme = theme
        w, h, gap = S(214), S(276), S(6)
        card = self.owner.card_global()
        wa = work_area(card.center())
        self._side = 1 if card.right() + gap + w <= wa.right() else -1
        x = card.right() + gap if self._side == 1 else card.left() - gap - w
        y = max(wa.top() + S(8), min(card.top() + S(70), wa.bottom() - h - S(8)))
        self.setGeometry(x, y, w, h)
        tile = self._tile()
        self._sparks = extras.theme_sparkles(theme, tile.width(), tile.height())
        self._close.setFixedSize(w - S(28), S(28))
        self._buy.setFixedSize(w - S(28), S(30))
        self._slide.jump(0.0)
        self._slide.target = 1.0
        self.ctx.preview_theme(theme["id"])
        shop = str(theme.get("id", "")).startswith("theme:")
        self._buy.setVisible(shop)
        if shop:
            from .wallet import coins_text
            self._buy.set_text(tr("Buy for {n} coins", n=coins_text(int(self.ctx.econ.shop_price(theme["id"]) or 0))))
        self.show()
        self._slide.to(1.0, 260)
        self._frame.start()
        self._auto.start(15000)

    def close_drawer(self) -> None:
        if self.isVisible() and self._slide.target != 0.0:
            self._auto.stop()
            self._slide.to(0.0, 200)
            self.ctx.preview_theme("")

    def close_now(self) -> None:
        if self.isVisible():
            self._slide.jump(0.0)

    def _buy_theme(self) -> None:
        """A shop theme: open its page in the shop, where it can be bought."""
        tid = str(self.theme.get("id", ""))
        if tid.startswith("theme:"):
            from .bazaar import SHOP_KINDS
            ctx = self.ctx
            ctx.shop_tab, ctx.shop_kind, ctx.shop_design = 1, SHOP_KINDS.index("theme"), tid.split(":", 1)[1]
            self.close_drawer()
            if ctx.window.current == "themes":
                ctx.reload_page()
            else:
                ctx.window.goto("themes")

    def _offset(self) -> float:
        return -self._side * self.width() * (1.0 - self._slide.level)

    def _tile(self) -> QRectF:
        return QRectF(S(14), S(38), self.width() - S(28), S(104))

    def _moved(self) -> None:
        if self._slide.level <= 0.001 and self._slide.target == 0.0:
            self._frame.stop()
            self._auto.stop()
            self.hide()
            if self.ctx._preview:
                self.ctx.preview_theme("")
            return
        self._close.move(int(S(14) + self._offset()), self.height() - S(40))
        self._buy.move(int(S(14) + self._offset()), self.height() - S(76))
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(self._offset(), 0)
        th, now = self.theme, time.monotonic()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha("#FFFFFF", 0.12), 1))
        p.setBrush(QColor(6, 8, 9))
        p.drawRoundedRect(r, S(14), S(14))
        p.setPen(QColor(TEXT))
        p.setFont(font(10, QFont.Weight.Bold, 2.2))
        p.drawText(QRectF(S(15), S(11), 150, S(18)), int(Qt.AlignmentFlag.AlignVCenter), tr("PREVIEW"))
        p.save()
        p.translate(self.width() - S(24), S(20))
        p.scale(S(13) / 20, S(13) / 20)
        draw_icon(p, "lock", QColor(TEXT_DIM))
        p.restore()

        tile = self._tile()
        rad = S(10)
        path = QPainterPath()
        path.addRoundedRect(tile, rad, rad)
        g = QLinearGradient(tile.topLeft(), tile.bottomLeft())
        g.setColorAt(0, ui.bg_top)
        g.setColorAt(1, ui.bg_bottom)
        p.fillPath(path, g)
        p.save()
        p.setClipPath(path)
        pm = extras.theme_pattern(th, int(tile.width()), int(tile.height()), ui.accent, self.devicePixelRatioF(),
                                  ui.scale * 0.62)
        if pm is not None:
            p.drawPixmap(tile.topLeft(), pm)
        extras.paint_sparkles(p, self._sparks, tile.left(), tile.top(), ui.accent, now, ui.scale * 0.8)
        p.restore()
        level = 0.75 + 0.25 * math.sin(now * 2.1)
        extras.paint_theme_edge(p, th, tile, rad, level, True, now)

        p.setPen(QColor(TEXT))
        p.setFont(font(15, QFont.Weight.Bold))
        p.drawText(QRectF(S(15), tile.bottom() + S(9), self.width() - S(30), S(22)),
                   int(Qt.AlignmentFlag.AlignVCenter), tr(th["name"]))
        from .shop import paint_price
        shop = str(th.get("id", "")).startswith("theme:")
        paint_price(p, QRectF(S(15), tile.bottom() + S(34), self.width() - S(30), S(18)),
                    int(self.ctx.econ.shop_price(th["id"]) or 0) if shop else
                    self.ctx.wallet.hours_for(f"theme:{th['id']}"), 11.5, "#E8C26A", centre=False, hours=not shop)


class DeleteDialog(QWidget):
    """Delete the account for good: type the username, then click twice and hold. Its own small window, because
    typing needs the keyboard and the menu never takes it from a game."""

    def __init__(self, ctx) -> None:
        super().__init__()
        from PyQt6.QtWidgets import QLineEdit
        from .pages import HoldButton
        self.ctx, self.online = ctx, ctx.online
        self.setWindowTitle("Rubenium")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedWidth(S(340))
        lay = vbox(self, 8, (18, 18, 18, 18))
        lay.addWidget(Label(tr("Delete account"), 16, bold=True))
        lay.addWidget(Label(tr("This deletes your account for good: username, time played and everything you own. "
                               "It cannot be undone."), 12, TEXT_DIM, wrap_w=S(304)))
        lay.addWidget(Label(tr("Type {name} to confirm", name=self.online.username()), 12, TEXT, wrap_w=S(304)))
        self.edit = QLineEdit()
        self.edit.setMaxLength(10)
        self.edit.setFixedHeight(S(34))
        self.edit.setStyleSheet(
            f"QLineEdit {{ background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10);"
            f" border-radius: {S(9)}px; padding: 0 {S(10)}px; color: {TEXT}; font-size: {S(13)}px; }}"
            f"QLineEdit:focus {{ border: 1px solid rgba(255,255,255,0.45); }}")
        self.edit.textChanged.connect(self._typed)
        lay.addWidget(self.edit)
        self.hint = Label("", 11, DANGER)
        self.hint.setFixedHeight(S(16))
        lay.addWidget(self.hint)
        self.hold = HoldButton(tr("Delete my account"))
        self.hold.setEnabled(False)
        self.hold.confirmed.connect(self._delete)
        lay.addWidget(self.hold)
        cancel = Button(tr("Cancel"), "ghost", 34)
        cancel.clicked.connect(self.close)
        lay.addWidget(cancel)
        self.online.answered.connect(self._answered)
        self.adjustSize()
        area = work_area(ctx.window.card_global().center())
        self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()

    def _typed(self, text: str) -> None:
        self.hold.setEnabled(text == self.online.username())      # exactly, capitals included

    def _delete(self) -> None:
        if self.edit.text() != self.online.username():
            return
        self.hold.setEnabled(False)
        self.edit.setEnabled(False)
        self.hint.set_color(TEXT_DIM)
        self.hint.set_text(tr("One moment…"))
        self.online.delete_account()

    def _answered(self, what: str, ok: bool, msg: str) -> None:
        if what != "delete":
            return
        if ok:
            self.close()
            self.ctx.quit()
        else:
            self.edit.setEnabled(True)
            self._typed(self.edit.text())
            self.hint.set_color(DANGER)
            self.hint.set_text(tr(msg))

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.close()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(alpha(DANGER, 0.55), 1.2))
        p.setBrush(QColor(12, 15, 16, 252))
        p.drawRoundedRect(r, S(16), S(16))


class AccountPanel(QWidget):
    """Log in / Create account, shown under the welcome card until someone is logged in."""

    def __init__(self, welcome) -> None:
        super().__init__(welcome)
        from PyQt6.QtWidgets import QLineEdit
        self.w, self.online = welcome, welcome.ctx.online
        self.mode = 0                                  # 0 log in, 1 create account
        self._free = ""                                # the last name the server said is free
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        self.fx = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.fx)
        lay = vbox(self, 8)
        self.seg = Segmented([tr("Log in"), tr("Create account")], 0)
        self.seg.changed.connect(self._mode)
        lay.addWidget(self.seg)
        css = (f"QLineEdit {{ background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10);"
               f" border-radius: {S(9)}px; padding: 0 {S(10)}px; color: {TEXT}; font-size: {S(13)}px;"
               f" selection-background-color: rgba(255,255,255,0.25); }}"
               f"QLineEdit:focus {{ border: 1px solid rgba(255,255,255,0.45); }}")
        self.user = QLineEdit()
        self.user.setPlaceholderText(tr("Username"))
        self.user.setMaxLength(10)
        self.pw = QLineEdit()
        self.pw.setPlaceholderText(tr("Password"))
        self.pw.setMaxLength(72)
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        for edit in (self.user, self.pw):
            edit.setFixedHeight(S(34))
            edit.setStyleSheet(css)
            edit.returnPressed.connect(self._submit)
        self.eye = Button(tr("Show"), "quiet", 34)
        self.eye.setFixedWidth(max(S(64), self.eye.sizeHint().width()))
        self.eye.clicked.connect(self._eye)
        line = hbox(spacing=6)
        line.addWidget(self.pw, 1)
        line.addWidget(self.eye)
        lay.addWidget(self.user)
        lay.addLayout(line)
        self.hint = Label("", 11, TEXT_DIM)
        self.hint.setFixedHeight(S(16))
        hl = hbox(spacing=4)
        hl.addWidget(self.hint, 1)
        self.forgot = Button(tr("Forgot password?"), "quiet", 18)
        self.forgot.setFixedWidth(max(S(110), self.forgot.sizeHint().width()))
        self.forgot.clicked.connect(self._forgot)
        hl.addWidget(self.forgot)
        lay.addLayout(hl)
        self._reset_poll = QTimer(self)
        self._reset_poll.setInterval(30000)
        self._reset_poll.timeout.connect(self._reset_check)
        if welcome.ctx.cfg["reset_rid"]:
            self._reset_poll.start()
            QTimer.singleShot(1500, self._reset_check)
        self.go = Button(tr("Log in"), "primary", 38)
        self.go.clicked.connect(self._submit)
        lay.addWidget(self.go)
        self._wait = QTimer(self)                      # ask the server only when typing pauses
        self._wait.setSingleShot(True)
        self._wait.setInterval(450)
        self._wait.timeout.connect(self._ask_free)
        self.user.textChanged.connect(self._typed)
        self.pw.textChanged.connect(self._typed)
        self.online.answered.connect(self._answered)
        self.hide()

    def place(self) -> None:
        w, h = S(300), S(184)
        top = self.w.card_top() + S(self.w.CH) * 0.52
        self.setGeometry(int(self.w.width() / 2 - w / 2), int(top), w, h)
        out = self.w.out_level()
        self.fx.setOpacity(max(0.0, min(1.0, (out - 0.5) / 0.5)))       # the card opens first, then the form
        self.setVisible(out > 0.51 and self.w.phase == "card")

    def sync(self) -> None:
        self.place()
        if not self.online.logged_in() and self.w.phase == "card":
            self.user.setFocus()

    def _say(self, text: str, colour: str = TEXT_DIM) -> None:
        self.hint.set_color(colour)
        self.hint.set_text(text)

    def _mode(self, i: int) -> None:
        self.mode = i
        self.go.set_text(tr("Create account") if i else tr("Log in"))
        self.forgot.setVisible(not i)
        self._typed()

    # forgot password: a request goes to the admin, who checks it is really you
    def _forgot(self) -> None:
        from .bazaar import AskDialog
        ctx = self.w.ctx

        def got_name(name: str, dlg) -> None:
            dlg.close()

            def got_msg(msg: str, dlg2) -> None:
                def sent(ok: bool, rid) -> None:
                    if not ok:
                        return dlg2.say(tr(str(rid)))
                    dlg2.close()
                    ctx.cfg["reset_rid"], ctx.cfg["reset_name"] = str(rid), name
                    ctx.cfg.save()
                    self._reset_poll.start()
                    self._say(tr("Sent to the admin. Keep Rubenium open: the answer shows here."), ui.accent.name())
                self.online.ask_reset(name, msg, sent)
            ctx._ask = AskDialog(ctx, tr("Help the admin check it is you"), tr("When you joined, your best item…"),
                                 tr("Send"), got_msg, 200,
                                 tr("Only the admin reads this. Say something only the real owner knows."))
        ctx._ask = AskDialog(ctx, tr("Forgot password?"), tr("Your username"), tr("Next"), got_name, 10,
                             tr("The admin gets your request with details to check it is really you, then gives you "
                                "a new password. Use the PC you play on."))

    def _reset_check(self) -> None:
        ctx = self.w.ctx
        rid = ctx.cfg["reset_rid"]
        if not rid or self.online.logged_in():
            return self._reset_poll.stop()

        def got(ok: bool, ans) -> None:
            if not ok or not isinstance(ans, dict):
                return
            if ans.get("state") == "done" and ans.get("password"):
                self._reset_poll.stop()
                self.seg.set_index(0) if hasattr(self.seg, "set_index") else None
                self.user.setText(ctx.cfg["reset_name"])
                self.pw.setText(ans["password"])
                ctx.cfg["reset_rid"] = ""
                ctx.cfg.save()
                self._say(tr("The admin gave you a new password: it is filled in. Change it in Settings."), ui.accent.name())
            elif ans.get("state") == "refused":
                self._reset_poll.stop()
                ctx.cfg["reset_rid"] = ""
                ctx.cfg.save()
                self._say(tr("The admin could not confirm it was you."), DANGER)
        self.online.reset_status(rid, got)

    def _eye(self) -> None:
        from PyQt6.QtWidgets import QLineEdit
        hidden = self.pw.echoMode() == QLineEdit.EchoMode.Password
        self.pw.setEchoMode(QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password)
        self.eye.set_text(tr("Hide") if hidden else tr("Show"))

    def _typed(self) -> None:
        from .online import USERNAME_RE, password_strength
        name, pw = self.user.text(), self.pw.text()
        self._wait.stop()
        if not self.mode:
            return self._say("")
        if name and not USERNAME_RE.match(name):
            return self._say(tr("3 to 10 letters or numbers"), WARN)
        if name and name.lower() != self._free.lower():
            self._say(tr("Checking…"))
            return self._wait.start()
        if pw:
            level = password_strength(pw)
            return self._say([tr("Password too short (8 or more)"), tr("Password: weak"), tr("Password: good"),
                              tr("Password: strong")][level], [WARN, WARN, TEXT_DIM, ui.accent.name()][level])
        self._say(tr("Username is free") if name else "", ui.accent.name())

    def _ask_free(self) -> None:
        from .online import USERNAME_RE
        if self.mode and USERNAME_RE.match(self.user.text()):
            self.online.check_free(self.user.text())

    def _answered(self, what: str, ok: bool, msg: str) -> None:
        if what.startswith("free:"):
            if what[5:] != self.user.text() or not self.mode:
                return
            if ok:
                self._free = what[5:]
                return self._typed()
            if msg == "This username is taken":
                return self._say(tr(msg), DANGER)
            self._free = what[5:]                      # could not check now: creating the account will tell
            return self._typed()
        self.go.setEnabled(True)
        if ok:
            sfx.play("on")
            self.pw.clear()
            self._free = ""
            self.w.setFocus()
        else:
            sfx.play("off")
            self._say(tr(msg), DANGER)

    def _submit(self) -> None:
        from .online import PASSWORD_MIN, USERNAME_RE
        name, pw = self.user.text().strip(), self.pw.text()
        if self.online.busy:
            return
        if not USERNAME_RE.match(name):
            return self._say(tr("3 to 10 letters or numbers"), WARN)
        if len(pw) < PASSWORD_MIN:
            return self._say(tr("Password too short (8 or more)"), WARN)
        self.go.setEnabled(False)
        self._say(tr("One moment…"))
        (self.online.sign_up if self.mode else self.online.log_in)(name, pw)

    def mousePressEvent(self, e) -> None:
        e.accept()


class Welcome(QWidget):
    """The start-up screen: a welcome card with one Launch button. Launch folds the card into a round R,
    a ring loads around it, then it flies to where the ball lives and becomes the ball."""
    CW, CH, BIG = 440, 250, 92

    def __init__(self, ctx, on_done) -> None:
        super().__init__()
        self.ctx, self._on_done = ctx, on_done
        self.setWindowTitle("Rubenium")
        # the start screen is a normal window: it is not pinned over every app (the ball and the menu are)
        self.setWindowFlags(WINDOW_FLAGS & ~Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.phase = "card"                      # card -> fold -> ring -> fly -> done
        self.appear = Tween(self, 0.0, self.update, QEasingCurve.Type.OutCubic)
        self.fold = Tween(self, 0.0, self.update, QEasingCurve.Type.InOutCubic)
        self.ring = Tween(self, 0.0, self.update, QEasingCurve.Type.InOutCubic)
        self.fly = Tween(self, 0.0, self._on_fly, QEasingCurve.Type.InOutCubic)
        self.hover = Tween(self, 0.0, self.update)
        self.press = Tween(self, 0.0, self.update)
        self.fold.finished.connect(self._folded)
        self.ring.finished.connect(self._loaded)
        self.fly.finished.connect(self._landed)
        self._down = False
        self._from = self._to = QPoint()
        self._clock = QTimer(self)
        self._clock.setTimerType(Qt.TimerType.PreciseTimer)
        self._clock.setInterval(16)
        self._clock.timeout.connect(self.update)
        self._logout_x, self._logout_w = 0.0, 0.0
        # The card is a little taller with a name under Launch, and taller still while it holds the login form.
        self.tall = Tween(self, 0.0, self._relayout, QEasingCurve.Type.InOutCubic)
        # Logged in: no button to press. A line runs around the card for 5 seconds, then Rubenium starts.
        self.count = Tween(self, 0.0, self._counted, QEasingCurve.Type.Linear)
        self.panel = AccountPanel(self)
        self.ctx.online.changed.connect(self._account_changed)

    IN, OUT = 0, 92                           # extra card height: logged in (name line) / logged out (form)

    def logged_in(self) -> bool:
        return self.ctx.online.logged_in()

    def _extra(self) -> float:
        return float(S(self.IN) if self.logged_in() else S(self.OUT))

    def out_level(self) -> float:
        """0 = the Launch view, 1 = the login form (in between while the card changes size)."""
        return max(0.0, min(1.0, (self.tall.level - S(self.IN)) / max(1.0, float(S(self.OUT) - S(self.IN)))))

    def card_h(self) -> float:
        return S(self.CH) + self.tall.level

    def card_top(self) -> float:
        return self.height() / 2 - self.card_h() / 2

    def _relayout(self) -> None:
        self.panel.place()
        self.update()

    COUNT_MS = 3000

    def _countdown(self) -> None:
        """Start (logged in) or stop (logged out) the 5 second line around the card."""
        self.count.jump(0.0)
        if self.logged_in() and self.phase == "card":
            self.count.to(1.0, self.COUNT_MS)

    def _counted(self) -> None:
        if self.count.level >= 0.999 and self.phase == "card" and self.logged_in():
            self.launch()
        self.update()

    def _account_changed(self) -> None:
        if self.phase == "card":
            self.tall.to(self._extra(), 420)
            self.panel.sync()
            self._countdown()
            self.update()

    def _take_keyboard(self) -> None:
        """Typing needs the keyboard: this window may take focus (it is the start screen)."""
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.show()
        self.raise_()
        self.activateWindow()

    def _link_rect(self) -> QRectF:
        """The small "Name · Log out" line under the Launch button, inside the card."""
        top = self.card_top() + S(self.CH) * 0.74 + S(12)
        return QRectF(self.width() / 2 - S(150), top, S(300), S(20))

    def start(self) -> None:
        ball = self.ctx.window.ball
        wa = work_area(ball.center)
        m = S(GLOW) + S(14)
        w, h = S(self.CW) + 2 * m, S(self.CH) + S(self.OUT) + 2 * m + S(16)
        self.setGeometry(wa.center().x() - w // 2, wa.center().y() - h // 2, w, h)
        self.tall.jump(self._extra())
        self.panel.place()
        if not self.logged_in():
            self._take_keyboard()
        self.show()
        self.panel.sync()
        QTimer.singleShot(450, self._countdown)
        self.appear.to(1.0, 420)
        self._clock.start()

    # -- geometry
    def _button(self) -> QRectF:
        bw, bh = S(176), S(44)
        return QRectF(self.width() / 2 - bw / 2, self.card_top() + S(self.CH) * 0.74, bw, bh)

    def _circle_d(self) -> float:
        f = self.fly.level if self.phase in ("fly", "done") else 0.0
        return lerp(float(S(self.BIG)), float(BD()), f)

    # -- the sequence
    def launch(self, force: bool = False) -> None:
        if self.phase != "card" or not (force or self.logged_in()):
            return
        self.panel.hide()
        self.phase = "fold"
        sfx.play("on")
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.hover.to(0.0, 120)
        self.fold.to(1.0, 520)

    def _folded(self) -> None:
        if self.phase == "fold":
            self.phase = "ring"
            self.ring.to(1.0, 640)

    def _loaded(self) -> None:
        if self.phase != "ring":
            return
        self.phase = "fly"
        self._from = self.geometry().center()
        self._to = QPoint(self.ctx.window.ball.center)
        dist = (self._to - self._from).manhattanLength()
        self.fly.to(1.0, int(max(480, min(760, 380 + dist * 0.22))))

    def _on_fly(self) -> None:
        if self.phase == "fly":
            f = self.fly.level
            c = QPoint(round(lerp(self._from.x(), self._to.x(), f)), round(lerp(self._from.y(), self._to.y(), f)))
            self.move(c.x() - self.width() // 2, c.y() - self.height() // 2)
        self.update()

    def _landed(self) -> None:
        if self.phase != "fly":
            return
        self.phase = "done"
        self._clock.stop()
        ball = self.ctx.window.ball
        ball.appear.jump(1.0)
        ball.place()
        ball.show()
        ball.repaint()                             # the real ball is drawn before this window goes away
        self.hide()
        done, self._on_done = self._on_done, None
        if done is not None:
            done()
        self.deleteLater()

    # -- mouse: only the Launch button does anything
    def mouseMoveEvent(self, e) -> None:
        over = self.phase == "card" and self.logged_in() and self._card_rect().contains(e.position())
        self.setCursor(Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.ArrowCursor)
        self.hover.to(1.0 if over else 0.0, 140)

    def leaveEvent(self, _e) -> None:
        self.hover.to(0.0, 200)

    def _card_rect(self) -> QRectF:
        h = self.card_h()
        return QRectF(self.width() / 2 - S(self.CW) / 2, self.height() / 2 - h / 2, S(self.CW), h)

    def _logout_rect(self) -> QRectF:
        r = self._link_rect()
        return QRectF(r.center().x() + self._logout_x, r.top(), self._logout_w, r.height())

    def mousePressEvent(self, e) -> None:
        if self.phase == "card" and self.logged_in() and e.button() == Qt.MouseButton.LeftButton \
                and self._logout_rect().contains(e.position()):
            sfx.play("pick")
            self.ctx.online.log_out()
            self._take_keyboard()
            self.panel.sync()
            return
        if (self.phase == "card" and self.logged_in() and e.button() == Qt.MouseButton.LeftButton
                and self._card_rect().contains(e.position())):           # a click on the card starts right away
            self._down = True
            self.press.to(1.0, 80)

    def mouseReleaseEvent(self, e) -> None:
        if self._down:
            self._down = False
            self.press.to(0.0, 160)
            if self._card_rect().contains(e.position()):
                self.launch()

    def closeEvent(self, e) -> None:
        if self.phase != "done":
            e.ignore()                             # there is no way to close it: Launch is the way in

    # -- painting
    def paintEvent(self, _e) -> None:
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        a = max(0.0, min(1.0, self.appear.level))
        m = max(0.0, min(1.0, self.fold.level))
        f = max(0.0, min(1.0, self.fly.level)) if self.phase in ("fly", "done") else 0.0
        d = self._circle_d()
        if self.phase == "fly":
            d *= 1.0 + 0.14 * math.sin(math.pi * min(1.0, f / 0.4))        # a soft pop as it takes off
        k = 0.94 + 0.06 * a
        w, h = lerp(S(self.CW) * k, d, m), lerp(self.card_h() * k, d, m)
        top = self.card_top()
        cx, cy = self.width() // 2, self.height() // 2
        shape = QRectF(cx - w / 2, cy - h / 2, w, h)
        radius = lerp(float(S(24)), d / 2, m)
        p.setOpacity(a)
        level = lerp(max(0.72, self.ctx.glow_level()), self.ctx.glow_level(), f)
        path = paint_shape(p, self.ctx, shape, radius, level, self.devicePixelRatioF())

        show = max(0.0, 1.0 - m / 0.45)                    # the card's content leaves first
        if show > 0.0:
            p.save()
            p.setClipPath(path)
            p.setOpacity(a * show)
            other = QColor.fromHsvF((max(0.0, ui.accent.hsvHueF()) + 0.17) % 1.0,
                                    min(1.0, ui.accent.hsvSaturationF() * 0.9 + 0.1), 1.0)
            spots = ((ui.accent, 0.34, 0.28 + 0.20 * math.sin(now * 0.55), 0.20 + 0.22 * math.cos(now * 0.43), 0.62),
                     (other, 0.24, 0.76 + 0.16 * math.cos(now * 0.37), 0.84 + 0.14 * math.sin(now * 0.61), 0.55),
                     (ui.accent, 0.16, 0.55 + 0.30 * math.sin(now * 0.29 + 2.0), 0.55 + 0.25 * math.cos(now * 0.33), 0.40))
            for col, strength, fx, fy, size in spots:    # slow drifting lights
                c = QPointF(shape.left() + w * fx, shape.top() + h * fy)
                g = QRadialGradient(c, w * size)
                g.setColorAt(0.0, alpha(col, strength))
                g.setColorAt(1.0, alpha(col, 0.0))
                p.fillRect(shape, g)
            sweep = (now * 0.16) % 1.6 - 0.3               # a faint band of light crossing now and then
            band = QLinearGradient(QPointF(shape.left() + w * (sweep - 0.18), shape.top()),
                                   QPointF(shape.left() + w * (sweep + 0.18), shape.bottom()))
            band.setColorAt(0.0, alpha("#FFFFFF", 0.0))
            band.setColorAt(0.5, alpha("#FFFFFF", 0.05))
            band.setColorAt(1.0, alpha("#FFFFFF", 0.0))
            p.fillRect(shape, band)

            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(14, QFont.Weight.DemiBold, 0.3))
            p.drawText(QRectF(shape.left(), top + S(self.CH) * 0.14, w, S(22)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("Welcome to"))
            p.setFont(font(42, QFont.Weight.ExtraBold, 0.5))
            fm = p.fontMetrics()
            word = "Rubenium"
            full = fm.horizontalAdvance(word)
            x0 = cx - full / 2
            split = x0 + full - fm.horizontalAdvance("ium")
            line = QRectF(x0, top + S(self.CH) * 0.25, full + S(4), S(56))
            p.save()
            p.setClipRect(QRectF(0, 0, split, self.height()), Qt.ClipOperation.IntersectClip)
            p.setPen(QColor(TEXT))
            p.drawText(line, int(Qt.AlignmentFlag.AlignVCenter), word)
            p.restore()
            p.save()
            p.setClipRect(QRectF(split, 0, self.width(), self.height()), Qt.ClipOperation.IntersectClip)
            p.setPen(ui.accent)
            p.drawText(line, int(Qt.AlignmentFlag.AlignVCenter), word)
            p.restore()

            shown_in = max(0.0, 1.0 - self.out_level() * 2)   # the name fades in once the form is gone
            p.setOpacity(a * show * shown_in)
            if self.logged_in():                               # "Name · Log out" under the button
                r = self._link_rect()
                p.setFont(font(11, QFont.Weight.DemiBold))
                fm = p.fontMetrics()
                name, sep, out = self.ctx.online.username(), "  ·  ", tr("Log out")
                total = fm.horizontalAdvance(name + sep + out)
                x0 = r.center().x() - total / 2
                x1 = x0 + fm.horizontalAdvance(name + sep)
                p.setPen(QColor(TEXT))
                p.drawText(QRectF(x0, r.top(), total, r.height()), int(Qt.AlignmentFlag.AlignVCenter), name)
                p.setPen(QColor(TEXT_DIM))
                p.drawText(QRectF(x0 + fm.horizontalAdvance(name), r.top(), total, r.height()),
                           int(Qt.AlignmentFlag.AlignVCenter), sep)
                f2 = font(11, QFont.Weight.DemiBold)
                f2.setUnderline(True)
                p.setFont(f2)
                p.drawText(QRectF(x1, r.top(), total, r.height()), int(Qt.AlignmentFlag.AlignVCenter), out)
                self._logout_x, self._logout_w = x1 - r.center().x(), fm.horizontalAdvance(out)
            p.restore()

        face = max(0.0, min(1.0, (m - 0.5) / 0.5))         # the R arrives as the circle forms
        if face > 0.0:
            p.setOpacity(a * face)
            c = QPointF(cx, cy)
            box = QRectF(c.x() - d / 2, c.y() - d / 2 - d * 0.02, d, d)
            extras.paint_r(p, box, d, self.ctx.ball_style(), ui.accent, now)
            turn = max(0.0, min(1.0, self.ring.level))
            if self.phase in ("ring", "fly") and turn > 0.0:
                inset = d * 0.09
                ring = QRectF(c.x() - d / 2 + inset, c.y() - d / 2 + inset, d - 2 * inset, d - 2 * inset)
                pen = QPen(alpha("#FFFFFF", 0.10 * (1.0 - f)), max(1.5, d * 0.04))
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(pen)
                p.drawEllipse(ring)
                pen.setColor(alpha(ui.accent, 1.0 - f))
                p.setPen(pen)
                p.drawArc(ring, 90 * 16, int(-360 * 16 * turn))
        p.setOpacity(a)
        paint_edge(p, self.ctx, shape, radius, level)
        if self.phase == "card" and self.count.level > 0.0 and self.logged_in():      # the 3 second line
            rr = shape.adjusted(S(1.5), S(1.5), -S(1.5), -S(1.5))
            rad = max(1.0, radius - S(1.5))
            line = QPainterPath()
            line.moveTo(rr.center().x(), rr.top())                    # from the top middle, clockwise
            line.lineTo(rr.right() - rad, rr.top())
            line.arcTo(QRectF(rr.right() - 2 * rad, rr.top(), 2 * rad, 2 * rad), 90, -90)
            line.lineTo(rr.right(), rr.bottom() - rad)
            line.arcTo(QRectF(rr.right() - 2 * rad, rr.bottom() - 2 * rad, 2 * rad, 2 * rad), 0, -90)
            line.lineTo(rr.left() + rad, rr.bottom())
            line.arcTo(QRectF(rr.left(), rr.bottom() - 2 * rad, 2 * rad, 2 * rad), 270, -90)
            line.lineTo(rr.left(), rr.top() + rad)
            line.arcTo(QRectF(rr.left(), rr.top(), 2 * rad, 2 * rad), 180, -90)
            line.lineTo(rr.center().x(), rr.top())
            width = S(3)
            pen = QPen(ui.accent, width)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            pen.setDashPattern([max(0.001, line.length() * self.count.level / width), 100000.0])
            p.setOpacity(a * max(0.0, 1.0 - self.out_level() * 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(pen)
            p.drawPath(line)
            p.setOpacity(a)


class LockCover(QWidget):
    """A blur of the page with a big padlock: the admin has locked the online part of the app."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.blur = None
        self.mode = "locked"                      # locked (by the admin) / update / offline
        self.setCursor(Qt.CursorShape.ForbiddenCursor)
        self.button = Button(tr("Update now"), "primary", 34, parent=self)
        self.button.setFixedWidth(S(160))
        self.button.hide()
        self.on_button = None
        self.button.clicked.connect(lambda: self.on_button() if self.on_button else None)

    def set_mode(self, mode: str, on_button=None) -> None:
        self.mode, self.on_button = mode, on_button
        self.button.setVisible(on_button is not None)
        self.button.set_text(tr("Update now") if mode == "update" else tr("Go online") if mode == "offmode" else tr("Try again"))
        self.update()

    def resizeEvent(self, _e) -> None:
        r = self.rect()
        top = min(r.center().y(), r.top() + S(150)) + S(110)
        self.button.move(r.center().x() - self.button.width() // 2, int(top))

    def take(self, widget) -> None:
        pm = widget.grab()
        if pm.isNull():
            self.blur = None
            return
        small = pm.scaled(max(1, pm.width() // 14), max(1, pm.height() // 14), Qt.AspectRatioMode.IgnoreAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
        self.blur = small.scaled(pm.size(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)

    def mousePressEvent(self, e) -> None:
        e.accept()

    def wheelEvent(self, e) -> None:
        e.accept()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect())
        if self.blur is not None:
            p.drawPixmap(self.rect(), self.blur)
        p.fillRect(r, QColor(6, 8, 10, 170))
        c = QPointF(r.center().x(), min(r.center().y(), r.top() + S(150)) - S(10))
        glow = QRadialGradient(c, S(90))
        glow.setColorAt(0, alpha(ui.accent, 0.30))
        glow.setColorAt(1, alpha(ui.accent, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, S(90), S(90))
        p.save()
        p.translate(c)
        p.scale(S(64) / 20, S(64) / 20)
        draw_icon(p, {"update": "refresh", "offline": "power", "offmode": "power"}.get(self.mode, "lock"), QColor("#FFFFFF"))
        p.restore()
        title, text = {
            "update": (tr("Update needed"), tr("A new version is available. Update to use online features.")),
            "offline": (tr("You are offline"), tr("No internet connection. Music, saved lyrics and tools still work. "
                                                 "Rubenium reconnects automatically.")),
            "offmode": (tr("Offline mode"), tr("Online features are paused. Music, saved lyrics and tools still work.")),
            "lockdown": (tr("Paused for a moment"), tr("The Rubenium team paused online features for a moment. Nothing you "
                                                       "own is lost: open trades and games were given back.")),
        }.get(self.mode, (tr("Temporarily locked"), tr("Online features are under maintenance. Your time still counts.")))
        p.setPen(QColor(TEXT))
        p.setFont(font(15, QFont.Weight.Bold))
        p.drawText(QRectF(r.left(), c.y() + S(42), r.width(), S(24)), int(Qt.AlignmentFlag.AlignCenter), title)
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(11, QFont.Weight.DemiBold))
        p.drawText(QRectF(r.left() + S(20), c.y() + S(68), r.width() - S(40), S(56)),
                   int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap), text)


class SheetPage(QWidget):
    """A small screen shown inside the menu instead of a separate window (a text box, the daily reward, a chat…).
    Everything stays in the main menu: nothing pops up over a game."""
    key = "sheet"
    fixed_height = 0

    def __init__(self, ctx, widget) -> None:
        super().__init__()
        self.ctx, self.widget = ctx, widget
        from .core import page_width
        self.W = page_width()
        lay = vbox(self, 6)
        widget.setParent(self)
        if widget.width() > self.W:
            widget.setFixedWidth(self.W)
        lay.addWidget(widget, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(1)
        widget.show()

    def content_height(self) -> int:
        lay = self.layout()
        lay.activate()
        return lay.sizeHint().height()

    def on_show(self) -> None:
        f = getattr(self.widget, "focus_me", None)
        if f is not None:
            QTimer.singleShot(60, f)

    def on_hide(self) -> None: ...

    def on_state(self, st) -> None: ...

    def release(self) -> None:
        """The page goes away, the small screen may come back: keep it."""
        try:
            self.widget.hide()
            self.widget.setParent(None)
        except RuntimeError:
            pass


class Body(QWidget):
    """Card chrome: wordmark, status dots, the R button (back to the ball), tab bar and the page host."""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.win = window
        self.to_ball = IconButton("rball", 28, tip=tr("Close to the ball"), parent=self)
        self.tabbar = None
        self.host = QWidget(self)
        self.cover = LockCover(self.host)
        self.cover.hide()
        self.set_tabs()
        self.to_ball.clicked.connect(window.collapse)
        self._press = None
        self._moved = False

    def set_tabs(self) -> None:
        """(Re)build the tab row from the tabs the user keeps switched on."""
        old = self.tabbar
        tabs = [(k, icon, tr(label), False) for k, icon, label in visible_tabs(self.win.ctx.cfg)]
        self.tabbar = TabBar(tabs, self.win.current, self)
        self.tabbar.changed.connect(self.win.goto)
        if old is not None:
            old.hide()
            old.deleteLater()
            self.tabbar.show()
            self.resizeEvent(None)

    def offset(self) -> int:
        return int(round((1.0 - self.win.chrome.level) * S(COMPACT)))

    def resizeEvent(self, _e) -> None:
        pad, w, off = S(PAD), self.width(), self.offset()
        level = self.win.chrome.level
        self.to_ball.move(w - pad - self.to_ball.width() + S(2),
                          S(HEADER_TOP) + (S(HEADER_H) - self.to_ball.height()) // 2)
        self.tabbar.setGeometry(pad, S(HEADER_TOP + HEADER_H + 8), w - 2 * pad, max(1, int(round(S(TAB_H) * level))))
        self.host.setGeometry(pad, S(CHROME_TOP) - off, w - 2 * pad + S(ScrollArea.GUTTER),
                              max(0, self.height() - S(CHROME_TOP + CHROME_BOTTOM) + off))
        if self.cover.isVisible():
            self.cover.setGeometry(self.host.rect())
        self.tabbar.fade = max(0.0, min(1.0, (level - 0.2) / 0.8))     # squashes and fades together
        self.tabbar.setVisible(level > 0.04)                             # a hidden bar never catches a click
        self.tabbar.update()
        page = self.win.page()
        if page is not None and hasattr(page, "set_compact"):
            page.set_compact(level)
        for child in self.host.children():
            if isinstance(child, ScrollArea):
                child.setGeometry(self.host.rect())

    def header_rect(self) -> QRectF:
        return QRectF(0, 0, self.width(), S(HEADER_TOP + HEADER_H + 4))

    def dots_rect(self) -> QRect:
        return QRect(S(PAD), S(HEADER_TOP), S(220), S(HEADER_H))

    def paintEvent(self, _e) -> None:
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(font(18, QFont.Weight.ExtraBold, 0.4))
        fm = p.fontMetrics()
        x, base = S(PAD), QRectF(S(PAD), S(HEADER_TOP), self.width(), S(HEADER_H))
        # Drawn as ONE word so the letters keep their natural spacing; the colour changes by clipping.
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
        x += full + S(9)
        st = self.win.ctx.state
        playing = st.status is Status.PLAYING
        live = st.status in (Status.PLAYING, Status.PAUSED)
        now = time.monotonic()
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            lift = math.sin(now * 5.0 - i * 0.9) * S(2.6) if playing else 0.0
            p.setBrush(alpha(ui.accent, 1.0 if playing else (0.6 if live else 0.25)))
            p.drawEllipse(QPointF(x + i * S(6), base.center().y() + S(4) - lift), S(1.7), S(1.7))
        name = self.win.ctx.online.username()
        if name:                                             # who is logged in: a small pill, right of the title
            p.setFont(font(10.5, QFont.Weight.DemiBold))
            tw = p.fontMetrics().horizontalAdvance(name)
            h = S(20)
            pill = QRectF(self.width() - S(PAD) - S(34) - tw - S(22), base.center().y() - h / 2, tw + S(22), h)
            if pill.left() > x + S(26):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha("#FFFFFF", 0.06))
                p.drawRoundedRect(pill, h / 2, h / 2)
                dot = QPointF(pill.left() + S(9), pill.center().y())           # just a small online dot
                p.setBrush(QColor("#3DDC84") if not self.win.ctx.online.offline else alpha("#FFFFFF", 0.3))
                p.drawEllipse(dot, S(3), S(3))
                p.setPen(QColor(TEXT_DIM))
                p.setFont(font(10.5, QFont.Weight.DemiBold))
                p.drawText(pill.adjusted(S(16), 0, -S(6), 0), int(Qt.AlignmentFlag.AlignVCenter), name)

    # drag the card from anywhere that is not a control
    # Hold the card for a moment, then move it. A quick click or flick never moves it; if you press and move
    # straight away, the card simply starts following after that moment.
    HOLD_MS = 200

    def mousePressEvent(self, e) -> None:
        if win.mouse_captured():               # a game has the mouse: not meant for Rubenium
            return
        self.win.show_chrome()
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.globalPosition().toPoint()
            self._armed = False
            QTimer.singleShot(self.HOLD_MS, lambda at=self._press: self._arm(at))

    def _arm(self, at: QPoint) -> None:
        if self._press is None or self._press is not at:
            return
        if not (QGuiApplication.mouseButtons() & Qt.MouseButton.LeftButton):
            self._press = None                  # the button was let go somewhere else
            return
        self._armed = True
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        # The point you pressed is the point you hold: if the mouse already moved, the card catches up with it.
        self.win.begin_drag(self._press)

    def mouseReleaseEvent(self, e) -> None:
        self.release_drag()

    def release_drag(self) -> None:
        self._press = None
        if getattr(self, "_armed", False):
            self._armed = False
            self.unsetCursor()
            self.win.end_drag()


# --------------------------------------------------------------------------- #
# The card
# --------------------------------------------------------------------------- #
class MainWindow(QWidget):
    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        cfg = ctx.cfg
        self.current = cfg["page"] if cfg["page"] in self.tab_keys() else "home"
        self.expanded = False
        self.modal = False
        self.game_state = 0
        self.pages: dict = {}
        self._snap = None
        self._snap_old = self._snap_new = None
        self._dir = 1
        self._ball_l = QRectF()
        self._max_l = QRectF()               # largest card rect inside the canvas
        self._anchor_bottom = False
        self.card_pos = None                 # where the card lives on screen (global top-left)
        self._pre_casino = None              # where the card was before the casino lifted it to fit
        self._docked = None                  # where the ball was parked after the last collapse
        self._reset_to = None
        self._closed_at_card = False         # True: the ball sits in the card's top corner (card was moved)
        self._through = False                # clicks pass through Rubenium (a game has the mouse)
        self._guard = QTimer(self)
        self._guard.setInterval(25)
        self._guard.timeout.connect(self._mouse_guard)
        self._heal_t = QTimer(self)                         # 4.5: never left blank or half off the screen
        self._heal_t.setInterval(1500)
        self._heal_t.timeout.connect(self.heal)
        self._heal_t.start()
        if win.IS_WIN:
            self._guard.start()
        self._open_from = None               # where the ball was when the card opened
        self._open_card = None
        self._pending_home = None
        self._sparks: list = []
        self._fsnap = None
        self.card_max_h = S(400)
        self._drag_origin = None
        self._drag_at = QPointF()
        self._follow_test = False            # tests move a fake mouse: no real button is held
        self._follow = QTimer(self)
        self._follow.setTimerType(Qt.TimerType.PreciseTimer)
        self._follow.setInterval(8)
        self._follow.timeout.connect(self._follow_step)

        self.setWindowTitle("Rubenium")
        self.setWindowFlags(WINDOW_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowOpacity(cfg["opacity"] / 100)

        self.morph = Tween(self, 0.0, self._on_morph)
        self.pageh = Tween(self, float(S(240)), self._on_pageh)
        self.slide = Tween(self, 1.0, self._on_slide)
        self._accent_from, self._accent_to = QColor(ui.accent), QColor(ui.accent)
        self.accent_t = Tween(self, 1.0, self._on_accent)
        self.fade = Tween(self, 1.0, self._on_fade)
        self.zoom = Tween(self, 1.0, self.update, QEasingCurve.Type.OutCubic)
        self._zoom_from = 1.0
        self._scale_shown = ui.scale
        self.chrome = Tween(self, 1.0, self._on_chrome, QEasingCurve.Type.InOutCubic)
        self._idle = QTimer(self)
        self._idle.setInterval(150)
        self._idle.timeout.connect(self._watch_idle)
        self._in_since = self._out_since = 0.0

        self.ball = BallWindow(self)
        self.ball.setWindowOpacity(cfg["opacity"] / 100)
        self.body = Body(self)
        self.body.hide()
        self.toast_w = Toast(self)
        self.confirm_w = Confirm(self)
        self.busy_w = Busy(self)
        self.drawer = PreviewDrawer(self)
        self._spark_timer = QTimer(self)
        self._spark_timer.setInterval(90)
        self._spark_timer.timeout.connect(self._twinkle)

        self._pulse = QTimer(self)
        self._pulse.setTimerType(Qt.TimerType.PreciseTimer)
        self._pulse.timeout.connect(self._tick)

    def tab_keys(self) -> list:
        return [t[0] for t in visible_tabs(self.ctx.cfg)]

    def tabs_changed(self) -> None:
        """A tab was switched on or off in Settings."""
        self.body.set_tabs()
        for key in list(self.pages):
            if key not in self.tab_keys() and key != self.current:
                self._drop_page(key)

    # ------------------------------------------------------------------ geometry
    def _place(self, ball: QRect, card_tl=None) -> None:
        """Lay the canvas out. With `card_tl` the card sits exactly there (kept on screen); without it the
        card opens at the ball. The card is always anchored by its top-left corner, so it never shuffles."""
        g, cw, m, d = S(GLOW), S(CARD_W), S(8), BD()
        if card_tl is None:
            wa = work_area(ball.center())
            x = ball.left() if ball.center().x() < wa.center().x() else ball.right() + 1 - cw
            y = ball.top()
        else:
            wa = work_area(card_tl + QPoint(cw // 2, S(40)))
            x, y = card_tl.x(), card_tl.y()
        x = max(wa.left() + m, min(x, wa.right() - cw - m))
        y = max(wa.top() + m, min(y, wa.bottom() - m - S(MIN_CARD)))
        room = wa.bottom() - m - y                              # low on the screen: tall pages scroll instead
        self.card_max_h = max(S(MIN_CARD), min(S(CHROME_TOP + CHROME_BOTTOM + MAX_CONTENT), int(wa.height() * 0.9), room))
        card_max = QRect(x, y, cw, self.card_max_h)
        if card_tl is not None:                                 # the ball starts inside the card's top strip
            bx = max(x, min(ball.left(), x + cw - d))
            ball = QRect(bx, y, d, d)
        canvas = card_max.united(ball).adjusted(-g, -g, g, g)
        self._anchor_bottom = False
        self._ball_l = QRectF(ball.translated(-canvas.topLeft()))
        self._max_l = QRectF(card_max.translated(-canvas.topLeft()))
        self.setGeometry(canvas)
        self.card_pos = QPoint(card_tl) if card_tl is not None else QPoint(x, y)   # where the user wants it
        self._save_card()
        self._sparks = extras.theme_sparkles(self.ctx.theme(), self._max_l.width(), self._max_l.height(), S(BAND))

    def _save_card(self) -> None:
        c = self.card_pos
        screen = QGuiApplication.screenAt(c + QPoint(S(CARD_W) // 2, S(40))) or QGuiApplication.primaryScreen()
        wa = screen.availableGeometry()
        new = {"screen": screen.name(), "nx": (c.x() - wa.left()) / max(1, wa.width()),
               "ny": (c.y() - wa.top()) / max(1, wa.height())}
        if new != self.ctx.cfg["card"]:
            self.ctx.cfg["card"] = new

    def card_global(self) -> QRect:
        c = self._card_rect()
        return QRect(self.mapToGlobal(c.topLeft().toPoint()), c.size().toSize())

    def _card_rect(self) -> QRectF:
        h, m = self.pageh.level - (1.0 - self.chrome.level) * S(COMPACT), self._max_l
        y = m.top() + m.height() - h if self._anchor_bottom else m.top()
        return QRectF(m.left(), y, m.width(), h)

    def _shape(self):
        t = self.morph.level
        b, c = self._ball_l, self._card_rect()
        r = QRectF(lerp(b.left(), c.left(), t), lerp(b.top(), c.top(), t),
                   lerp(b.width(), c.width(), t), lerp(b.height(), c.height(), t))
        return r, lerp(b.width() / 2, S(ui.radius), max(0.0, min(1.0, t)))

    def _card_h(self, key: str) -> float:
        return float(min(S(CHROME_TOP + CHROME_BOTTOM) + self.pages[key][2], self.card_max_h))

    # ------------------------------------------------------------------ pages
    # ------------------------------------------------------------------ small screens inside the menu
    def page_w(self) -> int:
        """4.1: how wide a small screen made for this menu should be (the online menu's halves are wider)."""
        return S(CARD_W - 2 * PAD)

    def embed(self, widget, keys: bool = False) -> None:
        """Show `widget` inside the menu, over the current tab, until it is closed. keys: it has a text box."""
        old = getattr(self, "sheet", None)
        if old is not None and old is not widget:
            self._close_sheet(old)
        self.sheet, self.sheet_tab, self.sheet_keys = widget, self.current, keys
        if keys:
            self.allow_keys(True)
        self.reload_page()

    def unembed(self, widget) -> None:
        if getattr(self, "sheet", None) is widget:
            self.sheet = None
            if self.sheet_keys:
                self.allow_keys(False)
            self.reload_page()

    def _close_sheet(self, widget=None) -> None:
        w = widget or getattr(self, "sheet", None)
        if w is None:
            return
        self.sheet = None
        if getattr(self, "sheet_keys", False):
            self.allow_keys(False)
        try:
            end = getattr(w, "on_closed", None)
            if end:
                end()
            w.deleteLater()
        except RuntimeError:
            pass

    def allow_keys(self, on: bool) -> None:
        """Typing needs the keyboard. Only while a text box is open may the menu take it; then it gives it back."""
        if bool(getattr(self, "_keys_on", False)) == on:
            return
        self._keys_on = on
        vis = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, not on)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, not on)
        if vis:
            self.show()
            win.set_topmost(int(self.winId()))
            if on:
                self.raise_()
                self.activateWindow()

    def _ensure_page(self, key: str):
        if key not in self.pages and getattr(self, "sheet", None) is not None and key == self.sheet_tab:
            page = SheetPage(self.ctx, self.sheet)
            h = page.content_height()
            sa = ScrollArea(page, h, self.body.host)
            sa.hide()
            self.pages[key] = (sa, page, h)
        if key not in self.pages:
            page = make_page(self.ctx, key)
            align_slider_rows(page)
            h = page.content_height()
            sa = ScrollArea(page, h, self.body.host)
            sa.hide()
            self.pages[key] = (sa, page, h)
        return self.pages[key]

    def _drop_page(self, key: str) -> None:
        if key in self.pages:
            sa, page, _h = self.pages.pop(key)
            if isinstance(page, SheetPage):
                page.release()
            page.on_hide()
            sa.hide()
            sa.deleteLater()

    def page(self):
        entry = self.pages.get(self.current)
        return entry[1] if entry else None

    def each_page(self):
        return [entry[1] for entry in self.pages.values()]

    def _layout_body(self) -> None:
        c = self._card_rect()
        self.body.setGeometry(int(round(c.left())), int(round(c.top())), int(c.width()), int(round(c.height())))

    def _finish_slide(self) -> None:
        if self.slide.busy or self._snap_new is not None:
            self.slide.jump(1.0)

    def goto(self, key: str) -> None:
        if key == "online" or key in ("games", "themes", "friends", "giveaway", "admin"):   # 4.4: admin opens full size online
            return self.ctx.enter_online(None if key == "online" else key)      # 3.2: they live in the online menu
        if key not in self.tab_keys():
            return
        if getattr(self, "sheet", None) is not None and key != self.sheet_tab:     # another tab: the small screen closes
            tab = self.sheet_tab
            self._close_sheet()
            self._drop_page(tab)
        if not self.expanded:
            self.current = key
            self.ctx.cfg["page"] = key
            self.body.tabbar.set_current(key)
            return self.expand()
        if key == self.current or self.morph.busy:
            return
        self._finish_slide()
        self.fade.jump(1.0)
        self.chrome.jump(1.0)
        self.toast_w.hide()
        self.confirm_w.hide()
        self.drawer.close_now()
        keys = self.tab_keys()
        self._dir = 1 if keys.index(key) > keys.index(self.current) else -1
        old_sa, old_page, _ = self._ensure_page(self.current)
        self._snap_old = snapshot(old_sa)
        old_page.on_hide()
        old_sa.hide()
        self.current = key
        self.ctx.cfg["page"] = key
        self.body.tabbar.set_current(key)
        sa, _page, _h = self._ensure_page(key)
        new_h = self._card_h(key)
        sa.setGeometry(0, 0, S(CARD_W - 2 * PAD) + S(ScrollArea.GUTTER), int(new_h) - S(CHROME_TOP + CHROME_BOTTOM))
        self._snap_new = snapshot(sa)
        self.slide.jump(0.0)
        self.slide.to(1.0, 280)
        self.pageh.to(new_h, 320)
        if self._dir and "perf" in self.pages and key != "perf":   # Stats is unloaded once it is left
            QTimer.singleShot(400, self._unload_stats)
        self.body.cover.hide()
        QTimer.singleShot(320, self.sync_lock)
        gone = [k for k in TEMP_TABS if k != key]          # a tab shown only while it was being read
        if gone:
            TEMP_TABS.difference_update(gone)
            self.body.set_tabs()

    def heal(self) -> None:
        """4.5: the small menu, open, always shows its page and sits on the screen; closed, it is not left drawn."""
        if getattr(self, "modal", False) or self.morph.busy or self.slide.busy or self.pageh.busy:
            return
        try:
            if self.ctx.window is not self:                 # online: this menu waits, folded into the ball
                if self.isVisible() and not self.expanded:
                    self.hide()
                return
            if self.expanded and self.isVisible():
                if not self.body.isVisible() and getattr(self, "sheet", None) is None:
                    self.morph.jump(1.0)
                    self._on_morph()
                card = self._card_rect()
                tl = self.mapToGlobal(card.topLeft().toPoint())
                g = QRect(tl, card.size().toSize())
                wa = work_area(g.center())
                if not wa.intersects(g) or g.left() < wa.left() - S(4) or g.right() > wa.right() + S(4) \
                        or g.top() < wa.top() - S(4):
                    self._place(self.ball.rect_global(), None)
                    self._layout_body()
                    self.update()
            elif not self.expanded and self.isVisible() and self.morph.level <= 0.001:
                self._on_morph()
        except RuntimeError:
            pass

    def _mouse_guard(self) -> None:
        """While a game hides or locks the mouse pointer, every Rubenium window lets clicks through to the
        game: aiming or clicking in a game can never open, drag or press anything in Rubenium."""
        captured = win.mouse_captured()
        # Game mode: while a fullscreen game is in front and the menu is closed, the ball is not there for the
        # mouse at all. Moving, aiming or clicking near it goes to the game. Right Shift still opens the menu.
        if not captured and self.ctx.cfg["game_mouse"] and not self.expanded:
            captured = win.fullscreen_in_front()
        if captured and self.ball._press_pos is not None and self._press_held():
            captured = False                    # the button is still held on the ball: a game seeing the same
            #                                     click (Rocket League menus do) must not cancel the opening
        if captured:
            self.ball.cancel_press()            # a press that began just before the game took the mouse
        through = captured and self.ball._press_pos is None and self._drag_origin is None
        if through != self._through or through:
            for w in (self.ball, self, self.drawer):
                hwnd = int(w.internalWinId() or 0)
                if hwnd:
                    win.set_click_through(hwnd, through)
        self._through = through

    def _press_held(self) -> bool:
        """The left button is still down and the pointer is still on the ball."""
        down = win.key_down(0x01) if win.IS_WIN else bool(QGuiApplication.mouseButtons() & Qt.MouseButton.LeftButton)
        if not down:
            return False
        m = S(14)
        return self.ball.rect_global().adjusted(-m, -m, m, m).contains(QCursor.pos())

    def _unload_stats(self) -> None:
        """The Stats tab measures the PC while it is open; once you leave it, it is removed completely."""
        if self.current != "perf" and "perf" in self.pages and not self.slide.busy:
            self._drop_page("perf")

    def _on_slide(self) -> None:
        if self.slide.level >= 0.999 and self._snap_new is not None:
            self._snap_old = self._snap_new = None
            if self.expanded and not self.morph.busy:
                sa, page, _ = self._ensure_page(self.current)
                self.body.resizeEvent(None)
                sa.show()
                page.on_show()
        self.update()

    def _on_pageh(self) -> None:
        if self.expanded and not self.morph.busy:
            self._layout_body()
        self.update()

    def sync_lock(self) -> None:
        """While the admin has locked the app, the online tabs are covered by a blur and a big padlock."""
        from .pages2 import LOCK_PAGES
        cover = self.body.cover
        ctx = self.ctx
        mode = ("offmode" if ctx.cfg["offline_mode"] and ctx.online.logged_in() else
                "locked" if ctx.econ.live.get("locked") else
                "lockdown" if ctx.econ.lockdown_cover() else
                "update" if getattr(ctx, "outdated", False) else
                "offline" if ctx.online.logged_in() and ctx.online.offline else "")
        on = bool(mode) and self.expanded and self.current in LOCK_PAGES
        if on and mode != cover.mode:
            cover.set_mode(mode, ctx.install_update if mode == "update" and ctx.updater.latest else
                           (ctx.online.probe if mode == "offline" else
                            (lambda: ctx.set_offline_mode(False)) if mode == "offmode" else None))
        if on:
            cover.setGeometry(self.body.host.rect())
            cover.resizeEvent(None)
            entry = self.pages.get(self.current)
            if entry is not None and not cover.isVisible():
                cover.take(entry[0])
            cover.show()
            cover.raise_()
        elif cover.isVisible():
            cover.hide()

    def showing(self, key: str) -> bool:
        """3.2: this page is on screen right now (the online menu shows several at once)."""
        return self.expanded and self.current == key

    def reload_page(self, key: str = None) -> None:
        """Rebuild the current page (its content changed) and glide to its new height. 3.2: a page that is not the
        current one is just dropped, so it is built fresh when it is opened."""
        if key is not None and key != self.current:
            self._drop_page(key)
            return
        if not self.expanded:
            self._drop_page(self.current)
            return
        self._finish_slide()
        old = self.pages.get(self.current)
        offset = old[0].offset() if old else 0.0
        self._drop_page(self.current)
        sa, page, _h = self._ensure_page(self.current)
        self.body.resizeEvent(None)
        sa.show()
        sa._target = min(offset, max(0.0, sa.max_offset()))
        sa._pos.jump(sa._target)
        page.on_show()
        self.pageh.to(self._card_h(self.current), 300)
        QTimer.singleShot(0, self.sync_lock)

    def rebuild(self) -> None:
        """Scale or language changed: rebuild every widget at an animation boundary."""
        self.morph.jump(1.0 if self.expanded else 0.0)
        self._finish_slide()
        for key in list(self.pages):
            self._drop_page(key)
        self.drawer.close_now()
        self.fade.jump(1.0)
        self.chrome.jump(1.0)
        self._fsnap = None
        self.toast_w.deleteLater()
        self.confirm_w.deleteLater()
        self.body.deleteLater()
        _tiles.clear()
        self.body = Body(self)
        self.toast_w = Toast(self)
        self.confirm_w = Confirm(self)
        self.busy_w.raise_()
        self.ball.clamp()
        self.ball.place()
        if self.expanded:
            home = self.card_pos or self.card_global().topLeft()       # same top-left corner as before
            if getattr(self.ctx, "casino", False):                     # the bigger casino must fit on screen
                if self._pre_casino is None:
                    self._pre_casino = QPoint(home)
                wa = work_area(home + QPoint(S(CARD_W) // 2, S(40)))
                need = S(CHROME_TOP + CHROME_BOTTOM + 480)
                home = QPoint(home.x(), max(wa.top() + S(8), min(home.y(), wa.bottom() - S(8) - need)))
            elif self._pre_casino is not None:                        # back where it was before the casino
                home, self._pre_casino = self._pre_casino, None
            d = BD()
            self._place(QRect(home.x(), home.y(), d, d), home)
            sa, page, _ = self._ensure_page(self.current)
            self.pageh.jump(self._card_h(self.current))
            self._layout_body()
            sa.show()
            page.on_show()
            self._fsnap = snapshot(self.body)                         # the new layout fades in
            self.body.hide()
            self.fade.jump(0.0)
            self._zoom_from = self._scale_shown / ui.scale if ui.scale else 1.0
            if abs(self._zoom_from - 1.0) > 0.001:                    # a new size glides in from the old one
                self.zoom.jump(0.0)
                self.zoom.to(1.0, 320)
                self.fade.to(1.0, 320)
            else:
                self.fade.to(1.0, 240)
        self._scale_shown = ui.scale
        self.update()
        self.ball.update()

    # ------------------------------------------------------------------ expand / collapse
    def show_ball(self) -> None:
        self._restore_position()
        self.ball.place()
        self.ball.show()
        self.ball.appear.to(1.0, 420)
        self._retime()

    def toggle(self) -> None:
        self.collapse() if self.expanded else self.expand()

    def expand(self) -> None:
        """Open the card where it lives. If the ball is parked in a corner it first flies back there."""
        if self.expanded or self.morph.busy or self.ball.gliding or self.ctx.welcome is not None:
            return
        home, b = self.card_pos, self.ball
        parked = self._docked is not None and (b.center - self._docked).manhattanLength() < 4
        # The card opens from the ball. Only when the ball sits in the corner of a card the user had moved
        # does the card come back exactly where it was.
        self._pending_home = home if (home is not None and parked and self._closed_at_card) else None
        if self._pending_home is not None:
            d, cw = BD(), S(CARD_W)
            target = QPoint(max(home.x() + d // 2, min(b.center.x(), home.x() + cw - d // 2)), home.y() + d // 2)
            if (target - b.center).manhattanLength() > 6:
                b.hover.jump(0.0)
                return b.glide_to(target, then=self._expand_now, fast=True)
        self._expand_now()

    def _expand_now(self) -> None:
        if self.expanded or self.morph.busy:
            return
        self.chrome.jump(1.0)
        self.expanded = True
        self.ctx.cfg["card_open"] = True
        self.ball.appear.jump(1.0)
        self.ball.hover.jump(0.0)
        self._place(self.ball.rect_global(), self._pending_home)   # laid out while hidden: nothing can flash
        self._open_from, self._open_card = QPoint(self.ball.center), QPoint(self.card_pos)
        sa, _page, _ = self._ensure_page(self.current)
        for key, (other, _p, _h) in list(self.pages.items()):   # only the page being opened shows (no overlap)
            if other is not sa:
                other.hide()
        self.pageh.jump(self._card_h(self.current))
        self._layout_body()
        sa.show()
        self._snap = snapshot(self.body)
        self.body.hide()
        self.morph.jump(0.0)
        self.show()
        self.repaint()                                     # first frame = the ball, exactly where it already is
        self.ball.hide()
        self.morph.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.morph.to(1.0, 400)
        self._retime()
        self.ctx.on_visibility()

    def collapse(self) -> None:
        if not self.expanded or self.morph.busy:
            return
        if getattr(self, "sheet", None) is not None:          # folding the menu closes a small screen
            tab = self.sheet_tab
            self._close_sheet()
            self._drop_page(tab)
        self._finish_slide()
        self.pageh.jump(self.pageh.target)
        self.fade.jump(1.0)
        self.toast_w.hide()
        self.confirm_w.hide()
        self.busy_w.hide()
        self.drawer.close_now()
        self._spark_timer.stop()
        self._idle.stop()
        self.expanded = False
        self.ctx.cfg["card_open"] = False
        c, d = self._card_rect(), BD()
        centre = self.mapToGlobal(c.center().toPoint())
        wa = work_area(centre)
        left = centre.x() < wa.center().x()
        if self._open_from is not None and self._open_card is not None and self.card_pos == self._open_card:
            # The card was not moved: it folds back into the ball exactly where the ball was.
            here = self.mapFromGlobal(self._open_from)
            self._ball_l = QRectF(here.x() - d / 2, here.y() - d / 2, d, d)
            self._closed_at_card = False
        else:
            # The card was moved: it folds into its own top corner (the side nearer the screen edge) and the
            # ball stays there, so the card opens in the same place next time.
            self._ball_l = QRectF(c.left() if left else c.right() - d, c.top(), d, d)
            self._closed_at_card = True
        here = self.mapToGlobal(self._ball_l.center().toPoint())
        safe = self.ball.keep_clear(here)                  # never folds into the top-right corner of a screen
        if safe != here:
            self._ball_l.translate(QPointF(safe - here))
        page = self.page()
        self._snap = snapshot(self.body)
        if page:
            page.on_hide()
        self.body.hide()
        if self.current in TEMP_TABS:                      # the temporary tab goes away with the card
            TEMP_TABS.clear()
            self.current = "home"
            self.ctx.cfg["page"] = "home"
            self.body.set_tabs()
        self.morph.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.morph.to(0.0, 300)
        self.ctx.on_visibility()

    def _on_morph(self) -> None:
        t = self.morph.level
        if not self.morph.busy:
            if self.expanded and t >= 0.999 and not self.body.isVisible():
                self._snap = None
                self._layout_body()
                self.body.show()
                page = self.page()
                if page:
                    page.on_show()
                self._in_since, self._out_since = 0.0, time.monotonic()
                self._idle.start()
                QTimer.singleShot(600, self.ctx.offer_update)
                if hasattr(self.ctx, "on_opened"):
                    QTimer.singleShot(450, self.ctx.on_opened)
            elif not self.expanded and t <= 0.001 and self.isVisible():
                self._snap = None
                self.ball.set_center(self.mapToGlobal(self._ball_l.center().toPoint()))
                self.ball.show()
                self.ball.repaint()                        # the real ball is drawn on top of the painted one
                self.hide()
                self._retime()
                self._docked = QPoint(self.ball.center)
                self.save_position()                       # the ball stays where the card closed
                if self._reset_to is not None:             # "Reset position" asked while the card was open
                    target, self._reset_to = self._reset_to, None
                    self._docked = None
                    self.ball.glide_to(target)
                if self.current == "perf":
                    self._drop_page("perf")
        self.update()

    def toast(self, text: str, kind: str = "ok") -> None:
        if self.expanded and not self.morph.busy:
            self.toast_w.show_text(text, kind, self._card_rect())

    def confirm(self, text: str, on_yes, yes: str = "", no: str = "", persistent: bool = False,
                on_no=None) -> None:
        if self.expanded and not self.morph.busy:
            self.toast_w.hide()
            self.confirm_w.ask(text, on_yes, self._card_rect(), yes, no, persistent, on_no)

    # ------------------------------------------------------------------ loading overlay
    def show_busy(self, text: str) -> None:
        if self.expanded and not self.morph.busy:
            self.toast_w.hide()
            self.confirm_w.hide()
            self.busy_w.start(text, self._card_rect())

    def end_busy(self, then=None) -> None:
        self.busy_w.finish(then)

    def _on_fade(self) -> None:
        if self.fade.level >= 0.999 and self._fsnap is not None:
            self._fsnap = None
            if self.expanded and not self.morph.busy:
                self.body.show()
        self.update()

    # ------------------------------------------------------------------ menu bar auto-hide
    def _chrome_allowed(self) -> bool:
        return (self.ctx.cfg["autohide"] and self.expanded and self.current in MUSIC_PAGES
                and not self.morph.busy and not self.slide.busy and self._snap_new is None
                and self._drag_origin is None and not self.confirm_w.isVisible() and not self.drawer.is_open()
                and not self.busy_w.isVisible()
                and not self.modal)

    def _watch_idle(self) -> None:
        if not self.expanded or self.morph.busy:
            return
        now = time.monotonic()
        m = S(6)
        inside = self.card_global().adjusted(-m, -m, m, m).contains(QCursor.pos())
        if inside != getattr(self, "_was_inside", None):       # 4.3: Compact Music Mode unfolds under the mouse
            self._was_inside = inside
            if not self.ctx.cfg["autohide"]:
                QTimer.singleShot(0, lambda: (lambda pg: pg.set_compact(self.chrome.level)
                                              if pg is not None and hasattr(pg, "set_compact") else None)(self.page()))
        if inside:
            self._in_since, self._out_since = self._in_since or now, 0.0
        else:
            self._out_since, self._in_since = self._out_since or now, 0.0
        allowed = self._chrome_allowed()
        if self.chrome.target > 0.5:
            if allowed and self._out_since and now - self._out_since > 2.5 and not self.isActiveWindow():   # 4.3: focused: stays
                self.toast_w.hide()
                self.chrome.to(0.0, 420)
        elif not allowed or (self._in_since and now - self._in_since > 0.25) or (inside and win.key_down(0x01)):
            self.chrome.to(1.0, 320)

    def show_chrome(self) -> None:
        self._in_since, self._out_since = time.monotonic(), 0.0
        if self.chrome.target < 0.5:
            self.chrome.to(1.0, 320)

    def chrome_setting(self) -> None:
        if not self.ctx.cfg["autohide"]:
            self.show_chrome()

    def _on_chrome(self) -> None:
        if self.expanded and not self.morph.busy:
            self._layout_body()
            self.body.resizeEvent(None)
        self.update()

    def theme_changed(self) -> None:
        self._sparks = extras.theme_sparkles(self.ctx.theme(), self._max_l.width(), self._max_l.height(), S(BAND))
        self._retime()
        self.update()
        self.ball.update()
        for page in self.each_page():
            page.update()

    def _twinkle(self) -> None:
        """Repaint only the little squares around each sparkle."""
        if not self.expanded or self.morph.busy or self.pageh.busy or self.slide.busy or not self._sparks:
            return
        card, m = self._card_rect(), self._max_l
        region = QRegion()
        pad = S(6)
        for x, y, *_rest in self._sparks:
            px, py = m.left() + x, m.top() + y
            if py < card.bottom():
                region = region.united(QRegion(int(px - pad), int(py - pad), 2 * pad, 2 * pad))
        self.update(region)

    def pick_file(self, title: str, pattern: str) -> str:
        if win.fullscreen_state() == 2:
            self.toast(tr("Leave your game first"), "warn")
            return ""
        self.modal = True
        self.hide()                       # the card is always on top and would cover the dialog
        try:
            path, _ = QFileDialog.getOpenFileName(None, title, "", pattern)
        finally:
            self.show()
            self.modal = False
        return path or ""

    # ------------------------------------------------------------------ timers / state
    def set_game_state(self, state: int) -> None:
        if state != self.game_state:
            self.game_state = state
            self._retime()
            page = self.page()                     # 4.0: Compact Music Mode follows the game
            if page is not None and hasattr(page, "set_compact"):
                page.set_compact(self.chrome.level)

    def _retime(self) -> None:
        """Animation clock. The glow only needs to be smooth when it follows music: 60 fps on the open card while
        music plays, 30 otherwise, 20 for the breathing ball, nothing in exclusive fullscreen. Keeps Rubenium light."""
        if self.game_state == 2:
            self._pulse.stop()
            self._spark_timer.stop()
            return
        if self.expanded and self._sparks:
            self._spark_timer.start()
        else:
            self._spark_timer.stop()
        if self.ctx.cfg["halo"]:
            music = self.ctx.state.status is Status.PLAYING
            if self.expanded:
                ms = 16 if music else 33
            else:
                ms = 33 if music else 50
            if self.game_state == 1:
                ms = 66
        else:
            ms = 33 if self.expanded else 1000
        self._pulse.start(ms)

    def _tick(self) -> None:
        if not self.expanded:
            if self.ball.isVisible() and not self.ball.gliding:
                self.ball.update()
            return
        if self.morph.busy or self.pageh.busy or self.slide.busy or self.chrome.busy:
            return
        if self.ctx.cfg["halo"] or self.ctx.theme().get("edge") == "shine":
            shape, _r = self._shape()
            g = S(GLOW)
            outer = shape.adjusted(-g, -g, g, g).toAlignedRect()
            inner = shape.adjusted(4, 4, -4, -4).toAlignedRect()
            self.update(QRegion(outer).subtracted(QRegion(inner)))
        if self.ctx.state.status is Status.PLAYING and self.body.isVisible():
            self.body.update(self.body.dots_rect())

    def on_state(self, st) -> None:
        playing = st.status is Status.PLAYING
        if playing != getattr(self, "_was_playing", None):
            self._was_playing = playing
            self._retime()
        for page in self.each_page():
            page.on_state(st)
        if self.body.isVisible():
            self.body.update(self.body.dots_rect())

    def on_art(self, pixmap) -> None:
        for page in self.each_page():
            page.on_art(pixmap)

    def set_accent(self, color: QColor) -> None:
        if color == self._accent_to:
            return
        self._accent_from, self._accent_to = QColor(ui.accent), QColor(color)
        self.accent_t.jump(0.0)
        self.accent_t.to(1.0, 450)

    def set_accent_now(self, color: QColor) -> None:
        """Animated themes step the colour themselves (a few times a second)."""
        self.accent_t.stop()
        self._accent_from = self._accent_to = QColor(color)
        self.accent_t.jump(1.0)

    def _on_accent(self) -> None:
        ui.accent = mix(self._accent_from, self._accent_to, self.accent_t.level)
        self.update()
        self.ball.update()
        if self.body.isVisible():
            for w in self.body.findChildren(QWidget):
                if w.isVisible():
                    w.update()
            self.body.update()

    def set_opacity(self, pct: int) -> None:
        self.setWindowOpacity(pct / 100)
        self.ball.setWindowOpacity(pct / 100)

    # ------------------------------------------------------------------ painting
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = max(0.0, min(1.0, self.morph.level))
        if self.zoom.busy and self._zoom_from != 1.0:       # size changed: the card grows or shrinks into place
            k = lerp(self._zoom_from, 1.0, self.zoom.level)
            o = self._max_l.topLeft()
            p.translate(o.x(), o.y())
            p.scale(k, k)
            p.translate(-o.x(), -o.y())
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        shape, radius = self._shape()
        level = self.ctx.glow_level()
        path = paint_shape(p, self.ctx, shape, radius, level, self.devicePixelRatioF())
        th = self.ctx.theme()
        if t > 0.3 and (th["layers"] or self._sparks or ui.accent2 is not None):
            m = self._max_l
            p.save()
            p.setClipPath(path)
            p.setOpacity(min(1.0, (t - 0.3) / 0.5))
            pm = extras.theme_pattern(th, int(m.width()), int(m.height()), self._accent_to, self.devicePixelRatioF(),
                                      ui.scale, S(BAND))
            if pm is not None:
                p.drawPixmap(m.topLeft(), pm)
            if self._sparks and not (self.expanded and self.current == "rl"):    # 4.0: the swaps stay clean
                extras.paint_sparkles(p, self._sparks, m.left(), m.top(), ui.accent, time.monotonic(), ui.scale)
            p.restore()
        if t < 0.4:
            paint_ball_face(p, self.ctx, shape, 1.0 - t / 0.4)
        card = self._card_rect()
        if self._fsnap is not None and not self.morph.busy:
            p.save()
            p.setClipPath(path)
            p.setOpacity(self.fade.level)
            p.drawPixmap(card.topLeft(), self._fsnap)
            p.restore()
        f = t
        if self.morph.busy:                         # fade by time, not by size: content arrives last, leaves first
            lin = self.morph.currentTime() / max(1, self.morph.duration())
            f = (lin - 0.45) / 0.55 if self.expanded else 1.0 - lin / 0.35
            f = max(0.0, min(1.0, f))
        if self._snap is not None and f > 0.0:
            p.save()
            p.setClipPath(path)
            p.setOpacity(f * f * (3 - 2 * f))
            p.drawPixmap(QPointF(card.left(), card.top() + (1 - f) * S(6)), self._snap)
            p.restore()
        if self._snap_new is not None and self.expanded and not self.morph.busy:
            s = self.slide.level
            area = QRectF(card.left() + S(PAD), card.top() + S(CHROME_TOP), S(CARD_W - 2 * PAD + ScrollArea.GUTTER),
                          max(0.0, card.height() - S(CHROME_TOP + CHROME_BOTTOM)))
            p.save()
            p.setClipRect(area)
            shift = S(30) * self._dir
            if self._snap_old is not None:
                p.setOpacity(max(0.0, 1.0 - s * 1.6))
                p.drawPixmap(QPointF(area.left() - s * shift, area.top()), self._snap_old)
            p.setOpacity(min(1.0, s * 1.3))
            p.drawPixmap(QPointF(area.left() + (1 - s) * shift, area.top()), self._snap_new)
            p.restore()
        paint_edge(p, self.ctx, shape, radius, level)

    # ------------------------------------------------------------------ dragging the card (kept on screen)
    def begin_drag(self, grab: QPoint) -> None:
        """Start moving the card. `grab` is the screen point that was pressed: that point of the card stays
        exactly under the mouse. The card follows the mouse every frame, gliding the last few pixels."""
        self._drag_start = QPoint(grab)
        self._drag_origin = self.pos()
        self._drag_at = QPointF(self.pos())
        self.drawer.close_now()
        self._follow.start()
        self._follow_step()

    def _drag_target(self, cursor: QPoint) -> QPoint:
        new = self._drag_origin + (cursor - self._drag_start)          # stored origin + total delta: no drift
        c = self._card_rect()
        wa, m = work_area(cursor), S(8)
        x = max(wa.left() + m - c.left(), min(new.x(), wa.right() - m - c.right()))
        y = max(wa.top() + m - c.top(), min(new.y(), wa.bottom() - m - S(MIN_CARD) - c.top()))
        return QPoint(int(x), int(y))

    def _follow_step(self) -> None:
        if self._drag_origin is None:
            self._follow.stop()
            return
        if not (QGuiApplication.mouseButtons() & Qt.MouseButton.LeftButton) and not self._follow_test:
            self.body.release_drag()                     # let go anywhere: the drag ends
            return
        target = QPointF(self._drag_target(QCursor.pos()))
        gap = target - self._drag_at
        if abs(gap.x()) + abs(gap.y()) < 1.5:
            self._drag_at = target
        else:
            self._drag_at = self._drag_at + gap * 0.55   # quick, smooth catch-up; never lags behind
        self.move(round(self._drag_at.x()), round(self._drag_at.y()))

    def end_drag(self) -> None:
        if self._drag_origin is None:
            return
        self._follow.stop()
        self.move(self._drag_target(QCursor.pos()))       # lands exactly where the mouse is
        moved = self.pos() != self._drag_origin
        self._drag_origin = None
        if moved and self.expanded and not self.morph.busy:
            home = self.card_global().topLeft()                         # this is now where the card lives
            d = BD()
            self._place(QRect(home.x(), home.y(), d, d), home)
            self._layout_body()
            if self.current in self.pages:
                self.pageh.to(self._card_h(self.current), 220)

    # ------------------------------------------------------------------ position persistence (per monitor, normalised)
    def save_position(self) -> None:
        c = self.ball.center
        screen = QGuiApplication.screenAt(c) or QGuiApplication.primaryScreen()
        wa = screen.availableGeometry()
        self.ctx.cfg["ball"] = {"screen": screen.name(),
                                "nx": (c.x() - wa.left()) / max(1, wa.width()),
                                "ny": (c.y() - wa.top()) / max(1, wa.height())}

    def _restore_position(self) -> None:
        b = self.ctx.cfg["ball"]
        screen = next((s for s in QGuiApplication.screens() if s.name() == b["screen"]), None)
        if screen is not None and 0 <= b["nx"] <= 1 and 0 <= b["ny"] <= 1:
            wa = screen.availableGeometry()
            self.ball.center = QPoint(int(wa.left() + b["nx"] * wa.width()), int(wa.top() + b["ny"] * wa.height()))
            self.ball.clamp()
        else:
            wa = QGuiApplication.primaryScreen().availableGeometry()
            self.ball.center = self.ball.corner_point(wa, False, True)
        c = self.ctx.cfg["card"]
        screen = next((s for s in QGuiApplication.screens() if s.name() == c["screen"]), None)
        if screen is not None and 0 <= c["nx"] <= 1 and 0 <= c["ny"] <= 1:
            wa = screen.availableGeometry()
            self.card_pos = QPoint(int(wa.left() + c["nx"] * wa.width()), int(wa.top() + c["ny"] * wa.height()))
            self._docked = QPoint(self.ball.center)
            d, b = BD(), self.ball.center                  # is the ball in that card's top corner?
            self._closed_at_card = (abs(b.y() - (self.card_pos.y() + d // 2)) <= 4
                                    and self.card_pos.x() - 4 <= b.x() - d // 2 <= self.card_pos.x() + S(CARD_W))

    def reset_position(self) -> None:
        self.card_pos = self._docked = None
        self.ctx.cfg["card"] = {"screen": "", "nx": -1.0, "ny": -1.0}
        wa = QGuiApplication.primaryScreen().availableGeometry()
        target = self.ball.corner_point(wa, False, True)
        if self.expanded:
            self._reset_to = target
            self.collapse()
        else:
            self.ball.glide_to(target)

    def closeEvent(self, e) -> None:
        e.ignore()
        self.ctx.quit()
