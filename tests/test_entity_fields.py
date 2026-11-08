"""記帳 1b：數字欄與記帳開關（issue #27；D-272、D-281、D-336、D-342、D-343，驗收 1～18）。
設定檔第九節數字欄、第十節記帳、第五節平常在哪；實體上一個數字一欄（欄:<欄名>）；kb entity field 的 --said／--card 規則；
綜合卡檔頭的數字行；她在屬性欄改數字；lookup；purge；遷移表補第十節；兩台改不同數字欄不算撞到。"""
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from tests import _cards
from tests import _entities as E
from tests import _tags as T
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import entities, migrate, pending, profile, purge, streams, synthesis, turn  # noqa: E402
from kb._lib import env  # noqa: E402
from kb._lib.io import read_json, write_json_atomic  # noqa: E402

SID = "test-sid"
ESS, CAP = "e-cccc0001", "e-cccc0002"
ESS_REL = "產品/精華液/精華液.md"
DAY = E.DAY
TYPES = (("案子", "matter"), ("業主", "party"), ("產品", "asset"), ("分店", "party"))


def field_row(type_, field, unit=""):
    return {"type": type_, "field": field, "unit": unit, "source": "confirmed", "date": DAY}


FIELDS = (field_row("產品", "售價", "元"), field_row("產品", "進價", "元"), field_row("產品", "每箱", "瓶"))


def write_profile(V, **changes):
    """改 profile.json（md 跟著重渲染、sha 對得上）。changes 的值是 None 就拿掉那個鍵。"""
    data = profile.load(V)
    for k, v in changes.items():
        if v is None:
            data.pop(k, None)
        else:
            data[k] = v
    text = profile.render_text(data)
    (Path(V) / profile.MD_POSIX).write_text(text, encoding="utf-8", newline="\n")
    data["md_sha256"] = profile.sha256_text(text)
    (Path(V) / profile.PROFILE_POSIX).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data


def entry(V, eid):
    return next(e for e in entities.load(V)["entities"] if e["id"] == eid)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        E.set_profile(self.V, types=TYPES)
        write_profile(self.V, fields=[dict(f) for f in FIELDS], tags=[T.tag("產品", "系列", ["保養", "保健"], False)],
                      money=[{"mode": "on", "places": [], "source": "inferred", "date": DAY}])
        data = entities.load(self.V)["entities"] + [E.entity(ESS, "精華液", "產品", card=True),
                                                    E.entity(CAP, "膠囊", "產品"),
                                                    E.entity("e-cccc0003", "北店", "分店"),
                                                    E.entity("e-cccc0004", "南店", "分店")]
        E.put_entities(self.V, data)
        T.write_synthesis(self.V, ESS, "精華液", ESS_REL, ["系列: 保養"])
        self.t = turn.start(self.V, SID, "記數字")["turn"]
        entities.sync_self(self.V, profile.load(self.V)["about"], self.t)  # fixture 的「你自己」先對齊，成功句才不多一行

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kb(self, *args):
        return run_kb(*args, cwd=self.V)

    def card(self):
        return (self.V / ESS_REL).read_text(encoding="utf-8")

    def front_lines(self):
        lines = self.card().splitlines()
        return lines[:lines.index("---", 1) + 1]

    def card_id(self, rel, title, date):
        E.write_card(self.V, rel, title, ["精華液"], date=date)
        return _cards.entry_of(self.V, rel)["id"]


# ---------- 1、2 設定檔與遷移 ----------

