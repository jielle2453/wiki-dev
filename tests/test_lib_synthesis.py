"""_lib/synthesis（實體與綜合卡第 2 點，D-114～D-121）：validate 每條錯各一、句子一字不差；render_cache 只改兩欄、
內容沒變不寫、備份帶 by program；buckets 四桶各一、門檻邊界 1 與 2 張、客戶自己不列、型別表沒有的不列。"""
import shutil
import unittest
from pathlib import Path

from tests import _entities as E
from kb._lib import cards, config, entities, synthesis, turn  # noqa: E402

XINYI_REL = "案子/信義王/信義王.md"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        self.t = turn.start(self.V, None, "")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def entity(self, eid):
        return next(e for e in entities.load(self.V)["entities"] if e["id"] == eid)

    def update(self, eid, **kw):
        data = entities.load(self.V)["entities"]
        for e in data:
            if e["id"] == eid:
                e.update(kw)
        E.put_entities(self.V, data)

    def buckets(self):
        data = entities.load(self.V)
        return synthesis.buckets(self.V, data, entities.mounts(self.V, data), entities._profile(self.V))

    def header(self, eid):
        data = entities.load(self.V)
        mounts = entities.mounts(self.V, data)
        e = self.entity(eid)
        return synthesis.header_for(self.V, e, mounts.get(e["name"], []), "2026-10-20")


class Header(Base):
    def test_header_shape(self):
        E.write_card(self.V, E.QUOTE, "信義王報價第二版", ["信義王", "王宅"], date="2026-10-01")
        E.write_card(self.V, E.ESTIMATE, "信義王估價", ["信義王"], date="2026-09-12")
        front = cards.parse_front(self.header(E.XINYI))
        self.assertEqual(list(front), list(synthesis.KEYS))
        self.assertEqual((front["編號"], front["型別"], front["大類"], front["名稱"], front["別名"], front["範本版本"],
                          front["更新日"]), (E.XINYI, "案子", "事", "信義王", ["信義王宅"], "2", "2026-10-20"))
        self.assertEqual([x.split(" ", 2)[2] for x in front["檔案卡"]], ["信義王報價第二版", "信義王估價"])
        self.assertTrue(all(len(x.split(" ")[1]) == 12 for x in front["整理到"]))
        self.assertEqual(front["整理到"], sorted(front["整理到"]))
        self.assertEqual(front["相關實體"], ["王宅"])

    def test_sections_for(self):
        got = synthesis.sections_for(entities._profile(self.V), "案子")
        self.assertEqual([s["name"] for s in got], ["現況", "時程", "金額", "推算", "紀事"])
        self.assertEqual([s["name"] for s in synthesis.sections_for(entities._profile(self.V), "不在表")],
                         ["現況", "推算", "紀事"])


class Validate(Base):
    def write(self, text, rel=XINYI_REL):
        p = self.V / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return synthesis.validate(self.V, rel)

    def good(self):
        return E.synthesis_text(self.header(E.XINYI), "信義王")

    def test_good_ok(self):
        self.assertEqual(self.write(self.good()), (True, ""))

    def test_each_error_sentence(self):
        good = self.good()
        E.write_card(self.V, E.ESTIMATE, "信義王估價", ["信義王"])
        stale = good  # 整理到是空的，現在掛了一張
        cases = [
            ("---\n編號: e-5c1d0a7e\n", XINYI_REL, "檔頭解析不了：少了結尾的 ---"),
            (good.replace("更新日: 2026-10-20\n", ""), XINYI_REL, "檔頭少了「更新日」"),
            (good.replace(E.XINYI, "e-99999999"), XINYI_REL, "編號 e-99999999 不在實體清單"),
            (good.replace(E.XINYI, E.SELF), XINYI_REL, "這是你自己（關於你），不寫綜合卡"),
            (good.replace(E.XINYI, E.WANG), XINYI_REL, "還沒跟客戶確認名稱，先問再寫"),
            (good, "案子/王宅/王宅.md", "綜合卡該放在 案子/信義王/信義王.md"),
            (good.replace("名稱: 信義王", "名稱: 信義"), XINYI_REL, "「名稱」照 kb cards todo 給的檔頭抄"),
            (good.replace("範本版本: 2", "範本版本: 9"), XINYI_REL, "範本版本該是 2"),
            (stale, XINYI_REL, "整理到不是現行的，重跑 kb cards todo 拿新檔頭"),
        ]
        for text, rel, want in cases:
            with self.subTest(want=want):
                self.assertEqual(self.write(text, rel), (False, want))

    def test_more_error_sentences(self):
        good = self.good()
        cases = [
            (good.replace("更新日: 2026-10-20", "更新日: 10/20"), "更新日要寫 YYYY-MM-DD"),
            (good.replace("## 現況", "## 近況"), "正文要有 # 信義王 與 ## 現況"),
            (good.replace("# 信義王\n", "# 信義王宅\n"), "正文要有 # 信義王 與 ## 現況"),
        ]
        for text, want in cases:
            with self.subTest(want=want):
                self.assertEqual(self.write(text), (False, want))
        self.update(E.XINYI, status="removed")
        self.assertEqual(self.write(good), (False, "這個實體已移除"))

    def test_list_value_where_string_expected_is_not_crash_free_pass(self):
        ok, reason = self.write(self.good().replace("編號: e-5c1d0a7e", "編號: [e-5c1d0a7e]"))
        self.assertFalse(ok)
        self.assertIn("不在實體清單", reason)


