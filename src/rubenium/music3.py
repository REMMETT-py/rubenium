"""3.2: the music app Play opens (asked the first time, changeable in Settings) and muting adverts.

Rubenium works with every music app, so it no longer assumes Spotify: the first time you press Play with no music
app open, you pick yours. Adverts: while the music app plays an advert (Spotify Free shows "Advertisement" or
"Spotify" as the song), its sound is muted, and turned back on when the music comes back. On by default."""
import logging
import time

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from . import win
from .core import S, sfx, TEXT, TEXT_DIM, alpha, font, mix, tr, ui
from .widgets import Button, Label, hbox, vbox

log = logging.getLogger("rubenium.music")

# id, name, colour, what to open (the app first, then its website)
MUSIC_APPS = [
    ("spotify", "Spotify", "#1DB954", ["spotify:", "https://open.spotify.com"]),
    ("apple", "Apple Music", "#FA2D48", [r"shell:AppsFolder\AppleInc.AppleMusicWin_nzyj5cx40ttqa!App", "https://music.apple.com"]),
    ("ytmusic", "YouTube Music", "#FF0033", ["https://music.youtube.com"]),
    ("deezer", "Deezer", "#A238FF", ["deezer://", "https://www.deezer.com"]),
    ("tidal", "TIDAL", "#FFFFFF", ["tidal://", "https://listen.tidal.com"]),
    ("amazon", "Amazon Music", "#25D1DA", [r"shell:AppsFolder\AmazonMobileLLC.AmazonMusic_kc6t79cpj4tp0!AmazonMobileLLC.AmazonMusic",
                                           "https://music.amazon.com"]),
    ("soundcloud", "SoundCloud", "#FF5500", ["https://soundcloud.com"]),
    ("youtube", "YouTube", "#FF0000", ["https://www.youtube.com"]),
]
APP_IDS = [a[0] for a in MUSIC_APPS]


def app_name(ident: str) -> str:
    return next((a[1] for a in MUSIC_APPS if a[0] == ident), "")


def open_music_app(ctx, ident: str) -> bool:
    """Open the music app (or its website). Returns False when nothing could be opened."""
    app = next((a for a in MUSIC_APPS if a[0] == ident), None)
    if app is None:
        return False
    for target in app[3]:
        if win.open_path(target):
            return True
    return False


def play_with_nothing_open(ctx) -> None:
    """Play was pressed and no music app is running: open the one the user picked, or ask which one."""
    ident = ctx.cfg["music_app"]
    if ident in APP_IDS:
        if not open_music_app(ctx, ident):
            ctx.toast(tr("Could not open {app}", app=app_name(ident)), "warn")
        else:
            ctx.toast(tr("Opening {app}…", app=app_name(ident)))
        return
    ask_music_app(ctx)


def ask_music_app(ctx, then_open: bool = True) -> None:
    w = MusicAppPicker(ctx, then_open)
    ctx.window.embed(w)


