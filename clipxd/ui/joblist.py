"""Safari İndirilenler listesi tarzı iş satırları."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QMenu, QProgressBar, QScrollArea, QVBoxLayout, QWidget

from clipxd.ui.theme import set_font, set_role
from clipxd.ui.widgets import Card, ElidedLabel, EmptyState, IconButton, Tile, safe_tooltip


class JobRow(QWidget):
    action = Signal(str, str)  # iş kimliği, eylem: cancel | reveal | retry | remove | folder | copy

    def __init__(self, job_id: str, title: str, subtitle: str, kind: str = "video", parent=None):
        super().__init__(parent)
        self.job_id = job_id
        self.state = "queued"
        self.menu_extra = []  # [(metin, eylem)]
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 10, 12, 10)
        h.setSpacing(12)
        icon = {"audio": "music", "video": "film", "gif": "photo"}.get(kind, "doc")
        self.tile = Tile(36, "accent", icon_name=icon, tint=True)
        h.addWidget(self.tile, 0, Qt.AlignVCenter)

        texts = QVBoxLayout()
        texts.setSpacing(4)
        self.title = ElidedLabel(title)
        set_font(self.title, 13, QFont.DemiBold)
        texts.addWidget(self.title)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 100)
        self.bar.hide()
        texts.addWidget(self.bar)
        self.subtitle = ElidedLabel(subtitle)
        set_font(self.subtitle, 11.5)
        set_role(self.subtitle, "secondary")
        texts.addWidget(self.subtitle)
        h.addLayout(texts, 1)

        self.btn_retry = IconButton("retry", "Yeniden dene", 26, 13, circle=True)
        self.btn_main = IconButton("xmark", "İptal et", 26, 13, circle=True)
        self.btn_retry.clicked.connect(lambda: self.action.emit(self.job_id, "retry"))
        self.btn_main.clicked.connect(self._main_clicked)
        h.addWidget(self.btn_retry, 0, Qt.AlignVCenter)
        h.addWidget(self.btn_main, 0, Qt.AlignVCenter)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.set_state("queued", subtitle)

    def _main_clicked(self):
        if self.state in ("queued", "running"):
            self.action.emit(self.job_id, "cancel")
        elif self.state == "done":
            self.action.emit(self.job_id, "reveal")
        else:
            self.action.emit(self.job_id, "remove")

    def set_title(self, text: str):
        self.title.setText(text)
        self.title.setToolTip(safe_tooltip(text))
        self.title.update()

    def set_state(self, state: str, subtitle: str | None = None, percent=None):
        self.state = state
        running = state in ("queued", "running")
        self.bar.setVisible(running)
        if running:
            if percent is None and state == "running":
                self.bar.setRange(0, 0)
            else:
                self.bar.setRange(0, 100)
                self.bar.setValue(int(percent or 0))
        if subtitle is not None:
            self.subtitle.setText(subtitle)
            self.subtitle.setToolTip(safe_tooltip(subtitle))
        set_role(self.subtitle, "danger" if state == "error" else "secondary")
        self.subtitle.update()
        if running:
            self.btn_main.set_icon("xmark")
            self.btn_main.setToolTip("İptal et")
        elif state == "done":
            self.btn_main.set_icon("magnifier")
            self.btn_main.setToolTip("Dosyayı göster")
        else:
            self.btn_main.set_icon("xmark")
            self.btn_main.setToolTip("Listeden kaldır")
        self.btn_retry.setVisible(state in ("error", "cancelled"))
        if state == "done":
            self.tile.set(color="success")
        elif state == "error":
            self.tile.set(color="danger")
        else:
            self.tile.set(color="accent")

    def set_progress(self, percent):
        if percent is None:
            self.bar.setRange(0, 0)
        else:
            self.bar.setRange(0, 100)
            self.bar.setValue(int(percent))

    def mouseDoubleClickEvent(self, e):
        if self.state == "done":
            self.action.emit(self.job_id, "reveal")

    def _menu(self, pos):
        m = QMenu(self)
        if self.state == "done":
            m.addAction("Dosyayı göster", lambda: self.action.emit(self.job_id, "reveal"))
        m.addAction("Klasörü aç", lambda: self.action.emit(self.job_id, "folder"))
        for text, act in self.menu_extra:
            m.addAction(text, lambda a=act: self.action.emit(self.job_id, a))
        m.addSeparator()
        if self.state in ("queued", "running"):
            m.addAction("İptal et", lambda: self.action.emit(self.job_id, "cancel"))
        if self.state in ("error", "cancelled"):
            m.addAction("Yeniden dene", lambda: self.action.emit(self.job_id, "retry"))
        if self.state not in ("queued", "running"):
            m.addAction("Listeden kaldır", lambda: self.action.emit(self.job_id, "remove"))
        m.exec(self.mapToGlobal(pos))


class JobList(QScrollArea):
    """Kart içinde iş satırları; boşken açıklama gösterir."""

    def __init__(self, empty_icon: str, empty_title: str, empty_subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("scrollBody")
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 4, 0)
        v.setSpacing(0)
        self.card = Card()
        self.empty = EmptyState(empty_icon, empty_title, empty_subtitle)
        v.addWidget(self.empty)
        v.addWidget(self.card)
        v.addStretch()
        self.setWidget(body)
        self.rows: dict[str, JobRow] = {}
        self._wraps: dict[str, QWidget] = {}
        self._refresh()

    def add(self, row: JobRow):
        wrap = self.card.add_widget(row, margins=(0, 0, 0, 0))
        self.rows[row.job_id] = row
        self._wraps[row.job_id] = wrap
        self._refresh()
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def remove(self, job_id: str):
        row = self.rows.pop(job_id, None)
        wrap = self._wraps.pop(job_id, None)
        if wrap is None:
            return
        self.card.rows.remove(wrap)
        for w in (wrap._sep, wrap):
            if w is not None:
                w.hide()
                w.deleteLater()
        # ilk satır silindiyse yeni ilk satırın ayracı gizlenmeli
        if self.card.rows and self.card.rows[0]._sep is not None:
            self.card.rows[0]._sep.hide()
            self.card.rows[0]._sep.deleteLater()
            self.card.rows[0]._sep = None
        self._refresh()

    def row(self, job_id: str) -> JobRow | None:
        return self.rows.get(job_id)

    def _refresh(self):
        has = bool(self.rows)
        self.card.setVisible(has)
        self.empty.setVisible(not has)
