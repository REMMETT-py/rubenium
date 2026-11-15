"""Coins: earned by time (25 every 15 minutes Rubenium is running), spent in the shop and the games.

The wallet is kept apart from the settings, signed with a key tied to this PC, and stored twice (a file and the
registry): editing it by hand, copying it from another PC or deleting one copy does not work. The daily spin
uses the date from the internet, not the PC clock.
"""
import base64
import hashlib
import hmac
import json
import logging
import math
import os
import random
import threading
import time

from PyQt6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF

from . import extras, win
from .core import DATA_DIR

log = logging.getLogger("rubenium.wallet")

DROP_S = 15 * 60            # a coin drop every 15 minutes...
DROP_COINS = 25             # ...of 25 coins (100 an hour)
COINS_PER_HOUR = 100
DAILY_WAIT_S = 20 * 3600    # the free daily spin comes back after 20 hours
ADMIN_COINS = 999_999

# Sixteen colours, white and black included. White is the free base colour.
COLOURS = [("white", "White", "#FFFFFF"), ("black", "Black", "#3A3F46"), ("red", "Red", "#FF4B4B"),
           ("orange", "Orange", "#FF8A3D"), ("amber", "Amber", "#FFB020"), ("yellow", "Yellow", "#FFE14D"),
           ("lime", "Lime", "#A6E22E"), ("green", "Green", "#2ECC71"), ("teal", "Teal", "#1ABC9C"),
           ("cyan", "Cyan", "#35D6E6"), ("sky", "Sky", "#2D9CFF"), ("blue", "Blue", "#4B6BFF"),
           ("purple", "Purple", "#9B5CFF"), ("magenta", "Magenta", "#D94BFF"), ("pink", "Pink", "#FF5CB8"),
           ("rose", "Rose", "#FF6F91")]
COLOUR_HEX = {ident: hexa for ident, _name, hexa in COLOURS}
C1_PRICE, C2_PRICE = 100, 100
MUSIC_S = 3600              # the music's colours open after 1 hour with Rubenium (free, not bought)
KEY_EVERY = 1000            # a key for every 1 000 coins played in the casino...
KEY_MAX = 10                # ...and never more than 10 keys at once

# --------------------------------------------------------------------------- #
# Badges: 50 designs, each in 17 colours of four rarities
# --------------------------------------------------------------------------- #
BADGES = [("star", "Star"), ("bolt", "Bolt"), ("flame", "Flame"), ("heart", "Heart"), ("sun", "Sun"),
          ("moon", "Moon"), ("clover", "Clover"), ("drop", "Droplet"), ("leaf", "Leaf"), ("note", "Note"),
          ("gamepad", "Gamepad"), ("dice", "Dice"), ("ghost", "Ghost"), ("alien", "Alien"), ("mushroom", "Mushroom"),
          ("cherry", "Cherry"), ("cube", "Cube"), ("headset", "Headset"), ("spade", "Spade"), ("club", "Club"),
          ("cat", "Cat"), ("paw", "Paw"), ("fish", "Fish"), ("feather", "Feather"), ("wing", "Wing"),
          ("tree", "Tree"), ("mountain", "Mountain"), ("wave", "Wave"), ("snowflake", "Snowflake"), ("eye", "Eye"),
          ("sword", "Sword"), ("axe", "Axe"), ("shield", "Shield"), ("skull", "Skull"), ("bomb", "Bomb"),
          ("crosshair", "Crosshair"), ("target", "Target"), ("shuriken", "Shuriken"), ("trident", "Trident"),
          ("anchor", "Anchor"),
          ("crown", "Crown"), ("trophy", "Trophy"), ("diamond", "Diamond"), ("gem", "Gem"), ("rocket", "Rocket ship"),
          ("planet", "Planet"), ("comet", "Comet"), ("key", "Key"), ("rook", "Rook"), ("hourglass", "Hourglass")]
BADGE_NAME = dict(BADGES)
RARITIES = [("basic", "Basic", "#9AA4AD"), ("rare", "Rare", "#4FA8FF"), ("very", "Very rare", "#C77DFF"),
            ("super", "Super rare", "#E8C26A")]
