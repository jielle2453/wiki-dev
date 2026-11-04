"""lint 清單 6（驗收 5）：她改過的骨架檔 → 待處理一件（鍵帶她那份的指紋，答過不再開）；存的 schema 比現在舊、舊範本的卡進數字。"""
import json
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

    def edit(self, rel="CLAUDE.md"):
        p = self.V / rel
        p.write_text(p.read_text(encoding="utf-8") + "\n我加的一句\n", encoding="utf-8")

    def stale_record(self, rel="CLAUDE.md"):
        """記的指紋停在舊版（新版這個檔改過、升級還沒處理完）。"""
        data = skeleton.recorded(self.V)
        data["files"][rel] = "0" * 64
        (self.V / skeleton.SKELETON_JSON).write_text(json.dumps(data), encoding="utf-8")

    def test_edited_but_skeleton_unchanged_is_quiet(self):
        """D-528：新版沒改這個檔（記的指紋等於新版的），她自己改了不問。"""
        self.edit()
        self.assertEqual(L.by_kind(versions.run(L.ctx(self.V)), "decide"), [])

    def test_edited_and_new_version_changed_asks(self):
        self.stale_record()
        self.edit()
        (dec,) = L.by_kind(versions.run(L.ctx(self.V)), "decide")
        self.assertTrue(dec["key"].startswith("skeleton:CLAUDE.md:"))
        self.assertTrue(dec["once"])
        self.assertIn("kb upgrade skeleton CLAUDE.md --replace", dec["data"]["results"][0]["do"][0])

    def test_keep_then_lint_quiet_even_after_more_edits(self):
        """#35：--keep 之後健檢不再問；她再改也不問，直到新版這個檔又改了。"""
        self.stale_record()
        self.edit()
        skeleton.keep(self.V, "CLAUDE.md")
        self.assertEqual(L.by_kind(versions.run(L.ctx(self.V)), "decide"), [])
        self.edit()
        self.assertEqual(L.by_kind(versions.run(L.ctx(self.V)), "decide"), [])
        self.stale_record()  # 新版又改了
        self.assertEqual(len(L.by_kind(versions.run(L.ctx(self.V)), "decide")), 1)

if __name__ == "__main__":
    unittest.main()
