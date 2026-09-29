"""macOS tarzı kontroller."""
import html

from PySide6.QtCore import (Property, QEasingCurve, QEvent, QPointF, QPropertyAnimation, QRectF, QSize, Qt,
                            Signal)
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QFrame, QHBoxLayout, QLabel, QSizePolicy,
                               QStyledItemDelegate, QVBoxLayout, QWidget)

from clipxd.ui import icons
from clipxd.ui.theme import font, set_font, set_role, theme


def styled(widget: QWidget, name: str) -> QWidget:
    widget.setObjectName(name)
    widget.setAttribute(Qt.WA_StyledBackground, True)
    return widget


def label(text: str = "", px: float = 13, weight=QFont.Normal, role: str | None = None, wrap=False,
          display=False) -> QLabel:
    lbl = QLabel(text)
    # Düz metin: video başlığı gibi dış kaynaklı metinler HTML olarak yorumlanmasın
    lbl.setTextFormat(Qt.PlainText)
    set_font(lbl, px, weight, display)
    if role:
        set_role(lbl, role)
    if wrap:
        lbl.setWordWrap(True)
    return lbl


def safe_tooltip(text: str) -> str:
    """Dış kaynaklı metni ipucunda HTML yorumlanmadan, olduğu gibi gösterir."""
    return f"<p style='white-space:pre-wrap'>{html.escape(text or '')}</p>" if text else ""


class ElidedLabel(QLabel):
    """Genişliğe sığmayan metni '…' ile kısaltan etiket (her zaman düz metin çizer)."""

    def __init__(self, text="", mode=Qt.ElideRight, parent=None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.PlainText)
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(30)

    def minimumSizeHint(self):
        return QSize(30, super().minimumSizeHint().height())

    def paintEvent(self, _):
        p = QPainter(self)
        text = self.fontMetrics().elidedText(self.text(), self._mode, self.width())
        self.style().drawItemText(p, self.rect(), int(self.alignment() | Qt.AlignVCenter), self.palette(),
                                  self.isEnabled(), text, self.foregroundRole())


# ---------------------------------------------------------------- trafik ışıkları

class TrafficLights(QWidget):
    close_clicked = Signal()
    minimize_clicked = Signal()
    zoom_clicked = Signal()

    D, GAP = 12, 8
    COLORS = ("#FF5F57", "#FEBC2E", "#28C840")

    def __init__(self, parent=None, minimize=True, zoom=True):
        super().__init__(parent)
        self.enabled_buttons = (True, minimize, zoom)
        self.setFixedSize(3 * self.D + 2 * self.GAP + 4, self.D + 4)
        self.setMouseTracking(True)
        self._hover = False
        self._pressed = -1
        self._watched = None

    def showEvent(self, e):
        super().showEvent(e)
        win = self.window()
        if win is not self._watched:
            win.installEventFilter(self)
            self._watched = win

    def eventFilter(self, obj, e):
        if e.type() in (QEvent.WindowActivate, QEvent.WindowDeactivate):
            self.update()
        return False

    def _rect(self, i) -> QRectF:
        return QRectF(2 + i * (self.D + self.GAP), 2, self.D, self.D)

    def _index_at(self, pos) -> int:
        for i in range(3):
            if self._rect(i).adjusted(-3, -3, 3, 3).contains(QPointF(pos)):
                return i
        return -1

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self._pressed = -1
        self.update()

    def mousePressEvent(self, e):
        self._pressed = self._index_at(e.position())
        self.update()

    def mouseReleaseEvent(self, e):
        idx = self._index_at(e.position())
        pressed, self._pressed = self._pressed, -1
        self.update()
        if idx == pressed and idx >= 0 and self.enabled_buttons[idx]:
            (self.close_clicked, self.minimize_clicked, self.zoom_clicked)[idx].emit()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        active = self.window().isActiveWindow() or self._hover
        for i in range(3):
            r = self._rect(i)
            if active and self.enabled_buttons[i]:
                col = QColor(self.COLORS[i])
                if self._pressed == i:
                    col = col.darker(120)
            else:
                col = theme.c("tl_inactive")
            p.setPen(QPen(col.darker(112), 0.6))
            p.setBrush(col)
            p.drawEllipse(r)
            if self._hover and self.enabled_buttons[i]:
                pen = QPen(QColor(0, 0, 0, 150), 1.2, Qt.SolidLine, Qt.RoundCap)
                p.setPen(pen)
                c = r.center()
                if i == 0:
                    p.drawLine(QPointF(c.x() - 2.6, c.y() - 2.6), QPointF(c.x() + 2.6, c.y() + 2.6))
                    p.drawLine(QPointF(c.x() + 2.6, c.y() - 2.6), QPointF(c.x() - 2.6, c.y() + 2.6))
                elif i == 1:
                    p.drawLine(QPointF(c.x() - 3, c.y()), QPointF(c.x() + 3, c.y()))
                else:
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(0, 0, 0, 150))
                    t1 = QPainterPath(QPointF(c.x() - 3, c.y() - 3))
                    t1.lineTo(c.x() + 1.2, c.y() - 3)
                    t1.lineTo(c.x() - 3, c.y() + 1.2)
                    t1.closeSubpath()
                    t2 = QPainterPath(QPointF(c.x() + 3, c.y() + 3))
                    t2.lineTo(c.x() - 1.2, c.y() + 3)
                    t2.lineTo(c.x() + 3, c.y() - 1.2)
                    t2.closeSubpath()
                    p.drawPath(t1)
                    p.drawPath(t2)


