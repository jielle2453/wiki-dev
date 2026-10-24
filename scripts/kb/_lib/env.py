"""按機器記的提示記號 .system/env.json（schema 1，D-021 補、D-094 補）：找不到的來源每台電腦只在開場報一次。
{"schema_version": 1, "machines": {"<機器名>": {"missing_sources_reported": {"<來源 id 或別名>": "YYYY-MM-DD"},
                                              "vault_path": "D:/知識庫", "backup_dir": "E:/備份"}}}
vault_path、backup_dir 是備份還原與換電腦加的選填欄（D-206、D-204）：這台電腦上次記的知識庫位置（realpath、正斜線）與備份放哪；
跟 missing_sources_reported 各管各的，改一個不動另一個。
讀改寫包 FileLock；壞 JSON 或形狀不對當空的重建（這個檔只有提示記號，別讓它拖垮開場，I-046）。
"""
import json
import platform
from datetime import date
from pathlib import Path

from kb._lib.io import FileLock, write_json_atomic

ENV_REL = Path(".system") / "env.json"
KEY = "missing_sources_reported"


def machine_name():
    return platform.node() or "unknown"


def _path(vault):
    return Path(vault) / ENV_REL


def _load(vault):
    try:
        with open(_path(vault), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("machines"), dict):
        return {"schema_version": 1, "machines": {}}
    return data


def _machine(data, create=False):
    """這台電腦的紀錄（物件）；沒有回 None，create 時補一份空的。"""
    machine = data["machines"].get(machine_name())
    if not isinstance(machine, dict):
        if not create:
            return None
        machine = {}
        data["machines"][machine_name()] = machine
    return machine


def _marks(data, create=False):
    machine = _machine(data, create)
    if machine is None or (not isinstance(machine.get(KEY), dict) and not create):
        return {}
    if not isinstance(machine.get(KEY), dict):
        machine[KEY] = {}
    return machine[KEY]


def missing_reported(vault, src_id):
    return src_id in _marks(_load(vault))


def mark_missing(vault, src_ids):
    """記成已報過；已有的保留第一次的日期。"""
    src_ids = list(src_ids)
    if not src_ids:
        return
    p = _path(vault)
    p.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(p):
        data = _load(vault)
        marks = _marks(data, create=True)
        for src_id in src_ids:
            marks.setdefault(src_id, date.today().isoformat())
        write_json_atomic(p, data)


def clear_missing(vault, src_ids):
    """來源又找得到：清掉記號，之後再失蹤再報一次。沒有要清的不寫檔。"""
    src_ids = list(src_ids)
    if not src_ids or not any(missing_reported(vault, s) for s in src_ids):
        return
    p = _path(vault)
    with FileLock(p):
        data = _load(vault)
        marks = _marks(data)
        for src_id in src_ids:
            marks.pop(src_id, None)
        write_json_atomic(p, data)


def _text_of(vault, key):
    machine = _machine(_load(vault))
    value = machine.get(key) if machine else None
    return value if isinstance(value, str) and value else None


def _set_text(vault, key, value):
    p = _path(vault)
    p.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(p):
        data = _load(vault)
        _machine(data, create=True)[key] = str(value)
        write_json_atomic(p, data)


def vault_path(vault):
    """這台電腦記的知識庫位置；沒記過回 None。只讀。"""
    return _text_of(vault, "vault_path")


def set_vault_path(vault, path):
    _set_text(vault, "vault_path", path)


def backup_dir(vault):
    """這台電腦記的備份夾；沒記過回 None。"""
    return _text_of(vault, "backup_dir")


def set_backup_dir(vault, path):
    _set_text(vault, "backup_dir", path)


def other_machines(vault):
    """別台電腦有紀錄的機器名（照檔案裡的順序）；這台自己不算。"""
    data = _load(vault)
    return [name for name, rec in data["machines"].items() if name != machine_name() and isinstance(rec, dict)]


def vault_paths_elsewhere(vault):
    """別台電腦記的知識庫位置（沒記的略過）。"""
    data = _load(vault)
    return [rec["vault_path"] for name, rec in data["machines"].items()
            if name != machine_name() and isinstance(rec, dict) and isinstance(rec.get("vault_path"), str)
            and rec["vault_path"]]
