"""彈性區（#21，D-509～D-513）黑箱：驗收準則 1～15 各至少一個測試。夾名一律從 areas.FREE_DIR 取，不寫字面（驗收 2）。
守門用 guard.decide 或真的跑 hooks/guard.py；知識庫用 tests/fixtures 的假總資料夾或 kb init 新建。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from tests import _backup, _produce
from tests._guard_fixture import KB, ROOT, make_vault, payload
from tests.test_hooks_guard import run_hook
from tests.test_type_dirs import Base as TypeBase, kb as kb_type, legacy_vault, top_dirs, uris
from tests.test_scripts_upgrade_cli import Base as UpgradeBase, run_inproc
from kb import guard  # noqa: E402
from kb._lib import backup, batches, build, cards, journal, migrate, profile, restore, skeleton, turn  # noqa: E402
from kb._lib.areas import FREE_DIR  # noqa: E402

A, B = "sid-free-a", "sid-free-b"
AGENT = "a0204e72"


def run_kb(*args, cwd, sid=None):
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT), PYTHONIOENCODING="utf-8")
    head = ["--session", sid] if sid else []
    return subprocess.run([sys.executable, str(KB), *head, *args], capture_output=True, text=True,
                          encoding="utf-8", cwd=str(cwd), env=env)


class FixtureVault(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        self.F = self.V / FREE_DIR
        self.F.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def decide(self, tool, value, cwd=None):
        return guard.decide(payload(tool, value, cwd or self.V))

    def put(self, name, text="內容\n"):
        p = self.F / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p


# ---------- 1、2 骨架與常數 ----------

class Skeleton(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kbfree-")).resolve()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def files(V):
        """骨架與設定檔（.system 的留痕、回合與工作日誌每次跑都會變，不比）。"""
        return {p.relative_to(V).as_posix(): p.read_bytes() for p in V.rglob("*")
                if p.is_file() and p.relative_to(V).parts[0] != ".system" and p.parent.name != "工作日誌"}

    def test_1_init_makes_it_and_check_lists_it(self):
        V = self.tmp / "kb"
        r = run_kb("init", str(V), "--check", cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(FREE_DIR, r.stdout)
        r = run_kb("init", str(V), cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((V / FREE_DIR).is_dir())
        self.assertFalse((V / FREE_DIR / ".gitkeep").exists())

    def test_1_existing_vault_only_gets_the_folder(self):
        V = self.tmp / "kb"
        run_kb("init", str(V), cwd=self.tmp)
        shutil.rmtree(V / FREE_DIR)
        before = self.files(V)
        r = run_kb("init", str(V), cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((V / FREE_DIR).is_dir())
        self.assertEqual(before, self.files(V))

    def test_2_static_files_match_constant(self):
        self.assertTrue((ROOT / "skeleton" / FREE_DIR / ".gitkeep").is_file())
        core = (ROOT / "rules" / "core.md").read_text(encoding="utf-8")
        r01 = next(line for line in core.splitlines() if line.startswith("- R-01 "))
        self.assertIn(f"{FREE_DIR}是客戶自己的：平常不讀不搜，她問到或指名才讀，寫用檔案工具；"
                      "卡、成品、客戶原檔的副本不放這裡。", r01)
        sk = (ROOT / "skeleton" / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("第一層有六區：", sk)
        self.assertIn(f"- {FREE_DIR}：客戶自己的空間；平常不讀，客戶問到或指名才讀。", sk)

    def test_2_name_written_only_in_areas(self):
        hits = []
        for base in ("scripts", "hooks"):
            for p in (ROOT / base).rglob("*.py"):
                if f'"{FREE_DIR}"' in p.read_text(encoding="utf-8"):
                    hits.append(p.relative_to(ROOT).as_posix())
        self.assertEqual(hits, ["scripts/kb/_lib/areas.py"])


# ---------- 3～5 守門 ----------

class GuardRead(FixtureVault):
    def test_3_file_tools_read_allow_z12(self):
        p = self.put("筆記.md")
        for tool, value in (("Read", p), ("Glob", self.F), ("Grep", self.F)):
            d = self.decide(tool, value)
            self.assertEqual((d.decision, d.zone), ("allow", "Z12"), tool)

    def test_3_shell_read_not_denied(self):
        p = self.put("筆記.md")
        d = self.decide("Bash", f'cat "{p}"')
        self.assertNotEqual(d.decision, "deny", d.reason)


class GuardWrite(FixtureVault):
    def test_4_write_allowed_and_backed_up(self):
        t = turn.start(self.V, A, "存一份到彈性區")["turn"]
        target = self.F / "筆記.md"
        data = dict(payload("Write", target, self.V), session_id=A)
        r = run_hook(data)
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "allow")
        rows = [e for e in turn.entries(self.V, t) if e["path"] == f"{FREE_DIR}/筆記.md"]
        self.assertEqual([e["action"] for e in rows], ["create"])

    def test_4_shell_write_denied(self):
        d = self.decide("Bash", f'echo x > "{self.F / "a.txt"}"')
        self.assertEqual((d.decision, d.reason_code), ("deny", "shell_write"))
        d = self.decide("PowerShell", f'Set-Content -Path "{self.F / "a.txt"}" -Value x')
        self.assertEqual((d.decision, d.reason_code), ("deny", "shell_write"))


class GuardCredential(FixtureVault):
    def test_5_password_file_read_denied(self):
        p = self.put("密碼.txt")
        d = self.decide("Read", p)
        self.assertEqual((d.decision, d.reason_code), ("deny", "credential"))
        d = self.decide("Bash", f'cat "{p}"')
        self.assertEqual((d.decision, d.reason_code), ("deny", "credential"))

    def test_5_grep_whole_vault_scans_free_area(self):
        self.put("筆記.md")
        d = self.decide("Grep", self.V)
        self.assertNotEqual(d.decision, "deny", d.reason)
        self.put("子夾/帳密.xlsx")
        d = self.decide("Grep", self.V)
        self.assertEqual((d.decision, d.reason_code), ("deny", "credential_inside"))
        self.assertIn(f"{FREE_DIR}/子夾/帳密.xlsx", d.reason)
        d = self.decide("Grep", self.F)
        self.assertEqual((d.decision, d.reason_code), ("deny", "credential_inside"))
        d = self.decide("Bash", f'grep -r 保固 "{self.V}"')
        self.assertEqual((d.decision, d.reason_code), ("deny", "credential_inside"))

    def test_5_search_without_path_walks_free_area(self):
        """review #1：grep -r、rg 沒給路徑時效用 cwd 是範圍；在知識庫根或彈性區裡也要走訪彈性區。"""
        self.put("子夾/密碼.txt")
        for cmd, cwd in (("grep -r abc", self.V), ("rg abc", self.V), ("grep -r abc", self.F)):
            d = self.decide("Bash", cmd, cwd)
            self.assertEqual((d.decision, d.reason_code), ("deny", "credential_inside"), (cmd, cwd))

    def test_5_other_zones_still_not_walked(self):
        (self.V / "AI 產出" / "帳密.xlsx").write_text("x", encoding="utf-8")
        d = self.decide("Grep", self.V)
        self.assertNotEqual(d.decision, "deny", d.reason)


