"""lint 清單 2（驗收 2）：綜合卡出現只有標題的段 → synthesis_fix「有空段」。"""
import shutil
import unittest

from tests import _lint as L
from kb.lint import state  # noqa: E402
from kb.lint.checks import empty_sections  # noqa: E402


class EmptySections(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_empty_section_marked(self):
        L.write_synthesis(self.V, body="## 現況\n- 進行中\n\n## 時程\n\n## 紀事\n- 10-20 登記\n")
        (found,) = empty_sections.run(L.ctx(self.V))
        self.assertEqual(found["data"]["cards"][0]["sections"], ["時程"])
        found["apply"](L.ctx(self.V))
        self.assertEqual([f["reason"] for f in state.fixes(self.V)], ["有空段"])

    def test_last_section_empty_too(self):
        L.write_synthesis(self.V, body="## 現況\n- 進行中\n\n## 推算\n")
        (found,) = empty_sections.run(L.ctx(self.V))
        self.assertEqual(found["data"]["cards"][0]["sections"], ["推算"])

    def test_full_sections(self):
        L.write_synthesis(self.V)
        self.assertEqual(empty_sections.run(L.ctx(self.V)), [])


if __name__ == "__main__":
    unittest.main()
