# -*- coding: utf-8 -*-
"""Themes, run timer, shortcuts, app launcher, Rocket League folder, crosshair library, session stats."""
from __future__ import annotations

import base64
import ctypes
import json
import logging
import math
import os
import time
from ctypes import wintypes
from pathlib import Path

from PyQt6.QtCore import QAbstractNativeEventFilter, QFileInfo, QObject, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPen
from PyQt6.QtWidgets import QFileIconProvider, QWidget

from . import win
from .core import CROSSHAIR, S, TEXT, alpha, font, mix, ui
from .engines import OVERLAY_FLAGS

log = logging.getLogger("rubenium.extras")

# --------------------------------------------------------------------------- #
# Themes: background designs, sparkles and glow, unlocked by hours of use.
# They never change the colour (the music / your accent does), so they always show.
# --------------------------------------------------------------------------- #
def _theme(ident, name, hours, glow=0, stars=0, links=0, comets=0, aurora=False, gold=0.0, sparkles=0,
           halo=1.0, edge=""):
    return dict(id=ident, name=name, hours=hours, layers=bool(glow or stars), glow_n=glow, stars=stars, links=links,
                comets=comets, aurora=aurora, gold=gold, sparkles=sparkles, glow=halo, edge=edge)


# One night sky that fills up as the hours go by: first a glow, then stars, then lines between them, comets, a
# second light, and from 100 h more and more gold. Every theme keeps everything the one before it had.
THEMES = [
    _theme("clean", "Clean", 0),
    _theme("glow", "Glow", 2, glow=1),
    _theme("stars", "First Stars", 12, glow=1, stars=14),
    _theme("starfield", "Starfield", 20, glow=1, stars=34, sparkles=3),
    _theme("aurora", "Aurora", 55, glow=2, stars=56, links=9, comets=3, aurora=True, sparkles=6, halo=1.2),
    _theme("nova", "Nova", 75, glow=2, stars=60, links=10, comets=4, aurora=True, gold=0.35, sparkles=7, halo=1.25,
           edge="shine"),
    _theme("royal", "Royal", 150, glow=3, stars=68, links=12, comets=5, aurora=True, gold=0.85, sparkles=11,
           halo=1.4, edge="goldshine"),
    _theme("legend", "Legend", 200, glow=3, stars=76, links=14, comets=6, aurora=True, gold=1.0, sparkles=14,
           halo=1.5, edge="legend"),
]
# Small extras that also unlock with time: the look of the R and of the song ring on the ball.
R_STYLES = [dict(id="classic", name="Classic", hours=0), dict(id="whitegold", name="White Gold", hours=30),
            dict(id="gold", name="Gold", hours=100)]
RING_STYLES = [dict(id="line", name="Line", hours=0), dict(id="whitegold", name="White Gold", hours=40),
               dict(id="gold", name="Gold", hours=125)]
RETIRED_STYLES = {"echo": "classic", "comet": "line", "outline": "classic", "neon": "classic", "dots": "line"}
# what the server calls each progression unlock (shown on your profile)
PROG_IDS = {"theme": {"clean": "prog:theme:1", "glow": "prog:theme:2", "stars": "prog:theme:3", "starfield": "prog:theme:4",
                      "aurora": "prog:theme:5", "nova": "prog:theme:6", "royal": "prog:theme:7", "legend": "prog:theme:8"},
            "ball_style": {"classic": "prog:ball:0", "whitegold": "prog:ball:2", "gold": "prog:ball:3"},
            "ring_style": {"line": "prog:ring:0", "whitegold": "prog:ring:2", "gold": "prog:ring:3"}}
SECOND_COLOUR_HOURS = 24


def unlocked_style(styles: list, ident: str, hours: float) -> str:
    """The style to use: the chosen one if it is unlocked, otherwise the first (free) one."""
    for st in styles:
        if st["id"] == ident and hours >= st["hours"]:
            return ident
    return styles[0]["id"]


