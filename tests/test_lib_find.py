"""_lib/find（kb find，Obsidian 智慧搜尋，#22，D-257）：拆字（實體、卡型、標籤、時間詞、字）與比對。驗收準則 3、4。"""
import json
import shutil
import unittest

from tests import _cards
from tests import _entities as E
from kb._lib import agenda, entities, find, profile, turn  # noqa: E402

TODAY = "2026-10-30"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        self.t = turn.start(self.V, None, "")["turn"]
        self._today = agenda._today
        agenda._today = lambda: TODAY
        # 三張卡：信義王的報價（9 月）、大安陳的估價（10 月）、大安陳的會議紀錄（8 月）
        self.quote = self.card(E.QUOTE, "報價單", "報價", "2026-09-12", ["信義王"], "含水電工程與油漆。〔第 1 段〕\n")
        self.estimate = self.card(E.ESTIMATE, "估價單", "報價", "2026-10-05", ["大安陳"], "木作估價，含櫃體。〔第 1 段〕\n")
        self.meeting = self.card(_cards.MEETING, "第一次會議", "會議紀錄", "2026-08-20", ["大安陳"], "討論廚房動線。〔第 1 段〕\n")

    def tearDown(self):
        agenda._today = self._today
        shutil.rmtree(self.tmp, ignore_errors=True)

    def card(self, rel, title, kind, date, names, body):
        item = E.new_item(self.V, rel)
        text = E.with_entities(_cards.card_text(item, title, body=body, kind=kind, date=date), names)
        path = _cards.card_path(self.V, item, title)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return _cards.entry_of(self.V, rel)["id"]

    def find(self, q):
        return find.find(self.V, q, today=TODAY)

    def ids(self, q):
        return [f["card"] for f in self.find(q)["files"]]

    def kinds(self, q):
        return [(p["kind"], p["text"]) for p in self.find(q)["parsed"]]


class Parse(Base):
    def test_entity_type_time_split(self):
        out = self.find("信義王 報價 上個月")
        self.assertEqual([p["kind"] for p in out["parsed"]], ["entity", "type", "time"])
        entity, typ, time = out["parsed"]
        self.assertEqual((entity["text"], entity["value"], entity["label"]), ("信義王", "信義王", "實體 信義王"))
        self.assertEqual((typ["text"], typ["value"], typ["label"]), ("報價", "報價", "卡型 報價"))
        self.assertEqual((time["text"], time["value"], time["label"]), ("上個月", ["2026-09-01", "2026-09-30"], "時間 9/1～9/30"))

    def test_results_are_that_entity_type_and_range(self):
        self.assertEqual(self.ids("信義王 報價 上個月"), [self.quote])

    def test_leftover_words_split_on_space(self):
        out = self.find("信義王 油漆 水電")
        self.assertEqual([(p["kind"], p["text"]) for p in out["parsed"]], [("entity", "信義王"), ("word", "油漆"), ("word", "水電")])

    def test_alias_finds_the_entity(self):
        out = self.find("信義王宅 報價")
        self.assertEqual(out["parsed"][0]["value"], "信義王")
        self.assertEqual(out["entities"][0], {"name": "信義王", "type": "案子", "why": "別名"})
        self.assertEqual(self.ids("信義王宅 報價"), [self.quote])

    def test_fullwidth_and_case_fold(self):
        entities.add(self.V, "案子", "ABC樓", self.t)
        self.assertEqual(self.find("ａｂｃ樓")["parsed"][0]["value"], "ABC樓")
        self.assertEqual(self.find("ＡＢＣ樓")["parsed"][0]["value"], "ABC樓")
        self.assertEqual(self.find("abc樓")["parsed"][0]["kind"], "entity")

    def test_fullwidth_query_finds_lowercase_entity(self):
        entities.add(self.V, "案子", "abc樓", self.t)
        self.assertEqual(self.find("ＡＢＣ樓")["parsed"][0]["value"], "abc樓")

    def test_merged_old_name_finds_target(self):
        entities.add(self.V, "案子", "舊案名", self.t)
        entities.merge(self.V, "舊案名", "信義王", self.t)
        out = self.find("舊案名")
        self.assertEqual(out["parsed"][0]["value"], "信義王")
        self.assertIn(out["entities"][0]["why"], ("合併", "別名"))  # merge 後舊名也變成目標的別名

    def test_longest_match_wins(self):
        entities.add(self.V, "案子", "信義", self.t)
        out = self.find("信義王")
        self.assertEqual([(p["text"], p["value"]) for p in out["parsed"]], [("信義王", "信義王")])

    def test_removed_entity_not_matched(self):
        entities.add(self.V, "案子", "甲案", self.t)
        entities.remove(self.V, "甲案", self.t)
        self.assertEqual(self.find("甲案")["parsed"][0]["kind"], "word")

    def test_empty_query(self):
        out = self.find("   ")
        self.assertEqual((out["parsed"], out["files"], out["entities"], out["total"], out["more"]), ([], [], [], 0, False))

    def test_punctuation_is_not_a_word(self):
        self.assertEqual(self.kinds("信義王，報價。"), [("entity", "信義王"), ("type", "報價")])

    def test_text_keeps_the_original_characters(self):
        entities.add(self.V, "案子", "abc樓", self.t)
        self.assertEqual(self.find("ＡＢＣ樓")["parsed"][0]["text"], "ＡＢＣ樓")


