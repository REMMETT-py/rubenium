"""Shop cosmetics: 10 balls, 10 song lines, 5 fonts and 6 themes. They are bought with coins, can be traded and
sold, and never look like the progression unlocks (no White Gold, no Gold progression look).

An item is named like the server names it: "ball:orbit:blue", "line:dash:red", "font:mono:white", "theme:ocean"."""
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen

from .core import TEXT, alpha, font, mix, tr

SHOP_COLOURS = {"grey": "#9AA4AD", "blue": "#4B6BFF", "green": "#2ECC71", "red": "#FF4B4B", "yellow": "#F4F04A",
                "orange": "#FF8A3D", "brown": "#A8744C", "teal": "#1ABC9C", "lava": "#FF3D1F", "purple": "#9B5CFF",
                "sky": "#2EC5FF", "lime": "#8CFF2E", "pink": "#FF5CB8", "beam": "#E8FF3A", "black": "#2A3037",
                "white": "#FFFFFF", "gold": "#E8C26A"}
COLOUR_ORDER = ["grey", "blue", "green", "red", "yellow", "orange", "brown", "teal", "lava", "purple", "sky", "lime",
                "pink", "beam", "black", "white"]
COLOUR_NAMES = {"grey": "Grey", "blue": "Blue", "green": "Green", "red": "Red", "yellow": "Yellow", "orange": "Orange",
                "brown": "Brown", "teal": "Teal", "lava": "Lava Red", "purple": "Purple", "sky": "Sky Blue",
                "lime": "Juicy Lime", "pink": "Pink", "beam": "Yellow Beam", "black": "Black", "white": "White",
                "gold": "Gold"}
BALLS = [("orbit", "Orbit"), ("pixel", "Pixel"), ("split", "Split"), ("halo", "Halo"), ("bubble", "Bubble"),
         ("spiral", "Spiral"), ("bullseye", "Bullseye"), ("hex", "Hex"), ("ripple", "Ripple"), ("shard", "Shard")]
LINES = [("dash", "Dash"), ("beads", "Beads"), ("zigzag", "Zigzag"), ("twin", "Twin"), ("pulse", "Pulse"),
         ("chain", "Chain"), ("ribbon", "Ribbon"), ("steps", "Steps"), ("spark", "Spark"), ("laser", "Laser")]
FONTS = [("rounded", "Rounded", ["Trebuchet MS", "Verdana"]), ("mono", "Mono", ["Cascadia Mono", "Consolas", "Courier New"]),
         ("serif", "Serif", ["Georgia", "Cambria", "Times New Roman"]), ("display", "Display", ["Bahnschrift", "Impact"]),
         ("script", "Script", ["Segoe Print", "Segoe Script", "Comic Sans MS"])]
# shop themes: two fixed colours and their own night sky (name, colour 1, colour 2, sky settings)
THEME_LOOKS = [("sunset", "Sunset", "#FF8A3D", "#FF3D7F", dict(glow=2, stars=22, comets=2, sparkles=4)),
               ("ocean", "Ocean", "#2D9CFF", "#1ABC9C", dict(glow=2, stars=30, aurora=True, sparkles=3)),
               ("forest", "Forest", "#2ECC71", "#A6E22E", dict(glow=2, stars=26, links=6, sparkles=5)),
               ("candy", "Candy", "#FF5CB8", "#9B5CFF", dict(glow=3, stars=18, sparkles=11)),
               ("storm", "Storm", "#8FA8FF", "#4B6BFF", dict(glow=3, stars=44, links=10, comets=6, aurora=True)),
               ("retro", "Retro", "#D94BFF", "#35D6E6", dict(glow=3, stars=52, links=14, sparkles=8, edge="shine"))]
KIND_NAMES = {"ball": "Ball", "line": "Line", "font": "Font", "theme": "Theme", "badge": "Badge"}
_NAMES = {"ball": dict(BALLS), "line": dict(LINES), "font": {f[0]: f[1] for f in FONTS},
          "theme": {t[0]: t[1] for t in THEME_LOOKS}}
_themes: dict = {}


def parts(item: str) -> tuple:
    bits = (item or "").split(":") + ["", "", ""]
    return bits[0], bits[1], bits[2]


def colour_of(item: str) -> QColor:
    return QColor(SHOP_COLOURS.get(parts(item)[2], "#FFFFFF"))


