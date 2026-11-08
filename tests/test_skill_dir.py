"""知識庫 .claude/skills/ 讓 AI 寫得進去（#52，D-533）黑箱：Z13 檔案工具寫放行、寫前備份、退回得掉；指令寫照 Z7 擋；
跳出 skills 夾（..、junction）照 Z7；地板句數 skill。驗收準則 1～9 各至少一個測試（10 由相關測試與 test_repo_hygiene 一起看）。"""
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
    def test_1_write_and_read_allowed_z13(self):
        self.skill.parent.mkdir(parents=True)
        self.skill.write_text("x\n", encoding="utf-8")
        for tool in ("Write", "Edit", "Read"):
            d = self.decide(tool, self.skill)
            self.assertEqual((d.decision, d.zone), ("allow", "Z13"), tool)

    def test_7_new_vault_without_skills_folder(self):
        self.assertFalse(self.S.exists())
        d = self.decide("Write", self.skill)
        self.assertEqual((d.decision, d.zone), ("allow", "Z13"))

    def test_3_shell_write_denied_teaches_file_tool(self):
        for tool, cmd in (("Bash", f'echo x > "{self.skill.as_posix()}"'),
                          ("PowerShell", f"Set-Content -Path '{self.skill}' -Value x")):
            d = self.decide(tool, cmd)
            self.assertEqual(d.decision, "deny", tool)
            self.assertEqual(d.reason_code, "willy", tool)
            self.assertIn("Write", d.reason, tool)

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
    def setUp(self):
        super().setUp()
        turn.start(self.V, SID, "幫我做一個 skill")

    def write(self, path):
        data = payload("Write", path, self.V)
        data["session_id"] = SID
        r = run_hook(data)
        self.assertEqual(r.returncode, 0, r.stderr)
        return decision_of(r)[1]

    def revert(self):
        r = run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_2_new_skill_reverted_gone(self):
        self.assertEqual(self.write(self.skill), "allow")
        self.skill.parent.mkdir(parents=True)
        self.skill.write_text("新的\n", encoding="utf-8")
        self.revert()
        self.assertFalse(self.skill.exists())

    def test_2_changed_skill_reverted_byte_equal(self):
        self.skill.parent.mkdir(parents=True)
        before = "---\nname: a\n---\n舊的\r\n".encode("utf-8")
        self.skill.write_bytes(before)
        self.assertEqual(self.write(self.skill), "allow")
        self.skill.write_text("改過\n", encoding="utf-8")
        self.revert()
        self.assertEqual(self.skill.read_bytes(), before)


class Floor(Base):
    TID = "20261108-120000-test"

    def test_8_new_skill_counted_once(self):
        turn.backup(self.V, ".claude/skills/a/SKILL.md", self.TID)
        turn.backup(self.V, ".claude/skills/a/範例.md", self.TID)
        self.assertEqual(journal.floor_note(self.V, self.TID), "新增 1 個 skill")

    def test_8_changed_two_skills(self):
        for name in ("a", "b"):
            p = self.S / name / "SKILL.md"
            p.parent.mkdir(parents=True)
            p.write_text("x", encoding="utf-8")
            turn.backup(self.V, f".claude/skills/{name}/SKILL.md", self.TID)
        self.assertEqual(journal.floor_note(self.V, self.TID), "改了 2 個 skill")

    def test_changed_text_names_skill(self):
        got = journal.changed_text([{"path": ".claude/skills/查報價/SKILL.md"}, {"path": ".claude/skills/查報價/x.md"}])
        self.assertEqual(got, "skill 查報價")


class Rule(unittest.TestCase):
    def test_9_r01_exception(self):
        text = (ROOT / "rules" / "core.md").read_text(encoding="utf-8")
        line = next(ln for ln in text.splitlines() if ln.startswith("- R-01 "))
        self.assertIn(".claude/skills/", line)


if __name__ == "__main__":
    unittest.main()
