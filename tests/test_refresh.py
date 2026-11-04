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


if __name__ == "__main__":
    unittest.main()
