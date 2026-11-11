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


def init_here(path, *extra):
    """同一個行程裡跑 kb init（要換替身時用）。"""
    import contextlib
    import io
    from kb import cli
    from kb._lib import io as kio
    saved, out = kio.LOCK_TIMEOUT, io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            code = cli.main(["init", str(path), *extra])
    finally:
        kio.LOCK_TIMEOUT = saved
    return code, out.getvalue()


class OuterVault(unittest.TestCase):
    """#66 丙 驗收 1：上層 vault＝從知識庫根往上最多兩層、最近一個有 .obsidian/ 資料夾的夾。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kbouter-"))
        self.up = self.tmp / "我的筆記"
        (self.up / ".obsidian").mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def got(self, rel):
        v = self.up.joinpath(*rel.split("/"))
        v.mkdir(parents=True, exist_ok=True)
        r = obsidian.outer_vault(v)
        return None if r is None else (Path(r[0]), r[1])

    def test_1_one_and_two_levels_up(self):
        real = Path(os.path.realpath(self.up))
        self.assertEqual(self.got("willy"), (real, "willy"))
        self.assertEqual(self.got("a/b"), (real, "a/b"))
        self.assertIsNone(self.got("a/b/c"))

    def test_1_obsidian_must_be_a_folder(self):
        shutil.rmtree(self.up / ".obsidian")
        (self.up / ".obsidian").write_text("x", encoding="utf-8")
        self.assertIsNone(self.got("willy"))

    def test_1_nearest_wins_and_own_folder_does_not_count(self):
        (self.up / "a" / ".obsidian").mkdir(parents=True)
        self.assertEqual(self.got("a/b"), (Path(os.path.realpath(self.up / "a")), "b"))
        (self.up / "a" / "b" / ".obsidian").mkdir()  # 知識庫自己的 .obsidian 不算
        self.assertEqual(self.got("a/b"), (Path(os.path.realpath(self.up / "a")), "b"))

    def test_1_none_when_no_outer(self):
        shutil.rmtree(self.up / ".obsidian")
        self.assertIsNone(self.got("willy"))
        self.assertEqual((obsidian.plan_outer(self.up / "willy"), obsidian.place_outer(self.up / "willy")), ([], ([], [])))


class PlaceOuter(unittest.TestCase):
    """#66 丙 驗收 2～5：有上層 vault 時 kb init 也放上層那份外掛。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kbouter-"))
        self.up = self.tmp / "我的筆記"
        (self.up / ".obsidian").mkdir(parents=True)
        self.V = self.up / "willy"
        self.outer_files = [self.up / PLUGIN / n for n in obsidian.FILES] + [self.up / COMMUNITY]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def src(self, name):
        return (ROOT / "obsidian" / name).read_bytes()

    def test_2_both_copies_placed_and_second_run_quiet(self):
        (self.up / COMMUNITY).write_text('["obsidian-git"]', encoding="utf-8")
        r = init(self.V)
        self.assertEqual(r.returncode, 0, r.stderr)
        for base in (self.V, self.up):
            for name in obsidian.FILES:
                self.assertEqual((base / PLUGIN / name).read_bytes(), self.src(name), f"{base.name}/{name}")
        self.assertEqual(json.loads((self.up / COMMUNITY).read_text(encoding="utf-8")), ["obsidian-git", "wiki-with-willy"])
        self.assertIn("上層的 Obsidian 資料夾（我的筆記）的首頁外掛也換成這一版", r.stdout.splitlines())
        self.assertIn("建了", r.stdout.splitlines()[0])
        before = [f.stat().st_mtime_ns for f in self.outer_files]
        r = init(self.V)
        self.assertEqual([f.stat().st_mtime_ns for f in self.outer_files], before)
        self.assertNotIn("上層的 Obsidian 資料夾", r.stdout)

    def test_2_outer_files_not_counted_or_listed_as_vault_files(self):
        out = json.loads(init(self.V, "--json").stdout)
        self.assertEqual(sorted(out["obsidian"]), sorted([f"{PLUGIN}/{n}" for n in obsidian.FILES] + [COMMUNITY]), "庫內的照舊")
        self.assertFalse([x for x in out["created"] if "我的筆記" in x or x.startswith("..")])
        self.assertTrue((self.up / PLUGIN / "main.js").is_file())
        self.assertFalse([f for f in (self.V / ".system").rglob("*") if f.is_file() and f.name == "main.js"], "上層的檔不進回合備份")

    def test_3_check_reports_and_writes_nothing(self):
        init(self.V)
        (self.up / PLUGIN / "main.js").write_text("舊", encoding="utf-8")
        before = {f: f.read_bytes() for f in self.outer_files}
        r = init(self.V, "--check")
        self.assertIn("會換 上層 我的筆記 的首頁外掛", r.stdout.splitlines())
        self.assertEqual(json.loads(init(self.V, "--check", "--json").stdout)["obsidian_outer"], ["main.js"])
        self.assertEqual({f: f.read_bytes() for f in self.outer_files}, before)
        shutil.rmtree(self.up / PLUGIN)
        (self.up / COMMUNITY).unlink()
        r = init(self.V, "--check")
        self.assertIn("會建 上層 我的筆記 的首頁外掛", r.stdout.splitlines())
        self.assertEqual(json.loads(init(self.V, "--check", "--json").stdout)["obsidian_outer"],
                         ["manifest.json", "main.js", "styles.css", "community-plugins.json"])
        self.assertFalse((self.up / PLUGIN).exists())
        init(self.V)
        self.assertEqual(json.loads(init(self.V, "--check", "--json").stdout)["obsidian_outer"], [])
        self.assertNotIn("上層", init(self.V, "--check").stdout)

    def test_4_broken_outer_community_file_left_alone(self):
        (self.up / COMMUNITY).write_text("{壞掉", encoding="utf-8")
        r = init(self.V)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.up / COMMUNITY).read_text(encoding="utf-8"), "{壞掉")
        for name in obsidian.FILES:
            self.assertEqual((self.up / PLUGIN / name).read_bytes(), self.src(name), name)
        self.assertIn("上層的 Obsidian 資料夾（我的筆記）的 community-plugins.json 讀不懂，沒動；Obsidian 的外掛要自己在設定裡打開",
                      r.stdout.splitlines())
        self.assertIn("community-plugins.json", (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8"))
        self.assertEqual(json.loads((self.V / COMMUNITY).read_text(encoding="utf-8")), ["wiki-with-willy"], "知識庫自己那份照補")

    def test_5_outer_not_writable_is_a_note(self):
        real_put = obsidian._put
        outer_dir = os.path.realpath(self.up / ".obsidian")

        def put(target, data):
            if os.path.realpath(target).startswith(outer_dir):
                raise PermissionError("唯讀")
            real_put(target, data)
        with mock.patch.object(obsidian, "_put", put):
            code, out = init_here(self.V)
        self.assertEqual(code, 0, out)
        self.assertTrue(any(line.startswith("上層的 Obsidian 資料夾（我的筆記）外掛沒放成：") and "唯讀" in line for line in out.splitlines()), out)
        self.assertNotIn("也換成這一版", out)
        for name in obsidian.FILES:
            self.assertEqual((self.V / PLUGIN / name).read_bytes(), self.src(name), name)
        self.assertFalse((self.up / PLUGIN / "main.js").exists())


if __name__ == "__main__":
    unittest.main()
