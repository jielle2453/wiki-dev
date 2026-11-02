"""kb home 的「要你確認的」逐種驗（Obsidian 首頁，#22，裁定 39，D-268）：每一種題照首頁給的 argv 真的跑一遍（subprocess kb），
跑完那題要從 kb home 消失；要 Claude 接手的整題在 claude 那邊（最下面那行）。表外的種類一律在 claude。"""
import json
import re
import shutil
import unittest
from pathlib import Path

from tests import _cards
from tests import _entities as E
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import agenda, cards, entities, home, inventory, pending, rulings, turn  # noqa: E402

TODAY = "2026-10-30"


def fill_in(argv, fills):
    return [re.sub(r"\{([^{}]+)\}", lambda m: fills.get(m.group(1), m.group(0)), x) for x in argv]


class Base(unittest.TestCase):
    def setUp(self):
        self._today = agenda._today
        agenda._today = lambda: TODAY

    def tearDown(self):
        agenda._today = self._today

    def vault(self, with_entities=True):
        tmp, V, raw = E.make_entity_vault(with_entities=with_entities)
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.raw = raw
        return V

    def turn(self, V):
        return turn.start(V, None, "")["turn"]

    def build(self, V):
        return home.build(V, today=TODAY)

    def keys(self, V):
        out = self.build(V)
        return [a["key"] for a in out["confirm"]] + [a["key"] for a in out["claude"]]

    def present(self, V, prefix):
        return any(k.startswith(prefix) for k in self.keys(V))

    def ask(self, V, kind):
        got = [a for a in self.build(V)["confirm"] if a["kind"] == kind]
        self.assertEqual(len(got), 1, f"{kind} 應該在確認區一題：{[(a['kind'], a['key']) for a in self.build(V)['confirm']]}")
        return got[0]

    def to_claude(self, V, kind):
        out = self.build(V)
        self.assertEqual([a["kind"] for a in out["confirm"] if a["kind"] == kind], [], f"{kind} 不該在確認區")
        got = [a for a in out["claude"] if a["kind"] == kind]
        self.assertEqual(len(got), 1, f"{kind} 應該在 claude：{out['claude']}")
        self.assertEqual(set(got[0]), {"key", "kind", "text"})
        return got[0]

    def labels(self, ask):
        return [r["label"] for r in ask["results"]]

    def answer(self, V, ask, label, **fills):
        r = next(x for x in ask["results"] if x["label"] == label)
        for argv in [r["argv"]] + ([r["after"]] if r.get("after") else []):
            p = run_kb(*fill_in(argv, fills), cwd=V)
            self.assertEqual(p.returncode, 0, f"{label} {argv}：{p.stdout}{p.stderr}")


class Aside(Base):
    """先放著：首頁加的，非急的才有；告知的（知道了）沒有；kb 原本叫「還沒，下次再問」「之後再說」的換掉。"""

    def test_aside_label_replaces_kb_words_and_info_has_none(self):
        V = self.vault()
        asks = [
            {"id": "inbox:f-1", "key": "inbox:f-1@a", "kind": "inbox_place", "question": "放哪？", "urgent": False,
             "results": [{"label": "放到 客戶案件/大安陳", "do": ["kb source-edit move 暫存區/a.pdf --to 客戶案件/大安陳"], "fill": [], "strict": False},
                         {"label": "先放著", "do": [], "fill": [], "strict": False}]},
            {"id": "pending:p-aaaaaaaa", "key": "p-aaaaaaaa", "kind": "pending_unreadable", "question": "讀不到", "urgent": False,
             "results": [{"label": "處理好了", "do": ["kb pending resolve p-aaaaaaaa"], "fill": [], "strict": False}]},
        ]
        confirm, claude = home._confirm(V, asks)
        self.assertEqual(claude, [])
        self.assertEqual([r["label"] for r in confirm[0]["results"]], ["放到…", "先放著"])
        self.assertEqual(confirm[0]["results"][-1]["argv"], ["asks", "set-aside", "inbox:f-1@a"])
        self.assertEqual([r["label"] for r in confirm[1]["results"]], ["知道了"])
        self.assertEqual(confirm[1]["results"][0]["argv"], ["pending", "dismiss", "p-aaaaaaaa"])

    def test_urgent_has_no_aside(self):
        V = self.vault()
        ask = {"id": "conflict:a-00000001", "key": "conflict:a-00000001@a", "kind": "agenda_conflict", "question": "哪個？", "urgent": True,
               "results": [{"label": "用新版", "do": ["kb agenda edit a-00000001 --date 2026-11-02"], "fill": [], "strict": False},
                           {"label": "維持", "do": ["kb agenda recheck a-00000001"], "fill": [], "strict": False}]}
        confirm, _claude = home._confirm(V, [ask])
        self.assertEqual([r["label"] for r in confirm[0]["results"]], ["用新版", "維持", "改到某天…"])


