"""拿掉 _個人（#51，D-532 撤回彈性區）黑箱：_個人 跟其他第一層夾一樣，不再特殊對待；升級時隨手記搬進 系統/、空夾拿掉。
驗收準則 1～12 各至少一個測試（13 在 tests/obsidian/，14、15 由本檔與 test_repo_hygiene 一起看）。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import _backup
from tests._guard_fixture import KB, ROOT, make_vault, payload
from tests.test_hooks_guard import run_hook
from tests.test_type_dirs import Base as TypeBase, kb as kb_type, legacy_vault
from tests.test_scripts_upgrade_cli import Base as UpgradeBase, run_inproc
from kb import guard  # noqa: E402
from kb._lib import backup, batches, build, journal, migrate, profile, restore, skeleton, turn, upgrade  # noqa: E402

NAME = "_個人"
A = "sid-free-a"
AGENT = "a0204e72"


def run_kb(*args, cwd, sid=None):
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT), PYTHONIOENCODING="utf-8")
    head = ["--session", sid] if sid else []
    return subprocess.run([sys.executable, str(KB), *head, *args], capture_output=True, text=True,
                          encoding="utf-8", cwd=str(cwd), env=env)


class FixtureVault(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        self.F = self.V / NAME
        self.O = self.V / "其他夾"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def decide(self, tool, value, cwd=None):
        return guard.decide(payload(tool, value, cwd or self.V))

    def put(self, rel, text="內容\n"):
        out = []
        for base in (self.F, self.O):
            p = base / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            out.append(p)
        return out


# ---------- 1～3 程式、靜態檔、骨架 ----------

class Static(unittest.TestCase):
    TREES = ("scripts", "hooks", "skills", "rules", "skeleton", "obsidian")

    def grep(self, pattern, trees):
        out = subprocess.run(["git", "grep", "-l", "-E", pattern, "--", *trees], capture_output=True, text=True,
                             encoding="utf-8", cwd=str(ROOT))
        return sorted(out.stdout.split())

    def test_1_no_free_area_code_left(self):
        pat = r"FREE_DIR|FREE_NOT_EMPTY|FREE_SINCE_AFTER|free_scan|Z12|_is_free|free_files"
        self.assertEqual(self.grep(pat, self.TREES), [])

    def test_2_name_only_in_upgrade(self):
        self.assertEqual(self.grep(NAME, ("hooks", "skills", "rules", "skeleton", "obsidian")), [])
        self.assertEqual(self.grep(NAME, ("scripts",)), ["scripts/kb/_lib/upgrade.py"])

    def test_3_skeleton_and_init(self):
        self.assertFalse((ROOT / "skeleton" / NAME).exists())
        tmp = Path(tempfile.mkdtemp(prefix="kbfree-")).resolve()
        try:
            V = tmp / "kb"
            r = run_kb("init", str(V), cwd=tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertFalse((V / NAME).exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ---------- 4 清冊與不讀 ----------

class Inventory(FixtureVault):
    def todo(self):
        r = run_kb("inventory", "scan", "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run_kb("cards", "todo", "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def test_4_listed_then_excluded(self):
        self.F.mkdir()
        (self.F / "a.md").write_text("11 月要談保固\n", encoding="utf-8")
        self.assertIn(f"{NAME}/a.md", self.todo())
        r = run_kb("folders", "exclude", NAME, "--kind", "unused", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(f"{NAME}/a.md", self.todo())


# ---------- 5 守門 ----------

class Guard(FixtureVault):
    def same(self, tool, rel):
        f, o = self.put(rel)
        got = [(d.decision, d.zone, d.reason_code) for d in (self.decide(tool, f), self.decide(tool, o))]
        self.assertEqual(got[0], got[1], (tool, rel))

    def test_5_same_as_other_folder(self):
        for tool in ("Read", "Write", "Grep"):
            self.same(tool, "a.md")
        self.same("Read", "密碼.txt")

    def test_5_vault_search_not_walked(self):
        self.put("子夾/帳密.xlsx")
        d = self.decide("Grep", self.V)
        self.assertNotEqual(d.decision, "deny", d.reason)
        d = self.decide("Bash", f'grep -r 保固 "{self.V}"')
        self.assertNotEqual(d.reason_code, "credential_inside", d.reason)


class Agent(FixtureVault):
    def setUp(self):
        super().setUp()
        turn.start(self.V, A, "好，現在做")
        batches.agent_start(self.V, A, AGENT)

    def hook(self, tool, value, **extra):
        data = dict(payload(tool, value, self.V), session_id=A, agent_id=AGENT, agent_type="wiki-with-willy:card-maker")
        data["tool_input"].update(extra)
        r = run_hook(data)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["hookSpecificOutput"].get("permissionDecision")

    def test_5_agent_same_as_other_folder(self):
        f, o = self.put("a.md")
        for tool in ("Read", "Write"):
            self.assertEqual(self.hook(tool, f), self.hook(tool, o), tool)
        cmd = 'python "' + str(ROOT) + '/scripts/kb.py" convert "file://知識庫/{}/a.md"'
        self.assertEqual(self.hook("Bash", cmd.format(NAME)), self.hook("Bash", cmd.format("其他夾")))
        self.assertEqual(self.hook("Glob", self.V, pattern="**/*.md"), "allow")


# ---------- 6 建置 ----------

class Build(FixtureVault):
    def test_6_finish_not_refused(self):
        self.put("交接.md")
        build._check(self.V, {"report": True}, "finish")
        self.assertNotIn("free_files", build.report_facts(self.V))


# ---------- 12 還原、日誌（不另比、不另數） ----------

class Restore(unittest.TestCase):
    def test_12_check_says_nothing_about_it(self):
        tmp, V, _raw = _backup.make_vault()
        try:
            (V / NAME).mkdir()
            (V / NAME / "廠商.md").write_text("大同\n", encoding="utf-8")
            (tmp / "備份").mkdir()
            z = _backup.make_zip(V, tmp / "備份")
            (V / NAME / "廠商.md").write_text("大同與聲寶\n", encoding="utf-8")
            got = restore.check(V, str(z))
            self.assertNotIn("free", got)
            self.assertNotIn(NAME, "\n".join(restore.lines(got)))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_12_journal_counts_it_as_other(self):
        self.assertEqual(journal.changed_text([{"path": f"{NAME}/a.md"}]), journal.changed_text([{"path": "其他夾/a.md"}]))


# ---------- 9（設定檔）與 10、11 遷移 ----------

class Profile(TypeBase):
    def test_9_type_dir_can_be_it(self):
        types = [{"name": "倉庫", "category": "物", "dir": NAME}]
        (self.V / NAME).mkdir()
        plan = profile.dir_plan(self.V, types, types)
        self.assertEqual(plan["types"][0]["dir"], NAME)
        self.assertIsNone(plan["refusal"])

    def test_9_unlisted_like_other_folders(self):
        (self.V / NAME).mkdir()
        r = kb_type(self.V, "profile", "check", "--json")
        self.assertIn(NAME, json.loads(r.stdout).get("unlisted") or [])


class Migrate(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.cid = legacy_vault()
        migrate.apply(self.V, turn.start(self.V, None, "")["turn"])  # 先補編號：01 案子、02 業主

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_10_schema6_dir_kept(self):
        (self.V / "01 案子").rename(self.V / NAME)
        pj = self.V / profile.PROFILE_POSIX
        data = json.loads(pj.read_text(encoding="utf-8"))
        data["types"][0]["dir"] = NAME
        data["schema_version"] = 6
        pj.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        migrate.apply(self.V, turn.start(self.V, None, "")["turn"])
        data = json.loads(pj.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 7)
        self.assertEqual(data["types"][0]["dir"], NAME)
        self.assertTrue((self.V / NAME / "信義王" / "信義王.md").is_file())
        self.assertEqual([p for p in migrate.pending(self.V) if p["rel"] == profile.PROFILE_POSIX], [])

    def test_11_extras_untouched(self):
        (self.V / "_extras").mkdir()
        (self.V / "_extras" / "x.txt").write_text("x\n", encoding="utf-8")
        got = migrate.apply(self.V, turn.start(self.V, None, "")["turn"])
        self.assertTrue((self.V / "_extras" / "x.txt").is_file())
        self.assertFalse((self.V / NAME).exists())
        self.assertEqual(got["notes"], [])


# ---------- 7～9 升級 ----------

class Upgrade(UpgradeBase):
    PLUGIN = "0.34.0"

    def setUp(self):
        super().setUp()
        self.root_sk = self.tmp / "skeleton"
        self.root_sk.mkdir()
        from kb import init
        self.sk = [mock.patch.object(skeleton, "skeleton_root", return_value=self.root_sk),
                   mock.patch.object(init, "skeleton_root", return_value=self.root_sk),
                   mock.patch.object(skeleton, "history", return_value={})]
        for p in self.sk:
            p.start()
        shutil.rmtree(self.V / ".claude", ignore_errors=True)
        self.F = self.V / NAME
        self.F.mkdir()
        self.note = self.V / "系統" / "隨手記.md"

    def tearDown(self):
        for p in self.sk:
            p.stop()
        super().tearDown()

    def finish(self, cur="0.33.0"):
        self.put_history(cur, pending={"to": self.PLUGIN, "snapshot": backup.snapshot(self.V, "upgrade").name,
                                       "started": "2026-11-08T10:00:00"})
        return upgrade.finish(self.V, turn.start(self.V, None, "")["turn"])

    def test_7_only_gitkeep_removed(self):
        (self.F / ".gitkeep").write_text("", encoding="utf-8")
        got = self.finish()
        self.assertFalse(self.F.exists())
        self.assertNotIn(upgrade.UPGRADE_LINE, got["migrate_notes"])

    def test_8_note_moved_other_files_kept(self):
        data = "11/20 前回大同\r\n  第二行  \n".encode("utf-8")
        (self.F / "隨手記.md").write_bytes(data)
        (self.F / "a.docx").write_bytes(b"PK\x03\x04docx")
        got = self.finish()
        self.assertEqual(self.note.read_bytes(), data)
        self.assertFalse((self.F / "隨手記.md").exists())
        self.assertTrue((self.F / "a.docx").is_file())
        self.assertIn(upgrade.UPGRADE_LINE, got["migrate_notes"])
        index = self.V / "檔案索引"
        made = [p for p in index.rglob("*.md") if "a.docx" in p.read_text(encoding="utf-8")] if index.is_dir() else []
        self.assertEqual(made, [])
        _code, out = run_inproc(["upgrade", "--finish"], self.V)  # 第二次：已經是這一版，不再說
        self.assertNotIn(NAME, out)

    def test_9_only_note_folder_removed(self):
        (self.F / "隨手記.md").write_text("便條\n", encoding="utf-8")
        got = self.finish()
        self.assertEqual(self.note.read_text(encoding="utf-8"), "便條\n")
        self.assertFalse(self.F.exists())
        self.assertNotIn(upgrade.UPGRADE_LINE, got["migrate_notes"])

    def test_9_note_already_there_both_kept(self):
        (self.F / "隨手記.md").write_text("舊的\n", encoding="utf-8")
        self.note.parent.mkdir(exist_ok=True)
        self.note.write_text("新的\n", encoding="utf-8")
        got = self.finish()
        self.assertEqual((self.F / "隨手記.md").read_text(encoding="utf-8"), "舊的\n")
        self.assertEqual(self.note.read_text(encoding="utf-8"), "新的\n")
        self.assertIn(upgrade.NOTE_BOTH, got["migrate_notes"])

    def test_type_folder_named_it_untouched(self):
        """review：舊庫的型別夾叫 _個人（dir 是它）不是彈性區：空的也不拿掉、不說 UPGRADE_LINE。"""
        with mock.patch.object(profile, "type_of_folder", side_effect=lambda v, f: "倉庫" if f == NAME else None):
            got = self.finish()
        self.assertTrue(self.F.is_dir())
        self.assertNotIn(upgrade.UPGRADE_LINE, got["migrate_notes"])

    def test_gitkeep_kept_when_her_files_there(self):
        (self.F / ".gitkeep").write_text("", encoding="utf-8")
        (self.F / "a.docx").write_bytes(b"x")
        got = self.finish()
        self.assertTrue((self.F / ".gitkeep").is_file())
        self.assertIn(upgrade.UPGRADE_LINE, got["migrate_notes"])

    def test_note_move_failed_said(self):
        (self.F / "隨手記.md").write_text("便條\n", encoding="utf-8")
        real = os.rename

        def rename(a, b, *k, **kw):
            if str(a).endswith("隨手記.md"):
                raise PermissionError(13, "denied")
            return real(a, b, *k, **kw)
        with mock.patch.object(os, "rename", side_effect=rename):
            got = self.finish()
        self.assertTrue((self.F / "隨手記.md").is_file())
        self.assertTrue(any(n.startswith("_個人/隨手記.md 沒搬到 系統/") for n in got["migrate_notes"]), got["migrate_notes"])

    def linked_not_moved(self, got):
        self.assertTrue(any(n.startswith("_個人/隨手記.md 沒搬到 系統/") for n in got["migrate_notes"]), got["migrate_notes"])

    def test_note_is_link_not_moved(self):
        """security-review (1)：隨手記.md 本身是連結 → 不搬（連結不跟），說沒搬。"""
        outside = self.tmp / "外面.md"
        outside.write_text("外面\n", encoding="utf-8")
        try:
            os.symlink(outside, self.F / "隨手記.md")
        except (OSError, NotImplementedError):
            self.skipTest("這台建不了 symlink")
        got = self.finish()
        self.assertTrue((self.F / "隨手記.md").is_symlink())
        self.assertFalse(self.note.exists())
        self.linked_not_moved(got)

    def test_system_is_junction_not_moved(self):
        """security-review (1)：系統/ 是 junction（可能在知識庫外）→ 不搬，說沒搬。"""
        (self.F / "隨手記.md").write_text("便條\n", encoding="utf-8")
        outside = self.tmp / "外面系統"
        if (self.V / "系統").exists():
            shutil.move(str(self.V / "系統"), str(outside))
        else:
            outside.mkdir()
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(self.V / "系統"), str(outside)], capture_output=True)
        if r.returncode != 0:
            self.skipTest("這台建不了 junction")
        got = self.finish()
        self.assertTrue((self.F / "隨手記.md").is_file())
        self.assertFalse((outside / "隨手記.md").exists())
        self.linked_not_moved(got)

    def test_newer_vault_not_touched(self):
        (self.F / ".gitkeep").write_text("", encoding="utf-8")
        self.PLUGIN = "0.34.1"
        got = self.finish(cur="0.34.0")
        self.assertTrue((self.F / ".gitkeep").is_file())
        self.assertNotIn(upgrade.UPGRADE_LINE, got["migrate_notes"])


if __name__ == "__main__":
    unittest.main()
