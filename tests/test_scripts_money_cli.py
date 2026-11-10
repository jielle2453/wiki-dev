"""kb money 黑箱（記帳 2 驗收 1～15、19、25）：記一筆、拆帳、重複、去重、單位、盤點、低庫存、分店與調貨、報帳、開關、
帳關著的口述與加總、改開補帳、改期列另一邊、區間、待處理、備份與工作日誌。"""
import datetime as dt
import json
import unittest

from tests.test_lib_money import MoneyBase
from kb._lib import journal, money, pending, statements, turn  # noqa: E402

TODAY = dt.date.today().isoformat()


class Add(MoneyBase):
    def test_1_add_stock_revert_streams(self):
        t = turn.start(self.V, None, "")["turn"]
        out = self.add("--dir", "收", "--amount", "5000", "--entity", "李小姐", "--item", "精華液 -2", "--item", "膠囊 -1",
                       "--text", "賣出")
        it = out["item"]
        self.assertEqual((it["status"], it["date"], it["dir"], it["amount"]), ("done", TODAY, "in", 5000))
        self.assertEqual([(ln["entity"], ln["qty"]) for ln in it["lines"]], [("精華液", -2), ("膠囊", -1)])
        self.assertTrue(it["id"].startswith("m-"))
        self.assertIn("收 5,000", out["tell"])
        self.assertEqual(self.kbj("money", "stock", "精華液")["products"][0]["total"], -2)
        self.assertTrue(any((self.V / ".system" / "streams" / "money").glob("*.jsonl")))
        self.assertIn(money.MONEY_POSIX, {r["path"] for r in turn.entries(self.V, t)})  # 驗收 25
        self.kb("versions", "revert")
        self.assertEqual([i for i in money.load(self.V)["items"] if i["status"] != "cancelled"], [])  # 退回新增＝收回欄
        self.assertEqual(money.stock(self.V)["products"], [])

    def test_25_journal_program_line(self):
        self.add("--dir", "收", "--amount", "5000", "--entity", "李小姐")
        progs = [r for m in journal.months(self.V) for r in journal.read_lines(self.V, m) if r.get("kind") == "program"]
        self.assertTrue(any("money add" in json.dumps(r, ensure_ascii=False) for r in progs))

    def test_2_open_and_unknown_amount(self):
        it = self.add("--due", "2026-11-30", "--dir", "收", "--amount", "120000", "--entity", "信義王")["item"]
        self.assertEqual((it["status"], it["due"]), ("open", "2026-11-30"))
        unknown = self.add("--due", "2026-11-30", "--dir", "收", "--entity", "王先生", "--text", "尾款")["item"]
        self.assertIsNone(unknown["amount"])
        r = self.kb("money", "settle", unknown["id"], code=3)
        self.assertIn("金額", r.stdout)
        r = self.kb("money", "add", "--dir", "收", "--entity", "王先生", "--text", "收錢", code=3)
        self.assertIn("金額", r.stdout)

    def test_3_settle_split_and_full(self):
        mid = self.add("--due", "2026-11-30", "--dir", "收", "--amount", "120000", "--entity", "信義王", "--text", "尾款")["item"]["id"]
        out = self.kbj("money", "settle", mid, "--amount", "100000", "--due", "2026-12-31")
        self.assertEqual((out["item"]["status"], out["item"]["amount"]), ("done", 100000))
        rest = out["split"]
        self.assertEqual((rest["status"], rest["amount"], rest["split_from"], rest["due"]), ("open", 20000, mid, "2026-12-31"))
        full = self.kbj("money", "settle", rest["id"])
        self.assertIsNone(full["split"])
        self.assertEqual(full["item"]["status"], "done")

    def test_4_repeat(self):
        mid = self.add("--repeat", "每月", "--due", "2026-11-10", "--dir", "付", "--amount", "3000", "--entity", "文具店",
                       "--text", "房租")["item"]["id"]
        out = self.kbj("money", "settle", mid, "--date", "2026-11-09")
        self.assertEqual(out["repeat"]["repeat_of"], mid)
        self.assertEqual((out["repeat"]["status"], out["repeat"]["amount"]), ("done", 3000))
        it = money.get(self.V, mid)
        self.assertEqual((it["status"], it["due"]), ("open", "2026-12-10"))

    def test_5_candidates_new_unsure_merge(self):
        a = self.add("--dir", "收", "--amount", "5000", "--date", "2026-10-30", "--entity", "李小姐")["item"]["id"]
        got = self.add("--dir", "收", "--amount", "5000", "--date", "2026-11-02", "--entity", "李小姐", code=3)
        self.assertEqual(got["refused"], "candidates")
        self.assertEqual([c["id"] for c in got["candidates"]], [a])
        b = self.add("--dir", "收", "--amount", "5000", "--date", "2026-11-02", "--entity", "李小姐", "--new")["item"]["id"]
        c = self.add("--dir", "收", "--amount", "5000", "--date", "2026-11-03", "--entity", "李小姐", "--new", "--unsure", a)
        dupes = [i for i in pending.load(self.V)["items"] if i["kind"] == "money_dupe" and i["status"] == "open"]
        self.assertEqual(len(dupes), 1)
        self.kb("money", "merge", a, b)
        self.kb("money", "merge", a, c["item"]["id"])
        live = [i for i in money.load(self.V)["items"] if i["status"] != "cancelled"]
        self.assertEqual([i["id"] for i in live], [a])
        o = self.add("--due", "2026-12-30", "--dir", "收", "--amount", "999", "--entity", "王先生")["item"]["id"]
        got = self.kbj("money", "candidates", "--dir", "收", "--amount", "100", "--entity", "王先生")
        self.assertEqual([(c["id"], c["open"]) for c in got["candidates"]], [(o, True)])  # 同實體同方向的未收也列

    def test_6_units(self):
        it = self.add("--dir", "付", "--amount", "100", "--entity", "文具店", "--item", "益生菌 +2箱")["item"]
        self.assertEqual((it["lines"][0]["qty"], it["lines"][0]["unit"]), (2, "箱"))
        self.assertEqual(self.kbj("money", "stock", "益生菌")["products"][0]["total"], 48)
        self.add("--dir", "付", "--amount", "100", "--entity", "文具店", "--item", "精華液 +3瓶", "--new")
        r = self.kb("money", "add", "--dir", "付", "--amount", "100", "--entity", "文具店", "--item", "精華液 +2箱", "--new")
        self.assertIn("精華液 +2 箱（不知道一箱幾瓶）", r.stdout)  # D-344 再補：不擋，照記、問一次
        self.assertIn("kb entity field 精華液 每箱=", r.stdout)
        out = self.add("--dir", "付", "--amount", "100", "--entity", "文具店", "--item", "精華液 +1箱", "--new")
        self.assertIn("kb entity field 精華液 每箱=<整數> --said", out["unit_ask"][0])
        self.kb("money", "count", "精華液", "--actual", "3瓶", code=3)  # 盤點例外：換不了退回

    def test_8_low_stock(self):
        self.add("--dir", "付", "--amount", "100", "--entity", "文具店", "--item", "精華液 +6", "--item", "膠囊 +6")
        out = self.add("--dir", "收", "--amount", "3600", "--entity", "李小姐", "--item", "精華液 -2", "--item", "膠囊 -2")
        self.assertEqual([(x["entity"], x["stock"], x["min"]) for x in out["low_stock"]], [("精華液", 4, 5)])
        out = self.add("--dir", "收", "--amount", "100", "--entity", "王先生", "--item", "膠囊 -1")
        self.assertNotIn("low_stock", out)


