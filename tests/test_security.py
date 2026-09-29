"""Hata / güvenlik taramasında bulunup düzeltilen sorunların regresyon testleri."""
import json
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path

from clipxd import accounts, converter, downloader, ffmpeg_tools, secure_store
from clipxd.settings import DEFAULTS, Settings


class TimeParsingTest(unittest.TestCase):
    def test_rejects_non_numeric(self):
        for bad in ("nan", "inf", "1e3", "-5", "1:-5", "0x10", "1:2:3:4", "abc", "1::2"):
            with self.assertRaises(ValueError, msg=bad):
                ffmpeg_tools.parse_time(bad)

    def test_valid_forms(self):
        self.assertEqual(ffmpeg_tools.parse_time("90"), 90)
        self.assertEqual(ffmpeg_tools.parse_time("1:30"), 90)
        self.assertEqual(ffmpeg_tools.parse_time("0:01:30"), 90)
        self.assertEqual(ffmpeg_tools.parse_time("01:30:00"), 5400)
        self.assertEqual(ffmpeg_tools.parse_time("12,5"), 12.5)
        self.assertIsNone(ffmpeg_tools.parse_time(""))


class FolderNameTest(unittest.TestCase):
    def test_windows_reserved_names(self):
        for name in ("CON", "nul", "COM1", "LPT9.txt", "aux "):
            folder = downloader.playlist_folder_name(name)
            self.assertNotEqual(folder.split(".")[0].strip().upper(),
                                name.split(".")[0].strip().upper(), folder)

    def test_no_path_traversal(self):
        for title in ("..", "../../Windows", "..\\..\\x", "/etc/passwd"):
            folder = downloader.playlist_folder_name(title)
            self.assertNotIn("/", folder)
            self.assertNotIn("\\", folder)
            self.assertNotIn(folder, ("..", "."))


class SelectionFilterTest(unittest.TestCase):
    def test_only_checks_flat_stage(self):
        f = downloader.selection_filter({"a", "b"})
        self.assertIsNone(f({"id": "a"}, incomplete=True))
        self.assertEqual(f({"id": "z"}, incomplete=True), "Seçilmedi")
        # tam çözülmüş videoda kimlik farklı olabilir: asla atlanmamalı
        self.assertIsNone(f({"id": "tam-kimlik-farkli"}, incomplete=False))
        self.assertIsNone(f({"playlist_id": "PL1"}, incomplete=True))  # liste düzeyi bilgi
        self.assertIsNone(downloader.selection_filter(set())({"id": "x"}, incomplete=True))


class _FakeYDL:
    def __init__(self, folder):
        self.folder = folder
        self.params = {"final_ext": None}
        self._postprocessor_hooks = []

    def prepare_filename(self, info):
        return str(Path(self.folder) / f"{info['title']}{info.get('mk_suffix', '')}.mp4")

    def __getattr__(self, name):  # yt-dlp'nin çağırdığı diğer yardımcılar (başlık, kayıt) için boş işlev
        return lambda *a, **k: None


class UniqueNameClaimTest(unittest.TestCase):
    def test_concurrent_same_title_gets_distinct_names(self):
        with tempfile.TemporaryDirectory() as d:
            ydl = _FakeYDL(d)
            first, second = downloader.UniqueNamePP(ydl), downloader.UniqueNamePP(ydl)
            _, i1 = first.run({"title": "Video"})
            _, i2 = second.run({"title": "Video"})  # ilk dosya henüz diskte yokken
            self.assertNotIn("mk_suffix", i1)
            self.assertEqual(i2["mk_suffix"], " (1)")
            first.release()
            second.release()
            _, i3 = downloader.UniqueNamePP(ydl).run({"title": "Video"})
            self.assertNotIn("mk_suffix", i3)  # rezervasyonlar kalktı

    def test_existing_file_on_disk(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "Video.mp4").write_bytes(b"x")
            (Path(d) / "Video (1).mp4").write_bytes(b"x")
            pp = downloader.UniqueNamePP(_FakeYDL(d))
            _, info = pp.run({"title": "Video"})
            self.assertEqual(info["mk_suffix"], " (2)")
            pp.release()


class AccountSafetyTest(unittest.TestCase):
    def test_empty_domains_import_nothing(self):
        jar = accounts.new_jar()
        jar.set_cookie(accounts.make_cookie(".bank.com", "session", "gizli"))
        self.assertEqual(len(accounts.filter_jar(jar, [])), 0)
        self.assertEqual(len(accounts.filter_jar(jar, None)), 0)

    def test_normalize_domains(self):
        valid, rejected = accounts.normalize_domains(
            "https://www.Site.com/giris, video.site.com; com  co.uk bad_domain *.cdn.site.com site.com")
        self.assertEqual(valid, ["site.com", "video.site.com", "cdn.site.com"])
        self.assertEqual(rejected, ["com", "co.uk", "bad_domain"])

    def test_corrupt_index_is_backed_up_not_lost(self):
        with tempfile.TemporaryDirectory() as d:
            idx = Path(d) / "accounts.json"
            idx.write_text("{bozuk json", encoding="utf-8")
            store = accounts.AccountStore(Path(d))
            self.assertEqual(store.all(), [])
            self.assertTrue(store.load_error)
            self.assertTrue(list(Path(d).glob("accounts.bozuk-*.json")))  # orijinal içerik korunuyor

    def test_unknown_fields_and_bad_ids(self):
        with tempfile.TemporaryDirectory() as d:
            data = [
                {"id": "abcdef123456", "name": "Ana", "platform": "instagram", "domains": ["instagram.com"],
                 "yeni_surum_alani": 1},
                {"id": "../../evil", "name": "Kötü", "platform": "x"},
                "bozuk-kayit",
            ]
            (Path(d) / "accounts.json").write_text(json.dumps(data), encoding="utf-8")
            store = accounts.AccountStore(Path(d))
            self.assertEqual([a.id for a in store.all()], ["abcdef123456"])
            self.assertFalse(store.load_error)


