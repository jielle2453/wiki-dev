"""_lib/renders（lint 第 4 點，D-223）：程式產生的 md 記指紋（.system/renders.json），重新產生前認出手改、把她那份存到
.system/handedits/；diff 把她改的分成打勾、刪掉、改日期、其他。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests._guard_fixture import SCRIPTS  # noqa: F401  sys.path
from kb._lib import renders  # noqa: E402

REL = "系統/待處理.md"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kbrenders-"))
        self.V = self.tmp / "vault"
        (self.V / ".system").mkdir(parents=True)
        (self.V / "系統").mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, text, rel=REL):
        (self.V / rel).write_text(text, encoding="utf-8", newline="\n")


class CheckRecord(Base):
    def test_no_file_or_no_record_is_not_hand_edited(self):
        self.assertIsNone(renders.check(self.V, REL))
        self.put("她寫的\n")
        self.assertIsNone(renders.check(self.V, REL), "沒有紀錄的當作沒被手改（第一次跑這版）")

    def test_record_then_same_text_is_clean(self):
        self.put("程式寫的\n")
        renders.record(self.V, REL, "程式寫的\n")
        self.assertIsNone(renders.check(self.V, REL))
        data = json.loads((self.V / ".system" / "renders.json").read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(len(data["files"][REL]), 64)

    def test_changed_text_returns_hers(self):
        self.put("程式寫的\n")
        renders.record(self.V, REL, "程式寫的\n")
        self.put("她改過\n")
        self.assertEqual(renders.check(self.V, REL), "她改過\n")

    def test_older_program_version_is_not_hand_edited(self):
        """退回把 md 換回程式以前寫的那份：對得上舊指紋，不算手改。"""
        renders.record(self.V, REL, "第一版\n")
        renders.record(self.V, REL, "第二版\n")
        self.put("第一版\n")
        self.assertIsNone(renders.check(self.V, REL))

    def test_bad_renders_json_counts_as_no_record(self):
        self.put("x\n")
        (self.V / ".system" / "renders.json").write_text("{壞", encoding="utf-8")
        self.assertIsNone(renders.check(self.V, REL))
        renders.record(self.V, REL, "x\n")
        self.assertIsNone(renders.check(self.V, REL))

    def test_record_keeps_date(self):
        renders.record(self.V, REL, "x\n", day="2026-10-20")
        self.assertEqual(renders.recorded_day(self.V, REL), "2026-10-20")


class Keep(Base):
    def test_saves_copy_under_handedits_and_logs(self):
        saved = renders.keep(self.V, REL, "她改過\n")
        self.assertTrue(saved.startswith(".system/handedits/"))
        self.assertTrue(saved.endswith("-待處理.md"))
        self.assertEqual((self.V / saved).read_text(encoding="utf-8"), "她改過\n")
        again = renders.keep(self.V, REL, "又改\n")
        self.assertNotEqual(saved, again, "同一秒兩次不能互蓋")
        log = renders.saved(self.V)
        self.assertEqual([s["file"] for s in log], [REL, REL])
        self.assertEqual(log[0]["saved"], saved)


class Diff(Base):
    BASE = "# 待處理\n\n## 讀不到（2）\n- 2026-10-01 甲讀不到。換一份\n- 2026-10-02 乙讀不到。換一份\n- 2026-10-03 丙讀不到。換一份\n"
    LINES = [("- 2026-10-01 甲讀不到。換一份", "p-1"), ("- 2026-10-02 乙讀不到。換一份", "p-2"),
             ("- 2026-10-03 丙讀不到。換一份", "p-3")]

    def test_checked_removed_date_other(self):
        hers = ("# 待處理\n\n## 讀不到（2）\n- [x] 2026-10-01 甲讀不到。換一份\n- 2026-10-09 丙讀不到。換一份\n"
                "我自己加的一行\n")
        got = renders.diff(self.BASE, hers, self.LINES)
        self.assertEqual([c["id"] for c in got["checked"]], ["p-1"])
        self.assertEqual([c["id"] for c in got["removed"]], ["p-2"])
        self.assertEqual([(c["id"], c["to"]) for c in got["changed_date"]], [("p-3", "2026-10-09")])
        self.assertEqual(got["other"], ["我自己加的一行"])

    def test_same_text_is_empty(self):
        got = renders.diff(self.BASE, self.BASE, self.LINES)
        self.assertEqual(got, {"checked": [], "removed": [], "changed_date": [], "other": []})

    def test_ignored_section_and_code_fence(self):
        base = "# x\n## 整理時要問你的\n- 問一\n```mermaid\ngantt\n```\n"
        hers = "# x\n## 整理時要問你的\n- 問二\n```mermaid\ngantt 改\n```\n"
        got = renders.diff(base, hers, [], ignore_sections=("整理時要問你的",))
        self.assertEqual(got["other"], [])

    def test_empty_checkbox_is_not_checked(self):
        hers = self.BASE.replace("- 2026-10-01", "- [ ] 2026-10-01")
        self.assertEqual(renders.diff(self.BASE, hers, self.LINES)["checked"], [])

    def test_unlink(self):
        """記帳 3（D-280）：連結還原成名字；沒有 | 的取路徑最後一段。"""
        self.assertEqual(renders.unlink("- 收 50,000 [[01 案子/信義王/信義王|信義王]] 第二期"), "- 收 50,000 信義王 第二期")
        self.assertEqual(renders.unlink("[[系統/帳/2026|2026]]、[[02 顧客/李小姐/李小姐]]"), "2026、李小姐")
        self.assertEqual(renders.unlink("沒有連結"), "沒有連結")

    def test_unlink_old_and_relative_links_are_the_same(self):
        """#66 甲（D-541）：同一行舊寫法與相對寫法還原後相同，只是連結寫法不同不算她手改。"""
        old = "- 2026-11-05（週四）會議 見面（[[02 顧客/李小姐/李小姐|李小姐]]）、[[02 顧客/李小姐/李小姐]]、| [[系統/帳/2026\\|2026]] |"
        new = old.replace("[[02 顧客/", "[[../02 顧客/").replace("[[系統/帳/", "[[./帳/")
        self.assertNotEqual(old, new)
        self.assertEqual(renders.unlink(new), renders.unlink(old))
        self.assertEqual(renders.unlink("[[../../檔案索引/a/報價單|報價單]]、[[./首頁]]、[[../a/b#段]]"), "報價單、首頁、b")
        base = "# 日程\n## 今天\n" + old.split("、")[0] + "\n"
        lines = [(base.splitlines()[-1].replace("[[02 顧客/", "[[../02 顧客/"), "a-1")]
        self.assertTrue(renders.is_empty(renders.diff(base.replace("[[02 顧客/", "[[../02 顧客/"), base, lines)))
        got = renders.diff(base.replace("[[02 顧客/", "[[../02 顧客/"), base.replace("2026-11-05（週四）", "2026-11-08"), lines)
        self.assertEqual([(c["id"], c["to"]) for c in got["changed_date"]], [("a-1", "2026-11-08")])

    def test_link_untouched_is_not_a_change(self):
        """她沒動連結的行不算改；Obsidian 搬卡改了連結路徑也不算；改日期照舊認得。"""
        base = "# 日程\n## 今天\n- 2026-11-05（週四）會議 見面（[[02 顧客/李小姐/李小姐|李小姐]]）\n"
        lines = [("- 2026-11-05（週四）會議 見面（[[02 顧客/李小姐/李小姐|李小姐]]）", "a-1")]
        moved = base.replace("02 顧客/李小姐", "03 顧客/李小姐")
        self.assertTrue(renders.is_empty(renders.diff(base, moved, lines)))
        plain = base.replace("[[02 顧客/李小姐/李小姐|李小姐]]", "李小姐")
        self.assertTrue(renders.is_empty(renders.diff(base, plain, lines)))
        got = renders.diff(base, base.replace("2026-11-05（週四）", "2026-11-08"), lines)
        self.assertEqual([(c["id"], c["to"]) for c in got["changed_date"]], [("a-1", "2026-11-08")])

    def test_skip_lines(self):
        """skip 認得的行（帳頁的表與合計）改了不算。"""
        base = "# 帳\n## 11 月\n合計：收 5,000\n| 商品 | 數 |\n|---|---|\n| 精華液 | 2 |\n"
        hers = base.replace("| 精華液 | 2 |", "| 精華液 | 9 |").replace("收 5,000", "收 9,000")
        skip = lambda line: line.startswith(("|", "合計"))  # noqa: E731
        self.assertTrue(renders.is_empty(renders.diff(base, hers, [], skip=skip)))
        self.assertEqual(len(renders.diff(base, hers, [])["other"]), 2)

    def test_handedit_flag(self):
        self.assertTrue(renders.is_empty({"checked": [], "removed": [], "changed_date": [], "other": []}))
        self.assertFalse(renders.is_empty({"checked": [{"id": "p-1"}], "removed": [], "changed_date": [], "other": []}))


