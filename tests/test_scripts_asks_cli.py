"""kb asks 的問法（lint 題，D-225、D-226；驗收 16、17）：跟這一句有關的才問（--about、這一回合查過的）、有時間性的照講、
一次最多一題（ASKS_MAX）、later 帶一題無關的、同一題一個 session 只回一次（asks_seen.json）、沒回的到期關掉（ask_expire_days）、
--all 全部、先放著（kb asks set-aside，逾期的也收）。放寬乙 D-310(4)、D-322 第 6 件、D-334(7)(8)。"""
import datetime as dt
import json
import shutil
import unittest

from tests import _entities as E
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import pending, turn  # noqa: E402

XINYI, DAAN = "e-5c1d0a7e", "e-0f3e9a21"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        self.t = turn.start(self.V, "s1", "信義王現在怎樣")["turn"]
        self.base_all = len(self.all()["asks"])
        self.xinyi = [self.unreadable(f"f-1000000{n}", f"信義王{n}.pdf", [XINYI]) for n in (1, 2)]
        self.other = [self.unreadable(f"f-2000000{n}", f"大安陳{n}.pdf", [DAAN]) for n in (1, 2, 3, 4)]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def unreadable(self, fid, name, ents):
        return pending.add(self.V, "unreadable", [fid], f"「{name}」讀不到", "檔案壞了", self.t, entity_ids=ents)

    def asks(self, *args, code=0, session=None):
        pre = ["--session", session] if session else []
        r = run_kb(*pre, "asks", *args, "--json", cwd=self.V)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def all(self):
        return self.asks("--all")


