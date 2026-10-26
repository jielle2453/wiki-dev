"""kb upgrade 黑箱（升級打包 驗收 3、6、7、9、10、12）：--check／直接跑／--finish／--downgrade／--background／skeleton。
要網路與 claude.exe 的走 kb.cli.main 同一個行程（替身換 upgrade._get、_call）；不用網路的另外 subprocess 跑 kb.py。"""
import contextlib
import io
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
from tests.test_lib_upgrade import Fake, MANIFEST_URL, ROLLOUT_URL, MARKET, manifest, rollout
from kb import cli  # noqa: E402
from kb._lib import backup, env, skeleton, upgrade, vault as vault_lib  # noqa: E402


def run_inproc(argv, cwd):
    old = os.getcwd()
    os.chdir(str(cwd))
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = cli.main(argv)
    finally:
        os.chdir(old)
    return code, buf.getvalue()


def run_kb(*args, cwd):
    envv = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(KB), *args], capture_output=True, text=True,
                          encoding="utf-8", cwd=str(cwd), env=envv)


class Base(unittest.TestCase):
    PLUGIN = "0.20.1"

    def setUp(self):
        self.tmp, self.V, self.raw = _backup.make_vault()
        self.fake = Fake(self.tmp / "fake")
        (self.V / ".system" / "config.json").write_text(json.dumps(
            {"update_manifest_url": MANIFEST_URL, "update_rollout_url": ROLLOUT_URL}), encoding="utf-8")
        self.vid = vault_lib.vault_id(self.V)
        self.patches = [
            mock.patch.object(upgrade, "_get", side_effect=self.fake.get),
            mock.patch.object(upgrade, "_call", side_effect=self.fake.call),
            mock.patch.object(upgrade, "plugin_version", side_effect=lambda: self.PLUGIN),
            mock.patch.object(upgrade, "_plugin_root", return_value=self.fake.root),
            mock.patch.object(upgrade, "installed_plugins_path", return_value=self.fake.installed),
            mock.patch.object(upgrade, "find_claude", return_value="C:/fake/claude.exe"),
            mock.patch.object(upgrade, "_today", return_value="2026-10-24"),
            mock.patch.object(upgrade, "_changelog", return_value=(
                "## 0.21.0 — 2026-10-30\n- **給客戶的一句話**：日程可以匯出成 Excel。\n\n"
                "## 0.20.2 — 2026-10-26\n- **給客戶的一句話**：修好日程匯出的日期錯誤。\n")),
            mock.patch.object(upgrade, "verify", side_effect=self.fake.verify),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def serve(self, version, mine=True, note="日程可以匯出成 Excel"):
        self.fake.texts[MANIFEST_URL] = manifest(version)
        self.fake.texts[ROLLOUT_URL] = rollout(**{version: {"for": [self.vid] if mine else ["kb-00000000"], "note": note}})
        self.fake.target = version

    def put_history(self, current, pending=None):
        (self.V / ".system" / "upgrade-history.json").write_text(json.dumps(
            {"schema_version": 1, "current": current, "pending": pending, "history": []}), encoding="utf-8")

    def history(self):
        return json.loads((self.V / ".system" / "upgrade-history.json").read_text(encoding="utf-8"))


class Check(Base):
    def test_json_for_a_minor_she_can_take(self):
        self.serve("0.21.0")
        self.put_history("0.20.1")
        code, out = run_inproc(["upgrade", "--check", "--json"], self.V)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"plugin": "0.20.1", "vault": "0.20.1", "latest": "0.21.0", "kind": "minor",
                                           "allowed": True, "note": "日程可以匯出成 Excel", "snapshot_for_downgrade": None,
                                           "error": None, "verify_failed": None})

    def test_human_lines_are_exact(self):
        self.serve("0.21.0")
        self.put_history("0.20.1")
        self.assertEqual(run_inproc(["upgrade", "--check"], self.V),
                         (0, "現在 0.20.1；最新 0.21.0（日程可以匯出成 Excel），說「升級」就幫你升。\n"))
        self.serve("0.20.1")
        self.assertEqual(run_inproc(["upgrade", "--check"], self.V), (0, "目前是最新版（0.20.1）。\n"))
        self.serve("0.21.0", mine=False)
        self.assertEqual(run_inproc(["upgrade", "--check"], self.V), (0, "目前是最新版（0.20.1）。\n"))

    def test_offline_exit_0_one_line_and_nothing_written(self):
        self.fake.texts[MANIFEST_URL] = TimeoutError("逾時")
        before = _backup.tree(self.V)
        self.assertEqual(run_inproc(["upgrade", "--check"], self.V), (0, "現在連不上更新的地方，晚點再問。\n"))
        code, out = run_inproc(["upgrade", "--check", "--json"], self.V)
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["error"])
        self.assertEqual(_backup.tree(self.V), before)

    def test_not_a_vault_exit_3(self):
        code, out = run_inproc(["upgrade", "--check"], self.tmp)
        self.assertEqual((code, out.strip()), (3, "這裡不是知識庫"))


