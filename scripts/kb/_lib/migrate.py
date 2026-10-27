"""狀態檔與卡檔頭的遷移表（升級打包 要做的事 2，D-054、D-215）：kb upgrade --finish 在新對話開場叫它轉格式。

STATE_FILES 是一張表：哪個檔、現在的 schema 版本、磁碟上存的版本、怎麼寫回。各檔用自己的 load（已有的遷移，在記憶體補欄位）讀、
照自己的寫法寫回（寫前備進回合，versions revert 退得回）。之後新增遷移的題，在這張表加一列（_lib/migrate.py 的表有變，
發行程式 tools/release.py 就不准標成小修，D-217）。
CARD_HEADER_MIGRATIONS 是卡的檔頭遷移：[{"from": 舊範本版本, "to": 新範本版本, "fn": 整張卡的文字 → 新文字}]，目前沒有要遷的（空表，D-054）；
只改檔頭機器欄位、正文不動，寫前備進回合；fn 改壞檔頭（解析不了、版本沒變成 to）就不寫、列進 skipped。
不需要遷移登記的：sources.json 排除列的選填欄（purge 等）、purge-pending.json、回合夾的 moves.jsonl、unlock.json、vault.json、
rulings.json（v0.19.0 沒升 schema）、lint.json、renders.json、set_aside.json、statements-archive.json、findings-archive.json（lint 題的新檔，schema 1）、batches.json、build.json（新檔 schema 1）、entities.json 的 ai_judged（schema 沒改）。
pending 只讀；apply 一個檔失敗不擋其他檔，失敗的列進 skipped（原因一句話）；rewrite 回清單的，那幾筆也併進 skipped。
entities.json schema 2 → 3（標籤記在實體上，D-505 七）：每個 active、有綜合卡的實體，檔頭的標籤行（第八節這個型別的欄、有值的）抄進 tags
（字典外的詞、單選寫兩個的那一欄不抄，列進 skipped）；tags_said 空、備份 by program（回答末尾不講）。沒有綜合卡、型別有標籤欄的
下次整理照 cards todo 的只補標籤項目補（裁定 4），不另外記。
"""
from collections import namedtuple
from pathlib import Path

from kb._lib import cards, entities, inventory, profile
from kb._lib import pending as pending_lib  # 這支自己有 pending()
from kb._lib.io import FileLock, read_json, write_text_atomic

Migration = namedtuple("Migration", "rel current stored rewrite")


class Skip(Exception):
    """這個檔先不遷：args[0] 是原因（一句白話）。"""


def _raw_version(rel):
    """磁碟上那個檔記的 schema_version（沒檔、壞檔、不是整數回 None；沒寫版本當 1，清冊與實體清單最早的版本）。"""
    def read(vault):
        try:
            data = read_json(Path(vault) / rel)
        except (ValueError, OSError):
            return None
        if not isinstance(data, dict):
            return None
        version = data.get("schema_version", 1)
        return version if isinstance(version, int) else None
    return read


def _rewrite_profile(vault, turn_id):
    with profile.lock(vault):
        data = profile.load(vault)
        if data is None:
            return
        if profile.md_sha256(vault) != data.get("md_sha256"):  # md 有沒套用的手改：重渲染會蓋掉，跟 kb init 一樣請先 apply
            raise Skip("設定檔有沒套用的改動，先 kb profile apply 再升級")
        profile.write_locked(vault, data, turn_id)


def _rewrite_inventory(vault, turn_id):
    from kb._lib import turn
    path = inventory._path(vault)
    with FileLock(path):
        turn.backup(vault, inventory.INVENTORY_POSIX, turn_id)
        inventory._write(vault, inventory.load(vault)["entries"])


