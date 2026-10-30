"""kb renders apply／drop（Obsidian 首頁，#22，D-263）與重新產生時認出手改直接照做（預設照做 6）。驗收準則 8、9。"""
import json
import shutil
import unittest

from tests import _entities as E
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import agenda, hand, pending, renders, rulings, turn  # noqa: E402

AGENDA_MD = "系統/日程.md"
PENDING_MD = "系統/待處理.md"
RULINGS_MD = "系統/裁示.md"
CARRIED = "## 你加的（還沒處理）"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        self.t = turn.start(self.V, None, "")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def md(self, rel):
        return (self.V / rel).read_text(encoding="utf-8")

    def write(self, rel, text):
        (self.V / rel).write_text(text, encoding="utf-8", newline="\n")

    def edit_lines(self, rel, fn):
        lines = self.md(rel).split("\n")
        self.write(rel, "\n".join(fn(lines)))

    def apply(self, rel, *extra):
        r = run_kb("renders", "apply", rel, "--json", *extra, cwd=self.V)
        self.assertIn(r.returncode, (0, 3), r.stdout + r.stderr)
        return r

    def report(self, rel):
        r = self.apply(rel)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def handedits(self):
        return [i for i in pending.load(self.V)["items"] if i.get("kind") == "handedit"]

    def saved_files(self):
        d = self.V / ".system" / "handedits"
        return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


