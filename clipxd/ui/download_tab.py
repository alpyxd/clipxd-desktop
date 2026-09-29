import os
import re
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path

from PySide6.QtCore import QRunnable, Qt, QTimer
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget
from yt_dlp.utils import DownloadCancelled, DownloadError

from clipxd import accounts as acc
from clipxd.downloader import (AUDIO_FORMATS, AUDIO_QUALITIES, BITRATE_AUDIO, THUMBNAIL_AUDIO, VIDEO_CONTAINERS,
                                 VIDEO_QUALITIES, DownloadOptions, friendly_error, playlist_folder_name, run_download)
from clipxd.ui import icons
from clipxd.ui.common import JobSignals, fill_combo, human_size, open_folder, reveal_file
from clipxd.ui.joblist import JobList, JobRow
from clipxd.ui.platforms import PlatformStrip
from clipxd.ui.playlist_sheet import PlaylistSheet
from clipxd.ui.sheets import alert
from clipxd.ui.theme import font, theme
from clipxd.ui.widgets import Card, FolderButton, IconButton, PopupCombo, Segmented, Toggle, section, styled

URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


@dataclass
class DownloadJob:
    id: str
    number: int
    url: str
    options: DownloadOptions
    account_id: str | None
    account_name: str = ""
    state: str = "queued"          # queued | running | done | error | cancelled
    title: str = ""
    files: list = field(default_factory=list)
    cancel: threading.Event = field(default_factory=threading.Event)
    folder: str = ""               # oynatma listesi klasörü
    playlist_title: str = ""
    selection: list | None = None  # kullanıcının listeden seçtiği sıra numaraları
    selection_ready: threading.Event = field(default_factory=threading.Event)


class DownloadRunnable(QRunnable):
    def __init__(self, job: DownloadJob, ctx, signals: JobSignals):
        super().__init__()
        self.job, self.ctx, self.signals = job, ctx, signals
        self._last_emit = 0.0
        self._last_status = None

    def _on_update(self, d: dict):
        # Arayüzü boğmamak için sık gelen ilerleme olaylarını seyreltir
        now = time.monotonic()
        if d.get("status") == self._last_status and now - self._last_emit < 0.2:
            return
        self._last_emit, self._last_status = now, d.get("status")
        self.signals.update.emit(self.job.id, d)

    def _choose(self, playlist):
        """İş parçacığında çalışır: seçim penceresini arayüze sorar ve yanıtı bekler."""
        job = self.job
        job.selection = None
        job.selection_ready.clear()
        self.signals.playlist.emit(job.id, playlist)
        while not job.selection_ready.wait(0.2):
            if job.cancel.is_set():
                return None
        return job.selection

    def run(self):
        job = self.job
        if job.cancel.is_set():
            self.signals.done.emit(job.id, False, "İptal edildi", [])
            return
        try:
            cookie_text = None
            account = self.ctx.accounts.get(job.account_id) if job.account_id else None
            if job.account_id and account is None:
                raise RuntimeError("Seçilen hesap artık yok")
            if account:
                cookie_text = self.ctx.accounts.load_cookie_text(account.id)
            result = run_download(job.url, job.options, self.ctx.ffmpeg, cookie_text, self._on_update,
                                  lambda lvl, msg: self.signals.log.emit(job.id, lvl, msg), job.cancel,
                                  choose=self._choose)
            job.folder, job.playlist_title = result.folder, result.playlist_title
            if account and result.cookiejar is not None:
                # site oturum çerezlerini yenilediyse güncel hâlini sakla
                self.ctx.accounts.store_jar_after_use(account.id, acc.filter_jar(result.cookiejar, account.domains))
            msg = "Tamamlandı"
            if result.errors:
                msg += f" ({len(result.errors)} öğe hatalı)"
            self.signals.done.emit(job.id, True, msg, result.files)
        except DownloadCancelled:
            self.signals.done.emit(job.id, False, "İptal edildi", [])
        except DownloadError as e:
            self.signals.log.emit(job.id, "error", str(e))
            self.signals.done.emit(job.id, False, friendly_error(str(e)), [])
        except Exception as e:  # beklenmeyen hata: arayüz çökmesin
            self.signals.log.emit(job.id, "error", traceback.format_exc())
            self.signals.done.emit(job.id, False, f"Hata: {e}", [])