class TimeWords(Base):
    def rng(self, q):
        return next(p["value"] for p in self.find(q)["parsed"] if p["kind"] == "time")

    def test_fixed_words(self):
        self.assertEqual(self.rng("今天"), ["2026-10-30", "2026-10-30"])
        self.assertEqual(self.rng("昨天"), ["2026-10-29", "2026-10-29"])
        self.assertEqual(self.rng("這週"), ["2026-10-26", "2026-11-01"])  # 2026-10-30 是週五
        self.assertEqual(self.rng("上週"), ["2026-10-19", "2026-10-25"])
        self.assertEqual(self.rng("這個月"), ["2026-10-01", "2026-10-31"])
        self.assertEqual(self.rng("上個月"), ["2026-09-01", "2026-09-30"])
        self.assertEqual(self.rng("今年"), ["2026-01-01", "2026-12-31"])
        self.assertEqual(self.rng("去年"), ["2025-01-01", "2025-12-31"])
        self.assertEqual(self.rng("最近"), ["2026-09-30", "2026-10-30"])

    def test_month_this_year_or_last_year_if_not_yet(self):
        self.assertEqual(self.rng("10 月"), ["2026-10-01", "2026-10-31"])
        self.assertEqual(self.rng("9月"), ["2026-09-01", "2026-09-30"])
        self.assertEqual(self.rng("12月"), ["2025-12-01", "2025-12-31"])  # 今年的 12 月還沒到 → 去年
        self.assertEqual(self.rng("11 月"), ["2025-11-01", "2025-11-30"])

    def test_year(self):
        self.assertEqual(self.rng("2025"), ["2025-01-01", "2025-12-31"])
        self.assertEqual(self.rng("2025年"), ["2025-01-01", "2025-12-31"])

    def test_year_and_month(self):
        self.assertEqual(self.rng("2025年3月"), ["2025-03-01", "2025-03-31"])

    def test_label_has_year_when_not_this_year(self):
        self.assertEqual(next(p["label"] for p in self.find("去年")["parsed"] if p["kind"] == "time"), "時間 2025/1/1～2025/12/31")

    def test_label_single_day(self):
        self.assertEqual(next(p["label"] for p in self.find("今天")["parsed"] if p["kind"] == "time"), "時間 10/30")

    def test_january_last_month_wraps_year(self):
        out = find.find(self.V, "上個月", today="2027-01-15")
        self.assertEqual(out["parsed"][0]["value"], ["2026-12-01", "2026-12-31"])

    def test_time_filter_uses_card_date(self):
        self.assertEqual(self.ids("這個月"), [self.estimate])
        self.assertEqual(sorted(self.ids("今年")), sorted([self.quote, self.estimate, self.meeting]))
        self.assertEqual(self.ids("去年"), [])