class RenderCache(Base):
    def test_only_two_fields_change_and_program_backup(self):
        card = self.V / XINYI_REL
        before = card.read_text(encoding="utf-8").splitlines()
        E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王", "王宅"], date="2026-10-01")
        self.assertEqual(synthesis.render_cache(self.V, ["信義王"], self.t), [XINYI_REL])
        after = card.read_text(encoding="utf-8").splitlines()
        front = cards.parse_front("\n".join(after))
        self.assertEqual([x.split(" ", 2)[2] for x in front["檔案卡"]], ["信義王報價"])
        self.assertEqual(front["相關實體"], ["王宅"])
        unchanged = [ln for ln in before if not ln.startswith(("檔案卡:", "相關實體:"))]
        i, j = after.index(synthesis.FILE_BEGIN), after.index(synthesis.FILE_END)  # 「相關檔」那段是另一件事（FileSection 測）
        rest = after[:i] + after[j + 2:]  # D-523：插在紀事前面，連同後面的空行
        self.assertEqual([ln for ln in rest if not ln.startswith(("檔案卡:", "相關實體:", "  - "))], unchanged)
        rows = {r["path"]: r for r in turn.entries(self.V, self.t)}
        self.assertEqual(rows[XINYI_REL]["by"], "program")
        self.assertEqual(turn.modified_synthesis_count(self.V, self.t), 0)

    def test_unchanged_not_written(self):
        card = self.V / XINYI_REL
        mtime = card.stat().st_mtime_ns
        self.assertEqual(synthesis.render_cache(self.V, None, self.t), [])
        self.assertEqual(card.stat().st_mtime_ns, mtime)
        self.assertEqual(turn.entries(self.V, self.t), [])

    def test_self_not_in_related(self):
        E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王", "林小姐室內設計"])
        synthesis.render_cache(self.V, ["信義王"], self.t)
        self.assertEqual(cards.parse_front((self.V / XINYI_REL).read_text(encoding="utf-8"))["相關實體"], [])

    def test_broken_card_left_alone(self):
        card = self.V / XINYI_REL
        card.write_text(card.read_text(encoding="utf-8").replace("範本版本: 1", "範本版本: 9"), encoding="utf-8")
        E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王"])
        self.assertEqual(synthesis.render_cache(self.V, ["信義王"], self.t), [])


class MarkSynced(Base):
    """D-518：validate 的 allow_stale、mark_synced 換 整理到、更新日、檔案卡、相關實體 四欄。"""

    def test_allow_stale_only_drops_stale(self):
        good = E.synthesis_text(self.header(E.XINYI), "信義王")
        (self.V / XINYI_REL).write_text(good, encoding="utf-8")
        E.write_card(self.V, E.ESTIMATE, "信義王估價", ["信義王"])
        self.assertEqual(synthesis.validate(self.V, XINYI_REL), (False, "整理到不是現行的，重跑 kb cards todo 拿新檔頭"))
        self.assertEqual(synthesis.validate(self.V, XINYI_REL, allow_stale=True), (True, ""))
        (self.V / XINYI_REL).write_text(good.replace("名稱: 信義王", "名稱: 信義"), encoding="utf-8")
        self.assertEqual(synthesis.validate(self.V, XINYI_REL, allow_stale=True),
                         (False, "「名稱」照 kb cards todo 給的檔頭抄"))

    def test_synced_not_a_list_is_its_own_error(self):
        """裁定 6：整理到寫成字串不算只差整理到：hook、--synced 照擋，cards todo 列 broken 不列 stale。"""
        import re
        good = E.synthesis_text(self.header(E.XINYI), "信義王")
        E.write_card(self.V, E.ESTIMATE, "信義王估價", ["信義王"])
        (self.V / XINYI_REL).write_text(re.sub(r"整理到:\n(  - .*\n)*", "整理到: 已整理\n", good), encoding="utf-8")
        want = "整理到 照 kb cards todo 給的檔頭抄（一行一項）"
        self.assertEqual(synthesis.validate(self.V, XINYI_REL, allow_stale=True), (False, want))
        b = self.buckets()
        self.assertEqual([i["entity_id"] for i in b["synthesis_stale"]], [])
        self.assertIn({"path": XINYI_REL, "reason": want}, b["synthesis_broken"])
        self.assertEqual(synthesis.mark_synced(self.V, ["信義王"], self.t), ([], [{"name": "信義王", "reason": want}]))

    def test_mark_synced_four_fields_only(self):
        from datetime import date
        card = self.V / XINYI_REL
        card.write_text(card.read_text(encoding="utf-8").replace("相關實體: []\n", "相關實體: []\n風格: [北歐]\n"),
                        encoding="utf-8", newline="\n")
        before = card.read_text(encoding="utf-8").splitlines()
        E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王", "王宅"])
        written, skipped = synthesis.mark_synced(self.V, ["信義王宅"], self.t)
        self.assertEqual((written, skipped), ([XINYI_REL], []))
        after = card.read_text(encoding="utf-8").splitlines()
        front = cards.parse_front("\n".join(after))
        self.assertEqual((front["更新日"], front["相關實體"], len(front["檔案卡"])), (date.today().isoformat(), ["王宅"], 1))
        self.assertEqual(synthesis.validate(self.V, XINYI_REL), (True, ""))
        keys = ("整理到:", "更新日:", "檔案卡:", "相關實體:", "  - ")
        self.assertEqual([l for l in after if not l.startswith(keys)], [l for l in before if not l.startswith(keys)])
        self.assertEqual({r["path"]: r["by"] for r in turn.entries(self.V, self.t)}[XINYI_REL], "program")
        self.assertEqual(synthesis.mark_synced(self.V, ["信義王"], self.t), ([], []))

    def test_name_and_alias_counted_once(self):
        """裁定 9：同一個實體名稱、別名各給一次只算一筆；寫了算一筆，都 skip 也只列一筆。"""
        E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王"])
        self.assertEqual(synthesis.mark_synced(self.V, ["信義王", "信義王宅"], self.t), ([XINYI_REL], []))
        card = self.V / XINYI_REL
        card.write_text(card.read_text(encoding="utf-8").replace("範本版本: 1", "範本版本: 9"), encoding="utf-8")
        self.assertEqual(synthesis.mark_synced(self.V, ["信義王", "信義王宅"], self.t),
                         ([], [{"name": "信義王", "reason": "範本版本該是 2"}]))

    def test_mark_synced_skips(self):
        card = self.V / XINYI_REL
        card.write_text(card.read_text(encoding="utf-8").replace("範本版本: 1", "範本版本: 9"), encoding="utf-8")
        before = card.read_text(encoding="utf-8")
        self.assertEqual(synthesis.mark_synced(self.V, ["信義王", "王宅", "沒有"], self.t), ([], [
            {"name": "信義王", "reason": "範本版本該是 2"}, {"name": "王宅", "reason": "還沒有綜合卡"},
            {"name": "沒有", "reason": "找不到這個實體"}]))
        self.assertEqual(card.read_text(encoding="utf-8"), before)


