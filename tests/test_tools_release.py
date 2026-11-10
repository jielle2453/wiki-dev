"""tools/release.py（升級打包 要做的事 9、驗收 15、16）：從 tag 打 zip（D-213）、小修規則（D-217）、publish／rollout（D-216、D-218）。
真的 git（tmp 裡的假開發 repo 與 bare 的假公開 repo），gh 與抓清單（_run 的 gh、_fetch）、等待（_sleep、_clock）用替身，不連網。"""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_under_test", ROOT / "tools" / "release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

GIT_ENV = {"GIT_AUTHOR_NAME": "發行", "GIT_AUTHOR_EMAIL": "r@example.invalid",
           "GIT_COMMITTER_NAME": "發行", "GIT_COMMITTER_EMAIL": "r@example.invalid", "GIT_CONFIG_GLOBAL": os.devnull,
           "GIT_CONFIG_SYSTEM": os.devnull}
MANIFEST_URL = "https://example.invalid/marketplace.json"
ROLLOUT_URL = "https://example.invalid/rollout.json"
PUBLIC_URL = "https://github.com/owner/wiki-with-willy"
ID1, ID2 = "kb-1a2b3c4d", "kb-5e6f7a8b"


def rmtree(path):
    """Windows 上 .git 底下的物件是唯讀的：先改權限再刪。"""
    import stat

    def onexc(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onexc=onexc, ignore_errors=False) if Path(path).exists() else None


def git(cwd, *args):
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, (args, r.stdout, r.stderr)
    return r.stdout


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


CHANGELOG = ("# CHANGELOG\n\n## {v} — 2026-10-30\n- **給客戶的一句話**：{note}\n- **改了什麼**：x\n\n"
             "## 0.20.0 — 2026-10-24\n- **給客戶的一句話**：舊的一句話。\n")


def skeleton_hashes(root):
    base = Path(root) / "skeleton"
    return {p.relative_to(base).as_posix(): sha(p.read_bytes()) for p in sorted(base.rglob("*"))
            if p.is_file() and p.name != ".gitkeep"}


def make_tree(root, version, note="日程可以匯出成 Excel。", schema=2, skeleton="身分\n", history=True, hooks_ref="hooks/session.py",
              fmt=1):
    """一個最小的假外掛樹，加上不該進 zip 的雜物。fmt 是流水檔格式版本（D-335）。"""
    write(root, ".claude-plugin/plugin.json", json.dumps({"name": "wiki-with-willy", "version": version}))
    write(root, "hooks/hooks.json", json.dumps({"hooks": {"SessionStart": [{"hooks": [
        {"type": "command", "command": f'python "${{CLAUDE_PLUGIN_ROOT}}/{hooks_ref}"'}]}]}}))
    write(root, "hooks/session.py", "print('x')\n")
    write(root, "scripts/kb/_lib/inventory.py", f"SCHEMA_VERSION = {schema}\n")
    write(root, "scripts/kb/_lib/migrate.py", "STATE_FILES = ()\n")
    write(root, "scripts/kb/_lib/streams.py", f"FORMAT_VERSION = {fmt}\n")
    write(root, "scripts/kb.py", "print('kb')\n")
    write(root, "agents/card-maker.md", "---\nname: card-maker\n---\n")
    write(root, "obsidian/manifest.json", json.dumps({"id": "wiki-with-willy", "version": version}))  # Obsidian 首頁外掛（#22）：三個檔都要在
    write(root, "obsidian/main.js", "module.exports = {};\n")
    write(root, "obsidian/styles.css", "/* 外掛 */\n")
    write(root, "skills/manage/SKILL.md", "---\nname: manage\n---\n")
    write(root, "rules/core.md", "核心\n")
    write(root, "templates/card.md", "卡\n")
    write(root, "skeleton/CLAUDE.md", skeleton)
    write(root, "skeleton/案子/.gitkeep", "")
    write(root, "config/defaults.json", json.dumps({"schema_version": 1, "update_manifest_url": MANIFEST_URL,
                                                    "update_rollout_url": ROLLOUT_URL}))
    write(root, "README.md", "說明\n")
    write(root, "LICENSE", "MIT\n")
    write(root, "CHANGELOG.md", CHANGELOG.format(v=version, note=note))
    write(root, "design/x.md", "設計文件\n")
    write(root, "tests/t.py", "pass\n")
    write(root, "tools/release.py", "pass\n")
    write(root, "CLAUDE.md", "給改 repo 的\n")
    write(root, ".claude/settings.json", "{}\n")
    write(root, ".gitattributes", "* text=auto eol=lf\n")
    hist = {"0.20.0": {"CLAUDE.md": sha("身分\n".encode("utf-8"))}} if history else {}
    if history:
        hist[version] = skeleton_hashes(root)
    write(root, "config/skeleton_history.json", json.dumps(hist, ensure_ascii=False, indent=2))


class Base(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, GIT_ENV)
        self.env.start()
        self.selftests = []  # 假外掛樹沒有真的 kb selftest：替身記下 zip、回過（換版前先驗新版）
        self.selftest_result = {"ok": True, "version": None, "step": None, "file": None, "line": None, "why": None}
        self.selftest = mock.patch.object(release, "_selftest", side_effect=lambda z: (self.selftests.append(Path(z)),
                                                                                         dict(self.selftest_result))[1])
        self.selftest.start()
        self.tmp = Path(tempfile.mkdtemp(prefix="kbrel-")).resolve()
        self.repo = self.tmp / "dev"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        make_tree(self.repo, "0.20.0")
        self.commit("0.20.0", tag="v0.20.0")

    def tearDown(self):
        self.selftest.stop()
        self.env.stop()
        rmtree(self.tmp)

    def commit(self, msg, tag=None):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", msg)
        if tag:
            git(self.repo, "tag", "-f", tag)  # 失敗情境的測試把 v0.20.0 移到新的 commit

    def names(self, zip_path):
        with zipfile.ZipFile(zip_path) as z:
            return sorted(z.namelist())


class Versions(unittest.TestCase):
    def test_tag_version(self):
        self.assertEqual(release.tag_version("v0.21.0"), "0.21.0")
        self.assertEqual(release.tag_version("0.21.0"), "0.21.0")
        for bad in ("v0.21", "release-1", "", "v1.2.3.4"):
            with self.subTest(bad=bad), self.assertRaises(release.ReleaseError):
                release.tag_version(bad)

    def test_versions_are_strict_like_the_client(self):
        """跟客戶端 parse_version 同一套：結尾換行、非 ASCII 數字、前導零都不收。"""
        for bad in ("v0.21.0\n", "0.21.0\n", "v٠.٢١.٠", "v0.21.00", "v00.21.0"):
            with self.subTest(bad=bad), self.assertRaises(release.ReleaseError):
                release.tag_version(bad)
        for bad in ("0.21.0\n", "٠.٢١.٠", "0.21.00"):
            with self.subTest(bad=bad):
                self.assertIsNone(release.parse_version(bad))

    def test_kind_matches_the_clients_rule(self):
        self.assertEqual(release.kind("0.20.0", "0.20.1"), "patch")
        self.assertEqual(release.kind("0.20.1", "0.21.0"), "minor")
        self.assertEqual(release.kind("1.2.3", "2.0.0"), "major")
        self.assertEqual(release.kind("0.21.0", "0.20.1"), "downgrade")


