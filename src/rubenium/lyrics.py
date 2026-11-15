# -*- coding: utf-8 -*-
"""Time-synced lyrics from LRCLIB (free public API, no key), fetched in a worker thread and cached on disk."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import ssl
import threading
import urllib.parse
import urllib.request

from PyQt6.QtCore import QObject, pyqtSignal

from .core import APP_NAME, LYRICS_DIR, VERSION

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
