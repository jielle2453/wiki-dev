"""她手改了卡，系統跟著更新（D-270）：card_base 基準、kb cards edits、各寫入點不誤報、退回與搬家（驗收 1、3～6、9）。
寫入點盤點（會改卡內文或卡的位置的 kb 地方）：
  A 實體改名 rename（正文標題換新名、綜合卡搬位置）          → test_rename_*
  B kb cards sync（檔案卡跟著原檔搬）                       → test_cards_sync_rekeys
  C 實體合併 merge、拿掉 remove、kb cards drop／skip（卡刪掉） → test_deleted_cards_not_listed
  D 只改檔頭的寫入（標籤行、實體欄、整理到、快取重渲染、遷移）→ test_front_only_writes_not_listed
  E kb versions revert（換回舊版、或拿掉新卡）               → test_revert_*
  F Z5、Z1 的 PostToolUse                                  → tests/test_hooks_output_log.py"""
import json
import shutil
import unittest
from pathlib import Path

from tests import _cards, _entities
from tests._guard_fixture import make_vault
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import card_base, turn  # noqa: E402

SID = "test-sid"
FILE_CARD = "檔案索引/公司行政/報稅時程表-647d76ee.md"
FILE_TEXT = ("---\n編號: f-647d76ee\n標題: 報稅時程表\n卡型: 表單\n實體: [信義王]\n標籤: [舊]\n---\n"
             "# 報稅時程表\n\n- 總價 5.5 萬〔第 1 段〕\n- 交屋 12 月〔第 2 段〕\n")
SYN_CARD = "案子/王宅/王宅.md"
SYN_TEXT = ("---\n編號: e-0f3e9a21\n型別: 案子\n名稱: 王宅\n標籤: [舊]\n---\n"
            "# 王宅\n\n## 現況\n- 施工中〔f-647d76ee〕\n")


def put(V, rel, text):
    p = Path(V) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")
    return p


