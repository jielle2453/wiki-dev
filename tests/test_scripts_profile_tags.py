"""標籤字典第一節第 3～5 點、第二節（D-236、D-237；驗收 4、7、8、實作疑義 2）黑箱：
kb profile add 標籤 → 第八節多一列、有綜合卡的實體記「補標籤」、cards todo 的 synthesis_stale 帶 reason；remove 標籤拒絕；
kb profile tag rename／merge／remove（詞與欄）--check 回影響與結果清單、不寫；做了只動那一行、其他行與內文位元組不變、
回合有每張卡的備份、versions revert 全部回得去；手改 md 拿掉有卡用到的詞 apply 拒絕，--rename-tag、--drop-tags 照做。"""
import json
import re
import shutil
import unittest
from pathlib import Path

from tests import _entities as E
from tests import _tags as T
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import entities, profile, turn  # noqa: E402

LI = "e-aaaa0001"
ZHANG = "e-aaaa0002"
LI_REL = "案子/內湖李/內湖李.md"
SKIP = (".system/versions/", ".system/journal/", ".system/turns/", "系統/工作日誌/", ".system/renders.json")


def tree(V):
    out = {}
    for p in sorted(Path(V).rglob("*")):
        rel = p.relative_to(V).as_posix()
        if p.is_dir() or any(rel.startswith(s) for s in SKIP) or rel.endswith((".lock", "hook-errors.log", "ledger.tsv")):
            continue
        out[rel] = p.read_bytes()
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        self.t = turn.start(self.V, None, "")["turn"]
        data = entities.load(self.V)["entities"]
        data += [E.entity(LI, "內湖李", card=True), E.entity(ZHANG, "士林張")]
        E.put_entities(self.V, data)
        T.set_tags(self.V)
        T.write_synthesis(self.V, E.XINYI, "信義王", T.XINYI_REL, ["工種: [水電, 木作]", "階段: 施工"])
        T.write_synthesis(self.V, E.DAAN, "大安陳", T.DAAN_REL, ["工種: [木作]", "階段: 報價"])
        T.write_synthesis(self.V, LI, "內湖李", LI_REL, ["工種: [水電]"])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kb(self, *args):
        return run_kb("profile", *args, cwd=self.V)

    def json_of(self, *args):
        r = self.kb(*args, "--json")
        return r.returncode, json.loads(r.stdout)

    def tags(self):
        return {(t["type"], t["field"]): t["words"] for t in profile.load(self.V)["tags"]}

    def card(self, rel):
        return (self.V / rel).read_text(encoding="utf-8")

    def line(self, rel, field):
        return next((x for x in self.card(rel).splitlines() if x.startswith(f"{field}:")), None)

    def fixes(self):
        p = self.V / ".system" / "lint.json"
        return {f["path"]: f["reason"] for f in json.loads(p.read_text(encoding="utf-8"))["synthesis_fix"]} if p.is_file() else {}

    def run_in_process(self, *argv):
        import contextlib
        import io
        import os
        from kb import cli
        out = io.StringIO()
        cwd = os.getcwd()
        os.chdir(self.V)
        try:
            with contextlib.redirect_stdout(out):
                code = cli.main(list(argv))
        finally:
            os.chdir(cwd)
        return code, out.getvalue().splitlines()