class VerifyFailed(Base):
    """換版前先驗新版：kb upgrade 驗不過 exit 3 那句一字不差；--check 多一行、--json 多 verify_failed。"""

    FAILED = {"ok": False, "version": "0.21.0", "python": "3.11", "step": "compile", "file": "hooks/guard.py", "line": 12,
              "why": "SyntaxError: invalid syntax"}
    REFUSED = "新版 0.21.0 在這台電腦跑不起來（hooks/guard.py 第 12 行：SyntaxError），先不換；什麼都沒動"

    def test_upgrade_refused(self):
        self.serve("0.21.0")
        self.put_history("0.20.1")
        self.fake.verify_result = self.FAILED
        self.assertEqual(run_inproc(["upgrade"], self.V), (3, self.REFUSED + "\n"))
        code, out = run_inproc(["upgrade", "--json"], self.V)
        self.assertEqual((code, json.loads(out)), (3, {"ok": False, "message": self.REFUSED}))
        self.assertEqual(backup.snapshots(self.V), [])
        self.assertIsNone(self.history()["pending"])
        self.assertEqual(self.fake.calls, [])

    def test_check_line_and_json(self):
        self.serve("0.21.0")
        self.put_history("0.20.1")
        env.set_update_check(self.V, dict(upgrade.BLANK_CHECK, date="2026-10-24", verify_failed=self.FAILED))
        code, out = run_inproc(["upgrade", "--check"], self.V)
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["現在 0.20.1；最新 0.21.0（日程可以匯出成 Excel），說「升級」就幫你升。",
                                            "新版 0.21.0 在這台電腦跑不起來（hooks/guard.py 第 12 行：SyntaxError），先沒換"])
        code, out = run_inproc(["upgrade", "--check", "--json"], self.V)
        self.assertEqual(json.loads(out)["verify_failed"], self.FAILED)


