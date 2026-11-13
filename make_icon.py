"""Draws rubenium.ico in code (glowing green R in a circle), sizes 16-256."""
import sys
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QRadialGradient

app = QGuiApplication(sys.argv)
img = QImage(256, 256, QImage.Format.Format_ARGB32)
img.fill(Qt.GlobalColor.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.RenderHint.Antialiasing)
g = QRadialGradient(QPointF(128, 128), 128)
g.setColorAt(0.70, QColor(29, 185, 84, 150))
g.setColorAt(1.00, QColor(29, 185, 84, 0))
p.setPen(Qt.PenStyle.NoPen)
p.setBrush(g)
p.drawEllipse(QPointF(128, 128), 128, 128)
p.setBrush(QColor("#0B0F10"))
p.drawEllipse(QPointF(128, 128), 100, 100)
f = QFont("Segoe UI")
f.setPixelSize(140)
f.setWeight(QFont.Weight.ExtraBold)
p.setFont(f)
p.setPen(QColor("#1DB954"))
p.drawText(img.rect(), int(Qt.AlignmentFlag.AlignCenter), "R")
p.end()
if not img.save("rubenium.ico"):          # Qt's ICO writer stores the 256 px image; Windows scales it
    img.save("rubenium.png")
    raise SystemExit("Could not write rubenium.ico (saved rubenium.png instead)")
print("rubenium.ico written")
