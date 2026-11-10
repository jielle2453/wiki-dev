"""skills/ingest 的形狀（ingest 製卡第 9 點，驗收 16、17、21）：frontmatter 只有 name、description；描述 150 字內、不帶英文；
本文 120 行內（字數上限在 test_budget，目標 3000 字內）、用 ${CLAUDE_PLUGIN_ROOT} 叫 kb.py、不寫絕對路徑；兩份 reference 在且 ≤150 行；
tests/evals/ingest.json 20 句、各半、不重複，不該觸發的有 manage、answer、note、produce 句；
templates/card.md 的檔頭鍵與 carding.md 的欄位表跟 cards.KEYS 一致；manage 只改了「加資料夾」那列的收尾句。
字數門檻在 test_budget，這裡只守形狀。"""
import json
import re
import unittest

from tests._guard_fixture import ROOT
from kb._lib import cards  # noqa: E402

SKILL_DIR = ROOT / "skills" / "ingest"
SKILL = SKILL_DIR / "SKILL.md"
MODULES = ("batch.md", "carding.md", "agenda-scan.md", "synthesis-batch.md", "synthesis-broken.md", "adopt.md")  # D-521
REFS = tuple(f"references/{m}" for m in MODULES) + ("references/commands.md", "references/redo.md")
AGENT_ONLY = tuple(f"references/{m}" for m in MODULES if m != "carding.md")
EVALS = ROOT / "tests" / "evals" / "ingest.json"
TEMPLATE = ROOT / "templates" / "card.md"
MANAGE = ROOT / "skills" / "manage" / "SKILL.md"
DESC_MAX = 150
BODY_MAX_LINES = 120
REFERENCE_MAX_LINES = 150
ABS_PATH = re.compile(r"(?<![A-Za-z$])[A-Za-z]:[\\/]|/Users/|/home/")
NOT_TRIGGER = ("上次那份報價在哪", "以後報價一律附日期", "做成 Word")
MANAGE_CLOSE = "加完問要不要整理成卡，要就照 ingest。"


def split(text):
    lines = text.splitlines()
    assert lines and lines[0] == "---", "SKILL.md 開頭不是 ---"
    end = lines.index("---", 1)
    return lines[1:end], "\n".join(lines[end + 1:])


class Frontmatter(unittest.TestCase):
    def setUp(self):
        front, self.body = split(SKILL.read_text(encoding="utf-8"))
        self.fields = dict(line.split(":", 1) for line in front)

    def test_only_name_and_description(self):
        self.assertEqual(set(self.fields), {"name", "description"})
        self.assertEqual(self.fields["name"].strip(), "ingest")

    def test_description_short_chinese(self):
        desc = self.fields["description"].strip()
        self.assertTrue(desc)
        self.assertLessEqual(len(desc), DESC_MAX)
        self.assertIsNone(re.search(r"[A-Za-z]{2,}", desc), desc)


class Body(unittest.TestCase):
    def setUp(self):
        self.body = split(SKILL.read_text(encoding="utf-8"))[1]

    def test_size(self):
        self.assertLessEqual(len(self.body.splitlines()), BODY_MAX_LINES)

    def test_calls_kb_through_plugin_root(self):
        self.assertIn("${CLAUDE_PLUGIN_ROOT}/scripts/kb.py", self.body)

    def test_order_of_steps(self):
        """骨架一節依序出現：changes → cards todo --json → plan → asks → turn note（整理 ingest 實作疑義裁定 1）。"""
        marks = ["changes", "cards todo --json", "plan", "asks", "turn note"]
        steps = self.body[self.body.index("## 骨架"):self.body.index("## 共通")]
        pos = [steps.index(m) for m in marks]
        self.assertEqual(pos, sorted(pos), marks)

    def test_mentions_judgment_words_and_principles(self):
        """仍屬判斷的字眼留在本文；答法對照（指令字串）不能回來（驗收 7）；兩條原則帶編號（裁定 1、2）。"""
        for want in ("manage", "收件", "還沒存檔"):
            with self.subTest(want=want):
                self.assertIn(want, self.body)
        for banned in ("cards drop", "pending resolve", "entity rename"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, self.body)
        for lead, code in (("原檔不見當作客戶刪的", "I-082"), ("一次問一件", "D-135")):
            with self.subTest(principle=lead):
                line = next((ln for ln in self.body.splitlines() if lead in ln), "")
                self.assertIn(code, line)

    def test_no_card_field_names(self):
        """驗收 7：欄位名住程式輸出，本文不寫。"""
        for field in ("new", "stale", "unlinked", "synthesis_new", "entity_drift"):
            with self.subTest(field=field):
                self.assertNotRegex(self.body, rf"(?<![A-Za-z_]){field}(?![A-Za-z_])")

    def test_no_absolute_paths(self):
        for p in (SKILL, *(SKILL_DIR / r for r in REFS)):
            with self.subTest(file=p.name):
                self.assertIsNone(ABS_PATH.search(p.read_text(encoding="utf-8")), p.name)

    def test_references_exist_and_short(self):
        for ref in REFS:
            if ref not in AGENT_ONLY:  # 拆出來的模組給製卡助手照批次的 read 讀，SKILL.md 不列（D-521）
                self.assertIn(ref, self.body)
            p = SKILL_DIR / ref
            with self.subTest(reference=ref):
                self.assertTrue(p.is_file())
                self.assertLessEqual(len(p.read_text(encoding="utf-8").splitlines()), REFERENCE_MAX_LINES)


