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
from .core import DATA_DIR, Net

log = logging.getLogger("rubenium.online")

API_URL = os.environ.get("RUBENIUM_API", "https://nrdcdjeahvvtkswkvacz.supabase.co")
API_KEY = "sb_publishable_cdVja4ZFwumAmMQIfZgaOw_pQbCbAXp"
MAIL = "@users.rubenium.app"                 # accounts have no real e-mail: the username is turned into one
USERNAME_RE = re.compile(r"^[A-Za-z0-9]{3,10}$")
PASSWORD_MIN = 8
BEAT_S = 60                                  # the server counts time from these, once a minute
ACTIVE_S = 600                               # "in use" = music playing, or mouse/keyboard in the last 10 min



def _run_back(fn) -> None:
    """Run a server answer on the main thread. A screen that was closed before its answer arrived is not an error."""
    try:
        fn()
    except RuntimeError as e:
        if "has been deleted" not in str(e):
            raise

class ApiError(Exception):
    def __init__(self, key: str, status: int = 0) -> None:
        super().__init__(key)
        self.key, self.status = key, status


# 4.0: online lag came from how requests were made, not from the server: every call built a new SSL context
# (reading the whole certificate bundle), opened a new connection with a full TLS handshake and started a new
# thread. With the live poll, Mini Golf every 0.6 s, trades and coinflips, that meant several handshakes a second,
# CPU spikes and answers arriving out of order. Now the SSL context is made once, each network thread keeps its
# connection open (keep-alive), and a small fixed pool of threads does the calls.
_SSL = None
_SSL_LOCK = threading.Lock()
_NET = threading.local()
_IDLE_S = 25.0                    # a connection unused this long is replaced (servers close idle ones)


def _net_ssl():
    global _SSL
    with _SSL_LOCK:
        if _SSL is None:
            import ssl
            try:
                import certifi
                _SSL = ssl.create_default_context(cafile=certifi.where())
            except Exception:  # noqa: BLE001
                _SSL = ssl.create_default_context()
        return _SSL


def _connection(timeout: float):
    """This thread's open connection to the server (made when needed)."""
    import http.client
    from urllib.parse import urlsplit
    conn = getattr(_NET, "conn", None)
    if conn is not None and (getattr(_NET, "url", "") != API_URL or time.monotonic() - getattr(_NET, "used", 0.0) > _IDLE_S):
        conn.close()
        conn = None
    if conn is None:
        import urllib.request
        u = urlsplit(API_URL)
        port = u.port or (443 if u.scheme == "https" else 80)
        proxy = urllib.request.getproxies().get(u.scheme)            # the same proxy settings urllib used
        if proxy and urllib.request.proxy_bypass(u.hostname or ""):
            proxy = None
        if proxy:
            pu = urlsplit(proxy if "://" in proxy else "http://" + proxy)
            head = {}
            if pu.username:
                from urllib.parse import unquote
                auth = base64.b64encode(f"{unquote(pu.username)}:{unquote(pu.password or '')}".encode()).decode()
                head["Proxy-Authorization"] = "Basic " + auth
            if u.scheme == "https":
                conn = http.client.HTTPSConnection(pu.hostname, pu.port or 8080, timeout=timeout, context=_net_ssl())
            else:
                conn = http.client.HTTPConnection(pu.hostname, pu.port or 8080, timeout=timeout)
            conn.set_tunnel(u.hostname, port, headers=head)
        elif u.scheme == "https":
            conn = http.client.HTTPSConnection(u.hostname, port, timeout=timeout, context=_net_ssl())
        else:
            conn = http.client.HTTPConnection(u.hostname, port, timeout=timeout)
        _NET.conn, _NET.url, _NET.fresh = conn, API_URL, True
        _NET.base = u.path.rstrip("/")
    else:
        _NET.fresh = False
    conn.timeout = timeout
    if conn.sock is not None:
        conn.sock.settimeout(timeout)
    return conn


