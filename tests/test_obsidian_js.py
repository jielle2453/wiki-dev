"""Obsidian 外掛的 JS 測試（D-265）：叫 node 內建的 test runner 跑 tests/obsidian/*.test.js。

沒有 node 就跳過並寫明（不算過）；有 node 就必須全過。node 24 的 `node --test <資料夾>` 會把資料夾當模組載入而失敗，
所以傳 glob 樣式讓 node 自己展開。
"""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_GLOB = "tests/obsidian/*.test.js"


class ObsidianJs(unittest.TestCase):
    def test_node_test_suite_passes(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("沒有 node，外掛的 JS 測試跳過")
        self.assertTrue(list((ROOT / "tests" / "obsidian").glob("*.test.js")), "tests/obsidian 底下沒有 *.test.js")
        done = subprocess.run(
            [node, "--test", TEST_GLOB],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        self.assertEqual(done.returncode, 0, f"node --test 沒過：\n{done.stdout}\n{done.stderr}")


if __name__ == "__main__":
    unittest.main()
