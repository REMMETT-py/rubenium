"""Rubenium accounts: log in, stay logged in, and tell the server the app is in use.

The server (Supabase) decides everything that matters; this file only asks. The key below is the public
"publishable" key: it is meant to be shipped in the app and can do nothing the server's rules do not allow."""
import base64
import json
import logging
import os
import re
import threading
import time
import uuid

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from . import win
from .core import DATA_DIR

log = logging.getLogger("rubenium.online")

API_URL = os.environ.get("RUBENIUM_API", "https://nrdcdjeahvvtkswkvacz.supabase.co")
API_KEY = "sb_publishable_cdVja4ZFwumAmMQIfZgaOw_pQbCbAXp"
MAIL = "@users.rubenium.app"                 # accounts have no real e-mail: the username is turned into one
USERNAME_RE = re.compile(r"^[A-Za-z0-9]{3,10}$")
PASSWORD_MIN = 8
BEAT_S = 60                                  # the server counts time from these, once a minute
ACTIVE_S = 600                               # "in use" = music playing, or mouse/keyboard in the last 10 min


class ApiError(Exception):
    def __init__(self, key: str, status: int = 0) -> None:
        super().__init__(key)
        self.key, self.status = key, status


def _request(path: str, body=None, token: str = "", method: str = "POST", timeout: float = 12.0):
    """One call to the server. Returns the decoded answer; raises ApiError('offline' | a server message)."""
    import ssl
    import urllib.error
    import urllib.request
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        ctx = ssl.create_default_context()
    headers = {"apikey": API_KEY, "Content-Type": "application/json", "User-Agent": "Rubenium"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(API_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx if API_URL.startswith("https") else None) as r:  # noqa: S310
            raw = r.read()
            return json.loads(raw.decode("utf-8")) if raw else None
    except urllib.error.HTTPError as exc:
        try:
            info = json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            info = {}
        text = " ".join(str(info.get(k, "")) for k in ("error_code", "code", "msg", "message", "error_description"))
        raise ApiError(text.strip() or f"http {exc.code}", exc.code) from None
    except Exception as exc:  # noqa: BLE001  (no internet, DNS, timeout...)
        raise ApiError("offline") from exc


def explain(err: ApiError) -> str:
    """A server or network error as a short sentence for the login screen (English key for tr())."""
    text = (err.key or "").lower()
    if text == "offline":
        return "No internet connection"
    if "rb_no_such_user" in text:
        return "No player with this name"
    if "rb_thats_you" in text:
        return "That is you"
    if "rb_friends_only" in text:
        return "Friends only"
    if "rb_too_many" in text:
        return "Your friends list is full"
    if "rb_username_taken" in text or "already registered" in text or "user_already_exists" in text:
        return "This username is taken"
    if "invalid login" in text or "invalid_credentials" in text:
        return "Wrong username or password"
    if "rate limit" in text or err.status == 429:
        return "Too many tries: wait a minute"
    if "weak_password" in text or "password should" in text:
        return "Password too short (8 or more)"
    if "rb_bad_username" in text:
        return "3 to 10 letters or numbers"
    if "not confirmed" in text or "email_address_invalid" in text or "signup" in text and "disabled" in text:
        return "Accounts are not open yet"
    return "Something went wrong: try again"


def password_strength(pw: str) -> int:
    """0 too short, 1 weak, 2 ok, 3 strong."""
    if len(pw) < PASSWORD_MIN:
        return 0
    kinds = sum(bool(re.search(p, pw)) for p in (r"[a-z]", r"[A-Z]", r"[0-9]", r"[^A-Za-z0-9]"))
    return 3 if (kinds >= 3 and len(pw) >= 10) else (2 if kinds >= 2 else 1)


# -- the saved login: encrypted by Windows for this Windows user (never a plain-text file)
def _session_path():
    return DATA_DIR / "session.dat"


def _seal(data: bytes) -> bytes:
    return win.protect(data) if win.IS_WIN else base64.b64encode(data)


def _unseal(data: bytes) -> bytes:
    return win.unprotect(data) if win.IS_WIN else base64.b64decode(data)


class Online(QObject):
    changed = pyqtSignal()                    # logged in / out, or the profile changed
    answered = pyqtSignal(str, bool, str)     # what ("login" | "signup" | "free:<name>"), ok, message key
    _back = pyqtSignal(object)                # run on the main thread

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self.s: dict = {}                     # access_token, refresh_token, expires_at, username, user_id
        self.minutes = 0
        self.offline = False
        self.elsewhere = False                # another PC of this account is counting time right now
        self.busy = False
        self.device = uuid.uuid4().hex        # this run of the app (only one earns time per account)
        self._back.connect(lambda fn: fn())
        self._beat = QTimer(self)
        self._beat.setInterval(BEAT_S * 1000)
        self._beat.timeout.connect(self._tick)
        self._load()

    # -- state
    def logged_in(self) -> bool:
        return bool(self.s.get("refresh_token"))

    def username(self) -> str:
        return str(self.s.get("username", ""))

    def hours(self) -> float:
        return self.minutes / 60.0

    def _load(self) -> None:
        try:
            data = json.loads(_unseal(_session_path().read_bytes()).decode("utf-8"))
            if isinstance(data, dict) and data.get("refresh_token") and data.get("username"):
                self.s = data
                self.minutes = int(data.get("minutes", 0))
        except Exception:  # noqa: BLE001  (no file yet, or not readable on this PC)
            self.s = {}

    def _save(self) -> None:
        try:
            path = _session_path()
            if not self.s:
                path.unlink(missing_ok=True)
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_bytes(_seal(json.dumps(dict(self.s, minutes=self.minutes)).encode("utf-8")))
            os.replace(tmp, path)
        except Exception:  # noqa: BLE001
            log.warning("could not save the login", exc_info=True)

    def _adopt(self, ans: dict, username: str = "") -> None:
        user = ans.get("user") or {}
        name = username or (user.get("user_metadata") or {}).get("username") or self.username()
        self.s = {"access_token": ans["access_token"], "refresh_token": ans["refresh_token"],
                  "expires_at": time.time() + float(ans.get("expires_in", 3600)), "username": name,
                  "user_id": user.get("id", self.s.get("user_id", ""))}
        self.offline = False
        self._save()

    # -- start / stop
    def start(self) -> None:
        self._beat.start()
        if self.logged_in():
            QTimer.singleShot(1500, self._tick)

    def stop(self) -> None:
        self._beat.stop()

    # -- log in, create, log out (the work runs off the main thread)
    def _run(self, what: str, job) -> None:
        def work():
            try:
                done = job()
                self._back.emit(lambda: (done(), self._finish(what, True, "")))
            except ApiError as err:
                msg = explain(err)
                log.info("%s failed: %s", what, err.key)
                self._back.emit(lambda: self._finish(what, False, msg))
            except Exception:  # noqa: BLE001
                log.exception("%s failed", what)
                self._back.emit(lambda: self._finish(what, False, "Something went wrong: try again"))
        threading.Thread(target=work, daemon=True).start()

    def _finish(self, what: str, ok: bool, msg: str) -> None:
        if what in ("login", "signup"):
            self.busy = False
            if ok:
                self.changed.emit()
                QTimer.singleShot(200, self._tick)
        self.answered.emit(what, ok, msg)

    def log_in(self, username: str, password: str) -> None:
        if self.busy:
            return
        self.busy = True

        def job():
            ans = _request("/auth/v1/token?grant_type=password",
                           {"email": username.lower() + MAIL, "password": password})
            return lambda: self._adopt(ans)
        self._run("login", job)

    def sign_up(self, username: str, password: str) -> None:
        if self.busy:
            return
        self.busy = True

        def job():
            ans = _request("/auth/v1/signup", {"email": username.lower() + MAIL, "password": password,
                                               "data": {"username": username}})
            if not ans or not ans.get("access_token"):
                raise ApiError("email not confirmed")           # the server is not set up for accounts yet
            return lambda: self._adopt(ans, username)
        self._run("signup", job)

    def check_free(self, username: str) -> None:
        def job():
            free = _request("/rest/v1/rpc/rb_username_free", {"name": username}, timeout=8)
            if free is not True:
                raise ApiError("rb_username_taken")
            return lambda: None
        self._run("free:" + username, job)

    def delete_account(self) -> None:
        """Delete this account for good (the server checks the username again)."""
        name = self.username()

        def job():
            if self.rpc("rb_delete_account", {"confirm": name}) is not True:
                raise ApiError("delete failed")
            return self.log_out
        self._run("delete", job)

    def log_out(self) -> None:
        token = self.s.get("access_token", "")
        self.s, self.minutes, self.elsewhere = {}, 0, False
        self._save()
        self.changed.emit()
        if token:
            threading.Thread(target=lambda: self._quiet("/auth/v1/logout?scope=local", token), daemon=True).start()

    @staticmethod
    def _quiet(path: str, token: str) -> None:
        try:
            _request(path, {}, token, timeout=6)
        except ApiError:
            pass

    # -- calls for a logged-in account
    def _token(self) -> str:
        """A valid access token (renewed when it is about to run out). Called off the main thread."""
        if time.time() > float(self.s.get("expires_at", 0)) - 120:
            try:
                ans = _request("/auth/v1/token?grant_type=refresh_token", {"refresh_token": self.s["refresh_token"]})
            except ApiError as err:
                if err.key != "offline" and err.status in (400, 401, 403):      # the login is no longer valid
                    self._back.emit(self.log_out)
                raise
            self._back.emit(lambda: self._adopt(ans))
            return ans["access_token"]
        return self.s["access_token"]

    def rpc(self, name: str, args: dict):
        """Call a server function as the logged-in account. Off the main thread only."""
        return _request("/rest/v1/rpc/" + name, args, self._token())

    def ask(self, fn: str, args: dict, done) -> None:
        """Call a server function for the logged-in account; `done(ok, answer or message)` runs on the main thread."""
        def work():
            try:
                ans = self.rpc(fn, args)
                self._back.emit(lambda: done(True, ans))
            except ApiError as err:
                msg = explain(err)
                self._back.emit(lambda: done(False, msg))
            except Exception:  # noqa: BLE001
                log.exception("%s failed", fn)
                self._back.emit(lambda: done(False, "Something went wrong: try again"))
        threading.Thread(target=work, daemon=True).start()

    def _in_use(self) -> bool:
        try:
            from .media import Status
            if getattr(self.ctx, "state", None) is not None and self.ctx.state.status is Status.PLAYING:
                return True
        except Exception:  # noqa: BLE001
            pass
        return win.idle_seconds() < ACTIVE_S

    def _tick(self) -> None:
        if not self.logged_in() or not self._in_use():
            return

        def work():
            try:
                ans = self.rpc("rb_heartbeat", {"device": self.device}) or {}
                self._back.emit(lambda: self._beaten(ans))
            except ApiError as err:
                off = err.key == "offline"
                self._back.emit(lambda: self._set_offline(off))
            except Exception:  # noqa: BLE001
                log.exception("heartbeat failed")
        threading.Thread(target=work, daemon=True).start()

    def _set_offline(self, off: bool) -> None:
        if off != self.offline:
            self.offline = off
            self.changed.emit()

    def _beaten(self, ans: dict) -> None:
        before = (self.minutes, self.elsewhere, self.offline, self.username())
        self.minutes = int(ans.get("minutes", self.minutes))
        self.elsewhere = bool(ans.get("elsewhere"))
        self.offline = False
        if ans.get("username"):
            self.s["username"] = ans["username"]
        if before != (self.minutes, self.elsewhere, False, self.username()):
            self._save()
            self.changed.emit()
