"""多個對話同開時，退回只退自己那個對話的（#20，D-506～D-508）。黑箱：回合用真的 hooks/turn.py、hooks/stop.py 開與收，
kb 呼叫帶 --session（模擬守門插的）。驗收準則 1～8、10～12。"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests._guard_fixture import KB, ROOT, make_vault
from tests.test_scripts_versions_cli import said
from kb._lib import batches, turn  # noqa: E402

A, B = "sid-aaaa", "sid-bbbb"
AGENT = "a0204e72"
CARD_REL = "案子/信義王/信義王.md"
TURN_CODE = re.compile(r"\d{8}-\d{6}-")


def hook(name, data):
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))
    r = subprocess.run([sys.executable, str(ROOT / "hooks" / name)], input=json.dumps(data, ensure_ascii=False),
                       capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT), env=env)
    assert r.returncode == 0, r.stderr
    return r.stdout


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        self.card = self.V / CARD_REL

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kb(self, *args, sid=None):
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))
        head = ["--session", sid] if sid else []
        return subprocess.run([sys.executable, str(KB), *head, *args], capture_output=True, text=True,
                              encoding="utf-8", cwd=str(self.V), env=env)

    def prompt(self, sid, text):
        hook("turn.py", {"session_id": sid, "cwd": str(self.V), "prompt": text, "hook_event_name": "UserPromptSubmit"})
        return turn._read_turn(turn._session_file(self.V, sid))["turn"]

    def stop(self, sid):
        hook("stop.py", {"session_id": sid, "cwd": str(self.V), "hook_event_name": "Stop", "last_assistant_message": "好"})

    def agenda(self, sid, text, date="2026-11-25"):
        r = self.kb("agenda", "add", "--kind", "提醒", "--date", date, "--text", text, sid=sid)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def edit_card(self, sid, text):
        """檔案工具改綜合卡：守門放行前 before_write 帶這個對話的 sid（同 hooks/guard.py），再真的寫。"""
        ok, code, why = turn.before_write(self.V, str(self.card), str(self.V), "Z1", sid)
        self.assertTrue(ok, why)
        self.card.write_text(text, encoding="utf-8")

    def agenda_texts(self):
        p = self.V / ".system" / "agenda.json"
        return [i.get("text") for i in json.loads(p.read_text(encoding="utf-8")).get("items", [])] if p.is_file() else []

    def snapshot(self):
        """知識庫每個檔的 sha256（不含鎖與錯誤 log）：拒絕時什麼都不動。"""
        got = {}
        for p in sorted(self.V.rglob("*")):
            if p.is_file() and not p.name.endswith(".lock") and p.name != "hook-errors.log":
                got[p.relative_to(self.V).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
        return got


class Revert(Base):
    def test_1_revert_takes_this_conversations_turn(self):
        t_a = self.prompt(A, "11/25 有個會")
        self.agenda(A, "有個會")
        self.stop(A)
        self.prompt(B, "我習慣週五對帳，記下來")
        self.assertEqual(self.kb("entity", "add", "--type", "案子", "--name", "信義王", sid=B).returncode, 0)
        r = self.kb("statement", "add", "--entity", "信義王", "--text", "我習慣週五對帳", sid=B)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.stop(B)
        self.prompt(A, "退回上一步")
        r = self.kb("versions", "revert", sid=A)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(r.stdout.startswith(f"已退回 {said(self.V, t_a)}"), r.stdout)
        self.assertNotIn("有個會", self.agenda_texts())
        self.assertIn("我習慣週五對帳", self.kb("statement", "list", sid=A).stdout)

    def test_2_write_lands_in_own_turn_while_other_is_answering(self):
        t_a = self.prompt(A, "11/25 有個會")
        t_b = self.prompt(B, "你好")  # B 開口、還沒答完：current.json 是 B
        self.agenda(A, "有個會")
        rows = json.loads(self.kb("versions", "list", "--json", sid=A).stdout)
        mine = [x for x in rows if any(e["path"] == ".system/agenda.json" for e in x["entries"])]
        self.assertEqual([(x["turn"], x["session"]) for x in mine], [(t_a, "self")])
        # B 開口時每句開頭的比對可能在它的回合夾寫 detected.jsonl（放寬丙），但 A 的寫入不會落進 B 的 manifest
        self.assertFalse((self.V / ".system" / "versions" / t_b / "manifest.jsonl").exists())

    def test_3_same_card_changed_by_other_conversation_is_conflict(self):
        """放寬丙（D-321(4)）：後來別的對話改過同一張卡，那一項不做、列 conflict（取代整個不退的 D-508）。"""
        self.prompt(A, "信義王改一下")
        self.edit_card(A, "A 改的\n")
        self.stop(A)
        t_b = self.prompt(B, "信義王再改")
        self.edit_card(B, "B 改的\n")
        self.stop(B)
        self.prompt(A, "退回上一步")
        r = self.kb("versions", "revert", sid=A)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"之後又被動過（{said(self.V, t_b)}）", r.stdout)
        self.assertIsNone(TURN_CODE.search(r.stdout), r.stdout)  # B-074
        self.assertEqual(self.card.read_text(encoding="utf-8"), "B 改的\n")
        r = self.kb("versions", "revert", "--json", sid=A)
        self.assertEqual(r.returncode, 0, r.stdout)
        got = json.loads(r.stdout)
        hit = [c for c in got["conflict"] if c["now"] == CARD_REL]
        self.assertEqual(len(hit), 1, got)
        self.assertEqual(hit[0]["later"][0]["side"], "other")
        self.assertEqual(hit[0]["later"][0]["said"], said(self.V, t_b))
        self.assertIn("backup", hit[0]["then"])
        self.assertEqual(self.card.read_text(encoding="utf-8"), "B 改的\n")

    def test_4_same_state_file_refused(self):
        self.prompt(A, "11/25 有個會")
        self.agenda(A, "有個會")
        self.stop(A)
        self.prompt(B, "提醒我寄發票")
        self.agenda(B, "寄發票", "2026-11-30")
        self.stop(B)
        self.prompt(A, "退回上一步")
        r = self.kb("versions", "revert", sid=A)
        self.assertEqual(r.returncode, 0, r.stdout)  # 全部是 conflict 交 AI 判斷，不算失敗
        self.assertIn("agenda.json：之後又被動過", r.stdout)
        self.assertEqual(sorted(self.agenda_texts()), ["寄發票", "有個會"])

    def test_4b_other_turn_started_earlier_but_wrote_later_refused(self):
        """B 先開口、A 後開口；A 先寫、B 後寫：B 的回合代號比 A 早，但寫在後面，照樣算後來改過。"""
        self.prompt(B, "提醒我寄發票")
        self.prompt(A, "11/25 有個會")
        self.agenda(A, "有個會")
        self.agenda(B, "寄發票", "2026-11-30")
        self.stop(A)
        self.stop(B)
        self.prompt(A, "退回上一步")
        r = self.kb("versions", "revert", sid=A)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(sorted(self.agenda_texts()), ["寄發票", "有個會"])

    def test_4c_other_conversation_same_second_counts(self):
        """時間只到秒：代號比較早的別的對話在同一秒寫同一份，也算後來改過（寧可多擋）。"""
        t_b = self.prompt(B, "提醒我寄發票")
        t_a = self.prompt(A, "11/25 有個會")
        self.agenda(A, "有個會")
        self.agenda(B, "寄發票", "2026-11-30")
        rows = {e["path"]: e["time"] for e in turn.entries(self.V, t_a)}
        m = self.V / ".system" / "versions" / t_b / "manifest.jsonl"
        fixed = [dict(json.loads(ln), time=rows[json.loads(ln)["path"]]) for ln in m.read_text(encoding="utf-8").splitlines()]
        m.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in fixed), encoding="utf-8")
        self.stop(A)
        self.stop(B)
        self.prompt(A, "退回上一步")
        r = self.kb("versions", "revert", sid=A)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(sorted(self.agenda_texts()), ["寄發票", "有個會"])

    def test_4e_other_conversation_writes_again_after_us_refused(self):
        """裁定 4：B 先寫 X（manifest 記第一次）→ A 寫 X → B 再寫 X（只記 writes.jsonl）→ A 退回 exit 3、X 不變。"""
        t_b = self.prompt(B, "信義王改一下")
        self.edit_card(B, "B 第一次\n")
        m = self.V / ".system" / "versions" / t_b / "manifest.jsonl"  # B 的第一次早很多：只靠 writes.jsonl 才看得到
        m.write_text("".join(json.dumps(dict(json.loads(ln), time="2000-01-01T00:00:00"), ensure_ascii=False) + "\n"
                             for ln in m.read_text(encoding="utf-8").splitlines()), encoding="utf-8")
        self.prompt(A, "信義王再改")
        self.edit_card(A, "A 改的\n")
        self.edit_card(B, "B 第二次\n")
        self.edit_card(B, "B 第二次\n")
        self.assertEqual([w["path"] for w in turn.writes(self.V, t_b)], [CARD_REL])  # 檔案工具經 before_write 也記；同路徑只一行
        self.stop(A)
        self.stop(B)
        self.prompt(A, "退回上一步")
        r = self.kb("versions", "revert", sid=A)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn(f"之後又被動過（{said(self.V, t_b)}）", r.stdout)
        self.assertEqual(self.card.read_text(encoding="utf-8"), "B 第二次\n")

    def test_4d_terminal_refusal_does_not_say_other_conversation(self):
        """終端機跑的沒有「這個對話」：擋下來的對話回合寫「對話裡」，不說「另一個對話」。"""
        self.prompt(B, "提醒我寄發票")
        self.prompt(A, "11/25 有個會")
        self.agenda(A, "有個會")
        self.agenda(B, "寄發票", "2026-11-30")
        self.stop(A)
        self.stop(B)
        r = self.kb("versions", "revert")  # 退代號最新的 A，B 那句後來也寫了日程
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("之後又被動過", r.stdout)
        self.assertEqual(sorted(self.agenda_texts()), ["寄發票", "有個會"])

    def test_5_terminal_turn_is_in_range(self):
        self.prompt(A, "信義王改一下")
        self.edit_card(A, "A 改的\n")
        self.stop(A)
        self.agenda(None, "終端機記的")  # 對話外：0000 回合
        self.prompt(A, "退回上一步")
        r = self.kb("versions", "revert", sid=A)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("那一次", r.stdout.splitlines()[0])
        self.assertNotIn("終端機記的", self.agenda_texts())
        self.assertEqual(self.card.read_text(encoding="utf-8"), "A 改的\n")

    def test_6_own_turns_not_skipped_and_again_cancels(self):
        self.prompt(A, "11/25 有個會")
        self.agenda(A, "有個會")
        self.stop(A)
        self.prompt(B, "信義王改一下")
        self.edit_card(B, "B 改的\n")
        self.stop(B)
        t_a2 = self.prompt(A, "加一個案子新店吳宅")
        self.assertEqual(self.kb("entity", "add", "--type", "案子", "--name", "新店吳宅", sid=A).returncode, 0)
        self.stop(A)
        self.prompt(A, "退回上一步")
        r = self.kb("versions", "revert", sid=A)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(r.stdout.startswith(f"已退回 {said(self.V, t_a2)}"), r.stdout)
        self.assertNotIn("新店吳宅", self.kb("entity", "list", sid=A).stdout)
        self.stop(A)
        self.prompt(A, "再退回")
        r = self.kb("versions", "revert", sid=A)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("不再算已退回", r.stdout)
        self.assertIn("新店吳宅", self.kb("entity", "list", sid=A).stdout)
        self.assertEqual(self.agenda_texts(), ["有個會"])
        self.assertEqual(self.card.read_text(encoding="utf-8"), "B 改的\n")

    def test_7_terminal_revert_takes_latest_of_all(self):
        self.prompt(A, "11/25 有個會")
        self.agenda(A, "有個會")
        self.stop(A)
        t_b = self.prompt(B, "信義王改一下")
        self.edit_card(B, "B 改的\n")
        self.stop(B)
        r = self.kb("versions", "revert")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(r.stdout.startswith(f"已退回 {said(self.V, t_b)}"), r.stdout)
        self.assertEqual(self.agenda_texts(), ["有個會"])

    def test_11_cardmaker_job_turn_counts_as_dispatching_conversation(self):
        job = self.prompt(A, "好，現在做")
        batches.agent_start(self.V, A, AGENT)
        self.prompt(A, "信義王的報價在哪？")  # A 中途說話，job 回合已不是 A 的目前回合
        out = hook("guard.py", {"session_id": A, "cwd": str(self.V), "hook_event_name": "PreToolUse", "tool_name": "Write",
                                "tool_input": {"file_path": str(self.V / "檔案索引" / "客戶案件" / "新卡-00000001.md")},
                                "agent_id": AGENT, "agent_type": batches.AGENT})
        self.assertIn('"allow"', out)
        self.assertIn("檔案索引/客戶案件/新卡-00000001.md", [e["path"] for e in turn.entries(self.V, job)])
        self.stop(A)
        self.prompt(B, "信義王改一下")
        self.edit_card(B, "B 改的\n")
        self.stop(B)
        self.prompt(A, "退回上一步")
        rows = {x["turn"]: x["session"] for x in json.loads(self.kb("versions", "list", "--json", sid=A).stdout)}
        self.assertEqual(rows[job], "self")
        r = self.kb("versions", "revert", sid=A)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(r.stdout.startswith(f"已退回 {said(self.V, job)}"), r.stdout)

    def test_11b_job_turn_without_session_falls_back_to_batches(self):
        """turn.json 沒記 session_id 的 job 回合：照 batches.json 的 job session 認。"""
        job = self.prompt(A, "好，現在做")
        self.agenda(A, "有個會")
        meta = self.V / ".system" / "versions" / job / "turn.json"
        data = json.loads(meta.read_text(encoding="utf-8"))
        data["session_id"] = ""
        meta.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        p = self.V / ".system" / "batches.json"
        got = batches.load(self.V)
        got["jobs"].append({"job": "j-00000001", "session_id": B, "turn": job, "status": "closed",
                            "created": "2026-10-29T00:00:00", "closed": "2026-10-29T00:00:01"})
        p.write_text(json.dumps(got, ensure_ascii=False), encoding="utf-8")
        rows = {x["turn"]: x["session"] for x in json.loads(self.kb("versions", "list", "--json", sid=A).stdout)}
        self.assertEqual(rows[job], "other")


class List(Base):
    def test_8_list_hides_other_conversation(self):
        t_a = self.prompt(A, "11/25 有個會")
        self.agenda(A, "有個會")
        self.stop(A)
        t_b = self.prompt(B, "信義王改一下")
        self.edit_card(B, "B 改的\n")
        self.stop(B)
        self.prompt(A, "看一下改了什麼")
        r = self.kb("versions", "list", sid=A)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(said(self.V, t_a), r.stdout)
        self.assertNotIn(said(self.V, t_b), r.stdout)
        self.assertIn("另一個對話還有 1 次改動，不在這裡退", r.stdout.splitlines())
        self.assertIsNone(TURN_CODE.search(r.stdout), r.stdout)
        rows = {x["turn"]: x["session"] for x in json.loads(self.kb("versions", "list", "--json", sid=A).stdout)}
        self.assertEqual((rows[t_a], rows[t_b]), ("self", "other"))
        r = self.kb("versions", "list")  # 終端機：照列全部
        self.assertIn(said(self.V, t_b), r.stdout)
        self.assertNotIn("另一個對話", r.stdout)


class SecretShown(Base):
    """裁定 5：密碼動作（守門回 ask）也插 --session，secret_shown 標在叫它的那個對話的回合。"""

    def test_ask_carries_session_and_secret_shown_lands_in_own_turn(self):
        out = json.loads(hook("guard.py", {"session_id": A, "cwd": str(self.V), "hook_event_name": "PreToolUse",
                                           "tool_name": "Bash",
                                           "tool_input": {"command": f'python "{KB}" unlock get --name 工地大門'}}))
        out = out["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "ask")
        self.assertEqual(out["updatedInput"]["command"], f'python "{KB}" --session {A} unlock get --name 工地大門')
        out = json.loads(hook("guard.py", {"session_id": A, "cwd": str(self.V), "hook_event_name": "PreToolUse",
                                           "tool_name": "Bash",
                                           "tool_input": {"command": f'python "{KB}" --session {B} unlock get --name 工地大門'}}))
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")  # ask 那條也不准自己帶 --session
        self.prompt(A, "工地大門密碼多少")
        self.prompt(B, "你好")  # B 後開口：current.json 是 B
        self.assertFalse(turn._read_turn(turn._session_file(self.V, A)).get("secret_shown"))
        import contextlib
        import io
        from kb import cli
        from kb._lib import io as kio
        from kb._lib import unlock
        old_backend, old_cwd, old_timeout = unlock.BACKEND, os.getcwd(), kio.LOCK_TIMEOUT
        unlock.BACKEND = unlock.MemoryBackend()
        try:
            os.chdir(self.V)
            with contextlib.redirect_stdout(io.StringIO()) as got:
                self.assertEqual(cli.main(["unlock", "save", "--kind", "記下的密碼", "--name", "工地大門", "--value", "8899"]), 0)
                self.assertEqual(cli.main(["--session", A, "unlock", "get", "--name", "工地大門"]), 0, got.getvalue())
        finally:
            os.chdir(old_cwd)
            unlock.BACKEND = old_backend
            kio.LOCK_TIMEOUT = old_timeout  # kb unlock 會改全域的鎖逾時，不還原會拖慢同一行程後面的測試
            turn.SESSION = None
        self.assertTrue(turn._read_turn(turn._session_file(self.V, A)).get("secret_shown"))
        self.assertFalse(turn._read_turn(turn._session_file(self.V, B)).get("secret_shown"))

    def test_password_call_marks_own_turn_without_rewriting(self):
        """裁定 12：帶 --password 的呼叫不改寫指令（值不進 hook 輸出），守門直接替 A 的目前回合標 secret_shown。"""
        self.prompt(A, "用密碼開那份 PDF")
        self.prompt(B, "你好")  # B 後開口：current.json 是 B
        raw = hook("guard.py", {"session_id": A, "cwd": str(self.V), "hook_event_name": "PreToolUse", "tool_name": "Bash",
                                "tool_input": {"command": f'python "{KB}" convert a.pdf --saved 門 --explicit --password "zq-7731"'}})
        self.assertNotIn("zq-7731", raw)
        self.assertNotIn("updatedInput", raw)
        self.assertTrue(turn._read_turn(turn._session_file(self.V, A)).get("secret_shown"))
        self.assertFalse(turn._read_turn(turn._session_file(self.V, B)).get("secret_shown"))


class TurnNote(Base):
    def test_10_note_and_redact_go_to_own_turn(self):
        self.prompt(A, "我的密碼是 abc")
        self.prompt(B, "你好")
        self.assertEqual(self.kb("turn", "note", "記了一筆", sid=A).returncode, 0)
        self.assertEqual(self.kb("turn", "redact", "我的密碼是（遮）", sid=A).returncode, 0)
        a = turn._read_turn(turn._session_file(self.V, A))
        b = turn._read_turn(turn._session_file(self.V, B))
        self.assertEqual((a["note"], a["prompt_head"]), ("記了一筆", "我的密碼是（遮）"))
        self.assertEqual((b["note"], b["prompt_head"]), ("", "你好"))


from tests import test_lib_purge as _purge  # noqa: E402  只借 setUp 與小工具，不把那邊的測試帶進來


class PurgeWrites(unittest.TestCase):
    """裁定 13：kb folders purge 把 writes.jsonl 裡那些卡與那夾的路徑整行拿掉。"""
    setUp = _purge.Purge.setUp
    tearDown = _purge.Purge.tearDown
    write_synthesis = _purge.Purge.write_synthesis
    exclude = _purge.Purge.exclude

    def test_purge_drops_writes_rows(self):
        V = self.V
        t = turn.start(V, None, "")["turn"]
        turn.backup(V, self.card_rel, t)
        turn.backup(V, self.card_rel, t)  # 同回合再寫一次：writes.jsonl
        turn.backup(V, "系統/日程.md", t)
        turn.backup(V, "系統/日程.md", t)
        self.assertEqual({w["path"] for w in turn.writes(V, t)}, {self.card_rel, "系統/日程.md"})
        turn.start(V, None, "")
        self.exclude()
        self.write_synthesis("信義王現在很好。")
        code, out = _purge.kb("folders", "purge", "客戶案件/私人", "--vault", str(V))
        self.assertEqual(code, 0, out)
        rows = [ln for d in (Path(V) / ".system/versions").iterdir() if (d / "writes.jsonl").is_file()
                for ln in (d / "writes.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertFalse([ln for ln in rows if "私人" in ln or self.card_rel in ln], rows)
        self.assertEqual([w["path"] for w in turn.writes(V, t)], ["系統/日程.md"])  # 別的路徑留著


if __name__ == "__main__":
    unittest.main()
