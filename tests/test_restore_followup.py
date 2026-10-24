"""備份還原與換電腦的測試後修正（design/reports/備份還原與換電腦-測試.md T-1～T-12）：hidden 還原走 exclude 那條路、
還原前快照留著、失敗全退（含中斷）、快照輪替與空間檢查、成功句、別個知識庫、開場 first 記位置、網路路徑、clean 保護 job 回合。"""
import contextlib
import errno
import io
import json
import os
import shutil
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest import mock

from tests import _backup, _cards, _entities
from kb import cli
from kb._lib import backup, clean, env, moved, restore, turn, vault as vault_lib  # noqa: E402
from kb._lib import io as kio  # noqa: E402

SECRET = "紫色大象UNIQ42"
DIARY = "日記本.txt"
SYSTEM = ".system"


def kb(*args):
    saved = kio.LOCK_TIMEOUT
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(list(args))
    kio.LOCK_TIMEOUT = saved
    return code, out.getvalue()


def hits(V, needle):
    out = []
    for p in Path(V).rglob("*"):
        if p.is_file() and not p.name.endswith((".lock", ".zip")):
            try:
                if needle in p.read_text(encoding="utf-8", errors="ignore"):
                    out.append(p.relative_to(V).as_posix())
            except OSError:
                pass
    return sorted(out)


def sources_rows(V):
    data = json.loads((Path(V) / SYSTEM / "sources.json").read_text(encoding="utf-8"))
    return data["sources"][0]["excludes"]


