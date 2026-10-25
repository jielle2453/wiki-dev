"""_lib/moved（備份還原與換電腦 要做的事 4，D-206、D-208）：state（same｜moved｜new_machine｜first）、check、apply。"""
import json
import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

from tests import _backup, _cards
from kb._lib import cards, env, moved, turn, unlock, vault as vault_lib  # noqa: E402
from kb._lib import sources as sources_lib  # noqa: E402


def posix(p):
    return Path(os.path.realpath(str(p))).as_posix()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _cards.make_card_vault()
        item = cards.todo(self.V, sources_lib.load(self.V))["new"]
        item = next(i for i in item if i["id"] == _cards.entry_of(self.V, _cards.MEETING)["id"])
        self.card = _cards.write_card(self.V, item, "大安陳會議一")
        vault_lib.ensure_vault_id(self.V)
        env.set_vault_path(self.V, posix(self.V))
        self.old_unlock = unlock.BACKEND
        unlock.BACKEND = unlock.MemoryBackend()

    def tearDown(self):
        unlock.BACKEND = self.old_unlock
        shutil.rmtree(self.tmp, ignore_errors=True)

    def sources_json(self, vault):
        return json.loads((vault / ".system" / "sources.json").read_text(encoding="utf-8"))

    def move_together(self):
        """知識庫與 raw 一起搬到另一個位置（舊的刪掉）；回新知識庫。"""
        base = self.tmp / "D槽"
        base.mkdir()
        shutil.copytree(self.V, base / "知識庫")
        shutil.copytree(self.raw, base / "raw")
        shutil.rmtree(self.V)
        shutil.rmtree(self.raw)
        return base / "知識庫"

    def move_vault_only(self, keep_old=False):
        """只搬知識庫（raw 留在舊位置）；keep_old 是複製。"""
        base = self.tmp / "D槽"
        base.mkdir()
        shutil.copytree(self.V, base / "知識庫")
        if not keep_old:
            shutil.rmtree(self.V)
        return base / "知識庫"


class State(Base):
    def test_first_when_nothing_recorded(self):
        (self.V / ".system" / "env.json").unlink()
        got = moved.state(self.V)
        self.assertEqual(got["state"], "first")
        self.assertIsNone(got["from"])
        self.assertEqual(got["to"], posix(self.V))
        self.assertFalse((self.V / ".system" / "env.json").exists(), "state 只讀")

    def test_same_moved_and_new_machine(self):
        self.assertEqual(moved.state(self.V)["state"], "same")
        NV = self.move_vault_only()
        got = moved.state(NV)
        self.assertEqual((got["state"], got["from"]), ("moved", posix(self.V)))
        data = json.loads((NV / ".system" / "env.json").read_text(encoding="utf-8"))
        data["machines"] = {"OTHER-PC": {"vault_path": "D:/lin/知識庫"}}
        (NV / ".system" / "env.json").write_text(json.dumps(data), encoding="utf-8")
        got = moved.state(NV)
        self.assertEqual((got["state"], got["from"]), ("new_machine", "D:/lin/知識庫"))

    def test_other_machine_without_path_still_new_machine(self):
        (self.V / ".system" / "env.json").write_text(json.dumps(
            {"schema_version": 1, "machines": {"OTHER-PC": {"missing_sources_reported": {}}}}), encoding="utf-8")
        self.assertEqual(moved.state(self.V)["state"], "new_machine")


