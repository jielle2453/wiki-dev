"""小修一批（10-26）的驗收：每條一個 test_<編號>_…，編號照 spec「要做的事」。"""
import json
import re
import shutil
import unittest
from pathlib import Path
from unittest import mock

from tests import _entities as E
from tests import _tags as T
from tests.test_lib_lookup import Base as LookupBase
from tests.test_lib_lookup import write_card
from tests.test_scripts_inventory_cli import run_kb
from tests.test_scripts_profile_tags import Base as TagBase
from tests.test_scripts_profile_tags import LI, LI_REL
from tests.test_scripts_versions_cli import Base as VersionsBase
from kb._lib import agenda, entities, findings, journal, plan, statements, turn  # noqa: E402
from kb._lib.paths import plugin_root  # noqa: E402

ROOT = plugin_root()
AGAIN = "再說一次「退回」會把這次的退回取消，不會再往前退。"


# ---------- 1. B-100 ----------

class LookupStaleFinding(LookupBase):
    def stale_finding(self):
        c, _ = findings.add(self.V, "信義王報價合計 182 萬", "兩份相加", ["信義王"], [self.quote], self.t)
        write_card(self.V, E.DRAFT, "信義王會議", ["信義王"], kind="會議紀錄")
        return c

    def test_01_lookup_stale_finding(self):
        c = self.stale_finding()
        got = json.loads(self.kb("信義王", "--json"))["findings"]
        self.assertEqual(got, [{"id": c["id"], "text": None, "how": "兩份相加",
                                "basis": [{"id": self.quote, "title": "信義王報價第二版"}], "date": c["date"],
                                "stale": True, "redo": "依據變了，要用就重算：兩份相加"}])
        out = self.kb("信義王")
        self.assertIn(f"- 依據變了，要用就重算：兩份相加（算於 {c['date']}）", out.splitlines())
        self.assertNotIn("182 萬", out)
        self.assertNotIn(findings.STALE_TEXT, out)

    def test_01_fresh_finding_unchanged(self):
        c, _ = findings.add(self.V, "信義王報價合計 182 萬", "兩份相加", ["信義王"], [self.quote], self.t)
        got = json.loads(self.kb("信義王", "--json"))["findings"]
        self.assertEqual(got[0], {"id": c["id"], "text": "信義王報價合計 182 萬", "how": "兩份相加",
                                  "basis": [{"id": self.quote, "title": "信義王報價第二版"}], "date": c["date"],
                                  "stale": False})
        self.assertIn(f"- 信義王報價合計 182 萬：兩份相加（算於 {c['date']}）", self.kb("信義王").splitlines())

    def test_01_brief_keeps_text(self):
        self.stale_finding()
        ent = entities.load(self.V)
        item = findings.active_for(findings.load(self.V), "信義王", ent)[0]
        got = findings.brief(self.V, item, agenda.card_titles(self.V), findings.context(self.V, ent))
        self.assertEqual((got["text"], got["stale"]), ("信義王報價合計 182 萬", True))
        self.assertNotIn("redo", got)


# ---------- 2. B-407 ----------

class VerifyText(unittest.TestCase):
    def test_02_verify_lookup_before_tally(self):
        text = (ROOT / "skills" / "answer" / "references" / "verify.md").read_text(encoding="utf-8")
        line = ("合計前，對每個要算進去的實體跑一次 `kb lookup \"<名稱>\" --json`：`statements`（口述）或 `rulings`（裁示）"
                "改過某一份的數字，就用改過的數字進 `kb tally`，那一筆短標〔你 X 說的〕；沒有改過的照原檔。")
        self.assertIn(line, text)
        section = text[text.index("加總：`kb tally`"):]
        self.assertLess(section.index(line), section.index("kb tally --row"))


# ---------- 3、15. B-099、B-089、B-475 ----------

R10 = ("- R-10 給客戶看的全是繁體中文；指令、鍵名、參數英文。工具之間不寫自言自語。不貼〔f-…〕〔s-…〕這類內部編號，"
       "出處講卡標題、哪天說的。")


class CoreR10(unittest.TestCase):
    def core(self):
        return (ROOT / "rules" / "core.md").read_text(encoding="utf-8")

    def test_03_r10_no_ids(self):
        self.assertIn(R10, self.core())

    def test_03_ingest_answer_like_answer(self):
        text = (ROOT / "skills" / "ingest" / "SKILL.md").read_text(encoding="utf-8")
        answer = text[text.index("- **回答**"):text.index("- **客戶回了**")]
        self.assertIn("問資料的照 answer 的做法答（粗估、核對、`kb tally`、短標）", answer)
        principles = text[text.index("## 原則"):text.index("## 骨架")]
        self.assertEqual(sum(1 for x in principles.splitlines() if x.startswith("- **")), 10)