class AgendaApply(Base):
    def setUp(self):
        super().setUp()
        self.a = agenda.add(self.V, "到期", "2030-03-01", "付尾款", ["信義王"], self.t)[0]["id"]
        self.b = agenda.add(self.V, "提醒", "2030-03-02", "訂窗簾", ["信義王"], self.t)[0]["id"]
        self.c = agenda.add(self.V, "承諾", "2030-03-03", "給報價", ["信義王"], self.t)[0]["id"]
        self.d = agenda.add(self.V, "會議", "2030-03-04", "丈量", ["信義王"], self.t)[0]["id"]

    def item(self, aid):
        return agenda.get(self.V, aid)

    def hand_the_four_edits(self):
        def change(lines):
            out = []
            for ln in lines:
                if "付尾款" in ln:
                    out.append(ln.replace("- ", "- [x] ", 1))
                elif "訂窗簾" in ln:
                    continue
                elif "給報價" in ln:
                    out.append(ln.replace("2030-03-03（週日）", "2030-03-10（週日）"))
                else:
                    out.append(ln)
            out.insert(len(out) - 3, "- 測試")
            return out
        self.edit_lines(AGENDA_MD, change)

    def test_8_checked_removed_changed_date_and_unknown_line(self):
        self.hand_the_four_edits()
        got = self.report(AGENDA_MD)
        self.assertEqual(self.item(self.a)["status"], "done")
        self.assertEqual(self.item(self.b)["status"], "cancelled")
        self.assertEqual(self.item(self.c)["date"], "2030-03-10")
        self.assertEqual(self.item(self.d)["status"], "open")
        self.assertEqual(got["page"], AGENDA_MD)
        self.assertEqual(len(got["applied"]), 3)
        self.assertEqual(got["carried"], ["測試"])
        text = self.md(AGENDA_MD)
        self.assertIn(CARRIED, text)
        self.assertTrue(text.rstrip().endswith("- 測試"))
        self.assertEqual([c["text"] for c in renders.carried(self.V, AGENDA_MD)], ["測試"])
        asks = json.loads(run_kb("asks", "--all", "--json", cwd=self.V).stdout)["asks"]
        (ask,) = [a for a in asks if a["kind"] == "carried"]
        self.assertIn("測試", ask["question"])
        self.assertEqual(ask["key"], renders.carried(self.V, AGENDA_MD)[0]["id"])

    def test_8_history_is_hand_and_no_handedit_opened(self):
        self.hand_the_four_edits()
        self.report(AGENDA_MD)
        for aid in (self.a, self.b, self.c):
            self.assertEqual(self.item(aid)["history"][-1]["by"], "hand", aid)
        self.assertEqual(self.handedits(), [])
        self.assertEqual(len(self.saved_files()), 1)  # 她那份照舊存

    def test_8_second_run_does_nothing(self):
        self.hand_the_four_edits()
        self.report(AGENDA_MD)
        before = self.md(AGENDA_MD)
        r = run_kb("renders", "apply", AGENDA_MD, cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "這頁沒有要照做的"))
        again = self.report(AGENDA_MD)
        self.assertEqual((again["applied"], again["carried"], again["dropped"]), ([], [], 0))
        self.assertEqual(self.md(AGENDA_MD), before)

    def test_nothing_edited(self):
        r = run_kb("renders", "apply", AGENDA_MD, cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "這頁沒有要照做的"))

    def test_changed_text_is_carried_not_cancelled(self):
        self.edit_lines(AGENDA_MD, lambda ls: [ln.replace("給報價", "給報價（延一週）") for ln in ls])
        got = self.report(AGENDA_MD)
        self.assertEqual(self.item(self.c)["status"], "open")
        self.assertEqual(got["applied"], [])
        (c,) = renders.carried(self.V, AGENDA_MD)
        self.assertEqual(c["kind"], "changed")
        self.assertIn("給報價（延一週）", c["text"])
        self.assertIn("給報價", c["orig"])
        self.assertIn("原本「", self.md(AGENDA_MD))
        self.assertIn("你改成「", self.md(AGENDA_MD))

    def test_9_without_plugin_next_command_does_the_same(self):
        self.hand_the_four_edits()
        agenda.add(self.V, "提醒", "2030-04-01", "別的", ["信義王"], self.t)
        self.assertEqual(self.item(self.a)["status"], "done")
        self.assertEqual(self.item(self.b)["status"], "cancelled")
        self.assertEqual(self.item(self.c)["date"], "2030-03-10")
        self.assertEqual(self.item(self.c)["history"][-1]["by"], "hand")
        self.assertEqual([c["text"] for c in renders.carried(self.V, AGENDA_MD)], ["測試"])
        text = self.md(AGENDA_MD)
        self.assertIn("- 測試", text)
        self.assertIn("別的", text)
        self.assertEqual(self.handedits(), [])
        self.assertTrue(any(n.endswith("日程.md") for n in self.saved_files()), "她那份照舊存")

    def test_14_consume_failure_is_only_logged_and_the_write_goes_on(self):
        """裁定 14：認手改時丟例外，只記 hook-errors.log，這次寫入照常做，之後的寫入也不會一直失敗；她那份照舊存。"""
        from unittest import mock
        self.hand_the_four_edits()
        with mock.patch.object(agenda, "_apply_hand", side_effect=RuntimeError("壞了")):
            agenda.add(self.V, "提醒", "2030-04-01", "別的", ["信義王"], self.t)
        self.assertTrue(any(i["text"] == "別的" for i in agenda.load(self.V)["items"]))
        self.assertEqual(self.item(self.a)["status"], "open")  # 半做的不留
        log = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8")
        self.assertIn("RuntimeError", log)
        self.assertEqual(len([n for n in self.saved_files() if n.endswith("日程.md")]), 1, "她那份只存一份（裁定 22）")
        (he,) = self.handedits()  # 另開一件 handedit（D-223 原本那條）
        self.assertEqual(he["data"]["file"], AGENDA_MD)
        self.assertTrue(he["data"]["saved"].startswith(".system/handedits/"))
        agenda.add(self.V, "提醒", "2030-04-02", "再一個", ["信義王"], self.t)  # 下一次寫入不再失敗
        self.assertTrue(any(i["text"] == "再一個" for i in agenda.load(self.V)["items"]))
        self.assertEqual(len(self.handedits()), 1, "同一份手改不會一直開新的")

    def test_22_apply_says_it_did_not_understand_and_recorded_it(self):
        from unittest import mock
        from kb import cli
        import contextlib
        import io
        self.hand_the_four_edits()
        out = io.StringIO()
        with mock.patch.object(agenda, "_apply_hand", side_effect=RuntimeError("壞了")), contextlib.redirect_stdout(out):
            code = cli.main(["renders", "apply", AGENDA_MD, "--vault", str(self.V)])
        self.assertEqual((code, out.getvalue().strip()), (0, "這頁你改的我沒認出來，記在待處理了"))
        self.assertEqual(len(self.handedits()), 1)
        self.assertEqual(self.item(self.a)["status"], "open")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["renders", "apply", AGENDA_MD, "--vault", str(self.V), "--json"])
        self.assertEqual(json.loads(out.getvalue())["applied"], [], "頁面已經重寫，再叫一次沒有手改")
        self.assertEqual(len(self.handedits()), 1)

    def test_22_json_flag_for_the_plugin(self):
        from unittest import mock
        from kb import cli
        import contextlib
        import io
        self.hand_the_four_edits()
        out = io.StringIO()
        with mock.patch.object(agenda, "_apply_hand", side_effect=RuntimeError("壞了")), contextlib.redirect_stdout(out):
            cli.main(["renders", "apply", AGENDA_MD, "--vault", str(self.V), "--json"])
        got = json.loads(out.getvalue())
        self.assertEqual((got["page"], got["applied"], got["carried"], got["dropped"], got["unrecognized"]), (AGENDA_MD, [], [], 0, True))

    def test_9_history_turn_is_the_triggering_turn(self):
        self.hand_the_four_edits()
        t2 = turn.start(self.V, None, "")["turn"]
        agenda.add(self.V, "提醒", "2030-04-01", "別的", ["信義王"], t2)
        self.assertEqual(self.item(self.a)["history"][-1]["turn"], t2)

    def test_dropping_a_line_in_the_carried_section_means_not_needed(self):
        self.hand_the_four_edits()
        self.report(AGENDA_MD)
        self.edit_lines(AGENDA_MD, lambda ls: [ln for ln in ls if ln != "- 測試"])
        got = self.report(AGENDA_MD)
        self.assertEqual(got["dropped"], 1)
        self.assertEqual(renders.carried(self.V, AGENDA_MD), [])
        self.assertNotIn(CARRIED, self.md(AGENDA_MD))

    def test_typing_inside_the_carried_section_is_carried_too(self):
        self.hand_the_four_edits()
        self.report(AGENDA_MD)
        self.write(AGENDA_MD, self.md(AGENDA_MD).rstrip("\n") + "\n- 另一件\n")
        got = self.report(AGENDA_MD)
        self.assertEqual(got["carried"], ["另一件"])
        self.assertEqual([c["text"] for c in renders.carried(self.V, AGENDA_MD)], ["測試", "另一件"])

    def test_checked_on_an_already_done_item_is_ignored(self):
        agenda.set_status(self.V, self.a, "done", self.t)
        md = self.md(AGENDA_MD)
        self.write(AGENDA_MD, md + "\n- [x] 隨手打的\n")
        got = self.report(AGENDA_MD)
        self.assertEqual(got["applied"], [])
        self.assertEqual(got["carried"], ["隨手打的"])

    def test_bad_date_goes_to_carried(self):
        self.edit_lines(AGENDA_MD, lambda ls: [ln.replace("2030-03-03（週日）", "2030-02-31（週日）") for ln in ls])
        got = self.report(AGENDA_MD)
        self.assertEqual(self.item(self.c)["date"], "2030-03-03")
        self.assertEqual(got["applied"], [])
        self.assertEqual(len(got["carried"]), 1)

    def test_secret_in_added_line_is_masked(self):
        self.write(AGENDA_MD, self.md(AGENDA_MD) + "\n- 密碼：abc123xyz\n")
        self.report(AGENDA_MD)
        texts = " ".join(c["text"] for c in renders.carried(self.V, AGENDA_MD))
        self.assertNotIn("abc123xyz", texts)
        self.assertNotIn("abc123xyz", self.md(AGENDA_MD))
        self.assertNotIn("abc123xyz", " ".join((self.V / ".system" / "handedits" / n).read_text(encoding="utf-8") for n in self.saved_files()))

    def test_journal_program_section(self):
        self.hand_the_four_edits()
        self.report(AGENDA_MD)
        out = run_kb("journal", "recent", "--n", "3", cwd=self.V).stdout
        self.assertIn("照你在日程.md改的：", out)
        self.assertIn("記成完成『付尾款』", out)


