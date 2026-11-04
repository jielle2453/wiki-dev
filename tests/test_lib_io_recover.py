"""_lib/io.recover_json（放寬丙 6-3，D-311(2)，驗收 18）：.system/*.json 寫壞，下一個讀它的程式把最近一份讀得懂的備份換回來、
壞的留 .system/broken/、工作日誌有程式段；備份都沒了，清冊從檔案卡重建、編號與卡一致；實在沒辦法照舊丟 ValueError。"""
import json
import shutil
import unittest
from datetime import date

from tests import _cards
from kb._lib import agenda, inventory, journal, statements, turn  # noqa: E402
from kb._lib import io as kio  # noqa: E402

ITEM = {"id": "a-00000001", "kind": "deadline", "start": None, "date": date.today().isoformat(), "ended": None, "time": None,
        "text": "報稅", "entities": [], "status": "open", "source": "confirmed", "origin": None, "lead_days": None,
        "created_turn": "t", "history": []}


class Recover(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _cards.make_card_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, text):
        (self.V / rel).write_text(text, encoding="utf-8", newline="\n")

    def program_rows(self):
        month = journal.month_of(turn.start(self.V, None, "")["turn"])
        return [r for r in journal.read_lines(self.V, month) if r.get("kind") == "program" and r.get("command") == "recover"]

    def test_agenda_bad_json_is_replaced_from_turn_backup(self):
        good = json.dumps({"schema_version": 1, "items": [ITEM]}, ensure_ascii=False)
        self.write(".system/agenda.json", good)
        t = turn.start(self.V, None, "改日程")["turn"]
        turn.backup(self.V, ".system/agenda.json", t)  # 回合備份：改之前那一份
        self.write(".system/agenda.json", "{壞掉的")
        self.assertEqual([i["id"] for i in agenda.load(self.V)["items"]], ["a-00000001"])
        (kept,) = list((self.V / ".system" / "broken").iterdir())
        self.assertTrue(kept.name.endswith("-agenda.json"))
        self.assertEqual(kept.read_text(encoding="utf-8"), "{壞掉的")
        self.assertEqual(json.loads((self.V / ".system" / "agenda.json").read_text(encoding="utf-8"))["items"][0]["id"], "a-00000001")
        (row,) = self.program_rows()
        self.assertIn("日程", row["note"])

    def test_inventory_rebuilt_from_cards_when_no_backup(self):
        item = next(i for i in _cards_todo(self.V) if i)
        _cards.write_card(self.V, item, "大安陳會議一")
        card_id = item["id"]
        shutil.rmtree(self.V / ".system" / "versions", ignore_errors=True)
        from tests._streams_util import break_state
        break_state(self.V, "inventory", "{壞掉的")  # 舊的整份 JSON 壞了才走備份與重建（流水檔的正本是合併結果，副本壞了會自己重寫）
        got = inventory.load(self.V)
        self.assertEqual([e["id"] for e in got["entries"]], [card_id])
        self.assertEqual(got["entries"][0]["locations"][0]["uri"], "file://" + _cards.MEETING)
        self.assertEqual(len(list((self.V / ".system" / "broken").iterdir())), 1)
        self.assertTrue(self.program_rows())

    def test_nothing_to_recover_still_raises(self):
        shutil.rmtree(self.V / ".system" / "versions", ignore_errors=True)
        self.write(".system/statements.json", "{壞掉的")
        with self.assertRaises(ValueError):
            statements.load(self.V)
        self.assertFalse(kio.recover_json(self.V, ".system/statements.json")["ok"])
        self.assertEqual((self.V / ".system" / "statements.json").read_text(encoding="utf-8"), "{壞掉的")

    def test_inventory_without_cards_is_not_rebuilt(self):
        shutil.rmtree(self.V / ".system" / "versions", ignore_errors=True)
        from tests._streams_util import break_state
        break_state(self.V, "inventory", "{壞掉的")
        with self.assertRaises(ValueError):
            inventory.load(self.V)


def _cards_todo(V):
    from kb._lib import cards
    from kb._lib import sources as sources_lib
    return [i for i in cards.todo(V, sources_lib.load(V))["new"] if i["id"] == _cards.entry_of(V, _cards.MEETING)["id"]]


if __name__ == "__main__":
    unittest.main()