class Places(MoneyBase):
    places = True

    def test_7_count(self):
        self.add("--dir", "付", "--amount", "100", "--entity", "文具店", "--item", "益生菌 +12 在北店")
        out = self.kbj("money", "count", "益生菌", "--actual", "10", "--place", "北店")
        self.assertEqual((out["item"]["dir"], out["item"]["lines"][0]["qty"], out["item"]["lines"][0]["place"]), ("none", -2, "北店"))
        self.assertEqual(money.stock(self.V, "益生菌")["products"][0]["places"]["北店"], 10)

    def test_9_places_transfer_and_usual(self):
        it = self.add("--dir", "收", "--amount", "100", "--entity", "李小姐", "--item", "益生菌 -2 在北店")["item"]
        self.assertEqual(it["lines"][0]["place"], "北店")
        r = self.kb("money", "add", "--dir", "收", "--amount", "100", "--entity", "王先生", "--item", "益生菌 -2 在李小姐", code=3)
        self.assertIn("地點", r.stdout)
        before = money.stock(self.V, "益生菌")["products"][0]
        self.add("--dir", "無", "--item", "益生菌 -5 在北店", "--item", "益生菌 +5 在南店", "--text", "調貨")
        after = money.stock(self.V, "益生菌")["products"][0]
        self.assertEqual(before["total"], after["total"])
        self.assertEqual((after["places"]["北店"], after["places"]["南店"]), (before["places"]["北店"] - 5, 5))
        self.team()
        out = self.add("--dir", "收", "--amount", "800", "--entity", "王先生", "--item", "益生菌 -2", "--new")
        self.assertEqual(out["item"]["lines"][0]["place"], "北店")
        self.assertIn("北店", out["tell"])

    def test_9_no_place_types_ignored(self):
        self.set_mode("on", [])
        it = self.add("--dir", "收", "--amount", "100", "--entity", "李小姐", "--item", "益生菌 -2 在北店")["item"]
        self.assertIsNone(it["lines"][0]["place"])

    def test_10_advanced_by(self):
        self.team()
        out = self.add("--dir", "付", "--amount", "3200", "--advanced-by", "小王", "--entity", "文具店", "--text", "文具")
        mid = out["item"]["id"]
        self.assertEqual(out["item"]["status"], "open")
        self.assertEqual([i["id"] for i in self.kbj("money", "list", "--advanced-by", "小王")["items"]], [mid])
        self.assertEqual(self.kbj("money", "sum", "--from", "2026-01-01", "--to", "2026-12-31", "--advanced-by", "小王")["open_out"],
                         3200)
        done = self.kbj("money", "settle", mid, "--date", "2026-11-09")["item"]
        self.assertEqual((done["status"], done["date"]), ("done", "2026-11-09"))
        r = self.kb("money", "add", "--dir", "付", "--amount", "1", "--advanced-by", "阿貓", code=3)
        self.assertIn("成員", r.stdout)

    def test_10_single_user_refuses_advanced_by(self):
        r = self.kb("money", "add", "--dir", "付", "--amount", "1", "--advanced-by", "小王", code=3)
        self.assertIn("單人", r.stdout)


