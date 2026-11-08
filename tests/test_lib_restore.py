"""_lib/restore（備份還原與換電腦 要做的事 2，D-205、D-211）：演練 check、動手 apply（先拍快照、全部移回）、空資料夾、hidden 重清。"""
import json
import shutil
import unittest
from pathlib import Path
from unittest import mock

from tests import _backup
from kb._lib import backup, restore, vault as vault_lib  # noqa: E402

SYSTEM = ".system"


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def statement(sid, text):
    return {"id": sid, "text": text, "entities": [], "date": "2026-10-01", "turn": "t", "status": "active",
            "replaced_by": None}


def file_card(V, short, title):
    p = V / "檔案索引" / "客戶案件" / f"{title}-{short}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n編號: f-{short}\n標題: {title}\n---\n\n# {title}\n", encoding="utf-8")
    return p


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _backup.make_vault()
        self.B = self.tmp / "備份"
        self.D = self.tmp / "空夾"
        self.D.mkdir()
        write_json(self.V / SYSTEM / "statements.json", {"schema_version": 1, "statements": [statement("s-0001", "舊口述")]})
        write_json(self.V / SYSTEM / "agenda.json", {"schema_version": 1, "items": []})
        (self.V / SYSTEM / "turns").mkdir()
        (self.V / SYSTEM / "turns" / "current.json").write_text("{}", encoding="utf-8")
        (self.V / SYSTEM / "ledger.tsv").write_text("before\n", encoding="utf-8")
        self.zip = _backup.make_zip(self.V, self.B)
        self.before = _backup.tree(self.V)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def change_after_backup(self):
        """備份之後：多一條口述、一條日程、改一張綜合卡、多一張檔案卡、多一個成品、日誌多一個回合。"""
        write_json(self.V / SYSTEM / "statements.json", {"schema_version": 1, "statements": [
            statement("s-0001", "舊口述"), statement("s-0002", "信義王的設計師換成小陳")]})
        write_json(self.V / SYSTEM / "agenda.json", {"schema_version": 1, "items": [
            {"id": "a-0001", "kind": "deadline", "date": "2026-11-01", "text": "交報價", "status": "open", "entities": []}]})
        (self.V / "案子" / "信義王" / "信義王.md").write_text("# 信義王\n\n新寫的內容。\n", encoding="utf-8")
        file_card(self.V, "9999", "大安陳報價 v3")
        (self.V / "暫存區" / "新報告.docx").write_bytes(b"docx")
        (self.V / SYSTEM / "turns" / "current.json").write_text('{"turn": "now"}', encoding="utf-8")
        (self.V / SYSTEM / "ledger.tsv").write_text("after\n", encoding="utf-8")
        j = self.V / SYSTEM / "journal"
        j.mkdir(exist_ok=True)
        (j / "2026-10.jsonl").write_text(json.dumps({"turn": "20261020-100000-abcd", "kind": "turn"}) + "\n", encoding="utf-8")

    def refused(self, fn, *a, **kw):
        with self.assertRaises(backup.Refused) as cm:
            fn(*a, **kw)
        return str(cm.exception)


