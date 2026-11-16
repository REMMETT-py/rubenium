# -*- coding: utf-8 -*-
"""Custom-painted controls. No stock Qt control is ever shown; nothing here takes keyboard focus."""
from __future__ import annotations

import math
from collections import deque
from typing import Callable, Optional

from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, QTimer, QVariantAnimation, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PyQt6.QtWidgets import QAbstractButton, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from . import win
from .core import (DANGER, PLACEHOLDER, S, sfx, SURFACE, SURFACE_HI, TEXT, TEXT_DIM, TEXT_FAINT, TRACK, WARN,
                   alpha, font, mix, tr, ui)

AA = QPainter.RenderHint.Antialiasing


class Tween(QVariantAnimation):
    """Float animator that always continues from its current value (interruptions retarget)."""

    def __init__(self, parent, initial: float = 0.0, on_change: Optional[Callable[[], None]] = None,
                 easing: QEasingCurve.Type = QEasingCurve.Type.OutCubic) -> None:
        super().__init__(parent)
        self._value = float(initial)
        self.target = float(initial)
        self._mute = False
        self._on_change = on_change
        self.setEasingCurve(easing)
        self.valueChanged.connect(self._handle)

    @property
    def level(self) -> float:
        return self._value

    def _handle(self, value) -> None:
        if self._mute:
            return
        self._value = float(value)
        if self._on_change:
            self._on_change()

    def to(self, target: float, ms: int = 150) -> None:
        self.stop()
        self.target = float(target)
        if abs(target - self._value) < 1e-6:
            self._handle(target)
            return
        self._mute = True                 # re-arming a finished animation makes Qt emit stale values
        start = self._value
        self.setCurrentTime(0)
        self.setStartValue(start)
        self.setEndValue(float(target))
        self.setDuration(ms)
        self._mute = False
        self._value = start
        self.start()

    def jump(self, value: float) -> None:
        self.stop()
        self.target = float(value)
        self._handle(value)

    @property
    def busy(self) -> bool:
        """Still travelling. False during the final value callback, so 'arrived' logic can run there."""
        return self.state() == QVariantAnimation.State.Running and abs(self._value - self.target) > 1e-6


# --------------------------------------------------------------------------- #
# Vector icons (20-unit box centred on 0,0; 1.75 stroke, round caps)
# --------------------------------------------------------------------------- #
_GEAR: Optional[QPainterPath] = None
FILLED = {"play", "pause", "prev", "next", "cog", "dice"}


def _gear_path() -> QPainterPath:
    global _GEAR
    if _GEAR is None:
        body = QPainterPath()
        body.addEllipse(QPointF(0, 0), 6.0, 6.0)
        for k in range(8):
            tooth = QPainterPath()
            tooth.addRoundedRect(QRectF(-1.6, -8.8, 3.2, 4.0), 0.8, 0.8)
            rot = QTransform()
            rot.rotate(k * 45)
            body = body.united(rot.map(tooth))
        hole = QPainterPath()
        hole.addEllipse(QPointF(0, 0), 2.5, 2.5)
        _GEAR = body.subtracted(hole)
    return _GEAR


def _poly(*pts) -> QPainterPath:
    path = QPainterPath(QPointF(*pts[0]))
    for pt in pts[1:]:
        path.lineTo(QPointF(*pt))
    return path


