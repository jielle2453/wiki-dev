"""日程重複（D-501，specs/2026-10-26-重複日程.md 驗收 1～8）：add／edit 的 repeat、會議提醒過了自動移（讀在記憶體、寫回記歷程）、
到期 done 才移、月底與 2/29、期間平移、cancel 整串、改日期換錨點、日程.md 與匯出的 repeat。"""
import json
import shutil
import unittest
from pathlib import Path

from tests import _entities as E
from tests.test_lib_agenda import item, put, read
from kb._lib import agenda, turn  # noqa: E402

TODAY = "2026-10-21"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        self.t = turn.start(self.V, None, "")["turn"]
        self._today = agenda._today
        self.today = TODAY
        agenda._today = lambda: self.today

    def tearDown(self):
        agenda._today = self._today
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add(self, **kw):
        args = dict(kind="reminder", date="2026-10-25", text="生日", entities=["信義王"])
        args.update(kw)
        return agenda.add(self.V, args.pop("kind"), args.pop("date"), args.pop("text"), args.pop("entities"), self.t, **args)[0]


class NextAfter(unittest.TestCase):
    def nxt(self, every, anchor, day):
        return agenda.next_after({"every": every, "from": anchor}, day)

    def test_each_period(self):
        self.assertEqual(self.nxt("year", "2026-03-15", "2026-03-15"), "2027-03-15")
        self.assertEqual(self.nxt("year", "2026-03-15", "2026-03-14"), "2026-03-15")
        self.assertEqual(self.nxt("month", "2026-01-10", "2026-05-20"), "2026-06-10")
        self.assertEqual(self.nxt("week", "2026-10-19", "2026-10-21"), "2026-10-26")
        self.assertEqual(self.nxt("year", "2020-03-15", "2026-10-21"), "2027-03-15")

    def test_month_end_does_not_drift(self):
        self.assertEqual(self.nxt("month", "2026-01-31", "2026-01-31"), "2026-02-28")
        self.assertEqual(self.nxt("month", "2026-01-31", "2026-02-28"), "2026-03-31")
        self.assertEqual(self.nxt("month", "2028-01-31", "2028-01-31"), "2028-02-29")

    def test_leap_day_yearly(self):
        self.assertEqual(self.nxt("year", "2024-02-29", "2024-02-29"), "2025-02-28")
        self.assertEqual(self.nxt("year", "2024-02-29", "2027-03-01"), "2028-02-29")


class AddEdit(Base):
    def test_add_repeat_stores_anchor(self):
        it = self.add(repeat="每年")
        self.assertEqual(it["repeat"], {"every": "year", "from": "2026-10-25"})
        self.assertNotIn("repeat", self.add(text="寄卡片"))

    def test_bad_value_refused(self):
        with self.assertRaises(agenda.AgendaRefused) as cm:
            self.add(repeat="每天")
        self.assertEqual(str(cm.exception), agenda.REPEAT_MSG)

    def test_edit_date_moves_anchor_and_no_repeat_removes(self):
        it = self.add(repeat="每月")
        it = agenda.edit(self.V, it["id"], self.t, date="2026-10-28")
        self.assertEqual(it["repeat"], {"every": "month", "from": "2026-10-28"})
        self.assertEqual(it["history"][-1]["change"], "date 2026-10-25 → 2026-10-28")
        it = agenda.edit(self.V, it["id"], self.t, repeat="不重複")
        self.assertNotIn("repeat", it)
        self.assertIn("repeat 每月 → ", it["history"][-1]["change"])

    def test_edit_sets_repeat_from_current_date(self):
        it = agenda.edit(self.V, self.add()["id"], self.t, repeat="每週")
        self.assertEqual(it["repeat"], {"every": "week", "from": "2026-10-25"})


