"""標籤字典第三節（D-234、D-238）：綜合卡檔頭的標籤行——驗證（字典外的欄、詞、單選兩個詞、空清單、設定檔讀不到）、
重寫不洗掉（stale 的 header 帶卡上現有的、第八節拿掉的欄不帶、新卡列出欄留空）、retag 只動那一行。"""
import shutil
import unittest
from pathlib import Path

from tests import _entities as E
from tests import _tags as T
from kb._lib import cards, entities, synthesis, turn  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        self.t = turn.start(self.V, None, "")["turn"]
        T.set_tags(self.V)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def buckets(self):
        data = entities.load(self.V)
        return synthesis.buckets(self.V, data, entities.mounts(self.V, data), entities._profile(self.V))


class Validate(Base):
    def check(self, lines):
        T.write_synthesis(self.V, E.XINYI, "信義王", T.XINYI_REL, lines)
        return synthesis.validate(self.V, T.XINYI_REL)

    def test_ok_cases(self):
        for lines in ([], ["工種: [水電, 木作]", "階段: 施工"], ["工種: []", "階段: []"], ["工種:"], ["階段: [完工]"],
                      ["工種: [水電]"]):
            with self.subTest(lines=lines):
                self.assertEqual(self.check(lines), (True, ""))

    def test_field_not_in_dictionary(self):
        self.assertEqual(self.check(["預算: [高]"]), (False, "檔頭的「預算」不是這類卡的標籤欄（第八節沒有）"))

    def test_field_of_other_type_is_not_allowed(self):
        T.set_tags(self.V, T.DEFAULT_TAGS + (T.tag("業主", "在意", ["醫療"]),))
        self.assertEqual(self.check(["在意: [醫療]"]), (False, "檔頭的「在意」不是這類卡的標籤欄（第八節沒有）"))

    def test_word_not_in_dictionary(self):
        ok, reason = self.check(["工種: [水電, 油漆]"])
        self.assertFalse(ok)
        self.assertEqual(reason, "「油漆」不在「工種」的字典裡：先問客戶要不要加（kb profile add 標籤 型別=案子 欄名=工種 詞=油漆），"
                                 "不要自己加")
        self.assertIn("先問客戶要不要加", self.check(["階段: 驗收"])[1])

    def test_single_with_two_words(self):
        self.assertEqual(self.check(["階段: [報價, 施工]"]), (False, "「階段」只能選一個詞"))

    def test_words_compare_by_key(self):
        T.set_tags(self.V, (T.tag("案子", "工種", ["ABC"]),))
        self.assertEqual(self.check(["工種: [abc]"]), (True, ""))

    def test_profile_unreadable_skips_tag_lines(self):
        """entities._profile 讀不到時給預設值（第八節空的）：驗標籤行前再讀一次，讀不到就不驗、寫 log。"""
        good = T.write_synthesis(self.V, E.XINYI, "信義王", T.XINYI_REL, ["預算: [高]"])
        prof = dict(entities._profile(self.V), tags=[])
        (self.V / ".system" / "profile.json").write_text("不是 json", encoding="utf-8")
        self.assertEqual(synthesis.validate(self.V, T.XINYI_REL, prof=prof), (True, ""))
        log = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8")
        self.assertIn("設定檔讀不到，綜合卡的標籤行沒有驗", log)
        (self.V / T.XINYI_REL).write_text(good.replace("範本版本: 1", "範本版本: 2"), encoding="utf-8")
        self.assertEqual(synthesis.validate(self.V, T.XINYI_REL, prof=prof), (False, "範本版本該是 1"), "其他照驗")