class Modes(MoneyBase):
    def test_11_off_and_spoken(self):
        self.set_mode("off")
        got = self.add("--dir", "收", "--amount", "5000", "--entity", "李小姐", code=3)
        self.assertEqual(got["refused"], "off")
        self.kbj("money", "list")
        self.assertEqual(self.kbj("money", "sum", "--from", "2026-01-01", "--to", "2026-12-31")["source"], "statements")
        self.set_mode("spoken")
        from tests import _entities as E
        from kb._lib import cards
        path = E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王"])
        fid = cards.parse_front((self.V / path).read_text(encoding="utf-8"))["編號"]
        got = self.add("--dir", "付", "--amount", "3000", "--entity", "信義王", "--card", fid, code=3)
        self.assertEqual(got["refused"], "spoken")
        self.add("--dir", "付", "--amount", "3000", "--entity", "信義王")

    def test_12_statements_money(self):
        self.set_mode("off")
        s = self.kbj("statement", "add", "--text", "幫公司收了王先生 5,000", "--entity", "王先生", "--money", "收", "5000")
        self.assertEqual(s["statement"]["money"], {"dir": "in", "amount": 5000, "ledger": None})
        bare = self.kbj("statement", "add", "--text", "今天收了 3,000", "--money", "收", "3000")
        self.assertEqual(bare["statement"]["entities"], [])
        self.kb("statement", "add", "--text", "今天天氣好", code=3)
        got = self.kbj("money", "sum", "--from", TODAY[:8] + "01", "--to", TODAY)
        self.assertEqual((got["source"], got["in"], len(got["items"])), ("statements", 8000, 2))
        listed = self.kbj("statement", "list", "--money")
        self.assertEqual(len(listed["statements"]), 2)

    def test_13_backfill(self):
        self.set_mode("off")
        sid = self.kbj("statement", "add", "--text", "幫公司收了王先生 5,000", "--entity", "王先生", "--money", "收",
                       "5000")["statement"]["id"]
        out = self.kbj("profile", "add", "記帳", "狀態=開")
        self.assertEqual(out["backfill"]["statements"], 1)
        rows = self.kbj("money", "backfill")["statements"]
        self.assertEqual([r["id"] for r in rows], [sid])
        it = self.add("--dir", "收", "--amount", "5000", "--entity", "王先生", "--from-statement", sid)["item"]
        self.assertEqual((it["origin"], it["date"]), ({"statement": sid}, TODAY))
        s = statements.find(statements.load(self.V), sid)
        self.assertEqual(s["money"]["ledger"], it["id"])
        self.assertEqual(self.kbj("money", "backfill")["statements"], [])
        sid2 = self.kbj("statement", "add", "--text", "又收了王先生 5,000", "--entity", "王先生", "--money", "收",
                        "5000")["statement"]["id"]
        got = self.add("--dir", "收", "--amount", "5000", "--entity", "王先生", "--from-statement", sid2, code=3)
        self.assertEqual(got["refused"], "candidates")


