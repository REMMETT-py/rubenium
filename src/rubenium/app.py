# -*- coding: utf-8 -*-
"""Application wiring: start-up order, shared context, tray and tidy shutdown."""
from __future__ import annotations

import atexit
import logging
import math
import os
import sys
from pathlib import Path
import threading
import time

from PyQt6.QtCore import QLocale, QObject, QPointF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QIcon, QImage, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

from . import win
from .econ import Econ
from .online import Online
from .wallet import COLOURS, Wallet
from .core import BUILD, Net, APP_NAME, ACCENT_DEFAULT, FONT_DEFAULT, FONT_FAMILIES, TEXT, Config, alpha, mix, apply_look, set_lang, sfx, setup_logging, tr, ui
from .engines import CrosshairOverlay, DisplayEngine, HudOverlay, PingTest, Sensors
from .lyrics import LyricsService
from .media import CMD_SEEK, MediaService, Status, TrackState, source_keywords
from . import extras
from .pages2 import TABS, TEMP_TABS
from .window import MainWindow, Welcome

log = logging.getLogger("rubenium.app")

APP_QSS = """
QToolTip { background:#181C1D; color:#EDEDED; border:1px solid #2C3233; padding:4px 7px; font-size:12px; }
QMenu { background:#181C1D; color:#EDEDED; border:1px solid #2C3233; padding:6px; font-size:13px; }
QMenu::item { padding:6px 24px 6px 12px; border-radius:5px; }
QMenu::item:selected { background:#2A3031; }
QMenu::separator { height:1px; background:#2C3233; margin:6px 4px; }
"""


def cleanup_files() -> None:
    """At start: remove what only takes room. Lyrics not opened for 30 days (at most 400 kept), leftover
    temporary files, profile pictures not seen for 30 days, and old downloads of the updater."""
    import tempfile
    from .core import DATA_DIR, LYRICS_DIR
    now = time.time()
    try:
        files = sorted((f for f in LYRICS_DIR.glob("*.json")), key=lambda f: f.stat().st_mtime, reverse=True)
        for n, f in enumerate(files):
            if n >= 400 or now - f.stat().st_mtime > 30 * 86400:
                f.unlink(missing_ok=True)
        for f in list(DATA_DIR.glob("*.tmp")) + list(DATA_DIR.glob("*/*.tmp")):
            if now - f.stat().st_mtime > 600:
                f.unlink(missing_ok=True)
        faces = DATA_DIR / "faces"
        if faces.is_dir():
            for f in faces.glob("*.jpg"):
                if now - f.stat().st_mtime > 30 * 86400:
                    f.unlink(missing_ok=True)
        tmp = Path(tempfile.gettempdir())
        for pattern in ("Rubenium_update*", "rubenium_*.png", "rubenium_*.tmp"):
            for f in tmp.glob(pattern):
                if f.is_file() and now - f.stat().st_mtime > 86400:
                    f.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        log.exception("cleanup failed")


def accent_from_image(pixmap: QPixmap):
    """Most vivid dominant hue of the cover, lifted to a readable accent. None if the cover is grey."""
    img = pixmap.toImage().scaled(24, 24, Qt.AspectRatioMode.IgnoreAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation).convertToFormat(QImage.Format.Format_RGB32)
    bins = [[0.0, 0.0, 0.0, 0.0] for _ in range(12)]          # weight, sum h-x, sum h-y, sum s
    import math
    for y in range(img.height()):
        for x in range(img.width()):
            c = QColor(img.pixel(x, y))
            h, s, v = c.hsvHueF(), c.hsvSaturationF(), c.valueF()
            if h < 0 or s < 0.28 or v < 0.22:
                continue
            w = s * s * (0.4 + v)
            b = bins[int(h * 12) % 12]
            b[0] += w
            b[1] += math.cos(h * 2 * math.pi) * w
            b[2] += math.sin(h * 2 * math.pi) * w
            b[3] += s * w
    best = max(bins, key=lambda b: b[0])
    if best[0] < 6.0:                                # black, white or grey cover: stay neutral, never a tint
        total = sum(QColor(img.pixel(x, y)).valueF() for y in range(img.height()) for x in range(img.width()))
        bright = total / max(1, img.width() * img.height())
        return QColor.fromHsvF(0.58, 0.04, 0.95 if bright > 0.55 else 0.80)
    hue = (math.atan2(best[2], best[1]) / (2 * math.pi)) % 1.0
    sat = max(0.45, min(0.68, best[3] / best[0]))
    return QColor.fromHsvF(hue, sat, 0.93)


def r_mark(size: float) -> QPainterPath:
    """A simple, bold R drawn from shapes (no font needed), for a square of `size` pixels."""
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QPolygonF
    u = size
    stem = QPainterPath()
    stem.addRect(QRectF(.30 * u, .24 * u, .13 * u, .52 * u))
    outer = QPainterPath()
    outer.addRect(QRectF(.30 * u, .24 * u, .26 * u, .30 * u))
    bulge = QPainterPath()
    bulge.addEllipse(QPointF(.56 * u, .39 * u), .15 * u, .15 * u)
    inner = QPainterPath()
    inner.addRect(QRectF(.43 * u, .35 * u, .13 * u, .08 * u))
    hole = QPainterPath()
    hole.addEllipse(QPointF(.56 * u, .39 * u), .04 * u, .04 * u)
    leg = QPainterPath()
    leg.addPolygon(QPolygonF([QPointF(.47 * u, .53 * u), QPointF(.61 * u, .53 * u), QPointF(.74 * u, .76 * u),
                              QPointF(.60 * u, .76 * u)]))
    leg.closeSubpath()
    return stem.united(outer.united(bulge).subtracted(inner.united(hole))).united(leg)


def app_icon() -> QIcon:
    """Black tile, white R."""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#0A0A0A"))
    p.drawRoundedRect(1, 1, 62, 62, 14, 14)
    p.setBrush(QColor("#FFFFFF"))
    p.drawPath(r_mark(64))
    p.end()
    return QIcon(pm)