class TestRoundOne(Base):
    """測試第 1 輪後裁定 11、15、19、20、21。"""

    def test_block_list_card_merged(self):
        """裁定 11：Obsidian 存的清單（一項一行）照認，改完寫回一行、底下的項目不留。"""
        T.write_synthesis(self.V, LI, "內湖李", LI_REL, ["工種:", "  - 水電", "  - 磁磚"])
        r = self.kb("tag", "merge", "案子", "工種", "水電", "--into", "木作")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.line(LI_REL, "工種"), "工種: [木作, 磁磚]")
        self.assertNotIn("  - 水電", self.card(LI_REL))
        from kb._lib import synthesis
        self.assertEqual(synthesis.validate(self.V, LI_REL), (True, ""))

    def test_unchangeable_card_counts_as_failure(self):
        """裁定 11：算進影響、卻改不了的卡不印成功；整個不做。"""
        from unittest import mock
        from kb._lib import synthesis
        before = tree(self.V)
        with mock.patch.object(synthesis, "retag", side_effect=lambda text, *a, **k: text):
            code, lines = self.run_in_process("profile", "tag", "merge", "案子", "工種", "水電", "--into", "木作")
        self.assertEqual(code, 3)
        self.assertEqual(lines, ["2 張綜合卡的標籤行改不了（信義王、內湖李），這次沒有改；先看那幾張的檔頭再試"])
        self.assertEqual(tree(self.V), before)

    def test_drop_tags_failure_rolls_back_profile_too(self):
        """裁定 15：apply --drop-tags 改卡中途失敗，設定檔兩檔與卡一起倒回。"""
        from unittest import mock
        from kb._lib import synthesis
        md = self.V / profile.MD_POSIX
        md.write_text(md.read_text(encoding="utf-8").replace("| 案子 | 工種 | 水電、木作、磁磚、系統櫃 |",
                                                             "| 案子 | 工種 | 木作、磁磚、系統櫃 |"),
                      encoding="utf-8", newline="\n")
        before = tree(self.V)
        real = synthesis.retag
        calls = []

        def flaky(text, *a, **k):
            calls.append(1)
            if len(calls) == 2:
                raise PermissionError(13, "被別的程式開著")
            return real(text, *a, **k)
        with mock.patch.object(synthesis, "retag", side_effect=flaky):
            code, lines = self.run_in_process("profile", "apply", "--drop-tags")
        self.assertEqual(code, 3)
        self.assertEqual(tree(self.V), before)
        self.assertEqual(self.kb("apply", "--drop-tags").returncode, 0, "倒回後重試走得通")

    def test_reserved_type_words_allowed_and_fullwidth_comma_refused(self):
        """裁定 19：詞與欄名不套型別保留字；詞另擋全形逗號。"""
        r = self.kb("add", "標籤", "型別=案子", "欄名=系統", "詞=收件匣、知識庫")
        self.assertEqual(r.returncode, 0, r.stdout)
        r = self.kb("add", "標籤", "型別=案子", "欄名=工種", "詞=甲，乙")
        self.assertEqual(r.returncode, 3)
        self.assertIn("含不能用的字元", r.stdout)

    def test_apply_from_with_tag_flags_refused(self):
        """裁定 20：apply --from 同時給 --drop-tags／--rename-tag 拒絕。"""
        md = self.V / profile.MD_POSIX
        for flags in (("--drop-tags",), ("--rename-tag", "案子", "工種", "水電", "水電工程")):
            r = self.kb("apply", "--from", str(md), *flags)
            self.assertEqual((r.returncode, r.stdout.strip()), (3, "apply --from 不能跟 --drop-tags、--rename-tag 一起用"))

    def test_add_errors_talk_fields(self):
        """裁定 21：經 add 改的錯誤句講欄位，不講節與列。"""
        cases = [(("型別=不存在", "欄名=在意", "詞=醫療"), "型別「不存在」不在設定檔第一節"),
                 (("型別=案子", "欄名=旅行", "詞=甲、甲"), "「旅行」的詞有重複：甲"),
                 (("型別=案子", "欄名=名稱", "詞=甲"), "欄名「名稱」不能用（是綜合卡檔頭原有的鍵）"),
                 (("型別=案子", "欄名=旅行", "詞=甲", "可多選=要"), "可多選只能打 ✓ 或留空"),
                 (("型別=案子", "欄名=旅行", "詞=甲[乙"), "詞「甲[乙」不能用（含不能用的字元）")]
        for fields, want in cases:
            with self.subTest(fields=fields):
                r = self.kb("add", "標籤", *fields)
                self.assertEqual((r.returncode, r.stdout.strip()), (3, want))


