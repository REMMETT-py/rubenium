# -*- coding: utf-8 -*-
"""Rubenium core: constants, paths, config, theme tokens, metrics, localisation, logging."""
from __future__ import annotations

import copy
import json
import logging
import logging.handlers
import os
import shutil
import sys
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from . import win

APP_NAME = "Rubenium"
VERSION = "1.0.0"            # file version of the .exe and setup
VERSION_NAME = "2.0"         # the version people see
BUILD = "2026.11.15.9"       # release tag (a date). It only ever goes up: this is what the updater compares
log = logging.getLogger("rubenium")

# --------------------------------------------------------------------------- #
# Paths (one place for data)
# --------------------------------------------------------------------------- #
DOCS = win.documents_dir()
DATA_DIR = DOCS / "Rubenium"
CONFIG_PATH = DATA_DIR / "settings.json"          # one folder in Documents, kept across updates
OLD_CONFIG_PATH = DOCS / "RubeniumConfig.json"
BACKUP_DIR = DATA_DIR / "backups"
CROSSHAIR_DIR = DATA_DIR / "crosshairs"
LYRICS_DIR = DATA_DIR / "lyrics_cache"
LOG_PATH = DATA_DIR / "rubenium.log"
RECOVERY_PATH = DATA_DIR / "display_recovery.json"


def ensure_dirs() -> None:
    for d in (DATA_DIR, BACKUP_DIR, CROSSHAIR_DIR, LYRICS_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass


def setup_logging() -> None:
    ensure_dirs()
    level = logging.DEBUG if os.environ.get("RUBENIUM_DEBUG") else logging.INFO
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    try:
        fh = logging.handlers.RotatingFileHandler(LOG_PATH, maxBytes=512_000, backupCount=2, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass
    if sys.stderr is not None:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)
    sys.excepthook = lambda t, v, tb: log.critical("Unhandled exception", exc_info=(t, v, tb))


# --------------------------------------------------------------------------- #
# Theme tokens
# --------------------------------------------------------------------------- #
ACCENT_DEFAULT = "#FFFFFF"      # white: the free base colour
BG_TOP = "#0B0F10"
BG_BOTTOM = "#101415"
SURFACE = "#1A1F20"
SURFACE_HI = "#282828"
TEXT = "#FFFFFF"
TEXT_DIM = "#B3B3B3"
TEXT_FAINT = "#7C8385"
PLACEHOLDER = "#575757"
TRACK = "#3A3A3A"
DANGER = "#E5484D"
WARN = "#F5A524"
FONT_FAMILIES = ["Segoe UI Variable", "Segoe UI", "Helvetica Neue", "Arial"]


class _UI:
    """Live theme state: every widget reads these at paint time."""
    scale = 1.0
    accent = QColor(ACCENT_DEFAULT)
    accent2 = None          # optional second colour (QColor), mixed into the outline and the header
    bg_top = QColor(BG_TOP)
    bg_bottom = QColor(BG_BOTTOM)
    ball = 1.0              # size of the ball, on top of the UI scale
    radius = 18             # card corner radius at 100 %


ui = _UI()


def S(v: float) -> int:
    """Scale a 100 % design dimension to the current UI scale."""
    return int(round(v * ui.scale))


def font(px: float, weight: QFont.Weight = QFont.Weight.Normal, spacing: float = 0.0) -> QFont:
    f = QFont()
    f.setFamilies(FONT_FAMILIES)
    f.setPixelSize(max(6, S(px)))
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing * ui.scale)
    return f


def mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
        round(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def alpha(c: QColor | str, a: float) -> QColor:
    c = QColor(c)
    c.setAlphaF(max(0.0, min(1.0, a)))
    return c


# Metrics at 100 % (the window multiplies through S()).
CARD_W = 380
GLOW = 22
RADIUS = 18
PAD = 14
BALL = 56
BALL_SIZES = (80, 90, 100, 110, 120, 130, 140)     # per cent of BALL: never tiny, never huge
BACKDROPS = (("#0B0F10", "#101415"), ("#000000", "#050607"), ("#0E1218", "#141A22"))   # dark, black, night blue
CORNERS = (18, 12, 6)
GLOW_POWER = (0.65, 1.0, 1.4)
LOCKED_TABS = ("home", "lyrics", "settings")       # always shown


class Sfx:
    """Very quiet, soft interface sounds (switch on, switch off, pick). Made in code once, cached as .wav files.
    Only for things you change, never for hovering."""
    RATE = 44100
    SOUNDS = {          # (start Hz, end Hz, length s, loudness 0-1): low, round and short
        "on": (330.0, 440.0, 0.17, 0.050),
        "off": (392.0, 294.0, 0.16, 0.045),
        "pick": (494.0, 466.0, 0.09, 0.030),
    }

    def __init__(self) -> None:
        self.enabled = True
        self._files: dict = {}
        self._last = 0.0

    def _make(self, name: str) -> str:
        import math
        import struct
        import wave
        f0, f1, length, gain = self.SOUNDS[name]
        folder = DATA_DIR / "sounds"
        path = folder / f"{name}_2.wav"                 # bump the number when a sound changes
        if not path.is_file():
            folder.mkdir(parents=True, exist_ok=True)
            n = int(self.RATE * length)
            frames, phase = bytearray(), 0.0
            for i in range(n):
                t = i / n
                freq = f0 + (f1 - f0) * (1 - (1 - t) ** 3)          # glides, then settles
                phase += 2 * math.pi * freq / self.RATE
                attack = min(1.0, i / (0.018 * self.RATE))
                env = (0.5 - 0.5 * math.cos(math.pi * attack)) * math.exp(-4.2 * t) * min(1.0, (n - i) / (0.03 * self.RATE))
                v = math.sin(phase)                                       # a pure tone: nothing sharp in it
                frames += struct.pack("<h", int(max(-1.0, min(1.0, v * env * gain)) * 32767))
            tmp = path.with_suffix(".tmp")
            with wave.open(str(tmp), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(self.RATE)
                w.writeframes(bytes(frames))
            os.replace(tmp, path)
        return str(path)

    def play(self, name: str) -> None:
        if not self.enabled or name not in self.SOUNDS or not win.IS_WIN:
            return
        import time
        now = time.monotonic()
        if now - self._last < 0.03:                    # two widgets reacting to one click: one sound
            return
        self._last = now
        try:
            if name not in self._files:
                self._files[name] = self._make(name)
            win.play_sound(self._files[name])
        except OSError as exc:
            log.debug("sound %s failed: %s", name, exc)


sfx = Sfx()


def BD() -> int:
    """Diameter of the ball in pixels (UI scale x the ball size the user picked)."""
    return int(round(BALL * ui.scale * ui.ball))


def apply_look(cfg) -> None:
    """Copy the look settings into the live theme state."""
    ui.scale = cfg["scale"] / 100
    size = cfg["ball_size"] if cfg["ball_size"] in BALL_SIZES else 100
    ui.ball = size / 100
    top, bottom = BACKDROPS[1 if cfg["backdrop"] == 1 else 0]            # dark or black
    ui.bg_top, ui.bg_bottom = QColor(top), QColor(bottom)
    ui.radius = CORNERS[2 if cfg["corners"] == 2 else 0]                 # round or sharp
HEADER_H = 26
TABBAR_H = 34
PAGE_HEIGHTS = {  # content heights at 100 %; tall pages scroll when the screen is small
    "friends": 300,
    "home": 138, "lyrics": 262, "crosshair": 520, "display": 520,
    "perf": 452, "tools": 468, "rl": 440, "settings": 480,
}

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
DISPLAY_PROFILE = {"brightness": 0, "contrast": 0, "gamma": 100, "shadow": 0,
                   "red": 100, "green": 100, "blue": 100,
                   "saturation": 100, "hue": 0, "vibrance": -1}       # -1: keep the PC's own vibrance
CROSSHAIR = {"style": "cross", "color": "#FFFFFF", "opacity": 100, "size": 100, "length": 5, "thickness": 2,
             "gap": 3, "dot": False, "dot_size": 2, "outline": True, "outline_w": 1,
             "radius": 10, "image": "", "image_scale": 100, "monitor": 0, "off_x": 0, "off_y": 0}

DEFAULTS: dict = {
    "schema": 3,
    "lang": "",
    "scale": 100,
    "opacity": 100,
    "ball_size": 100,
    "glow_power": 2,
    "backdrop": 1,
    "corners": 0,
    "ball_style": "classic",
    "ring_style": "line",
    "casino_warned": False,
    "news_tab": False,
    "welcome": True,
    "sounds": True,
    "accent2": "#B56BFF",
    "accent2_on": False,
    "splash": True,
    "badges": [],
    "game": 0,
    "scale_before_games": 0,
    "hold_open": True,
    "hold_ms": 400,
    "unlock_all": False,
    "card_open": False,
    "seen_version": "",
    "tabs_off": {},
    "halo": True,
    "autohide": True,
    "ring": True,
    "accent_from_art": True,
    "custom_accent": "",
    "theme": "clean",
    "usage_s": 0.0,
    "timer": {"overlay": False, "keys": True, "best": 0.0},
    "volume_seen": False,
    "update_check": True,
    "autostart": None,
    "source": "",
    "page": "home",
    "ball": {"screen": "", "nx": -1.0, "ny": -1.0},
    "card": {"screen": "", "nx": -1.0, "ny": -1.0},
    "crosshair_on": False,
    "crosshair": dict(CROSSHAIR),
    "crosshair_presets": {},
    "crosshair_slot": 0,
    "display": {"active": "off", "A": dict(DISPLAY_PROFILE), "B": dict(DISPLAY_PROFILE)},
    "hud": {"on": False, "corner": 0, "cpu": True, "gpu": True, "ram": True, "ping": True, "net": False, "clock": False},
    "tools": {"gaming": False, "saved": {}},
    "rl": {"auto_fix": True, "platform": "", "installs": {},
           "folder": "", "app": "", "active": {}, "orig": {}, "stamp": ""},      # last line: 2.0, migrated
}
FREE_DICTS = {"tabs_off", "saved", "slots", "crosshair_presets", "active", "orig", "installs"}   # dicts whose keys are user data


def _merge(default, loaded, key=""):
    """Per-key fallback to defaults: a wrong type or missing key never crashes the app."""
    if isinstance(default, dict):
        if not isinstance(loaded, dict):
            return copy.deepcopy(default)
        if key in FREE_DICTS:
            return copy.deepcopy(loaded)
        return {k: _merge(v, loaded.get(k), k) for k, v in default.items()}
    if default is None:
        return loaded if isinstance(loaded, (bool, type(None))) else None
    if isinstance(default, bool):
        return loaded if isinstance(loaded, bool) else default
    if isinstance(default, (int, float)):
        if isinstance(loaded, (int, float)) and not isinstance(loaded, bool):
            return type(default)(loaded)
        return default
    if isinstance(default, str):
        return loaded if isinstance(loaded, str) else default
    if isinstance(default, list) and isinstance(loaded, list):
        return [x for x in loaded if isinstance(x, (str, int, float))]
    return copy.deepcopy(default)


class Config(QObject):
    """Settings in Documents/Rubenium/settings.json: atomic, debounced, self-healing.
    Unknown keys are ignored and missing keys take their default, so any version can read any file."""
    changed = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.d: dict = copy.deepcopy(DEFAULTS)
        self.legacy_xy = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self.flush)
        self.load()

    def __getitem__(self, k):
        return self.d[k]

    def __setitem__(self, k, v):
        self.d[k] = v
        self.save()

    def load(self) -> None:
        ensure_dirs()
        raw = None
        if CONFIG_PATH.exists():
            try:
                raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                log.warning("Config unreadable (%s); trying newest backup", exc)
                for b in sorted(BACKUP_DIR.glob("RubeniumConfig-*.json"), reverse=True):
                    try:
                        raw = json.loads(b.read_text(encoding="utf-8"))
                        break
                    except (OSError, ValueError):
                        continue
        elif OLD_CONFIG_PATH.exists():                 # first version kept its file loose in Documents
            try:
                raw = json.loads(OLD_CONFIG_PATH.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raw = None
        else:
            raw = self._migrate_legacy()
        self.d = _merge(DEFAULTS, raw if isinstance(raw, dict) else {})
        d = self.d
        d["scale"] = int(min(150, max(70, round(d["scale"] / 10) * 10)))
        d["opacity"] = 100
        if d["crosshair"]["style"] not in ("cross", "tee", "dot", "circle"):
            d["crosshair"]["style"] = "cross"
        d["crosshair"]["size"] = 100
        for slot in ("A", "B"):
            if isinstance(raw, dict) and raw.get("schema", 2) < 3 and d["display"][slot]["vibrance"] == 50:
                d["display"][slot]["vibrance"] = -1             # 1.x saved 50 meaning "default"
        if not CONFIG_PATH.exists():
            self.flush()
        self._backup()

    def _migrate_legacy(self):
        """Import settings from Rubenify (never deletes the old files)."""
        out: dict = {}
        candidates = [DOCS / "RubenifyConfig.json", DOCS / "RubenSpotifyConfig.json"]
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "Rubenify" / "settings.json")
        for path in candidates:
            try:
                old = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(old, dict):
                continue
            log.info("Migrating settings from %s", path)
            if isinstance(old.get("glow"), bool):
                out["halo"] = old["glow"]
            for k in ("halo", "ring", "accent_from_art"):
                if isinstance(old.get(k), bool):
                    out[k] = old[k]
            op = old.get("opacity")
            if isinstance(op, (int, float)) and not isinstance(op, bool):
                out["opacity"] = int(op * 100) if op <= 1.0 else int(op)
            sc = old.get("scale")
            if isinstance(sc, (int, float)) and not isinstance(sc, bool):
                out["scale"] = int(sc * 100) if sc <= 3 else int(sc)
            if old.get("lang") in ("en", "fr"):
                out["lang"] = old["lang"]
            x, y = old.get("x"), old.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                self.legacy_xy = (int(x), int(y))
            break
        return out

    def _backup(self) -> None:
        try:
            if not CONFIG_PATH.exists():
                return
            target = BACKUP_DIR / f"RubeniumConfig-{time.strftime('%Y%m%d')}.json"
            if not target.exists():
                shutil.copy2(CONFIG_PATH, target)
            for old in sorted(BACKUP_DIR.glob("RubeniumConfig-*.json"), reverse=True)[5:]:
                old.unlink(missing_ok=True)
        except OSError as exc:
            log.debug("backup failed: %s", exc)

    def save(self) -> None:
        self._timer.start()

    def flush(self) -> None:
        self._timer.stop()
        try:
            ensure_dirs()
            tmp = CONFIG_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.d, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, CONFIG_PATH)
        except OSError as exc:
            log.warning("Could not save settings: %s", exc)

    def reset(self) -> None:
        keep = {k: self.d[k] for k in ("ball", "card", "lang", "autostart", "usage_s", "theme", "ball_style",
                                       "ring_style", "custom_accent", "accent2", "accent2_on", "accent_from_art",
                                       "badges", "seen_version")}       # what you bought stays on
        self.d = copy.deepcopy(DEFAULTS)
        self.d.update(keep)
        self.flush()


# --------------------------------------------------------------------------- #
# Localisation: English is the key, French lives in lang_fr.py
# --------------------------------------------------------------------------- #
_lang = "en"
_fr: dict = {}


def set_lang(code: str) -> None:
    global _lang, _fr
    _lang = "fr" if code == "fr" else "en"
    if _lang == "fr" and not _fr:
        from .lang_fr import FR
        _fr = FR


def lang() -> str:
    return _lang


def tr(text: str, **kw) -> str:
    out = _fr.get(text, text) if _lang == "fr" else text
    return out.format(**kw) if kw else out