def item_name(item: str) -> str:
    """"Orbit ball · Blue", "Ocean theme"... (badges are named in collection.py)."""
    kind, base, var = parts(item)
    if kind == "badge":
        from .collection import badge_label
        return badge_label(item)
    name = f"{tr(_NAMES.get(kind, {}).get(base, base.capitalize()))} ({tr(KIND_NAMES.get(kind, kind)).lower()})"
    return name + (f" · {tr(COLOUR_NAMES.get(var, var))}" if var else "")


def shop_theme(ident: str):
    """The theme dict (same shape as extras.THEMES) of a shop theme, e.g. "theme:ocean"."""
    if not _themes:
        from .extras import _theme
        for tid, name, c1, c2, sky in THEME_LOOKS:
            th = _theme("theme:" + tid, name, 0, **sky)
            th["tint"] = (c1, c2)
            _themes["theme:" + tid] = th
    return _themes.get(ident)


def font_families(item: str) -> list:
    base = parts(item)[1]
    return next((list(f[2]) for f in FONTS if f[0] == base), [])


# --------------------------------------------------------------------------- #
# Balls: the R in the item's colour, with a design around it
# --------------------------------------------------------------------------- #
def _r_text(p: QPainter, box: QRectF, d: float, col: QColor, dark: bool) -> None:
    f = font(20, QFont.Weight.ExtraBold)
    f.setPixelSize(max(8, int(d * 0.46)))
    p.setFont(f)
    centre = int(Qt.AlignmentFlag.AlignCenter)
    p.setPen(alpha("#FFFFFF" if dark else col, 0.45))
    p.drawText(box.translated(0, d * 0.022), centre, "R")
    p.setPen(col if not dark else QColor("#C9D2DA"))
    p.drawText(box, centre, "R")


