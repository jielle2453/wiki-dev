"""kb cards sync 沒變動提早結束（#71 C-8，驗收 5）：沒有要搬、要刪的卡時不跑 plan.build、回傳跟整份走相同；
有 moved、duplicates、卡式要補時照舊、結果跟整份走（_sync_all）相同。"""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import _cards
from kb._lib import cards, inventory, plan, streams, turn  # noqa: E402
from kb._lib import sources as sources_lib  # noqa: E402

EMPTY = {"moved": [], "updated": [], "dropped": [], "skipped": [], "changed": [], "touched": []}


class SyncFast(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _cards.make_card_vault()
        fid = _cards.entry_of(self.V, _cards.MEETING)["id"]
        self.item = next(i for i in cards.todo(self.V, sources_lib.load(self.V))["new"] if i["id"] == fid)
        self.card = _cards.write_card(self.V, self.item, "大安陳會議一")
        self.copies = []

    def tearDown(self):
        streams.forget()
        for d in [self.tmp] + self.copies:
            shutil.rmtree(d, ignore_errors=True)

    def twin(self):
        """整個暫存夾（知識庫與原檔）複製一份：同樣的狀態各跑一次新舊路徑。"""
        other = Path(tempfile.mkdtemp())
        self.copies.append(other)
        shutil.copytree(self.tmp, other, dirs_exist_ok=True)
        return other / Path(self.V).relative_to(self.tmp)

    def run_both(self, builds_expected):
        V2 = self.twin()
        with mock.patch.object(plan, "build", wraps=plan.build) as m:
            got = cards.sync(self.V, sources_lib.load(self.V), turn.start(self.V, None, "")["turn"])
        streams.forget()
        want = cards._sync_all(V2, sources_lib.load(V2), turn.start(V2, None, "")["turn"])
        self.assertEqual(got, want)
        if builds_expected:
            self.assertGreaterEqual(m.call_count, 1)
        else:
            self.assertEqual(m.call_count, 0)
        return got

    def test_nothing_to_do_skips_plan(self):
        self.assertEqual(self.run_both(builds_expected=False), EMPTY)

    def test_nothing_to_do_writes_nothing(self):
        before = {p: p.read_bytes() for p in Path(self.V, cards.CARDS_DIR).rglob("*.md")}
        cards.sync(self.V, sources_lib.load(self.V), turn.start(self.V, None, "")["turn"])
        self.assertEqual({p: p.read_bytes() for p in Path(self.V, cards.CARDS_DIR).rglob("*.md")}, before)

    def test_moved_goes_full_way(self):
        dst = self.raw / "客戶案件" / "信義王" / "會議紀錄_1.docx"
        dst.parent.mkdir(exist_ok=True)
        (self.raw / _cards.MEETING).rename(dst)
        _cards.scan_apply(self.V)
        got = self.run_both(builds_expected=True)
        self.assertEqual(len(got["moved"]), 1)

    def test_duplicates_go_full_way(self):
        wrong = self.V / "檔案索引" / "客戶案件" / "信義王" / self.card.name
        wrong.parent.mkdir(parents=True)
        wrong.write_text(self.card.read_text(encoding="utf-8"), encoding="utf-8")
        got = self.run_both(builds_expected=True)
        self.assertEqual(got["dropped"], [wrong.relative_to(self.V).as_posix()])

    def test_front_sync_still_runs_without_moves(self):
        fid = self.item["id"]
        inventory.set_card_mode(self.V, fid, "pointer", None, turn.start(self.V, None, "")["turn"])
        got = self.run_both(builds_expected=False)
        self.assertEqual([c["path"] for c in got["changed"]], [self.card.relative_to(self.V).as_posix()])


if __name__ == "__main__":
    unittest.main()
