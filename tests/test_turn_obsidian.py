"""--via obsidian（#22 Obsidian 首頁，D-255、D-264）：Obsidian 的改動自己開回合、自成一組。
驗收準則 5（回答中不併進對話、日誌抬頭）、6（退回分組）、7（清理不算回合數上限）。"""
import json
import os
import re
import subprocess
import sys
import unittest
from datetime import datetime, timedelta

from tests._guard_fixture import KB, ROOT
from tests.test_versions_sessions import A, B, Base
from kb._lib import clean, turn  # noqa: E402


class ViaBase(Base):
    def kbv(self, *args, via=True, sid=None):
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))
        head = (["--via", "obsidian"] if via else []) + (["--session", sid] if sid else [])
        return subprocess.run([sys.executable, str(KB), *head, *args], capture_output=True, text=True,
                              encoding="utf-8", cwd=str(self.V), env=env)

    def agenda_via(self, text, date="2026-11-26"):
        r = self.kbv("agenda", "add", "--kind", "提醒", "--date", date, "--text", text)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def versions(self):
        root = self.V / ".system" / "versions"
        out = {}
        for d in sorted(root.iterdir()) if root.is_dir() else []:
            meta = json.loads((d / "turn.json").read_text(encoding="utf-8"))
            out[d.name] = meta
        return out

    def obsidian_turns(self):
        return [t for t, m in self.versions().items() if m.get("source") == "obsidian"]

    def manifest_paths(self, turn_id):
        p = self.V / ".system" / "versions" / turn_id / "manifest.jsonl"
        return [json.loads(x)["path"] for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.is_file() else []


class OwnTurn(ViaBase):
    def test_5_during_answer_new_turn_not_merged(self):
        t_a = self.prompt(A, "11/25 有個會")
        before_cur = (self.V / ".system" / "turns" / "current.json").read_bytes()
        before_a = (self.V / ".system" / "turns" / f"{A}.json").read_bytes()
        self.agenda_via("在 Obsidian 加的")
        got = self.obsidian_turns()
        self.assertEqual(len(got), 1, self.versions())
        self.assertTrue(got[0].endswith("-obsd"), got[0])
        self.assertIn(".system/agenda.json", self.manifest_paths(got[0]))
        self.assertNotIn(".system/agenda.json", self.manifest_paths(t_a))
        self.assertEqual((self.V / ".system" / "turns" / "current.json").read_bytes(), before_cur)  # 不讀不寫 current.json
        self.assertEqual((self.V / ".system" / "turns" / f"{A}.json").read_bytes(), before_a)
        self.assertNotEqual(got[0], t_a)

    def test_5_journal_label(self):
        self.prompt(A, "問一句")
        self.agenda_via("日誌這句")
        r = self.kbv("journal", "recent", "--n", "3", via=False)
        self.assertIn("你在 Obsidian 按的", r.stdout, r.stdout)
        self.assertNotIn("你在終端機跑的", r.stdout)
        month = datetime.now().strftime("%Y-%m")
        md = (self.V / "系統" / "工作日誌" / f"{month}.md").read_text(encoding="utf-8")
        self.assertIn("你在 Obsidian 按的", md)
        self.assertNotIn("程式 agenda add", md)

    def test_terminal_label_unchanged(self):
        self.kbv("agenda", "add", "--kind", "提醒", "--date", "2026-11-26", "--text", "終端機", via=False)
        r = self.kbv("journal", "recent", "--n", "3", via=False)
        self.assertIn("你在終端機跑的", r.stdout)
        self.assertNotIn("Obsidian", r.stdout)

    def test_one_call_one_turn(self):
        turn.VIA = "obsidian"
        try:
            t1 = turn.current(self.V)
            t2 = turn.current(self.V)
            self.assertEqual(t1["turn"], t2["turn"])
            self.assertEqual(t1["source"], "obsidian")
            self.assertTrue(turn.now(self.V)["turn"] == t1["turn"])
            self.assertIsNone(turn.last(self.V))
            self.assertFalse(turn.in_conversation(self.V))
            self.assertFalse(turn.mark(self.V, "ingest"))
            self.assertFalse(turn.touch(self.V, entities=["王先生"]))
        finally:
            turn.VIA = None
            turn._VIA_TURNS.clear()

    def test_read_only_call_opens_no_turn(self):
        before = set(self.versions())
        r = self.kbv("agenda", "list")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(set(self.versions()), before)

    def test_value_other_than_obsidian_refused(self):
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))
        r = subprocess.run([sys.executable, str(KB), "--via", "web", "version"], capture_output=True, text=True,
                           encoding="utf-8", cwd=str(self.V), env=env)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("obsidian", r.stdout)

    def test_help_does_not_list_via(self):
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))
        r = subprocess.run([sys.executable, str(KB), "--help"], capture_output=True, text=True, encoding="utf-8",
                           cwd=str(self.V), env=env)
        self.assertNotIn("--via", r.stdout)


