"""kb config show／set／reset 黑箱（放寬甲 D-322 第 2 件、驗收 24）：set 寫 .system/config.json 且 config.get 讀得到、
保護用的鍵不給改、reset 回預設、型別照預設檢查、寫前備進回合（退回改得回來）、--json 的形狀。"""
import json
import shutil
import unittest

from tests.test_lib_inventory_scan import make_inv_vault
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import config, turn  # noqa: E402


class Config(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_inv_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kb(self, *args, code=0):
        r = run_kb("config", *args, cwd=self.V)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return r.stdout

    def test_set_then_get_then_reset(self):
        self.kb("set", "ingest_auto_max", "50")
        stored = json.loads((self.V / ".system" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["ingest_auto_max"], 50)
        self.assertEqual(config.get(self.V, "ingest_auto_max"), 50)
        self.kb("reset", "ingest_auto_max")
        self.assertEqual(config.get(self.V, "ingest_auto_max"), config.defaults()["ingest_auto_max"])
        self.assertNotIn("ingest_auto_max", json.loads((self.V / ".system" / "config.json").read_text(encoding="utf-8")))

    def test_protected_key_refused(self):
        out = self.kb("set", "credential_scan_max_entries", "1", code=3)
        self.assertEqual(out.strip(), "「credential_scan_max_entries」是保護用的，不給改")
        self.assertFalse((self.V / ".system" / "config.json").exists() and
                         "credential_scan_max_entries" in (self.V / ".system" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(self.kb("reset", "fingerprint_max_bytes", code=3).strip(), "「fingerprint_max_bytes」是保護用的，不給改")

    def test_type_checked_against_default(self):
        self.assertIn("要填整數", self.kb("set", "ingest_auto_max", "十", code=3))
        self.assertIn("要填整數", self.kb("set", "ingest_auto_max", "true", code=3))

    def test_show_json_shape(self):
        self.kb("set", "agenda_window_days", "21")
        got = json.loads(self.kb("show", "--json"))
        rows = {r["key"]: r for r in got["keys"]}
        self.assertEqual(set(rows), set(config.USER_KEYS))
        self.assertEqual((rows["agenda_window_days"]["value"], rows["agenda_window_days"]["default"]), (21, config.defaults()["agenda_window_days"]))
        self.assertTrue(rows["ingest_auto_max"]["why"])
        self.assertNotIn("credential_scan_max_entries", rows)

    def test_set_backed_up_into_turn_and_revert_restores(self):
        t = turn.start(self.V, None, "")["turn"]
        self.kb("set", "ingest_auto_max", "50")
        self.assertIn(".system/config.json", [e["path"] for e in turn.entries(self.V, t)])
        r = run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(config.get(self.V, "ingest_auto_max"), config.defaults()["ingest_auto_max"])

    def test_user_keys_are_in_defaults_with_why(self):
        base = config.defaults()
        for key in config.USER_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, base)
                self.assertTrue(base.get(f"_why_{key}"))


if __name__ == "__main__":
    unittest.main()
