"""輕流程 todo 精簡（2026-11-03）：cards todo --json 預設 moved 最多 10 筆加 moved_total、profile 只給 about；--full 整份。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from kb import cards as cards_cli  # noqa: E402


class Brief(unittest.TestCase):
    def data(self, n):
        return {"moved": [{"id": f"f-{k:08x}"} for k in range(n)], "new": [],
                "profile": {"about": [{"name": "我", "kind": "company", "aliases": []}], "card_types": [{"name": "x"}],
                            "tags": {"案子": []}}}

    def test_many_moved_cut(self):
        out = cards_cli._brief(self.data(11))
        self.assertEqual((len(out["moved"]), out["moved_total"]), (10, 11))

    def test_few_moved_kept(self):
        out = cards_cli._brief(self.data(10))
        self.assertEqual(len(out["moved"]), 10)
        self.assertNotIn("moved_total", out)

    def test_profile_about_only(self):
        out = cards_cli._brief(self.data(0))
        self.assertEqual(out["profile"], {"about": [{"name": "我", "kind": "company", "aliases": []}]})

    def test_original_untouched(self):
        d = self.data(11)
        cards_cli._brief(d)
        self.assertEqual((len(d["moved"]), set(d["profile"])), (11, {"about", "card_types", "tags"}))


if __name__ == "__main__":
    unittest.main()
