"""--check（Obsidian 首頁，#22，D-256）：entity progress／rename／merge 與 agenda cancel 先算後果、什麼都不寫。驗收準則 10。"""
import hashlib
import json
import shutil
import unittest

from tests import _entities as E
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import agenda, turn  # noqa: E402


def snapshot(V):
    """知識庫每個檔的 sha256（不含鎖與錯誤 log）。"""
    got = {}
    for p in sorted(V.rglob("*")):
        if p.is_file() and not p.name.endswith(".lock") and p.name != "hook-errors.log":
            got[p.relative_to(V).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return got


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        self.t = turn.start(self.V, None, "")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def check(self, *args, code=0):
        before = snapshot(self.V)
        r = run_kb(*args, "--check", "--json", cwd=self.V)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        self.assertEqual(snapshot(self.V), before, "什麼都沒寫")
        return json.loads(r.stdout)


class Progress(Base):
    def test_close_names_periods_and_open_items(self):
        agenda.add(self.V, "期間", "2030-11-30", "施工", ["信義王"], self.t, start="2030-09-01")
        agenda.add(self.V, "到期", "2030-10-01", "付款", ["信義王"], self.t)
        agenda.add(self.V, "提醒", "2030-10-02", "訂窗簾", ["信義王"], self.t)
        got = self.check("entity", "progress", "信義王", "結案")
        self.assertEqual(got, {"effects": ["信義王記成結案：『施工』這段期間會在今天結束；還開著的 2 件日程照舊"], "refuse": None})

    def test_close_with_nothing_open(self):
        self.assertEqual(self.check("entity", "progress", "信義王", "結案")["effects"], ["信義王記成結案"])

    def test_back_to_ongoing_from_closed_and_paused(self):
        run_kb("entity", "progress", "信義王", "結案", cwd=self.V)
        self.assertIn("改回進行中", self.check("entity", "progress", "信義王", "進行中")["effects"][0])
        self.assertIn("本來就是結案", self.check("entity", "progress", "信義王", "結案")["effects"][0])
        self.assertIn("擱置", self.check("entity", "progress", "信義王", "擱置")["effects"][0])

    def test_refusals_exit_3_and_say_why(self):
        got = self.check("entity", "progress", "林小姐室內設計", "結案", code=3)
        self.assertEqual((got["effects"], "不是「事」類" in got["refuse"]), ([], True))
        got = self.check("entity", "progress", "沒有這個人", "結案", code=3)
        self.assertTrue(got["refuse"])

    def test_bad_state_word(self):
        r = run_kb("entity", "progress", "信義王", "亂寫", "--check", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "狀態要是 進行中、結案、擱置 之一"))

    def test_human_output_is_one_sentence(self):
        r = run_kb("entity", "progress", "信義王", "結案", "--check", cwd=self.V)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "信義王記成結案"))


class Rename(Base):
    def test_effects_count_cards_and_folder(self):
        got = self.check("entity", "rename", "信義王", "--to", "信義王新家")
        (line,) = got["effects"]
        self.assertTrue(line.startswith("信義王改名叫信義王新家："), line)
        self.assertIn("夾、綜合卡", line)
        self.assertTrue(line.endswith("舊名記成別名"), line)

    def test_name_taken_is_refused(self):
        got = self.check("entity", "rename", "信義王", "--to", "大安陳", code=3)
        self.assertTrue(got["refuse"])
        self.assertEqual(got["effects"], [])

    def test_bad_characters_refused(self):
        self.check("entity", "rename", "信義王", "--to", "含$的名字", code=3)

    def test_unknown_type_refused(self):
        self.check("entity", "rename", "信義王", "--to", "信義王", "--type", "不存在的型別", code=3)


class Merge(Base):
    def test_effects(self):
        E.put_entities(self.V, entities_with_extra(self.V))
        got = self.check("entity", "merge", "舊信義", "--into", "信義王")
        (line,) = got["effects"]
        self.assertTrue(line.startswith("舊信義併進信義王："), line)
        self.assertIn("舊信義記成信義王的別名", line)
        self.assertIn("合併之後要分開只能退回", line)

    def test_same_entity_and_type_mismatch_refused(self):
        self.check("entity", "merge", "信義王", "--into", "信義王", code=3)
        got = self.check("entity", "merge", "林小姐室內設計", "--into", "信義王", code=3)
        self.assertTrue(got["refuse"])

    def test_different_type_refused(self):
        from kb._lib import entities
        E.put_entities(self.V, entities.load(self.V)["entities"] + [E.entity("e-aaaa0002", "王先生", type_="業主")])
        got = self.check("entity", "merge", "王先生", "--into", "信義王", code=3)
        self.assertIn("型別不同", got["refuse"])


def entities_with_extra(V):
    from kb._lib import entities
    data = entities.load(V)["entities"]
    data.append(E.entity("e-aaaa0001", "舊信義"))
    return data


class AgendaCancel(Base):
    def test_period_and_plain(self):
        p = agenda.add(self.V, "期間", "2030-11-30", "施工", ["信義王"], self.t, start="2030-09-01")[0]
        d = agenda.add(self.V, "到期", "2030-10-01", "付款", ["信義王"], self.t)[0]
        got = self.check("agenda", "cancel", p["id"])
        self.assertEqual(got["effects"], ["取消期間『施工』：時間軸上整段拿掉，同一件事還開著的 1 件日程照舊；之後可以重開"])
        got = self.check("agenda", "cancel", d["id"])
        self.assertEqual(got["effects"], ["取消『付款』（10/1）；之後可以重開"])

    def test_unknown_id(self):
        got = self.check("agenda", "cancel", "a-00000000", code=3)
        self.assertEqual(got["refuse"], "日程沒有 a-00000000")

    def test_without_check_still_cancels(self):
        d = agenda.add(self.V, "到期", "2030-10-01", "付款", ["信義王"], self.t)[0]
        r = run_kb("agenda", "cancel", d["id"], cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(agenda.get(self.V, d["id"])["status"], "cancelled")


class NoTurnOpened(Base):
    def test_via_obsidian_check_opens_no_turn(self):
        vdir = self.V / ".system" / "versions"
        before = sorted(p.name for p in vdir.iterdir()) if vdir.is_dir() else []
        r = run_kb("--via", "obsidian", "entity", "progress", "信義王", "結案", "--check", "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(before, sorted(p.name for p in vdir.iterdir()) if vdir.is_dir() else [])


if __name__ == "__main__":
    unittest.main()
