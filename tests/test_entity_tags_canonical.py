"""標籤記在實體上（D-505，issue #13；驗收 1～12、14）：標籤的正本在 entities.json（schema 3）的 tags，綜合卡檔頭是它的渲染。
kb entity tag 寫正本（沒有綜合卡也行）、hook 把 AI 寫的標籤行抄進正本（她說過的欄不抄、卡寫回）、照標籤篩與 lookup 讀正本、
改字典改正本、加欄沒卡的也補標籤（cards todo 的 tag_only）、回答末尾比對正本、健檢認出她手改的、舊庫升級把卡上的抄進來。"""
import json
import os
import shutil
import time
import unittest
from pathlib import Path

from tests import _entities as E
from tests import _lint as L
from tests import _tags as T
from tests.test_hooks_output_log import write_via_tools
from tests.test_hooks_session import payload as session_payload, run_turn_ctx as run_session  # 標籤的行挪到每句開頭（放寬丙 3b）
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import batches, entities, migrate, pending, plan, synthesis, turn  # noqa: E402
from kb.lint import state  # noqa: E402
from kb.lint.checks import tag_edits  # noqa: E402

LI, LI_REL = "e-aaaa0001", "案子/內湖李/內湖李.md"
OPENING_ONE = ("客戶在 Obsidian 卡的屬性欄改了 1 張綜合卡的標籤或數字（信義王）：跑 kb entity tag --from-card 記進去"
               "（數字一起記，同 kb entity field --from-card），跟她說「你在卡的屬性欄改了標籤或數字：…（記了什麼）」；"
               "不在字典的詞直接加進字典，不是數字的問她要記成多少。")  # 記帳 1b 第 6 點
SID = "test-sid"


def entry(V, eid):
    return next(e for e in entities.load(V)["entities"] if e["id"] == eid)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        self.t = turn.start(self.V, SID, "整理")["turn"]
        data = entities.load(self.V)["entities"] + [E.entity(LI, "內湖李")]
        E.put_entities(self.V, data)
        T.set_tags(self.V)
        T.write_synthesis(self.V, E.XINYI, "信義王", T.XINYI_REL, ["工種: [水電, 木作]", "階段: 施工"])
        E.write_card(self.V, E.ESTIMATE, "內湖李估價", ["內湖李"])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kb(self, *args):
        return run_kb(*args, cwd=self.V)

    def buckets(self):
        data = entities.load(self.V)
        return synthesis.buckets(self.V, data, entities.mounts(self.V, data), entities._profile(self.V))


class Schema(Base):
    def test_new_writes_schema3_and_schema2_has_no_tags(self):
        """驗收 1。"""
        entities.add(self.V, "案子", "士林張", self.t)
        raw = json.loads((self.V / entities.ENTITIES_POSIX).read_text(encoding="utf-8"))
        self.assertEqual(raw["schema_version"], 3)
        shutil.copy2(E.FIX / "entities-schema2.json", self.V / entities.ENTITIES_POSIX)
        data = entities.load(self.V)
        self.assertTrue(all("tags" not in e for e in data["entities"]))
        got = entities.tag_filter(self.V, [("工種", ["水電"])], data)
        self.assertEqual(got["counts"], [{"type": "案子", "total": 3, "matched": 0, "untagged": 3}])


