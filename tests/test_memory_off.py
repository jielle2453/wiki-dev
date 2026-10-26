"""關掉自動記憶（D-229，spec 2026-10-26-關掉自動記憶 驗收 1～4、7、8）：骨架的 .claude/settings.json 帶 autoMemoryEnabled false；
kb init 照抄；既有知識庫升級時骨架對帳換新、退回換得回舊版、她改過的照問；換電腦的環境檢查列出沒關的；小修不准改這個檔。
用真的 skeleton/，歷史檔用替身。環境檢查九項本身在 test_scripts_build_cli 測。"""
import hashlib
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
from tests._guard_fixture import KB, ROOT
from tests.test_tools_release import release  # tools/release.py 照那份測試的載法
from kb._lib import skeleton, turn  # noqa: E402

SID = "sid-memory"
REL = ".claude/settings.json"
SKELETON = ROOT / "skeleton" / ".claude" / "settings.json"
OLD = b'{\n  "permissions": {\n    "deny": []\n  }\n}\n'  # 0.22 以前的骨架原樣


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run_kb(*args, cwd):
    envv = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(KB), *args], capture_output=True, text=True,
                          encoding="utf-8", cwd=str(cwd), env=envv)


class Init(unittest.TestCase):
    def test_init_writes_memory_off(self):
        tmp = Path(tempfile.mkdtemp(prefix="kbmem-")).resolve()
        try:
            V = tmp / "新知識庫"
            r = run_kb("init", str(V), cwd=tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            got = V / ".claude" / "settings.json"
            data = json.loads(got.read_text(encoding="utf-8"))
            self.assertIs(data["autoMemoryEnabled"], False)
            self.assertEqual(data["permissions"]["deny"], [])
            self.assertEqual(got.read_bytes(), SKELETON.read_bytes())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Upgrade(unittest.TestCase):
    """既有知識庫（kb init 建的，其他骨架檔是原樣）的 settings.json 是舊版內容。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kbmem-")).resolve()
        self.V = self.tmp / "知識庫"
        r = run_kb("init", str(self.V), cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.target = self.V / ".claude" / "settings.json"
        self.target.write_bytes(OLD)
        self.history = {}
        self.patch = mock.patch.object(skeleton, "history", side_effect=lambda: self.history)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def record_old(self):
        data = json.loads((self.V / ".system" / "skeleton.json").read_text(encoding="utf-8"))
        data["files"][REL] = sha(OLD)
        (self.V / ".system" / "skeleton.json").write_text(json.dumps(data), encoding="utf-8")

    def test_recorded_old_version_is_replaced_backed_up_and_revertable(self):
        self.record_old()
        t = turn.start(self.V, SID, "升級")["turn"]
        got = skeleton.reconcile(self.V, t)
        self.assertEqual((got["replaced"], got["ask"]), ([REL], []))
        self.assertEqual(self.target.read_bytes(), SKELETON.read_bytes())
        self.assertEqual((self.V / ".system" / "versions" / t / "files" / REL).read_bytes(), OLD)
        turn.start(self.V, SID, "退回上一版")
        r = run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.target.read_bytes(), OLD)

    def test_no_record_but_old_content_in_history_is_replaced(self):
        (self.V / ".system" / "skeleton.json").unlink()
        self.history = {"0.22.0": {REL: sha(OLD)}}
        got = skeleton.reconcile(self.V, turn.start(self.V, SID, "升級")["turn"])
        self.assertIn(REL, got["replaced"])
        self.assertEqual(self.target.read_bytes(), SKELETON.read_bytes())

    def test_edited_settings_is_asked_and_not_touched(self):
        mine = b'{\n  "permissions": {\n    "deny": ["Bash(rm:*)"]\n  }\n}\n'
        self.target.write_bytes(mine)
        self.history = {"0.22.0": {REL: sha(OLD)}}
        for with_record in (True, False):
            with self.subTest(with_record=with_record):
                if with_record:
                    self.record_old()
                else:
                    (self.V / ".system" / "skeleton.json").unlink()
                got = skeleton.reconcile(self.V, turn.start(self.V, SID, "升級")["turn"])
                self.assertEqual((got["ask"], got["replaced"]), ([REL], []))
                self.assertEqual(self.target.read_bytes(), mine)


class NewMachine(unittest.TestCase):
    def test_moved_check_lists_memory_not_off(self):
        tmp, V, _raw = _backup.make_vault()
        try:
            (V / ".claude" / "settings.json").write_text(json.dumps({"permissions": {"deny": []}}), encoding="utf-8")
            (V / ".system" / "env.json").write_text(json.dumps(
                {"schema_version": 1, "machines": {"OLD-PC": {"vault_path": "D:/lin/知識庫"}}}), encoding="utf-8")
            r = run_kb("moved", "--check", "--json", cwd=V)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            got = json.loads(r.stdout)
            self.assertEqual(got["state"], "new_machine")
            self.assertIn({"key": "memory", "level": "warn",
                           "text": "這個知識庫沒關自動記憶：要記的事可能記到知識庫外面；升級到新版時會補上"}, got["env"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class PatchRule(unittest.TestCase):
    def test_patch_may_not_change_skeleton_settings(self):
        """D-217：骨架的 settings.json 改了（這題就是），那一版不准標小修。"""
        rel = "skeleton/.claude/settings.json"
        out = release._patch_problems({rel: SKELETON.read_bytes()}, {rel: OLD})
        self.assertEqual(out, [f"小修不能改骨架檔：{rel} 變了"])


if __name__ == "__main__":
    unittest.main()