class Init(unittest.TestCase):
    def test_1_new_vault(self):
        tmp = Path(tempfile.mkdtemp(prefix="kbfield-")).resolve()
        try:
            V = tmp / "kb"
            r = run_kb("init", str(V), cwd=tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            raw = json.loads((V / profile.PROFILE_POSIX).read_text(encoding="utf-8"))
            self.assertEqual(raw["schema_version"], 7)
            self.assertEqual(raw["fields"], [])
            self.assertEqual([m["mode"] for m in raw["money"]], ["on"])
            md = (V / profile.MD_POSIX).read_text(encoding="utf-8")
            self.assertIn("## 九、數字欄", md)
            tenth = md.split("## 十、記帳", 1)[1]
            self.assertIn("| 狀態 | 地點的型別 | 來源 | 日期 |", tenth)
            self.assertIn("| 開 |", tenth)
            self.assertEqual(profile.money_mode(profile.load(V)), "on")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Upgrade(Base):
    def test_2_old_vault_gets_spoken(self):
        data = write_profile(self.V, fields=None, money=None)
        md = (self.V / profile.MD_POSIX).read_text(encoding="utf-8").split("\n## 九、")[0]  # 0.33.0 的 md 只有八節
        (self.V / profile.MD_POSIX).write_text(md, encoding="utf-8", newline="\n")
        data["md_sha256"] = profile.sha256_text(md)
        write_json_atomic(self.V / profile.PROFILE_POSIX, data)
        self.assertEqual(profile.status(self.V)["state"], "ok", "舊 md 少了九、十節不算錯")
        self.assertEqual(profile.money_mode(profile.load(self.V)), "spoken")
        self.assertIn(profile.PROFILE_POSIX, [p["rel"] for p in migrate.pending(self.V)])
        got = migrate.apply(self.V, self.t)
        self.assertIn(profile.PROFILE_POSIX, got["migrated"])
        raw = json.loads((self.V / profile.PROFILE_POSIX).read_text(encoding="utf-8"))
        self.assertEqual((raw["schema_version"], raw["fields"], raw["money"][0]["mode"]), (7, [], "spoken"))
        md = (self.V / profile.MD_POSIX).read_text(encoding="utf-8")
        self.assertIn("## 九、數字欄", md)
        self.assertIn("| 只記我講的 |", md.split("## 十、記帳", 1)[1])
        self.assertEqual(profile.status(self.V)["state"], "ok")
        self.assertNotIn(profile.PROFILE_POSIX, [p["rel"] for p in migrate.pending(self.V)])
        again = migrate.apply(self.V, self.t)
        self.assertNotIn(profile.PROFILE_POSIX, again["migrated"])
        self.assertEqual(json.loads((self.V / profile.PROFILE_POSIX).read_text(encoding="utf-8"))["schema_version"], 7)


# ---------- 3 錯誤句 ----------

class Errors(Base):
    def md_with(self, fields=None, money=None, about=None, people=None):
        data = profile.load(self.V)
        if fields is not None:
            data["fields"] = fields
        if money is not None:
            data["money"] = money
        if about is not None:
            data["about"] = about
        if people is not None:
            data["people"] = people
        return profile.render_text(data)

    def err(self, text):
        with self.assertRaises(profile.ProfileError) as cm:
            profile.fill_missing(profile.parse_md(text), profile.load(self.V), profile.place_names(self.V))
        return cm.exception.message

    def test_3_messages(self):
        cases = [
            (dict(fields=[field_row("汽車", "售價")]), "第 9 節第 1 列的型別「汽車」不在第 1 節"),
            (dict(fields=[field_row("產品", "庫存")]), "第 9 節第 1 列的欄名「庫存」不能用（是程式算的，不能當欄）"),
            (dict(fields=[field_row("產品", "系列")]), "第 9 節第 1 列的欄名「系列」跟第 8 節產品的標籤欄同名"),
            (dict(fields=[field_row("產品", "售價"), field_row("產品", "售價")]), "第 9 節第 2 列跟第 1 列重複（型別 產品 的欄 售價）"),
            (dict(fields=[field_row("產品", "價" * 21)]), "第 9 節第 1 列的欄名「" + "價" * 20 + "」不能用（太長，最多 20 字）"),
            (dict(money=[{"mode": "half", "places": []}]), "第 10 節第 1 列的狀態要是 開、只記我講的、關 之一"),
            (dict(money=[{"mode": "on", "places": ["倉庫"]}]), "第 10 節第 1 列的地點的型別「倉庫」不在第 1 節"),
            (dict(money=[{"mode": "on", "places": ["分店"]}], people=3,
                  about=[{"name": "小王", "kind": "person", "aliases": [], "place": "精華液"}]),
             "第 5 節第 1 列的平常在哪「精華液」不是地點的實體（地點的型別：分店）"),
        ]
        for kw, want in cases:
            with self.subTest(want=want):
                text = self.md_with(**kw)
                if kw.get("money") and kw["money"][0]["mode"] == "half":
                    text = text.replace("| 狀態 | 地點的型別 | 來源 | 日期 |\n|---|---|---|---|\n|  |",
                                        "| 狀態 | 地點的型別 | 來源 | 日期 |\n|---|---|---|---|\n| 半開 |")
                self.assertEqual(self.err(text), want)

    def test_3_apply_refuses_whole(self):
        before = (self.V / profile.PROFILE_POSIX).read_bytes()
        md = self.V / profile.MD_POSIX
        md.write_text(md.read_text(encoding="utf-8").replace("| 產品 | 每箱 | 瓶 |", "| 產品 | 庫存 | 瓶 |"),
                      encoding="utf-8", newline="\n")
        r = self.kb("profile", "apply")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("第 9 節第 3 列的欄名「庫存」不能用", r.stdout)
        self.assertEqual((self.V / profile.PROFILE_POSIX).read_bytes(), before)

    def test_place_ok_and_usual_place(self):
        data = write_profile(self.V, money=[{"mode": "on", "places": ["分店"], "source": "confirmed", "date": DAY}], people=3,
                             about=[{"name": "小王", "kind": "person", "aliases": [], "place": "北店", "source": "said",
                                     "date": DAY}])
        md = (self.V / profile.MD_POSIX).read_text(encoding="utf-8")
        self.assertIn("| 名稱 | 是什麼 | 別名 | 平常在哪 | 來源 | 日期 |", md)
        self.assertEqual(profile.usual_place(data, "小王"), "北店")
        r = self.kb("profile", "add", "關於你", "名稱=小王", "平常在哪=南店")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(profile.usual_place(profile.load(self.V), "小王"), "南店")
        r = self.kb("profile", "add", "關於你", "名稱=小王", "平常在哪=精華液")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertEqual(profile.place_types(profile.load(self.V)), ["分店"])

    def test_single_user_place_hidden_but_kept(self):
        write_profile(self.V, money=[{"mode": "on", "places": ["分店"], "source": "confirmed", "date": DAY}],
                      about=[{"name": "小王", "kind": "person", "aliases": [], "place": "北店", "source": "said", "date": DAY}])
        md = (self.V / profile.MD_POSIX).read_text(encoding="utf-8")
        self.assertNotIn("平常在哪", md.split("## 五、", 1)[1].split("## 六、", 1)[0])
        r = self.kb("profile", "add", "偏好", "偏好=回答先講結論")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(profile.usual_place(profile.load(self.V), "小王"), "北店")
        r = self.kb("profile", "add", "關於你", "名稱=小王", "平常在哪=精華液")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertEqual(profile.usual_place(profile.load(self.V), "小王"), "北店")


# ---------- 4、5 kb profile add／remove／apply ----------

class ProfileCli(Base):
    def test_4_add_and_money(self):
        r = self.kb("profile", "add", "數字欄", "型別=產品", "欄名=安全庫存", "單位=瓶")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "已加數字欄：產品的安全庫存（瓶）"))
        self.assertIn("| 產品 | 安全庫存 | 瓶 |", (self.V / profile.MD_POSIX).read_text(encoding="utf-8"))
        r = self.kb("profile", "add", "記帳", "狀態=關")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "已改記帳：關"))
        self.assertEqual(profile.money_mode(profile.load(self.V)), "off")
        self.assertIn("| 關 |", (self.V / profile.MD_POSIX).read_text(encoding="utf-8").split("## 十、", 1)[1])
        r = self.kb("profile", "add", "記帳", "地點的型別=分店")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual((profile.money_mode(profile.load(self.V)), profile.place_types(profile.load(self.V))), ("off", ["分店"]))
        r = self.kb("profile", "remove", "記帳")
        self.assertEqual(r.returncode, 3, r.stdout)

    def test_4_remove_drops_values(self):
        self.kb("entity", "field", "精華液", "售價=1800", "--said")
        self.kb("entity", "field", "精華液", "售價=1900", "--said")
        self.assertIn("售價: 1900", self.card())
        t2 = turn.start(self.V, SID, "不記售價")["turn"]
        r = self.kb("profile", "remove", "數字欄", "型別=產品", "欄名=售價")
        self.assertEqual((r.returncode, r.stdout.strip()),
                         (0, "已拿掉數字欄：產品的售價；1 個實體的「售價」拿掉了（舊值留著）"))
        cur = entry(self.V, ESS)["欄:售價"]
        self.assertIsNone(cur["value"])
        self.assertEqual([o["value"] for o in cur["old"]], [1800, 1900])
        self.assertNotIn("售價:", self.card())
        r = self.kb("versions", "revert")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(entry(self.V, ESS)["欄:售價"]["value"], 1900)
        self.assertIn("售價: 1900", self.card())
        self.assertTrue(t2)

    def test_4_removed_then_readded_card_fills(self):
        self.kb("entity", "field", "精華液", "售價=1800", "--said")
        self.kb("profile", "remove", "數字欄", "型別=產品", "欄名=售價")
        self.kb("profile", "add", "數字欄", "型別=產品", "欄名=售價", "單位=元")
        fid = self.card_id(E.QUOTE, "精華液報價", "2026-09-01")
        r = self.kb("entity", "field", "精華液", "售價=1700", "--card", fid)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(entry(self.V, ESS)["欄:售價"]["value"], 1700, "欄拿掉不是她說清掉，加回來檔案填得進")

    def test_4_hand_remove_asks_then_drop_fields(self):
        self.kb("entity", "field", "精華液", "售價=1800", "--said")
        md = self.V / profile.MD_POSIX
        md.write_text(md.read_text(encoding="utf-8").replace("| 產品 | 售價 | 元 | 確認 | 2026-10-19 |\n", ""),
                      encoding="utf-8", newline="\n")
        r = self.kb("profile", "apply", "--json")
        self.assertEqual(r.returncode, 3, r.stdout)
        got = json.loads(r.stdout)
        self.assertIn("第九節拿掉了「產品／售價」這一欄，有 1 個產品記了值", got["message"])
        self.assertTrue(any("--drop-fields" in " ".join(x["do"]) for x in got["results"]))
        self.assertEqual(entry(self.V, ESS)["欄:售價"]["value"], 1800)
        r = self.kb("profile", "apply", "--drop-fields")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("1 個實體的「售價」拿掉了（舊值留著）", r.stdout)
        self.assertIsNone(entry(self.V, ESS)["欄:售價"]["value"])
        self.assertNotIn("售價:", self.card())

    def test_4_rename_moves(self):
        self.kb("entity", "field", "精華液", "進價=1200", "--said")
        md = self.V / profile.MD_POSIX
        md.write_text(md.read_text(encoding="utf-8").replace("| 產品 | 進價 | 元 |", "| 產品 | 成本 | 元 |"),
                      encoding="utf-8", newline="\n")
        r = self.kb("profile", "apply", "--json")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertTrue(any("--rename-field" in " ".join(x["do"]) for x in json.loads(r.stdout)["results"]))
        r = self.kb("profile", "apply", "--rename-field", "產品", "進價", "成本")
        self.assertEqual(r.returncode, 0, r.stdout)
        e = entry(self.V, ESS)
        self.assertNotIn("欄:進價", e)
        self.assertEqual((e["欄:成本"]["value"], e["欄:成本"]["from"]), (1200, "said"))
        self.assertIn("成本: 1200", self.card())
        self.assertNotIn("進價:", self.card())

    def test_5_cards_todo_profile(self):
        r = self.kb("cards", "todo", "--json", "--full")  # 預設精簡版只給 about；整份（製卡材料）才有
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        prof = json.loads(r.stdout)["profile"]
        self.assertEqual(prof["fields"]["產品"][0], {"field": "售價", "unit": "元"})
        self.assertEqual(prof["money_mode"], "on")


