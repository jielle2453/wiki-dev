"""對話外回合（D-502）：對話答完後沒有 session_id 呼叫 current() → 開終端機回合（尾 0000），不掛回那句對話；
對話回答中、有 session_id、--turn 照舊。整條路：對話一句（UserPromptSubmit → 寫入 → Stop）之後終端機 kb agenda done。"""
import json
import shutil
import unittest

from tests import _entities as E
from tests.test_hooks_stop import HOOK as STOP_HOOK, TURN_HOOK, run, stop_payload
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import agenda, journal, turn  # noqa: E402

SID = "test-sid"


class Current(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        self.d = self.V / ".system" / "turns"

    def tearDown(self):
        turn.OVERRIDE = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    def read(self, name):
        return json.loads((self.d / name).read_text(encoding="utf-8"))

    def ended(self):
        conv = turn.start(self.V, SID, "明天下午三點跟陳志強開會")
        turn.set_done(self.V, SID)
        return conv

    def test_ended_conversation_opens_terminal_turn(self):
        """驗收 1：回新回合，尾 0000、session_id 空；current.json 換成它；turns/<sid>.json 不被改。"""
        conv = self.ended()
        sess_before = (self.d / f"{SID}.json").read_bytes()
        t = turn.current(self.V)
        self.assertNotEqual(t["turn"], conv["turn"])
        self.assertTrue(t["turn"].endswith("-0000"), t["turn"])
        self.assertEqual(t["session_id"], "")
        self.assertEqual(self.read("current.json")["turn"], t["turn"])
        self.assertEqual((self.d / f"{SID}.json").read_bytes(), sess_before)

    def test_terminal_turn_is_reused(self):
        """驗收 2：同一個終端機再叫一次沿用同一個 0000 回合。"""
        self.ended()
        first = turn.current(self.V)
        self.assertEqual(turn.current(self.V)["turn"], first["turn"])

    def test_answering_conversation_keeps_its_turn(self):
        """驗收 3：對話回答中（done false）回那句對話的回合。"""
        conv = turn.start(self.V, SID, "改一下")
        self.assertEqual(turn.current(self.V)["turn"], conv["turn"])
        self.assertEqual(sorted(p.name for p in self.d.iterdir()), ["current.json", f"{SID}.json"])

    def test_with_sid_reads_session_file_even_when_done(self):
        """驗收 4：有 session_id 讀 turns/<sid>.json，行為不變。"""
        conv = self.ended()
        self.assertEqual(turn.current(self.V, SID)["turn"], conv["turn"])
        self.assertEqual(self.read("current.json")["turn"], conv["turn"])

    def test_override_unchanged(self):
        """驗收 5：--turn 回那個回合。"""
        conv = self.ended()
        turn.OVERRIDE = conv["turn"]
        self.assertEqual(turn.current(self.V)["turn"], conv["turn"])
        self.assertEqual(self.read("current.json")["turn"], conv["turn"])

    def test_old_turn_file_without_done_counts_as_done(self):
        """舊回合檔沒有 done 鍵：_read_turn 補成 true，照這個值。"""
        self.d.mkdir(parents=True, exist_ok=True)
        old = {"schema_version": 1, "turn": "20260101-090000-test", "session_id": SID, "started": "2026-01-01T09:00:00",
               "prompt_head": "舊的", "approved": False}
        (self.d / "current.json").write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
        self.assertTrue(turn.current(self.V)["turn"].endswith("-0000"))


class ActiveJob(unittest.TestCase):
    """裁定 2：回合已答完、但這個 session 有背景整理 job（收通知那一輪）→ 還算對話裡，current() 回那句、不寫程式段。"""

    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_done_with_active_job_stays_in_conversation(self):
        r = run_kb("agenda", "add", "--kind", "到期", "--date", "2999-11-30", "--text", "交屋", "--json", cwd=self.V)
        aid = json.loads(r.stdout)["item"]["id"]
        conv = turn.start(self.V, SID, "好，現在做")
        (self.V / ".system" / "batches.json").write_text(json.dumps(
            {"schema_version": 1, "jobs": [{"job": "j-1", "session_id": SID, "status": "open"}], "batches": [], "agents": []}),
            encoding="utf-8")
        turn.set_done(self.V, SID)
        self.assertTrue(turn.in_conversation(self.V))
        self.assertEqual(turn.current(self.V)["turn"], conv["turn"])
        before = [x for m in journal.months(self.V) for x in journal.read_lines(self.V, m) if x.get("kind") == "program"]
        r = run_kb("agenda", "done", aid, cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = [x for m in journal.months(self.V) for x in journal.read_lines(self.V, m) if x.get("kind") == "program"]
        self.assertEqual(after, before, "收通知那一輪跑的不寫程式段")
        self.assertEqual(turn._read_turn(turn._current_file(self.V))["turn"], conv["turn"])
        self.assertIn(".system/agenda.json", [e["path"] for e in turn.entries(self.V, conv["turn"])])


class AfterStop(unittest.TestCase):
    """裁定 3：turn note／redact 是補記剛答完那一句，沒帶 --turn 讀 current.json（turn.last），不開 0000。"""

    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_last_is_read_only(self):
        turn._current_file(self.V).unlink(missing_ok=True)  # 夾具建庫時跑過 kb，已有 current.json
        self.assertIsNone(turn.last(self.V))
        self.assertFalse(turn._current_file(self.V).exists())
        conv = turn.start(self.V, SID, "改一下")
        turn.set_done(self.V, SID)
        self.assertEqual(turn.last(self.V)["turn"], conv["turn"])
        self.assertEqual(turn._read_turn(turn._current_file(self.V))["turn"], conv["turn"])

    def test_redact_after_stop_rewrites_that_sentence(self):
        conv = turn.start(self.V, SID, "幫我登入 ERP")
        journal.begin_turn(self.V, None, conv)
        r = run(STOP_HOOK, stop_payload(self.V, "好了。"))
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_kb("turn", "redact", "幫我登入 ERP，已遮", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        row = next(x for x in journal.read_lines(self.V, journal.month_of(conv["turn"])) if x["turn"] == conv["turn"])
        self.assertEqual(row["prompt"], "幫我登入 ERP，已遮")
        self.assertEqual(turn._read_turn(turn._session_file(self.V, SID))["prompt_head"], "幫我登入 ERP，已遮")
        self.assertEqual(turn._read_turn(turn._current_file(self.V))["turn"], conv["turn"], "不開 0000")

    def test_note_without_any_turn_is_refused(self):
        turn._current_file(self.V).unlink(missing_ok=True)
        r = run_kb("turn", "note", "x", cwd=self.V)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertFalse((self.V / ".system" / "turns" / "current.json").exists())


class WholePath(unittest.TestCase):
    """驗收 6：對話一句之後在終端機 kb agenda done → versions list 那筆自己一個回合，不在那句對話底下。"""

    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kb(self, *args):
        r = run_kb(*args, cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def add(self, text):
        out = self.kb("agenda", "add", "--kind", "到期", "--date", "2999-11-30", "--text", text, "--json")
        return json.loads(out)["item"]["id"]

    def status(self, aid):
        return next(i for i in agenda.load(self.V)["items"] if i["id"] == aid)["status"]

    def test_agenda_done_after_conversation_is_its_own_turn(self):
        other = self.add("交屋")
        turn.start(self.V, None, "")  # 終端機先前的寫入封起來
        r = run(TURN_HOOK, {"session_id": SID, "cwd": str(self.V), "prompt": "明天下午三點跟陳志強開會",
                            "hook_event_name": "UserPromptSubmit"})
        self.assertEqual(r.returncode, 0, r.stderr)
        conv = turn._read_turn(turn._session_file(self.V, SID))["turn"]
        meeting = self.add("跟陳志強開會")  # 模型在對話裡叫的
        r = run(STOP_HOOK, stop_payload(self.V, "記好了。"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.kb("agenda", "done", other)  # 對話關掉之後，終端機（排程）跑的
        self.assertEqual(self.status(other), "done")

        latest, *rest = json.loads(self.kb("versions", "list", "--json"))
        self.assertNotEqual(latest["turn"], conv)
        self.assertTrue(latest["turn"].endswith("-0000"), latest["turn"])
        self.assertEqual(rest[0]["turn"], conv, "那句對話自己一筆，排在後面")
        rows = [x for m in journal.months(self.V) for x in journal.read_lines(self.V, m)]
        self.assertEqual([x["turn"] for x in rows if x.get("kind") != "program"], [conv])
        # 程式段代號用現在時間組（D-085 L2），可能跟備份回合差一秒（備份回合代號要排在那句對話之後），只比對得到一段
        self.assertEqual(len([x for x in rows if x.get("kind") == "program" and x["command"] == "agenda done"]), 1, rows)

        r = run_kb("versions", "revert", conv, cwd=self.V)  # 退那句對話：它不是最近一次，不退、agenda done 不動
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual(self.status(other), "done")
        self.kb("versions", "revert")  # 最近一次只有 agenda done：退掉它，對話裡加的那條留著
        self.assertEqual(self.status(other), "open")
        self.assertEqual(self.status(meeting), "open")


if __name__ == "__main__":
    unittest.main()