class App(QObject):
    """Shared context handed to the window and every page."""

    def __init__(self, qapp: QApplication) -> None:
        super().__init__()
        self.qapp = qapp
        self.cfg = Config()
        for _k in ("welcome", "splash"):                 # 3.0.0: always on (no longer a setting)
            if not self.cfg[_k]:
                self.cfg[_k] = True
        self._was_open = bool(self.cfg["card_open"])
        self.cfg["unlock_all"] = False
        if self.cfg["scale_before_games"]:           # the Games tab had made the menu bigger: back to your size
            self.cfg["scale"] = self.cfg["scale_before_games"]
            self.cfg["scale_before_games"] = 0
        for key, value in (("glow_power", 2), ("backdrop", 1), ("corners", 0)):     # 1.7: one look for everyone
            self.cfg[key] = value
        self.online = Online(self)                   # the account (log in on the welcome screen)
        self.econ = Econ(self)                       # coins, keys and items as the server has them
        self.wallet = Wallet(self)
        self.econ.changed.connect(self.sync_look)
        self.econ.changed.connect(self._flair_changed)
        self.econ.changed.connect(self._shop_items_check)
        self._screen_colour = None
        self._screen_timer = QTimer(self)
        self._screen_timer.timeout.connect(self._watch_screen)
        from .collection import set_econ
        from .bazaar import TradeLink
        from .friends import Faces
        set_econ(self.econ)
        self.faces = Faces(self)                     # profile pictures
        self.trade = TradeLink(self)                 # the trade being made, kept in step with the server
        self.trade.changed.connect(self._trade_changed)
        self.econ.live_changed.connect(self._live_changed)
        self.econ.locks_changed.connect(self._locks_changed)     # 4.0: the admin locked or unlocked something
        self.econ.xp_changed.connect(self._xp_first)              # 4.0: the levels are explained once
        self._xp_watch = QTimer(self)                             # (and again when the menu opens later)
        self._xp_watch.setInterval(3000)
        self._xp_watch.timeout.connect(lambda: self.econ.xp and self._xp_first())
        self._xp_watch.start()
        threading.Thread(target=cleanup_files, daemon=True).start()
        self.casino = False                          # inside the casino (Games tab, shown bigger)
        self.casino_ask = None                       # the gambling warning is being shown
        self._wear_only_owned()
        self.apply_font()
        disp = self.cfg["display"]
        if disp.get("active") == "B":                # one Custom since 1.1: an old "Custom 2" becomes Custom
            disp["A"] = dict(disp["B"])
            disp["active"] = "A"
        self.cfg["card_open"] = False
        self._news = False
        set_lang(self.cfg["lang"] or ("fr" if QLocale.system().language() == QLocale.Language.French else "en"))
        apply_look(self.cfg)
        sfx.enabled = bool(self.cfg["sounds"])
        self.welcome = None
        self._preview = ""
        self._apps = None
        ui.accent = self.base_accent()
        self.state = TrackState(Status.NOT_RUNNING)
        self.art_pixmap = None
        self._art_key = ""
        self._pos_base, self._pos_t = 0.0, time.monotonic()
        self._closing = False
        self.tray = None

        self.media = MediaService(self.cfg["source"])
        self.lyrics = LyricsService()
        self.display = DisplayEngine(self.cfg)
        self.sensors = Sensors()
        self.ping_test = PingTest()
        self.crosshair = CrosshairOverlay(self.cfg)
        self.hud = HudOverlay(self.cfg, self.sensors)
        self.meter = win.AudioMeter()
        self.appvol = win.AppVolume()
        from .music3 import AdMuter
        self.admute = AdMuter(self)
        self._env = 0.0
        self._audio = QTimer(self)
        self._audio.setInterval(33)
        self._audio.timeout.connect(self._sample_audio)
        self._safe("online swaps cache", extras.load_online_swaps_cache)   # before the engine: swaps that are on
        self.rocket = extras.RocketSwaps(self.cfg)
        self.splash = extras.Splash(self.cfg, self.rocket)
        self.rocket.busy.connect(self._rocket_busy)
        self.rocket.done.connect(self._rocket_done)
        self.rocket.changed.connect(self._rocket_changed)
        self.updater = extras.Updater(BUILD)
        self.updater.found.connect(self._update_found)
        self.updater.checked.connect(self._update_checked)
        self.updater.progress.connect(lambda pct: self.window.show_busy(tr("Downloading update… {p}%", p=pct)))
        self.updater.ready.connect(self._update_ready)
        self.updater.failed.connect(self._update_failed)
        self._update_prompted = ""
        extras.Updater.cleanup()
        from .hub import daily_nag, daily_unclaimed
        self._daily_timer = QTimer(self)                 # 4.4: unclaimed daily reward: a reminder every 30 minutes
        self._daily_timer.setInterval(30 * 60 * 1000)
        self._daily_timer.timeout.connect(lambda: daily_nag(self))
        self._daily_timer.start()

        def dots() -> None:                              # and a slow red dot on the online button
            from .widgets import NOTIFY_DOTS
            want = daily_unclaimed(self)
            if want != ("online" in NOTIFY_DOTS):
                NOTIFY_DOTS.discard("online") if not want else NOTIFY_DOTS.add("online")
        self._dot_timer = QTimer(self)
        self._dot_timer.setInterval(2000)
        self._dot_timer.timeout.connect(dots)
        self._dot_timer.start()
        self.session = extras.Session()
        self.sensors.sample.connect(self.session.feed)
        self.timer = extras.TimerEngine(self.cfg)
        self.timer_overlay = extras.TimerOverlay(self.cfg, self.timer)
        self.hotkeys = extras.Hotkeys(qapp)
        self.hotkeys.triggered.connect(self._on_key)
        from .music2 import TapKey
        self.tapkey = TapKey(self)                  # tap Right Shift: show or hide Rubenium
        self.tapkey.tapped.connect(self._tap_key)
        self.outdated = False                       # the server or the updater says: update before playing online
        self._usage = QTimer(self)
        self._usage.setInterval(60000)
        self._usage.timeout.connect(self._count_usage)
        self._usage.start()
        self.window = MainWindow(self)
        self.main_window = self.window              # 3.2: the small menu; self.window is the online menu while it is on
        self.online_mode = False
        self._online_win = None
        self.online.changed.connect(lambda: self.window.sync_lock())     # offline mode: cover the online tabs
        from .notify import Notifier
        self.notifier = Notifier(self)              # pop-ups and a quiet beep for what happens online

        self.media.state_changed.connect(self._on_state)
        self.media.artwork_ready.connect(self._on_artwork)
        self.display.failed.connect(self._on_display_failed)
        self.display.changed.connect(self.window.ball.update)
        qapp.aboutToQuit.connect(self.shutdown)
        atexit.register(self._last_resort)

        self._intro()                                # the welcome screen (or the ball) is up before anything heavy
        QTimer.singleShot(0, self._late_start)

    # ------------------------------------------------------------------ start-up
    def _intro(self) -> None:
        """Welcome screen -> Launch -> the ball lands where it was left. Skipped when the app restarts itself
        (after an update or to get admin rights) and when the user switched it off."""
        self._news = self.cfg["seen_version"] != BUILD and self.cfg["usage_s"] > 0    # updated, not new
        self.cfg["seen_version"] = BUILD
        restarted = "--updated" in sys.argv or "--elevated" in sys.argv
        selftest = "--selftest" in sys.argv or any(x.startswith("--selftest-update=") for x in sys.argv)
        if (not self.cfg["welcome"] or restarted) and (self.online.logged_in() or selftest):
            self.window.show_ball()
            QTimer.singleShot(700, self._after_intro)
            return
        try:
            self.window._restore_position()
            self.window._retime()
            self.welcome = Welcome(self, self._after_intro)
            self.welcome.start()
        except Exception:  # noqa: BLE001
            log.exception("welcome screen failed")
            self.welcome = None
            self.window.show_ball()

    def _after_intro(self) -> None:
        """Back to how the app was left: the card opens again if it was open (or to show what is new)."""
        self.welcome = None
        was_open, self._was_open = self._was_open, False
        if self._closing or "--selftest" in sys.argv:
            return
        if self._news:                              # after an update: the New tab shows up while it is read
            self._news = False
            TEMP_TABS.add("new")
            self.window.tabs_changed()
            self.window.goto("new")
        elif was_open:
            self.window.expand()

    @staticmethod
    def _safe(name: str, fn) -> None:
        """One start-up step. If it fails it is logged and the app carries on: the ball always appears."""
        try:
            fn()
        except Exception:  # noqa: BLE001
            log.exception("start-up step '%s' failed", name)

    def _late_start(self) -> None:
        self._safe("colours", self.refresh_accent)
        selftest = "--selftest" in sys.argv
        self._safe("media", self.media.start)
        if not selftest:
            self._safe("tray", self._make_tray)
            self._safe("autostart", self._sync_autostart)
        self._safe("overlays", self.apply_overlays)
        self._safe("timer", self.apply_timer)
        self._safe("accent", self.refresh_accent)
        self._safe("rocket", self.rocket.start)
        self._safe("online swaps", lambda: extras.fetch_online_swaps(self))
        self._safe("splash", self.splash.start)
        self._safe("coins", self.wallet.start)
        if self.cfg["offline_mode"]:               # offline mode survives a restart, but only when logged in
            if self.online.logged_in():
                Net.blocked = True
                self.online.offline = True
            else:
                self.cfg["offline_mode"] = False
        if "--selftest" not in sys.argv:
            self._safe("account", self.online.start)
            self._safe("economy", self.econ.start)
        self._zoomer = QTimer(self)
        self._zoomer.setInterval(350)
        self._zoomer.timeout.connect(self.game_zoom)
        self._zoomer.start()
        if self.cfg["update_check"] and not selftest:
            self._safe("updates", self.updater.start)
        self._safe("show/hide key", lambda: self.tapkey.set_key(self.cfg["hotkey"]))
        self._pin = QTimer(self)
        self._pin.setInterval(2000)
        self._pin.timeout.connect(lambda: self._safe("housekeeping", self._housekeeping))
        self._pin.start()
        # Right after Windows starts, the tray and the screen settings can still be settling: try again later.
        QTimer.singleShot(8000, lambda: self._safe("tray retry", self._retry_tray))
        QTimer.singleShot(12000, lambda: self._safe("display again", self._reapply_display))
        QTimer.singleShot(30000, lambda: self._safe("tray retry", self._retry_tray))
        swap = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--selftest-update=")), "")
        if swap:                                    # build test: install a local .exe exactly like an update
            QTimer.singleShot(1500, lambda: self._selftest_update(swap))
        elif selftest:
            QTimer.singleShot(1500, self._selftest)

    def _sync_autostart(self) -> None:
        if not win.IS_WIN:
            return
        self.cfg["autostart"] = win.autostart_set(True)   # 3.0.0: always starts with Windows (keeps the path right too)

    def _retry_tray(self) -> None:
        if self.tray is None and not self._closing and "--selftest" not in sys.argv:
            self._make_tray()

    def _reapply_display(self) -> None:
        if self.cfg["display"]["active"] in ("A", "B") and not self._closing:
            self.display.apply()

    def _selftest_update(self, setup: str) -> None:
        """Build test: update exactly like the Update button does (silent setup, then the new app starts)."""
        ok = extras.run_setup(setup, "--selftest")
        log.info("UPDATE SETUP %s", "STARTED" if ok else "FAILED")
        self.shutdown()
        self.qapp.exit(0 if ok else 1)

    def _selftest(self) -> None:
        """--selftest: open every tab in both languages, then quit. Exit code 0 only if nothing went wrong.
        The automatic build runs this on Windows before publishing a release."""
        errors: list = []
        old_hook = sys.excepthook

        def hook(t, v, tb) -> None:
            errors.append(v)
            log.critical("SELFTEST error", exc_info=(t, v, tb))
        sys.excepthook = hook
        w = self.window
        lang = self.cfg["lang"]
        TEMP_TABS.add("new")
        w.tabs_changed()
        if self.welcome is not None:               # the welcome screen is part of the test: press Launch
            self.welcome.launch(force=True)
            return QTimer.singleShot(3500, self._selftest)
        steps = [w.expand] + [lambda k=k: w.goto(k) for k, _, _ in TABS if k != "online"]
        steps += [lambda t=t: self.preview_theme(t["id"]) for t in extras.THEMES]      # every theme paints
        steps += [lambda: self.preview_theme("")]
        steps += [lambda: self.set_language("fr"), lambda: w.goto("home"), lambda: w.goto("rl"),
                  lambda: self.set_language(lang or "en"), w.collapse, w.expand, w.collapse]
        steps += [lambda: self.enter_online(), lambda: None, lambda: None,      # 3.2: the online menu opens and closes
                  lambda: self.leave_online(ask=False), lambda: None, lambda: None, lambda: None]

        def run(i: int = 0) -> None:
            if i < len(steps):
                log.info("SELFTEST step %d", i)
                try:
                    steps[i]()
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
                    log.exception("SELFTEST step %d failed", i)
                QTimer.singleShot(900, lambda: run(i + 1))
                return
            sys.excepthook = old_hook
            if win.IS_WIN:                          # the Stats tab's process reader must work on real Windows
                snap = win.process_snapshot()
                log.info("SELFTEST processes read: %s", None if snap is None else len(snap))
                if not snap or len(snap) < 10 or not any(n.lower() == "explorer.exe" or n.lower().startswith("rubenium")
                                                         for _p, n, _c, _m in snap):
                    errors.append(RuntimeError("process snapshot failed"))
                try:                                # the game-has-the-mouse test reads pointers correctly
                    import ctypes
                    u = ctypes.windll.user32
                    u.LoadCursorW.restype = ctypes.c_void_p
                    u.CreateCursor.restype = ctypes.c_void_p
                    arrow = u.LoadCursorW(None, ctypes.c_void_p(32512))
                    and_mask = (ctypes.c_ubyte * 128)(*([0xFF] * 128))
                    xor_mask = (ctypes.c_ubyte * 128)(*([0x00] * 128))
                    empty = u.CreateCursor(None, 0, 0, 32, 32, and_mask, xor_mask)
                    arrow_blank, empty_blank = win.cursor_is_blank(int(arrow)), win.cursor_is_blank(int(empty or 0))
                    win._foreground_game()
                    log.info("SELFTEST pointer test: arrow blank=%s, empty blank=%s, captured now=%s",
                             arrow_blank, empty_blank, win.mouse_captured())
                    if arrow_blank or not empty_blank:
                        errors.append(RuntimeError("pointer test failed"))
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
                try:                                # click-through switch on the ball's window
                    import ctypes
                    hwnd = int(self.window.ball.winId())
                    getter = ctypes.windll.user32.GetWindowLongPtrW
                    getter.restype = ctypes.c_ssize_t
                    win.set_click_through(hwnd, True)
                    on = bool(getter(ctypes.c_void_p(hwnd), -20) & 0x20)
                    win.set_click_through(hwnd, False)
                    off = not (getter(ctypes.c_void_p(hwnd), -20) & 0x20)
                    log.info("SELFTEST click-through: %s/%s, mouse captured now: %s", on, off, win.mouse_captured())
                    if not (on and off):
                        errors.append(RuntimeError("click-through switch failed"))
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
                try:
                    sfx.enabled = True
                    sfx.play("on")                  # the sound files can be made and played
                    log.info("SELFTEST sound file: %s", sfx._files.get("on"))
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
            log.info("SELFTEST %s (%d problems)", "OK" if not errors else "FAILED", len(errors))
            self.shutdown()
            self.qapp.exit(1 if errors else 0)
        run()
        QTimer.singleShot(120000, lambda: (log.error("SELFTEST timed out"), self.qapp.exit(2)))

    def apply_overlays(self) -> None:
        """(Re)apply everything that lives outside the card."""
        self.crosshair.refresh()
        self.hud.refresh()
        if self.cfg["display"]["active"] in ("A", "B"):
            self.display.probe()
            self.display.apply()
        elif self.display.probed:
            self.display.restore(keep_state=True)

    def _housekeeping(self) -> None:
        for overlay in (self.window, self.window.ball, self.window.drawer, self.crosshair, self.hud,
                        self.timer_overlay):            # the welcome / login screen is never pinned over other apps
            if overlay is None:
                continue
            if overlay is self.window and self.window.modal:
                continue
            if overlay.isVisible():
                win.set_topmost(int(overlay.winId()))
        self.window.set_game_state(win.fullscreen_state())

    def _make_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        menu.setStyleSheet(APP_QSS)
        for text, slot in ((tr("Open / close"), self.window.toggle),
                           (tr("Crosshair on / off"), lambda: self.set_crosshair(not self.cfg["crosshair_on"])),
                           (tr("Normal screen colours"), self.display.panic),
                           (tr("Put the ball back in the corner"), self.window.reset_position)):
            menu.addAction(text).triggered.connect(slot)
        menu.addSeparator()
        menu.addAction(tr("Quit Rubenium")).triggered.connect(self.quit)
        self._tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.window.toggle()
                                    if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    # ------------------------------------------------------------------ media
    def _on_state(self, st: TrackState) -> None:
        self.state = st
        self.admute.on_state(st)                      # 3.2: adverts are muted while they play
        self._pos_base, self._pos_t = float(st.position_ms), time.monotonic()
        if st.art_key != self._art_key:
            self._art_key = st.art_key
            if st.has_track and st.title:
                from .hub import history_add, history_share
                history_add(st.title, st.artist, st.source_id or "")
                history_share(self, st.title, st.artist)
            self.art_pixmap = None
            self.window.on_art(None)
            self.refresh_accent()
        self.window.on_state(st)
        self._sync_audio()

    def _on_artwork(self, key: str, data: bytes) -> None:
        if key != self._art_key:
            return                                    # stale: the track already changed
        pm = QPixmap()
        if pm.loadFromData(data):
            self.art_pixmap = pm
            self.window.on_art(pm)
            self.refresh_accent()

    def position_ms(self) -> float:
        st = self.state
        pos = self._pos_base
        if st.status is Status.PLAYING:
            pos += (time.monotonic() - self._pos_t) * 1000.0
        return min(pos, st.duration_ms) if st.duration_ms else pos

    def seek(self, ms: float) -> None:
        self._pos_base, self._pos_t = float(ms), time.monotonic()
        self.media.send(CMD_SEEK, int(ms))

    def on_visibility(self) -> None:
        self.media.watching = self.window.expanded or self.cfg["ring"]
        self.media.refresh()

    def open_player(self) -> None:
        """Album cover clicked: bring the music app to the front, maximised."""
        st = self.state
        if st.source_id and win.focus_app(source_keywords(st.source_id)):
            return
        if not st.source_id or "spotify" in st.source_id.lower():
            if win.open_path("spotify:"):
                return
        self.toast(tr("Could not find the music app window"), "warn")

    # ------------------------------------------------------------------ glow
    def _sync_audio(self) -> None:
        want = (self.cfg["halo"] and self.state.status is Status.PLAYING
                and not self.meter.failed and self.window.game_state != 2)
        if want and not self._audio.isActive():
            self._audio.start()
        elif not want and self._audio.isActive():
            self._audio.stop()
            self._env = 0.0

    def _sample_audio(self) -> None:
        peak = self.meter.peak()
        if peak is None:
            return self._sync_audio()
        target = min(1.0, (peak ** 0.8) * 1.25)
        self._env += (target - self._env) * (0.65 if target > self._env else 0.13)   # quick rise, soft fall

    def glow_level(self, hover: float = 0.0) -> float:
        pulse = 0.5 + 0.5 * math.sin(time.monotonic() * 2.0 * math.pi / 3.0)         # 3 s breathing cycle
        if self._audio.isActive():
            level = 0.30 + 0.10 * pulse + 0.62 * self._env                           # breathes, and follows the music
        else:
            level = 0.55 + 0.45 * pulse
            if self.state.status is not Status.PLAYING:
                level *= 0.7
        return min(1.0, level * (1.0 + 0.45 * hover))

    # ------------------------------------------------------------------ look
    # themes: background designs unlocked by hours of use; a locked one can be previewed
    # ------------------------------------------------------------------ coins and what they bought
    def _colour_ok(self, kind: str, hexa: str, real: bool = False) -> bool:
        """Colours are free: any valid colour may be used."""
        return bool(hexa) and QColor(hexa).isValid()

    def _flair_changed(self) -> None:
        if getattr(self, "window", None) is None:
            return
        for page in self.window.each_page():
            fl = getattr(page, "flair", None)
            if fl is not None:
                fl.fit()
                fl.update()

    def sync_look(self) -> None:
        """Tell the server which progression theme, ball and ring are on (shown on your profile)."""
        ec = self.econ
        if not ec.ready or getattr(self, "_syncing_look", False):
            return
        for slot, key in (("theme", "theme"), ("ball", "ball_style"), ("ring", "ring_style")):
            value = self.cfg[key]
            want = value if ":" in value else extras.PROG_IDS[key].get(value, "")
            if want and ec.worn(slot) != want and ec.can_wear(want):
                self._syncing_look = True
                ec.wear(slot, want, lambda _ok, _d: setattr(self, "_syncing_look", False))
                return

    def _wear_only_owned(self) -> None:
        """At start: anything worn that is not really owned (tried in test mode, or edited in) comes off."""
        w, cfg = self.wallet, self.cfg
        for key in ("ball_style", "ring_style"):                   # a removed style is swapped for its new one
            cfg[key] = extras.RETIRED_STYLES.get(cfg[key], cfg[key])
        if not w.really_owns(f"theme:{cfg['theme']}"):
            cfg["theme"] = "clean"
        if not w.really_owns(f"r:{cfg['ball_style']}"):
            cfg["ball_style"] = "classic"
        if not w.really_owns(f"ring:{cfg['ring_style']}"):
            cfg["ring_style"] = "line"
        if not self._colour_ok("c1", cfg["custom_accent"], real=True):
            cfg["custom_accent"] = ""
        if not self._colour_ok("c2", cfg["accent2"], real=True):
            cfg["accent2_on"] = False

    # ------------------------------------------------------------------ casino
    def _casino_scale(self, base: int) -> int:
        """The casino is shown 50% bigger, as long as it still fits on the screen."""
        scr = self.window.screen() or QGuiApplication.primaryScreen()
        area = scr.availableGeometry() if scr is not None else None
        fit = 999
        if area is not None:
            fit = int(min(area.height() * 0.92 / 640, area.width() * 0.9 / 400) * 100)
        return max(base, min(int(round(base * 1.5)), fit))

    def enter_casino(self, game=None) -> None:
        if game is not None:
            self.cfg["game"] = game
        self.casino = True
        if self.online_mode:                          # 3.2: the online menu is already big
            return self.reload_page("games")
        base = self.cfg["scale_before_games"] or self.cfg["scale"]
        want = self._casino_scale(base)
        if want != self.cfg["scale"]:
            self.cfg["scale_before_games"] = base
            self.cfg["scale"] = want
            ui.scale = want / 100
            self.rebuild_ui()
        else:
            self.reload_page()

    def leave_casino(self) -> None:
        self.casino = False
        if self.online_mode and not self.cfg["scale_before_games"]:
            return self.reload_page("games")
        before = self.cfg["scale_before_games"]
        if before:
            self.cfg["scale"] = before
            self.cfg["scale_before_games"] = 0
            ui.scale = before / 100
            self.rebuild_ui()
        else:
            self.reload_page()

    def game_zoom(self) -> None:
        """Switching the left half of the online menu away from Games while in the casino goes back to the lobby (a
        running round finishes first). 4.2: closing the menu, hiding it, going into a game or leaving online mode
        keeps the casino game you were on: it is there again next time."""
        w = self.window
        if not self.casino or w.morph.busy or w.slide.busy or w.zoom.busy or w.fade.busy or self.welcome is not None:
            return
        before = self.cfg["scale_before_games"]
        if not self.online_mode:                       # the casino lives in the online menu: it waits there
            if before:                                 # (a size left by an older version is put back once)
                self.cfg["scale"] = before
                self.cfg["scale_before_games"] = 0
                ui.scale = before / 100
                self.rebuild_ui()
            return
        if "games" in w.tab_keys():
            return
        entry = w.pages.get("games")
        page = entry[1] if entry else None
        if page is not None and hasattr(page, "busy") and page.busy():
            page.wrap_up()
            return
        self.casino = False
        w._drop_page("games")

    def usage_hours(self) -> float:
        return self.cfg["usage_s"] / 3600

    def _count_usage(self) -> None:
        self.cfg["usage_s"] = self.cfg["usage_s"] + 60.0

    def theme(self) -> dict:
        if self._preview:
            return extras.theme_by_id(self._preview)
        th = extras.theme_by_id(self.cfg["theme"])
        return th if self.wallet.owns(f"theme:{th['id']}") else extras.THEMES[0]

    def set_theme(self, ident: str) -> None:
        self._preview = ""
        self.cfg["theme"] = ident
        self._theme_changed()

    def preview_theme(self, ident: str) -> None:
        self._preview = ident
        self._theme_changed()

    def start_preview(self, ident: str) -> None:
        if self._preview != ident:
            self.preview_theme(ident)
            self.refresh_accent()

    def stop_preview(self) -> None:
        if self._preview:
            self._preview = ""
            self._theme_changed()
            self.refresh_accent()

    def _theme_changed(self) -> None:
        self.window.theme_changed()

    def base_accent(self) -> QColor:
        custom = self.cfg["custom_accent"]
        return QColor(custom) if self._colour_ok("c1", custom) else QColor(ACCENT_DEFAULT)

    def refresh_accent(self) -> None:
        target = None
        music = bool(self.cfg["accent_from_art"]) and self.wallet.owns("music")
        screen = bool(self.cfg["accent_from_screen"]) and not music
        tint = self.theme().get("tint")                  # a shop theme brings its own two colours
        if music and self.art_pixmap is not None:
            target = accent_from_image(self.art_pixmap)
        elif screen:
            target = self._screen_colour
        second = QColor(self.cfg["accent2"])
        # The second colour belongs to your own colours: it is not used while the music picks the colour.
        del second                                       # 2.2.1: a second colour only comes with a shop theme
        ui.accent2 = None
        if tint:                                         # a shop theme keeps its own colours (the music only tints them)
            target = mix(QColor(tint[0]), target, 0.2) if target is not None else QColor(tint[0])
            ui.accent2 = QColor(tint[1])
        self._screen_timer.setInterval(2500)
        if screen != self._screen_timer.isActive():
            self._screen_timer.start() if screen else self._screen_timer.stop()
            if screen:
                QTimer.singleShot(50, self._watch_screen)
        self.window.update()
        self.window.ball.update()
        self.window.set_accent(target or self.base_accent())
        for overlay in (self.hud,):
            if overlay.isVisible():
                overlay.update()

    def _watch_screen(self) -> None:
        """"Use screen colours": every 2.5 s take a tiny picture of the screen (64 x 36 points) and follow its
        main colour. Very light: one small copy, no video capture."""
        if not self.cfg["accent_from_screen"] or (self.cfg["accent_from_art"] and self.wallet.owns("music")):
            return self._screen_timer.stop()
        try:
            scr = self.window.screen() or QGuiApplication.primaryScreen()
            geo = scr.geometry()
            shot = scr.grabWindow(0, 0, 0, geo.width(), geo.height())
            if shot.isNull():
                return
            col = accent_from_image(shot.scaled(64, 36, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                Qt.TransformationMode.FastTransformation))
        except Exception:  # noqa: BLE001
            return
        old = self._screen_colour
        if col is not None and (old is None or abs(col.hsvHueF() - old.hsvHueF()) > 0.03
                                or abs(col.hsvSaturationF() - old.hsvSaturationF()) > 0.08):
            self._screen_colour = col
            self.window.set_accent(col)
            self.window.ball.update()

    def set_colour_source(self, source: str) -> None:
        """Only one of them at a time: "music", "screen" or "" (your own colours)."""
        self.cfg["accent_from_art"] = source == "music"
        self.cfg["accent_from_screen"] = source == "screen"
        self.refresh_accent()

    # ------------------------------------------------------------------ shop cosmetics (ball, line, theme, font)
    def wear_shop_item(self, item: str) -> None:
        """Put on a ball, line, theme or font from the shop ("" for a font = the normal font)."""
        kind = item.split(":")[0]
        key = {"ball": "ball_style", "line": "ring_style", "theme": "theme", "font": "font_item"}.get(kind)
        if key is None:
            return
        if kind == "theme":
            self.set_theme(item)
        else:
            self.cfg[key] = item
        if kind == "font":
            self.apply_font(rebuild=True)
            self.econ.wear("font", item)
        self.cfg.save()
        self.refresh_accent()
        self.window.ball.update()
        self.sync_look()

    def take_off_shop_item(self, kind: str) -> None:
        if kind == "theme":
            self.set_theme("clean")
        elif kind == "font":
            self.cfg["font_item"] = ""
            self.apply_font(rebuild=True)
            self.econ.wear("font", "prog:font:0")
        else:
            self.cfg["ball_style" if kind == "ball" else "ring_style"] = "classic" if kind == "ball" else "line"
        self.cfg.save()
        self.refresh_accent()
        self.window.ball.update()
        self.sync_look()

    def shop_item_worn(self, item: str) -> bool:
        return item in (self.cfg["ball_style"], self.cfg["ring_style"], self.cfg["theme"], self.cfg["font_item"])

    def apply_font(self, rebuild: bool = False) -> None:
        from .cosmetics import font_families
        item = self.cfg["font_item"]
        want = (font_families(item) if item and self.wallet.owns("font:" + item) else []) + list(FONT_DEFAULT)
        if want != FONT_FAMILIES:
            FONT_FAMILIES[:] = want
            if rebuild:
                self.rebuild_ui()

    def title_colour(self) -> str:
        """The colour of the song title: white, or the colour of the font you bought."""
        from .cosmetics import SHOP_COLOURS
        item = self.cfg["font_item"]
        if item and self.wallet.owns("font:" + item):
            var = item.split(":")[-1]
            return "#C9D2DA" if var in ("black", "grey") else SHOP_COLOURS.get(var, TEXT)
        return TEXT

    def _shop_items_check(self) -> None:
        """Something worn from the shop was sold or traded away: back to the normal look."""
        if not self.econ.ready:
            return
        changed = False
        for key, kind, plain in (("ball_style", "ball", "classic"), ("ring_style", "line", "line"),
                                 ("theme", "theme", "clean"), ("font_item", "font", "")):
            value = self.cfg[key]
            if value.startswith(kind + ":") and not self.econ.owns(value):
                self.cfg[key] = plain
                changed = True
                if kind == "font":
                    self.apply_font(rebuild=True)
        if changed:
            self._theme_changed()
            self.refresh_accent()
            self.window.ball.update()

    def faces_changed(self) -> None:
        """A picture arrived: repaint every page that is on screen (4.0: also Games, Shop and dialogs, which
        show faces too)."""
        if not self.window.expanded:
            return
        for key, entry in list(self.window.pages.items()):
            page = entry[1]
            if not page.isVisible():
                continue
            page.update()
            for w in page.findChildren(QWidget):
                if w.isVisible():
                    w.update()

    def _trade_changed(self) -> None:
        if self.window.showing("friends") and self.window.expanded:
            self.reload_page("friends")

    def _xp_first(self) -> None:
        """The first time levels reach this PC: explain them once, then the OG coupon (if any) opens."""
        if getattr(self, "_xp_intro_on", False):
            return
        if self.cfg["xp_intro"]:
            return self.offer_og_coupon()
        if not self.online.logged_in() or not self.window.expanded or getattr(self.window, "sheet", None) is not None:
            return                                   # asked again at the next XP update
        self._xp_intro_on = True

        def show() -> None:
            from .levels import LevelIntro
            if self.cfg["xp_intro"] or not self.window.expanded:
                self._xp_intro_on = False
                return
            intro = LevelIntro(self)
            intro.destroyed.connect(lambda *_a: setattr(self, "_xp_intro_on", False))
            self.window.embed(intro)
        QTimer.singleShot(1200, show)

    def offer_og_coupon(self) -> None:
        """OG players: their one-time XP coupon (to level 5) opens like a scratch card, once per session at most
        until it is used. It stays in Inventory > Levels if they close it."""
        if getattr(self, "_og_offered", False) or not self.window.expanded:
            return
        og = next((it for it in self.econ.items if it.get("item") == "coupon:og" and not it.get("locked")), None)
        if og is None:
            if self.econ.ready and self.econ.items:
                self._xp_watch.stop()                # nothing more to offer: the watch is over
            return
        self._og_offered = True
        from .levels import open_coupon
        QTimer.singleShot(600, lambda: open_coupon(self, og["id"], "coupon:og"))

    def _locks_changed(self) -> None:
        """Show what is paused right away (the server already refuses it). A game being played is not rebuilt: its
        next move gets the server's answer."""
        self.window.sync_lock()
        for key in ("games", "themes", "friends"):
            if key == "games" and (self.casino or getattr(self, "games_sub", None) in ("blocks", "sweeper", "memory",
                                                                                     "duel_run")):
                continue
            if self.window.showing(key):
                self.reload_page(key)

    def _live_changed(self) -> None:
        """Giveaways, the admin tab, the lock: from the server's latest news."""
        from .pages2 import LIVE_TABS
        want = set()
        ended = getattr(self, "_gw_ended", None)
        if ended is None:
            ended = self._gw_ended = {}
        now = time.monotonic()
        seen = self.__dict__.setdefault("_gw_seen_live", set())
        for g in self.econ.live.get("giveaways") or []:
            if g.get("state") == "live":
                want.add("giveaway")
                seen.add(g.get("id"))
            elif g.get("id") in seen:                   # just ended: the tab stays a minute to show the winner
                if g.get("id") not in ended:
                    ended[g.get("id")] = now
                    QTimer.singleShot(61000, self._live_changed)
                if now - ended[g.get("id")] < 60:
                    want.add("giveaway")
        if self.econ.admin:
            want.add("admin")
        if want != LIVE_TABS:
            LIVE_TABS.clear()
            LIVE_TABS.update(want)
            if not self.online_mode and self.window.current in ("giveaway", "admin") and self.window.current not in want:
                self.window.goto("home")
            self.window.tabs_changed()
            if self.main_window is not self.window:
                self.main_window.tabs_changed()
        self.window.sync_lock()
        for key in ("giveaway", "themes"):            # 3.2: the online menu may show both at once
            if not self.window.showing(key) or self.econ.holding:
                continue
            if key == "themes" and getattr(self, "shop_tab", 0) not in (1, 4):
                continue
            cur = (self.window.pages.get(key) or (None, None))[1]
            if cur is None or not getattr(cur, "reel", None) or not cur.reel.busy():
                self.reload_page(key)

    def notice(self, kind: str, data: dict) -> None:
        """A small message from the server (a gift, a giveaway win, something from the admin)."""
        if self.notifier.notice(kind, data):
            return
        from .collection import CASE_NAMES
        from .cosmetics import item_name
        from .wallet import coins_text
        if kind == "gift":
            text = tr("{name} gifted you a case: {case}", name=data.get("from", "?"), case=tr(CASE_NAMES.get(data.get("case"), "?")))
        elif kind == "giveaway":
            text = tr("You won the giveaway: {title}!", title=data.get("title", ""))
        elif data.get("item"):
            text = tr("You received: {what}", what=item_name(data["item"]))
        elif data.get("case"):
            text = tr("You received: {what}", what=tr(CASE_NAMES.get(data.get("case"), "?")))
        else:
            got = []
            if int(data.get("coins") or 0):
                got.append(tr("{n} coins", n=coins_text(data["coins"])))
            if int(data.get("keys") or 0):
                got.append(tr("{n} keys", n=data["keys"]))
            text = tr("You received: {what}", what=", ".join(got) or "?")
        sfx.play("on")
        self.toast(text)
        self.notifier.push("gift", tr("GIFT") if kind == "gift" else (tr("GIVEAWAY") if kind == "giveaway" else "RUBENIUM"), text,
                           "cases" if kind == "gift" else "inventory")

    def refresh_look(self) -> None:
        self.window._retime()
        self._sync_audio()
        self.on_visibility()
        self.window.update()
        self.window.ball.update()

    def ball_style(self) -> str:
        return self.cfg["ball_style"] if self.wallet.owns(f"r:{self.cfg['ball_style']}") else "classic"

    def ring_style(self) -> str:
        return self.cfg["ring_style"] if self.wallet.owns(f"ring:{self.cfg['ring_style']}") else "line"

    def set_look(self, key: str, value: int) -> None:
        """Ball size, glow strength, background and corners (Settings and Themes)."""
        if self.cfg[key] == value:
            return
        self.cfg[key] = value
        apply_look(self.cfg)
        w = self.window
        w.ball.clamp()
        w.ball.place()
        w.update()
        w.ball.update()
        if w.body.isVisible():
            w.body.update()

    def set_tab(self, key: str, on: bool) -> None:
        """Show or hide one tab of the menu bar."""
        if key == "new":                            # off unless the user asks for it
            self.cfg["news_tab"] = on
            return self.window.tabs_changed()
        off = dict(self.cfg["tabs_off"])
        if on:
            off.pop(key, None)
        else:
            off[key] = True
        self.cfg["tabs_off"] = off
        self.window.tabs_changed()

    def set_scale(self, pct: int) -> None:
        if pct != self.cfg["scale"]:
            self.cfg["scale"] = pct
            ui.scale = pct / 100
            self.rebuild_ui()

    def set_language(self, code: str) -> None:
        self.cfg["lang"] = code
        set_lang(code)
        self.rebuild_ui()
        if self.tray is not None:
            self.tray.hide()
            self.tray.deleteLater()
            self._make_tray()

    def rebuild_ui(self) -> None:
        QTimer.singleShot(0, self._rebuild)           # never rebuild from inside a widget's own signal

    def _rebuild(self) -> None:
        self.window.rebuild()
        self.apply_overlays()

    def apps(self, force: bool = False) -> list:
        if self._apps is None or force:
            self._apps = extras.scan_apps()
        return self._apps

    def apply_timer(self) -> None:
        self.timer_overlay.refresh()
        self.hotkeys.apply(self.cfg["timer"]["keys"])

    def _on_key(self, name: str) -> None:
        if name == "panic":
            self.display.panic()
        elif name == "timer_split":
            self.timer.start_split()
        elif name == "timer_pause":
            self.timer.pause()
        elif name == "timer_reset":
            self.timer.reset()

    # Rocket League swaps: the engine works in a thread, this side shows the loading screen and results
    def rocket_apply(self, desired: dict, reload: bool) -> None:
        if self.rocket.apply(desired, reload=reload):
            self.window.show_busy(tr("Closing Rocket League…") if reload else tr("Applying…"))

    def _rocket_busy(self, step: str) -> None:
        if self.window.busy_w.isVisible():
            self.window.show_busy(tr("Closing Rocket League…") if step == "close" else tr("Applying…"))

    def _rocket_done(self, ok: bool, key: str, info: dict) -> None:
        if info.get("quiet"):
            if ok:
                self.toast(tr("Swaps applied again after a Rocket League update"))
                if self.tray is not None and not self.window.expanded:
                    self.tray.showMessage("Rubenium", tr("Swaps applied again after a Rocket League update"),
                                          QSystemTrayIcon.MessageIcon.Information, 4000)
            return
        messages = {
            "ok": tr("Done"),
            "running": tr("Close Rocket League first"),
            "missing": tr("A game file is missing. Repair the game in Epic or Steam."),
            "nofile": tr("The swap file is missing"),
            "nobackup": tr("The original file is missing. Repair the game in Epic or Steam."),
            "nogame": tr("Rocket League not found"),
            "blocked": tr("Windows blocked the change"),
            "error": tr("Something went wrong. Try again."),
        }

        def after() -> None:
            if self.window.current == "rl":
                self.window.reload_page()
            if key == "blocked":
                self.window.confirm(tr("Windows blocked the change"), self._as_admin, yes=tr("Run as admin"),
                                    no=tr("Cancel"))
            else:
                self.toast(messages.get(key, key), "ok" if ok else "error")
        if ok and info.get("reload"):
            self.window.show_busy(tr("Starting Rocket League…"))
            self.rocket.launch(info.get("plat", ""))
        self.window.end_busy(after)

    def _rocket_changed(self) -> None:
        page = self.window.page()
        if page is not None and getattr(page, "pending", None) is not None:
            return                                  # never drop changes the user is waiting to apply
        if self.window.current == "rl" and self.window.expanded and not self.rocket.working:
            self.window.reload_page()

    def _as_admin(self) -> None:
        if win.relaunch_as_admin():
            self.quit()
        else:
            self.toast(tr("Windows blocked the change"), "error")

    # updates: found -> ask once (on the card), install -> verify -> restart
    # ------------------------------------------------------------------ 2.4
    def _game_running(self) -> bool:
        """A casino round or a mini game is being played on the open page."""
        page = self.window.page() if self.window.expanded else None
        if page is None:
            return False
        from PyQt6.QtWidgets import QWidget
        return any(getattr(w, "busy", False) is True for w in page.findChildren(QWidget))

    def set_offline_mode(self, on: bool) -> bool:
        """Offline mode: Rubenium makes no internet request. It cannot be used to dodge anything: it can only be
        switched on between games, cases and trades, at most once a minute, and the time spent offline earns
        nothing (the server only counts minutes it hears about). Returns False when the switch was refused."""
        on = bool(on)
        if on == bool(self.cfg["offline_mode"]):
            return True
        now = time.monotonic()
        if on:
            if not self.online.logged_in():
                self.toast(tr("Log in first"), "warn")
                return False
            busy = (self.econ.holding or bool(self.trade.trade_id)
                    or getattr(self, "games_sub", None) == "duel_run" or self._game_running())
            if busy:
                self.toast(tr("Finish what you are doing first"), "warn")
                return False
            wait = 60 - (now - getattr(self, "_offline_switched", -1e9))
            if wait > 0:
                self.toast(tr("Wait {s} s", s=int(wait) + 1), "warn")
                return False
        self._offline_switched = now
        self.cfg["offline_mode"] = on
        Net.blocked = on
        if on:
            self.online._set_offline(True)
            self.toast(tr("Offline mode on"))
        else:
            self.online.offline = False
            self.online.changed.emit()
            self.online.ask("rb_song_share", {"share": bool(self.cfg["share_songs"])}, lambda ok, d: None)
            self.online._tick()
            self.econ.refresh()
            self.econ.poll_live()
            self.econ.fetch_looks(force=True)
            self.toast(tr("Back online"))
        sfx.play("on" if not on else "off")
        self.window.sync_lock()
        if self.window.expanded:
            self.reload_page()
        return True

    def _tap_key(self) -> None:
        if self.window.expanded:
            self.window.collapse()
        else:
            self.window.expand()

    def set_outdated(self, on: bool) -> None:
        """Online games, trades and the market wait until Rubenium is up to date."""
        if on != self.outdated:
            self.outdated = on
            self.window.sync_lock()

    def og_event_check(self) -> None:
        """The OG event (16/11/2026): asked once per start, after the login is complete and the welcome screen is gone.
        The server decides (OG tag, the date, only once) and gives the rewards; then the cutscene plays."""
        if getattr(self, "_og_asked", False) or not self.online.logged_in() or self.cfg["offline_mode"]:
            return
        if self.welcome is not None:
            return QTimer.singleShot(1500, self.og_event_check)
        self._og_asked = True

        def got(ok: bool, data) -> None:
            if ok and isinstance(data, dict) and data.get("given"):
                from .ogevent import OgCutscene
                self.econ.gold_keys = int(data.get("gold_keys") or 0) + self.econ.gold_keys
                self._og_scene = OgCutscene(self, data)
                self._og_scene.show()
                self._og_scene.raise_()
        self.online.ask("rb_og_event", {}, got)

    def check_gold_wheels(self) -> None:
        """A Golden Wheel won earlier and never spun opens once the menu is ready."""
        if not self.online.logged_in() or self.cfg["offline_mode"]:
            return
        if self.welcome is not None:
            return QTimer.singleShot(2000, self.check_gold_wheels)
        from .goldwheel import check_gold_wheels
        check_gold_wheels(self)

    def after_login(self) -> None:
        """Once logged in: a quiet online backup each day. The tour and the daily reward wait until the menu is
        opened (never on top of a game)."""
        from .hub import backup_to_cloud
        self.tour_pending = not self.cfg["tutorial_done"]
        self.login_pending = True
        if self.window.expanded:
            self.on_opened()
        if time.time() - int(self.cfg["backup_at"] or 0) > 86400:
            backup_to_cloud(self, quiet=True)

    def on_opened(self) -> None:
        """The menu just opened: first the tour (the first time), then the daily reward if it is waiting."""
        from .hub import check_login_reward
        if not self.window.expanded or getattr(self.window, "sheet", None) is not None:
            return
        if getattr(self, "tour_pending", False):
            from .music2 import Tutorial
            self.tour_pending = False
            self._tour = Tutorial(self, lambda: QTimer.singleShot(300, self.on_opened))
            return
        if getattr(self, "login_pending", False) and self.online.logged_in() and self.online_mode:
            today = time.strftime("%Y-%m-%d")             # 4.4: the daily reward opens in online mode, once a day
            if self.cfg["daily_shown"] != today:
                self.cfg["daily_shown"] = today
                self.login_pending = False
                check_login_reward(self)

    def start_tutorial(self) -> None:
        from .music2 import Tutorial
        if not self.window.expanded:
            self.window.expand()
        QTimer.singleShot(450, lambda: setattr(self, "_tour", Tutorial(self)))

    def change_password_dialog(self) -> None:
        from .bazaar import AskDialog

        def got(pw: str, dlg) -> None:
            if len(pw) < 8:
                return dlg.say(tr("Password too short (8 or more)"))

            def done(ok: bool, msg) -> None:
                if not ok:
                    return dlg.say(tr(str(msg)))
                dlg.close()
                self.toast(tr("Password changed"))
            self.online.change_password(pw, done)
        self._ask = AskDialog(self, tr("Change password"), tr("New password (8 or more)"), tr("Change"), got, 72)
        self._ask.edit.setEchoMode(self._ask.edit.EchoMode.Password)

    def apply_restored(self) -> None:
        self.apply_config()
        self.tapkey.set_key(self.cfg["hotkey"])

    def _update_found(self, info: dict) -> None:
        """4.4: a new version installs by itself, straight away: no question (an old version can't play online)."""
        self.set_outdated(True)
        if self.window.current == "settings" and self.window.expanded:
            self.window.reload_page()
        self.offer_update()

    def offer_update(self) -> None:
        info = self.updater.latest
        if not info or self._update_prompted == info["version"] or self.updater.busy:
            return
        self._update_prompted = info["version"]
        if self.tray is not None and not self.window.expanded:
            self.tray.showMessage("Rubenium", tr("Updating to {v}…", v=info["label"]),
                                  QSystemTrayIcon.MessageIcon.Information, 4000)
        else:
            self.toast(tr("Updating to {v}…", v=info["label"]))
        self.install_update()

    def install_update(self) -> None:
        if self.updater.install():
            self.window.show_busy(tr("Downloading update… {p}%", p=0))

    def _update_checked(self, ok: bool, key: str) -> None:
        if key == "latest":
            self.toast(tr("Rubenium is up to date"))
        elif key == "offline":
            self.toast(tr("Could not check for updates"), "warn")

    def _update_ready(self, path: str) -> None:
        self.window.show_busy(tr("Restarting…"))
        started = extras.run_setup(path) if path.lower().endswith(".exe") else extras.restart(path)
        if started:
            QTimer.singleShot(400, self.quit)        # the setup waits for Rubenium to close, then installs
        else:
            self.window.end_busy(lambda: self.toast(tr("Update installed. Restart Rubenium."), "ok"))

    def _update_failed(self, key: str) -> None:
        self._update_prompted = ""                   # 4.4: the next check tries again by itself

        def after() -> None:
            if key == "blocked":
                self.toast(tr("Windows blocked the update. Download it from GitHub."), "error")
                win.open_path(self.updater.latest.get("page", extras.UPDATE_PAGE))
            else:
                self.toast(tr("The update failed. Try again in a moment."), "error")
        self.window.end_busy(after)

    def apply_config(self) -> None:
        """A whole new config was loaded (restore / reset)."""
        self.apply_timer()
        set_lang(self.cfg["lang"] or "en")
        apply_look(self.cfg)
        sfx.enabled = bool(self.cfg["sounds"])
        self.media.set_preferred(self.cfg["source"])
        self.refresh_accent()
        self.rebuild_ui()

    # ------------------------------------------------------------------ actions
    def toast(self, text: str, kind: str = "ok") -> None:
        self.window.toast(text, kind)

    def goto(self, key: str) -> None:
        self.window.goto(key)

    def reload_page(self, key: str = None) -> None:
        """Rebuild a page: the current one, or (3.2) the one named, wherever it is shown."""
        QTimer.singleShot(0, lambda: self.window.reload_page(key))

    # ------------------------------------------------------------------ 3.2: online mode
    def enter_online(self, focus: str = None) -> None:
        """The ONLINE button: the menu folds into the ball, the ball flies up off the screen and the online menu
        drops down from the top."""
        if self.online_mode:
            if focus:
                self.window.goto(focus)
            return
        if getattr(self, "_online_busy", False) or self.welcome is not None:
            return
        if not self.online.logged_in():
            return self.toast(tr("Log in first"), "warn")
        main = self.main_window
        self._online_busy = True
        self._online_back_open = main.expanded
        if focus in ("games", "themes", "friends", "giveaway"):
            self.cfg["online_tab"] = focus if focus != "giveaway" else self.cfg["online_tab"]
        if focus == "admin":                       # 4.4: the admin panel opens in the right half, full size
            left = next((k for k in (self.cfg["online_panes"] or []) if k in ("games", "themes")), "games")
            self.cfg["online_panes"] = [left, "admin"]
        from .onlinewin import fly_up, online_window

        state = {"dropped": False}

        def back_home() -> None:
            """4.1: the online menu could not open: never leave the user without the R."""
            self._online_busy = False
            self.online_mode = False
            self.window = main
            try:
                if self._online_win is not None:
                    self._online_win.hide()
            except Exception:  # noqa: BLE001
                pass
            main.ball.set_center(main.ball.center)
            main.show_ball()

        def drop() -> None:
            if state["dropped"]:
                return
            state["dropped"] = True
            self._online_busy = False
            try:
                self._online_win.open()
            except Exception:  # noqa: BLE001
                log.exception("online menu failed to open")
                return back_home()
            self.econ.poll_live()
            self.login_pending = True                  # 4.4: the first visit of the day shows the daily reward
            QTimer.singleShot(1200, self.on_opened)

        def fly() -> None:
            try:
                if self._online_win is None:
                    self._online_win = online_window(self, main)
                ow = self._online_win
                if focus:
                    ow.current = focus
                self.online_mode = True
                self.window = ow
                fly_up(self, main, drop)
            except Exception:  # noqa: BLE001
                log.exception("entering online mode failed")
                state["dropped"] = True
                back_home()

        def watchdog() -> None:
            if not state["dropped"]:
                log.warning("entering online mode did not finish, forcing it")
                drop() if self.online_mode and self._online_win is not None else back_home()
        QTimer.singleShot(4000, watchdog)
        if main.expanded:
            main.collapse()
            QTimer.singleShot(340, fly)
        else:
            fly()

    def leave_online(self, after=None, ask: bool = True) -> None:
        """The back arrow: tell what leaving would close (lobbies, a live match, a giveaway entry) and ask once; then
        the black hole takes the banner and the ball floats back down to where it lives."""
        if not self.online_mode or getattr(self, "_online_busy", False):
            return
        ow = self._online_win
        if not ask or not self.online.logged_in() or self.cfg["offline_mode"]:
            return self._leave_now(after, cancel=False)

        def got(ok: bool, st) -> None:
            if not ok or not isinstance(st, dict):
                return self._leave_now(after, cancel=False)
            lines = []
            if st.get("flip_open"):
                lines.append(tr("Your Coinflip lobby will close and your items come back."))
            if st.get("flip_joined"):
                lines.append(tr("You will leave the Coinflip you joined."))
            if st.get("golf_open"):
                lines.append(tr("Your Mini Golf lobby will close and your bet comes back."))
            if st.get("golf_live"):
                lines.append(tr("You will forfeit your live Mini Golf match."))
            gws = list(st.get("giveaways") or [])
            if gws:
                lines.append(tr("You will leave the giveaway: {t}.", t=", ".join(str(g) for g in gws[:2])))
            if not lines:
                return self._leave_now(after, cancel=False)
            if len(lines) == 1:
                text = tr("Leave online mode?") + " " + lines[0]
            else:
                text = tr("Leave online mode? This will be cancelled:") + "\n• " + "\n• ".join(lines)
            ow.confirm(text, lambda: self._leave_now(after, cancel=True), yes=tr("Leave"), no=tr("Stay"))
        self.online.ask("rb_online_status", {}, got)

    def _leave_now(self, after=None, cancel: bool = True) -> None:
        if not self.online_mode or getattr(self, "_online_busy", False):
            return
        self._online_busy = True
        ow, main = self._online_win, self.main_window
        if cancel:
            def left(ok: bool, data) -> None:
                if ok:
                    self.econ.refresh()
                    self.golf_lobby = self.flip_data = None
            self.online.ask("rb_online_leave", {}, left)
        from .onlinewin import float_down
        done = {"gone": False, "home": False}

        def home() -> None:
            # 4.1: whatever happens on the way (an effect that never ends, a page that fails), the R always comes
            # back: this runs once, from the animation or from the watchdog below.
            if done["home"]:
                return
            done["home"] = True
            self._online_busy = False
            try:
                main.ball.set_center(main.ball.center)
                main.show_ball()
            except Exception:  # noqa: BLE001
                log.exception("ball back failed")
                main.ball.show()
            try:
                if after is not None:
                    after()
                elif self._online_back_open:
                    main.expand()
            finally:
                self.on_visibility()

        def gone() -> None:
            if done["gone"]:
                return
            done["gone"] = True
            self.online_mode = False
            self.window = main
            self.cfg["card_open"] = False
            try:
                ow.hide()
                ow.ball.hide()
            except Exception:  # noqa: BLE001
                pass
            try:
                float_down(self, main, home)
            except Exception:  # noqa: BLE001
                log.exception("float down failed")
                home()

        def watchdog() -> None:
            if not done["gone"]:
                log.warning("leaving online mode did not finish, forcing it")
                gone()
            if not done["home"]:
                home()
        QTimer.singleShot(4000, watchdog)
        try:
            ow.start_leaving(gone)
        except Exception:  # noqa: BLE001
            log.exception("leaving online mode failed")
            gone()

    def pick_file(self, title: str, pattern: str) -> str:
        return self.window.pick_file(title, pattern)

    def overlay_active(self) -> bool:
        return self.crosshair.isVisible() or self.hud.isVisible() or self.display.active

    def set_crosshair(self, on: bool) -> None:
        self.cfg["crosshair_on"] = on
        self.crosshair.refresh()
        self.window.ball.update()
        page = self.window.page()
        if page is not None and page.key == "crosshair" and self.window.expanded:
            page.on_show()

    def set_hud(self, on: bool) -> None:
        self.cfg["hud"]["on"] = on
        self.cfg.save()
        self.hud.refresh()
        self.window.ball.update()

    def _on_display_failed(self, what: str) -> None:
        self.toast(tr("Your screen refused this setting"), "error")

    # ------------------------------------------------------------------ shutdown
    def delete_account_dialog(self) -> None:
        from .window import DeleteDialog
        self._delete_dialog = DeleteDialog(self)

    def quit(self) -> None:
        self.shutdown()
        self.qapp.quit()

    def shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        log.info("Shutting down")
        try:
            self.admute.release()                    # never leave the music app muted
            if self.online_mode and self.online.logged_in():
                try:                                 # leaving the app while online closes your lobbies
                    from .online import _request
                    _request("/rest/v1/rpc/rb_online_leave", {}, self.online.s.get("access_token", ""), timeout=3)
                except Exception:  # noqa: BLE001
                    pass
            self._audio.stop()
            self._usage.stop()
            self.rocket.stop()
            self.wallet.stop()
            self.online.stop()
            self.updater.stop()
            self.hotkeys.close()
            self.tapkey.stop()
            self.timer_overlay.hide()
            self.meter.close()
            self.window.hide()
            self.window.ball.hide()
            if self.welcome is not None:
                self.welcome.phase = "done"
                self.welcome.hide()
            self.crosshair.hide()
            self.hud.hide()
            if self.tray is not None:
                self.tray.hide()
            self.display.shutdown()
            self.sensors.shutdown()
            self.media.stop()
            self.media.wait(3000)
        finally:
            self.cfg.flush()

    def _last_resort(self) -> None:
        try:
            if self.display.probed:
                self.display.restore()
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    setup_logging()
    if not win.single_instance(wait=8.0 if ("--elevated" in sys.argv or "--updated" in sys.argv) else 0.0):
        return 0
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    qapp = QApplication(sys.argv)
    qapp.setApplicationName(APP_NAME)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setStyleSheet(APP_QSS)
    qapp.setWindowIcon(app_icon())
    try:
        qapp._rubenium = App(qapp)      # kept alive for the lifetime of the event loop
    except Exception:  # noqa: BLE001
        log.exception("Rubenium could not start")
        if "--selftest" in sys.argv:
            return 1
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, "Rubenium could not start.\n\nDetails are in "
                                             "Documents\\Rubenium\\rubenium.log", "Rubenium", 0x10)
        except Exception:  # noqa: BLE001
            pass
        return 1
    return qapp.exec()