# ---------- 6～10 kb entity field ----------

class FieldCommand(Base):
    def test_6_said_header_and_revert(self):
        before = {ESS_REL: (self.V / ESS_REL).read_bytes()}
        r = self.kb("entity", "field", "精華液", "售價=1,800", "進價=1200", "--said")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "精華液：售價 1,800 元、進價 1,200 元"))
        e = entry(self.V, ESS)
        self.assertEqual((e["欄:售價"]["value"], e["欄:售價"]["from"]), (1800, "said"))
        self.assertEqual((e["欄:進價"]["value"], e["欄:進價"]["from"]), (1200, "said"))
        lines = self.front_lines()
        self.assertEqual(lines[-4:], ["系列: 保養", "售價: 1800", "進價: 1200", "---"])
        got = json.loads(self.kb("entity", "field", "精華液", "售價=2000", "--said", "--json").stdout)
        self.assertEqual(got, {"entity": "精華液", "changed": {"售價": [1800, 2000]}, "kept": [], "conflicts": [],
                               "card": ESS_REL})
        self.assertEqual([o["value"] for o in entry(self.V, ESS)["欄:售價"]["old"]], [1800])
        r = self.kb("versions", "revert")  # 兩次 field 在同一個回合：一次退回都退掉
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("欄:售價", entry(self.V, ESS))
        self.assertEqual((self.V / ESS_REL).read_bytes(), before[ESS_REL])

    def test_7_refusals(self):
        cases = [(("會員價=1600", "--said"), "第九節沒有「會員價」這個數字欄；產品有：售價、進價、每箱"),
                 (("售價=一千八", "--said"), "看不懂這個數字：一千八"),
                 (("售價=-5", "--said"), "不能是負數：-5"),
                 (("售價=1800",), "要說是她說的（--said）還是哪張卡讀到的（--card f-…）")]
        for args, want in cases:
            with self.subTest(args=args):
                r = self.kb("entity", "field", "精華液", *args)
                self.assertEqual((r.returncode, r.stdout.strip()), (3, want))
        self.assertNotIn("欄:售價", entry(self.V, ESS))

    def test_8_card_rules(self):
        old = self.card_id(E.QUOTE, "精華液報價舊", "2026-09-01")
        new = self.card_id(E.ESTIMATE, "精華液報價新", "2026-10-01")
        undated = self.card_id(E.TEMPLATE, "精華液價目", "未載")
        self.kb("entity", "field", "精華液", "售價=1800", "--card", new)
        r = self.kb("entity", "field", "精華液", "售價=1600", "--card", old, "--json")
        self.assertEqual(json.loads(r.stdout)["kept"], [{"field": "售價", "why": "older"}])
        self.assertEqual(entry(self.V, ESS)["欄:售價"]["value"], 1800)
        r = self.kb("entity", "field", "精華液", "進價=1100", "--card", old)
        r = self.kb("entity", "field", "精華液", "進價=1200", "--card", new)
        self.assertEqual(entry(self.V, ESS)["欄:進價"]["value"], 1200, "比較新的蓋")
        r = self.kb("entity", "field", "精華液", "售價=1700", "--card", undated, "--json")
        got = json.loads(r.stdout)
        self.assertEqual(got["changed"], {})
        self.assertEqual(got["conflicts"], [{"field": "售價", "old": 1800, "new": 1700, "old_card": new, "new_card": undated}])
        self.assertEqual(entry(self.V, ESS)["欄:售價"]["value"], 1800)
        items = [i for i in pending.load(self.V)["items"] if i.get("kind") == "conflict" and i.get("status") == "open"]
        self.assertEqual(len(items), 1)
        self.assertIn("精華液 的 售價", items[0]["text"])
        same = self.card_id(E.DRAFT, "精華液報價同日", "2026-10-01")
        r = self.kb("entity", "field", "精華液", "進價=1300", "--card", same, "--json")
        self.assertEqual([c["field"] for c in json.loads(r.stdout)["conflicts"]], ["進價"], "同一天分不出新舊（D-281）")
        self.assertEqual(entry(self.V, ESS)["欄:進價"]["value"], 1200)
        self.kb("entity", "field", "精華液", "每箱=24", "--said")
        r = self.kb("entity", "field", "精華液", "每箱=12", "--card", new, "--json")
        self.assertEqual(json.loads(r.stdout)["kept"], [{"field": "每箱", "why": "said"}])
        self.assertEqual(entry(self.V, ESS)["欄:每箱"]["value"], 24)

    def test_9_clear(self):
        self.kb("entity", "field", "精華液", "售價=1800", "--said")
        r = self.kb("entity", "field", "精華液", "售價=", "--said")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "精華液：售價 沒有"))
        cur = entry(self.V, ESS)["欄:售價"]
        self.assertEqual((cur["value"], cur["from"], [o["value"] for o in cur["old"]]), (None, "said", [1800]))
        self.assertNotIn("售價:", self.card())

    def test_10_no_card_then_header_and_mark_synced(self):
        r = self.kb("entity", "field", "膠囊", "售價=900", "--said")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("售價: 900", T.header(self.V, CAP))
        self.kb("entity", "field", "精華液", "售價=1800", "--said")
        for broken in ("售價: 999", None):
            text = self.card()
            text = text.replace("售價: 1800", broken) if broken else text.replace("售價: 1800\n", "")
            (self.V / ESS_REL).write_text(text, encoding="utf-8", newline="\n")
            written, skipped = synthesis.mark_synced(self.V, ["精華液"], self.t)
            self.assertEqual(skipped, [])
            self.assertIn("售價: 1800", self.card())
            self.assertNotIn("售價: 999", self.card())

    def test_copy_tags_restores_numbers(self):
        self.kb("entity", "field", "精華液", "售價=1800", "--said")
        (self.V / ESS_REL).write_text(self.card().replace("售價: 1800", "售價: 5"), encoding="utf-8", newline="\n")
        synthesis.copy_tags(self.V, ESS_REL, self.t)
        self.assertIn("售價: 1800", self.card())
        self.assertEqual(entry(self.V, ESS)["欄:售價"]["value"], 1800)


