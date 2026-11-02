"""versions revert 讀 moves.jsonl（manage 第二版第 3、4 點，D-175）：退回搬回、卡與清冊跟回來；原位有同名整個不退；
moves.jsonl 被改壞（絕對路徑、..、沒登記的別名、排除裡的路徑）各拒絕、什麼都沒動；trash 那句；purged 那句；versions list 的白話。"""
import contextlib
import io
import json
import os
import re
from pathlib import Path
from unittest import mock

from tests import _cards
from tests.test_lib_source_edit import ESTIMATE, Base, entry, inv
from kb import versions
from kb._lib import source_edit as se
from kb._lib import cards, inventory, turn  # noqa: E402
from kb._lib import sources as sources_lib  # noqa: E402

ID_LIKE = re.compile(r"\b[aefsrcp]-[0-9a-f]{8}\b")


def revert(V):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = versions._revert(V, None, False, False)
    return code, out.getvalue()


def listing(V):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        versions._list(V, 5, False)
    return out.getvalue()


class RecordMove(Base):
    def test_record_and_read_back(self):
        turn.record_move(self.V, self.t, "move", "file", "file://a/x.txt", "file://b/x.txt")
        turn.record_move(self.V, self.t, "trash", "file", "file://a/y.txt")
        with open(Path(self.V) / ".system/versions" / self.t / "moves.jsonl", "a", encoding="utf-8") as f:
            f.write("壞行\n")
        rows = turn.moves(self.V, self.t)
        self.assertEqual([(r["op"], r["kind"], r["from"], r["to"]) for r in rows],
                         [("move", "file", "file://a/x.txt", "file://b/x.txt"), ("trash", "file", "file://a/y.txt", None)])
        with self.assertRaises(ValueError):
            turn.record_move(self.V, self.t, "copy", "file", "file://a/x.txt")