def paint_r(p: QPainter, box: QRectF, d: float, style: str, accent: QColor, now: float = 0.0) -> None:
    """The R of the ball, centred in `box` for a ball of diameter `d`, in one of R_STYLES."""
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QFont, QFontMetricsF, QLinearGradient, QPainterPath
    from .core import TEXT, font
    if style.startswith("ball:"):                        # a ball bought in the shop
        from .cosmetics import paint_shop_ball
        return paint_shop_ball(p, box, d, style, now)
    f = font(20, QFont.Weight.ExtraBold)
    f.setPixelSize(max(8, int(d * 0.46)))
    p.setFont(f)
    centre = int(Qt.AlignmentFlag.AlignCenter)
    if style == "classic":
        p.setPen(alpha(accent, 0.55))
        p.drawText(box.translated(0, d * 0.022), centre, "R")
        p.setPen(QColor(TEXT))
        p.drawText(box, centre, "R")
        return
    fm = QFontMetricsF(f)
    tb = fm.tightBoundingRect("R")
    path = QPainterPath()
    path.addText(QPointF(box.center().x() - tb.width() / 2 - tb.left(), box.center().y() - tb.height() / 2 - tb.top()),
                 f, "R")
    p.save()
    if style == "outline":
        pen = QPen(QColor(TEXT), max(1.2, d * 0.028))
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(alpha(accent, 0.18))
        p.drawPath(path)
    elif style == "echo":                              # white outline with two fading copies behind it
        width = max(1.2, d * 0.026)
        step = d * 0.034
        p.setBrush(Qt.BrushStyle.NoBrush)
        for n, a in ((2, 0.22), (1, 0.45)):
            pen = QPen(alpha(TEXT, a), width)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawPath(path.translated(step * n, step * n))
        pen = QPen(QColor(TEXT), width)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(QColor("#0A0D0E"))
        p.drawPath(path.translated(-step * 0.5, -step * 0.5))
    elif style == "whitegold":                         # a solid white R with a thin gold edge
        g = QLinearGradient(box.topLeft(), box.bottomRight())
        g.setColorAt(0.3, QColor("#E8C26A"))
        g.setColorAt(0.7, QColor("#B8862B"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawPath(path.translated(0, d * 0.02))
        pen = QPen(g, max(1.0, d * 0.02))
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(QColor("#FFFFFF"))
        p.drawPath(path)
    elif style == "neon":                              # a glowing tube in your colour with a white-hot core
        for w, a in ((d * 0.10, 0.10), (d * 0.065, 0.20), (d * 0.04, 0.45)):
            pen = QPen(alpha(accent, a), w)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        pen = QPen(mix(accent, QColor("#FFFFFF"), 0.75), max(1.0, d * 0.018))
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(alpha(accent, 0.10))
        p.drawPath(path)
    else:                                               # gold
        g = QLinearGradient(box.topLeft(), box.bottomRight())
        g.setColorAt(0.25, QColor("#FFF1C2"))
        g.setColorAt(0.5, QColor(GOLD))
        g.setColorAt(0.75, QColor("#B8862B"))
        p.setPen(QPen(alpha("#000000", 0.35), 1))
        p.setBrush(g)
        p.drawPath(path)
    p.restore()


def ring_pen(style: str, color: QColor, width: float) -> QPen:
    """Pen for the simple ring styles (line, dashes, dots)."""
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    if style == "dash":
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setDashPattern([2.6, 1.6])
    elif style == "dots":
        pen.setDashPattern([0.1, 2.2])
    return pen


def paint_ring(p: QPainter, ring: QRectF, style: str, frac: float, accent: QColor, width: float) -> None:
    """The song-progress ring of the ball, in one of RING_STYLES (all follow the accent colour)."""
    import math
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QConicalGradient
    frac = max(0.0, min(1.0, frac))
    if style.startswith("line:"):                        # a line bought in the shop
        from .cosmetics import paint_shop_ring
        return paint_shop_ring(p, ring, style, frac, width, time.monotonic())
    p.setBrush(Qt.BrushStyle.NoBrush)
    simple = style if style in ("line", "dash", "dots") else "line"
    p.setPen(ring_pen(simple, alpha("#FFFFFF", 0.10), width))
    p.drawEllipse(ring)
    if frac <= 0.0:
        return
    span = int(-360 * 16 * frac)
    head_ang = math.radians(90 - 360 * frac)
    head = QPointF(ring.center().x() + ring.width() / 2 * math.cos(head_ang),
                   ring.center().y() - ring.height() / 2 * math.sin(head_ang))
    if style in ("line", "dash", "dots"):
        p.setPen(ring_pen(style, accent, width))
        p.drawArc(ring, 90 * 16, span)
        return
    if style == "whitegold":                             # a white band edged in gold, with a pearl head
        pen = QPen(QColor("#C9A04A"), width * 1.45)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(ring, 90 * 16, span)
        pen = QPen(QColor("#FFFFFF"), width * 0.95)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(ring, 90 * 16, span)
        p.setPen(QPen(QColor("#C9A04A"), max(1.0, width * 0.5)))
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(head, width * 1.35, width * 1.35)
        return
    if style == "neon":                                  # glowing tube with a white-hot core and a bright head
        for w, a in ((width * 3.6, 0.10), (width * 2.3, 0.22)):
            pen = QPen(alpha(accent, a), w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(ring, 90 * 16, span)
        pen = QPen(mix(accent, QColor("#FFFFFF"), 0.6), width * 0.9)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(ring, 90 * 16, span)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha(accent, 0.45))
        p.drawEllipse(head, width * 2.0, width * 2.0)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(head, width * 0.85, width * 0.85)
        return
    # comet / gold: the arc fades in from its start and ends in a bright head
    gold = style == "gold"
    col = QColor(GOLD) if gold else accent
    g = QConicalGradient(ring.center(), 90.0)        # runs anticlockwise from the top; the arc covers 1-frac .. 1
    faded = alpha(QColor("#8A6A22") if gold else col, 0.35 if gold else 0.04)
    g.setColorAt(0.0, faded)
    g.setColorAt(max(0.001, min(0.998, 1.0 - frac)), alpha(QColor("#FFF1C2") if gold else col, 1.0))
    g.setColorAt(1.0, faded)
    if gold:                                             # warm light under the line
        for w, a in ((width * 3.4, 0.10), (width * 2.1, 0.18)):
            pen = QPen(alpha(col, a), w)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(ring, 90 * 16, span)
    pen = QPen(g, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawArc(ring, 90 * 16, span)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(alpha(col, 0.35))
    p.drawEllipse(head, width * 1.6, width * 1.6)
    if gold:                                             # the head is a small four-point star
        from PyQt6.QtGui import QPainterPath
        r1, r2 = width * 2.3, width * 0.6
        star = QPainterPath()
        for n in range(8):
            ang = math.radians(45 * n)
            rr = r1 if n % 2 == 0 else r2
            pt = QPointF(head.x() + rr * math.cos(ang), head.y() + rr * math.sin(ang))
            star.lineTo(pt) if n else star.moveTo(pt)
        star.closeSubpath()
        p.setBrush(QColor("#FFF6D8"))
        p.drawPath(star)
    else:
        p.setBrush(mix(accent, QColor("#FFFFFF"), 0.7))
        p.drawEllipse(head, width * 0.75, width * 0.75)


GOLD = "#E8C26A"
_pattern_cache: dict = {}


def theme_by_id(ident: str) -> dict:
    if ident.startswith("theme:"):                       # a theme bought in the shop
        from .cosmetics import shop_theme
        return shop_theme(ident) or THEMES[0]
    return next((t for t in THEMES if t["id"] == ident), THEMES[0])


def theme_colour(theme: dict, accent: QColor) -> QColor:
    """The colour a theme draws with: your colour, turning to gold in the last themes."""
    return mix(accent, QColor(GOLD), theme.get("gold", 0.0))


def _sky(theme: dict, w: float, h: float, unit: float) -> list:
    """Star positions. The same sky for every theme: a richer theme simply shows more of it."""
    import random
    rnd = random.Random(2008)
    stars = [(rnd.uniform(0.03, 0.97), rnd.uniform(0.05, 0.92), rnd.uniform(0.55, 1.35), rnd.uniform(0.35, 0.95))
             for _ in range(80)]
    return [(x * w, y * h, r * unit, a) for x, y, r, a in stars[:theme.get("stars", 0)]]


def _draw_theme(p: QPainter, theme: dict, w: float, h: float, accent: QColor, second, unit: float) -> None:
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QLinearGradient, QRadialGradient
    col = theme_colour(theme, accent)
    gold = theme.get("gold", 0.0)
    white = QColor("#FFFFFF")
    if second is not None:
        other = mix(second, QColor(GOLD), gold * 0.5)
    else:
        shifted = QColor.fromHsvF((max(0.0, accent.hsvHueF()) + 0.14) % 1.0, max(0.35, accent.hsvSaturationF()),
                                  max(0.6, accent.valueF()))
        other = mix(shifted, QColor("#FFD98A"), gold)
    p.setPen(Qt.PenStyle.NoPen)
    n = theme.get("glow_n", 0)
    if n:                                                # light from the top-left corner
        g = QRadialGradient(QPointF(w * 0.16, -h * 0.05), w * (0.55 + 0.1 * n))
        g.setColorAt(0, alpha(col, 0.12 + 0.05 * n))
        g.setColorAt(1, alpha(col, 0.0))
        p.setBrush(g)
        p.drawRect(QRectF(0, 0, w, h))
    if theme.get("aurora") or second is not None:        # a second light from the other corner
        g = QRadialGradient(QPointF(w * 0.86, -h * 0.12), w * 0.6)
        g.setColorAt(0, alpha(other, 0.24 if theme.get("aurora") else 0.16))
        g.setColorAt(1, alpha(other, 0.0))
        p.setBrush(g)
        p.drawRect(QRectF(0, 0, w, h))
    sky = _sky(theme, w, h, unit)
    links = theme.get("links", 0)
    if links and len(sky) > 3:                           # lines between the brightest stars
        bright = sorted(sorted(sky, key=lambda s: -s[3])[:links + 4], key=lambda s: s[0])
        pen = QPen(alpha(mix(col, white, 0.25), 0.26), max(1.0, 0.8 * unit))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        drawn = 0
        for a, b in zip(bright, bright[1:]):
            if drawn >= links:
                break
            if math.hypot(b[0] - a[0], b[1] - a[1]) < w * 0.34:
                p.drawLine(QPointF(a[0], a[1]), QPointF(b[0], b[1]))
                drawn += 1
        p.setPen(Qt.PenStyle.NoPen)
    for x, y, r, a in sky:
        p.setBrush(alpha(mix(white, col, 0.25 + 0.55 * gold), a))
        p.drawEllipse(QPointF(x, y), r, r)
        if r > 1.15 * unit:                              # the biggest ones get a soft halo
            p.setBrush(alpha(col, 0.16))
            p.drawEllipse(QPointF(x, y), r * 2.6, r * 2.6)
    comets = theme.get("comets", 0)
    if comets:
        import random
        rnd = random.Random(5)
        for _ in range(comets):
            x, y = rnd.uniform(0.08, 0.80) * w, rnd.uniform(0.12, 0.62) * h
            length = rnd.uniform(26, 54) * unit
            tail = QPointF(x + length, y - length * 0.42)
            g = QLinearGradient(QPointF(x, y), tail)
            g.setColorAt(0.0, alpha(mix(col, white, 0.5), 0.6))
            g.setColorAt(1.0, alpha(col, 0.0))
            pen = QPen(g, 1.4 * unit)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(x, y), tail)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(white, 0.8))
            p.drawEllipse(QPointF(x, y), 1.3 * unit, 1.3 * unit)
    if gold >= 0.6:                                      # fine gold dust along the top
        import random
        rnd = random.Random(31)
        for _ in range(int(40 * gold)):
            p.setBrush(alpha(GOLD, rnd.uniform(0.15, 0.5)))
            r = rnd.uniform(0.35, 0.8) * unit
            p.drawEllipse(QPointF(rnd.uniform(0, w), rnd.uniform(0, h * 0.5) ** 1.0), r, r)


def theme_pattern(theme: dict, w: int, h: int, accent: QColor, dpr: float, unit: float, band: float = 0.0):
    """Cached pixmap of a theme's background, faded out below `band` pixels (None when there is nothing)."""
    from PyQt6.QtGui import QLinearGradient, QPixmap
    second = ui.accent2
    if (not theme["layers"] and second is None) or w < 2 or h < 2:
        return None
    band = band or h
    key = (theme["id"], w, h, accent.rgb(), second.rgb() if second is not None else 0, round(dpr * 100),
           round(unit * 100), round(band))
    pm = _pattern_cache.get(key)
    if pm is None:
        if len(_pattern_cache) > 40:
            _pattern_cache.clear()
        pm = QPixmap(int(w * dpr), int(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        _draw_theme(p, theme, w, min(h, band), accent, second, unit)
        fade = QLinearGradient(0, 0, 0, band)                 # strongest under the header, gone below it
        fade.setColorAt(0.0, QColor(0, 0, 0, 255))
        fade.setColorAt(0.55, QColor(0, 0, 0, 150))
        fade.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        p.fillRect(QRectF(0, 0, w, h), fade)
        p.end()
        _pattern_cache[key] = pm
    return pm


def theme_sparkles(theme: dict, w: float, h: float, band: float = 0.0) -> list:
    """[(x, y, size, phase, speed, gold)] twinkling stars, stable for a theme; kept inside the header band."""
    import random
    n = theme.get("sparkles", 0)
    if not n:
        return []
    band = min(h, band or h)
    rnd = random.Random(77)                                    # the same ones in every theme, just more of them
    return [(rnd.uniform(0.06, 0.94) * w, rnd.uniform(0.10, 0.85) * band, rnd.uniform(1.4, 2.6),
             rnd.uniform(0, 6.28), rnd.uniform(0.6, 1.2), theme.get("gold", 0.0)) for _ in range(n)]


def paint_sparkles(p: QPainter, sparks: list, ox: float, oy: float, accent: QColor, now: float, unit: float) -> None:
    from PyQt6.QtCore import QPointF
    white = QColor("#FFFFFF")
    for x, y, size, phase, speed, gold in sparks:
        b = max(0.0, math.sin(now * speed + phase)) ** 3
        if b < 0.03:
            continue
        col = mix(accent, QColor(GOLD), gold)
        r = size * unit * (0.6 + 0.4 * b)
        c = QPointF(ox + x, oy + y)
        pen = QPen(alpha(mix(col, white, 0.55 - 0.3 * gold), 0.6 * b), max(1.0, 0.8 * unit))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(c.x() - r, c.y()), QPointF(c.x() + r, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - r), QPointF(c.x(), c.y() + r))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha(white, 0.7 * b))
        p.drawEllipse(c, 0.8 * unit, 0.8 * unit)


def paint_theme_edge(p: QPainter, theme: dict, shape: QRectF, radius: float, level: float, halo: bool,
                     now: float) -> None:
    """Card outline: your colour (two colours if a second one is set), then a travelling light, then gold."""
    from PyQt6.QtGui import QConicalGradient, QLinearGradient
    p.setBrush(Qt.BrushStyle.NoBrush)
    a = (80 + 110 * level) / 255 if halo else 0.35
    r = shape.adjusted(0.6, 0.6, -0.6, -0.6)
    style = theme.get("edge", "")
    golden = style in ("gold", "goldshine", "legend")
    if golden:
        base = QLinearGradient(shape.topLeft(), shape.bottomRight())
        base.setColorAt(0.0, alpha("#FFF1C2", min(1.0, a + 0.2)))
        base.setColorAt(0.5, alpha(GOLD, min(1.0, a + 0.15)))
        base.setColorAt(1.0, alpha("#B8862B", min(1.0, a + 0.15)))
        p.setPen(QPen(base, 1.3))
    elif ui.accent2 is not None:
        base = QLinearGradient(shape.topLeft(), shape.bottomRight())
        base.setColorAt(0.0, alpha(ui.accent, a))
        base.setColorAt(1.0, alpha(ui.accent2, a))
        p.setPen(QPen(base, 1.2))
    else:
        p.setPen(QPen(alpha(ui.accent, a), 1.2))
    p.drawRoundedRect(r, radius, radius)
    if style == "legend":                                # a second, fine line just inside
        inner = shape.adjusted(3.4, 3.4, -3.4, -3.4)
        p.setPen(QPen(alpha(GOLD, min(1.0, a * 0.55)), 1.0))
        p.drawRoundedRect(inner, max(0.0, radius - 3.0), max(0.0, radius - 3.0))
    if style in ("shine", "goldshine", "legend"):        # a light travelling around the outline
        tint = QColor("#FFF6D8") if golden else mix(ui.accent, QColor("#FFFFFF"), 0.6)
        for offset in ((0.0, 0.5) if style == "legend" else (0.0,)):
            g = QConicalGradient(shape.center(), (now * 40.0 + offset * 360.0) % 360.0)
            g.setColorAt(0.0, alpha("#FFFFFF", 0.0))
            g.setColorAt(0.04, alpha(tint, min(1.0, a + 0.3)))
            g.setColorAt(0.09, alpha("#FFFFFF", 0.0))
            g.setColorAt(1.0, alpha("#FFFFFF", 0.0))
            p.setPen(QPen(g, 1.7))
            p.drawRoundedRect(r, radius, radius)


# --------------------------------------------------------------------------- #
# Run timer
# --------------------------------------------------------------------------- #
def run_clock(seconds: float) -> str:
    seconds = max(0.0, seconds)
    cs = int(seconds * 100) % 100
    s = int(seconds)
    if s >= 3600:
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}.{cs:02d}"
    return f"{s // 60}:{s % 60:02d}.{cs:02d}"


class TimerEngine(QObject):
    changed = pyqtSignal()

    def __init__(self, cfg) -> None:
        super().__init__()
        self.cfg = cfg
        self.state = "idle"            # idle | running | paused
        self._base = 0.0
        self._t0 = 0.0
        self.splits: list = []

    def elapsed(self) -> float:
        return self._base + (time.monotonic() - self._t0 if self.state == "running" else 0.0)

    def start_split(self) -> None:
        if self.state == "idle":
            self._base, self._t0, self.splits, self.state = 0.0, time.monotonic(), [], "running"
        elif self.state == "paused":
            self._t0, self.state = time.monotonic(), "running"
        else:
            self.splits.append(self.elapsed())
        self.changed.emit()

    def pause(self) -> None:
        if self.state == "running":
            self._base, self.state = self.elapsed(), "paused"
        elif self.state == "paused":
            self._t0, self.state = time.monotonic(), "running"
        self.changed.emit()

    def finish(self) -> None:
        """Stop the run and keep it as the best time if it is faster."""
        if self.state == "idle":
            return
        total = self.elapsed()
        self._base, self.state = total, "paused"
        best = self.cfg["timer"]["best"]
        if total > 0.5 and (best <= 0 or total < best):
            self.cfg["timer"]["best"] = total
            self.cfg.save()
        self.changed.emit()

    def reset(self) -> None:
        self.state, self._base, self.splits = "idle", 0.0, []
        self.changed.emit()


class TimerOverlay(QWidget):
    """Click-through timer at the top of the screen."""

    def __init__(self, cfg, engine: TimerEngine) -> None:
        super().__init__()
        self.cfg, self.engine = cfg, engine
        self.setWindowFlags(OVERLAY_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._tick = QTimer(self)
        self._tick.setInterval(40)
        self._tick.timeout.connect(self.update)
        engine.changed.connect(self._sync)

    def refresh(self) -> None:
        if self.cfg["timer"]["overlay"]:
            w, h = S(150), S(38)
            g = QGuiApplication.primaryScreen().geometry()
            self.setGeometry(g.center().x() - w // 2, g.top() + S(10), w, h)
            self.show()
            win.make_overlay(int(self.winId()))
        else:
            self.hide()
        self._sync()

    def _sync(self) -> None:
        if self.isVisible() and self.engine.state == "running":
            self._tick.start()
        else:
            self._tick.stop()
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha(ui.accent, 0.5), 1))
        p.setBrush(QColor(10, 14, 15, 210))
        p.drawRoundedRect(r, S(9), S(9))
        f = font(19, QFont.Weight.Bold)
        f.setStyleHint(QFont.StyleHint.Monospace)
        p.setFont(f)
        p.setPen(QColor(TEXT) if self.engine.state != "paused" else alpha(TEXT, 0.6))
        p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), run_clock(self.engine.elapsed()))