class Upgrade(Base):
    def test_schema2_cards_copied_skipped_and_revert(self):
        """驗收 2：A 有卡有標籤 → tags 等於檔頭（字典外的那一欄進 skipped）；B 有卡沒標籤行 → 沒有 tags；C 沒卡 → todo 補標籤。"""
        shutil.copy2(E.FIX / "entities-schema2.json", self.V / entities.ENTITIES_POSIX)
        T.write_synthesis(self.V, E.XINYI, "信義王", T.XINYI_REL, ["工種: [水電, 油漆]", "階段: 施工"], sync=False)
        T.write_synthesis(self.V, E.DAAN, "大安陳", T.DAAN_REL, [], sync=False)
        before = (self.V / entities.ENTITIES_POSIX).read_bytes()
        got = migrate.apply(self.V, self.t)
        self.assertIn(entities.ENTITIES_POSIX, got["migrated"])
        self.assertEqual([s["rel"] for s in got["skipped"]], [T.XINYI_REL])
        self.assertIn("油漆", got["skipped"][0]["why"])
        self.assertEqual(entry(self.V, E.XINYI)["tags"], {"階段": "施工"})
        self.assertEqual(entry(self.V, E.XINYI)["tags_said"], [])
        self.assertNotIn("tags", entry(self.V, E.DAAN))
        (item,) = [i for i in self.buckets()["synthesis_stale"] if i.get("tag_only")]
        self.assertEqual((item["entity_id"], item["reason"]), (LI, "補標籤（工種、階段）"))
        self.assertEqual(plan._tagged_tell(self.V), [], "升級是程式抄的，回答末尾不講")
        r = self.kb("versions", "revert")
        self.assertEqual(r.returncode, 0, r.stdout)
        import json  # 流水檔改回後副本由流水檔重寫，排版不同；內容比逐欄（多人共用 1）
        self.assertEqual(json.loads((self.V / entities.ENTITIES_POSIX).read_text(encoding="utf-8")), json.loads(before.decode("utf-8")))


class TagCommand(Base):
    def test_no_card_written_and_sentence(self):
        """驗收 3。"""
        r = self.kb("entity", "tag", "內湖李", "工種=水電,木作", "階段=施工")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "內湖李標了：工種 水電、木作；階段 施工"))
        self.assertEqual(entry(self.V, LI)["tags"], {"工種": ["水電", "木作"], "階段": "施工"})
        got = json.loads(self.kb("entity", "tag", "內湖李", "階段=", "--json").stdout)
        self.assertEqual(got, {"name": "內湖李", "changed": ["階段"], "kept": [],
                               "tags": {"工種": ["水電", "木作"], "階段": ""}, "card": None})

    def test_refusals(self):
        cases = [(("工種=油漆",), "「油漆」不在「工種」的字典裡：先問客戶要不要加（kb profile add 標籤 型別=案子 欄名=工種 詞=油漆），不要自己加"),
                 (("階段=報價,施工",), "「階段」只能選一個詞"),
                 (("在意=醫療",), "第八節沒有「在意」這個標籤欄；有：工種、階段"),
                 (("工種",), "要寫成 欄=詞（多個詞用逗號分開；欄= 後面空著是看過、沒有）")]
        for args, want in cases:
            with self.subTest(args=args):
                r = self.kb("entity", "tag", "內湖李", *args)
                self.assertEqual((r.returncode, r.stdout.strip()), (3, want))
        r = self.kb("entity", "tag", "沒有這個", "工種=水電")
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "實體清單沒有「沒有這個」"))
        self.assertNotIn("tags", entry(self.V, LI))

    def test_said_rewrites_card_line_only(self):
        """驗收 4：卡上那一行換、其他位元組不變、備份 by program；tags_said 有那欄。"""
        before = (self.V / T.XINYI_REL).read_bytes()
        t2 = turn.start(self.V, SID, "改成完工")["turn"]
        r = self.kb("entity", "tag", "信義王", "階段=完工", "--said")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "信義王標了：階段 完工"))
        self.assertEqual((self.V / T.XINYI_REL).read_bytes(), before.replace("階段: 施工".encode(), "階段: 完工".encode()))
        row = next(x for x in turn.entries(self.V, t2) if x["path"] == T.XINYI_REL)
        self.assertEqual(row.get("by"), "program")
        self.assertEqual(entry(self.V, E.XINYI)["tags_said"], ["階段"])
        r = self.kb("entity", "tag", "信義王", "階段=施工")
        self.assertEqual(r.stdout.strip(), "信義王標了：階段 完工（階段是你說過的，照你說的留著）")
        self.assertEqual(plan._tagged_tell(self.V), [], "她親口說的不在回答末尾講")


