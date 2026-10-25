"""lint runner（驗收 6、13、14、20、22）：分四種（fix 接著做、decide 進待處理且同 key 合成一件、number 進報告、ingest 只數）、
不重複開待處理、一項出錯其他照跑並記 hook-errors.log、鎖、清理搶不到鎖寫一句、關掉不成立的待處理、收起放太久的、
本月第一次背景健檢寫上個月的報告與「報告出來了」那件。"""
import json
import shutil
import types
import unittest
from unittest import mock

from tests import _lint as L
from kb._lib import io as kio  # noqa: E402
from kb._lib import pending, turn  # noqa: E402
from kb.lint import checks, runner, state  # noqa: E402


def fake(name, found=None, boom=False):
    def run(ctx):
        if boom:
            raise RuntimeError("壞了")
        return [dict(f) for f in found or []]
    return types.SimpleNamespace(NAME=name, run=run)


class Runner(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def lint_items(self):
        return [i for i in pending.load(self.V)["items"] if i["kind"] == "lint"]

    def run_with(self, mods, **kw):
        with mock.patch.object(checks, "CHECKS", mods):
            return runner.run(self.V, **kw)

    def test_four_kinds_and_same_key_once(self):
        applied = []
        mods = [fake("修", [runner.finding("a", "fix", "a", "修了", apply=lambda ctx: applied.append(1) or "修好一件")]),
                fake("問", [runner.finding("b", "decide", "same", "要你決定一"), runner.finding("b", "decide", "same", "要你決定一")]),
                fake("數", [runner.finding("c", "number", "c", "", data={"x": 1})]),
                fake("交", [runner.finding("d", "ingest", "todo", "", data={"unsorted": 2})])]
        got = self.run_with(mods)
        self.assertEqual(applied, [1])
        self.assertIn("修好一件", got["done"])
        self.assertEqual([i["key"] for i in self.lint_items()], ["same"])
        self.assertEqual(got["ingest"], {"unsorted": 2})
        self.assertEqual(got["numbers"]["c"], {"x": 1})
        self.run_with(mods)
        self.assertEqual(len(self.lint_items()), 1, "再跑不重複開")

    def test_one_check_failing_does_not_stop_others(self):
        mods = [fake("壞的那項", boom=True), fake("問", [runner.finding("b", "decide", "k", "要你決定")])]
        got = self.run_with(mods)
        self.assertEqual(got["failed_checks"], ["壞的那項"])
        self.assertEqual(len(self.lint_items()), 1)
        log = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8")
        self.assertIn("\tlint\t", log)
        report = (self.V / got["report"]).read_text(encoding="utf-8")
        self.assertIn("壞的那項這項這次沒查成", report)

    def test_skipped_fix_writes_a_line(self):
        def skip(ctx):
            raise runner.Skipped("清理這次沒做：另一個備份、還原或退回正在跑，下週再清")
        got = self.run_with([fake("清", [runner.finding("s", "fix", "clean", "", apply=skip)])])
        self.assertIn("清理這次沒做：另一個備份、還原或退回正在跑，下週再清", got["notes"])
        self.assertIn("清理這次沒做", (self.V / got["report"]).read_text(encoding="utf-8"))

    def test_lock(self):
        lock = kio.FileLock(self.V / runner.LOCK_POSIX, timeout=1)
        lock.__enter__()
        try:
            with self.assertRaises(runner.Busy) as cm:
                self.run_with([])
            self.assertEqual(str(cm.exception), "另一個健檢正在跑，等它做完")
        finally:
            lock.__exit__(None, None, None)

    def test_closes_items_no_longer_true_and_sets_aside_old(self):
        t = turn.start(self.V, None, "")["turn"]
        gone = pending.add(self.V, "unreadable", ["f-00000009"], "「舊.pdf」讀不到", "檔案壞了", t)
        with mock.patch.object(pending, "_now", return_value="2026-08-01T00:00:00"):
            old = pending.add(self.V, "close", ["f-00000008"], "信義王看起來結案了", None, t, entity_ids=["e-5c1d0a7e"])
        got = self.run_with([], today="2026-10-25")
        by = {i["id"]: i for i in pending.load(self.V)["items"]}
        self.assertEqual((by[gone]["status"], by[gone]["how"]), ("done", "健檢確認已不成立"))
        self.assertEqual(by[old]["set_aside"]["by"], "lint")
        self.assertTrue(any("已經不成立" in d for d in got["done"]))
        self.assertTrue(any("先放著" in d for d in got["done"]))

    def test_background_first_of_month_writes_last_month(self):
        t = turn.start(self.V, None, "")["turn"]
        older, _c = pending.add_report(self.V, "2026-08", t)
        state.save(self.V, dict(state.load(self.V), last_report="2026-08", last_background="2026-09-28",
                                month_done=[{"date": "2026-09-20", "text": "清掉 3 個回合備份，空出 1 MB"}]))
        self.run_with([], background=True, today="2026-10-02")
        report = self.V / "系統" / "健檢報告" / "2026-09.md"
        self.assertTrue(report.is_file())
        self.assertIn("清掉 3 個回合備份", report.read_text(encoding="utf-8"))
        items = {i["id"]: i for i in pending.load(self.V)["items"] if i["kind"] == "report"}
        self.assertEqual(items[older]["status"], "done")
        (new,) = [i for i in items.values() if i["status"] == "open"]
        self.assertEqual(new["data"]["month"], "2026-09")
        st = state.load(self.V)
        self.assertEqual((st["last_report"], st["last_background"]), ("2026-09", "2026-10-02"))
        self.assertEqual(st["month_done"], [], "寫完報告換月清空")

    def test_first_ever_background_writes_no_report(self):
        self.run_with([], background=True, today="2026-10-02")
        self.assertFalse((self.V / "系統" / "健檢報告").exists())
        self.assertEqual(state.load(self.V)["last_report"], "2026-09")

    def test_background_uses_its_own_turn(self):
        cur = turn.start(self.V, "sid", "在問別的")["turn"]
        self.run_with([fake("問", [runner.finding("b", "decide", "k", "要你決定")])], background=True)
        self.assertEqual(turn.entries(self.V, cur), [], "背景健檢不寫進對話的回合")
        data = json.loads((self.V / ".system" / "turns" / "current.json").read_text(encoding="utf-8"))
        self.assertEqual(data["turn"], cur)


if __name__ == "__main__":
    unittest.main()
