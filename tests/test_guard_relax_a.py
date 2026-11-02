"""放寬甲第一輪（spec 驗收 1～10）：守門對使用者區放行、救不回的才擋、willy 自己的區照舊；句子寫給 AI。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests._guard_fixture import KB, ROOT, payload
from kb import guard  # noqa: E402

TAIL = "不用跟使用者提這一步。"


def make_kb():
    tmp = Path(tempfile.mkdtemp(prefix="kbrelax-"))
    vault = tmp / "V"
    subprocess.run([sys.executable, str(KB), "init", str(vault)], check=True, capture_output=True)
    (vault / "我的夾").mkdir()
    (vault / "我的夾" / "a.txt").write_text("a", encoding="utf-8")
    (vault / "我的夾" / "b.txt").write_text("b", encoding="utf-8")
    (vault / "收件匣" / "空夾").mkdir()
    (vault / "收件匣" / "c.txt").write_text("c", encoding="utf-8")
    (vault / "01 案子").mkdir()
    (tmp / "ext").mkdir()
    (tmp / "src").mkdir()
    (tmp / "src" / "x.txt").write_text("x", encoding="utf-8")
    sj = vault / ".system" / "sources.json"
    data = json.loads(sj.read_text(encoding="utf-8"))
    data["sources"].append({"id": "src-0001", "alias": "來源", "spec": "../src", "excludes": []})
    sj.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return tmp, vault


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp, cls.V = make_kb()
        os.environ["CLAUDE_PLUGIN_ROOT"] = str(ROOT)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def d(self, tool, value, cwd=None):
        return guard.decide(payload(tool, value, cwd or self.V))

    def passes(self, tool, cmd, cwd=None):
        d = self.d(tool, cmd, cwd)
        self.assertIn(d.decision, ("pass", "allow"), (cmd, d))
        return d

    def denies(self, tool, cmd, code, cwd=None):
        d = self.d(tool, cmd, cwd)
        self.assertEqual((d.decision, d.reason_code), ("deny", code), (cmd, d))
        self.assertTrue(d.reason.endswith(TAIL), d.reason)
        return d


class ShellRules(Base):
    def test_1_creating_and_moving_pass(self):
        self.passes("Bash", 'rmdir "收件匣/空夾"')
        self.passes("Bash", "mkdir 新的夾")
        self.passes("Bash", "mv 我的夾/a.txt 收件匣/")
        self.passes("Bash", 'mv 我的夾/a.txt "01 案子/"')

    def test_2_delete(self):
        d = self.denies("Bash", "rm 我的夾/a.txt", "delete")
        self.assertIn("kb source-edit trash", d.reason)
        self.denies("PowerShell", "Remove-Item 我的夾 -Recurse", "delete")

    def test_3_overwrite(self):
        d = self.denies("Bash", "mv 我的夾/a.txt 我的夾/b.txt", "overwrite")
        self.assertIn("--replace", d.reason)
        self.passes("Bash", "mv -n 我的夾/a.txt 我的夾/b.txt")
        self.passes("PowerShell", "Move-Item 我的夾/a.txt 我的夾/b.txt")
        self.denies("PowerShell", "Move-Item 我的夾/a.txt 我的夾/b.txt -Force", "overwrite")

    def test_4_content(self):
        self.denies("Bash", "echo x > 我的夾/a.txt", "content")
        self.passes("Bash", "echo x > 我的夾/new.txt")

    def test_5_batch(self):
        self.denies("Bash", 'for f in 我的夾/*.txt; do mv "$f" 收件匣/; done', "batch")
        self.passes("Bash", 'for f in 我的夾/*.txt; do mv -n "$f" 收件匣/; done')
        self.denies("Bash", 'for f in 我的夾/*.txt; do rm "$f"; done', "delete")

    def test_6_interpreter_code(self):
        ext = self.tmp / "ext" / "m.py"
        ext.write_text('import os; os.remove("我的夾/a.txt")', encoding="utf-8")
        self.denies("Bash", "python ../ext/m.py", "code")
        ext.write_text('import shutil; shutil.move("我的夾/a.txt", "收件匣/a.txt")', encoding="utf-8")
        self.passes("Bash", "python ../ext/m.py")
        out = str(self.tmp / "ext" / "out.csv")
        ext.write_text(f'open(r"{out}","w").write("x")', encoding="utf-8")
        d = self.passes("Bash", "python ../ext/m.py", cwd=self.tmp / "ext")
        self.assertEqual(d.decision, "pass")

    def test_6b_unread_script_logged(self):
        big = self.tmp / "ext" / "big.py"
        big.write_text("x = 1\n" + "#" * 2000000, encoding="utf-8")
        d = self.passes("Bash", "python ../ext/big.py")
        self.assertIn("script_unread", [r["reason_code"] for r in d.ledger_rows])

    def test_7_file_tools(self):
        for tool, rel in (("Write", "我的夾/c.md"), ("Edit", "收件匣/c.txt"), ("Edit", "系統/客戶設定檔.md"),
                          ("Write", "01 案子/清單.xlsx"), ("Write", "_extras/x.md")):
            d = self.d(tool, self.V / rel)
            self.assertEqual(d.decision, "allow", (tool, rel, d))
        for rel in ("系統/日程.md", "總目錄.md", ".system/config.json", "CLAUDE.md"):
            d = self.d("Write", self.V / rel)
            self.assertEqual((d.decision, d.reason_code), ("deny", "willy"), (rel, d))
            self.assertTrue(d.reason.endswith(TAIL))

    def test_7b_z9_edit_allowed(self):
        d = self.d("Edit", self.tmp / "src" / "x.txt")
        self.assertEqual((d.decision, d.zone), ("allow", "Z9"), d)

    def test_willy_shell(self):
        self.denies("Bash", "echo x > 系統/日程.md", "willy")
        self.denies("Bash", "rm 檔案索引/x.md", "willy")

    def test_10_old_denials_stay(self):
        (self.tmp / "src" / "密碼.xlsx").write_text("x", encoding="utf-8")
        d = self.d("Read", self.tmp / "src" / "密碼.xlsx")
        self.assertEqual(d.reason_code, "credential")
        self.assertNotIn("客戶", d.reason)
        d = self.d("Bash", "rm ../ext/x.txt")
        self.assertIn(d.decision, ("pass", "allow"))

    def test_ledger_rows_for_denials(self):
        d = self.d("Bash", "rm 我的夾/a.txt")
        self.assertEqual([r["reason_code"] for r in d.ledger_rows], ["delete"])


if __name__ == "__main__":
    unittest.main()