class Body(unittest.TestCase):
    def test_body_of(self):
        self.assertEqual(card_base.body_of("---\na: 1\n---\n# T\n"), "# T\n")
        self.assertEqual(card_base.body_of("---\r\na: 1\r\n---\r\n# T\r\n"), "# T\n")
        self.assertEqual(card_base.body_of("沒有檔頭\n"), "沒有檔頭\n")

    def test_strip_files_whole_line_only(self):
        """裁定 24：記號要整行才算（同 synthesis._span）；行中間的記號字串是內文，照留。"""
        from kb._lib import synthesis
        inline = "- 2026-10-30 備註 " + synthesis.FILE_BEGIN + " x〔f-00000001〕\n"
        body = "# T\n\n## 紀事\n" + inline + "- 2026-10-01 甲\n"
        self.assertEqual(card_base.strip_files(body), body)
        files = "　" + synthesis.FILE_BEGIN + "\n## 相關檔\n- [[a.md|甲]]\n" + synthesis.FILE_END + "\n"
        self.assertEqual(card_base.strip_files(body + "\n" + files + "\n## 備註\n二\n"), body + "\n## 備註\n二\n")

    def test_files_in_middle_keep_blank_line(self):
        """D-523 疑義裁定 1：相關檔夾在推算與紀事中間，補上或拿掉那段，body_of 一樣（後面還有字就空一行接）。"""
        from kb._lib import synthesis
        text = "---\na: 1\n---\n# T\n\n## 現況\n- 一\n\n## 推算\n- 二\n\n## 紀事\n- 2026-10-01 甲\n"
        files = synthesis.FILE_BEGIN + "\n## 相關檔\n- [[a.md|甲]]\n" + synthesis.FILE_END
        got = synthesis.with_file_section(text, files)
        self.assertIn(synthesis.FILE_END + "\n\n## 紀事", got)
        self.assertEqual(card_base.body_of(got), card_base.body_of(text))
        self.assertEqual(card_base.body_of(text + "\n" + files + "\n"), card_base.body_of(text), "在最後照舊")

    def test_hunks_add_and_delete(self):
        self.assertEqual(card_base.hunks("a\nb\n", "a\nb\nc\n"), [{"before": "", "after": "c"}])
        self.assertEqual(card_base.hunks("a\nb\nc", "a\nc"), [{"before": "b", "after": ""}])
        self.assertEqual(card_base.hunks("a\nb\nc", "a\nB\nc"), [{"before": "b", "after": "B"}])


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        put(self.V, FILE_CARD, FILE_TEXT)
        put(self.V, SYN_CARD, SYN_TEXT)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kb(self, *args):
        return run_kb(*args, cwd=self.V)

    def paths(self):
        return [e["path"] for e in card_base.edits(self.V)["edits"]]

    def cli_edits(self):
        r = self.kb("cards", "edits", "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)


class FirstRun(Base):
    def test_no_base_no_edits_then_every_card_has_base(self):
        """驗收 1：沒有 card_base.json 不報手改；跑過一次每張卡都有基準。"""
        self.assertFalse((self.V / card_base.BASE_POSIX).exists())
        self.assertEqual(card_base.edits(self.V), {"edits": [], "more": False})
        recs = json.loads((self.V / card_base.BASE_POSIX).read_text(encoding="utf-8"))
        self.assertEqual(recs["schema_version"], 1)
        self.assertEqual(set(recs["cards"]), {FILE_CARD, SYN_CARD})
        self.assertEqual(recs["cards"][FILE_CARD]["body"], card_base.body_of(FILE_TEXT))
        self.assertEqual(recs["cards"][FILE_CARD]["sha256"], card_base.sha(card_base.body_of(FILE_TEXT)))

    def test_card_without_record_gets_baseline_even_when_others_have_one(self):
        card_base.record(self.V, FILE_CARD)
        put(self.V, SYN_CARD, SYN_TEXT.replace("施工中", "改過了"))  # 沒紀錄的卡：現在的內容當基準
        self.assertEqual(self.paths(), [])
        self.assertIn(SYN_CARD, card_base.load(self.V))

    def test_broken_state_file_is_no_record(self):
        (self.V / ".system").mkdir(exist_ok=True)
        (self.V / card_base.BASE_POSIX).write_text("{壞掉", encoding="utf-8")
        self.assertEqual(card_base.edits(self.V)["edits"], [])
        self.assertEqual(set(card_base.load(self.V)), {FILE_CARD, SYN_CARD})

    def test_cli_first_run_silent(self):
        r = self.kb("cards", "edits")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "沒有你改過的卡"), r.stderr)


