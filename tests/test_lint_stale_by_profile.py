"""lint 清單 10（驗收 9）：卡型那節的列比檔案卡的製卡日期新 → 待處理一件（合成，帶 kb cards redo --ids）；
第四節的列比綜合卡的更新日新 → synthesis_fix「設定檔改了」。"""
import json
import re
import shutil
import unittest

from tests import _entities as E
from tests import _lint as L
from kb._lib import cards, profile  # noqa: E402
from kb.lint import state  # noqa: E402
from kb.lint.checks import stale_by_profile  # noqa: E402


class StaleByProfile(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def bump(self, section, name_key, name, day):
        p = self.V / profile.PROFILE_POSIX
        data = json.loads(p.read_text(encoding="utf-8"))
        for row in data[section]:
            if row.get(name_key) == name:
                row["date"] = day
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def card(self, rel, title, made):
        fid = L.write_card(self.V, rel, title)
        path = self.V / cards.card_of(self.V, fid)["path"]
        path.write_text(re.sub(r"^製卡日期: .*$", f"製卡日期: {made}", path.read_text(encoding="utf-8"), count=1, flags=re.M),
                        encoding="utf-8")
        return cards.parse_front(path.read_text(encoding="utf-8"))["編號"]

    def test_cards_made_before_row_change(self):
        a = self.card(E.QUOTE, "信義王報價", "2026-10-01")
        self.card(E.ESTIMATE, "內湖李估價", "2026-10-30")
        self.bump("card_types", "name", "報價", "2026-10-20")
        found = stale_by_profile.run(L.ctx(self.V))
        (dec,) = L.by_kind(found, "decide")
        self.assertEqual(dec["key"], "redo_by_profile:報價:2026-10-20")
        self.assertEqual(dec["data"]["ids"], [a])
        self.assertEqual(dec["data"]["results"][0]["do"], [f"kb cards redo --ids {a}"])

    def test_synthesis_older_than_section_row(self):
        L.write_synthesis(self.V, today="2026-10-10")
        self.bump("synthesis_sections", "type", "案子", "2026-10-20")
        (fix,) = L.by_kind(stale_by_profile.run(L.ctx(self.V)), "fix")
        fix["apply"](L.ctx(self.V))
        self.assertEqual([f["reason"] for f in state.fixes(self.V)], ["設定檔改了"])

    def test_nothing_changed(self):
        L.write_synthesis(self.V)
        self.assertEqual(stale_by_profile.run(L.ctx(self.V)), [])


if __name__ == "__main__":
    unittest.main()