RARITY_COLOUR = {k: c for k, _n, c in RARITIES}
RARITY_NAME = {k: n for k, n, _c in RARITIES}
# (id, name, rarity, main colour, light colour)
VARIANTS = [("gold", "Gold", "super", "#E8C26A", "#FFF1C2"),
            ("titanium", "Titanium White", "very", "#EEF1F4", "#FFFFFF"),
            ("black", "Black", "very", "#16191C", "#5A626B"),
            ("lava", "Lava Red", "rare", "#FF3D1F", "#FFB199"),
            ("purple", "Rich Purple", "rare", "#A43DFF", "#E2B8FF"),
            ("sky", "Sky Blue", "rare", "#2EC5FF", "#B8EEFF"),
            ("lime", "Juicy Lime", "rare", "#8CFF2E", "#DDFFB8"),
            ("pink", "Hot Pink", "rare", "#FF2E9A", "#FFB8DD"),
            ("beam", "Yellow Beam", "rare", "#FFEE2E", "#FFFBC2"),
            ("blue", "Blue", "basic", "#4A6FB8", "#7F9DD6"),
            ("green", "Green", "basic", "#4C8A5A", "#7DB389"),
            ("red", "Red", "basic", "#A84444", "#CC7676"),
            ("yellow", "Yellow", "basic", "#B89B42", "#D6BE76"),
            ("orange", "Orange", "basic", "#B8703A", "#D69B6E"),
            ("brown", "Brown", "basic", "#7A5A40", "#A0826A"),
            ("grey", "Grey", "basic", "#7A828A", "#A2A9B0"),
            ("teal", "Teal", "basic", "#3C8C8A", "#71B3B1")]
VARIANT = {v[0]: v for v in VARIANTS}
RARITY_ORDER = {"super": 0, "very": 1, "rare": 2, "basic": 3}
# Cases: each holds 10 badges. Odds are out of 10 000 for (basic, rare, very rare, super rare).
CASES = [dict(id="street", name="Street Case", price=200, basic=200, odds=(8200, 1500, 270, 30),
              colour="#7FA3B8", badges=["star", "bolt", "flame", "heart", "sun", "moon", "clover", "drop", "leaf", "note"]),
         dict(id="arcade", name="Arcade Case", price=400, basic=300, odds=(8000, 1650, 310, 40),
              colour="#4FA8FF", badges=["gamepad", "dice", "ghost", "alien", "mushroom", "cherry", "cube", "headset",
                                        "spade", "club"]),
         dict(id="wild", name="Wild Case", price=600, basic=400, odds=(7900, 1700, 350, 50),
              colour="#4CC98A", badges=["cat", "paw", "fish", "feather", "wing", "tree", "mountain", "wave",
                                        "snowflake", "eye"]),
         dict(id="warrior", name="Warrior Case", price=900, basic=600, odds=(7700, 1850, 390, 60),
              colour="#FF5C4D", badges=["sword", "axe", "shield", "skull", "bomb", "crosshair", "target", "shuriken",
                                        "trident", "anchor"]),
         dict(id="royal", name="Royal Case", price=1500, basic=800, odds=(7400, 2050, 470, 80),
              colour="#E8C26A", badges=["crown", "trophy", "diamond", "gem", "rocket", "planet", "comet", "key",
                                        "rook", "hourglass"])]
CASE_OF = {b: c for c in CASES for b in c["badges"]}
# A badge you already have is turned into coins: this share of the case price (never more than the case cost).
DUPLICATE = {"basic": 0.25, "rare": 1.0, "very": 3.0, "super": 10.0}


def variants_of(rarity: str) -> list:
    return [v for v in VARIANTS if v[2] == rarity]


def badge_price(ident: str) -> int:
    """Price of one basic colour of a badge (rare colours only come from cases)."""
    return int(CASE_OF[ident]["basic"])


FREE = {"theme:clean", "r:classic", "ring:dots", "c1:white"}


