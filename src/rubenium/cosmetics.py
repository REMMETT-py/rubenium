"""Shop cosmetics: 10 balls, 10 song lines, 5 fonts and 6 themes. They are bought with coins, can be traded and
sold, and never look like the progression unlocks (no White Gold, no Gold progression look).

An item is named like the server names it: "ball:orbit:blue", "line:dash:red", "font:mono:white", "theme:ocean"."""
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient

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
# profile looks (2.6): a banner behind your profile, a frame around your picture, a tag after your name
BANNERS = [("dusk", "Dusk"), ("mint", "Mint"), ("steel", "Steel"), ("rose", "Rose"), ("waves", "Waves"), ("grid", "Grid"),
           ("stripes", "Stripes"), ("dots", "Dots"), ("aurora", "Aurora"), ("circuit", "Circuit"), ("sunset", "Sunset"),
           ("peaks", "Peaks"), ("galaxy", "Galaxy"), ("lava", "Lava"), ("matrix", "Matrix"), ("prism", "Prism"),
           ("snow", "Snow"), ("ember", "Ember"), ("nebula", "Nebula")]
FRAMES = [("silver", "Silver"), ("bronze", "Bronze"), ("ink", "Ink"), ("neon", "Neon"), ("dashed", "Dashed"),
          ("twin", "Twin"), ("laurel", "Laurel"), ("crown", "Crown"), ("spikes", "Spikes"), ("flame", "Flame"),
          ("orbit", "Orbit"), ("rainbow", "Rainbow"), ("frost", "Frost"), ("star", "Star"), ("halo", "Halo")]
TAGS = [("og", "OG")]
MOVING = {"waves", "stripes", "aurora", "circuit", "galaxy", "lava", "matrix", "prism", "dashed", "flame", "orbit",
          "rainbow", "neon", "og", "snow", "ember", "nebula", "frost", "star", "halo"}
KIND_NAMES = {"ball": "Ball", "line": "Line", "font": "Font", "theme": "Theme", "badge": "Badge", "banner": "Banner",
              "frame": "Frame", "tag": "Tag"}
_NAMES = {"ball": dict(BALLS), "line": dict(LINES), "font": {f[0]: f[1] for f in FONTS},
          "theme": {t[0]: t[1] for t in THEME_LOOKS}, "banner": dict(BANNERS), "frame": dict(FRAMES), "tag": dict(TAGS)}
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
    if kind == "tag":
        return tr("{name} tag", name=_NAMES["tag"].get(base, base.upper()))
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
    if kind in ("banner", "frame", "tag"):
        return paint_look_icon(p, item, rect, now if effects else 0.0, dim)
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


# --------------------------------------------------------------------------- #
# Profile looks: banners, frames and tags
# --------------------------------------------------------------------------- #
_BANNER_COLS = {"dusk": ("#3A2A6B", "#C0587E"), "mint": ("#0F5F55", "#5CE0B8"), "steel": ("#2B3640", "#7D8C99"),
                "rose": ("#5B1E3A", "#FF8FB1"), "waves": ("#0B2447", "#2E8BFF"), "grid": ("#1A0B2E", "#35D6E6"),
                "stripes": ("#5A1A0A", "#FF8A3D"), "dots": ("#0D2E33", "#1ABC9C"), "aurora": ("#06121F", "#3DFFB0"),
                "circuit": ("#04170F", "#2ECC71"), "sunset": ("#2B0F3D", "#FF8A3D"), "peaks": ("#0E1A2B", "#8FA8FF"),
                "galaxy": ("#05040F", "#9B5CFF"), "lava": ("#1A0503", "#FF3D1F"), "matrix": ("#010A04", "#3DFF7A"),
                "prism": ("#101018", "#FF5CC8"), "snow": ("#16304A", "#BFE6FF"), "ember": ("#1A0806", "#FF7A2E"),
                "nebula": ("#07051A", "#4FE3FF")}


def look_moves(item: str) -> bool:
    return parts(item)[1] in MOVING