class Collect(Base):
    def test_only_the_allow_list_goes_into_the_zip_and_nothing_else(self):
        """驗收 15：zip 只含 D-213 清單（含 agents/，D-213 補）；design、tests、tools、repo 的 CLAUDE.md、.claude、git 設定檔都不放。"""
        files = release.collect(self.repo, "v0.20.0")
        names = set(files)
        for want in (".claude-plugin/plugin.json", "hooks/hooks.json", "hooks/session.py", "scripts/kb.py",
                     "scripts/kb/_lib/migrate.py", "agents/card-maker.md", "skills/manage/SKILL.md", "rules/core.md",
                     "templates/card.md", "skeleton/CLAUDE.md", "skeleton/案子/.gitkeep", "config/defaults.json",
                     "config/skeleton_history.json", "README.md", "CHANGELOG.md", "LICENSE"):
            self.assertIn(want, names)
        for banned in ("design/x.md", "tests/t.py", "tools/release.py", "CLAUDE.md", ".claude/settings.json", ".gitattributes"):
            self.assertNotIn(banned, names)

    def test_allowed_predicate(self):
        for ok in ("hooks/a.py", "agents/x.md", "README.md", ".claude-plugin/plugin.json"):
            self.assertTrue(release.allowed(ok), ok)
        for bad in ("design/x.md", "CLAUDE.md", ".claude/settings.json", "tests/a.py", "tools/release.py", "dist/a.zip",
                    "READMEx.md", "hooksx/a.py", "README.md/evil", ".gitignore"):
            self.assertFalse(release.allowed(bad), bad)


class Build(Base):
    def build(self, tag="v0.20.0"):
        return release.build(self.repo, tag, self.tmp / "dist")

    def test_build_makes_a_zip_with_sha256(self):
        got = self.build()
        self.assertEqual(got["version"], "0.20.0")
        self.assertTrue(Path(got["zip"]).is_file())
        self.assertEqual(got["sha256"], sha(Path(got["zip"]).read_bytes()))
        names = self.names(got["zip"])
        self.assertIn(".claude-plugin/plugin.json", names)
        self.assertNotIn("design/x.md", names)
        self.assertEqual(got["files"], len(names))

    def test_zip_is_reproducible(self):
        a = self.build()
        first = a["sha256"]
        b = self.build()
        self.assertEqual(b["sha256"], first)

    def test_default_out_dir_is_dist_under_the_repo(self):
        got = release.build(self.repo, "v0.20.0")
        self.assertEqual(Path(got["zip"]).parent, self.repo / "dist")
        self.assertEqual(Path(got["zip"]).name, "wiki-with-willy-0.20.0.zip")

    def test_unknown_tag_fails(self):
        with self.assertRaises(release.ReleaseError):
            self.build("v9.9.9")

    def test_extra_file_outside_the_list_is_caught_by_the_last_check(self):
        """故意放一個 design/x.md 進 zip → 擋（打包最後檢查，不管是怎麼混進去的）。"""
        z = self.tmp / "bad.zip"
        with zipfile.ZipFile(z, "w") as zf:
            for rel, data in release.collect(self.repo, "v0.20.0").items():
                zf.writestr(rel, data)
            zf.writestr("design/x.md", "設計")
        problems = release.check_zip(z, "0.20.0")
        self.assertTrue([p for p in problems if "design/x.md" in p and "清單" in p], problems)

    def test_clean_zip_has_no_problems(self):
        got = self.build()
        self.assertEqual(release.check_zip(got["zip"], "0.20.0"), [])

    def test_referenced_path_missing_is_caught(self):
        """hooks.json 引用到的路徑要在 zip 裡。"""
        make_tree(self.repo, "0.20.0", hooks_ref="hooks/missing.py")
        self.commit("壞引用", tag="v0.20.0")
        with self.assertRaises(release.ReleaseError) as cm:
            release.build(self.repo, "v0.20.0", self.tmp / "dist")
        self.assertIn("hooks/missing.py", str(cm.exception))

    def test_plugin_json_declared_paths_must_exist_too(self):
        write(self.repo, ".claude-plugin/plugin.json", json.dumps(
            {"name": "wiki-with-willy", "version": "0.20.0", "agents": ["./agents/card-maker.md", "./agents/gone.md"]}))
        self.commit("宣告的 agent 不在", tag="v0.20.0")
        with self.assertRaises(release.ReleaseError) as cm:
            release.build(self.repo, "v0.20.0", self.tmp / "dist")
        self.assertIn("agents/gone.md", str(cm.exception))

    def test_version_must_equal_the_tag(self):
        git(self.repo, "tag", "v0.21.0")  # 同一個 commit：plugin.json 還是 0.20.0
        with self.assertRaises(release.ReleaseError) as cm:
            self.build("v0.21.0")
        self.assertIn("0.20.0", str(cm.exception))
        self.assertIn("0.21.0", str(cm.exception))

    def test_changelog_needs_the_one_sentence_for_customers(self):
        """CHANGELOG 沒有給客戶的一句話 → 擋。"""
        write(self.repo, "CHANGELOG.md", "# CHANGELOG\n\n## 0.20.0 — 2026-10-24\n- **改了什麼**：x\n")
        self.commit("沒一句話", tag="v0.20.0")
        with self.assertRaises(release.ReleaseError) as cm:
            release.build(self.repo, "v0.20.0", self.tmp / "dist")
        self.assertIn("給客戶的一句話", str(cm.exception))

    def test_changelog_top_section_must_be_this_version(self):
        write(self.repo, "CHANGELOG.md", CHANGELOG.format(v="0.19.0", note="別版的。"))
        self.commit("最新一段不是這版", tag="v0.20.0")
        with self.assertRaises(release.ReleaseError):
            release.build(self.repo, "v0.20.0", self.tmp / "dist")

    def test_skeleton_history_must_have_this_version(self):
        """config/skeleton_history.json 要有這一版的骨架指紋（先跑 build --prepare），而且跟 tag 裡的骨架一致。"""
        make_tree(self.repo, "0.20.0", history=False)
        self.commit("沒歷史", tag="v0.20.0")
        with self.assertRaises(release.ReleaseError) as cm:
            release.build(self.repo, "v0.20.0", self.tmp / "dist")
        self.assertIn("--prepare", str(cm.exception))
        write(self.repo, "skeleton/CLAUDE.md", "骨架改了但歷史沒更新\n")
        write(self.repo, "config/skeleton_history.json", json.dumps({"0.20.0": {"CLAUDE.md": "0" * 64}}))
        self.commit("指紋對不上", tag="v0.20.0")
        with self.assertRaises(release.ReleaseError) as cm:
            release.build(self.repo, "v0.20.0", self.tmp / "dist")
        self.assertIn("--prepare", str(cm.exception))

    def test_all_problems_are_listed_together(self):
        write(self.repo, "CHANGELOG.md", "# CHANGELOG\n\n## 0.20.0 — 2026-10-24\n- x\n")
        self.commit("兩個問題", tag="v0.20.0")
        write(self.repo, ".claude-plugin/plugin.json", json.dumps({"name": "wiki-with-willy", "version": "0.20.5"}))
        self.commit("版本也不對", tag="v0.20.0")
        with self.assertRaises(release.ReleaseError) as cm:
            release.build(self.repo, "v0.20.0", self.tmp / "dist")
        text = str(cm.exception)
        self.assertIn("給客戶的一句話", text)
        self.assertIn("0.20.5", text)


