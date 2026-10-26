"""標籤字典第五節（D-238；驗收 11）：這一回合改寫的綜合卡標籤行跟備份比多了詞 → tell 一張一句「<名稱>標了：欄 詞」，
超過 3 張併成「另外 N 張也照字典標了」；只拿掉詞不講；新寫的卡全部算新加；派工回合（這一句收尾的整理）也算；kb asks 也帶。"""
import json
import shutil
import unittest
from datetime import datetime, timedelta

from tests import _entities as E
from tests import _tags as T
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import batches, entities, plan, turn  # noqa: E402

LI, LIN, ZHANG = "e-aaaa0001", "e-aaaa0003", "e-aaaa0002"
LI_REL, LIN_REL, ZHANG_REL = "案子/內湖李/內湖李.md", "案子/北投林/北投林.md", "案子/士林張/士林張.md"
SID = "sid-tags"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        data = entities.load(self.V)["entities"]
        data += [E.entity(LI, "內湖李", card=True), E.entity(LIN, "北投林", card=True), E.entity(ZHANG, "士林張", card=True)]
        E.put_entities(self.V, data)
        T.set_tags(self.V)
        self.cards = [(E.XINYI, "信義王", T.XINYI_REL), (E.DAAN, "大安陳", T.DAAN_REL), (LI, "內湖李", LI_REL),
                      (LIN, "北投林", LIN_REL), (ZHANG, "士林張", ZHANG_REL)]
        for eid, name, rel in self.cards:
            T.write_synthesis(self.V, eid, name, rel, ["工種: [木作]"])
        self.t = turn.start(self.V, SID, "整理")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def rewrite(self, i, lines, turn_id=None):
        eid, name, rel = self.cards[i]
        turn.backup(self.V, rel, turn_id or self.t)
        T.write_synthesis(self.V, eid, name, rel, lines)


class Tell(Base):
    def test_one_card_added_word(self):
        self.rewrite(0, ["工種: [木作, 水電]", "階段: 施工"])
        self.assertEqual(plan._tagged_tell(self.V), ["信義王標了：工種 水電；階段 施工"])

    def test_more_than_three_folded(self):
        for i in range(4):
            self.rewrite(i, ["工種: [木作, 水電]"])
        got = plan._tagged_tell(self.V)
        self.assertEqual(got[:3], ["信義王標了：工種 水電", "大安陳標了：工種 水電", "內湖李標了：工種 水電"])
        self.assertEqual(got[3:], ["另外 1 張也照字典標了"])

    def test_only_removed_not_told(self):
        self.rewrite(0, ["工種: []"])
        self.assertEqual(plan._tagged_tell(self.V), [])

    def test_untouched_turn_says_nothing(self):
        self.assertEqual(plan._tagged_tell(self.V), [])

    def test_new_card_counts_all_words(self):
        eid, name, rel = self.cards[4]
        (self.V / rel).unlink()
        turn.backup(self.V, rel, self.t)  # 新建：create，沒有舊檔
        T.write_synthesis(self.V, eid, name, rel, ["工種: [水電]", "階段: 報價"])
        self.assertEqual(plan._tagged_tell(self.V), ["士林張標了：工種 水電；階段 報價"])

    def test_job_turn_closed_this_sentence(self):
        """這個對話前一句派出去、這一句收尾的整理：寫在 job 回合的卡也算。"""
        job_turn = self.t
        self.rewrite(1, ["工種: [木作, 磁磚]"], job_turn)
        now = turn.start(self.V, SID, "做完了嗎")
        closed = (datetime.strptime(now["started"], "%Y-%m-%dT%H:%M:%S") + timedelta(seconds=1)).strftime(
            "%Y-%m-%dT%H:%M:%S")
        data = batches.empty()
        data["jobs"] = [{"job": "j-1", "session_id": SID, "turn": job_turn, "created": now["started"], "status": "closed",
                         "closed": closed}]
        (self.V / batches.BATCHES_POSIX).write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(plan._tagged_tell(self.V), ["大安陳標了：工種 磁磚"])
        data["jobs"][0]["closed"] = "2000-01-01T00:00:00"
        (self.V / batches.BATCHES_POSIX).write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(plan._tagged_tell(self.V), [], "更早就收尾的不算")

    def test_program_rename_or_merge_not_told(self):
        """裁定 12：tag 指令、apply 改名合併是程式改的，不算「標了」。"""
        r = run_kb("profile", "tag", "merge", "案子", "工種", "木作", "--into", "水電", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(plan._tagged_tell(self.V), [])
        r = run_kb("profile", "tag", "rename", "案子", "工種", "水電", "--to", "水電工程", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(plan._tagged_tell(self.V), [])
        self.assertNotIn("標了", "".join(json.loads(run_kb("asks", "--json", cwd=self.V).stdout)["tell"]))

    def test_asks_and_todo_carry_it(self):
        self.rewrite(0, ["工種: [木作, 水電]"])
        for args in (("asks", "--json"), ("cards", "todo", "--json")):
            with self.subTest(args=args):
                got = json.loads(run_kb(*args, cwd=self.V).stdout)
                self.assertIn("信義王標了：工種 水電", got["tell"])


if __name__ == "__main__":
    unittest.main()
