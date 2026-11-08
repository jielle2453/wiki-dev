"""放寬丙 第一輪 2：逐項改回。kb versions items／undo、項目的拆法、conflict、expired、journal 的 actions 欄與 md；
驗收 5～9、11，加 revert 的別名行為（驗收 10 由 test_scripts_versions_cli／test_versions_moves／test_versions_sessions 守）。"""
import contextlib
import io
import json
import shutil
from pathlib import Path

from tests.test_lib_source_edit import Base
from kb import versions
from kb._lib import agenda, items, journal, turn
from kb._lib import source_edit as se
from kb._lib import sources as sources_lib

EST = "客戶案件/內湖李/估價單.pdf"
OTHER = "報價與合約/合約範本.txt"


class UndoBase(Base):
    def setUp(self):
        super().setUp()
        self.turns = [self.t]

    def sentence(self, prompt="x"):
        """下一句：開新回合（同一個終端機 session）。"""
        self.t = turn.start(self.V, None, prompt)["turn"]
        self.turns.append(self.t)
        return self.t

    def do(self, op, target, dest=None, new_name=None):
        p = se.plan_move(self.V, sources_lib.load(self.V), target, self.V, dest=dest, new_name=new_name)
        return se.do_move(self.V, p, self.t, op)

    def undo(self, *targets, as_json=True):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = versions._undo_locked(self.V, list(targets), as_json, False)
        text = out.getvalue()
        return code, (json.loads(text) if as_json else text)

    def list_items(self, tid=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            versions._items(self.V, tid or self.t, 5, True)
        return json.loads(out.getvalue())["items"]

    def item_of(self, tid, op, what=None):
        led = items.Ledger(self.V)
        return next(it for it in led.items(tid) if it["op"] == op and (what is None or it["what"] == what))

    def agenda_items(self):
        p = Path(self.V) / ".system" / "agenda.json"
        return {i["id"]: i for i in json.loads(p.read_text(encoding="utf-8"))["items"]} if p.is_file() else {}


class ItemsListing(UndoBase):
    def test_items_lists_one_item_per_action_with_numbers(self):
        self.do("rename", EST, new_name="估價單_簽約版")
        rows = self.list_items()
        mv = [r for r in rows if r["op"] == "rename"]
        self.assertEqual(len(mv), 1)
        self.assertEqual(mv[0]["item"], f"{self.t}#{mv[0]['item'].split('#')[1]}")
        self.assertEqual((mv[0]["kind"], mv[0]["by"], mv[0]["copy"], mv[0]["undoable"]), ("file", "kb", False, True))
        self.assertTrue(mv[0]["from"].endswith("估價單.pdf") and mv[0]["to"].endswith("估價單_簽約版.pdf"))
        # 同一份清冊、卡跟著改：manifest 的 modify 也各是一項，有留一份
        mod = [r for r in rows if r["op"] == "modify"]
        self.assertTrue(mod and all(r["copy"] for r in mod))

    def test_numbers_do_not_shift_when_more_rows_are_added(self):
        self.do("rename", EST, new_name="估價單_簽約版")
        before = {r["item"]: r["op"] for r in self.list_items()}
        turn.record_move(self.V, self.t, "move", "file", "file://a/zz.txt", "file://b/zz.txt")
        after = {r["item"]: r["op"] for r in self.list_items()}
        for k, v in before.items():
            self.assertEqual(after.get(k), v)

    def test_human_listing(self):
        self.do("rename", EST, new_name="估價單_簽約版")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            versions._items(self.V, self.t, 5, False)
        self.assertIn(f"{self.t}#", out.getvalue())
        self.assertIn("改名", out.getvalue())


class UndoOneItem(UndoBase):
    def test_6_undo_only_the_rename_leaves_later_moves_and_agenda(self):
        """驗收 6：三句 (1) 改名 (2) 搬另一份 (3) 改日程 → undo 第一句的改名那項，只改回名字，其他不變，exit 0。"""
        t1 = self.t
        self.do("rename", EST, new_name="估價單_簽約版")
        self.sentence("搬另一份")
        self.do("move", str(self.raw / OTHER), dest=str(self.raw / "客戶案件" / "大安陳"))
        self.sentence("日程")
        agenda.add(self.V, kind="提醒", entities=[], text="寄發票", date="2026-12-01", turn_id=self.t)
        moved_to = self.raw / "客戶案件" / "大安陳" / "合約範本.txt"
        self.assertTrue(moved_to.is_file())
        self.sentence("改回名字")
        item = self.item_of(t1, "rename")["item"]
        code, got = self.undo(item)
        self.assertEqual(code, 0, got)
        self.assertEqual(got["done"], [item])
        self.assertTrue((self.raw / "客戶案件" / "內湖李" / "估價單.pdf").is_file())
        self.assertFalse((self.raw / "客戶案件" / "內湖李" / "估價單_簽約版.pdf").exists())
        self.assertTrue(moved_to.is_file())  # 第二句的搬動沒動
        self.assertEqual([i["text"] for i in self.agenda_items().values()], ["寄發票"])  # 第三句的日程沒動
        # 已改回的項目再看：標已改回過
        again = {r["item"]: r for r in self.list_items(t1)}
        self.assertFalse(again[item]["undoable"])
        self.assertEqual(again[item]["why"], "undone")

    def test_7_later_move_of_same_file_is_conflict_and_other_items_still_done(self):
        """驗收 7：第二句把改名後的檔搬到別夾 → 改回第一句的改名回 conflict（later 是第二句那項、now 是新位置），A 沒動；其他項照做。"""
        t1 = self.t
        self.do("rename", EST, new_name="估價單_簽約版")
        # 第一句另外還做了一件：搬另一份
        self.do("move", str(self.raw / OTHER), dest=str(self.raw / "客戶案件" / "大安陳"))
        t2 = self.sentence("把改名後的搬走")
        self.do("move", str(self.raw / "客戶案件" / "內湖李" / "估價單_簽約版.pdf"), dest=str(self.raw / "客戶案件" / "信義王"))
        self.sentence("改回第一句")
        code, got = self.undo(t1)
        self.assertEqual(code, 0, got)
        rename_item = self.item_of(t1, "rename")["item"]
        conflict = [c for c in got["conflict"] if c["item"] == rename_item]
        self.assertEqual(len(conflict), 1, got)
        c = conflict[0]
        self.assertEqual(c["why"], "later")
        self.assertEqual(c["later"][0]["item"], self.item_of(t2, "move")["item"])
        self.assertEqual(c["later"][0]["side"], "none")
        self.assertTrue(c["now"].endswith("信義王/估價單_簽約版.pdf"), c["now"])
        self.assertEqual(c["then"]["from"], "估價單.pdf")
        # A 沒動（還在第二句搬去的地方），第一句的另一項（搬合約範本）照做了
        self.assertTrue((self.raw / "客戶案件" / "信義王" / "估價單_簽約版.pdf").is_file())
        self.assertFalse((self.raw / "客戶案件" / "內湖李" / "估價單.pdf").exists())
        self.assertTrue((self.raw / OTHER).is_file())
        self.assertIn(self.item_of(t1, "move")["item"], got["done"])

    def test_8_agenda_entry_only_that_entry_is_restored(self):
        """驗收 8：一句改 a-77 的日期、下一句改 a-78 → undo 第一句只把 a-77 換回舊日期，a-78 不變。"""
        self.sentence("加兩件")
        a = agenda.add(self.V, kind="提醒", entities=[], text="甲", date="2026-12-01", turn_id=self.t)
        b = agenda.add(self.V, kind="提醒", entities=[], text="乙", date="2026-12-02", turn_id=self.t)
        aid, bid = a[0]["id"], b[0]["id"]
        t1 = self.sentence("改甲的日期")
        agenda.edit(self.V, aid, self.t, date="2026-12-09")
        self.sentence("改乙的日期")
        agenda.edit(self.V, bid, self.t, date="2026-12-10")
        self.sentence("改回")
        its = [it for it in items.Ledger(self.V).items(t1) if it["src"] == "record"]
        self.assertEqual([(it["op"], it["key"]) for it in its], [("set", aid)])
        code, got = self.undo(its[0]["item"])
        self.assertEqual(code, 0, got)
        ag = self.agenda_items()
        self.assertEqual(ag[aid]["date"], "2026-12-01")
        self.assertEqual(ag[bid]["date"], "2026-12-10")

    def test_9_card_changed_again_is_conflict_with_backup_path(self):
        """驗收 9：AI 改寫一張綜合卡、下一句又改同一張 → undo 第一句回 conflict，then 帶舊版複本路徑。"""
        card = Path(self.V) / "案子" / "信義王" / "信義王.md"
        t1 = self.t
        turn.backup(self.V, "案子/信義王/信義王.md", t1)
        card.write_text("第一次改\n", encoding="utf-8")
        self.sentence("又改")
        turn.backup(self.V, "案子/信義王/信義王.md", self.t)
        card.write_text("第二次改\n", encoding="utf-8")
        self.sentence("改回第一句")
        code, got = self.undo(t1)
        self.assertEqual(code, 0, got)
        c = got["conflict"][0]
        self.assertTrue(c["then"]["backup"].endswith(f"{t1}/files/案子/信義王/信義王.md"), c)
        self.assertEqual(c["now"], "案子/信義王/信義王.md")
        self.assertEqual(card.read_text(encoding="utf-8"), "第二次改\n")

    def test_11_expired_backup_and_journal_actions_still_undo_moves(self):
        """驗收 11：把那一回合的 files/ 刪掉模擬清掉 → 改內容那項回 skipped expired；搬動那項照 moves 還能改回。"""
        t1 = self.t
        self.do("rename", EST, new_name="估價單_簽約版")
        turn.backup(self.V, "案子/信義王/信義王.md", t1)
        (Path(self.V) / "案子" / "信義王" / "信義王.md").write_text("改過\n", encoding="utf-8")
        shutil.rmtree(Path(self.V) / ".system" / "versions" / t1 / "files")
        self.sentence("改回")
        rows = {r["item"]: r for r in self.list_items(t1)}
        gone = [r for r in rows.values() if r["op"] == "modify" and r["undoable"] is False]
        self.assertTrue(gone and all(r["why"] == "expired" for r in gone))
        code, got = self.undo(t1)
        self.assertEqual(code, 0, got)
        self.assertTrue(all(s["why"] == "expired" for s in got["skipped"]), got)
        self.assertTrue((self.raw / "客戶案件" / "內湖李" / "估價單.pdf").is_file())

    def test_all_expired_exit_3(self):
        t1 = self.t
        turn.backup(self.V, "案子/信義王/信義王.md", t1)
        (Path(self.V) / "案子" / "信義王" / "信義王.md").write_text("改過\n", encoding="utf-8")
        shutil.rmtree(Path(self.V) / ".system" / "versions" / t1 / "files")
        self.sentence()
        code, got = self.undo(t1)
        self.assertEqual(code, 3, got)
        self.assertEqual(got["done"], [])

    def test_unknown_target(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = versions._undo_locked(self.V, ["20200101-000000-zz#1"], False, False)
        self.assertEqual(code, 3)
        self.assertIn("找不到", out.getvalue())

    def test_undo_of_undo_brings_it_back(self):
        """改回本身也能改回：undo 它開的回合，原來的改名又回來。"""
        self.do("rename", EST, new_name="估價單_簽約版")
        t1 = self.t
        self.sentence("改回")
        code, got = self.undo(t1)
        self.assertEqual(code, 0, got)
        acting = got["turn"]
        self.assertTrue((self.raw / "客戶案件" / "內湖李" / "估價單.pdf").is_file())
        self.sentence("取消")
        code, got2 = self.undo(acting)
        self.assertEqual(code, 0, got2)
        self.assertTrue((self.raw / "客戶案件" / "內湖李" / "估價單_簽約版.pdf").is_file())

    def test_history_is_not_the_same_field(self):
        """記帳 1a（D-337）：一句改日期、下一句改內容，兩次都加歷程 → 退第一句不算「之後又改過」，只拿掉那一行歷程與日期。"""
        self.sentence("加一件")
        aid = agenda.add(self.V, kind="提醒", entities=[], text="甲", date="2026-12-01", turn_id=self.t)[0]["id"]
        t1 = self.sentence("改日期")
        agenda.edit(self.V, aid, self.t, date="2026-12-09")
        self.sentence("改內容")
        agenda.edit(self.V, aid, self.t, text="甲改")
        self.sentence("改回")
        code, got = self.undo(t1)
        self.assertEqual(code, 0, got)
        self.assertEqual(got["conflict"], [], got)
        self.assertTrue(got["done"], got)
        it = self.agenda_items()[aid]
        self.assertEqual((it["date"], it["text"]), ("2026-12-01", "甲改"))
        self.assertEqual(len(it["history"]), 1)
        self.assertIn("text", it["history"][0]["change"])
        self.sentence("取消")
        code, got2 = self.undo(got["turn"])
        self.assertEqual(code, 0, got2)
        it = self.agenda_items()[aid]
        self.assertEqual(it["date"], "2026-12-09")
        self.assertEqual(len(it["history"]), 2)


class JournalActions(UndoBase):
    def test_5_actions_in_row_and_md_plain_language(self):
        """驗收 5：回合行有 actions，md 寫「把…從…搬到…」；偵測到 15 份（by turn）md 併成一行。"""
        self.do("move", str(self.raw / OTHER), dest=str(self.raw / "客戶案件" / "大安陳"))
        data = turn.turn_data(self.V, self.t)
        journal.begin_turn(self.V, None, data)
        journal.complete_turn(self.V, data, "好了", "搬了一份", "program", [], False)
        month = journal.month_of(self.t)
        row = [obj for _raw, obj in journal._load(self.V, month) if obj and obj.get("turn") == self.t][0]
        acts = row["actions"]
        mv = [a for a in acts if a["op"] == "move"]
        self.assertEqual((mv[0]["by"], mv[0]["kind"]), ("kb", "file"))
        self.assertTrue(mv[0]["item"].startswith(self.t + "#"))
        md = journal.md_path(self.V, month).read_text(encoding="utf-8")
        self.assertIn("把合約範本.txt從 報價與合約 搬到 大安陳", md)

        t2 = self.sentence("一次搬很多")
        rows = [{"op": "move", "kind": "file", "from": f"file://客戶案件/a/f{i}.txt", "to": f"file://客戶案件/b/f{i}.txt", "id": f"f-{i:08x}",
                 "by": "turn", "time": "2026-11-05T10:00:00"} for i in range(15)]
        turn.record_detected(self.V, t2, rows)
        d2 = turn.turn_data(self.V, t2)
        journal.begin_turn(self.V, None, d2)
        journal.complete_turn(self.V, d2, "好", "搬了", "program", [], False)
        md = journal.md_path(self.V, journal.month_of(t2)).read_text(encoding="utf-8")
        self.assertIn("這一句有 15 份檔換了位置", md)
        self.assertNotIn("f3.txt", md)

    def test_json_set_action_has_old_new_and_long_values_are_none(self):
        self.sentence("加")
        a = agenda.add(self.V, kind="提醒", entities=[], text="甲", date="2026-12-01", turn_id=self.t)
        aid = a[0]["id"]
        t1 = self.sentence("改")
        agenda.edit(self.V, aid, self.t, date="2026-12-09", text="長" * 300)
        acts = items.actions_of_turn(self.V, t1, 200)
        sets = {x["field"]: x for x in acts if x["op"] == "set"}
        self.assertEqual((sets["date"]["old"], sets["date"]["new"]), ("2026-12-01", "2026-12-09"))
        self.assertEqual(sets["text"]["old"], "甲")
        self.assertIsNone(sets["text"]["new"])  # 超過 200 字的那個值記 None

    def test_old_rows_without_actions_still_render(self):
        data = turn.turn_data(self.V, self.t)
        journal.begin_turn(self.V, None, data)
        journal.complete_turn(self.V, data, "好", "沒動", "program", [], False)
        month = journal.month_of(self.t)
        row = [obj for _raw, obj in journal._load(self.V, month) if obj and obj.get("turn") == self.t][0]
        self.assertNotIn("actions", row)
        self.assertNotIn("動了：", journal.md_path(self.V, month).read_text(encoding="utf-8"))


class Cli(UndoBase):
    def kb(self, *args):
        import os
        import subprocess
        import sys
        from tests._guard_fixture import ROOT
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "kb.py"), *args], capture_output=True, text=True,
                              encoding="utf-8", cwd=str(self.V), env=env)

    def test_items_and_undo_through_the_cli(self):
        t1 = self.t
        self.do("rename", EST, new_name="估價單_簽約版")
        self.sentence("改回")
        r = self.kb("versions", "items", "--turn", t1, "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        rename = next(x for x in json.loads(r.stdout)["items"] if x["op"] == "rename")
        r = self.kb("versions", "undo", rename["item"], "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        got = json.loads(r.stdout)
        self.assertEqual(got["done"], [rename["item"]])
        self.assertTrue((self.raw / "客戶案件" / "內湖李" / "估價單.pdf").is_file())
        r = self.kb("versions", "undo", rename["item"])  # 已經改回過：沒做事、不是 conflict → exit 3
        self.assertEqual(r.returncode, 3, r.stdout)
        r = self.kb("versions", "undo", "nope#1")
        self.assertEqual(r.returncode, 3)

    def test_revert_is_alias_of_undo_latest_and_again_cancels(self):
        self.do("rename", EST, new_name="估價單_簽約版")
        r = self.kb("versions", "revert")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("再說一次「退回」會把這次的退回取消", r.stdout)
        self.assertTrue((self.raw / "客戶案件" / "內湖李" / "估價單.pdf").is_file())
        r = self.kb("versions", "revert")  # 連兩次是取消
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.raw / "客戶案件" / "內湖李" / "估價單_簽約版.pdf").is_file())
