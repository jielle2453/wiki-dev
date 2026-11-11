"""#57 卡片索引（D-345）：card_index 的結果跟逐卡讀（cards._scan_groups_files）完全一樣、跟得上任何人改的、壞了照舊、不寫進知識庫。"""
import contextlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests import _cards  # noqa: F401  (sys.path)
from kb._lib import card_index, cards  # noqa: E402
from kb._lib import vault as vault_lib  # noqa: E402


def card(cid, title, body="內文", extra=""):
    return f"---\n編號: {cid}\n標題: {title}\n卡型: 報價\n{extra}---\n\n# {title}\n\n{body}\n"


def put(V, rel, text, mtime=None):
    p = Path(V) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8"))
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


OLD = time.time() - 7200  # 兩小時前：寫進索引時不算「剛改」


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="idx-test-"))
        self.V = self.tmp / "總資料夾"
        (self.V / ".system").mkdir(parents=True)
        self.idx = self.tmp / "index"
        self.vid = vault_lib.ensure_vault_id(self.V)
        env = mock.patch.dict(os.environ, {"WIKI_WITH_WILLY_INDEX_DIR": str(self.idx)})
        env.start()
        self.addCleanup(env.stop)
        card_index._logged = False
        card_index.LOCK_TIMEOUT = 0.3

    def tearDown(self):
        card_index.LOCK_TIMEOUT = 3
        shutil.rmtree(self.tmp, ignore_errors=True)

    def same(self):
        """索引讀的跟逐卡讀的一樣。"""
        got = card_index.groups(self.V)
        self.assertIsNotNone(got)
        self.assertEqual(got, cards._scan_groups_files(self.V))
        return got

    def put_many(self):
        put(self.V, "檔案索引/甲/一般.md", card("f-1", "一般報價", "交期三週"), OLD)
        put(self.V, "檔案索引/甲/壞檔頭.md", "---\n編號 f-2\n---\n內文\n", OLD)
        put(self.V, "檔案索引/甲/沒編號.md", card("f-3", "x").replace("編號: f-3\n", ""), OLD)
        put(self.V, "檔案索引/甲/編號壞.md", card("[a, b]", "y").replace("編號: [a, b]", "編號: [a, b]"), OLD)
        put(self.V, "檔案索引/乙/同一.md", card("f-5", "同編號一"), OLD)
        put(self.V, "檔案索引/乙/同二.md", card("f-5", "同編號二"), OLD)
        put(self.V, "檔案索引/乙/bom.md", "﻿" + card("f-6", "有 BOM"), OLD)
        put(self.V, "檔案索引/.隱藏/不算.md", card("f-7", "隱藏夾"), OLD)
        put(self.V, "檔案索引/乙/.不算.md", card("f-8", "隱藏檔"), OLD)
        put(self.V, "檔案索引/乙/大寫.MD", card("f-9", "大寫副檔名"), OLD)
        put(self.V, "檔案索引/乙/readme.txt", card("f-10", "不是 md"), OLD)
        put(self.V, "檔案索引/客戶案件/王先生/報價單_中文路徑.md", card("f-11", "中文路徑", "宏鑫精密 GS-1V-UE"), OLD)
        put(self.V, "檔案索引/亂碼.md", None or "x", OLD)
        (self.V / "檔案索引" / "亂碼.md").write_bytes(b"\xff\xfe\x00bad")


