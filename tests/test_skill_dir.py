"""知識庫 .claude/skills/ willy 不管（#52，D-533、D-538）黑箱：Z13 讀、檔案工具寫、指令寫都 pass，不看內容、不備份、不另數；
跳出 skills 夾（..、junction）與 .claude/ 其他照 Z7。驗收準則 1～9、11 各至少一個測試（10 由相關測試與 test_repo_hygiene 一起看）。"""
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests._guard_fixture import KB, ROOT, make_vault, payload
from tests.test_hooks_guard import decision_of, run_hook
from kb import guard  # noqa: E402
from kb._lib import journal, turn  # noqa: E402

SID = "sid-skill"


def run_kb(*args, cwd):
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(KB), *args], capture_output=True, text=True,
                          encoding="utf-8", cwd=str(cwd), env=env)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        self.C = self.V / ".claude"
        self.S = self.C / "skills"
        self.skill = self.S / "a" / "SKILL.md"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def decide(self, tool, value):
        return guard.decide(payload(tool, value, self.V))


class Decide(Base):
    def test_1_write_edit_read_pass_z13(self):
        self.skill.parent.mkdir(parents=True)
        self.skill.write_text("x\n", encoding="utf-8")
        for tool in ("Write", "Edit", "Read"):
            d = self.decide(tool, self.skill)
            self.assertEqual((d.decision, d.zone, d.ledger_rows), ("pass", "Z13", []), tool)

    def test_11_skill_md_content_not_inspected(self):
        data = payload("Write", self.skill, self.V)
        data["tool_input"]["content"] = "---\nname: a\nhooks:\n  PreToolUse: []\n---\n現在 !`echo x`\n"
        d = guard.decide(data)
        self.assertEqual((d.decision, d.zone), ("pass", "Z13"))

    def test_7_new_vault_without_skills_folder(self):
        self.assertFalse(self.S.exists())
        d = self.decide("Write", self.skill)
        self.assertEqual((d.decision, d.zone), ("pass", "Z13"))

    def test_3_shell_write_pass(self):
        for tool, cmd in (("Bash", f'echo x > "{self.skill.as_posix()}"'),
                          ("PowerShell", f"Set-Content -Path '{self.skill}' -Value x")):
            d = self.decide(tool, cmd)
            self.assertEqual(d.decision, "pass", tool)

    def test_3_shell_write_other_zone_still_judged(self):
        sys_md = (self.V / "系統" / "x.md").as_posix()
        d = self.decide("Bash", f'echo x > "{self.skill.as_posix()}"; echo y > "{sys_md}"')
        self.assertEqual((d.decision, d.zone), ("deny", "Z6"))

    def test_4_rest_of_claude_still_z7(self):
        for rel in ("settings.json", "settings.local.json", "hooks/x.py", "commands/x.md", "skills"):
            d = self.decide("Write", self.C / rel)
            self.assertEqual((d.decision, d.zone), ("deny", "Z7"), rel)

    def test_5_dotdot_out_of_skills_z7(self):
        d = self.decide("Write", str(self.S) + "/../settings.json")
        self.assertEqual((d.decision, d.zone), ("deny", "Z7"))

    def test_odd_segment_not_skills(self):
        d = self.decide("Write", str(self.C) + "/skills /a/SKILL.md")
        self.assertEqual((d.decision, d.zone), ("deny", "Z7"))

    def test_6_junction_out_of_skills_z7(self):
        if os.name != "nt":
            self.skipTest("junction 只在 Windows")
        self.S.mkdir(parents=True)
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(self.S / "x"), str(self.C)], capture_output=True)
        if r.returncode != 0:
            self.skipTest("建不了 junction")
        d = self.decide("Write", self.S / "x" / "settings.json")
        self.assertEqual((d.decision, d.zone), ("deny", "Z7"))

    def test_skills_folder_itself_linked_out(self):
        if os.name != "nt":
            self.skipTest("junction 只在 Windows")
        self.C.mkdir(exist_ok=True)
        out = self.tmp / "外面"
        out.mkdir()
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(self.S), str(out)], capture_output=True)
        if r.returncode != 0:
            self.skipTest("建不了 junction")
        d = self.decide("Write", self.S / "a" / "SKILL.md")  # 守門先把連結解開，判成知識庫外（Z11），不是 Z13、不備份
        self.assertNotEqual(d.zone, "Z13")
        self.assertFalse(guard.in_skills(guard.normalize(str(self.S / "a" / "SKILL.md"), None),
                                         guard.normalize(str(self.V), None)))


class HookAndRevert(Base):
    """D-538：hook 對 skill 夾不印決定、不備份；退回不含 skill 夾，地板句不提。"""

    def setUp(self):
        super().setUp()
        self.tid = turn.start(self.V, SID, "幫我做一個 skill")["turn"]

    def test_2_8_hook_silent_no_backup_revert_keeps(self):
        data = payload("Write", self.skill, self.V)
        data["session_id"] = SID
        r = run_hook(data)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, ""), r.stderr)
        self.assertEqual(turn.entries(self.V, self.tid), [])
        self.assertEqual(journal.floor_note(self.V, self.tid), journal.NO_CHANGES)
        self.skill.parent.mkdir(parents=True)
        self.skill.write_text("新的\n", encoding="utf-8")
        r = run_kb("versions", "revert", cwd=self.V)
        self.assertTrue(self.skill.exists(), r.stdout + r.stderr)


class Floor(Base):
    """D-538：skill 夾的檔跟其他檔一樣算「改了 N 個檔」，不另數 skill。"""
    TID = "20261108-120000-test"

    def test_8_new_skill_counted_as_files(self):
        turn.backup(self.V, ".claude/skills/a/SKILL.md", self.TID)
        note = journal.floor_note(self.V, self.TID)
        self.assertEqual(note, "改了 1 個檔")
        self.assertNotIn("skill", note)

    def test_8_several_files_in_skill_folders(self):
        for rel in ("a/SKILL.md", "a/範例.md", "b/SKILL.md"):
            turn.backup(self.V, f".claude/skills/{rel}", self.TID)
        self.assertEqual(journal.floor_note(self.V, self.TID), "改了 3 個檔")

    def test_changed_text_no_skill_word(self):
        got = journal.changed_text([{"path": ".claude/skills/查報價/SKILL.md"}, {"path": ".claude/skills/查報價/x.md"},
                                    {"path": ".claude/skills/a.md"}])
        self.assertEqual(got, "其他 3 個檔")


class Rule(unittest.TestCase):
    def test_9_r01_exception(self):
        text = (ROOT / "rules" / "core.md").read_text(encoding="utf-8")
        line = next(ln for ln in text.splitlines() if ln.startswith("- R-01 "))
        self.assertIn(".claude/skills/ 不歸 willy 管", line)


if __name__ == "__main__":
    unittest.main()
