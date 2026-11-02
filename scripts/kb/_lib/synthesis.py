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
header_for 帶正本（實體清單的 tags，D-505）的標籤行；有卡的另帶卡上有那一行、正本還沒有的（字典內的照卡、字典外留空）與她自加的鍵，
沒有卡的照第八節列出每一欄（正本沒有的留空）。綜合卡檔頭是正本的渲染：hook 驗過之後抄進正本，write_tag_lines 照正本寫回那幾行；
retag 只改一行（kb profile tag）。tag_changes 比對正本在那一回合的備份（回答末尾那句）。
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
TAG_ONLY_REASON = "補標籤"
REDO = "redo"  # 整理到 那行的指紋欄：客戶說卡讀錯了，等卡重寫（實作回報裁定 1）
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# validate 的問題代號：這些一出就不再往下驗（後面的比對沒有意義）
GATING = ("parse", "missing_key", "unknown", "self", "removed", "inferred")


def card_rel(entity, vault=None):
    return entities.card_rel(entity, vault)


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


def blank_keys(text):
    """檔頭裡 KEYS 以外、冒號後面空著、底下也沒有清單項的鍵（還沒標過，裁定 14）。"""
    lines = str(text).lstrip("﻿").splitlines()
    out, pending = [], None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith(("  - ", "- ")):
            pending = None
            continue
        if not line.strip():
            continue
        if pending:
            out.append(pending)
        key, sep, raw = line.partition(":")
        pending = key.strip() if sep and not line.startswith(" ") and key.strip() not in KEYS and not raw.strip() else None
    if pending:
        out.append(pending)
    return out


def read_front(text):
    """cards.parse_front，另把空著的標籤鍵記成 ""（還沒標過），跟 []（看過、沒有）分開（裁定 14）。解析不了丟 ValueError。"""
    from kb._lib import cards
    front = cards.parse_front(text)
    for k in blank_keys(text):
        front[k] = ""
    return front


def card_tags(front, prof, type_):
    """卡檔頭上、第八節這個型別有的標籤行 [(欄, 值)]，照第八節的順序；值 "" 是空著（還沒標過）。"""
    have = {entities.key(k): v for k, v in front.items() if k not in KEYS}
    return [(t["field"], have[entities.key(t["field"])]) for t in profile.tags_for(prof, type_)
            if entities.key(t["field"]) in have]


def extra_tags(front, prof, type_):
    """卡檔頭上 KEYS 與第八節那個型別的欄以外的鍵（她自己加的屬性，裁定 13）[(鍵, 值)]，照卡上的順序。"""
    fields = {entities.key(t["field"]) for t in profile.tags_for(prof, type_)}
    return [(k, v) for k, v in front.items() if k not in KEYS and entities.key(k) not in fields]


