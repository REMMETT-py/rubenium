"""Badge pictures: 50 designs drawn from shapes, and how each colour (rarity) is painted.

Basic colours are matte. Rare colours are bright with a soft glow. Very rare colours (Titanium White, Black) are
metallic with a light that sweeps across them. Gold, the super rare one, shines, sweeps and sparkles."""
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QColor, QLinearGradient, QPainter, QPainterPath, QPainterPathStroker, QPen, QPolygonF,
                         QRadialGradient, QTransform)

from .wallet import VARIANT

_unit_cache: dict = {}
K = 100.0          # shapes are built 100x larger so that joining and cutting them keeps curves smooth


class _P(QPainterPath):
    """A path whose points are given in the -1..1 box."""

    def moveTo(self, x, y):
        super().moveTo(x * K, y * K)

    def lineTo(self, x, y):
        super().lineTo(x * K, y * K)

    def cubicTo(self, a, b, c, d, e, f):
        super().cubicTo(a * K, b * K, c * K, d * K, e * K, f * K)


def _p(*pts) -> QPainterPath:
    path = _P()
    path.addPolygon(QPolygonF([QPointF(x * K, y * K) for x, y in pts]))
    path.closeSubpath()
    return path


def _c(x: float, y: float, r: float, ry: float = 0.0) -> QPainterPath:
    path = _P()
    path.addEllipse(QPointF(x * K, y * K), r * K, (ry or r) * K)
    return path


def _r(x: float, y: float, w: float, h: float, rad: float = 0.0) -> QPainterPath:
    path = _P()
    path.addRoundedRect(QRectF(x * K, y * K, w * K, h * K), rad * K, rad * K)
    return path


def _ln(pts, width: float, curve: bool = False) -> QPainterPath:
    """A thick line through `pts` (or a curve when curve=True and 4 points are given)."""
    path = _P()
    path.moveTo(*pts[0])
    if curve:
        path.cubicTo(*pts[1], *pts[2], *pts[3])
    else:
        for pt in pts[1:]:
            path.lineTo(*pt)
    st = QPainterPathStroker()
    st.setWidth(width * K)
    st.setCapStyle(Qt.PenCapStyle.RoundCap)
    st.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return st.createStroke(path)


def _u(*paths) -> QPainterPath:
    out = QPainterPath()
    for path in paths:
        out = out.united(path)
    return out


def _star(n: int, r1: float, r2: float, turn: float = -90) -> QPainterPath:
    pts = []
    for k in range(n * 2):
        ang = math.radians(turn + 180 / n * k)
        rr = r1 if k % 2 == 0 else r2
        pts.append((rr * math.cos(ang), rr * math.sin(ang)))
    return _p(*pts)


def _heart() -> QPainterPath:
    path = _P()
    path.moveTo(0, 0.9)
    path.cubicTo(-1.5, -0.1, -0.7, -1.2, 0, -0.4)
    path.cubicTo(0.7, -1.2, 1.5, -0.1, 0, 0.9)
    return path


