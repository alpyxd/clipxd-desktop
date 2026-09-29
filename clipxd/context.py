from PySide6.QtCore import QThreadPool

from clipxd.accounts import AccountStore
from clipxd.ffmpeg_tools import find_ffmpeg
from clipxd.paths import data_dir
from clipxd.settings import Settings


class AppContext:
    """Sekmeler arasında paylaşılan durum."""

    def __init__(self):
        self.settings = Settings()
        self.accounts = AccountStore(data_dir())
        self.download_pool = QThreadPool()
        self.download_pool.setMaxThreadCount(max(1, int(self.settings["max_concurrent"])))
        self.convert_pool = QThreadPool()
        self.convert_pool.setMaxThreadCount(1)  # ffmpeg zaten tüm çekirdekleri kullanır
        self._ffmpeg = None

    @property
    def ffmpeg(self) -> str | None:
        if self._ffmpeg is None:
            self._ffmpeg = find_ffmpeg(self.settings["ffmpeg_path"]) or ""
        return self._ffmpeg or None

    def refresh_ffmpeg(self):
        self._ffmpeg = None
