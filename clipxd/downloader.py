"""yt-dlp tabanlı indirme motoru (Qt'den bağımsız)."""
import io
import os
import threading
from dataclasses import dataclass, field

import yt_dlp
from yt_dlp.postprocessor.common import PostProcessor
from yt_dlp.utils import DownloadCancelled, DownloadError, sanitize_filename

from clipxd.ffmpeg_tools import format_bytes, format_seconds
from clipxd.settings import DEFAULT_TEMPLATE

UNIQUE_FIELD = "%(mk_suffix|)s"  # çakışmada " (2)" gibi ek; UniqueNamePP doldurur

VIDEO_CONTAINERS = {"mp4": "MP4", "mkv": "MKV", "webm": "WEBM"}
VIDEO_QUALITIES = [
    (0, "En iyi (orijinal)"),
    (2160, "2160p (4K)"),
    (1440, "1440p (2K)"),
    (1080, "1080p (Full HD)"),
    (720, "720p (HD)"),
    (480, "480p"),
    (360, "360p"),
    (240, "240p"),
]
AUDIO_FORMATS = {
    "mp3": "MP3",
    "m4a": "M4A (AAC)",
    "opus": "OPUS",
    "flac": "FLAC",
    "wav": "WAV",
    "best": "Orijinal (dönüştürmeden)",
}
AUDIO_QUALITIES = [320, 256, 192, 160, 128, 96]
BITRATE_AUDIO = {"mp3", "m4a", "opus"}
THUMBNAIL_AUDIO = {"mp3", "m4a", "opus", "flac"}

JS_RUNTIMES = {"deno": {}, "node": {}, "bun": {}}


@dataclass
class DownloadOptions:
    kind: str = "video"               # "video" | "audio"
    container: str = "mp4"
    quality: int = 0                  # 0 = en iyi, aksi halde maksimum yükseklik
    compat: bool = True               # MP4'te H.264/AAC tercih et
    audio_format: str = "mp3"
    audio_quality: int = 320          # kbps
    embed_thumbnail: bool = True
    embed_metadata: bool = True
    embed_subs: bool = False
    playlist: bool = False
    out_dir: str = "."
    template: str = DEFAULT_TEMPLATE
    proxy: str = ""


def with_unique_suffix(template: str) -> str:
    """Şablonun uzantıdan hemen önceki yerine çakışma ekini koyar."""
    template = template or DEFAULT_TEMPLATE
    if "mk_suffix" in template:
        return template
    if template.endswith(".%(ext)s"):
        return template[: -len(".%(ext)s")] + UNIQUE_FIELD + ".%(ext)s"
    return template


# Aynı anda çalışan indirmelerin seçtiği dosya adları (henüz diskte olmayabilir)
_claimed_names: set[str] = set()
_claim_lock = threading.Lock()


def _name_key(path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.splitext(path)[0]))


class UniqueNamePP(PostProcessor):
    """Aynı adlı dosya varsa üzerine yazmak/atlamak yerine 'Başlık (1).mp4' gibi yeni ad verir.

    'video' aşamasında, yt-dlp dosya adını hesaplamadan hemen önce çalışır. Seçilen ad, indirme
    bitene kadar rezerve edilir; böylece aynı başlıklı iki eşzamanlı indirme aynı geçici dosyaya
    yazıp birbirini bozmaz. release() çağrılınca rezervasyon kalkar.
    """

    def __init__(self, downloader=None):
        super().__init__(downloader)
        self.claimed: list[str] = []

    def run(self, info):
        ydl = self._downloader
        final_ext = ydl.params.get("final_ext")

        def taken(path: str) -> bool:
            if _name_key(path) in _claimed_names or os.path.exists(path):
                return True
            # ses çıkarma / kapsayıcı değiştirmede son dosya farklı uzantıda olur
            return bool(final_ext) and os.path.exists(os.path.splitext(path)[0] + "." + final_ext)

        with _claim_lock:
            info.pop("mk_suffix", None)
            path = ydl.prepare_filename(info)
            n = 1  # dönüştürücü ve tarayıcılarla aynı: "Ad (1).mp4"
            while path and taken(path):
                info["mk_suffix"] = f" ({n})"
                path = ydl.prepare_filename(info)
                n += 1
            if path:
                key = _name_key(path)
                _claimed_names.add(key)
                self.claimed.append(key)
        return [], info

    def release(self):
        with _claim_lock:
            for key in self.claimed:
                _claimed_names.discard(key)
            self.claimed.clear()


