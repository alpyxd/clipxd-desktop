"""Çizgi tarzı ikonlar (24x24 SVG) ve uygulama simgesi."""
from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer

# "CURRENT" = ikon rengi (dolgu gereken parçalar için)
_ICONS = {
    "download": '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v8.3M8.4 12.6 12 16.2l3.6-3.6"/>',
    "convert": ('<path d="M4.5 10.5a7.5 7.5 0 0 1 13.3-4.2L20 8.6"/><path d="M20 4.3v4.4h-4.4"/>'
                '<path d="M19.5 13.5a7.5 7.5 0 0 1-13.3 4.2L4 15.4"/><path d="M4 19.7v-4.4h4.4"/>'),
    "person": ('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="10" r="3.2"/>'
               '<path d="M6.6 18.2c1.3-2.2 3.2-3.3 5.4-3.3s4.1 1.1 5.4 3.3"/>'),
    "sliders": '<path d="M4 7h9M18 7h2M4 17h2M11 17h9"/><circle cx="15.5" cy="7" r="2.3"/><circle cx="8.5" cy="17" r="2.3"/>',
    "xmark": '<path d="M7.5 7.5l9 9M16.5 7.5l-9 9"/>',
    "retry": '<path d="M15.5 6.44A7 7 0 1 1 10.78 5.61"/><path d="M10.4 2.9 13.2 5.6 10.4 8.3"/>',
    "magnifier": '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5"/>',
    "folder": '<path d="M3.5 7.5a2 2 0 0 1 2-2h3.8l2 2h7.2a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
    "chevron_left": '<path d="M14.5 5.5 8 12l6.5 6.5"/>',
    "chevron_right": '<path d="M9.5 5.5 16 12l-6.5 6.5"/>',
    "chevron_down": '<path d="M6.5 9.5 12 15l5.5-5.5"/>',
    "chevrons_updown": '<path d="M8.2 9.3 12 5.5l3.8 3.8M8.2 14.7 12 18.5l3.8-3.8"/>',
    "lock": ('<rect x="6.5" y="10.5" width="11" height="9" rx="2" fill="CURRENT" stroke="none"/>'
             '<path d="M8.8 10.5V8a3.2 3.2 0 0 1 6.4 0v2.5"/>'),
    "share": ('<path d="M12 3.5v11M8.3 7.2 12 3.5l3.7 3.7"/>'
              '<path d="M8 10.5H6.5a1 1 0 0 0-1 1v7.5a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1v-7.5a1 1 0 0 0-1-1H16"/>'),
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "clipboard": ('<rect x="5.5" y="5" width="13" height="15.5" rx="2"/>'
                  '<path d="M9 5V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v1M9 11h6M9 15h4"/>'),
    "film": ('<rect x="3.5" y="5" width="17" height="14" rx="2.5"/>'
             '<path d="M8 5v14M16 5v14M3.5 9.5H8M3.5 14.5H8M16 9.5h4.5M16 14.5h4.5"/>'),
    "music": '<path d="M9 17.5V6.5l10-2v11"/><circle cx="6.8" cy="17.5" r="2.2"/><circle cx="16.8" cy="15.5" r="2.2"/>',
    "doc": ('<path d="M7.5 3.5h6L18 8v11a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 19V5a1.5 1.5 0 0 1 1.5-1.5z"/>'
            '<path d="M13.5 3.5V8H18"/>'),
    "photo": ('<rect x="3.5" y="5" width="17" height="14" rx="2.5"/><circle cx="9" cy="10" r="1.6"/>'
              '<path d="M4 17l4.5-4.5 3.5 3.5 2.5-2.5L20 18"/>'),
    "trash": ('<path d="M4.5 7h15M9.5 7V5a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v2"/>'
              '<path d="M6.5 7l.8 11.5a2 2 0 0 0 2 1.8h5.4a2 2 0 0 0 2-1.8L17.5 7"/>'),
    "star": '<path d="M12 4.2l2.4 4.9 5.4.8-3.9 3.8.9 5.4L12 16.6l-4.8 2.5.9-5.4-3.9-3.8 5.4-.8z"/>',
    "star_fill": '<path fill="CURRENT" d="M12 4.2l2.4 4.9 5.4.8-3.9 3.8.9 5.4L12 16.6l-4.8 2.5.9-5.4-3.9-3.8 5.4-.8z"/>',
    "check_circle": '<circle cx="12" cy="12" r="9" fill="CURRENT" stroke="none"/><path d="M8 12.3l2.7 2.7L16 9.6" stroke="#FFFFFF"/>',
    "error_circle": '<circle cx="12" cy="12" r="9" fill="CURRENT" stroke="none"/><path d="M12 7.5v5.3M12 16.3v.2" stroke="#FFFFFF"/>',
    "globe": ('<circle cx="12" cy="12" r="9"/>'
              '<path d="M3 12h18M12 3c2.5 2.6 3.7 5.6 3.7 9s-1.2 6.4-3.7 9c-2.5-2.6-3.7-5.6-3.7-9S9.5 5.6 12 3z"/>'),
    "shield": '<path d="M12 3.5 5 6.3v5.2c0 4.3 2.9 7.7 7 9 4.1-1.3 7-4.7 7-9V6.3z"/><path d="M9 12l2.2 2.2L15.2 10"/>',
    "link": ('<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/>'
             '<path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>'),
    "sidebar": '<rect x="3.5" y="5" width="17" height="14" rx="2.5"/><path d="M9.5 5v14M5.8 8.5h1.6M5.8 11h1.6"/>',
    "tray_down": '<path d="M12 4v10M8 10.5l4 4 4-4"/><path d="M4 14.5v3A2.5 2.5 0 0 0 6.5 20h11a2.5 2.5 0 0 0 2.5-2.5v-3"/>',
    "warning": ('<path d="M10.3 5 2.9 18a2 2 0 0 0 1.7 3h14.8a2 2 0 0 0 1.7-3L13.7 5a2 2 0 0 0-3.4 0z"/>'
                '<path d="M12 10v4M12 17.3v.2"/>'),
    "terminal": '<rect x="3.5" y="5" width="17" height="14" rx="2.5"/><path d="M7.5 10l2.5 2-2.5 2M12 14.5h4"/>',
    "key": '<circle cx="8" cy="15" r="4"/><path d="M11 12l8.5-8.5M16.5 6.5l2 2M14.5 8.5l1.5 1.5"/>',
    "list": ('<path d="M9.5 6.5h10.5M9.5 12h10.5M9.5 17.5h10.5"/><circle cx="5" cy="6.5" r="1.2" fill="CURRENT"/>'
             '<circle cx="5" cy="12" r="1.2" fill="CURRENT"/><circle cx="5" cy="17.5" r="1.2" fill="CURRENT"/>'),
    "scissors": ('<circle cx="6.5" cy="7" r="2.5"/><circle cx="6.5" cy="17" r="2.5"/>'
                 '<path d="M8.6 8.5 19 17M8.6 15.5 19 7"/>'),
}


