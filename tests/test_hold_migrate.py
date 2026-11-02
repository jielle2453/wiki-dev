"""放寬甲第二輪 13（D-324）：收件匣與 AI 產出合成暫存區的升級遷移（_lib/hold_migrate，migrate.py 的遷移表一列，kb upgrade --finish 跑）。

fixture 是舊版的知識庫：收件匣/a.pdf、AI 產出/b.docx、AI 產出/a.pdf（內容跟收件匣那份不同）、AI 產出/c.md（跟收件匣/c.md 內容一樣），
都有清冊條目與檔案卡，綜合卡連到 a 與 b。驗：改名、兩夾並存、同名內容一樣、同名內容不同留在 AI 產出（left_in_output）、
清冊 uri 與卡搬家（編號不變）、總目錄與綜合卡連結、再跑一次不做事、開場那行。
"""
import json
import shutil
import unittest
from pathlib import Path

from tests import _cards, _entities
from kb._lib import cards, hold_migrate, inventory, migrate, synthesis, turn  # noqa: E402
from kb._lib import sources as sources_lib  # noqa: E402

OLD_FILES = {"收件匣/a.pdf": b"inbox a", "收件匣/c.md": b"same c", "收件匣/來源/價目.xlsx": b"periodic",
             "AI 產出/b.docx": b"output b", "AI 產出/a.pdf": b"output a is different", "AI 產出/c.md": b"same c"}


def inv(V):
    return json.loads((Path(V) / ".system" / "inventory.json").read_text(encoding="utf-8"))["entries"]


def entry(V, uri):
    return next(e for e in inv(V) if any(l["uri"] == uri for l in e["locations"]))


def by_uri(V, uri):
    return next((e for e in inv(V) if any(l["uri"] == uri for l in e["locations"])), None)


class Base(unittest.TestCase):
    both = False  # True：使用者自己開過叫暫存區的夾

    def setUp(self):
        self.tmp, self.V, self.raw = _entities.make_entity_vault(with_entities=True)
        V = self.V
        shutil.rmtree(V / "暫存區")  # fixture 是新骨架；這題要舊版的樣子
        self.t = turn.start(V, None, "")["turn"]
        self.ids = {}
        for rel, body in OLD_FILES.items():
            p = V / rel
            origin_out = rel.startswith("AI 產出/")
            if origin_out:
                turn.backup(V, rel, self.t)  # manifest 記 create，register_output 才肯登記
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body)
            e = inventory.register_output(V, rel, self.t) if origin_out else inventory.register_intake(V, rel, self.t, {})
            self.ids[rel] = e["id"]
        for rel, title in (("收件匣/a.pdf", "收件甲"), ("收件匣/c.md", "收件丙"), ("AI 產出/b.docx", "產出乙"),
                           ("AI 產出/a.pdf", "產出甲"), ("AI 產出/c.md", "產出丙")):
            self.card_of_rel = getattr(self, "card_of_rel", {})
            self.card_of_rel[rel] = _entities.write_card(V, rel, title, ["大安陳"])
        synthesis.render_cache(V, ["大安陳"], self.t)
        cards.render_index(V, self.t)
        if self.both:
            (V / "暫存區").mkdir()
        self.t2 = turn.start(V, None, "升級")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def card_front(self, fid):
        for p in (self.V / "檔案索引").rglob("*.md"):
            front = cards.parse_front(p.read_text(encoding="utf-8"))
            if front.get("編號") == fid:
                return p.relative_to(self.V).as_posix(), front
        return None, None


