"""kb restore list／check／apply 黑箱（備份還原與換電腦 驗收 7～13）：subprocess 跑 kb.py。"""
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
from kb._lib import backup, vault as vault_lib  # noqa: E402


def run_kb(*args, cwd):
    envv = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(KB), *args], capture_output=True, text=True,
                          encoding="utf-8", cwd=str(cwd), env=envv)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def statement(sid, text):
    return {"id": sid, "text": text, "entities": [], "date": "2026-10-01", "turn": "t", "status": "active",
            "replaced_by": None}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _backup.make_vault()
        self.B = self.tmp / "備份"
        self.D = self.tmp / "空夾"
        self.D.mkdir()
        write_json(self.V / ".system" / "statements.json", {"schema_version": 1, "statements": [statement("s-0001", "舊口述")]})
        self.zip = _backup.make_zip(self.V, self.B, "vault備份 2026-10-01.zip", created="2026-10-01T09:00:00")
        write_json(self.V / ".system" / "statements.json", {"schema_version": 1, "statements": [
            statement("s-0001", "舊口述"), statement("s-0002", "信義王的設計師換成小陳")]})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def statements(self, root=None):
        data = json.loads(((root or self.V) / ".system" / "statements.json").read_text(encoding="utf-8"))
        return [s["id"] for s in data["statements"]]


class List(Base):
    def test_list_human_and_json(self):
        r = run_kb("restore", "list", "--from", str(self.B), cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "10-01 09:00｜備份｜LIN-PC 做的｜1 MB")
        got = json.loads(run_kb("restore", "list", "--from", str(self.B), "--json", cwd=self.V).stdout)
        self.assertEqual([g["name"] for g in got], ["vault備份 2026-10-01.zip"])
        self.assertTrue(got[0]["usable"])
        self.assertEqual(Path(got[0]["path"]), (self.B / "vault備份 2026-10-01.zip").resolve())

    def test_list_marks_unusable_with_reason_and_includes_snapshots(self):
        (self.B / "vault備份 2026-10-02.zip").write_bytes(b"junk")
        backup.snapshot(self.V, "restore")
        got = json.loads(run_kb("restore", "list", "--from", str(self.B), "--json", cwd=self.V).stdout)
        bad = next(g for g in got if g["name"].endswith("10-02.zip"))
        self.assertFalse(bad["usable"])
        self.assertIn("壞了", bad["why"])
        self.assertTrue([g for g in got if g["kind"] == "snapshot"])
        human = run_kb("restore", "list", "--from", str(self.B), cwd=self.V).stdout
        self.assertIn("不能用：", human)

    def test_list_in_empty_folder_only_from_dir(self):
        got = json.loads(run_kb("restore", "list", "--from", str(self.B), "--json", cwd=self.D).stdout)
        self.assertEqual(len(got), 1)
        r = run_kb("restore", "list", cwd=self.D)
        self.assertEqual(r.returncode, 0)
        self.assertIn("沒有找到備份", r.stdout)


class Check(Base):
    def test_check_dry_human_and_json(self):
        before = _backup.tree(self.V)
        r = run_kb("restore", "check", str(self.zip), cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertEqual(lines[0], "會回到 10-01 09:00 的樣子")
        self.assertEqual(lines[-1], "你原本的資料夾不會動")
        self.assertIn("口述：會不見 1 條（「信義王的設計師換成小陳」）", r.stdout)
        self.assertNotIn("s-0002", r.stdout)
        got = json.loads(run_kb("restore", "check", str(self.zip), "--json", cwd=self.V).stdout)
        self.assertEqual(got["lose"]["statements"], 1)
        self.assertEqual(got["examples"]["statements"], ["信義王的設計師換成小陳"])
        self.assertEqual(_backup.tree(self.V), before)

    def test_check_refusals_exit_3_with_sentence(self):
        bad = self.B / "x.zip"
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("a.txt", "a")
        r = run_kb("restore", "check", str(bad), cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "這份不是 wiki-with-willy 的備份"))
        r = run_kb("restore", "check", "不存在.zip", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "找不到這份：不存在.zip"))
        j = run_kb("restore", "check", str(bad), "--json", cwd=self.V)
        self.assertEqual(j.returncode, 3)
        self.assertEqual(json.loads(j.stdout)["refuse"], "這份不是 wiki-with-willy 的備份")


class Apply(Base):
    def test_apply_then_undo(self):
        r = run_kb("restore", "apply", str(self.zip), cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertRegex(r.stdout.splitlines()[0], r"^已還原到 10-01 09:00 的備份；說「剛剛的還原不要了」可以回到還原前。還原後有 \d+ 份要重新整理。$")
        self.assertEqual(self.statements(), ["s-0001"])
        snaps = json.loads(run_kb("restore", "list", "--json", cwd=self.V).stdout)
        snap = next(g for g in snaps if g["kind"] == "snapshot")
        r = run_kb("restore", "apply", snap["name"], cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self.statements(), ["s-0001", "s-0002"])
        self.assertEqual(len(list((self.V / ".system" / "snapshots").glob("快照*.zip"))), 2)

    def test_apply_in_empty_folder(self):
        r = run_kb("restore", "apply", str(self.zip), cwd=self.D)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self.statements(self.D), ["s-0001"])
        self.assertEqual(vault_lib.vault_id(self.D), backup.read_meta(self.zip)["vault_id"])
        r = run_kb("moved", "--check", "--json", cwd=self.D)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(json.loads(r.stdout)["state"], ("first", "new_machine", "moved"))

    def test_apply_refusals(self):
        other = self.tmp / "別的夾"
        other.mkdir()
        (other / "a.txt").write_text("x", encoding="utf-8")
        r = run_kb("restore", "apply", str(self.zip), cwd=other)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "這個資料夾不是空的，也不是知識庫；換一個空資料夾"))
        newer = _backup.make_zip(self.V, self.B, "vault備份 2026-10-09.zip", plugin_version="99.0.0")
        before = _backup.tree(self.V)
        r = run_kb("restore", "apply", str(newer), cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "這份備份是比較新的版本（99.0.0）做的，先升級再還原"))
        self.assertEqual(_backup.tree(self.V), before)
        evil = self.B / "evil.zip"
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("wiki-with-willy-backup.json", json.dumps(
                {"schema_version": 1, "kind": "backup", "plugin_version": "0.1.0", "vault_id": "kb-00000000"}))
            z.writestr("../evil.txt", "x")
        r = run_kb("restore", "apply", str(evil), cwd=self.V)
        self.assertEqual(r.returncode, 3)
        self.assertFalse((self.tmp / "evil.txt").exists())
        r = run_kb("restore", "apply", "沒有.zip", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "找不到這份：沒有.zip"))
        _backup.put_batch(self.V)
        r = run_kb("restore", "apply", str(self.zip), cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "背景整理還在跑，先停掉再還原"))


if __name__ == "__main__":
    unittest.main()