def paint_shop_ball(p: QPainter, box: QRectF, d: float, item: str, now: float = 0.0) -> None:
    _k, design, var = parts(item)
    col = colour_of(item)
    dark = var == "black"
    line = QColor("#AEB8C2") if dark else col
    c = box.center()
    r = d / 2
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if design == "orbit":
        p.setPen(QPen(alpha(line, 0.45), max(1.0, d * 0.02)))
        p.save()
        p.translate(c)
        p.rotate(-24)
        p.drawEllipse(QPointF(0, 0), r * 0.74, r * 0.34)
        ang = now * 1.6
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(line)
        p.drawEllipse(QPointF(r * 0.74 * math.cos(ang), r * 0.34 * math.sin(ang)), d * 0.045, d * 0.045)
        p.restore()
    elif design == "pixel":
        p.setPen(Qt.PenStyle.NoPen)
        s = d * 0.075
        for k, (dx, dy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1), (-1.45, 0), (1.45, 0))):
            p.setBrush(alpha(line, 0.85 if k < 4 else 0.45))
            p.drawRect(QRectF(c.x() + dx * r * 0.5 - s / 2, c.y() + dy * r * 0.5 - s / 2, s, s))
    elif design == "halo":
        p.setPen(QPen(line, max(1.4, d * 0.04), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(c.x() - r * 0.5, c.y() - r * 0.82, r, r * 0.36), 0, 180 * 16)
        p.setPen(QPen(alpha(line, 0.35), max(1.0, d * 0.02)))
        p.drawArc(QRectF(c.x() - r * 0.5, c.y() - r * 0.82, r, r * 0.36), 180 * 16, 180 * 16)
    elif design == "bubble":
        for k, (dx, dy, rr) in enumerate(((-0.52, 0.44, 0.15), (0.56, -0.38, 0.19), (0.5, 0.5, 0.09), (-0.5, -0.5, 0.08))):
            bob = math.sin(now * 1.3 + k * 1.7) * d * 0.015
            p.setPen(QPen(alpha(line, 0.75), max(1.0, d * 0.018)))
            p.setBrush(alpha(line, 0.16))
            p.drawEllipse(QPointF(c.x() + dx * r, c.y() + dy * r + bob), rr * r, rr * r)
    elif design == "spiral":
        path = QPainterPath()
        for n in range(64):
            t = n / 63
            ang = t * 4.2 * math.pi + now * 0.5
            pt = QPointF(c.x() + r * 0.8 * t * math.cos(ang), c.y() + r * 0.8 * t * math.sin(ang))
            path.lineTo(pt) if n else path.moveTo(pt)
        p.setPen(QPen(alpha(line, 0.42), max(1.0, d * 0.022), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPath(path)
    elif design == "bullseye":
        for k, rr in enumerate((0.78, 0.6)):
            p.setPen(QPen(alpha(line, 0.6 - 0.25 * k), max(1.0, d * (0.03 - 0.008 * k))))
            p.drawEllipse(c, r * rr, r * rr)
    elif design == "hex":
        path = QPainterPath()
        for n in range(7):
            ang = math.radians(60 * n + now * 6)
            pt = QPointF(c.x() + r * 0.78 * math.cos(ang), c.y() + r * 0.78 * math.sin(ang))
            path.lineTo(pt) if n else path.moveTo(pt)
        p.setPen(QPen(alpha(line, 0.7), max(1.2, d * 0.03), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
    elif design == "ripple":
        for k in range(3):
            t = (now * 0.35 + k / 3) % 1.0
            p.setPen(QPen(alpha(line, 0.7 * (1 - t)), max(1.0, d * 0.024)))
            p.drawEllipse(c, r * (0.3 + 0.55 * t), r * (0.3 + 0.55 * t))
    elif design == "shard":
        p.setPen(Qt.PenStyle.NoPen)
        for k in range(6):
            ang = math.radians(60 * k + 15)
            tip = QPointF(c.x() + r * 0.86 * math.cos(ang), c.y() + r * 0.86 * math.sin(ang))
            a1, a2 = ang - 0.2, ang + 0.2
            tri = QPainterPath()
            tri.moveTo(tip)
            tri.lineTo(c.x() + r * 0.6 * math.cos(a1), c.y() + r * 0.6 * math.sin(a1))
            tri.lineTo(c.x() + r * 0.6 * math.cos(a2), c.y() + r * 0.6 * math.sin(a2))
            tri.closeSubpath()
            p.setBrush(alpha(line, 0.85 if k % 2 == 0 else 0.4))
            p.drawPath(tri)
    if design == "split":                                # the R in two halves: colour above, white below
        for top in (True, False):
            p.save()
            p.setClipRect(QRectF(box.left(), box.top() if top else c.y(), box.width(), box.height() / 2))
            _r_text(p, box, d, col if top else QColor(TEXT), dark and top)
            p.restore()
        p.setPen(QPen(alpha(line, 0.5), max(1.0, d * 0.016)))
        p.drawLine(QPointF(c.x() - r * 0.7, c.y()), QPointF(c.x() + r * 0.7, c.y()))
    else:
        _r_text(p, box, d, col, dark)
    p.restore()


# --------------------------------------------------------------------------- #
# Lines: the song-progress ring of the ball
# --------------------------------------------------------------------------- #
def _arc_points(ring: QRectF, frac: float, step_deg: float, wobble=None) -> list:
    c, r = ring.center(), ring.width() / 2
    n = max(2, int(360 * frac / step_deg) + 1)
    out = []
    for i in range(n):
        deg = min(360 * frac, i * step_deg)
        ang = math.radians(90 - deg)
        rr = r + (wobble(i) if wobble else 0.0)
        out.append(QPointF(c.x() + rr * math.cos(ang), c.y() - rr * math.sin(ang)))
    return out


def paint_shop_ring(p: QPainter, ring: QRectF, item: str, frac: float, width: float, now: float = 0.0) -> None:
    _k, design, var = parts(item)
    col = QColor("#8C96A0") if var == "black" else colour_of(item)
    frac = max(0.0, min(1.0, frac))
    span = int(-360 * 16 * frac)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(alpha("#FFFFFF", 0.10), width))
    p.drawEllipse(ring)
    if frac <= 0.0:
        return p.restore()
    round_pen = lambda c, w: QPen(c, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)      # noqa: E731
    if design in ("dash", "chain", "steps"):
        pen = QPen(col, width * (1.5 if design == "steps" else 1.0), Qt.PenStyle.CustomDashLine, Qt.PenCapStyle.FlatCap)
        pen.setDashPattern({"dash": [3.0, 2.0], "chain": [4.0, 1.4, 1.0, 1.4], "steps": [1.6, 1.0]}[design])
        p.setPen(pen)
        p.drawArc(ring, 90 * 16, span)
    elif design == "beads":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        for pt in _arc_points(ring, frac, 14):
            p.drawEllipse(pt, width * 0.8, width * 0.8)
    elif design == "zigzag":
        pts = _arc_points(ring, frac, 7, lambda i: width * (0.9 if i % 2 else -0.9))
        path = QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        p.setPen(QPen(col, width * 0.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
    elif design == "twin":
        for grow in (-width * 0.9, width * 0.9):
            p.setPen(round_pen(col, width * 0.5))
            p.drawArc(ring.adjusted(grow, grow, -grow, -grow), 90 * 16, span)
    elif design == "pulse":
        p.setPen(round_pen(alpha(col, 0.55), width * 0.6))
        p.drawArc(ring, 90 * 16, span)
        p.setPen(Qt.PenStyle.NoPen)
        for i, pt in enumerate(_arc_points(ring, frac, 24)):
            beat = 0.6 + 0.4 * math.sin(now * 4 - i * 0.8)
            p.setBrush(col)
            p.drawEllipse(pt, width * beat, width * beat)
    elif design == "ribbon":
        p.setPen(QPen(alpha(col, 0.3), width * 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        p.drawArc(ring, 90 * 16, span)
        p.setPen(round_pen(col, width * 0.6))
        p.drawArc(ring, 90 * 16, span)
    elif design == "laser":
        p.setPen(QPen(alpha(col, 0.28), width * 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(ring, 90 * 16, span)
        p.setPen(round_pen(col, width))
        p.drawArc(ring, 90 * 16, span)
        p.setPen(round_pen(mix(col, QColor("#FFFFFF"), 0.8), width * 0.35))
        p.drawArc(ring, 90 * 16, span)
    else:                                                    # spark: a line with a star at its head
        p.setPen(round_pen(col, width))
        p.drawArc(ring, 90 * 16, span)
        head = _arc_points(ring, frac, 360 * frac or 1)[-1]
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix(col, QColor("#FFFFFF"), 0.6))
        star = QPainterPath()
        size = width * (2.2 + 0.5 * math.sin(now * 5))
        for k in range(8):
            ang = math.radians(45 * k)
            rr = size if k % 2 == 0 else size * 0.3
            pt = QPointF(head.x() + rr * math.cos(ang), head.y() + rr * math.sin(ang))
            star.lineTo(pt) if k else star.moveTo(pt)
        star.closeSubpath()
        p.drawPath(star)
    p.restore()


# --------------------------------------------------------------------------- #
# A small picture of any item (shop, inventory, market, trades)
# --------------------------------------------------------------------------- #
def paint_cosmetic(p: QPainter, item: str, rect: QRectF, now: float = 0.0, effects: bool = True, dim: float = 1.0) -> None:
    kind, base, var = parts(item)
    if kind == "badge":
        from .collection import show_item
        return show_item(p, item, rect, now, effects, dim)
    d = min(rect.width(), rect.height())
    box = QRectF(rect.center().x() - d / 2, rect.center().y() - d / 2, d, d)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setOpacity(p.opacity() * dim)
    if kind == "ball":
        p.setPen(QPen(alpha("#FFFFFF", 0.12), 1))
        p.setBrush(QColor("#0B0E10"))
        p.drawEllipse(box)
        paint_shop_ball(p, box.translated(0, -d * 0.02), d, item, now if effects else 0.6)
    elif kind == "line":
        w = max(1.6, d * 0.07)
        paint_shop_ring(p, box.adjusted(w * 2.4, w * 2.4, -w * 2.4, -w * 2.4), item, 0.72, w, now if effects else 0.6)
    elif kind == "font":
        f = QFont()
        f.setFamilies(font_families(item) + ["Segoe UI", "Arial"])
        f.setPixelSize(max(8, int(d * 0.52)))
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(QColor("#AEB8C2") if var == "black" else colour_of(item))
        p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), "Aa")
    elif kind == "theme":
        look = next((t for t in THEME_LOOKS if t[0] == base), THEME_LOOKS[0])
        g = QLinearGradient(box.topLeft(), box.bottomRight())
        g.setColorAt(0.0, QColor(look[2]))
        g.setColorAt(1.0, QColor(look[3]))
        tile = box.adjusted(d * 0.08, d * 0.16, -d * 0.08, -d * 0.16)
        p.setPen(QPen(g, max(1.4, d * 0.06)))
        p.setBrush(QColor("#0B0E10"))
        p.drawRoundedRect(tile, d * 0.14, d * 0.14)
        p.setPen(Qt.PenStyle.NoPen)
        for k, (fx, fy, s) in enumerate(((0.3, 0.42, 0.05), (0.52, 0.6, 0.035), (0.7, 0.38, 0.045), (0.42, 0.68, 0.03))):
            p.setBrush(QColor(look[2 + k % 2]))
            tw = 0.7 + 0.3 * math.sin(now * 2 + k) if effects else 1.0
            p.drawEllipse(QPointF(box.left() + fx * d, box.top() + fy * d), s * d * tw, s * d * tw)
    p.restore()
