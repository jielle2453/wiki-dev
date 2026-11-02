"""_lib/source_edit（manage 第二版第 2 點，D-173～D-178）：准許的位置的每一種拒絕、同一顆硬碟（替身）、檔開著（替身）、
同名與 --replace、副檔名、憑證樣式、搬完清冊與卡跟上、不讀子夾的 spec 改寫、跨來源搬、AI 產出搬出後 origin 照舊、
where 的數字、回收筒（替身）、OneDrive（屬性替身）。"""
import json
import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

from tests import _cards, _entities
from kb import guard
from kb._lib import agenda, cards, entities, inventory, pending, turn  # noqa: E402
from kb._lib import source_edit as se  # noqa: E402
from kb._lib import sources as sources_lib  # noqa: E402

ESTIMATE = _entities.ESTIMATE  # 客戶案件/內湖李/估價單.pdf
MEMO = _entities.MEMO  # 公司行政/舊檔/Big5備忘.txt


def inv(V):
    return json.loads((Path(V) / ".system" / "inventory.json").read_text(encoding="utf-8"))


def entry(V, fid):
    return next(e for e in inv(V)["entries"] if e["id"] == fid)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _entities.make_entity_vault()
        _entities.put_entities(self.V, [_entities.entity(_entities.XINYI, "信義王"),
                                        _entities.entity("e-2b2b2b2b", "內湖李")])
        self.card_rel = _entities.write_card(self.V, ESTIMATE, "內湖李估價", ["內湖李"])
        self.fid = _cards.entry_of(self.V, ESTIMATE)["id"]
        cards.render_index(self.V)
        self.t = turn.start(self.V, None, "")["turn"]
        self.sources = sources_lib.load(self.V)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def refuse(self, fn, *args, **kw):
        with self.assertRaises(se.Refused) as cm:
            fn(*args, **kw)
        return str(cm.exception)

    def plan(self, target, dest=None, new_name=None):
        return se.plan_move(self.V, sources_lib.load(self.V), target, self.V, dest=dest, new_name=new_name)

    def move(self, target, dest, op="move", replace=False, new_name=None):
        p = self.plan(target, dest=dest, new_name=new_name)
        return p, se.do_move(self.V, p, self.t, op, replace=replace)

    def snapshot(self):
        return (inv(self.V), sorted(p.relative_to(self.raw).as_posix() for p in self.raw.rglob("*")),
                sorted(p.relative_to(self.V).as_posix() for p in (self.V / "檔案索引").rglob("*.md")))


