"""hooks/turn.py 黑箱：subprocess 餵 UserPromptSubmit payload。開回合、task-notification 不開、非使用者來源不開、
不在知識庫不開、壞 JSON exit 0 無輸出。"""
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from datetime import date, timedelta

from tests._guard_fixture import ROOT, make_vault
from kb._lib import journal  # noqa: E402

HOOK = ROOT / "hooks" / "turn.py"
SID = "test-sid"


def run_hook(data, cwd=None):
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))
    raw = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return subprocess.run([sys.executable, str(HOOK)], input=raw, capture_output=True, text=True,
                          encoding="utf-8", cwd=str(cwd or ROOT), env=env)


def settle(vault):
    """把假知識庫的來源套進清冊：每句開頭才不會印變動行（放寬丙 3b 把變動行挪到每句開頭）；今天那批記成做過，
    不印每天第一句的「製作中」（D-525，清冊裡的檔都還沒卡）。"""
    from datetime import date
    from kb._lib import env, inventory, sources as sources_lib, turn
    inventory.apply(vault, inventory.scan(vault, sources_lib.load(vault)), turn.start(vault, None, "")["turn"])
    env.set_daily_done(vault, date.today().isoformat())
    shutil.rmtree(vault / ".system" / "turns")  # 還沒有任何回合的樣子


def prompt_payload(cwd, prompt, **extra):
    data = {"session_id": SID, "cwd": str(cwd), "prompt": prompt, "hook_event_name": "UserPromptSubmit"}
    data.update(extra)
    return data