def draw_icon(p: QPainter, kind: str, fg: QColor, hover: float = 0.0) -> None:
    """Draw `kind` centred on the painter origin, in a 20-unit box."""
    p.save()
    if kind in FILLED:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fg)
        if kind == "play":
            path = _poly((-4.5, -6.5), (-4.5, 6.5), (6.5, 0))
            path.closeSubpath()
            p.drawPath(path)
        elif kind == "pause":
            p.drawRoundedRect(QRectF(-5.5, -6.5, 3.6, 13), 1, 1)
            p.drawRoundedRect(QRectF(1.9, -6.5, 3.6, 13), 1, 1)
        elif kind == "prev":
            p.drawRoundedRect(QRectF(-8, -6, 2.2, 12), 1, 1)
            path = _poly((7, -6.5), (7, 6.5), (-5, 0))
            path.closeSubpath()
            p.drawPath(path)
        elif kind == "next":
            p.drawRoundedRect(QRectF(5.8, -6, 2.2, 12), 1, 1)
            path = _poly((-7, -6.5), (-7, 6.5), (5, 0))
            path.closeSubpath()
            p.drawPath(path)
        elif kind == "dice":
            die = QPainterPath()
            die.addRoundedRect(QRectF(-7.5, -7.5, 15, 15), 3.5, 3.5)
            for dx, dy in ((-3.6, -3.6), (3.6, 3.6), (0, 0), (3.6, -3.6), (-3.6, 3.6)):
                dot = QPainterPath()
                dot.addEllipse(QPointF(dx, dy), 1.25, 1.25)
                die = die.subtracted(dot)
            p.drawPath(die)
        elif kind == "cog":
            p.rotate(hover * 60.0)
            p.drawPath(_gear_path())
        p.restore()
        return
    pen = QPen(fg, 1.75)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    line = lambda a, b, c, d: p.drawLine(QPointF(a, b), QPointF(c, d))  # noqa: E731
    if kind == "back":
        p.drawPath(_poly((3, -6.5), (-3.5, 0), (3, 6.5)))
    elif kind == "close":
        line(-4.5, -4.5, 4.5, 4.5)
        line(-4.5, 4.5, 4.5, -4.5)
    elif kind == "home":
        p.drawPath(_poly((-7.5, -0.5), (0, -7.5), (7.5, -0.5)))
        p.drawPath(_poly((-5.2, -2.5), (-5.2, 7), (5.2, 7), (5.2, -2.5)))
    elif kind == "lyrics":
        line(-7, -5, 7, -5)
        line(-7, 0, 2.5, 0)
        line(-7, 5, 5.5, 5)
    elif kind == "crosshair":
        p.drawEllipse(QPointF(0, 0), 6, 6)
        for a, b, c, d in ((0, -9, 0, -4), (0, 4, 0, 9), (-9, 0, -4, 0), (4, 0, 9, 0)):
            line(a, b, c, d)
    elif kind == "display":
        p.drawRoundedRect(QRectF(-8, -7, 16, 11), 2, 2)
        line(0, 4, 0, 7.5)
        line(-3.5, 7.5, 3.5, 7.5)
    elif kind == "perf":
        p.drawPath(_poly((-8.5, 1), (-4.5, 1), (-2, -6), (1.5, 6.5), (3.5, 1), (8.5, 1)))
    elif kind == "tools":
        path = _poly((1.5, -8), (-5.5, 1.5), (-0.5, 1.5), (-1.5, 8), (5.5, -1.5), (0.5, -1.5))
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "rocket":
        path = QPainterPath(QPointF(0, -8.5))
        path.cubicTo(4.5, -5, 4.5, 1, 2.6, 4.5)
        path.lineTo(-2.6, 4.5)
        path.cubicTo(-4.5, 1, -4.5, -5, 0, -8.5)
        p.drawPath(path)
        p.drawEllipse(QPointF(0, -2.2), 1.5, 1.5)
        line(-3.2, 2.2, -6, 6)
        line(3.2, 2.2, 6, 6)
        line(0, 6.5, 0, 8.5)
    elif kind == "power":
        p.drawArc(QRectF(-6.5, -5.5, 13, 13), int(130 * 16), int(280 * 16))
        line(0, -8, 0, -1)
    elif kind == "rball":
        p.drawEllipse(QPointF(0, 0), 8.6, 8.6)
        f = QFont()
        f.setFamilies(["Segoe UI Variable", "Segoe UI", "Arial"])
        f.setPixelSize(11)
        f.setWeight(QFont.Weight.ExtraBold)
        p.setFont(f)
        p.drawText(QRectF(-8, -8.4, 16.6, 16), int(Qt.AlignmentFlag.AlignCenter), "R")
    elif kind in ("volume", "muted"):
        p.setBrush(fg)
        path = _poly((-7.5, -2.6), (-4.2, -2.6), (0.2, -6.5), (0.2, 6.5), (-4.2, 2.6), (-7.5, 2.6))
        path.closeSubpath()
        p.drawPath(path)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if kind == "volume":
            p.drawArc(QRectF(-3.5, -4.5, 9, 9), -50 * 16, 100 * 16)
            p.drawArc(QRectF(-4.5, -8, 15, 16), -50 * 16, 100 * 16)
        else:
            line(3.5, -3, 8.5, 3)
            line(3.5, 3, 8.5, -3)
    elif kind == "timer":
        p.drawEllipse(QPointF(0, 1.5), 6.5, 6.5)
        line(0, 1.5, 0, -2.5)
        line(0, 1.5, 2.6, 3)
        line(-2, -8, 2, -8)
        line(0, -8, 0, -5)
    elif kind == "users":
        p.drawEllipse(QPointF(-3, -3.5), 3.2, 3.2)
        arc = QPainterPath()
        arc.moveTo(-8.5, 7)
        arc.cubicTo(-8.5, 1, 2.5, 1, 2.5, 7)
        p.drawPath(arc)
        p.drawEllipse(QPointF(5, -2), 2.4, 2.4)
        arc2 = QPainterPath()
        arc2.moveTo(5.5, 2.6)
        arc2.cubicTo(8, 2.8, 9, 4.5, 9, 7)
        p.drawPath(arc2)
    elif kind == "gem":
        p.drawPath(_poly((-8, -2), (-4, -7), (4, -7), (8, -2), (0, 8), (-8, -2)))
        p.drawPath(_poly((-8, -2), (8, -2)))
        p.drawPath(_poly((-3, -2), (0, 8), (3, -2)))
    elif kind == "spark":
        star = _poly((0, -8.5), (2.2, -2.2), (8.5, 0), (2.2, 2.2), (0, 8.5), (-2.2, 2.2), (-8.5, 0), (-2.2, -2.2))
        star.closeSubpath()
        p.drawPath(star)
    elif kind == "grid":
        for gx, gy in ((-7.5, -7.5), (1.5, -7.5), (-7.5, 1.5), (1.5, 1.5)):
            p.drawRoundedRect(QRectF(gx, gy, 6, 6), 1.5, 1.5)
    elif kind == "ball":
        p.drawEllipse(QPointF(0, 0), 5.5, 5.5)
        p.setBrush(fg)
        p.drawEllipse(QPointF(0, 0), 1.6, 1.6)
    elif kind == "shuffle":
        p.drawPath(_poly((-7.5, -4), (-3.5, -4), (2.5, 4), (7, 4)))
        p.drawPath(_poly((-7.5, 4), (-3.5, 4), (-1.6, 1.4)))
        p.drawPath(_poly((1, -2), (2.5, -4), (7, -4)))
        p.drawPath(_poly((5, -6), (7.3, -4), (5, -2)))
        p.drawPath(_poly((5, 2), (7.3, 4), (5, 6)))
    elif kind in ("repeat", "repeat1"):
        p.drawPath(_poly((-6.5, -0.5), (-6.5, -2), (-4.5, -4), (6, -4)))
        p.drawPath(_poly((6.5, 0.5), (6.5, 2), (4.5, 4), (-6, 4)))
        p.drawPath(_poly((4, -6.2), (6.4, -4), (4, -1.8)))
        p.drawPath(_poly((-4, 6.2), (-6.4, 4), (-4, 1.8)))
        if kind == "repeat1":
            p.setFont(_tiny_font())
            p.drawText(QRectF(-4, -4, 8, 8), int(Qt.AlignmentFlag.AlignCenter), "1")
    elif kind == "lock":
        p.drawRoundedRect(QRectF(-5, -1, 10, 8), 2, 2)
        p.drawArc(QRectF(-3.2, -7, 6.4, 9), 0, 180 * 16)
    elif kind == "gift":
        p.drawRoundedRect(QRectF(-6.5, -2, 13, 9), 1.5, 1.5)
        p.drawRect(QRectF(-7.5, -5, 15, 3))
        line(0, -5, 0, 7)
        p.drawArc(QRectF(-5, -9, 5, 4.5), 0, 270 * 16)
        p.drawArc(QRectF(0, -9, 5, 4.5), -90 * 16, 270 * 16)
    elif kind == "shield":
        p.drawPath(_poly((0, -7.5), (6.5, -5), (6, 1.5), (0, 7.5), (-6, 1.5), (-6.5, -5), (0, -7.5)))
        line(-2.5, 0, -0.5, 2.5)
        line(-0.5, 2.5, 3, -2)
    elif kind == "folder":
        p.drawPath(_poly((-7.5, 6), (-7.5, -5.5), (-2.5, -5.5), (-0.5, -3), (7.5, -3), (7.5, 6), (-7.5, 6)))
    elif kind == "copy":
        p.drawRoundedRect(QRectF(-3, -3, 10, 10), 2, 2)
        p.drawPath(_poly((-7, 3), (-7, -7), (3, -7)))
    elif kind == "trash":
        line(-6.5, -4.5, 6.5, -4.5)
        p.drawPath(_poly((-4.8, -4.5), (-4, 7), (4, 7), (4.8, -4.5)))
        line(-2, -7, 2, -7)
    elif kind == "plus":
        line(-6, 0, 6, 0)
        line(0, -6, 0, 6)
    elif kind == "check":
        p.drawPath(_poly((-6, 0.5), (-2, 4.5), (6.5, -4.5)))
    elif kind == "refresh":
        p.drawArc(QRectF(-6.5, -6.5, 13, 13), 40 * 16, 290 * 16)
        p.drawPath(_poly((2.2, -7.6), (6.2, -5.2), (3.6, -1.6)))
    elif kind == "note":
        p.setBrush(fg)
        p.drawEllipse(QPointF(-3.2, 5), 2.6, 2.1)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(_poly((-0.7, 5), (-0.7, -7), (5, -5), (5, -1.5)))
    elif kind == "chip":
        p.drawRoundedRect(QRectF(-5, -5, 10, 10), 1.5, 1.5)
        for k in (-2.5, 2.5):
            line(k, -8, k, -5)
            line(k, 5, k, 8)
            line(-8, k, -5, k)
            line(5, k, 8, k)
    elif kind == "key":
        p.drawEllipse(QPointF(-3.5, 0), 3.5, 3.5)
        p.drawPath(_poly((0, 0), (8, 0), (8, 3)))
        line(4.5, 0, 4.5, 2.5)
    p.restore()