class MoveFile(Base):
    def test_move_by_card_id_follows(self):
        dest = self.raw / "客戶案件" / "大安陳"
        _p, got = self.move(self.fid, str(dest))
        self.assertTrue((dest / "估價單.pdf").is_file())
        self.assertFalse((self.raw / "客戶案件" / "內湖李" / "估價單.pdf").exists())
        e = entry(self.V, self.fid)
        self.assertEqual([l["uri"] for l in e["locations"]], ["file://客戶案件/大安陳/估價單.pdf"])
        self.assertEqual(e["status"], "active")
        new_card = Path(self.V) / "檔案索引/客戶案件/大安陳" / Path(self.card_rel).name
        self.assertTrue(new_card.is_file())
        self.assertFalse((Path(self.V) / self.card_rel).exists())
        front = cards.parse_front(new_card.read_text(encoding="utf-8"))
        self.assertEqual(front["原檔"], ["file://客戶案件/大安陳/估價單.pdf"])
        self.assertEqual(front["開原檔"], cards.open_link(dest / "估價單.pdf"))
        self.assertIn("檔案索引/客戶案件/大安陳/", (Path(self.V) / "總目錄.md").read_text(encoding="utf-8"))
        rows = turn.moves(self.V, self.t)
        self.assertEqual([(r["op"], r["kind"], r["from"], r["to"]) for r in rows],
                         [("move", "file", "file://客戶案件/內湖李/估價單.pdf", "file://客戶案件/大安陳/估價單.pdf")])
        backed = {e["path"] for e in turn.entries(self.V, self.t)}
        self.assertIn(".system/inventory.json", backed)
        self.assertIn(self.card_rel, backed)
        self.assertEqual(got["cards_moved"], 1)
        self.assertEqual(cards.todo(self.V, sources_lib.load(self.V))["moved"], [])

    def test_move_across_sources_by_path(self):
        src = self.raw / "客戶案件" / "內湖李" / "估價單.pdf"
        dest = self.raw / "報價與合約"
        self.move(str(src), str(dest))
        e = entry(self.V, self.fid)
        self.assertEqual(e["locations"][0]["uri"], "file://報價與合約/估價單.pdf")
        self.assertTrue((Path(self.V) / "檔案索引/報價與合約" / Path(self.card_rel).name).is_file())

    def test_rename_keeps_extension(self):
        p, _got = self.move(self.fid, None, op="rename", new_name="內湖李估價_簽約版")
        self.assertEqual(p["new_name"], "內湖李估價_簽約版.pdf")
        self.assertTrue((self.raw / "客戶案件" / "內湖李" / "內湖李估價_簽約版.pdf").is_file())
        self.assertEqual(entry(self.V, self.fid)["locations"][0]["uri"], "file://客戶案件/內湖李/內湖李估價_簽約版.pdf")
        self.assertEqual(turn.moves(self.V, self.t)[0]["op"], "rename")

    def test_rename_other_extension_refused(self):
        self.assertEqual(self.refuse(self.plan, self.fid, new_name="合約.docx"), "副檔名不改：.pdf → .docx")

    def test_rename_bad_name_and_credential(self):
        self.assertEqual(self.refuse(self.plan, self.fid, new_name="a/b"), se.BAD_NAME)
        self.assertEqual(self.refuse(self.plan, self.fid, new_name="網銀密碼"), se.CREDENTIAL)

    def test_rename_collision(self):
        (self.raw / "客戶案件" / "內湖李" / "舊.pdf").write_bytes(b"x")
        p = self.plan(self.fid, new_name="舊")
        self.assertTrue(p["existing"])
        before = self.snapshot()
        self.assertEqual(self.refuse(se.do_move, self.V, p, self.t, "rename"),
                         "「內湖李」已經有「舊.pdf」（內容不一樣）：一樣的話不用搬；要取代加 --replace（原本那份先進資源回收筒）；要另取名加 --name <新名>。")
        self.assertEqual(self.snapshot(), before)


class Conflicts(Base):
    def test_same_content_and_name_and_check_sentence(self):
        dest = self.raw / "客戶案件" / "大安陳"
        shutil.copy2(self.raw / ESTIMATE, dest / "估價單.pdf")
        p = self.plan(self.fid, dest=str(dest))
        self.assertTrue(p["same_content"])
        with self.assertRaises(se.Conflict) as cm:
            se.do_move(self.V, p, self.t, "move")
        row = cm.exception.rows[0]
        self.assertEqual((row["name"], row["dest"], row["same_content"]), ("估價單.pdf", "客戶案件/大安陳", True))
        self.assertIn("（內容一樣）", str(cm.exception))
        self.assertIn("--replace", str(cm.exception))
        # --name 另取名：兩份都在
        p2 = se.plan_move(self.V, sources_lib.load(self.V), self.fid, self.V, dest=str(dest), to_name="估價單_新.pdf")
        se.do_move(self.V, p2, self.t, "move")
        self.assertTrue((dest / "估價單.pdf").is_file() and (dest / "估價單_新.pdf").is_file())


