"""_lib/home（Obsidian 首頁，#22，D-252）：willy-home/1 的各區。驗收準則 1（輸出照第 1 節）、2（件數跟既有算法一樣）。"""
import datetime as dt
import json
import shutil
import unittest

from tests import _cards
from tests import _entities as E
from kb._lib import agenda, entities, home, inventory, pending, turn  # noqa: E402

TODAY = "2026-10-30"


def day(n):
    return (dt.date.fromisoformat(TODAY) + dt.timedelta(days=n)).isoformat()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        self.t = turn.start(self.V, None, "")["turn"]
        self._today = agenda._today
        agenda._today = lambda: TODAY

    def tearDown(self):
        agenda._today = self._today
        shutil.rmtree(self.tmp, ignore_errors=True)

    def card(self, rel, title):
        """替原檔寫一張檔案卡，回卡編號。"""
        _cards.write_card(self.V, E.new_item(self.V, rel), title)
        return _cards.entry_of(self.V, rel)["id"]

    def add(self, kind, date, text, entity=("信義王",), **kw):
        return agenda.add(self.V, kind, date, text, list(entity), self.t, **kw)[0]

    def build(self, **kw):
        return home.build(self.V, today=TODAY, **kw)


class Shape(Base):
    def test_top_level_keys_and_schema(self):
        out = self.build()
        self.assertEqual(out["schema"], "willy-home/1")
        self.assertEqual(out["today"], TODAY)
        self.assertEqual(set(out), {"schema", "version", "today", "cheer", "counts", "timeline", "todo", "confirm", "claude", "others", "recent"})
        self.assertEqual(set(out["counts"]), {"overdue", "today", "week", "confirm", "other", "claude"})
        self.assertEqual(set(out["todo"]), {"overdue", "today", "week"})
        self.assertEqual(set(out["timeline"]), {"from", "to", "rows"})

    def test_version_is_plugin_version(self):
        from kb._lib.paths import read_manifest
        self.assertEqual(self.build()["version"], read_manifest()["version"])

    def test_empty_agenda(self):
        out = self.build()
        self.assertEqual(out["timeline"]["rows"], [])
        self.assertEqual((out["counts"]["overdue"], out["counts"]["today"], out["counts"]["week"]), (0, 0, 0))

    def test_json_serializable(self):
        self.add("到期", day(-2), "水電")
        json.dumps(self.build(), ensure_ascii=False)


class Cheer(Base):
    def test_short_and_from_the_right_group(self):
        groups = ((range(5, 12), home.CHEER_MORNING), (range(12, 18), home.CHEER_AFTERNOON),
                  (list(range(18, 24)) + list(range(0, 5)), home.CHEER_EVENING))
        for hours, group in groups:
            for hour in hours:
                for n in range(14):
                    text = home.cheer(day(n), hour)
                    self.assertLessEqual(len(text), 8, text)
                    self.assertIn(text, group)

    def test_greeting_only_never_about_overdue(self):
        late = self.build(hour=9)["cheer"]
        self.add("到期", day(-1), "過期的")
        self.assertEqual(self.build(hour=9)["cheer"], late, "有沒有逾期句子都一樣")
        for text in home.CHEER_MORNING + home.CHEER_AFTERNOON + home.CHEER_EVENING:
            self.assertNotIn("過期", text)

    def test_time_of_day_picks_the_group(self):
        self.assertIn(self.build(hour=8)["cheer"], home.CHEER_MORNING)
        self.assertIn(self.build(hour=14)["cheer"], home.CHEER_AFTERNOON)
        self.assertIn(self.build(hour=21)["cheer"], home.CHEER_EVENING)

    def test_same_day_same_hour_same_sentence(self):
        self.assertEqual(self.build(hour=9)["cheer"], self.build(hour=10)["cheer"])


