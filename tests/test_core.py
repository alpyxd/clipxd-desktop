import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from clipxd import accounts, converter, downloader, ffmpeg_tools, secure_store


class SecureStoreTest(unittest.TestCase):
    def test_roundtrip_and_not_plaintext(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.bin"
            secret = "sessionid\tGIZLI-DEGER-123 ğüşiöç"
            secure_store.write_secret(p, secret)
            self.assertEqual(secure_store.read_secret(p), secret)
            if secure_store.ENCRYPTED:
                self.assertNotIn(b"GIZLI-DEGER-123", p.read_bytes())


class AccountsTest(unittest.TestCase):
    def _jar(self):
        jar = accounts.new_jar()
        jar.set_cookie(accounts.make_cookie(".instagram.com", "sessionid", "abc", expires=4102444800,
                                            http_only=True))
        jar.set_cookie(accounts.make_cookie(".instagram.com", "csrftoken", "tok", expires=4102444800))
        jar.set_cookie(accounts.make_cookie(".google.com", "SID", "nope", expires=4102444800))
        return jar

    def test_filter_and_text_roundtrip(self):
        filtered = accounts.filter_jar(self._jar(), ["instagram.com"])
        self.assertEqual(sorted(c.name for c in filtered), ["csrftoken", "sessionid"])
        again = accounts.text_to_jar(accounts.jar_to_text(filtered))
        self.assertEqual(sorted(c.name for c in again), ["csrftoken", "sessionid"])

    def test_host_matching(self):
        self.assertTrue(accounts.host_matches("www.instagram.com", ["instagram.com"]))
        self.assertTrue(accounts.host_matches(".instagram.com", ["instagram.com"]))
        self.assertFalse(accounts.host_matches("notinstagram.com", ["instagram.com"]))
        self.assertTrue(accounts.host_matches("music.youtube.com", ["youtube.com"]))

    def test_store(self):
        with tempfile.TemporaryDirectory() as d:
            store = accounts.AccountStore(Path(d))
            jar = accounts.filter_jar(self._jar(), ["instagram.com"])
            a1 = store.add("Ana", "instagram", ["instagram.com"], jar, "test")
            a2 = store.add("Yedek", "instagram", ["instagram.com"], jar, "test")
            self.assertTrue(a1.default)
            self.assertFalse(a2.default)
            self.assertEqual(store.find_for_url("https://www.instagram.com/p/xyz/").id, a1.id)
            store.set_default(a2.id)
            self.assertEqual(store.find_for_url("https://instagram.com/reel/1").id, a2.id)
            self.assertIsNone(store.find_for_url("https://tiktok.com/@a/video/1"))
            ok, _ = store.status(store.get(a1.id))
            self.assertTrue(ok)
            # yeniden yükleme
            store2 = accounts.AccountStore(Path(d))
            self.assertEqual(len(store2.all()), 2)
            self.assertEqual(len(store2.load_jar(a1.id)), 2)
            store2.remove(a1.id)
            self.assertFalse((Path(d) / "cookies" / f"{a1.id}.bin").exists())

    def test_cookies_txt_import(self):
        content = ("# Netscape HTTP Cookie File\n"
                   "#HttpOnly_.tiktok.com\tTRUE\t/\tTRUE\t4102444800\tsessionid\tS1\n"
                   ".tiktok.com\tTRUE\t/\tFALSE\t0\ttt_webid\tW1\n"
                   ".google.com\tTRUE\t/\tTRUE\t4102444800\tSID\tX\n")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "cookies.txt"
            p.write_text(content, encoding="utf-8")
            jar = accounts.jar_from_file(str(p), ["tiktok.com"])
        self.assertEqual(sorted(c.name for c in jar), ["sessionid", "tt_webid"])
        ok, _ = accounts.auth_cookie_status(jar, accounts.PLATFORM_BY_KEY["tiktok"])
        self.assertTrue(ok)

    def test_auth_status_missing(self):
        jar = accounts.new_jar()
        jar.set_cookie(accounts.make_cookie(".instagram.com", "csrftoken", "tok"))
        ok, _ = accounts.auth_cookie_status(jar, accounts.PLATFORM_BY_KEY["instagram"])
        self.assertFalse(ok)


class DownloaderArgsTest(unittest.TestCase):
    def test_video_mp4_1080_compat(self):
        o = downloader.build_ydl_opts(downloader.DownloadOptions(quality=1080, out_dir="C:/tmp"), "ffmpeg")
        self.assertEqual(o["format"], "bv*+ba/b")
        self.assertEqual(o["format_sort"], ["res:1080", "vcodec:h264", "acodec:aac"])
        self.assertEqual(o["merge_output_format"], "mp4")
        self.assertTrue(o["noplaylist"])
        keys = [pp["key"] for pp in o["postprocessors"]]
        self.assertIn("FFmpegVideoRemuxer", keys)
        self.assertIn("EmbedThumbnail", keys)

    def test_webm_no_thumbnail(self):
        o = downloader.build_ydl_opts(downloader.DownloadOptions(container="webm"), None)
        self.assertEqual(o["merge_output_format"], "webm/mkv")
        self.assertNotIn("EmbedThumbnail", [pp["key"] for pp in o["postprocessors"]])

    def test_audio_mp3(self):
        o = downloader.build_ydl_opts(downloader.DownloadOptions(kind="audio", audio_quality=192), None)
        pp = next(p for p in o["postprocessors"] if p["key"] == "FFmpegExtractAudio")
        self.assertEqual(pp["preferredcodec"], "mp3")
        self.assertEqual(pp["preferredquality"], "192")

    def test_audio_best_keeps_original(self):
        o = downloader.build_ydl_opts(downloader.DownloadOptions(kind="audio", audio_format="best"), None)
        pp = next(p for p in o["postprocessors"] if p["key"] == "FFmpegExtractAudio")
        self.assertEqual(pp["preferredcodec"], "best")

    def test_template_has_no_id_and_gets_unique_suffix(self):
        o = downloader.build_ydl_opts(downloader.DownloadOptions(), None)
        tmpl = o["outtmpl"]["default"]
        self.assertNotIn("%(id)s", tmpl)
        self.assertTrue(tmpl.endswith("%(mk_suffix|)s.%(ext)s"))
        self.assertEqual(downloader.with_unique_suffix("%(uploader)s/%(title)s.%(ext)s"),
                         "%(uploader)s/%(title)s%(mk_suffix|)s.%(ext)s")
        self.assertEqual(o["ignoreerrors"], "only_download")

    def test_old_template_migrated(self):
        import json
        from clipxd.settings import DEFAULT_TEMPLATE, Settings
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "settings.json"
            p.write_text(json.dumps({"filename_template": "%(title).150B [%(id)s].%(ext)s"}), encoding="utf-8")
            self.assertEqual(Settings(p)["filename_template"], DEFAULT_TEMPLATE)
            p.write_text(json.dumps({"filename_template": "%(uploader)s - %(title)s.%(ext)s"}), encoding="utf-8")
            self.assertEqual(Settings(p)["filename_template"], "%(uploader)s - %(title)s.%(ext)s")

    def test_playlist_folder_name(self):
        name = downloader.playlist_folder_name('Rock: En İyiler / 2024? "Canlı" ...')
        for ch in '<>:"/\\|?*':
            self.assertNotIn(ch, name)
        self.assertFalse(name.endswith((".", " ")))
        self.assertEqual(downloader.playlist_folder_name(""), "Oynatma listesi")

    def test_playlist_from_flat_info(self):
        info = {"title": "Liste", "uploader": "Kanal", "entries": [
            {"id": "a", "title": "Bir", "duration": 60, "url": "u1"}, None,
            {"id": "c", "title": None, "url": "u3"}]}
        pl = downloader.playlist_from_info(info)
        self.assertEqual([(e.index, e.id) for e in pl.entries], [(1, "a"), (3, "c")])
        self.assertEqual(pl.entries[1].title, "u3")
        self.assertEqual(pl.total_duration, 60)

    def test_friendly_error(self):
        self.assertIn("giriş", downloader.friendly_error("ERROR: [Instagram] x: login required"))
        self.assertIn("DRM", downloader.friendly_error("ERROR: This video is DRM protected"))


class SupportedSitesTest(unittest.TestCase):
    def test_popular_present_adult_hidden(self):
        from clipxd.sites import supported_sites
        names = [n for n, _ in supported_sites()]
        self.assertGreater(len(names), 500)
        for expected in ("YouTube", "Instagram", "TikTok", "X (Twitter)", "Reddit", "Facebook", "Vimeo"):
            self.assertIn(expected, names)
        self.assertFalse([n for n in names if "porn" in n.lower()])
        self.assertEqual(names, sorted(names, key=str.casefold))


class ConverterCommandTest(unittest.TestCase):
    def test_copy_mp4(self):
        cmd = converter.build_command("ffmpeg", Path("a.mkv"), Path("a.mp4"), converter.ConvertOptions(mode="copy"))
        self.assertIn("copy", cmd)
        self.assertNotIn("libx264", cmd)

    def test_encode_720(self):
        opts = converter.ConvertOptions(resolution=720, quality="balanced", start="0:05", end="0:15")
        cmd = converter.build_command("ffmpeg", Path("a.mkv"), Path("a.mp4"), opts)
        self.assertIn("libx264", cmd)
        self.assertEqual(cmd[cmd.index("-crf") + 1], "23")
        self.assertIn("scale=-2:'min(720,ih)'", cmd)
        self.assertEqual(cmd[cmd.index("-ss") + 1], "5.000")
        self.assertEqual(cmd[cmd.index("-t") + 1], "10.000")

    def test_bad_trim(self):
        with self.assertRaises(ValueError):
            converter.trim_window(converter.ConvertOptions(start="10", end="5"))


FFMPEG = ffmpeg_tools.find_ffmpeg()


@unittest.skipUnless(FFMPEG, "ffmpeg yok")
class ConverterIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.src = Path(cls.tmp.name) / "kaynak.mkv"
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                        "testsrc=size=640x360:rate=25:duration=3", "-f", "lavfi", "-i",
                        "sine=frequency=440:duration=3", "-c:v", "libx264", "-c:a", "aac",
                        "-shortest", str(cls.src)], check=True, creationflags=ffmpeg_tools.NO_WINDOW)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _run(self, opts):
        dst = converter.output_path(self.src, opts)
        cmd = converter.build_command(FFMPEG, self.src, dst, opts)
        ratios = []
        converter.run_ffmpeg(cmd, ffmpeg_tools.probe_duration(FFMPEG, str(self.src)),
                             lambda r, s: ratios.append(r), threading.Event())
        self.assertTrue(dst.exists() and dst.stat().st_size > 0)
        return dst, ratios

    def test_duration(self):
        self.assertAlmostEqual(ffmpeg_tools.probe_duration(FFMPEG, str(self.src)), 3.0, delta=0.2)

    def test_remux_to_mp4(self):
        dst, ratios = self._run(converter.ConvertOptions(mode="copy", target="mp4"))
        self.assertEqual(dst.suffix, ".mp4")
        self.assertEqual(ratios[-1], 1.0)

    def test_encode_small_webm(self):
        dst, _ = self._run(converter.ConvertOptions(target="webm", resolution=240, speed="fast"))
        self.assertEqual(dst.suffix, ".webm")

    def test_mp3_and_gif(self):
        self._run(converter.ConvertOptions(target="mp3", audio_bitrate=128))
        self._run(converter.ConvertOptions(target="gif", resolution=120, end="1"))

    def test_copy_incompatible_gives_hint(self):
        opts = converter.ConvertOptions(mode="copy", target="mp3")  # aac -> mp3 kopyalanamaz
        dst = converter.output_path(self.src, opts)
        with self.assertRaises(converter.ConversionError) as ctx:
            converter.run_ffmpeg(converter.build_command(FFMPEG, self.src, dst, opts), 3.0,
                                 lambda *a: None, threading.Event())
        self.assertIn("Yeniden kodla", converter.explain_ffmpeg_error(ctx.exception.args[0], opts))

    def test_cancel(self):
        opts = converter.ConvertOptions(target="mp4", quality="lossless", speed="slow")
        dst = converter.output_path(self.src, opts)
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(converter.Cancelled):
            converter.run_ffmpeg(converter.build_command(FFMPEG, self.src, dst, opts), 3.0,
                                 lambda *a: None, cancel)


if __name__ == "__main__":
    unittest.main()