class Hook(Base):
    def write(self, rel, lines):
        text = E.synthesis_text(T.with_tag_lines(T.strip_tag_lines(T.header(self.V, LI)), lines), "內湖李")
        p = self.V / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        r = write_via_tools(self.V, p, text)
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)

    def test_ai_card_copied_and_said_field_written_back(self):
        """驗收 5、14：只有一份資料時先標進正本；第二份來了寫綜合卡，header 帶正本；AI 寫了別的詞，她說的欄不變、卡寫回。"""
        entities.set_tags(self.V, LI, {"工種": ["水電"]}, self.t)
        entities.set_tags(self.V, LI, {"階段": "施工"}, self.t, said=True)
        E.write_card(self.V, E.QUOTE, "內湖李報價", ["內湖李"])
        (item,) = [i for i in self.buckets()["synthesis_new"] if i["entity_id"] == LI]
        self.assertEqual(item["header"].splitlines()[-3:], ["工種: [水電]", "階段: 施工", "---"])
        self.assertEqual(item["tags_said"], ["階段"])
        self.write(LI_REL, ["工種: [水電, 磁磚]", "階段: 完工"])
        self.assertEqual(entry(self.V, LI)["tags"], {"工種": ["水電", "磁磚"], "階段": "施工"})
        self.assertIn("階段: 施工\n", (self.V / LI_REL).read_text(encoding="utf-8"))
        self.assertNotIn("階段: 完工", (self.V / LI_REL).read_text(encoding="utf-8"))
        self.assertTrue(entry(self.V, LI)["card"])


class Filter(Base):
    def test_no_card_listed_and_counts(self):
        """驗收 6、9。"""
        self.kb("entity", "tag", "內湖李", "階段=施工", "工種=")
        got = json.loads(self.kb("entity", "list", "--tag", "階段=施工", "--json").stdout)
        self.assertEqual(sorted(e["name"] for e in got["entities"]), ["信義王", "內湖李"])
        self.assertEqual(got["counts"][0]["matched"], 2)
        got = json.loads(self.kb("entity", "list", "--tag", "工種=水電", "--json").stdout)
        self.assertEqual([e["name"] for e in got["entities"]], ["信義王"], "工種= 是看過、沒有，不算符合")
        r = self.kb("lookup", "內湖李")
        self.assertIn("標籤：階段 施工", r.stdout)


class AddField(Base):
    def test_no_card_entity_marked_and_batch_tag_only(self):
        """驗收 7：加欄 → 沒卡的也記補標籤；cards batch 的項目有 tag_only、cards；有卡的照現在記卡路徑。"""
        self.kb("entity", "tag", "內湖李", "工種=水電", "階段=施工")
        self.assertFalse([i for i in self.buckets()["synthesis_stale"] if i.get("tag_only")], "欄都標過了不用補")
        r = self.kb("profile", "add", "標籤", "型別=案子", "欄名=預算", "詞=高、中")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("2 張案子的綜合卡要補標籤、1 個案子還沒有綜合卡，也會補標籤", r.stdout)
        self.assertEqual(sorted(f["path"] for f in state.fixes(self.V)), sorted([T.XINYI_REL, T.DAAN_REL, LI]))
        (item,) = [i for i in self.buckets()["synthesis_stale"] if i.get("tag_only")]
        self.assertEqual(item["reason"], "補標籤（預算）")
        self.assertEqual([c["title"] for c in item["cards"]], ["內湖李估價"])
        self.assertEqual(item["tags"], {"工種": ["水電"], "階段": "施工"})
        self.assertTrue(batches.tag_only("synthesis_stale", item))
        r = self.kb("profile", "add", "標籤", "型別=案子", "欄名=工種", "詞=油漆")
        self.kb("entity", "tag", "內湖李", "預算=高")
        self.assertNotIn(LI, [f["path"] for f in state.fixes(self.V)], "正本改過了，補標籤那筆不算")


