"""kb backup、kb versions clean、kb output links 黑箱（備份還原與換電腦 驗收 1～6、20）：subprocess 跑 kb.py，cwd 在 vault。"""
import json
import os
import shutil
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path

from tests import _backup
from tests._guard_fixture import KB, ROOT
from kb._lib import env, inventory  # noqa: E402


def run_kb(*args, cwd):
    envv = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(KB), *args], capture_output=True, text=True,
                          encoding="utf-8", cwd=str(cwd), env=envv)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _backup.make_vault()
        self.B = self.tmp / "備份"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class Backup(Base):
    def test_check_json_without_recorded_place(self):
        r = run_kb("backup", "--check", "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout)
        self.assertTrue(got["need_to"])
        self.assertIsNone(got["to"])
        self.assertEqual(set(got), {"to", "need_to", "files", "bytes", "sync_folder", "refuse"})

    def test_plain_backup_without_place_says_it_and_exits_3(self):
        r = run_kb("backup", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "還沒說備份要放哪"))

    def test_backup_to_writes_zip_and_remembers_place(self):
        r = run_kb("backup", "--to", str(self.B), cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        zips = list(self.B.glob("*.zip"))
        self.assertEqual(len(zips), 1)
        line = r.stdout.splitlines()[0]
        self.assertRegex(line, r"^備份好了：.+\.zip（\d+ 份、\d+ MB）；那裡留最近 3 份。$")
        with zipfile.ZipFile(zips[0]) as z:
            names = z.namelist()
            meta = json.loads(z.read("wiki-with-willy-backup.json").decode("utf-8"))
        for key in ("schema_version", "kind", "reason", "created", "plugin_version", "machine", "vault_name",
                    "vault_id", "files", "bytes"):
            self.assertIn(key, meta)
        self.assertFalse([n for n in names if n.startswith((".system/temp/", ".system/snapshots/")) or n.endswith(".lock")])
        self.assertIn("案子/空夾/", names)
        self.assertEqual(env.backup_dir(self.V), self.B.resolve().as_posix())
        r2 = run_kb("backup", "--json", cwd=self.V)  # 不帶 --to 照用
        self.assertEqual(r2.returncode, 0, r2.stderr)
        got = json.loads(r2.stdout)
        self.assertEqual(set(got) & {"path", "files", "bytes", "removed", "clean"}, {"path", "files", "bytes", "removed", "clean"})
        self.assertTrue(got["path"].endswith(" (2).zip"))

    def test_fourth_backup_removes_oldest_and_leaves_others(self):
        for day in ("2026-08-01", "2026-09-01", "2026-09-15"):
            _backup.make_zip(self.V, self.B, f"vault備份 {day}.zip", created=f"{day}T10:00:00")
        other = _backup.make_zip(self.V, self.B, "別人備份 2026-01-01.zip", vault_id="kb-ffffffff")
        mine = self.B / "我的.zip"
        with zipfile.ZipFile(mine, "w") as z:
            z.writestr("a.txt", "a")
        r = run_kb("backup", "--to", str(self.B), "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["removed"], ["vault備份 2026-08-01.zip"])
        self.assertTrue(other.exists() and mine.exists())

    def test_refusals_exact_and_no_tmp_left(self):
        cases = [
            (["--to", str(self.V / "AI 產出" / "備份")], "備份不能放在知識庫裡面"),
            (["--to", str(self.raw / "客戶案件" / "備份")], "備份不能放在登記的資料夾「客戶案件」裡，不然會被當成新檔整理"),
        ]
        for args, want in cases:
            r = run_kb("backup", *args, cwd=self.V)
            self.assertEqual((r.returncode, r.stdout.strip()), (3, want), args)
        _backup.put_batch(self.V)
        r = run_kb("backup", "--to", str(self.B), cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "背景整理還在跑，先停掉再備份"))
        _backup.put_batch(self.V, created_min_ago=5, seen_min_ago=15)
        from kb._lib import io as kio
        with kio.FileLock(self.V / ".system" / "revert"):
            r = run_kb("backup", "--to", str(self.B), cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "另一個備份、還原或退回正在跑，等它做完"))
        self.assertEqual(list(self.B.glob("*")) if self.B.exists() else [], [])

    def test_not_a_vault(self):
        r = run_kb("backup", "--to", str(self.B), cwd=self.tmp)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "這裡不是知識庫"))

    def test_success_runs_clean_and_says_so(self):
        _backup.put_turns(self.V, [40] * 25 + [1] * 25)
        r = run_kb("backup", "--to", str(self.B), cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"清掉 25 個回合備份，空出 \d+ MB；最早還能退回到 \d\d-\d\d \d\d:\d\d 那句「")
        self.assertEqual(len(list((self.V / ".system" / "versions").iterdir())), 25)

    def test_terminal_run_writes_a_program_segment(self):
        run_kb("backup", "--to", str(self.B), cwd=self.V)
        rows = []
        for f in (self.V / ".system" / "journal").glob("*.jsonl"):
            rows += [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()]
        self.assertTrue([r for r in rows if r.get("command") == "backup"])


class Clean(Base):
    def test_check_is_dry_and_matches_real(self):
        _backup.put_turns(self.V, [40] * 25 + [1] * 25)
        before = _backup.tree(self.V)
        r = run_kb("versions", "clean", "--check", "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stderr)
        planned = json.loads(r.stdout)
        self.assertEqual(_backup.tree(self.V), before)
        self.assertEqual(set(planned), {"turns_removed", "earliest", "snapshots_removed", "freed_bytes"})
        real = json.loads(run_kb("versions", "clean", "--json", cwd=self.V).stdout)
        self.assertEqual(planned, real)

    def test_human_text_has_no_turn_codes(self):
        _backup.put_turns(self.V, [40] * 25 + [1] * 25)
        r = run_kb("versions", "clean", cwd=self.V)
        self.assertRegex(r.stdout.strip(), r"^清掉 25 個回合備份，空出 \d+ MB；最早還能退回到 \d\d-\d\d \d\d:\d\d 那句「.*」。$")
        self.assertNotRegex(r.stdout, r"20\d{6}-\d{6}")
        r = run_kb("versions", "clean", cwd=self.V)
        self.assertRegex(r.stdout.strip(), r"^沒有要清的；最早還能退回到 ")


class Links(Base):
    def test_lists_links_and_empty_sentence(self):
        r = run_kb("output", "links", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "沒有存成連結的線上文件"))
        self.assertEqual(json.loads(run_kb("output", "links", "--json", cwd=self.V).stdout), [])
        inventory.register_link(self.V, "https://claude.ai/artifact/aaa", "t1", "信義王 進度報告", type_="報告")
        inventory.register_link(self.V, "https://claude.ai/artifact/bbb", "t1", "大安陳 報價")
        r = run_kb("output", "links", cwd=self.V)
        lines = r.stdout.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r"^.+（\d{4}-\d{2}-\d{2}）$")
        got = json.loads(run_kb("output", "links", "--json", cwd=self.V).stdout)
        self.assertEqual({g["title"] for g in got}, {"信義王 進度報告", "大安陳 報價"})
        self.assertEqual(set(got[0]), {"title", "url", "date", "type"})
        self.assertTrue(all(g["url"].startswith("https://claude.ai/") for g in got))


if __name__ == "__main__":
    unittest.main()
