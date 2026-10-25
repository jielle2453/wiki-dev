"""清單 6（原 2、3，D-054）：版本與骨架。她改過的骨架檔（CLAUDE.md 這類）→ 待處理一件（要留她的還是換回程式的；
鍵帶她那份的指紋，答過不再開，她又改了才再問）；沒有骨架紀錄的舊知識庫不判。存的 schema 比現在舊的狀態檔幾個、
舊範本的卡幾張是數字（遷移由升級做）。"""
import hashlib
from pathlib import Path

from kb._lib import cards, migrate, skeleton
from kb.lint import runner

NAME = "版本與骨架"


def run(ctx):
    out = []
    rec = skeleton.recorded(ctx.vault)
    if rec is not None:
        for rel in skeleton.files():
            p = Path(ctx.vault) / rel
            want = rec["files"].get(rel)
            if not want or not p.is_file():
                continue
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            if sha == want or skeleton.known(rel, sha):
                continue
            out.append(runner.finding(
                "versions", "decide", f"skeleton:{rel}:{sha[:12]}",
                f"你改過「{rel}」，跟程式的版本不同；要留你的，還是換回程式的？",
                data={"file": rel, "results": [{"label": "換回程式的", "do": [f"kb upgrade skeleton {rel} --replace"],
                                                "note": "她那份會備進回合，說「退回」就回來"}]},
                once=True))
    old_template = sum(1 for c in ctx.cards().values() if str(c["front"].get("範本版本")) != cards.TEMPLATE_VERSION)
    out.append(runner.finding("versions", "number", "versions", "",
                              data={"old_schema": len(migrate.pending(ctx.vault)), "old_template_cards": old_template}))
    return out
