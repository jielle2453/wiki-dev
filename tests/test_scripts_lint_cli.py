"""kb lint 黑箱（驗收 10、18、21）：--json 的欄位、人讀第一行一句話、同月重寫一份報告、ingest 跟 cards todo 同數、
另一個健檢在跑 exit 3 一字不差；kb lint handedit 列她手改的差異、--done 收掉；--background 不印、exit 0。"""
import json
import shutil
import unittest
from datetime import date

from tests import _lint as L
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import io as kio  # noqa: E402
from kb._lib import pending, turn  # noqa: E402
from kb.lint import runner  # noqa: E402

KEYS = {"month", "report", "summary", "done", "decide", "most_urgent", "set_aside", "ingest", "failed_checks"}


class LintCli(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kb(self, *args, code=0):
        r = run_kb("lint", *args, cwd=self.V)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return r.stdout

    def test_json_keys_and_report(self):
        got = json.loads(self.kb("--json"))
        self.assertTrue(KEYS <= set(got), set(got))
        month = date.today().strftime("%Y-%m")
        self.assertEqual((got["month"], got["report"]), (month, f"系統/健檢報告/{month}.md"))
        self.assertTrue((self.V / got["report"]).is_file())
        todo = json.loads(run_kb("cards", "todo", "--json", cwd=self.V).stdout)
        self.assertEqual(got["ingest"]["unsorted"], len(todo["new"]) + len(todo["stale"]))
        self.kb("--json")
        self.assertEqual(len(list((self.V / "系統" / "健檢報告").iterdir())), 1, "同月重寫同一份")

    def test_human_first_line_is_summary(self):
        self.kb("--json")  # 第一次跑才有工作日誌（守門那項從第二次起才查得成），先跑一次讓兩次比的狀態一樣
        got = json.loads(self.kb("--json"))
        out = self.kb().splitlines()
        self.assertEqual(out[0], got["summary"])

    def test_busy(self):
        lock = kio.FileLock(self.V / runner.LOCK_POSIX, timeout=1)
        lock.__enter__()
        try:
            self.assertEqual(self.kb(code=3).strip(), "另一個健檢正在跑，等它做完")
        finally:
            lock.__exit__(None, None, None)

    def test_background_silent(self):
        self.assertEqual(self.kb("--background"), "")
        self.assertTrue((self.V / ".system" / "lint.json").is_file())

    def test_handedit_list_and_done(self):
        t = turn.start(self.V, None, "")["turn"]
        a = pending.add(self.V, "unreadable", ["f-11111111"], "「甲.pdf」讀不到", "檔案壞了", t)
        b = pending.add(self.V, "unreadable", ["f-22222222"], "「乙.pdf」讀不到", "檔案壞了", t)
        # #22（D-263）：手改不再開 handedit 件；升級前留下的 handedit 件 kb lint handedit 照樣列、--done 照樣收，所以直接造一件
        from kb._lib import renders
        md = self.V / "系統" / "待處理.md"
        text = md.read_text(encoding="utf-8")
        la = next(ln for ln in text.splitlines() if "甲.pdf" in ln)
        lb = next(ln for ln in text.splitlines() if "乙.pdf" in ln)
        saved = renders.keep(self.V, "系統/待處理.md", text)
        pending.add_handedit(self.V, "系統/待處理.md", saved, {"checked": [{"id": a, "line": la}], "removed": [{"id": b, "line": lb}],
                                                                "changed_date": [], "other": []}, t)
        got = json.loads(self.kb("handedit", "--json"))
        (item,) = got["items"]
        self.assertEqual(item["file"], "系統/待處理.md")
        self.assertEqual([c["id"] for c in item["checked"]], [a])
        self.assertEqual([c["id"] for c in item["removed"]], [b])
        human = self.kb("handedit")
        self.assertNotIn("p-", human)
        self.assertEqual(self.kb("handedit", "--done", item["pending"]).strip(), "記下了：照你改的做完了")
        self.assertEqual(json.loads(self.kb("handedit", "--json"))["items"], [])
        self.assertEqual(self.kb("handedit", "--done", "p-00000000", code=3).strip(), "沒有這件待處理")


if __name__ == "__main__":
    unittest.main()
