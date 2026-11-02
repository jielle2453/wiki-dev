"""放寬甲第二輪 12（D-325）：定期抓的內容記位置。kb intake <檔> --from <來源> --name <項目> [--to <夾>/<檔名>]：
第一次 --to 指定放哪（AI 照 D-309 判斷），之後同來源同項目不帶 --to 就寫回那份「現在的位置」（使用者或 AI 搬過的，清冊已跟上）；
那份被刪了照記的位置寫回（restored_place）；沒登記過又猜不到不帶 --to 落 暫存區/<來源>/<項目>；目的地已有同名、不是這個來源交的回 conflict。
驗收 33、34。"""
import os
import shutil
from pathlib import Path
from unittest import mock

from tests.test_lib_source_edit import Base, entry, inv
from kb._lib import intake, inventory, turn  # noqa: E402
from kb._lib import source_edit as se  # noqa: E402
from kb._lib import sources as sources_lib  # noqa: E402

PLACE = "05 廠商/大同/價目表.xlsx"


class Periodic(Base):
    def setUp(self):
        super().setUp()
        self.dl = self.tmp / "下載"
        self.dl.mkdir()
        self.n = 0

    def deliver(self, body, to=None, name="價目表", from_="官網", fname="價目.xlsx", t=None, **kw):
        src = self.dl / fname
        src.write_bytes(body)
        return intake.receive(self.V, str(src), t or self.t, str(self.V), from_=from_, name=name, to=to, **kw)

    def periodic_entries(self, name="價目表"):
        return [e for e in inv(self.V)["entries"] if (e.get("intake") or {}).get("name") == name]

    def test_33_first_with_to_then_overwrite_same_place_keeps_id_and_backs_up(self):
        got = self.deliver(b"v1", to=PLACE)
        place = self.V / "05 廠商" / "大同" / "價目表.xlsx"
        self.assertEqual((place.read_bytes(), got["result"]), (b"v1", "new"))
        e = self.periodic_entries()[0]
        self.assertEqual((e["intake"]["from"], e["intake"]["name"], e["locations"][0]["uri"]),
                         ("官網", "價目表", "file://知識庫/05 廠商/大同/價目表.xlsx"))
        t2 = turn.start(self.V, None, "再抓")["turn"]
        again = self.deliver(b"v2", t=t2)  # 不帶 --to：寫回現在的位置
        self.assertEqual((place.read_bytes(), again["result"]), (b"v2", "updated"))
        after = self.periodic_entries()
        self.assertEqual([x["id"] for x in after], [e["id"]])  # 清冊編號不變
        self.assertEqual((self.V / ".system/versions" / t2 / "files" / "05 廠商" / "大同" / "價目表.xlsx").read_bytes(), b"v1")  # 回合有舊版
        same = self.deliver(b"v2", t=t2)
        self.assertEqual(same["result"], "same")  # 內容一樣不動

    def test_33_after_move_writes_new_place(self):
        self.deliver(b"v1", to=PLACE)
        t2 = turn.start(self.V, None, "整理")["turn"]
        old = self.V / "05 廠商" / "大同" / "價目表.xlsx"
        dest = self.V / "05 廠商" / "大同" / "價目"
        dest.mkdir()
        p = se.plan_move(self.V, sources_lib.load(self.V), str(old), str(self.V), dest=str(dest))
        se.do_move(self.V, p, t2, "move")
        t3 = turn.start(self.V, None, "再抓")["turn"]
        self.deliver(b"v2", t=t3)
        self.assertFalse(old.exists())
        self.assertEqual((dest / "價目表.xlsx").read_bytes(), b"v2")
        self.assertEqual(len(self.periodic_entries()), 1)

    def test_33_to_differs_moves_then_overwrites(self):
        self.deliver(b"v1", to=PLACE)
        t2 = turn.start(self.V, None, "以後放到別處")["turn"]
        (self.V / "05 廠商" / "二廠").mkdir()
        self.deliver(b"v2", to="05 廠商/二廠/價目表.xlsx", t=t2)
        self.assertFalse((self.V / "05 廠商" / "大同" / "價目表.xlsx").exists())
        self.assertEqual((self.V / "05 廠商" / "二廠" / "價目表.xlsx").read_bytes(), b"v2")
        self.assertEqual(len(self.periodic_entries()), 1)

    def test_33_trashed_is_written_back_with_restored_place(self):
        self.deliver(b"v1", to=PLACE)
        t2 = turn.start(self.V, None, "刪掉")["turn"]
        place = self.V / "05 廠商" / "大同" / "價目表.xlsx"
        with mock.patch.object(se, "recycle_room", return_value=(0, 10 ** 9)), \
                mock.patch.object(se, "shell_trash", side_effect=os.remove):
            tp = se.plan_trash(self.V, sources_lib.load(self.V), str(place), str(self.V))
            se.do_trash(self.V, tp, t2)
        self.assertFalse(place.exists())
        t3 = turn.start(self.V, None, "再抓")["turn"]
        got = self.deliver(b"v3", t=t3)
        self.assertEqual((place.read_bytes(), got.get("restored_place")), (b"v3", True))
        self.assertIn("寫回去了", got["said"])

    def test_34_unknown_goes_to_hold_by_source_and_name(self):
        got = self.deliver(b"%PDF", name="型錄", fname="型錄.pdf")
        self.assertEqual((self.V / "暫存區" / "官網" / "型錄.pdf").read_bytes(), b"%PDF")
        self.assertEqual(got["path"], "暫存區/官網/型錄.pdf")
        self.assertNotIn("restored_place", got)

    def test_34_same_name_not_from_this_source_is_conflict(self):
        d = self.V / "05 廠商" / "大同"
        d.mkdir(parents=True)
        (d / "價目表.xlsx").write_bytes(b"someone else's")
        with self.assertRaises(intake.Conflict) as cm:
            self.deliver(b"v1", to=PLACE)
        row = cm.exception.rows[0]
        self.assertEqual((row["name"], row["same_content"]), ("價目表.xlsx", False))
        self.assertEqual((d / "價目表.xlsx").read_bytes(), b"someone else's")

    def test_hold_is_default_for_plain_intake(self):
        src = self.dl / "合約.pdf"
        src.write_bytes(b"%PDF contract")
        got = intake.receive(self.V, str(src), self.t, str(self.V))
        self.assertEqual(got["path"], "暫存區/合約.pdf")
        self.assertTrue((self.V / "暫存區" / "合約.pdf").is_file())
        self.assertEqual(inventory.entry_for(self.V, "file://暫存區/合約.pdf")["origin"], "intake")