# ---------------------------------------------------------------- butonlar

class IconButton(QAbstractButton):
    """Araç çubuğu / satır ikon butonu. circle=True: kenarlıklı yuvarlak (Safari indirmeleri gibi)."""

    def __init__(self, icon_name: str, tooltip: str = "", size: int = 28, icon_size: int = 18,
                 circle: bool = False, color_key: str = "text2", danger_hover: bool = False, parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.icon_px = icon_size
        self.circle = circle
        self.color_key = color_key
        self.danger_hover = danger_hover
        self.setFixedSize(size, size)
        self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setFocusPolicy(Qt.NoFocus)

    def set_icon(self, name: str, color_key: str | None = None):
        self.icon_name = name
        if color_key:
            self.color_key = color_key
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        hover = self.underMouse() and self.isEnabled()
        if self.circle:
            p.setPen(QPen(theme.c("control_border"), 1))
            p.setBrush(theme.c("control_hover") if hover else theme.c("control"))
            p.drawEllipse(r)
        elif hover or self.isDown():
            p.setPen(Qt.NoPen)
            p.setBrush(theme.c("pressed") if self.isDown() else theme.c("hover"))
            p.drawRoundedRect(r, 6, 6)
        if not self.isEnabled():
            col = theme.c("text3")
        elif self.danger_hover and hover:
            col = theme.c("danger")
        elif self.isCheckable() and self.isChecked():
            col = theme.c("accent")
        else:
            col = theme.c(self.color_key)
        s = self.icon_px
        icons.paint(p, self.icon_name, QRectF((self.width() - s) / 2, (self.height() - s) / 2, s, s), col,
                    2.0 if s <= 14 else 1.8)


class Toggle(QAbstractButton):
    """iOS / macOS anahtarı."""

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(38, 22)
        self.setCursor(Qt.PointingHandCursor)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def _get(self):
        return self._pos

    def _set(self, v):
        self._pos = v
        self.update()

    knob = Property(float, _get, _set)

    def _animate(self, checked):
        if not self.isVisible():
            self._set(1.0 if checked else 0.0)
            return
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        off, on = theme.c("toggle_off"), theme.c("accent")
        t = self._pos
        track = QColor(
            round(off.red() + (on.red() - off.red()) * t),
            round(off.green() + (on.green() - off.green()) * t),
            round(off.blue() + (on.blue() - off.blue()) * t),
        )
        if not self.isEnabled():
            p.setOpacity(0.45)
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), self.height() / 2, self.height() / 2)
        d = self.height() - 4
        x = 2 + t * (self.width() - d - 4)
        p.setBrush(QColor(0, 0, 0, 38))
        p.drawEllipse(QRectF(x, 2.6, d, d))
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(x, 2, d, d))


