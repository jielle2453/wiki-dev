"""_lib/migrate（升級打包 要做的事 2、驗收 8）：狀態檔遷移表與卡檔頭遷移表。
schema 比現在舊的狀態檔照自己的 load 讀、照自己的寫法寫回（寫前備進回合，versions revert 退得回）；卡檔頭目前沒有要遷的（表是空的）。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests._guard_fixture import FIXTURES
from tests import _entities
from kb._lib import entities, inventory, migrate, profile, turn  # noqa: E402

PROFILE_FIX = FIXTURES / "profile"
INV_FIX = FIXTURES / "inventory"


def read(V, rel):
    return json.loads((Path(V) / rel).read_text(encoding="utf-8"))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kbmig-")).resolve()
        self.V = self.tmp / "vault"
        (self.V / ".system").mkdir(parents=True)
        (self.V / "系統").mkdir()
        self.turn = turn.start(self.V, None, "升級")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put_profile_v1(self):
        shutil.copy2(PROFILE_FIX / "schema1.json", self.V / ".system" / "profile.json")
        shutil.copy2(PROFILE_FIX / "schema1.md", self.V / "系統" / "客戶設定檔.md")

    def saved(self, rel):
        return self.V / ".system" / "versions" / self.turn / "files" / rel


class Table(Base):
    def test_registered_files_are_profile_inventory_entities_pending(self):
        """lint 題：pending.json schema 1 → 2 加一列（D-226）。"""
        self.assertEqual([m.rel for m in migrate.STATE_FILES],
                         [".system/profile.json", ".system/inventory.json", ".system/entities.json", ".system/pending.json"])

    def test_card_header_table_is_empty_for_now(self):
        self.assertEqual(migrate.CARD_HEADER_MIGRATIONS, [])


class Pending(Base):
    def test_nothing_pending_when_no_files(self):
        self.assertEqual(migrate.pending(self.V), [])

    def test_old_schemas_are_listed_with_from_and_to(self):
        self.put_profile_v1()
        shutil.copy2(INV_FIX / "inventory_v1.json", self.V / ".system" / "inventory.json")
        shutil.copy2(_entities.FIX / "entities.json", self.V / ".system" / "entities.json")
        got = {p["rel"]: (p["from"], p["to"]) for p in migrate.pending(self.V)}
        self.assertEqual(got, {".system/profile.json": (1, profile.SCHEMA_VERSION),
                               ".system/inventory.json": (1, inventory.SCHEMA_VERSION),
                               ".system/entities.json": (1, entities.SCHEMA_VERSION)})

    def test_current_schema_is_not_pending(self):
        (self.V / ".system" / "inventory.json").write_text(json.dumps(inventory.EMPTY), encoding="utf-8")
        self.assertEqual(migrate.pending(self.V), [])

    def test_unreadable_file_is_not_pending(self):
        (self.V / ".system" / "inventory.json").write_text("不是 json", encoding="utf-8")
        self.assertEqual(migrate.pending(self.V), [])


class ApplyProfile(Base):
    def test_schema1_with_untouched_md_is_rewritten_and_backed_up(self):
        """驗收 8：schema 1 的 profile.json（md 沒改過）→ 存成現在的 schema、寫前備進回合。"""
        self.put_profile_v1()
        before = (self.V / ".system" / "profile.json").read_text(encoding="utf-8")
        got = migrate.apply(self.V, self.turn)
        self.assertEqual(got["migrated"], [".system/profile.json"])
        self.assertEqual(got["skipped"], [])
        data = read(self.V, ".system/profile.json")
        self.assertEqual(data["schema_version"], profile.SCHEMA_VERSION)
        self.assertEqual(data["md_sha256"], profile.md_sha256(self.V))
        self.assertIn("## 五、關於你", (self.V / "系統" / "客戶設定檔.md").read_text(encoding="utf-8"))
        self.assertEqual(self.saved(".system/profile.json").read_text(encoding="utf-8"), before)
        self.assertTrue(self.saved("系統/客戶設定檔.md").is_file())
        self.assertEqual(migrate.pending(self.V), [])

    def test_hand_edited_md_is_skipped_and_files_untouched(self):
        """md 有沒套用的手改：不重渲染（會蓋掉她的改動），列進 skipped，請先 kb profile apply。"""
        self.put_profile_v1()
        md = self.V / "系統" / "客戶設定檔.md"
        md.write_text(md.read_text(encoding="utf-8") + "\n她手改的一行\n", encoding="utf-8")
        snap = (md.read_text(encoding="utf-8"), (self.V / ".system" / "profile.json").read_text(encoding="utf-8"))
        got = migrate.apply(self.V, self.turn)
        self.assertEqual(got["migrated"], [])
        self.assertEqual([s["rel"] for s in got["skipped"]], [".system/profile.json"])
        self.assertIn("kb profile apply", got["skipped"][0]["why"])
        self.assertEqual((md.read_text(encoding="utf-8"), (self.V / ".system" / "profile.json").read_text(encoding="utf-8")), snap)

    def test_revert_gets_the_old_profile_back(self):
        """versions revert 退得回：把備份放回去等於舊內容（備份就是寫前的原檔）。"""
        self.put_profile_v1()
        old = (self.V / ".system" / "profile.json").read_bytes()
        migrate.apply(self.V, self.turn)
        self.assertEqual(self.saved(".system/profile.json").read_bytes(), old)
        manifest = (self.V / ".system" / "versions" / self.turn / "manifest.jsonl").read_text(encoding="utf-8")
        self.assertIn(".system/profile.json", manifest)


class ApplyInventoryEntities(Base):
    def test_inventory_schema1_rewritten_as_schema2(self):
        shutil.copy2(INV_FIX / "inventory_v1.json", self.V / ".system" / "inventory.json")
        before = (self.V / ".system" / "inventory.json").read_text(encoding="utf-8")
        got = migrate.apply(self.V, self.turn)
        self.assertEqual(got["migrated"], [".system/inventory.json"])
        data = read(self.V, ".system/inventory.json")
        self.assertEqual(data["schema_version"], inventory.SCHEMA_VERSION)
        self.assertTrue(data["entries"])
        self.assertTrue(all("fingerprints" in e and "read" in e for e in data["entries"]))
        self.assertEqual(self.saved(".system/inventory.json").read_text(encoding="utf-8"), before)

    def test_entities_schema1_rewritten_as_current(self):
        shutil.copy2(_entities.FIX / "entities.json", self.V / ".system" / "entities.json")
        before = (self.V / ".system" / "entities.json").read_text(encoding="utf-8")
        got = migrate.apply(self.V, self.turn)
        self.assertEqual(got["migrated"], [".system/entities.json"])
        data = read(self.V, ".system/entities.json")
        self.assertEqual(data["schema_version"], entities.SCHEMA_VERSION)
        self.assertEqual(self.saved(".system/entities.json").read_text(encoding="utf-8"), before)

    def test_current_files_are_not_rewritten_or_backed_up(self):
        (self.V / ".system" / "inventory.json").write_text(json.dumps(inventory.EMPTY), encoding="utf-8")
        got = migrate.apply(self.V, self.turn)
        self.assertEqual((got["migrated"], got["skipped"], got["cards"]), ([], [], 0))
        self.assertFalse(self.saved(".system/inventory.json").exists())

    def test_one_bad_file_does_not_stop_the_others(self):
        """壞掉的 entities.json 列進 skipped，清冊照遷。"""
        shutil.copy2(INV_FIX / "inventory_v1.json", self.V / ".system" / "inventory.json")
        (self.V / ".system" / "entities.json").write_text(json.dumps(
            {"schema_version": 1, "entities": "壞的"}), encoding="utf-8")
        got = migrate.apply(self.V, self.turn)
        self.assertEqual(got["migrated"], [".system/inventory.json"])
        self.assertEqual([s["rel"] for s in got["skipped"]], [".system/entities.json"])


class Cards(Base):
    CARD = ("---\n編號: f-0000aaaa\n標題: 舊卡\n範本版本: 1\n---\n# 舊卡\n\n正文一行\n")

    def put_card(self, name="舊卡-0000aaaa.md", text=None):
        p = self.V / "檔案索引" / "案子"
        p.mkdir(parents=True, exist_ok=True)
        (p / name).write_text(text or self.CARD, encoding="utf-8", newline="\n")
        return f"檔案索引/案子/{name}"

    def fn(self, text):
        return text.replace("範本版本: 1", "範本版本: 2\n實體: []")

    def test_matching_card_header_is_migrated_and_backed_up(self):
        rel = self.put_card()
        with mock.patch.object(migrate, "CARD_HEADER_MIGRATIONS", [{"from": "1", "to": "2", "fn": self.fn}]):
            got = migrate.apply(self.V, self.turn)
        self.assertEqual(got["cards"], 1)
        text = (self.V / rel).read_text(encoding="utf-8")
        self.assertIn("範本版本: 2\n實體: []", text)
        self.assertTrue(text.endswith("正文一行\n"), "正文不動")
        self.assertEqual(self.saved(rel).read_text(encoding="utf-8"), self.CARD)

    def test_other_version_cards_left_alone(self):
        rel = self.put_card(text=self.CARD.replace("範本版本: 1", "範本版本: 2"))
        with mock.patch.object(migrate, "CARD_HEADER_MIGRATIONS", [{"from": "1", "to": "2", "fn": self.fn}]):
            got = migrate.apply(self.V, self.turn)
        self.assertEqual(got["cards"], 0)
        self.assertFalse(self.saved(rel).exists())

    def test_empty_table_touches_no_card(self):
        rel = self.put_card()
        got = migrate.apply(self.V, self.turn)
        self.assertEqual(got["cards"], 0)
        self.assertEqual((self.V / rel).read_text(encoding="utf-8"), self.CARD)

    def test_migration_that_breaks_the_header_is_skipped(self):
        """遷移函式把檔頭改壞（版本沒變成 to、解析不了）就不寫、列進 skipped。"""
        rel = self.put_card()
        with mock.patch.object(migrate, "CARD_HEADER_MIGRATIONS", [{"from": "1", "to": "2", "fn": lambda t: "壞了"}]):
            got = migrate.apply(self.V, self.turn)
        self.assertEqual(got["cards"], 0)
        self.assertEqual((self.V / rel).read_text(encoding="utf-8"), self.CARD)
        self.assertEqual([s["rel"] for s in got["skipped"]], [rel])


if __name__ == "__main__":
    unittest.main()