class Verify(Base):
    """換版前先驗新版 要做的事三、驗收 8：Python 3.10 語法與 zip 自己的 kb selftest。"""

    def test_py310_syntax_is_refused_with_file_and_line(self):
        write(self.repo, "scripts/kb/_lib/new.py", "x = 1\n\ndef f[T](x):\n    return x\n")
        write(self.repo, "hooks/also.py", "try:\n    pass\nexcept* ValueError:\n    pass\n")
        self.commit("新寫法", tag="v0.20.0")
        with self.assertRaises(release.ReleaseError) as cm:
            release.build(self.repo, "v0.20.0", self.tmp / "dist")
        msg = str(cm.exception)
        self.assertIn("scripts/kb/_lib/new.py 第 3 行：Python 3.10 不認得這種寫法", msg)
        self.assertRegex(msg, r"hooks/also\.py 第 \d+ 行：Python 3\.10 不認得這種寫法")  # except* 報哪一行看 Python 版本
        self.assertFalse((self.tmp / "dist" / "wiki-with-willy-0.20.0.zip").exists())

    def test_selftest_failure_is_refused_and_no_zip_left(self):
        self.selftest_result = {"ok": False, "version": "0.20.0", "step": "hooks", "file": None, "line": None,
                                "why": "守門（hooks/guard.py）該擋沒擋"}
        with self.assertRaises(release.ReleaseError) as cm:
            release.build(self.repo, "v0.20.0", self.tmp / "dist")
        self.assertIn("自我檢查沒過：hooks：守門（hooks/guard.py）該擋沒擋", str(cm.exception))
        self.assertFalse((self.tmp / "dist" / "wiki-with-willy-0.20.0.zip").exists())

    def test_selftest_runs_on_the_built_zip(self):
        got = release.build(self.repo, "v0.20.0", self.tmp / "dist")
        self.assertEqual(len(self.selftests), 1)
        self.assertEqual(self.selftests[0].parent, Path(got["zip"]).parent)

    def test_failed_rebuild_keeps_the_good_zip_of_the_same_tag(self):
        """裁定 16：先寫暫存名，全部檢查過才改名；同一個 tag 重打失敗，先前打好的那份不動、也不留暫存檔。"""
        got = release.build(self.repo, "v0.20.0", self.tmp / "dist")
        good = Path(got["zip"]).read_bytes()
        self.selftest_result = {"ok": False, "step": "hooks", "why": "x"}
        with self.assertRaises(release.ReleaseError):
            release.build(self.repo, "v0.20.0", self.tmp / "dist")
        self.assertEqual(Path(got["zip"]).read_bytes(), good)
        self.assertEqual(sorted(p.name for p in (self.tmp / "dist").iterdir()), ["wiki-with-willy-0.20.0.zip"])
        self.assertNotEqual(self.selftests[-1], Path(got["zip"]), "自我檢查跑在暫存名上")

    def test_all_problems_listed_together_with_the_selftest(self):
        write(self.repo, "scripts/kb/_lib/new.py", "type X = int\n")
        self.commit("新寫法", tag="v0.20.0")
        self.selftest_result = {"ok": False, "step": "import", "file": "scripts/kb/_lib/new.py", "line": 1,
                                "why": "SyntaxError: invalid syntax"}
        with self.assertRaises(release.ReleaseError) as cm:
            release.build(self.repo, "v0.20.0", self.tmp / "dist")
        msg = str(cm.exception)
        self.assertIn("Python 3.10 不認得", msg)
        self.assertIn("自我檢查沒過：import：scripts/kb/_lib/new.py 第 1 行：SyntaxError: invalid syntax", msg)

    def test_selftest_that_cannot_run_is_a_problem(self):
        self.selftest.stop()
        try:
            with self.assertRaises(release.ReleaseError) as cm:  # 假樹的 kb.py 只印一行，沒有 selftest
                release.build(self.repo, "v0.20.0", self.tmp / "dist")
        finally:
            self.selftest.start()
        self.assertIn("自我檢查沒過", str(cm.exception))


class Skipped(Base):
    def test_build_lists_the_top_level_names_it_left_out(self):
        """測試 I-1：清單外的檔照樣不放，但 build 要說略過了哪些頂層（新的執行用資料夾忘了加 ALLOW_DIRS 才看得到）。"""
        got = release.build(self.repo, "v0.20.0", self.tmp / "dist")
        for name in ("design", "tests", "tools", "CLAUDE.md", ".claude"):
            self.assertIn(name, got["skipped"])
        self.assertNotIn("scripts", got["skipped"])


class RelativeRepo(Base):
    def test_relative_repo_still_gives_an_absolute_zip_path(self):
        """桌面版確認準備時：--repo . 打出的 zip 路徑是相對的，publish 在公開 clone 裡跑 gh 找不到。"""
        old = os.getcwd()
        os.chdir(self.tmp)
        try:
            got = release.build("dev", "v0.20.0", "out")
        finally:
            os.chdir(old)
        self.assertTrue(Path(got["zip"]).is_absolute())
        self.assertTrue(Path(got["zip"]).is_file())


