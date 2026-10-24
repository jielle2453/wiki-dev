"""備份還原與換電腦 第二輪重測（design/reports/備份還原與換電腦-測試-2.md）N-1～N-6 的修正：網路路徑混寫斜線、cp -rt 併旗標、
重清 hidden 的輸出與換入成功之後的例外、FileNotFoundError 的說法、clean 保護 job 回合加閒置判斷、備份在寫 zip 之前先記位置。"""
import errno
import json
import os
import shutil
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from tests import _backup
from tests._guard_fixture import make_vault as make_guard_vault
from kb import guard
from kb._lib import backup, clean, env, restore  # noqa: E402

SYSTEM = ".system"
NETWORK = "備份要放在這台電腦的資料夾或隨身碟；網路上的位置請先對應成磁碟機"


class NetworkPaths(unittest.TestCase):
    """N-1：先把 \\ 換成 / 再判斷開頭是不是 //；\\\\?\\C:\\ 這種本機長路徑前綴放行，\\\\?\\UNC\\ 照擋。"""

    def test_mixed_slashes_are_network(self):
        for to in ("\\/host/share", "/\\host\\share", "\\/localhost/C$/x", "/\\localhost\\C$\\x",
                   "\\\\?\\UNC\\host\\share\\x", "//?/UNC/host/share/x", "\\\\host\\share", "//host/share"):
            with self.subTest(to=to):
                self.assertTrue(backup.is_network_path(to), to)

    def test_local_long_path_prefix_and_drives_are_not(self):
        for to in ("\\\\?\\C:\\Users\\lin\\備份", "//?/C:/work/lin/備份", "\\\\.\\C:\\備份", "D:\\備份", "D:/備份",
                   "/c/work/lin/備份", "備份", "./備份"):
            with self.subTest(to=to):
                self.assertFalse(backup.is_network_path(to), to)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _backup.make_vault()
        self.B = self.tmp / "備份"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def refused(self, fn, *a, **kw):
        with self.assertRaises(backup.Refused) as cm:
            fn(*a, **kw)
        return str(cm.exception)

    def test_check_and_backup_refuse_the_mixed_slash_forms(self):
        for to in ("\\/localhost/C$/x", "/\\localhost\\C$\\x"):
            with self.subTest(to=to):
                self.assertEqual(backup.check(self.V, to)["refuse"], NETWORK)
                self.assertEqual(self.refused(backup.backup, self.V, to=to), NETWORK)

    def test_local_long_path_prefix_is_not_refused_as_network(self):
        got = backup.check(self.V, "\\\\?\\" + str(self.B))
        self.assertNotEqual(got["refuse"], NETWORK)


