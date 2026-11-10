"""_lib/config：讀 config/defaults.json，客戶端 .system/config.json 同鍵覆寫，未知鍵 KeyError。"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from kb._lib import config  # noqa: E402


class Get(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kbcfg-"))
        self.vault = self.tmp / "vault"
        (self.vault / ".system").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_default_value_from_defaults_json(self):
        self.assertEqual(config.get(self.vault, "prompt_head_max"), 200)

    def test_defaults_json_has_why_for_each_key(self):
        data = json.loads((ROOT / "config" / "defaults.json").read_text(encoding="utf-8"))
        for key in data:
            if key.startswith("_why_"):
                continue
            with self.subTest(key=key):
                self.assertIn(f"_why_{key}", data)

    def test_journal_keys_have_defaults_and_why(self):
        """工作日誌：prompt_head_max 200（B-028）、journal_result_max 300（D-061），各有 _why。"""
        data = json.loads((ROOT / "config" / "defaults.json").read_text(encoding="utf-8"))
        self.assertEqual(config.get(self.vault, "prompt_head_max"), 200)
        self.assertEqual(config.get(self.vault, "journal_result_max"), 300)
        for key in ("prompt_head_max", "journal_result_max"):
            self.assertTrue(data.get(f"_why_{key}"), key)

    def test_inventory_keys_have_defaults_and_why(self):
        """清冊：單檔指紋上限 200 MB、快速比對讀取預算 200 MB、快速比對 5 秒（D-094、I-081）。"""
        data = json.loads((ROOT / "config" / "defaults.json").read_text(encoding="utf-8"))
        self.assertEqual(config.get(self.vault, "fingerprint_max_bytes"), 209715200)
        self.assertEqual(config.get(self.vault, "changes_quick_hash_budget_bytes"), 209715200)
        self.assertEqual(config.get(self.vault, "changes_quick_seconds"), 5)
        for key in ("fingerprint_max_bytes", "changes_quick_hash_budget_bytes", "changes_quick_seconds"):
            self.assertTrue(data.get(f"_why_{key}"), key)

    def test_relocate_sample_max(self):
        """manage 第二版第 9 點：folders relocate 抽樣 40 份，帶 _why。"""
        data = json.loads((ROOT / "config" / "defaults.json").read_text(encoding="utf-8"))
        self.assertEqual(config.get(self.vault, "relocate_sample_max"), 40)
        self.assertTrue(data.get("_why_relocate_sample_max"))

    def test_update_keys(self):
        """升級打包第 8 點：清單與名單網址（0.26.1 第一次發行時填，公開 repo 的 raw 網址）、抓 5 秒、換版 60 秒、一句話 40 字，各帶 _why。"""
        data = json.loads((ROOT / "config" / "defaults.json").read_text(encoding="utf-8"))
        want = {"update_manifest_url": "https://raw.githubusercontent.com/jielle2453/wiki-with-willy/main/marketplace.json",
                "update_rollout_url": "https://raw.githubusercontent.com/jielle2453/wiki-with-willy/main/rollout.json", "update_fetch_seconds": 5,
                "update_run_seconds": 60, "update_note_max": 40}
        for key, value in want.items():
            self.assertEqual(config.get(self.vault, key), value, key)
            self.assertTrue(data.get(f"_why_{key}"), key)

    def test_client_override_wins(self):
        (self.vault / ".system" / "config.json").write_text(
            json.dumps({"schema_version": 1, "prompt_head_max": 3}), encoding="utf-8")
        self.assertEqual(config.get(self.vault, "prompt_head_max"), 3)

    def test_unknown_key_raises_key_error(self):
        with self.assertRaises(KeyError):
            config.get(self.vault, "no_such_key")

    def test_wrong_type_in_client_file_uses_default_and_logs(self):
        """第一輪 L5：型別跟預設不同就用預設，寫一行 hook-errors.log。"""
        (self.vault / ".system" / "config.json").write_text(
            json.dumps({"prompt_head_max": "十"}), encoding="utf-8")
        self.assertEqual(config.get(self.vault, "prompt_head_max"), 200)
        log = (self.vault / ".system" / "hook-errors.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(log), 1)
        self.assertIn("prompt_head_max", log[0])

    def test_whole_file_not_an_object_uses_default_and_logs(self):
        """第二輪 L5 補（驗收 34）：config.json 整份是 5 → 用預設、寫一行 log。"""
        (self.vault / ".system" / "config.json").write_text("5", encoding="utf-8")
        self.assertEqual(config.get(self.vault, "prompt_head_max"), 200)
        log = (self.vault / ".system" / "hook-errors.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(log), 1)
        self.assertIn("config.json", log[0])

    def test_bool_is_not_accepted_as_int(self):
        (self.vault / ".system" / "config.json").write_text(
            json.dumps({"prompt_head_max": True}), encoding="utf-8")
        self.assertEqual(config.get(self.vault, "prompt_head_max"), 200)

    def test_int_accepted_for_float_key(self):
        """裁定 30：預設是小數的鍵寫整數照生效、回 float；true 與字串照舊退回預設、記 log。"""
        cfg = self.vault / ".system" / "config.json"
        cfg.write_text(json.dumps({"turn_scan_seconds": 2}), encoding="utf-8")
        got = config.get(self.vault, "turn_scan_seconds")
        self.assertEqual((got, type(got)), (2.0, float))
        log = self.vault / ".system" / "hook-errors.log"
        self.assertFalse(log.exists())
        for bad in (True, "2"):
            cfg.write_text(json.dumps({"turn_scan_seconds": bad}), encoding="utf-8")
            self.assertEqual(config.get(self.vault, "turn_scan_seconds"), 1.5)
        self.assertEqual(len(log.read_text(encoding="utf-8").splitlines()), 2)

    def test_client_file_cannot_add_unknown_key(self):
        (self.vault / ".system" / "config.json").write_text(json.dumps({"mystery": 1}), encoding="utf-8")
        with self.assertRaises(KeyError):
            config.get(self.vault, "mystery")


if __name__ == "__main__":
    unittest.main()