class Upgrade(Base):
    def test_success_sentence_exit_0(self):
        self.serve("0.21.0")
        self.put_history("0.20.1")
        code, out = run_inproc(["upgrade"], self.V)
        self.assertEqual((code, out.strip()), (0, "好了，開一個新對話就是新版（0.21.0）。"))
        self.assertEqual(len(backup.snapshots(self.V)), 1)
        self.assertEqual(self.history()["pending"]["to"], "0.21.0")

    def test_success_json(self):
        self.serve("0.21.0")
        code, out = run_inproc(["upgrade", "--json"], self.V)
        got = json.loads(out)
        self.assertEqual((code, got["ok"], got["message"], got["to"]), (0, True, "好了，開一個新對話就是新版（0.21.0）。", "0.21.0"))
        self.assertTrue(got["snapshot"])

    def test_refusals_exit_3_exact_sentences(self):
        self.serve("0.20.1")
        self.assertEqual(run_inproc(["upgrade"], self.V), (3, "目前是最新版（0.20.1）\n"))
        self.serve("0.21.0")
        self.fake.mode = "stale"
        self.assertEqual(run_inproc(["upgrade"], self.V), (3, "新版剛出來，幾分鐘後再說一次\n"))
        self.fake.texts[MANIFEST_URL] = OSError("斷線")
        self.assertEqual(run_inproc(["upgrade"], self.V), (3, "現在連不上更新的地方，晚點再說一次\n"))
        self.serve("0.21.0")
        _backup.put_batch(self.V, created_min_ago=1, seen_min_ago=0)
        self.assertEqual(run_inproc(["upgrade"], self.V), (3, "背景整理還在跑，先停掉再升級\n"))

    def test_refusal_json_has_ok_false_and_message(self):
        self.serve("0.20.1")
        code, out = run_inproc(["upgrade", "--json"], self.V)
        self.assertEqual((code, json.loads(out)), (3, {"ok": False, "message": "目前是最新版（0.20.1）"}))

    def test_downgrade_flag_flow(self):
        self.PLUGIN = "0.21.0"
        self.fake.set_installed("0.21.0", "user")
        self.fake.root = self.fake.root.parent / "0.21.0"
        self.fake.root.mkdir(parents=True, exist_ok=True)
        self.patches[3].stop()
        self.patches[3] = mock.patch.object(upgrade, "_plugin_root", return_value=self.fake.root)
        self.patches[3].start()
        snap = backup.snapshot(self.V, "upgrade")
        self.put_history("0.21.0")
        h = self.history()
        h["history"].append({"from": "0.20.0", "to": "0.21.0", "date": "2026-10-23", "kind": "minor",
                             "snapshot": snap.name, "by": "customer"})
        (self.V / ".system" / "upgrade-history.json").write_text(json.dumps(h), encoding="utf-8")
        self.serve("0.20.0")
        code, out = run_inproc(["upgrade", "--check", "--json"], self.V)
        got = json.loads(out)
        self.assertEqual((got["kind"], got["snapshot_for_downgrade"]), ("downgrade", snap.name))
        self.assertIn("restore", got)
        code, out = run_inproc(["upgrade", "--downgrade"], self.V)
        self.assertEqual((code, out.strip()), (0, "已回到 0.20.0 的知識庫，也換回 0.20.0；開一個新對話就好。"))

    def test_downgrade_without_snapshot_exit_3(self):
        self.PLUGIN = "0.21.0"
        self.put_history("0.21.0")
        self.serve("0.20.0")
        self.assertEqual(run_inproc(["upgrade", "--downgrade"], self.V),
                         (3, "升級前的快照已經不在，不能退回；請服務人員幫忙\n"))

    def test_only_one_mode_at_a_time(self):
        code, out = run_inproc(["upgrade", "--check", "--finish"], self.V)
        self.assertEqual(code, 3)
        self.assertIn("一次只能用一個", out)


