"""Oynatma listesinden indirilecek öğeleri seçme sayfası."""
from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QStyle, QStyledItemDelegate, QVBoxLayout)

from clipxd.downloader import PlaylistInfo
from clipxd.ffmpeg_tools import format_seconds
from clipxd.ui import icons
from clipxd.ui.sheets import Sheet
from clipxd.ui.theme import font, set_role, theme
from clipxd.ui.widgets import ElidedLabel, Tile, label, safe_tooltip

INDEX_ROLE = Qt.UserRole
DURATION_ROLE = Qt.UserRole + 1


def draw_checkbox(p: QPainter, rect: QRectF, checked: bool):
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    if checked:
        p.setPen(Qt.NoPen)
        p.setBrush(theme.c("accent"))
        p.drawRoundedRect(rect, 5, 5)
        path = QPainterPath(QPointF(rect.left() + rect.width() * 0.26, rect.top() + rect.height() * 0.52))
        path.lineTo(rect.left() + rect.width() * 0.44, rect.top() + rect.height() * 0.70)
        path.lineTo(rect.left() + rect.width() * 0.76, rect.top() + rect.height() * 0.32)
        p.setPen(QPen(Qt.white, 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
    else:
        p.setPen(QPen(theme.c("control_border"), 1.2))
        p.setBrush(theme.c("field"))
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)
    p.restore()


class EntryDelegate(QStyledItemDelegate):
    ROW_H = 38

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.ROW_H)

    def paint(self, p: QPainter, option, index):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(option.rect)
        if option.state & QStyle.State_MouseOver:
            p.setPen(Qt.NoPen)
            p.setBrush(theme.c("hover"))
            p.drawRoundedRect(r.adjusted(2, 1, -2, -1), 7, 7)
        checked = index.data(Qt.CheckStateRole) == Qt.Checked
        draw_checkbox(p, QRectF(r.left() + 12, r.center().y() - 9, 18, 18), checked)
        f_small = font(11.5)
        p.setFont(f_small)
        p.setPen(theme.c("text3"))
        p.drawText(QRectF(r.left() + 36, r.top(), 32, r.height()), Qt.AlignVCenter | Qt.AlignRight,
                   str(index.data(INDEX_ROLE)))
        duration = index.data(DURATION_ROLE) or ""
        p.setPen(theme.c("text2"))
        p.drawText(QRectF(r.right() - 76, r.top(), 64, r.height()), Qt.AlignVCenter | Qt.AlignRight, duration)
        f = font(13)
        p.setFont(f)
        p.setPen(theme.c("text") if checked else theme.c("text2"))
        title_rect = QRectF(r.left() + 80, r.top(), r.width() - 80 - 88, r.height())
        text = QFontMetrics(f).elidedText(index.data(Qt.DisplayRole), Qt.ElideRight, int(title_rect.width()))
        p.drawText(title_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
        p.restore()


class EntryList(QListWidget):
    """Satırın tamamına tıklayınca işaretlenen, macOS görünümlü liste."""

    def __init__(self, on_change):
        super().__init__()
        self.setObjectName("entries")
        self.on_change = on_change
        self.setItemDelegate(EntryDelegate(self))
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.viewport().setAttribute(Qt.WA_Hover, True)
        self.itemClicked.connect(self._toggle)

    def _toggle(self, item: QListWidgetItem):
        item.setData(Qt.CheckStateRole, Qt.Unchecked if item.data(Qt.CheckStateRole) == Qt.Checked else Qt.Checked)
        self.on_change()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space and self.currentItem() is not None:
            self._toggle(self.currentItem())
        else:
            super().keyPressEvent(e)

    def viewportEvent(self, e):
        if e.type() in (QEvent.HoverMove, QEvent.HoverLeave):
            self.viewport().update()
        return super().viewportEvent(e)


class PlaylistSheet(Sheet):
    """exec() -> seçilen sıra numaralarının listesi veya None."""

    def __init__(self, host, playlist: PlaylistInfo, folder: str, kind: str = "video"):
        super().__init__(host, width=640)
        self.playlist = playlist
        self.cancel_value = None
        b = self.body
        b.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(Tile(44, "accent", icon_name="list"), 0, Qt.AlignTop)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        t = ElidedLabel(playlist.title)
        t.setFont(font(16, QFont.Bold, display=True))
        t.setToolTip(safe_tooltip(playlist.title))
        titles.addWidget(t)
        parts = [p for p in (playlist.uploader, f"{len(playlist.entries)} öğe",
                             f"toplam {format_seconds(playlist.total_duration)}" if playlist.total_duration else "")
                 if p]
        titles.addWidget(label(" · ".join(parts), 12, role="secondary"))
        head.addLayout(titles, 1)
        b.addLayout(head)

        tools = QHBoxLayout()
        tools.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Listede ara")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icons.icon("magnifier", theme.c("text3"), 14), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self._filter)
        tools.addWidget(self.search, 1)
        tools.addSpacing(8)
        for text, value in (("Tümünü Seç", True), ("Hiçbirini Seçme", False)):
            btn = QPushButton(text)
            btn.setObjectName("link")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, v=value: self._set_all(v))
            tools.addWidget(btn)
        b.addLayout(tools)

        self.list = EntryList(self._changed)
        for e in playlist.entries:
            item = QListWidgetItem(e.title)
            item.setData(INDEX_ROLE, e.index)
            item.setData(DURATION_ROLE, format_seconds(e.duration) if e.duration else "")
            item.setData(Qt.CheckStateRole, Qt.Checked)
            item.setToolTip(safe_tooltip(e.title))
            self.list.addItem(item)
        rows = len(playlist.entries)
        self.list.setFixedHeight(min(380, max(1, rows) * EntryDelegate.ROW_H + 6))
        frame = QFrame()
        frame.setObjectName("card")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(4, 3, 4, 3)
        fl.addWidget(self.list)
        b.addWidget(frame)

        info = QHBoxLayout()
        folder_label = ElidedLabel(f"Kaydedilecek klasör: {folder}", Qt.ElideMiddle)
        folder_label.setFont(font(11.5))
        folder_label.setToolTip(safe_tooltip(folder))
        set_role(folder_label, "secondary")
        info.addWidget(folder_label, 1)
        self.count_label = label("", 11.5, QFont.Medium, role="secondary")
        info.addWidget(self.count_label)
        b.addLayout(info)

        buttons = self.add_buttons([("Vazgeç", None, None), ("İndir", "go", "primary")])
        self.download_btn = buttons[1]
        self.download_btn.clicked.disconnect()
        self.download_btn.clicked.connect(self._accept)
        self._changed()

    def _items(self, visible_only=False):
        for i in range(self.list.count()):
            item = self.list.item(i)
            if visible_only and item.isHidden():
                continue
            yield item

    def selected(self) -> list[int]:
        return [it.data(INDEX_ROLE) for it in self._items() if it.data(Qt.CheckStateRole) == Qt.Checked]

    def _set_all(self, value: bool):
        for it in self._items(visible_only=True):
            it.setData(Qt.CheckStateRole, Qt.Checked if value else Qt.Unchecked)
        self._changed()

    def _filter(self, text: str):
        q = text.casefold().strip()
        for it in self._items():
            it.setHidden(bool(q) and q not in it.text().casefold())

    def _changed(self):
        n = len(self.selected())
        total = self.list.count()
        self.count_label.setText(f"{n} / {total} seçili")
        self.download_btn.setEnabled(n > 0)
        self.download_btn.setText("İndir" if n == 0 else f"{n} Öğeyi İndir")

    def _accept(self):
        sel = self.selected()
        if sel:
            self.done(sel)

    def keyPressEvent(self, e):
        # Aramada Enter'a basmak yanlışlıkla indirmeyi başlatmasın
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and self.search.hasFocus():
            e.accept()
            return
        super().keyPressEvent(e)
