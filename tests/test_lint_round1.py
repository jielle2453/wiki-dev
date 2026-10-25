"""lint 第一輪測試報告的修正（design/reports/lint-測試.md）：T-1～T-11、T-13～T-16、T-19、T-20、T-22、T-24，加「其他」節的
開原檔遇 UNC 不查、手改留下的那份遮值。T-8 的端到端在 test_lib_purge 的 LintFiles。"""
import datetime as dt
import json
import os
import shutil
import subprocess
import types
import unittest
from unittest import mock

from tests import _entities as E
from tests import _lint as L
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import cards, entities, inventory, pending, plan, profile, renders, statements, turn  # noqa: E402
from kb.lint import checks, report, runner, state  # noqa: E402
from kb.lint.checks import citations, empty_sections, inferred, sizes, stale_by_profile  # noqa: E402

TODAY = dt.date.today()


def fake(name, found=None, boom=False):
    def run(ctx):
        if boom:
            raise RuntimeError("壞了")
        return [dict(f) for f in found or []]
    mod = types.SimpleNamespace(NAME=name, run=run)
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

    def lint_items(self, key=None):
        return [i for i in pending.load(self.V)["items"] if i["kind"] == "lint" and (key is None or i["key"] == key)]


class T1CloseWhenGone(Base):
    def test_closed_when_check_ran_and_did_not_return_it(self):
        self.run_with([fake("guard", [runner.finding("guard", "decide", "guard_stale", "守門沒在跑", items=["10-01"])])])
        self.run_with([fake("guard", [])])
        (item,) = self.lint_items("guard_stale")
        self.assertEqual((item["status"], item["how"]), ("done", runner.NOT_TRUE_HOW))

    def test_failed_check_keeps_it(self):
        self.run_with([fake("guard", [runner.finding("guard", "decide", "guard_stale", "守門沒在跑", items=["10-01"])])])
        self.run_with([fake("guard", boom=True)])
        self.assertEqual(self.lint_items("guard_stale")[0]["status"], "open")


