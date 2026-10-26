"""綜合卡（D-036、D-038、D-114～D-121；實體與綜合卡第 2 點）：檔頭、驗證、快取渲染、待辦清單。

綜合卡住 <型別>/<名稱>/<名稱>.md（D-046 的 Z1），一個實體一張。檔頭由 header_for 印給製卡者照抄；
「整理到」是寫卡時的依據：讀過的檔案卡與各自指紋前 12 碼，加上它有效的口述（s-）、掛在它或它的卡上的有效裁示（r-）
與有效推算（c-，answer 第 4 點），這三種的指紋欄寫 -（note 改知識釐清第一點）；PostToolUse 用 validate 驗它等於現行的依據；
「檔案卡」「相關實體」兩欄是快取（D-118），render_cache 只重寫這兩欄、備份帶 by program（D-075 不數）。
buckets 給 cards todo：synthesis_new（D-114 門檻數檔案卡加有效口述，裁示不算）、synthesis_stale（D-121）、synthesis_broken、
entity_drift（D-057）；前兩桶每項帶這個實體的口述、裁示與推算（statements、rulings、findings），added／changed／removed
每項帶 source。推算不算進建卡門檻。
健檢標的要更新（lint 題，.system/lint.json 的 synthesis_fix：出處點不開、有空段、設定檔改了）併進 synthesis_stale：
本來就要更新的那項多 reason 與 ids，本來不用更新的也列一項（added／changed／removed 是空的），整理時照現有流程改寫；
卡被改寫之後指紋變了，那筆就不算（lint.state.fixes）。
檔頭用 cards.parse_front 解析（同一套 YAML 子集）。
標籤行（標籤字典第三節，D-234）：KEYS 之後、照設定檔第八節那個型別的欄一欄一行（可多選 [a, b]、單選一個詞、看過沒有寫 []）；
沒有那一行是還沒照字典標過。problems 驗欄與詞在字典裡、單選不超過一個；設定檔讀不到時不驗標籤行（寫 log）。
header_for 帶卡上現有的標籤行（第八節已沒有的欄不帶），還沒有綜合卡的照第八節列出欄、值留空；retag 只改一行（kb profile tag）。
"""
import re
from datetime import date, datetime
from pathlib import Path

from kb._lib import config, entities, profile
from kb._lib.io import write_text_atomic

TEMPLATE_VERSION = "1"
KEYS = ("編號", "型別", "大類", "名稱", "別名", "範本版本", "整理到", "更新日", "檔案卡", "相關實體")
CACHE_KEYS = ("檔案卡", "相關實體")
BASE_SECTIONS = ("現況", "紀事", "推算")
BLOCK_KEYS = ("整理到", "檔案卡")  # 一行一項（"  - …"）；其他清單寫一行 [a, b]
LIST_KEYS = ("別名", "相關實體") + BLOCK_KEYS
BASE_HINTS = {"現況": "這件事現在怎樣：一點一行、事實變了就改寫，每點結尾〔f-…〕（口述是〔s-…〕）",
              "紀事": "日期倒序、只增不改：決定、改版、關鍵事件",
              "推算": "從多張卡算出來的：結果、算法、依據、算的日期；沒有就整段不寫"}
STALE_CODE = "synced"
REDO = "redo"  # 整理到 那行的指紋欄：客戶說卡讀錯了，等卡重寫（實作回報裁定 1）
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# validate 的問題代號：這些一出就不再往下驗（後面的比對沒有意義）
GATING = ("parse", "missing_key", "unknown", "self", "removed", "inferred")


def card_rel(entity):
    return entities.card_rel(entity)


def category_text(prof, type_name):
    """型別的大類，中文（對象、事、物、主題）；型別不在表回空字串。"""
    row = next((t for t in (prof or {}).get("types") or [] if entities.key(t["name"]) == entities.key(type_name)), None)
    return profile._REVERSED[0].get(row.get("category"), "") if row else ""


