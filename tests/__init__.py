"""測試套件。WIKI_WITH_WILLY_NO_BACKGROUND：黑箱跑開場 hook 時不開背景健檢的子行程（知識庫是暫存夾，背景還在寫就被刪掉；
子行程都繼承這個環境變數）。要測觸發的那幾支自己拿掉它。"""
import os

os.environ.setdefault("WIKI_WITH_WILLY_NO_BACKGROUND", "1")
