"""Shop > Shop, Inventory and Market, and the trade screen. Everything of value is done by the server: this file
only shows it and asks. An item in a trade or on the market is locked by the server until it is over."""
import math
import random
import time

from PyQt6.QtCore import QObject, QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from .collection import SLOTS, is_secret, worn
from .core import DANGER, S, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, mix, sfx, tr, ui
from .cosmetics import (BALLS, BANNERS, COLOUR_NAMES, COLOUR_ORDER, FONTS, FRAMES, LINES, THEME_LOOKS, colour_of, item_name,
                        paint_cosmetic)
from .econ import CLASS_NAMES, RARITY_COLOURS, RARITY_NAMES
from .shop import GOLD_TEXT, clock_text, paint_price
from .wallet import coins_text, paint_coin
from .widgets import present, close_embedded, lock_strip, refit_scroll, Tween, Button, IconButton, Label, Segmented, draw_icon, hbox, heading, vbox

KINDS = ["", "badge", "ball", "line", "font", "theme", "banner", "frame"]
LOOKS = ("banner", "frame", "tag")             # profile looks: worn on the server, seen by everyone
REASONS = {"time": "Time with Rubenium", "shop": "Shop", "vendor": "Sold to the vendor", "case": "Case opened",
           "case_coins": "Coins from a case", "daily_case": "Daily case", "spin": "Free spin", "bet": "Bet",
           "win": "Casino win", "quest": "Quest", "minigame": "Beat Tap", "market_buy": "Bought on the market",
           "market_sell": "Sold on the market", "trade": "Trade", "gift": "Case gifted", "giveaway": "Giveaway",
           "admin": "From the admin", "import": "Old progress", "quick_sell": "Quick sell", "reset": "Fresh start (2.6)"}


class AskDialog(QWidget):
    """A small window with one text box (typing needs the keyboard, which the menu never takes from a game)."""

    def __init__(self, ctx, title: str, hint: str, button: str, on_text, max_len: int = 10, note: str = "") -> None:
        super().__init__()
        from PyQt6.QtWidgets import QLineEdit
        from .window import work_area
        self._on_text = on_text
        self.ctx = ctx
        self.setWindowTitle("Rubenium")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedWidth(S(300))
        lay = vbox(self, 8, (18, 18, 18, 18))
        lay.addWidget(Label(title, 15, bold=True, wrap_w=S(264)))
        if note:
            lay.addWidget(Label(note, 11, TEXT_DIM, wrap_w=S(264)))
        self.edit = QLineEdit()
        self.edit.setMaxLength(max_len)
        self.edit.setPlaceholderText(hint)
        self.edit.setFixedHeight(S(34))
        self.edit.setStyleSheet(
            f"QLineEdit {{ background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.10);"
            f" border-radius: {S(9)}px; padding: 0 {S(10)}px; color: {TEXT}; font-size: {S(13)}px; }}"
            f"QLineEdit:focus {{ border: 1px solid rgba(255,255,255,0.45); }}")
        self.edit.returnPressed.connect(self._go)
        lay.addWidget(self.edit)
        self.note = Label("", 11, DANGER, wrap_w=S(264))
        self.note.setMinimumHeight(S(16))
        lay.addWidget(self.note)
        line = hbox(spacing=6)
        cancel = Button(tr("Cancel"), "ghost", 34)
        cancel.clicked.connect(self.close)
        go = Button(button, "primary", 34)
        go.clicked.connect(self._go)
        line.addWidget(cancel, 1)
        line.addWidget(go, 1)
        lay.addLayout(line)
        self.adjustSize()
        self.focus_me = self.edit.setFocus
        if present(self, ctx, keys=True):
            return
        area = work_area(ctx.window.card_global().center())
        self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()

    def close(self) -> bool:
        return close_embedded(self) or super().close()

    def say(self, text: str) -> None:
        self.note.set_text(text)

    def _go(self) -> None:
        text = self.edit.text().strip()
        if text:
            self._on_text(text, self)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.close()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(alpha(ui.accent, 0.45), 1.2))
        p.setBrush(QColor(12, 15, 16, 252))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), S(16), S(16))


def ask_number(ctx, title: str, hint: str, button: str, on_number, note: str = "") -> None:
    def got(text: str, dlg) -> None:
        digits = text.replace(" ", "")
        if not digits.isdigit():
            return dlg.say(tr("Numbers only"))
        on_number(int(digits), dlg)
    ctx._ask = AskDialog(ctx, title, hint, button, got, 9, note)


def rarity_line(ctx, item: str) -> str:
    info = ctx.econ.info(item)
    text = tr(RARITY_NAMES.get(info.get("rarity", "standard"), "Common"))
    if info.get("kind") == "badge" and int(info.get("cls") or 0):
        text += " · " + tr(CLASS_NAMES[int(info["cls"])])
    return text


def value_of(ctx, item: str) -> int:
    """What an item is worth, as shown everywhere (inventory, trades, collection)."""
    return ctx.econ.worth(item)


class ItemGrid(QWidget):
    """A grid of items (pictures with a line of text under them). Used by the shop, the inventory, the market
    and trades. entries: [{item, text, price, tag, mark, dim, empty}]"""
    picked = pyqtSignal(int)

    def __init__(self, ctx, entries: list, width: int, cols: int = 5, cell_h: int = 72, selected: int = -1,
                 moving: bool = True) -> None:
        super().__init__()
        self.ctx, self.entries, self.cols, self.selected = ctx, entries, cols, selected
        self.cw, self.ch = width / cols, S(cell_h)
        rows = max(1, (len(entries) + cols - 1) // cols)
        self.setFixedSize(width, int(rows * self.ch))
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = -1
        self._timer = QTimer(self)
        self._timer.setInterval(70)
        self._timer.timeout.connect(self.update)
        self._moving = moving and bool(entries)

    def showEvent(self, _e) -> None:
        if self._moving:
            self._timer.start()

    def hideEvent(self, _e) -> None:
        self._timer.stop()

    def _at(self, pos) -> int:
        i = int(pos.y() // self.ch) * self.cols + int(pos.x() // self.cw)
        return i if 0 <= i < len(self.entries) and 0 <= pos.x() < self.cols * self.cw else -1

    def mouseMoveEvent(self, e) -> None:
        i = self._at(e.position())
        if i != self._hover:
            self._hover = i
            item = self.entries[i].get("item") if i >= 0 else ""
            self.setToolTip(item_name(item) if item else "")
            self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = -1
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()
        i = self._at(e.position())
        if i >= 0 and e.button() == Qt.MouseButton.LeftButton and not self.entries[i].get("empty"):
            self.picked.emit(i)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        ec = self.ctx.econ
        for i, en in enumerate(self.entries):
            cell = QRectF((i % self.cols) * self.cw, (i // self.cols) * self.ch, self.cw, self.ch).adjusted(S(2), S(2), -S(2), -S(2))
            item = en.get("item", "")
            hov, sel = i == self._hover, i == self.selected
            if en.get("empty"):
                p.setPen(QPen(alpha("#FFFFFF", 0.10), 1, Qt.PenStyle.DashLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(cell, S(9), S(9))
                continue
            col = QColor(RARITY_COLOURS.get(ec.rarity(item), "#9AA4AD"))
            p.setPen(QPen(QColor("#FFFFFF") if sel else alpha(col, 0.5 + (0.3 if hov else 0.0)), S(1.6) if sel else 1.1))
            g = QLinearGradient(cell.topLeft(), cell.bottomLeft())
            g.setColorAt(0.0, QColor("#0E1316"))
            g.setColorAt(1.0, mix(QColor("#0E1316"), col, 0.16 + (0.08 if hov else 0.0)))
            p.setBrush(g)
            p.drawRoundedRect(cell, S(9), S(9))
            has_text = en.get("text") is not None or en.get("price") is not None
            size = min(cell.width() - S(18), cell.height() - (S(30) if has_text else S(14)))
            pic = QRectF(cell.center().x() - size / 2, cell.top() + S(7), size, size)
            paint_cosmetic(p, item, pic, now, effects=True, dim=float(en.get("dim", 1.0)))
            line = QRectF(cell.left() + S(2), cell.bottom() - S(19), cell.width() - S(4), S(16))
            if en.get("price") is not None:
                paint_price(p, line, en["price"], 9.5, GOLD_TEXT)
            elif en.get("text"):
                p.setPen(QColor(TEXT_DIM))
                f = font(9.5, QFont.Weight.DemiBold)
                p.setFont(f)
                text = p.fontMetrics().elidedText(en["text"], Qt.TextElideMode.ElideRight, int(line.width()))
                p.drawText(line, int(Qt.AlignmentFlag.AlignCenter), text)
            if en.get("tag", "").startswith("×"):                      # duplicates: a small x2 / x3 chip
                tag = "x" + en["tag"][1:]
                f = font(9, QFont.Weight.ExtraBold)
                tw = QFontMetrics(f).horizontalAdvance(tag) + S(10)
                chip = QRectF(cell.right() - tw - S(3), cell.top() + S(3), tw, S(15))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(ui.accent)
                p.drawRoundedRect(chip, S(7.5), S(7.5))
                p.setPen(QColor("#0B0E10") if ui.accent.lightnessF() > 0.55 else QColor("#FFFFFF"))
                p.setFont(f)
                p.drawText(chip, int(Qt.AlignmentFlag.AlignCenter), tag)
            elif en.get("tag"):
                p.setPen(QColor(TEXT))
                p.setFont(font(9, QFont.Weight.Bold))
                p.drawText(cell.adjusted(0, S(3), -S(5), 0), int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop), en["tag"])
            mark = en.get("mark", "")
            if mark == "worn":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(ui.accent)
                p.drawEllipse(QPointF(cell.left() + S(8), cell.top() + S(8)), S(3.2), S(3.2))
            elif mark == "lock":
                p.save()
                p.translate(cell.left() + S(10), cell.top() + S(10))
                p.scale(S(10) / 20, S(10) / 20)
                draw_icon(p, "lock", QColor(TEXT_DIM))
                p.restore()
            elif mark == "offered":                                    # 4.0: in the trade offer already
                c = QPointF(cell.left() + S(10), cell.top() + S(10))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#5BE08A"))
                p.drawEllipse(c, S(7), S(7))
                pen = QPen(QColor("#0B2614"), S(1.8))
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawPolyline([QPointF(c.x() - S(3.2), c.y()), QPointF(c.x() - S(0.8), c.y() + S(2.6)),
                                QPointF(c.x() + S(3.4), c.y() - S(2.6))])
            elif mark == "sale":
                tag = QRectF(cell.left() + S(3), cell.top() + S(3), S(30), S(14))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#FF4B6E"))
                p.drawRoundedRect(tag, S(7), S(7))
                p.setPen(QColor("#FFFFFF"))
                p.setFont(font(8.5, QFont.Weight.ExtraBold))
                p.drawText(tag, int(Qt.AlignmentFlag.AlignCenter), f"-{en.get('pct', 0)}%")


# --------------------------------------------------------------------------- #
# Special sale banner
# --------------------------------------------------------------------------- #
class SaleBanner(QWidget):
    """A sale chosen by the admin: big percentage, sparks rising, time left. Click to see the item."""

    def __init__(self, page, sale: dict) -> None:
        super().__init__()
        self.page, self.ctx, self.sale = page, page.ctx, sale
        self.setFixedHeight(S(66))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._until = time.monotonic() + int(sale.get("left") or 0)
        rnd = random.Random(str(sale.get("id")))
        self._sparks = [(rnd.random(), rnd.random(), rnd.uniform(0.25, 0.7), rnd.uniform(1.2, 2.6)) for _ in range(22)]
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self.update)

    def showEvent(self, _e) -> None:
        self._timer.start()

    def hideEvent(self, _e) -> None:
        self._timer.stop()

    def _item(self) -> str:
        """One item of the sale to show as its picture."""
        what = str(self.sale.get("what", ""))
        cat = self.ctx.econ.catalog
        if what in cat:
            return what
        return next((k for k in sorted(cat) if k.startswith(what + ":") and cat[k].get("price") is not None), what)

    def mousePressEvent(self, e) -> None:
        e.accept()
        bits = str(self.sale.get("what", "")).split(":")
        ctx = self.ctx
        if bits[0] == "badge" and len(bits) > 1:
            ctx.shop_tab, ctx.shop_badge = 2, bits[1]
        elif bits[0] in ("ball", "line", "font", "theme"):
            ctx.shop_tab, ctx.shop_kind = 1, ("ball", "line", "font", "theme").index(bits[0])
            ctx.shop_design = bits[1] if len(bits) > 1 else None
            ctx.shop_colour = bits[2] if len(bits) > 2 else ""
        sfx.play("pick")
        ctx.reload_page()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        bg = QLinearGradient(r.topLeft(), r.topRight())
        bg.setColorAt(0.0, QColor("#3A0E26"))
        bg.setColorAt(0.5, QColor("#2A1038"))
        bg.setColorAt(1.0, QColor("#10182E"))
        sweep = (now * 0.35) % 1.0
        edge = QLinearGradient(QPointF(r.left() + r.width() * (sweep * 2 - 0.5), r.top()),
                               QPointF(r.left() + r.width() * (sweep * 2), r.bottom()))
        edge.setColorAt(0.0, QColor("#FF4B6E"))
        edge.setColorAt(0.5, QColor("#FFE08A"))
        edge.setColorAt(1.0, QColor("#B36BFF"))
        edge.setSpread(QLinearGradient.Spread.ReflectSpread)
        p.setPen(QPen(edge, S(1.6)))
        p.setBrush(bg)
        p.drawRoundedRect(r, S(12), S(12))
        p.save()
        p.setClipRect(r)
        p.setPen(Qt.PenStyle.NoPen)
        for x, phase, size, speed in self._sparks:
            t = (now / speed + phase) % 1.0
            c = QColor.fromHsvF((0.92 + 0.2 * x) % 1.0, 0.55, 1.0)
            c.setAlphaF(math.sin(t * math.pi) * 0.85)
            p.setBrush(c)
            p.drawEllipse(QPointF(r.left() + x * r.width() + math.sin(now * 2 + phase * 9) * S(4), r.bottom() - t * r.height()),
                          S(size * 2.4), S(size * 2.4))
        p.restore()
        item = self._item()
        paint_cosmetic(p, item, QRectF(r.left() + S(10), r.top() + S(9), S(44), S(44)), now)
        pulse = 1.0 + 0.06 * math.sin(now * 5)
        p.setPen(QColor("#FFE08A"))
        f = font(22 * pulse, QFont.Weight.ExtraBold)
        p.setFont(f)
        p.drawText(QRectF(r.right() - S(96), r.top(), S(88), r.height()), int(Qt.AlignmentFlag.AlignCenter),
                   f"-{int(self.sale.get('pct', 0))}%")
        p.setPen(QColor("#FF9DB4"))
        p.setFont(font(9.5, QFont.Weight.ExtraBold, 1.2))
        p.drawText(QRectF(r.left() + S(64), r.top() + S(8), r.width() - S(170), S(14)), int(Qt.AlignmentFlag.AlignVCenter),
                   tr("SPECIAL SALE"))
        what = str(self.sale.get("what", ""))
        name = item_name(what) if what in self.ctx.econ.catalog else sale_title(what)
        p.setPen(QColor(TEXT))
        p.setFont(font(12.5, QFont.Weight.Bold))
        p.drawText(QRectF(r.left() + S(64), r.top() + S(23), r.width() - S(170), S(18)), int(Qt.AlignmentFlag.AlignVCenter),
                   p.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, int(r.width() - S(170))))
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10, QFont.Weight.DemiBold))
        left = max(0, int(self._until - now))
        p.drawText(QRectF(r.left() + S(64), r.top() + S(42), r.width() - S(170), S(14)), int(Qt.AlignmentFlag.AlignVCenter),
                   tr("Ends in {t}", t=clock_text(left)))


def sale_title(what: str) -> str:
    """A name for a sale on a whole group ("ball:orbit" = every colour of the Orbit ball)."""
    bits = what.split(":")
    group = {"ball": "Every ball", "line": "Every line", "font": "Every font", "theme": "Every theme",
             "badge": "Every Basic badge"}.get(bits[0], what)
    if len(bits) > 1:
        return item_name(what + ":").rstrip(" ·") + " · " + tr("every colour")
    return tr(group)


# --------------------------------------------------------------------------- #
# Shop > Shop: balls, lines, fonts, themes
# --------------------------------------------------------------------------- #
class Preview(QWidget):
    """The picked item, large and alive."""

    def __init__(self, ctx, item: str) -> None:
        super().__init__()
        self.ctx, self.item = ctx, item
        self.setFixedHeight(S(118))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self.update)

    def showEvent(self, _e) -> None:
        self._timer.start()

    def hideEvent(self, _e) -> None:
        self._timer.stop()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        col = QColor(RARITY_COLOURS.get(self.ctx.econ.rarity(self.item), "#9AA4AD"))
        g = QLinearGradient(r.topLeft(), r.bottomLeft())
        g.setColorAt(0.0, QColor("#0B0F11"))
        g.setColorAt(1.0, mix(QColor("#0B0F11"), col, 0.14))
        p.setPen(QPen(alpha(col, 0.4), 1.1))
        p.setBrush(g)
        p.drawRoundedRect(r, S(12), S(12))
        kind = self.item.split(":")[0]
        if kind == "font":
            from .cosmetics import font_families
            f = QFont()
            f.setFamilies(font_families(self.item) + ["Segoe UI", "Arial"])
            f.setPixelSize(S(24))
            f.setWeight(QFont.Weight.Bold)
            p.setFont(f)
            p.setPen(QColor("#AEB8C2") if self.item.endswith(":black") else colour_of(self.item))
            p.drawText(r.adjusted(0, S(14), 0, -S(44)), int(Qt.AlignmentFlag.AlignCenter), "Rubenium")
            f.setPixelSize(S(13))
            f.setWeight(QFont.Weight.Normal)
            p.setFont(f)
            p.setPen(QColor(TEXT_DIM))
            p.drawText(r.adjusted(0, S(62), 0, -S(12)), int(Qt.AlignmentFlag.AlignCenter), tr("Song title · Artist · 1:23"))
            return
        d = S(88)
        paint_cosmetic(p, self.item, QRectF(r.center().x() - d / 2, r.center().y() - d / 2, d, d), now)


