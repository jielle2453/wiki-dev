"""lint 清單 3（驗收 3）：守門這週擋幾次、跟上週比；守門最後跑的日期比最近的對話舊兩天以上 → 待處理一件（要服務人員看）。"""
import json
import os
import shutil
import unittest
from unittest import mock

from tests import _lint as L
from kb._lib import ledger, pending  # noqa: E402
from kb.lint import runner  # noqa: E402
from kb.lint.checks import guard  # noqa: E402

TODAY = "2026-10-25"
HEADER = "time\ttool\tdecision\tzone\treason_code\tpath_or_command_head\n"


class Guard(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()
        sysd = self.V / ".system"
        rows = [f"2026-10-{d}T10:00:00\tBash\tdeny\tZ2\tx\techo\n" for d in ("21", "23", "24")]
        rows += ["2026-10-15T10:00:00\tBash\tdeny\tZ2\tx\techo\n", "2026-10-24T11:00:00\tRead\tunparsed\tZ2\tx\tls\n"]
        (sysd / "ledger.tsv").write_text(HEADER + "".join(rows), encoding="utf-8")
        (sysd / "journal").mkdir(exist_ok=True)
        row = {"schema_version": 1, "kind": "turn", "turn": "20261025-090000-abcd", "time": "2026-10-25T09:00:00", "done": True}
        (sysd / "journal" / "2026-10.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
        (sysd / "guard-status").mkdir(exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def status(self, day):
        (self.V / ".system" / "guard-status" / "PC.json").write_text(json.dumps({"date": day}), encoding="utf-8")

    def test_counts_and_stale(self):
        self.status("2026-10-23")
        found = guard.run(L.ctx(self.V, today=TODAY))
        (num,) = L.by_kind(found, "number")
        self.assertEqual((num["data"]["denied_week"], num["data"]["denied_prev"]), (3, 1))
        (dec,) = L.by_kind(found, "decide")
        self.assertEqual(dec["key"], "guard_stale")
        self.assertNotIn("p-", dec["text"])

    def test_recent_status_is_fine(self):
        self.status("2026-10-24")
        self.assertEqual(L.kinds(guard.run(L.ctx(self.V, today=TODAY))), ["number"])

    def turns(self, *days):
        """換掉工作日誌：每天一段對話（按月分檔）。"""
        for p in (self.V / ".system" / "journal").glob("*.jsonl"):
            p.unlink()
        for d in days:
            row = {"schema_version": 1, "kind": "turn", "turn": d.replace("-", "") + "-090000-abcd", "time": d + "T09:00:00",
                   "done": True}
            with open(self.V / ".system" / "journal" / f"{d[:7]}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")

    def test_new_vault_no_status_yet_is_fine(self):
        """#63：新庫第一次開場，背景健檢比守門第一次寫 guard-status 早，不開「守門好像沒在跑」。"""
        self.turns(TODAY)
        self.assertEqual(L.kinds(guard.run(L.ctx(self.V, today=TODAY))), ["number"])
        self.turns("2026-10-24", TODAY)  # 最早的對話是昨天：還不到 STALE_DAYS 天
        self.assertEqual(L.kinds(guard.run(L.ctx(self.V, today=TODAY))), ["number"])

    def test_no_status_since_old_conversation_is_stale(self):
        """有對話、最早一段在 STALE_DAYS 天以前、guard-status 一直沒有：照舊開（最早那段在上個月的檔）。"""
        self.turns("2026-09-30", TODAY)
        (dec,) = L.by_kind(guard.run(L.ctx(self.V, today=TODAY)), "decide")
        self.assertEqual((dec["key"], dec["data"]["last"]), ("guard_stale", None))
        self.turns("2026-10-23")
        self.assertEqual(L.by_kind(guard.run(L.ctx(self.V, today=TODAY)), "decide")[0]["key"], "guard_stale")


class OpeningCloses(unittest.TestCase):
    """#63：已經開出去的 guard_stale，守門有紀錄之後下一次（這台今天第一次的）開場就關，不等背景健檢。"""

    def setUp(self):
        self.tmp, self.V, self.raw = L.make()
        self.t = runner._program_turn(self.V)
        pending.add_lint(self.V, "guard_stale", "守門好像沒在跑", {"last": None}, self.t, check="guard")
        env = mock.patch.dict(os.environ, {runner.NO_BACKGROUND_ENV: "1"})
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def item(self):
        (i,) = [i for i in pending.load(self.V)["items"] if i.get("key") == "guard_stale"]
        return i

    def test_closes_once_guard_has_record(self):
        runner.opening(self.V)
        self.assertEqual(self.item()["status"], "open", "守門還沒紀錄不關")
        d = self.V / ledger.STATUS_DIR_REL
        d.mkdir(parents=True, exist_ok=True)
        (d / "PC.json").write_text(json.dumps({"date": TODAY}), encoding="utf-8")
        runner.opening(self.V)
        self.assertEqual((self.item()["status"], self.item()["how"]), ("done", pending.LINT_GONE_HOW))

    def test_unreadable_pending_does_not_break_opening(self):
        with mock.patch.object(pending, "load", side_effect=ValueError("待處理不是物件")):
            self.assertFalse(runner.opening(self.V))
        log = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8")
        self.assertIn("開場關「守門好像沒在跑」出錯：ValueError", log)


if __name__ == "__main__":
    unittest.main()