def sections_for(prof, type_):
    """綜合卡要寫的段：固定三段（現況、紀事、推算）加設定檔第四節那個型別的列，[{"name","required","hint"}]。"""
    out = [{"name": n, "required": False, "hint": BASE_HINTS[n]} for n in BASE_SECTIONS]
    for s in (prof or {}).get("synthesis_sections") or []:
        if entities.key(s.get("type")) == entities.key(type_):
            out += [{"name": x["name"], "required": bool(x.get("required")), "hint": x.get("hint", "")}
                    for x in s.get("sections") or []]
    return out


# ---------- 快取欄 ----------

def _date_key(m):
    d = m.get("date") or ""
    return (1, d) if _DATE.match(d) else (0, "")


def card_lines(mounts_of_it):
    """檔案卡 欄：每行「<編號> <文件日期> <標題>」照文件日期倒序（未載的排最後），同日照編號。"""
    ordered = sorted(sorted(mounts_of_it, key=lambda m: m["id"]), key=_date_key, reverse=True)
    return [f"{m['id']} {m.get('date') or '未載'} {m.get('title') or ''}".rstrip() for m in ordered]


def synced_lines(mounts_of_it, stmts=(), ruls=(), redo=(), finds=()):
    """整理到 欄：檔案卡每行「<編號> <fp>」，口述、裁示與推算每行「<編號> -」，全部照編號排（c-、f-、r-、s-）。
    redo 是 redo 記號還有效的卡編號（cards redo 之後、卡還沒重寫）：那張卡的指紋欄寫 redo（實作回報裁定 1）。"""
    lines = {m["id"]: f"{m['id']} {REDO if m['id'] in redo else (m.get('fp') or '')}".rstrip() for m in mounts_of_it}
    lines.update({x["id"]: f"{x['id']} -" for x in list(stmts) + list(ruls) + list(finds)})
    return [lines[k] for k in sorted(lines)]


def knowledge(vault):
    """口述清單、裁示與推算清單（讀一次給整批用）、實體清單（推算記的名稱轉成現在的名稱）、清冊的 redo 記號 {卡編號: 記號}；
    titles 是檔案卡標題、fctx 是推算算過期要的東西，要用時才讀（_titles、_finding_ctx）。讀不到丟 ValueError（帶檔名）。"""
    from kb._lib import findings, inventory, rulings, statements
    marks = {e["id"]: e["redo"] for e in inventory.load(vault)["entries"] if e.get("redo") and e.get("id")}
    return {"statements": statements.load(vault), "rulings": rulings.load(vault), "findings": findings.load(vault),
            "entities": entities.load(vault), "titles": None, "fctx": None, "redo": marks}


def redo_ids(vault, know, mounts_of_it):
    """這幾張卡裡 redo 記號還有效的（卡檔現在的 sha256 前 12 碼等於記號，也就是 cards redo 之後還沒重寫）。"""
    from kb._lib import inventory
    marks = know.get("redo") or {}
    return {m["id"] for m in mounts_of_it if m["id"] in marks and inventory.card_sha(vault, m["path"]) == marks[m["id"]]}


def basis(know, name, mounts):
    """一個實體除了檔案卡以外的依據：(有效口述, 掛在它或它的卡上的有效裁示, 有效推算)。"""
    from kb._lib import findings, rulings, statements
    return (statements.active_for(know["statements"], name), rulings.for_entity(know["rulings"], name, mounts),
            findings.active_for(know["findings"], name, know.get("entities")))


def _titles(vault, know):
    if know["titles"] is None:
        from kb._lib import agenda
        know["titles"] = agenda.card_titles(vault)
    return know["titles"]


def _finding_ctx(vault, know, mounts):
    if know.get("fctx") is None:
        from kb._lib import findings
        know["fctx"] = findings.context(vault, know.get("entities"), mounts)
    return know["fctx"]


def finding_brief(vault, know, c, mounts):
    from kb._lib import findings
    return findings.brief(vault, c, _titles(vault, know), _finding_ctx(vault, know, mounts))


def statement_brief(s):
    return {"id": s["id"], "text": s.get("text"), "date": s.get("date")}


def ruling_brief(vault, know, r):
    from kb._lib import rulings
    titles = _titles(vault, know)
    return {"id": r["id"], "kind": r.get("kind"), "text": r.get("text"),
            "cards": [{"id": cid, "title": titles.get(cid)} for cid in rulings.card_ids(r)]}


