"""製卡帶偏好（D-503，issue #12 第一階段）：cards batch 的 profile 塊多 preferences（第六節每條的那句、順序照表）；
沒有偏好是 []；S-34、carding.md、card-maker.md 回報格式都寫到。"""
import json
import re
import shutil
import unittest

from tests import _cards
from tests._guard_fixture import ROOT
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import profile, turn  # noqa: E402

SID = "sid-pref"
DAY = "2026-10-26"
PREFS = ["回答先講結論", "日期帶星期", "寫進檔案（暫存區、報告、文件）時，提到客戶或其他實體用 Obsidian 連結 [[名字]]；對話裡回答照舊寫純文字"]


class Lib(unittest.TestCase):
    def test_preferences_are_the_sentences_in_order(self):
        d = profile.defaults(DAY)
        d["preferences"] = [{"text": t, "source": "corrected", "date": DAY} for t in PREFS]
        self.assertEqual(profile.card_types_for_todo(d)["preferences"], PREFS)

    def test_no_preferences_is_empty_list(self):
        self.assertEqual(profile.card_types_for_todo(profile.defaults(DAY))["preferences"], [])
        self.assertEqual(profile.card_types_for_todo({})["preferences"], [])


class Batch(unittest.TestCase):
    """驗收 1：kb cards batch <批次> --json 的 profile.preferences 是第六節那幾句、順序照表；第六節空的是 []。"""

    def setUp(self):
        self.tmp, self.V, self.raw = _cards.make_card_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def batch_profile(self):
        turn.start(self.V, SID, "好，現在做")
        r = run_kb("--session", SID, "cards", "dispatch", "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        b = json.loads(r.stdout)["batches"][0]["batch"]
        r = run_kb("cards", "batch", b, "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)["profile"]

    def test_batch_carries_preferences(self):
        d = profile.load(self.V)
        d["preferences"] = [{"text": t, "source": "corrected", "date": DAY} for t in PREFS]
        profile.write(self.V, d, turn.start(self.V, None, "")["turn"])
        self.assertEqual(self.batch_profile()["preferences"], PREFS)

    def test_batch_without_preferences(self):
        self.assertEqual(self.batch_profile()["preferences"], [])


class Docs(unittest.TestCase):
    """驗收 2、3：S-34 在、carding.md 有 profile.preferences、card-maker.md 回報有「沒照做的偏好」。"""

    def test_rule_s34(self):
        text = (ROOT / "rules" / "synthesis.md").read_text(encoding="utf-8")
        rule = dict(re.findall(r"^- (S-\d{2}) (.+)$", text, re.MULTILINE))["S-34"]
        for word in ("profile.preferences", "照規則", "沒照做的偏好", "carding.md"):
            self.assertIn(word, rule)

    def test_carding_and_card_maker(self):
        carding = (ROOT / "skills" / "ingest" / "references" / "carding.md").read_text(encoding="utf-8")
        self.assertIn("profile.preferences", carding)
        self.assertIn("S-34", carding)
        self.assertIn("沒照做的偏好：", (ROOT / "agents" / "card-maker.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