class Scope(Base):
    def test_about_limits_to_related_and_counts_others(self):
        got = self.asks("--about", "信義王")
        self.assertEqual(len(got["asks"]), 1, "ASKS_MAX 是 1")
        self.assertIn(got["asks"][0]["key"], set(self.xinyi))
        self.assertIn(XINYI, got["asks"][0]["about"]["entities"])
        self.assertIsNotNone(got["later"], "無關的最急一題放 later")
        self.assertNotIn(got["later"]["key"], {a["key"] for a in got["asks"]})
        self.assertEqual(got["others"], self.base_all + 6 - 1)
        self.assertNotIn("others_line", got)
        numbers = [r["n"] for r in got["asks"][0]["results"]]
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)), "篩過之後重新從 1 連號")

    def test_later_null_when_nothing_else(self):
        for pid in self.xinyi + self.other:
            run_kb("pending", "dismiss", pid, cwd=self.V)
        got = self.asks("--about", "信義王")
        self.assertEqual(len(got["asks"]), 0)
        self.assertEqual(got["later"] is None, self.base_all == 0)

    def test_same_ask_once_per_session(self):
        first = self.asks("--about", "信義王", session="s1")
        second = self.asks("--about", "信義王", session="s1")
        shown = {first["asks"][0]["key"], first["later"]["key"]}
        again = {a["key"] for a in second["asks"]} | ({second["later"]["key"]} if second["later"] else set())
        self.assertFalse(shown & again, "同一個 session 回過的題不再出現")
        third = self.asks("--about", "信義王", session="s2")
        self.assertEqual(third["asks"][0]["key"], first["asks"][0]["key"], "換 session 又出一次")
        every = {a["key"] for a in self.asks("--all", session="s1")["asks"]}
        self.assertTrue(shown <= every, "--all 照列")
        seen = json.loads((self.V / ".system" / "asks_seen.json").read_text(encoding="utf-8"))
        self.assertEqual(seen[first["asks"][0]["key"]]["sessions"], ["s1", "s2"])
        self.assertEqual(seen[first["asks"][0]["key"]]["first"], dt.date.today().isoformat())

    def test_no_session_not_recorded(self):
        self.asks("--about", "信義王")
        self.assertFalse((self.V / ".system" / "asks_seen.json").exists())

    def test_expired_ask_is_closed(self):
        first = self.asks("--about", "信義王", session="s1")
        key = first["asks"][0]["key"]
        p = self.V / ".system" / "asks_seen.json"
        seen = json.loads(p.read_text(encoding="utf-8"))
        seen[key]["first"] = (dt.date.today() - dt.timedelta(days=15)).isoformat()
        p.write_text(json.dumps(seen, ensure_ascii=False), encoding="utf-8")
        got = self.asks("--about", "信義王", session="s9")
        self.assertIn(key, got["expired"])
        self.assertNotIn(key, {a["key"] for a in got["asks"]})
        item = next(i for i in pending.load(self.V)["items"] if i["id"] == key)
        self.assertEqual((item["status"], item["how"]), ("closed", "沒回，照推測"))
        self.assertEqual(item["reason"], "檔案壞了", "unreadable 本來的 reason 不蓋掉")
        self.assertNotIn(key, {a["key"] for a in self.all()["asks"]})

    def test_answered_ask_leaves_seen(self):
        first = self.asks("--about", "信義王", session="s1")
        key = first["asks"][0]["key"]
        run_kb("pending", "dismiss", key, cwd=self.V)
        self.asks("--about", "信義王", session="s1")
        seen = json.loads((self.V / ".system" / "asks_seen.json").read_text(encoding="utf-8"))
        self.assertNotIn(key, seen)

    def test_alias_and_unknown_about(self):
        got = self.asks("--about", "沒登記的名字")
        self.assertEqual(got["asks"], [])

    def test_lookup_in_conversation_counts_as_related(self):
        r = run_kb("lookup", "信義王", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        got = self.asks()
        self.assertEqual(len(got["asks"]), 1)
        self.assertIn(got["asks"][0]["key"], set(self.xinyi))

    def test_time_sensitive_unrelated_still_asked(self):
        tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        later = (dt.date.today() + dt.timedelta(days=3)).isoformat()
        item = {"id": "a-12345678", "kind": "promise", "date": tomorrow, "text": "給報價", "entities": ["大安陳"],
                "status": "open", "source": "interview", "created_turn": "t", "history": [],
                "proposal": {"date": later, "text": "給報價", "card": None}}
        (self.V / ".system" / "agenda.json").write_text(
            json.dumps({"schema_version": 1, "items": [item]}, ensure_ascii=False), encoding="utf-8")
        got = self.asks("--about", "信義王")
        kinds = [a["kind"] for a in got["asks"]]
        self.assertIn("agenda_conflict", kinds)
        self.assertEqual(len(got["asks"]), 1)


class AllAndSetAside(Base):
    def test_all_has_everything_and_no_line(self):
        got = self.all()
        self.assertEqual(len(got["asks"]), self.base_all + 6)
        self.assertNotIn("others_line", got)
        self.assertNotIn("later", got)
        self.assertEqual(got["set_aside"], 0)

    def test_set_aside_pending_and_back(self):
        r = run_kb("asks", "set-aside", self.other[0], cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()),
                         (0, "先放著了：「大安陳1.pdf」讀不到：檔案壞了；有變化或快到期會再拿出來"), r.stderr)
        got = self.all()
        self.assertNotIn(self.other[0], [a["key"] for a in got["asks"]])
        self.assertEqual(got["set_aside"], 1)
        self.assertEqual(self.asks("--about", "信義王")["others"], self.base_all + 6 - 1 - 1, "先放著的不算進件數")

    def test_set_aside_non_pending_key_comes_back_when_object_changes(self):
        draft = self.V / "暫存區" / "報告" / "信義王 進度報告（草稿）.md"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_text("第一版\n", encoding="utf-8")
        turn.start(self.V, "s1", "下一句")  # 這一回合才寫的草稿不問
        key = next(a["key"] for a in self.all()["asks"] if a["kind"] == "draft")
        r = run_kb("asks", "set-aside", key, cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(r.stdout.startswith("先放著了：信義王 進度報告 的草稿還在等你看"))
        self.assertNotIn("draft", [a["kind"] for a in self.all()["asks"]])
        draft.write_text("第二版\n", encoding="utf-8")
        self.assertIn("draft", [a["kind"] for a in self.all()["asks"]], "對象變了鍵就變，回到前面")

    def test_set_aside_overdue_is_accepted_and_gone(self):
        """放寬乙：逾期的也收（不再 exit 3）；先放著之後 asks 不再出它。"""
        d = (dt.date.today() - dt.timedelta(days=3)).isoformat()
        item = {"id": "a-12345678", "kind": "promise", "date": d, "text": "給報價", "entities": ["大安陳"],
                "status": "open", "source": "interview", "created_turn": "t", "history": []}
        (self.V / ".system" / "agenda.json").write_text(
            json.dumps({"schema_version": 1, "items": [item]}, ensure_ascii=False), encoding="utf-8")
        over = next(a for a in self.all()["asks"] if a["kind"] == "overdue")
        r = run_kb("asks", "set-aside", over["key"], cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("overdue", [a["kind"] for a in self.all()["asks"]])
        self.assertNotIn("overdue", [a["kind"] for a in self.asks("--about", "信義王")["asks"]])

    def test_unknown_key(self):
        r = run_kb("asks", "set-aside", "name:e-00000000@abc", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "沒有這個問題"))


class LookupCarries(Base):
    """#46：kb lookup 順帶「回答末尾要問的事」（同 kb asks --about <查的實體>），answer 不必再叫 asks；同一句只有第一次 lookup 帶。"""
    def lookup(self, *args, session=None, turn_id=None):
        pre = (["--session", session] if session else []) + (["--turn", turn_id] if turn_id else [])
        r = run_kb(*pre, "lookup", "信義王", *args, cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def test_json_carries_asks_once_per_turn(self):
        got = json.loads(self.lookup("--json", session="s1"))["asks"]
        self.assertIn(got["asks"][0]["key"], set(self.xinyi))
        self.assertIsNotNone(got["later"])
        self.assertEqual(set(got), {"asks", "later", "others", "tell"})
        seen = json.loads((self.V / ".system" / "asks_seen.json").read_text(encoding="utf-8"))
        self.assertIn(got["asks"][0]["key"], seen)  # 跟 kb asks 一樣記「問過」
        self.assertIsNone(json.loads(self.lookup("--json", session="s1"))["asks"])  # 同一句第二次不帶

    def test_job_turn_does_not_carry(self):
        """--turn（子代理、card-maker）不回答客戶：不帶題、不記問過（review 第 1 條）。"""
        job = turn.start(self.V, "sid-job", "整理")["turn"]
        self.assertIsNone(json.loads(self.lookup("--json", turn_id=job))["asks"])
        self.assertFalse((self.V / ".system" / "asks_seen.json").exists())

    def test_text_has_end_section(self):
        out = self.lookup().splitlines()
        i = out.index("回答末尾要問：")
        self.assertIn("讀不到", out[i + 1])
        self.assertTrue(any(line.startswith("一段事說完再問：") for line in out[i:]))


if __name__ == "__main__":
    unittest.main()