class RealFlow(Base):
    """裁定 25、28：照真流程——kb profile add 標籤（12 張要補標，其中 1 張另有新口述）→ cards dispatch 直接派、不回 approval，
    job 回合核准、守門寫第 11 張起不擋。"""

    def test_add_tag_then_dispatch_without_approval(self):
        from kb._lib import batches, statements
        data = entities.load(self.V)["entities"]
        more = [E.entity(f"e-bbbb000{i}", f"案{i}", card=True) for i in range(9)]
        E.put_entities(self.V, data + more)
        for e in more:
            T.write_synthesis(self.V, e["id"], e["name"], f"案子/{e['name']}/{e['name']}.md", ["工種: [水電]"])
        statements.add(self.V, "內湖李改用系統櫃", ["內湖李"], turn.current(self.V)["turn"])
        r = self.kb("add", "標籤", "型別=案子", "欄名=預算", "詞=高、中")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("12 張案子的綜合卡要補標籤", r.stdout)
        sid = "sid-real"
        t = turn.start(self.V, sid, "現在補標籤")["turn"]
        real = batches._collect  # 這個假知識庫還有沒整理的原檔：只拿掉做卡與日程，綜合卡照真的 todo 算
        self.addCleanup(setattr, batches, "_collect", real)
        batches._collect = lambda v: dict(real(v), new=[], stale=[], unlinked=[], agenda_recheck=[], agenda_unscanned=[])
        got = batches.dispatch(self.V, sid, t)
        self.assertIsNone(got["approval"])
        self.assertEqual(sum(b["items"] for b in got["batches"]), 12)
        self.assertTrue(turn.turn_data(self.V, t).get("approved"))
        for rel in [T.XINYI_REL, T.DAAN_REL, LI_REL] + [f"案子/{e['name']}/{e['name']}.md" for e in more]:
            ok, code, _r = turn.before_write(self.V, str(self.V / rel), str(self.V), "Z1", sid, t)
            self.assertEqual((ok, code), (True, ""), rel)


class AddTag(Base):
    def test_add_field_then_word_marks_retag(self):
        r = self.kb("add", "標籤", "型別=案子", "欄名=預算", "詞=高、中", "可多選=✓")
        self.assertEqual((r.returncode, r.stdout.splitlines()[0]), (0, "已加標籤欄：案子的預算（高、中）；3 張案子的綜合卡要補標籤"))
        self.assertEqual(self.tags()[("案子", "預算")], ["高", "中"])
        self.assertEqual(self.fixes(), {T.XINYI_REL: "補標籤（預算）", T.DAAN_REL: "補標籤（預算）", LI_REL: "補標籤（預算）"})
        r = self.kb("add", "標籤", "型別=案子", "欄名=工種", "詞=油漆、拆除")
        self.assertEqual((r.returncode, r.stdout.splitlines()[0]), (0, "已加標籤的詞：案子的工種多了油漆、拆除；3 張案子的綜合卡要補標籤"))
        self.assertEqual(self.fixes()[T.XINYI_REL], "補標籤（預算）、補標籤（工種：油漆／拆除）")
        todo = json.loads(run_kb("cards", "todo", "--json", cwd=self.V).stdout)
        got = {i["path"]: i.get("reason") for i in todo["synthesis_stale"]}
        self.assertEqual(got[LI_REL], "補標籤（預算）、補標籤（工種：油漆／拆除）")
        self.assertEqual(todo["profile"]["tags"]["案子"][0]["field"], "工種")

    def test_remove_refused(self):
        r = self.kb("remove", "標籤", "型別=案子", "欄名=工種")
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "拿掉標籤的詞或欄用 kb profile tag remove（會先算有幾張卡用到）"))

    def test_bad_word_refused_writes_nothing(self):
        before = tree(self.V)
        r = self.kb("add", "標籤", "型別=案子", "欄名=工種", "詞=油[漆")
        self.assertEqual(r.returncode, 3)
        self.assertIn("不能用（含不能用的字元）", r.stdout)
        self.assertEqual(tree(self.V), before)


