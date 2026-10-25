"""lint 清單 1（驗收 1）：綜合卡的〔f-〕〔s-〕〔r-〕〔c-〕指到不存在、不採用、已收回的 → synthesis_fix 帶原因；cards todo 的 stale 有那張、
reason 對；改寫後那筆消失。紀事裡引用舊的不算。"""
import shutil
import unittest
from pathlib import Path

from tests import _entities as E
from tests import _lint as L
from kb._lib import cards, rulings, statements, turn  # noqa: E402
from kb._lib import sources as sources_lib  # noqa: E402
from kb.lint import state  # noqa: E402
from kb.lint.checks import citations  # noqa: E402


class Citations(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()
        self.t = turn.start(self.V, None, "")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stale(self):
        return [i for i in cards.todo(self.V, sources_lib.load(self.V))["synthesis_stale"] if i["path"] == L.XINYI_REL]

    def test_bad_ids_marked_and_rewrite_clears(self):
        quote = cards.parse_front((self.V / E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王"])).read_text(
            encoding="utf-8"))["編號"]
        rulings.add(self.V, "不採用", [], [quote], "這份報價別信", self.t)
        s = statements.add(self.V, "信義王改用系統櫃", ["信義王"], self.t)[0]
        statements.withdraw(self.V, s["id"], self.t)
        L.write_synthesis(self.V, body=f"## 現況\n- 報價 180 萬〔{quote}〕\n- 不存在〔f-00000000〕\n- 收回的〔{s['id']}〕\n\n"
                                       f"## 紀事\n- 10-20 收回過一條〔{s['id']}〕\n")
        (found,) = citations.run(L.ctx(self.V))
        self.assertEqual(found["kind"], "fix")
        self.assertEqual(found["data"]["cards"][0]["ids"], sorted([quote, "f-00000000", s["id"]]))
        self.assertTrue(found["apply"](L.ctx(self.V)))
        (fix,) = state.fixes(self.V)
        self.assertEqual((fix["path"], fix["reason"]), (L.XINYI_REL, "出處點不開"))
        (item,) = self.stale()
        self.assertEqual(item["reason"], "出處點不開")
        p = self.V / L.XINYI_REL
        p.write_text(p.read_text(encoding="utf-8").replace("- 不存在〔f-00000000〕\n", ""), encoding="utf-8")
        self.assertEqual(state.fixes(self.V), [], "改寫之後那筆就不算了")

    def test_old_ones_in_history_section_are_fine(self):
        s = statements.add(self.V, "信義王改用系統櫃", ["信義王"], self.t)[0]
        statements.withdraw(self.V, s["id"], self.t)
        L.write_synthesis(self.V, body=f"## 現況\n- 進行中\n\n## 紀事\n- 10-20 說過又收回〔{s['id']}〕\n")
        self.assertEqual(citations.run(L.ctx(self.V)), [])

    def test_clean_card(self):
        L.write_synthesis(self.V)
        self.assertEqual(citations.run(L.ctx(self.V)), [])


if __name__ == "__main__":
    unittest.main()