class MusicAppTile(QWidget):
    picked = pyqtSignal(str)

    def __init__(self, app: tuple, current: bool) -> None:
        super().__init__()
        self.app, self.current = app, current
        self.setFixedHeight(S(48))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hover = False

    def enterEvent(self, _e) -> None:
        self.hover = True
        self.update()

    def leaveEvent(self, _e) -> None:
        self.hover = False
        self.update()

    def mousePressEvent(self, e) -> None:
        e.accept()

    def mouseReleaseEvent(self, e) -> None:
        if self.rect().contains(e.position().toPoint()):
            self.picked.emit(self.app[0])

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        col = QColor(self.app[2])
        p.setPen(QPen(ui.accent if self.current else alpha(col, 0.5 if self.hover else 0.2), S(1.6) if self.current else 1))
        p.setBrush(alpha(col, 0.14 if self.hover else 0.07))
        p.drawRoundedRect(r, S(11), S(11))
        c = r.left() + S(24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawEllipse(QRectF(c - S(12), r.center().y() - S(12), S(24), S(24)))
        p.setPen(QColor("#0B0E10") if col.lightnessF() > 0.6 else QColor("#FFFFFF"))
        p.setFont(font(12, QFont.Weight.Black))
        p.drawText(QRectF(c - S(12), r.center().y() - S(12), S(24), S(24)), int(Qt.AlignmentFlag.AlignCenter), self.app[1][0])
        p.setPen(QColor(TEXT))
        p.setFont(font(12.5, QFont.Weight.Bold))
        p.drawText(r.adjusted(S(46), 0, -S(8), 0), int(Qt.AlignmentFlag.AlignVCenter), self.app[1])


class MusicAppPicker(QWidget):
    """Which music app do you use? Shown inside the menu the first time Play opens one (and from Settings)."""

    def __init__(self, ctx, then_open: bool = True) -> None:
        super().__init__()
        self.ctx, self.then_open = ctx, then_open
        self.setFixedWidth(ctx.window.page_w())
        lay = vbox(self, 8)
        lay.addWidget(Label(tr("Which music app do you use?"), 15, bold=True))
        grid = QWidget()
        from PyQt6.QtWidgets import QGridLayout
        gl = QGridLayout(grid)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(S(6))
        for i, app in enumerate(MUSIC_APPS):
            t = MusicAppTile(app, ctx.cfg["music_app"] == app[0])
            t.picked.connect(self._pick)
            gl.addWidget(t, i // 2, i % 2)
        lay.addWidget(grid)
        later = Button(tr("No preference for now"), "ghost", 32)          # 4.6: asked again next time
        later.clicked.connect(self._close)
        lay.addWidget(later)

    def _pick(self, ident: str) -> None:
        sfx.play("on")
        self.ctx.cfg["music_app"] = ident
        self.ctx.cfg.save()
        self._close()
        if self.then_open:
            if open_music_app(self.ctx, ident):
                self.ctx.toast(tr("Opening {app}…", app=app_name(ident)))
            else:
                self.ctx.toast(tr("Could not open {app}", app=app_name(ident)), "warn")
        else:
            self.ctx.toast(tr("Music app: {name}", name=app_name(ident)))
            self.ctx.reload_page()

    def _close(self) -> None:
        self.ctx.window.unembed(self)
        self.deleteLater()


# ================================================================ adverts
AD_WORDS = ("advertisement", "advert", "publicité", "publicite", "werbung", "anuncio", "pubblicità", "spotify free",
            "ad", "ads", "annonce", "sponsored", "sponsorisé", "sponsorise", "pub")     # 4.6: YouTube's names for ads


def is_advert(st) -> bool:
    """Is the music app playing an advert right now? (Spotify Free names the song "Advertisement" or "Spotify",
    with no artist; other apps name it as an advert.)"""
    if st is None or not getattr(st, "has_track", False):
        return False
    title = (st.title or "").strip().lower()
    artist = (st.artist or "").strip().lower()
    src = (st.source_id or "").lower()
    if any(w == title or title.startswith(w + " ") for w in AD_WORDS if len(w) > 3):
        return True
    if title in AD_WORDS or any(title.startswith(w + sep) for w in ("ad", "ads", "annonce", "pub") for sep in (" · ", ": ", " - ", " • ")):
        return True                                   # 4.6: YouTube in a browser names its ads "Ad", "Annonce"...
    if "spotify" in src:
        if title in ("spotify", "advertisement", "spotify free") or (not artist and title in ("", "spotify")):
            return True
        if artist == "spotify" and not (st.album or "").strip():
            return True
    return False


class AdMuter:
    """Mutes the music app while an advert plays and gives the sound back after. Only ever un-mutes what it muted."""

    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.muted_by_us = None          # the matcher of the app we muted
        self._last = 0.0

    def on_state(self, st) -> None:
        ad = bool(self.ctx.cfg["ad_mute"]) and is_advert(st)
        try:
            if ad and self.muted_by_us is None and st.source_id:
                from .media import source_keywords
                match = win.AppVolume.matcher(st.source_id, source_keywords(st.source_id))
                if match is None:
                    return
                got = self.ctx.appvol.get(match)
                if got is not None and not got[1]:          # only if it is not muted already
                    if self.ctx.appvol.set_mute(match, True):
                        self.muted_by_us = match
                        log.info("advert: muted %s", st.source_id)
            elif not ad and self.muted_by_us is not None:
                self.release()
        except Exception:  # noqa: BLE001
            log.exception("advert mute failed")

    def release(self) -> None:
        match, self.muted_by_us = self.muted_by_us, None
        if match is not None:
            try:
                self.ctx.appvol.set_mute(match, False)
                log.info("advert over: sound back")
            except Exception:  # noqa: BLE001
                log.exception("advert unmute failed")