class TurnHook(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        self.turns = self.V / ".system" / "turns"
        settle(self.V)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_opens_turn_silently(self):
        r = run_hook(prompt_payload(self.V, "改一下"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        sess = json.loads((self.turns / f"{SID}.json").read_text(encoding="utf-8"))
        cur = json.loads((self.turns / "current.json").read_text(encoding="utf-8"))
        self.assertEqual(sess["turn"], cur["turn"])
        self.assertEqual(sess["prompt_head"], "改一下")
        self.assertNotIn("approved", sess)

    def test_61_63_prompt_head_is_masked_everywhere(self):
        """D-081、B-027：帳密不進回合檔；versions list 印的問也是遮過的。"""
        r = run_hook(prompt_payload(self.V, "幫我登入 ERP，帳號 jie 密碼 abc123"))
        self.assertEqual(r.returncode, 0, r.stderr)
        sess = json.loads((self.turns / f"{SID}.json").read_text(encoding="utf-8"))
        self.assertEqual(sess["prompt_head"], "幫我登入 ERP，帳號 ███ 密碼 ███")  # D-187：只遮值
        self.assertNotIn("jie", sess["prompt_head"])
        from kb._lib import turn
        turn.backup(self.V, "案子/信義王/信義王.md", sess["turn"])
        kb = ROOT / "scripts" / "kb.py"
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))
        out = subprocess.run([sys.executable, str(kb), "versions", "list"], capture_output=True, text=True, encoding="utf-8",
                             cwd=str(self.V), env=env).stdout
        self.assertIn("███", out)
        self.assertNotIn("abc123", out)
        for p in (self.V / ".system").rglob("*"):
            if p.is_file():
                self.assertNotIn("abc123", p.read_text(encoding="utf-8", errors="ignore"), p)

    def test_task_notification_does_not_open(self):
        r = run_hook(prompt_payload(self.V, "<task-notification>done</task-notification>"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertFalse(self.turns.exists())

    def test_cross_session_message_does_not_open(self):
        """確認後裁定 L-3：跨 session 訊息不是客戶的話，不開回合（標頭不能變成 prompt_head 印給客戶）。"""
        r = run_hook(prompt_payload(self.V, '<cross-session-message from="uds:x" from-name="llm-wiki-j-51">改一下</cross-session-message>'))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertFalse(self.turns.exists())

    def test_system_reminder_does_not_open(self):
        r = run_hook(prompt_payload(self.V, "  <system-reminder>\n內部提醒\n</system-reminder>"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertFalse(self.turns.exists())

    def test_non_user_source_does_not_open(self):
        r = run_hook(prompt_payload(self.V, "改一下", source="scheduled"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.turns.exists())
        for ok in ("user", "sdk"):
            r = run_hook(prompt_payload(self.V, "改一下", source=ok))
            self.assertTrue((self.turns / f"{SID}.json").exists(), ok)

    def test_outside_vault_does_nothing(self):
        r = run_hook(prompt_payload(self.tmp, "改一下"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        self.assertFalse(self.turns.exists())
        self.assertFalse((self.tmp / ".system").exists())

    def test_bad_json_is_silent_exit_0(self):
        r = run_hook("not json", cwd=self.V)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "")
        lines = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].split("\t")[1], "turn")  # 第一輪 L7：第二欄是哪支 hook

    def test_bad_json_outside_vault_is_silent_exit_0(self):
        r = run_hook("[1, 2]")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "")

    def test_registered_in_hooks_json_as_user_prompt_submit(self):
        cfg = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        groups = cfg["hooks"]["UserPromptSubmit"]
        cmds = [h["command"] for g in groups for h in g["hooks"]]
        self.assertEqual(len(cmds), 1, cmds)
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/hooks/turn.py", cmds[0])
        self.assertEqual(groups[0]["hooks"][0]["timeout"], 5)
        self.assertEqual(len(cfg["hooks"]["PreToolUse"]), 1)  # PreToolUse 不動

    def journal_rows(self):
        return journal.read_lines(self.V, date.today().strftime("%Y-%m"))

    def md(self):
        return journal.md_path(self.V, date.today().strftime("%Y-%m")).read_text(encoding="utf-8")

    def errors(self):
        p = self.V / ".system" / "hook-errors.log"
        return p.read_text(encoding="utf-8").splitlines() if p.exists() else []

    def test_journal_line_opened_with_in_progress_md(self):
        """工作日誌（D-083）：開口就寫一行 done false；md 頂端三行、那段結果「（還沒結束）」。"""
        r = run_hook(prompt_payload(self.V, "改一下"))
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)
        rows = self.journal_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["kind"], rows[0]["prompt"], rows[0]["done"]), ("turn", "改一下", False))
        sess = json.loads((self.turns / f"{SID}.json").read_text(encoding="utf-8"))
        self.assertEqual((sess["note"], sess["done"]), ("", False))
        self.assertEqual(rows[0]["turn"], sess["turn"])
        md = self.md().splitlines()
        self.assertEqual(md[2:5], list(journal.HEADER_LINES))
        self.assertIn("- 結果：（還沒結束）", md)

    def test_journal_prompt_is_masked(self):
        run_hook(prompt_payload(self.V, "幫我登入 ERP，帳號 jie 密碼 abc123"))
        self.assertEqual(self.journal_rows()[0]["prompt"], "幫我登入 ERP，帳號 ███ 密碼 ███")

    def test_acceptance_29_prompt_value_after_blank_line_is_masked(self):
        """測試後修正 M2：回合檔、versions/<回合>/turn.json、jsonl 三處都 grep 不到值。"""
        run_hook(prompt_payload(self.V, "幫我登入，密碼如下：\n\nabc123"))
        sess = json.loads((self.turns / f"{SID}.json").read_text(encoding="utf-8"))
        from kb._lib import turn
        turn.before_write(self.V, str(self.V / "案子" / "信義王" / "信義王.md"), str(self.V), "Z1", SID)
        meta = self.V / ".system" / "versions" / sess["turn"] / "turn.json"
        self.assertTrue(meta.is_file())
        for p in (self.turns / f"{SID}.json", meta, journal.jsonl_path(self.V, date.today().strftime("%Y-%m"))):
            self.assertNotIn("abc123", p.read_text(encoding="utf-8"), p)
        self.assertEqual(sess["prompt_head"], "幫我登入，密碼如下： ███")

    def test_previous_turn_without_stop_is_flushed_as_interrupted(self):
        run_hook(prompt_payload(self.V, "第三句"))
        run_hook(prompt_payload(self.V, "第四句"))
        rows = {r["prompt"]: r for r in self.journal_rows()}
        self.assertEqual(len(rows), 2)
        third = rows["第三句"]
        self.assertTrue(third["done"])
        self.assertTrue(third["interrupted"])
        self.assertEqual(third["result"], "（回答被中斷，沒有結果）")
        self.assertEqual((third["note"], third["note_by"], third["changed"]), ("沒有改動", "program", []))
        self.assertFalse(rows["第四句"]["done"])
        md = self.md()
        self.assertLess(md.index("第四句"), md.index("第三句"))  # 最新在上

    def test_acceptance_26_flush_keeps_ai_note(self):
        """驗收 26（D-084）：中斷前模型叫過 turn note，補記的做了用它、note_by ai。"""
        run_hook(prompt_payload(self.V, "第一句"))
        kb = ROOT / "scripts" / "kb.py"
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))
        r = subprocess.run([sys.executable, str(kb), "turn", "note", "中斷前記的"], capture_output=True, text=True,
                           encoding="utf-8", cwd=str(self.V), env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        run_hook(prompt_payload(self.V, "第二句"))
        first = {r["prompt"]: r for r in self.journal_rows()}["第一句"]
        self.assertEqual((first["note"], first["note_by"], first["interrupted"]), ("中斷前記的", "ai", True))

    def test_old_turn_file_without_done_is_not_flushed(self):
        """疑義裁定 3：升級前的回合檔沒有 done 鍵，不補記。"""
        self.turns.mkdir(parents=True)
        old = {"schema_version": 1, "turn": "20261014-100000-test", "session_id": SID,
               "started": "2026-10-14T10:00:00", "prompt_head": "舊的", "approved": False}
        (self.turns / f"{SID}.json").write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
        run_hook(prompt_payload(self.V, "新的"))
        self.assertNotIn(old["turn"], [r["turn"] for r in journal.read_lines(self.V, "2026-10")])
        self.assertEqual([r["prompt"] for r in self.journal_rows()], ["新的"])

    def test_prompt_head_length_reads_config(self):
        """B-028 第 2 項：150 字整句留著；客戶端 prompt_head_max 10 就截 10。"""
        run_hook(prompt_payload(self.V, "長" * 150))
        sess = json.loads((self.turns / f"{SID}.json").read_text(encoding="utf-8"))
        self.assertEqual(sess["prompt_head"], "長" * 150)
        self.assertEqual(self.journal_rows()[0]["prompt"], "長" * 150)
        (self.V / ".system" / "config.json").write_text(json.dumps({"prompt_head_max": 10}), encoding="utf-8")
        run_hook(prompt_payload(self.V, "短" * 50))
        sess = json.loads((self.turns / f"{SID}.json").read_text(encoding="utf-8"))
        self.assertEqual(sess["prompt_head"], "短" * 10)

    def test_bad_journal_line_is_kept_and_logged(self):
        run_hook(prompt_payload(self.V, "第一句"))
        p = journal.jsonl_path(self.V, date.today().strftime("%Y-%m"))
        p.write_text(p.read_text(encoding="utf-8") + "{bad\n", encoding="utf-8")
        sess = json.loads((self.turns / f"{SID}.json").read_text(encoding="utf-8"))
        sess["done"] = True  # 前一句已結束，只看開口那一次讀檔
        (self.turns / f"{SID}.json").write_text(json.dumps(sess, ensure_ascii=False), encoding="utf-8")
        r = run_hook(prompt_payload(self.V, "第二句"))
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertIn("{bad", p.read_text(encoding="utf-8").splitlines())
        self.assertEqual(len(self.errors()), 1)
        self.assertEqual([r["prompt"] for r in self.journal_rows()], ["第一句", "第二句"])
        self.assertIn("第二句", self.md())

    def test_held_lock_still_opens_turn_and_logs(self):
        """驗收 18：鎖被占著（mtime 現在）回合照開、日誌沒新行、log 一行、4 秒內結束；鎖殘留 60 秒前就清掉照寫。"""
        p = journal.jsonl_path(self.V, date.today().strftime("%Y-%m"))
        p.parent.mkdir(parents=True)
        lock = p.with_name(p.name + ".lock")
        lock.write_text("", encoding="utf-8")
        t0 = time.time()
        r = run_hook(prompt_payload(self.V, "鎖住了"))
        elapsed = time.time() - t0
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertLess(elapsed, 4.5)
        self.assertTrue((self.turns / f"{SID}.json").exists())
        self.assertEqual(self.journal_rows(), [])
        self.assertEqual(len(self.errors()), 1)
        old = time.time() - 60
        os.utime(lock, (old, old))
        run_hook(prompt_payload(self.V, "鎖舊了"))
        self.assertIn("鎖舊了", [r["prompt"] for r in self.journal_rows()])

    def test_acceptance_32_unfinished_previous_and_held_lock_waits_once(self):
        """驗收 32（L1）：前一回合 done false 時鎖被占著，補記與開口同一把鎖只等一次，5 秒內結束、log 一行、回合照開。"""
        run_hook(prompt_payload(self.V, "第一句"))
        p = journal.jsonl_path(self.V, date.today().strftime("%Y-%m"))
        lock = p.with_name(p.name + ".lock")
        lock.write_text("", encoding="utf-8")
        t0 = time.time()
        r = run_hook(prompt_payload(self.V, "第二句"))
        self.assertLess(time.time() - t0, 4.5)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        sess = json.loads((self.turns / f"{SID}.json").read_text(encoding="utf-8"))
        self.assertEqual(sess["prompt_head"], "第二句")
        self.assertEqual(len(self.errors()), 1)
        lock.unlink()

    def test_second_prompt_opens_new_turn(self):
        run_hook(prompt_payload(self.V, "第一句"))
        first = json.loads((self.turns / f"{SID}.json").read_text(encoding="utf-8"))["turn"]
        run_hook(prompt_payload(self.V, "第二句"))
        second = json.loads((self.turns / f"{SID}.json").read_text(encoding="utf-8"))
        self.assertNotEqual(first, second["turn"])
        self.assertEqual(second["prompt_head"], "第二句")


STOPPED = "上一句的整理被你停了：這個對話不再自動整理，你說整理才做；回答用現有的資料。"


class IngestStopped(unittest.TestCase):
    """answer 第 9 點、驗收 12：上一句跑過 kb cards todo（回合記 ingest）又沒等到 Stop → 這一句帶一次 additionalContext、
    session 檔記 ingest_stopped；第三句不再印；沒跑 todo 的中斷不印；壞檔照開回合、exit 0。"""

    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        self.sess = self.V / ".system" / "turns" / f"{SID}.json"
        settle(self.V)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def say(self, prompt):
        r = run_hook(prompt_payload(self.V, prompt))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def context(self, out):
        data = json.loads(out)
        self.assertEqual(data["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        return data["hookSpecificOutput"]["additionalContext"]

    def session(self):
        return json.loads(self.sess.read_text(encoding="utf-8"))

    def test_todo_then_interrupt_prints_once(self):
        self.assertEqual(self.say("信義王現在怎樣？"), "")
        kb = ROOT / "scripts" / "kb.py"
        r = subprocess.run([sys.executable, str(kb), "cards", "todo", "--json"], capture_output=True, text=True,
                           encoding="utf-8", cwd=str(self.V), env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.session()["ingest"])
        out = self.say("信義王現在怎樣？")
        self.assertEqual(self.context(out), STOPPED)
        out.encode("ascii")
        self.assertTrue(self.session()["ingest_stopped"])
        self.assertEqual(self.say("那大安陳呢？"), "")
        self.assertTrue(self.session()["ingest_stopped"], "同一個 session 一直記著")

    def test_finished_turn_with_ingest_does_not_print(self):
        from kb._lib import turn
        self.say("整理")
        turn.mark(self.V, "ingest")
        turn.set_done(self.V, SID)
        self.assertEqual(self.say("下一句"), "")

    def test_interrupt_without_todo_does_not_print(self):
        self.say("第一句")
        self.assertEqual(self.say("第二句"), "")
        self.assertNotIn("ingest_stopped", self.session())

    def test_hooks_json_description_mentions_it(self):
        """answer 測試後修正裁定 20（F-8）：hooks.json 的 description 補開場接著整理與按停止兩句。"""
        desc = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["description"]
        self.assertIn("每句開頭比對清冊印變動行與整理指示", desc)
        self.assertIn("整理中按了停止，這個對話不再自動整理", desc)

    def test_terminal_todo_does_not_mark(self):
        from kb._lib import turn
        turn.start(self.V, None, "")
        self.assertFalse(turn.mark(self.V, "ingest"))
        self.assertNotIn("ingest", json.loads((self.V / ".system" / "turns" / "current.json").read_text(encoding="utf-8")))

    def test_broken_session_file_still_opens_turn(self):
        self.say("第一句")
        self.sess.write_text("{bad", encoding="utf-8")
        self.assertEqual(self.say("第二句"), "")
        self.assertEqual(self.session()["prompt_head"], "第二句")


if __name__ == "__main__":
    unittest.main()


class AgentMessages(unittest.TestCase):
    """card-maker（桌面版 D2，驗收 10）：子代理交回的 <agent-message、VS Code 的 [SYSTEM NOTIFICATION 不開回合、日誌不多一段。"""

    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        self.turns = self.V / ".system" / "turns"
        self.J = journal.jsonl_path(self.V, date.today().strftime("%Y-%m"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_not_prompts(self):
        for text in ('<agent-message from="a0204e72">批次 b-1：做好 18、沒做成 2</agent-message>',
                     "[SYSTEM NOTIFICATION - NOT USER INPUT]\n<task-notification>done</task-notification>",
                     "  <task-notification>done</task-notification>"):
            r = run_hook(prompt_payload(self.V, text))
            self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)
            self.assertFalse(self.turns.exists(), text)
            self.assertFalse(self.J.exists(), text)

    def test_ordinary_prompt_still_opens(self):
        r = run_hook(prompt_payload(self.V, "整理到哪了？"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.turns.exists())


class Transcript(unittest.TestCase):
    """暫存區第 3 點：payload 有 transcript_path 就記進回合檔（kb intake --pasted 從那裡取貼的圖與文字）。"""

    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        self.turns = self.V / ".system" / "turns"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_transcript_path_recorded(self):
        r = run_hook(prompt_payload(self.V, "存起來", transcript_path="C:/x/sess.jsonl"))
        self.assertEqual(r.returncode, 0, r.stderr)
        sess = json.loads((self.turns / f"{SID}.json").read_text(encoding="utf-8"))
        self.assertEqual(sess["transcript"], "C:/x/sess.jsonl")

    def test_without_transcript_path_no_key(self):
        run_hook(prompt_payload(self.V, "存起來"))
        sess = json.loads((self.turns / f"{SID}.json").read_text(encoding="utf-8"))
        self.assertNotIn("transcript", sess)


class EachTurnChecks(unittest.TestCase):
    """放寬丙 3b（D-327）：變動以外的檢查挪到每句開頭；先比修改時間、沒變不讀；講過就不再印；每天第一句做日程。"""

    CARD = "檔案索引/公司行政/報稅時程表-647d76ee.md"
    TEXT = ("---" + chr(10) + "編號: f-647d76ee" + chr(10) + "標題: 報稅時程表" + chr(10) + "卡型: 表單" + chr(10) + "---" + chr(10)
            + "# 報稅時程表" + chr(10) + chr(10) + "- 總價 5.5 萬〔第 1 段〕" + chr(10))

    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        settle(self.V)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def say(self, prompt="問"):
        r = run_hook(prompt_payload(self.V, prompt))
        self.assertEqual(r.returncode, 0, r.stderr)
        if not r.stdout:
            return []
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"].split(chr(10))

    def test_daily_agenda_line_only_on_the_first_sentence_of_the_day(self):
        item = {"id": "a-00000001", "kind": "deadline", "start": None, "date": (date.today() - timedelta(days=3)).isoformat(),
                "ended": None, "time": None, "text": "事", "entities": [], "status": "open", "source": "confirmed",
                "origin": None, "lead_days": None, "created_turn": "t", "history": []}
        (self.V / ".system" / "agenda.json").write_text(json.dumps({"schema_version": 1, "items": [item]}), encoding="utf-8")
        from kb._lib import env as env_lib
        env_lib.set_daily_done(self.V, (date.today() - timedelta(days=1)).isoformat())  # settle 記成今天做過，這裡要今天還沒做
        first = self.say()
        self.assertTrue([ln for ln in first if ln.startswith("日程：逾期 1")], first)
        env = json.loads((self.V / ".system" / "env.json").read_text(encoding="utf-8"))
        self.assertEqual([m["daily_done"] for m in env["machines"].values()], [date.today().isoformat()])
        self.assertEqual(self.say(), [])
        # 昨天做的：換一天又做一次
        for m in env["machines"].values():
            m["daily_done"] = (date.today() - timedelta(days=1)).isoformat()
        (self.V / ".system" / "env.json").write_text(json.dumps(env), encoding="utf-8")
        self.assertTrue([ln for ln in self.say() if ln.startswith("日程：逾期 1")])

    def test_card_edit_line_once_then_quiet_until_changed_again(self):
        p = self.V / self.CARD
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.TEXT, encoding="utf-8", newline=chr(10))
        self.assertEqual(self.say(), [])  # 補基準
        time.sleep(0.05)
        p.write_text(self.TEXT.replace("5.5 萬", "6 萬"), encoding="utf-8", newline=chr(10))
        got = self.say()
        self.assertEqual(len([ln for ln in got if "kb cards edits" in ln]), 1, got)
        self.assertEqual(self.say(), [], "沒有新的修改：比修改時間後不讀卡、也不重印")
        checks = json.loads((self.V / ".system" / "turns" / f"{SID}.json").read_text(encoding="utf-8"))["checks"]
        self.assertIn("cards", checks["stamps"])

    def test_moved_line_once_per_item_and_folder_counts_once(self):
        """放寬丙 5-3：認出搬動印一行（整夾算一件）；同一件同一個對話只講一次，新的一件再印。"""
        shutil.copy2(self.raw / "行政" / "請款" / "r.docx", self.raw / "行政" / "請款" / "r2.docx")
        settle(self.V)
        (self.raw / "行政" / "2025 結案").mkdir()
        shutil.move(self.raw / "行政" / "請款", self.raw / "行政" / "2025 結案" / "請款")
        got = self.say()
        lines = [ln for ln in got if "kb changes --moved" in ln]
        self.assertEqual(len(lines), 1, got)
        self.assertTrue(lines[0].startswith("有 1 件搬動：跑 kb changes --moved --json，照內容判斷"), lines[0])
        self.assertIn("看完 changes --moved 之後要讀搬過的檔，再跑 kb inventory scan", lines[0])  # 刪綜合卡說一聲 裁定 6：清冊還是舊位置，用編號讀不到
        self.assertEqual([ln for ln in self.say() if "kb changes --moved" in ln], [])
        shutil.move(self.raw / "客戶案件" / "a.txt", self.raw / "行政" / "a.txt")
        again = [ln for ln in self.say() if "kb changes --moved" in ln]
        self.assertEqual(len(again), 1)
        self.assertTrue(again[0].startswith("有 1 件搬動："), again[0])

    def test_no_session_id_means_no_checks(self):
        (self.raw / "客戶案件" / "新.txt").write_text("新", encoding="utf-8")
        r = run_hook({"cwd": str(self.V), "prompt": "問", "hook_event_name": "UserPromptSubmit"})
        self.assertEqual((r.returncode, r.stdout), (0, ""))