class PatchRule(Base):
    """D-217：小修不能改狀態檔 schema、骨架、_lib/migrate.py 的表；跟上一個 tag 比。"""

    def patch(self, **kw):
        make_tree(self.repo, "0.20.1", note="修好日期錯誤。", **kw)
        self.commit("0.20.1")
        git(self.repo, "tag", "v0.20.1")
        return release.build(self.repo, "v0.20.1", self.tmp / "dist")

    def test_previous_tag_is_the_greatest_older_one(self):
        git(self.repo, "tag", "v0.19.0")
        git(self.repo, "tag", "v0.20.1-rc")  # 不是 X.Y.Z，忽略
        self.assertEqual(release.previous_tag(self.repo, "0.20.1"), "v0.20.0")
        self.assertEqual(release.previous_tag(self.repo, "0.20.0"), "v0.19.0")
        self.assertIsNone(release.previous_tag(self.repo, "0.1.0"))

    def test_patch_with_no_format_change_is_fine(self):
        self.assertEqual(self.patch()["version"], "0.20.1")

    def test_patch_that_changes_a_schema_constant_is_refused(self):
        """跟上一個 tag 比改了 inventory 的 schema 常數卻標小修 → 擋。"""
        with self.assertRaises(release.ReleaseError) as cm:
            self.patch(schema=3)
        self.assertIn("scripts/kb/_lib/inventory.py", str(cm.exception))
        self.assertIn("SCHEMA_VERSION", str(cm.exception))

    def test_patch_that_changes_the_skeleton_is_refused(self):
        with self.assertRaises(release.ReleaseError) as cm:
            self.patch(skeleton="改過的身分\n")
        self.assertIn("skeleton/CLAUDE.md", str(cm.exception))

    def test_patch_that_changes_the_migrate_table_is_refused(self):
        make_tree(self.repo, "0.20.1", note="修好日期錯誤。")
        write(self.repo, "scripts/kb/_lib/migrate.py", "STATE_FILES = (1,)\n")
        self.commit("表有變", tag="v0.20.1")
        with self.assertRaises(release.ReleaseError) as cm:
            release.build(self.repo, "v0.20.1", self.tmp / "dist")
        self.assertIn("migrate.py", str(cm.exception))

    def test_patch_that_changes_any_schema_named_constant_is_refused(self):
        """測試 L-1：名稱含 SCHEMA 的常數（例如 upgrade.py 的 HISTORY_SCHEMA）也算格式版本。"""
        write(self.repo, "scripts/kb/_lib/upgrade.py", "HISTORY_SCHEMA = 1\n")
        self.commit("0.20.0 加檔", tag="v0.20.0")
        make_tree(self.repo, "0.20.1", note="修好日期錯誤。")
        write(self.repo, "scripts/kb/_lib/upgrade.py", "HISTORY_SCHEMA = 2\n")
        self.commit("0.20.1", tag="v0.20.1")
        with self.assertRaises(release.ReleaseError) as cm:
            release.build(self.repo, "v0.20.1", self.tmp / "dist")
        self.assertIn("HISTORY_SCHEMA", str(cm.exception))

    def test_patch_that_changes_a_literal_schema_version_is_refused(self):
        """測試 L-1：寫在字面裡的 "schema_version": N（env.py、turn.py…）改了也擋。"""
        write(self.repo, "scripts/kb/_lib/env.py", 'DEFAULT = {"schema_version": 1, "machines": {}}\n')
        self.commit("0.20.0 加檔", tag="v0.20.0")
        make_tree(self.repo, "0.20.1", note="修好日期錯誤。")
        write(self.repo, "scripts/kb/_lib/env.py", 'DEFAULT = {"schema_version": 2, "machines": {}}\n')
        self.commit("0.20.1", tag="v0.20.1")
        with self.assertRaises(release.ReleaseError) as cm:
            release.build(self.repo, "v0.20.1", self.tmp / "dist")
        self.assertIn("scripts/kb/_lib/env.py", str(cm.exception))

    def test_patch_that_changes_schema_version_only_in_a_docstring_is_allowed(self):
        """B-448：docstring、註解、一般字串裡寫到的 "schema_version": N 不算格式版本，改了照樣能當小修發。"""
        write(self.repo, "scripts/kb/_lib/notes.py", '"""說明：檔頭是 {"schema_version": 1}。"""\n# 註解 "schema_version": 1\n'
                                                     'X = \'"schema_version": 1\'\n')
        self.commit("0.20.0 加檔", tag="v0.20.0")
        make_tree(self.repo, "0.20.1", note="修好日期錯誤。")
        write(self.repo, "scripts/kb/_lib/notes.py", '"""說明：檔頭是 {"schema_version": 2}。"""\n# 註解 "schema_version": 2\n'
                                                     'X = \'"schema_version": 2\'\n')
        self.commit("0.20.1", tag="v0.20.1")
        self.assertEqual(release.build(self.repo, "v0.20.1", self.tmp / "dist")["version"], "0.20.1")

    def code_change_refused(self, old, new):
        write(self.repo, "scripts/kb/_lib/box.py", old)
        self.commit("0.20.0 加檔", tag="v0.20.0")
        make_tree(self.repo, "0.20.1", note="修好日期錯誤。")
        write(self.repo, "scripts/kb/_lib/box.py", new)
        self.commit("0.20.1", tag="v0.20.1")
        with self.assertRaises(release.ReleaseError) as cm:
            release.build(self.repo, "v0.20.1", self.tmp / "dist")
        self.assertIn("scripts/kb/_lib/box.py", str(cm.exception))

    def test_patch_that_changes_a_schema_version_dict_in_code_is_refused(self):
        """B-448：程式裡真的 dict 字面（包在函式、呼叫裡也算）改了照擋。"""
        self.code_change_refused('def empty():\n    return dict(items=[], **{"schema_version": 1})\n',
                                 'def empty():\n    return dict(items=[], **{"schema_version": 2})\n')

    def test_patch_that_changes_a_schema_version_keyword_is_refused(self):
        """B-448：呼叫參數 schema_version=N 改了照擋。"""
        self.code_change_refused("def empty():\n    return dict(schema_version=1, items=[])\n",
                                 "def empty():\n    return dict(schema_version=2, items=[])\n")

    def test_skeleton_history_file_itself_may_change_in_a_patch(self):
        """config/skeleton_history.json 每版都會追加，不算骨架改動。"""
        self.assertEqual(self.patch()["version"], "0.20.1")

    def test_minor_may_change_all_of_them(self):
        make_tree(self.repo, "0.21.0", note="大升級。", schema=3, skeleton="新身分\n", fmt=2)
        write(self.repo, "scripts/kb/_lib/migrate.py", "STATE_FILES = (1,)\n")
        self.commit("0.21.0", tag="v0.21.0")
        self.assertEqual(release.build(self.repo, "v0.21.0", self.tmp / "dist")["version"], "0.21.0")

    def test_first_release_without_a_previous_tag_skips_the_rule(self):
        rmtree(self.repo / ".git")
        git(self.repo, "init", "-q", "-b", "main")
        make_tree(self.repo, "0.20.1", note="第一版。")
        self.commit("第一版", tag="v0.20.1")
        self.assertEqual(release.build(self.repo, "v0.20.1", self.tmp / "dist")["version"], "0.20.1")


