#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rubenium 1.0 - gamer command centre for Windows 10 / 11.  One file.

HOW TO RUN
  1. Install Python 3.10 - 3.13 from python.org (tick "Add python.exe to PATH").
  2. Double-click this file. The first time it installs what it needs (about a minute),
     then the glowing ball appears. Click it. After that it starts with Windows.

  Needs: PyQt6, psutil and the winrt-Windows.* packages (installed automatically).
  Settings live in Documents/Rubenium/settings.json.
  Keys: Ctrl+Alt+Shift+R = normal screen colours.  Ctrl+F1 / F2 / F3 = timer start-split / pause / reset.

The app never injects into, hooks or reads the memory of a game. Its overlays are normal
click-through windows, so they do not show over EXCLUSIVE fullscreen (use borderless).
"""
from __future__ import annotations

import os
import sys

_PACKAGES = ["PyQt6>=6.6", "psutil>=5.9"]
_WIN_PACKAGES = ["winrt-runtime>=2.3", "winrt-Windows.Foundation>=2.3", "winrt-Windows.Foundation.Collections>=2.3",
                 "winrt-Windows.Media>=2.3", "winrt-Windows.Media.Control>=2.3", "winrt-Windows.Storage.Streams>=2.3"]


def _bootstrap() -> None:
    """Install missing packages once, then restart without a console window."""
    if getattr(sys, "frozen", False):
        return
    import importlib.util
    import subprocess

    def has(name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            return False

    missing = [p for p, mod in zip(_PACKAGES, ("PyQt6", "psutil")) if not has(mod)]
    if sys.platform == "win32" and not (has("winrt.windows.media.control") and has("winrt.windows.storage.streams")
                                         and has("winrt.windows.foundation") and has("winrt.windows.media")):
        missing += _WIN_PACKAGES
    if missing and not os.environ.get("RUBENIUM_BOOT"):
        os.environ["RUBENIUM_BOOT"] = "1"
        print("Rubenium: installing what it needs (first start only)...")
        cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *missing]
        try:
            ok = subprocess.call(cmd) == 0
        except OSError:
            ok = False
        if not ok or not has("PyQt6"):
            text = "Rubenium could not install its packages.\n\nOpen a command prompt and run:\n\npip install " + " ".join(
                p.split(">=")[0] for p in missing)
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, text, "Rubenium", 0x10)
            except Exception:
                print(text)
            raise SystemExit(1)
    exe = sys.executable or ""
    if (sys.platform == "win32" and os.path.basename(exe).lower() == "python.exe" and "--console" not in sys.argv
            and not os.environ.get("RUBENIUM_DEBUG")):
        pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(pyw):                      # no black console window left open behind the app
            subprocess.Popen([pyw, os.path.abspath(sys.argv[0]), *sys.argv[1:]], close_fds=True)
            raise SystemExit(0)


if __name__ == "__main__":
    _bootstrap()

win = engines = extras = sys.modules[__name__]        # the sections below call each other as win.x / engines.x


# ==================================================================================================
# SECTION: win
# ==================================================================================================
import ctypes
import logging
import os
import sys
import uuid
from ctypes import wintypes as W
from pathlib import Path

log = logging.getLogger("rubenium.win")
IS_WIN = sys.platform == "win32"

if IS_WIN:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    HANDLE, HWND, HDC = W.HANDLE, W.HWND, W.HDC
    LONG_PTR = ctypes.c_ssize_t

    user32.GetForegroundWindow.restype = HWND
    user32.GetWindowThreadProcessId.argtypes = [HWND, ctypes.POINTER(W.DWORD)]
    user32.SetWindowPos.argtypes = [HWND, HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.SetWindowPos.restype = W.BOOL
    user32.GetWindowLongPtrW.argtypes = [HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = LONG_PTR
    user32.SetWindowLongPtrW.argtypes = [HWND, ctypes.c_int, LONG_PTR]
    user32.SetWindowLongPtrW.restype = LONG_PTR
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.RegisterHotKey.argtypes = [HWND, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
    user32.UnregisterHotKey.argtypes = [HWND, ctypes.c_int]
    kernel32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    kernel32.OpenProcess.restype = HANDLE
    kernel32.CloseHandle.argtypes = [HANDLE]
    kernel32.QueryFullProcessImageNameW.argtypes = [HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, W.BOOL, W.LPCWSTR]
    kernel32.CreateMutexW.restype = HANDLE
    gdi32.CreateDCW.argtypes = [W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, ctypes.c_void_p]
    gdi32.CreateDCW.restype = HDC
    gdi32.DeleteDC.argtypes = [HDC]
    gdi32.GetDeviceGammaRamp.argtypes = [HDC, ctypes.c_void_p]
    gdi32.GetDeviceGammaRamp.restype = W.BOOL
    gdi32.SetDeviceGammaRamp.argtypes = [HDC, ctypes.c_void_p]
    gdi32.SetDeviceGammaRamp.restype = W.BOOL


class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, text: str) -> "GUID":
        return cls.from_buffer_copy(uuid.UUID(text).bytes_le)

    def __str__(self) -> str:
        return str(uuid.UUID(bytes_le=bytes(self)))


# --------------------------------------------------------------------------- #
# Shell / process basics
# --------------------------------------------------------------------------- #
def documents_dir() -> Path:
    """Documents folder, OneDrive-redirect safe (SHGetKnownFolderPath)."""
    if IS_WIN:
        try:
            shell32 = ctypes.WinDLL("shell32")
            ole32 = ctypes.WinDLL("ole32")
            out = ctypes.c_void_p()
            fid = GUID.parse("FDD39AD0-238F-46AF-ADB4-6C85480369C7")
            shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), W.DWORD, HANDLE, ctypes.POINTER(ctypes.c_void_p)]
            if shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(out)) == 0 and out.value:
                path = ctypes.wstring_at(out.value)
                ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
                ole32.CoTaskMemFree(out)
                if path:
                    return Path(path)
        except Exception as exc:  # noqa: BLE001
            log.debug("SHGetKnownFolderPath failed: %s", exc)
    docs = Path.home() / "Documents"
    return docs if docs.exists() or IS_WIN else Path.home() / ".rubenium"


def relaunch_as_admin() -> bool:
    """Start Rubenium again with administrator rights (Windows asks the user first)."""
    if not IS_WIN:
        return False
    import subprocess
    if getattr(sys, "frozen", False):
        exe, params = sys.executable, "--elevated"
    else:
        exe = sys.executable
        pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(pyw):
            exe = pyw
        params = subprocess.list2cmdline([os.path.abspath(sys.argv[0]), "--elevated"])
    try:
        shell32 = ctypes.WinDLL("shell32")
        shell32.ShellExecuteW.restype = ctypes.c_void_p
        res = shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        return (res or 0) > 32                       # <= 32 means refused or failed
    except Exception as exc:  # noqa: BLE001
        log.info("could not restart as admin: %s", exc)
        return False


_mutex = None


def single_instance(wait: float = 0.0) -> bool:
    """True if we are the only running copy (named mutex). `wait` gives a closing copy time to quit."""
    global _mutex
    if not IS_WIN:
        return True
    import time
    deadline = time.monotonic() + wait
    while True:
        _mutex = kernel32.CreateMutexW(None, False, "Local\\Rubenium.SingleInstance")
        if ctypes.get_last_error() != 183:          # ERROR_ALREADY_EXISTS
            return True
        if _mutex:
            kernel32.CloseHandle(_mutex)
            _mutex = None
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.2)


def fullscreen_state() -> int:
    """0 normal, 1 borderless/busy fullscreen app, 2 exclusive (D3D) fullscreen."""
    if not IS_WIN:
        return 0
    try:
        state = ctypes.c_int(0)
        if ctypes.WinDLL("shell32").SHQueryUserNotificationState(ctypes.byref(state)) != 0:
            return 0
        return {2: 1, 4: 1, 3: 2}.get(state.value, 0)
    except Exception:  # noqa: BLE001
        return 0


def key_down(vk: int) -> bool:
    return bool(IS_WIN and user32.GetAsyncKeyState(vk) & 0x8000)


def _exe_of(pid: int) -> str:
    h = kernel32.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION (name only)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        n = W.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
            return os.path.basename(buf.value).lower()
    finally:
        kernel32.CloseHandle(h)
    return ""


def focus_app(keywords: list) -> bool:
    """Bring the first visible window whose exe name contains a keyword to the front, maximised."""
    if not IS_WIN or not keywords:
        return False
    try:
        found: list = []
        proc_t = ctypes.WINFUNCTYPE(W.BOOL, HWND, W.LPARAM)
        user32.IsWindowVisible.argtypes = [HWND]
        user32.GetWindowTextLengthW.argtypes = [HWND]
        user32.ShowWindow.argtypes = [HWND, ctypes.c_int]
        user32.SetForegroundWindow.argtypes = [HWND]

        def cb(hwnd, _lp):
            if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
                pid = W.DWORD(0)
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value and pid.value != os.getpid():
                    exe = _exe_of(pid.value)
                    if exe and any(k in exe for k in keywords):
                        found.append(hwnd)
                        return False
            return True

        keep = proc_t(cb)
        user32.EnumWindows.argtypes = [proc_t, W.LPARAM]
        user32.EnumWindows(keep, 0)
        if not found:
            return False
        user32.ShowWindow(found[0], 3)                    # SW_MAXIMIZE
        user32.SetForegroundWindow(found[0])
        return True
    except Exception as exc:  # noqa: BLE001
        log.debug("focus_app failed: %s", exc)
        return False


class AudioMeter:
    """Output loudness (0-1) of the default speakers, read from the Windows mixer's own peak meter.
    Nothing is recorded or captured."""

    def __init__(self) -> None:
        self._meter = None
        self._peak = None
        self._opened = 0.0
        self.failed = not IS_WIN

    @staticmethod
    def _method(ptr, index, *argtypes):
        vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0]
        addr = ctypes.cast(vtbl, ctypes.POINTER(ctypes.c_void_p))[index]
        fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(addr)
        return lambda *a: fn(ptr, *a)

    def _open(self) -> None:
        import time
        self._opened = time.monotonic()
        self.close()
        ole32 = ctypes.WinDLL("ole32")
        clsid = GUID.parse("BCDE0395-E52F-467C-8E3D-C4579291692E")       # MMDeviceEnumerator
        iid_enum = GUID.parse("A95664D2-9614-4F35-A746-DE8DB63617E6")    # IMMDeviceEnumerator
        iid_meter = GUID.parse("C02216F6-8C67-4B5B-9D00-D008E73E0064")   # IAudioMeterInformation
        ole32.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, W.DWORD,
                                           ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
        ole32.CoCreateInstance.restype = ctypes.c_long
        enum = ctypes.c_void_p()
        if ole32.CoCreateInstance(ctypes.byref(clsid), None, 23, ctypes.byref(iid_enum), ctypes.byref(enum)) < 0:
            raise OSError("no audio device enumerator")
        dev = ctypes.c_void_p()
        try:
            get_default = self._method(enum, 4, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))
            if get_default(0, 1, ctypes.byref(dev)) < 0 or not dev:      # eRender, eMultimedia
                raise OSError("no default speakers")
            meter = ctypes.c_void_p()
            activate = self._method(dev, 3, ctypes.POINTER(GUID), W.DWORD, ctypes.c_void_p,
                                    ctypes.POINTER(ctypes.c_void_p))
            if activate(ctypes.byref(iid_meter), 23, None, ctypes.byref(meter)) < 0 or not meter:
                raise OSError("no peak meter")
            self._meter = meter
            self._peak = self._method(meter, 3, ctypes.POINTER(ctypes.c_float))
        finally:
            if dev:
                self._method(dev, 2)()
            self._method(enum, 2)()

    def peak(self):
        """Current loudness 0-1, or None when unavailable."""
        if self.failed:
            return None
        import time
        try:
            if self._meter is None or time.monotonic() - self._opened > 10:   # follows a device change
                self._open()
            value = ctypes.c_float(0.0)
            if self._peak(ctypes.byref(value)) < 0:
                self._meter = None
                return None
            return max(0.0, min(1.0, float(value.value)))
        except Exception as exc:  # noqa: BLE001
            log.info("audio meter unavailable: %s", exc)
            self.failed = True
            return None

    def close(self) -> None:
        if self._meter is not None:
            try:
                self._method(self._meter, 2)()
            except Exception:  # noqa: BLE001
                pass
        self._meter = self._peak = None


class AppVolume:
    """Volume of one app in the Windows volume mixer (the same per-app slider Windows shows).

    Every call opens the mixer fresh and releases everything, so a device change, an app restart or a
    new audio stream is always picked up. Sessions on every active output device are included."""

    def __init__(self) -> None:
        self.failed = not IS_WIN
        self._ole = None

    @staticmethod
    def _call(ptr, index, argtypes, *args) -> int:
        vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0]
        addr = ctypes.cast(vtbl, ctypes.POINTER(ctypes.c_void_p))[index]
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(addr)(ptr, *args)

    def _release(self, ptr) -> None:
        if ptr:
            try:
                self._call(ptr, 2, [])
            except Exception:  # noqa: BLE001
                pass

    def _each(self, match, action) -> int:
        """Run `action(volume_ptr)` for every mixer session whose process matches. Returns how many."""
        if self.failed:
            return 0
        P = ctypes.POINTER
        if self._ole is None:
            self._ole = ctypes.WinDLL("ole32")
            self._ole.CoInitializeEx.argtypes = [ctypes.c_void_p, W.DWORD]
            self._ole.CoInitializeEx(None, 2)            # harmless if COM is already set up on this thread
            self._ole.CoCreateInstance.argtypes = [P(GUID), ctypes.c_void_p, W.DWORD, P(GUID), P(ctypes.c_void_p)]
            self._ole.CoCreateInstance.restype = ctypes.c_long
        clsid = GUID.parse("BCDE0395-E52F-467C-8E3D-C4579291692E")         # MMDeviceEnumerator
        iid_enum = GUID.parse("A95664D2-9614-4F35-A746-DE8DB63617E6")      # IMMDeviceEnumerator
        iid_mgr = GUID.parse("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F")       # IAudioSessionManager2
        iid_ctl2 = GUID.parse("BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D")      # IAudioSessionControl2
        iid_vol = GUID.parse("87CE5498-68D6-44E5-9215-6DA47EF883D8")       # ISimpleAudioVolume
        found = 0
        enum = ctypes.c_void_p()
        if self._ole.CoCreateInstance(ctypes.byref(clsid), None, 23, ctypes.byref(iid_enum), ctypes.byref(enum)) < 0:
            raise OSError("no audio device enumerator")
        coll = ctypes.c_void_p()
        try:
            # EnumAudioEndpoints(eRender, DEVICE_STATE_ACTIVE)
            if self._call(enum, 3, [ctypes.c_int, W.DWORD, P(ctypes.c_void_p)], 0, 1, ctypes.byref(coll)) < 0:
                return 0
            n_dev = ctypes.c_uint(0)
            self._call(coll, 3, [P(ctypes.c_uint)], ctypes.byref(n_dev))
            for d in range(n_dev.value):
                dev, mgr, sessions = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
                try:
                    if self._call(coll, 4, [ctypes.c_uint, P(ctypes.c_void_p)], d, ctypes.byref(dev)) < 0:
                        continue
                    if self._call(dev, 3, [P(GUID), W.DWORD, ctypes.c_void_p, P(ctypes.c_void_p)],
                                  ctypes.byref(iid_mgr), 23, None, ctypes.byref(mgr)) < 0:
                        continue
                    if self._call(mgr, 5, [P(ctypes.c_void_p)], ctypes.byref(sessions)) < 0:   # GetSessionEnumerator
                        continue
                    count = ctypes.c_int(0)
                    self._call(sessions, 3, [P(ctypes.c_int)], ctypes.byref(count))
                    for i in range(count.value):
                        ctl, ctl2, vol = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
                        try:
                            if self._call(sessions, 4, [ctypes.c_int, P(ctypes.c_void_p)], i, ctypes.byref(ctl)) < 0:
                                continue
                            if self._call(ctl, 0, [P(GUID), P(ctypes.c_void_p)], ctypes.byref(iid_ctl2),
                                          ctypes.byref(ctl2)) < 0:
                                continue
                            pid = W.DWORD(0)
                            if self._call(ctl2, 14, [P(W.DWORD)], ctypes.byref(pid)) < 0 or not pid.value:
                                continue                     # 0 = Windows system sounds
                            if not match(int(pid.value)):
                                continue
                            if self._call(ctl, 0, [P(GUID), P(ctypes.c_void_p)], ctypes.byref(iid_vol),
                                          ctypes.byref(vol)) < 0:
                                continue
                            action(vol)
                            found += 1
                        finally:
                            for ptr in (vol, ctl2, ctl):
                                self._release(ptr)
                finally:
                    for ptr in (sessions, mgr, dev):
                        self._release(ptr)
        finally:
            self._release(coll)
            self._release(enum)
        return found

    @staticmethod
    def matcher(source_id: str, keywords: list):
        """Process test for a media source: exact exe for desktop apps, name words for store apps."""
        low = (source_id or "").lower()
        exe = os.path.basename(low) if low.endswith(".exe") else ""
        words = [k for k in keywords if k]
        cache: dict = {}

        def match(pid: int) -> bool:
            if pid not in cache:
                name = _exe_of(pid)
                cache[pid] = bool(name) and (name == exe if exe else any(w.replace(" ", "") in name for w in words))
            return cache[pid]
        return match if (exe or words) else None

    def get(self, match):
        """(volume 0-1, muted) of the app, or None when it has no sound in the mixer right now."""
        if match is None:
            return None
        out: list = []

        def read(vol) -> None:
            v, m = ctypes.c_float(0.0), W.BOOL(0)
            if self._call(vol, 4, [ctypes.POINTER(ctypes.c_float)], ctypes.byref(v)) >= 0:
                self._call(vol, 6, [ctypes.POINTER(W.BOOL)], ctypes.byref(m))
                out.append((float(v.value), bool(m.value)))
        try:
            self._each(match, read)
        except Exception as exc:  # noqa: BLE001
            log.info("app volume unavailable: %s", exc)
            self.failed = True
            return None
        if not out:
            return None
        return max(o[0] for o in out), all(o[1] for o in out)

    def set(self, match, value: float) -> bool:
        if match is None:
            return False
        value = max(0.0, min(1.0, value))
        try:
            return self._each(match, lambda vol: self._call(vol, 3, [ctypes.c_float, ctypes.c_void_p],
                                                            value, None)) > 0
        except Exception as exc:  # noqa: BLE001
            log.info("app volume change failed: %s", exc)
            return False

    def set_mute(self, match, on: bool) -> bool:
        if match is None:
            return False
        try:
            return self._each(match, lambda vol: self._call(vol, 5, [W.BOOL, ctypes.c_void_p], int(on), None)) > 0
        except Exception as exc:  # noqa: BLE001
            log.info("app mute failed: %s", exc)
            return False


def open_path(path) -> bool:
    try:
        if IS_WIN:
            os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
            return True
    except OSError as exc:
        log.debug("open_path failed: %s", exc)
    return False


# --------------------------------------------------------------------------- #
# Window helpers
# --------------------------------------------------------------------------- #
def set_topmost(hwnd: int) -> None:
    if IS_WIN and hwnd:
        user32.SetWindowPos(HWND(hwnd), HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)


def make_overlay(hwnd: int) -> None:
    """Click-through, never activated, hidden from Alt-Tab."""
    if IS_WIN and hwnd:
        ex = user32.GetWindowLongPtrW(HWND(hwnd), -20)
        user32.SetWindowLongPtrW(HWND(hwnd), -20, ex | 0x80000 | 0x20 | 0x08000000 | 0x80)


def place_physical(hwnd: int, x: int, y: int, w: int, h: int) -> None:
    if IS_WIN and hwnd:
        user32.SetWindowPos(HWND(hwnd), HWND(-1), x, y, w, h, 0x0010)


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MONITORINFOEX(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("rcMonitor", _RECT), ("rcWork", _RECT),
                ("dwFlags", W.DWORD), ("szDevice", ctypes.c_wchar * 32)]


def monitors() -> list:
    """[(device, x, y, w, h, primary)] in physical pixels, primary first."""
    out: list = []
    if not IS_WIN:
        return out
    try:
        proc_t = ctypes.WINFUNCTYPE(W.BOOL, HANDLE, HDC, ctypes.POINTER(_RECT), W.LPARAM)
        user32.GetMonitorInfoW.argtypes = [HANDLE, ctypes.c_void_p]

        def cb(hmon, _hdc, _rc, _lp):
            mi = _MONITORINFOEX()
            mi.cbSize = ctypes.sizeof(mi)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                r = mi.rcMonitor
                out.append((mi.szDevice, r.left, r.top, r.right - r.left, r.bottom - r.top, bool(mi.dwFlags & 1)))
            return True

        keep = proc_t(cb)
        user32.EnumDisplayMonitors.argtypes = [HDC, ctypes.c_void_p, proc_t, W.LPARAM]
        user32.EnumDisplayMonitors(None, None, keep, 0)
        out.sort(key=lambda m: (not m[5], m[0]))
    except Exception as exc:  # noqa: BLE001
        log.debug("monitors failed: %s", exc)
    return out


# --------------------------------------------------------------------------- #
# Autostart (HKCU Run key)
# --------------------------------------------------------------------------- #
_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --startup'
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    script = Path(sys.argv[0]).resolve()
    return f'"{pyw if pyw.exists() else exe}" "{script}" --startup'


def autostart_get() -> bool:
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN) as k:
            winreg.QueryValueEx(k, "Rubenium")
            return True
    except OSError:
        return False


def autostart_set(on: bool) -> bool:
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, "Rubenium", 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(k, "Rubenium")
                except FileNotFoundError:
                    pass
        return True
    except OSError as exc:
        log.warning("autostart change failed: %s", exc)
        return False


# --------------------------------------------------------------------------- #
# Display: gamma ramps, Magnification colour matrix, display modes
# --------------------------------------------------------------------------- #
class _DISPLAY_DEVICE(ctypes.Structure):
    _fields_ = [("cb", W.DWORD), ("DeviceName", ctypes.c_wchar * 32), ("DeviceString", ctypes.c_wchar * 128),
                ("StateFlags", W.DWORD), ("DeviceID", ctypes.c_wchar * 128), ("DeviceKey", ctypes.c_wchar * 128)]


def display_devices() -> list:
    """[(device name, adapter description)] for displays attached to the desktop."""
    out: list = []
    if not IS_WIN:
        return out
    try:
        i = 0
        while i < 16:
            dd = _DISPLAY_DEVICE()
            dd.cb = ctypes.sizeof(dd)
            if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
                break
            if dd.StateFlags & 1:
                out.append((dd.DeviceName, dd.DeviceString))
            i += 1
    except Exception as exc:  # noqa: BLE001
        log.debug("display_devices failed: %s", exc)
    return out


_RAMP = (W.WORD * 256) * 3 if IS_WIN else None


def gamma_get(device: str):
    """Current gamma ramp as 3 lists of 256 ints, or None."""
    if not IS_WIN:
        return None
    hdc = gdi32.CreateDCW(None, device, None, None)
    if not hdc:
        return None
    try:
        ramp = _RAMP()
        if not gdi32.GetDeviceGammaRamp(hdc, ctypes.byref(ramp)):
            return None
        return [list(ramp[c]) for c in range(3)]
    finally:
        gdi32.DeleteDC(hdc)


def gamma_set(device: str, ramp) -> bool:
    if not IS_WIN:
        return False
    hdc = gdi32.CreateDCW(None, device, None, None)
    if not hdc:
        return False
    try:
        buf = _RAMP()
        for c in range(3):
            for i in range(256):
                buf[c][i] = max(0, min(65535, int(ramp[c][i])))
        return bool(gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(buf)))
    finally:
        gdi32.DeleteDC(hdc)


_mag = None
_mag_state = None   # None untested, True ready, False unavailable


def mag_available() -> bool:
    global _mag, _mag_state
    if _mag_state is None:
        _mag_state = False
        if IS_WIN:
            try:
                _mag = ctypes.WinDLL("Magnification.dll")
                _mag.MagInitialize.restype = W.BOOL
                _mag.MagSetFullscreenColorEffect.argtypes = [ctypes.c_void_p]
                _mag.MagSetFullscreenColorEffect.restype = W.BOOL
                _mag.MagGetFullscreenColorEffect.argtypes = [ctypes.c_void_p]
                _mag.MagGetFullscreenColorEffect.restype = W.BOOL
                _mag_state = bool(_mag.MagInitialize())
            except Exception as exc:  # noqa: BLE001
                log.info("Magnification API unavailable: %s", exc)
    return bool(_mag_state)


def mag_set_matrix(m3) -> bool:
    """Apply a 3x3 colour matrix (column-vector form) to the whole desktop; verified by read-back."""
    if not mag_available():
        return False
    eff = (ctypes.c_float * 25)()
    for r in range(5):
        eff[r * 5 + r] = 1.0
    for r in range(3):
        for c in range(3):
            eff[c * 5 + r] = float(m3[r][c])       # the API uses row vectors: transpose
    if not _mag.MagSetFullscreenColorEffect(ctypes.byref(eff)):
        return False
    back = (ctypes.c_float * 25)()
    if not _mag.MagGetFullscreenColorEffect(ctypes.byref(back)):
        return False
    return all(abs(back[i] - eff[i]) < 0.01 for i in range(25))


def mag_shutdown() -> None:
    global _mag_state
    if _mag_state and _mag is not None:
        try:
            _mag.MagUninitialize()
        except Exception:  # noqa: BLE001
            pass
    _mag_state = None


class _DEVMODE(ctypes.Structure):
    _fields_ = [("dmDeviceName", ctypes.c_wchar * 32), ("dmSpecVersion", W.WORD), ("dmDriverVersion", W.WORD),
                ("dmSize", W.WORD), ("dmDriverExtra", W.WORD), ("dmFields", W.DWORD),
                ("dmPositionX", ctypes.c_long), ("dmPositionY", ctypes.c_long),
                ("dmDisplayOrientation", W.DWORD), ("dmDisplayFixedOutput", W.DWORD),
                ("dmColor", ctypes.c_short), ("dmDuplex", ctypes.c_short), ("dmYResolution", ctypes.c_short),
                ("dmTTOption", ctypes.c_short), ("dmCollate", ctypes.c_short),
                ("dmFormName", ctypes.c_wchar * 32), ("dmLogPixels", W.WORD), ("dmBitsPerPel", W.DWORD),
                ("dmPelsWidth", W.DWORD), ("dmPelsHeight", W.DWORD), ("dmDisplayFlags", W.DWORD),
                ("dmDisplayFrequency", W.DWORD), ("dmICMMethod", W.DWORD), ("dmICMIntent", W.DWORD),
                ("dmMediaType", W.DWORD), ("dmDitherType", W.DWORD), ("dmReserved1", W.DWORD),
                ("dmReserved2", W.DWORD), ("dmPanningWidth", W.DWORD), ("dmPanningHeight", W.DWORD)]


def refresh_info():
    """(width, height, current Hz, best Hz at this resolution) for the primary display, or None."""
    if not IS_WIN:
        return None
    try:
        cur = _DEVMODE()
        cur.dmSize = ctypes.sizeof(cur)
        if not user32.EnumDisplaySettingsExW(None, -1, ctypes.byref(cur), 0):
            return None
        best, i = cur.dmDisplayFrequency, 0
        while i < 2000:
            dm = _DEVMODE()
            dm.dmSize = ctypes.sizeof(dm)
            if not user32.EnumDisplaySettingsExW(None, i, ctypes.byref(dm), 0):
                break
            if (dm.dmPelsWidth, dm.dmPelsHeight, dm.dmBitsPerPel) == (cur.dmPelsWidth, cur.dmPelsHeight, cur.dmBitsPerPel):
                best = max(best, dm.dmDisplayFrequency)
            i += 1
        return int(cur.dmPelsWidth), int(cur.dmPelsHeight), int(cur.dmDisplayFrequency), int(best)
    except Exception as exc:  # noqa: BLE001
        log.debug("refresh_info failed: %s", exc)
        return None


def refresh_set(hz: int) -> bool:
    """Switch the primary display to `hz` at its current resolution (driver-tested first)."""
    if not IS_WIN:
        return False
    try:
        dm = _DEVMODE()
        dm.dmSize = ctypes.sizeof(dm)
        if not user32.EnumDisplaySettingsExW(None, -1, ctypes.byref(dm), 0):
            return False
        dm.dmDisplayFrequency = hz
        dm.dmFields = 0x400000 | 0x80000 | 0x100000
        if user32.ChangeDisplaySettingsExW(None, ctypes.byref(dm), None, 2, None) != 0:   # CDS_TEST
            return False
        return user32.ChangeDisplaySettingsExW(None, ctypes.byref(dm), None, 1, None) == 0
    except Exception as exc:  # noqa: BLE001
        log.debug("refresh_set failed: %s", exc)
        return False


# --------------------------------------------------------------------------- #
# NVIDIA: digital vibrance (NVAPI) and sensors (NVML). Absent on AMD / Intel.
# --------------------------------------------------------------------------- #
class _DVC_INFO(ctypes.Structure):
    _fields_ = [("version", ctypes.c_uint), ("currentLevel", ctypes.c_uint),
                ("minLevel", ctypes.c_uint), ("maxLevel", ctypes.c_uint)]


class NvVibrance:
    """Digital vibrance through nvapi_QueryInterface. `ok` is True only after a verified round trip."""

    def __init__(self) -> None:
        self.ok = False
        self.reason = "NVIDIA driver not found"
        self._handles: list = []
        self._get = self._set = None
        self.min, self.max = 0, 63
        self.original: dict = {}
        if not IS_WIN:
            return
        try:
            lib = ctypes.CDLL("nvapi64.dll" if ctypes.sizeof(ctypes.c_void_p) == 8 else "nvapi.dll")
            qi = lib.nvapi_QueryInterface
            qi.restype = ctypes.c_void_p
            qi.argtypes = [ctypes.c_uint]

            def fn(ident, *argtypes):
                addr = qi(ident)
                return ctypes.CFUNCTYPE(ctypes.c_int, *argtypes)(addr) if addr else None

            init = fn(0x0150E828)
            enum = fn(0x9ABDD40D, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p))
            self._get = fn(0x4085DE45, ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(_DVC_INFO))
            self._set = fn(0x172409B4, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint)
            if not (init and enum and self._get and self._set) or init() != 0:
                self.reason = "NVAPI did not initialise"
                return
            for i in range(16):
                h = ctypes.c_void_p()
                if enum(i, ctypes.byref(h)) != 0:
                    break
                self._handles.append(h)
            if not self._handles:
                self.reason = "No display is driven by the NVIDIA GPU"
                return
            for idx in range(len(self._handles)):
                info = self._info(idx)
                if info is None:
                    self.reason = "Driver refused the vibrance query"
                    return
                self.original[idx] = info.currentLevel
                self.min, self.max = info.minLevel, info.maxLevel
            # verified round trip: write the current value back and read it again
            first = self.original[0]
            if self._set(self._handles[0], 0, first) != 0 or self._info(0).currentLevel != first:
                self.reason = "Driver refused the vibrance write"
                return
            self.ok = self.max > self.min
            self.reason = ""
        except Exception as exc:  # noqa: BLE001
            log.info("NVAPI unavailable: %s", exc)

    def _info(self, idx: int):
        info = _DVC_INFO()
        info.version = ctypes.sizeof(_DVC_INFO) | 0x10000
        if self._get(self._handles[idx], 0, ctypes.byref(info)) != 0:
            return None
        return info

    def percent(self) -> int:
        """Current level as the 0-100 scale of the NVIDIA control panel (50 = default)."""
        info = self._info(0) if self.ok else None
        if info is None:
            return 50
        return int(round(50 + 50 * (info.currentLevel - self.min) / max(1, self.max - self.min)))

    def set_percent(self, pct: int) -> bool:
        if not self.ok:
            return False
        level = int(round(self.min + (max(50, min(100, pct)) - 50) / 50 * (self.max - self.min)))
        good = True
        for idx, h in enumerate(self._handles):
            if self._set(h, 0, level) != 0:
                good = False
        info = self._info(0)
        return good and info is not None and info.currentLevel == level

    def restore(self) -> None:
        if not self.ok:
            return
        for idx, level in self.original.items():
            try:
                self._set(self._handles[idx], 0, level)
            except Exception:  # noqa: BLE001
                pass


class _NvUtil(ctypes.Structure):
    _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]


class _NvMem(ctypes.Structure):
    _fields_ = [("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong), ("used", ctypes.c_ulonglong)]


class Nvml:
    """GPU load / VRAM / temperature from nvml.dll (ships with the NVIDIA driver)."""

    def __init__(self) -> None:
        self.ok = False
        self.name = ""
        self._lib = None
        self._h = ctypes.c_void_p()
        if not IS_WIN:
            return
        for cand in ("nvml.dll", os.path.expandvars(r"%ProgramW6432%\NVIDIA Corporation\NVSMI\nvml.dll")):
            try:
                self._lib = ctypes.CDLL(cand)
                break
            except OSError:
                continue
        if self._lib is None:
            return
        try:
            lib = self._lib
            if lib.nvmlInit_v2() != 0:
                return
            lib.nvmlDeviceGetHandleByIndex_v2.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)]
            if lib.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(self._h)) != 0:
                return
            lib.nvmlDeviceGetUtilizationRates.argtypes = [ctypes.c_void_p, ctypes.POINTER(_NvUtil)]
            lib.nvmlDeviceGetMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_NvMem)]
            lib.nvmlDeviceGetTemperature.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)]
            lib.nvmlDeviceGetName.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint]
            buf = ctypes.create_string_buffer(96)
            if lib.nvmlDeviceGetName(self._h, buf, 96) == 0:
                self.name = buf.value.decode("utf-8", "replace")
            self.ok = self.read() is not None
        except Exception as exc:  # noqa: BLE001
            log.info("NVML unavailable: %s", exc)

    def read(self):
        """(gpu %, vram used MB, vram total MB, temp C or None) or None."""
        try:
            u, m, t = _NvUtil(), _NvMem(), ctypes.c_uint(0)
            if self._lib.nvmlDeviceGetUtilizationRates(self._h, ctypes.byref(u)) != 0:
                return None
            if self._lib.nvmlDeviceGetMemoryInfo(self._h, ctypes.byref(m)) != 0:
                return None
            temp = t.value if self._lib.nvmlDeviceGetTemperature(self._h, 0, ctypes.byref(t)) == 0 else None
            return int(u.gpu), m.used / 1048576, m.total / 1048576, temp
        except Exception:  # noqa: BLE001
            return None

    def close(self) -> None:
        if self.ok:
            try:
                self._lib.nvmlShutdown()
            except Exception:  # noqa: BLE001
                pass


# --------------------------------------------------------------------------- #
# Tools: power plan, Game Mode, mouse acceleration, timer resolution, ping, info
# --------------------------------------------------------------------------- #
POWER_PLANS = {"saver": "a1841308-3541-4fab-bc81-f71556f20b4a",
               "balanced": "381b4222-f694-41f0-9685-ff5bb260df2e",
               "high": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"}


def power_get():
    """'saver' | 'balanced' | 'high' | 'other', or None when unreadable."""
    if not IS_WIN:
        return None
    try:
        pp = ctypes.WinDLL("powrprof")
        ptr = ctypes.POINTER(GUID)()
        if pp.PowerGetActiveScheme(None, ctypes.byref(ptr)) != 0 or not ptr:
            return None
        active = str(ptr.contents).lower()
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree(ctypes.cast(ptr, ctypes.c_void_p))
        for name, g in POWER_PLANS.items():
            if g == active:
                return name
        return "other"
    except Exception as exc:  # noqa: BLE001
        log.debug("power_get failed: %s", exc)
        return None


def power_set(name: str) -> bool:
    if not IS_WIN or name not in POWER_PLANS:
        return False
    try:
        g = GUID.parse(POWER_PLANS[name])
        ctypes.WinDLL("powrprof").PowerSetActiveScheme(None, ctypes.byref(g))
        return power_get() == name          # verified by read-back
    except Exception as exc:  # noqa: BLE001
        log.debug("power_set failed: %s", exc)
        return False


_GAMEBAR = r"Software\Microsoft\GameBar"


def game_mode_get():
    if not IS_WIN:
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _GAMEBAR) as k:
            try:
                return bool(winreg.QueryValueEx(k, "AutoGameModeEnabled")[0])
            except FileNotFoundError:
                return True       # value absent = Windows default (on)
    except OSError:
        return None


def game_mode_set(on: bool) -> bool:
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _GAMEBAR, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "AutoGameModeEnabled", 0, winreg.REG_DWORD, int(on))
            winreg.SetValueEx(k, "AllowAutoGameMode", 0, winreg.REG_DWORD, int(on))
        return game_mode_get() == on
    except OSError as exc:
        log.debug("game_mode_set failed: %s", exc)
        return False


def mouse_accel_get():
    """True if 'Enhance pointer precision' is on, None if unreadable."""
    if not IS_WIN:
        return None
    arr = (ctypes.c_int * 3)()
    if not user32.SystemParametersInfoW(0x0003, 0, ctypes.byref(arr), 0):
        return None
    return bool(arr[2])


def mouse_accel_set(on: bool) -> bool:
    if not IS_WIN:
        return False
    arr = (ctypes.c_int * 3)(6, 10, 1) if on else (ctypes.c_int * 3)(0, 0, 0)
    user32.SystemParametersInfoW(0x0004, 0, ctypes.byref(arr), 3)
    return mouse_accel_get() == on


_icmp = None


def ping_ms(ip=(1, 1, 1, 1), timeout_ms: int = 1000):
    """Round trip to `ip` in ms (IcmpSendEcho, no admin rights), or None."""
    global _icmp
    if not IS_WIN:
        return None
    try:
        ip_dll = ctypes.WinDLL("iphlpapi")
        if _icmp is None:
            ip_dll.IcmpCreateFile.restype = HANDLE
            _icmp = ip_dll.IcmpCreateFile()
        ip_dll.IcmpSendEcho.argtypes = [HANDLE, ctypes.c_uint32, ctypes.c_void_p, W.WORD, ctypes.c_void_p,
                                        ctypes.c_void_p, W.DWORD, W.DWORD]
        ip_dll.IcmpSendEcho.restype = W.DWORD
        addr = int.from_bytes(bytes(ip), "little")
        payload = ctypes.create_string_buffer(b"rubenium", 8)
        reply = ctypes.create_string_buffer(128)
        if ip_dll.IcmpSendEcho(_icmp, addr, payload, 8, None, reply, 128, timeout_ms) == 0:
            return None
        status = int.from_bytes(reply.raw[4:8], "little")
        return int.from_bytes(reply.raw[8:12], "little") if status == 0 else None
    except Exception as exc:  # noqa: BLE001
        log.debug("ping failed: %s", exc)
        return None


_DVR_STORE = r"System\GameConfigStore"
_DVR_APP = r"Software\Microsoft\Windows\CurrentVersion\GameDVR"


def game_dvr_get():
    """True if Windows background game recording is allowed, None if unreadable."""
    if not IS_WIN:
        return None
    import winreg
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _DVR_APP, 0, winreg.KEY_READ) as k:
            try:
                return bool(winreg.QueryValueEx(k, "AppCaptureEnabled")[0])
            except FileNotFoundError:
                return True
    except OSError:
        return None


def game_dvr_set(on: bool) -> bool:
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _DVR_APP, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "AppCaptureEnabled", 0, winreg.REG_DWORD, int(on))
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _DVR_STORE, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "GameDVR_Enabled", 0, winreg.REG_DWORD, int(on))
        return game_dvr_get() == on
    except OSError as exc:
        log.debug("game_dvr_set failed: %s", exc)
        return False


def flush_dns() -> bool:
    """Empty the Windows DNS cache (same as 'ipconfig /flushdns'). No admin rights needed."""
    if not IS_WIN:
        return False
    try:
        fn = ctypes.WinDLL("dnsapi").DnsFlushResolverCache
        fn.restype = W.BOOL
        if fn():
            return True
    except Exception as exc:  # noqa: BLE001
        log.debug("DnsFlushResolverCache failed: %s", exc)
    try:
        import subprocess
        r = subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=10,
                           creationflags=0x08000000)          # CREATE_NO_WINDOW
        return r.returncode == 0
    except Exception as exc:  # noqa: BLE001
        log.debug("ipconfig /flushdns failed: %s", exc)
        return False


def free_memory():
    """Ask Windows to trim the memory of background apps. Returns MB made available, or None."""
    if not IS_WIN:
        return None
    try:
        import psutil
        psapi = ctypes.WinDLL("psapi")
        psapi.EmptyWorkingSet.argtypes = [HANDLE]
        psapi.EmptyWorkingSet.restype = W.BOOL
        before = psutil.virtual_memory().available
        skip = {os.getpid()}
        front = W.DWORD(0)
        hwnd = user32.GetForegroundWindow()
        if hwnd:
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(front))
            skip.add(int(front.value))                 # never touch the game / app in front
        for pid in psutil.pids():
            if pid in skip or pid < 8:
                continue
            h = kernel32.OpenProcess(0x0400 | 0x0100, False, pid)   # QUERY_INFORMATION | SET_QUOTA
            if h:
                try:
                    psapi.EmptyWorkingSet(h)
                finally:
                    kernel32.CloseHandle(h)
        return max(0.0, (psutil.virtual_memory().available - before) / 1048576)
    except Exception as exc:  # noqa: BLE001
        log.debug("free_memory failed: %s", exc)
        return None


def cpu_name() -> str:
    if IS_WIN:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                return str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    import platform
    return platform.processor() or "CPU"


def windows_version() -> str:
    import platform
    if not IS_WIN:
        return platform.platform()
    v = sys.getwindowsversion()
    return f"Windows {'11' if v.build >= 22000 else '10'} (build {v.build})"


# ==================================================================================================
# SECTION: core
# ==================================================================================================
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


APP_NAME = "Rubenium"
VERSION = "4.0.0"            # build number: only ever goes up, it is what the updater compares
VERSION_NAME = "1.0"         # the version people see
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
ACCENT_DEFAULT = "#2D9CFF"      # boost blue
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
    "glow_power": 1,
    "backdrop": 0,
    "corners": 0,
    "ball_style": "classic",
    "ring_style": "line",
    "news_tab": False,
    "welcome": True,
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
        keep = {k: self.d[k] for k in ("ball", "card", "lang", "autostart", "usage_s", "theme")}
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
        pass
        _fr = FR


def lang() -> str:
    return _lang


def tr(text: str, **kw) -> str:
    out = _fr.get(text, text) if _lang == "fr" else text
    return out.format(**kw) if kw else out


# ==================================================================================================
# SECTION: lang_fr
# ==================================================================================================
FR = {
    # tabs
    "Home": "Accueil", "Lyrics": "Paroles", "Crosshair": "Viseur", "Display": "Écran", "Stats": "Stats",
    "Tools": "Outils", "Rocket": "Rocket", "Settings": "Réglages",
    # tray
    "Open / close": "Ouvrir / fermer", "Crosshair on / off": "Afficher / masquer le viseur",
    "Normal screen colours": "Couleurs d'écran normales",
    "Put the ball back in the corner": "Remettre la bulle dans le coin", "Quit Rubenium": "Quitter Rubenium",
    # home
    "Could not find the music app window": "Fenêtre de l'appli de musique introuvable",
    "Click to choose the music app": "Cliquez pour choisir l'appli de musique",
    "Open the music app": "Ouvrir l'appli de musique",
    "Shuffle": "Lecture aléatoire", "Previous": "Précédent", "Next": "Suivant", "Repeat": "Répéter",
    "Music app: {name}": "Appli de musique : {name}", "Music app: automatic": "Appli de musique : automatique",
    "Unknown artist": "Artiste inconnu", "Setup needed": "Installation à terminer",
    "Music app not responding": "L'appli de musique ne répond pas", "Trying again…": "Nouvel essai…",
    "Nothing is playing": "Aucune musique en cours",
    "Press play in your music app": "Lancez un titre dans votre appli de musique",
    "No music app is open": "Aucune appli de musique ouverte",
    "Press play to open Spotify": "Appuyez sur lecture pour ouvrir Spotify", "Auto": "Auto",
    # lyrics
    "Try again": "Réessayer", "Play a song to see its lyrics": "Lancez un titre pour voir les paroles",
    "Looking for lyrics…": "Recherche des paroles…", "No internet connection": "Pas de connexion Internet",
    "No lyrics for this song": "Pas de paroles pour ce titre",
    # crosshair
    "Show crosshair": "Afficher le viseur", "Cross": "Croix", "T": "T", "Dot": "Point", "Circle": "Cercle",
    "Image": "Image", "Colour": "Couleur", "Other colour": "Autre couleur", "Shape": "Forme",
    "Length": "Longueur", "Thickness": "Épaisseur", "Gap": "Écart", "Circle radius": "Taille du cercle",
    "Dot size": "Taille du point", "Outline width": "Épaisseur du contour", "Opacity": "Opacité",
    "Centre dot": "Point central", "Outline": "Contour", "Position": "Position",
    "Offset X": "Décalage horizontal", "Offset Y": "Décalage vertical", "Screen {n}": "Écran {n}",
    "Your own image": "Votre image", "Add image…": "Ajouter une image…", "Next image": "Image suivante",
    "Open the image folder": "Ouvrir le dossier des images", "Image size": "Taille de l'image",
    "Saved crosshairs": "Viseurs enregistrés", "Load": "Charger", "Save": "Enregistrer",
    "Use “borderless” or “windowed” mode in your game to see the crosshair.":
        "Mettez votre jeu en mode « fenêtré » ou « sans bordure » pour voir le viseur.",
    "Reset crosshair": "Réinitialiser le viseur", "Selected: {name}": "Image choisie : {name}",
    "No image yet": "Aucune image pour l'instant", "Add an image first": "Ajoutez d'abord une image",
    "Choose an image": "Choisir une image", "This file could not be added": "Impossible d'ajouter ce fichier",
    "Image added": "Image ajoutée",
    "Slot {n} is empty": "L'emplacement {n} est vide", "Crosshair reset": "Viseur réinitialisé",
    # display
    "Change my screen colours": "Modifier les couleurs de l'écran",
    "Goes back to normal when you turn it off": "Tout redevient normal quand vous désactivez",
    "Look A": "Style A", "Look B": "Style B", "Light": "Lumière", "Brightness": "Luminosité",
    "Contrast": "Contraste", "Gamma": "Gamma", "Brighter shadows": "Ombres plus claires",
    "Colour strength": "Intensité des couleurs", "Tint": "Teinte", "NVIDIA vibrance": "Vibrance NVIDIA",
    "Red": "Rouge", "Green": "Vert", "Blue": "Bleu",
    "Some settings are missing": "Certains réglages sont absents",
    "This PC or screen does not allow them.": "Ce PC ou cet écran ne les permet pas.",
    "Reset this look": "Réinitialiser ce style", "Look {p} reset": "Style {p} réinitialisé",
    "Your screen refused this setting": "Votre écran a refusé ce réglage",
    # stats
    "Processor": "Processeur", "Memory": "Mémoire", "Graphics": "Carte graphique", "Ping": "Ping",
    "Internet": "Internet", "On-screen stats": "Stats à l'écran",
    "Show stats while I play": "Afficher les stats pendant le jeu",
    "Top left": "Haut gauche", "Top right": "Haut droite", "Bottom left": "Bas gauche",
    "Bottom right": "Bas droite",
    # tools
    "Gaming mode": "Mode jeu",
    "Sets up Windows for games. Turn off to undo.": "Prépare Windows pour le jeu. Désactivez pour annuler.",
    "Full power": "Puissance maximale", "Windows Game Mode on": "Mode Jeu de Windows activé",
    "Mouse acceleration off": "Accélération de la souris désactivée",
    "Your screen can be smoother": "Votre écran peut être plus fluide",
    "It runs at {a} Hz but can do {b} Hz.": "Il est à {a} Hz mais peut aller jusqu'à {b} Hz.",
    "Use {b} Hz": "Passer à {b} Hz",
    "Screen: {a} Hz, the best it can do": "Écran : {a} Hz, son maximum",
    "Free up space": "Libérer de l'espace", "Deletes old temporary files": "Supprime les anciens fichiers temporaires",
    "My PC": "Mon PC", "Copy": "Copier", "Gaming mode is on": "Mode jeu activé",
    "Back to your normal settings": "Retour à vos réglages habituels", "Done": "C'est fait",
    "{mb} MB freed": "{mb} Mo libérés", "Screen": "Écran", "Copied": "Copié",
    # rocket league
    "Rocket League items": "Objets Rocket League",
    "Coming soon. Pick your files now: they are saved for later.":
        "Bientôt disponible. Choisissez déjà vos fichiers : ils sont gardés pour plus tard.",
    "Fix missing files after an update": "Réparer les fichiers manquants après une mise à jour",
    "Checks automatically when Rocket League updates": "Vérification automatique à chaque mise à jour du jeu",
    "My items": "Mes objets", "No file": "Aucun fichier", "Remove": "Retirer", "Choose…": "Choisir…",
    "Saved. This will work in a coming update.": "Enregistré. Cela fonctionnera dans une prochaine version.",
    "Choose a file": "Choisir un fichier",
    "Boost": "Boost", "Wheels": "Roues", "Decal": "Sticker", "Goal explosion": "Explosion de but",
    "Trail": "Traînée", "Topper": "Chapeau", "Car body": "Voiture",
    # settings
    "Look": "Apparence", "Glow": "Halo lumineux", "Glow moves with the music": "Le halo suit la musique",
    "Song progress around the ball": "Avancement du titre autour de la bulle",
    "Colour from the album cover": "Couleur selon la pochette", "Language": "Langue", "Size": "Taille",
    "Windows": "Windows", "Start with Windows": "Lancer au démarrage de Windows",
    "Reset settings": "Réinitialiser les réglages",
    "Press again to reset everything": "Appuyez encore une fois pour tout réinitialiser",
    "Settings reset": "Réglages réinitialisés",
    # window
    "Close to the ball": "Réduire en bulle", "Leave your game first": "Quittez d'abord votre jeu",
    # tools 1.2
    "Clock": "Heure", "Background recording off": "Enregistrement en arrière-plan désactivé",
    "Quick fixes": "Réparations rapides", "Free up memory": "Libérer de la mémoire",
    "Makes background apps give memory back": "Les applis en arrière-plan rendent de la mémoire",
    "Refresh internet connection": "Rafraîchir la connexion Internet",
    "Clears saved internet addresses. Helps when a game cannot connect.":
        "Efface les adresses Internet gardées en mémoire. Utile quand un jeu ne se connecte pas.",
    "Connection test": "Test de connexion", "Test my connection": "Tester ma connexion", "Testing…": "Test en cours…",
    "Press the button to check your ping.": "Appuyez sur le bouton pour mesurer votre ping.",
    "no answer": "pas de réponse", "lost": "perdu",
    "Great for online games": "Parfait pour jouer en ligne",
    "Good enough for most games": "Suffisant pour la plupart des jeux",
    "Unstable. A cable is better than Wi-Fi.": "Instable. Un câble est mieux que le Wi-Fi.",
    "Mouse sensitivity": "Sensibilité de la souris", "Mouse DPI": "DPI de la souris",
    "In-game sensitivity": "Sensibilité en jeu",
    "Full turn: {cm} cm   ·   eDPI {e}": "Tour complet : {cm} cm   ·   eDPI {e}",
    "Could not do that on this PC": "Impossible sur ce PC", "{mb} MB of memory freed": "{mb} Mo de mémoire libérés",
    "Connection refreshed": "Connexion rafraîchie",
    # 1.3
    "Appearance": "Apparence", "Progress ring": "Anneau de progression",
    "Match album colour": "Couleur de l'album", "Accent colour": "Couleur d'accent",
    # 1.4
    "Apps": "Applis", "Timer": "Chrono", "Themes": "Thèmes",
    "Start": "Démarrer", "Split": "Tour", "Resume": "Reprendre", "Pause": "Pause", "Finish": "Terminer",
    "Reset": "Effacer", "No splits yet": "Aucun temps", "Best: {t}": "Meilleur temps : {t}",
    "Show on screen": "Afficher à l'écran", "Keyboard shortcuts": "Raccourcis clavier",
    "Time used: {t}": "Temps d'utilisation : {t}", "In use": "Utilisé", "Use": "Utiliser",
    "Preview: unlocks at {h} hours": "Aperçu : se débloque à {h} heures", "Boost colour": "Couleur du thème Boost",
    "No apps found": "Aucune appli trouvée", "Search again": "Chercher à nouveau",
    "{name} closed": "{name} fermé", "Could not close {name}": "Impossible de fermer {name}",
    "Opening {name}": "Ouverture de {name}", "Could not open {name}": "Impossible d'ouvrir {name}",
    "Rocket League found": "Rocket League détecté", "Rocket League not found": "Rocket League introuvable",
    "Choose the game folder": "Choisissez le dossier du jeu",
    "That is not the Rocket League folder": "Ce n'est pas le dossier de Rocket League",
    "Mine": "Le mien", "Show as": "Afficher comme", "Soon": "Bientôt", "Off": "Désactivé", "Title": "Titre",
    "Pick the title you want to show": "Choisissez le titre à afficher",
    "Library": "Bibliothèque", "Copy code": "Copier le code", "Paste code": "Coller un code",
    "Code copied": "Code copié", "No crosshair code found": "Aucun code de viseur trouvé",
    "Classic": "Classique", "Small": "Petit", "Tight": "Serré", "Wide": "Large", "Big dot": "Gros point",
    "Cross dot": "Croix et point", "Circle dot": "Cercle et point", "Scope": "Lunette", "Thick": "Épais",
    "This session": "Cette session", "Time": "Durée", "Processor, highest": "Processeur, maximum",
    "Processor, average": "Processeur, moyenne", "Memory, highest": "Mémoire, maximum",
    "Ping, average": "Ping, moyenne", "Graphics card, hottest": "Carte graphique, température max.",
    # 1.5
    "Custom 1": "Custom 1", "Custom 2": "Custom 2", "Custom {n} reset": "Custom {n} réinitialisé", "Shadows": "Ombres",
    "Black outline": "Contour noir", "Yes": "Oui", "No": "Non", "Close {name}?": "Fermer {name} ?",
    "Close": "Fermer", "PREVIEW": "APERÇU",
    "Small cross": "Petite croix", "Tight cross": "Croix serrée", "Wide cross": "Croix large",
    "Thick cross": "Croix épaisse", "Cross and dot": "Croix et point", "Circle and dot": "Cercle et point",
    "Clean": "Épuré", "Grid": "Grille", "Dots": "Points", "Waves": "Vagues", "Hex": "Hexagones", "Stars": "Étoiles",
    "Beams": "Faisceaux", "Aurora": "Aurore", "Prism": "Prisme", "Legend": "Légende",
    "Reset colours": "Réinitialiser les couleurs",
    # 1.6
    "Mute": "Couper le son", "Unmute": "Remettre le son", "Music volume": "Volume de la musique",
    "Quick start": "Modèles", "Style": "Style", "Circle size": "Taille du cercle", "Left / right": "Gauche / droite",
    "Up / down": "Haut / bas",
    "Slot {n} is empty": "L'emplacement {n} est vide", "Hide menu bar when idle": "Masquer la barre au repos",
    "Start, then lap": "Démarrer, puis tour", "Pause / resume": "Pause / reprendre", "Reset to 0": "Remettre à 0",
    "Lines": "Lignes", "Radiance": "Éclat",
    # 2.0
    "My crosshairs": "Mes viseurs", "Slot {n}": "Slot {n}", "Clear slot": "Vider",
    "Save to slot {n}": "Enregistrer dans le slot {n}", "Click a slot to save": "Cliquez sur un slot",
    "Saved in slot {n}": "Enregistré dans le slot {n}",
    "Goal explosions": "Explosions de but", "Car bodies": "Voitures", "Boosts": "Boosts", "Trails": "Traînées",
    "File missing": "Fichier manquant",
    "An update put back the original files": "Une mise à jour a remis les fichiers d'origine",
    "Press Fix to swap them again": "Appuyez sur Réparer pour les remettre",
    "Game files were changed": "Des fichiers du jeu ont été modifiés",
    "A game file is missing": "Un fichier du jeu est manquant",
    "Repair the game in Epic or Steam": "Réparez le jeu dans Epic ou Steam",
    "Rocket League is open": "Rocket League est ouvert",
    "Swaps apply when you reload the game": "Les swaps s'appliquent en relançant le jeu",
    "Pick one swap per category": "Un seul swap par catégorie", "Fix": "Réparer",
    "Fix automatically after updates": "Réparer après chaque mise à jour",
    "Rocket League is open.": "Rocket League est ouvert.", "Reload": "Relancer", "Cancel": "Annuler",
    "Closing Rocket League…": "Fermeture de Rocket League…", "Applying…": "Application…",
    "Starting Rocket League…": "Lancement de Rocket League…",
    "Swaps applied again after a Rocket League update": "Swaps remis après la mise à jour de Rocket League",
    "Close Rocket League first": "Fermez d'abord Rocket League",
    "A game file is missing. Repair the game in Epic or Steam.":
        "Un fichier du jeu est manquant. Réparez le jeu dans Epic ou Steam.",
    "The swap file is missing": "Le fichier du swap est manquant",
    "The original file is missing. Repair the game in Epic or Steam.":
        "Le fichier d'origine est manquant. Réparez le jeu dans Epic ou Steam.",
    "Windows blocked the change": "Windows a bloqué le changement",
    "Something went wrong. Try again.": "Un problème est survenu. Réessayez.", "Run as admin": "Lancer en admin",
    # 2.1
    "Rocket League detected": "Rocket League détecté", "Rocket League not detected": "Rocket League non détecté",
    "Supports Steam and Epic": "Compatible Steam et Epic", "Search": "Rechercher",
    "1 change waiting": "1 changement en attente", "{n} changes waiting": "{n} changements en attente",
    "Apply": "Appliquer",
    "{name} version not detected": "Version {name} non détectée", "Turn off all swaps": "Désactiver tous les swaps",
    "Reset look": "Réinitialiser l'apparence", "Reset best time": "Effacer le meilleur temps",
    "Reset on-screen stats": "Réinitialiser les stats à l'écran",
    # 2.2
    "Updates": "Mises à jour", "Check for updates": "Rechercher", "Update to {v}": "Installer la {v}",
    "Version {v}": "Version {v}", "Check automatically": "Vérifier automatiquement",
    "Update {v} available": "Mise à jour {v} disponible", "Update": "Mettre à jour", "Later": "Plus tard",
    "Downloading update… {p}%": "Téléchargement… {p} %", "Restarting…": "Redémarrage…",
    "Rubenium is up to date": "Rubenium est à jour", "Could not check for updates": "Impossible de vérifier les mises à jour",
    "Update installed. Restart Rubenium.": "Mise à jour installée. Redémarrez Rubenium.",
    "Windows blocked the update. Download it from GitHub.":
        "Windows a bloqué la mise à jour. Téléchargez-la sur GitHub.",
    "The update failed. Nothing was changed.": "La mise à jour a échoué. Rien n'a été modifié.",
    # 3.0
    "Welcome to": "Bienvenue sur", "Launch": "Lancer", "Welcome screen": "Écran de bienvenue",
    "New": "Nouveautés", "What's new": "Nouveautés", "Decals": "Stickers", "Coming soon": "Bientôt disponible",
    "Only one swap at a time for {name}": "Un seul swap à la fois pour {name}",
    "Ball": "Bulle", "Ball size": "Taille de la bulle", "Menu bar": "Barre de menu",
    "Style": "Style", "Background": "Fond", "Corners": "Coins",
    "Soft": "Doux", "Normal": "Normal", "Strong": "Fort",
    "Dark": "Sombre", "Black": "Noir", "Night": "Nuit",
    "Round": "Ronds", "Medium": "Moyens", "Sharp": "Nets",
    "Start-up": "Démarrage", "Fixes": "Corrections",
    "Welcome screen with a Launch button and a loading animation":
        "Écran de bienvenue avec un bouton Lancer et une animation de chargement",
    "Rubenium comes back the way you left it": "Rubenium reprend là où vous l'aviez laissée",
    "8 new swaps and a new Decals section": "8 nouveaux swaps et une nouvelle section Stickers",
    "Several swaps can be on at once (one per item)": "Plusieurs swaps actifs en même temps (un par objet)",
    "Every swap has a spot for a picture of the result": "Chaque swap a un emplacement pour une image du résultat",
    "Room for more swaps in every section": "De la place pour d'autres swaps dans chaque section",
    "Stronger glow that follows the music better": "Halo plus fort, qui suit mieux la musique",
    "New theme options: glow, background and corners": "Nouvelles options de style : halo, fond et coins",
    "Themes unlock faster": "Les thèmes se débloquent plus vite",
    "Choose which tabs show in the menu bar": "Choisissez les onglets affichés dans la barre de menu",
    "Change the size of the ball, with a real-size preview":
        "Changez la taille de la bulle, avec un aperçu en taille réelle",
    "Tabs are in a cleaner order": "Onglets rangés dans un ordre plus clair",
    "Time used now keeps counting when the music stops":
        "Le temps d'utilisation continue de compter quand la musique s'arrête",
    "Timer keys and update checks keep working all day":
        "Les touches du chrono et la recherche de mises à jour fonctionnent toute la journée",
    # 1.0
    "RL SWAP": "RL SWAP", "RL Swap": "RL Swap", "Top apps": "Applis les plus gourmandes", "Earlier": "Avant",
    "Unlocks after {n} h of use": "Se débloque après {n} h d'utilisation",
    "The update failed. Try again in a moment.": "La mise à jour a échoué. Réessayez dans un instant.",
    "Hive": "Ruche", "Sonar": "Sonar", "Circuit": "Circuit", "Comets": "Comètes", "Nebula": "Nébuleuse",
    "Classic": "Classique", "Outline": "Contour", "Neon": "Néon", "Gold": "Or", "Line": "Ligne", "Dashes": "Tirets",
    "The Update button now works on every PC": "Le bouton Mettre à jour fonctionne maintenant sur tous les PC",
    "It also works when Windows protects the folder Rubenium is in":
        "Il fonctionne aussi quand Windows protège le dossier où se trouve Rubenium",
    "Every swap now shows a picture of the result": "Chaque swap affiche maintenant une image du résultat",
    "Black Lunation is ready": "Black Lunation est disponible",
    "The yellow outline only marks what is about to change": "Le contour jaune indique seulement ce qui va changer",
    "See which apps use the most processor and memory":
        "Voyez quelles applis utilisent le plus le processeur et la mémoire",
    "5 new themes, in a better order": "5 nouveaux thèmes, dans un meilleur ordre",
    "New styles for the R and for the song ring, unlocked with time":
        "Nouveaux styles pour le R et pour l'anneau du titre, à débloquer avec le temps",
    "Theme options for glow, background and corners": "Options de style : halo, fond et coins",
}


# ==================================================================================================
# SECTION: widgets
# ==================================================================================================
import math
from collections import deque
from typing import Callable, Optional

from PyQt6.QtCore import QEasingCurve, QPointF, QRectF, QTimer, QVariantAnimation, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PyQt6.QtWidgets import QAbstractButton, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget


AA = QPainter.RenderHint.Antialiasing


class Tween(QVariantAnimation):
    """Float animator that always continues from its current value (interruptions retarget)."""

    def __init__(self, parent, initial: float = 0.0, on_change: Optional[Callable[[], None]] = None,
                 easing: QEasingCurve.Type = QEasingCurve.Type.OutCubic) -> None:
        super().__init__(parent)
        self._value = float(initial)
        self.target = float(initial)
        self._mute = False
        self._on_change = on_change
        self.setEasingCurve(easing)
        self.valueChanged.connect(self._handle)

    @property
    def level(self) -> float:
        return self._value

    def _handle(self, value) -> None:
        if self._mute:
            return
        self._value = float(value)
        if self._on_change:
            self._on_change()

    def to(self, target: float, ms: int = 150) -> None:
        self.stop()
        self.target = float(target)
        if abs(target - self._value) < 1e-6:
            self._handle(target)
            return
        self._mute = True                 # re-arming a finished animation makes Qt emit stale values
        start = self._value
        self.setCurrentTime(0)
        self.setStartValue(start)
        self.setEndValue(float(target))
        self.setDuration(ms)
        self._mute = False
        self._value = start
        self.start()

    def jump(self, value: float) -> None:
        self.stop()
        self.target = float(value)
        self._handle(value)

    @property
    def busy(self) -> bool:
        """Still travelling. False during the final value callback, so 'arrived' logic can run there."""
        return self.state() == QVariantAnimation.State.Running and abs(self._value - self.target) > 1e-6


# --------------------------------------------------------------------------- #
# Vector icons (20-unit box centred on 0,0; 1.75 stroke, round caps)
# --------------------------------------------------------------------------- #
_GEAR: Optional[QPainterPath] = None
FILLED = {"play", "pause", "prev", "next", "cog"}


def _gear_path() -> QPainterPath:
    global _GEAR
    if _GEAR is None:
        body = QPainterPath()
        body.addEllipse(QPointF(0, 0), 6.0, 6.0)
        for k in range(8):
            tooth = QPainterPath()
            tooth.addRoundedRect(QRectF(-1.6, -8.8, 3.2, 4.0), 0.8, 0.8)
            rot = QTransform()
            rot.rotate(k * 45)
            body = body.united(rot.map(tooth))
        hole = QPainterPath()
        hole.addEllipse(QPointF(0, 0), 2.5, 2.5)
        _GEAR = body.subtracted(hole)
    return _GEAR


def _poly(*pts) -> QPainterPath:
    path = QPainterPath(QPointF(*pts[0]))
    for pt in pts[1:]:
        path.lineTo(QPointF(*pt))
    return path


def draw_icon(p: QPainter, kind: str, fg: QColor, hover: float = 0.0) -> None:
    """Draw `kind` centred on the painter origin, in a 20-unit box."""
    p.save()
    if kind in FILLED:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fg)
        if kind == "play":
            path = _poly((-4.5, -6.5), (-4.5, 6.5), (6.5, 0))
            path.closeSubpath()
            p.drawPath(path)
        elif kind == "pause":
            p.drawRoundedRect(QRectF(-5.5, -6.5, 3.6, 13), 1, 1)
            p.drawRoundedRect(QRectF(1.9, -6.5, 3.6, 13), 1, 1)
        elif kind == "prev":
            p.drawRoundedRect(QRectF(-8, -6, 2.2, 12), 1, 1)
            path = _poly((7, -6.5), (7, 6.5), (-5, 0))
            path.closeSubpath()
            p.drawPath(path)
        elif kind == "next":
            p.drawRoundedRect(QRectF(5.8, -6, 2.2, 12), 1, 1)
            path = _poly((-7, -6.5), (-7, 6.5), (5, 0))
            path.closeSubpath()
            p.drawPath(path)
        elif kind == "cog":
            p.rotate(hover * 60.0)
            p.drawPath(_gear_path())
        p.restore()
        return
    pen = QPen(fg, 1.75)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    line = lambda a, b, c, d: p.drawLine(QPointF(a, b), QPointF(c, d))  # noqa: E731
    if kind == "close":
        line(-4.5, -4.5, 4.5, 4.5)
        line(-4.5, 4.5, 4.5, -4.5)
    elif kind == "home":
        p.drawPath(_poly((-7.5, -0.5), (0, -7.5), (7.5, -0.5)))
        p.drawPath(_poly((-5.2, -2.5), (-5.2, 7), (5.2, 7), (5.2, -2.5)))
    elif kind == "lyrics":
        line(-7, -5, 7, -5)
        line(-7, 0, 2.5, 0)
        line(-7, 5, 5.5, 5)
    elif kind == "crosshair":
        p.drawEllipse(QPointF(0, 0), 6, 6)
        for a, b, c, d in ((0, -9, 0, -4), (0, 4, 0, 9), (-9, 0, -4, 0), (4, 0, 9, 0)):
            line(a, b, c, d)
    elif kind == "display":
        p.drawRoundedRect(QRectF(-8, -7, 16, 11), 2, 2)
        line(0, 4, 0, 7.5)
        line(-3.5, 7.5, 3.5, 7.5)
    elif kind == "perf":
        p.drawPath(_poly((-8.5, 1), (-4.5, 1), (-2, -6), (1.5, 6.5), (3.5, 1), (8.5, 1)))
    elif kind == "tools":
        path = _poly((1.5, -8), (-5.5, 1.5), (-0.5, 1.5), (-1.5, 8), (5.5, -1.5), (0.5, -1.5))
        path.closeSubpath()
        p.drawPath(path)
    elif kind == "rocket":
        path = QPainterPath(QPointF(0, -8.5))
        path.cubicTo(4.5, -5, 4.5, 1, 2.6, 4.5)
        path.lineTo(-2.6, 4.5)
        path.cubicTo(-4.5, 1, -4.5, -5, 0, -8.5)
        p.drawPath(path)
        p.drawEllipse(QPointF(0, -2.2), 1.5, 1.5)
        line(-3.2, 2.2, -6, 6)
        line(3.2, 2.2, 6, 6)
        line(0, 6.5, 0, 8.5)
    elif kind == "power":
        p.drawArc(QRectF(-6.5, -5.5, 13, 13), int(130 * 16), int(280 * 16))
        line(0, -8, 0, -1)
    elif kind == "rball":
        p.drawEllipse(QPointF(0, 0), 8.6, 8.6)
        f = QFont()
        f.setFamilies(["Segoe UI Variable", "Segoe UI", "Arial"])
        f.setPixelSize(11)
        f.setWeight(QFont.Weight.ExtraBold)
        p.setFont(f)
        p.drawText(QRectF(-8, -8.4, 16.6, 16), int(Qt.AlignmentFlag.AlignCenter), "R")
    elif kind in ("volume", "muted"):
        p.setBrush(fg)
        path = _poly((-7.5, -2.6), (-4.2, -2.6), (0.2, -6.5), (0.2, 6.5), (-4.2, 2.6), (-7.5, 2.6))
        path.closeSubpath()
        p.drawPath(path)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if kind == "volume":
            p.drawArc(QRectF(-3.5, -4.5, 9, 9), -50 * 16, 100 * 16)
            p.drawArc(QRectF(-4.5, -8, 15, 16), -50 * 16, 100 * 16)
        else:
            line(3.5, -3, 8.5, 3)
            line(3.5, 3, 8.5, -3)
    elif kind == "timer":
        p.drawEllipse(QPointF(0, 1.5), 6.5, 6.5)
        line(0, 1.5, 0, -2.5)
        line(0, 1.5, 2.6, 3)
        line(-2, -8, 2, -8)
        line(0, -8, 0, -5)
    elif kind == "gem":
        p.drawPath(_poly((-8, -2), (-4, -7), (4, -7), (8, -2), (0, 8), (-8, -2)))
        p.drawPath(_poly((-8, -2), (8, -2)))
        p.drawPath(_poly((-3, -2), (0, 8), (3, -2)))
    elif kind == "spark":
        star = _poly((0, -8.5), (2.2, -2.2), (8.5, 0), (2.2, 2.2), (0, 8.5), (-2.2, 2.2), (-8.5, 0), (-2.2, -2.2))
        star.closeSubpath()
        p.drawPath(star)
    elif kind == "grid":
        for gx, gy in ((-7.5, -7.5), (1.5, -7.5), (-7.5, 1.5), (1.5, 1.5)):
            p.drawRoundedRect(QRectF(gx, gy, 6, 6), 1.5, 1.5)
    elif kind == "ball":
        p.drawEllipse(QPointF(0, 0), 5.5, 5.5)
        p.setBrush(fg)
        p.drawEllipse(QPointF(0, 0), 1.6, 1.6)
    elif kind == "shuffle":
        p.drawPath(_poly((-7.5, -4), (-3.5, -4), (2.5, 4), (7, 4)))
        p.drawPath(_poly((-7.5, 4), (-3.5, 4), (-1.6, 1.4)))
        p.drawPath(_poly((1, -2), (2.5, -4), (7, -4)))
        p.drawPath(_poly((5, -6), (7.3, -4), (5, -2)))
        p.drawPath(_poly((5, 2), (7.3, 4), (5, 6)))
    elif kind in ("repeat", "repeat1"):
        p.drawPath(_poly((-6.5, -0.5), (-6.5, -2), (-4.5, -4), (6, -4)))
        p.drawPath(_poly((6.5, 0.5), (6.5, 2), (4.5, 4), (-6, 4)))
        p.drawPath(_poly((4, -6.2), (6.4, -4), (4, -1.8)))
        p.drawPath(_poly((-4, 6.2), (-6.4, 4), (-4, 1.8)))
        if kind == "repeat1":
            p.setFont(_tiny_font())
            p.drawText(QRectF(-4, -4, 8, 8), int(Qt.AlignmentFlag.AlignCenter), "1")
    elif kind == "lock":
        p.drawRoundedRect(QRectF(-5, -1, 10, 8), 2, 2)
        p.drawArc(QRectF(-3.2, -7, 6.4, 9), 0, 180 * 16)
    elif kind == "folder":
        p.drawPath(_poly((-7.5, 6), (-7.5, -5.5), (-2.5, -5.5), (-0.5, -3), (7.5, -3), (7.5, 6), (-7.5, 6)))
    elif kind == "copy":
        p.drawRoundedRect(QRectF(-3, -3, 10, 10), 2, 2)
        p.drawPath(_poly((-7, 3), (-7, -7), (3, -7)))
    elif kind == "trash":
        line(-6.5, -4.5, 6.5, -4.5)
        p.drawPath(_poly((-4.8, -4.5), (-4, 7), (4, 7), (4.8, -4.5)))
        line(-2, -7, 2, -7)
    elif kind == "plus":
        line(-6, 0, 6, 0)
        line(0, -6, 0, 6)
    elif kind == "check":
        p.drawPath(_poly((-6, 0.5), (-2, 4.5), (6.5, -4.5)))
    elif kind == "refresh":
        p.drawArc(QRectF(-6.5, -6.5, 13, 13), 40 * 16, 290 * 16)
        p.drawPath(_poly((2.2, -7.6), (6.2, -5.2), (3.6, -1.6)))
    elif kind == "note":
        p.setBrush(fg)
        p.drawEllipse(QPointF(-3.2, 5), 2.6, 2.1)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(_poly((-0.7, 5), (-0.7, -7), (5, -5), (5, -1.5)))
    elif kind == "chip":
        p.drawRoundedRect(QRectF(-5, -5, 10, 10), 1.5, 1.5)
        for k in (-2.5, 2.5):
            line(k, -8, k, -5)
            line(k, 5, k, 8)
            line(-8, k, -5, k)
            line(5, k, 8, k)
    elif kind == "key":
        p.drawEllipse(QPointF(-3.5, 0), 3.5, 3.5)
        p.drawPath(_poly((0, 0), (8, 0), (8, 3)))
        line(4.5, 0, 4.5, 2.5)
    p.restore()


def _tiny_font() -> QFont:
    f = QFont()
    f.setPixelSize(6)
    f.setWeight(QFont.Weight.Bold)
    return f


# --------------------------------------------------------------------------- #
# Buttons
# --------------------------------------------------------------------------- #
class IconButton(QAbstractButton):
    """Vector icon button with animated hover / press feedback (timings from the original app)."""

    def __init__(self, kind: str, size: int = 28, primary: bool = False, tip: str = "", parent=None) -> None:
        super().__init__(parent)
        self._kind = kind
        self._primary = primary
        self._size = size
        self.fade = 1.0                # opacity, used when the menu bar hides
        self.active = False            # accent tint (e.g. shuffle on)
        self.dot = False               # small accent dot under the icon
        self.setFixedSize(S(size), S(size))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if tip:
            self.setToolTip(tip)
        self._hover = Tween(self, on_change=self.update)
        self._press = Tween(self, on_change=self.update)

    def set_kind(self, kind: str) -> None:
        if kind != self._kind:
            self._kind = kind
            self.update()

    def set_active(self, on: bool) -> None:
        if on != self.active:
            self.active = self.dot = on
            self.update()

    def enterEvent(self, event) -> None:
        self._hover.to(1.0, 140)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover.to(0.0, 220)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press.to(1.0, 80)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._press.to(0.0, 170)
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        h, pr = self._hover.level, self._press.level
        p.setOpacity(self.fade)
        if not self.isEnabled():
            p.setOpacity(0.35 * self.fade)
            h = pr = 0.0
        scale = (self.width() / 28.0) * (1.0 + (0.07 if self._primary else 0.12) * h - 0.15 * pr)
        p.translate(self.width() / 2.0, self.height() / 2.0)
        p.scale(scale, scale)
        if self._primary:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(mix(QColor("#FFFFFF"), QColor("#D9D9D9"), pr))
            p.drawEllipse(QPointF(0, 0), 14, 14)
            fg = QColor("#000000")
            p.scale(0.82, 0.82)
        elif self.active:
            fg = mix(ui.accent, QColor(TEXT), 0.35 * h)
        else:
            fg = mix(mix(QColor(TEXT_DIM), QColor(TEXT), h), ui.accent, pr)
        p.scale(0.9, 0.9)
        draw_icon(p, self._kind, fg, h)
        if self.dot:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(ui.accent)
            p.drawEllipse(QPointF(0, 12.5), 1.4, 1.4)


class Button(QAbstractButton):
    """Text button: 'ghost' (neutral), 'primary' (accent), 'danger' (warm gradient), 'quiet' (text only)."""

    def __init__(self, text: str, kind: str = "ghost", height: int = 32, icon: str = "", parent=None) -> None:
        super().__init__(parent)
        self._text, self._kind, self._icon = text, kind, icon
        self.setFixedHeight(S(height))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._hover = Tween(self, on_change=self.update)
        self._press = Tween(self, on_change=self.update)
        self._font = font(12, QFont.Weight.DemiBold)
        self.fade = 1.0

    def set_text(self, text: str) -> None:
        self._text = text
        self.update()

    def set_kind(self, kind: str) -> None:
        self._kind = kind
        self.update()

    def sizeHint(self):
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QFontMetrics
        w = QFontMetrics(self._font).horizontalAdvance(self._text) + S(28) + (S(18) if self._icon else 0)
        return QSize(w, self.height())

    def enterEvent(self, e) -> None:
        self._hover.to(1.0, 140)
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover.to(0.0, 220)
        super().leaveEvent(e)

    def mousePressEvent(self, e) -> None:
        if self.fade < 0.5:                                 # faded out: let the click through
            e.ignore()
            return
        self._press.to(1.0, 80)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        self._press.to(0.0, 170)
        super().mouseReleaseEvent(e)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        h, pr = self._hover.level, self._press.level
        if self.fade < 0.01:
            return
        p.setOpacity(self.fade)
        if not self.isEnabled():
            p.setOpacity(0.4 * self.fade)
            h = pr = 0
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        inset = pr * S(1.5)
        r.adjust(inset, inset, -inset, -inset)
        rad = S(9)
        fg = QColor(TEXT)
        p.setPen(Qt.PenStyle.NoPen)
        if self._kind == "primary":
            p.setBrush(mix(ui.accent, QColor("#FFFFFF"), 0.14 * h))
            fg = QColor("#06110A")
        elif self._kind == "danger":
            p.setPen(QPen(alpha(DANGER, 0.45 + 0.25 * h), 1))
            p.setBrush(alpha(DANGER, 0.10 + 0.08 * h))
            fg = QColor("#FF8085")
        elif self._kind == "quiet":
            p.setBrush(alpha("#FFFFFF", 0.06 * h))
            fg = mix(QColor(TEXT_DIM), QColor(TEXT), h)
        else:
            p.setBrush(mix(QColor(SURFACE_HI), QColor("#3A3A3A"), h))
        p.drawRoundedRect(r, rad, rad)
        p.setFont(self._font)
        p.setPen(fg)
        if self._icon:
            tw = p.fontMetrics().horizontalAdvance(self._text)
            x0 = r.center().x() - (tw + S(20)) / 2
            p.save()
            p.translate(x0 + S(7), r.center().y())
            p.scale(S(14) / 20, S(14) / 20)
            draw_icon(p, self._icon, fg)
            p.restore()
            p.setPen(fg)
            p.drawText(QRectF(x0 + S(20), r.top(), tw + 4, r.height()), int(Qt.AlignmentFlag.AlignVCenter), self._text)
        else:
            text = p.fontMetrics().elidedText(self._text, Qt.TextElideMode.ElideRight, int(r.width() - S(12)))
            p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), text)


class Toggle(QAbstractButton):
    toggled_by_user = pyqtSignal(bool)

    def __init__(self, checked: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(S(38), S(22))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._pos = Tween(self, 1.0 if checked else 0.0, self.update, QEasingCurve.Type.OutBack)
        self._hover = Tween(self, on_change=self.update)
        self.clicked.connect(self._clicked)

    def _clicked(self) -> None:
        self._pos.to(1.0 if self.isChecked() else 0.0, 220)
        self.toggled_by_user.emit(self.isChecked())

    def set_checked(self, on: bool) -> None:
        if on != self.isChecked():
            self.setChecked(on)
            self._pos.to(1.0 if on else 0.0, 220)

    def enterEvent(self, e) -> None:
        self._hover.to(1.0, 140)

    def leaveEvent(self, e) -> None:
        self._hover.to(0.0, 220)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        if not self.isEnabled():
            p.setOpacity(0.4)
        t = max(0.0, min(1.0, self._pos.level))
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        on = mix(QColor("#3A3F42"), ui.accent, t)
        light = ui.accent.lightnessF() > 0.72                     # white / pale album colours
        edge = mix(alpha("#FFFFFF", 0.14), mix(ui.accent, QColor("#000000"), 0.45) if light else alpha(ui.accent, 0.0), t)
        p.setPen(QPen(edge, 1.2))
        p.setBrush(on)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        kr = r.height() / 2 - S(2.5) + self._hover.level * S(0.8)
        x = r.left() + r.height() / 2 + t * (r.width() - r.height())
        knob = mix(QColor("#FFFFFF"), QColor("#0E1213"), t if light else 0.0)
        p.setPen(QPen(alpha("#000000", 0.35), 1) if not light else Qt.PenStyle.NoPen)
        p.setBrush(knob)
        p.drawEllipse(QPointF(x, r.center().y()), kr, kr)


class Slider(QWidget):
    changed = pyqtSignal(float)       # while dragging
    released = pyqtSignal(float)      # drag finished

    def __init__(self, lo: float, hi: float, value: float, step: float = 1.0,
                 default: Optional[float] = None, ticks: int = 0, marks=None, parent=None) -> None:
        super().__init__(parent)
        self.lo, self.hi, self.step = lo, hi, step
        self.default = default
        self.ticks = ticks
        self.marks = sorted(set(marks or ([] if default is None else [default])))   # lock-in points
        self._value = self._snap(value)
        self.setFixedHeight(S(22))
        self.setMinimumWidth(S(60))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._shown = Tween(self, self._frac(self._value), self.update)
        self._hover = Tween(self, on_change=self.update)
        self._drag = False
        self.rainbow = False

    def _snap(self, v: float) -> float:
        v = max(self.lo, min(self.hi, v))
        return round(round((v - self.lo) / self.step) * self.step + self.lo, 6)

    def _frac(self, v: float) -> float:
        return (v - self.lo) / (self.hi - self.lo) if self.hi > self.lo else 0.0

    def value(self) -> float:
        return self._value

    def set_value(self, v: float, animate: bool = True) -> None:
        self._value = self._snap(v)
        if animate and self.isVisible():
            self._shown.to(self._frac(self._value), 180)
        else:
            self._shown.jump(self._frac(self._value))

    def _from_x(self, x: float) -> None:
        m = S(7)
        span = max(1, self.width() - 2 * m)
        f = max(0.0, min(1.0, (x - m) / span))
        v = self._snap(self.lo + f * (self.hi - self.lo))
        for mark in self.marks:                                  # the knob clicks into place near a mark
            if abs(m + span * self._frac(mark) - x) <= S(5):
                v = self._snap(mark)
                break
        self._shown.jump(self._frac(v))
        if v != self._value:
            self._value = v
            self.changed.emit(v)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag = True
            self._from_x(e.position().x())

    def mouseMoveEvent(self, e) -> None:
        if self._drag:
            self._from_x(e.position().x())

    def mouseReleaseEvent(self, e) -> None:
        if self._drag:
            self._drag = False
            self.released.emit(self._value)

    def mouseDoubleClickEvent(self, e) -> None:
        if self.default is not None:
            self.set_value(self.default)
            self.changed.emit(self._value)
            self.released.emit(self._value)

    def enterEvent(self, e) -> None:
        self._hover.to(1.0, 140)

    def leaveEvent(self, e) -> None:
        self._hover.to(0.0, 220)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        if not self.isEnabled():
            p.setOpacity(0.4)
        m, cy = S(7), self.height() / 2
        w = self.width() - 2 * m
        th = S(4)
        track = QRectF(m, cy - th / 2, w, th)
        p.setPen(Qt.PenStyle.NoPen)
        x = m + w * self._shown.level
        if self.rainbow:
            g = QLinearGradient(track.topLeft(), track.topRight())
            for i in range(7):
                g.setColorAt(i / 6, QColor.fromHsvF(min(0.999, i / 6), 0.9, 1.0))
            p.setBrush(g)
            p.drawRoundedRect(track, th / 2, th / 2)
        else:
            p.setBrush(QColor(TRACK))
            p.drawRoundedRect(track, th / 2, th / 2)
            p.setBrush(ui.accent)
            if self.lo < 0 < self.hi:                      # bipolar: fill from the centre
                zero = m + w * self._frac(0)
                p.drawRoundedRect(QRectF(min(zero, x), track.top(), abs(x - zero), th), th / 2, th / 2)
            else:
                p.drawRoundedRect(QRectF(m, track.top(), max(0.0, x - m), th), th / 2, th / 2)
        if self.ticks:
            p.setBrush(alpha("#FFFFFF", 0.25))
            for i in range(self.ticks + 1):
                p.drawRect(QRectF(m + w * i / self.ticks - 0.5, cy + th, 1, S(3)))
        for mark in self.marks:
            mx = m + w * self._frac(mark)
            p.setBrush(alpha("#FFFFFF", 0.55 if abs(mark - self._value) < 1e-6 else 0.22))
            p.drawEllipse(QPointF(mx, cy + th / 2 + S(4)), S(1.3), S(1.3))
        kr = S(5.5) + self._hover.level * S(1.2) + (S(1) if self._drag else 0)
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QPointF(x, cy), kr, kr)


class Segmented(QWidget):
    changed = pyqtSignal(int)

    def __init__(self, labels: list, index: int = 0, parent=None) -> None:
        super().__init__(parent)
        self._labels = labels
        self._index = max(0, min(len(labels) - 1, index))
        self.setFixedHeight(S(28))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pos = Tween(self, float(self._index), self.update, QEasingCurve.Type.OutBack)
        self._font = font(11.5, QFont.Weight.DemiBold)
        self.faint: set = set()           # options shown but not available

    def index(self) -> int:
        return self._index

    def set_index(self, i: int) -> None:
        i = max(0, min(len(self._labels) - 1, i))
        if i != self._index:
            self._index = i
            self._pos.to(float(i), 260)

    def mousePressEvent(self, e) -> None:
        i = int(e.position().x() / max(1, self.width()) * len(self._labels))
        i = max(0, min(len(self._labels) - 1, i))
        if i != self._index:
            self.set_index(i)
            self.changed.emit(i)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        if not self.isEnabled():
            p.setOpacity(0.4)
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.06))
        p.drawRoundedRect(r, S(8), S(8))
        n = len(self._labels)
        sw = r.width() / n
        pill = QRectF(self._pos.level * sw + S(2), S(2), sw - S(4), r.height() - S(4))
        p.setBrush(alpha(ui.accent, 0.22))
        p.drawRoundedRect(pill, S(6), S(6))
        p.setFont(self._font)
        for i, label in enumerate(self._labels):
            near = max(0.0, 1.0 - abs(self._pos.level - i))
            col = mix(QColor(TEXT_DIM), mix(ui.accent, QColor(TEXT), 0.55), near)
            if i in self.faint:
                col = alpha(TEXT_DIM, 0.35)
            p.setPen(col)
            cell = QRectF(i * sw, 0, sw, r.height())
            p.drawText(cell, int(Qt.AlignmentFlag.AlignCenter),
                       p.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, int(sw - S(6))))


class Swatches(QWidget):
    picked = pyqtSignal(str)

    def __init__(self, colors: list, current: str = "", per_row: int = 0, parent=None) -> None:
        super().__init__(parent)
        self._colors = colors
        self._current = current.upper()
        self._per_row = per_row or len(colors)
        rows = (len(colors) + self._per_row - 1) // self._per_row
        self.setFixedHeight(S(26) * rows)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_current(self, c: str) -> None:
        self._current = c.upper()
        self.update()

    def _cell(self) -> float:
        return min(S(28) if self._per_row == len(self._colors) else S(44), self.width() / max(1, self._per_row))

    def _centre(self, i: int) -> QPointF:
        cell = self._cell()
        return QPointF((i % self._per_row) * cell + cell / 2, (i // self._per_row) * S(26) + S(13))

    def mousePressEvent(self, e) -> None:
        cell = self._cell()
        col = int(e.position().x() / cell)
        i = col + int(e.position().y() / S(26)) * self._per_row
        if 0 <= col < self._per_row and 0 <= i < len(self._colors):
            self._current = self._colors[i].upper()
            self.update()
            self.picked.emit(self._colors[i])

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        for i, c in enumerate(self._colors):
            centre = self._centre(i)
            if c.upper() == self._current:
                p.setPen(QPen(QColor("#FFFFFF"), 1.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(centre, S(10), S(10))
            p.setPen(QPen(alpha("#FFFFFF", 0.18), 1))
            p.setBrush(QColor(c))
            p.drawEllipse(centre, S(7), S(7))


# --------------------------------------------------------------------------- #
# Text, panels, data widgets
# --------------------------------------------------------------------------- #
class Label(QWidget):
    """Painted label. Single line elides; pass wrap_w to wrap at a fixed width."""

    def __init__(self, text: str = "", px: float = 12, color: str = TEXT, bold: bool = False,
                 align=Qt.AlignmentFlag.AlignLeft, wrap_w: int = 0, weight=None, parent=None) -> None:
        super().__init__(parent)
        self._font = font(px, weight or (QFont.Weight.Bold if bold else QFont.Weight.Normal))
        self._color = QColor(color)
        self._align = align
        self._wrap_w = wrap_w
        self._text = ""
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        if wrap_w:
            self.setFixedWidth(wrap_w)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            self.setFixedHeight(S(px * 1.5))
        self.set_text(text)

    def set_text(self, text: str) -> None:
        if text == self._text:
            return
        self._text = text
        if self._wrap_w:
            from PyQt6.QtGui import QFontMetrics
            br = QFontMetrics(self._font).boundingRect(0, 0, self._wrap_w, 10000,
                                                      int(Qt.TextFlag.TextWordWrap), text)
            self.setFixedHeight(br.height() + 2)
        self.update()

    def set_color(self, color) -> None:
        self._color = QColor(color)
        self.update()

    def setFixedWidth(self, w: int) -> None:          # a fixed-width label must claim its space in layouts
        super().setFixedWidth(w)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def fit(self) -> "Label":
        self.setFixedWidth(self.text_width() + 2)
        return self

    def text(self) -> str:
        return self._text

    def text_width(self) -> int:
        from PyQt6.QtGui import QFontMetrics
        return QFontMetrics(self._font).horizontalAdvance(self._text)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setFont(self._font)
        p.setPen(self._color)
        if self._wrap_w:
            p.drawText(self.rect(), int(self._align | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap), self._text)
        else:
            text = p.fontMetrics().elidedText(self._text, Qt.TextElideMode.ElideRight, self.width())
            p.drawText(self.rect(), int(self._align | Qt.AlignmentFlag.AlignVCenter), text)


class Panel(QWidget):
    """Rounded elevated surface that hosts a layout."""

    def __init__(self, parent=None, tint: float = 0.045) -> None:
        super().__init__(parent)
        self._tint = tint
        self.accent_edge = False

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha(ui.accent, 0.45) if self.accent_edge else alpha("#FFFFFF", 0.06), 1))
        p.setBrush(alpha("#FFFFFF", self._tint))
        p.drawRoundedRect(r, S(10), S(10))


class Glyph(QWidget):
    """A vector icon inside a soft disc: used for designed empty / locked / unavailable states."""

    def __init__(self, kind: str, size: int = 56, parent=None) -> None:
        super().__init__(parent)
        self._kind = kind
        self.setFixedSize(S(size), S(size))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        c = QPointF(self.width() / 2, self.height() / 2)
        rad = self.width() / 2 - 1
        p.setPen(QPen(alpha(ui.accent, 0.35), 1))
        p.setBrush(alpha(ui.accent, 0.08))
        p.drawEllipse(c, rad, rad)
        p.translate(c)
        k = self.width() / 44
        p.scale(k, k)
        draw_icon(p, self._kind, mix(ui.accent, QColor(TEXT), 0.35))


class Sparkline(QWidget):
    def __init__(self, maximum: float = 100.0, height: int = 30, parent=None) -> None:
        super().__init__(parent)
        self._max = maximum
        self._auto = maximum <= 0
        self._data: deque = deque(maxlen=60)
        self.setFixedHeight(S(height))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def push(self, v: float) -> None:
        self._data.append(max(0.0, float(v)))
        self.update()

    def paintEvent(self, _e) -> None:
        if len(self._data) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(AA)
        w, h = self.width(), self.height() - 2
        top = max(self._data) * 1.15 if self._auto else self._max
        top = max(top, 1e-6)
        n = self._data.maxlen
        step = w / (n - 1)
        x0 = w - (len(self._data) - 1) * step
        path = QPainterPath()
        for i, v in enumerate(self._data):
            pt = QPointF(x0 + i * step, 1 + h - min(1.0, v / top) * h)
            path.lineTo(pt) if i else path.moveTo(pt)
        fill = QPainterPath(path)
        fill.lineTo(w, h + 2)
        fill.lineTo(x0, h + 2)
        fill.closeSubpath()
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, alpha(ui.accent, 0.30))
        g.setColorAt(1, alpha(ui.accent, 0.0))
        p.fillPath(fill, g)
        p.setPen(QPen(ui.accent, 1.5))
        p.drawPath(path)


class Gauge(QWidget):
    """270-degree arc gauge with an animated value."""

    def __init__(self, caption: str, unit: str = "%", size: int = 96, parent=None) -> None:
        super().__init__(parent)
        self._caption, self._unit = caption, unit
        self._text = "–"
        self.setFixedSize(S(size), S(size))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._v = Tween(self, 0.0, self.update)

    def set_value(self, fraction: Optional[float], text: str = "") -> None:
        if fraction is None:
            self._text = "–"
            self._v.to(0.0, 300)
        else:
            self._text = text or f"{round(fraction * 100)}"
            self._v.to(max(0.0, min(1.0, fraction)), 450)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        th = S(6)
        r = QRectF(self.rect()).adjusted(th, th, -th, -th)
        pen = QPen(QColor(TRACK), th)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(r, 225 * 16, -270 * 16)
        v = self._v.level
        col = ui.accent if v < 0.75 else mix(QColor(WARN), QColor(DANGER), (v - 0.75) * 4)
        if v > 0.004:
            pen.setColor(col)
            p.setPen(pen)
            p.drawArc(r, 225 * 16, int(-270 * 16 * v))
        p.setPen(QColor(TEXT))
        p.setFont(font(19, QFont.Weight.Bold))
        box = QRectF(0, self.height() * 0.28, self.width(), self.height() * 0.3)
        p.drawText(box, int(Qt.AlignmentFlag.AlignCenter), self._text)
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(9.5, QFont.Weight.DemiBold, 0.6))
        p.drawText(QRectF(0, self.height() * 0.56, self.width(), S(14)), int(Qt.AlignmentFlag.AlignCenter), self._unit)
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(0, self.height() - S(17), self.width(), S(15)), int(Qt.AlignmentFlag.AlignCenter),
                   self._caption)


class ProgressBar(QWidget):
    """4 px track; click or drag to seek when `seekable`."""
    seek = pyqtSignal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(S(12))
        self._fraction = 0.0
        self._px = -1
        self.seekable = False
        self._hover = Tween(self, on_change=self.update)

    def set_fraction(self, fraction: float) -> None:
        fraction = max(0.0, min(1.0, fraction))
        px = int(fraction * max(1, self.width()))
        self._fraction = fraction
        if px != self._px:           # repaint only when the bar visibly moves
            self._px = px
            self.update()

    def enterEvent(self, e) -> None:
        if self.seekable:
            self._hover.to(1.0, 140)

    def leaveEvent(self, e) -> None:
        self._hover.to(0.0, 220)

    def mousePressEvent(self, e) -> None:
        if self.seekable and e.button() == Qt.MouseButton.LeftButton:
            f = max(0.0, min(1.0, e.position().x() / max(1, self.width())))
            self._fraction, self._px = f, -1
            self.update()
            self.seek.emit(f)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        p.setPen(Qt.PenStyle.NoPen)
        th = S(4) + self._hover.level * S(1.5)
        r = QRectF(0, (self.height() - th) / 2, self.width(), th)
        p.setBrush(QColor(TRACK))
        p.drawRoundedRect(r, th / 2, th / 2)
        if self._fraction > 0:
            p.setBrush(ui.accent)
            fw = max(4.0, r.width() * self._fraction)
            p.drawRoundedRect(QRectF(0, r.top(), fw, th), th / 2, th / 2)
            if self._hover.level > 0.02:
                p.setBrush(alpha("#FFFFFF", self._hover.level))
                p.drawEllipse(QPointF(min(fw, r.width() - S(4)), r.center().y()), S(4.5), S(4.5))


class ArtWidget(QWidget):
    """Rounded album cover with a 280 ms cross-fade and a note placeholder. Click = open the player."""
    clicked = pyqtSignal()

    def __init__(self, size: int, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(S(size), S(size))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pixmap: Optional[QPixmap] = None
        self._fade = Tween(self, 1.0, self.update, QEasingCurve.Type.InOutQuad)

    def set_pixmap(self, pixmap: Optional[QPixmap]) -> None:
        if pixmap is None or pixmap.isNull():
            self._pixmap = None
            self._fade.jump(1.0)
            self.update()
            return
        target = int(self.width() * self.devicePixelRatioF())
        self._pixmap = pixmap.scaled(target, target, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                     Qt.TransformationMode.SmoothTransformation)
        self._fade.jump(0.0)
        self._fade.to(1.0, 280)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHints(AA | QPainter.RenderHint.SmoothPixmapTransform)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), S(10), S(10))
        p.setClipPath(clip)
        p.fillRect(self.rect(), QColor("#1C2122"))
        if self._pixmap is None or self._fade.level < 1.0:
            p.save()
            p.translate(self.width() / 2, self.height() / 2)
            k = self.width() / 50
            p.scale(k, k)
            draw_icon(p, "note", QColor(PLACEHOLDER))
            p.restore()
        if self._pixmap is not None:
            pm = self._pixmap
            side = min(pm.width(), pm.height())
            src = QRectF((pm.width() - side) / 2, (pm.height() - side) / 2, side, side)
            p.setOpacity(self._fade.level)
            p.drawPixmap(QRectF(self.rect()), pm, src)
            p.setOpacity(1.0)
        p.setClipping(False)
        p.setPen(QPen(alpha("#FFFFFF", 0.07), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), S(10), S(10))


# --------------------------------------------------------------------------- #
# Scroll area (inertial wheel, thin thumb, fading edges)
# --------------------------------------------------------------------------- #
class _ScrollOverlay(QWidget):
    def __init__(self, area: "ScrollArea") -> None:
        super().__init__(area)
        self._area = area
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        a = self._area
        span = a.max_offset()
        if span <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(AA)
        w, h, fade = self.width(), self.height(), S(18)
        bg = mix(ui.bg_top, ui.bg_bottom, 0.5)
        if a.offset() > 1:
            g = QLinearGradient(0, 0, 0, fade)
            g.setColorAt(0, bg)
            g.setColorAt(1, alpha(bg, 0))
            p.fillRect(QRectF(0, 0, w, fade), g)
        if a.offset() < span - 1:
            g = QLinearGradient(0, h - fade, 0, h)
            g.setColorAt(0, alpha(bg, 0))
            g.setColorAt(1, bg)
            p.fillRect(QRectF(0, h - fade, w, fade), g)
        th = max(S(24), h * h / (h + span))
        y = (h - th) * a.offset() / span
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.22))
        p.drawRoundedRect(QRectF(w - S(3), y, S(3), th), S(1.5), S(1.5))


class ScrollArea(QWidget):
    GUTTER = 8        # the thumb lives in this strip, right of the content

    def __init__(self, content: QWidget, content_h: int, parent=None) -> None:
        super().__init__(parent)
        self.content = content
        content.setParent(self)
        self._content_h = content_h
        self._target = 0.0
        self._pos = Tween(self, 0.0, self._apply)
        self._overlay = _ScrollOverlay(self)

    def offset(self) -> float:
        return self._pos.level

    def max_offset(self) -> float:
        return max(0.0, self._content_h - self.height())

    def _apply(self) -> None:
        self.content.move(0, -int(round(self._pos.level)))
        self._overlay.update()

    def resizeEvent(self, _e) -> None:
        self.content.setGeometry(0, -int(round(self._pos.level)), self.width() - S(self.GUTTER),
                                 max(self._content_h, self.height()))
        self._overlay.setGeometry(self.rect())
        self._overlay.raise_()
        if self._target > self.max_offset():
            self._target = self.max_offset()
            self._pos.jump(self._target)

    def wheelEvent(self, e) -> None:
        if self.max_offset() > 0:
            self._target = max(0.0, min(self.max_offset(), self._target - e.angleDelta().y() / 120 * S(70)))
            self._pos.to(self._target, 280)
        e.accept()


# --------------------------------------------------------------------------- #
# Tab bar: icon tabs, the active one opens into a labelled accent pill
# --------------------------------------------------------------------------- #
class TabBar(QWidget):
    SLOT = 27
    fade = 1.0
    changed = pyqtSignal(str)

    def __init__(self, tabs: list, current: str, parent=None) -> None:
        """tabs: [(key, icon, label, locked)]"""
        super().__init__(parent)
        self._tabs = tabs
        self._current = current
        self._hover_i = -1
        self._full_h = S(30)
        self.setMinimumHeight(1)
        self.setMaximumHeight(self._full_h)
        self.resize(self.width(), self._full_h)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._font = font(11.5, QFont.Weight.DemiBold)
        self._w = [Tween(self, 1.0 if t[0] == current else 0.0, self.update, QEasingCurve.Type.OutBack) for t in tabs]
        self._h = [Tween(self, 0.0, self.update) for _ in tabs]
        from PyQt6.QtGui import QFontMetrics
        fm = QFontMetrics(self._font)
        self._lw = [fm.horizontalAdvance(t[2]) + S(8) for t in tabs]

    def set_current(self, key: str) -> None:
        self._current = key
        for i, t in enumerate(self._tabs):
            self._w[i].to(1.0 if t[0] == key else 0.0, 320)

    def set_locked(self, key: str, locked: bool) -> None:
        self._tabs = [(k, i, l, locked if k == key else lk) for k, i, l, lk in self._tabs]
        self.update()

    def _slot(self) -> float:
        """Icon slot width: shrinks a little when the open label would not fit otherwise."""
        n = len(self._tabs)
        return min(float(S(self.SLOT)), (self.width() - max(self._lw)) / n)

    def _rects(self) -> list:
        n, slot = len(self._tabs), self._slot()
        gap = max(0.0, (self.width() - n * slot - max(self._lw)) / max(1, n - 1))
        out, x = [], 0.0
        for i in range(n):
            w = slot + self._lw[i] * max(0.0, self._w[i].level)
            out.append(QRectF(x, 0, w, self._full_h))
            x += w + gap
        return out

    def _index_at(self, x: float) -> int:
        for i, r in enumerate(self._rects()):
            if r.left() - 2 <= x <= r.right() + 2:
                return i
        return -1

    def mouseMoveEvent(self, e) -> None:
        i = self._index_at(e.position().x())
        if i != self._hover_i:
            if self._hover_i >= 0:
                self._h[self._hover_i].to(0.0, 220)
            self._hover_i = i
            if i >= 0:
                self._h[i].to(1.0, 140)
                self.setToolTip(self._tabs[i][2])

    def leaveEvent(self, _e) -> None:
        if self._hover_i >= 0:
            self._h[self._hover_i].to(0.0, 220)
        self._hover_i = -1

    def mousePressEvent(self, e) -> None:
        i = self._index_at(e.position().x())
        if i >= 0 and self._tabs[i][0] != self._current:
            self.changed.emit(self._tabs[i][0])

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        p.setOpacity(self.fade)
        if self.height() < self._full_h:                    # squashing away
            p.translate(0, self.height() / 2)
            p.scale(1.0, self.height() / self._full_h)
            p.translate(0, -self._full_h / 2)
        slot = self._slot()
        for i, (r, (key, icon, label, locked)) in enumerate(zip(self._rects(), self._tabs)):
            w, h = max(0.0, min(1.0, self._w[i].level)), self._h[i].level
            if w > 0.01 or h > 0.01:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(mix(alpha("#FFFFFF", 0.07 * h), alpha(ui.accent, 0.18), w))
                p.drawRoundedRect(r.adjusted(0, S(1), 0, -S(1)), S(9), S(9))
            fg = mix(mix(QColor(TEXT_DIM), QColor(TEXT), h), ui.accent, w)
            p.save()
            p.translate(r.left() + slot / 2, r.center().y())
            k = S(15.5) / 20
            p.scale(k, k)
            draw_icon(p, icon, fg, max(h, w))
            if locked:
                p.translate(8.5, -7.5)
                p.scale(0.42, 0.42)
                draw_icon(p, "lock", QColor(TEXT_FAINT))
            p.restore()
            if w > 0.05:
                p.save()
                p.setClipRect(r)
                p.setOpacity(w)
                p.setFont(self._font)
                p.setPen(mix(ui.accent, QColor(TEXT), 0.45))
                p.drawText(QRectF(r.left() + slot - S(3), 0, self._lw[i], self._full_h),
                           int(Qt.AlignmentFlag.AlignVCenter), label)
                p.restore()


# --------------------------------------------------------------------------- #
# Layout helpers
# --------------------------------------------------------------------------- #
def snapshot(widget: QWidget) -> QPixmap:
    """Render a widget and its children onto a transparent pixmap (works while it is hidden)."""
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QRegion
    dpr = widget.devicePixelRatioF()
    pm = QPixmap(max(1, int(widget.width() * dpr)), max(1, int(widget.height() * dpr)))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    widget.render(pm, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
    return pm


def vbox(parent=None, spacing: float = 8, margins=(0, 0, 0, 0)) -> QVBoxLayout:
    lay = QVBoxLayout(parent) if parent is not None else QVBoxLayout()
    lay.setContentsMargins(*[S(m) for m in margins])
    lay.setSpacing(S(spacing))
    return lay


def hbox(parent=None, spacing: float = 8, margins=(0, 0, 0, 0)) -> QHBoxLayout:
    lay = QHBoxLayout(parent) if parent is not None else QHBoxLayout()
    lay.setContentsMargins(*[S(m) for m in margins])
    lay.setSpacing(S(spacing))
    return lay


def heading(text: str) -> Label:
    return Label(text.upper(), 10, TEXT_FAINT, weight=QFont.Weight.Bold)


def row(label: str, control: QWidget, sub: str = "", height: int = 30) -> QWidget:
    """Label on the left (optional dim sub-line), control on the right."""
    w = QWidget()
    w.setFixedHeight(S(height + (12 if sub else 0)))
    lay = hbox(w, 10)
    if sub:
        col = vbox(spacing=0)
        col.addStretch(1)
        col.addWidget(Label(label, 12.5))
        col.addWidget(Label(sub, 10.5, TEXT_FAINT))
        col.addStretch(1)
        lay.addLayout(col, 1)
    else:
        lay.addWidget(Label(label, 12.5), 1)
    lay.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
    return w


class SliderRow(QWidget):
    """Label + slider + live value. Double-click the slider to reset."""
    changed = pyqtSignal(float)
    released = pyqtSignal(float)

    def __init__(self, label: str, lo: float, hi: float, value: float, step: float = 1.0,
                 default: Optional[float] = None, fmt: Callable[[float], str] = lambda v: f"{v:g}",
                 label_w: int = 96, marks=None, parent=None) -> None:
        super().__init__(parent)
        self._fmt = fmt
        self.setFixedHeight(S(26))
        lay = hbox(self, 6)
        name = Label(label, 12)
        name.setFixedWidth(max(S(label_w), name.text_width() + S(8)))
        self.name = name
        self.slider = Slider(lo, hi, value, step, default, marks=marks)
        self._val = Label(fmt(self.slider.value()), 11, TEXT_DIM, align=Qt.AlignmentFlag.AlignRight)
        self._val.setFixedWidth(S(42))
        lay.addWidget(name)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self._val)
        self.slider.changed.connect(self._on)
        self.slider.released.connect(self.released)

    def _on(self, v: float) -> None:
        self._val.set_text(self._fmt(v))
        self.changed.emit(v)

    def value(self) -> float:
        return self.slider.value()

    def set_value(self, v: float) -> None:
        self.slider.set_value(v)
        self._val.set_text(self._fmt(self.slider.value()))


def notice(icon: str, title: str, text: str, width: int, button: Optional[QWidget] = None) -> QWidget:
    """Designed explained state: used instead of ever showing a dead control."""
    panel = Panel()
    lay = hbox(panel, 10, (10, 9, 10, 9))
    lay.addWidget(Glyph(icon, 34), 0, Qt.AlignmentFlag.AlignTop)
    col = vbox(spacing=2)
    col.addWidget(Label(title, 12, bold=True))
    col.addWidget(Label(text, 10.5, TEXT_DIM, wrap_w=width - S(34 + 10 + 20)))
    if button is not None:
        col.addSpacing(S(4))
        col.addWidget(button)
    lay.addLayout(col, 1)
    return panel


def align_slider_rows(page: QWidget) -> None:
    """Give every slider row on a page the same label width: wide enough for the longest label,
    so no label is cut short and all sliders still line up."""
    rows = page.findChildren(SliderRow)
    if rows:
        width = min(S(170), max(r.name.width() for r in rows))
        for r in rows:
            r.name.setFixedWidth(width)


class KeyChip(QWidget):
    """A keyboard key drawn as a small rounded cap, e.g. Ctrl + F1."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text
        self._font = font(10.5, QFont.Weight.Bold)
        from PyQt6.QtGui import QFontMetrics
        self.setFixedSize(QFontMetrics(self._font).horizontalAdvance(text) + S(14), S(20))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(AA)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -1.5)
        p.setPen(QPen(alpha("#FFFFFF", 0.22), 1))
        p.setBrush(alpha("#FFFFFF", 0.07))
        p.drawRoundedRect(r, S(5), S(5))
        p.setPen(QColor(TEXT))
        p.setFont(self._font)
        p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), self._text)


