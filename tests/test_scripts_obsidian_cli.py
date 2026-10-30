"""kb obsidian status／open（Obsidian 首頁，#22，D-259）。外部（登錄、%LOCALAPPDATA%、行程、os.startfile）都換替身。驗收準則 14。"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests._guard_fixture import make_vault
from kb import cli  # noqa: E402
from kb._lib import io as kio  # noqa: E402
from kb._lib import obsidian  # noqa: E402


def kb(vault, *args):
    saved_cwd, saved_to = os.getcwd(), kio.LOCK_TIMEOUT
    out = io.StringIO()
    try:
        os.chdir(vault)
        with contextlib.redirect_stdout(out):
            code = cli.main(list(args))
    finally:
        os.chdir(saved_cwd)
        kio.LOCK_TIMEOUT = saved_to
    return code, out.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        self.cfg = Path(tempfile.mkdtemp(prefix="obs-cfg-")) / "obsidian.json"
        self.state = {"installed": True, "running": False}
        self.started = []
        self.patches = [
            mock.patch.dict(os.environ, {obsidian.CONFIG_ENV: str(self.cfg)}),
            mock.patch.object(obsidian, "installed", lambda: self.state["installed"]),
            mock.patch.object(obsidian, "_running", lambda: self.state["running"]),
            mock.patch.object(obsidian, "_startfile", lambda url: self.started.append(url)),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.cfg.parent, ignore_errors=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def register(self, vault=None):
        self.cfg.write_text(json.dumps({"vaults": {"abcdef0123456789": {"path": str(vault or self.V), "ts": 1}}}), encoding="utf-8")


class Status(Base):
    def test_three_items_each_right(self):
        code, out = kb(self.V, "obsidian", "status", "--json")
        self.assertEqual((code, json.loads(out)), (0, {"installed": True, "registered": False, "plugin": False}))
        self.register()
        obsidian.place(self.V)
        self.assertEqual(json.loads(kb(self.V, "obsidian", "status", "--json")[1]), {"installed": True, "registered": True, "plugin": True})
        self.state["installed"] = False
        self.assertFalse(json.loads(kb(self.V, "obsidian", "status", "--json")[1])["installed"])

    def test_human_lines(self):
        code, out = kb(self.V, "obsidian", "status")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["Obsidian：這台電腦有裝", "這個知識庫：Obsidian 還沒登記", "首頁外掛：還沒放好（kb init 或 kb obsidian open 會放）"])

    def test_plugin_half_placed_is_not_placed(self):
        obsidian.place(self.V)
        (self.V / obsidian.PLUGIN_REL / "main.js").write_text("舊", encoding="utf-8")
        self.assertFalse(json.loads(kb(self.V, "obsidian", "status", "--json")[1])["plugin"])

    def test_registered_compares_real_paths(self):
        self.register(str(self.V).upper() if os.name == "nt" else self.V)
        self.assertTrue(json.loads(kb(self.V, "obsidian", "status", "--json")[1])["registered"])

    def test_broken_config_counts_as_not_registered(self):
        self.cfg.write_text("{壞", encoding="utf-8")
        self.assertFalse(json.loads(kb(self.V, "obsidian", "status", "--json")[1])["registered"])


class Open(Base):
    def test_registered_opens_directly(self):
        self.register()
        code, out = kb(self.V, "obsidian", "open")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(self.started), 1)
        self.assertTrue(self.started[0].startswith("obsidian://open?path="))
        self.assertIn("%2F", self.started[0])
        self.assertIn("信任", out)
        self.assertNotIn("加進", out.splitlines()[0])

    def test_not_registered_obsidian_closed_writes_config_then_opens(self):
        self.cfg.write_text(json.dumps({"vaults": {"1111111111111111": {"path": "C:/別的庫", "ts": 5}}, "frame": "hidden"}), encoding="utf-8")
        code, out = kb(self.V, "obsidian", "open", "--json")
        self.assertEqual(code, 0, out)
        got = json.loads(out)
        self.assertTrue(got["registered_now"])
        data = json.loads(self.cfg.read_text(encoding="utf-8"))
        self.assertEqual(data["frame"], "hidden", "別的設定不動")
        self.assertIn("1111111111111111", data["vaults"])
        (new_id,) = [k for k in data["vaults"] if k != "1111111111111111"]
        self.assertRegex(new_id, r"^[0-9a-f]{16}$")
        self.assertTrue(data["vaults"][new_id]["ts"] > 0)
        self.assertEqual(Path(data["vaults"][new_id]["path"]).resolve(), Path(self.V).resolve())
        self.assertEqual(len(self.started), 1)

    def test_not_registered_but_obsidian_running_refuses(self):
        self.state["running"] = True
        code, out = kb(self.V, "obsidian", "open")
        self.assertEqual((code, out.strip()), (3, "先關掉 Obsidian 再說一次（它開著的時候我沒辦法把這個知識庫加進去）"))
        self.assertEqual(self.started, [])
        self.assertFalse(self.cfg.exists())

    def test_running_and_registered_just_opens(self):
        self.state["running"] = True
        self.register()
        self.assertEqual(kb(self.V, "obsidian", "open")[0], 0)
        self.assertEqual(len(self.started), 1)

    def test_not_installed(self):
        self.state["installed"] = False
        code, out = kb(self.V, "obsidian", "open")
        self.assertEqual(code, 3)
        self.assertIn("obsidian.md", out)
        self.assertEqual(self.started, [])

    def test_places_plugin_first(self):
        self.register()
        self.assertFalse((self.V / obsidian.PLUGIN_REL / "main.js").exists())
        kb(self.V, "obsidian", "open")
        self.assertTrue((self.V / obsidian.PLUGIN_REL / "main.js").is_file())
        self.assertEqual(json.loads((self.V / obsidian.COMMUNITY_REL).read_text(encoding="utf-8")), ["wiki-with-willy"])

    def test_broken_config_refuses_without_overwriting(self):
        self.cfg.write_text("{壞", encoding="utf-8")
        code, out = kb(self.V, "obsidian", "open")
        self.assertEqual(code, 3)
        self.assertEqual(self.cfg.read_text(encoding="utf-8"), "{壞")
        self.assertEqual(self.started, [])

    def test_open_url_encodes_everything(self):
        url = obsidian.open_url("D:/資料/王 小明/知識庫".replace("/", chr(92)))
        self.assertTrue(url.startswith("obsidian://open?path=D%3A%2F"), url)
        self.assertNotIn(" ", url)
        self.assertNotIn("\\", url)


if __name__ == "__main__":
    unittest.main()