class SettingsSafetyTest(unittest.TestCase):
    def test_wrong_types_fall_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "settings.json"
            p.write_text(json.dumps({"max_concurrent": "abc", "theme": 5, "download": "x",
                                     "convert": {"fps": "hızlı", "target": "mkv"}, "bilinmeyen": 1}),
                         encoding="utf-8")
            s = Settings(p)
            self.assertEqual(s["max_concurrent"], DEFAULTS["max_concurrent"])
            self.assertEqual(s["theme"], DEFAULTS["theme"])
            self.assertEqual(s["download"], DEFAULTS["download"])
            self.assertEqual(s["convert"]["fps"], DEFAULTS["convert"]["fps"])
            self.assertEqual(s["convert"]["target"], "mkv")
            self.assertNotIn("bilinmeyen", s.data)
            p.write_text(json.dumps({"max_concurrent": 99, "download": {"compat": "evet"}}), encoding="utf-8")
            s = Settings(p)
            self.assertEqual(s["max_concurrent"], DEFAULTS["max_concurrent"])
            self.assertIs(s["download"]["compat"], True)

    def test_proxy_moved_to_encrypted_store(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "settings.json"
            p.write_text(json.dumps({"proxy": "socks5://kullanici:SIFRE123@host:1080"}), encoding="utf-8")
            s = Settings(p)
            self.assertEqual(s.proxy, "socks5://kullanici:SIFRE123@host:1080")
            self.assertNotIn("SIFRE123", p.read_text(encoding="utf-8"))
            if secure_store.ENCRYPTED:
                self.assertNotIn(b"SIFRE123", (Path(d) / "proxy.bin").read_bytes())
            s.proxy = ""
            self.assertFalse((Path(d) / "proxy.bin").exists())


class RebrandMigrationTest(unittest.TestCase):
    def test_legacy_data_folder_is_moved(self):
        import os
        from unittest import mock
        from clipxd import paths
        with tempfile.TemporaryDirectory() as d:
            old = Path(d) / "MedyaKit"
            (old / "cookies").mkdir(parents=True)
            (old / "settings.json").write_text("{}", encoding="utf-8")
            (old / "cookies" / "abc.bin").write_bytes(b"sifreli")
            env = {k: v for k, v in os.environ.items() if k != "CLIPXD_DATA_DIR"}
            env["APPDATA"] = d
            with mock.patch.dict(os.environ, env, clear=True):
                new = paths.data_dir()
            self.assertEqual(new, Path(d) / "ClipXD")
            self.assertTrue((new / "cookies" / "abc.bin").exists())
            self.assertFalse(old.exists())
            # ikinci çağrı: zaten taşınmış, yeniden dokunulmaz
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(paths.data_dir(), new)

    def test_legacy_default_download_dir_is_updated(self):
        from clipxd.paths import default_download_dir, legacy_download_dir
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "settings.json"
            p.write_text(json.dumps({"download_dir": str(legacy_download_dir())}), encoding="utf-8")
            self.assertEqual(Settings(p)["download_dir"], str(default_download_dir()))
            p.write_text(json.dumps({"download_dir": "D:/Videolarim"}), encoding="utf-8")
            self.assertEqual(Settings(p)["download_dir"], "D:/Videolarim")  # kullanıcının seçimi korunur

    def test_dpapi_entropy_unchanged(self):
        # Değişirse eski sürümle eklenen hesapların çerezleri çözülemez
        self.assertEqual(secure_store._ENTROPY, b"MedyaKit-cookie-store-v1")


class TemplateValidationTest(unittest.TestCase):
    def test_template_rules(self):
        from clipxd.ui.settings_tab import SettingsPage
        ok = SettingsPage._template_problem
        self.assertEqual(ok("%(title)s.%(ext)s"), "")
        self.assertEqual(ok("%(uploader)s/%(title)s.%(ext)s"), "")
        self.assertTrue(ok("%(title)s"))                   # uzantı yok
        self.assertTrue(ok("C:/Windows/%(title)s.%(ext)s"))  # mutlak yol
        self.assertTrue(ok("../%(title)s.%(ext)s"))         # klasör dışına çıkma
        self.assertTrue(ok("a\\..\\%(title)s.%(ext)s"))


FFMPEG = ffmpeg_tools.find_ffmpeg()


@unittest.skipUnless(FFMPEG, "ffmpeg yok")
class ConverterCancelTest(unittest.TestCase):
    def test_cancel_takes_effect_quickly(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "uzun.mkv"
            subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                            "testsrc=size=1280x720:rate=30:duration=60", "-c:v", "libx264", "-preset",
                            "ultrafast", str(src)], check=True, creationflags=ffmpeg_tools.NO_WINDOW)
            opts = converter.ConvertOptions(target="webm", quality="lossless", speed="slow")
            dst = converter.output_path(src, opts)
            cancel = threading.Event()
            threading.Timer(0.8, cancel.set).start()
            t = time.time()
            with self.assertRaises(converter.Cancelled):
                converter.run_ffmpeg(converter.build_command(FFMPEG, src, dst, opts), 60, lambda *a: None, cancel)
            self.assertLess(time.time() - t, 4)


if __name__ == "__main__":
    unittest.main()