# ---------- 6 製卡助手 ----------

class Agent(FixtureVault):
    def setUp(self):
        super().setUp()
        self.job = turn.start(self.V, A, "好，現在做")["turn"]
        batches.agent_start(self.V, A, AGENT)

    def hook(self, tool, value, agent=True, **extra):
        data = dict(payload(tool, value, self.V), session_id=A)
        data["tool_input"].update(extra)
        if agent:
            data.update(agent_id=AGENT, agent_type="wiki-with-willy:card-maker")
        r = run_hook(data)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["hookSpecificOutput"]

    def test_6_agent_cannot_touch_free_area(self):
        p = self.put("筆記.md")
        for tool in ("Read", "Write"):
            out = self.hook(tool, p)
            self.assertEqual(out["permissionDecision"], "deny", tool)
        out = self.hook("Bash", f'python "{ROOT}/scripts/kb.py" convert "{FREE_DIR}/筆記.md"')
        self.assertEqual(out["permissionDecision"], "deny")
        out = self.hook("Bash", f'python "{ROOT}/scripts/kb.py" convert "file://知識庫/{FREE_DIR}/筆記.md"')
        self.assertEqual(out["permissionDecision"], "deny", "review #2：uri 寫法也擋")

    def test_6_agent_search_containing_free_area_denied(self):
        """spec 裁定 4：製卡助手 Grep／Glob 的範圍包含彈性區根就擋；主對話照舊。"""
        self.put("筆記.md")
        out = self.hook("Grep", self.V, pattern="保固")
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("agent_scope", (self.V / ".system" / "ledger.tsv").read_text(encoding="utf-8"))
        self.assertEqual(self.hook("Grep", self.V / "檔案索引", pattern="保固")["permissionDecision"], "allow")
        self.assertEqual(self.hook("Grep", self.V, agent=False, pattern="保固")["permissionDecision"], "allow")
        for pattern in ("**/*.md", f"{FREE_DIR}/*", "_ex*/*.md", FREE_DIR):  # 只點名彈性區本身也擋（寧可多擋）
            self.assertEqual(self.hook("Glob", self.V, pattern=pattern)["permissionDecision"], "deny", pattern)
        for pattern in ("*.md", "檔案索引/**/*.md"):
            self.assertEqual(self.hook("Glob", self.V, pattern=pattern)["permissionDecision"], "allow", pattern)
        self.assertEqual(self.hook("Glob", self.V, agent=False, pattern="**/*.md")["permissionDecision"], "allow")

    def test_6_agent_search_bypasses_denied(self):
        """裁定 4 的 code-review：樣式帶 ..、絕對路徑、{…}、path 有萬用字元、path 在知識庫上層都算碰到彈性區。"""
        self.put("筆記.md")
        index = self.V / "檔案索引"
        cases = [("Glob", index, {"pattern": f"../{FREE_DIR}/**/*.md"}),
                 ("Glob", self.V, {"pattern": f"{self.F.as_posix()}/*.md"}),
                 ("Glob", self.V, {"pattern": f"{{{FREE_DIR},檔案索引}}/*.md"}),
                 ("Glob", self.V, {"pattern": f"@({FREE_DIR})/*"}),
                 ("Glob", f"{self.V.as_posix()}/_ex*", {"pattern": "*.md"}),
                 ("Grep", self.V.parent, {"pattern": "保固"})]
        for tool, path, extra in cases:
            out = self.hook(tool, path, **extra)
            self.assertEqual(out.get("permissionDecision"), "deny", (tool, path, extra))
        self.assertEqual(self.hook("Glob", index, pattern="../檔案索引/*.md")["permissionDecision"], "allow")

    def test_6_agent_reads_index_as_before(self):
        index = self.V / "檔案索引"
        out = self.hook("Glob", index)
        self.assertEqual(out["permissionDecision"], "allow")


