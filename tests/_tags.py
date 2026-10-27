"""測試共用（標籤字典）：在 tests/_entities 的知識庫設定檔第八節放字典、寫帶標籤行的綜合卡。"""
import json
from pathlib import Path

from tests import _entities as E
from kb._lib import entities, profile, synthesis  # noqa: E402

XINYI_REL = "案子/信義王/信義王.md"
DAAN_REL = "案子/大安陳/大安陳.md"
DAY = E.DAY


def tag(type_, field, words, multi=True):
    return {"type": type_, "field": field, "words": list(words), "multi": multi, "source": "confirmed", "date": DAY}


DEFAULT_TAGS = (tag("案子", "工種", ["水電", "木作", "磁磚", "系統櫃"]), tag("案子", "階段", ["報價", "施工", "完工"], False))


def set_tags(V, tags=DEFAULT_TAGS):
    """直接改 profile.json 的 tags（md 跟著重渲染、sha 對得上）。"""
    data = profile.load(V)
    data["tags"] = [dict(t) for t in tags]
    text = profile.render_text(data)
    (Path(V) / profile.MD_POSIX).write_text(text, encoding="utf-8", newline="\n")
    data["md_sha256"] = profile.sha256_text(text)
    (Path(V) / profile.PROFILE_POSIX).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def header(V, eid, today="2026-10-20"):
    data = entities.load(V)
    mounts = entities.mounts(V, data)
    e = next(x for x in data["entities"] if x["id"] == eid)
    return synthesis.header_for(V, e, mounts.get(e["name"], []), today)


def with_tag_lines(header_text, lines):
    """檔頭結尾的 --- 之前插標籤行（lines 是「欄: 值」字串）。"""
    body = header_text.rstrip("\n")
    assert body.endswith("\n---")
    return body[:-4] + "".join(f"\n{x}" for x in lines) + "\n---\n"


def strip_tag_lines(header_text):
    """header 裡 synthesis.KEYS 以外的行拿掉（拿到不帶標籤的檔頭）。"""
    out = []
    for line in header_text.splitlines():
        key = line.partition(":")[0].strip()
        if line in ("---",) or line.startswith("  - ") or key in synthesis.KEYS:
            out.append(line)
    return "\n".join(out) + "\n"


SETUP_TURN = "20000101-000000-setup"


def write_synthesis(V, eid, name, rel, lines=(), body=None, turn_id=SETUP_TURN, sync=True):
    """照現行檔頭寫一張綜合卡（標籤行換成 lines）。sync：照 PostToolUse 把標籤行抄進實體清單的正本（D-505，備進 turn_id）。回文字。"""
    text = with_tag_lines(strip_tag_lines(header(V, eid)), lines)
    text = E.synthesis_text(text, name) if body is None else E.synthesis_text(text, name, body)
    p = Path(V) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")
    if sync:
        synthesis.copy_tags(V, rel, turn_id)
        text = p.read_text(encoding="utf-8")
    return text


def clear_tags(V, eid):
    """實體清單那一筆拿掉 tags、tags_said（還沒標過的樣子）。"""
    data = entities.load(V)["entities"]
    for e in data:
        if e["id"] == eid:
            for k in ("tags", "tags_said", "tags_at"):
                e.pop(k, None)
    E.put_entities(V, data)
