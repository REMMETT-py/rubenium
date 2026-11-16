# -*- coding: utf-8 -*-
"""Every Win32 / NVIDIA call in one place (ctypes only).

Each function fails soft: on another OS, a missing DLL or a refused call it returns
None / False so the UI can show an explained state instead of a dead control.
Nothing here injects into, hooks or reads the memory of another process.
"""
from __future__ import annotations

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


# --------------------------------------------------------------------------- #
# Every process in ONE system call (name, processor time, memory), like Task Manager.
# No handle is opened on any process, so nothing is denied and it costs about a millisecond.
# --------------------------------------------------------------------------- #
class _UNICODE_STRING(ctypes.Structure):
    _fields_ = [("Length", ctypes.c_ushort), ("MaximumLength", ctypes.c_ushort), ("Buffer", ctypes.c_void_p)]


class _SYSTEM_PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("NextEntryOffset", ctypes.c_uint32), ("NumberOfThreads", ctypes.c_uint32),
                ("WorkingSetPrivateSize", ctypes.c_longlong), ("HardFaultCount", ctypes.c_uint32),
                ("NumberOfThreadsHighWatermark", ctypes.c_uint32), ("CycleTime", ctypes.c_ulonglong),
                ("CreateTime", ctypes.c_longlong), ("UserTime", ctypes.c_longlong), ("KernelTime", ctypes.c_longlong),
                ("ImageName", _UNICODE_STRING), ("BasePriority", ctypes.c_int32),
                ("UniqueProcessId", ctypes.c_void_p), ("InheritedFromUniqueProcessId", ctypes.c_void_p),
                ("HandleCount", ctypes.c_uint32), ("SessionId", ctypes.c_uint32), ("UniqueProcessKey", ctypes.c_void_p),
                ("PeakVirtualSize", ctypes.c_size_t), ("VirtualSize", ctypes.c_size_t),
                ("PageFaultCount", ctypes.c_uint32), ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t)]


_snap_buf = None


def process_snapshot():
    """[(pid, name, processor time in 100 ns units, private memory in bytes)] or None if not available."""
    global _snap_buf
    if not IS_WIN:
        return None
    try:
        ntdll = ctypes.WinDLL("ntdll")
        size = len(_snap_buf) if _snap_buf is not None else 1 << 20
        for _ in range(6):
            if _snap_buf is None or len(_snap_buf) < size:
                _snap_buf = ctypes.create_string_buffer(size)
            need = ctypes.c_ulong(0)
            status = ntdll.NtQuerySystemInformation(5, _snap_buf, len(_snap_buf), ctypes.byref(need)) & 0xFFFFFFFF
            if status == 0:
                break
            if status != 0xC0000004:                     # anything but "buffer too small"
                return None
            size = max(len(_snap_buf) * 2, need.value + 65536)
        else:
            return None
        base = ctypes.addressof(_snap_buf)
        out, offset = [], 0
        while True:
            info = _SYSTEM_PROCESS_INFORMATION.from_address(base + offset)
            pid = int(info.UniqueProcessId or 0)
            name = ""
            if info.ImageName.Buffer and info.ImageName.Length:
                name = ctypes.wstring_at(info.ImageName.Buffer, info.ImageName.Length // 2)
            out.append((pid, name, int(info.UserTime) + int(info.KernelTime), int(info.WorkingSetPrivateSize)))
            if not info.NextEntryOffset:
                break
            offset += info.NextEntryOffset
        return out
    except Exception as exc:  # noqa: BLE001
        log.debug("process snapshot failed: %s", exc)
        return None


def play_sound(path: str) -> None:
    """Play a short .wav without waiting (a new sound cuts the previous one: no pile-up)."""
    if not IS_WIN:
        return
    try:
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception as exc:  # noqa: BLE001
        log.debug("sound failed: %s", exc)


# --------------------------------------------------------------------------- #
# Games that take over the mouse: let clicks pass through Rubenium while the pointer is hidden or locked
# --------------------------------------------------------------------------- #
class _CURSORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("flags", ctypes.c_uint32), ("hCursor", ctypes.c_void_p),
                ("x", ctypes.c_long), ("y", ctypes.c_long)]


class _ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", ctypes.c_int32), ("xHotspot", ctypes.c_uint32), ("yHotspot", ctypes.c_uint32),
                ("hbmMask", ctypes.c_void_p), ("hbmColor", ctypes.c_void_p)]


