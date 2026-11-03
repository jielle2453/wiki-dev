"""rules/core.md 內容（D-059、D-087）：R-01～R-14 各恰一次、順序遞增、每條以「- R-nn 」開頭；不含絕對路徑與 plugin 變數。"""
import re
import unittest
from pathlib import Path

from tests import _guard_fixture  # noqa: F401  把 scripts/ 加進 sys.path
from kb._lib.areas import FREE_DIR  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "rules" / "core.md"


class RulesCore(unittest.TestCase):
    def setUp(self):
        self.text = CORE.read_text(encoding="utf-8")

    def test_r01_to_r14_each_once_in_order(self):
        """條目各恰一次、順序遞增；條文裡引用別條（R-14「照 R-12」）不算條目，但引用的編號要存在。"""
        found = re.findall(r"^- (R-\d{2}) ", self.text, re.M)
        ids = [f"R-{n:02d}" for n in range(1, 15)]
        self.assertEqual(found, ids)
        for ref in re.findall(r"R-\d{2}", self.text):
            self.assertIn(ref, ids)

    def test_each_rule_line_starts_with_dash_and_id(self):
        rules = [line for line in self.text.splitlines() if line.startswith("- ")]
        self.assertEqual(len(rules), 14)
        for n, line in enumerate(rules, 1):
            self.assertTrue(line.startswith(f"- R-{n:02d} "), line)

    def test_no_absolute_path_or_plugin_variable(self):
        for bad in ("C:", "${CLAUDE_PLUGIN_ROOT}", "\\", "http"):
            self.assertNotIn(bad, self.text)

    def test_r13_recent_changes_uses_changed(self):
        """answer 測試第二輪後裁定 29（G-1）：「最近改了什麼」在常駐就寫明帶 --changed，不載 answer 也篩得對。"""
        line = next(ln for ln in self.text.splitlines() if ln.startswith("- R-13 "))
        self.assertTrue(line.endswith("問最近改了什麼用 kb journal recent --changed 答。"), line)

    def test_r13_closing_mentions_wip(self):
        """D-525 第 6 點：收工、今天先這樣時有製作中就帶一句，不問。"""
        line = next(ln for ln in self.text.splitlines() if ln.startswith("- R-13 "))
        self.assertIn("客戶說「收工」「今天先這樣」，跑 kb cards wip，有製作中的就在回答最後帶一句還有哪幾份沒整理，不問", line)

    def test_r04_trash_through_kb(self):
        """manage 第二版第 10 點（D-173、I-116）：R-04 刪除改成經 kb 丟資源回收筒；放寬乙改成先留一份就做、不先講後果。R-07 改成先拍快照再代做。"""
        line = next(ln for ln in self.text.splitlines() if ln.startswith("- R-04 "))
        self.assertEqual(line, "- R-04 動客戶的檔：搬、改名、建夾、刪空夾用什麼方法都行；刪掉、蓋掉、改內容之前先留一份（刪用 kb source-edit trash，改文字檔用 Edit，Word、Excel 用 kb office），留好就做，不先講後果、不多問。kb 說刪了救不回來時，用白話問一句，客戶說確定才刪。")

    def test_r01_free_area_read_only_when_asked(self):
        """彈性區（#21，D-511、裁定 12、19）：R-01 句尾補彈性區平常不讀、別處找不到也不翻、有檔才問、提到這一區或答應要看才讀、Word 走 kb convert 讀不到照實說；夾名照 areas.FREE_DIR。"""
        line = next(ln for ln in self.text.splitlines() if ln.startswith("- R-01 "))
        self.assertTrue(line.endswith(f"{FREE_DIR}是客戶自己的：平常不讀不搜，別處找不到也不去翻，說沒有，{FREE_DIR}有檔才問要不要看；"
                                      "她提到這一區或答應要看才讀，Word、Excel 這類用 kb convert 讀、讀不到就照實說，寫用檔案工具；"
                                      "卡、成品、客戶原檔的副本不放這裡。"), line)

    def test_r07_restore_and_upgrade_after_yes(self):
        """備份還原與換電腦要做的事 12（D-205、D-215）：R-07 這一句跟「升級與打包發行」共用、一字不差。"""
        line = next(ln for ln in self.text.splitlines() if ln.startswith("- R-07 "))
        self.assertEqual(line, "- R-07 重建整個知識庫先拍快照再代做；還原、升級先講一句會發生什麼，客戶說好就做。只有搬整個知識庫在開著的對話裡做不到，一步一步帶客戶做。")

    def test_utf8_lf_single_trailing_newline(self):
        raw = CORE.read_bytes()
        self.assertNotIn(b"\r", raw)
        self.assertTrue(raw.endswith(b"\n") and not raw.endswith(b"\n\n"))



class SkeletonSentinel(unittest.TestCase):
    def test_plugin_screen_sentence(self):
        """manage 第二版第 1 點（B-093 3-3）：哨兵句補「Python 正常就看外掛畫面」那一句。"""
        text = (ROOT / "skeleton" / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("Python 正常就看外掛有沒有裝著、啟用（claude plugin list）", text)


if __name__ == "__main__":
    unittest.main()


class BuildReportTemplate(unittest.TestCase):
    def test_backup_hint_in_how_to_start_section(self):
        """備份還原與換電腦要做的事 14（D-209）：交付報告「怎麼開始問」段有備份那句。"""
        text = (ROOT / "templates" / "build-report.md").read_text(encoding="utf-8")
        section = text.split("## 怎麼開始問", 1)[1].split("\n## ", 1)[0]
        self.assertIn("建議偶爾備份：說「幫我備份」就好", section)