# ---------- 4（作廢）、5、14：skill 文字 ----------

class SkillText(unittest.TestCase):
    def read(self, *parts):
        return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")

    def test_04_old_intake_sentence_gone(self):
        self.assertNotIn("先把檔案放進登記的資料夾", self.read("skills", "ingest", "SKILL.md"))

    def test_05_manage_files_follows_d239(self):
        text = self.read("skills", "manage", "references", "files.md")
        self.assertIn("這是實體改名或換型別，照 note 的做法（她講明結果就做，沒講清楚才問）。", text)
        self.assertNotIn("照 note 的做法問她", text)

    def test_14_ingest_body_size(self):
        text = self.read("skills", "ingest", "SKILL.md")
        body = text.split("\n---\n", 1)[1]
        self.assertLessEqual(len(body.strip("\n")), 4400)
        self.assertTrue(body.startswith("\n# 整理成卡\n"))
        for gone in ("**說繁體中文**", "一次一個指令"):
            self.assertNotIn(gone, body)
        self.assertIn("- `references/intake.md`：收件匣怎麼收、拿不到怎麼說、放哪怎麼問。", body)

    def test_14_commands_dispatch_line(self):
        text = self.read("skills", "ingest", "references", "commands.md")
        self.assertLessEqual(len(text.splitlines()), 150)
        self.assertNotIn("每個欄位怎麼處理照 SKILL 骨架的「讀派工結果」。", text)
        self.assertIn("常走的照 SKILL 骨架「讀派工結果」；其他幾種：`approval` 照它的問句問客戶，說好跑它的 `do` 再 dispatch，"
                      "說不要照骨架「客戶說停」做（綜合卡留到下次）；`stopped` 是這一句說了停，不派，帶 `taken_over` 是整理交給了"
                      "另一個對話，照 `say` 講一次，之後收到通知也不再派；`done` 是都做完了，到骨架「回答」，最後的回答用 `tell`；"
                      "`say` 沒句子就不說話，`announce` 講過的也不再講；回報有字典外那行，照 D-231 問她要不要加，不自己加"
                      "（留到「回答」問）。", text)


# ---------- 6. B-441 ----------

class RevertAgain(VersionsBase):
    def test_06_revert_says_again(self):
        self.modify_card_in_turn()
        self.new_turn()
        r = run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.splitlines()[-1], AGAIN)

    def test_06_revert_json_again(self):
        self.modify_card_in_turn()
        self.new_turn()
        r = run_kb("versions", "revert", "--json", cwd=self.V)
        self.assertEqual(json.loads(r.stdout)["again"], AGAIN)

    def test_06_revert_of_revert_says_again(self):
        self.modify_card_in_turn()
        self.new_turn()
        run_kb("versions", "revert", cwd=self.V)
        self.new_turn("再退回一步")
        r = run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lines = r.stdout.splitlines()
        self.assertTrue(any(x.startswith("這一次退的是那次「退回」本身") for x in lines), lines)
        self.assertEqual(lines[-1], AGAIN)

    def test_06_refusal_has_no_again(self):
        r = run_kb("versions", "revert", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "沒有可以退回的改動"))


# ---------- 7. B-094 ----------

class MapPipes(unittest.TestCase):
    def test_07_claude_md_rows_have_three_pipes(self):
        pipe = re.compile(r"(?<!\\)\|")
        for i, line in enumerate((ROOT / "CLAUDE.md").read_text(encoding="utf-8").split("\n"), 1):
            if line.startswith("| "):
                self.assertEqual(len(pipe.findall(line)), 3, f"第 {i} 行")


# ---------- 8. B-464 ----------