class T2AnsweredStaysClosed(Base):
    def found(self, items):
        return [fake("inferred", [runner.finding("inferred", "decide", "inferred:entity", "名字是我猜的", items=items)])]

    def test_dismissed_not_reopened_until_items_change(self):
        self.run_with(self.found(["王宅"]))
        (item,) = self.lint_items()
        pending.dismiss(self.V, item["id"], self.t)
        self.run_with(self.found(["王宅"]))
        self.assertEqual([i["status"] for i in self.lint_items()], ["dismissed"])
        self.run_with(self.found(["王宅", "林宅"]))
        self.assertEqual(sorted(i["status"] for i in self.lint_items()), ["dismissed", "open"])

    def test_closed_by_lint_reopens(self):
        self.run_with(self.found(["王宅"]))
        self.run_with([fake("inferred", [])])
        self.run_with(self.found(["王宅"]))
        self.assertEqual(sorted(i["status"] for i in self.lint_items()), ["done", "open"])

    def test_redo_marked_cards_not_candidates(self):
        a = L.write_card(self.V, E.QUOTE, "信義王報價")
        p = self.V / cards.card_of(self.V, a)["path"]
        p.write_text(p.read_text(encoding="utf-8").replace(f"製卡日期: {TODAY.isoformat()}", "製卡日期: 2026-10-01"),
                     encoding="utf-8")
        prof = json.loads((self.V / profile.PROFILE_POSIX).read_text(encoding="utf-8"))
        for row in prof["card_types"]:
            if row["name"] == "報價":
                row["date"] = "2026-10-20"
        (self.V / profile.PROFILE_POSIX).write_text(json.dumps(prof, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(len([f for f in stale_by_profile.run(L.ctx(self.V)) if f["kind"] == "decide"]), 1)
        cards.mark_redo(self.V, a, self.t)
        self.assertEqual([f for f in stale_by_profile.run(L.ctx(self.V)) if f["kind"] == "decide"], [])


class T3PastDatesNotUrgent(Base):
    def item(self, day):
        pid, _c = pending.add_lint(self.V, "inferred:agenda", "推測的日程放太久", {"dates": [day]}, self.t)
        return pid

    def test_past_date(self):
        pid = self.item((TODAY - dt.timedelta(days=5)).isoformat())
        asks, _h = plan.pending_asks(self.V)
        self.assertFalse(next(a for a in asks if a["key"] == pid)["urgent"])
        pending.set_aside(self.V, pid, "customer", self.t)
        self.assertEqual(pending.due_back(self.V, pending.load(self.V)["items"]), set())

    def test_tomorrow(self):
        pid = self.item((TODAY + dt.timedelta(days=1)).isoformat())
        asks, _h = plan.pending_asks(self.V)
        self.assertTrue(next(a for a in asks if a["key"] == pid)["urgent"])


class T4UrgentCannotBeSetAside(Base):
    def test_overdue_refused_with_answers(self):
        past = (TODAY - dt.timedelta(days=3)).isoformat()
        item = {"id": "a-12345678", "kind": "promise", "date": past, "text": "給報價", "entities": ["大安陳"], "status": "open",
                "source": "interview", "created_turn": "t", "history": []}
        (self.V / ".system" / "agenda.json").write_text(json.dumps({"schema_version": 1, "items": [item]}, ensure_ascii=False),
                                                         encoding="utf-8")
        key = next(a["key"] for a in json.loads(run_kb("asks", "--all", "--json", cwd=self.V).stdout)["asks"]
                   if a["kind"] == "overdue")
        r = run_kb("asks", "set-aside", key, cwd=self.V)
        self.assertEqual(r.returncode, 3)
        self.assertEqual(r.stdout.splitlines()[0], "這件已經過了日期，沒辦法先放著：做完了、不用了，還是改到哪一天？")
        got = json.loads(run_kb("asks", "set-aside", key, "--json", cwd=self.V).stdout)
        self.assertEqual(got["refused"], "這件已經過了日期，沒辦法先放著：做完了、不用了，還是改到哪一天？")
        self.assertEqual([x["label"] for x in got["ask"]["results"]], ["完成了", "不用了", "還沒，改到某天", "還沒，下次再問"])
        self.assertIn(key, [a["key"] for a in json.loads(run_kb("asks", "--all", "--json", cwd=self.V).stdout)["asks"]])


class T5StillUnreadable(Base):
    def test_card_behind_current_file_keeps_unreadable(self):
        a = L.write_card(self.V, E.QUOTE, "信義王報價")
        pid = pending.add(self.V, "unreadable", [a], "「報價_v2.pdf」讀不到", "有密碼", self.t)
        p = self.V / inventory.INVENTORY_POSIX
        inv = json.loads(p.read_text(encoding="utf-8"))
        e = next(x for x in inv["entries"] if x["id"] == a)
        e["fingerprints"].append(dict(e["fingerprints"][-1], sha256="1" * 64))
        p.write_text(json.dumps(inv, ensure_ascii=False), encoding="utf-8")
        self.run_with([])
        self.assertEqual(next(i for i in pending.load(self.V)["items"] if i["id"] == pid)["status"], "open")


class T6ArchiveFollowsRename(Base):
    def test_rename_changes_archived_statements(self):
        a = statements.add(self.V, "信義王改用系統櫃", ["信義王"], self.t)[0]["id"]
        statements.add(self.V, "信義王改回木工", ["信義王"], self.t, replaces=a)
        statements.archive(self.V, [a], self.t)
        entities.rename(self.V, "信義王", "王宅邸", None, self.t)
        (arch,) = statements.load_archive(self.V)["statements"]
        self.assertEqual(arch["entities"], ["王宅邸"])


class T7FixOnlyOnce(Base):
    def test_second_run_does_not_repeat(self):
        L.write_synthesis(self.V, body="## 現況\n- 進行中\n\n## 時程\n")
        (f1,) = empty_sections.run(L.ctx(self.V))
        self.assertTrue(f1["apply"](L.ctx(self.V)))
        (f2,) = empty_sections.run(L.ctx(self.V))
        self.assertIsNone(f2["apply"](L.ctx(self.V)))


class T9QuotedDo(Base):
    def test_name_with_shell_chars_is_quoted(self):
        data = entities.load(self.V)
        data["entities"].append(E.entity("e-99990000", "x;calc", source="inferred", date="2026-08-01"))
        E.put_entities(self.V, data["entities"])
        found = {f["key"]: f for f in inferred.run(L.ctx(self.V, today="2026-10-25"))}
        do = found["inferred:entity"]["data"]["results"][0]["do"]
        self.assertIn('kb entity confirm "x;calc"', do)


class T10KeepFailsNoRewrite(Base):
    def test_pending_md_kept_when_copy_fails(self):
        pending.add(self.V, "unreadable", ["f-11111111"], "「甲.pdf」讀不到", "檔案壞了", self.t)
        md = self.V / pending.MD_POSIX
        hers = md.read_text(encoding="utf-8").replace("- 20", "- [x] 20", 1)
        md.write_text(hers, encoding="utf-8")
        with mock.patch.object(renders, "keep", side_effect=OSError("磁碟滿了")):
            pending.add(self.V, "unreadable", ["f-22222222"], "「乙.pdf」讀不到", "檔案壞了", self.t)
        self.assertEqual(md.read_text(encoding="utf-8"), hers, "留不住她那份就不重寫")

    def test_index_kept_when_copy_fails(self):
        cards.render_index(self.V, self.t)
        p = self.V / cards.INDEX_POSIX
        p.write_text(p.read_text(encoding="utf-8") + "我加的\n", encoding="utf-8")
        with mock.patch.object(renders, "keep", side_effect=OSError("磁碟滿了")):
            cards.render_index(self.V, self.t)
        self.assertIn("我加的", p.read_text(encoding="utf-8"))


class T11Bom(Base):
    def test_bom_is_not_a_hand_edit(self):
        pending.add(self.V, "unreadable", ["f-11111111"], "「甲.pdf」讀不到", "檔案壞了", self.t)
        md = self.V / pending.MD_POSIX
        md.write_bytes("﻿".encode("utf-8") + md.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))
        self.assertIsNone(renders.check(self.V, pending.MD_POSIX))


@unittest.skipUnless(os.name == "nt", "mklink /J 只在 Windows")
class T13SizesSkipJunction(Base):
    def test_junction_not_counted(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "big.bin").write_bytes(b"x" * 3_000_000)
        link = self.V / ".system" / "temp"
        if link.exists():
            shutil.rmtree(link)
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        (num,) = [f for f in sizes.run(L.ctx(self.V)) if f["kind"] == "number"]
        self.assertLess(num["data"]["vault_bytes"], 3_000_000)


class T14InnerTypes(Base):
    def test_renders_history_wrong_type(self):
        (self.V / renders.RENDERS_POSIX).write_text(json.dumps({"schema_version": 1, "files": {}, "history": {"a.md": 5}}),
                                                     encoding="utf-8")
        renders.record(self.V, "a.md", "x\n")
        self.assertIsNone(renders.check(self.V, "a.md"))

    def test_lint_json_wrong_types(self):
        state.save(self.V, {"last_counts": "壞", "last_report": 5, "last_background": 7, "synthesis_fix": "x", "month_done": 3})
        st = state.load(self.V)
        self.assertEqual((st["last_counts"], st["last_report"], st["last_background"], st["synthesis_fix"], st["month_done"]),
                         (None, None, None, [], []))
        self.run_with([])
        self.run_with([], background=True)


class T15FutureDate(Base):
    def test_future_last_background_counts_as_due(self):
        state.save(self.V, dict(state.load(self.V), last_background="2099-01-01"))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(runner.NO_BACKGROUND_ENV, None)
            with mock.patch.object(runner, "_spawn") as spawn:
                self.assertTrue(runner.opening(self.V))
        spawn.assert_called_once()


class T16FailedNotAllFine(unittest.TestCase):
    def test_summary(self):
        self.assertEqual(report.summary(0, 0, None, failed=2), "有 2 項這次沒查成。")
        self.assertEqual(report.summary(2, 1, None, failed=1), "大致正常，有 1 項這次沒查成；這個月替你做了 1 件事。")


class T19RulingsHeader(unittest.TestCase):
    def test_header_consistent(self):
        from kb._lib import rulings
        self.assertNotIn("不會生效", rulings.HEADER)


class T20ReportItemNotCounted(Base):
    def test_old_report_item_not_in_monthly_decide(self):
        pending.add_report(self.V, "2026-08", self.t)
        state.save(self.V, dict(state.load(self.V), last_report="2026-08", last_background="2026-09-28"))
        self.run_with([], background=True, today="2026-10-02")
        text = (self.V / "系統" / "健檢報告" / "2026-09.md").read_text(encoding="utf-8")
        self.assertNotIn("健檢報告出來了", text)


class T22DefaultRowsNotGuesses(Base):
    def test_only_rows_added_later(self):
        p = self.V / profile.PROFILE_POSIX
        prof = json.loads(p.read_text(encoding="utf-8"))
        for sec in ("card_types", "exclusions", "synthesis_sections"):
            for row in prof.get(sec) or []:
                row["date"] = "2026-08-01"
        p.write_text(json.dumps(prof, ensure_ascii=False), encoding="utf-8")
        found = {f["key"] for f in inferred.run(L.ctx(self.V, today="2026-10-25"))}
        self.assertNotIn("inferred:profile", found, "程式預設的列不算我推測的")
        prof["card_types"].append({"name": "請款", "sections": [], "source": "inferred", "date": "2026-08-01"})
        p.write_text(json.dumps(prof, ensure_ascii=False), encoding="utf-8")
        found = {f["key"]: f for f in inferred.run(L.ctx(self.V, today="2026-10-25"))}
        self.assertEqual(found["inferred:profile"]["items"], ["card_types:請款"])


class T24IngestAfterUpkeep(Base):
    def test_conflict_count_after_closing(self):
        card = L.write_card(self.V, E.QUOTE, "信義王報價")
        pending.add_conflict(self.V, [card, "f-00000077"], "寫法不同", self.t)
        got = runner.run(self.V)
        self.assertEqual(got["ingest"]["conflicts"], 0)


class OtherUncAndMask(Base):
    def test_unc_link_not_checked(self):
        self.assertFalse(citations._open_broken({"開原檔": "file://///server/share/x.pdf"}))
        self.assertFalse(citations._open_broken({"開原檔": "file:///%5C%5Cserver%5Cshare%5Cx.pdf"}))

    def test_saved_copy_and_other_masked(self):
        pending.add(self.V, "unreadable", ["f-11111111"], "「甲.pdf」讀不到", "檔案壞了", self.t)
        md = self.V / pending.MD_POSIX
        md.write_text(md.read_text(encoding="utf-8") + "網銀密碼：Hunter2xyz\n", encoding="utf-8")
        pending.add(self.V, "unreadable", ["f-22222222"], "「乙.pdf」讀不到", "檔案壞了", self.t)
        (item,) = [i for i in pending.load(self.V)["items"] if i["kind"] == "handedit"]
        self.assertNotIn("Hunter2xyz", json.dumps(item["data"]["diff"], ensure_ascii=False))
        self.assertNotIn("Hunter2xyz", (self.V / item["data"]["saved"]).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
