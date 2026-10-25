"""lint 第二輪測試報告的修正（design/reports/lint-測試-2.md）：T-26～T-31。T-25 與 T-31 的端到端在 test_lib_purge 的 LintPending。"""
import datetime as dt
import json
import re
import shutil
import types
import unittest
from unittest import mock

from tests import _entities as E
from tests import _lint as L
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import pending, profile, purge, renders, skeleton, turn  # noqa: E402
from kb.lint import checks, runner  # noqa: E402
from kb.lint.checks import citations, stale_by_profile  # noqa: E402

def today():
    """執行時才取今天（發行前 T-40：載入時固定的話跨午夜會偶發失敗）。"""
    return dt.date.today()


def fake(name, found=None):
    mod = types.SimpleNamespace(NAME=name, run=lambda ctx: [dict(f) for f in found or []])
    mod.__name__ = f"kb.lint.checks.{name}"
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()
        self.t = turn.start(self.V, None, "")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_with(self, mods, **kw):
        with mock.patch.object(checks, "CHECKS", mods):
            return runner.run(self.V, **kw)

    def items(self, key):
        return [i for i in pending.load(self.V)["items"] if i.get("key") == key]


class T26ForgetAnsweredWhenGone(Base):
    def test_dismissed_then_gone_then_back_reopens(self):
        stale = [fake("guard", [runner.finding("guard", "decide", "guard_stale", "守門好像沒在跑")])]
        self.run_with(stale)
        pending.dismiss(self.V, self.items("guard_stale")[0]["id"], self.t)
        self.run_with(stale)
        self.assertEqual([i["status"] for i in self.items("guard_stale")], ["dismissed"], "條件沒變不重開")
        self.run_with([fake("guard", [])])
        self.assertTrue(self.items("guard_stale")[0].get("cleared"))
        self.run_with(stale)
        self.assertEqual(sorted(i["status"] for i in self.items("guard_stale")), ["dismissed", "open"], "復發就重開")

    def test_redo_items_cover_every_card(self):
        a = L.write_card(self.V, E.QUOTE, "信義王報價")
        b = L.write_card(self.V, E.ESTIMATE, "內湖李估價")
        for cid in (a, b):
            from kb._lib import cards
            p = self.V / cards.card_of(self.V, cid)["path"]
            p.write_text(re.sub(r"^製卡日期: .*$", "製卡日期: 2026-10-01", p.read_text(encoding="utf-8"), count=1, flags=re.M),
                         encoding="utf-8")
        prof = json.loads((self.V / profile.PROFILE_POSIX).read_text(encoding="utf-8"))
        for row in prof["card_types"]:
            if row["name"] == "報價":
                row["date"] = "2026-10-20"
        (self.V / profile.PROFILE_POSIX).write_text(json.dumps(prof, ensure_ascii=False), encoding="utf-8")
        with mock.patch.object(stale_by_profile, "REDO_SHOWN", 1):
            (dec,) = [f for f in stale_by_profile.run(L.ctx(self.V)) if f["kind"] == "decide"]
        self.assertEqual(len(dec["data"]["ids"]), 1)
        self.assertEqual(sorted(dec["items"]), sorted([a, b]), "指紋照全部的卡算")