# ---------- 11 她在屬性欄改 ----------

class HandEdit(Base):
    def edit(self, old, new):
        p = self.V / ESS_REL
        p.write_text(p.read_text(encoding="utf-8").replace(old, new), encoding="utf-8", newline="\n")
        later = time.time() + 30
        os.utime(p, (later, later))

    def line(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
        import _checks
        return _checks.line_tags(self.V)

    def test_11_hand_edit_from_card(self):
        self.kb("entity", "field", "精華液", "售價=1800", "--said")
        self.edit("售價: 1800", "售價: 2000")
        line = self.line()
        self.assertTrue(line.startswith("客戶在 Obsidian 卡的屬性欄改了 1 張綜合卡的標籤或數字（精華液）"), line)
        self.assertIn("你在卡的屬性欄改了標籤或數字：", line)
        r = self.kb("entity", "field", "精華液", "--from-card")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "照你在卡上改的記下了：精華液 售價 2,000 元"))
        cur = entry(self.V, ESS)["欄:售價"]
        self.assertEqual((cur["value"], cur["from"]), (2000, "hand"))
        self.assertIsNone(self.line())

    def test_11_not_a_number(self):
        self.kb("entity", "field", "精華液", "售價=1800", "--said")
        self.edit("售價: 1800", "售價: 兩千")
        (got,) = entities.tag_edits(self.V)
        self.assertEqual((got["ok"], got["problem"]), (False, "精華液的卡上「售價」寫了「兩千」，不是數字：要記成多少？"))
        r = self.kb("entity", "field", "精華液", "--from-card")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, got["problem"]))
        self.assertEqual(entry(self.V, ESS)["欄:售價"]["value"], 1800)

    def test_11_line_deleted_is_clear(self):
        self.kb("entity", "field", "精華液", "售價=1800", "--said")
        self.edit("售價: 1800\n", "")
        r = self.kb("entity", "tag", "--from-card")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIsNone(entry(self.V, ESS)["欄:售價"]["value"])