class FormatRule(Base):
    """記帳 1a（D-335）：遷移表比上一個 tag 多了列＝大升級，流水檔格式版本（streams.FORMAT_VERSION）要比上一個 tag 大。"""

    def minor(self, migrate=None, fmt=1):
        make_tree(self.repo, "0.21.0", note="大升級。", fmt=fmt)
        if migrate is not None:
            write(self.repo, "scripts/kb/_lib/migrate.py", migrate)
        self.commit("0.21.0", tag="v0.21.0")
        return release.build(self.repo, "v0.21.0", self.tmp / "dist")

    def test_new_row_without_format_bump_is_refused(self):
        with self.assertRaises(release.ReleaseError) as cm:
            self.minor("STATE_FILES = (\n    Migration(1),\n)\n")
        msg = str(cm.exception)
        self.assertIn("FORMAT_VERSION", msg)
        self.assertIn("STATE_FILES", msg)
        self.assertIn("要升", msg)
        self.assertFalse(list((self.tmp / "dist").glob("*.zip")))

    def test_new_row_with_format_bump_passes(self):
        self.assertEqual(self.minor("STATE_FILES = (\n    Migration(1),\n)\n", fmt=2)["version"], "0.21.0")

    def test_format_bump_without_new_rows_passes(self):
        """驗收 4：只升格式版本、遷移表沒新列（1a 單獨跑時）不擋。"""
        self.assertEqual(self.minor(fmt=2)["version"], "0.21.0")

    def test_no_new_rows_no_bump_passes(self):
        self.assertEqual(self.minor()["version"], "0.21.0")

    def test_rows_of_the_other_two_tables_count_too(self):
        for name in ("CARD_HEADER_MIGRATIONS", "SYNTHESIS_MIGRATIONS"):
            with self.subTest(name=name):
                with self.assertRaises(release.ReleaseError) as cm:
                    self.minor(f'STATE_FILES = ()\n{name} = [{{"from": "1", "to": "2"}}]\n')
                self.assertIn(name, str(cm.exception))

    def test_migration_rows_counts_literal_tables(self):
        text = ('STATE_FILES = (\n    Migration(1),\n    Migration(2),\n)\nCARD_HEADER_MIGRATIONS = []\n'
                'SYNTHESIS_MIGRATIONS = [{"from": "1"}]  # 註解\n').encode("utf-8")
        self.assertEqual(release.migration_rows(text),
                         {"STATE_FILES": 2, "CARD_HEADER_MIGRATIONS": 0, "SYNTHESIS_MIGRATIONS": 1})
        self.assertEqual(release.migration_rows(b"STATE_FILES = ()\n")["SYNTHESIS_MIGRATIONS"], 0)  # 沒有這張表算 0 列
        self.assertEqual(release.format_version(b"FORMAT_VERSION = 3\n"), 3)
        self.assertIsNone(release.format_version(b"X = 1\n"))

    def test_real_repo_tables_are_readable(self):
        """這個 repo 自己的 migrate.py、streams.py 讀得出列數與格式版本（表改寫法時要跟著改發行程式）。"""
        root = Path(__file__).resolve().parent.parent / "scripts" / "kb" / "_lib"
        rows = release.migration_rows((root / "migrate.py").read_bytes())
        self.assertTrue(all(isinstance(n, int) for n in rows.values()), rows)
        self.assertGreater(rows["STATE_FILES"], 0)
        self.assertGreater(rows["SYNTHESIS_MIGRATIONS"], 0)
        self.assertIsInstance(release.format_version((root / "streams.py").read_bytes()), int)