class Matching(Base):
    def test_same_kind_is_or_different_kind_is_and(self):
        self.assertEqual(sorted(self.ids("信義王 大安陳")), sorted([self.quote, self.estimate, self.meeting]))
        self.assertEqual(sorted(self.ids("信義王 大安陳 報價")), sorted([self.quote, self.estimate]))
        self.assertEqual(sorted(self.ids("報價 會議紀錄")), sorted([self.quote, self.estimate, self.meeting]))

    def test_title_hit_before_body_hit(self):
        out = self.find("估價")
        self.assertEqual([(f["card"], f["hit"]) for f in out["files"]], [(self.estimate, "title")])
        out = self.find("水電")
        self.assertEqual([(f["card"], f["hit"]) for f in out["files"]], [(self.quote, "body")])

    def test_title_hits_sort_before_newer_body_hits(self):
        out = self.find("第一次 木作")  # 第一次：會議紀錄的標題（8 月）；木作：估價單的內文（10 月，日期更新）
        self.assertEqual([(f["card"], f["hit"]) for f in out["files"]], [(self.meeting, "title"), (self.estimate, "body")])

    def test_unparsed_words_compare_title_and_body(self):
        self.assertEqual(self.ids("廚房動線"), [self.meeting])

    def test_filter_only_hit(self):
        self.assertEqual({f["hit"] for f in self.find("信義王")["files"]}, {"filter"})

    def test_newest_first_among_same_hit(self):
        self.assertEqual(self.ids("報價"), [self.estimate, self.quote])

    def test_file_fields(self):
        f = self.find("信義王")["files"][0]
        self.assertEqual(set(f), {"card", "title", "type", "date", "entities", "open", "card_path", "hit"})
        self.assertEqual((f["title"], f["type"], f["date"], f["entities"]), ("報價單", "報價", "2026-09-12", ["信義王"]))
        self.assertTrue(f["card_path"].startswith("檔案索引/"))
        self.assertIn("path", f["open"])

    def test_not_found(self):
        out = self.find("信義王 會議紀錄")
        self.assertEqual((out["files"], out["total"], out["more"]), ([], 0, False))

    def test_more_and_total_follow_the_cap(self):
        (self.V / ".system" / "config.json").write_text(json.dumps({"find_results_max": 1}), encoding="utf-8")
        out = self.find("報價")
        self.assertEqual((len(out["files"]), out["total"], out["more"]), (1, 2, True))

    def test_synthesis_body_hit_lists_entity(self):
        syn = self.V / "案子" / "信義王" / "信義王.md"
        syn.write_text(syn.read_text(encoding="utf-8") + "\n信義王的窗簾要訂做。\n", encoding="utf-8")
        out = self.find("窗簾")
        self.assertIn({"name": "信義王", "type": "案子", "why": "內文"}, out["entities"])

    def test_entity_cards_use_card_mounts(self):
        self.assertEqual(sorted(self.ids("大安陳")), sorted([self.estimate, self.meeting]))


