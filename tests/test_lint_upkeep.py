"""lint 驗收 13、15、9 補：關掉不成立的待處理另三種（寫法不同的卡不在、要確認結案的實體已結案、程式動到的檔不在清冊）；
pending.json 遷移後說退回回得去；kb cards redo --ids 一次標幾張。"""
import json
import shutil
import types
import unittest
from unittest import mock

from tests import _entities as E
from tests import _lint as L
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import entities, inventory, pending, turn  # noqa: E402
from kb.lint import checks, runner  # noqa: E402


class CloseUntrue(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()
        self.t = turn.start(self.V, None, "")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_lint(self):
        with mock.patch.object(checks, "CHECKS", [types.SimpleNamespace(NAME="空", run=lambda ctx: [])]):
            return runner.run(self.V)

    def status(self, pid):
        return next(i for i in pending.load(self.V)["items"] if i["id"] == pid)

    def test_three_more_kinds(self):
        card = L.write_card(self.V, E.QUOTE, "信義王報價")
        conflict, _c = pending.add_conflict(self.V, [card, "f-00000077"], "報價與合約寫法不同", self.t)
        keep, _c = pending.add_conflict(self.V, [card, card], "同一張自己比", self.t)
        p = self.V / entities.ENTITIES_POSIX
        data = json.loads(p.read_text(encoding="utf-8"))
        for e in data["entities"]:
            if e["name"] == "大安陳":
                e["progress"] = "closed"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        closed = pending.add(self.V, "close", ["f-00000066"], "大安陳看起來結案了", None, self.t, entity_ids=[E.DAAN])
        touched = pending.add(self.V, "script_touched", ["f-00000055"], "程式動到了「甲.xlsx」", None, self.t)
        real = inventory.load(self.V)["entries"][0]["id"]
        still = pending.add(self.V, "script_touched", [real], "程式動到了「乙.xlsx」", None, self.t)
        self.run_lint()
        for pid in (conflict["id"], closed, touched):
            self.assertEqual((self.status(pid)["status"], self.status(pid)["how"]), ("done", runner.NOT_TRUE_HOW), pid)
        for pid in (keep["id"], still):
            self.assertEqual(self.status(pid)["status"], "open", pid)


class MigrationRevert(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_v1_to_v2_and_back(self):
        from kb._lib import migrate
        p = self.V / pending.PENDING_POSIX
        item = {"id": "p-aaaa0001", "kind": "unreadable", "file_ids": ["f-1"], "entity_ids": [], "text": "x", "reason": None,
                "created": "2026-10-01T00:00:00", "created_turn": "t", "status": "open", "resolved": None, "how": None}
        raw = json.dumps({"schema_version": 1, "items": [item]}, ensure_ascii=False)
        p.write_text(raw, encoding="utf-8")
        turn.start(self.V, None, "")
        migrate.apply(self.V, turn.current(self.V)["turn"])
        self.assertEqual(json.loads(p.read_text(encoding="utf-8"))["schema_version"], 2)
        r = run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(p.read_text(encoding="utf-8"), raw)


class RedoIds(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_marks_several(self):
        a = L.write_card(self.V, E.QUOTE, "信義王報價")
        b = L.write_card(self.V, E.ESTIMATE, "內湖李估價")
        r = run_kb("cards", "redo", "--ids", f"{a},{b}", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.splitlines()[0]), (0, "已標成要重做：2 張卡，下次整理時照原檔重寫"), r.stderr)
        marks = {e["id"]: e.get("redo") for e in inventory.load(self.V)["entries"]}
        self.assertTrue(marks[a] and marks[b])
        r = run_kb("cards", "redo", "--ids", "f-00000000", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "沒有寫好的卡可以重做"))
        r = run_kb("cards", "redo", a, "--ids", b, cwd=self.V)
        self.assertEqual(r.returncode, 3)


if __name__ == "__main__":
    unittest.main()