class TagCommands(Base):
    def test_merge_check_shape(self):
        before = tree(self.V)
        code, got = self.json_of("tag", "merge", "案子", "工種", "水電", "--into", "木作", "--check")
        self.assertEqual(code, 0)
        self.assertEqual(got, {
            "op": "merge", "type": "案子", "field": "工種", "word": "水電", "target": "木作",
            "impact": {"cards": 2, "both": 1},
            "question": "案子卡有 2 張標了水電，其中 1 張也標了木作；併起來 2 張都只剩木作。要併嗎？",
            "results": [{"n": 1, "label": "併成木作", "do": ["kb profile tag merge 案子 工種 水電 --into 木作"], "strict": True,
                         "fill": []},
                        {"n": 2, "label": "先不要", "do": [], "strict": False, "fill": []}],
            "refusal": None})
        r = self.kb("tag", "merge", "案子", "工種", "水電", "--into", "木作", "--check")
        self.assertEqual(r.stdout.splitlines()[0], "案子卡有 2 張標了水電，其中 1 張也標了木作")
        self.assertEqual(tree(self.V), before, "--check 不寫")

    def test_merge_does_and_reverts(self):
        before = tree(self.V)
        body_before = {rel: self.card(rel) for rel in (T.XINYI_REL, T.DAAN_REL, LI_REL)}
        r = self.kb("tag", "merge", "案子", "工種", "水電", "--into", "木作")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(r.stdout.strip(), "已把「水電」併進「木作」：2 張卡只剩木作；不對可以說退回")
        self.assertEqual(self.tags()[("案子", "工種")], ["木作", "磁磚", "系統櫃"])
        self.assertEqual(self.line(T.XINYI_REL, "工種"), "工種: [木作]")
        self.assertEqual(self.line(LI_REL, "工種"), "工種: [木作]")
        self.assertEqual(self.card(T.DAAN_REL), body_before[T.DAAN_REL])
        self.assertEqual(self.card(T.XINYI_REL), body_before[T.XINYI_REL].replace("工種: [水電, 木作]", "工種: [木作]"),
                         "其他行與內文不變")
        files = self.V / ".system" / "versions" / turn.current(self.V)["turn"] / "files"
        for rel in (T.XINYI_REL, LI_REL, profile.PROFILE_POSIX, profile.MD_POSIX):
            self.assertTrue((files / rel).is_file(), rel)
        self.assertEqual(re.findall(r"[aefsrcp]-[0-9a-f]{8}", r.stdout), [])
        rv = run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(rv.returncode, 0, rv.stdout)
        self.assertEqual(tree(self.V), before)

    def test_rename_word(self):
        code, got = self.json_of("tag", "rename", "案子", "工種", "水電", "--to", "水電工程", "--check")
        self.assertEqual((code, got["impact"], got["results"][0]["do"], got["results"][0]["strict"]),
                         (0, {"cards": 2, "both": 0}, ["kb profile tag rename 案子 工種 水電 --to 水電工程"], False))
        before = tree(self.V)
        r = self.kb("tag", "rename", "案子", "工種", "水電", "--to", "水電工程")
        self.assertEqual(r.stdout.strip(), "已把「工種」的「水電」改叫「水電工程」：2 張卡跟著改；不對可以說退回")
        self.assertEqual(self.tags()[("案子", "工種")], ["水電工程", "木作", "磁磚", "系統櫃"])
        self.assertEqual(self.line(T.XINYI_REL, "工種"), "工種: [水電工程, 木作]")
        run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(tree(self.V), before)

    def test_rename_word_to_existing_points_to_merge(self):
        r = self.kb("tag", "rename", "案子", "工種", "水電", "--to", "木作")
        self.assertEqual((r.returncode, r.stdout.strip()),
                         (3, "「木作」已經在「工種」的字典裡；要併在一起用 kb profile tag merge 案子 工種 水電 --into 木作"))

    def test_remove_word_single_and_multi(self):
        before = tree(self.V)
        code, got = self.json_of("tag", "remove", "案子", "階段", "施工", "--check")
        self.assertEqual((got["impact"], got["results"][0]["strict"]), ({"cards": 1, "both": 0}, True))
        r = self.kb("tag", "remove", "案子", "階段", "施工")
        self.assertEqual(r.stdout.strip(), "已從「階段」拿掉「施工」：1 張卡上一起拿掉；不對可以說退回")
        self.assertEqual(self.line(T.XINYI_REL, "階段"), "階段: []")
        self.assertEqual(self.tags()[("案子", "階段")], ["報價", "完工"])
        run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(tree(self.V), before)
        self.kb("tag", "remove", "案子", "工種", "水電")
        self.assertEqual(self.line(LI_REL, "工種"), "工種: []")
        self.assertEqual(self.line(T.XINYI_REL, "工種"), "工種: [木作]")

    def test_rename_and_remove_field(self):
        before = tree(self.V)
        code, got = self.json_of("tag", "rename", "案子", "工種", "--to", "做什麼", "--check")
        self.assertEqual((got["impact"], got["field"], got["target"]), ({"cards": 3, "both": 0}, "工種", "做什麼"))
        r = self.kb("tag", "rename", "案子", "工種", "--to", "做什麼")
        self.assertEqual(r.stdout.strip(), "已把標籤欄「工種」改叫「做什麼」：3 張卡跟著改；不對可以說退回")
        self.assertEqual(self.line(T.XINYI_REL, "做什麼"), "做什麼: [水電, 木作]")
        self.assertIsNone(self.line(T.XINYI_REL, "工種"))
        run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(tree(self.V), before)
        r = self.kb("tag", "remove", "案子", "階段", "--check")
        self.assertIn("案子卡有 2 張寫了「階段」這一行", r.stdout.splitlines()[0])
        r = self.kb("tag", "remove", "案子", "階段")
        self.assertEqual(r.stdout.strip(), "已拿掉標籤欄「階段」：2 張卡拿掉這一行；不對可以說退回")
        self.assertIsNone(self.line(T.XINYI_REL, "階段"))
        self.assertNotIn(("案子", "階段"), self.tags())
        run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(tree(self.V), before)

    def test_refusals(self):
        before = tree(self.V)
        cases = [
            (("tag", "remove", "案子", "預算"), "第八節沒有「預算」這個標籤欄；有：工種、階段"),
            (("tag", "remove", "案子", "工種", "油漆"), "「工種」的字典沒有「油漆」；有：水電、木作、磁磚、系統櫃"),
            (("tag", "merge", "案子", "工種", "水電", "--into", "油漆"), "「工種」的字典沒有「油漆」；有：水電、木作、磁磚、系統櫃"),
            (("tag", "merge", "案子", "工種", "水電", "--into", "水電"), "「水電」跟「水電」是同一個"),
            (("tag", "rename", "案子", "工種", "--to", "階段"), "「案子」已經有「階段」這個標籤欄"),
            (("tag", "rename", "案子", "工種", "水電", "--to", "水[電"), None),
        ]
        for args, want in cases:
            with self.subTest(args=args):
                r = self.kb(*args)
                self.assertEqual(r.returncode, 3, r.stdout)
                if want:
                    self.assertEqual(r.stdout.strip(), want)
        self.assertEqual(tree(self.V), before)

    def test_keeps_retag_mark_after_rewrite(self):
        """補標籤記號跟著卡的新指紋：tag 指令改了卡，之前標的補標籤還算數。"""
        self.kb("add", "標籤", "型別=案子", "欄名=預算", "詞=高")
        self.kb("tag", "merge", "案子", "工種", "水電", "--into", "木作")
        todo = json.loads(run_kb("cards", "todo", "--json", cwd=self.V).stdout)
        self.assertEqual({i["path"] for i in todo["synthesis_stale"] if i.get("reason")}, {T.XINYI_REL, T.DAAN_REL, LI_REL})


