w=open('rubenium/window.py').read()
def rep(a,b):
    global w
    assert a in w, a[:70]; w=w.replace(a,b)
rep('''COMPACT = CHROME_TOP - 12      # how much the menu bar gives back to the music when it hides''','''COMPACT = TAB_H + 10           # the tab row squashes away; the title and the R button stay''')
rep('''    def offset(self) -> int:
        return int(round((1.0 - self.win.chrome.level) * S(COMPACT)))

    def resizeEvent(self, _e) -> None:
        pad, w, off = S(PAD), self.width(), self.offset()
        level = self.win.chrome.level
        self.to_ball.move(w - pad - self.to_ball.width() + S(2),
                          S(HEADER_TOP) + (S(HEADER_H) - self.to_ball.height()) // 2 - off)
        self.tabbar.setGeometry(pad, S(HEADER_TOP + HEADER_H + 8) - off, w - 2 * pad, S(TAB_H))
        self.host.setGeometry(pad, S(CHROME_TOP) - off, w - 2 * pad + S(ScrollArea.GUTTER),
                              max(0, self.height() - S(CHROME_TOP + CHROME_BOTTOM) + off))
        fade = max(0.0, min(1.0, (level - 0.25) / 0.75))       # the bar fades before it slides away
        self.to_ball.fade = fade
        self.tabbar.fade = fade
        shown = level > 0.04                                   # hidden controls never catch a click
        self.to_ball.setVisible(shown)
        self.tabbar.setVisible(shown)
        self.to_ball.update()
        self.tabbar.update()''','''    def offset(self) -> int:
        return int(round((1.0 - self.win.chrome.level) * S(COMPACT)))

    def resizeEvent(self, _e) -> None:
        pad, w, off = S(PAD), self.width(), self.offset()
        level = self.win.chrome.level
        self.to_ball.move(w - pad - self.to_ball.width() + S(2),
                          S(HEADER_TOP) + (S(HEADER_H) - self.to_ball.height()) // 2)
        self.tabbar.setGeometry(pad, S(HEADER_TOP + HEADER_H + 8), w - 2 * pad, max(1, int(round(S(TAB_H) * level))))
        self.host.setGeometry(pad, S(CHROME_TOP) - off, w - 2 * pad + S(ScrollArea.GUTTER),
                              max(0, self.height() - S(CHROME_TOP + CHROME_BOTTOM) + off))
        self.tabbar.fade = max(0.0, min(1.0, (level - 0.2) / 0.8))     # squashes and fades together
        self.tabbar.setVisible(level > 0.04)                             # a hidden bar never catches a click
        self.tabbar.update()
        page = self.win.page()
        if page is not None and hasattr(page, "set_compact"):
            page.set_compact(level)''')
rep('''        level = self.win.chrome.level
        if level < 0.02:
            return
        p.setOpacity(max(0.0, min(1.0, (level - 0.25) / 0.75)))
        p.translate(0, -self.offset())
        p.setFont(font(18, QFont.Weight.ExtraBold, 0.4))''','''        p.setFont(font(18, QFont.Weight.ExtraBold, 0.4))''')
open('rubenium/window.py','w').write(w)

s=open('rubenium/widgets.py').read()
def rp(a,b):
    global s
    assert a in s, a[:70]; s=s.replace(a,b)
# TabBar: draw at full height, scaled down vertically when squashed
rp('''        self._tabs = tabs
        self._current = current
        self._hover_i = -1
        self.setFixedHeight(S(30))''','''        self._tabs = tabs
        self._current = current
        self._hover_i = -1
        self._full_h = S(30)
        self.setMinimumHeight(1)
        self.setMaximumHeight(self._full_h)
        self.resize(self.width(), self._full_h)''')
rp('''            out.append(QRectF(x, 0, w, self.height()))''','''            out.append(QRectF(x, 0, w, self._full_h))''')
rp('''        p.setOpacity(self.fade)
        slot = self._slot()''','''        p.setOpacity(self.fade)
        if self.height() < self._full_h:                    # squashing away
            p.translate(0, self.height() / 2)
            p.scale(1.0, self.height() / self._full_h)
            p.translate(0, -self._full_h / 2)
        slot = self._slot()''')
rp('''                p.drawText(QRectF(r.left() + slot - S(3), 0, self._lw[i], self.height()),''','''                p.drawText(QRectF(r.left() + slot - S(3), 0, self._lw[i], self._full_h),''')
# Button fade
rp('''        self._font = font(12, QFont.Weight.DemiBold)

    def set_text''','''        self._font = font(12, QFont.Weight.DemiBold)
        self.fade = 1.0

    def set_text''')
rp('''        h, pr = self._hover.level, self._press.level
        if not self.isEnabled():
            p.setOpacity(0.4)
            h = pr = 0''','''        h, pr = self._hover.level, self._press.level
        if self.fade < 0.01:
            return
        p.setOpacity(self.fade)
        if not self.isEnabled():
            p.setOpacity(0.4 * self.fade)
            h = pr = 0''')
rp('''    def mousePressEvent(self, e) -> None:
        self._press.to(1.0, 80)
        super().mousePressEvent(e)''','''    def mousePressEvent(self, e) -> None:
        if self.fade < 0.5:                                 # faded out: let the click through
            e.ignore()
            return
        self._press.to(1.0, 80)
        super().mousePressEvent(e)''')
open('rubenium/widgets.py','w').write(s)

p=open('rubenium/pages.py').read()
a='''    def on_hide(self) -> None:
        self._timer.stop()
        self._vol_timer.stop()'''
assert a in p
p=p.replace(a,'''    def set_compact(self, level: float) -> None:
        """The menu bar is hiding: the music app name fades with it."""
        self.chip.fade = max(0.0, min(1.0, (level - 0.2) / 0.8))
        self.chip.update()

    def on_hide(self) -> None:
        self._timer.stop()
        self._vol_timer.stop()''')
open('rubenium/pages.py','w').write(p)
