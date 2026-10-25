"""lint 清單 7（驗收 6）：清理叫前一份的 clean.run（鎖被占、背景整理在跑就跳過）；收件匣份數、綜合卡太長進待處理、知識庫大小。"""
import shutil
import unittest
from unittest import mock

from tests import _lint as L
from kb._lib import backup, clean  # noqa: E402
from kb.lint import runner  # noqa: E402
from kb.lint.checks import sizes  # noqa: E402


class Sizes(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def clean_fix(self, found):
        return next(f for f in found if f["kind"] == "fix" and f["key"] == "clean")

    def test_clean_calls_clean_run(self):
        got = {"turns_removed": 40, "earliest": None, "snapshots_removed": 0, "freed_bytes": 12 * 1024 * 1024}
        with mock.patch.object(clean, "run", return_value=got) as run:
            text = self.clean_fix(sizes.run(L.ctx(self.V)))["apply"](L.ctx(self.V))
        run.assert_called_once()
        self.assertEqual(text, "清掉 40 個回合備份，空出 12 MB")

    def test_clean_nothing_to_do_is_silent(self):
        got = {"turns_removed": 0, "earliest": None, "snapshots_removed": 0, "freed_bytes": 0}
        with mock.patch.object(clean, "run", return_value=got):
            self.assertIsNone(self.clean_fix(sizes.run(L.ctx(self.V)))["apply"](L.ctx(self.V)))

    def test_lock_busy_skips(self):
        with mock.patch.object(clean, "run", side_effect=backup.Refused(backup.BUSY)):
            with self.assertRaises(runner.Skipped):
                self.clean_fix(sizes.run(L.ctx(self.V)))["apply"](L.ctx(self.V))

    def test_background_batch_running_skips(self):
        with mock.patch.object(backup, "batch_running", return_value=True), mock.patch.object(clean, "run") as run:
            with self.assertRaises(runner.Skipped):
                self.clean_fix(sizes.run(L.ctx(self.V)))["apply"](L.ctx(self.V))
        run.assert_not_called()

    def test_inbox_and_big_synthesis(self):
        inbox = self.V / "收件匣"
        inbox.mkdir(exist_ok=True)
        for old in inbox.iterdir():
            old.unlink()
        for n in range(31):
            (inbox / f"{n}.txt").write_text("x", encoding="utf-8")
        L.write_synthesis(self.V, body="## 現況\n" + "- " + "字" * 13000 + "\n")
        found = sizes.run(L.ctx(self.V))
        (num,) = L.by_kind(found, "number")
        self.assertEqual(num["data"]["inbox"], 31)
        self.assertGreater(num["data"]["vault_bytes"], 13000)
        (dec,) = L.by_kind(found, "decide")
        self.assertEqual(dec["key"], f"synthesis_big:{L.XINYI_REL}")


if __name__ == "__main__":
    unittest.main()