def related(data, mounts, entity):
    """跟它共用至少一張檔案卡、不是客戶自己、status 不是 merged 的實體名稱，照共用張數多到少（同數照名稱）。"""
    mine = {m["id"] for m in mounts.get(entity["name"], [])}
    by_name = {e["name"]: e for e in data["entities"] if e.get("status") != "merged"}
    counts = {}
    for name, ms in mounts.items():
        other = by_name.get(name)
        if other is None or other.get("id") == entity.get("id") or entities.is_self(other):
            continue
        n = sum(1 for m in ms if m["id"] in mine)
        if n:
            counts[name] = n
    return sorted(counts, key=lambda n: (-counts[n], n))


# ---------- 檔頭 ----------

def tag_value_text(v):
    """標籤行的值：清單 [a, b]（空的 []）、單一個詞照寫、None 是留空給製卡者填。"""
    if v is None:
        return ""
    if isinstance(v, list):
        return f"[{', '.join(v)}]"
    return str(v)


def tag_line(field, v):
    text = tag_value_text(v)
    return f"{field}: {text}" if text else f"{field}:"


def _front_text(front, tags=()):
    out = ["---"]
    for k in KEYS:
        if k not in front:
            continue
        v = front[k]
        if k in BLOCK_KEYS:
            out.append(f"{k}:")
            out.extend(f"  - {x}" for x in v)
        elif isinstance(v, list):
            out.append(f"{k}: [{', '.join(v)}]")
        else:
            out.append(f"{k}: {v}")
    out.extend(tag_line(f, v) for f, v in tags)
    out.append("---")
    return "\n".join(out) + "\n"


def card_tags(front, prof, type_):
    """卡檔頭上、第八節這個型別有的標籤行 [(欄, 值)]，照第八節的順序；第八節已沒有的欄不帶。"""
    have = {entities.key(k): v for k, v in front.items() if k not in KEYS}
    return [(t["field"], have[entities.key(t["field"])]) for t in profile.tags_for(prof, type_)
            if entities.key(t["field"]) in have]