class NotListed(Base):
    """表外的種類與要 Claude 接手的：整題在 claude，不在確認區；過期與推測的日程兩邊都不列。"""

    def test_out_of_table_kinds_go_to_claude(self):
        V = self.vault()
        asks = [{"id": f"{k}:x", "key": f"x-{k}", "kind": k, "question": f"{k}？", "urgent": False,
                 "results": [{"label": "好", "do": ["kb pending dismiss p-1"], "fill": [], "strict": False}]}
                for k in ("batch", "draft", "credential_same_kind", "carried", "pending_lint", "pending_report", "pending_conflict",
                          "pending_handedit", "pending_tag_edit", "drift_missing", "something_new")]
        confirm, claude = home._confirm(V, asks)
        self.assertEqual(confirm, [])
        self.assertEqual([c["kind"] for c in claude], [a["kind"] for a in asks])
        self.assertEqual(claude[0], {"key": "x-batch", "kind": "batch", "text": "batch？"})

    def test_overdue_listed_nowhere(self):
        V = self.vault()
        t = self.turn(V)
        agenda.add(V, "到期", "2026-10-25", "付款", ["信義王"], t)
        out = self.build(V)
        self.assertEqual([a for a in out["confirm"] if a["kind"] == "overdue"], [])
        self.assertEqual([a for a in out["claude"] if a["kind"] == "overdue"], [])
        self.assertEqual(out["counts"]["claude"], 0)

    def test_inferred_agenda_lint_listed_nowhere(self):
        V = self.vault()
        t = self.turn(V)
        pid = pending.add_lint(V, "inferred:agenda", "日程有 1 條是我從檔案推測的", {"dates": [], "results": [{"label": "一條一條看", "note": "x"}]}, t)
        self.assertFalse(self.present(V, pid))
        pid2 = pending.add_lint(V, "stale:something", "別的健檢", {"results": [{"label": "看", "note": "x"}]}, t)
        self.to_claude(V, "pending_lint")

    def test_count_is_claude_plus_others(self):
        V = self.vault()
        t = self.turn(V)
        pending.add_lint(V, "stale:something", "別的健檢", {"results": [{"label": "看", "note": "x"}]}, t)
        out = self.build(V)
        self.assertEqual(out["counts"]["claude"], len(out["claude"]) + len(out["others"]))
        self.assertGreaterEqual(out["counts"]["claude"], 1)


