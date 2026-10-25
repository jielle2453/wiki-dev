"""lint 第三類（驗收 12）：被取代或收回、沒有綜合卡引用的口述與推算移到封存檔；有引用的不動；lookup 不受影響。"""
import shutil
import unittest

from tests import _entities as E
from tests import _lint as L
from kb._lib import cards, findings, lookup, statements, turn  # noqa: E402
from kb.lint.checks import archive  # noqa: E402


class Archive(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()
        self.t = turn.start(self.V, None, "")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_unreferenced_moved_referenced_kept(self):
        a = statements.add(self.V, "信義王改用系統櫃", ["信義王"], self.t)[0]["id"]
        b = statements.add(self.V, "信義王改回木工", ["信義王"], self.t, replaces=a)[0]["id"]
        c = statements.add(self.V, "大安陳延後交屋", ["大安陳"], self.t)[0]["id"]
        statements.withdraw(self.V, c, self.t)
        L.write_synthesis(self.V, body=f"## 現況\n- 木工〔{b}〕\n\n## 紀事\n- 10-20 收回〔{c}〕\n")
        before = lookup.lookup(self.V, "信義王")["statements"]
        (fix,) = archive.run(L.ctx(self.V))
        self.assertEqual(fix["data"]["statements"], [a])
        self.assertEqual(fix["apply"](L.ctx(self.V)), "收起 1 條被取代或收回的口述")
        ids = {s["id"] for s in statements.load(self.V)["statements"]}
        self.assertEqual(ids, {b, c})
        self.assertEqual([s["id"] for s in statements.load_archive(self.V)["statements"]], [a])
        self.assertEqual(lookup.lookup(self.V, "信義王")["statements"], before)

    def test_findings_too(self):
        q = cards.parse_front((self.V / E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王"])).read_text(
            encoding="utf-8"))["編號"]
        old = findings.add(self.V, "合計 182 萬", "相加", ["信義王"], [q], self.t)[0]["id"]
        findings.add(self.V, "合計 183 萬", "相加", ["信義王"], [q], self.t, replaces=old)
        (fix,) = archive.run(L.ctx(self.V))
        self.assertEqual(fix["data"]["findings"], [old])

    def test_nothing(self):
        statements.add(self.V, "信義王改用系統櫃", ["信義王"], self.t)
        self.assertEqual(archive.run(L.ctx(self.V)), [])


if __name__ == "__main__":
    unittest.main()