class _BITMAP(ctypes.Structure):
    _fields_ = [("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long), ("bmHeight", ctypes.c_long),
                ("bmWidthBytes", ctypes.c_long), ("bmPlanes", ctypes.c_ushort), ("bmBitsPixel", ctypes.c_ushort),
                ("bmBits", ctypes.c_void_p)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("rcMonitor", W.RECT), ("rcWork", W.RECT), ("dwFlags", W.DWORD)]


_blank_cache: dict = {}


def _bitmap_bytes(hbm) -> tuple:
    gdi = ctypes.windll.gdi32
    gdi.GetObjectW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    gdi.GetBitmapBits.argtypes = [ctypes.c_void_p, ctypes.c_long, ctypes.c_void_p]
    bm = _BITMAP()
    if not gdi.GetObjectW(ctypes.c_void_p(hbm), ctypes.sizeof(bm), ctypes.byref(bm)):
        return b"", 0
    size = bm.bmWidthBytes * bm.bmHeight
    if size <= 0 or size > 4 * 1024 * 1024:
        return b"", 0
    buf = ctypes.create_string_buffer(size)
    got = gdi.GetBitmapBits(ctypes.c_void_p(hbm), size, buf)
    return buf.raw[:max(0, got)], bm.bmBitsPixel


def cursor_is_blank(hcursor: int) -> bool:
    """True when the mouse pointer is an empty picture: many games hide the pointer that way while you aim."""
    if not IS_WIN or not hcursor:
        return False
    if hcursor in _blank_cache:
        return _blank_cache[hcursor]
    blank = False
    info = _ICONINFO()
    try:
        u = ctypes.windll.user32
        u.GetIconInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        if u.GetIconInfo(ctypes.c_void_p(hcursor), ctypes.byref(info)):
            if info.hbmColor:                                     # colour pointer: blank if nothing is opaque
                data, bpp = _bitmap_bytes(info.hbmColor)
                if data and bpp == 32:
                    blank = not any(data[3::4])
                elif data:
                    mask, _ = _bitmap_bytes(info.hbmMask)
                    blank = not any(data) and bool(mask) and all(b == 0xFF for b in mask)
            elif info.hbmMask:                                    # black and white: top half AND, bottom XOR
                data, _ = _bitmap_bytes(info.hbmMask)
                half = len(data) // 2
                blank = bool(data) and all(b == 0xFF for b in data[:half]) and not any(data[half:])
    except Exception:  # noqa: BLE001
        blank = False
    finally:
        try:
            gdi = ctypes.windll.gdi32
            gdi.DeleteObject.argtypes = [ctypes.c_void_p]
            for hbm in (info.hbmMask, info.hbmColor):
                if hbm:
                    gdi.DeleteObject(ctypes.c_void_p(hbm))
        except Exception:  # noqa: BLE001
            pass
    if len(_blank_cache) > 64:
        _blank_cache.clear()
    _blank_cache[hcursor] = blank
    return blank


_SHELL_CLASSES = {"progman", "workerw", "shell_traywnd", "shell_secondarytraywnd", "windows.ui.core.corewindow"}


def _foreground_game():
    """(left, top, right, bottom) of the window in front if it fills its whole monitor (a fullscreen or borderless
    game, or a video), else None. Never Rubenium itself, the desktop or the taskbar."""
    u = ctypes.windll.user32
    u.GetForegroundWindow.restype = ctypes.c_void_p
    u.MonitorFromWindow.restype = ctypes.c_void_p
    hwnd = u.GetForegroundWindow()
    if not hwnd:
        return None
    pid = W.DWORD(0)
    u.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(pid))
    if pid.value == os.getpid():
        return None
    cls = ctypes.create_unicode_buffer(64)
    u.GetClassNameW(ctypes.c_void_p(hwnd), cls, 64)
    if cls.value.lower() in _SHELL_CLASSES:
        return None
    rect = W.RECT()
    if not u.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect)):
        return None
    mon = u.MonitorFromWindow(ctypes.c_void_p(hwnd), 2)
    mi = _MONITORINFO()
    mi.cbSize = ctypes.sizeof(mi)
    if not mon or not u.GetMonitorInfoW(ctypes.c_void_p(mon), ctypes.byref(mi)):
        return None
    m = mi.rcMonitor
    if rect.left <= m.left and rect.top <= m.top and rect.right >= m.right and rect.bottom >= m.bottom:
        return (rect.left, rect.top, rect.right, rect.bottom)
    return None


