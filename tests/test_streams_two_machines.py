"""多人共用 1 驗收 2、3、5、7、15 的一部分：兩台模擬（換機器名）與真的 git（兩份 clone 各記各的、push／pull 沒有衝突）。"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from kb._lib import env, streams  # noqa: E402
from kb._lib.io import read_json, write_json_atomic  # noqa: E402

GIT = shutil.which("git")


def as_machine(vault, name):
    env.machine_name = lambda: name
    env.set_machine_id(vault, "m-" + name)


def add_item(vault, kind_file, list_key, rec):
    p = Path(vault) / ".system" / kind_file
    doc = read_json(p) or {"schema_version": 1, list_key: []}
    doc[list_key].append(rec)
    write_json_atomic(p, doc)


def edit_item(vault, kind_file, list_key, rid, **fields):
    p = Path(vault) / ".system" / kind_file
    doc = read_json(p)
    for it in doc[list_key]:
        if it["id"] == rid:
            it.update(fields)
    write_json_atomic(p, doc)


class TwoMachines(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.V = self.tmp / "v"
        (self.V / ".system").mkdir(parents=True)
        self._orig = env.machine_name

    def tearDown(self):
        env.machine_name = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_each_machine_writes_only_its_own_file(self):
        as_machine(self.V, "aaaa")
        add_item(self.V, "agenda.json", "items", {"id": "a-1", "text": "11/25 開會", "status": "open"})
        add_item(self.V, "statements.json", "statements", {"id": "s-1", "text": "甲", "status": "active"})
        add_item(self.V, "entities.json", "entities", {"id": "e-1", "name": "大同", "type": "客戶", "status": "active"})
        as_machine(self.V, "bbbb")
        add_item(self.V, "agenda.json", "items", {"id": "a-2", "text": "寄發票", "status": "open"})
        edit_item(self.V, "entities.json", "entities", "e-1", type="廠商")
        edit_item(self.V, "entities.json", "entities", "e-1", name="大同建材")
        got = read_json(self.V / ".system" / "agenda.json")["items"]
        self.assertEqual({i["id"] for i in got}, {"a-1", "a-2"})
        ent = read_json(self.V / ".system" / "entities.json")["entities"][0]
        self.assertEqual((ent["name"], ent["type"]), ("大同建材", "廠商"))
        files = sorted(p.relative_to(self.V).as_posix() for p in (self.V / ".system" / "streams").rglob("*.jsonl"))
        self.assertEqual(files, [".system/streams/agenda/m-aaaa.jsonl", ".system/streams/agenda/m-bbbb.jsonl",
                                 ".system/streams/entities/m-aaaa.jsonl", ".system/streams/entities/m-bbbb.jsonl",
                                 ".system/streams/statements/m-aaaa.jsonl"])
        # 每個檔只有自己的代號
        for p in (self.V / ".system" / "streams").rglob("*.jsonl"):
            for ln in p.read_text(encoding="utf-8").splitlines():
                self.assertEqual(json.loads(ln)["by"], p.stem)

    def test_profile_two_machines_conflict_and_preference(self):
        as_machine(self.V, "aaaa")
        prof = {"schema_version": 7, "types": [{"name": "客戶"}], "preferences": []}
        write_json_atomic(self.V / ".system" / "profile.json", prof)
        base = streams.load(self.V, "profile")
        self.assertIn("profile", base.records)
        # 兩台從同一版各改第一節：模擬 B 台的行（base 是 A 的第 1 版）
        d = streams.stream_dir(self.V, "profile")
        a = {"v": 1, "op": "set", "id": "profile", "seq": 2, "base": 1, "by": "m-aaaa", "set": {"types": [{"name": "甲"}]}}
        b = {"v": 1, "op": "set", "id": "profile", "seq": 2, "base": 1, "by": "m-bbbb", "set": {"types": [{"name": "乙"}]}}
        (d / "m-aaaa.jsonl").open("a", encoding="utf-8").write(json.dumps(a, ensure_ascii=False) + "\n")
        (d / "m-bbbb.jsonl").write_text(json.dumps(b, ensure_ascii=False) + "\n", encoding="utf-8")
        st = streams.load(self.V, "profile")
        self.assertEqual([(c["id"], c["field"]) for c in st.conflicts], [("profile", "types")])
        # 一台改第一節、一台加偏好：都在
        as_machine(self.V, "cccc")
        doc = read_json(self.V / ".system" / "profile.json")
        doc["preferences"].append({"text": "簡短", "use": "all", "source": "said", "date": "2026-11-04"})
        write_json_atomic(self.V / ".system" / "profile.json", doc)
        doc = read_json(self.V / ".system" / "profile.json")
        self.assertEqual([p["text"] for p in doc["preferences"]], ["簡短"])


class InventoryPendingSplit(unittest.TestCase):
    """驗收 6、15：清冊與待處理拆成共用與本機兩半。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.V = self.tmp / "v"
        (self.V / ".system").mkdir(parents=True)
        self._orig = env.machine_name

    def tearDown(self):
        env.machine_name = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def entry(self, **kw):
        e = {"id": "f-1", "origin": "client_file", "locations": [{"uri": "file://雲端/a.pdf", "size": 10, "mtime": 5}],
             "fingerprints": [{"sha256": "x"}], "status": "active", "read": "ok", "missing_since": None, "first_seen": "2026-11-01"}
        e.update(kw)
        return e

    def test_missing_source_only_marks_this_machine(self):
        inv = self.V / ".system" / "inventory.json"
        as_machine(self.V, "aaaa")
        write_json_atomic(inv, {"schema_version": 2, "entries": [self.entry()]})
        # A 台的來源根不存在：掃描把它標成 missing、讀不到
        doc = read_json(inv)
        doc["entries"][0].update(status="missing", missing_since="2026-11-04", read="error", error="找不到")
        write_json_atomic(inv, doc)
        self.assertEqual(read_json(inv)["entries"][0]["status"], "missing")
        shared = "".join(p.read_text(encoding="utf-8") for p in (self.V / ".system" / "streams" / "inventory").glob("*.jsonl"))
        self.assertNotIn("missing", shared)
        self.assertNotIn("找不到", shared)
        self.assertTrue((self.V / ".system" / "local" / "inventory.json").is_file())
        # B 台（同一份共用流水檔，沒有 A 的本機半）照常
        (self.V / ".system" / "local" / "inventory.json").rename(self.V / ".system" / "local" / "inventory.A")
        as_machine(self.V, "bbbb")
        e = read_json(inv)["entries"][0]
        self.assertEqual((e["status"], e["read"], e["missing_since"]), ("active", "ok", None))

    def test_pending_missing_file_stays_local_others_shared(self):
        pen = self.V / ".system" / "pending.json"
        as_machine(self.V, "aaaa")
        items = [{"id": "p-1", "kind": "missing_file", "status": "open", "text": "原檔不見"},
                 {"id": "p-2", "kind": "close", "status": "open", "text": "結案嗎"},
                 {"id": "p-3", "kind": "unreadable", "status": "open", "text": "讀不到"}]
        write_json_atomic(pen, {"schema_version": 2, "items": items})
        self.assertEqual({i["id"] for i in read_json(pen)["items"]}, {"p-1", "p-2", "p-3"})
        shared = "".join(p.read_text(encoding="utf-8") for p in (self.V / ".system" / "streams" / "pending").glob("*.jsonl"))
        self.assertIn("p-2", shared)
        self.assertNotIn("p-1", shared)
        self.assertNotIn("p-3", shared)
        local = json.loads((self.V / ".system" / "local" / "pending.json").read_text(encoding="utf-8"))["items"]
        self.assertEqual(set(local), {"p-1", "p-3"})

    def test_shared_inventory_fields_cross_machines(self):
        inv = self.V / ".system" / "inventory.json"
        as_machine(self.V, "aaaa")
        write_json_atomic(inv, {"schema_version": 2, "entries": [self.entry()]})
        doc = read_json(inv)
        doc["entries"][0].update(card_mode="pointer", intake={"from": "官網", "name": "價目表"})
        write_json_atomic(inv, doc)
        as_machine(self.V, "bbbb")
        doc = read_json(inv)
        doc["entries"][0]["archived"] = {"date": "2026-11-04", "reason": "過時", "turn": "t"}
        write_json_atomic(inv, doc)
        e = read_json(inv)["entries"][0]
        self.assertEqual((e["card_mode"], e["intake"]["name"], e["archived"]["reason"]), ("pointer", "價目表", "過時"))
        as_machine(self.V, "aaaa")
        self.assertEqual(read_json(inv)["entries"][0]["archived"]["reason"], "過時")