class Buckets(Base):
    def test_threshold_one_and_two_and_confirm(self):
        self.update(E.WANG, source="inferred")
        E.write_card(self.V, E.QUOTE, "王宅報價", ["王宅"])
        self.assertEqual(self.buckets()["synthesis_new"], [])
        E.write_card(self.V, E.ESTIMATE, "王宅估價", ["王宅"])
        (item,) = self.buckets()["synthesis_new"]
        self.assertEqual((item["entity_id"], item["name"], item["type"], item["category"], item["confirmed"], item["path"]),
                         (E.WANG, "王宅", "案子", "事", False, "案子/王宅/王宅.md"))
        self.assertEqual(item["question"], "我要幫「王宅」（案子，掛了 2 份檔）整理一頁現況：名字這樣叫對嗎？它跟其他案子是同一件嗎？")
        self.assertEqual(len(item["cards"]), 2)
        self.assertEqual([s["name"] for s in item["sections"]], ["現況", "時程", "金額", "推算", "紀事"])
        self.assertTrue(item["header"].startswith("---\n編號: e-0f3e9a21\n"))
        self.update(E.WANG, source="confirmed")
        (item,) = self.buckets()["synthesis_new"]
        self.assertTrue(item["confirmed"])
        self.assertNotIn("question", item)
        (self.V / ".system" / "config.json").write_text('{"synthesis_min_cards": 3}', encoding="utf-8")
        self.assertEqual(self.buckets()["synthesis_new"], [])

    def test_self_and_type_not_in_table_not_listed(self):
        data = entities.load(self.V)["entities"]
        data.append(E.entity("e-22222222", "順發水電", type_="廠商"))
        E.put_entities(self.V, data)
        for rel, title in ((E.QUOTE, "a"), (E.ESTIMATE, "b"), (E.DRAFT, "c")):
            E.write_card(self.V, rel, title, ["林小姐室內設計", "順發水電"])
        self.assertEqual(self.buckets()["synthesis_new"], [])

    def test_read_ranges_skip_events(self):
        """D-521 驗收 3：read_ranges 是內文去掉 ## 紀事 那段（標題到下一個 ## 之前）。"""
        text = ("---\na: 1\n---\n# 信義王\n\n一句。\n\n## 現況\n- 一點\n\n## 紀事\n- 2026-10-20 甲\n- 2026-10-01 乙\n\n"
                "## 時程\n未知\n")
        lines = text.splitlines()
        got = synthesis.read_ranges(text)
        self.assertEqual(got, [[4, 7], [15, 2]])
        kept = [lines[a - 1 + i] for a, n in got for i in range(n)]
        self.assertFalse([l for l in kept if "紀事" in l or l.startswith("- 2026")])
        self.assertEqual(synthesis.read_ranges(text.split("\n## 時程")[0] + "\n"), [[4, 7]])  # 紀事在最後
        self.assertEqual(synthesis.read_ranges("---\na: 1\n---\n# x\n\n## 現況\n- 一\n"), [[4, 4]])
        self.assertEqual(synthesis.read_ranges("---\na: 1\n---\n"), [])
        self.assertEqual(synthesis.read_ranges("沒有檔頭\n## 紀事\n- x\n"), [[1, 1]])

    FILES = "<!-- willy:檔 開始 -->\n## 相關檔\n\n### 報價\n- [[a.md|甲]]\n<!-- willy:檔 結束 -->\n"

    def test_read_ranges_skip_file_section(self):
        """D-521 裁定 5：程式寫的「相關檔」那段（開始到結束記號）也不讀；紀事緊接在它前面也一樣。"""
        text = "---\na: 1\n---\n# x\n\n## 現況\n- 一\n\n## 紀事\n- 2026-10-20 甲\n\n" + self.FILES
        self.assertEqual(synthesis.read_ranges(text), [[4, 5]])
        text = "---\na: 1\n---\n# x\n\n## 現況\n- 一\n\n" + self.FILES + "\n## 備註\n二\n"
        self.assertEqual(synthesis.read_ranges(text), [[4, 5], [15, 3]])
        self.assertEqual(synthesis.read_ranges("---\na: 1\n---\n# x\n\n<!-- willy:檔 開始 -->\n## 相關檔\n- 沒結束\n"),
                         [[4, 2]])  # 沒有結束記號算到檔尾（同 _span）

    def test_marker_counts_only_as_whole_line(self):
        """裁定 14：行中間的記號字串不算相關檔；render 照樣把真的那段插在紀事前面（D-523），那行與後面的段一字不動。"""
        inline = "- 2026-10-30 備註 " + synthesis.FILE_BEGIN + " x〔f-00000001〕"
        text = "---\na: 1\n---\n# x\n\n## 紀事\n" + inline + "\n- 2026-10-01 甲\n\n## 時程\n未知\n"
        self.assertIsNone(synthesis._span(text))
        got = synthesis.with_file_section(text, self.FILES.rstrip("\n"))
        self.assertEqual(got, text.replace("\n## 紀事\n", "\n" + self.FILES + "\n## 紀事\n"))
        self.assertEqual(synthesis._span(got)[0], got.index("\n" + synthesis.FILE_BEGIN + "\n") + 1)

    def test_marker_line_with_unicode_spaces(self):
        """review：記號行前後是全形空白、不斷行空白也算記號行（同 read_ranges 的 strip），兩邊認的是同一段。"""
        files = self.FILES.replace(synthesis.FILE_BEGIN, "\u3000" + synthesis.FILE_BEGIN + "\xa0")
        text = "---\na: 1\n---\n# x\n\n## 現況\n- 一\n\n" + files
        self.assertEqual(synthesis._span(text)[0], text.index("\u3000"))
        self.assertEqual(synthesis.read_ranges(text), [[4, 5]])

    def test_empty_events_section_gets_blank_line_before_files(self):
        """裁定 20：紀事段只有標題、下一行就是相關檔記號，新條跟記號之間空一行。"""
        text = "---\na: 1\n---\n# x\n\n## 現況\n- 一\n\n## 紀事\n" + self.FILES
        got, _a, _d = synthesis.insert_events(text, [("2026-10-25", "2026-10-25 開會〔f-00000001〕")])
        self.assertEqual(got, text.replace("## 紀事\n", "## 紀事\n- 2026-10-25 開會〔f-00000001〕\n\n"))

    def test_insert_events_keeps_file_section(self):
        """D-521 裁定 5：舊版面紀事在相關檔前面時加的行不進相關檔；D-523：沒有紀事段一律補在全卡最後（相關檔下面）。"""
        new = "- 2026-10-25 開會〔f-00000001〕"
        text = "---\na: 1\n---\n# x\n\n## 現況\n- 一\n\n## 紀事\n- 2026-10-01 甲\n\n" + self.FILES
        got, added, _dup = synthesis.insert_events(text, [("2026-10-25", new[2:])])
        self.assertEqual(added, [new[2:]])
        self.assertEqual(got, text.replace("## 紀事\n", f"## 紀事\n{new}\n"))
        got, _a, _d = synthesis.insert_events(text, [("2026-09-01", "2026-09-01 早〔f-00000001〕")])
        self.assertEqual(got, text.replace("- 2026-10-01 甲\n", "- 2026-10-01 甲\n- 2026-09-01 早〔f-00000001〕\n"))
        for text in ("---\na: 1\n---\n# x\n\n## 現況\n- 一\n\n" + self.FILES,  # 只有現況
                     "---\na: 1\n---\n# x\n\n## 推算\n- 一\n\n" + self.FILES,  # 沒有現況
                     "---\na: 1\n---\n# x\n一句。\n\n" + self.FILES):  # 一段都沒有
            with self.subTest(text=text):
                got, _a, _d = synthesis.insert_events(text, [("2026-10-25", new[2:])])
                self.assertEqual(got, text + f"\n## 紀事\n{new}\n")

    def test_stale_added_changed_removed(self):
        a = E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王"])
        E.write_card(self.V, E.ESTIMATE, "信義王估價", ["信義王"])
        card = self.V / XINYI_REL
        card.write_text(E.synthesis_text(self.header(E.XINYI), "信義王"), encoding="utf-8")
        self.assertEqual(self.buckets()["synthesis_stale"], [])
        E.write_card(self.V, E.DRAFT, "信義王會議", ["信義王"])
        (item,) = self.buckets()["synthesis_stale"]
        self.assertEqual([x["title"] for x in item["added"]], ["信義王會議"])
        self.assertEqual((item["changed"], item["removed"]), ([], []))
        self.assertNotIn("header", item)  # D-520：檔頭程式管，不給
        self.assertNotIn("body_line", item)
        lines = card.read_text(encoding="utf-8").splitlines()
        ((start, n),) = item["read_ranges"]  # 沒有紀事段：一段到檔尾（D-521）
        self.assertEqual((lines[start - 2], start + n - 1), ("---", len(lines)))
        p = self.V / a
        p.write_text(p.read_text(encoding="utf-8").replace("實體: [信義王]", "實體: []"), encoding="utf-8")
        (item,) = self.buckets()["synthesis_stale"]
        self.assertEqual([(x["id"], x["title"]) for x in item["removed"]],
                         [(cards.parse_front(p.read_text(encoding="utf-8"))["編號"], "信義王報價")])
        card.write_text(E.synthesis_text(E.stale_header(self.V, item), "信義王"), encoding="utf-8")
        self.assertEqual(self.buckets()["synthesis_stale"], [])

    def test_stale_changed_when_fingerprint_moves(self):
        a = E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王"])
        (self.V / XINYI_REL).write_text(E.synthesis_text(self.header(E.XINYI), "信義王"), encoding="utf-8")
        p = self.V / a
        front = cards.parse_front(p.read_text(encoding="utf-8"))
        p.write_text(p.read_text(encoding="utf-8").replace(front["指紋"], "a" * 64), encoding="utf-8")
        (item,) = self.buckets()["synthesis_stale"]
        self.assertEqual([x["id"] for x in item["changed"]], [front["編號"]])

    def test_broken_and_misplaced(self):
        card = self.V / XINYI_REL
        card.write_text(card.read_text(encoding="utf-8").replace("範本版本: 1", "範本版本: 9"), encoding="utf-8")
        stray = self.V / "案子" / "王宅" / "王宅.md"
        stray.parent.mkdir()
        stray.write_text((E.FIX / "大安陳.md").read_text(encoding="utf-8"), encoding="utf-8")
        got = self.buckets()["synthesis_broken"]
        self.assertEqual(got, [{"path": XINYI_REL, "reason": "範本版本該是 2"},
                               {"path": "案子/王宅/王宅.md", "reason": "綜合卡該放在 案子/大安陳/大安陳.md"}])

    def test_drift_with_question(self):
        (self.V / "案子" / "信義王").rename(self.V / "案子" / "王宅邸")
        (item,) = self.buckets()["entity_drift"]
        self.assertEqual(item["question"], "「信義王」的資料夾改成「王宅邸」了？要跟著改名，還是改回來？")
        self.assertEqual(self.buckets()["synthesis_broken"], [], "drift 認出的不重複列")
        (self.V / "案子" / "王宅邸" / "信義王.md").rename(self.V / "案子" / "王宅邸" / "王宅邸.md")
        (self.V / "案子" / "王宅邸").rename(self.V / "案子" / "信義王")
        self.assertEqual(self.buckets()["entity_drift"][0]["question"],
                         "「信義王」的綜合卡檔名改成「王宅邸」了？要採新名，還是改回來？")
        shutil.move(str(self.V / "案子" / "信義王"), str(self.V / "業主" / "信義王"))
        self.assertEqual(self.buckets()["entity_drift"][0]["question"],
                         "「信義王」的資料夾搬到「業主」底下了？要跟著改，還是搬回「案子」？")
        shutil.rmtree(self.V / "業主" / "信義王")
        self.assertEqual(self.buckets()["entity_drift"][0]["question"],
                         "「信義王」的資料夾（或綜合卡）不見了：是不要了，還是刪錯了？")

    def test_min_cards_default(self):
        self.assertEqual(config.get(self.V, "synthesis_min_cards"), 2)