class RevertMoves(Base):
    def test_file_move_back_and_cards_follow(self):
        before_card = (Path(self.V) / self.card_rel).read_bytes()
        self.move(self.fid, str(self.raw / "客戶案件" / "大安陳"))
        code, out = revert(self.V)
        self.assertEqual(code, 0, out)
        self.assertTrue((self.raw / ESTIMATE).is_file())
        self.assertFalse((self.raw / "客戶案件" / "大安陳" / "估價單.pdf").exists())
        self.assertEqual(entry(self.V, self.fid)["locations"][0]["uri"], "file://" + ESTIMATE)
        self.assertEqual((Path(self.V) / self.card_rel).read_bytes(), before_card)
        self.assertFalse(list((Path(self.V) / "檔案索引/客戶案件/大安陳").glob("*.md")))
        self.assertIn("估價單.pdf：從 大安陳 搬到 內湖李", out)

    def test_folder_move_back_restores_exclude(self):
        lee = self.raw / "客戶案件" / "內湖李"
        (lee / "私人").mkdir()
        (lee / "私人" / "日記.txt").write_text("秘密", encoding="utf-8")
        p = Path(self.V) / ".system/sources.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["sources"][0]["excludes"].append({"spec": "內湖李/私人", "kind": "hidden", "reason": "", "added": "2026-10-22"})
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        before = p.read_text(encoding="utf-8")
        self.move(str(lee), str(self.raw / "報價與合約"))
        code, out = revert(self.V)
        self.assertEqual(code, 0, out)
        self.assertTrue((lee / "私人" / "日記.txt").is_file())
        self.assertEqual(json.loads(p.read_text(encoding="utf-8")), json.loads(before))
        self.assertEqual(entry(self.V, self.fid)["locations"][0]["uri"], "file://" + ESTIMATE)

    def test_ai_output_move_back(self):
        t0 = turn.start(self.V, None, "")["turn"]
        turn.backup(self.V, "AI 產出/報告.docx", t0)
        (Path(self.V) / "AI 產出" / "報告.docx").write_bytes(b"r")
        from kb._lib import inventory
        e = inventory.register_output(self.V, "AI 產出/報告.docx", t0)
        dest = Path(self.V) / "案子" / "內湖李"
        dest.mkdir(parents=True, exist_ok=True)
        self.t = turn.start(self.V, None, "")["turn"]
        self.move(str(Path(self.V) / "AI 產出" / "報告.docx"), str(dest))
        code, out = revert(self.V)
        self.assertEqual(code, 0, out)
        self.assertTrue((Path(self.V) / "AI 產出" / "報告.docx").is_file())
        self.assertEqual(entry(self.V, e["id"])["locations"][0]["uri"], "file://AI 產出/報告.docx")

    def test_same_name_at_origin_refuses_whole(self):
        self.move(self.fid, str(self.raw / "客戶案件" / "大安陳"))
        (self.raw / ESTIMATE).write_bytes(b"new one")
        before = self.snapshot()
        code, out = revert(self.V)
        self.assertEqual(code, 3)
        self.assertEqual(out.strip(), "退不回去：「內湖李」裡已經有「估價單.pdf」了；先把那份改名或搬走再說退回，什麼都沒動")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((Path(self.V) / ".system/versions" / self.t / "reverted.json").exists())

    def tamper(self, uri):
        path = Path(self.V) / ".system/versions" / self.t / "moves.jsonl"
        row = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        row["from"] = uri
        path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    def test_tampered_records_refused(self):
        self.move(self.fid, str(self.raw / "客戶案件" / "大安陳"))
        excluded = self.raw / "公司行政" / "舊檔"
        p = Path(self.V) / ".system/sources.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["sources"][2]["excludes"].append({"spec": "舊檔", "kind": "unused", "reason": "", "added": "2026-10-22"})
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        cases = {
            "file://客戶案件/C:/Windows/x.pdf": "退不回去：回合紀錄的搬動路徑不對（file://客戶案件/C:/Windows/x.pdf），什麼都沒動；請服務人員看",
            "file://客戶案件/../../x.pdf": "退不回去：回合紀錄的搬動路徑不對（file://客戶案件/../../x.pdf），什麼都沒動；請服務人員看",
            "file://沒有這個/x.pdf": "退不回去：「沒有這個」現在沒有登記；要退回得先把它加回來，什麼都沒動",
            "file://公司行政/舊檔/x.pdf": "退不回去：「x.pdf」在設成不讀的夾裡；要退回得先取消不讀，什麼都沒動",
            "file://知識庫/.system/x.pdf": "退不回去：回合紀錄的搬動路徑不對（file://知識庫/.system/x.pdf），什麼都沒動；請服務人員看",
            "/abs/x.pdf": "退不回去：回合紀錄的搬動路徑不對（/abs/x.pdf），什麼都沒動；請服務人員看",
            "file://客戶案件/（已排除）": "退不回去：那一回合搬過的檔在清掉的不讀夾裡，紀錄已經清掉，什麼都沒動",
            # security-review：段中間的磁碟代號會變成另一顆磁碟的相對路徑（D:Secret/x），不能被當成在根底下
            "file://知識庫/a/D:/Secret/x.pdf": "退不回去：回合紀錄的搬動路徑不對（file://知識庫/a/D:/Secret/x.pdf），什麼都沒動；請服務人員看",
            "file://客戶案件/a/D:/Secret/x.pdf": "退不回去：回合紀錄的搬動路徑不對（file://客戶案件/a/D:/Secret/x.pdf），什麼都沒動；請服務人員看",
            "file://知識庫/系統./x/y.pdf": "退不回去：回合紀錄的搬動路徑不對（file://知識庫/系統./x/y.pdf），什麼都沒動；請服務人員看",
        }
        self.assertTrue(excluded.is_dir())
        here = os.getcwd()
        os.chdir(self.V)  # 真的 kb 從知識庫裡跑：磁碟相對路徑會接到 cwd（security-review 那條要在這個條件下才重現）
        self.addCleanup(os.chdir, here)
        for uri, text in cases.items():
            with self.subTest(uri=uri):
                self.tamper(uri)
                before = self.snapshot()
                code, out = revert(self.V)
                self.assertEqual(code, 3)
                self.assertEqual(out.strip(), text)
                self.assertEqual(self.snapshot(), before)

    def test_trash_revert_brings_card_and_inventory_back(self):
        with mock.patch.object(se, "recycle_room", return_value=(0, 10 ** 9)):
            p = se.plan_trash(self.V, self.sources, self.fid, self.V)
        with mock.patch.object(se, "shell_trash", side_effect=os.remove):
            se.do_trash(self.V, p, self.t)
        code, out = revert(self.V)
        self.assertEqual(code, 0, out)
        self.assertIn("估價單.pdf 在資源回收筒，要從那裡拿回來", out)
        self.assertTrue((Path(self.V) / self.card_rel).is_file())
        self.assertNotEqual(entry(self.V, self.fid)["status"], "deleted")

    def test_purged_row_skipped_with_line(self):
        t = turn.start(self.V, None, "")["turn"]
        turn.backup(self.V, self.card_rel, t, action="delete")
        os.remove(Path(self.V) / self.card_rel)
        m = Path(self.V) / ".system/versions" / t / "manifest.jsonl"
        row = json.loads(m.read_text(encoding="utf-8").splitlines()[0])
        row.update(action="purged", path="（已排除）")
        m.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        code, out = revert(self.V)
        self.assertEqual(code, 0, out)
        self.assertIn("那一版因為不讀的夾清掉了，退不回", out)
        self.assertFalse((Path(self.V) / self.card_rel).exists())


