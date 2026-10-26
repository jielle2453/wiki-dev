"""kb selftest（換版前先驗新版 要做的事一，驗收 1、2）：檢查自己這份 plugin——模組 import 得到、版本、暫存小知識庫、
hooks.json 每個 hook 跑一次、kb upgrade --background。真的跑（不換替身）：repo 本身一次、複製一份各做一種壞法各一次。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import _backup
from tests._guard_fixture import KB, ROOT

PLUGIN_PARTS = (".claude-plugin", "hooks", "scripts", "config", "rules", "skills", "templates", "skeleton", "agents")
SELFTEST_PREFIX = "wiki-with-willy-selftest-"


def run_selftest(kb_py, cwd, *extra):
    envv = dict(os.environ, PYTHONIOENCODING="utf-8")
    envv.pop("CLAUDE_PLUGIN_ROOT", None)
    r = subprocess.run([sys.executable, str(kb_py), "selftest", *extra], capture_output=True, text=True,
                       encoding="utf-8", cwd=str(cwd), env=envv, timeout=300)
    return r


def leftovers():
    base = Path(tempfile.gettempdir())
    return {p.name for p in base.iterdir() if p.name.startswith(SELFTEST_PREFIX)}


def snapshot(folder):
    """夾裡每個檔的 (相對路徑, 大小, 修改時間)。"""
    out = {}
    for p in Path(folder).rglob("*"):
        if p.is_file():
            st = p.stat()
            out[p.relative_to(folder).as_posix()] = (st.st_size, st.st_mtime_ns)
    return out


def copy_plugin(dest):
    """repo 裡會進 zip 的那幾個夾複製一份（不帶 __pycache__）；回 plugin 根。"""
    dest = Path(dest)
    for part in PLUGIN_PARTS:
        src = ROOT / part
        if src.is_dir():
            shutil.copytree(src, dest / part, ignore=shutil.ignore_patterns("__pycache__"))
    return dest


class InRepo(unittest.TestCase):
    """驗收 1：repo 裡跑是過的；不留小知識庫；cwd 的知識庫沒被動到。"""

    def setUp(self):
        self.tmp, self.V, _raw = _backup.make_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_passes_in_the_repo_and_touches_nothing(self):
        before_tmp = leftovers()
        before = snapshot(self.V)
        r = run_selftest(KB, self.V, "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        got = json.loads(r.stdout)
        version = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
        self.assertEqual(got, {"ok": True, "version": version, "step": None, "file": None, "line": None, "why": None})
        self.assertEqual(leftovers(), before_tmp)
        self.assertEqual(snapshot(self.V), before)

    def test_human_line(self):
        r = run_selftest(KB, self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        version = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
        self.assertEqual(r.stdout.strip(), f"自我檢查過了（{version}）")


class Broken(unittest.TestCase):
    """驗收 2：複製一份、各做一種壞法，ok 是 false、step 對。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kbselftest-")).resolve()
        self.root = copy_plugin(self.tmp / "plugin")
        self.kb = self.root / "scripts" / "kb.py"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def edit(self, rel, fn):
        p = self.root / rel
        p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8", newline="\n")

    def run_json(self):
        before = leftovers()
        r = run_selftest(self.kb, self.tmp, "--json")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        got = json.loads(r.stdout)
        self.assertIs(got["ok"], False)
        self.assertEqual(leftovers(), before)
        self.assertNotIn(str(self.tmp), json.dumps(got, ensure_ascii=False))
        self.assertNotIn(str(self.tmp).replace("\\", "/"), json.dumps(got, ensure_ascii=False))
        return got

    def test_missing_import(self):
        self.edit("scripts/kb/_lib/vault.py", lambda t: "import no_such_module_for_selftest\n" + t)
        got = self.run_json()
        self.assertEqual(got["step"], "import")
        self.assertEqual(got["file"], "scripts/kb/_lib/vault.py")
        self.assertEqual(got["line"], 1)
        self.assertIn("ModuleNotFoundError", got["why"])

    def test_guard_never_prints(self):
        self.edit("hooks/guard.py", lambda t: t.replace("def emit(decision, reason, updated=None):\n",
                                                         "def emit(decision, reason, updated=None):\n    return\n"))
        got = self.run_json()
        self.assertEqual(got["step"], "hooks")
        self.assertIn("該擋沒擋", got["why"])
        self.assertIn("hooks/guard.py", got["why"])

    def test_guard_that_raises_at_run_time(self):
        """裁定 9：守門執行時丟例外，知識庫裡一律印「守門出錯」的 deny；該擋那例的理由不能是它、該放那例（小知識庫裡讀普通檔）不能 deny。"""
        self.edit("scripts/kb/guard.py", lambda t: t.replace(
            "def decide(payload):\n", "def decide(payload):\n    raise RuntimeError('壞了')\n", 1))
        got = self.run_json()
        self.assertEqual(got["step"], "hooks")
        self.assertIn("hooks/guard.py", got["why"])

    def test_hook_that_swallows_an_exception_into_the_log(self):
        """裁定 10：hook 吞了例外、exit 0，但寫了 .system/hook-errors.log：不過，why 帶那一行。"""
        self.edit("scripts/kb/_lib/turn.py", lambda t: t.replace(
            "def start(vault, session_id, prompt, inherit=None):\n",
            "def start(vault, session_id, prompt, inherit=None):\n    raise RuntimeError('回合壞了')\n", 1))
        got = self.run_json()
        self.assertEqual(got["step"], "hooks")
        self.assertIn("hook-errors.log", got["why"])
        self.assertIn("RuntimeError", got["why"])

    def test_slow_hook_times_out(self):
        cfg = self.root / "config" / "defaults.json"
        data = json.loads(cfg.read_text(encoding="utf-8"))
        data["selftest_hook_seconds"] = 1
        cfg.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.edit("hooks/session.py", lambda t: "import time; time.sleep(10)\n" + t)
        got = self.run_json()
        self.assertEqual(got["step"], "hooks")
        self.assertIn("逾時", got["why"])
        self.assertIn("hooks/session.py", got["why"])

    def test_hook_exit_code(self):
        self.edit("hooks/turn.py", lambda t: "import sys; sys.exit(1)\n" + t)
        got = self.run_json()
        self.assertEqual(got["step"], "hooks")
        self.assertIn("hooks/turn.py", got["why"])

    def test_upgrade_background_fails(self):
        self.edit("scripts/kb/upgrade_cli.py", lambda t: t.replace(
            "    if args.background:\n        try:",
            "    if args.background:\n        raise RuntimeError('壞了')\n        try:"))
        got = self.run_json()
        self.assertEqual(got["step"], "upgrade")

    def test_bad_version(self):
        mf = self.root / ".claude-plugin" / "plugin.json"
        data = json.loads(mf.read_text(encoding="utf-8"))
        data["version"] = "0.x"
        mf.write_text(json.dumps(data), encoding="utf-8")
        got = self.run_json()
        self.assertEqual(got["step"], "version")
        self.assertIsNone(got["version"])

    def test_human_line_names_the_step(self):
        self.edit("hooks/turn.py", lambda t: "import sys; sys.exit(1)\n" + t)
        r = run_selftest(self.kb, self.tmp)
        self.assertEqual(r.returncode, 3)
        self.assertTrue(r.stdout.startswith("自我檢查沒過：hooks："), r.stdout)


