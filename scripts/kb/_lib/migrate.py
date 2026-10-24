"""狀態檔與卡檔頭的遷移表（升級打包 要做的事 2，D-054、D-215）：kb upgrade --finish 在新對話開場叫它轉格式。

STATE_FILES 是一張表：哪個檔、現在的 schema 版本、磁碟上存的版本、怎麼寫回。各檔用自己的 load（已有的遷移，在記憶體補欄位）讀、
照自己的寫法寫回（寫前備進回合，versions revert 退得回）。之後新增遷移的題，在這張表加一列（_lib/migrate.py 的表有變，
發行程式 tools/release.py 就不准標成小修，D-217）。
CARD_HEADER_MIGRATIONS 是卡的檔頭遷移：[{"from": 舊範本版本, "to": 新範本版本, "fn": 整張卡的文字 → 新文字}]，目前沒有要遷的（空表，D-054）；
只改檔頭機器欄位、正文不動，寫前備進回合；fn 改壞檔頭（解析不了、版本沒變成 to）就不寫、列進 skipped。
不需要遷移登記的：sources.json 排除列的選填欄（purge 等）、purge-pending.json、回合夾的 moves.jsonl、unlock.json、vault.json、
rulings.json（v0.19.0 沒升 schema）、batches.json、build.json（新檔 schema 1）、entities.json 的 ai_judged（schema 沒改）。
pending 只讀；apply 一個檔失敗不擋其他檔，失敗的列進 skipped（原因一句話）。
"""
from collections import namedtuple
from pathlib import Path

from kb._lib import cards, entities, inventory, profile
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
    with entities.lock(vault):
        entities._save(vault, entities.load(vault), turn_id)


STATE_FILES = (
    Migration(profile.PROFILE_POSIX, lambda: profile.SCHEMA_VERSION, profile.stored_schema, _rewrite_profile),
    Migration(inventory.INVENTORY_POSIX, lambda: inventory.SCHEMA_VERSION, _raw_version(inventory.INVENTORY_POSIX),
              _rewrite_inventory),
    Migration(entities.ENTITIES_POSIX, lambda: entities.SCHEMA_VERSION, _raw_version(entities.ENTITIES_POSIX),
              _rewrite_entities),
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
            m.rewrite(vault, turn_id)
        except Skip as e:
            skipped.append({"rel": m.rel, "why": str(e)})
        except (ValueError, OSError) as e:
            skipped.append({"rel": m.rel, "why": f"沒遷成（{_first_line(e)}）"})
        else:
            migrated.append(m.rel)
    return {"migrated": migrated, "skipped": skipped, "cards": _migrate_cards(vault, turn_id, skipped)}