# --------------------------------------------------------------------------- #
# Keyboard shortcuts (RegisterHotKey: no hooks)
# --------------------------------------------------------------------------- #
class _KeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback) -> None:
        super().__init__()
        self._cb = callback

    def nativeEventFilter(self, event_type, message):
        try:
            if bytes(event_type) == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0312:       # WM_HOTKEY
                    self._cb(int(msg.wParam))
                    return True, 0
        except Exception:  # noqa: BLE001
            pass
        return False, 0


class Hotkeys(QObject):
    """Fixed keys. Ctrl+Alt+Shift+R: normal screen colours. Ctrl+F1 / F2 / F3: run timer."""
    triggered = pyqtSignal(str)
    KEYS = {1: ("panic", 0x2 | 0x1 | 0x4, 0x52),          # Ctrl+Alt+Shift+R
            2: ("timer_split", 0x2, 0x70), 3: ("timer_pause", 0x2, 0x71), 4: ("timer_reset", 0x2, 0x72)}

    def __init__(self, app) -> None:
        super().__init__()
        self._last = (0, 0.0)
        self._on: set = set()
        self._filter = _KeyFilter(self._hit)
        app.installNativeEventFilter(self._filter)

    def _hit(self, ident: int) -> None:
        now = time.monotonic()
        if self._last[0] == ident and now - self._last[1] < 0.12:
            return                                   # Qt can deliver the same message twice
        self._last = (ident, now)
        if ident in self.KEYS:
            self.triggered.emit(self.KEYS[ident][0])

    def apply(self, timer_keys: bool) -> None:
        if not win.IS_WIN:
            return
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        for ident, (name, mods, vk) in self.KEYS.items():
            want = name == "panic" or timer_keys
            if want and ident not in self._on:
                if user32.RegisterHotKey(None, ident, mods | 0x4000, vk):
                    self._on.add(ident)
            elif not want and ident in self._on:
                user32.UnregisterHotKey(None, ident)
                self._on.discard(ident)

    def close(self) -> None:
        if win.IS_WIN:
            for ident in list(self._on):
                ctypes.windll.user32.UnregisterHotKey(None, ident)  # type: ignore[attr-defined]
        self._on.clear()


# --------------------------------------------------------------------------- #
# Launcher: find installed apps from the Start menu and the desktop
# --------------------------------------------------------------------------- #
APP_WORDS = ["steam", "epic games", "rocket league", "discord", "spotify", "obs", "riot", "valorant",
             "counter-strike", "fortnite", "battle.net", "minecraft", "ea app", "ubisoft", "gog galaxy", "medal",
             "overwolf", "bakkesmod", "nvidia", "afterburner", "twitch", "streamlabs", "chrome", "firefox",
             "edge", "brave", "opera", "league of legends", "roblox", "geforce", "teamspeak", "telegram",
             "whatsapp", "apex", "overwatch", "genshin", "xbox", "playnite", "parsec", "curseforge", "lunar client",
             "blizzard", "rockstar", "grand theft auto", "call of duty", "warzone", "rainbow six", "pubg", "dota",
             "elden ring", "hoyoplay", "honkai", "wuthering", "zenless", "marvel rivals", "the finals", "deadlock",
             "fall guys", "trackmania", "osu!", "faceit", "esea", "g hub", "razer", "steelseries", "icue",
             "wootility", "msi center", "armoury crate", "voicemeeter", "elgato", "stream deck", "nvidia app",
             "amd software", "itch", "heroic", "prism launcher", "modrinth", "vlc", "apple music", "deezer", "tidal",
             "amazon games", "ea sports", "fc 2", "nba 2k", "f1 2", "forza", "halo", "destiny", "warframe",
             "path of exile", "lost ark", "new world", "rust", "dead by daylight", "sea of thieves", "gta",
             "geometry dash", "terraria", "among us", "brawlhalla", "rocketleague", "obsidian", "notion"]
APP_SKIP = ["uninstall", "désinstall", "help", "readme", "manual", "documentation", "website", "support",
            "license", "release notes", "crash", "repair", "setup", "installer", "updater", "diagnos"]
GAME_DIRS = ["steamapps\\common", "epic games", "riot games", "\\games\\", "ubisoft game launcher", "ea games"]
PROTECTED = {"explorer.exe", "python.exe", "pythonw.exe", "rubenium.exe", "svchost.exe", "csrss.exe",
             "winlogon.exe", "dwm.exe", "system", "lsass.exe", "services.exe"}


def _start_folders() -> list:
    out = []
    for env, tail in (("APPDATA", r"Microsoft\Windows\Start Menu\Programs"),
                      ("PROGRAMDATA", r"Microsoft\Windows\Start Menu\Programs"),
                      ("USERPROFILE", "Desktop"), ("PUBLIC", "Desktop")):
        base = os.environ.get(env)
        if base:
            out.append(Path(base) / tail)
    out.append(win.documents_dir().parent / "Desktop")        # OneDrive-redirected desktop
    return out


STORE_SKIP = ("steamworks", "redistributable", "proton", "steam linux runtime", "directx", "vc redist",
              "dedicated server", "sdk", "soundtrack", "benchmark")


def _main_exe(folder: str) -> str:
    """The game's own .exe in its folder (the largest one at the top, else in Binaries/Win64)."""
    best, size = "", 0
    for sub in ("", os.path.join("Binaries", "Win64"), "bin", "Game"):
        try:
            with os.scandir(os.path.join(folder, sub)) as it:
                for e in it:
                    name = e.name.lower()
                    if e.is_file() and name.endswith(".exe") and not any(w in name for w in
                                                                          ("crash", "unins", "setup", "redist",
                                                                           "launcher_helper", "report", "eac")):
                        st = e.stat().st_size
                        if st > size:
                            best, size = e.path, st
        except OSError:
            continue
        if best:
            break
    return best


