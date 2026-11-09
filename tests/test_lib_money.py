"""記帳 2（issue #27；D-271～D-277、D-282、D-284、D-338、D-339、D-342、D-343）：_lib/money 的資料與算法。
庫存（商品 × 地點與合計）、區間加總與比較、估的、毛利、for_entity、owed_to、改名合併跟著換、兩台改同一筆不同欄、
製卡待抽（money_fp）、purge 清出處卡、lookup、批次加讀 references/money.md。CLI 的黑箱在 test_scripts_money_cli。"""
import json
import os
import shutil
import unittest
from pathlib import Path

from tests import _entities as E
from tests.test_entity_fields import field_row, write_profile
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import entities, env, inventory, money, people, profile, streams, turn  # noqa: E402

DAY = E.DAY
TYPES = (("案子", "matter"), ("業主", "party"), ("產品", "asset"), ("分店", "party"))
FIELDS = (field_row("產品", "售價", "元"), field_row("產品", "進價", "元"), field_row("產品", "安全庫存", "瓶"),
          field_row("產品", "每箱", "瓶"))
ESS, CAP, PRO, NORTH, SOUTH, LEE, SHOP, MRWANG = ("e-dddd0001", "e-dddd0002", "e-dddd0003", "e-dddd0004", "e-dddd0005",
                                                  "e-dddd0006", "e-dddd0007", "e-dddd0008")


def money_row(mode="on", places=()):
    return [{"mode": mode, "places": list(places), "source": "confirmed", "date": DAY}]


class MoneyBase(unittest.TestCase):
    """產品 精華液（售價 1800、進價 1200、安全庫存 5）、膠囊（售價 900）、益生菌；分店 北店、南店；業主 李小姐、文具店、王先生；
    記帳開著。places=True 時第十節的地點型別是分店。"""
    places = False

    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        E.set_profile(self.V, types=TYPES)
        write_profile(self.V, fields=[dict(f) for f in FIELDS],
                      money=money_row("on", ["分店"] if self.places else []))
        ents = entities.load(self.V)["entities"] + [
            E.entity(ESS, "精華液", "產品", **{"欄:售價": {"value": 1800, "from": "said"}, "欄:進價": {"value": 1200, "from": "said"},
                                              "欄:安全庫存": {"value": 5, "from": "said"}}),
            E.entity(CAP, "膠囊", "產品", **{"欄:售價": {"value": 900, "from": "said"}}),
            E.entity(PRO, "益生菌", "產品", **{"欄:每箱": {"value": 24, "from": "said"}}),
            E.entity(NORTH, "北店", "分店"), E.entity(SOUTH, "南店", "分店"),
            E.entity(LEE, "李小姐", "業主"), E.entity(SHOP, "文具店", "業主"), E.entity(MRWANG, "王先生", "業主")]
        E.put_entities(self.V, ents)
        self.t = turn.start(self.V, None, "記帳")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kb(self, *args, code=0):
        r = run_kb(*args, cwd=self.V)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return r

    def kbj(self, *args, code=0):
        return json.loads(self.kb(*args, "--json", code=code).stdout)

    def add(self, *args, code=0):
        return self.kbj("money", "add", *args, code=code)

    def set_mode(self, mode, places=()):
        data = profile.load(self.V)
        write_profile(self.V, money=money_row(mode, places), people=data.get("people", 1), about=data.get("about") or [])

    def team(self, me="小王", place="北店"):
        write_profile(self.V, people=3, money=money_row("on", ["分店"]),
                      about=[{"name": "小王", "kind": "person", "aliases": [], "place": place, "source": "said", "date": DAY},
                             {"name": "老闆", "kind": "person", "aliases": [], "source": "said", "date": DAY}])
        env.set_person(self.V, me)


class Stock(MoneyBase):
    places = True

    def test_stock_by_place_and_total(self):
        self.add("--dir", "付", "--amount", "1000", "--entity", "文具店", "--item", "益生菌 +20 在北店", "--item", "益生菌 +5在南店")
        self.add("--dir", "無", "--item", "益生菌 -5 在北店", "--item", "益生菌 +5 在南店", "--text", "調貨")
        got = money.stock(self.V, "益生菌")["products"]
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0]["total"], got[0]["places"]), (25, {"北店": 15, "南店": 10}))
        north = money.stock(self.V, place="北店")["products"]
        self.assertEqual([(p["name"], p["places"]) for p in north], [("益生菌", {"北店": 15})])

    def test_cancelled_not_counted_open_counted(self):
        a = self.add("--dir", "收", "--entity", "李小姐", "--due", "2026-12-01", "--item", "精華液 -2 在北店")["item"]["id"]
        self.assertEqual(money.stock(self.V, "精華液")["products"][0]["total"], -2)  # 賒帳先拿貨照算（新定 5）
        self.kb("money", "cancel", a)
        self.assertEqual(money.stock(self.V, "精華液")["products"], [])


