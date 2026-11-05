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

IGNORE = (ROOT / "skeleton" / ".gitignore").read_text(encoding="utf-8")  # 第 1 份出貨的 .gitignore


def tid(v):
    return turn.start(v, None, "")["turn"]


@unittest.skipUnless(gf.have_git(), "沒有 git")
class RefreshBase(unittest.TestCase):
    def setUp(self):
        self.tmp, self.A, self.raw = _cards.make_card_vault()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bare = self.tmp / "origin.git"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(self.bare)], check=True, capture_output=True, env=gf.ENV)
        from kb._lib import migrate
        migrate.migrate_streams(self.A)  # 第 1 份：舊的整份 JSON → 這台的流水檔，才有東西進 git
        from kb._lib import profile
        with profile.lock(self.A):  # 設定檔升到這版（真的庫升級時就轉了），B 重畫才不會順手升級、多寫一行
            profile.write_locked(self.A, profile.load(self.A), tid(self.A))
        gf.write(self.A, ".gitignore", IGNORE)
        gf.must(self.A, "init", "-b", "main")
        gf.must(self.A, "add", "-A")
        gf.must(self.A, "commit", "-m", "init", who="甲")
        gf.must(self.A, "remote", "add", "origin", str(self.bare))
        gf.must(self.A, "push", "-u", "origin", "main")
        self.B = self.tmp / "B"
        subprocess.run(["git", "clone", str(self.bare), str(self.B)], check=True, capture_output=True, env=gf.ENV)
        gf.must(self.B, "config", "merge.conflictstyle", "merge")
        from kb._lib import streams
        for k in streams.KINDS:  # 新 clone：衍生的整份 JSON 副本（.gitignore 擋掉的）從流水檔重畫，find_vault 才認得
            streams.load(self.B, k)
        self.B_env = mock.patch.dict(os.environ, gf.ENV)
        self.B_env.start()
        self.addCleanup(self.B_env.stop)

    def commit_push(self, repo, msg, who):
        gf.must(repo, "add", "-A")
        gf.must(repo, "commit", "-m", msg, who=who)
        gf.must(repo, "push")