class Merge(Base):
    def test_merge_entities_and_cards_and_revert(self):
        """驗收 8：正本與卡都換、impact.entities 有卡沒卡都算；revert 全回。"""
        self.kb("entity", "tag", "內湖李", "工種=水電")
        t2 = turn.start(self.V, None, "併")["turn"]
        before = {p: (self.V / p).read_bytes() for p in (entities.ENTITIES_POSIX, T.XINYI_REL)}
        got = json.loads(self.kb("profile", "tag", "merge", "案子", "工種", "水電", "--into", "木作", "--check",
                                 "--json").stdout)
        self.assertEqual(got["impact"], {"entities": 2, "both": 1})
        self.assertEqual(got["question"], "案子有 2 個標了水電，其中 1 個也標了木作；併起來 2 個都只剩木作。要併嗎？")
        r = self.kb("profile", "tag", "merge", "案子", "工種", "水電", "--into", "木作")
        self.assertEqual(r.stdout.strip(), "已把「水電」併進「木作」：2 個只剩木作；不對可以說退回")
        self.assertEqual(entry(self.V, LI)["tags"]["工種"], ["木作"])
        self.assertEqual(entry(self.V, E.XINYI)["tags"]["工種"], ["木作"])
        self.assertIn("工種: [木作]\n", (self.V / T.XINYI_REL).read_text(encoding="utf-8"))
        self.assertEqual(next(x for x in turn.entries(self.V, t2) if x["path"] == entities.ENTITIES_POSIX).get("by"),
                         "program")
        r = self.kb("versions", "revert")
        self.assertEqual(r.returncode, 0, r.stdout)
        for p, b in before.items():
            self.assertEqual((self.V / p).read_bytes(), b, p)


class Tell(Base):
    def test_entity_tag_without_card_told(self):
        """驗收 10：這一回合 entity tag 給沒卡的實體加了詞 → tell 有那一句。"""
        turn.start(self.V, SID, "補標籤")
        self.kb("entity", "tag", "內湖李", "工種=水電")
        self.assertEqual(plan._tagged_tell(self.V), ["內湖李標了：工種 水電"])


