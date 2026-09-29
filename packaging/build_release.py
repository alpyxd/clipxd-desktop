"""ClipXD Desktop Windows sürüm paketi.

Adımlar: simge + sürüm bilgisi -> PyInstaller -> gereksiz dil paketlerini temizle ->
üçüncü taraf lisanslarını ekle -> zip + SHA-256.

Kullanım:  .venv\\Scripts\\python.exe packaging\\build_release.py
Çıktı:     dist\\ClipXD-Desktop-<sürüm>-win64.zip (+ .sha256)
"""
import hashlib
import importlib.metadata as md
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from clipxd import APP_FULL_NAME, APP_NAME, __version__  # noqa: E402

DIST = ROOT / "dist"
BUILD = ROOT / "build"
APP_DIR = DIST / APP_NAME
THIRD_PARTY = ROOT / "packaging" / "third_party"
ZIP_PATH = DIST / f"ClipXD-Desktop-{__version__}-win64.zip"

# Pakete giren (çalışma zamanında kullanılan) Python dağıtımları
RUNTIME_PACKAGES = [
    "PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6", "yt-dlp", "yt-dlp-ejs", "imageio-ffmpeg",
    "mutagen", "pycryptodomex", "brotli", "certifi", "websockets", "requests", "urllib3", "idna",
    "charset-normalizer",
]
# Qt WebEngine (giriş penceresi) için yalnızca İngilizce ve Türkçe arayüz dosyaları tutulur
KEEP_LOCALES = {"en-US.pak", "tr.pak"}


def run(cmd, **kw):
    print(">", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT, **kw)


def version_file() -> Path:
    parts = [int(p) for p in __version__.split(".")] + [0] * 4
    v = tuple(parts[:4])
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{APP_NAME}'),
      StringStruct('FileDescription', '{APP_FULL_NAME}'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', '{APP_NAME}'),
      StringStruct('LegalCopyright', 'Copyright (c) 2026 Alpay. MIT License.'),
      StringStruct('OriginalFilename', '{APP_NAME}.exe'),
      StringStruct('ProductName', '{APP_FULL_NAME}'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    BUILD.mkdir(exist_ok=True)
    path = BUILD / "version_info.txt"
    path.write_text(text, encoding="utf-8")
    return path


def build():
    run([sys.executable, "-c", "from clipxd.app import write_icon; write_icon('assets/icon.ico')"])
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--log-level", "WARN",
         "--name", APP_NAME, "--icon", "assets/icon.ico", "--version-file", str(version_file()),
         "--collect-data", "imageio_ffmpeg", "--collect-all", "yt_dlp_ejs", "ClipXD.pyw"])


def prune():
    saved = 0
    for pak in APP_DIR.rglob("qtwebengine_locales/*.pak"):
        if pak.name not in KEEP_LOCALES:
            saved += pak.stat().st_size
            pak.unlink()
    print(f"dil paketleri temizlendi: {saved / 2**20:.1f} MB")


def _license_files(dist) -> list[Path]:
    out = []
    for f in dist.files or []:
        name = str(f).upper()
        if any(k in name for k in ("LICENSE", "COPYING", "NOTICE", "AUTHORS")) and not name.endswith(".PY"):
            out.append(Path(dist.locate_file(f)))
    return out


