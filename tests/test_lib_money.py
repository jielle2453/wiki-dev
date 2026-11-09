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
        if me:  # None：這台還沒記是誰
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


# ---------- 記帳 3：帳頁、日程頁讀帳、卡底下的資料 ----------

from unittest import mock  # noqa: E402

from kb._lib import agenda, hand, renders  # noqa: E402

TODAY3 = "2026-11-23"


class PageBase(MoneyBase):
    """今天固定 2026-11-23（agenda._today），在行程裡呼叫 money。"""

    def setUp(self):
        super().setUp()
        self.p = mock.patch.object(agenda, "_today", return_value=TODAY3)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        super().tearDown()

    def put(self, dir_, amount=None, **kw):
        return money.add(self.V, self.t, dir_, amount, new=True, **kw)[0]

    def page(self, rel=money.MD_POSIX):
        return (Path(self.V) / rel).read_text(encoding="utf-8")


class Pages(PageBase):
    places = True

    def test_01_pages_written_and_old_year_untouched(self):
        self.put("收", "50000", due="2026-11-20", entities=["信義王"], text="第二期")
        self.put("收", "5000", date="2025-03-02", entities=["李小姐"])
        self.put("收", "3000", date="2026-10-30", entities=["李小姐"])
        top = self.page()
        self.assertTrue(top.startswith("# 帳\n（程式產生"))
        self.assertIn("## 還沒收付的\n- 11/20（五）收 50,000 [[案子/信義王/信義王|信義王]] 第二期　已過 3 天\n", top)
        for title in ("## 庫存", "## 每季（淨）", "## 每年"):
            self.assertIn(title, top)
        self.assertIn("- [[系統/帳/2026|2026]]　收 3,000｜付 0｜淨 3,000", top)
        self.assertIn("- [[系統/帳/2025|2025]]　收 5,000｜付 0｜淨 5,000", top)
        year = self.page(money.year_rel("2026"))
        self.assertIn("## 全年\n合計：收 3,000｜付 0｜淨 3,000", year)
        self.assertIn("## 10 月\n合計：收 3,000", year)
        self.assertIn("> [!note]- 明細（1 筆）\n> - 10/30（五）收 3,000 李小姐", year)
        old = Path(self.V) / money.year_rel("2025")
        os.utime(old, (1_000_000_000, 1_000_000_000))
        self.put("付", "800", date="2026-11-02", entities=["文具店"], text="文具")
        self.assertEqual(old.stat().st_mtime, 1_000_000_000, "只有今年的帳變了，去年那頁不重寫")
        self.assertIn("文具", self.page(money.year_rel("2026")))

    def test_02_month_by_paid_date_open_only_in_overview_estimate_margin(self):
        mid = self.put("收", "5000", due="2026-10-15", entities=["李小姐"], items=["精華液 -2", "膠囊 -1"], text="賣出")["id"]
        year = Path(self.V) / money.year_rel("2026")
        self.assertFalse(year.exists() and "賣出" in year.read_text(encoding="utf-8"), "還沒收的不進月份")
        self.assertIn("賣出", self.page())
        money.settle(self.V, mid, self.t, date="2026-12-01")
        text = self.page(money.year_rel("2026"))
        self.assertIn("## 12 月", text)
        self.assertNotIn("## 10 月", text)
        self.assertNotIn("賣出", self.page().split("## 庫存")[0], "收了就不在還沒收付的")
        self.assertIn("| 商品 | 賣出 | 金額 | 毛利（估） |", text)
        self.assertIn("4,000（估）", text)  # 多品項沒單價照售價分、標估
        self.assertIn("| 膠囊 | 1 | 1,000（估） |  |", text)  # 沒有進價毛利空著
        self.put("收", "1800", date="2026-09-03", items=["膠囊 -2@900"])
        sep = self.page(money.year_rel("2026")).split("## 9 月")[1]
        self.assertIn("| 商品 | 賣出 | 金額 |\n", sep, "整個月都沒有毛利就不出那欄")

    def test_03_quarter_table(self):
        self.put("收", "120000", date="2024-02-01")
        self.put("收", "158000", date="2025-02-01")
        self.put("收", "201000", date="2026-02-01")
        self.put("付", "1000", date="2026-11-21")
        top = self.page()
        self.assertIn("| 季 | 2024 | 2025 | 2026 |", top)
        self.assertIn("| 第一季 | 120,000 | 158,000 | 201,000 |", top)
        self.assertIn("| 第四季 |  |  | -1,000 |", top)
        self.assertIn("| 全年 | 120,000 | 158,000 | 200,000（到 11/21） |", top)

    def test_04_stock_table(self):
        self.put("付", "1000", entities=["文具店"], items=["益生菌 +20 在北店"])
        self.put("無", items=["益生菌 -5 在北店", "益生菌 +5 在南店"], text="調貨")
        self.put("付", "100", items=["膠囊 +3"])
        top = self.page()
        self.assertIn("| 商品 | 北店 | 南店 | 未指定 | 合計 |", top)
        self.assertIn("| 益生菌 | 15 瓶 | 5 瓶 | 0 瓶 | 20 瓶 |", top)
        self.assertIn("| 膠囊 | 0 瓶 | 0 瓶 | 3 瓶 | 3 瓶 |", top, "地點一筆都沒有也列 0；沒指定地點的進「未指定」（確認報告 #10）")


class PagesRemoved(PageBase):
    def test_removed_entity_marked_on_pages_and_home(self):
        """記帳 2 的「（已拿掉）」：帳頁、首頁上拿掉的實體名字照加註（名字留著、錢不刪）。"""
        from kb._lib import home
        self.put("收", "50000", due="2026-11-20", entities=["王先生"], text="第二期")
        self.put("收", "5000", date="2026-10-30", entities=["王先生"], items=["精華液 -2"])
        self.kb("entity", "remove", "王先生")
        self.kb("entity", "remove", "精華液")
        self.put("付", "1", date="2026-11-01", text="觸發重畫")
        self.assertIn("- 11/20（五）收 50,000 王先生（已拿掉） 第二期", self.page())
        year = self.page(money.year_rel("2026"))
        self.assertIn("收 5,000 王先生（已拿掉）（精華液（已拿掉） −2 瓶）", year)
        late = home.build(self.V, today=TODAY3)["todo"]["overdue"][0]
        self.assertIn("王先生（已拿掉）", late["text"])
        self.assertEqual(late["entities"], [])
        self.assertTrue(late["match"].startswith("- 11/20（五）收 50,000 王先生（已拿掉）"))


