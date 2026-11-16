"""Shop > Badges and Shop > Cases: the badge collection, the three badges on show, the vendor and the cases.

Everything here asks the server (econ.py): buying a colour, selling to the vendor, opening a case."""
import math
import random
import time

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from .badges import item_animated, paint_item, paint_secret
from .core import S, sfx, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, lang, mix, tr, ui
from .econ import CLASS_COLOURS, CLASS_NAMES, RARITY_COLOURS, RARITY_NAMES, TIERS
from .shop import GOLD_TEXT, paint_price
from .wallet import (BADGE_NAME, BADGE_ROWS, EXOTIC_IDS, GOLD_IDS, PAINTED_IDS, SHINY_IDS, TITANIUM_IDS, VARIANT_NAME,
                     badge_item, coins_text, paint_coin, variants_for)
from .widgets import Tween, draw_icon

SHOWCASE = 3
SLOTS = ("badge1", "badge2", "badge3")
CASE_NAMES = {"starter": "Starter Case", "standard": "Standard Case", "gamble": "All or Nothing",
              "painter": "Painter's Case", "premium": "Premium Case", "jackpot": "Jackpot Case",
              "titan": "Titanium Case", "vault": "Legend Vault", "mythic": "Mythic Hunt", "daily": "Daily Case"}
CASE_COLOURS = {"starter": "#7FA3B8", "standard": "#4FA8FF", "gamble": "#FF5C5C", "painter": "#FF8A3D",
                "premium": "#B36BFF", "jackpot": "#F2C14E", "titan": "#DDE6EE", "vault": "#FF5CC8", "mythic": "#35E0D0"}
CASE_FRONT = {"starter": ("heart", "clover", "note"), "standard": ("ghost", "moon", "sun"),
              "gamble": ("dice", "skull", "dice"), "painter": ("feather", "quill", "drop"),
              "premium": ("sword", "bolt", "flame"), "jackpot": ("$", "$", "$"), "titan": ("shield", "rook", "anchor"),
              "vault": ("crown", "trophy", "comet"), "mythic": ("?", "?", "?")}
CASE_NOTES = {"gamble": "Half the time: almost nothing. The other half: always Rare or better.",
              "painter": "Never a Basic badge: every badge comes in colour.",
              "jackpot": "Coins only. Most of the time a little. Once in a while: 8 000 to 16 000.",
              "titan": "The best chance of a Titanium badge.", "vault": "No Common badges inside.",
              "mythic": "The best chance of a Mythic badge. Only Epic or better inside."}
ECON = None            # set by the app at start: lets this file know which Mythic badges are still secret


def set_econ(econ) -> None:
    global ECON
    ECON = econ


def is_secret(item: str) -> bool:
    return ECON is not None and not ECON.admin and ECON.secret(item)


def show_item(p: QPainter, item: str, rect: QRectF, now: float = 0.0, effects: bool = True, dim: float = 1.0) -> None:
    """Draw a badge, or a glowing "?" when it is a Mythic badge this account never had (other items: their picture)."""
    if item and not item.startswith("badge:"):
        from .cosmetics import paint_cosmetic
        return paint_cosmetic(p, item, rect, now, effects, dim)
    if is_secret(item):
        return paint_secret(p, rect, now, effects and dim >= 0.6)
    paint_item(p, item, rect, now, effects, dim)


def worn(ctx) -> list:
    return ctx.econ.badges_worn()


def badge_label(item: str) -> str:
    _k, base, var = (item.split(":") + ["", ""])[:3]
    if is_secret(item):
        return "???"
    return f"{tr(BADGE_NAME.get(base, base))} · {tr(VARIANT_NAME.get(var, var))}"


def rarity_colour(ctx, item: str) -> QColor:
    return QColor(RARITY_COLOURS[ctx.econ.rarity(item)])


class _Shiny(QWidget):
    """A widget that repaints smoothly while it shows a shiny (very rare or gold) badge."""

    def __init__(self) -> None:
        super().__init__()
        self._shine = QTimer(self)
        self._shine.setInterval(40)
        self._shine.timeout.connect(self.update)

    def shiny(self) -> bool:
        return False

    def showEvent(self, _e) -> None:
        if self.shiny():
            self._shine.start()

    def hideEvent(self, _e) -> None:
        self._shine.stop()

    def restart(self) -> None:
        if self.isVisible() and self.shiny():
            self._shine.start()
        else:
            self._shine.stop()
        self.update()