@dataclass
class PlaylistEntry:
    index: int          # listedeki sıra (1'den başlar) — yt-dlp playlist_items ile aynı
    id: str
    title: str
    duration: float | None
    url: str


@dataclass
class PlaylistInfo:
    title: str
    uploader: str
    entries: list

    @property
    def total_duration(self) -> float:
        return sum(e.duration or 0 for e in self.entries)


def playlist_from_info(info: dict) -> PlaylistInfo:
    entries = []
    for i, e in enumerate(info.get("entries") or [], start=1):
        if not e:
            continue
        entries.append(PlaylistEntry(
            index=i, id=str(e.get("id") or ""), title=e.get("title") or e.get("url") or f"Öğe {i}",
            duration=e.get("duration"), url=e.get("url") or e.get("webpage_url") or ""))
    return PlaylistInfo(
        title=info.get("title") or info.get("id") or "Oynatma listesi",
        uploader=info.get("uploader") or info.get("channel") or "",
        entries=entries,
    )


def selection_filter(wanted_ids: set):
    """yt-dlp match_filter: liste taranıp indirilirken sıra kayarsa seçilmemiş video inmesin.

    Yalnızca liste aşamasında (tarama bilgisiyle, incomplete=True) bakılır. Tam çözülen videoda
    bakılmaz: bazı sitelerde oradaki kimlik taramadakinden farklıdır ve seçilen öğe atlanırdı.
    """
    def only_selected(entry, *, incomplete=False):
        if not incomplete:
            return None
        vid = entry.get("id")
        if vid is None or not wanted_ids or vid in wanted_ids:
            return None
        return "Seçilmedi"
    return only_selected


