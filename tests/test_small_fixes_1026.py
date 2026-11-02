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
        self.assertIn("問資料的照 answer 的做法答（先答、核對、`kb tally`、短標）", answer)
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
        self.assertNotIn("請她在檔案總管", text)
        self.assertNotIn("照 note 的做法問她", text)

    def test_14_ingest_body_size(self):
        text = self.read("skills", "ingest", "SKILL.md")
        body = text.split("\n---\n", 1)[1]
        self.assertLessEqual(len(body.strip("\n")), 4400)
        self.assertTrue(body.startswith("\n# 整理成卡\n"))
        for gone in ("**說繁體中文**", "一次一個指令"):
            self.assertNotIn(gone, body)
        self.assertIn("- `references/intake.md`：怎麼收、放哪、拿不到怎麼辦。", body)

    def test_14_commands_dispatch_line(self):
        text = self.read("skills", "ingest", "references", "commands.md")
        self.assertLessEqual(len(text.splitlines()), 150)
        self.assertNotIn("每個欄位怎麼處理照 SKILL 骨架的「讀派工結果」。", text)
        self.assertIn("常走的照 SKILL 骨架「讀派工結果」；其他幾種：`approval` 有帶就直接跑它的 `do` 再 dispatch，"
                      "不停下來問（一次改很多張綜合卡也照做，寫前程式會先留一份）；`stopped` 是這一句說了停，不派，帶 `taken_over` 是整理交給了"
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


# ========== 乙段 ==========

# ---------- 15. B-475 ----------

class CoreHonorific(unittest.TestCase):
    def test_15_r10_no_honorific(self):
        lines = [x for x in (ROOT / "rules" / "core.md").read_text(encoding="utf-8").splitlines() if x.startswith("- R-10 ")]
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith(R10 + "稱呼客戶用「你」，不用「您」。"), lines)  # 放寬乙：句尾補不講內部名詞


# ---------- 16、17. B-400、B-402 ----------

class VersionsOutputs(VersionsBase):
    def put_output(self, t, rel, text="成品\n"):
        from kb._lib import inventory
        turn.backup(self.V, rel, t["turn"])
        (self.V / rel).write_text(text, encoding="utf-8")
        return inventory.register_output(self.V, rel, t["turn"])

    def entry(self, eid):
        from kb._lib import inventory
        return next(e for e in inventory.load(self.V)["entries"] if e["id"] == eid)

    def test_16_unbacked_not_counted(self):
        t = turn.start(self.V, "sid-16", "寫兩份")
        self.put_output(t, "暫存區/a.md")
        scanned = self.put_output(t, "暫存區/b.md")
        p = self.V / ".system" / "inventory.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        for e in data["entries"]:
            if e["id"] == scanned["id"]:
                e["unbacked"] = True
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        r = run_kb("versions", "list", "--json", cwd=self.V)
        row = next(x for x in json.loads(r.stdout) if x["turn"] == t["turn"])
        self.assertEqual(row["counts"]["outputs"], 1)

    def test_17_link_download_deleted_keeps_entry(self):
        from kb._lib import inventory
        url = "https://claude.ai/artifact/abc"
        ta = turn.start(self.V, "sid-17", "存成線上文件")
        link = inventory.register_link(self.V, url, ta["turn"], "提案")
        tb = turn.start(self.V, "sid-17", "下載回來")
        rel = "暫存區/提案.pdf"
        turn.backup(self.V, rel, tb["turn"])
        (self.V / rel).write_bytes(b"%PDF")
        inventory.attach_location(self.V, link["id"], rel, tb["turn"])
        plain = self.put_output(tb, "暫存區/附件.md")
        self.new_turn()
        r = run_kb("versions", "revert", "--delete-outputs", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.V / rel).exists())
        got = self.entry(link["id"])
        self.assertEqual((got["status"], [x["uri"] for x in got["locations"]]), ("active", [url]))
        self.assertEqual(self.entry(plain["id"])["status"], "deleted")

    def same_turn_link(self):
        """被退的那一回合自己建 link 又掛下載檔（測試報告 #1）：那筆是那一回合的成品。"""
        from kb._lib import inventory
        t = turn.start(self.V, "sid-17b", "存成線上文件再下載")
        link = inventory.register_link(self.V, "https://claude.ai/artifact/xyz", t["turn"], "提案")
        rel = "暫存區/提案.pdf"
        turn.backup(self.V, rel, t["turn"])
        (self.V / rel).write_bytes(b"%PDF")
        inventory.attach_location(self.V, link["id"], rel, t["turn"])
        self.new_turn()
        return link, rel

    def test_17_same_turn_link_is_deleted_like_an_output(self):
        link, rel = self.same_turn_link()
        r = run_kb("versions", "revert", "--delete-outputs", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.V / rel).exists())
        self.assertEqual(self.entry(link["id"])["status"], "deleted")
        self.assertIn("成品 1 份刪了", r.stdout)

    def test_17_same_turn_link_without_flag_is_turn_reverted(self):
        link, rel = self.same_turn_link()
        r = run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.V / rel).exists())
        self.assertEqual(self.entry(link["id"])["status"], "turn_reverted")


