"""lint 清單 3（驗收 3）：守門這週擋幾次、跟上週比；守門最後跑的日期比最近的對話舊兩天以上 → 待處理一件（要服務人員看）。"""
import json
import shutil
import unittest

from tests import _lint as L
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


if __name__ == "__main__":
    unittest.main()