class Summary(MoneyBase):
    def test_range_by_paid_date_estimated_and_margin(self):
        self.add("--dir", "收", "--amount", "5000", "--date", "2026-10-30", "--entity", "李小姐", "--item", "精華液 -2",
                 "--item", "膠囊 -1", "--text", "賣出")
        self.add("--dir", "收", "--amount", "3600", "--date", "2026-09-10", "--entity", "李小姐", "--item", "精華液 -2@1800")
        self.add("--dir", "付", "--amount", "800", "--date", "2026-10-02", "--entity", "文具店", "--text", "文具")
        self.add("--dir", "收", "--amount", "120000", "--due", "2026-10-31", "--entity", "王先生", "--text", "尾款")
        got = money.summary(self.V, "2026-10-01", "2026-10-31")
        self.assertEqual((got["in"], got["out"], got["net"], got["open_in"]), (5000, 800, 4200, 120000))
        ess = next(p for p in got["products"] if p["name"] == "精華液")
        self.assertEqual((ess["qty"], ess["estimated"]), (2, True))
        self.assertEqual(ess["amount"], 4000)  # 5000 照售價 1800×2 : 900×1 分
        self.assertEqual(ess["margin"], 1200)  # 2 ×（1800 − 1200）
        cap = next(p for p in got["products"] if p["name"] == "膠囊")
        self.assertIsNone(cap["margin"])  # 沒有進價不算
        vs = money.summary(self.V, "2026-10-01", "2026-10-31", vs=("2026-09-01", "2026-09-30"))
        self.assertEqual(vs["vs"]["in"], 3600)
        self.assertEqual(vs["diff"]["in"]["diff"], 1400)
        sep = money.summary(self.V, "2026-09-01", "2026-09-30")
        ess = next(p for p in sep["products"] if p["name"] == "精華液")
        self.assertEqual((ess["amount"], ess["estimated"]), (3600, False))

    def test_entity_filter_and_by_type(self):
        self.add("--dir", "收", "--amount", "5000", "--date", "2026-10-30", "--entity", "李小姐")
        self.add("--dir", "收", "--amount", "300", "--date", "2026-10-30", "--text", "零售")
        got = money.summary(self.V, "2026-10-01", "2026-10-31", entity="李小姐")
        self.assertEqual(got["in"], 5000)
        everyone = money.summary(self.V, "2026-10-01", "2026-10-31")
        self.assertIn("其他", everyone["by_type"])
        self.assertEqual(everyone["by_type"]["業主"][0]["name"], "李小姐")


class ForEntity(MoneyBase):
    places = True

    def test_for_entity_and_lookup(self):
        self.add("--dir", "收", "--amount", "5000", "--date", "2026-10-30", "--entity", "李小姐", "--item", "精華液 -2 在北店")
        self.add("--dir", "收", "--amount", "1800", "--due", "2026-11-30", "--entity", "李小姐")
        got = money.for_entity(self.V, "李小姐")
        self.assertEqual((got["in"], got["open_in"], len(got["open"]), len(got["recent"])), (5000, 1800, 1, 1))
        out = self.kbj("lookup", "李小姐")
        self.assertEqual(out["money"]["in"], 5000)
        lines = self.kb("lookup", "李小姐").stdout
        self.assertIn("帳：累計收 5,000｜未收 1,800", lines)
        ess = self.kbj("lookup", "精華液")["money"]
        self.assertEqual(ess["stock"]["places"], {"北店": -2, "南店": 0})
        north = self.kbj("lookup", "北店")["money"]
        self.assertEqual([p["name"] for p in north["stock"]], ["精華液"])

    def test_lookup_off_without_items_has_no_money(self):
        self.set_mode("off")
        self.assertNotIn("money", self.kbj("lookup", "李小姐"))


