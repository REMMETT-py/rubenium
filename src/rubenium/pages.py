# -*- coding: utf-8 -*-
"""The eight pages of the card. Short labels, few words; anything the PC cannot do is replaced by a
short notice instead of a dead control."""
from __future__ import annotations

import bisect
import copy
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from PyQt6.QtCore import QEasingCurve, QPoint, QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QAbstractButton, QFileDialog, QGridLayout, QWidget

from . import engines, extras, win
from .core import (sfx, DANGER, BALL, BALL_SIZES, BD, GLOW, LOCKED_TABS, WARN, APP_NAME, BACKUP_DIR, CARD_W, CROSSHAIR, CROSSHAIR_DIR, DATA_DIR, DISPLAY_PROFILE, ACCENT_DEFAULT,
                   LOG_PATH, PAD, S, TEXT, TEXT_DIM, TEXT_FAINT, VERSION_NAME, alpha, font, lang, mix, tr, ui)
from .media import CMD_NEXT, CMD_PREV, CMD_REPEAT, CMD_SEEK, CMD_SHUFFLE, CMD_TOGGLE, Status, source_keywords
from .music2 import badge_menu
from .widgets import (ArtWidget, Button, Slider, Gauge, Glyph, IconButton, Label, Panel, ProgressBar, Segmented,
                      SliderRow, Sparkline, Swatches, Toggle, Tween, heading, hbox, notice, row, vbox)


def clock(ms: float) -> str:
    s = max(0, int(ms // 1000))
    return f"{s // 60}:{s % 60:02d}"


class Page(QWidget):
    key = ""
    fixed_height = 0

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        from .core import page_width
        self.W = page_width()                   # 4.1: wider in the online menu's halves

    def content_height(self) -> int:
        if self.fixed_height:
            return S(self.fixed_height)
        lay = self.layout()
        lay.activate()
        return lay.sizeHint().height()

    def on_show(self) -> None: ...
    def on_hide(self) -> None: ...
    def on_state(self, st) -> None: ...
    def on_art(self, pixmap) -> None: ...


# --------------------------------------------------------------------------- #
# Home: the music widget
# --------------------------------------------------------------------------- #
class Flair(QWidget):
    """Up to three of your badges. They fade in on the music tab where the music app's name fades out."""

    def __init__(self, ctx, parent) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.fade = 1.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._shine = QTimer(self)                  # rare colours shimmer: repaint only while they show
        self._shine.setInterval(40)
        self._shine.timeout.connect(self.update)
        self.fit()

    def _parts(self) -> list:
        """The badges on show (server items, e.g. "badge:star:gold")."""
        return self.ctx.econ.badges_worn()[:3]

    def _unit(self) -> float:
        return S(16) * max(50, min(200, int(self.ctx.cfg["badge_size"]))) / 100

    def fit(self) -> None:
        n = len(self._parts())
        u = self._unit()
        self.setFixedSize(max(1, int(n * (u + S(3)))), int(u + S(2)))
        self.setVisible(bool(n) and self.ctx.cfg["badge_pos"] != "hidden")
        from .badges import item_animated
        moving = self.isVisible() and self.fade > 0.01 and any(item_animated(i) for i in self._parts())
        if moving and not self._shine.isActive():
            self._shine.start()
        elif not moving:
            self._shine.stop()

    def paintEvent(self, _e) -> None:
        if self.fade <= 0.01:
            return
        from .badges import paint_item
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self.fade)
        now = time.monotonic()
        u = self._unit()
        for k, item in enumerate(self._parts()):
            paint_item(p, item, QRectF(k * (u + S(3)) + S(1), S(1), u, u), now)


class HoldButton(QAbstractButton):
    """A button that is hard to press by accident: click, click again, then hold until it fills up."""
    confirmed = pyqtSignal()

    def __init__(self, text: str, height: int = 34) -> None:
        super().__init__()
        self._text = text
        self.stage = 0                              # 0 idle, 1 clicked once, 2 hold to confirm
        self.setFixedHeight(S(height))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._hover = Tween(self, on_change=self.update)
        self.charge = Tween(self, 0.0, self.update, QEasingCurve.Type.Linear)
        self.charge.finished.connect(self._charged)
        self._idle = QTimer(self)
        self._idle.setSingleShot(True)
        self._idle.timeout.connect(self._back)

    def _back(self) -> None:
        if not self.isDown():
            self.stage = 0
            self.charge.jump(0.0)
            self.update()

    def enterEvent(self, e) -> None:
        self._hover.to(1.0, 140)

    def leaveEvent(self, e) -> None:
        self._hover.to(0.0, 220)

    def mousePressEvent(self, e) -> None:
        e.accept()
        if e.button() != Qt.MouseButton.LeftButton:
            return
        self.setDown(True)
        if self.stage == 2:
            self.charge.jump(0.0)
            self.charge.to(1.0, 1600)

    def mouseReleaseEvent(self, e) -> None:
        e.accept()
        if not self.isDown():
            return
        self.setDown(False)
        if self.stage < 2:
            self.stage += 1
            sfx.play("pick")
        elif self.charge.level < 0.999:
            self.charge.to(0.0, 180)                # let go too early: nothing happens
        self._idle.start(6000)
        self.update()

    def _charged(self) -> None:
        if self.stage == 2 and self.isDown() and self.charge.target >= 1.0 and self.charge.level >= 0.999:
            self.setDown(False)
            self.stage = 0
            self.charge.jump(0.0)
            self.update()
            self.confirmed.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        rad = S(10)
        h = self._hover.level
        p.setPen(QPen(alpha(DANGER, 0.45 + 0.25 * h + 0.3 * (self.stage > 0)), 1.2))
        p.setBrush(alpha(DANGER, 0.08 + 0.06 * h + 0.05 * self.stage))
        p.drawRoundedRect(r, rad, rad)
        c = max(0.0, min(1.0, self.charge.level))
        if c > 0.0:
            clip = QPainterPath()
            clip.addRoundedRect(r, rad, rad)
            p.save()
            p.setClipPath(clip)
            p.fillRect(QRectF(r.left(), r.top(), r.width() * c, r.height()), alpha(DANGER, 0.55))
            p.restore()
        text = (self._text, tr("Click again"), tr("Hold to reset"))[self.stage]
        p.setPen(QColor(TEXT))
        p.setFont(font(12, QFont.Weight.DemiBold))
        p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), text)


