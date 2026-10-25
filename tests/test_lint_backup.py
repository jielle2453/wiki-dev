"""lint 清單 8（驗收 7）：沒有任何備份 → 建議下一步那句；回合備份夾寫不進去 → 待處理一件。"""
import shutil
import unittest
from unittest import mock

from tests import _lint as L
from kb._lib import backup as backup_lib  # noqa: E402
from kb.lint.checks import backup  # noqa: E402


class Backup(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_never_backed_up(self):
        (num,) = backup.run(L.ctx(self.V))
        self.assertIsNone(num["data"]["last_backup_days"])
        self.assertEqual(num["data"]["suggest"], "還沒備份過，說「幫我備份」就好")

    def test_old_backup(self):
        rows = [{"kind": "snapshot", "created": "2026-10-24T10:00:00", "usable": True},
                {"kind": "backup", "created": "2026-09-15T10:00:00", "usable": True}]
        with mock.patch.object(backup_lib, "list_backups", return_value=rows):
            (num,) = backup.run(L.ctx(self.V, today="2026-10-25"))
        self.assertEqual(num["data"]["last_backup_days"], 40)
        self.assertEqual(num["data"]["suggest"], "上次備份是 40 天前，說「幫我備份」就好")

    def test_recent_backup_no_suggestion(self):
        rows = [{"kind": "backup", "created": "2026-10-20T10:00:00", "usable": True}]
        with mock.patch.object(backup_lib, "list_backups", return_value=rows):
            (num,) = backup.run(L.ctx(self.V, today="2026-10-25"))
        self.assertIsNone(num["data"]["suggest"])

    def test_versions_not_writable(self):
        with mock.patch.object(backup, "_writable", return_value=False):
            found = backup.run(L.ctx(self.V))
        (dec,) = L.by_kind(found, "decide")
        self.assertEqual(dec["key"], "versions_unwritable")


if __name__ == "__main__":
    unittest.main()