def _store_games() -> list:
    """Games installed through Steam and Epic, even without a Start menu or desktop shortcut."""
    out = []
    import re
    for lib in _steam_roots():                            # Steam: one appmanifest per installed game
        apps = Path(lib) / "steamapps"
        try:
            manifests = list(apps.glob("appmanifest_*.acf"))
        except OSError:
            continue
        for acf in manifests:
            try:
                text = acf.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            got = {k: v for k, v in re.findall(r'"(appid|name|installdir)"\s+"([^"]*)"', text)}
            name = got.get("name", "").strip()
            if not name or not got.get("appid") or any(w in name.lower() for w in STORE_SKIP):
                continue
            folder = str(apps / "common" / got.get("installdir", ""))
            out.append({"name": name, "path": f"steam://rungameid/{got['appid']}", "exe_path": _main_exe(folder)})
    program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    try:                                                  # Epic: one manifest per installed game
        for item in (Path(program_data) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests").glob("*.item"):
            try:
                data = json.loads(item.read_text(encoding="utf-8", errors="ignore"))
            except (OSError, ValueError):
                continue
            name, app = str(data.get("DisplayName", "")).strip(), str(data.get("AppName", ""))
            main = str(data.get("MainGameAppName", "") or app)
            if not name or not app or main != app or data.get("bIsApplication") is False:
                continue                                  # add-ons and DLC have their own manifest
            if any(w in name.lower() for w in STORE_SKIP):
                continue
            exe = os.path.join(str(data.get("InstallLocation", "")), str(data.get("LaunchExecutable", "")))
            out.append({"name": name, "path": f"com.epicgames.launcher://apps/{app}?action=launch&silent=true",
                        "exe_path": exe if os.path.isfile(exe) else ""})
    except OSError:
        pass
    return out


def scan_apps(limit: int = 60) -> list:
    """[{name, path, exe, icon}] for apps worth a quick-launch tile: Start menu and desktop shortcuts of known
    apps and launchers, plus every game installed through Steam or Epic. exe is '' when unknown."""
    if not win.IS_WIN:
        return []
    found: dict = {}
    provider = QFileIconProvider()
    for folder in _start_folders():
        try:
            files = [f for f in folder.rglob("*") if f.suffix.lower() in (".lnk", ".url")]
        except OSError:
            continue
        for f in files:
            name = f.stem.strip()
            low = name.lower()
            if low in found or any(w in low for w in APP_SKIP):
                continue
            exe, icon_path, keep = "", "", False
            try:
                if f.suffix.lower() == ".url":
                    url = ""
                    for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                        if line.startswith("URL="):
                            url = line[4:].strip()
                        elif line.startswith("IconFile="):
                            icon_path = line[9:].strip()
                    keep = url.startswith(("steam://", "com.epicgames.launcher://", "uplay://", "origin"))
                else:
                    target = QFileInfo(str(f)).symLinkTarget()
                    tlow = target.lower().replace("/", "\\")
                    if tlow and not tlow.endswith(".exe"):
                        continue
                    exe = os.path.basename(tlow)
                    if exe == "update.exe":                       # Discord-style stub launchers
                        exe = low.replace(" ", "") + ".exe"
                    keep = any(w in low for w in APP_WORDS) or any(d in tlow for d in GAME_DIRS)
            except OSError:
                continue
            if not keep:
                continue
            icon = QIcon(icon_path) if icon_path and os.path.exists(icon_path) else provider.icon(QFileInfo(str(f)))
            found[low] = {"name": name, "path": str(f), "exe": exe, "icon": icon}
    try:
        for game in _store_games():
            low = game["name"].lower()
            if low in found:
                continue                                  # it already has a shortcut (with its own icon)
            exe_path = game["exe_path"]
            icon = provider.icon(QFileInfo(exe_path)) if exe_path else QIcon()
            found[low] = {"name": game["name"], "path": game["path"],
                          "exe": os.path.basename(exe_path).lower() if exe_path else "", "icon": icon}
    except Exception as exc:  # noqa: BLE001
        log.debug("store games: %s", exc)
    apps = sorted(found.values(), key=lambda a: a["name"].lower())
    return apps[:limit]


def running_names() -> set:
    try:
        import psutil
        return {(p.info["name"] or "").lower() for p in psutil.process_iter(["name"])}
    except Exception:  # noqa: BLE001
        return set()


def close_app(exe: str) -> bool:
    """Force-close every process called `exe` (like 'End task')."""
    exe = exe.lower()
    if not exe or exe in PROTECTED:
        return False
    try:
        import psutil
        done = False
        for p in psutil.process_iter(["name"]):
            if (p.info["name"] or "").lower() == exe and p.pid != os.getpid():
                try:
                    p.kill()
                    done = True
                except Exception:  # noqa: BLE001
                    pass
        return done
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# What's new (shown in the New tab; English text is the key, French is in lang_fr)
# --------------------------------------------------------------------------- #
NEWS = [        # every version, newest first: (version, [lines])
    ("2.6", ['Fresh start: everyone begins again with 500 coins and 3 keys (items, spins and cases reset)',
             'Free OG tag for every user who joined before 17 November',
             'Profiles: banners, frames and a showcase of your 3 favourite badges, seen by everyone',
             '16 banners and 12 frames in the Shop, on the Market and in Daily Deals',
             'Quick sell: sell any item right away for a quarter of its value, or every extra copy at once',
             'Style > Your profile: change your banner, frame, tag and showcase in one place',
             'Frames and tags show in every list, the leaderboards and the chat']),
    ("2.5", ['Games tab: Earn coins (mini games) and Duels are now two big separate cards',
             'Beat Tap has 4 modes (Normal, Rush, Long notes, Chords); Memory has 3 card styles',
             'The Shop tab is now the Hub: Get items (Shop, Deals, Cases, Market) and Yours (Inventory, Collection, Sets, Style)',
             'New: Deals, 4 items cheaper every day',
             'Friend profiles: friends get Message, Duel, Trade and Gift; others see what adding them unlocks',
             'Settings in 6 clear sections; Game mode text no longer goes off the screen',
             'Visualisers removed',
             'Translations fixed everywhere (users instead of players, one consistent French)']),
    ("2.4.1", ['Gifted cases open for free (after the server update)',
             'Everything opens inside the menu: no more extra windows over your games',
             'Game mode: in fullscreen games the mouse goes through Rubenium; tap Right Shift to open it',
             'The daily reward has a flame that grows every day, and waits until you open the menu',
             'Profile picture editor: move, zoom, turn, mirror and filters',
             'Big clear buttons in the shop and the admin panel',
             'No more error messages while the server update is waiting']),
    ("2.4", ['New Beat Tap: four lanes, long notes, combos and it gets faster',
             'New mini game: Memory. Duels with friends, with or without a bet',
             'Scratch card every 12 hours and a daily login reward (day 7: a free case)',
             'Messages with friends, leaderboards, trade history and collection sets with big bonuses',
             'Mini games pay a little more, with limits every 2 hours instead of every day',
             'Badges cost what they are really worth; Titanium, Gold and Mythic only come from cases',
             'Badge size and place, better lyrics, song history and Right Shift to show or hide',
             'Backups, offline mode, password help from the admin, a tour and nicer case openings']),
    ("2.3", ["New free mini game: Parking. Slide the cars and get the red car out for coins",
             "Quests now sit across the top of the Games tab",
             "Colour 2 is gone: only shop themes have a second colour",
             "Nothing in the shop looks like gold any more: gold is only for real awards",
             "Friend profiles: last seen, collection worth, gold badges, games played and what they wear",
             "Admin panel: every give and edit window works"]),
    ("2.2", ["The Ultimate Update: a fresh start for everyone (500 coins, 3 keys). Hours and friends stay",
             "Trading: send a request from a profile, 8 items and coins each side, Ready then Confirm",
             "Market: sell to other users at your price, or accept their offers (5% fee)",
             "Inventory, and a Shop with 10 balls, 10 lines, 5 fonts and 6 themes in every colour",
             "Badges remade: 12 Common, 12 Rare, 12 Epic, 12 Legendary and 6 secret Mythic",
             "Finishes: Basic, Painted, Shiny, Titanium and Gold (Gold is extremely rare)",
             "9 cases, gifts for friends, coins drops that usually beat the price",
             "Beat Tap mini game, quests every hour, day and week",
             "Rocket with automatic cash-out, Dice with more choices, free spin every 2 hours",
             "Social tab: your stats, profile pictures, every user, name changes",
             "Notifications with a quiet sound (choose them in Settings), live giveaways",
             "More coins with time: 20 every 10 minutes",
             "Use screen colours: the menu follows the colours of your screen"]),
    ("2.1", ["Quests: three daily and three weekly goals that pay coins",
             "Friends: a refresh button, and badges on profiles"]),
    ("2.0", ["The online update: coins, keys and items now live on your account",
             "Everyone starts fresh: 500 coins and 3 keys",
             "Coins come with time (10 every 15 minutes) and 1 key every hour",
             "Five rarities: Standard, Rare, Special, Epic, Exotic. 55 badges, 5 of them Exotic",
             "Sell badges to the vendor for quick coins",
             "Four new cases with their odds shown, and a free daily case",
             "Casino played on the server, with two new games: Dice and Rocket",
             "Free spin every 3 hours: press Collect to take the prize",
             "Themes, ball and ring now unlock with hours played"]),
    ("1.10", ["Logged in? Rubenium starts by itself after 5 seconds (click the card to start at once)"]),
    ("1.9", ["Friends: add users by username and see who is online",
             "Profiles show time played and, soon, badges and play history"]),
    ("1.8", ["The login now sits inside the start screen",
             "You can delete your account in Settings (type your name, then hold)",
             "Reset all settings is gone (each tab keeps its own reset)",
             "Three Rocket League swaps were removed"]),
    ("1.7", ["Accounts: create one or log in on the welcome screen. You stay logged in",
             "Time played is now counted online, for your account",
             "One look for everyone: strong glow, black background, round corners"]),
    ("1.6", ["Timer moved to the bottom of the Screen tab",
             "New ball and ring: White Gold. Neon is now number 3",
             "Long song names get smaller instead of being cut",
             "Medal is no longer picked up as a music app"]),
    ("1.5", ["Turn off all swaps is now Reset Swaps: it puts every original file back",
             "Wrong, left-over or broken swap files are found and fixed automatically"]),
    ("1.4", ["Casino lobby: the menu only grows when you go in, and goes back when you leave",
             "New games: Plinko and Bombs. Slots now show every prize",
             "50 badges in 17 colours, from basic to gold. Show 3 of them on the music tab",
             "Cases with real odds and an opening animation. Keys are earned in the casino",
             "New ball style and ring: Neon",
             "Colours cost 100 coins each. The music's colours open after 1 hour, for free",
             "A fresh start: everyone begins again from zero coins"]),
    ("1.3", ["Coins: 25 every 15 minutes, with a timer for the next drop. Your hours became coins",
             "Shop: themes, colours, ball styles, badges and titles are bought with coins",
             "Games: blackjack, chicken, wheel and slots, plus a free spin every day",
             "Badges and titles show on the music tab",
             "Tidier menu: Screen holds crosshair and display, PC holds stats, tools and apps",
             "Resetting the settings now takes two clicks and a hold"]),
    ("1.2", ["Rubenium ignores the mouse while a game uses it to aim, even in borderless fullscreen",
             "Moving the menu: the spot you hold stays under the mouse, and it follows smoothly",
             "The ball never sits over the close buttons in the top-right corner"]),
    ("1.1", ["Themes rebuilt: one night sky that fills with stars, then turns to gold",
             "Pick any colour on a colour line, and add a second colour after 24 h",
             "New ball styles, with a gold ring",
             "Rubenium start screen when Rocket League and Fortnite load",
             "Softer interface sounds",
             "The menu size changes smoothly",
             "New app icon"]),
    ("1.0", ["Hold the ball to open Rubenium, so it never opens by accident in a game",
             "Hold the menu for a moment to move it",
             "9 new swaps, separate Fennec and Octane decals, and a Paint finishes section",
             "Open apps move to the top of the Apps tab",
             "New white styles for the R",
             "The full update history is in this tab"]),
    ("0.9", ["New swaps and a Player banners section",
             "The ball stays where you leave it and snaps to corners and edges",
             "Clicks go through Rubenium while a game hides or locks the mouse",
             "Display has just two choices: Default and Custom",
             "Apps finds every game installed with Steam or Epic"]),
    ("0.8", ["Rubenium installs like a normal Windows app and updates by itself",
             "Soft, quiet interface sounds",
             "Top apps in Stats, measured like Task Manager",
             "Rubenium uses much less processor"]),
    ("0.7", ["A picture on every swap",
             "5 new themes, and styles for the R and the song ring",
             "A more reliable Update button"]),
    ("0.6", ["Welcome screen with a Launch button",
             "8 new swaps, and several swaps on at once",
             "Choose your tabs and the size of the ball",
             "Stronger glow that follows the music"]),
    ("0.5", ["Updates from inside the app",
             "New swap: Big Splash to Adidas"]),
    ("0.4", ["Rocket League swaps for Steam and Epic, with backups of the original files",
             "The menu bar hides when you are not using it",
             "6 save slots for crosshairs"]),
    ("0.3", ["New tabs: Stats, Timer, Apps, Themes and Rocket League",
             "Crosshair presets",
             "Themes that unlock with time"]),
    ("0.2", ["No licence key needed",
             "The glow follows the music",
             "Simpler wording in English and French",
             "Settings saved in Documents"]),
    ("0.1", ["First version: music, lyrics, crosshair, screen colours and tools in one glowing ball"]),
]

# --------------------------------------------------------------------------- #
# Rocket League: find the game, swap item files, keep the originals safe
# --------------------------------------------------------------------------- #
RL_CATS = [("goal", "Goal explosions"), ("body", "Car bodies"), ("fdecal", "Fennec decals"),
           ("odecal", "Octane decals"), ("boost", "Boosts"), ("wheels", "Wheels"), ("paint", "Paint finishes"),
           ("banner", "Player banners"), ("trail", "Trails")]
# One entry per swap. `old` is the item you equip in the game, `new` is what it turns into, `file` is the game
# file it replaces. Several swaps of one category can be on together; two swaps of the SAME file cannot.
# To add a swap: put its file in swaps/<id>/<file> (and, if you have one, a picture named preview.png) and
# add one line here. preview=False: the tile never shows a picture.
RL_ITEMS = [
    dict(id="atomizer_gentlemates", cat="goal", old="Atomizer", new="Gentle Mates 2025", file="explosion_Rekt_SF.upk"),
    dict(id="splash_adidas", cat="goal", old="Big Splash", new="Adidas", file="explosion_splash_SF.upk"),
    dict(id="splash_supernova", cat="goal", old="Big Splash", new="SuperNova III", file="explosion_splash_SF.upk"),
    dict(id="octane_fennec", cat="body", old="Octane", new="Fennec", file="Body_Octane_SF.upk"),
    dict(id="fennec_flames_likescraft", cat="fdecal", old="Flames", new="Likescraft", file="skin_grain_flames_SF.upk"),
    dict(id="fennec_flames_blacklunation", cat="fdecal", old="Flames", new="Black Lunation",
         file="skin_grain_flames_SF.upk"),
    dict(id="fennec_stripes_falcons", cat="fdecal", old="Stripes", new="RLCS Falcons", file="skin_grain_stripes_SF.upk"),
    dict(id="fennec_stripes_cosmological", cat="fdecal", old="Stripes", new="Cosmological",
         file="skin_grain_stripes_SF.upk"),
    dict(id="fennec_stripes_ombre", cat="fdecal", old="Stripes", new="Ombre", file="skin_grain_stripes_SF.upk"),
    dict(id="fennec_nitty_gc", cat="fdecal", old="Nitty Gritty", new="S-13 Grand Champion",
         file="skin_grain_racelines_SF.upk"),
    dict(id="fennec_ribbon_affluenter", cat="fdecal", old="Ribbon", new="Affluenter", file="skin_grain_block_SF.upk"),
    dict(id="octane_lightning_ssg", cat="odecal", old="Lightning", new="RLCS SSG", file="Skin_Octane_Lightning_SF.upk"),
    dict(id="octane_stripes_joyo", cat="odecal", old="Stripes", new="Joyo Octane", file="Skin_Octane_Stripes_SF.upk"),
    dict(id="bubbles_alpha", cat="boost", old="Bubbles", new="Alpha Boost", file="Boost_Bubble_SF.upk"),
    dict(id="bubbles_dev", cat="boost", old="Bubbles", new="Dev Boost", file="Boost_Bubble_SF.upk"),
    dict(id="bubbles_purple", cat="boost", old="Bubbles", new="Invisible Boost", file="Boost_Bubble_SF.upk",
         preview=False),
    dict(id="standard_purple", cat="boost", old="Standard", new="Purple Standard", file="Boost_Standard_SF.upk"),
    dict(id="flamethrower_sparkles", cat="boost", old="Flamethrower", new="Sparkles", file="Boost_Flamethrower_SF.upk"),
    dict(id="dieci_black_infinium", cat="wheels", old="Black Dieci", new="Infinium", file="WHEEL_Caliber_SF.upk"),
    dict(id="stern_alpha", cat="wheels", old="Stern", new="Alpha Wheels", file="WHEEL_Hydra_SF.upk"),
    dict(id="anodized_pearl", cat="paint", old="Anodized", new="Anodized Pearl", file="paintfinish_anodized_SF.upk"),
    dict(id="banner_ssl_s8", cat="banner", old="Standard", new="S8 Supersonic Legend",
         file="playerBanner_RLShield_SF.upk"),
    dict(id="banner_ssl_s21", cat="banner", old="Standard", new="S21 Supersonic Legend",
         file="playerBanner_RLShield_SF.upk"),
]
RL_BY_ID = {it["id"]: it for it in RL_ITEMS}
RL_EXE = "rocketleague.exe"


# Swap files that were in an earlier version and are gone: {hash: game file}. If one is still in the game
# folder it is recognised and the original is put back (see RocketSwaps.needs_repair).
RETIRED = {"f1cb440607e0dd4cabfd155b71c29ad444d2d44b7322251455b3f1e1ea30a9fd": "playerBanner_RLShield_SF.upk",
           "4a2c413d16f1683509728f38604bcd8a453fa07b6325ebb84b14a927a712be27": "skin_grain_stripes_SF.upk",
           # 1.8: three swaps were removed for good. Every version of their files is recognised here, so the
           # original game file is put back automatically for anyone who still has one in the game.
           "ed71a46b22a8f4608e27a57502e22f569b4c1f661ba9e130faf720df2742bdfd": "explosion_Dragon_SF.upk",
           "ed814c9961159e70f1dcef48755cdb54e455fee66110b0ef6e19e05662617827": "explosion_Dragon_SF.upk",
           "b529dea013234bcaebc4841426a0d483360f9ff7509948372af9b6917f4ac2f7": "explosion_Dragon_SF.upk",
           "3c4680632863f58e2fe4c736802e959d6bc351dcbf74cda4fd5b110b4fab0a6b": "explosion_Dragon_SF.upk",
           "122727c810efe7df76f3fada4caf085b18af1781e63d4f70697fa7c744ab018d": "playerBanner_DiamondTile_SF.upk"}


def swap_files() -> list:
    """Every game file Rubenium may have replaced: today's swaps and the ones that were removed."""
    return sorted({it["file"] for it in RL_ITEMS} | set(RETIRED.values()), key=str.lower)


REMOVED_SWAPS = ("dragons_lanternlift", "dragons_monsoon", "diamond_electric", "fennec_stripes_strongline")

# Clean game files shipped with the app in swaps/_originals: used to put a game file back when the player's own
# saved copy is missing or unusable. Only files checked to be untouched originals are listed (and a shipped
# file is only ever used if it still matches its fingerprint here).
ORIGINALS = {
    "Body_Octane_SF.upk": "3359efe77733d8aae7e21e227b841e4e25822b7758a072e7eef104ee06c48ba4",
    "WHEEL_Caliber_SF.upk": "0e5006251eef9d30a281c724a62a2b8de0b204c5ebc8c8ad33bc2f0c5c6db4a1",
    "explosion_Dragon_SF.upk": "633e72e7924b76727587c2b94a4097564930965ca6d512aff6f654a38718c9f0",
    "playerBanner_DiamondTile_SF.upk": "05aadcd1aa89cacebedbf1b74a689ead278f60b08cd24a28e968d4bb89e59eb4",
}
UPK_MAGIC = b"\xc1\x83\x2a\x9e"           # how every Rocket League package file starts


def upk_ok(path) -> bool:
    """Does this look like a whole Rocket League package (not empty, not cut off at the start)?"""
    try:
        with open(path, "rb") as f:
            head = f.read(4)
        return head == UPK_MAGIC and os.path.getsize(path) > 1024
    except OSError:
        return False


def bundled_original(name: str):
    """The clean copy of game file `name` shipped with Rubenium, or None."""
    want = next((h for f, h in ORIGINALS.items() if f.lower() == name.lower()), None)
    if not want:
        return None
    for root in _swap_roots():
        f = root / "_originals" / name
        if f.is_file() and file_hash(f) == want:
            return f
    return None
ABSENT = "absent"      # marks a swap file the game did not have: switching the swap off removes it


def rl_key(item: dict) -> str:
    """Swaps are told apart by the game file they replace: one swap per file."""
    return item["file"].lower()


def _swap_roots() -> list:
    import sys
    return [Path(getattr(sys, "_MEIPASS", "")) / "swaps", Path(sys.argv[0]).resolve().parent / "swaps",
            Path(sys.executable).resolve().parent / "swaps"]


_previews: dict = {}


def swap_preview(item: dict):
    """The picture of what a swap looks like (swaps/<id>/preview.png), or None when there is none yet."""
    from PyQt6.QtGui import QPixmap
    ident = item["id"]
    if item.get("preview") is False:
        return None
    if ident not in _previews:
        found = None
        for root in [_rl_store() / "swaps"] + _swap_roots():
            for name in ("preview.png", "preview.jpg", "preview.webp"):
                f = root / ident / name
                try:
                    if f.is_file():
                        pm = QPixmap(str(f))
                        if not pm.isNull():
                            found = pm
                            break
                except OSError:
                    continue
            if found is not None:
                break
        _previews[ident] = found
    return _previews[ident]


def _rl_store():
    from .core import DATA_DIR
    return DATA_DIR / "rocket_league"


PLATFORMS = ("epic", "steam")
PLATFORM_NAMES = {"epic": "Epic Games", "steam": "Steam"}


def rocket_league_ok(folder: str) -> bool:
    return bool(folder) and os.path.isdir(os.path.join(folder, "TAGame", "CookedPCConsole"))


def platform_of(folder: str) -> str:
    return "steam" if "steamapps" in folder.lower().replace("/", "\\") else "epic"


def _drives() -> list:
    """Local hard drives only (no network, CD or card readers, which can be slow to answer)."""
    import string
    try:
        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        mask = k32.GetLogicalDrives()
        out = []
        for i, d in enumerate(string.ascii_uppercase):
            if mask & (1 << i) and k32.GetDriveTypeW(f"{d}:\\") == 3:     # DRIVE_FIXED
                out.append(f"{d}:\\")
        return out
    except Exception:  # noqa: BLE001
        return []


def _steam_roots() -> list:
    roots = []
    try:
        import winreg
        for hive, key, value in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                 (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                                 (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    roots.append(str(winreg.QueryValueEx(k, value)[0]))
            except OSError:
                continue
    except ImportError:
        pass
    libraries = []
    import re
    for root in roots:
        libraries.append(root)
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        try:
            text = open(vdf, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for m in re.finditer(r'"path"\s+"([^"]+)"', text):            # every Steam library on every drive
            libraries.append(m.group(1).replace("\\\\", "\\"))
    return libraries


def find_installs() -> dict:
    """{platform: {"folder", "app"}} for every Rocket League install that can be found on this PC."""
    if not win.IS_WIN:
        return {}
    found: dict = {}

    def add(folder: str, app: str = "", platform: str = "") -> None:
        if not folder:
            return
        folder = os.path.normpath(folder)
        if not rocket_league_ok(folder):
            return
        plat = platform or platform_of(folder)
        if plat not in found:
            found[plat] = {"folder": folder, "app": app}
        elif app and not found[plat]["app"]:
            found[plat]["app"] = app

    program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    try:                                                  # Epic: one manifest per installed game
        for item in (Path(program_data) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests").glob("*.item"):
            try:
                data = json.loads(item.read_text(encoding="utf-8", errors="ignore"))
            except (OSError, ValueError):
                continue
            if "rocket league" in str(data.get("DisplayName", "")).lower() or data.get("AppName") == "Sugar":
                add(str(data.get("InstallLocation", "")), str(data.get("AppName", "")), "epic")
    except OSError:
        pass
    try:                                                  # Epic: the launcher's own list
        data = json.loads((Path(program_data) / "Epic" / "UnrealEngineLauncher" / "LauncherInstalled.dat")
                          .read_text(encoding="utf-8", errors="ignore"))
        for entry in data.get("InstallationList", []):
            if entry.get("AppName") == "Sugar" or "rocketleague" in str(entry.get("InstallLocation", "")).lower():
                add(str(entry.get("InstallLocation", "")), str(entry.get("AppName", "")), "epic")
    except (OSError, ValueError, AttributeError):
        pass
    for lib in _steam_roots():                            # Steam: every library folder
        add(os.path.join(lib, "steamapps", "common", "rocketleague"), "", "steam")
    if len(found) < 2:                                    # last resort: the usual folders on every drive
        for drive in _drives():
            for tail in ("Program Files\\Epic Games\\rocketleague", "Epic Games\\rocketleague",
                         "Games\\Epic Games\\rocketleague", "Games\\rocketleague",
                         "Program Files (x86)\\Steam\\steamapps\\common\\rocketleague",
                         "Program Files\\Steam\\steamapps\\common\\rocketleague",
                         "SteamLibrary\\steamapps\\common\\rocketleague", "Steam\\steamapps\\common\\rocketleague",
                         "Games\\SteamLibrary\\steamapps\\common\\rocketleague"):
                add(os.path.join(drive, tail))
    return found


_hash_cache: dict = {}


def file_hash(path) -> str:
    """SHA-256 of a file, cached by size and modification time ("" if it cannot be read)."""
    import hashlib
    try:
        st = os.stat(path)
    except OSError:
        return ""
    key = (str(path), st.st_size, st.st_mtime_ns)
    hit = _hash_cache.get(key)
    if hit is None:
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for block in iter(lambda: f.read(1 << 20), b""):
                    h.update(block)
        except OSError:
            return ""
        hit = _hash_cache[key] = h.hexdigest()
        if len(_hash_cache) > 64:
            for k in list(_hash_cache)[:32]:
                _hash_cache.pop(k, None)
    return hit


def swap_source(item: dict):
    """Where this swap's replacement file is. Files shipped with the app are copied once into
    Documents/Rubenium/rocket_league/swaps so they survive app updates."""
    import shutil
    if item.get("soon"):
        return None                              # shown as "Coming soon": cannot be switched on yet
    store = _rl_store() / "swaps" / item["id"] / item["file"]
    for root in _swap_roots():
        src = root / item["id"] / item["file"]
        if src.is_file():
            if store.is_file():
                if file_hash(store) == file_hash(src):
                    return store
                _remember_custom(item["file"], file_hash(store))   # an app update brought a new version
            try:
                store.parent.mkdir(parents=True, exist_ok=True)
                tmp = store.with_name(store.name + ".part")
                shutil.copyfile(src, tmp)
                os.replace(tmp, store)
                return store
            except OSError:
                return src
    return store if store.is_file() else None


def _known_customs() -> dict:
    """{hash: file name} of swap files from earlier app versions (still recognised as swaps, never as originals)."""
    try:
        data = json.loads((_rl_store() / "known.json").read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _remember_custom(filename: str, digest: str) -> None:
    if not digest:
        return
    known = _known_customs()
    known[digest] = filename
    try:
        path = _rl_store() / "known.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(known, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def _atomic_copy(src, dst) -> None:
    """Copy so that `dst` is never half-written: a temporary file in the same folder, then a rename."""
    import shutil
    dst = Path(dst)
    tmp = dst.with_name(dst.name + ".rbn-tmp")
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def _clean_install(entry) -> dict:
    e = entry if isinstance(entry, dict) else {}
    act = e.get("active") if isinstance(e.get("active"), dict) else {}
    orig = e.get("orig") if isinstance(e.get("orig"), dict) else {}
    return {"folder": str(e.get("folder", "") or ""), "app": str(e.get("app", "") or ""),
            "manual": bool(e.get("manual", False)),
            "active": {str(k): str(v) for k, v in act.items()}, "orig": {str(k): str(v) for k, v in orig.items()},
            "stamp": str(e.get("stamp", "") or "")}


class RocketSwaps(QObject):
    """Swaps Rocket League item files and puts them back, separately for each install (Steam / Epic).

    * The real files decide what is swapped: every check reads the game files, never a stored guess.
    * The game's own file is copied to Documents/Rubenium/rocket_league/originals/<platform> before it is
      ever replaced.
    * After a game update (the game's exe changed) the files the update put back become the new originals and
      the swaps can be applied again (automatically if the user wants).
    * If a swapped file was changed by something else while the game did not update, the saved original is
      kept and the user is offered a fix."""
    busy = pyqtSignal(str)              # step text
    done = pyqtSignal(bool, str, dict)  # ok, message key, results to store
    changed = pyqtSignal()

    def __init__(self, cfg) -> None:
        super().__init__()
        self.cfg = cfg
        self.working = False
        self.found: dict = {}
        self._noticed = ""
        self._timer = QTimer(self)
        self._timer.setInterval(20000)
        self._timer.timeout.connect(self.watch)
        self.done.connect(self._finished)
        self._detected = False
        self._repair_wait: dict = {}               # per install: no new repair before this time
        self._index: dict = {}                     # per install: game file name -> path (from a folder search)
        self._migrate()
        for ident in REMOVED_SWAPS:                # swaps that are gone: their saved files go too
            try:
                import shutil
                shutil.rmtree(_rl_store() / "swaps" / ident, ignore_errors=True)
            except Exception:  # noqa: BLE001
                pass

    # -- settings
    @property
    def rl(self) -> dict:
        return self.cfg["rl"]

    def _installs(self) -> dict:
        raw = self.rl["installs"]
        clean = {p: _clean_install(raw.get(p)) for p in PLATFORMS if p in raw}
        self.rl["installs"] = clean
        return clean

    def _entry(self, plat: str) -> dict:
        installs = self._installs()
        if plat not in installs:
            installs[plat] = _clean_install({})
        return installs[plat]

    def _migrate(self) -> None:
        """2.0 kept one install at the top level: move it under its platform."""
        import shutil
        rl = self.rl
        if not rl.get("folder"):
            return
        plat = platform_of(rl["folder"])
        e = self._entry(plat)
        if not e["folder"]:
            e.update(folder=rl["folder"], app=rl.get("app", ""), active=dict(rl.get("active") or {}),
                     orig=dict(rl.get("orig") or {}), stamp=rl.get("stamp", ""))
            old = _rl_store() / "originals"
            new = old / plat
            try:
                new.mkdir(parents=True, exist_ok=True)
                for f in old.glob("*.upk"):
                    shutil.move(str(f), str(new / f.name))
            except OSError:
                pass
        rl.update(folder="", app="", active={}, orig={}, stamp="")
        if not rl["platform"]:
            rl["platform"] = plat
        self.cfg.save()

    def detect(self) -> list:
        """Look for every install again. Returns the platforms found."""
        found = find_installs()
        for plat in PLATFORMS:                        # a folder the user picked by hand still counts
            e = self.rl["installs"].get(plat)
            if plat not in found and isinstance(e, dict) and e.get("manual") and rocket_league_ok(e.get("folder", "")):
                found[plat] = {"folder": os.path.normpath(e["folder"]), "app": e.get("app", "")}
        self.found = found
        for plat, info in found.items():
            e = self._entry(plat)
            if os.path.normcase(e["folder"]) != os.path.normcase(info["folder"]):
                e["folder"] = info["folder"]
                e["stamp"] = ""                        # a new place: treat it like an update
            if info["app"]:
                e["app"] = info["app"]
        if self.rl["platform"] not in found:
            self.rl["platform"] = next((p for p in PLATFORMS if p in found), "")
        self.cfg.save()
        return [p for p in PLATFORMS if p in found]

    def add_folder(self, folder: str) -> str:
        """A folder chosen by hand. Returns its platform, or "" if it is not Rocket League."""
        if not rocket_league_ok(folder):
            return ""
        plat = platform_of(folder)
        e = self._entry(plat)
        e.update(folder=os.path.normpath(folder), manual=True)
        self.rl["platform"] = plat
        self.cfg.save()
        self.detect()
        return plat

    def available(self) -> list:
        return [p for p in PLATFORMS if p in self.found]

    def platform(self) -> str:
        p = self.rl["platform"]
        return p if p in self.found else ""

    def set_platform(self, plat: str) -> bool:
        if plat not in self.found:
            return False
        self.rl["platform"] = plat
        self.cfg.save()
        return True

    def folder(self, plat: str = "") -> str:
        plat = plat or self.platform()
        return self.found.get(plat, {}).get("folder", "")

    def cooked(self, plat: str = "") -> Path:
        return Path(self.folder(plat)) / "TAGame" / "CookedPCConsole"

    def game_file(self, plat: str, name: str) -> Path:
        """Where the game keeps one file. Most are directly in CookedPCConsole, some in a sub-folder (found by
        a search of the game's folders, remembered). An item the game has not downloaded yet has no file:
        then the swap is placed directly in CookedPCConsole, where the game looks for it."""
        cooked = self.cooked(plat)
        direct = cooked / name
        if direct.is_file():
            return direct
        index = self._index.get(plat)
        if index is None or (name.lower() not in index and time.monotonic() - index.get("", 0) > 120):
            index = {"": time.monotonic()}
            try:
                for root in (cooked, Path(self.folder(plat)) / "TAGame"):
                    for dirpath, _dirs, files in os.walk(root):
                        for f in files:
                            if f.lower().endswith(".upk"):
                                index.setdefault(f.lower(), os.path.join(dirpath, f))
            except OSError:
                pass
            self._index[plat] = index
        found = index.get(name.lower())
        if found and os.path.isfile(found):
            return Path(found)
        return direct

    def active(self, plat: str = "") -> dict:
        """The swaps the user wants on this install: {game file: item id}, one per game file.
        (Before 3.0 this was stored per category; only the item ids matter, so old settings still load.)"""
        plat = plat or self.platform()
        out = {}
        for ident in self._entry(plat)["active"].values() if plat else []:
            it = RL_BY_ID.get(ident)
            if it and not it.get("soon"):
                out[rl_key(it)] = ident
        return out

    def actual(self, plat: str = "") -> dict:
        """What the game files really are right now: {game file: item id}."""
        plat = plat or self.platform()
        out = {}
        if not plat:
            return out
        for it in RL_ITEMS:
            src = swap_source(it)
            game = self.game_file(plat, it["file"])
            if src is not None and game.is_file() and file_hash(game) == file_hash(src):
                out[rl_key(it)] = it["id"]
        return out

    def stamp(self, plat: str = "") -> str:
        exe = Path(self.folder(plat)) / "Binaries" / "Win64" / "RocketLeague.exe"
        try:
            st = exe.stat()
            return f"{st.st_size}:{int(st.st_mtime)}"
        except OSError:
            return ""

    def running(self, plat: str = "") -> bool:
        """Is this install's game running? (Unknown process paths count as running, to be safe.)"""
        folder = os.path.normcase(self.folder(plat))
        try:
            import psutil
            for p in psutil.process_iter(["name"]):
                if (p.info["name"] or "").lower() != RL_EXE:
                    continue
                try:
                    exe = os.path.normcase(p.exe() or "")
                except Exception:  # noqa: BLE001
                    return True
                if not folder or not exe or exe.startswith(folder):
                    return True
        except Exception:  # noqa: BLE001
            return False
        return False

    def _customs(self, filename: str) -> set:
        out = {h for h, name in _known_customs().items() if name.lower() == filename.lower()}
        out |= {h for h, name in RETIRED.items() if name.lower() == filename.lower()}
        for it in RL_ITEMS:
            if it["file"].lower() == filename.lower():
                src = swap_source(it)
                if src is not None:
                    out.add(file_hash(src))
        out.discard("")
        return out

    def check(self, plat: str = "") -> str:
        """off | ok | nogame | missing | nofile | changed | undone (for the wanted swaps of one install)"""
        plat = plat or self.platform()
        if not plat:
            return "nogame"
        act = self.active(plat)
        if not act:
            return "off"
        worst, order = "ok", ["ok", "undone", "changed", "nofile", "missing"]
        e = self._entry(plat)
        for ident in act.values():
            it = RL_BY_ID[ident]
            game = self.game_file(plat, it["file"])
            src = swap_source(it)
            if src is None:
                state = "nofile"
            elif not game.is_file():
                state = "undone"                    # not placed yet (or removed): applying puts it back
            elif file_hash(game) == file_hash(src):
                state = "ok"
            elif self.stamp(plat) != e["stamp"]:
                state = "undone"
            else:
                state = "changed"
            if order.index(state) > order.index(worst):
                worst = state
        return worst

    # -- applying (in a worker thread; settings are only written back on the main thread)
    def apply(self, desired: dict, reload: bool = False, quiet: bool = False, plat: str = "") -> bool:
        plat = plat or self.platform()
        if self.working:
            return False
        if not plat or not rocket_league_ok(self.folder(plat)):
            self.done.emit(False, "nogame", {"quiet": quiet})
            return False
        self.working = True
        desired = {rl_key(RL_BY_ID[i]): i for i in desired.values() if i in RL_BY_ID}
        e = self._entry(plat)
        paths = {name.lower(): self.game_file(plat, name) for name in swap_files()}
        job = {"plat": plat, "cooked": self.cooked(plat), "paths": paths, "orig": dict(e["orig"]),
               "stamp_saved": e["stamp"], "stamp_now": self.stamp(plat),
               "was": {RL_BY_ID[i]["file"].lower() for i in e["active"].values() if i in RL_BY_ID}}
        import threading
        threading.Thread(target=self._work, args=(dict(desired), reload, quiet, job), daemon=True).start()
        return True

    def _work(self, desired: dict, reload: bool, quiet: bool, job: dict) -> None:
        plat = job["plat"]
        info = {"desired": desired, "reload": False, "quiet": quiet, "plat": plat}
        try:
            if self.running(plat):
                if not reload:
                    return self.done.emit(False, "running", info)
                info["reload"] = True
                self.busy.emit("close")
                self._close_game(plat)
                if self.running(plat):
                    return self.done.emit(False, "running", info)
            self.busy.emit("apply")
            ok, key, orig = self._apply(desired, job)
            info["orig"] = orig
            info["stamp"] = self.stamp(plat)
            self.done.emit(ok, key, info)
        except PermissionError:
            self.done.emit(False, "blocked", info)
        except Exception as exc:  # noqa: BLE001
            log.warning("swap failed: %s", exc)
            self.done.emit(False, "error", info)

    def _close_game(self, plat: str) -> None:
        folder = os.path.normcase(self.folder(plat))
        try:
            import psutil
            for p in psutil.process_iter(["name"]):
                if (p.info["name"] or "").lower() != RL_EXE:
                    continue
                try:
                    exe = os.path.normcase(p.exe() or "")
                except Exception:  # noqa: BLE001
                    exe = ""
                if not exe or exe.startswith(folder):
                    try:
                        p.kill()
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            return
        for _ in range(60):                           # up to 15 s for Windows to let go of the files
            if not self.running(plat):
                time.sleep(1.0)
                return
            time.sleep(0.25)

    def _apply(self, desired: dict, job: dict):
        """Make every swap file of one install match `desired`. Returns (ok, message key, originals)."""
        cooked = job["cooked"]
        backups = _rl_store() / "originals" / job["plat"]
        backups.mkdir(parents=True, exist_ok=True)
        orig = dict(job["orig"])
        updated = job["stamp_now"] != job["stamp_saved"]
        want_by_file = {}
        for ident in desired.values():
            it = RL_BY_ID.get(ident)
            if it:
                want_by_file[it["file"].lower()] = it
        for name in swap_files():
            game = job["paths"].get(name.lower(), cooked / name)
            want = want_by_file.get(name.lower())
            if not game.is_file():
                # The game has no such file (an item it has not downloaded): the swap is simply added, and
                # taken away again when it is switched off.
                if want:
                    src = swap_source(want)
                    if src is None:
                        return False, "nofile", orig
                    _atomic_copy(src, game)
                    if file_hash(game) != file_hash(src):
                        return False, "error", orig
                    orig[name] = ABSENT
                continue
            cur = file_hash(game)
            customs = self._customs(name)
            backup = backups / name
            broken = not upk_ok(game)                  # empty or cut off: never kept as an original
            if want:
                src = swap_source(want)
                if src is None:
                    return False, "nofile", orig
                want_hash = file_hash(src)
                if cur == want_hash:
                    continue
                if cur not in customs and not broken and orig.get(name) == ABSENT:
                    orig.pop(name, None)                # the game has the file now (an update): a real original
                if cur not in customs and not broken:
                    # The file in the game is an original. Keep it, unless it is a stranger's file
                    # (same game version but different from the original we saved).
                    tampered = (not updated) and orig.get(name) and orig.get(name) != cur and backup.is_file()
                    if not tampered:
                        _atomic_copy(game, backup)
                        if file_hash(backup) != cur:
                            return False, "error", orig
                        orig[name] = cur
                if self._restore_source(name, backups, customs) is None:
                    return False, "nobackup", orig     # never swap without a way back
                _atomic_copy(src, game)
                if file_hash(game) != want_hash:
                    return False, "error", orig
            elif cur in customs and orig.get(name) == ABSENT:
                game.unlink()                           # it was added by a swap: remove it again
            elif cur in customs or broken:
                # A swap that is not wanted (left over, from another tool, or from an old version) or a broken
                # file: put the original back, from the player's own saved copy or the clean copy shipped
                # with Rubenium.
                src = self._restore_source(name, backups, customs)
                if src is None:
                    if name.lower() in job.get("was", set()):
                        return False, "nobackup", orig  # the swap being switched off cannot be undone
                    continue                            # a left-over we cannot fix yet: leave it, fix the rest
                good = file_hash(src)
                _atomic_copy(src, game)
                if file_hash(game) != good:
                    return False, "error", orig
                if src != backup:
                    orig[name] = good
        return True, "ok", orig

    @staticmethod
    def _restore_source(name: str, backups: Path, customs: set):
        """Where to take the original of `name` from: the player's own saved copy if it is sound, otherwise
        the clean copy shipped with Rubenium (None if neither)."""
        backup = backups / name
        if backup.is_file() and upk_ok(backup) and file_hash(backup) not in customs:
            return backup
        return bundled_original(name)

    def needs_repair(self, plat: str) -> bool:
        """Is a game file a swap the player does not want (another swap, a left-over, one from an old version),
        or broken, while it can be fixed? Checked for everyone, also new users with no swaps on."""
        want = {}
        for ident in self.active(plat).values():
            it = RL_BY_ID[ident]
            want[it["file"].lower()] = it
        backups = _rl_store() / "originals" / plat
        orig = self._entry(plat)["orig"]
        for name in swap_files():
            game = self.game_file(plat, name)
            if not game.is_file():
                continue
            cur = file_hash(game)
            customs = self._customs(name)
            item = want.get(name.lower())
            if item is not None:
                src = swap_source(item)
                if src is not None and cur in customs and cur != file_hash(src):
                    return True                         # the wrong swap is in the game
                continue
            if cur in customs and orig.get(name) == ABSENT:
                return True
            if (cur in customs or not upk_ok(game)) and self._restore_source(name, backups, customs) is not None:
                return True
        return False

    def _finished(self, ok: bool, key: str, info: dict) -> None:
        self.working = False
        plat = info.get("plat")
        if plat in PLATFORMS:
            e = self._entry(plat)
            if "orig" in info:
                e["orig"] = info["orig"]
            if ok:
                e["active"] = dict(info.get("desired", {}))
                e["stamp"] = info.get("stamp", "")
                self._noticed = ""
                self._repair_wait.pop(plat, None)
        self.cfg.save()
        self.changed.emit()

    # -- start the game again after a reload
    def launch(self, plat: str = "") -> bool:
        plat = plat or self.platform()
        if plat == "steam":
            url = "steam://rungameid/252950"
        else:
            url = f"com.epicgames.launcher://apps/{self._entry(plat)['app'] or 'Sugar'}?action=launch&silent=true"
        return win.open_path(url)

    # -- watching for game updates and changed files (every install)
    def ensure_detected(self) -> None:
        if not self._detected:
            self._detected = True
            self.detect()

    def start(self) -> None:
        QTimer.singleShot(1500, self.ensure_detected)       # after the ball is on screen
        self._timer.start()
        QTimer.singleShot(4000, self.watch)

    def stop(self) -> None:
        self._timer.stop()

    def watch(self) -> None:
        self.ensure_detected()
        if self.working:
            return
        for plat in self.available():
            if self.running(plat) or time.monotonic() < self._repair_wait.get(plat, 0.0):
                continue
            if self.needs_repair(plat) and self._settled(plat):
                self._repair_wait[plat] = time.monotonic() + 600            # if it cannot be fixed: retry later
                self.apply(self.active(plat), quiet=True, plat=plat)       # puts the right files back
                return
            if not self.active(plat):
                continue
            state = self.check(plat)
            if state == "undone" and self.rl["auto_fix"] and not self.running(plat) and self._settled(plat):
                self.apply(self.active(plat), quiet=True, plat=plat)
                return
            if state in ("changed", "undone", "missing") and self._noticed != plat + state:
                self._noticed = plat + state
                self.changed.emit()

    def _settled(self, plat: str) -> bool:
        """True once the game files have not moved for a minute (an update has finished)."""
        newest = 0.0
        for it in RL_ITEMS:
            try:
                newest = max(newest, os.stat(self.cooked(plat) / it["file"]).st_mtime)
            except OSError:
                pass
        return time.time() - newest > 60


# --------------------------------------------------------------------------- #
# Game start screen: the picture Easy Anti-Cheat shows while Rocket League and Fortnite start
# --------------------------------------------------------------------------- #
class Splash(QObject):
    """Replaces EasyAntiCheat\\SplashScreen.png in the game folders with Rubenium's picture (the original is
    kept and comes back when the setting is switched off). A game update puts its own picture back, so this is
    checked again from time to time. Only this one picture is touched."""
    NAME = "SplashScreen.png"

    def __init__(self, cfg, rocket) -> None:
        super().__init__()
        self.cfg, self.rocket = cfg, rocket
        self._busy = False
        self._targets = None
        self._timer = QTimer(self)
        self._timer.setInterval(10 * 60 * 1000)
        self._timer.timeout.connect(self.sync)

    def start(self) -> None:
        QTimer.singleShot(6000, self.sync)
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    @staticmethod
    def source():
        for root in _swap_roots() + [_rl_store() / "swaps"]:
            f = root / "_splash" / Splash.NAME
            try:
                if f.is_file():
                    return f
            except OSError:
                continue
        return None

    def _roots(self) -> list:
        roots = [info.get("folder", "") for info in self.rocket.found.values()]
        program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        try:
            for item in (Path(program_data) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests").glob("*.item"):
                try:
                    data = json.loads(item.read_text(encoding="utf-8", errors="ignore"))
                except (OSError, ValueError):
                    continue
                if str(data.get("AppName", "")) == "Fortnite" or str(data.get("DisplayName", "")).lower() == "fortnite":
                    roots.append(str(data.get("InstallLocation", "")))
        except OSError:
            pass
        return [r for r in dict.fromkeys(roots) if r and os.path.isdir(r)]

    def _find(self) -> list:
        """Every EasyAntiCheat*\\SplashScreen.png in the game folders (a short search, a few folders deep)."""
        found = []
        skip = {"content", "paks", "cookedpcconsole", "movies", "localization", "engine", "plugins", "saved"}
        for root in self._roots():
            level = [root]
            for _depth in range(5):
                nxt = []
                for folder in level:
                    try:
                        with os.scandir(folder) as it:
                            for e in it:
                                if not e.is_dir(follow_symlinks=False):
                                    continue
                                low = e.name.lower()
                                if low.startswith("easyanticheat"):
                                    f = os.path.join(e.path, self.NAME)
                                    if os.path.isfile(f):
                                        found.append(f)
                                elif low not in skip:
                                    nxt.append(e.path)
                    except OSError:
                        continue
                level = nxt[:400]
        return list(dict.fromkeys(found))

    def sync(self) -> None:
        if self._busy or not win.IS_WIN:
            return
        self._busy = True
        import threading
        threading.Thread(target=self._work, args=(bool(self.cfg["splash"]),), daemon=True).start()

    def _work(self, on: bool) -> None:
        try:
            self.apply(on, self._find())
        except Exception as exc:  # noqa: BLE001
            log.debug("splash: %s", exc)
        finally:
            self._busy = False

    def apply(self, on: bool, targets: list) -> int:
        """Returns how many pictures were changed."""
        import hashlib
        src = self.source()
        if src is None:
            return 0
        ours = file_hash(src)
        keep = _rl_store().parent / "splash_originals"
        changed = 0
        for target in targets:
            backup = keep / (hashlib.sha1(os.path.normcase(target).encode("utf-8")).hexdigest()[:16] + ".png")
            try:
                current = file_hash(Path(target))
                if on and current != ours:
                    keep.mkdir(parents=True, exist_ok=True)
                    _atomic_copy(Path(target), backup)             # the game's own picture (also after an update)
                    _atomic_copy(src, Path(target))
                    changed += 1
                elif not on and current == ours and backup.is_file():
                    _atomic_copy(backup, Path(target))
                    changed += 1
            except OSError as exc:
                log.debug("splash %s: %s", target, exc)
        if changed:
            log.info("game start screen: %d picture(s) %s", changed, "set" if on else "restored")
        return changed


# --------------------------------------------------------------------------- #
# Crosshair library and share codes
# --------------------------------------------------------------------------- #
def _x(**kw) -> dict:
    return kw


SHAPE_KEYS = ("style", "length", "thickness", "gap", "dot", "dot_size", "radius")
_SHAPE0 = dict(style="cross", length=5, thickness=2, gap=3, dot=False, dot_size=2, radius=10)
# shapes only: colour, size and outline are your own settings and stay as they are
XHAIR_LIBRARY = [(name, {**_SHAPE0, **shape}) for name, shape in [
    ("Small cross", _x()),
    ("Cross", _x(length=8, gap=4)),
    ("Cross and dot", _x(length=6, gap=4, dot=True)),
    ("Dot", _x(style="dot", dot_size=4)),
    ("T", _x(style="tee", length=8, gap=3)),
    ("Circle", _x(style="circle", radius=8, length=0)),
]]
_CODE_KEYS = [("s", "style"), ("c", "color"), ("o", "opacity"), ("l", "length"), ("t", "thickness"), ("g", "gap"),
              ("d", "dot"), ("ds", "dot_size"), ("ol", "outline"), ("ow", "outline_w"), ("r", "radius"), ("z", "size")]
_LIMITS = {"opacity": (10, 100), "length": (0, 40), "thickness": (1, 10), "gap": (0, 30), "dot_size": (1, 12),
           "outline_w": (1, 4), "radius": (2, 60), "size": (50, 300)}


def xhair_encode(c: dict) -> str:
    data = {short: c[key] for short, key in _CODE_KEYS if key in c}
    raw = json.dumps(data, separators=(",", ":")).encode()
    return "RBX-" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def xhair_decode(text: str):
    """Crosshair settings from a share code, or None. Unknown fields are ignored, missing ones use defaults,
    so codes from older and newer versions keep working."""
    try:
        text = "".join((text or "").split())
        if not text.upper().startswith("RBX-"):
            return None
        body = text[4:]
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode("utf-8"))
        if not isinstance(data, dict):
            return None
        out: dict = {}
        for short, key in _CODE_KEYS:
            if short not in data:
                continue
            v = data[short]
            if key == "style" and v in ("cross", "tee", "dot", "circle"):
                out[key] = v
            elif key == "color" and isinstance(v, str) and QColor(v).isValid():
                out[key] = QColor(v).name().upper()
            elif key in ("dot", "outline") and isinstance(v, bool):
                out[key] = v
            elif key in _LIMITS and isinstance(v, (int, float)) and not isinstance(v, bool):
                lo, hi = _LIMITS[key]
                out[key] = int(max(lo, min(hi, v)))
        return out or None
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# Session stats (very light: one sample every 5 seconds)
# --------------------------------------------------------------------------- #
class Session(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.started = time.monotonic()
        self.cpu_peak = self.ram_peak = 0.0
        self.cpu_sum, self.n = 0.0, 0
        self.temp_peak = None
        self.ping_sum, self.ping_n = 0.0, 0
        self._ps = None
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._sample)
        self._timer.start()

    def _sample(self) -> None:
        try:
            if self._ps is None:
                import psutil
                self._ps = psutil
                psutil.cpu_percent(None)
                return
            cpu = self._ps.cpu_percent(None)
            self.cpu_peak = max(self.cpu_peak, cpu)
            self.cpu_sum += cpu
            self.n += 1
            self.ram_peak = max(self.ram_peak, self._ps.virtual_memory().percent)
        except Exception:  # noqa: BLE001
            self._timer.stop()

    def feed(self, d: dict) -> None:
        """Extra readings whenever the Stats page or the on-screen stats are sampling."""
        if d.get("temp") is not None:
            self.temp_peak = max(self.temp_peak or 0, d["temp"])
        if d.get("ping") is not None:
            self.ping_sum += d["ping"]
            self.ping_n += 1

    def duration(self) -> float:
        return time.monotonic() - self.started


def hours_text(seconds: float) -> str:
    h = seconds / 3600
    if h < 1:
        return f"{int(seconds // 60)} min"
    return f"{h:.1f} h" if h < 10 else f"{int(h)} h"


# --------------------------------------------------------------------------- #
# Updates from GitHub Releases
# --------------------------------------------------------------------------- #
UPDATE_REPO = "REMMETT-py/rubenium"
UPDATE_PAGE = f"https://github.com/{UPDATE_REPO}/releases/latest"


def version_tuple(text: str) -> tuple:
    import re
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:4]) if nums else (0,)


def app_home() -> Path:
    """A folder Windows always lets the app write to (used for downloads and, if needed, for the app itself)."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return Path(base) / "Rubenium"


def clean_env() -> dict:
    """Environment for starting another program: it must not inherit this app's packaging variables."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("_MEI", "_PYI"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


SETUP = "RubeniumSetup.exe"
SETUP_ARGS = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]


def run_setup(path: str, extra: str = "") -> bool:
    """Start the downloaded setup without any window. It waits for this app to close, installs over it and
    starts the new version. Returns False if it could not be started."""
    import subprocess
    args = [path, *SETUP_ARGS] + ([f"/RUBENIUMARGS={extra}"] if extra else [])
    try:
        subprocess.Popen(args, close_fds=True, env=clean_env(), cwd=os.path.dirname(path) or None)
        return True
    except OSError as exc:
        log.warning("could not start the setup: %s", exc)
        return False


class Updater(QObject):
    """Checks the latest GitHub release, downloads it, checks its SHA-256 and swaps the app in place.

    Release assets it understands: RubeniumSetup.exe (the installed app updates by running it silently, like
    any Windows program), Rubenium.py and swaps.zip (the script version), each with a matching .sha256 file.
    Nothing is run or installed unless its checksum matches."""
    found = pyqtSignal(dict)          # a newer version is out
    checked = pyqtSignal(bool, str)   # manual check finished: ok, message key ("latest" / "offline")
    progress = pyqtSignal(int)        # download percent
    failed = pyqtSignal(str)          # install failed: message key
    ready = pyqtSignal(str)           # installed: path to start

    def __init__(self, current: str) -> None:
        super().__init__()
        self.current = current
        self.latest: dict = {}
        self.busy = False
        self._timer = QTimer(self)
        self._timer.setInterval(6 * 3600 * 1000)
        self._timer.timeout.connect(lambda: self.check(manual=False))

    def start(self) -> None:
        self._timer.start()
        QTimer.singleShot(15000, lambda: self.check(manual=False))

    def stop(self) -> None:
        self._timer.stop()

    @staticmethod
    def _get(url: str, limit: int = 2_000_000, accept: str = "application/vnd.github+json") -> bytes:
        import ssl
        import urllib.request
        try:
            import certifi  # type: ignore
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:  # noqa: BLE001
            ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "Rubenium-updater", "Accept": accept})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:  # noqa: S310
            data = resp.read(limit + 1)
        if len(data) > limit:
            raise ValueError("response too large")
        return data

    def check(self, manual: bool = False) -> None:
        if self.busy:
            return
        self.busy = True
        import threading
        threading.Thread(target=self._check, args=(manual,), daemon=True).start()

    def _check(self, manual: bool) -> None:
        try:
            rel = json.loads(self._get(f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest").decode("utf-8"))
            tag = str(rel.get("tag_name", ""))
            assets = {str(a.get("name", "")): str(a.get("browser_download_url", ""))
                      for a in rel.get("assets", []) if isinstance(a, dict)}
            import re
            shown = re.search(r"Rubenium\s+v?(\d+(?:\.\d+)*)", str(rel.get("name", "")))   # "... Rubenium 1.0" -> 1.0
            info = {"version": tag.lstrip("vV"), "label": shown.group(1) if shown else tag.lstrip("vV"),
                    "page": str(rel.get("html_url", UPDATE_PAGE)), "assets": assets}
            self.busy = False
            # Releases are told apart by their tag, a date such as 2026.11.14.3, which only ever goes up.
            # (The title starts with the same date so that Rubenium 0.8 and 0.9, which read the title, update too.)
            if version_tuple(tag) > version_tuple(self.current):
                self.latest = info
                self.found.emit(info)
                if manual:
                    self.checked.emit(True, "found")
            elif manual:
                self.checked.emit(True, "latest")
        except Exception as exc:  # noqa: BLE001
            log.info("update check failed: %s", exc)
            self.busy = False
            if manual:
                self.checked.emit(False, "offline")

    # -- installing
    def install(self) -> bool:
        if self.busy or not self.latest:
            return False
        self.busy = True
        import threading
        threading.Thread(target=self._install, args=(dict(self.latest),), daemon=True).start()
        return True

    def _download(self, url: str, dest: Path, share: tuple) -> None:
        import urllib.request
        import ssl
        try:
            import certifi  # type: ignore
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:  # noqa: BLE001
            ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "Rubenium-updater"})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp, open(dest, "wb") as out:  # noqa: S310
            total = int(resp.headers.get("Content-Length") or 0)
            got, last = 0, -1
            while True:
                block = resp.read(1 << 16)
                if not block:
                    break
                got += len(block)
                if got > 400 * 1024 * 1024:
                    raise ValueError("download too large")
                out.write(block)
                if total:
                    pct = share[0] + int((share[1] - share[0]) * got / total)
                    if pct != last:
                        last = pct
                        self.progress.emit(pct)

    def _fetch_checked(self, assets: dict, name: str, dest: Path, share: tuple) -> bool:
        """Download `name` to `dest` and verify it against `name`.sha256. False if there is no checksum."""
        sha_url = assets.get(name + ".sha256")
        if not sha_url or not assets.get(name):
            return False
        want = self._get(sha_url, 10_000, "application/octet-stream").decode("utf-8", "ignore").split()[0].lower()
        if len(want) != 64:
            raise ValueError("bad checksum file")
        self._download(assets[name], dest, share)
        if file_hash(dest) != want:
            dest.unlink(missing_ok=True)
            raise ValueError("checksum mismatch")
        return True

    def _install(self, info: dict) -> None:
        import sys
        import zipfile
        assets = info["assets"]
        try:
            if getattr(sys, "frozen", False):
                work = app_home() / "update"                  # a folder Windows always lets us write to
                try:
                    work.mkdir(parents=True, exist_ok=True)
                except OSError:
                    import tempfile
                    work = Path(tempfile.gettempdir())
                setup = work / SETUP
                done = False
                for attempt in range(3):                      # a dropped connection is tried again
                    try:
                        done = self._fetch_checked(assets, SETUP, setup, (0, 100))
                        break
                    except (OSError, ValueError) as exc:
                        log.info("download attempt %d failed: %s", attempt + 1, exc)
                        if attempt == 2:
                            raise
                        time.sleep(2.0)
                if not done:
                    raise FileNotFoundError("no setup in release")
                self.busy = False
                self.ready.emit(str(setup))
            else:
                script = Path(sys.argv[0]).resolve()
                new = script.with_name(script.name + ".download")
                if not self._fetch_checked(assets, "Rubenium.py", new, (0, 70)):
                    raise FileNotFoundError("no script in release")
                zip_tmp = script.with_name("swaps.zip.download")
                if assets.get("swaps.zip") and self._fetch_checked(assets, "swaps.zip", zip_tmp, (70, 100)):
                    root = script.parent / "swaps"
                    with zipfile.ZipFile(zip_tmp) as z:
                        for member in z.infolist():
                            parts = Path(member.filename).parts
                            if (member.is_dir() or len(parts) != 3 or parts[0] != "swaps" or ".." in parts
                                    or not parts[2].lower().endswith((".upk", ".png", ".jpg", ".webp"))):
                                continue            # only swaps/<id>/<file>: game files and pictures
                            dest = root / parts[1] / parts[2]
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            tmp = dest.with_name(dest.name + ".part")
                            with z.open(member) as src, open(tmp, "wb") as out:
                                out.write(src.read())
                            os.replace(tmp, dest)
                    zip_tmp.unlink(missing_ok=True)
                os.replace(new, script)
                self.busy = False
                self.ready.emit(str(script))
        except PermissionError:
            self.busy = False
            self.failed.emit("blocked")
        except Exception as exc:  # noqa: BLE001
            log.warning("update failed: %s", exc)
            self.busy = False
            self.failed.emit("error")

    @staticmethod
    def cleanup() -> None:
        """Remove what an earlier update left behind."""
        import sys
        here = Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0]).resolve()
        junk = [here.parent / n for n in (here.stem + ".old.exe", here.stem + ".new.exe", here.stem + ".download",
                                          here.name + ".download", "swaps.zip.download")]
        junk += [app_home() / "update" / "Rubenium.download", app_home() / "update" / SETUP]
        for f in junk:
            try:
                f.unlink()
            except OSError:
                pass
        import shutil
        for old in ("app", "current"):                     # copies an older updater put there
            folder = app_home() / old
            if folder.is_dir() and not str(here).lower().startswith(str(folder).lower()):
                shutil.rmtree(folder, ignore_errors=True)


