import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QComboBox, QLabel

from clipxd.ui.theme import set_font, set_role


class JobSignals(QObject):
    update = Signal(str, dict)            # iş kimliği, alanlar
    log = Signal(str, str, str)           # iş kimliği, seviye, mesaj
    done = Signal(str, bool, str, list)   # iş kimliği, başarılı mı, mesaj, dosyalar
    playlist = Signal(str, object)        # iş kimliği, PlaylistInfo (kullanıcı seçimi bekleniyor)


def reveal_file(path: str):
    path = os.path.normpath(path)
    if os.name == "nt" and os.path.exists(path):
        subprocess.Popen(["explorer", "/select,", path])
    else:
        open_folder(str(Path(path).parent))


def open_folder(path: str):
    if not path:
        return  # boş yol uygulamanın kendi klasörünü açardı
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # sürücü takılı değil vb.: yine de açmayı dene, Windows uyarı gösterir
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def hint_label(text: str, min_width: int = 0, px: float = 11.5) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    set_font(label, px)
    set_role(label, "secondary")
    if min_width:
        # kelime kaydırmalı etiketler dar genişliğe göre yükseklik hesaplayıp boşluk bırakmasın
        label.setMinimumWidth(min_width)
    return label


def fill_combo(combo: QComboBox, items, current=None):
    """items: [(veri, etiket), ...] veya {veri: etiket}."""
    combo.blockSignals(True)
    combo.clear()
    pairs = items.items() if isinstance(items, dict) else items
    for data, text in pairs:
        combo.addItem(text, data)
    if current is not None:
        idx = combo.findData(current)
        if idx >= 0:
            combo.setCurrentIndex(idx)
    combo.blockSignals(False)


def human_size(paths) -> str:
    from clipxd.ffmpeg_tools import format_bytes
    total = 0
    for p in paths:
        try:
            total += os.path.getsize(p)
        except OSError:
            pass
    return format_bytes(total)
