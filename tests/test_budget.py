"""常駐預算（D-070）。數字住這裡，超過就紅。字數算法：len(text)，不去空白。

檔案不存在就 skipTest；存在就量。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]

SKILL_DESC_MAX_CHARS = 150
SKILL_DESC_TOTAL_MAX_CHARS = 900
CORE_MAX_LINES = 60
CORE_MAX_CHARS = 2500
CLIENT_CLAUDE_MD_MAX_LINES = 25
CLIENT_CLAUDE_MD_MAX_CHARS = 1200
SKILL_BODY_MAX_LINES = 120
SKILL_BODY_MAX_CHARS = 5000
REFERENCE_MAX_LINES = 150
RESIDENT_TOTAL_MAX_CHARS = 5050  # 放寬乙：core 與 CLAUDE.md 換成新說法（變長），5000→5050；實測 5021
OPENING_MAX_LINES = 8
TURN_MAX_LINES = 8  # 放寬丙 3b：每句開頭（第一句最壞：變動、整理指示、找不到來源、設定檔、日程都在）
TURN_MAX_CHARS = 1000
OPENING_MAX_CHARS = 600  # 放寬甲：開場兩句改成 spec 的新句（變長），550→600；原註 客戶機路徑量（B-060、D-070 補）：最壞情況（有新版加滿六行）521；原本 400 是開發機短路徑量的

SKILLS_DIR = ROOT / "skills"
CORE = ROOT / "rules" / "core.md"
CLIENT_CLAUDE_MD = ROOT / "skeleton" / "CLAUDE.md"
FIXTURE_TOO_LONG = ROOT / "tests" / "fixtures" / "budget" / "too_long_SKILL.md"
SESSION_HOOK = ROOT / "hooks" / "session.py"
TURN_HOOK = ROOT / "hooks" / "turn.py"
FIXTURE_VAULT = ROOT / "tests" / "fixtures" / "vault"
# B-060：開場 kb 那行要照客戶電腦上最長的合理路徑量（plugin 裝在 ~/.claude/plugins/cache/<市集>/wiki-with-willy/<版本>/ 底下，
# 比開發機的 worktree 路徑長）：20 字的使用者名稱、20 字的市集名、9 字的版本。刻意拆開拼，讓本檔不含開發機路徑字串
LONG_PLUGIN_ROOT = ("C:" + "/Users/" + "名" * 20 + "/.claude/plugins/cache/" + "m" * 20 + "/wiki-with-willy/99.99.999")


def read(path):
    return path.read_text(encoding="utf-8")


def count_lines(text):
    return len(text.splitlines())


def split_skill(text):
    """回 (description, body)。frontmatter 是開頭兩個 --- 之間；沒有 frontmatter 就 description 空。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return "", text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            front, body = lines[1:i], lines[i + 1:]
            break
    else:
        return "", text
    desc = ""
    for line in front:
        if line.startswith("description:"):
            desc = line[len("description:"):].strip()
    return desc, "\n".join(body)


def measure_skill(path):
    desc, body = split_skill(read(path))
    return {"desc_chars": len(desc), "body_lines": count_lines(body), "body_chars": len(body)}


def skill_over_budget(m):
    return (
        m["desc_chars"] > SKILL_DESC_MAX_CHARS
        or m["body_lines"] > SKILL_BODY_MAX_LINES
        or m["body_chars"] > SKILL_BODY_MAX_CHARS
    )


def skill_files():
    return sorted(SKILLS_DIR.glob("*/SKILL.md")) if SKILLS_DIR.is_dir() else []


