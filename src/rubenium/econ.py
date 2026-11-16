"""The online economy as the app sees it: a copy of what the server says (coins, keys, items, what is worn).

Nothing is decided here. Every action is a request to the server; the answer is what gets shown."""
import json
import logging
import threading
import uuid

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .core import DATA_DIR

log = logging.getLogger("rubenium.econ")

MYTHICS = ("galaxy", "phoenix", "glitch", "crystal", "dragon", "rubenium")
TIERS = ["standard", "rare", "special", "epic", "exotic"]
RARITY_NAMES = {"standard": "Common", "rare": "Rare", "special": "Epic", "epic": "Legendary", "exotic": "Mythic"}
CLASS_NAMES = ["Basic", "Painted", "Shiny", "Titanium", "Gold", "Prismatic"]
CLASS_COLOURS = ["#9AA4AD", "#6FB7FF", "#FF7AD9", "#E6EEF5", "#FFC94D", "#C38BFF"]
RARITY_COLOURS = {"standard": "#9AA4AD", "rare": "#4FA8FF", "special": "#B36BFF", "epic": "#FF5CC8",
                  "exotic": "#FFC94D"}
ERRORS = {"rb_not_enough": "Not enough coins", "rb_not_for_sale": "This is not for sale",
          "rb_already_owned": "You already have it", "rb_not_yours": "You do not have this",
          "rb_item_locked": "This item is in a trade", "rb_not_tradeable": "This cannot be sold",
          "rb_too_soon": "Not ready yet", "rb_bad_bet": "Bet between 10 and 1 000",
          "rb_round_open": "Finish your round first", "rb_already_worn": "Already on show",
          "rb_nothing_to_collect": "Nothing to collect", "rb_not_done": "Not finished yet",
          "rb_already_claimed": "Already claimed", "rb_trade_locked": "Unlocks after 5 hours with Rubenium",
          "rb_they_cannot_trade": "This user needs 5 hours with Rubenium first",
          "rb_bad_price": "This price is too low or too high", "rb_too_many_listings": "You have too many items on sale",
          "rb_not_listed": "No longer on sale", "rb_sold": "Already sold", "rb_own_listing": "This is your own item",
          "rb_trade_gone": "This trade is over", "rb_trade_changed": "The offer changed: look again",
          "rb_not_ready": "Both users must be ready", "rb_wait": "Wait for the countdown",
          "rb_too_many_trades": "Too many open trades", "rb_bad_offer": "This offer is not possible",
          "rb_round_gone": "This round is over", "rb_too_early": "Too early: wait for x1.20",
          "rb_gift_limit": "3 gifts a day at most", "rb_friends_only": "Friends only",
          "rb_no_such_user": "No user with this name", "rb_thats_you": "That is you",
          "rb_giveaway_over": "This giveaway is over", "rb_giveaway_hours": "You need more hours to join",
          "rb_rename_wait": "One name change every 24 hours", "rb_username_taken": "This username is taken",
          "rb_bad_username": "3 to 10 letters or numbers", "rb_same_name": "That is already your name",
          "rb_bad_picture": "This picture cannot be used", "rb_not_admin": "Admin only",
          "rb_banned": "This account is blocked", "rb_bad_choice": "This is not possible", "rb_no_case": "No such case",
          "rb_update_needed": "Update Rubenium to keep playing online", "rb_app_locked": "Rubenium is locked for now",
          "rb_not_friends": "Friends only", "rb_duel_gone": "This duel is over", "rb_already_played": "You already played this duel",
          "rb_too_many": "Too many at once: wait a little", "rb_slow_down": "Slow down a little",
          "rb_already_undone": "Already undone", "rb_cant_undo": "This cannot be undone",
          "rb_weak_password": "8 characters at least", "rb_too_big": "Too big",
          "rb_server_old": "Coming very soon: the server is being updated"}


def server_missing(data) -> bool:
    """The server does not have this yet (its update was not run): not a real error."""
    text = str(data).lower()
    return ("pgrst202" in text or "could not find the function" in text or "rb_server_old" in text
            or "server is being updated" in text or ("function" in text and "does not exist" in text))