class Refusals(Base):
    """驗收 2：每種拒絕一字不差、什麼都沒動。"""

    def assert_refused(self, text, *args, **kw):
        before = self.snapshot()
        self.assertEqual(self.refuse(self.plan, *args, **kw), text)
        self.assertEqual(self.snapshot(), before)

    def test_destinations(self):
        outside = self.tmp / "外面"
        outside.mkdir()
        p = self.plan(self.fid, dest=str(outside))  # 放寬甲：沒登記的地方照收（清冊記成 outside）
        self.assertEqual(Path(p["dest_dir"]), outside)
        old = self.raw / "公司行政" / "舊檔"
        guard_sources = json.loads((Path(self.V) / ".system/sources.json").read_text(encoding="utf-8"))
        guard_sources["sources"][2]["excludes"].append({"spec": "舊檔", "kind": "unused", "reason": "", "added": "2026-10-22"})
        (Path(self.V) / ".system/sources.json").write_text(json.dumps(guard_sources, ensure_ascii=False), encoding="utf-8")
        self.assert_refused("「舊檔」使用者說過不讀，不搬進去也不搬出來。", self.fid, dest=str(old))
        for rel, hint in ((".system", "用對應的 kb 指令改"), ("檔案索引", "用 Edit 或 Write 改")):
            msg = self.refuse(self.plan, self.fid, dest=str(Path(self.V) / rel))
            self.assertTrue(msg.startswith(f"「{rel}」是 willy 自己的檔：") and msg.endswith(guard.AI_TAIL), msg)
        self.assertTrue(self.refuse(self.plan, self.fid, dest=str(self.V)).endswith(guard.AI_TAIL))
        for rel in ("案子", "AI 產出", "收件匣"):  # 放寬甲：型別夾、AI 產出、收件匣都收
            self.assertEqual(Path(self.plan(self.fid, dest=str(Path(self.V) / rel))["dest_dir"]), Path(self.V) / rel)
        self.assert_refused("找不到這個夾：" + str(self.tmp / "沒有"), self.fid, dest=str(self.tmp / "沒有"))

    def test_objects(self):
        (Path(self.V) / "案子" / "內湖李").mkdir(parents=True, exist_ok=True)
        dest = str(self.raw / "報價與合約")
        # 放寬甲：整個實體夾、型別夾、登記的來源根本身、綜合卡、沒登記的檔都收
        for src in (Path(self.V) / "案子" / "內湖李", Path(self.V) / "案子",
                    Path(self.V) / "案子" / "信義王" / "信義王.md", self._outside_file()):
            self.assertEqual(self.plan(str(src), dest=dest)["src"], str(src))
        # 登記的來源根本身搬走：搬完自動換登記位置，所以要搬去的地方不能是知識庫或別的來源裡面（兩張卡）
        away = self.tmp / "別處"
        away.mkdir()
        self.assertEqual(self.plan(str(self.raw / "公司行政"), dest=str(away))["source_root"], "公司行政")
        self.assertIn("kb folders remove", self.refuse(self.plan, str(self.raw / "公司行政"), dest=dest))
        self.assert_refused("這個檔名像密碼或金鑰，不動。", str(self.raw / "公司行政" / "薪資" / "網銀密碼.txt"), dest=dest)
        msg = self.refuse(self.plan, str(Path(self.V) / ".system" / "sources.json"), dest=dest)
        self.assertTrue(msg.startswith("「sources.json」是 willy 自己的檔：") and msg.endswith(guard.AI_TAIL), msg)
        self.assert_refused("找不到這個檔：f-00000000", "f-00000000", dest=dest)
        self.assert_refused("不能把夾搬進它自己裡面", str(self.raw / "客戶案件" / "內湖李"),
                            dest=str(self.raw / "客戶案件" / "內湖李"))

    def _outside_file(self):
        p = self.tmp / "外.txt"
        p.write_text("x", encoding="utf-8")
        return str(p)

    def test_credential_destination_and_synthesis_name(self):
        secret = self.raw / "報價與合約" / "密碼"
        secret.mkdir()
        self.assert_refused("這個檔名像密碼或金鑰，不動。", self.fid, dest=str(secret))
        md = self.raw / "客戶案件" / "信義王.md"
        md.write_text("x", encoding="utf-8")
        _cards.scan_apply(self.V)
        self.assert_refused("「信義王.md」跟綜合卡同名，換個名字", str(md), dest=str(Path(self.V) / "案子" / "信義王"))

    def test_same_place(self):
        self.assert_refused("「估價單.pdf」已經在「內湖李」裡了", self.fid, dest=str(self.raw / "客戶案件" / "內湖李"))