class SkillBudget(unittest.TestCase):
    def test_each_skill_description_and_body(self):
        files = skill_files()
        if not files:
            self.skipTest("skills/ 尚未建立")
        for p in files:
            m = measure_skill(p)
            with self.subTest(skill=p.parent.name):
                self.assertLessEqual(m["desc_chars"], SKILL_DESC_MAX_CHARS)
                self.assertLessEqual(m["body_lines"], SKILL_BODY_MAX_LINES)
                self.assertLessEqual(m["body_chars"], SKILL_BODY_MAX_CHARS)

    def test_skill_descriptions_total(self):
        files = skill_files()
        if not files:
            self.skipTest("skills/ 尚未建立")
        total = sum(measure_skill(p)["desc_chars"] for p in files)
        self.assertLessEqual(total, SKILL_DESC_TOTAL_MAX_CHARS)

    def test_each_reference_lines(self):
        refs = sorted(SKILLS_DIR.glob("*/references/*.md")) if SKILLS_DIR.is_dir() else []
        if not refs:
            self.skipTest("skills/*/references/ 尚未建立")
        for p in refs:
            with self.subTest(reference=f"{p.parent.parent.name}/{p.name}"):
                self.assertLessEqual(count_lines(read(p)), REFERENCE_MAX_LINES)


class CoreBudget(unittest.TestCase):
    def test_core_lines_and_chars(self):
        if not CORE.exists():
            self.skipTest("rules/core.md 尚未建立")
        text = read(CORE)
        self.assertLessEqual(count_lines(text), CORE_MAX_LINES)
        self.assertLessEqual(len(text), CORE_MAX_CHARS)


class ClientClaudeMdBudget(unittest.TestCase):
    def test_client_claude_md_lines_and_chars(self):
        if not CLIENT_CLAUDE_MD.exists():
            self.skipTest("skeleton/CLAUDE.md 尚未建立")
        text = read(CLIENT_CLAUDE_MD)
        self.assertLessEqual(count_lines(text), CLIENT_CLAUDE_MD_MAX_LINES)
        self.assertLessEqual(len(text), CLIENT_CLAUDE_MD_MAX_CHARS)


def opening_status(source, prepare=None):
    """跑 hooks/session.py，回 additionalContext 在 core 全文之前的狀態行（不含隔開的空行）。prepare(vault) 先改 fixture 複本。"""
    tmp = Path(tempfile.mkdtemp(prefix="kbbudget-"))
    try:
        vault = tmp / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        if prepare is not None:
            prepare(vault)
        data = {"session_id": "budget", "cwd": str(vault), "hook_event_name": "SessionStart", "source": source}
        r = subprocess.run([sys.executable, str(SESSION_HOOK)], input=json.dumps(data), capture_output=True,
                           text=True, encoding="utf-8", cwd=str(vault), env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)))
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    core = read(CORE)
    tail = "\n\n" + core
    assert ctx.endswith(tail), "additionalContext 結尾不是空行加 core 全文"
    return ctx[:-len(tail)].replace(ROOT.as_posix(), LONG_PLUGIN_ROOT)  # B-060：換成客戶電腦最長的合理路徑再量


class OpeningBudget(unittest.TestCase):
    def test_status_lines_startup_and_compact(self):
        if not SESSION_HOOK.exists():
            self.skipTest("hooks/session.py 尚未建立")
        for source in ("startup", "compact"):
            status = opening_status(source)
            with self.subTest(source=source):
                self.assertLessEqual(count_lines(status), OPENING_MAX_LINES)
                self.assertLessEqual(len(status), OPENING_MAX_CHARS)


