"""_lib/skeleton（升級打包 要做的事 3、驗收 9）：骨架檔的指紋、skeleton.json 記錄、換版時的對帳。
沒改過換新、改過問、沒有紀錄對 config/skeleton_history.json；--keep／--replace。skeleton/ 與歷史都用假的，不碰真的骨架。"""
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests._guard_fixture import SCRIPTS  # noqa: F401  加 sys.path
from kb._lib import skeleton, turn  # noqa: E402


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kbskel-"))
        self.V = self.tmp / "vault"
        (self.V / ".system").mkdir(parents=True)
        self.root = self.tmp / "skeleton"
        (self.root / ".claude").mkdir(parents=True)
        (self.root / "案子").mkdir()
        (self.root / "案子" / ".gitkeep").write_text("", encoding="utf-8")
        self.put_skeleton("CLAUDE.md", "新版身分\n")
        self.put_skeleton(".claude/settings.json", "{}\n")
        self.history = {}
        self.patches = [mock.patch.object(skeleton, "skeleton_root", return_value=self.root),
                        mock.patch.object(skeleton, "history", side_effect=lambda: self.history),
                        mock.patch.object(skeleton, "plugin_version", return_value="0.21.0")]
        for p in self.patches:
            p.start()
        self.turn = turn.start(self.V, None, "升級")["turn"]

    def tearDown(self):
        for p in self.patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put_skeleton(self, rel, text):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")

    def put_vault(self, rel, text):
        p = self.V / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")

    def vault_text(self, rel):
        return (self.V / rel).read_text(encoding="utf-8")

    def skeleton_json(self):
        return json.loads((self.V / ".system" / "skeleton.json").read_text(encoding="utf-8"))


class Hashes(Base):
    def test_files_skip_gitkeep_and_hashes_are_sha256_of_bytes(self):
        self.assertEqual(skeleton.files(), [".claude/settings.json", "CLAUDE.md"])
        self.assertEqual(skeleton.hashes(), {"CLAUDE.md": sha("新版身分\n"), ".claude/settings.json": sha("{}\n")})

    def test_known_checks_every_version_in_history(self):
        self.history = {"0.20.0": {"CLAUDE.md": sha("舊版\n")}, "0.20.1": {"CLAUDE.md": sha("舊版二\n")}}
        self.assertTrue(skeleton.known("CLAUDE.md", sha("舊版\n")))
        self.assertTrue(skeleton.known("CLAUDE.md", sha("舊版二\n")))
        self.assertFalse(skeleton.known("CLAUDE.md", sha("她改過\n")))
        self.assertFalse(skeleton.known(".claude/settings.json", sha("舊版\n")))


class Record(Base):
    def test_recorded_none_without_file_or_garbage(self):
        self.assertIsNone(skeleton.recorded(self.V))
        (self.V / ".system" / "skeleton.json").write_text("不是 json", encoding="utf-8")
        self.assertIsNone(skeleton.recorded(self.V))

    def test_record_all_then_read(self):
        skeleton.record(self.V)
        data = self.skeleton_json()
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["version"], "0.21.0")
        self.assertEqual(data["files"], skeleton.hashes())
        self.assertEqual(skeleton.recorded(self.V), data)

    def test_record_some_merges_and_keeps_others(self):
        (self.V / ".system" / "skeleton.json").write_text(json.dumps(
            {"schema_version": 1, "version": "0.20.0", "files": {"CLAUDE.md": "舊指紋"}}), encoding="utf-8")
        skeleton.record(self.V, [".claude/settings.json"])
        data = self.skeleton_json()
        self.assertEqual(data["files"], {"CLAUDE.md": "舊指紋", ".claude/settings.json": sha("{}\n")})
        self.assertEqual(data["version"], "0.21.0")