class HomePage(Page):
    key = "home"
    ART, ART_COMPACT, CTRL_H = 88, 64, 38          # 4.1: Compact Music Mode: smaller cover, no button row

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self._opt_until, self._opt_playing = 0.0, False
        lay = vbox(self, 8)
        body = hbox(spacing=12)
        self.art = ArtWidget(88)
        info = vbox(spacing=1)
        top = hbox(spacing=6)
        self.title = Label("", 15, bold=True, shrink=10.5)         # long names get smaller instead of "…"
        self.title.setFixedHeight(S(22))
        self.chip = Button("", "quiet", 20)
        self.chip.setToolTip(tr("Click to choose the music app"))
        self.art.setToolTip(tr("Open the music app"))
        self.art.clicked.connect(ctx.open_player)
        top.addWidget(self.title, 1)
        top.addWidget(self.chip)
        self.artist = Label("", 12, TEXT_DIM)
        self.artist.setFixedHeight(S(18))
        controls = hbox(spacing=4)
        self.b_shuffle = IconButton("shuffle", 28, tip=tr("Shuffle"))
        self.b_prev = IconButton("prev", 30, tip=tr("Previous"))
        self.b_play = IconButton("play", 38, primary=True)
        self.b_next = IconButton("next", 30, tip=tr("Next"))
        self.b_repeat = IconButton("repeat", 28, tip=tr("Repeat"))
        for b in (self.b_shuffle, self.b_prev, self.b_play, self.b_next, self.b_repeat):
            controls.addWidget(b)
        controls.addStretch(1)
        self.b_vol = IconButton("volume", 24, tip=tr("Mute"))
        self.vol = Slider(0, 100, 100, 1)
        self.vol.setFixedWidth(S(62))
        self.vol.setMinimumWidth(S(40))
        self.vol.setToolTip(tr("Music volume"))
        controls.addWidget(self.b_vol)
        controls.addWidget(self.vol)
        self.b_vol.hide()
        self.vol.hide()
        self.flair = Flair(ctx, None)
        self.info = info
        info.addWidget(self.flair)
        info.addLayout(top)
        info.addWidget(self.artist)
        self.b_look = IconButton("gem", 24, tip=tr("Badge size and place"))
        self.b_look.clicked.connect(lambda: badge_menu(ctx, self._look_changed))
        controls.addWidget(self.b_look)
        info.addStretch(1)
        self.ctrl_box = QWidget()                     # 4.1: Compact Music Mode folds this row away smoothly
        self.ctrl_box.setLayout(controls)
        self.ctrl_box.setFixedHeight(S(self.CTRL_H))
        info.addWidget(self.ctrl_box)
        body.addWidget(self.art, 0, Qt.AlignmentFlag.AlignTop)
        body.addLayout(info, 1)
        prog = hbox(spacing=8)
        self.t_pos = Label("0:00", 10, TEXT_FAINT)
        self.t_dur = Label("0:00", 10, TEXT_FAINT, align=Qt.AlignmentFlag.AlignRight)
        self.t_pos.setFixedWidth(S(30))
        self.t_dur.setFixedWidth(S(30))
        self.progress = ProgressBar()
        prog.addWidget(self.t_pos)
        prog.addWidget(self.progress, 1)
        prog.addWidget(self.t_dur)
        lay.addLayout(body)
        lay.addLayout(prog)

        m = ctx.media
        self.b_prev.clicked.connect(lambda: m.send(CMD_PREV))
        self.b_next.clicked.connect(lambda: m.send(CMD_NEXT))
        self.b_shuffle.clicked.connect(lambda: m.send(CMD_SHUFFLE))
        self.b_repeat.clicked.connect(lambda: m.send(CMD_REPEAT))
        self.b_play.clicked.connect(self._toggle)
        self.chip.clicked.connect(self._cycle_source)
        self.progress.seek.connect(self._seek)
        self.vol.changed.connect(self._vol_set)
        self.b_vol.clicked.connect(self._vol_mute)
        self._muted = False
        self._vol_timer = QTimer(self)
        self._vol_timer.setInterval(1000)
        self._vol_timer.timeout.connect(self._vol_poll)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._tick)
        self.squash = Tween(self, 0.0, self._squash_step, QEasingCurve.Type.InOutCubic)
        self.on_state(ctx.state)
        self.art.set_pixmap(ctx.art_pixmap)

    def on_show(self) -> None:
        self._timer.start()
        self._tick()
        self._vol_timer.start()
        self._vol_poll()

    # music volume: the app's own slider in the Windows volume mixer, kept in sync both ways
    def _vol_match(self):
        st = self.ctx.state
        return win.AppVolume.matcher(st.source_id, source_keywords(st.source_id)) if st.source_id else None

    def _vol_poll(self) -> None:
        if self.vol._drag or getattr(self, "_compact", False):
            return
        res = self.ctx.appvol.get(self._vol_match()) if self.ctx.state.source_id else None
        show = res is not None
        self._vol_ok = show
        if show != self.b_vol.isVisible():
            self.vol.setVisible(show)
            self.b_vol.setVisible(show)
        if show:
            level, muted = res
            if abs(self.vol.value() - level * 100) >= 1:
                self.vol.set_value(round(level * 100))
            self._muted = muted
            self.b_vol.set_kind("muted" if muted else "volume")
            self.b_vol.setToolTip(tr("Unmute") if muted else tr("Mute"))

    def _vol_set(self, v: float) -> None:
        match = self._vol_match()
        if self._muted and v > 0:
            self.ctx.appvol.set_mute(match, False)
            self._muted = False
            self.b_vol.set_kind("volume")
        self.ctx.appvol.set(match, v / 100)

    def _vol_mute(self) -> None:
        if self.ctx.appvol.set_mute(self._vol_match(), not self._muted):
            self._muted = not self._muted
            self.b_vol.set_kind("muted" if self._muted else "volume")

    def set_compact(self, level: float) -> None:
        """The menu bar is hiding: the music app name fades with it. 4.0, Compact Music Mode: while you play a game
        (or the menu is tucked away), only the track, its time and a bigger title stay."""
        self.chip.fade = max(0.0, min(1.0, (level - 0.2) / 0.8))
        self.chip.update()
        self._place_flair()
        win = self.ctx.window
        # 4.3: compact only while you are away from Rubenium (in a game, the mouse elsewhere). As soon as the menu bar
        # comes back (mouse over it, or it has the focus) everything unfolds again. The setting only decides whether
        # it folds at all.
        if self.ctx.cfg["autohide"]:
            away = level < 0.5
        else:
            away = getattr(win, "game_state", 0) > 0 and not getattr(win, "_in_since", 0.0) and not win.isActiveWindow()
        want = bool(self.ctx.cfg["compact_music"]) and away
        if want != getattr(self, "_compact", False):
            self._compact = want
            self._apply_compact()

    def _apply_compact(self) -> None:
        """4.1: the card folds smoothly, the way the menu bar does: the button row closes up, the cover gets a little
        smaller, the title and artist grow, and the whole menu gets shorter with it (no gap is left)."""
        on = getattr(self, "_compact", False)
        if not on:                                  # 4.3: unfolding: the buttons are back at once and fade in
            st = self.ctx.state
            for b in (self.b_prev, self.b_play, self.b_next, self.b_look):
                b.show()
            self.b_shuffle.setVisible(st.shuffle is not None)
            self.b_repeat.setVisible(st.repeat is not None)
            QTimer.singleShot(0, self._vol_poll)
        self.on_state(self.ctx.state)               # the hint never mentions a button that is not there
        if self.isVisible() and self.ctx.window.expanded:
            self.squash.to(1.0 if on else 0.0, 380)
        else:
            self.squash.jump(1.0 if on else 0.0)

    def _squash_step(self) -> None:
        k = max(0.0, min(1.0, self.squash.level))
        self.ctrl_box.setFixedHeight(int(round(S(self.CTRL_H) * (1 - k))))
        self.ctrl_box.setVisible(k < 0.999)
        self._ctrl_fade(max(0.0, min(1.0, 1.0 - k / 0.55)))      # 4.3: gone by half way, back over the last half
        side = S(self.ART + (self.ART_COMPACT - self.ART) * k)
        self.art.setFixedSize(side, side)
        self.title.set_size(round((15 + 4 * k) * 2) / 2)
        self.title.setFixedHeight(S(22 + 6 * k))
        self.artist.set_size(12 + (1 if k > 0.5 else 0))
        self._refit()

    def _ctrl_fade(self, o: float) -> None:
        """4.3: the play, skip and other buttons fade with the fold (painted fade: a graphics effect would not draw
        on the see-through menu)."""
        for b in (self.b_shuffle, self.b_prev, self.b_play, self.b_next, self.b_repeat, self.b_vol, self.b_look):
            if abs(b.fade - o) > 0.004:
                b.fade = o
                b.update()
        self.vol.setVisible(bool(getattr(self, "_vol_ok", False)) and o > 0.6)

    def _refit(self) -> None:
        """Tell the menu the page is shorter (or taller) now: the card follows it frame by frame."""
        win = self.ctx.window
        entry = win.pages.get(self.key) if hasattr(win, "pages") else None
        if entry is None or entry[1] is not self:
            return
        lay = self.layout()
        lay.invalidate()
        h = self.content_height()
        if h == entry[2]:
            return
        win.pages[self.key] = (entry[0], self, h)
        entry[0].set_content_height(h)
        if win.current == self.key and win.expanded and not win.morph.busy and not win.slide.busy:
            win.pageh.jump(win._card_h(self.key))
            win._layout_body()
            win.update()

    def _place_flair(self) -> None:
        """The badges sit on their own line above the song title (or under the artist): they never cover it."""
        want = 2 if self.ctx.cfg["badge_pos"] == "below" else 0
        if self.info.indexOf(self.flair) != want:
            self.info.removeWidget(self.flair)
            self.info.insertWidget(want, self.flair)
        self.flair.fade = 1.0
        self.flair.fit()
        self.flair.update()

    def _look_changed(self) -> None:
        self.ctx.cfg.save()
        self._place_flair()
        self.ctx.reload_page()

    def on_hide(self) -> None:
        self._timer.stop()
        self._vol_timer.stop()

    def on_art(self, pixmap) -> None:
        self.art.set_pixmap(pixmap)

    def _toggle(self) -> None:
        if self.ctx.state.status is Status.NOT_RUNNING:          # 3.2: no music app open: yours opens (asked once)
            from .music3 import play_with_nothing_open
            return play_with_nothing_open(self.ctx)
        playing_now = self.ctx.state.status is Status.PLAYING
        self._opt_playing = not playing_now           # optimistic flip, corrected by the next real state
        self._opt_until = time.monotonic() + 0.8
        self.b_play.set_kind("pause" if self._opt_playing else "play")
        self.ctx.media.send(CMD_TOGGLE)

    def _seek(self, fraction: float) -> None:
        st = self.ctx.state
        if st.can_seek:
            self.ctx.seek(fraction * st.duration_ms)

    def _cycle_source(self) -> None:
        st = self.ctx.state
        ids = [""] + [sid for sid, _ in st.sources]
        cur = self.ctx.cfg["source"]
        nxt = ids[(ids.index(cur) + 1) % len(ids)] if cur in ids else ""
        self.ctx.cfg["source"] = nxt
        self.ctx.media.set_preferred(nxt)
        name = dict(st.sources).get(nxt, "")
        self.ctx.toast(tr("Music app: {name}", name=name) if nxt else tr("Music app: automatic"))

    def _tick(self) -> None:
        st = self.ctx.state
        if st.has_track and st.duration_ms > 0:
            pos = self.ctx.position_ms()
            self.progress.set_fraction(pos / st.duration_ms)
            self.t_pos.set_text(clock(pos))
        else:
            self.progress.set_fraction(0.0)
            self.t_pos.set_text("0:00")

    def on_state(self, st) -> None:
        usable = st.status in (Status.PLAYING, Status.PAUSED, Status.STOPPED, Status.NOT_RUNNING)
        self.b_play.setEnabled(usable)
        self.b_prev.setEnabled(st.has_track and st.can_prev)
        self.b_next.setEnabled(st.has_track and st.can_next)
        if st.has_track:
            title, artist = st.title, st.artist or tr("Unknown artist")
        elif st.status is Status.UNAVAILABLE:
            title, artist = tr("Setup needed"), st.message
        elif st.status is Status.ERROR:
            title, artist = tr("Music app not responding"), tr("Trying again…")
        elif st.status is Status.STOPPED:
            title, artist = tr("Nothing is playing"), tr("Press play in your music app")
        else:
            from .music3 import app_name
            mine = app_name(self.ctx.cfg["music_app"])
            if getattr(self, "_compact", False):     # 4.1: no play button in Compact Music Mode
                title, artist = tr("No music app is open"), (mine or "")
            else:
                title, artist = tr("No music app is open"), (tr("Press play to open {app}", app=mine) if mine else
                                                             tr("Press play to open your music app"))
        self.title.set_text(title)
        self.artist.set_text(artist)
        self.setToolTip(st.message if st.status is Status.UNAVAILABLE else "")

        pinned = bool(self.ctx.cfg["source"])
        chip = st.source or (tr("Auto") if not pinned else "")
        self.chip.setVisible(bool(st.sources) or pinned)
        text = ("● " if pinned else "") + (chip or tr("Auto"))
        self.chip.set_text(text)
        self.chip.setFixedWidth(QFontMetrics(font(12, QFont.Weight.DemiBold)).horizontalAdvance(text) + S(16))

        self.b_shuffle.setVisible(st.shuffle is not None)        # never a dead control (the folded row hides itself)
        self.b_repeat.setVisible(st.repeat is not None)
        self.b_shuffle.set_active(bool(st.shuffle))
        self.b_repeat.set_active(bool(st.repeat))
        self.b_repeat.set_kind("repeat1" if st.repeat == 1 else "repeat")
        if st.source_id != getattr(self, "_vol_src", None):          # another app: look for its volume now
            self._vol_src = st.source_id
            if self._vol_timer.isActive():
                QTimer.singleShot(0, self._vol_poll)

        playing = st.status is Status.PLAYING
        shown = self._opt_playing if time.monotonic() < self._opt_until else playing
        self.b_play.set_kind("pause" if shown else "play")
        self.progress.seekable = st.can_seek
        self.t_dur.set_text(clock(st.duration_ms) if st.has_track else "0:00")
        self._tick()