class Prepare(Base):
    def test_prepare_appends_this_versions_skeleton_fingerprints(self):
        """build --prepare 追加 skeleton_history.json（在打 tag 之前的發行 commit 裡做）。"""
        make_tree(self.repo, "0.21.0", note="大升級。", history=False)
        write(self.repo, "config/skeleton_history.json", json.dumps({"0.20.0": {"CLAUDE.md": "a" * 64}}))
        path = release.prepare(self.repo, "v0.21.0")
        self.assertEqual(Path(path), self.repo / "config" / "skeleton_history.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["0.20.0"], {"CLAUDE.md": "a" * 64}, "舊的保留")
        self.assertEqual(data["0.21.0"], {"CLAUDE.md": sha("身分\n".encode("utf-8"))})
        self.assertNotIn(".gitkeep", json.dumps(data))

    def test_prepare_twice_gives_the_same_file(self):
        make_tree(self.repo, "0.21.0", note="大升級。", history=False)
        write(self.repo, "config/skeleton_history.json", "{}")
        release.prepare(self.repo, "v0.21.0")
        first = (self.repo / "config" / "skeleton_history.json").read_bytes()
        release.prepare(self.repo, "v0.21.0")
        self.assertEqual((self.repo / "config" / "skeleton_history.json").read_bytes(), first)

    def test_prepare_refuses_when_version_is_not_the_tag(self):
        with self.assertRaises(release.ReleaseError):
            release.prepare(self.repo, "v0.21.0")

    def test_prepare_then_build_passes(self):
        make_tree(self.repo, "0.21.0", note="大升級。", history=False)
        write(self.repo, "config/skeleton_history.json", "{}")
        release.prepare(self.repo, "v0.21.0")
        self.commit("0.21.0", tag="v0.21.0")
        self.assertEqual(release.build(self.repo, "v0.21.0", self.tmp / "dist")["version"], "0.21.0")


class Publish(Base):
    """驗收 16：本機假的公開 repo（bare）、gh 與抓清單的替身。"""

    def setUp(self):
        super().setUp()
        make_tree(self.repo, "0.21.0", note="日程可以匯出成 Excel。", schema=2)
        self.commit("0.21.0", tag="v0.21.0")
        self.bare = self.tmp / "public.git"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(self.bare))
        self.public = self.tmp / "public"
        git(self.tmp, "clone", "-q", str(self.bare), str(self.public))
        git(self.public, "remote", "set-url", "origin", PUBLIC_URL + ".git")
        git(self.public, "remote", "set-url", "--push", "origin", str(self.bare))
        write(self.public, "README.md", "公開 repo\n")
        git(self.public, "add", "-A")
        git(self.public, "commit", "-q", "-m", "init")
        git(self.public, "push", "-q", "origin", "main")
        self.gh_calls = []
        self.releases = set()  # gh 這邊已經建好的 release（tag）
        self.fail_push = 0  # 接下來幾次 git push 要失敗
        self.fetches = []
        self.served = ["0.20.0"]  # 每次抓回的版本；用完維持最後一個
        self.sleeps = []
        self.clock = [0.0]
        real_run = release._run

        def run(argv, cwd=None, **kw):
            if argv[0] == "gh":
                self.gh_calls.append((list(argv), cwd))
                if argv[1:3] == ["release", "view"]:
                    if argv[3] not in self.releases:
                        raise release.ReleaseError("gh release view 失敗：release not found")
                    return "{}"
                if argv[1:3] == ["release", "create"]:
                    self.releases.add(argv[3])
                return ""
            if argv[:2] == ["git", "push"] and self.fail_push:
                self.fail_push -= 1
                raise release.ReleaseError("git push 失敗：連不上")
            return real_run(argv, cwd=cwd, **kw)

        def fetch(url, timeout):
            self.fetches.append(url)
            version = self.served.pop(0) if len(self.served) > 1 else self.served[0]
            return json.dumps({"plugins": [{"name": "wiki-with-willy", "version": version}]})

        def sleep(sec):
            self.sleeps.append(sec)
            self.clock[0] += sec
        self.patches = [mock.patch.object(release, "_run", side_effect=run), mock.patch.object(release, "_fetch", side_effect=fetch),
                        mock.patch.object(release, "_sleep", side_effect=sleep),
                        mock.patch.object(release, "_clock", side_effect=lambda: self.clock[0])]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        super().tearDown()

    def fresh_clone(self):
        self.n = getattr(self, "n", 0) + 1
        clone = self.tmp / f"check{self.n}"
        git(self.tmp, "clone", "-q", str(self.bare), str(clone))
        return clone

    def remote_file(self, rel):
        clone = self.fresh_clone()
        p = clone / rel
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

    def publish(self, who="all", wait=15):
        return release.publish(self.repo, "v0.21.0", self.public, who, wait=wait)

    def test_waits_until_the_list_shows_the_new_version_then_changes_the_roster(self):
        self.served = ["0.20.0", "0.20.0", "0.21.0"]
        got = self.publish(who=[ID1])
        self.assertEqual(self.sleeps, [30, 30], "每 30 秒抓一次，抓到新版就停")
        self.assertEqual(len(self.fetches), 3)
        self.assertTrue(all(u == MANIFEST_URL for u in self.fetches))
        market = self.remote_file("marketplace.json")
        entry = next(p for p in market["plugins"] if p["name"] == "wiki-with-willy")
        self.assertEqual(entry["version"], "0.21.0")
        self.assertEqual(entry["source"]["source"], "archive")
        self.assertTrue(entry["source"]["url"].endswith("/releases/download/v0.21.0/wiki-with-willy-0.21.0.zip"))
        self.assertEqual(entry["source"]["sha256"], got["sha256"])
        self.assertEqual(self.remote_file("rollout.json"),
                         {"schema_version": 1, "versions": {"0.21.0": {"for": [ID1], "note": "日程可以匯出成 Excel。"}}})

    def test_gh_release_create_with_the_zip_and_run_in_the_public_clone(self):
        self.served = ["0.21.0"]
        got = self.publish()
        argv, cwd = next(c for c in self.gh_calls if c[0][1:3] == ["release", "create"])
        self.assertEqual(argv[:4], ["gh", "release", "create", "v0.21.0"])
        self.assertIn(str(got["zip"]), argv)
        self.assertEqual(Path(cwd), self.public)

    def test_rerun_after_a_failed_push_finishes_without_recreating_the_release(self):
        """gh release 建好之後推清單失敗：重跑 publish 不再建 release（會撞「已經存在」），改成把同一個 zip 補傳上去，
        本機那個還沒推的清單 commit 也要推上去，接著等清單、改名單。"""
        self.served = ["0.21.0"]
        self.fail_push = 1
        with self.assertRaises(release.ReleaseError):
            self.publish()
        self.assertIsNone(self.remote_file("marketplace.json"))
        got = self.publish()
        creates = [a for a, _c in self.gh_calls if a[1:3] == ["release", "create"]]
        uploads = [a for a, _c in self.gh_calls if a[1:3] == ["release", "upload"]]
        self.assertEqual(len(creates), 1, "release 只建一次")
        self.assertEqual(len(uploads), 1)
        self.assertEqual(uploads[0][3], "v0.21.0")
        self.assertIn(str(got["zip"]), uploads[0])
        self.assertIn("--clobber", uploads[0])
        entry = next(p for p in self.remote_file("marketplace.json")["plugins"] if p["name"] == "wiki-with-willy")
        self.assertEqual((entry["version"], entry["source"]["sha256"]), ("0.21.0", got["sha256"]))
        self.assertEqual(self.remote_file("rollout.json")["versions"]["0.21.0"]["for"], "all")

    def test_dirty_public_clone_refuses_before_anything_is_published(self):
        """公開 repo 的 clone 有沒 commit 的改動（已暫存或改了追蹤的檔）：什麼都不做，免得那些改動被一起 commit 推出去。"""
        write(self.public, "雜物.txt", "不該推\n")
        git(self.public, "add", "雜物.txt")
        self.served = ["0.21.0"]
        with self.assertRaises(release.ReleaseError) as cm:
            self.publish()
        self.assertIn("沒 commit 的改動", str(cm.exception))
        self.assertEqual(self.gh_calls, [])
        self.assertIsNone(self.remote_file("marketplace.json"))

    def test_untracked_files_in_the_public_clone_do_not_block(self):
        write(self.public, "筆記.txt", "沒加進 git\n")
        self.served = ["0.21.0"]
        self.publish()
        self.assertFalse((self.fresh_clone() / "筆記.txt").exists())

    def test_order_is_zip_then_list_then_roster(self):
        """D-218：先推 zip 與清單、確認抓得到新版，才改名單。"""
        events = []
        real = release._run

        def run(argv, cwd=None, **kw):
            if argv[0] == "gh":
                if argv[1:3] == ["release", "view"]:  # 還沒有這個 release
                    raise release.ReleaseError("gh release view 失敗：release not found")
                events.append("gh")
                return ""
            if argv[:2] == ["git", "push"]:
                events.append("push")
            return real.__wrapped__(argv, cwd=cwd, **kw) if hasattr(real, "__wrapped__") else subprocess_run(argv, cwd)
        self.patches[0].stop()
        with mock.patch.object(release, "_run", side_effect=run), \
                mock.patch.object(release, "_fetch", side_effect=lambda u, t: events.append("fetch") or json.dumps(
                    {"plugins": [{"name": "wiki-with-willy", "version": "0.21.0"}]})):
            self.publish()
        self.assertEqual(events, ["gh", "push", "fetch", "push"])
        self.patches[0].start()

    def test_timeout_stops_and_leaves_the_roster_untouched(self):
        """超過 --wait → 停下來、名單沒改。"""
        self.served = ["0.20.0"]
        with self.assertRaises(release.ReleaseError) as cm:
            self.publish(wait=2)
        self.assertIn("名單沒改", str(cm.exception))
        self.assertIsNone(self.remote_file("rollout.json"))
        self.assertEqual(next(p for p in self.remote_file("marketplace.json")["plugins"])["version"], "0.21.0",
                         "清單與 zip 已經推了，重跑 rollout 就好")
        self.assertLessEqual(max(self.clock), 2 * 60 + 30)

    def test_empty_manifest_url_refuses_before_anything_is_published(self):
        write(self.repo, "config/defaults.json", json.dumps({"schema_version": 1, "update_manifest_url": ""}))
        self.commit("網址還沒填", tag="v0.21.0")  # 看的是 tag 裡的設定
        with self.assertRaises(release.ReleaseError) as cm:
            self.publish()
        self.assertIn("update_manifest_url", str(cm.exception))
        self.assertEqual(self.gh_calls, [])
        self.assertIsNone(self.remote_file("marketplace.json"))

    def test_url_filled_only_in_the_working_tree_refuses(self):
        """測試 M-1：tag 裡網址是空的、只有工作區填了沒 commit → 擋（客戶拿到的是 tag 裡的設定）。"""
        write(self.repo, "config/defaults.json", json.dumps({"schema_version": 1, "update_manifest_url": "",
                                                             "update_rollout_url": ""}))
        self.commit("網址還沒填", tag="v0.21.0")
        write(self.repo, "config/defaults.json", json.dumps({"schema_version": 1, "update_manifest_url": MANIFEST_URL,
                                                             "update_rollout_url": ROLLOUT_URL}))
        with self.assertRaises(release.ReleaseError) as cm:
            self.publish()
        self.assertIn("tag 裡", str(cm.exception))
        self.assertEqual(self.gh_calls, [])
        self.assertIsNone(self.remote_file("marketplace.json"))

    def test_empty_rollout_url_refuses(self):
        """測試 M-1：名單網址空的話客戶端名單是空的、沒人拿得到新版 → 也擋。"""
        write(self.repo, "config/defaults.json", json.dumps({"schema_version": 1, "update_manifest_url": MANIFEST_URL,
                                                             "update_rollout_url": ""}))
        self.commit("名單網址沒填", tag="v0.21.0")
        with self.assertRaises(release.ReleaseError) as cm:
            self.publish()
        self.assertIn("update_rollout_url", str(cm.exception))
        self.assertEqual(self.gh_calls, [])

    def test_note_comes_from_the_tag_not_the_working_tree(self):
        write(self.repo, "CHANGELOG.md", CHANGELOG.format(v="0.21.0", note="工作區改過沒 commit 的。"))
        self.served = ["0.21.0"]
        self.publish()
        self.assertEqual(self.remote_file("rollout.json")["versions"]["0.21.0"]["note"], "日程可以匯出成 Excel。")

    def test_origin_with_a_token_refuses_and_never_prints_it(self):
        """測試 M-2：origin 帶帳密 → 擋、什麼都沒發，錯誤句不印 token。"""
        for bad in ("https://ghp_SECRET123@github.com/owner/r.git", "https://user:tok@github.com/owner/r",
                    "https://gitlab.com/owner/r.git"):
            git(self.public, "remote", "set-url", "origin", bad)
            with self.subTest(bad=bad), self.assertRaises(release.ReleaseError) as cm:
                self.publish()
            self.assertNotIn("SECRET", str(cm.exception))
            self.assertNotIn("user:tok", str(cm.exception))
        self.assertEqual(self.gh_calls, [])
        self.assertIsNone(self.remote_file("marketplace.json"))

    def test_ssh_origin_gives_the_https_download_url(self):
        git(self.public, "remote", "set-url", "origin", "git@github.com:owner/wiki-with-willy.git")
        self.served = ["0.21.0"]
        self.publish()
        entry = next(p for p in self.remote_file("marketplace.json")["plugins"] if p["name"] == "wiki-with-willy")
        self.assertEqual(entry["source"]["url"],
                         PUBLIC_URL + "/releases/download/v0.21.0/wiki-with-willy-0.21.0.zip")

    def test_build_failure_publishes_nothing(self):
        git(self.repo, "tag", "v0.22.0")
        with self.assertRaises(release.ReleaseError):
            release.publish(self.repo, "v0.22.0", self.public, "all")
        self.assertEqual(self.gh_calls, [])

    def test_gh_failure_stops_before_the_list_is_touched(self):
        def run(argv, cwd=None, **kw):
            if argv[0] == "gh":
                raise release.ReleaseError("gh 失敗：release 已經存在")
            return subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8").stdout
        self.patches[0].stop()
        with mock.patch.object(release, "_run", side_effect=run):
            with self.assertRaises(release.ReleaseError):
                self.publish()
        self.patches[0].start()
        self.assertIsNone(self.remote_file("marketplace.json"))

    def test_roster_forms_all_none_and_ids(self):
        self.served = ["0.21.0"]
        self.publish(who="none")
        self.assertEqual(self.remote_file("rollout.json")["versions"]["0.21.0"]["for"], "none")

    def test_marketplace_json_keeps_other_fields_on_update(self):
        write(self.public, "marketplace.json", json.dumps({"name": "willy", "owner": {"name": "w"}, "description": "d", "plugins": [
            {"name": "wiki-with-willy", "description": "d2", "version": "0.20.0",
             "source": {"source": "archive", "url": "https://old", "sha256": "0" * 64}}]}))
        git(self.public, "add", "-A")
        git(self.public, "commit", "-q", "-m", "舊清單")
        git(self.public, "push", "-q", "origin", "main")
        self.served = ["0.21.0"]
        self.publish()
        market = self.remote_file("marketplace.json")
        self.assertEqual((market["name"], market["owner"], market["description"]), ("willy", {"name": "w"}, "d"))
        self.assertEqual(len(market["plugins"]), 1)
        self.assertEqual(market["plugins"][0]["description"], "d2")
        self.assertEqual(market["plugins"][0]["version"], "0.21.0")


