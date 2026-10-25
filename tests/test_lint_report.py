"""健檢報告（驗收 21，D-227）：固定格式（templates/health-report.md）、沒內容的段不寫、摺疊段、不印編號、一句話跟上個月比。"""
import re
import unittest

from tests._guard_fixture import ROOT  # noqa: F401  sys.path
from kb.lint import report  # noqa: E402


class Summary(unittest.TestCase):
    def test_compare_with_last_month(self):
        self.assertEqual(report.summary(3, 3, {"decide": 5, "done": 3}), "大致正常；要你決定的事比上個月少 2 件。")
        self.assertEqual(report.summary(0, 2, {"decide": 0, "done": 4}),
                         "一切正常；要你決定的事跟上個月一樣多，替你做的事比上個月少 2 件。")
        self.assertEqual(report.summary(6, 1, None), "有 6 件要你決定；這個月替你做了 1 件事。")
        self.assertEqual(report.summary(0, 0, None), "一切正常。")


class Text(unittest.TestCase):
    def full(self):
        return report.text("2026-10", summary="大致正常；要你決定的事比上個月少 2 件。",
                           done=["清掉 40 個回合備份，空出 12 MB", "收起 3 條被取代或收回的口述"],
                           decide=["設定檔的「報價」那類改過之後，有 120 張卡是之前做的；要不要照新的設定重做？"],
                           aside=["「大安陳合約.pdf」讀不到（放了 45 天）"], suggest=["上次備份是 40 天前，說「幫我備份」就好"],
                           numbers=["卡 412、綜合卡 38、待處理 5（先放著 6）"])

    def test_format(self):
        text = self.full()
        self.assertTrue(text.startswith("# 健檢報告 2026-10\n這是什麼："))
        heads = re.findall(r"^## (.+)$", text, re.M)
        self.assertEqual(heads, ["一句話", "這個月替你做了什麼", "要你決定的", "先放著超過一個月的", "建議下一步", "數字（給服務人員）"])
        self.assertIn("> [!todo]- 已放進待處理（1 件，這是當時的狀況，現在的看 [[待處理]]）\n> - 設定檔的", text)
        self.assertIn("- 清掉 40 個回合備份，空出 12 MB\n", text)

    def test_empty_sections_dropped(self):
        text = report.text("2026-10", summary="一切正常。", done=[], decide=[], aside=[], suggest=[], numbers=["卡 3"])
        self.assertEqual(re.findall(r"^## (.+)$", text, re.M), ["一句話", "數字（給服務人員）"])
        self.assertNotIn("{", text)

    def test_no_ids(self):
        self.assertIsNone(re.search(r"\b[pfsrcae]-[0-9a-f]{8}\b", self.full()))

    def test_template_file_is_used(self):
        self.assertIn("這是什麼：", report.template())


if __name__ == "__main__":
    unittest.main()
