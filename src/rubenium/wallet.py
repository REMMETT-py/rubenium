"""What the rest of the app asks about coins and unlocks. Since 2.0 everything is decided by the server
(see econ.py); this file is the small bridge the screens use, plus the names of badges and colours."""
from PyQt6.QtCore import QObject, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen

from . import extras

# Sixteen colours, white and black included. White is the free base colour.
COLOURS = [("white", "White", "#FFFFFF"), ("black", "Black", "#3A3F46"), ("red", "Red", "#FF4B4B"),
           ("orange", "Orange", "#FF8A3D"), ("amber", "Amber", "#FFB020"), ("yellow", "Yellow", "#FFE14D"),
           ("lime", "Lime", "#A6E22E"), ("green", "Green", "#2ECC71"), ("teal", "Teal", "#1ABC9C"),
           ("cyan", "Cyan", "#35D6E6"), ("sky", "Sky", "#2D9CFF"), ("blue", "Blue", "#4B6BFF"),
           ("purple", "Purple", "#9B5CFF"), ("magenta", "Magenta", "#D94BFF"), ("pink", "Pink", "#FF5CB8"),
           ("rose", "Rose", "#FF6F91")]
COLOUR_HEX = {ident: hexa for ident, _name, hexa in COLOURS}

# --------------------------------------------------------------------------- #
# Badges: 12 Common, 12 Rare, 12 Epic, 12 Legendary (in this order), then the 6 Mythic ones
# --------------------------------------------------------------------------- #
BADGES = [("heart", "Heart"), ("drop", "Droplet"), ("clover", "Clover"), ("paw", "Paw Print"), ("cat", "Cat"),
          ("fish", "Fish"), ("cherry", "Cherries"), ("feather", "Feather"), ("note", "Music Note"), ("dice", "Dice"),
          ("headset", "Headphones"), ("gamepad", "Game Controller"),
          ("mushroom", "Mushroom"), ("tree", "Tree"), ("wave", "Wave"), ("ghost", "Ghost"), ("spade", "Spade"),
          ("club", "Club"), ("diamond", "Diamond"), ("eye", "Eye"), ("snowflake", "Snowflake"),
          ("mountain", "Mountain"), ("moon", "Moon"), ("sun", "Sun"),
          ("star", "Star"), ("bolt", "Lightning Bolt"), ("flame", "Flame"), ("anchor", "Anchor"), ("key", "Key"),
          ("pickaxe", "Pickaxe"), ("rook", "Rook"), ("shield", "Shield"), ("sword", "Sword"), ("skull", "Skull"),
          ("trident", "Trident"), ("quill", "Quill"),
          ("hourglass", "Hourglass"), ("target", "Target"), ("comet", "Comet"), ("saturn", "Saturn"),
          ("alien", "Alien"), ("rocket", "Rocket ship"), ("shootingstar", "Shooting Star"), ("planet", "Planet"),
          ("crown", "Crown"), ("trophy", "Trophy"), ("goldenstar", "Golden Star"), ("sunburst", "Sunburst Star")]
EXOTICS = [("galaxy", "Galaxy"), ("phoenix", "Phoenix"), ("glitch", "Glitch"), ("crystal", "Crystal Heart"),
           ("dragon", "Dragon Eye"), ("rubenium", "Rubenium")]
BADGE_NAME = dict(BADGES + EXOTICS)
EXOTIC_IDS = tuple(b for b, _n in EXOTICS)
BADGE_ROWS = [("standard", [b for b, _n in BADGES[0:12]]), ("rare", [b for b, _n in BADGES[12:24]]),
              ("special", [b for b, _n in BADGES[24:36]]), ("epic", [b for b, _n in BADGES[36:48]]),
              ("exotic", list(EXOTIC_IDS))]
# the colours of a badge, rarest first
GOLD_IDS = ["gold"]
TITANIUM_IDS = ["black", "white"]
SHINY_IDS = ["hotpink", "lime", "sky", "royal", "lava"]
PAINTED_IDS = ["red", "blue", "yellow", "green", "orange", "purple", "pink", "brown"]
# balls, lines and fonts of the shop come in these colours
COLOUR_IDS = ["blue", "green", "red", "yellow", "orange", "brown", "teal", "lava", "purple", "sky", "lime", "pink", "beam"]
PRESTIGE_IDS = ["black", "white", "gold"]
VARIANT_NAME = {"grey": "Basic", "blue": "Blue", "green": "Green", "red": "Red", "yellow": "Yellow", "orange": "Orange",
                "brown": "Brown", "teal": "Teal", "lava": "Lava Red", "purple": "Purple", "sky": "Sky Blue",
                "lime": "Juicy Lime", "pink": "Pink", "beam": "Yellow Beam", "black": "Titanium Black",
                "white": "Titanium White", "gold": "Gold", "prime": "Prismatic", "hotpink": "Hot Pink",
                "royal": "Rich Purple"}


