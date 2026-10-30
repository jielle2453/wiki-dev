"""手改卡測試第 1 輪後（裁定 5）：型別改名／合併換鍵（#1）、Z5／Z1 驗證沒過也記基準（#2）、--done 同回合不出假通知（#3）、
實體改名時程式換的標題不算她改的（#4）、開場一張都沒比到也說一句（#5）、驗收 3 的端到端（#7：merge、skip、型別改名、型別合併）。
purge 洗 card_base.json（#6）在 tests/test_lib_purge.py。"""
import json
import shutil
import unittest
from pathlib import Path

from tests import _cards, _entities
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import card_base, turn  # noqa: E402

SID = "test-sid"
XINYI = "案子/信義王/信義王.md"
DAAN = "案子/大安陳/大安陳.md"


class EntityVault(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _entities.make_entity_vault(with_entities=True)
        card_base.edits(self.V)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kb(self, *args):
        r = run_kb(*args, cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def edits(self):
        return json.loads(self.kb("cards", "edits", "--json").stdout)

    def hand_edit(self, rel, line="- 交屋延到 12 月"):
        p = self.V / rel
        p.write_text(p.read_text(encoding="utf-8") + line + "\n", encoding="utf-8", newline="\n")

    def keys(self):
        return set(card_base.load(self.V))


class TypeOps(EntityVault):
    """#1、#7：kb profile type rename／merge 搬整個型別夾，紀錄跟著換鍵、她沒處理的手改保留、舊鍵不殘留。"""

    def test_type_rename_rekeys_not_listed(self):
        self.kb("profile", "type", "rename", "案子", "--to", "工程")
        self.assertEqual(self.edits(), {"edits": [], "more": False})
        self.assertEqual(self.keys(), {"工程/信義王/信義王.md", "工程/大安陳/大安陳.md"})

    def test_type_rename_keeps_pending_hand_edit(self):
        self.hand_edit(XINYI)
        self.kb("profile", "type", "rename", "案子", "--to", "工程")
        got = self.edits()
        self.assertEqual([e["path"] for e in got["edits"]], ["工程/信義王/信義王.md"])
        self.assertIn({"before": "", "after": "- 交屋延到 12 月"}, got["edits"][0]["hunks"])
        self.assertEqual(self.keys(), {"工程/信義王/信義王.md", "工程/大安陳/大安陳.md"})  # 舊鍵不殘留

    def test_type_merge_rekeys_and_keeps_pending(self):
        self.hand_edit(XINYI)
        self.kb("profile", "type", "merge", "案子", "--into", "業主")
        got = self.edits()
        self.assertEqual([e["path"] for e in got["edits"]], ["業主/信義王/信義王.md"])
        self.assertEqual(self.keys(), {"業主/信義王/信義王.md", "業主/大安陳/大安陳.md"})


class EntityOps(EntityVault):
    def test_entity_merge_forgets_source_card(self):
        """#7：kb entity merge 來源綜合卡刪掉，紀錄跟著刪，不列。"""
        self.kb("entity", "merge", "大安陳", "--into", "信義王")
        self.assertEqual(self.edits(), {"edits": [], "more": False})
        self.assertNotIn(DAAN, self.keys())

    def test_rename_with_pending_does_not_count_program_title_as_hers(self):
        """#4：她有沒處理的手改時實體改名，程式換的標題不算進她的 hunks。"""
        self.hand_edit(XINYI)
        self.kb("entity", "rename", "信義王", "--to", "王宅邸")
        (item,) = self.edits()["edits"]
        self.assertEqual(item["path"], "案子/王宅邸/王宅邸.md")
        self.assertEqual(item["hunks"], [{"before": "", "after": "- 交屋延到 12 月"}])


class SkipEndToEnd(unittest.TestCase):
    """#7：kb cards skip 拿掉有卡的檔，紀錄跟著刪，不列。"""

    def setUp(self):
        self.tmp, self.V, self.raw = _cards.make_card_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_skip_removes_card_and_base(self):
        from kb._lib import cards, sources as sources_lib
        fid = _cards.entry_of(self.V, _cards.MEETING)["id"]
        item = next(i for i in cards.todo(self.V, sources_lib.load(self.V))["new"] if i["id"] == fid)
        p = _cards.write_card(self.V, item, "大安陳第一次會議")
        rel = p.relative_to(self.V).as_posix()
        card_base.edits(self.V)
        self.assertIn(rel, card_base.load(self.V))
        md = self.V / "系統" / "客戶設定檔.md"
        text = md.read_text(encoding="utf-8")
        row = "| 請款 | 不整理 |\n"
        # 照既有 Skip 測試的做法：設定檔第三節加一列「請款 | 不整理」再 apply
        from tests.test_scripts_cards_cli import PAY
        md.write_text(text.replace(PAY, PAY + row), encoding="utf-8", newline="\n")
        self.assertEqual(run_kb("profile", "apply", cwd=self.V).returncode, 0)
        turn.start(self.V, None, "")
        r = run_kb("cards", "skip", fid, "--kind", "請款", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(p.exists())
        self.assertNotIn(rel, card_base.load(self.V))
        r = run_kb("cards", "edits", "--json", cwd=self.V)
        self.assertEqual(json.loads(r.stdout), {"edits": [], "more": False})


if __name__ == "__main__":
    unittest.main()
