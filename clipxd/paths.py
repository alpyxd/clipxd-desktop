import os
import shutil
from pathlib import Path

from clipxd import APP_NAME, LEGACY_APP_NAME


def _config_root() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def _app_folder(name: str) -> Path:
    return _config_root() / (name if os.name == "nt" else name.lower())


def _migrate_legacy(new: Path):
    """Eski adla (MedyaKit) oluşturulmuş veri klasörünü bir kez yeni ada taşır."""
    old = _app_folder(LEGACY_APP_NAME)
    if new.exists() or not old.is_dir():
        return
    try:
        old.rename(new)  # aynı sürücüde anlık; şifreli dosyalar olduğu gibi taşınır
    except OSError:
        try:
            shutil.copytree(old, new)  # eski uygulama açıksa dosyalar kilitli olabilir: kopyala
        except OSError:
            pass


def data_dir() -> Path:
    """Ayarların ve şifreli hesap verilerinin tutulduğu klasör."""
    override = os.environ.get("CLIPXD_DATA_DIR")
    if override:
        base = Path(override)
    else:
        base = _app_folder(APP_NAME)
        _migrate_legacy(base)
    base.mkdir(parents=True, exist_ok=True)
    return base


def default_download_dir() -> Path:
    return Path.home() / "Downloads" / APP_NAME


def legacy_download_dir() -> Path:
    return Path.home() / "Downloads" / LEGACY_APP_NAME


def unique_path(path: Path) -> Path:
    """Dosya varsa sonuna ' (1)', ' (2)' ... ekler."""
    if not path.exists():
        return path
    i = 1
    while True:
        candidate = path.with_name(f"{path.stem} ({i}){path.suffix}")
        if not candidate.exists():
            return candidate
        i += 1