def svg(name: str, color: str, stroke: float = 1.8) -> str:
    body = _ICONS[name].replace("CURRENT", color)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')


_renderers: dict = {}


def _renderer(name: str, color: str, stroke: float) -> QSvgRenderer:
    key = (name, color, stroke)
    r = _renderers.get(key)
    if r is None:
        r = QSvgRenderer(QByteArray(svg(name, color, stroke).encode("utf-8")))
        _renderers[key] = r
    return r


def paint(painter: QPainter, name: str, rect: QRectF, color, stroke: float = 1.8):
    col = QColor(color)
    hexcol = col.name(QColor.HexRgb)
    painter.save()
    if col.alphaF() < 1:
        painter.setOpacity(painter.opacity() * col.alphaF())
    _renderer(name, hexcol, stroke).render(painter, QRectF(rect))
    painter.restore()


def pixmap(name: str, color, size: int = 18, stroke: float = 1.8, dpr: float = 2.0) -> QPixmap:
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    paint(p, name, QRectF(0, 0, pm.width(), pm.height()), color, stroke)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, color, size: int = 18) -> QIcon:
    return QIcon(pixmap(name, color, size))


# ---------------------------------------------------------------- ClipXD logosu

BRAND_GRADIENT = ("#FF4D8D", "#8A4DFF", "#3DA5FF")  # pembe -> mor -> mavi


def brand_gradient(x1: float, y1: float, x2: float, y2: float) -> QLinearGradient:
    grad = QLinearGradient(x1, y1, x2, y2)
    for i, c in enumerate(BRAND_GRADIENT):
        grad.setColorAt(i / (len(BRAND_GRADIENT) - 1), QColor(c))
    return grad


def paint_logo(p: QPainter, rect: QRectF):
    """Degradeli kare + oynat üçgeni + indirme rozeti."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    s, ox, oy = rect.width(), rect.x(), rect.y()
    radius = s * 0.235
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(brand_gradient(ox, oy, ox + s, oy + s)))
    p.drawRoundedRect(rect, radius, radius)
    shine = QLinearGradient(ox, oy, ox, oy + s)
    shine.setColorAt(0, QColor(255, 255, 255, 70))
    shine.setColorAt(0.55, QColor(255, 255, 255, 0))
    p.setBrush(QBrush(shine))
    p.drawRoundedRect(rect, radius, radius)

    small = s < 26  # çok küçük boyutta rozet okunmaz: yalnızca ortalanmış üçgen
    pts = ((0.36, 0.26), (0.36, 0.74), (0.76, 0.50)) if small else ((0.30, 0.25), (0.30, 0.69), (0.66, 0.47))
    tri = QPainterPath(QPointF(ox + s * pts[0][0], oy + s * pts[0][1]))
    for x, y in pts[1:]:
        tri.lineTo(ox + s * x, oy + s * y)
    tri.closeSubpath()
    p.setBrush(QColor("white"))
    p.setPen(QPen(QColor("white"), max(1.0, s * 0.07), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPath(tri)
    if small:
        p.restore()
        return

    # indirme rozeti: degrade renkli halka ile üçgenden ayrılan beyaz daire
    c = QPointF(ox + s * 0.70, oy + s * 0.70)
    r = s * 0.165
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(brand_gradient(ox, oy, ox + s, oy + s)))
    p.drawEllipse(c, r + s * 0.045, r + s * 0.045)
    p.setBrush(QColor("white"))
    p.drawEllipse(c, r, r)
    pen = QPen(QColor(BRAND_GRADIENT[1]), max(1.0, s * 0.045), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawLine(QPointF(c.x(), c.y() - r * 0.52), QPointF(c.x(), c.y() + r * 0.42))
    head = QPainterPath(QPointF(c.x() - r * 0.42, c.y() + r * 0.02))
    head.lineTo(c.x(), c.y() + r * 0.46)
    head.lineTo(c.x() + r * 0.42, c.y() + r * 0.02)
    p.drawPath(head)
    p.restore()


def app_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    inset = size * 0.06  # macOS simge ızgarası gibi hafif boşluk
    paint_logo(p, QRectF(inset, inset, size - 2 * inset, size - 2 * inset))
    p.end()
    return pm


def app_icon() -> QIcon:
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(app_pixmap(size))
    return ic