@unittest.skipUnless(GIT, "沒有 git")
class RealGit(unittest.TestCase):
    def git(self, cwd, *args):
        r = subprocess.run([GIT, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false", *args],
                           cwd=cwd, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, f"git {args}: {r.stdout}{r.stderr}")
        return r.stdout

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = env.machine_name
        self.bare = self.tmp / "remote.git"
        self.git(self.tmp, "init", "--bare", "-b", "main", str(self.bare))
        seed = self.tmp / "seed"
        seed.mkdir()
        self.git(seed, "init", "-b", "main")
        (seed / ".gitignore").write_text(".system/local/\n.system/legacy/\n.system/*.json\n.system/env.json\n", encoding="utf-8")
        (seed / ".system").mkdir()
        (seed / ".system" / "keep").write_text("x", encoding="utf-8")
        self.git(seed, "add", "-A")
        self.git(seed, "commit", "-m", "init")
        self.git(seed, "remote", "add", "origin", str(self.bare))
        self.git(seed, "push", "origin", "main")
        self.A, self.B = self.tmp / "a", self.tmp / "b"
        for d in (self.A, self.B):
            self.git(self.tmp, "clone", str(self.bare), str(d))

    def tearDown(self):
        env.machine_name = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_two_clones_no_merge_conflict(self):
        as_machine(self.A, "aaaa")
        add_item(self.A, "agenda.json", "items", {"id": "a-1", "text": "11/25 有個會", "status": "open"})
        add_item(self.A, "statements.json", "statements", {"id": "s-1", "text": "甲", "status": "active"})
        as_machine(self.B, "bbbb")
        add_item(self.B, "agenda.json", "items", {"id": "a-2", "text": "提醒我寄發票", "status": "open"})
        add_item(self.B, "statements.json", "statements", {"id": "s-2", "text": "乙", "status": "active"})
        for d in (self.A, self.B):
            self.git(d, "add", "-A")
            self.git(d, "commit", "-m", "x")
        self.git(self.A, "push", "origin", "main")
        self.git(self.B, "pull", "--no-rebase", "--no-edit", "origin", "main")
        self.git(self.B, "push", "origin", "main")
        self.git(self.A, "pull", "--no-rebase", "--no-edit", "origin", "main")
        for d, name in ((self.A, "aaaa"), (self.B, "bbbb")):
            as_machine(d, name)
            got = read_json(d / ".system" / "agenda.json")["items"]
            self.assertEqual({i["text"] for i in got}, {"11/25 有個會", "提醒我寄發票"})
            got = read_json(d / ".system" / "statements.json")["statements"]
            self.assertEqual({i["id"] for i in got}, {"s-1", "s-2"})
        status = self.git(self.A, "status", "--porcelain")
        self.assertNotIn("local", status)
        self.assertNotIn("agenda.json", status)


if __name__ == "__main__":
    unittest.main()
