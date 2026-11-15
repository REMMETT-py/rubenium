"""Shop > Badges and Shop > Cases: your badge collection, the showcase on the music tab, and the cases.

Basic colours of a badge are bought directly. Rare, very rare and super rare colours only come out of cases.
A case costs coins and one key; keys are earned by playing in the casino."""
import math
import random
import time

from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from .badges import animated, paint_badge
from .core import S, sfx, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, lang, mix, tr, ui
from .shop import GOLD_TEXT, paint_price
from .wallet import (BADGE_NAME, BADGES, CASE_OF, CASES, RARITIES, RARITY_COLOUR, RARITY_NAME, VARIANT, VARIANTS,
                     coins_text, variants_of)
from .widgets import Tween, draw_icon

SHOWCASE = 3


def worn(ctx) -> list:
    items = ctx.cfg["badges"] if isinstance(ctx.cfg["badges"], list) else []
    return [i for i in items if "/" in str(i)][:SHOWCASE]


def badge_label(ident: str, var: str) -> str:
    return f"{tr(BADGE_NAME[ident])} · {tr(VARIANT[var][1])}"


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
    """The three badges shown on the music tab. Click one to take it off."""

    def __init__(self, page) -> None:
        super().__init__()
        self.page, self.ctx = page, page.ctx
        self.setFixedHeight(S(60))
        self.setMouseTracking(True)
        self._hover = -1
        self.ctx.wallet.changed.connect(self.update)

    def shiny(self) -> bool:
        return any(animated(i.split("/")[1]) for i in worn(self.ctx))

    def _slot(self, k: int) -> QRectF:
        d = S(50)
        return QRectF(k * (d + S(8)) + 0.5, (self.height() - d) / 2, d, d)

    def mouseMoveEvent(self, e) -> None:
        k = next((k for k in range(SHOWCASE) if self._slot(k).contains(e.position())), -1)
        if k != self._hover:
            self._hover = k
            filled = 0 <= k < len(worn(self.ctx))
            self.setCursor(Qt.CursorShape.PointingHandCursor if filled else Qt.CursorShape.ArrowCursor)
            self.setToolTip(tr("Take off") if filled else "")
            self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = -1
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()
        items = worn(self.ctx)
        k = next((k for k in range(SHOWCASE) if self._slot(k).contains(e.position())), -1)
        if 0 <= k < len(items) and e.button() == Qt.MouseButton.LeftButton:
            sfx.play("pick")
            items.pop(k)
            self.page.set_worn(items)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        items = worn(self.ctx)
        now = time.monotonic()
        for k in range(SHOWCASE):
            r = self._slot(k)
            if k < len(items):
                ident, var = items[k].split("/")
                col = QColor(RARITY_COLOUR[VARIANT[var][2]])
                p.setPen(QPen(alpha(col, 0.75 if k == self._hover else 0.45), 1.3))
                p.setBrush(alpha(col, 0.10))
                p.drawRoundedRect(r, S(12), S(12))
                paint_badge(p, ident, r.adjusted(S(13), S(13), -S(13), -S(13)), var, now)
            else:
                pen = QPen(alpha("#FFFFFF", 0.14), 1.2, Qt.PenStyle.DashLine)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r, S(12), S(12))
                p.setPen(QPen(alpha("#FFFFFF", 0.22), S(1.6)))
                c = r.center()
                p.drawLine(QPointF(c.x() - S(6), c.y()), QPointF(c.x() + S(6), c.y()))
                p.drawLine(QPointF(c.x(), c.y() - S(6)), QPointF(c.x(), c.y() + S(6)))
        right = QRectF(self._slot(SHOWCASE - 1).right() + S(14), 0, 0, self.height())
        right.setRight(self.width())
        total = len(BADGES) * len(VARIANTS)
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10, QFont.Weight.DemiBold))
        p.drawText(QRectF(right.left(), right.top() + S(10), right.width(), S(16)),
                   int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), tr("Collected"))
        p.setPen(QColor(TEXT))
        p.setFont(font(15, QFont.Weight.Bold))
        p.drawText(QRectF(right.left(), right.top() + S(26), right.width(), S(24)),
                   int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                   f"{coins_text(self.ctx.wallet.badge_total())} / {coins_text(total)}")


