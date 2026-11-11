"""測試套件。WIKI_WITH_WILLY_NO_BACKGROUND：黑箱跑開場 hook 時不開背景健檢與背景查新版的子行程（知識庫是暫存夾，背景還在寫就被刪掉；
子行程都繼承這個環境變數）。要測觸發的那幾支自己拿掉它。"""
import atexit
import os
import shutil
import tempfile

os.environ.setdefault("WIKI_WITH_WILLY_NO_BACKGROUND", "1")
os.environ.setdefault("WIKI_WITH_WILLY_NO_SCHEDULE", "1")  # 背景比對的排程：不碰這台真的工作排程器，沒有測試拿掉（裁定 11）
if "WIKI_WITH_WILLY_INDEX_DIR" not in os.environ:  # 卡片索引（#57）：測試一律寫到這個暫存夾，不碰這台真的 LOCALAPPDATA；不同測試庫的檔名不同
    _INDEX_DIR = tempfile.mkdtemp(prefix="wiki-index-")
    os.environ["WIKI_WITH_WILLY_INDEX_DIR"] = _INDEX_DIR
    atexit.register(shutil.rmtree, _INDEX_DIR, ignore_errors=True)