def turn_status(prepare=None, session_id="budget-turn"):
    """跑 hooks/turn.py（每句開頭，放寬丙 3b），回 additionalContext 的行（沒有輸出回 []）。"""
    tmp = Path(tempfile.mkdtemp(prefix="kbbudget-"))
    try:
        vault = tmp / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        if prepare is not None:
            prepare(vault)
        data = {"session_id": session_id, "cwd": str(vault), "prompt": "問", "hook_event_name": "UserPromptSubmit"}
        r = subprocess.run([sys.executable, str(TURN_HOOK)], input=json.dumps(data), capture_output=True,
                           text=True, encoding="utf-8", cwd=str(vault), env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)))
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"].splitlines() if r.stdout else []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def all_lines_vault(vault):
    """變動、有變動、找不到來源、設定檔四行同時在（客戶設定檔與型別第 12 點）：fixture 沒複製 raw，兩個來源都找不到、
    清冊是空的（知識庫裡的檔都算新增）；設定檔三節各改一處，再加一個不在型別表的第一層夾。
    變動行帶「實體夾有變」（實體與綜合卡第 7 點）：信義王 card true、夾被客戶改名。
    日程行（日程第 6 點）三個數字都有：一條逾期、一條今天、一條 7 天內，七行是最壞情況。"""
    md = vault / "系統" / "客戶設定檔.md"
    text = md.read_text(encoding="utf-8")
    text = text.replace("| 案子 | 事 |  | 推測 | 2026-10-19 |", "| 案子 | 事 |  | 推測 | 2026-10-19 |\n| 工地 | 事 | 一個裝修案 |")
    text = text.replace("| 報價 | 日期與數字 |  |", "| 報價 | 日期與數字 | ✓ |")
    text = text.replace("| 地址 | 只記種類 | 推測 | 2026-10-19 |", "| 地址 | 只記種類 | 推測 | 2026-10-19 |\n| 請款 | 不整理 |")
    md.write_text(text, encoding="utf-8", newline="\n")
    (vault / "合作廠商與工班名冊").mkdir()
    entities_fix = ROOT / "tests" / "fixtures" / "entities"
    shutil.copy2(entities_fix / "entities.json", vault / ".system" / "entities.json")
    shutil.copy2(entities_fix / "信義王.md", vault / "案子" / "信義王" / "信義王.md")
    (vault / "案子" / "信義王").rename(vault / "案子" / "信義王的家")
    agenda_item = {"id": "a-5e6f7a8b", "kind": "deadline", "start": None, "date": "2020-01-01", "ended": None, "time": None,
                   "text": "付款", "entities": [], "status": "open", "source": "confirmed", "origin": None, "lead_days": None,
                   "created_turn": "t", "history": []}
    other = dict(agenda_item, id="a-00000001", kind="meeting", date=date.today().isoformat())
    soon = dict(agenda_item, id="a-00000002", kind="meeting", date=(date.today() + timedelta(days=2)).isoformat())
    (vault / ".system" / "agenda.json").write_text(
        json.dumps({"schema_version": 1, "items": [agenda_item, other, soon]}, ensure_ascii=False), encoding="utf-8")


class OpeningAllLines(unittest.TestCase):
    def test_opening_lines_within_budget(self):
        """開場只留 kb 行、這台每天第一次的日程／版本／搬家、摺疊行（放寬丙 3b）：最壞情況在預算內。"""
        if not SESSION_HOOK.exists():
            self.skipTest("hooks/session.py 尚未建立")
        for source in ("startup", "compact"):
            status = opening_status(source, all_lines_vault)
            lines = status.splitlines()
            with self.subTest(source=source):
                self.assertEqual(sum(1 for ln in lines if ln.startswith("日程：逾期 1（")), 1, lines)
                self.assertFalse([ln for ln in lines if "變動" in ln], lines)
                self.assertLessEqual(count_lines(status), OPENING_MAX_LINES)
                self.assertLessEqual(len(status), OPENING_MAX_CHARS, (len(status), lines))

    def test_turn_lines_within_budget(self):
        """每句開頭的行（變動、整理指示、找不到來源、設定檔、日程）同時都在的第一句：守 TURN_MAX_LINES、TURN_MAX_CHARS。"""
        lines = turn_status(all_lines_vault)
        for head in ("這台電腦找不到來源", "設定檔被手改了（", "日程：逾期 1（", "實體夾有變 2："):
            self.assertEqual(sum(1 for ln in lines if ln.startswith(head)), 1, (head, lines))
        self.assertEqual(sum(1 for ln in lines if re.match(r"有 \d+ 份新放或改過（製作中）", ln)), 1, lines)  # D-525
        self.assertLessEqual(len(lines), TURN_MAX_LINES)
        self.assertLessEqual(len("\n".join(lines)), TURN_MAX_CHARS, len("\n".join(lines)))


