import os
import threading
import traceback
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path

from PySide6.QtCore import QRunnable, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
                               QStackedLayout, QVBoxLayout, QWidget)

from clipxd import converter as cv
from clipxd.ffmpeg_tools import format_bytes, format_seconds, probe_duration
from clipxd.ui import icons
from clipxd.ui.common import JobSignals, fill_combo, hint_label, human_size, open_folder, reveal_file
from clipxd.ui.joblist import JobList, JobRow
from clipxd.ui.sheets import alert
from clipxd.ui.theme import set_role, theme
from clipxd.ui.widgets import (Card, ElidedLabel, FolderButton, IconButton, PopupCombo, Segmented, Tile, label,
                                 section, styled)

MEDIA_FILTER = ("Medya dosyaları (*.mp4 *.mkv *.webm *.mov *.avi *.flv *.wmv *.m4v *.3gp *.ts *.mts "
                "*.mp3 *.m4a *.aac *.opus *.ogg *.oga *.flac *.wav *.wma *.gif);;Tüm dosyalar (*)")
AUDIO_EXT = {".mp3", ".m4a", ".aac", ".opus", ".ogg", ".oga", ".flac", ".wav", ".wma"}


def kind_of(target_or_path: str) -> str:
    ext = target_or_path.lower().rsplit(".", 1)[-1]
    if ext == "gif":
        return "gif"
    if ext in cv.AUDIO_TARGETS or f".{ext}" in AUDIO_EXT:
        return "audio"
    return "video"


@dataclass
class ConvertJob:
    id: str
    src: Path
    options: cv.ConvertOptions
    state: str = "queued"
    dst: Path | None = None
    cancel: threading.Event = field(default_factory=threading.Event)


class ConvertRunnable(QRunnable):
    def __init__(self, job: ConvertJob, ffmpeg: str, signals: JobSignals):
        super().__init__()
        self.job, self.ffmpeg, self.signals = job, ffmpeg, signals

    def run(self):
        job = self.job
        if job.cancel.is_set():
            self.signals.done.emit(job.id, False, "İptal edildi", [])
            return
        dst = None
        try:
            start, trim = cv.trim_window(job.options)
            duration = probe_duration(self.ffmpeg, str(job.src))
            if duration is not None:
                duration = max(duration - (start or 0), 0.01)
                if trim is not None:
                    duration = min(duration, trim)
            dst = cv.output_path(job.src, job.options)
            job.dst = dst
            self.signals.update.emit(job.id, {"status": "Dönüştürülüyor", "percent": 0 if duration else None,
                                              "detail": dst.name})
            cmd = cv.build_command(self.ffmpeg, job.src, dst, job.options)

            def progress(ratio, speed):
                eta = ""
                if ratio and speed.endswith("x"):
                    try:
                        mult = float(speed[:-1])
                        if mult > 0 and duration:
                            eta = format_seconds(duration * (1 - ratio) / mult)
                    except ValueError:
                        pass
                self.signals.update.emit(job.id, {
                    "status": "Dönüştürülüyor",
                    "percent": ratio * 100 if ratio is not None else None,
                    "speed": speed if speed and speed != "N/A" else "",
                    "eta": eta,
                })

            cv.run_ffmpeg(cmd, duration, progress, job.cancel)
            self.signals.done.emit(job.id, True, "Tamamlandı", [str(dst)])
        except cv.Cancelled:
            if dst:
                dst.unlink(missing_ok=True)
            self.signals.done.emit(job.id, False, "İptal edildi", [])
        except cv.ConversionError as e:
            if dst:
                dst.unlink(missing_ok=True)
            lines = e.args[0] if e.args else []
            self.signals.log.emit(job.id, "error", "\n".join(lines))
            self.signals.done.emit(job.id, False, cv.explain_ffmpeg_error(lines, job.options), [])
        except ValueError as e:
            self.signals.done.emit(job.id, False, str(e), [])
        except Exception as e:
            self.signals.log.emit(job.id, "error", traceback.format_exc())
            self.signals.done.emit(job.id, False, f"Hata: {e}", [])


