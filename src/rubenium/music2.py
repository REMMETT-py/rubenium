"""2.4 music extras: the visualiser under the song, the show/hide key (Right Shift), the badge size and place
menu, and the first-run tutorial."""
import math
import time
from collections import deque

from PyQt6.QtCore import QObject, QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from . import win
from .core import S, sfx, TEXT, TEXT_DIM, alpha, font, mix, tr, ui
from .widgets import Button, Label, hbox, vbox

VIS_STYLES = [("bars", "Bars"), ("mirror", "Mirror"), ("wave", "Wave"), ("pulse", "Pulse"), ("dots", "Dots"),
              ("spark", "Sparks"), ("off", "Off")]


class Visualiser(QWidget):
    """A strip that moves with the music. It follows how loud the music is right now (from the Windows mixer),
    with a little movement of its own so it always looks alive."""
    N = 32

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self.setFixedHeight(S(34))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.levels = deque([0.0] * self.N, maxlen=self.N)
        self.bars = [0.0] * self.N
        self.sparks: list = []
        self._t = QTimer(self)
        self._t.setInterval(33)
        self._t.timeout.connect(self._step)

    def style(self) -> str:
        return str(self.ctx.cfg["visualiser"])

    def sync(self) -> None:
        on = self.style() != "off" and self.isVisible()
        self.setVisible(self.style() != "off")
        if on and not self._t.isActive():
            self._t.start()
        elif not on:
            self._t.stop()

    def showEvent(self, _e) -> None:
        if self.style() != "off":
            self._t.start()

    def hideEvent(self, _e) -> None:
        self._t.stop()

    def _level(self) -> float:
        from .media import Status
        if self.ctx.state.status is not Status.PLAYING:
            return 0.0
        env = float(getattr(self.ctx, "_env", 0.0) or 0.0)
        if env <= 0.001 and getattr(self.ctx.meter, "failed", False):        # no mixer: a gentle fake beat
            t = time.monotonic()
            env = 0.35 + 0.25 * abs(math.sin(t * 3.1)) * abs(math.sin(t * 1.3))
        return min(1.0, env)

    def _step(self) -> None:
        lvl = self._level()
        self.levels.append(lvl)
        t = time.monotonic()
        for i in range(self.N):                        # each bar: the loudness, shaped per band, plus a wobble
            band = 0.55 + 0.45 * math.sin(i * 0.55 + t * 2.3) * math.cos(i * 0.21 - t * 1.7)
            target = lvl * (0.35 + 0.65 * band) * (1.15 - 0.5 * abs(i - self.N / 2) / (self.N / 2))
            self.bars[i] += (target - self.bars[i]) * (0.55 if target > self.bars[i] else 0.18)
        if self.style() == "spark" and lvl > 0.45:
            import random
            self.sparks.append((random.uniform(0, 1), t, random.uniform(0.6, 1.0) * lvl))
        self.sparks = [s for s in self.sparks if t - s[1] < 0.9]
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(S(2), S(2), -S(2), -S(2))
        style = self.style()
        acc = QColor(ui.accent)
        acc2 = QColor(ui.accent2) if getattr(ui, "accent2", None) else mix(acc, QColor("#FFFFFF"), 0.35)
        n = self.N
        w = r.width() / n
        from .media import Status
        if self.ctx.state.status is not Status.PLAYING:
            p.setOpacity(0.35)                             # nothing playing: a quiet, still strip
        if style in ("bars", "mirror"):
            p.setPen(Qt.PenStyle.NoPen)
            for i, v in enumerate(self.bars):
                h = max(S(2), v * r.height() * (0.5 if style == "mirror" else 1.0))
                col = mix(acc, acc2, i / max(1, n - 1))
                g = QLinearGradient(0, r.bottom(), 0, r.top())
                g.setColorAt(0, alpha(col, 0.55))
                g.setColorAt(1, col)
                p.setBrush(g)
                x = r.left() + i * w + w * 0.18
                if style == "bars":
                    p.drawRoundedRect(QRectF(x, r.bottom() - h, w * 0.64, h), S(1.5), S(1.5))
                else:
                    p.drawRoundedRect(QRectF(x, r.center().y() - h, w * 0.64, h * 2), S(1.5), S(1.5))
        elif style == "wave":
            path = QPainterPath()
            vals = list(self.levels)
            t = time.monotonic()
            for i, v in enumerate(vals):
                x = r.left() + r.width() * i / (len(vals) - 1)
                y = r.center().y() - math.sin(i * 0.6 + t * 6) * v * r.height() * 0.45
                path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
            for wdt, a in ((S(5), 0.18), (S(2), 1.0)):
                pen = QPen(alpha(acc, a), wdt)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                p.setPen(pen)
                p.drawPath(path)
        elif style == "pulse":
            v = self.levels[-1] if self.levels else 0.0
            c = r.center()
            for k in range(3):
                rad = (S(8) + v * r.width() * 0.45) * (1 - k * 0.28)
                g = QRadialGradient(c, max(1.0, rad))
                g.setColorAt(0, alpha(acc, 0.45 - k * 0.12))
                g.setColorAt(1, alpha(acc, 0.0))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(g)
                p.drawEllipse(c, rad, min(rad, r.height() / 2 + S(4)))
            p.setPen(QPen(alpha(acc, 0.7), S(1.4)))
            p.drawLine(QPointF(r.left(), c.y()), QPointF(c.x() - S(10) - v * S(60), c.y()))
            p.drawLine(QPointF(c.x() + S(10) + v * S(60), c.y()), QPointF(r.right(), c.y()))
        elif style == "dots":
            p.setPen(Qt.PenStyle.NoPen)
            for i, v in enumerate(self.bars):
                col = mix(acc, acc2, i / max(1, n - 1))
                rows = int(1 + v * 5)
                for k in range(rows):
                    p.setBrush(alpha(col, 0.35 + 0.65 * (k + 1) / rows))
                    p.drawEllipse(QPointF(r.left() + i * w + w / 2, r.bottom() - S(3) - k * S(6)), S(2), S(2))
        elif style == "spark":
            now = time.monotonic()
            p.setPen(Qt.PenStyle.NoPen)
            for x, born, v in self.sparks:
                age = (now - born) / 0.9
                p.setBrush(alpha(mix(acc, acc2, x), 1 - age))
                p.drawEllipse(QPointF(r.left() + x * r.width(), r.bottom() - age * r.height() * (0.4 + v)), S(2.2), S(2.2))
            p.setPen(QPen(alpha(acc, 0.25 + 0.5 * (self.levels[-1] if self.levels else 0)), S(1.2)))
            p.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.right(), r.bottom()))


