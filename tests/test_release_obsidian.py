"""tools/release.py 的 obsidian/（Obsidian 首頁，#22，D-258；驗收準則 17）：zip 清單含 obsidian/，最後檢查三個檔都在、manifest 版號等於 tag。"""
import json
import unittest

from tests.test_tools_release import Base, make_tree, write
from tools import release  # noqa: E402


class ObsidianInZip(Base):
    def test_files_go_into_the_zip(self):
        files = release.collect(self.repo, "v0.20.0")
        for name in ("manifest.json", "main.js", "styles.css"):
            self.assertIn(f"obsidian/{name}", files)

    def test_allowed(self):
        self.assertTrue(release.allowed("obsidian/main.js"))
        self.assertFalse(release.allowed("obsidianx/main.js"))

    def test_good_tree_has_no_problems(self):
        self.assertEqual(release.problems(release.collect(self.repo, "v0.20.0"), "0.20.0"), [])

    def test_missing_file_is_reported(self):
        files = release.collect(self.repo, "v0.20.0")
        del files["obsidian/styles.css"]
        self.assertIn("obsidian/styles.css 不在 zip 裡", release.problems(files, "0.20.0"))

    def test_whole_folder_missing_lists_all_three(self):
        files = {k: v for k, v in release.collect(self.repo, "v0.20.0").items() if not k.startswith("obsidian/")}
        got = release.problems(files, "0.20.0")
        for name in ("manifest.json", "main.js", "styles.css"):
            self.assertIn(f"obsidian/{name} 不在 zip 裡", got)

    def test_manifest_version_must_equal_tag(self):
        files = release.collect(self.repo, "v0.20.0")
        files["obsidian/manifest.json"] = json.dumps({"id": "wiki-with-willy", "version": "0.19.0"}).encode("utf-8")
        self.assertIn("obsidian/manifest.json 的版本是 0.19.0，tag 是 0.20.0", release.problems(files, "0.20.0"))

    def test_manifest_must_be_json(self):
        files = release.collect(self.repo, "v0.20.0")
        files["obsidian/manifest.json"] = b"{"
        self.assertIn("obsidian/manifest.json 不是合法的 JSON", release.problems(files, "0.20.0"))

    def test_build_refuses_when_manifest_version_differs(self):
        write(self.repo, "obsidian/manifest.json", json.dumps({"id": "wiki-with-willy", "version": "0.19.0"}))
        from tests.test_tools_release import git
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "x")
        git(self.repo, "tag", "-f", "v0.20.0")
        with self.assertRaises(release.ReleaseError) as cm:
            release.build(self.repo, "v0.20.0")
        self.assertIn("obsidian/manifest.json 的版本是 0.19.0", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