# ==================================================================================================
# SECTION: media
# ==================================================================================================
import asyncio
import ctypes
import hashlib
import logging
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger("rubenium.media")

MAX_ART_BYTES = 4 * 1024 * 1024
ART_ATTEMPTS = 3
CMD_PREV, CMD_TOGGLE, CMD_NEXT, CMD_SHUFFLE, CMD_REPEAT, CMD_SEEK = "prev", "toggle", "next", "shuffle", "repeat", "seek"

WIN_INSTALL_HINT = ("pip install winrt-runtime winrt-Windows.Foundation winrt-Windows.Foundation.Collections "
                    "winrt-Windows.Media winrt-Windows.Media.Control winrt-Windows.Storage.Streams")

APP_NAMES = [("spotify", "Spotify"), ("applemusic", "Apple Music"), ("itunes", "iTunes"), ("deezer", "Deezer"),
             ("tidal", "TIDAL"), ("amazon", "Amazon Music"), ("qobuz", "Qobuz"), ("youtubemusic", "YouTube Music"),
             ("ytmdesktop", "YouTube Music"), ("soundcloud", "SoundCloud"), ("chrome", "Chrome"),
             ("msedge", "Edge"), ("firefox", "Firefox"), ("opera", "Opera"), ("brave", "Brave"),
             ("vivaldi", "Vivaldi"), ("arc", "Arc"), ("vlc", "VLC"), ("foobar", "foobar2000"),
             ("musicbee", "MusicBee"), ("aimp", "AIMP"), ("winamp", "Winamp"), ("zunemusic", "Media Player"),
             ("wmplayer", "Media Player"), ("mediaplayer", "Media Player"), ("plex", "Plex"), ("cider", "Cider"),
             ("discord", "Discord")]