class ClickTarget(Base):
    """點日程那件該開哪張卡（裁定 32）：origin 的檔案卡 → 掛的第一個實體的綜合卡 → None。"""

    def marks(self):
        return {m["text"]: m for m in next(r for r in self.build()["timeline"]["rows"] if r["key"] == E.XINYI)["marks"]}

    def test_origin_card_first(self):
        cid = self.card(E.QUOTE, "報價單")
        self.add("到期", day(2), "有出處的", card=cid)
        got = self.marks()["有出處的"]["card"]
        self.assertEqual(got["kind"], "origin")
        self.assertTrue(got["path"].endswith(".md"))
        self.assertNotEqual(got["path"], "案子/信義王/信義王.md", "是檔案卡，不是綜合卡")

    def test_synthesis_of_first_entity_when_no_origin(self):
        self.add("到期", day(2), "沒出處的")
        self.assertEqual(self.marks()["沒出處的"]["card"], {"path": "案子/信義王/信義王.md", "kind": "synthesis"})

    def test_none_when_no_card_and_no_entity(self):
        self.add("到期", day(2), "沒掛的", entity=())
        row = next(r for r in self.build()["timeline"]["rows"] if r["key"] == home.OTHER_KEY)
        self.assertIsNone(row["marks"][0]["card"])

    def test_todo_items_carry_it_too(self):
        self.add("到期", day(-1), "過期的")
        self.assertEqual(self.build()["todo"]["overdue"][0]["card"]["kind"], "synthesis")


class Counts(Base):
    def setUp(self):
        super().setUp()
        self.add("到期", day(-3), "逾期一")
        self.add("承諾", day(-1), "逾期二")
        self.add("會議", day(-1), "過去的會")  # 會議過了不算逾期
        self.add("提醒", TODAY, "今天提醒")
        self.add("到期", TODAY, "今天到期")
        self.add("會議", day(3), "三天後的會")
        self.add("到期", day(30), "很久以後", lead_days=7)
        self.add("提醒", day(20), "提前很久提醒", lead_days=30)
        self.add("期間", day(40), "施工", start=day(-20))  # 期間不算

    def test_counts_equal_agenda_counts(self):
        got = self.build()["counts"]
        want = agenda.counts(self.V, agenda.load(self.V), TODAY)
        self.assertEqual((got["overdue"], got["today"], got["week"]), (want["overdue"], want["today"], want["upcoming"]))
        self.assertEqual((got["overdue"], got["today"], got["week"]), (2, 2, 2))

    def test_todo_groups_have_the_same_numbers(self):
        out = self.build()
        for key in ("overdue", "today", "week"):
            self.assertEqual(len(out["todo"][key]), out["counts"][key])
        self.assertEqual([m["text"] for m in out["todo"]["overdue"]], ["逾期一", "逾期二"])  # 日期早的在前

    def test_opening_line_says_the_same(self):
        import importlib.util
        from tests._guard_fixture import ROOT
        spec = importlib.util.spec_from_file_location("hook_session", ROOT / "hooks" / "session.py")
        mod = importlib.util.module_from_spec(spec)
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        spec.loader.exec_module(mod)
        line = mod.line_agenda(self.V)
        c = self.build()["counts"]
        self.assertIn(f"逾期 {c['overdue']}", line)
        self.assertIn(f"今天 {c['today']}", line)
        self.assertIn(f"天內 {c['week']}", line)

    def test_done_and_cancelled_not_counted(self):
        it = self.add("到期", day(-9), "做完了")
        agenda.set_status(self.V, it["id"], "done", self.t)
        out = self.build()
        self.assertEqual(out["counts"]["overdue"], 2)
        self.assertNotIn("做完了", [m["text"] for m in out["todo"]["overdue"]])


