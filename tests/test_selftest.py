import json
import tempfile
import unittest
from pathlib import Path

from clipxd import selftest


class SelfTestTest(unittest.TestCase):
    def test_report_without_download(self):
        with tempfile.TemporaryDirectory() as d:
            report = Path(d) / "rapor.json"
            code = selftest.run(["ClipXD.exe", "--self-test", str(report)])
            data = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(code, 0, data)
            self.assertTrue(data["ok"])
            self.assertTrue(data["checks"]["ffmpeg"])
            self.assertTrue(data["checks"]["yt_dlp_ejs"])
            self.assertGreater(data["checks"]["sites"], 500)


if __name__ == "__main__":
    unittest.main()
