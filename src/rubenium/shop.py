"""The shop (Themes tab): everything that changes the look is bought here with coins."""
from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QAbstractButton, QGridLayout, QWidget

from . import extras
from .core import lang, S, sfx, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, mix, tr, ui
from .pages import Page
from .wallet import CATALOG, COLOURS, COLOUR_HEX, DROP_COINS, coins_text, paint_coin
from .widgets import Button, IconButton, Label, Segmented, Toggle, Tween, draw_icon, hbox, heading, row, vbox

GOLD_TEXT = "#E8C26A"


def clock_text(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds >= 3600:
        return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
    return f"{seconds // 60}:{seconds % 60:02d}"


class CoinBar(QWidget):
    """Your coins, and the countdown to the next coin drop."""

    def __init__(self, ctx, keys: bool = False) -> None:
        super().__init__()
        self.ctx = ctx
        self.keys = keys                           # in the casino it also shows your keys
        self.setFixedHeight(S(40))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._shown = float(ctx.wallet.balance())
        self._tick = QTimer(self)
        self._tick.setInterval(33)
        self._tick.timeout.connect(self._step)
        self._second = QTimer(self)
        self._second.setInterval(1000)
        self._second.timeout.connect(self.update)
        ctx.wallet.changed.connect(self._changed)

    def showEvent(self, _e) -> None:
        self._second.start()
        self._changed()

    def hideEvent(self, _e) -> None:
        self._second.stop()
        self._tick.stop()

    def _changed(self) -> None:
        if self.isVisible():
            self._tick.start()

    def _step(self) -> None:                       # the number rolls to its new value
        target = float(self.ctx.wallet.balance())
        gap = target - self._shown
        if abs(gap) < 1:
            self._shown = target
            self._tick.stop()
        else:
            self._shown += gap * 0.18 + (1 if gap > 0 else -1)
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha("#FFFFFF", 0.08), 1))
        p.setBrush(alpha("#FFFFFF", 0.04))
        p.drawRoundedRect(r, S(11), S(11))
        paint_coin(p, QPointF(r.left() + S(20), r.center().y()), S(9))
        p.setPen(QColor(TEXT))
        p.setFont(font(16, QFont.Weight.Bold))
        p.drawText(QRectF(r.left() + S(36), r.top(), r.width() / 2, r.height()), int(Qt.AlignmentFlag.AlignVCenter),
                   coins_text(round(self._shown)))
        right = QRectF(r.center().x(), r.top(), r.width() / 2 - S(12), r.height())
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(11, QFont.Weight.DemiBold))
        text = "∞" if self.ctx.wallet.admin else f"+{DROP_COINS}  ·  {clock_text(self.ctx.wallet.next_drop())}"
        p.drawText(right, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), text)
        if self.keys:
            tw = p.fontMetrics().horizontalAdvance(text)
            n = str(min(self.ctx.wallet.keys(), 99))
            p.setPen(QColor(TEXT))
            p.setFont(font(12, QFont.Weight.Bold))
            nw = p.fontMetrics().horizontalAdvance(n)
            x = right.right() - tw - S(14) - nw
            p.drawText(QRectF(x, r.top(), nw + S(2), r.height()), int(Qt.AlignmentFlag.AlignVCenter), n)
            p.save()
            p.translate(x - S(12), r.center().y())
            p.scale(S(13) / 20, S(13) / 20)
            draw_icon(p, "key", ui.accent)
            p.restore()


def paint_price(p: QPainter, rect: QRectF, price: int, size: float = 10.0, colour=TEXT_DIM, centre: bool = True) -> None:
    """A small coin followed by a price, inside `rect`."""
    text = coins_text(price)
    p.setFont(font(size, QFont.Weight.DemiBold))
    tw = p.fontMetrics().horizontalAdvance(text)
    cr = S(size * 0.42)
    total = cr * 2 + S(4) + tw
    x = rect.center().x() - total / 2 if centre else rect.left()
    paint_coin(p, QPointF(x + cr, rect.center().y()), cr)
    p.setPen(QColor(colour))
    p.drawText(QRectF(x + cr * 2 + S(4), rect.top(), tw + S(2), rect.height()), int(Qt.AlignmentFlag.AlignVCenter), text)