class Evals(unittest.TestCase):
    def setUp(self):
        self.items = json.loads(EVALS.read_text(encoding="utf-8"))

    def test_twenty_half_and_half_unique(self):
        self.assertEqual(len(self.items), 20)
        for item in self.items:
            self.assertEqual(set(item), {"query", "should_trigger"})
            self.assertIsInstance(item["should_trigger"], bool)
        self.assertEqual(sum(i["should_trigger"] for i in self.items), 10)
        self.assertEqual(len({i["query"] for i in self.items}), 20)

    def test_negatives_cover_neighbours(self):
        negatives = [i["query"] for i in self.items if not i["should_trigger"]]
        for want in NOT_TRIGGER:
            with self.subTest(want=want):
                self.assertTrue(any(want in q for q in negatives), want)
        self.assertTrue(any("加進來" in q for q in negatives), "要有一句 manage")


def template_keys(text):
    lines = text.splitlines()
    start = lines.index("---")
    end = lines.index("---", start + 1)
    return [ln.split(":", 1)[0] for ln in lines[start + 1:end] if ln and not ln.startswith(" ")]


class FieldTables(unittest.TestCase):
    def test_template_keys_match_cards_keys(self):
        self.assertEqual(template_keys(TEMPLATE.read_text(encoding="utf-8")), list(cards.KEYS))

    def test_carding_table_matches(self):
        text = (SKILL_DIR / "references" / "carding.md").read_text(encoding="utf-8")
        rows = [ln for ln in text.splitlines() if ln.startswith("| `")]
        keys = [re.match(r"\| `([^`]+)`", ln).group(1) for ln in rows]
        self.assertEqual(keys, list(cards.KEYS))

    def test_template_header_comment(self):
        first = TEMPLATE.read_text(encoding="utf-8").splitlines()[0]
        self.assertTrue(first.startswith("<!--") and "kb cards todo" in first and "沒內容的段不寫" in first, first)


class ManageRow(unittest.TestCase):
    def test_add_row_closing_sentence(self):
        """manage 第二版改成 D-132 的骨架：加資料夾那行加完問要不要整理成卡，要就交給 ingest。"""
        row = next(ln for ln in MANAGE.read_text(encoding="utf-8").splitlines() if ln.startswith("- **加資料夾**"))
        self.assertTrue(row.rstrip().endswith(MANAGE_CLOSE), row[-80:])
        self.assertNotIn("整理成卡的功能之後補", row)



