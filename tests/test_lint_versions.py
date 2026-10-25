"""lint 清單 6（驗收 5）：她改過的骨架檔 → 待處理一件（鍵帶她那份的指紋，答過不再開）；存的 schema 比現在舊、舊範本的卡進數字。"""
import shutil
import unittest

from tests import _lint as L
from kb._lib import migrate, skeleton  # noqa: E402
from kb.lint.checks import versions  # noqa: E402


class Versions(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()
        for rel in skeleton.files():  # 跟骨架一模一樣的起點
            target = self.V / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((skeleton.skeleton_root() / rel).read_bytes())
        skeleton.record(self.V)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_untouched_skeleton_only_numbers(self):
        found = versions.run(L.ctx(self.V))
        (num,) = L.by_kind(found, "number")
        self.assertEqual(num["data"]["old_schema"], len(migrate.pending(self.V)))
        self.assertIn("old_template_cards", num["data"])
        self.assertEqual(L.by_kind(found, "decide"), [])

    def test_customer_edited_claude_md(self):
        p = self.V / "CLAUDE.md"
        p.write_text(p.read_text(encoding="utf-8") + "\n我加的一句\n", encoding="utf-8")
        (dec,) = L.by_kind(versions.run(L.ctx(self.V)), "decide")
        self.assertTrue(dec["key"].startswith("skeleton:CLAUDE.md:"))
        self.assertTrue(dec["once"])
        self.assertIn("kb upgrade skeleton CLAUDE.md --replace", dec["data"]["results"][0]["do"][0])


if __name__ == "__main__":
    unittest.main()