def _designs(kind: str) -> list:
    return {"ball": BALLS, "line": LINES, "font": [(f[0], f[1]) for f in FONTS],
            "theme": [(t[0], t[1]) for t in THEME_LOOKS], "banner": BANNERS, "frame": FRAMES}[kind]


SHOP_KINDS = ("ball", "line", "font", "theme", "banner", "frame")


def _on_sale(ec, item: str) -> bool:
    """In the shop: sold right now (event items are not), or already yours."""
    return item in ec.catalog and (ec.catalog[item].get("price") is not None or ec.owns(item))


def _design_shown(ec, kind: str, base: str) -> bool:
    """A ball, line, font or theme design is in the shop when one of its colours is sold (limited ones: when yours)."""
    head = f"{kind}:{base}"
    return any((k == head or k.startswith(head + ":")) and (v.get("price") is not None or ec.owns(k))
               for k, v in ec.catalog.items())


def look_worn(ctx, item: str) -> bool:
    """A banner, frame or tag is worn on the server (everyone sees it)."""
    return ctx.econ.worn(item.split(":")[0]) == item


def wear_look(ctx, item: str, on: bool) -> None:
    kind = item.split(":")[0]

    def done(ok: bool, d) -> None:
        if not ok:
            ctx.toast(tr(str(d)), "warn")
        else:
            ctx.econ.looks_changed.emit()
        ctx.reload_page()
    if on and item == "frame:yuletide":           # 4.0: the advent frame rings its bells when you put it on
        sfx.tune("jingle")
    else:
        sfx.play("pick")
    ctx.econ.wear(kind, item if on else "", done)


