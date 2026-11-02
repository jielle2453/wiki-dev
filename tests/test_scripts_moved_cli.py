"""kb moved 黑箱（備份還原與換電腦 驗收 15～17）：subprocess 跑 kb.py；知識庫搬到另一處、env.json 記舊位置。"""
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests import _backup, _cards
from tests._guard_fixture import KB, ROOT
from kb._lib import cards, env, unlock, vault as vault_lib  # noqa: E402
from kb._lib import sources as sources_lib  # noqa: E402

HOOK = ROOT / "hooks" / "session.py"


def run_kb(*args, cwd):
    envv = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(KB), *args], capture_output=True, text=True,
                          encoding="utf-8", cwd=str(cwd), env=envv)


def opening(cwd):
    envv = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))
    raw = json.dumps({"session_id": "abc", "cwd": str(cwd), "source": "startup", "hook_event_name": "SessionStart"})
    r = subprocess.run([sys.executable, str(HOOK)], input=raw, capture_output=True, text=True, encoding="utf-8",
                       cwd=str(ROOT), env=envv)
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"].split("\n\n", 1)[0].split("\n")


def posix(p):
    return Path(os.path.realpath(str(p))).as_posix()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _cards.make_card_vault()
        todo = cards.todo(self.V, sources_lib.load(self.V))["new"]
        item = next(i for i in todo if i["id"] == _cards.entry_of(self.V, _cards.MEETING)["id"])
        _cards.write_card(self.V, item, "大安陳會議一")
        vault_lib.ensure_vault_id(self.V)
        env.set_vault_path(self.V, posix(self.V))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def move_together(self, keep_old=False):
        base = self.tmp / "D槽"
        base.mkdir()
        shutil.copytree(self.V, base / "知識庫")
        shutil.copytree(self.raw, base / "raw")
        if not keep_old:
            shutil.rmtree(self.V)
            shutil.rmtree(self.raw)
        return base / "知識庫"

    def card_link(self, vault):
        card = next((vault / "檔案索引").rglob("大安陳會議一-*.md"))
        return cards.parse_front(card.read_text(encoding="utf-8"))["開原檔"]


class Moved(Base):
    def test_check_then_apply_then_quiet(self):
        NV = self.move_together()
        link_before = self.card_link(NV)
        self.assertIn("知識庫換了位置：先跑 kb moved 補好再做別的。", opening(NV))
        before = _backup.tree(NV)
        r = run_kb("moved", "--check", "--json", cwd=NV)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout)
        self.assertEqual((got["state"], got["from"], got["to"]), ("moved", posix(self.V), posix(NV)))
        self.assertEqual(got["cards_relinked"], 1)
        self.assertEqual(got["missing_sources"], [])
        self.assertEqual(_backup.tree(NV), before, "--check 不動任何東西")
        r = run_kb("moved", cwd=NV)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertIn("卡的開原檔連結更新了 1 張", r.stdout)
        self.assertNotEqual(self.card_link(NV), link_before)
        self.assertEqual(env.vault_path(NV), posix(NV))
        self.assertNotIn("知識庫換了位置：先跑 kb moved 補好再做別的。", opening(NV))
        self.assertEqual(json.loads(run_kb("moved", "--json", cwd=NV).stdout)["state"], "same")

    def test_revert_gives_the_old_links_back(self):
        NV = self.move_together()
        link_before = self.card_link(NV)
        sources_before = (NV / ".system" / "sources.json").read_bytes()
        self.assertEqual(run_kb("moved", cwd=NV).returncode, 0)
        r = run_kb("versions", "revert", cwd=NV)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self.card_link(NV), link_before)
        self.assertEqual((NV / ".system" / "sources.json").read_bytes(), sources_before)

    def test_vault_alone_rewrites_sources_and_finds_them(self):
        base = self.tmp / "D槽"
        base.mkdir()
        shutil.copytree(self.V, base / "知識庫")
        shutil.rmtree(self.V)
        NV = base / "知識庫"
        r = run_kb("moved", "--json", cwd=NV)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        got = json.loads(r.stdout)
        self.assertEqual(len(got["sources_rewritten"]), 3)
        for e in sources_lib.load(NV).entries:
            self.assertTrue(Path(e["root"]).is_dir(), e["root"])

    def test_old_copy_reported_but_never_deleted(self):
        NV = self.move_together(keep_old=True)
        got = json.loads(run_kb("moved", "--check", "--json", cwd=NV).stdout)
        self.assertEqual(got["old_copy"], posix(self.V))
        r = run_kb("moved", cwd=NV)
        self.assertIn(f"舊位置還有一份：{posix(self.V)}", r.stdout)
        self.assertIn(f"問使用者一句要不要刪舊的，說好就 kb source-edit trash {posix(self.V)}。", r.stdout)
        self.assertTrue(self.V.is_dir())
        (self.V / ".system" / "vault.json").write_text(json.dumps(
            {"schema_version": 1, "vault_id": "kb-ffffffff"}), encoding="utf-8")
        self.assertIsNone(json.loads(run_kb("moved", "--check", "--json", cwd=NV).stdout)["old_copy"])

    def test_not_a_vault(self):
        r = run_kb("moved", cwd=self.tmp)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "這裡不是知識庫"))

    def test_same_place_says_nothing_to_do(self):
        r = run_kb("moved", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "位置沒變，沒有要補的"))


class NewMachine(Base):
    def test_other_machine_only(self):
        (self.V / ".system" / "env.json").write_text(json.dumps(
            {"schema_version": 1, "machines": {"OLD-PC": {"vault_path": "D:/lin/知識庫"}}}), encoding="utf-8")
        self.assertIn("這台電腦第一次開這個知識庫：先跑 kb moved 看要補什麼。", opening(self.V))
        got = json.loads(run_kb("moved", "--check", "--json", cwd=self.V).stdout)
        self.assertEqual(got["state"], "new_machine")
        self.assertIn("env", got)
        self.assertIn("passwords_missing", got)
        r = run_kb("moved", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(env.vault_path(self.V), posix(self.V))
        data = json.loads((self.V / ".system" / "env.json").read_text(encoding="utf-8"))
        self.assertIn("OLD-PC", data["machines"])


if __name__ == "__main__":
    unittest.main()