class Detect(Base):
    def setUp(self):
        super().setUp()
        card_base.edits(self.V)  # 補基準

    def test_hand_edit_listed_with_hunks(self):
        """驗收 4：一般寫檔改一行內文，列出那張，hunks 的 before／after 對。"""
        put(self.V, FILE_CARD, FILE_TEXT.replace("總價 5.5 萬", "總價 6 萬"))
        got = self.cli_edits()
        self.assertEqual(got["more"], False)
        (item,) = got["edits"]
        self.assertEqual({k: item[k] for k in ("path", "kind", "id", "title", "entities")},
                         {"path": FILE_CARD, "kind": "file", "id": "f-647d76ee", "title": "報稅時程表",
                          "entities": ["信義王"]})
        self.assertEqual(item["hunks"], [{"before": "- 總價 5.5 萬〔第 1 段〕", "after": "- 總價 6 萬〔第 1 段〕"}])

    def test_synthesis_edit_listed(self):
        put(self.V, SYN_CARD, SYN_TEXT + "- 交屋延到 12 月\n")
        (item,) = self.cli_edits()["edits"]
        self.assertEqual((item["path"], item["kind"], item["entity"]), (SYN_CARD, "synthesis", "王宅"))
        self.assertEqual(item["hunks"], [{"before": "", "after": "- 交屋延到 12 月"}])

    def test_front_only_edit_not_listed(self):
        put(self.V, FILE_CARD, FILE_TEXT.replace("標籤: [舊]", "標籤: [新]"))
        put(self.V, SYN_CARD, SYN_TEXT.replace("標籤: [舊]", "標籤: [新, 另一個]"))
        self.assertEqual(self.cli_edits(), {"edits": [], "more": False})

    def test_crlf_save_is_not_an_edit(self):
        put(self.V, FILE_CARD, FILE_TEXT)
        (self.V / FILE_CARD).write_bytes(FILE_TEXT.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(self.paths(), [])

    def test_deleted_card_not_listed(self):
        (self.V / FILE_CARD).unlink()
        self.assertEqual(self.paths(), [])

    def test_cli_human_text_lists_path(self):
        put(self.V, FILE_CARD, FILE_TEXT.replace("12 月", "1 月"))
        r = self.kb("cards", "edits")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(FILE_CARD, r.stdout)
        self.assertIn("- 交屋 12 月〔第 2 段〕", r.stdout)
        self.assertIn("- 交屋 1 月〔第 2 段〕", r.stdout)

    def test_deadline_passed_sets_more(self):
        put(self.V, FILE_CARD, FILE_TEXT.replace("12 月", "1 月"))
        got = card_base.edits(self.V, deadline=-1)
        self.assertEqual(got, {"edits": [], "more": True})

    def test_read_only_when_persist_false(self):
        base = (self.V / card_base.BASE_POSIX).read_bytes()
        put(self.V, "檔案索引/新卡-aaaaaaaa.md", FILE_TEXT)
        card_base.edits(self.V, persist=False)
        self.assertEqual((self.V / card_base.BASE_POSIX).read_bytes(), base)


class Done(Base):
    def setUp(self):
        super().setUp()
        card_base.edits(self.V)
        put(self.V, FILE_CARD, FILE_TEXT.replace("5.5 萬", "6 萬"))

    def test_done_clears(self):
        """驗收 6：--done 之後不列。"""
        r = self.kb("cards", "edits", "--done", FILE_CARD)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "記下了（1 張）"), r.stderr)
        self.assertEqual(self.cli_edits(), {"edits": [], "more": False})

    def test_done_not_a_card_refused(self):
        for bad in ("案子/不存在/不存在.md", "暫存區/x.md", "檔案索引/沒有這張-11111111.md"):
            r = self.kb("cards", "edits", "--done", bad)
            self.assertNotEqual(r.returncode, 0, bad)
            self.assertIn("不是卡", r.stdout)
        self.assertEqual(self.paths(), [FILE_CARD])  # 拒絕時什麼都沒換

    def test_done_refuses_whole_batch(self):
        r = self.kb("cards", "edits", "--done", FILE_CARD, "案子/不存在/不存在.md")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.paths(), [FILE_CARD])


class Rename(Base):
    """A 實體改名：搬位置、正文標題換新名，都是程式改的，不算她改。"""

    def setUp(self):
        self.tmp, self.V, self.raw = _entities.make_entity_vault(with_entities=True)
        self.old = "案子/信義王/信義王.md"
        self.new = "案子/王宅邸/王宅邸.md"

    def test_entity_remove_forgets_card(self):
        """C：拿掉實體、綜合卡刪掉，紀錄跟著刪。"""
        card_base.edits(self.V)
        self.assertIn(self.old, card_base.load(self.V))
        r = self.kb("entity", "remove", "信義王")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(self.old, card_base.load(self.V))
        self.assertEqual(self.cli_edits(), {"edits": [], "more": False})

    def test_rename_rekeys_and_not_listed(self):
        """驗收 9、3（A）。"""
        card_base.edits(self.V)
        self.assertIn(self.old, card_base.load(self.V))
        r = self.kb("entity", "rename", "信義王", "--to", "王宅邸")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        recs = card_base.load(self.V)
        self.assertNotIn(self.old, recs)
        self.assertIn(self.new, recs)
        self.assertIn("# 王宅邸", recs[self.new]["body"])  # 基準是改完標題的那一版
        self.assertEqual(self.cli_edits(), {"edits": [], "more": False})

    def test_rename_keeps_pending_hand_edit(self):
        """她改了還沒處理就改名：基準不換，她那行仍列得出來。"""
        card_base.edits(self.V)
        p = self.V / self.old
        p.write_text(p.read_text(encoding="utf-8") + "- 交屋延到 12 月\n", encoding="utf-8", newline="\n")
        self.assertEqual(self.kb("entity", "rename", "信義王", "--to", "王宅邸").returncode, 0)
        (item,) = self.cli_edits()["edits"]
        self.assertEqual(item["path"], self.new)
        self.assertIn({"before": "", "after": "- 交屋延到 12 月"}, item["hunks"])

    def test_moved_without_rekey_is_healed_by_content(self):
        """退回夾名這類沒人換鍵的搬家：內文一樣的一筆舊紀錄認作同一張。"""
        card_base.edits(self.V)
        (self.V / "案子" / "信義王").rename(self.V / "案子" / "王宅邸")
        (self.V / "案子" / "王宅邸" / "信義王.md").rename(self.V / self.new)
        self.assertEqual(self.paths(), [])
        recs = card_base.load(self.V)
        self.assertIn(self.new, recs)
        self.assertNotIn(self.old, recs)


