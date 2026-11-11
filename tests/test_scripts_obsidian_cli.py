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


class Source(unittest.TestCase):
    def test_14_no_invalid_escape_sequences(self):
        """裁定 14：docstring 裡無效的跳脫序列（Windows 路徑的反斜線加 o）在 Python 3.14 是 SyntaxWarning、-W error 下是 SyntaxError。"""
        import warnings
        for rel in ("scripts/kb/obsidian_cli.py", "scripts/kb/_lib/obsidian.py", "scripts/kb/home_cli.py", "scripts/kb/find_cli.py",
                    "scripts/kb/renders_cli.py", "scripts/kb/_lib/home.py", "scripts/kb/_lib/find.py", "scripts/kb/_lib/hand.py"):
            path = Path(__file__).resolve().parent.parent / rel
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                compile(path.read_bytes(), str(path), "exec")


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
        self.assertEqual((code, json.loads(out)), (0, {"installed": True, "registered": False, "plugin": False, "outer": None}))
        self.register()
        obsidian.place(self.V)
        self.assertEqual(json.loads(kb(self.V, "obsidian", "status", "--json")[1]), {"installed": True, "registered": True, "plugin": True, "outer": None})
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

    def test_14_refusal_does_not_place_the_plugin(self):
        """裁定 14：先檢查再放外掛檔；拒絕的時候知識庫裡不留東西。"""
        self.state["running"] = True
        self.assertEqual(kb(self.V, "obsidian", "open")[0], 3)
        self.assertFalse((self.V / obsidian.PLUGIN_REL / "main.js").exists())
        self.assertFalse((self.V / obsidian.COMMUNITY_REL).exists())
        self.cfg.write_text("{壞", encoding="utf-8")
        self.state["running"] = False
        self.assertEqual(kb(self.V, "obsidian", "open")[0], 3)
        self.assertFalse((self.V / obsidian.PLUGIN_REL / "main.js").exists())
        self.assertFalse((self.V / obsidian.COMMUNITY_REL).exists())

    def test_14_place_oserror_is_a_note_not_a_traceback(self):
        self.register()
        with mock.patch.object(obsidian, "place", side_effect=OSError("唯讀")):
            code, out = kb(self.V, "obsidian", "open")
        self.assertEqual(code, 0, out)
        self.assertIn("Obsidian 外掛沒放成：唯讀", out)
        self.assertEqual(len(self.started), 1)
        with mock.patch.object(obsidian, "place", side_effect=OSError("唯讀")):
            code, out = kb(self.V, "obsidian", "open", "--json")
        self.assertEqual(code, 0, out)
        self.assertIn("Obsidian 外掛沒放成：唯讀", json.loads(out)["notes"])

    def test_open_url_encodes_everything(self):
        url = obsidian.open_url("D:/資料/王 小明/知識庫".replace("/", chr(92)))
        self.assertTrue(url.startswith("obsidian://open?path=D%3A%2F"), url)
        self.assertNotIn(" ", url)
        self.assertNotIn("\\", url)


class Outer(Base):
    """#66 丙 驗收 7、8：知識庫在她原本的 Obsidian 資料夾（上層 vault）裡。這裡上層是 self.tmp、前綴是 vault。"""

    def setUp(self):
        super().setUp()
        (self.tmp / ".obsidian").mkdir()
        self.name = self.tmp.name

    def test_7_status_when_outer_registered(self):
        self.register(self.tmp)
        code, out = kb(self.V, "obsidian", "status", "--json")
        self.assertEqual((code, json.loads(out)), (0, {"installed": True, "registered": True, "plugin": False,
                                                       "outer": {"name": self.name, "prefix": "vault", "plugin": False}}))
        obsidian.place_outer(self.V)
        self.assertEqual(json.loads(kb(self.V, "obsidian", "status", "--json")[1])["outer"],
                         {"name": self.name, "prefix": "vault", "plugin": True})
        lines = kb(self.V, "obsidian", "status")[1].splitlines()
        self.assertEqual(lines[1], "這個知識庫：Obsidian 已經登記")
        self.assertEqual(lines[-1], f"這個知識庫在你原本的 Obsidian 資料夾（{self.name}）裡面，會從那裡打開")

    def test_7_open_opens_the_outer_vault_without_registering(self):
        from kb import obsidian_cli
        self.register(self.tmp)
        before = self.cfg.read_text(encoding="utf-8")
        self.state["running"] = True  # 不用寫 obsidian.json，Obsidian 在跑也不擋
        code, out = kb(self.V, "obsidian", "open")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.started, [obsidian.open_url(os.path.realpath(self.tmp))])
        self.assertEqual(self.cfg.read_text(encoding="utf-8"), before, "沒有多出知識庫那一筆")
        self.assertEqual(out.splitlines()[0],
                         f"已打開 Obsidian（你原本的資料夾 {self.name}），按左邊的首頁按鈕就看得到。" + obsidian_cli.TRUST_NOTE)
        for base in (self.V, self.tmp):
            self.assertTrue((base / obsidian.PLUGIN_REL / "main.js").is_file(), base.name)
        self.started.clear()
        got = json.loads(kb(self.V, "obsidian", "open", "--json")[1])
        self.assertEqual((got["opened"], got["registered_now"], got["outer"], got["wrote"]), (True, False, self.name, []))

    def test_7_outer_registered_counts_as_registered(self):
        self.assertFalse(obsidian.vault_registered(self.V))
        self.register(self.tmp)
        self.assertTrue(obsidian.vault_registered(self.V), "上層已登記也算（moved 的 obsidian_reopen 用這個）")

    def test_8_outer_not_registered_is_as_before(self):
        from kb import obsidian_cli
        code, out = kb(self.V, "obsidian", "status", "--json")
        self.assertEqual(json.loads(out), {"installed": True, "registered": False, "plugin": False, "outer": None})
        self.assertEqual(len(kb(self.V, "obsidian", "status")[1].splitlines()), 3)
        self.state["running"] = True
        code, out = kb(self.V, "obsidian", "open")
        self.assertEqual((code, out.strip()), (3, obsidian_cli.CLOSE_FIRST))
        self.state["running"] = False
        code, out = kb(self.V, "obsidian", "open", "--json")
        got = json.loads(out)
        self.assertEqual((code, got["registered_now"], got["outer"]), (0, True, None))
        self.assertEqual(self.started, [obsidian.open_url(self.V)])
        (entry,) = json.loads(self.cfg.read_text(encoding="utf-8"))["vaults"].values()
        self.assertEqual(Path(entry["path"]).resolve(), Path(self.V).resolve())

    def test_8_own_registration_wins(self):
        self.register(self.V)
        self.assertIsNone(json.loads(kb(self.V, "obsidian", "status", "--json")[1])["outer"])
        kb(self.V, "obsidian", "open")
        self.assertEqual(self.started, [obsidian.open_url(self.V)])


if __name__ == "__main__":
    unittest.main()