class FileChip(QWidget):
    removed = Signal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 5, 6, 5)
        h.setSpacing(10)
        k = kind_of(path)
        h.addWidget(Tile(28, "accent", icon_name={"audio": "music", "gif": "photo"}.get(k, "film"), tint=True))
        name = ElidedLabel(Path(path).name, Qt.ElideMiddle)
        name.setToolTip(path)
        h.addWidget(name, 1)
        try:
            size = format_bytes(os.path.getsize(path))
        except OSError:
            size = ""
        h.addWidget(label(size, 11.5, role="tertiary"))
        x = IconButton("xmark", "Kaldır", 22, 12)
        x.clicked.connect(lambda: self.removed.emit(self.path))
        h.addWidget(x)


class DropZone(QFrame):
    """Dosyaları sürükle-bırak alanı; dosya eklenince listeye dönüşür."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(190)
        self._paths: list[str] = []
        self.stack = QStackedLayout(self)

        empty = QWidget()
        ev = QVBoxLayout(empty)
        ev.setSpacing(6)
        ev.addStretch()
        self.empty_icon = QLabel()
        self.empty_icon.setAlignment(Qt.AlignCenter)
        ev.addWidget(self.empty_icon)
        t = label("Dosyaları buraya sürükleyin", 14, QFont.DemiBold, role="secondary")
        t.setAlignment(Qt.AlignCenter)
        ev.addWidget(t)
        s = label("Video veya ses dosyaları — birden fazla seçebilirsiniz", 11.5, role="tertiary")
        s.setAlignment(Qt.AlignCenter)
        ev.addWidget(s)
        pick = QPushButton("Dosya Seç…")
        pick.setCursor(Qt.PointingHandCursor)
        pick.clicked.connect(self.pick)
        pr = QHBoxLayout()
        pr.addStretch()
        pr.addWidget(pick)
        pr.addStretch()
        ev.addSpacing(4)
        ev.addLayout(pr)
        ev.addStretch()
        self.stack.addWidget(empty)

        filled = QWidget()
        fv = QVBoxLayout(filled)
        fv.setContentsMargins(6, 6, 6, 6)
        fv.setSpacing(4)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("scrollBody")
        self.list_layout = QVBoxLayout(body)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        self.list_layout.addStretch()
        scroll.setWidget(body)
        fv.addWidget(scroll, 1)
        bar = QHBoxLayout()
        self.count_label = label("", 11.5, role="secondary")
        add = QPushButton("Dosya Ekle…")
        add.setObjectName("link")
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self.pick)
        clr = QPushButton("Tümünü Kaldır")
        clr.setObjectName("link")
        clr.setCursor(Qt.PointingHandCursor)
        clr.clicked.connect(self.clear)
        bar.addWidget(self.count_label)
        bar.addStretch()
        bar.addWidget(add)
        bar.addWidget(clr)
        fv.addLayout(bar)
        self.stack.addWidget(filled)

        self._paint_icon()
        theme.changed.connect(self._paint_icon)

    def _paint_icon(self):
        self.empty_icon.setPixmap(icons.pixmap("tray_down", theme.c("text3"), 40, 1.5))

    def _set_active(self, on: bool):
        self.setProperty("active", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def pick(self):
        paths, _ = QFileDialog.getOpenFileNames(self.window(), "Dönüştürülecek dosyaları seç", "", MEDIA_FILTER)
        self.add_paths(paths)

    def add_paths(self, paths):
        for p in paths:
            p = str(Path(p))
            if Path(p).is_file() and p not in self._paths:
                self._paths.append(p)
                chip = FileChip(p)
                chip.removed.connect(self.remove)
                self.list_layout.insertWidget(self.list_layout.count() - 1, chip)
        self._refresh()

    def remove(self, path: str):
        if path in self._paths:
            self._paths.remove(path)
        for i in range(self.list_layout.count()):
            w = self.list_layout.itemAt(i).widget()
            if isinstance(w, FileChip) and w.path == path:
                w.hide()
                w.deleteLater()
        self._refresh()

    def clear(self):
        for p in list(self._paths):
            self.remove(p)

    def paths(self) -> list[str]:
        return list(self._paths)

    def _refresh(self):
        n = len(self._paths)
        self.stack.setCurrentIndex(1 if n else 0)
        self.count_label.setText(f"{n} dosya")
        self.changed.emit()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._set_active(True)

    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._set_active(False)

    def dropEvent(self, e):
        self._set_active(False)
        if e.mimeData().hasUrls():
            self.add_paths(u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile())
            e.acceptProposedAction()


class ConvertPage(QWidget):
    title = "Dönüştür"

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        styled(self, "page")
        self.ctx = ctx
        self.jobs: dict[str, ConvertJob] = {}
        self._runnables = {}
        self.signals = JobSignals()
        self.signals.update.connect(self._on_update)
        self.signals.done.connect(self._on_done)
        self.actions = None
        self._build()
        self._load_prefs()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 4, 24, 20)
        root.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(section("Dosyalar"))
        self.drop = DropZone()
        left.addWidget(self.drop, 1)
        top.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(6)
        right.addWidget(section("Çıktı"))
        self.out_card = Card()
        self.mode = Segmented([("encode", "Yeniden kodla"), ("copy", "Uzantı değiştir")], min_segment=104)
        self.out_card.add_row("Mod", self.mode)
        self.target_combo = PopupCombo(min_width=170)
        self.target_combo.addItem("VİDEO")
        self.target_combo.model().item(0).setEnabled(False)
        for k, v in cv.VIDEO_TARGETS.items():
            self.target_combo.addItem(v, k)
        self.target_combo.addItem("SES")
        self.target_combo.model().item(self.target_combo.count() - 1).setEnabled(False)
        for k, v in cv.AUDIO_TARGETS.items():
            self.target_combo.addItem(v, k)
        self.target_combo.setCurrentIndex(1)
        self.out_card.add_row("Biçim", self.target_combo)
        self.folder = FolderButton(allow_same=True)
        self.out_card.add_row("Konum", self.folder)
        right.addWidget(self.out_card)
        self.mode_hint = hint_label("", 300)
        self.mode_hint.setContentsMargins(4, 2, 4, 0)
        right.addWidget(self.mode_hint)
        right.addStretch()
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.start_btn = QPushButton("Dönüştür")
        self.start_btn.setObjectName("pill")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self.start_conversions)
        btn_row.addWidget(self.start_btn)
        right.addLayout(btn_row)
        top.addLayout(right, 1)
        root.addLayout(top)

        mid = QHBoxLayout()
        mid.setSpacing(16)
        self.video_box = QWidget()
        vb = QVBoxLayout(self.video_box)
        vb.setContentsMargins(0, 0, 0, 0)
        vb.setSpacing(6)
        vb.addWidget(section("Görüntü"))
        self.video_card = Card()
        self.codec_combo = PopupCombo(min_width=190)
        fill_combo(self.codec_combo, cv.VIDEO_CODECS)
        self.row_codec = self.video_card.add_row("Codec", self.codec_combo)
        self.quality_combo = PopupCombo()
        fill_combo(self.quality_combo, [(k, v[0]) for k, v in cv.QUALITY_PRESETS.items()])
        self.row_quality = self.video_card.add_row("Kalite", self.quality_combo)
        self.speed_combo = PopupCombo()
        fill_combo(self.speed_combo, [(k, v[0]) for k, v in cv.SPEED_PRESETS.items()])
        self.row_speed = self.video_card.add_row("Kodlama hızı", self.speed_combo)
        self.res_combo = PopupCombo()
        fill_combo(self.res_combo, [(r, "Orijinal" if r == 0 else f"{r}p") for r in cv.RESOLUTIONS])
        self.video_card.add_row("Çözünürlük", self.res_combo)
        self.fps_combo = PopupCombo()
        fill_combo(self.fps_combo, [(f, "Orijinal" if f == 0 else f"{f} fps") for f in cv.FPS_CHOICES])
        self.video_card.add_row("Kare hızı", self.fps_combo)
        vb.addWidget(self.video_card)
        vb.addStretch()
        mid.addWidget(self.video_box, 1)

        audio_box = QVBoxLayout()
        audio_box.setSpacing(6)
        self.audio_section = section("Ses ve Kırpma")
        audio_box.addWidget(self.audio_section)
        self.audio_card = Card()
        self.abr_combo = PopupCombo()
        fill_combo(self.abr_combo, [(b, f"{b} kbps") for b in cv.AUDIO_BITRATES])
        self.row_abr = self.audio_card.add_row("Ses kalitesi", self.abr_combo)
        self.start_edit = QLineEdit()
        self.start_edit.setPlaceholderText("Baştan")
        self.end_edit = QLineEdit()
        self.end_edit.setPlaceholderText("Sona kadar")
        for w in (self.start_edit, self.end_edit):
            w.setFixedWidth(150)
            w.setAlignment(Qt.AlignRight)
            w.setToolTip("Saniye (90), dakika:saniye (1:30) veya saat:dk:sn (0:01:30)")
        self.audio_card.add_row("Başlangıç", self.start_edit, "örn. 1:30")
        self.audio_card.add_row("Bitiş", self.end_edit)
        audio_box.addWidget(self.audio_card)
        audio_box.addStretch()
        mid.addLayout(audio_box, 1)
        root.addLayout(mid)

        clear = QPushButton("Bitenleri Temizle")
        clear.setObjectName("link")
        clear.setCursor(Qt.PointingHandCursor)
        clear.clicked.connect(self._clear_finished)
        root.addWidget(section("Dönüşümler", clear))
        self.list = JobList("convert", "Henüz dönüşüm yok",
                            "Dosya ekleyip biçimi seçin, ardından Dönüştür'e basın.")
        self.list.setMinimumHeight(120)
        root.addWidget(self.list, 1)

        self.mode.changed.connect(lambda _: self._update_enabled())
        self.target_combo.currentIndexChanged.connect(self._update_enabled)
        self.codec_combo.currentIndexChanged.connect(self._update_enabled)

    def _update_enabled(self):
        target = self.target_combo.currentData()
        is_audio = target in cv.AUDIO_TARGETS
        is_gif = target == "gif"
        self.mode.set_item_enabled(1, not is_gif)
        if is_gif and self.mode.value() == "copy":
            self.mode.set_value("encode")
        encode = self.mode.value() == "encode"

        self.video_box.setVisible(encode and not is_audio)
        codec_ok = target in ("mp4", "mkv", "mov")
        self.video_card.set_row_visible(self.row_codec, codec_ok)
        self.video_card.set_row_visible(self.row_quality, not is_gif)
        self.video_card.set_row_visible(self.row_speed, not is_gif)
        if target == "mov" and self.codec_combo.currentData() == "vp9":
            self.codec_combo.setCurrentIndex(self.codec_combo.findData("h264"))
        abr_ok = encode and not is_gif and target not in cv.LOSSLESS_AUDIO
        self.audio_card.set_row_visible(self.row_abr, abr_ok)
        self.audio_section.findChild(QLabel).setText("Ses ve Kırpma" if abr_ok else "Kırpma")

        if not encode:
            self.mode_hint.setText("Görüntü ve ses yeniden kodlanmaz; kalite birebir korunur, işlem saniyeler "
                                   "sürer. Hedef biçim kaynaktaki codec'i desteklemiyorsa 'Yeniden kodla' seçin.")
        elif is_gif:
            self.mode_hint.setText("GIF için çözünürlük (varsayılan 480p) ve kare hızı (varsayılan 12) kullanılır. "
                                   "Uzun videolarda başlangıç ve bitiş belirlemeniz önerilir.")
        elif is_audio:
            self.mode_hint.setText("Videodan ses çıkarır veya ses dosyasını başka bir biçime çevirir.")
        else:
            self.mode_hint.setText("Çözünürlük yalnızca küçültülür. 'Kayıpsıza yakın' en yüksek kaliteyi, "
                                   "'Çok küçük dosya' en küçük boyutu verir.")

    def _load_prefs(self):
        p = self.ctx.settings["convert"]
        self.mode.set_value(p["mode"])
        for combo, key in ((self.target_combo, "target"), (self.codec_combo, "video_codec"),
                           (self.quality_combo, "quality"), (self.speed_combo, "speed"),
                           (self.res_combo, "resolution"), (self.fps_combo, "fps"),
                           (self.abr_combo, "audio_bitrate")):
            idx = combo.findData(p[key])
            if idx >= 0:
                combo.setCurrentIndex(idx)
        self.folder.set_path(p["out_dir"])
        self._update_enabled()

    def _options(self) -> cv.ConvertOptions:
        return cv.ConvertOptions(
            mode=self.mode.value(),
            target=self.target_combo.currentData(),
            video_codec=self.codec_combo.currentData(),
            quality=self.quality_combo.currentData(),
            resolution=self.res_combo.currentData(),
            fps=self.fps_combo.currentData(),
            audio_bitrate=self.abr_combo.currentData(),
            speed=self.speed_combo.currentData(),
            start=self.start_edit.text().strip(),
            end=self.end_edit.text().strip(),
            out_dir=self.folder.path,
        )

    def _save_prefs(self):
        o = self._options()
        self.ctx.settings["convert"] = {
            "mode": o.mode, "target": o.target, "video_codec": o.video_codec, "quality": o.quality,
            "resolution": o.resolution, "fps": o.fps, "audio_bitrate": o.audio_bitrate, "speed": o.speed,
            "out_dir": o.out_dir,
        }
        self.ctx.settings.save()

    def add_files(self, paths):
        self.drop.add_paths(paths)

    @staticmethod
    def _target_label(opts: cv.ConvertOptions) -> str:
        label_ = (cv.VIDEO_TARGETS | cv.AUDIO_TARGETS)[opts.target].split(" (")[0]
        return label_ + (" · kayıpsız" if opts.effective_mode() == "copy" else "")

    def start_conversions(self):
        paths = self.drop.paths()
        if not paths:
            alert(self, "Dosya eklenmedi", "Önce dönüştürülecek dosyaları sürükleyip bırakın veya seçin.")
            return
        if not self.ctx.ffmpeg:
            alert(self, "ffmpeg bulunamadı", "Ayarlar'dan ffmpeg konumunu belirtin.", kind="error")
            return
        opts = self._options()
        try:
            cv.trim_window(opts)
        except ValueError as e:
            alert(self, "Kırpma aralığı geçersiz", str(e), kind="warning")
            return
        if opts.out_dir:
            Path(opts.out_dir).mkdir(parents=True, exist_ok=True)
        self._save_prefs()
        for p in paths:
            job = ConvertJob(uuid.uuid4().hex, Path(p), replace(opts))
            self.jobs[job.id] = job
            row = JobRow(job.id, job.src.name, f"→ {self._target_label(opts)} — Sırada", kind_of(opts.target))
            row.action.connect(self._on_action)
            self.list.add(row)
            self._start(job)
        self.drop.clear()

    def _start(self, job: ConvertJob):
        job.cancel = threading.Event()
        job.state = "queued"
        row = self.list.row(job.id)
        if row:
            row.set_state("queued", f"→ {self._target_label(job.options)} — Sırada", 0)
        r = ConvertRunnable(job, self.ctx.ffmpeg, self.signals)
        r.setAutoDelete(False)
        self._runnables[job.id] = r
        self.ctx.convert_pool.start(r)

    def _on_update(self, job_id, d):
        job = self.jobs.get(job_id)
        row = self.list.row(job_id)
        if not job or not row or job.state not in ("queued", "running"):
            return
        job.state = "running"
        target = d.get("detail") or (job.dst.name if job.dst else self._target_label(job.options))
        parts = [p for p in (d.get("speed", ""), f"{d['eta']} kaldı" if d.get("eta") else "") if p]
        sub = f"→ {target} — {d.get('status', '')}" + (" · " + " · ".join(parts) if parts else "…")
        row.set_state("running", sub, d.get("percent"))

    def _on_done(self, job_id, ok, msg, files):
        self._runnables.pop(job_id, None)
        job = self.jobs.get(job_id)
        row = self.list.row(job_id)
        if not job or not row:
            return
        if ok:
            job.state = "done"
            row.set_state("done", f"→ {Path(files[0]).name} — {human_size(files)}")
        else:
            job.state = "cancelled" if msg == "İptal edildi" else "error"
            row.set_state(job.state, msg if job.state == "error" else "İptal edildi")

    def _on_action(self, job_id, action):
        job = self.jobs.get(job_id)
        if not job:
            return
        if action == "cancel" and job.state in ("queued", "running"):
            job.cancel.set()
            r = self._runnables.get(job_id)
            if job.state == "queued" and r and self.ctx.convert_pool.tryTake(r):
                self._on_done(job_id, False, "İptal edildi", [])
        elif action == "retry" and job.state in ("error", "cancelled"):
            self._start(job)
        elif action == "reveal":
            if job.state == "done" and job.dst:
                reveal_file(str(job.dst))
            else:
                open_folder(str(job.src.parent))
        elif action == "folder":
            open_folder(str(job.dst.parent if job.dst else job.src.parent))
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
