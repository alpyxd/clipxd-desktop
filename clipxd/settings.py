import copy
import json
import threading
from pathlib import Path

from clipxd import secure_store
from clipxd.paths import data_dir, default_download_dir, legacy_download_dir

DEFAULT_TEMPLATE = "%(title).150B.%(ext)s"
OLD_DEFAULT_TEMPLATES = {"%(title).150B [%(id)s].%(ext)s"}  # eski sürümlerin varsayılanı (sonunda [kimlik])

DEFAULTS = {
    "download_dir": str(default_download_dir()),
    "filename_template": DEFAULT_TEMPLATE,
    "max_concurrent": 2,
    "ffmpeg_path": "",
    "proxy": "",          # yalnızca eski sürümden taşımak için; değer proxy.bin'de şifreli tutulur
    "theme": "system",
    "download": {
        "kind": "video",
        "container": "mp4",
        "quality": 0,
        "compat": True,
        "audio_format": "mp3",
        "audio_quality": 320,
        "embed_thumbnail": True,
        "embed_metadata": True,
        "embed_subs": False,
        "playlist": False,
    },
    "convert": {
        "mode": "encode",
        "target": "mp4",
        "video_codec": "h264",
        "quality": "high",
        "resolution": 0,
        "fps": 0,
        "audio_bitrate": 192,
        "speed": "medium",
        "out_dir": "",
    },
}


def _same_kind(default, value) -> bool:
    if isinstance(default, bool) or isinstance(value, bool):
        return isinstance(default, bool) and isinstance(value, bool)
    if isinstance(default, int):
        return isinstance(value, int)
    return isinstance(value, type(default))


def _merge(defaults: dict, loaded: dict) -> dict:
    """Varsayılanların üzerine yüklenen değerleri koyar; türü uymayan değerler yok sayılır
    (elle bozulmuş bir ayar dosyası uygulamayı açılışta çökertmesin)."""
    out = copy.deepcopy(defaults)
    if not isinstance(loaded, dict):
        return out
    for key, value in loaded.items():
        if key not in out:
            continue
        if isinstance(out[key], dict):
            if isinstance(value, dict):
                out[key] = _merge(out[key], value)
        elif _same_kind(out[key], value):
            out[key] = value
    return out


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / "settings.json"
        self._lock = threading.Lock()
        self.data = copy.deepcopy(DEFAULTS)
        if self.path.exists():
            try:
                self.data = _merge(DEFAULTS, json.loads(self.path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass  # bozuk ayar dosyası: varsayılanlarla devam et
        if self.data.get("filename_template") in OLD_DEFAULT_TEMPLATES:
            self.data["filename_template"] = DEFAULT_TEMPLATE
        if self.data.get("download_dir") == str(legacy_download_dir()):
            # eski adın varsayılan klasörü (İndirilenler\MedyaKit) -> İndirilenler\ClipXD
            self.data["download_dir"] = str(default_download_dir())
        if not 1 <= self.data["max_concurrent"] <= 6:
            self.data["max_concurrent"] = DEFAULTS["max_concurrent"]
        # Proxy (kullanıcı adı/şifre içerebilir) artık şifreli dosyada; eski düz metin değeri taşı
        legacy_proxy = self.data.pop("proxy", "")
        if legacy_proxy and not self.proxy:
            self.proxy = legacy_proxy
            self.save()

    @property
    def _proxy_path(self) -> Path:
        return self.path.with_name("proxy.bin")

    @property
    def proxy(self) -> str:
        try:
            return secure_store.read_secret(self._proxy_path) if self._proxy_path.exists() else ""
        except (OSError, ValueError):
            return ""

    @proxy.setter
    def proxy(self, value: str):
        value = (value or "").strip()
        if value:
            secure_store.write_secret(self._proxy_path, value)
        else:
            self._proxy_path.unlink(missing_ok=True)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def save(self):
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