class AgendaConflict(Base):
    def setUp(self):
        super().setUp()

    def scene(self):
        V = self.vault()
        t = self.turn(V)
        path = E.write_card(V, E.QUOTE, "信義王報價", ["信義王"])
        front = cards.parse_front((V / path).read_text(encoding="utf-8"))
        cid, fp = front["編號"], (front.get("內容指紋") or front["指紋"])[:12]
        item, _ = agenda.add(V, "到期", "2027-03-10", "交屋", ["信義王"], t, card=cid)
        p = V / ".system" / "agenda.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["items"][0]["source"] = "confirmed"
        data["items"][0]["proposal"] = {"date": "2027-03-20", "text": "交屋", "card": cid, "fp": fp}
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return V, item["id"]

    def test_answers(self):
        V, aid = self.scene()
        ask = self.ask(V, "agenda_conflict")
        self.assertEqual(self.labels(ask), ["用新版 3/20", "維持 3/10", "改到某天…", "先放著"])
        date = ask["results"][2]
        self.assertEqual(date["fill"]["input"], "date")
        self.assertEqual(date["argv"], ["agenda", "edit", aid, "--date", "{新日期}"])
        for label, fills in (("用新版 3/20", {}), ("維持 3/10", {}), ("改到某天…", {"新日期": "2027-04-01"}), ("先放著", {})):
            with self.subTest(label=label):
                V, aid = self.scene()
                ask = self.ask(V, "agenda_conflict")
                self.answer(V, ask, label, **fills)
                self.assertFalse(self.present(V, f"conflict:{aid}"), label)


class Close(Base):
    def scene(self):
        V = self.vault()
        t = self.turn(V)
        path = E.write_card(V, E.QUOTE, "信義王報價", ["信義王"])
        fid = cards.parse_front((V / path).read_text(encoding="utf-8"))["編號"]
        pid = pending.add(V, "close", [fid], "「信義王」看起來已經結束了，要記成結案嗎？", None, t, entity_ids=[E.XINYI])
        return V, pid

    def test_three_answers_and_aside_all_finish(self):
        V, pid = self.scene()
        self.assertEqual(self.labels(self.ask(V, "close")), ["對，結案了", "還沒", "先暫停了", "先放著"])
        for label in ("對，結案了", "還沒", "先暫停了", "先放著"):
            with self.subTest(label=label):
                V, pid = self.scene()
                self.answer(V, self.ask(V, "close"), label)
                self.assertFalse(self.present(V, pid), label)


class Name(Base):
    def scene(self):
        tmp, V, raw = _cards.make_card_vault()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        E.set_profile(V)
        turn.start(V, "sid-home", "好")
        for name in ("新來的", "內湖李"):
            self.assertEqual(run_kb("entity", "add", "--type", "案子", "--name", name, cwd=V).returncode, 0)
        self.assertEqual(run_kb("entity", "add", "--type", "業主", "--name", "王先生", cwd=V).returncode, 0)
        for rel in (E.QUOTE, E.ESTIMATE, E.DRAFT, E.TEMPLATE):  # 掛夠幾張卡才會出名字題（D-114 門檻）
            E.write_card(V, rel, "卡" + rel[-6:], ["新來的"])
        return V

    def asks_of(self, V, name):
        return [a for a in self.build(V)["confirm"] if a["kind"] == "name" and name in a["text"]]

    def test_answers_and_select_options(self):
        V = self.scene()
        (ask,) = self.asks_of(V, "新來的")
        self.assertEqual(self.labels(ask), ["名字對", "改名…", "跟…同一個", "先放著"])
        merge = ask["results"][2]["fill"]
        self.assertEqual((merge["input"], merge["name"]), ("select", "同一個"))
        self.assertEqual([o["value"] for o in merge["options"]], ["內湖李"], "同型別、active 的其他實體；不同型別的（王先生）不在")
        rename = ask["results"][1]
        self.assertEqual((rename["argv"], rename["after"], rename["fill"]["input"]),
                         (["entity", "rename", "新來的", "--to", "{新名字}"], ["entity", "confirm", "{新名字}"], "text"))

    def test_each_answer_finishes_the_question(self):
        for label, fills in (("名字對", {}), ("改名…", {"新名字": "新來的宅"}), ("跟…同一個", {"同一個": "內湖李"}), ("先放著", {})):
            with self.subTest(label=label):
                V = self.scene()
                (ask,) = self.asks_of(V, "新來的")
                self.answer(V, ask, label, **fills)
                self.assertEqual(self.asks_of(V, "新來的"), [], label)
                self.assertEqual([a for a in self.build(V)["confirm"] if a["kind"] == "name" and "新來的宅" in a["text"]], [], label)