class Timeline(Base):
    def test_one_row_per_active_matter_entity_and_other(self):
        self.add("期間", day(30), "施工", start=day(-10))
        self.add("到期", day(5), "水電驗收", entity=("大安陳",))
        self.add("提醒", day(2), "沒掛實體的", entity=())
        self.add("提醒", day(3), "掛業主的", entity=("林小姐室內設計",))  # 非事類實體 → 其他
        rows = self.build()["timeline"]["rows"]
        keys = [r["key"] for r in rows]
        self.assertEqual(sorted(keys), sorted([E.XINYI, E.DAAN, home.OTHER_KEY]))
        self.assertEqual(keys[-1], home.OTHER_KEY)  # 其他放最後
        other = rows[-1]
        self.assertEqual((other["label"], other["type"]), ("其他", None))
        self.assertEqual(len(other["marks"]), 2)

    def test_row_fields(self):
        self.add("期間", day(30), "施工", start=day(-10))
        row = next(r for r in self.build()["timeline"]["rows"] if r["key"] == E.XINYI)
        self.assertEqual((row["label"], row["type"], row["progress"]), ("信義王", "案子", "active"))
        self.assertEqual(row["links"], [])
        self.assertEqual(row["pauses"], [])

    def test_bar_and_point_marks(self):
        self.add("期間", day(30), "施工", start=day(-10))
        self.add("會議", day(4), "開會", time="14:00")
        marks = {m["text"]: m for m in next(r for r in self.build()["timeline"]["rows"] if r["key"] == E.XINYI)["marks"]}
        bar, point = marks["施工"], marks["開會"]
        self.assertEqual((bar["shape"], bar["kind"], bar["start"], bar["end"]), ("bar", "period", day(-10), day(30)))
        self.assertEqual((point["shape"], point["kind"], point["end"], point["time"], point["hard"]), ("point", "meeting", day(4), "14:00", True))
        for m in (bar, point):
            self.assertEqual((m["baseline"], m["critical"], m["slack"], m["derived"], m["children"]), (None, False, None, False, []))
            self.assertEqual(m["entities"], ["信義王"])

    def test_late_inferred_repeat(self):
        self.add("到期", day(-2), "晚了的")
        self.add("提醒", day(1), "每週的", repeat="每週")
        self.add("到期", day(2), "推測的", card=self.card(E.QUOTE, "報價單"))
        marks = {m["text"]: m for m in next(r for r in self.build()["timeline"]["rows"] if r["key"] == E.XINYI)["marks"]}
        self.assertTrue(marks["晚了的"]["late"])
        self.assertFalse(marks["每週的"]["late"])
        self.assertEqual(marks["每週的"]["repeat"], "每週")
        self.assertTrue(marks["推測的"]["inferred"])

    def test_meeting_in_the_past_is_not_late(self):
        self.add("會議", day(-2), "過去的會")
        m = next(r for r in self.build()["timeline"]["rows"] if r["key"] == E.XINYI)["marks"][0]
        self.assertFalse(m["late"])

    def test_window_from_and_to(self):
        out = self.build()["timeline"]
        self.assertEqual(out["from"], day(-7))
        self.assertEqual(out["to"], day(60))

    def test_far_future_and_cancelled_left_out_but_overdue_open_stays(self):
        self.add("到期", day(200), "太遠了")
        c = self.add("到期", day(5), "取消的")
        agenda.set_status(self.V, c["id"], "cancelled", self.t)
        self.add("到期", day(-30), "好久前還沒做")
        texts = [m["text"] for r in self.build()["timeline"]["rows"] for m in r["marks"]]
        self.assertEqual(texts, ["好久前還沒做"])

    def test_done_before_window_left_out_done_recent_kept(self):
        old = self.add("到期", day(-30), "舊的完成")
        new = self.add("到期", day(-3), "剛完成")
        for it in (old, new):
            agenda.set_status(self.V, it["id"], "done", self.t)
        texts = [m["text"] for r in self.build()["timeline"]["rows"] for m in r["marks"]]
        self.assertEqual(texts, ["剛完成"])

    def test_row_order_nearest_open_date_first(self):
        self.add("到期", day(20), "晚的", entity=("信義王",))
        self.add("到期", day(5), "早的", entity=("大安陳",))
        keys = [r["key"] for r in self.build()["timeline"]["rows"]]
        self.assertEqual(keys, [E.DAAN, E.XINYI])

    def test_closed_matter_marks_stay_with_progress_closed(self):
        self.add("提醒", day(2), "還開著")
        entities.set_progress(self.V, "信義王", "closed", self.t)
        row = next(r for r in self.build()["timeline"]["rows"] if r["key"] == E.XINYI)
        self.assertEqual(row["progress"], "closed")

    def test_paused_entity_listed_with_pauses(self):
        self.add("期間", day(30), "施工", start=day(-10))
        entities.set_progress(self.V, "信義王", "paused", self.t)
        row = next(r for r in self.build()["timeline"]["rows"] if r["key"] == E.XINYI)
        self.assertEqual(row["progress"], "paused")
        self.assertEqual(len(row["pauses"]), 1)
        self.assertEqual(set(row["pauses"][0]), {"start", "end"})

    def test_alias_of_entity_maps_to_its_row(self):
        self.add("提醒", day(2), "用別名掛的", entity=("信義王宅",))
        keys = [r["key"] for r in self.build()["timeline"]["rows"]]
        self.assertEqual(keys, [E.XINYI])

    def test_done_period_end_uses_ended(self):
        it = self.add("期間", day(30), "做完的施工", start=day(-20))
        agenda.set_status(self.V, it["id"], "done", self.t)
        m = next(r for r in self.build()["timeline"]["rows"] if r["key"] == E.XINYI)["marks"][0]
        self.assertEqual((m["status"], m["start"]), ("done", day(-20)))
        self.assertEqual(m["end"], agenda.get(self.V, it["id"]).get("ended") or day(30))