class Header(Base):
    def test_new_header_lists_fields_blank(self):
        (self.V / T.XINYI_REL).unlink()
        front_lines = T.header(self.V, E.XINYI).splitlines()
        self.assertEqual(front_lines[-3:], ["工種:", "階段:", "---"])
        self.assertEqual(cards.parse_front(T.header(self.V, E.XINYI))["工種"], [])

    def test_stale_header_keeps_tags_and_drops_removed_field(self):
        T.write_synthesis(self.V, E.XINYI, "信義王", T.XINYI_REL, ["階段: 施工", "工種: [水電]"])
        E.write_card(self.V, E.ESTIMATE, "信義王估價", ["信義王"])
        (item,) = self.buckets()["synthesis_stale"]
        self.assertEqual(item["header"].splitlines()[-3:], ["工種: [水電]", "階段: 施工", "---"], "照第八節的順序")
        T.set_tags(self.V, (T.DEFAULT_TAGS[1],))
        self.assertEqual([b["path"] for b in self.buckets()["synthesis_broken"]], [T.XINYI_REL])
        data = entities.load(self.V)
        found = synthesis.problems(self.V, T.XINYI_REL, (self.V / T.XINYI_REL).read_text(encoding="utf-8"), data,
                                   entities.mounts(self.V, data), entities._profile(self.V))
        self.assertIn(("tag", "檔頭的「工種」不是這類卡的標籤欄（第八節沒有）"), found)
        self.assertEqual(T.header(self.V, E.XINYI).splitlines()[-2:], ["階段: 施工", "---"], "壞卡的 header 也不帶拿掉的欄")

    def test_invalid_words_blanked_in_header(self):
        """壞卡（詞不在字典、單選寫兩個）的 header 不把錯的詞帶回去：那一欄留空給製卡者重標，對的照留。"""
        T.write_synthesis(self.V, E.XINYI, "信義王", T.XINYI_REL, ["工種: [水電, 油漆]", "階段: [報價, 施工]"])
        self.assertEqual(T.header(self.V, E.XINYI).splitlines()[-3:], ["工種:", "階段:", "---"])
        T.write_synthesis(self.V, E.XINYI, "信義王", T.XINYI_REL, ["工種: [水電]", "階段: 驗收"])
        self.assertEqual(T.header(self.V, E.XINYI).splitlines()[-3:], ["工種: [水電]", "階段:", "---"])

    def test_card_without_tag_lines_gets_none_in_stale_header(self):
        T.write_synthesis(self.V, E.XINYI, "信義王", T.XINYI_REL, [])
        E.write_card(self.V, E.ESTIMATE, "信義王估價", ["信義王"])
        (item,) = self.buckets()["synthesis_stale"]
        self.assertEqual(item["header"].splitlines()[-2:], ["相關實體: []", "---"], "沒標過的不替它加空行")

    def test_synthesis_new_header(self):
        (self.V / T.XINYI_REL).unlink()
        data = entities.load(self.V)["entities"]
        for e in data:
            if e["id"] == E.XINYI:
                e["card"] = False
        E.put_entities(self.V, data)
        E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王"])
        E.write_card(self.V, E.ESTIMATE, "信義王估價", ["信義王"])
        item = next(i for i in self.buckets()["synthesis_new"] if i["entity_id"] == E.XINYI)
        self.assertEqual(item["header"].splitlines()[-3:], ["工種:", "階段:", "---"])


class Retag(unittest.TestCase):
    TEXT = ("---\n編號: e-1\n相關實體: [王宅]\n工種: [水電, 木作]\n階段: 施工\n---\n# 王宅\n\n工種: [水電] 不是檔頭\n")

    def test_replace_list(self):
        got = synthesis.retag(self.TEXT, "工種", lambda v: ["磁磚" if w == "水電" else w for w in v])
        self.assertEqual(got, self.TEXT.replace("工種: [水電, 木作]\n", "工種: [磁磚, 木作]\n"))

    def test_dedupe_and_empty_and_single(self):
        got = synthesis.retag(self.TEXT, "工種", lambda v: ["木作" if w == "水電" else w for w in v])
        self.assertIn("\n工種: [木作]\n", got)
        got = synthesis.retag(self.TEXT, "工種", lambda v: [])
        self.assertIn("\n工種: []\n", got)
        got = synthesis.retag(self.TEXT, "階段", lambda v: [])
        self.assertIn("\n階段: []\n", got)
        got = synthesis.retag(self.TEXT, "階段", lambda v: "完工")
        self.assertIn("\n階段: 完工\n", got)

    def test_rename_key_and_drop_line(self):
        got = synthesis.retag(self.TEXT, "工種", lambda v: v, new_field="做什麼")
        self.assertEqual(got, self.TEXT.replace("\n工種: [水電, 木作]\n", "\n做什麼: [水電, 木作]\n"))
        got = synthesis.retag(self.TEXT, "工種", lambda v: synthesis.DROP)
        self.assertEqual(got, self.TEXT.replace("工種: [水電, 木作]\n", ""))
        self.assertTrue(got.endswith("工種: [水電] 不是檔頭\n"), "內文不動")

    def test_absent_line_unchanged(self):
        self.assertEqual(synthesis.retag(self.TEXT, "預算", lambda v: ["x"]), self.TEXT)

    def test_crlf_kept(self):
        text = self.TEXT.replace("\n", "\r\n")
        got = synthesis.retag(text, "階段", lambda v: "完工")
        self.assertEqual(got, text.replace("階段: 施工\r\n", "階段: 完工\r\n"))


if __name__ == "__main__":
    unittest.main()
