"""lint 第二類（驗收 10，D-220）：整理擱著的只數、交 ingest；數字跟 kb cards todo 同一套。"""
import json
import shutil
import unittest

from tests import _lint as L
from tests.test_scripts_inventory_cli import run_kb
from kb.lint.checks import todo  # noqa: E402


class Todo(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_same_numbers_as_cards_todo(self):
        (found,) = todo.run(L.ctx(self.V))
        self.assertEqual(found["kind"], "ingest")
        data = json.loads(run_kb("cards", "todo", "--json", cwd=self.V).stdout)
        self.assertEqual(found["data"]["unsorted"], len(data["new"]) + len(data["stale"]))
        self.assertEqual(found["data"]["unlinked"], len(data["unlinked"]))
        self.assertEqual(found["data"]["synthesis_stale"], len(data["synthesis_stale"]))
        self.assertEqual(found["data"]["missing"], len(data["missing"]))


if __name__ == "__main__":
    unittest.main()