class Sections(Base):
    def test_others_are_open_pending_not_in_asks(self):
        out = self.build()
        asked = {a["key"] for a in out["confirm"]}
        for o in out["others"]:
            self.assertNotIn(o["id"], asked)
            self.assertTrue(o["dismiss"])
        self.assertEqual(out["counts"]["other"], len(out["others"]))
        self.assertEqual(out["counts"]["confirm"], len(out["confirm"]))

    def test_confirm_and_claude_split_kb_asks(self):
        from kb import asks_cli
        want = [a for a in asks_cli._collect(self.V)[0] if a["kind"] != "overdue"]
        out = self.build()
        got = {a["key"]: a for a in out["confirm"] + out["claude"]}
        self.assertEqual(sorted(got), sorted(a["key"] for a in want))
        for w in want:
            self.assertEqual(got[w["key"]]["text"], w["question"])
        self.assertEqual(out["counts"]["claude"], len(out["claude"]) + len(out["others"]))

    def test_argv_from_do(self):
        self.assertEqual(home._argv(["kb pending dismiss p-1"]), ["pending", "dismiss", "p-1"])
        self.assertEqual(home._argv(['kb pending resolve p-1 --how "{客戶的話}"']), ["pending", "resolve", "p-1", "--how", "{客戶的話}"])
        self.assertEqual(home._argv(['kb entity add "王 先生" --type 業主']), ["entity", "add", "王 先生", "--type", "業主"])
        self.assertIsNone(home._argv([]))
        self.assertIsNone(home._argv(["kb a", "kb b"]))
        self.assertIsNone(home._argv(["kb 'unclosed"]))

    def test_every_confirm_result_has_argv_or_null_and_fill_shape(self):
        for a in self.build()["confirm"]:
            for r in a["results"]:
                self.assertIn("argv", r)
                self.assertTrue(r["argv"] is None or (isinstance(r["argv"], list) and all(isinstance(x, str) for x in r["argv"])))
                self.assertTrue(r["fill"] is None or {"name", "rule", "input"} <= set(r["fill"]) <= {"name", "rule", "input", "options"})


class SetAside(Base):
    """裁定 39：首頁自己補「先放著」（逐種驗在 test_home_confirm_kinds）；過期的在待辦處理，確認區與最下面那行都不列。"""

    def test_real_overdue_ask_listed_nowhere(self):
        self.add("到期", day(-2), "過了的事")
        out = self.build()
        self.assertEqual([a for a in out["confirm"] + out["claude"] if a["kind"] == "overdue"], [])


class Range(Base):
    """裁定 34：build 可指定時間軸的起訖；沒帶照舊今天前 7 天到 home_timeline_days。"""

    def test_default_window_unchanged(self):
        out = self.build()["timeline"]
        self.assertEqual((out["from"], out["to"]), (day(-7), day(60)))

    def test_given_window_is_used(self):
        self.add("到期", day(100), "三個月後的事")
        out = self.build(lo=day(-30), hi=day(120))["timeline"]
        self.assertEqual((out["from"], out["to"]), (day(-30), day(120)))
        self.assertEqual([m["text"] for r in out["rows"] for m in r["marks"]], ["三個月後的事"])

    def test_only_one_end_given_other_default(self):
        out = self.build(hi=day(200))["timeline"]
        self.assertEqual((out["from"], out["to"]), (day(-7), day(200)))
        out = self.build(lo=day(-90))["timeline"]
        self.assertEqual((out["from"], out["to"]), (day(-90), day(60)))

    def test_done_before_given_from_still_left_out(self):
        it = self.add("到期", day(-20), "舊的完成")
        agenda.set_status(self.V, it["id"], "done", self.t)
        self.assertEqual([m for r in self.build(lo=day(-10))["timeline"]["rows"] for m in r["marks"]], [])
        self.assertEqual([m["text"] for r in self.build(lo=day(-30))["timeline"]["rows"] for m in r["marks"]], ["舊的完成"])

    def test_other_sections_do_not_change_with_window(self):
        a, b = self.build(), self.build(lo=day(-300), hi=day(300))
        for key in ("todo", "confirm", "counts", "others", "cheer"):
            self.assertEqual(a[key], b[key], key)