class Renderers(unittest.TestCase):
    """五個重新產生的地方（D-223、D-263）：待處理、日程、裁示有 JSON 真相 → 存她那份、認得出的照做（不再開 handedit，#22）；總目錄、工作日誌 → 只存。"""

    def setUp(self):
        from tests import _entities as E
        from kb._lib import turn
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        self.t = turn.start(self.V, None, "")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def handedits(self):
        from kb._lib import pending
        return [i for i in pending.load(self.V)["items"] if i.get("kind") == "handedit"]

    def saved_files(self):
        d = self.V / ".system" / "handedits"
        return sorted(p.name for p in d.iterdir()) if d.is_dir() else []

    def test_pending_checked_and_removed(self):
        from kb._lib import pending
        a = pending.add(self.V, "unreadable", ["f-11111111"], "「甲.pdf」讀不到", "檔案壞了", self.t)
        b = pending.add(self.V, "unreadable", ["f-22222222"], "「乙.pdf」讀不到", "檔案壞了", self.t)
        md = self.V / "系統" / "待處理.md"
        text = md.read_text(encoding="utf-8")
        lines = text.splitlines()
        lines = [ln.replace("- ", "- [x] ", 1) if "甲.pdf" in ln else ln for ln in lines if "乙.pdf" not in ln]
        md.write_text("\n".join(lines) + "\n", encoding="utf-8")
        pending.add(self.V, "unreadable", ["f-33333333"], "「丙.pdf」讀不到", "檔案壞了", self.t)
        # #22（D-263 修訂 D-223）：認得出的直接照做，不再開 handedit；她那份照舊存
        items = {i["id"]: i for i in pending.load(self.V)["items"]}
        self.assertEqual((items[a]["status"], items[a]["how"]), ("done", "在待處理.md 打勾"))
        self.assertEqual(items[b]["status"], "dismissed")
        self.assertEqual(self.handedits(), [])
        self.assertEqual(len(self.saved_files()), 1)
        self.assertIn("丙.pdf", md.read_text(encoding="utf-8"), "新的照寫")
        self.assertNotIn("[x]", md.read_text(encoding="utf-8"))

    def test_unchanged_md_opens_nothing(self):
        from kb._lib import pending
        pending.add(self.V, "unreadable", ["f-11111111"], "「甲.pdf」讀不到", "檔案壞了", self.t)
        pending.add(self.V, "unreadable", ["f-22222222"], "「乙.pdf」讀不到", "檔案壞了", self.t)
        self.assertEqual(self.handedits(), [])
        self.assertEqual(self.saved_files(), [])

    def test_agenda_date_change(self):
        from kb._lib import agenda
        it, _new = agenda.add(self.V, "承諾", "2030-01-10", "給報價", ["信義王"], self.t)
        md = self.V / "系統" / "日程.md"
        text = md.read_text(encoding="utf-8")
        self.assertIn("- 2030-01-10（週四）承諾 給報價", text)
        md.write_text(text.replace("- 2030-01-10（週四）", "- 2030-01-12（週六）"), encoding="utf-8")
        agenda.add(self.V, "會議", "2030-02-01", "丈量", ["信義王"], self.t)
        # #22（D-263 修訂 D-223）：改日期直接照做（歷程 by hand），不再開 handedit；她那份照舊存
        now = agenda.get(self.V, it["id"])
        self.assertEqual(now["date"], "2030-01-12")
        self.assertEqual(now["history"][-1]["by"], "hand")
        self.assertEqual(self.handedits(), [])
        self.assertTrue(any(n.endswith("日程.md") for n in self.saved_files()))

    def test_rulings_removed(self):
        from kb._lib import rulings
        r = rulings.add(self.V, "口述為準", ["信義王"], [], "報價以我說的為準", self.t)
        md = self.V / "系統" / "裁示.md"
        md.write_text("\n".join(ln for ln in md.read_text(encoding="utf-8").splitlines() if "報價以我說的為準" not in ln)
                      + "\n", encoding="utf-8")
        rulings.add(self.V, "口述為準", ["大安陳"], [], "工期以我說的為準", self.t)
        # #22（D-263 修訂 D-223）：刪掉一行 = 收回，不再開 handedit；她那份照舊存
        data = {x["id"]: x for x in rulings.load(self.V)["rulings"]}
        self.assertEqual(data[r["id"]]["status"], "revoked")
        self.assertEqual(self.handedits(), [])
        self.assertTrue(any(n.endswith("裁示.md") for n in self.saved_files()))

    def test_index_only_saved(self):
        from kb._lib import cards
        cards.render_index(self.V, self.t)
        p = self.V / "總目錄.md"
        p.write_text(p.read_text(encoding="utf-8") + "我加的\n", encoding="utf-8")
        cards.render_index(self.V, self.t)
        self.assertEqual(self.handedits(), [])
        self.assertTrue(any(n.endswith("-總目錄.md") for n in self.saved_files()))
        self.assertNotIn("我加的", p.read_text(encoding="utf-8"))

    def test_journal_only_saved(self):
        from kb._lib import journal
        journal.record_program(self.V, "第一段", [], "x")
        month = journal.months(self.V)[-1]
        p = journal.md_path(self.V, month)
        p.write_text(p.read_text(encoding="utf-8") + "我加的\n", encoding="utf-8")
        journal.record_program(self.V, "第二段", [], "x")
        self.assertEqual(self.handedits(), [])
        self.assertTrue(any(n.endswith(f"-{month}.md") for n in self.saved_files()))


if __name__ == "__main__":
    unittest.main()
