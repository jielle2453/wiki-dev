"""kb find 黑箱（Obsidian 智慧搜尋，#22）：subprocess 跑 kb.py。--json 格式、人讀一行一筆、找不到、不在知識庫裡。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests import _cards
from tests import _entities as E
from tests.test_scripts_inventory_cli import run_kb


class FindCli(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        item = E.new_item(self.V, E.QUOTE)
        text = E.with_entities(_cards.card_text(item, "報價單", body="含水電工程。〔第 1 段〕\n", kind="報價", date="2026-09-12"), ["信義王"])
        path = _cards.card_path(self.V, item, "報價單")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_json(self):
        r = run_kb("find", "信義王 報價", "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(set(out), {"q", "parsed", "entities", "files", "total", "more"})
        self.assertEqual(out["q"], "信義王 報價")
        self.assertEqual([f["title"] for f in out["files"]], ["報價單"])

    def test_human_line_per_file(self):
        r = run_kb("find", "信義王 報價", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lines = r.stdout.strip().splitlines()
        self.assertEqual(lines[0], "照這樣找：實體 信義王、卡型 報價")
        self.assertTrue(any(l.startswith("報價單（報價，2026-09-12）") for l in lines), r.stdout)

    def test_nothing_found(self):
        r = run_kb("find", "完全不存在的東西", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.splitlines()[-1]), (0, "沒有找到"))

    def test_dash_leading_query_needs_double_dash(self):
        r = run_kb("find", "--json", "--", "-abc", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["q"], "-abc")

    def test_not_in_vault(self):
        with tempfile.TemporaryDirectory() as d:
            r = run_kb("find", "x", "--json", cwd=Path(d))
        self.assertEqual(r.returncode, 3)

    def test_via_obsidian_read_only_opens_no_turn(self):
        vdir = self.V / ".system" / "versions"
        before = sorted(p.name for p in vdir.iterdir()) if vdir.is_dir() else []
        r = run_kb("--via", "obsidian", "find", "信義王", "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(before, sorted(p.name for p in vdir.iterdir()) if vdir.is_dir() else [])


if __name__ == "__main__":
    unittest.main()