# ---------- 7 退回 ----------

class Revert(FixtureVault):
    def write(self, sid, name, text):
        data = dict(payload("Write", self.F / name, self.V), session_id=sid)
        out = json.loads(run_hook(data).stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "allow")
        (self.F / name).write_text(text, encoding="utf-8")

    def test_7_revert_removes_new_file(self):
        turn.start(self.V, A, "存一份")
        self.write(A, "筆記.md", "11 月要談保固\n")
        r = run_kb("versions", "revert", cwd=self.V, sid=A)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.F / "筆記.md").exists())

    def test_7_revert_edit_restores_old_text(self):
        self.put("筆記.md", "舊的\n")
        turn.start(self.V, A, "改一下")
        self.write(A, "筆記.md", "新的\n")
        r = run_kb("versions", "revert", cwd=self.V, sid=A)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.F / "筆記.md").read_text(encoding="utf-8"), "舊的\n")

    def test_7_other_conversation_wrote_later_refuses(self):
        turn.start(self.V, A, "存一份")
        self.write(A, "筆記.md", "A 寫的\n")
        turn.start(self.V, B, "我也改")
        self.write(B, "筆記.md", "B 寫的\n")
        r = run_kb("versions", "revert", cwd=self.V, sid=A)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertEqual((self.F / "筆記.md").read_text(encoding="utf-8"), "B 寫的\n")


# ---------- 8 不盤點 ----------