def build_cosmetics(page, lay) -> None:
    ctx, ec = page.ctx, page.ctx.econ
    if not ec.ready or not ec.catalog:
        return lay.addWidget(Label(tr("Connecting…") if ctx.online.logged_in() else tr("Log in to see the shop"), 12, TEXT_DIM))
    from .games import GamePicker
    kind_i = min(int(getattr(ctx, "shop_kind", 0) or 0), len(SHOP_KINDS) - 1)
    kind = SHOP_KINDS[kind_i]
    design = getattr(ctx, "shop_design", None)
    if design is not None and kind in ("banner", "frame") and f"{kind}:{design}" not in ec.catalog:
        design = None
    if design is None:
        for sale in (ec.live.get("sales") or [])[:2]:
            lay.addWidget(SaleBanner(page, sale))
        seg = GamePicker([tr("Balls"), tr("Lines"), tr("Fonts"), tr("Themes"), tr("Banners"), tr("Frames")], kind_i)

        def switch(i: int) -> None:
            ctx.shop_kind = i
            ctx.shop_design = None
            ctx.reload_page()
        seg.changed.connect(switch)
        lay.addWidget(seg)
        if kind in ("banner", "frame"):
            if not any(k.startswith(kind + ":") for k in ec.catalog):         # the server has not had 2.6 yet
                from .hub import WaitCard
                return lay.addWidget(WaitCard(page.W))
            lay.addWidget(Label(tr("Visible on your profile, in lists and in chat."),
                                10.5, TEXT_DIM, wrap_w=page.W))
        entries = []
        for base, name in _designs(kind):
            if kind in ("banner", "frame") and not _on_sale(ec, f"{kind}:{base}"):
                continue
            if kind not in ("banner", "frame") and not _design_shown(ec, kind, base):
                continue
            item = f"{kind}:{base}" if kind in ("theme", "banner", "frame") else f"{kind}:{base}:{'white' if kind == 'font' else 'sky'}"
            cheapest = item if kind in ("theme", "banner", "frame") else f"{kind}:{base}:grey"
            owned = any(k.startswith(f"{kind}:{base}") for k in ec._owned)
            pct = max((ec.sale(k) for k in ec.catalog if k.startswith(f"{kind}:{base}")), default=0)
            entries.append({"item": item, "price": ec.shop_price(cheapest), "tag": tr(name),
                            "mark": "sale" if pct else ("worn" if owned else ""), "pct": pct})
        designs = [d for d in _designs(kind) if (_on_sale(ec, f"{kind}:{d[0]}") if kind in ("banner", "frame")
                                                 else _design_shown(ec, kind, d[0]))]
        if kind in ("banner", "frame"):                    # cheapest first: Common to Legendary
            order = sorted(range(len(entries)), key=lambda i: (entries[i]["price"] or 0, i))
            entries, designs = [entries[i] for i in order], [designs[i] for i in order]
        grid = ItemGrid(ctx, entries, page.W, 3 if kind in ("theme", "banner") else 4 if kind == "frame" else 5,
                        96 if kind in ("theme", "banner") else 86)

        def pick(i: int) -> None:
            sfx.play("pick")
            ctx.shop_design, ctx.shop_colour = designs[i][0], ""
            ctx.reload_page()
        grid.picked.connect(pick)
        lay.addWidget(grid)
        lay.addWidget(Label(tr("Every item can be worn, traded and sold."), 10.5,
                            TEXT_DIM, wrap_w=page.W))
        lay.addWidget(tax_explainer(ctx, page.W))
        return
    # one design: preview, colours, buy or wear
    names = dict(_designs(kind))
    variants = [""] if kind in ("theme", "banner", "frame") else [c for c in COLOUR_ORDER if f"{kind}:{design}:{c}" in ec.catalog]
    colour = getattr(ctx, "shop_colour", "") or ""
    if colour not in variants:
        colour = next((c for c in variants if ec.owns(_cid(kind, design, c))), variants[0] if variants else "")
    item = _cid(kind, design, colour)
    top = hbox(spacing=8)
    back = IconButton("back", 32, tip=tr("Back"))

    def leave() -> None:
        ctx.shop_design = None
        ctx.stop_preview()
        ctx.reload_page()
    back.clicked.connect(leave)
    top.addWidget(back)
    top.addWidget(Label(tr(names.get(design, design)), 15, bold=True), 1)
    top.addWidget(Label(rarity_line(ctx, item), 11, RARITY_COLOURS.get(ec.rarity(item), TEXT_DIM), bold=True))
    lay.addLayout(top)
    if kind in ("banner", "frame"):
        lay.addWidget(LookPreview(ctx, item, page.W))
    else:
        lay.addWidget(Preview(ctx, item))
    if kind == "theme":
        ctx.start_preview(item)
    if len(variants) > 1:
        lay.addWidget(Label(tr(COLOUR_NAMES.get(colour, colour)), 12, bold=True))
        entries = [{"item": _cid(kind, design, c), "mark": "worn" if ec.owns(_cid(kind, design, c)) else
                    ("sale" if ec.sale(_cid(kind, design, c)) else ""), "pct": ec.sale(_cid(kind, design, c))}
                   for c in variants]
        grid = ItemGrid(ctx, entries, page.W, 6, 52, variants.index(colour))

        def pick_colour(i: int) -> None:
            sfx.play("pick")
            ctx.shop_colour = variants[i]
            ctx.reload_page()
        grid.picked.connect(pick_colour)
        lay.addWidget(grid)
    price, full = ec.shop_price(item), ec.price(item)
    if ec.owns(item):
        on = look_worn(ctx, item) if kind in LOOKS else ctx.shop_item_worn(item)
        b = Button(tr("Take off") if on else tr("Wear"), "ghost" if on else "primary", 38)

        def toggle() -> None:
            if kind in LOOKS:
                return wear_look(ctx, item, not on)
            sfx.play("pick")
            ctx.take_off_shop_item(kind) if on else ctx.wear_shop_item(item)
            ctx.reload_page()
        b.clicked.connect(toggle)
        lay.addWidget(b)
        lay.addWidget(Label(tr("Sell it or put it on the market from your Inventory."), 10.5, TEXT_DIM, wrap_w=page.W))
    elif price is not None:
        text = tr("Buy for {n} coins", n=coins_text(price))
        if ec.sale(item):
            text += f"  (-{ec.sale(item)}%)"
        b = Button(text, "primary", 38)
        lay.addWidget(TaxNote(ctx, item, page.W))

        def buy() -> None:
            if price > ec.coins:
                return ctx.toast(tr("Not enough coins: {n} more needed", n=coins_text(price - ec.coins)), "warn")

            def done(ok: bool, data) -> None:
                if not ok:
                    sfx.play("off")
                    return ctx.toast(tr(str(data)), "warn")
                sfx.play("on")
                ctx.toast(tr("Bought: {what}", what=item_name(item)))
                ctx.reload_page()
            ctx.window.confirm(tr("Buy {name} for {n} coins?", name=item_name(item), n=coins_text(price)),
                               lambda: (b.setEnabled(False), ec.buy(item, done)), yes=tr("Buy"))
        b.clicked.connect(buy)
        lay.addWidget(b)


class TaxNote(QWidget):
    """3.2: why the shop costs more: worth (what players pay each other) + the shop tax = the shop price."""

    def __init__(self, ctx, item: str, width: int) -> None:
        super().__init__()
        self.ctx, self.item = ctx, item
        self.setFixedSize(width, S(54))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ec = self.ctx.econ
        worth, price = ec.worth(self.item), ec.shop_price(self.item) or 0
        tax = int(round(ec.tax() * 100))
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha(GOLD_TEXT, 0.3), 1))
        p.setBrush(alpha(GOLD_TEXT, 0.06))
        p.drawRoundedRect(r, S(10), S(10))
        third = r.width() / 3
        cells = [(tr("Worth"), coins_text(worth), TEXT), (tr("+{n}% shop tax", n=tax), coins_text(max(0, price - worth)), TEXT_DIM),
                 (tr("Shop price"), coins_text(price), GOLD_TEXT)]
        for i, (head, val, col) in enumerate(cells):
            box = QRectF(r.left() + i * third, r.top(), third, r.height())
            p.setPen(QColor(TEXT_DIM))
            p.setFont(font(9, QFont.Weight.DemiBold))
            p.drawText(QRectF(box.left(), box.top() + S(7), box.width(), S(14)), int(Qt.AlignmentFlag.AlignCenter), head)
            p.setPen(QColor(col))
            p.setFont(font(12.5, QFont.Weight.ExtraBold))
            p.drawText(QRectF(box.left(), box.top() + S(23), box.width(), S(22)), int(Qt.AlignmentFlag.AlignCenter), val)
            if i:
                p.setPen(QPen(alpha("#FFFFFF", 0.08), 1))
                p.drawLine(QPointF(box.left(), box.top() + S(8)), QPointF(box.left(), box.bottom() - S(8)))


def tax_explainer(ctx, width: int):
    """The one line that explains the two prices."""
    tax = int(round(ctx.econ.tax() * 100))
    return Label(tr("Buying from the shop adds a {n}% tax.", n=tax),
                 10, TEXT_DIM, wrap_w=width)


def _cid(kind: str, design: str, colour: str) -> str:
    return f"{kind}:{design}" if kind in ("theme", "banner", "frame") else f"{kind}:{design}:{colour}"


GOLD_STEPS = {"standard": (10, 30, 75), "rare": (15, 45, 110), "special": (25, 75, 180), "epic": (40, 120, 300)}


class LookPreview(QWidget):
    """How a banner or a frame looks on your own profile."""

    def __init__(self, ctx, item: str, width: int, note: str = "") -> None:
        super().__init__()
        self.ctx, self.item, self.note = ctx, item, note
        self.setFixedSize(width, S(118))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self.update)

    def showEvent(self, _e) -> None:
        self._timer.start()

    def hideEvent(self, _e) -> None:
        self._timer.stop()

    def paintEvent(self, _e) -> None:
        from .cosmetics import paint_banner
        from .friends import paint_face, paint_name_tags
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        now = time.monotonic()
        ec = self.ctx.econ
        name = self.ctx.online.username() or "Rubenium"
        kind = self.item.split(":")[0]
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha("#FFFFFF", 0.08), 1))
        p.setBrush(alpha("#FFFFFF", 0.04))
        p.drawRoundedRect(r, S(12), S(12))
        banner = self.item if kind == "banner" else ec.look_of(name).get("banner", "")
        top = QRectF(r.left(), r.top(), r.width(), S(74))
        if banner:
            paint_banner(p, top, banner, now, S(12), 1.0, ec.gold_of(banner))
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(alpha("#FFFFFF", 0.05))
            p.drawRoundedRect(top, S(12), S(12))
        face = QRectF(r.left() + S(16), top.bottom() - S(30), S(56), S(56))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#0B0E10"))
        p.drawEllipse(face.adjusted(-S(3), -S(3), S(3), S(3)))
        frame = self.item if kind == "frame" else ec.look_of(name).get("frame", "")
        paint_face(p, face, self.ctx, name, int(ec.avatar_v or 0), None, frame, now)
        x = face.right() + S(14)
        p.setPen(QColor("#FFFFFF"))
        p.setFont(font(15, QFont.Weight.ExtraBold))
        p.drawText(QRectF(x, top.bottom() - S(30), S(220), S(26)), int(Qt.AlignmentFlag.AlignVCenter), name)
        paint_name_tags(p, x + p.fontMetrics().horizontalAdvance(name) + S(8), top.bottom() - S(17), self.ctx, name,
                        bool(ec.admin))
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10, QFont.Weight.DemiBold))
        p.drawText(QRectF(x, top.bottom() + S(6), r.width() - x - S(10), S(30)), int(Qt.AlignmentFlag.AlignVCenter),
                   self.note or self._gold_note(kind) or tr("Preview on your profile"))

    def _gold_note(self, kind: str) -> str:
        """For a banner you own: how far it is from its next gold level."""
        from .cosmetics import gold_steps_text
        if kind != "banner":
            return ""
        w = self.ctx.econ.wear_data.get(self.item)
        if w:
            return gold_steps_text(w.get("steps"), int(w.get("minutes") or 0))
        steps = GOLD_STEPS.get(self.ctx.econ.rarity(self.item))
        return tr("Turns gold after {a}, {b} and {c} h worn", a=steps[0], b=steps[1], c=steps[2]) if steps else ""


# --------------------------------------------------------------------------- #
# Inventory
# --------------------------------------------------------------------------- #
class LedgerList(QWidget):
    """The last changes of your coins and keys."""

    def __init__(self, rows: list, width: int) -> None:
        super().__init__()
        self.rows = rows[:60]
        self.row_h = S(26)
        self.setFixedSize(width, max(S(26), int(self.row_h * len(self.rows))))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i, row in enumerate(self.rows):
            r = QRectF(0, i * self.row_h, self.width(), self.row_h)
            if i % 2 == 0:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(alpha("#FFFFFF", 0.03))
                p.drawRoundedRect(r.adjusted(0, 1, 0, -1), S(6), S(6))
            p.setPen(QColor(TEXT))
            p.setFont(font(11, QFont.Weight.DemiBold))
            p.drawText(r.adjusted(S(8), 0, -S(120), 0), int(Qt.AlignmentFlag.AlignVCenter),
                       tr(REASONS.get(row.get("reason", ""), row.get("reason", ""))))
            coins, keys = int(row.get("coins") or 0), int(row.get("keys") or 0)
            bits = []
            if coins:
                bits.append(("+" if coins > 0 else "−") + coins_text(abs(coins)))
            if keys:
                bits.append(("+" if keys > 0 else "−") + f"{abs(keys)} " + tr("key"))
            p.setPen(QColor("#5BE08A") if coins > 0 or (not coins and keys > 0) else QColor("#FF7A7A"))
            p.setFont(font(11, QFont.Weight.Bold))
            p.drawText(r.adjusted(0, 0, -S(8), 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                       "  ".join(bits))


class WalletRow(QWidget):
    """Your keys (they can be traded) and your cases waiting to be opened."""

    def __init__(self, page) -> None:
        super().__init__()
        self.page, self.ctx = page, page.ctx
        self.setFixedHeight(S(40))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr("Keys can be added to trades. Click to see your cases."))

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if self.rect().contains(e.position().toPoint()):
            sfx.play("pick")
            self.ctx.shop_tab, self.ctx.shop_case = 3, None
            self.ctx.reload_page()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ec = self.ctx.econ
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(alpha("#FFFFFF", 0.08), 1))
        p.setBrush(alpha("#FFFFFF", 0.04))
        p.drawRoundedRect(r, S(10), S(10))
        half = r.width() / 2
        p.save()
        p.translate(r.left() + S(20), r.center().y())
        p.scale(S(14) / 20, S(14) / 20)
        draw_icon(p, "key", ui.accent)
        p.restore()
        p.setPen(QColor(TEXT))
        p.setFont(font(12, QFont.Weight.Bold))
        p.drawText(QRectF(r.left() + S(36), r.top(), half - S(40), r.height()), int(Qt.AlignmentFlag.AlignVCenter),
                   tr("{n} keys", n=ec.keys))
        cases = sum(int(v or 0) for v in ec.stock.values())
        from .collection import paint_case
        paint_case(p, QRectF(r.left() + half + S(8), r.top() + S(8), S(26), r.height() - S(16)), "standard")
        p.drawText(QRectF(r.left() + half + S(40), r.top(), half - S(44), r.height()), int(Qt.AlignmentFlag.AlignVCenter),
                   tr("{n} cases to open", n=cases))


