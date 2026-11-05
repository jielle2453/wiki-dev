"""多人共用 2：兩台模擬（老闆 boss-pc、小王 wang-laptop）的日程、偏好、口述出處、可以讀、來源位置、開場問名字。
兩台用 platform.node 換機器名模擬（env.json 照機器名分）；kb 子行程用真的機器名。"""
import json
import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests.test_people import Base
from kb._lib import agenda, env, profile, rulings, statements, turn  # noqa: E402
from kb._lib import sources as sources_lib  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import _checks  # noqa: E402
import session  # noqa: E402


class TwoMachines(Base):
    def setUp(self):
        super().setUp()
        self.multi(3)
        for m, name in (("boss-pc", "老闆"), ("wang-laptop", "小王")):
            with self.as_machine(m):
                env.set_person(self.V, name)
                env.set_vault_path(self.V, os.path.realpath(self.V).replace("\\", "/"))  # 不是「新電腦第一次開」
        self.t = turn.start(self.V, None, "")["turn"]

    def put_prefs(self, prefs):
        data = profile.load(self.V)
        (self.V / ".system" / "profile.json").write_text(json.dumps(dict(data, preferences=prefs), ensure_ascii=False),
                                                         encoding="utf-8")

    def test_line_who(self):
        with self.as_machine("new-pc"):
            line = _checks.line_who(self.V)
            self.assertIn("kb who set", line)
            self.assertIn("預設", line)
        with self.as_machine("boss-pc"):
            self.assertIsNone(_checks.line_who(self.V))

    def test_line_who_single_silent(self):
        self.kb("profile", "set", "people", "1")
        with self.as_machine("new-pc"):
            self.assertIsNone(_checks.line_who(self.V))

    def test_agenda_whose(self):
        with self.as_machine("boss-pc"):
            agenda.add(self.V, "meeting", "2099-01-02", "週五全員開會", [], self.t)
            agenda.add(self.V, "reminder", "2099-01-03", "提醒我回電", [], self.t, whose="老闆")

        def texts(machine):
            with self.as_machine(machine):
                return [i["text"] for i in agenda.visible(self.V, agenda.load(self.V)["items"])]
        self.assertEqual(texts("boss-pc"), ["週五全員開會", "提醒我回電"])
        self.assertEqual(texts("wang-laptop"), ["週五全員開會"])
        with self.as_machine("wang-laptop"):
            data = agenda.load(self.V)
            self.assertNotIn("提醒我回電", agenda.render_text(self.V, data))
            self.assertIn("週五全員開會", agenda.render_text(self.V, data))
            self.assertEqual(sum(agenda.counts(self.V, data, today="2099-01-01").values()), 1)
            self.assertEqual(len(agenda.export_payload(self.V, data)["items"]), 1)
        with self.as_machine("boss-pc"):
            self.assertEqual(sum(agenda.counts(self.V, agenda.load(self.V), today="2099-01-01").values()), 2)

    def test_agenda_cli_list_all(self):
        r = self.kb("agenda", "add", "--kind", "提醒", "--date", "2099-01-03", "--text", "寄樣品", "--whose", "不是這台的人")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # 真機器沒有記名字：多人時 me 是 None → 不篩（還沒問名字前先全看得到）；用 boss-pc 的名字在程式內驗篩
        with self.as_machine("boss-pc"):
            self.assertEqual(agenda.visible(self.V, agenda.load(self.V)["items"]), [])
        self.assertEqual(len(json.loads(self.kb("agenda", "list", "--all", "--json").stdout)["items"]), 1)

    def test_agenda_edit_whose_and_origin_team(self):
        with self.as_machine("boss-pc"):
            it, _ = agenda.add(self.V, "reminder", "2099-01-03", "寄樣品", [], self.t, whose="小王")
            self.assertEqual(it["whose"], ["小王"])
            agenda.edit(self.V, it["id"], self.t, whose="全隊")
            self.assertNotIn("whose", agenda.get(self.V, it["id"]))

    def test_preferences_block(self):
        self.put_prefs([
            {"text": "回答短一點", "use": "全部", "source": "corrected", "date": "2026-11-01", "whose": "小王"},
            {"text": "講金額都用萬元", "use": "全部", "source": "corrected", "date": "2026-11-01", "whose": "team"},
            {"text": "老闆的習慣", "use": "全部", "source": "corrected", "date": "2026-11-01", "whose": "老闆"}])
        with self.as_machine("boss-pc"):
            block = session.preferences_block(self.V)
        self.assertNotIn("回答短一點", block)
        self.assertIn("講金額都用萬元", block)
        self.assertIn("老闆的習慣", block)
        with self.as_machine("wang-laptop"):
            block = session.preferences_block(self.V)
        self.assertIn("回答短一點", block)
        self.assertNotIn("老闆的習慣", block)

    def test_preferences_cap_cuts_oldest_team_first(self):
        self.put_prefs([{"text": f"全隊{i}", "use": "全部", "source": "corrected", "date": f"2026-10-0{i + 1}",
                         "whose": "team"} for i in range(3)]
                       + [{"text": "我的", "use": "全部", "source": "corrected", "date": "2026-09-01", "whose": "老闆"}])
        from kb._lib import config
        real = config.get
        with mock.patch.object(config, "get", side_effect=lambda v, k, *a: 3 if k == "preference_max" else real(v, k, *a)):
            with self.as_machine("boss-pc"):
                block = session.preferences_block(self.V)
        self.assertNotIn("全隊0", block)
        self.assertIn("全隊1", block)
        self.assertIn("我的", block)

    def test_statement_who_and_source_text(self):
        from tests import _entities as E
        from kb._lib import entities
        E.install(self.V)
        name = next(e["name"] for e in entities.load(self.V)["entities"] if e.get("status") == "active")
        with self.as_machine("wang-laptop"):
            it, _ = statements.add(self.V, "交期是十二月", [name], self.t)
        self.assertEqual(it["who"], "小王")
        self.assertTrue(statements.said_by(it, True).startswith("小王 "))
        self.assertTrue(statements.said_by(it, True).endswith("說的"))
        old = {"date": "2026-11-01", "text": "舊的"}
        self.assertEqual(statements.said_by(old, True), "11/01 說的")  # 升級前的只寫日期
        self.assertEqual(statements.said_by(old, False), "你 11/01 說的")
        from kb import lookup_cli  # #43：文字輸出也帶誰說的（AI 跑的是不帶 --json 的）
        from kb._lib import lookup
        line = next(x for x in lookup_cli._lines(lookup.lookup(self.V, name)) if "交期是十二月" in x)
        self.assertTrue(line.endswith(f"（{statements.said_by(it, True)}）"), line)
        from kb._lib import people
        with mock.patch.object(people, "multi", lambda v: False):  # 單人照舊不帶
            line = next(x for x in lookup_cli._lines(lookup.lookup(self.V, name)) if "交期是十二月" in x)
        self.assertNotIn("說的", line)
        from tests.test_scripts_inventory_cli import run_kb
        with self.as_machine("wang-laptop"):
            out = run_kb("statement", "list", cwd=self.V).stdout
        self.assertIn(f"，{statements.said_by(it, True)}）", out)

    def test_readable_ids_per_person(self):
        old = rulings.load(self.V)
        base = {"kind": "credential_read", "entities": [], "cards": [], "text": "x", "date": "2026-11-01", "turn": "t",
                "status": "active", "revoked": None}
        old["rulings"] = [dict(base, id="r-1", files=["f-boss"], person="老闆"),
                          dict(base, id="r-2", files=["f-old"])]  # 升級前沒有 person
        (self.V / ".system" / "rulings.json").write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
        with self.as_machine("boss-pc"):
            self.assertEqual(rulings.readable_ids(self.V), {"f-boss", "f-old"})
        with self.as_machine("wang-laptop"):
            self.assertEqual(rulings.readable_ids(self.V), {"f-old"})

    def test_folders_locate_and_shared_default(self):
        other = Path(self.tmp) / "雲端夾"
        other.mkdir()
        (other / "a.txt").write_text("x", encoding="utf-8")
        r = self.kb("folders", "add", str(other), "--alias", "共享Y")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        entry = next(s for s in sources_lib.load_raw(self.V)["sources"] if s["alias"] == "共享Y")
        self.assertTrue(entry.get("shared"))  # 多人沒給 --shared 也是 shared
        mine = Path(self.tmp) / "小王的雲端夾"
        mine.mkdir()
        before = (self.V / ".system" / "sources.json").read_bytes()
        r = self.kb("folders", "locate", "共享Y", str(mine))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.V / ".system" / "sources.json").read_bytes(), before)  # 共用的沒動
        root = next(s["root"] for s in sources_lib.load(self.V).entries if s["alias"] == "共享Y")
        self.assertTrue(root.endswith("小王的雲端夾"), root)
        self.assertEqual(self.kb("folders", "locate", "共享Y", str(Path(self.tmp) / "沒有這個夾")).returncode, 3)
        self.assertEqual(self.kb("folders", "locate", "共享Y", "--clear").returncode, 0)
        root = next(s["root"] for s in sources_lib.load(self.V).entries if s["alias"] == "共享Y")
        self.assertFalse(root.endswith("小王的雲端夾"), root)

    def test_folders_single_not_shared(self):
        self.kb("profile", "set", "people", "1")
        other = Path(self.tmp) / "單人夾"
        other.mkdir()
        self.kb("folders", "add", str(other), "--alias", "單人Y")
        entry = next(s for s in sources_lib.load_raw(self.V)["sources"] if s["alias"] == "單人Y")
        self.assertFalse(entry.get("shared"))

    def test_missing_source_line_team(self):
        other = Path(self.tmp) / "會消失的夾"
        other.mkdir()
        (other / "a.txt").write_text("x", encoding="utf-8")
        self.kb("folders", "add", str(other), "--alias", "會消失")
        shutil.rmtree(other)
        with self.as_machine("wang-laptop"):
            line = _checks.line_missing_sources(self.V)
            self.assertIsNotNone(line)
            self.assertIn("kb folders locate 會消失 <路徑>", line)
            self.assertIsNone(_checks.line_missing_sources(self.V))  # 只報一次

    def test_single_agenda_not_filtered(self):
        self.kb("profile", "set", "people", "1")
        with self.as_machine("boss-pc"):
            agenda.add(self.V, "reminder", "2099-01-03", "寄樣品", [], self.t, whose="小王")
            self.assertEqual(len(agenda.visible(self.V, agenda.load(self.V)["items"])), 1)