class NotInventoried(FixtureVault):
    def test_8_scan_changes_todo_skip_it(self):
        for n in ("a.txt", "b.docx", "子夾/c.md"):
            self.put(n)
        r = run_kb("inventory", "scan", "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(FREE_DIR, r.stdout)
        r = run_kb("changes", cwd=self.V)
        self.assertNotIn(FREE_DIR, r.stdout)
        r = run_kb("cards", "todo", "--json", cwd=self.V)
        self.assertNotIn(FREE_DIR, r.stdout)
        self.assertNotIn(FREE_DIR, json.dumps(json.loads((self.V / ".system" / "inventory.json").read_text(
            encoding="utf-8")), ensure_ascii=False))


# ---------- 9 設定檔 ----------

class Profile(TypeBase):
    def test_9_not_reported_as_unlisted(self):
        (self.V / FREE_DIR / "筆記.md").write_text("x\n", encoding="utf-8")
        r = kb_type(self.V, "profile", "check", "--json")
        self.assertNotIn(FREE_DIR, json.loads(r.stdout).get("unlisted") or [])
        self.add_type("合約", "物")
        self.assertTrue((self.V / FREE_DIR).is_dir())
        self.assertEqual(profile.load(self.V)["types"][-1]["dir"], "03 合約")

    def test_9_type_folder_renamed_to_free_dir_not_adopted(self):
        shutil.rmtree(self.V / FREE_DIR)
        (self.V / "01 案子").rename(self.V / FREE_DIR)
        st = profile.status(self.V)
        self.assertEqual(st.get("renamed") or [], [])
        self.assertNotIn(FREE_DIR, st.get("unlisted") or [])
        turn.start(self.V, None, "")
        kb_type(self.V, "profile", "apply", code=None)
        self.assertTrue((self.V / FREE_DIR).is_dir(), "不收編彈性區")
        self.assertEqual(profile.load(self.V)["types"][0]["dir"], "01 案子")

    def test_9_type_named_free_dir(self):
        self.add_type(FREE_DIR, "物")
        self.assertEqual(profile.load(self.V)["types"][-1]["dir"], f"03 {FREE_DIR}")
        self.assertTrue((self.V / f"03 {FREE_DIR}").is_dir())
        self.assertTrue((self.V / FREE_DIR).is_dir(), "彈性區照留")

    def test_9_legacy_type_named_free_dir_keeps_its_folder(self):
        """review #4：升級前就有、夾名是型別名的那列（沒有 dir），補編號時把它的夾搬過去，不另建空夾。"""
        legacy = [{"name": FREE_DIR, "category": "物"}]
        (self.V / FREE_DIR / "某實體").mkdir(parents=True, exist_ok=True)
        plan = profile.dir_plan(self.V, legacy, legacy, number_legacy=True)
        self.assertEqual(plan["moves"], [(FREE_DIR, f"01 {FREE_DIR}")])
        self.assertEqual(plan["creates"], [])

    def test_9_dir_plan_never_keeps_free_dir(self):
        types = [{"name": "倉庫", "category": "物", "dir": FREE_DIR}]
        (self.V / FREE_DIR).mkdir(exist_ok=True)
        plan = profile.dir_plan(self.V, types, types)
        self.assertEqual(plan["types"][0]["dir"], "01 倉庫")
        self.assertIsNone(plan["refusal"])
        legacy = [{"name": FREE_DIR, "category": "物"}]
        self.assertEqual(profile.dir_plan(self.V, legacy, legacy)["refusal"], profile.FREE_TAKEN)


# ---------- 10 日誌 ----------

class Journal(unittest.TestCase):
    def test_10_changed_text_counts_free_area(self):
        changed = [{"path": f"{FREE_DIR}/a.md"}, {"path": f"{FREE_DIR}/子夾/b.txt"}, {"path": "AI 產出/x.docx"}]
        self.assertEqual(journal.changed_text(changed), f"AI 產出 1 份；{FREE_DIR} 2 份")


class JournalBlackBox(FixtureVault):
    def test_10_journal_recent_says_two(self):
        hook = ROOT / "hooks"
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))

        def run(name, data):
            subprocess.run([sys.executable, str(hook / name)], input=json.dumps(data, ensure_ascii=False),
                           capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT), env=env, check=True)
        run("turn.py", {"session_id": A, "cwd": str(self.V), "prompt": "記兩份", "hook_event_name": "UserPromptSubmit"})
        for n in ("a.md", "b.md"):
            data = dict(payload("Write", self.F / n, self.V), session_id=A)
            self.assertEqual(json.loads(run_hook(data).stdout)["hookSpecificOutput"]["permissionDecision"], "allow")
            (self.F / n).write_text("x\n", encoding="utf-8")
        run("stop.py", {"session_id": A, "cwd": str(self.V), "hook_event_name": "Stop", "last_assistant_message": "好"})
        r = run_kb("journal", "recent", cwd=self.V)
        self.assertIn(f"{FREE_DIR} 2 份", r.stdout)