def pretty_source(app_id: str) -> str:
    low = (app_id or "").lower()
    for needle, name in APP_NAMES:
        if needle in low:
            return name
    base = os.path.basename(app_id or "").split("!")[0]
    base = base[:-4] if base.lower().endswith(".exe") else base
    return (base.split("_")[0].split(".")[-1] or "Media").strip()[:18] or "Media"


def source_keywords(app_id: str) -> list:
    """Words to look for in a process name to find the window of this media source."""
    low = (app_id or "").lower()
    if low.endswith(".exe"):
        return [os.path.basename(low)[:-4]]
    special = {"zunemusic": "microsoft.media.player", "applemusic": "applemusic", "itunes": "itunes"}
    for needle, _name in APP_NAMES:
        if needle in low:
            return [special.get(needle, needle)]
    return []


class Status(Enum):
    PLAYING = auto()
    PAUSED = auto()
    STOPPED = auto()
    NOT_RUNNING = auto()
    UNAVAILABLE = auto()   # permanent problem (missing package, unsupported OS)
    ERROR = auto()         # transient problem


@dataclass(frozen=True)
class TrackState:
    status: Status
    title: str = ""
    artist: str = ""
    album: str = ""
    position_ms: int = 0
    duration_ms: int = 0
    message: str = ""
    source_id: str = ""
    source: str = ""
    shuffle: Optional[bool] = None      # None = the app does not expose it
    repeat: Optional[int] = None        # 0 off, 1 track, 2 list
    can_seek: bool = False
    can_prev: bool = True
    can_next: bool = True
    sources: tuple = ()                 # ((id, name), ...) of every app with a media session

    @property
    def has_track(self) -> bool:
        return self.status in (Status.PLAYING, Status.PAUSED) and bool(self.title)

    @property
    def art_key(self) -> str:
        if not self.has_track:
            return ""
        return f"{self.title}\x1f{self.artist}\x1f{self.album}\x1f{self.source_id}"


