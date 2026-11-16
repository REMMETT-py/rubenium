"""The shop (Themes tab): everything that changes the look is bought here with coins."""
from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QAbstractButton, QGridLayout, QWidget

from . import extras
from .core import lang, S, sfx, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, mix, tr, ui
from .pages import Page
from .wallet import COLOURS, COLOUR_HEX, coins_text, paint_coin
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
        ec = self.ctx.econ
        text = f"+{int(ec.cfg.get('coin_amount', 10))}  ·  {clock_text(ec.next_coin_s())}"
        if not ec.ready:
            text = tr("Offline") if self.ctx.online.offline or not self.ctx.online.logged_in() else "…"
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


def paint_price(p: QPainter, rect: QRectF, price, size: float = 10.0, colour=TEXT_DIM, centre: bool = True,
                hours: bool = False) -> None:
    """A small coin followed by a price, inside `rect` (or, for progression, the hours of play it needs)."""
    if hours:
        text = f"{price:g} h"
        p.setFont(font(size, QFont.Weight.DemiBold))
        tw = p.fontMetrics().horizontalAdvance(text)
        x = rect.center().x() - (tw + S(size)) / 2 if centre else rect.left()
        p.save()
        p.translate(x + S(size * 0.4), rect.center().y())
        p.scale(S(size * 0.95) / 20, S(size * 0.95) / 20)
        draw_icon(p, "lock", QColor(colour))
        p.restore()
        p.setPen(QColor(colour))
        p.drawText(QRectF(x + S(size), rect.top(), tw + S(2), rect.height()), int(Qt.AlignmentFlag.AlignVCenter), text)
        return
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
            shop = th["id"].startswith("theme:")              # a shop theme: its price in coins
            paint_price(p, QRectF(foot.left() + S(18), foot.top(), foot.width() - S(18), foot.height()),
                        int(ctx.econ.info(th["id"]).get("price") or 0) if shop else ctx.wallet.hours_for(ident), 10.5,
                        GOLD_TEXT if nxt else TEXT_DIM, centre=False, hours=not shop)


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
            paint_price(p, foot, ctx.wallet.hours_for(self.ident), 9.5, hours=True)


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
    """Six parts: Theme (colours, progression), Shop (balls, lines, fonts, themes), Badges, Cases, Market and
    Inventory."""
    key = "themes"
    SECTIONS = ["Style", "Shop", "Collection", "Cases", "Market", "Inventory", "Sets", "Deals"]
    ICONS = ["spark", "ball", "shield", "gift", "chip", "folder", "grid", "timer"]
    GET = [1, 7, 3, 4]                     # getting things: shop, today's deals, cases, market
    MINE = [5, 2, 6, 0]                    # what is yours: inventory, collection, sets, your style
    NOTES = ["Your profile, your colours and the looks you unlock with time.", "Balls, lines, fonts, themes, banners and frames to buy.",
             "Your collection: click a badge to see every colour.", "Open cases for coins and badges. Gifts are free.",
             "Buy and sell with other users.", "Everything you own. Sell, show or trade it.",
             "Collect full sets for a big bonus.", "4 items cheaper today. New deals every day at midnight."]

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self.reel = None
        self.cards, self.unlocks, self.c1 = [], [], None
        lay = vbox(self, 8)
        lay.addWidget(CoinBar(ctx, keys=True))
        tab = getattr(ctx, "shop_tab", 0)
        from .bazaar import build_cosmetics, build_inventory, build_market
        from .hub import NavTiles
        gifts = sum(int(v or 0) for v in ctx.econ.stock.values())
        rows = []
        for title, ids in ((tr("GET ITEMS"), self.GET), (tr("YOURS"), self.MINE)):
            lay.addWidget(Label(title, 9.5, TEXT_FAINT, weight=QFont.Weight.Bold))
            nav = NavTiles([(tr(self.SECTIONS[k]), self.ICONS[k]) for k in ids], ids.index(tab) if tab in ids else -1,
                           badges={ids.index(3): gifts} if 3 in ids else {})
            nav.changed.connect(lambda i, ids=ids: self._section(ids[i]))
            lay.addWidget(nav)
            rows.append(nav)
        self.seg = rows[0]
        self.navs = rows
        note = Label(tr(self.NOTES[tab]), 10.5, TEXT_DIM, wrap_w=self.W)
        lay.addWidget(note)
        if tab == 1:
            build_cosmetics(self, lay)
        elif tab == 2:
            self._badges(lay)
        elif tab == 3:
            self._cases(lay)
        elif tab == 4:
            build_market(self, lay)
        elif tab == 5:
            build_inventory(self, lay)
        elif tab == 6:
            from .hub import build_sets
            build_sets(self, lay)
        elif tab == 7:
            from .hub import build_deals
            build_deals(self, lay)
        else:
            self._look(lay)
        ctx.wallet.changed.connect(self._refresh)

    def _section(self, i: int) -> None:
        if self.reel is not None and self.reel.busy():
            return None
        self.ctx.shop_tab = i
        self.ctx.shop_badge = None
        self.ctx.shop_case = None
        self.ctx.shop_design = None
        self.ctx.inv_pick = ""
        self.ctx.stop_preview()
        self.ctx.window.drawer.close_now()
        self.ctx.reload_page()

    # -- Look
    def _look(self, lay) -> None:
        ctx, wallet = self.ctx, self.ctx.wallet
        from .bazaar import build_profile_style
        build_profile_style(self, lay)
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
        self.t_screen = Toggle(bool(ctx.cfg["accent_from_screen"]) and not self.t_music.isChecked())
        self.t_screen.toggled_by_user.connect(self._screen)
        lay.addWidget(row(tr("Use screen colours"), self.t_screen))
        self._music_text()
        lay.addWidget(Label(tr("Colour 1"), 12.5))
        self.c1 = ColourRow(self, "c1", "custom_accent")
        lay.addWidget(self.c1)
        lay.addWidget(Label(tr("Themes from the shop bring their own second colour."), 10.5, TEXT_DIM, wrap_w=self.W))

        lay.addWidget(heading(tr("Progression")))
        lay.addWidget(UnlockBar(self))
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
        from .cosmetics import THEME_LOOKS, shop_theme
        every = list(extras.THEMES) + [shop_theme("theme:" + t[0]) for t in THEME_LOOKS]   # 3.0.0: shop themes too
        for i, th in enumerate(t for t in every if t):
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
        from .wallet import BADGE_NAME, badge_item, variants_for
        ctx, ec = self.ctx, self.ctx.econ
        base = getattr(ctx, "shop_badge", None)
        if not ec.ready:
            return lay.addWidget(Label(tr("Connecting…") if ctx.online.logged_in() else tr("Log in to see your badges"),
                                       12, TEXT_DIM))
        if not base:
            lay.addWidget(heading(tr("On show")))
            self.showcase = Showcase(self)
            lay.addWidget(self.showcase)
            lay.addWidget(heading(tr("Collection")))
            lay.addWidget(BadgeGrid(self))
            return
        top = hbox(spacing=8)
        back = IconButton("back", 32, tip=tr("Back"))
        back.clicked.connect(lambda: self.open_badge(None))
        top.addWidget(back)
        top.addWidget(Label(tr(BADGE_NAME[base]), 15, bold=True), 1)
        lay.addLayout(top)
        self.big = BigBadge(self)
        lay.addWidget(self.big)
        self.picker = VariantPicker(self, base)
        have = [v for v in variants_for(base) if ec.owns(badge_item(base, v))]
        first = next((v for v in have if badge_item(base, v) in worn(ctx)), have[0] if have else variants_for(base)[-1])
        self.picker.var = getattr(ctx, "shop_var", "") or first
        ctx.shop_var = ""
        self.picker.picked.connect(self._variant)
        lay.addWidget(self.picker)
        self.luck = Label("", 10.5, TEXT_DIM, wrap_w=self.W)
        lay.addWidget(self.luck)
        self.badge_btn = Button("", "primary", 38)
        self.badge_btn.clicked.connect(self._badge_action)
        lay.addWidget(self.badge_btn)
        self.sell_btn = Button(tr("Sell on the market"), "ghost", 32)
        self.sell_btn.clicked.connect(self._sell)
        lay.addWidget(self.sell_btn)
        self._variant(self.picker.var)

    def open_badge(self, base) -> None:
        if self.reel is not None and self.reel.busy():
            return
        self.ctx.shop_tab = 2
        self.ctx.shop_badge = base
        self.ctx.reload_page()

    def _item(self) -> str:
        from .wallet import badge_item
        return badge_item(self.ctx.shop_badge, self.picker.var)

    def _variant(self, var: str) -> None:
        from .collection import worn
        ec = self.ctx.econ
        self.picker.var = var
        item = self._item()
        self.big.show_item(item)
        from .collection import CASE_NAMES, chance_text, item_chances
        from .econ import CLASS_NAMES, RARITY_NAMES
        info = ec.info(item)
        head = tr(RARITY_NAMES.get(info.get("rarity", "standard"), "Common")) + " · " + tr(CLASS_NAMES[int(info.get("cls") or 0)])
        odds = item_chances(ec, item)
        if odds:
            best = "  ·  ".join(f"{tr(CASE_NAMES.get(cid, cid))}: {chance_text(pr)}" for cid, pr in odds[:3])
            self.luck.set_text(head + "\n" + tr("Chance of this exact badge per open:") + " " + best)
        else:
            self.luck.set_text(head + "\n" + tr("Not in any case right now."))
        price = ec.price(item)
        if ec.owns(item):
            on = item in worn(self.ctx)
            self.badge_btn.set_text(tr("Take off") if on else tr("Show on the music tab"))
            self.badge_btn.set_kind("ghost" if on else "primary")
        elif price is not None:
            self.badge_btn.set_text(tr("Buy for {n} coins", n=coins_text(price)))
            self.badge_btn.set_kind("primary")
        else:
            self.badge_btn.set_text(tr("Only from cases"))
            self.badge_btn.set_kind("ghost")
        self.badge_btn.setEnabled(True)
        self.sell_btn.setVisible(any(not i.get("locked") for i in ec.items if i["item"] == item))
        self.badge_btn.update()

    def _answer(self, ok: bool, data) -> None:
        """After the server answered: show an error, or refresh what this page shows."""
        if not ok:
            sfx.play("off")
            self.ctx.toast(tr(str(data)), "warn")
        if getattr(self, "picker", None) is not None and self.ctx.window.current == "themes":
            try:
                self._variant(self.picker.var)
                self.picker.restart()
            except RuntimeError:
                pass

    def _badge_action(self) -> None:
        from .collection import SLOTS, worn
        from .econ import RARITY_NAMES
        ctx, ec = self.ctx, self.ctx.econ
        item = self._item()
        if ec.owns(item):
            if item in worn(ctx):
                slot = next(s for s in SLOTS if ec.worn(s) == item)
                sfx.play("pick")
                return ec.wear(slot, "", self._answer)
            free = next((s for s in SLOTS if not ec.worn(s)), None)
            if free is None:
                return ctx.toast(tr("Your showcase is full: take one off first"), "warn")
            sfx.play("pick")
            return ec.wear(free, item, self._answer)
        price = ec.price(item)
        if price is None:
            self.ctx.shop_tab = 2
            self.ctx.shop_badge = None
            return ctx.reload_page()
        if price > ec.coins:
            return ctx.toast(tr("Not enough coins: {n} more needed", n=coins_text(price - ec.coins)), "warn")
        from .collection import badge_label
        text = tr("Buy {name} ({rarity}) for {n} coins?", name=badge_label(item), rarity=tr(RARITY_NAMES[ec.rarity(item)]),
                  n=coins_text(price))
        ctx.window.confirm(text, lambda: (self.badge_btn.setEnabled(False), ec.buy(item, self._bought_item)), yes=tr("Buy"))

    def _bought_item(self, ok: bool, data) -> None:
        if ok:
            sfx.play("on")
        self._answer(ok, data)

    def _sell(self) -> None:
        from .bazaar import market_sell
        market_sell(self.ctx, self._item())

    # -- Cases
    DAILY = {"id": "daily", "price": 0, "odds": [7500, 2000, 450, 50, 0, 0], "coin_min": 30, "coin_max": 120,
             "exotics": False, "pity_tier": 1, "pity_after": 0}

    def daily_wait(self):
        """Seconds until the free daily case (0 = ready, None = not known yet)."""
        return getattr(self.ctx, "daily_wait_s", None)

    def _timers(self) -> None:
        import time as _time

        def got(ok: bool, data) -> None:
            if ok and isinstance(data, dict):
                self.ctx.daily_ready_at = _time.monotonic() + int(data.get("daily") or 0)
                self._tick_daily()
        self.ctx.econ.call("rb_timers", {}, got)

    def _tick_daily(self) -> None:
        import time as _time
        at = getattr(self.ctx, "daily_ready_at", None)
        self.ctx.daily_wait_s = None if at is None else max(0, int(at - _time.monotonic()))
        for card in self.findChildren(QWidget):
            if getattr(card, "case", None) is not None and card.case.get("id") == "daily":
                card.update()

    def _cases(self, lay) -> None:
        from .collection import CASE_NAMES, CaseCard, CaseReel, OddsTable
        ctx, ec = self.ctx, self.ctx.econ
        if not ec.ready or not ec.cases:
            return lay.addWidget(Label(tr("Connecting…") if ctx.online.logged_in() else tr("Log in to open cases"),
                                       12, TEXT_DIM))
        cid = getattr(ctx, "shop_case", None)
        self._daily_timer = QTimer(self)
        self._daily_timer.setInterval(1000)
        self._daily_timer.timeout.connect(self._tick_daily)
        self._daily_timer.start()
        self._timers()
        if not cid:
            from .collection import case_kind
            from .games import KeyCard
            lay.addWidget(KeyCard(ctx))
            lay.addWidget(CaseCard(self, self.DAILY))
            if case_kind("starter"):
                for kind, title in (("coins", tr("Coin cases")), ("hunt", tr("Rare hunts")), ("style", tr("Style cases"))):
                    lay.addWidget(heading(title))
                    for case in ec.cases:
                        if case_kind(case["id"]) == kind:
                            lay.addWidget(CaseCard(self, case))
                for case in ec.cases:                         # a case the admin added later
                    if not case_kind(case["id"]):
                        lay.addWidget(CaseCard(self, case))
            else:
                for case in ec.cases:
                    lay.addWidget(CaseCard(self, case))
            lay.addWidget(Label(tr("Each case costs coins and 1 key."), 10.5, TEXT_DIM, wrap_w=self.W))
            return
        case = self.DAILY if cid == "daily" else next((c for c in ec.cases if c["id"] == cid), ec.cases[0])
        top = hbox(spacing=8)
        self.case_back = IconButton("back", 32, tip=tr("Back"))
        self.case_back.clicked.connect(lambda: self.open_case(None))
        top.addWidget(self.case_back)
        top.addWidget(Label(tr(CASE_NAMES.get(case["id"], "Daily Case")), 15, bold=True), 1)
        lay.addLayout(top)
        self.reel = CaseReel(self, case)
        self.reel.done.connect(self._opened)
        lay.addWidget(self.reel)
        gifts = int(ec.stock.get(case["id"], 0) or 0) if cid != "daily" else 0
        text = (tr("Open for free") if cid == "daily" else
                tr("Open your gift for free ({n} left)", n=gifts) if gifts else
                tr("Open for {n} coins + 1 key", n=coins_text(case["price"])))
        self.open_btn = Button(text, "primary", 40)
        self.open_btn.clicked.connect(lambda: self._open(case))
        lay.addWidget(self.open_btn)
        if cid != "daily":
            from .collection import CASE_NOTES
            if case["id"] in CASE_NOTES:
                lay.addWidget(Label(tr(CASE_NOTES[case["id"]]), 11, TEXT_DIM, wrap_w=self.W))
            gift = Button(tr("Gift this case to a friend"), "ghost", 30)
            gift.clicked.connect(lambda: self._gift(case))
            lay.addWidget(gift)
        if cid != "daily":
            lay.addWidget(heading(tr("Chances")))
            lay.addWidget(OddsTable(case, self.W))
        else:
            lay.addWidget(Label(tr("Once a day: coins, a key or a badge."),
                                10.5, TEXT_DIM, wrap_w=self.W))

    def open_case(self, cid) -> None:
        if self.reel is not None and self.reel.busy():
            return
        self.ctx.shop_tab = 3
        self.ctx.shop_case = cid
        self.ctx.shop_badge = None
        self.ctx.reload_page()

    def _open(self, case: dict) -> None:
        ctx, ec = self.ctx, self.ctx.econ
        if self.reel.busy() or getattr(self, "_asking", False):
            return
        daily = case["id"] == "daily"
        if daily and self.daily_wait() != 0:
            return ctx.toast(tr("Not ready yet"), "warn")
        gifted = not daily and int(ec.stock.get(case["id"], 0) or 0) > 0        # a gift: free, no coins and no key
        if gifted and ec.server_old and ec.keys < 1:
            return ctx.toast(tr("Gifts open for free once the server update is done. Until then they need 1 key."), "warn")
        gold = not daily and not gifted and ec.gold_keys > 0      # a gold key is used before a normal one
        if not daily and not gifted and ec.keys < 1 and not gold:
            return ctx.toast(tr("You need a key: 1 key every 15 minutes"), "warn")
        if not daily and not gifted and case["price"] > ec.coins:
            return ctx.toast(tr("Not enough coins: {n} more needed", n=coins_text(case["price"] - ec.coins)), "warn")
        self._asking = True
        self._lock(True)
        ec.holding = True

        def got(ok: bool, data) -> None:
            self._asking = False
            if not ok:
                ec.holding = False
                self._lock(False)
                sfx.play("off")
                return ctx.toast(tr(str(data)), "warn")
            self._pending = data                             # coins and item show when the strip stops
            ec.fetch_gold_keys()
            if daily:
                import time as _time
                ctx.daily_ready_at = _time.monotonic() + 24 * 3600
            try:
                self.reel.spin(data)
            except RuntimeError:
                pass
        if daily:
            ec.call("rb_daily_case", {}, got, hold=True)
        else:
            if gold:
                ec.gold_keys -= 1
            ec.call("rb_open_case_gold" if gold else "rb_open_case", {"which": case["id"]}, got, once=True, hold=True)

    def _opened(self) -> None:
        data, self._pending = getattr(self, "_pending", None), None
        self.ctx.econ.holding = False
        if data:
            ec = self.ctx.econ
            if data.get("item") and data.get("id"):
                ec.gained(data["item"], data["id"], "case")
            if "stock" in data:
                ec.stock[data.get("case") or self.ctx.shop_case] = int(data.get("stock") or 0)
            ec.absorb(data)
            ec.changed.emit()
            cid = self.ctx.shop_case
            case = next((c for c in ec.cases if c["id"] == cid), None)
            won = int(data.get("won") or 0)
            if case is not None and case.get("mode") != "jackpot" and won > int(case.get("coin_max") or 0) > 0:
                sfx.play("on")
                self.ctx.toast(tr("Lucky drop: ×3! +{n} coins", n=coins_text(won)))
            left = int(ec.stock.get(cid, 0) or 0) if cid and cid != "daily" else 0
            case = next((c for c in ec.cases if c["id"] == cid), None)
            if case is not None:
                try:
                    self.open_btn.set_text(tr("Open your gift for free ({n} left)", n=left) if left else
                                           tr("Open for {n} coins + 1 key", n=coins_text(case["price"])))
                except RuntimeError:
                    pass
        QTimer.singleShot(900, lambda: self._lock(False))

    def _gift(self, case: dict) -> None:
        from .bazaar import AskDialog
        from .collection import CASE_NAMES
        ctx, ec = self.ctx, self.ctx.econ
        if not ec.can_trade():
            return ctx.toast(tr("Gifts unlock after 5 hours with Rubenium"), "warn")

        def send(name: str, dlg) -> None:
            if case["price"] > ec.coins:
                return dlg.say(tr("Not enough coins"))
            if ec.keys < 1 and "case_lucky_pct" in ec.cfg:
                return dlg.say(tr("You need a key: 1 key every 15 minutes"))

            def done(ok: bool, data) -> None:
                if not ok:
                    return dlg.say(tr(str(data)))
                dlg.close()
                sfx.play("on")
                ctx.toast(tr("Gift sent to {name}!", name=name))
            ec.call("rb_case_gift", {"name": name, "which": case["id"]}, done, once=True)
        ctx._ask = AskDialog(ctx, tr("Gift: {case}", case=tr(CASE_NAMES.get(case["id"], ""))), tr("Friend's username"),
                             tr("Gift for {n}", n=coins_text(case["price"])), send, 10,
                             tr("It costs {n} coins and 1 key. Your friend opens it for free. 3 gifts a day at most.",
                                n=coins_text(case["price"])) if "case_lucky_pct" in ec.cfg else
                             tr("Your friend opens it for free. 3 gifts a day at most."))

    def _lock(self, on: bool) -> None:
        try:
            for wdg in (self.open_btn, self.case_back, *getattr(self, "navs", [])):
                wdg.setEnabled(not on)
        except RuntimeError:
            pass

    # -- progression: nothing is bought, it opens with time played
    def buy(self, ident: str) -> None:
        hours = self.ctx.wallet.hours_for(ident)
        self.ctx.toast(tr("Unlocks after {n} h with Rubenium", n=f"{hours:g}"), "warn")

    def claim_set(self, which: str) -> None:
        from .hub import claim_set
        claim_set(self.ctx, which)

    def flair_changed(self) -> None:
        self.ctx.cfg.save()

    # -- colours
    def set_colour(self, kind: str, col: str) -> None:
        self.ctx.cfg["custom_accent"] = col
        self.ctx.refresh_accent()
        self._rows()

    def _music(self, on: bool) -> None:
        if on and not self.ctx.wallet.owns("music"):
            self.t_music.set_checked(False)
            return self._music_text()
        self.ctx.set_colour_source("music" if on else "")
        if on:
            self.t_screen.set_checked(False)
        self._rows()

    def _screen(self, on: bool) -> None:
        """Only one of the two at a time: no fighting colours."""
        self.ctx.set_colour_source("screen" if on else "")
        if on:
            self.t_music.set_checked(False)
        self._rows()

    def _rows(self) -> None:
        """With the music's (or the screen's) colours on, your own colour is greyed out."""
        if self.c1 is None:
            return
        wallet = self.ctx.wallet
        auto = (bool(self.ctx.cfg["accent_from_art"]) and wallet.owns("music")) or bool(self.ctx.cfg["accent_from_screen"])
        self.c1.set_state(auto, False)

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
        for w in self.cards + self.unlocks + [x for x in (self.c1,) if x is not None]:
            w.update()

    def on_show(self) -> None:
        self._refresh()

    def on_hide(self) -> None:
        self.ctx.window.drawer.close_now()
        self.ctx.stop_preview()
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