# ---------- 11 convert ----------

class Convert(FixtureVault):
    def test_11_convert_reads_free_area(self):
        _produce.docx(self.F / "會議.docx", ["11 月要跟大同談保固"])
        before = (self.V / ".system" / "pending.json").read_text(encoding="utf-8") \
            if (self.V / ".system" / "pending.json").is_file() else None
        r = run_kb("convert", str(self.F / "會議.docx"), cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(".system", r.stdout)
        _produce.docx(self.F / "密碼.docx", ["x"])
        r = run_kb("convert", str(self.F / "密碼.docx"), cwd=self.V)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        from kb import convert
        self.assertIn(convert.CREDENTIAL, r.stdout)
        after = (self.V / ".system" / "pending.json").read_text(encoding="utf-8") \
            if (self.V / ".system" / "pending.json").is_file() else None
        self.assertEqual(before, after)


# ---------- 12 來源別名 ----------

class Sources(FixtureVault):
    def test_12_alias_and_exclude_refused(self):
        home = self.tmp / "home"  # tmp 在 %TEMP%（系統夾底下），家目錄指到別處（同 test_scripts_folders_cli）
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT), PYTHONIOENCODING="utf-8", USERPROFILE=str(home), HOME=str(home))
        (self.raw / "新的").mkdir()
        r = subprocess.run([sys.executable, str(KB), "folders", "add", "../raw/新的", "--alias", FREE_DIR],
                           capture_output=True, text=True, encoding="utf-8", cwd=str(self.V), env=env)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("保留字", r.stdout)
        (self.F / "x").mkdir()
        r = run_kb("folders", "exclude", f"{FREE_DIR}/x", "--kind", "unused", cwd=self.V)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("知識庫裡的夾不能設成不讀", r.stdout)


# ---------- 13 建置 ----------

class Build(FixtureVault):
    def test_13_finish_refused_while_not_empty(self):
        data = {"report": True}
        self.put("交接.md")
        with self.assertRaises(build.Refused) as cm:
            build._check(self.V, data, "finish")
        self.assertEqual(str(cm.exception), f"交貨前{FREE_DIR}要是空的：還有 1 份")
        self.assertEqual(build.report_facts(self.V)["free_files"], 1)
        (self.F / "交接.md").unlink()
        (self.F / ".gitkeep").write_text("", encoding="utf-8")
        (self.F / "desktop.ini").write_text("", encoding="utf-8")  # review #6：檔案總管留的看不到的檔不算
        (self.F / "Thumbs.db").write_bytes(b"x")
        (self.F / "空子夾").mkdir()
        build._check(self.V, data, "finish")
        self.assertEqual(build.report_facts(self.V)["free_files"], 0)


# ---------- 14 備份還原 ----------