class Unit(unittest.TestCase):
    """拆指令與從 traceback 取檔與行（不開子行程）。"""

    def setUp(self):
        from kb._lib import selftest
        self.st = selftest

    def test_command_parts(self):
        self.assertEqual(self.st.command_parts('python "${CLAUDE_PLUGIN_ROOT}/hooks/subagent.py" start'),
                         ("subagent.py", ["start"]))
        self.assertEqual(self.st.command_parts('python "${CLAUDE_PLUGIN_ROOT}/hooks/guard.py"'), ("guard.py", []))
        for bad in ("echo hi", 'python "${CLAUDE_PLUGIN_ROOT}/hooks/../x.py"', 'python "${CLAUDE_PLUGIN_ROOT}/hooks/a b.py"',
                    'python "unclosed'):
            with self.subTest(bad=bad):
                self.assertIsNone(self.st.command_parts(bad))

    def test_where_from_stderr_traceback(self):
        root = Path("C:/外掛")
        err = ('Traceback (most recent call last):\n  File "C:\\外掛\\hooks\\guard.py", line 3, in <module>\n'
               '  File "C:\\外掛\\scripts\\kb\\guard.py", line 40, in f\nNameError: x\n')
        self.assertEqual(self.st.where_in(err, root), ("scripts/kb/guard.py", 40))
        self.assertEqual(self.st.where_in("沒有 traceback", root), (None, None))
        self.assertEqual(self.st.where_in('  File "D:\\別處\\y.py", line 2, in f\n', root), (None, None))

    def test_guard_error_reason_is_read_from_that_copy(self):
        self.assertEqual(self.st.guard_error_reason(ROOT), "守門出錯，這次不放行。說「檢查」我看原因")

    def test_why_has_no_absolute_paths(self):
        why = self.st.clean_why("FileNotFoundError: C:\\Users\\某人\\x.py 和 /tmp/y 都不在")
        self.assertNotIn("C:\\Users", why)
        self.assertNotIn("/tmp/y", why)
        self.assertIn("FileNotFoundError", why)


if __name__ == "__main__":
    unittest.main()