# --------------------------------------------------------------------------- #
# Lyrics
# --------------------------------------------------------------------------- #
class LyricsView(QWidget):
    def __init__(self, page: "LyricsPage") -> None:
        super().__init__(page)
        self.page = page
        self.kind = "idle"
        self.lines: list = []
        self._tops: list = []
        self._heights: list = []
        self._idx = -1
        self._scroll = Tween(self, 0.0, self.update)
        self._manual = 0.0
        self._font = font(15, QFont.Weight.DemiBold)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def set_content(self, kind: str, lines: list) -> None:
        self.kind, self.lines, self._idx, self._manual = kind, lines, -1, 0.0
        self._layout()
        self._scroll.jump(0.0)
        self.update()

    def _text(self, i: int) -> str:
        item = self.lines[i]
        return (item[1] if isinstance(item, (tuple, list)) else item) or "♪"

    def _layout(self) -> None:
        fm = QFontMetrics(self._font)
        w = max(50, self.width() - S(8))
        self._tops, self._heights, y = [], [], 0
        for i in range(len(self.lines)):
            h = fm.boundingRect(0, 0, w, 10000, int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignHCenter),
                                self._text(i)).height() + S(10)
            self._tops.append(y)
            self._heights.append(h)
            y += h
        self._total = y

    def resizeEvent(self, _e) -> None:
        self._layout()

    def set_position(self, ms: float) -> None:
        if self.kind != "synced" or not self.lines:
            return
        i = bisect.bisect_right([ln[0] for ln in self.lines], ms + 150) - 1
        if i != self._idx:
            self._idx = i
            target = (self._tops[i] + self._heights[i] / 2) if i >= 0 else 0.0
            self._scroll.to(target, 420)

    def wheelEvent(self, e) -> None:
        if self.kind == "plain":
            top = max(0.0, self._total - self.height() + S(20))
            self._manual = max(0.0, min(top, self._manual - e.angleDelta().y() / 120 * S(60)))
            self._scroll.to(self._manual, 260)
        e.accept()

    def mousePressEvent(self, e) -> None:
        if self.kind != "synced" or not self.page.ctx.state.can_seek:
            return
        y = e.position().y() - self.height() / 2 + self._scroll.level
        i = bisect.bisect_right(self._tops, y) - 1
        if 0 <= i < len(self.lines):
            self.page.ctx.seek(self.lines[i][0])

    def paintEvent(self, _e) -> None:
        if self.kind not in ("synced", "plain") or not self.lines:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setFont(self._font)
        h, w = self.height(), self.width()
        base = h / 2 - self._scroll.level if self.kind == "synced" else S(6) - self._scroll.level
        first = max(0, bisect.bisect_right(self._tops, -base) - 1)
        for i in range(first, len(self.lines)):
            y = base + self._tops[i]
            if y > h:
                break
            mid = y + self._heights[i] / 2
            edge = min(1.0, max(0.0, min(mid, h - mid) / S(46)))
            if self.kind == "synced":
                d = abs(i - self._idx)
                col = QColor(TEXT) if d == 0 else alpha(TEXT_DIM, max(0.25, 0.75 - 0.14 * d))
                if i < self._idx:
                    col = alpha(TEXT_DIM, 0.38)
            else:
                col = alpha(TEXT, 0.86)
            col.setAlphaF(col.alphaF() * edge)
            p.setPen(col)
            p.drawText(QRectF(S(4), y, w - S(8), self._heights[i]),
                       int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap), self._text(i))