def _tiny_font() -> QFont:
    f = QFont()
    f.setPixelSize(6)
    f.setWeight(QFont.Weight.Bold)
    return f


# --------------------------------------------------------------------------- #
# Buttons
# --------------------------------------------------------------------------- #
class IconButton(QAbstractButton):
    """Vector icon button with animated hover / press feedback (timings from the original app)."""

    def __init__(self, kind: str, size: int = 28, primary: bool = False, tip: str = "", parent=None) -> None:
        super().__init__(parent)
        self._kind = kind
        self._primary = primary
        self._size = size
        self.fade = 1.0                # opacity, used when the menu bar hides
        self.active = False            # accent tint (e.g. shuffle on)
        self.dot = False               # small accent dot under the icon
        self.setFixedSize(S(size), S(size))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if tip:
            self.setToolTip(tip)
        self._hover = Tween(self, on_change=self.update)
        self._press = Tween(self, on_change=self.update)

    def set_kind(self, kind: str) -> None:
        if kind != self._kind:
            self._kind = kind
            self.update()

    def set_active(self, on: bool) -> None:
        if on != self.active:
            self.active = self.dot = on
            self.update()

    def enterEvent(self, event) -> None:
        self._hover.to(1.0, 140)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover.to(0.0, 220)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press.to(1.0, 80)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._press.to(0.0, 170)
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        h, pr = self._hover.level, self._press.level
        p.setOpacity(self.fade)
        if not self.isEnabled():
            p.setOpacity(0.35 * self.fade)
            h = pr = 0.0
        scale = (self.width() / 28.0) * (1.0 + (0.07 if self._primary else 0.12) * h - 0.15 * pr)
        p.translate(self.width() / 2.0, self.height() / 2.0)
        p.scale(scale, scale)
        if self._primary:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(mix(QColor("#FFFFFF"), QColor("#D9D9D9"), pr))
            p.drawEllipse(QPointF(0, 0), 14, 14)
            fg = QColor("#000000")
            p.scale(0.82, 0.82)
        elif self.active:
            fg = mix(ui.accent, QColor(TEXT), 0.35 * h)
        else:
            fg = mix(mix(QColor(TEXT_DIM), QColor(TEXT), h), ui.accent, pr)
        p.scale(0.9, 0.9)
        draw_icon(p, self._kind, fg, h)
        if self.dot:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ui.accent)
            p.drawEllipse(QPointF(0, 12.5), 1.4, 1.4)


class Button(QAbstractButton):
    """Text button: 'ghost' (neutral), 'primary' (accent), 'danger' (warm gradient), 'quiet' (text only)."""

    def __init__(self, text: str, kind: str = "ghost", height: int = 32, icon: str = "", parent=None) -> None:
        super().__init__(parent)
        self._text, self._kind, self._icon = text, kind, icon
        self.setFixedHeight(S(height))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._hover = Tween(self, on_change=self.update)
        self._press = Tween(self, on_change=self.update)
        self._font = font(12, QFont.Weight.DemiBold)
        self.fade = 1.0

    def set_text(self, text: str) -> None:
        self._text = text
        self.update()

    def set_kind(self, kind: str) -> None:
        self._kind = kind
        self.update()

    def sizeHint(self):
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QFontMetrics
        w = QFontMetrics(self._font).horizontalAdvance(self._text) + S(28) + (S(18) if self._icon else 0)
        return QSize(w, self.height())

    def enterEvent(self, e) -> None:
        self._hover.to(1.0, 140)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover.to(0.0, 220)
        super().leaveEvent(e)

    def mousePressEvent(self, e) -> None:
        if self.fade < 0.5:                                 # faded out: let the click through
            e.ignore()
            return
        self._press.to(1.0, 80)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        self._press.to(0.0, 170)
        super().mouseReleaseEvent(e)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        h, pr = self._hover.level, self._press.level
        if self.fade < 0.01:
            return
        p.setOpacity(self.fade)
        if not self.isEnabled():
            p.setOpacity(0.4 * self.fade)
            h = pr = 0
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        inset = pr * S(1.5)
        r.adjust(inset, inset, -inset, -inset)
        rad = S(9)
        fg = QColor(TEXT)
        p.setPen(Qt.PenStyle.NoPen)
        if self._kind == "primary":
            p.setBrush(mix(ui.accent, QColor("#FFFFFF"), 0.14 * h))
            fg = QColor("#06110A")
        elif self._kind == "danger":
            p.setPen(QPen(alpha(DANGER, 0.45 + 0.25 * h), 1))
            p.setBrush(alpha(DANGER, 0.10 + 0.08 * h))
            fg = QColor("#FF8085")
        elif self._kind == "quiet":
            p.setBrush(alpha("#FFFFFF", 0.06 * h))
            fg = mix(QColor(TEXT_DIM), QColor(TEXT), h)
        else:
            p.setBrush(mix(QColor(SURFACE_HI), QColor("#3A3A3A"), h))
        p.drawRoundedRect(r, rad, rad)
        p.setFont(self._font)
        p.setPen(fg)
        if self._icon:
            tw = p.fontMetrics().horizontalAdvance(self._text)
            x0 = r.center().x() - (tw + S(20)) / 2
            p.save()
            p.translate(x0 + S(7), r.center().y())
            p.scale(S(14) / 20, S(14) / 20)
            draw_icon(p, self._icon, fg)
            p.restore()
            p.setPen(fg)
            p.drawText(QRectF(x0 + S(20), r.top(), tw + 4, r.height()), int(Qt.AlignmentFlag.AlignVCenter), self._text)
        else:
            text = p.fontMetrics().elidedText(self._text, Qt.TextElideMode.ElideRight, int(r.width() - S(12)))
            p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), text)