class Related(MoneyBase):
    @unittest.skip("#65 甲段：這條測的是已拿掉的畫面／連動（首頁、日程、帳頁、lookup、待處理），乙段隨本檔一起刪")
    def test_14_related_both_ways(self):
        aid = json.loads(self.kb("agenda", "add", "--kind", "到期", "--date", "2026-11-30", "--text", "交屋", "--entity", "信義王",
                                 "--json").stdout)["item"]["id"]
        mid = self.add("--due", "2026-11-30", "--dir", "收", "--amount", "120000", "--entity", "信義王", "--text", "尾款")["item"]["id"]
        self.assertIn("信義王還有一筆 11/30 到期的尾款 120,000", self.kb("agenda", "edit", aid, "--date", "2026-12-10").stdout)
        self.kb("agenda", "edit", aid, "--date", "2026-11-30")
        out = self.kbj("agenda", "edit", aid, "--date", "2026-12-10")
        self.assertEqual([m["id"] for m in out["related_money"]], [mid])
        self.kb("agenda", "edit", aid, "--date", "2026-11-30")
        out = self.kbj("money", "edit", mid, "--due", "2026-12-10")
        self.assertEqual([a["id"] for a in out["related_agenda"]], [aid])


class Asks(MoneyBase):
    @unittest.skip("#65 甲段：這條測的是已拿掉的畫面／連動（首頁、日程、帳頁、lookup、待處理），乙段隨本檔一起刪")
    def test_19_asks(self):
        from tests import _entities as E
        from kb._lib import cards
        path = E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王"])
        fid = cards.parse_front((self.V / path).read_text(encoding="utf-8"))["編號"]
        a = self.add("--dir", "收", "--amount", "5000", "--date", "2026-10-30", "--entity", "李小姐")["item"]["id"]
        b = self.add("--dir", "收", "--amount", "5000", "--date", "2026-10-30", "--entity", "李小姐", "--new", "--unsure", a)
        self.kb("money", "unsure", "--card", fid, "--text", "匯款單 3,000，看不出誰付誰")
        asks = self.kbj("asks", "--all")["asks"]
        dupe = next(x for x in asks if x["kind"] == "pending_money_dupe")
        yes = dupe["results"][0]
        self.assertTrue(any(f"money merge {a} {b['item']['id']}" in d for d in yes["do"]))
        unsure = next(x for x in asks if x["kind"] == "pending_money_unsure")
        self.assertTrue(any(fid in "".join(r["do"]) for r in unsure["results"]))


