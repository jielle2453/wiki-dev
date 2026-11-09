"""背景比對（#60、#61，D-536）：kb changes --background 寫 .system/local/changes.json；kb changes、kb inventory scan 跟著更新；
每句開頭只讀清單（hooks/_checks.file_compare、line_wip、卡的手改用清單的 cards_mtime）。"""
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from tests._guard_fixture import ROOT, make_vault
from kb._lib import changes_list

KB = ROOT / "scripts" / "kb.py"


def kb(vault, *args, executable=None):
    return subprocess.run([executable or sys.executable, str(KB), *args], capture_output=True, text=True, encoding="utf-8",
                          cwd=str(vault), env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)))


def checks_module():
    import importlib.util
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("hook_checks_list", ROOT / "hooks" / "_checks.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        (self.raw / "行政" / "請款" / "r.docx").write_bytes(b"PK fake request")
        r = kb(self.V, "inventory", "scan")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        changes_list.path(self.V).unlink(missing_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def listed(self):
        return json.loads(changes_list.path(self.V).read_text(encoding="utf-8"))

    def background(self):
        r = kb(self.V, "changes", "--background", "--vault", str(self.V))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        return r


class Background(Base):
    def test_writes_list_silently(self):
        (self.raw / "客戶案件" / "新.txt").write_text("新\n", encoding="utf-8")
        (self.raw / "行政" / "請款" / "r.docx").unlink()
        self.background()
        d = self.listed()
        self.assertEqual((d["schema_version"], d["via"]), (1, "background"))
        self.assertEqual([u.rsplit("/", 1)[-1] for u in d["report"]["added"]], ["新.txt"])
        self.assertEqual([u.rsplit("/", 1)[-1] for u in d["report"]["missing"]], ["r.docx"])
        self.assertTrue(d["report"]["ids"][d["report"]["missing"][0]].startswith("f-"))
        self.assertNotIn("entries", d["report"])
        self.assertIsInstance(d["wip"]["n"], int)
        self.assertLessEqual(len(d["wip"]["names"]), 3)
        self.assertIsInstance(d["cards_mtime"], float)
        self.assertGreaterEqual(d["seconds"], 0)
        self.assertFalse(list(changes_list.path(self.V).parent.glob("*.tmp")))

    def test_fresh_lock_skips_stale_lock_runs(self):
        lock = self.V / changes_list.LOCK_REL
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("x", encoding="utf-8")
        self.background()
        self.assertFalse(changes_list.path(self.V).exists(), "30 分鐘內有一個在跑就直接結束")
        old = time.time() - 31 * 60
        os.utime(lock, (old, old))
        self.background()
        self.assertTrue(changes_list.path(self.V).exists())
        self.assertFalse(lock.exists(), "跑完放掉鎖")

    def test_newer_list_is_not_overwritten(self):
        """review 3：比的期間 AI 當場比過或套用了（清單比背景開始時新），背景的舊結果不蓋過去。"""
        self.assertEqual(kb(self.V, "changes").returncode, 0)
        d = self.listed()
        d["at"] = "2999-01-01T00:00:00"
        changes_list.path(self.V).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        self.background()
        self.assertEqual(self.listed()["via"], "changes")

    def test_error_logged_as_scan_exit_0(self):
        (self.V / ".system" / "sources.json").write_text("{壞", encoding="utf-8")
        self.background()
        log = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual([ln.split("\t")[1] for ln in log], ["scan"])
        self.assertFalse(changes_list.path(self.V).exists())

    def test_stdout_none_does_not_break(self):
        """驗收 10：pythonw 跑的 stdout、stderr 是 None。"""
        code = ("import os, sys, runpy\nkb, v = sys.argv[1], sys.argv[2]\nsys.path.insert(0, os.path.dirname(kb))\n"
                "sys.stdout = None\nsys.stderr = None\n"
                "sys.argv = [kb, 'changes', '--background', '--vault', v]\ntry:\n    runpy.run_path(kb, run_name='__main__')\n"
                "except SystemExit as e:\n    open(v + '/exit.txt', 'w').write(str(e.code))")
        r = subprocess.run([sys.executable, "-c", code, str(KB), str(self.V)], capture_output=True, text=True, encoding="utf-8",
                           cwd=str(self.V))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.V / "exit.txt").read_text(), "0")
        self.assertEqual(self.listed()["via"], "background")