class RevertRedraws(MoneyBase):
    """測試報告中 #1：versions undo／revert 改回帳（流水檔）後，帳頁、年頁、日程頁照日程那樣重畫。"""

    def setUp(self):
        super().setUp()
        import datetime as dt
        from kb._lib import agenda
        agenda.render(self.V)
        money.render(self.V, hand={})  # 帳.md 在記帳那回合之前就有（kb init 建的）
        self.due = (dt.date.today() + dt.timedelta(days=2)).isoformat()
        self.year = str(dt.date.today().year)

    def page(self, rel):
        return (Path(self.V) / rel).read_text(encoding="utf-8")

    def test_undo_one_item_redraws(self):
        from kb._lib import agenda
        mid = self.add("--dir", "收", "--amount", "50000", "--due", self.due, "--entity", "李小姐", "--text", "尾款甲")["item"]["id"]
        self.add("--dir", "收", "--amount", "777", "--entity", "李小姐", "--text", "零售乙", "--new")
        self.assertIn("尾款甲", self.page(agenda.MD_POSIX))
        turn.start(self.V, None, "改回")
        got = json.loads(self.kb("versions", "items", "--turn", self.t, "--json").stdout)["items"]
        item = next(x for x in got if mid in json.dumps(x, ensure_ascii=False))
        r = self.kb("versions", "undo", item["item"], "--json")
        self.assertEqual(money.get(self.V, mid)["status"], "cancelled", r.stdout)
        self.assertNotIn("尾款甲", self.page(money.MD_POSIX))
        self.assertNotIn("尾款甲", self.page(agenda.MD_POSIX))
        self.assertIn("零售乙", self.page(money.year_rel(self.year)), "沒改回的那筆照留")

    def test_revert_turn_redraws(self):
        from kb._lib import agenda
        self.add("--dir", "收", "--amount", "50000", "--due", self.due, "--entity", "李小姐", "--text", "尾款甲")
        r = self.kb("versions", "revert")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual({i["status"] for i in money.load(self.V)["items"]}, {"cancelled"})  # 流水檔：退回＝收回
        self.assertNotIn("尾款甲", self.page(money.MD_POSIX))
        self.assertNotIn("尾款甲", self.page(agenda.MD_POSIX))


class PagesNoPlace(PageBase):
    def test_04b_no_place_type_only_total(self):
        self.put("付", "1000", items=["精華液 +20"])
        self.assertIn("| 商品 | 合計 |\n|---|---|\n| 精華液 | 20 瓶 |", self.page())


class PageHand(PageBase):
    """新定 1：刪掉明細一行＝取消、改日期、改金額照做；表與合計改了不算；看不懂的交給 AI（D-299）。"""

    def edit_page(self, rel, old, new):
        p = Path(self.V) / rel
        text = p.read_text(encoding="utf-8")
        self.assertIn(old, text)
        p.write_text(text.replace(old, new), encoding="utf-8", newline="\n")

    def test_05_hand_edits(self):
        a = self.put("收", "5000", date="2026-10-30", entities=["李小姐"])["id"]
        b = self.put("付", "800", date="2026-10-02", entities=["文具店"], text="文具")["id"]
        c = self.put("收", "50000", due="2026-11-20", entities=["王先生"], text="第二期")["id"]
        d = self.put("收", "300", date="2026-10-05", text="零售")["id"]
        y = money.year_rel("2026")
        self.edit_page(y, "> - 10/30（五）收 5,000 李小姐\n", "")
        self.edit_page(y, "10/2（五）付 800 文具店 文具", "10/3（五）付 800 文具店 文具")
        self.edit_page(y, "10/5（一）收 300 零售", "10/5（一）收 350 零售")
        self.edit_page(y, "合計：收 5,300", "合計：收 9,999")
        self.edit_page(money.MD_POSIX, "11/20（五）收 50,000", "11/28（五）收 50,000")
        self.edit_page(money.MD_POSIX, "## 庫存\n", "## 庫存\n下週要補貨\n")
        report = money.apply_hand(self.V, self.t)
        got = {i["id"]: i for i in money.load(self.V)["items"]}
        self.assertEqual(got[a]["status"], "cancelled")
        self.assertEqual(got[b]["date"], "2026-10-03")
        self.assertEqual(got[d]["amount"], 350)
        self.assertEqual(got[c]["due"], "2026-11-28")
        self.assertEqual(got[a]["history"][-1]["by"], "hand")
        self.assertEqual(len(report["applied"]), 4, report)
        self.assertEqual(report["carried"], [], "庫存段的字改了不算（數字是算的）")
        year = self.page(y)
        self.assertNotIn("9,999", year, "合計改了不算，下次照帳重算")
        self.assertNotIn("李小姐", year)

    def test_05c_review_fixes(self):
        """code-review：只認第一個日期與金額；別處的數字改了交給 AI；沒變不說改了；帳關著時帳頁的改動交給 AI；她那份沒存成要報出來。"""
        self.assertEqual(money.hand_change("> - 11/5（四）收 300 甲（拆自 10/30 那筆）", "> - 11/5（四）收 300 甲（拆自 10/31 那筆）"), None)
        self.assertEqual(money.hand_change("> - 11/5（四）收 300 甲", "> - 11/6（四）收 350 甲"), {"date": "11/6", "amount": "350"})
        self.assertEqual(money._merge_reports([{"applied": ["x"], "carried": [], "dropped": 0, "saved": "a"}, hand.KEEP_FAILED]),
                         hand.KEEP_FAILED)
        mid = self.put("收", "300", date="2026-10-05", text="零售")["id"]
        y = money.year_rel("2026")
        self.edit_page(y, "10/5（一）收 300 零售", "10/5（一）收 300.0 零售")
        report = money.apply_hand(self.V, self.t)
        self.assertEqual((report["applied"], money.get(self.V, mid)["amount"]), ([], 300), "金額沒變不說改了")
        self.set_mode("off")
        self.edit_page(y, "> - 10/5（一）收 300 零售\n", "")
        report = money.apply_hand(self.V, self.t)
        self.assertEqual(money.get(self.V, mid)["status"], "done", "帳關著：不照做")
        self.assertEqual(len(report["carried"]), 1)

    def test_05b_unrecognized_goes_to_ai(self):
        self.put("收", "50000", due="2026-11-20", entities=["王先生"], text="第二期")
        self.edit_page(money.MD_POSIX, "## 還沒收付的\n", "## 還沒收付的\n- 王先生說月底一起付\n")
        report = money.apply_hand(self.V, self.t)
        self.assertEqual(report["carried"], ["王先生說月底一起付"])
        rows = renders.unhanded(self.V)
        self.assertEqual([(rel, c["text"]) for rel, c in rows], [(money.MD_POSIX, "王先生說月底一起付")])
        self.assertIn("## 你加的（還沒處理）\n", self.page())
        self.assertEqual(hand.page_name(money.year_rel("2026")), "帳/2026.md")


