"""ffmpeg ile yerel dosya dönüştürme: kapsayıcı değiştirme (kayıpsız) ve yeniden kodlama."""
import subprocess
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from clipxd.ffmpeg_tools import NO_WINDOW, parse_time
from clipxd.paths import unique_path

VIDEO_TARGETS = {
    "mp4": "MP4",
    "mkv": "MKV",
    "webm": "WEBM",
    "mov": "MOV",
    "avi": "AVI",
    "gif": "GIF (animasyon)",
}
AUDIO_TARGETS = {
    "mp3": "MP3",
    "m4a": "M4A (AAC)",
    "opus": "OPUS",
    "ogg": "OGG (Vorbis)",
    "flac": "FLAC (kayıpsız)",
    "wav": "WAV (sıkıştırmasız)",
}
LOSSLESS_AUDIO = {"flac", "wav"}

VIDEO_CODECS = {"h264": "H.264 (en uyumlu)", "h265": "H.265 / HEVC (daha küçük)", "vp9": "VP9"}

# anahtar: (etiket, x264 crf, x265 crf, vp9 crf, mpeg4 q)
QUALITY_PRESETS = {
    "lossless": ("Kayıpsıza yakın", 16, 20, 24, 2),
    "high": ("Yüksek", 19, 23, 30, 3),
    "balanced": ("Dengeli", 23, 27, 34, 5),
    "small": ("Küçük dosya", 27, 31, 40, 8),
    "tiny": ("Çok küçük dosya", 31, 35, 46, 12),
}
# anahtar: (etiket, x264/x265 preset, vp9 cpu-used)
SPEED_PRESETS = {
    "fast": ("Hızlı", "veryfast", 5),
    "medium": ("Normal", "medium", 3),
    "slow": ("Yavaş (daha verimli)", "slow", 1),
}
RESOLUTIONS = [0, 2160, 1440, 1080, 720, 480, 360, 240]
FPS_CHOICES = [0, 60, 30, 24, 15]
AUDIO_BITRATES = [320, 256, 192, 160, 128, 96, 64]

# Kopyalama modunda kapsayıcıya göre seçilecek akışlar
_COPY_MAPS = {
    "mkv": ["-map", "0"],
    "mp4": ["-map", "0:v?", "-map", "0:a?"],
    "mov": ["-map", "0:v?", "-map", "0:a?"],
    "webm": ["-map", "0:v?", "-map", "0:a?"],
    "avi": ["-map", "0:v?", "-map", "0:a?"],
}


@dataclass
class ConvertOptions:
    mode: str = "encode"          # "copy" = sadece kapsayıcı değiştir, "encode" = yeniden kodla
    target: str = "mp4"
    video_codec: str = "h264"
    quality: str = "high"
    resolution: int = 0           # 0 = orijinal, aksi halde maksimum yükseklik
    fps: int = 0                  # 0 = orijinal
    audio_bitrate: int = 192
    speed: str = "medium"
    start: str = ""               # kırpma başlangıcı (boş = baştan)
    end: str = ""                 # kırpma bitişi (boş = sona kadar)
    out_dir: str = ""             # boş = kaynak dosyanın klasörü

    @property
    def is_audio(self) -> bool:
        return self.target in AUDIO_TARGETS

    def effective_mode(self) -> str:
        return "encode" if self.target == "gif" else self.mode


def output_path(src: Path, opts: ConvertOptions) -> Path:
    folder = Path(opts.out_dir) if opts.out_dir else src.parent
    ext = "opus" if opts.target == "opus" else opts.target
    dst = folder / f"{src.stem}.{ext}"
    if dst.resolve() == src.resolve():
        dst = folder / f"{src.stem}_donusturuldu.{ext}"
    return unique_path(dst)


def trim_window(opts: ConvertOptions) -> tuple[float | None, float | None]:
    """(başlangıç, süre) saniye cinsinden. Geçersizse ValueError."""
    start = parse_time(opts.start)
    end = parse_time(opts.end)
    if end is not None and end <= (start or 0):
        raise ValueError("Bitiş zamanı başlangıçtan sonra olmalı")
    duration = end - (start or 0) if end is not None else None
    return start, duration


def _video_filters(opts: ConvertOptions) -> list[str]:
    filters = []
    if opts.fps:
        filters.append(f"fps={opts.fps}")
    if opts.resolution:
        filters.append(f"scale=-2:'min({opts.resolution},ih)'")
    return filters


def _audio_codec_args(target: str, bitrate: int) -> list[str]:
    if target in ("mp3", "avi"):
        return ["-c:a", "libmp3lame", "-b:a", f"{bitrate}k"]
    if target in ("m4a", "mp4", "mov", "mkv"):
        return ["-c:a", "aac", "-b:a", f"{bitrate}k"]
    if target in ("opus", "webm"):
        return ["-c:a", "libopus", "-b:a", f"{bitrate}k"]
    if target == "ogg":
        return ["-c:a", "libvorbis", "-b:a", f"{bitrate}k"]
    if target == "flac":
        return ["-c:a", "flac"]
    if target == "wav":
        return ["-c:a", "pcm_s16le"]
    raise ValueError(f"Bilinmeyen hedef: {target}")