class UnlockBar(QWidget):
    """Time played, and how far the next unlock is."""

    def __init__(self, page) -> None:
        super().__init__()
        self.ctx = page.ctx
        self.setFixedHeight(S(40))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.ctx.wallet.changed.connect(self.update)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        hours = self.ctx.wallet.minutes() / 60
        steps = sorted({float(st["hours"]) for group in (extras.THEMES, extras.R_STYLES, extras.RING_STYLES)
                        for st in group})
        nxt = next((h for h in steps if h > hours), None)
        prev = max([h for h in steps if h <= hours] or [0.0])
        r = QRectF(self.rect())
        p.setPen(QColor(TEXT))
        p.setFont(font(12.5, QFont.Weight.DemiBold))
        shown = f"{hours:.1f}".replace(".", "," if lang() == "fr" else ".")
        p.drawText(QRectF(0, 0, r.width(), S(20)), int(Qt.AlignmentFlag.AlignVCenter), tr("{n} h played", n=shown))
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(11, QFont.Weight.DemiBold))
        p.drawText(QRectF(0, 0, r.width(), S(20)), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                   tr("Everything unlocked") if nxt is None else tr("Next unlock at {n} h", n=f"{nxt:g}"))
        bar = QRectF(0, S(26), r.width(), S(6))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.08))
        p.drawRoundedRect(bar, S(3), S(3))
        frac = 1.0 if nxt is None else max(0.0, min(1.0, (hours - prev) / max(0.01, nxt - prev)))
        p.setBrush(ui.accent)
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), max(bar.height(), bar.width() * frac), bar.height()), S(3), S(3))