# --------------------------------------------------------------------------- #
# Badges
# --------------------------------------------------------------------------- #
class Showcase(_Shiny):
    """The three badges shown on the music tab and on your profile. Click one to take it off."""

    def __init__(self, page) -> None:
        super().__init__()
        self.page, self.ctx = page, page.ctx
        self.setFixedHeight(S(60))
        self.setMouseTracking(True)
        self._hover = -1
        self.ctx.econ.changed.connect(self.restart)

    def _filled(self) -> list:
        return [(s, self.ctx.econ.worn(s)) for s in SLOTS if self.ctx.econ.worn(s)]

    def shiny(self) -> bool:
        return any(item_animated(i) for _s, i in self._filled())

    def _slot(self, k: int) -> QRectF:
        d = S(50)
        return QRectF(k * (d + S(8)) + 0.5, (self.height() - d) / 2, d, d)

    def mouseMoveEvent(self, e) -> None:
        k = next((k for k in range(SHOWCASE) if self._slot(k).contains(e.position())), -1)
        if k != self._hover:
            self._hover = k
            filled = 0 <= k < len(self._filled())
            self.setCursor(Qt.CursorShape.PointingHandCursor if filled else Qt.CursorShape.ArrowCursor)
            self.setToolTip(tr("Take off") if filled else "")
            self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = -1
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()
        items = self._filled()
        k = next((k for k in range(SHOWCASE) if self._slot(k).contains(e.position())), -1)
        if 0 <= k < len(items) and e.button() == Qt.MouseButton.LeftButton:
            sfx.play("pick")
            self.ctx.econ.wear(items[k][0], "")

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        items = self._filled()
        now = time.monotonic()
        for k in range(SHOWCASE):
            r = self._slot(k)
            if k < len(items):
                item = items[k][1]
                col = rarity_colour(self.ctx, item)
                p.setPen(QPen(alpha(col, 0.75 if k == self._hover else 0.45), 1.3))
                p.setBrush(alpha(col, 0.10))
                p.drawRoundedRect(r, S(12), S(12))
                paint_item(p, item, r.adjusted(S(14), S(14), -S(14), -S(14)), now)
            else:
                p.setPen(QPen(alpha("#FFFFFF", 0.14), 1.2, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r, S(12), S(12))
                p.setPen(QPen(alpha("#FFFFFF", 0.22), S(1.6)))
                c = r.center()
                p.drawLine(QPointF(c.x() - S(6), c.y()), QPointF(c.x() + S(6), c.y()))
                p.drawLine(QPointF(c.x(), c.y() - S(6)), QPointF(c.x(), c.y() + S(6)))
        ec = self.ctx.econ
        right = QRectF(self._slot(SHOWCASE - 1).right() + S(14), 0, 0, self.height())
        right.setRight(self.width())
        total = sum(1 for v in ec.catalog.values() if v.get("kind") == "badge") or 870
        have = len({i["item"] for i in ec.items if i["item"].startswith("badge:")})
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10, QFont.Weight.DemiBold))
        p.drawText(QRectF(right.left(), right.top() + S(10), right.width(), S(16)),
                   int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), tr("Collected"))
        p.setPen(QColor(TEXT))
        p.setFont(font(15, QFont.Weight.Bold))
        p.drawText(QRectF(right.left(), right.top() + S(26), right.width(), S(24)),
                   int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), f"{have} / {total}")


