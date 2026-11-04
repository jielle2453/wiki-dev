"""共用流水檔 streams（多人共用 1）：寫、合併、撞到、孤兒、截斷、新格式、快取、compact、purge 標記、整份文件轉換。"""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from kb._lib import env, streams  # noqa: E402


def machine(vault, name):
    """模擬換一台：env.json 這台的機器名與代號都換掉。"""
    env.machine_name = lambda: name
    env.set_machine_id(vault, name)


class StreamsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.V = Path(self._tmp.name)
        (self.V / ".system").mkdir()
        self._orig = env.machine_name
        machine(self.V, "m-aaaa0001")

    def tearDown(self):
        env.machine_name = self._orig
        self._tmp.cleanup()

    def put(self, name, kind, *rows):
        d = streams.stream_dir(self.V, kind)
        d.mkdir(parents=True, exist_ok=True)
        with open(d / f"{name}.jsonl", "a", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write((r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)) + "\n")

    def test_create_set_retract_roundtrip(self):
        streams.write(self.V, "agenda", {}, {"a-1": {"date": "11-25", "status": "open"}})
        streams.write(self.V, "agenda", {"a-1": {"date": "11-25", "status": "open"}}, {"a-1": {"date": "11-26", "status": "open"}})
        streams.write(self.V, "agenda", {"a-1": {"date": "11-26", "status": "open"}}, {})
        rows = [json.loads(x) for x in (streams.own_file(self.V, "agenda")).read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r["op"] for r in rows], ["create", "set", "set"])
        self.assertEqual([r["seq"] for r in rows], [1, 2, 3])
        self.assertEqual([r["base"] for r in rows], [0, 1, 2])
        self.assertEqual(rows[1]["set"], {"date": "11-26"})
        self.assertEqual(rows[2]["set"], {"_del": True})
        self.assertEqual(streams.read_doc(self.V, "agenda")["items"], [])

    def test_two_machines_different_fields_both_kept(self):
        self.put("m-a", "entities", {"op": "create", "id": "e-1", "seq": 1, "base": 0, "by": "m-a", "set": {"name": "X"}})
        self.put("m-a", "entities", {"op": "set", "id": "e-1", "seq": 2, "base": 1, "by": "m-a", "set": {"type": "客戶"}})
        self.put("m-b", "entities", {"op": "set", "id": "e-1", "seq": 2, "base": 1, "by": "m-b", "set": {"status": "removed"}})
        st = streams.load(self.V, "entities")
        self.assertEqual(st.records["e-1"], {"name": "X", "type": "客戶", "status": "removed"})
        self.assertEqual(st.conflicts, [])

    def test_conflict_same_field_both_sides_same_result(self):
        self.put("m-a", "entities", {"op": "create", "id": "e-1", "seq": 1, "base": 0, "by": "m-a", "set": {"name": "X"}})
        self.put("m-a", "entities", {"op": "set", "id": "e-1", "seq": 2, "base": 1, "by": "m-a", "set": {"name": "甲"}})
        self.put("m-b", "entities", {"op": "set", "id": "e-1", "seq": 2, "base": 1, "by": "m-b", "set": {"name": "乙"}})
        st = streams.load(self.V, "entities")
        self.assertEqual(len(st.conflicts), 1)
        self.assertEqual((st.conflicts[0]["id"], st.conflicts[0]["field"]), ("e-1", "name"))
        shown = streams.conflicts_json(st)
        self.assertEqual({v["value"] for v in shown[0]["values"]}, {"甲", "乙"})
        # 檔名順序不同（兩台各自算）取到同一個暫取值
        again = streams.load(self.V, "entities").records["e-1"]["name"]
        self.assertEqual(again, st.records["e-1"]["name"])

    def test_same_value_or_seen_is_not_conflict(self):
        self.put("m-a", "entities", {"op": "create", "id": "e-1", "seq": 1, "base": 0, "by": "m-a", "set": {"name": "X"}})
        self.put("m-a", "entities", {"op": "set", "id": "e-1", "seq": 2, "base": 1, "by": "m-a", "set": {"name": "甲"}})
        self.put("m-b", "entities", {"op": "set", "id": "e-1", "seq": 2, "base": 1, "by": "m-b", "set": {"name": "甲"}})
        self.assertEqual(streams.load(self.V, "entities").conflicts, [])
        self.put("m-b", "entities", {"op": "set", "id": "e-1", "seq": 3, "base": 2, "by": "m-b", "set": {"name": "丙"}})
        st = streams.load(self.V, "entities")
        self.assertEqual(st.conflicts, [])
        self.assertEqual(st.records["e-1"]["name"], "丙")

    def test_orphan_line_is_kept(self):
        self.put("m-b", "agenda", {"op": "set", "id": "a-9", "seq": 2, "base": 1, "by": "m-b", "set": {"date": "x"}})
        self.assertEqual(streams.load(self.V, "agenda").records["a-9"], {"date": "x"})

    def test_truncated_last_line_skipped_and_logged(self):
        self.put("m-a", "agenda", {"op": "create", "id": "a-1", "seq": 1, "base": 0, "by": "m-a", "set": {"t": 1}})
        d = streams.stream_dir(self.V, "agenda") / "m-a.jsonl"
        with open(d, "a", encoding="utf-8") as f:
            f.write('{"op": "set", "id": "a-1", "se')
        st = streams.load(self.V, "agenda")
        self.assertEqual(st.records["a-1"], {"t": 1})
        self.assertIn("不完整", (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8"))

    def test_newer_format_raises(self):
        self.put("m-a", "agenda", {"v": 99, "op": "create", "id": "a-1", "seq": 1, "base": 0, "by": "m-a", "set": {}})
        with self.assertRaises(streams.NewerFormat):
            streams.load(self.V, "agenda")

    def test_cache_not_recomputed(self):
        streams.write(self.V, "agenda", {}, {"a-1": {"t": 1}})
        streams.load(self.V, "agenda")
        n = streams.stats["merges"]
        streams.load(self.V, "agenda")
        streams.load(self.V, "agenda")
        self.assertEqual(streams.stats["merges"], n)
        streams.write(self.V, "agenda", {"a-1": {"t": 1}}, {"a-1": {"t": 2}})
        streams.load(self.V, "agenda")
        self.assertEqual(streams.stats["merges"], n + 1)

    def test_merge_speed_report(self):
        rows = []
        for m in range(10):
            lines = [json.dumps({"op": "create", "id": f"e-{m}-{i}", "seq": 1, "base": 0, "by": f"m-{m}", "set": {"name": f"n{i}", "type": "客戶"}})
                     for i in range(5000)]
            self.put(f"m-{m}", "entities", *lines)
        t = time.time()
        streams.load(self.V, "entities")
        took = time.time() - t
        print(f"[streams] 10 台 x 5000 行 entities 合併 {took:.2f} 秒（超過 0.5 秒要回報）")
        self.assertLess(took, 30)

    def test_compact_only_own_file(self):
        streams.write(self.V, "agenda", {}, {"a-1": {"t": 1}})
        streams.write(self.V, "agenda", {"a-1": {"t": 1}}, {"a-1": {"t": 2}})
        streams.write(self.V, "agenda", {"a-1": {"t": 2}}, {"a-1": {"t": 3}})
        self.put("m-other", "agenda", {"op": "set", "id": "a-1", "seq": 2, "base": 1, "by": "m-other", "set": {"u": 1}})
        before = (streams.stream_dir(self.V, "agenda") / "m-other.jsonl").read_text(encoding="utf-8")
        self.assertEqual(streams.compact(self.V, "agenda"), 1)
        self.assertEqual((streams.stream_dir(self.V, "agenda") / "m-other.jsonl").read_text(encoding="utf-8"), before)
        self.assertEqual(streams.load(self.V, "agenda").records["a-1"]["t"], 3)

    def test_mask_rewrites_own_lines(self):
        streams.write(self.V, "statements", {}, {"s-1": {"text": "祕密", "status": "active"}})
        streams.write_mask(self.V, "statements", ["s-1"], ["text"])
        raw = streams.own_file(self.V, "statements").read_text(encoding="utf-8")
        self.assertNotIn("祕密", raw)
        self.assertEqual(streams.load(self.V, "statements").records["s-1"]["text"], streams.MASKED)

    def test_doc_roundtrip_all_shapes(self):
        docs = {
            "statements": {"schema_version": 1, "statements": [{"id": "s-1", "text": "甲"}, {"id": "s-2", "text": "乙"}]},
            "set_aside": {"schema_version": 1, "keys": {"k1": {"at": "x"}}},
            "sources": {"schema_version": 1, "sources": [{"id": "src-1", "alias": "甲", "spec": "D:/x"}], "vault_excludes": []},
            "profile": {"schema_version": 3, "applied": None, "types": [{"name": "客戶"}],
                        "preferences": [{"text": "簡短", "use": "all"}, {"text": "禮貌", "use": "all"}]},
        }
        for kind, doc in docs.items():
            streams.write_doc(self.V, kind, doc)
            self.assertEqual(streams.read_doc(self.V, kind), doc, kind)

    def test_lazy_migrate_from_legacy_file(self):
        p = self.V / ".system" / "agenda.json"
        p.write_text(json.dumps({"schema_version": 1, "items": [{"id": "a-1", "text": "舊"}]}), encoding="utf-8")
        from kb._lib.io import read_json, write_json_atomic
        self.assertEqual(read_json(p)["items"][0]["text"], "舊")
        doc = read_json(p)
        doc["items"].append({"id": "a-2", "text": "新"})
        write_json_atomic(p, doc)
        self.assertTrue((self.V / ".system" / "legacy" / "agenda.json").is_file())
        self.assertEqual([i["id"] for i in read_json(p)["items"]], ["a-1", "a-2"])
        self.assertEqual(json.loads((self.V / ".system" / "legacy" / "agenda.json").read_text(encoding="utf-8"))["items"][0]["text"], "舊")
        self.assertEqual(len(json.loads(p.read_text(encoding="utf-8"))["items"]), 2)  # 衍生副本


class ArchiveField(StreamsTest):
    """驗收 7：封存不再搬檔，同一筆多一欄 archived；主清單不列、封存那一邊列。"""

    def test_archive_sets_field_and_restore_brings_back(self):
        from kb._lib import statements
        streams.write_doc(self.V, "statements", {"schema_version": 1, "statements": [
            {"id": "s-1", "text": "舊", "entities": ["X"], "status": "withdrawn", "replaced_by": None},
            {"id": "s-2", "text": "新", "entities": ["X"], "status": "active", "replaced_by": None}]})
        self.assertEqual(statements.archive(self.V, ["s-1"], "t-1"), 1)
        self.assertEqual([s["id"] for s in statements.load(self.V)["statements"]], ["s-2"])
        self.assertEqual([s["id"] for s in statements.load_archive(self.V)["statements"]], ["s-1"])
        self.assertTrue(streams.load(self.V, "statements").records["s-1"]["archived"])
        # 沒有另外一份封存流水檔，封存檔也沒被當正本寫
        self.assertEqual(sorted(p.name for p in (self.V / ".system" / "streams").iterdir()), ["statements"])

    def test_archive_view_edit_in_place_keeps_main(self):
        from kb._lib.io import read_json, write_json_atomic
        streams.write_doc(self.V, "findings", {"schema_version": 1, "findings": [
            {"id": "c-1", "text": "甲", "status": "withdrawn"}, {"id": "c-2", "text": "乙", "status": "active"}]})
        from kb._lib import findings
        findings.archive(self.V, ["c-1"], "t-1")
        arch = read_json(self.V / ".system" / "findings-archive.json")
        arch["findings"][0]["text"] = "甲改"
        write_json_atomic(self.V / ".system" / "findings-archive.json", arch)
        self.assertEqual([c["text"] for c in findings.load(self.V)["findings"]], ["乙"])
        self.assertEqual([c["text"] for c in findings.load_archive(self.V)["findings"]], ["甲改"])


if __name__ == "__main__":
    unittest.main()
