"""Desteklenen tüm siteler (aranabilir liste)."""
from PySide6.QtCore import QEvent, QRectF, QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
                               QStyle, QStyledItemDelegate, QVBoxLayout)
from yt_dlp.version import __version__ as YTDLP_VERSION

from clipxd.sites import supported_sites
from clipxd.ui import icons
from clipxd.ui.platforms import DOWNLOAD_PLATFORMS, platform_tile
from clipxd.ui.sheets import Sheet
from clipxd.ui.theme import font, theme
from clipxd.ui.widgets import Tile, label

DESC_ROLE = Qt.UserRole


class SiteDelegate(QStyledItemDelegate):
    ROW_H = 34

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
        name = index.data(Qt.DisplayRole)
        f = font(13)
        fm = QFontMetrics(f)
        p.setFont(f)
        p.setPen(theme.c("text"))
        name_w = min(fm.horizontalAdvance(name), int(r.width() * 0.55))
        p.drawText(QRectF(r.left() + 12, r.top(), name_w, r.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   fm.elidedText(name, Qt.ElideRight, name_w))
        desc = index.data(DESC_ROLE) or ""
        if desc:
            fs = font(11.5)
            p.setFont(fs)
            p.setPen(theme.c("text3"))
            x = r.left() + 12 + name_w + 12
            w = r.right() - 12 - x
            p.drawText(QRectF(x, r.top(), w, r.height()), Qt.AlignVCenter | Qt.AlignRight,
                       QFontMetrics(fs).elidedText(desc, Qt.ElideRight, int(w)))
        p.restore()


class SiteList(QListWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("entries")
        self.setItemDelegate(SiteDelegate(self))
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.viewport().setAttribute(Qt.WA_Hover, True)

    def viewportEvent(self, e):
        if e.type() in (QEvent.HoverMove, QEvent.HoverLeave):
            self.viewport().update()
        return super().viewportEvent(e)


class SitesSheet(Sheet):
    def __init__(self, host):
        super().__init__(host, width=620)
        sites = supported_sites()
        b = self.body
        b.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(Tile(44, "accent", icon_name="globe"), 0, Qt.AlignTop)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("Desteklenen Siteler", 16, QFont.Bold, display=True))
        titles.addWidget(label(f"{len(sites)} site · yt-dlp {YTDLP_VERSION} ile", 12, role="secondary"))
        head.addLayout(titles, 1)
        b.addLayout(head)

        # popüler platformlar ve neler indirilebildiği
        popular = QFrame()
        popular.setObjectName("card")
        pv = QVBoxLayout(popular)
        pv.setContentsMargins(14, 10, 14, 10)
        pv.setSpacing(8)
        for key, name, what in DOWNLOAD_PLATFORMS[:6]:
            row = QHBoxLayout()
            row.setSpacing(10)
            row.addWidget(platform_tile(key, 22))
            row.addWidget(label(name, 13, QFont.Medium))
            row.addStretch()
            row.addWidget(label(what, 11.5, role="secondary"))
            pv.addLayout(row)
        b.addWidget(popular)

        self.search = QLineEdit()
        self.search.setPlaceholderText(f"{len(sites)} site içinde ara")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icons.icon("magnifier", theme.c("text3"), 14), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self._filter)
        b.addWidget(self.search)

        self.list = SiteList()
        for name, desc in sites:
            item = QListWidgetItem(name)
            item.setData(DESC_ROLE, desc)
            if desc:
                item.setToolTip(desc)
            self.list.addItem(item)
        self.list.setFixedHeight(240)
        frame = QFrame()
        frame.setObjectName("card")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(4, 3, 4, 3)
        fl.addWidget(self.list)
        self.empty = label("Sonuç yok. Link yine de çalışabilir; yapıştırıp deneyin.", 12, role="tertiary")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.hide()
        fl.addWidget(self.empty)
        b.addWidget(frame)

        b.addWidget(label("Listede olmayan birçok sitedeki videolar da genel algılamayla indirilebilir. "
                          "Bir site çalışmayı bırakırsa Ayarlar'dan yt-dlp'yi güncelleyin.", 11.5, role="secondary",
                          wrap=True))
        self.add_buttons([("Kapat", None, "primary")])
        self.search.setFocus()

    def _filter(self, text: str):
        q = text.casefold().strip()
        shown = 0
        for i in range(self.list.count()):
            it = self.list.item(i)
            hide = bool(q) and q not in it.text().casefold() and q not in (it.data(DESC_ROLE) or "").casefold()
            it.setHidden(hide)
            shown += not hide
        self.empty.setVisible(shown == 0)
        self.list.setVisible(shown > 0)
