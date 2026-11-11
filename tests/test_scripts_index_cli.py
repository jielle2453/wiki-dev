"""kb index rebuild 與卡片索引接上各指令（#57，D-345）：黑箱 subprocess。驗收 2～9。"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from tests import _cards
from tests import _entities as E
from tests._guard_fixture import ROOT
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import card_index, cards, find, lookup  # noqa: E402
from kb._lib import vault as vault_lib  # noqa: E402


def snapshot(V):
    return sorted(str(p.relative_to(V)) for p in Path(V).rglob("*") if p.is_file())


class IndexCli(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        vault_lib.ensure_vault_id(self.V)
        item = E.new_item(self.V, E.QUOTE)
        text = E.with_entities(_cards.card_text(item, "報價單", body="交期三週。含水電工程。〔第 1 段〕\n", kind="報價", date="2026-09-12"), ["信義王"])
        self.path = _cards.card_path(self.V, item, "報價單")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(text, encoding="utf-8", newline="\n")
        self.rel = self.path.relative_to(self.V).as_posix()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def files(self, *words):
        return [f["card_path"] for f in json.loads(run_kb("find", *words, "--json", cwd=self.V).stdout)["files"]]

    def test_rebuild_human_and_json(self):
        n = len(cards._scan_groups_files(self.V)[0]) + len(cards._scan_groups_files(self.V)[1])
        r = run_kb("index", "rebuild", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout.strip(), rf"^索引重建好了：{n} 張卡，[0-9.]+ 秒$")
        r = run_kb("index", "rebuild", "--json", cwd=self.V)
        out = json.loads(r.stdout)
        self.assertEqual((set(out), out["cards"]), ({"cards", "seconds"}, n))

    def test_rebuild_without_vault_id_exits_1(self):
        os.remove(self.V / ".system" / "vault.json")
        r = run_kb("index", "rebuild", cwd=self.V)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("沒有編號", r.stdout)

    def test_two_char_word_only_in_body(self):  # 驗收 3
        out = json.loads(run_kb("find", "交期", "--json", cwd=self.V).stdout)
        self.assertEqual([(f["card_path"], f["hit"]) for f in out["files"]], [(self.rel, "body")])

    def test_find_follows_edit_and_matches_without_index(self):  # 驗收 2(a)、結果不變
        self.assertEqual(self.files("交期"), [self.rel])
        self.path.write_text(self.path.read_text(encoding="utf-8").replace("交期三週", "出貨三週"), encoding="utf-8", newline="\n")
        self.assertEqual(self.files("交期"), [])
        self.assertEqual(self.files("出貨"), [self.rel])
        os.remove(vault_lib._path(self.V))  # 沒有編號：不走索引，結果要一樣
        self.assertEqual(self.files("出貨"), [self.rel])
        self.assertEqual(self.files("交期"), [])

    def test_index_unusable_still_exit_0(self):  # 驗收 4：亂碼、版本不對
        self.files("交期")
        db = card_index.db_path(self.V)
        db.write_bytes(b"garbage" * 100)
        r = run_kb("find", "交期", "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([f["card_path"] for f in json.loads(r.stdout)["files"]], [self.rel])
        con = sqlite3.connect(db)
        self.assertEqual(con.execute("select v from meta where k='schema_version'").fetchone(), ("1",))
        con.execute("update meta set v='2' where k='schema_version'")
        con.commit()
        con.close()
        r = run_kb("lookup", "交期", "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([m["path"] for m in json.loads(r.stdout)["mentions"]], [self.rel])
        log = self.V / ".system" / "hook-errors.log"
        self.assertLessEqual(len([l for l in log.read_text(encoding="utf-8").splitlines() if "\tindex\t" in l]) if log.exists() else 0, 2)

    def test_nothing_new_in_vault(self):  # 驗收 5
        before = snapshot(self.V)
        run_kb("find", "交期", cwd=self.V)
        run_kb("changes", "--background", cwd=self.V)
        run_kb("index", "rebuild", cwd=self.V)
        run_kb("lookup", "交期", cwd=self.V)
        run_kb("cards", "list", cwd=self.V)
        after = snapshot(self.V)
        self.assertEqual([p for p in after if p not in before and not p.startswith(".system")], [])
        self.assertTrue(card_index.db_path(self.V).exists())
        self.assertEqual(card_index.db_path(self.V).parent, Path(os.environ["WIKI_WITH_WILLY_INDEX_DIR"]))

    def test_read_only_commands_walk_once(self):  # 驗收 6
        real = card_index.changed
        calls = []

        def counting(*a, **k):
            calls.append(1)
            return real(*a, **k)

        from kb import cards as cards_cli, find_cli, lookup_cli
        import argparse

        def run(module, **kw):
            del calls[:]
            with mock.patch.object(card_index, "changed", counting):
                with mock.patch("builtins.print"):
                    module.run(argparse.Namespace(vault=str(self.V), **kw))
            return len(calls)

        self.assertEqual(run(find_cli, query="信義王 報價"), 1)
        self.assertEqual(run(find_cli, query="交期 完全不存在的東西"), 1)
        self.assertEqual(run(lookup_cli, name="信義王", id=None), 1)
        self.assertEqual(run(lookup_cli, name="交期", id=None), 1)
        self.assertEqual(run(cards_cli, cards_command="list", type=[], year=None, entity=[], source=None), 1)

    def test_background_updates_index(self):  # 驗收 7
        self.files("交期")
        item = E.new_item(self.V, E.QUOTE) if False else None
        new = self.path.with_name("另一張.md")
        new.write_text(self.path.read_text(encoding="utf-8").replace("f-", "f-9", 1).replace("報價單", "另一張"), encoding="utf-8", newline="\n")
        env = dict(os.environ)
        r = run_kb("changes", "--background", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        con = sqlite3.connect(card_index.db_path(self.V))
        self.assertEqual(con.execute("select count(*) from cards where path = ?", (new.relative_to(self.V).as_posix(),)).fetchone(), (1,))
        con.close()

    def test_cards_index_same_text(self):  # 驗收 9：總目錄逐字不變（含 broken 的卡、圖示開與關）
        bad = self.V / "檔案索引" / "壞檔頭.md"
        bad.write_text("---\n編號 f-x\n---\n內文\n", encoding="utf-8", newline="\n")
        nonum = self.V / "檔案索引" / "沒編號.md"
        nonum.write_text("---\n標題: 沒編號但有標題\n原檔: [a.pdf]\n---\n內文\n", encoding="utf-8", newline="\n")
        for icons in (True, False):
            from kb._lib import config
            with mock.patch.object(config, "get", side_effect=lambda v, k, _g=config.get: icons if k == "index_icons" else _g(v, k)):
                with mock.patch.object(card_index, "groups", return_value=None):
                    cards._render_index(self.V, None)
                    old = (self.V / "總目錄.md").read_text(encoding="utf-8")
                cards._render_index(self.V, None)
                new = (self.V / "總目錄.md").read_text(encoding="utf-8")
            self.assertEqual(new, old)
            self.assertIn("沒編號但有標題", new)

    def same_as_files(self):
        got = card_index.groups(self.V)
        self.assertIsNotNone(got)
        self.assertEqual(got, cards._scan_groups_files(self.V))

    def age(self):
        """卡的修改時間設成兩小時前：寫進索引時不算「剛改」，之後的改動靠修改時間、大小抓到。"""
        t = time.time() - 7200
        os.utime(self.path, (t, t))

    def test_entity_rename_follows(self):  # 驗收 2(c)：真的跑 kb entity rename（改很多張的檔頭）
        self.age()
        self.assertEqual(self.files("信義王"), [self.rel])
        self.same_as_files()
        r = run_kb("entity", "rename", "信義王", "--to", "信義王宅邸", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("信義王宅邸", self.path.read_text(encoding="utf-8"))
        self.assertEqual(self.files("信義王宅邸"), [self.rel])
        self.same_as_files()
        self.assertEqual(card_index.groups(self.V)[0][next(iter(card_index.groups(self.V)[0]))][0]["front"]["實體"], ["信義王宅邸"])

    def test_versions_revert_follows(self):  # 驗收 2(d)：真的跑 kb versions revert（退回一句做卡的話）
        from tests import test_cardmaker_revert as R
        sid = "sid-index"

        def hook(name, data):
            env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))
            r = subprocess.run([sys.executable, str(ROOT / "hooks" / name)], input=json.dumps(data, ensure_ascii=False),
                               capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT), env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            return r.stdout

        def prompt(text):
            hook("turn.py", {"session_id": sid, "cwd": str(self.V), "prompt": text, "hook_event_name": "UserPromptSubmit"})

        def tool(event, path):
            return hook("guard.py" if event == "PreToolUse" else "output_log.py", {
                "session_id": sid, "cwd": str(self.V), "hook_event_name": event, "tool_name": "Write",
                "tool_input": {"file_path": str(path)}})

        self.age()
        self.assertEqual(self.files("新卡獨特詞"), [])  # 索引建好
        prompt("好，整理這份")
        item = E.new_item(self.V, _cards.MEETING)
        new = _cards.card_path(self.V, item, "會議紀錄")
        self.assertIn('"allow"', tool("PreToolUse", new))
        new.parent.mkdir(parents=True, exist_ok=True)
        new.write_text(_cards.card_text(item, "會議紀錄", body="新卡獨特詞。\n"), encoding="utf-8", newline="\n")
        self.assertEqual(tool("PostToolUse", new), "")
        newrel = new.relative_to(self.V).as_posix()
        self.assertEqual(self.files("新卡獨特詞"), [newrel])
        self.same_as_files()
        prompt("退回上一句")
        r = run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(new.exists())
        self.assertEqual(self.files("新卡獨特詞"), [])
        self.same_as_files()


if __name__ == "__main__":
    unittest.main()
