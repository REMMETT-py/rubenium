# -*- coding: utf-8 -*-
"""Timer, Themes, Launcher and Rocket League pages, plus the tab list."""
from __future__ import annotations

import os

from PyQt6.QtCore import QEasingCurve, QPoint, QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QAbstractButton, QFileDialog, QGridLayout, QWidget

from . import extras, win
from .core import WARN, ACCENT_DEFAULT, LOCKED_TABS, S, sfx, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, mix, tr, ui
from .admin import AdminPage, GiveawayPage
from .friends import FriendsPage
from .games import GamesPage
from .shop import ShopPage
from .pages import (CrosshairPage, DisplayPage, HomePage, LyricsPage, Page, PerfPage, SettingsPage, ToolsPage)
from .widgets import (notice, Button, Glyph, KeyChip, Label, Panel, Segmented, Swatches, Toggle, Tween, draw_icon, heading, hbox,
                      row, vbox)


# --------------------------------------------------------------------------- #
# Timer
# --------------------------------------------------------------------------- #
class TimeFace(QWidget):
    def __init__(self, engine) -> None:
        super().__init__()
        self.engine = engine
        self.setFixedHeight(S(64))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        f = font(40, QFont.Weight.Bold)
        f.setStyleHint(QFont.StyleHint.Monospace)
        p.setFont(f)
        state = self.engine.state
        p.setPen(QColor(TEXT) if state == "running" else (ui.accent if state == "paused" else alpha(TEXT, 0.55)))
        p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), extras.run_clock(self.engine.elapsed()))


class TimersPage(Page):
    key = "timer"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        eng = ctx.timer
        cfg = ctx.cfg["timer"]
        lay = vbox(self, 8)
        self.face = TimeFace(eng)
        lay.addWidget(self.face)
        btns = hbox(spacing=8)
        self.b_go = Button("", "primary", 34)
        self.b_pause = Button("", "ghost", 34)
        self.b_stop = Button(tr("Finish"), "ghost", 34)
        self.b_reset = Button(tr("Reset"), "ghost", 34)
        self.b_go.clicked.connect(eng.start_split)
        self.b_pause.clicked.connect(eng.pause)
        self.b_stop.clicked.connect(eng.finish)
        self.b_reset.clicked.connect(eng.reset)
        btns.addWidget(self.b_go, 3)
        btns.addWidget(self.b_pause, 2)
        btns.addWidget(self.b_stop, 2)
        btns.addWidget(self.b_reset, 2)
        lay.addLayout(btns)

        box = Panel()
        col = vbox(box, 2, (12, 8, 12, 8))
        self.lines = []
        for _ in range(5):
            line = hbox(spacing=6)
            a = Label("", 11.5, TEXT_DIM)
            a.setFixedWidth(S(26))
            b = Label("", 12.5, TEXT, bold=True)
            c = Label("", 11.5, TEXT_DIM, align=Qt.AlignmentFlag.AlignRight)
            line.addWidget(a)
            line.addWidget(b, 1)
            line.addWidget(c, 1)
            col.addLayout(line)
            self.lines.append((a, b, c))
        lay.addWidget(box)
        self.best = Label("", 11.5, TEXT_DIM, align=Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.best)

        t1 = Toggle(cfg["overlay"])
        t1.toggled_by_user.connect(lambda on: self._set("overlay", on))
        lay.addWidget(row(tr("Show on screen"), t1))
        if win.IS_WIN:
            t2 = Toggle(cfg["keys"])
            t2.toggled_by_user.connect(lambda on: self._set("keys", on))
            lay.addWidget(row(tr("Keyboard shortcuts"), t2))
            keys = Panel()
            grid = QGridLayout(keys)
            grid.setContentsMargins(S(12), S(8), S(12), S(8))
            grid.setHorizontalSpacing(S(10))
            grid.setVerticalSpacing(S(5))
            for i, (k, what) in enumerate((("Ctrl + F1", tr("Start, then lap")), ("Ctrl + F2", tr("Pause / resume")),
                                           ("Ctrl + F3", tr("Reset to 0")))):
                grid.addWidget(KeyChip(k), i, 0)
                grid.addWidget(Label(what, 12), i, 1)
            grid.setColumnStretch(1, 1)
            lay.addWidget(keys)
        lay.addSpacing(S(4))
        self.b_best = Button(tr("Reset best time"), "danger", 34)
        self.b_best.clicked.connect(self._reset_best)
        lay.addWidget(self.b_best)
        eng.changed.connect(self._sync)
        self._tick = QTimer(self)
        self._tick.setInterval(33)
        self._tick.timeout.connect(self.face.update)
        self._sync()

    def _reset_best(self) -> None:
        self.ctx.cfg["timer"]["best"] = 0.0
        self.ctx.cfg.save()
        self._sync()

    def _set(self, key: str, on: bool) -> None:
        self.ctx.cfg["timer"][key] = on
        self.ctx.cfg.save()
        self.ctx.apply_timer()

    def on_show(self) -> None:
        self._sync()

    def on_hide(self) -> None:
        self._tick.stop()

    def _sync(self) -> None:
        eng = self.ctx.timer
        if eng.state == "running" and self.isVisible():
            self._tick.start()
        else:
            self._tick.stop()
        self.b_go.set_text({"idle": tr("Start"), "running": tr("Split"), "paused": tr("Resume")}[eng.state])
        self.b_pause.set_text(tr("Pause"))
        self.b_pause.setEnabled(eng.state == "running")
        self.b_stop.setEnabled(eng.state != "idle")
        self.b_reset.setEnabled(eng.state != "idle")
        splits = eng.splits
        shown = list(enumerate(splits))[-5:]
        for i, (a, b, c) in enumerate(self.lines):
            if i < len(shown):
                n, t = shown[i]
                prev = splits[n - 1] if n else 0.0
                a.set_text(str(n + 1))
                b.set_text(extras.run_clock(t))
                c.set_text("+" + extras.run_clock(t - prev))
            else:
                a.set_text("")
                b.set_text(tr("No splits yet") if i == 0 and not shown else "")
                b.set_color(TEXT_FAINT if not shown else TEXT)
                c.set_text("")
        for _a, b, _c in self.lines[:len(shown)]:
            b.set_color(TEXT)
        best = self.ctx.cfg["timer"]["best"]
        self.b_best.setEnabled(best > 0)
        self.best.set_text(tr("Best: {t}", t=extras.run_clock(best)) if best > 0 else "")
        self.face.update()