def subprocess_run(argv, cwd):
    return subprocess.run(argv, cwd=str(cwd) if cwd else None, capture_output=True, text=True, encoding="utf-8").stdout


class Rollout(Base):
    def setUp(self):
        super().setUp()
        self.bare = self.tmp / "public.git"
        git(self.tmp, "init", "-q", "--bare", "-b", "main", str(self.bare))
        self.public = self.tmp / "public"
        git(self.tmp, "clone", "-q", str(self.bare), str(self.public))
        write(self.public, "rollout.json", json.dumps({"schema_version": 1, "versions": {
            "0.21.0": {"for": [ID1], "note": "日程可以匯出成 Excel"}}}))
        git(self.public, "add", "-A")
        git(self.public, "commit", "-q", "-m", "init")
        git(self.public, "push", "-q", "origin", "main")

    def fresh_clone(self):
        self.n = getattr(self, "n", 0) + 1
        clone = self.tmp / f"check{self.n}"
        git(self.tmp, "clone", "-q", str(self.bare), str(clone))
        return clone

    def remote(self):
        clone = self.fresh_clone()
        return json.loads((clone / "rollout.json").read_text(encoding="utf-8"))

    def test_none_stops_the_spread_and_keeps_the_note(self):
        """驗收 16 / 例句 17：rollout 0.21.0 --none。"""
        release.rollout(self.repo, "0.21.0", self.public, "none")
        self.assertEqual(self.remote()["versions"]["0.21.0"], {"for": "none", "note": "日程可以匯出成 Excel"})

    def test_all_and_ids(self):
        release.rollout(self.repo, "0.21.0", self.public, "all")
        self.assertEqual(self.remote()["versions"]["0.21.0"]["for"], "all")
        release.rollout(self.repo, "0.21.0", self.public, [ID1, ID2])
        self.assertEqual(self.remote()["versions"]["0.21.0"]["for"], [ID1, ID2])

    def test_vault_id_with_a_trailing_newline_is_refused(self):
        """測試 L-6：整串比對，kb-xxxxxxxx 後面帶換行不收。"""
        with self.assertRaises(release.ReleaseError):
            release.rollout(self.repo, "0.21.0", self.public, [ID1 + "\n"])
        self.assertEqual(self.remote()["versions"]["0.21.0"]["for"], [ID1])

    def test_dirty_public_clone_refuses(self):
        write(self.public, "README.md", "改了沒 commit\n")
        git(self.public, "add", "README.md")
        with self.assertRaises(release.ReleaseError) as cm:
            release.rollout(self.repo, "0.21.0", self.public, "none")
        self.assertIn("沒 commit 的改動", str(cm.exception))
        self.assertEqual(self.remote()["versions"]["0.21.0"]["for"], [ID1])

    def test_other_versions_are_left_alone(self):
        write(self.public, "rollout.json", json.dumps({"schema_version": 1, "versions": {
            "0.21.0": {"for": [ID1], "note": "a"}, "0.20.1": {"for": "all", "note": "b"}}}))
        git(self.public, "add", "-A")
        git(self.public, "commit", "-q", "-m", "兩版")
        git(self.public, "push", "-q", "origin", "main")
        release.rollout(self.repo, "0.21.0", self.public, "none")
        self.assertEqual(self.remote()["versions"]["0.20.1"], {"for": "all", "note": "b"})

    def test_new_version_takes_its_note_from_the_changelog(self):
        make_tree(self.repo, "0.22.0", note="新的一句話。")
        self.commit("0.22.0")
        release.rollout(self.repo, "0.22.0", self.public, "all")
        self.assertEqual(self.remote()["versions"]["0.22.0"]["note"], "新的一句話。")

    def test_no_note_anywhere_refuses(self):
        with self.assertRaises(release.ReleaseError):
            release.rollout(self.repo, "9.9.9", self.public, "all")

    def test_bad_vault_id_refuses_and_changes_nothing(self):
        before = self.remote()
        with self.assertRaises(release.ReleaseError):
            release.rollout(self.repo, "0.21.0", self.public, ["kb-壞的"])
        self.assertEqual(self.remote(), before)

    def test_roster_file_is_created_when_missing(self):
        (self.public / "rollout.json").unlink()
        git(self.public, "add", "-A")
        git(self.public, "commit", "-q", "-m", "刪掉")
        git(self.public, "push", "-q", "origin", "main")
        make_tree(self.repo, "0.21.0", note="日程可以匯出成 Excel。")
        self.commit("0.21.0")
        release.rollout(self.repo, "0.21.0", self.public, [ID1])
        self.assertEqual(self.remote()["schema_version"], 1)


