"""暫存區（issue #10，D-240～D-245）的程式庫層：回合記對話紀錄位置、env 的 inbox_reminded、清冊 register_intake 與掃描保留 intake 欄、
卡檔頭的「收件」行、從對話紀錄取貼的圖與文字（tests/fixtures/intake 的假紀錄：桌面版有 <pasted_content> 與 base64 圖、
有 inlined_image_paths 的、VS Code 沒有標記的）。kb intake 整段流程在 test_scripts_intake_cli。"""
import base64
import json
import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

from tests import _cards
from tests.test_lib_inventory_scan import make_inv_vault
from kb._lib import cards, env, intake, inventory, turn  # noqa: E402
from kb._lib import sources as sources_lib  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "intake"
PASTE = "第一條 甲方委託乙方裝修。\n第二條 工期 30 天，逾期每日罰 1,000 元。\n\n  （以下空白）"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_inv_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class TurnTranscript(Base):
    def test_start_records_transcript_and_inherit_does_not_carry_it(self):
        t = turn.start(self.V, "sid-a", "存起來", transcript="C:/x/sess.jsonl")
        self.assertEqual(t["transcript"], "C:/x/sess.jsonl")
        self.assertEqual(turn.current(self.V, "sid-a")["transcript"], "C:/x/sess.jsonl")
        again = turn.start(self.V, "sid-a", "", inherit=t)
        self.assertNotIn("transcript", again)

    def test_start_without_transcript_has_no_key(self):
        self.assertNotIn("transcript", turn.start(self.V, "sid-a", "x"))


class EnvInbox(Base):
    def test_inbox_reminded_round_trip_and_other_keys_kept(self):
        self.assertIsNone(env.inbox_reminded(self.V))
        env.set_vault_path(self.V, "D:/知識庫")
        env.set_inbox_reminded(self.V, "2026-10-26")
        self.assertEqual(env.inbox_reminded(self.V), "2026-10-26")
        self.assertEqual(env.vault_path(self.V), "D:/知識庫")