def mouse_captured() -> bool:
    """True while a game has the mouse for aiming or turning the camera. Rubenium then lets every click and
    hover pass through to the game, so it can never be opened, dragged or lit up by accident. Seen as:
    - the pointer is hidden, or locked inside one window;
    - a fullscreen or borderless game is in front and its pointer is an empty picture, or is held in the
      middle of the screen (how most shooters turn the camera with the mouse).
    In a game menu with a normal pointer Rubenium stays usable."""
    if not IS_WIN:
        return False
    try:
        u = ctypes.windll.user32
        ci = _CURSORINFO()
        ci.cbSize = ctypes.sizeof(_CURSORINFO)
        if not u.GetCursorInfo(ctypes.byref(ci)):
            return False
        if ci.flags & 2:                                      # hidden because touch or a pen is used: not a game
            return False
        if not (ci.flags & 1) or not ci.hCursor:              # no pointer shown
            return True
        clip = W.RECT()
        if u.GetClipCursor(ctypes.byref(clip)):
            vx, vy = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
            vw, vh = u.GetSystemMetrics(78), u.GetSystemMetrics(79)
            if (clip.right - clip.left) < vw - 2 or (clip.bottom - clip.top) < vh - 2 or clip.left > vx or clip.top > vy:
                return True                                   # pointer locked inside one window
        game = _foreground_game()
        if game is None:
            return False
        if cursor_is_blank(int(ci.hCursor)):
            return True
        cx, cy = (game[0] + game[2]) // 2, (game[1] + game[3]) // 2
        return abs(ci.x - cx) <= 3 and abs(ci.y - cy) <= 3   # held in the middle of the game
    except Exception:  # noqa: BLE001
        return False


def fullscreen_in_front() -> bool:
    """A fullscreen or borderless window (a game) is in front of everything (not Rubenium, not the desktop)."""
    if not IS_WIN:
        return False
    try:
        return _foreground_game() is not None
    except Exception:  # noqa: BLE001
        return False


def set_click_through(hwnd: int, on: bool) -> None:
    """Let mouse clicks go through a (layered) window to whatever is under it, or stop doing so."""
    if not IS_WIN or not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        get = user32.GetWindowLongPtrW
        put = user32.SetWindowLongPtrW
        get.restype = ctypes.c_ssize_t
        get.argtypes = [W.HWND, ctypes.c_int]
        put.restype = ctypes.c_ssize_t
        put.argtypes = [W.HWND, ctypes.c_int, ctypes.c_ssize_t]
        style = get(hwnd, -20)                                    # GWL_EXSTYLE
        want = (style | 0x20) if on else (style & ~0x20)        # WS_EX_TRANSPARENT (the window is layered)
        if want != style:
            put(hwnd, -20, want)
    except Exception as exc:  # noqa: BLE001
        log.debug("click-through failed: %s", exc)



# --------------------------------------------------------------------------- #
# Small helpers for accounts: secrets kept by Windows, and time since the last input
# --------------------------------------------------------------------------- #
class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", W.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _crypt(data: bytes, protect_it: bool) -> bytes:
    """Windows data protection (DPAPI): only this Windows user on this PC can read the result back."""
    buf = ctypes.create_string_buffer(data, len(data))
    src = _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    out = _BLOB()
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    fn = crypt32.CryptProtectData if protect_it else crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0x01, ctypes.byref(out)):       # 0x01: never show UI
        raise OSError("data protection failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def protect(data: bytes) -> bytes:
    return _crypt(data, True)


def unprotect(data: bytes) -> bytes:
    return _crypt(data, False)


class _LASTINPUT(ctypes.Structure):
    _fields_ = [("cbSize", W.UINT), ("dwTime", W.DWORD)]


def idle_seconds() -> float:
    """Seconds since the mouse or keyboard was last used (0 when it cannot be told)."""
    if not IS_WIN:
        return 0.0
    try:
        info = _LASTINPUT(ctypes.sizeof(_LASTINPUT), 0)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        return ((ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0
    except Exception:  # noqa: BLE001
        return 0.0