class Toggle(QAbstractButton):
    toggled_by_user = pyqtSignal(bool)

    def __init__(self, checked: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(S(38), S(22))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pos = Tween(self, 1.0 if checked else 0.0, self.update, QEasingCurve.Type.OutBack)
        self._hover = Tween(self, on_change=self.update)
        self.clicked.connect(self._clicked)

    def _clicked(self) -> None:
        self._pos.to(1.0 if self.isChecked() else 0.0, 220)
        sfx.play("on" if self.isChecked() else "off")
        self.toggled_by_user.emit(self.isChecked())

    def set_checked(self, on: bool) -> None:
        if on != self.isChecked():
            self.setChecked(on)
            self._pos.to(1.0 if on else 0.0, 220)

    def enterEvent(self, e) -> None:
        self._hover.to(1.0, 140)

    def leaveEvent(self, e) -> None:
        self._hover.to(0.0, 220)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        if not self.isEnabled():
            p.setOpacity(0.4)
        t = max(0.0, min(1.0, self._pos.level))
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        on = mix(QColor("#3A3F42"), ui.accent, t)
        light = ui.accent.lightnessF() > 0.72                     # white / pale album colours
        edge = mix(alpha("#FFFFFF", 0.14), mix(ui.accent, QColor("#000000"), 0.45) if light else alpha(ui.accent, 0.0), t)
        p.setPen(QPen(edge, 1.2))
        p.setBrush(on)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        kr = r.height() / 2 - S(2.5) + self._hover.level * S(0.8)
        x = r.left() + r.height() / 2 + t * (r.width() - r.height())
        knob = mix(QColor("#FFFFFF"), QColor("#0E1213"), t if light else 0.0)
        p.setPen(QPen(alpha("#000000", 0.35), 1) if not light else Qt.PenStyle.NoPen)
        p.setBrush(knob)
        p.drawEllipse(QPointF(x, r.center().y()), kr, kr)


class Slider(QWidget):
    changed = pyqtSignal(float)       # while dragging
    released = pyqtSignal(float)      # drag finished

    def __init__(self, lo: float, hi: float, value: float, step: float = 1.0,
                 default: Optional[float] = None, ticks: int = 0, marks=None, parent=None) -> None:
        super().__init__(parent)
        self.lo, self.hi, self.step = lo, hi, step
        self.default = default
        self.ticks = ticks
        self.marks = sorted(set(marks or ([] if default is None else [default])))   # lock-in points
        self._value = self._snap(value)
        self.setFixedHeight(S(22))
        self.setMinimumWidth(S(60))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._shown = Tween(self, self._frac(self._value), self.update)
        self._hover = Tween(self, on_change=self.update)
        self._drag = False
        self.rainbow = False

    def _snap(self, v: float) -> float:
        v = max(self.lo, min(self.hi, v))
        return round(round((v - self.lo) / self.step) * self.step + self.lo, 6)

    def _frac(self, v: float) -> float:
        return (v - self.lo) / (self.hi - self.lo) if self.hi > self.lo else 0.0

    def value(self) -> float:
        return self._value

    def set_value(self, v: float, animate: bool = True) -> None:
        self._value = self._snap(v)
        if animate and self.isVisible():
            self._shown.to(self._frac(self._value), 180)
        else:
            self._shown.jump(self._frac(self._value))

    def _from_x(self, x: float) -> None:
        m = S(7)
        span = max(1, self.width() - 2 * m)
        f = max(0.0, min(1.0, (x - m) / span))
        v = self._snap(self.lo + f * (self.hi - self.lo))
        for mark in self.marks:                                  # the knob clicks into place near a mark
            if abs(m + span * self._frac(mark) - x) <= S(5):
                v = self._snap(mark)
                break
        self._shown.jump(self._frac(v))
        if v != self._value:
            self._value = v
            self.changed.emit(v)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = True
            self._from_x(e.position().x())

    def mouseMoveEvent(self, e) -> None:
        if self._drag:
            self._from_x(e.position().x())

    def mouseReleaseEvent(self, e) -> None:
        if self._drag:
            self._drag = False
            self.released.emit(self._value)

    def mouseDoubleClickEvent(self, e) -> None:
        if self.default is not None:
            self.set_value(self.default)
            self.changed.emit(self._value)
            self.released.emit(self._value)

    def enterEvent(self, e) -> None:
        self._hover.to(1.0, 140)

    def leaveEvent(self, e) -> None:
        self._hover.to(0.0, 220)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        if not self.isEnabled():
            p.setOpacity(0.4)
        m, cy = S(7), self.height() / 2
        w = self.width() - 2 * m
        th = S(4)
        track = QRectF(m, cy - th / 2, w, th)
        p.setPen(Qt.PenStyle.NoPen)
        x = m + w * self._shown.level
        if self.rainbow:
            if getattr(self, "parked", False) and not self._drag:
                p.setOpacity(p.opacity() * 0.6)
            g = QLinearGradient(track.topLeft(), track.topRight())
            for i in range(7):
                g.setColorAt(i / 6, QColor.fromHsvF(min(0.999, i / 6), 0.9, 1.0))
            p.setBrush(g)
            p.drawRoundedRect(track, th / 2, th / 2)
        else:
            p.setBrush(QColor(TRACK))
            p.drawRoundedRect(track, th / 2, th / 2)
            p.setBrush(ui.accent)
            if self.lo < 0 < self.hi:                      # bipolar: fill from the centre
                zero = m + w * self._frac(0)
                p.drawRoundedRect(QRectF(min(zero, x), track.top(), abs(x - zero), th), th / 2, th / 2)
            else:
                p.drawRoundedRect(QRectF(m, track.top(), max(0.0, x - m), th), th / 2, th / 2)
        if self.ticks:
            p.setBrush(alpha("#FFFFFF", 0.25))
            for i in range(self.ticks + 1):
                p.drawRect(QRectF(m + w * i / self.ticks - 0.5, cy + th, 1, S(3)))
        for mark in self.marks:
            mx = m + w * self._frac(mark)
            p.setBrush(alpha("#FFFFFF", 0.55 if abs(mark - self._value) < 1e-6 else 0.22))
            p.drawEllipse(QPointF(mx, cy + th / 2 + S(4)), S(1.3), S(1.3))
        if getattr(self, "parked", False) and not self._drag:   # a plain colour is in use: knob rests off the line
            p.setPen(QPen(alpha("#FFFFFF", 0.55), S(1.3)))
            p.setBrush(QColor(14, 17, 18))
            p.drawEllipse(QPointF(x, cy + S(7)), S(3.8), S(3.8))
            return
        kr = S(5.5) + self._hover.level * S(1.2) + (S(1) if self._drag else 0)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QPointF(x, cy), kr, kr)