class Follow(MoneyBase):
    places = True

    def test_rename_merge_and_remove(self):
        mid = self.add("--dir", "收", "--amount", "5000", "--entity", "李小姐", "--item", "精華液 -2 在北店")["item"]["id"]
        self.kb("entity", "rename", "精華液", "--to", "玻尿酸精華")
        self.kb("entity", "rename", "北店", "--to", "台北店")
        it = money.get(self.V, mid)
        self.assertEqual((it["lines"][0]["entity"], it["lines"][0]["place"]), ("玻尿酸精華", "台北店"))
        self.kb("entity", "merge", "李小姐", "--into", "王先生")
        self.assertEqual(money.get(self.V, mid)["entities"], ["王先生"])
        self.kb("entity", "remove", "王先生")
        self.assertEqual(money.get(self.V, mid)["entities"], ["王先生"])  # 拿掉的實體錢不刪
        self.assertIn("王先生（已拿掉）", self.kb("money", "list").stdout)  # 測試報告低 #5：帳上看得出已拿掉


class TwoMachines(MoneyBase):
    def setUp(self):
        super().setUp()
        self._orig = env.machine_name
        self.addCleanup(lambda: setattr(env, "machine_name", self._orig))

    def machine(self, name):
        env.machine_name = lambda: name
        env.set_machine_id(self.V, "m-" + name)

    def test_17_two_fields_no_conflict_history_both(self):
        self.machine("boss-pc")
        t0 = turn.start(self.V, "sid-boss", "記帳")["turn"]
        mid = money.add(self.V, t0, "收", amount="120000", due="2026-11-30", entities=["王先生"], text="尾款")[0]["id"]
        boss = streams.own_file(self.V, "money")
        seen = boss.read_bytes()
        t1 = turn.start(self.V, "sid-boss", "改到期")["turn"]
        money.edit(self.V, mid, t1, due="2026-12-10")
        boss_now = boss.read_bytes()
        boss.write_bytes(seen)
        self.machine("wang-laptop")
        t2 = turn.start(self.V, "sid-wang", "改備註")["turn"]
        money.edit(self.V, mid, t2, note="年底獎金下來再付")
        boss.write_bytes(boss_now)
        self.assertEqual(streams.conflicts_of(self.V, "money"), [])
        it = money.get(self.V, mid)
        self.assertEqual((it["due"], it["note"]), ("2026-12-10", "年底獎金下來再付"))
        self.assertTrue({t1, t2} <= {h["turn"] for h in it["history"]})


class Extract(MoneyBase):
    """製卡抽錢（驗收 20、21）：read 多 references/money.md、money_fp。"""

    def card(self):
        from kb._lib import cards
        path = E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王"])
        front = cards.parse_front((self.V / path).read_text(encoding="utf-8"))
        return front["編號"]

    def test_read_list_by_mode(self):
        from kb._lib import batches
        on = batches.read_list("cards", (), {"money_mode": "on", "fields": {}})
        self.assertTrue(any(p.endswith("references/money.md") for p in on))
        for mode in ("off", "spoken"):
            got = batches.read_list("agenda", (), {"money_mode": mode, "fields": {}})
            self.assertFalse(any(p.endswith("references/money.md") for p in got), mode)
        fields = batches.read_list("cards", (), {"money_mode": "spoken", "fields": {"產品": [{"field": "售價"}]}})
        self.assertTrue(any(p.endswith("references/money.md") for p in fields))

    def test_scanned_and_unscanned(self):
        fid = self.card()
        self.assertIn(fid, [c["id"] for c in money.unscanned(self.V)["money_unscanned"]])
        self.kb("money", "scanned", fid)
        entry = next(e for e in inventory.load(self.V)["entries"] if e["id"] == fid)
        self.assertTrue(entry.get("money_fp"))
        self.assertNotIn(fid, [c["id"] for c in money.unscanned(self.V)["money_unscanned"]])

    def test_spoken_scan_relisted_when_on(self):
        fid = self.card()
        self.set_mode("spoken")
        write_profile(self.V, fields=[dict(f) for f in FIELDS])
        self.kb("money", "scanned", fid)
        self.assertNotIn(fid, [c["id"] for c in money.unscanned(self.V)["money_unscanned"]])
        self.set_mode("on")
        self.assertIn(fid, [c["id"] for c in money.unscanned(self.V)["money_unscanned"]])

    def test_off_without_fields_lists_nothing(self):
        self.card()
        write_profile(self.V, fields=[], money=money_row("off"))
        self.assertEqual(money.unscanned(self.V)["money_unscanned"], [])

    def test_collect_merges_into_agenda_batch(self):
        from kb._lib import cards, sources
        fid = self.card()
        from kb._lib import agenda
        agenda.mark_scanned(self.V, fid, self.t)
        out = cards.collect(self.V, sources.load(self.V))
        self.assertIn(fid, [c["id"] for c in out["money_unscanned"]])
        self.assertIn(fid, [c["id"] for c in out["agenda_unscanned"]])  # 跟日程的待抽同一批做

    def test_tell_lines(self):
        fid = self.card()
        self.add("--dir", "付", "--amount", "3000", "--entity", "信義王", "--card", fid, "--text", "進貨")
        self.assertTrue(money.tell_lines(self.V, self.t)[0].startswith("我從檔案記了 1 筆帳："))
        self.assertTrue(any(x.startswith("我從檔案記了 1 筆帳：") for x in self.kbj("asks")["tell"]))  # 回答末尾（plan.tell）

    def test_purge_card_drops_inferred_keeps_said(self):
        fid = self.card()
        a = self.add("--dir", "付", "--amount", "3000", "--entity", "信義王", "--card", fid, "--text", "進貨")["item"]["id"]
        b = self.add("--dir", "收", "--amount", "500", "--entity", "信義王", "--text", "訂金")["item"]["id"]
        self.kb("money", "attach", b, "--card", fid)
        n = money.purge_cards(self.V, {fid}, self.t)
        self.assertEqual(n, 2)
        ids = {i["id"]: i for i in money.load(self.V)["items"]}
        self.assertNotIn(a, ids)
        self.assertEqual(ids[b]["cards"], [])


