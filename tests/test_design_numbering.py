"""decisions、backlog、incidents 的編號不重複（process 第八節：兩人協作、decisions.md 與 backlog.md 用 merge=union，撞號或同一條新舊兩版都留下時這裡紅）。"""
import re
import unittest
from collections import Counter
from pathlib import Path

DESIGN = Path(__file__).resolve().parents[1] / "design"
ENTRIES = {
    "decisions.md": re.compile(r"^#+ (D-\d+)\b", re.MULTILINE),
    "backlog.md": re.compile(r"^\| (B-\d+) \|", re.MULTILINE),
    "incidents.md": re.compile(r"^#+ (I-\d+)\b", re.MULTILINE),
}


class DesignNumbering(unittest.TestCase):
    def test_numbers_are_unique(self):
        for name, pattern in ENTRIES.items():
            with self.subTest(file=name):
                found = pattern.findall((DESIGN / name).read_text(encoding="utf-8"))
                self.assertTrue(found, f"{name} 找不到任何條目，格式變了要改這裡")
                twice = sorted(n for n, c in Counter(found).items() if c > 1)
                self.assertEqual(twice, [], f"{name} 有重複的編號（撞號，或合併後同一條留了新舊兩版）")


if __name__ == "__main__":
    unittest.main()