def _build_catalog() -> dict:
    """Every item of the shop: {id: dict(kind, name, price, needs)}. `needs` is the item to own first."""
    items: dict = {}
    prev = None
    for th in extras.THEMES:                              # themes are bought in order
        ident = f"theme:{th['id']}"
        items[ident] = dict(kind="theme", name=th["name"], price=th["hours"] * 2 * COINS_PER_HOUR, needs=prev)
        prev = ident
    for kind, styles in (("r", extras.R_STYLES), ("ring", extras.RING_STYLES)):
        for st in styles:
            items[f"{kind}:{st['id']}"] = dict(kind=kind, name=st["name"], price=st["hours"] * 2 * COINS_PER_HOUR,
                                               needs=None)
    for ident, name, _hexa in COLOURS:
        items[f"c1:{ident}"] = dict(kind="c1", name=name, price=0 if ident == "white" else C1_PRICE, needs=None)
        items[f"c2:{ident}"] = dict(kind="c2", name=name, price=C2_PRICE, needs="c1:*")
    return items


CATALOG = _build_catalog()


def coins_text(n: int) -> str:
    return f"{int(n):,}".replace(",", " ")


# --------------------------------------------------------------------------- #
# Signing and storage
# --------------------------------------------------------------------------- #
_SALT = b"rubenium/wallet/2/a81c4e07d3f95b26"     # 1.4: a fresh start for everyone


def _machine() -> str:
    if win.IS_WIN:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                                winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                return str(winreg.QueryValueEx(key, "MachineGuid")[0])
        except OSError:
            pass
    return os.environ.get("COMPUTERNAME", "") or "this-pc"


def _key() -> bytes:
    return hashlib.sha256(_SALT + _machine().encode("utf-8", "ignore")).digest()