class BadgeGrid(_Shiny):
    """All 50 badges. Each shows the rarest colour you have (or a dark outline) and how many colours you own."""
    COLS = 6

    def __init__(self, page, idents=None) -> None:
        super().__init__()
        self.page, self.ctx = page, page.ctx
        self.idents = idents or [b[0] for b in BADGES]
        self.cw, self.ch = page.W / self.COLS, S(62)
        rows = (len(self.idents) + self.COLS - 1) // self.COLS
        self.setFixedSize(page.W, int(rows * self.ch))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self._hover = -1

    def shiny(self) -> bool:
        w = self.ctx.wallet
        return any(animated(v) for b in self.idents for v in w.badge_variants(b)[:1])

    def _cell(self, i: int) -> QRectF:
        return QRectF((i % self.COLS) * self.cw, (i // self.COLS) * self.ch, self.cw, self.ch)

    def _at(self, pos) -> int:
        i = int(pos.y() // self.ch) * self.COLS + int(pos.x() // self.cw)
        return i if 0 <= i < len(self.idents) and pos.x() < self.COLS * self.cw else -1

    def mouseMoveEvent(self, e) -> None:
        i = self._at(e.position())
        if i != self._hover:
            self._hover = i
            self.setToolTip(tr(BADGE_NAME[self.idents[i]]) if i >= 0 else "")
            self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = -1
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()
        i = self._at(e.position())
        if i >= 0 and e.button() == Qt.MouseButton.LeftButton:
            sfx.play("pick")
            self.page.open_badge(self.idents[i])

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.ctx.wallet
        wearing = {i.split("/")[0] for i in worn(self.ctx)}
        now = time.monotonic()
        for i, ident in enumerate(self.idents):
            cell = self._cell(i)
            have = w.badge_variants(ident)
            best = have[0] if have else ""
            d = S(40)
            c = QPointF(cell.center().x(), cell.top() + S(4) + d / 2)
            hov = i == self._hover
            ring = QColor(RARITY_COLOUR[VARIANT[best][2]]) if best else QColor("#FFFFFF")
            p.setPen(QPen(ui.accent if ident in wearing else alpha(ring, (0.55 if best else 0.10) + (0.2 if hov else 0)),
                          1.3))
            p.setBrush(alpha(ring, 0.08) if best else QColor("#0A0D0E"))
            p.drawEllipse(c, d / 2, d / 2)
            g = S(21)
            box = QRectF(c.x() - g / 2, c.y() - g / 2, g, g)
            if best:
                paint_badge(p, ident, box, best, now, effects=True)
            else:
                paint_badge(p, ident, box, "grey", 0, effects=False, dim=0.28 + (0.2 if hov else 0.0))
            p.setFont(font(9, QFont.Weight.DemiBold))
            p.setPen(ring if best else QColor(TEXT_FAINT))
            p.drawText(QRectF(cell.left(), cell.top() + S(4) + d + S(1), cell.width(), S(14)),
                       int(Qt.AlignmentFlag.AlignCenter), f"{len(have)}/{len(VARIANTS)}")


class BigBadge(_Shiny):
    """One badge, large, in the colour picked below it, with its name and rarity."""

    def __init__(self, page) -> None:
        super().__init__()
        self.page = page
        self.ident, self.var = "star", "grey"
        self.setFixedHeight(S(136))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._born = time.monotonic()

    def shiny(self) -> bool:
        return True                                    # the glow behind it breathes

    def show_variant(self, ident: str, var: str) -> None:
        self.ident, self.var = ident, var
        self._born = time.monotonic()
        self.restart()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        rarity = VARIANT[self.var][2]
        owned = self.page.ctx.wallet.has_badge(self.ident, self.var)
        col = QColor(RARITY_COLOUR[rarity])
        c = QPointF(self.width() / 2, S(54))
        breath = 0.5 + 0.5 * math.sin(now * 2.0)
        glow = QRadialGradient(c, S(70))
        glow.setColorAt(0.0, alpha(col, 0.20 + 0.08 * breath if owned else 0.07))
        glow.setColorAt(1.0, alpha(col, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, S(70), S(70))
        if rarity in ("very", "super") and owned:          # slow light rays
            p.save()
            p.translate(c)
            p.rotate(now * 12)
            for k in range(10):
                p.rotate(36)
                path = QPainterPath()
                path.moveTo(0, 0)
                path.lineTo(S(64), -S(7))
                path.lineTo(S(64), S(7))
                path.closeSubpath()
                p.setBrush(alpha(col, 0.07 if rarity == "very" else 0.11))
                p.drawPath(path)
            p.restore()
        pop = min(1.0, (now - self._born) / 0.25)
        size = S(74) * (0.85 + 0.15 * (1 - (1 - pop) ** 3))
        paint_badge(p, self.ident, QRectF(c.x() - size / 2, c.y() - size / 2, size, size), self.var, now,
                    dim=1.0 if owned else 0.35)
        if not owned:
            p.save()
            p.translate(c.x() + S(30), c.y() + S(28))
            p.setBrush(QColor(14, 17, 18))
            p.setPen(QPen(alpha("#FFFFFF", 0.14), 1))
            p.drawEllipse(QPointF(0, 0), S(11), S(11))
            p.scale(S(12) / 20, S(12) / 20)
            draw_icon(p, "lock", QColor(TEXT_DIM))
            p.restore()
        p.setPen(QColor(TEXT))
        p.setFont(font(13, QFont.Weight.Bold))
        p.drawText(QRectF(0, S(98), self.width(), S(20)), int(Qt.AlignmentFlag.AlignCenter), tr(VARIANT[self.var][1]))
        p.setPen(col)
        p.setFont(font(10.5, QFont.Weight.Bold))
        p.drawText(QRectF(0, S(117), self.width(), S(16)), int(Qt.AlignmentFlag.AlignCenter), tr(RARITY_NAME[rarity]))


class VariantPicker(_Shiny):
    """The 17 colours of one badge, in four rows from rarest to basic."""
    picked = pyqtSignal(str)

    def __init__(self, page, ident: str) -> None:
        super().__init__()
        self.page, self.ctx, self.ident = page, page.ctx, ident
        self.var = ""
        self.label_w = S(80)
        self.sq, self.gap = S(28), S(5)
        self.rows = [variants_of(k) for k, _n, _c in RARITIES][::-1]          # super, very, rare, basic
        self.row_h = S(36)
        self.setFixedSize(page.W, int(self.row_h * len(self.rows)))
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = ""

    def shiny(self) -> bool:
        return any(animated(v) for v in self.ctx.wallet.badge_variants(self.ident))

    def _rect(self, row: int, k: int) -> QRectF:
        return QRectF(self.label_w + k * (self.sq + self.gap), row * self.row_h + (self.row_h - self.sq) / 2,
                      self.sq, self.sq)

    def _at(self, pos) -> str:
        for row, vs in enumerate(self.rows):
            for k, v in enumerate(vs):
                if self._rect(row, k).adjusted(-2, -2, 2, 2).contains(pos):
                    return v[0]
        return ""

    def mouseMoveEvent(self, e) -> None:
        v = self._at(e.position())
        if v != self._hover:
            self._hover = v
            self.setToolTip(tr(VARIANT[v][1]) if v else "")
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
        w = self.ctx.wallet
        wearing = set(worn(self.ctx))
        now = time.monotonic()
        for row, vs in enumerate(self.rows):
            rarity = vs[0][2]
            col = QColor(RARITY_COLOUR[rarity])
            p.setPen(col)
            p.setFont(font(10, QFont.Weight.Bold))
            p.drawText(QRectF(0, row * self.row_h, self.label_w - S(6), self.row_h), int(Qt.AlignmentFlag.AlignVCenter),
                       tr(RARITY_NAME[rarity]))
            for k, (vid, _name, _r, main, _light) in enumerate(vs):
                r = self._rect(row, k)
                have = w.has_badge(self.ident, vid)
                sel = vid == self.var
                hov = vid == self._hover
                p.setPen(QPen(QColor("#FFFFFF") if sel else alpha(col, 0.5 if have else (0.25 if hov else 0.10)),
                              S(1.6) if sel else 1.1))
                p.setBrush(alpha(col, 0.10) if have else QColor("#0C1013"))
                p.drawRoundedRect(r, S(7), S(7))
                inner = r.adjusted(S(6), S(6), -S(6), -S(6))
                if have:
                    paint_badge(p, self.ident, inner, vid, now, effects=rarity != "basic")
                else:
                    p.setPen(QPen(alpha("#FFFFFF", 0.25), 1) if vid == "black" else Qt.PenStyle.NoPen)
                    p.setBrush(alpha(QColor(main), 0.9 if vid == "black" else 0.45))
                    p.drawEllipse(r.center(), S(4.5), S(4.5))
                if f"{self.ident}/{vid}" in wearing:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(ui.accent)
                    p.drawEllipse(QPointF(r.right() - S(3), r.top() + S(3)), S(3), S(3))


# --------------------------------------------------------------------------- #
# Cases
# --------------------------------------------------------------------------- #
def case_by_id(ident: str) -> dict:
    return next((c for c in CASES if c["id"] == ident), CASES[0])


def paint_case(p: QPainter, rect: QRectF, case: dict, shake: float = 0.0) -> None:
    """A small closed case in the case's colour, with three of its badges on the front."""
    p.save()
    p.translate(rect.center().x() + shake, rect.center().y())
    w, h = rect.width(), rect.height() * 0.72
    body = QRectF(-w / 2, -h / 2 + rect.height() * 0.08, w, h)
    col = QColor(case["colour"])
    g = QLinearGradient(body.topLeft(), body.bottomLeft())
    g.setColorAt(0.0, mix(col, QColor("#FFFFFF"), 0.18))
    g.setColorAt(1.0, mix(col, QColor("#000000"), 0.45))
    p.setPen(QPen(alpha("#000000", 0.5), 1))
    p.setBrush(g)
    p.drawRoundedRect(body, w * 0.12, w * 0.12)
    p.setBrush(alpha("#000000", 0.28))
    p.drawRect(QRectF(body.left(), body.top() + h * 0.32, w, h * 0.12))
    handle = QRectF(-w * 0.18, body.top() - h * 0.16, w * 0.36, h * 0.2)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(mix(col, QColor("#000000"), 0.3), max(1.5, w * 0.06)))
    p.drawRoundedRect(handle, w * 0.06, w * 0.06)
    bs = w * 0.22
    for k, ident in enumerate(case["badges"][:3]):
        x = -bs * 1.25 + k * bs * 1.25
        paint_badge(p, ident, QRectF(x - bs / 2, body.top() + h * 0.56 - bs / 2, bs, bs), "titanium", 0, effects=False)
    p.restore()


class CaseCard(QWidget):
    """A case in the list: picture, name, price, and how much of it you have collected."""

    def __init__(self, page, case: dict) -> None:
        super().__init__()
        self.page, self.ctx, self.case = page, page.ctx, case
        self.setFixedHeight(S(80))
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
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self._hover.level
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        col = QColor(self.case["colour"])
        p.setPen(QPen(mix(alpha("#FFFFFF", 0.08), col, 0.4 + 0.5 * h), 1.2))
        bg = QLinearGradient(r.topLeft(), r.topRight())
        bg.setColorAt(0.0, alpha(col, 0.14 + 0.06 * h))
        bg.setColorAt(0.6, QColor("#0C1113"))
        p.setBrush(bg)
        p.drawRoundedRect(r, S(12), S(12))
        paint_case(p, QRectF(r.left() + S(12), r.top() + S(10), S(58), r.height() - S(20)), self.case,
                   math.sin(time.monotonic() * 40) * S(1.2) * h)
        x = r.left() + S(84)
        p.setPen(QColor(TEXT))
        p.setFont(font(13.5, QFont.Weight.Bold))
        p.drawText(QRectF(x, r.top() + S(12), r.width() - S(90), S(22)), int(Qt.AlignmentFlag.AlignVCenter),
                   tr(self.case["name"]))
        paint_price(p, QRectF(x, r.top() + S(36), S(80), S(18)), self.case["price"], 11, GOLD_TEXT, centre=False)
        p.setFont(font(11, QFont.Weight.DemiBold))
        pw = p.fontMetrics().horizontalAdvance(coins_text(self.case["price"])) + S(26)
        p.setPen(QColor(TEXT_DIM))
        p.drawText(QRectF(x + pw, r.top() + S(36), S(14), S(18)), int(Qt.AlignmentFlag.AlignVCenter), "+")
        p.save()
        p.translate(x + pw + S(20), r.top() + S(45))
        p.scale(S(12) / 20, S(12) / 20)
        draw_icon(p, "key", ui.accent)
        p.restore()
        w = self.ctx.wallet
        total = len(self.case["badges"]) * len(VARIANTS)
        have = sum(len(w.badge_variants(b)) for b in self.case["badges"])
        bar = QRectF(x, r.bottom() - S(16), r.width() - S(98), S(4))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.08))
        p.drawRoundedRect(bar, S(2), S(2))
        p.setBrush(col)
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), max(S(4), bar.width() * have / total), bar.height()), S(2), S(2))
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(9.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(bar.left(), bar.top() - S(17), bar.width(), S(14)),
                   int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), f"{have} / {total}")