def _drop_connection() -> None:
    conn = getattr(_NET, "conn", None)
    if conn is not None:
        conn.close()
    _NET.conn = None


def _request(path: str, body=None, token: str = "", method: str = "POST", timeout: float = 12.0):
    """One call to the server. Returns the decoded answer; raises ApiError('offline' | a server message)."""
    import http.client
    if Net.blocked:                                   # offline mode: nothing leaves the PC
        raise ApiError("offline")
    headers = {"apikey": API_KEY, "Content-Type": "application/json", "User-Agent": "Rubenium",
               "Connection": "keep-alive"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None if body is None else json.dumps(body).encode("utf-8")
    for attempt in (0, 1):
        try:
            conn = _connection(timeout)
            reused = not _NET.fresh
            conn.request(method, _NET.base + path, body=data, headers=headers)
            r = conn.getresponse()
            raw = r.read()
            status = r.status
            _NET.used = time.monotonic()
            if r.getheader("Connection", "").lower() == "close":
                _drop_connection()
        except (http.client.RemoteDisconnected, BrokenPipeError, ConnectionResetError) as exc:
            _drop_connection()
            # A kept-alive connection the server had already closed: the request never reached it, so it is
            # safe to send it once more on a new connection. Anything else is reported, never sent twice.
            if attempt == 0 and reused:
                continue
            raise ApiError("offline") from exc
        except Exception as exc:  # noqa: BLE001  (no internet, DNS, timeout...)
            _drop_connection()
            raise ApiError("offline") from exc
        if status >= 400:
            try:
                info = json.loads(raw.decode("utf-8"))
            except Exception:  # noqa: BLE001
                info = {}
            if not isinstance(info, dict):
                info = {}
            text = " ".join(str(info.get(k, "")) for k in ("error_code", "code", "msg", "message", "error_description"))
            raise ApiError(text.strip() or f"http {status}", status)
        try:
            return json.loads(raw.decode("utf-8")) if raw else None
        except ValueError as exc:
            raise ApiError("offline") from exc
    raise ApiError("offline")


class _NetPool:
    """A few daemon threads that do the server calls in order of arrival (daemon: closing Rubenium never waits
    for a slow network)."""

    def __init__(self, n: int) -> None:
        import queue
        self.q = queue.Queue()
        for i in range(n):
            threading.Thread(target=self._run, name=f"rb-net-{i}", daemon=True).start()

    def _run(self) -> None:
        while True:
            job = self.q.get()
            try:
                job()
            except Exception:  # noqa: BLE001
                log.exception("network job failed")

    def submit(self, job) -> None:
        self.q.put(job)


_POOL = None


def net_pool() -> _NetPool:
    global _POOL
    if _POOL is None:
        _POOL = _NetPool(6)
    return _POOL


def public_file(path: str) -> str:
    """The download address of a public file in Supabase Storage."""
    return API_URL + "/storage/v1/object/public/" + path


def download(url: str, timeout: float = 120.0) -> bytes:
    if Net.blocked:
        raise ApiError("offline")
    import ssl
    import urllib.request
    try:
        import certifi
        sc = ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001
        sc = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"apikey": API_KEY, "User-Agent": "Rubenium"})
    with urllib.request.urlopen(req, timeout=timeout, context=sc if url.startswith("https") else None) as r:  # noqa: S310
        return r.read()


def explain(err: ApiError) -> str:
    """A server or network error as a short sentence for the login screen (English key for tr())."""
    text = (err.key or "").lower()
    if text == "offline":
        return "No internet connection"
    if "pgrst202" in text or "could not find the function" in text or ("function" in text and "does not exist" in text):
        return "Coming very soon: the server is being updated"
    if "rb_no_such_user" in text:
        return "No user with this name"
    if "rb_thats_you" in text:
        return "That is you"
    if "rb_friends_only" in text:
        return "Friends only"
    if "rb_too_many" in text:
        return "Your friends list is full"
    if "rb_device_used" in text:
        return "This PC already has an account"
    if "rb_update_needed" in text:
        return "Update Rubenium first"
    if "rb_banned" in text:
        return "This account is blocked"
    if "rb_slow_down" in text:
        return "Slow down a little"
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


