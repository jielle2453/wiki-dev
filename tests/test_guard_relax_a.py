"""放寬甲第一輪（spec 驗收 1～10）：守門對使用者區放行、救不回的才擋、willy 自己的區照舊；句子寫給 AI。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests._guard_fixture import HOOK, KB, ROOT, payload
from kb import guard  # noqa: E402

TAIL = "不用跟使用者提這一步。"


def make_kb():
    tmp = Path(tempfile.mkdtemp(prefix="kbrelax-"))
    vault = tmp / "V"
    subprocess.run([sys.executable, str(KB), "init", str(vault)], check=True, capture_output=True)
    (vault / "我的夾").mkdir()
    (vault / "我的夾" / "a.txt").write_text("a", encoding="utf-8")
    (vault / "我的夾" / "b.txt").write_text("b", encoding="utf-8")
    (vault / "暫存區" / "空夾").mkdir()
    (vault / "暫存區" / "c.txt").write_text("c", encoding="utf-8")
    (vault / "01 案子").mkdir()
    (tmp / "ext").mkdir()
    (tmp / "src").mkdir()
    (tmp / "src" / "x.txt").write_text("x", encoding="utf-8")
    sj = vault / ".system" / "sources.json"
    data = json.loads(sj.read_text(encoding="utf-8"))
    data["sources"].append({"id": "src-0001", "alias": "來源", "spec": "../src", "excludes": []})
    sj.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return tmp, vault


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp, cls.V = make_kb()
        os.environ["CLAUDE_PLUGIN_ROOT"] = str(ROOT)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def d(self, tool, value, cwd=None):
        return guard.decide(payload(tool, value, cwd or self.V))

    def passes(self, tool, cmd, cwd=None):
        d = self.d(tool, cmd, cwd)
        self.assertIn(d.decision, ("pass", "allow"), (cmd, d))
        return d

    def denies(self, tool, cmd, code, cwd=None):
        d = self.d(tool, cmd, cwd)
        self.assertEqual((d.decision, d.reason_code), ("deny", code), (cmd, d))
        self.assertTrue(d.reason.endswith(TAIL), d.reason)
        return d


class ShellRules(Base):
    def test_1_creating_and_moving_pass(self):
        self.passes("Bash", 'rmdir "暫存區/空夾"')
        self.passes("Bash", "mkdir 新的夾")
        self.passes("Bash", "mv 我的夾/a.txt 暫存區/")
        self.passes("Bash", 'mv 我的夾/a.txt "01 案子/"')

    def test_2_delete(self):
        d = self.denies("Bash", "rm 我的夾/a.txt", "delete")
        self.assertIn("kb source-edit trash", d.reason)
        self.denies("PowerShell", "Remove-Item 我的夾 -Recurse", "delete")

    def test_3_overwrite(self):
        d = self.denies("Bash", "mv 我的夾/a.txt 我的夾/b.txt", "overwrite")
        self.assertIn("--replace", d.reason)
        self.passes("Bash", "mv -n 我的夾/a.txt 我的夾/b.txt")
        self.passes("PowerShell", "Move-Item 我的夾/a.txt 我的夾/b.txt")
        self.denies("PowerShell", "Move-Item 我的夾/a.txt 我的夾/b.txt -Force", "overwrite")

    def test_4_content(self):
        self.denies("Bash", "echo x > 我的夾/a.txt", "content")
        self.passes("Bash", "echo x > 我的夾/new.txt")

    def test_5_batch(self):
        self.denies("Bash", 'for f in 我的夾/*.txt; do mv "$f" 暫存區/; done', "batch")
        self.passes("Bash", 'for f in 我的夾/*.txt; do mv -n "$f" 暫存區/; done')
        self.denies("Bash", 'for f in 我的夾/*.txt; do rm "$f"; done', "delete")

    def test_6_interpreter_code(self):
        ext = self.tmp / "ext" / "m.py"
        ext.write_text('import os; os.remove("我的夾/a.txt")', encoding="utf-8")
        self.denies("Bash", "python ../ext/m.py", "code")
        ext.write_text('import shutil; shutil.move("我的夾/a.txt", "暫存區/a.txt")', encoding="utf-8")
        self.passes("Bash", "python ../ext/m.py")
        out = str(self.tmp / "ext" / "out.csv")
        ext.write_text(f'open(r"{out}","w").write("x")', encoding="utf-8")
        d = self.passes("Bash", "python ../ext/m.py", cwd=self.tmp / "ext")
        self.assertEqual(d.decision, "pass")

    def test_6b_unread_script_logged(self):
        big = self.tmp / "ext" / "big.py"
        big.write_text("x = 1\n" + "#" * 2000000, encoding="utf-8")
        d = self.passes("Bash", "python ../ext/big.py")
        self.assertIn("script_unread", [r["reason_code"] for r in d.ledger_rows])

    def test_6c_bare_name_in_code(self):
        # 測試報告 #1：程式碼裡的名字沒斜線沒副檔名（'notes'），cwd 在知識庫時也要擋
        (self.V / "notes").write_text("n", encoding="utf-8")
        self.denies("Bash", "python -c \"import os; os.remove('notes')\"", "code")
        out = str(self.tmp / "ext" / "o.csv")
        self.denies("Bash", f"python -c \"import os,sys; os.remove('notes'); open(sys.argv[1],'w')\" {out}", "code")
        self.passes("Bash", f"python -c \"import sys; open(sys.argv[1],'w').write('x')\" {out}")

    def test_3b_powershell_named_param_is_not_noclobber(self):
        # 測試報告 #2：-Destination 含 n，不能當 -n
        self.denies("PowerShell", "copy 我的夾/a.txt -Destination 我的夾/b.txt", "overwrite")
        self.denies("PowerShell", "cp 我的夾/a.txt -Destination 我的夾/b.txt", "overwrite")
        self.passes("Bash", "cp -n 我的夾/a.txt 我的夾/b.txt")

    def test_7_file_tools(self):
        for tool, rel in (("Write", "我的夾/c.md"), ("Edit", "暫存區/c.txt"), ("Edit", "系統/客戶設定檔.md"),
                          ("Write", "01 案子/清單.xlsx"), ("Write", "_個人/x.md")):
            d = self.d(tool, self.V / rel)
            self.assertEqual(d.decision, "allow", (tool, rel, d))
        for rel in ("系統/日程.md", "總目錄.md", ".system/config.json", "CLAUDE.md"):
            d = self.d("Write", self.V / rel)
            self.assertEqual((d.decision, d.reason_code), ("deny", "willy"), (rel, d))
            self.assertTrue(d.reason.endswith(TAIL))

    def test_7b_z9_edit_allowed(self):
        d = self.d("Edit", self.tmp / "src" / "x.txt")
        self.assertEqual((d.decision, d.zone), ("allow", "Z9"), d)

    def test_willy_shell(self):
        self.denies("Bash", "echo x > 系統/日程.md", "willy")
        self.denies("Bash", "rm 檔案索引/x.md", "willy")

    def test_10_old_denials_stay(self):
        (self.tmp / "src" / "密碼.xlsx").write_text("x", encoding="utf-8")
        d = self.d("Read", self.tmp / "src" / "密碼.xlsx")
        self.assertEqual(d.reason_code, "credential")
        self.assertNotIn("客戶", d.reason)
        d = self.d("Bash", "rm ../ext/x.txt")
        self.assertIn(d.decision, ("pass", "allow"))

    def test_ledger_rows_for_denials(self):
        d = self.d("Bash", "rm 我的夾/a.txt")
        self.assertEqual([r["reason_code"] for r in d.ledger_rows], ["delete"])


class HoldZone(Base):
    """放寬甲第二輪 9（D-324）：Z3 併進 Z4（暫存區），Z3 不再出現；規則照第一輪的 Z4。舊夾名收件匣、AI 產出 現在只是使用者的夾（Z8）。"""

    def test_zone_table_has_no_z3(self):
        self.assertNotIn("Z3", guard.ZONES)
        self.assertNotIn("Z3", set(guard.RESERVED.values()))
        self.assertEqual(guard.ZONES["Z4"]["name"], "暫存區")

    def test_hold_is_z4_and_old_names_are_user_folders(self):
        from kb._lib.paths import normalize
        v = normalize(str(self.V), None)
        from kb._lib import sources as sources_lib
        sources = sources_lib.load(self.V)
        self.assertEqual(guard.classify(normalize(str(self.V / "暫存區" / "c.txt"), None), v, sources)[0], "Z4")
        for old in ("收件匣", "AI 產出"):
            self.assertEqual(guard.classify(normalize(str(self.V / old / "a.txt"), None), v, sources)[0], "Z2", old)

    def test_file_tools_and_shell_follow_user_zone_rules(self):
        d = self.d("Edit", self.V / "暫存區" / "c.txt")
        self.assertEqual((d.decision, d.zone), ("allow", "Z4"), d)
        self.passes("Bash", 'rmdir "暫存區/空夾"')
        self.denies("Bash", "rm 暫存區/c.txt", "delete")
        self.passes("Bash", "cat 暫存區/c.txt")


class VaultExcludes(Base):
    """一.6：知識庫裡使用者的夾設成不讀（sources.json 頂層 vault_excludes），由 Sources 解析，守門回 Z10／Z10b。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        sj = cls.V / ".system" / "sources.json"
        data = json.loads(sj.read_text(encoding="utf-8"))
        data["vault_excludes"] = [{"spec": "我的夾", "kind": "hidden"}]
        sj.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        (cls.V / "01 案子" / "王宅").mkdir()
        (cls.V / "01 案子" / "王宅" / "x.txt").write_text("x", encoding="utf-8")
        data["vault_excludes"].append({"spec": "01 案子/王宅", "kind": "unused"})
        sj.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_excluded_dir(self):
        for tool, rel in (("Read", "我的夾/a.txt"), ("Write", "我的夾/new.txt"), ("Edit", "01 案子/王宅/x.txt")):
            d = self.d(tool, self.V / rel)
            self.assertEqual((d.decision, d.zone, d.reason_code), ("deny", "Z10", "excluded"), (rel, d))
            self.assertTrue(d.reason.endswith(TAIL))

    def test_shell_into_excluded(self):
        self.denies("Bash", "mv 暫存區/c.txt 我的夾/", "excluded")

    def test_range_containing_excluded(self):
        d = self.d("Glob", self.V / "01 案子")
        self.assertEqual((d.decision, d.reason_code), ("deny", "excluded_inside"), d)

    def test_other_folders_unaffected(self):
        d = self.d("Read", self.V / "暫存區" / "c.txt")
        self.assertEqual(d.decision, "allow", d)

    def test_sources_parse(self):
        from kb._lib import sources as S
        s = S.load(self.V)
        self.assertEqual(len(s.vault_excludes), 2)
        self.assertEqual([e["alias"] for e in s.entries], ["來源"])  # 沒有假來源

    def test_bad_vault_excludes_rejected(self):
        from kb._lib import sources as S
        sj = self.V / ".system" / "sources.json"
        good = sj.read_text(encoding="utf-8")
        try:
            data = json.loads(good)
            data["vault_excludes"] = "x"
            sj.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                S.load_raw(self.V)
        finally:
            sj.write_text(good, encoding="utf-8")