class T27PendingSetAside(Base):
    def urgent_item(self):
        pid, _c = pending.add_lint(self.V, "inferred:agenda", "推測的日程放太久",
                                   {"dates": [(today() + dt.timedelta(days=1)).isoformat()]}, self.t)
        return pid

    def test_pending_set_aside_refuses_urgent(self):
        pid = self.urgent_item()
        r = run_kb("pending", "set-aside", pid, cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.splitlines()[0]), (3, "這件快到期了，沒辦法先放著：推測的日程放太久"))
        self.assertIsNone(self.items("inferred:agenda")[0]["set_aside"])
        got = json.loads(run_kb("pending", "set-aside", pid, "--json", cwd=self.V).stdout)
        self.assertEqual(got["refused"], "這件快到期了，沒辦法先放著：推測的日程放太久")

    def test_asks_p_path_does_not_need_todo(self):
        pid = pending.add(self.V, "unreadable", ["f-11111111"], "「甲.pdf」讀不到", "檔案壞了", self.t)
        (self.V / ".system" / "inventory.json").write_text("{壞", encoding="utf-8")
        r = run_kb("asks", "set-aside", pid, cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(pending.load(self.V)["items"][0]["set_aside"]["by"], "customer")


class T28UnreadableSourceIsFailed(Base):
    def lint(self):
        return runner.run(self.V)

    def put(self, key, check):
        pid, _c = pending.add_lint(self.V, key, "要你決定", {}, self.t, check=check)
        return pid

    def status(self, pid):
        return next(i for i in pending.load(self.V)["items"] if i["id"] == pid)["status"]

    def test_agenda_broken(self):
        pid = self.put("inferred:agenda", "inferred")
        (self.V / ".system" / "agenda.json").write_text("{壞", encoding="utf-8")
        got = self.lint()
        self.assertIn("推測放太久", got["failed_checks"])
        self.assertEqual(self.status(pid), "open")

    def test_skeleton_record_broken(self):
        """第三輪 T-35：沒有 skeleton.json 是舊庫、照常查；壞掉才算沒查成。"""
        pid = self.put("skeleton:CLAUDE.md:abc", "versions")
        (self.V / skeleton.SKELETON_JSON).write_text("{壞", encoding="utf-8")
        got = self.lint()
        self.assertIn("版本與骨架", got["failed_checks"])
        self.assertEqual(self.status(pid), "open")

    def test_journal_missing(self):
        pid = self.put("guard_stale", "guard")
        shutil.rmtree(self.V / ".system" / "journal", ignore_errors=True)
        with mock.patch("kb.lint.runner._journal"):
            got = self.lint()
        self.assertIn("守門", got["failed_checks"])
        self.assertEqual(self.status(pid), "open")

    def test_profile_broken(self):
        pid = self.put("redo_by_profile:報價:2026-10-20", "stale_by_profile")
        (self.V / profile.PROFILE_POSIX).write_text("{壞", encoding="utf-8")
        got = self.lint()
        self.assertIn("設定檔改了之後的卡", got["failed_checks"])
        self.assertEqual(self.status(pid), "open")


class T29BaseIsWhatWasWritten(Base):
    def add(self, name):
        return pending.add(self.V, "unreadable", [f"f-{abs(hash(name)) % 10**8:08d}"], f"「{name}」讀不到", "檔案壞了", self.t)

    def test_item_added_while_keep_failed_is_not_removed(self):
        a = self.add("甲.pdf")
        md = self.V / pending.MD_POSIX
        md.write_text(md.read_text(encoding="utf-8").replace("- 20", "- [x] 20", 1), encoding="utf-8")
        with mock.patch.object(renders, "keep", side_effect=OSError("磁碟滿了")):
            b = self.add("乙.pdf")
        self.add("丙.pdf")
        (item,) = [i for i in pending.load(self.V)["items"] if i["kind"] == "handedit"]
        diff = item["data"]["diff"]
        self.assertEqual([c["id"] for c in diff["checked"]], [a])
        self.assertNotIn(b, [c["id"] for c in diff["removed"]])
        self.assertEqual(diff["other"], [], "標題的件數行不比")


class T30Unc(unittest.TestCase):
    def test_mixed_slashes_not_checked(self):
        with mock.patch.object(citations.os.path, "exists") as exists:
            for link in ("file:///%5C/server/share/x.pdf", "file:///%2F%5Cserver/share/x.pdf", "file://///server/s/x.pdf"):
                self.assertFalse(citations._open_broken({"開原檔": link}), link)
        exists.assert_not_called()


class T31RendersFailureCounts(Base):
    def test_renders_unwritable_is_remaining(self):
        renders.set_asks(self.V, ["「王家心情」名字對嗎？"])
        counts = {"findings": 0, "backups": 0, "undecodable": 0, "left": {"state": 0}}
        with mock.patch.object(purge, "write_json_atomic", side_effect=OSError("寫不進去")):
            purge._lint_files(self.V, {"f-1"}, lambda t: str(t).replace("王家心情", "（已排除）"), self.t, counts)
        self.assertGreaterEqual(counts["left"]["state"], 1)


if __name__ == "__main__":
    unittest.main()