class Hidden(Base):
    """N-3：重清 hidden 被擋住時兩行不能矛盾；換入成功之後的例外不能讓 apply 在寫成功句之前就丟出去。"""

    def make_zip(self):
        return _backup.make_zip(self.V, self.B)

    def test_blocked_by_synthesis_is_not_reported_as_cleaned(self):
        raw = json.loads((self.V / SYSTEM / "sources.json").read_text(encoding="utf-8"))
        raw["sources"][0]["excludes"] = [{"spec": "私人", "kind": "hidden", "reason": "", "added": "2026-10-01",
                                          "purge": "2026-10-02"}]
        z = self.make_zip()  # 備份裡就有這條 hidden；現在把它拿掉再還原不會重清，所以用現在有、備份沒有的組合：
        (self.V / SYSTEM / "sources.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        with mock.patch("kb._lib.purge.blocking", return_value=["信義王"]):
            got = restore.apply(self.V, str(z))
        self.assertEqual(got["hidden_reapplied"], [], "被擋住的不算重清過")
        self.assertIn("信義王", got["hidden_left"])

    def test_exception_after_the_swap_still_reports_the_restore(self):
        z = self.make_zip()
        (self.V / "案子" / "新卡.md").write_text("新\n", encoding="utf-8")
        with mock.patch.object(restore, "_run_init", side_effect=RuntimeError("boom")):
            got = restore.apply(self.V, str(z))
        self.assertTrue(got["sentence"].startswith("已還原到 "))
        self.assertTrue(got["not_finished"])
        self.assertIn("kb init", "\n".join(got["not_finished"]))
        self.assertFalse((self.V / "案子" / "新卡.md").exists(), "換入已經完成")

    def test_hidden_step_exception_is_reported_not_raised(self):
        raw = json.loads((self.V / SYSTEM / "sources.json").read_text(encoding="utf-8"))
        z = self.make_zip()
        raw["sources"][0]["excludes"] = [{"spec": "私人", "kind": "hidden", "reason": "", "added": "2026-10-01",
                                          "purge": "2026-10-02"}]
        (self.V / SYSTEM / "sources.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        with mock.patch("kb.folders._snapshot_status", side_effect=ValueError("清冊讀不到")):
            got = restore.apply(self.V, str(z))
        self.assertTrue(got["sentence"].startswith("已還原到 "))
        self.assertIn("私人", got["hidden_left"])
        self.assertEqual(got["hidden_reapplied"], [])


class Errors(unittest.TestCase):
    def test_file_not_found_says_missing_backup_only_for_the_source(self):
        s = restore.oserror_sentence
        src = Path(r"C:\備份\vault備份 2026-10-01.zip")
        self.assertEqual(s(FileNotFoundError(2, "x", str(src)), source="vault備份 2026-10-01.zip", source_path=src),
                         "找不到這份：vault備份 2026-10-01.zip")
        other = s(FileNotFoundError(2, "x", r"C:\kb\案子\某檔.md"), source="vault備份 2026-10-01.zip", source_path=src)
        self.assertEqual(other, "還原沒有做成：FileNotFoundError；什麼都沒動")
        self.assertEqual(s(FileNotFoundError(2, "x")), "還原沒有做成：FileNotFoundError；什麼都沒動")


class OpenJobs(Base):
    """N-5：clean 保護還開著的 job 的回合，加閒置判斷（跟 card_batch_idle_minutes 同一套）；當機留下的 job 不永遠保護。"""

    def put(self, ids, created_min_ago, batch_seen_min_ago=None, batch_created_min_ago=None):
        now = datetime.now().replace(microsecond=0)
        fmt = "%Y-%m-%dT%H:%M:%S"
        job = {"job": "j-1", "session_id": "s", "status": "open", "turn": ids[0],
               "created": (now - timedelta(minutes=created_min_ago)).strftime(fmt)}
        batches = []
        if batch_created_min_ago is not None:
            b = {"kind": "cards", "items": ["f-1"], "status": "open", "job": "j-1",
                 "created": (now - timedelta(minutes=batch_created_min_ago)).strftime(fmt)}
            if batch_seen_min_ago is not None:
                b["last_seen"] = (now - timedelta(minutes=batch_seen_min_ago)).strftime(fmt)
            batches.append(b)
        (self.V / SYSTEM / "batches.json").write_text(json.dumps(
            {"schema_version": 1, "jobs": [job], "batches": batches, "agents": []}), encoding="utf-8")

    def left(self):
        return sorted(p.name for p in (self.V / SYSTEM / "versions").iterdir())

    def test_active_job_is_protected(self):
        ids = _backup.put_turns(self.V, [90, 80] + [1] * 30)
        self.put(ids, created_min_ago=5, batch_created_min_ago=5, batch_seen_min_ago=1)
        clean.run(self.V)
        self.assertIn(ids[0], self.left())

    def test_crashed_job_with_idle_batch_is_not_protected_forever(self):
        ids = _backup.put_turns(self.V, [90, 80] + [1] * 30)
        self.put(ids, created_min_ago=300, batch_created_min_ago=300, batch_seen_min_ago=200)
        clean.run(self.V)
        self.assertNotIn(ids[0], self.left())

    def test_new_job_without_batches_yet_is_protected_old_one_is_not(self):
        ids = _backup.put_turns(self.V, [90, 80] + [1] * 30)
        self.put(ids, created_min_ago=1)
        clean.run(self.V)
        self.assertIn(ids[0], self.left())
        self.put(ids, created_min_ago=600)
        clean.run(self.V)
        self.assertNotIn(ids[0], self.left())


class FirstBackup(Base):
    """N-6：kb backup 在寫 zip 之前就先記位置，讓第一份備份裡也有位置紀錄；拒絕時不寫。"""

    def test_first_backup_contains_the_place(self):
        self.assertFalse((self.V / SYSTEM / "env.json").exists())
        got = backup.backup(self.V, to=str(self.B))
        with zipfile.ZipFile(got["path"]) as z:
            data = json.loads(z.read(".system/env.json").decode("utf-8"))
        here = Path(os.path.realpath(str(self.V))).as_posix()
        self.assertEqual(data["machines"][env.machine_name()]["vault_path"], here)

    def test_refusal_does_not_record_the_place(self):
        self.assertEqual(self.refused(backup.backup, self.V, to=str(self.V / "AI 產出" / "備份")), "備份不能放在知識庫裡面")
        self.assertFalse((self.V / SYSTEM / "env.json").exists())
        self.assertEqual(self.refused(backup.backup, self.V), "還沒說備份要放哪")
        self.assertFalse((self.V / SYSTEM / "env.json").exists())


class CpBundledFlags(unittest.TestCase):
    """N-2：cp -rt、cp -at 這種 -t 併在短選項裡的寫法，理由句也要是搬家那句。"""

    def setUp(self):
        self.tmp, self.V, self.raw = make_guard_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def decide(self, command, tool="Bash"):
        d = guard.decide({"tool_name": tool, "tool_input": {"command": command}, "cwd": str(self.V),
                          "permission_mode": "default"})
        return d.decision, d.reason_code

    def test_bundled_t_flag_gives_the_move_sentence(self):
        v = str(self.V).replace("\\", "/")
        for cmd in (f"cp -rt /d/x '{v}'", f"cp -at /d/x '{v}'", f"cp -r -t /d/x '{v}'", f"cp -rvt /d/x '{v}'"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.decide(cmd), ("deny", "vault_move"))

    def test_put_into_the_vault_root_is_still_the_old_sentence(self):
        v = str(self.V).replace("\\", "/")
        decision, code = self.decide(f"cp -rt '{v}' a.txt")
        self.assertEqual(decision, "deny")
        self.assertNotEqual(code, "vault_move")

    def test_capital_T_means_the_opposite_and_stays_a_normal_destination(self):
        v = str(self.V).replace("\\", "/")
        decision, code = self.decide(f"cp -rT a '{v}'")
        self.assertNotEqual(code, "vault_move")


if __name__ == "__main__":
    unittest.main()