class CardMakerSkeleton(unittest.TestCase):
    """card-maker（D-196～D-200）：骨架派工 → 收通知再派 → done 才拿 asks、tell → note_cmd；停與進度各有一步；三條原則帶編號。"""

    def setUp(self):
        self.body = split(SKILL.read_text(encoding="utf-8"))[1]
        self.steps = self.body[self.body.index("## 骨架"):self.body.index("## 共通")]

    def test_dispatch_flow_in_order(self):
        marks = ["cards todo --json", "cards dispatch --json", "Agent 工具", "subagent_type", "approval", "cards status",
                 "cards stop --json", "TaskStop", "`asks` 有就問一件", "note_cmd", "turn note"]
        pos = [self.steps.index(m) for m in marks]
        self.assertEqual(pos, sorted(pos), marks)

    def test_three_new_principles(self):
        for lead, code in (("製卡交給製卡助手", "D-196"), ("派工照程式給的 prompt", "D-197"), ("子代理的回報不轉述檔案內容", "D-022")):
            with self.subTest(principle=lead):
                line = next((ln for ln in self.body.splitlines() if lead in ln), "")
                self.assertIn(code, line)

    def test_references_cover_new_commands(self):
        commands = (SKILL_DIR / "references" / "commands.md").read_text(encoding="utf-8")
        for head in ("## cards dispatch", "## cards status", "cards stop", "## cards unreadable"):
            with self.subTest(head=head):
                self.assertIn(head, commands)
        self.assertNotIn("按停止", commands)
        modules = "".join((SKILL_DIR / "references" / m).read_text(encoding="utf-8") for m in MODULES)
        for want in ("## 批次（card-maker）", "## 材料的欄位", "被擋或打回：", "kb cards unreadable"):
            with self.subTest(want=want):
                self.assertIn(want, modules)


# 原 carding.md 每一節的關鍵句（D-521 驗收 5：拆成模組後每條都還在某一份）
OLD_SECTIONS = {
    "批次": ("第一步跑 `kb cards batch <批次> --json`", "清單只用 `items`，不跑 `cards todo`", "「被擋或打回：」那行的寫法也在那裡",
           "多回一行「字典外：<型別>的<欄>：<詞>」", "製卡者是背景的 card-maker"),
    "材料的欄位": ("`moved`：`{\"id\",\"from\",\"to\"}`", "`orphans`：卡的編號不在清冊", "`profile_missing` 是 true 時",
              "`card_types`（`[{\"name\",\"sections\"", "`entities`：`[{\"name\",\"type\",\"aliases\",\"self\"}]`",
              "`agenda_recheck`：`{\"id\"（日程條目）", "`unlinked`：`{\"id\",\"path\",\"reason\",\"types\",\"prefill\"}`",
              "`synthesis_new`：`{\"entity_id\"", "「出處點不開」", "`synthesis_broken`：`{\"path\",\"reason\"}`",
              "`entity_drift`：`{\"entity_id\"", "`tag_only: true`", "`missing_types`："),
    "一": ("先跑 `convert <編號>`，照它印的做",), "二": ("檔頭是卡的第一段",), "三": ("檔頭之後寫 `# <標題>`",),
    "四": ("正文夠用就好",), "五": ("表外但明顯是證號",), "六": ("轉換結果是空的（空檔）",), "七": ("`unlinked` 是要補掛實體的舊卡",),
    "八": ("`synthesis_broken` 每項 `{path, reason}`", "再跑 `kb entity clean <path>`"),
    "九": ("**直接加（D-128）**", "**結束證據（D-127）**", "**待重對（`agenda_recheck`，D-130）**", "**工期**"),
    "十": ("**「可以讀」的密碼檔**", "開的時候印「密碼不對」"), "十一": ("`names` 每項是到門檻",), "十二": ("`items` 每項 `{name, chunk}`",),
    "十三": ("`stale` 每項帶 `change`", "指路卡（檔頭 `卡式: 指路`", "`pointer_changed`（`{id, title, change, diff}`"),
}
SECTION_REF = re.compile(r"carding\.md[^\n。；，、（]{0,6}?第?([一二三四五六七八九十]{1,3})(?:～([一二三四五六七八九十]{1,3}))?節")


class ModuleSplit(unittest.TestCase):
    """D-521 驗收 5：原 carding.md 每條規則都在某一份新檔；design/ 以外沒有指到 carding.md 不存在的節號。"""

    def test_every_old_rule_kept(self):
        modules = "".join((SKILL_DIR / "references" / m).read_text(encoding="utf-8") for m in MODULES)
        for sec, phrases in OLD_SECTIONS.items():
            for want in phrases:
                with self.subTest(section=sec, want=want):
                    self.assertIn(want, modules)

    def test_no_dangling_section_refs(self):
        carding = (SKILL_DIR / "references" / "carding.md").read_text(encoding="utf-8")
        heads = set(re.findall(r"^## ([一二三四五六七八九十]+)、", carding, re.M))
        self.assertEqual(heads, {"一", "二", "三", "四", "五", "六", "七", "十", "十一", "十三"})  # 十三 留 carding.md（裁定 4）
        skip = ("design", "tests", ".git")
        for f in list(ROOT.rglob("*.md")) + list(ROOT.rglob("*.py")):
            rel = f.relative_to(ROOT)
            if rel.parts[0] in skip or rel.name == "CHANGELOG.md":
                continue
            for m in SECTION_REF.finditer(f.read_text(encoding="utf-8")):
                for num in filter(None, m.groups()):
                    with self.subTest(file=str(rel), ref=m.group(0)):
                        self.assertIn(num, heads)


