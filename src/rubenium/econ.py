"""The online economy as the app sees it: a copy of what the server says (coins, keys, items, what is worn).

Nothing is decided here. Every action is a request to the server; the answer is what gets shown."""
import json
import logging
import threading
import uuid

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .core import DATA_DIR

log = logging.getLogger("rubenium.econ")

TIERS = ["standard", "rare", "special", "epic", "exotic"]
RARITY_NAMES = {"standard": "Standard", "rare": "Rare", "special": "Special", "epic": "Epic", "exotic": "Exotic"}
RARITY_COLOURS = {"standard": "#9AA4AD", "rare": "#4FA8FF", "special": "#B36BFF", "epic": "#FF5CC8",
                  "exotic": "#FFC94D"}
ERRORS = {"rb_not_enough": "Not enough coins", "rb_not_for_sale": "This is not for sale",
          "rb_already_owned": "You already have it", "rb_not_yours": "You do not have this",
          "rb_item_locked": "This item is in a trade", "rb_not_tradeable": "This cannot be sold",
          "rb_too_soon": "Not ready yet", "rb_bad_bet": "Bet between 10 and 1 000",
          "rb_round_open": "Finish your round first", "rb_already_worn": "Already on show",
          "rb_nothing_to_collect": "Nothing to collect"}


