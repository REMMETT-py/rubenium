"""Shop > Shop, Inventory and Market, and the trade screen. Everything of value is done by the server: this file
only shows it and asks. An item in a trade or on the market is locked by the server until it is over."""
import math
import random
import time

from PyQt6.QtCore import QObject, QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from .collection import SLOTS, is_secret, worn
from .core import DANGER, S, TEXT, TEXT_DIM, TEXT_FAINT, alpha, font, mix, sfx, tr, ui
from .cosmetics import (BALLS, COLOUR_NAMES, COLOUR_ORDER, FONTS, LINES, THEME_LOOKS, colour_of, item_name,
                        paint_cosmetic)
from .econ import CLASS_NAMES, RARITY_COLOURS, RARITY_NAMES
from .shop import GOLD_TEXT, clock_text, paint_price
from .wallet import coins_text, paint_coin
from .widgets import Button, IconButton, Label, Segmented, draw_icon, hbox, heading, vbox

KINDS = ["", "badge", "ball", "line", "font", "theme"]
REASONS = {"time": "Time with Rubenium", "shop": "Shop", "vendor": "Sold to the vendor", "case": "Case opened",
           "case_coins": "Coins from a case", "daily_case": "Daily case", "spin": "Free spin", "bet": "Bet",
           "win": "Casino win", "quest": "Quest", "minigame": "Beat Tap", "market_buy": "Bought on the market",
           "market_sell": "Sold on the market", "trade": "Trade", "gift": "Case gifted", "giveaway": "Giveaway",
           "admin": "From the admin", "import": "Old progress"}


class AskDialog(QWidget):
    """A small window with one text box (typing needs the keyboard, which the menu never takes from a game)."""

    def __init__(self, ctx, title: str, hint: str, button: str, on_text, max_len: int = 10, note: str = "") -> None:
        super().__init__()
        from PyQt6.QtWidgets import QLineEdit
        from .window import work_area
        self._on_text = on_text
        self.setWindowTitle("Rubenium")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
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
        area = work_area(ctx.window.card_global().center())
        self.move(area.center().x() - self.width() // 2, area.center().y() - self.height() // 2)
        self.show()
        self.raise_()
        self.activateWindow()
        self.edit.setFocus()

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
    return int(ctx.econ.info(item).get("value") or 0)


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
            if en.get("tag"):
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
            "theme": [(t[0], t[1]) for t in THEME_LOOKS]}[kind]


def build_cosmetics(page, lay) -> None:
    ctx, ec = page.ctx, page.ctx.econ
    if not ec.ready or not ec.catalog:
        return lay.addWidget(Label(tr("Connecting…") if ctx.online.logged_in() else tr("Log in to see the shop"), 12, TEXT_DIM))
    kind_i = int(getattr(ctx, "shop_kind", 0) or 0)
    kind = ("ball", "line", "font", "theme")[kind_i]
    design = getattr(ctx, "shop_design", None)
    if design is None:
        for sale in (ec.live.get("sales") or [])[:2]:
            lay.addWidget(SaleBanner(page, sale))
        seg = Segmented([tr("Balls"), tr("Lines"), tr("Fonts"), tr("Themes")], kind_i)

        def switch(i: int) -> None:
            ctx.shop_kind = i
            ctx.reload_page()
        seg.changed.connect(switch)
        lay.addWidget(seg)
        entries = []
        for base, name in _designs(kind):
            item = f"theme:{base}" if kind == "theme" else f"{kind}:{base}:{'white' if kind == 'font' else 'sky'}"
            cheapest = f"theme:{base}" if kind == "theme" else f"{kind}:{base}:grey"
            owned = any(k.startswith(f"{kind}:{base}") for k in ec._owned)
            pct = max((ec.sale(k) for k in ec.catalog if k.startswith(f"{kind}:{base}")), default=0)
            entries.append({"item": item, "price": ec.shop_price(cheapest), "tag": tr(name),
                            "mark": "sale" if pct else ("worn" if owned else ""), "pct": pct})
        grid = ItemGrid(ctx, entries, page.W, 3 if kind == "theme" else 5, 86 if kind != "theme" else 96)

        def pick(i: int) -> None:
            sfx.play("pick")
            ctx.shop_design, ctx.shop_colour = _designs(kind)[i][0], ""
            ctx.reload_page()
        grid.picked.connect(pick)
        lay.addWidget(grid)
        lay.addWidget(Label(tr("Everything here can be worn, traded and sold. Prices start at the one shown."), 10.5,
                            TEXT_DIM, wrap_w=page.W))
        return
    # one design: preview, colours, buy or wear
    names = dict(_designs(kind))
    variants = [""] if kind == "theme" else [c for c in COLOUR_ORDER if f"{kind}:{design}:{c}" in ec.catalog]
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
        on = ctx.shop_item_worn(item)
        b = Button(tr("Take off") if on else tr("Wear"), "ghost" if on else "primary", 38)

        def toggle() -> None:
            sfx.play("pick")
            ctx.take_off_shop_item(kind) if on else ctx.wear_shop_item(item)
            ctx.reload_page()
        b.clicked.connect(toggle)
        lay.addWidget(b)
        lay.addWidget(Label(tr("Sell it or put it on the market from your Inventory."), 10.5, TEXT_DIM, wrap_w=page.W))
    elif price is not None:
        text = tr("Buy for {n} coins", n=coins_text(price))
        if price != full:
            text += f"  (-{ec.sale(item)}%)"
        b = Button(text, "primary", 38)

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


