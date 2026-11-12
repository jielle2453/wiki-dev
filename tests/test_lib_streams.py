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

    def test_newer_format_reads_but_write_refused(self):
        """多人共用 2 第 4 點：讀容忍（認得的欄照算），寫之前 check_writable 才丟 NewerFormat（帶 app）。"""
        self.put("m-a", "agenda", {"v": 99, "app": "0.99.0", "op": "create", "id": "a-1", "seq": 1, "base": 0,
                                   "by": "m-a", "set": {"t": 1, "新欄": 2}})
        self.assertEqual(streams.load(self.V, "agenda").records["a-1"]["t"], 1)
        with self.assertRaises(streams.NewerFormat) as cm:
            streams.check_writable(self.V, "agenda")
        self.assertEqual(cm.exception.app, "0.99.0")
        with self.assertRaises(streams.NewerFormat):
            streams.write(self.V, "agenda", {}, {"a-2": {"t": 1}})

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

    def test_write_compacts_when_own_file_is_big(self):
        old = streams.COMPACT_BYTES
        streams.COMPACT_BYTES = 2000
        try:
            streams.write(self.V, "agenda", {}, {"a-1": {"t": 0}})
            for i in range(1, 40):
                streams.write(self.V, "agenda", {"a-1": {"t": i - 1}}, {"a-1": {"t": i}})
        finally:
            streams.COMPACT_BYTES = old
        lines = streams.own_file(self.V, "agenda").read_text(encoding="utf-8").splitlines()
        self.assertLess(len(lines), 40)
        self.assertEqual(streams.load(self.V, "agenda").records["a-1"]["t"], 39)

    def test_conflicts_of_for_json_output(self):
        self.put("m-a", "entities", {"op": "create", "id": "e-1", "seq": 1, "base": 0, "by": "m-a", "set": {"name": "X"}})
        self.put("m-a", "entities", {"op": "set", "id": "e-1", "seq": 2, "base": 1, "by": "m-a", "set": {"name": "甲"}})
        self.put("m-b", "entities", {"op": "set", "id": "e-1", "seq": 2, "base": 1, "by": "m-b", "set": {"name": "乙"}})
        got = streams.conflicts_of(self.V, "entities")
        self.assertEqual((got[0]["id"], got[0]["field"]), ("e-1", "name"))
        self.assertEqual(streams.conflicts_of(self.V, "agenda"), [])

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



class ProfileLocalSha(StreamsTest):
    """#42：設定檔 md 不進 git，md_sha256 每台自己記（.system/local/profile.json）；共用那份第一次建時帶著、之後不跟著改，讀時換成這台的。"""

    def test_local_sha_wins_and_shared_stays(self):
        doc = {"schema_version": 1, "types": [], "md_sha256": "aaa"}
        streams.write_doc(self.V, "profile", doc)
        self.assertEqual(streams.read_doc(self.V, "profile")["md_sha256"], "aaa")
        machine(self.V, "m-bbbb0002")  # 別台畫出另一個指紋：只記在它自己那一半，不寫共用流水檔
        streams.write_doc(self.V, "profile", dict(doc, md_sha256="bbb"))
        self.assertFalse((streams.stream_dir(self.V, "profile") / "m-bbbb0002.jsonl").exists())
        shared = [r.get("md_sha256") for r in streams.load(self.V, "profile").records.values()]
        self.assertEqual(shared, ["aaa"])
        self.assertEqual(streams.read_doc(self.V, "profile")["md_sha256"], "bbb")
        streams.write_doc(self.V, "profile", dict(doc, md_sha256="bbb", types=[{"name": "案子"}]))  # 別的欄照常進共用
        self.assertTrue((streams.stream_dir(self.V, "profile") / "m-bbbb0002.jsonl").exists())
        self.assertEqual([r.get("md_sha256") for r in streams.load(self.V, "profile").records.values()], ["aaa"])
        streams._write_local(self.V, "profile", {"md_sha256": None})  # 這台沒記過：用共用的
        self.assertEqual(streams.read_doc(self.V, "profile")["md_sha256"], "aaa")
        streams.write_doc(self.V, "profile", dict(doc, md_sha256=None))  # 清成 None（設定檔重建、沒有 md）：讀回 None
        self.assertIsNone(streams.read_doc(self.V, "profile")["md_sha256"])


