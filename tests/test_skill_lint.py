"""skills/lint 的形狀（lint 題要做的事 10，驗收 23）：frontmatter 只有 name、description；描述 150 字內、不帶英文、收「幫我檢查」
「有沒有什麼問題」「看健檢報告」，不收的放分號後；本文 120 行、3000 字內、沒有步驟編號與參數對照表，原則帶理由與編號
（D-220、D-222、D-223、D-227、升格）；骨架指到 kb lint 與 references/report.md；report.md ≤150 行、沒有絕對路徑；
tests/evals/lint.json 20 句、各半，不該觸發的含「看待處理」「有沒有要我確認的」「幫我備份」「整理一下」。"""
import json
import re
import unittest

from tests._guard_fixture import ROOT

SKILL_DIR = ROOT / "skills" / "lint"
SKILL = SKILL_DIR / "SKILL.md"
REPORT = SKILL_DIR / "references" / "report.md"
EVALS = ROOT / "tests" / "evals" / "lint.json"
ABS_PATH = re.compile(r"(?<![A-Za-z$])[A-Za-z]:[\\/]|/Users/|/home/")


def split(text):
    lines = text.splitlines()
    end = lines.index("---", 1)
    return lines[1:end], "\n".join(lines[end + 1:])


class Shape(unittest.TestCase):
    def setUp(self):
        front, self.body = split(SKILL.read_text(encoding="utf-8"))
        self.fields = dict(line.split(":", 1) for line in front)

    def test_frontmatter(self):
        self.assertEqual(set(self.fields), {"name", "description"})
        self.assertEqual(self.fields["name"].strip(), "lint")
        desc = self.fields["description"].strip()
        self.assertLessEqual(len(desc), 150)
        self.assertIsNone(re.search(r"[A-Za-z]{2,}", desc), desc)
        for word in ("幫我檢查", "有沒有什麼問題", "看健檢報告"):
            self.assertIn(word, desc)
        self.assertIn("看待處理", desc[desc.index("；"):])

    def test_body_size_and_style(self):
        self.assertLessEqual(len(self.body), 3000)
        self.assertLessEqual(len(self.body.splitlines()), 120)
        self.assertIsNone(re.search(r"^\s*\d+\.\s", self.body, re.M), "骨架不編號")
        self.assertIsNone(re.search(r"^\|", self.body, re.M), "本文沒有對照表")

    def test_principles_have_reasons_and_codes(self):
        part = self.body[self.body.index("## 原則"):self.body.index("## 骨架")]
        bullets = [b for b in part.splitlines() if b.startswith("- **")]
        self.assertGreaterEqual(len(bullets), 5)
        for b in bullets:
            self.assertRegex(b, r"（[^）]*[DBI]-\d+[^）]*）", b)
        for code in ("D-220", "D-222", "D-223", "D-227", "D-150"):
            self.assertIn(code, part)

    def test_skeleton_points(self):
        part = self.body[self.body.index("## 骨架"):]
        for word in ("kb lint --json", "kb lint handedit", "references/report.md", "ingest", "kb asks"):
            self.assertIn(word, part)
        self.assertIn('python "${CLAUDE_PLUGIN_ROOT}/scripts/kb.py"', self.body)

    def test_report_reference(self):
        text = REPORT.read_text(encoding="utf-8")
        self.assertLessEqual(len(text.splitlines()), 150)
        self.assertIsNone(ABS_PATH.search(text))
        for word in ("most_urgent", "handedit", "promote", "redo_by_profile", "看健檢報告", "退回"):
            self.assertIn(word, text)


class Evals(unittest.TestCase):
    def test_twenty_half_half(self):
        rows = json.loads(EVALS.read_text(encoding="utf-8"))
        self.assertEqual(len(rows), 20)
        self.assertEqual(sum(r["should_trigger"] for r in rows), 10)
        negatives = " ".join(r["query"] for r in rows if not r["should_trigger"])
        for word in ("看待處理", "有沒有要我確認的", "備份", "整理一下"):
            self.assertIn(word, negatives)


if __name__ == "__main__":
    unittest.main()