class Unit(MoneyBase):
    def test_parse_item(self):
        self.assertEqual(money.parse_item("精華液 -2瓶@1,800在北店"), ("精華液", "-2", "瓶", "1,800", "北店"))
        self.assertEqual(money.parse_item("益生菌 +2箱"), ("益生菌", "+2", "箱", None, None))
        self.assertEqual(money.parse_item("益生菌 -2 在北店"), ("益生菌", "-2", None, None, "北店"))
        with self.assertRaises(money.MoneyRefused):
            money.parse_item("精華液")


class UnitsBase(MoneyBase):
    def live(self):
        return [i for i in money.load(self.V)["items"] if i["status"] != "cancelled"]

    def lines_of(self, name):
        return [(ln["qty"], ln.get("unit")) for i in self.live() for ln in i["lines"] if ln["entity"] == name]

    def buy(self, item, code=0):
        args = ("--dir", "付", "--amount", "100", "--entity", "文具店", "--item", item, "--new")
        if code:
            return self.kb("money", "add", *args, code=code)
        return self.add(*args)


class Units6(UnitsBase):
    """驗收 6（D-344 與 11-09 補）：第九節有基本單位（產品：安全庫存、每箱的單位是瓶）。品項照她講的存 qty、unit，算的時候才換；
    換不到同一組的單位寫入時退回、不寫。"""

    def test_6_pack_stored_as_said_stock_converts(self):
        out = self.buy("益生菌 +2箱")
        self.assertEqual((out["item"]["lines"][0]["qty"], out["item"]["lines"][0]["unit"]), (2, "箱"))
        self.assertIn("益生菌 +2 箱（48 瓶）", out["tell"])
        out = self.buy("益生菌 +3瓶")
        self.assertEqual((out["item"]["lines"][0]["qty"], out["item"]["lines"][0]["unit"]), (3, "瓶"))
        self.assertIn("益生菌 +3 瓶", out["tell"])
        out = self.buy("益生菌 +3")
        self.assertEqual((out["item"]["lines"][0]["qty"], out["item"]["lines"][0]["unit"]), (3, ""))
        self.assertIn("益生菌 +3 瓶", out["tell"])  # 沒寫單位算基本單位
        st = money.stock(self.V, "益生菌")["products"][0]
        self.assertEqual((st["total"], st["unit"], st["apart"], st["text"]), (54, "瓶", [], "54 瓶"))

    def test_6_other_unit_after_base_refused_profile_first(self):
        self.buy("膠囊 +2瓶")
        r = self.buy("膠囊 +2箱", code=3)
        self.assertIn("kb entity field 膠囊 每箱=", r.stdout)
        self.assertNotIn("kb profile add", r.stdout)  # 第九節已有每箱
        self.assertIn("瓶", r.stdout)
        self.assertIn("一箱幾瓶", r.stdout)  # 第 4 輪 #17：第九節的每箱（單位瓶）看得出箱大，直接問
        self.assertIn("kb entity field 膠囊 每箱=<整數> --said", r.stdout)
        r = self.buy("膠囊 +2盒", code=3)
        add = r.stdout.index("kb profile add 數字欄 型別=產品 欄名=每<大的> 單位=<小的>")
        self.assertLess(add, r.stdout.index("kb entity field 膠囊 每<大的>=<整數> --said"))  # #16：先 profile add 再 entity field
        self.assertIn("盒、瓶哪個大", r.stdout)  # 第 4 輪 #17：大小不知道讓 AI 問她，不猜
        self.assertNotIn("每盒", r.stdout)
        self.assertEqual(self.lines_of("膠囊"), [(2, "瓶")])

    def test_6_one_unit_only_written_shown_apart(self):
        self.buy("膠囊 +2箱")  # 只用一種單位：照記不問
        self.assertEqual(self.lines_of("膠囊"), [(2, "箱")])
        st = money.stock(self.V, "膠囊")["products"][0]
        self.assertEqual((st["total"], st["unit"], st["text"]), (2, "箱", "2 箱（不知道一箱幾瓶）"))
        self.buy("膠囊 -1箱")
        self.assertEqual(money.stock(self.V, "膠囊")["products"][0]["total"], 1)
        self.buy("膠囊 -1瓶")  # 第 4 輪 #20：基本單位當作用過，照記、分開列
        self.assertEqual(money.stock(self.V, "膠囊")["products"][0]["text"], "-1 瓶＋1 箱（不知道一箱幾瓶）")

    def test_6_count_actual_same_rules(self):
        self.buy("益生菌 +50")
        out = self.kbj("money", "count", "益生菌", "--actual", "1箱")
        ln = out["item"]["lines"][0]
        self.assertEqual((out["diff"], ln["qty"], ln["unit"]), (-26, -26, "瓶"))  # 26 瓶換不成整箱：存基本單位
        self.assertIn("1 箱", out["tell"])  # #15：盤點也講她說的
        self.assertIn("24 瓶", out["tell"])
        out = self.kbj("money", "count", "益生菌", "--actual", "2箱")
        ln = out["item"]["lines"][0]
        self.assertEqual((ln["qty"], ln["unit"]), (1, "箱"))  # 差 24 瓶剛好一箱：存她講的單位
        self.assertEqual(money.stock(self.V, "益生菌")["products"][0]["total"], 48)
        self.buy("膠囊 +3瓶")
        self.kb("money", "count", "膠囊", "--actual", "2箱", code=3)

    def test_6_unit_price_and_margin_convert(self):
        self.kb("entity", "field", "精華液", "每箱=10", "--said")
        self.add("--dir", "收", "--amount", "18000", "--entity", "李小姐", "--item", "精華液 -1箱")
        self.add("--dir", "收", "--amount", "100", "--entity", "王先生", "--item", "益生菌 -1箱@960", "--item", "精華液 -2瓶@1800")
        got = {p["name"]: p for p in money.summary(self.V, "2000-01-01", "2100-01-01")["products"]}
        self.assertEqual((got["精華液"]["qty"], got["精華液"]["unit"], got["精華液"]["margin"]), (12, "瓶", 7200))
        self.assertEqual((got["益生菌"]["qty"], got["益生菌"]["amount"]), (24, 960))  # 單價是她講那單位（箱）的價

    def test_6_split_listed_when_field_removed(self):
        self.kb("entity", "field", "精華液", "每箱=24", "--said")
        self.buy("精華液 +2箱")
        self.buy("精華液 +12瓶")
        ents = entities.load(self.V)["entities"]
        for e in ents:
            if e["name"] == "精華液":
                e.pop("欄:每箱", None)
                e["欄:安全庫存"] = {"value": 20, "from": "said"}
        E.put_entities(self.V, ents)
        st = money.stock(self.V, "精華液")["products"][0]
        self.assertEqual((st["total"], st["unit"]), (12, "瓶"))
        self.assertEqual([(a["qty"], a["unit"]) for a in st["apart"]], [(2, "箱")])
        self.assertEqual(st["text"], "12 瓶＋2 箱（不知道一箱幾瓶）")
        low = money.low_stock(self.V, ["精華液"])
        self.assertEqual((low[0]["stock"], low[0]["text"]), (12, "12 瓶＋2 箱（不知道一箱幾瓶）"))
        self.assertIn("庫存 12 瓶＋2 箱（不知道一箱幾瓶）", self.kb("lookup", "精華液").stdout)
        self.assertIn("精華液 12 瓶＋2 箱（不知道一箱幾瓶）", self.kb("money", "stock", "精華液").stdout)
        self.assertIn("精華液 +2 箱（不知道一箱幾瓶）", self.kb("money", "list").stdout)
        # 第 4 輪 #20、#21：已經分開列的，再記用過的單位（含基本單位）照記，同一筆的收款也不擋；只有沒用過的新單位退回
        self.buy("精華液 -1瓶")
        self.add("--dir", "收", "--amount", "1800", "--entity", "李小姐", "--item", "精華液 -1箱")
        self.assertEqual(money.stock(self.V, "精華液")["products"][0]["text"], "11 瓶＋1 箱（不知道一箱幾瓶）")
        self.buy("精華液 +1盒", code=3)


