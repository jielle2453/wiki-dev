"""清單 7（原 17，D-207）：清理與大小。清理照前一份（_lib/clean.run，跟備份還原同一把鎖，搶不到、背景整理在跑就這次不清、
報告寫一句）；收件匣份數、知識庫總大小是數字；綜合卡超過 lint_synthesis_max_chars 字 → 待處理一件（問要不要精簡）。"""
import os
from pathlib import Path

from kb._lib import backup, clean, inventory
from kb.lint import runner
from kb.lint.checks.system_dir import _is_link

NAME = "清理與大小"
BUSY_TEXT = "清理這次沒做：另一個備份、還原或退回正在跑，下週再清"
BATCH_TEXT = "清理這次沒做：背景整理在跑，下週再清"


def _clean(ctx):
    if backup.batch_running(ctx.vault):
        raise runner.Skipped(BATCH_TEXT)
    try:
        got = clean.run(ctx.vault)
    except backup.Refused:
        raise runner.Skipped(BUSY_TEXT) from None
    parts = []
    if got["turns_removed"]:
        parts.append(f"{got['turns_removed']} 個回合備份")
    if got["snapshots_removed"]:
        parts.append(f"{got['snapshots_removed']} 份快照")
    if not parts:
        return None
    return f"清掉 {'、'.join(parts)}，空出 {clean.mb_text(got['freed_bytes'])}"


def _walk(root, skip_hidden=True):
    count = size = 0
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not (skip_hidden and d.startswith(".")) and not _is_link(Path(dirpath) / d)]  # junction 也不走（T-13）
        for name in files:
            if skip_hidden and name.startswith("."):
                continue
            count += 1
            try:
                size += os.path.getsize(os.path.join(dirpath, name))
            except OSError:
                pass
    return count, size


def run(ctx):
    out = [runner.finding("sizes", "fix", "clean", "", apply=_clean)]
    inbox, _bytes = _walk(Path(ctx.vault) / inventory.HOLD)
    _n, total = _walk(ctx.vault, skip_hidden=False)
    out.append(runner.finding("sizes", "number", "sizes", "", data={"inbox": inbox, "vault_bytes": total,
                                                                     "inbox_over": inbox > ctx.config("lint_inbox_max")}))
    limit = ctx.config("lint_synthesis_max_chars")
    for e, rel, text in ctx.synthesis():
        if len(text) > limit:
            out.append(runner.finding(
                "sizes", "decide", f"synthesis_big:{rel}",
                f"「{e['name']}」的綜合卡有 {len(text)} 字，太長了；要不要下次整理時精簡？",
                data={"path": rel, "chars": len(text),
                      "results": [{"label": "好，精簡", "note": "下次整理改寫這張時請製卡助手把舊的現況精簡、紀事保留"}]},
                entity_ids=[e["id"]]))
    return out
