"""Pencere içinde açılan macOS tarzı sayfalar (sheet) ve uyarılar."""
from PySide6.QtCore import QEasingCurve, QEvent, QEventLoop, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)

from clipxd.ui import icons
from clipxd.ui.theme import theme
from clipxd.ui.widgets import label


class Sheet(QWidget):
    """Üst pencereyi karartıp ortada bir kart gösterir. exec() kapanana kadar bekler."""

    def __init__(self, host: QWidget, width: int = 520):
        top = host.window() if host is not None else None
        super().__init__(top)
        self.top = top
        self.result = None
        self._loop = None
        self._t = 0.0
        self._closing = False
        self.default_button = None
        self.cancel_value = None
        self.setFocusPolicy(Qt.StrongFocus)

        self.card = QFrame(self)
        self.card.setObjectName("sheet")
        self.card.setFixedWidth(width)
        self.body = QVBoxLayout(self.card)
        self.body.setContentsMargins(24, 22, 24, 20)
        self.body.setSpacing(12)
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(50)
        shadow.setOffset(0, 16)
        shadow.setColor(QColor(0, 0, 0, 110 if theme.dark else 70))
        self.card.setGraphicsEffect(shadow)

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._step)
        self._anim.finished.connect(self._anim_done)
        if top is not None:
            top.installEventFilter(self)
            self.setGeometry(top.rect())

    def eventFilter(self, obj, e):
        if obj is self.top:
            if e.type() == QEvent.Resize:
                self.setGeometry(self.top.rect())
                self._place()
            elif e.type() == QEvent.Hide and not e.spontaneous() and not self._closing:
                # Pencere kapatıldı (küçültme değil): bekleyen exec() takılı kalmasın
                self.result = self.cancel_value
                self._closing = True
                self._anim.stop()
                self.hide()
                if self._loop is not None:
                    self._loop.quit()
                self.deleteLater()
        return False

    def _place(self):
        self.card.adjustSize()
        cw, ch = self.card.width(), self.card.height()
        y = max(56, int((self.height() - ch) * 0.38)) - int(18 * (1 - self._t))
        self.card.move(int((self.width() - cw) / 2), y)

    def _step(self, v):
        self._t = float(v)
        self._place()
        self.update()

    def _anim_done(self):
        if self._closing:
            self.hide()
            if self._loop is not None:
                self._loop.quit()
            self.deleteLater()

    def paintEvent(self, _):
        p = QPainter(self)
        dim = theme.c("dim")
        dim.setAlphaF(dim.alphaF() * self._t)
        p.fillRect(self.rect(), dim)

    def mousePressEvent(self, e):
        e.accept()  # alttaki pencereye tıklama geçmesin

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.done(self.cancel_value)
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter) and self.default_button is not None:
            self.default_button.click()
        else:
            super().keyPressEvent(e)

    def exec(self):
        self.show()
        self.raise_()
        self._place()
        self.setFocus()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._loop = QEventLoop()
        self._loop.exec()
        return self.result

    def done(self, result=None):
        if self._closing:
            return
        self.result = result
        self._closing = True
        self._anim.stop()
        self._anim.setDuration(140)
        self._anim.setStartValue(self._t)
        self._anim.setEndValue(0.0)
        self._anim.start()

    # --- içerik yardımcıları
    def add_buttons(self, specs, stretch_first=True) -> list[QPushButton]:
        """specs: [(metin, değer, tür)] tür: 'primary' | 'destructive' | None"""
        row = QHBoxLayout()
        row.setSpacing(8)
        if stretch_first:
            row.addStretch()
        buttons = []
        for text, value, kind in specs:
            b = QPushButton(text)
            b.setMinimumWidth(92)
            b.setCursor(Qt.PointingHandCursor)
            if kind in ("primary", "destructive"):
                b.setObjectName(kind)
            if kind == "primary":
                self.default_button = b
            b.clicked.connect(lambda _=False, v=value: self.done(v))
            row.addWidget(b)
            buttons.append(b)
        self.body.addSpacing(4)
        self.body.addLayout(row)
        return buttons


def alert(parent, title: str, text: str = "", buttons=("Tamam",), default: int | None = 0,
          cancel: int | None = None, kind: str = "info", destructive: int | None = None) -> int:
    """macOS uyarısı. Seçilen butonun sırasını döndürür (Esc -> cancel veya -1)."""
    sheet = Sheet(parent, width=340)
    sheet.cancel_value = cancel if cancel is not None else -1
    body = sheet.body
    body.setContentsMargins(22, 22, 22, 18)
    body.setSpacing(8)
    ic = QLabel()
    ic.setAlignment(Qt.AlignCenter)
    if kind == "warning":
        ic.setPixmap(icons.pixmap("warning", theme.c("warning"), 52, 1.6))
    elif kind == "error":
        ic.setPixmap(icons.pixmap("error_circle", theme.c("danger"), 52))
    else:
        pm = icons.app_pixmap(128)
        pm.setDevicePixelRatio(2.0)
        ic.setPixmap(pm)
    body.addWidget(ic)
    t = label(title, 14, QFont.Bold, wrap=True)
    t.setAlignment(Qt.AlignCenter)
    body.addWidget(t)
    if text:
        m = label(text, 12, role="secondary", wrap=True)
        m.setAlignment(Qt.AlignCenter)
        m.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.addWidget(m)
    body.addSpacing(6)
    box = QHBoxLayout() if len(buttons) <= 2 else QVBoxLayout()
    box.setSpacing(8)
    # macOS: iki butonda varsayılan sağda
    for i, text_ in enumerate(buttons):
        b = QPushButton(text_)
        b.setCursor(Qt.PointingHandCursor)
        b.setMinimumHeight(28)
        if i == default:
            b.setObjectName("primary")
            sheet.default_button = b
        elif i == destructive:
            b.setObjectName("destructive")
        b.clicked.connect(lambda _=False, v=i: sheet.done(v))
        box.addWidget(b, 1)
    body.addLayout(box)
    result = sheet.exec()
    return -1 if result is None else result


def confirm(parent, title: str, text: str = "", ok: str = "Tamam", cancel: str = "Vazgeç",
            destructive: bool = False, kind: str = "info") -> bool:
    idx = alert(parent, title, text, buttons=(cancel, ok), default=None if destructive else 1, cancel=0,
                destructive=1 if destructive else None, kind=kind)
    return idx == 1