class TypeOps(Base):
    def test_type_rename_keeps_tags(self):
        r = self.kb("type", "rename", "案子", "--to", "工程")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(set(self.tags()), {("工程", "工種"), ("工程", "階段")})
        from kb._lib import synthesis
        self.assertEqual(synthesis.validate(self.V, "工程/信義王/信義王.md"), (True, ""))

    def test_type_remove_drops_tags(self):
        T.set_tags(self.V, T.DEFAULT_TAGS + (T.tag("業主", "在意", ["醫療"]),))
        r = self.kb("type", "remove", "業主")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn(("業主", "在意"), self.tags())

    def test_type_merge_merges_tags_and_reverts(self):
        """裁定 6：合併時來源型別的列併進目標（同名欄併詞、目標沒有的欄整列帶過去、可多選任一有勾），卡上標籤行照留、驗得過。"""
        T.set_tags(self.V, T.DEFAULT_TAGS + (T.tag("業主", "工種", ["油漆", "水電"], False),))
        before = tree(self.V)
        r = self.kb("type", "merge", "案子", "--into", "業主")
        self.assertEqual(r.returncode, 0, r.stdout)
        rows = {(t["type"], t["field"]): t for t in profile.load(self.V)["tags"]}
        self.assertEqual(set(rows), {("業主", "工種"), ("業主", "階段")})
        self.assertEqual(rows[("業主", "工種")]["words"], ["油漆", "水電", "木作", "磁磚", "系統櫃"])
        self.assertTrue(rows[("業主", "工種")]["multi"])
        self.assertEqual((rows[("業主", "階段")]["words"], rows[("業主", "階段")]["multi"]), (["報價", "施工", "完工"], False))
        from kb._lib import synthesis
        self.assertEqual(self.line("業主/信義王/信義王.md", "工種"), "工種: [水電, 木作]")
        self.assertEqual(synthesis.validate(self.V, "業主/信義王/信義王.md"), (True, ""))
        rv = run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(rv.returncode, 0, rv.stdout)
        self.assertEqual(tree(self.V), before)

    def test_type_merge_too_many_words_refused(self):
        T.set_tags(self.V, (T.tag("案子", "工種", [f"甲{i}" for i in range(20)]),
                            T.tag("業主", "工種", [f"乙{i}" for i in range(20)])))
        before = tree(self.V)
        r = self.kb("type", "merge", "案子", "--into", "業主")
        self.assertEqual((r.returncode, r.stdout.strip()),
                         (3, "併過去之後「業主／工種」會有 40 個詞，超過 30 個；先拿掉一些再併"))
        self.assertEqual(tree(self.V), before)