class HookRun(unittest.TestCase):
    """驗收 7b、8、9：hook 實跑（subprocess 餵 payload）。"""
    SID = "relax-sid"

    def setUp(self):
        self.tmp, self.V = make_kb()
        os.environ["CLAUDE_PLUGIN_ROOT"] = str(ROOT)
        from kb._lib import turn
        self.turn = turn
        self.t = turn.start(self.V, self.SID, "改一下")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def hook(self, tool, value):
        data = payload(tool, value, self.V)
        data["session_id"] = self.SID
        r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(data, ensure_ascii=False), capture_output=True,
                           text=True, encoding="utf-8", cwd=str(ROOT), env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def vdir(self):
        return self.V / ".system" / "versions" / self.t["turn"]

    def test_7b_edit_inbox_backs_up(self):
        r = self.hook("Edit", self.V / "暫存區" / "c.txt")
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "allow")
        rows = [e for e in self.turn.entries(self.V, self.t["turn"]) if e["path"] == "暫存區/c.txt"]
        self.assertEqual([e["action"] for e in rows], ["modify"])
        self.assertEqual((self.vdir() / "files" / "暫存區" / "c.txt").read_text(encoding="utf-8"), "c")

    def test_8_z9_edit_backup_and_revert(self):
        f = self.tmp / "src" / "x.txt"
        r = self.hook("Edit", f)
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "allow")
        rows = [e for e in self.turn.entries(self.V, self.t["turn"]) if e.get("uri")]
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["uri"], "file://來源/x.txt")
        self.assertEqual(rows[0]["path"], "_src/來源/x.txt")
        self.assertEqual((self.vdir() / "files" / "_src" / "來源" / "x.txt").read_text(encoding="utf-8"), "x")
        f.write_text("改過了", encoding="utf-8")  # 模擬 Edit 真的改了
        r = subprocess.run([sys.executable, str(KB), "versions", "revert"], cwd=str(self.V), capture_output=True, text=True,
                           encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(f.read_text(encoding="utf-8"), "x")

    def test_9_no_shell_writes_jsonl(self):
        r = self.hook("Bash", "mv 我的夾/a.txt 暫存區/")
        out = json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] if r.stdout.strip() else "pass"
        self.assertIn(out, ("pass", "allow"))
        self.assertEqual(list(self.vdir().rglob("shell_writes.jsonl")), [])
        self.assertEqual(list((self.V / ".system").rglob("shell_writes.jsonl")), [])
        rows = self.ledger_rows()
        self.assertTrue(all(r["decision"] != "deny" for r in rows), rows)

    def ledger_rows(self):
        p = self.V / ".system" / "ledger.tsv"
        return [dict(zip(("time", "tool", "decision", "zone", "reason_code", "head"), ln.split("	")))
                for ln in p.read_text(encoding="utf-8").splitlines()[1:]] if p.is_file() else []


if __name__ == "__main__":
    unittest.main()
