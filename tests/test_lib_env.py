"""_lib/env：.system/env.json 按機器記「找不到的來源已報過」（D-021 補、D-094 補）。報過／清掉、壞 JSON 重建、機器名。"""
import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from tests._guard_fixture import SCRIPTS  # noqa: F401  加 sys.path
from kb._lib import env  # noqa: E402


class Env(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kbenv-"))
        self.V = self.tmp / "vault"
        (self.V / ".system").mkdir(parents=True)
        self.path = self.V / ".system" / "env.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def data(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_not_reported_when_no_file(self):
        self.assertFalse(env.missing_reported(self.V, "src-3f9a"))
        self.assertFalse(self.path.exists())

    def test_mark_then_reported_with_today_under_this_machine(self):
        env.mark_missing(self.V, ["src-3f9a", "報價夾"])
        self.assertTrue(env.missing_reported(self.V, "src-3f9a"))
        self.assertTrue(env.missing_reported(self.V, "報價夾"))
        self.assertFalse(env.missing_reported(self.V, "src-0000"))
        data = self.data()
        self.assertEqual(data["schema_version"], 1)
        marks = data["machines"][env.machine_name()]["missing_sources_reported"]
        self.assertEqual(marks, {"src-3f9a": date.today().isoformat(), "報價夾": date.today().isoformat()})

    def test_mark_keeps_first_date(self):
        self.path.write_text(json.dumps({"schema_version": 1, "machines": {env.machine_name(): {
            "missing_sources_reported": {"src-3f9a": "2026-10-01"}}}}), encoding="utf-8")
        env.mark_missing(self.V, ["src-3f9a"])
        self.assertEqual(self.data()["machines"][env.machine_name()]["missing_sources_reported"]["src-3f9a"], "2026-10-01")

    def test_clear_then_not_reported(self):
        env.mark_missing(self.V, ["src-3f9a", "src-7c21"])
        env.clear_missing(self.V, ["src-3f9a"])
        self.assertFalse(env.missing_reported(self.V, "src-3f9a"))
        self.assertTrue(env.missing_reported(self.V, "src-7c21"))

    def test_clear_without_marks_writes_nothing(self):
        env.clear_missing(self.V, ["src-3f9a"])
        self.assertFalse(self.path.exists())

    def test_other_machine_marks_are_separate(self):
        self.path.write_text(json.dumps({"schema_version": 1, "machines": {"OTHER-PC": {
            "missing_sources_reported": {"src-3f9a": "2026-10-01"}}}}), encoding="utf-8")
        self.assertFalse(env.missing_reported(self.V, "src-3f9a"))
        env.mark_missing(self.V, ["src-3f9a"])
        env.clear_missing(self.V, ["src-3f9a"])
        self.assertEqual(self.data()["machines"]["OTHER-PC"]["missing_sources_reported"], {"src-3f9a": "2026-10-01"})

    def test_broken_json_is_rebuilt(self):
        self.path.write_text("{not json", encoding="utf-8")
        self.assertFalse(env.missing_reported(self.V, "src-3f9a"))
        env.mark_missing(self.V, ["src-3f9a"])
        self.assertTrue(env.missing_reported(self.V, "src-3f9a"))
        self.assertEqual(self.data()["schema_version"], 1)

    def test_wrong_shape_is_rebuilt(self):
        self.path.write_text(json.dumps({"schema_version": 1, "machines": []}), encoding="utf-8")
        env.mark_missing(self.V, ["src-3f9a"])
        self.assertTrue(env.missing_reported(self.V, "src-3f9a"))

    def test_machine_name_falls_back_to_unknown(self):
        with mock.patch("socket.gethostname", return_value=""):
            self.assertEqual(env.machine_name(), "unknown")
        with mock.patch("socket.gethostname", return_value="DESKTOP-ABC"):
            self.assertEqual(env.machine_name(), "DESKTOP-ABC")

    def test_machine_name_is_hostname_same_as_platform_node(self):
        """裁定 24：改用 socket.gethostname（platform.node 走 WMI，有負載 1.4～1.7 s）；值要跟 platform.node 一樣，
        不然流水檔會把同一台當成另一台。真的去叫，不模擬。"""
        import platform
        import socket
        self.assertEqual(socket.gethostname(), platform.node())
        self.assertEqual(env.machine_name(), platform.node())
        with mock.patch("platform.node", side_effect=AssertionError("不該叫 platform.node")):
            env.machine_name()

    def test_machine_name_oserror_same_as_platform_node(self):
        """裁定 24：gethostname 丟 OSError 時跟 platform.node 一樣當 ''，machine_name 照舊回 unknown。"""
        with mock.patch("socket.gethostname", side_effect=OSError("no host")):
            self.assertEqual(env.machine_name(), "unknown")


if __name__ == "__main__":
    unittest.main()


class MachineRecords(unittest.TestCase):
    """備份還原與換電腦第 6 點：每台電腦多 vault_path、backup_dir（選填欄，schema 照 1）；互不覆蓋。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kbenv-"))
        self.V = self.tmp / "vault"
        (self.V / ".system").mkdir(parents=True)
        self.path = self.V / ".system" / "env.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def data(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_nothing_recorded_returns_none(self):
        self.assertIsNone(env.vault_path(self.V))
        self.assertIsNone(env.backup_dir(self.V))
        self.assertEqual(env.other_machines(self.V), [])
        self.assertFalse(self.path.exists())

    def test_set_and_read_back_this_machine(self):
        env.set_vault_path(self.V, "D:/知識庫")
        env.set_backup_dir(self.V, "E:/備份")
        self.assertEqual(env.vault_path(self.V), "D:/知識庫")
        self.assertEqual(env.backup_dir(self.V), "E:/備份")
        data = self.data()
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["machines"][env.machine_name()]["vault_path"], "D:/知識庫")

    def test_marking_missing_keeps_paths_and_the_other_way_round(self):
        env.set_vault_path(self.V, "D:/知識庫")
        env.set_backup_dir(self.V, "E:/備份")
        env.mark_missing(self.V, ["src-3f9a"])
        self.assertEqual(env.vault_path(self.V), "D:/知識庫")
        self.assertEqual(env.backup_dir(self.V), "E:/備份")
        env.set_vault_path(self.V, "F:/知識庫")
        self.assertTrue(env.missing_reported(self.V, "src-3f9a"))
        env.clear_missing(self.V, ["src-3f9a"])
        self.assertEqual(env.vault_path(self.V), "F:/知識庫")
        self.assertEqual(env.backup_dir(self.V), "E:/備份")

    def test_other_machines_lists_names_with_records(self):
        self.path.write_text(json.dumps({"schema_version": 1, "machines": {
            "LIN-PC": {"vault_path": "C:/a"}, env.machine_name(): {"vault_path": "D:/b"},
            "OLD": {"missing_sources_reported": {}}, "BAD": "x"}}), encoding="utf-8")
        self.assertEqual(sorted(env.other_machines(self.V)), ["LIN-PC", "OLD"])
        self.assertEqual(env.vault_path(self.V), "D:/b")
        self.assertEqual(env.vault_paths_elsewhere(self.V), ["C:/a"])

    def test_broken_file_reads_as_nothing(self):
        self.path.write_text("{壞", encoding="utf-8")
        self.assertIsNone(env.vault_path(self.V))
        self.assertEqual(env.other_machines(self.V), [])


class UpdateCheck(unittest.TestCase):
    """升級打包 要做的事 6：每台電腦多 update_check（背景查新版的結果），跟其他欄各管各的。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kbenv-"))
        self.V = self.tmp / "vault"
        (self.V / ".system").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_none_when_never_checked(self):
        self.assertIsNone(env.update_check(self.V))
        self.assertFalse((self.V / ".system" / "env.json").exists())

    def test_set_then_read_under_this_machine(self):
        got = {"date": "2026-10-23", "latest": "0.21.0", "kind": "minor", "allowed": True,
               "note": "日程可以匯出成 Excel", "auto_patched": None, "error": None}
        env.set_update_check(self.V, got)
        self.assertEqual(env.update_check(self.V), got)
        data = json.loads((self.V / ".system" / "env.json").read_text(encoding="utf-8"))
        self.assertEqual(data["machines"][env.machine_name()]["update_check"], got)

    def test_independent_of_other_fields(self):
        env.set_vault_path(self.V, "D:/知識庫")
        env.mark_missing(self.V, ["src-1"])
        env.set_update_check(self.V, {"date": "2026-10-23"})
        self.assertEqual(env.vault_path(self.V), "D:/知識庫")
        self.assertTrue(env.missing_reported(self.V, "src-1"))
        env.set_vault_path(self.V, "E:/新位置")
        self.assertEqual(env.update_check(self.V), {"date": "2026-10-23"})

    def test_other_machine_not_read(self):
        (self.V / ".system" / "env.json").write_text(json.dumps(
            {"schema_version": 1, "machines": {"別台": {"update_check": {"date": "2026-10-01"}}}}), encoding="utf-8")
        self.assertIsNone(env.update_check(self.V))

    def test_garbage_value_reads_as_none(self):
        (self.V / ".system" / "env.json").write_text(json.dumps(
            {"schema_version": 1, "machines": {env.machine_name(): {"update_check": "壞掉"}}}), encoding="utf-8")
        self.assertIsNone(env.update_check(self.V))