class RegisterIntake(Base):
    def put(self, rel, data, turn_id):
        turn.backup(self.V, rel, turn_id)
        p = self.V / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def test_new_entry_then_update_appends_fingerprint(self):
        t = turn.start(self.V, None, "")["turn"]
        rel = "暫存區/公司系統/客戶王先生.md"
        self.put(rel, b"v1", t)
        e = inventory.register_intake(self.V, rel, t, {"from": "公司系統", "name": "客戶王先生"})
        self.assertEqual((e["origin"], e["status"], e["created_turn"]), ("intake", "active", t))
        self.assertEqual((e["intake"]["from"], e["intake"]["name"]), ("公司系統", "客戶王先生"))
        self.assertRegex(e["intake"]["received"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")
        self.assertEqual(e["locations"][0]["uri"], "file://暫存區/公司系統/客戶王先生.md")
        t2 = turn.start(self.V, None, "")["turn"]
        self.put(rel, b"v2-longer", t2)
        with mock.patch.object(inventory, "_now", return_value="2026-10-27T09:00:00"):
            e2 = inventory.register_intake(self.V, rel, t2, {"from": "公司系統", "name": "客戶王先生"})
        self.assertEqual(e2["id"], e["id"])
        self.assertEqual(len(e2["fingerprints"]), 2)
        self.assertEqual(e2["fingerprints"][-1]["turn"], t2)
        self.assertEqual(e2["intake"]["received"], e["intake"]["received"])  # 裁定 6 #3：記第一次收的，覆蓋看指紋的 time
        self.assertEqual(e2["fingerprints"][-1]["time"], "2026-10-27T09:00:00")
        self.assertEqual(e2["locations"][0]["size"], len(b"v2-longer"))
        self.assertEqual(sum(1 for x in inventory.load(self.V)["entries"] if x["origin"] == "intake"), 1)

    def test_fresh_does_not_attach_to_a_stale_active_entry(self):
        """code review：檔在 kb 外被刪、清冊還記著 active，新收同名的另開一筆，舊的改 superseded。"""
        t = turn.start(self.V, None, "")["turn"]
        self.put("暫存區/a.pdf", b"old", t)
        old = inventory.register_intake(self.V, "暫存區/a.pdf", t, {}, fresh=True)
        (self.V / "暫存區" / "a.pdf").unlink()
        t2 = turn.start(self.V, None, "")["turn"]
        self.put("暫存區/a.pdf", b"new content", t2)
        new = inventory.register_intake(self.V, "暫存區/a.pdf", t2, {}, fresh=True)
        self.assertNotEqual(new["id"], old["id"])
        self.assertEqual(new["created_turn"], t2)
        got = {e["id"]: e["status"] for e in inventory.load(self.V)["entries"]}
        self.assertEqual((got[old["id"]], got[new["id"]]), ("superseded", "active"))

    def test_meta_keys_only_when_given(self):
        t = turn.start(self.V, None, "")["turn"]
        self.put("暫存區/合約.pdf", b"%PDF", t)
        e = inventory.register_intake(self.V, "暫存區/合約.pdf", t, {})
        self.assertEqual(set(e["intake"]), {"received"})

    def test_scan_and_apply_keep_intake_field(self):
        t = turn.start(self.V, None, "")["turn"]
        self.put("暫存區/合約.pdf", b"%PDF-1", t)
        e = inventory.register_intake(self.V, "暫存區/合約.pdf", t, {"original_name": "IMG_1.pdf"})
        report = inventory.scan(self.V, sources_lib.load(self.V))
        inventory.apply(self.V, report, turn.start(self.V, None, "")["turn"])
        got = inventory.entry_for(self.V, "file://暫存區/合約.pdf")
        self.assertEqual(got["id"], e["id"])
        self.assertEqual(got["intake"], e["intake"])
        (self.V / "暫存區" / "合約.pdf").write_bytes(b"%PDF-2 changed")
        report = inventory.scan(self.V, sources_lib.load(self.V))
        inventory.apply(self.V, report, turn.start(self.V, None, "")["turn"])
        got = inventory.entry_for(self.V, "file://暫存區/合約.pdf")
        self.assertEqual(got["intake"], e["intake"])
        self.assertEqual(len(got["fingerprints"]), 2)


class CardHeader(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _cards.make_card_vault()
        self.t = turn.start(self.V, None, "")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add(self, rel, meta, data=b"hello"):
        turn.backup(self.V, rel, self.t)
        p = self.V / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data + rel.encode("utf-8"))
        with mock.patch.object(inventory, "_now", return_value="2026-10-26T14:32:05"):
            return inventory.register_intake(self.V, rel, self.t, meta)

    def item(self, fid):
        return next(i for i in cards.todo(self.V, sources_lib.load(self.V))["new"] if i["id"] == fid)

    def test_header_has_intake_line_three_examples(self):
        cases = (("暫存區/a.txt", {}, "收件: 2026-10-26"),
                 ("暫存區/公司系統/b.md", {"from": "公司系統", "name": "b"}, "收件: 2026-10-26，從公司系統"),
                 ("暫存區/c.png", {"pasted": "image", "copy": True}, "收件: 2026-10-26，對話裡的版本"))
        for rel, meta, want in cases:
            with self.subTest(rel=rel):
                e = self.add(rel, meta)
                lines = self.item(e["id"])["header"].splitlines()
                self.assertEqual(lines[lines.index("出處: 對話收件") + 1], want)

    def test_validate_wants_the_line_only_when_entry_has_intake(self):
        e = self.add("暫存區/a.txt", {"from": "公司系統"})
        item = self.item(e["id"])
        p = _cards.write_card(self.V, item, "王先生資料", kind="資料")
        by_id = {x["id"]: x for x in inventory.load(self.V)["entries"]}
        rel = p.relative_to(self.V).as_posix()
        self.assertEqual(cards.validate(self.V, rel, by_id), (True, ""))
        text = p.read_text(encoding="utf-8")
        for bad in (text.replace("收件: 2026-10-26，從公司系統\n", ""), text.replace("，從公司系統", "，從別處")):
            p.write_text(bad, encoding="utf-8", newline="\n")
            self.assertEqual(cards.validate(self.V, rel, by_id), (False, "收件那行照 kb cards todo 印的抄"))
        # 客戶自己丟進暫存區的（掃描入冊、沒有 intake 欄）：卡上沒有這行照過
        (self.V / "暫存區" / "自己丟的.txt").write_text("hi", encoding="utf-8")
        _cards.scan_apply(self.V)
        mine = inventory.entry_for(self.V, "file://暫存區/自己丟的.txt")
        self.assertNotIn("intake", mine)
        item = self.item(mine["id"])
        self.assertNotIn("收件:", item["header"])
        p2 = _cards.write_card(self.V, item, "自己丟的", kind="資料")
        by_id = {x["id"]: x for x in inventory.load(self.V)["entries"]}
        self.assertEqual(cards.validate(self.V, p2.relative_to(self.V).as_posix(), by_id), (True, ""))

    def test_broken_intake_line_goes_to_broken_with_header(self):
        e = self.add("暫存區/a.txt", {})
        item = self.item(e["id"])
        p = _cards.write_card(self.V, item, "甲", kind="資料")
        p.write_text(p.read_text(encoding="utf-8").replace("收件: 2026-10-26\n", ""), encoding="utf-8", newline="\n")
        broken = cards.todo(self.V, sources_lib.load(self.V))["broken"]
        hit = next(b for b in broken if b.get("id") == e["id"])
        self.assertEqual(hit["reason"], "收件那行照 kb cards todo 印的抄")
        self.assertIn("收件: 2026-10-26\n", hit["header"])


class Transcript(unittest.TestCase):
    def message(self, name):
        return intake.read_message(FIX / name)

    def test_desktop_lists_image_and_pasted_text(self):
        msg = self.message("desktop.jsonl")
        items = intake.pasted_items(msg)
        png = (FIX / "名片.png").read_bytes()
        self.assertEqual(items, [{"ref": "image:1", "kind": "image", "media_type": "image/png", "bytes": len(png)},
                                 {"ref": "text:1", "kind": "text", "chars": len(PASTE)}])
        self.assertEqual(intake.pasted_text(msg, 1), PASTE)
        data, media, upload = intake.pasted_image(msg, 1)
        self.assertEqual((data, media, upload), (png, "image/png", None))

    def test_uploads_original_is_matched_in_order(self):
        msg = self.message("uploads.jsonl")
        self.assertEqual(msg["uploads"], ["<UPLOADS>/sess/c226210d-image.png"])
        _data, _media, upload = intake.pasted_image(msg, 1)
        self.assertEqual(upload, "<UPLOADS>/sess/c226210d-image.png")

    def test_vscode_without_marker_is_the_whole_message(self):
        msg = self.message("vscode.jsonl")
        whole = "王先生合約\n第一條 甲方委託乙方裝修。\n第二條 工期 30 天。"
        self.assertEqual(intake.pasted_items(msg), [{"ref": "text:1", "kind": "text", "chars": len(whole)}])
        self.assertEqual(intake.pasted_text(msg, 1), whole)
        msg = self.message("plain.jsonl")
        self.assertEqual(intake.pasted_text(msg, 1), "只有一段文字，沒有標記")

    def test_missing_item_or_file_raises(self):
        msg = self.message("vscode.jsonl")
        with self.assertRaises(intake.NotInTranscript):
            intake.pasted_image(msg, 1)
        with self.assertRaises(intake.NotInTranscript):
            intake.pasted_text(msg, 2)
        with self.assertRaises(intake.NotInTranscript):
            intake.read_message(FIX / "沒有這個檔.jsonl")

    def test_reads_from_the_end_skipping_tool_results_meta_and_notifications(self):
        msg = self.message("desktop.jsonl")
        self.assertEqual(msg["uuid"], "u2")

    def test_previous_message_is_the_one_right_before(self):
        """裁定 8 #2：上一則只認緊接在前的那一則客戶訊息（中間只隔 AI 回答、工具結果這類），再往前不找。"""
        this, prev = intake.read_messages(FIX / "desktop.jsonl", prev=True)
        self.assertEqual((this["uuid"], prev["uuid"]), ("u2", "u1"))
        self.assertEqual(intake.pasted_text(prev, 1), "上一句：幫我看王先生")
        items = intake.pasted_list(FIX / "desktop.jsonl")
        self.assertEqual([i["ref"] for i in items], ["image:1", "text:1", "prev:text:1"])

    def test_no_previous_across_compaction_or_at_start(self):
        import tempfile
        d = Path(tempfile.mkdtemp(prefix="kbintake-"))
        try:
            lines = [json.dumps({"type": "user", "uuid": "old", "message": {"role": "user", "content": "很久以前"}}),
                     json.dumps({"type": "user", "uuid": "sum", "isCompactSummary": True,
                                 "message": {"role": "user", "content": "摘要"}}),
                     json.dumps({"type": "user", "uuid": "now", "message": {"role": "user", "content": "存起來"}})]
            p = d / "c.jsonl"
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
            got = intake.read_messages(p, prev=True)
            self.assertEqual([m["uuid"] for m in got], ["now"])
            p.write_text(lines[2] + "\n", encoding="utf-8")
            self.assertEqual([m["uuid"] for m in intake.read_messages(p, prev=True)], ["now"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def _jsonl(self, records):
        import tempfile
        d = Path(tempfile.mkdtemp(prefix="kbintake-"))
        self.addCleanup(shutil.rmtree, d, True)
        p = d / "t.jsonl"
        p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
        return p

    @staticmethod
    def _user(uid, parent, content, **extra):
        return dict({"type": "user", "uuid": uid, "parentUuid": parent, "message": {"role": "user", "content": content}}, **extra)

    @staticmethod
    def _ai(uid, parent):
        return {"type": "assistant", "uuid": uid, "parentUuid": parent, "message": {"role": "assistant", "content": "好"}}

    def test_previous_skips_interrupt_and_command_records(self):
        """code review：按停止（[Request interrupted…]）與斜線指令的紀錄不算客戶訊息，上一則還是她貼的那則。"""
        p = self._jsonl([self._user("u1", None, "合約全文……"), self._ai("a1", "u1"),
                         self._user("i1", "a1", [{"type": "text", "text": "[Request interrupted by user]"}]),
                         self._user("c1", "i1", "<command-name>/cost</command-name>"),
                         self._user("u2", "c1", "存起來")])
        this, prev = intake.read_messages(p, prev=True)
        self.assertEqual((this["uuid"], prev["uuid"]), ("u2", "u1"))

    def test_previous_follows_parent_chain_not_file_order(self):
        """code review：退回、編輯後檔裡還留著被丟掉的那一支（u1），上一則照 parentUuid 是 u0。"""
        p = self._jsonl([self._user("u0", None, "第一段"), self._ai("a0", "u0"),
                         self._user("u1", "a0", "丟掉的那支"), self._ai("a1", "u1"),
                         self._user("u2", "a0", "存起來")])
        this, prev = intake.read_messages(p, prev=True)
        self.assertEqual((this["uuid"], prev["uuid"]), ("u2", "u0"))

    def test_previous_message_uploads_are_its_own(self):
        """code review：上一則的原圖是它跟這一則之間的 inlined_image_paths 附件；這一則的不混進去。"""
        img = {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                           "data": base64.b64encode((FIX / "名片.png").read_bytes()).decode()}}
        p = self._jsonl([self._user("u1", None, [img, {"type": "text", "text": "名片"}]),
                         {"type": "attachment", "uuid": "t1", "parentUuid": "u1",
                          "attachment": {"type": "inlined_image_paths", "paths": ["X/old.png"]}},
                         self._ai("a1", "t1"), self._user("u2", "a1", "存起來")])
        this, prev = intake.read_messages(p, prev=True)
        self.assertEqual((this["uploads"], prev["uploads"]), ([], ["X/old.png"]))
        self.assertEqual(intake.pasted_image(prev, 1)[2], "X/old.png")

    def test_only_this_message_does_not_read_further(self):
        p = self._jsonl([{"broken": True}, self._user("u2", None, "存起來")])
        self.assertEqual([m["uuid"] for m in intake.read_messages(p)], ["u2"])

    def test_parse_ref_prev(self):
        self.assertEqual(intake.parse_ref("prev:image:2"), ("image", 2, True))
        self.assertEqual(intake.parse_ref("text:1"), ("text", 1, False))
        self.assertEqual(intake.parse_ref("prev:x:1"), (None, None, False))

    def test_big_transcript_reads_backwards(self):
        tmp = Path(__file__).resolve().parent / "fixtures" / "intake"
        src = (tmp / "desktop.jsonl").read_text(encoding="utf-8").splitlines()
        filler = json.dumps({"type": "user", "uuid": "old", "message": {"role": "user", "content": "x" * 5000}})
        import tempfile
        d = Path(tempfile.mkdtemp(prefix="kbintake-"))
        try:
            p = d / "big.jsonl"
            p.write_text("\n".join([filler] * 300 + src) + "\n", encoding="utf-8")
            self.assertEqual(intake.read_message(p)["uuid"], "u2")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class Names(unittest.TestCase):
    def test_name_checks(self):
        for bad in ("a/b", "a\\b", "a:b", "a*b", 'a"b', "a<b", "a|b", "a$b", "a`b", "", "  "):
            with self.subTest(bad=bad), self.assertRaises(intake.Refused) as c:
                intake.check_name(bad)
            self.assertEqual(str(c.exception), intake.BAD_NAME)
        for bad in (".", "..", ".hidden", "~$x"):
            with self.subTest(bad=bad), self.assertRaises(intake.Refused):
                intake.check_name(bad)
        for bad in ("CON", "nul.txt", "COM1"):
            with self.subTest(bad=bad), self.assertRaises(intake.Refused):
                intake.check_name(bad)
        self.assertEqual(intake.check_name("王先生合約.jpg"), "王先生合約.jpg")

    def test_too_long_errors(self):
        """裁定 6 #5：路徑太長的幾種 OSError 都認得；一般的找不到路徑不算。"""
        import errno
        self.assertTrue(intake.too_long(OSError(errno.ENAMETOOLONG, "x")))
        e = FileNotFoundError(2, "x", "C:/" + "a" * 300)
        e.winerror = 3
        self.assertTrue(intake.too_long(e))
        short = FileNotFoundError(2, "x", "C:/a/b.pdf")
        short.winerror = 3
        self.assertFalse(intake.too_long(short))
        self.assertFalse(intake.too_long(PermissionError(13, "x", "C:/a")))
        with self.assertRaises(intake.Refused) as c:
            intake.check_name("字" * 256)
        self.assertEqual(str(c.exception), intake.TOO_LONG)

    def test_titled_name_keeps_original_extension(self):
        self.assertEqual(intake.titled("王先生合約", ".jpg"), "王先生合約.jpg")
        self.assertEqual(intake.titled("王先生合約.JPG", ".jpg"), "王先生合約.JPG")
        self.assertEqual(intake.titled("2026.10 報價", ".pdf"), "2026.10 報價.pdf")


if __name__ == "__main__":
    unittest.main()
