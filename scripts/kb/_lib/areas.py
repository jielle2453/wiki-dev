"""知識庫第一層給客戶自己用的保留夾（彈性區，D-509、D-513）與暫存區（D-324）：名稱只在這裡定一次，其他地方一律引用常數。

改名時另外三處是靜態檔、要跟著改：skeleton/<FREE_DIR>/、rules/core.md R-01、skeleton/CLAUDE.md（tests/test_free_area 對齊）。
暫存區同理：skeleton/<HOLD_DIR>/ 與 skeleton/CLAUDE.md、rules、skills 裡的字（spec 乙）。
"""
FREE_DIR = "_個人"
HOLD_DIR = "暫存區"  # 第一層的暫存區：原本的收件匣與 AI 產出合成一個（D-324）；willy 不會自動清裡面的東西
OLD_INBOX = "收件匣"  # 舊名：只給升級遷移與讀舊資料用（出處類別「對話收件」「AI 產出」是誰放的，不是夾名，照舊）
OLD_OUTPUT = "AI 產出"
# 從這一版（含）以前升上來的才講「第一層的 FREE_DIR 現在是你自己的區」：這題一定在它之後發行，發行時不用改（spec 裁定 2）
FREE_SINCE_AFTER = "0.27.1"