class Same(Base):
    def test_groups_equal_files(self):
        got = self.same()
        self.assertEqual(got[0], got[0])
        self.put_many()
        groups, broken = self.same()
        self.assertEqual(sorted(groups), ["f-1", "f-11", "f-5", "f-6", "f-9"])
        reasons = {b["path"].rsplit("/", 1)[1]: b["reason"] for b in broken}
        self.assertIn("檔頭解析不了", reasons["壞檔頭.md"])
        self.assertIn("檔頭解析不了", reasons["亂碼.md"])
        self.assertEqual(reasons["沒編號.md"], "檔頭少了「編號」")
        self.assertNotIn(".不算.md", reasons)

    def test_second_run_rereads_nothing(self):
        self.put_many()
        self.same()
        with mock.patch.object(cards, "parse_front", side_effect=AssertionError("不該重讀")):
            self.assertIsNotNone(card_index.groups(self.V))

    def test_front_types_survive_json(self):
        put(self.V, "檔案索引/a.md", card("f-1", "型別", extra="標籤: [a, b]\n實體:\n  - 王\n  - 李\n數字: 3\n"), OLD)
        self.same()
        self.same()  # 第二次是從索引讀出來的


class Follows(Base):
    def setUp(self):
        super().setUp()
        self.put_many()
        self.same()

    def test_edit_in_place(self):  # (a) Obsidian 手改
        put(self.V, "檔案索引/甲/一般.md", card("f-1", "一般報價", "交期五週也行"))
        self.assertEqual(self.same()[0]["f-1"][0]["front"]["標題"], "一般報價")
        self.assertEqual(card_index.body_hits(self.V, ["交期五週"])["交期五週"], {"檔案索引/甲/一般.md"})

    def test_add_delete_rename(self):  # (b)
        put(self.V, "檔案索引/新.md", card("f-20", "新卡"))
        self.assertIn("f-20", self.same()[0])
        os.rename(self.V / "檔案索引/新.md", self.V / "檔案索引/改名.md")
        self.assertEqual(self.same()[0]["f-20"][0]["path"], "檔案索引/改名.md")
        os.remove(self.V / "檔案索引/改名.md")
        self.assertNotIn("f-20", self.same()[0])

    def test_same_size_and_mtime_restored_right_after(self):  # (e) 只靠「剛改不到 2 秒」那條
        p = self.V / "檔案索引/乙/同一.md"
        # 這張是 OLD 寫進索引的；先讓它在索引裡變成「剛改過就記進去」的那種：把 mtime 設成現在再建一次
        os.utime(p, None)
        self.same()
        before = p.stat()
        text = p.read_text(encoding="utf-8").replace("同編號一", "同編號甲")  # 大小相同
        p.write_bytes(text.encode("utf-8"))
        os.utime(p, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(p.stat().st_size, before.st_size)
        got = self.same()
        self.assertEqual([c["front"]["標題"] for c in got[0]["f-5"]], ["同編號甲", "同編號二"])

    def test_same_size_after_two_seconds(self):  # (f)
        p = self.V / "檔案索引/甲/一般.md"
        size = p.stat().st_size
        later = time.time() - 3600
        p.write_bytes(p.read_bytes().replace("交期三週".encode(), "交期四週".encode()))
        os.utime(p, (later, later))
        self.assertEqual(p.stat().st_size, size)
        self.same()
        self.assertEqual(card_index.body_hits(self.V, ["交期四週"])["交期四週"], {"檔案索引/甲/一般.md"})

    def test_entity_rename_many_cards(self):  # (c) 改很多張的檔頭
        for i in range(5):
            put(self.V, f"檔案索引/多/{i}.md", card(f"f-3{i}", f"卡{i}", extra="實體: [舊名]\n"), OLD)
        self.same()
        for i in range(5):
            p = self.V / f"檔案索引/多/{i}.md"
            p.write_bytes(p.read_bytes().replace("舊名".encode(), "新名".encode()))
        groups = self.same()[0]
        self.assertTrue(all(groups[f"f-3{i}"][0]["front"]["實體"] == ["新名"] for i in range(5)))


class Hits(Base):
    def test_two_char_word_only_in_body(self):
        put(self.V, "檔案索引/a.md", card("f-1", "報價單", "交期：三週。Delivery GS-1V-UE"), OLD)
        put(self.V, "檔案索引/b.md", card("f-2", "別的", "沒有"), OLD)
        card_index.groups(self.V)
        got = card_index.body_hits(self.V, ["交期", "gs-1v-ue", "不存在"])
        self.assertEqual(got, {"交期": {"檔案索引/a.md"}, "gs-1v-ue": {"檔案索引/a.md"}, "不存在": set()})

    def test_none_before_groups_or_without_index(self):
        card_index._fresh.clear()
        put(self.V, "檔案索引/a.md", card("f-1", "報價單"), OLD)
        self.assertIsNone(card_index.body_hits(self.V, ["x"]))

    def test_body_matches_find_body(self):
        from kb._lib import find
        put(self.V, "檔案索引/a.md", "﻿" + card("f-1", "報價單", "ＡＢＣ　全形 Ｄ"), OLD)
        card_index.groups(self.V)
        hit = card_index.body_hits(self.V, ["abc 全形 d"])["abc 全形 d"]
        self.assertEqual(hit, {"檔案索引/a.md"})
        self.assertIn("abc 全形 d", find._body(self.V, "檔案索引/a.md"))

    def test_crlf_card_header_not_in_body(self):  # 實作疑義 5：手改成 CRLF 的卡，檔頭不當內文
        text = card("f-1", "報價單", "交期三週").replace("\n", "\r\n")
        put(self.V, "檔案索引/a.md", text, OLD)
        card_index.groups(self.V)
        self.assertEqual(card_index.body_hits(self.V, ["交期三週"])["交期三週"], {"檔案索引/a.md"})
        self.assertEqual(card_index.body_hits(self.V, ["卡型: 報價"])["卡型: 報價"], set())
        self.same()


class Unusable(Base):
    def setUp(self):
        super().setUp()
        self.put_many()
        self.same()
        self.db = card_index.db_path(self.V)

    def log_lines(self):
        p = self.V / ".system" / "hook-errors.log"
        return [l for l in p.read_text(encoding="utf-8").splitlines() if "\tindex\t" in l] if p.exists() else []

    def test_missing_file(self):
        os.remove(self.db)
        self.same()
        self.assertTrue(self.db.exists())

    def test_garbage_file_replaced(self):
        self.db.write_bytes(b"this is not a sqlite database" * 50)
        self.same()
        self.assertEqual(sqlite3.connect(self.db).execute("select v from meta where k='schema_version'").fetchone(), ("1",))

    def test_schema_version_2_replaced(self):
        con = sqlite3.connect(self.db)
        con.execute("update meta set v='2' where k='schema_version'")
        con.commit()
        con.close()
        self.same()
        con = sqlite3.connect(self.db)
        self.assertEqual(con.execute("select v from meta where k='schema_version'").fetchone(), ("1",))
        con.close()

    def test_locked_falls_back_and_does_not_write(self):
        put(self.V, "檔案索引/新.md", card("f-20", "新卡"), OLD)  # 有東西要寫
        con = sqlite3.connect(self.db, isolation_level=None)
        con.execute("BEGIN EXCLUSIVE")
        try:
            self.assertIsNone(card_index.groups(self.V))
            self.assertEqual(cards._scan_groups(self.V), cards._scan_groups_files(self.V))
        finally:
            con.execute("ROLLBACK")
            con.close()
        self.assertLessEqual(len(self.log_lines()), 1)
        self.same()  # 鎖放掉就補上
        con = sqlite3.connect(self.db)
        self.assertEqual(con.execute("select count(*) from cards where path='檔案索引/新.md'").fetchone(), (1,))
        con.close()

    def test_index_dir_not_writable_falls_back_and_logs_once(self):
        shutil.rmtree(self.idx, ignore_errors=True)
        self.idx.write_text("我是檔案不是夾")  # 建不了夾
        for _ in range(3):
            self.assertIsNone(card_index.groups(self.V))
            self.assertEqual(cards._scan_groups(self.V), cards._scan_groups_files(self.V))
        self.assertEqual(len(self.log_lines()), 1)

    def test_no_vault_id(self):
        os.remove(self.V / ".system" / "vault.json")
        self.assertIsNone(card_index.db_path(self.V))
        self.assertIsNone(card_index.groups(self.V))
        self.assertEqual(cards._scan_groups(self.V), cards._scan_groups_files(self.V))


class Place(Base):
    def test_db_path_per_vault(self):
        a = card_index.db_path(self.V)
        self.assertEqual(a.parent, self.idx)
        self.assertTrue(a.name.startswith(self.vid + "-") and a.name.endswith(".sqlite"))
        other = self.tmp / "另一個庫"
        (other / ".system").mkdir(parents=True)
        vault_lib.ensure_vault_id(other)
        self.assertNotEqual(card_index.db_path(other), a)

    def test_default_dir_is_localappdata(self):
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.tmp / "L")}):
            os.environ.pop("WIKI_WITH_WILLY_INDEX_DIR")
            self.assertEqual(card_index.db_path(self.V).parent, self.tmp / "L" / "wiki-with-willy" / "index")

    def test_nothing_new_in_vault(self):
        put(self.V, "檔案索引/a.md", card("f-1", "報價單"), OLD)
        before = sorted(str(p.relative_to(self.V)) for p in self.V.rglob("*"))
        card_index.groups(self.V)
        card_index.rebuild(self.V)
        card_index.body_hits(self.V, ["報價"])
        self.assertEqual(before, sorted(str(p.relative_to(self.V)) for p in self.V.rglob("*")))
        self.assertTrue(card_index.db_path(self.V).exists())