class BackendUnavailable(RuntimeError):
    pass


def _td_ms(value) -> int:
    try:
        return int(value.total_seconds() * 1000)
    except Exception:  # noqa: BLE001
        return 0


class WindowsBackend:
    art_may_lag = True

    def __init__(self, wake) -> None:
        try:
            from winrt.windows.media.control import (  # type: ignore
                GlobalSystemMediaTransportControlsSessionManager as Manager,
                GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
            )
            from winrt.windows.storage.streams import Buffer, DataReader, InputStreamOptions  # type: ignore
        except ImportError:
            try:  # legacy projection
                from winsdk.windows.media.control import (  # type: ignore
                    GlobalSystemMediaTransportControlsSessionManager as Manager,
                    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
                )
                from winsdk.windows.storage.streams import Buffer, DataReader, InputStreamOptions  # type: ignore
            except ImportError as exc:
                raise BackendUnavailable(WIN_INSTALL_HINT) from exc
        self._repeat_enum = None
        for mod in ("winrt.windows.media", "winsdk.windows.media"):
            try:
                self._repeat_enum = __import__(mod, fromlist=["MediaPlaybackAutoRepeatMode"]).MediaPlaybackAutoRepeatMode
                break
            except Exception:  # noqa: BLE001
                continue
        self._PlaybackStatus = PlaybackStatus
        self._Buffer, self._DataReader, self._InputStreamOptions = Buffer, DataReader, InputStreamOptions
        try:  # join the multithreaded apartment for this worker thread
            ctypes.windll.ole32.CoInitializeEx(None, 0)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        self._wake = wake
        self._loop = asyncio.new_event_loop()
        self._manager = self._run(Manager.request_async())
        self._thumb_ref = None
        self._hooked = None            # (session, id, tokens) kept alive so events keep firing
        self._rehook = False
        self.preferred = ""
        self.events = False
        try:
            self._manager.add_sessions_changed(self._on_sessions)
            self._manager.add_current_session_changed(self._on_sessions)
            self.events = True
        except Exception as exc:  # noqa: BLE001
            log.info("GSMTC manager events unavailable, polling only: %s", exc)

    # -- helpers
    def _run(self, awaitable):
        async def _await():
            return await awaitable
        return self._loop.run_until_complete(_await())

    def _on_sessions(self, *_a) -> None:
        self._rehook = True
        self._wake()

    def _on_change(self, *_a) -> None:
        self._wake()

    def _hook(self, session, sid: str) -> None:
        if self._hooked and self._hooked[1] == sid and not self._rehook:
            return
        self._unhook()
        self._rehook = False
        tokens = []
        try:
            tokens.append(("remove_media_properties_changed", session.add_media_properties_changed(self._on_change)))
            tokens.append(("remove_playback_info_changed", session.add_playback_info_changed(self._on_change)))
        except Exception as exc:  # noqa: BLE001
            log.debug("session events unavailable: %s", exc)
        self._hooked = (session, sid, tokens)

    def _unhook(self) -> None:
        if self._hooked:
            session, _sid, tokens = self._hooked
            for name, token in tokens:
                try:
                    getattr(session, name)(token)
                except Exception:  # noqa: BLE001
                    pass
        self._hooked = None

    def _sessions(self) -> list:
        try:
            return list(self._manager.get_sessions())
        except Exception:  # noqa: BLE001
            return []

    def _pick(self, sessions: list):
        """Pinned source if present; otherwise whatever is playing; otherwise Windows' current session."""
        if not sessions:
            return None
        ps = self._PlaybackStatus

        def sid(s):
            return s.source_app_user_model_id or ""

        def playing(s):
            try:
                return s.get_playback_info().playback_status == ps.PLAYING
            except Exception:  # noqa: BLE001
                return False

        if self.preferred:
            for s in sessions:
                if sid(s) == self.preferred:
                    return s
        current = None
        try:
            current = self._manager.get_current_session()
        except Exception:  # noqa: BLE001
            pass
        if current is not None and playing(current):
            return current
        for s in sessions:
            if playing(s):
                return s
        return current or sessions[0]

    # -- API
    def poll(self) -> TrackState:
        sessions = self._sessions()
        sources = tuple((s.source_app_user_model_id or "", pretty_source(s.source_app_user_model_id or ""))
                        for s in sessions)
        session = self._pick(sessions)
        if session is None:
            self._thumb_ref = None
            self._unhook()
            return TrackState(Status.NOT_RUNNING)
        sid = session.source_app_user_model_id or ""
        self._hook(session, sid)
        common = dict(source_id=sid, source=pretty_source(sid), sources=sources)

        props = self._run(session.try_get_media_properties_async())
        info = session.get_playback_info()
        timeline = session.get_timeline_properties()
        self._thumb_ref = props.thumbnail

        title = (props.title or "").strip()
        ps = self._PlaybackStatus
        if not title or info.playback_status in (ps.STOPPED, ps.CLOSED):
            return TrackState(Status.STOPPED, **common)
        playing = info.playback_status == ps.PLAYING

        start = _td_ms(timeline.start_time)
        duration = max(0, _td_ms(timeline.end_time) - start)
        position = max(0, _td_ms(timeline.position) - start)
        if playing:  # SMTC reports the position at 'last_updated_time'
            try:
                stamp = timeline.last_updated_time
                if stamp.year > 2000:
                    if stamp.tzinfo is None:
                        stamp = stamp.replace(tzinfo=timezone.utc)
                    position += int((datetime.now(timezone.utc) - stamp).total_seconds() * 1000)
            except Exception:  # noqa: BLE001
                pass
        if duration:
            position = min(position, duration)

        shuffle = repeat = None
        can_seek, can_prev, can_next = False, True, True
        try:
            controls = info.controls
            can_prev, can_next = bool(controls.is_previous_enabled), bool(controls.is_next_enabled)
            can_seek = bool(controls.is_playback_position_enabled) and duration > 0
            if controls.is_shuffle_enabled and info.is_shuffle_active is not None:
                shuffle = bool(info.is_shuffle_active)
            if controls.is_repeat_enabled and self._repeat_enum is not None and info.auto_repeat_mode is not None:
                repeat = int(info.auto_repeat_mode)
        except Exception as exc:  # noqa: BLE001
            log.debug("controls unreadable: %s", exc)

        return TrackState(
            Status.PLAYING if playing else Status.PAUSED, title=title,
            artist=(props.artist or "").strip(), album=(props.album_title or "").strip(),
            position_ms=position, duration_ms=duration, shuffle=shuffle, repeat=repeat,
            can_seek=can_seek, can_prev=can_prev, can_next=can_next, **common)

    def fetch_artwork(self, state: TrackState) -> Optional[bytes]:
        ref = self._thumb_ref
        if ref is None:
            return None

        async def _read() -> Optional[bytes]:
            stream = await ref.open_read_async()
            try:
                buf = self._Buffer(MAX_ART_BYTES)
                await stream.read_async(buf, buf.capacity, self._InputStreamOptions.READ_AHEAD)
                reader = self._DataReader.from_buffer(buf)
                data = bytearray(reader.unconsumed_buffer_length)
                reader.read_bytes(data)
                return bytes(data) or None
            finally:
                try:
                    stream.close()
                except Exception:  # noqa: BLE001
                    pass

        return self._run(_read())

    def send(self, command: str, arg, state: Optional[TrackState]) -> None:
        session = self._pick(self._sessions())
        if session is None:
            if command == CMD_TOGGLE:          # nothing is running: open the default player
                try:
                    os.startfile("spotify:")   # type: ignore[attr-defined]  # noqa: S606
                except OSError:
                    pass
            return
        if command == CMD_PREV:
            self._run(session.try_skip_previous_async())
        elif command == CMD_NEXT:
            self._run(session.try_skip_next_async())
        elif command == CMD_TOGGLE:
            self._run(session.try_toggle_play_pause_async())
        elif command == CMD_SHUFFLE and state is not None and state.shuffle is not None:
            self._run(session.try_change_shuffle_active_async(not state.shuffle))
        elif command == CMD_REPEAT and state is not None and state.repeat is not None and self._repeat_enum:
            nxt = {0: 2, 2: 1, 1: 0}.get(state.repeat, 0)       # off -> list -> track -> off
            self._run(session.try_change_auto_repeat_mode_async(self._repeat_enum(nxt)))
        elif command == CMD_SEEK and arg is not None:
            start = 0
            try:
                start = _td_ms(session.get_timeline_properties().start_time)
            except Exception:  # noqa: BLE001
                pass
            self._run(session.try_change_playback_position_async(int((int(arg) + start) * 10000)))

    def close(self) -> None:
        self._unhook()
        try:
            self._loop.close()
        except Exception:  # noqa: BLE001
            pass


class DemoBackend:
    """Fake player used for UI development on non-Windows machines (RUBENIUM_DEMO=1)."""
    art_may_lag = False
    events = False
    preferred = ""

    def __init__(self, wake) -> None:
        self._t0 = time.monotonic()
        self._playing, self._shuffle, self._repeat = True, False, 0

    def poll(self) -> TrackState:
        pos = int((time.monotonic() - self._t0) * 1000) % 215000 if self._playing else 42000
        return TrackState(Status.PLAYING if self._playing else Status.PAUSED, "Midnight City", "M83",
                          "Hurry Up, We're Dreaming", pos, 243000, source_id="Spotify.exe", source="Spotify",
                          shuffle=self._shuffle, repeat=self._repeat, can_seek=True,
                          sources=(("Spotify.exe", "Spotify"), ("chrome.exe", "Chrome")))

    def fetch_artwork(self, state):
        return None

    def send(self, command, arg, state) -> None:
        if command == CMD_TOGGLE:
            self._playing = not self._playing
        elif command == CMD_SHUFFLE:
            self._shuffle = not self._shuffle
        elif command == CMD_REPEAT:
            self._repeat = {0: 2, 2: 1, 1: 0}[self._repeat]

    def close(self) -> None:
        pass


class MediaService(QThread):
    """Worker thread: keeps every OS call off the UI thread."""
    state_changed = pyqtSignal(object)        # TrackState
    artwork_ready = pyqtSignal(str, bytes)    # art_key, image bytes

    def __init__(self, preferred: str = "", parent=None) -> None:
        super().__init__(parent)
        self._commands: "queue.Queue[tuple]" = queue.Queue()
        self._wake = threading.Event()
        self._halt = threading.Event()
        self._preferred = preferred
        self._art_key = ""
        self._art_digest: Optional[bytes] = None
        self._art_polls = 0
        self._last: Optional[TrackState] = None
        self.watching = True       # False while nothing on screen needs the timeline

    def send(self, command: str, arg=None) -> None:
        self._commands.put((command, arg))
        self._wake.set()

    def set_preferred(self, source_id: str) -> None:
        self._preferred = source_id
        self._art_key = ""
        self._wake.set()

    def refresh(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._halt.set()
        self._wake.set()

    def run(self) -> None:
        backend = None
        for attempt in range(8):                    # right after Windows starts, its media service can be late
            try:
                if os.environ.get("RUBENIUM_DEMO"):
                    backend = DemoBackend(self._wake.set)
                elif sys.platform == "win32":
                    backend = WindowsBackend(self._wake.set)
                else:
                    raise BackendUnavailable("Rubenium needs Windows 10 or 11")
                break
            except BackendUnavailable as exc:
                log.error("%s", exc)
                self.state_changed.emit(TrackState(Status.UNAVAILABLE, message=str(exc)))
                return
            except Exception as exc:  # noqa: BLE001
                log.warning("Media start-up attempt %d failed: %s", attempt + 1, exc)
                if self._halt.wait(min(15.0, 2.0 * (attempt + 1))):
                    return
        if backend is None:
            self.state_changed.emit(TrackState(Status.UNAVAILABLE, message="Windows media service did not answer"))
            return
        try:
            self._loop(backend)
        finally:
            backend.close()

    def _loop(self, backend) -> None:
        failures = 0
        while not self._halt.is_set():
            backend.preferred = self._preferred
            if self._run_commands(backend) and self._halt.wait(0.15):
                break
            try:
                state = backend.poll()
                failures = 0
            except Exception as exc:  # noqa: BLE001
                failures += 1
                log.debug("poll failed: %s", exc)
                state = TrackState(Status.ERROR, message=str(exc)[:80])
            self._last = state
            self.state_changed.emit(state)
            try:
                self._sync_artwork(backend, state)
            except Exception as exc:  # noqa: BLE001
                log.debug("artwork failed: %s", exc)

            if failures:
                interval = min(8.0, 2.0 * (1 + failures))
            elif state.status is Status.PLAYING and self.watching:
                interval = 1.0
            elif backend.events:
                interval = 5.0        # events wake us instantly; this is only a safety net
            else:
                interval = 2.0
            self._wake.wait(interval)
            self._wake.clear()
            self._halt.wait(0.05)     # coalesce event bursts

    def _run_commands(self, backend) -> bool:
        ran = False
        while True:
            try:
                command, arg = self._commands.get_nowait()
            except queue.Empty:
                return ran
            try:
                backend.send(command, arg, self._last)
                ran = True
            except Exception as exc:  # noqa: BLE001
                log.warning("Command %s failed: %s", command, exc)

    def _sync_artwork(self, backend, state: TrackState) -> None:
        key = state.art_key
        if not key:
            self._art_key, self._art_digest, self._art_polls = "", None, 0
            return
        if key != self._art_key:
            self._art_key, self._art_digest, self._art_polls = key, None, 0
        if self._art_polls >= ART_ATTEMPTS:
            return
        self._art_polls += 1
        data = backend.fetch_artwork(state)
        if not data:
            if self._art_polls < ART_ATTEMPTS:
                threading.Timer(0.7, self._wake.set).start()      # artwork often lands after the metadata
            return
        digest = hashlib.sha1(data).digest()  # noqa: S324
        if digest != self._art_digest:
            self._art_digest = digest
            self.artwork_ready.emit(key, data)
        if not backend.art_may_lag:
            self._art_polls = ART_ATTEMPTS
        elif self._art_polls < ART_ATTEMPTS:
            threading.Timer(0.9, self._wake.set).start()


# ==================================================================================================
# SECTION: lyrics
# ==================================================================================================
import hashlib
import json
import logging
import re
import ssl
import threading
import urllib.parse
import urllib.request

from PyQt6.QtCore import QObject, pyqtSignal


log = logging.getLogger("rubenium.lyrics")
API = "https://lrclib.net/api/"
_LINE = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")
_NOISE = re.compile(r"\s*[\(\[][^\)\]]*(official|video|audio|lyrics?|visuali[sz]er|remaster(ed)?|hd|4k|mv|clip)"
                    r"[^\)\]]*[\)\]]", re.I)


def clean_title(title: str) -> str:
    return _NOISE.sub("", title).strip() or title


def clean_artist(artist: str) -> str:
    artist = re.sub(r"\s*-\s*Topic$", "", artist, flags=re.I)
    return re.sub(r"VEVO$", "", artist).strip() or artist


def parse_lrc(text: str) -> list:
    """'[mm:ss.xx] line' -> [(ms, line)] sorted by time."""
    out = []
    for raw in text.splitlines():
        stamps = list(_LINE.finditer(raw))
        if not stamps:
            continue
        line = raw[stamps[-1].end():].strip()
        for m in stamps:
            frac = m.group(3) or "0"
            ms = int(m.group(1)) * 60000 + int(m.group(2)) * 1000 + int(frac.ljust(3, "0")[:3])
            out.append((ms, line))
    out.sort(key=lambda x: x[0])
    return out


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        return ssl.create_default_context()


class LyricsService(QObject):
    """result(key, kind, payload): kind is 'synced' [(ms, line)], 'plain' [line], 'none' or 'offline'."""
    result = pyqtSignal(str, str, object)

    def __init__(self) -> None:
        super().__init__()
        self._mem: dict = {}
        self._busy: set = set()
        self._ssl = None

    @staticmethod
    def key(title: str, artist: str) -> str:
        return hashlib.sha1(f"{clean_title(title)}\x1f{clean_artist(artist)}".lower().encode()).hexdigest()  # noqa: S324

    def request(self, title: str, artist: str, album: str, duration_ms: int) -> str:
        key = self.key(title, artist)
        if key in self._mem:
            self.result.emit(key, *self._mem[key])
        elif key not in self._busy:
            self._busy.add(key)
            threading.Thread(target=self._work, args=(key, title, artist, album, duration_ms), daemon=True).start()
        return key

    def _get(self, endpoint: str, params: dict):
        if self._ssl is None:
            self._ssl = _ssl_context()
        url = API + endpoint + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{VERSION}"})
        with urllib.request.urlopen(req, timeout=7, context=self._ssl) as resp:  # noqa: S310
            return json.loads(resp.read(2_000_000).decode("utf-8"))

    def _work(self, key, title, artist, album, duration_ms) -> None:
        kind, payload = "none", []
        cache = LYRICS_DIR / f"{key}.json"
        try:
            try:
                data = json.loads(cache.read_text(encoding="utf-8"))
                kind, payload = data["kind"], [tuple(x) if isinstance(x, list) else x for x in data["payload"]]
            except (OSError, ValueError, KeyError):
                kind, payload = self._download(clean_title(title), clean_artist(artist), album, duration_ms)
                try:
                    cache.write_text(json.dumps({"kind": kind, "payload": payload}), encoding="utf-8")
                except OSError:
                    pass
            self._mem[key] = (kind, payload)
        except Exception as exc:  # noqa: BLE001  (network down, DNS, TLS...)
            log.debug("lyrics fetch failed: %s", exc)
            kind, payload = "offline", []
        finally:
            self._busy.discard(key)
        self.result.emit(key, kind, payload)

    def _download(self, title, artist, album, duration_ms):
        best = None
        import urllib.error
        if duration_ms > 0:
            try:
                params = {"track_name": title, "artist_name": artist, "duration": round(duration_ms / 1000)}
                if album:
                    params["album_name"] = album
                best = self._get("get", params)
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
        if not best or not (best.get("syncedLyrics") or best.get("plainLyrics")):
            found = self._get("search", {"track_name": title, "artist_name": artist})
            if isinstance(found, list) and found:
                def score(item):
                    d = abs((item.get("duration") or 0) * 1000 - duration_ms) if duration_ms else 0
                    return (0 if item.get("syncedLyrics") else 1, d)
                found.sort(key=score)
                cand = found[0]
                if not duration_ms or abs((cand.get("duration") or 0) * 1000 - duration_ms) < 8000:
                    best = cand
        if best:
            if best.get("syncedLyrics"):
                lines = parse_lrc(best["syncedLyrics"])
                if lines:
                    return "synced", lines
            if best.get("plainLyrics"):
                return "plain", [ln.strip() for ln in best["plainLyrics"].splitlines()]
            if best.get("instrumental"):
                return "plain", ["♪"]
        return "none", []


# ==================================================================================================
# SECTION: engines
# ==================================================================================================
import json
import logging
import math
import threading
import time

from PyQt6.QtCore import QObject, QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QWidget


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


# ==================================================================================================
# SECTION: extras
# ==================================================================================================
import base64
import ctypes
import json
import logging
import math
import os
import time
from ctypes import wintypes
from pathlib import Path

from PyQt6.QtCore import QAbstractNativeEventFilter, QFileInfo, QObject, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPen
from PyQt6.QtWidgets import QFileIconProvider, QWidget


log = logging.getLogger("rubenium.extras")

# --------------------------------------------------------------------------- #
# Themes: background designs, sparkles and glow, unlocked by hours of use.
# They never change the colour (the music / your accent does), so they always show.
# --------------------------------------------------------------------------- #
THEMES = [      # in unlock order: each one is a little richer than the one before
    dict(id="clean", name="Clean", hours=0, layers=[]),
    dict(id="dots", name="Dots", hours=1, layers=["dots"]),
    dict(id="grid", name="Grid", hours=2, layers=["grid"]),
    dict(id="lines", name="Lines", hours=5, layers=["lines"]),
    dict(id="hex", name="Hive", hours=8, layers=["hex"]),
    dict(id="waves", name="Waves", hours=12, layers=["waves"]),
    dict(id="rings", name="Sonar", hours=18, layers=["rings"]),
    dict(id="glow", name="Radiance", hours=25, layers=["glow"], glow=1.2),
    dict(id="circuit", name="Circuit", hours=32, layers=["glow", "circuit"], glow=1.2),
    dict(id="stars", name="Stars", hours=40, layers=["glow"], sparkles=7, glow=1.25),
    dict(id="comet", name="Comets", hours=50, layers=["glow", "comet"], sparkles=3, glow=1.3),
    dict(id="aurora", name="Aurora", hours=62, layers=["aurora"], sparkles=4, glow=1.3),
    dict(id="nebula", name="Nebula", hours=75, layers=["aurora", "hex"], sparkles=9, glow=1.35),
    dict(id="prism", name="Prism", hours=100, layers=["aurora", "dots"], glow=1.35, edge="rainbow"),
    dict(id="legend", name="Legend", hours=150, layers=["glow", "lines"], sparkles=8, glow=1.45, edge="gold"),
]
# Small extras that also unlock with time: the look of the R and of the song ring on the ball.
R_STYLES = [dict(id="classic", name="Classic", hours=0), dict(id="outline", name="Outline", hours=3),
            dict(id="neon", name="Neon", hours=15), dict(id="gold", name="Gold", hours=45),
            dict(id="prism", name="Prism", hours=90)]
RING_STYLES = [dict(id="line", name="Line", hours=0), dict(id="dash", name="Dashes", hours=10),
               dict(id="dots", name="Dots", hours=30)]


def unlocked_style(styles: list, ident: str, hours: float) -> str:
    """The style to use: the chosen one if it is unlocked, otherwise the first (free) one."""
    for st in styles:
        if st["id"] == ident and hours >= st["hours"]:
            return ident
    return styles[0]["id"]


def paint_r(p: QPainter, box: QRectF, d: float, style: str, accent: QColor, now: float = 0.0) -> None:
    """The R of the ball, centred in `box` for a ball of diameter `d`, in one of R_STYLES."""
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QConicalGradient, QFont, QFontMetricsF, QLinearGradient, QPainterPath
    pass
    f = font(20, QFont.Weight.ExtraBold)
    f.setPixelSize(max(8, int(d * 0.46)))
    p.setFont(f)
    centre = int(Qt.AlignmentFlag.AlignCenter)
    if style == "classic":
        p.setPen(alpha(accent, 0.55))
        p.drawText(box.translated(0, d * 0.022), centre, "R")
        p.setPen(QColor(TEXT))
        p.drawText(box, centre, "R")
        return
    fm = QFontMetricsF(f)
    tb = fm.tightBoundingRect("R")
    path = QPainterPath()
    path.addText(QPointF(box.center().x() - tb.width() / 2 - tb.left(), box.center().y() - tb.height() / 2 - tb.top()),
                 f, "R")
    p.save()
    if style == "outline":
        pen = QPen(QColor(TEXT), max(1.2, d * 0.028))
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(alpha(accent, 0.18))
        p.drawPath(path)
    elif style == "neon":
        p.setBrush(Qt.BrushStyle.NoBrush)
        for width, a in ((d * 0.14, 0.10), (d * 0.09, 0.16), (d * 0.05, 0.28)):
            pen = QPen(alpha(accent, a), width)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix(accent, QColor("#FFFFFF"), 0.55))
        p.drawPath(path)
    elif style == "gold":
        g = QLinearGradient(box.topLeft(), box.bottomRight())
        g.setColorAt(0.25, QColor("#FFF1C2"))
        g.setColorAt(0.5, QColor(GOLD))
        g.setColorAt(0.75, QColor("#B8862B"))
        p.setPen(QPen(alpha("#000000", 0.35), 1))
        p.setBrush(g)
        p.drawPath(path)
    else:                                               # prism: slowly turning colours
        g = QConicalGradient(box.center(), (now * 30.0) % 360.0)
        for i in range(7):
            g.setColorAt(i / 6, QColor.fromHsvF((i / 6) % 1.0 * 0.999, 0.45, 1.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawPath(path)
    p.restore()


def ring_pen(style: str, color: QColor, width: float) -> QPen:
    """Pen for the song ring on the ball, in one of RING_STYLES."""
    pen = QPen(color, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    if style == "dash":
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        pen.setDashPattern([2.6, 1.6])
    elif style == "dots":
        pen.setDashPattern([0.1, 2.2])
    return pen


GOLD = "#E8C26A"
_pattern_cache: dict = {}


def theme_by_id(ident: str) -> dict:
    return next((t for t in THEMES if t["id"] == ident), THEMES[0])


def _draw_layer(p: QPainter, layer: str, w: float, h: float, accent: QColor, unit: float) -> None:
    """One quiet background layer. Patterns start one card-padding in from the left edge so they line up
    with the content; a fade applied afterwards keeps them in the header area only."""
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QPainterPath, QRadialGradient
    pad = 14 * unit
    if layer == "grid":
        p.setPen(QPen(alpha(accent, 0.11), 1))
        step = 16 * unit
        x = pad
        while x < w:
            p.drawLine(QPointF(x, 0), QPointF(x, h))
            x += step
        y = step
        while y < h:
            p.drawLine(QPointF(0, y), QPointF(w, y))
            y += step
    elif layer == "dots":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha(accent, 0.30))
        step = 12 * unit
        y = step / 2
        while y < h:
            x = pad
            while x < w:
                p.drawEllipse(QPointF(x, y), 0.9 * unit, 0.9 * unit)
                x += step
            y += step
    elif layer == "hex":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(alpha(accent, 0.13), 1))
        r = 9 * unit
        dx, dy = r * 1.732, r * 1.5
        row, y = 0, 0.0
        while y < h + r:
            x = pad + (dx / 2 if row % 2 else 0.0)
            while x < w + r:
                cell = QPainterPath()
                for k in range(6):
                    ang = math.radians(60 * k - 90)
                    pt = QPointF(x + r * math.cos(ang), y + r * math.sin(ang))
                    cell.lineTo(pt) if k else cell.moveTo(pt)
                cell.closeSubpath()
                p.drawPath(cell)
                x += dx
            y += dy
            row += 1
    elif layer == "rings":
        p.setBrush(Qt.BrushStyle.NoBrush)
        c = QPointF(w * 0.80, 0)
        for n in range(1, 11):
            p.setPen(QPen(alpha(accent, max(0.03, 0.24 - 0.022 * n)), 1.1))
            p.drawEllipse(c, n * 15 * unit, n * 15 * unit)
    elif layer == "circuit":
        import random
        rnd = random.Random(11)
        p.setBrush(Qt.BrushStyle.NoBrush)
        step = 12 * unit
        for _ in range(11):
            x, y = pad + rnd.randrange(0, max(1, int((w - pad) / step))) * step, rnd.randrange(0, 9) * step
            trace = QPainterPath(QPointF(x, y))
            for _seg in range(rnd.randrange(2, 5)):
                if rnd.random() < 0.5:
                    x += rnd.choice((-3, -2, 2, 3, 4)) * step
                else:
                    y += rnd.choice((1, 2, 3)) * step
                trace.lineTo(QPointF(x, y))
            p.setPen(QPen(alpha(accent, 0.20), 1.1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(trace)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(accent, 0.45))
            p.drawEllipse(QPointF(x, y), 1.8 * unit, 1.8 * unit)
    elif layer == "comet":
        import random
        from PyQt6.QtGui import QLinearGradient
        rnd = random.Random(5)
        white = QColor("#FFFFFF")
        for _ in range(6):
            x, y = pad + rnd.random() * (w - pad), rnd.random() * h * 0.55
            length = (26 + rnd.random() * 34) * unit
            tail = QPointF(x + length, y - length * 0.45)
            g = QLinearGradient(QPointF(x, y), tail)
            g.setColorAt(0.0, alpha(mix(accent, white, 0.5), 0.55))
            g.setColorAt(1.0, alpha(accent, 0.0))
            pen = QPen(g, 1.4 * unit)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(x, y), tail)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(white, 0.75))
            p.drawEllipse(QPointF(x, y), 1.3 * unit, 1.3 * unit)
    elif layer == "lines":
        p.setPen(QPen(alpha(accent, 0.12), 1))
        step = 10 * unit
        x = -h
        while x < w:
            p.drawLine(QPointF(x, h), QPointF(x + h, 0))
            x += step
    elif layer == "waves":
        p.setBrush(Qt.BrushStyle.NoBrush)
        for n in range(3):
            path = QPainterPath()
            base, amp = (18 + n * 16) * unit, (5 + n) * unit
            for i in range(0, int(w) + 9, 6):
                y = base + math.sin(i / (38.0 * unit) + n * 1.7) * amp
                path.lineTo(i, y) if i else path.moveTo(i, y)
            p.setPen(QPen(alpha(accent, 0.22 - 0.05 * n), 1.2))
            p.drawPath(path)
    elif layer == "glow":
        g = QRadialGradient(QPointF(w * 0.18, 0), w * 0.75)
        g.setColorAt(0, alpha(accent, 0.20))
        g.setColorAt(1, alpha(accent, 0.0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRect(QRectF(0, 0, w, h))
    elif layer == "aurora":
        other = QColor.fromHsvF((max(0.0, accent.hsvHueF()) + 0.14) % 1.0,
                                max(0.35, accent.hsvSaturationF()), max(0.6, accent.valueF()))
        p.setPen(Qt.PenStyle.NoPen)
        for cx, col in ((0.15, accent), (0.85, other)):
            g = QRadialGradient(QPointF(w * cx, -h * 0.15), w * 0.6)
            g.setColorAt(0, alpha(col, 0.22))
            g.setColorAt(1, alpha(col, 0.0))
            p.setBrush(g)
            p.drawRect(QRectF(0, 0, w, h))


def theme_pattern(theme: dict, w: int, h: int, accent: QColor, dpr: float, unit: float, band: float = 0.0):
    """Cached pixmap of a theme's layers, faded out below `band` pixels (None for a plain theme)."""
    from PyQt6.QtGui import QLinearGradient, QPixmap
    if not theme["layers"] or w < 2 or h < 2:
        return None
    band = band or h
    key = (theme["id"], w, h, accent.rgb(), round(dpr * 100), round(unit * 100), round(band))
    pm = _pattern_cache.get(key)
    if pm is None:
        if len(_pattern_cache) > 40:
            _pattern_cache.clear()
        pm = QPixmap(int(w * dpr), int(h * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for layer in theme["layers"]:
            _draw_layer(p, layer, w, min(h, band), accent, unit)
        fade = QLinearGradient(0, 0, 0, band)                 # strongest under the header, gone below it
        fade.setColorAt(0.0, QColor(0, 0, 0, 255))
        fade.setColorAt(0.55, QColor(0, 0, 0, 150))
        fade.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        p.fillRect(QRectF(0, 0, w, h), fade)
        p.end()
        _pattern_cache[key] = pm
    return pm


def theme_sparkles(theme: dict, w: float, h: float, band: float = 0.0) -> list:
    """[(x, y, size, phase, speed)], stable for a theme; kept inside the header band."""
    import random
    n = theme.get("sparkles", 0)
    if not n:
        return []
    band = min(h, band or h)
    rnd = random.Random(theme["id"])
    return [(rnd.uniform(0.06, 0.94) * w, rnd.uniform(0.10, 0.85) * band, rnd.uniform(1.4, 2.6),
             rnd.uniform(0, 6.28), rnd.uniform(0.6, 1.2)) for _ in range(n)]


def paint_sparkles(p: QPainter, sparks: list, ox: float, oy: float, accent: QColor, now: float, unit: float) -> None:
    from PyQt6.QtCore import QPointF
    white = QColor("#FFFFFF")
    for x, y, size, phase, speed in sparks:
        b = max(0.0, math.sin(now * speed + phase)) ** 3
        if b < 0.03:
            continue
        r = size * unit * (0.6 + 0.4 * b)
        c = QPointF(ox + x, oy + y)
        pen = QPen(alpha(mix(accent, white, 0.55), 0.6 * b), max(1.0, 0.8 * unit))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(c.x() - r, c.y()), QPointF(c.x() + r, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - r), QPointF(c.x(), c.y() + r))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha(white, 0.7 * b))
        p.drawEllipse(c, 0.8 * unit, 0.8 * unit)


def paint_theme_edge(p: QPainter, theme: dict, shape: QRectF, radius: float, level: float, halo: bool,
                     now: float) -> None:
    """Card outline: plain accent, rotating rainbow or double gold."""
    from PyQt6.QtGui import QConicalGradient
    p.setBrush(Qt.BrushStyle.NoBrush)
    a = (80 + 110 * level) / 255 if halo else 0.35
    r = shape.adjusted(0.6, 0.6, -0.6, -0.6)
    style = theme.get("edge", "")
    if style == "rainbow":
        g = QConicalGradient(shape.center(), (now * 25.0) % 360.0)
        for i in range(7):
            g.setColorAt(i / 6, alpha(QColor.fromHsvF((i / 6) % 1.0 * 0.999, 0.45, 1.0), min(1.0, a + 0.1)))
        p.setPen(QPen(g, 1.3))
        p.drawRoundedRect(r, radius, radius)
    elif style == "gold":
        p.setPen(QPen(alpha(GOLD, min(1.0, a + 0.15)), 1.3))
        p.drawRoundedRect(r, radius, radius)
    else:
        p.setPen(QPen(alpha(ui.accent, a), 1.2))
        p.drawRoundedRect(r, radius, radius)


# --------------------------------------------------------------------------- #
# Run timer
# --------------------------------------------------------------------------- #
def run_clock(seconds: float) -> str:
    seconds = max(0.0, seconds)
    cs = int(seconds * 100) % 100
    s = int(seconds)
    if s >= 3600:
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}.{cs:02d}"
    return f"{s // 60}:{s % 60:02d}.{cs:02d}"


class TimerEngine(QObject):
    changed = pyqtSignal()

    def __init__(self, cfg) -> None:
        super().__init__()
        self.cfg = cfg
        self.state = "idle"            # idle | running | paused
        self._base = 0.0
        self._t0 = 0.0
        self.splits: list = []

    def elapsed(self) -> float:
        return self._base + (time.monotonic() - self._t0 if self.state == "running" else 0.0)

    def start_split(self) -> None:
        if self.state == "idle":
            self._base, self._t0, self.splits, self.state = 0.0, time.monotonic(), [], "running"
        elif self.state == "paused":
            self._t0, self.state = time.monotonic(), "running"
        else:
            self.splits.append(self.elapsed())
        self.changed.emit()

    def pause(self) -> None:
        if self.state == "running":
            self._base, self.state = self.elapsed(), "paused"
        elif self.state == "paused":
            self._t0, self.state = time.monotonic(), "running"
        self.changed.emit()

    def finish(self) -> None:
        """Stop the run and keep it as the best time if it is faster."""
        if self.state == "idle":
            return
        total = self.elapsed()
        self._base, self.state = total, "paused"
        best = self.cfg["timer"]["best"]
        if total > 0.5 and (best <= 0 or total < best):
            self.cfg["timer"]["best"] = total
            self.cfg.save()
        self.changed.emit()

    def reset(self) -> None:
        self.state, self._base, self.splits = "idle", 0.0, []
        self.changed.emit()


class TimerOverlay(QWidget):
    """Click-through timer at the top of the screen."""

    def __init__(self, cfg, engine: TimerEngine) -> None:
        super().__init__()
        self.cfg, self.engine = cfg, engine
        self.setWindowFlags(OVERLAY_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._tick = QTimer(self)
        self._tick.setInterval(40)
        self._tick.timeout.connect(self.update)
        engine.changed.connect(self._sync)

    def refresh(self) -> None:
        if self.cfg["timer"]["overlay"]:
            w, h = S(150), S(38)
            g = QGuiApplication.primaryScreen().geometry()
            self.setGeometry(g.center().x() - w // 2, g.top() + S(10), w, h)
            self.show()
            win.make_overlay(int(self.winId()))
        else:
            self.hide()
        self._sync()

    def _sync(self) -> None:
        if self.isVisible() and self.engine.state == "running":
            self._tick.start()
        else:
            self._tick.stop()
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha(ui.accent, 0.5), 1))
        p.setBrush(QColor(10, 14, 15, 210))
        p.drawRoundedRect(r, S(9), S(9))
        f = font(19, QFont.Weight.Bold)
        f.setStyleHint(QFont.StyleHint.Monospace)
        p.setFont(f)
        p.setPen(QColor(TEXT) if self.engine.state != "paused" else alpha(TEXT, 0.6))
        p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), run_clock(self.engine.elapsed()))


