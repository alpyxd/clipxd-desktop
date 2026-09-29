"""Arayüzsüz öz test: paketlenmiş sürümün (exe) indirme motorunun çalıştığını doğrular.

Kullanım:  ClipXD.exe --self-test rapor.json [--url LINK --out KLASÖR]
Rapor JSON olarak yazılır; çıkış kodu 0 = başarılı, 1 = sorun var. Pencereli exe'nin
konsolu olmadığı için sonuç dosyaya yazılır.
"""
import json
import sys
import threading
import traceback


def _arg(argv: list, name: str) -> str | None:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def run(argv: list) -> int:
    report_path = _arg(argv, "--self-test")
    url, out_dir = _arg(argv, "--url"), _arg(argv, "--out")
    report = {"ok": False, "checks": {}}
    checks = report["checks"]
    try:
        from clipxd import __version__
        from clipxd.ffmpeg_tools import ffmpeg_version, find_ffmpeg
        import yt_dlp.version
        import yt_dlp_ejs  # noqa: F401  (YouTube JS çözücü betikleri)
        from clipxd.sites import supported_sites

        checks["version"] = __version__
        checks["frozen"] = bool(getattr(sys, "frozen", False))
        ffmpeg = find_ffmpeg()
        checks["ffmpeg"] = ffmpeg_version(ffmpeg) if ffmpeg else None
        checks["yt_dlp"] = yt_dlp.version.__version__
        checks["yt_dlp_ejs"] = True
        checks["sites"] = len(supported_sites())
        ok = bool(ffmpeg) and checks["sites"] > 500

        if url and out_dir:
            from clipxd.downloader import DownloadOptions, run_download
            logs = []
            result = run_download(url, DownloadOptions(quality=240, out_dir=out_dir, embed_thumbnail=False),
                                  ffmpeg, None, lambda d: None, lambda lvl, msg: logs.append(f"{lvl}: {msg}"),
                                  threading.Event())
            checks["download_files"] = result.files
            checks["download_warnings"] = [line for line in logs if line.startswith(("warning", "error"))][-5:]
            ok = ok and bool(result.files)
        report["ok"] = ok
    except Exception:
        report["error"] = traceback.format_exc()
    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    return 0 if report["ok"] else 1