def _video_codec_args(opts: ConvertOptions) -> list[str]:
    _, crf264, crf265, crf_vp9, q_mpeg4 = QUALITY_PRESETS[opts.quality]
    _, x_preset, vp9_cpu = SPEED_PRESETS[opts.speed]
    codec = opts.video_codec
    if opts.target == "webm":
        codec = "vp9"
    elif opts.target == "mov" and codec == "vp9":
        codec = "h264"
    if opts.target == "avi":
        return ["-c:v", "mpeg4", "-q:v", str(q_mpeg4), "-pix_fmt", "yuv420p"]
    if codec == "h265":
        args = ["-c:v", "libx265", "-crf", str(crf265), "-preset", x_preset, "-pix_fmt", "yuv420p"]
        if opts.target in ("mp4", "mov"):
            args += ["-tag:v", "hvc1"]  # Apple/QuickTime uyumluluğu
        return args
    if codec == "vp9":
        return ["-c:v", "libvpx-vp9", "-crf", str(crf_vp9), "-b:v", "0", "-row-mt", "1",
                "-deadline", "good", "-cpu-used", str(vp9_cpu), "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-crf", str(crf264), "-preset", x_preset, "-pix_fmt", "yuv420p"]


def build_command(ffmpeg: str, src: Path, dst: Path, opts: ConvertOptions) -> list[str]:
    start, duration = trim_window(opts)
    cmd = [ffmpeg, "-hide_banner", "-nostdin", "-y"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(src)]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]

    target = opts.target
    mode = opts.effective_mode()

    if target == "gif":
        height = opts.resolution or 480
        fps = opts.fps or 12
        graph = (f"fps={fps},scale=-2:'min({height},ih)':flags=lanczos,split[a][b];"
                 f"[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5")
        cmd += ["-vf", graph, "-an", "-loop", "0"]
    elif opts.is_audio:
        cmd += ["-map", "0:a:0", "-vn", "-sn", "-dn"]
        if mode == "copy":
            cmd += ["-c:a", "copy"]
        else:
            cmd += _audio_codec_args(target, opts.audio_bitrate)
        if target == "m4a":
            cmd += ["-movflags", "+faststart"]
    elif mode == "copy":
        cmd += _COPY_MAPS.get(target, ["-map", "0"]) + ["-c", "copy"]
        if target in ("mp4", "mov"):
            cmd += ["-movflags", "+faststart"]
    else:
        cmd += ["-map", "0:v:0", "-map", "0:a?"]
        if target == "mkv":
            cmd += ["-map", "0:s?", "-c:s", "copy"]
        cmd += _video_codec_args(opts)
        filters = _video_filters(opts)
        if filters:
            cmd += ["-vf", ",".join(filters)]
        cmd += _audio_codec_args(target, opts.audio_bitrate)
        if target in ("mp4", "mov"):
            cmd += ["-movflags", "+faststart"]

    cmd += ["-progress", "pipe:1", "-nostats", str(dst)]
    return cmd


class ConversionError(Exception):
    pass


class Cancelled(Exception):
    pass


def explain_ffmpeg_error(lines: list[str], opts: ConvertOptions) -> str:
    text = "\n".join(lines)
    low = text.lower()
    if opts.effective_mode() == "copy" and ("could not find tag for codec" in low
                                            or "not supported" in low
                                            or "invalid argument" in low
                                            or "codec not currently supported" in low):
        return ("Kaynaktaki codec bu kapsayıcıya kopyalanamıyor. "
                "'Yeniden kodla' modunu seçip tekrar deneyin.")
    if "matches no streams" in low or "does not contain any stream" in low:
        return "Dosyada istenen türde akış yok (örn. ses çıkarmak için ses izi bulunamadı)."
    if "no such file" in low:
        return "Kaynak dosya bulunamadı."
    tail = [l for l in lines if l.strip()][-4:]
    return "ffmpeg hatası:\n" + "\n".join(tail)


def run_ffmpeg(cmd: list[str], duration: float | None, on_progress, cancel: threading.Event) -> None:
    """ffmpeg'i çalıştırır; on_progress(oran 0..1 veya None, hız_çarpanı) çağırır."""
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                            text=True, encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    stderr_tail = deque(maxlen=40)

    def drain():
        for line in proc.stderr:
            stderr_tail.append(line.rstrip())

    t = threading.Thread(target=drain, daemon=True)
    t.start()

    def watch_cancel():
        # ffmpeg ilerleme yazmasa bile (ör. takılan girdi) iptal hemen etkili olsun
        while proc.poll() is None:
            if cancel.wait(0.2):
                proc.kill()
                return

    threading.Thread(target=watch_cancel, daemon=True).start()

    out_time = 0.0
    speed = ""
    try:
        for line in proc.stdout:
            if cancel.is_set():
                proc.kill()
                break
            key, _, value = line.strip().partition("=")
            if key in ("out_time_us", "out_time_ms"):  # ikisi de mikrosaniye cinsinden
                try:
                    out_time = int(value) / 1_000_000
                except ValueError:
                    pass
            elif key == "speed":
                speed = value.strip()
            elif key == "progress":
                if value == "end":
                    ratio = 1.0
                else:
                    ratio = min(out_time / duration, 1.0) if duration else None
                on_progress(ratio, speed)
        proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        t.join(timeout=2)
        proc.stdout.close()
        proc.stderr.close()

    if cancel.is_set():
        raise Cancelled()
    if proc.returncode != 0:
        raise ConversionError(list(stderr_tail))