def build_inventory(page, lay) -> None:
    from .games import GamePicker
    ctx, ec = page.ctx, page.ctx.econ
    if not ec.ready:
        return lay.addWidget(Label(tr("Connecting…") if ctx.online.logged_in() else tr("Log in to see your items"), 12, TEXT_DIM))
    raw = getattr(ctx, "inv_tab", 0)
    tab = 8 if raw == "levels" else int(raw or 0)
    ctx.inv_tab = tab
    picker = GamePicker([tr("All"), tr("Badges"), tr("Balls"), tr("Lines"), tr("Fonts"), tr("Themes"), tr("Profile"),
                         tr("Coins"), tr("Levels")], tab)

    def switch(i: int) -> None:
        ctx.inv_tab, ctx.inv_pick = i, ""
        ctx.reload_page()
    picker.changed.connect(switch)
    lay.addWidget(picker)
    lay.addWidget(WalletRow(page))                       # 3.2: keys and cases are yours too
    if tab == 8:                                         # 4.0: your level, badges and XP coupons
        from .levels import build_levels
        return build_levels(page, lay)
    if tab == 7:
        rows = getattr(ctx, "ledger_rows", None)
        if rows is None or time.monotonic() - getattr(ctx, "ledger_at", 0) > 8:
            ctx.ledger_at = time.monotonic()

            def got(ok: bool, data) -> None:
                if ok and isinstance(data, list) and data != getattr(ctx, "ledger_rows", None):
                    ctx.ledger_rows = data
                    if ctx.window.showing("themes") and getattr(ctx, "inv_tab", 0) == 7:
                        ctx.reload_page("themes")
            ec.online.ask("rb_ledger_list", {}, got)
        lay.addWidget(heading(tr("Coin history")))
        if rows:
            lay.addWidget(LedgerList(rows, page.W))
        else:
            lay.addWidget(Label(tr("Loading…") if rows is None else tr("Nothing here yet"), 12, TEXT_DIM))
        return
    want = ["", "badge", "ball", "line", "font", "theme", "look"][tab]
    groups: dict = {}
    for it in ec.items:
        k = it["item"].split(":")[0]
        if k == "coupon":                                 # XP coupons live in Levels
            continue
        if not want or k == want or (want == "look" and k in LOOKS):
            groups.setdefault(it["item"], []).append(it)
    order = sorted(groups, key=lambda k: (-value_of(ctx, k), k))
    total = sum(value_of(ctx, k) * len(v) for k, v in groups.items())
    count = sum(len(v) for v in groups.values())
    lay.addWidget(Label(tr("{n} items · worth about {v} coins", n=count, v=coins_text(total)), 11, TEXT_DIM))
    extras = [i["id"] for k in order for i in [c for c in groups[k] if not c.get("locked")][1:]
              if ec.quick_value(k) > 0 and len(groups[k]) > 1]
    if extras:
        b = Button(tr("Quick sell every extra copy ({n})", n=len(extras)), "ghost", 30, icon="gem")
        b.setToolTip(tr("Keeps one of each item and sells the rest right away"))
        b.clicked.connect(lambda: quick_sell(ctx, extras, tr("{n} extra copies", n=len(extras))))
        lay.addWidget(b)
    if not order:
        lay.addWidget(Label(tr("Nothing here yet. Open cases or visit the shop."), 12, TEXT_DIM, wrap_w=page.W))
        return
    pick = getattr(ctx, "inv_pick", "") or ""
    if pick not in groups:
        pick = ""
    if pick:
        _inventory_detail(page, lay, pick, groups[pick])
    wearing = set(worn(ctx))
    entries = []
    for k in order:
        free = [i for i in groups[k] if not i.get("locked")]
        on = k in wearing or ctx.shop_item_worn(k) or (k.split(":")[0] in LOOKS and look_worn(ctx, k))
        entries.append({"item": k, "text": coins_text(value_of(ctx, k)) if value_of(ctx, k) else tr("Free"),
                        "tag": f"×{len(groups[k])}" if len(groups[k]) > 1 else "",
                        "mark": "lock" if not free else ("worn" if on else "")})
    grid = ItemGrid(ctx, entries, page.W, 5, 72, order.index(pick) if pick else -1)

    def choose(i: int) -> None:
        sfx.play("pick")
        ctx.inv_pick = "" if order[i] == pick else order[i]
        ctx.reload_page()
    grid.picked.connect(choose)
    lay.addWidget(grid)


def _inventory_detail(page, lay, item: str, copies: list) -> None:
    ctx, ec = page.ctx, page.ctx.econ
    kind = item.split(":")[0]
    free = [c for c in copies if not c.get("locked")]
    head = hbox(spacing=8)
    head.addWidget(Label(item_name(item), 13.5, bold=True), 1)
    head.addWidget(Label(rarity_line(ctx, item), 10.5, RARITY_COLOURS.get(ec.rarity(item), TEXT_DIM), bold=True))
    lay.addLayout(head)
    locked = len(copies) - len(free)
    note = tr("Worth {v} coins", v=coins_text(value_of(ctx, item))) if value_of(ctx, item) else \
        tr("A gift for the first users of Rubenium. It cannot be sold or traded.")
    if locked:
        where = copies[0].get("locked") or next((c["locked"] for c in copies if c.get("locked")), "")
        note += "  ·  " + (tr("{n} on the market", n=locked) if str(where).startswith("market") else tr("{n} in a trade", n=locked))
    lay.addWidget(Label(note, 10.5, TEXT_DIM, wrap_w=page.W))
    line = hbox(spacing=6)
    if kind == "badge":
        on = item in worn(ctx)
        b = Button(tr("Take off") if on else tr("Show"), "ghost" if on else "primary", 32)

        def show() -> None:
            done = lambda ok, d: (None if ok else ctx.toast(tr(str(d)), "warn"), ctx.reload_page())      # noqa: E731
            if on:
                return ec.wear(next(s for s in SLOTS if ec.worn(s) == item), "", done)
            slot = next((s for s in SLOTS if not ec.worn(s)), None)
            if slot is None:
                return ctx.toast(tr("Your showcase is full: take one off first"), "warn")
            sfx.play("pick")
            ec.wear(slot, item, done)
        b.clicked.connect(show)
    elif kind in LOOKS:
        on = look_worn(ctx, item)
        b = Button(tr("Take off") if on else tr("Wear"), "ghost" if on else "primary", 32)
        b.clicked.connect(lambda: wear_look(ctx, item, not on))
    else:
        on = ctx.shop_item_worn(item)
        b = Button(tr("Take off") if on else tr("Wear"), "ghost" if on else "primary", 32)

        def wear() -> None:
            sfx.play("pick")
            ctx.take_off_shop_item(kind) if on else ctx.wear_shop_item(item)
            ctx.reload_page()
        b.clicked.connect(wear)
    line.addWidget(b, 1)
    sellable = bool(free) and bool(ec.info(item).get("tradeable"))
    sell = Button(tr("Market"), "ghost", 32, icon="chip")
    sell.setEnabled(sellable)
    sell.setToolTip(tr("Put it on the market: other users buy it or make you an offer"))
    sell.clicked.connect(lambda: market_sell(ctx, item))
    line.addWidget(sell, 1)
    quick = Button(tr("Quick sell"), "ghost", 32, icon="gem")
    quick.setEnabled(sellable and ec.quick_value(item) > 0)
    quick.setToolTip(tr("Sell it right now for about {n} coins",
                        n=coins_text(ec.quick_value(item))))
    quick.clicked.connect(lambda: quick_sell(ctx, [free[-1]["id"]], item_name(item)))
    line.addWidget(quick, 1)
    lay.addLayout(line)
    if sellable and len(free) > 1 and ec.quick_value(item) > 0:
        rest = [c["id"] for c in free[1:]]
        more = Button(tr("Quick sell the extra copies ({n}), keep one", n=len(rest)), "quiet", 26)
        more.clicked.connect(lambda: quick_sell(ctx, rest, tr("{n} × {name}", n=len(rest), name=item_name(item))))
        lay.addWidget(more)


def quick_sell(ctx, ids: list, what: str) -> None:
    """Sell to Rubenium right away: low price (a quarter of the value), but instant. The server says the exact
    amount first."""
    ec = ctx.econ
    if not ec.quick_ready():
        return ctx.toast(tr("Coming very soon: the server is being updated"), "warn")

    def quoted(ok: bool, q) -> None:
        if not ok or not isinstance(q, dict):
            from .econ import server_missing
            return ctx.toast(tr("Coming very soon: the server is being updated") if server_missing(q)
                             else tr("Something went wrong: try again"), "warn")
        total, n = int(q.get("total") or 0), int(q.get("n") or 0)
        if not n:
            return ctx.toast(tr("This cannot be sold"), "warn")

        def go() -> None:
            def done(ok2: bool, d) -> None:
                if not ok2:
                    sfx.play("off")
                    return ctx.toast(tr(str(d)), "warn")
                sfx.play("on")
                ctx.toast(tr("Sold for {n} coins", n=coins_text(int(d.get("paid") or total))))
                ctx.inv_pick = ""
                ctx.reload_page()
            ec.quick_sell(ids, done)
        ctx.window.confirm(tr("Quick sell {what} for {n} coins? Instant, but the market usually pays more.",
                              what=what, n=coins_text(total)), go, yes=tr("Sell"))
    ec.quick_quote(ids, quoted)


def build_profile_style(page, lay) -> None:
    """Style > Your profile: banner, frame, tag and the 3 badges of your showcase, as everyone sees them."""
    from .friends import Showcase3
    ctx, ec = page.ctx, page.ctx.econ
    lay.addWidget(heading(tr("Your profile")))
    if not ec.ready:
        return lay.addWidget(Label(tr("Log in to change your profile"), 11, TEXT_DIM))
    lay.addWidget(LookPreview(ctx, "", page.W, tr("This is what other users see")))
    if not any(k.startswith("banner:") for k in ec.catalog):
        return lay.addWidget(Label(tr("Banners and frames: coming very soon"), 11, TEXT_DIM))
    for kind, title, empty in (("banner", tr("Banner"), tr("No banner yet: buy one in the Shop or on the Market.")),
                               ("frame", tr("Frame"), tr("No frame yet: buy one in the Shop or on the Market.")),
                               ("tag", tr("Tag"), tr("No tag yet."))):
        mine = sorted({i["item"] for i in ec.items if i["item"].startswith(kind + ":")},
                      key=lambda k: (-ec.worth(k), k))
        if kind == "tag" and not mine:
            continue
        head = hbox(spacing=8)
        head.addWidget(Label(title, 12.5, bold=True), 1)
        cur = ec.worn(kind)
        head.addWidget(Label(item_name(cur) if cur and cur in mine else tr("None"), 10.5, TEXT_DIM))
        lay.addLayout(head)
        if not mine:
            lay.addWidget(Label(empty, 10.5, TEXT_FAINT, wrap_w=page.W))
            continue
        entries = [{"item": k, "text": tr("Worn") if k == cur else tr("Wear")} for k in mine]
        grid = ItemGrid(ctx, entries, page.W, 3 if kind == "banner" else 5, 80 if kind == "banner" else 70,
                        mine.index(cur) if cur in mine else -1)
        grid.picked.connect(lambda i, m=mine, c=cur: wear_look(ctx, m[i], m[i] != c))
        lay.addWidget(grid)
        level = int((ec.wear_data.get(cur) or {}).get("level") or 0) if kind == "banner" and cur else 0
        if level:                                          # 3.1: keep the normal look or show its gold
            from .cosmetics import GOLD_NAMES
            pick = ec.worn("banner_gold")
            pick = min(level, int(pick) if pick.isdigit() else 3)
            seg = Segmented([tr("Normal")] + [tr(GOLD_NAMES[n]) for n in range(1, level + 1)], pick)

            def choose(i: int) -> None:
                def done(ok: bool, _d) -> None:
                    if ok:
                        ec.equip["banner_gold"] = i
                        ec.looks_changed.emit()
                        ctx.reload_page()
                ec.call("rb_banner_gold", {"level": i}, done)
            seg.changed.connect(choose)
            lay.addWidget(seg)
    lay.addWidget(Label(tr("Click the one you wear to take it off."), 10, TEXT_FAINT))
    head = hbox(spacing=8)
    head.addWidget(Label(tr("Showcase"), 12.5, bold=True), 1)
    pick = Button(tr("Choose badges"), "ghost", 26)

    def to_collection() -> None:
        ctx.shop_tab = 2
        if ctx.window.showing("themes"):
            ctx.reload_page("themes")
        else:
            ctx.window._drop_page("themes")
            ctx.window.goto("themes")
    pick.clicked.connect(to_collection)
    head.addWidget(pick)
    lay.addLayout(head)
    lay.addWidget(Showcase3(ctx, ec.badges_worn(), page.W, True))
    lay.addWidget(Label(tr("The 3 badges you show are the showcase on your profile."), 10, TEXT_FAINT, wrap_w=page.W))