# ---------- 12 改名、合併、換型別 ----------

class Follow(Base):
    def test_12_rename(self):
        self.kb("entity", "field", "精華液", "售價=1800", "--said")
        r = self.kb("entity", "rename", "精華液", "--to", "玻尿酸精華")
        self.assertEqual(r.returncode, 0, r.stdout)
        e = entry(self.V, ESS)
        self.assertEqual(e["欄:售價"]["value"], 1800)
        self.assertIn("售價: 1800", (self.V / "產品/玻尿酸精華/玻尿酸精華.md").read_text(encoding="utf-8"))

    def test_12_merge(self):
        self.kb("entity", "field", "精華液", "售價=1800", "--said")
        self.kb("entity", "field", "膠囊", "售價=900", "進價=500", "--said")
        r = self.kb("entity", "merge", "膠囊", "--into", "精華液")
        self.assertEqual(r.returncode, 0, r.stdout)
        e = entry(self.V, ESS)
        self.assertEqual(e["欄:售價"]["value"], 1800)
        self.assertEqual([o["value"] for o in e["欄:售價"]["old"]], [900])
        self.assertEqual(e["欄:進價"]["value"], 500)
        self.assertIn("進價: 500", self.card())

    def test_12_retype(self):
        self.kb("entity", "field", "精華液", "售價=1800", "--said")
        r = self.kb("entity", "rename", "精華液", "--to", "精華液", "--type", "案子")
        self.assertEqual(r.returncode, 0, r.stdout)
        e = entry(self.V, ESS)
        self.assertEqual(e["欄:售價"]["value"], 1800, "值留著")
        text = (self.V / "案子/精華液/精華液.md").read_text(encoding="utf-8")
        self.assertNotIn("售價:", text, "新型別第九節沒有那欄，不顯示")