def _rand(i: int, k: int = 0) -> float:
    """A fixed pseudo random number in [0, 1) (so stars stay where they are between frames)."""
    x = math.sin(i * 12.9898 + k * 78.233) * 43758.5453
    return x - math.floor(x)


def paint_banner(p: QPainter, rect: QRectF, item: str, now: float = 0.0, radius: float = 10.0, dim: float = 1.0) -> None:
    """A profile banner filling `rect` (rounded corners)."""
    base = parts(item)[1]
    c1, c2 = (QColor(c) for c in _BANNER_COLS.get(base, ("#1A2026", "#3A4650")))
    w, h = rect.width(), rect.height()
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setOpacity(p.opacity() * dim)
    clip = QPainterPath()
    clip.addRoundedRect(rect, radius, radius)
    p.setClipPath(clip)
    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0.0, c1)
    g.setColorAt(1.0, c2 if base in ("dusk", "mint", "steel", "rose", "sunset") else mix(c1, c2, 0.35))
    p.fillRect(rect, g)
    p.setPen(Qt.PenStyle.NoPen)
    L, T = rect.left(), rect.top()
    if base == "waves":
        for k in range(4):
            path = QPainterPath(QPointF(L, rect.bottom()))
            for x in range(0, int(w) + 8, 6):
                y = T + h * (0.35 + k * 0.17) + math.sin(x / w * 6.3 * (1 + k * 0.3) + now * (0.8 + k * 0.3) + k) * h * 0.07
                path.lineTo(L + x, y)
            path.lineTo(rect.right(), rect.bottom())
            p.setBrush(alpha(c2, 0.16 + k * 0.08))
            p.drawPath(path)
    elif base == "grid":
        horizon = T + h * 0.45
        p.setPen(QPen(alpha(c2, 0.55), 1))
        for k in range(-10, 11):
            p.drawLine(QPointF(L + w / 2 + k * w * 0.03, horizon), QPointF(L + w / 2 + k * w * 0.16, rect.bottom()))
        off = (now * 0.4) % 1.0
        for k in range(8):
            f = ((k + off) / 8) ** 2
            p.drawLine(QPointF(L, horizon + f * (rect.bottom() - horizon)), QPointF(rect.right(), horizon + f * (rect.bottom() - horizon)))
        sun = QLinearGradient(QPointF(0, T + h * 0.05), QPointF(0, horizon))
        sun.setColorAt(0, QColor("#FF5CB8"))
        sun.setColorAt(1, QColor("#FFC94D"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(sun)
        p.drawEllipse(QPointF(L + w / 2, horizon), h * 0.3, h * 0.3)
        p.fillRect(QRectF(L, horizon, w, h), mix(c1, QColor("#000000"), 0.2))
        p.setPen(QPen(alpha(c2, 0.55), 1))
        for k in range(-10, 11):
            p.drawLine(QPointF(L + w / 2 + k * w * 0.03, horizon), QPointF(L + w / 2 + k * w * 0.16, rect.bottom()))
        for k in range(8):
            f = ((k + off) / 8) ** 2
            p.drawLine(QPointF(L, horizon + f * (rect.bottom() - horizon)), QPointF(rect.right(), horizon + f * (rect.bottom() - horizon)))
    elif base == "stripes":
        p.setBrush(alpha(c2, 0.45))
        step = h * 0.5
        off = (now * 20) % (step * 2)
        x = L - h - step * 2 + off
        while x < rect.right() + h:
            path = QPainterPath(QPointF(x, rect.bottom()))
            path.lineTo(x + h, T)
            path.lineTo(x + h + step, T)
            path.lineTo(x + step, rect.bottom())
            p.drawPath(path)
            x += step * 2
    elif base == "dots":
        n = 22
        for i in range(n * 3):
            cx, cy = L + _rand(i) * w, T + _rand(i, 1) * h
            r = h * (0.03 + _rand(i, 2) * 0.09)
            p.setBrush(alpha(c2, 0.15 + _rand(i, 3) * 0.4))
            p.drawEllipse(QPointF(cx, cy), r, r)
    elif base == "aurora":
        for i in range(30):
            p.setBrush(alpha("#FFFFFF", 0.3 + 0.5 * _rand(i, 4)))
            p.drawEllipse(QPointF(L + _rand(i) * w, T + _rand(i, 1) * h * 0.6), 0.8, 0.8)
        for k, col in enumerate(("#3DFFB0", "#9B5CFF", "#2EC5FF")):
            path = QPainterPath(QPointF(L, T + h))
            for x in range(0, int(w) + 8, 6):
                y = T + h * (0.45 + 0.12 * k) + math.sin(x / w * 5 + now * 0.7 + k * 2) * h * 0.14 \
                    + math.sin(x / w * 13 + now * 1.3) * h * 0.04
                path.lineTo(L + x, y)
            path.lineTo(rect.right(), T + h)
            band = QLinearGradient(QPointF(0, T + h * 0.2), QPointF(0, T + h))
            band.setColorAt(0, alpha(col, 0.0))
            band.setColorAt(0.5, alpha(col, 0.35))
            band.setColorAt(1, alpha(col, 0.0))
            p.setBrush(band)
            p.drawPath(path)
    elif base == "circuit":
        p.setPen(QPen(alpha(c2, 0.45), 1.3))
        for i in range(14):
            x0, y0 = L + _rand(i) * w, T + _rand(i, 1) * h
            x1 = x0 + (_rand(i, 2) - 0.5) * w * 0.4
            path = QPainterPath(QPointF(x0, y0))
            path.lineTo(x1, y0)
            path.lineTo(x1 + h * 0.15, y0 + h * 0.15 * (1 if _rand(i, 3) > 0.5 else -1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            glow = 0.4 + 0.6 * max(0.0, math.sin(now * 2 + i * 1.7))
            p.setBrush(alpha(c2, glow))
            p.drawEllipse(QPointF(x0, y0), 2.2, 2.2)
        p.setPen(Qt.PenStyle.NoPen)
    elif base == "sunset":
        p.setBrush(alpha("#FFC94D", 0.95))
        sun = QRectF(L + w * 0.62, T + h * 0.18, h * 0.62, h * 0.62)
        p.drawEllipse(sun)
        for k in range(5):
            p.fillRect(QRectF(sun.left(), sun.top() + sun.height() * (0.52 + k * 0.1), sun.width(), sun.height() * 0.035 * (k + 1)),
                       mix(QColor("#C0306E"), QColor("#FF8A3D"), 0.4))
        p.fillRect(QRectF(L, T + h * 0.78, w, h * 0.22), QColor("#1A0828"))
    elif base == "peaks":
        for k, (col, hh) in enumerate((("#2A3A5C", 0.35), ("#1B2740", 0.55), ("#101828", 0.75))):
            path = QPainterPath(QPointF(L, rect.bottom()))
            for i in range(9):
                x = L + i * w / 8
                y = T + h * (hh + (0.18 if (i + k) % 2 else -0.05) * (0.6 + _rand(i, k) * 0.6))
                path.lineTo(x, y)
            path.lineTo(rect.right(), rect.bottom())
            p.setBrush(QColor(col))
            p.drawPath(path)
        p.setBrush(alpha("#FFFFFF", 0.85))
        p.drawEllipse(QPointF(L + w * 0.18, T + h * 0.22), h * 0.08, h * 0.08)
    elif base == "galaxy":
        neb = QLinearGradient(rect.topLeft(), rect.bottomRight())
        neb.setColorAt(0.2, alpha("#9B5CFF", 0.0))
        neb.setColorAt(0.5, alpha("#9B5CFF", 0.35))
        neb.setColorAt(0.65, alpha("#FF5CB8", 0.22))
        neb.setColorAt(0.9, alpha("#2EC5FF", 0.0))
        p.fillRect(rect, neb)
        for i in range(60):
            tw = 0.35 + 0.65 * abs(math.sin(now * (0.8 + _rand(i, 5) * 2) + i))
            p.setBrush(alpha("#FFFFFF", tw * (0.4 + 0.6 * _rand(i, 2))))
            r = 0.6 + _rand(i, 3) * 1.4
            p.drawEllipse(QPointF(L + _rand(i) * w, T + _rand(i, 1) * h), r, r)
        sx = L + ((now * 0.25) % 1.6 - 0.3) * w
        p.setPen(QPen(alpha("#FFFFFF", 0.7), 1.2))
        p.drawLine(QPointF(sx, T + h * 0.2), QPointF(sx - w * 0.08, T + h * 0.32))
        p.setPen(Qt.PenStyle.NoPen)
    elif base == "lava":
        for i in range(9):
            cx = L + (_rand(i) + 0.05 * math.sin(now * 0.6 + i)) * w
            cy = T + h * (0.5 + 0.45 * math.sin(now * (0.3 + _rand(i, 1) * 0.4) + i * 1.3))
            r = h * (0.22 + _rand(i, 2) * 0.25)
            blob = QLinearGradient(QPointF(cx, cy - r), QPointF(cx, cy + r))
            blob.setColorAt(0, alpha("#FFC94D", 0.85))
            blob.setColorAt(1, alpha("#FF3D1F", 0.6))
            p.setBrush(blob)
            p.drawEllipse(QPointF(cx, cy), r, r)
    elif base == "matrix":
        f = QFont("Consolas")
        f.setPixelSize(max(6, int(h * 0.13)))
        p.setFont(f)
        cw = f.pixelSize() * 0.9
        cols = int(w / cw) + 1
        for c in range(cols):
            speed = 0.6 + _rand(c) * 1.2
            head = ((now * speed + _rand(c, 1) * 3) % 1.6) * h
            for k in range(8):
                y = head - k * f.pixelSize()
                if T - f.pixelSize() < T + y < rect.bottom() + f.pixelSize():
                    p.setPen(alpha("#C8FFD8" if k == 0 else "#3DFF7A", max(0.0, 1 - k / 8)))
                    ch = chr(0x30A0 + int(_rand(c * 31 + k, int(now * 3) % 7) * 90))
                    p.drawText(QPointF(L + c * cw, T + y), ch)
        p.setPen(Qt.PenStyle.NoPen)
    elif base == "prism":
        sweep = QLinearGradient(QPointF(L - w + (now * 0.3 % 1) * w * 2, T), QPointF(L + (now * 0.3 % 1) * w * 2, rect.bottom()))
        for k, col in enumerate(("#FF5CC8", "#FFC94D", "#3DFF7A", "#2EC5FF", "#9B5CFF", "#FF5CC8")):
            sweep.setColorAt(k / 5, alpha(col, 0.55))
        p.fillRect(rect, sweep)
        p.setBrush(alpha("#FFFFFF", 0.18))
        tri = QPainterPath(QPointF(L + w * 0.5, T + h * 0.15))
        tri.lineTo(L + w * 0.62, T + h * 0.85)
        tri.lineTo(L + w * 0.38, T + h * 0.85)
        tri.closeSubpath()
        p.drawPath(tri)
    elif base == "snow":                                       # snowy hills and falling snow
        for k, (col, hh) in enumerate((("#9CC7E8", 0.62), ("#DDEFFF", 0.74), ("#FFFFFF", 0.86))):
            path = QPainterPath(QPointF(L, rect.bottom()))
            for x in range(0, int(w) + 8, 8):
                path.lineTo(L + x, T + h * hh + math.sin(x / w * 5 + k * 1.7) * h * 0.06)
            path.lineTo(rect.right(), rect.bottom())
            p.setBrush(QColor(col))
            p.drawPath(path)
        for i in range(46):
            fall = (_rand(i, 1) + now * (0.06 + _rand(i, 2) * 0.08)) % 1.0
            x = L + (_rand(i) + 0.04 * math.sin(now * 1.3 + i)) * w
            r = 0.8 + _rand(i, 3) * 1.6
            p.setBrush(alpha("#FFFFFF", 0.55 + 0.45 * _rand(i, 4)))
            p.drawEllipse(QPointF(x, T + fall * h), r, r)
    elif base == "ember":                                      # sparks rising from a glowing floor
        floor = QLinearGradient(QPointF(0, T + h * 0.5), QPointF(0, rect.bottom()))
        floor.setColorAt(0, alpha("#FF3D1F", 0.0))
        floor.setColorAt(1, alpha("#FF7A2E", 0.65))
        p.fillRect(rect, floor)
        for i in range(36):
            rise = (_rand(i, 1) + now * (0.12 + _rand(i, 2) * 0.2)) % 1.0
            x = L + (_rand(i) + 0.05 * math.sin(now * 2 + i * 1.3)) * w
            r = 0.8 + _rand(i, 3) * 1.8
            p.setBrush(alpha("#FFC94D" if i % 3 else "#FF5C2E", (1 - rise) * 0.95))
            p.drawEllipse(QPointF(x, rect.bottom() - rise * h), r, r)
    elif base == "nebula":                                     # slowly turning clouds of colour, twinkling stars
        for k, col in enumerate(("#4FE3FF", "#B36BFF", "#FF5CC8")):
            a = now * 0.25 + k * 2.1
            cx, cy = L + w * (0.5 + 0.25 * math.cos(a)), T + h * (0.5 + 0.3 * math.sin(a * 1.3))
            g2 = QRadialGradient(QPointF(cx, cy), h * 0.9)
            g2.setColorAt(0, alpha(col, 0.45))
            g2.setColorAt(1, alpha(col, 0.0))
            p.fillRect(rect, g2)
        for i in range(50):
            tw = 0.3 + 0.7 * abs(math.sin(now * (1 + _rand(i, 5) * 2) + i))
            p.setBrush(alpha("#FFFFFF", tw))
            p.drawEllipse(QPointF(L + _rand(i) * w, T + _rand(i, 1) * h), 0.7 + _rand(i, 2), 0.7 + _rand(i, 2))
    shade = QLinearGradient(rect.topLeft(), rect.bottomLeft())       # a soft shade at the bottom, for text on top
    shade.setColorAt(0.55, alpha("#000000", 0.0))
    shade.setColorAt(1.0, alpha("#000000", 0.35))
    p.fillRect(rect, shade)
    p.restore()


_FRAME_COLS = {"silver": ("#F2F6FA", "#8A96A3"), "bronze": ("#FFB067", "#8A4B1E"), "ink": ("#0B0E10", "#FFFFFF"),
               "neon": ("#2EF2FF", "#2EF2FF"), "dashed": ("#FFFFFF", "#9AA4AD"), "twin": ("#FF5CB8", "#2EC5FF"),
               "laurel": ("#FFD36B", "#B8862B"), "crown": ("#FFD36B", "#B8862B"), "spikes": ("#E6EEF5", "#6E7C88"),
               "flame": ("#FFC94D", "#FF3D1F"), "orbit": ("#B36BFF", "#4FE3FF"), "rainbow": ("#FF5CC8", "#2EC5FF"),
               "frost": ("#E8F6FF", "#7FC8FF"), "star": ("#FFE9A8", "#FFC94D"), "halo": ("#FFFFFF", "#C9B6FF")}


def paint_frame(p: QPainter, face: QRectF, item: str, now: float = 0.0, dim: float = 1.0) -> None:
    """A frame around a round profile picture `face` (drawn on top of it, slightly outside)."""
    base = parts(item)[1]
    if not base:
        return
    c1, c2 = (QColor(c) for c in _FRAME_COLS.get(base, ("#FFFFFF", "#9AA4AD")))
    d = face.width()
    wd = max(1.6, d * 0.085)
    c = face.center()
    r = d / 2 + wd * 0.35
    ring = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setOpacity(p.opacity() * dim)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if base in ("silver", "bronze", "laurel", "crown", "spikes"):
        g = QLinearGradient(ring.topLeft(), ring.bottomRight())
        g.setColorAt(0.0, c1)
        g.setColorAt(0.5, c2)
        g.setColorAt(1.0, c1)
        p.setPen(QPen(g, wd))
        p.drawEllipse(ring)
    elif base == "ink":
        p.setPen(QPen(c1, wd * 1.3))
        p.drawEllipse(ring)
        p.setPen(QPen(c2, max(1.0, wd * 0.25)))
        p.drawEllipse(ring.adjusted(wd * 0.75, wd * 0.75, -wd * 0.75, -wd * 0.75))
    elif base == "neon":
        pulse = 0.75 + 0.25 * math.sin(now * 3)
        for k in (3.2, 2.2, 1.4):
            p.setPen(QPen(alpha(c1, 0.12 * pulse * (4 - k)), wd * k))
            p.drawEllipse(ring)
        p.setPen(QPen(QColor("#E8FFFF"), wd * 0.6))
        p.drawEllipse(ring)
    elif base == "dashed":
        pen = QPen(c1, wd * 0.8)
        pen.setDashPattern([2.2, 1.6])
        pen.setDashOffset(-now * 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawEllipse(ring)
    elif base == "twin":
        p.setPen(QPen(c1, wd * 0.5))
        p.drawEllipse(ring.adjusted(-wd * 0.45, -wd * 0.45, wd * 0.45, wd * 0.45))
        p.setPen(QPen(c2, wd * 0.5))
        p.drawEllipse(ring.adjusted(wd * 0.25, wd * 0.25, -wd * 0.25, -wd * 0.25))
    elif base == "flame":
        p.setPen(Qt.PenStyle.NoPen)
        n = 18
        for i in range(n):
            a = i / n * math.tau
            flick = 0.55 + 0.45 * abs(math.sin(now * 5 + i * 1.9))
            ln = wd * (1.4 + 1.6 * flick)
            tip = QPointF(c.x() + math.cos(a) * (r + ln), c.y() + math.sin(a) * (r + ln))
            left = QPointF(c.x() + math.cos(a - 0.17) * r, c.y() + math.sin(a - 0.17) * r)
            right = QPointF(c.x() + math.cos(a + 0.17) * r, c.y() + math.sin(a + 0.17) * r)
            g = QLinearGradient(QPointF(c.x() + math.cos(a) * r, c.y() + math.sin(a) * r), tip)
            g.setColorAt(0, c2)
            g.setColorAt(1, alpha(c1, 0.0))
            path = QPainterPath(left)
            path.quadTo(QPointF(c.x() + math.cos(a) * (r + ln * 0.6), c.y() + math.sin(a) * (r + ln * 0.6)), tip)
            path.lineTo(right)
            path.closeSubpath()
            p.setBrush(g)
            p.drawPath(path)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(c1, wd * 0.8))
        p.drawEllipse(ring)
    elif base == "orbit":
        p.setPen(QPen(alpha(c1, 0.9), wd * 0.55))
        p.drawEllipse(ring)
        p.setPen(Qt.PenStyle.NoPen)
        for k in range(3):
            a = now * (1.6 + k * 0.4) + k * 2.1
            rr = r + wd * (0.9 + k * 0.5)
            p.setBrush(c2 if k % 2 else c1)
            p.drawEllipse(QPointF(c.x() + math.cos(a) * rr, c.y() + math.sin(a) * rr), wd * 0.55, wd * 0.55)
    elif base == "rainbow":
        from PyQt6.QtGui import QConicalGradient
        g = QConicalGradient(c, (now * 90) % 360)
        for k, col in enumerate(("#FF5CC8", "#FFC94D", "#3DFF7A", "#2EC5FF", "#9B5CFF", "#FF5CC8")):
            g.setColorAt(k / 5, QColor(col))
        p.setPen(QPen(g, wd))
        p.drawEllipse(ring)
    elif base == "frost":                                     # icy ring with crystals
        g = QLinearGradient(ring.topLeft(), ring.bottomRight())
        g.setColorAt(0, c1)
        g.setColorAt(1, c2)
        p.setPen(QPen(g, wd * 0.8))
        p.drawEllipse(ring)
        p.setPen(QPen(alpha("#FFFFFF", 0.9), max(1.0, wd * 0.25)))
        for i in range(6):
            a = i / 6 * math.tau + now * 0.2
            cx, cy = c.x() + math.cos(a) * r, c.y() + math.sin(a) * r
            for k in range(3):
                b = a + k * math.pi / 3
                p.drawLine(QPointF(cx - math.cos(b) * wd * 0.9, cy - math.sin(b) * wd * 0.9),
                           QPointF(cx + math.cos(b) * wd * 0.9, cy + math.sin(b) * wd * 0.9))
    elif base == "star":                                      # gold ring with orbiting stars
        p.setPen(QPen(c2, wd * 0.7))
        p.drawEllipse(ring)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(5):
            a = i / 5 * math.tau + now * 0.6
            sc = QPointF(c.x() + math.cos(a) * r, c.y() + math.sin(a) * r)
            pts = []
            for k in range(10):
                rr = wd * (1.3 if k % 2 == 0 else 0.55)
                b = k / 10 * math.tau - math.pi / 2 + now
                pts.append(QPointF(sc.x() + math.cos(b) * rr, sc.y() + math.sin(b) * rr))
            path = QPainterPath(pts[0])
            for q in pts[1:]:
                path.lineTo(q)
            path.closeSubpath()
            p.setBrush(c1)
            p.drawPath(path)
    elif base == "halo":                                      # a soft glowing halo that breathes, and a light above
        breathe = 0.7 + 0.3 * math.sin(now * 2)
        for k in (4.0, 2.6, 1.6):
            p.setPen(QPen(alpha(c2, 0.10 * breathe * (5 - k)), wd * k))
            p.drawEllipse(ring)
        p.setPen(QPen(c1, wd * 0.5))
        p.drawEllipse(ring)
        top = QRectF(c.x() - r * 0.55, c.y() - r - wd * 2.6, r * 1.1, wd * 1.4)
        p.setPen(QPen(alpha("#FFF6C8", 0.6 + 0.4 * breathe), wd * 0.55))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(top)
    if base == "laurel":                                      # leaves up both sides
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#E8C26A"))
        for side in (-1, 1):
            for k in range(5):
                a = math.pi / 2 + side * (0.45 + k * 0.38)
                lc = QPointF(c.x() + math.cos(a) * (r + wd * 0.9), c.y() + math.sin(a) * (r + wd * 0.9))
                p.save()
                p.translate(lc)
                p.rotate(math.degrees(a) + 90 + side * 30)
                p.drawEllipse(QPointF(0, 0), wd * 0.55, wd * 1.15)
                p.restore()
    elif base == "crown":
        p.setPen(Qt.PenStyle.NoPen)
        cw, ch = d * 0.46, d * 0.26
        top = c.y() - r - ch * 0.55
        path = QPainterPath(QPointF(c.x() - cw / 2, top + ch))
        for k, (fx, fy) in enumerate(((-0.5, 0.15), (-0.25, 0.55), (0.0, 0.0), (0.25, 0.55), (0.5, 0.15))):
            path.lineTo(c.x() + fx * cw, top + fy * ch)
        path.lineTo(c.x() + cw / 2, top + ch)
        path.closeSubpath()
        g = QLinearGradient(QPointF(0, top), QPointF(0, top + ch))
        g.setColorAt(0, QColor("#FFE9A8"))
        g.setColorAt(1, QColor("#C99A2E"))
        p.setBrush(g)
        p.drawPath(path)
        p.setBrush(QColor("#FF4B6E"))
        p.drawEllipse(QPointF(c.x(), top + ch * 0.62), ch * 0.12, ch * 0.12)
    elif base == "spikes":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c1)
        n = 12
        for i in range(n):
            a = i / n * math.tau + math.pi / n
            path = QPainterPath(QPointF(c.x() + math.cos(a - 0.12) * r, c.y() + math.sin(a - 0.12) * r))
            path.lineTo(c.x() + math.cos(a) * (r + wd * 2.0), c.y() + math.sin(a) * (r + wd * 2.0))
            path.lineTo(c.x() + math.cos(a + 0.12) * r, c.y() + math.sin(a + 0.12) * r)
            path.closeSubpath()
            p.drawPath(path)
    p.restore()


def paint_tag(p: QPainter, x: float, cy: float, item: str, now: float = 0.0, size: float = 8.5,
              centre: bool = False, px: float = 0.0) -> float:
    """A tag after a name ("OG": gold, with a light running across). Returns its width. `px`: an exact pixel size."""
    text = _NAMES["tag"].get(parts(item)[1], parts(item)[1].upper()) or "?"
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    f = font(size, QFont.Weight.Black, 0.8)
    if px:
        f.setPixelSize(max(6, int(px)))
    p.setFont(f)
    hgt = f.pixelSize() * 1.75
    w = p.fontMetrics().horizontalAdvance(text) + hgt * 0.75
    if centre:
        x -= w / 2
    box = QRectF(x, cy - hgt / 2, w, hgt)
    g = QLinearGradient(box.topLeft(), box.bottomRight())
    g.setColorAt(0.0, QColor("#FFE9A8"))
    g.setColorAt(0.5, QColor("#E8B13A"))
    g.setColorAt(1.0, QColor("#B87A16"))
    p.setPen(QPen(QColor("#FFF4CF"), 0.8))
    p.setBrush(g)
    p.drawRoundedRect(box, hgt * 0.28, hgt * 0.28)
    if now:                                                    # a light running across
        clip = QPainterPath()
        clip.addRoundedRect(box, hgt * 0.28, hgt * 0.28)
        p.setClipPath(clip)
        sx = box.left() + ((now * 0.5) % 1.6 - 0.3) * box.width() * 1.4
        shine = QLinearGradient(QPointF(sx - hgt, 0), QPointF(sx + hgt, 0))
        shine.setColorAt(0, alpha("#FFFFFF", 0.0))
        shine.setColorAt(0.5, alpha("#FFFFFF", 0.65))
        shine.setColorAt(1, alpha("#FFFFFF", 0.0))
        p.fillRect(box, shine)
        p.setClipping(False)
    p.setPen(QColor("#3A2300"))
    p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), text)
    p.restore()
    return w


def paint_blank_face(p: QPainter, face: QRectF) -> None:
    """A plain grey picture (for previews of frames)."""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#2A3238"))
    p.drawEllipse(face)
    clip = QPainterPath()
    clip.addEllipse(face)
    p.setClipPath(clip)
    p.setBrush(QColor("#55626C"))
    d = face.width()
    p.drawEllipse(QPointF(face.center().x(), face.top() + d * 0.4), d * 0.18, d * 0.18)
    p.drawEllipse(QPointF(face.center().x(), face.top() + d * 0.95), d * 0.34, d * 0.3)
    p.restore()


def paint_look_icon(p: QPainter, item: str, rect: QRectF, now: float = 0.0, dim: float = 1.0) -> None:
    """The small picture of a banner, frame or tag (shop, inventory, market, trades)."""
    kind = parts(item)[0]
    d = min(rect.width(), rect.height())
    box = QRectF(rect.center().x() - d / 2, rect.center().y() - d / 2, d, d)
    p.save()
    p.setOpacity(p.opacity() * dim)
    if kind == "banner":
        paint_banner(p, QRectF(box.left(), box.top() + d * 0.2, d, d * 0.6), item, now, d * 0.1)
    elif kind == "frame":
        face = box.adjusted(d * 0.22, d * 0.22, -d * 0.22, -d * 0.22)
        paint_blank_face(p, face)
        paint_frame(p, face, item, now)
    else:
        paint_tag(p, box.center().x(), box.center().y(), item, now, centre=True, px=d * 0.24)
    p.restore()