def pc_id() -> str:
    """One fixed id for this PC (a fingerprint of the Windows install: no personal data). The server allows
    one account per PC."""
    import hashlib
    raw = ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            raw = str(winreg.QueryValueEx(key, "MachineGuid")[0])
    except Exception:  # noqa: BLE001
        raw = os.environ.get("RUBENIUM_PC", "") or str(uuid.getnode())
    return hashlib.sha256(("rubenium-pc:" + raw).encode()).hexdigest()[:40]


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
    beat = pyqtSignal(dict)                   # the server's answer to a heartbeat (balance, time)
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
        self._back.connect(_run_back)
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
            login = username.lower()
            try:                                             # after a name change the account keeps its first login name
                first = _request("/rest/v1/rpc/rb_login_for", {"name": username}, timeout=8)
                if isinstance(first, str) and first:
                    login = first
            except ApiError as err:
                if err.key == "offline":
                    raise
            ans = _request("/auth/v1/token?grant_type=password", {"email": login + MAIL, "password": password})
            return lambda: self._adopt(ans)
        self._run("login", job)

    def sign_up(self, username: str, password: str) -> None:
        if self.busy:
            return
        self.busy = True

        def job():
            pc = pc_id()
            try:
                free = _request("/rest/v1/rpc/rb_device_free", {"pc": pc}, timeout=8) or {}
            except ApiError as err:
                if err.key == "offline":
                    raise
                free = {}
            if free.get("free") is False:
                raise ApiError("rb_device_used")
            try:
                ans = _request("/auth/v1/signup", {"email": username.lower() + MAIL, "password": password,
                                                   "data": {"username": username, "device": pc}})
            except ApiError as err:
                if "database error" in (err.key or "").lower():     # the server refused: almost always the PC rule
                    raise ApiError("rb_device_used") from None
                raise
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
        if Net.blocked:                                # logging out leaves offline mode (the login needs the internet)
            Net.blocked = False
            self.ctx.cfg["offline_mode"] = False
            token = ""
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
        if not self.s.get("refresh_token"):
            raise ApiError("offline")
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

    def in_background(self, job, done) -> None:
        """Run job() off the main thread; done(ok, answer or message) comes back on the main thread."""
        def work():
            try:
                ans = job()
                self._back.emit(lambda: done(True, ans))
            except ApiError as err:
                msg = explain(err) if err.key != "offline" else "No internet connection"
                self._back.emit(lambda: done(False, msg))
            except Exception as exc:  # noqa: BLE001
                log.exception("background job failed")
                text = str(exc) or "Something went wrong: try again"
                self._back.emit(lambda: done(False, text))
        threading.Thread(target=work, daemon=True).start()

    def make_bot(self, name: str, password: str, ticket: str, done) -> None:
        """Admin: create a bot account with the normal sign up (so it can be logged into), without leaving
        the admin account."""
        def job():
            ans = _request("/auth/v1/signup", {"email": name.lower() + MAIL, "password": password,
                                               "data": {"username": name, "device": "bot:" + ticket}})
            if not ans or not ans.get("access_token"):
                raise ApiError("email not confirmed")
            return True
        self.in_background(job, done)

    def upload(self, path: str, data: bytes, kind: str, done) -> None:
        """Admin: put a file in Supabase Storage (bucket path like "swaps/<id>/file")."""
        def job():
            import ssl
            import urllib.error
            import urllib.request
            try:
                import certifi
                sc = ssl.create_default_context(cafile=certifi.where())
            except Exception:  # noqa: BLE001
                sc = ssl.create_default_context()
            req = urllib.request.Request(API_URL + "/storage/v1/object/" + path, data=data, method="POST",
                                         headers={"apikey": API_KEY, "Authorization": "Bearer " + self._token(),
                                                  "Content-Type": kind, "x-upsert": "true", "User-Agent": "Rubenium"})
            try:
                with urllib.request.urlopen(req, timeout=120, context=sc if API_URL.startswith("https") else None) as r:  # noqa: S310
                    r.read()
            except urllib.error.HTTPError as exc:
                raise ApiError(f"upload failed ({exc.code})", exc.code) from None
            except Exception as exc:  # noqa: BLE001
                raise ApiError("offline") from exc
            return True
        self.in_background(job, done)

    def rpc(self, name: str, args: dict):
        """Call a server function as the logged-in account. Off the main thread only."""
        return _request("/rest/v1/rpc/" + name, args, self._token())

    def ask(self, fn: str, args: dict, done, raw: bool = False) -> None:
        """Call a server function for the logged-in account; `done(ok, answer or message)` runs on the main thread."""
        def emit(job) -> None:
            try:
                self._back.emit(job)
            except RuntimeError:                    # Rubenium is closing: nobody is waiting for the answer
                pass

        def work():
            try:
                ans = self.rpc(fn, args)
                if self.offline:
                    emit(lambda: self._set_offline(False))
                emit(lambda: done(True, ans))
            except ApiError as err:
                msg = err.key if (raw and err.key != "offline") else explain(err)
                if err.key == "offline":
                    emit(lambda: self._set_offline(True))
                emit(lambda: done(False, msg))
            except Exception:  # noqa: BLE001
                log.exception("%s failed", fn)
                emit(lambda: done(False, "Something went wrong: try again"))
        net_pool().submit(work)

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
        if not hasattr(self, "_retry"):
            self._retry = QTimer(self)
            self._retry.setInterval(20000)
            self._retry.timeout.connect(self.probe)
        if off and Net.blocked:
            self._retry.stop()                   # offline mode: no point asking
        elif off and not self._retry.isActive():
            self._retry.start()                  # offline mode: try again every 20 seconds, quietly
        elif not off:
            self._retry.stop()

    def change_password(self, new: str, done) -> None:
        """The logged-in account gets a new password (after the admin gave a temporary one, say)."""
        def work():
            try:
                _request("/auth/v1/user", {"password": new}, self._token(), method="PUT")
                self._back.emit(lambda: done(True, ""))
            except ApiError as err:
                msg = explain(err)
                self._back.emit(lambda: done(False, msg))
            except Exception:  # noqa: BLE001
                log.exception("password change failed")
                self._back.emit(lambda: done(False, "Something went wrong: try again"))
        threading.Thread(target=work, daemon=True).start()

    def ask_reset(self, name: str, message: str, done) -> None:
        """Forgot the password: a request for the admin (works without logging in)."""
        def work():
            try:
                rid = _request("/rest/v1/rpc/rb_reset_ask", {"name": name, "pc": pc_id(), "msg": message})
                self._back.emit(lambda: done(True, rid))
            except ApiError as err:
                msg = explain(err)
                self._back.emit(lambda: done(False, msg))
            except Exception:  # noqa: BLE001
                log.exception("reset ask failed")
                self._back.emit(lambda: done(False, "Something went wrong: try again"))
        threading.Thread(target=work, daemon=True).start()

    def reset_status(self, rid: str, done) -> None:
        def work():
            try:
                ans = _request("/rest/v1/rpc/rb_reset_status", {"rid": rid, "pc": pc_id()})
                self._back.emit(lambda: done(True, ans))
            except Exception:  # noqa: BLE001
                self._back.emit(lambda: done(False, None))
        threading.Thread(target=work, daemon=True).start()

    def probe(self) -> None:
        """Is the internet back? One small question to the server."""
        if self.logged_in() and not Net.blocked:
            self.ask("rb_timers", {}, lambda _ok, _d: None)

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
        self.beat.emit(ans)
