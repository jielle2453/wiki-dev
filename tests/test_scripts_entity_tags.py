"""標籤字典第四節（D-235；驗收 9、10）黑箱：kb entity list --tag 不同欄且、同欄或，第一句照實說幾個符合、幾個還沒標過；
欄或詞不在字典、寫法不對拒絕一字不差；--json 照格式；kb lookup 多一行標籤、沒有標籤的不印。"""
import json
import re
import shutil
import unittest

from tests import _entities as E
from tests import _tags as T
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import entities, turn  # noqa: E402

LI, ZHANG, LIN = "e-aaaa0001", "e-aaaa0002", "e-aaaa0003"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        turn.start(self.V, None, "")
        data = [dict(e, status="removed") if e["id"] == E.WANG else e for e in entities.load(self.V)["entities"]]
        data += [E.entity(LI, "內湖李", card=True), E.entity(ZHANG, "士林張"), E.entity(LIN, "北投林", card=True)]
        E.put_entities(self.V, data)
        T.set_tags(self.V)
        T.write_synthesis(self.V, E.XINYI, "信義王", T.XINYI_REL, ["工種: [水電, 木作]", "階段: 施工"])
        T.write_synthesis(self.V, LI, "內湖李", "案子/內湖李/內湖李.md", ["工種: [水電]", "階段: 施工"])
        T.write_synthesis(self.V, E.DAAN, "大安陳", T.DAAN_REL, ["工種: [木作]", "階段: 報價"])
        T.write_synthesis(self.V, LIN, "北投林", "案子/北投林/北投林.md", [])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kb(self, *args):
        return run_kb(*args, cwd=self.V)

    @staticmethod
    def names(lines):
        return [re.match(r"- (\S+?)（", x).group(1) for x in lines if x.startswith("- ")]


class TagFilter(Base):
    def test_and_across_fields(self):
        r = self.kb("entity", "list", "--tag", "工種=水電", "--tag", "階段=施工")
        lines = r.stdout.splitlines()
        self.assertEqual((r.returncode, lines[0]), (0, "案子 5 個中 2 個符合；另有 2 個還沒照字典標過"))
        self.assertEqual(self.names(lines), ["信義王", "內湖李"])
        self.assertIn("有綜合卡", lines[1])

    def test_or_within_field(self):
        for arg in ("工種=木作,磁磚", "工種=木作、磁磚"):
            with self.subTest(arg=arg):
                lines = self.kb("entity", "list", "--tag", arg).stdout.splitlines()
                self.assertEqual(lines[0], "案子 5 個中 2 個符合；另有 2 個還沒照字典標過")
                self.assertEqual(self.names(lines), ["信義王", "大安陳"])

    def test_untagged_half_hidden_when_zero(self):
        for rel in ("案子/北投林/北投林.md",):
            T.write_synthesis(self.V, LIN, "北投林", rel, ["工種: []", "階段: []"])
        data = [dict(e, status="removed") if e["id"] == ZHANG else e for e in entities.load(self.V)["entities"]]
        E.put_entities(self.V, data)
        lines = self.kb("entity", "list", "--tag", "工種=系統櫃").stdout.splitlines()
        self.assertEqual(lines, ["案子 4 個中 0 個符合"])

    def test_json(self):
        r = self.kb("entity", "list", "--tag", "工種=水電", "--tag", "階段=施工", "--json")
        got = json.loads(r.stdout)
        self.assertEqual(got["counts"], [{"type": "案子", "total": 5, "matched": 2, "untagged": 2}])
        self.assertEqual(got["tag"], [{"field": "工種", "words": ["水電"]}, {"field": "階段", "words": ["施工"]}])
        self.assertEqual([e["name"] for e in got["entities"]], ["信義王", "內湖李"])
        self.assertTrue(all("mounted" in e and "has_card" in e for e in got["entities"]))

    def test_refusals(self):
        cases = [
            (("--tag", "預算=高"), "第八節沒有「預算」這個標籤欄；有：工種、階段"),
            (("--tag", "工種=油漆"), "「工種」的字典沒有「油漆」；有：水電、木作、磁磚、系統櫃"),
            (("--tag", "工種"), "--tag 要寫成 欄=詞（多個詞用逗號分開）"),
            (("--tag", "=水電"), "--tag 要寫成 欄=詞（多個詞用逗號分開）"),
            (("--tag", "工種="), "--tag 要寫成 欄=詞（多個詞用逗號分開）"),
        ]
        for args, want in cases:
            with self.subTest(args=args):
                r = self.kb("entity", "list", *args)
                self.assertEqual((r.returncode, r.stdout.strip()), (3, want))

    def test_without_tag_unchanged(self):
        lines = self.kb("entity", "list").stdout.splitlines()
        self.assertFalse(any("符合" in x for x in lines))
        self.assertEqual(len([x for x in lines if x.startswith("- ")]), 6)


class Lookup(Base):
    def test_lookup_tag_line(self):
        lines = self.kb("lookup", "信義王").stdout.splitlines()
        self.assertIn("標籤：工種 水電、木作；階段 施工", lines)
        got = json.loads(self.kb("lookup", "信義王", "--json").stdout)
        self.assertEqual(got["tags"], [{"field": "工種", "words": ["水電", "木作"]}, {"field": "階段", "words": ["施工"]}])

    def test_no_tags_no_line(self):
        lines = self.kb("lookup", "北投林").stdout.splitlines()
        self.assertFalse(any(x.startswith("標籤：") for x in lines))
        self.assertEqual(json.loads(self.kb("lookup", "北投林", "--json").stdout)["tags"], [])


if __name__ == "__main__":
    unittest.main()
