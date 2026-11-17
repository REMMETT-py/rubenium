# -*- coding: utf-8 -*-
"""Now-playing for EVERY music app, through Windows' System Media Transport Controls.

Any app that shows up in the Windows volume flyout works: Spotify, Apple Music, Deezer,
TIDAL, YouTube / YouTube Music / SoundCloud in a browser, VLC, foobar2000, Media Player...
State changes arrive as GSMTC events; a light poll only keeps the timeline honest.
"""
from __future__ import annotations

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


# Apps that report "media" to Windows but are not music players: never shown or used on the music tab.
BLOCKED_SOURCES = ("medal",)


def blocked_source(app_id: str) -> bool:
    low = (app_id or "").lower()
    return any(word in low for word in BLOCKED_SOURCES)


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
            return [s for s in self._manager.get_sessions() if not blocked_source(s.source_app_user_model_id or "")]
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
            if current is not None and blocked_source(current.source_app_user_model_id or ""):
                current = None
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
        if session is None:                    # 3.2: nothing is running: the app opens the music app the user picked
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
