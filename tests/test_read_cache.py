"""讀檔快取（#71，D-548 (3)）：同一個 process 內 streams.read_doc、inventory.load 記住結果；
命中不讀檔、回複本；寫過或外部改過就重讀；kb lookup、kb cards todo 的 --json 加快取前後逐位元組相同。"""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import _cards
from tests import _entities as E
from tests.test_lib_lookup import write_card
from kb import cli
from kb._lib import env, inventory, streams, turn  # noqa: E402


def bump(path):
    """外部改檔：內容一樣、只動 mtime（size 不變也要認得）。"""
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))


class ReadDocCache(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.V = Path(self._tmp.name)
        (self.V / ".system").mkdir()
        self._orig = env.machine_name
        env.machine_name = lambda: "m-aaaa0001"
        env.set_machine_id(self.V, "m-aaaa0001")
        streams.forget()
        streams.write(self.V, "agenda", {}, {"a-1": {"date": "11-25", "status": "open"}})
        streams.forget()

    def tearDown(self):
        streams.forget()
        env.machine_name = self._orig
        self._tmp.cleanup()

    def test_a_second_call_does_not_read(self):
        with mock.patch.object(streams, "load", wraps=streams.load) as m:
            first = streams.read_doc(self.V, "agenda")
            second = streams.read_doc(self.V, "agenda")
        self.assertEqual(m.call_count, 1)
        self.assertEqual(first, second)

    def test_b_caller_edits_do_not_leak(self):
        doc = streams.read_doc(self.V, "agenda")
        doc["items"][0]["date"] = "改掉"
        doc["items"].append({"id": "a-x"})
        again = streams.read_doc(self.V, "agenda")
        self.assertEqual([i["date"] for i in again["items"]], ["11-25"])

    def test_c_write_doc_then_new_value(self):
        doc = streams.read_doc(self.V, "agenda")
        doc["items"][0]["date"] = "11-30"
        streams.write_doc(self.V, "agenda", doc)
        self.assertEqual(streams.read_doc(self.V, "agenda")["items"][0]["date"], "11-30")

    def test_c_write_then_new_value(self):
        streams.read_doc(self.V, "agenda")
        streams.write(self.V, "agenda", {"a-1": {"date": "11-25", "status": "open"}}, {"a-1": {"date": "12-01", "status": "open"}})
        self.assertEqual(streams.read_doc(self.V, "agenda")["items"][0]["date"], "12-01")

    def test_c_archive_view_follows_base_write(self):
        streams.write(self.V, "statements", {}, {"s-1": {"text": "甲"}})
        self.assertEqual(streams.read_doc(self.V, "statements_archive")["statements"], [])
        streams.write(self.V, "statements", {"s-1": {"text": "甲"}}, {"s-1": {"text": "甲", "archived": "2026-11-19"}})
        self.assertEqual([s["id"] for s in streams.read_doc(self.V, "statements_archive")["statements"]], ["s-1"])

    def test_d_external_stream_change(self):
        streams.read_doc(self.V, "agenda")
        row = {"v": streams.FORMAT_VERSION, "op": "create", "id": "a-2", "seq": 1, "base": 0, "by": "m-bbbb0002",
               "set": {"date": "12-24", "status": "open"}}
        other = streams.stream_dir(self.V, "agenda") / "m-bbbb0002.jsonl"
        other.write_text(json.dumps(row) + "\n", encoding="utf-8")
        self.assertEqual(sorted(i["id"] for i in streams.read_doc(self.V, "agenda")["items"]), ["a-1", "a-2"])

    def test_d_external_mtime_only(self):
        streams.read_doc(self.V, "agenda")
        bump(streams.own_file(self.V, "agenda"))
        with mock.patch.object(streams, "load", wraps=streams.load) as m:
            streams.read_doc(self.V, "agenda")
        self.assertEqual(m.call_count, 1)

    def test_d_external_mirror_edit_absorbed(self):
        streams.read_doc(self.V, "agenda")
        legacy = self.V / streams.legacy_rel("agenda")
        doc = json.loads(legacy.read_text(encoding="utf-8"))
        doc["items"][0]["date"] = "手改"
        legacy.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(streams.read_doc(self.V, "agenda")["items"][0]["date"], "手改")

    def test_local_half_change(self):
        streams.write_doc(self.V, "pending", {"schema_version": 1, "items": []})
        self.assertEqual(streams.read_doc(self.V, "pending")["items"], [])
        streams._write_local(self.V, "pending", {"p-1": {"id": "p-1", "kind": "missing_file"}})
        self.assertEqual([i["id"] for i in streams.read_doc(self.V, "pending")["items"]], ["p-1"])

    def test_key_uses_absolute_path(self):
        cwd = os.getcwd()
        try:
            os.chdir(self.V.parent)
            with mock.patch.object(streams, "load", wraps=streams.load) as m:
                streams.read_doc(self.V, "agenda")
                streams.read_doc(Path(self.V.name), "agenda")
            self.assertEqual(m.call_count, 1)
        finally:
            os.chdir(cwd)


class InventoryCache(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, _raw = _cards.make_card_vault()
        streams.forget()

    def tearDown(self):
        streams.forget()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_second_call_does_not_read(self):
        with mock.patch.object(inventory, "read_json", wraps=inventory.read_json) as m:
            first = inventory.load(self.V)
            second = inventory.load(self.V)
        self.assertEqual(m.call_count, 1)
        self.assertEqual(first, second)
        self.assertTrue(first["entries"])

    def test_b_caller_edits_do_not_leak(self):
        inv = inventory.load(self.V)
        n = len(inv["entries"])
        inv["entries"][0]["status"] = "改掉"
        inv["entries"].append({"id": "x"})
        again = inventory.load(self.V)
        self.assertEqual(len(again["entries"]), n)
        self.assertNotEqual(again["entries"][0]["status"], "改掉")

    def test_c_write_then_new_value(self):
        inv = inventory.load(self.V)
        fid = inv["entries"][0]["id"]
        inv["entries"][0]["note"] = "新值"
        inventory._write(self.V, inv["entries"])
        got = next(e for e in inventory.load(self.V)["entries"] if e["id"] == fid)
        self.assertEqual(got.get("note"), "新值")

    def test_d_external_change(self):
        inventory.load(self.V)
        if streams.exists(self.V, "inventory"):
            target = streams.own_file(self.V, "inventory")
        else:
            target = self.V / inventory.INVENTORY_REL
        bump(target)
        with mock.patch.object(inventory, "read_json", wraps=inventory.read_json) as m:
            inventory.load(self.V)
        self.assertEqual(m.call_count, 1)


@contextlib.contextmanager
def no_cache():
    """每次讀之前都清掉：等於沒有快取。"""
    rd, ld = streams.read_doc, inventory.load

    def rd2(*a, **k):
        streams.forget()
        return rd(*a, **k)

    def ld2(*a, **k):
        streams.forget()
        return ld(*a, **k)

    with mock.patch.object(streams, "read_doc", rd2), mock.patch.object(inventory, "load", ld2):
        yield


class SameOutput(unittest.TestCase):
    """驗收 2：同一份 fixture，加快取前後 --json 逐位元組相同。"""

    def kb(self, V, *args):
        cwd = os.getcwd()
        out = io.StringIO()
        streams.forget()
        try:
            os.chdir(V)
            with contextlib.redirect_stdout(out):
                code = cli.main(list(args))
        finally:
            os.chdir(cwd)
            streams.forget()
        self.assertIn(code, (0, None), out.getvalue())
        return out.getvalue()

    def compare(self, V, *args):
        with no_cache():
            before = self.kb(V, *args)
        after = self.kb(V, *args)
        self.assertTrue(before.strip())
        self.assertEqual(before.encode("utf-8"), after.encode("utf-8"))

    def test_lookup(self):
        tmp, V, _raw = E.make_entity_vault(with_entities=True)
        try:
            turn.start(V, None, "")
            write_card(V, E.QUOTE, "信義王報價第二版", ["信義王"], date="2026-10-01")
            self.compare(V, "lookup", "信義王", "--json")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cards_todo(self):
        tmp, V, _raw = _cards.make_card_vault()
        try:
            self.compare(V, "cards", "todo", "--json")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