class Doubles(Base):
    def test_other_disk_copies_then_trashes_original(self):
        """放寬甲：不同顆硬碟不拒絕，複製過去、比內容指紋一樣才把原檔丟資源回收筒。"""
        src = self.raw / "客戶案件" / "內湖李" / "估價單.pdf"
        body = src.read_bytes()
        with mock.patch.object(se, "_dev", side_effect=lambda p: 1 if "內湖李" in str(p) else 2):
            p = self.plan(self.fid, dest=str(self.raw / "報價與合約"))
        self.assertTrue(p["cross_disk"])
        trashed = []

        def fake_trash(path):
            trashed.append(Path(path).name)
            os.remove(path)
        with mock.patch.object(se, "shell_trash", side_effect=fake_trash), \
                mock.patch.object(se, "recycle_room", return_value=(0, 10 ** 9)):
            got = se.do_move(self.V, p, self.t, "move")
        self.assertEqual((self.raw / "報價與合約" / "估價單.pdf").read_bytes(), body)
        self.assertFalse(src.exists())
        self.assertEqual(trashed, ["估價單.pdf"])
        self.assertEqual(got["original"], {"kept": "trash", "refused": None})
        self.assertEqual(entry(self.V, self.fid)["locations"][0]["uri"], "file://報價與合約/估價單.pdf")

    def test_other_disk_no_room_keeps_both(self):
        """連回合備份都放不下：原檔不動、兩份都留，回 refused 句交給 AI 問使用者（待你決定 1）。"""
        src = self.raw / "客戶案件" / "內湖李" / "估價單.pdf"
        with mock.patch.object(se, "_dev", side_effect=lambda p: 1 if "內湖李" in str(p) else 2):
            p = self.plan(self.fid, dest=str(self.raw / "報價與合約"))
        with mock.patch.object(se, "shell_trash", side_effect=se.BinUnavailable("x")), \
                mock.patch.object(se.shutil, "disk_usage", return_value=mock.Mock(free=0)):
            got = se.do_move(self.V, p, self.t, "move")
        self.assertTrue(src.exists() and (self.raw / "報價與合約" / "估價單.pdf").exists())
        self.assertIn("--permanent", got["original"]["refused"])

    def test_file_open(self):
        p = self.plan(self.fid, dest=str(self.raw / "報價與合約"))
        before = self.snapshot()
        with mock.patch.object(se, "_rename", side_effect=PermissionError(13, "in use")):
            self.assertEqual(self.refuse(se.do_move, self.V, p, self.t, "move"),
                             "「估價單.pdf」開著，關掉才動得了：請使用者關掉那個檔（沒存的內容會不見，不要替他關），關好再跑一次。")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(turn.moves(self.V, self.t), [])

    def test_replace_trashes_target_then_moves(self):
        dest = self.raw / "客戶案件" / "大安陳"
        (dest / "估價單.pdf").write_bytes(b"old one")
        _cards.scan_apply(self.V)
        old_id = _cards.entry_of(self.V, "客戶案件/大安陳/估價單.pdf")["id"]
        p = self.plan(self.fid, dest=str(dest))
        self.assertTrue(p["existing"])
        with self.assertRaises(se.Conflict) as cm:
            se.do_move(self.V, p, self.t, "move")
        self.assertFalse(cm.exception.rows[0]["same_content"])
        self.assertEqual(cm.exception.rows[0]["existing"], "file://客戶案件/大安陳/估價單.pdf")
        calls = []

        def fake_trash(path):
            calls.append(Path(path).name)
            os.remove(path)
        with mock.patch.object(se, "shell_trash", side_effect=fake_trash), \
                mock.patch.object(se, "recycle_room", return_value=(0, 10 ** 9)):
            se.do_move(self.V, self.plan(self.fid, dest=str(dest)), self.t, "move", replace=True)
        self.assertEqual(calls, ["估價單.pdf"])
        self.assertNotEqual((dest / "估價單.pdf").read_bytes(), b"old one")
        self.assertEqual(entry(self.V, old_id)["status"], "deleted")
        self.assertEqual(entry(self.V, self.fid)["locations"][0]["uri"], "file://客戶案件/大安陳/估價單.pdf")
        self.assertEqual([r["op"] for r in turn.moves(self.V, self.t)], ["trash", "move"])