# --------------------------------------------------------------------------- #
# Themes
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Launcher
# --------------------------------------------------------------------------- #
class AppTile(QAbstractButton):
    def __init__(self, app: dict) -> None:
        super().__init__()
        self.app = app
        self.running = False
        self.setFixedHeight(S(76))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip(app["name"])
        self._hover = Tween(self, on_change=self.update)
        self._press = Tween(self, on_change=self.update)
        self._pm = app["icon"].pixmap(S(36), S(36)) if app.get("icon") is not None else None

    def set_running(self, on: bool) -> None:
        if on != self.running:
            self.running = on
            self.update()

    def enterEvent(self, e) -> None:
        self._hover.to(1.0, 140)

    def leaveEvent(self, e) -> None:
        self._hover.to(0.0, 220)

    def mousePressEvent(self, e) -> None:
        self._press.to(1.0, 80)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        self._press.to(0.0, 170)
        super().mouseReleaseEvent(e)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        h, pr = self._hover.level, self._press.level
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        p.setPen(QPen(alpha(ui.accent, 0.55), 1) if self.running else Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.04 + 0.06 * h))
        p.drawRoundedRect(r, S(10), S(10))
        size = S(36) * (1 + 0.06 * h - 0.08 * pr)
        box = QRectF(r.center().x() - size / 2, r.top() + S(9) + (S(36) - size) / 2, size, size)
        if self._pm is not None and not self._pm.isNull():
            p.drawPixmap(box, self._pm, QRectF(self._pm.rect()))
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(ui.accent, 0.25))
            p.drawRoundedRect(box, S(8), S(8))
            p.setPen(QColor(TEXT))
            p.setFont(font(16, QFont.Weight.Bold))
            p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), self.app["name"][:1].upper())
        if self.running:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ui.accent)
            p.drawEllipse(QPointF(r.right() - S(9), r.top() + S(9)), S(3), S(3))
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        p.setPen(mix(QColor(TEXT_DIM), QColor(TEXT), max(h, 1.0 if self.running else 0.0)))
        text = p.fontMetrics().elidedText(self.app["name"], Qt.TextElideMode.ElideRight, int(r.width() - S(8)))
        p.drawText(QRectF(r.left(), r.bottom() - S(22), r.width(), S(18)), int(Qt.AlignmentFlag.AlignCenter), text)


