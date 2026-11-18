# -*- coding: utf-8 -*-
"""Engines behind the tabs: display colour, crosshair overlay, sensors and the stats overlay.

Overlays are ordinary always-on-top, click-through, never-activated windows. They do not hook,
inject into or capture any game. They are visible over windowed and borderless-fullscreen games;
exclusive fullscreen draws over everything, so they cannot appear there.
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time

from PyQt6.QtCore import QObject, QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

from . import win
from .core import CROSSHAIR_DIR, RECOVERY_PATH, S, TEXT, TEXT_DIM, alpha, font, ui

log = logging.getLogger("rubenium.engines")

OVERLAY_FLAGS = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
                 | Qt.WindowType.NoDropShadowWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus
                 | Qt.WindowType.WindowTransparentForInput)


# --------------------------------------------------------------------------- #
# Display colour engine
# --------------------------------------------------------------------------- #
def build_ramp(pr: dict, base=None) -> list:
    """Gamma ramp (3 x 256, 0-65535) for brightness / contrast / gamma / shadow boost / RGB balance.
    It is applied on top of the screen's own ramp (`base`), so calibration and Night light are kept and
    the default values change nothing at all."""
    b, c, g, s = pr["brightness"] / 100, pr["contrast"] / 100, max(0.3, pr["gamma"] / 100), pr["shadow"] / 100
    gains = (pr["red"] / 100, pr["green"] / 100, pr["blue"] / 100)
    ramp = [[0] * 256 for _ in range(3)]
    for i in range(256):
        x = i / 255
        x += s * 1.2 * x * (1 - x) ** 3                 # lifts dark tones, leaves highlights alone
        x = (x - 0.5) * (1 + c * 0.6) + 0.5 + b * 0.25
        x = max(0.0, min(1.0, x)) ** (1 / g)
        for ch in range(3):
            y = max(0.0, min(1.0, x * gains[ch]))
            if base is not None:
                pos = y * 255
                lo = int(pos)
                hi = min(255, lo + 1)
                ramp[ch][i] = int(round(base[ch][lo] + (base[ch][hi] - base[ch][lo]) * (pos - lo)))
            else:
                ramp[ch][i] = int(round(y * 65535))
    return ramp


def ramp_neutral(pr: dict) -> bool:
    return (pr["brightness"] == 0 and pr["contrast"] == 0 and pr["gamma"] == 100 and pr["shadow"] == 0
            and pr["red"] == pr["green"] == pr["blue"] == 100)


def colour_matrix(saturation: float, hue_deg: float) -> list:
    """3x3 (column-vector) matrix: saturation then hue rotation, luminance preserving."""
    s = saturation
    lr, lg, lb = 0.213, 0.715, 0.072
    sat = [[lr * (1 - s) + s, lg * (1 - s), lb * (1 - s)],
           [lr * (1 - s), lg * (1 - s) + s, lb * (1 - s)],
           [lr * (1 - s), lg * (1 - s), lb * (1 - s) + s]]
    a = math.radians(hue_deg)
    c, n = math.cos(a), math.sin(a)
    hue = [[0.213 + c * 0.787 - n * 0.213, 0.715 - c * 0.715 - n * 0.715, 0.072 - c * 0.072 + n * 0.928],
           [0.213 - c * 0.213 + n * 0.143, 0.715 + c * 0.285 + n * 0.140, 0.072 - c * 0.072 - n * 0.283],
           [0.213 - c * 0.213 - n * 0.787, 0.715 - c * 0.715 + n * 0.715, 0.072 + c * 0.928 + n * 0.072]]
    return [[sum(hue[r][k] * sat[k][c2] for k in range(3)) for c2 in range(3)] for r in range(3)]


class DisplayEngine(QObject):
    """System-wide colour control. Everything is snapshotted first and restored on exit, crash or panic."""
    changed = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, cfg) -> None:
        super().__init__()
        self.cfg = cfg
        self.devices: list = []
        self.original: dict = {}
        self.gamma_ok = False
        self.mag_ok = False
        self.nv: win.NvVibrance | None = None
        self.probed = False
        self._mag_dirty = False
        self._gamma_dirty = False
        self._nv_dirty = False
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(16)
        self._debounce.timeout.connect(self._apply_now)

    # -- capability probe (lazy: only when the Display tab or an active profile needs it)
    def probe(self) -> None:
        if self.probed:
            return
        self.probed = True
        self.devices = [name for name, _ in win.display_devices()]
        self._recover_after_crash()
        good = bool(self.devices)
        for dev in self.devices:
            ramp = win.gamma_get(dev)
            if ramp is None or not win.gamma_set(dev, ramp):     # verified round trip
                good = False
                break
            self.original[dev] = ramp
        self.gamma_ok = good
        self.mag_ok = win.mag_available()
        self.nv = win.NvVibrance()
        log.info("display caps: gamma=%s mag=%s nvidia=%s", self.gamma_ok, self.mag_ok, self.nv.ok)

    def _recover_after_crash(self) -> None:
        try:
            data = json.loads(RECOVERY_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        log.warning("Previous session ended without restoring colours: restoring now")
        for dev, ramp in data.get("ramps", {}).items():
            win.gamma_set(dev, ramp)
        RECOVERY_PATH.unlink(missing_ok=True)

    def _write_recovery(self) -> None:
        if RECOVERY_PATH.exists() or not self.original:
            return
        try:
            RECOVERY_PATH.write_text(json.dumps({"ramps": self.original}), encoding="utf-8")
        except OSError:
            pass

    # -- state
    @property
    def manual(self) -> str:
        return self.cfg["display"]["active"]

    @property
    def effective(self) -> str:
        return self.manual

    @property
    def active(self) -> bool:
        return self.effective in ("A", "B")

    def set_active(self, name: str) -> None:
        self.cfg["display"]["active"] = name if name in ("A", "B") else "off"
        self.cfg.save()
        self.apply()
        self.changed.emit()

    def toggle_ab(self) -> str:
        self.set_active("B" if self.manual == "A" else "A")
        return self.manual

    def apply(self) -> None:
        self._debounce.start()

    def _apply_now(self) -> None:
        self.probe()
        name = self.effective
        if name not in ("A", "B"):
            self.restore(keep_state=True)
            return
        pr = self.cfg["display"][name]
        if self.gamma_ok:
            if ramp_neutral(pr):
                if self._gamma_dirty:
                    for dev, ramp in self.original.items():
                        win.gamma_set(dev, ramp)
                    self._gamma_dirty = False
            else:
                self._write_recovery()
                ok = all(win.gamma_set(dev, build_ramp(pr, self.original.get(dev))) for dev in self.devices)
                if ok:
                    self._gamma_dirty = True
                else:
                    self.failed.emit("gamma")
        if self.mag_ok:
            if pr["saturation"] == 100 and pr["hue"] == 0:
                if self._mag_dirty:
                    win.mag_set_matrix([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
                    self._mag_dirty = False
            elif win.mag_set_matrix(colour_matrix(pr["saturation"] / 100, pr["hue"])):
                self._mag_dirty = True
            else:
                self.failed.emit("matrix")
        if self.nv is not None and self.nv.ok:
            if pr["vibrance"] < 0 or pr["vibrance"] == self.nv_default():   # untouched: the PC keeps its own value
                if self._nv_dirty:
                    self.nv.restore()
                    self._nv_dirty = False
            elif self.nv.set_percent(pr["vibrance"]):
                self._nv_dirty = True
            else:
                self.failed.emit("vibrance")

    def nv_default(self) -> int:
        """The vibrance the PC had before Rubenium touched it (0-100 like the NVIDIA panel)."""
        nv = self.nv
        if nv is None or not nv.ok or not nv.original:
            return 50
        level = nv.original.get(0, nv.min)
        return int(round(50 + 50 * (level - nv.min) / max(1, nv.max - nv.min)))

    def restore(self, keep_state: bool = False) -> None:
        """Put the screen back exactly as it was found."""
        if self._gamma_dirty:
            for dev, ramp in self.original.items():
                win.gamma_set(dev, ramp)
            self._gamma_dirty = False
        if self._mag_dirty:
            win.mag_set_matrix([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
            self._mag_dirty = False
        if self._nv_dirty and self.nv is not None:
            self.nv.restore()
            self._nv_dirty = False
        RECOVERY_PATH.unlink(missing_ok=True)

    def panic(self) -> None:
        self.cfg["display"]["active"] = "off"
        self.cfg.save()
        self._debounce.stop()
        self.probe()
        self._gamma_dirty = self._mag_dirty = self._nv_dirty = True
        self.restore()
        self.changed.emit()

    def shutdown(self) -> None:
        self._debounce.stop()
        if self.probed:
            self.restore()
            win.mag_shutdown()


# --------------------------------------------------------------------------- #
# Crosshair
# --------------------------------------------------------------------------- #
_image_cache: dict = {}


def crosshair_image(name: str):
    if not name:
        return None
    path = CROSSHAIR_DIR / name
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return None
    hit = _image_cache.get(name)
    if hit and hit[0] == stamp:
        return hit[1]
    pm = QPixmap(str(path))
    if pm.isNull():
        return None
    _image_cache[name] = (stamp, pm)
    return pm


def crosshair_extent(c: dict) -> int:
    """Half-size in pixels needed to draw the crosshair."""
    if c.get("style") == "image" and crosshair_image(c.get("image", "")) is not None:     # 4.0: your own picture
        return int(c.get("image_px", 48)) // 2 + 3
    o = c["outline_w"] if c["outline"] else 0
    f = c.get("size", 100) / 100
    reach = (c["gap"] + c["length"]) * f
    if c["style"] == "circle":
        reach = max(reach if c["length"] else 0, c["radius"] * f + c["thickness"])
    if c["style"] == "dot":
        reach = c["dot_size"] * f
    return int(max(reach, c["dot_size"] * f) + o + 3)


def paint_crosshair(p: QPainter, c: dict, cx: float, cy: float, k: int = 1) -> None:
    """Draw the crosshair centred on (cx, cy); k is an integer zoom used by the preview."""
    if c.get("style") == "image":                   # 4.0: a picture of your own, at its size and opacity
        pm = crosshair_image(c.get("image", ""))
        if pm is not None:
            side = max(4, int(c.get("image_px", 48))) * k
            p.save()
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p.setOpacity(p.opacity() * max(0.1, c["opacity"] / 100))
            sc = pm.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            p.drawPixmap(int(cx - sc.width() / 2), int(cy - sc.height() / 2), sc)
            p.restore()
            return
    col = QColor(c["color"])
    col.setAlphaF(max(0.05, c["opacity"] / 100))
    black = QColor(0, 0, 0, int(col.alpha() * 0.9))
    f = c.get("size", 100) / 100                    # one "size" setting scales every part except thickness
    t, ln, gap = max(1, c["thickness"]) * k, round(c["length"] * f) * k, round(c["gap"] * f) * k
    o = (c["outline_w"] * k) if c["outline"] else 0
    ds = max(1, round(c["dot_size"] * f)) * k
    x0, y0 = int(cx) - t // 2, int(cy) - t // 2
    rects = []
    if c["style"] in ("cross", "tee") or (c["style"] == "circle" and ln > 0):
        rects += [QRectF(cx - gap - ln, y0, ln, t), QRectF(cx + gap, y0, ln, t), QRectF(x0, cy + gap, t, ln)]
        if c["style"] != "tee":
            rects.append(QRectF(x0, cy - gap - ln, t, ln))
    dot = c["dot"] or c["style"] == "dot"
    if dot:
        rects.append(QRectF(int(cx) - ds // 2 if ds % 2 == 0 else int(cx) - ds // 2, int(cy) - ds // 2, ds, ds))
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    p.setPen(Qt.PenStyle.NoPen)
    if o:
        p.setBrush(black)
        for r in rects:
            if r.width() > 0 and r.height() > 0:
                p.drawRect(r.adjusted(-o, -o, o, o))
    if c["style"] == "circle":
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rad = round(c["radius"] * f) * k
        p.setBrush(Qt.BrushStyle.NoBrush)
        if o:
            p.setPen(QPen(black, t + 2 * o))
            p.drawEllipse(QPointF(cx, cy), rad, rad)
        p.setPen(QPen(col, t))
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(col)
    for r in rects:
        if r.width() > 0 and r.height() > 0:
            p.drawRect(r)


class CrosshairOverlay(QWidget):
    """A tiny click-through window at the centre of the chosen monitor, drawn in physical pixels."""

    def __init__(self, cfg) -> None:
        super().__init__()
        self.cfg = cfg
        self.setWindowFlags(OVERLAY_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._phys = 64

    def refresh(self) -> None:
        if not self.cfg["crosshair_on"]:
            self.hide()
            return
        c = self.cfg["crosshair"]
        half = crosshair_extent(c)
        self._phys = half * 2
        mons = win.monitors()
        screens = QGuiApplication.screens()
        if mons:
            dev, mx, my, mw, mh, _prim = mons[min(c["monitor"], len(mons) - 1)]
            screen = next((s for s in screens if s.name() == dev), QGuiApplication.primaryScreen())
            dpr = screen.devicePixelRatio()
            g = screen.geometry()
            side = max(2, int(math.ceil(self._phys / dpr)))
            self.setGeometry(g.center().x() - side // 2, g.center().y() - side // 2, side, side)
            self.show()
            x = mx + mw // 2 - half + c["off_x"]
            y = my + mh // 2 - half + c["off_y"]
            win.make_overlay(int(self.winId()))
            win.place_physical(int(self.winId()), x, y, self._phys, self._phys)
        else:                                   # non-Windows development fallback
            screen = screens[min(c["monitor"], len(screens) - 1)]
            g = screen.geometry()
            self.setGeometry(g.center().x() - half + c["off_x"], g.center().y() - half + c["off_y"],
                             self._phys, self._phys)
            self.show()
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        dpr = self.devicePixelRatioF()
        p.scale(1 / dpr, 1 / dpr)
        w, h = round(self.width() * dpr), round(self.height() * dpr)
        paint_crosshair(p, self.cfg["crosshair"], w // 2, h // 2)


# --------------------------------------------------------------------------- #
# Sensors (only sampled while the Performance page or the HUD is visible)
# --------------------------------------------------------------------------- #
class Sensors(QObject):
    sample = pyqtSignal(dict)

    def __init__(self) -> None:
        super().__init__()
        self._users: set = set()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._psutil = None
        self.available = True
        self.nvml: win.Nvml | None = None
        self._net = None
        self._ping = None
        self._ping_busy = False
        self._n = 0
        self.last: dict = {}

    def acquire(self, who: str) -> None:
        self._users.add(who)
        if not self._timer.isActive():
            self._start()

    def release(self, who: str) -> None:
        self._users.discard(who)
        if not self._users:
            self._timer.stop()

    def _start(self) -> None:
        if self._psutil is None and self.available:
            try:
                import psutil
                self._psutil = psutil
                psutil.cpu_percent(None)
            except ImportError:
                self.available = False
        if self.nvml is None:
            self.nvml = win.Nvml()
        self._net = None
        self._timer.start()
        QTimer.singleShot(150, self._tick)

    def _ping_work(self) -> None:
        try:
            self._ping = win.ping_ms()
        finally:
            self._ping_busy = False

    def _tick(self) -> None:
        d: dict = {"cpu": None, "ram": None, "gpu": None, "vram": None, "temp": None,
                   "up": None, "down": None, "ping": self._ping}
        ps = self._psutil
        if ps is not None:
            try:
                d["cpu"] = ps.cpu_percent(None)
                vm = ps.virtual_memory()
                d["ram"] = vm.percent
                d["ram_used"], d["ram_total"] = vm.used / 2 ** 30, vm.total / 2 ** 30
                io, now = ps.net_io_counters(), time.monotonic()
                if self._net is not None:
                    dt = max(0.2, now - self._net[2])
                    d["up"] = max(0.0, (io.bytes_sent - self._net[0]) / dt)
                    d["down"] = max(0.0, (io.bytes_recv - self._net[1]) / dt)
                self._net = (io.bytes_sent, io.bytes_recv, now)
            except Exception as exc:  # noqa: BLE001
                log.debug("psutil sample failed: %s", exc)
        if self.nvml is not None and self.nvml.ok:
            r = self.nvml.read()
            if r:
                d["gpu"], d["vram"], d["temp"] = r[0], (r[1], r[2]), r[3]
        self._n += 1
        if self._n % 2 == 1 and not self._ping_busy and win.IS_WIN:
            self._ping_busy = True
            threading.Thread(target=self._ping_work, daemon=True).start()
        self.last = d
        self.sample.emit(d)

    def shutdown(self) -> None:
        self._timer.stop()
        if self.nvml is not None:
            self.nvml.close()


class HudOverlay(QWidget):
    """Click-through stats strip in a screen corner."""

    def __init__(self, cfg, sensors: Sensors) -> None:
        super().__init__()
        self.cfg, self.sensors = cfg, sensors
        self.setWindowFlags(OVERLAY_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._items: list = []
        sensors.sample.connect(self._on_sample)

    def refresh(self) -> None:
        if self.cfg["hud"]["on"]:
            self.sensors.acquire("hud")
            self._on_sample(self.sensors.last)
            self.show()
            win.make_overlay(int(self.winId()))
        else:
            self.sensors.release("hud")
            self.hide()

    def _on_sample(self, d: dict) -> None:
        if not self.cfg["hud"]["on"]:
            return
        h = self.cfg["hud"]
        items = []

        def val(v, suffix="%"):
            return "–" if v is None else f"{round(v)}{suffix}"

        if h["cpu"]:
            items.append(("CPU", val(d.get("cpu"))))
        if h["gpu"] and d.get("gpu") is not None:
            temp = f" {d['temp']}°" if d.get("temp") is not None else ""
            items.append(("GPU", val(d.get("gpu")) + temp))
        if h["ram"]:
            items.append(("RAM", val(d.get("ram"))))
        if h["ping"]:
            items.append(("PING", val(d.get("ping"), " ms")))
        if h["net"] and d.get("down") is not None:
            items.append(("NET", f"{d['down'] / 125000:.1f} Mb"))
        if h["clock"]:
            items.append(("", time.strftime("%H:%M")))
        self._items = items or [("", time.strftime("%H:%M"))]
        fm_l, fm_v = font(9, QFont.Weight.Bold, 0.5), font(12, QFont.Weight.DemiBold)
        from PyQt6.QtGui import QFontMetrics
        w = S(10)
        for label, value in self._items:
            w += QFontMetrics(fm_l).horizontalAdvance(label) + S(5) + QFontMetrics(fm_v).horizontalAdvance(value) + S(12)
        hgt = S(26)
        screen = QGuiApplication.primaryScreen()
        g = screen.geometry()
        m = S(10)
        corner = h["corner"]
        x = g.left() + m if corner in (0, 2) else g.right() - w - m
        y = g.top() + m if corner in (0, 1) else g.bottom() - hgt - m
        self.setGeometry(int(x), int(y), int(w), int(hgt))
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha(ui.accent, 0.5), 1))
        p.setBrush(QColor(10, 14, 15, 205))
        p.drawRoundedRect(r, S(8), S(8))
        x = S(10)
        fl, fv = font(9, QFont.Weight.Bold, 0.5), font(12, QFont.Weight.DemiBold)
        for label, value in self._items:
            p.setFont(fl)
            p.setPen(ui.accent)
            lw = p.fontMetrics().horizontalAdvance(label)
            p.drawText(QRectF(x, 0, lw + 2, self.height()), int(Qt.AlignmentFlag.AlignVCenter), label)
            x += lw + S(5)
            p.setFont(fv)
            p.setPen(QColor(TEXT))
            vw = p.fontMetrics().horizontalAdvance(value)
            p.drawText(QRectF(x, 0, vw + 2, self.height()), int(Qt.AlignmentFlag.AlignVCenter), value)
            x += vw + S(12)


# --------------------------------------------------------------------------- #
# Connection test (runs in a thread; the page only listens)
# --------------------------------------------------------------------------- #
PING_TARGETS = [("Cloudflare", (1, 1, 1, 1)), ("Google", (8, 8, 8, 8)), ("Quad9", (9, 9, 9, 9))]


class PingTest(QObject):
    """done([(name, average ms or None, jitter ms, lost %)])"""
    done = pyqtSignal(list)

    def __init__(self) -> None:
        super().__init__()
        self.busy = False
        self.last: list = []

    def start(self) -> bool:
        if self.busy:
            return False
        self.busy = True
        threading.Thread(target=self._work, daemon=True).start()
        return True

    def _work(self) -> None:
        out = []
        try:
            for name, ip in PING_TARGETS:
                times = []
                for _ in range(6):
                    times.append(win.ping_ms(ip, 800))
                    time.sleep(0.12)
                good = [t for t in times if t is not None]
                lost = round(100 * (len(times) - len(good)) / len(times))
                if good:
                    avg = sum(good) / len(good)
                    jitter = sum(abs(a - b) for a, b in zip(good, good[1:])) / max(1, len(good) - 1)
                    out.append((name, round(avg), round(jitter), lost))
                else:
                    out.append((name, None, 0, 100))
        finally:
            self.busy = False
            self.last = out
            self.done.emit(out)