class Tags(Base):
    def setUp(self):
        super().setUp()
        data = profile.load(self.V)
        data["tags"] = [{"type": "案子", "field": "階段", "words": ["施工中", "已交屋"], "multi": False, "source": "interview", "date": TODAY}]
        text = profile.render_text(data)
        (self.V / profile.MD_POSIX).write_text(text, encoding="utf-8", newline="\n")
        data["md_sha256"] = profile.sha256_text(text)
        (self.V / profile.PROFILE_POSIX).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        ent = entities.load(self.V)
        for e in ent["entities"]:
            if e["name"] == "信義王":
                e["tags"] = {"階段": ["施工中"]}
            if e["name"] == "大安陳":
                e["tags"] = {"階段": ["已交屋"]}
        E.put_entities(self.V, ent["entities"])

    def test_tag_word_filters_cards_of_tagged_entities(self):
        out = self.find("施工中")
        self.assertEqual([(p["kind"], p["label"]) for p in out["parsed"]], [("tag", "標籤 施工中")])
        self.assertEqual(self.ids("施工中"), [self.quote])
        self.assertEqual(sorted(self.ids("已交屋")), sorted([self.estimate, self.meeting]))
        self.assertEqual(self.ids("已交屋 報價"), [self.estimate])

    def test_two_tag_words_are_or(self):
        """裁定 11：同種類是「或」，兩個標籤詞中一個就算。"""
        out = self.find("施工中 已交屋")
        self.assertEqual([p["kind"] for p in out["parsed"]], ["tag", "tag"])
        self.assertEqual(sorted(self.ids("施工中 已交屋")), sorted([self.quote, self.estimate, self.meeting]))

    def test_tag_or_still_and_with_other_kinds(self):
        self.assertEqual(sorted(self.ids("施工中 已交屋 報價")), sorted([self.quote, self.estimate]))


class Fallback(Base):
    """裁定 12：拆完 0 筆時，整串去掉時間詞當字再找一次。"""
    def setUp(self):
        super().setUp()
        data = profile.load(self.V)
        data["tags"] = [{"type": "案子", "field": "工種", "words": ["燈具"], "multi": False, "source": "interview", "date": TODAY}]
        text = profile.render_text(data)
        (self.V / profile.MD_POSIX).write_text(text, encoding="utf-8", newline="\n")
        data["md_sha256"] = profile.sha256_text(text)
        (self.V / profile.PROFILE_POSIX).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.upgrade = self.card(E.TEMPLATE, "追加燈具升級", "報價", "2026-10-01", ["信義王"], "換燈。〔第 1 段〕\n")

    def test_zero_results_retry_whole_string_as_words(self):
        out = self.find("燈具升級")
        self.assertTrue(out["fallback"])
        self.assertEqual([(p["kind"], p["text"]) for p in out["parsed"]], [("word", "燈具升級")])
        self.assertEqual([f["card"] for f in out["files"]], [self.upgrade])

    def test_fallback_drops_time_words_and_keeps_the_rest(self):
        out = self.find("追加燈具升級 這個月")
        self.assertTrue(out["fallback"])
        self.assertEqual([(p["kind"], p["text"]) for p in out["parsed"]], [("word", "追加燈具升級")])
        self.assertEqual([f["card"] for f in out["files"]], [self.upgrade])

    def test_no_fallback_key_when_first_pass_found_something(self):
        self.assertNotIn("fallback", self.find("信義王"))

    def test_still_zero_after_fallback(self):
        out = self.find("不存在的詞語 信義王")
        self.assertEqual(out["files"], [])
        self.assertTrue(out["fallback"])
        self.assertEqual([p["kind"] for p in out["parsed"]], ["word", "word"])

    def test_nothing_to_retry_when_only_words(self):
        out = self.find("不存在的詞語")
        self.assertNotIn("fallback", out)

    def test_one_recognized_entity_is_not_retried(self):
        out = self.find("信義王 去年")
        self.assertEqual(out["files"], [])
        self.assertNotIn("fallback", out)
        self.assertEqual([p["kind"] for p in out["parsed"]], ["entity", "time"])

    def test_time_only_zero_results_has_no_fallback(self):
        out = self.find("去年")
        self.assertEqual(out["files"], [])
        self.assertNotIn("fallback", out)


class ReadOnly(Base):
    def test_nothing_written_no_turn(self):
        def snap():
            return {str(p): p.read_bytes() for p in (self.V / ".system").rglob("*.json")}, \
                sorted(p.name for p in (self.V / ".system" / "versions").iterdir()) if (self.V / ".system" / "versions").is_dir() else []
        before = snap()
        self.find("信義王 報價 上個月")
        self.assertEqual(before, snap())


if __name__ == "__main__":
    unittest.main()
