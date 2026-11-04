"""lint 清單 7（驗收 6）：清理叫前一份的 clean.run（鎖被占、背景整理在跑就跳過）；暫存區份數、綜合卡太長進待處理、知識庫大小。"""
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

    def test_inbox_count(self):
        inbox = self.V / "暫存區"
        inbox.mkdir(exist_ok=True)
        for old in inbox.iterdir():
            old.unlink()
        for n in range(31):
            (inbox / f"{n}.txt").write_text("x", encoding="utf-8")
        (num,) = L.by_kind(sizes.run(L.ctx(self.V)), "number")
        self.assertEqual(num["data"]["inbox"], 31)

    def test_big_read_part_marks_fix_not_ask(self):
        """D-527：read_ranges 超過門檻 → fix（標要更新，原因太長），不開 decide。"""
        L.write_synthesis(self.V, body="## 現況\n- " + "字" * 4100 + "\n")
        found = sizes.run(L.ctx(self.V))
        self.assertEqual(L.by_kind(found, "decide"), [])
        fix = next(f for f in found if f["key"] == "synthesis_big")
        self.assertEqual(fix["kind"], "fix")
        self.assertEqual(fix["data"]["reason"], "太長")
        self.assertEqual(fix["data"]["cards"][0]["path"], L.XINYI_REL)

    def test_events_and_related_files_do_not_count(self):
        """紀事、相關檔再長也不算；現況沒超過就沒有件。"""
        body = "## 現況\n- 進行中\n\n## 紀事\n" + "".join(f"- 2026-01-{n % 28 + 1:02d} {'字' * 50}〔f-{n:08x}〕\n" for n in range(120))
        L.write_synthesis(self.V, body=body)
        self.assertFalse([f for f in sizes.run(L.ctx(self.V)) if f["key"] == "synthesis_big"])


if __name__ == "__main__":
    unittest.main()
