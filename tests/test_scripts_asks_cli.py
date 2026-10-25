"""kb asks 的問法（lint 題，D-225、D-226；驗收 16、17）：跟這一句有關的才問（--about、這一回合查過的）、有時間性的照講、
其他報件數（others、others_line 一個 session 說一次）、--all 全部、先放著（kb asks set-aside）。"""
import datetime as dt
import json
import shutil
import unittest

from tests import _entities as E
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import pending, turn  # noqa: E402

XINYI, DAAN = "e-5c1d0a7e", "e-0f3e9a21"
LINE = "還有 {n} 件要你決定的事，有空說『看待處理』"


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

    def asks(self, *args, code=0):
        r = run_kb("asks", *args, "--json", cwd=self.V)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def all(self):
        return self.asks("--all")


class Scope(Base):
    def test_about_limits_to_related_and_counts_others(self):
        got = self.asks("--about", "信義王")
        self.assertEqual({a["key"] for a in got["asks"]}, set(self.xinyi))
        self.assertTrue(all(XINYI in a["about"]["entities"] for a in got["asks"]))
        self.assertEqual(got["others"], self.base_all + 4)
        self.assertEqual(got["others_line"], LINE.format(n=self.base_all + 4))
        numbers = [r["n"] for a in got["asks"] for r in a["results"]]
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)), "篩過之後重新從 1 連號")

    def test_others_line_once_per_session(self):
        self.assertIsNotNone(self.asks("--about", "信義王")["others_line"])
        turn.start(self.V, "s1", "那大安陳呢")
        self.assertIsNone(self.asks("--about", "信義王")["others_line"], "同一個 session 說過了")
        turn.start(self.V, "s2", "新對話")
        self.assertIsNotNone(self.asks("--about", "信義王")["others_line"], "新 session 又說一次")

    def test_alias_and_unknown_about(self):
        got = self.asks("--about", "沒登記的名字")
        self.assertEqual(got["asks"], [])

    def test_lookup_in_conversation_counts_as_related(self):
        r = run_kb("lookup", "信義王", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        got = self.asks()
        self.assertEqual({a["key"] for a in got["asks"]}, set(self.xinyi))

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
        self.assertLessEqual(len(got["asks"]), 3)


class AllAndSetAside(Base):
    def test_all_has_everything_and_no_line(self):
        got = self.all()
        self.assertEqual(len(got["asks"]), self.base_all + 6)
        self.assertNotIn("others_line", got)
        self.assertEqual(got["set_aside"], 0)

    def test_set_aside_pending_and_back(self):
        r = run_kb("asks", "set-aside", self.other[0], cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()),
                         (0, "先放著了：「大安陳1.pdf」讀不到：檔案壞了；有變化或快到期會再拿出來"), r.stderr)
        got = self.all()
        self.assertNotIn(self.other[0], [a["key"] for a in got["asks"]])
        self.assertEqual(got["set_aside"], 1)
        self.assertEqual(self.asks("--about", "信義王")["others"], self.base_all + 3, "先放著的不算進件數")

    def test_set_aside_non_pending_key_comes_back_when_object_changes(self):
        draft = self.V / "AI 產出" / "報告" / "信義王 進度報告（草稿）.md"
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

    def test_unknown_key(self):
        r = run_kb("asks", "set-aside", "name:e-00000000@abc", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "沒有這個問題"))


if __name__ == "__main__":
    unittest.main()