class Rename(Base):
    def test_rename_when_only_inbox_and_full_migration(self):
        V = self.V
        before_ids = sorted(e["id"] for e in inv(V))
        got = hold_migrate.rewrite(V, self.t2)
        # 收件匣整個改名、AI 產出併進去
        self.assertFalse((V / "收件匣").exists())
        self.assertEqual((V / "暫存區" / "a.pdf").read_bytes(), b"inbox a")  # 原收件匣那份
        self.assertEqual((V / "暫存區" / "b.docx").read_bytes(), b"output b")
        self.assertEqual((V / "暫存區" / "c.md").read_bytes(), b"same c")
        self.assertTrue((V / "暫存區" / "來源" / "價目.xlsx").is_file())
        # 同名內容不同：不搬，留在 AI 產出，結果列 left_in_output
        self.assertEqual((V / "AI 產出" / "a.pdf").read_bytes(), b"output a is different")
        self.assertEqual(got["left_in_output"], [{"name": "a.pdf", "existing": "file://暫存區/a.pdf"}])
        self.assertEqual(sorted(p.relative_to(V / "AI 產出").as_posix() for p in (V / "AI 產出").rglob("*")), ["a.pdf"])
        # 同名內容一樣：AI 產出那份拿掉、回合有備份、清冊那筆 duplicate_of
        self.assertFalse((V / "AI 產出" / "c.md").exists())
        self.assertTrue((V / ".system/versions" / self.t2 / "files" / "AI 產出" / "c.md").is_file())
        dup = next(e for e in inv(V) if e["id"] == self.ids["AI 產出/c.md"])
        self.assertEqual(dup["duplicate_of"], self.ids["收件匣/c.md"])
        self.assertEqual(dup["status"], "deleted")
        # 清冊 uri 換成暫存區、編號不變
        self.assertEqual(sorted(e["id"] for e in inv(V)), before_ids)
        self.assertEqual(entry(V, "file://暫存區/a.pdf")["id"], self.ids["收件匣/a.pdf"])
        self.assertEqual(entry(V, "file://暫存區/b.docx")["id"], self.ids["AI 產出/b.docx"])
        self.assertEqual(entry(V, "file://暫存區/來源/價目.xlsx")["id"], self.ids["收件匣/來源/價目.xlsx"])
        self.assertEqual(entry(V, "file://AI 產出/a.pdf")["id"], self.ids["AI 產出/a.pdf"])  # 沒搬的位置照舊
        self.assertEqual(entry(V, "file://暫存區/b.docx")["origin"], "ai_output")  # 出處類別是誰放的，不變
        self.assertEqual(entry(V, "file://暫存區/a.pdf")["origin"], "intake")

    def test_cards_move_with_same_ids_and_links_follow(self):
        V = self.V
        hold_migrate.rewrite(V, self.t2)
        for rel, new_uri in (("收件匣/a.pdf", "file://暫存區/a.pdf"), ("AI 產出/b.docx", "file://暫存區/b.docx"),
                             ("收件匣/c.md", "file://暫存區/c.md")):
            path, front = self.card_front(self.ids[rel])
            self.assertIsNotNone(path, rel)
            self.assertTrue(path.startswith("檔案索引/暫存區/"), path)
            self.assertEqual(front["原檔"], [new_uri])
        path, front = self.card_front(self.ids["AI 產出/a.pdf"])  # 沒搬的檔，卡也不動
        self.assertTrue(path.startswith("檔案索引/AI 產出/"), path)
        self.assertFalse(list((V / "檔案索引" / "收件匣").glob("**/*.md")) if (V / "檔案索引" / "收件匣").exists() else [])
        index = (V / "總目錄.md").read_text(encoding="utf-8")
        self.assertIn("檔案索引/暫存區/", index)
        self.assertNotIn("檔案索引/收件匣/", index)
        # 綜合卡快取跟上：照卡編號列檔案卡（卡搬了、編號沒變，連結點得到）；同名拿掉的那份（deleted）不再列
        text = (V / "案子" / "大安陳" / "大安陳.md").read_text(encoding="utf-8")
        for rel in ("收件匣/a.pdf", "收件匣/c.md", "AI 產出/b.docx", "AI 產出/a.pdf"):
            self.assertIn(self.ids[rel], text, rel)
        self.assertNotIn(self.ids["AI 產出/c.md"], text)
        for rel in ("收件匣/a.pdf", "AI 產出/b.docx"):
            self.assertTrue((V / self.card_front(self.ids[rel])[0]).is_file())
        todo = cards.todo(V, sources_lib.load(V))  # 沒有要重做的、沒有位置對不上的
        self.assertEqual([i["id"] for i in todo["moved"]], [])
        for rel in ("收件匣/a.pdf", "AI 產出/b.docx"):
            self.assertNotIn(self.ids[rel], [i["id"] for i in todo["new"] + todo["stale"]])

    def test_second_run_does_nothing(self):
        V = self.V
        hold_migrate.rewrite(V, self.t2)
        self.assertFalse(hold_migrate.needs(V))  # 留下的同名不同內容的檔不算動作
        again = turn.start(V, None, "再跑")["turn"]
        snap = {p.relative_to(V).as_posix(): p.read_bytes() for p in V.rglob("*") if p.is_file()
                and ".system/versions" not in p.as_posix() and ".system/turns" not in p.as_posix()}
        got = hold_migrate.rewrite(V, again)
        self.assertEqual((got["notes"], got["left_in_output"]), ([], [{"name": "a.pdf", "existing": "file://暫存區/a.pdf"}]))
        after = {p.relative_to(V).as_posix(): p.read_bytes() for p in V.rglob("*") if p.is_file()
                 and ".system/versions" not in p.as_posix() and ".system/turns" not in p.as_posix()}
        self.assertEqual(after, snap)

    def test_session_line_counts_leftovers(self):
        V = self.V
        self.assertEqual(hold_migrate.left_count(V), 0)  # 還沒有暫存區：不講
        hold_migrate.rewrite(V, self.t2)
        self.assertEqual(hold_migrate.left_count(V), 1)
        import importlib.util
        spec = importlib.util.spec_from_file_location("session_hook_hold", Path(__file__).resolve().parents[1] / "hooks" / "session.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        line = mod.line_hold_left(V)
        self.assertEqual(line, "升級後「AI 產出」還有 1 份跟暫存區同名、內容不同：照內容判斷取代或另取名，用 kb source-edit move 搬進暫存區，做完說一聲。")
        (V / "AI 產出" / "a.pdf").unlink()  # 搬完（或處理掉）就不再講
        self.assertIsNone(mod.line_hold_left(V))


class BothFolders(Base):
    both = True

    def test_inbox_merged_into_existing_hold(self):
        """兩個夾都有（使用者自己開過叫暫存區的夾）：收件匣的東西照同名規則併進去，不是整夾改名。"""
        V = self.V
        (V / "暫存區" / "c.md").write_bytes(b"different from inbox")  # 使用者自己放的同名檔
        got = hold_migrate.rewrite(V, self.t2)
        self.assertEqual((V / "暫存區" / "c.md").read_bytes(), b"different from inbox")  # 內容不同：不蓋
        self.assertEqual((V / "收件匣" / "c.md").read_bytes(), b"same c")
        self.assertEqual((V / "暫存區" / "a.pdf").read_bytes(), b"inbox a")
        self.assertTrue((V / "暫存區" / "來源" / "價目.xlsx").is_file())
        self.assertIn({"name": "c.md", "existing": "file://暫存區/c.md"}, got["left_in_output"])
        self.assertEqual(entry(V, "file://暫存區/a.pdf")["id"], self.ids["收件匣/a.pdf"])
        self.assertEqual(entry(V, "file://收件匣/c.md")["id"], self.ids["收件匣/c.md"])  # 沒搬的位置照舊


class TableAndFinish(Base):
    def test_migration_table_row_and_apply(self):
        V = self.V
        pend = [m for m in migrate.STATE_FILES if m.rel == hold_migrate.REL]
        self.assertEqual(len(pend), 1)
        self.assertTrue(any(p["rel"] == hold_migrate.REL for p in migrate.pending(V)))
        got = migrate.apply(V, self.t2)
        self.assertIn(hold_migrate.REL, got["migrated"])
        self.assertTrue(any("暫存區" in n for n in got["notes"]))
        self.assertEqual(got["left_in_output"], [{"name": "a.pdf", "existing": "file://暫存區/a.pdf"}])
        self.assertFalse(any(p["rel"] == hold_migrate.REL for p in migrate.pending(V)))  # 再跑一次不做事
        again = migrate.apply(V, self.t2)
        self.assertNotIn(hold_migrate.REL, again["migrated"])

    def test_nothing_to_do_on_new_vault(self):
        shutil.rmtree(self.V / "收件匣")
        shutil.rmtree(self.V / "AI 產出")
        (self.V / "暫存區").mkdir()
        self.assertFalse(hold_migrate.needs(self.V))
        self.assertFalse(any(p["rel"] == hold_migrate.REL for p in migrate.pending(self.V)))


if __name__ == "__main__":
    unittest.main()