class Econ(QObject):
    changed = pyqtSignal()          # coins, keys, items or what is worn changed
    loaded = pyqtSignal()           # the first full answer from the server arrived

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx, self.online = ctx, ctx.online
        self.ready = False
        self.coins = self.keys = self.minutes = 0
        self.coin_min = self.key_min = self.day_coins = 0
        self.items: list = []                    # [{id, item, locked, origin}]
        self.seen: set = set()                   # every item ever owned
        self.equip: dict = {}
        self.imported = True
        self.catalog: dict = {}                  # item id -> {kind, base, variant, rarity, price, value, tradeable}
        self.cases: list = []
        self.cfg: dict = {}
        self._owned: dict = {}                   # item id -> [instance ids]
        self._load_catalog_file()
        self.online.changed.connect(self._account)
        self.online.beat.connect(self._beat)
        self._was_in = False

    # -- what the app asks about
    def owns(self, item: str) -> bool:
        return item in self._owned

    def copies(self, item: str) -> list:
        return list(self._owned.get(item, ()))

    def had(self, item: str) -> bool:
        """Owned once, not any more (shown greyed out)."""
        return item in self.seen and item not in self._owned

    def info(self, item: str) -> dict:
        return self.catalog.get(item, {})

    def rarity(self, item: str) -> str:
        return self.info(item).get("rarity", "standard")

    def price(self, item: str):
        return self.info(item).get("price")

    def vendor_price(self, item: str) -> int:
        info = self.info(item)
        if not info or not info.get("tradeable"):
            return 0
        return max(1, int(int(info.get("value", 0)) * float(self.cfg.get("vendor_share", 0.45))))

    def unlocked(self, prog: str) -> bool:
        """A progression item: unlocked by time played."""
        info = self.info(prog)
        return bool(info) and info.get("kind") == "prog" and int(info.get("value", 0)) <= self.minutes

    def can_wear(self, item: str) -> bool:
        return self.owns(item) or self.unlocked(item)

    def worn(self, slot: str) -> str:
        return str(self.equip.get(slot, "") or "")

    def badges_worn(self) -> list:
        return [self.worn(s) for s in ("badge1", "badge2", "badge3") if self.worn(s)]

    def next_coin_s(self) -> int:
        every = int(self.cfg.get("coin_every_min", 15))
        return max(60, (every - self.coin_min) * 60)

    def next_key_s(self) -> int:
        every = int(self.cfg.get("key_every_min", 60))
        return max(60, (every - self.key_min) * 60)

    # -- talking to the server
    def start(self) -> None:
        self._account()

    def _account(self) -> None:
        now_in = self.online.logged_in()
        if now_in and not self._was_in:
            self.refresh()
            self.fetch_catalog()
        elif not now_in and self._was_in:
            self.ready = False
            self.coins = self.keys = self.minutes = 0
            self.items, self.seen, self.equip, self._owned = [], set(), {}, {}
            self.changed.emit()
        self._was_in = now_in

    def refresh(self) -> None:
        if self.online.logged_in():
            self.online.ask("rb_state", {}, self._state)

    def _state(self, ok: bool, data) -> None:
        if not ok or not isinstance(data, dict):
            return QTimer.singleShot(15000, self.refresh) if not self.ready else None
        first = not self.ready
        self.ready = True
        self.minutes = int(data.get("minutes", 0))
        self.day_coins = int(data.get("day_coins", 0))
        self.imported = bool(data.get("imported", True))
        self.items = list(data.get("items") or [])
        self.seen = set(data.get("seen") or [])
        self._index()
        self.absorb(data)
        if first:
            self.loaded.emit()
        self.changed.emit()

    def _index(self) -> None:
        self._owned = {}
        for it in self.items:
            self._owned.setdefault(it["item"], []).append(it["id"])

    def absorb(self, ans) -> None:
        """Take the balance (and what is worn) from any server answer."""
        if not isinstance(ans, dict):
            return
        for key in ("coins", "keys", "coin_min", "key_min", "minutes"):
            if ans.get(key) is not None:
                setattr(self, key, int(ans[key]))
        if isinstance(ans.get("equip"), dict):
            self.equip = dict(ans["equip"])

    def _beat(self, ans: dict) -> None:
        before = (self.coins, self.keys, self.minutes)
        self.absorb(ans)
        if before != (self.coins, self.keys, self.minutes):
            self.changed.emit()

    def call(self, fn: str, args: dict, done=None, once: bool = False) -> None:
        """Ask the server to do something. `done(ok, answer or message)` runs on the main thread, after the
        balance in the answer was taken. `once` adds an id so a resend can never be done twice."""
        if once:
            args = dict(args, req=uuid.uuid4().hex)

        def back(ok: bool, data) -> None:
            if ok:
                self.absorb(data)
            else:
                data = ERRORS.get(next((k for k in ERRORS if k in str(data)), ""),
                                  "No internet connection" if data == "offline" else "Something went wrong: try again")
            if done is not None:
                done(ok, data)
            if ok:
                self.changed.emit()
        self.online.ask(fn, args, back, raw=True)

    # -- actions
    def gained(self, item: str, instance: str, origin: str = "") -> None:
        """An item arrived (shop, case): put it in the local copy right away."""
        if item and instance and instance not in {i["id"] for i in self.items}:
            self.items.append({"id": instance, "item": item, "locked": None, "origin": origin})
            self.seen.add(item)
            self._index()

    def buy(self, item: str, done=None) -> None:
        def back(ok: bool, data) -> None:
            if ok:
                self.gained(data.get("item"), data.get("id"), "shop")
            if done:
                done(ok, data)
        self.call("rb_buy", {"what": item}, back, once=True)

    def sell(self, instance: str, done=None) -> None:
        def back(ok: bool, data) -> None:
            if ok:
                self.items = [i for i in self.items if i["id"] != instance]
                self._index()
            if done:
                done(ok, data)
        self.call("rb_sell", {"item_id": instance}, back, once=True)

    def wear(self, slot: str, item: str, done=None) -> None:
        def back(ok: bool, data) -> None:
            if ok and isinstance(data, dict):
                self.equip = dict(data)
            if done:
                done(ok, data)
        self.call("rb_equip", {"slot": slot, "what": item or ""}, back)

    # -- the catalogue (prices, rarities): fetched from the server, kept on disk between starts
    def _catalog_path(self):
        return DATA_DIR / "catalog.json"

    def _load_catalog_file(self) -> None:
        try:
            data = json.loads(self._catalog_path().read_text(encoding="utf-8"))
            self.catalog, self.cases, self.cfg = data["catalog"], data["cases"], data["cfg"]
        except Exception:  # noqa: BLE001
            pass

    def fetch_catalog(self) -> None:
        from .online import ApiError, _request

        def work():
            try:
                rows, offset = [], 0
                while True:                                   # the server gives at most 1 000 rows at a time
                    part = _request(f"/rest/v1/rb_catalog?select=*&order=id&limit=1000&offset={offset}", method="GET")
                    rows += part or []
                    if not part or len(part) < 1000:
                        break
                    offset += 1000
                cases = _request("/rest/v1/rb_cases?select=*&order=pos", method="GET") or []
                cfg = {r["key"]: r["value"] for r in (_request("/rest/v1/rb_config?select=*", method="GET") or [])}
                catalog = {r["id"]: {k: r[k] for k in ("kind", "base", "variant", "rarity", "price", "value", "tradeable")}
                           for r in rows}
                if catalog:
                    self.online._back.emit(lambda: self._got_catalog(catalog, cases, cfg))
            except ApiError:
                pass
            except Exception:  # noqa: BLE001
                log.exception("catalogue fetch failed")
        threading.Thread(target=work, daemon=True).start()

    def _got_catalog(self, catalog: dict, cases: list, cfg: dict) -> None:
        self.catalog, self.cases, self.cfg = catalog, cases, cfg
        try:
            path = self._catalog_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"catalog": catalog, "cases": cases, "cfg": cfg}), encoding="utf-8")
        except OSError:
            pass
        self.changed.emit()
