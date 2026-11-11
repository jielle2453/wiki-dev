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
                         [".system/profile.json", ".system/inventory.json", ".system/entities.json", ".system/pending.json",
                          ".system/profile.json", "暫存區", ".system/profile.json"])  # 第五列：型別夾補編號（D-249）；第六列：暫存區（D-324）；彈性區兩列 #51 拿掉；第七列：記帳開關補第十節（記帳 1b）

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

    def test_schema4_adds_section_eight_and_reverts(self):
        """標籤字典驗收 2：schema 4（md 沒改過）→ 寫回 schema 5、md 多第八節、兩檔備進回合、versions revert 回得去。"""
        from tests.test_scripts_inventory_cli import run_kb
        shutil.copy2(PROFILE_FIX / "schema4.json", self.V / ".system" / "profile.json")
        shutil.copy2(PROFILE_FIX / "schema4.md", self.V / "系統" / "客戶設定檔.md")
        (self.V / ".system" / "sources.json").write_text('{"schema_version": 1, "sources": []}', encoding="utf-8")
        md =self.V / "系統" / "客戶設定檔.md"
        before = ((self.V / ".system" / "profile.json").read_bytes(), md.read_bytes())
        got = migrate.apply(self.V, self.turn)
        self.assertEqual(got["migrated"], [".system/profile.json"])
        data = read(self.V, ".system/profile.json")
        self.assertEqual((data["schema_version"], data["tags"]), (7, []))
        self.assertIn("\n## 八、標籤\n", md.read_text(encoding="utf-8"))
        self.assertEqual((self.saved(".system/profile.json").read_bytes(), self.saved("系統/客戶設定檔.md").read_bytes()),
                         before)
        r = run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(((self.V / ".system" / "profile.json").read_bytes(), md.read_bytes()), before)

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