class Segmented(QWidget):
    changed = pyqtSignal(int)

    def __init__(self, labels: list, index: int = 0, parent=None) -> None:
        super().__init__(parent)
        self._labels = labels
        self._index = max(0, min(len(labels) - 1, index))
        self.setFixedHeight(S(28))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pos = Tween(self, float(self._index), self.update, QEasingCurve.Type.OutBack)
        self._font = font(11.5, QFont.Weight.DemiBold)
        self.faint: set = set()           # options shown but not available

    def index(self) -> int:
        return self._index

    def set_index(self, i: int) -> None:
        i = max(0, min(len(self._labels) - 1, i))
        if i != self._index:
            self._index = i
            self._pos.to(float(i), 260)

    def mousePressEvent(self, e) -> None:
        i = int(e.position().x() / max(1, self.width()) * len(self._labels))
        i = max(0, min(len(self._labels) - 1, i))
        if i != self._index:
            if i in self.faint:
                sfx.play("off")
            else:
                sfx.play("pick")
            self.set_index(i)
            self.changed.emit(i)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        if not self.isEnabled():
            p.setOpacity(0.4)
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.06))
        p.drawRoundedRect(r, S(8), S(8))
        n = len(self._labels)
        sw = r.width() / n
        pill = QRectF(self._pos.level * sw + S(2), S(2), sw - S(4), r.height() - S(4))
        p.setBrush(alpha(ui.accent, 0.22))
        p.drawRoundedRect(pill, S(6), S(6))
        p.setFont(self._font)
        for i, label in enumerate(self._labels):
            near = max(0.0, 1.0 - abs(self._pos.level - i))
            col = mix(QColor(TEXT_DIM), mix(ui.accent, QColor(TEXT), 0.55), near)
            if i in self.faint:
                col = alpha(TEXT_DIM, 0.35)
            p.setPen(col)
            cell = QRectF(i * sw, 0, sw, r.height())
            p.drawText(cell, int(Qt.AlignmentFlag.AlignCenter),
                       p.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, int(sw - S(6))))


class Swatches(QWidget):
    picked = pyqtSignal(str)

    def __init__(self, colors: list, current: str = "", per_row: int = 0, parent=None) -> None:
        super().__init__(parent)
        self._colors = colors
        self._current = current.upper()
        self.resting = False                  # the slider is in use: dots greyed a little (still clickable)
        self._per_row = per_row or len(colors)
        rows = (len(colors) + self._per_row - 1) // self._per_row
        self.setFixedHeight(S(26) * rows)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_current(self, c: str) -> None:
        self._current = c.upper()
        self.update()

    def _cell(self) -> float:
        return min(S(28) if self._per_row == len(self._colors) else S(44), self.width() / max(1, self._per_row))

    def _centre(self, i: int) -> QPointF:
        cell = self._cell()
        return QPointF((i % self._per_row) * cell + cell / 2, (i // self._per_row) * S(26) + S(13))

    def mousePressEvent(self, e) -> None:
        cell = self._cell()
        col = int(e.position().x() / cell)
        i = col + int(e.position().y() / S(26)) * self._per_row
        if 0 <= col < self._per_row and 0 <= i < len(self._colors):
            if self._current != self._colors[i].upper():
                sfx.play("pick")
            self._current = self._colors[i].upper()
            self.update()
            self.picked.emit(self._colors[i])

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        if self.resting:
            p.setOpacity(0.4)
        for i, c in enumerate(self._colors):
            centre = self._centre(i)
            if c.upper() == self._current:
                p.setPen(QPen(QColor("#FFFFFF"), 1.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(centre, S(10), S(10))
            p.setPen(QPen(alpha("#FFFFFF", 0.18), 1))
            p.setBrush(QColor(c))
            p.drawEllipse(centre, S(7), S(7))


# --------------------------------------------------------------------------- #
# Text, panels, data widgets
# --------------------------------------------------------------------------- #
class Label(QWidget):
    """Painted label. Single line elides; pass wrap_w to wrap at a fixed width."""

    def __init__(self, text: str = "", px: float = 12, color: str = TEXT, bold: bool = False,
                 align=Qt.AlignmentFlag.AlignLeft, wrap_w: int = 0, weight=None, parent=None, shrink: float = 0) -> None:
        super().__init__(parent)
        self._px, self._shrink = px, shrink          # shrink: smallest size a long single line may shrink to
        self._weight = weight or (QFont.Weight.Bold if bold else QFont.Weight.Normal)
        self._font = font(px, self._weight)
        self._color = QColor(color)
        self._align = align
        self._wrap_w = wrap_w
        self._text = ""
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        if wrap_w:
            self.setFixedWidth(wrap_w)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            self.setFixedHeight(S(px * 1.5))
        self.set_text(text)

    def set_text(self, text: str) -> None:
        if text == self._text:
            return
        self._text = text
        if self._wrap_w:
            from PyQt6.QtGui import QFontMetrics
            br = QFontMetrics(self._font).boundingRect(0, 0, self._wrap_w, 10000,
                                                      int(Qt.TextFlag.TextWordWrap), text)
            self.setFixedHeight(br.height() + 2)
        self.update()

    def set_color(self, color) -> None:
        self._color = QColor(color)
        self.update()

    def setFixedWidth(self, w: int) -> None:          # a fixed-width label must claim its space in layouts
        super().setFixedWidth(w)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def fit(self) -> "Label":
        self.setFixedWidth(self.text_width() + 2)
        return self

    def text(self) -> str:
        return self._text

    def text_width(self) -> int:
        from PyQt6.QtGui import QFontMetrics
        return QFontMetrics(self._font).horizontalAdvance(self._text)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setFont(self._font)
        p.setPen(self._color)
        if self._wrap_w:
            p.drawText(self.rect(), int(self._align | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), self._text)
        else:
            if self._shrink and p.fontMetrics().horizontalAdvance(self._text) > self.width():
                px = self._px                      # smaller until it fits, before ever cutting it with "…"
                while px > self._shrink and p.fontMetrics().horizontalAdvance(self._text) > self.width():
                    px = max(self._shrink, px - 0.5)
                    p.setFont(font(px, self._weight))
            text = p.fontMetrics().elidedText(self._text, Qt.TextElideMode.ElideRight, self.width())
            p.drawText(self.rect(), int(self._align | Qt.AlignmentFlag.AlignVCenter), text)


class Panel(QWidget):
    """Rounded elevated surface that hosts a layout."""

    def __init__(self, parent=None, tint: float = 0.045) -> None:
        super().__init__(parent)
        self._tint = tint
        self.accent_edge = False

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha(ui.accent, 0.45) if self.accent_edge else alpha("#FFFFFF", 0.06), 1))
        p.setBrush(alpha("#FFFFFF", self._tint))
        p.drawRoundedRect(r, S(10), S(10))


class Glyph(QWidget):
    """A vector icon inside a soft disc: used for designed empty / locked / unavailable states."""

    def __init__(self, kind: str, size: int = 56, parent=None) -> None:
        super().__init__(parent)
        self._kind = kind
        self.setFixedSize(S(size), S(size))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        c = QPointF(self.width() / 2, self.height() / 2)
        rad = self.width() / 2 - 1
        p.setPen(QPen(alpha(ui.accent, 0.35), 1))
        p.setBrush(alpha(ui.accent, 0.08))
        p.drawEllipse(c, rad, rad)
        p.translate(c)
        k = self.width() / 44
        p.scale(k, k)
        draw_icon(p, self._kind, mix(ui.accent, QColor(TEXT), 0.35))


class Sparkline(QWidget):
    def __init__(self, maximum: float = 100.0, height: int = 30, parent=None) -> None:
        super().__init__(parent)
        self._max = maximum
        self._auto = maximum <= 0
        self._data: deque = deque(maxlen=60)
        self.setFixedHeight(S(height))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def push(self, v: float) -> None:
        self._data.append(max(0.0, float(v)))
        self.update()

    def paintEvent(self, _e) -> None:
        if len(self._data) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(AA)
        w, h = self.width(), self.height() - 2
        top = max(self._data) * 1.15 if self._auto else self._max
        top = max(top, 1e-6)
        n = self._data.maxlen
        step = w / (n - 1)
        x0 = w - (len(self._data) - 1) * step
        path = QPainterPath()
        for i, v in enumerate(self._data):
            pt = QPointF(x0 + i * step, 1 + h - min(1.0, v / top) * h)
            path.lineTo(pt) if i else path.moveTo(pt)
        fill = QPainterPath(path)
        fill.lineTo(w, h + 2)
        fill.lineTo(x0, h + 2)
        fill.closeSubpath()
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, alpha(ui.accent, 0.30))
        g.setColorAt(1, alpha(ui.accent, 0.0))
        p.fillPath(fill, g)
        p.setPen(QPen(ui.accent, 1.5))
        p.drawPath(path)


class Gauge(QWidget):
    """270-degree arc gauge with an animated value."""

    def __init__(self, caption: str, unit: str = "%", size: int = 96, parent=None) -> None:
        super().__init__(parent)
        self._caption, self._unit = caption, unit
        self._text = "–"
        self.setFixedSize(S(size), S(size))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._v = Tween(self, 0.0, self.update)

    def set_value(self, fraction: Optional[float], text: str = "") -> None:
        if fraction is None:
            self._text = "–"
            self._v.to(0.0, 300)
        else:
            self._text = text or f"{round(fraction * 100)}"
            self._v.to(max(0.0, min(1.0, fraction)), 450)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        th = S(6)
        r = QRectF(self.rect()).adjusted(th, th, -th, -th)
        pen = QPen(QColor(TRACK), th)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(r, 225 * 16, -270 * 16)
        v = self._v.level
        col = ui.accent if v < 0.75 else mix(QColor(WARN), QColor(DANGER), (v - 0.75) * 4)
        if v > 0.004:
            pen.setColor(col)
            p.setPen(pen)
            p.drawArc(r, 225 * 16, int(-270 * 16 * v))
        p.setPen(QColor(TEXT))
        p.setFont(font(19, QFont.Weight.Bold))
        box = QRectF(0, self.height() * 0.28, self.width(), self.height() * 0.3)
        p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), self._text)
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(9.5, QFont.Weight.DemiBold, 0.6))
        p.drawText(QRectF(0, self.height() * 0.56, self.width(), S(14)), int(Qt.AlignmentFlag.AlignCenter), self._unit)
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(0, self.height() - S(17), self.width(), S(15)), int(Qt.AlignmentFlag.AlignCenter),
                   self._caption)