class TagFixes(TagBase):
    BROKEN = "階段: 施工"

    def break_xinyi(self):
        """信義王卡的檔頭「階段」寫兩次（cards.parse_front 讀不懂）；回那時的位元組。"""
        p = self.V / T.XINYI_REL
        text = p.read_text(encoding="utf-8")
        self.assertIn(self.BROKEN, text)
        text = text.replace(self.BROKEN, f"{self.BROKEN}\n{self.BROKEN}", 1)
        p.write_text(text, encoding="utf-8", newline="\n")
        return p.read_bytes()

    def canon(self, eid):
        return next(e for e in entities.load(self.V)["entities"] if e["id"] == eid).get("tags")

    def test_08_type_not_in_table(self):
        for args in (("remove", "不存在的型別", "在意"), ("rename", "不存在的型別", "在意", "--to", "別的"),
                     ("merge", "不存在的型別", "在意", "健康", "--into", "醫療")):
            for extra in (("--check",), ()):
                r = self.kb("tag", *args, *extra)
                self.assertEqual((r.returncode, r.stdout.strip()), (3, "型別表沒有「不存在的型別」"), args + extra)

    def test_08_field_not_in_type(self):
        r = self.kb("tag", "remove", "案子", "在意", "--check")
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "第八節沒有「在意」這個標籤欄；有：工種、階段"))

    def check_unreadable(self, args, done):
        before = self.break_xinyi()
        li_before = self.card(LI_REL)
        code, got = self.json_of("tag", *args, "--check")
        self.assertEqual((code, got["unreadable"]), (0, ["信義王"]))
        r = self.kb("tag", *args, "--check")
        self.assertIn("另有 1 張綜合卡的檔頭讀不懂，卡上那行沒跟著改（實體清單改好了）：信義王", r.stdout.splitlines())
        r = self.kb("tag", *args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.splitlines(), [done, "另有 1 張綜合卡的檔頭讀不懂，卡上那行沒跟著改（實體清單改好了）：信義王"])
        self.assertEqual((self.V / T.XINYI_REL).read_bytes(), before)
        self.assertNotEqual(self.card(LI_REL), li_before)
        return self.canon(E.XINYI), self.canon(LI)

    def test_08_merge_unreadable_card(self):
        xinyi, li = self.check_unreadable(("merge", "案子", "工種", "水電", "--into", "木作"),
                                          "已把「水電」併進「木作」：2 個只剩木作；不對可以說退回")
        self.assertEqual((xinyi["工種"], li["工種"]), (["木作"], ["木作"]))
        self.assertEqual(self.line(LI_REL, "工種"), "工種: [木作]")

    def test_08_remove_unreadable_card(self):
        xinyi, li = self.check_unreadable(("remove", "案子", "工種", "水電"),
                                          "已從「工種」拿掉「水電」：2 個一起拿掉；不對可以說退回")
        self.assertEqual((xinyi["工種"], li["工種"]), (["木作"], []))

    def test_08_rename_unreadable_card(self):
        xinyi, li = self.check_unreadable(("rename", "案子", "工種", "水電", "--to", "電工"),
                                          "已把「工種」的「水電」改叫「電工」：2 個跟著改；不對可以說退回")
        self.assertEqual((xinyi["工種"], li["工種"]), (["電工", "木作"], ["電工"]))

    def test_08_no_broken_card_no_line(self):
        code, got = self.json_of("tag", "merge", "案子", "工種", "水電", "--into", "木作", "--check")
        self.assertEqual((code, got["unreadable"]), (0, []))
        r = self.kb("tag", "merge", "案子", "工種", "水電", "--into", "木作")
        self.assertNotIn("讀不懂", r.stdout)


# ---------- 9. B-467 ----------