class ThemeCard(QAbstractButton):
    """Mini card showing a theme's background design, with its price while it is locked."""

    def __init__(self, theme: dict, page) -> None:
        super().__init__()
        self.theme, self.page = theme, page
        self.setFixedHeight(S(92))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._hover = Tween(self, on_change=self.update)
        self._sparks = None

    def enterEvent(self, e) -> None:
        self._hover.to(1.0, 140)

    def leaveEvent(self, e) -> None:
        self._hover.to(0.0, 220)

    def paintEvent(self, _e) -> None:
        th, ctx = self.theme, self.page.ctx
        ident = f"theme:{th['id']}"
        unlocked = ctx.wallet.owns(ident)
        nxt = not unlocked and not ctx.wallet.blocked_by(ident)          # the next one that can be bought
        active = ctx.cfg["theme"] == th["id"] and unlocked
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self._hover.level
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        rad = S(11)
        path = QPainterPath()
        path.addRoundedRect(r, rad, rad)
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0, QColor("#0A0D0E"))
        g.setColorAt(1, QColor("#0F1314"))
        p.fillPath(path, g)
        p.save()
        p.setClipPath(path)
        p.setOpacity(1.0 if unlocked else (0.6 if nxt else 0.32) + 0.2 * h)
        pm = extras.theme_pattern(th, int(r.width()), int(r.height()), ui.accent, self.devicePixelRatioF(),
                                  ui.scale * 0.7, r.height() * 1.1)
        if pm is not None:
            p.drawPixmap(r.topLeft(), pm)
        if self._sparks is None:
            self._sparks = extras.theme_sparkles(th, r.width(), r.height(), r.height() * 0.6)
        extras.paint_sparkles(p, self._sparks, r.left(), r.top(), ui.accent, 1.2, ui.scale * 0.8)
        p.restore()
        p.setOpacity(1.0 if (unlocked or h > 0.5) else 0.6)
        extras.paint_theme_edge(p, th, r, rad, 0.9 if active else 0.25 + 0.3 * h, True, 0.0)
        p.setOpacity(1.0)
        p.setPen(QColor(TEXT) if unlocked else mix(QColor(TEXT_DIM), QColor(TEXT), h))
        p.setFont(font(13, QFont.Weight.Bold))
        p.drawText(QRectF(r.left() + S(12), r.top() + S(9), r.width() - S(24), S(20)),
                   int(Qt.AlignmentFlag.AlignVCenter), tr(th["name"]))
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        foot = QRectF(r.left() + S(12), r.bottom() - S(27), r.width() - S(24), S(18))
        if active:
            p.setPen(ui.accent)
            p.drawText(foot, int(Qt.AlignmentFlag.AlignVCenter), tr("In use"))
        elif unlocked:
            p.setPen(mix(QColor(TEXT_DIM), QColor(TEXT), h))
            p.drawText(foot, int(Qt.AlignmentFlag.AlignVCenter), tr("Use"))
        else:
            p.save()
            p.translate(foot.left() + S(6), foot.center().y())
            p.scale(S(11) / 20, S(11) / 20)
            draw_icon(p, "lock", QColor(TEXT_DIM))
            p.restore()
            paint_price(p, QRectF(foot.left() + S(18), foot.top(), foot.width() - S(18), foot.height()),
                        ctx.wallet.price(ident), 10.5, GOLD_TEXT if nxt else TEXT_DIM, centre=False)


class UnlockTile(QAbstractButton):
    """A small ball showing one style of the R or of the song ring. Locked ones show their price."""

    def __init__(self, kind: str, style: dict, key: str, page) -> None:
        super().__init__()
        self.kind, self.style, self.key, self.page = kind, style, key, page
        self.ident = f"{kind}:{style['id']}"
        self.setFixedSize(S(62), S(74))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._hover = Tween(self, on_change=self.update)

    def enterEvent(self, e) -> None:
        self._hover.to(1.0, 140)

    def leaveEvent(self, e) -> None:
        self._hover.to(0.0, 220)

    def paintEvent(self, _e) -> None:
        ctx, st = self.page.ctx, self.style
        open_ = ctx.wallet.owns(self.ident)
        current = ctx.ball_style() if self.kind == "r" else ctx.ring_style()
        active = open_ and current == st["id"]
        h = self._hover.level
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = float(S(46))
        c = QPointF(self.width() / 2, S(4) + d / 2)
        p.setPen(QPen(mix(alpha("#FFFFFF", 0.10 + 0.12 * h), ui.accent, 1.0 if active else 0.0), 1.3))
        p.setBrush(QColor("#0A0D0E"))
        p.drawEllipse(c, d / 2, d / 2)
        p.setOpacity(1.0 if open_ else 0.38 + 0.2 * h)
        box = QRectF(c.x() - d / 2, c.y() - d / 2 - d * 0.02, d, d)
        if self.kind == "r":
            extras.paint_r(p, box, d, st["id"], ui.accent, 0.6)
        else:
            ring = QRectF(c.x() - d / 2, c.y() - d / 2, d, d).adjusted(S(6), S(6), -S(6), -S(6))
            extras.paint_ring(p, ring, st["id"], 0.68, ui.accent, S(2.4))
        p.setOpacity(1.0)
        foot = QRectF(0, S(4) + d + S(4), self.width(), S(16))
        if open_:
            p.setFont(font(10, QFont.Weight.DemiBold))
            p.setPen(ui.accent if active else mix(QColor(TEXT_DIM), QColor(TEXT), h))
            p.drawText(foot, int(Qt.AlignmentFlag.AlignCenter), tr(st["name"]))
        else:
            paint_price(p, foot, ctx.wallet.price(self.ident), 9.5)


