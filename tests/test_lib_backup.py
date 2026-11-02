"""_lib/backup（備份還原與換電腦 要做的事 1，D-203、D-204、D-211）：zip 內容與排除、命名、留 3 份、拒絕、快照、list。"""
import json
import shutil
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests import _backup
from kb._lib import backup, env, vault as vault_lib  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _backup.make_vault()
        self.B = self.tmp / "備份"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def names(self, zpath):
        with zipfile.ZipFile(zpath) as z:
            return z.namelist()

    def refused(self, fn, *a, **kw):
        with self.assertRaises(backup.Refused) as cm:
            fn(*a, **kw)
        return str(cm.exception)


class WriteZip(Base):
    def test_contents_exclusions_and_empty_dirs(self):
        z = _backup.make_zip(self.V, self.B)
        names = self.names(z)
        self.assertIn("wiki-with-willy-backup.json", names)
        self.assertIn(".system/sources.json", names)
        self.assertIn("案子/信義王/信義王.md", names)
        self.assertIn("案子/空夾/", names)
        self.assertFalse([n for n in names if n.startswith(".system/temp/") or n.startswith(".system/snapshots/")])
        self.assertFalse([n for n in names if n.endswith(".lock")])
        self.assertFalse([n for n in names if n.endswith(".tmp")])
        self.assertEqual(list(self.B.glob("*.tmp")), [])

    def test_meta_fields_and_counts(self):
        z = _backup.make_zip(self.V, self.B)
        meta = backup.read_meta(z)
        for key in ("schema_version", "kind", "reason", "created", "plugin_version", "machine", "vault_name",
                    "vault_id", "files", "bytes"):
            self.assertIn(key, meta, key)
        self.assertEqual(meta["kind"], "backup")
        self.assertEqual(meta["vault_id"], vault_lib.vault_id(self.V))
        real = [n for n in self.names(z) if not n.endswith("/") and n != "wiki-with-willy-backup.json"]
        self.assertEqual(meta["files"], len(real))
        self.assertGreater(meta["bytes"], 0)

    def test_read_meta_none_when_missing_or_not_zip(self):
        self.B.mkdir()
        (self.B / "a.zip").write_bytes(b"not a zip")
        with zipfile.ZipFile(self.B / "b.zip", "w") as z:
            z.writestr("x.txt", "x")
        self.assertIsNone(backup.read_meta(self.B / "a.zip"))
        self.assertIsNone(backup.read_meta(self.B / "b.zip"))

    def test_verify_ok_returns_meta(self):
        z = _backup.make_zip(self.V, self.B)
        self.assertEqual(backup.verify(z)["kind"], "backup")

    def test_verify_refusals(self):
        self.B.mkdir()
        with zipfile.ZipFile(self.B / "nometa.zip", "w") as z:
            z.writestr("x.txt", "x")
        self.assertEqual(self.refused(backup.verify, self.B / "nometa.zip"), "這份不是 wiki-with-willy 的備份")
        good = _backup.make_zip(self.V, self.B, "vault備份 2026-10-02.zip")
        data = bytearray(good.read_bytes())
        data[len(data) // 3] ^= 0xFF
        bad = self.B / "壞.zip"
        bad.write_bytes(bytes(data))
        msg = self.refused(backup.verify, bad)
        self.assertTrue(msg.startswith("這份備份壞了（") and msg.endswith("），換一份"), msg)
        for evil in ("../x.txt", "C:/x.txt", "/abs/x.txt", "a/../../x.txt", "D:\\x.txt"):
            p = self.B / "evil.zip"
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("wiki-with-willy-backup.json", json.dumps(
                    {"schema_version": 1, "kind": "backup", "plugin_version": "0.1.0", "vault_id": "kb-00000000"}))
                z.writestr(evil, "x")
            self.assertEqual(self.refused(backup.verify, p), "這份備份壞了（裡面有不安全的路徑），換一份", evil)
            p.unlink()

    def test_verify_newer_plugin_version(self):
        z = _backup.make_zip(self.V, self.B, plugin_version="99.0.0")
        msg = self.refused(backup.verify, z)
        self.assertEqual(msg, "這份備份是比較新的版本（99.0.0）做的，先升級再還原")


class Backup(Base):
    def test_need_to_when_nothing_recorded(self):
        got = backup.check(self.V)
        self.assertTrue(got["need_to"])
        self.assertIsNone(got["to"])
        self.assertIsNone(got["refuse"])
        self.assertEqual(self.refused(backup.backup, self.V), "還沒說備份要放哪")

    def test_backup_to_records_dir_and_second_run_reuses_it(self):
        got = backup.backup(self.V, to=str(self.B))
        zpath = Path(got["path"])
        self.assertTrue(zpath.is_file())
        self.assertEqual(zpath.parent.resolve(), self.B.resolve())
        self.assertRegex(zpath.name, r"^vault備份 \d{4}-\d{2}-\d{2}\.zip$")
        self.assertEqual(env.backup_dir(self.V), self.B.resolve().as_posix())
        self.assertEqual(got["removed"], [])
        got2 = backup.backup(self.V)  # 不帶 --to 照用
        self.assertTrue(got2["path"].endswith(" (2).zip"), got2["path"])

    def test_check_does_not_write(self):
        before = _backup.tree(self.V)
        got = backup.check(self.V, to=str(self.B))
        self.assertEqual(got["to"], self.B.resolve().as_posix())
        self.assertFalse(got["need_to"])
        self.assertGreater(got["files"], 3)
        self.assertGreater(got["bytes"], 0)
        self.assertFalse(got["sync_folder"])
        self.assertEqual(_backup.tree(self.V), before)
        self.assertFalse(self.B.exists())
        self.assertIsNone(env.backup_dir(self.V))

    def test_keeps_three_and_only_ours(self):
        for day in ("2026-08-01", "2026-09-01", "2026-09-15"):
            _backup.make_zip(self.V, self.B, f"vault備份 {day}.zip", created=f"{day}T10:00:00")
        _backup.make_zip(self.V, self.B, "別人備份 2026-01-01.zip", vault_id="kb-ffffffff", created="2026-01-01T10:00:00")
        with zipfile.ZipFile(self.B / "我的壓縮檔.zip", "w") as z:
            z.writestr("a.txt", "a")
        (self.B / "備註.txt").write_text("hi", encoding="utf-8")
        got = backup.backup(self.V, to=str(self.B))
        self.assertEqual(got["removed"], ["vault備份 2026-08-01.zip"])
        left = sorted(p.name for p in self.B.iterdir())
        self.assertIn("別人備份 2026-01-01.zip", left)
        self.assertIn("我的壓縮檔.zip", left)
        self.assertIn("備註.txt", left)
        mine = [n for n in left if n.startswith("vault備份")]
        self.assertEqual(len(mine), 3)
        self.assertNotIn("vault備份 2026-08-01.zip", mine)

    def test_keep_function_counts_only_qualified(self):
        for day in ("2026-01-01", "2026-01-02"):
            _backup.make_zip(self.V, self.B, f"vault備份 {day}.zip")
        self.assertEqual(backup.keep(self.B, vault_lib.vault_id(self.V), 1), ["vault備份 2026-01-01.zip"])

    def test_refusals_in_vault_in_source_unwritable_space(self):
        inside = self.V / "暫存區" / "備份"
        self.assertEqual(self.refused(backup.backup, self.V, to=str(inside)), "備份不能放在知識庫裡面")
        self.assertFalse(inside.exists())
        src = self.raw / "客戶案件" / "備份"
        self.assertEqual(self.refused(backup.backup, self.V, to=str(src)),
                         "備份不能放在登記的資料夾「客戶案件」裡，不然會被當成新檔整理")
        with mock.patch.object(backup, "_can_write", return_value=False):
            self.assertEqual(self.refused(backup.backup, self.V, to=str(self.B)),
                             f"那個位置寫不進去：{self.B.resolve().as_posix()}")
        with mock.patch.object(backup, "_free_bytes", return_value=0):
            msg = self.refused(backup.backup, self.V, to=str(self.B))
        self.assertRegex(msg, r"^空間不夠：要 \d+ MB，那裡只剩 0 MB$")
        self.assertEqual(list(self.B.glob("*")) if self.B.exists() else [], [])

    def test_check_reports_refuse_sentence(self):
        got = backup.check(self.V, to=str(self.V / "暫存區" / "備份"))
        self.assertEqual(got["refuse"], "備份不能放在知識庫裡面")

    def test_batch_running_blocks_unless_idle(self):
        _backup.put_batch(self.V, created_min_ago=1)
        self.assertEqual(self.refused(backup.backup, self.V, to=str(self.B)), "背景整理還在跑，先停掉再備份")
        _backup.put_batch(self.V, created_min_ago=5, seen_min_ago=15)  # 視窗當掉留下的舊批次不擋
        self.assertIn("path", backup.backup(self.V, to=str(self.B)))

    def test_lock_busy(self):
        from kb._lib import io as kio
        with kio.FileLock(self.V / ".system" / "revert"):
            self.assertEqual(self.refused(backup.backup, self.V, to=str(self.B)),
                             "另一個備份、還原或退回正在跑，等它做完")
        self.assertEqual(list(self.B.glob("*.tmp")) if self.B.exists() else [], [])

    def test_no_tmp_left_when_verify_fails(self):
        with mock.patch.object(backup, "verify", side_effect=backup.Refused("這份備份壞了（x），換一份")):
            with self.assertRaises(backup.Refused):
                backup.backup(self.V, to=str(self.B))
        self.assertEqual(list(self.B.glob("*")), [])

    def test_onedrive_marks_sync_folder(self):
        sync = self.tmp / "OneDrive"
        with mock.patch.dict("os.environ", {"OneDrive": str(sync)}):
            got = backup.check(self.V, to=str(sync / "備份"))
        self.assertTrue(got["sync_folder"])

    def test_old_vault_without_id_gets_one(self):
        (self.V / ".system" / "vault.json").unlink()
        got = backup.backup(self.V, to=str(self.B))
        self.assertTrue(vault_lib.vault_id(self.V).startswith("kb-"))
        self.assertEqual(backup.read_meta(Path(got["path"]))["vault_id"], vault_lib.vault_id(self.V))

    def test_backup_runs_clean_afterwards(self):
        _backup.put_turns(self.V, [40] * 25 + [1] * 25)
        got = backup.backup(self.V, to=str(self.B))
        self.assertEqual(got["clean"]["turns_removed"], 25)


class Snapshot(Base):
    def test_snapshot_goes_to_system_snapshots_with_reason(self):
        got = backup.snapshot(self.V, "restore")
        self.assertEqual(got.parent, self.V / ".system" / "snapshots")
        self.assertRegex(got.name, r"^快照 \d{4}-\d{2}-\d{2} \d{4}（還原前）\.zip$")
        meta = backup.read_meta(got)
        self.assertEqual((meta["kind"], meta["reason"]), ("snapshot", "restore"))
        up = backup.snapshot(self.V, "upgrade")
        self.assertIn("（升級前）", up.name)

    def test_snapshot_keeps_only_two(self):
        d = self.V / ".system" / "snapshots"
        for _ in range(4):
            backup.snapshot(self.V, "restore")
        self.assertEqual(len(list(d.glob("快照*.zip"))), 2)
        self.assertEqual(len(list(d.glob("*.tmp"))), 0)

    def test_snapshot_excludes_older_snapshots_and_temp(self):
        backup.snapshot(self.V, "restore")
        got = backup.snapshot(self.V, "restore")
        self.assertFalse([n for n in self.names(got) if n.startswith(".system/snapshots/")])


class ListBackups(Base):
    def test_lists_qualified_with_usable_and_why(self):
        _backup.make_zip(self.V, self.B, "vault備份 2026-10-01.zip", created="2026-10-01T09:00:00")
        _backup.make_zip(self.V, self.B, "vault備份 2026-10-05.zip", created="2026-10-05T09:00:00", machine="OTHER")
        _backup.make_zip(self.V, self.B, "vault備份 2026-10-06.zip", plugin_version="99.0.0")
        (self.B / "vault備份 2026-10-07.zip").write_bytes(b"junk")
        (self.B / "不相干.zip").write_bytes(b"junk")
        snap = backup.snapshot(self.V, "restore")
        got = backup.list_backups(self.V, extra_dir=str(self.B))
        by_name = {g["name"]: g for g in got}
        self.assertNotIn("不相干.zip", by_name)
        self.assertEqual(by_name["vault備份 2026-10-05.zip"]["machine"], "OTHER")
        self.assertTrue(by_name["vault備份 2026-10-01.zip"]["usable"])
        self.assertFalse(by_name["vault備份 2026-10-06.zip"]["usable"])
        self.assertIn("99.0.0", by_name["vault備份 2026-10-06.zip"]["why"])
        self.assertFalse(by_name["vault備份 2026-10-07.zip"]["usable"])
        self.assertEqual(by_name[snap.name]["kind"], "snapshot")
        for g in got:
            for key in ("name", "path", "kind", "created", "machine", "plugin_version", "bytes", "usable", "why"):
                self.assertIn(key, g)
        created = [g["created"] or "" for g in got]
        self.assertEqual(created, sorted(created, reverse=True))

    def test_uses_recorded_dir_and_dedupes(self):
        backup.backup(self.V, to=str(self.B))
        got = backup.list_backups(self.V, extra_dir=str(self.B))
        self.assertEqual(len([g for g in got if g["kind"] == "backup"]), 1)

    def test_without_vault_only_from_dir(self):
        z = _backup.make_zip(self.V, self.B)
        got = backup.list_backups(None, extra_dir=str(self.B))
        self.assertEqual([g["name"] for g in got], [z.name])


if __name__ == "__main__":
    unittest.main()