class SynthesisLayout(unittest.TestCase):
    """D-523 驗收 4：綜合卡範本版本 1 → 2，推算搬到其他段後面、紀事搬到最後；pending／apply 一起列。"""
    def setUp(self):
        self.tmp, self.V, _raw = _entities.make_entity_vault(with_entities=True)
        with mock.patch.object(migrate, "SYNTHESIS_MIGRATIONS", []):  # 其他遷移（型別夾補編號會搬夾）先跑完
            migrate.apply(self.V, turn.start(self.V, None, "先遷別的")["turn"])
        rels = {Path(rel).stem: rel for rel, _v in migrate._synthesis_cards(self.V)}
        self.XINYI, self.DAAN = rels["信義王"], rels["大安陳"]
        self.turn = turn.start(self.V, None, "升級")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def text(self, rel):
        return (self.V / rel).read_text(encoding="utf-8")

    def heads(self, rel):
        return [l for l in self.text(rel).split("\n") if l.startswith("## ") or l.startswith("<!-- willy:檔")]

    def old_cards(self):
        return sorted(p["rel"] for p in migrate.pending(self.V) if p["from"] == 1 and p["to"] == 2)

    def test_pending_apply_backup_undo_and_idempotent(self):
        from kb._lib import card_base
        from tests.test_scripts_inventory_cli import run_kb
        before = {rel: self.text(rel) for rel in (self.XINYI, self.DAAN)}
        self.assertEqual(self.old_cards(), sorted([self.DAAN, self.XINYI]))
        got = migrate.apply(self.V, self.turn)
        self.assertEqual(got["cards"], 2)
        self.assertEqual(self.heads(self.XINYI), ["## 現況", "## 時程", "## 紀事"])
        self.assertIn("範本版本: 2\n", self.text(self.XINYI))
        self.assertEqual(self.old_cards(), [])
        for rel, old in before.items():
            self.assertEqual((self.V / ".system" / "versions" / self.turn / "files" / rel).read_text(encoding="utf-8"), old)
        self.assertEqual(card_base.edits(self.V)["edits"], [], "程式搬的不算她手改")
        after = self.text(self.XINYI)
        self.assertEqual(migrate.apply(self.V, turn.start(self.V, None, "再一次")["turn"])["cards"], 0)
        self.assertEqual(self.text(self.XINYI), after, "跑第二次不變")
        r = run_kb("versions", "undo", self.turn, cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.text(self.XINYI), before[self.XINYI])

    def test_unreadable_card_does_not_block_others(self):
        (self.V / self.DAAN).write_text("壞掉的卡，沒有檔頭\n", encoding="utf-8")
        got = migrate.apply(self.V, self.turn)
        self.assertEqual(got["cards"], 1)
        self.assertEqual([s["rel"] for s in got["skipped"]], [self.DAAN])
        self.assertIn("範本版本: 2\n", self.text(self.XINYI))
        self.assertEqual(self.text(self.DAAN), "壞掉的卡，沒有檔頭\n")

    def test_hand_edited_file_section_only_events_move(self):
        """她手改過相關檔那段（D-223）：照樣只搬紀事，那段一字不動。"""
        from kb._lib import synthesis
        p = self.V / self.XINYI
        files = synthesis.FILE_BEGIN + "\n## 相關檔\n她自己寫的一行\n" + synthesis.FILE_END
        p.write_text(self.text(self.XINYI).rstrip("\n") + "\n\n" + files + "\n", encoding="utf-8", newline="\n")
        migrate.apply(self.V, self.turn)
        text = self.text(self.XINYI)
        self.assertIn(files, text)
        self.assertEqual(self.heads(self.XINYI), ["## 現況", "## 時程", synthesis.FILE_BEGIN, "## 相關檔",
                                                  synthesis.FILE_END, "## 紀事"])

    def test_pending_hand_edit_stays_hers_only(self):
        """review：遷移當下她有沒處理的手改：留成待處理，搬動的推算、紀事不算她改的。"""
        from kb._lib import card_base
        card_base.record(self.V, self.XINYI)
        p = self.V / self.XINYI
        p.write_text(self.text(self.XINYI).replace("## 現況\n", "## 現況\n- 她加的一句\n"), encoding="utf-8", newline="\n")
        migrate.apply(self.V, self.turn)
        (got,) = card_base.edits(self.V)["edits"]
        self.assertEqual(got["hunks"], [{"before": "", "after": "- 她加的一句"}])

    def test_no_version_and_unreadable_entities_are_listed(self):
        """review：檔頭沒有範本版本的卡列進 skipped；實體清單讀不了也列，不默默當成沒卡。"""
        p = self.V / self.DAAN
        p.write_text("\n".join(l for l in self.text(self.DAAN).split("\n") if not l.startswith("範本版本")),
                     encoding="utf-8", newline="\n")
        got = migrate.apply(self.V, self.turn)
        self.assertEqual([s["rel"] for s in got["skipped"]], [self.DAAN])
        self.assertIn("範本版本", got["skipped"][0]["why"])
        skipped = []
        with mock.patch.object(migrate.entities, "load", side_effect=ValueError("壞了")):
            self.assertEqual(migrate._migrate_synthesis(self.V, self.turn, skipped), 0)
        self.assertEqual(len(skipped), 1)
        self.assertIn("實體清單", skipped[0]["why"])

    def test_crlf_card_kept_on_real_path(self):
        """review：實際走 migrate.apply 時 CRLF 卡照樣是 CRLF（不經 read_text 的換行轉換）。"""
        p = self.V / self.XINYI
        p.write_bytes(self.text(self.XINYI).replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(migrate.apply(self.V, self.turn)["cards"], 2)
        raw = p.read_bytes().decode("utf-8")
        self.assertIn("範本版本: 2\r\n", raw)
        self.assertNotIn("\n", raw.replace("\r\n", ""))

    def test_version_only_read_from_header(self):
        """review：讀不懂的卡只看檔頭的範本版本（內文剛好有那行不算）；檔頭寫 "2" 有引號也算版本 2。"""
        p = self.V / self.DAAN
        no_ver = "\n".join(l for l in self.text(self.DAAN).split("\n") if not l.startswith("範本版本"))
        p.write_bytes((no_ver + "\n範本版本: 2\n").encode("utf-8") + b"\xff\n")
        self.assertEqual([s["rel"] for s in migrate.apply(self.V, self.turn)["skipped"]], [self.DAAN])
        self.assertIn("範本版本: 2\n", self.text(self.XINYI))
        p.write_bytes(self.text(self.XINYI).replace("範本版本: 2", '範本版本: "2"').encode("utf-8") + b"\xff\n")
        self.assertNotIn(self.DAAN, [s["rel"] for s in migrate.apply(self.V, turn.start(self.V, None, "再")["turn"])["skipped"]])

    def test_header_without_closing_line(self):
        """review：檔頭沒有結尾的 ---，內文剛好有「範本版本: 2」那行：不當成版本 2，列進 skipped。"""
        p = self.V / self.DAAN
        p.write_bytes(b"---\n\xe5\x90\x8d\xe7\xa8\xb1: x\n# x\n" + "範本版本: 2\n".encode("utf-8") + b"\xff\n")
        self.assertIsNone(migrate._header_version(p))
        self.assertIn(self.DAAN, [s["rel"] for s in migrate.apply(self.V, self.turn)["skipped"]])

    def test_broken_card_already_new_not_reported(self):
        """review：讀不懂但範本版本已是 2 的卡不在遷移範圍，不每次升級都報。"""
        p = self.V / self.DAAN
        p.write_bytes(self.text(self.DAAN).replace("範本版本: 1", "範本版本: 2").encode("utf-8") + b"\xff\n")
        got = migrate.apply(self.V, self.turn)
        self.assertNotIn(self.DAAN, [s["rel"] for s in got["skipped"]])


class MoneyGone(Base):
    """#65 拿掉記帳（驗收 3、4）：設定檔拿掉第九、十節與平常在哪，開著的帳待處理關掉，舊帳的檔原樣留著。"""
    DAY = "2026-10-19"
    OLD_TAIL = ("\n## 九、數字欄\n舊的提示\n\n| 型別 | 欄名 | 單位 | 來源 | 日期 |\n|---|---|---|---|---|\n| 產品 | 售價 | 元 | 確認 | 2026-10-19 |\n"
                "\n## 十、記帳\n舊的提示\n\n| 狀態 | 地點的型別 | 來源 | 日期 |\n|---|---|---|---|\n| {mode} | 分店 | 確認 | 2026-10-19 |\n")

    def put_old(self, mode="開", mode_key="on"):
        from kb._lib import pending
        data = profile.defaults(self.DAY)
        data["about"] = [{"name": "小王", "kind": "person", "aliases": [], "place": "北店", "source": "said", "date": self.DAY}]
        old_md = profile.render_text(data) + self.OLD_TAIL.format(mode=mode)
        data["fields"] = [{"type": "產品", "field": "售價", "unit": "元", "source": "confirmed", "date": self.DAY}]
        data["money"] = [{"mode": mode_key, "places": ["分店"], "source": "confirmed", "date": self.DAY}]
        data["md_sha256"] = profile.sha256_text(old_md)
        (self.V / "系統" / "客戶設定檔.md").write_text(old_md, encoding="utf-8", newline="\n")
        (self.V / ".system" / "profile.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.kept = {".system/money.json": '{"schema_version": 1, "items": []}', "系統/帳.md": "# 帳\n舊的"}
        for rel, text in self.kept.items():
            (self.V / rel).write_text(text, encoding="utf-8")
        pending.add(self.V, "money_dupe", ["f-1a2b3c4d"], "可能同一筆", None, self.turn)
        pending.add(self.V, "money_unsure", ["f-1a2b3c4e"], "看不出", None, self.turn)
        pending.add(self.V, "unreadable", ["f-1a2b3c4f"], "讀不到", "x", self.turn)

    def states(self):
        from kb._lib import pending
        return {i["kind"]: (i["status"], i["how"]) for i in pending.load(self.V)["items"]}

    def test_old_vault_is_listed_then_cleaned_and_idempotent(self):
        self.put_old()
        self.assertIn(".system/profile.json", [p["rel"] for p in migrate.pending(self.V)])
        got = migrate.apply(self.V, self.turn)
        self.assertEqual(got["skipped"], [])
        data = read(self.V, ".system/profile.json")
        self.assertNotIn("fields", data)
        self.assertNotIn("money", data)
        self.assertTrue(all("place" not in a for a in data["about"]))
        md = (self.V / "系統" / "客戶設定檔.md").read_text(encoding="utf-8")
        self.assertNotIn("## 九、", md)
        self.assertNotIn("## 十、", md)
        self.assertEqual(data["md_sha256"], profile.md_sha256(self.V))
        for rel, text in self.kept.items():
            self.assertEqual((self.V / rel).read_text(encoding="utf-8"), text, f"{rel} 不碰")
        self.assertEqual(migrate.pending(self.V), [])
        again = migrate.apply(self.V, self.turn)
        self.assertEqual((again["migrated"], again["notes"]), ([], []))

    def test_money_pending_closed_with_how_and_other_kinds_untouched(self):
        self.put_old()
        migrate.apply(self.V, self.turn)
        st = self.states()
        self.assertEqual(st["money_dupe"], ("closed", "記帳改成另外的客製功能"))
        self.assertEqual(st["money_unsure"], ("closed", "記帳改成另外的客製功能"))
        self.assertEqual(st["unreadable"][0], "open")

    def test_note_only_when_money_was_on_or_spoken(self):
        for mode, key, said in (("開", "on", True), ("只記我講的", "spoken", True), ("關", "off", False)):
            with self.subTest(mode=mode):
                self.tearDown()
                self.setUp()
                self.put_old(mode, key)
                notes = migrate.apply(self.V, self.turn)["notes"]
                self.assertEqual(notes, ["記帳改成另外的客製功能，你之前記的帳還在 系統/帳.md，不會再更新"] if said else [])

    def test_only_open_money_pending_left_is_still_due(self):
        """設定檔已經乾淨、只剩開著的帳待處理（例如別台舊版又寫了一件）：照樣關掉。"""
        from kb._lib import pending
        (self.V / ".system" / "profile.json").write_text(json.dumps(profile.defaults(self.DAY)), encoding="utf-8")
        pending.add(self.V, "money_unsure", ["f-1a2b3c4e"], "看不出", None, self.turn)
        self.assertEqual([p["rel"] for p in migrate.pending(self.V)], [".system/profile.json"])
        migrate.apply(self.V, self.turn)
        self.assertEqual(self.states()["money_unsure"][0], "closed")


class OldExtras(Base):
    """#51（D-532）：_extras 改名那列拿掉，_extras 當一般夾。"""

    def test_extras_left_alone(self):
        (self.V / "_extras").mkdir()
        (self.V / "_extras" / "a.md").write_text("x", encoding="utf-8")
        self.assertEqual(migrate.pending(self.V), [])
        got = migrate.apply(self.V, self.turn)
        self.assertEqual((self.V / "_extras" / "a.md").read_text(encoding="utf-8"), "x")
        self.assertFalse((self.V / "_個人").exists())
        self.assertEqual(got["notes"], [])


if __name__ == "__main__":
    unittest.main()