class Restore(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, _raw = _backup.make_vault()
        self.F = self.V / FREE_DIR
        self.F.mkdir()
        (self.F / "廠商.md").write_text("大同\n", encoding="utf-8")
        (self.F / "會議.md").write_text("保固\n", encoding="utf-8")
        self.B = self.tmp / "備份"
        self.B.mkdir()
        self.zip = _backup.make_zip(self.V, self.B)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_14_free_area_any_case_is_not_a_type_folder(self):
        """spec 裁定 5：RESERVED_TOP 不分大小寫，_Extras 底下的同名卡不算綜合卡。"""
        shutil.rmtree(self.F)
        odd = self.V / FREE_DIR.capitalize() / "某人"
        odd.mkdir(parents=True)
        (odd / "某人.md").write_text("# 某人\n", encoding="utf-8")
        labels = restore._labels(self.V, [])
        self.assertFalse([k for k in labels["synthesis"] if k.casefold().startswith(FREE_DIR.casefold())])

    def test_14_zip_has_free_area_and_check_says_it(self):
        with zipfile.ZipFile(str(self.zip)) as z:
            self.assertIn(f"{FREE_DIR}/廠商.md", z.namelist())
        self.assertEqual(restore.check(self.V, str(self.zip))["free"], {"count": 0, "examples": []})
        (self.F / "廠商.md").write_text("大同與聲寶\n", encoding="utf-8")
        got = restore.check(self.V, str(self.zip))
        self.assertEqual(got["free"], {"count": 1, "examples": ["廠商.md"]})
        self.assertIn(f"{FREE_DIR}會變回備份那時的樣子：廠商.md", restore.lines(got))
        r = run_kb("restore", "check", str(self.zip), "--json", cwd=self.V)
        self.assertEqual(json.loads(r.stdout)["free"]["count"], 1)


# ---------- 15 升級 ----------

class Migrate(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.cid = legacy_vault()
        migrate.apply(self.V, turn.start(self.V, None, "")["turn"])  # 先補編號：01 案子、02 業主
        # 她自己把「01 案子」改名成彈性區的名字，舊版記下了這個夾名
        (self.V / "01 案子").rename(self.V / FREE_DIR)
        pj = self.V / profile.PROFILE_POSIX
        data = json.loads(pj.read_text(encoding="utf-8"))
        data["types"][0]["dir"] = FREE_DIR
        pj.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_15_type_folder_named_free_dir_goes_back_to_default(self):
        self.assertTrue([p for p in migrate.pending(self.V) if p["rel"] == profile.PROFILE_POSIX])
        got = migrate.apply(self.V, turn.start(self.V, None, "")["turn"])
        self.assertEqual(got["notes"], [f"型別夾「{FREE_DIR}」改成「01 案子」：這個名字現在是你自己的區"])
        self.assertEqual([t["dir"] for t in profile.load(self.V)["types"]], ["01 案子", "02 業主"])
        self.assertTrue((self.V / "01 案子" / "信義王" / "信義王.md").is_file())
        self.assertFalse((self.V / FREE_DIR).exists())
        self.assertIn("file://知識庫/01 案子/信義王/報價.txt", uris(self.V))
        rel = cards._scan_groups(self.V)[0][self.cid][0]["path"]
        self.assertTrue(rel.startswith("檔案索引/知識庫/01 案子/信義王/"), rel)
        self.assertEqual([p for p in migrate.pending(self.V) if p["rel"] == profile.PROFILE_POSIX], [])
        self.assertIn("01 案子", top_dirs(self.V))


class UpgradeLine(UpgradeBase):
    PLUGIN = "0.28.0"

    def setUp(self):
        super().setUp()
        self.root_sk = self.tmp / "skeleton"
        (self.root_sk / FREE_DIR).mkdir(parents=True)
        (self.root_sk / FREE_DIR / ".gitkeep").write_text("", encoding="utf-8")
        from kb import init
        self.sk = [mock.patch.object(skeleton, "skeleton_root", return_value=self.root_sk),
                   mock.patch.object(init, "skeleton_root", return_value=self.root_sk),
                   mock.patch.object(skeleton, "history", return_value={})]
        for p in self.sk:
            p.start()
        shutil.rmtree(self.V / ".claude", ignore_errors=True)

    def tearDown(self):
        for p in self.sk:
            p.stop()
        super().tearDown()

    def pend(self, cur):
        self.put_history(cur, pending={"to": self.PLUGIN, "snapshot": backup.snapshot(self.V, "upgrade").name,
                                       "started": "2026-10-24T10:00:00"})

    def test_15_own_folder_kept_and_said_once(self):
        (self.V / FREE_DIR).mkdir()
        (self.V / FREE_DIR / "她的.txt").write_text("x\n", encoding="utf-8")
        self.pend("0.27.1")
        code, out = run_inproc(["upgrade", "--finish"], self.V)
        self.assertEqual(code, 0, out)
        self.assertIn(f"第一層的「{FREE_DIR}」現在是你自己的區：我平常不讀，你問到才讀。", out.splitlines())
        self.assertTrue((self.V / FREE_DIR / "她的.txt").is_file())
        self.PLUGIN = "0.28.1"
        code, out = run_inproc(["upgrade", "--finish"], self.V)
        self.assertEqual(code, 0, out)
        self.assertNotIn("現在是你自己的區", out)

    def test_15_no_line_when_folder_was_not_there(self):
        self.pend("0.27.1")
        code, out = run_inproc(["upgrade", "--finish"], self.V)
        self.assertEqual(code, 0, out)
        self.assertNotIn("現在是你自己的區", out)
        self.assertTrue((self.V / FREE_DIR).is_dir(), "init 補上夾")


if __name__ == "__main__":
    unittest.main()
