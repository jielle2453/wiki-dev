"""lint 清單 4：手改的偵測在重新產生那一刻（_lib/renders）；健檢只數還沒處理完的、這個月總目錄與工作日誌被手改幾次。"""
import shutil
import unittest

from tests import _lint as L
from kb._lib import pending, renders, turn  # noqa: E402
from kb.lint.checks import handedits  # noqa: E402


class HandEdits(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_counts_open_and_saved(self):
        t = turn.start(self.V, None, "")["turn"]
        pending.add_handedit(self.V, "系統/日程.md", ".system/handedits/x-日程.md",
                             {"checked": [], "removed": [], "changed_date": [], "other": ["x"]}, t)
        renders.keep(self.V, "總目錄.md", "她的\n")
        (num,) = handedits.run(L.ctx(self.V))
        self.assertEqual((num["kind"], num["data"]["open"], num["data"]["index_saved"]), ("number", 1, 1))

    def test_nothing(self):
        (num,) = handedits.run(L.ctx(self.V))
        self.assertEqual((num["data"]["open"], num["data"]["index_saved"], num["data"]["journal_saved"]), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
