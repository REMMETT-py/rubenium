"""2.4 music extras: the show/hide key (Right Shift), the badge size and place
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

# ================================================================ the show / hide key
KEY_CHOICES = [("rshift", "Right Shift", 0xA1), ("rctrl", "Right Ctrl", 0xA3), ("insert", "Insert", 0x2D),
               ("home", "Home", 0x24), ("ralt", "Right Alt", 0xA5), ("off", "Off", 0)]
# 4.6: the game mode key (any of these, but never the show / hide key)
GM_KEY_CHOICES = [("rshift", "Right Shift", 0xA1), ("rctrl", "Right Ctrl", 0xA3), ("ralt", "Right Alt", 0xA5),
                  ("insert", "Insert", 0x2D), ("home", "Home", 0x24), ("end", "End", 0x23), ("pgup", "Page Up", 0x21),
                  ("pgdn", "Page Down", 0x22), ("pause", "Pause", 0x13), ("scroll", "Scroll Lock", 0x91),
                  ("f9", "F9", 0x78), ("f10", "F10", 0x79), ("f11", "F11", 0x7A), ("f12", "F12", 0x7B)]


class TapKey(QObject):
    """Tap one key (default Right Shift) to show or hide Rubenium. A tap is a short press with no other key: holding
    the key (to run in a game, say) does nothing. It reads the key state, it does not hook the keyboard."""
    tapped = pyqtSignal()
    held = pyqtSignal()                 # 4.5: held for 3 seconds: restart Rubenium
    GAME_KEYS = (0x57, 0x41, 0x53, 0x44, 0x20, 0x25, 0x26, 0x27, 0x28, 0xA0, 0x01, 0x02)  # WASD space arrows LShift mouse (not LCtrl: AltGr sends it)

    def __init__(self, parent=None, hold_s: float = 3.0, choices=None) -> None:
        super().__init__(parent)
        self.hold_s = hold_s
        self.choices = choices or KEY_CHOICES
        self.vk = 0
        self._down_at = 0.0
        self._was = False
        self._fired = False
        self._t = QTimer(self)
        self._t.setInterval(30)
        self._t.timeout.connect(self._poll)

    def set_key(self, name: str) -> None:
        self.vk = next((vk for k, _n, vk in self.choices if k == name), 0)
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
            self._fired = False
        elif down and not self._fired and any(win.key_down(k) for k in self.GAME_KEYS):
            self._fired = True                          # held while playing (running, aiming...): never a restart
        elif down and not self._fired and now - self._down_at >= self.hold_s:
            self._fired = True
            self.held.emit()
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
    m.exec(QCursor.pos())


# ================================================================ tutorial (first start, can be replayed in Settings)
TUTORIAL = [
    ("Welcome to Rubenium!", "This little tour takes 30 seconds. Click Next, or Skip any time."),
    ("The ball", "The round R on your screen is Rubenium. Click it to open this menu; click the R at the top to fold it back. "
                 "Tap Right Shift to show or hide it."),
    ("Music", "The first tab shows what is playing in Spotify, YouTube Music and others. The button with the gem picks "
              "the badge size and where badges go."),
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