def market_sell(ctx, item: str) -> None:
    """Sell = put it on the market. Choose a price between the lowest and highest allowed; players buy it at
    that price or make you an offer."""
    ec = ctx.econ
    free = [i for i in ec.items if i["item"] == item and not i.get("locked")]
    if not free:
        return ctx.toast(tr("This item is already on the market or in a trade"), "warn")
    if not ec.can_trade():
        return ctx.toast(tr("The market opens after 5 hours with Rubenium"), "warn")

    def priced(ok: bool, info) -> None:
        if not ok or not isinstance(info, dict):
            return ctx.toast(tr("Something went wrong: try again"), "warn")
        lo, hi = int(info.get("min") or 1), int(info.get("max") or 1)

        def listed(n: int, dlg) -> None:
            if n < lo or n > hi:
                return dlg.say(tr("Between {a} and {b} coins", a=coins_text(lo), b=coins_text(hi)))

            def done(ok2: bool, d) -> None:
                if not ok2:
                    return dlg.say(tr(str(d)))
                dlg.close()
                sfx.play("on")
                ctx.toast(tr("On the market for {n} coins", n=coins_text(n)))
                ec.refresh()
                ctx.mk_at = 0
                QTimer.singleShot(600, ctx.reload_page)
            ec.call("rb_market_list", {"item_id": free[-1]["id"], "price": n}, done)
        ask_number(ctx, tr("Sell: {name}", name=item_name(item)), tr("Price in coins"), tr("Put on sale"), listed,
                   tr("Usual price: about {v} coins. Choose between {a} and {b}. Users can buy it at your price or "
                      "make you an offer. The market keeps 5% when it sells.",
                      v=coins_text(int(info.get("estimate") or 0)), a=coins_text(lo), b=coins_text(hi)))
    ec.online.ask("rb_market_price", {"what": item}, priced)


# --------------------------------------------------------------------------- #
# Market
# --------------------------------------------------------------------------- #
class ListingRow(QWidget):
    """One item on sale: picture, name, seller, price."""
    clicked = pyqtSignal()

    def __init__(self, ctx, row: dict, width: int, mine: bool = False) -> None:
        super().__init__()
        self.ctx, self.row, self.mine = ctx, row, mine
        self.setFixedSize(width, S(48))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False
        self._timer = QTimer(self)
        self._timer.setInterval(80)
        self._timer.timeout.connect(self.update)

    def showEvent(self, _e) -> None:
        self._timer.start()

    def hideEvent(self, _e) -> None:
        self._timer.stop()

    def enterEvent(self, _e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = False
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        row, item = self.row, self.row.get("item", "")
        r = QRectF(self.rect()).adjusted(0.5, 2, -0.5, -2)
        col = QColor(RARITY_COLOURS.get(self.ctx.econ.rarity(item), "#9AA4AD"))
        p.setPen(QPen(alpha(col, 0.35 + (0.3 if self._hover else 0)), 1.1))
        p.setBrush(mix(QColor("#0D1214"), col, 0.07 + (0.05 if self._hover else 0)))
        p.drawRoundedRect(r, S(10), S(10))
        paint_cosmetic(p, item, QRectF(r.left() + S(8), r.top() + S(6), r.height() - S(12), r.height() - S(12)),
                       time.monotonic())
        x = r.left() + S(52)
        p.setPen(QColor(TEXT))
        p.setFont(font(12, QFont.Weight.Bold))
        name = p.fontMetrics().elidedText(item_name(item), Qt.TextElideMode.ElideRight, int(r.width() - S(150)))
        p.drawText(QRectF(x, r.top() + S(5), r.width() - S(150), S(18)), int(Qt.AlignmentFlag.AlignVCenter), name)
        p.setPen(QColor(TEXT_DIM))
        p.setFont(font(10, QFont.Weight.DemiBold))
        if self.mine:
            state = row.get("state")
            sub = tr("On sale") if state == "open" else tr("Sold to {name}", name=row.get("buyer") or "?")
        else:
            sub = (tr("Yours") if row.get("mine") else tr("by {name}", name=row.get("seller", "?"))) + \
                "  ·  " + tr("usual: {v}", v=coins_text(int(row.get("estimate") or 0)))
        p.drawText(QRectF(x, r.top() + S(23), r.width() - S(150), S(16)), int(Qt.AlignmentFlag.AlignVCenter), sub)
        paint_coin(p, QPointF(r.right() - S(86), r.center().y()), S(6))
        p.setPen(QColor(GOLD_TEXT))
        p.setFont(font(12.5, QFont.Weight.Bold))
        p.drawText(QRectF(r.right() - S(76), r.top(), S(68), r.height()), int(Qt.AlignmentFlag.AlignVCenter),
                   coins_text(int(row.get("price") or 0)))


def build_market(page, lay) -> None:
    ctx, ec = page.ctx, page.ctx.econ
    if not ec.ready:
        return lay.addWidget(Label(tr("Connecting…") if ctx.online.logged_in() else tr("Log in to see the market"), 12, TEXT_DIM))
    tab = int(getattr(ctx, "mk_tab", 0) or 0)
    offers = int(ec.live.get("offers") or 0)
    seg = Segmented([tr("Buy"), tr("My sales"), tr("Offers") + (f" ({offers})" if offers else "")], tab)

    def switch(i: int) -> None:
        ctx.mk_tab, ctx.mk_at = i, 0
        ctx.reload_page()
    seg.changed.connect(switch)
    lay.addWidget(seg)
    if tab == 2:
        return _offers(page, lay)
    if tab:
        fn, args = "rb_market_mine", {}
    else:                                                    # 4.0: search by name, type, rarity and finish
        flt = market_filters(ctx)
        if not _market_search_bar(page, lay, flt):
            return
        ids = market_ids(ctx, flt["q"]) if flt["q"] else None
        if ids is not None and not ids:
            return lay.addWidget(Label(tr("No item is called “{q}”.", q=flt["q"]), 12, TEXT_DIM, wrap_w=page.W))
        fn, args = "rb_market_search", {"ids": ids, "kind": flt["kind"], "rarity": flt["rarity"],
                                        "cls": flt["cls"], "sort": flt["sort"], "page": 0}
    key = (fn, str(args))
    rows = getattr(ctx, "mk_rows", None) if getattr(ctx, "mk_key", None) == key else None
    if rows is None or time.monotonic() - getattr(ctx, "mk_at", 0) > 10:
        ctx.mk_at = time.monotonic()

        def got(ok: bool, data) -> None:
            if not ok or not isinstance(data, list):
                return
            changed = data != getattr(ctx, "mk_rows", None) or getattr(ctx, "mk_key", None) != key
            ctx.mk_rows, ctx.mk_key = data, key
            if changed and ctx.window.showing("themes") and getattr(ctx, "shop_tab", 0) == 4:
                ctx.reload_page("themes")
        ec.online.ask(fn, args, got)
    if rows is None:
        return lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
    if not rows:
        searching = not tab and market_filters(ctx) != MARKET_FILTERS
        lay.addWidget(Label(tr("Nothing on sale. List an item from your Inventory.") if tab else
                            tr("Nothing on sale matches this search.") if searching else
                            tr("Nothing on sale right now. Be the first: put an item on sale from your Inventory."),
                            12, TEXT_DIM, wrap_w=page.W))
    for row in rows[:40]:
        if is_secret(row.get("item", "")):
            row = dict(row)
        w = ListingRow(ctx, row, page.W, mine=bool(tab))
        w.clicked.connect(lambda r=row: _market_click(page, r, bool(tab)))
        lay.addWidget(w)
    if not tab:
        lay.addWidget(Label(tr("Fixed price set by the seller. 5% market fee."), 10.5, TEXT_DIM,
                            wrap_w=page.W))


MARKET_FILTERS = {"q": "", "kind": "", "rarity": "", "cls": None, "sort": "new"}
MARKET_SORTS = [("new", "Newest"), ("cheap", "Cheapest"), ("dear", "Priciest"), ("deal", "Best deals")]
MARKET_KINDS = [("", "All"), ("badge", "Badges"), ("banner", "Banners"), ("frame", "Frames"), ("ball", "Balls"),
                ("line", "Lines"), ("theme", "Themes"), ("font", "Fonts")]


def market_filters(ctx) -> dict:
    f = getattr(ctx, "mk_filters", None)
    if not isinstance(f, dict):
        f = ctx.mk_filters = dict(MARKET_FILTERS)
    return f


def market_ids(ctx, query: str) -> list:
    """Every item whose name, type, rarity or finish holds all the words typed (English or French)."""
    words = [w for w in query.lower().replace(",", " ").split() if w]
    from .cosmetics import KIND_NAMES
    out = []
    for iid, info in ctx.econ.catalog.items():
        if not info.get("tradeable") or info.get("kind") in ("prog", "tag", "coupon"):
            continue
        kind = info.get("kind", "")
        hay = [item_name(iid), iid, KIND_NAMES.get(kind, kind), RARITY_NAMES.get(info.get("rarity", ""), "")]
        if kind == "badge":
            hay.append(CLASS_NAMES[min(int(info.get("cls") or 0), len(CLASS_NAMES) - 1)])
        text = " ".join(hay + [tr(h) for h in hay]).lower()
        if all(w in text for w in words):
            out.append(iid)
    return out


def _market_search_bar(page, lay, flt: dict) -> bool:
    """The search bar and its filters. False if nothing more should be shown (never, for now)."""
    ctx = page.ctx

    def apply(**kw) -> None:
        flt.update(kw)
        ctx.mk_at = 0
        ctx.reload_page()

    def ask() -> None:
        def got(text: str, dlg) -> None:
            dlg.close()
            apply(q=text.strip()[:40])
        AskDialog(ctx, tr("Search the market"), tr("Name, type, rarity or finish"), tr("Search"), got, 40,
                  tr("For example: dragon, titanium, mythic banner."))
    bar = SearchBar(flt["q"], page.W)
    bar.clicked.connect(ask)
    bar.cleared.connect(lambda: apply(**MARKET_FILTERS))
    lay.addWidget(bar)
    kinds = Segmented([tr(n) for _k, n in MARKET_KINDS], [k for k, _n in MARKET_KINDS].index(flt["kind"])
                      if flt["kind"] in [k for k, _n in MARKET_KINDS] else 0)
    kinds.changed.connect(lambda i: apply(kind=MARKET_KINDS[i][0], cls=None if MARKET_KINDS[i][0] != "badge" else flt["cls"]))
    lay.addWidget(kinds)
    rar = ["", "standard", "rare", "special", "epic", "exotic"]
    rs = Segmented([tr("Any rarity")] + [tr(RARITY_NAMES[r]) for r in rar[1:]], rar.index(flt["rarity"]) if flt["rarity"] in rar else 0)
    rs.changed.connect(lambda i: apply(rarity=rar[i]))
    lay.addWidget(rs)
    if flt["kind"] == "badge":
        cls = [None, 0, 1, 2, 3, 4]
        cs = Segmented([tr("Any finish")] + [tr(CLASS_NAMES[c]) for c in cls[1:]],
                       cls.index(flt["cls"]) if flt["cls"] in cls else 0)
        cs.changed.connect(lambda i: apply(cls=cls[i]))
        lay.addWidget(cs)
    srt = [k for k, _n in MARKET_SORTS]
    ss = Segmented([tr(n) for _k, n in MARKET_SORTS], srt.index(flt["sort"]) if flt["sort"] in srt else 0)
    ss.changed.connect(lambda i: apply(sort=srt[i]))
    lay.addWidget(ss)
    return True


class SearchBar(QWidget):
    """A search field drawn like one: click to type (the keyboard stays with your game until then)."""
    clicked = pyqtSignal()
    cleared = pyqtSignal()

    def __init__(self, query: str, width: int) -> None:
        super().__init__()
        self.query = query
        self.setFixedSize(width, S(38))
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self._hover = False

    def enterEvent(self, _e) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = False
        self.update()

    def _x_rect(self) -> QRectF:
        return QRectF(self.width() - S(34), 0, S(34), self.height())

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self.query and self._x_rect().contains(e.position()):
            sfx.play("pick")
            return self.cleared.emit()
        self.clicked.emit()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(alpha(ui.accent, 0.7) if self.query else alpha("#FFFFFF", 0.22 if self._hover else 0.12), S(1.2)))
        p.setBrush(alpha("#FFFFFF", 0.07 if self._hover else 0.05))
        p.drawRoundedRect(r, S(10), S(10))
        p.save()
        p.translate(r.left() + S(18), r.center().y())
        p.scale(S(15) / 20, S(15) / 20)
        draw_icon(p, "search", QColor(TEXT_DIM))
        p.restore()
        p.setFont(font(12, QFont.Weight.DemiBold if self.query else QFont.Weight.Normal))
        p.setPen(QColor(TEXT) if self.query else QColor(TEXT_DIM))
        p.drawText(r.adjusted(S(34), 0, -S(36), 0), int(Qt.AlignmentFlag.AlignVCenter),
                   self.query or tr("Search the market: name, type, rarity, finish…"))
        if self.query:
            c = self._x_rect().center()
            p.setPen(QPen(QColor(TEXT_DIM), S(1.6)))
            p.drawLine(QPointF(c.x() - S(4), c.y() - S(4)), QPointF(c.x() + S(4), c.y() + S(4)))
            p.drawLine(QPointF(c.x() + S(4), c.y() - S(4)), QPointF(c.x() - S(4), c.y() + S(4)))