class AgendaReadsMoney(PageBase):
    """D-273（2）、D-280：日程頁列帳的到期件、實體名字是連到卡實際位置的連結；刪掉那行＝取消；counts 算進去。"""

    def setUp(self):
        super().setUp()
        agenda.render(self.V, self.t)

    def md(self):
        return (Path(self.V) / agenda.MD_POSIX).read_text(encoding="utf-8")

    def test_07_links_follow_card_location(self):
        agenda.add(self.V, "會議", "2026-11-25", "見面", ["信義王"], self.t)
        self.assertIn("見面（[[案子/信義王/信義王|信義王]]）", self.md())
        (Path(self.V) / "案子" / "信義王").rename(Path(self.V) / "業主" / "信義王")  # 卡搬到別的夾（D-308 之後可以搬）
        agenda.render(self.V, self.t)
        self.assertIn("見面（[[業主/信義王/信義王|信義王]]）", self.md(), "卡搬過夾，連結跟著對")
        self.assertIsNone(agenda.apply_hand(self.V, self.t), "沒動的不算改")
        p = Path(self.V) / agenda.MD_POSIX
        p.write_text(self.md().replace("2026-11-25（週三）會議", "2026-11-26（週三）會議"), encoding="utf-8", newline="\n")
        agenda.apply_hand(self.V, self.t)
        self.assertEqual(agenda.load(self.V)["items"][0]["date"], "2026-11-26", "改了日期照舊被認出")

    def test_08_money_rows_counts_and_cancel(self):
        late = self.put("收", "50000", due="2026-11-20", entities=["信義王"], text="第二期")["id"]
        self.put("付", "3200", due="2026-11-23", text="文具")
        self.put("收", "1800", due="2026-11-27", entities=["李小姐"])
        self.put("收", "999", date="2026-11-01")
        md = self.md()
        self.assertIn("## 逾期\n- 2026-11-20（週五）收 50,000 [[案子/信義王/信義王|信義王]] 第二期\n", md)
        self.assertIn("## 今天\n- 2026-11-23（週一）付 3,200 文具\n", md)
        self.assertIn("- 2026-11-27（週五）收 1,800 李小姐", md)
        self.assertNotIn("999", md)
        self.assertEqual(agenda.counts(self.V, agenda.load(self.V)), {"overdue": 1, "today": 1, "upcoming": 1})
        p = Path(self.V) / agenda.MD_POSIX
        p.write_text(md.replace("- 2026-11-20（週五）收 50,000 [[案子/信義王/信義王|信義王]] 第二期\n", ""),
                     encoding="utf-8", newline="\n")
        report = agenda.apply_hand(self.V, self.t)
        self.assertEqual(money.get(self.V, late)["status"], "cancelled", report)
        self.assertNotIn("收 50,000", self.md())
        self.assertNotIn("第二期", self.page().split("## 庫存")[0], "帳頁跟著重畫")
        self.assertEqual(agenda.counts(self.V, agenda.load(self.V))["overdue"], 0)

    def test_08b_change_date_and_check_on_agenda_page(self):
        a = self.put("收", "1800", due="2026-11-27", entities=["李小姐"])["id"]
        b = self.put("付", "3200", due="2026-11-28", text="文具")["id"]
        p = Path(self.V) / agenda.MD_POSIX
        md = self.md().replace("2026-11-27（週五）收 1,800", "2026-12-01（週五）收 1,800")
        md = md.replace("- 2026-11-28（週六）付 3,200 文具", "- [x] 2026-11-28（週六）付 3,200 文具")
        p.write_text(md, encoding="utf-8", newline="\n")
        agenda.apply_hand(self.V, self.t)
        self.assertEqual(money.get(self.V, a)["due"], "2026-12-01")
        self.assertEqual((money.get(self.V, b)["status"], money.get(self.V, b)["date"]), ("done", TODAY3))


class Registered(PageBase):
    """驗收 6：帳頁與年頁在「程式產生的頁」各處登記（restore 在 test_lib_restore、init 在 test_scripts_init_cli、外掛在 JS 測試）。"""

    def test_06_renders_cli_purge_journal_items_refresh(self):
        from kb import renders_cli
        from kb._lib import items, journal, purge, refresh
        self.put("收", "5000", date="2026-10-30", entities=["李小姐"])
        y = money.year_rel("2026")
        self.assertEqual((renders_cli._page("系統\\帳.md"), renders_cli._page(y), renders_cli._page("系統/帳/x.md")),
                         (money.MD_POSIX, y, None))
        self.assertEqual(renders_cli._entry(y)[0], money.apply_hand)
        self.assertIn(money.MD_POSIX, [md for _j, md, _r in purge.MD_RENDERS])
        self.assertEqual(journal.changed_text([{"path": money.MONEY_POSIX}, {"path": money.MD_POSIX}, {"path": y}]), "帳")
        self.assertEqual((items.derived_from(money.MD_POSIX), items.derived_from(y), items.derived_from("01 案子/a/a.md")),
                         (money.MONEY_POSIX, money.MONEY_POSIX, False))
        for rel in (money.MD_POSIX, y):
            (Path(self.V) / rel).write_text("被 pull 蓋掉的舊版\n", encoding="utf-8")
        done = refresh._render_pages(self.V, self.t)
        self.assertIn(money.MD_POSIX, done)
        self.assertIn("10/30（五）收 5,000", self.page(y), "pull 之後重畫（D-293），不當成手改")
        self.assertEqual(renders.carried(self.V, money.MD_POSIX), [])

    def test_06b_kb_renders_apply_year_page(self):
        mid = self.put("收", "5000", date="2026-10-30", entities=["李小姐"])["id"]
        y = money.year_rel("2026")
        p = Path(self.V) / y
        p.write_text(self.page(y).replace("> - 10/30（五）收 5,000 李小姐\n", ""), encoding="utf-8", newline="\n")
        out = self.kbj("renders", "apply", y)
        self.assertEqual(out["page"], y)
        self.assertEqual(len(out["applied"]), 1)
        self.assertEqual(money.get(self.V, mid)["status"], "cancelled")

    def test_06c_purge_old_year_page_from_stream(self):
        """年頁的舊版：帳是流水檔，沒有整份舊版可重畫，派生頁的舊版拿掉（同日程）。"""
        from kb._lib import purge
        files = Path(self.tmp) / "files"
        (files / "系統" / "帳").mkdir(parents=True)
        (files / "系統" / "帳" / "2026.md").write_text("# 帳 2026\n舊的\n", encoding="utf-8")
        rows = [{"path": money.MONEY_POSIX, "stream": True}, {"path": "系統/帳/2026.md"}]
        counts = {"backups": 0, "left": {"backups": 0}}
        state = {}
        purge._scrub_md(self.V, files, rows, lambda t: t, counts, {}, state)
        self.assertFalse((files / "系統" / "帳" / "2026.md").exists())
        self.assertEqual(rows[1]["action"], "purged")