class SimpleCardForAiNotes(unittest.TestCase):
    """D-519（#33）：md 檔的卡（不管誰寫的）寫簡單版，只寫重點三到五點。"""

    def test_carding_simple_version(self):
        carding = (SKILL_DIR / "references" / "carding.md").read_text(encoding="utf-8")
        line = next(ln for ln in carding.splitlines() if "簡單版" in ln)
        for want in ("md 檔（不管誰寫的）", "## 重點", "三到五點", "D-519"):
            with self.subTest(want=want):
                self.assertIn(want, line)
        self.assertIn("2. md 檔例外：只寫第 1 點的簡單版", carding)


class MoneyConfirm(unittest.TestCase):
    """記帳確認報告 #3、#5：子代理都讀的 card-maker 說字有 $ 用單引號；ingest 的 money.md 範例用單引號、沒寫日期不給 --date --due。"""

    def test_3_single_quotes(self):
        agent = (ROOT / "agents" / "card-maker.md").read_text(encoding="utf-8")
        self.assertIn("單引號", agent)
        self.assertIn("`$`", agent)
        money = (SKILL_DIR / "references" / "money.md").read_text(encoding="utf-8")
        self.assertIn("--text '<讀到什麼、哪裡看不出>'", money)
        self.assertNotIn('--text "', money)

    def test_5_no_date_is_open(self):
        money = (SKILL_DIR / "references" / "money.md").read_text(encoding="utf-8")
        self.assertIn("沒寫日期", money)
        self.assertIn("不要記成今天", money)


if __name__ == "__main__":
    unittest.main()


class Wip(unittest.TestCase):
    """D-525 第 7 點、裁定 3、5：她說整理才用，開場有變動那條拿掉；md 用 --ids 只做卡；commands.md 有 cards wip。"""

    def test_drift_deleted_synthesis_card(self):
        """刪綜合卡說一聲 第 1 點（D-311(3)）：實體夾有變那段，綜合卡被刪的照 entity_drift 判斷、用現有指令做、最後說一聲。"""
        body = split(SKILL.read_text(encoding="utf-8"))[1]
        line = next((l for l in body.splitlines() if "實體夾有變" in l), "")
        for want in ("carding.md", "entity remove", "說一聲", "asks", "D-311(3)"):
            self.assertIn(want, line)
        ref = (SKILL_DIR / "references" / "carding.md").read_text(encoding="utf-8")
        field = next((l for l in ref.splitlines() if l.startswith("- `entity_drift`")), "")
        for want in ("progress", "last_activity", "deleted_with", "mounts", "similar", "D-311(3)"):
            self.assertIn(want, field)

    def test_triggers(self):
        front, body = split(SKILL.read_text(encoding="utf-8"))
        fields = dict(line.split(":", 1) for line in front)
        self.assertNotIn("開場", fields["description"])
        self.assertNotIn("開場有變動先派整理", body)
        self.assertIn("cards wip", body)
        self.assertIn("--ids", body)
        self.assertIn("不只 X", body)
        self.assertIn("一律 `cards dispatch` 不帶 `--ids`", body, "裁定 15：她說整理 md 也照常整理")
        self.assertIn("她這句沒說整理", body)

    def test_commands_has_wip(self):
        text = (SKILL.parent / "references" / "commands.md").read_text(encoding="utf-8")
        self.assertIn("`cards wip [--json]`", text)
        self.assertIn("主對話也用它整理每句開頭那行列的 md", text)

    def test_md_card_logs_entities(self):
        """裁定 6：md 卡寫完，對卡上的實體各跑一次 kb entity log --synced；不讀綜合卡、不改現況。"""
        text = (SKILL.parent / "references" / "carding.md").read_text(encoding="utf-8")
        line = next(ln for ln in text.splitlines() if ln.startswith("2. md 檔例外"))
        self.assertIn("kb entity log <實體> '<文件日期> <卡標題>〔<卡編號>〕'", line)
        self.assertNotIn("--synced", line, "裁定 7：只加紀事，不標整理到")
        self.assertIn("不讀綜合卡、不改現況", line)