def _market_click(page, row: dict, mine: bool) -> None:
    ctx, ec = page.ctx, page.ctx.econ
    price, item = int(row.get("price") or 0), row.get("item", "")

    def after(ok: bool, data) -> None:
        if not ok:
            sfx.play("off")
            ctx.toast(tr(str(data)), "warn")
        else:
            sfx.play("on")
        ctx.mk_at = 0
        ec.refresh()
        QTimer.singleShot(500, ctx.reload_page)
    if mine or row.get("mine"):
        if row.get("state", "open") != "open":
            return
        return ctx.window.confirm(tr("Take {name} off the market?", name=item_name(item)),
                                  lambda: ec.call("rb_market_cancel", {"listing": row["listing"]}, after), yes=tr("Take off"))
    if not ec.can_trade():
        return ctx.toast(tr("The market opens after 5 hours with Rubenium"), "warn")
    if price > ec.coins:
        return ctx.toast(tr("Not enough coins: {n} more needed", n=coins_text(price - ec.coins)), "warn")

    def bought(ok: bool, data) -> None:
        if ok and isinstance(data, dict):
            ec.gained(data.get("item"), data.get("id"), "market")
            ctx.toast(tr("Bought: {what}", what=item_name(item)))
        after(ok, data)
    text = tr("Buy {name} for {n} coins?", name=item_name(item), n=coins_text(price))
    est = int(row.get("estimate") or 0)
    if est and price > est * 2:
        text += " " + tr("This is much more than its usual price ({v}).", v=coins_text(est))
    def offer() -> None:
        low = -(-price // 2)

        def sent(n: int, dlg) -> None:
            if n < low or n >= price:
                return dlg.say(tr("Between {a} and {b} coins", a=coins_text(low), b=coins_text(price - 1)))
            if n > ec.coins:
                return dlg.say(tr("Not enough coins"))

            def done(ok: bool, d) -> None:
                if not ok:
                    return dlg.say(tr(str(d)))
                dlg.close()
                sfx.play("on")
                ctx.toast(tr("Offer sent. Your coins stay yours until the seller accepts."))
            ec.call("rb_market_offer", {"listing": row["listing"], "price": n}, done)
        ask_number(ctx, tr("Make an offer"), tr("Your price"), tr("Send offer"), sent,
                   tr("{name}: on sale for {n} coins. Offer at least {a}.", name=item_name(item), n=coins_text(price),
                      a=coins_text(low)))
    ctx.window.confirm(text, lambda: ec.call("rb_market_buy", {"listing": row["listing"]}, bought, once=True),
                       yes=tr("Buy"), no=tr("Make an offer"), on_no=offer)


def _offers(page, lay) -> None:
    """Offers made to you (accept or refuse), and offers you made."""
    ctx, ec = page.ctx, page.ctx.econ
    data = getattr(ctx, "offer_rows", None)
    if data is None or time.monotonic() - getattr(ctx, "offer_at", 0) > 8:
        ctx.offer_at = time.monotonic()

        def got(ok: bool, d) -> None:
            if ok and isinstance(d, dict) and d != getattr(ctx, "offer_rows", None):
                ctx.offer_rows = d
                if ctx.window.showing("themes") and getattr(ctx, "shop_tab", 0) == 4:
                    ctx.reload_page("themes")
        ec.online.ask("rb_market_offers", {}, got)
    if data is None:
        return lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))

    def answer(o: dict, yes: bool) -> None:
        def done(ok: bool, d) -> None:
            if not ok:
                sfx.play("off")
                ctx.toast(tr(str(d)), "warn")
            else:
                sfx.play("on")
                ctx.toast(tr("Sold for {n} coins!", n=coins_text(o["price"])) if yes else tr("Offer refused"))
            ctx.offer_rows, ctx.mk_at = None, 0
            ec.refresh()
            QTimer.singleShot(400, ctx.reload_page)
        if yes:
            ctx.window.confirm(tr("Sell {name} to {who} for {n} coins?", name=item_name(o["item"]), who=o["from"],
                                  n=coins_text(o["price"])), lambda: ec.call("rb_market_answer", {"offer": o["offer"], "accept": True}, done),
                               yes=tr("Sell"))
        else:
            ec.call("rb_market_answer", {"offer": o["offer"], "accept": False}, done)
    lay.addWidget(heading(tr("Offers for your items")))
    if not data.get("to_me"):
        lay.addWidget(Label(tr("No offers yet."), 11.5, TEXT_DIM))
    for o in data.get("to_me") or []:
        w = ListingRow(ctx, {"item": o["item"], "price": o["price"], "seller": o["from"],
                             "estimate": o.get("asking")}, page.W)
        w.setToolTip(tr("{who} offers {n} coins (your price: {p})", who=o["from"], n=coins_text(o["price"]),
                        p=coins_text(o.get("asking") or 0)))
        lay.addWidget(w)
        line = hbox(spacing=6)
        no = Button(tr("Refuse"), "ghost", 28)
        yes = Button(tr("Accept {n}", n=coins_text(o["price"])), "primary", 28)
        no.clicked.connect(lambda _=False, x=o: answer(x, False))
        yes.clicked.connect(lambda _=False, x=o: answer(x, True))
        line.addWidget(no, 1)
        line.addWidget(yes, 2)
        lay.addLayout(line)
    lay.addWidget(heading(tr("Your offers")))
    if not data.get("mine"):
        lay.addWidget(Label(tr("You have not made any offer."), 11.5, TEXT_DIM))
    states = {"open": "Waiting", "taken": "Accepted", "refused": "Refused", "gone": "Closed"}
    for o in data.get("mine") or []:
        w = ListingRow(ctx, {"item": o["item"], "price": o["price"], "seller": tr(states.get(o["state"], "")),
                             "estimate": o.get("asking")}, page.W)
        if o["state"] == "open":
            w.clicked.connect(lambda x=o: ctx.window.confirm(tr("Take back this offer?"), lambda: ec.call(
                "rb_market_unoffer", {"offer": x["offer"]}, lambda _o, _d: (setattr(ctx, "offer_rows", None), ctx.reload_page())),
                yes=tr("Take back")))
        lay.addWidget(w)


# --------------------------------------------------------------------------- #
# Trading
# --------------------------------------------------------------------------- #
class TradeLink(QObject):
    """Keeps one trade in step with the server while it is open (asked every 1.5 s). If this stops (the app is
    closed, the internet is gone), the server ends the trade by itself after a minute."""
    changed = pyqtSignal()

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self.trade_id = ""
        self.data: dict = {}
        self.peek: dict = {}            # 4.0: the other player's tradeable items (look only)
        self.summary: dict = {}         # 4.0: what the server recorded once the trade is done
        self.view = 0                   # 4.0: 0 = your inventory, 1 = theirs
        self.shown_ready, self.shown_trade = (), ""
        self.got_at = 0.0
        self.busy = False
        self._sig = ""
        self._timer = QTimer(self)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(self.poll)

    def open(self, trade_id: str) -> None:
        if trade_id and trade_id != self.trade_id:
            self.trade_id, self.data, self._sig = trade_id, {}, ""
            self.peek, self.summary, self.view = {}, {}, 0
        self._timer.start()
        self.poll()

    def close(self) -> None:
        self._timer.stop()
        self.trade_id, self.data, self._sig = "", {}, ""
        self.peek, self.summary, self.view = {}, {}, 0

    def close_if_left(self) -> None:
        w = self.ctx.window
        if self.finished() and not (w.showing("friends") and w.expanded):
            self.close()

    def finished(self) -> bool:
        """The trade is over (done or cancelled): only its summary is left to show."""
        return bool(self.trade_id) and self.data.get("state") in ("done", "cancelled")

    def poll(self) -> None:
        if not self.trade_id:
            return self._timer.stop()
        tid = self.trade_id

        def got(ok: bool, data) -> None:
            if tid != self.trade_id:
                return
            if not ok:
                if "rb_trade_gone" in str(data):
                    self.data = {"state": "cancelled", "why": "gone"}
                    self._timer.stop()
                    self.changed.emit()
                return
            self.data, self.got_at = data, time.monotonic()
            sig = str([data.get(k) for k in ("state", "version", "a_ready", "b_ready", "a_ok", "b_ok", "a_coins",
                                              "b_coins", "a_keys", "b_keys")]) + str(data.get("wait") is None)
            if data.get("state") in ("done", "cancelled"):
                self._timer.stop()
                self.ctx.econ.refresh()
            if sig != self._sig:
                self._sig = sig
                self.changed.emit()
        self.ctx.online.ask("rb_trade_get", {"trade": tid}, got, raw=True)

    def act(self, fn: str, args: dict, quiet: bool = False) -> None:
        if self.busy:
            return
        self.busy = True

        def back(ok: bool, data) -> None:
            self.busy = False
            if not ok and not quiet:
                sfx.play("off")
                self.ctx.toast(tr(str(data)), "warn")
            self.poll()
        self.ctx.econ.call(fn, dict(args, trade=self.trade_id), back)

    def wait_left(self) -> float:
        wait = self.data.get("wait")
        return 0.0 if wait is None else max(0.0, float(wait) - (time.monotonic() - self.got_at))