class Foreground(Base):
    def test_changes_writes_list_and_carries_wip(self):
        """驗收 6、實作疑義 1：AI 當場跑 kb changes 也寫清單（via changes），wip、cards_mtime 沿用舊清單。"""
        self.background()
        old = self.listed()
        (self.raw / "客戶案件" / "新.txt").write_text("新\n", encoding="utf-8")
        r = kb(self.V, "changes", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("新.txt", r.stdout)
        d = self.listed()
        self.assertEqual(d["via"], "changes")
        self.assertGreaterEqual(d["at"], old["at"])
        self.assertEqual((d["wip"], d["cards_mtime"]), (old["wip"], old["cards_mtime"]))
        self.assertIn("新.txt", json.dumps(d["report"]["added"], ensure_ascii=False))

    def test_no_old_list_writes_null(self):
        self.assertEqual(kb(self.V, "changes").returncode, 0)
        d = self.listed()
        self.assertEqual((d["via"], d["wip"], d["cards_mtime"]), ("changes", None, None))

    def test_quick_incomplete_does_not_write(self):
        (self.V / ".system" / "config.json").write_text(json.dumps({"changes_quick_hash_budget_bytes": 1}), encoding="utf-8")
        (self.raw / "客戶案件" / "a.txt").write_text("改過了，長度不一樣\n", encoding="utf-8")
        self.assertEqual(kb(self.V, "changes", "--quick").returncode, 0)
        self.assertFalse(changes_list.path(self.V).exists())

    def test_inventory_scan_writes_empty_report(self):
        """驗收 7：套用後清單的新增、修改、不見都是空的；之前就不見的留在 still_missing。帶 --source 的不寫。"""
        (self.raw / "客戶案件" / "新.txt").write_text("新\n", encoding="utf-8")
        (self.raw / "行政" / "請款" / "r.docx").unlink()
        self.assertEqual(kb(self.V, "inventory", "scan", "--source", "客戶案件").returncode, 0)
        self.assertFalse(changes_list.path(self.V).exists())
        self.assertEqual(kb(self.V, "inventory", "scan").returncode, 0)
        d = self.listed()
        self.assertEqual(d["via"], "inventory scan")
        self.assertEqual([d["report"][k] for k in ("added", "modified", "missing", "moved")], [[], [], [], []])
        self.assertTrue(any(u.endswith("r.docx") for u in d["report"]["still_missing"]))


class Read(Base):
    def test_bad_or_other_schema_is_no_list(self):
        p = changes_list.path(self.V)
        p.parent.mkdir(parents=True, exist_ok=True)
        for text in ("{壞", json.dumps({"schema_version": 2, "report": {}}), "[]"):
            p.write_text(text, encoding="utf-8")
            self.assertIsNone(changes_list.read(self.V))
            self.assertIsNone(changes_list.compare(self.V))

    def test_compare_restores_report_shape(self):
        shutil.move(self.raw / "客戶案件" / "a.txt", self.raw / "行政" / "a.txt")
        self.background()
        sources, report = changes_list.compare(self.V)
        self.assertEqual(len(report["moved"]), 1)
        old, new = report["moved"][0]
        self.assertTrue(old.endswith("客戶案件/a.txt") and new.endswith("行政/a.txt"))
        from kb._lib import inventory
        (row,) = inventory.detected_rows(sources, report, by="outside")
        self.assertTrue(row["id"].startswith("f-"))

    def test_hooks_read_list_not_scan(self):
        """驗收 5：新檔在跑背景之前那一句沒有；跑完下一句有 WIP_LINE。"""
        m = checks_module()
        (self.raw / "客戶案件" / "新.txt").write_text("新\n", encoding="utf-8")
        self.assertIsNone(m.file_compare(self.V))
        self.background()
        m = checks_module()
        lines, _told = m.change_lines(self.V)
        self.assertEqual(lines, [m.WIP_LINE.format(n=1)])

    def test_null_wip_and_cards_mtime_mean_unknown(self):
        """實作疑義 1：null 當不知道：line_wip 不印、卡的手改這句不比。"""
        self.assertEqual(kb(self.V, "changes").returncode, 0)
        m = checks_module()
        self.assertIsNone(m.line_wip(self.V))
        self.assertIsNone(m.listed_cards_mtime(self.V))

    def test_line_wip_from_list(self):
        p = changes_list.path(self.V)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {"schema_version": 1, "at": "2026-11-10T10:00:00", "seconds": 1.0, "via": "background",
                "report": {"added": [], "modified": [], "missing": [], "still_missing": [], "moved": [], "missing_sources": [],
                           "incomplete": False, "ids": {}},
                "wip": {"n": 5, "names": ["甲.xlsx", "乙.docx", "丙.pdf"]}, "cards_mtime": 123.0}
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        m = checks_module()
        self.assertEqual(m.line_wip(self.V), m.WIP_DAILY.format(n=5, names="甲.xlsx、乙.docx、丙.pdf…"))
        self.assertEqual(m.listed_cards_mtime(self.V), 123.0)
        data["wip"] = {"n": 0, "names": []}
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.assertIsNone(checks_module().line_wip(self.V))


class Removed(unittest.TestCase):
    def test_no_old_names_left(self):
        """驗收 12。"""
        r = subprocess.run(["git", "grep", "-n", "-E", "after_answer|stop_scan_seconds|turn_scan_hash_budget_bytes|CHANGES_INCOMPLETE",
                            "--", "hooks", "scripts", "config"], capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT))
        self.assertEqual(r.stdout, "")


if __name__ == "__main__":
    unittest.main()