class Reconcile(Base):
    def test_untouched_file_is_replaced_with_new_version_and_backed_up(self):
        """知識庫裡的跟 skeleton.json 記的一樣（她沒改過），新版改了 → 直接換新。"""
        self.put_vault("CLAUDE.md", "舊版身分\n")
        self.put_vault(".claude/settings.json", "{}\n")
        (self.V / ".system" / "skeleton.json").write_text(json.dumps(
            {"schema_version": 1, "version": "0.20.0",
             "files": {"CLAUDE.md": sha("舊版身分\n"), ".claude/settings.json": sha("{}\n")}}), encoding="utf-8")
        got = skeleton.reconcile(self.V, self.turn)
        self.assertEqual(got["replaced"], ["CLAUDE.md"])
        self.assertEqual(got["ask"], [])
        self.assertEqual(self.vault_text("CLAUDE.md"), "新版身分\n")
        saved = self.V / ".system" / "versions" / self.turn / "files" / "CLAUDE.md"
        self.assertEqual(saved.read_text(encoding="utf-8"), "舊版身分\n")
        self.assertEqual(self.skeleton_json()["files"]["CLAUDE.md"], sha("新版身分\n"))

    def test_edited_file_is_asked_and_not_touched(self):
        """她改過 → skeleton_ask 有它、檔沒動、記錄沒動。"""
        self.put_vault("CLAUDE.md", "她加了一行\n")
        self.put_vault(".claude/settings.json", "{}\n")
        (self.V / ".system" / "skeleton.json").write_text(json.dumps(
            {"schema_version": 1, "version": "0.20.0",
             "files": {"CLAUDE.md": sha("舊版身分\n"), ".claude/settings.json": sha("{}\n")}}), encoding="utf-8")
        got = skeleton.reconcile(self.V, self.turn)
        self.assertEqual(got["ask"], ["CLAUDE.md"])
        self.assertEqual(got["replaced"], [])
        self.assertEqual(self.vault_text("CLAUDE.md"), "她加了一行\n")
        self.assertEqual(self.skeleton_json()["files"]["CLAUDE.md"], sha("舊版身分\n"))

    def test_file_the_new_version_did_not_change_is_not_asked(self):
        """她改過、但新版這個檔沒改（記的指紋等於新版的）→ 不問、不動。"""
        self.put_vault("CLAUDE.md", "她加了一行\n")
        self.put_vault(".claude/settings.json", "{}\n")
        (self.V / ".system" / "skeleton.json").write_text(json.dumps(
            {"schema_version": 1, "version": "0.20.0",
             "files": {"CLAUDE.md": sha("新版身分\n"), ".claude/settings.json": sha("{}\n")}}), encoding="utf-8")
        got = skeleton.reconcile(self.V, self.turn)
        self.assertEqual((got["ask"], got["replaced"]), ([], []))
        self.assertEqual(self.vault_text("CLAUDE.md"), "她加了一行\n")

    def test_up_to_date_file_just_updates_record(self):
        self.put_vault("CLAUDE.md", "新版身分\n")
        self.put_vault(".claude/settings.json", "{}\n")
        got = skeleton.reconcile(self.V, self.turn)
        self.assertEqual((got["ask"], got["replaced"]), ([], []))
        self.assertEqual(self.skeleton_json()["files"], skeleton.hashes())

    def test_no_record_and_content_in_history_counts_as_untouched(self):
        """沒有 skeleton.json 的舊知識庫：跟歷史裡任何一版對得上 → 當她沒改過、直接換。"""
        self.history = {"0.19.0": {"CLAUDE.md": sha("更舊的身分\n")}}
        self.put_vault("CLAUDE.md", "更舊的身分\n")
        self.put_vault(".claude/settings.json", "{}\n")
        got = skeleton.reconcile(self.V, self.turn)
        self.assertEqual(got["replaced"], ["CLAUDE.md"])
        self.assertEqual(self.vault_text("CLAUDE.md"), "新版身分\n")

    def test_no_record_and_unknown_content_is_asked(self):
        self.history = {"0.19.0": {"CLAUDE.md": sha("更舊的身分\n")}}
        self.put_vault("CLAUDE.md", "她自己寫的\n")
        self.put_vault(".claude/settings.json", "{}\n")
        got = skeleton.reconcile(self.V, self.turn)
        self.assertEqual(got["ask"], ["CLAUDE.md"])
        self.assertEqual(self.vault_text("CLAUDE.md"), "她自己寫的\n")

    def test_no_record_edited_but_previous_version_same_as_new_is_not_asked(self):
        """沒有紀錄、她改過，但她那一版（from_version）的骨架指紋跟新版一樣 = 新版沒改這個檔 → 不問。"""
        self.history = {"0.20.0": {"CLAUDE.md": sha("新版身分\n")}}
        self.put_vault("CLAUDE.md", "她自己寫的\n")
        self.put_vault(".claude/settings.json", "{}\n")
        got = skeleton.reconcile(self.V, self.turn, from_version="0.20.0")
        self.assertEqual((got["ask"], got["replaced"]), ([], []))

    def test_missing_file_is_created_and_recorded(self):
        got = skeleton.reconcile(self.V, self.turn)
        self.assertEqual(sorted(got["created"]), [".claude/settings.json", "CLAUDE.md"])
        self.assertEqual(self.vault_text("CLAUDE.md"), "新版身分\n")
        self.assertEqual(self.skeleton_json()["files"], skeleton.hashes())


class KeepReplace(Base):
    def setUp(self):
        super().setUp()
        self.put_vault("CLAUDE.md", "她加了一行\n")
        self.put_vault(".claude/settings.json", "{}\n")
        (self.V / ".system" / "skeleton.json").write_text(json.dumps(
            {"schema_version": 1, "version": "0.20.0",
             "files": {"CLAUDE.md": sha("舊版身分\n"), ".claude/settings.json": sha("{}\n")}}), encoding="utf-8")

    def test_keep_leaves_file_and_updates_record_so_it_is_not_asked_again(self):
        skeleton.keep(self.V, "CLAUDE.md")
        self.assertEqual(self.vault_text("CLAUDE.md"), "她加了一行\n")
        self.assertEqual(self.skeleton_json()["files"]["CLAUDE.md"], sha("新版身分\n"))
        got = skeleton.reconcile(self.V, self.turn)
        self.assertEqual((got["ask"], got["replaced"]), ([], []))

    def test_replace_backs_up_hers_then_writes_new(self):
        skeleton.replace(self.V, "CLAUDE.md", self.turn)
        self.assertEqual(self.vault_text("CLAUDE.md"), "新版身分\n")
        saved = self.V / ".system" / "versions" / self.turn / "files" / "CLAUDE.md"
        self.assertEqual(saved.read_text(encoding="utf-8"), "她加了一行\n")
        self.assertEqual(self.skeleton_json()["files"]["CLAUDE.md"], sha("新版身分\n"))

    def test_only_skeleton_files_are_accepted(self):
        for rel in ("../outside.md", "系統/客戶設定檔.md", ".system/profile.json", "C:/x", "CLAUDE.md/../CLAUDE.md"):
            with self.subTest(rel=rel), self.assertRaises(skeleton.Refused):
                skeleton.keep(self.V, rel)
            with self.subTest(rel=rel, op="replace"), self.assertRaises(skeleton.Refused):
                skeleton.replace(self.V, rel, self.turn)


if __name__ == "__main__":
    unittest.main()