class Drift(Base):
    def moved(self, how):
        V = self.vault()
        v = V / "案子"
        if how == "folder_renamed":
            (v / "信義王").rename(v / "王宅邸")
        elif how == "both_renamed":
            (v / "信義王").rename(v / "王宅邸")
            (v / "王宅邸" / "信義王.md").rename(v / "王宅邸" / "王宅邸.md")
        elif how == "card_renamed":
            (v / "信義王" / "信義王.md").rename(v / "信義王" / "王宅邸.md")
        elif how == "moved_type":
            shutil.move(str(v / "信義王"), str(V / "業主" / "信義王"))
        elif how == "moved_unknown_type":
            (V / "廠商").mkdir()
            shutil.move(str(v / "信義王"), str(V / "廠商" / "信義王"))
        elif how == "missing":
            shutil.rmtree(v / "信義王")
        return V

    def test_renamed_kinds_finish_with_every_answer(self):
        cases = {
            "folder_renamed": ("drift_folder_renamed", ["跟著改名叫王宅邸", "改回信義王", "改成別的名字", "先放著"]),
            "both_renamed": ("drift_both_renamed", ["跟著改名叫王宅邸", "改回信義王", "改成別的名字", "先放著"]),
            "card_renamed": ("drift_card_renamed", ["用新檔名王宅邸", "改回信義王", "改成別的名字", "先放著"]),
            "moved_type": ("drift_moved_type", ["跟著改到業主", "搬回案子", "先放著"]),
        }
        for how, (kind, want) in cases.items():
            V = self.moved(how)
            ask = self.ask(V, kind)
            self.assertEqual(self.labels(ask), want, how)
            for label in want:
                with self.subTest(how=how, label=label):
                    V = self.moved(how)
                    ask = self.ask(V, kind)
                    self.answer(V, ask, label, 新名字="信義王新")
                    self.assertFalse(self.present(V, f"drift:{E.XINYI}"), (how, label))

    def test_text_input_for_other_name(self):
        ask = self.ask(self.moved("folder_renamed"), "drift_folder_renamed")
        other = next(r for r in ask["results"] if r["label"] == "改成別的名字")
        self.assertEqual((other["fill"]["input"], other["fill"]["name"]), ("text", "新名字"))

    def test_moved_to_unknown_type_has_one_answer_so_whole_ask_goes_to_claude(self):
        V = self.moved("moved_unknown_type")
        self.to_claude(V, "drift_moved_type")

    def test_missing_folder_goes_to_claude_because_rebuild_needs_claude(self):
        V = self.moved("missing")
        self.to_claude(V, "drift_missing")
        # 為什麼：entity rebuild 只把實體的 card 改成 false、不寫檔，那張綜合卡要 Claude 照檔案卡重寫
        self.turn(V)
        self.assertEqual(run_kb("entity", "rebuild", "信義王", cwd=V).returncode, 0)
        self.assertFalse(entities.find(entities.load(V), "信義王")[0]["card"])
        self.assertFalse((V / "案子" / "信義王" / "信義王.md").exists())