# ---------- 18、21. B-091、B-469 ----------

class EntityFollow(LookupBase):
    def finding_on(self, name, cards_):
        c, _ = findings.add(self.V, f"{name}報價合計 182 萬", "兩份相加", [name], cards_, self.t)
        return c["id"]

    def names_of(self, cid):
        return findings.find(findings.load(self.V), cid)["entities"]

    def test_18_rename_follows(self):
        cid = self.finding_on("信義王", [self.quote])
        r = run_kb("entity", "rename", "信義王", "--to", "信義王公館", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.names_of(cid), ["信義王公館"])
        self.assertEqual([c["id"] for c in json.loads(run_kb("lookup", "信義王公館", "--json", cwd=self.V).stdout)["findings"]],
                         [cid])

    def test_18_merge_follows(self):
        cid = self.finding_on("王宅", [self.quote])
        r = run_kb("entity", "merge", "王宅", "--into", "信義王", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.names_of(cid), ["信義王"])

    def test_18_rename_failure_rolls_back(self):
        self.finding_on("信義王", [self.quote])
        p = self.V / ".system" / "findings.json"
        before = p.read_bytes()
        with mock.patch.object(entities, "_save", side_effect=RuntimeError("壞了")):
            with self.assertRaises(RuntimeError):
                entities.rename(self.V, "信義王", "信義王公館", None, self.t)
        self.assertEqual(p.read_bytes(), before)

    def period(self):
        it, _ = agenda.add(self.V, "期間", "2030-02-01", "施工", ["信義王"], self.t, start="2030-01-01")
        return it

    def test_21_remove_ends_open_period(self):
        it = self.period()
        r = run_kb("entity", "remove", "信義王", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        got = agenda.get(self.V, it["id"])
        self.assertEqual((got["status"], got["ended"]), ("done", agenda._today()))
        md = (self.V / agenda.MD_POSIX).read_text(encoding="utf-8")
        self.assertNotIn("沒結束", md)

    def test_21_remove_failure_rolls_back(self):
        self.period()
        p = self.V / ".system" / "agenda.json"
        before = p.read_bytes()
        with mock.patch.object(entities, "_save", side_effect=RuntimeError("壞了")):
            with self.assertRaises(RuntimeError):
                entities.remove(self.V, "信義王", self.t)
        self.assertEqual(p.read_bytes(), before)


# ---------- 19. B-463 ----------

class FixFollowsCache(TagBase):
    def test_19_rename_keeps_lint_fix(self):
        from kb.lint import state
        self.assertTrue(state.add_fix(self.V, T.XINYI_REL, "補標籤（在意）", [], self.t))
        r = run_kb("entity", "rename", "信義王", "--to", "信義王公館", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        new_rel = "案子/信義王公館/信義王公館.md"
        self.assertTrue((self.V / new_rel).is_file())
        got = {f["path"]: f for f in state.fixes(self.V)}
        self.assertIn(new_rel, got)
        self.assertEqual(got[new_rel]["sha"], state.card_sha(self.V, new_rel))
        self.assertIn("補標籤（在意）", got[new_rel]["reason"])
        todo = json.loads(run_kb("cards", "todo", "--json", cwd=self.V).stdout)
        self.assertTrue(any("補標籤（在意）" in str(x.get("reason")) for x in todo["synthesis_stale"]), todo["synthesis_stale"])

    def test_19_carried_fix_not_revived_after_card_is_fixed(self):
        """code-review：改名帶過來的記號只帶一次；卡改好之後再重渲染快取，舊路徑那筆不會把它叫回來。"""
        from kb._lib import synthesis
        from kb.lint import state
        state.add_fix(self.V, T.XINYI_REL, "補標籤（在意）", [], self.t)
        self.assertEqual(run_kb("entity", "rename", "信義王", "--to", "信義王公館", cwd=self.V).returncode, 0)
        self.assertNotIn(T.XINYI_REL, [f["path"] for f in state.load(self.V)["synthesis_fix"]])
        new_rel = "案子/信義王公館/信義王公館.md"
        p = self.V / new_rel
        p.write_text(p.read_text(encoding="utf-8") + "\n- 補好了\n", encoding="utf-8", newline="\n")  # AI 改寫了卡
        synthesis.render_cache(self.V, ["信義王公館"], self.t)
        self.assertNotIn(new_rel, [f["path"] for f in state.fixes(self.V)])

    def test_19_cache_rewrite_keeps_lint_fix(self):
        from kb._lib import synthesis
        from kb.lint import state
        state.add_fix(self.V, T.XINYI_REL, "補標籤（在意）", [], self.t)
        p = self.V / T.XINYI_REL
        p.write_text(re.sub(r"(?m)^相關實體:.*$", "相關實體: [不是這個]", p.read_text(encoding="utf-8"), count=1),
                     encoding="utf-8", newline="\n")  # 快取欄跟現在對不上：render_cache 會重寫這張
        state.add_fix(self.V, T.XINYI_REL, "補標籤（在意）", [], self.t)  # 照現在的卡記
        self.assertEqual(synthesis.render_cache(self.V, ["信義王"], self.t), [T.XINYI_REL])
        got = {f["path"]: f for f in state.fixes(self.V)}
        self.assertEqual(got[T.XINYI_REL]["sha"], state.card_sha(self.V, T.XINYI_REL))


# ---------- 20. B-466 ----------

class AgendaNewVersion(LookupBase):
    def test_20_new_version_not_rechecked_again(self):
        it, _ = agenda.add(self.V, "到期", "2030-01-05", "交平面圖", ["信義王"], self.t, card=self.quote)
        agenda.edit(self.V, it["id"], self.t)  # 她說這條對：記成確認
        card = next(self.V.rglob("信義王報價第二版*.md"))
        text = card.read_text(encoding="utf-8")
        card.write_text(re.sub(r"(?m)^(內容指紋|指紋): *\S+", r"\1: " + "a" * 64, text, count=1), encoding="utf-8",
                        newline="\n")
        todo = json.loads(run_kb("cards", "todo", "--json", cwd=self.V).stdout)
        self.assertIn(it["id"], [x["id"] for x in todo["agenda_recheck"]])
        agenda.recheck(self.V, it["id"], self.t, propose_date="2030-01-20")
        todo = json.loads(run_kb("cards", "todo", "--json", cwd=self.V).stdout)
        ask = next(a for a in todo["asks"] if a["kind"] == "agenda_conflict")
        do = ask["results"][0]["do"]
        self.assertEqual(len(do), 1)
        import shlex
        r = run_kb(*shlex.split(do[0])[1:], cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        todo = json.loads(run_kb("cards", "todo", "--json", cwd=self.V).stdout)
        self.assertNotIn(it["id"], [x["id"] for x in todo["agenda_recheck"]])
        self.assertEqual(agenda.get(self.V, it["id"])["date"], "2030-01-20")


# ---------- 22. B-454 ----------

class StatementArchive(AgendaBase):
    def put(self, items, archived=()):
        (self.V / ".system" / "statements.json").write_text(
            json.dumps({"schema_version": 1, "statements": list(items)}, ensure_ascii=False), encoding="utf-8")
        if archived:
            (self.V / statements.ARCHIVE_POSIX).write_text(
                json.dumps({"schema_version": 1, "statements": list(archived)}, ensure_ascii=False), encoding="utf-8")

    def item(self, sid, text, status="active", replaced_by=None, **kw):
        return dict({"id": sid, "text": text, "entities": ["信義王"], "date": "2026-10-01", "turn": "t", "status": status,
                     "replaced_by": replaced_by}, **kw)

    def test_22_restore_writes_list_first(self):
        self.put([self.item("s-22222222", "改刷卡", "withdrawn")],
                 [self.item("s-11111111", "原本的門禁", "superseded", "s-22222222", archived="2026-10-02")])
        with mock.patch.object(statements, "_drop_archived", side_effect=RuntimeError("壞了")):
            statements.restore(self.V, "s-11111111", self.t)  # 清單已經改好：封存那步出錯只記 log
        self.assertEqual(statements.find(statements.load(self.V), "s-11111111")["status"], "active")
        self.assertIsNotNone(statements.find(statements.load_archive(self.V), "s-11111111"))
        log = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8")
        self.assertEqual(sum(1 for x in log.splitlines() if "\tstatements\t" in x), 1)

    def test_22_restore_moves_out_of_archive(self):
        self.put([self.item("s-22222222", "改刷卡", "withdrawn")],
                 [self.item("s-11111111", "原本的門禁", "superseded", "s-22222222", archived="2026-10-02")])
        got = statements.restore(self.V, "s-11111111", self.t)
        self.assertNotIn("archived", got)
        self.assertIsNone(statements.find(statements.load_archive(self.V), "s-11111111"))

    def test_22_withdraw_with_broken_archive(self):
        self.put([self.item("s-11111111", "門禁改刷卡")])
        (self.V / statements.ARCHIVE_POSIX).write_text("{", encoding="utf-8")
        r = run_kb("statement", "withdraw", "s-11111111", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "已收回：門禁改刷卡"))
        log = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8")
        self.assertEqual(sum(1 for x in log.splitlines() if "\tstatement\t" in x), 1)

    def test_22_revert_lint_turn_restores_report(self):
        """背景健檢本月第一次跑寫上個月的報告：先跑一次建好健檢紀錄，把 last_report 往前撥，再跑一次就會寫。"""
        from kb.lint import runner
        from kb.lint import state as lint_state
        runner.run(self.V, background=True)
        prev = runner._prev_month(agenda._today()[:7])
        st = lint_state.load(self.V)
        st["last_report"] = runner._prev_month(prev)
        lint_state.save(self.V, st, None)
        p = self.V / "系統" / "健檢報告" / f"{prev}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("健檢之前的樣子\n", encoding="utf-8")
        runner.run(self.V, background=True)
        self.assertNotEqual(p.read_text(encoding="utf-8"), "健檢之前的樣子\n")
        r = run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(p.read_text(encoding="utf-8"), "健檢之前的樣子\n")


class PurgeLintBackups(unittest.TestCase):
    """裁定 6：健檢報告寫前備進回合之後，purge 把回合夾裡健檢報告與 lint.json 的備份整份刪掉；現行報告照舊逐字遮。"""
    from tests.test_lib_purge import Purge as _P
    setUp, tearDown = _P.setUp, _P.tearDown
    write_synthesis, exclude = _P.write_synthesis, _P.exclude

    def test_22_purge_drops_report_and_lint_backups(self):
        from kb.lint import state as lint_state
        from tests.test_lib_purge import hits, kb
        V = self.V
        title = "王家心情"
        report_rel = "系統/健檢報告/2026-10.md"
        report = V / report_rel
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(f"# 健檢報告 2026-10\n- 「{title}」那張的出處點不開\n", encoding="utf-8")
        lint_state.change(V, lambda d: d["month_done"].append({"date": "2026-10-20", "text": f"標了「{title}」那張"}) or True)
        t = turn.start(V, None, "健檢")["turn"]
        turn.backup(V, report_rel, t)
        turn.backup(V, ".system/lint.json", t)
        files = V / ".system" / "versions" / t / "files"
        self.assertIn(title, (files / report_rel).read_text(encoding="utf-8"))
        self.assertIn(title, (files / ".system" / "lint.json").read_text(encoding="utf-8"))
        turn.start(V, None, "不要讀私人那夾")
        code, out = self.exclude()
        self.assertEqual(code, 0, out)
        self.write_synthesis("信義王現在很好。")
        code, out = kb("folders", "purge", "客戶案件/私人", "--vault", str(V))
        self.assertEqual(code, 0, out)
        backups = [p for p in (V / ".system" / "versions").rglob("*")
                   if p.is_file() and ("/files/系統/健檢報告/" in p.as_posix() or p.as_posix().endswith("/files/.system/lint.json"))]
        self.assertEqual(backups, [])
        self.assertEqual([h for h in hits(V, title) if h.startswith(".system/versions/")], [])
        now = report.read_text(encoding="utf-8")
        self.assertNotIn(title, now)
        self.assertIn("（已排除）", now)


# ---------- 24. B-424 (1) ----------

class GuardAskMask(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        from tests._guard_fixture import make_vault
        cls.tmp, cls.V, _raw = make_vault()
        os.environ["CLAUDE_PLUGIN_ROOT"] = str(ROOT)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def reason(self, rest):
        from tests._guard_fixture import payload
        from kb import guard
        d = guard.decide(payload("Bash", f'python "{ROOT.as_posix()}/scripts/kb.py" {rest}', self.V))
        self.assertEqual(d.decision, "ask")
        return d.reason

    def test_24_fixed_sentence_not_masked(self):
        from kb import guard
        self.assertEqual(self.reason("unlock $x --name a"), guard.ASK_PREFIX + guard.ASK_UNKNOWN)

    def test_24_name_still_masked(self):
        got = self.reason("unlock get --name 密碼=hunter2")
        self.assertNotIn("hunter2", got)
        self.assertTrue(got.startswith(guard_prefix()), got)


def guard_prefix():
    from kb import guard
    return guard.ASK_PREFIX + "要把存好的「"


# ---------- 25、26. B-046 (2)、B-045 (1) ----------

class InventoryDuplicates(unittest.TestCase):
    def setUp(self):
        from tests.test_scripts_inventory_cli import make_inv_vault
        self.tmp, self.V, self.raw = make_inv_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def source_dir(self):
        from kb._lib import sources as sources_lib
        return Path(sources_lib.load(self.V).entries[0]["root"])

    def scan(self):
        r = run_kb("inventory", "scan", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout.splitlines()

    def test_25_duplicates_listed(self):
        root = self.source_dir()
        (root / "甲報價.txt").write_text("甲的報價 100 萬\n", encoding="utf-8")
        (root / "乙合約.txt").write_text("乙的合約 200 萬\n", encoding="utf-8")
        self.scan()
        (root / "副本").mkdir()
        shutil.copy2(root / "甲報價.txt", root / "副本" / "甲報價.txt")
        shutil.copy2(root / "乙合約.txt", root / "副本" / "乙合約.txt")
        lines = self.scan()
        dup = [x for x in lines if x.startswith("同一份內容在多處：")]
        self.assertEqual(len(dup), 1, lines)
        self.assertIn("甲報價.txt（2 處）", dup[0])
        self.assertIn("乙合約.txt（2 處）", dup[0])
        self.assertEqual(lines.index(dup[0]), 2)

    def test_25_no_duplicates_no_line(self):
        self.scan()  # 範例來源本來就有重複檔：第一次掃才報；之後沒有新的重複就不印
        self.assertFalse(any(x.startswith("同一份內容在多處") for x in self.scan()))

    def test_26_hidden_exclude_trims_location(self):
        from kb._lib import sources as sources_lib
        root = self.source_dir()
        (root / "不讀").mkdir()
        (root / "甲報價.txt").write_text("甲的報價 100 萬\n", encoding="utf-8")
        shutil.copy2(root / "甲報價.txt", root / "不讀" / "甲報價.txt")
        self.scan()
        alias = sources_lib.load(self.V).entries[0]["alias"]
        r = run_kb("folders", "exclude", f"{alias}/不讀", "--kind", "hidden", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("清冊：1 份少了這裡的位置（別處的照常讀）", r.stdout.splitlines())
        self.assertNotIn("0 份已拿掉", r.stdout)


if __name__ == "__main__":
    unittest.main()
