import os
import re
import sys

from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout,
                               QWidget)
from yt_dlp.version import __version__ as YTDLP_VERSION

from clipxd import __version__
from clipxd.ffmpeg_tools import ffmpeg_version
from clipxd.paths import data_dir
from clipxd.settings import DEFAULT_TEMPLATE
from clipxd.ui.common import fill_combo, open_folder
from clipxd.ui.sheets import alert
from clipxd.ui.theme import set_role, theme
from clipxd.ui.widgets import BrandMark, Card, PopupCombo, Segmented, label, section, styled

THEMES = [("system", "Otomatik"), ("light", "Açık"), ("dark", "Koyu")]
PROXY_RE = re.compile(r"^(https?|socks4a?|socks5h?)://([^\s/@]+@)?[^\s/@:]+(:\d{1,5})?/?$", re.IGNORECASE)


class SettingsPage(QWidget):
    title = "Ayarlar"

    def __init__(self, ctx, on_saved, parent=None):
        super().__init__(parent)
        styled(self, "page")
        self.ctx = ctx
        self.on_saved = on_saved
        self.actions = None
        self._proc = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("scrollBody")
        center = QHBoxLayout(body)
        center.setContentsMargins(24, 4, 24, 24)
        column = QWidget()
        column.setMaximumWidth(760)
        v = QVBoxLayout(column)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        center.addStretch()
        center.addWidget(column, 10)
        center.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll)

        # --- görünüm
        v.addWidget(section("Görünüm"))
        look = Card()
        self.theme_seg = Segmented(THEMES, min_segment=84)
        look.add_row("Tema", self.theme_seg, "Otomatik, Windows'un açık/koyu ayarını izler")
        v.addWidget(look)
        v.addSpacing(14)

        # --- indirme
        v.addWidget(section("İndirme"))
        dl = Card()
        self.template_edit = QLineEdit()
        self.template_edit.setFixedWidth(300)
        dl.add_row("Dosya adı şablonu", self.template_edit,
                   "%(title)s başlık · %(uploader)s yükleyen · %(id)s kimlik · %(upload_date)s tarih. "
                   "Alt klasör: %(uploader)s/%(title)s.%(ext)s")
        self.concurrent = PopupCombo(min_width=90)
        fill_combo(self.concurrent, [(i, str(i)) for i in range(1, 7)])
        dl.add_row("Aynı anda indirme", self.concurrent)
        self.proxy_edit = QLineEdit()
        self.proxy_edit.setFixedWidth(300)
        self.proxy_edit.setPlaceholderText("Yok")
        dl.add_row("Proxy", self.proxy_edit, "Örn: socks5://127.0.0.1:1080 veya http://sunucu:8080")
        v.addWidget(dl)
        v.addSpacing(14)

        # --- ffmpeg
        v.addWidget(section("ffmpeg"))
        ff = Card()
        path_row = QWidget()
        ph = QHBoxLayout(path_row)
        ph.setContentsMargins(0, 0, 0, 0)
        ph.setSpacing(6)
        self.ffmpeg_edit = QLineEdit()
        self.ffmpeg_edit.setFixedWidth(240)
        self.ffmpeg_edit.setPlaceholderText("Otomatik")
        pick = QPushButton("Seç…")
        pick.clicked.connect(self._browse_ffmpeg)
        ph.addWidget(self.ffmpeg_edit)
        ph.addWidget(pick)
        self.ff_row = ff.add_row("Konum", path_row, " ")
        v.addWidget(ff)
        v.addSpacing(14)

        # --- hakkında
        v.addWidget(section("Hakkında"))
        about = Card()
        brand = QWidget()
        bh = QHBoxLayout(brand)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.addWidget(BrandMark(logo_px=34, text_px=20))
        bh.addStretch()
        bh.addWidget(label(f"Sürüm {__version__}", role="secondary"))
        about.add_widget(brand, margins=(8, 8, 14, 8))
        upd = QWidget()
        uh = QHBoxLayout(upd)
        uh.setContentsMargins(0, 0, 0, 0)
        uh.setSpacing(10)
        uh.addWidget(label(YTDLP_VERSION, role="secondary"))
        self.update_btn = QPushButton("Güncelle")
        self.update_btn.clicked.connect(self._update_ytdlp)
        if getattr(sys, "frozen", False):
            self.update_btn.setEnabled(False)
            self.update_btn.setToolTip("Paketlenmiş sürümde güncelleme yeni sürüm indirilerek yapılır.")
        uh.addWidget(self.update_btn)
        about.add_row("yt-dlp", upd, "Bir sitede indirme bozulursa ilk çözüm güncellemektir")
        data_btn = QPushButton("Klasörü Aç")
        data_btn.clicked.connect(lambda: open_folder(str(data_dir())))
        about.add_row("Veriler", data_btn, "Ayarlar ve şifreli hesap bilgileri")
        v.addWidget(about)
        foot = label("Bu aracı yalnızca indirme hakkınız olan içerikler için kullanın. Platformların kullanım "
                     "koşullarına ve telif haklarına uymak kullanıcının sorumluluğundadır.", 11, role="tertiary",
                     wrap=True)
        foot.setContentsMargins(4, 6, 4, 0)
        v.addWidget(foot)
        v.addStretch()

        self._load()
        self.theme_seg.changed.connect(self._theme_changed)
        self.concurrent.currentIndexChanged.connect(lambda _: self._save())
        for edit in (self.template_edit, self.proxy_edit, self.ffmpeg_edit):
            edit.editingFinished.connect(self._save)

    def _load(self):
        s = self.ctx.settings
        self.theme_seg.set_value(s["theme"])
        self.template_edit.setText(s["filename_template"])
        idx = self.concurrent.findData(int(s["max_concurrent"]))
        self.concurrent.setCurrentIndex(max(0, idx))
        self.proxy_edit.setText(s.proxy)
        self.ffmpeg_edit.setText(s["ffmpeg_path"])
        self._show_ffmpeg()

    def _show_ffmpeg(self):
        ff = self.ctx.ffmpeg
        sub = self.ff_row.subtitle_label
        if ff:
            sub.setText(f"Kullanılan: {ff} (sürüm {ffmpeg_version(ff)})")
            set_role(sub, "secondary")
        else:
            sub.setText("ffmpeg bulunamadı!")
            set_role(sub, "danger")

    def _browse_ffmpeg(self):
        path, _ = QFileDialog.getOpenFileName(self.window(), "ffmpeg seç", "",
                                              "ffmpeg (ffmpeg*.exe ffmpeg*);;Tüm dosyalar (*)")
        if path:
            self.ffmpeg_edit.setText(path)
            self._save()

    def _theme_changed(self, mode):
        self.ctx.settings["theme"] = mode
        self.ctx.settings.save()
        theme.apply(mode)

    @staticmethod
    def _template_problem(template: str) -> str:
        if not template:
            return ""
        if "%(ext)s" not in template:
            return "Şablon dosya uzantısı için %(ext)s içermeli, örn: %(title)s.%(ext)s"
        if os.path.isabs(template) or re.match(r"^[a-zA-Z]:", template) or ".." in re.split(r"[\\/]", template):
            return "Şablon seçilen indirme klasörünün içinde kalmalı: mutlak yol veya '..' kullanılamaz."
        return ""

    def _save(self):
        s = self.ctx.settings
        template = self.template_edit.text().strip()
        problem = self._template_problem(template)
        if problem:
            alert(self, "Geçersiz şablon", problem, kind="warning")
            self.template_edit.setText(s["filename_template"])
            return
        proxy = self.proxy_edit.text().strip()
        if proxy and not PROXY_RE.match(proxy):
            alert(self, "Geçersiz proxy", "Biçim: http://sunucu:port, socks5://127.0.0.1:1080 veya "
                                          "http://kullanıcı:şifre@sunucu:port", kind="warning")
            self.proxy_edit.setText(s.proxy)
            return
        s["filename_template"] = template or DEFAULT_TEMPLATE
        s["max_concurrent"] = self.concurrent.currentData()
        if proxy != s.proxy:
            s.proxy = proxy  # şifreli dosyaya yazılır, settings.json'a değil
        ffmpeg_changed = s["ffmpeg_path"] != self.ffmpeg_edit.text().strip()
        s["ffmpeg_path"] = self.ffmpeg_edit.text().strip()
        s.save()
        self.ctx.download_pool.setMaxThreadCount(s["max_concurrent"])
        if ffmpeg_changed:
            self.ctx.refresh_ffmpeg()
            self._show_ffmpeg()
        self.on_saved()

    def _update_ytdlp(self):
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Güncelleniyor…")
        self._proc = QProcess(self)
        self._proc.setProcessChannelMode(QProcess.MergedChannels)
        self._proc.finished.connect(self._update_done)
        self._proc.start(sys.executable, ["-m", "pip", "install", "-U", "yt-dlp[default]"])

    def _update_done(self, code, _status):
        out = bytes(self._proc.readAll()).decode("utf-8", "replace")
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Güncelle")
        if code == 0:
            alert(self, "yt-dlp güncellendi", "Değişikliğin etkili olması için uygulamayı yeniden başlatın.")
        else:
            alert(self, "Güncelleme başarısız", out[-800:], kind="error")