class Cli(Base):
    def run_main(self, *argv):
        import contextlib
        import io
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = release.main(list(argv))
            except SystemExit as e:
                code = e.code
        return code, out.getvalue(), err.getvalue()

    def test_build_prints_sha256_and_exits_0(self):
        code, out, _err = self.run_main("build", "v0.20.0", "--repo", str(self.repo), "--out", str(self.tmp / "dist"))
        self.assertEqual(code, 0)
        self.assertRegex(out, r"sha256[:：] ?[0-9a-f]{64}")
        self.assertIn("0.20.0", out)

    def test_failure_prints_reason_and_exits_1(self):
        code, out, err = self.run_main("build", "v9.9.9", "--repo", str(self.repo))
        self.assertEqual(code, 1)
        self.assertTrue((out + err).strip())

    def test_prepare_flag(self):
        make_tree(self.repo, "0.21.0", note="大升級。", history=False)
        write(self.repo, "config/skeleton_history.json", "{}")
        code, _out, _err = self.run_main("build", "v0.21.0", "--prepare", "--repo", str(self.repo))
        self.assertEqual(code, 0)
        self.assertIn("0.21.0", json.loads((self.repo / "config" / "skeleton_history.json").read_text(encoding="utf-8")))

    def test_publish_needs_exactly_one_of_for_all_none(self):
        for extra in ([], ["--all", "--none"], ["--for", ID1, "--all"]):
            with self.subTest(extra=extra):
                code, _o, _e = self.run_main("publish", "v0.20.0", "--public", str(self.tmp), *extra)
                self.assertNotEqual(code, 0)

    def test_rollout_arguments(self):
        parser = release.build_parser()
        got = parser.parse_args(["rollout", "0.21.0", "--public", "x", "--for", ID1, ID2])
        self.assertEqual((got.command, got.version, got.who), ("rollout", "0.21.0", [ID1, ID2]))
        got = parser.parse_args(["rollout", "0.21.0", "--public", "x", "--none"])
        self.assertEqual(got.who, "none")
        got = parser.parse_args(["publish", "v0.21.0", "--public", "x", "--all", "--wait", "3"])
        self.assertEqual((got.who, got.wait), ("all", 3))

    def test_publish_wait_defaults_to_15(self):
        got = release.build_parser().parse_args(["publish", "v0.21.0", "--public", "x", "--none"])
        self.assertEqual(got.wait, 15)


if __name__ == "__main__":
    unittest.main()