class PendingApply(Base):
    def setUp(self):
        super().setUp()
        self.p1 = pending.add(self.V, "unreadable", ["f-11111111"], "「甲.pdf」讀不到", "檔案壞了", self.t)
        self.p2 = pending.add(self.V, "unreadable", ["f-22222222"], "「乙.pdf」讀不到", "檔案壞了", self.t)

    def status(self, pid):
        return next(i for i in pending.load(self.V)["items"] if i["id"] == pid)

    def test_checked_resolves_removed_dismisses_and_text_is_carried(self):
        def change(lines):
            out = []
            for ln in lines:
                if "甲.pdf" in ln:
                    out.append(ln.replace("- ", "- [x] ", 1))
                elif "乙.pdf" in ln:
                    continue
                else:
                    out.append(ln)
            return out + ["- 順便提醒我打給王先生"]
        self.edit_lines(PENDING_MD, change)
        got = self.report(PENDING_MD)
        self.assertEqual((self.status(self.p1)["status"], self.status(self.p1)["how"]), ("done", "在待處理.md 打勾"))
        self.assertEqual(self.status(self.p2)["status"], "dismissed")
        self.assertEqual(len(got["applied"]), 2)
        self.assertEqual(got["carried"], ["順便提醒我打給王先生"])
        text = self.md(PENDING_MD)
        self.assertIn(CARRIED, text)
        self.assertNotIn("[x]", text)
        self.assertEqual(self.handedits(), [])

    def test_next_pending_write_applies_too(self):
        self.edit_lines(PENDING_MD, lambda ls: [ln for ln in ls if "乙.pdf" not in ln])
        pending.add(self.V, "unreadable", ["f-33333333"], "「丙.pdf」讀不到", "檔案壞了", self.t)
        self.assertEqual(self.status(self.p2)["status"], "dismissed")
        self.assertIn("丙.pdf", self.md(PENDING_MD))
        self.assertEqual(self.handedits(), [])

    def test_24_pending_page_hand_edit_goes_through_guarded(self):
        """裁定 24：待處理頁認手改出錯，資料退回、她那份只存一份、另開 handedit，寫入照常。"""
        from unittest import mock
        self.edit_lines(PENDING_MD, lambda ls: [ln.replace("- ", "- [x] ", 1) if "甲.pdf" in ln else ln for ln in ls])
        with mock.patch.object(pending, "_apply_hand", side_effect=RuntimeError("壞了")):
            pending.add(self.V, "unreadable", ["f-33333333"], "「丙.pdf」讀不到", "檔案壞了", self.t)
        self.assertEqual(self.status(self.p1)["status"], "open")
        self.assertIn("丙.pdf", self.md(PENDING_MD))
        (he,) = self.handedits()
        self.assertEqual(he["data"]["file"], PENDING_MD)
        self.assertEqual(len([n for n in self.saved_files() if n.endswith("待處理.md")]), 1)
        log = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8")
        self.assertIn("RuntimeError", log)

    def test_date_change_on_pending_is_carried(self):
        self.edit_lines(PENDING_MD, lambda ls: [ln.replace(ln[2:12], "2031-01-01") if "甲.pdf" in ln else ln for ln in ls])
        got = self.report(PENDING_MD)
        self.assertEqual(self.status(self.p1)["status"], "open")
        self.assertEqual(len(got["carried"]), 1)