class OddsTable(QWidget):
    """The real chance of each rarity in this case."""

    def __init__(self, case: dict, width: int) -> None:
        super().__init__()
        self.case = case
        self.row_h = S(24)
        self.setFixedSize(width, int(self.row_h * 4))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        order = list(zip(("basic", "rare", "very", "super"), self.case["odds"]))[::-1]
        for k, (rarity, share) in enumerate(order):
            r = QRectF(0, k * self.row_h, self.width(), self.row_h)
            col = QColor(RARITY_COLOUR[rarity])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(col, 0.07))
            p.drawRoundedRect(r.adjusted(0, S(1.5), 0, -S(1.5)), S(6), S(6))
            p.setBrush(col)
            p.drawEllipse(QPointF(r.left() + S(12), r.center().y()), S(4), S(4))
            p.setPen(col)
            p.setFont(font(11, QFont.Weight.Bold))
            p.drawText(r.adjusted(S(24), 0, 0, 0), int(Qt.AlignmentFlag.AlignVCenter), tr(RARITY_NAME[rarity]))
            names = ", ".join(tr(v[1]) for v in variants_of(rarity)) if rarity != "basic" else tr("8 plain colours")
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(9.5, QFont.Weight.DemiBold))
            fm = p.fontMetrics()
            name_w = self.width() * 0.48
            p.drawText(QRectF(r.left() + self.width() * 0.32, r.top(), name_w, r.height()), int(Qt.AlignmentFlag.AlignVCenter),
                       fm.elidedText(names, Qt.TextElideMode.ElideRight, int(name_w)))
            pct = share / 100
            text = f"{pct:.2f}%" if pct < 1 else f"{pct:.1f}%"
            p.setPen(QColor(TEXT))
            p.setFont(font(11, QFont.Weight.Bold))
            p.drawText(r.adjusted(0, 0, -S(10), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                       text.replace(".", ",") if lang() == "fr" else text)


class CaseReel(QWidget):
    """The opening: a strip of badges races past the marker and slows down until it stops on yours."""
    done = pyqtSignal()
    ITEMS = 52
    WIN = 46
    SPIN_S = 6.6

    def __init__(self, page, case: dict) -> None:
        super().__init__()
        self.page, self.ctx, self.case = page, page.ctx, case
        self.setFixedHeight(S(178))
        self.cw, self.gap = S(64), S(6)
        self.state = "idle"                              # idle -> spin -> result
        self.result = None
        rnd = random.Random(hash(case["id"]) & 0xFFFF)
        self.strip = [self._filler(rnd) for _ in range(self.ITEMS)]
        self.offset = self._start()
        self._t0 = 0.0
        self._target = 0.0
        self._last_cell = 0
        self._last_tick = 0.0
        self._stop_t = 0.0
        self._frames = QTimer(self)
        self._frames.setTimerType(Qt.TimerType.PreciseTimer)
        self._frames.setInterval(16)
        self._frames.timeout.connect(self._step)
        self._sparks: list = []

    def _filler(self, rnd) -> tuple:
        """A random badge for the strip, drawn with the case's real odds (so the strip looks like the case)."""
        roll = rnd.randrange(10000)
        rarity = "super"
        for kind, share in zip(("basic", "rare", "very", "super"), self.case["odds"]):
            if roll < share:
                rarity = kind
                break
            roll -= share
        return rnd.choice(self.case["badges"]), rnd.choice(variants_of(rarity))[0]

    def _start(self) -> float:
        return 2 * (self.cw + self.gap) + self.cw / 2

    def busy(self) -> bool:
        return self.state in ("spin", "landed") or (self.state == "result" and time.monotonic() - self._stop_t < 0.9)

    def spin(self, result: dict) -> None:
        rnd = random.Random()
        self.strip = [self._filler(rnd) for _ in range(self.ITEMS)]
        self.strip[self.WIN] = (result["badge"], result["var"])
        self.result = result
        self.state = "spin"
        self.offset = self._start()
        self._target = self.WIN * (self.cw + self.gap) + self.cw / 2 + rnd.uniform(-0.38, 0.38) * self.cw
        self._t0 = time.monotonic()
        self._last_cell = int(self.offset // (self.cw + self.gap))
        self._sparks = []
        self._frames.start()

    def skip(self) -> None:
        """Jump to the end (the Shop was left mid-opening)."""
        if self.state == "spin":
            self._t0 = time.monotonic() - self.SPIN_S
            self._step()

    def _step(self) -> None:
        now = time.monotonic()
        if self.state == "spin":
            t = min(1.0, (now - self._t0) / self.SPIN_S)
            eased = 1.0 - (1.0 - t) ** 4.2
            start = self._start()
            self.offset = start + (self._target - start) * eased
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
        elif self.state == "result" and now - self._stop_t > 6.0 and self.result["rarity"] == "basic":
            self._frames.setInterval(40)
        self.update()

    def _reveal(self) -> None:
        if self.result is None:
            return
        self.state = "result"
        self._stop_t = time.monotonic()
        rarity = self.result["rarity"]
        sfx.play("on")
        if rarity in ("very", "super"):
            QTimer.singleShot(180, lambda: sfx.play("on"))
        n = {"basic": 0, "rare": 14, "very": 26, "super": 46}[rarity]
        rnd = random.Random()
        self._sparks = [(rnd.uniform(0, math.tau), rnd.uniform(S(60), S(150)), rnd.uniform(0.6, 1.3)) for _ in range(n)]
        refund = self.ctx.wallet.pay_refund()
        if refund:
            self.result["refund"] = refund
        self.done.emit()

    def back_to_strip(self) -> None:
        if self.state == "result":
            self.state = "idle"
            self._frames.stop()
            self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()
        if self.state == "result" and not self.busy():
            self.back_to_strip()

    def hideEvent(self, _e) -> None:
        self.skip()

    # -- painting
    def _card(self, p: QPainter, rect: QRectF, ident: str, var: str, now: float, flash: float = 0.0) -> None:
        rarity = VARIANT[var][2]
        col = QColor(RARITY_COLOUR[rarity])
        g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        g.setColorAt(0.0, QColor("#11171A"))
        g.setColorAt(1.0, mix(QColor("#11171A"), col, 0.32))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(rect, S(8), S(8))
        p.setBrush(col)
        p.drawRoundedRect(QRectF(rect.left() + S(6), rect.bottom() - S(5), rect.width() - S(12), S(3)), S(1.5), S(1.5))
        size = rect.width() * 0.56
        paint_badge(p, ident, QRectF(rect.center().x() - size / 2, rect.center().y() - size / 2 - S(4), size, size), var,
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
        else:
            self._paint_strip(p, r, now)
        p.restore()
        p.setPen(QPen(alpha("#FFFFFF", 0.08), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, S(12), S(12))

    def _paint_strip(self, p: QPainter, r: QRectF, now: float) -> None:
        cx = r.center().x()
        ch = S(88)
        top = r.center().y() - ch / 2
        step = self.cw + self.gap
        first = max(0, int((self.offset - cx) // step) - 1)
        speed = 0.0
        if self.state == "spin":
            t = min(1.0, (now - self._t0) / self.SPIN_S)
            speed = (1.0 - t) ** 3.2
        for i in range(first, min(self.ITEMS, first + int(r.width() // step) + 4)):
            x = cx - self.offset + i * step
            ident, var = self.strip[i]
            flash = 0.0
            if self.state == "landed" and i == self.WIN:
                flash = max(0.0, 1.0 - (now - self._stop_t) / 0.6) * (0.5 + 0.5 * math.sin((now - self._stop_t) * 30))
            self._card(p, QRectF(x, top, self.cw, ch), ident, var, now, flash)
        fade = QLinearGradient(r.topLeft(), r.topRight())                      # dark edges
        fade.setColorAt(0.0, QColor(9, 12, 13, 250))
        fade.setColorAt(0.22, QColor(9, 12, 13, 0))
        fade.setColorAt(0.78, QColor(9, 12, 13, 0))
        fade.setColorAt(1.0, QColor(9, 12, 13, 250))
        p.fillRect(r, fade)
        heat = speed if self.state == "spin" else 0.0
        mark = mix(QColor(GOLD_TEXT), QColor("#FFFFFF"), heat)
        p.setPen(QPen(alpha(mark, 0.35), S(6)))
        p.drawLine(QPointF(cx, top - S(10)), QPointF(cx, top + ch + S(10)))
        p.setPen(QPen(mark, S(2)))
        p.drawLine(QPointF(cx, top - S(10)), QPointF(cx, top + ch + S(10)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mark)
        for y, d in ((top - S(14), 1), (top + ch + S(14), -1)):
            path = QPainterPath()
            path.moveTo(cx - S(7), y)
            path.lineTo(cx + S(7), y)
            path.lineTo(cx, y + d * S(9))
            path.closeSubpath()
            p.drawPath(path)
        if self.state == "idle" and self.result is None:
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(10, QFont.Weight.DemiBold))
            p.drawText(QRectF(r.left(), r.bottom() - S(26), r.width(), S(18)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("{n} badges, 17 colours each", n=len(self.case["badges"])))

    def _paint_result(self, p: QPainter, r: QRectF, now: float) -> None:
        res = self.result
        rarity = res["rarity"]
        col = QColor(RARITY_COLOUR[rarity])
        age = now - self._stop_t
        c = QPointF(r.center().x(), r.top() + S(66))
        burst = QRadialGradient(c, S(150))
        burst.setColorAt(0.0, alpha(col, 0.42 if rarity != "basic" else 0.18))
        burst.setColorAt(1.0, alpha(col, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(burst)
        p.drawEllipse(c, S(150), S(150))
        if rarity != "basic":                                               # rays
            rays = {"rare": 8, "very": 12, "super": 16}[rarity]
            p.save()
            p.translate(c)
            p.rotate(now * (14 if rarity == "rare" else 22))
            for k in range(rays):
                p.rotate(360 / rays)
                path = QPainterPath()
                path.moveTo(0, 0)
                path.lineTo(S(170), -S(10))
                path.lineTo(S(170), S(10))
                path.closeSubpath()
                p.setBrush(alpha(col, 0.10 if rarity == "rare" else 0.16))
                p.drawPath(path)
            p.restore()
        if age < 0.35:                                                      # white flash as it opens
            p.setBrush(QColor(255, 255, 255, int(200 * (1 - age / 0.35))))
            p.drawRect(r)
        for ang, dist, spd in self._sparks:                                 # sparks flying out
            k = min(1.0, age * spd / 1.4)
            if k >= 1.0:
                continue
            d = dist * (1 - (1 - k) ** 3)
            pt = QPointF(c.x() + d * math.cos(ang), c.y() + d * math.sin(ang))
            sc = QColor("#FFF6D8") if rarity == "super" else mix(col, QColor("#FFFFFF"), 0.5)
            sc.setAlphaF(1.0 - k)
            p.setBrush(sc)
            p.drawEllipse(pt, S(2.2) * (1 - k * 0.5), S(2.2) * (1 - k * 0.5))
        pop = min(1.0, age / 0.45)
        over = 1 + 0.18 * math.sin(pop * math.pi) * (1 - pop)
        size = S(70) * (0.4 + 0.6 * (1 - (1 - pop) ** 3)) * over
        paint_badge(p, res["badge"], QRectF(c.x() - size / 2, c.y() - size / 2, size, size), res["var"], now)
        p.setPen(QColor(TEXT))
        p.setFont(font(14, QFont.Weight.Bold))
        p.drawText(QRectF(r.left(), r.top() + S(110), r.width(), S(22)), int(Qt.AlignmentFlag.AlignCenter),
                   badge_label(res["badge"], res["var"]))
        p.setPen(col)
        p.setFont(font(10.5, QFont.Weight.ExtraBold))
        p.drawText(QRectF(r.left(), r.top() + S(131), r.width(), S(16)), int(Qt.AlignmentFlag.AlignCenter),
                   tr(RARITY_NAME[rarity]).upper())
        if res["new"] or self.ctx.wallet.admin:
            text, tc, bgc = tr("NEW"), "#0A0D0E", ui.accent
        else:
            text, tc, bgc = tr("Duplicate: +{n} coins", n=coins_text(res.get("refund", 0))), GOLD_TEXT, alpha(GOLD_TEXT, 0.14)
        p.setFont(font(10, QFont.Weight.ExtraBold))
        tw = p.fontMetrics().horizontalAdvance(text) + S(20)
        pill = QRectF(c.x() - tw / 2, r.top() + S(150), tw, S(20))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bgc)
        p.drawRoundedRect(pill, S(10), S(10))
        p.setPen(QColor(tc))
        p.drawText(pill, int(Qt.AlignmentFlag.AlignCenter), text)


class CaseContents(BadgeGrid):
    """The ten badges a case can give, with how many colours of each you own."""
    COLS = 5