class ReviewFixes(MoneyBase):
    """code-review 修正：重開取消的已收付回到已收付、留的那筆取消了不併、重複要給到期日、--unsure 編號錯不寫、
    還沒收付的不能只改收付日、同一對 money_dupe 不論順序只開一件。"""

    def test_reopen_and_merge(self):
        a = self.add("--dir", "收", "--amount", "5000", "--date", "2026-10-30", "--entity", "李小姐")["item"]["id"]
        self.kb("money", "cancel", a)
        self.assertEqual(self.kbj("money", "reopen", a)["item"]["status"], "done")
        b = self.add("--dir", "收", "--amount", "5000", "--date", "2026-10-30", "--entity", "李小姐", "--new")["item"]["id"]
        self.kb("money", "cancel", a)
        self.kb("money", "merge", a, b, code=3)
        self.assertEqual(money.get(self.V, b)["status"], "done")

    def test_repeat_needs_due_and_edit_date_open(self):
        self.kb("money", "add", "--dir", "付", "--amount", "20000", "--entity", "文具店", "--repeat", "每月", code=3)
        o = self.add("--dir", "收", "--amount", "100", "--due", "2026-12-01", "--entity", "王先生")["item"]["id"]
        self.kb("money", "edit", o, "--date", "2026-11-03", code=3)

    def test_unsure_bad_id_writes_nothing_and_dupe_pair_once(self):
        self.kb("money", "add", "--dir", "收", "--amount", "5000", "--entity", "李小姐", "--new", "--unsure", "m-00000000", code=3)
        self.assertEqual(money.load(self.V)["items"], [])
        a = self.add("--dir", "收", "--amount", "5000", "--entity", "李小姐")["item"]["id"]
        b = self.add("--dir", "收", "--amount", "5000", "--entity", "李小姐", "--new", "--unsure", a)["item"]["id"]
        t = turn.current(self.V)["turn"]
        pending.add_money(self.V, "money_dupe", "x", t, data={"keep": b, "other": a})
        self.assertEqual(len([i for i in pending.load(self.V)["items"] if i["kind"] == "money_dupe"]), 1)


class SettleCard(MoneyBase):
    """測試報告中 #1：製卡助手 settle 一定帶 --card（讀到匯款單），出處記在收付的那筆。"""

    def test_settle_with_card(self):
        from tests import _entities as E
        from kb._lib import cards
        path = E.write_card(self.V, E.QUOTE, "信義王匯款單", ["信義王"])
        fid = cards.parse_front((self.V / path).read_text(encoding="utf-8"))["編號"]
        mid = self.add("--due", "2026-11-30", "--dir", "收", "--amount", "120000", "--entity", "信義王")["item"]["id"]
        out = self.kbj("money", "settle", mid, "--amount", "100000", "--card", fid)
        self.assertEqual(out["item"]["cards"], [fid])
        self.assertEqual(out["split"]["cards"], [])