class Countdown(QWidget):
    """Both are ready: 5 seconds to look one last time, then Confirm lights up."""
    done = pyqtSignal()

    def __init__(self, link: TradeLink) -> None:
        super().__init__()
        self.link = link
        self.setFixedHeight(S(34))
        self._fired = False
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

    def showEvent(self, _e) -> None:
        self._timer.start()

    def hideEvent(self, _e) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        if self.link.wait_left() <= 0 and not self._fired:
            self._fired = True
            self.done.emit()
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        left = self.link.wait_left()
        r = QRectF(self.rect()).adjusted(1, 3, -1, -3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(alpha("#FFFFFF", 0.06))
        p.drawRoundedRect(r, S(8), S(8))
        p.setBrush(alpha(GOLD_TEXT, 0.35))
        p.drawRoundedRect(QRectF(r.left(), r.top(), r.width() * (1 - min(1.0, left / 5.0)), r.height()), S(8), S(8))
        p.setPen(QColor(TEXT))
        p.setFont(font(11.5, QFont.Weight.Bold))
        p.drawText(r, int(Qt.AlignmentFlag.AlignCenter),
                   tr("Look one last time… {n}", n=int(math.ceil(left))) if left > 0 else tr("You can confirm now"))


# --------------------------------------------------------------------------- #
# 4.0: the trade screen: who is ready, both inventories (yours to add from, theirs to look at), and a summary
# --------------------------------------------------------------------------- #
READY_GREEN = "#5BE08A"
LOSS_RED = "#FF7A7A"


def paint_key(p: QPainter, c: QPointF, size: float, colour) -> None:
    """The key icon, `size` pixels tall, centred on c."""
    p.save()
    p.translate(c)
    p.scale(size / 20, size / 20)
    draw_icon(p, "key", QColor(colour))
    p.restore()


class ReadyPill(QWidget):
    """One player's state in the trade: NOT READY (dark), READY (green) or CONFIRMED (bright green). It flashes when
    the state has just changed, so a change on the other side is never missed."""

    def __init__(self, name: str, ready: bool, ok: bool, flash: bool) -> None:
        super().__init__()
        self.name, self.ready, self.ok = name, ready, ok
        self.setFixedHeight(S(32))
        self.setMinimumWidth(S(120))
        self._flash = Tween(self, 1.0 if flash else 0.0, self.update)
        if flash:
            QTimer.singleShot(30, lambda: self._flash.to(0.0, 900))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(S(1), S(1), -S(1), -S(1))
        on = self.ready or self.ok
        green = QColor(READY_GREEN)
        f = self._flash.level
        if on:
            p.setPen(QPen(mix(green, QColor("#FFFFFF"), 0.4 * f), S(1.6)))
            p.setBrush(mix(QColor("#123A24"), green, 0.25 + (0.25 if self.ok else 0.0) + 0.3 * f))
        else:
            p.setPen(QPen(mix(QColor("#2A3238"), QColor("#FFFFFF"), 0.35 * f), S(1.2)))
            p.setBrush(QColor("#12171A"))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        dot = QPointF(r.left() + S(14), r.center().y())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FFFFFF") if on else QColor("#46505A"))
        p.drawEllipse(dot, S(4), S(4))
        state = tr("CONFIRMED") if self.ok else tr("READY") if self.ready else tr("NOT READY")
        sf = font(10, QFont.Weight.ExtraBold)
        sw = QFontMetrics(sf).horizontalAdvance(state) + S(4)
        p.setFont(sf)
        p.setPen(QColor("#FFFFFF") if on else QColor(TEXT_FAINT))
        sr = QRectF(r.right() - sw - S(12), r.top(), sw, r.height())
        p.drawText(sr, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), state)
        nf = font(11, QFont.Weight.Bold)
        p.setFont(nf)
        p.setPen(QColor(TEXT) if on else QColor(TEXT_DIM))
        nr = QRectF(dot.x() + S(10), r.top(), sr.left() - dot.x() - S(16), r.height())
        p.drawText(nr, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                   QFontMetrics(nf).elidedText(self.name, Qt.TextElideMode.ElideRight, int(nr.width())))


class AmountRow(QWidget):
    """Coins and keys with their icons (never covered by a button), and the value on the right."""

    def __init__(self, coins: int, keys: int, worth: str = "", sign: str = "", colour: str = "",
                 skip_zero: bool = False) -> None:
        super().__init__()
        self.coins, self.keys, self.worth, self.sign, self.colour = coins, keys, worth, sign, colour
        self.skip_zero = skip_zero              # the trade summary: only what moved
        self.setFixedHeight(S(24))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        f = font(11.5, QFont.Weight.Bold)
        p.setFont(f)
        fm = QFontMetrics(f)
        x = S(2)
        if self.coins or not self.skip_zero:
            paint_coin(p, QPointF(x + S(8), h / 2), S(7.5))
            x += S(20)
            text = self.sign + coins_text(self.coins)
            p.setPen(QColor(self.colour or GOLD_TEXT))
            p.drawText(QRectF(x, 0, fm.horizontalAdvance(text) + S(4), h), int(Qt.AlignmentFlag.AlignVCenter), text)
            x += fm.horizontalAdvance(text) + S(16)
        if self.keys or not self.skip_zero:
            paint_key(p, QPointF(x + S(8), h / 2), S(16), self.colour or ui.accent)
            x += S(20)
            text = self.sign + str(self.keys)
            p.setPen(QColor(self.colour) if self.colour else ui.accent)
            p.drawText(QRectF(x, 0, fm.horizontalAdvance(text) + S(4), h), int(Qt.AlignmentFlag.AlignVCenter), text)
            x += fm.horizontalAdvance(text) + S(10)
        if self.worth:
            wf = font(10.5)
            p.setFont(wf)
            p.setPen(QColor(TEXT_DIM))
            wr = QRectF(x, 0, self.width() - x - S(2), h)
            p.drawText(wr, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight),
                       QFontMetrics(wf).elidedText(self.worth, Qt.TextElideMode.ElideLeft, int(wr.width())))


class InvSwitch(QWidget):
    """YOUR INVENTORY | NAME'S INVENTORY: a two-way switch. The side shown is lit, the other is dark."""
    changed = pyqtSignal(int)

    def __init__(self, labels: list, index: int) -> None:
        super().__init__()
        self.labels, self.index = labels, index
        self.setFixedHeight(S(36))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pos = Tween(self, float(index), self.update)
        self._hover = -1
        self.setMouseTracking(True)

    def mouseMoveEvent(self, e) -> None:
        i = 0 if e.position().x() < self.width() / 2 else 1
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = -1
        self.update()

    def mousePressEvent(self, e) -> None:
        i = 0 if e.position().x() < self.width() / 2 else 1
        if i != self.index:
            sfx.play("pick")
            self.index = i
            self._pos.to(float(i), 280)
            self.changed.emit(i)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(S(1), S(1), -S(1), -S(1))
        p.setPen(QPen(QColor("#252C31"), S(1.2)))
        p.setBrush(QColor("#0B0F11"))
        p.drawRoundedRect(r, S(10), S(10))
        half = r.width() / 2
        knob = QRectF(r.left() + S(3) + self._pos.level * half, r.top() + S(3), half - S(6), r.height() - S(6))
        g = QLinearGradient(knob.topLeft(), knob.bottomLeft())
        g.setColorAt(0.0, mix(ui.accent, QColor("#FFFFFF"), 0.18))
        g.setColorAt(1.0, ui.accent)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(knob, S(8), S(8))
        f = font(10.5, QFont.Weight.ExtraBold)
        p.setFont(f)
        fm = QFontMetrics(f)
        on_text = QColor("#0B0E10") if ui.accent.lightnessF() > 0.55 else QColor("#FFFFFF")
        for i, text in enumerate(self.labels):
            cell = QRectF(r.left() + i * half + S(6), r.top(), half - S(12), r.height())
            near = max(0.0, 1.0 - abs(self._pos.level - i))         # 1 = this side is lit
            dark = QColor("#4A535B") if i != self._hover else QColor("#7A848C")
            p.setPen(mix(dark, on_text, near))
            p.drawText(cell, int(Qt.AlignmentFlag.AlignCenter),
                       fm.elidedText(text, Qt.TextElideMode.ElideRight, int(cell.width())))


class SlideBox(QWidget):
    """Holds one page of content; a new one slides in from the side while the old one slides out."""

    def __init__(self, width: int) -> None:
        super().__init__()
        self.setFixedWidth(width)
        self.cur = self.old = None
        self._dir = 1
        self._t = Tween(self, 1.0, self._place)

    def put(self, w: QWidget, direction: int = 0) -> None:
        w.setParent(self)
        w.setFixedWidth(self.width())
        if w.layout() is not None:
            w.layout().activate()
            w.setFixedHeight(w.layout().sizeHint().height())
        self._t.stop()
        if self.old is not None:                     # a slide still running: finish it at once
            self.old.deleteLater()
            self.old = None
        self.old, self.cur = self.cur, w
        w.show()
        if self.old is None or not direction:
            if self.old is not None:
                self.old.deleteLater()
                self.old = None
            w.move(0, 0)
            self._height(w.height())
            return
        self._dir = direction
        self._height(max(w.height(), self.old.height()))
        self._t._value = 0.0
        self._place()
        self._t.to(1.0, 300)

    def _height(self, h: int) -> None:
        if h != self.height():
            self.setFixedHeight(h)
            refit_scroll(self)

    def _place(self) -> None:
        if self.cur is None:
            return
        v = self._t.level
        self.cur.move(int((1.0 - v) * self._dir * self.width()), 0)
        if self.old is not None:
            self.old.move(int(-v * self._dir * self.width()), 0)
            if v >= 1.0:
                self.old.deleteLater()
                self.old = None
                self._height(self.cur.height())


def _trade_pool(page, link, mine: list, offer) -> QWidget:
    """Your side of the switch: your tradeable items, click one to add it."""
    ctx, ec = page.ctx, page.ctx.econ
    box = QWidget()
    lay = vbox(box, 6)
    offered = {r["id"] for r in mine}
    pool = [i for i in ec.items if not i.get("locked") and i["id"] not in offered
            and ec.info(i["item"]).get("tradeable") and ec.info(i["item"]).get("kind") != "coupon"]
    pool.sort(key=lambda i: (-value_of(ctx, i["item"]), i["item"]))
    if not pool:
        lay.addWidget(Label(tr("Nothing more to add."), 11.5, TEXT_DIM))
        return box
    lay.addWidget(Label(tr("Click an item to add it to your offer."), 10.5, TEXT_DIM, wrap_w=page.W))
    pool = pool[:60]
    grid = ItemGrid(ctx, [{"item": i["item"], "text": coins_text(value_of(ctx, i["item"]))} for i in pool], page.W, 6, 64)

    def add(i: int) -> None:
        if len(mine) >= 8:
            return ctx.toast(tr("8 items at most"), "warn")
        sfx.play("pick")
        offer([r["id"] for r in mine] + [pool[i]["id"]], None)
    grid.picked.connect(add)
    lay.addWidget(grid)
    return box


