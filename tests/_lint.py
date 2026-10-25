"""lint 測試共用：tests/_entities 的知識庫（實體清單、兩張舊範本的綜合卡）、寫一張合法的綜合卡、建檢查用的 Context。"""
from pathlib import Path

from tests import _entities as E
from kb._lib import entities, synthesis, turn  # noqa: E402
from kb.lint import runner  # noqa: E402

XINYI_REL = "案子/信義王/信義王.md"


def make():
    """回 (tmp, V, raw)。"""
    return E.make_entity_vault(with_entities=True)


def write_synthesis(V, name="信義王", body="## 現況\n- 案子進行中\n", today=None):
    """照 synthesis.header_for 寫一張驗得過的綜合卡；body 接在「# <名稱>」之後。回相對路徑。"""
    data = entities.load(V)
    e, _hit = entities.find(data, name)
    ms = entities.mounts(V, data).get(e["name"], [])
    rel = synthesis.card_rel(e)
    text = synthesis.header_for(V, e, ms, today=today) + f"# {e['name']}\n\n{body}"
    p = Path(V) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")
    return rel


def write_card(V, rel, title, names=("信義王",), kind="報價"):
    """E.write_card 寫一張第二版檔案卡，卡型換成 kind。回卡編號。"""
    import re
    from kb._lib import cards
    p = Path(V) / E.write_card(V, rel, title, list(names))
    text = re.sub(r"^卡型: .*$", f"卡型: {kind}", p.read_text(encoding="utf-8"), count=1, flags=re.M)
    p.write_text(text, encoding="utf-8", newline="\n")
    return cards.parse_front(text)["編號"]


def ctx(V, today=None, background=False):
    return runner.Context(V, today=today, turn_id=turn.start(V, None, "")["turn"], background=background)


def kinds(found):
    return sorted(f["kind"] for f in found)


def by_kind(found, kind):
    return [f for f in found if f["kind"] == kind]