class CardsSync(Base):
    """B 檔案卡跟著原檔搬：換鍵；改的只有檔頭。"""

    def test_rekey_unit(self):
        card_base.edits(self.V)
        new = "檔案索引/新夾/報稅時程表-647d76ee.md"
        put(self.V, new, FILE_TEXT)
        (self.V / FILE_CARD).unlink()
        card_base.rekey(self.V, FILE_CARD, new)
        self.assertEqual(self.paths(), [])
        self.assertNotIn(FILE_CARD, card_base.load(self.V))


class FrontOnly(Base):
    def test_front_only_writes_not_listed(self):
        """D：實體欄、標籤行、整理到、快取重渲染等只動檔頭的寫入，內文位元組不動，基準不用換。"""
        from kb._lib import cards, synthesis
        card_base.edits(self.V)
        put(self.V, FILE_CARD, cards.rewrite_entities((self.V / FILE_CARD).read_text(encoding="utf-8"), ["信義王", "王宅"]))
        put(self.V, SYN_CARD, synthesis.replace_front((self.V / SYN_CARD).read_text(encoding="utf-8"),
                                                       {"標籤": ["X"]}))
        self.assertEqual(self.paths(), [])


class Deleted(Base):
    """C 卡刪掉（merge、remove、cards drop／skip、purge）：不列；同位置重建的新卡當新卡補基準。"""

    def test_deleted_cards_not_listed(self):
        card_base.edits(self.V)
        card_base.forget(self.V, FILE_CARD)
        (self.V / FILE_CARD).unlink()
        self.assertEqual(self.paths(), [])
        self.assertNotIn(FILE_CARD, card_base.load(self.V))
        put(self.V, FILE_CARD, FILE_TEXT.replace("5.5 萬", "7 萬"))  # 重建：新卡
        self.assertEqual(self.paths(), [])


class Revert(Base):
    """E 退回：基準跟著換回那一版。"""

    def claude_edits_synthesis(self):
        card_base.edits(self.V)
        t = turn.start(self.V, SID, "更新王宅")
        turn.backup(self.V, SYN_CARD, t["turn"])
        put(self.V, SYN_CARD, SYN_TEXT + "- Claude 加的一點\n")
        card_base.record(self.V, SYN_CARD)  # Z1 的 PostToolUse 記的
        self.assertEqual(self.paths(), [])
        return t

    def test_revert_claude_change_not_listed(self):
        """驗收 5。"""
        self.claude_edits_synthesis()
        turn.start(self.V, SID, "退回上一版")
        r = self.kb("versions", "revert")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.V / SYN_CARD).read_text(encoding="utf-8"), SYN_TEXT)
        self.assertEqual(self.cli_edits(), {"edits": [], "more": False})
        self.assertEqual(card_base.load(self.V)[SYN_CARD]["body"], card_base.body_of(SYN_TEXT))

    def test_revert_new_card_forgets_it(self):
        card_base.edits(self.V)
        t = turn.start(self.V, SID, "建一張")
        new = "案子/新案/新案.md"
        turn.backup(self.V, new, t["turn"])
        put(self.V, new, SYN_TEXT.replace("王宅", "新案"))
        card_base.record(self.V, new)
        turn.start(self.V, SID, "退回上一版")
        self.assertEqual(self.kb("versions", "revert").returncode, 0)
        self.assertFalse((self.V / new).exists())
        self.assertNotIn(new, card_base.load(self.V))


if __name__ == "__main__":
    unittest.main()