class RulingsApply(Base):
    def setUp(self):
        super().setUp()
        self.r1 = rulings.add(self.V, "口述為準", ["信義王"], [], "報價以我說的為準", self.t)
        self.r2 = rulings.add(self.V, "口述為準", ["大安陳"], [], "工期以我說的為準", self.t)

    def test_removed_revokes_checked_is_carried(self):
        def change(lines):
            out = []
            for ln in lines:
                if "報價以我說的為準" in ln:
                    continue
                if "工期以我說的為準" in ln:
                    out.append(ln.replace("- ", "- [x] ", 1))
                else:
                    out.append(ln)
            return out
        self.edit_lines(RULINGS_MD, change)
        got = self.report(RULINGS_MD)
        data = {r["id"]: r for r in rulings.load(self.V)["rulings"]}
        self.assertEqual(data[self.r1["id"]]["status"], "revoked")
        self.assertEqual(data[self.r2["id"]]["status"], "active")
        self.assertEqual(len(got["applied"]), 1)
        self.assertEqual(len(got["carried"]), 1)
        self.assertIn(CARRIED, self.md(RULINGS_MD))

    def test_next_ruling_write_applies_too(self):
        self.edit_lines(RULINGS_MD, lambda ls: [ln for ln in ls if "報價以我說的為準" not in ln])
        rulings.add(self.V, "口述為準", ["大安陳"], [], "付款以合約為準", self.t)
        data = {r["id"]: r for r in rulings.load(self.V)["rulings"]}
        self.assertEqual(data[self.r1["id"]]["status"], "revoked")
        self.assertEqual(self.handedits(), [])


