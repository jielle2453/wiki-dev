"""lint 桌面版確認後的修正（llm-wiki-test/lint-check/確認報告.md）：六件。
1 指令照設定檔的欄位、2 推測日程記成確認、3 先放著的讀不到不算沒整理完、4 整理還有只算做得了的、5 背景健檢在工作日誌的說法、
6 重做候選只收清冊 active 的卡。"""
import json
import re
import shutil
import unittest
from pathlib import Path

from tests import _cards
from tests import _entities as E
from tests import _lint as L
from tests._guard_fixture import ROOT
from tests.test_scripts_inventory_cli import run_kb
from kb import lint_cli  # noqa: E402
from kb._lib import agenda, cards, inventory, journal, pending, profile, turn  # noqa: E402
from kb.lint import report  # noqa: E402
from kb.lint.checks import rulings_promote, stale_by_profile  # noqa: E402

PROFILE_ADD = re.compile(r"kb profile add (\S+) (\S+?)=")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()
        self.t = turn.start(self.V, None, "")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class One_ProfileCommandsUseRealColumns(unittest.TestCase):
    def test_every_profile_add_in_notes_and_docs(self):
        columns = {name: set(cols) for name, cols, _key in profile.SECTION_SPECS}
        texts = [(ROOT / "skills" / "lint" / rel).read_text(encoding="utf-8") for rel in ("SKILL.md", "references/report.md")]
        texts.append(json.dumps(rulings_promote.__dict__.get("NOTE", ""), ensure_ascii=False))
        texts.append(Path(rulings_promote.__file__).read_text(encoding="utf-8"))
        hits = [m for t in texts for m in PROFILE_ADD.finditer(t)]
        self.assertTrue(hits)
        for m in hits:
            section, column = m.group(1), m.group(2)
            self.assertIn(column, columns.get(section, set()), m.group(0))


class Two_InferredAgendaConfirm(Base):
    def put(self, source):
        item = {"id": "a-11112222", "kind": "promise", "date": "2030-12-05", "text": "給報價", "entities": ["信義王"],
                "status": "open", "source": source, "created_turn": "t", "history": []}
        (self.V / agenda.AGENDA_POSIX).write_text(json.dumps({"schema_version": 1, "items": [item]}, ensure_ascii=False),
                                                  encoding="utf-8")

    def test_edit_without_fields_confirms_inferred(self):
        self.put("inferred")
        r = run_kb("agenda", "edit", "a-11112222", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "記成確認了：給報價"), r.stderr)
        it = agenda.get(self.V, "a-11112222")
        self.assertEqual(it["source"], "confirmed")
        self.assertTrue(it["history"])
        r = run_kb("agenda", "edit", "a-11112222", "--date", "2030-12-05", cwd=self.V)
        self.assertEqual(r.stdout.strip(), "沒有要改的：給報價")

    def test_same_value_also_confirms_inferred(self):
        self.put("inferred")
        r = run_kb("agenda", "edit", "a-11112222", "--date", "2030-12-05", cwd=self.V)
        self.assertEqual(r.stdout.strip(), "記成確認了：給報價")

    def test_not_inferred_unchanged(self):
        self.put("interview")
        r = run_kb("agenda", "edit", "a-11112222", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "沒有給要改的欄位"))
        r = run_kb("agenda", "edit", "a-11112222", "--date", "2030-12-05", cwd=self.V)
        self.assertEqual(r.stdout.strip(), "沒有要改的：給報價")

    def test_note_says_edit_without_fields(self):
        from kb.lint.checks import inferred
        self.assertIn("kb agenda edit <編號>（不帶欄位", Path(inferred.__file__).read_text(encoding="utf-8"))


class Three_SetAsideUnreadableNotUnsorted(Base):
    def test_unreadable_set_aside_not_counted(self):
        fid = _cards.entry_of(self.V, E.MEMO)["id"]
        before = cards.unsorted(self.V)
        pid = pending.add(self.V, "unreadable", [fid], "「Big5備忘.txt」讀不到", "編碼", self.t)
        pending.set_aside(self.V, pid, "lint", self.t)
        self.assertEqual(cards.unsorted(self.V), before - 1)


