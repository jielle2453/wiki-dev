"""plugin.json 的 version 必須等於 CHANGELOG 最新一段的版號（conventions 三）；最新一段要有「給客戶的一句話」（升級打包）。"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADING = re.compile(r"^## (\d+\.\d+\.\d+) — ", re.MULTILINE)
SECTION = re.compile(r"^## (\d+\.\d+\.\d+) — .*?(?=^## |\Z)", re.MULTILINE | re.DOTALL)
SENTENCE = re.compile(r"^- \*\*給客戶的一句話\*\*：\S.*$", re.MULTILINE)


class VersionSync(unittest.TestCase):
    def test_manifest_version_equals_latest_changelog_section(self):
        with open(ROOT / ".claude-plugin" / "plugin.json", encoding="utf-8") as f:
            manifest_version = json.load(f)["version"]
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        m = HEADING.search(text)
        self.assertIsNotNone(m, "CHANGELOG.md 找不到 `## X.Y.Z — ` 段落")
        self.assertEqual(manifest_version, m.group(1))


    def test_obsidian_manifest_version_equals_plugin_version(self):
        """Obsidian 首頁外掛（#22，D-258）跟 plugin 同一版：obsidian/manifest.json 的 version 等於 plugin.json 的。"""
        with open(ROOT / ".claude-plugin" / "plugin.json", encoding="utf-8") as f:
            plugin_version = json.load(f)["version"]
        with open(ROOT / "obsidian" / "manifest.json", encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(manifest["version"], plugin_version)
        self.assertEqual(manifest["id"], "wiki-with-willy")


class CustomerSentence(unittest.TestCase):
    """升級打包 要做的事 10：CHANGELOG 每一段多一行「給客戶的一句話」（從 0.20.0 起）；沒寫不准發行，發行程式也擋。"""

    def test_latest_section_has_the_customer_sentence(self):
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        latest = SECTION.search(text)
        self.assertIsNotNone(latest)
        self.assertRegex(latest.group(0), SENTENCE, f"{latest.group(1)} 那一段缺「給客戶的一句話」")

    def test_intro_explains_the_line(self):
        head = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").split("\n## ", 1)[0]
        self.assertIn("給客戶的一句話", head)

    def test_skeleton_history_is_well_formed_and_has_the_first_entry(self):
        """config/skeleton_history.json：版本 → 每個骨架檔的 sha256（發行程式每版追加）；至少有 0.20.0 那一筆。"""
        data = json.loads((ROOT / "config" / "skeleton_history.json").read_text(encoding="utf-8"))
        self.assertIn("0.20.0", data)
        skeleton = ROOT / "skeleton"
        names = {p.relative_to(skeleton).as_posix() for p in skeleton.rglob("*") if p.is_file() and p.name != ".gitkeep"}
        for version, files in data.items():
            with self.subTest(version=version):
                self.assertRegex(version, r"^\d+\.\d+\.\d+$")
                for sha in files.values():
                    self.assertRegex(sha, r"^[0-9a-f]{64}$")
        self.assertEqual(set(data["0.20.0"]), names)


if __name__ == "__main__":
    unittest.main()