class CloseAsk(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.V = Path(tempfile.mkdtemp())
        (self.V / ".system").mkdir()
        E.put_entities(self.V, [E.entity("e-0f3e9a21", "王宅")])
        item = {"id": "p-9a8b7c6d", "kind": "close", "file_ids": ["f-11111111", "f-22222222"],
                "entity_ids": ["e-0f3e9a21"], "text": "「王宅」看起來已經結束了，要記成結案嗎？", "reason": "依據",
                "created": "2026-10-20T10:00:00", "created_turn": "t", "status": "open", "resolved": None, "how": None}
        (self.V / ".system" / "pending.json").write_text(
            json.dumps({"schema_version": 1, "items": [item]}, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.V, ignore_errors=True)

    def question(self, titles):
        asks = plan._close_asks(self.V, titles)
        self.assertEqual(len(asks), 1)
        return asks[0]["question"]

    def test_09_all_titles(self):
        q = self.question({"f-11111111": "報價第二版", "f-22222222": "合約"})
        self.assertEqual(q, "「王宅」看起來已經結束了，要記成結案嗎？（依據：報價第二版、合約）")

    def test_09_one_missing(self):
        q = self.question({"f-11111111": "報價第二版"})
        self.assertEqual(q, "「王宅」看起來已經結束了，要記成結案嗎？（依據：報價第二版，另外 1 份檔案）")
        self.assertNotIn("f-", q)

    def test_09_all_missing(self):
        q = self.question({})
        self.assertEqual(q, "「王宅」看起來已經結束了，要記成結案嗎？（依據：2 份檔案）")
        self.assertNotIn("f-", q)


# ---------- 10、11. B-468、B-470 ----------

class AgendaBase(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        self.t = turn.start(self.V, None, "")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def agenda_bytes(self):
        return (self.V / ".system" / "agenda.json").read_bytes()


class AgendaEdit(AgendaBase):
    def period(self):
        it, _ = agenda.add(self.V, "期間", "2030-02-01", "施工", ["信義王"], self.t, start="2030-01-01")
        return it

    def test_10_period_two_entities_refused(self):
        it = self.period()
        before = self.agenda_bytes()
        r = run_kb("agenda", "edit", it["id"], "--entity", "信義王", "--entity", "大安陳", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "期間只掛一個實體"))
        self.assertEqual(self.agenda_bytes(), before)

    def test_10_period_other_entity_ok(self):
        it = self.period()
        r = run_kb("agenda", "edit", it["id"], "--entity", "大安陳", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(agenda.get(self.V, it["id"])["entities"], ["大安陳"])

    def test_10_not_period_two_entities_ok(self):
        it, _ = agenda.add(self.V, "到期", "2030-02-01", "交圖", ["信義王"], self.t)
        r = run_kb("agenda", "edit", it["id"], "--entity", "信義王", "--entity", "大安陳", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(agenda.get(self.V, it["id"])["entities"], ["信義王", "大安陳"])


class AgendaRender(AgendaBase):
    def test_11_render_failure_is_logged(self):
        with mock.patch.object(agenda, "render", side_effect=RuntimeError("壞了")):
            it, created = agenda.add(self.V, "到期", "2030-02-01", "交圖", ["信義王"], self.t)
        self.assertTrue(created)
        self.assertEqual([i["id"] for i in agenda.load(self.V)["items"]], [it["id"]])
        log = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(sum(1 for x in log if "\tagenda_render\t" in x), 1)


# ---------- 12. B-473 ----------

MARKED = "## 結論 **182 萬** ```python x=1``` 見 #10"


class JournalPlain(AgendaBase):
    def test_12_plain(self):
        self.assertEqual(journal.plain(MARKED), "結論 182 萬 x=1 見 #10")
        self.assertEqual(journal.plain("#標籤 a-b > c `x` ```中文```"), "#標籤 a-b > c `x` 中文")
        self.assertEqual(journal.plain("####### 七個"), "####### 七個")

    def test_12_render_and_recent(self):
        t = turn.start(self.V, "sid-12", "今年報價總共多少")
        journal.complete_turn(self.V, t, MARKED, "回答了", "ai", [], False)
        month = journal.month_of(t["turn"])
        raw = (self.V / ".system" / "journal" / f"{month}.jsonl").read_text(encoding="utf-8")
        self.assertIn(json.dumps(MARKED, ensure_ascii=False)[1:-1], raw)
        md = (self.V / "系統" / "工作日誌" / f"{month}.md").read_text(encoding="utf-8")
        self.assertIn("- 結果：結論 182 萬 x=1 見 #10", md)
        r = run_kb("journal", "recent", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for out in (md.split("\n", 2)[2], r.stdout):
            for mark in ("## 結論", "**", "```"):
                self.assertNotIn(mark, out)
        self.assertIn("結論 182 萬 x=1 見 #10", r.stdout)


# ---------- 13. B-476 ----------

SECRET = "hunter2"


class StatementSecret(AgendaBase):
    def put(self, *items):
        (self.V / ".system" / "statements.json").write_text(
            json.dumps({"schema_version": 1, "statements": list(items)}, ensure_ascii=False), encoding="utf-8")

    def item(self, sid, text, status="active", replaced_by=None):
        return {"id": sid, "text": text, "entities": ["信義王"], "date": "2026-10-01", "turn": "t", "status": status,
                "replaced_by": replaced_by}

    def assert_no_secret(self):
        for p in list((self.V / ".system" / "journal").glob("*.jsonl")) + list((self.V / "系統" / "工作日誌").glob("*.md")):
            self.assertNotIn(SECRET, p.read_text(encoding="utf-8"), p.name)
        self.assertTrue(list((self.V / ".system" / "journal").glob("*.jsonl")))

    def test_13_withdraw(self):
        self.put(self.item("s-11111111", f"門禁密碼：{SECRET}"))
        r = run_kb("statement", "withdraw", "s-11111111", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_no_secret()

    def test_13_restore(self):
        self.put(self.item("s-11111111", f"門禁密碼：{SECRET}", "superseded", "s-22222222"),
                 self.item("s-22222222", "門禁改刷卡", "withdrawn"))
        r = run_kb("statement", "restore", "s-11111111", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_no_secret()

    def test_13_add_replaces(self):
        self.put(self.item("s-11111111", f"門禁密碼：{SECRET}"))
        r = run_kb("statement", "add", "--entity", "信義王", "--text", "門禁改刷卡", "--replaces", "s-11111111", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assert_no_secret()

    def test_13_add_mentions_password_file(self):
        r = run_kb("statement", "add", "--entity", "信義王", "--text", "密碼檔不能讀，已提醒客戶", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(statements.load(self.V)["statements"][0]["text"], "密碼檔不能讀，已提醒客戶")


if __name__ == "__main__":
    unittest.main()