def _rewrite_entities(vault, turn_id):
    from kb._lib import synthesis
    stored = _raw_version(entities.ENTITIES_POSIX)(vault)
    prof = entities._profile(vault)
    skipped, found = [], {}
    if isinstance(stored, int) and stored < 3:
        for e in entities.load(vault)["entities"]:
            if e.get("status") != "active" or entities.is_self(e) or not e.get("type") or "tags" in e:
                continue
            rel = entities.locate(vault, e) if e.get("card") else None
            if not rel:
                continue
            try:
                front = synthesis.read_front((Path(vault) / rel).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, ValueError) as err:
                skipped.append({"rel": rel, "why": f"綜合卡的標籤沒搬成（{_first_line(err)}）"})
                continue
            rows = {entities.key(t["field"]): t for t in profile.tags_for(prof, e["type"])}
            tags = {}
            for f, v in synthesis.card_tags(front, prof, e["type"]):
                if v == "":
                    continue
                row = rows[entities.key(f)]
                why = entities.tag_refusal(row, entities.tag_words(v))
                if why:
                    skipped.append({"rel": rel, "why": f"「{row['field']}」沒搬進實體清單：{why}"})
                    continue
                tags[row["field"]] = entities.tag_normal(row, v)
            if tags:
                found[e["id"]] = tags
    with entities.lock(vault):
        data = entities.load(vault)
        for e in data["entities"]:
            if e.get("id") in found and "tags" not in e:
                e.update(tags=found[e["id"]], tags_said=[], tags_at=entities._now_stamp())
        entities._save(vault, data, turn_id, by="program")
    return skipped


def _rewrite_pending(vault, turn_id):
    """schema 1 → 2（lint 題，D-226）：load 補 set_aside、returned，照 pending 自己的寫法寫回（兩檔備進回合、重渲染）。"""
    pending_lib.refresh(vault, turn_id)


STATE_FILES = (
    Migration(profile.PROFILE_POSIX, lambda: profile.SCHEMA_VERSION, profile.stored_schema, _rewrite_profile),
    Migration(inventory.INVENTORY_POSIX, lambda: inventory.SCHEMA_VERSION, _raw_version(inventory.INVENTORY_POSIX),
              _rewrite_inventory),
    Migration(entities.ENTITIES_POSIX, lambda: entities.SCHEMA_VERSION, _raw_version(entities.ENTITIES_POSIX),
              _rewrite_entities),
    Migration(pending_lib.PENDING_POSIX, lambda: pending_lib.SCHEMA_VERSION, _raw_version(pending_lib.PENDING_POSIX),
              _rewrite_pending),
)
CARD_HEADER_MIGRATIONS = []


def pending(vault):
    """要遷的狀態檔 [{"rel", "from", "to"}]：存的 schema 比現在舊的。只讀；沒檔、讀不了的不算。"""
    out = []
    for m in STATE_FILES:
        stored, current = m.stored(vault), m.current()
        if isinstance(stored, int) and stored < current:
            out.append({"rel": m.rel, "from": stored, "to": current})
    return out


def _first_line(e):
    text = str(e).strip().splitlines()
    return text[0] if text else type(e).__name__


def _migrate_cards(vault, turn_id, skipped):
    """卡的檔頭遷移；回遷了幾張。表是空的不掃卡。"""
    if not CARD_HEADER_MIGRATIONS:
        return 0
    from kb._lib import turn
    found, _broken = cards.scan_cards(vault)
    count = 0
    for card in found.values():
        rel = card["path"]
        version = str(card["front"].get("範本版本"))
        mig = next((m for m in CARD_HEADER_MIGRATIONS if str(m["from"]) == version), None)
        if mig is None:
            continue
        target = Path(vault) / rel
        try:
            text = target.read_text(encoding="utf-8")
            new = mig["fn"](text)
            if str(cards.parse_front(new).get("範本版本")) != str(mig["to"]):
                raise ValueError("遷移後範本版本不對")
            turn.backup(vault, rel, turn_id)
            write_text_atomic(target, new)
        except (ValueError, OSError) as e:
            skipped.append({"rel": rel, "why": f"卡的檔頭沒遷成（{_first_line(e)}）"})
            continue
        count += 1
    return count


def apply(vault, turn_id):
    """遷移全部要遷的。回 {"migrated": [rel…], "skipped": [{"rel","why"}], "cards": 遷了幾張卡的檔頭}。
    一個檔失敗（Skip、讀不了、寫不進去）列進 skipped，不擋其他檔。"""
    migrated, skipped = [], []
    todo = {p["rel"] for p in pending(vault)}
    for m in STATE_FILES:
        if m.rel not in todo:
            continue
        try:
            extra = m.rewrite(vault, turn_id)
        except Skip as e:
            skipped.append({"rel": m.rel, "why": str(e)})
        except (ValueError, OSError) as e:
            skipped.append({"rel": m.rel, "why": f"沒遷成（{_first_line(e)}）"})
        else:
            migrated.append(m.rel)
            skipped += extra or []
    return {"migrated": migrated, "skipped": skipped, "cards": _migrate_cards(vault, turn_id, skipped)}
