"""kb home 黑箱（Obsidian 首頁，#22）：subprocess 跑 kb.py，cwd 在 vault。沒帶 --json 拒絕、--opened、只讀不開回合。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests import _cards
from tests import _entities as E
from tests.test_scripts_inventory_cli import run_kb


class HomeCli(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_needs_json(self):
        r = run_kb("home", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "這個指令給外掛用，要帶 --json"))

    def test_json_output(self):
        r = run_kb("home", "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(out["schema"], "willy-home/1")
        self.assertIn("timeline", out)

    def test_global_json_flag_also_works(self):
        r = run_kb("--json", "home", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["schema"], "willy-home/1")

    def test_opened_ids(self):
        fid = _cards.entry_of(self.V, E.QUOTE)["id"]
        _cards.write_card(self.V, E.new_item(self.V, E.QUOTE), "報價單")
        r = run_kb("home", "--json", "--opened", f"{fid},f-不存在, ", cwd=self.V)
        out = json.loads(r.stdout)
        self.assertEqual(out["recent"][0]["card"], fid)
        self.assertEqual(out["recent"][0]["why"], "opened")

    def test_from_to_set_the_timeline_window(self):
        r = run_kb("home", "--json", "--from", "2026-01-01", "--to", "2026-03-31", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        tl = json.loads(r.stdout)["timeline"]
        self.assertEqual((tl["from"], tl["to"]), ("2026-01-01", "2026-03-31"))

    def test_from_to_are_optional(self):
        tl = json.loads(run_kb("home", "--json", cwd=self.V).stdout)["timeline"]
        one = json.loads(run_kb("home", "--json", "--to", "2099-01-01", cwd=self.V).stdout)["timeline"]
        self.assertEqual(one["from"], tl["from"])
        self.assertEqual(one["to"], "2099-01-01")

    def test_bad_dates_or_reversed_range_exit_3(self):
        for args in (("--from", "明天"), ("--to", "2026-13-40"), ("--from", "2026-05-01", "--to", "2026-04-01")):
            r = run_kb("home", "--json", *args, cwd=self.V)
            self.assertEqual(r.returncode, 3, args)
            self.assertIn("日期", r.stdout)

    def test_not_in_vault(self):
        with tempfile.TemporaryDirectory() as d:
            r = run_kb("home", "--json", cwd=Path(d))
        self.assertEqual(r.returncode, 3)

    def test_via_obsidian_opens_no_turn_for_read_only(self):
        before = sorted(p.name for p in (self.V / ".system" / "versions").iterdir()) if (self.V / ".system" / "versions").is_dir() else []
        r = run_kb("--via", "obsidian", "home", "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = sorted(p.name for p in (self.V / ".system" / "versions").iterdir()) if (self.V / ".system" / "versions").is_dir() else []
        self.assertEqual(before, after)

    def test_help_lists_home(self):
        r = run_kb("--help", cwd=self.V)
        self.assertIn("home", r.stdout)


if __name__ == "__main__":
    unittest.main()