class ProgressBar(QWidget):
    """4 px track; click or drag to seek when `seekable`."""
    seek = pyqtSignal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(S(12))
        self._fraction = 0.0
        self._px = -1
        self.seekable = False
        self._hover = Tween(self, on_change=self.update)

    def set_fraction(self, fraction: float) -> None:
        fraction = max(0.0, min(1.0, fraction))
        px = int(fraction * max(1, self.width()))
        self._fraction = fraction
        if px != self._px:           # repaint only when the bar visibly moves
            self._px = px
            self.update()

    def enterEvent(self, e) -> None:
        if self.seekable:
            self._hover.to(1.0, 140)

    def leaveEvent(self, e) -> None:
        self._hover.to(0.0, 220)

    def mousePressEvent(self, e) -> None:
        if self.seekable and e.button() == Qt.MouseButton.LeftButton:
            f = max(0.0, min(1.0, e.position().x() / max(1, self.width())))
            self._fraction, self._px = f, -1
            self.update()
            self.seek.emit(f)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        p.setPen(Qt.PenStyle.NoPen)
        th = S(4) + self._hover.level * S(1.5)
        r = QRectF(0, (self.height() - th) / 2, self.width(), th)
        p.setBrush(QColor(TRACK))
        p.drawRoundedRect(r, th / 2, th / 2)
        if self._fraction > 0:
            p.setBrush(ui.accent)
            fw = max(4.0, r.width() * self._fraction)
            p.drawRoundedRect(QRectF(0, r.top(), fw, th), th / 2, th / 2)
            if self._hover.level > 0.02:
                p.setBrush(alpha("#FFFFFF", self._hover.level))
                p.drawEllipse(QPointF(min(fw, r.width() - S(4)), r.center().y()), S(4.5), S(4.5))


class ArtWidget(QWidget):
    """Rounded album cover with a 280 ms cross-fade and a note placeholder. Click = open the player."""
    clicked = pyqtSignal()

    def __init__(self, size: int, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(S(size), S(size))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pixmap: Optional[QPixmap] = None
        self._fade = Tween(self, 1.0, self.update, QEasingCurve.Type.InOutQuad)

    def set_pixmap(self, pixmap: Optional[QPixmap]) -> None:
        if pixmap is None or pixmap.isNull():
            self._pixmap = None
            self._fade.jump(1.0)
            self.update()
            return
        target = int(self.width() * self.devicePixelRatioF())
        self._pixmap = pixmap.scaled(target, target, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                     Qt.TransformationMode.SmoothTransformation)
        self._fade.jump(0.0)
        self._fade.to(1.0, 280)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHints(AA | QPainter.RenderHint.SmoothPixmapTransform)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), S(10), S(10))
        p.setClipPath(clip)
        p.fillRect(self.rect(), QColor("#1C2122"))
        if self._pixmap is None or self._fade.level < 1.0:
            p.save()
            p.translate(self.width() / 2, self.height() / 2)
            k = self.width() / 50
            p.scale(k, k)
            draw_icon(p, "note", QColor(PLACEHOLDER))
            p.restore()
        if self._pixmap is not None:
            pm = self._pixmap
            side = min(pm.width(), pm.height())
            src = QRectF((pm.width() - side) / 2, (pm.height() - side) / 2, side, side)
            p.setOpacity(self._fade.level)
            p.drawPixmap(QRectF(self.rect()), pm, src)
            p.setOpacity(1.0)
        p.setClipping(False)
        p.setPen(QPen(alpha("#FFFFFF", 0.07), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), S(10), S(10))