class Knowledge(Base):
    """note 改知識第 6 點、驗收 1～4、9、10：依據 = 檔案卡＋有效口述＋有效裁示；整理到收 s-、r- 行（指紋 -）；門檻數口述。"""

    def setUp(self):
        super().setUp()
        from kb._lib import rulings, statements
        self.statements, self.rulings = statements, rulings
        self.card_rel = E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王"])
        self.cid = cards.parse_front((self.V / self.card_rel).read_text(encoding="utf-8"))["編號"]
        self.write_synthesis()

    def write_synthesis(self, header=None):
        (self.V / XINYI_REL).write_text(E.synthesis_text(header or self.header(E.XINYI), "信義王"), encoding="utf-8")
        self.assertEqual(self.buckets()["synthesis_stale"], [])

    def stale(self):
        (item,) = self.buckets()["synthesis_stale"]
        return item

    def test_new_statement_is_added_with_source_and_item_carries_statements(self):
        s, _r = self.statements.add(self.V, "信義王改用系統櫃", ["信義王"], self.t)
        item = self.stale()
        self.assertEqual(item["added"], [{"id": s["id"], "text": "信義王改用系統櫃", "date": s["date"], "source": "statement"}])
        self.assertEqual((item["changed"], item["removed"]), ([], []))
        self.assertEqual(item["statements"], [{"id": s["id"], "text": "信義王改用系統櫃", "date": s["date"]}])
        self.assertEqual(item["rulings"], [])
        front = cards.parse_front(E.stale_header(self.V, item))
        self.assertIn(f"{s['id']} -", front["整理到"])
        self.assertEqual(front["整理到"], sorted(front["整理到"]))

    def test_header_lines_order(self):
        s, _r = self.statements.add(self.V, "信義王改用系統櫃", ["信義王"], self.t)
        r = self.rulings.add(self.V, "口述為準", ["信義王"], [], "信義王的報價以口述為準", turn_id=self.t)
        lines = cards.parse_front(self.header(E.XINYI))["整理到"]
        self.assertEqual([x.split(" ")[0][:2] for x in lines], ["f-", "r-", "s-"])
        self.assertEqual(lines[1:], [f"{r['id']} -", f"{s['id']} -"])

    def test_card_items_carry_source(self):
        E.write_card(self.V, E.ESTIMATE, "信義王估價", ["信義王"])
        (added,) = self.stale()["added"]
        self.assertEqual((added["title"], added["source"]), ("信義王估價", "card"))

    def test_superseded_is_removed_and_new_is_added(self):
        old, _r = self.statements.add(self.V, "王宅的聯絡人是王先生", ["信義王"], self.t)
        self.write_synthesis(E.stale_header(self.V, self.stale()))
        new, _r = self.statements.add(self.V, "聯絡人改成王太太", ["信義王"], self.t, replaces=old["id"])
        item = self.stale()
        self.assertEqual([(x["id"], x["source"]) for x in item["added"]], [(new["id"], "statement")])
        self.assertEqual(item["removed"], [{"id": old["id"], "text": "王宅的聯絡人是王先生", "date": old["date"],
                                            "source": "statement"}])
        self.write_synthesis(E.stale_header(self.V, item))
        self.statements.withdraw(self.V, new["id"], self.t)
        self.assertEqual([x["id"] for x in self.stale()["removed"]], [new["id"]])

    def test_ruling_on_card_makes_its_entity_stale_and_revoke_removes(self):
        r = self.rulings.add(self.V, "不採用", [], [self.cid], "這份報價是舊的，別信", turn_id=self.t)
        item = self.stale()
        self.assertEqual(item["added"], [{"id": r["id"], "kind": "ruled_out", "text": "這份報價是舊的，別信", "source": "ruling"}])
        self.assertEqual(item["rulings"], [{"id": r["id"], "kind": "ruled_out", "text": "這份報價是舊的，別信",
                                            "cards": [{"id": self.cid, "title": "信義王報價"}]}])
        self.write_synthesis(E.stale_header(self.V, item))
        self.rulings.remove(self.V, r["id"], self.t)
        self.assertEqual([(x["id"], x["source"]) for x in self.stale()["removed"]], [(r["id"], "ruling")])

    def test_ruling_recheck_does_not_make_it_stale(self):
        r = self.rulings.add(self.V, "不採用", [], [self.cid], "別信", turn_id=self.t)
        self.write_synthesis(E.stale_header(self.V, self.stale()))
        self.rulings.recheck(self.V, r["id"], self.t)
        self.assertEqual(self.buckets()["synthesis_stale"], [])

    def test_validate_with_statement_lines(self):
        self.statements.add(self.V, "信義王改用系統櫃", ["信義王"], self.t)
        header = self.header(E.XINYI)
        (self.V / XINYI_REL).write_text(E.synthesis_text(header, "信義王"), encoding="utf-8")
        self.assertEqual(synthesis.validate(self.V, XINYI_REL), (True, ""))
        stripped = "\n".join(ln for ln in header.splitlines() if not ln.startswith("  - s-")) + "\n"
        (self.V / XINYI_REL).write_text(E.synthesis_text(stripped, "信義王"), encoding="utf-8")
        self.assertEqual(synthesis.validate(self.V, XINYI_REL), (False, "整理到不是現行的，重跑 kb cards todo 拿新檔頭"))

    def test_threshold_counts_statements_but_not_rulings_or_self(self):
        self.update(E.WANG, source="confirmed")
        E.write_card(self.V, E.ESTIMATE, "王宅估價", ["王宅"])
        self.assertEqual(self.buckets()["synthesis_new"], [])
        self.rulings.add(self.V, "口述為準", ["王宅"], [], "王宅以口述為準", turn_id=self.t)
        self.assertEqual(self.buckets()["synthesis_new"], [])
        s, _r = self.statements.add(self.V, "王宅改成兩房", ["王宅"], self.t)
        (item,) = self.buckets()["synthesis_new"]
        self.assertEqual(item["name"], "王宅")
        self.assertEqual([x["id"] for x in item["statements"]], [s["id"]])
        self.assertEqual(len(item["rulings"]), 1)
        self.assertIn(f"  - {s['id']} -\n", item["header"])
        self.statements.add(self.V, "公司下個月搬家", ["林小姐室內設計"], self.t)
        self.statements.add(self.V, "公司要換電話", ["林小姐室內設計"], self.t)
        self.assertEqual([i["name"] for i in self.buckets()["synthesis_new"]], ["王宅"])


