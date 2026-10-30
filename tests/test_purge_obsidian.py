"""purge 連 Obsidian 的痕跡一起清（Obsidian 首頁，#22，D-262）。驗收準則 13：workspace.json 與外掛 data.json 裡指到那夾的卡拿掉、
其他留著；成功句多一行；carried 照字詞遮罩。真的 exclude --kind hidden 再 purge。"""
import json
import shutil
import unittest
from pathlib import Path

from tests import test_lib_purge as P
from kb._lib import agenda, renders, turn  # noqa: E402

DIARY, kb = P.DIARY, P.kb

LINE = "Obsidian 自己的快取在知識庫外面，下次打開 Obsidian 會自己丟掉"


class ObsidianTraces(unittest.TestCase):
    setUp, tearDown = P.Purge.setUp, P.Purge.tearDown
    write_synthesis, exclude = P.Purge.write_synthesis, P.Purge.exclude

    def put(self, rel, data):
        p = Path(self.V) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    def run_purge(self):
        turn.start(self.V, None, "不要讀私人那夾")
        code, out = self.exclude()
        self.assertEqual(code, 0, out)
        self.write_synthesis("信義王現在很好。")
        code, out = kb("folders", "purge", "客戶案件/私人", "--vault", str(self.V))
        self.assertEqual(code, 0, out)
        return out

    def leaf(self, file, kind="markdown"):
        return {"id": "x" + file[-6:], "type": "leaf", "state": {"type": kind, "state": {"file": file}}}

    def workspace(self):
        mine = self.card_rel
        other = "檔案索引/客戶案件/內湖李/內湖李估價-aaaaaaaa.md"
        return {
            "main": {"id": "m", "type": "split", "children": [
                {"id": "t1", "type": "tabs", "children": [self.leaf(mine), self.leaf(other), self.leaf("系統/日程.md")]}]},
            "left": {"id": "l", "type": "split", "children": [{"id": "t2", "type": "tabs", "children": [self.leaf(mine, "file-explorer")]}]},
            "right": {"id": "r", "type": "split", "children": []},
            "active": "t1",
            "lastOpenFiles": [mine, other, "系統/日程.md", f"檔案索引/客戶案件/私人/別張卡-{self.fid[2:]}.md"],
        }, other

    def test_workspace_and_data_cleaned_others_kept(self):
        ws, other = self.workspace()
        wp = self.put(".obsidian/workspace.json", ws)
        dp = self.put(".obsidian/plugins/wiki-with-willy/data.json",
                      {"opened": [{"card": self.fid, "at": "2026-10-30T09:00:00"}, {"card": self.keep_fid, "at": "2026-10-30T09:05:00"}]})
        out = self.run_purge()
        got = json.loads(wp.read_text(encoding="utf-8"))
        self.assertEqual(got["lastOpenFiles"], [other, "系統/日程.md"])
        files = []

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "leaf":
                    files.append(node["state"]["state"]["file"])
                for c in node.get("children") or []:
                    walk(c)
        for part in ("main", "left", "right"):
            walk(got[part])
        self.assertEqual(sorted(files), sorted([other, "系統/日程.md"]))
        self.assertEqual(got["active"], "t1", "其他的欄位不動")
        self.assertEqual(json.loads(dp.read_text(encoding="utf-8")), {"opened": [{"card": self.keep_fid, "at": "2026-10-30T09:05:00"}]})
        line = out.splitlines()[-2]  # 在快照那句前面
        self.assertTrue(line.endswith(LINE), out)
        self.assertRegex(line, r"^Obsidian 裡清了：工作區 \d+ 處、外掛最近 1 筆；")
        self.assertNotIn("書籤", line, "沒有書籤檔就不提")
        self.assertNotIn(DIARY, wp.read_text(encoding="utf-8"))

    def bookmarks(self):
        mine = self.card_rel
        other = "檔案索引/客戶案件/內湖李/內湖李估價-aaaaaaaa.md"
        return {"items": [
            {"type": "file", "ctime": 1, "path": mine, "title": "我的"},
            {"type": "file", "ctime": 2, "path": other},
            {"type": "group", "ctime": 3, "title": "常看", "items": [
                {"type": "file", "ctime": 4, "path": mine}, {"type": "file", "ctime": 5, "path": "系統/日程.md"}]},
            {"type": "folder", "ctime": 6, "path": "檔案索引/客戶案件/私人"},
            {"type": "search", "ctime": 7, "query": "報價"},
            {"type": "url", "ctime": 8, "url": "https://example.com"},
        ]}, other

    def test_15_bookmarks_cleaned_groups_included_others_kept(self):
        data, other = self.bookmarks()
        bp = self.put(".obsidian/bookmarks.json", data)
        out = self.run_purge()
        got = json.loads(bp.read_text(encoding="utf-8"))
        self.assertEqual([i.get("path") or i.get("query") or i.get("url") or i["title"] for i in got["items"]],
                         [other, "常看", "報價", "https://example.com"])
        (group,) = [i for i in got["items"] if i["type"] == "group"]
        self.assertEqual([i["path"] for i in group["items"]], ["系統/日程.md"])
        line = out.splitlines()[-2]
        self.assertRegex(line, r"書籤 3 個")
        self.assertTrue(line.endswith(LINE), out)

    def test_15_unreadable_bookmarks_left_alone_and_counted(self):
        bp = Path(self.V) / ".obsidian" / "bookmarks.json"
        bp.parent.mkdir(parents=True)
        bp.write_text("{壞掉", encoding="utf-8")
        turn.start(self.V, None, "不要讀私人那夾")
        self.exclude()
        self.write_synthesis("信義王現在很好。")
        code, out = kb("folders", "purge", "客戶案件/私人", "--vault", str(self.V))
        self.assertEqual(bp.read_text(encoding="utf-8"), "{壞掉")
        self.assertEqual(code, 3, out)
        self.assertIn("狀態檔", out)

    def test_15_sentence_unchanged_when_nothing_in_obsidian_to_clean(self):
        out = self.run_purge()
        self.assertEqual(out.splitlines()[-2], LINE)

    def test_unreadable_workspace_left_alone_and_counted(self):
        wp = Path(self.V) / ".obsidian" / "workspace.json"
        wp.parent.mkdir(parents=True)
        wp.write_text("{壞掉", encoding="utf-8")
        turn.start(self.V, None, "不要讀私人那夾")
        self.exclude()
        self.write_synthesis("信義王現在很好。")
        code, out = kb("folders", "purge", "客戶案件/私人", "--vault", str(self.V))
        self.assertEqual(wp.read_text(encoding="utf-8"), "{壞掉")
        self.assertEqual(code, 3, out)  # 沒清完：還剩狀態檔
        self.assertIn("狀態檔", out)

    def test_missing_obsidian_files_are_fine(self):
        out = self.run_purge()
        self.assertIn(LINE, out)
        self.assertFalse((Path(self.V) / ".obsidian").exists())

    def test_carried_with_the_words_dropped_others_kept(self):
        V = self.V
        t = turn.start(V, None, "")["turn"]
        renders.add_carried(V, "系統/日程.md", [{"kind": "added", "text": f"問一下{DIARY}的事", "orig": None},
                                              {"kind": "added", "text": "跟廠商約時間", "orig": None},
                                              {"kind": "changed", "text": "改過的", "orig": f"原本提到{DIARY}"}])
        agenda.refresh_md(V, t)
        self.assertIn(DIARY, (Path(V) / "系統" / "日程.md").read_text(encoding="utf-8"))
        self.run_purge()
        left = [c["text"] for c in renders.carried(V, "系統/日程.md")]
        self.assertEqual(left, ["跟廠商約時間"])
        md = (Path(V) / "系統" / "日程.md").read_text(encoding="utf-8")
        self.assertNotIn(DIARY, md)
        self.assertIn("跟廠商約時間", md)


if __name__ == "__main__":
    unittest.main()