class Roll(Base):
    def test_passing_kinds_roll_in_memory_then_on_write(self):
        put(self.V, [item(id="a-1", kind="reminder", date="2026-03-15", repeat={"every": "year", "from": "2025-03-15"}),
                     item(id="a-2", kind="meeting", date="2026-10-19", repeat={"every": "week", "from": "2026-10-05"}),
                     item(id="a-3", kind="meeting", date="2026-10-21", repeat={"every": "week", "from": "2026-10-21"})])
        got = {i["id"]: i["date"] for i in agenda.load(self.V)["items"]}
        self.assertEqual(got, {"a-1": "2027-03-15", "a-2": "2026-10-26", "a-3": "2026-10-21"})
        self.assertEqual(read(self.V)[0]["date"], "2026-03-15")  # 讀不寫
        self.add(text="別的事")
        disk = {i["id"]: i for i in read(self.V)}
        self.assertEqual(disk["a-1"]["date"], "2027-03-15")
        self.assertEqual(disk["a-1"]["history"][-1]["change"], "重複：2026-03-15 過了，移到 2027-03-15")
        self.assertEqual(disk["a-1"]["history"][-1]["by"], "program")
        self.assertEqual(disk["a-3"]["history"], [])

    def test_tracked_kinds_stay_overdue_until_done(self):
        put(self.V, [item(id="a-1", kind="deadline", date="2026-10-01", repeat={"every": "year", "from": "2026-10-01"})])
        self.assertEqual(agenda.counts(self.V, agenda.load(self.V))["overdue"], 1)
        it = agenda.set_status(self.V, "a-1", "done", self.t)
        self.assertEqual((it["date"], it["status"]), ("2027-10-01", "open"))
        self.assertEqual(it["history"][-1]["change"], "完成 2026-10-01 那次，下次 2027-10-01")
        self.assertEqual(agenda.counts(self.V, agenda.load(self.V))["overdue"], 0)

    def test_period_done_shifts_start(self):
        put(self.V, [item(id="a-1", kind="period", start="2026-10-01", date="2026-10-05", entities=["信義王"],
                          repeat={"every": "month", "from": "2026-10-05"})])
        it = agenda.set_status(self.V, "a-1", "done", self.t)
        self.assertEqual((it["start"], it["date"], it["status"], it["ended"]), ("2026-11-01", "2026-11-05", "open", None))

    def test_cancel_and_closed_do_not_roll(self):
        put(self.V, [item(id="a-1", kind="reminder", date="2026-03-15", repeat={"every": "year", "from": "2026-03-15"},
                          status="cancelled")])
        self.assertEqual(agenda.load(self.V)["items"][0]["date"], "2026-03-15")
        put(self.V, [item(id="a-2", kind="reminder", date="2026-11-15", repeat={"every": "year", "from": "2026-11-15"})])
        it = agenda.set_status(self.V, "a-2", "cancelled", self.t)
        self.assertEqual((it["date"], it["status"]), ("2026-11-15", "cancelled"))


class Views(Base):
    def test_md_line_and_export(self):
        it = self.add(repeat="每年", lead_days=3)
        md = (Path(self.V) / agenda.MD_POSIX).read_text(encoding="utf-8")
        self.assertIn("生日（[[案子/信義王/信義王|信義王]]）（每年）", md)
        row = agenda.export_payload(self.V, agenda.load(self.V))["items"][0]
        self.assertEqual(row["repeat"], "year")
        self.assertEqual(row["fp"], agenda.item_fp(dict(it, repeat=None)))  # repeat 不進指紋


if __name__ == "__main__":
    unittest.main()


class Wording(Base):
    def test_no_repeat_shown_as_words(self):  # 測試 T-1
        aid = self.add(repeat="每月")["id"]
        msg = agenda.edit(self.V, aid, self.t, repeat=agenda.NO_REPEAT)
        log = read(self.V)
        self.assertIn("repeat 每月 → 不重複", json.dumps(log, ensure_ascii=False) + str(msg))
        self.assertEqual(agenda.show(None, "repeat"), "不重複")
        self.assertEqual(agenda.show(None), "")

    def test_overdue_question_for_repeat(self):  # 測試 T-2：重複的不給整串改日期，「這次不用」走 done
        from kb._lib import plan
        it = {"id": "a-1", "kind": "deadline", "date": "2026-11-10", "text": "月繳B", "entities": [], "status": "open",
              "repeat": {"every": "month", "from": "2026-11-10"}}
        ask = plan._overdue(it)
        self.assertIn("（每月）過了", ask["question"])
        self.assertEqual([(r["label"], r["do"]) for r in ask["results"]], [
            ("完成了", ["kb agenda done a-1"]), ("這次不用，跳到下一次", ["kb agenda done a-1"]),
            ("以後都不要了", ["kb agenda cancel a-1"]), ("還沒，下次再問", [])])