class Check(Base):
    def test_counts_and_examples_without_ids(self):
        self.change_after_backup()
        before = _backup.tree(self.V)
        got = restore.check(self.V, str(self.zip))
        self.assertEqual(_backup.tree(self.V), before, "check 不動任何檔")
        self.assertIsNone(got["refuse"])
        self.assertEqual(got["kind"], "backup")
        self.assertEqual(got["machine"], "LIN-PC")
        self.assertEqual(got["lose"]["statements"], 1)
        self.assertEqual(got["lose"]["agenda"], 1)
        self.assertEqual(got["lose"]["cards"], 1)
        self.assertEqual(got["lose"]["synthesis"], 1)
        self.assertEqual(got["lose"]["outputs"], 1)
        self.assertEqual(got["lose"]["journal_turns"], 1)
        for key in ("statements", "rulings", "agenda", "findings", "entities", "cards", "synthesis", "outputs"):
            self.assertEqual(got["back"][key], 0, key)
        self.assertEqual(got["examples"]["statements"], ["信義王的設計師換成小陳"])
        self.assertEqual(got["examples"]["cards"], ["大安陳報價 v3"])
        self.assertEqual(got["examples"]["synthesis"], ["信義王"])
        self.assertEqual(got["hidden_reapply"], [])
        self.assertIsNone(got["build_step"])

    def test_skeleton_file_she_changed_after_the_backup_is_listed(self):
        """桌面版確認 B-5：CLAUDE.md 這類骨架檔備份後改過，演練要講會變回那份的樣子。"""
        (self.V / "CLAUDE.md").write_text("原本的說明\n", encoding="utf-8")
        z = _backup.make_zip(self.V, self.B, "vault備份 2026-10-03.zip")
        (self.V / "CLAUDE.md").write_text("原本的說明\n我習慣先講結論\n", encoding="utf-8")
        got = restore.check(self.V, str(z))
        self.assertEqual(got["skeleton_changed"], ["CLAUDE.md"])
        self.assertIn("CLAUDE.md", "\n".join(restore.lines(got)))
        (self.V / "CLAUDE.md").write_text("原本的說明\n", encoding="utf-8")
        self.assertEqual(restore.check(self.V, str(z))["skeleton_changed"], [])

    def test_back_side_counts_what_comes_back(self):
        file_card(self.V, "7777", "會回來的卡")
        z = _backup.make_zip(self.V, self.B, "vault備份 2026-10-02.zip")
        (self.V / "檔案索引" / "客戶案件" / "會回來的卡-7777.md").unlink()
        got = restore.check(self.V, str(z))
        self.assertEqual(got["back"]["cards"], 1)
        self.assertEqual(got["lose"]["cards"], 0)

    def test_lines_are_plain_without_ids(self):
        self.change_after_backup()
        lines = restore.lines(restore.check(self.V, str(self.zip)))
        self.assertTrue(lines[0].startswith("會回到 ") and lines[0].endswith(" 的樣子"), lines[0])
        self.assertEqual(lines[-1], "你原本的資料夾不會動")
        text = "\n".join(lines)
        self.assertIn("信義王的設計師換成小陳", text)
        for bad in ("s-0002", "a-0001", "f-9999"):
            self.assertNotIn(bad, text)

    def test_hidden_reapply_and_build_step(self):
        src = json.loads((self.V / SYSTEM / "sources.json").read_text(encoding="utf-8"))
        src["sources"][0]["excludes"] = [{"spec": "薪資", "kind": "hidden", "reason": "x", "purge": "2026-10-05"}]
        write_json(self.V / SYSTEM / "sources.json", src)
        got = restore.check(self.V, str(self.zip))
        self.assertEqual(got["hidden_reapply"], ["客戶案件/薪資"])

    def test_build_step_reported_when_not_done(self):
        write_json(self.V / SYSTEM / "build.json", {"schema_version": 1, "step": "cards"})
        z = _backup.make_zip(self.V, self.B, "vault備份 2026-10-03.zip")
        self.assertEqual(restore.check(self.V, str(z))["build_step"], "cards")

    def test_find_by_snapshot_name_and_missing(self):
        snap = backup.snapshot(self.V, "restore")
        self.assertIsNone(restore.check(self.V, snap.name)["refuse"])
        self.assertEqual(self.refused(restore.find_source, "不存在.zip", self.V, self.V), "找不到這份：不存在.zip")

    def test_refusals_are_reported_as_sentences(self):
        junk = self.B / "壞.zip"
        junk.write_bytes(b"x")
        self.assertTrue(restore.check(self.V, str(junk))["refuse"].startswith("這份備份壞了（"))
        _backup.put_batch(self.V)
        self.assertEqual(restore.check(self.V, str(self.zip))["refuse"], "背景整理還在跑，先停掉再還原")

    def test_not_empty_not_vault_refused(self):
        other = self.tmp / "別的夾"
        other.mkdir()
        (other / "a.txt").write_text("x", encoding="utf-8")
        got = restore.check(other, str(self.zip))
        self.assertEqual(got["refuse"], "這個資料夾不是空的，也不是知識庫；換一個空資料夾")

    def test_empty_folder_everything_comes_back(self):
        got = restore.check(self.D, str(self.zip))
        self.assertIsNone(got["refuse"])
        self.assertEqual(got["lose"]["statements"], 0)
        self.assertEqual(got["back"]["statements"], 1)
        self.assertFalse((self.D / SYSTEM).exists())


