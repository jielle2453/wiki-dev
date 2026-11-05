"""_lib/git.py（多人共用 3 驗收 1）：用本機裸 repo，不連網。"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import _gitfix as gf
from kb._lib import git  # noqa: E402


@unittest.skipUnless(gf.have_git(), "沒有 git")
class GitTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.bare, self.a, self.b = gf.make_team(self._tmp.name)
        for r in (self.a, self.b):
            os.environ.update(gf.ENV)

    def test_not_repo(self):
        d = Path(self._tmp.name) / "plain"
        d.mkdir()
        self.assertFalse(git.is_repo(d))
        self.assertIsNone(git.head(d))
        self.assertEqual(git.unmerged(d), [])
        self.assertFalse(git.merge_in_progress(d))
        self.assertFalse(git.rebase_in_progress(d))
        self.assertEqual(git.push_tag(d, "willy/claim/x", "甲"), "error")
        self.assertIsNone(git.list_remote_tags(d, "willy/"))
        self.assertIsNone(git.repo_size(d))
        self.assertFalse(git.exclude_remove(d, "x"))

    def test_no_git_binary(self):
        with mock.patch("shutil.which", return_value=None):
            self.assertFalse(git.is_repo(self.a))
            self.assertIsNone(git.head(self.a))
            self.assertEqual(git.run(self.a, "status")[0], 127)

    def test_head_changed_since(self):
        old = git.head(self.a)
        gf.write(self.a, "x/新.md", "n\n")
        gf.must(self.a, "add", "-A")
        gf.must(self.a, "commit", "-m", "n")
        new = git.head(self.a)
        self.assertNotEqual(old, new)
        self.assertEqual(git.changed_since(self.a, old, new), ["x/新.md"])
        self.assertIsNone(git.changed_since(self.a, None, new))

    def test_push_tag_taken_by_second_clone(self):
        self.assertEqual(git.push_tag(self.a, "willy/claim/f-1-aaa-20261101", "甲"), "ok")
        self.assertEqual(git.push_tag(self.b, "willy/claim/f-1-aaa-20261101", "乙"), "taken")
        self.assertEqual(git.tags_local(self.b, "willy/claim/f-1-aaa-20261101"), [])  # 失敗就刪本機那個
        self.assertEqual(git.list_remote_tags(self.b, "willy/claim/f-1-"), ["willy/claim/f-1-aaa-20261101"])
        self.assertEqual(git.tag_message(self.b, "willy/claim/f-1-aaa-20261101"), "甲")
        self.assertTrue(git.delete_remote_tag(self.a, "willy/claim/f-1-aaa-20261101"))
        self.assertEqual(git.list_remote_tags(self.b, "willy/claim/"), [])
        self.assertEqual(git.push_tag(self.b, "willy/claim/f-1-aaa-20261101", "乙"), "ok")

    def test_push_tag_offline(self):
        gf.must(self.a, "remote", "set-url", "origin", str(Path(self._tmp.name) / "不存在.git"))
        self.assertEqual(git.push_tag(self.a, "willy/lint/2026-W45", "甲"), "offline")
        self.assertIsNone(git.list_remote_tags(self.a, "willy/"))

    def test_index_lock_retry(self):
        lock = Path(self.a) / ".git" / "index.lock"
        lock.write_text("", encoding="utf-8")
        slept = []

        def fake_sleep(sec):
            slept.append(sec)
            if len(slept) == 2:
                lock.unlink()
        gf.write(self.a, "n.md", "1\n")
        with mock.patch.object(git, "_SLEEP", fake_sleep):
            self.assertTrue(git.add(self.a, ["n.md"]))
        self.assertEqual(slept, [2.0, 2.0])

    def test_index_lock_gives_up_after_five(self):
        lock = Path(self.a) / ".git" / "index.lock"
        lock.write_text("", encoding="utf-8")
        slept = []
        with mock.patch.object(git, "_SLEEP", slept.append):
            self.assertFalse(git.add(self.a, ["README.md"]))
        self.assertEqual(len(slept), 5)

    def test_exclude(self):
        self.assertTrue(git.exclude_add(self.a, "大.mp4"))
        gf.write(self.a, "大.mp4", "z")
        self.assertEqual(git.status_untracked_and_modified(self.a), [])
        self.assertTrue(git.exclude_remove(self.a, "大.mp4"))
        self.assertEqual(git.status_untracked_and_modified(self.a), [("??", "大.mp4")])
        self.assertFalse(git.tracked(self.a, "大.mp4"))
        self.assertTrue(git.tracked(self.a, "README.md"))
        self.assertTrue(git.repo_size(self.a))
        self.assertEqual(git.largest_tracked(self.a)[0][0], "README.md")

    def test_conflict_helpers(self):
        for r, t in ((self.a, "甲的\n"), (self.b, "乙的\n")):
            gf.write(r, "卡.md", t)
            gf.must(r, "add", "-A")
        gf.must(self.a, "commit", "-m", "a", who="甲")
        gf.must(self.a, "push")
        gf.must(self.b, "commit", "-m", "b", who="乙")
        gf.git(self.b, "pull", "--no-rebase", "--no-edit")
        self.assertTrue(git.merge_in_progress(self.b))
        self.assertEqual(git.unmerged(self.b), ["卡.md"])
        self.assertEqual(git.show_stage(self.b, "卡.md", 2).strip(), "乙的")
        self.assertEqual(git.show_stage(self.b, "卡.md", 3).strip(), "甲的")
        self.assertEqual(git.author_of(self.b, "MERGE_HEAD", "卡.md"), "甲")
        self.assertTrue(git.checkout_theirs(self.b, "卡.md"))
        self.assertTrue(git.add(self.b, ["卡.md"]))
        self.assertTrue(git.commit_merge(self.b))
        self.assertFalse(git.merge_in_progress(self.b))
        self.assertEqual(git.unmerged(self.b), [])
        self.assertEqual((self.b / "卡.md").read_text(encoding="utf-8").strip(), "甲的")

    def test_head_and_dir_read_from_files_without_git(self):
        """#44：一般 clone 每句開頭讀 .git 裡的檔，不叫子行程；packed-refs、detached、rebase 一樣對。"""
        want = gf.must(self.a, "rev-parse", "HEAD").strip()
        no_git = mock.patch.object(git, "_once", side_effect=AssertionError("不該叫 git"))
        with no_git:
            self.assertTrue(git.is_repo(self.a))
            self.assertEqual(git.head(self.a), want)
            self.assertFalse(git.rebase_in_progress(self.a))
            self.assertFalse(git.merge_in_progress(self.a))
            (self.a / ".git" / "rebase-merge").mkdir()
            self.assertTrue(git.rebase_in_progress(self.a))
            (self.a / ".git" / "rebase-merge").rmdir()
        gf.must(self.a, "pack-refs", "--all")
        self.assertFalse((self.a / ".git" / "refs" / "heads" / "main").exists())
        with no_git:
            self.assertEqual(git.head(self.a), want)
        gf.must(self.a, "checkout", "-q", "--detach")
        with no_git:
            self.assertEqual(git.head(self.a), want)

    def test_dot_git_file_falls_back_to_git(self):
        """.git 是檔（git worktree）：讀不懂就照舊叫 git。"""
        wt = Path(self._tmp.name) / "wt"
        gf.must(self.a, "worktree", "add", "-q", "--detach", str(wt))
        self.assertTrue((wt / ".git").is_file())
        self.assertTrue(git.is_repo(wt))
        self.assertEqual(git.head(wt), gf.must(self.a, "rev-parse", "HEAD").strip())
        self.assertFalse(git.rebase_in_progress(wt))

    def test_unborn_and_broken_dot_git(self):
        """還沒有 commit 的分支 head 是 None；.git 只有 HEAD 的壞夾不當成 repo（交給 git 判斷）。"""
        fresh = Path(self._tmp.name) / "fresh"
        fresh.mkdir()
        gf.must(fresh, "init", "-q", "-b", "main")
        self.assertTrue(git.is_repo(fresh))
        self.assertIsNone(git.head(fresh))
        broken = Path(self._tmp.name) / "broken"
        (broken / ".git").mkdir(parents=True)
        (broken / ".git" / "HEAD").write_text("ref: refs/heads/main" + chr(10), encoding="utf-8")
        self.assertIsNone(git._plain_git_dir(broken))
        self.assertFalse(git.is_repo(broken))
        self.assertIsNone(git.head(broken))


if __name__ == "__main__":
    unittest.main()