def version_line_vault(kind):
    """line_version 三種句子的最壞情況（B-060、升級打包 驗收 17）：在 all_lines_vault 的六行都在之上再加一句。
    a 換了版要 --finish（整理指示讓位）、b 有新版加最長的一句話（update_note_max 字）、c 撤回。"""
    def prepare(vault):
        import platform
        all_lines_vault(vault)
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
        hist = {"schema_version": 1, "current": "0.1.0" if kind == "a" else plugin, "pending": None, "history": []}
        chk = {"date": date.today().isoformat(), "latest": None, "kind": None, "allowed": False, "note": None,
               "auto_patched": None, "error": None}
        if kind == "b":
            chk.update(latest="99.99.999", kind="major", allowed=True, note="字" * 40)
        if kind == "c":
            chk.update(latest="0.0.1", kind="downgrade", allowed=True, note="x")
        (vault / ".system" / "upgrade-history.json").write_text(json.dumps(hist), encoding="utf-8")
        (vault / ".system" / "env.json").write_text(json.dumps(
            {"schema_version": 1, "machines": {platform.node() or "unknown": {"update_check": chk}}}), encoding="utf-8")
    return prepare


class OpeningVersionLines(unittest.TestCase):
    def test_each_version_line_worst_case_within_budget(self):
        if not SESSION_HOOK.exists():
            self.skipTest("hooks/session.py 尚未建立")
        heads = {"a": "已換到 ", "b": "有新版 ", "c": "這一版 "}
        for kind, head in heads.items():
            status = opening_status("compact", version_line_vault(kind))
            lines = status.splitlines()
            with self.subTest(kind=kind):
                self.assertEqual(sum(1 for ln in lines if ln.startswith(head)), 1, lines)
                self.assertTrue(lines[0].startswith("【wiki-with-willy】kb 指令：python \"" + LONG_PLUGIN_ROOT), "kb 行用長路徑量")
                self.assertLessEqual(count_lines(status), OPENING_MAX_LINES, lines)
                self.assertLessEqual(len(status), OPENING_MAX_CHARS, (len(status), lines))

    def test_finish_line_hides_the_ingest_hint_so_it_is_not_the_worst_case(self):
        lines = turn_status(version_line_vault("a"))
        self.assertFalse([ln for ln in lines if re.match(r"有 \d+ 份", ln)], lines)


PREFERENCE_MAX = 20  # 開場那組（整理成卡以外，D-504）；整理成卡那組不進開場
PREFERENCE_MAX_CHARS = 1000
WORST_USES = ("全部", "做文件", "每日議題")  # 分三組：小標也算進去


def opening_preferences_chars():
    """設定檔第六節開場那組放滿（20 條、合計 1000 字，分全部、做文件、一個客製 skill 三組）時，開場在 core 之後多出來的字數。"""
    texts = [f"{i:02d}" + "偏" * 48 for i in range(PREFERENCE_MAX)]
    assert sum(len(t) for t in texts) == PREFERENCE_MAX_CHARS

    def prepare(vault):
        p = vault / ".system" / "profile.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["preferences"] = [{"text": t, "use": WORST_USES[i % 3], "source": "corrected", "date": "2026-10-20"}
                               for i, t in enumerate(texts)]
        data["schema_version"] = 3
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp = Path(tempfile.mkdtemp(prefix="kbbudget-"))
    try:
        vault = tmp / "vault"
        shutil.copytree(FIXTURE_VAULT, vault)
        prepare(vault)
        data = {"session_id": "budget", "cwd": str(vault), "hook_event_name": "SessionStart", "source": "compact"}
        r = subprocess.run([sys.executable, str(SESSION_HOOK)], input=json.dumps(data), capture_output=True,
                           text=True, encoding="utf-8", cwd=str(vault), env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)))
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    core = read(CORE)
    block = ctx[ctx.index(core) + len(core):]
    assert block.startswith("\n客戶偏好（跟上面的核心規則衝突時照客戶的，只有刪掉、蓋掉之前先留一份不讓）：\n") and block.count("\n- ") == PREFERENCE_MAX, block[:80]
    assert "\n做文件時：\n" in block and "\n每日議題：\n" in block, block
    return len(block)