class Apply(Base):
    def test_restores_data_and_keeps_preserved_things(self):
        self.change_after_backup()
        (self.V / SYSTEM / "vault.json").write_text(json.dumps(
            {"schema_version": 1, "vault_id": vault_lib.vault_id(self.V)}), encoding="utf-8")
        got = restore.apply(self.V, str(self.zip))
        data = json.loads((self.V / SYSTEM / "statements.json").read_text(encoding="utf-8"))
        self.assertEqual([s["id"] for s in data["statements"]], ["s-0001"])
        self.assertEqual(json.loads((self.V / SYSTEM / "agenda.json").read_text(encoding="utf-8"))["items"], [])
        self.assertEqual(_backup.tree(self.V)["案子/信義王/信義王.md"], self.before["案子/信義王/信義王.md"])
        self.assertFalse((self.V / "檔案索引" / "客戶案件" / "大安陳報價 v3-9999.md").exists())
        self.assertFalse((self.V / "暫存區" / "新報告.docx").exists())
        self.assertEqual((self.V / SYSTEM / "ledger.tsv").read_text(encoding="utf-8"), "after\n")
        self.assertIn("now", (self.V / SYSTEM / "turns" / "current.json").read_text(encoding="utf-8"))
        self.assertEqual(vault_lib.vault_id(self.V), backup.read_meta(self.zip)["vault_id"])
        snaps = list((self.V / SYSTEM / "snapshots").glob("快照*（還原前）.zip"))
        self.assertEqual(len(snaps), 1)
        self.assertEqual(backup.read_meta(snaps[0])["reason"], "restore")
        self.assertRegex(got["sentence"], r"^已還原到 \d\d-\d\d \d\d:\d\d 的備份；說「剛剛的還原不要了」可以回到還原前。"
                                           r"還原後有 \d+ 份要重新整理。$")
        self.assertFalse(list((self.V / SYSTEM / "temp").glob("restore-*")))

    def test_restored_state_equals_backup_time_except_preserved(self):
        self.change_after_backup()
        restore.apply(self.V, str(self.zip))
        skip = (".system/turns", ".system/snapshots", ".system/temp", ".system/ledger.tsv", ".system/env.json",
                ".system/journal", ".system/vault.json", ".system/revert.lock")
        now = {k: v for k, v in _backup.tree(self.V).items() if not k.startswith(skip)}
        was = {k: v for k, v in self.before.items() if not k.startswith(skip)}
        extra = {k for k in now if k not in was}
        missing = {k for k in was if k not in now}
        self.assertEqual(missing, set(), missing)
        self.assertFalse([k for k in extra if k not in (".gitignore", ".gitattributes") and not k.startswith((".system/", "系統/", ".obsidian/"))], extra)  # kb init 補的骨架（Obsidian 外掛每次 init 都放，#22 D-260）

    def test_journal_gets_a_restore_segment_at_the_end(self):
        restore.apply(self.V, str(self.zip))
        rows = []
        for f in sorted((self.V / SYSTEM / "journal").glob("*.jsonl")):
            rows += [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertTrue(rows)
        self.assertIn("還原", rows[-1].get("note", ""))

    def test_undo_restore_from_latest_snapshot(self):
        self.change_after_backup()
        restore.apply(self.V, str(self.zip))
        latest = restore.latest_snapshot(self.V)
        self.assertIsNotNone(latest)
        restore.apply(self.V, latest.name)
        data = json.loads((self.V / SYSTEM / "statements.json").read_text(encoding="utf-8"))
        self.assertIn("s-0002", [s["id"] for s in data["statements"]])
        self.assertEqual(len(list((self.V / SYSTEM / "snapshots").glob("快照*.zip"))), 2)

    def test_failure_moves_everything_back(self):
        self.change_after_backup()
        before = _backup.tree(self.V, skip=(".system/snapshots", ".system/temp"))
        calls = {"n": 0}
        real = restore._rename

        def flaky(src, dst):
            if ".system/temp" not in str(dst).replace("\\", "/"):  # 「移到位」這一段
                calls["n"] += 1
                if calls["n"] == 3:
                    raise PermissionError(13, "拒絕存取", str(dst))
            return real(src, dst)
        with mock.patch.object(restore, "_rename", flaky):
            msg = self.refused(restore.apply, self.V, str(self.zip))
        self.assertTrue(msg.startswith("有檔案開著（") and msg.endswith("），關掉再說一次；什麼都沒動"), msg)
        self.assertEqual(_backup.tree(self.V, skip=(".system/snapshots", ".system/temp")), before)
        self.assertEqual([p.name for p in (self.V / SYSTEM / "temp").iterdir()], ["暫存.txt"])
        self.assertFalse((self.V / SYSTEM / "revert.lock").exists())

    def test_refusals_change_nothing(self):
        before = _backup.tree(self.V)
        for make in ("nometa", "slip", "newer"):
            p = self.B / f"{make}.zip"
            if make == "nometa":
                import zipfile
                with zipfile.ZipFile(p, "w") as z:
                    z.writestr("x.txt", "x")
            elif make == "slip":
                import zipfile
                with zipfile.ZipFile(p, "w") as z:
                    z.writestr("wiki-with-willy-backup.json", json.dumps(
                        {"schema_version": 1, "kind": "backup", "plugin_version": "0.1.0", "vault_id": "kb-00000000"}))
                    z.writestr("../evil.txt", "x")
            else:
                p = _backup.make_zip(self.V, self.B, "newer.zip", plugin_version="99.0.0")
            with self.assertRaises(backup.Refused):
                restore.apply(self.V, str(p))
        self.assertEqual(_backup.tree(self.V), before)
        self.assertFalse((self.tmp / "evil.txt").exists())

    def test_batch_running_and_lock_busy(self):
        _backup.put_batch(self.V)
        self.assertEqual(self.refused(restore.apply, self.V, str(self.zip)), "背景整理還在跑，先停掉再還原")
        _backup.put_batch(self.V, created_min_ago=5, seen_min_ago=15)
        from kb._lib import io as kio
        with kio.FileLock(self.V / SYSTEM / "revert"):
            self.assertEqual(self.refused(restore.apply, self.V, str(self.zip)), "另一個備份、還原或退回正在跑，等它做完")

    def test_empty_folder_becomes_vault_with_backups_vault_json(self):
        got = restore.apply(self.D, str(self.zip))
        self.assertTrue((self.D / SYSTEM / "sources.json").is_file())
        self.assertEqual(vault_lib.vault_id(self.D), backup.read_meta(self.zip)["vault_id"])
        self.assertTrue((self.D / "案子" / "空夾").is_dir())
        self.assertEqual(json.loads((self.D / SYSTEM / "statements.json").read_text(encoding="utf-8"))["statements"][0]["id"],
                         "s-0001")
        self.assertIsNone(got["snapshot"])
        self.assertFalse(list((self.D / SYSTEM / "temp").glob("restore-*")))

    def test_current_hidden_exclude_is_kept_and_purged_again(self):
        src = json.loads((self.V / SYSTEM / "sources.json").read_text(encoding="utf-8"))
        src["sources"][0]["excludes"] = [{"spec": "薪資", "kind": "hidden", "reason": "x", "purge": "2026-10-05"}]
        write_json(self.V / SYSTEM / "sources.json", src)
        got = restore.apply(self.V, str(self.zip))
        after = json.loads((self.V / SYSTEM / "sources.json").read_text(encoding="utf-8"))
        excl = after["sources"][0]["excludes"]
        self.assertEqual([(e["spec"], e["kind"]) for e in excl], [("薪資", "hidden")])
        self.assertNotEqual(excl[0].get("purge"), "pending")
        self.assertEqual(got["hidden_reapplied"], ["客戶案件/薪資"])


if __name__ == "__main__":
    unittest.main()