# --------------------------------------------------------------------------- #
# Keyboard shortcuts (RegisterHotKey: no hooks)
# --------------------------------------------------------------------------- #
class _KeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback) -> None:
        super().__init__()
        self._cb = callback

    def nativeEventFilter(self, event_type, message):
        try:
            if bytes(event_type) == b"windows_generic_MSG":
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0312:       # WM_HOTKEY
                    self._cb(int(msg.wParam))
                    return True, 0
        except Exception:  # noqa: BLE001
            pass
        return False, 0


class Hotkeys(QObject):
    """Fixed keys. Ctrl+Alt+Shift+R: normal screen colours. Ctrl+F1 / F2 / F3: run timer."""
    triggered = pyqtSignal(str)
    KEYS = {1: ("panic", 0x2 | 0x1 | 0x4, 0x52),          # Ctrl+Alt+Shift+R
            2: ("timer_split", 0x2, 0x70), 3: ("timer_pause", 0x2, 0x71), 4: ("timer_reset", 0x2, 0x72)}

    def __init__(self, app) -> None:
        super().__init__()
        self._last = (0, 0.0)
        self._on: set = set()
        self._filter = _KeyFilter(self._hit)
        app.installNativeEventFilter(self._filter)

    def _hit(self, ident: int) -> None:
        now = time.monotonic()
        if self._last[0] == ident and now - self._last[1] < 0.12:
            return                                   # Qt can deliver the same message twice
        self._last = (ident, now)
        if ident in self.KEYS:
            self.triggered.emit(self.KEYS[ident][0])

    def apply(self, timer_keys: bool) -> None:
        if not win.IS_WIN:
            return
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        for ident, (name, mods, vk) in self.KEYS.items():
            want = name == "panic" or timer_keys
            if want and ident not in self._on:
                if user32.RegisterHotKey(None, ident, mods | 0x4000, vk):
                    self._on.add(ident)
            elif not want and ident in self._on:
                user32.UnregisterHotKey(None, ident)
                self._on.discard(ident)

    def close(self) -> None:
        if win.IS_WIN:
            for ident in list(self._on):
                ctypes.windll.user32.UnregisterHotKey(None, ident)  # type: ignore[attr-defined]
        self._on.clear()


# --------------------------------------------------------------------------- #
# Launcher: find installed apps from the Start menu and the desktop
# --------------------------------------------------------------------------- #
APP_WORDS = ["steam", "epic games", "rocket league", "discord", "spotify", "obs", "riot", "valorant",
             "counter-strike", "fortnite", "battle.net", "minecraft", "ea app", "ubisoft", "gog galaxy", "medal",
             "overwolf", "bakkesmod", "nvidia", "afterburner", "twitch", "streamlabs", "chrome", "firefox",
             "edge", "brave", "opera", "league of legends", "roblox", "geforce", "teamspeak", "telegram",
             "whatsapp", "apex", "overwatch", "genshin", "xbox", "playnite", "parsec", "curseforge", "lunar client"]
APP_SKIP = ["uninstall", "désinstall", "help", "readme", "manual", "documentation", "website", "support",
            "license", "release notes", "crash", "repair", "setup", "installer", "updater", "diagnos"]
GAME_DIRS = ["steamapps\\common", "epic games", "riot games", "\\games\\", "ubisoft game launcher", "ea games"]
PROTECTED = {"explorer.exe", "python.exe", "pythonw.exe", "rubenium.exe", "svchost.exe", "csrss.exe",
             "winlogon.exe", "dwm.exe", "system", "lsass.exe", "services.exe"}


def _start_folders() -> list:
    out = []
    for env, tail in (("APPDATA", r"Microsoft\Windows\Start Menu\Programs"),
                      ("PROGRAMDATA", r"Microsoft\Windows\Start Menu\Programs"),
                      ("USERPROFILE", "Desktop"), ("PUBLIC", "Desktop")):
        base = os.environ.get(env)
        if base:
            out.append(Path(base) / tail)
    out.append(win.documents_dir().parent / "Desktop")        # OneDrive-redirected desktop
    return out


def scan_apps(limit: int = 40) -> list:
    """[{name, path, exe, icon}] for apps worth a quick-launch tile. exe is '' when unknown."""
    if not win.IS_WIN:
        return []
    found: dict = {}
    provider = QFileIconProvider()
    for folder in _start_folders():
        try:
            files = [f for f in folder.rglob("*") if f.suffix.lower() in (".lnk", ".url")]
        except OSError:
            continue
        for f in files:
            name = f.stem.strip()
            low = name.lower()
            if low in found or any(w in low for w in APP_SKIP):
                continue
            exe, icon_path, keep = "", "", False
            try:
                if f.suffix.lower() == ".url":
                    url = ""
                    for line in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                        if line.startswith("URL="):
                            url = line[4:].strip()
                        elif line.startswith("IconFile="):
                            icon_path = line[9:].strip()
                    keep = url.startswith(("steam://", "com.epicgames.launcher://", "uplay://", "origin"))
                else:
                    target = QFileInfo(str(f)).symLinkTarget()
                    tlow = target.lower().replace("/", "\\")
                    if tlow and not tlow.endswith(".exe"):
                        continue
                    exe = os.path.basename(tlow)
                    if exe == "update.exe":                       # Discord-style stub launchers
                        exe = low.replace(" ", "") + ".exe"
                    keep = any(w in low for w in APP_WORDS) or any(d in tlow for d in GAME_DIRS)
            except OSError:
                continue
            if not keep:
                continue
            icon = QIcon(icon_path) if icon_path and os.path.exists(icon_path) else provider.icon(QFileInfo(str(f)))
            found[low] = {"name": name, "path": str(f), "exe": exe, "icon": icon}
    apps = sorted(found.values(), key=lambda a: a["name"].lower())
    return apps[:limit]


def running_names() -> set:
    try:
        import psutil
        return {(p.info["name"] or "").lower() for p in psutil.process_iter(["name"])}
    except Exception:  # noqa: BLE001
        return set()


def close_app(exe: str) -> bool:
    """Force-close every process called `exe` (like 'End task')."""
    exe = exe.lower()
    if not exe or exe in PROTECTED:
        return False
    try:
        import psutil
        done = False
        for p in psutil.process_iter(["name"]):
            if (p.info["name"] or "").lower() == exe and p.pid != os.getpid():
                try:
                    p.kill()
                    done = True
                except Exception:  # noqa: BLE001
                    pass
        return done
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- #
# What's new (shown in the New tab; English text is the key, French is in lang_fr)
# --------------------------------------------------------------------------- #
NEWS = [        # newest first: (version shown, [(heading, [lines])])
    ("1.0", [
        ("Updates", ["The Update button now works on every PC",
                     "It also works when Windows protects the folder Rubenium is in"]),
        ("RL Swap", ["Every swap now shows a picture of the result",
                     "Black Lunation is ready",
                     "The yellow outline only marks what is about to change"]),
        ("Stats", ["See which apps use the most processor and memory"]),
        ("Themes", ["5 new themes, in a better order",
                    "New styles for the R and for the song ring, unlocked with time"]),
    ]),
    ("", [
        ("Start-up", ["Welcome screen with a Launch button and a loading animation",
                      "Rubenium comes back the way you left it"]),
        ("RL Swap", ["8 new swaps and a new Decals section",
                     "Several swaps can be on at once (one per item)",
                     "Room for more swaps in every section"]),
        ("Look", ["Stronger glow that follows the music better",
                  "Theme options for glow, background and corners"]),
        ("Settings", ["Choose which tabs show in the menu bar",
                      "Change the size of the ball, with a real-size preview"]),
        ("Fixes", ["Time used now keeps counting when the music stops",
                   "Timer keys and update checks keep working all day"]),
    ]),
]

# --------------------------------------------------------------------------- #
# Rocket League: find the game, swap item files, keep the originals safe
# --------------------------------------------------------------------------- #
RL_CATS = [("goal", "Goal explosions"), ("body", "Car bodies"), ("decal", "Decals"), ("boost", "Boosts"),
           ("wheels", "Wheels"), ("trail", "Trails")]
# One entry per swap. `old` is the item you equip in the game, `new` is what it turns into, `file` is the game
# file it replaces. Several swaps of one category can be on together; two swaps of the SAME file cannot.
# To add a swap: put its file in swaps/<id>/<file> (and, if you have one, a picture named preview.png) and
# add one line here.
RL_ITEMS = [
    dict(id="atomizer_gentlemates", cat="goal", old="Atomizer", new="Gentle Mates 2025", file="explosion_Rekt_SF.upk"),
    dict(id="splash_adidas", cat="goal", old="Big Splash", new="Adidas", file="explosion_splash_SF.upk"),
    dict(id="splash_supernova", cat="goal", old="Big Splash", new="SuperNova III", file="explosion_splash_SF.upk"),
    dict(id="octane_fennec", cat="body", old="Octane", new="Fennec", file="Body_Octane_SF.upk"),
    dict(id="fennec_flames_likescraft", cat="decal", old="Fennec: Flames", new="Likescraft",
         file="skin_grain_flames_SF.upk"),
    dict(id="fennec_flames_blacklunation", cat="decal", old="Fennec: Flames", new="Black Lunation",
         file="skin_grain_flames_SF.upk"),
    dict(id="fennec_stripes_falcons", cat="decal", old="Fennec: Stripes", new="RLCS Falcons",
         file="skin_grain_stripes_SF.upk"),
    dict(id="fennec_nitty_gc", cat="decal", old="Fennec: Nitty Gritty", new="S-13 Grand Champion",
         file="skin_grain_racelines_SF.upk"),
    dict(id="octane_lightning_ssg", cat="decal", old="Octane: Lightning", new="RLCS SSG",
         file="Skin_Octane_Lightning_SF.upk"),
    dict(id="octane_stripes_joyo", cat="decal", old="Octane: Stripes", new="Joyo Octane",
         file="Skin_Octane_Stripes_SF.upk"),
    dict(id="bubbles_alpha", cat="boost", old="Bubbles", new="Alpha Boost", file="Boost_Bubble_SF.upk"),
    dict(id="bubbles_dev", cat="boost", old="Bubbles", new="Dev Boost", file="Boost_Bubble_SF.upk"),
    dict(id="bubbles_purple", cat="boost", old="Bubbles", new="Standard Purple", file="Boost_Bubble_SF.upk"),
]
RL_BY_ID = {it["id"]: it for it in RL_ITEMS}
RL_EXE = "rocketleague.exe"


def rl_key(item: dict) -> str:
    """Swaps are told apart by the game file they replace: one swap per file."""
    return item["file"].lower()


def _swap_roots() -> list:
    import sys
    return [Path(getattr(sys, "_MEIPASS", "")) / "swaps", Path(sys.argv[0]).resolve().parent / "swaps",
            Path(sys.executable).resolve().parent / "swaps"]


_previews: dict = {}


def swap_preview(item: dict):
    """The picture of what a swap looks like (swaps/<id>/preview.png), or None when there is none yet."""
    from PyQt6.QtGui import QPixmap
    ident = item["id"]
    if ident not in _previews:
        found = None
        for root in [_rl_store() / "swaps"] + _swap_roots():
            for name in ("preview.png", "preview.jpg", "preview.webp"):
                f = root / ident / name
                try:
                    if f.is_file():
                        pm = QPixmap(str(f))
                        if not pm.isNull():
                            found = pm
                            break
                except OSError:
                    continue
            if found is not None:
                break
        _previews[ident] = found
    return _previews[ident]


def _rl_store():
    pass
    return DATA_DIR / "rocket_league"


PLATFORMS = ("epic", "steam")
PLATFORM_NAMES = {"epic": "Epic Games", "steam": "Steam"}


def rocket_league_ok(folder: str) -> bool:
    return bool(folder) and os.path.isdir(os.path.join(folder, "TAGame", "CookedPCConsole"))


def platform_of(folder: str) -> str:
    return "steam" if "steamapps" in folder.lower().replace("/", "\\") else "epic"


def _drives() -> list:
    """Local hard drives only (no network, CD or card readers, which can be slow to answer)."""
    import string
    try:
        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        mask = k32.GetLogicalDrives()
        out = []
        for i, d in enumerate(string.ascii_uppercase):
            if mask & (1 << i) and k32.GetDriveTypeW(f"{d}:\\") == 3:     # DRIVE_FIXED
                out.append(f"{d}:\\")
        return out
    except Exception:  # noqa: BLE001
        return []


def _steam_roots() -> list:
    roots = []
    try:
        import winreg
        for hive, key, value in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                 (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
                                 (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", "InstallPath")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    roots.append(str(winreg.QueryValueEx(k, value)[0]))
            except OSError:
                continue
    except ImportError:
        pass
    libraries = []
    import re
    for root in roots:
        libraries.append(root)
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        try:
            text = open(vdf, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for m in re.finditer(r'"path"\s+"([^"]+)"', text):            # every Steam library on every drive
            libraries.append(m.group(1).replace("\\\\", "\\"))
    return libraries


def find_installs() -> dict:
    """{platform: {"folder", "app"}} for every Rocket League install that can be found on this PC."""
    if not win.IS_WIN:
        return {}
    found: dict = {}

    def add(folder: str, app: str = "", platform: str = "") -> None:
        if not folder:
            return
        folder = os.path.normpath(folder)
        if not rocket_league_ok(folder):
            return
        plat = platform or platform_of(folder)
        if plat not in found:
            found[plat] = {"folder": folder, "app": app}
        elif app and not found[plat]["app"]:
            found[plat]["app"] = app

    program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    try:                                                  # Epic: one manifest per installed game
        for item in (Path(program_data) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests").glob("*.item"):
            try:
                data = json.loads(item.read_text(encoding="utf-8", errors="ignore"))
            except (OSError, ValueError):
                continue
            if "rocket league" in str(data.get("DisplayName", "")).lower() or data.get("AppName") == "Sugar":
                add(str(data.get("InstallLocation", "")), str(data.get("AppName", "")), "epic")
    except OSError:
        pass
    try:                                                  # Epic: the launcher's own list
        data = json.loads((Path(program_data) / "Epic" / "UnrealEngineLauncher" / "LauncherInstalled.dat")
                          .read_text(encoding="utf-8", errors="ignore"))
        for entry in data.get("InstallationList", []):
            if entry.get("AppName") == "Sugar" or "rocketleague" in str(entry.get("InstallLocation", "")).lower():
                add(str(entry.get("InstallLocation", "")), str(entry.get("AppName", "")), "epic")
    except (OSError, ValueError, AttributeError):
        pass
    for lib in _steam_roots():                            # Steam: every library folder
        add(os.path.join(lib, "steamapps", "common", "rocketleague"), "", "steam")
    if len(found) < 2:                                    # last resort: the usual folders on every drive
        for drive in _drives():
            for tail in ("Program Files\\Epic Games\\rocketleague", "Epic Games\\rocketleague",
                         "Games\\Epic Games\\rocketleague", "Games\\rocketleague",
                         "Program Files (x86)\\Steam\\steamapps\\common\\rocketleague",
                         "Program Files\\Steam\\steamapps\\common\\rocketleague",
                         "SteamLibrary\\steamapps\\common\\rocketleague", "Steam\\steamapps\\common\\rocketleague",
                         "Games\\SteamLibrary\\steamapps\\common\\rocketleague"):
                add(os.path.join(drive, tail))
    return found


_hash_cache: dict = {}


def file_hash(path) -> str:
    """SHA-256 of a file, cached by size and modification time ("" if it cannot be read)."""
    import hashlib
    try:
        st = os.stat(path)
    except OSError:
        return ""
    key = (str(path), st.st_size, st.st_mtime_ns)
    hit = _hash_cache.get(key)
    if hit is None:
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for block in iter(lambda: f.read(1 << 20), b""):
                    h.update(block)
        except OSError:
            return ""
        hit = _hash_cache[key] = h.hexdigest()
        if len(_hash_cache) > 64:
            for k in list(_hash_cache)[:32]:
                _hash_cache.pop(k, None)
    return hit


def swap_source(item: dict):
    """Where this swap's replacement file is. Files shipped with the app are copied once into
    Documents/Rubenium/rocket_league/swaps so they survive app updates."""
    import shutil
    store = _rl_store() / "swaps" / item["id"] / item["file"]
    for root in _swap_roots():
        src = root / item["id"] / item["file"]
        if src.is_file():
            if store.is_file():
                if file_hash(store) == file_hash(src):
                    return store
                _remember_custom(item["file"], file_hash(store))   # an app update brought a new version
            try:
                store.parent.mkdir(parents=True, exist_ok=True)
                tmp = store.with_name(store.name + ".part")
                shutil.copyfile(src, tmp)
                os.replace(tmp, store)
                return store
            except OSError:
                return src
    return store if store.is_file() else None


def _known_customs() -> dict:
    """{hash: file name} of swap files from earlier app versions (still recognised as swaps, never as originals)."""
    try:
        data = json.loads((_rl_store() / "known.json").read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _remember_custom(filename: str, digest: str) -> None:
    if not digest:
        return
    known = _known_customs()
    known[digest] = filename
    try:
        path = _rl_store() / "known.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(known, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def _atomic_copy(src, dst) -> None:
    """Copy so that `dst` is never half-written: a temporary file in the same folder, then a rename."""
    import shutil
    dst = Path(dst)
    tmp = dst.with_name(dst.name + ".rbn-tmp")
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dst)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def _clean_install(entry) -> dict:
    e = entry if isinstance(entry, dict) else {}
    act = e.get("active") if isinstance(e.get("active"), dict) else {}
    orig = e.get("orig") if isinstance(e.get("orig"), dict) else {}
    return {"folder": str(e.get("folder", "") or ""), "app": str(e.get("app", "") or ""),
            "manual": bool(e.get("manual", False)),
            "active": {str(k): str(v) for k, v in act.items()}, "orig": {str(k): str(v) for k, v in orig.items()},
            "stamp": str(e.get("stamp", "") or "")}


class RocketSwaps(QObject):
    """Swaps Rocket League item files and puts them back, separately for each install (Steam / Epic).

    * The real files decide what is swapped: every check reads the game files, never a stored guess.
    * The game's own file is copied to Documents/Rubenium/rocket_league/originals/<platform> before it is
      ever replaced.
    * After a game update (the game's exe changed) the files the update put back become the new originals and
      the swaps can be applied again (automatically if the user wants).
    * If a swapped file was changed by something else while the game did not update, the saved original is
      kept and the user is offered a fix."""
    busy = pyqtSignal(str)              # step text
    done = pyqtSignal(bool, str, dict)  # ok, message key, results to store
    changed = pyqtSignal()

    def __init__(self, cfg) -> None:
        super().__init__()
        self.cfg = cfg
        self.working = False
        self.found: dict = {}
        self._noticed = ""
        self._timer = QTimer(self)
        self._timer.setInterval(20000)
        self._timer.timeout.connect(self.watch)
        self.done.connect(self._finished)
        self._detected = False
        self._migrate()

    # -- settings
    @property
    def rl(self) -> dict:
        return self.cfg["rl"]

    def _installs(self) -> dict:
        raw = self.rl["installs"]
        clean = {p: _clean_install(raw.get(p)) for p in PLATFORMS if p in raw}
        self.rl["installs"] = clean
        return clean

    def _entry(self, plat: str) -> dict:
        installs = self._installs()
        if plat not in installs:
            installs[plat] = _clean_install({})
        return installs[plat]

    def _migrate(self) -> None:
        """2.0 kept one install at the top level: move it under its platform."""
        import shutil
        rl = self.rl
        if not rl.get("folder"):
            return
        plat = platform_of(rl["folder"])
        e = self._entry(plat)
        if not e["folder"]:
            e.update(folder=rl["folder"], app=rl.get("app", ""), active=dict(rl.get("active") or {}),
                     orig=dict(rl.get("orig") or {}), stamp=rl.get("stamp", ""))
            old = _rl_store() / "originals"
            new = old / plat
            try:
                new.mkdir(parents=True, exist_ok=True)
                for f in old.glob("*.upk"):
                    shutil.move(str(f), str(new / f.name))
            except OSError:
                pass
        rl.update(folder="", app="", active={}, orig={}, stamp="")
        if not rl["platform"]:
            rl["platform"] = plat
        self.cfg.save()

    def detect(self) -> list:
        """Look for every install again. Returns the platforms found."""
        found = find_installs()
        for plat in PLATFORMS:                        # a folder the user picked by hand still counts
            e = self.rl["installs"].get(plat)
            if plat not in found and isinstance(e, dict) and e.get("manual") and rocket_league_ok(e.get("folder", "")):
                found[plat] = {"folder": os.path.normpath(e["folder"]), "app": e.get("app", "")}
        self.found = found
        for plat, info in found.items():
            e = self._entry(plat)
            if os.path.normcase(e["folder"]) != os.path.normcase(info["folder"]):
                e["folder"] = info["folder"]
                e["stamp"] = ""                        # a new place: treat it like an update
            if info["app"]:
                e["app"] = info["app"]
        if self.rl["platform"] not in found:
            self.rl["platform"] = next((p for p in PLATFORMS if p in found), "")
        self.cfg.save()
        return [p for p in PLATFORMS if p in found]

    def add_folder(self, folder: str) -> str:
        """A folder chosen by hand. Returns its platform, or "" if it is not Rocket League."""
        if not rocket_league_ok(folder):
            return ""
        plat = platform_of(folder)
        e = self._entry(plat)
        e.update(folder=os.path.normpath(folder), manual=True)
        self.rl["platform"] = plat
        self.cfg.save()
        self.detect()
        return plat

    def available(self) -> list:
        return [p for p in PLATFORMS if p in self.found]

    def platform(self) -> str:
        p = self.rl["platform"]
        return p if p in self.found else ""

    def set_platform(self, plat: str) -> bool:
        if plat not in self.found:
            return False
        self.rl["platform"] = plat
        self.cfg.save()
        return True

    def folder(self, plat: str = "") -> str:
        plat = plat or self.platform()
        return self.found.get(plat, {}).get("folder", "")

    def cooked(self, plat: str = "") -> Path:
        return Path(self.folder(plat)) / "TAGame" / "CookedPCConsole"

    def active(self, plat: str = "") -> dict:
        """The swaps the user wants on this install: {game file: item id}, one per game file.
        (Before 3.0 this was stored per category; only the item ids matter, so old settings still load.)"""
        plat = plat or self.platform()
        out = {}
        for ident in self._entry(plat)["active"].values() if plat else []:
            it = RL_BY_ID.get(ident)
            if it:
                out[rl_key(it)] = ident
        return out

    def actual(self, plat: str = "") -> dict:
        """What the game files really are right now: {game file: item id}."""
        plat = plat or self.platform()
        out = {}
        if not plat:
            return out
        for it in RL_ITEMS:
            src = swap_source(it)
            game = self.cooked(plat) / it["file"]
            if src is not None and game.is_file() and file_hash(game) == file_hash(src):
                out[rl_key(it)] = it["id"]
        return out

    def stamp(self, plat: str = "") -> str:
        exe = Path(self.folder(plat)) / "Binaries" / "Win64" / "RocketLeague.exe"
        try:
            st = exe.stat()
            return f"{st.st_size}:{int(st.st_mtime)}"
        except OSError:
            return ""

    def running(self, plat: str = "") -> bool:
        """Is this install's game running? (Unknown process paths count as running, to be safe.)"""
        folder = os.path.normcase(self.folder(plat))
        try:
            import psutil
            for p in psutil.process_iter(["name"]):
                if (p.info["name"] or "").lower() != RL_EXE:
                    continue
                try:
                    exe = os.path.normcase(p.exe() or "")
                except Exception:  # noqa: BLE001
                    return True
                if not folder or not exe or exe.startswith(folder):
                    return True
        except Exception:  # noqa: BLE001
            return False
        return False

    def _customs(self, filename: str) -> set:
        out = {h for h, name in _known_customs().items() if name.lower() == filename.lower()}
        for it in RL_ITEMS:
            if it["file"].lower() == filename.lower():
                src = swap_source(it)
                if src is not None:
                    out.add(file_hash(src))
        out.discard("")
        return out

    def check(self, plat: str = "") -> str:
        """off | ok | nogame | missing | nofile | changed | undone (for the wanted swaps of one install)"""
        plat = plat or self.platform()
        if not plat:
            return "nogame"
        act = self.active(plat)
        if not act:
            return "off"
        worst, order = "ok", ["ok", "undone", "changed", "nofile", "missing"]
        e = self._entry(plat)
        for ident in act.values():
            it = RL_BY_ID[ident]
            game = self.cooked(plat) / it["file"]
            src = swap_source(it)
            if not game.is_file():
                state = "missing"
            elif src is None:
                state = "nofile"
            elif file_hash(game) == file_hash(src):
                state = "ok"
            elif self.stamp(plat) != e["stamp"]:
                state = "undone"
            else:
                state = "changed"
            if order.index(state) > order.index(worst):
                worst = state
        return worst

    # -- applying (in a worker thread; settings are only written back on the main thread)
    def apply(self, desired: dict, reload: bool = False, quiet: bool = False, plat: str = "") -> bool:
        plat = plat or self.platform()
        if self.working:
            return False
        if not plat or not rocket_league_ok(self.folder(plat)):
            self.done.emit(False, "nogame", {"quiet": quiet})
            return False
        self.working = True
        desired = {rl_key(RL_BY_ID[i]): i for i in desired.values() if i in RL_BY_ID}
        e = self._entry(plat)
        job = {"plat": plat, "cooked": self.cooked(plat), "orig": dict(e["orig"]), "stamp_saved": e["stamp"],
               "stamp_now": self.stamp(plat)}
        import threading
        threading.Thread(target=self._work, args=(dict(desired), reload, quiet, job), daemon=True).start()
        return True

    def _work(self, desired: dict, reload: bool, quiet: bool, job: dict) -> None:
        plat = job["plat"]
        info = {"desired": desired, "reload": False, "quiet": quiet, "plat": plat}
        try:
            if self.running(plat):
                if not reload:
                    return self.done.emit(False, "running", info)
                info["reload"] = True
                self.busy.emit("close")
                self._close_game(plat)
                if self.running(plat):
                    return self.done.emit(False, "running", info)
            self.busy.emit("apply")
            ok, key, orig = self._apply(desired, job)
            info["orig"] = orig
            info["stamp"] = self.stamp(plat)
            self.done.emit(ok, key, info)
        except PermissionError:
            self.done.emit(False, "blocked", info)
        except Exception as exc:  # noqa: BLE001
            log.warning("swap failed: %s", exc)
            self.done.emit(False, "error", info)

    def _close_game(self, plat: str) -> None:
        folder = os.path.normcase(self.folder(plat))
        try:
            import psutil
            for p in psutil.process_iter(["name"]):
                if (p.info["name"] or "").lower() != RL_EXE:
                    continue
                try:
                    exe = os.path.normcase(p.exe() or "")
                except Exception:  # noqa: BLE001
                    exe = ""
                if not exe or exe.startswith(folder):
                    try:
                        p.kill()
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            return
        for _ in range(60):                           # up to 15 s for Windows to let go of the files
            if not self.running(plat):
                time.sleep(1.0)
                return
            time.sleep(0.25)

    def _apply(self, desired: dict, job: dict):
        """Make every swap file of one install match `desired`. Returns (ok, message key, originals)."""
        cooked = job["cooked"]
        backups = _rl_store() / "originals" / job["plat"]
        backups.mkdir(parents=True, exist_ok=True)
        orig = dict(job["orig"])
        updated = job["stamp_now"] != job["stamp_saved"]
        want_by_file = {}
        for ident in desired.values():
            it = RL_BY_ID.get(ident)
            if it:
                want_by_file[it["file"].lower()] = it
        files = sorted({it["file"] for it in RL_ITEMS}, key=str.lower)
        for name in files:
            game = cooked / name
            want = want_by_file.get(name.lower())
            if not game.is_file():
                if want:
                    return False, "missing", orig
                continue
            cur = file_hash(game)
            customs = self._customs(name)
            backup = backups / name
            if want:
                src = swap_source(want)
                if src is None:
                    return False, "nofile", orig
                want_hash = file_hash(src)
                if cur == want_hash:
                    continue
                if cur not in customs:
                    # The file in the game is an original. Keep it, unless it is a stranger's file
                    # (same game version but different from the original we saved).
                    tampered = (not updated) and orig.get(name) and orig.get(name) != cur and backup.is_file()
                    if not tampered:
                        _atomic_copy(game, backup)
                        if file_hash(backup) != cur:
                            return False, "error", orig
                        orig[name] = cur
                if not backup.is_file():
                    return False, "nobackup", orig
                _atomic_copy(src, game)
                if file_hash(game) != want_hash:
                    return False, "error", orig
            elif cur in customs:
                if not backup.is_file():
                    return False, "nobackup", orig
                _atomic_copy(backup, game)
                if orig.get(name) and file_hash(game) != orig[name]:
                    return False, "error", orig
        return True, "ok", orig

    def _finished(self, ok: bool, key: str, info: dict) -> None:
        self.working = False
        plat = info.get("plat")
        if plat in PLATFORMS:
            e = self._entry(plat)
            if "orig" in info:
                e["orig"] = info["orig"]
            if ok:
                e["active"] = dict(info.get("desired", {}))
                e["stamp"] = info.get("stamp", "")
                self._noticed = ""
        self.cfg.save()
        self.changed.emit()

    # -- start the game again after a reload
    def launch(self, plat: str = "") -> bool:
        plat = plat or self.platform()
        if plat == "steam":
            url = "steam://rungameid/252950"
        else:
            url = f"com.epicgames.launcher://apps/{self._entry(plat)['app'] or 'Sugar'}?action=launch&silent=true"
        return win.open_path(url)

    # -- watching for game updates and changed files (every install)
    def ensure_detected(self) -> None:
        if not self._detected:
            self._detected = True
            self.detect()

    def start(self) -> None:
        QTimer.singleShot(1500, self.ensure_detected)       # after the ball is on screen
        self._timer.start()
        QTimer.singleShot(4000, self.watch)

    def stop(self) -> None:
        self._timer.stop()

    def watch(self) -> None:
        self.ensure_detected()
        if self.working:
            return
        for plat in self.available():
            if not self.active(plat):
                continue
            state = self.check(plat)
            if state == "undone" and self.rl["auto_fix"] and not self.running(plat) and self._settled(plat):
                self.apply(self.active(plat), quiet=True, plat=plat)
                return
            if state in ("changed", "undone", "missing") and self._noticed != plat + state:
                self._noticed = plat + state
                self.changed.emit()

    def _settled(self, plat: str) -> bool:
        """True once the game files have not moved for a minute (an update has finished)."""
        newest = 0.0
        for it in RL_ITEMS:
            try:
                newest = max(newest, os.stat(self.cooked(plat) / it["file"]).st_mtime)
            except OSError:
                pass
        return time.time() - newest > 60


# --------------------------------------------------------------------------- #
# Crosshair library and share codes
# --------------------------------------------------------------------------- #
def _x(**kw) -> dict:
    return kw


SHAPE_KEYS = ("style", "length", "thickness", "gap", "dot", "dot_size", "radius")
_SHAPE0 = dict(style="cross", length=5, thickness=2, gap=3, dot=False, dot_size=2, radius=10)
# shapes only: colour, size and outline are your own settings and stay as they are
XHAIR_LIBRARY = [(name, {**_SHAPE0, **shape}) for name, shape in [
    ("Small cross", _x()),
    ("Cross", _x(length=8, gap=4)),
    ("Cross and dot", _x(length=6, gap=4, dot=True)),
    ("Dot", _x(style="dot", dot_size=4)),
    ("T", _x(style="tee", length=8, gap=3)),
    ("Circle", _x(style="circle", radius=8, length=0)),
]]
_CODE_KEYS = [("s", "style"), ("c", "color"), ("o", "opacity"), ("l", "length"), ("t", "thickness"), ("g", "gap"),
              ("d", "dot"), ("ds", "dot_size"), ("ol", "outline"), ("ow", "outline_w"), ("r", "radius"), ("z", "size")]
_LIMITS = {"opacity": (10, 100), "length": (0, 40), "thickness": (1, 10), "gap": (0, 30), "dot_size": (1, 12),
           "outline_w": (1, 4), "radius": (2, 60), "size": (50, 300)}


def xhair_encode(c: dict) -> str:
    data = {short: c[key] for short, key in _CODE_KEYS if key in c}
    raw = json.dumps(data, separators=(",", ":")).encode()
    return "RBX-" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def xhair_decode(text: str):
    """Crosshair settings from a share code, or None. Unknown fields are ignored, missing ones use defaults,
    so codes from older and newer versions keep working."""
    try:
        text = "".join((text or "").split())
        if not text.upper().startswith("RBX-"):
            return None
        body = text[4:]
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode("utf-8"))
        if not isinstance(data, dict):
            return None
        out: dict = {}
        for short, key in _CODE_KEYS:
            if short not in data:
                continue
            v = data[short]
            if key == "style" and v in ("cross", "tee", "dot", "circle"):
                out[key] = v
            elif key == "color" and isinstance(v, str) and QColor(v).isValid():
                out[key] = QColor(v).name().upper()
            elif key in ("dot", "outline") and isinstance(v, bool):
                out[key] = v
            elif key in _LIMITS and isinstance(v, (int, float)) and not isinstance(v, bool):
                lo, hi = _LIMITS[key]
                out[key] = int(max(lo, min(hi, v)))
        return out or None
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# Session stats (very light: one sample every 5 seconds)
# --------------------------------------------------------------------------- #
class Session(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.started = time.monotonic()
        self.cpu_peak = self.ram_peak = 0.0
        self.cpu_sum, self.n = 0.0, 0
        self.temp_peak = None
        self.ping_sum, self.ping_n = 0.0, 0
        self._ps = None
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._sample)
        self._timer.start()

    def _sample(self) -> None:
        try:
            if self._ps is None:
                import psutil
                self._ps = psutil
                psutil.cpu_percent(None)
                return
            cpu = self._ps.cpu_percent(None)
            self.cpu_peak = max(self.cpu_peak, cpu)
            self.cpu_sum += cpu
            self.n += 1
            self.ram_peak = max(self.ram_peak, self._ps.virtual_memory().percent)
        except Exception:  # noqa: BLE001
            self._timer.stop()

    def feed(self, d: dict) -> None:
        """Extra readings whenever the Stats page or the on-screen stats are sampling."""
        if d.get("temp") is not None:
            self.temp_peak = max(self.temp_peak or 0, d["temp"])
        if d.get("ping") is not None:
            self.ping_sum += d["ping"]
            self.ping_n += 1

    def duration(self) -> float:
        return time.monotonic() - self.started


def hours_text(seconds: float) -> str:
    h = seconds / 3600
    if h < 1:
        return f"{int(seconds // 60)} min"
    return f"{h:.1f} h" if h < 10 else f"{int(h)} h"


# --------------------------------------------------------------------------- #
# Updates from GitHub Releases
# --------------------------------------------------------------------------- #
UPDATE_REPO = "REMMETT-py/rubenium"
UPDATE_PAGE = f"https://github.com/{UPDATE_REPO}/releases/latest"


def version_tuple(text: str) -> tuple:
    import re
    nums = re.findall(r"\d+", text or "")
    return tuple(int(n) for n in nums[:4]) if nums else (0,)


def app_home() -> Path:
    """A folder Windows always lets the app write to (used for downloads and, if needed, for the app itself)."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return Path(base) / "Rubenium"


def side_exe() -> Path:
    return app_home() / "app" / "Rubenium.exe"


def side_version() -> str:
    try:
        return (app_home() / "app" / "version.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def clean_env() -> dict:
    """Environment for starting another copy of the app: a packed .exe must not inherit this one's temp folder."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("_MEI", "_PYI"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def _same_file(a, b) -> bool:
    try:
        return os.path.normcase(os.path.realpath(str(a))) == os.path.normcase(os.path.realpath(str(b)))
    except OSError:
        return False


def _retry(fn, tries: int = 24, wait: float = 0.5):
    """Windows and antivirus hold new files for a moment: try again for a few seconds before giving up."""
    last = None
    for n in range(tries):
        try:
            return fn()
        except OSError as exc:
            last = exc
            time.sleep(wait if n else 0.15)
    raise last


def handoff(current: str) -> bool:
    """If an update had to be installed beside the original .exe (its folder was protected), every start of the
    original passes straight on to that newer copy. True when it did: the caller just exits."""
    import subprocess
    import sys
    if not getattr(sys, "frozen", False) or "--no-handoff" in sys.argv:
        return False
    side = side_exe()
    try:
        if (not side.is_file() or _same_file(sys.executable, side)
                or version_tuple(side_version()) <= version_tuple(current)):
            return False
        log.info("handing over to %s (%s)", side, side_version())
        subprocess.Popen([str(side), *sys.argv[1:]], close_fds=True, env=clean_env(), cwd=str(side.parent))
        return True
    except OSError as exc:
        log.warning("hand-over failed: %s", exc)
        return False


def place_exe(new: Path, version: str) -> str:
    """Put a downloaded, verified .exe into use and return the path to start.
    1. Next to the running app: the running file is renamed (Windows allows that), the new one takes its name.
    2. If that folder cannot be written (Windows 'Controlled folder access', Program Files, read-only...),
       the new version goes to the app's own folder in AppData and the old .exe hands over to it from then on."""
    import shutil
    import sys
    target = Path(sys.executable).resolve()
    if not os.environ.get("RUBENIUM_TEST_SIDE"):
        tmp = target.with_name(target.stem + ".new.exe")
        old = target.with_name(target.stem + ".old.exe")
        try:
            try:
                old.unlink()
            except OSError:
                pass
            _retry(lambda: shutil.copyfile(new, tmp), tries=6)
            if file_hash(tmp) != file_hash(new):
                raise OSError("copy does not match")
            _retry(lambda: os.replace(target, old))
            try:
                _retry(lambda: os.replace(tmp, target))
            except OSError:
                _retry(lambda: os.replace(old, target))     # put the working one back
                raise
            if _same_file(target, side_exe()):
                try:
                    (target.parent / "version.txt").write_text(version, encoding="utf-8")
                except OSError:
                    pass
            return str(target)
        except OSError as exc:
            log.warning("could not update in place (%s): installing in %s", exc, app_home())
            try:
                tmp.unlink()
            except OSError:
                pass
    side = side_exe()
    if _same_file(target, side):
        raise PermissionError("the app's own folder cannot be written")
    side.parent.mkdir(parents=True, exist_ok=True)
    part = side.with_name("Rubenium.part")
    _retry(lambda: shutil.copyfile(new, part))
    if file_hash(part) != file_hash(new):
        raise OSError("copy does not match")
    _retry(lambda: os.replace(part, side))
    (side.parent / "version.txt").write_text(version, encoding="utf-8")
    return str(side)


class Updater(QObject):
    """Checks the latest GitHub release, downloads it, checks its SHA-256 and swaps the app in place.

    Release assets it understands: Rubenium.exe, Rubenium.py, swaps.zip, each with a matching .sha256 file.
    Nothing is installed unless its checksum matches."""
    found = pyqtSignal(dict)          # a newer version is out
    checked = pyqtSignal(bool, str)   # manual check finished: ok, message key ("latest" / "offline")
    progress = pyqtSignal(int)        # download percent
    failed = pyqtSignal(str)          # install failed: message key
    ready = pyqtSignal(str)           # installed: path to start

    def __init__(self, current: str) -> None:
        super().__init__()
        self.current = current
        self.latest: dict = {}
        self.busy = False
        self._timer = QTimer(self)
        self._timer.setInterval(6 * 3600 * 1000)
        self._timer.timeout.connect(lambda: self.check(manual=False))

    def start(self) -> None:
        self._timer.start()
        QTimer.singleShot(15000, lambda: self.check(manual=False))

    def stop(self) -> None:
        self._timer.stop()

    @staticmethod
    def _get(url: str, limit: int = 2_000_000, accept: str = "application/vnd.github+json") -> bytes:
        import ssl
        import urllib.request
        try:
            import certifi  # type: ignore
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:  # noqa: BLE001
            ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "Rubenium-updater", "Accept": accept})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:  # noqa: S310
            data = resp.read(limit + 1)
        if len(data) > limit:
            raise ValueError("response too large")
        return data

    def check(self, manual: bool = False) -> None:
        if self.busy:
            return
        self.busy = True
        import threading
        threading.Thread(target=self._check, args=(manual,), daemon=True).start()

    def _check(self, manual: bool) -> None:
        try:
            rel = json.loads(self._get(f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest").decode("utf-8"))
            tag = str(rel.get("tag_name", ""))
            assets = {str(a.get("name", "")): str(a.get("browser_download_url", ""))
                      for a in rel.get("assets", []) if isinstance(a, dict)}
            import re
            shown = re.search(r"\d+(?:\.\d+)+", str(rel.get("name", "")))       # "Rubenium 1.0" -> 1.0
            info = {"version": tag.lstrip("vV"), "label": shown.group(0) if shown else tag.lstrip("vV"),
                    "page": str(rel.get("html_url", UPDATE_PAGE)), "assets": assets}
            self.busy = False
            if version_tuple(tag) > version_tuple(self.current):
                self.latest = info
                self.found.emit(info)
                if manual:
                    self.checked.emit(True, "found")
            elif manual:
                self.checked.emit(True, "latest")
        except Exception as exc:  # noqa: BLE001
            log.info("update check failed: %s", exc)
            self.busy = False
            if manual:
                self.checked.emit(False, "offline")

    # -- installing
    def install(self) -> bool:
        if self.busy or not self.latest:
            return False
        self.busy = True
        import threading
        threading.Thread(target=self._install, args=(dict(self.latest),), daemon=True).start()
        return True

    def _download(self, url: str, dest: Path, share: tuple) -> None:
        import urllib.request
        import ssl
        try:
            import certifi  # type: ignore
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:  # noqa: BLE001
            ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "Rubenium-updater"})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp, open(dest, "wb") as out:  # noqa: S310
            total = int(resp.headers.get("Content-Length") or 0)
            got, last = 0, -1
            while True:
                block = resp.read(1 << 16)
                if not block:
                    break
                got += len(block)
                if got > 400 * 1024 * 1024:
                    raise ValueError("download too large")
                out.write(block)
                if total:
                    pct = share[0] + int((share[1] - share[0]) * got / total)
                    if pct != last:
                        last = pct
                        self.progress.emit(pct)

    def _fetch_checked(self, assets: dict, name: str, dest: Path, share: tuple) -> bool:
        """Download `name` to `dest` and verify it against `name`.sha256. False if there is no checksum."""
        sha_url = assets.get(name + ".sha256")
        if not sha_url or not assets.get(name):
            return False
        want = self._get(sha_url, 10_000, "application/octet-stream").decode("utf-8", "ignore").split()[0].lower()
        if len(want) != 64:
            raise ValueError("bad checksum file")
        self._download(assets[name], dest, share)
        if file_hash(dest) != want:
            dest.unlink(missing_ok=True)
            raise ValueError("checksum mismatch")
        return True

    def _install(self, info: dict) -> None:
        import sys
        import zipfile
        assets = info["assets"]
        try:
            if getattr(sys, "frozen", False):
                work = app_home() / "update"                  # never the app's own folder: it may be protected
                try:
                    work.mkdir(parents=True, exist_ok=True)
                except OSError:
                    import tempfile
                    work = Path(tempfile.gettempdir())
                new = work / "Rubenium.download"
                done = False
                for attempt in range(3):                      # a dropped connection is tried again
                    try:
                        done = self._fetch_checked(assets, "Rubenium.exe", new, (0, 100))
                        break
                    except (OSError, ValueError) as exc:
                        log.info("download attempt %d failed: %s", attempt + 1, exc)
                        if attempt == 2:
                            raise
                        time.sleep(2.0)
                if not done:
                    raise FileNotFoundError("no exe in release")
                path = place_exe(new, info["version"])
                try:
                    new.unlink()
                except OSError:
                    pass
                self.busy = False
                self.ready.emit(path)
            else:
                script = Path(sys.argv[0]).resolve()
                new = script.with_name(script.name + ".download")
                if not self._fetch_checked(assets, "Rubenium.py", new, (0, 70)):
                    raise FileNotFoundError("no script in release")
                zip_tmp = script.with_name("swaps.zip.download")
                if assets.get("swaps.zip") and self._fetch_checked(assets, "swaps.zip", zip_tmp, (70, 100)):
                    root = script.parent / "swaps"
                    with zipfile.ZipFile(zip_tmp) as z:
                        for member in z.infolist():
                            parts = Path(member.filename).parts
                            if (member.is_dir() or len(parts) != 3 or parts[0] != "swaps" or ".." in parts
                                    or not parts[2].lower().endswith((".upk", ".png", ".jpg", ".webp"))):
                                continue            # only swaps/<id>/<file>: game files and pictures
                            dest = root / parts[1] / parts[2]
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            tmp = dest.with_name(dest.name + ".part")
                            with z.open(member) as src, open(tmp, "wb") as out:
                                out.write(src.read())
                            os.replace(tmp, dest)
                    zip_tmp.unlink(missing_ok=True)
                os.replace(new, script)
                self.busy = False
                self.ready.emit(str(script))
        except PermissionError:
            self.busy = False
            self.failed.emit("blocked")
        except Exception as exc:  # noqa: BLE001
            log.warning("update failed: %s", exc)
            self.busy = False
            self.failed.emit("error")

    @staticmethod
    def cleanup() -> None:
        """Remove what an earlier update left behind."""
        import sys
        here = Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0]).resolve()
        junk = [here.parent / n for n in (here.stem + ".old.exe", here.stem + ".new.exe", here.stem + ".download",
                                          here.name + ".download", "swaps.zip.download")]
        junk += [app_home() / "update" / "Rubenium.download", app_home() / "app" / "Rubenium.part"]
        for f in junk:
            try:
                f.unlink()
            except OSError:
                pass