_WINDOWS_RESERVED ={"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(10)), *(f"LPT{i}" for i in range(10))}


def playlist_folder_name(title: str) -> str:
    """Uzak kaynaktan gelen liste adını güvenli bir klasör adına çevirir (yol ayırıcıları yt-dlp temizler)."""
    name = sanitize_filename(title or "Oynatma listesi").strip().rstrip(" .")
    name = name[:120].rstrip(" .") or "Oynatma listesi"
    if name.split(".")[0].strip().upper() in _WINDOWS_RESERVED:
        # Windows'ta CON, NUL, COM1... (uzantılı hâlleri de: NUL.txt) klasör adı olamaz; noktadan
        # önceki kısım değişmeli, bu yüzden başa ekle
        name = f"_{name}"
    return name


def build_args(opts: DownloadOptions, ffmpeg: str | None) -> list[str]:
    """Seçenekleri yt-dlp komut satırı argümanlarına çevirir."""
    args = ["--ignore-config", "--no-mtime", "-N", "4",
            "-P", opts.out_dir, "-o", with_unique_suffix(opts.template)]
    args.append("--yes-playlist" if opts.playlist else "--no-playlist")
    if ffmpeg:
        args += ["--ffmpeg-location", ffmpeg]
    if opts.proxy:
        args += ["--proxy", opts.proxy]

    if opts.kind == "audio":
        fmt = opts.audio_format
        args += ["-f", "ba/b", "-x", "--audio-format", fmt]
        if fmt == "m4a":
            args += ["-S", "acodec:aac"]
        elif fmt == "opus":
            args += ["-S", "acodec:opus"]
        if fmt in BITRATE_AUDIO:
            args += ["--audio-quality", f"{opts.audio_quality}K"]
        if opts.embed_thumbnail and fmt in THUMBNAIL_AUDIO:
            args.append("--embed-thumbnail")
        if opts.embed_metadata:
            args.append("--embed-metadata")
        return args

    container = opts.container
    sort = [f"res:{opts.quality}" if opts.quality else "res"]
    if container == "mp4" and opts.compat:
        sort += ["vcodec:h264", "acodec:aac"]
    elif container == "webm":
        sort += ["vcodec:vp9", "acodec:opus"]
    args += ["-f", "bv*+ba/b", "-S", ",".join(sort)]
    args += ["--merge-output-format", "webm/mkv" if container == "webm" else container]
    if container in ("mp4", "mkv"):
        args += ["--remux-video", container]
    if opts.embed_subs:
        args += ["--embed-subs", "--sub-langs", "tr.*,en.*,-live_chat"]
    if opts.embed_thumbnail and container != "webm":
        args.append("--embed-thumbnail")
    if opts.embed_metadata:
        args.append("--embed-metadata")
    return args


def build_ydl_opts(opts: DownloadOptions, ffmpeg: str | None) -> dict:
    parsed = yt_dlp.parse_options(build_args(opts, ffmpeg))
    ydl_opts = dict(parsed.ydl_opts)
    ydl_opts["js_runtimes"] = {k: dict(v) for k, v in JS_RUNTIMES.items()}
    ydl_opts["noprogress"] = True
    ydl_opts["ignoreerrors"] = "only_download"  # listede tek bir öğe hata verirse diğerlerine devam et
    return ydl_opts


def friendly_error(message: str) -> str:
    msg = message.replace("ERROR: ", "").strip()
    low = msg.lower()
    if "drm" in low:
        return "Bu içerik DRM ile korunuyor, indirilemez."
    if "sign in to confirm" in low and "bot" in low:
        return "YouTube bot doğrulaması istiyor. Hesaplar sekmesinden bir YouTube hesabı ekleyin."
    if any(k in low for k in ("login required", "log in", "sign in", "private", "cookies",
                              "authentication", "members-only", "members only", "age-restricted",
                              "confirm your age", "not authorized", "requires login")):
        return ("İçerik giriş gerektiriyor ya da bu hesapla erişilemiyor. Hesaplar sekmesinden bu "
                "platform için hesap ekleyin veya oturumu yenileyin.")
    if "unsupported url" in low:
        return "Bu link desteklenmiyor."
    if "http error 429" in low or "too many requests" in low or "rate-limit" in low:
        return "Site geçici olarak istek sınırı uyguladı. Biraz bekleyip tekrar deneyin."
    if "http error 404" in low or "not found" in low or "unavailable" in low:
        return "İçerik bulunamadı veya kaldırılmış."
    if "ffmpeg" in low and ("not found" in low or "not installed" in low):
        return "ffmpeg bulunamadı. Ayarlar sekmesinden ffmpeg yolunu kontrol edin."
    return msg.splitlines()[0][:300] if msg else "Bilinmeyen hata"


_PP_LABELS = [
    ("Merger", "Birleştiriliyor"),
    ("ExtractAudio", "Ses dönüştürülüyor"),
    ("VideoRemuxer", "Kapsayıcı ayarlanıyor"),
    ("EmbedSubtitle", "Altyazı ekleniyor"),
    ("Metadata", "Bilgiler ekleniyor"),
    ("EmbedThumbnail", "Kapak ekleniyor"),
    ("ThumbnailsConvertor", "Kapak hazırlanıyor"),
    ("MoveFiles", "Taşınıyor"),
]


@dataclass
class DownloadResult:
    files: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    cookiejar: object = None
    folder: str = ""          # oynatma listesi indirildiyse listenin klasörü
    playlist_title: str = ""


class _Logger:
    def __init__(self, on_log, errors):
        self.on_log = on_log
        self.errors = errors

    def debug(self, msg):
        if not msg.startswith("[debug] "):
            self.on_log("info", msg)

    def info(self, msg):
        self.on_log("info", msg)

    def warning(self, msg):
        self.on_log("warning", msg)

    def error(self, msg):
        self.errors.append(msg)
        self.on_log("error", msg)


def run_download(url: str, opts: DownloadOptions, ffmpeg: str | None, cookie_text: str | None,
                 on_update, on_log, cancel: threading.Event, choose=None) -> DownloadResult:
    """Tek bir linki veya oynatma listesini indirir.

    Önce link hızlıca taranır. Oynatma listesiyse choose(PlaylistInfo) çağrılır; seçilen sıra
    numaralarının listesini (veya iptal için None) döndürmelidir. Liste öğeleri, çıktı klasörü
    içinde liste adıyla açılan bir klasöre kaydedilir. Tek videoda bilgi yeniden çekilmeden indirilir.

    on_update(dict) alanları: status, percent (0-100 ya da None), speed, eta, title, item,
    index/count (listedeki sıra / seçilen öğe sayısı), playlist
    Hata durumunda DownloadError, iptalde DownloadCancelled fırlatır.
    """
    result = DownloadResult()
    state = {"title": ""}

    def item_label(info):
        idx = info.get("playlist_autonumber") or info.get("playlist_index")
        total = info.get("n_entries") or info.get("playlist_count")
        return f"{idx}/{total}" if idx and total else ""

    def item_fields(info):
        return {"index": info.get("playlist_autonumber"), "count": info.get("n_entries"),
                "playlist": info.get("playlist_title") or result.playlist_title}

    def progress_hook(d):
        if cancel.is_set():
            raise DownloadCancelled("Kullanıcı iptal etti")
        info = d.get("info_dict") or {}
        title = info.get("title") or state["title"]
        state["title"] = title
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            percent = done * 100 / total if total else None
            if percent is None and d.get("fragment_count"):
                percent = (d.get("fragment_index") or 0) * 100 / d["fragment_count"]
            kind = "ses" if info.get("vcodec") == "none" else ("video" if info.get("acodec") == "none" else "")
            on_update({
                "status": f"İndiriliyor ({kind})" if kind else "İndiriliyor",
                "percent": percent,
                "speed": (format_bytes(d.get("speed")) + "/s") if d.get("speed") else "",
                "eta": format_seconds(d.get("eta")),
                "title": title,
                "item": item_label(info),
                "size": format_bytes(total),
                "downloaded": format_bytes(done),
                **item_fields(info),
            })
        elif d["status"] == "finished":
            on_update({"status": "İndirildi, işleniyor", "percent": 100, "speed": "", "eta": "",
                       "title": title, "item": item_label(info), **item_fields(info)})

    def pp_hook(d):
        name = d.get("postprocessor", "")
        info = d.get("info_dict") or {}
        if d["status"] == "started":
            label = next((lbl for key, lbl in _PP_LABELS if key in name), "İşleniyor")
            on_update({"status": label, "percent": None, "speed": "", "eta": "",
                       "title": info.get("title") or state["title"], "item": item_label(info),
                       **item_fields(info)})
        elif d["status"] == "finished" and "MoveFiles" in name:
            path = info.get("filepath")
            if path and path not in result.files:
                result.files.append(path)

    ydl_opts = build_ydl_opts(opts, ffmpeg)
    ydl_opts["logger"] = _Logger(on_log, result.errors)
    ydl_opts["progress_hooks"] = [progress_hook]
    ydl_opts["postprocessor_hooks"] = [pp_hook]
    ydl_opts["extract_flat"] = "in_playlist"  # tarama: liste öğelerini tek tek açmadan listele
    if cookie_text is not None:
        ydl_opts["cookiefile"] = io.StringIO(cookie_text)  # çerezler diske düz metin yazılmaz

    on_update({"status": "Bilgi alınıyor", "percent": None, "speed": "", "eta": "", "title": "", "item": ""})
    ydl = yt_dlp.YoutubeDL(ydl_opts)
    namer = UniqueNamePP(ydl)
    ydl.add_post_processor(namer, when="video")
    try:
        with ydl:
            info = ydl.extract_info(url, download=False)
            if cancel.is_set():
                raise DownloadCancelled("Kullanıcı iptal etti")
            if not info:
                raise DownloadError(result.errors[-1] if result.errors else "Bilgi alınamadı")

            if info.get("_type") == "playlist":
                playlist = playlist_from_info(info)
                if not playlist.entries:
                    raise DownloadError("Oynatma listesi boş veya öğelere erişilemiyor")
                result.playlist_title = playlist.title
                on_update({"status": "Seçim bekleniyor", "percent": None, "speed": "", "eta": "",
                           "title": playlist.title, "item": "", "playlist": playlist.title})
                selected = choose(playlist) if choose else [e.index for e in playlist.entries]
                if cancel.is_set() or not selected:
                    raise DownloadCancelled("Seçim iptal edildi")
                chosen = set(selected)
                wanted_ids = {e.id for e in playlist.entries if e.index in chosen and e.id}
                result.folder = os.path.join(opts.out_dir, playlist_folder_name(playlist.title))
                ydl.params["extract_flat"] = False
                ydl.params["playlist_items"] = ",".join(str(i) for i in sorted(chosen))
                ydl.params["match_filter"] = selection_filter(wanted_ids)
                ydl.params["paths"] = {**(ydl.params.get("paths") or {}), "home": result.folder}
                ydl.download([url])
            else:
                # tek video: tarama sırasında alınan bilgiyle doğrudan indir (ikinci kez çekmeden).
                # Çok videolu gönderilerde (galeri vb.) öğeler taramada açılmamış olabilir.
                ydl.params["extract_flat"] = False
                ydl.process_ie_result(info, download=True)
    finally:
        namer.release()
        if cookie_text is not None:
            result.cookiejar = ydl.cookiejar
    if not result.files:
        raise DownloadError(result.errors[-1] if result.errors else "İndirme başarısız")
    return result