class Drop(Base):
    def setUp(self):
        super().setUp()
        agenda.add(self.V, "到期", "2030-03-01", "付尾款", ["信義王"], self.t)
        self.write(AGENDA_MD, self.md(AGENDA_MD) + "\n- 測試\n")
        self.report(AGENDA_MD)
        self.cid = renders.carried(self.V, AGENDA_MD)[0]["id"]

    def test_drop_removes_the_line_and_the_ask(self):
        r = run_kb("renders", "drop", self.cid, "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["id"], self.cid)
        self.assertEqual(renders.carried(self.V, AGENDA_MD), [])
        self.assertNotIn(CARRIED, self.md(AGENDA_MD))
        self.assertNotIn("測試", self.md(AGENDA_MD))
        asks = json.loads(run_kb("asks", "--all", "--json", cwd=self.V).stdout)["asks"]
        self.assertEqual([a for a in asks if a["kind"] == "carried"], [])

    def test_drop_unknown(self):
        r = run_kb("renders", "drop", "c-00000000", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "沒有這一筆「你加的」"))

    def test_drop_keeps_other_hand_edits_on_the_page(self):
        self.edit_lines(AGENDA_MD, lambda ls: [ln.replace("- ", "- [x] ", 1) if "付尾款" in ln else ln for ln in ls])
        r = run_kb("renders", "drop", self.cid, cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        (it,) = [i for i in agenda.load(self.V)["items"] if i["text"] == "付尾款"]
        self.assertEqual(it["status"], "done")

    def test_14_drop_with_unsaved_hand_edit_does_not_overwrite_it(self):
        """她那份存不下（KEEP_FAILED）時 drop 也不重寫那頁，免得蓋掉她的改動（裁定 14）。"""
        d = self.V / ".system" / "handedits"
        if d.is_dir():
            shutil.rmtree(d)
        d.write_text("擋住", encoding="utf-8")
        self.edit_lines(AGENDA_MD, lambda ls: [ln.replace("- ", "- [x] ", 1) if "付尾款" in ln else ln for ln in ls])
        mine = self.md(AGENDA_MD)
        r = run_kb("renders", "drop", self.cid, cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "她那份沒存成，這次先不動；再說一次"))
        self.assertEqual(self.md(AGENDA_MD), mine)
        self.assertEqual([c["id"] for c in renders.carried(self.V, AGENDA_MD)], [self.cid])

    def test_ask_results_for_agenda_page(self):
        asks = json.loads(run_kb("asks", "--all", "--json", cwd=self.V).stdout)["asks"]
        (ask,) = [a for a in asks if a["kind"] == "carried"]
        labels = [r["label"] for r in ask["results"]]
        self.assertEqual(labels, ["加成日程", "不用了"])
        add, drop = ask["results"]
        self.assertTrue(add["do"][0].startswith("kb agenda add --kind {種類} --date {日期} --text"))
        self.assertEqual(add["do"][1], f"kb renders drop {self.cid}")
        self.assertEqual([f["name"] for f in add["fill"]], ["種類", "日期"])
        self.assertEqual(drop["argv"], ["renders", "drop", self.cid])
        self.assertEqual(add["argv"], ["agenda", "add", "--text", "測試"])
        self.assertEqual(add["after"], ["renders", "drop", self.cid])

    def test_ask_results_for_pending_and_rulings_pages(self):
        pending.add(self.V, "unreadable", ["f-11111111"], "「甲.pdf」讀不到", "檔案壞了", self.t)
        self.write(PENDING_MD, self.md(PENDING_MD) + "\n- 隨手寫的\n")
        self.report(PENDING_MD)
        asks = json.loads(run_kb("asks", "--all", "--json", cwd=self.V).stdout)["asks"]
        mine = [a for a in asks if a["kind"] == "carried" and "待處理.md" in a["question"]]
        self.assertEqual([r["label"] for r in mine[0]["results"]], ["不用了", "跟 Claude 說"])
        self.assertIsNone(mine[0]["results"][1]["argv"])

    def test_home_puts_carried_on_the_claude_side(self):
        """裁定 39（D-268）：carried 不在「要你確認的」那張表裡（種類與日期要問、要 Claude 接手），整題算進最下面那行。"""
        from kb._lib import home
        out = home.build(self.V)
        self.assertEqual([a for a in out["confirm"] if a["kind"] == "carried"], [])
        (ask,) = [a for a in out["claude"] if a["kind"] == "carried"]
        self.assertIn("測試", ask["text"])
        self.assertEqual(set(ask), {"key", "kind", "text"})


