"""知識庫第一層給客戶自己用的保留夾（彈性區，D-509、D-513）：名稱只在這裡定一次，其他地方一律引用 FREE_DIR。

改名時另外三處是靜態檔、要跟著改：skeleton/<FREE_DIR>/、rules/core.md R-01、skeleton/CLAUDE.md（tests/test_free_area 對齊）。
"""
FREE_DIR = "_extras"
# 從這一版（含）以前升上來的才講「第一層的 FREE_DIR 現在是你自己的區」：這題一定在它之後發行，發行時不用改（spec 裁定 2）
FREE_SINCE_AFTER = "0.27.1"
