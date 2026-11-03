"""hooks/session.py 黑箱：subprocess 餵 SessionStart payload（D-087、D-060）。第一行 kb 指令前綴、core.md 全文接在空行後、
compact 才有摺疊那行、不在知識庫或壞 JSON 無輸出 exit 0、stdout 純 ASCII、2 秒內、hooks.json 註冊。
清冊題：變動行三種（無、有數字、incomplete）、找不到來源第一次印第二次不印、清冊壞掉其他行照印且 log 一行。"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from tests._guard_fixture import ROOT, make_vault

HOOK = ROOT / "hooks" / "session.py"
CORE = ROOT / "rules" / "core.md"
KB_LINE = f'【wiki-with-willy】kb 指令：python "{ROOT.as_posix()}/scripts/kb.py" <子命令>'
COMPACT_LINE = "對話剛摺疊，規則已重新帶入；做到一半的事以工作日誌為準。"
ERROR_LINE = "【wiki-with-willy】開場程式出錯（{}），詳見 .system/hook-errors.log；跑 kb selftest 看原因，修好之前不改任何檔。"  # 即 ERROR_LINE_FATAL


def run(data, cwd=None):
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))
    raw = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return subprocess.run([sys.executable, str(HOOK)], input=raw, capture_output=True, text=True,
                          encoding="utf-8", cwd=str(cwd or ROOT), env=env)


TURN_HOOK = ROOT / "hooks" / "turn.py"
_SID = [0]


def turn_lines(cwd, sid=None):
    """每句開頭給 AI 的行（放寬丙 3b：變動、卡、標籤、設定檔、找不到的來源、整理提示都挪到 hooks/turn.py）。
    每次換一個 session，不被「這個對話講過了」擋掉。"""
    _SID[0] += 1
    data = {"session_id": sid or f"t{_SID[0]}", "cwd": str(cwd), "prompt": "問", "hook_event_name": "UserPromptSubmit"}
    r = subprocess.run([sys.executable, str(TURN_HOOK)], input=json.dumps(data, ensure_ascii=False), capture_output=True,
                       text=True, encoding="utf-8", cwd=str(cwd), env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)))
    assert r.returncode == 0, r.stderr
    if not r.stdout:
        return []
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"].split("\n")


def run_turn_ctx(data):
    """給別的測試檔用：跟 run 一樣收 payload（只用 cwd），但跑 hooks/turn.py（每句開頭，放寬丙 3b），stdout 沒東西時補一個空的
    additionalContext，呼叫端照舊 json.loads。每次換一個 session。"""
    import types
    _SID[0] += 1
    turn_data = {"session_id": f"tc{_SID[0]}", "cwd": data["cwd"], "prompt": "問", "hook_event_name": "UserPromptSubmit"}
    r = subprocess.run([sys.executable, str(TURN_HOOK)], input=json.dumps(turn_data, ensure_ascii=False), capture_output=True,
                       text=True, encoding="utf-8", cwd=str(data["cwd"]), env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)))
    out = r.stdout or json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": ""}})
    return types.SimpleNamespace(returncode=r.returncode, stdout=out, stderr=r.stderr)


def payload(cwd, source="startup"):
    data = {"session_id": "abc", "transcript_path": "x.jsonl", "cwd": str(cwd), "hook_event_name": "SessionStart"}
    if source is not None:
        data["source"] = source
    return data


class SessionHook(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def context(self, source="startup"):
        r = run(payload(self.V, source))
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")
        return out["hookSpecificOutput"]["additionalContext"]

    def test_startup_first_line_is_kb_prefix_and_path_exists(self):
        ctx = self.context("startup")
        self.assertEqual(ctx.splitlines()[0], KB_LINE)
        self.assertTrue((ROOT / "scripts" / "kb.py").is_file())

    def test_core_full_text_after_blank_line(self):
        core = CORE.read_text(encoding="utf-8")
        ctx = self.context("startup")
        self.assertTrue(ctx.endswith("\n\n" + core), ctx[:200])
        status = ctx[:-len("\n\n" + core)].split("\n")  # 清冊審閱裁定 10：kb 行與 core 之間允許多狀態行
        self.assertEqual(status[0], KB_LINE)
        self.assertTrue(all(line for line in status), status)

    def test_compact_adds_second_line(self):
        status = self.context("compact").split("\n\n", 1)[0].split("\n")
        self.assertEqual((status[0], status[-1]), (KB_LINE, COMPACT_LINE))

    def test_other_sources_have_no_compact_line(self):
        for source in ("startup", "resume", "clear", None):
            with self.subTest(source=source):
                self.assertNotIn(COMPACT_LINE, self.context(source))

    def test_outside_vault_silent_exit_0(self):
        r = run(payload(ROOT))
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)

    def test_bad_json_silent_exit_0_and_logged(self):
        r = run("not json", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)
        lines = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[-1].split("\t")[1], "session")

    def test_error_after_vault_found_prints_error_line_and_logs(self):
        """第一輪 D2：找到知識庫之後出錯，除了寫 log，還要印一行出錯的 additionalContext（失敗明講）。
        複製 hooks/session.py、scripts/ 與 manifest 到沒有 rules/ 的暫存夾，讀 core.md 會 FileNotFoundError。"""
        plugin = self.tmp / "plugin"
        (plugin / "hooks").mkdir(parents=True)
        shutil.copy2(HOOK, plugin / "hooks" / "session.py")
        shutil.copy2(HOOK.parent / "_checks.py", plugin / "hooks" / "_checks.py")
        shutil.copytree(ROOT / "scripts", plugin / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / ".claude-plugin", plugin / ".claude-plugin")
        shutil.copytree(ROOT / "config", plugin / "config")  # 清冊題：變動行要讀設定，缺它會多一行 log
        raw = json.dumps(payload(self.V), ensure_ascii=False)
        r = subprocess.run([sys.executable, str(plugin / "hooks" / "session.py")], input=raw, capture_output=True,
                           text=True, encoding="utf-8", cwd=str(self.V), env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin)))
        self.assertEqual(r.returncode, 0, r.stderr)
        r.stdout.encode("ascii")
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SessionStart")
        self.assertEqual(out["additionalContext"], ERROR_LINE.format("FileNotFoundError"))
        lines = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].split("\t")[1], "session")

    def test_broken_stdout_pipe_still_exit_0(self):
        """第一輪低項：stdout 讀端先關掉（pipe 斷），write／flush 失敗也要 exit 0、stderr 乾淨（結束時的補 flush 不能再炸）。"""
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))
        p = subprocess.Popen([sys.executable, str(HOOK)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, cwd=str(self.V), env=env)
        p.stdout.close()
        p.stdin.write(json.dumps(payload(self.V)).encode("utf-8"))
        p.stdin.close()
        err = p.stderr.read()
        p.stderr.close()
        self.assertEqual(p.wait(timeout=10), 0, err)
        self.assertEqual(err, b"")

    def test_stdout_is_pure_ascii(self):
        r = run(payload(self.V, "compact"))
        self.assertTrue(r.stdout)
        r.stdout.encode("ascii")

    def test_single_run_within_2_seconds(self):
        start = time.monotonic()
        r = run(payload(self.V))
        self.assertEqual(r.returncode, 0)
        self.assertLess(time.monotonic() - start, 2.0)

    def test_registered_in_hooks_json_as_session_start(self):
        cfg = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        groups = cfg["hooks"]["SessionStart"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["matcher"], "startup|resume|clear|compact")
        hooks = groups[0]["hooks"]
        self.assertEqual(len(hooks), 1)
        self.assertEqual(hooks[0]["command"], 'python "${CLAUDE_PLUGIN_ROOT}/hooks/session.py"')
        self.assertEqual(hooks[0]["timeout"], 10)
        self.assertTrue(cfg["description"].startswith("開場帶入核心規則與 kb 指令前綴；"))
        self.assertEqual(len(cfg["hooks"]), 8)  # card-maker 加 SubagentStart、SubagentStop；B 段第 6 步加 SessionEnd


KB = ROOT / "scripts" / "kb.py"
CHANGES_INCOMPLETE = "變動還沒比完：下一句接著比，不用跟客戶提。"
WIP = "有 {} 份新放或改過（製作中）：不整理、不跟客戶提；先跑 kb inventory scan 記進清冊；問到這幾份讀原檔答。"  # D-525
MISSING = "有 {} 份不見：跑 kb inventory scan 再 kb cards sync 拿掉卡；不派整理、不做卡。"
MD = ("有 {} 份 md 新放或改過（{}）：先跑 kb inventory scan，再照 ingest 只整理這幾份"
      "（kb cards dispatch --ids <編號>，編號看 kb cards todo --json）；其他製作中的不一起整理。")
DRIFT = "實體夾有變 {}：跑 kb cards todo --json，只照 asks 問實體夾那題，不做卡。"  # D-525 裁定 1
CHANGE_HEAD = re.compile(r"^(有 \d+ 份|實體夾有變 |變動還沒比完)")
SHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def big_xlsx(path, rows, first=1):
    """一張工作表、5 欄數字；first 改 A1 的值（「改一格」）。900k 列約 27 MB，不設時間上限抽字要 14 秒（測試報告發現一的量級）。"""
    import zipfile
    parts = [f'<?xml version="1.0"?><worksheet xmlns="{SHEET_NS}"><sheetData>']
    for r in range(1, rows + 1):
        a = first if r == 1 else r
        parts.append(f'<row r="{r}"><c r="A{r}"><v>{a}</v></c><c r="B{r}"><v>{r * 2}</v></c><c r="C{r}"><v>{r * 3}</v></c>'
                     f'<c r="D{r}"><v>{r * 4}</v></c><c r="E{r}"><v>{r * 5}</v></c></row>')
    parts.append("</sheetData></worksheet>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", "".join(parts))


class OpeningBigOoxml(unittest.TestCase):
    """審閱裁定 34、測試報告發現一：11 MB 級的 xlsx 改一格後，開場 hook 總時間在 10 秒（SessionStart 逾時）內。"""

    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_big_xlsx_one_cell_changed_opening_within_10_seconds(self):
        from kb._lib import inventory
        from kb._lib import sources as sources_lib

        p = self.raw / "客戶案件" / "大表.xlsx"
        big_xlsx(p, 900_000)
        self.assertGreater(p.stat().st_size, 10_000_000)
        real = inventory.content_fp.text_fingerprint
        inventory.content_fp.text_fingerprint = lambda path, **kw: None  # 入冊這步不是要量的，跳過抽字省時間
        try:
            report = inventory.scan(self.V, sources_lib.load(self.V))
        finally:
            inventory.content_fp.text_fingerprint = real
        from kb._lib import turn
        inventory.apply(self.V, report, turn.start(self.V, None, "")["turn"])
        big_xlsx(p, 900_000, first=999)
        st = p.stat()
        os.utime(p, (st.st_atime, st.st_mtime + 100))
        start = time.monotonic()
        lines = turn_lines(self.V)  # 變動比對挪到每句開頭（放寬丙 3b）
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 10.0, f"每句開頭花了 {elapsed:.1f} 秒")
        self.assertTrue(set(lines) & {CHANGES_INCOMPLETE, WIP.format(1)}, lines)
        r = run(payload(self.V))  # 開場本身不比對、不印變動
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertTrue(ctx.endswith(CORE.read_text(encoding="utf-8")))


class OpeningInventory(unittest.TestCase):
    """清冊題第 7 點：line_changes、line_missing_sources 共用一次快速 scan；每行各自 try（I-046）。"""

    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        # fixture 的 r.docx 與 合約.docx 都是 0 位元組，同一份內容會併成一筆；給它自己的內容才測得到「不見」
        (self.raw / "行政" / "請款" / "r.docx").write_bytes(b"PK fake request")
        r = subprocess.run([sys.executable, str(KB), "inventory", "scan"], capture_output=True, text=True,
                           encoding="utf-8", cwd=str(self.V), env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def status(self, source="startup"):
        r = run(payload(self.V, source))
        self.assertEqual(r.returncode, 0, r.stderr)
        r.stdout.encode("ascii")
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        lines = ctx.split("\n\n", 1)[0].split("\n")
        more = turn_lines(self.V)  # 開場之後的第一句：每句開頭的行排在開場的行後面（摺疊行仍是最後一行）
        return lines[:-1] + more + lines[-1:] if lines[-1] == COMPACT_LINE else lines + more

    def change_lines(self, lines):
        return [ln for ln in lines if CHANGE_HEAD.match(ln)]

    def test_no_change_no_line(self):
        self.assertEqual(self.change_lines(self.status()), [])

    def test_counts_line(self):
        (self.raw / "客戶案件" / "新.txt").write_text("新\n", encoding="utf-8")
        (self.raw / "客戶案件" / "a.txt").write_text("改過了，長度不一樣\n", encoding="utf-8")
        (self.raw / "行政" / "請款" / "r.docx").unlink()
        self.assertEqual(self.change_lines(self.status()), [WIP.format(2), MISSING.format(1)])

    def test_moves_and_duplicates_are_not_counted(self):
        shutil.copy2(self.raw / "客戶案件" / "a.txt", self.raw / "客戶案件" / "a 副本.txt")
        (self.raw / "行政" / "請款" / "r.docx").rename(self.raw / "行政" / "r.docx")
        self.assertEqual(self.change_lines(self.status()), [])

    def test_never_scanned_vault_counts_everything_as_new(self):
        """審閱裁定 10：沒有清冊等於全部新增。"""
        (self.V / ".system" / "inventory.json").unlink()
        lines = self.change_lines(self.status())
        self.assertRegex(lines[0], r"^有 [1-9]\d* 份新放或改過（製作中）：")
        self.assertTrue(all(ln.startswith("有 ") and "不見" not in ln for ln in lines), lines)

    def test_incomplete_line(self):
        # 每句開頭的比對用自己的上限（放寬丙）：讀取上限 1 位元組，改過的檔算不了指紋就是沒比完
        (self.V / ".system" / "config.json").write_text(json.dumps({"turn_scan_hash_budget_bytes": 1}), encoding="utf-8")
        (self.raw / "客戶案件" / "a.txt").write_text("改過了，長度不一樣" + chr(10), encoding="utf-8")
        self.assertEqual(self.change_lines(self.status()), [CHANGES_INCOMPLETE])

    def test_missing_source_reported_once_then_cleared(self):
        (self.raw / "客戶案件").rename(self.raw / "客戶案件_舊")
        line = "這台電腦找不到來源「客戶案件」：跑 kb folders locate <別名> 自己找，找到就 kb folders relocate 接上、說一聲；找不到才問使用者。"
        self.assertIn(line, self.status())
        env_json = json.loads((self.V / ".system" / "env.json").read_text(encoding="utf-8"))
        self.assertEqual([list(m["missing_sources_reported"]) for m in env_json["machines"].values()], [["src-3f9a"]])
        lines = self.status()
        self.assertNotIn(line, lines)
        self.assertEqual(self.change_lines(lines), [], "根找不到的來源底下不算不見")
        (self.raw / "客戶案件_舊").rename(self.raw / "客戶案件")
        self.assertNotIn(line, self.status())
        env_json = json.loads((self.V / ".system" / "env.json").read_text(encoding="utf-8"))
        self.assertEqual([m["missing_sources_reported"] for m in env_json["machines"].values()], [{}])
        (self.raw / "客戶案件").rename(self.raw / "客戶案件_舊")
        self.assertIn(line, self.status(), "又失蹤再報一次")

    def test_two_missing_sources_joined(self):
        (self.raw / "客戶案件").rename(self.raw / "客戶案件_舊")
        (self.raw / "行政").rename(self.raw / "行政_舊")
        self.assertIn("這台電腦找不到來源「客戶案件」、「行政」：跑 kb folders locate <別名> 自己找，找到就 kb folders relocate 接上、說一聲；找不到才問使用者。", self.status())

    def test_many_missing_sources_list_three_and_count(self):
        """審閱裁定 32：最多列 3 個別名，再多寫「等 N 個」；整段仍在 400 字內、全部都記成報過。"""
        p = self.V / ".system" / "sources.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        for i in range(5):
            data["sources"].append({"id": f"src-a{i:03d}", "alias": f"很長很長的外接硬碟資料夾第{i}號", "spec": f"../沒有/{i}",
                                    "excludes": []})
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        lines = self.status("compact")
        line = [ln for ln in lines if "找不到來源" in ln]
        self.assertEqual(line, ["這台電腦找不到來源「很長很長的外接硬碟資料夾第0號」、「很長很長的外接硬碟資料夾第1號」、"
                                "「很長很長的外接硬碟資料夾第2號」等 5 個：跑 kb folders locate <別名> 自己找，找到就 kb folders relocate 接上、說一聲；找不到才問使用者。"])
        self.assertLessEqual(len("\n".join(lines)), 400)
        self.assertLessEqual(len(lines), 8)
        env_json = json.loads((self.V / ".system" / "env.json").read_text(encoding="utf-8"))
        self.assertEqual(len(next(iter(env_json["machines"].values()))["missing_sources_reported"]), 5)

    def test_broken_inventory_other_lines_still_printed_and_one_log_line(self):
        (self.V / ".system" / "inventory.json").write_text("{bad", encoding="utf-8")
        lines = self.status("compact")
        self.assertEqual(lines[0], KB_LINE)
        self.assertEqual(lines[-1], COMPACT_LINE)
        self.assertEqual(self.change_lines(lines), [])
        self.assertFalse(any("找不到來源" in ln for ln in lines))
        log = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0].split("\t")[1], "turn")

    def test_opening_writes_only_env_json(self):
        (self.raw / "客戶案件").rename(self.raw / "客戶案件_舊")
        (self.raw / "行政" / "請款" / "r.docx").unlink()

        def stamps():
            return {p.relative_to(self.V).as_posix(): p.stat().st_mtime_ns
                    for p in (self.V / ".system").rglob("*") if p.is_file()}
        before = stamps()
        self.status()
        after = stamps()
        changed = {k for k in after if before.get(k) != after[k]}  # 每句開頭的 hook 還會開回合（turns、journal、renders），檢查本身只讀
        self.assertEqual({k for k in changed if not k.startswith((".system/turns/", ".system/journal/", ".system/renders", ".system/versions/"))},
                         {".system/env.json", ".system/vault.json", ".system/upgrade-history.json"})


class OpeningWip(unittest.TestCase):
    """D-525 第 1、8 點與裁定 3、驗收 2、6：新放、改過的檔（md 以外）印製作中那行，不叫整理、不帶份數上限；同一份同一個對話只講一次；
    md 照舊叫整理那幾份（按過停止不印）；不見照舊叫 scan、sync。"""

    setUp = OpeningInventory.setUp
    tearDown = OpeningInventory.tearDown
    status = OpeningInventory.status
    change_lines = OpeningInventory.change_lines

    def hint_lines(self, lines):
        return [ln for ln in lines if "照 ingest" in ln or "ingest skill" in ln]

    def skip_all(self):
        """清冊每份都記成依設定不整理：沒有還沒整理的（D-161 之前「沒變動」的樣子）。"""
        p = self.V / ".system" / "inventory.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        for e in data["entries"]:
            e["skip_kind"] = "請款"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_no_change_no_hint(self):
        self.skip_all()
        lines = self.status()
        self.assertEqual(self.hint_lines(lines), [])
        self.assertEqual([ln for ln in lines if ln.startswith(("還有 ", "製作中 "))], [])

    def test_unsorted_without_change_prints_nothing(self):
        """放寬丙 3（D-310(2)）：沒有新變動、清冊還有沒做成卡的 → 不報「還有 N 份沒整理完」，也沒有整理指示。"""
        sys.path.insert(0, str(ROOT / "scripts"))
        from kb._lib import cards
        self.assertGreater(cards.unsorted(self.V), 0)
        lines = self.status()
        self.assertEqual([ln for ln in lines if "沒整理完" in ln or "要跟著搬" in ln or "要改寫" in ln], [])
        self.assertEqual(self.hint_lines(lines), [])
        self.assertEqual(self.change_lines(lines), [])

    def stop_session(self, sid="abc"):
        """sid 那個對話在上一句按過停止：session 檔記著 ingest_stopped。"""
        turns = self.V / ".system" / "turns"
        turns.mkdir(parents=True, exist_ok=True)
        (turns / f"{sid}.json").write_text(json.dumps({
            "schema_version": 1, "turn": "20261021-100000-abc", "session_id": sid, "started": "2026-10-21T10:00:00",
            "prompt_head": "", "note": "", "done": True, "ingest_stopped": True}), encoding="utf-8")

    def test_unreadable_session_file_counts_as_not_stopped(self):
        """answer 測試第二輪後裁定 34（G-7）：session 檔讀不到（OSError）當沒按過停止，指示照印，寫一行 log。"""
        import importlib.util
        sys.path.insert(0, str(ROOT / "scripts"))
        spec = importlib.util.spec_from_file_location("hook_checks_stopped", ROOT / "hooks" / "_checks.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        (self.V / ".system" / "turns" / "abc.json").mkdir(parents=True)
        self.assertFalse(mod._stopped(self.V, "abc"))
        log = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(log), 1, log)

    def test_stopped_session_gets_no_md_hint(self):
        """answer 測試後修正裁定 14（F-2）：按過停止，md 不再叫整理；製作中那行不是整理指示，照印。"""
        (self.raw / "客戶案件" / "新.txt").write_text("新" + chr(10), encoding="utf-8")
        (self.raw / "客戶案件" / "筆記.md").write_text("# 筆記" + chr(10), encoding="utf-8")
        self.stop_session()
        lines = turn_lines(self.V, "abc")
        self.assertIn(WIP.format(1), lines)
        self.assertEqual(self.hint_lines(lines), [])

    def test_over_time_budget_prints_no_change_lines(self):
        """每句開頭時間到就停（_checks.TURN_BUDGET），下一句接著做；停的那句沒有變動行也不報錯。"""
        import importlib.util
        sys.path.insert(0, str(ROOT / "scripts"))
        spec = importlib.util.spec_from_file_location("hook_checks", ROOT / "hooks" / "_checks.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.START = time.monotonic() - 1000
        (self.raw / "客戶案件" / "新.txt").write_text("新" + chr(10), encoding="utf-8")
        self.assertEqual(mod.turn_lines(self.V, "s-late"), [])

    def test_wip_line_does_not_ask_to_sort(self):
        (self.raw / "客戶案件" / "新.txt").write_text("新" + chr(10), encoding="utf-8")
        lines = self.status()
        self.assertIn(WIP.format(1), lines)
        self.assertEqual(self.hint_lines(lines), [])
        self.assertFalse([ln for ln in lines if "20 份" in ln], lines)  # 不帶份數上限
        self.assertLessEqual(len(lines), 8)

    def test_same_file_is_told_once_per_conversation(self):
        (self.raw / "客戶案件" / "新.txt").write_text("新" + chr(10), encoding="utf-8")
        self.assertIn(WIP.format(1), turn_lines(self.V, "same"))
        self.assertEqual(turn_lines(self.V, "same"), [])  # 同一份同一個對話講過就不再印
        (self.raw / "客戶案件" / "新2.txt").write_text("新二" + chr(10), encoding="utf-8")
        self.assertIn(WIP.format(1), turn_lines(self.V, "same"))  # 只數沒講過的那份

    def test_many_files_told_once(self):
        """一次放的份數比 told 留的條數（30）多，下一句也不再講（told_files）。"""
        for i in range(40):
            (self.raw / "客戶案件" / f"批{i}.txt").write_text(f"{i}" + chr(10), encoding="utf-8")
        self.assertIn(WIP.format(40), turn_lines(self.V, "many"))
        self.assertEqual(turn_lines(self.V, "many"), [])

    def test_missing_told_once(self):
        (self.raw / "行政" / "請款" / "r.docx").unlink()
        self.assertIn(MISSING.format(1), turn_lines(self.V, "gone"))
        self.assertEqual(turn_lines(self.V, "gone"), [])

    def test_md_line_names_only_md(self):
        """第 8 點、裁定 3：md 照舊叫整理那幾份（列檔名），同一回合的其他檔走製作中、不一起整理。"""
        (self.raw / "客戶案件" / "新.txt").write_text("新" + chr(10), encoding="utf-8")
        (self.raw / "客戶案件" / "筆記.md").write_text("# 筆記" + chr(10), encoding="utf-8")
        lines = turn_lines(self.V, "md")
        self.assertIn(MD.format(1, "筆記.md"), lines)
        self.assertIn(WIP.format(1), lines)
        self.assertEqual(turn_lines(self.V, "md"), [])

    def test_md_names_shown_three(self):
        for i in range(4):
            (self.raw / "客戶案件" / f"n{i}.md").write_text(f"# {i}" + chr(10), encoding="utf-8")
        (line,) = [ln for ln in self.status() if " md 新放或改過" in ln]
        self.assertRegex(line, r"^有 4 份 md 新放或改過（n\d\.md、n\d\.md、n\d\.md等）：")

    def test_pointer_archived_skipped_not_wip(self):
        """裁定 8：指路卡、清冊封存、照設定不整理的檔改了，每句開頭不算製作中（跟 kb cards wip 同一套）。"""
        p = self.V / ".system" / "inventory.json"
        base = p.read_text(encoding="utf-8")
        for field, value in (("card_mode", "pointer"), ("archived", True), ("skip_kind", "請款")):
            with self.subTest(field=field):
                data = json.loads(base)
                (entry,) = [e for e in data["entries"] if any(loc["uri"].endswith("/a.txt") for loc in e["locations"])]
                entry[field] = value
                p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                (self.raw / "客戶案件" / "a.txt").write_text(f"改過 {field}\n", encoding="utf-8")
                self.assertEqual([ln for ln in turn_lines(self.V, f"filter-{field}") if CHANGE_HEAD.match(ln)], [])
        (self.raw / "客戶案件" / "新.txt").write_text("新\n", encoding="utf-8")  # 新放的（清冊沒有）照算
        self.assertIn(WIP.format(1), turn_lines(self.V, "filter-new"))

    def test_incomplete_line_no_hint(self):
        # 每句開頭的比對用自己的上限（放寬丙）：讀取上限 1 位元組，改過的檔算不了指紋就是沒比完
        (self.V / ".system" / "config.json").write_text(json.dumps({"turn_scan_hash_budget_bytes": 1}), encoding="utf-8")
        (self.raw / "客戶案件" / "a.txt").write_text("改過了，長度不一樣" + chr(10), encoding="utf-8")
        lines = self.status()
        self.assertIn(CHANGES_INCOMPLETE, lines)
        self.assertEqual(self.hint_lines(lines), [])


class DailyWip(unittest.TestCase):
    """D-525 第 5 點、驗收 5：每天第一句有製作中才多一行（最多 3 個檔名），沒有不印。"""

    setUp = OpeningInventory.setUp
    tearDown = OpeningInventory.tearDown

    def daily(self):
        return [ln for ln in turn_lines(self.V) if ln.startswith("製作中 ")]

    def test_line_when_wip_then_not_again_today(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from kb._lib import cards
        from tests import _cards
        for i in range(3):
            (self.raw / "客戶案件" / f"加{i}.txt").write_text(f"{i}" + chr(10), encoding="utf-8")
        _cards.scan_apply(self.V)
        n = len(cards.wip(self.V))
        self.assertGreater(n, 3)
        (line,) = self.daily()
        self.assertRegex(line, rf"^製作中 {n} 份：[^、]+、[^、]+、[^、]+…；跟客戶說一句還有這幾份沒整理、要整理說一聲，不問、不追。$")
        self.assertEqual(self.daily(), [])  # 每天第一句才印

    def test_no_wip_no_line(self):
        OpeningWip.skip_all(self)
        self.assertEqual(self.daily(), [])


class OpeningEntityDrift(unittest.TestCase):
    """實體與綜合卡第 7 點、驗收 13：實體夾有變自成一行、只叫問 asks 那題（D-525 裁定 1）；實體清單壞了變動行照印、log 一行；
    只寫 env.json。fixture 的 案子/信義王/信義王.md 換成 tests/fixtures/entities 的綜合卡，信義王 card true。"""

    setUp_inventory = OpeningInventory.setUp
    tearDown = OpeningInventory.tearDown
    status = OpeningInventory.status
    change_lines = OpeningInventory.change_lines

    def setUp(self):
        self.setUp_inventory()
        fix = ROOT / "tests" / "fixtures" / "entities"
        shutil.copy2(fix / "entities.json", self.V / ".system" / "entities.json")
        shutil.copy2(fix / "信義王.md", self.V / "案子" / "信義王" / "信義王.md")
        (self.V / "案子" / "大安陳").mkdir()
        shutil.copy2(fix / "大安陳.md", self.V / "案子" / "大安陳" / "大安陳.md")

    def stamps(self):
        return {p.relative_to(self.V).as_posix(): p.stat().st_mtime_ns
                for p in (self.V / ".system").rglob("*") if p.is_file()}

    def test_no_drift_no_line(self):
        self.assertEqual(self.change_lines(self.status()), [])

    def test_drift_alone_then_hint(self):
        (self.V / "案子" / "信義王").rename(self.V / "案子" / "王宅")
        before = self.stamps()
        lines = self.status()
        self.assertIn(DRIFT.format(1), lines)
        self.assertFalse([ln for ln in lines if "照 ingest" in ln], lines)
        after = self.stamps()
        self.assertLessEqual({k for k in after if before.get(k) != after[k] and not k.startswith((".system/turns/", ".system/journal/", ".system/renders", ".system/versions/"))}, {".system/env.json", ".system/vault.json", ".system/upgrade-history.json", ".system/card_base.json"})  # card_base：第一次開補卡的基準（D-270）

    def test_drift_appended_to_counts(self):
        (self.raw / "客戶案件" / "新.txt").write_text("新\n", encoding="utf-8")
        shutil.rmtree(self.V / "案子" / "大安陳")
        lines = self.status()
        self.assertIn(WIP.format(1), lines)
        self.assertIn(DRIFT.format(1), lines)

    def test_broken_entities_change_line_still_printed(self):
        (self.raw / "客戶案件" / "新.txt").write_text("新\n", encoding="utf-8")
        (self.V / ".system" / "entities.json").write_text("{bad", encoding="utf-8")
        self.assertEqual(self.change_lines(self.status()), [WIP.format(1)])
        # 放寬丙 6-3：實體清單壞了，沒有備份就從綜合卡檔頭重建，壞的留在 .system/broken/，不再只寫 log
        (kept,) = list((self.V / ".system" / "broken").iterdir())
        self.assertEqual(kept.read_text(encoding="utf-8"), "{bad")
        self.assertIn("entities", json.loads((self.V / ".system" / "entities.json").read_text(encoding="utf-8")))


ASK = "跑 kb profile apply 套用；做完照核心規則講發現什麼、推測使用者的意思、做了什麼。"
TYPE_ROW = "| 案子 | 事 |  | 推測 | 2026-10-19 |\n"


class OpeningProfile(unittest.TestCase):
    """客戶設定檔與型別第 7 點、驗收 10：沒改不印；有改一行；讀不懂一行；unlisted 接在同一行或自成一行；只讀不寫；
    profile.json 壞了其他行照印、log 一行。fixture 的型別表只有「案子」。"""

    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        self.md = self.V / "系統" / "客戶設定檔.md"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    status = OpeningInventory.status

    def profile_lines(self, lines=None):
        return [ln for ln in (lines if lines is not None else self.status()) if ln.startswith("設定檔")]

    def edit(self, old, new):
        text = self.md.read_text(encoding="utf-8")
        self.assertIn(old, text)
        self.md.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")

    def test_unchanged_no_line(self):
        self.assertEqual(self.profile_lines(), [])

    def test_changed_line(self):
        self.edit(TYPE_ROW, TYPE_ROW + "| 工地 | 事 | x |\n")
        self.assertEqual(self.profile_lines(), [f"設定檔被手改了（型別 +1）：{ASK}"])

    def test_whitespace_only_change_no_line(self):
        self.edit(TYPE_ROW, TYPE_ROW + "\n")
        self.assertEqual(self.profile_lines(), [])

    def test_unreadable_line(self):
        self.edit(TYPE_ROW, TYPE_ROW + "| 工地 | 事 |\n")
        self.assertEqual(self.profile_lines(),
                         ["設定檔有改但讀不懂：第 1 節第 2 列欄數不對（要 3 欄或 5 欄）；改好下次再問"])

    def test_unreadable_line_has_no_unlisted_part(self):
        (self.V / "廠商").mkdir()
        self.edit(TYPE_ROW, TYPE_ROW + "| 工地 | 事 |\n")
        self.assertEqual(self.profile_lines(),
                         ["設定檔有改但讀不懂：第 1 節第 2 列欄數不對（要 3 欄或 5 欄）；改好下次再問"])

    def test_unlisted_not_printed(self):
        """放寬甲：第一層有不在型別表的夾不再印（PROFILE_UNLISTED 拿掉）。"""
        (self.V / "廠商").mkdir()
        self.assertEqual(self.profile_lines(), [])
        self.edit(TYPE_ROW, TYPE_ROW + "| 工地 | 事 | x |\n")
        self.assertEqual(self.profile_lines(), [f"設定檔被手改了（型別 +1）：{ASK}"])

    def test_reads_only(self):
        (self.V / "廠商").mkdir()

        def stamps():
            return {p.relative_to(self.V).as_posix(): p.stat().st_mtime_ns
                    for p in (self.V / ".system").rglob("*") if p.is_file()}
        for change in ((TYPE_ROW, TYPE_ROW + "| 工地 | 事 | x |\n"), ("| 工地 | 事 | x |", "| 工地 | 事 |")):
            before = stamps()
            self.edit(*change)
            self.assertTrue(self.profile_lines())
            after = stamps()
            self.assertEqual({k for k in after if before.get(k) != after[k] and not k.startswith((".system/turns/", ".system/journal/", ".system/renders", ".system/versions/"))}
                             - {".system/env.json", ".system/vault.json", ".system/upgrade-history.json"}, set())
        self.assertEqual(self.md.read_text(encoding="utf-8").count("| 工地 | 事 |"), 1)

    def test_broken_profile_json_other_lines_printed(self):
        (self.V / ".system" / "profile.json").write_text("{bad", encoding="utf-8")
        lines = self.status("compact")
        self.assertEqual((lines[0], lines[-1]), (KB_LINE, COMPACT_LINE))
        self.assertEqual(self.profile_lines(lines), [])
        log = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(log), 2, "設定檔那行與偏好段（note 改規則第 4 點）各自 try、各記一行（I-046）")
        self.assertEqual({ln.split("\t")[1] for ln in log}, {"session", "turn"})


if __name__ == "__main__":
    unittest.main()


class OpeningAgenda(unittest.TestCase):
    """日程題第 6 點、驗收 5：日程行三種（沒有、有逾期帶提示、只有接下來）、0 的項不印、agenda.json 壞了其他行照印、開場不寫檔。"""

    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, *specs):
        """specs：(kind, 距今天數, status)。"""
        from datetime import date, timedelta
        items = [{"id": f"a-{i:08x}", "kind": kind, "start": None, "date": (date.today() + timedelta(days=days)).isoformat(),
                  "ended": None, "time": None, "text": f"事{i}", "entities": [], "status": status, "source": "confirmed",
                  "origin": None, "lead_days": None, "created_turn": "t", "history": []}
                 for i, (kind, days, status) in enumerate(specs)]
        (self.V / ".system" / "agenda.json").write_text(
            json.dumps({"schema_version": 1, "items": items}, ensure_ascii=False), encoding="utf-8")

    def status(self, source="startup"):
        r = run(payload(self.V, source))
        self.assertEqual(r.returncode, 0, r.stderr)
        r.stdout.encode("ascii")
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        return ctx.split("\n\n", 1)[0].split("\n")

    def agenda_lines(self, lines):
        return [ln for ln in lines if ln.startswith("日程：")]

    def test_no_agenda_no_line(self):
        self.assertEqual(self.agenda_lines(self.status()), [])

    def test_overdue_line_has_the_hint(self):
        self.put(("deadline", -3, "open"))
        self.assertEqual(self.agenda_lines(self.status()), ["日程：逾期 1（逾期的在回答最後問一件，客戶說先放著就 kb asks set-aside）"])

    def test_all_three_numbers(self):
        self.put(("deadline", -3, "open"), ("promise", -1, "open"), ("meeting", 0, "open"), ("reminder", 2, "open"),
                 ("deadline", 5, "open"))
        self.assertEqual(self.agenda_lines(self.status()), ["日程：逾期 2（逾期的在回答最後問一件，客戶說先放著就 kb asks set-aside）、今天 1、7 天內 2"])

    def test_only_upcoming(self):
        self.put(("meeting", 2, "open"), ("reminder", 6, "open"), ("deadline", 30, "open"))
        self.assertEqual(self.agenda_lines(self.status()), ["日程：7 天內 2"])

    def test_zero_everywhere_prints_nothing(self):
        self.put(("deadline", -3, "done"), ("meeting", -3, "open"), ("deadline", 3, "cancelled"), ("period", 3, "open"))
        self.assertEqual(self.agenda_lines(self.status()), [])

    def test_window_reads_config(self):
        self.put(("meeting", 2, "open"), ("meeting", 5, "open"))
        (self.V / ".system" / "config.json").write_text(json.dumps({"agenda_window_days": 3}), encoding="utf-8")
        self.assertEqual(self.agenda_lines(self.status()), ["日程：3 天內 1"])

    def test_line_sits_before_compact_line(self):
        self.put(("meeting", 2, "open"))
        lines = self.status("compact")
        self.assertEqual((lines[-2], lines[-1]), ("日程：7 天內 1", COMPACT_LINE))

    def test_broken_agenda_other_lines_still_printed_and_one_log_line(self):
        (self.V / ".system" / "agenda.json").write_text("{bad", encoding="utf-8")
        lines = self.status("compact")
        self.assertEqual((lines[0], lines[-1]), (KB_LINE, COMPACT_LINE))
        self.assertEqual(self.agenda_lines(lines), [])
        log = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(log), 1)
        self.assertEqual(log[0].split("\t")[1], "session")
        self.assertIn(".system/agenda.json", log[0])

    def test_opening_writes_nothing_but_env_json(self):
        self.put(("deadline", -3, "open"), ("meeting", 2, "open"))

        def stamps():
            return {p.relative_to(self.V).as_posix(): p.stat().st_mtime_ns
                    for p in (self.V / ".system").rglob("*") if p.is_file()}
        before = stamps()
        self.status()
        after = stamps()
        self.assertEqual({k for k in after if before.get(k) != after[k]} - {".system/env.json", ".system/vault.json", ".system/upgrade-history.json"}, set())
        self.assertFalse((self.V / "系統" / "日程.md").exists())


class OpeningPreferences(unittest.TestCase):
    """note 改規則第 4 點、驗收 13（D-137）：core.md 之後接「客戶偏好：」一條一行；沒有不印；profile.json 壞了這段不印、其他照印、寫 log。"""

    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, *texts):
        p = self.V / ".system" / "profile.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["preferences"] = [{"text": t, "source": "corrected", "date": "2026-10-20"} for t in texts]
        data["schema_version"] = 3
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def context(self):
        r = run(payload(self.V))
        self.assertEqual(r.returncode, 0, r.stderr)
        r.stdout.encode("ascii")
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_block_after_core(self):
        self.put("回答先講結論", "講日期都帶星期")
        ctx = self.context()
        core = CORE.read_text(encoding="utf-8")
        self.assertTrue(ctx.endswith("\n\n" + core + "\n客戶偏好（跟上面的核心規則衝突時照客戶的，只有刪掉、蓋掉之前先留一份不讓）：\n- 回答先講結論\n- 講日期都帶星期"), ctx[-200:])
        self.assertEqual(ctx.splitlines()[0], KB_LINE)

    def test_no_preferences_no_block(self):
        self.put()
        self.assertNotIn("客戶偏好", self.context())
        self.assertTrue(self.context().endswith(CORE.read_text(encoding="utf-8")))

    def test_broken_profile_skips_block_only(self):
        (self.V / ".system" / "profile.json").write_text("{bad", encoding="utf-8")
        ctx = self.context()
        self.assertNotIn("客戶偏好", ctx)
        self.assertEqual(ctx.splitlines()[0], KB_LINE)
        self.assertTrue(ctx.endswith("\n\n" + CORE.read_text(encoding="utf-8")))
        log = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8").splitlines()
        self.assertTrue(log and all(ln.split("\t")[1] == "session" for ln in log))


class OpeningLeftAndMoved(unittest.TestCase):
    """card-maker 驗收 13b（B-415）：開場那行「還有 N 份沒整理完、M 張卡要跟著搬」；讀不到記進待處理的（有密碼、線上文件打不開）
    不算；0 的那半不印。"""

    def setUp(self):
        from tests import _cards
        self._cards = _cards
        self.tmp, self.V, self.raw = _cards.make_card_vault()
        _cards.mark_dates_scanned(self.V)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def todo(self):
        r = subprocess.run([sys.executable, str(KB), "cards", "todo", "--json"], capture_output=True, text=True,
                           encoding="utf-8", cwd=str(self.V))
        return json.loads(r.stdout)

    def status(self):
        r = run(payload(self.V))
        self.assertEqual(r.returncode, 0, r.stderr)
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        return ctx.split("\n\n", 1)[0].split("\n") + turn_lines(self.V)

    def test_left_and_moved(self):
        from kb._lib import inventory, pending, turn
        raw = str(self.raw).casefold()
        items = [i for i in self.todo()["new"] if i["kind"] != "link" and str(i["path"]).casefold().startswith(raw)]
        for n, item in enumerate(items[:5]):
            self._cards.write_card(self.V, item, f"卡{n}")
        for item in items[:5]:  # 原檔搬到同夾底下的另一個夾：卡要跟著搬
            src = Path(item["path"])
            dst = src.parent / "搬過" / src.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
        self._cards.scan_apply(self.V)
        self._cards.mark_dates_scanned(self.V)
        t = turn.start(self.V, None, "")["turn"]
        locked = items[5]["id"]
        pending.add(self.V, "unreadable", [locked], "x 讀不到", "有密碼", t)
        link = inventory.register_link(self.V, "https://claude.ai/artifact/abc", t, "報價說明")
        r = subprocess.run([sys.executable, str(KB), "cards", "unreadable", link["id"], "--reason", "線上文件打不開"],
                           capture_output=True, text=True, encoding="utf-8", cwd=str(self.V))
        self.assertEqual(r.returncode, 0, r.stdout)
        data = self.todo()
        self.assertEqual(len(data["moved"]), 5)
        left = len(data["new"]) + len(data["stale"])
        self.assertNotIn(locked, [i["id"] for i in data["new"]])
        self.assertGreater(left, 0)
        lines = self.status()  # 放寬丙 3（D-310(2)）：不再報份數與要跟著搬的卡
        self.assertEqual([ln for ln in lines if "沒整理完" in ln or "要跟著搬" in ln or "要改寫" in ln], [])

    def test_only_moved(self):
        p = self.V / ".system" / "inventory.json"
        raw = str(self.raw).casefold()
        items = [i for i in self.todo()["new"] if str(i["path"] or "").casefold().startswith(raw)][:2]
        for n, item in enumerate(items):
            self._cards.write_card(self.V, item, f"卡{n}")
        data = json.loads(p.read_text(encoding="utf-8"))
        keep = {i["id"] for i in items}
        for e in data["entries"]:
            if e["id"] not in keep:
                e["skip_kind"] = "請款"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        for item in items:
            src = Path(item["path"])
            (src.parent / "搬過").mkdir(exist_ok=True)
            src.rename(src.parent / "搬過" / src.name)
        self._cards.scan_apply(self.V)
        self._cards.mark_dates_scanned(self.V)
        self.assertEqual([ln for ln in self.status() if "要跟著搬" in ln], [])


class OpeningMoved(unittest.TestCase):
    """備份還原與換電腦第 4 點：line_moved（換了位置、這台電腦第一次開）排在變動行前面，只讀；印了就不印整理指示與找不到來源。"""
    setUp, tearDown, status = OpeningInventory.setUp, OpeningInventory.tearDown, OpeningInventory.status
    MOVED = "知識庫換了位置：先跑 kb moved 補好再做別的。"
    NEW = "這台電腦第一次開這個知識庫：先跑 kb moved 看要補什麼。"

    def put_env(self, machines):
        (self.V / ".system" / "env.json").write_text(json.dumps(
            {"schema_version": 1, "machines": machines}, ensure_ascii=False), encoding="utf-8")

    def me(self):
        import platform
        return platform.node() or "unknown"

    def here(self):
        return Path(os.path.realpath(str(self.V))).as_posix()

    def test_no_record_prints_nothing(self):
        lines = self.status()
        self.assertNotIn(self.MOVED, lines)
        self.assertNotIn(self.NEW, lines)

    def test_first_run_quietly_records_the_place_and_vault_id(self):
        """測試 T-2：這台與別台都沒有位置紀錄（first）時，開場默默寫 vault_path、補 vault.json，不印；第二次開場也不印。"""
        self.assertFalse((self.V / ".system" / "vault.json").exists())
        lines = self.status()
        self.assertNotIn(self.MOVED, lines)
        self.assertNotIn(self.NEW, lines)
        data = json.loads((self.V / ".system" / "env.json").read_text(encoding="utf-8"))
        self.assertEqual(data["machines"][self.me()]["vault_path"], self.here())
        self.assertTrue((self.V / ".system" / "vault.json").is_file())
        before = (self.V / ".system" / "env.json").read_bytes()
        lines = self.status()
        self.assertNotIn(self.MOVED, lines)
        self.assertEqual((self.V / ".system" / "env.json").read_bytes(), before)

    def test_after_the_first_record_moving_the_folder_is_noticed(self):
        """記過位置之後搬到別處：開場印換了位置那句（舊位置是自己記的，不是 kb moved 寫的）。"""
        self.status()  # 第一次：記下位置
        data = json.loads((self.V / ".system" / "env.json").read_text(encoding="utf-8"))
        data["machines"][self.me()]["vault_path"] = "D:/lin/舊位置/知識庫"  # 模擬記的是搬家之前的位置
        data["machines"][self.me()].pop("daily_done", None)  # 每天第一次才印（放寬丙 3b）：換一天
        (self.V / ".system" / "env.json").write_text(json.dumps(data), encoding="utf-8")
        self.assertIn(self.MOVED, self.status())

    def test_same_place_prints_nothing(self):
        self.put_env({self.me(): {"vault_path": self.here()}})
        lines = self.status()
        self.assertNotIn(self.MOVED, lines)
        self.assertNotIn(self.NEW, lines)

    def test_moved_line_and_no_change_lines(self):
        (self.raw / "客戶案件" / "新.txt").write_text("新\n", encoding="utf-8")
        self.put_env({self.me(): {"vault_path": "D:/lin/桌面/知識庫"}})
        before = (self.V / ".system" / "env.json").read_bytes()
        lines = self.status()
        self.assertIn(self.MOVED, lines)
        self.assertFalse([ln for ln in lines if CHANGE_HEAD.match(ln)], lines)  # 先補位置：變動行讓位（D-525 起沒有另一行數字）
        env_after = json.loads((self.V / ".system" / "env.json").read_text(encoding="utf-8"))
        self.assertEqual(env_after["machines"][self.me()]["vault_path"], "D:/lin/桌面/知識庫", "只讀，不寫 vault_path")

    def test_without_moved_the_wip_line_is_there(self):
        (self.raw / "客戶案件" / "新.txt").write_text("新\n", encoding="utf-8")
        self.assertIn(WIP.format(1), self.status())

    def test_new_machine_line(self):
        self.put_env({"OTHER-PC": {"vault_path": "D:/lin/知識庫"}})
        lines = self.status()
        self.assertIn(self.NEW, lines)
        self.assertNotIn(self.MOVED, lines)

    def test_missing_source_line_yields_and_mark_is_not_written(self):
        (self.raw / "客戶案件").rename(self.raw / "客戶案件_舊")
        self.put_env({self.me(): {"vault_path": "D:/lin/桌面/知識庫"}})
        lines = self.status()
        self.assertFalse([ln for ln in lines if ln.startswith("這台電腦找不到來源")], lines)
        data = json.loads((self.V / ".system" / "env.json").read_text(encoding="utf-8"))
        self.assertNotIn("missing_sources_reported", data["machines"][self.me()])

    def test_broken_env_file_is_quiet(self):
        (self.V / ".system" / "env.json").write_text("{壞", encoding="utf-8")
        lines = self.status()
        self.assertNotIn(self.MOVED, lines)
        self.assertNotIn(self.NEW, lines)


class OpeningUpgrade(unittest.TestCase):
    """升級打包 要做的事 7（驗收 10、11）：line_version 三句、第一次記版本、整理指示讓位、背景子行程。"""
    setUp, tearDown, status = OpeningInventory.setUp, OpeningInventory.tearDown, OpeningInventory.status

    def plugin(self):
        return json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]

    def put_history(self, current, pending=None):
        (self.V / ".system" / "upgrade-history.json").write_text(json.dumps(
            {"schema_version": 1, "current": current, "pending": pending, "history": []}), encoding="utf-8")

    def put_check(self, **kw):
        from datetime import date
        base = {"date": date.today().isoformat(), "latest": None, "kind": None, "allowed": False, "note": None,
                "auto_patched": None, "error": None}
        (self.V / ".system" / "env.json").write_text(json.dumps(
            {"schema_version": 1, "machines": {self.me(): {"update_check": dict(base, **kw)}}}), encoding="utf-8")

    def me(self):
        import platform
        return platform.node() or "unknown"

    def version_lines(self, lines):
        return [ln for ln in lines if ln.startswith(("已換到", "有新版", "這一版"))]

    def test_first_run_records_current_version_and_prints_nothing(self):
        """驗收 10：沒有 upgrade-history.json → 開場不印換版那行、記成現在版本。"""
        self.assertFalse((self.V / ".system" / "upgrade-history.json").exists())
        self.assertEqual(self.version_lines(self.status()), [])
        data = json.loads((self.V / ".system" / "upgrade-history.json").read_text(encoding="utf-8"))
        self.assertEqual((data["current"], data["pending"], data["history"]), (self.plugin(), None, []))
        before = (self.V / ".system" / "upgrade-history.json").read_bytes()
        self.assertEqual(self.version_lines(self.status()), [])
        self.assertEqual((self.V / ".system" / "upgrade-history.json").read_bytes(), before)

    def test_changed_version_line_comes_right_after_the_kb_line(self):
        """驗收 11：current 不等於 plugin 版本 → 換版那句，排在 kb 那行之後、變動那行之前。"""
        self.put_history("0.1.0")
        (self.raw / "客戶案件" / "新.txt").write_text("新\n", encoding="utf-8")
        lines = self.status()
        want = f"已換到 {self.plugin()}：先跑 kb upgrade --finish 再做別的。"
        self.assertEqual(lines[1], want)

    def test_changed_version_hides_the_change_lines(self):
        """有 --finish 要做時變動行不印（D-525：製作中、md 那行都叫跑 scan），免得轉格式前就記清冊、整理。"""
        self.put_history("0.1.0")
        (self.raw / "客戶案件" / "新.txt").write_text("新\n", encoding="utf-8")
        lines = self.status()
        self.assertFalse([ln for ln in lines if CHANGE_HEAD.match(ln)], lines)

    def test_same_version_keeps_the_wip_line(self):
        self.put_history(self.plugin())
        (self.raw / "客戶案件" / "新.txt").write_text("新\n", encoding="utf-8")
        self.assertIn(WIP.format(1), self.status())

    def test_new_version_line_for_a_big_upgrade(self):
        self.put_history(self.plugin())
        self.put_check(latest="99.0.0", kind="major", allowed=True, note="日程可以匯出成 Excel")
        lines = self.status()
        self.assertEqual(lines[1], "有新版 99.0.0：日程可以匯出成 Excel；客戶說「升級」再帶他做，這行只講一次。")

    def test_new_version_line_not_printed_when_not_on_the_roster_or_only_a_patch(self):
        self.put_history(self.plugin())
        parts = self.plugin().split(".")
        major = f"{int(parts[0]) + 1}.0.0"
        patch = ".".join(parts[:2] + [str(int(parts[2]) + 1)])
        for latest, allowed in ((major, False), (patch, True)):
            self.put_check(latest=latest, kind="x", allowed=allowed, note="x")
            with self.subTest(latest=latest, allowed=allowed):
                self.assertEqual(self.version_lines(self.status()), [])

    def test_withdrawn_line_when_the_list_points_back(self):
        self.put_history(self.plugin())
        self.put_check(latest="0.0.1", kind="downgrade", allowed=True, note="x")
        self.assertEqual(self.status()[1], f"這一版 {self.plugin()} 撤回了；用起來有問題的話說「退回舊版」。")

    def test_changed_version_beats_the_new_version_line(self):
        self.put_history("0.1.0")
        self.put_check(latest="99.0.0", kind="major", allowed=True, note="x")
        lines = self.version_lines(self.status())
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("已換到"))

    def test_broken_history_prints_no_version_line_logs_once_and_keeps_other_lines(self):
        (self.V / ".system" / "upgrade-history.json").write_text("{壞", encoding="utf-8")
        (self.raw / "客戶案件" / "新.txt").write_text("新\n", encoding="utf-8")
        lines = self.status()
        self.assertEqual(self.version_lines(lines), [])
        self.assertIn(WIP.format(1), lines, "壞檔不影響變動行")
        log = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8")
        self.assertEqual(log.count("upgrade-history.json"), 2)  # 開場一次、第一句開頭一次（各自的行程只記一行）
        self.assertEqual((self.V / ".system" / "upgrade-history.json").read_text(encoding="utf-8"), "{壞")

    def test_no_background_env_never_spawns_so_black_box_runs_stay_offline(self):
        """預設網址 0.26.1 起填了；測試設的 WIKI_WITH_WILLY_NO_BACKGROUND 讓黑箱跑開場不開子行程、不連網。"""
        self.put_history(self.plugin())
        self.status()
        env_file = self.V / ".system" / "env.json"
        self.assertFalse(env_file.exists() and "update_check" in env_file.read_text(encoding="utf-8"))


class OpeningSpawn(unittest.TestCase):
    """驗收 11：日期不是今天 → 背景子行程有被叫（替身記下參數）、開場沒有等它（時間 < 1 秒）。同行程載入 hooks/session.py。"""

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("session_hook_under_test", HOOK)
        self.session = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.session)
        self.tmp, self.V, self.raw = make_vault()
        (self.V / ".system" / "config.json").write_text(json.dumps(
            {"update_manifest_url": "https://example.invalid/marketplace.json"}), encoding="utf-8")
        self.env = os.environ.pop("WIKI_WITH_WILLY_NO_BACKGROUND", None)

    def tearDown(self):
        if self.env is not None:
            os.environ["WIKI_WITH_WILLY_NO_BACKGROUND"] = self.env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_manifest_url_never_spawns(self):
        """清單網址空字串（客戶自己的 config.json 蓋掉）：背景查新版看到空就不查。"""
        from unittest import mock
        from kb._lib import upgrade
        (self.V / ".system" / "config.json").write_text(json.dumps({"update_manifest_url": ""}), encoding="utf-8")
        calls = []
        with mock.patch.object(upgrade, "_popen", side_effect=lambda argv, **kw: calls.append(argv)):
            self.session.line_version(self.V)
        self.assertEqual(calls, [])

    def test_no_background_env_never_spawns(self):
        from unittest import mock
        from kb._lib import upgrade
        os.environ["WIKI_WITH_WILLY_NO_BACKGROUND"] = "1"
        try:
            calls = []
            with mock.patch.object(upgrade, "_popen", side_effect=lambda argv, **kw: calls.append(argv)):
                self.session.line_version(self.V)
            self.assertEqual(calls, [])
        finally:
            del os.environ["WIKI_WITH_WILLY_NO_BACKGROUND"]

    def test_spawn_called_with_background_args_and_not_waited_on(self):
        from unittest import mock
        from kb._lib import upgrade
        proc = mock.Mock()
        proc.wait.side_effect = AssertionError("開場不等背景")
        proc.communicate.side_effect = AssertionError("開場不等背景")
        calls = []
        started = time.monotonic()
        with mock.patch.object(upgrade, "_popen", side_effect=lambda argv, **kw: calls.append((argv, kw)) or proc):
            self.session.line_version(self.V)
        self.assertLess(time.monotonic() - started, 1)
        self.assertEqual(len(calls), 1)
        argv, kw = calls[0]
        self.assertEqual(argv[-2:], ["upgrade", "--background"])
        self.assertTrue(argv[-3].endswith("kb.py"))
        self.assertEqual(Path(kw["cwd"]).resolve(), Path(self.V).resolve())

    def test_yesterday_spawns_today_does_not(self):
        from datetime import date, timedelta
        from unittest import mock
        from kb._lib import env, upgrade
        calls = []
        with mock.patch.object(upgrade, "_popen", side_effect=lambda argv, **kw: calls.append(argv)):
            env.set_update_check(self.V, {"date": (date.today() - timedelta(days=1)).isoformat()})
            self.session._UPGRADE.clear()
            self.session.line_version(self.V)
            self.assertEqual(len(calls), 1)
            self.session._UPGRADE.clear()
            self.session.line_version(self.V)  # 上一次開場已經記了今天
            self.assertEqual(len(calls), 1)


def _checks_module():
    """hooks/_checks.py（session.py 載入時 import 的那一份）。"""
    sys.path.insert(0, str(ROOT / "hooks"))
    sys.path.insert(0, str(ROOT / "scripts"))
    import _checks
    return _checks


class BackgroundLint(unittest.TestCase):
    """lint 題驗收 20（D-221、D-227）：lint.json 的 last_background 超過 lint_background_days → 開場背景開 kb lint --background
    （替身記參數）、不等它、開場 < 1 秒；沒超過不開；同一天第二次開場不再開；開場不多印一行。"""

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("session_hook_lint", HOOK)
        self.session = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.session)
        self.tmp, self.V, self.raw = make_vault()
        self.env = os.environ.pop("WIKI_WITH_WILLY_NO_BACKGROUND", None)

    def tearDown(self):
        if self.env is not None:
            os.environ["WIKI_WITH_WILLY_NO_BACKGROUND"] = self.env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, **fields):
        (self.V / ".system" / "lint.json").write_text(json.dumps(dict({"schema_version": 1}, **fields)), encoding="utf-8")

    def spawn_calls(self):
        from unittest import mock
        from kb.lint import runner
        calls = []
        proc = mock.Mock()
        proc.wait.side_effect = AssertionError("開場不等背景")
        with mock.patch.object(runner, "_popen", side_effect=lambda argv, **kw: calls.append((argv, kw)) or proc):
            started = time.monotonic()
            lines = self.session.status_lines(self.V, "startup", "sid")
            self.assertLess(time.monotonic() - started, 3)
        return calls, lines

    def test_eight_days_ago_spawns(self):
        from datetime import date, timedelta
        self.put(last_background=(date.today() - timedelta(days=8)).isoformat())
        calls, lines = self.spawn_calls()
        self.assertEqual(len(calls), 1)
        argv, kw = calls[0]
        self.assertEqual(argv[-2:], ["lint", "--background"])
        self.assertTrue(argv[-3].endswith("kb.py"))
        self.assertEqual(Path(kw["cwd"]).resolve(), Path(self.V).resolve())
        self.assertFalse([ln for ln in lines if "健檢" in ln], "開場不另外提醒（D-221 修訂）")
        again, _lines = self.spawn_calls()
        self.assertEqual(again, [], "同一天開過了")

    def test_no_lint_json_spawns(self):
        calls, _lines = self.spawn_calls()
        self.assertEqual(len(calls), 1)

    def test_recent_does_not_spawn(self):
        from datetime import date, timedelta
        self.put(last_background=(date.today() - timedelta(days=3)).isoformat())
        self.assertEqual(self.spawn_calls()[0], [])

    def test_not_when_opening_asks_to_fix_first(self):
        """換了位置（先 kb moved）或換了版（先 --finish）的開場不開：健檢會把只是搬家造成的出處點不開記成要決定的事。"""
        from unittest import mock
        with mock.patch.object(_checks_module(), "line_moved", return_value="知識庫換了位置：先跑 kb moved 補好再做別的。"):
            self.assertEqual(self.spawn_calls()[0], [])
        (self.V / ".system" / "env.json").unlink(missing_ok=True)  # 上一個呼叫已記今天做過了
        with mock.patch.object(_checks_module(), "upgrade_state", return_value={"finish": True, "line": "x"}):
            self.assertEqual(self.spawn_calls()[0], [])

    def test_lock_busy_does_not_wait_long(self):
        from kb._lib import io as kio
        from kb.lint import state
        lock = kio.FileLock(self.V / state.LINT_POSIX, timeout=1)
        lock.__enter__()
        try:
            started = time.monotonic()
            calls, _lines = self.spawn_calls()
            self.assertLess(time.monotonic() - started, 2.5)
            self.assertEqual(calls, [], "記不到今天開過就不開，下次開場再試")
        finally:
            lock.__exit__(None, None, None)

    def test_switch_for_tests(self):
        os.environ["WIKI_WITH_WILLY_NO_BACKGROUND"] = "1"
        try:
            self.assertEqual(self.spawn_calls()[0], [])
        finally:
            del os.environ["WIKI_WITH_WILLY_NO_BACKGROUND"]


class LintFixCounted(unittest.TestCase):
    """lint 題 D-161（桌面版確認後 3a 定）：健檢標的要改寫綜合卡在同一行另講「K 張綜合卡要改寫」，「還有 N 份沒整理完」只數檔；
    0 的那半不印，整理指示照舊接在後面。"""

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("session_hook_fix", HOOK)
        self.session = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.session)
        self.tmp, self.V, self.raw = make_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_no_unsorted_or_fix_lines_any_more(self):
        """放寬丙 3（D-310(2)）：變動行不再報「還有 N 份沒整理完」「N 張綜合卡要改寫」「N 張卡要跟著搬」。"""
        from unittest import mock
        checks = _checks_module()
        report = {"incomplete": False, "added": [], "modified": [], "missing": [], "missing_sources": []}
        for cache in (checks._DRIFT, checks._SCAN):
            cache.clear()
        with mock.patch.object(checks, "file_compare", return_value=(None, report)),                 mock.patch.object(checks, "drift_count", return_value=0):
            self.assertEqual(checks.change_lines(self.V), ([], []))
            self.assertIsNone(checks.line_drift(self.V))

    def test_cards_unsorted_counts_files_only(self):
        from tests import _lint as L
        from kb._lib import cards
        from kb.lint import state
        tmp, V, _raw = L.make()
        try:
            before = cards.unsorted(V)
            state.add_fix(V, L.write_synthesis(V), "有空段", [])
            self.assertEqual(cards.unsorted(V), before)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class NoInboxLine(unittest.TestCase):
    """放寬丙 3（D-318）：收件匣放很久的提醒拿掉了；開場不再有那行，defaults 沒有 inbox_remind_ 的鍵，env.json 舊欄略過。"""

    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_twenty_old_files_print_no_line(self):
        hold = self.V / "暫存區"
        hold.mkdir(exist_ok=True)
        for i in range(20):
            f = hold / f"舊{i}.txt"
            f.write_text("x", encoding="utf-8")
            os.utime(f, (time.time() - 30 * 86400, time.time() - 30 * 86400))
        (self.V / ".system" / "env.json").write_text(json.dumps(
            {"schema_version": 1, "machines": {"X": {"inbox_reminded": "2020-01-01"}}}), encoding="utf-8")
        r = run(payload(self.V))
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn("沒歸位", ctx)
        self.assertFalse(hasattr(_checks_module(), "line_inbox"))

    def test_opening_does_not_compare_files(self):
        """放寬丙 3b：開場不再比對來源；有新檔也沒有變動行、沒有整理指示（每句開頭才比）。"""
        (self.raw / "客戶案件" / "新.txt").write_text("新", encoding="utf-8")
        r = run(payload(self.V))
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        head = ctx.split(chr(10) + chr(10), 1)[0]
        self.assertNotIn("有變動", head)
        self.assertEqual(head.split(chr(10)), [KB_LINE])

    def test_defaults_have_no_inbox_remind_keys(self):
        data = json.loads((ROOT / "config" / "defaults.json").read_text(encoding="utf-8"))
        self.assertEqual([k for k in data if "inbox_remind" in k], [])


class OpeningCardEdits(unittest.TestCase):
    """手改卡跟著更新（D-270 驗收 7）：有她改過的卡開場多一行，沒有就沒有；比對超過時限 more 為 true、開場照出。"""

    CARD = "檔案索引/公司行政/報稅時程表-647d76ee.md"
    TEXT = "---\n編號: f-647d76ee\n標題: 報稅時程表\n卡型: 表單\n---\n# 報稅時程表\n\n- 總價 5.5 萬〔第 1 段〕\n"

    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        p = self.V / self.CARD
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.TEXT, encoding="utf-8", newline="\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def lines(self):
        return turn_lines(self.V)  # 放寬丙 3b：手改卡的提醒挪到每句開頭

    def edit_lines(self, lines):
        return [ln for ln in lines if "kb cards edits" in ln]

    def hand_edit(self, n=1):
        (self.V / self.CARD).write_text(self.TEXT.replace("5.5 萬", "6 萬"), encoding="utf-8", newline="\n")

    def test_first_open_silent_then_baseline_exists(self):
        """驗收 1：沒有 card_base.json 的庫開場不報手改，開完每張卡都有基準。"""
        self.assertEqual(self.edit_lines(self.lines()), [])
        base = json.loads((self.V / ".system" / "card_base.json").read_text(encoding="utf-8"))
        self.assertIn(self.CARD, base["cards"])

    def test_line_when_edited(self):
        self.lines()  # 第一次開：補基準
        self.hand_edit()
        got = self.edit_lines(self.lines())
        self.assertEqual(got, ["客戶在 Obsidian 改了 1 張卡（kb cards edits）：先照 note skill 處理完再回答；那是客戶的意思，照做、不跟客戶提指令名。"])

    def test_no_line_after_done(self):
        self.lines()
        self.hand_edit()
        r = subprocess.run([sys.executable, str(KB), "cards", "edits", "--done", self.CARD], capture_output=True,
                           text=True, encoding="utf-8", cwd=str(self.V), env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.edit_lines(self.lines()), [])

    def test_over_time_budget_says_maybe_more(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("hook_checks_edits", ROOT / "hooks" / "_checks.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.lines()  # 補基準
        self.hand_edit()
        line, done = mod.line_card_edits(self.V, deadline=time.monotonic() - 1000)  # 假時鐘：時限早就過了
        self.assertFalse(done)
        self.assertEqual(line,  # 一張都沒比到：不知道有沒有，照 spec 說「可能有」（裁定 5 #5）
                         "可能有客戶改過的卡（kb cards edits）：先跑一次看看，有的話先照 note skill 處理完再回答；那是客戶的意思，照做、不跟客戶提指令名。")
        log = (self.V / ".system" / "hook-errors.log")
        self.assertFalse(log.exists() and "card_base" in log.read_text(encoding="utf-8"))

    def test_more_wording(self):
        """時限內沒比完、已經找到的先講，加「可能還有」。"""
        import importlib.util
        from kb._lib import card_base
        spec = importlib.util.spec_from_file_location("hook_checks_more", ROOT / "hooks" / "_checks.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.lines()
        orig = card_base.edits
        card_base.edits = lambda vault, deadline=None, persist=True: {"edits": [{"path": self.CARD}] * 2, "more": True}
        try:
            self.assertEqual(mod.line_card_edits(self.V)[0],
                             "客戶在 Obsidian 改了 2 張卡（可能還有，kb cards edits）：先照 note skill 處理完再回答；那是客戶的意思，照做、不跟客戶提指令名。")
        finally:
            card_base.edits = orig