# ================================================================ the show / hide key
KEY_CHOICES = [("rshift", "Right Shift", 0xA1), ("rctrl", "Right Ctrl", 0xA3), ("insert", "Insert", 0x2D),
               ("home", "Home", 0x24), ("f8", "F8", 0x77), ("off", "Off", 0)]


class TapKey(QObject):
    """Tap one key (default Right Shift) to show or hide Rubenium. A tap is a short press with no other key: holding
    the key (to run in a game, say) does nothing. It reads the key state, it does not hook the keyboard."""
    tapped = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.vk = 0
        self._down_at = 0.0
        self._was = False
        self._t = QTimer(self)
        self._t.setInterval(30)
        self._t.timeout.connect(self._poll)

    def set_key(self, name: str) -> None:
        self.vk = next((vk for k, _n, vk in KEY_CHOICES if k == name), 0)
        self._was = False
        if self.vk and win.IS_WIN:
            self._t.start()
        else:
            self._t.stop()

    def _poll(self) -> None:
        down = win.key_down(self.vk)
        now = time.monotonic()
        if down and not self._was:
            self._down_at = now
        elif not down and self._was and now - self._down_at < 0.35:
            self.tapped.emit()
        self._was = down

    def stop(self) -> None:
        self._t.stop()


# ================================================================ badges on the music tab: size and place
BADGE_SIZES = [(70, "Small"), (100, "Normal"), (130, "Large"), (160, "Huge")]
BADGE_PLACES = [("above", "Above the title"), ("below", "Under the artist"), ("hidden", "Hidden")]