class ListMoves(Base):
    def test_list_shows_plain_lines_without_ids(self):
        self.move(self.fid, str(self.raw / "客戶案件" / "大安陳"))
        out = listing(self.V)
        self.assertIn("    估價單.pdf：從 內湖李 搬到 大安陳", out)
        self.assertIsNone(ID_LIKE.search(out), out)
        data = json.loads(self._json())
        self.assertEqual(data[0]["moves"][0]["from"], "file://" + ESTIMATE)

    def _json(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            versions._list(self.V, 5, True)
        return out.getvalue()


class TrashBackupRevert(Base):
    """放寬甲 待你決定 1：回收筒進不了先留進回合備份；退回把檔放回原位，隨身碟沒插著先說一句、什麼都不動。"""

    def trash_via_backup(self):
        src = self.raw / ESTIMATE
        body = src.read_bytes()
        with mock.patch.object(se, "shell_trash", side_effect=se.BinUnavailable("x")), \
                mock.patch.object(se, "recycle_room", return_value=(0, 10 ** 9)):
            p = se.plan_trash(self.V, self.sources, self.fid, self.V)
            got = se.do_trash(self.V, p, self.t)
        self.assertEqual(got["kept"], "backup")
        self.assertFalse(src.exists())
        return src, body

    def test_revert_puts_file_back(self):
        src, body = self.trash_via_backup()
        code, _out = revert(self.V)
        self.assertEqual(code, 0, _out)
        self.assertEqual(src.read_bytes(), body)

    def test_drive_gone_says_plug_in_and_moves_nothing(self):
        src, _body = self.trash_via_backup()
        root = self.raw / "客戶案件"
        root.rename(self.raw / "客戶案件_拔掉了")  # 模擬來源所在的磁碟沒接著
        try:
            code, out = revert(self.V)
        finally:
            (self.raw / "客戶案件_拔掉了").rename(root)
        self.assertEqual(code, 3, out)
        self.assertEqual(out.strip(), "原本放「估價單.pdf」的「客戶案件」現在找不到：先請使用者把隨身碟或磁碟接上再改回。")
        self.assertFalse(src.exists())


class OutsideMove(Base):
    """放寬甲（spec 一.5、資料格式「清冊」）：搬到沒登記的地方（桌面）：清冊那份記成可攜 spec file://~/Desktop/…、狀態 outside；
    不掃描、卡留著、卡上位置欄與開原檔指過去；versions revert 把檔搬回來、清冊改回原狀態。"""

    def setUp(self):
        super().setUp()
        self.home = self.tmp / "home"
        (self.home / "Desktop").mkdir(parents=True)
        patcher = mock.patch.dict(os.environ, {"USERPROFILE": str(self.home), "HOME": str(self.home)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_move_to_desktop_marks_outside_and_card_stays(self):
        desk = self.home / "Desktop"
        before_card_front = cards.parse_front((Path(self.V) / self.card_rel).read_text(encoding="utf-8"))
        self.move(self.fid, str(desk))
        self.assertTrue((desk / "估價單.pdf").is_file())
        e = entry(self.V, self.fid)
        self.assertEqual((e["status"], [loc["uri"] for loc in e["locations"]]), ("outside", ["file://~/Desktop/估價單.pdf"]))
        card = Path(self.V) / self.card_rel
        self.assertTrue(card.is_file(), "卡留著")
        front = cards.parse_front(card.read_text(encoding="utf-8"))
        self.assertEqual(front["原檔"], ["file://~/Desktop/估價單.pdf"])
        self.assertEqual(front["開原檔"], cards.open_link(desk / "估價單.pdf"))
        self.assertNotEqual(front["原檔"], before_card_front["原檔"])
        self.assertEqual(cards.todo(self.V, sources_lib.load(self.V))["moved"], [])
        # 不掃描：再掃一次，狀態不被改成 missing
        report = inventory.scan(self.V, sources_lib.load(self.V))
        inventory.apply(self.V, report, turn.start(self.V, None, "")["turn"])
        self.assertEqual(entry(self.V, self.fid)["status"], "outside")

    def test_revert_moves_file_back_and_restores_entry(self):
        desk = self.home / "Desktop"
        before_card = (Path(self.V) / self.card_rel).read_bytes()
        self.move(self.fid, str(desk))
        code, out = revert(self.V)
        self.assertEqual(code, 0, out)
        self.assertTrue((self.raw / ESTIMATE).is_file())
        self.assertFalse((desk / "估價單.pdf").exists())
        e = entry(self.V, self.fid)
        self.assertEqual((e["status"], e["locations"][0]["uri"]), ("active", "file://" + ESTIMATE))
        self.assertEqual((Path(self.V) / self.card_rel).read_bytes(), before_card)

    def test_move_back_from_desktop_makes_entry_active_again(self):
        desk = self.home / "Desktop"
        self.move(self.fid, str(desk))
        t2 = turn.start(self.V, None, "")["turn"]
        p = se.plan_move(self.V, sources_lib.load(self.V), str(desk / "估價單.pdf"), self.V,
                         dest=str(self.raw / "客戶案件" / "大安陳"))
        se.do_move(self.V, p, t2, "move")
        e = entry(self.V, self.fid)
        self.assertEqual((e["status"], e["locations"][0]["uri"]), ("active", "file://客戶案件/大安陳/估價單.pdf"))
        self.assertTrue(list((Path(self.V) / "檔案索引/客戶案件/大安陳").glob("*.md")))

    def test_outside_not_under_home_records_absolute_uri_and_revert(self):
        """設計自定 (8)：家目錄外也不拒絕，記絕對路徑 file:///…，狀態 outside；path_of 認得；退回搬得回來。"""
        elsewhere = self.tmp / "不在家目錄"
        elsewhere.mkdir()
        before_card = (Path(self.V) / self.card_rel).read_bytes()
        self.move(self.fid, str(elsewhere))
        self.assertTrue((elsewhere / "估價單.pdf").is_file())
        e = entry(self.V, self.fid)
        uri = e["locations"][0]["uri"]
        self.assertEqual(e["status"], "outside")
        self.assertTrue(uri.startswith("file:///") and uri.endswith("/不在家目錄/估價單.pdf"), uri)
        self.assertEqual(os.path.normcase(os.path.realpath(inventory.path_of(self.V, sources_lib.load(self.V), uri))),
                         os.path.normcase(os.path.realpath(elsewhere / "估價單.pdf")))
        front = cards.parse_front((Path(self.V) / self.card_rel).read_text(encoding="utf-8"))
        self.assertEqual(front["原檔"], [uri])
        report = inventory.scan(self.V, sources_lib.load(self.V))  # 不掃描：狀態不變
        inventory.apply(self.V, report, self.t)
        self.assertEqual(entry(self.V, self.fid)["status"], "outside")
        code, out = revert(self.V)
        self.assertEqual(code, 0, out)
        self.assertTrue((self.raw / ESTIMATE).is_file())
        self.assertFalse((elsewhere / "估價單.pdf").exists())
        e = entry(self.V, self.fid)
        self.assertEqual((e["status"], e["locations"][0]["uri"]), ("active", "file://" + ESTIMATE))
        self.assertEqual((Path(self.V) / self.card_rel).read_bytes(), before_card)

    def test_home_itself_as_destination(self):
        self.move(self.fid, str(self.home))
        self.assertEqual(entry(self.V, self.fid)["locations"][0]["uri"], "file://~/估價單.pdf")


class RegistryFollows(Base):
    """放寬甲（spec 五、六節）：整個型別夾改名、登記來源的根搬走，profile.json 的 dir／sources.json 的 spec 跟著換；退回回得去。"""

    def test_type_folder_rename_updates_profile_dir_and_revert(self):
        from kb._lib import entities, profile
        card = Path(self.V) / "案子" / "信義王"
        card.mkdir(parents=True, exist_ok=True)
        (card / "信義王.md").write_text("x", encoding="utf-8")
        before = profile.load(self.V)
        before_dir = next((t.get("dir") or t["name"]) for t in before["types"] if t["name"] == "案子")
        p = se.plan_move(self.V, sources_lib.load(self.V), str(Path(self.V) / before_dir), self.V, new_name="工程案")
        se.do_move(self.V, p, self.t, "rename")
        row = next(t for t in profile.load(self.V)["types"] if t["name"] == "案子")
        self.assertEqual(row["dir"], "工程案")
        self.assertTrue((Path(self.V) / "工程案" / "信義王" / "信義王.md").is_file())
        self.assertEqual(profile.dir_type(profile.load(self.V), "工程案"), "案子")
        code, out = revert(self.V)
        self.assertEqual(code, 0, out)
        row = next(t for t in profile.load(self.V)["types"] if t["name"] == "案子")
        self.assertEqual(row.get("dir") or row["name"], before_dir)
        self.assertTrue((Path(self.V) / before_dir / "信義王" / "信義王.md").is_file())
        self.assertFalse((Path(self.V) / "工程案").exists())

    def test_source_root_rename_updates_spec(self):
        root = self.raw / "客戶案件"
        sp = Path(self.V) / ".system" / "sources.json"
        old = json.loads(sp.read_text(encoding="utf-8"))["sources"][0]
        p = se.plan_move(self.V, sources_lib.load(self.V), str(root), self.V, new_name="客戶案件改名")
        self.assertEqual(p["source_root"], old["alias"])
        se.do_move(self.V, p, self.t, "rename")
        now = json.loads(sp.read_text(encoding="utf-8"))["sources"][0]
        self.assertTrue(now["spec"].endswith("客戶案件改名"), now["spec"])
        self.assertTrue((self.raw / "客戶案件改名").is_dir())
        self.assertEqual(entry(self.V, self.fid)["locations"][0]["uri"], "file://" + ESTIMATE)
        self.assertEqual(entry(self.V, self.fid)["status"], "active")
        self.assertTrue(Path(sources_lib.load(self.V).entries[0]["root"]).is_dir())

    def test_source_root_into_vault_refused(self):
        msg = self.refuse(se.plan_move, self.V, sources_lib.load(self.V), str(self.raw / "客戶案件"), self.V,
                          dest=str(Path(self.V) / "案子"))
        self.assertIn("kb folders remove", msg)
