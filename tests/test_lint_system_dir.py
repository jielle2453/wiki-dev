"""lint 清單 9（驗收 8）：.system/ 底下有捷徑夾 → 待處理一件；工作日誌卡在沒寫完的那行超過一天 → 地板句補完、done true。"""
import json
import os
import shutil
import subprocess
import unittest

from tests import _lint as L
from kb._lib import journal  # noqa: E402
from kb.lint.checks import system_dir  # noqa: E402


class SystemDir(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @unittest.skipUnless(os.name == "nt", "mklink /J 只在 Windows")
    def test_junction_in_system(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        link = self.V / ".system" / "temp"
        if link.exists():
            shutil.rmtree(link)
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        (dec,) = L.by_kind(system_dir.run(L.ctx(self.V)), "decide")
        self.assertEqual(dec["key"], "system_link")
        self.assertIn(".system/temp", dec["data"]["paths"])

    def test_stuck_journal_row_completed(self):
        d = self.V / ".system" / "journal"
        d.mkdir(exist_ok=True)
        old = {"schema_version": 1, "kind": "turn", "turn": "20261023-100000-abcd", "time": "2026-10-23T10:00:00",
               "prompt": "幫我整理", "done": False}
        new = dict(old, turn="20261025-090000-abcd", time="2026-10-25T09:00:00")
        (d / "2026-10.jsonl").write_text(json.dumps(old) + "\n" + json.dumps(new) + "\n", encoding="utf-8")
        (fix,) = L.by_kind(system_dir.run(L.ctx(self.V, today="2026-10-25")), "fix")
        text = fix["apply"](L.ctx(self.V, today="2026-10-25"))
        self.assertEqual(text, "補完 1 句沒記完的工作日誌")  # 桌面版確認後改白話
        rows = {r["turn"]: r for r in journal.read_lines(self.V, "2026-10")}
        self.assertTrue(rows["20261023-100000-abcd"]["done"])
        self.assertEqual(rows["20261023-100000-abcd"]["note"], journal.NO_CHANGES)
        self.assertFalse(rows["20261025-090000-abcd"]["done"], "不到一天的不動")

    def test_clean_system(self):
        self.assertEqual(system_dir.run(L.ctx(self.V)), [])


if __name__ == "__main__":
    unittest.main()