# ---------- 13 兩台 ----------

class TwoMachines(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.V = self.tmp / "v"
        (self.V / ".system").mkdir(parents=True)
        self._orig = env.machine_name

    def tearDown(self):
        env.machine_name = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def as_machine(self, name):
        env.machine_name = lambda: name
        env.set_machine_id(self.V, "m-" + name)

    def line(self, by, field, value):
        return {"v": streams.FORMAT_VERSION, "op": "set", "id": "e-1", "seq": 2, "base": 1, "by": by,
                "set": {field: {"value": value, "from": "said", "card": None, "doc_date": None, "at": "2026-11-09T10:00:00",
                                "old": []}}}

    def conflicts(self, field_a, field_b):
        self.as_machine("aaaa")
        p = self.V / ".system" / "entities.json"
        write_json_atomic(p, {"schema_version": 3, "entities": [{"id": "e-1", "name": "精華液", "type": "產品",
                                                                  "status": "active"}]})
        d = streams.stream_dir(self.V, "entities")
        with (d / "m-aaaa.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(self.line("m-aaaa", field_a, 1800), ensure_ascii=False) + "\n")
        (d / "m-bbbb.jsonl").write_text(json.dumps(self.line("m-bbbb", field_b, 1200), ensure_ascii=False) + "\n",
                                        encoding="utf-8")
        st = streams.load(self.V, "entities")
        return [(c["id"], c["field"]) for c in st.conflicts], st.records["e-1"]

    def test_13_different_fields_no_conflict(self):
        got, rec = self.conflicts("欄:售價", "欄:進價")
        self.assertEqual(got, [])
        self.assertEqual((rec["欄:售價"]["value"], rec["欄:進價"]["value"]), (1800, 1200))

    def test_13_same_field_conflict(self):
        got, _rec = self.conflicts("欄:售價", "欄:售價")
        self.assertEqual(got, [("e-1", "欄:售價")])


# ---------- 14 守門 ----------

class Guard(unittest.TestCase):
    def setUp(self):
        from tests._guard_fixture import make_vault
        from kb._lib import batches
        self.tmp, self.V, self.raw = make_vault()
        self.job = turn.start(self.V, "sid-f", "好，現在做")["turn"]
        batches.agent_start(self.V, "sid-f", "a0204e72")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, args):
        from tests._guard_fixture import ROOT, payload
        from tests.test_cardmaker_round1 import guard_out
        from kb._lib import batches
        data = payload("Bash", f'python "{ROOT}/scripts/kb.py" {args}', self.V)
        data.update(session_id="sid-f", agent_id="a0204e72", agent_type=batches.AGENT)
        return guard_out(data)

    def test_14_agent_card_allowed_said_denied(self):
        out = self.call("entity field 精華液 售價=1800 --card f-1a2b3c4d")
        self.assertEqual(out["permissionDecision"], "allow", out)
        self.assertIn(f"--turn {self.job}", out["updatedInput"]["command"])
        for denied in ("entity field 精華液 售價=1800 --said", "entity field 精華液 售價=1800 --sa",
                       "entity field --from-card", "entity field 精華液 --from-card"):
            with self.subTest(denied=denied):
                out = self.call(denied)
                self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]), ("deny", "製卡助手不能做這件事"))


