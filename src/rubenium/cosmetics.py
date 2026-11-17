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
         ("spiral", "Spiral"), ("bullseye", "Bullseye"), ("hex", "Hex"), ("ripple", "Ripple"), ("shard", "Shard"),
         ("petal", "Petal"), ("gear", "Gear"), ("planet", "Planet"), ("nova", "Nova"), ("snowglobe", "Snow Globe")]
LINES = [("dash", "Dash"), ("beads", "Beads"), ("zigzag", "Zigzag"), ("twin", "Twin"), ("pulse", "Pulse"),
         ("chain", "Chain"), ("ribbon", "Ribbon"), ("steps", "Steps"), ("spark", "Spark"), ("laser", "Laser"),
         ("wave", "Wave"), ("stars", "Stars"), ("helix", "Helix"), ("lightning", "Lightning"), ("garland", "Garland")]
FONTS = [("rounded", "Rounded", ["Trebuchet MS", "Verdana"]), ("mono", "Mono", ["Cascadia Mono", "Consolas", "Courier New"]),
         ("serif", "Serif", ["Georgia", "Cambria", "Times New Roman"]), ("display", "Display", ["Bahnschrift", "Impact"]),
         ("script", "Script", ["Segoe Print", "Segoe Script", "Comic Sans MS"])]
# shop themes: two fixed colours and their own night sky (name, colour 1, colour 2, sky settings)
THEME_LOOKS = [("sunset", "Sunset", "#FF8A3D", "#FF3D7F", dict(glow=2, stars=22, comets=2, sparkles=4)),
               ("ocean", "Ocean", "#2D9CFF", "#1ABC9C", dict(glow=2, stars=30, aurora=True, sparkles=3)),
               ("forest", "Forest", "#2ECC71", "#A6E22E", dict(glow=2, stars=26, links=6, sparkles=5)),
               ("candy", "Candy", "#FF5CB8", "#9B5CFF", dict(glow=3, stars=18, sparkles=11)),
               ("storm", "Storm", "#8FA8FF", "#4B6BFF", dict(glow=3, stars=44, links=10, comets=6, aurora=True)),
               ("retro", "Retro", "#D94BFF", "#35D6E6", dict(glow=3, stars=52, links=14, sparkles=8, edge="shine")),
               ("lagoon", "Lagoon", "#20D3C2", "#3A7BFF", dict(glow=2, stars=24, aurora=True, sparkles=4)),
               ("midnight", "Midnight", "#7C8CFF", "#1B2A6B", dict(glow=3, stars=60, comets=4, links=8, sparkles=6)),
               ("inferno", "Inferno", "#FF5A1F", "#FFC14D", dict(glow=3, stars=36, comets=8, sparkles=12, edge="shine"))]
# profile looks (2.6): a banner behind your profile, a frame around your picture, a tag after your name
BANNERS = [("dusk", "Dusk"), ("mint", "Mint"), ("steel", "Steel"), ("rose", "Rose"), ("stripes", "Stripes"), ("dots", "Dots"),
           ("carbon", "Carbon"), ("dunes", "Dunes"),
           ("waves", "Waves"), ("peaks", "Peaks"), ("ember", "Ember"), ("circuit", "Circuit"), ("sunset", "Sunset"),
           ("honeycomb", "Honeycomb"), ("comet", "Comet"), ("deepsea", "Deep Sea"),
           ("grid", "Grid"), ("jungle", "Jungle"), ("sakura", "Sakura"), ("lava", "Lava"), ("prism", "Prism"),
           ("city", "City Nights"), ("neon", "Neon"), ("fireflies", "Fireflies"),
           ("galaxy", "Galaxy"), ("nebula", "Nebula"), ("matrix", "Matrix"), ("storm", "Storm"), ("vortex", "Vortex"),
           ("snow", "Snow"), ("aurora", "Aurora"),
           ("slate", "Slate"), ("pastel", "Pastel"), ("tides", "Tides"), ("canyon", "Canyon"), ("koi", "Koi Pond"),
           ("synthwave", "Synthwave"), ("supernova", "Supernova"), ("dragon", "Dragon"),
           ("wreath", "Wreath"), ("hearth", "Hearth"), ("northstar", "North Star")]
FRAMES = [("silver", "Silver"), ("bronze", "Bronze"), ("ink", "Ink"), ("neon", "Neon"), ("dashed", "Dashed"),
          ("twin", "Twin"), ("laurel", "Laurel"), ("crown", "Crown"), ("spikes", "Spikes"), ("flame", "Flame"),
          ("orbit", "Orbit"), ("rainbow", "Rainbow"), ("frost", "Frost"), ("star", "Star"), ("halo", "Halo"), ("vine", "Vine"),
          ("wood", "Wood"), ("pulse", "Pulse"), ("thorns", "Thorns"), ("gears", "Gears"), ("phoenix", "Phoenix"),
          ("holly", "Holly"), ("snowflake", "Snowflake"), ("northstar", "North Star")]
TAGS = [("og", "OG")]
MOVING = {"tides", "koi", "synthwave", "supernova", "dragon", "hearth", "northstar", "wreath", "pulse", "thorns", "gears",
          "phoenix", "snowflake", "holly", "waves", "stripes", "aurora", "circuit", "galaxy", "lava", "matrix", "prism", "dashed", "flame", "orbit",
          "rainbow", "neon", "og", "snow", "ember", "nebula", "frost", "star", "halo", "jungle", "sakura", "vine",
          "honeycomb", "comet", "deepsea", "city", "fireflies", "storm", "vortex"}
