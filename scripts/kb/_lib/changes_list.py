"""背景比對的清單（#60、#61，D-536）：.system/local/changes.json，這台電腦自己的，不備份、不進回合帳。

kb changes --background（電腦排程）寫、kb changes 與 kb inventory scan（全部來源）跟著寫；每句開頭（hooks/_checks）只讀這份。
格式：{schema_version: 1, at, seconds, via: background|changes|inventory scan, report, wip: {n, names} 或 null, cards_mtime 或 null}。
report 是 inventory.public(report) 去掉 entries，多 ids（變動那幾份的 uri → 清冊編號，給 detected_rows 用）。
讀不懂、schema_version 不是 1 → 當沒有清單（不記 log：排程還沒跑過是正常的）。
"""
import os
import time
from datetime import datetime
from pathlib import Path

from kb._lib.io import read_json, write_json_atomic

LIST_REL = ".system/local/changes.json"
LOCK_REL = ".system/local/changes.lock"
LOCK_STALE = 30 * 60  # 秒：超過算上一個中途被砍留下的
SCHEMA_VERSION = 1
WIP_NAMES = 3
VIA = ("background", "changes", "inventory scan")
_NOT_CARD_DIRS = {".system", ".git", ".obsidian", ".claude", ".trash", "系統"}


def path(vault):
    return Path(vault) / LIST_REL


def read(vault):
    """讀清單；沒有、讀不懂、版本不對回 None。"""
    try:
        data = read_json(path(vault))
    except (ValueError, OSError):
        return None
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION or not isinstance(data.get("report"), dict):
        return None
    return data


def _ids(report):
    """變動那幾份（修改、不見、之前就不見、搬動兩端）的 uri → 清冊編號。"""
    from kb._lib import inventory
    wanted = set(report["modified"]) | set(report["missing"]) | set(report.get("still_missing") or [])
    for a, b in report["moved"]:
        wanted.update((a, b))
    keys = {inventory.uri_key(u): u for u in wanted}
    out = {}
    for e in report.get("entries") or []:
        for loc in e.get("locations") or []:
            u = keys.get(inventory.uri_key(loc.get("uri", "")))
            if u is not None and e.get("id"):
                out.setdefault(u, e["id"])
    return out


def write(vault, report, via, seconds, wip=None, cards_mtime=None):
    """寫清單（暫存檔再換名）。report 是 inventory.scan 的回傳（帶 entries）。"""
    from kb._lib import inventory
    body = {k: v for k, v in inventory.public(report).items()}
    body["moved"] = [list(m) for m in report["moved"]]
    body["ids"] = _ids(report)
    data = {"schema_version": SCHEMA_VERSION, "at": datetime.now().isoformat(timespec="seconds"), "seconds": round(seconds, 1),
            "via": via, "report": body, "wip": wip, "cards_mtime": cards_mtime}
    p = path(vault)
    p.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(p, data)
    return data


def write_carried(vault, report, via, seconds):
    """AI 當場跑的（kb changes、kb inventory scan）：wip、cards_mtime 沿用舊清單，沒有就 null（實作疑義 1）。"""
    old = read(vault) or {}
    return write(vault, report, via, seconds, old.get("wip"), old.get("cards_mtime"))


def applied(report):
    """kb inventory scan 套用之後：新增、修改、不見、搬動都是空的；這次不見的併進之前就不見的。"""
    out = dict(report)
    out.update(added=[], modified=[], moved=[], duplicates=[], restored=[], missing=[],
               still_missing=list(dict.fromkeys(list(report.get("still_missing") or []) + list(report["missing"]))))
    return out


def wip_summary(rows):
    return {"n": len(rows), "names": [r["name"] for r in rows[:WIP_NAMES]]}


def compare(vault):
    """每句開頭用：清單還原成 file_compare 的 (sources, report)；沒有清單回 None。sources 重新讀（清單存不下）。"""
    data = read(vault)
    if data is None:
        return None
    from kb._lib import sources as sources_lib
    r = dict(data["report"])
    for k in ("added", "modified", "missing", "still_missing", "moved", "missing_sources"):
        r[k] = list(r.get(k) or [])
    r["moved"] = [tuple(m) for m in r["moved"]]
    r["incomplete"] = bool(r.get("incomplete"))
    r["entries"] = [{"id": eid, "locations": [{"uri": u}]} for u, eid in (r.pop("ids", None) or {}).items()]
    return sources_lib.load(vault), r


def acquire(vault):
    """背景比對的鎖：拿到回 True；別的還在跑（LOCK_STALE 內）回 False。"""
    p = Path(vault) / LOCK_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - p.stat().st_mtime < LOCK_STALE:
                    return False
                p.unlink()
            except FileNotFoundError:
                pass
            continue
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    return False


def release(vault):
    try:
        (Path(vault) / LOCK_REL).unlink()
    except FileNotFoundError:
        pass


def _newest_mtime(paths):
    best = 0.0
    for p in paths:
        try:
            best = max(best, os.stat(p).st_mtime)
        except OSError:
            pass
    return best


def cards_mtime(vault):
    """卡可能被改的最近修改時間：第一層（不含系統夾、暫存區）底下所有 .md，加 entities.json（原 hooks/_checks.cards_mtime）。"""
    from kb._lib.areas import HOLD_DIR

    skip = {s.casefold() for s in _NOT_CARD_DIRS | {HOLD_DIR}}
    best = _newest_mtime([os.path.join(str(vault), ".system", "entities.json")])
    stack = [str(vault)]
    top = True
    while stack:
        root = stack.pop()
        try:
            with os.scandir(root) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if not (top and e.name.casefold() in skip):
                                stack.append(e.path)
                        elif e.name.endswith(".md") and not top:
                            best = max(best, e.stat(follow_symlinks=False).st_mtime)
                    except OSError:
                        continue
        except OSError:
            continue
        top = False
    return best