class ResidentTotal(unittest.TestCase):
    def test_answer_description_is_counted(self):
        """answer 第 15 點：常駐合計含 answer 的描述（四個 skill 的描述都在 skill_files 裡）。"""
        self.assertLessEqual({"answer", "ingest", "manage", "note"}, {p.parent.name for p in skill_files()})

    def test_resident_total(self):
        parts = [measure_skill(p)["desc_chars"] for p in skill_files()]
        for p in (CORE, CLIENT_CLAUDE_MD):
            if p.exists():
                parts.append(len(read(p)))
        if SESSION_HOOK.exists():
            parts.append(len(opening_status("compact")) + len("\n\n"))  # 狀態行與 core 之間的空行也進常駐
        if not parts:
            self.skipTest("常駐檔尚未建立")
        if SESSION_HOOK.exists():  # note 改規則驗收 13（D-137、D-504）：偏好開場那組最壞 20 條 1000 字，開場段接在 core 之後
            parts.append(opening_preferences_chars())
        self.assertLessEqual(sum(parts), RESIDENT_TOTAL_MAX_CHARS)


class SelfTest(unittest.TestCase):
    """內建自測：量超長 fixture，必須判超標；否則量法本身壞了。"""

    def test_too_long_fixture_is_judged_over_budget(self):
        self.assertTrue(FIXTURE_TOO_LONG.exists(), f"缺 fixture：{FIXTURE_TOO_LONG.name}")
        m = measure_skill(FIXTURE_TOO_LONG)
        self.assertGreater(m["desc_chars"], SKILL_DESC_MAX_CHARS)
        self.assertGreater(m["body_lines"], SKILL_BODY_MAX_LINES)
        self.assertTrue(skill_over_budget(m))
        print("內建自測通過：too_long_SKILL.md 判超標", m)


if __name__ == "__main__":
    unittest.main()


AGENT_DESC_MAX_CHARS = 600
AGENT_BODY_MAX_CHARS = 3000
CARD_MAKER = ROOT / "agents" / "card-maker.md"
SUBAGENT_HOOK = ROOT / "hooks" / "subagent.py"


class CardMakerBudget(unittest.TestCase):
    """card-maker（驗收 15）：描述 600 字內、本文 3000 字內；SubagentStart 注入的狀態部分守開場預算、core 守 core 預算。"""

    def test_agent_description_and_body(self):
        if not CARD_MAKER.exists():
            self.skipTest("agents/card-maker.md 尚未建立")
        desc, body = split_skill(read(CARD_MAKER))
        self.assertTrue(desc)
        self.assertLessEqual(len(desc), AGENT_DESC_MAX_CHARS)
        self.assertLessEqual(len(body), AGENT_BODY_MAX_CHARS)

    def test_subagent_start_injection(self):
        if not SUBAGENT_HOOK.exists():
            self.skipTest("hooks/subagent.py 尚未建立")
        tmp = Path(tempfile.mkdtemp(prefix="kbbudget-"))
        try:
            vault = tmp / "vault"
            shutil.copytree(FIXTURE_VAULT, vault)
            data = {"session_id": "budget", "cwd": str(vault), "hook_event_name": "SubagentStart",
                    "agent_id": "a1", "agent_type": "wiki-with-willy:card-maker"}
            r = subprocess.run([sys.executable, str(SUBAGENT_HOOK), "start"], input=json.dumps(data), capture_output=True,
                               text=True, encoding="utf-8", cwd=str(vault), env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)))
            ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        core = read(CORE)
        self.assertTrue(ctx.endswith(chr(10) * 2 + core))
        status = ctx[:-len(core) - 2]
        self.assertLessEqual(count_lines(status), OPENING_MAX_LINES)
        self.assertLessEqual(len(status), OPENING_MAX_CHARS)
        self.assertLessEqual(len(ctx), RESIDENT_TOTAL_MAX_CHARS)


BUILD_SKILL = ROOT / "skills" / "build" / "SKILL.md"
BUILD_BODY_MAX_CHARS = 3000


class BuildSkillBudget(unittest.TestCase):
    """build 第 1 點（驗收 13）：只由人打（disable-model-invocation）、本文 3000 字內；references 的行數由上面那組量。"""

    def test_build_skill(self):
        text = read(BUILD_SKILL)
        front = text.split("---")[1]
        self.assertIn("disable-model-invocation: true", front.splitlines())
        self.assertIn("name: build", front.splitlines())
        _desc, body = split_skill(text)
        self.assertLessEqual(len(body), BUILD_BODY_MAX_CHARS)
        self.assertLessEqual(count_lines(body), SKILL_BODY_MAX_LINES)
