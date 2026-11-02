"""放寬丙第三輪 11、12、13（驗收 24、25、26）：指路卡（kb cards mode／seen、todo 的 change 與 pointer_changed）、
封存（kb archive、todo／find／lookup／總目錄／待處理／題目）、卡上口述為準裁示帶得出來。真的跑 CLI。"""
import json
import shutil
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from tests import _cards, _ooxml
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import cards, entities, pending, plan, turn  # noqa: E402

TXT = "報價與合約/合約範本.txt"
CHANGED_BLOCKS = [("h", "大安陳第一次會議"), ("p", "討論廚房動線與插座位置"), ("tbl", [["項目", "結論"], ["廚具", "一字型"]])]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _cards.make_card_vault()
        self.set_config(recard_idle_minutes=0)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def set_config(self, **kv):
        p = self.V / ".system" / "config.json"
        data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        data.update(kv)
        p.write_text(json.dumps(data), encoding="utf-8")

    def kb(self, *args):
        return run_kb(*args, cwd=self.V)

    def ok(self, *args):
        r = self.kb(*args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r

    def todo(self):
        return json.loads(self.ok("cards", "todo", "--json").stdout)

    def fid(self, rel=_cards.MEETING):
        return _cards.entry_of(self.V, rel)["id"]

    def entry(self, fid):
        inv = json.loads((self.V / ".system" / "inventory.json").read_text(encoding="utf-8"))
        return next(e for e in inv["entries"] if e["id"] == fid)

    def card(self, rel=_cards.MEETING, title="會議"):
        item = next(i for i in self.todo()["new"] if i["id"] == self.fid(rel))
        return _cards.write_card(self.V, item, title)

    def front(self, path):
        return cards.parse_front(Path(path).read_text(encoding="utf-8"))

    def change_file(self):
        _ooxml.docx(self.raw / _cards.MEETING, CHANGED_BLOCKS)
        _cards.scan_apply(self.V)

    def cache(self, fid):
        return self.V / ".system" / "local" / "textcache" / f"{fid}.txt"


class PointerMode(Base):
    def test_mode_pointer_records_inventory_and_textcache(self):
        fid = self.fid()
        got = json.loads(self.ok("cards", "mode", fid, "pointer", "--json").stdout)
        self.assertEqual((got["mode"], got["track"], got["textcache"]), ("pointer", True, True))
        self.assertEqual(self.entry(fid)["card_mode"], "pointer")
        self.assertIn("廚房動線", self.cache(fid).read_text(encoding="utf-8"))

    def test_mode_goes_into_the_turn_and_card_front_follows(self):
        path = self.card()
        fid = self.fid()
        self.ok("cards", "mode", fid, "pointer")
        self.assertEqual(self.front(path).get("卡式"), "指路")
        self.ok("cards", "mode", fid, "full")
        self.assertNotIn("卡式", self.front(path))
        self.assertNotIn("card_mode", self.entry(fid))
        self.assertFalse(self.cache(fid).exists())

    def test_sync_補卡式_from_inventory(self):
        path = self.card()
        fid = self.fid()
        self.ok("cards", "mode", fid, "pointer")
        path.write_text(cards.set_front_value(path.read_text(encoding="utf-8"), "卡式", None), encoding="utf-8", newline="\n")
        self.assertNotIn("卡式", self.front(path))
        self.ok("cards", "sync")
        self.assertEqual(self.front(path).get("卡式"), "指路")

    def test_pointer_file_change_goes_to_pointer_changed_with_diff(self):
        path = self.card()
        fid = self.fid()
        self.ok("cards", "mode", fid, "pointer")
        self.change_file()
        data = self.todo()
        self.assertEqual([i["id"] for i in data["stale"]], [])
        (item,) = data["pointer_changed"]
        self.assertEqual(item["id"], fid)
        self.assertIn("插座位置", item["diff"])
        self.assertIn("changes_7d", item["change"])
        self.ok("cards", "seen", fid)
        self.assertEqual(self.todo()["pointer_changed"], [])
        self.assertIn("插座位置", self.cache(fid).read_text(encoding="utf-8"))
        self.assertEqual(self.todo()["stale"], [])  # 看過了也沒有掉回重做
        self.assertEqual(self.front(path)["指紋"], cards.current_fp(self.entry(fid)))

    def test_track_no_has_no_diff_and_drops_cache(self):
        self.card()
        fid = self.fid()
        self.ok("cards", "mode", fid, "pointer", "--track", "no")
        self.assertFalse(self.cache(fid).exists())
        self.change_file()
        (item,) = self.todo()["pointer_changed"]
        self.assertNotIn("diff", item)

    def test_diff_is_cut_at_the_limit(self):
        self.card()
        fid = self.fid()
        self.set_config(pointer_diff_max_chars=30)
        self.ok("cards", "mode", fid, "pointer")
        self.change_file()
        (item,) = self.todo()["pointer_changed"]
        self.assertTrue(item["diff_truncated"])
        self.assertEqual(len(item["diff"]), 30)

    def test_pointer_changed_not_counted_and_open_file_still_deferred(self):
        self.card()
        fid = self.fid()
        self.ok("cards", "mode", fid, "pointer")
        before = self.todo()["plan"]
        self.change_file()
        data = self.todo()
        self.assertEqual(data["plan"], before)  # 不算進整理的份數
        (self.raw / "客戶案件/大安陳/~$會議紀錄_1.docx").write_bytes(b"x")  # 鎖檔：照 D-329 先不列
        data = self.todo()
        self.assertEqual(data["pointer_changed"], [])
        self.assertEqual([d["why"] for d in data["deferred"]], ["open"])

    def test_change_counts_from_fingerprint_times(self):
        self.card()
        fid = self.fid()
        self.change_file()  # 清冊多一筆指紋，卡的指紋過時
        p = self.V / ".system" / "inventory.json"
        inv = json.loads(p.read_text(encoding="utf-8"))
        entry = next(e for e in inv["entries"] if e["id"] == fid)
        last = entry["fingerprints"][-1]
        now = datetime.now()
        entry["fingerprints"] = entry["fingerprints"][:1] + [
            dict(last, time=(now - timedelta(days=d)).strftime("%Y-%m-%dT%H:%M:%S")) for d in (40, 5, 4, 3, 2, 1)]
        entry["fingerprints"][-1] = dict(last, time=now.strftime("%Y-%m-%dT%H:%M:%S"))
        p.write_text(json.dumps(inv), encoding="utf-8")
        (item,) = self.todo()["stale"]
        change = item["change"]
        self.assertEqual((change["changes_7d"], change["changes_30d"], change["days_since"]), (5, 5, 0))
        self.assertEqual((change["mode"], change["track"], change["open"], change["entity_done"]), ("full", True, False, False))

    def test_mode_refuses_unknown_and_seen_needs_pointer(self):
        self.assertEqual(self.kb("cards", "mode", "f-00000000", "pointer").returncode, 3)
        self.card()
        r = self.kb("cards", "seen", self.fid())
        self.assertEqual(r.returncode, 3)


class Archive(Base):
    def test_archive_file_marks_inventory_card_and_stops_redo(self):
        path = self.card()
        fid = self.fid()
        r = self.ok("archive", fid, "--reason", "舊價目表", "--json")
        self.assertEqual(json.loads(r.stdout)["done"][0]["id"], fid)
        info = self.entry(fid)["archived"]
        self.assertEqual(info["reason"], "舊價目表")
        self.assertEqual(self.front(path)["封存"], info["date"])
        self.change_file()
        data = self.todo()
        self.assertEqual(data["stale"], [])
        self.assertNotIn(fid, [i["id"] for i in data["new"]])
        self.assertEqual(data["pointer_changed"], [])
        self.ok("archive", "--undo", fid)
        self.assertNotIn("archived", self.entry(fid))
        self.assertNotIn("封存", self.front(path))
        self.assertEqual([i["id"] for i in self.todo()["stale"]], [fid])

    def test_archive_goes_into_the_turn(self):
        """清冊與卡檔頭的改動備進回合（退得回）。"""
        path = self.card()
        fid = self.fid()
        self.ok("archive", fid)
        last = sorted(p.name for p in (self.V / ".system" / "versions").iterdir() if p.is_dir())[-1]
        paths = {e["path"] for e in turn.entries(self.V, last)}
        self.assertIn(".system/inventory.json", paths)
        self.assertIn(path.relative_to(self.V).as_posix(), paths)

    def test_new_archived_file_is_not_listed_as_new(self):
        fid = self.fid()
        before = {i["id"] for i in self.todo()["new"]}
        self.assertIn(fid, before)
        self.ok("archive", fid)
        self.assertNotIn(fid, {i["id"] for i in self.todo()["new"]})

    def test_find_and_list_keep_it_with_archived_last(self):
        self.card(title="會議紀錄新")
        self.card(TXT, "會議範本")
        a, b = self.fid(), self.fid(TXT)
        self.ok("archive", b)
        got = json.loads(self.ok("find", "會議", "--json").stdout)
        files = got["files"]
        self.assertEqual({f["card"] for f in files}, {a, b})
        self.assertEqual([f["archived"] for f in files], [False, True])
        listed = json.loads(self.ok("cards", "list", "--json").stdout)["cards"]
        self.assertEqual([c["archived"] for c in listed], [False, True])
        self.ok("archive", a)  # 兩張都封存：照原順序
        self.ok("archive", "--undo", b)
        files = json.loads(self.ok("find", "會議", "--json").stdout)["files"]
        self.assertEqual([f["card"] for f in files], [b, a])

    def test_entity_archive_and_lookup_and_index(self):
        self.ok("entity", "add", "--type", "案子", "--name", "大同建材")
        syn = self.V / "案子" / "大同建材" / "大同建材.md"
        syn.parent.mkdir(parents=True, exist_ok=True)
        syn.write_text("# 大同建材\n", encoding="utf-8")
        self.ok("archive", "大同建材", "--reason", "不往來了")
        ent = next(e for e in entities.load(self.V)["entities"] if e["name"] == "大同建材")
        self.assertEqual(ent["archived"]["reason"], "不往來了")
        got = json.loads(self.ok("lookup", "大同建材", "--json").stdout)
        self.assertTrue(got["archived"])
        text = (self.V / "總目錄.md").read_text(encoding="utf-8")
        head, _sep, fold = text.partition("> [!note]- 已封存")
        self.assertIn("大同建材", fold)
        self.assertNotIn("[大同建材]", head)
        self.assertIn("已封存", self.ok("lookup", "大同建材").stdout)
        self.ok("archive", "--undo", "大同建材")
        self.assertNotIn("已封存", (self.V / "總目錄.md").read_text(encoding="utf-8"))
        self.assertFalse(json.loads(self.ok("lookup", "大同建材", "--json").stdout)["archived"])

    def test_archive_refuses_unknown_target_and_writes_nothing(self):
        fid = self.fid()
        r = self.kb("archive", fid, "沒有這個東西")
        self.assertEqual(r.returncode, 3)
        self.assertNotIn("archived", self.entry(fid))

    def test_archive_by_path(self):
        fid = self.fid()
        self.ok("archive", str(self.raw / _cards.MEETING))
        self.assertIn("archived", self.entry(fid))

    def test_archived_synthesis_file_goes_to_the_other_box(self):
        from kb._lib import synthesis
        a = {"id": "f-1", "path": "檔案索引/a/a-1.md", "title": "甲", "date": "2026-01-01", "card_type": "會議紀錄", "relation": "main"}
        b = dict(a, id="f-2", path="檔案索引/a/b-2.md", title="乙", date="2026-02-01", archived=True)
        text = synthesis.file_section([a, b])
        main, _sep, other = text.partition("> [!note]- 其他")
        self.assertIn("甲", main)
        self.assertNotIn("乙", main)
        self.assertIn("乙", other)

    def test_pending_and_asks_hide_archived(self):
        fid = self.fid()
        pid = pending.add(self.V, "unreadable", [fid], "「會議」讀不到", "有密碼", turn.start(self.V, None, "")["turn"])
        self.assertIn(pid, [i["id"] for i in json.loads(self.ok("pending", "list", "--json").stdout)])
        self.ok("archive", fid)
        self.assertNotIn(pid, [i["id"] for i in json.loads(self.ok("pending", "list", "--json").stdout)])
        self.assertNotIn("會議", (self.V / "系統" / "待處理.md").read_text(encoding="utf-8") if (self.V / "系統" / "待處理.md").exists() else "")
        # 題目：跟封存的檔有關的拿掉
        asks = [{"id": "credential:" + fid, "kind": "x", "question": "q", "results": [], "about": {"files": [fid], "entities": []}},
                {"id": "credential:f-other", "kind": "x", "question": "q2", "results": [], "about": {"files": ["f-other"], "entities": []}}]
        shown, hidden = plan.visible(self.V, asks)
        self.assertEqual([a["id"] for a in shown], ["credential:f-other"])
        self.assertEqual(hidden, 0)

    def test_agenda_unscanned_skips_archived(self):
        self.card()
        fid = self.fid()
        self.assertIn(fid, [i["id"] for i in self.todo()["agenda_unscanned"]])
        self.ok("archive", fid)
        self.assertNotIn(fid, [i["id"] for i in self.todo()["agenda_unscanned"]])

    def test_archive_entity_leaves_matter_progress_alone(self):
        self.ok("entity", "add", "--type", "案子", "--name", "王宅")
        self.ok("archive", "王宅")
        ent = next(e for e in entities.load(self.V)["entities"] if e["name"] == "王宅")
        self.assertEqual(ent.get("progress"), "ongoing")
        again = json.loads(self.ok("archive", "王宅", "--json").stdout)
        self.assertEqual(again["done"], [])
        self.assertEqual(len(again["unchanged"]), 1)


class SpokenRulings(Base):
    def test_find_and_lookup_cards_carry_spoken_wins_rulings(self):
        self.card(title="會議紀錄新")
        fid = self.fid()
        self.ok("ruling", "add", "--kind", "口述為準", "--card", fid, "--text", "會議結論以客戶說的為準")
        files = json.loads(self.ok("find", "會議", "--json").stdout)["files"]
        (row,) = files
        self.assertEqual([r["text"] for r in row["rulings"]], ["會議結論以客戶說的為準"])
        self.assertEqual(row["rulings"][0]["cards"][0]["id"], fid)

    def test_card_without_ruling_has_no_field(self):
        self.card(title="會議紀錄新")
        (row,) = json.loads(self.ok("find", "會議", "--json").stdout)["files"]
        self.assertNotIn("rulings", row)

    def test_lookup_cards_of_entity_carry_rulings(self):
        self.ok("entity", "add", "--type", "案子", "--name", "大安陳")
        item = next(i for i in self.todo()["new"] if i["id"] == self.fid())
        p = _cards.card_path(self.V, item, "會議")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_cards.card_text(item, "會議").replace("實體: []", "實體: [大安陳]"), encoding="utf-8", newline="\n")
        fid = self.fid()
        self.ok("ruling", "add", "--kind", "口述為準", "--card", fid, "--text", "以客戶說的為準")
        got = json.loads(self.ok("lookup", "大安陳", "--json").stdout)
        (card,) = got["cards"]
        self.assertEqual([r["text"] for r in card["rulings"]], ["以客戶說的為準"])
        self.assertTrue(got["rulings"])  # 頂層照舊
        self.assertFalse(card["archived"])


if __name__ == "__main__":
    unittest.main()
