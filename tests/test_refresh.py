"""kb refresh（多人共用 3 驗收 2、5、6、8）：真 git，本機裸 repo＋兩份 clone，不連網。"""
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests import _cards, _gitfix as gf
from tests._guard_fixture import KB, ROOT
from kb._lib import card_base, cards, git, refresh, turn  # noqa: E402
from kb._lib import sources as sources_lib  # noqa: E402

IGNORE = "系統/\n總目錄.md\n.system/renders.json\n.system/local/\n.system/versions/\n.system/turns/\n.system/temp/\n.system/hook-errors.log\n.system/*.lock\n*.lock\n"


def tid(v):
    return turn.start(v, None, "")["turn"]


@unittest.skipUnless(gf.have_git(), "沒有 git")
class RefreshBase(unittest.TestCase):
    def setUp(self):
        self.tmp, self.A, self.raw = _cards.make_card_vault()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bare = self.tmp / "origin.git"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(self.bare)], check=True, capture_output=True, env=gf.ENV)
        gf.write(self.A, ".gitignore", IGNORE)
        gf.must(self.A, "init", "-b", "main")
        gf.must(self.A, "add", "-A")
        gf.must(self.A, "commit", "-m", "init", who="甲")
        gf.must(self.A, "remote", "add", "origin", str(self.bare))
        gf.must(self.A, "push", "-u", "origin", "main")
        self.B = self.tmp / "B"
        subprocess.run(["git", "clone", str(self.bare), str(self.B)], check=True, capture_output=True, env=gf.ENV)
        gf.must(self.B, "config", "merge.conflictstyle", "merge")
        self.B_env = mock.patch.dict(os.environ, gf.ENV)
        self.B_env.start()
        self.addCleanup(self.B_env.stop)

    def commit_push(self, repo, msg, who):
        gf.must(repo, "add", "-A")
        gf.must(repo, "commit", "-m", msg, who=who)
        gf.must(repo, "push")