class MoveFolder(Base):
    def add_hidden(self, alias_index, spec):
        p = Path(self.V) / ".system/sources.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["sources"][alias_index]["excludes"].append({"spec": spec, "kind": "hidden", "reason": "", "added": "2026-10-22"})
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def sources_json(self):
        return json.loads((Path(self.V) / ".system/sources.json").read_text(encoding="utf-8"))

    def test_check_counts_and_moves_nothing(self):
        lee = self.raw / "客戶案件" / "內湖李"
        (lee / "私人").mkdir()
        (lee / "私人" / "日記.txt").write_text("秘密", encoding="utf-8")
        (lee / "~$估價.docx").write_bytes(b"x")
        self.add_hidden(0, "內湖李/私人")
        before = self.snapshot()
        p = self.plan(str(lee), dest=str(self.raw / "報價與合約"))
        lines = se.check_lines(p, "move")
        self.assertEqual(lines[0], "要搬：內湖李（3 份，卡 1 張）從 客戶案件 搬到 報價與合約")
        self.assertIn("裡面不讀的夾：私人", lines)
        self.assertIn("可能有檔開著：~$估價.docx", lines)
        self.assertEqual(self.snapshot(), before)

    def test_same_source_rewrites_exclude(self):
        lee = self.raw / "客戶案件" / "內湖李"
        (lee / "私人").mkdir()
        (lee / "私人" / "日記.txt").write_text("秘密", encoding="utf-8")
        self.add_hidden(0, "內湖李/私人")
        archive = self.raw / "客戶案件" / "2025 封存"
        archive.mkdir()
        self.move(str(lee), str(archive))
        self.assertTrue((archive / "內湖李" / "估價單.pdf").is_file())
        self.assertEqual(self.sources_json()["sources"][0]["excludes"][-1]["spec"], "2025 封存/內湖李/私人")
        self.assertEqual(entry(self.V, self.fid)["locations"][0]["uri"], "file://客戶案件/2025 封存/內湖李/估價單.pdf")
        d = guard.decide({"tool_name": "Read", "tool_input": {"file_path": str(archive / "內湖李" / "私人" / "日記.txt")},
                          "cwd": str(self.V)})
        self.assertEqual(d.decision, "deny")
        self.assertEqual(turn.moves(self.V, self.t)[0]["kind"], "folder")
        self.assertTrue((Path(self.V) / "檔案索引/客戶案件/2025 封存/內湖李" / Path(self.card_rel).name).is_file())

    def test_across_sources_moves_exclude_row(self):
        lee = self.raw / "客戶案件" / "內湖李"
        (lee / "私人").mkdir()
        (lee / "私人" / "日記.txt").write_text("秘密", encoding="utf-8")
        self.add_hidden(0, "內湖李/私人")
        self.move(str(lee), str(self.raw / "報價與合約"))
        data = self.sources_json()["sources"]
        self.assertEqual([x["spec"] for x in data[0]["excludes"]], [])
        self.assertEqual(data[1]["excludes"][-1]["spec"], "內湖李/私人")
        self.assertEqual(data[1]["excludes"][-1]["kind"], "hidden")
        d = guard.decide({"tool_name": "Read", "tool_input": {
            "file_path": str(self.raw / "報價與合約" / "內湖李" / "私人" / "日記.txt")}, "cwd": str(self.V)})
        self.assertEqual(d.decision, "deny")
        self.assertEqual(entry(self.V, self.fid)["locations"][0]["uri"], "file://報價與合約/內湖李/估價單.pdf")

    def test_folder_with_credential_file_into_vault_refused(self):
        """security-review：知識庫裡不查憑證樣式（D-081），整個夾搬進實體夾會把 .env、id_rsa 帶進來，先擋。"""
        proj = self.raw / "客戶案件" / "內湖李"
        (proj / ".env").write_text("KEY=1", encoding="utf-8")
        dest = Path(self.V) / "案子" / "內湖李"
        dest.mkdir(parents=True, exist_ok=True)
        self.assertEqual(self.refuse(self.plan, str(proj), dest=str(dest)), "這個檔名像密碼或金鑰，不動。")
        (proj / ".env").unlink()
        (proj / "子").mkdir()
        (proj / "子" / "網銀密碼.txt").write_text("x", encoding="utf-8")
        self.assertEqual(self.refuse(self.plan, str(proj), dest=str(dest)), "這個檔名像密碼或金鑰，不動。")

    def test_folder_with_hidden_into_vault_refused(self):
        lee = self.raw / "客戶案件" / "內湖李"
        (lee / "私人").mkdir()
        self.add_hidden(0, "內湖李/私人")
        (Path(self.V) / "案子" / "內湖李").mkdir(parents=True, exist_ok=True)
        self.assertEqual(self.refuse(self.plan, str(lee), dest=str(Path(self.V) / "案子" / "內湖李")),
                         "「私人」使用者說過不讀，不搬進去也不搬出來。")


