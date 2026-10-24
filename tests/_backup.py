"""備份還原與換電腦的測試共用：知識庫複本（tests/fixtures/inventory，另放暫存、鎖檔與空夾）、假批次、假回合、整包雜湊。"""
import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from tests.test_lib_inventory_scan import make_inv_vault
from kb._lib import backup  # noqa: E402

TIME = "%Y-%m-%dT%H:%M:%S"


def make_vault():
    """回 (tmp, V, raw)：V 有口述、暫存、快照夾、鎖檔、一個空的型別夾，備份該排除的都有。"""
    tmp, V, raw = make_inv_vault()
    (V / "案子" / "空夾").mkdir()
    (V / ".system" / "temp").mkdir(exist_ok=True)
    (V / ".system" / "temp" / "暫存.txt").write_text("暫存\n", encoding="utf-8")
    (V / ".system" / "snapshots").mkdir(exist_ok=True)
    (V / ".system" / "snapshots" / "舊快照.zip").write_bytes(b"x")
    (V / ".system" / "statements.json").write_text(json.dumps(
        {"schema_version": 1, "statements": []}, ensure_ascii=False), encoding="utf-8")
    (V / ".system" / "別人.lock").write_text("", encoding="utf-8")
    from kb._lib import vault as vault_lib
    vault_lib.ensure_vault_id(V)
    return tmp, V, raw


def put_batch(V, created_min_ago=1, seen_min_ago=None):
    """寫一個 open 的批次進 batches.json：建立 created_min_ago 分鐘前、最後動靜 seen_min_ago 分鐘前（沒給就沒有 last_seen）。"""
    now = datetime.now().replace(microsecond=0)
    batch = {"kind": "cards", "items": ["f-0001"], "status": "open", "job": "j-1",
             "created": (now - timedelta(minutes=created_min_ago)).strftime(TIME)}
    if seen_min_ago is not None:
        batch["last_seen"] = (now - timedelta(minutes=seen_min_ago)).strftime(TIME)
    (V / ".system" / "batches.json").write_text(json.dumps(
        {"schema_version": 1, "jobs": [{"job": "j-1", "session_id": "s", "status": "open", "turn": "t"}],
         "batches": [batch], "agents": []}, ensure_ascii=False), encoding="utf-8")


def put_turns(V, days_ago, prefix="t", prompt="那一句"):
    """versions/ 底下放一批回合夾（turn.json 有 started、prompt_head），days_ago 是每個回合幾天前；回夾名清單（照給的順序）。"""
    now = datetime.now().replace(microsecond=0)
    ids = []
    for i, d in enumerate(days_ago):
        started = now - timedelta(days=d, seconds=len(days_ago) - i)
        tid = f"{started:%Y%m%d-%H%M%S}-{prefix}{i:03d}"
        folder = V / ".system" / "versions" / tid
        folder.mkdir(parents=True)
        (folder / "turn.json").write_text(json.dumps({
            "schema_version": 1, "turn": tid, "started": started.strftime(TIME),
            "prompt_head": f"{prompt}{i}", "done": True}, ensure_ascii=False), encoding="utf-8")
        (folder / "manifest.jsonl").write_text("", encoding="utf-8")
        (folder / "x.bin").write_bytes(b"0" * 100)
        ids.append(tid)
    return ids


def tree(V, skip=()):
    """整個資料夾的 {相對路徑: sha256 或 None（空夾）}，比兩次是否一模一樣。"""
    out = {}
    root = Path(V)
    for dirpath, dirs, files in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        if rel_dir != "." and not dirs and not files:
            out[rel_dir + "/"] = None
        for name in files:
            p = Path(dirpath) / name
            rel = p.relative_to(root).as_posix()
            if any(rel == s or rel.startswith(s.rstrip("/") + "/") for s in skip):
                continue
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def make_zip(V, B, name="vault備份 2026-10-01.zip", **meta_over):
    """用 backup.write_zip 當場做一份合格的備份；回路徑。"""
    from kb._lib import vault as vault_lib
    B.mkdir(parents=True, exist_ok=True)
    meta = {"schema_version": 1, "kind": "backup", "reason": None,
            "created": datetime.now().strftime(TIME), "plugin_version": backup.plugin_version(),
            "machine": "LIN-PC", "vault_name": Path(V).name, "vault_id": vault_lib.vault_id(V)}
    meta.update(meta_over)
    dest = B / name
    backup.write_zip(V, dest, meta)
    return dest