class Hidden(unittest.TestCase):
    """知識庫有一個私人夾（裡面一份檔、一張卡）。備份時還沒排除；之後排除成 hidden（當場清完）；再還原那份舊備份。"""

    def setUp(self):
        self.tmp, self.V, self.raw = _entities.make_entity_vault()
        V = self.V
        self.private = self.raw / "客戶案件" / "私人"
        self.private.mkdir()
        (self.private / DIARY).write_text(f"今天{SECRET}來了", encoding="utf-8")
        _cards.scan_apply(V)
        self.fid = _cards.entry_of(V, "客戶案件/私人/" + DIARY)["id"]
        item = _entities.new_item(V, "客戶案件/私人/" + DIARY)
        p = _cards.card_path(V, item, "王家心情")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_cards.card_text(item, "王家心情", body=f"寫著{SECRET}。〔第 1 段〕\n"), encoding="utf-8", newline="\n")
        self.card_rel = p.relative_to(V).as_posix()
        vault_lib.ensure_vault_id(V)
        self.B = self.tmp / "備份"
        turn.start(V, None, "備份前")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def exclude_hidden(self):
        turn.start(self.V, None, "不要讀私人那夾")
        code, out = kb("folders", "exclude", str(self.private), "--kind", "hidden", "--vault", str(self.V))
        self.assertEqual(code, 0, out)
        self.assertFalse((self.V / self.card_rel).exists())

    def active_under_private(self):
        inv = json.loads((self.V / SYSTEM / "inventory.json").read_text(encoding="utf-8"))
        return [e for e in inv["entries"] if e.get("status") == "active"
                and any("客戶案件/私人/" in loc.get("uri", "") for loc in e.get("locations") or [])]

    def test_old_backup_restore_really_cleans_the_hidden_folder(self):
        """T-1：還原一份比 hidden 排除舊的備份，卡、清冊條目、內文都要真的是 0，不能只標已完成。"""
        z = _backup.make_zip(self.V, self.B)
        self.assertTrue((self.V / self.card_rel).exists())
        self.exclude_hidden()
        got = restore.apply(self.V, str(z))
        self.assertEqual(got["hidden_reapplied"], ["客戶案件/私人"])
        self.assertFalse((self.V / self.card_rel).exists(), "卡拿掉了")
        self.assertEqual(self.active_under_private(), [], "清冊條目不再是 active")
        self.assertEqual(hits(self.V, SECRET), [], "全庫找不到那夾的內文")
        self.assertEqual(hits(self.V, "王家心情"), [])
        rows = sources_rows(self.V)
        self.assertEqual([(r["spec"], r["kind"]) for r in rows], [("私人", "hidden")])
        self.assertNotEqual(rows[0].get("purge"), "pending")

    def test_hidden_is_not_downgraded_to_unused_by_an_old_backup(self):
        """T-4：備份裡同 spec 但 kind 是 unused，現在是 hidden：還原後仍是 hidden、卡不回來。"""
        raw = json.loads((self.V / SYSTEM / "sources.json").read_text(encoding="utf-8"))
        raw["sources"][0]["excludes"] = [{"spec": "私人", "kind": "unused", "reason": "", "added": "2026-10-01"}]
        (self.V / SYSTEM / "sources.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        z = _backup.make_zip(self.V, self.B)
        raw["sources"][0]["excludes"] = []
        (self.V / SYSTEM / "sources.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        self.exclude_hidden()
        restore.apply(self.V, str(z))
        self.assertEqual([(r["spec"], r["kind"]) for r in sources_rows(self.V)], [("私人", "hidden")])
        self.assertFalse((self.V / self.card_rel).exists())
        self.assertEqual(hits(self.V, SECRET), [])

    def test_pre_restore_snapshot_is_kept_when_hidden_were_all_clean(self):
        """使用者定：拍快照時現在的 hidden 都清完了，重清時 purge 跳過這次的還原前快照，「還原不要了」回得去。"""
        z = _backup.make_zip(self.V, self.B)
        self.exclude_hidden()
        old_snap = backup.snapshot(self.V, "upgrade")
        got = restore.apply(self.V, str(z))
        names = [p.name for p in backup.snapshots(self.V)]
        self.assertIsNotNone(got["snapshot"])
        self.assertIn(got["snapshot"], names)
        self.assertNotIn(old_snap.name, names, "別的快照（可能有那夾的卡）照舊刪掉")
        self.assertRegex(got["sentence"], r"說「剛剛的還原不要了」可以回到還原前")
        # 反悔：回到還原前，那夾的東西不會因為快照而回來（快照是排除之後拍的）
        restore.apply(self.V, got["snapshot"])
        self.assertEqual(hits(self.V, SECRET), [])
        self.assertFalse((self.V / self.card_rel).exists())

    def test_pending_hidden_means_all_snapshots_go(self):
        """現在還有沒清完（pending）的 hidden：整包照舊刪，回不去那句要明說。"""
        z = _backup.make_zip(self.V, self.B)
        self.exclude_hidden()
        raw = json.loads((self.V / SYSTEM / "sources.json").read_text(encoding="utf-8"))
        raw["sources"][0]["excludes"][0]["purge"] = "pending"
        (self.V / SYSTEM / "sources.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        got = restore.apply(self.V, str(z))
        self.assertIsNone(got["snapshot"])
        self.assertEqual(list((self.V / SYSTEM / "snapshots").glob("*")), [])
        self.assertIn("回不到還原前", got["sentence"])

    def test_purge_never_marks_done_while_active_entries_remain(self):
        """purge 找不到要清的、但清冊裡還有那夾 active 的條目時不准標完成。"""
        from kb._lib import purge
        raw = json.loads((self.V / SYSTEM / "sources.json").read_text(encoding="utf-8"))
        raw["sources"][0]["excludes"] = [{"spec": "私人", "kind": "hidden", "reason": "", "added": "2026-10-01", "purge": "pending"}]
        (self.V / SYSTEM / "sources.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        self.assertTrue(self.active_under_private())
        got = purge.purge(self.V, "客戶案件", "私人", str(self.private), turn.current(self.V)["turn"])
        self.assertTrue(got["remaining"], "還有 active 的條目，不算清完")


class Failure(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _backup.make_vault()
        self.B = self.tmp / "備份"
        self.zip = _backup.make_zip(self.V, self.B)
        (self.V / SYSTEM / "ledger.tsv").write_text("after\n", encoding="utf-8")
        (self.V / "案子" / "新卡.md").write_text("新\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def tree(self):
        return _backup.tree(self.V, skip=(".system/snapshots", ".system/temp"))

    def flaky(self, exc, at=3, also_undo=False):
        real = restore._rename
        calls = {"n": 0, "undo": 0}

        def fn(src, dst):
            text = str(dst).replace("\\", "/")
            if ".system/temp" not in text:
                calls["n"] += 1
                if calls["n"] == at:
                    raise exc
                if also_undo and calls["n"] > at:
                    calls["undo"] += 1
                    if calls["undo"] == 1:
                        raise PermissionError(13, "拒絕存取", str(dst))
            return real(src, dst)
        return fn

    def test_runtime_error_rolls_everything_back(self):
        before = self.tree()
        with mock.patch.object(restore, "_rename", self.flaky(RuntimeError("boom"))):
            with self.assertRaises(backup.Refused) as cm:
                restore.apply(self.V, str(self.zip))
        self.assertTrue(str(cm.exception).endswith("什麼都沒動"), str(cm.exception))
        self.assertEqual(self.tree(), before)
        self.assertEqual([p.name for p in (self.V / SYSTEM / "temp").iterdir()], ["暫存.txt"])

    def test_keyboard_interrupt_rolls_everything_back_and_propagates(self):
        before = self.tree()
        with mock.patch.object(restore, "_rename", self.flaky(KeyboardInterrupt())):
            with self.assertRaises(KeyboardInterrupt):
                restore.apply(self.V, str(self.zip))
        self.assertEqual(self.tree(), before)
        self.assertEqual([p.name for p in (self.V / SYSTEM / "temp").iterdir()], ["暫存.txt"])

    def test_when_moving_back_fails_restore_old_is_kept_and_named(self):
        with mock.patch.object(restore, "_rename", self.flaky(RuntimeError("boom"), also_undo=True)):
            with self.assertRaises(backup.Refused) as cm:
                restore.apply(self.V, str(self.zip))
        msg = str(cm.exception)
        self.assertIn("restore-old-", msg)
        self.assertNotIn("什麼都沒動", msg)
        olds = list((self.V / SYSTEM / "temp").glob("restore-old-*"))
        self.assertEqual(len(olds), 1)
        self.assertTrue(any(olds[0].iterdir()), "還原前的東西還在那裡")

    def test_failure_removes_the_snapshot_taken_this_time(self):
        older = backup.snapshot(self.V, "upgrade")
        before = sorted(p.name for p in backup.snapshots(self.V))
        with mock.patch.object(restore, "_rename", self.flaky(PermissionError(13, "x", "a.docx"))):
            with self.assertRaises(backup.Refused):
                restore.apply(self.V, str(self.zip))
        self.assertEqual(sorted(p.name for p in backup.snapshots(self.V)), before)
        self.assertTrue(older.exists())

    def test_oserror_sentences_by_errno(self):
        s = restore.oserror_sentence
        self.assertEqual(s(PermissionError(13, "x", "a.docx"), need_mb=5, free_mb=1), "有檔案開著（a.docx），關掉再說一次；什麼都沒動")
        self.assertEqual(s(OSError(errno.ENOSPC, "no space"), need_mb=5, free_mb=1), "空間不夠：要 5 MB，那裡只剩 1 MB")
        self.assertEqual(s(FileNotFoundError(2, "x", "x.zip"), source="x.zip", source_path=Path("x.zip")), "找不到這份：x.zip")

    def test_space_check_before_anything_is_touched(self):
        before = _backup.tree(self.V)
        with mock.patch.object(backup, "_free_bytes", return_value=0):
            with self.assertRaises(backup.Refused) as cm:
                restore.apply(self.V, str(self.zip))
        self.assertRegex(str(cm.exception), r"^空間不夠：要 \d+ MB，那裡只剩 0 MB$")
        self.assertEqual(_backup.tree(self.V), before, "連快照都還沒拍")

    def test_snapshot_source_is_not_deleted_by_rotation(self):
        old = backup.snapshot(self.V, "restore")
        mid = backup.snapshot(self.V, "restore")
        got = restore.apply(self.V, old.name)
        self.assertTrue(old.exists(), "來源快照輪替時不刪")
        self.assertIsNotNone(got["snapshot"])
        self.assertTrue(restore.latest_snapshot(self.V).exists())
        self.assertLessEqual(len(backup.snapshots(self.V)), 3)
        self.assertTrue(mid.exists() or len(backup.snapshots(self.V)) >= 2)

    def test_success_sentence_without_snapshot_says_cannot_undo(self):
        D = self.tmp / "空夾"
        D.mkdir()
        got = restore.apply(D, str(self.zip))
        self.assertIsNone(got["snapshot"])
        self.assertRegex(got["sentence"], r"^已還原到 .+ 的備份；這次沒有還原前的快照，回不到還原前。還原後有 \d+ 份要重新整理。$")

    def test_success_sentence_with_snapshot_keeps_the_old_wording(self):
        got = restore.apply(self.V, str(self.zip))
        self.assertIn("說「剛剛的還原不要了」可以回到還原前。", got["sentence"])


class OtherVault(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _backup.make_vault()
        self.B = self.tmp / "備份"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_other_vault_flag_and_line(self):
        z = _backup.make_zip(self.V, self.B, "vault備份 2026-10-01.zip", vault_id="kb-ffffffff")
        got = restore.check(self.V, str(z))
        self.assertTrue(got["other_vault"])
        self.assertIsNone(got["refuse"])
        self.assertIn("這份是另一個知識庫的備份", "\n".join(restore.lines(got)))
        same = _backup.make_zip(self.V, self.B, "vault備份 2026-10-02.zip")
        got2 = restore.check(self.V, str(same))
        self.assertFalse(got2["other_vault"])
        self.assertNotIn("另一個知識庫", "\n".join(restore.lines(got2)))

    def test_other_vault_is_still_allowed(self):
        z = _backup.make_zip(self.V, self.B, "vault備份 2026-10-01.zip", vault_id="kb-ffffffff")
        restore.apply(self.V, str(z))

    def test_empty_folder_is_not_other_vault(self):
        D = self.tmp / "空夾"
        D.mkdir()
        z = _backup.make_zip(self.V, self.B)
        self.assertFalse(restore.check(D, str(z))["other_vault"])


class FirstPlace(unittest.TestCase):
    """T-2：first（這台與別台都沒有位置紀錄）時默默記位置、補 vault.json；換位置、換電腦時不動。"""

    def setUp(self):
        self.tmp, self.V, self.raw = _backup.make_vault()
        (self.V / SYSTEM / "vault.json").unlink()
        self.B = self.tmp / "備份"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def here(self):
        return Path(os.path.realpath(str(self.V))).as_posix()

    def test_note_place_records_only_when_first(self):
        self.assertEqual(moved.note_place(self.V), "first")
        self.assertEqual(env.vault_path(self.V), self.here())
        self.assertTrue(vault_lib.vault_id(self.V).startswith("kb-"))
        env.set_vault_path(self.V, "D:/lin/舊的位置")
        self.assertEqual(moved.note_place(self.V), "moved")
        self.assertEqual(env.vault_path(self.V), "D:/lin/舊的位置", "換了位置時不覆蓋")

    def test_note_place_leaves_new_machine_alone(self):
        (self.V / SYSTEM / "env.json").write_text(json.dumps(
            {"schema_version": 1, "machines": {"OTHER-PC": {"vault_path": "D:/lin/知識庫"}}}), encoding="utf-8")
        self.assertEqual(moved.note_place(self.V), "new_machine")
        self.assertIsNone(env.vault_path(self.V))

    def test_commands_of_this_topic_record_the_place_on_first_run(self):
        cwd = os.getcwd()
        os.chdir(self.V)
        try:
            code, out = kb("backup", "--to", str(self.B))
            self.assertEqual(code, 0, out)
            self.assertEqual(env.vault_path(self.V), self.here())
            (self.V / SYSTEM / "env.json").write_text(json.dumps(
                {"schema_version": 1, "machines": {}}), encoding="utf-8")
            code, out = kb("versions", "clean")
            self.assertEqual(code, 0, out)
            self.assertEqual(env.vault_path(self.V), self.here())
            (self.V / SYSTEM / "env.json").write_text(json.dumps(
                {"schema_version": 1, "machines": {}}), encoding="utf-8")
            z = next(self.B.glob("*.zip"))
            code, out = kb("restore", "apply", str(z))
            self.assertEqual(code, 0, out)
            self.assertEqual(env.vault_path(self.V), self.here())
        finally:
            os.chdir(cwd)


class Misc(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _backup.make_vault()
        self.B = self.tmp / "備份"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pre_1980_mtime_does_not_break_backup_or_snapshot(self):
        os.utime(self.V / "案子" / "說明.txt", (0, 0))
        got = backup.backup(self.V, to=str(self.B))
        self.assertTrue(Path(got["path"]).is_file())
        self.assertTrue(backup.snapshot(self.V, "restore").is_file())

    def test_file_vanishing_between_walk_and_write_is_skipped(self):
        real = backup.collect

        def with_ghost(vault):
            files, empty, total = real(vault)
            return files + [(Path(vault) / "案子" / "不存在的檔.txt", "案子/不存在的檔.txt")], empty, total
        with mock.patch.object(backup, "collect", with_ghost):
            got = backup.backup(self.V, to=str(self.B))
        meta = backup.read_meta(Path(got["path"]))
        with zipfile.ZipFile(got["path"]) as z:
            names = [n for n in z.namelist() if not n.endswith("/") and n != backup.META_NAME]
        self.assertNotIn("案子/不存在的檔.txt", names)
        self.assertEqual(meta["files"], len(names), "meta 的份數是真的寫進去的")

    def test_list_does_not_run_testzip(self):
        z = _backup.make_zip(self.V, self.B)
        with mock.patch.object(zipfile.ZipFile, "testzip", side_effect=AssertionError("list 不該讀完整份")):
            got = backup.list_backups(None, extra_dir=str(self.B))
        self.assertEqual([g["name"] for g in got], [z.name])
        self.assertTrue(got[0]["usable"])

    def test_list_still_marks_a_corrupt_central_directory(self):
        z = _backup.make_zip(self.V, self.B)
        data = z.read_bytes()
        z.write_bytes(data[:-30])
        got = backup.list_backups(None, extra_dir=str(self.B))
        self.assertFalse(got[0]["usable"])

    def test_check_and_apply_still_run_the_full_test(self):
        z = _backup.make_zip(self.V, self.B)
        data = bytearray(z.read_bytes())
        data[len(data) // 3] ^= 0xFF
        bad = self.B / "vault備份 2026-10-09.zip"
        bad.write_bytes(bytes(data))
        got = restore.check(self.V, str(bad))
        self.assertTrue(got["refuse"].startswith("這份備份壞了（"))

    def test_network_paths_are_refused(self):
        sentence = "備份要放在這台電腦的資料夾或隨身碟；網路上的位置請先對應成磁碟機"
        for to in ("//server/share/備份", "\\\\server\\share\\備份", "//localhost/C$/x", "//server@SSL/DavWWWRoot/x",
                   "\\\\server@SSL\\DavWWWRoot\\x"):
            with self.subTest(to=to):
                self.assertEqual(backup.check(self.V, to)["refuse"], sentence)
                with self.assertRaises(backup.Refused) as cm:
                    backup.backup(self.V, to=to)
                self.assertEqual(str(cm.exception), sentence)
        self.assertFalse(self.B.exists())

    def test_local_cloud_folders_and_drive_letters_are_accepted(self):
        sync = self.tmp / "OneDrive" / "備份"
        self.assertIsNone(backup.check(self.V, str(sync))["refuse"])
        self.assertIsNone(backup.check(self.V, str(self.tmp / "Dropbox" / "備份"))["refuse"])
        self.assertIsNone(backup.check(self.V, str(self.B))["refuse"])

    def test_snapshot_rotate_false_keeps_all_until_rotated(self):
        for _ in range(3):
            backup.snapshot(self.V, "restore", rotate=False)
        self.assertEqual(len(backup.snapshots(self.V)), 3)
        keep = backup.snapshots(self.V)[-1]
        backup.rotate_snapshots(self.V, protect=(keep,))
        left = backup.snapshots(self.V)
        self.assertIn(keep, left)
        self.assertEqual(len(left), 3 if keep not in backup.snapshots(self.V)[:2] else 2)

    def test_clean_keeps_open_job_turns(self):
        ids = _backup.put_turns(self.V, [90, 80] + [1] * 30)
        (self.V / SYSTEM / "batches.json").write_text(json.dumps({
            "schema_version": 1, "jobs": [{"job": "j-1", "session_id": "s", "status": "open", "turn": ids[0],
                                           "created": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")},
                                          {"job": "j-0", "session_id": "s", "status": "closed", "turn": ids[1]}],
            "batches": [], "agents": []}), encoding="utf-8")
        clean.run(self.V)
        left = sorted(p.name for p in (self.V / SYSTEM / "versions").iterdir())
        self.assertIn(ids[0], left, "還開著的 job 的回合不清")
        self.assertNotIn(ids[1], left, "已關的 job 的回合照清")


if __name__ == "__main__":
    unittest.main()