class FileSection(Base):
    """放寬丙 7（驗收 19、20）：綜合卡最後一段「相關檔」是程式寫的快取。"""

    def card(self, rel=XINYI_REL):
        return (self.V / rel).read_text(encoding="utf-8")

    def by_id(self):
        from kb._lib import inventory
        return {e["id"]: e for e in inventory.load(self.V)["entries"]}

    def mention(self, rel, name):
        p = self.V / rel
        p.write_text(p.read_text(encoding="utf-8").replace("提到: []", f"提到: [{name}]"), encoding="utf-8", newline="\n")

    def test_main_and_mention_sections(self):
        main = E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王"], date="2026-10-01")
        other = E.write_card(self.V, E.ESTIMATE, "信義王估價", ["信義王"], date="2026-09-12")
        self.mention(other, "大安陳")
        self.assertEqual(cards.validate(self.V, other, self.by_id()), (True, ""))
        synthesis.render_cache(self.V, None, self.t)
        text = self.card()
        self.assertIn(synthesis.FILE_BEGIN + "\n## 相關檔\n", text)
        self.assertIn(synthesis.FILE_END + "\n\n## 紀事\n", text)  # D-523：插在紀事前面
        self.assertIn(f"[[{main}|信義王報價]]（2026-10-01）", text)
        self.assertIn(f"[[{other}|信義王估價]]（2026-09-12）", text)
        self.assertNotIn("[!note]- 其他", text)
        daan = self.card("案子/大安陳/大安陳.md")
        self.assertIn("> [!note]- 其他\n> - [[" + other + "|信義王估價]]", daan)
        self.assertNotIn("### ", daan)
        self.assertEqual(synthesis.render_cache(self.V, None, self.t), [])  # 穩定：第二次不寫

    def test_old_version_folded(self):
        old = E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王"], date="2026-08-01")
        new = E.write_card(self.V, E.ESTIMATE, "信義王報價", ["信義王"], date="2026-10-01")
        synthesis.render_cache(self.V, ["信義王"], self.t)
        text = self.card()
        self.assertLess(text.index(new), text.index("> [!note]- 舊版"))
        self.assertGreater(text.index(old), text.index("> [!note]- 舊版"))

    def test_v2_card_counts_as_main(self):
        rel = E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王"])
        p = self.V / rel
        p.write_text(p.read_text(encoding="utf-8").replace("提到: []\n", "").replace("範本版本: 3", "範本版本: 2"),
                     encoding="utf-8", newline="\n")
        self.assertEqual(cards.validate(self.V, rel, self.by_id()), (True, ""))
        synthesis.render_cache(self.V, ["信義王"], self.t)
        self.assertIn(f"[[{rel}|信義王報價]]", self.card())

    def test_ai_edit_without_section_passes_and_handedit_kept(self):
        E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王"])
        synthesis.render_cache(self.V, ["信義王"], self.t)
        text = self.card()
        i, j = synthesis._span(text)
        self.assertIn("整理到", synthesis.validate(self.V, XINYI_REL)[1])  # 只差整理到（AI 的事），這段本身不挑
        (self.V / XINYI_REL).write_text(text[:i].rstrip() + "\n\n" + text[j:].lstrip(), encoding="utf-8",
                                        newline="\n")  # AI 把段拿掉再寫
        self.assertIn("整理到", synthesis.validate(self.V, XINYI_REL)[1])
        synthesis.render_cache(self.V, ["信義王"], self.t)
        self.assertEqual(self.card(), text)
        (self.V / XINYI_REL).write_text(text.replace("## 相關檔", "## 相關檔\n她寫的一行"), encoding="utf-8", newline="\n")
        t2 = turn.start(self.V, None, "")["turn"]
        self.assertEqual(synthesis.render_cache(self.V, ["信義王"], t2), [XINYI_REL])
        self.assertEqual(self.card(), text)
        from kb._lib import renders
        (saved,) = renders.saved(self.V)
        self.assertEqual(saved["file"], XINYI_REL)
        self.assertIn("她寫的一行", (self.V / saved["saved"]).read_text(encoding="utf-8"))

    def test_no_files_no_section(self):
        synthesis.render_cache(self.V, ["信義王"], self.t)
        self.assertNotIn(synthesis.FILE_BEGIN, self.card())