class HandEdit(Base):
    def edit(self, old, new):
        p = self.V / T.XINYI_REL
        p.write_text(p.read_text(encoding="utf-8").replace(old, new), encoding="utf-8", newline="\n")
        later = time.time() + 30
        os.utime(p, (later, later))

    def run_check(self):
        c = L.ctx(self.V)
        found = tag_edits.run(c)
        return [f["apply"](c) for f in found]

    def opening(self):
        r = run_session(session_payload(self.V))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"].splitlines()

    def test_opening_line_then_from_card(self):
        """驗收 11（裁定 6）：開場段有那一行；--from-card 照她改的記進正本、句子一字不差、開場那行不再出現。"""
        self.edit("階段: 施工", "階段: 完工")
        self.assertIn(OPENING_ONE,
                      self.opening())
        self.assertEqual(entities.tag_edits(self.V), [{"name": "信義王", "fields": ["階段"], "ok": True, "problem": None}])
        r = self.kb("entity", "tag", "--from-card")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "照你在卡上改的記下了：信義王 階段 完工"))
        self.assertEqual(entry(self.V, E.XINYI)["tags"]["階段"], "完工")
        self.assertEqual(entry(self.V, E.XINYI)["tags_said"], ["階段"])
        self.assertFalse([x for x in self.opening() if x.startswith("客戶在 Obsidian 卡的屬性欄改了")])
        self.assertEqual(self.kb("entity", "tag", "--from-card", "信義王").stdout.strip(), "卡上的標籤跟實體清單一樣，沒有要記的")

    def test_from_card_outside_dictionary_not_written(self):
        self.edit("階段: 施工", "階段: 暫停")
        (got,) = entities.tag_edits(self.V)
        self.assertEqual((got["ok"], got["problem"]), (False, "信義王的卡上「暫停」不在「階段」的字典裡：要加進字典還是改回 施工？"))
        r = self.kb("entity", "tag", "--from-card", "信義王", "--json")
        self.assertEqual(json.loads(r.stdout), {"recorded": [], "problems": [
            {"name": "信義王", "field": "階段", "card": "暫停", "problem": got["problem"]}]})
        self.assertEqual(entry(self.V, E.XINYI)["tags"]["階段"], "施工")
        r = self.kb("entity", "tag", "--from-card", "內湖李")
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "「內湖李」沒有綜合卡"))

    def test_single_two_words_first_same_as_canonical(self):
        """測試回報：單選欄改成兩個詞、第一個跟正本一樣，也要算她改了（開場、--from-card、健檢都問）。"""
        self.edit("階段: 施工", "階段: [施工, 完工]")
        want = "信義王的卡上「階段」寫了 2 個詞，這一欄只能選一個：要留哪一個？"
        self.assertEqual(entities.tag_edits(self.V), [{"name": "信義王", "fields": ["階段"], "ok": False, "problem": want}])
        self.assertIn(OPENING_ONE,
                      self.opening())
        r = self.kb("entity", "tag", "--from-card", "信義王")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, want))
        self.assertEqual(entry(self.V, E.XINYI)["tags"]["階段"], "施工")
        self.run_check()
        (item,) = [i for i in pending.load(self.V)["items"] if i["kind"] == "tag_edit"]
        self.assertEqual((item["status"], item["text"]), ("open", want))

    def test_more_than_three_names(self):
        for eid, name in ((E.DAAN, "大安陳"), ("e-aaaa0011", "甲"), ("e-aaaa0012", "乙"), ("e-aaaa0013", "丙")):
            if eid != E.DAAN:
                E.put_entities(self.V, entities.load(self.V)["entities"] + [E.entity(eid, name, card=True)])
            rel = f"案子/{name}/{name}.md"
            T.write_synthesis(self.V, eid, name, rel, ["階段: 施工"])
            p = self.V / rel
            p.write_text(p.read_text(encoding="utf-8").replace("階段: 施工", "階段: 完工"), encoding="utf-8", newline="\n")
            os.utime(p, (time.time() + 30, time.time() + 30))
        self.edit("階段: 施工", "階段: 完工")
        (line,) = [x for x in self.opening() if x.startswith("客戶在 Obsidian 卡的屬性欄改了")]
        self.assertTrue(line.startswith("客戶在 Obsidian 卡的屬性欄改了 5 張綜合卡的標籤或數字（"), line)
        self.assertEqual(line.split("（")[1].split("）")[0].count("、"), 2)
        self.assertIn("…）", line)

    def test_in_dictionary_copied_as_said(self):
        """驗收 11：字典裡的詞、卡較新 → 正本照改、tags_said 加欄、報告那句。"""
        self.edit("階段: 施工", "階段: 完工")
        self.assertEqual(self.run_check(), ["你在 信義王 的卡上把階段改成完工，照你改的記下了"])
        self.assertEqual(entry(self.V, E.XINYI)["tags"]["階段"], "完工")
        self.assertEqual(entry(self.V, E.XINYI)["tags_said"], ["階段"])
        self.assertEqual(self.run_check(), [], "一樣了就不再報")

    def test_card_older_not_counted(self):
        p = self.V / T.XINYI_REL
        p.write_text(p.read_text(encoding="utf-8").replace("階段: 施工", "階段: 完工"), encoding="utf-8", newline="\n")
        os.utime(p, (time.time() - 3600, time.time() - 3600))
        self.assertEqual(self.run_check(), [])
        self.assertEqual(entry(self.V, E.XINYI)["tags"]["階段"], "施工")

    def test_outside_dictionary_asks_then_closes(self):
        self.edit("階段: 施工", "階段: 暫停")
        self.run_check()
        (item,) = [i for i in pending.load(self.V)["items"] if i["kind"] == "tag_edit"]
        self.assertEqual((item["status"], item["entity_ids"]), ("open", [E.XINYI]))
        self.assertIn("暫停", item["text"])
        self.assertEqual([r["label"] for r in item["data"]["results"]], ["把暫停加進「階段」的字典", "「階段」改回去"])
        asks, _hidden = plan.pending_asks(self.V)
        self.assertIn(f"pending:{item['id']}", [a["id"] for a in asks])
        self.assertIn(f"- {item['id']} 卡上手改的標籤不合字典 ", self.kb("pending", "list").stdout, "裁定 8")
        self.assertEqual(entry(self.V, E.XINYI)["tags"]["階段"], "施工")
        r = self.kb("entity", "tag", "信義王", "階段=施工")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.run_check()
        (item,) = [i for i in pending.load(self.V)["items"] if i["kind"] == "tag_edit"]
        self.assertEqual(item["status"], "done")


