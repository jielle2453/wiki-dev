"""D-526（jacky 11-03）：紀事同日同卡——md 簡單卡那條 --if-absent 已有就不寫；綜合卡批次材料帶 same_card_events。"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from kb._lib import synthesis  # noqa: E402

CARD = ("---\n名稱: 台船\n---\n\n## 現況\n\n- 展示 12/8\n\n## 紀事\n\n"
        "- 2026-11-03 展示改 12 月 8 日、4 人〔f-0000000a〕\n- 2026-11-01 第一次聯絡〔f-0000000b〕\n")


class IfAbsent(unittest.TestCase):
    def test_short_line_not_written_when_card_logged(self):
        new, added, dup = synthesis.insert_events(CARD, [("2026-11-03", "2026-11-03 台船展示前確認〔f-0000000a〕")], True)
        self.assertEqual((new, added), (CARD, []))
        self.assertIn("展示改 12 月 8 日", new)

    def test_other_day_still_blocked(self):
        new, added, _ = synthesis.insert_events(CARD, [("2026-11-05", "2026-11-05 台船展示前確認〔f-0000000a〕")], True)
        self.assertEqual(added, [])

    def test_multi_card_line_with_one_new_card_written(self):
        """review 第 2 條：一行掛兩張卡、只有一張已有紀事，照寫（新那張的出處不丟）。"""
        _new, added, _ = synthesis.insert_events(CARD, [("2026-11-04", "2026-11-04 合併〔f-0000000a〕〔f-0000000c〕")], True)
        self.assertEqual(len(added), 1)

    def test_new_card_written(self):
        new, added, _ = synthesis.insert_events(CARD, [("2026-11-03", "2026-11-03 新檔〔f-0000000c〕")], True)
        self.assertEqual(added, ["2026-11-03 新檔〔f-0000000c〕"])

    def test_without_flag_replaces_as_before(self):
        new, added, _ = synthesis.insert_events(CARD, [("2026-11-03", "2026-11-03 展示改 12 月 8 日、4 人、多一位採購〔f-0000000a〕")])
        self.assertNotIn("4 人〔f-0000000a〕", new)
        self.assertIn("多一位採購", new)


class SameCardEvents(unittest.TestCase):
    def test_lines_for_ids(self):
        self.assertEqual(synthesis.same_card_events(CARD, {"f-0000000a"}), ["2026-11-03 展示改 12 月 8 日、4 人〔f-0000000a〕"])

    def test_none(self):
        self.assertEqual(synthesis.same_card_events(CARD, {"f-0000000c"}), [])
        self.assertEqual(synthesis.same_card_events(CARD, set()), [])


if __name__ == "__main__":
    unittest.main()