class HueLine(QWidget):
    """A line of colours: click or slide to pick one. `dim` greys it out (the music is choosing the colour);
    `locked` shows it dark and barred with the hours it needs."""
    picked = pyqtSignal(str)
    SAT, VAL = 0.80, 1.0

    def __init__(self, colour: str, locked_hours: int = 0) -> None:
        super().__init__()
        self.setFixedHeight(S(30))
        self.dim = False
        self.locked = False
        self.locked_hours = locked_hours
        self._hue = self._hue_of(colour)
        self.knob_on = True                       # off while white or black is picked: one or the other, never both
        self._down = False
        self._knob = Tween(self, self._hue, self.update)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @staticmethod
    def _hue_of(colour: str) -> float:
        h = QColor(colour).hsvHueF()
        return max(0.0, min(0.999, h if h >= 0 else 0.58))

    def colour(self) -> QColor:
        return QColor.fromHsvF(self._hue, self.SAT, self.VAL)

    def set_colour(self, colour: str) -> None:
        self._hue = self._hue_of(colour)
        self._knob.to(self._hue, 200)

    def set_state(self, dim: bool, locked: bool) -> None:
        self.dim, self.locked = dim, locked
        self.setCursor(Qt.CursorShape.ArrowCursor if (dim or locked) else Qt.CursorShape.PointingHandCursor)
        self.update()

    def _bar(self) -> QRectF:
        return QRectF(S(9), self.height() / 2 - S(5), self.width() - S(18), S(10))

    def _pick(self, x: float, glide: bool) -> None:
        self.knob_on = True
        bar = self._bar()
        self._hue = max(0.0, min(0.999, (x - bar.left()) / max(1.0, bar.width())))
        self._knob.to(self._hue, 160) if glide else self._knob.jump(self._hue)
        self.picked.emit(self.colour().name())
        self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and not (self.dim or self.locked):
            self._down = True
            self._pick(e.position().x(), True)
        e.accept()                               # never drags the card

    def mouseMoveEvent(self, e) -> None:
        if self._down:
            self._pick(e.position().x(), False)

    def mouseReleaseEvent(self, e) -> None:
        if self._down:
            self._down = False
            sfx.play("pick")

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bar = self._bar()
        g = QLinearGradient(bar.topLeft(), bar.topRight())
        for i in range(13):
            g.setColorAt(i / 12, QColor.fromHsvF(min(0.999, i / 12), self.SAT, self.VAL))
        off = self.dim or self.locked
        parked = not self.knob_on and not off            # a plain colour is in use: the line rests
        p.setOpacity(0.16 if self.locked else (0.28 if self.dim else (0.6 if parked else 1.0)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(bar, bar.height() / 2, bar.height() / 2)
        p.setOpacity(1.0)
        if self.locked:                           # dark, barred, with the hours it needs
            clip = QPainterPath()
            clip.addRoundedRect(bar, bar.height() / 2, bar.height() / 2)
            p.save()
            p.setClipPath(clip)
            p.setPen(QPen(alpha("#000000", 0.55), S(3)))
            x = bar.left() - bar.height()
            while x < bar.right():
                p.drawLine(QPointF(x, bar.bottom()), QPointF(x + bar.height(), bar.top()))
                x += S(9)
            p.restore()
            text = f"{self.locked_hours} h"
            p.setFont(font(10.5, QFont.Weight.Bold))
            tw = p.fontMetrics().horizontalAdvance(text) + S(34)
            pill = QRectF(bar.center().x() - tw / 2, bar.center().y() - S(10), tw, S(20))
            p.setPen(QPen(alpha("#FFFFFF", 0.12), 1))
            p.setBrush(QColor(14, 17, 18))
            p.drawRoundedRect(pill, S(10), S(10))
            p.save()
            p.translate(pill.left() + S(14), pill.center().y())
            p.scale(S(11) / 20, S(11) / 20)
            draw_icon(p, "lock", QColor(TEXT_DIM))
            p.restore()
            p.setPen(QColor(TEXT_DIM))
            p.drawText(pill.adjusted(S(22), 0, -S(8), 0), int(Qt.AlignmentFlag.AlignCenter), text)
            return
        if off:
            return
        x = bar.left() + bar.width() * self._knob.level
        if parked:                                       # the knob sits just off the line, empty: not in use
            p.setPen(QPen(alpha("#FFFFFF", 0.55), S(1.4)))
            p.setBrush(QColor(14, 17, 18))
            p.drawEllipse(QPointF(x, bar.bottom() + S(4.5)), S(4.2), S(4.2))
            return
        c = QPointF(x, bar.center().y())
        p.setPen(QPen(QColor("#FFFFFF"), S(2)))
        p.setBrush(QColor.fromHsvF(max(0.0, min(0.999, self._knob.level)), self.SAT, self.VAL))
        p.drawEllipse(c, S(8), S(8))


class ColourRow(QWidget):
    """Sixteen small squares: owned colours can be picked, the others bought one by one. Once all sixteen are
    owned they melt into a colour line (plus white and black) on which any colour can be picked."""
    N = len(COLOURS)

    def __init__(self, page, kind: str, key: str) -> None:
        super().__init__()
        self.page, self.ctx, self.kind, self.key = page, page.ctx, kind, key
        self.setFixedSize(page.W, S(26))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.dim = False
        self.blocked = False                       # second colours wait for every first colour
        self._hover = -1
        self.sq = S(18)
        self.gap = (page.W - self.N * self.sq) / (self.N - 1)
        self.melt = Tween(self, 0.0, self.update, QEasingCurve.Type.InOutCubic)
        self.melt.finished.connect(self._melted)
        self.line = HueLine(self.ctx.cfg[key] or "#2D9CFF")
        self.line.setParent(self)
        self.line.setGeometry(0, 0, int(page.W - 2 * (self.sq + S(6))), self.height())
        self.line.picked.connect(lambda col: self.page.set_colour(self.kind, col))
        self.fused = self.ctx.wallet.all_colours(kind)
        self.line.setVisible(self.fused)

    def _square(self, i: int) -> QRectF:
        return QRectF(i * (self.sq + self.gap), (self.height() - self.sq) / 2, self.sq, self.sq)

    def _end_slot(self, n: int) -> QRectF:           # white and black sit at the right of the line
        x = self.width() - (2 - n) * self.sq - (1 - n) * S(6)
        return QRectF(x, (self.height() - self.sq) / 2, self.sq, self.sq)

    def set_state(self, dim: bool, blocked: bool) -> None:
        self.dim, self.blocked = dim, blocked
        self.line.set_state(dim, False)
        self.update()

    def start_melt(self) -> None:
        """All sixteen are owned: the squares flow together into the colour line."""
        if not self.fused and self.melt.target < 1.0:
            self.melt.jump(0.0)
            self.melt.to(1.0, 900)

    def _melted(self) -> None:
        if self.melt.target >= 1.0 and not self.fused:
            self.fused = True
            self.line.set_colour(self.ctx.cfg[self.key] or "#2D9CFF")
            self.line.show()
            self.update()

    def _index_at(self, pos) -> int:
        if self.fused:
            for n in (0, 1):
                if self._end_slot(n).adjusted(-2, -2, 2, 2).contains(pos):
                    return n
            return -1
        for i in range(self.N):
            if self._square(i).adjusted(-self.gap / 2, -4, self.gap / 2, 4).contains(pos):
                return i
        return -1

    def mouseMoveEvent(self, e) -> None:
        i = self._index_at(e.position())
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = -1
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()
        if e.button() != Qt.MouseButton.LeftButton or self.melt.busy:
            return
        i = self._index_at(e.position())
        if i < 0:
            return
        ident, _name, hexa = COLOURS[i]
        if self.blocked:
            return self.ctx.toast(tr("Unlock every Colour 1 first"), "warn")
        if self.dim:
            return
        if self.ctx.wallet.owns(f"{self.kind}:{ident}"):
            sfx.play("pick")
            self.page.set_colour(self.kind, hexa)
        else:
            self.page.buy(f"{self.kind}:{ident}")

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        wallet = self.ctx.wallet
        current = (self.ctx.cfg[self.key] or "").upper()
        if self.kind == "c1" and not current:
            current = COLOUR_HEX["white"]
        plain = current in (COLOUR_HEX["white"].upper(), COLOUR_HEX["black"].upper())
        if self.line.knob_on == plain:
            self.line.knob_on = not plain
            self.line.update()
        t = 1.0 if self.fused else max(0.0, min(1.0, self.melt.level))
        base = 0.3 if (self.dim or self.blocked) else 1.0
        bar = self.line._bar().translated(self.line.x(), 0)
        hues = [i for i in range(self.N) if i > 1]
        for i, (ident, _name, hexa) in enumerate(COLOURS):
            r = self._square(i)
            if t > 0.0:                               # on the way to the line (or already there)
                if i <= 1:
                    goal = self._end_slot(i)
                else:
                    k = hues.index(i)
                    goal = QRectF(bar.left() + k * bar.width() / len(hues), bar.top(), bar.width() / len(hues) + 0.6,
                                  bar.height())
                r = QRectF(r.left() + (goal.left() - r.left()) * t, r.top() + (goal.top() - r.top()) * t,
                           r.width() + (goal.width() - r.width()) * t, r.height() + (goal.height() - r.height()) * t)
            if self.fused and i > 1:
                continue                              # the line itself is drawn by the HueLine
            owned = wallet.owns(f"{self.kind}:{ident}")
            col = QColor(hexa)
            rad = S(5) * (1.0 - t) if i > 1 else S(5)
            resting = self.fused and i <= 1 and not plain and not self.dim     # the line is in use: greyed a bit
            p.setOpacity(base * (1.0 if owned else 0.9) * (0.4 if resting else 1.0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(col if owned else alpha(col, 0.20))
            p.drawRoundedRect(r, rad, rad)
            if ident == "black" and owned:
                p.setPen(QPen(alpha("#FFFFFF", 0.25), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), rad, rad)
            if not owned:                             # a small lock
                p.save()
                p.translate(r.center())
                p.scale(S(9) / 20, S(9) / 20)
                draw_icon(p, "lock", alpha("#FFFFFF", 0.55))
                p.restore()
            picked = owned and current == hexa.upper() and not self.dim
            if picked or (i == self._hover and base == 1.0 and t in (0.0, 1.0)):
                p.setOpacity(base)
                p.setPen(QPen(QColor("#FFFFFF") if picked else alpha("#FFFFFF", 0.45), S(1.6)))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(-S(2.5), -S(2.5), S(2.5), S(2.5)), rad + S(2), rad + S(2))
        p.setOpacity(1.0)
        if self.blocked:                              # one lock for the whole row
            p.save()
            p.translate(self.width() / 2, self.height() / 2)
            p.scale(S(13) / 20, S(13) / 20)
            draw_icon(p, "lock", QColor(TEXT))
            p.restore()


class ShopPage(Page):
    """Three parts: Look (colours, ball, themes), Badges (your collection) and Cases."""
    key = "themes"
    SECTIONS = ["Look", "Badges", "Cases"]

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.reel = None
        self.cards, self.unlocks, self.c1, self.c2 = [], [], None, None
        lay = vbox(self, 8)
        lay.addWidget(CoinBar(ctx, keys=True))
        tab = getattr(ctx, "shop_tab", 0)
        self.seg = Segmented([tr(n) for n in self.SECTIONS], tab)
        self.seg.changed.connect(self._section)
        lay.addWidget(self.seg)
        if tab == 1:
            self._badges(lay)
        elif tab == 2:
            self._cases(lay)
        else:
            self._look(lay)
        ctx.wallet.changed.connect(self._refresh)

    def _section(self, i: int) -> None:
        if self.reel is not None and self.reel.busy():
            return self.seg.set_index(2)
        self.ctx.shop_tab = i
        self.ctx.shop_badge = None
        self.ctx.shop_case = None
        self.ctx.window.drawer.close_now()
        self.ctx.reload_page()

    # -- Look
    def _look(self, lay) -> None:
        ctx, wallet = self.ctx, self.ctx.wallet
        lay.addWidget(heading(tr("Colour")))
        self.t_music = Toggle(bool(ctx.cfg["accent_from_art"]) and wallet.owns("music"))
        self.t_music.toggled_by_user.connect(self._music)
        self.music_wait = Label("", 10.5, TEXT_DIM)
        music = QWidget()
        ml = hbox(music, 8)
        texts = QWidget()
        tl = vbox(texts, 0)
        tl.addWidget(Label(tr("Use the colours of the music"), 12.5))
        tl.addWidget(self.music_wait)
        ml.addWidget(texts, 1)
        ml.addWidget(self.t_music, 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(music)
        self._music_text()
        lay.addWidget(Label(tr("Colour 1"), 12.5))
        self.c1 = ColourRow(self, "c1", "custom_accent")
        lay.addWidget(self.c1)
        self.t_second = Toggle(bool(ctx.cfg["accent2_on"]))
        self.t_second.toggled_by_user.connect(self._second_on)
        lay.addWidget(row(tr("Colour 2"), self.t_second))
        self.c2 = ColourRow(self, "c2", "accent2")
        lay.addWidget(self.c2)

        lay.addWidget(heading(tr("Ball")))
        for kind, styles, key in (("r", extras.R_STYLES, "ball_style"), ("ring", extras.RING_STYLES, "ring_style")):
            line = hbox(spacing=0)
            for n, st in enumerate(styles):
                tile = UnlockTile(kind, st, key, self)
                tile.clicked.connect(lambda _=False, t=tile: self._unlock_pick(t))
                line.addWidget(tile)
                if n < len(styles) - 1:
                    line.addStretch(1)
                self.unlocks.append(tile)
            lay.addLayout(line)

        lay.addWidget(heading(tr("Themes")))
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(S(2))
        for i, th in enumerate(extras.THEMES):
            card = ThemeCard(th, self)
            card.clicked.connect(lambda _=False, t=th: self._pick(t))
            grid.addWidget(card, i // 2, i % 2)
            self.cards.append(card)
        lay.addLayout(grid)
        self._tick = QTimer(self)                      # the music colours count down to their hour
        self._tick.setInterval(15000)
        self._tick.timeout.connect(self._music_text)
        self._tick.start()
        self._refresh()

    def _music_text(self) -> None:
        wait = self.ctx.wallet.music_wait()
        done = max(0.0, (3600 - wait) / 3600)
        hours = f"{min(0.9, done):.1f}"
        self.music_wait.set_text("" if not wait else tr("{x} / 1 hour to unlock",
                                                        x=hours.replace(".", ",") if lang() == "fr" else hours))
        self.music_wait.setVisible(bool(wait))
        self.t_music.setEnabled(not wait)

    # -- Badges
    def _badges(self, lay) -> None:
        from .collection import BadgeGrid, BigBadge, Showcase, VariantPicker, worn
        ctx = self.ctx
        ident = getattr(ctx, "shop_badge", None)
        if not ident:
            lay.addWidget(heading(tr("Showcase")))
            self.showcase = Showcase(self)
            lay.addWidget(self.showcase)
            lay.addWidget(heading(tr("Collection")))
            lay.addWidget(BadgeGrid(self))
            return
        from .wallet import BADGE_NAME, CASE_OF
        top = hbox(spacing=8)
        back = IconButton("back", 32, tip=tr("Back"))
        back.clicked.connect(lambda: self.open_badge(None))
        top.addWidget(back)
        top.addWidget(Label(tr(BADGE_NAME[ident]), 15, bold=True), 1)
        top.addWidget(Label(tr(CASE_OF[ident]["name"]), 10.5, TEXT_DIM, align=Qt.AlignmentFlag.AlignRight), 1)
        lay.addLayout(top)
        self.big = BigBadge(self)
        lay.addWidget(self.big)
        self.picker = VariantPicker(self, ident)
        have = ctx.wallet.badge_variants(ident)
        first = next((v for v in have if f"{ident}/{v}" in worn(ctx)), have[0] if have else "grey")
        self.picker.var = getattr(ctx, "shop_var", "") or first
        ctx.shop_var = ""
        self.picker.picked.connect(self._variant)
        lay.addWidget(self.picker)
        self.badge_btn = Button("", "primary", 38)
        self.badge_btn.clicked.connect(self._badge_action)
        lay.addWidget(self.badge_btn)
        self._variant(self.picker.var)

    def open_badge(self, ident) -> None:
        if self.reel is not None and self.reel.busy():
            return
        self.ctx.shop_tab = 1
        self.ctx.shop_badge = ident
        self.ctx.reload_page()

    def _variant(self, var: str) -> None:
        from .collection import case_by_id, worn
        from .wallet import CASE_OF, VARIANT, badge_price
        ident = self.ctx.shop_badge
        self.big.show_variant(ident, var)
        w = self.ctx.wallet
        rarity = VARIANT[var][2]
        if w.has_badge(ident, var):
            on = f"{ident}/{var}" in worn(self.ctx)
            self.badge_btn.set_text(tr("Take off") if on else tr("Show on the music tab"))
            self.badge_btn.set_kind("ghost" if on else "primary")
        elif rarity == "basic":
            self.badge_btn.set_text(tr("Buy for {n} coins", n=coins_text(badge_price(ident))))
            self.badge_btn.set_kind("primary")
        else:
            self.badge_btn.set_text(tr("Find it in the {case}", case=tr(case_by_id(CASE_OF[ident]["id"])["name"])))
            self.badge_btn.set_kind("ghost")
        self.badge_btn.update()

    def _badge_action(self) -> None:
        from .collection import worn
        from .wallet import BADGE_NAME, CASE_OF, VARIANT, badge_price
        ctx, w = self.ctx, self.ctx.wallet
        ident, var = ctx.shop_badge, self.picker.var
        item = f"{ident}/{var}"
        if w.has_badge(ident, var):
            items = worn(ctx)
            if item in items:
                items.remove(item)
            elif len(items) >= 3:
                return ctx.toast(tr("Your showcase is full: take one off first"), "warn")
            else:
                items.append(item)
            sfx.play("pick")
            self.set_worn(items)
            self._variant(var)
            self.picker.update()
        elif VARIANT[var][2] == "basic":
            price = badge_price(ident)
            if price > w.balance():
                return ctx.toast(tr("Not enough coins: {n} more needed", n=coins_text(price - w.balance())), "warn")
            name = f"{tr(BADGE_NAME[ident])} · {tr(VARIANT[var][1])}"
            ctx.window.confirm(tr("Buy {name} for {n} coins?", name=name, n=coins_text(price)),
                               lambda: self._bought_badge(ident, var), yes=tr("Buy"))
        else:
            self.open_case(CASE_OF[ident]["id"])

    def _bought_badge(self, ident: str, var: str) -> None:
        from .collection import worn
        if not self.ctx.wallet.buy_badge(ident, var):
            return
        sfx.play("on")
        items = worn(self.ctx)
        if len(items) < 3:
            items.append(f"{ident}/{var}")
            self.set_worn(items)
        self._variant(var)
        self.picker.restart()

    def set_worn(self, items: list) -> None:
        self.ctx.cfg["badges"] = list(items)[:3]
        self.ctx.cfg.save()
        for page in self.ctx.window.each_page():
            fl = getattr(page, "flair", None)
            if fl is not None:
                fl.fit()
                fl.update()
        sc = getattr(self, "showcase", None)
        if sc is not None:
            sc.restart()

    # -- Cases
    def _cases(self, lay) -> None:
        from .collection import CaseCard, CaseContents, CaseReel, OddsTable, case_by_id
        ctx = self.ctx
        cid = getattr(ctx, "shop_case", None)
        if not cid:
            from .wallet import CASES
            for case in CASES:
                lay.addWidget(CaseCard(self, case))
            note = Label(tr("Keys come from playing in the casino. Basic colours can also be bought in Badges."), 10.5,
                         TEXT_DIM, wrap_w=self.W)
            lay.addWidget(note)
            return
        case = case_by_id(cid)
        top = hbox(spacing=8)
        self.case_back = IconButton("back", 32, tip=tr("Back"))
        self.case_back.clicked.connect(lambda: self.open_case(None))
        top.addWidget(self.case_back)
        top.addWidget(Label(tr(case["name"]), 15, bold=True), 1)
        lay.addLayout(top)
        self.reel = CaseReel(self, case)
        self.reel.done.connect(self._opened)
        lay.addWidget(self.reel)
        self.open_btn = Button(tr("Open for {n} coins + 1 key", n=coins_text(case["price"])), "primary", 40)
        self.open_btn.clicked.connect(lambda: self._open(case))
        lay.addWidget(self.open_btn)
        lay.addWidget(heading(tr("Chances")))
        lay.addWidget(OddsTable(case, self.W))
        lay.addWidget(heading(tr("Inside")))
        lay.addWidget(CaseContents(self, case["badges"]))

    def open_case(self, cid) -> None:
        if self.reel is not None and self.reel.busy():
            return
        self.ctx.shop_tab = 2
        self.ctx.shop_case = cid
        self.ctx.shop_badge = None
        self.ctx.reload_page()

    def _open(self, case: dict) -> None:
        w = self.ctx.wallet
        if self.reel.busy():
            return
        if w.keys() < 1:
            return self.ctx.toast(tr("You need a key: play in the casino"), "warn")
        if case["price"] > w.balance():
            return self.ctx.toast(tr("Not enough coins: {n} more needed", n=coins_text(case["price"] - w.balance())), "warn")
        res = w.open_case(case["id"])
        if res is None:
            return
        self.reel.spin(res)
        self._lock(True)

    def _opened(self) -> None:
        QTimer.singleShot(900, lambda: self._lock(False))

    def _lock(self, on: bool) -> None:
        for wdg in (self.open_btn, self.case_back, self.seg):
            wdg.setEnabled(not on)

    def open_badge_from_case(self, ident: str) -> None:
        self.open_badge(ident)

    # -- buying
    def buy(self, ident: str) -> None:
        wallet, item = self.ctx.wallet, CATALOG[ident]
        if wallet.owns(ident):
            return
        blocked = wallet.blocked_by(ident)
        if blocked == "c1:*":
            return self.ctx.toast(tr("Unlock every Colour 1 first"), "warn")
        if blocked:
            return self.ctx.toast(tr("Unlock {name} first", name=tr(CATALOG[blocked]["name"])), "warn")
        price = wallet.price(ident)
        if price > wallet.balance():
            return self.ctx.toast(tr("Not enough coins: {n} more needed", n=coins_text(price - wallet.balance())), "warn")
        self.ctx.window.confirm(tr("Buy {name} for {n} coins?", name=tr(item["name"]), n=coins_text(price)),
                                lambda: self._bought(ident), yes=tr("Buy"))

    def _bought(self, ident: str) -> None:
        wallet = self.ctx.wallet
        if not wallet.buy(ident):
            return
        sfx.play("on")
        kind = CATALOG[ident]["kind"]
        value = ident.split(":", 1)[1] if ":" in ident else ""
        if kind == "theme":                                  # what you buy is put on straight away
            self.ctx.window.drawer.close_now()
            self.ctx.set_theme(value)
        elif kind == "r":
            self.ctx.cfg["ball_style"] = value
        elif kind == "ring":
            self.ctx.cfg["ring_style"] = value
        elif kind in ("c1", "c2"):
            self.set_colour(kind, COLOUR_HEX[value])
            row_w = self.c1 if kind == "c1" else self.c2
            if wallet.all_colours(kind):
                row_w.start_melt()
        self.ctx.window.ball.update()
        self._refresh()

    def flair_changed(self) -> None:
        self.ctx.cfg.save()

    # -- colours
    def set_colour(self, kind: str, col: str) -> None:
        if kind == "c1":
            self.ctx.cfg["custom_accent"] = col
        else:
            self.ctx.cfg["accent2"] = col
            if not self.ctx.cfg["accent2_on"]:               # picking a second colour switches it on
                self.ctx.cfg["accent2_on"] = True
                self.t_second.set_checked(True)
        self.ctx.refresh_accent()
        self._rows()

    def _music(self, on: bool) -> None:
        if on and not self.ctx.wallet.owns("music"):
            self.t_music.set_checked(False)
            return self._music_text()
        self.ctx.cfg["accent_from_art"] = on
        self.ctx.refresh_accent()
        self._rows()

    def _second_on(self, on: bool) -> None:
        self.ctx.cfg["accent2_on"] = on
        self.ctx.refresh_accent()
        self._rows()

    def _rows(self) -> None:
        """With the music's colours on, your own colours are greyed out. Second colours come after the first."""
        if self.c1 is None:
            return
        wallet = self.ctx.wallet
        music = bool(self.ctx.cfg["accent_from_art"]) and wallet.owns("music")
        ready = wallet.all_colours("c1")
        has_second = any(wallet.owns(f"c2:{ident}") for ident, _n, _h in COLOURS)
        self.c1.set_state(music, False)
        self.c2.set_state(music and ready, not ready)
        self.t_second.setVisible(has_second)
        self.t_second.setEnabled(not music)

    # -- ball styles and themes
    def _unlock_pick(self, tile) -> None:
        if not self.ctx.wallet.owns(tile.ident):
            return self.buy(tile.ident)
        if self.ctx.cfg[tile.key] != tile.style["id"]:
            sfx.play("pick")
        self.ctx.cfg[tile.key] = tile.style["id"]
        self.ctx.window.ball.update()
        for t in self.unlocks:
            t.update()

    def _pick(self, th: dict) -> None:
        drawer = self.ctx.window.drawer
        if self.ctx.wallet.owns(f"theme:{th['id']}"):
            drawer.close_now()
            if self.ctx.cfg["theme"] != th["id"]:
                sfx.play("pick")
            self.ctx.set_theme(th["id"])
        elif drawer.is_open() and drawer.theme is th:
            drawer.close_drawer()
        else:
            drawer.open_for(th)
        self._refresh()

    def _refresh(self) -> None:
        self._rows()
        for w in self.cards + self.unlocks + [x for x in (self.c1, self.c2) if x is not None]:
            w.update()

    def on_show(self) -> None:
        self._refresh()

    def on_hide(self) -> None:
        self.ctx.window.drawer.close_now()
        if self.reel is not None:
            self.reel.skip()


class PriceTag(QWidget):
    """A coin and a price, as a small label."""

    def __init__(self, price: int) -> None:
        super().__init__()
        self.price = price
        self.setFixedSize(S(58), S(20))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_price(p, QRectF(self.rect()), self.price, 10.5, GOLD_TEXT)