def _cid(kind: str, design: str, colour: str) -> str:
    return f"theme:{design}" if kind == "theme" else f"{kind}:{design}:{colour}"


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


def build_inventory(page, lay) -> None:
    from .games import GamePicker
    ctx, ec = page.ctx, page.ctx.econ
    if not ec.ready:
        return lay.addWidget(Label(tr("Connecting…") if ctx.online.logged_in() else tr("Log in to see your items"), 12, TEXT_DIM))
    tab = int(getattr(ctx, "inv_tab", 0) or 0)
    picker = GamePicker([tr("All"), tr("Badges"), tr("Balls"), tr("Lines"), tr("Fonts"), tr("Themes"), tr("Coins")], tab)

    def switch(i: int) -> None:
        ctx.inv_tab, ctx.inv_pick = i, ""
        ctx.reload_page()
    picker.changed.connect(switch)
    lay.addWidget(picker)
    if tab == 6:
        rows = getattr(ctx, "ledger_rows", None)
        if rows is None or time.monotonic() - getattr(ctx, "ledger_at", 0) > 8:
            ctx.ledger_at = time.monotonic()

            def got(ok: bool, data) -> None:
                if ok and isinstance(data, list) and data != getattr(ctx, "ledger_rows", None):
                    ctx.ledger_rows = data
                    if ctx.window.current == "themes" and getattr(ctx, "inv_tab", 0) == 6:
                        ctx.reload_page()
            ec.online.ask("rb_ledger_list", {}, got)
        lay.addWidget(heading(tr("Coin history")))
        if rows:
            lay.addWidget(LedgerList(rows, page.W))
        else:
            lay.addWidget(Label(tr("Loading…") if rows is None else tr("Nothing here yet"), 12, TEXT_DIM))
        return
    want = KINDS[tab]
    groups: dict = {}
    for it in ec.items:
        if not want or it["item"].split(":")[0] == want:
            groups.setdefault(it["item"], []).append(it)
    order = sorted(groups, key=lambda k: (-value_of(ctx, k), k))
    total = sum(value_of(ctx, k) * len(v) for k, v in groups.items())
    count = sum(len(v) for v in groups.values())
    lay.addWidget(Label(tr("{n} items · worth about {v} coins", n=count, v=coins_text(total)), 11, TEXT_DIM))
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
        entries.append({"item": k, "text": coins_text(value_of(ctx, k)), "tag": f"×{len(groups[k])}" if len(groups[k]) > 1 else "",
                        "mark": "lock" if not free else ("worn" if k in wearing or ctx.shop_item_worn(k) else "")})
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
    note = tr("Worth about {v} coins", v=coins_text(value_of(ctx, item)))
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
    else:
        on = ctx.shop_item_worn(item)
        b = Button(tr("Take off") if on else tr("Wear"), "ghost" if on else "primary", 32)

        def wear() -> None:
            sfx.play("pick")
            ctx.take_off_shop_item(kind) if on else ctx.wear_shop_item(item)
            ctx.reload_page()
        b.clicked.connect(wear)
    line.addWidget(b, 1)
    sell = Button(tr("Sell"), "ghost", 32)
    sell.setEnabled(bool(free) and bool(ec.info(item).get("tradeable")))
    sell.setToolTip(tr("Put it on the market: other players buy it or make you an offer"))
    sell.clicked.connect(lambda: market_sell(ctx, item))
    line.addWidget(sell, 1)
    lay.addLayout(line)


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
                   tr("Usual price: about {v} coins. Choose between {a} and {b}. Players can buy it at your price or "
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
    from .games import GamePicker
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
    if not ec.can_trade():
        lay.addWidget(Label(tr("The market opens after 5 hours with Rubenium. You have {h} so far.",
                               h=f"{ec.minutes / 60:.1f} h"), 11, GOLD_TEXT, wrap_w=page.W))
    if tab == 2:
        return _offers(page, lay)
    fn, args = ("rb_market_mine", {}) if tab else \
        ("rb_market_browse", {"kind": KINDS[int(getattr(ctx, "mk_kind", 0) or 0)],
                              "sort": "cheap" if getattr(ctx, "mk_sort", 0) else "new", "page": 0})
    key = (fn, str(args))
    rows = getattr(ctx, "mk_rows", None) if getattr(ctx, "mk_key", None) == key else None
    if rows is None or time.monotonic() - getattr(ctx, "mk_at", 0) > 10:
        ctx.mk_at = time.monotonic()

        def got(ok: bool, data) -> None:
            if not ok or not isinstance(data, list):
                return
            changed = data != getattr(ctx, "mk_rows", None) or getattr(ctx, "mk_key", None) != key
            ctx.mk_rows, ctx.mk_key = data, key
            if changed and ctx.window.current == "themes" and getattr(ctx, "shop_tab", 0) == 4:
                ctx.reload_page()
        ec.online.ask(fn, args, got)
    if not tab:
        kinds = GamePicker([tr("All"), tr("Badges"), tr("Balls"), tr("Lines"), tr("Fonts"), tr("Themes")],
                           int(getattr(ctx, "mk_kind", 0) or 0))

        def set_kind(i: int) -> None:
            ctx.mk_kind, ctx.mk_at = i, 0
            ctx.reload_page()
        kinds.changed.connect(set_kind)
        lay.addWidget(kinds)
        sort = Segmented([tr("Newest"), tr("Cheapest")], int(getattr(ctx, "mk_sort", 0) or 0))

        def set_sort(i: int) -> None:
            ctx.mk_sort, ctx.mk_at = i, 0
            ctx.reload_page()
        sort.changed.connect(set_sort)
        lay.addWidget(sort)
    if rows is None:
        return lay.addWidget(Label(tr("Loading…"), 12, TEXT_DIM))
    if not rows:
        lay.addWidget(Label(tr("You have nothing on sale. Put an item on sale from your Inventory.") if tab else
                            tr("Nothing on sale right now. Be the first: put an item on sale from your Inventory."),
                            12, TEXT_DIM, wrap_w=page.W))
    for row in rows[:40]:
        if is_secret(row.get("item", "")):
            row = dict(row)
        w = ListingRow(ctx, row, page.W, mine=bool(tab))
        w.clicked.connect(lambda r=row: _market_click(page, r, bool(tab)))
        lay.addWidget(w)
    if not tab:
        lay.addWidget(Label(tr("The price is fixed by the seller. The market keeps 5% of every sale."), 10.5, TEXT_DIM,
                            wrap_w=page.W))


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
                if ctx.window.current == "themes" and getattr(ctx, "shop_tab", 0) == 4:
                    ctx.reload_page()
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
        self.got_at = 0.0
        self.busy = False
        self._sig = ""
        self._timer = QTimer(self)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(self.poll)

    def open(self, trade_id: str) -> None:
        if trade_id and trade_id != self.trade_id:
            self.trade_id, self.data, self._sig = trade_id, {}, ""
        self._timer.start()
        self.poll()

    def close(self) -> None:
        self._timer.stop()
        self.trade_id, self.data, self._sig = "", {}, ""

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
                                              "b_coins")]) + str(data.get("wait") is None)
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
    if state == "asked":
        lay.addWidget(Label(tr("Waiting for {name} to accept… (5 minutes at most)", name=them), 12, TEXT_DIM, wrap_w=page.W))
        return
    if state == "done":
        lay.addWidget(Label(tr("Trade done! The items are in your Inventory."), 13, "#5BE08A", bold=True, wrap_w=page.W))
        return
    if state == "cancelled":
        why = {"expired": "The trade ended: a player left or took too long.", "failed": "The trade could not be done: nothing was exchanged."
               }.get(d.get("why"), "The trade was cancelled. Nothing was exchanged.")
        lay.addWidget(Label(tr(why), 12.5, "#FF9A9A", wrap_w=page.W))
        return
    items = d.get("items") or []
    mine = [i for i in items if i.get("side") == me]
    theirs = [i for i in items if i.get("side") == other]
    my_coins, their_coins = int(d.get(me + "_coins") or 0), int(d.get(other + "_coins") or 0)
    my_ready, their_ready = bool(d.get(me + "_ready")), bool(d.get(other + "_ready"))
    my_ok, their_ok = bool(d.get(me + "_ok")), bool(d.get(other + "_ok"))
    give = sum(int(i.get("estimate") or 0) for i in mine) + my_coins
    get = sum(int(i.get("estimate") or 0) for i in theirs) + their_coins
    version = int(d.get("version") or 0)

    def offer(ids: list, coins: int) -> None:
        link.act("rb_trade_offer", {"items": ids, "coins": coins})

    def side(title: str, rows: list, coins: int, total: int, ready: bool, removable: bool) -> None:
        head = hbox(spacing=6)
        head.addWidget(Label(title, 12, bold=True), 1)
        head.addWidget(Label(tr("Ready") if ready else tr("Not ready"), 10.5, "#5BE08A" if ready else TEXT_FAINT, bold=True))
        lay.addLayout(head)
        entries = [{"item": r["item"], "text": coins_text(int(r.get("estimate") or 0))} for r in rows]
        entries += [{"empty": True}] * (8 - len(entries))
        grid = ItemGrid(ctx, entries, page.W, 8, 56)
        if removable:
            grid.picked.connect(lambda i: offer([r["id"] for k, r in enumerate(mine) if k != i], my_coins))
        lay.addWidget(grid)
        foot = hbox(spacing=6)
        foot.addWidget(Label(tr("Coins: {n}", n=coins_text(coins)), 11.5, GOLD_TEXT, bold=True))
        foot.addWidget(Label(tr("Worth about {v}", v=coins_text(total)), 10.5, TEXT_DIM), 1)
        if removable:
            b = Button(tr("Change coins"), "ghost", 24)

            def change() -> None:
                def got(n: int, dlg) -> None:
                    if n > ec.coins:
                        return dlg.say(tr("Not enough coins"))
                    dlg.close()
                    offer([r["id"] for r in mine], n)
                ask_number(ctx, tr("Coins to give"), "0", tr("OK"), got, tr("You have {n} coins.", n=coins_text(ec.coins)))
            b.clicked.connect(change)
            foot.addWidget(b)
        lay.addLayout(foot)
    side(tr("You give"), mine, my_coins, give, my_ready, True)
    side(tr("You get"), theirs, their_coins, get, their_ready, False)
    if give > max(get * 2, get + 500):
        lay.addWidget(Label(tr("Careful: you give much more than you get. Look again before you accept."), 11.5, "#FFB020",
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
            lay.addWidget(Label(tr("{name} confirmed. Your turn.", name=them), 11, "#5BE08A"))
        return
    ready = Button(tr("Not ready") if my_ready else tr("Ready"), "ghost" if my_ready else "primary", 36)
    ready.clicked.connect(lambda: link.act("rb_trade_ready", {"ready": not my_ready, "seen_version": version}))
    lay.addWidget(ready)
    lay.addWidget(Label(tr("Any change makes both players not ready again. Nothing moves until both confirm."), 10.5,
                        TEXT_DIM, wrap_w=page.W))
    offered = {r["id"] for r in mine}
    pool = [i for i in ec.items if not i.get("locked") and i["id"] not in offered
            and ec.info(i["item"]).get("tradeable")]
    pool.sort(key=lambda i: (-value_of(ctx, i["item"]), i["item"]))
    lay.addWidget(heading(tr("Your items (click to add)")))
    if not pool:
        lay.addWidget(Label(tr("Nothing more to add."), 11.5, TEXT_DIM))
        return
    pool = pool[:60]
    grid = ItemGrid(ctx, [{"item": i["item"], "text": coins_text(value_of(ctx, i["item"]))} for i in pool], page.W, 6, 62)

    def add(i: int) -> None:
        if len(mine) >= 8:
            return ctx.toast(tr("8 items at most"), "warn")
        sfx.play("pick")
        offer([r["id"] for r in mine] + [pool[i]["id"]], my_coins)
    grid.picked.connect(add)
    lay.addWidget(grid)