class Misc(Base):
    def test_bad_page(self):
        r = run_kb("renders", "apply", "系統/日程.txt", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "頁只收 系統/日程.md、系統/待處理.md、系統/裁示.md"))

    def test_backslash_page_name_is_accepted(self):
        r = run_kb("renders", "apply", "系統\\日程.md", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_via_obsidian_journal_label(self):
        agenda.add(self.V, "到期", "2030-03-01", "付尾款", ["信義王"], self.t)
        self.write(AGENDA_MD, self.md(AGENDA_MD) + "\n- 測試\n")
        r = run_kb("--via", "obsidian", "renders", "apply", AGENDA_MD, cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("你在 Obsidian 按的", run_kb("journal", "recent", "--n", "2", cwd=self.V).stdout)

    def turn_dirs(self):
        d = self.V / ".system" / "versions"
        return sorted(x.name for x in d.iterdir()) if d.is_dir() else []

    def test_14_nothing_to_apply_opens_no_obsidian_turn(self):
        agenda.add(self.V, "到期", "2030-03-01", "付尾款", ["信義王"], self.t)
        before = self.turn_dirs()
        r = run_kb("--via", "obsidian", "renders", "apply", AGENDA_MD, cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "這頁沒有要照做的"))
        r = run_kb("--via", "obsidian", "renders", "apply", AGENDA_MD, "--json", cwd=self.V)
        self.assertEqual(json.loads(r.stdout), {"page": AGENDA_MD, "applied": [], "carried": [], "dropped": 0})
        self.assertEqual(self.turn_dirs(), before)

    def test_14_unknown_drop_opens_no_obsidian_turn(self):
        before = self.turn_dirs()
        r = run_kb("--via", "obsidian", "renders", "drop", "c-00000000", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "沒有這一筆「你加的」"))
        self.assertEqual(self.turn_dirs(), before)

    def test_14_real_edit_still_opens_the_obsidian_turn(self):
        agenda.add(self.V, "到期", "2030-03-01", "付尾款", ["信義王"], self.t)
        self.write(AGENDA_MD, self.md(AGENDA_MD) + "\n- 測試\n")
        before = self.turn_dirs()
        r = run_kb("--via", "obsidian", "renders", "apply", AGENDA_MD, cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.turn_dirs()), len(before) + 1)

    def test_index_and_journal_pages_still_only_saved(self):
        self.assertEqual(hand.PAGE_NAMES.keys(), {AGENDA_MD, PENDING_MD, RULINGS_MD})


if __name__ == "__main__":
    unittest.main()