class AppGrid(QWidget):
    """Four tiles per row. Open apps sit at the top; when one opens or closes, the tiles glide to their new places."""
    COLS = 4

    def __init__(self, tiles: list, width: int) -> None:
        super().__init__()
        self.tiles = tiles
        self.gap = S(4)
        self.tw = (width - self.gap * (self.COLS - 1)) // self.COLS
        self.th = S(76)
        rows = (len(tiles) + self.COLS - 1) // self.COLS
        self.setFixedSize(width, max(self.th, rows * (self.th + self.gap) - self.gap))
        for t in tiles:
            t.setParent(self)
            t.setFixedSize(self.tw, self.th)
        self._order: list = []
        self._from: dict = {}
        self._to: dict = {}
        self._move = Tween(self, 1.0, self._step, QEasingCurve.Type.InOutCubic)
        self.arrange(False)

    def _spot(self, i: int) -> QPoint:
        return QPoint((i % self.COLS) * (self.tw + self.gap), (i // self.COLS) * (self.th + self.gap))

    def arrange(self, animate: bool) -> None:
        order = sorted(range(len(self.tiles)), key=lambda i: (not self.tiles[i].running, i))
        if order == self._order:
            return
        self._order = order
        self._to = {self.tiles[i]: self._spot(n) for n, i in enumerate(order)}
        if animate and self.isVisible():
            self._from = {t: t.pos() for t in self.tiles}
            for t in self.tiles:
                if t.running:
                    t.raise_()                  # open apps pass over the others on their way up
            self._move.jump(0.0)
            self._move.to(1.0, 460)
        else:
            self._move.jump(1.0)
            for t, pt in self._to.items():
                t.move(pt)

    def _step(self) -> None:
        f = self._move.level
        for t, pt in self._to.items():
            a = self._from.get(t, pt)
            t.move(round(a.x() + (pt.x() - a.x()) * f), round(a.y() + (pt.y() - a.y()) * f))


class LauncherPage(Page):
    key = "launch"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        lay = vbox(self, 8)
        apps = ctx.apps()
        self.tiles = []
        self.grid = None
        if not apps:
            lay.addSpacing(S(16))
            lay.addWidget(Glyph("grid", 52), 0, Qt.AlignmentFlag.AlignHCenter)
            lay.addWidget(Label(tr("No apps found"), 12.5, TEXT_DIM, align=Qt.AlignmentFlag.AlignHCenter))
            lay.addSpacing(S(8))
        else:
            names = extras.running_names()
            for app in apps:
                tile = AppTile(app)
                tile.running = bool(app["exe"]) and app["exe"] in names
                tile.clicked.connect(lambda _=False, t=tile: self._click(t))
                self.tiles.append(tile)
            self.grid = AppGrid(self.tiles, self.W)
            lay.addWidget(self.grid)
        again = Button(tr("Search again"), "quiet", 28, icon="refresh")
        again.clicked.connect(self._rescan)
        lay.addWidget(again)
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._poll)

    def on_show(self) -> None:
        self._poll()
        self._timer.start()

    def on_hide(self) -> None:
        self._timer.stop()

    def _poll(self) -> None:
        if not self.tiles:
            return
        names = extras.running_names()
        for t in self.tiles:
            t.set_running(bool(t.app["exe"]) and t.app["exe"] in names)
        if self.grid is not None:
            self.grid.arrange(True)

    def _rescan(self) -> None:
        self.ctx.apps(force=True)
        self.ctx.reload_page()

    def _click(self, tile: AppTile) -> None:
        app = tile.app
        if tile.running:
            def close(t=tile) -> None:
                if extras.close_app(t.app["exe"]):
                    t.set_running(False)
                    self.grid.arrange(True)
                    self.ctx.toast(tr("{name} closed", name=t.app["name"]))
                else:
                    self.ctx.toast(tr("Could not close {name}", name=t.app["name"]), "error")
            self.ctx.window.confirm(tr("Close {name}?", name=app["name"]), close)
        elif win.open_path(app["path"]):
            self.ctx.toast(tr("Opening {name}", name=app["name"]))
            QTimer.singleShot(2500, self._poll)
        else:
            self.ctx.toast(tr("Could not open {name}", name=app["name"]), "error")


# --------------------------------------------------------------------------- #
# Rocket League: item swaps
# --------------------------------------------------------------------------- #
class SwapTile(QAbstractButton):
    """One swap: picture of the result, the item you equip, what it becomes, and a tick.
    With no item it is an empty "?" slot kept for a future swap."""

    def __init__(self, item, on: bool, ready: bool) -> None:
        super().__init__()
        self.item, self.on, self.ready = item, on, ready
        self.setFixedHeight(S(50) if item is not None else S(34))
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pm = extras.swap_preview(item) if item is not None else None
        self._thumb = None
        if item is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = Tween(self, on_change=self.update)
        self._on = Tween(self, 1.0 if on else 0.0, self.update)
        self.pending = False

    def set_state(self, on: bool, pending: bool) -> None:
        self.pending = pending
        if on != self.on:
            self.on = on
            self._on.to(1.0 if on else 0.0, 200)
        self.update()

    def enterEvent(self, e) -> None:
        if self.item is not None:
            self._hover.to(1.0, 140)

    def leaveEvent(self, e) -> None:
        self._hover.to(0.0, 220)

    def _picture(self, side: int):
        """The preview, cropped to a square and scaled once for this size."""
        dpr = self.devicePixelRatioF()
        key = (side, round(dpr * 100))
        if self._pm is not None and (self._thumb is None or self._thumb[0] != key):
            px = max(1, int(round(side * dpr)))
            pm = self._pm.scaled(px, px, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                 Qt.TransformationMode.SmoothTransformation)
            pm = pm.copy((pm.width() - px) // 2, (pm.height() - px) // 2, px, px)
            pm.setDevicePixelRatio(dpr)
            self._thumb = (key, pm)
        return self._thumb[1] if self._thumb else None

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        rad = S(10)
        h, on = self._hover.level, self._on.level
        if self.item is None:
            pen = QPen(alpha("#FFFFFF", 0.10), 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r, rad, rad)
            p.setPen(alpha(TEXT_DIM, 0.45))
            p.setFont(font(15, QFont.Weight.Bold))
            p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), "?")
            return
        if not self.ready:
            p.setOpacity(0.45)
        if self.pending:                                    # waiting for "Reload"
            p.setPen(QPen(QColor(WARN), 1.4, Qt.PenStyle.DashLine))
        else:
            p.setPen(QPen(mix(alpha("#FFFFFF", 0.08 + 0.10 * h), ui.accent, on), 1.2))
        p.setBrush(mix(alpha("#FFFFFF", 0.04 + 0.04 * h), alpha(ui.accent, 0.16), on))
        p.drawRoundedRect(r, rad, rad)

        side = int(r.height() - S(10))                      # picture of the result (black until one is added)
        box = QRectF(r.left() + S(5), r.top() + S(5), side, side)
        clip = QPainterPath()
        clip.addRoundedRect(box, S(7), S(7))
        p.fillPath(clip, QColor("#000000"))
        pm = self._picture(side)
        if pm is not None:
            p.save()
            p.setClipPath(clip)
            p.drawPixmap(box.topLeft(), pm)
            p.restore()
        p.setPen(QPen(alpha("#FFFFFF", 0.10), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(box, S(7), S(7))

        x = box.right() + S(10)
        w = r.right() - S(34) - x
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        old = self.item["old"] if self.ready else tr("Coming soon")
        p.drawText(QRectF(x, r.top() + S(7), w, S(16)), int(Qt.AlignmentFlag.AlignVCenter),
                   p.fontMetrics().elidedText(old, Qt.TextElideMode.ElideRight, int(w)))
        p.setPen(QColor(TEXT))
        p.setFont(font(12.5, QFont.Weight.Bold))
        p.drawText(QRectF(x, r.top() + S(23), w, S(19)), int(Qt.AlignmentFlag.AlignVCenter),
                   p.fontMetrics().elidedText("→ " + self.item["new"], Qt.TextElideMode.ElideRight, int(w)))
        cx, cy, cr = r.right() - S(17), r.center().y(), S(7)          # round tick on the right
        p.setPen(QPen(mix(alpha("#FFFFFF", 0.25), ui.accent, on), 1.3))
        p.setBrush(alpha(ui.accent, on))
        p.drawEllipse(QPointF(cx, cy), cr, cr)
        if on > 0.05:
            pen = QPen(alpha("#06110A" if ui.accent.lightnessF() > 0.6 else "#FFFFFF", on), 1.6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            path = QPainterPath(QPointF(cx - 3.2, cy + 0.2))
            path.lineTo(QPointF(cx - 0.9, cy + 2.6))
            path.lineTo(QPointF(cx + 3.4, cy - 2.4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)


class RocketPage(Page):
    key = "rl"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        eng = ctx.rocket
        eng.ensure_detected()
        self.pending = None                       # wanted swaps while the game is open, until Reload
        self.tiles = []
        lay = vbox(self, 8)
        plats = eng.available()
        self.plat = eng.platform()

        box = Panel()
        box.accent_edge = bool(self.plat)
        h = hbox(box, 8, (12, 8, 8, 8))
        col = vbox(spacing=0)
        col.addWidget(Label(tr("Rocket League detected") if self.plat else tr("Rocket League not detected"), 12.5,
                            bold=True))
        col.addWidget(Label(tr("Supports Steam and Epic"), 10.5, TEXT_DIM))
        h.addLayout(col, 1)
        if not self.plat:
            b = Button(tr("Search"), "primary", 28, icon="refresh")
            b.setFixedWidth(max(S(96), b.sizeHint().width()))
            b.clicked.connect(self._search)
            h.addWidget(b)
        lay.addWidget(box)

        names = [extras.PLATFORM_NAMES[pl] for pl in extras.PLATFORMS]
        self.seg = Segmented(names, extras.PLATFORMS.index(self.plat) if self.plat else 0)
        self.seg.faint = {i for i, pl in enumerate(extras.PLATFORMS) if pl not in plats}
        self.seg.changed.connect(self._platform)
        lay.addWidget(self.seg)
        if not self.plat:
            pick = Button(tr("Choose the game folder"), "quiet", 28, icon="folder")
            pick.clicked.connect(self._folder)
            lay.addWidget(pick)

        state = eng.check() if self.plat else "nogame"
        if state in ("undone", "changed", "missing"):
            text = {"undone": tr("An update put back the original files"), "changed": tr("Game files were changed"),
                    "missing": tr("A game file is missing")}[state]
            fix = None
            if state != "missing":
                fix = Button(tr("Fix"), "primary", 28)
                fix.clicked.connect(self._fix)
            warn = notice("rocket", text, tr("Press Fix to swap them again") if fix else tr("Repair the game in Epic or Steam"),
                          self.W, fix)
            lay.addWidget(warn)

        content = QWidget()
        cl = vbox(content, 8)
        shown = self._shown()
        base = eng.actual() if self.plat else {}
        for cat, name in extras.RL_CATS:
            cl.addWidget(heading(tr(name)))
            col = vbox(spacing=5)
            for it in [x for x in extras.RL_ITEMS if x["cat"] == cat]:
                key = extras.rl_key(it)
                ready = extras.swap_source(it) is not None
                on = shown.get(key) == it["id"]
                tile = SwapTile(it, on, ready)
                tile.pending = self._waiting(it, shown, base)
                tile.setEnabled(bool(self.plat) and ready)
                tile.clicked.connect(lambda _=False, i=it: self._toggle(i))
                self.tiles.append(tile)
                col.addWidget(tile)
            col.addWidget(SwapTile(None, False, False))      # room for the next swap
            cl.addLayout(col)
        t = Toggle(ctx.cfg["rl"]["auto_fix"])
        t.toggled_by_user.connect(self._auto)
        cl.addSpacing(S(2))
        cl.addWidget(row(tr("Fix automatically after updates"), t))
        cl.addSpacing(S(4))
        reset = Button(tr("Reset Swaps"), "danger", 34)
        reset.clicked.connect(self._reset)
        cl.addWidget(reset)
        if not self.plat:                           # nothing to swap until the game is found
            content.setEnabled(False)
            from PyQt6.QtWidgets import QGraphicsBlurEffect
            blur = QGraphicsBlurEffect(content)
            blur.setBlurRadius(S(7))
            content.setGraphicsEffect(blur)
        lay.addWidget(content)

        self._poll = QTimer(self)
        self._poll.setInterval(2000)
        self._poll.timeout.connect(self._bar)

    # -- what the tiles show: the real files, or the choice waiting for Reload
    def _shown(self) -> dict:
        if not self.plat:
            return {}
        return dict(self.pending) if self.pending is not None else self.ctx.rocket.actual()

    @staticmethod
    def _waiting(item: dict, shown: dict, base: dict) -> bool:
        """Yellow outline = this tile is about to change: it is being switched on, or switched off with nothing
        taking its place. A swap that is simply replaced by another one of the same item gets no outline."""
        key = extras.rl_key(item)
        now, want = base.get(key) == item["id"], shown.get(key) == item["id"]
        if want:
            return not now
        return now and key not in shown

    def _sync(self) -> None:
        base = self.ctx.rocket.actual()
        shown = self._shown()
        for tile in self.tiles:
            key, ident = extras.rl_key(tile.item), tile.item["id"]
            on = shown.get(key) == ident
            tile.set_state(on, self._waiting(tile.item, shown, base))
        self._bar()

    def _bar(self) -> None:
        """The bar at the bottom: shown only while changes are waiting."""
        if self.pending is None:
            return
        eng = self.ctx.rocket
        base = eng.actual()
        n = sum(1 for key in set(self.pending) | set(base) if self.pending.get(key) != base.get(key))
        if n == 0:
            self.pending = None
            self.ctx.window.confirm_w.hide()
            return
        text = tr("1 change waiting") if n == 1 else tr("{n} changes waiting", n=n)
        yes = tr("Reload") if eng.running() else tr("Apply")      # Reload = close the game, swap, start it
        self.ctx.window.confirm(text, self._go, yes=yes, no=tr("Cancel"), persistent=True, on_no=self._cancel)

    def on_show(self) -> None:
        self._poll.start()

    def on_hide(self) -> None:
        self._poll.stop()
        if self.pending is not None:              # leaving the tab drops unapplied changes
            self.pending = None
            self.ctx.window.confirm_w.hide()
            self._sync()

    # -- actions
    def _toggle(self, item: dict) -> None:
        eng = self.ctx.rocket
        if eng.working or not self.plat:
            return
        desired = self._shown()
        key = extras.rl_key(item)
        if desired.get(key) == item["id"]:
            sfx.play("off")
            desired.pop(key)                       # off: the original comes back
        else:
            sfx.play("on")
            if key in desired:                     # two swaps of the same item cannot be on together
                self.ctx.toast(tr("Only one swap at a time for {name}", name=item["old"]), "warn")
            desired[key] = item["id"]
        self._choose(desired)

    def _choose(self, desired: dict) -> None:
        eng = self.ctx.rocket
        if eng.running() or self.pending is not None:
            self.pending = desired                 # collect changes; the bar asks once
            self._sync()
        else:
            self.ctx.rocket_apply(desired, False)

    def _go(self) -> None:
        desired, self.pending = self.pending, None
        if desired is not None:
            self.ctx.rocket_apply(desired, self.ctx.rocket.running())

    def _cancel(self) -> None:
        self.pending = None
        self._sync()

    def _fix(self) -> None:
        self._choose(self.ctx.rocket.active())

    def _reset(self) -> None:
        """Every swap off and every swap file back to the original (also repairs broken files)."""
        self._choose({})

    def _auto(self, on: bool) -> None:
        self.ctx.cfg["rl"]["auto_fix"] = on
        self.ctx.cfg.save()

    def _platform(self, i: int) -> None:
        eng = self.ctx.rocket
        plat = extras.PLATFORMS[i]
        if plat == self.plat:
            return
        if not eng.set_platform(plat):             # not installed: snap back
            self.seg.set_index(extras.PLATFORMS.index(self.plat) if self.plat else 0)
            self.ctx.toast(tr("{name} version not detected", name=extras.PLATFORM_NAMES[plat]), "warn")
            return
        self.pending = None
        self.ctx.window.confirm_w.hide()
        self.ctx.reload_page()

    def _search(self) -> None:
        found = self.ctx.rocket.detect()
        if found:
            self.ctx.toast(tr("Rocket League detected"))
            self.ctx.reload_page()
        else:
            self.ctx.toast(tr("Rocket League not detected"), "warn")

    def _folder(self) -> None:
        w = self.ctx.window
        w.modal = True
        w.hide()
        try:
            path = QFileDialog.getExistingDirectory(None, tr("Choose the game folder"))
        finally:
            w.show()
            w.modal = False
        if not path:
            return
        if self.ctx.rocket.add_folder(path):
            self.ctx.reload_page()
        else:
            self.ctx.toast(tr("That is not the Rocket League folder"), "error")


class NewsPage(Page):
    """Every update since the first version, newest first."""
    key = "new"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        lay = vbox(self, 6)
        lay.addWidget(Label(tr("Updates"), 16, bold=True))
        for n, (version, lines) in enumerate(extras.NEWS):
            lay.addSpacing(S(6))
            head = hbox(spacing=8)
            head.addWidget(Label(tr("Version {v}", v=version), 13, ui.accent.name() if n == 0 else TEXT, bold=True).fit())
            if n == 0:
                head.addWidget(Label(tr("This version"), 10.5, TEXT_DIM).fit())
            head.addStretch(1)
            lay.addLayout(head)
            for text in lines:
                line = hbox(spacing=8)
                dot = Label("•", 12.5, TEXT_FAINT)
                dot.setFixedWidth(S(8))
                line.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
                line.addWidget(Label(tr(text), 12.5, TEXT if n == 0 else TEXT_DIM, wrap_w=self.W - S(18)))
                line.addStretch(1)
                lay.addLayout(line)


class Combined(Page):
    """Several pages stacked in one tab, each under its own title."""
    parts: tuple = ()

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        lay = vbox(self, 10)
        self.subs = []
        for n, (cls, title) in enumerate(self.parts):
            if n:
                lay.addSpacing(S(10))
            lay.addWidget(Label(tr(title), 16, bold=True))
            sub = cls(ctx)
            self.subs.append(sub)
            lay.addWidget(sub)

    def on_show(self) -> None:
        for sub in self.subs:
            sub.on_show()

    def on_hide(self) -> None:
        for sub in self.subs:
            sub.on_hide()

    def on_state(self, st) -> None:
        for sub in self.subs:
            sub.on_state(st)

    def on_art(self, pixmap) -> None:
        for sub in self.subs:
            sub.on_art(pixmap)


class ScreenPage(Combined):
    key = "crosshair"
    parts = ((CrosshairPage, "Crosshair"), (DisplayPage, "Display"), (TimersPage, "Timer"))


class PcPage(Combined):
    key = "perf"
    parts = ((PerfPage, "Stats"), (LauncherPage, "Apps"), (ToolsPage, "Tools"))


PAGES = {"home": HomePage, "lyrics": LyricsPage, "crosshair": ScreenPage, "rl": RocketPage, "perf": PcPage,
         "games": GamesPage, "friends": FriendsPage, "themes": ShopPage, "new": NewsPage, "settings": SettingsPage,
         "giveaway": GiveawayPage, "admin": AdminPage}
# Fixed order: music first, then what you use in a game, then the PC, then fun and looks, settings last.
TABS = [("home", "home", "Home"), ("lyrics", "lyrics", "Lyrics"), ("crosshair", "display", "Screen"),
        ("rl", "rocket", "RL SWAP"), ("perf", "perf", "PC"),
        ("giveaway", "gift", "Giveaway"), ("games", "dice", "Games"), ("themes", "gem", "Shop"),
        ("friends", "users", "Social"), ("new", "spark", "Updates"), ("settings", "cog", "Settings"),
        ("admin", "shield", "Admin")]
LIVE_TABS: set = set()      # Giveaway (while one is live) and Admin (the admin account only)
LOCK_PAGES = {"games", "themes", "friends", "giveaway"}     # covered while the admin has locked the app


TEMP_TABS: set = set()      # tabs shown only until the user leaves them


def visible_tabs(cfg) -> list:
    """The tabs the user keeps in the menu bar (Home, Lyrics and Settings cannot be hidden)."""
    off = cfg["tabs_off"] if isinstance(cfg["tabs_off"], dict) else {}

    def shown(key: str) -> bool:
        if key in ("giveaway", "admin"):
            return key in LIVE_TABS
        if key in LOCKED_TABS or key in TEMP_TABS:
            return True
        if key == "new":                        # off by default; shows by itself after an update
            return bool(cfg["news_tab"])
        return not off.get(key)
    return [t for t in TABS if shown(t[0])]


def make_page(ctx, key: str) -> Page:
    return PAGES[key](ctx)