def _trade_peek(page, link, them: str) -> QWidget:
    """Their side of the switch: what they could trade. Only to look at, nothing here can be changed."""
    ctx = page.ctx
    box = QWidget()
    lay = vbox(box, 6)
    pk = link.peek if link.peek.get("trade") == link.trade_id else {}
    if "items" not in pk:
        lay.addWidget(Label(tr("Loading {name}'s items…", name=them), 11.5, TEXT_DIM))
        return box
    items = pk["items"]
    if not items:
        lay.addWidget(Label(tr("{name} has nothing to trade.", name=them), 11.5, TEXT_DIM, wrap_w=page.W))
        return box
    lay.addWidget(Label(tr("Look only: ask {name} in the chat to add something.", name=them), 10.5, TEXT_DIM,
                        wrap_w=page.W))
    grid = ItemGrid(ctx, [{"item": i["item"], "text": coins_text(int(i.get("worth") or 0)),
                           "mark": "offered" if i.get("offered") else ""} for i in items[:60]], page.W, 6, 64)
    grid.picked.connect(lambda _i: ctx.toast(tr("This is {name}'s inventory: you can only look.", name=them)))
    lay.addWidget(grid)
    return box


def _trade_summary(page, lay, link, them: str) -> None:
    """After the trade: what you got and what you gave, as the server recorded it."""
    ctx = page.ctx
    sm = link.summary if link.summary.get("id") == link.trade_id else None
    if sm is None:
        lay.addWidget(Label(tr("Trade done! Loading the summary…"), 13, READY_GREEN, bold=True, wrap_w=page.W))
        tid = link.trade_id

        def got(ok: bool, data) -> None:
            if tid != link.trade_id:
                return
            link.summary = data if ok and isinstance(data, dict) else {"id": tid, "failed": True}
            link.summary["id"] = tid
            ctx.reload_page("friends")
        ctx.online.ask("rb_trade_summary", {"trade": tid}, got, raw=True)
        return
    lay.addWidget(Label(tr("Trade complete ✓"), 17, READY_GREEN, bold=True))
    if sm.get("failed"):
        lay.addWidget(Label(tr("The items are in your Inventory."), 12, TEXT_DIM, wrap_w=page.W))
        return
    worth_got = sum(int(i.get("worth") or 0) for i in sm.get("got") or []) + int(sm.get("coins_got") or 0)
    worth_gave = sum(int(i.get("worth") or 0) for i in sm.get("gave") or []) + int(sm.get("coins_gave") or 0)

    def part(title: str, rows: list, coins: int, keys: int, sign: str, colour: str) -> None:
        head = hbox(spacing=6)
        head.addWidget(Label(title, 12.5, colour, bold=True), 1)
        lay.addLayout(head)
        if rows:
            lay.addWidget(ItemGrid(ctx, [{"item": r["item"], "text": sign + coins_text(int(r.get("worth") or 0))}
                                         for r in rows], page.W, 6, 64, moving=False))
        elif not coins and not keys:
            lay.addWidget(Label(tr("Nothing"), 11, TEXT_FAINT))
        if coins or keys:
            lay.addWidget(AmountRow(coins, keys, sign=sign, colour=colour, skip_zero=True))
    part(tr("You received from {name}", name=sm.get("other") or them), sm.get("got") or [],
         int(sm.get("coins_got") or 0), int(sm.get("keys_got") or 0), "+", READY_GREEN)
    part(tr("You gave"), sm.get("gave") or [], int(sm.get("coins_gave") or 0), int(sm.get("keys_gave") or 0),
         "−", LOSS_RED)
    net = worth_got - worth_gave
    lay.addWidget(Label(tr("Value change: about {v}", v=("+" if net >= 0 else "−") + coins_text(abs(net))), 11.5,
                        READY_GREEN if net >= 0 else LOSS_RED, bold=True))
    lay.addWidget(Label(tr("Everything is already in your Inventory."), 10.5,
                        TEXT_DIM, wrap_w=page.W))


def build_trade(page, lay) -> None:
    """The trade screen (inside the Social tab)."""
    ctx, ec, link = page.ctx, page.ctx.econ, page.ctx.trade
    d = link.data
    if not d:
        lay.addWidget(Label(tr("Opening the trade…"), 12, TEXT_DIM))
        return
    me = d.get("me", "a")
    other = "b" if me == "a" else "a"
    them = d.get(other, "?")
    state = d.get("state")
    top = hbox(spacing=8)
    top.addWidget(Label(tr("Trade with {name}", name=them), 15, bold=True), 1)
    leave = Button(tr("Close") if state in ("done", "cancelled") else tr("Cancel trade"), "ghost", 28)

    def stop() -> None:
        if state in ("asked", "open"):
            ec.call("rb_trade_cancel", {"trade": link.trade_id}, lambda _o, _d: ec.refresh())
        link.close()
        ctx.reload_page()
    leave.clicked.connect(stop)
    top.addWidget(leave)
    lay.addLayout(top)
    if state in ("asked", "open"):
        lock_strip(ctx, lay, "trading", page.W)                     # 4.0: paused by the admins
    if state == "asked":
        lay.addWidget(Label(tr("Waiting for {name} to accept… (5 minutes at most)", name=them), 12, TEXT_DIM, wrap_w=page.W))
        return
    if state == "done":
        return _trade_summary(page, lay, link, them)
    if state == "cancelled":
        why = {"expired": "The trade ended: a user left or took too long.", "failed": "The trade could not be done: nothing was exchanged."
               }.get(d.get("why"), "The trade was cancelled. Nothing was exchanged.")
        lay.addWidget(Label(tr(why), 12.5, "#FF9A9A", wrap_w=page.W))
        return
    items = d.get("items") or []
    mine = [i for i in items if i.get("side") == me]
    theirs = [i for i in items if i.get("side") == other]
    my_coins, their_coins = int(d.get(me + "_coins") or 0), int(d.get(other + "_coins") or 0)
    my_keys, their_keys = int(d.get(me + "_keys") or 0), int(d.get(other + "_keys") or 0)      # 3.2: keys can be traded
    my_ready, their_ready = bool(d.get(me + "_ready")), bool(d.get(other + "_ready"))
    my_ok, their_ok = bool(d.get(me + "_ok")), bool(d.get(other + "_ok"))
    give = sum(int(i.get("estimate") or 0) for i in mine) + my_coins
    get = sum(int(i.get("estimate") or 0) for i in theirs) + their_coins
    version = int(d.get("version") or 0)

    def offer(ids: list, coins, keys: int = None) -> None:
        link.act("rb_trade_offer", {"items": ids, "coins": my_coins if coins is None else coins,
                                    "keys": my_keys if keys is None else keys})

    # who is ready: both players, side by side, flashing when it just changed
    now = (my_ready, my_ok, their_ready, their_ok)
    was = link.shown_ready if link.shown_trade == link.trade_id else now
    link.shown_ready, link.shown_trade = now, link.trade_id
    pills = hbox(spacing=8)
    pills.addWidget(ReadyPill(tr("You"), my_ready, my_ok, was[:2] != now[:2]), 1)
    pills.addWidget(ReadyPill(them, their_ready, their_ok, was[2:] != now[2:]), 1)
    lay.addLayout(pills)

    def side(title: str, rows: list, coins: int, total: int, removable: bool, keys: int) -> None:
        lay.addWidget(Label(title, 12, bold=True))
        entries = [{"item": r["item"], "text": coins_text(int(r.get("estimate") or 0))} for r in rows]
        entries += [{"empty": True}] * (8 - len(entries))
        grid = ItemGrid(ctx, entries, page.W, 8, 60)
        if removable:
            grid.setToolTip(tr("Click an item to take it back"))
            grid.picked.connect(lambda i: offer([r["id"] for k, r in enumerate(mine) if k != i], None))
        lay.addWidget(grid)
        lay.addWidget(AmountRow(coins, keys, tr("Worth about {v}", v=coins_text(total))))
        if not removable:
            return
        row = hbox(spacing=6)
        row.addStretch(1)
        kb = Button(tr("Keys"), "ghost", 26, icon="key")

        def change_keys() -> None:
            def got(n: int, dlg) -> None:
                if n > ec.keys:
                    return dlg.say(tr("You have {n} keys", n=ec.keys))
                if n > 99:
                    return dlg.say(tr("99 at most"))
                dlg.close()
                offer([r["id"] for r in mine], None, n)
            ask_number(ctx, tr("Keys to give"), str(keys), tr("OK"), got, tr("You have {n} keys.", n=ec.keys))
        kb.clicked.connect(change_keys)
        row.addWidget(kb)
        b = Button(tr("Change coins"), "ghost", 26)

        def change() -> None:
            def got(n: int, dlg) -> None:
                if n > ec.coins:
                    return dlg.say(tr("Not enough coins"))
                dlg.close()
                offer([r["id"] for r in mine], n)
            ask_number(ctx, tr("Coins to give"), str(coins), tr("OK"), got,
                       tr("You have {n} coins.", n=coins_text(ec.coins)))
        b.clicked.connect(change)
        row.addWidget(b)
        lay.addLayout(row)
    side(tr("You give"), mine, my_coins, give, True, my_keys)
    side(tr("{name} gives", name=them), theirs, their_coins, get, False, their_keys)
    if give > max(get * 2, get + 500):
        lay.addWidget(Label(tr("Uneven trade: you give much more than you get."), 11.5, "#FFB020",
                            bold=True, wrap_w=page.W))
    if my_ready and their_ready:
        cd = Countdown(link)
        lay.addWidget(cd)
        line = hbox(spacing=6)
        back = Button(tr("Not ready"), "ghost", 36)
        back.clicked.connect(lambda: link.act("rb_trade_ready", {"ready": False, "seen_version": version}))
        go = Button(tr("Waiting for {name}…", name=them) if my_ok else tr("Confirm trade"), "primary", 36)
        go.setEnabled(link.wait_left() <= 0 and not my_ok)
        cd.done.connect(lambda: go.setEnabled(not my_ok))
        go.clicked.connect(lambda: (go.setEnabled(False), link.act("rb_trade_confirm", {"seen_version": version})))
        line.addWidget(back, 1)
        line.addWidget(go, 2)
        lay.addLayout(line)
        if their_ok and not my_ok:
            lay.addWidget(Label(tr("{name} confirmed. Your turn.", name=them), 11, READY_GREEN))
    else:
        ready = Button(tr("Not ready") if my_ready else tr("Ready"), "ghost" if my_ready else "primary", 36)
        ready.clicked.connect(lambda: link.act("rb_trade_ready", {"ready": not my_ready, "seen_version": version}))
        lay.addWidget(ready)
    lay.addWidget(Label(tr("Any change to the offer sets both players back to Not ready."), 10.5,
                        TEXT_DIM, wrap_w=page.W))

    # the two inventories
    switch = InvSwitch([tr("YOUR INVENTORY"), tr("{name}'S INVENTORY", name=them.upper())], 1 if link.view else 0)
    lay.addWidget(switch)
    box = SlideBox(page.W)
    lay.addWidget(box)

    def fill(direction: int = 0) -> None:
        try:
            box.put(_trade_peek(page, link, them) if link.view else _trade_pool(page, link, mine, offer), direction)
        except RuntimeError:                         # the page was rebuilt meanwhile
            pass

    def fetch() -> None:
        pk = link.peek
        if pk.get("trade") == link.trade_id and pk.get("version") == version and "items" in pk:
            return
        tid = link.trade_id

        def got(ok: bool, data) -> None:
            if tid != link.trade_id or not ok or not isinstance(data, dict):
                return
            link.peek = {"trade": tid, "version": version, "items": data.get("items") or []}
            if link.view:
                fill()
        ctx.online.ask("rb_trade_inventory", {"trade": tid}, got, raw=True)

    def flip(i: int) -> None:
        link.view = i
        fill(1 if i else -1)
        if i:
            fetch()
    switch.changed.connect(flip)
    fill()
    if link.view:
        fetch()