class Units6NoSection9(UnitsBase):
    """驗收 6（D-344 補）：第九節什麼都沒設的店：照她講的記；各單位分開，換不到同一組的退回。"""

    def setUp(self):
        super().setUp()
        write_profile(self.V, fields=[], money=money_row("on"))

    def test_6_same_unit_ok_other_refused(self):
        self.buy("精華液 +2瓶")
        self.buy("精華液 +3瓶")
        r = self.buy("精華液 +2箱", code=3)
        add = r.stdout.index("kb profile add 數字欄 型別=產品 欄名=每<大的> 單位=<小的>")  # 第 4 輪 #17：大小讓 AI 問她
        field = r.stdout.index("kb entity field 精華液 每<大的>=<整數> --said")
        self.assertLess(add, field)
        self.assertEqual(self.lines_of("精華液"), [(2, "瓶"), (3, "瓶")])  # 不寫
        st = money.stock(self.V, "精華液")["products"][0]
        self.assertEqual((st["total"], st["unit"]), (5, "瓶"))
        self.assertIn("庫存 5 瓶", self.kb("lookup", "精華液").stdout)
        self.assertIn("精華液 5 瓶", self.kb("money", "stock", "精華液").stdout)

    def test_6_11_no_unit_first_then_box_refused(self):
        mid = self.buy("精華液 +3")["item"]["id"]
        r = self.buy("精華液 +2箱", code=3)
        self.assertIn("kb money edit", r.stdout)
        self.assertIn(mid, r.stdout)
        self.assertEqual(self.lines_of("精華液"), [(3, "")])
        self.kb("money", "edit", mid, "--item", "精華液 +3箱")  # 她說那 3 是箱
        self.buy("精華液 +2箱")
        st = money.stock(self.V, "精華液")["products"][0]
        self.assertEqual((st["total"], st["unit"]), (5, "箱"))

    def test_6_no_unit_after_unit_refused(self):
        self.buy("精華液 +2瓶")
        r = self.buy("精華液 -1", code=3)
        self.assertIn("沒寫單位", r.stdout)

    def test_6_12_box_then_bottles_no_drift(self):
        self.buy("精華液 +2箱")
        self.buy("精華液 -24瓶", code=3)
        self.kb("profile", "add", "數字欄", "型別=產品", "欄名=每箱", "單位=瓶")
        self.kb("entity", "field", "精華液", "每箱=24", "--said")
        self.buy("精華液 -24瓶")
        st = money.stock(self.V, "精華液")["products"][0]
        self.assertEqual((st["total"], st["unit"], st["text"]), (24, "瓶", "24 瓶"))
        self.buy("精華液 -72瓶")
        self.assertEqual(money.stock(self.V, "精華液")["products"][0]["total"], -48)

    def test_6_12_base_is_box_bottles_exact(self):
        self.kb("profile", "add", "數字欄", "型別=產品", "欄名=安全庫存", "單位=箱")
        self.kb("profile", "add", "數字欄", "型別=產品", "欄名=每箱", "單位=瓶")
        self.kb("entity", "field", "精華液", "每箱=24", "--said")
        self.buy("精華液 +2箱")
        self.buy("精華液 -24瓶")
        st = money.stock(self.V, "精華液")["products"][0]
        self.assertEqual((st["total"], st["unit"]), (1, "箱"))
        for _ in range(3):
            self.buy("精華液 -8瓶")
        self.assertEqual(money.stock(self.V, "精華液")["products"][0]["total"], 0)

    def test_6_13_base_set_later_old_lines_follow(self):
        self.buy("精華液 +2箱")
        self.kb("profile", "add", "數字欄", "型別=產品", "欄名=安全庫存", "單位=瓶")
        st = money.stock(self.V, "精華液")["products"][0]
        self.assertEqual(st["text"], "2 箱（不知道一箱幾瓶）")
        self.assertEqual(money.low_stock(self.V, ["精華液"]), [])  # 換不了的不跟安全庫存比
        self.buy("精華液 +10瓶")  # 第 4 輪 #20：基本單位當作用過，照記；#13：不會悄悄 2+10
        self.assertEqual(money.stock(self.V, "精華液")["products"][0]["text"], "10 瓶＋2 箱（不知道一箱幾瓶）")
        self.kb("profile", "add", "數字欄", "型別=產品", "欄名=每箱", "單位=瓶")
        self.kb("entity", "field", "精華液", "每箱=24", "--said")
        st = money.stock(self.V, "精華液")["products"][0]
        self.assertEqual((st["total"], st["unit"], st["apart"]), (58, "瓶", []))  # 舊帳照新欄算

    def test_6_14_pack_value_without_section9_not_silent(self):
        self.buy("益生菌 +2箱")  # 實體有每箱=24，第九節沒欄：沒有基本單位，照記
        self.assertEqual(money.stock(self.V, "益生菌")["products"][0]["text"], "2 箱")
        self.buy("益生菌 +24瓶", code=3)

    def test_6_two_units_in_one_add_refused(self):
        self.kb("money", "add", "--dir", "付", "--amount", "100", "--entity", "文具店", "--item", "精華液 +2瓶",
                "--item", "精華液 +1箱", code=3)
        self.assertEqual(self.live(), [])

    def test_6_edit_ignores_itself(self):
        mid = self.buy("精華液 +2箱")["item"]["id"]
        self.kb("money", "edit", mid, "--item", "精華液 +5瓶")
        self.assertEqual(self.lines_of("精華液"), [(5, "瓶")])

    def test_6_cancelled_not_counted(self):
        mid = self.buy("精華液 +2箱")["item"]["id"]
        self.kb("money", "cancel", mid)
        self.buy("精華液 +2瓶")

    def test_6_count_no_base(self):
        out = self.kbj("money", "count", "精華液", "--actual", "4瓶")
        self.assertEqual((out["diff"], out["item"]["lines"][0]["unit"]), (4, "瓶"))
        self.kb("money", "count", "精華液", "--actual", "1箱", code=3)