def _pack(data: dict) -> str:
    body = base64.b64encode(json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")).decode("ascii")
    return body + "." + hmac.new(_key(), body.encode("ascii"), hashlib.sha256).hexdigest()


def _unpack(text: str):
    """The wallet stored in `text`, or None if it is not ours or was changed."""
    try:
        body, sig = text.strip().rsplit(".", 1)
        if not hmac.compare_digest(sig, hmac.new(_key(), body.encode("ascii"), hashlib.sha256).hexdigest()):
            return None
        data = json.loads(base64.b64decode(body).decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _file():
    return DATA_DIR / "wallet2.dat"


def _read_file() -> str:
    try:
        return _file().read_text(encoding="ascii")
    except (OSError, UnicodeError):
        return ""


def _read_registry() -> str:
    if not win.IS_WIN:
        return ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Rubenium") as key:
            return str(winreg.QueryValueEx(key, "Wallet2")[0])
    except OSError:
        return ""


def _write(text: str) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _file().with_suffix(".tmp")
        tmp.write_text(text, encoding="ascii")
        os.replace(tmp, _file())
    except OSError as exc:
        log.debug("wallet file: %s", exc)
    if win.IS_WIN:
        try:
            import winreg
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Rubenium") as key:
                winreg.SetValueEx(key, "Wallet2", 0, winreg.REG_SZ, text)
        except OSError as exc:
            log.debug("wallet registry: %s", exc)


def internet_time(timeout: float = 4.0):
    """The current time (seconds since 1970) from the internet, or None when offline. Used for the daily spin,
    so changing the PC clock does nothing."""
    import urllib.request
    from email.utils import parsedate_to_datetime
    for url in ("https://www.google.com", "https://www.cloudflare.com", "https://api.github.com"):
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Rubenium"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                stamp = resp.headers.get("Date")
            if stamp:
                return parsedate_to_datetime(stamp).timestamp()
        except Exception:  # noqa: BLE001
            continue
    return None


# --------------------------------------------------------------------------- #
# The wallet
# --------------------------------------------------------------------------- #
class Wallet(QObject):
    changed = pyqtSignal()
    dropped = pyqtSignal(int)           # coins just earned by time
    time_checked = pyqtSignal()         # the internet date arrived (or failed)

    def __init__(self, cfg) -> None:
        super().__init__()
        self.cfg = cfg
        self.admin = False              # test mode: endless coins, everything open, nothing is kept
        self.tampered = False
        self.net_offset = None          # internet time minus PC time, once known
        self._checking = False
        self._dirty = False
        self.d = self._load()
        self._last = time.monotonic()
        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._second)
        self._saver = QTimer(self)
        self._saver.setInterval(60000)
        self._saver.timeout.connect(self.save)

    # -- loading
    def _blank(self) -> dict:
        return {"v": 2, "coins": 0, "owned": [], "progress": 0.0, "daily": 0.0, "seq": 0, "warned": False,
                "won": 0, "lost": 0, "inv": [], "keys": 0, "kprog": 0.0, "played": 0.0, "opened": 0, "pending": 0}

    def _load(self) -> dict:
        texts = [t for t in (_read_file(), _read_registry()) if t]
        valid = [d for d in (_unpack(t) for t in texts) if d]
        if valid:
            data = max(valid, key=lambda d: int(d.get("seq", 0)))
            base = self._blank()
            base.update(data)
            base["coins"] = max(0, int(base["coins"]))
            for old, new in extras.RETIRED_STYLES.items():          # removed styles: owners get the new one
                for kind in ("r", "ring"):
                    if f"{kind}:{old}" in base["owned"] and f"{kind}:{new}" not in base["owned"]:
                        base["owned"].append(f"{kind}:{new}")
            base["owned"] = [str(i) for i in base["owned"] if str(i) in CATALOG]
            base["inv"] = [str(i) for i in base["inv"] if self._valid_badge(str(i))]
            base["keys"] = max(0, min(KEY_MAX, int(base["keys"])))
            if int(base.get("pending", 0)) > 0:          # coins from a duplicate whose case was still opening
                base["coins"] += int(base["pending"])
                base["pending"] = 0
                self._dirty = True
            return base
        data = self._blank()
        if texts:                                   # a wallet exists but it was changed by hand: start again
            self.tampered = True
            log.warning("wallet did not pass its check: starting from zero")
        self._dirty = True
        return data

    @staticmethod
    def _valid_badge(item: str) -> bool:
        ident, _s, var = item.partition("/")
        return ident in BADGE_NAME and var in VARIANT

    def start(self) -> None:
        self._last = time.monotonic()
        self._clock.start()
        self._saver.start()
        if self._dirty:
            self.save()

    def stop(self) -> None:
        self._clock.stop()
        self._saver.stop()
        self.save()

    def save(self) -> None:
        if self.admin or not self._dirty:
            return
        self.d["seq"] = int(self.d.get("seq", 0)) + 1
        _write(_pack(self.d))
        self._dirty = False

    # -- earning by time
    def _second(self) -> None:
        now = time.monotonic()
        step, self._last = now - self._last, now
        if step <= 0 or step > 5 or self.admin:         # the PC slept: that time does not count
            return
        before = float(self.d.get("played", 0.0))
        self.d["played"] = before + step
        if before < MUSIC_S <= self.d["played"]:
            self.changed.emit()
        self.d["progress"] = float(self.d["progress"]) + step
        self._dirty = True
        if self.d["progress"] >= DROP_S:
            self.d["progress"] -= DROP_S
            self.d["coins"] += DROP_COINS
            self.save()
            self.dropped.emit(DROP_COINS)
            self.changed.emit()

    def next_drop(self) -> int:
        """Seconds until the next coin drop."""
        return max(0, int(math.ceil(DROP_S - float(self.d["progress"]))))

    # -- coins
    def balance(self) -> int:
        return ADMIN_COINS if self.admin else int(self.d["coins"])

    def spend(self, n: int) -> bool:
        """Take n coins. False (and nothing happens) when there are not enough: no debt, ever."""
        n = int(n)
        if n < 0 or n > self.balance():
            return False
        if not self.admin:
            self.d["coins"] -= n
            self.d["lost"] = int(self.d.get("lost", 0)) + n
            self._dirty = True
            self.save()
        self.changed.emit()
        return True

    def add(self, n: int) -> None:
        n = max(0, int(n))
        if n and not self.admin:
            self.d["coins"] += n
            self.d["won"] = int(self.d.get("won", 0)) + n
            self._dirty = True
            self.save()
        self.changed.emit()

    # -- the shop
    def owns(self, ident: str) -> bool:
        return self.admin or self.really_owns(ident)

    def really_owns(self, ident: str) -> bool:
        """Owned for real (not through test mode): what is kept when Rubenium restarts."""
        if ident == "music":
            return float(self.d.get("played", 0.0)) >= MUSIC_S
        return ident in FREE or ident in self.d["owned"]

    def music_wait(self) -> int:
        """Seconds of Rubenium still needed before the music's colours open."""
        return 0 if self.owns("music") else max(0, int(math.ceil(MUSIC_S - float(self.d.get("played", 0.0)))))

    def all_colours(self, kind: str) -> bool:
        return all(self.owns(f"{kind}:{ident}") for ident, _n, _h in COLOURS)

    def price(self, ident: str) -> int:
        return int(CATALOG[ident]["price"])

    def blocked_by(self, ident: str) -> str:
        """'' when the item can be bought now, else the id of what has to be owned first ('c1:*' = every
        first colour)."""
        needs = CATALOG[ident]["needs"]
        if needs == "c1:*":
            return "" if self.all_colours("c1") else "c1:*"
        return "" if (not needs or self.owns(needs)) else needs

    def buy(self, ident: str) -> bool:
        if ident not in CATALOG or self.owns(ident) or self.blocked_by(ident):
            return False
        price = self.price(ident)
        if price > self.balance():
            return False
        if not self.admin:
            self.d["coins"] -= price
            self.d["owned"].append(ident)
            self._dirty = True
            self.save()
        self.changed.emit()
        return True

    # -- casino keys
    def keys(self) -> int:
        return 99 if self.admin else int(self.d["keys"])

    def key_progress(self) -> float:
        """0..1 towards the next key (1 when the key holder is full)."""
        if self.keys() >= KEY_MAX:
            return 1.0
        return max(0.0, min(1.0, float(self.d["kprog"]) / KEY_EVERY))

    def bet(self, n: int) -> bool:
        """A casino bet: taken like any spend, and it counts towards the next key."""
        if not self.spend(n):
            return False
        if not self.admin and int(self.d["keys"]) < KEY_MAX:
            self.d["kprog"] = float(self.d["kprog"]) + int(n)
            while self.d["kprog"] >= KEY_EVERY and int(self.d["keys"]) < KEY_MAX:
                self.d["kprog"] -= KEY_EVERY
                self.d["keys"] = int(self.d["keys"]) + 1
            if int(self.d["keys"]) >= KEY_MAX:
                self.d["kprog"] = 0.0
            self._dirty = True
            self.save()
            self.changed.emit()
        return True

    def add_keys(self, n: int) -> None:
        if not self.admin:
            self.d["keys"] = min(KEY_MAX, int(self.d["keys"]) + max(0, int(n)))
            self._dirty = True
            self.save()
        self.changed.emit()

    # -- badges
    def has_badge(self, ident: str, var: str) -> bool:
        return self.admin or f"{ident}/{var}" in self.d["inv"]

    def really_has_badge(self, ident: str, var: str) -> bool:
        return f"{ident}/{var}" in self.d["inv"]

    def badge_variants(self, ident: str) -> list:
        """The colours of a badge you own, rarest first."""
        if self.admin:
            return [v[0] for v in VARIANTS]
        have = {i.split("/", 1)[1] for i in self.d["inv"] if i.startswith(ident + "/")}
        return [v[0] for v in VARIANTS if v[0] in have]

    def badge_total(self) -> int:
        return len(BADGES) * len(VARIANTS) if self.admin else len(self.d["inv"])

    def buy_badge(self, ident: str, var: str) -> bool:
        """Basic colours can be bought; rarer ones only come from cases."""
        if ident not in BADGE_NAME or var not in VARIANT or VARIANT[var][2] != "basic" or self.has_badge(ident, var):
            return False
        price = badge_price(ident)
        if price > self.balance():
            return False
        if not self.admin:
            self.d["coins"] -= price
            self.d["inv"].append(f"{ident}/{var}")
            self._dirty = True
            self.save()
        self.changed.emit()
        return True

    def open_case(self, case_id: str):
        """Open a case: costs its price and one key. Returns dict(badge, var, rarity, new, refund) or None."""
        case = next((c for c in CASES if c["id"] == case_id), None)
        if case is None or self.keys() < 1 or case["price"] > self.balance():
            return None
        rng = random.SystemRandom()
        roll = rng.randrange(10000)
        rarity = "super"
        for kind, share in zip(("basic", "rare", "very", "super"), case["odds"]):
            if roll < share:
                rarity = kind
                break
            roll -= share
        ident = rng.choice(case["badges"])
        var = rng.choice(variants_of(rarity))[0]
        new = not self.really_has_badge(ident, var)
        refund = 0 if new else int(case["price"] * DUPLICATE[rarity])
        if not self.admin:
            self.d["coins"] -= case["price"]
            self.d["keys"] = int(self.d["keys"]) - 1
            self.d["opened"] = int(self.d.get("opened", 0)) + 1
            if new:
                self.d["inv"].append(f"{ident}/{var}")
            self.d["pending"] = int(self.d.get("pending", 0)) + refund     # paid when the case shows it
            self._dirty = True
            self.save()
        self.changed.emit()
        return dict(badge=ident, var=var, rarity=rarity, new=new, refund=refund)

    def pay_refund(self) -> int:
        """Coins for duplicates, paid when the case animation shows them (or at the next start)."""
        n = int(self.d.get("pending", 0))
        if n > 0 and not self.admin:
            self.d["coins"] += n
            self.d["pending"] = 0
            self._dirty = True
            self.save()
        self.changed.emit()
        return n

    # -- gambling warning
    def warned(self) -> bool:
        return bool(self.d.get("warned"))

    def accept_warning(self) -> None:
        self.d["warned"] = True
        self._dirty = True
        self.save()

    # -- daily spin (internet date only)
    def check_time(self) -> None:
        if self._checking:
            return
        self._checking = True

        def work() -> None:
            stamp = internet_time()
            if stamp is not None:                                # counted on from here with a clock the PC date cannot move
                self.net_offset = stamp - time.monotonic()
            self._checking = False
            try:
                self.time_checked.emit()
            except RuntimeError:
                pass
        threading.Thread(target=work, daemon=True).start()

    def checking(self) -> bool:
        return self._checking

    def daily_wait(self):
        """Seconds until the daily spin is free again (0 = ready), or None while the date is not known."""
        if self.net_offset is None:
            return None
        now = time.monotonic() + self.net_offset
        return max(0, int(math.ceil(float(self.d["daily"]) + DAILY_WAIT_S - now)))

    def claim_daily(self, coins: int, keys: int = 0) -> bool:
        """Mark today's free spin as used and pay its prize at once (so closing Rubenium mid-spin loses nothing)."""
        if self.daily_wait() != 0:
            return False
        if not self.admin:
            self.d["daily"] = time.monotonic() + self.net_offset
            self.d["coins"] += max(0, int(coins))
            self.d["keys"] = min(KEY_MAX, int(self.d["keys"]) + max(0, int(keys)))
            self._dirty = True
            self.save()
        self.changed.emit()
        return True


# --------------------------------------------------------------------------- #
# Small pictures: the coin and the badges
# --------------------------------------------------------------------------- #
def paint_coin(p: QPainter, c: QPointF, r: float) -> None:
    p.save()
    p.setPen(QPen(QColor("#B8862B"), max(1.0, r * 0.14)))
    p.setBrush(QColor("#E8C26A"))
    p.drawEllipse(c, r, r)
    p.setPen(QPen(QColor("#FFF1C2"), max(1.0, r * 0.16)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(c.x() - r * 0.55, c.y() - r * 0.55, r * 1.1, r * 1.1), 100 * 16, 110 * 16)
    p.restore()