class Panel(PageBase):
    """驗收 10：kb entity panel（D-340）：日程只有全隊的＋我的、帳的合計與最近幾筆；商品給各店庫存；分店給那店的庫存。"""
    places = True

    def panel(self, name):
        from kb import entity
        return entity.panel_data(self.V, name, today=TODAY3)

    def test_10_customer(self):
        agenda.add(self.V, "會議", "2026-11-25", "見李小姐", ["李小姐"], self.t)
        agenda.add(self.V, "到期", "2026-11-01", "寄目錄", ["李小姐"], self.t)
        self.put("收", "5000", date="2026-10-30", entities=["李小姐"], items=["精華液 -2 在北店", "膠囊 -1 在北店"])
        self.put("收", "1800", due="2026-11-20", entities=["李小姐"], text="月底付另一半")
        got = self.panel("李小姐")
        self.assertEqual((got["entity"], got["type"], got["stock"]), ("李小姐", "業主", None))
        self.assertEqual([a["text"] for a in got["agenda"]], ["寄目錄", "見李小姐"])
        self.assertEqual(got["agenda"][0]["line"], "11/1（日）到期：寄目錄（已過 22 天）")
        self.assertTrue(got["agenda"][0]["late"])
        self.assertEqual(got["agenda"][1]["page"], "系統/日程.md")
        m = got["money"]
        self.assertEqual((m["in"], m["open_in"], m["total_n"]), (5000, 1800, 1))
        self.assertEqual(m["head"], "累計收 5,000｜未收 1,800")
        self.assertEqual(m["open"][0]["line"], "未收 1,800 月底付另一半（到期 11/20，已過 3 天）")
        self.assertEqual((m["open"][0]["page"], m["open"][0]["match"][:17]), ("系統/帳.md", "- 11/20（五）收 1,800"))
        self.assertEqual(m["recent"][0]["line"], "10/30（五）收 5,000 精華液 ×2、膠囊 ×1，北店")
        self.assertEqual(m["recent"][0]["page"], money.year_rel("2026"))
        self.assertTrue(m["recent"][0]["match"].startswith("> - 10/30（五）收 5,000"))

    def test_10b_product_and_place(self):
        self.put("付", "1000", entities=["文具店"], items=["精華液 +20 在北店", "精華液 +5 在南店"])
        self.put("收", "3600", date="2026-11-02", entities=["李小姐"], items=["精華液 -2 在北店"])
        ess = self.panel("精華液")
        self.assertEqual(ess["stock"]["places"], {"北店": 18, "南店": 5})
        self.assertEqual(ess["money"]["head"], "庫存 23 瓶（北店 18、南店 5）｜賣出累計 2 瓶")
        north = self.panel("北店")
        self.assertEqual([(p["name"], p["places"]) for p in north["stock"]["products"]], [("精華液", {"北店": 18})])
        self.assertEqual(north["stock"]["line"], "庫存：精華液 18 瓶")

    def test_10c_nothing_and_whose(self):
        got = self.panel("王先生")
        self.assertEqual((got["agenda"], got["money"], got["stock"]), ([], None, None))
        self.team(me="小王")
        agenda.add(self.V, "提醒", "2026-11-25", "小美自己的事", ["王先生"], self.t, whose="老闆")
        agenda.add(self.V, "提醒", "2026-11-26", "全隊的事", ["王先生"], self.t)
        self.assertEqual([a["text"] for a in self.panel("王先生")["agenda"]], ["全隊的事"], "別人的個人事不在小王那台")
        env.set_person(self.V, "老闆")
        self.assertEqual(len(self.panel("王先生")["agenda"]), 2)

    def test_10d_cli_json_read_only(self):
        self.put("收", "1800", due="2026-11-20", entities=["李小姐"])
        before = sorted(p.name for p in (Path(self.V) / ".system" / "versions").iterdir())
        out = self.kbj("entity", "panel", "李小姐")
        self.assertEqual(set(out), {"entity", "type", "agenda", "money", "stock"})
        self.assertEqual(out["money"]["open_in"], 1800)
        self.assertEqual(sorted(p.name for p in (Path(self.V) / ".system" / "versions").iterdir()), before, "唯讀，不開回合")
        self.kb("entity", "panel", "沒有這個人", "--json", code=3)


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
    """驗收 6（D-344 與 11-09 補、再補）：第九節有基本單位（產品：安全庫存、每箱的單位是瓶）。品項照她講的存 qty、unit，算的時候才換；
    換不到同一組的單位照記、分開列，成功句帶「（不知道一箱幾瓶）」、unit_ask 教 AI 問一次；盤點換不了才退回。"""

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

    def test_6_other_unit_after_base_written_with_ask(self):
        self.buy("膠囊 +2瓶")
        self.assertNotIn("unit_ask", self.buy("膠囊 +1瓶"))  # 換得了的不問
        out = self.buy("膠囊 +2箱")  # 再補：不擋，照記、分開列
        self.assertIn("膠囊 +2 箱（不知道一箱幾瓶）", out["tell"])
        ask = "\n".join(out["unit_ask"])
        self.assertNotIn("kb profile add", ask)  # 第九節已有每箱
        self.assertIn("一箱幾瓶", ask)  # 第 4 輪 #17：第九節的每箱（單位瓶）看得出箱大，直接問
        self.assertIn("kb entity field 膠囊 每箱=<整數> --said", ask)
        self.assertNotIn("照原句再記", ask)
        r = self.kb("money", "add", "--dir", "付", "--amount", "100", "--entity", "文具店", "--item", "膠囊 +2盒", "--new")
        add = r.stdout.index("kb profile add 數字欄 型別=產品 欄名=每<大的> 單位=<小的>")
        self.assertLess(add, r.stdout.index("kb entity field 膠囊 每<大的>=<整數> --said"))  # #16：先 profile add 再 entity field
        self.assertIn("盒、瓶哪個大", r.stdout)  # 第 4 輪 #17：大小不知道讓 AI 問她，不猜
        self.assertIn("膠囊 +2 盒（不知道盒跟瓶怎麼換）", r.stdout)  # 第 5 輪 #27：大小看不出不猜方向，跟庫存同一套字
        self.assertNotIn("每盒", r.stdout)
        self.assertEqual(self.lines_of("膠囊"), [(2, "瓶"), (1, "瓶"), (2, "箱"), (2, "盒")])
        st = money.stock(self.V, "膠囊")["products"][0]
        self.assertEqual((st["total"], st["unit"]), (3, "瓶"))
        self.assertEqual([(a["qty"], a["unit"]) for a in st["apart"]], [(2, "箱"), (2, "盒")])
        self.kb("entity", "field", "膠囊", "每箱=12", "--said")  # 答了：舊帳照新欄算
        self.assertEqual(money.stock(self.V, "膠囊")["products"][0]["total"], 27)

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
        r = self.kb("money", "count", "膠囊", "--actual", "2箱", code=3)  # 盤點例外：換不了照舊退回
        self.assertIn("一箱幾瓶", r.stdout)
        self.assertEqual(self.lines_of("膠囊"), [(3, "瓶")])

    def test_6_count_refused_when_already_apart(self):
        self.buy("膠囊 +3瓶")
        self.buy("膠囊 +1箱")  # 記帳照記、分開列
        r = self.kb("money", "count", "膠囊", "--actual", "5瓶", code=3)  # 盤點要對得上合計：換不成同一組就退回
        self.assertIn("一箱幾瓶", r.stdout)
        self.assertEqual(self.lines_of("膠囊"), [(3, "瓶"), (1, "箱")])
        self.kb("entity", "field", "膠囊", "每箱=12", "--said")
        out = self.kbj("money", "count", "膠囊", "--actual", "20瓶")
        self.assertEqual(out["diff"], 5)

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
        # 第 4 輪 #20、#21 與 D-344 再補：已經分開列的、沒用過的新單位都照記，同一筆的收款也不擋
        self.buy("精華液 -1瓶")
        self.add("--dir", "收", "--amount", "1800", "--entity", "李小姐", "--item", "精華液 -1箱")
        self.assertEqual(money.stock(self.V, "精華液")["products"][0]["text"], "11 瓶＋1 箱（不知道一箱幾瓶）")
        out = self.buy("精華液 +1盒")
        self.assertTrue(out["unit_ask"])
        self.assertEqual(money.stock(self.V, "精華液")["products"][0]["text"],
                         "11 瓶＋1 箱＋1 盒（不知道一箱幾瓶、盒跟瓶怎麼換）")


