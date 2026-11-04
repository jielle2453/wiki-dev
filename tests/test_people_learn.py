"""多人共用 2 第 3 點：新同事第一次（D-300）。新 clone＝共用清冊有東西、本機清冊（.system/local/inventory.json）是空的。"""
import json
import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests import _cards
from tests.test_people import Base
from kb._lib import inventory, moved  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import _checks  # noqa: E402


class Learn(Base):
    def setUp(self):
        super().setUp()
        os.environ["WIKI_WITH_WILLY_NO_BACKGROUND"] = "1"
        self.addCleanup(os.environ.pop, "WIKI_WITH_WILLY_NO_BACKGROUND", None)
        self.local = self.V / ".system" / "local" / "inventory.json"
        self.learned = self.V / ".system" / "local" / "learned.json"
        self.assertTrue(self.local.is_file(), "scan_apply 之後本機清冊應該有東西")

    def new_clone(self):
        """模擬新 clone：本機那半與 env.json 都沒有（git 不帶它們）。"""
        self.local.unlink()
        for p in (self.learned, self.V / ".system" / "env.json"):
            if p.exists():
                p.unlink()

    def test_not_learning_on_normal_vault(self):
        self.assertFalse(inventory.learning(self.V))
        self.assertIsNone(_checks.line_learning(self.V))

    def test_new_clone_learning_line_scan_silent_then_learn(self):
        self.new_clone()
        self.assertTrue(inventory.learning(self.V))
        self.assertIn("還在認檔案", _checks.line_learning(self.V))
        r = self.kb("inventory", "scan", "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(json.loads(r.stdout)["learning"])
        r = self.kb("inventory", "learn", "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        got = json.loads(r.stdout)
        self.assertGreater(got["learned"], 0)
        self.assertTrue(self.learned.is_file())
        self.assertFalse(inventory.learning(self.V))
        self.assertIsNone(_checks.line_learning(self.V))
        r = self.kb("inventory", "scan", "--json")
        rep = json.loads(r.stdout)
        self.assertEqual((len(rep["added"]), len(rep["modified"])), (0, 0), r.stdout)
        # 改一份才報 1
        some = next(p for p in Path(self.raw).rglob("*.txt"))
        some.write_text(some.read_text(encoding="utf-8") + "又多一行", encoding="utf-8")
        rep = json.loads(self.kb("inventory", "scan", "--json").stdout)
        self.assertEqual(len(rep["modified"]), 1, rep)

    def test_placeholder_not_read(self):
        self.new_clone()
        real = inventory.read_kind
        target = []

        def fake(segs, st, cap, credential=True):
            if not target:
                target.append("/".join(segs))
                return "placeholder", None
            return real(segs, st, cap, credential)
        read = []
        real_sha = inventory.sha256_of

        def spy(path, should_stop=None):
            read.append(path)
            return real_sha(path, should_stop)
        with mock.patch.object(inventory, "read_kind", fake), mock.patch.object(inventory, "sha256_of", spy):
            got = inventory.learn(self.V)
        self.assertEqual(got["placeholder"], 1)
        self.assertFalse(any(target[0] in p for p in read), (target, read))  # 占位檔沒讀內容
        items = json.loads(self.local.read_text(encoding="utf-8"))["items"]
        self.assertTrue(any(v.get("read") == "placeholder" and v.get("locs") for v in items.values()))

    def test_no_env_json_no_moved_line(self):
        self.new_clone()
        self.assertIsNone(_checks.line_moved(self.V))  # 新 clone 不誤問搬家（D-300）


if __name__ == "__main__":
    unittest.main()
