"""Draws rubenium.ico in code: a black tile with a white R. The R is built from shapes, so no font is needed
(the build machine has none)."""
import sys
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPolygonF

app = QGuiApplication(sys.argv)
N = 256


def r_mark(u: float) -> QPainterPath:
    stem = QPainterPath()
    stem.addRect(QRectF(.30 * u, .24 * u, .13 * u, .52 * u))
    outer = QPainterPath()
    outer.addRect(QRectF(.30 * u, .24 * u, .26 * u, .30 * u))
    bulge = QPainterPath()
    bulge.addEllipse(QPointF(.56 * u, .39 * u), .15 * u, .15 * u)
    inner = QPainterPath()
    inner.addRect(QRectF(.43 * u, .35 * u, .13 * u, .08 * u))
    hole = QPainterPath()
    hole.addEllipse(QPointF(.56 * u, .39 * u), .04 * u, .04 * u)
    leg = QPainterPath()
    leg.addPolygon(QPolygonF([QPointF(.47 * u, .53 * u), QPointF(.61 * u, .53 * u), QPointF(.74 * u, .76 * u),
                              QPointF(.60 * u, .76 * u)]))
    leg.closeSubpath()
    return stem.united(outer.united(bulge).subtracted(inner.united(hole))).united(leg)


img = QImage(N, N, QImage.Format.Format_ARGB32)
img.fill(Qt.GlobalColor.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.RenderHint.Antialiasing)
p.setPen(Qt.PenStyle.NoPen)
p.setBrush(QColor("#0A0A0A"))
p.drawRoundedRect(QRectF(4, 4, N - 8, N - 8), 56, 56)
p.setBrush(QColor("#FFFFFF"))
p.drawPath(r_mark(N))
p.end()
if not img.save("rubenium.ico"):          # Qt's ICO writer stores the 256 px image; Windows scales it
    img.save("rubenium.png")
    raise SystemExit("Could not write rubenium.ico (saved rubenium.png instead)")
print("rubenium.ico written")
