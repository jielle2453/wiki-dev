"""kb selftest 的 obsidian 這一步（Obsidian 首頁，#22；驗收準則 17）：三個檔在、manifest 是合法 JSON、版號等於 plugin.json，不跑 node。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import _guard_fixture  # noqa: F401  (放好 sys.path)
from kb._lib import paths, selftest  # noqa: E402


class ObsidianStep(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="kbst-obs-"))
        (self.root / "obsidian").mkdir()
        self.version = "0.20.0"
        self.manifest = {"id": "wiki-with-willy", "version": self.version}
        self.write("manifest.json", json.dumps(self.manifest))
        self.write("main.js", "module.exports = {};\n")
        self.write("styles.css", "")
        patcher = mock.patch.object(paths, "read_manifest", return_value={"name": "wiki-with-willy", "version": self.version})
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write(self, name, text):
        (self.root / "obsidian" / name).write_text(text, encoding="utf-8")

    def fails(self):
        with self.assertRaises(selftest.Failed) as cm:
            selftest._step_obsidian(self.root)
        return cm.exception

    def test_good(self):
        selftest._step_obsidian(self.root)

    def test_step_is_in_the_list_and_last(self):
        self.assertEqual(selftest.STEPS[-1], "obsidian")

    def test_missing_each_file(self):
        for name in selftest.OBSIDIAN_FILES:
            kept = (self.root / "obsidian" / name).read_bytes()
            (self.root / "obsidian" / name).unlink()
            e = self.fails()
            self.assertEqual((e.why, e.file), (f"obsidian/{name} 不在", f"obsidian/{name}"))
            (self.root / "obsidian" / name).write_bytes(kept)

    def test_manifest_not_json(self):
        self.write("manifest.json", "{")
        self.assertEqual(self.fails().why, "obsidian/manifest.json 不是合法的 JSON")

    def test_manifest_version_differs(self):
        self.write("manifest.json", json.dumps({"id": "wiki-with-willy", "version": "0.19.0"}))
        e = self.fails()
        self.assertEqual((e.why, e.file), ("obsidian/manifest.json 的版號跟 plugin.json 不一樣", "obsidian/manifest.json"))

    def test_real_plugin_passes(self):
        mock.patch.stopall()
        selftest._step_obsidian(selftest.ROOT_FROM_FILE)


if __name__ == "__main__":
    unittest.main()