# ---------- 15 lookup、16 tally、17 purge ----------

class Lookup(Base):
    def test_15_lookup(self):
        self.kb("entity", "field", "精華液", "售價=1800", "--said")
        self.kb("entity", "field", "精華液", "進價=1200", "--card", self.card_id(E.QUOTE, "精華液報價", "2026-09-01"))
        got = json.loads(self.kb("lookup", "精華液", "--json").stdout)
        self.assertEqual(got["fields"], {"售價": {"value": 1800, "unit": "元", "said": True},
                                         "進價": {"value": 1200, "unit": "元", "said": False}})
        text = self.kb("lookup", "精華液").stdout
        self.assertIn("數字：售價 1,800 元（你說的）、進價 1,200 元", text)


class Numbers(unittest.TestCase):
    def test_16_tally_parse_moved(self):
        from decimal import Decimal
        from kb import tally_cli
        from kb._lib import numbers
        self.assertIs(tally_cli.parse_number, numbers.parse_number)
        self.assertEqual(tally_cli.parse_number("-3.5"), Decimal("-3.5"))
        with self.assertRaises(tally_cli.TallyRefused):
            tally_cli.parse_number("一千")
        with self.assertRaises(numbers.NumberRefused):
            numbers.parse_number("-3", negative=False)
        self.assertEqual(numbers.parse_number("3萬", negative=False), Decimal("30000"))