class Areas(Base):
    def test_ai_output_to_entity_folder_keeps_origin(self):
        out = Path(self.V) / "AI 產出" / "內湖李報告.docx"
        t = turn.start(self.V, None, "")["turn"]
        turn.backup(self.V, "AI 產出/內湖李報告.docx", t)
        out.write_bytes(b"report")
        e = inventory.register_output(self.V, "AI 產出/內湖李報告.docx", t)
        dest = Path(self.V) / "案子" / "內湖李"
        dest.mkdir(parents=True, exist_ok=True)
        self.move(str(out), str(dest))
        got = entry(self.V, e["id"])
        self.assertEqual(got["origin"], "ai_output")
        self.assertEqual(got["locations"][0]["uri"], "file://知識庫/案子/內湖李/內湖李報告.docx")
        self.assertTrue((dest / "內湖李報告.docx").is_file())

    def test_inbox_to_source(self):
        fid = _cards.entry_of(self.V, "收件匣/貼文.txt")["id"]
        self.move(str(Path(self.V) / "收件匣" / "貼文.txt"), str(self.raw / "客戶案件" / "大安陳"))
        self.assertEqual(entry(self.V, fid)["locations"][0]["uri"], "file://客戶案件/大安陳/貼文.txt")


class Trash(Base):
    def fake(self, path):
        os.remove(path)

    def test_check_lines(self):
        _entities.install(self.V)
        _entities.put_entities(self.V, [_entities.entity("e-2b2b2b2b", "內湖李")])
        (Path(self.V) / "案子" / "內湖李").mkdir(parents=True, exist_ok=True)
        (Path(self.V) / "案子" / "內湖李" / "內湖李.md").write_text("x", encoding="utf-8")
        with mock.patch.object(se, "recycle_room", return_value=(0, 10 ** 9)):
            p = se.plan_trash(self.V, self.sources, self.fid, self.V)
        self.assertEqual(se.trash_lines(p), ["要丟進資源回收筒：估價單.pdf（客戶案件\\內湖李）",
                                             "那張卡會拿掉；綜合卡要更新：內湖李",
                                             "說「退回上一版」救不回來，刪錯要從資源回收筒拿"])

    def test_check_when_same_content_elsewhere(self):
        """同一份內容在別處還有：卡留著，第二行不能說這份沒有卡（skill-reviewer）。"""
        import shutil as sh
        sh.copy2(self.raw / ESTIMATE, self.raw / "報價與合約" / "估價單.pdf")
        _cards.scan_apply(self.V)
        with mock.patch.object(se, "recycle_room", return_value=(0, 10 ** 9)):
            p = se.plan_trash(self.V, sources_lib.load(self.V), str(self.raw / "報價與合約" / "估價單.pdf"), self.V)
        self.assertEqual(se.trash_lines(p)[1], "同一份內容在別處還有，卡留著")

    def test_bin_unavailable_keeps_backup_then_deletes(self):
        """驗收 12b：回收筒用不了 -> 先留進回合備份、比指紋一樣才刪，kept 是 backup；退回後檔回原位。"""
        src = self.raw / ESTIMATE
        body = src.read_bytes()
        for boom in (se.BinUnavailable("這顆磁碟沒有資源回收筒"),):
            with mock.patch.object(se, "shell_trash", side_effect=boom), mock.patch.object(se, "recycle_room", return_value=(0, 10 ** 9)):
                p = se.plan_trash(self.V, self.sources, self.fid, self.V)
                got = se.do_trash(self.V, p, self.t)
        self.assertEqual(got["kept"], "backup")
        self.assertFalse(src.exists())
        rows = [e for e in turn.entries(self.V, self.t) if e.get("uri") == "file://客戶案件/內湖李/估價單.pdf"]
        self.assertEqual(rows[0]["action"], "modify")
        self.assertEqual((turn.turn_dir(self.V, self.t) / "files" / rows[0]["path"]).read_bytes(), body)

    def test_too_big_goes_to_backup_and_no_room_refuses(self):
        src = self.raw / ESTIMATE
        with mock.patch.object(se, "recycle_room", return_value=(100, 120)):
            p = se.plan_trash(self.V, self.sources, self.fid, self.V)
            with mock.patch.object(se.shutil, "disk_usage", return_value=mock.Mock(free=0)):
                msg = self.refuse(se.do_trash, self.V, p, self.t)
        self.assertIn("--permanent", msg)
        self.assertIn("進不了資源回收筒", msg)
        self.assertTrue(src.exists())
        with mock.patch.object(se, "recycle_room", return_value=(100, 120)), \
                mock.patch.object(se.shutil, "disk_usage", return_value=mock.Mock(free=0)):
            got = se.do_trash(self.V, p, self.t, permanent=True)
        self.assertEqual(got["kept"], "permanent")
        self.assertFalse(src.exists())

    def test_permanent_still_trashes_when_bin_works(self):
        with mock.patch.object(se, "shell_trash", side_effect=self.fake), mock.patch.object(se, "recycle_room", return_value=(0, 10 ** 9)):
            p = se.plan_trash(self.V, self.sources, self.fid, self.V)
            got = se.do_trash(self.V, p, self.t, permanent=True)
        self.assertEqual(got["kept"], "trash")

    def test_folder_empty_and_with_files(self):
        empty = self.raw / "客戶案件" / "空夾"
        empty.mkdir()
        p = se.plan_trash(self.V, sources_lib.load(self.V), str(empty), self.V)
        self.assertTrue(p["empty"])
        got = se.do_trash(self.V, p, self.t)
        self.assertEqual(got["kept"], "removed")
        self.assertFalse(empty.exists())
        lee = self.raw / "客戶案件" / "內湖李"
        with mock.patch.object(se, "shell_trash", side_effect=lambda x: shutil.rmtree(x)), \
                mock.patch.object(se, "recycle_room", return_value=(0, 10 ** 9)):
            p = se.plan_trash(self.V, sources_lib.load(self.V), str(lee), self.V)
            got = se.do_trash(self.V, p, self.t)
        self.assertFalse(lee.exists())
        self.assertEqual(entry(self.V, self.fid)["status"], "deleted")
        self.assertTrue(got["card_removed"])

    def test_readonly_file_is_trashed(self):
        src = self.raw / ESTIMATE
        os.chmod(src, 0o444)
        with mock.patch.object(se, "shell_trash", side_effect=self.fake), mock.patch.object(se, "recycle_room", return_value=(0, 10 ** 9)):
            p = se.plan_trash(self.V, self.sources, self.fid, self.V)
            se.do_trash(self.V, p, self.t)
        self.assertFalse(src.exists())

    def test_trash_follows_like_drop(self):
        t = self.t
        pending.add(self.V, "unreadable", [self.fid], "x 讀不到", "檔案壞了", t)
        agenda.add(self.V, "到期", "2026-12-01", "交估價", ["內湖李"], t, card=self.fid)
        with mock.patch.object(se, "recycle_room", return_value=(0, 10 ** 9)):
            p = se.plan_trash(self.V, sources_lib.load(self.V), self.fid, self.V)
        with mock.patch.object(se, "shell_trash", side_effect=self.fake):
            got = se.do_trash(self.V, p, t)
        self.assertFalse((self.raw / ESTIMATE).exists())
        self.assertEqual(entry(self.V, self.fid)["status"], "deleted")
        self.assertFalse((Path(self.V) / self.card_rel).exists())
        self.assertTrue(got["card_removed"])
        self.assertIsNone(pending.open_for(self.V, self.fid, "unreadable"))
        self.assertEqual([i["status"] for i in agenda.load(self.V)["items"]], ["cancelled"])
        self.assertEqual(turn.moves(self.V, t)[0], dict(turn.moves(self.V, t)[0], op="trash", to=None))
        self.assertEqual(se.trash_sentence(p, got), "已丟進資源回收筒：估價單.pdf")  # D-305：成功句不講卡


