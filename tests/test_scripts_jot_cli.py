"""kb jot（Obsidian 首頁的隨手記，#22，D-267、裁定 35）黑箱：subprocess 跑 kb.py，知識庫用 kb init 建。
內容一行、去頭尾空白、不收空的、2000 字內；接在 <FREE_DIR>/隨手記.md 最下面；寫前備進回合；--via obsidian 退得回來；Claude 不讀（日誌不抄內容）。"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests._guard_fixture import KB, ROOT
from kb._lib import journal  # noqa: E402
from kb._lib.areas import FREE_DIR  # noqa: E402

NOTE = f"{FREE_DIR}/隨手記.md"
LINE = re.compile(r"^- \d{4}-\d{2}-\d{2} \d{2}:\d{2} (.*)$")


def run_kb(*args, cwd, via=False):
    head = ["--via", "obsidian"] if via else []
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(KB), *head, *args], capture_output=True, text=True, encoding="utf-8", cwd=str(cwd), env=env)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kbjot-")).resolve()
        self.V = self.tmp / "kb"
        r = run_kb("init", str(self.V), cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.F = self.V / FREE_DIR

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def jot(self, *args, **kw):
        return run_kb("jot", *args, cwd=self.V, **kw)

    def lines(self):
        return (self.V / NOTE).read_text(encoding="utf-8").split("\n")


class Write(Base):
    def test_creates_the_page_with_header_and_one_line(self):
        r = self.jot("11 月要談保固")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "記下了"), r.stdout + r.stderr)
        got = self.lines()
        self.assertEqual(got[0:2], ["# 隨手記", ""])
        self.assertRegex(got[2], LINE)
        self.assertEqual(LINE.match(got[2]).group(1), "11 月要談保固")
        self.assertEqual(got[3:], [""], "最後一行有換行、沒有多的")

    def test_appends_at_the_bottom_and_keeps_one_header(self):
        self.jot("第一則")
        self.jot("第二則")
        got = [l for l in self.lines() if l]
        self.assertEqual(got[0], "# 隨手記")
        self.assertEqual([LINE.match(l).group(1) for l in got[1:]], ["第一則", "第二則"])

    def test_page_the_customer_wrote_is_kept_and_missing_final_newline_is_fixed(self):
        self.F.mkdir(exist_ok=True)
        (self.V / NOTE).write_text("# 隨手記\n\n- 2026-01-01 08:00 她自己寫的\n自己加的一行", encoding="utf-8")
        self.jot("新的")
        got = self.lines()
        self.assertEqual(got[:4], ["# 隨手記", "", "- 2026-01-01 08:00 她自己寫的", "自己加的一行"])
        self.assertEqual(LINE.match(got[4]).group(1), "新的")

    def test_creates_the_free_dir_if_it_is_missing(self):
        shutil.rmtree(self.F, ignore_errors=True)
        r = self.jot("沒有彈性區也行")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.V / NOTE).is_file())

    def test_lf_only_and_text_kept_as_is(self):
        self.jot("password: hunter2  abc=123", )
        raw = (self.V / NOTE).read_bytes()
        self.assertNotIn(b"\r", raw)
        self.assertIn("password: hunter2  abc=123".encode("utf-8"), raw, "她自己的筆記，不遮值")

    def test_json_output(self):
        r = run_kb("jot", "存一下", "--json", cwd=self.V)
        out = json.loads(r.stdout)
        self.assertEqual(out["path"], NOTE)
        self.assertRegex(out["line"], LINE)
        self.assertTrue(out["turn"])


class Input(Base):
    def test_empty_or_blank_is_refused_and_nothing_written(self):
        for text in ("", "   ", "\n\t\n"):
            r = self.jot(text)
            self.assertEqual((r.returncode, r.stdout.strip()), (3, "沒有內容可以記"), repr(text))
        self.assertFalse((self.V / NOTE).exists())

    def test_no_argument_is_refused(self):
        r = self.jot()
        self.assertEqual(r.returncode, 3)

    def test_newlines_become_one_line_and_ends_are_trimmed(self):
        self.jot("  第一行\r\n第二行\n\n第三行  ")
        got = [l for l in self.lines() if l.startswith("- ")]
        self.assertEqual(len(got), 1)
        self.assertEqual(LINE.match(got[0]).group(1), "第一行 第二行 第三行")

    def test_2000_chars_ok_2001_refused(self):
        self.assertEqual(self.jot("字" * 2000).returncode, 0)
        r = self.jot("字" * 2001)
        self.assertEqual(r.returncode, 3)
        self.assertIn("2000", r.stdout)
        self.assertEqual(len([l for l in self.lines() if l.startswith("- ")]), 1)

    def test_not_in_vault(self):
        with tempfile.TemporaryDirectory() as d:
            r = run_kb("jot", "x", cwd=Path(d))
        self.assertEqual(r.returncode, 3)

    def test_text_starting_with_a_dash_after_double_dash(self):
        r = self.jot("--json", "--", "-開頭的字")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(json.loads(r.stdout)["line"].endswith(" -開頭的字"))

    def test_plugin_knows_the_same_free_dir_name(self):
        """外掛（obsidian/main.js）讀隨手記那一頁用的夾名要跟 areas.FREE_DIR 一樣（改名時兩邊一起改）。"""
        main = (ROOT / "obsidian" / "main.js").read_text(encoding="utf-8")
        self.assertIn(f"const FREE_DIR = '{FREE_DIR}';", main)

    def test_help_lists_jot(self):
        self.assertIn("jot", run_kb("--help", cwd=self.V).stdout)


class Undo(Base):
    def turn_of(self, r):
        return json.loads(r.stdout)["turn"]

    def test_via_obsidian_new_page_revert_removes_it(self):
        r = self.jot("只有這一則", "--json", via=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        back = run_kb("versions", "revert", self.turn_of(r), cwd=self.V, via=True)
        self.assertEqual(back.returncode, 0, back.stdout + back.stderr)
        self.assertFalse((self.V / NOTE).exists())

    def test_via_obsidian_revert_only_takes_back_the_last_one(self):
        self.jot("舊的", via=True)
        r = self.jot("新的", "--json", via=True)
        back = run_kb("versions", "revert", self.turn_of(r), cwd=self.V, via=True)
        self.assertEqual(back.returncode, 0, back.stdout + back.stderr)
        got = [LINE.match(l).group(1) for l in self.lines() if l.startswith("- ")]
        self.assertEqual(got, ["舊的"])

    def test_an_older_turn_code_is_refused_and_page_unchanged(self):
        first = self.jot("先記的", "--json", via=True)
        self.jot("後記的", via=True)
        back = run_kb("versions", "revert", self.turn_of(first), cwd=self.V, via=True)
        self.assertNotEqual(back.returncode, 0)
        got = [LINE.match(l).group(1) for l in self.lines() if l.startswith("- ")]
        self.assertEqual(got, ["先記的", "後記的"])

    def test_each_via_obsidian_call_is_its_own_turn_with_a_backup(self):
        a = self.turn_of(self.jot("甲", "--json", via=True))
        b = self.turn_of(self.jot("乙", "--json", via=True))
        self.assertNotEqual(a, b)
        manifest = (self.V / ".system" / "versions" / b / "manifest.jsonl").read_text(encoding="utf-8")
        self.assertIn(NOTE, manifest)
        self.assertIn('"modify"', manifest)
        self.assertTrue((self.V / ".system" / "versions" / b / "files" / FREE_DIR / "隨手記.md").is_file(), "寫前的舊版在回合裡")


class Journal(Base):
    def rows(self):
        return [r for m in journal.months(self.V) for r in journal.read_lines(self.V, m) if r.get("kind") == "program"]

    def test_terminal_run_records_a_program_row_without_the_text(self):
        self.jot("不要被日誌抄走的字")
        rows = self.rows()
        self.assertTrue(rows)
        self.assertNotIn("不要被日誌抄走的字", json.dumps(rows, ensure_ascii=False))
        self.assertIn("隨手記", json.dumps(rows, ensure_ascii=False))

    def test_via_obsidian_row_is_marked_obsidian(self):
        self.jot("x", via=True)
        self.assertTrue(any(r.get("source") == "obsidian" for r in self.rows()), self.rows())


if __name__ == "__main__":
    unittest.main()