class Purge(Base):
    def test_17_purge_drops_value_and_old(self):
        fid = self.card_id(E.QUOTE, "精華液報價", "2026-09-01")
        other = self.card_id(E.ESTIMATE, "精華液估價", "2026-10-01")
        self.kb("entity", "field", "精華液", "售價=1600", "--card", fid)
        self.kb("entity", "field", "精華液", "售價=1800", "--card", other)
        self.kb("entity", "field", "精華液", "進價=1100", "--card", fid)
        counts = {"left": {"state": 0}, "card_ids": set(), "findings": 0, "finding_ids": set()}
        purge._current_state(self.V, {fid}, self.t, counts)
        e = entry(self.V, ESS)
        self.assertEqual((e["欄:售價"]["value"], e["欄:售價"]["old"]), (1800, []))
        self.assertEqual((e["欄:進價"]["value"], e["欄:進價"]["card"]), (None, None))
        self.assertNotIn("進價:", self.card())
        self.assertIn("售價: 1800", self.card())
        self.assertEqual(entities.tag_edits(self.V), [], "清掉的值不會被當成她在屬性欄寫的")
        data = {"entities": [dict(e, **{"欄:每箱": {"value": 24, "card": fid, "old": [{"value": 12, "card": fid}]}})]}
        self.assertTrue(purge.drop_entity_fields(data, {fid}))
        self.assertEqual((data["entities"][0]["欄:每箱"]["value"], data["entities"][0]["欄:每箱"]["old"]), (None, []))


if __name__ == "__main__":
    unittest.main()
