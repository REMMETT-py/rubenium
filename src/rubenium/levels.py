"""4.0: levels 0 to 100, XP and the level badges.

The server gives XP (games, Mini Golf, Coinflip, trades, quests, online time, XP coupons) and keeps the level. The app
only shows it: the XP bar across the top of the online menu, the level-up scene, the badge of every 5 levels, the
Levels part of the Inventory (pick the badge your profile shows) and XP coupons, opened like a scratch card.

Badges carry no number: they grow from a plain bronze coin (level 0) to a radiant crowned crest (level 100). Every
5 levels adds something: a new metal, rings, a gem, wings, rays, orbiting sparks, a stronger aura."""
import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QGridLayout, QWidget

from .core import S, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, mix, sfx, tr, ui
from .widgets import Button, Label, heading, hbox, vbox

# one look per 5 levels: (name, main colour, light colour, gem colour)
LEVEL_TIERS = [
    ("Copper", "#9A5B34", "#D9925E", None), ("Bronze", "#8C6A3C", "#D8B07A", None),
    ("Iron", "#6B7580", "#B8C2CC", None), ("Steel", "#7C8B99", "#DDE6EE", "#4FC3FF"),
    ("Silver", "#9EA8B3", "#F2F5F8", "#4FC3FF"), ("Gold", "#B8892E", "#FFE08A", "#FF5C8A"),
    ("Jade", "#1E8C5E", "#7DFFC0", "#E8FFF3"), ("Emerald", "#0F7A4A", "#5CFF9E", "#FFFFFF"),
    ("Sapphire", "#1D4FA8", "#7FB4FF", "#FFFFFF"), ("Amethyst", "#6B2FB3", "#C98BFF", "#FFE9FF"),
    ("Ruby", "#A8173A", "#FF7A96", "#FFE2E8"), ("Topaz", "#C46A12", "#FFC066", "#FFF6D8"),
    ("Platinum", "#A9B6C2", "#FFFFFF", "#9AE6FF"), ("Obsidian", "#1A1424", "#8F6BFF", "#D9C8FF"),
    ("Aurora", "#0E5B6E", "#5CFFE0", "#FFFFFF"), ("Solar", "#C24E00", "#FFD24D", "#FFFFFF"),
    ("Nebula", "#4A1A7A", "#FF8AE0", "#FFFFFF"), ("Crystal", "#3E8FB0", "#E6FBFF", "#FFFFFF"),
    ("Celestial", "#2B3FA6", "#FFE9A8", "#FFFFFF"), ("Mythic", "#8A1240", "#FFB3D9", "#FFFFFF"),
    ("Legend", "#B8892E", "#FFF2B8", "#FFFFFF"),
]


def xp_need(l: int) -> int:
    return 50 + 12 * l + int(0.6 * l * l)


def level_of_xp(x: int) -> int:
    """The same curve as the server (rb_xp_need)."""
    total, lv = 0, 0
    while lv < 100 and total + xp_need(lv) <= x:
        total += xp_need(lv)
        lv += 1
    return lv