# --------------------------------------------------------------------------- #
# Scroll area (inertial wheel, thin thumb, fading edges)
# --------------------------------------------------------------------------- #
class _ScrollOverlay(QWidget):
    def __init__(self, area: "ScrollArea") -> None:
        super().__init__(area)
        self._area = area
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        a = self._area
        span = a.max_offset()
        if span <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(AA)
        w, h, fade = self.width(), self.height(), S(18)
        bg = mix(ui.bg_top, ui.bg_bottom, 0.5)
        if a.offset() > 1:
            g = QLinearGradient(0, 0, 0, fade)
            g.setColorAt(0, bg)
            g.setColorAt(1, alpha(bg, 0))
            p.fillRect(QRectF(0, 0, w, fade), g)
        if a.offset() < span - 1:
            g = QLinearGradient(0, h - fade, 0, h)
            g.setColorAt(0, alpha(bg, 0))
            g.setColorAt(1, bg)
            p.fillRect(QRectF(0, h - fade, w, fade), g)
        th = max(S(24), h * h / (h + span))
        y = (h - th) * a.offset() / span
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.22))
        p.drawRoundedRect(QRectF(w - S(3), y, S(3), th), S(1.5), S(1.5))


class ScrollArea(QWidget):
    GUTTER = 8        # the thumb lives in this strip, right of the content

    def __init__(self, content: QWidget, content_h: int, parent=None) -> None:
        super().__init__(parent)
        self.content = content
        content.setParent(self)
        self._content_h = content_h
        self._target = 0.0
        self._pos = Tween(self, 0.0, self._apply)
        self._overlay = _ScrollOverlay(self)

    def offset(self) -> float:
        return self._pos.level

    def max_offset(self) -> float:
        return max(0.0, self._content_h - self.height())

    def _apply(self) -> None:
        self.content.move(0, -int(round(self._pos.level)))
        self._overlay.update()

    def resizeEvent(self, _e) -> None:
        self.content.setGeometry(0, -int(round(self._pos.level)), self.width() - S(self.GUTTER),
                                 max(self._content_h, self.height()))
        self._overlay.setGeometry(self.rect())
        self._overlay.raise_()
        if self._target > self.max_offset():
            self._target = self.max_offset()
            self._pos.jump(self._target)

    def wheelEvent(self, e) -> None:
        if self.max_offset() > 0:
            self._target = max(0.0, min(self.max_offset(), self._target - e.angleDelta().y() / 120 * S(70)))
            self._pos.to(self._target, 280)
        e.accept()


# --------------------------------------------------------------------------- #
# Tab bar: icon tabs, the active one opens into a labelled accent pill
# --------------------------------------------------------------------------- #
class TabBar(QWidget):
    SLOT = 27
    fade = 1.0
    changed = pyqtSignal(str)

    def __init__(self, tabs: list, current: str, parent=None) -> None:
        """tabs: [(key, icon, label, locked)]"""
        super().__init__(parent)
        self._tabs = tabs
        self._current = current
        self._hover_i = -1
        self._full_h = S(30)
        self.setMinimumHeight(1)
        self.setMaximumHeight(self._full_h)
        self.resize(self.width(), self._full_h)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._font = font(11.5, QFont.Weight.DemiBold)
        self._w = [Tween(self, 1.0 if t[0] == current else 0.0, self.update, QEasingCurve.Type.OutBack) for t in tabs]
        self._h = [Tween(self, 0.0, self.update) for _ in tabs]
        from PyQt6.QtGui import QFontMetrics
        fm = QFontMetrics(self._font)
        self._lw = [fm.horizontalAdvance(t[2]) + S(8) for t in tabs]

    def set_current(self, key: str) -> None:
        self._current = key
        for i, t in enumerate(self._tabs):
            self._w[i].to(1.0 if t[0] == key else 0.0, 320)

    def set_locked(self, key: str, locked: bool) -> None:
        self._tabs = [(k, i, l, locked if k == key else lk) for k, i, l, lk in self._tabs]
        self.update()

    def _slot(self) -> float:
        """Icon slot width: shrinks a little when the open label would not fit otherwise."""
        n = len(self._tabs)
        return min(float(S(self.SLOT)), (self.width() - max(self._lw)) / n)

    def _rects(self) -> list:
        n, slot = len(self._tabs), self._slot()
        gap = max(0.0, (self.width() - n * slot - max(self._lw)) / max(1, n - 1))
        out, x = [], 0.0
        for i in range(n):
            w = slot + self._lw[i] * max(0.0, self._w[i].level)
            out.append(QRectF(x, 0, w, self._full_h))
            x += w + gap
        return out

    def _index_at(self, x: float) -> int:
        for i, r in enumerate(self._rects()):
            if r.left() - 2 <= x <= r.right() + 2:
                return i
        return -1

    def mouseMoveEvent(self, e) -> None:
        i = self._index_at(e.position().x())
        if i != self._hover_i:
            if self._hover_i >= 0:
                self._h[self._hover_i].to(0.0, 220)
            self._hover_i = i
            if i >= 0:
                self._h[i].to(1.0, 140)
                self.setToolTip(self._tabs[i][2])

    def leaveEvent(self, _e) -> None:
        if self._hover_i >= 0:
            self._h[self._hover_i].to(0.0, 220)
        self._hover_i = -1

    def mousePressEvent(self, e) -> None:
        i = self._index_at(e.position().x())
        if i >= 0 and self._tabs[i][0] != self._current:
            self.changed.emit(self._tabs[i][0])

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        p.setOpacity(self.fade)
        if self.height() < self._full_h:                    # squashing away
            p.translate(0, self.height() / 2)
            p.scale(1.0, self.height() / self._full_h)
            p.translate(0, -self._full_h / 2)
        slot = self._slot()
        for i, (r, (key, icon, label, locked)) in enumerate(zip(self._rects(), self._tabs)):
            w, h = max(0.0, min(1.0, self._w[i].level)), self._h[i].level
            if w > 0.01 or h > 0.01:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(mix(alpha("#FFFFFF", 0.07 * h), alpha(ui.accent, 0.18), w))
                p.drawRoundedRect(r.adjusted(0, S(1), 0, -S(1)), S(9), S(9))
            fg = mix(mix(QColor(TEXT_DIM), QColor(TEXT), h), ui.accent, w)
            if key == "giveaway":                            # a live giveaway: the tab shines gold
                import time as _t
                pulse = 0.5 + 0.5 * math.sin(_t.monotonic() * 3)
                gold = QColor("#E8C26A")
                p.setPen(QPen(alpha(gold, 0.5 + 0.4 * pulse), S(1.2)))
                p.setBrush(alpha(gold, 0.12 + 0.12 * pulse + 0.15 * w))
                p.drawRoundedRect(r.adjusted(0, S(1), 0, -S(1)), S(9), S(9))
                fg = mix(gold, QColor("#FFFFFF"), 0.25 * pulse)
                if not hasattr(self, "_gold_t"):
                    self._gold_t = QTimer(self)
                    self._gold_t.setInterval(60)
                    self._gold_t.timeout.connect(self.update)
                    self._gold_t.start()
            p.save()
            p.translate(r.left() + slot / 2, r.center().y())
            k = S(15.5) / 20
            p.scale(k, k)
            draw_icon(p, icon, fg, max(h, w))
            if locked:
                p.translate(8.5, -7.5)
                p.scale(0.42, 0.42)
                draw_icon(p, "lock", QColor(TEXT_FAINT))
            p.restore()
            if w > 0.05:
                p.save()
                p.setClipRect(r)
                p.setOpacity(w)
                p.setFont(self._font)
                p.setPen(mix(ui.accent, QColor(TEXT), 0.45))
                p.drawText(QRectF(r.left() + slot - S(3), 0, self._lw[i], self._full_h),
                           int(Qt.AlignmentFlag.AlignVCenter), label)
                p.restore()