def variants_for(base: str) -> list:
    """Every colour a badge exists in, best first."""
    if base in EXOTIC_IDS:
        return ["gold", "prime", "white", "black"]
    return GOLD_IDS + TITANIUM_IDS[::-1] + SHINY_IDS + PAINTED_IDS + ["grey"]


def badge_item(base: str, var: str) -> str:
    return f"badge:{base}:{var}"


def coins_text(n: int) -> str:
    return f"{int(n):,}".replace(",", " ")


def hours_label(hours: float) -> str:
    return f"{hours:g} h"


class Wallet(QObject):
    changed = pyqtSignal()
    dropped = pyqtSignal(int)
    time_checked = pyqtSignal()

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx, self.cfg, self.econ = ctx, ctx.cfg, ctx.econ
        self.admin = False
        self.econ.changed.connect(self.changed)
        ctx.online.changed.connect(self.changed)

    def start(self) -> None: ...

    def stop(self) -> None: ...

    # -- balance (from the server)
    def balance(self) -> int:
        return int(self.econ.coins)

    def keys(self) -> int:
        return int(self.econ.keys)

    def next_drop(self) -> int:
        return self.econ.next_coin_s()

    def minutes(self) -> int:
        return max(int(self.econ.minutes), int(self.ctx.online.minutes))

    # -- progression: themes, the R of the ball and its ring unlock with time played
    def hours_for(self, ident: str) -> float:
        kind, _s, value = ident.partition(":")
        styles = {"theme": extras.THEMES, "r": extras.R_STYLES, "ring": extras.RING_STYLES}.get(kind)
        if styles is None:
            return 0.0                                   # colours and the music's colours are free
        return next((float(st["hours"]) for st in styles if st["id"] == value), 1e9)

    def owns(self, ident: str) -> bool:
        value = ident.partition(":")[2]
        if value.split(":")[0] in ("ball", "line", "theme", "font"):       # bought in the shop, not unlocked by time
            return self.econ.owns(value) or not self.econ.ready
        return self.minutes() >= self.hours_for(ident) * 60

    really_owns = owns

    def all_colours(self, _kind: str) -> bool:
        return True

    def blocked_by(self, _ident: str) -> str:
        return ""

    def music_wait(self) -> int:
        return 0

    # -- the free spin (every 3 hours) and the daily case: when they are ready again
    spin_waiting = None                       # a prize that was rolled and not collected yet
    _spin_at = _daily_at = None
    _checking = False

    def check_time(self) -> None:
        if self._checking:
            return
        self._checking = True

        def got(ok: bool, data) -> None:
            import time
            self._checking = False
            if ok and isinstance(data, dict):
                now = time.monotonic()
                self._spin_at = now + int(data.get("spin") or 0)
                self._daily_at = now + int(data.get("daily") or 0)
                self.spin_waiting = data.get("spin_waiting")
            self.time_checked.emit()
        self.econ.call("rb_timers", {}, got)

    def checking(self) -> bool:
        return self._checking

    def daily_wait(self):
        """Seconds until the free spin (0 = ready, None = not known yet)."""
        import time
        return None if self._spin_at is None else max(0, int(self._spin_at - time.monotonic()))

    def spin_used(self) -> None:
        import time
        self._spin_at = time.monotonic() + float(self.econ.cfg.get("spin_hours", 2)) * 3600

    # -- the gambling warning (accepted once per PC)
    def warned(self) -> bool:
        return bool(self.cfg["casino_warned"])

    def accept_warning(self) -> None:
        self.cfg["casino_warned"] = True
        self.cfg.save()


def paint_coin(p: QPainter, c: QPointF, r: float) -> None:
    p.save()
    p.setPen(QPen(QColor("#B8862B"), max(1.0, r * 0.14)))
    p.setBrush(QColor("#E8C26A"))
    p.drawEllipse(c, r, r)
    p.setPen(QPen(QColor("#FFF1C2"), max(1.0, r * 0.16)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(c.x() - r * 0.55, c.y() - r * 0.55, r * 1.1, r * 1.1), 100 * 16, 110 * 16)
    p.restore()