def _build(ident: str) -> QPainterPath:
    """The badge in a box from -1 to 1."""
    path = _P()
    if ident == "star":
        return _star(5, 1.0, 0.42)
    if ident == "bolt":
        return _p((0.25, -1), (-0.6, 0.15), (-0.05, 0.15), (-0.3, 1), (0.6, -0.2), (0.05, -0.2))
    if ident == "flame":
        path.moveTo(0, -1)
        path.cubicTo(0.9, -0.2, 0.75, 1, 0, 1)
        path.cubicTo(-0.75, 1, -0.9, 0.1, -0.3, -0.25)
        path.cubicTo(-0.1, 0.1, 0.15, -0.3, 0, -1)
        return path
    if ident == "heart":
        return _heart()
    if ident == "sun":
        rays = [_c(0.84 * math.cos(math.radians(45 * n)), 0.84 * math.sin(math.radians(45 * n)), 0.13) for n in range(8)]
        return _u(_c(0, 0, 0.5), *rays)
    if ident == "moon":
        return _c(0, 0, 0.9).subtracted(_c(0.42, -0.25, 0.78))
    if ident == "clover":
        return _u(_c(0, -0.45, 0.42), _c(-0.45, 0.1, 0.42), _c(0.45, 0.1, 0.42), _p((-0.08, 0.2), (0.08, 0.2), (0.2, 1), (0.02, 1)))
    if ident == "drop":
        path.moveTo(0, -1)
        path.cubicTo(0.15, -0.6, 0.75, -0.05, 0.75, 0.35)
        path.cubicTo(0.75, 0.8, 0.4, 1, 0, 1)
        path.cubicTo(-0.4, 1, -0.75, 0.8, -0.75, 0.35)
        path.cubicTo(-0.75, -0.05, -0.15, -0.6, 0, -1)
        return path.subtracted(_c(-0.32, 0.38, 0.12, 0.2))
    if ident == "leaf":
        path.moveTo(-0.8, 0.8)
        path.cubicTo(-0.9, -0.4, 0, -0.95, 0.9, -0.9)
        path.cubicTo(0.95, 0, 0.4, 0.85, -0.8, 0.8)
        return path.subtracted(_ln([(-0.45, 0.45), (0.55, -0.55)], 0.09)).united(_ln([(-0.8, 0.8), (-0.98, 0.98)], 0.12))
    if ident == "note":
        return _u(_c(-0.38, 0.58, 0.33, 0.27), _r(-0.13, -0.92, 0.15, 1.5), _p((-0.02, -0.92), (0.62, -0.62), (0.62, -0.3), (-0.02, -0.55)))
    if ident == "gamepad":
        body = _u(_r(-1, -0.5, 2, 0.95, 0.45), _c(-0.6, 0.32, 0.4), _c(0.6, 0.32, 0.4))
        return body.subtracted(_u(_r(-0.7, -0.07, 0.36, 0.13), _r(-0.585, -0.19, 0.13, 0.37), _c(0.42, -0.08, 0.1),
                                  _c(0.66, 0.12, 0.1)))
    if ident == "dice":
        pips = _u(*[_c(x, y, 0.15) for x, y in ((-0.42, -0.42), (0.42, 0.42), (0, 0), (0.42, -0.42), (-0.42, 0.42))])
        return _r(-0.85, -0.85, 1.7, 1.7, 0.3).subtracted(pips)
    if ident == "ghost":
        path.moveTo(-0.75, 0.9)
        path.lineTo(-0.75, -0.15)
        path.cubicTo(-0.75, -1.05, 0.75, -1.05, 0.75, -0.15)
        for x, y in ((0.75, 0.9), (0.5, 0.62), (0.25, 0.9), (0, 0.62), (-0.25, 0.9), (-0.5, 0.62)):
            path.lineTo(x, y)
        path.closeSubpath()
        return path.subtracted(_u(_c(-0.28, -0.2, 0.13, 0.18), _c(0.28, -0.2, 0.13, 0.18)))
    if ident == "alien":
        path.moveTo(-0.84, -0.2)
        path.cubicTo(-0.84, -1.12, 0.84, -1.12, 0.84, -0.2)
        path.cubicTo(0.84, 0.35, 0.3, 0.95, 0, 0.95)
        path.cubicTo(-0.3, 0.95, -0.84, 0.35, -0.84, -0.2)
        eyes = _u(_p((-0.62, -0.18), (-0.12, -0.02), (-0.18, 0.24), (-0.5, 0.14)),
                  _p((0.62, -0.18), (0.12, -0.02), (0.18, 0.24), (0.5, 0.14)))
        return path.subtracted(eyes)
    if ident == "mushroom":
        path.moveTo(-0.95, 0.05)
        path.cubicTo(-0.95, -1.0, 0.95, -1.0, 0.95, 0.05)
        path.closeSubpath()
        cap = path.subtracted(_u(_c(-0.42, -0.32, 0.16), _c(0.22, -0.52, 0.14), _c(0.55, -0.12, 0.11)))
        return cap.united(_r(-0.3, 0.12, 0.6, 0.83, 0.16))
    if ident == "cherry":
        return _u(_c(-0.42, 0.45, 0.38), _c(0.42, 0.56, 0.38), _ln([(-0.42, 0.1), (0.1, -0.85)], 0.11),
                  _ln([(0.42, 0.2), (0.1, -0.85)], 0.11), _p((0.1, -0.85), (0.6, -0.98), (0.38, -0.6)))
    if ident == "cube":
        hexa = _p((0, -1), (0.87, -0.5), (0.87, 0.5), (0, 1), (-0.87, 0.5), (-0.87, -0.5))
        return hexa.subtracted(_u(_ln([(0, 0), (-0.87, -0.5)], 0.11), _ln([(0, 0), (0.87, -0.5)], 0.11),
                                  _ln([(0, 0), (0, 1)], 0.11)))
    if ident == "headset":
        band = _ln([(-0.78, 0.15), (-0.78, -0.95), (0.78, -0.95), (0.78, 0.15)], 0.17, curve=True)
        return _u(band, _r(-1, -0.05, 0.42, 0.8, 0.16), _r(0.58, -0.05, 0.42, 0.8, 0.16),
                  _ln([(0.72, 0.62), (0.6, 0.95), (0.05, 0.95)], 0.09))
    if ident == "spade":
        top = _P()
        top.moveTo(0, -1)
        top.cubicTo(0.25, -0.62, 0.9, -0.35, 0.9, 0.12)
        top.lineTo(-0.9, 0.12)
        top.cubicTo(-0.9, -0.35, -0.25, -0.62, 0, -1)
        return _u(top, _c(-0.46, 0.18, 0.44, 0.38), _c(0.46, 0.18, 0.44, 0.38), _p((0, 0.2), (0.36, 0.98), (-0.36, 0.98)))
    if ident == "club":
        return _u(_c(0, -0.47, 0.37), _c(-0.47, 0.13, 0.37), _c(0.47, 0.13, 0.37), _c(0, 0, 0.22),
                  _p((0, 0.1), (0.32, 0.98), (-0.32, 0.98)))
    if ident == "cat":
        head = _u(_c(0, 0.18, 0.86, 0.74), _p((-0.82, -0.12), (-0.68, -0.98), (-0.18, -0.5)),
                  _p((0.82, -0.12), (0.68, -0.98), (0.18, -0.5)))
        return head.subtracted(_u(_c(-0.33, 0.08, 0.12, 0.17), _c(0.33, 0.08, 0.12, 0.17),
                                  _p((-0.11, 0.36), (0.11, 0.36), (0, 0.49))))
    if ident == "paw":
        return _u(_c(0, 0.45, 0.5, 0.42), _c(-0.66, -0.08, 0.21, 0.24), _c(-0.25, -0.52, 0.22, 0.26),
                  _c(0.25, -0.52, 0.22, 0.26), _c(0.66, -0.08, 0.21, 0.24))
    if ident == "fish":
        return _u(_c(-0.18, 0, 0.66, 0.46), _p((0.32, 0), (0.98, -0.52), (0.98, 0.52))).subtracted(_c(-0.48, -0.1, 0.1))
    if ident == "feather":
        path.moveTo(0.85, -0.95)
        path.cubicTo(-0.25, -0.8, -0.78, 0.1, -0.6, 0.75)
        path.cubicTo(0.1, 0.62, 0.82, -0.1, 0.85, -0.95)
        return path.subtracted(_ln([(0.7, -0.78), (-0.5, 0.62)], 0.07)).united(_ln([(-0.55, 0.68), (-0.9, 1.0)], 0.1))
    if ident == "wing":
        path.moveTo(-0.95, -0.5)
        path.cubicTo(-0.2, -0.95, 0.8, -0.78, 0.98, -0.22)
        for x, y in ((0.52, -0.06), (0.86, 0.2), (0.38, 0.36), (0.64, 0.62), (0.12, 0.7), (0.32, 0.96)):
            path.lineTo(x, y)
        path.cubicTo(-0.5, 0.92, -0.98, 0.2, -0.95, -0.5)
        return path
    if ident == "tree":
        return _u(_p((0, -1), (0.55, -0.32), (-0.55, -0.32)), _p((0, -0.62), (0.75, 0.24), (-0.75, 0.24)),
                  _p((0, -0.2), (0.92, 0.68), (-0.92, 0.68)), _r(-0.13, 0.6, 0.26, 0.38))
    if ident == "mountain":
        hill = _p((-1, 0.8), (-0.35, -0.42), (-0.1, -0.04), (0.3, -0.78), (1, 0.8))
        return hill.subtracted(_ln([(0.06, -0.36), (0.18, -0.26), (0.3, -0.42), (0.42, -0.26), (0.53, -0.38)], 0.08))
    if ident == "wave":
        path.moveTo(-1, 0.85)
        path.lineTo(-1, 0.2)
        path.cubicTo(-0.6, -0.9, 0.6, -1.0, 0.88, -0.2)
        path.cubicTo(0.5, -0.6, 0.02, -0.42, 0.1, 0.05)
        path.cubicTo(0.15, 0.4, 0.6, 0.35, 1, 0.2)
        path.lineTo(1, 0.85)
        path.closeSubpath()
        return path
    if ident == "snowflake":
        parts = []
        for k in range(6):
            a = math.radians(60 * k - 90)
            ex, ey = 0.95 * math.cos(a), 0.95 * math.sin(a)
            parts.append(_ln([(0, 0), (ex, ey)], 0.13))
            mx, my = 0.55 * math.cos(a), 0.55 * math.sin(a)
            for side in (-1, 1):
                b = a + side * math.radians(42)
                parts.append(_ln([(mx, my), (mx + 0.3 * math.cos(b), my + 0.3 * math.sin(b))], 0.11))
        return _u(*parts)
    if ident == "eye":
        path.moveTo(-1, 0)
        path.cubicTo(-0.5, -0.78, 0.5, -0.78, 1, 0)
        path.cubicTo(0.5, 0.78, -0.5, 0.78, -1, 0)
        return path.subtracted(_c(0, 0, 0.42)).united(_c(0, 0, 0.24))
    if ident == "sword":
        upright = _u(_p((0, -1), (0.12, -0.85), (0.12, 0.35), (-0.12, 0.35), (-0.12, -0.85)),
                     _r(-0.45, 0.35, 0.9, 0.14, 0.06), _r(-0.07, 0.49, 0.14, 0.32), _c(0, 0.88, 0.12))
        return QTransform().rotate(45).scale(1.12, 1.12).map(upright)
    if ident == "axe":
        head = _P()
        head.moveTo(0.08, -0.95)
        head.cubicTo(0.72, -0.98, 1.02, -0.42, 0.86, 0.08)
        head.lineTo(0.16, -0.3)
        head.closeSubpath()
        return _u(_ln([(-0.62, 0.95), (0.3, -0.72)], 0.15), head)
    if ident == "shield":
        path.moveTo(0, -1)
        path.lineTo(0.85, -0.65)
        path.cubicTo(0.85, 0.3, 0.45, 0.8, 0, 1)
        path.cubicTo(-0.45, 0.8, -0.85, 0.3, -0.85, -0.65)
        path.closeSubpath()
        return path.subtracted(_ln([(0, -0.62), (0, 0.6)], 0.09))
    if ident == "skull":
        head = _u(_c(0, -0.16, 0.78, 0.74), _r(-0.44, 0.28, 0.88, 0.66, 0.16))
        return head.subtracted(_u(_c(-0.3, -0.1, 0.2, 0.22), _c(0.3, -0.1, 0.2, 0.22), _p((0, 0.12), (0.11, 0.32), (-0.11, 0.32)),
                                  _r(-0.2, 0.64, 0.07, 0.32), _r(-0.035, 0.64, 0.07, 0.32), _r(0.13, 0.64, 0.07, 0.32)))
    if ident == "bomb":
        ball = _c(-0.12, 0.2, 0.72).subtracted(_c(-0.4, -0.06, 0.12, 0.09))
        return _u(ball, _p((0.16, -0.5), (0.43, -0.78), (0.68, -0.54), (0.41, -0.26)),
                  _ln([(0.56, -0.66), (0.66, -0.86), (0.82, -0.86), (0.92, -0.98)], 0.08, curve=True))
    if ident == "crosshair":
        ring = _c(0, 0, 0.74).subtracted(_c(0, 0, 0.58))
        return _u(ring, _r(-0.07, -1, 0.14, 0.44), _r(-0.07, 0.56, 0.14, 0.44), _r(-1, -0.07, 0.44, 0.14),
                  _r(0.56, -0.07, 0.44, 0.14), _c(0, 0, 0.12))
    if ident == "target":
        return _u(_c(0, 0, 0.96).subtracted(_c(0, 0, 0.76)), _c(0, 0, 0.56).subtracted(_c(0, 0, 0.37)), _c(0, 0, 0.18))
    if ident == "shuriken":
        return _star(4, 1.0, 0.3, -90).subtracted(_c(0, 0, 0.13))
    if ident == "trident":
        return _u(_r(-0.07, -0.4, 0.14, 1.38), _r(-0.07, -0.82, 0.14, 0.5), _p((0, -1.0), (0.16, -0.78), (-0.16, -0.78)),
                  _r(-0.62, -0.7, 0.13, 0.45), _p((-0.555, -0.96), (-0.7, -0.68), (-0.41, -0.68)),
                  _r(0.49, -0.7, 0.13, 0.45), _p((0.555, -0.96), (0.7, -0.68), (0.41, -0.68)), _r(-0.62, -0.32, 1.24, 0.14, 0.06))
    if ident == "anchor":
        ring = _c(0, -0.76, 0.21).subtracted(_c(0, -0.76, 0.1))
        arc = _ln([(-0.74, 0.2), (-0.62, 0.95), (0.62, 0.95), (0.74, 0.2)], 0.14, curve=True)
        return _u(ring, _r(-0.07, -0.56, 0.14, 1.42), _r(-0.45, -0.4, 0.9, 0.13, 0.06), arc,
                  _p((-0.74, 0.04), (-0.94, 0.36), (-0.54, 0.36)), _p((0.74, 0.04), (0.94, 0.36), (0.54, 0.36)))
    if ident == "crown":
        return _p((-1, 0.65), (-1, -0.55), (-0.45, 0.0), (0, -0.8), (0.45, 0.0), (1, -0.55), (1, 0.65)).subtracted(
            _r(-0.75, 0.3, 1.5, 0.1))
    if ident == "trophy":
        cup = _P()
        cup.moveTo(-0.6, -0.9)
        cup.lineTo(0.6, -0.9)
        cup.cubicTo(0.6, 0.1, 0.3, 0.3, 0, 0.3)
        cup.cubicTo(-0.3, 0.3, -0.6, 0.1, -0.6, -0.9)
        handles = [_c(s * 0.72, -0.45, 0.26, 0.3).subtracted(_c(s * 0.72, -0.45, 0.12, 0.15)) for s in (-1, 1)]
        return _u(cup, _p((-0.1, 0.25), (0.1, 0.25), (0.1, 0.7), (0.45, 0.7), (0.45, 0.95), (-0.45, 0.95), (-0.45, 0.7),
                          (-0.1, 0.7)), *handles)
    if ident == "diamond":
        gem = _p((-0.55, -0.7), (0.55, -0.7), (1, -0.15), (0, 0.95), (-1, -0.15))
        return gem.subtracted(_ln([(-0.92, -0.15), (0.92, -0.15)], 0.07))
    if ident == "gem":
        octo = _p((-0.5, -0.88), (0.5, -0.88), (0.9, -0.42), (0.9, 0.42), (0.5, 0.88), (-0.5, 0.88), (-0.9, 0.42), (-0.9, -0.42))
        inner = [(-0.26, -0.48), (0.26, -0.48), (0.48, -0.22), (0.48, 0.22), (0.26, 0.48), (-0.26, 0.48), (-0.48, 0.22),
                 (-0.48, -0.22), (-0.26, -0.48)]
        return octo.subtracted(_ln(inner, 0.08))
    if ident == "rocket":
        body = _P()
        body.moveTo(0, -1)
        body.cubicTo(0.6, -0.4, 0.42, 0.3, 0.3, 0.55)
        body.lineTo(-0.3, 0.55)
        body.cubicTo(-0.42, 0.3, -0.6, -0.4, 0, -1)
        body = body.subtracted(_c(0, -0.3, 0.14))
        return _u(body, _p((-0.3, 0.2), (-0.75, 0.8), (-0.3, 0.55)), _p((0.3, 0.2), (0.75, 0.8), (0.3, 0.55)),
                  _p((-0.14, 0.62), (0.14, 0.62), (0, 1)))
    if ident == "planet":
        tilt = QTransform().rotate(-22)
        outer, inner = tilt.map(_c(0, 0, 1.0, 0.34)), tilt.map(_c(0, 0, 0.8, 0.2))
        ring = outer.subtracted(inner)
        gap = QPainterPathStroker()
        gap.setWidth(0.16 * K)
        ball = _c(0, 0, 0.56).subtracted(gap.createStroke(outer))
        front = ring.subtracted(_r(-1.2, -1.2, 2.4, 1.2).subtracted(_r(-1.2, -1.2, 0.0, 0.0)))
        back = ring.subtracted(_c(0, 0, 0.64))
        return _u(ball, front, back)
    if ident == "comet":
        tail = _p((0.02, -0.8), (-0.96, 0.96), (0.8, -0.02))
        return _u(_c(0.44, -0.44, 0.44), tail).subtracted(_ln([(0.08, -0.2), (-0.5, 0.5)], 0.06))
    if ident == "key":
        bow = _c(-0.45, -0.45, 0.42).subtracted(_c(-0.45, -0.45, 0.17))
        return _u(bow, _ln([(-0.16, -0.16), (0.86, 0.86)], 0.17), _ln([(0.42, 0.42), (0.22, 0.62)], 0.15),
                  _ln([(0.66, 0.66), (0.46, 0.86)], 0.15))
    if ident == "rook":
        return _p((-0.6, -0.95), (-0.35, -0.95), (-0.35, -0.7), (-0.12, -0.7), (-0.12, -0.95), (0.12, -0.95), (0.12, -0.7),
                  (0.35, -0.7), (0.35, -0.95), (0.6, -0.95), (0.6, -0.45), (0.42, -0.3), (0.42, 0.45), (0.7, 0.65),
                  (0.7, 0.95), (-0.7, 0.95), (-0.7, 0.65), (-0.42, 0.45), (-0.42, -0.3), (-0.6, -0.45))
    if ident == "hourglass":
        glass = _p((-0.7, -1), (0.7, -1), (0.7, -0.84), (0.6, -0.84), (0.6, -0.6), (0.12, 0), (0.6, 0.6), (0.6, 0.84),
                   (0.7, 0.84), (0.7, 1), (-0.7, 1), (-0.7, 0.84), (-0.6, 0.84), (-0.6, 0.6), (-0.12, 0), (-0.6, -0.6),
                   (-0.6, -0.84), (-0.7, -0.84))
        return glass.subtracted(_p((-0.44, -0.72), (0.44, -0.72), (0.3, -0.5), (-0.3, -0.5)))
    return _c(0, 0, 0.8)


