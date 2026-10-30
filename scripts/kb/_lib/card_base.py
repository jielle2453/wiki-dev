"""她手改了卡，系統跟著更新（D-270）：記程式與 Claude 最後寫的那一版（基準），再跟卡現在的內文比。

只比內文（檔頭 --- 之後）；檔頭的標籤行走 tag_edit（D-505），其他檔頭欄位是程式的。
基準記在 .system/card_base.json：{"schema_version": 1, "cards": {相對路徑: {"sha256", "body", "at"}}}；讀不到當沒有紀錄。
卡 = 檔案索引/ 底下的 .md（檔案卡）與 <型別夾>/<名稱>/<名稱>.md、檔頭有 型別 與 名稱 的綜合卡。

誰寫卡誰更新基準：output_log 的 Z5、Z1 驗過之後 record；rename／cards sync 搬卡 rekey；刪卡 forget；退回 after_revert。
記不了只記 log（record_safe 吞例外），不擋原本的寫入。沒有紀錄的卡（第一次用到、別的路徑長出來的卡）：
edits 把現在的內容當基準補上、不報手改；卡搬了但沒人 rekey（退回夾名）時，內文跟一筆沒對應檔的紀錄一樣就認作同一張。
"""
import difflib
import hashlib
from datetime import datetime
from pathlib import Path

from kb._lib import cards, inventory
from kb._lib.io import FileLock, read_json, write_json_atomic

BASE_POSIX = ".system/card_base.json"
SCHEMA = 1


def body_of(text):
    """檔頭之後的全文，行尾統一 \\n；沒有檔頭就是整份。"""
    text = str(text).lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1:])
    return text


def sha(body):
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _path(vault):
    return Path(vault) / BASE_POSIX


def load(vault):
    """{相對路徑: 紀錄}；檔不在、壞掉、格式不對都當沒有紀錄。"""
    try:
        data = read_json(_path(vault), None)
    except (ValueError, OSError):
        return {}
    got = data.get("cards") if isinstance(data, dict) else None
    if not isinstance(got, dict):
        return {}
    return {k: v for k, v in got.items() if isinstance(v, dict) and isinstance(v.get("sha256"), str)
            and isinstance(v.get("body"), str)}


def _save(vault, recs):
    write_json_atomic(_path(vault), {"schema_version": SCHEMA, "cards": recs})