class Groups(ViaBase):
    def setUp(self):
        super().setUp()
        self.prompt(A, "我習慣週五對帳，記下來")
        self.assertEqual(self.kb("entity", "add", "--type", "案子", "--name", "信義王", sid=A).returncode, 0)
        r = self.kb("statement", "add", "--entity", "信義王", "--text", "我習慣週五對帳", sid=A)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.stop(A)
        self.agenda_via("Obsidian 加的一條")  # 比對話那句晚：「最近一次」是 Obsidian 的

    def test_6_conversation_revert_skips_obsidian(self):
        self.prompt(A, "退回")
        r = self.kb("versions", "revert", sid=A)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Obsidian 加的一條", self.agenda_texts())  # Obsidian 的沒被退
        self.assertNotIn("我習慣週五對帳", self.kb("statement", "list", sid=A).stdout)

    def test_6_via_revert_only_obsidian(self):
        self.agenda_via("Obsidian 再加一條", date="2026-11-27")
        r = self.kbv("versions", "revert")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Obsidian 再加一條", self.agenda_texts())
        self.assertIn("Obsidian 加的一條", self.agenda_texts())
        self.assertIn("我習慣週五對帳", self.kb("statement", "list", sid=A).stdout)  # 對話的沒動

    def test_6_via_revert_with_none_of_its_own(self):
        import shutil
        for t in self.obsidian_turns():
            shutil.rmtree(self.V / ".system" / "versions" / t)
        r = self.kbv("versions", "revert")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("沒有可以退回的改動", r.stdout)
        self.assertIn("我習慣週五對帳", self.kb("statement", "list", sid=A).stdout)

    def test_6_terminal_sees_all(self):
        r = self.kbv("versions", "revert", via=False)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Obsidian 加的一條", self.agenda_texts())  # 終端機照舊挑最近的，就是 Obsidian 那個

    def test_via_revert_leaves_current_json_alone(self):
        self.prompt(B, "別的對話正在答")
        before = (self.V / ".system" / "turns" / "current.json").read_bytes()
        r = self.kbv("versions", "revert")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.V / ".system" / "turns" / "current.json").read_bytes(), before)

    def test_list_marks_obsidian(self):
        r = self.kbv("versions", "list", via=False)
        self.assertIn("（Obsidian）", r.stdout, r.stdout)
        out = subprocess.run([sys.executable, str(KB), "versions", "list", "--json"], capture_output=True, text=True,
                             encoding="utf-8", cwd=str(self.V), env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)))
        rows = json.loads(out.stdout)
        self.assertEqual(sorted({r.get("source") or "" for r in rows}), ["", "obsidian"])

    def test_list_in_conversation_hides_obsidian_without_calling_it_another_conversation(self):
        r = self.kbv("versions", "list", via=False, sid=A)
        self.assertNotIn("Obsidian", r.stdout)
        self.assertNotIn("另一個對話", r.stdout)

    def test_list_via_shows_only_obsidian(self):
        r = self.kbv("versions", "list")
        self.assertIn("（Obsidian）", r.stdout)
        self.assertNotIn("週五對帳", r.stdout)


def _make_turns(V, count, days_ago, source=None, prefix="t"):
    root = V / ".system" / "versions"
    now = datetime.now().replace(microsecond=0)
    ids = []
    for i in range(count):
        started = now - timedelta(days=days_ago, seconds=count - i)
        tid = f"{started:%Y%m%d-%H%M%S}-{prefix}{i:03d}"
        folder = root / tid
        folder.mkdir(parents=True)
        meta = {"schema_version": 1, "turn": tid, "started": started.strftime("%Y-%m-%dT%H:%M:%S"),
                "prompt_head": f"句{i}", "done": True}
        if source:
            meta["source"] = source
        (folder / "turn.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        (folder / "manifest.jsonl").write_text("", encoding="utf-8")
        ids.append(tid)
    return ids


class Clean(ViaBase):
    def count(self, source):
        return sum(1 for m in self.versions().values() if (m.get("source") or "") == source)

    def test_7_obsidian_turns_not_counted_in_limit(self):
        _make_turns(self.V, 250, 2, source="obsidian", prefix="obsd")
        _make_turns(self.V, 30, 1, prefix="conv")
        got = clean.run(self.V)
        self.assertEqual(got["turns_removed"], 0)
        self.assertEqual(self.count("obsidian"), 250)
        self.assertEqual(self.count(""), 30)

    def test_7_conversation_turns_keep_200_limit(self):
        _make_turns(self.V, 250, 2, source="obsidian", prefix="obsd")
        _make_turns(self.V, 210, 1, prefix="conv")
        got = clean.run(self.V)
        self.assertEqual(got["turns_removed"], 10)
        self.assertEqual(self.count("obsidian"), 250)
        self.assertEqual(self.count(""), 200)

    def test_7_obsidian_turns_still_go_after_keep_days(self):
        _make_turns(self.V, 5, 40, source="obsidian", prefix="obsd")
        _make_turns(self.V, 30, 1, prefix="conv")
        got = clean.run(self.V)
        self.assertEqual(got["turns_removed"], 5)
        self.assertEqual(self.count("obsidian"), 0)

    def test_7_min_turns_counts_only_conversation_ones(self):
        _make_turns(self.V, 5, 40, prefix="conv")  # 對話的舊回合只有 5 個，不到 20 個下限：留著
        _make_turns(self.V, 30, 40, source="obsidian", prefix="obsd")  # Obsidian 的過了 30 天：都清
        got = clean.run(self.V)
        self.assertEqual(got["turns_removed"], 30)
        self.assertEqual(self.count(""), 5)


if __name__ == "__main__":
    unittest.main()