class FormatVersion(StreamsTest):
    """記帳 1a（D-335）：流水檔格式版本跟大升級走（記帳 1a 升 2，#68 拿掉承諾升 3）；舊版讀到比它新的行照讀、要寫才擋（D-298）。"""

    def test_format_version_is_3_and_rows_carry_it(self):
        self.assertEqual(streams.FORMAT_VERSION, 3)
        streams.write(self.V, "agenda", {}, {"a-1": {"t": 1}})
        row = json.loads(streams.own_file(self.V, "agenda").read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(row["v"], 3)

    def test_v1_rows_still_read(self):
        self.put("m-a", "agenda", {"v": 1, "op": "create", "id": "a-1", "seq": 1, "base": 0, "by": "m-a", "set": {"t": 1}})
        self.assertEqual(streams.load(self.V, "agenda").records["a-1"], {"t": 1})
        streams.check_writable(self.V, "agenda")  # 舊的行不擋新版寫

    def test_old_program_refuses_to_write_after_newer_row(self):
        """格式 2 的舊程式（0.41.x）讀到 v3 的行照讀、寫之前停；格式 1（0.33.0）也一樣。"""
        from unittest import mock
        streams.write(self.V, "agenda", {}, {"a-1": {"t": 1}})
        for old in (1, 2):
            with self.subTest(old=old), mock.patch.object(streams, "FORMAT_VERSION", old):  # 舊版的 check_writable：同一套、格式版本 old
                self.assertEqual(streams.load(self.V, "agenda").records["a-1"]["t"], 1)
                with self.assertRaises(streams.NewerFormat) as cm:
                    streams.check_writable(self.V, "agenda")
                self.assertEqual(cm.exception.version, 3)


H0 = {"date": "2026-11-01", "change": "建立", "by": "ai", "turn": "t0"}
HA = {"date": "2026-11-03", "change": "date 11-25 → 11-26", "by": "ai", "turn": "tA"}
HB = {"date": "2026-11-02", "change": "加備註", "by": "ai", "turn": "tB"}


class AppendOnly(StreamsTest):
    """記帳 1a（D-337，B-530）：日程每筆的 history 只往後加；兩台各自加的行合起來都留、不算撞到，退回只拿掉自己那一行。"""

    A, B = "m-aaaa0001", "m-bbbb0002"

    def put(self, name, kind, *rows):  # 沒寫 v 的行當格式 2（新版寫的）
        super().put(name, kind, *[dict({"v": 2}, **r) if isinstance(r, dict) else r for r in rows])

    def test_v1_rows_read_as_before(self):
        """格式 1 的行照舊整份取代（0.34.0 以前的退回寫較短的清單，拿掉的那行不回來）；從格式 2 的行起合起來。"""
        self.put(self.A, "agenda", {"v": 1, "op": "create", "id": "a-1", "seq": 1, "base": 0, "by": self.A,
                                    "set": {"history": [H0]}},
                 {"v": 1, "op": "set", "id": "a-1", "seq": 2, "base": 1, "by": self.A, "set": {"history": [H0, HA]}},
                 {"v": 1, "op": "set", "id": "a-1", "seq": 3, "base": 2, "by": self.A, "set": {"history": [H0]},
                  "reverts": [{"kind": "agenda", "id": "a-1", "seq": 2, "by": self.A}]})
        self.assertEqual(streams.load(self.V, "agenda").records["a-1"]["history"], [H0])
        self.put(self.B, "agenda", {"op": "set", "id": "a-1", "seq": 4, "base": 3, "by": self.B, "set": {"history": [H0, HB]}})
        self.assertEqual(streams.load(self.V, "agenda").records["a-1"]["history"], [H0, HB])

    def seed(self):
        self.put(self.A, "agenda", {"v": 1, "op": "create", "id": "a-1", "seq": 1, "base": 0, "by": self.A,
                                    "set": {"date": "2026-11-25", "text": "開會", "history": [H0]}})
        self.put(self.A, "agenda", {"v": 2, "op": "set", "id": "a-1", "seq": 2, "base": 1, "by": self.A, "turn": "tA",
                                    "set": {"date": "2026-11-26", "history": [H0, HA]}})
        self.put(self.B, "agenda", {"v": 2, "op": "set", "id": "a-1", "seq": 2, "base": 1, "by": self.B, "turn": "tB",
                                    "set": {"note": "帶樣品", "history": [H0, HB]}})

    def test_registered(self):
        self.assertEqual(streams.APPEND_ONLY["agenda"], ("history",))

    def test_both_sides_kept_no_conflict_sorted_by_date(self):
        self.seed()
        st = streams.load(self.V, "agenda")
        self.assertEqual(st.conflicts, [])
        rec = st.records["a-1"]
        self.assertEqual(rec["history"], [H0, HB, HA])  # 照 date 排
        self.assertEqual((rec["date"], rec["note"]), ("2026-11-26", "帶樣品"))
        self.assertEqual(streams.conflicts_of(self.V, "agenda"), [])

    def test_same_date_then_by_version(self):
        h1 = dict(HB, date="2026-11-03", change="第二版加的")
        self.put(self.A, "agenda", {"op": "create", "id": "a-1", "seq": 1, "base": 0, "by": self.A, "set": {"history": [H0]}})
        self.put(self.B, "agenda", {"op": "set", "id": "a-1", "seq": 3, "base": 2, "by": self.B, "set": {"history": [H0, h1]}})
        self.put(self.A, "agenda", {"op": "set", "id": "a-1", "seq": 2, "base": 1, "by": self.A, "set": {"history": [H0, HA]}})
        self.assertEqual(streams.load(self.V, "agenda").records["a-1"]["history"], [H0, HA, h1])

    def test_same_element_only_once(self):
        self.seed()
        self.put(self.B, "agenda", {"op": "set", "id": "a-1", "seq": 3, "base": 2, "by": self.B,
                                    "set": {"history": [H0, HA, HB]}})
        self.assertEqual(streams.load(self.V, "agenda").records["a-1"]["history"], [H0, HB, HA])

    def test_other_list_fields_still_conflict(self):
        self.seed()
        self.put(self.A, "agenda", {"op": "set", "id": "a-1", "seq": 3, "base": 2, "by": self.A, "set": {"entities": ["甲"]}})
        self.put(self.B, "agenda", {"op": "set", "id": "a-1", "seq": 3, "base": 2, "by": self.B, "set": {"entities": ["乙"]}})
        self.assertEqual([c["field"] for c in streams.load(self.V, "agenda").conflicts], ["entities"])

    def test_other_kinds_unchanged(self):
        self.put(self.A, "entities", {"op": "create", "id": "e-1", "seq": 1, "base": 0, "by": self.A, "set": {"history": [1]}})
        self.put(self.A, "entities", {"op": "set", "id": "e-1", "seq": 2, "base": 1, "by": self.A, "set": {"history": [2]}})
        self.put(self.B, "entities", {"op": "set", "id": "e-1", "seq": 2, "base": 1, "by": self.B, "set": {"history": [3]}})
        self.assertEqual([c["field"] for c in streams.load(self.V, "entities").conflicts], ["history"])

    def test_line_effects_old_new_use_the_union(self):
        self.seed()
        self.put(self.B, "agenda", {"op": "set", "id": "a-1", "seq": 3, "base": 2, "by": self.B,
                                    "set": {"history": [H0, HA, HB, dict(HB, change="再加")]}})
        eff = streams.line_effects(self.V, "agenda", "a-1", 3, self.B)
        self.assertEqual(eff["old"]["history"], [H0, HB, HA])
        added = [h for h in eff["new"]["history"] if h not in eff["old"]["history"]]
        self.assertEqual([h["change"] for h in added], ["再加"])

    def test_revert_removes_only_own_line_and_field(self):
        self.seed()
        machine(self.V, self.A)
        eff = streams.line_effects(self.V, "agenda", "a-1", 2, self.A)
        streams.revert_line(self.V, "agenda", "a-1", eff, "t-undo")
        st = streams.load(self.V, "agenda")
        rec = st.records["a-1"]
        self.assertEqual(rec["history"], [H0, HB])
        self.assertEqual((rec["date"], rec["note"]), ("2026-11-25", "帶樣品"))
        self.assertEqual(st.conflicts, [])
        # B 台還沒看到這次退回、又寫了一行帶著 A 的那行：A 那行不會回來
        self.put(self.B, "agenda", {"op": "set", "id": "a-1", "seq": 3, "base": 2, "by": self.B,
                                    "set": {"history": [H0, HB, HA, dict(HB, change="再加")]}})
        got = streams.load(self.V, "agenda").records["a-1"]["history"]
        self.assertNotIn(HA, got)
        self.assertEqual([h["change"] for h in got], ["建立", "加備註", "再加"])

    def test_undo_of_revert_brings_line_back(self):
        self.seed()
        machine(self.V, self.A)
        streams.revert_line(self.V, "agenda", "a-1", streams.line_effects(self.V, "agenda", "a-1", 2, self.A), "t-undo")
        undo_row = json.loads(streams.own_file(self.V, "agenda").read_text(encoding="utf-8").splitlines()[-1])
        eff = streams.line_effects(self.V, "agenda", "a-1", undo_row["seq"], self.A)
        streams.revert_line(self.V, "agenda", "a-1", eff, "t-again")
        rec = streams.load(self.V, "agenda").records["a-1"]
        self.assertEqual(rec["history"], [H0, HB, HA])
        self.assertEqual(rec["date"], "2026-11-26")

    def test_later_lines_ignore_append_only(self):
        self.seed()
        self.put(self.B, "agenda", {"op": "set", "id": "a-1", "seq": 3, "base": 2, "by": self.B,
                                    "set": {"note": "改", "history": [H0, HA, HB, dict(HB, change="再加")]}})
        self.assertEqual(streams.later_lines(self.V, "agenda", "a-1", 2, ["date", "history"]), [])
        self.assertEqual(len(streams.later_lines(self.V, "agenda", "a-1", 2, ["note", "history"])), 1)


if __name__ == "__main__":
    unittest.main()