class OneDrive(Base):
    def test_trash_third_line(self):
        with mock.patch.object(se, "recycle_room", return_value=(0, 10 ** 9)):
            with mock.patch.object(se, "cloud_only", return_value=True):
                p = se.plan_trash(self.V, self.sources, self.fid, self.V)
                self.assertEqual(se.trash_lines(p)[2], "這份只在雲端：會從你所有裝置一起刪，要救得到 OneDrive 網頁的回收筒")
            with mock.patch.object(se, "onedrive_roots", return_value=[str(self.raw).replace("\\", "/").lower()]):
                p = se.plan_trash(self.V, self.sources, self.fid, self.V)
                self.assertEqual(se.trash_lines(p)[2], "刪錯要從資源回收筒拿；別台電腦與 OneDrive 上的那份也會一起刪")
            p = se.plan_trash(self.V, self.sources, self.fid, self.V)
            self.assertEqual(se.trash_lines(p)[2], "說「退回上一版」救不回來，刪錯要從資源回收筒拿")

    def test_cloud_only_move_keeps_id(self):
        """驗收 21：只在雲端的檔搬了，清冊位置換了、id 不變，沒有變成新增加不見。"""
        data = inv(self.V)  # 清冊裡它是占位檔：沒有指紋（掃描認不出搬動，B-095）
        for x in data["entries"]:
            if x["id"] == self.fid:
                x["read"], x["fingerprints"] = "placeholder", []
        (Path(self.V) / ".system/inventory.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        real_kind = inventory.read_kind

        def kind(segs, st, cap, credential=True):
            return ("placeholder", None) if segs[-1] == "估價單.pdf" else real_kind(segs, st, cap, credential)
        with mock.patch.object(se, "cloud_only", return_value=True), mock.patch.object(inventory, "read_kind", kind):
            self.move(self.fid, str(self.raw / "報價與合約"))
        e = entry(self.V, self.fid)
        self.assertEqual(e["status"], "active")
        self.assertEqual(e["locations"][0]["uri"], "file://報價與合約/估價單.pdf")
        self.assertEqual(sum(1 for x in inv(self.V)["entries"]
                             if any(l["uri"] == "file://報價與合約/估價單.pdf" for l in x["locations"])), 1)

    def test_leaving_onedrive_download_line(self):
        root = str(self.raw / "客戶案件").replace("\\", "/").lower()
        with mock.patch.object(se, "onedrive_roots", return_value=[root]), \
                mock.patch.object(se, "_attrs", return_value=se.RECALL_ON_DATA_ACCESS):
            p = self.plan(str(self.raw / "客戶案件" / "內湖李"), dest=str(self.raw / "報價與合約"))
        self.assertTrue(any(l.startswith("1 份只在雲端，搬出 OneDrive 會先全部下載（約 ") for l in se.check_lines(p, "move")))


class Where(Base):
    def test_counts(self):
        _entities.write_card(self.V, MEMO, "內湖李備忘", ["內湖李"])
        _entities.write_card(self.V, _entities.TEMPLATE, "內湖李合約範本", ["內湖李"])
        before = self.snapshot()
        got = se.where(self.V, "內湖李")
        by = {r["folder"]: r for r in got["folders"]}
        self.assertEqual(set(by), {"客戶案件/內湖李", "公司行政/舊檔", "報價與合約"})
        self.assertEqual(by["客戶案件/內湖李"]["count"], 1)
        self.assertEqual(by["客戶案件/內湖李"]["types"], {"會議紀錄": 1})
        first = entry(self.V, self.fid)["first_seen"][:10]
        self.assertEqual(by["客戶案件/內湖李"]["latest"], first)
        self.assertEqual(se.where_lines(got)[0], "內湖李的檔放在：")
        self.assertIn(f"- 客戶案件/內湖李：1 份（會議紀錄 1），最近 {first}", se.where_lines(got))
        self.assertEqual(se.where(self.V, "內湖李", "合約")["folders"], [])
        self.assertEqual(self.snapshot(), before)

    def test_unknown_entity(self):
        self.assertEqual(self.refuse(se.where, self.V, "沒有這個"), "實體清單沒有「沒有這個」，先 kb entity add")


class Open(Base):
    def test_open_two_and_refusals(self):
        opened = []
        with mock.patch.object(se, "_startfile", side_effect=opened.append):
            paths = se.check_open(self.V, self.sources, [str(self.raw / "客戶案件"), str(self.tmp)], self.V)
            se.open_folders(paths)
        self.assertEqual(len(opened), 2)
        self.assertEqual(self.refuse(se.check_open, self.V, self.sources, ["a", "b", "c"], self.V), "一次最多開兩個夾")
        self.assertEqual(self.refuse(se.check_open, self.V, self.sources, [str(Path(self.V) / ".system")], self.V),
                         "「.system」是知識庫自己用的地方，不搬進去也不搬出來")


if __name__ == "__main__":
    unittest.main()