class Units6NoSection9(UnitsBase):
    """驗收 6（D-344 補、再補）：第九節什麼都沒設的店：照她講的記；各單位分開列，換不到同一組的照記、成功句與 unit_ask 教 AI 問一次。"""

    def setUp(self):
        super().setUp()
        write_profile(self.V, fields=[], money=money_row("on"))

    def test_6_same_unit_ok_other_written_apart(self):
        self.buy("精華液 +2瓶")
        out = self.buy("精華液 +3瓶")
        self.assertNotIn("unit_ask", out)  # 只用一種單位：照記不問
        out = self.buy("精華液 +2箱")  # 再補：不擋
        self.assertIn("精華液 +2 箱", out["tell"])
        self.assertIn("（不知道箱跟瓶怎麼換）", out["tell"])  # 第九節沒設：不知道哪個大，不猜（第 4 輪 #17）
        ask = "\n".join(out["unit_ask"])
        add = ask.index("kb profile add 數字欄 型別=產品 欄名=每<大的> 單位=<小的>")  # 第 4 輪 #17：大小讓 AI 問她
        self.assertLess(add, ask.index("kb entity field 精華液 每<大的>=<整數> --said"))
        self.assertIn("箱、瓶哪個大", ask)
        self.assertIn("不知道就放著", ask)
        self.assertEqual(self.lines_of("精華液"), [(2, "瓶"), (3, "瓶"), (2, "箱")])
        st = money.stock(self.V, "精華液")["products"][0]
        self.assertEqual((st["total"], st["unit"]), (5, "瓶"))
        self.assertEqual([(a["qty"], a["unit"]) for a in st["apart"]], [(2, "箱")])
        self.assertIn("庫存 5 瓶＋2 箱", self.kb("lookup", "精華液").stdout)
        self.assertIn("精華液 5 瓶＋2 箱", self.kb("money", "stock", "精華液").stdout)
        # 同一筆的收款照記
        out = self.add("--dir", "收", "--amount", "3600", "--entity", "李小姐", "--item", "精華液 -1箱")
        self.assertEqual((out["item"]["amount"], out["item"]["lines"][0]["unit"]), (3600, "箱"))
        self.assertTrue(out["unit_ask"])
        self.kb("profile", "add", "數字欄", "型別=產品", "欄名=每箱", "單位=瓶")  # 答了：舊帳照新欄算成一組
        self.kb("entity", "field", "精華液", "每箱=24", "--said")
        st = money.stock(self.V, "精華液")["products"][0]
        self.assertEqual((st["total"], st["unit"], st["apart"]), (29, "瓶", []))
        self.assertNotIn("unit_ask", self.buy("精華液 +1箱"))

    def test_6_11_no_unit_first_then_box_apart(self):
        mid = self.buy("精華液 +3")["item"]["id"]
        out = self.buy("精華液 +2箱")
        ask = "\n".join(out["unit_ask"])
        self.assertIn("kb money edit", ask)
        self.assertIn(mid, ask)
        self.assertEqual(self.lines_of("精華液"), [(3, ""), (2, "箱")])
        self.assertIn("3（沒寫單位）＋2 箱", money.stock(self.V, "精華液")["products"][0]["text"])
        self.kb("money", "edit", mid, "--item", "精華液 +3箱")  # 她說那 3 是箱
        st = money.stock(self.V, "精華液")["products"][0]
        self.assertEqual((st["total"], st["unit"], st["apart"]), (5, "箱", []))

    def test_6_no_unit_after_unit_written(self):
        self.buy("精華液 +2瓶")
        out = self.buy("精華液 -1")
        self.assertIn("沒寫單位", out["tell"])
        ask = "\n".join(out["unit_ask"])
        self.assertIn("是不是瓶", ask)
        self.assertIn(f"kb money edit {out['item']['id']}", ask)

    def test_6_12_box_then_bottles_no_drift(self):
        self.buy("精華液 +2箱")
        out = self.buy("精華液 -24瓶")  # 照記、分開列
        self.assertIn("（不知道瓶跟箱怎麼換）", out["tell"])
        self.kb("profile", "add", "數字欄", "型別=產品", "欄名=每箱", "單位=瓶")
        self.kb("entity", "field", "精華液", "每箱=24", "--said")
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
        self.assertEqual(st["text"], "2 箱（不知道箱跟瓶怎麼換）")  # 第 5 輪 #27：還沒有每箱欄，大小看不出
        self.assertEqual(money.low_stock(self.V, ["精華液"]), [])  # 換不了的不跟安全庫存比
        self.buy("精華液 +10瓶")  # 照記；#13：不會悄悄 2+10
        self.assertEqual(money.stock(self.V, "精華液")["products"][0]["text"], "10 瓶＋2 箱（不知道箱跟瓶怎麼換）")
        self.kb("profile", "add", "數字欄", "型別=產品", "欄名=每箱", "單位=瓶")
        self.kb("entity", "field", "精華液", "每箱=24", "--said")
        st = money.stock(self.V, "精華液")["products"][0]
        self.assertEqual((st["total"], st["unit"], st["apart"]), (58, "瓶", []))  # 舊帳照新欄算

    def test_6_14_pack_value_without_section9_not_silent(self):
        self.buy("益生菌 +2箱")  # 實體有每箱=24，第九節沒欄：沒有基本單位，照記
        self.assertEqual(money.stock(self.V, "益生菌")["products"][0]["text"], "2 箱")
        out = self.buy("益生菌 +24瓶")  # 照記、分開列，不會悄悄加成 3 箱
        self.assertIn("kb profile add 數字欄", "\n".join(out["unit_ask"]))
        self.assertIn("2 箱＋24 瓶", money.stock(self.V, "益生菌")["products"][0]["text"])

    def test_6_two_units_in_one_add_written(self):
        out = self.add("--dir", "付", "--amount", "100", "--entity", "文具店", "--item", "精華液 +2瓶", "--item", "精華液 +1箱",
                       "--new")
        self.assertEqual(self.lines_of("精華液"), [(2, "瓶"), (1, "箱")])
        self.assertEqual(len(out["unit_ask"]), 1)
        self.assertIn("（不知道箱跟瓶怎麼換）", out["tell"])

    def test_6_edit_ignores_itself(self):
        mid = self.buy("精華液 +2箱")["item"]["id"]
        out = self.kbj("money", "edit", mid, "--item", "精華液 +5瓶")
        self.assertEqual(self.lines_of("精華液"), [(5, "瓶")])
        self.assertNotIn("unit_ask", out)

    def test_6_edit_to_other_unit_asks(self):
        self.buy("精華液 +2瓶")
        mid = self.buy("精華液 +1瓶")["item"]["id"]
        out = self.kbj("money", "edit", mid, "--item", "精華液 +1箱")
        self.assertEqual(self.lines_of("精華液"), [(2, "瓶"), (1, "箱")])
        self.assertIn("（不知道箱跟瓶怎麼換）", out["tell"])
        self.assertTrue(out["unit_ask"])

    def test_6_cancelled_not_counted(self):
        mid = self.buy("精華液 +2箱")["item"]["id"]
        self.kb("money", "cancel", mid)
        self.assertNotIn("unit_ask", self.buy("精華液 +2瓶"))

    def test_6_count_no_base(self):
        out = self.kbj("money", "count", "精華液", "--actual", "4瓶")
        self.assertEqual((out["diff"], out["item"]["lines"][0]["unit"]), (4, "瓶"))
        r = self.kb("money", "count", "精華液", "--actual", "1箱", code=3)  # 盤點例外：換不了退回
        self.assertIn("箱、瓶哪個大", r.stdout)
        self.assertEqual(self.lines_of("精華液"), [(4, "瓶")])