class ConfirmReport(MoneyBase):
    """記帳確認報告（design/reports/記帳-確認.md）發現 #1、#2、#5、#6、#7：未收付不受區間限制、「我」由程式填這台的人、
    製卡沒日期記未收、照 do 記帳就關那題、算不出金額的那幾筆另外標。"""

    def card(self, title="信義王合約"):
        from tests import _entities as E
        from kb._lib import cards
        path = E.write_card(self.V, E.QUOTE, title, ["信義王"])
        return cards.parse_front((self.V / path).read_text(encoding="utf-8"))["編號"]

    def test_1_open_not_limited_by_range(self):
        self.add("--dir", "收", "--amount", "100000", "--due", "2026-10-01", "--entity", "信義王", "--text", "第二期")
        self.add("--dir", "收", "--amount", "20000", "--due", "2027-01-30", "--entity", "王先生", "--text", "尾款", "--new")
        self.add("--dir", "付", "--amount", "102000", "--due", "2027-02-05", "--entity", "文具店", "--text", "進貨")
        self.add("--dir", "收", "--amount", "5000", "--date", "2026-11-05", "--entity", "李小姐")
        got = self.kbj("money", "sum", "--from", "2026-11-01", "--to", "2026-11-09")
        self.assertEqual((got["in"], got["open_in"], got["open_out"]), (5000, 120000, 102000))
        old = self.kbj("money", "sum", "--from", "2000-01-01", "--to", "2026-09-30")
        self.assertEqual(old["open_in"], 120000, "問欠多少用很早到以前也看得到以後到期的")
        self.assertIn("不限區間", self.kb("money", "sum", "--from", "2026-11-01", "--to", "2026-11-09").stdout)

    def test_2_advanced_by_me(self):
        self.team(me="小王")
        out = self.add("--dir", "付", "--amount", "3200", "--advanced-by", "我", "--entity", "文具店", "--text", "文具")
        self.assertEqual(out["item"]["advanced_by"], "小王")
        bare = self.add("--dir", "付", "--amount", "500", "--advanced-by", "--entity", "文具店", "--text", "郵票", "--new")
        self.assertEqual(bare["item"]["advanced_by"], "小王")
        self.assertEqual(len(self.kbj("money", "list", "--open", "--advanced-by", "我")["items"]), 2)
        self.assertEqual(self.kbj("money", "sum", "--from", "2026-01-01", "--to", "2026-01-31", "--advanced-by", "我")["open_out"],
                         3700)
        edited = self.kbj("money", "edit", out["item"]["id"], "--advanced-by", "老闆")["item"]
        self.assertEqual(edited["advanced_by"], "老闆")
        self.assertEqual(self.kbj("money", "edit", out["item"]["id"], "--advanced-by", "我")["item"]["advanced_by"], "小王")

    def test_2_me_not_set_or_single(self):
        r = self.kb("money", "add", "--dir", "付", "--amount", "1", "--advanced-by", "我", code=3)
        self.assertIn("單人", r.stdout)
        self.team(me=None)
        r = self.kb("money", "add", "--dir", "付", "--amount", "1", "--advanced-by", "我", code=3)
        self.assertIn("kb who set", r.stdout)
        self.assertEqual(money.load(self.V)["items"], [])

    def test_5_card_without_date_is_open(self):
        fid = self.card()
        it = self.add("--card", fid, "--dir", "收", "--amount", "80000", "--entity", "信義王", "--text", "簽約款")["item"]
        self.assertEqual((it["status"], it["date"], it["due"]), ("open", None, None))
        paid = self.add("--card", fid, "--dir", "收", "--amount", "3000", "--date", "2026-10-01", "--entity", "信義王", "--new")["item"]
        self.assertEqual(paid["status"], "done")
        said = self.add("--dir", "收", "--amount", "700", "--entity", "李小姐")["item"]
        self.assertEqual((said["status"], said["date"]), ("done", TODAY), "她講的沒給日期照舊是今天")

    @unittest.skip("#65 甲段：這條測的是已拿掉的畫面／連動（首頁、日程、帳頁、lookup、待處理），乙段隨本檔一起刪")
    def test_6_do_with_resolves_closes_pending(self):
        fid = self.card("影印紙收據")
        pid = self.kbj("money", "unsure", "--card", fid, "--text", "收據 3,500，看不出誰付誰")["pending"]["id"]
        ask = next(x for x in self.kbj("asks", "--all")["asks"] if x["kind"] == "pending_money_unsure")
        paid = next(r for r in ask["results"] if r["label"] == "她付的")
        self.assertTrue(paid["do"] and f"--resolves {pid}" in paid["do"][0])
        self.assertIsNone(paid["argv"], "帳的欄要 AI 填，首頁不直接跑")
        r = self.kb("money", "add", "--card", fid, "--dir", "付", "--amount", "1", "--resolves", "p-00000000", code=3)
        self.assertIn("p-00000000", r.stdout)
        self.assertEqual(money.load(self.V)["items"], [], "編號錯了不寫")
        self.add("--card", fid, "--dir", "付", "--amount", "3500", "--date", "2026-11-01", "--entity", "文具店",
                 "--resolves", pid)
        item = next(i for i in pending.load(self.V)["items"] if i["id"] == pid)
        self.assertEqual(item["status"], "done")
        mid = self.add("--dir", "收", "--amount", "5000", "--due", "2026-12-01", "--entity", "李小姐")["item"]["id"]
        pid2 = self.kbj("money", "unsure", "--card", fid, "--text", "另一筆看不出")["pending"]["id"]
        self.kbj("money", "settle", mid, "--resolves", pid2)
        self.assertEqual(next(i for i in pending.load(self.V)["items"] if i["id"] == pid2)["status"], "done")

    def test_7_one_line_unknown_rest_counted(self):
        self.add("--dir", "收", "--amount", "5000", "--date", "2026-10-30", "--entity", "李小姐", "--item", "精華液 -2",
                 "--item", "益生菌 -1", "--text", "賣出")  # 益生菌沒有售價：這筆分不出
        self.add("--dir", "收", "--amount", "5400", "--date", "2026-10-20", "--entity", "王先生", "--item", "精華液 -3@1800")
        got = self.kbj("money", "sum", "--from", "2026-10-01", "--to", "2026-10-31")
        ess = next(p for p in got["products"] if p["name"] == "精華液")
        self.assertEqual((ess["qty"], ess["amount"], ess["missing"]), (5, 5400, 1))
        pro = next(p for p in got["products"] if p["name"] == "益生菌")
        self.assertEqual((pro["amount"], pro["missing"]), (None, 1))
        self.assertIn("1 筆沒算進去", self.kb("money", "sum", "--from", "2026-10-01", "--to", "2026-10-31").stdout)
        year = (self.V / money.year_rel("2026")).read_text(encoding="utf-8")
        self.assertIn("| 5,400（1 筆沒算進去） |", year)