class RefreshTest(RefreshBase):
    def test_not_repo_does_nothing(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        self.assertEqual(refresh.run(plain), refresh.empty())

    def test_pull_rerenders_and_records_head(self):
        refresh.run(self.B, tid(self.B))
        old = refresh.read_last_head(self.B)
        self.assertEqual(old, git.head(self.B))
        self.assertFalse(refresh.head_changed(self.B))
        gf.write(self.A, "行事曆說明.txt", "新的\n")
        self.commit_push(self.A, "a", "甲")
        gf.must(self.B, "pull", "--no-rebase")
        self.assertTrue(refresh.head_changed(self.B))
        got = refresh.run(self.B, tid(self.B))
        self.assertEqual(got["pulled"], ["行事曆說明.txt"])
        self.assertIn("總目錄.md", got["rendered"])
        self.assertTrue((Path(self.B) / "總目錄.md").is_file())
        self.assertFalse(refresh.head_changed(self.B))
        self.assertFalse(refresh.run(self.B, tid(self.B))["pulled"])  # 沒新東西

    def test_second_runner_skips(self):
        (Path(self.B) / ".system" / "local").mkdir(parents=True, exist_ok=True)
        from kb._lib.io import FileLock
        with FileLock(Path(self.B) / ".system" / "local" / "refresh"):
            self.assertTrue(refresh.run(self.B, "t")["skipped"])

    def test_file_conflict_keeps_mine_and_copies_theirs(self):
        gf.write(self.A, "報價單.docx", "甲\n")
        self.commit_push(self.A, "a", "小王")
        gf.write(self.B, "報價單.docx", "乙\n")
        gf.must(self.B, "add", "-A")
        gf.must(self.B, "commit", "-m", "b", who="我")
        gf.git(self.B, "pull", "--no-rebase", "--no-edit")
        self.assertTrue(git.merge_in_progress(self.B))
        got = refresh.run(self.B, tid(self.B))
        self.assertEqual(got["conflicts"], [{"path": "報價單.docx", "kind": "file", "other": "小王",
                                              "copy": "報價單（小王的版本）.docx"}])
        self.assertEqual((self.B / "報價單.docx").read_text(encoding="utf-8").strip(), "乙")
        self.assertEqual((self.B / "報價單（小王的版本）.docx").read_text(encoding="utf-8").strip(), "甲")
        self.assertFalse(git.merge_in_progress(self.B))
        self.assertEqual(gf.must(self.B, "status", "--porcelain").strip(), "")
        gf.must(self.B, "push")

    def test_card_conflict_keeps_theirs_and_pending(self):
        todo = cards.todo(self.A, sources_lib.load(self.A))["new"]
        item = next(i for i in todo if i["id"] == _cards.entry_of(self.A, _cards.MEETING)["id"])
        _cards.write_card(self.A, item, "大安陳會議一")
        self.commit_push(self.A, "card", "甲")
        gf.must(self.B, "pull", "--no-rebase")
        rel = next(p.relative_to(self.A).as_posix() for p in (self.A / "檔案索引").rglob("大安陳會議一-*.md"))
        card_base.record(self.A, rel)
        self.commit_push(self.A, "base", "甲")
        gf.must(self.B, "pull", "--no-rebase")
        text = (self.A / rel).read_text(encoding="utf-8")
        (self.A / rel).write_text(text.replace("第一次會議的紀錄", "第一次會議的紀錄（甲改）"), encoding="utf-8", newline="\n")
        self.commit_push(self.A, "a", "小王")
        (self.B / rel).write_text(text.replace("第一次會議的紀錄", "第一次會議的紀錄（乙改）"), encoding="utf-8", newline="\n")
        gf.must(self.B, "add", "-A")
        gf.must(self.B, "commit", "-m", "b", who="我")
        gf.git(self.B, "pull", "--no-rebase", "--no-edit")
        self.assertTrue(git.merge_in_progress(self.B))
        got = refresh.run(self.B, tid(self.B))
        self.assertEqual([(c["path"], c["kind"], c["other"]) for c in got["conflicts"]], [(rel, "card", "小王")])
        body = (self.B / rel).read_text(encoding="utf-8")
        self.assertIn("甲改", body)
        self.assertNotIn("乙改", body)
        pend = card_base.load(self.B)[rel].get("pending")
        self.assertIn("乙改", pend["after"])
        self.assertFalse(git.merge_in_progress(self.B))
        self.assertEqual(gf.must(self.B, "status", "--porcelain").strip(), "")
        gf.must(self.B, "push")

    def test_rebase_in_progress_untouched(self):
        (Path(self.B) / ".git" / "rebase-merge").mkdir()
        before = gf.must(self.B, "status", "--porcelain")
        got = refresh.run(self.B, "t")
        self.assertTrue(got["rebase"])
        self.assertEqual(got["conflicts"], [])
        self.assertEqual(gf.must(self.B, "status", "--porcelain"), before)

    def test_big_file_excluded(self):
        gf.write(self.B, "客戶案件/影片.mp4", "z" * 20000)
        from kb._lib import config
        real = config.get
        with mock.patch.object(config, "get", lambda v, k: 0.01 if k == "git_file_max_mb" else real(v, k)):
            got = refresh.run(self.B, tid(self.B))
        self.assertEqual([b["path"] for b in got["big"]], ["客戶案件/影片.mp4"])
        self.assertIn("/客戶案件/影片.mp4", (self.B / ".git" / "info" / "exclude").read_text(encoding="utf-8"))
        self.assertNotIn("影片", gf.must(self.B, "status", "--porcelain"))
        # 搬走後 exclude 拿掉（source-edit 叫的）
        self.assertTrue(git.exclude_remove(self.B, "客戶案件/影片.mp4"))

    def test_cli_json_and_in_git_only(self):
        r = subprocess.run([sys.executable, str(KB), "refresh", "--json"], capture_output=True, text=True, encoding="utf-8",
                           cwd=str(self.B), env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT), PYTHONIOENCODING="utf-8"))
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout)
        self.assertTrue(got["ok"])
        self.assertFalse(got["rebase"])


class PulledEditsTest(RefreshBase):
    """問 1 (a)：pull 進來的卡不被這台當成手改；自己改的照記。"""

    def test_pulled_card_not_counted_as_hand_edit(self):
        todo = cards.todo(self.A, sources_lib.load(self.A))["new"]
        item = next(i for i in todo if i["id"] == _cards.entry_of(self.A, _cards.MEETING)["id"])
        p = _cards.write_card(self.A, item, "大安陳會議一")
        rel = p.relative_to(self.A).as_posix()
        card_base.record(self.A, rel)
        self.commit_push(self.A, "card", "甲")
        gf.must(self.B, "pull", "--no-rebase")
        card_base.record(self.B, rel)
        refresh.run(self.B, tid(self.B))  # 記下目前的 HEAD
        p.write_text(p.read_text(encoding="utf-8").replace("第一次會議的紀錄", "第一次會議（小王改）"), encoding="utf-8", newline="\n")
        self.commit_push(self.A, "wang", "小王")
        gf.must(self.B, "pull", "--no-rebase")
        self.assertEqual(len(card_base.edits(self.B, persist=False)["edits"]), 1)  # 還沒 refresh：對不上基準
        got = refresh.run(self.B, tid(self.B))
        self.assertIn(rel, got["pulled"])
        self.assertEqual(card_base.edits(self.B)["edits"], [])
        # 這台的人接著自己改 → 照記
        q = self.B / rel
        q.write_text(q.read_text(encoding="utf-8") + "\n我補一句\n", encoding="utf-8", newline="\n")
        self.assertEqual(len(card_base.edits(self.B)["edits"]), 1)