class Recent(Base):
    def setUp(self):
        super().setUp()
        self.f1 = self.card(E.QUOTE, "報價單")
        self.f2 = self.card(E.ESTIMATE, "估價單")

    def test_added_newest_first(self):
        out = self.build()["recent"]
        self.assertTrue(out)
        stamps = [r["at"] for r in out if r["why"] == "added"]
        self.assertEqual(stamps, sorted(stamps, reverse=True))
        for r in out:
            self.assertEqual(set(r), {"card", "title", "type", "date", "why", "at", "open", "card_path"})

    def test_opened_come_first_and_deduplicate(self):
        out = self.build(opened=[self.f2, self.f1, "f-不存在"])
        self.assertEqual([r["card"] for r in out["recent"][:2]], [self.f2, self.f1])
        self.assertEqual([r["why"] for r in out["recent"][:2]], ["opened", "opened"])
        cards = [r["card"] for r in out["recent"]]
        self.assertEqual(len(cards), len(set(cards)))
        self.assertNotIn("f-不存在", cards)

    def test_open_path_is_existing_absolute_forward_slash(self):
        row = next(r for r in self.build(opened=[self.f1])["recent"] if r["card"] == self.f1)
        self.assertIn("path", row["open"])
        self.assertNotIn("\\", row["open"]["path"])
        import os
        self.assertTrue(os.path.exists(row["open"]["path"]))

    def test_max_from_config(self):
        (self.V / ".system" / "config.json").write_text(json.dumps({"home_recent_max": 1}), encoding="utf-8")
        self.assertEqual(len(self.build(opened=[self.f1, self.f2])["recent"]), 1)

    def test_link_entry_opens_with_url(self):
        data = inventory.load(self.V)
        e = next(x for x in data["entries"] if x["id"] == self.f1)
        e["kind"] = "link"
        e["locations"] = [{"uri": "https://claude.ai/artifact/abc"}]
        self.assertEqual(home._open_target(self.V, None, e), {"url": "https://claude.ai/artifact/abc"})


class Resilience(Base):
    def test_broken_agenda_still_returns_the_rest(self):
        (self.V / ".system" / "agenda.json").write_text("{壞掉", encoding="utf-8")
        out = self.build()
        self.assertEqual(out["timeline"]["rows"], [])
        self.assertTrue(any("日程" in w for w in out["warnings"]))
        self.assertIn("recent", out)

    def test_14_broken_sources_only_blanks_what_needs_it(self):
        """裁定 14：.system/sources.json 壞了，只有要用它的那區空白，其他照常（驗收 1 的 resilience）。"""
        (self.V / ".system" / "sources.json").write_text("{bad", encoding="utf-8")
        out = self.build()
        self.assertTrue(any("來源" in w for w in out["warnings"]), out.get("warnings"))
        self.assertEqual(out["recent"], [])
        for key in ("timeline", "todo", "confirm", "others", "counts", "cheer"):
            self.assertIn(key, out)

    def test_14_broken_sources_cli_exit_0_with_json(self):
        (self.V / ".system" / "sources.json").write_text("{bad", encoding="utf-8")
        from tests.test_scripts_inventory_cli import run_kb
        r = run_kb("home", "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["schema"], "willy-home/1")

    def test_read_only_and_no_turn(self):
        before = sorted(p.name for p in (self.V / ".system" / "versions").iterdir()) if (self.V / ".system" / "versions").is_dir() else []
        files = {str(p): p.stat().st_mtime_ns for p in (self.V / ".system").rglob("*") if p.is_file() and "hook-errors" not in p.name}
        self.build()
        after = sorted(p.name for p in (self.V / ".system" / "versions").iterdir()) if (self.V / ".system" / "versions").is_dir() else []
        self.assertEqual(before, after)
        for p, m in files.items():
            self.assertEqual(__import__("pathlib").Path(p).stat().st_mtime_ns, m, p)

    def test_patches_restored_after_build(self):
        from kb._lib import cards, config
        real = (cards._scan_groups, cards.open_link, config.get, entities.mounts)
        self.build()
        self.assertEqual((cards._scan_groups, cards.open_link, config.get, entities.mounts), real)


if __name__ == "__main__":
    unittest.main()