# --------------------------------------------------------------------------- #
# Layout helpers
# --------------------------------------------------------------------------- #
def snapshot(widget: QWidget) -> QPixmap:
    """Render a widget and its children onto a transparent pixmap (works while it is hidden)."""
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QRegion
    dpr = widget.devicePixelRatioF()
    pm = QPixmap(max(1, int(widget.width() * dpr)), max(1, int(widget.height() * dpr)))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    widget.render(pm, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    return pm


def vbox(parent=None, spacing: float = 8, margins=(0, 0, 0, 0)) -> QVBoxLayout:
    lay = QVBoxLayout(parent) if parent is not None else QVBoxLayout()
    lay.setContentsMargins(*[S(m) for m in margins])
    lay.setSpacing(S(spacing))
    return lay


def hbox(parent=None, spacing: float = 8, margins=(0, 0, 0, 0)) -> QHBoxLayout:
    lay = QHBoxLayout(parent) if parent is not None else QHBoxLayout()
    lay.setContentsMargins(*[S(m) for m in margins])
    lay.setSpacing(S(spacing))
    return lay


def heading(text: str) -> Label:
    return Label(text.upper(), 10, TEXT_FAINT, weight=QFont.Weight.Bold)


def row(label: str, control: QWidget, sub: str = "", height: int = 30) -> QWidget:
    """Label on the left (optional dim sub-line), control on the right."""
    w = QWidget()
    w.setFixedHeight(S(height + (12 if sub else 0)))
    lay = hbox(w, 10)
    if sub:
        col = vbox(spacing=0)
        col.addStretch(1)
        col.addWidget(Label(label, 12.5))
        col.addWidget(Label(sub, 10.5, TEXT_FAINT))
        col.addStretch(1)
        lay.addLayout(col, 1)
    else:
        lay.addWidget(Label(label, 12.5), 1)
    lay.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
    return w


class SliderRow(QWidget):
    """Label + slider + live value. Double-click the slider to reset."""
    changed = pyqtSignal(float)
    released = pyqtSignal(float)

    def __init__(self, label: str, lo: float, hi: float, value: float, step: float = 1.0,
                 default: Optional[float] = None, fmt: Callable[[float], str] = lambda v: f"{v:g}",
                 label_w: int = 96, marks=None, parent=None) -> None:
        super().__init__(parent)
        self._fmt = fmt
        self.setFixedHeight(S(26))
        lay = hbox(self, 6)
        name = Label(label, 12)
        name.setFixedWidth(max(S(label_w), name.text_width() + S(8)))
        self.name = name
        self.slider = Slider(lo, hi, value, step, default, marks=marks)
        self._val = Label(fmt(self.slider.value()), 11, TEXT_DIM, align=Qt.AlignmentFlag.AlignRight)
        self._val.setFixedWidth(S(42))
        lay.addWidget(name)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self._val)
        self.slider.changed.connect(self._on)
        self.slider.released.connect(self.released)

    def _on(self, v: float) -> None:
        self._val.set_text(self._fmt(v))
        self.changed.emit(v)

    def value(self) -> float:
        return self.slider.value()

    def set_value(self, v: float) -> None:
        self.slider.set_value(v)
        self._val.set_text(self._fmt(self.slider.value()))

    def set_parked(self, on: bool) -> None:
        """A plain colour is picked instead: the knob rests off the line and the value is hidden."""
        self.slider.parked = on
        self._val.setVisible(True)
        self._val.set_color(QColor(0, 0, 0, 0) if on else QColor(TEXT_DIM))
        self.slider.update()


def notice(icon: str, title: str, text: str, width: int, button: Optional[QWidget] = None) -> QWidget:
    """Designed explained state: used instead of ever showing a dead control."""
    panel = Panel()
    lay = hbox(panel, 10, (10, 9, 10, 9))
    lay.addWidget(Glyph(icon, 34), 0, Qt.AlignmentFlag.AlignTop)
    col = vbox(spacing=2)
    col.addWidget(Label(title, 12, bold=True))
    col.addWidget(Label(text, 10.5, TEXT_DIM, wrap_w=width - S(34 + 10 + 20)))
    if button is not None:
        col.addSpacing(S(4))
        col.addWidget(button)
    lay.addLayout(col, 1)
    return panel


def align_slider_rows(page: QWidget) -> None:
    """Give every slider row on a page the same label width: wide enough for the longest label,
    so no label is cut short and all sliders still line up."""
    rows = page.findChildren(SliderRow)
    if rows:
        width = min(S(170), max(r.name.width() for r in rows))
        for r in rows:
            r.name.setFixedWidth(width)


class KeyChip(QWidget):
    """A keyboard key drawn as a small rounded cap, e.g. Ctrl + F1."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text
        self._font = font(10.5, QFont.Weight.Bold)
        from PyQt6.QtGui import QFontMetrics
        self.setFixedSize(QFontMetrics(self._font).horizontalAdvance(text) + S(14), S(20))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -1.5)
        p.setPen(QPen(alpha("#FFFFFF", 0.22), 1))
        p.setBrush(alpha("#FFFFFF", 0.07))
        p.drawRoundedRect(r, S(5), S(5))
        p.setPen(QColor(TEXT))
        p.setFont(self._font)
        p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), self._text)


def present(widget, ctx, keys: bool = False) -> bool:
    """Show a small screen inside the open menu (never a separate window over a game). False when the menu is
    closed (the start screen, say): the caller then shows it as a small window."""
    win_ = getattr(ctx, "window", None)
    if win_ is None or not getattr(win_, "expanded", False) or not hasattr(win_, "embed"):
        return False
    widget._embedded = True
    widget.setWindowFlags(Qt.WindowType.Widget)
    widget.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
    win_.embed(widget, keys)
    return True


def close_embedded(widget) -> bool:
    """close() of a small screen shown inside the menu. True when it was."""
    if not getattr(widget, "_embedded", False):
        return False
    widget._embedded = False
    end = getattr(widget, "on_closed", None)
    if end:
        end()
    widget.ctx.window.unembed(widget)
    widget.deleteLater()
    return True