class LyricsPage(Page):
    key = "lyrics"
    fixed_height = 262

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self._key = ""
        self._track = ""
        self.view = LyricsView(self)
        self.empty = QWidget(self)
        col = vbox(self.empty, 8)
        col.addStretch(1)
        self.glyph = Glyph("note", 52)
        col.addWidget(self.glyph, 0, Qt.AlignmentFlag.AlignHCenter)
        self.msg = Label("", 12, TEXT_DIM, align=Qt.AlignmentFlag.AlignHCenter)
        col.addWidget(self.msg)
        self.retry = Button(tr("Try again"), "ghost", 28)
        self.retry.setFixedWidth(S(120))
        col.addWidget(self.retry, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addStretch(1)
        self.retry.clicked.connect(lambda: self._request(force=True))
        ctx.lyrics.result.connect(self._on_result)
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(lambda: self.view.set_position(self.ctx.position_ms()))
        self.on_state(ctx.state)

    def resizeEvent(self, _e) -> None:
        self.view.setGeometry(self.rect())
        self.empty.setGeometry(self.rect())

    def _show_empty(self, text: str, retry: bool = False) -> None:
        self.msg.set_text(text)
        self.retry.setVisible(retry)
        self.empty.show()
        self.view.hide()

    def on_show(self) -> None:
        self._timer.start()
        self._request()

    def on_hide(self) -> None:
        self._timer.stop()

    def on_state(self, st) -> None:
        track = st.art_key
        if track != self._track:
            self._track = track
            self._key = ""
            self.view.set_content("idle", [])
            if not st.has_track:
                self._show_empty(tr("Play a song to see its lyrics"))
            elif self.isVisible():
                self._request()

    def _request(self, force: bool = False) -> None:
        st = self.ctx.state
        if not st.has_track or (self._key and not force):
            return
        self._show_empty(tr("Looking for lyrics…"))
        self._key = self.ctx.lyrics.request(st.title, st.artist, st.album, st.duration_ms)

    def _on_result(self, key: str, kind: str, payload) -> None:
        if key != self._key:
            return
        if kind in ("synced", "plain") and payload:
            self.view.set_content(kind, payload)
            self.empty.hide()
            self.view.show()
            self.view.set_position(self.ctx.position_ms())
        elif kind == "offline":
            self._key = ""
            self._show_empty(tr("No internet connection"), retry=True)
        else:
            self._show_empty(tr("No lyrics for this song"))


# --------------------------------------------------------------------------- #
# Crosshair designer
# --------------------------------------------------------------------------- #
class CrosshairPreview(QWidget):
    def __init__(self, cfg) -> None:
        super().__init__()
        self.cfg = cfg
        self.setFixedHeight(S(112))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        from PyQt6.QtGui import QLinearGradient, QPainterPath
        clip = QPainterPath()
        clip.addRoundedRect(r, S(10), S(10))
        p.setClipPath(clip)
        half = r.width() / 2
        g = QLinearGradient(0, 0, 0, r.height())           # sky / ground so any colour can be judged
        g.setColorAt(0, QColor("#5B7C99"))
        g.setColorAt(0.5, QColor("#9DB1BC"))
        g.setColorAt(0.5001, QColor("#5C5A4E"))
        g.setColorAt(1, QColor("#2C2B26"))
        p.fillRect(QRectF(0, 0, half, r.height()), g)
        p.fillRect(QRectF(half, 0, half, r.height()), QColor("#0D1112"))
        c = self.cfg["crosshair"]
        if c.get("style") == "image":                       # 4.0: a big picture is shown smaller here, never cut
            c = dict(c, image_px=min(int(c.get("image_px", 48)), int(self.height() - S(16))))
        ext = engines.crosshair_extent(c)
        k = max(1, min(4, int((self.height() / 2 - 6) // max(1, ext))))
        for cx in (half / 2, half * 1.5):
            p.save()
            engines.paint_crosshair(p, c, round(cx), round(r.height() / 2), k)
            p.restore()
        p.setClipping(False)
        p.setPen(QPen(alpha("#FFFFFF", 0.08), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, S(10), S(10))
        p.setPen(alpha("#FFFFFF", 0.55))
        p.setFont(font(9.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(S(8), S(5), 80, S(14)), int(Qt.AlignmentFlag.AlignLeft), f"×{k}")


def clean_crosshair(data) -> dict:
    """A saved crosshair made safe for this version (unknown keys dropped, old styles replaced)."""
    if not isinstance(data, dict):
        return dict(CROSSHAIR)
    out = {**CROSSHAIR, **{k: v for k, v in data.items() if k in CROSSHAIR and isinstance(v, type(CROSSHAIR[k]))}}
    if out["style"] not in ("cross", "tee", "dot", "circle", "image"):
        out["style"] = "cross"
    if out["style"] == "image" and engines.crosshair_image(out.get("image", "")) is None:
        out["style"] = "cross"                   # the picture is gone (or this is someone else's code)
    out["image_px"] = max(8, min(256, int(out.get("image_px") or 48)))
    if not QColor(out["color"]).isValid():
        out["color"] = CROSSHAIR["color"]
    out["size"] = 100
    return out


SHAPE_COMPARE = ("style", "color", "opacity", "length", "thickness", "gap", "dot", "dot_size", "outline",
                 "outline_w", "radius", "off_x", "off_y")


class SlotTile(QAbstractButton):
    """One of the six save slots, drawn with the crosshair it holds."""

    def __init__(self, number: int, data) -> None:
        super().__init__()
        self.number = number
        self.data = clean_crosshair(data) if isinstance(data, dict) else None
        self.selected = False
        self.modified = False
        self.setFixedHeight(S(52))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip(tr("Slot {n}", n=number))
        self._hover = Tween(self, on_change=self.update)

    def enterEvent(self, e) -> None:
        self._hover.to(1.0, 140)

    def leaveEvent(self, e) -> None:
        self._hover.to(0.0, 220)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        h = self._hover.level
        edge = ui.accent if self.selected else alpha("#FFFFFF", 0.10 + 0.18 * h)
        p.setPen(QPen(edge, 1.3 if self.selected else 1.0))
        p.setBrush(QColor("#0D1112") if self.data else alpha("#FFFFFF", 0.03 + 0.03 * h))
        p.drawRoundedRect(r, S(9), S(9))
        if self.data:
            p.save()
            p.setClipRect(r.adjusted(2, 2, -2, -2))
            engines.paint_crosshair(p, self.data, self.width() // 2, self.height() // 2, 1)
            p.restore()
        else:
            pen = QPen(alpha(TEXT_DIM, 0.45 + 0.3 * h), 1.6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            c = r.center()
            p.drawLine(QPointF(c.x() - S(5), c.y()), QPointF(c.x() + S(5), c.y()))
            p.drawLine(QPointF(c.x(), c.y() - S(5)), QPointF(c.x(), c.y() + S(5)))
        p.setPen(alpha(TEXT, 0.55))
        p.setFont(font(9, QFont.Weight.Bold))
        p.drawText(QRectF(r.left() + S(6), r.top() + S(3), S(14), S(12)), int(Qt.AlignmentFlag.AlignLeft), str(self.number))
        if self.selected and self.modified:                 # unsaved changes
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(WARN))
            p.drawEllipse(QPointF(r.right() - S(7), r.top() + S(7)), S(2.5), S(2.5))


XH_COLORS = ["#FFFFFF", "#00FF66", "#00E5FF", "#FFE600", "#FF3B3B", "#FF4DD2", "#FF8A00", "#7C4DFF"]


STYLES = ["cross", "tee", "dot", "circle", "image"]
XH_IMAGE_MAX_BYTES = 4 * 1024 * 1024          # 4.0: your own crosshair picture: 4 MB file at most,
XH_IMAGE_MAX_SIDE = 4096                      # 4096 px a side at most, saved at 256 px (sharp at every size used)


class CrosshairPage(Page):
    key = "crosshair"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        cfg = ctx.cfg
        c = cfg["crosshair"]
        lay = vbox(self, 7)
        self.preview = CrosshairPreview(cfg)
        lay.addWidget(self.preview)
        self.t_on = Toggle(cfg["crosshair_on"])
        self.t_on.toggled_by_user.connect(lambda on: ctx.set_crosshair(on))
        lay.addWidget(row(tr("Show crosshair"), self.t_on))

        lay.addWidget(heading(tr("My crosshairs")))
        slots = hbox(spacing=5)
        self.tiles = []
        saved = cfg["crosshair_presets"]
        for n in range(1, 7):
            tile = SlotTile(n, saved.get(str(n)))
            tile.clicked.connect(lambda _=False, t=tile: self._slot_click(t))
            slots.addWidget(tile, 1)
            self.tiles.append(tile)
        lay.addLayout(slots)
        acts = hbox(spacing=8)
        self.b_save = Button("", "primary", 30)
        self.b_clear = Button(tr("Clear slot"), "ghost", 30)
        self.b_save.clicked.connect(self._slot_save)
        self.b_clear.clicked.connect(self._slot_clear)
        acts.addWidget(self.b_save, 2)
        acts.addWidget(self.b_clear, 1)
        lay.addLayout(acts)

        lay.addWidget(heading(tr("Style")))
        self.style = Segmented([tr("Cross"), tr("T"), tr("Dot"), tr("Circle"), tr("Image")],
                               STYLES.index(c["style"]) if c["style"] in STYLES else 0)
        self.style.changed.connect(self._style)
        lay.addWidget(self.style)
        if c["style"] == "image":                           # 4.0: your own picture
            self._image_part(lay, c)
        self.sw = Swatches(XH_COLORS, c["color"])
        self.sw.picked.connect(lambda col: self._set("color", col))
        lay.addWidget(self.sw)
        hue = QColor(c["color"]).hsvHue()
        self.hue = SliderRow(tr("Other colour"), 0, 359, hue if hue >= 0 else 0, 1, fmt=lambda v: f"{int(v)}°",
                             marks=[0, 60, 120, 180, 240, 300])
        self.hue.slider.rainbow = True
        self.hue.changed.connect(self._hue)
        lay.addWidget(self.hue)
        self._colour_mode()

        lay.addWidget(heading(tr("Shape")))
        self.rows: dict = {}
        px = lambda v: f"{int(v)} px"  # noqa: E731
        for key, label, lo, hi, fmt, marks in (
                ("length", tr("Length"), 0, 40, px, [0, 5, 10, 20, 30, 40]),
                ("gap", tr("Gap"), 0, 30, px, [0, 3, 5, 10, 20, 30]),
                ("thickness", tr("Thickness"), 1, 10, px, [1, 2, 4, 6, 8, 10]),
                ("radius", tr("Circle size"), 2, 60, px, [5, 10, 20, 30, 40, 60]),
                ("dot_size", tr("Dot size"), 1, 12, px, [1, 2, 4, 6, 8, 12]),
                ("outline_w", tr("Outline width"), 1, 4, px, [1, 2, 3, 4]),
                ("opacity", tr("Opacity"), 10, 100, lambda v: f"{int(v)}%", [25, 50, 75, 100])):
            r = SliderRow(label, lo, hi, c[key], 1, CROSSHAIR[key], fmt, marks=marks)
            r.changed.connect(lambda v, k=key: self._set(k, int(v)))
            self.rows[key] = r
            lay.addWidget(r)
        two = hbox(spacing=10)
        self.t_dot, self.t_out = Toggle(c["dot"]), Toggle(c["outline"])
        self.t_dot.toggled_by_user.connect(lambda on: self._set("dot", on))
        self.t_out.toggled_by_user.connect(lambda on: self._set("outline", on))
        two.addWidget(row(tr("Centre dot"), self.t_dot), 1)
        two.addWidget(row(tr("Outline"), self.t_out), 1)
        lay.addLayout(two)

        lay.addWidget(heading(tr("Position")))
        for key, label in (("off_x", tr("Left / right")), ("off_y", tr("Up / down"))):
            r = SliderRow(label, -60, 60, c[key], 1, 0, px, marks=[-40, -20, 0, 20, 40])
            r.changed.connect(lambda v, k=key: self._set(k, int(v)))
            self.rows[key] = r
            lay.addWidget(r)
        mons = win.monitors() or QGuiApplication.screens()
        if len(mons) > 1:
            seg = Segmented([tr("Screen {n}", n=i + 1) for i in range(min(4, len(mons)))], min(c["monitor"], 3))
            seg.changed.connect(lambda i: self._set("monitor", i))
            lay.addWidget(seg)

        codes = hbox(spacing=8)
        b_copy, b_paste = Button(tr("Copy code"), icon="copy"), Button(tr("Paste code"))
        b_copy.clicked.connect(self._copy_code)
        b_paste.clicked.connect(self._paste_code)
        codes.addWidget(b_copy, 1)
        codes.addWidget(b_paste, 1)
        lay.addLayout(codes)
        lay.addSpacing(S(4))
        b_reset = Button(tr("Reset crosshair"), "danger", 34)
        b_reset.clicked.connect(self._reset)
        lay.addWidget(b_reset)
        self._sync()

    def on_show(self) -> None:
        self.t_on.set_checked(self.ctx.cfg["crosshair_on"])

    # -- 4.0: a picture of your own as the crosshair
    def _image_part(self, lay, c: dict) -> None:
        has = engines.crosshair_image(c.get("image", "")) is not None
        line = hbox(spacing=6)
        imp = Button(tr("Change image") if has else tr("Import an image"), "primary", 30, icon="folder")
        imp.clicked.connect(self._import_image)
        line.addWidget(imp, 2)
        back = Button(tr("Default crosshair"), "ghost", 30)
        back.clicked.connect(self._default_crosshair)
        line.addWidget(back, 1)
        lay.addLayout(line)
        size = SliderRow(tr("Image size"), 8, 256, int(c.get("image_px", 48)), 2, 48, lambda v: f"{int(v)} px",
                         marks=[16, 32, 64, 128, 256])
        size.changed.connect(lambda v: self._set("image_px", int(v)))
        size.setEnabled(has)
        lay.addWidget(size)
        lay.addWidget(Label(tr("PNG (best with a see-through background), JPG, BMP or WEBP, 4 MB at most. Move it with "
                               "Position below; Opacity works too."), 10, TEXT_DIM, wrap_w=self.W))

    def _style(self, i: int) -> None:
        if STYLES[i] == "image" and engines.crosshair_image(self.ctx.cfg["crosshair"].get("image", "")) is None:
            self.ctx.cfg["crosshair"]["style"] = "image"         # show the import button straight away
            self.ctx.reload_page()
            return QTimer.singleShot(150, self._import_image)
        was = self.ctx.cfg["crosshair"]["style"]
        self._set("style", STYLES[i])
        if (was == "image") != (STYLES[i] == "image"):
            self.ctx.reload_page()

    def _import_image(self) -> None:
        import hashlib
        path = self.ctx.pick_file(tr("Choose a crosshair image"), "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            if engines.crosshair_image(self.ctx.cfg["crosshair"].get("image", "")) is None:
                self.ctx.cfg["crosshair"]["style"] = "cross"
                self.ctx.reload_page()
            return
        try:
            size = os.path.getsize(path)
        except OSError:
            return self.ctx.toast(tr("This file cannot be read"), "warn")
        if size > XH_IMAGE_MAX_BYTES:
            return self.ctx.toast(tr("This picture is too big (4 MB at most)"), "warn")
        from PyQt6.QtGui import QImage, QImageReader
        reader = QImageReader(path)
        dim = reader.size()
        if not dim.isValid() or dim.width() > XH_IMAGE_MAX_SIDE or dim.height() > XH_IMAGE_MAX_SIDE:
            return self.ctx.toast(tr("This picture is too large (4096 px a side at most)"), "warn")
        img = reader.read()
        if img.isNull() or img.width() < 4 or img.height() < 4:
            return self.ctx.toast(tr("This is not a picture Rubenium can use"), "warn")
        img = img.convertToFormat(QImage.Format.Format_ARGB32)
        if max(img.width(), img.height()) > 256:
            img = img.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        CROSSHAIR_DIR.mkdir(parents=True, exist_ok=True)
        from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        name = "custom_" + hashlib.sha1(bytes(ba)).hexdigest()[:12] + ".png"
        try:
            (CROSSHAIR_DIR / name).write_bytes(bytes(ba))
        except OSError:
            return self.ctx.toast(tr("The picture could not be saved"), "warn")
        c = self.ctx.cfg["crosshair"]
        c["image"], c["style"] = name, "image"
        self.ctx.toast(tr("Crosshair image ready"))
        self._replace(c)

    def _default_crosshair(self) -> None:
        """Back to the normal crosshair (the picture stays in your folder: choose Image to use it again)."""
        c = self.ctx.cfg["crosshair"]
        c["style"] = "cross"
        self._replace(c)

    def _sync(self) -> None:
        c = self.ctx.cfg["crosshair"]
        st = c["style"]
        lines = st in ("cross", "tee") or (st == "circle" and c["length"] > 0)
        self.rows["length"].setEnabled(st != "dot")
        self.rows["gap"].setEnabled(lines)
        self.rows["thickness"].setEnabled(st != "dot")
        self.rows["radius"].setEnabled(st == "circle")
        self.rows["dot_size"].setEnabled(st == "dot" or c["dot"])
        self.rows["outline_w"].setEnabled(c["outline"])
        if st == "image":                           # 4.0: a picture keeps its own colours and shape
            for key in ("length", "gap", "thickness", "radius", "dot_size", "outline_w"):
                self.rows[key].setEnabled(False)
            self.t_dot.setEnabled(False)
            self.t_out.setEnabled(False)
        self.sw.setEnabled(st != "image")
        self.hue.setEnabled(st != "image")
        sel = self.ctx.cfg["crosshair_slot"]
        for tile in self.tiles:
            tile.selected = tile.number == sel and tile.data is not None
            tile.modified = tile.selected and any(tile.data.get(k) != c.get(k) for k in SHAPE_COMPARE)
            tile.update()
        has = any(t.selected for t in self.tiles)
        self.b_save.set_text(tr("Save to slot {n}", n=sel) if has else tr("Click a slot to save"))
        self.b_save.setEnabled(has)
        self.b_clear.setEnabled(has)

    def _slot_click(self, tile: "SlotTile") -> None:
        cfg = self.ctx.cfg
        if tile.data is None:                               # empty slot: keep the current crosshair here
            cfg["crosshair_presets"][str(tile.number)] = copy.deepcopy(cfg["crosshair"])
            cfg["crosshair_slot"] = tile.number
            cfg.save()
            tile.data = clean_crosshair(cfg["crosshair"])
            self.ctx.toast(tr("Saved in slot {n}", n=tile.number))
            self._sync()
        else:                                               # filled slot: use it
            cfg["crosshair_slot"] = tile.number
            keep = cfg["crosshair"]["monitor"]
            self._replace({**clean_crosshair(tile.data), "monitor": keep})

    def _slot_save(self) -> None:
        cfg = self.ctx.cfg
        n = cfg["crosshair_slot"]
        if not 1 <= n <= 6:
            return
        cfg["crosshair_presets"][str(n)] = copy.deepcopy(cfg["crosshair"])
        cfg.save()
        self.tiles[n - 1].data = clean_crosshair(cfg["crosshair"])
        self.ctx.toast(tr("Saved in slot {n}", n=n))
        self._sync()

    def _slot_clear(self) -> None:
        cfg = self.ctx.cfg
        n = cfg["crosshair_slot"]
        if not 1 <= n <= 6:
            return
        cfg["crosshair_presets"].pop(str(n), None)
        cfg["crosshair_slot"] = 0
        cfg.save()
        self.tiles[n - 1].data = None
        self._sync()

    def _apply(self) -> None:
        self.ctx.cfg.save()
        self.preview.update()
        self.ctx.crosshair.refresh()
        self._sync()

    def _colour_mode(self) -> None:
        """A dot colour or the slider: one or the other, and it is clear which one is in use."""
        preset = (self.ctx.cfg["crosshair"]["color"] or "").upper() in [c.upper() for c in XH_COLORS]
        self.sw.resting = not preset
        self.sw.update()
        self.hue.set_parked(preset)

    def _set(self, key: str, value) -> None:
        self.ctx.cfg["crosshair"][key] = value
        if key == "color":
            self.sw.set_current(value)
            self._colour_mode()
        self._apply()

    def _hue(self, v: float) -> None:
        col = QColor.fromHsv(int(v), 255, 255).name().upper()
        self.sw.set_current(col)
        self._set("color", col)

    def _replace(self, data: dict) -> None:
        self.ctx.cfg["crosshair"] = clean_crosshair(data)
        self.ctx.crosshair.refresh()
        self.ctx.reload_page()

    def _copy_code(self) -> None:
        QGuiApplication.clipboard().setText(extras.xhair_encode(self.ctx.cfg["crosshair"]))
        self.ctx.toast(tr("Code copied"))

    def _paste_code(self) -> None:
        data = extras.xhair_decode(QGuiApplication.clipboard().text())
        if data is None:
            return self.ctx.toast(tr("No crosshair code found"), "warn")
        self._replace(clean_crosshair({**self.ctx.cfg["crosshair"], **data}))

    def _reset(self) -> None:
        keep = self.ctx.cfg["crosshair"]["monitor"]
        self._replace({**CROSSHAIR, "monitor": keep})


# --------------------------------------------------------------------------- #
# Display colour
# --------------------------------------------------------------------------- #
class DisplayPage(Page):
    """Default = the screen exactly as Windows has it (every slider locked at its normal value).
    Custom = your own settings (saved). Moving any slider while on Default switches to Custom."""
    key = "display"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        eng = ctx.display
        eng.probe()
        lay = vbox(self, 7)
        self.seg = Segmented([tr("Default"), tr("Custom")], 1 if eng.manual == "A" else 0)
        self.seg.changed.connect(self._mode)
        lay.addWidget(self.seg)
        holder = QWidget()                             # room for two lines in both modes: the card never jumps
        holder.setFixedHeight(S(32))
        self.hint = Label("", 11, TEXT_DIM, wrap_w=self.W, parent=holder)
        lay.addWidget(holder)

        self.rows: dict = {}
        pct = lambda v: f"{int(v):+d}"  # noqa: E731

        def add(key, label, lo, hi, fmt, marks, default=None):
            default = DISPLAY_PROFILE[key] if default is None else default
            r = SliderRow(label, lo, hi, default, 1, default, fmt, marks=sorted(set(marks + [default])))
            r.changed.connect(lambda v, k=key: self._set(k, int(v)))
            self.rows[key] = r
            lay.addWidget(r)

        lay.addWidget(heading(tr("Light")))
        if eng.gamma_ok:
            add("brightness", tr("Brightness"), -50, 50, pct, [-50, -25, 0, 25, 50])
            add("contrast", tr("Contrast"), -50, 50, pct, [-50, -25, 0, 25, 50])
            add("gamma", tr("Gamma"), 60, 180, lambda v: f"{v / 100:.2f}", [60, 80, 100, 120, 140, 160, 180])
            add("shadow", tr("Shadows"), 0, 100, lambda v: f"{int(v)}%", [0, 25, 50, 75, 100])
        lay.addWidget(heading(tr("Colour")))
        if eng.mag_ok:
            add("saturation", tr("Colour strength"), 0, 200, lambda v: f"{int(v)}%", [0, 50, 100, 150, 200])
            add("hue", tr("Tint"), -180, 180, lambda v: f"{int(v):+d}°", [-90, -45, 0, 45, 90])
        if eng.nv is not None and eng.nv.ok:
            add("vibrance", tr("NVIDIA vibrance"), 50, 100, lambda v: f"{int(v)}%", [50, 60, 70, 80, 90, 100],
                default=eng.nv_default())
        if eng.gamma_ok:
            add("red", tr("Red"), 50, 100, lambda v: f"{int(v)}%", [50, 75, 100])
            add("green", tr("Green"), 50, 100, lambda v: f"{int(v)}%", [50, 75, 100])
            add("blue", tr("Blue"), 50, 100, lambda v: f"{int(v)}%", [50, 75, 100])
        if not (eng.gamma_ok and eng.mag_ok):
            lay.addWidget(notice("display", tr("Some settings are missing"),
                                 tr("This PC or screen does not allow them."), self.W))
        lay.addSpacing(S(4))
        self.b_reset = Button(tr("Reset Custom"), "danger", 34)
        self.b_reset.clicked.connect(self._reset)
        lay.addWidget(self.b_reset)
        self._show_rows()
        eng.changed.connect(self._refresh)

    def _custom(self) -> bool:
        return self.ctx.display.manual == "A"

    def on_show(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        self.seg.set_index(1 if self._custom() else 0)
        self._show_rows()

    def _show_rows(self) -> None:
        """Custom: the saved values. Default: every slider at its normal value."""
        custom = self._custom()
        pr = self.ctx.cfg["display"]["A"]
        for key, r in self.rows.items():
            value = pr.get(key, r.slider.default) if custom else r.slider.default
            r.set_value(r.slider.default if value < r.slider.lo else value)
        self.hint.set_text(tr("Your own settings. They are saved.") if custom else
                           tr("Your screen as Windows shows it. Move any slider to switch to Custom."))

    def _mode(self, i: int) -> None:
        self.ctx.display.set_active("A" if i == 1 else "off")
        self._show_rows()

    def _set(self, key: str, value: int) -> None:
        self.ctx.cfg["display"]["A"][key] = value
        self.ctx.cfg.save()
        if not self._custom():                       # moving a slider on Default switches to Custom
            self.ctx.display.set_active("A")
            self.seg.set_index(1)
            pr = self.ctx.cfg["display"]["A"]
            for k, r in self.rows.items():           # the other sliders show your saved Custom values
                if k != key:
                    v = pr.get(k, r.slider.default)
                    r.set_value(r.slider.default if v < r.slider.lo else v)
            self.hint.set_text(tr("Your own settings. They are saved."))
        else:
            self.ctx.display.apply()

    def _reset(self) -> None:
        self.ctx.cfg["display"]["A"] = dict(DISPLAY_PROFILE)
        self.ctx.cfg.save()
        self._show_rows()
        self.ctx.display.apply()
        self.ctx.toast(tr("Custom reset"))


# --------------------------------------------------------------------------- #
# Performance monitor + HUD
# --------------------------------------------------------------------------- #
class StatTile(Panel):
    def __init__(self, title: str, spark_max: float = 0.0) -> None:
        super().__init__()
        self.setFixedHeight(S(74))
        lay = vbox(self, 2, (10, 8, 10, 6))
        top = hbox(spacing=6)
        top.addWidget(Label(title.upper(), 9.5, TEXT_FAINT, weight=QFont.Weight.Bold).fit())
        self.value = Label("–", 13, bold=True, align=Qt.AlignmentFlag.AlignRight)
        top.addWidget(self.value, 1)
        lay.addLayout(top)
        self.spark = Sparkline(spark_max, 34)
        lay.addWidget(self.spark)


def rate(bps: float) -> str:
    mb = bps * 8 / 1e6
    return f"{mb:.1f} Mb/s" if mb >= 1 else f"{bps * 8 / 1e3:.0f} kb/s"


class PickGauge(Gauge):
    """A gauge you can click (to choose what the Top apps list shows)."""
    clicked = pyqtSignal()

    def __init__(self, caption: str) -> None:
        super().__init__(caption)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class TopList(QWidget):
    """Five rows: app name, how much it uses, and a bar on a fixed scale (the whole processor, or all of the
    memory), so 2 % looks small and 50 % fills half. Bars glide to their new length."""
    ROWS = 5

    def __init__(self) -> None:
        super().__init__()
        self.rows: list = []            # (name, value text, fraction of the whole)
        self._shown: dict = {}          # name -> drawn fraction
        self.setFixedHeight(S(26) * self.ROWS)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._anim = QTimer(self)
        self._anim.setInterval(16)
        self._anim.timeout.connect(self._step)

    def set_rows(self, rows: list) -> None:
        if rows != self.rows:
            names = {r[0] for r in rows}
            self._shown = {n: v for n, v in self._shown.items() if n in names}
            self.rows = rows
            self._anim.start()
            self.update()

    def _step(self) -> None:
        moving = False
        for name, _text, frac in self.rows:
            cur = self._shown.get(name, 0.0)
            nxt = cur + (frac - cur) * 0.22
            if abs(frac - nxt) < 0.001:
                nxt = frac
            else:
                moving = True
            self._shown[name] = nxt
        if not moving:
            self._anim.stop()
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rh, w = S(26), self.width()
        vw = S(64)
        for i in range(self.ROWS):
            y = i * rh
            track = QRectF(0, y + S(17), w, S(3))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha("#FFFFFF", 0.08 if i < len(self.rows) else 0.05))
            p.drawRoundedRect(track, 1.5, 1.5)
            if i >= len(self.rows):
                continue
            name, value, _frac = self.rows[i]
            p.setFont(font(12, QFont.Weight.DemiBold))
            p.setPen(QColor(TEXT))
            p.drawText(QRectF(0, y, w - vw - S(8), S(16)), int(Qt.AlignmentFlag.AlignVCenter),
                       p.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, int(w - vw - S(8))))
            p.setFont(font(11.5))
            p.setPen(QColor(TEXT_DIM))
            p.drawText(QRectF(w - vw, y, vw, S(16)), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), value)
            frac = max(0.0, min(1.0, self._shown.get(name, 0.0)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ui.accent)
            p.drawRoundedRect(QRectF(0, track.top(), max(S(3), w * frac), track.height()), 1.5, 1.5)


class PerfPage(Page):
    key = "perf"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        s = ctx.sensors
        s.acquire("probe")
        s.release("probe")
        lay = vbox(self, 8)
        self.g_gpu = None
        gauges = hbox(spacing=0)
        self.g_cpu, self.g_ram = PickGauge(tr("Processor")), PickGauge(tr("RAM"))
        gauges.addStretch(1)
        gauges.addWidget(self.g_cpu)
        gauges.addStretch(1)
        if s.nvml is not None and s.nvml.ok:
            self.g_gpu = Gauge(tr("Graphics"))
            gauges.addWidget(self.g_gpu)
            gauges.addStretch(1)
        gauges.addWidget(self.g_ram)
        gauges.addStretch(1)
        lay.addLayout(gauges)
        self.detail = Label("", 10.5, TEXT_DIM, align=Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.detail)
        tiles = hbox(spacing=8)
        self.t_ping, self.t_down = StatTile(tr("Ping")), StatTile(tr("Internet"))
        tiles.addWidget(self.t_ping, 1)
        tiles.addWidget(self.t_down, 1)
        lay.addLayout(tiles)

        lay.addWidget(heading(tr("Top apps")))          # click a gauge (or here) to switch
        self.top_kind = 0
        self.top_seg = Segmented([tr("Processor"), tr("RAM")], 0)
        self.top_seg.changed.connect(self._top_pick)
        lay.addWidget(self.top_seg)
        self.top_list = TopList()
        lay.addWidget(self.top_list)
        self.top_me = Label("", 10.5, TEXT_FAINT)
        lay.addWidget(self.top_me)
        self._top_data = ([], [], 0.0, 0.0)
        self.top = extras.TopApps()
        self.top.setParent(self)
        self.top.ready.connect(self._top_ready)
        self.g_cpu.clicked.connect(lambda: self._top_pick(0, True))
        self.g_ram.clicked.connect(lambda: self._top_pick(1, True))

        lay.addWidget(heading(tr("On-screen stats")))
        hud = ctx.cfg["hud"]
        self.t_hud = Toggle(hud["on"])
        self.t_hud.toggled_by_user.connect(lambda on: ctx.set_hud(on))
        lay.addWidget(row(tr("Show stats while I play"), self.t_hud))
        corner = Segmented([tr("Top left"), tr("Top right"), tr("Bottom left"), tr("Bottom right")], hud["corner"])
        corner.changed.connect(lambda i: self._hud("corner", i))
        lay.addWidget(corner)
        items = [("cpu", tr("Processor")), ("ram", tr("RAM")), ("ping", tr("Ping")), ("net", tr("Internet")),
                 ("clock", tr("Clock"))]
        if self.g_gpu is not None:
            items.insert(1, ("gpu", tr("Graphics")))
        for i in range(0, len(items), 2):
            pair = hbox(spacing=10)
            for key, label in items[i:i + 2]:
                t = Toggle(hud[key])
                t.toggled_by_user.connect(lambda on, k=key: self._hud(k, on))
                pair.addWidget(row(label, t, height=26), 1)
            if len(items[i:i + 2]) == 1:
                pair.addStretch(1)
            lay.addLayout(pair)
        lay.addSpacing(S(4))
        hud_reset = Button(tr("Reset on-screen stats"), "danger", 34)
        hud_reset.clicked.connect(self._hud_reset)
        lay.addWidget(hud_reset)
        lay.addWidget(heading(tr("This session")))
        box = Panel()
        grid = QGridLayout(box)
        grid.setContentsMargins(S(12), S(9), S(12), S(9))
        grid.setVerticalSpacing(S(4))
        self.sess = {}
        names = [("time", tr("Time")), ("cpu", tr("Processor, highest")), ("cpu_avg", tr("Processor, average")),
                 ("ram", tr("RAM, highest")), ("ping", tr("Ping, average"))]
        if self.g_gpu is not None:
            names.append(("temp", tr("Graphics card, hottest")))
        for i, (key, label) in enumerate(names):
            grid.addWidget(Label(label, 11.5, TEXT_DIM), i, 0)
            v = Label("–", 12, TEXT, bold=True, align=Qt.AlignmentFlag.AlignRight)
            grid.addWidget(v, i, 1)
            self.sess[key] = v
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        lay.addWidget(box)
        self._session()
        s.sample.connect(self._on_sample)

    def _hud(self, key: str, value) -> None:
        self.ctx.cfg["hud"][key] = value
        self.ctx.cfg.save()
        self.ctx.hud.refresh()

    def on_show(self) -> None:
        self.t_hud.set_checked(self.ctx.cfg["hud"]["on"])
        self.ctx.sensors.acquire("page")
        self.top.start()

    def on_hide(self) -> None:
        self.ctx.sensors.release("page")
        self.top.stop()

    def _top_pick(self, kind: int, from_gauge: bool = False) -> None:
        self.top_kind = kind
        if from_gauge:
            self.top_seg.set_index(kind)
        self._top_show()

    def _top_ready(self, cpu: list, ram: list, me_cpu: float, me_ram: float) -> None:
        self._top_data = (cpu, ram, me_cpu, me_ram)
        self._top_show()

    @staticmethod
    def _pct(v: float) -> str:
        return f"{v:.0f}%" if v >= 9.5 else f"{v:.1f}%"

    @staticmethod
    def _size(b: float) -> str:
        return f"{b / 2 ** 30:.1f} GB" if b >= 2 ** 30 else f"{b / 2 ** 20:.0f} MB"

    def _top_show(self) -> None:
        cpu, ram, me_cpu, me_ram = self._top_data
        if self.top_kind == 0:
            rows = [(n, self._pct(v), v / 100.0) for n, v in cpu]
            me = self._pct(me_cpu)
        else:
            import psutil
            total = max(1, psutil.virtual_memory().total)
            rows = [(n, self._size(b), b / total) for n, b in ram]
            me = self._size(me_ram)
        self.top_list.set_rows(rows)
        if self._top_data[0] or self._top_data[1]:
            self.top_me.set_text(tr("Rubenium itself: {v}", v=me))

    def _hud_reset(self) -> None:
        from .core import DEFAULTS
        self.ctx.cfg["hud"] = copy.deepcopy(DEFAULTS["hud"])
        self.ctx.hud.refresh()
        self.ctx.reload_page()

    def _session(self) -> None:
        se = self.ctx.session
        self.sess["time"].set_text(extras.hours_text(se.duration()))
        if se.n:
            self.sess["cpu"].set_text(f"{round(se.cpu_peak)}%")
            self.sess["cpu_avg"].set_text(f"{round(se.cpu_sum / se.n)}%")
            self.sess["ram"].set_text(f"{round(se.ram_peak)}%")
        if se.ping_n:
            self.sess["ping"].set_text(f"{round(se.ping_sum / se.ping_n)} ms")
        if "temp" in self.sess and se.temp_peak is not None:
            self.sess["temp"].set_text(f"{se.temp_peak} °C")

    def _on_sample(self, d: dict) -> None:
        if not self.isVisible():
            return
        self._session()
        cpu, ram = d.get("cpu"), d.get("ram")
        self.g_cpu.set_value(None if cpu is None else cpu / 100)
        self.g_ram.set_value(None if ram is None else ram / 100)
        parts = []
        if ram is not None:
            parts.append(f"{d['ram_used']:.1f} / {d['ram_total']:.0f} GB")
        if self.g_gpu is not None:
            gpu = d.get("gpu")
            self.g_gpu.set_value(None if gpu is None else gpu / 100)
            if d.get("temp") is not None:
                parts.append(f"{d['temp']} °C")
        self.detail.set_text("   ·   ".join(parts))
        ping = d.get("ping")
        self.t_ping.value.set_text(f"{ping} ms" if ping is not None else "–")
        if ping is not None:
            self.t_ping.spark.push(ping)
        v = d.get("down")
        if v is not None:
            self.t_down.value.set_text(rate(v))
            self.t_down.spark.push(v)


# --------------------------------------------------------------------------- #
# Tools: one switch for gaming, two safe buttons
# --------------------------------------------------------------------------- #
class ToolsPage(Page):
    key = "tools"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        lay = vbox(self, 8)
        tools = ctx.cfg["tools"]
        box = Panel()
        box.accent_edge = tools["gaming"]
        col = vbox(box, 6, (12, 10, 12, 10))
        self.t_game = Toggle(tools["gaming"])
        self.t_game.toggled_by_user.connect(self._gaming)
        self.t_game.setEnabled(win.IS_WIN)
        col.addWidget(row(tr("Gaming mode"), self.t_game))
        for line in (tr("Full power"), tr("Windows Game Mode on"), tr("Mouse acceleration off"),
                     tr("Background recording off")):
            col.addWidget(Label(line, 11.5,
                                TEXT if tools["gaming"] else TEXT_DIM))
        lay.addWidget(box)

        info = win.refresh_info()
        if info is not None:
            w, h, cur, best = info
            self._best = best
            if best > cur:
                lay.addWidget(notice("display", tr("Your screen can be smoother"),
                                     tr("It runs at {a} Hz but can do {b} Hz.", a=cur, b=best), self.W,
                                     self._button(tr("Use {b} Hz", b=best), self._fix_hz, "primary")))
        lay.addWidget(heading(tr("Quick fixes")))
        two = hbox(spacing=8)
        clean = Button(tr("Free up space"), icon="trash")
        clean.setToolTip(tr("Deletes old temporary files"))
        clean.clicked.connect(self._clean)
        mem = Button(tr("Free up memory"), icon="chip")
        mem.setToolTip(tr("Makes background apps give memory back"))
        mem.clicked.connect(self._memory)
        mem.setEnabled(win.IS_WIN)
        two.addWidget(clean, 1)
        two.addWidget(mem, 1)
        lay.addLayout(two)
        dns = Button(tr("Refresh internet connection"), icon="refresh")
        dns.setToolTip(tr("Clears saved internet addresses. Helps when a game cannot connect."))
        dns.clicked.connect(self._dns)
        dns.setEnabled(win.IS_WIN)
        lay.addWidget(dns)

        lay.addWidget(heading(tr("Connection test")))
        self.net_box = Panel()
        self.net_col = vbox(self.net_box, 3, (10, 8, 10, 8))
        self.net_lines = [Label("", 11.5, TEXT_DIM) for _ in range(3)]
        for lb in self.net_lines:
            self.net_col.addWidget(lb)
        lay.addWidget(self.net_box)
        self.b_test = Button(tr("Test my connection"), "primary", 30)
        self.b_test.clicked.connect(self._test)
        self.b_test.setEnabled(win.IS_WIN)
        lay.addWidget(self.b_test)
        ctx.ping_test.done.connect(self._show_test)
        self._show_test(ctx.ping_test.last)

        lay.addWidget(heading(tr("My PC")))
        self.info_lines = self._system_info()
        panel = Panel()
        col = vbox(panel, 3, (10, 8, 10, 8))
        for line in self.info_lines:
            col.addWidget(Label(line, 11, TEXT_DIM))
        lay.addWidget(panel)
        cp = Button(tr("Copy"), icon="copy")
        cp.clicked.connect(self._copy_info)
        lay.addWidget(cp)

    @staticmethod
    def _button(text, slot, kind="ghost"):
        b = Button(text, kind, 28)
        b.clicked.connect(slot)
        return b

    def _gaming(self, on: bool) -> None:
        tools = self.ctx.cfg["tools"]
        if on:
            tools["saved"] = {"plan": win.power_get(), "game_mode": win.game_mode_get(),
                              "accel": win.mouse_accel_get(), "dvr": win.game_dvr_get()}
            win.power_set("high")              # each call checks itself; a PC without that plan just keeps its own
            win.game_mode_set(True)
            win.mouse_accel_set(False)
            win.game_dvr_set(False)
        else:
            saved = tools.get("saved") or {}
            if saved.get("plan") in win.POWER_PLANS:
                win.power_set(saved["plan"])
            if isinstance(saved.get("game_mode"), bool):
                win.game_mode_set(saved["game_mode"])
            if isinstance(saved.get("accel"), bool):
                win.mouse_accel_set(saved["accel"])
            if isinstance(saved.get("dvr"), bool):
                win.game_dvr_set(saved["dvr"])
        tools["gaming"] = on
        self.ctx.cfg.save()
        self.ctx.toast(tr("Gaming mode is on") if on else tr("Back to your normal settings"))
        self.ctx.reload_page()

    def _memory(self) -> None:
        mb = win.free_memory()
        if mb is None:
            self.ctx.toast(tr("Could not do that on this PC"), "error")
        else:
            self.ctx.toast(tr("{mb} MB of memory freed", mb=f"{mb:.0f}"))

    def _dns(self) -> None:
        ok = win.flush_dns()
        self.ctx.toast(tr("Connection refreshed") if ok else tr("Could not do that on this PC"), "ok" if ok else "error")

    def _test(self) -> None:
        if self.ctx.ping_test.start():
            self.b_test.setEnabled(False)
            self.b_test.set_text(tr("Testing…"))

    def _show_test(self, results: list) -> None:
        self.b_test.setEnabled(win.IS_WIN and not self.ctx.ping_test.busy)
        self.b_test.set_text(tr("Test my connection"))
        if not results:
            self.net_lines[0].set_text("")
            for lb in self.net_lines[1:]:
                lb.set_text("")
            return
        for lb, (name, avg, jitter, lost) in zip(self.net_lines, results):
            lb.set_text(f"{name}:  {tr('no answer')}" if avg is None
                        else f"{name}:  {avg} ms   ±{jitter} ms" + (f"   {lost}% {tr('lost')}" if lost else ""))

    def _fix_hz(self) -> None:
        ok = win.refresh_set(self._best)
        self.ctx.toast(tr("Done") if ok else tr("Your screen refused this setting"), "ok" if ok else "error")
        self.ctx.reload_page()

    def _clean(self) -> None:
        freed, cutoff = 0, time.time() - 86400
        root = Path(tempfile.gettempdir())
        try:
            for entry in root.iterdir():
                try:
                    if entry.is_file() and entry.stat().st_mtime < cutoff:
                        size = entry.stat().st_size
                        entry.unlink()
                        freed += size
                    elif entry.is_dir() and entry.stat().st_mtime < cutoff and not entry.name.startswith("_MEI"):
                        size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
                        shutil.rmtree(entry)
                        freed += size
                except OSError:
                    continue              # in use: skipped
        except OSError:
            pass
        self.ctx.toast(tr("{mb} MB freed", mb=f"{freed / 1048576:.0f}"))

    def _system_info(self) -> list:
        lines = [win.windows_version(), win.cpu_name()]
        try:
            import psutil
            lines.append(tr("RAM") + f": {psutil.virtual_memory().total / 2 ** 30:.0f} GB")
        except Exception:  # noqa: BLE001
            pass
        lines += sorted({desc for _n, desc in win.display_devices()})
        for s in QGuiApplication.screens():
            g, dpr = s.geometry(), s.devicePixelRatio()
            lines.append(f"{tr('Screen')}: {round(g.width() * dpr)}×{round(g.height() * dpr)}, {round(s.refreshRate())} Hz")
        return lines

    def _copy_info(self) -> None:
        QGuiApplication.clipboard().setText("\n".join(self.info_lines))
        self.ctx.toast(tr("Copied"))


# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #


class BallPreview(QWidget):
    """The ball exactly as it is on screen: same size, same glow, same painting code."""

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self.setFixedHeight(int(BALL * ui.scale * max(BALL_SIZES) / 100) + 2 * S(GLOW) + S(4))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._clock = QTimer(self)
        self._clock.setInterval(33)
        self._clock.timeout.connect(self.update)

    def showEvent(self, _e) -> None:
        self._clock.start()

    def hideEvent(self, _e) -> None:
        self._clock.stop()

    def paintEvent(self, _e) -> None:
        from .window import paint_ball_face, paint_edge, paint_shape
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = BD()
        shape = QRectF(self.width() / 2 - d / 2, self.height() / 2 - d / 2, d, d)
        level = self.ctx.glow_level()
        paint_shape(p, self.ctx, shape, d / 2, level, self.devicePixelRatioF())
        paint_ball_face(p, self.ctx, shape, 1.0)
        paint_edge(p, self.ctx, shape, d / 2, level)


class StylePart:
    """Your ball, its effects, your colours, the R and ring styles you unlock with time and the themes. 4.2: the
    Shop's Style again (in 4.0 and 4.1 it was Settings > Look)."""
    cards: list
    unlocks: list
    c1 = None

    def buy(self, ident: str) -> None:
        hours = self.ctx.wallet.hours_for(ident)
        self.ctx.toast(tr("Unlocks after {n} h with Rubenium", n=f"{hours:g}"), "warn")

    def flair_changed(self) -> None:
        self.ctx.cfg.save()

    def build_style(self, lay) -> None:
        """4.2: the Shop's Style (it was Settings > Look): the ball, its effects, colours, R and ring styles, themes."""
        ctx, cfg = self.ctx, self.ctx.cfg

        def toggle(label, key, after=None):
            t = Toggle(bool(cfg[key]))

            def on(v):
                cfg[key] = v
                if after:
                    after(v)
            t.toggled_by_user.connect(on)
            lay.addWidget(row(label, t))
            return t
        lay.addWidget(heading(tr("Ball")))
        self.preview = BallPreview(ctx)
        lay.addWidget(self.preview)
        ball = SliderRow(tr("Ball size"), min(BALL_SIZES), max(BALL_SIZES), cfg["ball_size"], 10, 100,
                         lambda v: f"{int(v)}%", marks=list(BALL_SIZES))
        ball.changed.connect(lambda v: (ctx.set_look("ball_size", int(v)), self.preview.update()))
        lay.addWidget(ball)
        lay.addWidget(heading(tr("Effects")))
        toggle(tr("Glow"), "halo", after=lambda v: ctx.refresh_look())
        toggle(tr("Progress ring"), "ring", after=lambda v: ctx.refresh_look())
        toggle(tr("Hide menu bar when idle"), "autohide", after=lambda v: ctx.window.chrome_setting())
        self._look(lay)
        ctx.wallet.changed.connect(self._refresh_style)

    def _look(self, lay) -> None:
        """Colours, the progression (R and ring styles) and the themes."""
        from PyQt6.QtWidgets import QGridLayout
        from .shop import ColourRow, ThemeCard, UnlockBar, UnlockTile
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
        self._refresh_style()

    def _music_text(self) -> None:
        wait = self.ctx.wallet.music_wait()
        done = max(0.0, (3600 - wait) / 3600)
        hours = f"{min(0.9, done):.1f}"
        self.music_wait.set_text("" if not wait else tr("{x} / 1 hour to unlock",
                                                        x=hours.replace(".", ",") if lang() == "fr" else hours))
        self.music_wait.setVisible(bool(wait))
        self.t_music.setEnabled(not wait)

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
        self._refresh_style()

    def _refresh_style(self) -> None:
        self._rows()
        for w in self.cards + self.unlocks + [x for x in (self.c1,) if x is not None]:
            w.update()


class SettingsPage(StylePart, Page):
    def _log_out(self) -> None:
        self.ctx.online.log_out()
        self.ctx.quit()

    key = "settings"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        cfg = ctx.cfg
        self.cards, self.unlocks, self.c1 = [], [], None
        lay = vbox(self, 6)

        def toggle(label, key, after=None):
            t = Toggle(bool(cfg[key]))

            def on(v):
                cfg[key] = v
                if after:
                    after(v)
            t.toggled_by_user.connect(on)
            lay.addWidget(row(label, t))
            return t

        from .hub import NavTiles
        sec = int(getattr(ctx, "settings_tab", 0) or 0)
        shown = [0, 1, 2, 3, 4, 5]                      # 4.5: Style is here too (also in the Shop), online or not
        if sec not in shown:
            sec = ctx.settings_tab = 0
        tiles = NavTiles([(tr("General"), "cog"), (tr("Style"), "spark"), (tr("Sounds"), "volume"), (tr("Account"), "users"),
                          (tr("Backup"), "folder"), (tr("About"), "refresh")], shown.index(sec), per_row=3)

        def pick(i: int) -> None:
            ctx.settings_tab = shown[i]
            ctx.reload_page()
        tiles.changed.connect(pick)
        lay.addWidget(tiles)

        def note(text: str) -> None:                    # a short explanation under a setting, never off the edge
            lay.addWidget(Label(text, 10, TEXT_DIM, wrap_w=self.W))

        if sec == 0:                                    # ---------------------------------------------- General
            lay.addWidget(heading(tr("Opening")))
            toggle(tr("Hold to open"), "hold_open", after=lambda v: ctx.reload_page())
            if cfg["hold_open"]:                       # the time only matters while hold to open is on
                hold = SliderRow(tr("Hold time"), 200, 1000, cfg["hold_ms"], 100, 400, lambda v: f"{v / 1000:.1f} s",
                                 marks=list(range(200, 1001, 100)))

                def hold_set(v) -> None:
                    cfg["hold_ms"] = int(v)
                hold.changed.connect(hold_set)
                lay.addWidget(hold)
            from .music2 import KEY_CHOICES
            keys = [k for k, _n, _v in KEY_CHOICES]
            hk = Segmented([tr("No key") if k == "off" else n.replace("Right ", "R ") for k, n, _v in KEY_CHOICES],
                           keys.index(cfg["hotkey"]) if cfg["hotkey"] in keys else 0)

            def set_key(i: int) -> None:
                cfg["hotkey"] = keys[i]
                ctx.tapkey.set_key(keys[i])
            hk.changed.connect(set_key)
            lay.addWidget(Label(tr("Show / hide key"), 11.5, TEXT))
            lay.addWidget(hk)
            note(tr("Tap it once to open or close Rubenium, even in a game."))
            lay.addWidget(Label(tr("Holding this key down for 3 seconds restarts Rubenium, in case you are stuck or run into a problem."),
                                10, "#FFD54A", wrap_w=self.W))
            lay.addWidget(heading(tr("Music")))                 # 3.2
            from .music3 import app_name, ask_music_app
            app_btn = Button(app_name(cfg["music_app"]) or tr("Ask me"), "ghost", 30)
            app_btn.clicked.connect(lambda: ask_music_app(ctx, then_open=False))
            lay.addWidget(row(tr("Play opens"), app_btn))
            toggle(tr("Mute adverts"), "ad_mute", after=lambda v: (None if v else ctx.admute.release()))

            def compact_set(_v) -> None:
                home = ctx.window.pages.get("home")
                if home is not None:
                    home[1].set_compact(ctx.window.chrome.level)
            toggle(tr("Compact Music Mode"), "compact_music", after=compact_set)
            lay.addWidget(heading(tr("Games")))
            toggle(tr("Game mode"), "game_mouse")
            note(tr("While a fullscreen game is in front and Rubenium is closed, the ball ignores the mouse: clicks and "
                    "aiming near it go straight to the game. Open Rubenium with the show / hide key."))
            speeds = ["slow", "normal", "fast"]                  # 4.0: how fast cases open
            sp = Segmented([tr("Slow") + " 0.75×", tr("Normal") + " 1×", tr("Fast") + " 2.5×"],
                           speeds.index(cfg["chest_speed"]) if cfg["chest_speed"] in speeds else 1)
            sp.changed.connect(lambda i: cfg.__setitem__("chest_speed", speeds[i]))
            lay.addWidget(Label(tr("Case opening speed"), 12))
            lay.addWidget(sp)
            lay.addWidget(heading(tr("Language and size")))
            seg = Segmented(["English", "Français"], 1 if lang() == "fr" else 0)
            seg.setFixedWidth(S(170))
            seg.changed.connect(lambda i: ctx.set_language("fr" if i else "en"))
            lay.addWidget(row(tr("Language"), seg))
            size = SliderRow(tr("Size"), 70, 150, cfg["scale"], 10, 100, lambda v: f"{int(v)}%",
                             marks=list(range(70, 151, 10)))
            size.released.connect(lambda v: ctx.set_scale(int(v)))        # applied when you let go
            lay.addWidget(size)
            lay.addWidget(heading(tr("Tabs in the menu bar")))           # 4.2: moved here from Look
            from .pages2 import TABS
            for key, _icon, label in TABS:             # Home, Lyrics and Settings always stay
                if key in LOCKED_TABS or key in ("giveaway", "admin", "online"):      # ONLINE always stays
                    continue
                t = Toggle(bool(cfg["news_tab"]) if key == "new" else not cfg["tabs_off"].get(key))
                t.toggled_by_user.connect(lambda v, k=key: ctx.set_tab(k, v))
                lay.addWidget(row(tr(label), t))

        elif sec == 1:                                  # ---------------------------------------------- Style
            self.build_style(lay)
        elif sec == 2:                                  # ---------------------------------------------- Sounds
            lay.addWidget(heading(tr("Sounds")))

            def sounds(v: bool) -> None:
                cfg["sounds"] = v
                sfx.enabled = v
                if v:
                    sfx.play("on")                  # a sample of how quiet they are
            snd = Toggle(cfg["sounds"])
            snd.toggled_by_user.connect(sounds)
            lay.addWidget(row(tr("Interface sounds"), snd))
            from .notify import settings_section
            settings_section(ctx, lay)

        elif sec == 3:                                  # ---------------------------------------------- Account
            if not ctx.online.logged_in():
                lay.addWidget(Label(tr("Log in to see your account."), 12, TEXT_DIM))
            else:
                hours = ctx.online.hours()
                played = f"{hours:.1f}".replace(".", "," if lang() == "fr" else ".")
                lay.addWidget(heading(tr("Account")))
                lay.addWidget(Label(f"{ctx.online.username()}  ·  {played} h", 13, TEXT, bold=True))
                line = hbox(spacing=6)
                pw = Button(tr("Change password"), "ghost", 30)
                pw.clicked.connect(ctx.change_password_dialog)
                out = Button(tr("Log out"), "ghost", 30)
                out.clicked.connect(lambda: ctx.window.confirm(tr("Log out and close Rubenium?"), self._log_out,
                                                               yes=tr("Log out")))
                line.addWidget(pw, 1)
                line.addWidget(out, 1)
                lay.addLayout(line)
                lay.addWidget(heading(tr("Connection")))
                off = Toggle(bool(cfg["offline_mode"]))

                def set_off(v: bool) -> None:
                    if not ctx.set_offline_mode(v):
                        off.set_checked(not v)          # not allowed right now: the switch goes back
                off.toggled_by_user.connect(set_off)
                lay.addWidget(row(tr("Offline mode"), off))
                lay.addWidget(Label(tr("Disconnects Rubenium from the internet. Online features and time rewards are paused."), 10, TEXT_DIM, wrap_w=self.W))
                tour = Button(tr("Show the tour again"), "ghost", 30)
                tour.clicked.connect(ctx.start_tutorial)
                lay.addWidget(tour)
                lay.addSpacing(S(8))
                gone = Button(tr("Delete account"), "quiet", 24)
                gone.setFixedWidth(max(S(120), gone.sizeHint().width()))
                gone.clicked.connect(ctx.delete_account_dialog)
                lay.addWidget(gone, 0, Qt.AlignmentFlag.AlignRight)

        elif sec == 4:                                  # ---------------------------------------------- Backup
            from .hub import backup_section
            backup_section(ctx, lay, self.W)

        else:                                           # ---------------------------------------------- About
            lay.addWidget(heading(tr("Updates")))
            latest = ctx.updater.latest
            if latest:
                up = Button(tr("Update to {v}", v=latest.get("label", latest["version"])), "primary", 32)
                up.clicked.connect(ctx.install_update)
            else:
                up = Button(tr("Check for updates"), "ghost", 32, icon="refresh")
                up.clicked.connect(lambda: ctx.updater.check(manual=True))
            lay.addWidget(row(tr("Version {v}", v=VERSION_NAME), up))
            up.setFixedWidth(max(S(150), up.sizeHint().width()))
            t_up = Toggle(cfg["update_check"])

            def auto_up(v) -> None:
                cfg["update_check"] = v
                ctx.updater.start() if v else ctx.updater.stop()
            t_up.toggled_by_user.connect(auto_up)
            lay.addWidget(row(tr("Check automatically"), t_up))
            lay.addSpacing(S(10))
            leave = Button(tr("Quit Rubenium"), "quiet", 22)
            leave.setFixedWidth(max(S(120), leave.sizeHint().width()))
            leave.clicked.connect(lambda: ctx.window.confirm(tr("Quit Rubenium?"), ctx.quit, yes=tr("Quit")))
            lay.addWidget(leave, 0, Qt.AlignmentFlag.AlignHCenter)
