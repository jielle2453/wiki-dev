"""kb moved 的 Obsidian 那一行（Obsidian 首頁，#22，第 15 點）：搬了家、新位置 Obsidian 還沒登記而且她用過 Obsidian 才說。"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.test_scripts_moved_cli import Base, posix, run_kb
from kb._lib import obsidian  # noqa: E402

LINE = "Obsidian 要重新打開：kb obsidian open"


class MovedObsidian(Base):
    def test_line_when_obsidian_used_and_new_place_not_registered(self):
        NV = self.move_together()
        (NV / ".obsidian").mkdir()
        cfg = Path(tempfile.mkdtemp(prefix="obs-")) / "obsidian.json"
        cfg.write_text(json.dumps({"vaults": {"abcdef0123456789": {"path": posix(self.V), "ts": 1}}}), encoding="utf-8")
        envv = dict(os.environ, OBSIDIAN_CONFIG=str(cfg))
        with mock.patch.dict(os.environ, envv):
            r = run_kb("moved", "--check", cwd=NV)
            self.assertIn(LINE, r.stdout.splitlines())
            self.assertTrue(json.loads(run_kb("moved", "--check", "--json", cwd=NV).stdout)["obsidian_reopen"])
            r = run_kb("moved", cwd=NV)
            self.assertIn(LINE, r.stdout.splitlines())

    def test_no_line_when_never_used_obsidian(self):
        NV = self.move_together()
        self.assertNotIn(LINE, run_kb("moved", "--check", cwd=NV).stdout)
        self.assertFalse(json.loads(run_kb("moved", "--check", "--json", cwd=NV).stdout)["obsidian_reopen"])

    def test_no_line_when_new_place_already_registered(self):
        NV = self.move_together()
        (NV / ".obsidian").mkdir()
        cfg = Path(tempfile.mkdtemp(prefix="obs-")) / "obsidian.json"
        cfg.write_text(json.dumps({"vaults": {"abcdef0123456789": {"path": posix(NV), "ts": 1}}}), encoding="utf-8")
        with mock.patch.dict(os.environ, {obsidian.CONFIG_ENV: str(cfg)}):
            self.assertNotIn(LINE, run_kb("moved", "--check", cwd=NV).stdout)

    def test_no_line_when_nothing_moved(self):
        (self.V / ".obsidian").mkdir()
        self.assertNotIn(LINE, run_kb("moved", cwd=self.V).stdout)


if __name__ == "__main__":
    unittest.main()