class Units6Pages(UnitsBase):
    """驗收 6（D-344 與 11-09 補）接記帳 3：帳頁庫存、年頁明細與商品、panel、首頁、卡底下那段照同一套換算，換不了的分開列。"""

    def page(self, rel=None):
        return (Path(self.V) / (rel or money.MD_POSIX)).read_text(encoding="utf-8")

    def test_6_pages_and_panel_convert(self):
        self.buy("益生菌 +2箱")
        self.buy("益生菌 +3瓶")
        self.add("--dir", "收", "--amount", "2400", "--entity", "李小姐", "--item", "益生菌 -1箱")
        self.assertIn("27 瓶 |", self.page().split("## 庫存")[1])
        year = self.page(money.year_rel(money._today()[:4]))
        self.assertIn("益生菌 +2 箱（48 瓶）", year)
        self.assertIn("益生菌 −1 箱（24 瓶）", year)
        self.assertIn("| 24 | 2,400 |", year)  # 商品賣出換成基本單位
        got = self.kbj("entity", "panel", "益生菌")
        self.assertEqual(got["stock"]["line"], "庫存 27 瓶")
        self.assertIn("賣出累計 24 瓶", got["money"]["head"])
        self.assertTrue(any("益生菌 ×1 箱" in r["line"] for r in got["money"]["recent"]))  # 卡底下那段：她講的單位

    def test_6_no_section9_pages_unitless_and_said(self):
        write_profile(self.V, fields=[], money=money_row("on"))
        self.buy("精華液 +2瓶")
        self.buy("精華液 +3瓶")
        self.assertIn("5 瓶 |", self.page().split("## 庫存")[1])
        self.assertIn("精華液 +3 瓶", self.page(money.year_rel(money._today()[:4])))
        self.assertEqual(self.kbj("entity", "panel", "精華液")["stock"]["line"], "庫存 5 瓶")

    def test_6_split_shown_everywhere(self):
        from kb._lib import home
        self.kb("entity", "field", "精華液", "每箱=24", "--said")
        self.buy("精華液 +2箱")
        self.buy("精華液 +12瓶")
        ents = entities.load(self.V)["entities"]
        for e in ents:
            if e["name"] == "精華液":
                e.pop("欄:每箱", None)
                e["欄:安全庫存"] = {"value": 20, "from": "said"}
        E.put_entities(self.V, ents)
        money.render(self.V)
        split = "12 瓶＋2 箱（不知道一箱幾瓶）"
        self.assertIn(split, self.page().split("## 庫存")[1])
        self.assertIn("精華液 +2 箱（不知道一箱幾瓶）", self.page(money.year_rel(money._today()[:4])))
        self.assertEqual(self.kbj("entity", "panel", "精華液")["stock"]["line"], "庫存 " + split)
        todo = home.build(self.V)["todo"]["stock"]
        self.assertEqual([(s["entity"], s["stock"], s["text"]) for s in todo], [("精華液", 12, split)])

    def test_6_home_skips_unconvertible_only(self):
        from kb._lib import home
        self.buy("膠囊 +2箱")  # 第九節安全庫存是瓶、膠囊不知道一箱幾瓶：不跟安全庫存比
        ents = entities.load(self.V)["entities"]
        for e in ents:
            if e["name"] == "膠囊":
                e["欄:安全庫存"] = {"value": 5, "from": "said"}
        E.put_entities(self.V, ents)
        self.assertEqual(home.build(self.V)["todo"]["stock"], [])