def heads(text):
    """內文的段標題與相關檔記號，照出現的順序。"""
    return [l for l in text.split("\n") if l.startswith("## ") or l == synthesis.FILE_BEGIN]


def segments(text):
    """{段標題或相關檔: 那段的字（去頭尾空行）}：遷移前後照段比對用。"""
    out, cur, buf = {}, None, []
    lines = text.split("\n")
    i = next(n for n in range(1, len(lines)) if lines[n] == "---") + 1
    for l in lines[i:]:
        if l.startswith("## ") or l == synthesis.FILE_BEGIN:
            if cur:
                out[cur] = "\n".join(buf).strip("\n")
            cur, buf = l, []
        if cur:
            buf.append(l)
        if l == synthesis.FILE_END:
            out[cur], cur, buf = "\n".join(buf).strip("\n"), None, []
    if cur:
        out[cur] = "\n".join(buf).strip("\n")
    return out


class Layout(Base):
    """D-523：現況 → 第四節的段 → 推算 → 相關檔 → 紀事；舊版（範本版本 1）照舊算有效、由遷移搬。"""
    FILES = synthesis.FILE_BEGIN + "\n## 相關檔\n\n### 報價\n- [[a.md|甲]]\n" + synthesis.FILE_END
    HEAD = "---\n編號: e-5c1d0a7e\n名稱: 信義王\n範本版本: 1\n整理到:\n  - f-00000001 aaaaaaaaaaaa\n---\n# 信義王\n\n一句。\n\n"
    NOW = "## 現況\n- 一點〔f-00000001〕\n"
    EVENTS = "## 紀事\n- 2026-10-20 甲〔f-00000001〕\n- 2026-10-01 乙〔f-00000001〕\n"
    GUESS = "## 推算\n- 差 3 萬〔f-00000001〕（算於 2026-10-20）\n"
    CUSTOM = "## 時程\n- 開始 2026-09-12〔f-00000001〕\n\n## 金額\n未知\n"

    def old(self, *parts):
        return self.HEAD + "\n".join(parts) + "\n"

    def test_template_version_and_old_still_valid(self):
        self.assertEqual(synthesis.TEMPLATE_VERSION, "2")
        good = E.synthesis_text(self.header(E.XINYI), "信義王")
        self.assertIn("範本版本: 2\n", good)
        p = self.V / XINYI_REL
        p.write_text(good.replace("範本版本: 2", "範本版本: 1"), encoding="utf-8", newline="\n")
        self.assertEqual(synthesis.validate(self.V, XINYI_REL), (True, ""), "遷移前的舊版照舊算有效")

    def test_template_file_order(self):
        from tests._guard_fixture import ROOT
        text = (ROOT / "templates" / "synthesis.md").read_text(encoding="utf-8")
        self.assertIn("範本版本: 2\n", text)
        self.assertEqual(heads(text), ["## 現況", "## 時程", "## 金額", "## 推算", "## 紀事"])

    def test_render_cache_puts_files_above_events(self):
        """驗收 2：新版面的卡補相關檔時插在紀事前面；紀事不在最後的舊版照舊接在最後。"""
        E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王"])
        p = self.V / XINYI_REL
        p.write_text(E.synthesis_text(self.header(E.XINYI), "信義王", "一句。\n\n" + self.NOW + "\n" + self.CUSTOM + "\n"
                                      + self.GUESS + "\n" + self.EVENTS), encoding="utf-8", newline="\n")
        synthesis.render_cache(self.V, ["信義王"], self.t)
        self.assertEqual(heads(p.read_text(encoding="utf-8")),
                         ["## 現況", "## 時程", "## 金額", "## 推算", synthesis.FILE_BEGIN, "## 相關檔", "## 紀事"])
        self.assertTrue(p.read_text(encoding="utf-8").endswith(self.EVENTS))
        self.assertEqual(synthesis.render_cache(self.V, ["信義王"], self.t), [])  # 穩定
        old = self.old(self.NOW, self.EVENTS, self.CUSTOM)  # review：紀事不在最後也插在紀事前面（spec 第 2 點）
        self.assertEqual(heads(synthesis.with_file_section(old, self.FILES)),
                         ["## 現況", synthesis.FILE_BEGIN, "## 相關檔", "## 紀事", "## 時程", "## 金額"])
        self.assertEqual(heads(synthesis.with_file_section(self.old(self.NOW), self.FILES)),
                         ["## 現況", synthesis.FILE_BEGIN, "## 相關檔"], "沒有紀事段才接在最後")

    def test_read_ranges_one_part_and_log_goes_last(self):
        """驗收 3：新版面 read_ranges 是一段（不含相關檔、紀事）；沒有紀事段就補在最後。"""
        text = self.old(self.NOW, self.CUSTOM, self.GUESS, self.FILES + "\n", self.EVENTS)
        (got,) = synthesis.read_ranges(text)
        lines = text.split("\n")
        kept = lines[got[0] - 1:got[0] - 1 + got[1]]
        self.assertEqual(kept[0], "# 信義王")
        self.assertFalse([l for l in kept if l.startswith("- 2026") or "相關檔" in l or l == synthesis.FILE_BEGIN])
        new, added, _dup = synthesis.insert_events(text, [("2026-10-25", "2026-10-25 開會〔f-00000001〕")])
        self.assertTrue(new.rstrip("\n").endswith("## 紀事\n- 2026-10-25 開會〔f-00000001〕\n- 2026-10-20 甲〔f-00000001〕\n"
                                                  "- 2026-10-01 乙〔f-00000001〕"))
        bare = self.old(self.NOW, self.CUSTOM, self.FILES)
        new, _a, _d = synthesis.insert_events(bare, [("2026-10-25", "2026-10-25 開會〔f-00000001〕")])
        self.assertEqual(new, bare + "\n## 紀事\n- 2026-10-25 開會〔f-00000001〕\n")

    def migrate(self, text):
        new = synthesis.migrate_layout(text)
        self.assertIn("範本版本: 2\n", new)
        self.assertEqual(new.replace("範本版本: 2\n", "範本版本: 1\n").split("---\n# ")[0], text.split("---\n# ")[0],
                         "檔頭只改範本版本")
        self.assertEqual(segments(new), segments(text), "每段內容一字不差")
        self.assertEqual(synthesis.migrate_layout(new), new, "跑第二次不變")
        return heads(new)

    def test_migrate_layout_cases(self):
        """驗收 4：四種舊版卡遷移後是 現況、自訂段、推算、相關檔、紀事。"""
        F = [synthesis.FILE_BEGIN, "## 相關檔"]
        cases = [
            ("全部", (self.NOW, self.EVENTS, self.GUESS, self.CUSTOM, self.FILES), ["## 現況", "## 時程", "## 金額", "## 推算"] + F + ["## 紀事"]),
            ("沒有相關檔", (self.NOW, self.EVENTS, self.GUESS, self.CUSTOM), ["## 現況", "## 時程", "## 金額", "## 推算", "## 紀事"]),
            ("沒有推算", (self.NOW, self.EVENTS, self.CUSTOM, self.FILES), ["## 現況", "## 時程", "## 金額"] + F + ["## 紀事"]),
            ("沒有紀事", (self.NOW, self.GUESS, self.CUSTOM, self.FILES), ["## 現況", "## 時程", "## 金額", "## 推算"] + F),
            ("她自己加的段留原位", (self.NOW, "## 備忘\n她寫的\n", self.EVENTS, self.GUESS, self.CUSTOM),
             ["## 現況", "## 備忘", "## 時程", "## 金額", "## 推算", "## 紀事"]),
        ]
        for name, parts, want in cases:
            with self.subTest(name):
                self.assertEqual(self.migrate(self.old(*parts)), want)

    def test_migrate_layout_crlf_and_bom(self):
        text = "﻿" + self.old(self.NOW, self.EVENTS, self.GUESS, self.CUSTOM, self.FILES).replace("\n", "\r\n")
        new = synthesis.migrate_layout(text)
        self.assertTrue(new.startswith("﻿---\r\n"))
        self.assertNotIn("\n", new.replace("\r\n", ""))
        self.assertEqual(heads(new.replace("\r\n", "\n").lstrip("﻿"))[-1], "## 紀事")

    def test_migrate_layout_refuses_unreadable(self):
        for bad in ("沒有檔頭\n## 紀事\n", "---\n名稱: x\n---\n# x\n"):  # 沒檔頭、檔頭沒有範本版本
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                synthesis.migrate_layout(bad)

    def test_migrate_layout_refuses_unclosed_files(self):
        """review：相關檔少了結束記號（算到檔尾）不遷，免得紀事排進那段、下次 render 被換掉。"""
        with self.assertRaises(ValueError):
            synthesis.migrate_layout(self.old(self.NOW, self.EVENTS, synthesis.FILE_BEGIN + "\n## 相關檔\n- x\n"))

    def test_unclosed_files_stop_at_events(self):
        """review：相關檔沒結束記號時算到「## 紀事」之前（沒有紀事才到檔尾）：紀事照樣補在最後，render 換那段不會刪掉紀事。"""
        files = synthesis.FILE_BEGIN + "\n## 相關檔\n- x\n"
        new, _a, _d = synthesis.insert_events(self.old(self.NOW, files), [("2026-10-25", "2026-10-25 開會〔f-00000001〕")])
        self.assertEqual(new, self.old(self.NOW, files, "## 紀事\n- 2026-10-25 開會〔f-00000001〕"))
        span = synthesis._span(new)
        self.assertEqual(new[span[1]:].lstrip("\n")[:5], "## 紀事")
        got = synthesis.with_file_section(new, self.FILES)
        self.assertTrue(got.endswith("## 紀事\n- 2026-10-25 開會〔f-00000001〕\n"))
        self.assertIn(self.FILES, got)
        lines = new.split("\n")
        self.assertEqual(synthesis._file_lines(lines)[1], lines.index("## 紀事"))

    def test_events_heading_with_unicode_space(self):
        """review：「## 紀事」後面接全形空白也認得（同 _events_span 的 rstrip），相關檔插在它前面。"""
        text = self.old(self.NOW, "## 紀事\u3000\n- 2026-10-20 甲〔f-00000001〕\n")
        got = synthesis.with_file_section(text, self.FILES)
        self.assertLess(got.index(synthesis.FILE_BEGIN), got.index("## 紀事"))

    def test_migrate_layout_crlf_without_final_newline(self):
        """review：全 CRLF、檔尾沒換行、最後一行被搬到中間：每行都還是 CRLF，跑第二次不變。"""
        text = self.old(self.NOW, self.EVENTS, self.FILES).replace("\n", "\r\n").rstrip("\r\n")
        new = synthesis.migrate_layout(text)
        self.assertNotIn("\n", new.replace("\r\n", ""))
        self.assertEqual(synthesis.migrate_layout(new), new)

    def test_migrate_layout_mixed_eol_keeps_file_bytes(self):
        """review：CRLF 卡、相關檔是 LF（混用）：每行照原本的換行，相關檔那段一個位元組都不變。"""
        crlf = self.old(self.NOW, self.EVENTS, self.GUESS).replace("\n", "\r\n")
        text = crlf + "\n" + self.FILES + "\n"
        new = synthesis.migrate_layout(text)
        self.assertIn("\n" + self.FILES + "\n", new)
        self.assertIn("## 現況\r\n- 一點〔f-00000001〕\r\n", new)
        self.assertIn("範本版本: 2\r\n", new)
        self.assertEqual(heads(new.replace("\r\n", "\n"))[-1], "## 紀事")
        self.assertEqual(synthesis.migrate_layout(new), new)

    def test_migrate_layout_text_after_files_stays_with_it(self):
        """review：相關檔結束記號後面她打的字跟著那段，不被搬到別段底下。"""
        new = synthesis.migrate_layout(self.old(self.NOW, self.EVENTS, self.GUESS, self.FILES + "\n\n她打的字\n"))
        self.assertLess(new.index(synthesis.FILE_END), new.index("她打的字"))
        self.assertLess(new.index("她打的字"), new.index("## 紀事"))
        self.assertLess(new.index("## 推算"), new.index(synthesis.FILE_BEGIN))


if __name__ == "__main__":
    unittest.main()