def licenses():
    lic = APP_DIR / "licenses"
    if lic.exists():
        shutil.rmtree(lic)
    lic.mkdir()
    rows = []
    for name in RUNTIME_PACKAGES:
        dist = md.distribution(name)
        target = lic / dist.metadata["Name"]
        target.mkdir(exist_ok=True)
        for f in _license_files(dist):
            shutil.copy2(f, target / f.name)
        expr = dist.metadata.get("License-Expression") or dist.metadata.get("License") or "-"
        rows.append((dist.metadata["Name"], dist.version, expr.splitlines()[0][:60],
                     f"https://pypi.org/project/{dist.metadata['Name']}/{dist.version}/"))

    # Qt / PySide6: LGPL-3.0 (pip paketinde metin yok)
    shutil.copy2(THIRD_PARTY / "LGPL-3.0.txt", lic / "PySide6" / "LGPL-3.0.txt")
    shutil.copy2(THIRD_PARTY / "GPL-3.0.txt", lic / "PySide6" / "GPL-3.0.txt")

    # Python çalışma zamanı
    (lic / "Python").mkdir()
    for f in Path(sys.base_prefix).glob("LICENSE*"):
        shutil.copy2(f, lic / "Python" / f.name)
    rows.append(("Python", sys.version.split()[0], "PSF-2.0", "https://www.python.org/downloads/source/"))

    # ffmpeg (imageio-ffmpeg ile gelen gyan.dev yapısı): GPL-3.0
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    info = subprocess.run([ffmpeg, "-hide_banner", "-version"], capture_output=True, text=True).stdout
    ff_version = info.split()[2] if info.startswith("ffmpeg version") else "?"
    (lic / "ffmpeg").mkdir()
    shutil.copy2(THIRD_PARTY / "GPL-3.0.txt", lic / "ffmpeg" / "GPL-3.0.txt")
    (lic / "ffmpeg" / "README.txt").write_text(
        "Bu pakette bulunan ffmpeg ikili dosyasi GNU GPL surum 3 (veya sonrasi) ile lisanslidir.\n"
        "The ffmpeg binary in this package is licensed under the GNU GPL version 3 (or later).\n\n"
        "Kaynak kodu / Source code:\n"
        "  FFmpeg: https://ffmpeg.org/download.html  (git: https://git.ffmpeg.org/ffmpeg.git)\n"
        "  Bu yapi / This build: https://www.gyan.dev/ffmpeg/builds/ (imageio-ffmpeg araciligiyla)\n\n"
        f"Surum ve derleme ayarlari / Version and build configuration:\n\n{info}",
        encoding="utf-8")
    rows.append(("FFmpeg", ff_version, "GPL-3.0-or-later", "https://ffmpeg.org/download.html"))

    shutil.copy2(ROOT / "LICENSE", APP_DIR / "LICENSE.txt")
    width = max(len(r[0]) for r in rows)
    table = "\n".join(f"  {n:<{width}}  {v:<14} {lic_:<48} {src}" for n, v, lic_, src in rows)
    (APP_DIR / "THIRD-PARTY-NOTICES.txt").write_text(
        f"{APP_FULL_NAME} {__version__}\n"
        "ClipXD kaynak kodu MIT lisanslidir (LICENSE.txt): https://github.com/alpyxd/clipxd-desktop\n"
        "ClipXD source code is MIT licensed (LICENSE.txt).\n\n"
        "Bu paket asagidaki ucuncu taraf bilesenlerini icerir; lisans metinleri 'licenses' klasorundedir.\n"
        "This package bundles the following third-party components; license texts are in 'licenses'.\n"
        "GPL/LGPL bilesenlerin kaynak kodu asagidaki adreslerden edinilebilir.\n"
        "Source code for GPL/LGPL components is available at the addresses below.\n\n"
        f"{table}\n\n"
        "Qt / Qt WebEngine (Chromium) bilesen lisanslari: https://doc.qt.io/qt-6/licenses-used-in-qt.html\n"
        "PySide6/Qt kutuphaneleri ayri DLL dosyalari olarak gelir ve LGPL-3.0 geregi degistirilebilir.\n"
        "PySide6/Qt libraries ship as separate DLLs and may be replaced as permitted by the LGPL-3.0.\n",
        encoding="utf-8")
    print(f"lisanslar eklendi: {len(rows)} bileşen")


def make_zip() -> str:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(APP_DIR.rglob("*")):
            if f.is_file():
                z.write(f, Path(APP_NAME) / f.relative_to(APP_DIR))
    digest = hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest()
    ZIP_PATH.with_name(ZIP_PATH.name + ".sha256").write_text(f"{digest}  {ZIP_PATH.name}\n", encoding="utf-8")
    print(f"{ZIP_PATH.name}: {ZIP_PATH.stat().st_size / 2**20:.1f} MB, sha256 {digest}")
    return digest


if __name__ == "__main__":
    build()
    prune()
    licenses()
    make_zip()