class Four_OnlyDoableCountsAsTidying(unittest.TestCase):
    def test_report_and_cli(self):
        ingest = {"unsorted": 0, "unlinked": 0, "synthesis_stale": 0, "missing": 0, "duplicates": 0, "unreadable": 2,
                  "overdue": 0, "conflicts": 2}
        self.assertEqual(report._suggest({}, ingest), [])
        self.assertEqual(report._ingest_text(ingest), "")
        self.assertIn("讀不到 2 份", report._decide_text(ingest))
        got = {"summary": "大致正常。", "done": [], "decide": 4, "most_urgent": None, "ingest": ingest}
        self.assertFalse([ln for ln in lint_cli._lines(got) if ln.startswith("整理還有")])
        ingest["unsorted"] = 3
        self.assertEqual(report._suggest({}, ingest), ["整理還有沒做完的，說「整理」就好"])
        self.assertEqual(report._ingest_text(ingest), "待整理 3 份")


class Five_JournalWording(Base):
    def test_background_lint_label(self):
        journal.record_program(self.V, "健檢：補完 1 句沒記完的工作日誌", [], "lint --background")
        out = run_kb("journal", "recent", cwd=self.V).stdout
        self.assertIn("每週健檢（自動）", out)
        self.assertNotIn("kb lint --background", out)
        md = journal.md_path(self.V, journal.months(self.V)[-1]).read_text(encoding="utf-8")
        self.assertIn("每週健檢（自動）", md)

    def test_stuck_text(self):
        from kb.lint.checks import system_dir
        self.assertIn("補完 {n} 句沒記完的工作日誌", Path(system_dir.__file__).read_text(encoding="utf-8"))


class Six_RedoOnlyActiveCards(Base):
    def test_excluded_card_not_candidate(self):
        a = L.write_card(self.V, E.QUOTE, "信義王報價")
        b = L.write_card(self.V, E.ESTIMATE, "內湖李估價")
        for cid in (a, b):
            p = self.V / cards.card_of(self.V, cid)["path"]
            p.write_text(re.sub(r"^製卡日期: .*$", "製卡日期: 2026-10-01", p.read_text(encoding="utf-8"), count=1, flags=re.M),
                         encoding="utf-8")
        prof = json.loads((self.V / profile.PROFILE_POSIX).read_text(encoding="utf-8"))
        for row in prof["card_types"]:
            if row["name"] == "報價":
                row["date"] = "2026-10-20"
        (self.V / profile.PROFILE_POSIX).write_text(json.dumps(prof, ensure_ascii=False), encoding="utf-8")
        p = self.V / inventory.INVENTORY_POSIX
        inv = json.loads(p.read_text(encoding="utf-8"))
        next(e for e in inv["entries"] if e["id"] == b)["status"] = "excluded"
        p.write_text(json.dumps(inv, ensure_ascii=False), encoding="utf-8")
        (dec,) = [f for f in stale_by_profile.run(L.ctx(self.V)) if f["kind"] == "decide"]
        self.assertEqual(dec["data"]["ids"], [a])



class T39ChangedInPlainWords(Base):
    """發行前 T-39：工作日誌「改了」不出現英文：健檢、問法的新檔都有白話名字；背景健檢那段也是。"""

    def test_new_state_files_have_names(self):
        rels = (".system/lint.json", ".system/set_aside.json", ".system/renders.json", ".system/statements-archive.json",
                ".system/findings-archive.json", ".system/handedits/20261025-120000-待處理.md", "系統/健檢報告/2026-10.md")
        text = journal.changed_text([{"path": r, "action": "modify"} for r in rels])
        self.assertIsNone(re.search(r"[A-Za-z]", text), text)
        for word in ("健檢紀錄", "先放著的清單", "手改比對紀錄", "口述封存", "推算封存", "你手改的那份", "健檢報告"):
            self.assertIn(word, text)

    def test_background_segment(self):
        from unittest import mock
        from kb.lint import checks, runner
        with mock.patch.object(checks, "CHECKS", []):
            runner.run(self.V, background=True)
        out = run_kb("journal", "recent", "--changed", cwd=self.V).stdout
        changed = [ln for ln in out.splitlines() if "改了：" in ln]
        self.assertTrue(changed, out)
        self.assertIsNone(re.search(r"[A-Za-z]", "".join(changed)), changed)


if __name__ == "__main__":
    unittest.main()