class Once(Base):
    def test_walks_once(self):
        put(self.V, "檔案索引/a.md", card("f-1", "報價單"), OLD)
        real = card_index.changed
        calls = []

        def counting(*a, **k):
            calls.append(1)
            return real(*a, **k)

        with mock.patch.object(card_index, "changed", counting):
            with card_index.once(self.V):
                for _ in range(5):
                    cards._scan_groups(self.V)
                    cards.active_cards(self.V)
            self.assertEqual(len(calls), 1)
            cards._scan_groups(self.V)
            self.assertEqual(len(calls), 2)  # 離開之後還原
        self.assertEqual(cards._scan_groups, cards._scan_groups)

    def test_returns_copies(self):
        put(self.V, "檔案索引/a.md", card("f-1", "報價單"), OLD)
        with card_index.once(self.V):
            g, b = cards._scan_groups(self.V)
            g.clear()
            self.assertIn("f-1", cards._scan_groups(self.V)[0])


class Rebuild(Base):
    def test_rebuild(self):
        self.put_many()
        n, secs = card_index.rebuild(self.V)
        self.assertEqual(n, len(cards._walk_cards(self.V)))
        self.assertGreaterEqual(secs, 0)

    def test_rebuild_unusable_raises(self):
        os.remove(self.V / ".system" / "vault.json")
        with self.assertRaises(card_index.Unusable):
            card_index.rebuild(self.V)


class Deadline(Base):
    def test_timeout_saves_what_was_read(self):
        for i in range(10):
            put(self.V, f"檔案索引/{i}.md", card(f"f-{i}", f"卡{i}"), OLD)
        with self.assertRaises(TimeoutError):
            card_index.groups(self.V, time.monotonic() - 1)
        card_index.groups(self.V)  # 沒設時限的補完

    def test_partial_progress_kept(self):
        for i in range(10):
            put(self.V, f"檔案索引/{i}.md", card(f"f-{i}", f"卡{i}"), OLD)
        real = cards.parse_front
        seen = []

        def slow(text):
            seen.append(1)
            if len(seen) == 4:
                time.sleep(0.5)  # 第 4 張讀完時限就過了
            return real(text)

        with mock.patch.object(cards, "parse_front", slow):
            with self.assertRaises(TimeoutError):
                card_index.groups(self.V, time.monotonic() + 0.3)
        con = sqlite3.connect(card_index.db_path(self.V))
        self.assertEqual(con.execute("select count(*) from cards").fetchone(), (4,))
        con.close()


if __name__ == "__main__":
    unittest.main()