class RefreshTest(RefreshBase):
    def test_fresh_clone_found_and_guarded(self):
        """#39：新 clone 沒有 .gitignore 擋掉的衍生副本，find_vault 照樣認、從流水檔補出副本，守門照常擋。"""
        from kb import guard
        from tests._guard_fixture import payload
        C = self.tmp / "C"
        subprocess.run(["git", "clone", str(self.bare), str(C)], check=True, capture_output=True, env=gf.ENV)
        self.assertFalse((C / sources_lib.SOURCES_REL).exists())
        found = guard.find_vault(str(C / ".system" / "streams"))
        self.assertIsNotNone(found)
        self.assertTrue(os.path.samefile(found, C))
        self.assertEqual([s["alias"] for s in sources_lib.load_raw(C)["sources"]],
                         [s["alias"] for s in sources_lib.load_raw(self.A)["sources"]])
        got = guard.decide(payload("Write", C / sources_lib.SOURCES_REL, C))
        self.assertEqual(got.decision, "deny", got)
        (C / sources_lib.SOURCES_REL).unlink()  # 快取還在、只刪副本：也補回來
        self.assertTrue(os.path.samefile(guard.find_vault(str(C)), C))
        self.assertTrue((C / sources_lib.SOURCES_REL).is_file())
        empty = self.tmp / "空" / ".system" / "streams" / "sources"  # 空的流水檔夾不算知識庫
        empty.mkdir(parents=True)
        self.assertIsNone(guard.find_vault(str(empty)))

    def test_profile_md_untracked_and_rerendered(self):
        """#42（jacky 2026-11-05 定）：設定檔 md 不進 git。舊庫追蹤著它，A 升級換 .gitignore 時不再追蹤；
        B pull 後檔被刪，refresh 重畫回來；兩台的 git 都不再有它。"""
        from kb._lib import profile, skeleton
        md = profile.MD_POSIX
        self.assertTrue((self.A / md).is_file())
        gf.write(self.A, ".gitignore", IGNORE.replace("系統/*" + chr(10), "系統/*" + chr(10) + "!系統/客戶設定檔.md" + chr(10)))  # 舊版放行
        self.commit_push(self.A, "old", "甲")
        gf.must(self.B, "pull", "--no-rebase")
        self.assertIn(md, gf.must(self.B, "-c", "core.quotepath=false", "ls-files", md))
        gf.write(self.A, ".gitignore", IGNORE)
        skeleton._untrack_rendered(self.A)
        self.commit_push(self.A, "untrack", "甲")
        self.assertTrue((self.A / md).is_file())  # 這台的檔留著
        gf.must(self.B, "pull", "--no-rebase")
        self.assertFalse((self.B / md).exists())  # pull 把別台不再追蹤的刪掉
        refresh.run(self.B, tid(self.B))
        self.assertTrue((self.B / md).is_file())
        for v in (self.A, self.B):
            self.assertEqual(gf.must(v, "ls-files", md).strip(), "")
            self.assertNotIn("客戶設定檔", gf.must(v, "-c", "core.quotepath=false", "status", "--porcelain"))
        # review：A 改設定 → 流水檔同步到 B，B 的 md 還在但是舊的；指紋各台自己記，B 不當成手改、refresh 畫成新的
        r = subprocess.run([sys.executable, str(KB), "profile", "set", "people", "4"], capture_output=True, text=True,
                           encoding="utf-8", cwd=str(self.A), env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT), PYTHONIOENCODING="utf-8"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.commit_push(self.A, "people", "甲")
        old_b = (self.B / md).read_text(encoding="utf-8")
        gf.must(self.B, "pull", "--no-rebase")
        self.assertEqual((self.B / md).read_text(encoding="utf-8"), old_b)  # md 不進 git，pull 不動它
        self.assertEqual(profile.status(self.B)["state"], "ok")  # 不當成她手改
        refresh.run(self.B, tid(self.B))
        self.assertEqual((self.B / md).read_text(encoding="utf-8"), (self.A / md).read_text(encoding="utf-8"))

    def test_profile_md_modify_delete_conflict(self):
        """#42 review：還沒升級的那台改了設定檔 md、這邊已不再追蹤 → 收拾成不追蹤、留這台的檔、合併做完。"""
        from kb._lib import profile, skeleton
        md = profile.MD_POSIX
        gf.write(self.A, ".gitignore", IGNORE.replace("系統/*" + chr(10), "系統/*" + chr(10) + "!系統/客戶設定檔.md" + chr(10)))
        self.commit_push(self.A, "old", "甲")
        gf.must(self.B, "pull", "--no-rebase")
        gf.write(self.A, ".gitignore", IGNORE)
        skeleton._untrack_rendered(self.A)
        self.commit_push(self.A, "untrack", "甲")
        (self.B / md).write_text((self.B / md).read_text(encoding="utf-8") + chr(10) + "乙加的" + chr(10), encoding="utf-8")
        gf.must(self.B, "add", "-A")
        gf.must(self.B, "commit", "-m", "b", who="乙")
        gf.git(self.B, "pull", "--no-rebase", "--no-edit")
        self.assertTrue(git.merge_in_progress(self.B))
        got = refresh.run(self.B, tid(self.B))
        self.assertEqual(got["conflicts"], [])
        self.assertFalse(git.merge_in_progress(self.B))
        self.assertTrue((self.B / md).is_file())
        self.assertEqual(gf.must(self.B, "ls-files", md).strip(), "")

    def test_profile_md_conflict_other_direction(self):
        """#42 review：這邊已不再追蹤、還沒升級的那台改了 md 先推 → 這邊收拾後 md 是這台畫的（不是對方的）、不追蹤、不當手改。"""
        from kb._lib import profile, skeleton
        md = profile.MD_POSIX
        gf.write(self.A, ".gitignore", IGNORE.replace("系統/*" + chr(10), "系統/*" + chr(10) + "!系統/客戶設定檔.md" + chr(10)))
        self.commit_push(self.A, "old", "甲")
        gf.must(self.B, "pull", "--no-rebase")
        (self.B / md).write_text((self.B / md).read_text(encoding="utf-8") + chr(10) + "乙加的" + chr(10), encoding="utf-8")
        self.commit_push(self.B, "b", "乙")
        gf.write(self.A, ".gitignore", IGNORE)
        skeleton._untrack_rendered(self.A)
        gf.must(self.A, "add", "-A")
        gf.must(self.A, "commit", "-m", "untrack", who="甲")
        gf.git(self.A, "pull", "--no-rebase", "--no-edit")
        refresh.run(self.A, tid(self.A))
        self.assertFalse(git.merge_in_progress(self.A))
        self.assertNotIn("乙加的", (self.A / md).read_text(encoding="utf-8"))
        self.assertEqual(gf.must(self.A, "ls-files", md).strip(), "")
        self.assertEqual(profile.status(self.A)["state"], "ok")

    def test_profile_md_user_allowed_stays_tracked(self):
        """#42 review：她自己在 .gitignore 放行設定檔 md（行尾空白、開頭斜線也算）→ 不取消追蹤。"""
        from kb._lib import profile, skeleton
        md = profile.MD_POSIX
        gf.write(self.A, ".gitignore", IGNORE + "!/系統/客戶設定檔.md  " + chr(10))
        self.commit_push(self.A, "allow", "甲")
        self.assertEqual(gf.must(self.A, "-c", "core.quotepath=false", "ls-files", md).strip(), md)
        skeleton._untrack_rendered(self.A)
        self.assertEqual(gf.must(self.A, "-c", "core.quotepath=false", "ls-files", md).strip(), md)

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
        self.assertEqual([e["path"] for e in card_base.edits(self.B, persist=False)["edits"]], [rel])
        gf.must(self.A, "pull", "--no-rebase")  # #45：pending 跟著共用流水檔到 A，A 不當成自己的手改
        self.assertIsNotNone(card_base.load(self.A)[rel].get("pending"))
        self.assertEqual(card_base.edits(self.A, persist=False)["edits"], [])

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
        outside = [s["alias"] for s in sources_lib.load(self.B).entries if s["alias"] not in ("暫存區", "知識庫")]
        self.assertTrue(outside)
        self.assertEqual(got["big"][0]["cloud"], outside[0])  # #45：知識庫外登記的來源（以前讀錯鍵，永遠 None）
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