class Absorb(Base):
    """裁定 11：重寫綜合卡前先收她的手改；裁定 12：整行拿掉是說「沒有」。"""
    edit = HandEdit.edit
    opening = HandEdit.opening

    def batch(self):
        from datetime import datetime
        E.write_card(self.V, E.QUOTE, "信義王報價", ["信義王"])  # 信義王多一張卡：綜合卡要更新
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        (self.V / batches.BATCHES_POSIX).write_text(json.dumps({"schema_version": 1, "agents": [], "jobs": [
            {"job": "j-1", "session_id": SID, "turn": self.t, "status": "open"}], "batches": [
            {"batch": "b-1", "job": "j-1", "kind": "synthesis", "items": [E.XINYI], "created": now, "status": "open"}]}),
            encoding="utf-8")
        return [i for i in batches.batch_view(self.V, "b-1")["items"] if i["entity_id"] == E.XINYI]

    def test_batch_header_is_her_edit(self):
        self.edit("階段: 施工", "階段: 完工")
        (item,) = self.batch()
        self.assertIn("階段: 完工", E.stale_header(self.V, item).splitlines())
        self.assertEqual(item["tags_said"], ["階段"])
        self.assertEqual(entry(self.V, E.XINYI)["tags"]["階段"], "完工")

    def test_outside_dictionary_not_dispatched(self):
        self.edit("階段: 施工", "階段: 暫停")
        self.assertEqual(self.batch(), [])
        (item,) = [i for i in pending.load(self.V)["items"] if i["kind"] == "tag_edit"]
        self.assertEqual((item["status"], item["entity_ids"]), ("open", [E.XINYI]))
        parts = batches._skip_entities(self.V, batches.split(self.V, batches._collect(self.V)), batches.absorb_tag_edits(self.V, self.t))
        self.assertNotIn(E.XINYI, [k for _b, k, _i in parts["synthesis"]], "已在問、卡還沒改好：dispatch 也不派")

    def broken_not_dispatched(self, old, new):
        """補驗：卡上有字典外的詞（或單選兩詞）驗卡判成壞的，進 synthesis_broken；照樣不派、tag_edit 開著、健檢不自動 done。"""
        self.edit(old, new)
        t2 = turn.start(self.V, SID, "整理")["turn"]
        before = batches.split(self.V, batches._collect(self.V))
        self.assertIn(("synthesis_broken", T.XINYI_REL), [(b, k) for b, k, _i in before["synthesis"]], "前提：壞卡桶")
        parts = batches._skip_entities(self.V, before, batches.absorb_tag_edits(self.V, t2))
        self.assertNotIn(T.XINYI_REL, [k for _b, k, _i in parts["synthesis"]])
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        (self.V / batches.BATCHES_POSIX).write_text(json.dumps({"schema_version": 1, "agents": [], "jobs": [
            {"job": "j-1", "session_id": SID, "turn": t2, "status": "open"}], "batches": [
            {"batch": "b-1", "job": "j-1", "kind": "synthesis", "items": [T.XINYI_REL], "created": now, "status": "open"}]}),
            encoding="utf-8")
        self.assertEqual(batches.batch_view(self.V, "b-1")["items"], [])
        c = L.ctx(self.V)
        for f in tag_edits.run(c):
            f["apply"](c)
        (item,) = [i for i in pending.load(self.V)["items"] if i["kind"] == "tag_edit"]
        self.assertEqual((item["status"], item["entity_ids"]), ("open", [E.XINYI]))
        return item

    def test_broken_outside_dictionary_not_dispatched(self):
        item = self.broken_not_dispatched("工種: [水電, 木作]", "工種: [水電, 狗]")
        self.assertIn("狗", item["text"])
        self.assertEqual(entry(self.V, E.XINYI)["tags"]["工種"], ["水電", "木作"])

    def test_broken_single_two_words_not_dispatched(self):
        item = self.broken_not_dispatched("階段: 施工", "階段: [施工, 完工]")
        self.assertEqual(item["text"], "信義王的卡上「階段」寫了 2 個詞，這一欄只能選一個：要留哪一個？")

    def test_dropped_line_is_none_and_kept(self):
        self.edit("階段: 施工\n", "")
        self.assertIn(OPENING_ONE,
                      self.opening())
        r = self.kb("entity", "tag", "--from-card")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "照你在卡上改的記下了：信義王 階段 沒有"))
        e = entry(self.V, E.XINYI)
        self.assertEqual((e["tags"]["階段"], e["tags_said"]), ("", ["階段"]))
        self.assertIn("階段: []\n", (self.V / T.XINYI_REL).read_text(encoding="utf-8"), "渲染照正本寫回空的")
        self.assertFalse([x for x in self.opening() if x.startswith("客戶在 Obsidian 卡的屬性欄改了")])
        self.kb("profile", "add", "標籤", "型別=案子", "欄名=預算", "詞=高、中")
        T.write_synthesis(self.V, E.XINYI, "信義王", T.XINYI_REL, ["工種: [水電, 木作]", "階段: 施工", "預算: 高"], turn_id=self.t)
        e = entry(self.V, E.XINYI)
        self.assertEqual((e["tags"]["階段"], e["tags"]["預算"]), ("", "高"), "補標籤不蓋回她說的沒有")

    def test_ai_omitted_line_written_back_not_counted(self):
        T.write_synthesis(self.V, E.XINYI, "信義王", T.XINYI_REL, ["工種: [水電, 木作]"], turn_id=self.t)
        self.assertIn("階段: 施工\n", (self.V / T.XINYI_REL).read_text(encoding="utf-8"))
        self.assertEqual(entities.tag_edits(self.V), [])


class NewEntity(Base):
    def test_after_ingest_tag_only_dispatched_same_job(self):
        """驗收 12：新實體整理完、不夠寫綜合卡 → 同一個整理的綜合卡批次裡有只補標籤的項目。"""
        parts = batches.split(self.V, batches._collect(self.V))
        keys = [k for _b, k, i in parts["synthesis"] if i.get("tag_only")]
        self.assertEqual(keys, [LI])
        (item,) = [i for b, k, i in parts["synthesis"] if k == LI]
        self.assertEqual(item["cards"][0]["title"], "內湖李估價")
        self.assertIsNone(batches._approval(self.V, self.t, parts["synthesis"], batches._settings(self.V)),
                          "只補標籤、沒有綜合卡的不算進大改動門檻")


if __name__ == "__main__":
    unittest.main()