def restart(path: str, extra: tuple = ()) -> bool:
    """Start the (new) app again; the running copy then quits."""
    import subprocess
    import sys
    args = ["--updated", *extra]
    try:
        if getattr(sys, "frozen", False):
            subprocess.Popen([path, *args], close_fds=True, env=clean_env(), cwd=os.path.dirname(path) or None)
        else:
            exe = sys.executable
            pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
            subprocess.Popen([pyw if os.path.exists(pyw) else exe, path, *args], close_fds=True)
        return True
    except OSError as exc:
        log.warning("restart failed: %s", exc)
        return False


class TopApps(QObject):
    """Which apps use the most processor and memory right now (grouped by app name, sampled in a thread)."""
    ready = pyqtSignal(list, list)      # [(name, percent of the whole processor)], [(name, bytes)]

    def __init__(self) -> None:
        super().__init__()
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._kick)
        self._busy = False
        self._procs: dict = {}

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
            self._kick()
            QTimer.singleShot(700, self._kick)      # processor use needs two looks: show numbers quickly

    def stop(self) -> None:
        self._timer.stop()

    def _kick(self) -> None:
        if self._busy:
            return
        self._busy = True
        import threading
        threading.Thread(target=self._sample, daemon=True).start()

    def _sample(self) -> None:
        cpu: dict = {}
        ram: dict = {}
        try:
            import psutil
            cores = psutil.cpu_count() or 1
            seen = {}
            for proc in psutil.process_iter(["pid", "name"]):
                pid, name = proc.info["pid"], proc.info["name"] or ""
                if not pid or not name or name in ("System Idle Process", "Idle", "Memory Compression"):
                    continue
                keep = self._procs.get(pid)
                if keep is None or keep[0] != name:
                    keep = (name, proc)
                    try:
                        proc.cpu_percent(None)              # first look: nothing to report yet
                    except Exception:  # noqa: BLE001
                        continue
                    seen[pid] = keep
                    used = 0.0
                else:
                    seen[pid] = keep
                    try:
                        used = keep[1].cpu_percent(None) / cores
                    except Exception:  # noqa: BLE001
                        continue
                try:
                    mem = keep[1].memory_info().rss
                except Exception:  # noqa: BLE001
                    mem = 0
                label = name[:-4] if name.lower().endswith(".exe") else name
                cpu[label] = cpu.get(label, 0.0) + used
                ram[label] = ram.get(label, 0) + mem
            self._procs = seen
        except Exception as exc:  # noqa: BLE001
            log.debug("top apps: %s", exc)
        top_cpu = sorted(cpu.items(), key=lambda kv: kv[1], reverse=True)[:5]
        top_ram = sorted(ram.items(), key=lambda kv: kv[1], reverse=True)[:5]
        self._busy = False
        try:
            self.ready.emit(top_cpu, top_ram)
        except RuntimeError:
            pass


# ==================================================================================================
# SECTION: pages
# ==================================================================================================
import bisect
import copy
import os
import shutil
import tempfile
import time
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QAbstractButton, QFileDialog, QGridLayout, QWidget



def clock(ms: float) -> str:
    s = max(0, int(ms // 1000))
    return f"{s // 60}:{s % 60:02d}"


class Page(QWidget):
    key = ""
    fixed_height = 0

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self.W = S(CARD_W - 2 * PAD)

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
class HomePage(Page):
    key = "home"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        self._opt_until, self._opt_playing = 0.0, False
        lay = vbox(self, 8)
        body = hbox(spacing=12)
        self.art = ArtWidget(88)
        info = vbox(spacing=1)
        top = hbox(spacing=6)
        self.title = Label("", 15, bold=True)
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
        info.addLayout(top)
        info.addWidget(self.artist)
        info.addStretch(1)
        info.addLayout(controls)
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
        if self.vol._drag:
            return
        res = self.ctx.appvol.get(self._vol_match()) if self.ctx.state.source_id else None
        show = res is not None
        if show != self.vol.isVisible():
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
        """The menu bar is hiding: the music app name fades with it."""
        self.chip.fade = max(0.0, min(1.0, (level - 0.2) / 0.8))
        self.chip.update()

    def on_hide(self) -> None:
        self._timer.stop()
        self._vol_timer.stop()

    def on_art(self, pixmap) -> None:
        self.art.set_pixmap(pixmap)

    def _toggle(self) -> None:
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
            title, artist = tr("No music app is open"), tr("Press play to open Spotify")
        self.title.set_text(title)
        self.artist.set_text(artist)
        self.setToolTip(st.message if st.status is Status.UNAVAILABLE else "")

        pinned = bool(self.ctx.cfg["source"])
        chip = st.source or (tr("Auto") if not pinned else "")
        self.chip.setVisible(bool(st.sources) or pinned)
        text = ("● " if pinned else "") + (chip or tr("Auto"))
        self.chip.set_text(text)
        self.chip.setFixedWidth(QFontMetrics(font(12, QFont.Weight.DemiBold)).horizontalAdvance(text) + S(16))

        self.b_shuffle.setVisible(st.shuffle is not None)        # never a dead control
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
    if out["style"] not in ("cross", "tee", "dot", "circle"):
        out["style"] = "cross"
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


STYLES = ["cross", "tee", "dot", "circle"]


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
        self.style = Segmented([tr("Cross"), tr("T"), tr("Dot"), tr("Circle")],
                               STYLES.index(c["style"]) if c["style"] in STYLES else 0)
        self.style.changed.connect(lambda i: self._set("style", STYLES[i]))
        lay.addWidget(self.style)
        self.sw = Swatches(XH_COLORS, c["color"])
        self.sw.picked.connect(lambda col: self._set("color", col))
        lay.addWidget(self.sw)
        hue = QColor(c["color"]).hsvHue()
        self.hue = SliderRow(tr("Other colour"), 0, 359, hue if hue >= 0 else 0, 1, fmt=lambda v: f"{int(v)}°",
                             marks=[0, 60, 120, 180, 240, 300])
        self.hue.slider.rainbow = True
        self.hue.changed.connect(self._hue)
        lay.addWidget(self.hue)

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

    def _set(self, key: str, value) -> None:
        self.ctx.cfg["crosshair"][key] = value
        if key == "color":
            self.sw.set_current(value)
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
    key = "display"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        eng = ctx.display
        eng.probe()
        cfg = ctx.cfg
        self.slot = eng.manual if eng.manual in ("A", "B") else "A"
        pr = cfg["display"][self.slot]
        lay = vbox(self, 7)

        self.t_on = Toggle(eng.manual in ("A", "B"))
        self.t_on.toggled_by_user.connect(self._power)
        lay.addWidget(row(tr("Change my screen colours"), self.t_on))
        self.seg = Segmented([tr("Custom 1"), tr("Custom 2")], 0 if self.slot == "A" else 1)
        self.seg.changed.connect(self._slot)
        lay.addWidget(self.seg)

        self.rows: dict = {}
        pct = lambda v: f"{int(v):+d}"  # noqa: E731

        def add(key, label, lo, hi, fmt, marks, default=None):
            value = pr[key]
            default = DISPLAY_PROFILE[key] if default is None else default
            if value < lo:                                    # "keep the PC's own value"
                value = default
            r = SliderRow(label, lo, hi, value, 1, default, fmt, marks=sorted(set(marks + [default])))
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
        b_reset = Button(tr("Reset colours"), "danger", 34)
        b_reset.clicked.connect(self._reset)
        lay.addWidget(b_reset)
        eng.changed.connect(self._refresh)

    def on_show(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        eng = self.ctx.display
        self.t_on.set_checked(eng.manual in ("A", "B"))
        if eng.manual in ("A", "B") and eng.manual != self.slot:
            self.slot = eng.manual
            self.seg.set_index(0 if self.slot == "A" else 1)
            self._load_rows()

    def _load_rows(self) -> None:
        pr = self.ctx.cfg["display"][self.slot]
        for key, r in self.rows.items():
            r.set_value(r.slider.default if pr[key] < r.slider.lo else pr[key])

    def _power(self, on: bool) -> None:
        self.ctx.display.set_active(self.slot if on else "off")

    def _slot(self, i: int) -> None:
        self.slot = "AB"[i]
        self._load_rows()
        if self.ctx.display.manual in ("A", "B"):
            self.ctx.display.set_active(self.slot)

    def _set(self, key: str, value: int) -> None:
        self.ctx.cfg["display"][self.slot][key] = value
        self.ctx.cfg.save()
        if not self.ctx.display.active:              # moving a slider shows the result straight away
            self.t_on.set_checked(True)
            self.ctx.display.set_active(self.slot)
        elif self.ctx.display.effective == self.slot:
            self.ctx.display.apply()

    def _reset(self) -> None:
        self.ctx.cfg["display"][self.slot] = dict(DISPLAY_PROFILE)
        self.ctx.cfg.save()
        self._load_rows()
        self.ctx.display.apply()
        self.ctx.toast(tr("Custom {n} reset", n=1 if self.slot == "A" else 2))


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
    """Five rows: app name, how much it uses, and a bar."""
    ROWS = 5

    def __init__(self) -> None:
        super().__init__()
        self.rows: list = []            # (name, value text, fraction of the bar)
        self.setFixedHeight(S(26) * self.ROWS)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_rows(self, rows: list) -> None:
        if rows != self.rows:
            self.rows = rows
            self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rh, w = S(26), self.width()
        vw = S(64)
        for i in range(self.ROWS):
            y = i * rh
            if i >= len(self.rows):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha("#FFFFFF", 0.05))
                p.drawRoundedRect(QRectF(0, y + S(17), w, S(3)), 1.5, 1.5)
                continue
            name, value, frac = self.rows[i]
            p.setFont(font(12, QFont.Weight.DemiBold))
            p.setPen(QColor(TEXT))
            p.drawText(QRectF(0, y, w - vw - S(8), S(16)), int(Qt.AlignmentFlag.AlignVCenter),
                       p.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, int(w - vw - S(8))))
            p.setFont(font(11.5))
            p.setPen(QColor(TEXT_DIM))
            p.drawText(QRectF(w - vw, y, vw, S(16)), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), value)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha("#FFFFFF", 0.08))
            p.drawRoundedRect(QRectF(0, y + S(17), w, S(3)), 1.5, 1.5)
            p.setBrush(ui.accent)
            p.drawRoundedRect(QRectF(0, y + S(17), max(S(3), w * max(0.0, min(1.0, frac))), S(3)), 1.5, 1.5)


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
        self.g_cpu, self.g_ram = PickGauge(tr("Processor")), PickGauge(tr("Memory"))
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
        self.top_seg = Segmented([tr("Processor"), tr("Memory")], 0)
        self.top_seg.changed.connect(self._top_pick)
        lay.addWidget(self.top_seg)
        self.top_list = TopList()
        lay.addWidget(self.top_list)
        self._top_data = ([], [])
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
        items = [("cpu", tr("Processor")), ("ram", tr("Memory")), ("ping", tr("Ping")), ("net", tr("Internet")),
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
                 ("ram", tr("Memory, highest")), ("ping", tr("Ping, average"))]
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

    def _top_ready(self, cpu: list, ram: list) -> None:
        self._top_data = (cpu, ram)
        self._top_show()

    def _top_show(self) -> None:
        cpu, ram = self._top_data
        if self.top_kind == 0:
            top = max([v for _, v in cpu] + [1.0])
            rows = [(n, f"{v:.0f}%" if v >= 9.5 else f"{v:.1f}%", v / top) for n, v in cpu]
        else:
            top = max([b for _, b in ram] + [1])
            rows = [(n, f"{b / 2 ** 30:.1f} GB" if b >= 2 ** 30 else f"{b / 2 ** 20:.0f} MB", b / top) for n, b in ram]
        self.top_list.set_rows(rows)

    def _hud_reset(self) -> None:
        pass
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
            lines.append(tr("Memory") + f": {psutil.virtual_memory().total / 2 ** 30:.0f} GB")
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
        pass
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        d = BD()
        shape = QRectF(self.width() / 2 - d / 2, self.height() / 2 - d / 2, d, d)
        level = self.ctx.glow_level()
        paint_shape(p, self.ctx, shape, d / 2, level, self.devicePixelRatioF())
        paint_ball_face(p, self.ctx, shape, 1.0)
        paint_edge(p, self.ctx, shape, d / 2, level)


class SettingsPage(Page):
    key = "settings"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        cfg = ctx.cfg
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

        lay.addWidget(heading(tr("Appearance")))
        toggle(tr("Glow"), "halo", after=lambda v: ctx.refresh_look())
        toggle(tr("Progress ring"), "ring", after=lambda v: ctx.refresh_look())
        toggle(tr("Match album colour"), "accent_from_art", after=lambda v: ctx.refresh_accent())
        toggle(tr("Hide menu bar when idle"), "autohide", after=lambda v: ctx.window.chrome_setting())
        toggle(tr("Welcome screen"), "welcome")
        seg = Segmented(["English", "Français"], 1 if lang() == "fr" else 0)
        seg.setFixedWidth(S(170))
        seg.changed.connect(lambda i: ctx.set_language("fr" if i else "en"))
        lay.addWidget(row(tr("Language"), seg))
        size = SliderRow(tr("Size"), 70, 150, cfg["scale"], 10, 100, lambda v: f"{int(v)}%",
                         marks=list(range(70, 151, 10)))
        size.released.connect(lambda v: ctx.set_scale(int(v)))        # applied when you let go
        lay.addWidget(size)

        lay.addWidget(heading(tr("Ball")))
        self.preview = BallPreview(ctx)
        lay.addWidget(self.preview)
        ball = SliderRow(tr("Ball size"), min(BALL_SIZES), max(BALL_SIZES), cfg["ball_size"], 10, 100,
                         lambda v: f"{int(v)}%", marks=list(BALL_SIZES))
        ball.changed.connect(lambda v: (ctx.set_look("ball_size", int(v)), self.preview.update()))
        lay.addWidget(ball)

        lay.addWidget(heading(tr("Menu bar")))
        pass
        for key, _icon, label in TABS:                 # Home, Lyrics and Settings always stay
            if key in LOCKED_TABS:
                continue
            t = Toggle(bool(cfg["news_tab"]) if key == "new" else not cfg["tabs_off"].get(key))
            t.toggled_by_user.connect(lambda v, k=key: ctx.set_tab(k, v))
            lay.addWidget(row(tr(label), t))

        if win.IS_WIN:
            lay.addWidget(heading(tr("Windows")))
            t = Toggle(win.autostart_get())

            def auto(v, t=t):
                if win.autostart_set(v):
                    cfg["autostart"] = v
                else:
                    t.set_checked(not v)
            t.toggled_by_user.connect(auto)
            lay.addWidget(row(tr("Start with Windows"), t))

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

        lay.addSpacing(S(6))
        quit_btn = Button(tr("Quit Rubenium"), "ghost", 34)
        quit_btn.clicked.connect(ctx.quit)
        lay.addWidget(quit_btn)
        reset = Button(tr("Reset settings"), "danger", 34)
        reset.clicked.connect(self._reset)
        lay.addWidget(reset)
        self._confirm_until = 0.0

    def _reset(self) -> None:
        if time.monotonic() > self._confirm_until:
            self._confirm_until = time.monotonic() + 4
            return self.ctx.toast(tr("Press again to reset everything"), "warn")
        self.ctx.cfg.reset()
        self.ctx.apply_config()
        self.ctx.toast(tr("Settings reset"))


# ==================================================================================================
# SECTION: pages2
# ==================================================================================================
import os

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QAbstractButton, QFileDialog, QGridLayout, QWidget



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
ACCENTS = [ACCENT_DEFAULT, "#5AC8FA", "#2ED9C3", "#1DB954", "#8BE04E", "#FFD23F", "#FF8A3D", "#FF5A3C",
           "#FF5C8A", "#E05BFF", "#A66BFF", "#6C7BFF", "#C9A26B", "#B8C2CC", "#8A939B", "#FFFFFF"]


class ThemeCard(QAbstractButton):
    """Mini card showing a theme's background design, with its lock and progress."""

    def __init__(self, theme: dict, page: "ThemesPage") -> None:
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
        hours = ctx.usage_hours()
        unlocked = hours >= th["hours"]
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
        p.setOpacity(1.0 if unlocked else 0.55 + 0.25 * h)
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
            p.setPen(QColor(TEXT_DIM))
            p.drawText(foot, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), f"{th['hours']} h")
            p.save()
            p.translate(foot.left() + S(6), foot.center().y())
            p.scale(S(11) / 20, S(11) / 20)
            draw_icon(p, "lock", QColor(TEXT_DIM))
            p.restore()
            p.setPen(Qt.PenStyle.NoPen)
            bar = QRectF(foot.left() + S(18), foot.center().y() - S(1.5), foot.width() - S(62), S(3))
            p.setBrush(alpha("#FFFFFF", 0.12))
            p.drawRoundedRect(bar, 1.5, 1.5)
            p.setBrush(ui.accent)
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * min(1.0, hours / th["hours"]), bar.height()), 1.5, 1.5)


STYLE_ROWS = (("Glow", "glow_power", ("Normal", "Strong"), (1, 2)),
              ("Background", "backdrop", ("Dark", "Black"), (0, 1)),
              ("Corners", "corners", ("Round", "Sharp"), (0, 2)))


class UnlockTile(QAbstractButton):
    """A small ball showing one style of the R or of the song ring. Locked ones show the hours they need."""

    def __init__(self, kind: str, style: dict, key: str, page) -> None:
        super().__init__()
        self.kind, self.style, self.key, self.page = kind, style, key, page
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
        open_ = ctx.usage_hours() >= st["hours"]
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
            extras.paint_r(p, box, d, st["id"], ui.accent, 0.0)
        else:
            ring = QRectF(c.x() - d / 2, c.y() - d / 2, d, d).adjusted(S(6), S(6), -S(6), -S(6))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(extras.ring_pen(st["id"], alpha("#FFFFFF", 0.12), S(2.4)))
            p.drawEllipse(ring)
            p.setPen(extras.ring_pen(st["id"], ui.accent, S(2.4)))
            p.drawArc(ring, 90 * 16, int(-360 * 16 * 0.68))
        p.setOpacity(1.0)
        foot = QRectF(0, S(4) + d + S(4), self.width(), S(16))
        p.setFont(font(10, QFont.Weight.DemiBold))
        if open_:
            p.setPen(ui.accent if active else mix(QColor(TEXT_DIM), QColor(TEXT), h))
            p.drawText(foot, int(Qt.AlignmentFlag.AlignCenter), tr(st["name"]))
        else:
            text = f"{st['hours']} h"
            tw = p.fontMetrics().horizontalAdvance(text) + S(13)
            x = (self.width() - tw) / 2
            p.save()
            p.translate(x + S(5), foot.center().y())
            p.scale(S(10) / 20, S(10) / 20)
            draw_icon(p, "lock", QColor(TEXT_DIM))
            p.restore()
            p.setPen(QColor(TEXT_DIM))
            p.drawText(QRectF(x + S(13), foot.top(), tw, foot.height()), int(Qt.AlignmentFlag.AlignVCenter), text)