class CarriedHandedTest(RefreshBase):
    """驗收 10：程式頁上沒照格式的字，下一句交給 AI 一次。"""
    prompt = TurnHookTest.prompt

    def test_carried_handed_once_then_dropped(self):
        from kb._lib import renders
        self.prompt(self.A, sid="c0")
        added, _d = renders.add_carried(self.A, "系統/日程.md", [{"kind": "added", "text": "下週三跟廠商確認規格"}])
        cid = added[0]["id"]
        out = self.prompt(self.A, sid="c1")
        self.assertIn("下週三跟廠商確認規格", out)
        self.assertIn(cid, out)
        self.assertNotIn(cid, self.prompt(self.A, sid="c1"))
        self.assertNotIn(cid, self.prompt(self.A, sid="c2"))
        self.assertTrue(renders.carried(self.A, "系統/日程.md"))  # 還沒處理完的「你加的」那段照留
        self.assertEqual(renders.drop_carried(self.A, cid)[0], "系統/日程.md")
        self.assertEqual(renders.carried(self.A, "系統/日程.md"), [])

    def test_home_no_longer_asks_to_add_agenda(self):
        from kb._lib import plan
        self.assertFalse(hasattr(plan, "carried_asks"))


class StopHookTest(RefreshBase):
    def test_stop_hook_has_record_after(self):
        text = (ROOT / "hooks" / "stop.py").read_text(encoding="utf-8")
        self.assertIn("refresh.write_after", text)