def restart(path: str, extra: tuple = ()) -> bool:
    """Start the (new) app again; the running copy then quits."""
    import subprocess
    import sys
    args = ["--updated", *extra]
    try:
        if getattr(sys, "frozen", False):
            subprocess.Popen([path, *args], close_fds=True, env=clean_env(), cwd=os.path.dirname(path) or None)
        else:
            exe = sys.executable
            pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
            subprocess.Popen([pyw if os.path.exists(pyw) else exe, path, *args], close_fds=True)
        return True
    except OSError as exc:
        log.warning("restart failed: %s", exc)
        return False


class TopApps(QObject):
    """Which apps use the most processor and memory, measured like Task Manager (processor = share of the whole
    PC, memory = private memory), grouped by app name and smoothed so the list does not jump around.
    On Windows one system call reads every process (about a millisecond), so measuring costs next to nothing.
    Rubenium itself is reported on its own line, not in the ranking."""
    ready = pyqtSignal(list, list, float, float)    # [(name, %)], [(name, bytes)], Rubenium %, Rubenium bytes
    HIDDEN = {"", "idle", "system idle process", "registry", "memory compression", "secure system"}

    def __init__(self) -> None:
        super().__init__()
        self._timer = QTimer(self)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(self._sample)
        self._last: dict = {}           # pid -> (name, processor time)
        self._t = 0.0
        self._smooth: dict = {}         # name -> smoothed %
        self._me = os.getpid()
        self._psutil_procs: dict = {}

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
            self._sample()
            QTimer.singleShot(500, self._sample)        # processor use needs two looks: numbers show quickly

    def stop(self) -> None:
        self._timer.stop()

    def _read(self):
        snap = win.process_snapshot()
        if snap is not None:
            return snap, 1e-7                          # processor time is in 100 ns steps
        try:                                           # other systems (and tests): psutil, slower but fine
            import psutil
            out = []
            for proc in psutil.process_iter(["pid", "name", "cpu_times", "memory_info"]):
                info = proc.info
                ct, mem = info.get("cpu_times"), info.get("memory_info")
                if ct is None:
                    continue
                out.append((info["pid"], info["name"] or "", ct.user + ct.system, getattr(mem, "rss", 0) if mem else 0))
            return out, 1.0
        except Exception:  # noqa: BLE001
            return [], 1.0

    def _sample(self) -> None:
        snap, unit = self._read()
        now = time.monotonic()
        wall = now - self._t if self._t else 0.0
        self._t = now
        cores = max(1, os.cpu_count() or 1)
        cpu: dict = {}
        ram: dict = {}
        seen: dict = {}
        me_cpu, me_ram = 0.0, 0.0
        for pid, name, used, mem in snap:
            seen[pid] = (name, used)
            label = name[:-4] if name.lower().endswith(".exe") else name
            if label.lower() in self.HIDDEN or not pid:
                continue
            prev = self._last.get(pid)
            pct = 0.0
            if prev is not None and prev[0] == name and wall > 0.2:
                pct = max(0.0, (used - prev[1]) * unit / (wall * cores) * 100.0)
            if pid == self._me:
                me_cpu, me_ram = pct, float(mem)
                continue
            cpu[label] = cpu.get(label, 0.0) + pct
            ram[label] = ram.get(label, 0) + mem
        self._last = seen
        if wall <= 0.2:
            return                                     # first look: nothing to compare with yet
        smooth = {}
        for label in set(cpu) | set(self._smooth):    # smooth: rises quickly, falls gently
            new, old = min(100.0, cpu.get(label, 0.0)), self._smooth.get(label, 0.0)
            v = old + (new - old) * (0.7 if new > old else 0.35)
            if v > 0.05 or label in cpu:
                smooth[label] = v
        self._smooth = smooth
        top_cpu = sorted(((n, v) for n, v in smooth.items() if n in cpu), key=lambda kv: kv[1], reverse=True)[:5]
        top_ram = sorted(ram.items(), key=lambda kv: kv[1], reverse=True)[:5]
        try:
            self.ready.emit(top_cpu, top_ram, me_cpu, me_ram)
        except RuntimeError:
            pass