class Segmented(QWidget):
    """macOS segment kontrolü: [ Video | Ses ]."""

    changed = Signal(object)

    def __init__(self, items, parent=None, min_segment=64):
        super().__init__(parent)
        self.items = list(items)  # [(veri, etiket), ...]
        self._enabled = [True] * len(self.items)
        self._index = 0
        self._pos = 0.0
        self.setFixedHeight(28)
        self.setCursor(Qt.PointingHandCursor)
        fm = QFontMetrics(font(13, QFont.DemiBold))
        self._seg_w = max(min_segment, max(fm.horizontalAdvance(lbl) for _, lbl in self.items) + 26)
        self.setMinimumWidth(self._seg_w * len(self.items) + 4)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._anim = QPropertyAnimation(self, b"slide", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def sizeHint(self):
        return QSize(self._seg_w * len(self.items) + 4, 28)

    def _get(self):
        return self._pos

    def _set(self, v):
        self._pos = v
        self.update()

    slide = Property(float, _get, _set)

    def value(self):
        return self.items[self._index][0]

    def index(self) -> int:
        return self._index

    def set_value(self, data, emit=False):
        for i, (d, _) in enumerate(self.items):
            if d == data:
                self._select(i, animate=False, emit=emit)
                return

    def set_item_enabled(self, i: int, enabled: bool):
        self._enabled[i] = enabled
        self.update()

    def _select(self, i, animate=True, emit=True):
        if not self._enabled[i]:
            return
        changed = i != self._index
        self._index = i
        if animate and self.isVisible():
            self._anim.stop()
            self._anim.setStartValue(self._pos)
            self._anim.setEndValue(float(i))
            self._anim.start()
        else:
            self._set(float(i))
        if changed and emit:
            self.changed.emit(self.value())

    def mousePressEvent(self, e):
        if not self.isEnabled():
            return
        seg = (self.width() - 4) / len(self.items)
        i = int(max(0, min(len(self.items) - 1, (e.position().x() - 2) // seg)))
        self._select(i)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Left and self._index > 0:
            self._select(self._index - 1)
        elif e.key() == Qt.Key_Right and self._index < len(self.items) - 1:
            self._select(self._index + 1)
        else:
            super().keyPressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.5)
        r = QRectF(self.rect())
        p.setPen(Qt.NoPen)
        p.setBrush(theme.c("segment_bg"))
        p.drawRoundedRect(r, 7, 7)
        n = len(self.items)
        seg = (r.width() - 4) / n
        sel = QRectF(2 + self._pos * seg, 2, seg, r.height() - 4)
        if not theme.dark:
            p.setBrush(QColor(0, 0, 0, 22))
            p.drawRoundedRect(sel.translated(0, 0.7), 5.5, 5.5)
        p.setBrush(theme.c("segment_sel"))
        p.drawRoundedRect(sel, 5.5, 5.5)
        # seçili olmayan bölümler arası ince ayraçlar
        p.setPen(QPen(theme.c("text3", 0.35), 1))
        for i in range(1, n):
            if i not in (self._index, self._index + 1) and abs(self._pos - self._index) < 0.01:
                x = 2 + i * seg
                p.drawLine(QPointF(x, 7), QPointF(x, r.height() - 7))
        for i, (_, text) in enumerate(self.items):
            p.setFont(font(13, QFont.DemiBold if i == self._index else QFont.Normal))
            p.setPen(theme.c("text") if self._enabled[i] else theme.c("text3"))
            p.drawText(QRectF(2 + i * seg, 0, seg, r.height()), Qt.AlignCenter, text)


class PopupCombo(QComboBox):
    """macOS açılır menü butonu. Odakta değilken fare tekerleğiyle değişmez."""

    def __init__(self, parent=None, min_width=150):
        super().__init__(parent)
        self.setItemDelegate(QStyledItemDelegate(self))
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumWidth(min_width)
        self.setCursor(Qt.PointingHandCursor)

    def wheelEvent(self, e):
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()


# ---------------------------------------------------------------- kartlar ve satırlar

class Card(QFrame):
    """Sistem Ayarları tarzı gruplanmış satırlar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.rows: list[QWidget] = []

    def _add_sep(self) -> QWidget:
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(14, 0, 0, 0)
        line = styled(QWidget(), "sep")
        line.setFixedHeight(1)
        h.addWidget(line)
        self._layout.addWidget(wrap)
        return wrap

    def add_row(self, title: str, widget: QWidget | None = None, subtitle: str | None = None,
                icon: str | None = None) -> QWidget:
        sep = self._add_sep() if self.rows else None
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(14, 7, 12, 7)
        h.setSpacing(12)
        if icon:
            ic = QLabel()
            ic.setPixmap(icons.pixmap(icon, theme.c("accent"), 18))
            h.addWidget(ic)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        row.title_label = label(title)
        texts.addWidget(row.title_label)
        row.subtitle_label = None
        if subtitle:
            row.subtitle_label = label(subtitle, 11.5, role="secondary", wrap=True)
            texts.addWidget(row.subtitle_label)
        h.addLayout(texts, 1)
        if widget is not None:
            h.addWidget(widget, 0, Qt.AlignVCenter)
        row.setMinimumHeight(42)
        row._sep = sep
        self._layout.addWidget(row)
        self.rows.append(row)
        return row

    def add_widget(self, widget: QWidget, margins=(14, 10, 14, 10)) -> QWidget:
        sep = self._add_sep() if self.rows else None
        wrap = QWidget()
        h = QVBoxLayout(wrap)
        h.setContentsMargins(*margins)
        h.addWidget(widget)
        wrap._sep = sep
        self._layout.addWidget(wrap)
        self.rows.append(wrap)
        return wrap

    def set_row_visible(self, row: QWidget, visible: bool):
        row.setVisible(visible)
        self.refresh_separators()

    def refresh_separators(self):
        seen = False
        for row in self.rows:
            if row._sep is not None:
                row._sep.setVisible(row.isVisibleTo(self) and seen)
            if row.isVisibleTo(self):
                seen = True


def section(title: str, right: QWidget | None = None) -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(4, 0, 2, 0)
    h.addWidget(label(title, 13, QFont.DemiBold))
    h.addStretch()
    if right is not None:
        h.addWidget(right)
    return w


class Tile(QWidget):
    """Renkli yuvarlatılmış kare (platform / dosya türü simgesi)."""

    def __init__(self, size=36, color="#8E8E93", text="", icon_name=None, gradient=None, tint=False, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.color, self.text, self.icon_name, self.gradient, self.tint = color, text, icon_name, gradient, tint

    def set(self, color=None, icon_name=None, text=None):
        if color:
            self.color = color
        if icon_name is not None:
            self.icon_name = icon_name
        if text is not None:
            self.text = text
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        radius = r.width() * 0.26
        p.setPen(Qt.NoPen)
        color = theme.c(self.color) if self.color in theme.t else QColor(self.color)
        if self.tint:
            bg = QColor(color)
            bg.setAlphaF(0.16 if theme.dark else 0.12)
            p.setBrush(bg)
            fg = color
        else:
            grad = QLinearGradient(r.topLeft(), r.bottomLeft())
            stops = self.gradient or (color.lighter(118).name(), color.name())
            for i, s in enumerate(stops):
                grad.setColorAt(i / max(1, len(stops) - 1), QColor(s))
            p.setBrush(grad)
            fg = QColor("#FFFFFF")
            if theme.dark and color.lightness() < 50:
                # siyah kutular (X, TikTok) koyu arka planda kaybolmasın
                p.setPen(QPen(QColor(255, 255, 255, 45), 1))
                r = r.adjusted(0.5, 0.5, -0.5, -0.5)
        p.drawRoundedRect(r, radius, radius)
        p.setPen(Qt.NoPen)
        if self.icon_name:
            s = r.width() * 0.56
            icons.paint(p, self.icon_name, QRectF((r.width() - s) / 2, (r.height() - s) / 2, s, s), fg, 1.9)
        elif self.text:
            p.setPen(fg)
            p.setFont(font(r.width() * 0.42, QFont.Bold, display=True))
            p.drawText(r, Qt.AlignCenter, self.text)


class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 26, 20, 26)
        v.setSpacing(6)
        v.addStretch()
        self._icon_name = icon_name
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignCenter)
        v.addWidget(self.icon)
        t = label(title, 15, QFont.DemiBold, role="secondary")
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        if subtitle:
            s = label(subtitle, 12, role="tertiary", wrap=True)
            s.setAlignment(Qt.AlignCenter)
            v.addWidget(s)
        v.addStretch()
        self._paint_icon()
        theme.changed.connect(self._paint_icon)

    def _paint_icon(self):
        self.icon.setPixmap(icons.pixmap(self._icon_name, theme.c("text3"), 44, 1.5))


class FolderButton(QAbstractButton):
    """📁 Klasör adı ⌄ — tıklayınca menü: klasör seç / aç (isteğe bağlı: kaynakla aynı klasör)."""

    changed = Signal(str)

    def __init__(self, path: str = "", allow_same: bool = False, parent=None):
        super().__init__(parent)
        self.path = path
        self.allow_same = allow_same
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setFixedHeight(28)
        self.setMinimumWidth(170)
        self.setMaximumWidth(280)
        self.clicked.connect(self._menu)

    def display_text(self) -> str:
        if not self.path:
            return "Kaynakla aynı klasör" if self.allow_same else "Klasör seçin"
        from pathlib import Path
        return Path(self.path).name or self.path

    def set_path(self, path: str, emit=False):
        self.path = path
        self.setToolTip(path or self.display_text())
        self.update()
        if emit:
            self.changed.emit(path)

    def sizeHint(self):
        fm = QFontMetrics(font(13))
        return QSize(min(280, max(170, fm.horizontalAdvance(self.display_text()) + 64)), 28)

    def _menu(self):
        from PySide6.QtWidgets import QFileDialog, QMenu
        from clipxd.ui.common import open_folder
        m = QMenu(self)
        if self.path:
            info = m.addAction(self.path)
            info.setEnabled(False)
            m.addSeparator()
        if self.allow_same:
            same = m.addAction("Kaynakla aynı klasör")
            same.triggered.connect(lambda: self.set_path("", emit=True))
        choose = m.addAction("Klasör seç…")
        choose.triggered.connect(self._choose)
        if self.path:
            m.addAction("Klasörü aç", lambda: open_folder(self.path))
        m.exec(self.mapToGlobal(self.rect().bottomLeft()))

    def _choose(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self.window(), "Klasör seç", self.path)
        if d:
            self.set_path(d, emit=True)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(theme.c("control_border"), 1))
        p.setBrush(theme.c("control_hover") if self.underMouse() else theme.c("control"))
        p.drawRoundedRect(r, 6, 6)
        icons.paint(p, "folder", QRectF(9, 6, 16, 16), theme.c("accent"), 1.9)
        p.setPen(theme.c("text"))
        p.setFont(font(13))
        text_rect = QRectF(31, 0, self.width() - 31 - 24, self.height())
        p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(font(13)).elidedText(self.display_text(), Qt.ElideMiddle, int(text_rect.width())))
        icons.paint(p, "chevrons_updown", QRectF(self.width() - 20, 8, 12, 12), theme.c("text2"), 2.2)


# ---------------------------------------------------------------- kenar çubuğu

class BrandMark(QWidget):
    """Logo + 'ClipXD' yazısı ('XD' marka degradesiyle)."""

    def __init__(self, logo_px: int = 28, text_px: float = 19, parent=None):
        super().__init__(parent)
        self.logo_px, self.text_px = logo_px, text_px
        self.setFixedHeight(logo_px + 8)
        self.setToolTip("ClipXD Desktop")

    def sizeHint(self):
        fm = QFontMetrics(font(self.text_px, QFont.Bold, display=True))
        return QSize(self.logo_px + 18 + fm.horizontalAdvance("ClipXD"), self.logo_px + 8)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        icons.paint_logo(p, QRectF(8, (h - self.logo_px) / 2, self.logo_px, self.logo_px))
        f = font(self.text_px, QFont.Bold, display=True)
        fm = QFontMetrics(f)
        p.setFont(f)
        x = 8 + self.logo_px + 10
        p.setPen(theme.c("text"))
        p.drawText(QRectF(x, 0, fm.horizontalAdvance("Clip") + 2, h), Qt.AlignVCenter | Qt.AlignLeft, "Clip")
        x2 = x + fm.horizontalAdvance("Clip")
        w2 = fm.horizontalAdvance("XD")
        p.setPen(QPen(QBrush(icons.brand_gradient(x2, 0, x2 + w2, 0)), 1))
        p.drawText(QRectF(x2, 0, w2 + 4, h), Qt.AlignVCenter | Qt.AlignLeft, "XD")


class SidebarItem(QAbstractButton):
    def __init__(self, icon_name: str, text: str, parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.setText(text)
        self.setCheckable(True)
        self.setFixedHeight(32)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setFocusPolicy(Qt.NoFocus)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0, 1, 0, -1)
        if self.isChecked():
            p.setPen(Qt.NoPen)
            p.setBrush(theme.c("sidebar_sel"))
            p.drawRoundedRect(r, 7, 7)
        elif self.underMouse():
            p.setPen(Qt.NoPen)
            p.setBrush(theme.c("hover"))
            p.drawRoundedRect(r, 7, 7)
        icons.paint(p, self.icon_name, QRectF(10, (self.height() - 18) / 2, 18, 18), theme.c("accent"), 1.8)
        p.setPen(theme.c("text"))
        p.setFont(font(13, QFont.Medium if self.isChecked() else QFont.Normal))
        p.drawText(QRectF(38, 0, self.width() - 44, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())


class Sidebar(QWidget):
    current_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        styled(self, "sidebar")
        self.setFixedWidth(216)
        self._v = QVBoxLayout(self)
        self._v.setContentsMargins(10, 52, 10, 12)
        self._v.setSpacing(1)
        self.items: list[SidebarItem] = []
        self._bottom = None

    def add_brand(self):
        self._v.addWidget(BrandMark())
        self._v.addSpacing(10)

    def add_header(self, text: str):
        lbl = label(text, 11, QFont.DemiBold, role="tertiary")
        lbl.setContentsMargins(10, 12 if self.items else 4, 0, 4)
        self._v.addWidget(lbl)

    def add_item(self, icon_name: str, text: str) -> int:
        item = SidebarItem(icon_name, text)
        idx = len(self.items)
        item.clicked.connect(lambda _=False, i=idx: self.set_current(i))
        self.items.append(item)
        self._v.addWidget(item)
        return idx

    def add_stretch(self):
        self._v.addStretch(1)

    def add_bottom(self, widget: QWidget):
        self._v.addWidget(widget)

    def set_current(self, idx: int):
        for i, it in enumerate(self.items):
            it.setChecked(i == idx)
        self.current_changed.emit(idx)