def badge_menu(ctx, on_change) -> None:
    from PyQt6.QtGui import QAction, QCursor
    from PyQt6.QtWidgets import QMenu
    m = QMenu()
    m.addSection(tr("Badge size"))
    for v, name in BADGE_SIZES:
        a = QAction(tr(name), m)
        a.setCheckable(True)
        a.setChecked(int(ctx.cfg["badge_size"]) == v)
        a.triggered.connect(lambda _c=False, v=v: (ctx.cfg.__setitem__("badge_size", v), on_change()))
        m.addAction(a)
    m.addSection(tr("Badge place"))
    for k, name in BADGE_PLACES:
        a = QAction(tr(name), m)
        a.setCheckable(True)
        a.setChecked(ctx.cfg["badge_pos"] == k)
        a.triggered.connect(lambda _c=False, k=k: (ctx.cfg.__setitem__("badge_pos", k), on_change()))
        m.addAction(a)
    m.addSection(tr("Visualiser"))
    for k, name in VIS_STYLES:
        a = QAction(tr(name), m)
        a.setCheckable(True)
        a.setChecked(ctx.cfg["visualiser"] == k)
        a.triggered.connect(lambda _c=False, k=k: (ctx.cfg.__setitem__("visualiser", k), on_change()))
        m.addAction(a)
    m.exec(QCursor.pos())


# ================================================================ tutorial (first start, can be replayed in Settings)
TUTORIAL = [
    ("Welcome to Rubenium!", "This little tour takes 30 seconds. Click Next, or Skip any time."),
    ("The ball", "The round R on your screen is Rubenium. Click it to open this menu; click the R at the top to fold it back. "
                 "Tap Right Shift to show or hide it."),
    ("Music", "The first tab shows what is playing in Spotify, YouTube Music and others. The button with the gem picks "
              "the badge size, where badges go and the visualiser style."),
    ("Coins and keys", "You earn coins and keys just by having Rubenium open. Spend them on cases, the shop and the "
                       "market, or win more in the mini games and the casino."),
    ("Games", "Beat Tap, Parking and Memory pay coins. Duel your friends, scratch a card every 12 hours and come "
              "back every day for the login reward."),
    ("Social", "Add friends, chat, trade and see who is top of the leaderboards."),
    ("All set!", "Settings has backups, the show/hide key and this tour again. Have fun!"),
]


class Tutorial(QWidget):
    """A card over the menu, one step at a time."""

    def __init__(self, ctx, on_done=None) -> None:
        host = ctx.window.body
        super().__init__(host)
        self.ctx, self.on_done = ctx, on_done
        self.step = 0
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        lay = vbox(self, 10, (22, 20, 22, 20))
        self.title = Label("", 16, bold=True, wrap_w=S(290))
        self.text = Label("", 12, TEXT_DIM, wrap_w=S(290))
        lay.addStretch(1)
        lay.addWidget(self.title)
        lay.addWidget(self.text)
        line = hbox(spacing=6)
        self.skip = Button(tr("Skip"), "ghost", 32)
        self.skip.clicked.connect(self.finish)
        self.next = Button(tr("Next"), "primary", 32)
        self.next.clicked.connect(self._next)
        line.addWidget(self.skip, 1)
        line.addWidget(self.next, 1)
        lay.addLayout(line)
        lay.addStretch(1)
        self._show_step()
        self.setGeometry(host.rect())
        self.show()
        self.raise_()

    def _show_step(self) -> None:
        title, text = TUTORIAL[self.step]
        self.title.set_text(tr(title))
        self.text.set_text(tr(text))
        last = self.step == len(TUTORIAL) - 1
        self.next.set_text(tr("Done") if last else tr("Next") + f"  {self.step + 1}/{len(TUTORIAL)}")
        self.skip.setVisible(not last)
        self.update()

    def _next(self) -> None:
        sfx.play("pick")
        if self.step >= len(TUTORIAL) - 1:
            return self.finish()
        self.step += 1
        self._show_step()

    def finish(self) -> None:
        self.ctx.cfg["tutorial_done"] = True
        self.hide()
        self.deleteLater()
        if self.on_done:
            self.on_done()

    def mousePressEvent(self, e) -> None:
        e.accept()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(4, 6, 8, 150))
        card = QRectF(self.rect()).adjusted(S(8), 0, -S(8), 0)
        h = S(220)
        card = QRectF(card.left(), card.center().y() - h / 2, card.width(), h)
        p.setPen(QPen(alpha(ui.accent, 0.6), S(1.4)))
        p.setBrush(QColor(12, 15, 16, 250))
        p.drawRoundedRect(card, S(16), S(16))
        dots = len(TUTORIAL)
        for k in range(dots):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ui.accent if k == self.step else alpha("#FFFFFF", 0.2))
            p.drawEllipse(QPointF(card.center().x() + (k - (dots - 1) / 2) * S(12), card.top() + S(16)), S(3), S(3))