def tier_of(level: int) -> int:
    return max(0, min(20, int(level) // 5))


def badge_name(level: int) -> str:
    return tr(LEVEL_TIERS[tier_of(level)][0])


def _lv_star(c: QPointF, r_out: float, r_in: float, n: int, rot: float = -90.0) -> QPainterPath:
    path = QPainterPath()
    for k in range(n * 2):
        ang = math.radians(rot + 180.0 / n * k)
        rr = r_out if k % 2 == 0 else r_in
        pt = QPointF(c.x() + math.cos(ang) * rr, c.y() + math.sin(ang) * rr)
        path.lineTo(pt) if k else path.moveTo(pt)
    path.closeSubpath()
    return path


def _lv_poly(c: QPointF, r: float, n: int, rot: float = -90.0) -> QPainterPath:
    path = QPainterPath()
    for k in range(n):
        ang = math.radians(rot + 360.0 / n * k)
        pt = QPointF(c.x() + math.cos(ang) * r, c.y() + math.sin(ang) * r)
        path.lineTo(pt) if k else path.moveTo(pt)
    path.closeSubpath()
    return path


def _lv_shield(c: QPointF, r: float) -> QPainterPath:
    path = QPainterPath(QPointF(c.x(), c.y() - r))
    path.cubicTo(c.x() + r * 0.55, c.y() - r * 0.95, c.x() + r * 0.9, c.y() - r * 0.8, c.x() + r * 0.9, c.y() - r * 0.55)
    path.cubicTo(c.x() + r * 0.9, c.y() + r * 0.25, c.x() + r * 0.45, c.y() + r * 0.75, c.x(), c.y() + r)
    path.cubicTo(c.x() - r * 0.45, c.y() + r * 0.75, c.x() - r * 0.9, c.y() + r * 0.25, c.x() - r * 0.9, c.y() - r * 0.55)
    path.cubicTo(c.x() - r * 0.9, c.y() - r * 0.8, c.x() - r * 0.55, c.y() - r * 0.95, c.x(), c.y() - r)
    return path


def _lv_metal(c: QPointF, r: float, main: QColor, light: QColor) -> QLinearGradient:
    g = QLinearGradient(QPointF(c.x() - r, c.y() - r), QPointF(c.x() + r, c.y() + r))
    g.setColorAt(0.0, light)
    g.setColorAt(0.45, main)
    g.setColorAt(0.55, mix(main, QColor("#000000"), 0.25))
    g.setColorAt(1.0, mix(light, main, 0.4))
    return g


def paint_level_badge(p: QPainter, c: QPointF, size: float, level: int, now: float = 0.0, aura: bool = True,
                      locked: bool = False) -> None:
    """The badge of a level (every 5 levels share one). size = the full width it may use, aura included."""
    t = tier_of(level)
    _name, m, l, gem = LEVEL_TIERS[t]
    main, light = QColor(m), QColor(l)
    if locked:
        main, light = QColor("#3A4048"), QColor("#5A626B")
    r = size * (0.30 + 0.05 * t / 10) if t < 10 else size * 0.27     # winged badges keep room for their wings
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    # aura: from level 20, stronger and pulsing as levels go up; level 100 shifts through colours
    if aura and t >= 4 and not locked:
        k = (t - 3) / 17
        pulse = 0.75 + 0.25 * math.sin(now * (1.5 + k * 2))
        col = QColor.fromHsvF((now * 0.08) % 1.0, 0.55, 1.0) if t == 20 else light
        g = QRadialGradient(c, size * 0.5)
        g.setColorAt(0, alpha(col, 0.55 * k * pulse))
        g.setColorAt(0.55, alpha(col, 0.22 * k * pulse))
        g.setColorAt(1, alpha(col, 0.0))
        p.setBrush(g)
        p.drawEllipse(c, size * 0.5, size * 0.5)
    # rays turning behind (level 70 and up)
    if t >= 14 and not locked:
        p.save()
        p.translate(c)
        p.rotate(now * (12 + t))
        n = 8 + (t - 14) * 2
        for k in range(n):
            p.rotate(360 / n)
            ray = QPainterPath(QPointF(0, -r * 0.2))
            ray.lineTo(-r * 0.09, -size * 0.48)
            ray.lineTo(r * 0.09, -size * 0.48)
            ray.closeSubpath()
            p.setBrush(alpha(light, 0.12 + 0.03 * (t - 14)))
            p.drawPath(ray)
        p.restore()
    # wings (level 50 and up), bigger with every tier, two pairs at 90+
    if t >= 10:
        span = min(r * (1.0 + 0.06 * (t - 10)), size * 0.47 - r * 0.72)
        for pair in range(2 if t >= 18 else 1):
            for side in (-1, 1):
                for f in range(3 + min(3, (t - 10) // 2)):
                    a = math.radians(-10 - f * 16 - pair * 30)
                    root = QPointF(c.x() + side * r * 0.72, c.y() - r * 0.05 + pair * r * 0.35)
                    tip = QPointF(root.x() + side * math.cos(a) * span * (1 - f * 0.1), root.y() + math.sin(a) * span * (1 - f * 0.1))
                    feather = QPainterPath(root)
                    feather.quadTo(QPointF((root.x() + tip.x()) / 2, root.y() - r * 0.25), tip)
                    feather.quadTo(QPointF((root.x() + tip.x()) / 2, root.y() + r * 0.1), QPointF(root.x(), root.y() + r * 0.18))
                    feather.closeSubpath()
                    g = QLinearGradient(root, tip)
                    g.setColorAt(0, mix(main, light, 0.3))
                    g.setColorAt(1, alpha(light, 0.9))
                    p.setBrush(g)
                    p.drawPath(feather)
    # the body: coin, hexagon, shield, star-shield, crest
    if t < 4:
        body = QPainterPath()
        body.addEllipse(c, r, r)
    elif t < 8:
        body = _lv_poly(c, r * 1.08, 6)
    elif t < 12:
        body = _lv_shield(c, r * 1.1)
    elif t < 16:
        body = _lv_star(c, r * 1.18, r * 0.92, 8, -90 + 22.5)
    else:
        body = _lv_star(c, r * 1.22, r * 0.95, 10)
    p.setBrush(_lv_metal(c, r, main, light))
    p.drawPath(body)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(alpha(light, 0.9), max(1.0, size * 0.018)))
    p.drawPath(body)
    # inner rings: one more every 15 levels
    p.setPen(QPen(alpha(mix(light, main, 0.5), 0.8), max(1.0, size * 0.012)))
    for k in range(min(3, t // 3)):
        rr = r * (0.78 - k * 0.12)
        p.drawEllipse(c, rr, rr)
    # engraved marks round the edge from level 15
    if t >= 3:
        p.setPen(QPen(alpha(light, 0.55), max(1.0, size * 0.01)))
        n = 12 + t
        for k in range(n):
            a = math.tau * k / n
            p.drawLine(QPointF(c.x() + math.cos(a) * r * 0.86, c.y() + math.sin(a) * r * 0.86),
                       QPointF(c.x() + math.cos(a) * r * 0.93, c.y() + math.sin(a) * r * 0.93))
    # the centre: a star at first, a cut gem from level 15
    p.setPen(Qt.PenStyle.NoPen)
    if gem and not locked:
        gc = QColor(gem)
        gem_r = r * (0.28 + 0.02 * min(t, 10))
        cut = _lv_poly(c, gem_r, 8 if t >= 12 else 6, -90 + (22.5 if t >= 12 else 30))
        gg = QRadialGradient(QPointF(c.x() - gem_r * 0.3, c.y() - gem_r * 0.3), gem_r * 1.4)
        gg.setColorAt(0, QColor("#FFFFFF"))
        gg.setColorAt(0.35, gc)
        gg.setColorAt(1, mix(gc, main, 0.6))
        p.setBrush(gg)
        p.drawPath(cut)
        p.setPen(QPen(alpha("#FFFFFF", 0.5), max(1.0, size * 0.008)))
        for k in range(8 if t >= 12 else 6):
            a = math.radians(-90 + (45 if t >= 12 else 60) * k + (22.5 if t >= 12 else 30))
            p.drawLine(c, QPointF(c.x() + math.cos(a) * gem_r, c.y() + math.sin(a) * gem_r))
        p.setPen(Qt.PenStyle.NoPen)
    else:
        p.setBrush(alpha(light, 0.9))
        p.drawPath(_lv_star(c, r * 0.36, r * 0.15, 5))
    # crown (level 80 and up)
    if t >= 16:
        cw, ch = r * 0.9, r * 0.42
        top = c.y() - r * 1.18
        crown = QPainterPath(QPointF(c.x() - cw / 2, top + ch))
        for k, (dx, dy) in enumerate(((-0.5, 0.15), (-0.32, 0.55), (-0.16, 0.0), (0.0, 0.5), (0.16, 0.0), (0.32, 0.55), (0.5, 0.15))):
            crown.lineTo(c.x() + dx * cw, top + dy * ch)
        crown.lineTo(c.x() + cw / 2, top + ch)
        crown.closeSubpath()
        g = QLinearGradient(QPointF(c.x(), top), QPointF(c.x(), top + ch))
        g.setColorAt(0, QColor("#FFF6C8"))
        g.setColorAt(1, QColor("#C8962E"))
        p.setBrush(g)
        p.drawPath(crown)
        for dx in (-0.16, 0.0, 0.16):
            p.setBrush(QColor(gem or "#FF5C8A"))
            p.drawEllipse(QPointF(c.x() + dx * cw, top + ch * 0.62), r * 0.05, r * 0.05)
    # orbiting sparks (level 60 and up)
    if t >= 12 and not locked:
        n = t - 10
        for k in range(n):
            a = now * (0.8 + 0.05 * k) + k * math.tau / n
            orbit = size * (0.40 + 0.04 * (k % 2))
            pt = QPointF(c.x() + math.cos(a) * orbit, c.y() + math.sin(a) * orbit * 0.55)
            p.setBrush(alpha(light, 0.9))
            p.drawEllipse(pt, size * 0.012 + 0.6, size * 0.012 + 0.6)
    # a shine passing over it (level 25 and up)
    if t >= 5 and not locked:
        sweep = (now * 0.35) % 2.0 - 0.5
        p.save()
        p.setClipPath(body)
        g = QLinearGradient(QPointF(c.x() - r + sweep * 2 * r, c.y() - r), QPointF(c.x() - r + sweep * 2 * r + r * 0.5, c.y() + r))
        g.setColorAt(0, alpha("#FFFFFF", 0.0))
        g.setColorAt(0.5, alpha("#FFFFFF", 0.35))
        g.setColorAt(1, alpha("#FFFFFF", 0.0))
        p.setBrush(g)
        p.drawRect(QRectF(c.x() - r * 1.3, c.y() - r * 1.3, r * 2.6, r * 2.6))
        p.restore()
    # level 100: stars twinkling all round
    if t == 20 and not locked:
        rnd = random.Random(7)
        for k in range(14):
            a = rnd.random() * math.tau
            d = size * (0.30 + rnd.random() * 0.2)
            tw = 0.5 + 0.5 * math.sin(now * 3 + k)
            p.setBrush(alpha("#FFFFFF", 0.3 + 0.6 * tw))
            p.drawPath(_lv_star(QPointF(c.x() + math.cos(a) * d, c.y() + math.sin(a) * d), size * 0.025 * (0.6 + tw * 0.6),
                             size * 0.008, 4, 0))
    p.restore()


class LevelBadge(QWidget):
    """A level badge on its own (animated when it has an aura)."""
    clicked = pyqtSignal()

    def __init__(self, level: int, size: int = 64, locked: bool = False, animate: bool = True) -> None:
        super().__init__()
        self.level, self.locked, self.selected = level, locked, False
        self.setFixedSize(S(size), S(size))
        self._t = QTimer(self)
        self._t.setInterval(66)                    # 4.0: 15 images a second are enough for a slow aura
        self._t.timeout.connect(self.update)
        if animate and tier_of(level) >= 4 and not locked:
            self._t.start()

    def set_level(self, level: int, locked: bool = False) -> None:
        self.level, self.locked = level, locked
        if tier_of(level) >= 4 and not locked:
            self._t.start()
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        if self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.selected:
            p.setPen(QPen(ui.accent, S(2)))
            p.setBrush(alpha(ui.accent, 0.10))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), S(10), S(10))
        paint_level_badge(p, QPointF(self.width() / 2, self.height() / 2 + S(1)), self.width() * 0.92, self.level,
                          time.monotonic(), locked=self.locked)


class XPBar(QWidget):
    """Across the top of the online menu: the badge, the level, the bar towards the next level (animated)."""
    clicked = pyqtSignal()

    def __init__(self, ctx, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(S(38))
        self.shown = self._target()                # what the bar shows now (moves towards the real value)
        self.flash = 0.0
        self._t = QTimer(self)
        self._t.setInterval(33)
        self._t.timeout.connect(self._step)
        self._t.start()
        ctx.econ.xp_changed.connect(self._changed)
        self.setToolTip(tr("Your level. Click to see your level badges."))

    def _target(self) -> float:
        x = self.ctx.econ.xp
        need = max(1, int(x.get("need") or 1))
        return int(x.get("level") or 0) + min(1.0, int(x.get("into") or 0) / need)

    def _changed(self) -> None:
        self.flash = 1.0

    SHINE_EVERY, SHINE_S = 6.0, 1.2              # 4.0: the light runs along the bar now and then, not non-stop

    def _step(self) -> None:
        """4.0: repaint only what moves. The bar sits at the top of the online menu, and every repaint of it made
        the whole see-through window repaint too: 30 times a second, even when nothing changed."""
        if not self.isVisible():
            return
        tgt = self._target()
        moving = abs(tgt - self.shown) > 0.001
        if moving:
            self.shown += (tgt - self.shown) * 0.12 if tgt > self.shown else (tgt - self.shown)
        flashing = self.flash > 0
        self.flash = max(0.0, self.flash - 0.03)
        shining = (time.monotonic() % self.SHINE_EVERY) < self.SHINE_S + 0.05
        self._n = getattr(self, "_n", 0) + 1
        if moving or flashing or shining:
            self.update()
        elif self._n % 3 == 0 and tier_of(self._badge()) >= 4:          # the badge's aura: 10 images a second
            h = self.height()
            self.update(0, 0, int(h * 1.1), h)

    def _badge(self) -> int:
        x = self.ctx.econ.xp
        lvl = int(self.shown)
        return int(x.get("badge") if x.get("badge") is not None else (lvl // 5) * 5)

    def mouseReleaseEvent(self, e) -> None:
        if self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x = self.ctx.econ.xp
        lvl = int(self.shown)
        frac = self.shown - lvl
        now = time.monotonic()
        h = self.height()
        badge = int(x.get("badge") if x.get("badge") is not None else (lvl // 5) * 5)
        paint_level_badge(p, QPointF(h / 2, h / 2), h * 1.05, badge, now)
        p.setFont(font(12.5, QFont.Weight.ExtraBold))
        p.setPen(QColor(TEXT))
        label = tr("Level {n}", n=lvl)
        lw = p.fontMetrics().horizontalAdvance(label)
        p.drawText(QRectF(h + S(6), 0, lw + S(4), h * 0.55), int(Qt.AlignmentFlag.AlignBottom), label)
        need = int(x.get("need") or 0)
        into = int(x.get("into") or 0) if lvl == int(x.get("level") or 0) else int(frac * max(1, need))
        right = tr("MAX") if lvl >= 100 else f"{into:,} / {need:,} XP".replace(",", " ")
        p.setFont(font(9.5, QFont.Weight.Bold))
        p.setPen(QColor(TEXT_DIM))
        rw = p.fontMetrics().horizontalAdvance(right)
        p.drawText(QRectF(self.width() - rw - S(2), 0, rw + S(2), h * 0.55), int(Qt.AlignmentFlag.AlignBottom), right)
        bar = QRectF(h + S(6), h * 0.62, self.width() - h - S(8), S(8))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.08))
        p.drawRoundedRect(bar, bar.height() / 2, bar.height() / 2)
        fill = QRectF(bar.left(), bar.top(), max(bar.height(), bar.width() * (1.0 if lvl >= 100 else frac)), bar.height())
        g = QLinearGradient(fill.topLeft(), fill.topRight())
        g.setColorAt(0, mix(ui.accent, QColor("#FFFFFF"), 0.1))
        g.setColorAt(1, mix(ui.accent, QColor("#FFE08A"), 0.45))
        p.setBrush(g)
        p.drawRoundedRect(fill, bar.height() / 2, bar.height() / 2)
        shine = (now % self.SHINE_EVERY) / self.SHINE_S * 1.4 - 0.2      # a light running along the bar
        sx = fill.left() + fill.width() * shine
        if fill.left() < sx < fill.right():
            sg = QLinearGradient(QPointF(sx - S(20), 0), QPointF(sx + S(20), 0))
            sg.setColorAt(0, alpha("#FFFFFF", 0))
            sg.setColorAt(0.5, alpha("#FFFFFF", 0.45))
            sg.setColorAt(1, alpha("#FFFFFF", 0))
            p.setBrush(sg)
            p.drawRoundedRect(fill, bar.height() / 2, bar.height() / 2)
        if self.flash > 0:
            p.setPen(QPen(alpha("#FFE08A", self.flash), S(2)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(bar.adjusted(-S(2), -S(2), S(2), S(2)), bar.height(), bar.height())


# ================================================================ the level-up scene
def play_level_up(ctx, level: int, old: int) -> None:
    """A short scene over the screen (never takes a click): the badge rises, rays, LEVEL UP, the new level."""
    from PyQt6.QtGui import QGuiApplication
    from .onlinewin import FxOverlay, spark_burst
    w = ctx.window
    try:
        card = w.card_global() if w.expanded else w.ball.frameGeometry()
    except Exception:  # noqa: BLE001
        card = None
    screen = QGuiApplication.screenAt(card.center()) if card is not None else None
    screen = screen or QGuiApplication.primaryScreen()
    fx = FxOverlay(ctx, screen)
    centre = fx.local(card.center()) if card is not None else QPointF(fx.width() / 2, fx.height() / 2)
    new_badge = tier_of(level) > tier_of(old)
    size = S(170)
    sfx.tune("levelup")

    def paint(p: QPainter, k: float, now: float) -> None:
        fade = min(1.0, k / 0.08) * (1.0 - max(0.0, (k - 0.85) / 0.15))
        p.setOpacity(fade)
        g = QRadialGradient(centre, S(260))
        g.setColorAt(0, QColor(0, 0, 0, 170))
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(centre, S(260), S(260))
        rise = 1 - (1 - min(1.0, k / 0.25)) ** 3
        c = QPointF(centre.x(), centre.y() - S(20) - S(40) * (1 - rise))
        p.save()                                             # rays
        p.translate(c)
        p.rotate(now * 30)
        for i in range(16):
            p.rotate(22.5)
            ray = QPainterPath(QPointF(0, 0))
            ray.lineTo(-S(8), -S(200) * rise)
            ray.lineTo(S(8), -S(200) * rise)
            ray.closeSubpath()
            p.setBrush(alpha(ui.accent, 0.10))
            p.drawPath(ray)
        p.restore()
        p.save()
        p.translate(c)
        sc = 0.4 + 0.6 * rise + 0.05 * math.sin(now * 6) * (1 - k)
        p.scale(sc, sc)
        paint_level_badge(p, QPointF(0, 0), size, level, now)
        p.restore()
        p.setFont(font(26, QFont.Weight.Black, 3))
        p.setPen(QColor("#FFE08A"))
        p.drawText(QRectF(c.x() - S(200), c.y() + size * 0.5, S(400), S(36)), int(Qt.AlignmentFlag.AlignCenter), tr("LEVEL UP"))
        p.setFont(font(15, QFont.Weight.Bold))
        p.setPen(QColor(TEXT))
        sub = tr("Level {n}", n=level) + (("  ·  " + tr("New badge: {name}", name=badge_name(level))) if new_badge else "")
        p.drawText(QRectF(c.x() - S(220), c.y() + size * 0.5 + S(36), S(440), S(24)), int(Qt.AlignmentFlag.AlignCenter), sub)

    from .collection import CASE_NAMES
    opened = [tr(CASE_NAMES.get(c["id"], c["id"])) for c in ctx.econ.cases
              if old < int(c.get("min_level") or 0) <= level]          # cases unlocked by these levels (2 to 5)

    def unlocked(p: QPainter, k: float, _now: float) -> None:
        if not opened or k < 0.35:
            return
        p.setOpacity(min(1.0, (k - 0.35) / 0.12) * (1.0 - max(0.0, (k - 0.85) / 0.15)))
        r = QRectF(centre.x() - S(210), centre.y() + size * 0.5 + S(70), S(420), S(30))
        p.setPen(QPen(QColor("#FFE08A"), S(1.4)))
        p.setBrush(QColor(40, 30, 6, 220))
        p.drawRoundedRect(r, S(15), S(15))
        p.setPen(QColor("#FFE08A"))
        p.setFont(font(12, QFont.Weight.Bold))
        p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), tr("Unlocked: {what}", what=", ".join(opened)))

    fx.add(3.4, paint)
    if opened:
        fx.add(3.4, unlocked)
    spark_burst(fx, centre, ui.accent, n=40, reach=S(240), dur=1.1)
    spark_burst(fx, centre, QColor("#FFE08A"), n=24, reach=S(180), dur=0.9)
    ctx.toast(tr("Level {n}!", n=level) + (" " + tr("New badge unlocked") if new_badge else "")
              + ("  ·  " + tr("Unlocked: {what}", what=", ".join(opened)) if opened else ""))


# ================================================================ the first explanation
class LevelIntro(QWidget):
    """Shown once after the update: what XP is, how to earn it, levels and badges."""

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self.setFixedWidth(ctx.window.page_w())
        lay = vbox(self, 8)
        top = hbox(spacing=10)
        for lv in (0, 25, 50, 100):
            top.addWidget(LevelBadge(lv, 56))
        top.addStretch(1)
        lay.addLayout(top)
        lay.addWidget(Label(tr("New: levels and XP"), 16, bold=True))
        w = self.width()
        for title, text in (
                (tr("XP"), tr("Earn XP by playing, trading and being online.")),
                (tr("Badges"), tr("A new badge every 5 levels. Pick yours in Inventory > Levels."))):
            lay.addWidget(Label(title, 12, TEXT, bold=True))
            lay.addWidget(Label(text, 10.5, TEXT_DIM, wrap_w=w))
        ok = Button(tr("Got it"), "primary", 34)
        ok.clicked.connect(self._close)
        lay.addWidget(ok)

    def _close(self) -> None:
        self.ctx.cfg["xp_intro"] = True
        self.ctx.cfg.save()
        self.ctx.window.unembed(self)
        self.deleteLater()
        if hasattr(self.ctx, "offer_og_coupon"):
            self.ctx.offer_og_coupon()


# ================================================================ XP coupons
COUPONS = {"coupon:common": ("Common XP coupon", 150, "#9AA4AD"), "coupon:uncommon": ("Uncommon XP coupon", 400, "#3DDC84"),
           "coupon:rare": ("Rare XP coupon", 1000, "#4FC3FF"), "coupon:epic": ("Epic XP coupon", 2500, "#B36BFF"),
           "coupon:og": ("OG XP coupon", 0, "#E8C26A")}


def coupon_xp_text(item: str) -> str:
    name, xp, _c = COUPONS.get(item, ("XP coupon", 0, "#FFFFFF"))
    return tr("Up to level 5") if item == "coupon:og" else tr("{n} XP", n=f"{xp:,}".replace(",", " "))


def paint_coupon(p: QPainter, r: QRectF, item: str, now: float = 0.0, label: bool = True) -> None:
    """A ticket with a torn edge, its colour, XP and a star (label=False: the scratch card writes its own)."""
    name, xp, col = COUPONS.get(item, ("XP coupon", 0, "#FFFFFF"))
    c = QColor(col)
    path = QPainterPath()
    rad = r.height() * 0.12
    path.addRoundedRect(r, rad, rad)
    notch = QPainterPath()
    for side in (r.left(), r.right()):
        notch.addEllipse(QPointF(side, r.center().y()), r.height() * 0.12, r.height() * 0.12)
    path = path.subtracted(notch)
    g = QLinearGradient(r.topLeft(), r.bottomRight())
    g.setColorAt(0, mix(c, QColor("#FFFFFF"), 0.25))
    g.setColorAt(1, mix(c, QColor("#000000"), 0.35))
    p.setPen(QPen(alpha("#FFFFFF", 0.5), max(1.0, r.height() * 0.02)))
    p.setBrush(g)
    p.drawPath(path)
    p.setPen(QPen(alpha("#FFFFFF", 0.35), max(1.0, r.height() * 0.015), Qt.PenStyle.DashLine))
    x = r.left() + r.width() * 0.32
    p.drawLine(QPointF(x, r.top() + r.height() * 0.12), QPointF(x, r.bottom() - r.height() * 0.12))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(alpha("#FFFFFF", 0.9))
    p.drawPath(_lv_star(QPointF(r.left() + r.width() * 0.16, r.center().y()), r.height() * 0.24, r.height() * 0.1, 5))
    if label:
        p.setPen(QColor("#FFFFFF"))
        p.setFont(font(max(6.0, r.height() / S(1) * 0.20), QFont.Weight.Black, 1))
        p.drawText(QRectF(x + r.width() * 0.04, r.top(), r.width() * 0.62, r.height() * 0.55), int(Qt.AlignmentFlag.AlignBottom), "XP")
        p.setFont(font(max(5.0, r.height() / S(1) * 0.13), QFont.Weight.Bold))
        p.drawText(QRectF(x + r.width() * 0.04, r.top() + r.height() * 0.55, r.width() * 0.62, r.height() * 0.35),
                   int(Qt.AlignmentFlag.AlignTop), "OG" if item == "coupon:og" else f"+{xp}")
    if item in ("coupon:epic", "coupon:og"):                    # a shine for the best ones
        sweep = (now * 0.5) % 2.0 - 0.5
        p.save()
        p.setClipPath(path)
        sg = QLinearGradient(QPointF(r.left() + sweep * r.width(), r.top()), QPointF(r.left() + sweep * r.width() + r.width() * 0.2, r.bottom()))
        sg.setColorAt(0, alpha("#FFFFFF", 0))
        sg.setColorAt(0.5, alpha("#FFFFFF", 0.4))
        sg.setColorAt(1, alpha("#FFFFFF", 0))
        p.setBrush(sg)
        p.drawRect(r)
        p.restore()


class ScratchCoupon(QWidget):
    """Scratch the silver off with the mouse (or press Reveal) to see the XP. The server already decided it.
    4.1: the silver is one picture the mouse erases (the same work at the first and the thousandth stroke) and the
    press is kept here, so dragging scratches instead of moving the menu."""
    revealed = pyqtSignal()
    CELL = 12                                       # the grid that measures how much is scratched

    def __init__(self, item: str) -> None:
        super().__init__()
        self.item = item
        self.setFixedHeight(S(120))
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.done = False
        self.text = coupon_xp_text(item)
        self.foil = None                            # QImage of the silver, made at the first paint
        self.cells: set = set()
        self.total = 1
        self.last = None
        self._t = QTimer(self)                      # the coupon's gentle shine
        self._t.setInterval(50)
        self._t.timeout.connect(self.update)

    def showEvent(self, _e) -> None:
        self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()

    def _area(self) -> QRectF:
        r = QRectF(self.rect()).adjusted(S(4), S(4), -S(4), -S(4))
        return r.adjusted(r.width() * 0.33, S(6), -S(8), -S(6))

    def _make_foil(self) -> None:
        a = self._area()
        dpr = self.devicePixelRatioF()
        img = QImage(max(1, int(a.width() * dpr)), max(1, int(a.height() * dpr)), QImage.Format.Format_ARGB32_Premultiplied)
        img.setDevicePixelRatio(dpr)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(0, 0, a.width(), a.height())
        g = QLinearGradient(box.topLeft(), box.bottomRight())
        g.setColorAt(0, QColor("#C9CED4"))
        g.setColorAt(0.5, QColor("#8A929B"))
        g.setColorAt(1, QColor("#D9DEE3"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(box, S(8), S(8))
        p.setPen(QColor("#4A525B"))
        p.setFont(font(10, QFont.Weight.Bold))
        p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), tr("Scratch here"))
        p.end()
        self.foil = img
        c = S(self.CELL)
        self.total = max(1, int(a.width() // c) * int(a.height() // c))

    def resizeEvent(self, _e) -> None:
        self.foil = None
        self.cells.clear()

    def mousePressEvent(self, e) -> None:
        e.accept()                                  # never let the drag reach the window
        if self.done:
            return
        self.last = e.position()
        self._scratch(self.last)

    def mouseMoveEvent(self, e) -> None:
        e.accept()
        if self.done or self.last is None:
            return
        a, b = self.last, e.position()
        steps = max(1, int(math.hypot(b.x() - a.x(), b.y() - a.y()) / S(4)))
        for k in range(1, steps + 1):
            self._scratch(QPointF(a.x() + (b.x() - a.x()) * k / steps, a.y() + (b.y() - a.y()) * k / steps))
        self.last = b
        if len(self.cells) / self.total > 0.45:
            self.reveal()

    def mouseReleaseEvent(self, e) -> None:
        e.accept()
        self.last = None

    def _scratch(self, pos: QPointF) -> None:
        if self.foil is None:
            self._make_foil()
        a = self._area()
        local = pos - a.topLeft()
        if not QRectF(0, 0, a.width(), a.height()).adjusted(-S(12), -S(12), S(12), S(12)).contains(local):
            return
        rad = S(12)
        p = QPainter(self.foil)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0))
        p.drawEllipse(local, rad, rad)
        p.end()
        c = S(self.CELL)
        cols, rows = int(a.width() // c), int(a.height() // c)
        for dx in (-rad * 0.6, 0, rad * 0.6):
            for dy in (-rad * 0.6, 0, rad * 0.6):
                cx, cy = int((local.x() + dx) // c), int((local.y() + dy) // c)
                if 0 <= cx < cols and 0 <= cy < rows:
                    self.cells.add((cx, cy))
        self.update(a.toAlignedRect().adjusted(-2, -2, 2, 2))

    def reveal(self) -> None:
        if not self.done:
            self.done = True
            self.last = None
            sfx.tune("coupon")
            self.update()
            self.revealed.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(S(4), S(4), -S(4), -S(4))
        paint_coupon(p, r, self.item, time.monotonic(), label=False)
        p.setPen(QColor("#FFFFFF"))
        box = self._area().adjusted(S(6), 0, -S(6), 0)
        size = 20.0
        while size > 9:                             # the prize always fits under the silver
            f = font(size, QFont.Weight.Black)
            p.setFont(f)
            if p.fontMetrics().horizontalAdvance(self.text) <= box.width():
                break
            size -= 1
        p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), self.text)
        if self.done:
            return
        if self.foil is None:
            self._make_foil()
        p.drawImage(self._area().topLeft(), self.foil)


class CouponOpen(QWidget):
    """Opening one XP coupon: scratch, reveal, the bar fills (and the level-up scenes play)."""

    def __init__(self, ctx, instance: str, item: str) -> None:
        super().__init__()
        self.ctx, self.instance, self.item = ctx, instance, item
        self.setFixedWidth(ctx.window.page_w())
        lay = vbox(self, 8)
        name = COUPONS.get(item, ("XP coupon", 0, ""))[0]
        lay.addWidget(Label(tr(name), 16, bold=True))
        if item == "coupon:og":
            lay.addWidget(Label(tr("A special thank-you for our OG players. You've been here since day one, and we "
                                   "appreciate you being part of the journey. Enjoy your free XP reward!"),
                                11, "#E8C26A", wrap_w=self.width()))
        self.card = ScratchCoupon(item)
        self.card.revealed.connect(self._use)
        lay.addWidget(self.card)
        self.result = Label("", 12, TEXT, bold=True, wrap_w=self.width())
        lay.addWidget(self.result)
        line = hbox(spacing=6)
        self.reveal_btn = Button(tr("Reveal"), "primary", 32)
        self.reveal_btn.clicked.connect(self.card.reveal)
        self.close_btn = Button(tr("Close"), "ghost", 32)
        self.close_btn.clicked.connect(self._close)
        line.addWidget(self.reveal_btn, 1)
        line.addWidget(self.close_btn, 1)
        lay.addLayout(line)
        self._sent = False

    def _use(self) -> None:
        if self._sent:
            return
        self._sent = True
        self.reveal_btn.setEnabled(False)
        import uuid

        def got(ok: bool, data) -> None:
            if not ok or not isinstance(data, dict):
                self.result.set_text(tr("This coupon could not be used. Try again later."))
                return
            self.ctx.econ.take_xp(data.get("info"))
            self.result.set_text(tr("+{n} XP", n=f"{int(data.get('xp') or 0):,}".replace(",", " "))
                                 + ("  ·  " + tr("Level {n}", n=data.get("level")) if data.get("level") is not None else ""))
            self.ctx.econ.refresh()
        self.ctx.econ.call("rb_coupon_use", {"item_id": self.instance, "req": uuid.uuid4().hex}, got)

    def _close(self) -> None:
        self.ctx.window.unembed(self)
        self.deleteLater()


def open_coupon(ctx, instance: str, item: str) -> None:
    ctx.window.embed(CouponOpen(ctx, instance, item))


# ================================================================ Inventory > Levels
def build_levels(page, lay) -> None:
    """Your level, how XP comes, every level badge: pick the one your profile shows."""
    ctx = page.ctx
    x = ctx.econ.xp
    lvl = int(x.get("level") or 0)
    lay.addWidget(XPBar(ctx))
    today, cap = int(x.get("today") or 0), int(x.get("cap") or 2500)
    lay.addWidget(Label(tr("Today: {a} / {b} XP", a=today, b=cap), 10, TEXT_DIM,
                        wrap_w=page.W))
    coupons = [it for it in ctx.econ.items if str(it.get("item", "")).startswith("coupon:")]
    if coupons:
        lay.addWidget(heading(tr("XP coupons")))
        for it in coupons:
            line = hbox(spacing=8)
            tile = _CouponTile(it["item"])
            line.addWidget(tile)
            texts = QWidget()
            tl = vbox(texts, 0)
            tl.addWidget(Label(tr(COUPONS.get(it["item"], ("XP coupon",))[0]), 12, TEXT, bold=True))
            tl.addWidget(Label(coupon_xp_text(it["item"]), 10.5, TEXT_DIM))
            line.addWidget(texts, 1)
            b = Button(tr("Open"), "primary", 30)
            b.clicked.connect(lambda _=False, i=it: open_coupon(ctx, i["id"], i["item"]))
            line.addWidget(b)
            lay.addLayout(line)
    lay.addWidget(heading(tr("Level badges")))
    lay.addWidget(Label(tr("Click an unlocked badge to show it on your profile."), 10, TEXT_DIM, wrap_w=page.W))
    grid = QGridLayout()
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(S(4))
    shown = int(x.get("badge") or 0)
    tiles = []
    for i, lv in enumerate(range(0, 101, 5)):
        cell = QWidget()
        cl = vbox(cell, 0)
        b = LevelBadge(lv, 58, locked=lv > lvl, animate=lv <= lvl)
        b.selected = lv == shown
        b.setToolTip(badge_name(lv) + "  ·  " + tr("Level {n}", n=lv))
        b.clicked.connect(lambda lv=lv: _pick_badge(page, lv))
        cl.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
        cl.addWidget(Label(str(lv), 9.5, TEXT if lv <= lvl else TEXT_FAINT, align=Qt.AlignmentFlag.AlignHCenter), 0,
                     Qt.AlignmentFlag.AlignHCenter)
        grid.addWidget(cell, i // 4, i % 4)
        tiles.append(b)
    lay.addLayout(grid)
    gated = sorted((c for c in ctx.econ.cases if int(c.get("min_level") or 0) > 0), key=lambda c: int(c["min_level"]))
    if gated:                                     # 4.0: the only things levels open, all by level 5
        from .collection import CASE_NAMES
        lay.addWidget(heading(tr("Unlocks")))
        for c in gated:
            need = int(c["min_level"])
            done = lvl >= need
            lay.addWidget(Label(("✓  " if done else "🔒  ") + tr("Level {n}: {case}", n=need,
                                                               case=tr(CASE_NAMES.get(c["id"], c["id"]))),
                                11, "#5BE08A" if done else TEXT_DIM, bold=done, wrap_w=page.W))
    lay.addWidget(heading(tr("How to earn XP")))
    for text in (tr("Casino games: up to 25 XP a bet (600 a day)"), tr("Minigames: 10 to 45 XP when they pay (900 a day)"),
                 tr("Mini Golf: 40 XP a match, +30 for the winner"), tr("Coinflip: 25 XP each"), tr("Trades: 15 XP each"),
                 tr("Quests: 60 XP, sets: 150 XP"), tr("Online: 10 XP every 10 minutes"), tr("Cases: 8 XP, wheel and scratch card: 15 XP"),
                 tr("Advent calendar: 100 XP a door, 500 on the 25th"), tr("XP coupons: from cases, the wheel and scratch cards")):
        lay.addWidget(Label("•  " + text, 10.5, TEXT_DIM, wrap_w=page.W))


def _pick_badge(page, lv: int) -> None:
    ctx = page.ctx
    if lv > int(ctx.econ.xp.get("level") or 0):
        return ctx.toast(tr("Unlocks at level {n}", n=lv), "warn")

    def got(ok: bool, data) -> None:
        if ok:
            ctx.econ.take_xp(data)
            sfx.play("pick")
            ctx.reload_page()
    ctx.econ.call("rb_level_badge_set", {"which": lv}, got)


class _CouponTile(QWidget):
    def __init__(self, item: str) -> None:
        super().__init__()
        self.item = item
        self.setFixedSize(S(74), S(40))
        self._t = QTimer(self)
        self._t.setInterval(50)
        self._t.timeout.connect(self.update)
        if item in ("coupon:epic", "coupon:og"):
            self._t.start()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_coupon(p, QRectF(self.rect()).adjusted(S(2), S(2), -S(2), -S(2)), self.item, time.monotonic())