def header_tags(vault, entity, prof):
    """header_for 要帶的標籤行：這個實體的綜合卡在、讀得懂就帶卡上現有的（字典外的詞、單選寫了兩個的那一欄留空，
    不把錯的帶回去）；沒有卡（或讀不懂）照第八節列出欄、值留空。"""
    from kb._lib import cards
    p = Path(vault) / card_rel(entity)
    if p.is_file():
        try:
            front = cards.parse_front(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            front = None
        if front is not None:
            rows = {entities.key(t["field"]): t for t in profile.tags_for(prof, entity.get("type"))}
            return [(f, v if _tag_ok(rows[entities.key(f)], v) else None)
                    for f, v in card_tags(front, prof, entity.get("type"))]
    return [(t["field"], None) for t in profile.tags_for(prof, entity.get("type"))]


def _tag_ok(row, v):
    words = tag_words(v)
    known = {entities.key(w) for w in row.get("words") or []}
    return all(entities.key(w) in known for w in words) and (row.get("multi") or len(words) <= 1)


def header_for(vault, entity, mounts_of_it, today=None, data=None, mounts=None, prof=None, know=None, tags=None):
    """印給製卡者照抄的綜合卡檔頭（資料與介面格式那個樣子）。data、mounts、prof、know 沒給自己讀。
    tags 是標籤行 [(欄, 值)]；沒給照 header_tags（卡上現有的，或照第八節留空）。"""
    data = data if data is not None else entities.load(vault)
    mounts = mounts if mounts is not None else entities.mounts(vault, data)
    prof = prof if prof is not None else entities._profile(vault)
    know = know if know is not None else knowledge(vault)
    stmts, ruls, finds = basis(know, entity["name"], mounts)
    return _front_text({
        "編號": entity["id"], "型別": entity.get("type"), "大類": category_text(prof, entity.get("type")),
        "名稱": entity["name"], "別名": list(entity.get("aliases") or []), "範本版本": TEMPLATE_VERSION,
        "整理到": synced_lines(mounts_of_it, stmts, ruls, redo_ids(vault, know, mounts_of_it), finds),
        "更新日": today or date.today().isoformat(),
        "檔案卡": card_lines(mounts_of_it), "相關實體": related(data, mounts, entity)},
        tags if tags is not None else header_tags(vault, entity, prof))


def tag_words(v):
    """標籤行的值攤成詞的清單（單選的一個詞也算一個）。"""
    if isinstance(v, list):
        return list(v)
    return [v] if v not in (None, "") else []


def tagged_cards(vault, type_name, data=None):
    """這個型別 active、不是客戶自己、有綜合卡的實體：[(實體, 相對路徑, 檔頭)]，讀不懂的卡跳過（kb profile tag、補標籤用）。"""
    from kb._lib import cards
    data = data if data is not None else entities.load(vault)
    out = []
    for e in data["entities"]:
        if (e.get("status") != "active" or entities.is_self(e) or not e.get("type")
                or entities.key(e["type"]) != entities.key(type_name)):
            continue
        rel = card_rel(e) if (Path(vault) / card_rel(e)).is_file() else (entities.locate(vault, e) if e.get("card") else None)
        if not rel:
            continue
        try:
            front = cards.parse_front((Path(vault) / rel).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        out.append((e, rel, front))
    return out


def front_tag(front, field):
    """檔頭上 field 那一行的值（比對照 entities.key）；沒有這一行回 None。"""
    for k, v in front.items():
        if k not in KEYS and entities.key(k) == entities.key(field):
            return v
    return None


def tag_changes(vault, turn_ids):
    """這幾個回合寫過的綜合卡（回合帳裡 <型別>/<名稱>/<名稱>.md），標籤行跟那一回合的備份比多了的詞（新寫的卡全部算）：
    [(名稱, [(欄, [新加的詞])])]，照第一次寫的順序；拿掉的不算（標籤字典第五節）。只讀。"""
    from kb._lib import cards, turn
    prof = entities._profile(vault)
    types = {entities.key(t["name"]) for t in prof.get("types") or []}
    olds, order = {}, []
    for tid in turn_ids:
        for row in turn.entries(vault, tid):
            rel = str(row.get("path") or "")
            parts = rel.split("/")
            if (len(parts) != 3 or parts[2] != f"{parts[1]}.md" or entities.key(parts[0]) not in types
                    or rel in olds):
                continue
            old = None
            if row.get("action") != "create":
                try:
                    old = (Path(vault) / turn.VERSIONS_REL / tid / "files" / rel).read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
            olds[rel] = old
            order.append(rel)
    out = []
    for rel in order:
        try:
            front = cards.parse_front((Path(vault) / rel).read_text(encoding="utf-8"))
            before = cards.parse_front(olds[rel]) if olds[rel] is not None else {}
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        had = {entities.key(f): {entities.key(w) for w in tag_words(v)}
               for f, v in card_tags(before, prof, front.get("型別"))}
        added = []
        for f, v in card_tags(front, prof, front.get("型別")):
            more = [w for w in tag_words(v) if entities.key(w) not in had.get(entities.key(f), set())]
            if more:
                added.append((f, more))
        if added:
            out.append((front.get("名稱") or rel.split("/")[1], added))
    return out


DROP = object()  # retag 的 fn 回它：拿掉那一行


def retag(text, field, fn, new_field=None):
    """只改檔頭裡「field:」那一行（kb profile tag，D-237）：fn(現在的值) 回新值（清單、一個詞，或 DROP 拿掉那一行）；
    new_field 給了換鍵。其他行與內文原樣（含換行字元）；沒有那一行原樣回。"""
    from kb._lib import cards
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        bare = line.rstrip("\r\n")
        if i == 0:
            if bare.lstrip("﻿") != "---":
                return text
            continue
        if bare == "---":
            return text
        key, sep, raw = bare.partition(":")
        if not sep or bare.startswith(" ") or entities.key(key.strip()) != entities.key(field):
            continue
        value = fn([] if not raw.strip() else cards._value(raw))
        if value is DROP:
            lines[i] = ""
        else:
            if isinstance(value, list):
                value = list(dict.fromkeys(value))
            lines[i] = f"{new_field or key.strip()}: {tag_value_text(value)}" + line[len(bare):]
        return "".join(lines)
    return text


def replace_front(text, updates):
    """只換檔頭裡 updates 給的鍵（一行的值或「鍵:」下接「  - 項」的整塊），其他行原樣；鍵不在檔頭就不加。"""
    lines = text.splitlines(keepends=True)
    out, i, in_front = [], 0, False
    while i < len(lines):
        line = lines[i]
        bare = line.rstrip("\r\n")
        if i == 0 and bare.lstrip("﻿") == "---":
            in_front = True
        elif in_front and bare == "---":
            in_front = False
        elif in_front and bare.partition(":")[0].strip() in updates and not bare.startswith(" "):
            k = bare.partition(":")[0].strip()
            v = updates[k]
            i += 1
            while i < len(lines) and lines[i].startswith(("  - ", "- ")):
                i += 1
            if k in BLOCK_KEYS:
                out.append(f"{k}:\n")
                out.extend(f"  - {x}\n" for x in v)
            elif isinstance(v, list):
                out.append(f"{k}: [{', '.join(v)}]\n")
            else:
                out.append(f"{k}: {v}\n")
            continue
        out.append(line)
        i += 1
    return "".join(out)


def replace_title(text, old, new):
    """正文第一個「# <old>」換成「# <new>」（改名後卡才驗得過）；其他行原樣。"""
    lines = text.splitlines(keepends=True)
    seen = 0
    for i, line in enumerate(lines):
        if line.rstrip("\r\n") == "---":
            seen += 1
            continue
        if seen >= 2 and line.rstrip("\r\n").rstrip() == f"# {old}":
            lines[i] = f"# {new}" + line[len(line.rstrip("\r\n")):]
            break
    return "".join(lines)


def _body_lines(text):
    lines = str(text).lstrip("﻿").splitlines()
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            return [x.rstrip() for x in lines[i + 1:]]
    return []


# ---------- 驗證 ----------

def problems(vault, rel, text, data, mounts, prof, know=None):
    """綜合卡的問題 [(代號, 原因)]，照 validate 的順序；GATING 的一出就只回它一個。know 沒給自己讀。"""
    from kb._lib import cards
    try:
        front = cards.parse_front(text)
    except ValueError as e:
        return [("parse", f"檔頭解析不了：{e}")]
    for k in KEYS:
        if k not in front:
            return [("missing_key", f"檔頭少了「{k}」")]
    eid = front["編號"]
    entry = next((e for e in data["entities"] if e.get("id") == eid), None) if isinstance(eid, str) else None
    if entry is None:
        return [("unknown", f"編號 {eid} 不在實體清單")]
    if entities.is_self(entry):
        return [("self", "這是你自己（關於你），不寫綜合卡")]
    if entry.get("status") != "active":
        return [("removed", "這個實體已移除")]
    if entry.get("source") == "inferred":
        return [("inferred", "還沒跟客戶確認名稱，先問再寫")]
    out = []
    want = card_rel(entry)
    if rel.casefold() != want.casefold():
        out.append(("path", f"綜合卡該放在 {want}"))
    expect = {"型別": entry.get("type"), "大類": category_text(prof, entry.get("type")), "名稱": entry["name"],
              "別名": list(entry.get("aliases") or [])}
    for k, v in expect.items():
        if front[k] != v:
            out.append(("field", f"「{k}」照 kb cards todo 給的檔頭抄"))
            break
    if front["範本版本"] != TEMPLATE_VERSION:
        out.append(("version", f"範本版本該是 {TEMPLATE_VERSION}"))
    have = front["整理到"]
    know = know if know is not None else knowledge(vault)
    stmts, ruls, finds = basis(know, entry["name"], mounts)
    ms = mounts.get(entry["name"], [])
    if not isinstance(have, list) or sorted(have) != sorted(synced_lines(ms, stmts, ruls, redo_ids(vault, know, ms), finds)):
        out.append((STALE_CODE, "整理到不是現行的，重跑 kb cards todo 拿新檔頭"))
    day = front["更新日"]
    ok = isinstance(day, str) and bool(_DATE.match(day))
    if ok:
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            ok = False
    if not ok:
        out.append(("date", "更新日要寫 YYYY-MM-DD"))
    body = _body_lines(text)
    if f"# {entry['name']}" not in body or "## 現況" not in body:
        out.append(("body", f"正文要有 # {entry['name']} 與 ## 現況"))
    out += _tag_problems(vault, front, prof, entry.get("type"))
    return out


def _tag_dictionary(vault, prof, type_):
    """驗標籤行用的這個型別的欄 {key: 第八節那列}；設定檔讀不到回 None（不驗，寫 log）。
    prof 的第八節是空的時再讀一次設定檔確認（entities._profile 讀不到時給的是預設值）。"""
    rows = profile.tags_for(prof, type_)
    if not rows and not (prof or {}).get("tags"):
        try:
            real = profile.load(vault)
        except ValueError:
            real = None
        if real is None:
            from kb._lib import ledger
            ledger.log_error(vault, "設定檔讀不到，綜合卡的標籤行沒有驗", source="synthesis")
            return None
        rows = profile.tags_for(real, type_)
    return {entities.key(t["field"]): t for t in rows}


def _tag_problems(vault, front, prof, type_):
    extra = [k for k in front if k not in KEYS]
    if not extra:
        return []
    fields = _tag_dictionary(vault, prof, type_)
    if fields is None:
        return []
    for k in extra:
        row = fields.get(entities.key(k))
        if row is None:
            return [("tag", f"檔頭的「{k}」不是這類卡的標籤欄（第八節沒有）")]
        v = front[k]
        words = v if isinstance(v, list) else [v]
        if not row.get("multi") and len(words) > 1:
            return [("tag", f"「{row['field']}」只能選一個詞")]
        known = {entities.key(w) for w in row.get("words") or []}
        for w in words:
            if entities.key(w) not in known:
                return [("tag", f"「{w}」不在「{row['field']}」的字典裡：先問客戶要不要加"
                                f"（kb profile add 標籤 型別={row['type']} 欄名={row['field']} 詞={w}），不要自己加")]
    return []


def safe_problems(vault, rel, text, data, mounts, prof, know=None):
    """problems 整段包住：任何例外都當成解析不了（同 cards.safe_problems）。"""
    try:
        return problems(vault, rel, text, data, mounts, prof, know)
    except Exception as e:  # noqa: BLE001
        return [("parse", f"檔頭解析不了：{type(e).__name__}")]


def validate(vault, rel, data=None, mounts=None, prof=None, know=None):
    """PostToolUse 與測試用：回 (ok, reason)，只報第一個錯。"""
    try:
        text = (Path(vault) / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        return False, f"檔頭解析不了：{type(e).__name__}"
    try:
        data = data if data is not None else entities.load(vault)
        mounts = mounts if mounts is not None else entities.mounts(vault, data)
        prof = prof if prof is not None else entities._profile(vault)
        know = know if know is not None else knowledge(vault)
    except Exception as e:  # noqa: BLE001
        return False, f"檔頭解析不了：{type(e).__name__}"
    found = safe_problems(vault, rel, text, data, mounts, prof, know)
    return (False, found[0][1]) if found else (True, "")


# ---------- 快取渲染 ----------

def _cache_ok(found):
    """合法綜合卡（或只差整理到）才重渲染快取。"""
    return all(code == STALE_CODE for code, _r in found)


def render_cache(vault, entity_names, turn_id):
    """對這些實體裡已有合法綜合卡的（只差整理到也算），只重寫檔頭的 檔案卡 與 相關實體 兩欄；內容沒變不寫；
    寫前 turn.backup(by="program")。entity_names 是 None 就全部；名稱可以是別名或合併過的。回重寫了的相對路徑清單。"""
    from kb._lib import turn
    data = entities.load(vault)
    mounts = entities.mounts(vault, data)
    prof = entities._profile(vault)
    know = knowledge(vault)
    if entity_names is None:
        targets = [e for e in data["entities"] if e.get("status") == "active"]
    else:
        targets, seen = [], set()
        for name in entity_names:
            e, _hit = entities.find(data, name)
            if e is not None and e.get("id") not in seen:
                seen.add(e.get("id"))
                targets.append(e)
    written = []
    for e in targets:
        if entities.is_self(e) or not e.get("type") or e.get("status") != "active":
            continue
        rel = card_rel(e)
        p = Path(vault) / rel
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not _cache_ok(safe_problems(vault, rel, text, data, mounts, prof, know)):
            continue
        new = replace_front(text, {"檔案卡": card_lines(mounts.get(e["name"], [])),
                                   "相關實體": related(data, mounts, e)})
        if new == text:
            continue
        turn.backup(vault, rel, turn_id, by="program")
        write_text_atomic(p, new)
        written.append(rel)
    return written


def related_names(data, mounts, names):
    """names 加上跟它們共用檔案卡的實體（改名、合併後要重渲染快取的那一圈）。"""
    out = set()
    for name in names:
        e, _hit = entities.find(data, name)
        if e is None:
            continue
        out.add(e["name"])
        out.update(related(data, mounts, e))
    return sorted(out)


# ---------- 待辦 ----------

def _question(d):
    name = d["name"]
    found = d.get("found") or ""
    folder, stem = (found.split("/") + ["", "", ""])[1], (found.rpartition("/")[2])[:-3]
    if d["kind"] in ("folder_renamed", "both_renamed"):
        return f"「{name}」的資料夾改成「{folder}」了？要跟著改名，還是改回來？"
    if d["kind"] == "card_renamed":
        return f"「{name}」的綜合卡檔名改成「{stem}」了？要採新名，還是改回來？"
    if d["kind"] == "moved_type":
        return f"「{name}」的資料夾搬到「{found.split('/')[0]}」底下了？要跟著改，還是搬回「{d['type']}」？"
    return f"「{name}」的資料夾（或綜合卡）不見了：是不要了，還是刪錯了？"


def _brief(m):
    return {"id": m["id"], "path": m.get("path"), "title": m.get("title")}


def buckets(vault, data, mounts, prof):
    """給 cards todo：回 synthesis_new、synthesis_stale、synthesis_broken、entity_drift 四桶（資料與介面格式）。只讀。"""
    min_cards = config.get(vault, "synthesis_min_cards")
    know = knowledge(vault)
    types = {entities.key(t["name"]) for t in prof.get("types") or []}
    drift_list = entities.drift(vault, data)
    drift_ids = {d["entity_id"] for d in drift_list}
    drift_found = {d["found"].casefold() for d in drift_list if d["found"]}
    today = date.today().isoformat()
    new, stale, broken = [], [], []
    listed = set()
    fixes = _lint_fixes(vault)
    for e in data["entities"]:
        if e.get("status") == "merged" or entities.is_self(e) or not e.get("type"):
            continue
        rel = card_rel(e)
        ms = mounts.get(e["name"], [])
        p = Path(vault) / rel
        if p.is_file():
            try:
                text = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as err:
                broken.append({"path": rel, "reason": f"檔頭解析不了：{type(err).__name__}"})
                listed.add(rel.casefold())
                continue
            found = safe_problems(vault, rel, text, data, mounts, prof, know)
            fix = fixes.get(rel.casefold())
            if not found and fix is None:
                continue
            if not found or [c for c, _r in found] == [STALE_CODE]:
                item = _stale_item(vault, e, rel, text, ms, data, mounts, prof, today, know)
                if fix is not None:
                    item.update(reason=fix.get("reason"), ids=list(fix.get("ids") or []))
                stale.append(item)
            else:
                broken.append({"path": rel, "reason": found[0][1]})
                listed.add(rel.casefold())
            continue
        if e.get("status") != "active" or e.get("id") in drift_ids or entities.key(e["type"]) not in types:
            continue
        stmts, ruls, finds = basis(know, e["name"], mounts)
        if len(ms) + len(stmts) < min_cards:
            continue
        item = {"entity_id": e["id"], "name": e["name"], "type": e["type"], "category": category_text(prof, e["type"]),
                "confirmed": e.get("source") != "inferred", "path": rel, "cards": [_brief(m) for m in ms],
                "statements": [statement_brief(s) for s in stmts],
                "rulings": [ruling_brief(vault, know, r) for r in ruls],
                "findings": [finding_brief(vault, know, c, mounts) for c in finds],
                "sections": sections_for(prof, e["type"]),
                "header": header_for(vault, e, ms, today, data, mounts, prof, know)}
        if not item["confirmed"]:
            item["question"] = (f"我要幫「{e['name']}」（{e['type']}，掛了 {len(ms)} 份檔）整理一頁現況："
                                f"名字這樣叫對嗎？它跟其他{e['type']}是同一件嗎？")
        new.append(item)
    by_id = {e.get("id"): e for e in data["entities"]}
    for eid, rels in sorted(entities.synthesis_files(vault).items()):
        for rel in rels:
            if rel.casefold() in drift_found or rel.casefold() in listed:
                continue
            owner = by_id.get(eid)
            if owner is not None and owner.get("type") and rel.casefold() == card_rel(owner).casefold():
                continue
            ok, reason = validate(vault, rel, data, mounts, prof, know)
            broken.append({"path": rel, "reason": reason if not ok else f"綜合卡該放在 {card_rel(owner)}"})
            listed.add(rel.casefold())
    drift_items = [dict(d, question=_question(d)) for d in drift_list]
    return {"synthesis_new": new, "synthesis_stale": stale, "synthesis_broken": broken, "entity_drift": drift_items}


def _stale_item(vault, e, rel, text, ms, data, mounts, prof, today, know):
    from kb._lib import cards, findings, rulings, statements
    front = cards.parse_front(text)
    have = {}
    for line in front.get("整理到") or []:
        cid, _sp, fp = str(line).partition(" ")
        have[cid] = fp.strip()
    titles = {}
    for line in front.get("檔案卡") or []:
        parts = str(line).split(" ", 2)
        if len(parts) == 3:
            titles[parts[0]] = parts[2]
    stmts, ruls, finds = basis(know, e["name"], mounts)
    redo = redo_ids(vault, know, ms)
    now = {m["id"]: (REDO if m["id"] in redo else (m.get("fp") or ""), dict(_brief(m), source="card")) for m in ms}
    now.update({s["id"]: ("-", dict(statement_brief(s), source="statement")) for s in stmts})
    now.update({r["id"]: ("-", _ruling_source(r)) for r in ruls})
    now.update({c["id"]: ("-", _finding_source(c)) for c in finds})
    added = [now[c][1] for c in sorted(now) if c not in have]
    changed = [dict(now[c][1], **({"reason": cards.REDO_REASON} if have[c] == REDO else {}))
               for c in sorted(now) if c in have and have[c] != now[c][0]]
    gone = [c for c in sorted(have) if c not in now]
    groups = cards._scan_groups(vault)[0] if any(c.startswith("f-") for c in gone) else {}
    removed = []
    for c in gone:
        if c.startswith("s-"):
            removed.append(dict(statement_brief(statements.find(know["statements"], c) or {"id": c}), source="statement"))
        elif c.startswith("r-"):
            removed.append(_ruling_source(rulings.find(know["rulings"], c) or {"id": c}))
        elif c.startswith("c-"):
            removed.append(_finding_source(findings.find(know["findings"], c) or {"id": c}))
        else:
            removed.append({"id": c, "path": groups[c][0]["path"] if c in groups else None, "title": titles.get(c),
                            "source": "card"})
    return {"entity_id": e["id"], "name": e["name"], "path": rel,
            "header": header_for(vault, e, ms, today, data, mounts, prof, know),
            "statements": [statement_brief(s) for s in stmts], "rulings": [ruling_brief(vault, know, r) for r in ruls],
            "findings": [finding_brief(vault, know, c, mounts) for c in finds],
            "added": added, "changed": changed, "removed": removed}


def _lint_fixes(vault):
    """健檢標的要更新綜合卡 {小寫路徑: 那筆}；讀不到當沒有。"""
    try:
        from kb.lint import state
        return {f["path"].casefold(): f for f in state.fixes(vault)}
    except Exception:  # noqa: BLE001  健檢狀態壞了不能擋整理
        return {}


def lint_fix_count(vault):
    """健檢標的、還算數的要更新綜合卡張數（開場「還有 N 份沒整理完」算進去，D-161）。"""
    return len(_lint_fixes(vault))


def _ruling_source(r):
    return {"id": r["id"], "kind": r.get("kind"), "text": r.get("text"), "source": "ruling"}


def _finding_source(c):
    return {"id": c["id"], "text": c.get("text"), "date": c.get("date"), "source": "finding"}
