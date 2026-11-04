"""多人共用 2 第 9 點：暫存區當成保留別名「暫存區」的來源（團隊雲端的夾）。兩台＝換 platform.node，各自 locate 自己的路徑。"""
import json
import unittest
from pathlib import Path

from tests.test_people import Base
from kb._lib import inventory, sources as sources_lib  # noqa: E402


class Hold(Base):
    def setUp(self):
        super().setUp()
        self.cloud_a = Path(self.tmp) / "老闆的雲端暫存"
        self.cloud_b = Path(self.tmp) / "小王的雲端暫存"
        self.cloud_a.mkdir()
        self.cloud_b.mkdir()
        (self.cloud_a / "放著.txt").write_text("x", encoding="utf-8")
        self.multi(3)

    def add_hold(self):
        r = self.kb("folders", "add", str(self.cloud_a), "--alias", "暫存區", "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def test_register_only_multi_and_only_hold(self):
        got = self.add_hold()
        self.assertEqual(got["alias"], "暫存區")
        entry = next(s for s in sources_lib.load_raw(self.V)["sources"] if s["alias"] == "暫存區")
        self.assertTrue(entry["shared"])
        other = Path(self.tmp) / "別的夾"
        other.mkdir()
        r = self.kb("folders", "add", str(other), "--alias", "收件匣")
        self.assertEqual(r.returncode, 3, r.stdout)

    def test_single_hold_refused(self):
        self.kb("profile", "set", "people", "1")
        r = self.kb("folders", "add", str(self.cloud_a), "--alias", "暫存區")
        self.assertEqual(r.returncode, 3, r.stdout)

    def test_left_in_vault(self):
        hold = self.V / "暫存區"
        hold.mkdir(exist_ok=True)
        n = sum(1 for x in hold.rglob("*") if x.is_file())
        (hold / "a.txt").write_text("1", encoding="utf-8")
        (hold / "b.txt").write_text("2", encoding="utf-8")
        self.assertEqual(self.add_hold()["left_in_vault"], n + 2)

    def test_intake_and_output_land_in_cloud_hold(self):
        self.add_hold()
        r = self.kb("folders", "locate", "暫存區", str(self.cloud_b))  # 這台的雲端夾位置不同
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        src = Path(self.tmp) / "外面來的.txt"
        src.write_text("內容", encoding="utf-8")
        before = sorted(p.name for p in (self.V / "暫存區").rglob("*") if p.is_file()) if (self.V / "暫存區").is_dir() else []
        r = self.kb("intake", str(src), "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.cloud_b / "外面來的.txt").is_file())
        after = sorted(p.name for p in (self.V / "暫存區").rglob("*") if p.is_file()) if (self.V / "暫存區").is_dir() else []
        self.assertEqual(before, after)  # 知識庫裡的暫存區沒有新檔
        uris = [loc["uri"] for e in inventory.load(self.V)["entries"] for loc in e.get("locations") or []]
        self.assertIn("file://暫存區/外面來的.txt", uris)
        work = Path(self.tmp) / "成品.docx"
        work.write_bytes(b"docx")
        r = self.kb("output", "save", str(work), "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.cloud_b / "成品.docx").is_file())


if __name__ == "__main__":
    unittest.main()