class ThemesPage(Page):
    key = "themes"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        lay = vbox(self, 8)
        lay.addWidget(heading(tr("Colour")))
        self.sw = Swatches(ACCENTS, ctx.cfg["custom_accent"] or ACCENT_DEFAULT, per_row=8)
        self.sw.picked.connect(self._accent)
        lay.addWidget(self.sw)
        lay.addWidget(heading(tr("Style")))
        self.style = {}
        for label, key, names, values in STYLE_ROWS:       # two choices each: (setting value for 1st, 2nd)
            seg = Segmented([tr(n) for n in names], 1 if ctx.cfg[key] == values[1] else 0)
            seg.setFixedWidth(S(170))
            seg.changed.connect(lambda i, k=key, v=values: ctx.set_look(k, v[i]))
            self.style[key] = seg
            lay.addWidget(row(tr(label), seg))
        lay.addWidget(heading(tr("Ball")))
        self.unlocks = []
        for kind, styles, key in (("r", extras.R_STYLES, "ball_style"), ("ring", extras.RING_STYLES, "ring_style")):
            line = hbox(spacing=6)
            for st in styles:
                tile = UnlockTile(kind, st, key, self)
                tile.clicked.connect(lambda _=False, t=tile: self._unlock_pick(t))
                line.addWidget(tile)
                self.unlocks.append(tile)
            line.addStretch(1)
            lay.addLayout(line)
        lay.addWidget(heading(tr("Themes")))
        self.used = Label("", 12, TEXT_DIM)
        lay.addWidget(self.used)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(S(2))
        self.cards = []
        for i, th in enumerate(extras.THEMES):
            card = ThemeCard(th, self)
            card.clicked.connect(lambda _=False, t=th: self._pick(t))
            grid.addWidget(card, i // 2, i % 2)
            self.cards.append(card)
        lay.addLayout(grid)
        lay.addSpacing(S(4))
        reset = Button(tr("Reset look"), "danger", 34)
        reset.clicked.connect(self._reset)
        lay.addWidget(reset)
        self._refresh()

    def _reset(self) -> None:
        self.ctx.window.drawer.close_now()
        self.ctx.cfg["custom_accent"] = ""
        for _label, key, _names, values in STYLE_ROWS:
            self.ctx.set_look(key, values[0])
            self.style[key].set_index(0)
        self.ctx.cfg["ball_style"], self.ctx.cfg["ring_style"] = "classic", "line"
        self.ctx.window.ball.update()
        self.ctx.set_theme("clean")
        self.sw.set_current(ACCENT_DEFAULT)
        self.ctx.refresh_accent()
        self._refresh()

    def on_show(self) -> None:
        self._refresh()

    def _unlock_pick(self, tile) -> None:
        if self.ctx.usage_hours() < tile.style["hours"]:
            return self.ctx.toast(tr("Unlocks after {n} h of use", n=tile.style["hours"]), "warn")
        self.ctx.cfg[tile.key] = tile.style["id"]
        self.ctx.window.ball.update()
        for t in self.unlocks:
            t.update()

    def _refresh(self) -> None:
        self.used.set_text(tr("Time used: {t}", t=extras.hours_text(self.ctx.cfg["usage_s"])))
        for c in self.cards:
            c.update()

    def _pick(self, th: dict) -> None:
        drawer = self.ctx.window.drawer
        if self.ctx.usage_hours() >= th["hours"]:
            drawer.close_now()
            self.ctx.set_theme(th["id"])
        elif drawer.is_open() and drawer.theme is th:
            drawer.close_drawer()
        else:
            drawer.open_for(th)
        self._refresh()

    def _accent(self, col: str) -> None:
        self.ctx.cfg["custom_accent"] = "" if col.upper() == ACCENT_DEFAULT.upper() else col
        self.ctx.refresh_accent()


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


class LauncherPage(Page):
    key = "launch"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        lay = vbox(self, 8)
        apps = ctx.apps()
        self.tiles = []
        if not apps:
            lay.addSpacing(S(16))
            lay.addWidget(Glyph("grid", 52), 0, Qt.AlignmentFlag.AlignHCenter)
            lay.addWidget(Label(tr("No apps found"), 12.5, TEXT_DIM, align=Qt.AlignmentFlag.AlignHCenter))
            lay.addSpacing(S(8))
        else:
            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(S(4))
            for i, app in enumerate(apps):
                tile = AppTile(app)
                tile.clicked.connect(lambda _=False, t=tile: self._click(t))
                grid.addWidget(tile, i // 4, i % 4)
                self.tiles.append(tile)
            for c in range(4):
                grid.setColumnStretch(c, 1)
            lay.addLayout(grid)
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

    def _rescan(self) -> None:
        self.ctx.apps(force=True)
        self.ctx.reload_page()

    def _click(self, tile: AppTile) -> None:
        app = tile.app
        if tile.running:
            def close(t=tile) -> None:
                if extras.close_app(t.app["exe"]):
                    t.set_running(False)
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
        reset = Button(tr("Turn off all swaps"), "danger", 34)
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
            desired.pop(key)                       # off: the original comes back
        else:
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
        if self._shown():
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
    """What changed in this version."""
    key = "new"

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        lay = vbox(self, 6)
        lay.addWidget(Label(tr("What's new"), 16, bold=True))
        for version, groups in extras.NEWS:
            if version:
                lay.addWidget(Label(tr("Version {v}", v=version), 11.5, TEXT_DIM))
            else:
                lay.addSpacing(S(10))
                lay.addWidget(Label(tr("Earlier"), 14, bold=True))
            for title, lines in groups:
                lay.addSpacing(S(4))
                lay.addWidget(heading(tr(title)))
                for text in lines:
                    line = hbox(spacing=8)
                    dot = Label("•", 12.5, TEXT_FAINT)
                    dot.setFixedWidth(S(8))
                    line.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
                    line.addWidget(Label(tr(text), 12.5, TEXT, wrap_w=self.W - S(18)))
                    line.addStretch(1)
                    lay.addLayout(line)


PAGES = {"home": HomePage, "lyrics": LyricsPage, "crosshair": CrosshairPage, "display": DisplayPage,
         "perf": PerfPage, "tools": ToolsPage, "timer": TimersPage, "launch": LauncherPage, "themes": ThemesPage,
         "rl": RocketPage, "new": NewsPage, "settings": SettingsPage}
# Fixed order: music first, then what you use in a game, then tools, then the look, settings last.
TABS = [("home", "home", "Home"), ("lyrics", "lyrics", "Lyrics"), ("crosshair", "crosshair", "Crosshair"),
        ("display", "display", "Display"), ("rl", "rocket", "RL SWAP"), ("launch", "grid", "Apps"),
        ("perf", "perf", "Stats"), ("timer", "timer", "Timer"), ("tools", "tools", "Tools"),
        ("themes", "gem", "Themes"), ("new", "spark", "New"), ("settings", "cog", "Settings")]


TEMP_TABS: set = set()      # tabs shown only until the user leaves them


def visible_tabs(cfg) -> list:
    """The tabs the user keeps in the menu bar (Home, Lyrics and Settings cannot be hidden)."""
    off = cfg["tabs_off"] if isinstance(cfg["tabs_off"], dict) else {}

    def shown(key: str) -> bool:
        if key in LOCKED_TABS or key in TEMP_TABS:
            return True
        if key == "new":                        # off by default; shows by itself after an update
            return bool(cfg["news_tab"])
        return not off.get(key)
    return [t for t in TABS if shown(t[0])]


def make_page(ctx, key: str) -> Page:
    return PAGES[key](ctx)


# ==================================================================================================
# SECTION: window
# ==================================================================================================
import time

from PyQt6.QtCore import QEasingCurve, QPoint, QPointF, QRect, QRectF, QTimer, Qt
from PyQt6.QtGui import (QCursor, QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                         QRadialGradient, QRegion)
from PyQt6.QtWidgets import QFileDialog, QWidget

import math


HEADER_TOP, HEADER_H, TAB_H = 12, 26, 30
CHROME_TOP = HEADER_TOP + HEADER_H + 8 + TAB_H + 10
CHROME_BOTTOM = 14
COMPACT = TAB_H + 10           # the tab row squashes away; the title and the R button stay
MUSIC_PAGES = ("home", "lyrics")
MAX_CONTENT = 540
MIN_CARD = 250
BAND = 120                 # themes decorate only this top part of the card
WINDOW_FLAGS = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
                | Qt.WindowType.NoDropShadowWindowHint
                | Qt.WindowType.WindowDoesNotAcceptFocus)      # clicking never steals focus from a game


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


# --------------------------------------------------------------------------- #
# Shared painting
# --------------------------------------------------------------------------- #
_tiles: dict = {}


def _glow_tile(radius: int, dpr: float):
    """Pre-rendered glow for a rounded square of `radius`, in physical pixels: (pixmap, cap px)."""
    key = (radius, round(dpr * 100), ui.accent.rgb(), S(GLOW))
    hit = _tiles.get(key)
    if hit is None:
        if len(_tiles) > 48:
            _tiles.clear()
        g = S(GLOW)
        cap = int(round((radius + g) * dpr))
        mid = 4
        pm = QPixmap(2 * cap + mid, 2 * cap + mid)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(dpr, dpr)
        inner = 2 * radius + mid / dpr
        rect = QRectF(g, g, inner, inner)
        layers, reach = 16, g - 1.0                 # many faint rings: bright at the edge, fading to nothing
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(layers, 0, -1):
            a = 0.013 + 0.062 * ((layers - i) / layers) ** 2
            pen = QPen(alpha(ui.accent, a), 2.0 * reach * i / layers)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawRoundedRect(rect, radius, radius)
        p.end()
        hit = _tiles[key] = (pm, cap, mid)
    return hit


def draw_glow(p: QPainter, shape: QRectF, radius: float, level: float, dpr: float) -> None:
    """Nine-slice the cached glow around `shape`."""
    r = int(max(2, round(min(radius, shape.width() / 2, shape.height() / 2))))
    pm, cap, mid = _glow_tile(r, dpr)
    g = S(GLOW)
    c = cap / dpr                                   # corner size in logical pixels
    x0, y0 = shape.left() - g, shape.top() - g
    w, h = shape.width() + 2 * g, shape.height() + 2 * g
    mw, mh = max(0.0, w - 2 * c), max(0.0, h - 2 * c)
    xs = [(x0, c, 0, cap), (x0 + c, mw, cap, mid), (x0 + c + mw, c, cap + mid, cap)]
    ys = [(y0, c, 0, cap), (y0 + c, mh, cap, mid), (y0 + c + mh, c, cap + mid, cap)]
    old = p.opacity()
    p.setOpacity(old * max(0.0, min(1.0, level)))
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    for ty, th, sy, sh in ys:
        for tx, tw, sx, sw in xs:
            if tw > 0.01 and th > 0.01 and not (sx == cap and sy == cap):
                p.drawPixmap(QRectF(tx, ty, tw, th), pm, QRectF(sx, sy, sw, sh))
    p.setOpacity(old)


def paint_shape(p: QPainter, ctx, shape: QRectF, radius: float, level: float, dpr: float) -> QPainterPath:
    """Glow + dark glass body. Returns the body path (for clipping content)."""
    if ctx.cfg["halo"]:
        power = GLOW_POWER[ctx.cfg["glow_power"] if 0 <= ctx.cfg["glow_power"] < 3 else 1]
        power = max(1.0, power)                             # two strengths: normal and strong
        draw_glow(p, shape, radius, level * min(1.0, power), dpr)
        if power > 1.0:
            draw_glow(p, shape, radius, level * (power - 1.0), dpr)
        extra = ctx.theme().get("glow", 1.0) - 1.0          # richer themes get a stronger halo
        if extra > 0.01:
            draw_glow(p, shape, radius, level * extra, dpr)
    path = QPainterPath()
    path.addRoundedRect(shape, radius, radius)
    grad = QLinearGradient(shape.topLeft(), shape.bottomLeft())
    grad.setColorAt(0.0, ui.bg_top)
    grad.setColorAt(1.0, ui.bg_bottom)
    p.fillPath(path, grad)
    tint = QLinearGradient(shape.topLeft(), QPointF(shape.left(), shape.top() + min(shape.height(), S(110))))
    tint.setColorAt(0.0, alpha(ui.accent, 0.08))
    tint.setColorAt(1.0, alpha(ui.accent, 0.0))
    p.fillPath(path, tint)
    return path


def paint_edge(p: QPainter, ctx, shape: QRectF, radius: float, level: float) -> None:
    extras.paint_theme_edge(p, ctx.theme(), shape, radius, level, ctx.cfg["halo"], time.monotonic())


def paint_ball_face(p: QPainter, ctx, shape: QRectF, opacity: float) -> None:
    p.save()
    p.setOpacity(p.opacity() * opacity)
    d = min(shape.width(), shape.height())
    c = QPointF(shape.left() + d / 2, shape.top() + d / 2)
    st = ctx.state
    if ctx.cfg["ring"] and st.has_track and st.duration_ms > 0:
        frac = max(0.0, min(1.0, ctx.position_ms() / st.duration_ms))
        ring = QRectF(c.x() - d / 2, c.y() - d / 2, d, d).adjusted(S(5), S(5), -S(5), -S(5))
        style = ctx.ring_style()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(extras.ring_pen(style, alpha("#FFFFFF", 0.10), S(2.2)))
        p.drawEllipse(ring)
        p.setPen(extras.ring_pen(style, ui.accent, S(2.2)))
        p.drawArc(ring, 90 * 16, int(-360 * 16 * frac))
    box = QRectF(c.x() - d / 2, c.y() - d / 2 - d * 0.02, d, d)
    extras.paint_r(p, box, d, ctx.ball_style(), ui.accent, time.monotonic())
    if ctx.overlay_active():
        p.setPen(QPen(ui.bg_top, S(1.5)))
        p.setBrush(ui.accent)
        p.drawEllipse(QPointF(c.x() + d * 0.33, c.y() - d * 0.33), S(4), S(4))
    p.restore()


def work_area(point: QPoint) -> QRect:
    screen = QGuiApplication.screenAt(point) or QGuiApplication.primaryScreen()
    return screen.availableGeometry()


# --------------------------------------------------------------------------- #
# The ball
# --------------------------------------------------------------------------- #
class BallWindow(QWidget):
    def __init__(self, owner: "MainWindow") -> None:
        super().__init__()
        self.owner, self.ctx = owner, owner.ctx
        self.setWindowTitle("Rubenium")
        self.setWindowFlags(WINDOW_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.center = QPoint(200, 200)
        self.hover = Tween(self, 0.0, self.update, QEasingCurve.Type.OutBack)
        self.press = Tween(self, 0.0, self.update)
        self.appear = Tween(self, 0.0, self.update, QEasingCurve.Type.OutBack)
        self._glide = Tween(self, 1.0, self._on_glide, QEasingCurve.Type.InOutCubic)
        self._glide.finished.connect(self._glide_done)
        self._then = None
        self._from, self._to = QPoint(), QPoint()
        self._press_pos = None
        self._moved = False

    # -- geometry
    def rect_global(self) -> QRect:
        d = BD()
        return QRect(self.center.x() - d // 2, self.center.y() - d // 2, d, d)

    def place(self) -> None:
        g = S(GLOW)
        self.setGeometry(self.rect_global().adjusted(-g, -g, g, g))

    def set_center(self, c: QPoint) -> None:
        self.center = QPoint(c)
        self.place()

    def clamp(self) -> None:
        wa = work_area(self.center)
        r = BD() // 2 + S(6)
        self.center = QPoint(max(wa.left() + r, min(wa.right() - r, self.center.x())),
                             max(wa.top() + r, min(wa.bottom() - r, self.center.y())))

    @staticmethod
    def corner_point(wa: QRect, left: bool, top: bool) -> QPoint:
        m = S(14) + BD() // 2
        return QPoint(wa.left() + m if left else wa.right() - m, wa.top() + m if top else wa.bottom() - m)

    def nearest_corner(self, point: QPoint) -> QPoint:
        wa = work_area(point)
        return self.corner_point(wa, point.x() < wa.center().x(), point.y() < wa.center().y())

    # -- glide (the window only moves: nothing is repainted, so it is perfectly smooth)
    @property
    def gliding(self) -> bool:
        return self._glide.busy

    def _glide_done(self) -> None:
        then, self._then = self._then, None
        if then is not None:
            then()
        else:
            self.owner.save_position()

    def glide_to(self, target: QPoint, then=None, fast: bool = False) -> None:
        self._from, self._to = QPoint(self.center), QPoint(target)
        self._then = then
        dist = (target - self.center).manhattanLength()
        if dist < 3:
            self.set_center(target)
            self._glide_done()
            return
        self._glide.jump(0.0)
        self._glide.to(1.0, int(min(300, 150 + dist * 0.18)) if fast else int(min(520, 260 + dist * 0.35)))

    def _on_glide(self) -> None:
        t = self._glide.level
        ex, ey = t ** 0.7, t ** 1.6                         # x leads, y follows: a soft curve into the corner
        dx, dy = self._to.x() - self._from.x(), self._to.y() - self._from.y()
        if abs(dy) > abs(dx):
            ex, ey = ey, ex
        self.set_center(QPoint(round(self._from.x() + dx * ex), round(self._from.y() + dy * ey)))

    # -- painting
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        a = self.appear.level
        if a < 1.0:
            p.setOpacity(max(0.0, min(1.0, a)))
        k = (0.6 + 0.4 * min(1.15, a)) * (1 + 0.07 * self.hover.level - 0.06 * self.press.level)
        g, d = S(GLOW), BD()
        w = d * k
        shape = QRectF(g + d / 2 - w / 2, g + d / 2 - w / 2, w, w)
        level = self.ctx.glow_level(max(0.0, self.hover.level))
        paint_shape(p, self.ctx, shape, w / 2, level, self.devicePixelRatioF())
        paint_ball_face(p, self.ctx, shape, 1.0)
        paint_edge(p, self.ctx, shape, w / 2, level)

    # -- mouse: click opens, drag moves (kept on screen)
    def enterEvent(self, e) -> None:
        self.hover.to(1.0, 260)

    def leaveEvent(self, e) -> None:
        self.hover.to(0.0, 320)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton and not self.gliding:
            self._press_pos = e.globalPosition().toPoint()
            self._origin = QPoint(self.center)
            self._moved = False
            self.press.to(1.0, 80)

    def mouseMoveEvent(self, e) -> None:
        if self._press_pos is None:
            return
        pos = e.globalPosition().toPoint()
        if not self._moved and (pos - self._press_pos).manhattanLength() >= 5:
            self._moved = True
        if self._moved:
            self.center = self._origin + (pos - self._press_pos)      # stored origin + total delta: no drift
            self.clamp()
            self.place()

    def mouseReleaseEvent(self, e) -> None:
        if self._press_pos is None:
            return
        self._press_pos = None
        self.press.to(0.0, 200)
        if self._moved:
            self.owner.save_position()
        else:
            self.owner.expand()


class Toast(QWidget):
    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._text, self._kind = "", "ok"
        self._fade = Tween(self, 0.0, self._changed)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self._fade.to(0.0, 260))
        self.hide()

    def _changed(self) -> None:
        if self._fade.level <= 0.001 and self._fade.target == 0.0:
            self.hide()
        self.update()

    def show_text(self, text: str, kind: str, card: QRectF) -> None:
        self._text, self._kind = text, kind
        from PyQt6.QtGui import QFontMetrics
        fm = QFontMetrics(font(11.5, QFont.Weight.DemiBold))
        max_w = int(card.width() - S(28))
        br = fm.boundingRect(0, 0, max_w - S(34), 1000, int(Qt.TextFlag.TextWordWrap), text)
        w, h = min(max_w, br.width() + S(38)), br.height() + S(16)
        self.setGeometry(int(card.center().x() - w / 2), int(card.bottom() - h - S(12)), int(w), int(h))
        self.show()
        self.raise_()
        self._fade.to(1.0, 180)
        self._timer.start(2400 + 30 * len(text))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._fade.level
        p.setOpacity(t)
        p.translate(0, (1 - t) * S(8))
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        col = {"ok": ui.accent, "warn": QColor(WARN), "error": QColor(DANGER)}.get(self._kind, ui.accent)
        p.setPen(QPen(alpha(col, 0.55), 1))
        p.setBrush(QColor(22, 27, 28, 250))
        p.drawRoundedRect(r, S(10), S(10))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawEllipse(QPointF(S(14), r.center().y()), S(3.5), S(3.5))
        p.setPen(QColor(TEXT))
        p.setFont(font(11.5, QFont.Weight.DemiBold))
        p.drawText(r.adjusted(S(26), 0, -S(8), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap), self._text)


class Confirm(QWidget):
    """A short question with Yes / No, shown on the card itself."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self._text = ""
        self._yes_cb = None
        self._yes = Button(tr("Yes"), "primary", 28, parent=self)
        self._no = Button(tr("No"), "ghost", 28, parent=self)
        self._no_cb = None
        self._yes.clicked.connect(self._accept)
        self._no.clicked.connect(self._decline)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self._rise = Tween(self, 1.0, self.update)
        self.hide()

    def ask(self, text: str, on_yes, card: QRectF, yes: str = "", no: str = "", persistent: bool = False,
            on_no=None) -> None:
        again = self.isVisible() and persistent
        self._text, self._yes_cb, self._no_cb = text, on_yes, on_no
        self._yes.set_text(yes or tr("Yes"))
        self._no.set_text(no or tr("No"))
        w, h = int(card.width() - S(28)), S(46)
        self.setGeometry(int(card.left() + S(14)), int(card.bottom() - h - S(12)), w, h)
        yw = max(S(58), self._yes.sizeHint().width())
        nw = max(S(58), self._no.sizeHint().width())
        self._no.setGeometry(w - nw - S(9), S(9), nw, S(28))
        self._yes.setGeometry(w - nw - yw - S(15), S(9), yw, S(28))
        self.show()
        self.raise_()
        if not again:
            self._rise.jump(0.0)
            self._rise.to(1.0, 180)
        self.update()
        if persistent:
            self._timer.stop()                  # stays until the user answers
        else:
            self._timer.start(7000)

    def _accept(self) -> None:
        cb, self._yes_cb, self._no_cb = self._yes_cb, None, None
        self.hide()
        if cb:
            cb()

    def _decline(self) -> None:
        cb, self._yes_cb, self._no_cb = self._no_cb, None, None
        self.hide()
        if cb:
            cb()

    def mousePressEvent(self, e) -> None:
        e.accept()                      # never drags the card

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(self._rise.level)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha(WARN, 0.6), 1))
        p.setBrush(QColor(22, 27, 28, 252))
        p.drawRoundedRect(r, S(10), S(10))
        p.setPen(QColor(TEXT))
        p.setFont(font(12, QFont.Weight.DemiBold))
        room = self._yes.x() - S(20)
        text = p.fontMetrics().elidedText(self._text, Qt.TextElideMode.ElideRight, room)
        p.drawText(QRectF(S(12), 0, room, self.height()), int(Qt.AlignmentFlag.AlignVCenter), text)


class Busy(QWidget):
    """A short loading screen over the card: fades in, spins, fades out. Blocks clicks while it shows."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self._text = ""
        self._fade = Tween(self, 0.0, self._faded)
        self._spin = QTimer(self)
        self._spin.setInterval(16)
        self._spin.timeout.connect(self.update)
        self._since = 0.0
        self._then = None
        self.hide()

    def start(self, text: str, card: QRectF) -> None:
        self._text = text
        self.setGeometry(card.toAlignedRect())
        if not self.isVisible() or self._fade.target < 0.5:
            self._since = time.monotonic()
            self.show()
            self.raise_()
            self._fade.to(1.0, 180)
            self._spin.start()
        self.update()

    def finish(self, then=None) -> None:
        if not self.isVisible():
            if then:
                then()
            return
        self._then = then
        wait = max(0, int((0.7 - (time.monotonic() - self._since)) * 1000))   # never just a flash
        QTimer.singleShot(wait, lambda: self._fade.to(0.0, 240))

    def _faded(self) -> None:
        if self._fade.level <= 0.001 and self._fade.target == 0.0:
            self._spin.stop()
            self.hide()
            then, self._then = self._then, None
            if then:
                then()
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()

    def wheelEvent(self, e) -> None:
        e.accept()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._fade.level
        r = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(r, S(ui.radius), S(ui.radius))
        p.fillPath(path, QColor(ui.bg_top.red(), ui.bg_top.green(), ui.bg_top.blue(), int(232 * t)))
        p.setOpacity(t)
        c = QPointF(r.center().x(), r.center().y() - S(10))
        rad = S(15)
        pen = QPen(alpha("#FFFFFF", 0.12), S(3))
        p.setPen(pen)
        p.drawEllipse(c, rad, rad)
        pen = QPen(ui.accent, S(3))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        start = int((time.monotonic() * 360) % 360)
        p.drawArc(QRectF(c.x() - rad, c.y() - rad, 2 * rad, 2 * rad), -start * 16, 100 * 16)
        p.setPen(QColor(TEXT))
        p.setFont(font(12.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(r.left(), c.y() + rad + S(10), r.width(), S(22)), int(Qt.AlignmentFlag.AlignCenter), self._text)


class PreviewDrawer(QWidget):
    """A small black panel that slides out beside the card to preview a locked theme."""

    def __init__(self, owner: "MainWindow") -> None:
        super().__init__()
        self.owner, self.ctx = owner, owner.ctx
        self.setWindowFlags(WINDOW_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.theme = extras.THEMES[0]
        self._side = 1                                   # 1 = right of the card, -1 = left
        self._slide = Tween(self, 0.0, self._moved, QEasingCurve.Type.OutCubic)
        self._close = Button(tr("Close"), "ghost", 28, parent=self)
        self._close.clicked.connect(self.close_drawer)
        self._frame = QTimer(self)
        self._frame.setInterval(33)
        self._frame.timeout.connect(self.update)
        self._auto = QTimer(self)
        self._auto.setSingleShot(True)
        self._auto.timeout.connect(self.close_drawer)
        self._sparks: list = []

    def is_open(self) -> bool:
        return self.isVisible() and self._slide.target > 0.5

    def open_for(self, theme: dict) -> None:
        self.theme = theme
        w, h, gap = S(214), S(252), S(6)
        card = self.owner.card_global()
        wa = work_area(card.center())
        self._side = 1 if card.right() + gap + w <= wa.right() else -1
        x = card.right() + gap if self._side == 1 else card.left() - gap - w
        y = max(wa.top() + S(8), min(card.top() + S(70), wa.bottom() - h - S(8)))
        self.setGeometry(x, y, w, h)
        tile = self._tile()
        self._sparks = extras.theme_sparkles(theme, tile.width(), tile.height())
        self._close.setFixedSize(w - S(28), S(28))
        self._slide.jump(0.0)
        self._slide.target = 1.0
        self.ctx.preview_theme(theme["id"])
        self.show()
        self._slide.to(1.0, 260)
        self._frame.start()
        self._auto.start(15000)

    def close_drawer(self) -> None:
        if self.isVisible() and self._slide.target != 0.0:
            self._auto.stop()
            self._slide.to(0.0, 200)
            self.ctx.preview_theme("")

    def close_now(self) -> None:
        if self.isVisible():
            self._slide.jump(0.0)

    def _offset(self) -> float:
        return -self._side * self.width() * (1.0 - self._slide.level)

    def _tile(self) -> QRectF:
        return QRectF(S(14), S(38), self.width() - S(28), S(104))

    def _moved(self) -> None:
        if self._slide.level <= 0.001 and self._slide.target == 0.0:
            self._frame.stop()
            self._auto.stop()
            self.hide()
            if self.ctx._preview:
                self.ctx.preview_theme("")
            return
        self._close.move(int(S(14) + self._offset()), self.height() - S(40))
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(self._offset(), 0)
        th, now = self.theme, time.monotonic()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha("#FFFFFF", 0.12), 1))
        p.setBrush(QColor(6, 8, 9))
        p.drawRoundedRect(r, S(14), S(14))
        p.setPen(QColor(TEXT))
        p.setFont(font(10, QFont.Weight.Bold, 2.2))
        p.drawText(QRectF(S(15), S(11), 150, S(18)), int(Qt.AlignmentFlag.AlignVCenter), tr("PREVIEW"))
        p.save()
        p.translate(self.width() - S(24), S(20))
        p.scale(S(13) / 20, S(13) / 20)
        draw_icon(p, "lock", QColor(TEXT_DIM))
        p.restore()

        tile = self._tile()
        rad = S(10)
        path = QPainterPath()
        path.addRoundedRect(tile, rad, rad)
        g = QLinearGradient(tile.topLeft(), tile.bottomLeft())
        g.setColorAt(0, ui.bg_top)
        g.setColorAt(1, ui.bg_bottom)
        p.fillPath(path, g)
        p.save()
        p.setClipPath(path)
        pm = extras.theme_pattern(th, int(tile.width()), int(tile.height()), ui.accent, self.devicePixelRatioF(),
                                  ui.scale * 0.62)
        if pm is not None:
            p.drawPixmap(tile.topLeft(), pm)
        extras.paint_sparkles(p, self._sparks, tile.left(), tile.top(), ui.accent, now, ui.scale * 0.8)
        p.restore()
        level = 0.75 + 0.25 * math.sin(now * 2.1)
        extras.paint_theme_edge(p, th, tile, rad, level, True, now)

        p.setPen(QColor(TEXT))
        p.setFont(font(15, QFont.Weight.Bold))
        p.drawText(QRectF(S(15), tile.bottom() + S(9), self.width() - S(30), S(22)),
                   int(Qt.AlignmentFlag.AlignVCenter), tr(th["name"]))
        have, need = self.ctx.usage_hours(), th["hours"]
        bar = QRectF(S(15), tile.bottom() + S(38), self.width() - S(30), S(4))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.12))
        p.drawRoundedRect(bar, 2, 2)
        p.setBrush(ui.accent)
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), max(S(4), bar.width() * min(1.0, have / max(1, need))), bar.height()), 2, 2)
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(S(15), bar.bottom() + S(5), self.width() - S(30), S(16)),
                   int(Qt.AlignmentFlag.AlignVCenter), f"{int(have)} / {need} h")