class Econ(QObject):
    changed = pyqtSignal()          # coins, keys, items or what is worn changed
    loaded = pyqtSignal()           # the first full answer from the server arrived
    live_changed = pyqtSignal()     # giveaways, sales or trade requests changed
    looks_changed = pyqtSignal()    # someone changed their banner, frame or tag

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
        self.admin = False
        self.holding = False
        self.avatar_v = 0
        self.stock: dict = {}                    # case id -> gifted cases waiting
        self.scratch_in = 0                      # seconds until the next scratch card
        self.server_old = False                  # the server has not had the 2.4 update yet
        self.streak, self.streak_day = 0, None
        self.looks: dict = {}                    # username -> {tag, frame, banner} for everyone (2.6)
        self._looks_at = 0.0
        self.gold_keys = 0                       # OG event keys (3.0.0)
        self.wear_data: dict = {}                   # your banners: item -> {minutes, level, steps} (3.0.0 gold banners)
        self.live: dict = {}                     # giveaways, sales, trade requests (asked every 20 s)
        self._live_sig = ""
        self._live_timer = QTimer(self)
        self._live_timer.setInterval(4000)                 # 3.0.0: trades, invites and gifts show within seconds
        self._live_timer.timeout.connect(self.poll_live)
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

    def secret(self, item: str) -> bool:
        """A Mythic badge this account never had: it stays a "?" everywhere."""
        parts = (item or "").split(":")
        if len(parts) < 2 or parts[0] != "badge" or parts[1] not in MYTHICS:
            return False
        head = f"badge:{parts[1]}:"
        return not any(s.startswith(head) for s in self.seen)

    def sale(self, item: str) -> int:
        """Percent off in the shop right now (0 = no sale)."""
        best = 0
        for s in self.live.get("sales") or []:
            what = str(s.get("what", ""))
            if item == what or item.startswith(what + ":"):
                best = max(best, int(s.get("pct", 0)))
        return best

    def shop_price(self, item: str):
        price = self.price(item)
        if price is None:
            return None
        return max(1, -(-int(price) * (100 - self.sale(item)) // 100))

    def can_trade(self) -> bool:
        return self.minutes >= int(self.cfg.get("trade_min_minutes", 300))

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
        return max(1, int(int(info.get("value", 0)) * float(self.cfg.get("vendor_share", 0.25))))

    def unlocked(self, prog: str) -> bool:
        """A progression item: unlocked by time played."""
        info = self.info(prog)
        return bool(info) and info.get("kind") == "prog" and int(info.get("value", 0)) <= self.minutes

    def can_wear(self, item: str) -> bool:
        if self.owns(item) or self.unlocked(item):
            return True
        if item.startswith("badge:") and item.endswith(":grey"):     # Basic comes with any colour of the badge
            head = item[:-4]
            return any(k.startswith(head) for k in self._owned)
        return False

    def worn(self, slot: str) -> str:
        return str(self.equip.get(slot, "") or "")

    def badges_worn(self) -> list:
        """What is on show. Something sold, traded or taken away is never shown, even before the server says so."""
        return [self.worn(s) for s in ("badge1", "badge2", "badge3") if self.worn(s) and (not self.ready or self.can_wear(self.worn(s)))]

    def look_of(self, name: str) -> dict:
        """The tag, frame and banner someone shows. Yours comes from what you wear right now."""
        if name and self.ready and name.lower() == (self.online.username() or "").lower():
            mine = {k: self.worn(k) for k in ("tag", "frame", "banner") if self.worn(k) and self.can_wear(self.worn(k))}
            if mine.get("banner") and self.gold_of(mine["banner"]):
                mine["gold"] = self.gold_of(mine["banner"])
            return mine
        return self.looks.get(name) or {}

    def streak_bonus(self) -> int:
        """3.1: every day of the login streak adds coins to the AFK pay (up to 20 days)."""
        per = int(self.cfg.get("streak_coin", 0) or 0)
        if not per or not self.streak or not self.streak_day:
            return 0
        import datetime
        try:
            day = datetime.date.fromisoformat(str(self.streak_day)[:10])
        except ValueError:
            return 0
        if (datetime.date.today() - day).days > 1:
            return 0
        return per * min(int(self.streak), int(self.cfg.get("streak_coin_days", 20) or 20))

    def gold_of(self, item: str) -> int:
        """How gold one of your banners is (0-3), from the hours you wore it."""
        try:
            level = int((self.wear_data.get(item) or {}).get("level") or 0)
            pick = self.worn("banner_gold")
            return max(0, min(3, level, int(pick) if str(pick).isdigit() else 3))
        except (TypeError, ValueError):
            return 0

    def fetch_wear(self) -> None:
        def got(ok: bool, data) -> None:
            if ok and isinstance(data, dict) and data != self.wear_data:
                self.wear_data = data
                self.looks_changed.emit()
        self.online.ask("rb_wear_mine", {}, got)

    def fetch_looks(self, force: bool = False) -> None:
        import time
        if not self.online.logged_in() or (not force and time.monotonic() - self._looks_at < 40):
            return
        self._looks_at = time.monotonic()
        self.fetch_wear()

        def got(ok: bool, data) -> None:
            if ok and isinstance(data, dict) and data != self.looks:
                self.looks = data
                self.looks_changed.emit()
        self.online.ask("rb_looks", {}, got)

    def quick_ready(self) -> bool:
        """Quick sell needs the 2.6 server update."""
        return "quick_share" in self.cfg

    def worth(self, item: str) -> int:
        """What an item is worth, the same everywhere (and the same rule as the server): its shop price when the shop
        sells it; Titanium and Gold badges 50 x their value; Mythic badges 400 x their value."""
        info = self.info(item)
        if not info:
            return 0
        if info.get("price"):
            return int(info["price"])
        v = int(info.get("value") or 0)
        if info.get("kind") == "badge":
            if info.get("rarity") == "exotic":
                return v * 400
            if int(info.get("cls") or 0) >= 3:
                return v * 50
        return v

    def quick_value(self, item: str) -> int:
        """About what quick sell pays for one (the server decides; shop items can pay less)."""
        info = self.info(item)
        if not info or not info.get("tradeable") or info.get("kind") in ("prog", "tag"):
            return 0
        pay = int(info.get("value") or 0) * float(self.cfg.get("quick_share", 0.25))
        if info.get("kind") == "badge":
            pay = max(pay, self.worth(item) * float(self.cfg.get("quick_worth_share", 0) or 0))
        return max(1, int(pay))

    def quick_quote(self, ids: list, done) -> None:
        self.online.ask("rb_quick_quote", {"ids": list(ids)}, lambda ok, d: done(ok, d))

    def quick_sell(self, ids: list, done=None) -> None:
        def back(ok: bool, data) -> None:
            if ok:
                gone = set(ids)
                self.items = [i for i in self.items if i["id"] not in gone]
                self._index()
            if done:
                done(ok, data)
        self.call("rb_quick_sell", {"ids": list(ids)}, back, once=True)

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
            from .online import pc_id
            from .core import build_number

            def hello(ok: bool, data) -> None:
                if not ok:                                   # a server without 2.4: the old hello
                    if server_missing(data):
                        self.server_old = True
                        self.changed.emit()
                    return self.online.ask("rb_hello", {"pc": pc_id()}, lambda _ok, _d: None)
                if self.server_old:
                    self.server_old = False
                    self.changed.emit()
                if isinstance(data, dict) and hasattr(self.ctx, "set_outdated"):
                    self.ctx.set_outdated(bool(data.get("update")))
            self.online.ask("rb_hello2", {"pc": pc_id(), "build": build_number()}, hello)
            self.refresh()
            self.fetch_catalog()
            self._live_timer.start()
            QTimer.singleShot(2500, self.poll_live)
        elif not now_in and self._was_in:
            self.ready = False
            self._live_timer.stop()
            self.live, self.admin, self.stock, self.looks, self.wear_data = {}, False, {}, {}, {}
            self.live_changed.emit()
            self.coins = self.keys = self.minutes = 0
            self.items, self.seen, self.equip, self._owned = [], set(), {}, {}
            self.changed.emit()
        self._was_in = now_in

    def refresh(self) -> None:
        if self.online.logged_in():
            if not self.ready:
                self._load_cache()
            self.online.ask("rb_state", {}, self._state)

    # offline mode: the last answer is kept on disk, so coins and items still show without internet
    def _load_cache(self) -> None:
        try:
            data = json.loads((DATA_DIR / "state_cache.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(data, dict) and data.get("username") == self.online.username():
            self.items = list(data.get("items") or [])
            self.seen = set(data.get("seen") or [])
            self._index()
            self.absorb(data)
            self.changed.emit()

    def _save_cache(self, data: dict) -> None:
        try:
            tmp = DATA_DIR / "state_cache.json.tmp"
            tmp.write_text(json.dumps(data), encoding="utf-8")
            tmp.replace(DATA_DIR / "state_cache.json")
        except OSError:
            pass

    def _state(self, ok: bool, data) -> None:
        if not ok or not isinstance(data, dict):
            return QTimer.singleShot(15000, self.refresh) if not self.ready else None
        self._save_cache(data)
        first = not self.ready
        self.ready = True
        self.minutes = int(data.get("minutes", 0))
        self.day_coins = int(data.get("day_coins", 0))
        self.imported = bool(data.get("imported", True))
        self.admin = bool(data.get("admin"))
        self.avatar_v = int(data.get("avatar_v") or 0)
        self.stock = dict(data.get("stock") or {})
        self.scratch_in = int(data.get("scratch_in") or 0)
        self.streak = int(data.get("streak") or 0)
        self.streak_day = data.get("streak_day")
        self.items = list(data.get("items") or [])
        self.seen = set(data.get("seen") or [])
        self._index()
        self.absorb(data)
        self.fetch_gold_keys()
        if first:
            if hasattr(self.ctx, "check_gold_wheels"):
                QTimer.singleShot(3000, self.ctx.check_gold_wheels)
            self.loaded.emit()
            if hasattr(self.ctx, "after_login"):
                QTimer.singleShot(1200, self.ctx.after_login)
        self.changed.emit()

    def fetch_gold_keys(self) -> None:
        """Gold keys (OG event): one use each, spent before normal keys. Nothing on an older server."""
        def got(ok: bool, data) -> None:
            if ok and isinstance(data, int) and data != self.gold_keys:
                self.gold_keys = data
                self.changed.emit()
        self.online.ask("rb_gold_keys", {}, got)

    def poll_live(self) -> None:
        if not self.online.logged_in():
            return

        def got(ok: bool, data) -> None:
            if not ok or not isinstance(data, dict):
                return
            notes = data.pop("notices", None) or []
            before = (self.coins, self.keys)
            self.absorb(data)
            sig = json.dumps([data.get("giveaways"), data.get("sales"), data.get("trades"), data.get("asks"),
                              data.get("open_trade")], sort_keys=True, default=str)
            self.live = data
            if notes:
                self.refresh()
                for n in notes:
                    try:
                        self.ctx.notice(n.get("kind", ""), n.get("data") or {})
                    except Exception:  # noqa: BLE001
                        log.exception("notice failed")
            if sig != self._live_sig:
                self._live_sig = sig
                self.live_changed.emit()
            if before != (self.coins, self.keys):
                self.changed.emit()
        self.online.ask("rb_live", {}, got, raw=True)
        self.fetch_looks()

    def _index(self) -> None:
        self._owned = {}
        for it in self.items:
            self._owned.setdefault(it["item"], []).append(it["id"])

    def absorb(self, ans) -> None:
        """Take the balance (and what is worn) from any server answer."""
        if not isinstance(ans, dict):
            return
        for key in ("coins", "keys", "coin_min", "key_min", "minutes"):
            if self.holding and key in ("coins", "keys"):          # a case strip is still turning: no spoilers
                continue
            if ans.get(key) is not None:
                setattr(self, key, int(ans[key]))
        if isinstance(ans.get("equip"), dict):
            self.equip = dict(ans["equip"])

    def _beat(self, ans: dict) -> None:
        before = (self.coins, self.keys, self.minutes)
        self.absorb(ans)
        if before != (self.coins, self.keys, self.minutes):
            self.changed.emit()

    def adjust(self, coins: int = 0, keys: int = 0) -> None:
        """Change the balance on screen (a bet leaving, a prize landing): the server already did it for real."""
        self.coins = max(0, self.coins + int(coins))
        self.keys = max(0, self.keys + int(keys))
        self.changed.emit()

    def call(self, fn: str, args: dict, done=None, once: bool = False, hold: bool = False) -> None:
        """Ask the server to do something. `done(ok, answer or message)` runs on the main thread, after the
        balance in the answer was taken. `once` adds an id so a resend can never be done twice."""
        if once:
            args = dict(args, req=uuid.uuid4().hex)

        def back(ok: bool, data) -> None:
            if ok and not hold:                 # hold: the game shows the result first, then the coins
                self.absorb(data)
            if not ok and server_missing(data):  # the app is newer than the server: say it once, calmly
                self.server_old = True
                data = "rb_server_old"
            if not ok:
                data = ERRORS.get(next((k for k in ERRORS if k in str(data)), ""),
                                  "No internet connection" if data == "offline" else "Something went wrong: try again")
            if done is not None:
                done(ok, data)
            if ok and not hold:
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
                catalog = {r["id"]: {k: r.get(k) for k in ("kind", "base", "variant", "rarity", "price", "value", "tradeable", "cls")}
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