class QuietTurn(RefreshBase):
    """#44：HEAD 沒變的那句，每句開頭的 git 對帳一個子行程都不叫（多人原本每句先付 0.4 秒）。"""

    def test_unchanged_head_calls_no_git(self):
        sys.path.insert(0, str(ROOT / "hooks"))
        import _checks
        refresh.run(self.B, tid(self.B))
        with mock.patch.object(git, "_once", side_effect=AssertionError("不該叫 git")):
            self.assertEqual(_checks.refresh_lines(self.B), [])


class SmallLines(unittest.TestCase):
    """#45（問題 06）：同步進來的流水檔不列給 AI；設定檔 conflicts 不列機器算的 md_sha256。"""

    def test_pulled_line_skips_streams(self):
        sys.path.insert(0, str(ROOT / "hooks"))
        import _checks
        got = {"pulled": [".system/streams/profile/m-1.jsonl", ".gitignore", "報價單.docx"], "conflicts": [], "big": []}
        with mock.patch.object(git, "is_repo", lambda v: True), mock.patch.object(git, "rebase_in_progress", lambda v: False), \
                mock.patch.object(refresh, "head_changed", lambda v: True), mock.patch.object(refresh, "run", lambda v: got):
            lines = [x for x, _once in _checks.refresh_lines("V")]
        self.assertEqual(len(lines), 1)
        self.assertIn("1 個檔（報價單.docx）", lines[0])
        got["pulled"] = [".system/streams/profile/m-1.jsonl", ".gitignore", "系統/客戶設定檔.md"]  # 程式動的也不列（#42 回測）
        with mock.patch.object(git, "is_repo", lambda v: True), mock.patch.object(git, "rebase_in_progress", lambda v: False), \
                mock.patch.object(refresh, "head_changed", lambda v: True), mock.patch.object(refresh, "run", lambda v: got):
            self.assertEqual(_checks.refresh_lines("V"), [])

    def test_unknown_machine_pending_still_shown(self):
        """#45 review：pending 記的那台找不到流水檔（代號換了）→ 照報，免得永遠沒人處理；沒記 machine 的舊資料照報。"""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(card_base._others_pending(d, {"machine": "m-00000000"}, "m-11111111"))
            self.assertFalse(card_base._others_pending(d, {}, "m-11111111"))
            sd = Path(d) / ".system" / "streams" / "card_base"
            sd.mkdir(parents=True)
            (sd / "m-00000000.jsonl").write_text("", encoding="utf-8")
            self.assertTrue(card_base._others_pending(d, {"machine": "m-00000000"}, "m-11111111"))
            self.assertFalse(card_base._others_pending(d, {"machine": "m-11111111"}, "m-11111111"))

    def test_profile_conflicts_skip_md_sha(self):
        import io
        from contextlib import redirect_stdout
        from kb import profile_cli
        from kb._lib import profile, streams
        rows = [{"id": "p", "field": "md_sha256", "values": []}, {"id": "p", "field": "types", "values": []}]
        buf = io.StringIO()
        with mock.patch.object(profile, "status", lambda v: {"state": "ok", "data": {}}), \
                mock.patch.object(profile_cli, "_limits", lambda v: {}), \
                mock.patch.object(profile, "sections_schema", lambda *a, **k: []), \
                mock.patch.object(profile, "card_titles", lambda v, d: {}), mock.patch.object(profile, "use_choices", lambda v: []), \
                mock.patch.object(profile_cli, "_pending_edit", lambda st: None), \
                mock.patch.object(streams, "conflicts_of", lambda v, k: rows), redirect_stdout(buf):
            profile_cli._show("V", True)
        self.assertEqual([c["field"] for c in json.loads(buf.getvalue())["conflicts"]], ["types"])


if __name__ == "__main__":
    unittest.main()