class Units4thRound(UnitsBase):
    """記帳2 測試第 4 輪（D-344 補之後）：#17 退回句只教「一箱幾瓶」設每<大的>=整數；#18 沒基本單位只講過一種單位那組照算毛利、
    多品項金額；#20、#21 只有沒用過又換不過去的新單位才退回；#23 地點格不吵、第九節拿掉每箱欄時實體上的值照用。"""
    places = True

    def no_section9(self, *fields):
        write_profile(self.V, fields=[field_row("產品", f, u) for f, u in fields], money=money_row("on", ["分店"]))

    def test_17_no_base_box_then_bottle_asks_big_holds_small(self):
        self.no_section9()
        self.buy("精華液 +2箱")
        r = self.buy("精華液 -24瓶", code=3)
        self.assertIn("kb profile add 數字欄 型別=產品 欄名=每<大的> 單位=<小的>", r.stdout)
        self.assertIn("kb entity field 精華液 每<大的>=<整數> --said", r.stdout)
        self.assertIn("瓶、箱哪個大", r.stdout)
        for bad in ("每瓶", "一瓶幾箱", "對調"):
            self.assertNotIn(bad, r.stdout)

    def test_17_base_is_box_asks_box_holds_bottles(self):
        self.no_section9(("安全庫存", "箱"), ("每箱", "瓶"))
        self.buy("精華液 +2箱")
        r = self.buy("精華液 -24瓶", code=3)
        self.assertIn("一箱幾瓶", r.stdout)
        self.assertIn("kb entity field 精華液 每箱=<整數> --said", r.stdout)
        self.assertNotIn("kb profile add", r.stdout)
        for bad in ("每瓶", "一瓶幾箱"):
            self.assertNotIn(bad, r.stdout)
        self.kb("entity", "field", "精華液", "每箱=24", "--said")
        self.buy("精華液 -24瓶")
        self.buy("精華液 -24瓶")
        st = money.stock(self.V, "精華液")["products"][0]
        self.assertEqual((st["total"], st["unit"], st["text"]), (0, "箱", "0 箱"))  # 沒有小數漂移

    def test_18_no_base_one_unit_margin_and_estimate(self):
        """報告 probe10：第九節只有售價、進價（沒有安全庫存、每…），只講瓶；ba794c22 是金額 7,200（估）、毛利 2,400。"""
        self.no_section9(("售價", "元"), ("進價", "元"))
        self.buy("精華液 +10瓶")
        self.buy("膠囊 +10瓶")
        self.add("--dir", "收", "--amount", "3600", "--entity", "李小姐", "--item", "精華液 -2瓶")
        self.add("--dir", "收", "--amount", "2700", "--entity", "李小姐", "--item", "精華液 -1瓶", "--item", "膠囊 -1瓶")
        self.add("--dir", "收", "--amount", "1800", "--entity", "李小姐", "--item", "精華液 -1瓶")
        got = {p["name"]: p for p in money.summary(self.V, "2000-01-01", "2100-01-01")["products"]}
        ess = got["精華液"]
        self.assertEqual((ess["qty"], ess["unit"], ess["amount"], ess["estimated"], ess["margin"], ess["text"]),
                         (4, "瓶", 7200, True, 2400, "4 瓶"))
        self.assertEqual((got["膠囊"]["amount"], got["膠囊"]["margin"]), (900, None))  # 膠囊沒進價

    def test_18_two_groups_without_base_still_apart(self):
        self.no_section9(("售價", "元"), ("進價", "元"))
        self.buy("精華液 +10瓶")
        d = money.load(self.V)  # 兩台各記一種（手造）
        it = dict(d["items"][0], id="m-zzzz9999", lines=[dict(d["items"][0]["lines"][0], qty=2, unit="箱")])
        d["items"].append(it)
        (Path(self.V) / money.MONEY_POSIX).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        self.add("--dir", "收", "--amount", "3600", "--entity", "李小姐", "--item", "精華液 -2瓶")
        p = money.summary(self.V, "2000-01-01", "2100-01-01")["products"][0]
        self.assertEqual((p["amount"], p["margin"]), (3600, None))  # 兩組換不了：不算毛利

    def test_18_unitless_safety_stock_compares_the_one_unit(self):
        self.no_section9(("安全庫存", ""))
        self.kb("entity", "field", "精華液", "安全庫存=5", "--said")
        self.buy("精華液 +3瓶")
        low = money.low_stock(self.V, ["精華液"])
        self.assertEqual([(x["stock"], x["unit"]) for x in low], [(3, "瓶")])

    def test_20_new_unit_refused_used_units_and_payment_ok(self):
        self.buy("膠囊 +2箱")  # 第一次講：照記，分開列（#19 由 AI 問）
        self.buy("膠囊 +3瓶")  # 基本單位當作用過
        out = self.add("--dir", "收", "--amount", "900", "--entity", "李小姐", "--item", "膠囊 -1箱")  # 收款不被擋
        self.assertEqual(out["item"]["amount"], 900)
        self.assertIn("（不知道一箱幾瓶）", out["tell"])
        self.buy("膠囊 +1", )  # 沒寫單位就是基本單位
        r = self.buy("膠囊 +1盒", code=3)  # 沒用過、又換不過去的新單位
        self.assertIn("盒", r.stdout)
        self.assertEqual(money.stock(self.V, "膠囊")["products"][0]["text"], "4 瓶＋1 箱（不知道一箱幾瓶）")

    def test_20_no_base_apart_records_used_units(self):
        self.no_section9()
        self.buy("精華液 +2瓶")
        d = money.load(self.V)  # 兩台各記一種（#21 競態也是這樣）
        d["items"].append(dict(d["items"][0], id="m-zzzz9998", lines=[dict(d["items"][0]["lines"][0], qty=1, unit="箱")]))
        (Path(self.V) / money.MONEY_POSIX).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        self.buy("精華液 +1箱")
        self.buy("精華液 +1瓶")
        self.buy("精華液 +1盒", code=3)
        self.buy("精華液 +1", code=3)  # 沒寫單位、又沒有基本單位：照舊問
        self.assertIn("3 瓶＋2 箱", money.stock(self.V, "精華液")["products"][0]["text"])

    def test_23a_unplaced_apart_not_in_every_place_cell(self):
        self.buy("膠囊 +2箱")  # 沒指定地點
        st = money.stock(self.V, "膠囊")["products"][0]
        self.assertEqual(st["text"], "2 箱（不知道一箱幾瓶）")
        self.assertEqual(st["places_text"], {"北店": "0 瓶", "南店": "0 瓶"})
        self.buy("膠囊 +1箱 在北店")
        st = money.stock(self.V, "膠囊")["products"][0]
        self.assertEqual(st["places_text"], {"北店": "1 箱（不知道一箱幾瓶）", "南店": "0 瓶"})

    def test_23b_pack_value_kept_when_section9_field_removed(self):
        self.buy("益生菌 +2箱 在北店")
        self.kb("profile", "remove", "數字欄", "型別=產品", "欄名=每箱")
        st = money.stock(self.V, "益生菌")["products"][0]
        self.assertEqual((st["total"], st["unit"], st["text"]), (48, "瓶", "48 瓶"))
        self.kb("profile", "add", "數字欄", "型別=產品", "欄名=每箱", "單位=瓶")
        self.kb("entity", "field", "益生菌", "每箱=", "--said")  # 她說清掉：就不知道了
        self.assertEqual(money.stock(self.V, "益生菌")["products"][0]["text"], "2 箱（不知道一箱幾瓶）")


if __name__ == "__main__":
    unittest.main()