class UndoOthers(TwoMachines):
    """第 11 點：老闆同一句記日程又記口述，小王改了那筆日期；老闆退回那一句。"""

    def cli(self, *argv):
        import contextlib
        import io
        from kb import cli
        saved = (turn.SESSION, turn.OVERRIDE, turn.VIA)  # cli.main 會設這幾個全域：測完還回去，不汙染同一個行程後面的測試
        self.addCleanup(lambda: (setattr(turn, "SESSION", saved[0]), setattr(turn, "OVERRIDE", saved[1]),
                                 setattr(turn, "VIA", saved[2])))
        buf = io.StringIO()
        cwd = os.getcwd()
        os.chdir(self.V)
        try:
            with contextlib.redirect_stdout(buf):
                code = cli.main(list(argv))
        finally:
            os.chdir(cwd)
        return code, buf.getvalue()

    def test_undo_item_changed_by_other(self):
        from tests import _entities as E
        from kb._lib import entities
        E.install(self.V)
        name = next(e["name"] for e in entities.load(self.V)["entities"] if e.get("status") == "active")
        with self.as_machine("boss-pc"):
            tid = turn.start(self.V, "sid-boss", "記日程和口述")["turn"]
            it, _ = agenda.add(self.V, "meeting", "2099-01-02", "跟廠商開會", [], tid)
            statements.add(self.V, "交期是十二月", [name], tid)
        with self.as_machine("wang-laptop"):
            t2 = turn.start(self.V, "sid-wang", "改日期")["turn"]
            agenda.edit(self.V, it["id"], t2, date="2099-01-09")
        with self.as_machine("boss-pc"):
            code, out = self.cli("--session", "sid-boss", "versions", "undo", tid, "--json")
            got = json.loads(out)
            self.assertEqual(len(got["conflict"]), 1, out)
            c = got["conflict"][0]
            self.assertEqual(c["later"][-1]["side"], "other")
            self.assertEqual(c["later"][-1]["who"], "小王")
            self.assertEqual(c["now"]["date"], "2099-01-09")
            self.assertTrue(got["done"], out)  # 口述那項照改回
            code, text = self.cli("--session", "sid-boss", "versions", "undo", tid)
            self.assertIn("小王", text)
            self.assertIn("2099-01-09", text)
            code, out = self.cli("--session", "sid-boss", "versions", "undo", c["item"], "--yes", "--json")
            self.assertEqual(json.loads(out)["done"], [c["item"]], out)
            cur = agenda.get(self.V, it["id"])
            self.assertEqual(cur["status"], "cancelled")  # 那筆收回
            self.assertEqual(cur["date"], "2099-01-09")  # 小王改的日期那欄不動