class Units4thRound(UnitsBase):
    """記帳2 測試第 4 輪（D-344 補之後）：#17 問的那句只教「一箱幾瓶」設每<大的>=整數；#18 沒基本單位只講過一種單位那組照算毛利、
    多品項金額；#20、#21 與 D-344 再補：記帳不因單位擋，換不了的照記、分開列、問一次；#23 地點格不吵、第九節拿掉每箱欄時實體上的值照用。"""
    places = True

    def no_section9(self, *fields):
        write_profile(self.V, fields=[field_row("產品", f, u) for f, u in fields], money=money_row("on", ["分店"]))

    def test_17_no_base_box_then_bottle_asks_big_holds_small(self):
        self.no_section9()
        self.buy("精華液 +2箱")
        out = self.buy("精華液 -24瓶")  # 再補：照記
        said = out["tell"] + "\n" + "\n".join(out["unit_ask"])
        self.assertIn("kb profile add 數字欄 型別=產品 欄名=每<大的> 單位=<小的>", said)
        self.assertIn("kb entity field 精華液 每<大的>=<整數> --said", said)
        self.assertIn("瓶、箱哪個大", said)
        for bad in ("每瓶", "一瓶幾箱", "對調"):
            self.assertNotIn(bad, said)

    def test_17_base_is_box_asks_box_holds_bottles(self):
        self.no_section9(("安全庫存", "箱"), ("每箱", "瓶"))
        self.buy("精華液 +2箱")
        out = self.buy("精華液 -24瓶")  # 再補：照記
        said = out["tell"] + "\n" + "\n".join(out["unit_ask"])
        self.assertIn("24 瓶（不知道一箱幾瓶）", out["tell"])  # 第九節看得出箱大
        self.assertIn("kb entity field 精華液 每箱=<整數> --said", said)
        self.assertNotIn("kb profile add", said)
        for bad in ("每瓶", "一瓶幾箱"):
            self.assertNotIn(bad, said)
        self.kb("entity", "field", "精華液", "每箱=24", "--said")
        self.assertNotIn("unit_ask", self.buy("精華液 -24瓶"))
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

    def test_20_new_unit_written_apart_payment_ok(self):
        self.buy("膠囊 +2箱")  # 第一次講：照記，分開列（#19 由 AI 問）
        self.buy("膠囊 +3瓶")  # 基本單位當作用過
        out = self.add("--dir", "收", "--amount", "900", "--entity", "李小姐", "--item", "膠囊 -1箱")  # 收款不被擋
        self.assertEqual(out["item"]["amount"], 900)
        self.assertIn("（不知道一箱幾瓶）", out["tell"])
        self.buy("膠囊 +1", )  # 沒寫單位就是基本單位
        out = self.buy("膠囊 +1盒")  # 沒用過、又換不過去的新單位：再補後也照記
        self.assertIn("盒", "\n".join(out["unit_ask"]))
        self.assertEqual(money.stock(self.V, "膠囊")["products"][0]["text"], "4 瓶＋1 箱＋1 盒（不知道一箱幾瓶、盒跟瓶怎麼換）")

    def test_20_no_base_apart_records_used_units(self):
        self.no_section9()
        self.buy("精華液 +2瓶")
        d = money.load(self.V)  # 兩台各記一種（#21 競態也是這樣）
        d["items"].append(dict(d["items"][0], id="m-zzzz9998", lines=[dict(d["items"][0]["lines"][0], qty=1, unit="箱")]))
        (Path(self.V) / money.MONEY_POSIX).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        self.buy("精華液 +1箱")
        self.buy("精華液 +1瓶")
        self.assertTrue(self.buy("精華液 +1盒")["unit_ask"])
        self.assertTrue(self.buy("精華液 +1")["unit_ask"])  # 沒寫單位、又沒有基本單位：照記、問一次
        text = money.stock(self.V, "精華液")["products"][0]["text"]
        for want in ("3 瓶", "2 箱", "1 盒", "1（沒寫單位）"):
            self.assertIn(want, text)

    def test_23a_unplaced_apart_not_in_every_place_cell(self):
        self.buy("膠囊 +2箱")  # 沒指定地點
        st = money.stock(self.V, "膠囊")["products"][0]
        self.assertEqual(st["text"], "2 箱（不知道一箱幾瓶）")
        self.assertEqual(st["places_text"], {"北店": "0 瓶", "南店": "0 瓶", "未指定": "2 箱（不知道一箱幾瓶）"})  # 確認報告 #10
        self.buy("膠囊 +1箱 在北店")
        st = money.stock(self.V, "膠囊")["products"][0]
        self.assertEqual(st["places_text"], {"北店": "1 箱（不知道一箱幾瓶）", "南店": "0 瓶", "未指定": "2 箱（不知道一箱幾瓶）"})

    def test_23b_pack_value_kept_when_section9_field_removed(self):
        self.buy("益生菌 +2箱 在北店")
        self.kb("profile", "remove", "數字欄", "型別=產品", "欄名=每箱")
        st = money.stock(self.V, "益生菌")["products"][0]
        self.assertEqual((st["total"], st["unit"], st["text"]), (48, "瓶", "48 瓶"))
        self.kb("profile", "add", "數字欄", "型別=產品", "欄名=每箱", "單位=瓶")
        self.kb("entity", "field", "益生菌", "每箱=", "--said")  # 她說清掉：就不知道了
        self.assertEqual(money.stock(self.V, "益生菌")["products"][0]["text"], "2 箱（不知道一箱幾瓶）")