class AfterTest(RefreshBase):
    """退回時別人改過的檔（驗收 7）：after.jsonl 與 other_changed。"""

    def test_output_changed_later_gets_copy_and_who_is_coworker(self):
        t = tid(self.A)
        rel = "暫存區/產出.txt"
        gf.write(self.A, rel, "舊\n")
        turn.backup(self.A, rel, t)  # 回合備份：舊版
        (self.A / rel).write_text("AI 寫的\n", encoding="utf-8")
        self.assertEqual(refresh.write_after(self.A, t), 1)
        self.assertFalse(refresh.changed_after(self.A, t, rel))
        self.assertIsNone(refresh.other_changed(self.A, t, rel))
        (self.A / rel).write_text("同事改的\n", encoding="utf-8")  # 雲端同步進來
        backup = self.A / ".system" / "versions" / t / "files" / rel
        got = refresh.other_changed(self.A, t, rel, backup)
        self.assertEqual((got["side"], got["who"], got["via"], got["done"]), ("other", "同事", "cloud", None))
        self.assertEqual(got["copy"], "暫存區/產出（退回前的版本）.txt")
        self.assertEqual((self.A / got["copy"]).read_text(encoding="utf-8"), "舊\n")
        self.assertEqual((self.A / rel).read_text(encoding="utf-8"), "同事改的\n")  # 原位不動

    def test_card_pulled_later_marked_redo_with_git_author(self):
        todo = cards.todo(self.A, sources_lib.load(self.A))["new"]
        item = next(i for i in todo if i["id"] == _cards.entry_of(self.A, _cards.MEETING)["id"])
        t = tid(self.A)
        p = _cards.write_card(self.A, item, "大安陳會議一")
        rel = p.relative_to(self.A).as_posix()
        turn.backup(self.A, rel, t)
        self.assertEqual(refresh.write_after(self.A, t), 1)
        self.commit_push(self.A, "card", "甲")
        (self.A / rel).write_text(p.read_text(encoding="utf-8").replace("第一次會議的紀錄", "第一次會議（小王改）"),
                                  encoding="utf-8", newline="\n")
        self.commit_push(self.A, "wang", "小王")
        got = refresh.other_changed(self.A, t, rel)
        self.assertEqual((got["who"], got["via"], got["done"], got["copy"]), ("小王", "pull", "redo", None))


class TurnHookTest(RefreshBase):
    """驗收 3、6：每句開頭 HEAD 變了才叫一次；開場不叫；rebase 到一半每句有那句。"""

    def prompt(self, vault, text="好", sid="s1"):
        payload = {"session_id": sid, "cwd": str(vault), "prompt": text, "hook_event_name": "UserPromptSubmit"}
        r = subprocess.run([sys.executable, str(ROOT / "hooks" / "turn.py")], input=json.dumps(payload), capture_output=True,
                           text=True, encoding="utf-8", cwd=str(ROOT), env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)))
        self.assertEqual(r.returncode, 0, r.stderr)
        if not r.stdout.strip():
            return ""
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_called_only_when_head_changed(self):
        self.prompt(self.B)  # 第一次：記下 HEAD
        self.assertEqual(refresh.read_last_head(self.B), git.head(self.B))
        gf.write(self.A, "行事曆說明.txt", "新的\n")
        self.commit_push(self.A, "a", "小王")
        self.assertNotIn("同事", self.prompt(self.B, sid="s2"))  # 還沒 pull：HEAD 沒變
        gf.must(self.B, "pull", "--no-rebase")
        out = self.prompt(self.B, sid="s3")
        self.assertIn("可能是同事動的", out)
        self.assertNotIn("你跟", out)
        self.assertNotIn("可能是同事動的", self.prompt(self.B, sid="s3"))  # 同一個 HEAD 不再叫

    def test_rebase_line_every_turn_but_once_per_conversation(self):
        self.prompt(self.B)
        (Path(self.B) / ".git" / "rebase-merge").mkdir()
        first = self.prompt(self.B, sid="s5")
        self.assertIn("rebase 到一半", first)
        self.assertNotIn("rebase 到一半", self.prompt(self.B, sid="s5"))

    def test_session_hook_does_not_call_refresh(self):
        self.assertNotIn("refresh", (ROOT / "hooks" / "session.py").read_text(encoding="utf-8"))


class StopHookTest(RefreshBase):
    def test_stop_hook_has_record_after(self):
        text = (ROOT / "hooks" / "stop.py").read_text(encoding="utf-8")
        self.assertIn("refresh.write_after", text)


if __name__ == "__main__":
    unittest.main()
