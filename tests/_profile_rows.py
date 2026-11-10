"""測試用的設定檔寫法（原本住 test_entity_fields，#65 拿掉數字欄時搬出來；kb money 的測試還在用，乙段一起刪）。"""
import json
from pathlib import Path

from tests import _entities as E
from kb._lib import profile  # noqa: E402


def field_row(type_, field, unit=""):
    return {"type": type_, "field": field, "unit": unit, "source": "confirmed", "date": E.DAY}


def write_profile(V, **changes):
    """改 profile.json（md 跟著重渲染、sha 對得上）。changes 的值是 None 就拿掉那個鍵。"""
    data = profile.load(V)
    for k, v in changes.items():
        if v is None:
            data.pop(k, None)
        else:
            data[k] = v
    text = profile.render_text(data)
    (Path(V) / profile.MD_POSIX).write_text(text, encoding="utf-8", newline="\n")
    data["md_sha256"] = profile.sha256_text(text)
    (Path(V) / profile.PROFILE_POSIX).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return data