class Welcome(QWidget):
    """The start-up screen: a welcome card with one Launch button. Launch folds the card into a round R,
    a ring loads around it, then it flies to where the ball lives and becomes the ball."""
    CW, CH, BIG = 440, 250, 92

    def __init__(self, ctx, on_done) -> None:
        super().__init__()
        self.ctx, self._on_done = ctx, on_done
        self.setWindowTitle("Rubenium")
        self.setWindowFlags(WINDOW_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.phase = "card"                      # card -> fold -> ring -> fly -> done
        self.appear = Tween(self, 0.0, self.update, QEasingCurve.Type.OutCubic)
        self.fold = Tween(self, 0.0, self.update, QEasingCurve.Type.InOutCubic)
        self.ring = Tween(self, 0.0, self.update, QEasingCurve.Type.InOutCubic)
        self.fly = Tween(self, 0.0, self._on_fly, QEasingCurve.Type.InOutCubic)
        self.hover = Tween(self, 0.0, self.update)
        self.press = Tween(self, 0.0, self.update)
        self.fold.finished.connect(self._folded)
        self.ring.finished.connect(self._loaded)
        self.fly.finished.connect(self._landed)
        self._down = False
        self._from = self._to = QPoint()
        self._clock = QTimer(self)
        self._clock.setTimerType(Qt.TimerType.PreciseTimer)
        self._clock.setInterval(16)
        self._clock.timeout.connect(self.update)

    def start(self) -> None:
        ball = self.ctx.window.ball
        wa = work_area(ball.center)
        m = S(GLOW) + S(14)
        w, h = S(self.CW) + 2 * m, S(self.CH) + 2 * m
        self.setGeometry(wa.center().x() - w // 2, wa.center().y() - h // 2, w, h)
        self.show()
        self.appear.to(1.0, 420)
        self._clock.start()

    # -- geometry
    def _button(self) -> QRectF:
        bw, bh = S(176), S(44)
        return QRectF(self.width() / 2 - bw / 2, self.height() / 2 + S(self.CH) * 0.24, bw, bh)

    def _circle_d(self) -> float:
        f = self.fly.level if self.phase in ("fly", "done") else 0.0
        return lerp(float(S(self.BIG)), float(BD()), f)

    # -- the sequence
    def launch(self) -> None:
        if self.phase != "card":
            return
        self.phase = "fold"
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.hover.to(0.0, 120)
        self.fold.to(1.0, 520)

    def _folded(self) -> None:
        if self.phase == "fold":
            self.phase = "ring"
            self.ring.to(1.0, 640)

    def _loaded(self) -> None:
        if self.phase != "ring":
            return
        self.phase = "fly"
        self._from = self.geometry().center()
        self._to = QPoint(self.ctx.window.ball.center)
        dist = (self._to - self._from).manhattanLength()
        self.fly.to(1.0, int(max(480, min(760, 380 + dist * 0.22))))

    def _on_fly(self) -> None:
        if self.phase == "fly":
            f = self.fly.level
            c = QPoint(round(lerp(self._from.x(), self._to.x(), f)), round(lerp(self._from.y(), self._to.y(), f)))
            self.move(c.x() - self.width() // 2, c.y() - self.height() // 2)
        self.update()

    def _landed(self) -> None:
        if self.phase != "fly":
            return
        self.phase = "done"
        self._clock.stop()
        ball = self.ctx.window.ball
        ball.appear.jump(1.0)
        ball.place()
        ball.show()
        ball.repaint()                             # the real ball is drawn before this window goes away
        self.hide()
        done, self._on_done = self._on_done, None
        if done is not None:
            done()
        self.deleteLater()

    # -- mouse: only the Launch button does anything
    def mouseMoveEvent(self, e) -> None:
        over = self.phase == "card" and self._button().contains(e.position())
        self.setCursor(Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.ArrowCursor)
        self.hover.to(1.0 if over else 0.0, 140)

    def leaveEvent(self, _e) -> None:
        self.hover.to(0.0, 200)

    def mousePressEvent(self, e) -> None:
        if (self.phase == "card" and e.button() == Qt.MouseButton.LeftButton
                and self._button().contains(e.position())):
            self._down = True
            self.press.to(1.0, 80)

    def mouseReleaseEvent(self, e) -> None:
        if self._down:
            self._down = False
            self.press.to(0.0, 160)
            if self._button().contains(e.position()):
                self.launch()

    def closeEvent(self, e) -> None:
        if self.phase != "done":
            e.ignore()                             # there is no way to close it: Launch is the way in

    # -- painting
    def paintEvent(self, _e) -> None:
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        a = max(0.0, min(1.0, self.appear.level))
        m = max(0.0, min(1.0, self.fold.level))
        f = max(0.0, min(1.0, self.fly.level)) if self.phase in ("fly", "done") else 0.0
        d = self._circle_d()
        if self.phase == "fly":
            d *= 1.0 + 0.14 * math.sin(math.pi * min(1.0, f / 0.4))        # a soft pop as it takes off
        k = 0.94 + 0.06 * a
        w, h = lerp(S(self.CW) * k, d, m), lerp(S(self.CH) * k, d, m)
        cx, cy = self.width() // 2, self.height() // 2
        shape = QRectF(cx - w / 2, cy - h / 2, w, h)
        radius = lerp(float(S(24)), d / 2, m)
        p.setOpacity(a)
        level = lerp(max(0.72, self.ctx.glow_level()), self.ctx.glow_level(), f)
        path = paint_shape(p, self.ctx, shape, radius, level, self.devicePixelRatioF())

        show = max(0.0, 1.0 - m / 0.45)                    # the card's content leaves first
        if show > 0.0:
            p.save()
            p.setClipPath(path)
            p.setOpacity(a * show)
            other = QColor.fromHsvF((max(0.0, ui.accent.hsvHueF()) + 0.17) % 1.0,
                                    min(1.0, ui.accent.hsvSaturationF() * 0.9 + 0.1), 1.0)
            spots = ((ui.accent, 0.34, 0.28 + 0.20 * math.sin(now * 0.55), 0.20 + 0.22 * math.cos(now * 0.43), 0.62),
                     (other, 0.24, 0.76 + 0.16 * math.cos(now * 0.37), 0.84 + 0.14 * math.sin(now * 0.61), 0.55),
                     (ui.accent, 0.16, 0.55 + 0.30 * math.sin(now * 0.29 + 2.0), 0.55 + 0.25 * math.cos(now * 0.33), 0.40))
            for col, strength, fx, fy, size in spots:    # slow drifting lights
                c = QPointF(shape.left() + w * fx, shape.top() + h * fy)
                g = QRadialGradient(c, w * size)
                g.setColorAt(0.0, alpha(col, strength))
                g.setColorAt(1.0, alpha(col, 0.0))
                p.fillRect(shape, g)
            sweep = (now * 0.16) % 1.6 - 0.3               # a faint band of light crossing now and then
            band = QLinearGradient(QPointF(shape.left() + w * (sweep - 0.18), shape.top()),
                                   QPointF(shape.left() + w * (sweep + 0.18), shape.bottom()))
            band.setColorAt(0.0, alpha("#FFFFFF", 0.0))
            band.setColorAt(0.5, alpha("#FFFFFF", 0.05))
            band.setColorAt(1.0, alpha("#FFFFFF", 0.0))
            p.fillRect(shape, band)

            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(14, QFont.Weight.DemiBold, 0.3))
            p.drawText(QRectF(shape.left(), cy - S(self.CH) * 0.36, w, S(22)), int(Qt.AlignmentFlag.AlignCenter),
                       tr("Welcome to"))
            p.setFont(font(42, QFont.Weight.ExtraBold, 0.5))
            fm = p.fontMetrics()
            word = "Rubenium"
            full = fm.horizontalAdvance(word)
            x0 = cx - full / 2
            split = x0 + full - fm.horizontalAdvance("ium")
            line = QRectF(x0, cy - S(self.CH) * 0.25, full + S(4), S(56))
            p.save()
            p.setClipRect(QRectF(0, 0, split, self.height()), Qt.ClipOperation.IntersectClip)
            p.setPen(QColor(TEXT))
            p.drawText(line, int(Qt.AlignmentFlag.AlignVCenter), word)
            p.restore()
            p.save()
            p.setClipRect(QRectF(split, 0, self.width(), self.height()), Qt.ClipOperation.IntersectClip)
            p.setPen(ui.accent)
            p.drawText(line, int(Qt.AlignmentFlag.AlignVCenter), word)
            p.restore()

            b = self._button()
            hv, pr = self.hover.level, self.press.level
            grow = S(2) * hv - S(1.5) * pr
            b = b.adjusted(-grow, -grow * 0.5, grow, grow * 0.5)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha(ui.accent, 0.22 + 0.10 * hv))
            p.drawRoundedRect(b.adjusted(-S(3), -S(3), S(3), S(3)), S(16), S(16))
            p.setBrush(mix(ui.accent, QColor("#FFFFFF"), 0.10 * hv))
            p.drawRoundedRect(b, S(13), S(13))
            p.setPen(QColor("#06110A" if ui.accent.lightnessF() > 0.6 else "#FFFFFF"))
            p.setFont(font(15, QFont.Weight.Bold, 0.3))
            p.drawText(b, int(Qt.AlignmentFlag.AlignCenter), tr("Launch"))
            p.restore()

        face = max(0.0, min(1.0, (m - 0.5) / 0.5))         # the R arrives as the circle forms
        if face > 0.0:
            p.setOpacity(a * face)
            c = QPointF(cx, cy)
            box = QRectF(c.x() - d / 2, c.y() - d / 2 - d * 0.02, d, d)
            extras.paint_r(p, box, d, self.ctx.ball_style(), ui.accent, now)
            turn = max(0.0, min(1.0, self.ring.level))
            if self.phase in ("ring", "fly") and turn > 0.0:
                inset = d * 0.09
                ring = QRectF(c.x() - d / 2 + inset, c.y() - d / 2 + inset, d - 2 * inset, d - 2 * inset)
                pen = QPen(alpha("#FFFFFF", 0.10 * (1.0 - f)), max(1.5, d * 0.04))
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.setPen(pen)
                p.drawEllipse(ring)
                pen.setColor(alpha(ui.accent, 1.0 - f))
                p.setPen(pen)
                p.drawArc(ring, 90 * 16, int(-360 * 16 * turn))
        p.setOpacity(a)
        paint_edge(p, self.ctx, shape, radius, level)


class Body(QWidget):
    """Card chrome: wordmark, status dots, the R button (back to the ball), tab bar and the page host."""

    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self.win = window
        self.to_ball = IconButton("rball", 28, tip=tr("Close to the ball"), parent=self)
        self.tabbar = None
        self.host = QWidget(self)
        self.set_tabs()
        self.to_ball.clicked.connect(window.collapse)
        self._press = None
        self._moved = False

    def set_tabs(self) -> None:
        """(Re)build the tab row from the tabs the user keeps switched on."""
        old = self.tabbar
        tabs = [(k, icon, tr(label), False) for k, icon, label in visible_tabs(self.win.ctx.cfg)]
        self.tabbar = TabBar(tabs, self.win.current, self)
        self.tabbar.changed.connect(self.win.goto)
        if old is not None:
            old.hide()
            old.deleteLater()
            self.tabbar.show()
            self.resizeEvent(None)

    def offset(self) -> int:
        return int(round((1.0 - self.win.chrome.level) * S(COMPACT)))

    def resizeEvent(self, _e) -> None:
        pad, w, off = S(PAD), self.width(), self.offset()
        level = self.win.chrome.level
        self.to_ball.move(w - pad - self.to_ball.width() + S(2),
                          S(HEADER_TOP) + (S(HEADER_H) - self.to_ball.height()) // 2)
        self.tabbar.setGeometry(pad, S(HEADER_TOP + HEADER_H + 8), w - 2 * pad, max(1, int(round(S(TAB_H) * level))))
        self.host.setGeometry(pad, S(CHROME_TOP) - off, w - 2 * pad + S(ScrollArea.GUTTER),
                              max(0, self.height() - S(CHROME_TOP + CHROME_BOTTOM) + off))
        self.tabbar.fade = max(0.0, min(1.0, (level - 0.2) / 0.8))     # squashes and fades together
        self.tabbar.setVisible(level > 0.04)                             # a hidden bar never catches a click
        self.tabbar.update()
        page = self.win.page()
        if page is not None and hasattr(page, "set_compact"):
            page.set_compact(level)
        for child in self.host.children():
            if isinstance(child, ScrollArea):
                child.setGeometry(self.host.rect())

    def header_rect(self) -> QRectF:
        return QRectF(0, 0, self.width(), S(HEADER_TOP + HEADER_H + 4))

    def dots_rect(self) -> QRect:
        return QRect(S(PAD), S(HEADER_TOP), S(220), S(HEADER_H))

    def paintEvent(self, _e) -> None:
        import math
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(font(18, QFont.Weight.ExtraBold, 0.4))
        fm = p.fontMetrics()
        x, base = S(PAD), QRectF(S(PAD), S(HEADER_TOP), self.width(), S(HEADER_H))
        # Drawn as ONE word so the letters keep their natural spacing; the colour changes by clipping.
        word = "Rubenium"
        full = fm.horizontalAdvance(word)
        split = x + full - fm.horizontalAdvance("ium")
        p.save()
        p.setClipRect(QRectF(0, 0, split, self.height()))
        p.setPen(QColor(TEXT))
        p.drawText(base, int(Qt.AlignmentFlag.AlignVCenter), word)
        p.setClipRect(QRectF(split, 0, self.width(), self.height()))
        p.setPen(ui.accent)
        p.drawText(base, int(Qt.AlignmentFlag.AlignVCenter), word)
        p.restore()
        x += full + S(9)
        st = self.win.ctx.state
        playing = st.status is Status.PLAYING
        live = st.status in (Status.PLAYING, Status.PAUSED)
        now = time.monotonic()
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(3):
            lift = math.sin(now * 5.0 - i * 0.9) * S(2.6) if playing else 0.0
            p.setBrush(alpha(ui.accent, 1.0 if playing else (0.6 if live else 0.25)))
            p.drawEllipse(QPointF(x + i * S(6), base.center().y() + S(4) - lift), S(1.7), S(1.7))

    # drag the card from anywhere that is not a control
    def mousePressEvent(self, e) -> None:
        self.win.show_chrome()
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.globalPosition().toPoint()
            self._moved = False
            self.win.begin_drag(self._press)

    def mouseMoveEvent(self, e) -> None:
        if self._press is None:
            return
        pos = e.globalPosition().toPoint()
        if not self._moved and (pos - self._press).manhattanLength() >= 4:
            self._moved = True
        if self._moved:
            self.win.drag_to(pos)

    def mouseReleaseEvent(self, e) -> None:
        self._press = None
        self.win.end_drag()


# --------------------------------------------------------------------------- #
# The card
# --------------------------------------------------------------------------- #
class MainWindow(QWidget):
    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        cfg = ctx.cfg
        self.current = cfg["page"] if cfg["page"] in self.tab_keys() else "home"
        self.expanded = False
        self.modal = False
        self.game_state = 0
        self.pages: dict = {}
        self._snap = None
        self._snap_old = self._snap_new = None
        self._dir = 1
        self._ball_l = QRectF()
        self._max_l = QRectF()               # largest card rect inside the canvas
        self._anchor_bottom = False
        self.card_pos = None                 # where the card lives on screen (global top-left)
        self._docked = None                  # where the ball was parked after the last collapse
        self._pending_home = None
        self._sparks: list = []
        self._fsnap = None
        self.card_max_h = S(400)
        self._drag_origin = None

        self.setWindowTitle("Rubenium")
        self.setWindowFlags(WINDOW_FLAGS)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowOpacity(cfg["opacity"] / 100)

        self.morph = Tween(self, 0.0, self._on_morph)
        self.pageh = Tween(self, float(S(240)), self._on_pageh)
        self.slide = Tween(self, 1.0, self._on_slide)
        self._accent_from, self._accent_to = QColor(ui.accent), QColor(ui.accent)
        self.accent_t = Tween(self, 1.0, self._on_accent)
        self.fade = Tween(self, 1.0, self._on_fade)
        self.chrome = Tween(self, 1.0, self._on_chrome, QEasingCurve.Type.InOutCubic)
        self._idle = QTimer(self)
        self._idle.setInterval(150)
        self._idle.timeout.connect(self._watch_idle)
        self._in_since = self._out_since = 0.0

        self.ball = BallWindow(self)
        self.ball.setWindowOpacity(cfg["opacity"] / 100)
        self.body = Body(self)
        self.body.hide()
        self.toast_w = Toast(self)
        self.confirm_w = Confirm(self)
        self.busy_w = Busy(self)
        self.drawer = PreviewDrawer(self)
        self._spark_timer = QTimer(self)
        self._spark_timer.setInterval(90)
        self._spark_timer.timeout.connect(self._twinkle)

        self._pulse = QTimer(self)
        self._pulse.setTimerType(Qt.TimerType.PreciseTimer)
        self._pulse.timeout.connect(self._tick)

    def tab_keys(self) -> list:
        return [t[0] for t in visible_tabs(self.ctx.cfg)]

    def tabs_changed(self) -> None:
        """A tab was switched on or off in Settings."""
        self.body.set_tabs()
        for key in list(self.pages):
            if key not in self.tab_keys() and key != self.current:
                self._drop_page(key)

    # ------------------------------------------------------------------ geometry
    def _place(self, ball: QRect, card_tl=None) -> None:
        """Lay the canvas out. With `card_tl` the card sits exactly there (kept on screen); without it the
        card opens at the ball. The card is always anchored by its top-left corner, so it never shuffles."""
        g, cw, m, d = S(GLOW), S(CARD_W), S(8), BD()
        if card_tl is None:
            wa = work_area(ball.center())
            x = ball.left() if ball.center().x() < wa.center().x() else ball.right() + 1 - cw
            y = ball.top()
        else:
            wa = work_area(card_tl + QPoint(cw // 2, S(40)))
            x, y = card_tl.x(), card_tl.y()
        x = max(wa.left() + m, min(x, wa.right() - cw - m))
        y = max(wa.top() + m, min(y, wa.bottom() - m - S(MIN_CARD)))
        room = wa.bottom() - m - y                              # low on the screen: tall pages scroll instead
        self.card_max_h = max(S(MIN_CARD), min(S(CHROME_TOP + CHROME_BOTTOM + MAX_CONTENT), int(wa.height() * 0.9), room))
        card_max = QRect(x, y, cw, self.card_max_h)
        if card_tl is not None:                                 # the ball starts inside the card's top strip
            bx = max(x, min(ball.left(), x + cw - d))
            ball = QRect(bx, y, d, d)
        canvas = card_max.united(ball).adjusted(-g, -g, g, g)
        self._anchor_bottom = False
        self._ball_l = QRectF(ball.translated(-canvas.topLeft()))
        self._max_l = QRectF(card_max.translated(-canvas.topLeft()))
        self.setGeometry(canvas)
        self.card_pos = QPoint(card_tl) if card_tl is not None else QPoint(x, y)   # where the user wants it
        self._save_card()
        self._sparks = extras.theme_sparkles(self.ctx.theme(), self._max_l.width(), self._max_l.height(), S(BAND))

    def _save_card(self) -> None:
        c = self.card_pos
        screen = QGuiApplication.screenAt(c + QPoint(S(CARD_W) // 2, S(40))) or QGuiApplication.primaryScreen()
        wa = screen.availableGeometry()
        new = {"screen": screen.name(), "nx": (c.x() - wa.left()) / max(1, wa.width()),
               "ny": (c.y() - wa.top()) / max(1, wa.height())}
        if new != self.ctx.cfg["card"]:
            self.ctx.cfg["card"] = new

    def card_global(self) -> QRect:
        c = self._card_rect()
        return QRect(self.mapToGlobal(c.topLeft().toPoint()), c.size().toSize())

    def _card_rect(self) -> QRectF:
        h, m = self.pageh.level - (1.0 - self.chrome.level) * S(COMPACT), self._max_l
        y = m.top() + m.height() - h if self._anchor_bottom else m.top()
        return QRectF(m.left(), y, m.width(), h)

    def _shape(self):
        t = self.morph.level
        b, c = self._ball_l, self._card_rect()
        r = QRectF(lerp(b.left(), c.left(), t), lerp(b.top(), c.top(), t),
                   lerp(b.width(), c.width(), t), lerp(b.height(), c.height(), t))
        return r, lerp(b.width() / 2, S(ui.radius), max(0.0, min(1.0, t)))

    def _card_h(self, key: str) -> float:
        return float(min(S(CHROME_TOP + CHROME_BOTTOM) + self.pages[key][2], self.card_max_h))

    # ------------------------------------------------------------------ pages
    def _ensure_page(self, key: str):
        if key not in self.pages:
            page = make_page(self.ctx, key)
            align_slider_rows(page)
            h = page.content_height()
            sa = ScrollArea(page, h, self.body.host)
            sa.hide()
            self.pages[key] = (sa, page, h)
        return self.pages[key]

    def _drop_page(self, key: str) -> None:
        if key in self.pages:
            sa, page, _h = self.pages.pop(key)
            page.on_hide()
            sa.hide()
            sa.deleteLater()

    def page(self):
        entry = self.pages.get(self.current)
        return entry[1] if entry else None

    def each_page(self):
        return [entry[1] for entry in self.pages.values()]

    def _layout_body(self) -> None:
        c = self._card_rect()
        self.body.setGeometry(int(round(c.left())), int(round(c.top())), int(c.width()), int(round(c.height())))

    def _finish_slide(self) -> None:
        if self.slide.busy or self._snap_new is not None:
            self.slide.jump(1.0)

    def goto(self, key: str) -> None:
        if key not in self.tab_keys():
            return
        if not self.expanded:
            self.current = key
            self.ctx.cfg["page"] = key
            self.body.tabbar.set_current(key)
            return self.expand()
        if key == self.current or self.morph.busy:
            return
        self._finish_slide()
        self.fade.jump(1.0)
        self.chrome.jump(1.0)
        self.toast_w.hide()
        self.confirm_w.hide()
        self.drawer.close_now()
        keys = self.tab_keys()
        self._dir = 1 if keys.index(key) > keys.index(self.current) else -1
        old_sa, old_page, _ = self._ensure_page(self.current)
        self._snap_old = snapshot(old_sa)
        old_page.on_hide()
        old_sa.hide()
        self.current = key
        self.ctx.cfg["page"] = key
        self.body.tabbar.set_current(key)
        sa, _page, _h = self._ensure_page(key)
        new_h = self._card_h(key)
        sa.setGeometry(0, 0, S(CARD_W - 2 * PAD) + S(ScrollArea.GUTTER), int(new_h) - S(CHROME_TOP + CHROME_BOTTOM))
        self._snap_new = snapshot(sa)
        self.slide.jump(0.0)
        self.slide.to(1.0, 280)
        self.pageh.to(new_h, 320)
        gone = [k for k in TEMP_TABS if k != key]          # a tab shown only while it was being read
        if gone:
            TEMP_TABS.difference_update(gone)
            self.body.set_tabs()

    def _on_slide(self) -> None:
        if self.slide.level >= 0.999 and self._snap_new is not None:
            self._snap_old = self._snap_new = None
            if self.expanded and not self.morph.busy:
                sa, page, _ = self._ensure_page(self.current)
                self.body.resizeEvent(None)
                sa.show()
                page.on_show()
        self.update()

    def _on_pageh(self) -> None:
        if self.expanded and not self.morph.busy:
            self._layout_body()
        self.update()

    def reload_page(self) -> None:
        """Rebuild the current page (its content changed) and glide to its new height."""
        if not self.expanded:
            self._drop_page(self.current)
            return
        self._finish_slide()
        old = self.pages.get(self.current)
        offset = old[0].offset() if old else 0.0
        self._drop_page(self.current)
        sa, page, _h = self._ensure_page(self.current)
        self.body.resizeEvent(None)
        sa.show()
        sa._target = min(offset, max(0.0, sa.max_offset()))
        sa._pos.jump(sa._target)
        page.on_show()
        self.pageh.to(self._card_h(self.current), 300)

    def rebuild(self) -> None:
        """Scale or language changed: rebuild every widget at an animation boundary."""
        self.morph.jump(1.0 if self.expanded else 0.0)
        self._finish_slide()
        for key in list(self.pages):
            self._drop_page(key)
        self.drawer.close_now()
        self.fade.jump(1.0)
        self.chrome.jump(1.0)
        self._fsnap = None
        self.toast_w.deleteLater()
        self.confirm_w.deleteLater()
        self.body.deleteLater()
        _tiles.clear()
        self.body = Body(self)
        self.toast_w = Toast(self)
        self.confirm_w = Confirm(self)
        self.busy_w.raise_()
        self.ball.clamp()
        self.ball.place()
        if self.expanded:
            home = self.card_pos or self.card_global().topLeft()       # same top-left corner as before
            d = BD()
            self._place(QRect(home.x(), home.y(), d, d), home)
            sa, page, _ = self._ensure_page(self.current)
            self.pageh.jump(self._card_h(self.current))
            self._layout_body()
            sa.show()
            page.on_show()
            self._fsnap = snapshot(self.body)                         # the new layout fades in
            self.body.hide()
            self.fade.jump(0.0)
            self.fade.to(1.0, 240)
        self.update()
        self.ball.update()

    # ------------------------------------------------------------------ expand / collapse
    def show_ball(self) -> None:
        self._restore_position()
        self.ball.place()
        self.ball.show()
        self.ball.appear.to(1.0, 420)
        self._retime()

    def toggle(self) -> None:
        self.collapse() if self.expanded else self.expand()

    def expand(self) -> None:
        """Open the card where it lives. If the ball is parked in a corner it first flies back there."""
        if self.expanded or self.morph.busy or self.ball.gliding or self.ctx.welcome is not None:
            return
        home, b = self.card_pos, self.ball
        parked = self._docked is not None and (b.center - self._docked).manhattanLength() < 4
        self._pending_home = home if (home is not None and parked) else None
        if self._pending_home is not None:
            d, cw = BD(), S(CARD_W)
            target = QPoint(max(home.x() + d // 2, min(b.center.x(), home.x() + cw - d // 2)), home.y() + d // 2)
            if (target - b.center).manhattanLength() > 6:
                b.hover.jump(0.0)
                return b.glide_to(target, then=self._expand_now, fast=True)
        self._expand_now()

    def _expand_now(self) -> None:
        if self.expanded or self.morph.busy:
            return
        self.chrome.jump(1.0)
        self.expanded = True
        self.ctx.cfg["card_open"] = True
        self.ball.appear.jump(1.0)
        self.ball.hover.jump(0.0)
        self._place(self.ball.rect_global(), self._pending_home)   # laid out while hidden: nothing can flash
        sa, _page, _ = self._ensure_page(self.current)
        self.pageh.jump(self._card_h(self.current))
        self._layout_body()
        sa.show()
        self._snap = snapshot(self.body)
        self.body.hide()
        self.morph.jump(0.0)
        self.show()
        self.repaint()                                     # first frame = the ball, exactly where it already is
        self.ball.hide()
        self.morph.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.morph.to(1.0, 400)
        self._retime()
        self.ctx.on_visibility()

    def collapse(self) -> None:
        if not self.expanded or self.morph.busy:
            return
        self._finish_slide()
        self.pageh.jump(self.pageh.target)
        self.fade.jump(1.0)
        self.toast_w.hide()
        self.confirm_w.hide()
        self.busy_w.hide()
        self.drawer.close_now()
        self._spark_timer.stop()
        self._idle.stop()
        self.expanded = False
        self.ctx.cfg["card_open"] = False
        c, d = self._card_rect(), BD()
        centre = self.mapToGlobal(c.center().toPoint())
        wa = work_area(centre)
        left, top = centre.x() < wa.center().x(), centre.y() < wa.center().y()
        self._corner = self.ball.corner_point(wa, left, top)
        self._ball_l = QRectF(c.left() if left else c.right() - d, c.top() if top else c.bottom() - d, d, d)
        page = self.page()
        self._snap = snapshot(self.body)
        if page:
            page.on_hide()
        self.body.hide()
        if self.current in TEMP_TABS:                      # the temporary tab goes away with the card
            TEMP_TABS.clear()
            self.current = "home"
            self.ctx.cfg["page"] = "home"
            self.body.set_tabs()
        self.morph.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.morph.to(0.0, 300)
        self.ctx.on_visibility()

    def _on_morph(self) -> None:
        t = self.morph.level
        if not self.morph.busy:
            if self.expanded and t >= 0.999 and not self.body.isVisible():
                self._snap = None
                self._layout_body()
                self.body.show()
                page = self.page()
                if page:
                    page.on_show()
                self._in_since, self._out_since = 0.0, time.monotonic()
                self._idle.start()
                QTimer.singleShot(600, self.ctx.offer_update)
            elif not self.expanded and t <= 0.001 and self.isVisible():
                self._snap = None
                self.ball.set_center(self.mapToGlobal(self._ball_l.center().toPoint()))
                self.ball.show()
                self.ball.repaint()                        # the real ball is drawn on top of the painted one
                self.hide()
                self._retime()
                self._docked = QPoint(self._corner)
                self.ball.glide_to(self._corner)           # then it curves into the nearest corner
        self.update()

    def toast(self, text: str, kind: str = "ok") -> None:
        if self.expanded and not self.morph.busy:
            self.toast_w.show_text(text, kind, self._card_rect())

    def confirm(self, text: str, on_yes, yes: str = "", no: str = "", persistent: bool = False,
                on_no=None) -> None:
        if self.expanded and not self.morph.busy:
            self.toast_w.hide()
            self.confirm_w.ask(text, on_yes, self._card_rect(), yes, no, persistent, on_no)

    # ------------------------------------------------------------------ loading overlay
    def show_busy(self, text: str) -> None:
        if self.expanded and not self.morph.busy:
            self.toast_w.hide()
            self.confirm_w.hide()
            self.busy_w.start(text, self._card_rect())

    def end_busy(self, then=None) -> None:
        self.busy_w.finish(then)

    def _on_fade(self) -> None:
        if self.fade.level >= 0.999 and self._fsnap is not None:
            self._fsnap = None
            if self.expanded and not self.morph.busy:
                self.body.show()
        self.update()

    # ------------------------------------------------------------------ menu bar auto-hide
    def _chrome_allowed(self) -> bool:
        return (self.ctx.cfg["autohide"] and self.expanded and self.current in MUSIC_PAGES
                and not self.morph.busy and not self.slide.busy and self._snap_new is None
                and self._drag_origin is None and not self.confirm_w.isVisible() and not self.drawer.is_open()
                and not self.busy_w.isVisible()
                and not self.modal)

    def _watch_idle(self) -> None:
        if not self.expanded or self.morph.busy:
            return
        now = time.monotonic()
        m = S(6)
        inside = self.card_global().adjusted(-m, -m, m, m).contains(QCursor.pos())
        if inside:
            self._in_since, self._out_since = self._in_since or now, 0.0
        else:
            self._out_since, self._in_since = self._out_since or now, 0.0
        allowed = self._chrome_allowed()
        if self.chrome.target > 0.5:
            if allowed and self._out_since and now - self._out_since > 2.5:
                self.toast_w.hide()
                self.chrome.to(0.0, 420)
        elif not allowed or (self._in_since and now - self._in_since > 0.25) or (inside and win.key_down(0x01)):
            self.chrome.to(1.0, 320)

    def show_chrome(self) -> None:
        self._in_since, self._out_since = time.monotonic(), 0.0
        if self.chrome.target < 0.5:
            self.chrome.to(1.0, 320)

    def chrome_setting(self) -> None:
        if not self.ctx.cfg["autohide"]:
            self.show_chrome()

    def _on_chrome(self) -> None:
        if self.expanded and not self.morph.busy:
            self._layout_body()
            self.body.resizeEvent(None)
        self.update()

    def theme_changed(self) -> None:
        self._sparks = extras.theme_sparkles(self.ctx.theme(), self._max_l.width(), self._max_l.height(), S(BAND))
        self._retime()
        self.update()
        self.ball.update()
        for page in self.each_page():
            page.update()

    def _twinkle(self) -> None:
        """Repaint only the little squares around each sparkle."""
        if not self.expanded or self.morph.busy or self.pageh.busy or self.slide.busy or not self._sparks:
            return
        card, m = self._card_rect(), self._max_l
        region = QRegion()
        pad = S(6)
        for x, y, _size, _phase, _speed in self._sparks:
            px, py = m.left() + x, m.top() + y
            if py < card.bottom():
                region = region.united(QRegion(int(px - pad), int(py - pad), 2 * pad, 2 * pad))
        self.update(region)

    def pick_file(self, title: str, pattern: str) -> str:
        if win.fullscreen_state() == 2:
            self.toast(tr("Leave your game first"), "warn")
            return ""
        self.modal = True
        self.hide()                       # the card is always on top and would cover the dialog
        try:
            path, _ = QFileDialog.getOpenFileName(None, title, "", pattern)
        finally:
            self.show()
            self.modal = False
        return path or ""

    # ------------------------------------------------------------------ timers / state
    def set_game_state(self, state: int) -> None:
        if state != self.game_state:
            self.game_state = state
            self._retime()

    def _retime(self) -> None:
        """Animation clock: 60 fps for the card, 30 for the ball, nothing in exclusive fullscreen."""
        if self.game_state == 2:
            self._pulse.stop()
            self._spark_timer.stop()
            return
        if self.expanded and self._sparks:
            self._spark_timer.start()
        else:
            self._spark_timer.stop()
        if self.ctx.cfg["halo"]:
            ms = 16 if self.expanded else 33
            if self.game_state == 1:
                ms = 66
        else:
            ms = 33 if self.expanded else 1000
        self._pulse.start(ms)

    def _tick(self) -> None:
        if not self.expanded:
            if self.ball.isVisible() and not self.ball.gliding:
                self.ball.update()
            return
        if self.morph.busy or self.pageh.busy or self.slide.busy or self.chrome.busy:
            return
        if self.ctx.cfg["halo"] or self.ctx.theme().get("edge") == "rainbow":
            shape, _r = self._shape()
            g = S(GLOW)
            outer = shape.adjusted(-g, -g, g, g).toAlignedRect()
            inner = shape.adjusted(4, 4, -4, -4).toAlignedRect()
            self.update(QRegion(outer).subtracted(QRegion(inner)))
        if self.ctx.state.status is Status.PLAYING and self.body.isVisible():
            self.body.update(self.body.dots_rect())

    def on_state(self, st) -> None:
        for page in self.each_page():
            page.on_state(st)
        if self.body.isVisible():
            self.body.update(self.body.dots_rect())

    def on_art(self, pixmap) -> None:
        for page in self.each_page():
            page.on_art(pixmap)

    def set_accent(self, color: QColor) -> None:
        if color == self._accent_to:
            return
        self._accent_from, self._accent_to = QColor(ui.accent), QColor(color)
        self.accent_t.jump(0.0)
        self.accent_t.to(1.0, 450)

    def set_accent_now(self, color: QColor) -> None:
        """Animated themes step the colour themselves (a few times a second)."""
        self.accent_t.stop()
        self._accent_from = self._accent_to = QColor(color)
        self.accent_t.jump(1.0)

    def _on_accent(self) -> None:
        ui.accent = mix(self._accent_from, self._accent_to, self.accent_t.level)
        self.update()
        self.ball.update()
        if self.body.isVisible():
            for w in self.body.findChildren(QWidget):
                if w.isVisible():
                    w.update()
            self.body.update()

    def set_opacity(self, pct: int) -> None:
        self.setWindowOpacity(pct / 100)
        self.ball.setWindowOpacity(pct / 100)

    # ------------------------------------------------------------------ painting
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = max(0.0, min(1.0, self.morph.level))
        shape, radius = self._shape()
        level = self.ctx.glow_level()
        path = paint_shape(p, self.ctx, shape, radius, level, self.devicePixelRatioF())
        th = self.ctx.theme()
        if t > 0.3 and (th["layers"] or self._sparks):
            m = self._max_l
            p.save()
            p.setClipPath(path)
            p.setOpacity(min(1.0, (t - 0.3) / 0.5))
            pm = extras.theme_pattern(th, int(m.width()), int(m.height()), self._accent_to, self.devicePixelRatioF(),
                                      ui.scale, S(BAND))
            if pm is not None:
                p.drawPixmap(m.topLeft(), pm)
            if self._sparks:
                extras.paint_sparkles(p, self._sparks, m.left(), m.top(), ui.accent, time.monotonic(), ui.scale)
            p.restore()
        if t < 0.4:
            paint_ball_face(p, self.ctx, shape, 1.0 - t / 0.4)
        card = self._card_rect()
        if self._fsnap is not None and not self.morph.busy:
            p.save()
            p.setClipPath(path)
            p.setOpacity(self.fade.level)
            p.drawPixmap(card.topLeft(), self._fsnap)
            p.restore()
        f = t
        if self.morph.busy:                         # fade by time, not by size: content arrives last, leaves first
            lin = self.morph.currentTime() / max(1, self.morph.duration())
            f = (lin - 0.45) / 0.55 if self.expanded else 1.0 - lin / 0.35
            f = max(0.0, min(1.0, f))
        if self._snap is not None and f > 0.0:
            p.save()
            p.setClipPath(path)
            p.setOpacity(f * f * (3 - 2 * f))
            p.drawPixmap(QPointF(card.left(), card.top() + (1 - f) * S(6)), self._snap)
            p.restore()
        if self._snap_new is not None and self.expanded and not self.morph.busy:
            s = self.slide.level
            area = QRectF(card.left() + S(PAD), card.top() + S(CHROME_TOP), S(CARD_W - 2 * PAD + ScrollArea.GUTTER),
                          max(0.0, card.height() - S(CHROME_TOP + CHROME_BOTTOM)))
            p.save()
            p.setClipRect(area)
            shift = S(30) * self._dir
            if self._snap_old is not None:
                p.setOpacity(max(0.0, 1.0 - s * 1.6))
                p.drawPixmap(QPointF(area.left() - s * shift, area.top()), self._snap_old)
            p.setOpacity(min(1.0, s * 1.3))
            p.drawPixmap(QPointF(area.left() + (1 - s) * shift, area.top()), self._snap_new)
            p.restore()
        paint_edge(p, self.ctx, shape, radius, level)

    # ------------------------------------------------------------------ dragging the card (kept on screen)
    def begin_drag(self, global_pos: QPoint) -> None:
        self._drag_start = global_pos
        self._drag_origin = self.pos()
        self.drawer.close_now()

    def drag_to(self, global_pos: QPoint) -> None:
        if self._drag_origin is None:
            return
        new = self._drag_origin + (global_pos - self._drag_start)      # stored origin + total delta: no drift
        c = self._card_rect()
        wa, m = work_area(global_pos), S(8)
        x = max(wa.left() + m - c.left(), min(new.x(), wa.right() - m - c.right()))
        y = max(wa.top() + m - c.top(), min(new.y(), wa.bottom() - m - S(MIN_CARD) - c.top()))
        self.move(int(x), int(y))

    def end_drag(self) -> None:
        if self._drag_origin is None:
            return
        moved = self.pos() != self._drag_origin
        self._drag_origin = None
        if moved and self.expanded and not self.morph.busy:
            home = self.card_global().topLeft()                         # this is now where the card lives
            d = BD()
            self._place(QRect(home.x(), home.y(), d, d), home)
            self._layout_body()
            if self.current in self.pages:
                self.pageh.to(self._card_h(self.current), 220)

    # ------------------------------------------------------------------ position persistence (per monitor, normalised)
    def save_position(self) -> None:
        c = self.ball.center
        screen = QGuiApplication.screenAt(c) or QGuiApplication.primaryScreen()
        wa = screen.availableGeometry()
        self.ctx.cfg["ball"] = {"screen": screen.name(),
                                "nx": (c.x() - wa.left()) / max(1, wa.width()),
                                "ny": (c.y() - wa.top()) / max(1, wa.height())}

    def _restore_position(self) -> None:
        b = self.ctx.cfg["ball"]
        screen = next((s for s in QGuiApplication.screens() if s.name() == b["screen"]), None)
        if screen is not None and 0 <= b["nx"] <= 1 and 0 <= b["ny"] <= 1:
            wa = screen.availableGeometry()
            self.ball.center = QPoint(int(wa.left() + b["nx"] * wa.width()), int(wa.top() + b["ny"] * wa.height()))
            self.ball.clamp()
        else:
            wa = QGuiApplication.primaryScreen().availableGeometry()
            self.ball.center = self.ball.corner_point(wa, False, True)
        c = self.ctx.cfg["card"]
        screen = next((s for s in QGuiApplication.screens() if s.name() == c["screen"]), None)
        if screen is not None and 0 <= c["nx"] <= 1 and 0 <= c["ny"] <= 1:
            wa = screen.availableGeometry()
            self.card_pos = QPoint(int(wa.left() + c["nx"] * wa.width()), int(wa.top() + c["ny"] * wa.height()))
            self._docked = QPoint(self.ball.center)        # first open goes back to where the card was

    def reset_position(self) -> None:
        self.card_pos = self._docked = None
        self.ctx.cfg["card"] = {"screen": "", "nx": -1.0, "ny": -1.0}
        wa = QGuiApplication.primaryScreen().availableGeometry()
        target = self.ball.corner_point(wa, False, True)
        if self.expanded:
            self.collapse()
            self._corner = target
        else:
            self.ball.glide_to(target)

    def closeEvent(self, e) -> None:
        e.ignore()
        self.ctx.quit()


# ==================================================================================================
# SECTION: app
# ==================================================================================================
import atexit
import logging
import math
import os
import sys
from pathlib import Path
import time

from PyQt6.QtCore import QLocale, QObject, QPointF, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QIcon, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon


log = logging.getLogger("rubenium.app")

APP_QSS = """
QToolTip { background:#181C1D; color:#EDEDED; border:1px solid #2C3233; padding:4px 7px; font-size:12px; }
QMenu { background:#181C1D; color:#EDEDED; border:1px solid #2C3233; padding:6px; font-size:13px; }
QMenu::item { padding:6px 24px 6px 12px; border-radius:5px; }
QMenu::item:selected { background:#2A3031; }
QMenu::separator { height:1px; background:#2C3233; margin:6px 4px; }
"""


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


def app_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(alpha(ACCENT_DEFAULT, 0.35))
    p.drawEllipse(QPointF(32, 32), 31, 31)
    p.setBrush(QColor("#0B0F10"))
    p.drawEllipse(QPointF(32, 32), 27, 27)
    f = QFont("Segoe UI")
    f.setPixelSize(36)
    f.setWeight(QFont.Weight.ExtraBold)
    p.setFont(f)
    p.setPen(QColor(ACCENT_DEFAULT))
    p.drawText(pm.rect(), int(Qt.AlignmentFlag.AlignCenter), "R")
    p.end()
    return QIcon(pm)


class App(QObject):
    """Shared context handed to the window and every page."""

    def __init__(self, qapp: QApplication) -> None:
        super().__init__()
        self.qapp = qapp
        self.cfg = Config()
        self._was_open = bool(self.cfg["card_open"])
        self.cfg["card_open"] = False
        self._news = False
        set_lang(self.cfg["lang"] or ("fr" if QLocale.system().language() == QLocale.Language.French else "en"))
        apply_look(self.cfg)
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
        self._env = 0.0
        self._audio = QTimer(self)
        self._audio.setInterval(33)
        self._audio.timeout.connect(self._sample_audio)
        self.rocket = extras.RocketSwaps(self.cfg)
        self.rocket.busy.connect(self._rocket_busy)
        self.rocket.done.connect(self._rocket_done)
        self.rocket.changed.connect(self._rocket_changed)
        self.updater = extras.Updater(VERSION)
        self.updater.found.connect(self._update_found)
        self.updater.checked.connect(self._update_checked)
        self.updater.progress.connect(lambda pct: self.window.show_busy(tr("Downloading update… {p}%", p=pct)))
        self.updater.ready.connect(self._update_ready)
        self.updater.failed.connect(self._update_failed)
        self._update_prompted = ""
        extras.Updater.cleanup()
        self.session = extras.Session()
        self.sensors.sample.connect(self.session.feed)
        self.timer = extras.TimerEngine(self.cfg)
        self.timer_overlay = extras.TimerOverlay(self.cfg, self.timer)
        self.hotkeys = extras.Hotkeys(qapp)
        self.hotkeys.triggered.connect(self._on_key)
        self._usage = QTimer(self)
        self._usage.setInterval(60000)
        self._usage.timeout.connect(self._count_usage)
        self._usage.start()
        self.window = MainWindow(self)

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
        self._news = self.cfg["seen_version"] != VERSION and self.cfg["usage_s"] > 0    # updated, not new
        self.cfg["seen_version"] = VERSION
        restarted = "--updated" in sys.argv or "--elevated" in sys.argv
        if not self.cfg["welcome"] or restarted:
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
        selftest = "--selftest" in sys.argv
        self._safe("media", self.media.start)
        if not selftest:
            self._safe("tray", self._make_tray)
            self._safe("autostart", self._sync_autostart)
        self._safe("overlays", self.apply_overlays)
        self._safe("timer", self.apply_timer)
        self._safe("accent", self.refresh_accent)
        self._safe("rocket", self.rocket.start)
        if self.cfg["update_check"] and not selftest:
            self._safe("updates", self.updater.start)
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
        if self.cfg["autostart"] is None:                 # first run: start with Windows by default
            self.cfg["autostart"] = win.autostart_set(True)
        elif self.cfg["autostart"]:
            win.autostart_set(True)                       # keeps the path right if the app was moved

    def _retry_tray(self) -> None:
        if self.tray is None and not self._closing and "--selftest" not in sys.argv:
            self._make_tray()

    def _reapply_display(self) -> None:
        if self.cfg["display"]["active"] in ("A", "B") and not self._closing:
            self.display.apply()

    def _selftest_update(self, new_exe: str) -> None:
        try:
            path = extras.place_exe(Path(new_exe), "999.0.0" if os.environ.get("RUBENIUM_TEST_SIDE") else VERSION)
            log.info("UPDATE SWAP OK %s", path)
            ok = extras.restart(path, ("--selftest",))
        except Exception:  # noqa: BLE001
            log.exception("UPDATE SWAP FAILED")
            ok = False
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
            self.welcome.launch()
            return QTimer.singleShot(3500, self._selftest)
        steps = [w.expand] + [lambda k=k: w.goto(k) for k, _, _ in TABS]
        steps += [lambda: self.set_language("fr"), lambda: w.goto("home"), lambda: w.goto("rl"),
                  lambda: self.set_language(lang or "en"), w.collapse, w.expand, w.collapse]

        def run(i: int = 0) -> None:
            if i < len(steps):
                try:
                    steps[i]()
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
                    log.exception("SELFTEST step %d failed", i)
                QTimer.singleShot(900, lambda: run(i + 1))
                return
            sys.excepthook = old_hook
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
                        self.timer_overlay, self.welcome):
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
        self._pos_base, self._pos_t = float(st.position_ms), time.monotonic()
        if st.art_key != self._art_key:
            self._art_key = st.art_key
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
    def usage_hours(self) -> float:
        return self.cfg["usage_s"] / 3600

    def _count_usage(self) -> None:
        self.cfg["usage_s"] = self.cfg["usage_s"] + 60.0

    def theme(self) -> dict:
        if self._preview:
            return extras.theme_by_id(self._preview)
        th = extras.theme_by_id(self.cfg["theme"])
        return th if self.usage_hours() >= th["hours"] else extras.THEMES[0]

    def set_theme(self, ident: str) -> None:
        self._preview = ""
        self.cfg["theme"] = ident
        self._theme_changed()

    def preview_theme(self, ident: str) -> None:
        self._preview = ident
        self._theme_changed()

    def _theme_changed(self) -> None:
        self.window.theme_changed()

    def base_accent(self) -> QColor:
        custom = self.cfg["custom_accent"]
        if custom and QColor(custom).isValid():
            return QColor(custom)
        return QColor(ACCENT_DEFAULT)

    def refresh_accent(self) -> None:
        target = None
        if self.cfg["accent_from_art"] and self.art_pixmap is not None:
            target = accent_from_image(self.art_pixmap)
        self.window.set_accent(target or self.base_accent())
        for overlay in (self.hud,):
            if overlay.isVisible():
                overlay.update()

    def refresh_look(self) -> None:
        self.window._retime()
        self._sync_audio()
        self.on_visibility()
        self.window.update()
        self.window.ball.update()

    def ball_style(self) -> str:
        return extras.unlocked_style(extras.R_STYLES, self.cfg["ball_style"], self.usage_hours())

    def ring_style(self) -> str:
        return extras.unlocked_style(extras.RING_STYLES, self.cfg["ring_style"], self.usage_hours())

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
    def _update_found(self, info: dict) -> None:
        if self.window.current == "settings" and self.window.expanded:
            self.window.reload_page()
        self.offer_update()
        if self.tray is not None and not self.window.expanded:
            self.tray.showMessage("Rubenium", tr("Update {v} available", v=info["label"]),
                                  QSystemTrayIcon.MessageIcon.Information, 5000)

    def offer_update(self) -> None:
        info = self.updater.latest
        if not info or self._update_prompted == info["version"] or not self.window.expanded:
            return
        if self.window.confirm_w.isVisible() or self.window.busy_w.isVisible():
            return
        self._update_prompted = info["version"]
        self.window.confirm(tr("Update {v} available", v=info["label"]), self.install_update,
                            yes=tr("Update"), no=tr("Later"))

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
        if extras.restart(path):
            QTimer.singleShot(400, self.quit)
        else:
            self.window.end_busy(lambda: self.toast(tr("Update installed. Restart Rubenium."), "ok"))

    def _update_failed(self, key: str) -> None:
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
        self.media.set_preferred(self.cfg["source"])
        self.refresh_accent()
        self.rebuild_ui()

    # ------------------------------------------------------------------ actions
    def toast(self, text: str, kind: str = "ok") -> None:
        self.window.toast(text, kind)

    def goto(self, key: str) -> None:
        self.window.goto(key)

    def reload_page(self) -> None:
        QTimer.singleShot(0, self.window.reload_page)

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
    def quit(self) -> None:
        self.shutdown()
        self.qapp.quit()

    def shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        log.info("Shutting down")
        try:
            self._audio.stop()
            self._usage.stop()
            self.rocket.stop()
            self.updater.stop()
            self.hotkeys.close()
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
    if extras.handoff(VERSION):                     # a newer copy installed by the updater takes over
        return 0
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


if __name__ == "__main__":
    sys.exit(main())