class UrlEdit(QPlainTextEdit):
    """Link alanı: Ctrl+Enter ile indirmeyi başlatır, odakta kartı vurgular."""

    def __init__(self, card: QFrame, on_submit):
        super().__init__()
        self.card = card
        self.on_submit = on_submit
        self.setObjectName("bare")
        self.setFont(font(14))
        self.setTabChangesFocus(True)

    def _set_focus_prop(self, value: bool):
        self.card.setProperty("focus", value)
        self.card.style().unpolish(self.card)
        self.card.style().polish(self.card)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self._set_focus_prop(True)

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self._set_focus_prop(False)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and e.modifiers() & Qt.ControlModifier:
            self.on_submit()
            return
        super().keyPressEvent(e)


class DownloadPage(QWidget):
    title = "İndir"

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        styled(self, "page")
        self.ctx = ctx
        self.jobs: dict[str, DownloadJob] = {}
        self._runnables = {}
        self._counter = 0
        self.signals = JobSignals()
        self.signals.update.connect(self._on_update)
        self.signals.log.connect(self._on_log)
        self.signals.done.connect(self._on_done)
        self.signals.playlist.connect(self._on_playlist)
        self._selection_queue: list = []   # aynı anda birden çok liste gelirse sırayla sorulur
        self._selecting = False
        self._build()
        self._load_prefs()
        self.ctx.accounts.listeners.append(self._refresh_accounts)
        self._refresh_accounts()

    # ------------------------------------------------------------------ arayüz
    def _build(self):
        # sayfa başlığı yerine: hangi platformlardan indirilebildiği
        self.header = PlatformStrip(self._show_sites)
        self.actions = QWidget()
        ah = QHBoxLayout(self.actions)
        ah.setContentsMargins(0, 0, 0, 0)
        open_btn = IconButton("folder", "İndirme klasörünü aç", 30, 18)
        open_btn.clicked.connect(lambda: open_folder(self.folder.path))
        ah.addWidget(open_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 4, 24, 20)
        root.setSpacing(12)

        # --- link kartı
        url_card = QFrame()
        url_card.setObjectName("urlCard")
        uh = QHBoxLayout(url_card)
        uh.setContentsMargins(14, 10, 10, 10)
        uh.setSpacing(10)
        self.link_icon = QLabel()
        uh.addWidget(self.link_icon, 0, Qt.AlignTop)
        self.urls = UrlEdit(url_card, self.start_downloads)
        self.urls.setPlaceholderText("Video, gönderi, reel veya oynatma listesi linkini yapıştırın\n"
                                     "Birden fazla link için her satıra bir tane — Ctrl+Enter ile başlat")
        self.urls.setFixedHeight(54)
        uh.addWidget(self.urls, 1)
        paste = IconButton("clipboard", "Panodan yapıştır", 32, 18)
        paste.clicked.connect(self._paste)
        uh.addWidget(paste, 0, Qt.AlignVCenter)
        self.start_btn = QPushButton("İndir")
        self.start_btn.setObjectName("pill")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setFont(font(13, QFont.DemiBold))
        self.start_btn.clicked.connect(self.start_downloads)
        uh.addWidget(self.start_btn, 0, Qt.AlignVCenter)
        root.addWidget(url_card)

        # --- seçenek kartları
        cols = QHBoxLayout()
        cols.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(section("Biçim"))
        self.fmt_card = Card()
        self.kind = Segmented([("video", "Video"), ("audio", "Ses")], min_segment=74)
        self.fmt_card.add_row("Tür", self.kind)
        self.container_combo = PopupCombo()
        fill_combo(self.container_combo, VIDEO_CONTAINERS)
        self.row_container = self.fmt_card.add_row("Biçim", self.container_combo)
        self.audio_format_combo = PopupCombo(min_width=190)
        fill_combo(self.audio_format_combo, AUDIO_FORMATS)
        self.row_audio_fmt = self.fmt_card.add_row("Biçim", self.audio_format_combo)
        self.quality_combo = PopupCombo()
        fill_combo(self.quality_combo, VIDEO_QUALITIES)
        self.row_quality = self.fmt_card.add_row("Kalite", self.quality_combo)
        self.audio_quality_combo = PopupCombo()
        fill_combo(self.audio_quality_combo, [(q, f"{q} kbps") for q in AUDIO_QUALITIES])
        self.row_audio_q = self.fmt_card.add_row("Kalite", self.audio_quality_combo)
        self.account_combo = PopupCombo(min_width=190)
        self.account_combo.setToolTip("Gizli / hesaba özel içerikler için giriş yapılmış hesap kullanılır.")
        self.fmt_card.add_row("Hesap", self.account_combo)
        self.folder = FolderButton()
        self.folder.changed.connect(lambda _: self._save_prefs())
        self.fmt_card.add_row("Konum", self.folder)
        left.addWidget(self.fmt_card)
        left.addStretch()

        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(section("Seçenekler"))
        self.opt_card = Card()
        self.compat = Toggle()
        self.row_compat = self.opt_card.add_row("Uyumluluk öncelikli", self.compat, "H.264/AAC — her cihazda oynatılır")
        self.thumb = Toggle()
        self.row_thumb = self.opt_card.add_row("Kapak resmini göm", self.thumb)
        self.meta = Toggle()
        self.opt_card.add_row("Başlık ve sanatçı bilgisi", self.meta)
        self.subs = Toggle()
        self.row_subs = self.opt_card.add_row("Altyazıları göm", self.subs, "Türkçe ve İngilizce")
        self.playlist = Toggle()
        self.opt_card.add_row("Linkteki listeyi aç", self.playlist,
                              "Video bir listeye aitse (list=…) listeden seçim yapılır")
        right.addWidget(self.opt_card)
        right.addStretch()
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        root.addLayout(cols)

        # --- indirme listesi
        tools = QWidget()
        th = QHBoxLayout(tools)
        th.setContentsMargins(0, 0, 0, 0)
        th.setSpacing(4)
        self.log_btn = IconButton("terminal", "Ayrıntılı günlüğü göster", 26, 16)
        self.log_btn.setCheckable(True)
        self.log_btn.toggled.connect(lambda on: self.log_view.setVisible(on))
        clear = QPushButton("Bitenleri Temizle")
        clear.setObjectName("link")
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(self._clear_finished)
        th.addWidget(self.log_btn)
        th.addWidget(clear)
        root.addWidget(section("İndirmeler", tools))
        self.list = JobList("tray_down", "Henüz indirme yok",
                            "Bir link yapıştırıp İndir'e basın. İndirilenler burada görünür.")
        root.addWidget(self.list, 1)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("log")
        self.log_view.setReadOnly(True)
        self.log_view.setFont(font(11, mono=True))
        self.log_view.setMaximumBlockCount(3000)
        self.log_view.setFixedHeight(150)
        self.log_view.hide()
        root.addWidget(self.log_view)

        self.kind.changed.connect(lambda _: self._update_enabled())
        self.container_combo.currentIndexChanged.connect(self._update_enabled)
        self.audio_format_combo.currentIndexChanged.connect(self._update_enabled)
        self._paint_icons()
        theme.changed.connect(self._paint_icons)

    def _paint_icons(self):
        self.link_icon.setPixmap(icons.pixmap("link", theme.c("text3"), 18))

    def _show_sites(self):
        from clipxd.ui.sites_sheet import SitesSheet
        QGuiApplication.setOverrideCursor(Qt.WaitCursor)  # ilk açılışta liste hazırlanır
        try:
            sheet = SitesSheet(self)
        finally:
            QGuiApplication.restoreOverrideCursor()
        sheet.exec()

    def _update_enabled(self):
        video = self.kind.value() == "video"
        card = self.fmt_card
        for row in (self.row_container, self.row_quality):
            row.setVisible(video)
        for row in (self.row_audio_fmt, self.row_audio_q):
            row.setVisible(not video)
        audio_fmt = self.audio_format_combo.currentData()
        self.audio_quality_combo.setEnabled(audio_fmt in BITRATE_AUDIO)
        card.refresh_separators()
        self.row_compat.setVisible(video)
        self.row_subs.setVisible(video)
        self.compat.setEnabled(self.container_combo.currentData() == "mp4")
        thumb_ok = (self.container_combo.currentData() != "webm") if video else audio_fmt in THUMBNAIL_AUDIO
        self.thumb.setEnabled(thumb_ok)
        self.opt_card.refresh_separators()

    def _load_prefs(self):
        p = self.ctx.settings["download"]
        self.kind.set_value(p["kind"])
        for combo, key in ((self.container_combo, "container"), (self.quality_combo, "quality"),
                           (self.audio_format_combo, "audio_format"), (self.audio_quality_combo, "audio_quality")):
            idx = combo.findData(p[key])
            if idx >= 0:
                combo.setCurrentIndex(idx)
        self.compat.setChecked(p["compat"])
        self.thumb.setChecked(p["embed_thumbnail"])
        self.meta.setChecked(p["embed_metadata"])
        self.subs.setChecked(p["embed_subs"])
        self.playlist.setChecked(p["playlist"])
        self.folder.set_path(self.ctx.settings["download_dir"])
        self._update_enabled()

    def _save_prefs(self):
        self.ctx.settings["download"] = {
            "kind": self.kind.value(),
            "container": self.container_combo.currentData(),
            "quality": self.quality_combo.currentData(),
            "compat": self.compat.isChecked(),
            "audio_format": self.audio_format_combo.currentData(),
            "audio_quality": self.audio_quality_combo.currentData(),
            "embed_thumbnail": self.thumb.isChecked(),
            "embed_metadata": self.meta.isChecked(),
            "embed_subs": self.subs.isChecked(),
            "playlist": self.playlist.isChecked(),
        }
        self.ctx.settings["download_dir"] = self.folder.path
        self.ctx.settings.save()

    def _refresh_accounts(self):
        current = self.account_combo.currentData()
        items = [("auto", "Otomatik"), ("none", "Hesap kullanma")]
        items += [(a.id, f"{a.name} — {a.platform_name}") for a in self.ctx.accounts.all()]
        fill_combo(self.account_combo, items, current or "auto")

    def _paste(self):
        text = QGuiApplication.clipboard().text().strip()
        if text:
            existing = self.urls.toPlainText().strip()
            self.urls.setPlainText(f"{existing}\n{text}".strip())

    def _options(self) -> DownloadOptions:
        video = self.kind.value() == "video"
        return DownloadOptions(
            kind="video" if video else "audio",
            container=self.container_combo.currentData(),
            quality=self.quality_combo.currentData(),
            compat=self.compat.isChecked(),
            audio_format=self.audio_format_combo.currentData(),
            audio_quality=self.audio_quality_combo.currentData(),
            embed_thumbnail=self.thumb.isChecked() and self.thumb.isEnabled(),
            embed_metadata=self.meta.isChecked(),
            embed_subs=self.subs.isChecked() and video,
            playlist=self.playlist.isChecked(),
            out_dir=self.folder.path,
            template=self.ctx.settings["filename_template"],
            proxy=self.ctx.settings.proxy,
        )

    @staticmethod
    def _summary(o: DownloadOptions) -> str:
        if o.kind == "audio":
            s = AUDIO_FORMATS[o.audio_format].split(" (")[0]
            return f"{s} · {o.audio_quality} kbps" if o.audio_format in BITRATE_AUDIO else s
        q = dict(VIDEO_QUALITIES)[o.quality].split(" (")[0]
        return f"{o.container.upper()} · {q}"

    # ------------------------------------------------------------------ işler
    def start_downloads(self):
        urls = URL_RE.findall(self.urls.toPlainText())
        urls = list(dict.fromkeys(u.rstrip(").,;'\"") for u in urls))
        if not urls:
            alert(self, "Link bulunamadı", "Lütfen en az bir geçerli link (http veya https ile başlayan) girin.")
            return
        # Aynı link aynı anda iki kez indirilirse iki iş aynı geçici dosyaya yazıp çıktıyı bozar
        active = {j.url for j in self.jobs.values() if j.state in ("queued", "running")}
        skipped = [u for u in urls if u in active]
        urls = [u for u in urls if u not in active]
        if skipped:
            alert(self, "Zaten indiriliyor", f"{len(skipped)} link şu anda indiriliyor, tekrar eklenmedi."
                  if urls else "Bu link şu anda indiriliyor. Bitmesini bekleyin veya iptal edip yeniden başlatın.")
            if not urls:
                return
        opts = self._options()
        if not opts.out_dir:
            alert(self, "Konum seçilmedi", "Lütfen indirilen dosyaların kaydedileceği klasörü seçin.")
            return
        if not self.ctx.ffmpeg:
            alert(self, "ffmpeg bulunamadı", "Birleştirme ve dönüştürme yapılamayacak. Ayarlar'dan ffmpeg "
                                             "konumunu kontrol edin.", kind="warning")
        self._save_prefs()
        choice = self.account_combo.currentData()
        for url in urls:
            if choice == "auto":
                account = self.ctx.accounts.find_for_url(url)
            elif choice == "none":
                account = None
            else:
                account = self.ctx.accounts.get(choice)
            self._counter += 1
            job = DownloadJob(uuid.uuid4().hex, self._counter, url, replace(opts),
                              account.id if account else None, account.name if account else "")
            self.jobs[job.id] = job
            row = JobRow(job.id, url, self._summary(opts) + " — Sırada", opts.kind)
            row.menu_extra = [("Linki kopyala", "copy")]
            row.action.connect(self._on_action)
            self.list.add(row)
            self._start(job)
        self.urls.clear()

    def _start(self, job: DownloadJob):
        job.cancel = threading.Event()
        job.state = "queued"
        job.files = []
        job.folder = ""
        row = self.list.row(job.id)
        if row:
            row.set_state("queued", self._summary(job.options) + " — Sırada", 0)
        runnable = DownloadRunnable(job, self.ctx, self.signals)
        runnable.setAutoDelete(False)
        self._runnables[job.id] = runnable
        self.ctx.download_pool.start(runnable)

    @staticmethod
    def _details(d: dict) -> str:
        status = d.get("status", "")
        if status.startswith("İndiriliyor") and (d.get("downloaded") or d.get("speed")):
            progress = f"{d['downloaded']} / {d['size']}" if d.get("size") else d.get("downloaded", "")
            parts = [progress, d.get("speed", ""), f"{d['eta']} kaldı" if d.get("eta") else ""]
            return " · ".join(p for p in parts if p)
        return f"{status}…" if status else ""

    def _on_update(self, job_id: str, d: dict):
        job = self.jobs.get(job_id)
        row = self.list.row(job_id)
        if not job or not row or job.state in ("done", "error", "cancelled"):
            return
        job.state = "running"
        if d.get("playlist"):
            job.playlist_title = d["playlist"]
        if d.get("status") == "Seçim bekleniyor":
            row.set_title(job.playlist_title or job.url)
            row.tile.set(icon_name="list")
            row.set_state("running", "Oynatma listesi — indirilecek öğeleri seçin…", None)
            return
        details = self._details(d)
        index, count = d.get("index"), d.get("count")
        if job.playlist_title and index and count:
            # liste: başlıkta liste adı, altta "[3/10] video adı", çubukta listenin genel ilerlemesi
            row.set_title(job.playlist_title)
            percent = d.get("percent")
            overall = ((index - 1) + (percent if percent is not None else 100) / 100) / count * 100
            sub = f"[{index}/{count}] {d.get('title') or ''}" + (f" — {details}" if details else "")
            row.set_state("running", sub, overall)
            return
        if d.get("title"):
            job.title = d["title"]
        row.set_title(job.title or job.url)
        summary = self._summary(job.options)
        row.set_state("running", f"{summary} — {details}" if details else summary, d.get("percent"))

    def _on_playlist(self, job_id: str, playlist):
        self._selection_queue.append((job_id, playlist))
        QTimer.singleShot(0, self._next_selection)  # sinyal işleyicisinin dışında aç

    def _next_selection(self):
        if self._selecting or not self._selection_queue:
            return
        job_id, playlist = self._selection_queue.pop(0)
        job = self.jobs.get(job_id)
        if job is None or job.cancel.is_set():
            if job is not None:
                job.selection_ready.set()
            QTimer.singleShot(0, self._next_selection)
            return
        self._selecting = True
        try:
            folder = os.path.join(job.options.out_dir, playlist_folder_name(playlist.title))
            job.selection = PlaylistSheet(self, playlist, folder, job.options.kind).exec()
        finally:
            self._selecting = False
            job.selection_ready.set()
        QTimer.singleShot(0, self._next_selection)

    def _on_log(self, job_id: str, level: str, msg: str):
        job = self.jobs.get(job_id)
        prefix = f"[#{job.number}]" if job else ""
        tag = {"warning": "UYARI ", "error": "HATA "}.get(level, "")
        self.log_view.appendPlainText(f"{prefix} {tag}{msg}")

    def _on_done(self, job_id: str, ok: bool, msg: str, files: list):
        self._runnables.pop(job_id, None)
        job = self.jobs.get(job_id)
        row = self.list.row(job_id)
        if not job or not row:
            return
        job.files = files
        summary = self._summary(job.options)
        if ok:
            job.state = "done"
            note = "" if msg == "Tamamlandı" else f" · {msg}"
            size = human_size(files)
            if job.folder:
                row.set_title(job.playlist_title or Path(job.folder).name)
                row.set_state("done", f"{summary} — {len(files)} dosya · {size} · klasör: {Path(job.folder).name}{note}")
            else:
                extra = f" · {len(files)} dosya" if len(files) > 1 else ""
                row.set_state("done", f"{summary} — {size or 'Tamamlandı'}{extra}{note}")
                if not job.title and files:
                    row.set_title(Path(files[-1]).stem)
        else:
            job.state = "cancelled" if msg == "İptal edildi" else "error"
            row.set_state(job.state, msg if job.state == "error" else f"{summary} — İptal edildi")

    def _on_action(self, job_id: str, action: str):
        job = self.jobs.get(job_id)
        if not job:
            return
        if action == "cancel" and job.state in ("queued", "running"):
            job.cancel.set()
            runnable = self._runnables.get(job_id)
            if job.state == "queued" and runnable and self.ctx.download_pool.tryTake(runnable):
                self._on_done(job_id, False, "İptal edildi", [])  # henüz başlamamıştı
            else:
                self.list.row(job_id).set_state("running", self._summary(job.options) + " — İptal ediliyor…")
        elif action == "retry" and job.state in ("error", "cancelled"):
            self._start(job)
        elif action == "reveal":
            if job.folder:
                open_folder(job.folder)  # liste: klasörün kendisini aç
            elif job.files:
                reveal_file(job.files[-1])
            else:
                open_folder(job.options.out_dir)
        elif action == "folder":
            open_folder(job.folder or job.options.out_dir)
        elif action == "copy":
            QGuiApplication.clipboard().setText(job.url)
        elif action == "remove" and job.state not in ("queued", "running"):
            self.list.remove(job_id)
            del self.jobs[job_id]

    def _clear_finished(self):
        for jid, job in list(self.jobs.items()):
            if job.state in ("done", "error", "cancelled"):
                self.list.remove(jid)
                del self.jobs[jid]

    def active_count(self) -> int:
        return sum(1 for j in self.jobs.values() if j.state in ("queued", "running"))

    def cancel_all(self):
        for job in self.jobs.values():
            job.cancel.set()

    def shutdown(self):
        self._save_prefs()
