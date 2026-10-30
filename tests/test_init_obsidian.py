"""kb init 放 Obsidian 外掛（Obsidian 首頁，#22，D-258、D-260）。驗收準則 11：放三個檔與 community-plugins.json 那項；.obsidian 裡她的檔不動；
舊版外掛被換掉；community-plugins.json 有別的外掛時留著；不算骨架項目。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests._guard_fixture import KB, ROOT
from kb._lib import obsidian  # noqa: E402

PLUGIN = ".obsidian/plugins/wiki-with-willy"
COMMUNITY = ".obsidian/community-plugins.json"


def init(path, *extra):
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))
    return subprocess.run([sys.executable, str(KB), "init", str(path), *extra], capture_output=True, text=True, encoding="utf-8", env=env)


class Place(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kbinit-obs-"))
        self.V = self.tmp / "知識庫"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def src(self, name):
        return (ROOT / "obsidian" / name).read_bytes()

    def test_fresh_init_places_three_files_and_community_entry(self):
        r = init(self.V)
        self.assertEqual(r.returncode, 0, r.stderr)
        for name in obsidian.FILES:
            self.assertEqual((self.V / PLUGIN / name).read_bytes(), self.src(name), name)
        self.assertEqual(json.loads((self.V / COMMUNITY).read_text(encoding="utf-8")), ["wiki-with-willy"])
        self.assertIn("Obsidian 首頁外掛放好了", r.stdout)

    def test_not_counted_as_skeleton_items(self):
        r = init(self.V, "--json")
        out = json.loads(r.stdout)
        self.assertFalse([x for x in out["created"] if x.startswith(".obsidian")])
        self.assertEqual(sorted(out["obsidian"]), sorted([f"{PLUGIN}/{n}" for n in obsidian.FILES] + [COMMUNITY]))

    def test_her_files_in_obsidian_folder_untouched(self):
        init(self.V)
        app = self.V / ".obsidian" / "app.json"
        app.write_text('{"showUnsupportedFiles": false}', encoding="utf-8")
        other = self.V / ".obsidian" / "appearance.json"
        other.write_text('{"theme": "moonstone"}', encoding="utf-8")
        init(self.V)
        self.assertEqual(app.read_text(encoding="utf-8"), '{"showUnsupportedFiles": false}')
        self.assertEqual(other.read_text(encoding="utf-8"), '{"theme": "moonstone"}')

    def test_old_plugin_is_replaced_and_new_equal_not_rewritten(self):
        init(self.V)
        main = self.V / PLUGIN / "main.js"
        main.write_text("// 舊版\n", encoding="utf-8")
        data = self.V / PLUGIN / "data.json"
        data.write_text('{"opened": []}', encoding="utf-8")
        r = init(self.V)
        self.assertEqual(main.read_bytes(), self.src("main.js"))
        self.assertEqual(data.read_text(encoding="utf-8"), '{"opened": []}', "外掛自己的資料不動")
        self.assertIn("Obsidian 首頁外掛放好了（1 項）", r.stdout)
        before = (self.V / PLUGIN / "styles.css").stat().st_mtime_ns
        r = init(self.V)
        self.assertEqual((self.V / PLUGIN / "styles.css").stat().st_mtime_ns, before)
        self.assertNotIn("Obsidian 首頁外掛", r.stdout)

    def test_other_community_plugins_kept(self):
        (self.V / ".obsidian").mkdir(parents=True)
        (self.V / COMMUNITY).write_text('["dataview", "calendar"]', encoding="utf-8")
        init(self.V)
        self.assertEqual(json.loads((self.V / COMMUNITY).read_text(encoding="utf-8")), ["dataview", "calendar", "wiki-with-willy"])

    def test_already_listed_not_rewritten(self):
        (self.V / ".obsidian").mkdir(parents=True)
        text = '[\n  "wiki-with-willy",\n  "dataview"\n]\n'
        (self.V / COMMUNITY).write_text(text, encoding="utf-8")
        init(self.V)
        self.assertEqual((self.V / COMMUNITY).read_text(encoding="utf-8"), text)

    def test_broken_community_file_left_alone_with_note_and_log(self):
        (self.V / ".obsidian").mkdir(parents=True)
        (self.V / COMMUNITY).write_text("{壞掉", encoding="utf-8")
        r = init(self.V)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.V / COMMUNITY).read_text(encoding="utf-8"), "{壞掉")
        self.assertIn("community-plugins.json 讀不懂", r.stdout)
        self.assertIn("community-plugins.json", (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8"))
        self.assertTrue((self.V / PLUGIN / "main.js").is_file(), "外掛三個檔照放")

    def test_check_lists_and_writes_nothing(self):
        r = init(self.V, "--check")
        self.assertIn(f"會建 {PLUGIN}/main.js", r.stdout.splitlines())
        self.assertIn(f"會建 {COMMUNITY}", r.stdout.splitlines())
        self.assertFalse(self.V.exists())
        init(self.V)
        (self.V / PLUGIN / "main.js").write_text("舊", encoding="utf-8")
        r = init(self.V, "--check", "--json")
        self.assertEqual(json.loads(r.stdout)["obsidian"], [f"{PLUGIN}/main.js"])
        self.assertEqual((self.V / PLUGIN / "main.js").read_text(encoding="utf-8"), "舊")
        r = init(self.V, "--check")
        self.assertIn(f"會換 {PLUGIN}/main.js", r.stdout.splitlines())

    def test_plugin_without_obsidian_folder_skips_quietly(self):
        with mock.patch.object(obsidian, "source_dir", return_value=self.tmp / "不存在"):
            self.V.mkdir()
            wrote, notes = obsidian.place(self.V)
            self.assertEqual((wrote, notes, obsidian.plan(self.V)), ([], [], []))
        self.assertFalse((self.V / ".obsidian").exists())

    def test_second_init_has_nothing_missing(self):
        init(self.V)
        r = init(self.V)
        self.assertIn("沒有缺的", r.stdout)


if __name__ == "__main__":
    unittest.main()
