"""lint 清單 5（驗收 4）：推測放太久沒確認（lint_inferred_days）：日程、實體、設定檔列各合成一件；放沒多久的不列。"""
import json
import shutil
import unittest

from tests import _lint as L
from kb.lint.checks import inferred  # noqa: E402


def agenda_item(day):
    return {"id": "a-11112222", "kind": "promise", "date": "2026-12-05", "text": "給報價", "entities": ["信義王"],
            "status": "open", "source": "inferred", "created_turn": f"{day.replace('-', '')}-100000-abcd",
            "history": [{"date": day, "change": "add", "by": "ai", "turn": "t"}]}


class Inferred(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put_agenda(self, day):
        (self.V / ".system" / "agenda.json").write_text(
            json.dumps({"schema_version": 1, "items": [agenda_item(day)]}, ensure_ascii=False), encoding="utf-8")

    def test_old_guesses_one_per_kind(self):
        self.put_agenda("2026-10-16")
        found = inferred.run(L.ctx(self.V, today="2026-11-25"))
        by_key = {f["key"]: f for f in found}
        self.assertEqual(set(by_key), {"inferred:agenda", "inferred:entity", "inferred:profile"})
        self.assertTrue(all(f["kind"] == "decide" for f in found))
        self.assertEqual(by_key["inferred:agenda"]["data"]["dates"], ["2026-12-05"])
        self.assertIn("王宅", by_key["inferred:entity"]["text"])

    def test_recent_not_listed(self):
        self.put_agenda("2026-10-20")
        self.assertEqual(inferred.run(L.ctx(self.V, today="2026-10-30")), [])


if __name__ == "__main__":
    unittest.main()