def header_tags(vault, entity, prof):
    """header_for 要帶的標籤行：第八節這個型別的欄，值照正本（D-505）；正本沒有的那一欄，有綜合卡而且卡上有那一行就照卡
    （字典外的詞、單選寫了兩個的留空，不把錯的帶回去），卡上也沒有就不帶；沒有卡的每一欄都列（沒有值留空）。
    接著照原樣帶卡上字典外的鍵（裁定 13）。"""
    type_ = entity.get("type")
    front = None
    p = Path(vault) / card_rel(entity, vault)
    if p.is_file():
        try:
            front = read_front(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            front = None
    tags = entity.get("tags") or {}
    out = []
    for t in profile.tags_for(prof, type_):
        v = entities.tag_value(tags, t["field"])
        if v == "":
            v = []  # 正本的單選看過、沒有：卡上寫 []（空著是還沒標過，裁定 14）
        if v is None and front is not None:
            if front_tag(front, t["field"]) is None:
                continue
            v = front_tag(front, t["field"])
        out.append((t["field"], v if v is not None and _tag_ok(t, v) else None))
    return out + (extra_tags(front, prof, type_) if front is not None else [])


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
    return entities.tag_words(v)


def tagged_entities(vault, type_name, data=None):
    """這個型別 active、不是客戶自己的實體：[(實體, 正本的 tags)]（照標籤篩、impact、kb profile tag 用；沒標過的 tags 是 {}）。"""
    data = data if data is not None else entities.load(vault)
    return [(e, dict(e.get("tags") or {})) for e in data["entities"]
            if e.get("status") == "active" and not entities.is_self(e) and e.get("type")
            and entities.key(e["type"]) == entities.key(type_name)]


def tagged_cards(vault, type_name, data=None):
    """這個型別 active、不是客戶自己、有綜合卡的實體：[(實體, 相對路徑, 檔頭)]，讀不懂的卡跳過（kb profile tag、補標籤用）。
    檔頭照 read_front：空著的標籤鍵是 ""。"""
    data = data if data is not None else entities.load(vault)
    out = []
    for e in data["entities"]:
        if (e.get("status") != "active" or entities.is_self(e) or not e.get("type")
                or entities.key(e["type"]) != entities.key(type_name)):
            continue
        rel = card_rel(e, vault) if (Path(vault) / card_rel(e, vault)).is_file() else (entities.locate(vault, e) if e.get("card") else None)
        if not rel:
            continue
        try:
            front = read_front((Path(vault) / rel).read_text(encoding="utf-8"))
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
    """這幾個回合正本多了的詞（D-505 三-4）：第一個有備份 entities.json 的回合，那份備份跟現在的 tags 比，每個 active 實體
    [(名稱, [(欄, [新加的詞])])]，照實體清單的順序；拿掉的不算（標籤字典第五節）。只讀。那份備份是程式改的（by program：
    kb profile tag、手改套用、升級）不算（裁定 12）；這一回合才進 tags_said 的欄是她親口說的，不算。"""
    import json
    from kb._lib import turn
    before = None
    for tid in turn_ids:
        row = next((r for r in turn.entries(vault, tid) if r.get("path") == entities.ENTITIES_POSIX), None)
        if row is None:
            continue
        if row.get("by") == "program":
            return []
        if row.get("action") == "create":
            before = {}
        else:
            try:
                old = json.loads((Path(vault) / turn.VERSIONS_REL / tid / "files" / entities.ENTITIES_POSIX)
                                 .read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, ValueError):
                return []
            before = {e.get("id"): e for e in (old.get("entities") or []) if isinstance(e, dict)}                 if isinstance(old, dict) else {}
        break
    if before is None:
        return []
    out = []
    for e in entities.load(vault)["entities"]:
        if e.get("status") != "active" or entities.is_self(e) or not e.get("type") or not e.get("tags"):
            continue
        was = before.get(e.get("id")) or {}
        said_before = entities.said_fields(was)
        fresh_said = entities.said_fields(e) - said_before
        added = []
        for f, v in e["tags"].items():
            if entities.key(f) in fresh_said:
                continue
            had = {entities.key(w) for w in entities.tag_words(entities.tag_value(was.get("tags"), f))}
            more = [w for w in entities.tag_words(v) if entities.key(w) not in had]
            if more:
                added.append((f, more))
        if added:
            out.append((e["name"], added))
    return out


def copy_tags(vault, rel, turn_id, by=None):
    """綜合卡檔頭的標籤行抄進正本（D-505 決策 3；hook 驗過之後、升級時叫）：第八節這個型別、有值的欄（空著的是還沒標過，不抄）；
    字典外的詞、單選寫兩個的那一欄不抄、回在 skipped。tags_said 裡的欄不抄：卡上那一行照正本寫回（備進回合 by program）；
    正本有、卡上漏寫的欄也照正本補回（不然開場會當成她整行拿掉，裁定 12）。
    回 {"changed","kept","skipped": [(欄, 原因)],"rewrote": 有沒有把卡寫回}；卡讀不懂、實體不在丟 ValueError（呼叫端照 I-046 記 log）。"""
    from kb._lib import turn
    p = Path(vault) / rel
    text = p.read_text(encoding="utf-8")
    front = read_front(text)
    eid = front.get("編號")
    entry = next((e for e in entities.load(vault)["entities"] if e.get("id") == eid), None)
    if entry is None:
        raise ValueError(f"編號 {eid} 不在實體清單")
    prof = entities._profile(vault)
    rows = {entities.key(t["field"]): t for t in profile.tags_for(prof, entry.get("type"))}
    updates, skipped = {}, []
    for f, v in card_tags(front, prof, entry.get("type")):
        if v == "":
            continue
        why = entities.tag_refusal(rows[entities.key(f)], tag_words(v))
        if why:
            skipped.append((f, why))
            continue
        updates[f] = v
    got = {"changed": [], "kept": [], "skipped": skipped, "rewrote": False}
    kept = []
    if updates:
        res = entities.set_tags(vault, eid, updates, turn_id, by=by)
        got.update(changed=res["changed"], kept=res["kept"])
        entry, kept = res["entity"], res["kept"]
    back = kept + missing_tag_fields(text, entry, prof)
    if back:
        new = write_tag_lines(text, entry.get("tags"), back)
        if new != text:
            turn.backup(vault, rel, turn_id, by="program")
            write_text_atomic(p, new)
            got["rewrote"] = True
    return got


def missing_tag_fields(text, entry, prof):
    """正本有、卡檔頭沒有那一行的標籤欄（照第八節的順序）。卡讀不懂回 []。"""
    try:
        front = read_front(text)
    except ValueError:
        return []
    have = {entities.key(k) for k in front}
    return [t["field"] for t in profile.tags_for(prof, entry.get("type"))
            if entities.key(t["field"]) not in have and entities.tag_value(entry.get("tags"), t["field"]) is not None]


def write_tag_lines(text, tags, fields):
    """卡檔頭 fields 那幾欄照正本 tags 寫（一行，「欄: 值」；空的照 [] 或「欄:」）；卡上沒有那一行就補在檔頭結尾的 --- 前。
    其他行與內文原樣（含換行字元）。回新文字（沒變回原文）。"""
    for field in fields:
        v = entities.tag_value(tags, field)
        if v is None:
            continue
        text = _set_line(text, field, v)
    return text


def _set_line(text, field, v):
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n").lstrip("﻿").strip() != "---":
        return text
    for i in range(1, len(lines)):
        bare = lines[i].rstrip("\r\n")
        eol = lines[i][len(bare):] or "\n"
        if bare.strip() == "---":
            lines[i:i] = [tag_line(field, v if v != "" else []) + eol]
            return "".join(lines)
        k, sep, _raw = bare.partition(":")
        if not sep or bare.startswith((" ", "- ")) or k.strip() in KEYS or entities.key(k.strip()) != entities.key(field):
            continue
        j = i + 1
        while j < len(lines) and lines[j].startswith(("  - ", "- ")):
            j += 1
        new = tag_line(k.strip(), v if v != "" else []) + eol  # 單選看過、沒有在卡上寫 []（空著是還沒標過，裁定 14）
        if lines[i:j] == [new]:
            return text
        lines[i:j] = [new]
        return "".join(lines)
    return text


DROP = object()  # retag 的 fn 回它：拿掉那一行


def retag(text, field, fn, new_field=None):
    """只改檔頭裡「field:」那一欄（kb profile tag，D-237）：fn(現在的值) 回新值（清單、一個詞，或 DROP 拿掉那一欄）；
    new_field 給了換鍵。跟 cards.parse_front 認同樣的寫法（一行 [a, b]、底下一項一行的清單、分隔線行尾有空白），
    改完寫回一行 [a, b]，拿掉時底下的清單項一起拿掉（裁定 11）。空著的（還沒標過）換詞不動、換鍵保持空著、拿掉照拿（裁定 14）。
    其他行與內文原樣（含換行字元）；沒有那一欄原樣回。"""
    from kb._lib import cards
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n").lstrip("﻿").strip() != "---":
        return text
    for i in range(1, len(lines)):
        bare = lines[i].rstrip("\r\n")
        if bare.strip() == "---":
            return text
        key, sep, raw = bare.partition(":")
        if (not sep or bare.startswith((" ", "- ")) or not key.strip()
                or entities.key(key.strip()) != entities.key(field)):
            continue
        j, items = i + 1, []
        while j < len(lines) and lines[j].startswith(("  - ", "- ")):
            items.append(cards._scalar(lines[j].rstrip("\r\n").split("- ", 1)[1]))
            j += 1
        eol = lines[i][len(bare):]
        name = new_field or key.strip()
        if raw.strip():
            value = cards._value(raw)
            if items and isinstance(value, list):
                value += items
        elif items:
            value = items
        else:  # 空著：還沒標過
            if fn("") is DROP:
                lines[i:j] = []
            elif new_field:
                lines[i:j] = [f"{name}:{eol}"]
            return "".join(lines)
        new = fn(value)
        if new is DROP:
            lines[i:j] = []
        else:
            if isinstance(new, list):
                new = list(dict.fromkeys(new))
            lines[i:j] = [f"{name}: {tag_value_text(new)}{eol}"]
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
    try:
        front = read_front(text)
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
    want = card_rel(entry, vault)
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
    if not isinstance(have, list):  # 不是清單是抄錯格式，不算只差整理到（裁定 6）
        out.append(("synced_shape", "整理到 照 kb cards todo 給的檔頭抄（一行一項）"))
    elif sorted(have) != sorted(synced_lines(ms, stmts, ruls, redo_ids(vault, know, ms), finds)):
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
    """只驗第八節裡這個型別的欄（詞要在字典裡、單選只能一個）；字典外的鍵不擋（她自加的屬性，裁定 13）；
    空著的算還沒標過，放行（裁定 14）。"""
    extra = [k for k in front if k not in KEYS]
    if not extra:
        return []
    fields = _tag_dictionary(vault, prof, type_)
    if fields is None:
        return []
    for k in extra:
        row = fields.get(entities.key(k))
        if row is None:
            continue
        words = tag_words(front[k])
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


def validate(vault, rel, data=None, mounts=None, prof=None, know=None, allow_stale=False):
    """PostToolUse 與測試用：回 (ok, reason)，只報第一個錯。allow_stale：只差整理到算過（hook 用，D-518）。"""
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
    if allow_stale:
        found = [f for f in found if f[0] != STALE_CODE]
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
    maps = None  # 健檢記號：用到才讀（PostToolUse 每寫一張卡都走這裡）
    written = []
    for e in targets:
        if entities.is_self(e) or not e.get("type") or e.get("status") != "active":
            continue
        rel = card_rel(e, vault)
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
        need = new != text or bool(e.get("aliases"))
        if need and maps is None:
            maps = _fix_maps(vault)  # 寫之前讀：還算數的要照寫之前的指紋認
        if new != text:
            turn.backup(vault, rel, turn_id, by="program")
            write_text_atomic(p, new)
            written.append(rel)
        if need:
            _follow_fixes(vault, e, rel, new != text, *maps)
    return written


NO_ENTITY = "找不到這個實體"
NO_CARD = "還沒有綜合卡"


def _synced_card(vault, e, data, mounts, prof, know):
    """mark_synced 的檢查：回 (相對路徑, 卡的內文, 不寫的原因)；原因是 None 才寫（合法綜合卡，只差整理到也算）。"""
    rel = card_rel(e, vault) if e.get("type") else None
    p = Path(vault) / rel if rel else None
    if p is None or not p.is_file():
        return rel, None, NO_CARD
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:
        return rel, None, f"檔頭解析不了：{type(err).__name__}"
    bad = [r for code, r in safe_problems(vault, rel, text, data, mounts, prof, know) if code != STALE_CODE]
    return rel, text, (bad[0] if bad else None)


def mark_synced(vault, names, turn_id):
    """AI 用 Edit 改完內文之後（D-518）：合法綜合卡（只差整理到也算）的 整理到（header_for 同一算法）、更新日（今天）、
    檔案卡、相關實體 換成現行的，其他檔頭行與內文不動；內容沒變不寫；寫前 turn.backup(by="program")。
    名稱可以是別名。回 (寫了的相對路徑, skipped [{"name","reason"}])；找不到、沒卡、卡有別的錯的不寫、列進 skipped。"""
    from kb._lib import turn
    data = entities.load(vault)
    mounts = entities.mounts(vault, data)
    prof = entities._profile(vault)
    know = knowledge(vault)
    today = date.today().isoformat()
    maps = None
    written, skipped, seen = [], [], set()
    for name in names:
        e, _hit = entities.find(data, name)
        if e is None:
            skipped.append({"name": name, "reason": NO_ENTITY})
            continue
        if e.get("id") in seen:
            continue
        rel, text, reason = _synced_card(vault, e, data, mounts, prof, know)
        seen.add(e.get("id"))  # 檢查完才記：寫了或確定 skipped 的同一個實體再給一次只算一筆（裁定 9）
        if reason:
            skipped.append({"name": name, "reason": reason})
            continue
        p = Path(vault) / rel
        ms = mounts.get(e["name"], [])
        stmts, ruls, finds = basis(know, e["name"], mounts)
        new = replace_front(text, {"整理到": synced_lines(ms, stmts, ruls, redo_ids(vault, know, ms), finds),
                                   "更新日": today, "檔案卡": card_lines(ms), "相關實體": related(data, mounts, e)})
        need = new != text or bool(e.get("aliases"))
        if need and maps is None:
            maps = _fix_maps(vault)
        if new != text:
            turn.backup(vault, rel, turn_id, by="program")
            write_text_atomic(p, new)
            written.append(rel)
        if need:
            _follow_fixes(vault, e, rel, new != text, *maps)
    return written, skipped


def _fix_maps(vault):
    """健檢記的要更新綜合卡：(還算數的 {路徑: 那筆}, 全部的 {路徑: 那筆})；讀不到回兩個空的（照 state.fixes 的做法只記 log）。"""
    try:
        from kb.lint import state
        return {f["path"]: f for f in state.fixes(vault)}, {f["path"]: f for f in state.load(vault)["synthesis_fix"]}
    except Exception as e:  # noqa: BLE001
        from kb._lib import ledger
        ledger.log_error(vault, f"lint.json 讀不到：{type(e).__name__}: {e}", source="synthesis")
        return {}, {}


def _follow_fixes(vault, e, rel, rewrote, fixes, raw_fixes):
    """重寫快取欄之後，健檢記的「要更新」照新的卡檔指紋再記一次（B-463，同 profile_cli._retag_cards）：
    這張卡寫之前還算數的那筆；改名搬了夾的，記在舊名（現在是別名）位置、那個檔已不在的那筆也跟過來，帶過來就拿掉舊那筆
    （只帶一次：卡改好之後不會再被舊那筆叫回來）。
    lint.json 不備進回合：設成不想讓 AI 看到時會走到這裡，回合夾的備份 purge 只換路徑，卡標題會留在備份裡。"""
    found = [fixes[rel]] if rewrote and rel in fixes else []
    moved = []
    for alias in e.get("aliases") or []:
        old = card_rel(dict(e, name=alias), vault)
        if old != rel and old in raw_fixes and not (Path(vault) / old).exists():
            found.append(raw_fixes.pop(old))
            moved.append(old)
    if not found:
        return
    try:
        from kb.lint import state
        for f in found:
            state.add_fix(vault, rel, f.get("reason"), f.get("ids") or [])
        if moved:
            state.change(vault, lambda d: _drop_fixes(d, moved))
    except Exception as err:  # noqa: BLE001  快取欄已寫好；記號沒跟上只記 log
        from kb._lib import ledger
        ledger.log_error(vault, f"健檢記號沒跟上 {rel}：{type(err).__name__}: {err}", source="synthesis")


def _drop_fixes(data, paths):
    before = len(data["synthesis_fix"])
    data["synthesis_fix"] = [f for f in data["synthesis_fix"] if f["path"] not in paths]
    return len(data["synthesis_fix"]) != before


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
    """drift 的問句；moved_type 講上層夾時照設定檔換回型別名（found_type，型別夾編號：客戶看不到編號）。"""
    name = d["name"]
    found = d.get("found") or ""
    folder, stem = (found.split("/") + ["", "", ""])[1], (found.rpartition("/")[2])[:-3]
    if d["kind"] in ("folder_renamed", "both_renamed"):
        return f"「{name}」的資料夾改成「{folder}」了？要跟著改名，還是改回來？"
    if d["kind"] == "card_renamed":
        return f"「{name}」的綜合卡檔名改成「{stem}」了？要採新名，還是改回來？"
    if d["kind"] == "moved_type":
        return f"「{name}」的資料夾搬到「{d.get('found_type') or found.split('/')[0]}」底下了？要跟著改，還是搬回「{d['type']}」？"
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
        rel = card_rel(e, vault)
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
            item = _tag_only_item(e, ms, prof, fixes)
            if item is not None:
                stale.append(item)
            continue
        item = {"entity_id": e["id"], "name": e["name"], "type": e["type"], "category": category_text(prof, e["type"]),
                "confirmed": e.get("source") != "inferred", "path": rel, "cards": [_brief(m) for m in ms],
                "statements": [statement_brief(s) for s in stmts],
                "rulings": [ruling_brief(vault, know, r) for r in ruls],
                "findings": [finding_brief(vault, know, c, mounts) for c in finds],
                "sections": sections_for(prof, e["type"]), "tags_said": list(e.get("tags_said") or []),
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
            if owner is not None and owner.get("type") and rel.casefold() == card_rel(owner, vault).casefold():
                continue
            ok, reason = validate(vault, rel, data, mounts, prof, know)
            broken.append({"path": rel, "reason": reason if not ok else f"綜合卡該放在 {card_rel(owner, vault)}"})
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
            "added": added, "changed": changed, "removed": removed, "tags_said": list(e.get("tags_said") or [])}


def _tag_only_item(e, ms, prof, fixes):
    """還不夠寫綜合卡的實體要補標籤（D-505 決策 4、裁定 4）：型別有標籤欄、掛了檔案卡，而且正本少了某一欄（新實體、升級、第八節加欄），
    或健檢用實體編號記了「補標籤」（第八節加詞，正本 tags 沒改過才算）。回 synthesis_stale 的只補標籤項目，不用補回 None。"""
    if not ms or entities.is_self(e) or not profile.tags_for(prof, e.get("type")):
        return None
    missing = entities.tag_status(e, prof)
    fix = fixes.get(str(e.get("id")).casefold())
    if fix is not None and fix.get("sha") != entities.tags_fingerprint(e):
        fix = None
    if not missing and fix is None:
        return None
    reasons = [r for r in str((fix or {}).get("reason") or "").split("、") if r]
    if missing:
        reasons.insert(0, f"{TAG_ONLY_REASON}（{'、'.join(missing)}）")
    return {"entity_id": e["id"], "name": e["name"], "type": e["type"], "tag_only": True,
            "cards": [_brief(m) for m in ms], "tags": dict(e.get("tags") or {}), "tags_said": list(e.get("tags_said") or []),
            "reason": "、".join(dict.fromkeys(reasons)), "added": [], "changed": [], "removed": []}


def _lint_fixes(vault):
    """健檢標的要更新綜合卡 {小寫路徑: 那筆}（沒有綜合卡的實體是 {小寫實體編號: 那筆}，裁定 4）；讀不到當沒有。"""
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
