"""Platform görünümleri (marka logosu yerine renkli kutu + baş harf) ve indirme platformları şeridi."""
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from clipxd.ui.widgets import Tile

PLATFORM_LOOK = {
    "youtube": ("#FF0033", "▶", None),
    "instagram": ("#DD2A7B", "I", ("#FEDA75", "#FA7E1E", "#D62976", "#962FBF", "#4F5BD5")),
    "tiktok": ("#111111", "T", ("#25F4EE", "#111111", "#FE2C55")),
    "x": ("#111111", "X", None),
    "facebook": ("#1877F2", "f", None),
    "reddit": ("#FF4500", "R", None),
    "vimeo": ("#1AB7EA", "V", None),
    "twitch": ("#9146FF", "T", None),
    "linkedin": ("#0A66C2", "in", None),
    "pinterest": ("#E60023", "P", None),
    "soundcloud": ("#FF5500", "S", None),
    "dailymotion": ("#0066DC", "D", None),
    "bilibili": ("#00A1D6", "B", None),
    "custom": ("#8E8E93", "", None),
}

# İndir sayfasının üstünde gösterilen platformlar: (anahtar, ad, indirilebilenler)
DOWNLOAD_PLATFORMS = [
    ("youtube", "YouTube", "Videolar, Shorts, oynatma listeleri ve kanallar"),
    ("instagram", "Instagram", "Gönderiler, Reels ve hikâyeler (hikâyeler için hesap gerekir)"),
    ("tiktok", "TikTok", "Videolar ve profildeki videolar"),
    ("x", "X (Twitter)", "Gönderilerdeki videolar ve GIF'ler"),
    ("facebook", "Facebook", "Videolar ve Reels"),
    ("reddit", "Reddit", "Video gönderileri"),
    ("vimeo", "Vimeo", "Videolar ve şifre korumalı olmayan gizli bağlantılar"),
    ("twitch", "Twitch", "Yayın kayıtları (VOD) ve klipler"),
    ("soundcloud", "SoundCloud", "Parçalar ve setler (ses)"),
    ("dailymotion", "Dailymotion", "Videolar ve oynatma listeleri"),
    ("pinterest", "Pinterest", "Video pinler"),
    ("linkedin", "LinkedIn", "Gönderilerdeki videolar"),
    ("bilibili", "Bilibili", "Videolar"),
]


def platform_tile(key: str, size: int = 36) -> Tile:
    color, text, grad = PLATFORM_LOOK.get(key, PLATFORM_LOOK["custom"])
    if key == "custom":
        return Tile(size, color, icon_name="globe")
    return Tile(size, color, text=text, gradient=grad)


class _CountSignal(QObject):
    ready = Signal(int)


class PlatformStrip(QWidget):
    """Desteklenen platform simgeleri + 'tüm siteler' bağlantısı."""

    def __init__(self, on_show_all, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        for key, name, what in DOWNLOAD_PLATFORMS:
            tile = platform_tile(key, 28)
            tile.setToolTip(f"<b>{name}</b><br>{what}")
            h.addWidget(tile)
        h.addSpacing(8)
        self.more = QPushButton("Tüm siteler")
        self.more.setObjectName("link")
        self.more.setCursor(Qt.PointingHandCursor)
        self.more.setToolTip("Desteklenen tüm siteleri göster")
        self.more.clicked.connect(on_show_all)
        h.addWidget(self.more)
        # Site sayısı yt-dlp sürümüne göre değişir; açılışı yavaşlatmamak için arka planda say
        self._sig = _CountSignal()
        self._sig.ready.connect(self._set_count)
        threading.Thread(target=self._count, daemon=True).start()

    def _count(self):
        try:
            from clipxd.sites import supported_sites
            self._sig.ready.emit(len(supported_sites()))
        except Exception:
            pass

    def _set_count(self, n: int):
        others = max(0, n - len(DOWNLOAD_PLATFORMS))
        self.more.setText(f"+{others // 50 * 50} site daha" if others >= 100 else "Tüm siteler")