def _entry(body):
    return {"sha256": sha(body), "body": body, "at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}


def _locked(vault, fn):
    """讀、改、寫整份基準，鎖住免得兩個程序互蓋。"""
    _path(vault).parent.mkdir(parents=True, exist_ok=True)
    with FileLock(_path(vault)):
        recs = load(vault)
        out = fn(recs)
        _save(vault, recs)
        return out


# ---------- 哪些是卡 ----------

def _reserved(name):
    return name.startswith(".") or name.casefold() in inventory.VAULT_RESERVED_DIRS


def is_synthesis_text(text):
    try:
        front = cards.parse_front(text)
    except ValueError:
        return False
    return "名稱" in front and "型別" in front


def all_cards(vault):
    """[(相對路徑, 'file'|'synthesis')]，照路徑排。"""
    out = [(rel, "file") for rel in cards._walk_cards(vault)]
    root = Path(vault)
    try:
        tops = sorted(p for p in root.iterdir() if p.is_dir() and not _reserved(p.name))
    except OSError:
        return out
    for top in tops:
        try:
            names = sorted(p for p in top.iterdir() if p.is_dir() and not p.name.startswith("."))
        except OSError:
            continue
        for d in names:
            f = d / f"{d.name}.md"
            try:
                if f.is_file() and is_synthesis_text(f.read_text(encoding="utf-8")):
                    out.append((f.relative_to(root).as_posix(), "synthesis"))
            except (OSError, UnicodeDecodeError):
                continue
    return sorted(out)


def card_kind(vault, rel):
    """這個相對路徑是卡嗎：'file'、'synthesis' 或 None（檔要在）。"""
    parts = rel.split("/")
    p = Path(vault) / rel
    if parts[0] == cards.CARDS_DIR and rel.lower().endswith(".md") and not any(x.startswith(".") for x in parts):
        return "file" if p.is_file() else None
    if len(parts) == 3 and not _reserved(parts[0]) and not parts[1].startswith(".") and parts[2] == f"{parts[1]}.md":
        try:
            return "synthesis" if p.is_file() and is_synthesis_text(p.read_text(encoding="utf-8")) else None
        except (OSError, UnicodeDecodeError):
            return None
    return None


def _read_body(vault, rel):
    return body_of((Path(vault) / rel).read_text(encoding="utf-8"))


# ---------- 寫的人更新基準 ----------

def record(vault, rel):
    """把這張卡現在的內文記成基準（卡要在）。"""
    body = _read_body(vault, rel)
    _locked(vault, lambda recs: recs.__setitem__(rel, _entry(body)))


def record_safe(vault, rel):
    """寫卡的人叫：記不了只記 log，不擋原本的寫入。回有沒有記成。"""
    try:
        if card_kind(vault, rel) is None:
            return False
        record(vault, rel)
        return True
    except BaseException as e:  # noqa: BLE001
        _log(vault, e)
        return False


def in_sync(vault, rel):
    """這張卡現在的內文就是基準（或根本沒紀錄）：此時程式改它，基準可以跟著換；她有沒處理的手改就不換。"""
    try:
        got = load(vault).get(rel)
        return got is None or got["sha256"] == sha(_read_body(vault, rel))
    except (OSError, UnicodeDecodeError):
        return True


def rekey(vault, old, new, synced=True):
    """卡搬家：紀錄換鍵。synced（搬之前沒有手改）時順便把基準換成新位置現在的內文，內文跟著程式改過（例：改名換標題）。"""
    try:
        def fn(recs):
            got = recs.pop(old, None)
            if got is None:
                return
            if synced and card_kind(vault, new):
                got = _entry(_read_body(vault, new))
            recs[new] = got
        _locked(vault, fn)
    except BaseException as e:  # noqa: BLE001
        _log(vault, e)


def forget(vault, *rels):
    try:
        _locked(vault, lambda recs: [recs.pop(r, None) for r in rels])
    except BaseException as e:  # noqa: BLE001
        _log(vault, e)


def after_revert(vault, restored, removed):
    """kb versions revert：還原回來的卡基準換成那一版，被拿掉的卡刪紀錄；不算她改的。"""
    try:
        have = load(vault)
        removed = [r for r in removed if r in have]
        restored = [r for r in restored if card_kind(vault, r)]
        if not removed and not restored:  # 退回的不是卡：不碰狀態檔
            return

        def fn(recs):
            for rel in removed:
                recs.pop(rel, None)
            for rel in restored:
                if card_kind(vault, rel):
                    recs[rel] = _entry(_read_body(vault, rel))
        _locked(vault, fn)
    except BaseException as e:  # noqa: BLE001
        _log(vault, e)


# ---------- 認出她改的 ----------

def hunks(before, after):
    """逐行比對的改動塊：新增 before 是 ""、刪掉 after 是 ""。"""
    a, b = before.split("\n"), after.split("\n")
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            out.append({"before": "\n".join(a[i1:i2]), "after": "\n".join(b[j1:j2])})
    return out


def _item(vault, rel, kind, old_body, new_body):
    try:
        front = cards.parse_front((Path(vault) / rel).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        front = {}
    if kind == "file":
        ents = front.get("實體")
        item = {"path": rel, "kind": "file", "id": front.get("編號") or "", "title": front.get("標題") or "",
                "entities": [x for x in ents if isinstance(x, str)] if isinstance(ents, list) else []}
    else:
        item = {"path": rel, "kind": "synthesis", "entity": front.get("名稱") or rel.split("/")[1]}
    item["hunks"] = hunks(old_body, new_body)
    return item


def edits(vault, deadline=None, persist=True):
    """比每張卡現在的內文跟基準。回 {"edits": [...], "more": 時限內沒比完}。
    沒紀錄的卡（含搬了沒換鍵的）補基準、不報；persist=False 時不寫狀態檔。被刪的卡不列。"""
    import time
    recs = load(vault)
    found = all_cards(vault)
    live = {rel for rel, _k in found}
    orphans = {}  # sha → 沒對應檔的紀錄路徑：卡搬了但沒人換鍵
    for rel, got in recs.items():
        if rel not in live:
            orphans.setdefault(got["sha256"], rel)
    out, added, drop, more = [], {}, [], False
    for rel, kind in found:
        if deadline is not None and time.monotonic() > deadline:
            more = True
            break
        try:
            body = _read_body(vault, rel)
        except (OSError, UnicodeDecodeError):
            continue
        got = recs.get(rel)
        if got is None:
            s = sha(body)
            old = orphans.pop(s, None)
            if old is not None:
                drop.append(old)
            added[rel] = _entry(body)
        elif got["sha256"] != sha(body):
            out.append(_item(vault, rel, kind, got["body"], body))
    if persist and (added or drop):
        try:
            def fn(cur):
                for rel, ent in added.items():
                    cur.setdefault(rel, ent)
                for rel in drop:
                    cur.pop(rel, None)
            _locked(vault, fn)
        except BaseException as e:  # noqa: BLE001  補不了基準只記 log
            _log(vault, e)
    return {"edits": out, "more": more}


class DoneRefused(ValueError):
    pass


def done(vault, paths):
    """Claude 處理完了：這幾張的基準換成現在的內容。路徑不是卡或不存在就整個拒絕。"""
    rels = []
    for p in paths:
        rel = str(p).replace("\\", "/").strip("/")
        if card_kind(vault, rel) is None:
            raise DoneRefused(f"「{p}」不是卡（要寫知識庫相對路徑，例：檔案索引/…/xxx.md）或檔案不存在")
        rels.append(rel)
    bodies = {rel: _read_body(vault, rel) for rel in rels}
    _locked(vault, lambda recs: [recs.__setitem__(r, _entry(b)) for r, b in bodies.items()])
    return rels


def _log(vault, e):
    try:
        from kb._lib import ledger
        ledger.log_error(vault, f"card_base {type(e).__name__}: {str(e)[:200]}", source="card_base")
    except BaseException:  # noqa: BLE001
        pass