def unit_path(ident: str) -> QPainterPath:
    if ident not in _unit_cache:
        _unit_cache[ident] = QTransform().scale(1 / K, 1 / K).map(_build(ident))
    return _unit_cache[ident]


def badge_path(ident: str, rect: QRectF) -> QPainterPath:
    u = min(rect.width(), rect.height()) / 2
    return QTransform().translate(rect.center().x(), rect.center().y()).scale(u, u).map(unit_path(ident))


def animated(var: str) -> bool:
    """Does this colour move (and need repainting)?"""
    return VARIANT.get(var, ("", "", "basic"))[2] in ("very", "super")


def _sparkle(p: QPainter, c: QPointF, r: float, colour: QColor) -> None:
    star = QPainterPath()
    for k in range(8):
        ang = math.radians(45 * k)
        rr = r if k % 2 == 0 else r * 0.26
        pt = QPointF(c.x() + rr * math.cos(ang), c.y() + rr * math.sin(ang))
        star.lineTo(pt) if k else star.moveTo(pt)
    star.closeSubpath()
    p.setBrush(colour)
    p.drawPath(star)


def paint_badge(p: QPainter, ident: str, rect: QRectF, var: str = "grey", now: float = 0.0, effects: bool = True,
                dim: float = 1.0) -> None:
    """Draw badge `ident` in colour `var` inside `rect`. `effects` adds the glow, shine and sparkles of the rarer
    colours (off for tiny sizes). `dim` < 1 draws it faded (not owned)."""
    v = VARIANT.get(var) or VARIANT["grey"]
    _vid, _name, rarity, main, light = v
    path = badge_path(ident, rect)
    u = min(rect.width(), rect.height()) / 2
    box = path.boundingRect()
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setOpacity(p.opacity() * dim)
    p.setPen(Qt.PenStyle.NoPen)
    if effects and rarity in ("rare", "super") and dim >= 1.0:          # soft glow behind
        halo = QColor(main)
        for w, a in ((u * 0.42, 0.10), (u * 0.22, 0.18)):
            halo.setAlphaF(a)
            pen = QPen(halo, w)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
    g = QLinearGradient(box.topLeft(), box.bottomLeft())
    if rarity == "super":
        g = QLinearGradient(box.topLeft(), box.bottomRight())
        g.setColorAt(0.0, QColor("#FFF6D8"))
        g.setColorAt(0.45, QColor(main))
        g.setColorAt(1.0, QColor("#9C7424"))
    elif var == "titanium":
        g.setColorAt(0.0, QColor("#FFFFFF"))
        g.setColorAt(1.0, QColor("#BFC6CD"))
    elif var == "black":
        g.setColorAt(0.0, QColor("#30363C"))
        g.setColorAt(1.0, QColor("#08090A"))
    elif rarity == "rare":
        g.setColorAt(0.0, QColor(light))
        g.setColorAt(0.55, QColor(main))
        g.setColorAt(1.0, QColor(main))
    else:
        g.setColorAt(0.0, QColor(light))
        g.setColorAt(1.0, QColor(main))
    p.setBrush(g)
    p.drawPath(path)
    if rarity == "very":                                    # a thin rim that catches the light
        rim = QColor("#FFFFFF") if var == "black" else QColor("#8D969F")
        rim.setAlphaF(0.55 if var == "black" else 0.7)
        p.setPen(QPen(rim, max(0.8, u * 0.06)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
    if effects and rarity in ("very", "super") and dim >= 1.0:          # light sweeping across
        period = 2.6 if rarity == "super" else 3.4
        t = (now % period) / period
        x = box.left() - box.width() + t * box.width() * 3
        band = QLinearGradient(QPointF(x, box.top()), QPointF(x + box.width() * 0.6, box.bottom()))
        shine = QColor("#FFFFFF")
        band.setColorAt(0.0, QColor(255, 255, 255, 0))
        shine.setAlphaF(0.75 if rarity == "super" else (0.55 if var == "black" else 0.85))
        band.setColorAt(0.5, shine)
        band.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.save()
        p.setClipPath(path)
        p.fillRect(box.adjusted(-2, -2, 2, 2), band)
        p.restore()
    if effects and rarity == "super" and dim >= 1.0:          # twinkling stars around it
        seed = sum(ord(ch) for ch in ident)
        for k in range(4):
            phase = (now * 0.9 + k * 0.27 + seed * 0.013) % 1.0
            tw = math.sin(phase * math.pi)
            ang = math.radians(seed * 37 + k * 97)
            dist = u * (0.95 + 0.12 * (k % 2))
            c = QPointF(rect.center().x() + dist * math.cos(ang), rect.center().y() + dist * math.sin(ang))
            col = QColor("#FFF6D8")
            col.setAlphaF(max(0.0, tw))
            _sparkle(p, c, u * (0.16 + 0.08 * tw), col)
    if effects and var == "black" and dim >= 1.0:              # tiny white glints for black
        for k in range(2):
            phase = (now * 0.7 + k * 0.5) % 1.0
            tw = max(0.0, math.sin(phase * math.pi))
            c = QPointF(box.left() + box.width() * (0.28 + 0.44 * k), box.top() + box.height() * (0.3 + 0.35 * k))
            col = QColor("#FFFFFF")
            col.setAlphaF(tw * 0.9)
            _sparkle(p, c, u * 0.14 * (0.6 + 0.4 * tw), col)
    if effects and var == "titanium" and dim >= 1.0:           # a soft cool aura
        aura = QRadialGradient(rect.center(), u * 1.25)
        aura.setColorAt(0.6, QColor(220, 235, 255, 0))
        aura.setColorAt(0.85, QColor(220, 235, 255, 22))
        aura.setColorAt(1.0, QColor(220, 235, 255, 0))
        p.setBrush(aura)
        p.drawEllipse(rect.center(), u * 1.25, u * 1.25)
    p.restore()
