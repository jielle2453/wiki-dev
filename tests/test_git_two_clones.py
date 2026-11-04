"""認領整理（多人共用 3 驗收 4）：真 git，兩份 clone 同時 cards dispatch。多人判斷（第 2 份 people.multi）用假替身。"""
import unittest
from datetime import datetime, timedelta
from unittest import mock

from tests import _gitfix as gf
from tests.test_refresh import RefreshBase, tid
from kb._lib import batches, git  # noqa: E402


@unittest.skipUnless(gf.have_git(), "沒有 git")
class ClaimTest(RefreshBase):
    def setUp(self):
        super().setUp()
        self.sa, self.sb = "sess-a", "sess-b"
        gf.must(self.A, "pull", "--no-rebase")
        gf.must(self.B, "pull", "--no-rebase")

    def disp(self, vault, sid, name, multi=True):
        with mock.patch.object(git, "multi", lambda v: multi), mock.patch.object(git, "me", lambda v: name):
            return batches.dispatch(vault, sid, tid(vault))

    def test_only_one_side_gets_the_work(self):
        a = self.disp(self.A, self.sa, "甲")
        self.assertTrue(a["batches"])
        self.assertEqual(a["claimed_elsewhere"], [])
        b = self.disp(self.B, self.sb, "乙")
        mine_a = {c for x in batches.load(self.A)["batches"] for c in x["items"]}
        mine_b = {c for x in batches.load(self.B)["batches"] for c in x["items"]}
        self.assertFalse(mine_a & mine_b)  # 同一份只有一邊派到（A 一次派不完的剩下的，B 才拿得到）
        self.assertTrue(b["claimed_elsewhere"])
        self.assertEqual({c["id"] for c in b["claimed_elsewhere"]}, mine_a)
        self.assertEqual({c["by"] for c in b["claimed_elsewhere"]}, {"甲"})
        self.assertFalse(b["offline"])
        with mock.patch.object(git, "multi", lambda v: True):
            self.assertEqual(batches.elsewhere(self.B), {"count": len(b["claimed_elsewhere"]), "by": ["甲"]})

    def test_release_deletes_tag(self):
        a = self.disp(self.A, self.sa, "甲")
        fids = [c for b in batches.load(self.A)["batches"] for c in b["items"]]
        self.assertTrue(git.list_remote_tags(self.A, "willy/claim/"))
        with mock.patch.object(git, "multi", lambda v: True), mock.patch.object(git, "me", lambda v: "甲"):
            self.assertEqual(batches.release_claims(self.A, fids), len(fids))
        self.assertEqual(git.list_remote_tags(self.A, "willy/claim/"), [])
        _ = a

    def test_offline_dispatches_nothing(self):
        gf.must(self.A, "remote", "set-url", "origin", str(self.tmp / "不存在.git"))
        a = self.disp(self.A, self.sa, "甲")
        self.assertTrue(a["offline"])
        self.assertEqual(a["batches"], [])
        self.assertEqual([b for b in batches.load(self.A)["batches"]], [])

    def test_old_tag_can_be_reclaimed(self):
        self.disp(self.A, self.sa, "甲")
        names = git.list_remote_tags(self.A, "willy/claim/")
        old = (datetime.now() - timedelta(days=3)).strftime("%Y%m%d")
        for n in names:  # 把標籤改成 3 天前的（遠端換名字）
            gf.must(self.A, "push", "origin", f"{n}:refs/tags/{n.rsplit('-', 1)[0]}-{old}")
            git.delete_remote_tag(self.A, n)
        b = self.disp(self.B, self.sb, "乙")
        self.assertTrue(b["batches"])
        self.assertEqual(b["claimed_elsewhere"], [])

    def test_single_or_not_git_unchanged(self):
        a = self.disp(self.A, self.sa, "甲", multi=False)
        self.assertTrue(a["batches"])
        self.assertEqual(git.list_remote_tags(self.A, "willy/claim/"), [])
        self.assertEqual(a["claimed_elsewhere"], [])


@unittest.skipUnless(gf.have_git(), "沒有 git")
class LintSplitTest(RefreshBase):
    def lint_as(self, vault, name, multi=True):
        from kb.lint import runner, state
        with mock.patch.object(git, "multi", lambda v: multi), mock.patch.object(git, "me", lambda v: name), \
                mock.patch.dict("os.environ", {"WIKI_WITH_WILLY_NO_BACKGROUND": "1"}):
            runner.run(vault, background=True, today="2026-11-04")
        return state.load(vault)

    def test_one_runs_shared_other_only_local(self):
        a = self.lint_as(self.A, "甲")
        b = self.lint_as(self.B, "乙")
        self.assertEqual(a["last_shared"], "2026-11-04")
        self.assertIsNone(b["last_shared"])
        self.assertEqual(b["last_background"], "2026-11-04")  # 本機的照跑
        self.assertEqual(git.list_remote_tags(self.A, "willy/lint/"), ["willy/lint/2026-W45"])
        self.assertEqual(self.lint_as(self.A, "甲")["last_shared"], "2026-11-04")  # 自己的標籤不擋自己

    def test_single_runs_everything_and_pushes_no_tag(self):
        a = self.lint_as(self.A, "甲", multi=False)
        self.assertEqual(a["last_shared"], "2026-11-04")
        self.assertEqual(git.list_remote_tags(self.A, "willy/"), [])

    def test_old_claim_tags_cleaned(self):
        from kb.lint import runner
        old = "willy/claim/f-1-aaaaaaaaaaaa-20261020"
        new = "willy/claim/f-2-bbbbbbbbbbbb-20261103"
        with mock.patch.object(git, "multi", lambda v: True):
            for n in (old, new):
                self.assertEqual(git.push_tag(self.A, n, "甲"), "ok")
            self.assertEqual(runner.clean_old_claims(self.A, "2026-11-04"), 1)
        self.assertEqual(git.list_remote_tags(self.A, "willy/claim/"), [new])


@unittest.skipUnless(gf.have_git(), "沒有 git")
class SkeletonClaimTest(RefreshBase):
    def test_only_one_machine_rewrites_shared_file(self):
        from kb._lib import skeleton
        with mock.patch.object(git, "multi", lambda v: True):
            with mock.patch.object(git, "me", lambda v: "甲"):
                self.assertTrue(skeleton.claim_rewrite(self.A, "CLAUDE.md"))
                self.assertTrue(skeleton.claim_rewrite(self.A, "CLAUDE.md"))  # 自己的標籤不擋自己
            with mock.patch.object(git, "me", lambda v: "乙"):
                self.assertFalse(skeleton.claim_rewrite(self.B, "CLAUDE.md"))
                self.assertTrue(skeleton.claim_rewrite(self.B, "別的檔.md"))
        self.assertTrue(skeleton.claim_rewrite(self.B, "CLAUDE.md"))  # 單人照改


if __name__ == "__main__":
    unittest.main()