class ConfirmPlaces(MoneyBase):
    """確認報告發現 #10：沒講地點的進出另成「未指定」，各店加未指定等於合計。"""
    places = True

    def test_10_unplaced_column(self):
        self.add("--dir", "付", "--amount", "1000", "--entity", "文具店", "--item", "益生菌 +20 在北店")
        top = (self.V / money.MD_POSIX).read_text(encoding="utf-8")
        self.assertIn("| 商品 | 北店 | 南店 | 合計 |", top, "都有地點就不出未指定")
        self.add("--dir", "收", "--amount", "500", "--entity", "李小姐", "--item", "益生菌 -2")
        st = self.kbj("money", "stock", "益生菌")["products"][0]
        self.assertEqual((st["total"], st["places"]), (18, {"北店": 20, "南店": 0, "未指定": -2}))
        self.assertIn("未指定 -2", self.kb("money", "stock", "益生菌").stdout)
        top = (self.V / money.MD_POSIX).read_text(encoding="utf-8")
        self.assertIn("| 商品 | 北店 | 南店 | 未指定 | 合計 |", top)
        self.assertIn("| 益生菌 | 20 瓶 | 0 瓶 | -2 瓶 | 18 瓶 |", top)
        self.assertEqual([p["places"] for p in money.stock(self.V, place="北店")["products"]], [{"北店": 20}])