class Check(Base):
    def test_same_and_first_report_nothing_and_write_nothing(self):
        before = _backup.tree(self.V)
        got = moved.check(self.V)
        self.assertEqual(got["state"], "same")
        for key in ("sources_rewritten", "missing_sources", "env", "passwords_missing"):
            self.assertEqual(got[key], [], key)
        self.assertEqual((got["cards_relinked"], got["old_copy"]), (0, None))
        self.assertEqual(_backup.tree(self.V), before)

    def test_moved_together_relinks_cards_only(self):
        NV = self.move_together()
        before = _backup.tree(NV)
        got = moved.check(NV)
        self.assertEqual(got["state"], "moved")
        self.assertEqual(got["from"], posix(self.V))
        self.assertEqual(got["to"], posix(NV))
        self.assertEqual(got["sources_rewritten"], [])
        self.assertEqual(got["cards_relinked"], 1)
        self.assertEqual(got["missing_sources"], [])
        self.assertEqual(_backup.tree(NV), before, "--check 不動任何檔")

    def test_vault_moved_alone_rewrites_relative_sources(self):
        NV = self.move_vault_only()
        got = moved.check(NV)
        self.assertEqual(sorted(got["sources_rewritten"]), sorted(["公司行政", "客戶案件", "報價與合約"]))
        self.assertEqual(got["missing_sources"], [])
        self.assertEqual(self.sources_json(NV)["sources"][0]["spec"], "../raw/客戶案件", "check 不寫")

    def test_missing_source_listed(self):
        NV = self.move_vault_only()
        raw = self.sources_json(NV)
        raw["sources"][0]["spec"] = "../不存在/客戶案件"
        (NV / ".system" / "sources.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        got = moved.check(NV)
        self.assertEqual(got["missing_sources"], ["客戶案件"])
        self.assertNotIn("客戶案件", got["sources_rewritten"])

    def test_old_copy_only_when_same_vault_id(self):
        NV = self.move_vault_only(keep_old=True)
        self.assertEqual(moved.check(NV)["old_copy"], posix(self.V))
        (self.V / ".system" / "vault.json").write_text(json.dumps(
            {"schema_version": 1, "vault_id": "kb-ffffffff"}), encoding="utf-8")
        self.assertIsNone(moved.check(NV)["old_copy"])

    def test_new_machine_lists_env_and_missing_passwords(self):
        data = {"schema_version": 1, "machines": {"OTHER-PC": {"vault_path": "D:/lin/知識庫"}}}
        (self.V / ".system" / "env.json").write_text(json.dumps(data), encoding="utf-8")
        (self.V / ".system" / "unlock.json").write_text(json.dumps({
            "schema_version": 1, "kinds": [{"label": "保險單", "credential": "PDF 密碼/保險單", "examples": []},
                                           {"label": "門禁", "credential": "PDF 密碼/工地大門", "examples": []}],
            "opened": []}), encoding="utf-8")
        unlock.save(self.V, "PDF 密碼", "保險單", "x-secret-value")
        items = [{"key": "python", "level": "ok", "text": "Python 3.12"},
                 {"key": "pdf", "level": "fail", "text": "PDF 元件沒裝", "fix": "kb office setup"}]
        with mock.patch("kb._lib.build.env_items", return_value=items):
            got = moved.check(self.V)
        self.assertEqual(got["state"], "new_machine")
        self.assertEqual([i["key"] for i in got["env"]], ["pdf"])
        self.assertEqual(got["passwords_missing"], ["工地大門"])

    def test_old_vault_without_id_does_not_crash(self):
        NV = self.move_vault_only()
        (NV / ".system" / "vault.json").unlink(missing_ok=True)
        self.assertEqual(moved.check(NV)["state"], "moved")


class Apply(Base):
    def test_together_relinks_cards_and_records_path(self):
        NV = self.move_together()
        t = turn.start(NV, None, "補連結")
        got = moved.apply(NV, t["turn"])
        self.assertEqual(got["cards_relinked"], 1)
        self.assertEqual(env.vault_path(NV), posix(NV))
        self.assertEqual(moved.state(NV)["state"], "same")
        card = next((NV / "檔案索引").rglob("大安陳會議一-*.md"))
        link = cards.parse_front(card.read_text(encoding="utf-8"))["開原檔"]
        entry = _cards.entry_of(NV, _cards.MEETING)
        self.assertEqual(link, cards.entry_link(NV, sources_lib.load(NV), entry))
        self.assertEqual(cards.todo(NV, sources_lib.load(NV))["moved"], [])

    def test_vault_alone_rewrites_sources_and_backs_up_into_turn(self):
        NV = self.move_vault_only()
        t = turn.start(NV, None, "補連結")
        got = moved.apply(NV, t["turn"])
        self.assertEqual(sorted(got["sources_rewritten"]), sorted(["公司行政", "客戶案件", "報價與合約"]))
        specs = [s["spec"] for s in self.sources_json(NV)["sources"]]
        self.assertEqual(specs, ["../../raw/客戶案件", "../../raw/報價與合約", "../../raw/公司行政"])
        resolved = [e["root"] for e in sources_lib.load(NV).entries]
        for root in resolved:
            self.assertTrue(Path(root).is_dir(), root)
        paths = {e["path"] for e in turn.entries(NV, t["turn"])}
        self.assertIn(".system/sources.json", paths)

    def test_first_only_records_the_path(self):
        (self.V / ".system" / "env.json").unlink()
        before = _backup.tree(self.V, skip=(".system/env.json",))
        got = moved.apply(self.V, turn.start(self.V, None, "x")["turn"])
        self.assertEqual(got["state"], "first")
        self.assertEqual(env.vault_path(self.V), posix(self.V))
        after = _backup.tree(self.V, skip=(".system/env.json", ".system/versions", ".system/turns"))
        self.assertEqual(after, {k: v for k, v in before.items() if not k.startswith((".system/versions", ".system/turns"))})

    def test_new_machine_writes_path_and_keeps_other_machines(self):
        data = {"schema_version": 1, "machines": {"OTHER-PC": {"vault_path": "D:/lin/知識庫"}}}
        (self.V / ".system" / "env.json").write_text(json.dumps(data), encoding="utf-8")
        with mock.patch("kb._lib.build.env_items", return_value=[]):
            moved.apply(self.V, turn.start(self.V, None, "x")["turn"])
        got = json.loads((self.V / ".system" / "env.json").read_text(encoding="utf-8"))
        self.assertEqual(got["machines"]["OTHER-PC"]["vault_path"], "D:/lin/知識庫")
        self.assertEqual(got["machines"][env.machine_name()]["vault_path"], posix(self.V))
        self.assertTrue(vault_lib.vault_id(self.V))


if __name__ == "__main__":
    unittest.main()