class BadgeGrid(_Shiny):
    """Every badge, in five rows: Common, Rare, Epic, Legendary, Mythic. Each shows the best colour you have.
    One you no longer have is greyed out; a Mythic you never had is a glowing question mark."""
    COLS = 6

    def __init__(self, page, idents=None) -> None:
        super().__init__()
        self.page, self.ctx = page, page.ctx
        self.cw, self.ch, self.head = page.W / self.COLS, S(60), S(26)
        self.cells: list = []                      # (base, rect)
        self.heads: list = []                      # (rarity, y, bases)
        y = 0.0
        for rarity, bases in BADGE_ROWS:
            self.heads.append((rarity, y, bases))
            y += self.head
            for i, base in enumerate(bases):
                self.cells.append((base, QRectF((i % self.COLS) * self.cw, y + (i // self.COLS) * self.ch, self.cw, self.ch)))
            y += ((len(bases) + self.COLS - 1) // self.COLS) * self.ch + S(6)
        self.idents = [b for b, _r in self.cells]
        self.setFixedSize(page.W, int(y))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self._hover = -1
        self.ctx.econ.changed.connect(self.restart)

    def state(self, base: str) -> tuple:
        """(colours owned, best owned colour or '', a colour owned before or '')"""
        ec = self.ctx.econ
        have = [v for v in variants_for(base) if ec.owns(badge_item(base, v))]
        before = next((v for v in variants_for(base) if ec.had(badge_item(base, v))), "")
        return have, (have[0] if have else ""), before

    def shiny(self) -> bool:
        return True

    def _at(self, pos) -> int:
        return next((i for i, (_b, r) in enumerate(self.cells) if r.contains(pos)), -1)

    def _secret(self, base: str) -> bool:
        return self.ctx.econ.secret(badge_item(base, "prime"))

    def mouseMoveEvent(self, e) -> None:
        i = self._at(e.position())
        if i != self._hover:
            self._hover = i
            self.setToolTip("" if i < 0 else ("???" if self._secret(self.idents[i]) else tr(BADGE_NAME[self.idents[i]])))
            self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = -1
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()
        i = self._at(e.position())
        if i >= 0 and e.button() == Qt.MouseButton.LeftButton:
            if self._secret(self.idents[i]):
                sfx.play("off")
                return self.ctx.toast(tr("A secret: find it in a case to reveal it"), "warn")
            sfx.play("pick")
            self.page.open_badge(self.idents[i])

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        wearing = {i.split(":")[1] for i in worn(self.ctx) if i.count(":") == 2}
        now = time.monotonic()
        for rarity, y, bases in self.heads:
            col = QColor(RARITY_COLOURS[rarity])
            got = sum(1 for b in bases if self.state(b)[1])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(col, 0.10))
            p.drawRoundedRect(QRectF(0, y + S(2), self.width(), self.head - S(6)), S(7), S(7))
            p.setBrush(col)
            p.drawRoundedRect(QRectF(0, y + S(2), S(3), self.head - S(6)), S(1.5), S(1.5))
            p.setPen(col)
            p.setFont(font(11, QFont.Weight.ExtraBold, 0.6))
            p.drawText(QRectF(S(11), y, self.width(), self.head - S(2)), int(Qt.AlignmentFlag.AlignVCenter),
                       tr(RARITY_NAMES[rarity]).upper())
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(10.5, QFont.Weight.DemiBold))
            p.drawText(QRectF(0, y, self.width() - S(9), self.head - S(2)),
                       int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), f"{got} / {len(bases)}")
        for i, (base, cell) in enumerate(self.cells):
            have, best, before = self.state(base)
            d = S(40)
            c = QPointF(cell.center().x(), cell.top() + S(3) + d / 2)
            hov = i == self._hover
            mythic = base in EXOTIC_IDS
            ring = QColor(RARITY_COLOURS["exotic" if mythic else self.ctx.econ.rarity(badge_item(base, "grey"))])
            g = S(20) if mythic else S(21)
            box = QRectF(c.x() - g / 2, c.y() - g / 2, g, g)
            if self._secret(base):
                paint_secret(p, QRectF(c.x() - d * 0.36, c.y() - d * 0.36, d * 0.72, d * 0.72), now, True)
            else:
                p.setPen(QPen(ui.accent if base in wearing else alpha(ring, (0.55 if best else 0.12) + (0.2 if hov else 0)),
                              1.3))
                p.setBrush(alpha(ring, 0.08) if best else QColor("#0A0D0E"))
                p.drawEllipse(c, d / 2, d / 2)
                if best:
                    paint_item(p, badge_item(base, best), box, now)
                else:
                    paint_item(p, badge_item(base, before or ("prime" if mythic else "grey")), box, 0,
                               effects=False, dim=(0.42 if before else 0.26) + (0.15 if hov else 0.0))
            p.setFont(font(9, QFont.Weight.DemiBold))
            p.setPen(ring if best else QColor(TEXT_FAINT))
            p.drawText(QRectF(cell.left(), cell.top() + S(3) + d + S(1), cell.width(), S(14)),
                       int(Qt.AlignmentFlag.AlignCenter),
                       "?" if self._secret(base) else f"{len(have)}/{len(variants_for(base))}")


class BigBadge(_Shiny):
    """One badge, large, in the colour picked below it, with its name, rarity and whether you have it."""

    def __init__(self, page) -> None:
        super().__init__()
        self.page, self.ctx = page, page.ctx
        self.item = "badge:star:grey"
        self.setFixedHeight(S(140))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._born = time.monotonic()

    def shiny(self) -> bool:
        return True

    def show_item(self, item: str) -> None:
        self.item = item
        self._born = time.monotonic()
        self.restart()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        ec = self.ctx.econ
        rarity = ec.rarity(self.item)
        owned, before = ec.owns(self.item), ec.had(self.item)
        col = QColor(RARITY_COLOURS[rarity])
        c = QPointF(self.width() / 2, S(54))
        breath = 0.5 + 0.5 * math.sin(now * 2.0)
        glow = QRadialGradient(c, S(70))
        glow.setColorAt(0.0, alpha(col, 0.20 + 0.08 * breath if owned else 0.07))
        glow.setColorAt(1.0, alpha(col, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, S(70), S(70))
        if rarity in ("epic", "exotic") and owned:
            p.save()
            p.translate(c)
            p.rotate(now * 12)
            for _k in range(10):
                p.rotate(36)
                ray = QPainterPath()
                ray.moveTo(0, 0)
                ray.lineTo(S(64), -S(7))
                ray.lineTo(S(64), S(7))
                ray.closeSubpath()
                p.setBrush(alpha(col, 0.07 if rarity == "epic" else 0.12))
                p.drawPath(ray)
            p.restore()
        pop = min(1.0, (now - self._born) / 0.25)
        size = S(66) * (0.85 + 0.15 * (1 - (1 - pop) ** 3))
        show_item(p, self.item, QRectF(c.x() - size / 2, c.y() - size / 2, size, size), now, effects=True,
                  dim=1.0 if (owned or ec.can_wear(self.item)) else 0.8)
        count = len(ec.copies(self.item))
        p.setPen(QColor(TEXT))
        p.setFont(font(13, QFont.Weight.Bold))
        name = tr(VARIANT_NAME.get(self.item.split(":")[2], "")) + (f"  ×{count}" if count > 1 else "")
        p.drawText(QRectF(0, S(98), self.width(), S(20)), int(Qt.AlignmentFlag.AlignCenter), name)
        owned = owned or ec.can_wear(self.item)
        tag = tr(RARITY_NAMES[rarity]) + ("" if owned else "  ·  " + (tr("No longer owned") if before else tr("Not owned")))
        p.setPen(col)
        p.setFont(font(10.5, QFont.Weight.Bold))
        p.drawText(QRectF(0, S(118), self.width(), S(16)), int(Qt.AlignmentFlag.AlignCenter), tag)


class VariantPicker(_Shiny):
    """Every colour of one badge: prestige finishes on top, then the colours, then grey."""
    picked = pyqtSignal(str)

    def __init__(self, page, base: str) -> None:
        super().__init__()
        self.page, self.ctx, self.base = page, page.ctx, base
        self.var = ""
        self.label_w = S(74)
        self.sq, self.gap = S(28), S(5)
        if base in EXOTIC_IDS:
            self.rows = [("Gold", GOLD_IDS), ("Prismatic", ["prime"]), ("Titanium", TITANIUM_IDS)]
        else:
            self.rows = [("Gold", GOLD_IDS), ("Titanium", TITANIUM_IDS), ("Shiny", SHINY_IDS), ("Painted", PAINTED_IDS),
                         ("Basic", ["grey"])]
        self.row_h = S(36)
        self.setFixedSize(page.W, int(self.row_h * len(self.rows)))
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = ""
        self.ctx.econ.changed.connect(self.restart)

    def shiny(self) -> bool:
        return any(self.ctx.econ.owns(badge_item(self.base, v)) and item_animated(badge_item(self.base, v))
                   for _t, vs in self.rows for v in vs)

    def _rect(self, row: int, k: int) -> QRectF:
        return QRectF(self.label_w + k * (self.sq + self.gap), row * self.row_h + (self.row_h - self.sq) / 2,
                      self.sq, self.sq)

    def _at(self, pos) -> str:
        for row, (_t, vs) in enumerate(self.rows):
            for k, v in enumerate(vs):
                if self._rect(row, k).adjusted(-2, -2, 2, 2).contains(pos):
                    return v
        return ""

    def mouseMoveEvent(self, e) -> None:
        v = self._at(e.position())
        if v != self._hover:
            self._hover = v
            self.setToolTip(tr(VARIANT_NAME[v]) if v else "")
            self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = ""
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()
        v = self._at(e.position())
        if v and e.button() == Qt.MouseButton.LeftButton:
            sfx.play("pick")
            self.var = v
            self.picked.emit(v)
            self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ec = self.ctx.econ
        wearing = set(worn(self.ctx))
        now = time.monotonic()
        for row, (title, vs) in enumerate(self.rows):
            p.setPen(QColor(CLASS_COLOURS[{"Gold": 4, "Prismatic": 5, "Titanium": 3, "Shiny": 2, "Painted": 1}.get(title, 0)]))
            p.setFont(font(10, QFont.Weight.Bold))
            p.drawText(QRectF(0, row * self.row_h, self.label_w - S(6), self.row_h), int(Qt.AlignmentFlag.AlignVCenter),
                       tr(title) if title else "")
            for k, v in enumerate(vs):
                item = badge_item(self.base, v)
                r = self._rect(row, k)
                col = QColor(CLASS_COLOURS[int(ec.info(item).get("cls") or 0)])
                have, sel, hov = ec.can_wear(item), v == self.var, v == self._hover
                p.setPen(QPen(QColor("#FFFFFF") if sel else alpha(col, 0.55 if have else (0.3 if hov else 0.12)),
                              S(1.6) if sel else 1.1))
                p.setBrush(alpha(col, 0.10) if have else QColor("#0C1013"))
                p.drawRoundedRect(r, S(7), S(7))
                paint_item(p, item, r.adjusted(S(6.5), S(6.5), -S(6.5), -S(6.5)), now, effects=have,
                           dim=1.0 if have else (0.62 if ec.had(item) else 0.45))
                if item in wearing:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(ui.accent)
                    p.drawEllipse(QPointF(r.right() - S(3), r.top() + S(3)), S(3), S(3))


# --------------------------------------------------------------------------- #
# Cases
# --------------------------------------------------------------------------- #
def paint_case(p: QPainter, rect: QRectF, case_id: str, shake: float = 0.0) -> None:
    """A small closed case in its colour, with three of its badges on the front."""
    p.save()
    p.translate(rect.center().x() + shake, rect.center().y())
    w, h = rect.width(), rect.height() * 0.72
    body = QRectF(-w / 2, -h / 2 + rect.height() * 0.08, w, h)
    col = QColor(CASE_COLOURS.get(case_id, "#3DDC84"))
    g = QLinearGradient(body.topLeft(), body.bottomLeft())
    g.setColorAt(0.0, mix(col, QColor("#FFFFFF"), 0.18))
    g.setColorAt(1.0, mix(col, QColor("#000000"), 0.45))
    p.setPen(QPen(alpha("#000000", 0.5), 1))
    p.setBrush(g)
    p.drawRoundedRect(body, w * 0.12, w * 0.12)
    p.setBrush(alpha("#000000", 0.28))
    p.drawRect(QRectF(body.left(), body.top() + h * 0.32, w, h * 0.12))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(mix(col, QColor("#000000"), 0.3), max(1.5, w * 0.06)))
    p.drawRoundedRect(QRectF(-w * 0.18, body.top() - h * 0.16, w * 0.36, h * 0.2), w * 0.06, w * 0.06)
    bs = w * 0.2
    for k, base in enumerate(CASE_FRONT.get(case_id, ("heart", "star", "note"))):
        x = -bs * 1.3 + k * bs * 1.3
        spot = QRectF(x - bs / 2, body.top() + h * 0.56 - bs / 2, bs, bs)
        if base == "?":
            paint_secret(p, spot, time.monotonic(), True)
        elif base == "$":
            paint_coin(p, spot.center(), bs * 0.46)
        else:
            paint_item(p, badge_item(base, "white"), spot, 0, effects=False)
    p.restore()


class CaseCard(QWidget):
    """A case in the list (or the free daily case): picture, name, price or countdown."""

    def __init__(self, page, case: dict) -> None:
        super().__init__()
        self.page, self.ctx, self.case = page, page.ctx, case
        self.setFixedHeight(S(64))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = Tween(self, on_change=self.update)

    def enterEvent(self, _e) -> None:
        self._hover.to(1.0, 140)

    def leaveEvent(self, _e) -> None:
        self._hover.to(0.0, 220)

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            sfx.play("pick")
            self.page.open_case(self.case["id"])

    def paintEvent(self, _e) -> None:
        from .shop import clock_text
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self._hover.level
        cid = self.case["id"]
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        col = QColor(CASE_COLOURS.get(cid, "#3DDC84"))
        p.setPen(QPen(mix(alpha("#FFFFFF", 0.08), col, 0.4 + 0.5 * h), 1.2))
        bg = QLinearGradient(r.topLeft(), r.topRight())
        bg.setColorAt(0.0, alpha(col, 0.14 + 0.06 * h))
        bg.setColorAt(0.6, QColor("#0C1113"))
        p.setBrush(bg)
        p.drawRoundedRect(r, S(12), S(12))
        paint_case(p, QRectF(r.left() + S(12), r.top() + S(8), S(48), r.height() - S(16)), cid,
                   math.sin(time.monotonic() * 40) * S(1.2) * h)
        x = r.left() + S(74)
        p.setPen(QColor(TEXT))
        p.setFont(font(13.5, QFont.Weight.Bold))
        p.drawText(QRectF(x, r.top() + S(9), r.width() - S(90), S(22)), int(Qt.AlignmentFlag.AlignVCenter),
                   tr(CASE_NAMES.get(cid, "Daily Case")))
        line = QRectF(x, r.top() + S(33), r.width() - S(90), S(18))
        have = int(self.ctx.econ.stock.get(cid, 0) or 0)
        if have:
            tag = QRectF(r.right() - S(86), r.top() + S(9), S(76), S(20))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(GOLD_TEXT, 0.16))
            p.drawRoundedRect(tag, S(10), S(10))
            p.setPen(QColor(GOLD_TEXT))
            p.setFont(font(10, QFont.Weight.Bold))
            p.drawText(tag, int(Qt.AlignmentFlag.AlignCenter), tr("{n} gifted", n=have))
        if cid == "daily":
            wait = self.page.daily_wait()
            p.setPen(QColor(GOLD_TEXT) if wait == 0 else QColor(TEXT_DIM))
            p.setFont(font(11, QFont.Weight.DemiBold))
            p.drawText(line, int(Qt.AlignmentFlag.AlignVCenter),
                       tr("Free: ready") if wait == 0 else ("…" if wait is None else tr("Free again in {t}", t=clock_text(wait))))
        else:
            paint_price(p, line, self.case["price"], 11, GOLD_TEXT, centre=False)
            p.setFont(font(11, QFont.Weight.DemiBold))
            pw = p.fontMetrics().horizontalAdvance(coins_text(self.case["price"])) + S(26)
            p.setPen(QColor(TEXT_DIM))
            p.drawText(QRectF(x + pw, line.top(), S(14), S(18)), int(Qt.AlignmentFlag.AlignVCenter), "+")
            p.save()
            p.translate(x + pw + S(20), line.center().y())
            p.scale(S(12) / 20, S(12) / 20)
            draw_icon(p, "key", ui.accent)
            p.restore()


class OddsTable(QWidget):
    """The real chances of this case: what kind of drop, and for a badge, which finish."""

    def __init__(self, case: dict, width: int) -> None:
        super().__init__()
        self.case = case
        self.rows = [("tier", i, share) for i, share in enumerate(case["odds"]) if share > 0][::-1]
        variants = list(case.get("variants") or [])
        if any(t for _k, t, _s in self.rows) and variants:
            self.rows.append(("head", 0, 0))
            self.rows += [("cls", i, share) for i, share in enumerate(variants) if share > 0][::-1]
        self.row_h = S(24)
        self.setFixedSize(width, int(self.row_h * len(self.rows) + S(4)))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        case = self.case
        for k, (kind, n, share) in enumerate(self.rows):
            r = QRectF(0, k * self.row_h, self.width(), self.row_h)
            if kind == "head":
                p.setPen(QColor(TEXT_DIM))
                p.setFont(font(10.5, QFont.Weight.Bold))
                p.drawText(r, int(Qt.AlignmentFlag.AlignVCenter), tr("If it is a badge, its finish:"))
                continue
            if kind == "cls":
                col, name = QColor(CLASS_COLOURS[n]), tr(CLASS_NAMES[n])
            elif n:
                col, name = QColor(RARITY_COLOURS[TIERS[n - 1]]), tr(RARITY_NAMES[TIERS[n - 1]])
            elif case.get("mode") == "jackpot":
                col, name = QColor(GOLD_TEXT), tr("{a} to {b} coins", a=100, b=coins_text(16000))
            else:
                col, name = QColor(GOLD_TEXT), tr("{a} to {b} coins", a=coins_text(case["coin_min"]), b=coins_text(case["coin_max"]))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(col, 0.07))
            p.drawRoundedRect(r.adjusted(0, S(1.5), 0, -S(1.5)), S(6), S(6))
            if kind == "tier" and not n:
                paint_coin(p, QPointF(r.left() + S(12), r.center().y()), S(5))
            else:
                p.setBrush(col)
                p.drawEllipse(QPointF(r.left() + S(12), r.center().y()), S(4), S(4))
            p.setPen(col)
            p.setFont(font(11, QFont.Weight.Bold))
            p.drawText(r.adjusted(S(24), 0, 0, 0), int(Qt.AlignmentFlag.AlignVCenter), name)
            pct = share / 100
            text = f"{pct:.2f}%" if pct < 1 else f"{pct:.1f}%"
            p.setPen(QColor(TEXT))
            p.drawText(r.adjusted(0, 0, -S(10), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                       text.replace(".", ",") if lang() == "fr" else text)


class CaseReel(QWidget):
    """The opening: a strip of drops races past the marker and slows down until it stops on yours. The server
    already decided and saved the drop before the strip starts."""
    done = pyqtSignal()
    ITEMS, WIN, SPIN_S = 52, 46, 6.6

    def __init__(self, page, case: dict) -> None:
        super().__init__()
        self.page, self.ctx, self.case = page, page.ctx, case
        self.setFixedHeight(S(178))
        self.cw, self.gap = S(64), S(6)
        self.state = "idle"                              # idle -> spin -> landed -> result
        self.result = None
        self._pool = {}
        rnd = random.Random(sum(map(ord, case["id"])))
        self.strip = [self._filler(rnd) for _ in range(self.ITEMS)]
        self.offset = self._start()
        self._t0 = self._target = self._last_tick = self._stop_t = 0.0
        self._last_cell = 0
        self._frames = QTimer(self)
        self._frames.setTimerType(Qt.TimerType.PreciseTimer)
        self._frames.setInterval(16)
        self._frames.timeout.connect(self._step)
        self._sparks: list = []

    def _badges_of(self, tier: int) -> list:
        if tier not in self._pool:
            self._pool[tier] = [b for b in BADGE_ROWS[tier - 1][1]] or ["star"]
        return self._pool[tier]

    def _filler(self, rnd) -> tuple:
        """A drop for the strip, picked with the case's real odds (so the strip looks like the case)."""
        roll, tier = rnd.randrange(10000), 0
        for i, share in enumerate(self.case["odds"]):
            if roll < share:
                tier = i
                break
            roll -= share
        if tier == 0:
            if self.case.get("mode") == "jackpot":
                return ("coins", rnd.choice([150, 220, 300, 380, 1200, 1500, 4000, 12000]))
            return ("coins", rnd.randint(self.case["coin_min"], max(self.case["coin_min"], self.case["coin_max"])))
        base = rnd.choice(self._badges_of(tier))
        if tier == 5:
            return ("item", badge_item(base, rnd.choice(["prime"] * 9 + ["white"])))
        roll, cls = rnd.randrange(10000), 0
        for i, share in enumerate(self.case.get("variants") or [10000]):
            if roll < share:
                cls = i
                break
            roll -= share
        if rnd.random() < 0.06:                              # a few rare ones flash past: that is the thrill
            cls = rnd.choice([2, 3, 4])
        var = rnd.choice([["grey"], PAINTED_IDS, SHINY_IDS, TITANIUM_IDS, GOLD_IDS][cls])
        return ("item", badge_item(base, var))

    def _start(self) -> float:
        return 2 * (self.cw + self.gap) + self.cw / 2

    INTRO_S = 0.75

    def busy(self) -> bool:
        return self.state in ("intro", "spin", "landed") or (self.state == "result" and time.monotonic() - self._stop_t < 0.9)

    def spin(self, result: dict) -> None:
        rnd = random.Random()
        self.strip = [self._filler(rnd) for _ in range(self.ITEMS)]
        self.strip[self.WIN] = ("item", result["item"]) if result.get("item") else ("coins", int(result.get("won", 0)))
        self.result = result
        self.state = "intro"                              # 2.4: the case shakes and opens, then the strip runs
        self._intro_t = time.monotonic()
        self.offset = self._start()
        self._target = self.WIN * (self.cw + self.gap) + self.cw / 2 + rnd.uniform(-0.38, 0.38) * self.cw
        self._t0 = time.monotonic()
        self._last_cell = int(self.offset // (self.cw + self.gap))
        self._sparks = []
        self._frames.setInterval(16)
        self._frames.start()

    def skip(self) -> None:
        if self.state == "intro":
            self.state = "spin"
            self._t0 = time.monotonic()
        if self.state == "spin":
            self._t0 = time.monotonic() - self.SPIN_S
            self._step()

    def _step(self) -> None:
        now = time.monotonic()
        if self.state == "intro" and now - self._intro_t >= self.INTRO_S:
            self.state = "spin"
            self._t0 = now
            sfx.play("on")
        if self.state == "spin":
            t = min(1.0, (now - self._t0) / self.SPIN_S)
            start = self._start()
            self.offset = start + (self._target - start) * (1.0 - (1.0 - t) ** 4.2)
            cell = int((self.offset + self.gap / 2) // (self.cw + self.gap))
            if cell != self._last_cell:
                self._last_cell = cell
                if now - self._last_tick > 0.035:
                    self._last_tick = now
                    sfx.play("pick")
            if t >= 1.0:
                self.state = "landed"
                self._stop_t = now
                QTimer.singleShot(650, self._reveal)
        self.update()

    def _tier(self) -> int:
        return int((self.result or {}).get("tier", 0))

    def _reveal(self) -> None:
        if self.result is None:
            return
        self.state = "result"
        self._stop_t = time.monotonic()
        tier = self._tier()
        sfx.play("on")
        if tier >= 4:
            QTimer.singleShot(180, lambda: sfx.play("on"))
        n = [0, 0, 10, 18, 30, 60][tier] + [0, 0, 12, 30, 70][int(self.result.get("cls") or 0)]
        rnd = random.Random()
        self._sparks = [(rnd.uniform(0, math.tau), rnd.uniform(S(60), S(150)), rnd.uniform(0.6, 1.3)) for _ in range(n)]
        self.done.emit()

    def mousePressEvent(self, e) -> None:
        e.accept()
        if self.state == "result" and not self.busy():
            self.state = "idle"
            self._frames.stop()
            self.update()

    def hideEvent(self, _e) -> None:
        self.skip()

    def _card(self, p: QPainter, rect: QRectF, drop: tuple, now: float, flash: float = 0.0) -> None:
        kind, what = drop
        col = QColor(GOLD_TEXT) if kind == "coins" else rarity_colour(self.ctx, what)
        g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        g.setColorAt(0.0, QColor("#11171A"))
        g.setColorAt(1.0, mix(QColor("#11171A"), col, 0.32 if kind == "item" else 0.12))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(rect, S(8), S(8))
        p.setBrush(col if kind == "item" else alpha(col, 0.5))
        p.drawRoundedRect(QRectF(rect.left() + S(6), rect.bottom() - S(5), rect.width() - S(12), S(3)), S(1.5), S(1.5))
        if kind == "coins":
            paint_coin(p, QPointF(rect.center().x(), rect.center().y() - S(10)), S(11))
            p.setPen(QColor(GOLD_TEXT))
            p.setFont(font(11, QFont.Weight.Bold))
            p.drawText(QRectF(rect.left(), rect.center().y() + S(6), rect.width(), S(18)), int(Qt.AlignmentFlag.AlignCenter),
                       coins_text(what))
            p.setPen(Qt.PenStyle.NoPen)
        else:
            size = rect.width() * 0.5
            show_item(p, what, QRectF(rect.center().x() - size / 2, rect.center().y() - size / 2 - S(4), size, size),
                      now, effects=self.state != "spin")
        if flash > 0:
            p.setBrush(QColor(255, 255, 255, int(150 * flash)))
            p.drawRoundedRect(rect, S(8), S(8))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(r, S(12), S(12))
        p.fillPath(clip, QColor("#090C0D"))
        now = time.monotonic()
        p.save()
        p.setClipPath(clip)
        if self.state == "result":
            self._paint_result(p, r, now)
        elif self.state == "intro":
            self._paint_intro(p, r, now)
        else:
            self._paint_strip(p, r, now)
        p.restore()
        p.setPen(QPen(alpha("#FFFFFF", 0.08), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, S(12), S(12))

    def _paint_intro(self, p: QPainter, r: QRectF, now: float) -> None:
        """The case shakes, a light leaks out, the lid flies open."""
        k = min(1.0, (now - self._intro_t) / self.INTRO_S)
        c = r.center()
        col = QColor(CASE_COLOURS.get(self.case["id"], GOLD_TEXT))
        glow = QRadialGradient(c, S(120))
        glow.setColorAt(0, alpha(col, 0.15 + 0.45 * k))
        glow.setColorAt(1, alpha(col, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, S(120), S(120))
        shake = math.sin(now * 70) * S(4) * (k if k < 0.7 else 0.0)
        p.save()
        p.translate(c.x() + shake, c.y() + S(8))
        p.rotate(math.sin(now * 55) * 4 * (k if k < 0.7 else 0.0))
        body = QRectF(-S(34), -S(16), S(68), S(42))
        g = QLinearGradient(body.topLeft(), body.bottomLeft())
        g.setColorAt(0, mix(col, QColor("#FFFFFF"), 0.25))
        g.setColorAt(1, mix(col, QColor("#000000"), 0.45))
        p.setBrush(g)
        p.drawRoundedRect(body, S(6), S(6))
        lift = max(0.0, (k - 0.7) / 0.3)
        p.save()
        p.translate(-S(36), -S(16))
        p.rotate(-70 * lift)
        p.setBrush(mix(col, QColor("#FFFFFF"), 0.4))
        p.drawRoundedRect(QRectF(0, -S(12), S(72), S(14)), S(5), S(5))
        p.restore()
        p.setBrush(QColor(20, 22, 24, 200))
        p.drawRoundedRect(QRectF(-S(5), -S(8), S(10), S(14)), S(3), S(3))
        p.restore()
        if lift > 0:
            p.setBrush(QColor(255, 255, 255, int(200 * lift)))
            p.drawRect(r)

    def _paint_strip(self, p: QPainter, r: QRectF, now: float) -> None:
        cx, ch = r.center().x(), S(88)
        top = r.center().y() - ch / 2
        step = self.cw + self.gap
        first = max(0, int((self.offset - cx) // step) - 1)
        speed = (1.0 - min(1.0, (now - self._t0) / self.SPIN_S)) ** 3.2 if self.state == "spin" else 0.0
        if self.state == "landed":                        # a glow in the drop's colour, just before the reveal
            tier = self._tier()
            col = QColor(RARITY_COLOURS[TIERS[tier - 1]]) if tier else QColor(GOLD_TEXT)
            a = min(1.0, (now - self._stop_t) / 0.5)
            halo = QRadialGradient(QPointF(cx, r.center().y()), S(110))
            halo.setColorAt(0, alpha(col, 0.55 * a))
            halo.setColorAt(1, alpha(col, 0.0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(halo)
            p.drawEllipse(QPointF(cx, r.center().y()), S(110), S(110))
        for i in range(first, min(self.ITEMS, first + int(r.width() // step) + 4)):
            flash = 0.0
            if self.state == "landed" and i == self.WIN:
                flash = max(0.0, 1.0 - (now - self._stop_t) / 0.6) * (0.5 + 0.5 * math.sin((now - self._stop_t) * 30))
            rect = QRectF(cx - self.offset + i * step, top, self.cw, ch)
            if speed > 0.25:                              # motion blur while it races
                p.setOpacity(0.18 * speed)
                self._card(p, rect.translated(S(10) * speed, 0), self.strip[i], now)
                p.setOpacity(1.0)
            self._card(p, rect, self.strip[i], now, flash)
        fade = QLinearGradient(r.topLeft(), r.topRight())
        for at, a in ((0.0, 250), (0.22, 0), (0.78, 0), (1.0, 250)):
            fade.setColorAt(at, QColor(9, 12, 13, a))
        p.fillRect(r, fade)
        mark = mix(QColor(GOLD_TEXT), QColor("#FFFFFF"), speed)
        p.setPen(QPen(alpha(mark, 0.35), S(6)))
        p.drawLine(QPointF(cx, top - S(10)), QPointF(cx, top + ch + S(10)))
        p.setPen(QPen(mark, S(2)))
        p.drawLine(QPointF(cx, top - S(10)), QPointF(cx, top + ch + S(10)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mark)
        for y, d in ((top - S(14), 1), (top + ch + S(14), -1)):
            tri = QPainterPath()
            tri.moveTo(cx - S(7), y)
            tri.lineTo(cx + S(7), y)
            tri.lineTo(cx, y + d * S(9))
            tri.closeSubpath()
            p.drawPath(tri)

    def _paint_result(self, p: QPainter, r: QRectF, now: float) -> None:
        res, tier = self.result, self._tier()
        col = QColor(RARITY_COLOURS[TIERS[tier - 1]]) if tier else QColor(GOLD_TEXT)
        age = now - self._stop_t
        c = QPointF(r.center().x(), r.top() + S(66))
        burst = QRadialGradient(c, S(150))
        burst.setColorAt(0.0, alpha(col, 0.42 if tier >= 2 else 0.18))
        burst.setColorAt(1.0, alpha(col, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(burst)
        p.drawEllipse(c, S(150), S(150))
        if tier >= 2:
            rays = [0, 0, 8, 10, 14, 18][tier]
            p.save()
            p.translate(c)
            p.rotate(now * (12 + 4 * tier))
            for _k in range(rays):
                p.rotate(360 / rays)
                ray = QPainterPath()
                ray.moveTo(0, 0)
                ray.lineTo(S(170), -S(10))
                ray.lineTo(S(170), S(10))
                ray.closeSubpath()
                p.setBrush(alpha(col, 0.08 + 0.03 * (tier - 2)))
                p.drawPath(ray)
            p.restore()
        if age < 0.35 and tier >= 2:
            p.setBrush(QColor(255, 255, 255, int((120 + 30 * tier) * (1 - age / 0.35))))
            p.drawRect(r)
        if age < 0.9:                                     # a shock ring rolls out
            ring = S(30) + age / 0.9 * S(220)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(alpha(col, 0.7 * (1 - age / 0.9)), S(3)))
            p.drawEllipse(c, ring, ring)
            p.setPen(Qt.PenStyle.NoPen)
        big = tier >= 4 or int(res.get("cls") or 0) >= 2
        if big:                                           # confetti for the big ones
            rnd = random.Random(int(self._stop_t * 1000))
            for k in range(40):
                x0 = rnd.uniform(r.left(), r.right())
                fall = (age * rnd.uniform(S(60), S(130)) + rnd.uniform(-S(60), 0)) % (r.height() + S(20))
                sway = math.sin(age * rnd.uniform(2, 5) + k) * S(8)
                cc = QColor.fromHsvF(rnd.random(), 0.6, 1.0) if tier == 5 else mix(col, QColor("#FFFFFF"), rnd.uniform(0, 0.6))
                p.setBrush(cc)
                p.save()
                p.translate(x0 + sway, r.top() + fall - S(10))
                p.rotate(age * 200 + k * 37)
                p.drawRect(QRectF(-S(2.5), -S(1.2), S(5), S(2.4)))
                p.restore()
        for ang, dist, spd in self._sparks:
            k = min(1.0, age * spd / 1.4)
            if k < 1.0:
                d = dist * (1 - (1 - k) ** 3)
                sc = mix(col, QColor("#FFFFFF"), 0.5)
                sc.setAlphaF(1.0 - k)
                p.setBrush(sc)
                p.drawEllipse(QPointF(c.x() + d * math.cos(ang), c.y() + d * math.sin(ang)), S(2.2), S(2.2))
        pop = min(1.0, age / 0.45)
        size = S(64) * (0.4 + 0.6 * (1 - (1 - pop) ** 3)) * (1 + 0.18 * math.sin(pop * math.pi) * (1 - pop))
        if res.get("item"):
            paint_item(p, res["item"], QRectF(c.x() - size / 2, c.y() - size / 2, size, size), now)
            title, tag = badge_label(res["item"]), tr(RARITY_NAMES[TIERS[tier - 1]]).upper()
            cls = int(res.get("cls") or 0)
            if cls:
                tag += "  ·  " + tr(CLASS_NAMES[cls]).upper()
        else:
            paint_coin(p, c, size * 0.42)
            title, tag = "+" + coins_text(int(res.get("won", 0))), tr("Coins").upper()
        if int(res.get("won_keys", 0) or 0):
            title, tag = "+1 " + tr("key"), tr("Key").upper()
        p.setPen(QColor(TEXT))
        p.setFont(font(14, QFont.Weight.Bold))
        p.drawText(QRectF(r.left(), r.top() + S(112), r.width(), S(22)), int(Qt.AlignmentFlag.AlignCenter), title)
        p.setPen(col)
        p.setFont(font(10.5, QFont.Weight.ExtraBold))
        p.drawText(QRectF(r.left(), r.top() + S(134), r.width(), S(16)), int(Qt.AlignmentFlag.AlignCenter),
                   tag)
