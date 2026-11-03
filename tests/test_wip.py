"""製作中（D-525 第 3、4 點，驗收 4）：kb cards wip 是 todo 的 new＋stale（md、標了重做的不列，裁定 2），
entities 照實體夾（prefill_entities）與檔名含名稱或別名；kb lookup 多 in_progress、人讀多一行「製作中：」。"""
import datetime
import json
import shutil
import unittest

from tests import _cards
from tests import _entities as E
from tests.test_lib_lookup import OWNER, write_card
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import cards, lookup, turn  # noqa: E402
from kb._lib import sources as sources_lib  # noqa: E402


class Wip(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        data = json.loads((self.V / ".system" / "entities.json").read_text(encoding="utf-8"))["entities"]
        E.put_entities(self.V, data + [E.entity(OWNER, "王先生", "業主", aliases=["王董"])])
        self.t = turn.start(self.V, None, "")["turn"]
        self.contract, _ = write_card(self.V, E.CONTRACT, "信義王合約", ["信義王"], kind="合約", date="2026-09-20")
        (self.V / "案子" / "信義王" / "新報價.txt").write_text("新報價\n", encoding="utf-8")
        (self.raw / "客戶案件" / "王董估價.txt").write_text("估價\n", encoding="utf-8")
        (self.raw / "客戶案件" / "雜項.txt").write_text("雜項\n", encoding="utf-8")
        (self.raw / "客戶案件" / "王董筆記.md").write_text("# 筆記\n", encoding="utf-8")
        _cards.scan_apply(self.V)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def by_name(self, rows=None):
        return {r["name"]: r for r in (cards.wip(self.V) if rows is None else rows)}

    def test_entities_and_md(self):
        rows = self.by_name()
        self.assertEqual(rows["新報價.txt"]["entities"], ["信義王"])  # 實體夾底下
        self.assertEqual(rows["王董估價.txt"]["entities"], ["王先生"])  # 檔名含別名
        self.assertEqual(rows["雜項.txt"]["entities"], [])
        self.assertNotIn("王董筆記.md", rows)  # md 不算製作中（第 8 點）
        for r in rows.values():
            self.assertEqual(set(r), {"id", "path", "name", "mtime", "entities"})
        self.assertNotIn(self.contract, {r["id"] for r in rows.values()}, "有卡、沒改過的不列")

    def test_archived_entity_not_matched_by_filename(self):
        data = json.loads((self.V / ".system" / "entities.json").read_text(encoding="utf-8"))["entities"]
        for e in data:
            if e["name"] == "王先生":
                e["archived"] = True
        E.put_entities(self.V, data)
        self.assertEqual(self.by_name()["王董估價.txt"]["entities"], [])

    def test_changed_listed(self):
        from tests import _ooxml
        _ooxml.docx(self.V / "案子" / "信義王" / "合約.docx", [("p", "改過的合約")])
        _cards.scan_apply(self.V)
        row = self.by_name()["合約.docx"]
        self.assertEqual((row["id"], row["entities"]), (self.contract, ["信義王"]))
        self.assertTrue(row["mtime"].startswith(str(datetime.date.today().year)))

    def test_not_wip_entry_not_listed(self):
        """裁定 13：有卡的檔記成照設定不整理後又改了，wip 跟每句開頭一樣不列（cards.not_wip）。"""
        from tests import _ooxml
        p = self.V / ".system" / "inventory.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        for e in data["entries"]:
            if e["id"] == self.contract:
                e["skip_kind"] = "合約"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        _ooxml.docx(self.V / "案子" / "信義王" / "合約.docx", [("p", "改過的合約")])
        _cards.scan_apply(self.V)
        self.assertNotIn(self.contract, {r["id"] for r in cards.wip(self.V)})
        self.assertEqual(lookup.lookup(self.V, "信義王")["in_progress"], [r for r in cards.wip(self.V) if "信義王" in r["entities"]])

    def test_redo_not_listed(self):
        """標了重做（卡讀錯）的不算製作中（裁定 2）：todo 照常列 stale，wip 不列。"""
        r = run_kb("cards", "redo", self.contract, cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(self.contract, [i["id"] for i in cards.todo(self.V, sources_lib.load(self.V))["stale"]])
        self.assertNotIn(self.contract, {r["id"] for r in cards.wip(self.V)})

    def test_cli_json_and_text(self):
        r = run_kb("cards", "wip", "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rows = self.by_name(json.loads(r.stdout))
        self.assertEqual(rows["新報價.txt"]["entities"], ["信義王"])
        r = run_kb("cards", "wip", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(r.stdout.startswith("製作中 "), r.stdout)
        self.assertIn("新報價.txt", r.stdout)

    def test_lookup_in_progress(self):
        got = lookup.lookup(self.V, "信義王")
        self.assertEqual([r["name"] for r in got["in_progress"]], ["新報價.txt"])
        self.assertEqual(lookup.lookup(self.V, "王董")["in_progress"][0]["name"], "王董估價.txt")
        self.assertEqual(lookup.lookup(self.V, "沒有這個")["in_progress"], [])
        r = run_kb("lookup", "信義王", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        (line,) = [ln for ln in r.stdout.splitlines() if ln.startswith("製作中：")]
        self.assertRegex(line, r"^製作中：新報價\.txt（\d{1,2}/\d{1,2} 改）$")


if __name__ == "__main__":
    unittest.main()