class Finish(Base):
    PLUGIN = "0.21.0"

    def setUp(self):
        super().setUp()
        self.root_sk = self.tmp / "skeleton"
        (self.root_sk / ".claude").mkdir(parents=True)
        (self.root_sk / "CLAUDE.md").write_text("新版身分\n", encoding="utf-8", newline="\n")
        (self.root_sk / ".claude" / "settings.json").write_text("{}\n", encoding="utf-8", newline="\n")
        from kb import init
        self.sk = [mock.patch.object(skeleton, "skeleton_root", return_value=self.root_sk),
                   mock.patch.object(init, "skeleton_root", return_value=self.root_sk),
                   mock.patch.object(skeleton, "history", return_value={})]
        for p in self.sk:
            p.start()
        shutil.rmtree(self.V / ".claude", ignore_errors=True)  # fixture 自帶的骨架檔不是骨架原樣，會被當成她改過

    def tearDown(self):
        for p in self.sk:
            p.stop()
        super().tearDown()

    def pend(self):
        self.put_history("0.20.1", pending={"to": "0.21.0", "snapshot": backup.snapshot(self.V, "upgrade").name,
                                            "started": "2026-10-24T10:00:00"})

    def test_human_first_line_and_exit_0(self):
        self.pend()
        (self.V / "CLAUDE.md").unlink()
        code, out = run_inproc(["upgrade", "--finish"], self.V)
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(lines[0], "已升到 0.21.0：日程可以匯出成 Excel。")
        self.assertIn("補上骨架：CLAUDE.md", lines)

    def test_patch_first_line_wording(self):
        self.PLUGIN = "0.20.2"
        self.put_history("0.20.1")
        code, out = run_inproc(["upgrade", "--finish"], self.V)
        self.assertEqual(out.splitlines()[0], "已自動套用小修正 0.20.2：修好日程匯出的日期錯誤。")

    def test_already(self):
        self.put_history("0.21.0")
        self.assertEqual(run_inproc(["upgrade", "--finish"], self.V), (0, "已經是 0.21.0\n"))

    def test_first_time_says_already_and_records(self):
        self.assertEqual(run_inproc(["upgrade", "--finish"], self.V), (0, "已經是 0.21.0\n"))
        self.assertEqual(self.history()["current"], "0.21.0")

    def test_json_keys_and_ask_lines(self):
        self.pend()
        (self.V / "CLAUDE.md").write_text("她加了一行\n", encoding="utf-8", newline="\n")
        (self.V / ".system" / "skeleton.json").write_text(json.dumps(
            {"schema_version": 1, "version": "0.20.1", "files": {"CLAUDE.md": "0" * 64}}), encoding="utf-8")
        code, out = run_inproc(["upgrade", "--finish", "--json"], self.V)
        got = json.loads(out)
        self.assertEqual(code, 0)
        for key in ("from", "to", "kind", "snapshot", "migrated", "cards_migrated", "skeleton_replaced", "skeleton_ask", "note"):
            self.assertIn(key, got)
        self.assertEqual((got["from"], got["to"], got["kind"], got["note"]), ("0.20.1", "0.21.0", "minor", "日程可以匯出成 Excel。"))
        self.assertEqual(got["skeleton_ask"], ["CLAUDE.md"])
        self.assertTrue(got["ok"])
        code, out = run_inproc(["upgrade", "--finish"], self.V)  # 已經轉過，再跑是「已經是」；要問的在第一次的輸出
        self.assertEqual(out.strip(), "已經是 0.21.0")

    def test_ask_line_names_the_file_and_the_two_commands(self):
        self.pend()
        (self.V / "CLAUDE.md").write_text("她加了一行\n", encoding="utf-8", newline="\n")
        (self.V / ".system" / "skeleton.json").write_text(json.dumps(
            {"schema_version": 1, "version": "0.20.1", "files": {"CLAUDE.md": "0" * 64}}), encoding="utf-8")
        _code, out = run_inproc(["upgrade", "--finish"], self.V)
        ask = [ln for ln in out.splitlines() if ln.startswith("要問她：")]
        self.assertEqual(len(ask), 1)
        self.assertIn("CLAUDE.md", ask[0])
        self.assertIn("--keep", ask[0])
        self.assertIn("--replace", ask[0])
        self.assertEqual(out.splitlines()[-1], ask[0], "要問的放最後")

    def test_busy_lock_exit_3(self):
        self.pend()
        with backup.acquire(self.V):
            code, out = run_inproc(["upgrade", "--finish"], self.V)
        self.assertEqual((code, out.strip()), (3, "另一個備份、還原或退回正在跑，等它做完"))

    def test_migrated_files_listed(self):
        from tests._guard_fixture import FIXTURES
        self.pend()
        shutil.copy2(FIXTURES / "profile" / "schema1.json", self.V / ".system" / "profile.json")
        shutil.copy2(FIXTURES / "profile" / "schema1.md", self.V / "系統" / "客戶設定檔.md")
        _code, out = run_inproc(["upgrade", "--finish"], self.V)
        self.assertIn("轉成新格式：.system/profile.json", out.splitlines())

    def test_terminal_run_writes_a_program_journal_line(self):
        """終端機跑的記一段程式段（D-085）；對話裡叫的不記。"""
        self.pend()
        run_inproc(["upgrade", "--finish"], self.V)
        months = list((self.V / ".system" / "journal").glob("*.jsonl"))
        self.assertTrue(months)
        self.assertIn("upgrade --finish", months[0].read_text(encoding="utf-8"))


