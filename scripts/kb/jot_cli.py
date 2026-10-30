"""kb jot "<內容>" [--json]（Obsidian 首頁的隨手記，#22，D-267、裁定 35）：把「- YYYY-MM-DD HH:MM 內容」接在 <FREE_DIR>/隨手記.md 最下面。
沒有那一頁就建（檔頭一行「# 隨手記」）；寫前 turn.backup（退得回來）；--via obsidian 照 D-255 開自己的回合，終端機跑的記程式段。
內容一行（換行換成空白）、去頭尾空白、不收空的、MAX_LEN 字內；照原樣存，不遮值（這是她自己的筆記）。
彈性區是客戶自己的區（D-510）：Claude 不讀、不整理，工作日誌只記「記了一則隨手記」，不抄內容。
成功印「記下了」；--json 回 {path, line, turn}（turn 是這一筆的回合代號，外掛復原時帶給 versions revert，只退這一筆）。
"""
import argparse
import datetime as dt
import json
import re
from pathlib import Path

from kb import journal_cli
from kb._lib import io as kio
from kb._lib import turn
from kb._lib.areas import FREE_DIR
from kb.inventory_cli import NOT_IN_VAULT, find_vault

NOTE_NAME = "隨手記.md"
NOTE_REL = f"{FREE_DIR}/{NOTE_NAME}"
HEADER = "# 隨手記"
MAX_LEN = 2000
DONE = "記下了"
EMPTY = "沒有內容可以記"
TOO_LONG = f"太長了：隨手記一則最多 {MAX_LEN} 個字"
JOURNAL_NOTE = "記了一則隨手記"
CLI_LOCK_TIMEOUT = 30
LINE_BREAKS = re.compile(r"\s*[\r\n]+\s*")


def add_arguments(sub):
    sub.add_argument("text", nargs="?", help="要記的一句話（一行；換行會換成空白）")
    sub.add_argument("--vault", help="總資料夾；沒給就從目前目錄往上找")
    sub.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 輸出")


def normalize(text):
    """一行、去頭尾空白；回 (內容, 問題)，問題是 None 或要印的那句。"""
    one = LINE_BREAKS.sub(" ", str(text or "")).strip()
    if not one:
        return "", EMPTY
    if len(one) > MAX_LEN:
        return "", TOO_LONG
    return one, None


def append_line(vault, line):
    """接在最下面（沒有檔就建，前面放檔頭）；寫前備進回合。回 (action, turn_id)。"""
    path = Path(vault) / NOTE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    with kio.FileLock(path):
        turn_id = turn.current(vault)["turn"]
        action = "modify" if path.is_file() else "create"
        turn.backup(vault, NOTE_REL, turn_id)
        old = path.read_text(encoding="utf-8") if action == "modify" else HEADER + "\n\n"
        if old and not old.endswith("\n"):
            old += "\n"
        kio.write_text_atomic(path, old + line + "\n")
    return action, turn_id


def run(args):
    vault = find_vault(args)
    if vault is None:
        print(NOT_IN_VAULT)
        return 3
    text, problem = normalize(args.text)
    if problem:
        print(problem)
        return 3
    kio.LOCK_TIMEOUT = CLI_LOCK_TIMEOUT
    line = f"- {dt.datetime.now():%Y-%m-%d %H:%M} {text}"
    conversation = journal_cli.in_conversation(vault)
    try:
        action, turn_id = append_line(vault, line)
    except OSError as e:
        print(f"沒記到：{e}")
        return 3
    journal_cli.record_program_or_warn(vault, JOURNAL_NOTE, [{"path": NOTE_REL, "action": action}], "jot", conversation)
    if getattr(args, "json", False):
        print(json.dumps({"path": NOTE_REL, "line": line, "turn": turn_id}, ensure_ascii=False))
    else:
        print(DONE)
    return 0