class Colleague(TwoMachines):
    """第 10 點：多人時共用夾裡兩句話之間被刪的檔，說「可能是同事動的」，不說「你」、不掛人名。"""

    def setup_shared(self):
        other = Path(self.tmp) / "共用夾"
        other.mkdir()
        (other / "a.txt").write_text("x", encoding="utf-8")
        (other / "b.txt").write_text("y", encoding="utf-8")
        r = self.kb("folders", "add", str(other), "--alias", "共用")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.kb("inventory", "scan")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return other

    def test_shared_missing_line_says_colleague(self):
        other = self.setup_shared()
        (other / "a.txt").unlink()
        _checks.START = __import__("time").monotonic()  # 每句開頭的時限從這裡算
        with self.as_machine("wang-laptop"):
            lines, _told = _checks.change_lines(self.V, [], None)
        text = "\n".join(lines)
        self.assertIn("可能是同事動的", text)
        self.assertNotIn("你", text)
        self.assertNotIn("小王", text)

    def test_single_unshared_no_colleague(self):
        self.kb("profile", "set", "people", "1")
        other = self.setup_shared()
        (other / "a.txt").unlink()
        _checks.START = __import__("time").monotonic()
        with self.as_machine("boss-pc"):
            lines, _told = _checks.change_lines(self.V, [], None)
        self.assertTrue(lines)
        self.assertNotIn("可能是同事動的", "\n".join(lines))

    def test_journal_action_line(self):
        from kb._lib import journal
        a = {"item": "t#1", "op": "missing", "kind": "file", "from": "file://共用/a.txt", "to": None, "by": "outside",
             "colleague": True}
        self.assertIn("可能是同事動的", journal._action_line(a))
        self.assertNotIn("可能是同事動的", journal._action_line(dict(a, colleague=False)))


if __name__ == "__main__":
    unittest.main()
