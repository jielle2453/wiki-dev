"""lint 第三類（驗收 11）：同種類、掛的卡同卡型的有效裁示到 ruling_promote_min 條 → 待處理一件（擬一條偏好）；少一條不列。"""
import shutil
import unittest

from tests import _entities as E
from tests import _lint as L
from kb._lib import rulings, turn  # noqa: E402
from kb.lint.checks import rulings_promote  # noqa: E402

FILES = (E.QUOTE, E.ESTIMATE, E.DRAFT, E.TEMPLATE, E.MEMO)


class Promote(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()
        self.t = turn.start(self.V, None, "")["turn"]
        self.ids = []
        for n, rel in enumerate(FILES):
            self.ids.append(L.write_card(self.V, rel, f"報價{n}"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def rule(self, n):
        for cid in self.ids[:n]:
            rulings.add(self.V, "口述為準", [], [cid], "報價以我說的為準", self.t)

    def test_five_promote(self):
        self.rule(5)
        (dec,) = rulings_promote.run(L.ctx(self.V))
        self.assertEqual((dec["kind"], dec["key"]), ("decide", "promote:spoken_wins:報價"))
        self.assertEqual(len(dec["data"]["rulings"]), 5)
        self.assertIn("5 次", dec["text"])
        self.assertNotIn("r-", dec["text"])

    def test_four_not_yet(self):
        self.rule(4)
        self.assertEqual(rulings_promote.run(L.ctx(self.V)), [])


if __name__ == "__main__":
    unittest.main()