EVENT_LOOKS = {"banner:snow", "banner:aurora", "frame:frost", "banner:wreath", "banner:hearth", "banner:northstar",
               "frame:holly", "frame:snowflake", "frame:northstar"}      # the Christmas looks (advent calendar, Winter Case)
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
            th = _theme("theme:" + tid, name, 0, glow=1, sparkles=sky.get("sparkles", 0) // 2,
                        halo=1.0 + 0.1 * sky.get("glow", 2), edge=sky.get("edge", ""))
            th["tint"] = (c1, c2)
            th["scene"] = tid                              # 3.1: its own picture instead of the night sky
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
    elif design == "petal":                              # 3.2 Common: four soft petals
        p.setPen(Qt.PenStyle.NoPen)
        for k in range(4):
            ang = math.radians(45 + 90 * k)
            p.setBrush(alpha(line, 0.42))
            p.save()
            p.translate(c.x() + r * 0.62 * math.cos(ang), c.y() + r * 0.62 * math.sin(ang))
            p.rotate(45 + 90 * k)
            p.drawEllipse(QPointF(0, 0), r * 0.2, r * 0.11)
            p.restore()
    elif design == "gear":                               # 3.2 Rare: a turning cog, teeth and a hub ring
        teeth, outer, inner = 10, r * 0.86, r * 0.72
        path = QPainterPath()
        spin = now * 18
        for k in range(teeth * 4 + 1):
            ang = math.radians(spin + k * 360 / (teeth * 4))
            rr = outer if (k % 4) in (1, 2) else inner
            pt = QPointF(c.x() + rr * math.cos(ang), c.y() + rr * math.sin(ang))
            path.lineTo(pt) if k else path.moveTo(pt)
        p.setPen(QPen(alpha(line, 0.75), max(1.0, d * 0.022), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
        p.setPen(QPen(alpha(line, 0.3), max(1.0, d * 0.015)))
        p.drawEllipse(c, r * 0.6, r * 0.6)
    elif design == "planet":                             # 3.2 Epic: a tilted ring, a moon and two little stars
        p.save()
        p.translate(c)
        p.rotate(-18)
        p.setPen(QPen(alpha(line, 0.35), max(1.0, d * 0.05)))
        p.drawArc(QRectF(-r * 0.92, -r * 0.3, r * 1.84, r * 0.6), 0, -180 * 16)      # back half, faint
        p.setPen(QPen(alpha(line, 0.85), max(1.0, d * 0.032)))
        p.drawArc(QRectF(-r * 0.92, -r * 0.3, r * 1.84, r * 0.6), 0, 180 * 16)
        p.restore()
        ang = now * 0.9
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix(line, QColor("#FFFFFF"), 0.35))
        p.drawEllipse(QPointF(c.x() + r * 0.8 * math.cos(ang), c.y() + r * 0.8 * math.sin(ang) * 0.9), d * 0.05, d * 0.05)
        for k, (sx, sy) in enumerate(((-0.62, -0.6), (0.66, 0.55))):
            tw = 0.5 + 0.5 * math.sin(now * 3 + k * 2)
            p.setBrush(alpha("#FFFFFF", 0.4 + 0.5 * tw))
            p.drawEllipse(QPointF(c.x() + sx * r, c.y() + sy * r), d * 0.018, d * 0.018)
    elif design in ("nova", "snowglobe"):              # 3.2 Legendary: a burst of rays and orbiting sparks
        if design == "snowglobe":                         # limited: a glass globe with falling snow
            p.setPen(QPen(alpha("#DDF3FF", 0.65), max(1.0, d * 0.025)))
            p.setBrush(alpha("#9FE3FF", 0.10))
            p.drawEllipse(c, r * 0.84, r * 0.84)
            p.setPen(Qt.PenStyle.NoPen)
            for k in range(12):
                fx = math.sin(k * 7.3) * 0.6
                fy = ((now * 0.12 + k / 12) % 1.0) * 1.4 - 0.7
                if fx * fx + fy * fy < 0.55:
                    p.setBrush(alpha("#FFFFFF", 0.85))
                    p.drawEllipse(QPointF(c.x() + fx * r, c.y() + fy * r), d * 0.016, d * 0.016)
            p.setBrush(alpha("#C8283D", 0.85))
            p.drawRoundedRect(QRectF(c.x() - r * 0.5, c.y() + r * 0.72, r, r * 0.18), r * 0.06, r * 0.06)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            for k in range(12):
                ang = math.radians(k * 30 + now * 20)
                long_ = 0.9 if k % 2 == 0 else 0.7
                ray = QPainterPath()
                ray.moveTo(c.x() + r * 0.56 * math.cos(ang - 0.08), c.y() + r * 0.56 * math.sin(ang - 0.08))
                ray.lineTo(c.x() + r * long_ * math.cos(ang), c.y() + r * long_ * math.sin(ang))
                ray.lineTo(c.x() + r * 0.56 * math.cos(ang + 0.08), c.y() + r * 0.56 * math.sin(ang + 0.08))
                ray.closeSubpath()
                p.setBrush(alpha(line, 0.75 if k % 2 == 0 else 0.4))
                p.drawPath(ray)
            for k in range(3):
                ang = now * (1.4 + k * 0.5) + k * 2.1
                p.setBrush(mix(line, QColor("#FFFFFF"), 0.6))
                p.drawEllipse(QPointF(c.x() + r * 0.92 * math.cos(ang), c.y() + r * 0.92 * math.sin(ang)), d * 0.025, d * 0.025)
            glow = QRadialGradient(c, r * 0.62)
            glow.setColorAt(0, alpha(line, 0.25))
            glow.setColorAt(1, alpha(line, 0.0))
            p.setBrush(glow)
            p.drawEllipse(c, r * 0.62, r * 0.62)
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
    elif design == "wave":                                   # 3.2 Common: a soft wave
        pts = _arc_points(ring, frac, 3, lambda i: width * 0.8 * math.sin(i * 0.9 + now * 3))
        path = QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        p.setPen(QPen(col, width * 0.65, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
    elif design == "stars":                                  # 3.2 Rare: a faint line dotted with little stars
        p.setPen(round_pen(alpha(col, 0.35), width * 0.45))
        p.drawArc(ring, 90 * 16, span)
        p.setPen(Qt.PenStyle.NoPen)
        for i, pt in enumerate(_arc_points(ring, frac, 20)):
            tw = 0.7 + 0.3 * math.sin(now * 3 + i)
            star = QPainterPath()
            size = width * 1.3 * tw
            for k in range(10):
                ang = math.radians(-90 + 36 * k)
                rr = size if k % 2 == 0 else size * 0.42
                q = QPointF(pt.x() + rr * math.cos(ang), pt.y() + rr * math.sin(ang))
                star.lineTo(q) if k else star.moveTo(q)
            star.closeSubpath()
            p.setBrush(col)
            p.drawPath(star)
    elif design == "helix":                                  # 3.2 Epic: two strands twisting round each other
        for phase, a in ((0.0, 1.0), (math.pi, 0.55)):
            pts = _arc_points(ring, frac, 3, lambda i, ph=phase: width * 1.1 * math.sin(i * 0.35 + ph + now * 2))
            path = QPainterPath(pts[0])
            for pt in pts[1:]:
                path.lineTo(pt)
            p.setPen(QPen(alpha(col, a), width * 0.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix(col, QColor("#FFFFFF"), 0.5))
        for pt in _arc_points(ring, frac, 26):
            p.drawEllipse(pt, width * 0.35, width * 0.35)
    elif design == "lightning":                              # 3.2 Legendary: a crackling bolt with a glow
        rnd_k = int(now * 12)
        pts = _arc_points(ring, frac, 6, lambda i: width * 1.2 * math.sin(i * 2.7 + rnd_k * 1.3) * (0.4 + 0.6 * ((i * 37 + rnd_k) % 5) / 4))
        path = QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        p.setPen(QPen(alpha(col, 0.25), width * 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
        p.setPen(QPen(col, width * 0.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.MiterJoin))
        p.drawPath(path)
        p.setPen(QPen(mix(col, QColor("#FFFFFF"), 0.85), width * 0.3))
        p.drawPath(path)
    elif design == "garland":                                # limited: a green garland with red and gold baubles
        p.setPen(round_pen(QColor("#1F7A4A"), width * 1.3))
        p.drawArc(ring, 90 * 16, span)
        p.setPen(Qt.PenStyle.NoPen)
        for i, pt in enumerate(_arc_points(ring, frac, 22)):
            glow_ = 0.75 + 0.25 * math.sin(now * 3 + i * 1.3)
            p.setBrush(QColor("#E8384F") if i % 2 == 0 else QColor("#E8C26A"))
            p.setOpacity(glow_)
            p.drawEllipse(pt, width * 0.75, width * 0.75)
        p.setOpacity(1.0)
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
                "nebula": ("#07051A", "#4FE3FF"), "jungle": ("#06200F", "#2ECC71"), "sakura": ("#2A0E22", "#FF9CCB"),
                "carbon": ("#15181C", "#2C3238"), "dunes": ("#F2A65A", "#FFD9A0"), "honeycomb": ("#1A1204", "#FFB627"),
                "comet": ("#060B1E", "#4F8BFF"), "deepsea": ("#021226", "#1FB5D6"), "city": ("#0B0F2A", "#3A2A6B"),
                "neon": ("#0A0412", "#2A0F3D"), "fireflies": ("#0C2416", "#1B3D22"), "storm": ("#0D1220", "#3A4A6B"),
                "vortex": ("#08041A", "#4FE3FF"),
                "slate": ("#2A3138", "#56616B"), "pastel": ("#F7C6D9", "#B8D8FF"), "tides": ("#062A3A", "#33C4D8"),
                "canyon": ("#4A1E10", "#E07A3C"), "koi": ("#062A28", "#0E5B57"), "synthwave": ("#14052B", "#FF2BD6"),
                "supernova": ("#05030F", "#FFB347"), "dragon": ("#120406", "#C8283D"), "wreath": ("#5A0E18", "#C8283D"),
                "hearth": ("#1C0A05", "#FF8A3D"), "northstar": ("#050B1E", "#1B3A6B")}


def look_moves(item: str) -> bool:
    return parts(item)[1] in MOVING


def _rand(i: int, k: int = 0) -> float:
    """A fixed pseudo random number in [0, 1) (so stars stay where they are between frames)."""
    x = math.sin(i * 12.9898 + k * 78.233) * 43758.5453
    return x - math.floor(x)


def paint_banner(p: QPainter, rect: QRectF, item: str, now: float = 0.0, radius: float = 10.0, dim: float = 1.0,
                 gold: int = 0) -> None:
    """A profile banner filling `rect` (rounded corners). `gold` 1-3: it turned gold with the hours it was worn."""
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
    elif base == "jungle":                                     # layers of swaying leaves, light through them
        for i in range(10):
            p.setBrush(alpha("#FFF6B0", 0.05 + 0.04 * math.sin(now + i)))
            x = L + _rand(i, 7) * w
            beam = QPainterPath(QPointF(x, T))
            beam.lineTo(x + w * 0.06, T)
            beam.lineTo(x + w * 0.16, rect.bottom())
            beam.lineTo(x + w * 0.1, rect.bottom())
            p.drawPath(beam)
        for k, col in enumerate(("#0F5B2A", "#1B8A3E", "#2ECC71")):
            for i in range(9):
                cx = L + (i + 0.5) / 9 * w + math.sin(now * 0.9 + i + k) * w * 0.012
                cy = (T + h * (0.15 + 0.35 * k)) if i % 2 else (rect.bottom() - h * (0.1 + 0.2 * k))
                p.save()
                p.translate(cx, cy)
                p.rotate(-35 + _rand(i, k) * 70 + math.sin(now * 1.2 + i) * 6)
                p.setBrush(QColor(col))
                p.drawEllipse(QPointF(0, 0), h * 0.09, h * 0.24)
                p.restore()
    elif base == "sakura":                                     # a branch and falling pink petals
        p.setPen(QPen(QColor("#4A2230"), max(1.5, h * 0.04)))
        path = QPainterPath(QPointF(L, T + h * 0.25))
        path.cubicTo(QPointF(L + w * 0.3, T + h * 0.05), QPointF(L + w * 0.5, T + h * 0.4), QPointF(L + w * 0.85, T + h * 0.15))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(12):
            t2 = (i + 0.5) / 12
            pt = path.pointAtPercent(t2)
            p.setBrush(QColor("#FFC1DE" if i % 2 else "#FF8FC2"))
            p.drawEllipse(pt, h * 0.06, h * 0.06)
        for i in range(30):
            fall = (_rand(i, 1) + now * (0.05 + _rand(i, 2) * 0.06)) % 1.0
            x = L + (_rand(i) + 0.08 * math.sin(now * 1.1 + i)) * w
            p.save()
            p.translate(x, T + fall * h)
            p.rotate(now * 90 + i * 40)
            p.setBrush(alpha("#FFC1DE", 0.85))
            p.drawEllipse(QPointF(0, 0), 2.4, 1.3)
            p.restore()
    elif base == "carbon":                                     # carbon fibre weave
        cell = max(6.0, h * 0.09)
        for gy in range(int(h / cell) + 2):
            for gx in range(int(w / cell) + 2):
                r_ = QRectF(L + gx * cell, T + gy * cell, cell, cell)
                g2 = QLinearGradient(r_.topLeft(), r_.bottomRight() if (gx + gy) % 2 else r_.bottomLeft())
                g2.setColorAt(0, alpha("#FFFFFF", 0.07))
                g2.setColorAt(1, alpha("#000000", 0.25))
                p.fillRect(r_.adjusted(0.5, 0.5, -0.5, -0.5), g2)
    elif base == "dunes":                                      # warm dunes under a low sun
        p.setBrush(alpha("#FFE2A8", 0.85))
        p.drawEllipse(QPointF(L + w * 0.78, T + h * 0.32), h * 0.16, h * 0.16)
        for k, (y0, col) in enumerate(((0.55, "#C98A4B"), (0.68, "#A86A35"), (0.82, "#7E4C24"))):
            path = QPainterPath(QPointF(L, rect.bottom()))
            for x in range(0, int(w) + 8, 8):
                path.lineTo(L + x, T + h * y0 + math.sin(x / w * 5.0 + k * 1.9) * h * 0.06)
            path.lineTo(rect.right(), rect.bottom())
            p.setBrush(QColor(col))
            p.drawPath(path)
    elif base == "honeycomb":                                  # hexagons that light up one after another
        rr = max(7.0, h * 0.13)
        dx, dy = rr * 1.73, rr * 1.5
        for gy in range(int(h / dy) + 2):
            for gx in range(int(w / dx) + 2):
                cx = L + gx * dx + (dx / 2 if gy % 2 else 0)
                cy = T + gy * dy
                glow = max(0.0, math.sin(now * 1.4 - gx * 0.45 + gy * 0.9)) ** 3
                hexp = QPainterPath()
                for n in range(7):
                    a = math.radians(60 * n + 30)
                    pt = QPointF(cx + rr * 0.92 * math.cos(a), cy + rr * 0.92 * math.sin(a))
                    hexp.lineTo(pt) if n else hexp.moveTo(pt)
                p.setPen(QPen(alpha(c2, 0.35 + 0.5 * glow), 1.1))
                p.setBrush(alpha(c2, 0.05 + 0.3 * glow))
                p.drawPath(hexp)
        p.setPen(Qt.PenStyle.NoPen)
    elif base == "comet":                                      # comets crossing a starry sky
        for i in range(30):
            p.setBrush(alpha("#FFFFFF", 0.25 + 0.5 * ((i * 37) % 10) / 10))
            p.drawEllipse(QPointF(L + (i * 97 % 1000) / 1000 * w, T + (i * 61 % 1000) / 1000 * h), 0.9, 0.9)
        for k in range(3):
            t = (now * 0.22 + k / 3) % 1.0
            head = QPointF(L - w * 0.2 + t * w * 1.4, T + h * (0.15 + 0.25 * k) + t * h * 0.35)
            tail = QPointF(head.x() - w * 0.22, head.y() - h * 0.055 * 1)
            g2 = QLinearGradient(tail, head)
            g2.setColorAt(0, alpha(c2, 0.0))
            g2.setColorAt(1, alpha("#FFFFFF", 0.9))
            p.setPen(QPen(g2, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(tail, head)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(head, 2.2, 2.2)
    elif base == "deepsea":                                    # light rays from above, bubbles rising
        for k in range(5):
            x0 = L + w * (0.1 + 0.2 * k) + math.sin(now * 0.4 + k) * w * 0.03
            ray = QPainterPath(QPointF(x0 - w * 0.03, T))
            ray.lineTo(x0 + w * 0.03, T)
            ray.lineTo(x0 + w * 0.12, rect.bottom())
            ray.lineTo(x0 - w * 0.02, rect.bottom())
            g2 = QLinearGradient(QPointF(0, T), QPointF(0, rect.bottom()))
            g2.setColorAt(0, alpha(c2, 0.28))
            g2.setColorAt(1, alpha(c2, 0.0))
            p.setBrush(g2)
            p.drawPath(ray)
        for i in range(16):
            t = (now * (0.12 + (i % 4) * 0.03) + i * 0.137) % 1.0
            x = L + (i * 131 % 1000) / 1000 * w + math.sin(now * 2 + i) * 3
            p.setPen(QPen(alpha("#BFF4FF", 0.7 * (1 - t)), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(x, rect.bottom() - t * h), 1.5 + (i % 3), 1.5 + (i % 3))
        p.setPen(Qt.PenStyle.NoPen)
    elif base == "city":                                       # a skyline at night, windows switching on and off
        p.setBrush(alpha("#FFE9A8", 0.9))
        p.drawEllipse(QPointF(L + w * 0.85, T + h * 0.22), h * 0.09, h * 0.09)
        x, i = L, 0
        while x < rect.right():
            bw = w * (0.05 + ((i * 53) % 7) / 100)
            bh = h * (0.35 + ((i * 29) % 9) / 16)
            top_ = rect.bottom() - bh
            p.setBrush(QColor("#0A0D1A") if i % 2 else QColor("#121633"))
            p.drawRect(QRectF(x, top_, bw, bh))
            for wy in range(int(bh / 7)):
                for wx in range(max(1, int(bw / 6))):
                    lit = math.sin(i * 7.1 + wy * 3.3 + wx * 1.7 + math.floor(now * 0.5 + (i + wx) * 0.13)) > 0.35
                    if lit:
                        p.setBrush(alpha("#FFD36B", 0.85))
                        p.drawRect(QRectF(x + 2 + wx * 6, top_ + 3 + wy * 7, 2.4, 3))
            x += bw + 1
            i += 1
    elif base == "neon":                                       # glowing tubes that pulse
        for k, (col, y0) in enumerate((("#FF2BD6", 0.3), ("#2EF2FF", 0.55), ("#B6FF2E", 0.8))):
            pulse = 0.55 + 0.45 * math.sin(now * 2.2 + k * 2.1)
            path = QPainterPath(QPointF(L - 4, T + h * y0))
            for x in range(0, int(w) + 10, 10):
                path.lineTo(L + x, T + h * y0 + (h * 0.08 if (x // 40) % 2 else -h * 0.08))
            p.setBrush(Qt.BrushStyle.NoBrush)
            for width, a in ((7, 0.12), (3.5, 0.35), (1.6, 1.0)):
                p.setPen(QPen(alpha(col, a * pulse), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                              Qt.PenJoinStyle.RoundJoin))
                p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
    elif base == "fireflies":                                  # a dark forest with drifting lights
        for k in range(9):
            x = L + w * (k / 8)
            p.setBrush(QColor("#06140C"))
            tri = QPainterPath(QPointF(x, T + h * (0.25 + 0.1 * (k % 3))))
            tri.lineTo(x - w * 0.07, rect.bottom())
            tri.lineTo(x + w * 0.07, rect.bottom())
            tri.closeSubpath()
            p.drawPath(tri)
        for i in range(22):
            x = L + ((i * 89 % 1000) / 1000 + 0.03 * math.sin(now * 0.5 + i)) * w
            y = T + ((i * 47 % 1000) / 1000 * 0.8 + 0.1 + 0.04 * math.cos(now * 0.7 + i * 2)) * h
            a = max(0.0, math.sin(now * 1.7 + i * 1.3))
            gl = QRadialGradient(QPointF(x, y), 6)
            gl.setColorAt(0, alpha("#E8FF7A", 0.9 * a))
            gl.setColorAt(1, alpha("#E8FF7A", 0.0))
            p.setBrush(gl)
            p.drawEllipse(QPointF(x, y), 6, 6)
    elif base == "storm":                                      # heavy clouds, rain and lightning
        flash = max(0.0, 1 - ((now * 0.45) % 1.0) * 9)        # a bright flash once every ~2 seconds
        for k in range(7):
            p.setBrush(alpha("#2A3550", 0.85))
            p.drawEllipse(QPointF(L + w * (k / 6) + math.sin(now * 0.2 + k) * 6, T + h * 0.12), w * 0.13, h * 0.32)
        p.setPen(QPen(alpha("#9FC3FF", 0.35), 1))
        for i in range(40):
            t = (now * 1.6 + i * 0.173) % 1.0
            x = L + (i * 113 % 1000) / 1000 * w
            p.drawLine(QPointF(x - t * 6, T + h * 0.3 + t * h * 0.7), QPointF(x - t * 6 - 3, T + h * 0.3 + t * h * 0.7 + 7))
        if flash > 0:
            bolt = QPainterPath(QPointF(L + w * 0.62, T + h * 0.25))
            for dxf, dyf in ((-0.04, 0.2), (0.03, 0.18), (-0.05, 0.22), (0.02, 0.2)):
                cur = bolt.currentPosition()
                bolt.lineTo(cur.x() + w * dxf, cur.y() + h * dyf)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for width, a in ((6, 0.25), (2, 1.0)):
                p.setPen(QPen(alpha("#E6F0FF", a * flash), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawPath(bolt)
            p.fillRect(rect, alpha("#CFE0FF", 0.18 * flash))
        p.setPen(Qt.PenStyle.NoPen)
    elif base == "vortex":                                     # a slowly turning spiral of light
        cen = QPointF(L + w * 0.5, T + h * 0.5)
        for arm in range(4):
            path = QPainterPath()
            for n in range(60):
                t = n / 59
                ang = arm * math.pi / 2 + t * 5.5 + now * 0.6
                rr = t * w * 0.55
                pt = QPointF(cen.x() + rr * math.cos(ang), cen.y() + rr * 0.45 * math.sin(ang))
                path.lineTo(pt) if n else path.moveTo(pt)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for width, a in ((8, 0.10), (3, 0.35), (1.2, 0.9)):
                p.setPen(QPen(alpha(c2 if arm % 2 else QColor("#FF5CC8"), a), width, Qt.PenStyle.SolidLine,
                              Qt.PenCapStyle.RoundCap))
                p.drawPath(path)
        core = QRadialGradient(cen, h * 0.4)
        core.setColorAt(0, alpha("#FFFFFF", 0.85))
        core.setColorAt(1, alpha(c2, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(core)
        p.drawEllipse(cen, h * 0.4, h * 0.4)
    else:
        _paint_banner_32(p, base, rect, c1, c2, now)
    if gold > 0:
        paint_gold(p, rect, gold, now)
    shade = QLinearGradient(rect.topLeft(), rect.bottomLeft())       # a soft shade at the bottom, for text on top
    shade.setColorAt(0.55, alpha("#000000", 0.0))
    shade.setColorAt(1.0, alpha("#000000", 0.35))
    p.fillRect(rect, shade)
    p.restore()



def _paint_banner_32(p: QPainter, base: str, rect: QRectF, c1: QColor, c2: QColor, now: float) -> None:
    """3.2 banners. The rarer, the more there is in them: Common are calm, Legendary are full scenes that move."""
    w, h = rect.width(), rect.height()
    L, T = rect.left(), rect.top()
    p.setPen(Qt.PenStyle.NoPen)
    if base == "slate":                                        # Common: two-tone slate with fine lines
        path = QPainterPath(QPointF(L + w * 0.55, T))
        path.lineTo(rect.right(), T)
        path.lineTo(rect.right(), rect.bottom())
        path.lineTo(L + w * 0.35, rect.bottom())
        p.setBrush(alpha(c2, 0.45))
        p.drawPath(path)
        p.setPen(QPen(alpha("#FFFFFF", 0.06), 1))
        for k in range(12):
            y = T + h * k / 12
            p.drawLine(QPointF(L, y), QPointF(rect.right(), y))
    elif base == "pastel":                                     # Common: soft blobs of colour
        for k, (x, y, rr, col) in enumerate(((0.2, 0.3, 0.5, "#FFD6E8"), (0.75, 0.7, 0.6, "#CFE6FF"), (0.5, 0.9, 0.4, "#E6D6FF"))):
            g = QRadialGradient(QPointF(L + w * x, T + h * y), w * rr)
            g.setColorAt(0, alpha(col, 0.8))
            g.setColorAt(1, alpha(col, 0.0))
            p.setBrush(g)
            p.drawEllipse(QPointF(L + w * x, T + h * y), w * rr, w * rr)
    elif base == "tides":                                      # Rare: tides rolling in with white foam
        for k in range(5):
            path = QPainterPath(QPointF(L, rect.bottom()))
            pts = []
            for x in range(0, int(w) + 8, 5):
                y = T + h * (0.3 + k * 0.14) + math.sin(x / w * 5 + now * (1 + k * 0.25) + k * 1.3) * h * 0.06
                pts.append(QPointF(L + x, y))
                path.lineTo(L + x, y)
            path.lineTo(rect.right(), rect.bottom())
            p.setBrush(alpha(mix(c2, QColor("#FFFFFF"), 0.1 * k), 0.15 + k * 0.08))
            p.drawPath(path)
            p.setPen(QPen(alpha("#FFFFFF", 0.35 - k * 0.04), 1.2))
            crest = QPainterPath(pts[0])
            for pt in pts[1:]:
                crest.lineTo(pt)
            p.drawPath(crest)
            p.setPen(Qt.PenStyle.NoPen)
    elif base == "canyon":                                     # Rare: layered red rock under a low sun
        sun = QRadialGradient(QPointF(L + w * 0.75, T + h * 0.3), h * 0.5)
        sun.setColorAt(0, alpha("#FFE2A8", 0.85))
        sun.setColorAt(1, alpha("#FFE2A8", 0.0))
        p.setBrush(sun)
        p.drawEllipse(QPointF(L + w * 0.75, T + h * 0.3), h * 0.5, h * 0.5)
        for k in range(4):
            path = QPainterPath(QPointF(L, rect.bottom()))
            for x in range(0, int(w) + 10, 10):
                step = (x // 40) % 2
                y = T + h * (0.35 + k * 0.15) + (h * 0.05 if step else 0) + _rand(x, k) * h * 0.02
                path.lineTo(L + x, y)
            path.lineTo(rect.right(), rect.bottom())
            p.setBrush(mix(c2, QColor("#2A0E06"), 0.2 + k * 0.22))
            p.drawPath(path)
    elif base == "koi":                                        # Epic: a pond with ripples and three koi swimming
        for k in range(3):
            t = (now * 0.25 + k / 3) % 1.0
            cen = QPointF(L + w * (0.25 + 0.25 * k), T + h * (0.35 + 0.2 * (k % 2)))
            p.setPen(QPen(alpha("#BFF8F0", 0.35 * (1 - t)), 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(cen, w * 0.18 * t, h * 0.18 * t)
        p.setPen(Qt.PenStyle.NoPen)
        for k, col in enumerate(("#FF7A2E", "#FFFFFF", "#FFC14D")):
            ang = now * (0.35 + 0.08 * k) + k * 2.1
            cx, cy = L + w * 0.5 + math.cos(ang) * w * 0.32, T + h * 0.5 + math.sin(ang) * h * 0.28
            head = math.degrees(ang) + 90
            p.save()
            p.translate(cx, cy)
            p.rotate(head)
            fl = h * 0.12
            body = QPainterPath(QPointF(0, -fl))
            body.cubicTo(fl * 0.5, -fl * 0.5, fl * 0.4, fl * 0.6, 0, fl * 1.1)
            body.cubicTo(-fl * 0.4, fl * 0.6, -fl * 0.5, -fl * 0.5, 0, -fl)
            p.setBrush(QColor(col))
            p.drawPath(body)
            tail = QPainterPath(QPointF(0, fl * 1.0))
            sway = math.sin(now * 6 + k) * fl * 0.3
            tail.lineTo(-fl * 0.45 + sway, fl * 1.6)
            tail.lineTo(fl * 0.45 + sway, fl * 1.6)
            tail.closeSubpath()
            p.drawPath(tail)
            if col == "#FFFFFF":
                p.setBrush(QColor("#E8384F"))
                p.drawEllipse(QPointF(0, -fl * 0.3), fl * 0.25, fl * 0.3)
            p.restore()
        for k in range(4):                                     # lily pads
            pad = QPointF(L + w * _rand(k, 41), T + h * _rand(k, 42))
            p.setBrush(alpha("#2E8B3E", 0.75))
            p.drawPie(QRectF(pad.x() - h * 0.1, pad.y() - h * 0.08, h * 0.2, h * 0.16), 30 * 16, 300 * 16)
    elif base == "synthwave":                                  # Epic: striped sun, palms and a moving grid
        horizon = T + h * 0.55
        sun = QPointF(L + w * 0.5, horizon)
        sg = QLinearGradient(0, horizon - h * 0.42, 0, horizon)
        sg.setColorAt(0, QColor("#FFD36B"))
        sg.setColorAt(1, QColor("#FF2BD6"))
        p.setBrush(sg)
        p.drawEllipse(sun, h * 0.42, h * 0.42)
        p.save()
        disc = QPainterPath()
        disc.addEllipse(sun, h * 0.42, h * 0.42)
        p.setClipPath(disc, Qt.ClipOperation.IntersectClip)
        for k in range(5):
            p.fillRect(QRectF(sun.x() - h * 0.45, horizon - h * (0.05 + 0.07 * k), h * 0.9, h * 0.012 * (k + 1)), c1)
        p.restore()
        p.fillRect(QRectF(L, horizon, w, h), mix(c1, QColor("#000000"), 0.3))
        p.setPen(QPen(alpha("#2EF2FF", 0.7), 1))
        off = (now * 0.6) % 1.0
        for k in range(-12, 13):
            p.drawLine(QPointF(L + w / 2 + k * w * 0.025, horizon), QPointF(L + w / 2 + k * w * 0.14, rect.bottom()))
        for k in range(7):
            f = ((k + off) / 7) ** 2
            p.drawLine(QPointF(L, horizon + f * (rect.bottom() - horizon)), QPointF(rect.right(), horizon + f * (rect.bottom() - horizon)))
        p.setPen(Qt.PenStyle.NoPen)
        for side in (0.12, 0.88):                              # two palm trees
            base_x = L + w * side
            p.setPen(QPen(QColor("#0A0418"), max(1.5, h * 0.03), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            trunk = QPainterPath(QPointF(base_x, horizon + h * 0.05))
            trunk.quadTo(base_x + (h * 0.05 if side < 0.5 else -h * 0.05), T + h * 0.35, base_x, T + h * 0.2)
            p.drawPath(trunk)
            for k in range(5):
                ang = math.radians(-170 + k * 40) + math.sin(now * 1.5 + k) * 0.05
                leaf = QPainterPath(QPointF(base_x, T + h * 0.2))
                leaf.quadTo(base_x + math.cos(ang) * h * 0.18, T + h * 0.2 + math.sin(ang) * h * 0.1 - h * 0.05,
                            base_x + math.cos(ang) * h * 0.3, T + h * 0.2 + math.sin(ang) * h * 0.18 + h * 0.04)
                p.drawPath(leaf)
            p.setPen(Qt.PenStyle.NoPen)
    elif base == "supernova":                                  # Legendary: a star exploding, rings and debris
        cen = QPointF(L + w * 0.5, T + h * 0.5)
        for k in range(70):                                    # background stars
            p.setBrush(alpha("#FFFFFF", 0.2 + 0.6 * _rand(k, 5) * (0.6 + 0.4 * math.sin(now * 2 + k))))
            p.drawEllipse(QPointF(L + w * _rand(k, 1), T + h * _rand(k, 2)), 0.9, 0.9)
        cycle = (now * 0.35) % 1.0
        for k in range(3):                                     # shock rings racing out
            t = (cycle + k / 3) % 1.0
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(alpha(mix(c2, QColor("#FFFFFF"), 0.3), 0.8 * (1 - t)), 1.5 + 3 * (1 - t)))
            p.drawEllipse(cen, w * 0.6 * t, h * 0.6 * t * 0.9)
        p.setPen(Qt.PenStyle.NoPen)
        for k in range(48):                                    # debris flying out
            ang = _rand(k, 7) * math.tau
            t = (now * (0.2 + 0.3 * _rand(k, 8)) + _rand(k, 9)) % 1.0
            pos = QPointF(cen.x() + math.cos(ang) * w * 0.55 * t, cen.y() + math.sin(ang) * h * 0.55 * t)
            p.setBrush(alpha(QColor("#FFE2A8") if k % 3 else QColor("#FF5C8A"), 1 - t))
            p.drawEllipse(pos, 1.6 * (1 - t) + 0.6, 1.6 * (1 - t) + 0.6)
        core = QRadialGradient(cen, h * 0.5)
        core.setColorAt(0, alpha("#FFFFFF", 1.0))
        core.setColorAt(0.2, alpha(c2, 0.85))
        core.setColorAt(0.6, alpha("#FF2B6B", 0.25))
        core.setColorAt(1, alpha("#FF2B6B", 0.0))
        p.setBrush(core)
        p.drawEllipse(cen, h * 0.5, h * 0.5)
        p.save()                                               # a cross of light
        p.translate(cen)
        p.rotate(now * 8)
        for k in range(4):
            p.rotate(90)
            ray = QPainterPath(QPointF(0, -1.5))
            ray.lineTo(w * 0.4, 0)
            ray.lineTo(0, 1.5)
            p.setBrush(alpha("#FFFFFF", 0.55))
            p.drawPath(ray)
        p.restore()
    elif base == "dragon":                                     # Legendary: a dragon gliding over fire and embers
        glow = QLinearGradient(rect.bottomLeft(), rect.topLeft())
        glow.setColorAt(0, alpha("#FF5A1F", 0.55))
        glow.setColorAt(0.5, alpha("#FF5A1F", 0.0))
        p.fillRect(rect, glow)
        for k in range(40):                                    # embers
            t = (now * (0.15 + 0.2 * _rand(k, 3)) + _rand(k, 4)) % 1.0
            x = L + w * _rand(k, 5) + math.sin(now + k) * 4
            y = rect.bottom() - t * h
            p.setBrush(alpha("#FFC14D" if k % 2 else "#FF5A1F", 1 - t))
            p.drawEllipse(QPointF(x, y), 1.4, 1.4)
        sweep = (now * 0.08) % 1.4 - 0.2                       # the dragon crosses the banner
        hx, hy = L + w * sweep, T + h * 0.42 + math.sin(now * 1.3) * h * 0.06
        body = QPainterPath(QPointF(hx, hy))                   # a long serpent body behind its head
        for k in range(1, 14):
            body.lineTo(hx - k * h * 0.11, hy + math.sin(now * 3 - k * 0.6) * h * 0.08)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for width, col in ((h * 0.13, QColor("#3A0A10")), (h * 0.08, c2), (h * 0.02, QColor("#FFC14D"))):
            p.setPen(QPen(col, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(body)
        p.setPen(Qt.PenStyle.NoPen)
        flap = math.sin(now * 5) * 0.5 + 0.5                   # wings
        for side in (-1, 1):
            wing = QPainterPath(QPointF(hx - h * 0.3, hy))
            wing.lineTo(hx - h * 0.15, hy + side * h * (0.25 + 0.2 * flap))
            wing.lineTo(hx - h * 0.45, hy + side * h * (0.15 + 0.15 * flap))
            wing.lineTo(hx - h * 0.62, hy + side * h * (0.3 + 0.15 * flap))
            wing.closeSubpath()
            p.setBrush(alpha("#5A0E18", 0.95))
            p.drawPath(wing)
        p.setBrush(c2)
        p.drawEllipse(QPointF(hx, hy), h * 0.07, h * 0.05)
        p.setBrush(QColor("#FFE26B"))
        p.drawEllipse(QPointF(hx + h * 0.02, hy - h * 0.012), h * 0.012, h * 0.012)
        fire = QRadialGradient(QPointF(hx + h * 0.18, hy), h * 0.16)  # a breath of fire
        fire.setColorAt(0, alpha("#FFF1B8", 0.9))
        fire.setColorAt(0.5, alpha("#FF8A3D", 0.6))
        fire.setColorAt(1, alpha("#FF3D1F", 0.0))
        p.setBrush(fire)
        p.drawEllipse(QPointF(hx + h * 0.18, hy), h * 0.18 * (0.8 + 0.2 * math.sin(now * 9)), h * 0.08)
    elif base == "wreath":                                     # limited Rare: a Christmas wreath with berries and a bow
        cen = QPointF(L + w * 0.5, T + h * 0.5)
        for k in range(36):
            ang = k / 36 * math.tau
            p.setBrush(QColor("#1F7A4A") if k % 2 else QColor("#2E9E5F"))
            p.save()
            p.translate(cen.x() + math.cos(ang) * h * 0.32, cen.y() + math.sin(ang) * h * 0.32)
            p.rotate(math.degrees(ang) + 45)
            p.drawEllipse(QPointF(0, 0), h * 0.07, h * 0.035)
            p.restore()
        for k in range(10):
            ang = k / 10 * math.tau + 0.3
            p.setBrush(QColor("#FF3B4E"))
            p.drawEllipse(QPointF(cen.x() + math.cos(ang) * h * 0.3, cen.y() + math.sin(ang) * h * 0.3), h * 0.025, h * 0.025)
        p.setBrush(QColor("#E8C26A"))
        p.drawEllipse(QPointF(cen.x() - h * 0.06, cen.y() + h * 0.3), h * 0.06, h * 0.04)
        p.drawEllipse(QPointF(cen.x() + h * 0.06, cen.y() + h * 0.3), h * 0.06, h * 0.04)
        for k in range(30):                                    # gentle snow
            t = (now * 0.08 + _rand(k, 1)) % 1.0
            p.setBrush(alpha("#FFFFFF", 0.7))
            p.drawEllipse(QPointF(L + w * _rand(k, 2) + math.sin(now + k) * 3, T + t * h), 1.2, 1.2)
    elif base == "hearth":                                     # limited Epic: a fireplace, stockings and a warm glow
        p.fillRect(QRectF(L, T, w, h), alpha("#2A120A", 0.6))
        for row in range(5):                                   # bricks
            for col in range(12):
                bx = L + (col + (0.5 if row % 2 else 0)) * w / 11
                p.setBrush(alpha("#5A2414", 0.6))
                p.drawRect(QRectF(bx, T + row * h * 0.12, w / 11 - 2, h * 0.1))
        fp = QRectF(L + w * 0.3, T + h * 0.35, w * 0.4, h * 0.65)
        p.setBrush(QColor("#0D0503"))
        p.drawRoundedRect(fp, 4, 4)
        for k in range(5):                                     # flames
            fx = fp.left() + fp.width() * (0.2 + 0.15 * k)
            fh = fp.height() * (0.45 + 0.2 * math.sin(now * 6 + k * 1.7))
            flame = QPainterPath(QPointF(fx - fp.width() * 0.06, fp.bottom()))
            flame.quadTo(fx - fp.width() * 0.08, fp.bottom() - fh * 0.5, fx, fp.bottom() - fh)
            flame.quadTo(fx + fp.width() * 0.08, fp.bottom() - fh * 0.5, fx + fp.width() * 0.06, fp.bottom())
            g = QLinearGradient(0, fp.bottom(), 0, fp.bottom() - fh)
            g.setColorAt(0, QColor("#FF5A1F"))
            g.setColorAt(1, QColor("#FFE26B"))
            p.setBrush(g)
            p.drawPath(flame)
        warm = QRadialGradient(fp.center(), w * 0.45)
        warm.setColorAt(0, alpha("#FF8A3D", 0.35 + 0.1 * math.sin(now * 4)))
        warm.setColorAt(1, alpha("#FF8A3D", 0.0))
        p.setBrush(warm)
        p.drawRect(rect)
        p.setBrush(QColor("#3A1A10"))                          # the mantel and three stockings
        p.drawRect(QRectF(L + w * 0.22, T + h * 0.28, w * 0.56, h * 0.07))
        for k, col in enumerate(("#E8384F", "#FFFFFF", "#1F7A4A")):
            sx = L + w * (0.3 + 0.2 * k)
            sway = math.sin(now * 2 + k) * 1.5
            p.setBrush(QColor(col))
            p.drawRoundedRect(QRectF(sx + sway, T + h * 0.35, w * 0.04, h * 0.22), 2, 2)
            p.drawEllipse(QPointF(sx + sway + w * 0.03, T + h * 0.56), w * 0.035, h * 0.05)
    elif base == "northstar":                                  # limited Legendary: the North Star over snowy pines and an aurora
        for k in range(3):                                     # aurora curtains
            path = QPainterPath(QPointF(L, T + h * 0.2))
            for x in range(0, int(w) + 8, 6):
                path.lineTo(L + x, T + h * (0.18 + 0.06 * k) + math.sin(x / w * 5 + now * 0.7 + k) * h * 0.08)
            path.lineTo(rect.right(), T)
            path.lineTo(L, T)
            g = QLinearGradient(0, T, 0, T + h * 0.4)
            g.setColorAt(0, alpha(["#3DFFB0", "#4FE3FF", "#B36BFF"][k], 0.0))
            g.setColorAt(1, alpha(["#3DFFB0", "#4FE3FF", "#B36BFF"][k], 0.25))
            p.setBrush(g)
            p.drawPath(path)
        for k in range(60):
            p.setBrush(alpha("#FFFFFF", 0.3 + 0.5 * _rand(k, 3) * (0.5 + 0.5 * math.sin(now * 2 + k))))
            p.drawEllipse(QPointF(L + w * _rand(k, 1), T + h * 0.6 * _rand(k, 2)), 0.9, 0.9)
        star = QPointF(L + w * 0.62, T + h * 0.28)
        glow = QRadialGradient(star, h * 0.45)
        glow.setColorAt(0, alpha("#FFF6C8", 0.75))
        glow.setColorAt(1, alpha("#FFF6C8", 0.0))
        p.setBrush(glow)
        p.drawEllipse(star, h * 0.45, h * 0.45)
        p.save()
        p.translate(star)
        p.rotate(math.sin(now * 0.8) * 4)
        shape = QPainterPath()
        for k in range(8):
            ang = math.radians(-90 + 45 * k)
            rr = h * (0.2 if k % 2 == 0 else 0.05) * (1.0 if k % 4 == 0 else 0.7 if k % 2 == 0 else 1.0)
            pt = QPointF(math.cos(ang) * rr, math.sin(ang) * rr)
            shape.lineTo(pt) if k else shape.moveTo(pt)
        shape.closeSubpath()
        p.setBrush(QColor("#FFF6C8"))
        p.drawPath(shape)
        p.restore()
        p.setBrush(alpha("#E8F4FF", 0.9))                       # snowy ground
        snow = QPainterPath(QPointF(L, rect.bottom()))
        for x in range(0, int(w) + 10, 10):
            snow.lineTo(L + x, T + h * 0.85 + math.sin(x / w * 4) * h * 0.04)
        snow.lineTo(rect.right(), rect.bottom())
        p.drawPath(snow)
        for k in range(9):                                     # pines
            px = L + w * (0.04 + k * 0.12) + _rand(k, 6) * 8
            ph = h * (0.3 + 0.2 * _rand(k, 7))
            tree = QPainterPath(QPointF(px, T + h * 0.9 - ph))
            tree.lineTo(px + ph * 0.25, T + h * 0.9)
            tree.lineTo(px - ph * 0.25, T + h * 0.9)
            tree.closeSubpath()
            p.setBrush(QColor("#0B2A1A"))
            p.drawPath(tree)
            p.setBrush(alpha("#FFFFFF", 0.8))
            cap = QPainterPath(QPointF(px, T + h * 0.9 - ph))
            cap.lineTo(px + ph * 0.07, T + h * 0.9 - ph * 0.72)
            cap.lineTo(px - ph * 0.07, T + h * 0.9 - ph * 0.72)
            cap.closeSubpath()
            p.drawPath(cap)


GOLD_NAMES = {1: "Gold I", 2: "Gold II", 3: "Gold III"}


def paint_gold(p: QPainter, rect: QRectF, level: int, now: float = 0.0) -> None:
    """A banner worn for many hours turns gold: I a gold tint and edge, II a richer gold with a moving shine,
    III solid gold with a bright sweep and sparkles."""
    level = max(0, min(3, int(level)))
    if not level:
        return
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    tint = QLinearGradient(rect.topLeft(), rect.bottomRight())
    k = (0.45, 0.7, 0.95)[level - 1]
    tint.setColorAt(0, alpha("#FFD978", k))
    tint.setColorAt(0.5, alpha("#E0A93A", k))
    tint.setColorAt(1, alpha("#8A5A14", k))
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Overlay)
    p.fillRect(rect, tint)
    if level >= 2:                                         # the colours of the banner turn to gold
        gray = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gray.setColorAt(0, alpha("#FFE9A8", 0.5 if level == 2 else 0.95))
        gray.setColorAt(1, alpha("#C98F2A", 0.5 if level == 2 else 0.95))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
        p.fillRect(rect, gray)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        p.fillRect(rect, alpha("#6B4510", 0.35 if level == 2 else 0.7))
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    if level >= 2:                                         # a band of light sweeping across
        t = (now * (0.25 if level == 2 else 0.4)) % 1.6 - 0.3
        x = rect.left() + t * rect.width()
        sweep = QLinearGradient(QPointF(x - rect.width() * 0.15, 0), QPointF(x + rect.width() * 0.15, 0))
        sweep.setColorAt(0, alpha("#FFFFFF", 0.0))
        sweep.setColorAt(0.5, alpha("#FFF6D8", 0.35 if level == 2 else 0.55))
        sweep.setColorAt(1, alpha("#FFFFFF", 0.0))
        p.fillRect(rect, sweep)
    if level >= 3:                                         # sparkles
        for i in range(10):
            a = max(0.0, math.sin(now * 2.3 + i * 1.9))
            if a < 0.2:
                continue
            c = QPointF(rect.left() + (i * 157 % 1000) / 1000 * rect.width(),
                        rect.top() + (i * 83 % 1000) / 1000 * rect.height() * 0.8 + rect.height() * 0.05)
            s = 2.5 + 2.5 * a
            star = QPainterPath(QPointF(c.x(), c.y() - s))
            for pt in ((c.x() + s * 0.25, c.y() - s * 0.25), (c.x() + s, c.y()), (c.x() + s * 0.25, c.y() + s * 0.25),
                       (c.x(), c.y() + s), (c.x() - s * 0.25, c.y() + s * 0.25), (c.x() - s, c.y()),
                       (c.x() - s * 0.25, c.y() - s * 0.25)):
                star.lineTo(QPointF(*pt))
            star.closeSubpath()
            p.setBrush(alpha("#FFF6D8", 0.9 * a))
            p.drawPath(star)
    edge = QLinearGradient(rect.topLeft(), rect.bottomRight())
    edge.setColorAt(0, QColor("#FFE7A0"))
    edge.setColorAt(0.5, QColor("#E8C26A"))
    edge.setColorAt(1, QColor("#9C6B1E"))
    p.setPen(QPen(edge, (1.2, 2.0, 2.8)[level - 1]))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))      # clipped to the rounded banner
    p.restore()


def gold_steps_text(steps, minutes: int) -> str:
    """'Gold I in 6 h' / 'Gold III' for the progress of one banner."""
    hours = [int(h) for h in (steps or [])][:3]
    level = sum(1 for h in hours if minutes >= h * 60)
    if level >= len(hours) or not hours:
        return tr(GOLD_NAMES.get(level, "")) if level else ""
    left = max(1, math.ceil((hours[level] * 60 - minutes) / 60))
    return tr("{gold} in {h} h", gold=tr(GOLD_NAMES[level + 1]), h=left)

_FRAME_COLS = {"silver": ("#F2F6FA", "#8A96A3"), "bronze": ("#FFB067", "#8A4B1E"), "ink": ("#0B0E10", "#FFFFFF"),
               "neon": ("#2EF2FF", "#2EF2FF"), "dashed": ("#FFFFFF", "#9AA4AD"), "twin": ("#FF5CB8", "#2EC5FF"),
               "laurel": ("#FFD36B", "#B8862B"), "crown": ("#FFD36B", "#B8862B"), "spikes": ("#E6EEF5", "#6E7C88"),
               "flame": ("#FFC94D", "#FF3D1F"), "orbit": ("#B36BFF", "#4FE3FF"), "rainbow": ("#FF5CC8", "#2EC5FF"),
               "frost": ("#E8F6FF", "#7FC8FF"), "vine": ("#7BE07B", "#2E8B3E"), "star": ("#FFE9A8", "#FFC94D"), "halo": ("#FFFFFF", "#C9B6FF"),
               "wood": ("#B97A4A", "#6B3E1F"), "pulse": ("#3DDC84", "#0F6B3A"), "thorns": ("#3A5A2E", "#C8283D"),
               "gears": ("#D9DEE3", "#8A939C"), "phoenix": ("#FFC14D", "#FF4B1F"), "holly": ("#1F7A4A", "#E8384F"),
               "snowflake": ("#E8F6FF", "#7FC8FF"), "northstar": ("#FFE9A8", "#E8C26A")}


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
    elif base == "vine":                                      # a vine wrapped around, with leaves that sway
        p.setPen(QPen(c2, wd * 0.55))
        p.drawEllipse(ring)
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(10):
            a = i / 10 * math.tau
            lc = QPointF(c.x() + math.cos(a) * r, c.y() + math.sin(a) * r)
            p.save()
            p.translate(lc)
            p.rotate(math.degrees(a) + 45 + math.sin(now * 2 + i) * 12)
            p.setBrush(c1 if i % 2 else c2)
            p.drawEllipse(QPointF(wd * 0.6, 0), wd * 0.9, wd * 0.45)
            p.restore()
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
    if base in ("wood", "pulse", "thorns", "gears", "phoenix", "holly", "snowflake", "northstar"):
        _paint_frame_32(p, base, c, r, wd, c1, c2, now)
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


def _paint_frame_32(p: QPainter, base: str, c: QPointF, r: float, wd: float, c1: QColor, c2: QColor, now: float) -> None:
    """3.2 frames, simple for Common, busy for Legendary."""
    ring = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if base == "wood":                                        # Common: a wooden ring with its grain
        p.setPen(QPen(c2, wd * 1.2))
        p.drawEllipse(ring)
        p.setPen(QPen(c1, wd * 0.6))
        p.drawEllipse(ring)
        p.setPen(QPen(alpha("#3A1E0C", 0.6), max(1.0, wd * 0.12)))
        for k in range(8):
            a0 = k * 45 + 10
            p.drawArc(ring.adjusted(-wd * 0.2, -wd * 0.2, wd * 0.2, wd * 0.2), a0 * 16, 18 * 16)
    elif base == "pulse":                                     # Rare: a light runs round the ring
        p.setPen(QPen(alpha(c2, 0.9), wd))
        p.drawEllipse(ring)
        for k in range(3):
            ang = now * 2.4 - k * 0.25
            col = alpha(c1, 1.0 - k * 0.3)
            p.setPen(QPen(col, wd * (1.2 - 0.2 * k), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(ring, int(math.degrees(-ang) * 16), 24 * 16)
    elif base == "thorns":                                    # Epic: a thorny vine and a red rose
        p.setPen(QPen(c1, wd * 0.6))
        p.drawEllipse(ring)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#22361C"))
        for k in range(16):
            a = k / 16 * math.tau + 0.1
            o = 1 if k % 2 else -1
            base_pt = QPointF(c.x() + math.cos(a) * r, c.y() + math.sin(a) * r)
            tip = QPointF(c.x() + math.cos(a + o * 0.12) * (r + o * wd * 1.4), c.y() + math.sin(a + o * 0.12) * (r + o * wd * 1.4))
            thorn = QPainterPath(QPointF(base_pt.x() + math.sin(a) * wd * 0.3, base_pt.y() - math.cos(a) * wd * 0.3))
            thorn.lineTo(tip)
            thorn.lineTo(base_pt.x() - math.sin(a) * wd * 0.3, base_pt.y() + math.cos(a) * wd * 0.3)
            thorn.closeSubpath()
            p.drawPath(thorn)
        rose = QPointF(c.x() + r * 0.72, c.y() - r * 0.72)
        bloom = 1 + 0.06 * math.sin(now * 2)
        for k in range(5):
            a = k / 5 * math.tau + now * 0.3
            p.setBrush(mix(c2, QColor("#FF8095"), 0.2 * (k % 2)))
            p.drawEllipse(QPointF(rose.x() + math.cos(a) * wd * 0.6, rose.y() + math.sin(a) * wd * 0.6), wd * 0.8 * bloom, wd * 0.8 * bloom)
        p.setBrush(QColor("#7A0F1E"))
        p.drawEllipse(rose, wd * 0.5, wd * 0.5)
    elif base == "gears":                                     # Epic: two cog rings turning against each other
        for k, (rr, teeth, speed, col) in enumerate(((r + wd * 0.5, 24, 12, c1), (r - wd * 0.4, 18, -16, c2))):
            path = QPainterPath()
            for n in range(teeth * 4 + 1):
                ang = math.radians(now * speed + n * 360 / (teeth * 4))
                rad = rr + (wd * 0.45 if (n % 4) in (1, 2) else 0)
                pt = QPointF(c.x() + rad * math.cos(ang), c.y() + rad * math.sin(ang))
                path.lineTo(pt) if n else path.moveTo(pt)
            p.setPen(QPen(col, max(1.0, wd * 0.4), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c1)
        for k in range(6):
            a = math.radians(k * 60 + now * 12)
            p.drawEllipse(QPointF(c.x() + math.cos(a) * r, c.y() + math.sin(a) * r), wd * 0.18, wd * 0.18)
    elif base == "phoenix":                                   # Legendary: a ring of fire and two burning wings
        for k in (3.0, 2.0, 1.2):
            p.setPen(QPen(alpha(c2, 0.14 * (4 - k)), wd * k))
            p.drawEllipse(ring)
        p.setPen(QPen(c1, wd * 0.6))
        p.drawEllipse(ring)
        p.setPen(Qt.PenStyle.NoPen)
        beat = math.sin(now * 3) * 0.12
        for side in (-1, 1):                                  # feathers fan out from each side, never over the face
            for k in range(5):
                root = QPointF(c.x() + side * (r + wd * 0.3), c.y() + r * (0.25 - k * 0.12))
                tip = QPointF(c.x() + side * (r + wd * (4.2 - k * 0.5)), c.y() - r * (0.15 + k * 0.2 + beat))
                feather = QPainterPath(root)
                feather.quadTo(c.x() + side * (r + wd * 2.6), c.y() + r * (0.2 - k * 0.1), tip.x(), tip.y())
                feather.quadTo(c.x() + side * (r + wd * 1.4), c.y() - r * (0.05 + k * 0.12), root.x(), root.y() - wd * 0.6)
                feather.closeSubpath()
                g = QLinearGradient(root, tip)
                g.setColorAt(0, alpha(c2, 0.95))
                g.setColorAt(1, alpha(c1, 0.75))
                p.setBrush(g)
                p.drawPath(feather)
        for k in range(10):                                   # sparks
            t = (now * 0.6 + k / 10) % 1.0
            a = k / 10 * math.tau
            p.setBrush(alpha("#FFE9A8", 1 - t))
            p.drawEllipse(QPointF(c.x() + math.cos(a) * (r + wd * 3 * t), c.y() + math.sin(a) * (r + wd * 3 * t) - t * wd * 2),
                          wd * 0.2, wd * 0.2)
    elif base == "holly":                                     # limited Rare: holly leaves and red berries
        p.setPen(QPen(c1, wd * 0.8))
        p.drawEllipse(ring)
        p.setPen(Qt.PenStyle.NoPen)
        for k in range(6):
            a = k / 6 * math.tau - math.pi / 2
            lc = QPointF(c.x() + math.cos(a) * r, c.y() + math.sin(a) * r)
            for side in (-1, 1):
                p.save()
                p.translate(lc)
                p.rotate(math.degrees(a) + 90 + side * 35)
                p.setBrush(QColor("#1F7A4A"))
                p.drawEllipse(QPointF(0, -wd * 0.9), wd * 0.45, wd * 0.95)
                p.restore()
            p.setBrush(c2)
            p.drawEllipse(lc, wd * 0.35, wd * 0.35)
    elif base == "snowflake":                                 # limited Epic: an icy ring with turning snowflakes
        p.setPen(QPen(alpha(c2, 0.8), wd))
        p.drawEllipse(ring)
        p.setPen(QPen(c1, wd * 0.35))
        p.drawEllipse(ring)
        for k in range(4):
            a = k / 4 * math.tau + now * 0.4
            fc = QPointF(c.x() + math.cos(a) * r, c.y() + math.sin(a) * r)
            p.save()
            p.translate(fc)
            p.rotate(now * 40 + k * 20)
            p.setPen(QPen(QColor("#FFFFFF"), max(1.0, wd * 0.18), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for j in range(6):
                p.rotate(60)
                p.drawLine(QPointF(0, 0), QPointF(0, -wd * 1.2))
                p.drawLine(QPointF(0, -wd * 0.7), QPointF(wd * 0.3, -wd * 0.95))
                p.drawLine(QPointF(0, -wd * 0.7), QPointF(-wd * 0.3, -wd * 0.95))
            p.restore()
    elif base == "northstar":                                 # limited Legendary: gold ring, the star on top, orbiting light
        g = QLinearGradient(ring.topLeft(), ring.bottomRight())
        g.setColorAt(0, QColor("#FFF6C8"))
        g.setColorAt(0.5, c2)
        g.setColorAt(1, QColor("#FFF6C8"))
        p.setPen(QPen(g, wd))
        p.drawEllipse(ring)
        p.setPen(Qt.PenStyle.NoPen)
        top = QPointF(c.x(), c.y() - r - wd * 0.6)
        glow = QRadialGradient(top, wd * 3.5)
        glow.setColorAt(0, alpha("#FFF6C8", 0.9))
        glow.setColorAt(1, alpha("#FFF6C8", 0.0))
        p.setBrush(glow)
        p.drawEllipse(top, wd * 3.5, wd * 3.5)
        star = QPainterPath()
        for k in range(8):
            ang = math.radians(-90 + 45 * k)
            rr = wd * (2.2 if k % 2 == 0 else 0.6)
            pt = QPointF(top.x() + math.cos(ang) * rr, top.y() + math.sin(ang) * rr)
            star.lineTo(pt) if k else star.moveTo(pt)
        star.closeSubpath()
        p.setBrush(QColor("#FFFFFF"))
        p.drawPath(star)
        for k in range(3):
            a = now * (1.2 + k * 0.3) + k * 2
            p.setBrush(alpha("#FFE9A8", 0.9))
            p.drawEllipse(QPointF(c.x() + math.cos(a) * (r + wd * 0.9), c.y() + math.sin(a) * (r + wd * 0.9)), wd * 0.22, wd * 0.22)


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