class HandEdit(Base):
    def edit_md(self, old, new):
        md = self.V / profile.MD_POSIX
        text = md.read_text(encoding="utf-8")
        self.assertIn(old, text)
        md.write_text(text.replace(old, new), encoding="utf-8", newline="\n")

    def test_drop_used_word_refused_then_drop_tags(self):
        self.edit_md("| 案子 | 階段 | 報價、施工、完工 |", "| 案子 | 階段 | 報價、完工 |")
        before = tree(self.V)
        code, got = self.json_of("apply")
        self.assertEqual(code, 3)
        self.assertEqual(got["message"], "第八節拿掉了「案子／階段」的「施工」，有 1 張綜合卡用到；沒有套用")
        labels = [(r["label"], r["do"], r["strict"]) for r in got["results"]]
        self.assertEqual(labels, [("卡上的施工一起拿掉，照你改的套用", ["kb profile apply --drop-tags"], True),
                                  ("其實是要併到別的詞：先把第八節那格改回去，再跟我說施工併到哪個", [], False),
                                  ("先不套用", [], False)])
        self.assertTrue(got["results"][1].get("note"))
        self.assertEqual(tree(self.V), before)
        r = self.kb("apply", "--drop-tags")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.line(T.XINYI_REL, "階段"), "階段: []")
        self.assertEqual(self.tags()[("案子", "階段")], ["報價", "完工"])

    def test_one_out_one_in_offers_rename_tag(self):
        self.edit_md("| 案子 | 工種 | 水電、木作、磁磚、系統櫃 |", "| 案子 | 工種 | 水電工程、木作、磁磚、系統櫃 |")
        code, got = self.json_of("apply")
        self.assertEqual(code, 3)
        first = got["results"][0]
        self.assertEqual((first["label"], first["do"], first["strict"]),
                         ("「水電」改叫「水電工程」，卡上一起換", ["kb profile apply --rename-tag 案子 工種 水電 水電工程"], False))
        r = self.kb("apply", "--rename-tag", "案子", "工種", "水電", "水電工程")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.line(T.XINYI_REL, "工種"), "工種: [水電工程, 木作]")
        self.assertEqual(self.line(LI_REL, "工種"), "工種: [水電工程]")

    def test_unused_removal_applies(self):
        self.edit_md("| 案子 | 工種 | 水電、木作、磁磚、系統櫃 |", "| 案子 | 工種 | 水電、木作、磁磚 |")
        r = self.kb("apply")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.tags()[("案子", "工種")], ["水電", "木作", "磁磚"])

    def test_flags_without_matching_removal_refused(self):
        self.edit_md("| 案子 | 工種 | 水電、木作、磁磚、系統櫃 |", "| 案子 | 工種 | 水電、木作、磁磚 |")
        r = self.kb("apply", "--drop-tags")
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "第八節沒有拿掉卡上用到的詞或欄，不用 --drop-tags"))
        r = self.kb("apply", "--rename-tag", "案子", "工種", "水電", "水電工程")
        self.assertEqual((r.returncode, r.stdout.strip()),
                         (3, "--rename-tag 案子 工種 水電 水電工程 對不上第八節的改動（要拿掉一個有卡用到的詞、多一個詞）"))

    def test_add_word_by_hand_marks_retag(self):
        self.edit_md("| 案子 | 工種 | 水電、木作、磁磚、系統櫃 |", "| 案子 | 工種 | 水電、木作、磁磚、系統櫃、油漆 |")
        r = self.kb("apply")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.fixes()[LI_REL], "補標籤（工種：油漆）")

    def test_unticking_multi_with_multi_word_cards_refused(self):
        """裁定 7：手改拿掉可多選的勾、卡上有兩個以上的詞 → 拒絕、結果清單只有先不套用；沒有這種卡照常套用。"""
        self.edit_md("| 案子 | 工種 | 水電、木作、磁磚、系統櫃 | ✓ |", "| 案子 | 工種 | 水電、木作、磁磚、系統櫃 |  |")
        before = tree(self.V)
        code, got = self.json_of("apply")
        self.assertEqual(code, 3)
        self.assertEqual(got["message"], "案子／工種 有 1 張卡標了兩個以上的詞；要改成單選得先拿掉多的")
        self.assertEqual([(r["label"], r["do"]) for r in got["results"]], [("先不套用", [])])
        self.assertEqual(tree(self.V), before)
        r = self.kb("apply", "--drop-tags")
        self.assertEqual(r.returncode, 3, "旗標也不放過")
        T.write_synthesis(self.V, E.XINYI, "信義王", T.XINYI_REL, ["工種: [水電]", "階段: 施工"])
        r = self.kb("apply")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertFalse(next(t for t in profile.load(self.V)["tags"] if t["field"] == "工種")["multi"])

    def test_several_removals_all_listed(self):
        """裁定 8：一次拿掉好幾個有卡用到的詞，拒絕句一行一個全部列出。"""
        self.edit_md("| 案子 | 工種 | 水電、木作、磁磚、系統櫃 |", "| 案子 | 工種 | 磁磚、系統櫃 |")
        self.edit_md("| 案子 | 階段 | 報價、施工、完工 |", "| 案子 | 階段 | 報價、完工 |")
        code, got = self.json_of("apply")
        self.assertEqual(code, 3)
        self.assertEqual(got["message"].splitlines(), [
            "第八節拿掉了「案子／工種」的「水電」，有 2 張綜合卡用到",
            "第八節拿掉了「案子／工種」的「木作」，有 2 張綜合卡用到",
            "第八節拿掉了「案子／階段」的「施工」，有 1 張綜合卡用到",
            "沒有套用"])
        self.assertEqual(got["results"][0]["label"], "卡上的這幾個詞一起拿掉，照你改的套用")
        r = self.kb("apply")
        self.assertEqual(r.stdout.strip().splitlines()[0], "第八節拿掉了「案子／工種」的「水電」，有 2 張綜合卡用到")


if __name__ == "__main__":
    unittest.main()
