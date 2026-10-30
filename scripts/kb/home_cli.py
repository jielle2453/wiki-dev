"""kb home --json [--opened f-…,f-…]（Obsidian 首頁，#22，D-252）：首頁一次要的東西一支給齊，格式 willy-home/1。
只讀、不開回合；給外掛用，沒帶 --json 不做（人讀模式不做）。--opened 是外掛記的、她從首頁開過的卡編號（新到舊），不在清冊 active 的略過。
"""
import argparse
import json

from kb._lib import home
from kb.inventory_cli import NOT_IN_VAULT, find_vault

NEEDS_JSON = "這個指令給外掛用，要帶 --json"


def add_arguments(sub):
    sub.add_argument("--opened", default="", help="她從首頁開過的卡編號，逗號分隔，新到舊")
    sub.add_argument("--vault", help="總資料夾；沒給就從目前目錄往上找")
    sub.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 輸出")


def run(args):
    if not getattr(args, "json", False):
        print(NEEDS_JSON)
        return 3
    vault = find_vault(args)
    if vault is None:
        print(NOT_IN_VAULT)
        return 3
    opened = [x.strip() for x in str(args.opened or "").split(",") if x.strip()]
    print(json.dumps(home.build(vault, opened), ensure_ascii=False))
    return 0
