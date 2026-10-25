"""_lib/clean（備份還原與換電腦 要做的事 3，D-207、D-056、D-211）：回合備份與快照放太久的清掉。"""
import json
import shutil
import unittest
from pathlib import Path

from tests import _backup
from kb._lib import backup, clean  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _backup.make_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def turn_dirs(self):
        root = self.V / ".system" / "versions"
        return sorted(p.name for p in root.iterdir()) if root.is_dir() else []


class Plan(Base):
    def test_old_ones_go_but_recent_stay(self):
        _backup.put_turns(self.V, [40] * 25 + [1] * 25)
        got = clean.run(self.V)
        self.assertEqual(got["turns_removed"], 25)
        self.assertEqual(len(self.turn_dirs()), 25)
        self.assertGreater(got["freed_bytes"], 0)

    def test_over_count_cleans_down_to_keep_turns(self):
        _backup.put_turns(self.V, [1] * 210)
        got = clean.run(self.V)
        self.assertEqual(got["turns_removed"], 10)
        self.assertEqual(len(self.turn_dirs()), 200)

    def test_minimum_twenty_always_kept(self):
        _backup.put_turns(self.V, [40] * 15)
        got = clean.run(self.V)
        self.assertEqual(got["turns_removed"], 0)
        self.assertEqual(len(self.turn_dirs()), 15)
        _backup.put_turns(self.V, [60] * 10, prefix="u")
        got = clean.run(self.V)
        self.assertEqual(len(self.turn_dirs()), 20)
        self.assertEqual(got["turns_removed"], 5)

    def test_removes_oldest_first(self):
        ids = _backup.put_turns(self.V, [90, 80, 70] + [40] * 20)
        clean.run(self.V)
        left = self.turn_dirs()
        self.assertEqual(len(left), 20)
        for old in ids[:3]:
            self.assertNotIn(old, left)

    def test_current_and_unfinished_turns_stay(self):
        ids = _backup.put_turns(self.V, [90, 80] + [1] * 30)
        (self.V / ".system" / "turns").mkdir()
        cur = {"turn": ids[0], "session_id": "s1", "done": False}
        (self.V / ".system" / "turns" / "s1.json").write_text(json.dumps(cur), encoding="utf-8")
        (self.V / ".system" / "turns" / "current.json").write_text(json.dumps(
            {"turn": ids[1], "session_id": "", "done": True}), encoding="utf-8")
        got = clean.run(self.V)
        left = self.turn_dirs()
        self.assertIn(ids[0], left)
        self.assertIn(ids[1], left)
        self.assertEqual(got["turns_removed"], 0)

    def test_check_matches_real_run_and_changes_nothing(self):
        _backup.put_turns(self.V, [40] * 25 + [1] * 25)
        for _ in range(3):
            backup.snapshot(self.V, "restore")
        shutil.copy(next((self.V / ".system" / "snapshots").glob("快照*.zip")), self.V / ".system" / "snapshots" / "快照 2020-01-01 0000（還原前）.zip")
        before = _backup.tree(self.V)
        planned = clean.run(self.V, check=True)
        self.assertEqual(_backup.tree(self.V), before)
        real = clean.run(self.V)
        self.assertEqual(planned, real)
        self.assertEqual(real["snapshots_removed"], 1)

    def test_snapshots_over_two_cleaned(self):
        folder = self.V / ".system" / "snapshots"
        for i in range(4):
            shutil.copy(backup.snapshot(self.V, "restore"), folder / f"快照 2020-01-0{i + 1} 0000（升級前）.zip")
        got = clean.run(self.V)
        self.assertEqual(len(list(folder.glob("快照*.zip"))), 2)
        self.assertGreaterEqual(got["snapshots_removed"], 1)

    def test_earliest_is_oldest_left(self):
        ids = _backup.put_turns(self.V, [40] * 5 + [3] * 20, prompt="第")
        got = clean.run(self.V)
        self.assertEqual(got["turns_removed"], 5)
        self.assertEqual(got["earliest"]["prompt_head"], "第5")
        self.assertTrue(got["earliest"]["time"].startswith(ids[5][:4]))

    def test_nothing_to_clean(self):
        got = clean.run(self.V)
        self.assertEqual((got["turns_removed"], got["snapshots_removed"], got["freed_bytes"]), (0, 0, 0))
        self.assertIsNone(got["earliest"])

    def test_lock_busy_refused(self):
        from kb._lib import io as kio
        with kio.FileLock(self.V / ".system" / "revert"):
            with self.assertRaises(backup.Refused) as cm:
                clean.run(self.V)
        self.assertEqual(str(cm.exception), "另一個備份、還原或退回正在跑，等它做完")


if __name__ == "__main__":
    unittest.main()