class Skeleton(Base):
    PLUGIN = "0.21.0"

    def setUp(self):
        super().setUp()
        self.root_sk = self.tmp / "skeleton"
        self.root_sk.mkdir()
        (self.root_sk / "CLAUDE.md").write_text("新版身分\n", encoding="utf-8", newline="\n")
        self.sk = [mock.patch.object(skeleton, "skeleton_root", return_value=self.root_sk),
                   mock.patch.object(skeleton, "history", return_value={})]
        for p in self.sk:
            p.start()
        (self.V / "CLAUDE.md").write_text("她加了一行\n", encoding="utf-8", newline="\n")

    def tearDown(self):
        for p in self.sk:
            p.stop()
        super().tearDown()

    def test_keep(self):
        code, out = run_inproc(["upgrade", "skeleton", "CLAUDE.md", "--keep"], self.V)
        self.assertEqual((code, out.strip()), (0, "好了，保留你改的 CLAUDE.md。"))
        self.assertEqual((self.V / "CLAUDE.md").read_text(encoding="utf-8"), "她加了一行\n")
        self.assertIn("CLAUDE.md", skeleton.recorded(self.V)["files"])

    def test_replace_backs_up_hers(self):
        code, out = run_inproc(["upgrade", "skeleton", "CLAUDE.md", "--replace"], self.V)
        self.assertEqual((code, out.strip()), (0, "好了，CLAUDE.md 換成新版了；你改的那份備在這一回合裡，說「退回」就回來。"))
        self.assertEqual((self.V / "CLAUDE.md").read_text(encoding="utf-8"), "新版身分\n")
        saved = list((self.V / ".system" / "versions").glob("*/files/CLAUDE.md"))
        self.assertEqual([p.read_text(encoding="utf-8") for p in saved], ["她加了一行\n"])

    def test_unknown_file_exit_3(self):
        code, out = run_inproc(["upgrade", "skeleton", "系統/日程.md", "--keep"], self.V)
        self.assertEqual((code, out.strip()), (3, "這不是骨架檔：系統/日程.md"))

    def test_needs_exactly_one_of_keep_replace(self):
        for extra in ([], ["--keep", "--replace"]):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    run_inproc(["upgrade", "skeleton", "CLAUDE.md", *extra], self.V)


class Background(Base):
    def test_silent_and_records(self):
        self.serve("0.21.0")
        code, out = run_inproc(["upgrade", "--background"], self.V)
        self.assertEqual((code, out), (0, ""))
        self.assertEqual(env.update_check(self.V)["latest"], "0.21.0")

    def test_offline_still_silent_exit_0(self):
        self.fake.texts[MANIFEST_URL] = OSError("斷線")
        self.assertEqual(run_inproc(["upgrade", "--background"], self.V), (0, ""))

    def test_outside_a_vault_is_silent_exit_0(self):
        self.assertEqual(run_inproc(["upgrade", "--background"], self.tmp), (0, ""))


class Subprocess(unittest.TestCase):
    """不用網路的黑箱：真的 kb.py、真的骨架；清單網址是預設的空字串，所以查不到。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kbupg-")).resolve()
        self.V = self.tmp / "知識庫"
        r = run_kb("init", str(self.V), cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_check_without_urls_says_offline_exit_0(self):
        r = run_kb("upgrade", "--check", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "現在連不上更新的地方，晚點再問。"))

    def test_finish_right_after_init_says_already(self):
        manifest_version = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
        r = run_kb("upgrade", "--finish", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, f"已經是 {manifest_version}"))

    def test_background_with_empty_url_is_silent_and_writes_nothing(self):
        before = _backup.tree(self.V)
        r = run_kb("upgrade", "--background", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertEqual(_backup.tree(self.V), before)

    def test_help_lists_upgrade(self):
        self.assertIn("upgrade", run_kb("--help", cwd=self.V).stdout)


if __name__ == "__main__":
    unittest.main()
