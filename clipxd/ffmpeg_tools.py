import os
import re
import shutil
import subprocess
from pathlib import Path

NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def find_ffmpeg(custom: str = "") -> str | None:
    """Sıra: ayarlardaki yol -> PATH -> imageio-ffmpeg ile gelen gömülü ffmpeg."""
    if custom:
        p = Path(custom)
        if p.is_dir():
            p = p / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        if p.is_file():
            return str(p)
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def ffmpeg_version(ffmpeg: str) -> str:
    try:
        out = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, timeout=10,
                             creationflags=NO_WINDOW).stdout
        m = re.match(r"ffmpeg version (\S+)", out)
        return m.group(1) if m else "?"
    except (OSError, subprocess.SubprocessError):
        return "?"


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def probe_duration(ffmpeg: str, path: str) -> float | None:
    """Süreyi saniye olarak döndürür (ffprobe gerektirmez)."""
    try:
        proc = subprocess.run([ffmpeg, "-hide_banner", "-i", path], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    m = _DURATION_RE.search(proc.stderr)
    if not m:
        return None
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)


_TIME_RE = re.compile(r"^(?:(\d{1,3}):)?(?:(\d{1,2}):)?(\d+(?:\.\d+)?)$")


def parse_time(text: str) -> float | None:
    """'90', '1:30', '00:01:30.5' -> saniye. Boş/None -> None. Geçersizse ValueError.

    Yalnızca rakamlar kabul edilir ('nan', 'inf', '1e3', negatif değerler reddedilir).
    """
    text = (text or "").strip().replace(",", ".")
    if not text:
        return None
    m = _TIME_RE.match(text)
    if not m:
        raise ValueError(f"Geçersiz zaman: {text} (örnek: 90, 1:30 veya 0:01:30)")
    a, b, sec = m.groups()
    parts = [p for p in (a, b) if p is not None]
    total = 0.0
    for part in parts:
        total = total * 60 + int(part)
    return total * 60 + float(sec) if parts else float(sec)


def format_seconds(sec: float | None) -> str:
    if sec is None or sec < 0:
        return ""
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def format_bytes(n: float | None) -> str:
    if not n:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