class Inbox(Base):
    def scene(self):
        import tests.test_scripts_intake_cli as ic
        tmp, V, raw = _cards.make_card_vault()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.tmp = Path(tmp)
        _cards.mark_dates_scanned(V)
        t0 = turn.start(V, None, "")["turn"]
        entities.add(V, "案子", "大安陳", t0)
        for item in cards.todo(V, __import__("kb._lib.sources", fromlist=["load"]).load(V))["new"]:
            if item["uri"].endswith("會議紀錄_1.docx"):
                p = _cards.write_card(V, item, "第一次會議")
                p.write_text(p.read_text(encoding="utf-8").replace("實體: []", "實體: [大安陳]"), encoding="utf-8", newline="\n")
        turn.start(V, "sid-home", "這是大安陳的合約")
        src = self.tmp / "下載" / "合約.pdf"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(b"%PDF chen")
        r = ic.run("intake", str(src), cwd=V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        (e,) = [x for x in inventory.load(V)["entries"] if x.get("origin") == "intake" and x.get("intake")]
        item = next(i for i in cards.todo(V, __import__("kb._lib.sources", fromlist=["load"]).load(V))["new"] if i["id"] == e["id"])
        p = _cards.write_card(V, item, "大安陳合約", kind="合約")
        p.write_text(p.read_text(encoding="utf-8").replace("實體: []", "實體: [大安陳]"), encoding="utf-8", newline="\n")
        return V, e["id"]

    def test_one_select_candidates_first_then_all_entity_folders(self):
        V, fid = self.scene()
        ask = self.ask(V, "inbox_place")
        self.assertEqual(self.labels(ask), ["放到…", "先放著"])
        fill = ask["results"][0]["fill"]
        self.assertEqual((fill["name"], fill["input"]), ("放到", "select"))
        groups = [o["group"] for o in fill["options"]]
        self.assertEqual(groups, sorted(groups, key=lambda g: g != "常放"), "候選的夾在前、全部的在後")
        self.assertEqual(fill["options"][0], {"label": "客戶案件/大安陳", "value": "客戶案件/大安陳", "group": "常放"})
        self.assertIn("案子/大安陳", [o["value"] for o in fill["options"] if o["group"] == "全部"])
        self.assertEqual(len({o["value"] for o in fill["options"]}), len(fill["options"]), "不重複")

    def test_pick_any_option_moves_the_file_and_the_ask_goes_away(self):
        for choice in ("客戶案件/大安陳", "案子/大安陳"):
            with self.subTest(choice=choice):
                V, fid = self.scene()
                self.answer(V, self.ask(V, "inbox_place"), "放到…", 放到=choice)
                self.assertFalse(self.present(V, f"inbox:{fid}"))
                self.assertFalse((V / "暫存區" / "合約.pdf").exists())

    def test_aside_finishes(self):
        V, fid = self.scene()
        self.answer(V, self.ask(V, "inbox_place"), "先放著")
        self.assertFalse(self.present(V, f"inbox:{fid}"))


class InferredAgenda(Base):
    """推測的日程改在日程確認（對、改到某天、不用了）：答完那條不再是推測，下一次 kb lint 把「推測放太久」那件自己關掉。"""

    def scene(self):
        V = self.vault()
        t = self.turn(V)
        path = E.write_card(V, E.QUOTE, "信義王報價", ["信義王"])
        cid = cards.parse_front((V / path).read_text(encoding="utf-8"))["編號"]
        item, _ = agenda.add(V, "到期", "2027-03-10", "交屋", ["信義王"], t, card=cid)
        p = V / ".system" / "agenda.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["items"][0]["created_turn"] = "20250101-100000-abcd"
        data["items"][0]["history"] = []
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(run_kb("lint", cwd=V).returncode, 0)
        (lint,) = [i for i in pending.load(V)["items"] if i.get("key") == "inferred:agenda"]
        self.assertEqual(lint["status"], "open")
        return V, item["id"], lint["id"]

    def test_three_answers_close_the_lint_item_next_run(self):
        for argv_tail in ((), ("--date", "2027-04-01"), None):
            with self.subTest(answer=argv_tail):
                V, aid, pid = self.scene()
                self.assertFalse(self.present(V, pid), "首頁不列這件")
                self.assertTrue(next(i for i in agenda.load(V)["items"] if i["id"] == aid)["source"] == "inferred")
                argv = ["agenda", "cancel", aid] if argv_tail is None else ["agenda", "edit", aid, *argv_tail]
                self.assertEqual(run_kb(*argv, cwd=V).returncode, 0)
                self.assertEqual(run_kb("lint", cwd=V).returncode, 0)
                (lint,) = [i for i in pending.load(V)["items"] if i["id"] == pid]
                self.assertEqual(lint["status"], "done")


class MissingSource(Base):
    def scene(self):
        tmp, V, raw = _cards.make_card_vault()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        (raw / _cards.MEETING).unlink()
        _cards.scan_apply(V)
        return V

    def test_two_answers_and_aside_finish(self):
        V = self.scene()
        ask = self.ask(V, "missing")
        self.assertEqual(self.labels(ask), ["刪了，卡也拿掉", "卡留著", "先放著"])
        self.assertEqual(ask["results"][1]["argv"][:3], ["pending", "resolve", ask["key"]])
        self.assertEqual(ask["results"][1]["argv"][3:], ["--how", "客戶說卡留著"], "不用她打字")
        for label in ("刪了，卡也拿掉", "卡留著", "先放著"):
            with self.subTest(label=label):
                V = self.scene()
                ask = self.ask(V, "missing")
                self.answer(V, ask, label)
                self.assertFalse(self.present(V, ask["key"]), label)


class RulingRecheck(Base):
    def scene(self):
        V = self.vault()
        t = self.turn(V)
        path = E.write_card(V, E.CONTRACT, "合約", ["信義王"])
        front = cards.parse_front((V / path).read_text(encoding="utf-8"))
        cid, fp = front["編號"], (front.get("內容指紋") or front["指紋"])[:12]
        item = rulings.add(V, "不採用", [], [cid], "合約.docx 是舊的，別信", turn_id=t)
        p = V / path
        p.write_text(p.read_text(encoding="utf-8").replace(fp, "b" * 12, 1), encoding="utf-8")
        return V, item["id"]

    def test_both_answers_and_aside_finish(self):
        V, rid = self.scene()
        ask = self.ask(V, "ruling_recheck")
        self.assertEqual(self.labels(ask), ["可以了", "還是別信", "先放著"])
        for label in ("可以了", "還是別信", "先放著"):
            with self.subTest(label=label):
                V, rid = self.scene()
                self.answer(V, self.ask(V, "ruling_recheck"), label)
                self.assertFalse(self.present(V, f"ruling:{rid}"), label)


class Info(Base):
    def test_unreadable_and_script_touched_only_known(self):
        for kind in ("unreadable", "script_touched"):
            with self.subTest(kind=kind):
                V = self.vault()
                t = self.turn(V)
                fid = _cards.entry_of(V, E.QUOTE)["id"]
                pid = pending.add(V, kind, [fid], "有一份檔", "有密碼" if kind == "unreadable" else None, t)
                ask = self.ask(V, f"pending_{kind}")
                self.assertEqual(self.labels(ask), ["知道了"])
                self.assertEqual(ask["results"][0]["argv"], ["pending", "dismiss", pid])
                self.answer(V, ask, "知道了")
                self.assertFalse(self.present(V, pid))


class ClaudeSide(Base):
    """手改、標籤、健檢、報告、兩份寫法不同、草稿：真的建出來，確認它們在 claude（要 Claude 接手）。"""

    def test_pending_kinds(self):
        V = self.vault()
        t = self.turn(V)
        fid = _cards.entry_of(V, E.QUOTE)["id"]
        pending.add_handedit(V, "系統/日程.md", ".system/handedits/x.md", {"checked": [], "removed": [], "changed_date": [], "other": ["（比對不出改了哪裡）"]}, t)
        pending.add_tag_edit(V, E.XINYI, "信義王的標籤改過了", {"fields": [], "results": []}, t)
        pending.add_lint(V, "stale:something", "健檢查到的", {"results": [{"label": "看", "note": "x"}]}, t)
        pending.add_report(V, "2026-10", t)
        cid2 = _cards.entry_of(V, E.ESTIMATE)["id"]
        pending.add_conflict(V, [fid, cid2], "兩份寫法不同", t)
        for kind in ("pending_handedit", "pending_tag_edit", "pending_lint", "pending_report", "pending_conflict"):
            self.to_claude(V, kind)

    def test_draft(self):
        V = self.vault()
        d = V / "暫存區" / "報告"
        d.mkdir(parents=True)
        (d / "2026-10-21 內湖李 進度報告（草稿）.md").write_text("草稿", encoding="utf-8")
        self.to_claude(V, "draft")


if __name__ == "__main__":
    unittest.main()