class Units5thRound(UnitsBase):
    """記帳2 測試第 5 輪：#24 售價、進價看第九節那欄的單位（元這類錢照基本單位），換不到那個單位的毛利、估的金額不算；
    #25 盤點退回句一個單位問一次、跟 unit_ask 同一套；#27 大小看不出不猜方向；#31 淨值 0 的那組不顯示。"""

    def section9(self, *fields):
        write_profile(self.V, fields=[field_row("產品", f, u) for f, u in fields], money=money_row("on"))

    def products(self):
        return {p["name"]: p for p in money.summary(self.V, "2000-01-01", "2100-01-01")["products"]}

    def test_6_24_price_unit_not_convertible_no_margin(self):
        self.section9(("售價", "瓶"), ("進價", "瓶"), ("安全庫存", "箱"))  # 售價是一瓶的價，基本單位箱、沒有每箱
        self.buy("精華液 +10箱")
        self.add("--dir", "收", "--amount", "3600", "--entity", "李小姐", "--item", "精華液 -2箱")
        p = self.products()["精華液"]
        self.assertEqual((p["qty"], p["unit"], p["amount"], p["margin"]), (2, "箱", 3600, None))  # 不拿瓶價乘箱數
        self.add("--dir", "收", "--amount", "5000", "--entity", "李小姐", "--item", "精華液 -1箱", "--item", "膠囊 -1箱")
        got = self.products()
        self.assertEqual((got["精華液"]["amount"], got["精華液"]["missing"], got["膠囊"]["amount"]), (3600, 1, None))  # 估不出的那筆不估、其他照算（確認報告 #7）
        self.kb("profile", "add", "數字欄", "型別=產品", "欄名=每箱", "單位=瓶")
        self.kb("entity", "field", "精華液", "每箱=10", "--said")
        self.assertEqual(self.products()["精華液"]["margin"], 3 * 10 * 600)  # 換得了：一箱 10 瓶的價

    def test_6_24_no_base_only_box_price_per_bottle(self):
        self.section9(("售價", "瓶"), ("進價", "瓶"))  # 報告腳本 K：只講箱，售價是瓶的價
        self.buy("精華液 +10箱")
        self.add("--dir", "收", "--amount", "12000", "--entity", "李小姐", "--item", "精華液 -8箱@1500")
        p = self.products()["精華液"]
        self.assertEqual((p["qty"], p["unit"], p["amount"], p["margin"]), (8, "箱", 12000, None))

    def test_6_24_money_unit_is_base_price(self):
        self.section9(("售價", "元"), ("進價", "元/瓶"), ("安全庫存", "瓶"))  # 欄的單位是錢：照基本單位（現行為）
        self.add("--dir", "收", "--amount", "3600", "--entity", "李小姐", "--item", "精華液 -2瓶")
        self.assertEqual(self.products()["精華液"]["margin"], 1200)

    def test_6_25_count_refused_one_ask_same_as_unit_ask(self):
        ask = self.buy("膠囊 +2箱")["unit_ask"][0]
        self.buy("膠囊 +10瓶")
        r = self.kb("money", "count", "膠囊", "--actual", "3箱", code=3)
        self.assertIn(ask[:-len(money.ASK_TAIL)], r.stdout)  # 跟成功輸出的 unit_ask 同一套
        self.assertEqual(r.stdout.count("問她一次"), 1)
        self.assertNotIn("瓶、瓶", r.stdout)

    def test_6_25_count_no_base_one_ask(self):
        self.section9()
        self.buy("精華液 +2箱")
        self.buy("精華液 +5瓶")
        r = self.kb("money", "count", "精華液", "--actual", "3箱", code=3)
        self.assertEqual(r.stdout.count("哪個大"), 1)  # 不再「箱、瓶哪個大」「瓶、箱哪個大」兩條
        self.assertEqual(r.stdout.count("問她一次"), 1)

    def test_6_27_base_box_no_pack_field_no_direction_guess(self):
        self.section9(("安全庫存", "箱"))
        self.buy("膠囊 +3箱")
        out = self.buy("膠囊 -24瓶")
        self.assertIn("膠囊 −24 瓶（不知道瓶跟箱怎麼換）", out["tell"])
        st = money.stock(self.V, "膠囊")["products"][0]
        self.assertEqual(st["text"], "3 箱−24 瓶（不知道瓶跟箱怎麼換）")
        for said in (out["tell"], st["text"], "\n".join(out["unit_ask"])):
            self.assertNotIn("一瓶幾箱", said)
        self.kb("profile", "add", "數字欄", "型別=產品", "欄名=每箱", "單位=瓶")  # 看得出箱大才寫一箱幾瓶
        self.assertEqual(money.stock(self.V, "膠囊")["products"][0]["text"], "3 箱−24 瓶（不知道一箱幾瓶）")

    def test_6_31_zero_apart_group_not_shown(self):
        self.buy("膠囊 +36瓶")
        self.buy("膠囊 +1箱")
        self.buy("膠囊 -1箱")
        st = money.stock(self.V, "膠囊")["products"][0]
        self.assertEqual(st["text"], "36 瓶")
        self.assertIn("庫存 36 瓶", self.kb("lookup", "膠囊").stdout)
        self.assertNotIn("0 箱", self.kb("lookup", "膠囊").stdout)


if __name__ == "__main__":
    unittest.main()
