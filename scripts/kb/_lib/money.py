"""帳 .system/money.json（記帳 2，issue #27；D-271～D-277、D-282、D-284、D-338、D-339、D-342、D-343）。

正本在流水檔 .system/streams/money/（streams.KINDS 登記 money，收回欄 status cancelled，history 只往後加，D-337、D-339）；
.system/money.json 是合起來的衍生副本，照日程那樣整份讀進、整份交回（io.read_json／write_json_atomic 認得檔名）。
一筆：id（m- 加 8 碼 hex）、dir（in｜out｜none 只動數量）、amount（none 一律 0；None 是金額未知，只准 open）、status（open｜done｜
cancelled）、date（收付那天，open 是 None）、due（到期日）、entities、lines（[{"entity","qty","unit","unit_price","place"}]，qty、unit
照她講的原樣、unit_price 是那個單位的價，算的時候才照 Units 換成基本單位，D-344 補；沒寫單位或沒有 unit 欄是 ""）、advanced_by（墊的人，D-338）、text、note、split_from、repeat（{every, from}）、repeat_of、source（confirmed｜inferred｜
corrected）、origin（{"card","fp"}｜{"statement"}｜None）、cards（補的出處卡）、created_turn、history。帳全隊看得到、不分誰的，
不另存記的人（D-339：誰改的照流水檔每行的「是誰」答）。
寫都經 _mutate：鎖、讀、fn、有變才備進回合再寫、after_write（第 3 份的掛點，這份空的）。寫之前看設定檔第十節：關的時候
拒絕所有寫入、只記我講的拒絕帶卡的（D-343，保險；句子給 AI 不給她）；實體改名合併、purge 這些跟著動的不擋。
庫存、收付合計、未收付都由這裡算（D-271、D-284），AI 不心算。
"""
import copy
import datetime as dt
import re
import secrets
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from kb._lib import config
from kb._lib.io import FileLock, read_json, write_json_atomic

MONEY_POSIX = ".system/money.json"
SCHEMA_VERSION = 1
DIRS = {"收": "in", "付": "out", "無": "none", "in": "in", "out": "out", "none": "none"}
DIR_TEXT = {"in": "收", "out": "付", "none": ""}
STATUSES = ("open", "done", "cancelled")
REPEATS = {"每年": "year", "每月": "month", "每週": "week", "year": "year", "month": "month", "week": "week"}
NO_REPEAT = "不重複"
FIELDS_SUFFIX = ":fields"  # 清冊 money_fp：不是「開」的時候只抽了數字欄，改成開要重抽（D-343）
OTHER = "其他"
MINUS = "−"
OFF_MSG = "帳是關的，錢的話記成口述"
SPOKEN_MSG = "這個知識庫只記她講的錢"
DIR_MSG = "方向要是 收、付、無 之一"
AMOUNT_UNKNOWN_DONE = "金額未知只准還沒收付的；收付了要給 --amount"
SETTLE_UNKNOWN = "這筆金額未知，收付了要給 --amount"
NOT_OPEN = "這筆不是還沒收付的"
ITEM_MSG = "品項要寫「<商品> <±數量>[單位][@單價][在<地點>]」，例：精華液 -2瓶@1800在北店"
PLACE_MSG = "「{name}」不是地點（地點的型別：{types}）"
NO_ENTITY = "實體清單沒有「{}」，先 kb entity add"
ADV_SINGLE = "單人知識庫沒有墊的人"
ADV_MEMBER = "「{}」不是成員名單上的人（設定檔第五節）"
REPEAT_MSG = "重複要是 每年、每月、每週、不重複 之一"
REPEAT_PARTIAL = "重複的那筆要整筆收付；少收付的部分另記一筆"
REPEAT_NEEDS_DUE = "重複的要給 --due（下一次的到期日）"
EDIT_DATE_OPEN = "還沒收付的這筆不能只改收付日；收付了用 kb money settle <編號> --date <那天>"
MERGE_KEEP_CANCELLED = "要留的那筆已經取消了；先 kb money reopen 再併，或換一筆留"
STATEMENT_NO_MONEY = "這句口述沒有錢的記號"
STATEMENT_DONE = "這句口述已經補進帳了"
UNSURE_NEEDS_NEW = "--unsure 要跟 --new 一起給"
_ITEM = re.compile(r"^(?P<name>.+?)\s+(?P<qty>[+-]?[0-9][0-9,]*(?:\.[0-9]+)?)\s*(?P<unit>(?!在)[^\s@0-9+\-]+?)?\s*"
                   r"(?:@\s*(?P<price>[0-9][0-9,]*(?:\.[0-9]+)?萬?))?\s*(?:在\s*(?P<place>\S.*?))?\s*$")


class MoneyRefused(ValueError):
    """kb money 的拒絕：訊息是給 AI 看的那句；payload 是 --json 時多給的（candidates、refused）。"""

    def __init__(self, message, **payload):
        super().__init__(message)
        self.payload = payload


def _today():
    from kb._lib import agenda
    return agenda._today()


def _path(vault):
    return Path(vault) / MONEY_POSIX


def _key(name):
    from kb._lib import entities
    return entities.key(name)


# ---------- 讀 ----------

def empty():
    return {"schema_version": SCHEMA_VERSION, "items": []}


def load(vault):
    """沒檔回空的；壞 JSON、形狀不對、版本比這版新丟 ValueError，訊息帶 .system/money.json。"""
    try:
        data = read_json(_path(vault))
    except ValueError as e:
        raise ValueError(f"{MONEY_POSIX}（JSON 壞了：{e}）") from e
    if data is None:
        return empty()
    if not isinstance(data, dict) or not isinstance(data.get("items"), list) or any(not isinstance(i, dict) for i in data["items"]):
        raise ValueError(f"{MONEY_POSIX}（形狀不對）")
    version = data.get("schema_version", SCHEMA_VERSION)
    if not isinstance(version, int) or version > SCHEMA_VERSION:
        raise ValueError(f"{MONEY_POSIX}（版本 {version!r} 比這版 plugin 新）")
    return {"schema_version": SCHEMA_VERSION, "items": data["items"]}


def _find(data, mid):
    it = next((i for i in data["items"] if i.get("id") == mid), None)
    if it is None:
        raise MoneyRefused(f"帳裡沒有 {mid}")
    return it


def get(vault, mid):
    return _find(load(vault), mid)


def _profile(vault):
    from kb._lib import profile
    try:
        return profile.load(vault) or {}
    except ValueError:
        return {}


def mode(vault, prof=None):
    """第十節的狀態 on｜spoken｜off（沒有第十節讀成 spoken）。"""
    from kb._lib import profile
    return profile.money_mode(prof if prof is not None else _profile(vault))


def exists(vault):
    from kb._lib import streams
    return _path(vault).exists() or streams.exists(vault, "money")


# ---------- 寫 ----------

def after_write(vault, turn_id, data):
    """寫完的掛點（第 3 份畫帳頁、卡底下用）；這份什麼都不做。"""
    return None


def check_mode(vault, card=False):
    """關的時候擋所有寫入、只記我講的擋帶卡的（D-343）。"""
    m = mode(vault)
    if m == "off":
        raise MoneyRefused(OFF_MSG, refused="off")
    if card and m == "spoken":
        raise MoneyRefused(SPOKEN_MSG, refused="spoken")


def _mutate(vault, turn_id, fn, check=None):
    """鎖住讀改寫：fn(data) 回 (結果, 有沒有改)；有改才備份、寫、after_write。check 是 "write"／"card" 時先看開關。"""
    if check:
        check_mode(vault, card=check == "card")
    p = _path(vault)
    p.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(p):
        data = load(vault)
        result, changed = fn(data)
        if changed:
            from kb._lib import turn
            turn.backup(vault, MONEY_POSIX, turn_id)
            write_json_atomic(p, data)
            after_write(vault, turn_id, data)
    return result


def _new_id(data):
    taken = {i.get("id") for i in data["items"]}
    while True:
        new = "m-" + secrets.token_hex(4)
        if new not in taken:
            return new


def _log(it, change, by, turn_id):
    it.setdefault("history", []).append({"date": _today(), "change": change, "by": by, "turn": turn_id})


def _date(text):
    from kb._lib import agenda
    try:
        return agenda.parse_date(text).isoformat()
    except agenda.AgendaRefused as e:
        raise MoneyRefused(str(e)) from None


def _amount(text):
    """金額字串 → int／float；None 是未知。"""
    if text is None:
        return None
    from kb._lib import numbers
    try:
        return numbers.plain(numbers.parse_number(str(text).strip(), negative=False))
    except numbers.NumberRefused as e:
        raise MoneyRefused(str(e)) from None


def _dir(text):
    d = DIRS.get(str(text or "").strip())
    if d is None:
        raise MoneyRefused(DIR_MSG)
    return d


def _every(value):
    value = (value or "").strip()
    if value == NO_REPEAT:
        return None
    if value not in REPEATS:
        raise MoneyRefused(REPEAT_MSG)
    return REPEATS[value]


def _ents(vault):
    from kb._lib import entities
    return entities.load(vault)


def _entity(ents, name):
    from kb._lib import entities
    e, _hit = entities.find(ents, str(name).strip())
    if e is None or e.get("status") != "active":
        raise MoneyRefused(NO_ENTITY.format(str(name).strip()))
    return e


def _names(ents, names):
    out = []
    for n in names or []:
        e = _entity(ents, n)
        if all(_key(x) != _key(e["name"]) for x in out):
            out.append(e["name"])
    return out


def parse_item(text):
    """「精華液 -2瓶@1,800在北店」→ (商品, 數量字串, 單位或 None, 單價字串或 None, 地點或 None)；看不懂丟 MoneyRefused。"""
    m = _ITEM.match(str(text or "").strip())
    if not m:
        raise MoneyRefused(ITEM_MSG)
    return m.group("name").strip(), m.group("qty"), m.group("unit") or None, m.group("price"), m.group("place")


def _type_fields(prof, type_name):
    from kb._lib import profile
    return profile.fields_for(prof, type_name)


def base_unit(prof, type_name):
    """這個型別的基本單位：安全庫存那欄的單位，沒有就第一個「每…」欄的單位；都沒有回 ""。"""
    rows = _type_fields(prof, type_name)
    for f in rows:
        if f.get("field") == "安全庫存" and f.get("unit"):
            return f["unit"]
    return next((f["unit"] for f in rows if str(f.get("field", "")).startswith("每") and f.get("unit")), "")


def _field_unit(prof, type_name, field):
    """第九節這個型別那一欄的單位；第九節沒這欄回 None。"""
    return next(((f.get("unit") or "") for f in _type_fields(prof, type_name) if f.get("field") == field), None)


def _pack(entry, field):
    from kb._lib import entities
    v = entities.field_value(entry, field) if entry else None
    return Fraction(str(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def factor(prof, entry, unit, base):
    """一<unit> 是幾個基本單位（Fraction，D-344 補）：沒寫單位或就是基本單位是 1；實體有「每<unit>」的值就是它；
    基本單位是大的（每<基本單位> 的單位是 unit）就倒過來除；換不了回 None。"""
    if not unit or unit == base:
        return Fraction(1)
    if not base or not entry:
        return None
    typ = entry.get("type")
    v = _pack(entry, "每" + unit)
    if v is not None and _field_unit(prof, typ, "每" + unit) in (None, "", base):
        return v
    v = _pack(entry, "每" + base)
    if v is not None and _field_unit(prof, typ, "每" + base) == unit:
        return 1 / v
    return None


def _frac(v):
    return Fraction(str(v if v is not None else 0))


def _num(fr):
    """Fraction → JSON 的數：除得盡的照原數，除不盡的取 4 位小數（只在顯示、合計時，帳裡存的是她講的數）。"""
    from kb._lib import numbers
    fr = Fraction(fr)
    d = Decimal(fr.numerator) / Decimal(fr.denominator)
    if d * fr.denominator != fr.numerator:
        d = d.quantize(Decimal("0.0001"))
    return numbers.plain(d)


class Units:
    """一個商品的單位換算（D-344 補）：base 是第九節的基本單位（"" 是沒有）；to_base 把一個品項換成 (數, 組)，
    換得了的組是 base（沒寫單位的也是），換不了的組是它自己的單位。"""

    def __init__(self, prof, entry):
        self.entry = entry
        self.base = base_unit(prof, entry.get("type")) if entry else ""
        self.prof = prof

    def to_base(self, qty, unit):
        unit = unit or ""
        f = factor(self.prof, self.entry, unit, self.base)
        return (_frac(qty) * f, self.base) if f is not None else (_frac(qty), unit)


def _units(prof, ents, name, cache=None):
    from kb._lib import entities
    k = _key(name or "")
    if cache is not None and k in cache:
        return cache[k]
    got = Units(prof, entities.find(ents, name)[0] if name else None)
    if cache is not None:
        cache[k] = got
    return got


def _show_q(fr, unit=""):
    from kb._lib import numbers
    return numbers.show(_num(fr)) + (f" {unit}" if unit else "")


def groups_text(groups, base):
    """[(組的單位, 數)]（主要的那組在前）→「12 瓶＋2 箱（不知道一箱幾瓶）」；只有一組照那組顯示（D-344 補：換不了的分開列）。"""
    if not groups:
        return _show_q(Fraction(0), base)
    many = len(groups) > 1
    parts = []
    for i, (u, q) in enumerate(groups):
        text = _show_q(abs(q) if i else q, u) + ("（沒寫單位）" if many and not u else "")
        parts.append(text if not i else (MINUS if q < 0 else "＋") + text)
    odd = [u for u, _q in groups if u and u != base]
    if base and odd:
        return "".join(parts) + "（不知道" + "、".join(f"一{u}幾{base}" for u in odd) + "）"
    return "".join(parts) + ("（單位不同，沒有加在一起）" if many else "")


def _pick_main(groups, base):
    """主要的那組：基本單位那組；沒有就第一組（只有一組照那組）。"""
    if base in groups or not groups:
        return base
    return next(iter(groups))


def _unit_label(u):
    return u or "沒寫單位"


def _unit_msg(prof, units, name, prior, new_units):
    """換不到同一組的退回句（D-344 補；#16 先 profile add 再 entity field）。prior 是 [(單位, 帳的編號)]，new_units 是這次的單位。"""
    base, typ = units.base, (units.entry or {}).get("type")
    old = [u for u, _mid in prior]
    head = (f"「{name}」以前記過的單位：{'、'.join(dict.fromkeys(map(_unit_label, old))) or '（沒有）'}；"
            f"這次是：{'、'.join(dict.fromkeys(map(_unit_label, new_units)))}；換不成同一個單位，沒有寫。")
    steps = []
    if base:
        for u in dict.fromkeys(u for u in old + list(new_units) if units.to_base(1, u)[1] != base):
            add = (f"先 kb profile add 數字欄 型別={typ} 欄名=每{u} 單位={base}，再 "
                   if _field_unit(prof, typ, "每" + u) is None else "")
            steps.append(f"問她一次一{u}幾{base}，答了{add}kb entity field {name} 每{u}=<數> --said"
                         f"（{u}比{base}小就反過來設 每{base}，欄的單位={u}）")
    else:
        said = [u for u in new_units if u]
        named = list(dict.fromkeys(said + [u for u in old if u]))
        if len(named) > 1:
            big, small = named[:2]
            steps.append(f"問她一次一{big}幾{small}，答了先 kb profile add 數字欄 型別={typ} 欄名=每{big} 單位={small}，"
                         f"再 kb entity field {name} 每{big}=<數> --said（大小相反就對調）")
        blank = list(dict.fromkeys(mid for u, mid in prior if not u))
        if blank and said:
            steps.append(f"之前沒寫單位的（{'、'.join(blank)}）問她是什麼單位，"
                         f"kb money edit <編號> --item \"<那筆全部的品項，補上單位>\"")
    tail = "；然後照原句再記" if steps else ""
    if not base and any(not u for u in new_units) and any(old):
        steps.append(f"這次沒寫單位：是{'、'.join(dict.fromkeys(u for u in old if u))}的話 --item 補上單位再記，不確定先問她")
    return head + "；".join(steps) + tail


def _check_units(prof, ents, data, lines, exclude=None):
    """寫入前（D-344 補）：同一個商品，以前沒取消的筆（exclude 是正在改的那筆）加上這次的品項，換不到同一組就退回。"""
    mine = {}
    for ln in lines:
        mine.setdefault(_key(ln["entity"]), []).append(ln)
    if not mine:
        return
    prior = {k: [] for k in mine}
    for it in _live(data):
        if exclude is not None and it.get("id") == exclude:
            continue
        for ln in it.get("lines") or []:
            k = _key(ln.get("entity") or "")
            if k in prior:
                prior[k].append((ln.get("unit") or "", it.get("id"), ln))
    cache = {}
    for k, new in mine.items():
        units = _units(prof, ents, new[0]["entity"], cache)
        keys = {units.to_base(1, u)[1] for u, _m, _ln in prior[k]} | {units.to_base(1, ln.get("unit"))[1] for ln in new}
        if len(keys) > 1:
            raise MoneyRefused(_unit_msg(prof, units, new[0]["entity"], [(u, m) for u, m, _ln in prior[k]],
                                         [ln.get("unit") or "" for ln in new]))


def line_text(prof, ents, ln, cache=None):
    """一個品項的數量與單位（D-344 補）：「+2 箱（48 瓶）」；沒寫單位算基本單位；換不了的「+2 箱（不知道一箱幾瓶）」。"""
    units = _units(prof, ents, ln.get("entity"), cache)
    unit, q = ln.get("unit") or "", _frac(ln.get("qty"))
    base = units.base
    if not unit or unit == base:
        return _qty_text(q, base)
    got, group = units.to_base(q, unit)
    if group == base and base:
        return f"{_qty_text(q, unit)}（{_show_q(abs(got), base)}）"
    return _qty_text(q, unit) + (f"（不知道一{unit}幾{base}）" if base else "")


def _place(vault, prof, ents, name, place_types):
    """地點：沒有地點型別的知識庫一律 None；給了要是地點型別的實體；沒給照記的人平常在哪（D-342）。"""
    if not place_types:
        return None
    if name:
        e = _entity(ents, name)
        if _key(e.get("type")) not in {_key(t) for t in place_types}:
            raise MoneyRefused(PLACE_MSG.format(name=e["name"], types="、".join(place_types)))
        return e["name"]
    from kb._lib import people, profile
    me = people.me(vault)
    return profile.usual_place(prof, me) if me else None


def _lines(vault, raw_items, prof=None, ents=None, exclude=None):
    """品項換成 lines：照她講的原樣存 qty、unit（沒講是 ""），單價是她講那個單位的價（D-344 補，寫入不換算）；
    寫之前照 _check_units 看單位換不換得到同一組。exclude 是正在改的那筆。"""
    from kb._lib import numbers, profile
    prof = _profile(vault) if prof is None else prof
    ents = _ents(vault) if ents is None else ents
    place_types = profile.place_types(prof)
    out = []
    for raw in raw_items or []:
        name, qty, unit, price, place = parse_item(raw)
        e = _entity(ents, name)
        try:
            n = numbers.parse_number(qty.lstrip("+"))
            unit_price = None if price is None else numbers.plain(numbers.parse_number(price, negative=False))
        except numbers.NumberRefused as e2:
            raise MoneyRefused(str(e2)) from None
        out.append({"entity": e["name"], "qty": numbers.plain(n), "unit": unit or "", "unit_price": unit_price,
                    "place": _place(vault, prof, ents, place, place_types)})
    if out:
        _check_units(prof, ents, load(vault), out, exclude)
    return out


def _advanced(vault, name):
    if name is None:
        return None
    from kb._lib import people
    if not people.multi(vault):
        raise MoneyRefused(ADV_SINGLE)
    members = people.members(vault)
    hit = next((m for m in members if _key(m) == _key(name)), None)
    if hit is None:
        raise MoneyRefused(ADV_MEMBER.format(name))
    return hit


def _ref_day(it):
    return it.get("date") or it.get("due")


def _overlap(a, b):
    ka, kb_ = {_key(x) for x in a or []}, {_key(x) for x in b or []}
    return bool(ka & kb_) if ka or kb_ else True


def _row(it, is_open):
    return {"id": it.get("id"), "dir": it.get("dir"), "amount": it.get("amount"), "status": it.get("status"),
            "date": it.get("date"), "due": it.get("due"), "entities": list(it.get("entities") or []), "text": it.get("text"),
            "open": is_open}


def find_candidates(vault, data, dir_, amount, day, names, exclude=()):
    """D-276：同實體（都沒掛也算）、同方向，金額相同、日期差在 money_dupe_days 天內的；同實體同方向還沒收付的也列（open: True）。"""
    if dir_ == "none":
        return []
    days = config.get(vault, "money_dupe_days")
    out = []
    for it in data["items"]:
        if it.get("id") in exclude or it.get("status") == "cancelled" or it.get("dir") != dir_:
            continue
        if not _overlap(names, it.get("entities")):
            continue
        if it.get("status") == "open":
            out.append(_row(it, True))
            continue
        ref = _ref_day(it)
        if amount is not None and it.get("amount") is not None and Decimal(str(it["amount"])) == Decimal(str(amount)) \
                and ref and day and abs((dt.date.fromisoformat(ref) - dt.date.fromisoformat(day)).days) <= days:
            out.append(_row(it, False))
    return out


def candidates(vault, dir_, amount=None, date=None, due=None, entities=()):
    """kb money candidates：只列不寫。"""
    names = _names(_ents(vault), entities)
    day = _date(date) if date else (_date(due) if due else _today())
    return find_candidates(vault, load(vault), _dir(dir_), _amount(amount), day, names)


def _statement(vault, sid):
    from kb._lib import statements
    s = statements.find(statements.load(vault), sid)
    if s is None:
        raise MoneyRefused(statements.NOT_FOUND.format(sid))
    mark = s.get("money")
    if not isinstance(mark, dict):
        raise MoneyRefused(STATEMENT_NO_MONEY)
    if mark.get("ledger"):
        raise MoneyRefused(STATEMENT_DONE)
    return s


def add(vault, turn_id, dir_, amount=None, date=None, due=None, entities=(), items=(), advanced_by=None, text="", note="",
        repeat=None, new=False, unsure=None, card=None, statement=None, by="ai"):
    """記一筆。回 (筆, 新建了嗎)。驗完才寫；有候選又沒帶 new → MoneyRefused（payload refused=candidates、candidates）。
    card 給了 → 來源 inferred、origin 記卡與指紋，同一張卡已有同方向同金額同日的不重複、回既有。statement 給了 → 照那句口述的日期記、
    origin.statement，寫完口述的記號補 ledger。unsure（要跟 new）→ 寫完開一條 money_dupe 待處理（呼叫端 CLI 開）。"""
    from kb._lib import agenda
    if unsure and not new:
        raise MoneyRefused(UNSURE_NEEDS_NEW)
    d = _dir(dir_)
    amt = 0 if d == "none" else _amount(amount)
    adv = _advanced(vault, advanced_by)
    st = _statement(vault, statement) if statement else None
    day = _date(date) if date else None
    if st is not None and day is None and not due:
        day = st.get("date") or _today()
    due_ = _date(due) if due else None
    if d == "none":
        status, day = "done", day or _today()
    elif day:
        status = "done"
    elif due_ or adv:
        status = "open"
    else:
        status, day = "done", _today()
    if amt is None and status != "open":
        raise MoneyRefused(AMOUNT_UNKNOWN_DONE)
    prof, ents = _profile(vault), _ents(vault)
    names = _names(ents, entities)
    lines = _lines(vault, items, prof, ents)
    every = _every(repeat) if repeat else None
    if every and not due_:
        raise MoneyRefused(REPEAT_NEEDS_DUE)
    text = " ".join(str(text or "").split())
    note = " ".join(str(note or "").split())

    def fn(data):
        if unsure:
            _find(data, unsure)  # 寫之前先驗，編號錯了不寫（不然 AI 重跑會記兩次）
        origin, source = None, "confirmed"
        if card:
            found = agenda._card(vault, card, no_card="這份還沒有檔案卡，先寫卡再記帳")
            origin, source = {"card": card, "fp": agenda.card_fp(found["front"])}, "inferred"
            same = next((i for i in data["items"] if i.get("status") != "cancelled" and (i.get("origin") or {}).get("card") == card
                         and i.get("dir") == d and i.get("amount") == amt and _ref_day(i) == (day or due_)), None)
            if same is not None:
                return (same, False), False
        elif st is not None:
            origin = {"statement": st["id"]}
        if not new:
            found_c = find_candidates(vault, data, d, amt, day or due_ or _today(), names)
            if found_c:
                raise MoneyRefused("有可能是同一筆的，先看 candidates；確定是另一筆再帶 --new", refused="candidates",
                                   candidates=found_c)
        it = {"id": _new_id(data), "dir": d, "amount": amt, "status": status, "date": day if status == "done" else None,
              "due": due_, "entities": names, "lines": lines, "advanced_by": adv, "text": text, "note": note,
              "split_from": None, "repeat": {"every": every, "from": due_ or day} if every else None, "repeat_of": None,
              "source": source, "origin": origin, "cards": [], "created_turn": turn_id, "history": []}
        _log(it, "記下", by, turn_id)
        data["items"].append(it)
        return (it, True), True
    got = _mutate(vault, turn_id, fn, check="card" if card else "write")
    if st is not None and got[1]:
        from kb._lib import statements
        statements.set_ledger(vault, st["id"], got[0]["id"], turn_id)
    return got


EDITABLE = ("amount", "date", "due", "entities", "lines", "advanced_by", "text", "note")


def _show(v):
    if v is None:
        return ""
    if isinstance(v, list):
        return "、".join(x if isinstance(x, str) else f"{x.get('entity')} {x.get('qty')}{x.get('unit') or ''}" for x in v)
    return str(v)


def edit(vault, mid, turn_id, by="ai", amount=None, date=None, due=None, entities=None, items=None, advanced_by=None, text=None,
         note=None):
    """改欄（None 當沒給）。來源推測的改了 → corrected。回 (改之後的筆, 改之前的筆)。"""
    new = {}
    if amount is not None:
        new["amount"] = _amount(amount)
    if date is not None:
        new["date"] = _date(date)
    if due is not None:
        new["due"] = _date(due)
    if entities:
        new["entities"] = _names(_ents(vault), entities)
    if items:
        new["lines"] = _lines(vault, items, exclude=mid)
    if advanced_by is not None:
        new["advanced_by"] = _advanced(vault, advanced_by)
    if text is not None:
        new["text"] = " ".join(str(text).split())
    if note is not None:
        new["note"] = " ".join(str(note).split())

    def fn(data):
        it = _find(data, mid)
        before = copy.deepcopy(it)
        if it.get("dir") == "none" and "amount" in new:
            new.pop("amount")
        if new.get("amount", it.get("amount")) is None and it.get("status") == "done":
            raise MoneyRefused(AMOUNT_UNKNOWN_DONE)
        if "date" in new and it.get("status") == "open" and it.get("dir") != "none":
            raise MoneyRefused(EDIT_DATE_OPEN)
        changes = []
        for k in EDITABLE:
            if k in new and new[k] != it.get(k):
                changes.append(f"{k} {_show(it.get(k))} → {_show(new[k])}")
                it[k] = new[k]
                if k == "due" and it.get("repeat"):
                    it["repeat"] = {**it["repeat"], "from": new[k]}
        if not changes:
            return (it, before), False
        if it.get("source") == "inferred":
            it["source"] = "corrected"
        _log(it, "；".join(changes), by, turn_id)
        return (it, before), True
    return _mutate(vault, turn_id, fn, check="write")


def settle(vault, mid, turn_id, amount=None, date=None, due=None, by="ai", card=None):
    """收付了（D-275）：金額少於原額就拆——原筆改已收付那部分（品項留在這筆），另生一筆還沒收付的差額（split_from 指回）；
    有 repeat 的另生一筆已收付（repeat_of）、原筆的到期移到下一次（D-501 那套）。回 (原筆, 拆出的或 None, 重複生的或 None)。"""
    from kb._lib import agenda
    paid = _amount(amount)
    day = _date(date) if date else _today()
    due_ = _date(due) if due else None
    if card:  # 製卡讀到匯款單、收據：出處記在收付的那筆（拆出的還沒收付那筆不帶）
        agenda._card(vault, card, no_card="這份還沒有檔案卡，先寫卡再記帳")

    def _cite(row):
        if card and card not in (row.get("cards") or []) and (row.get("origin") or {}).get("card") != card:
            row["cards"] = list(row.get("cards") or []) + [card]

    def fn(data):
        it = _find(data, mid)
        if it.get("status") != "open":
            raise MoneyRefused(NOT_OPEN)
        whole = it.get("amount")
        got = whole if paid is None else paid
        if got is None:
            raise MoneyRefused(SETTLE_UNKNOWN)
        if it.get("repeat"):
            if whole is not None and Decimal(str(got)) < Decimal(str(whole)):
                raise MoneyRefused(REPEAT_PARTIAL)
            done = copy.deepcopy(it)
            done.update({"id": _new_id(data), "status": "done", "date": day, "amount": got, "repeat": None, "repeat_of": mid,
                         "created_turn": turn_id, "history": []})
            _cite(done)
            _log(done, f"記下（{mid} 那次收付了）", by, turn_id)
            data["items"].append(done)
            was = it.get("due") or day
            it["due"] = agenda.next_after(it["repeat"], was)
            _log(it, f"{was} 那次收付了，下次 {it['due']}", by, turn_id)
            return (it, None, done), True
        rest = None
        if whole is not None and Decimal(str(got)) < Decimal(str(whole)):
            from kb._lib import numbers
            rest = copy.deepcopy(it)
            rest.update({"id": _new_id(data), "amount": numbers.plain(Decimal(str(whole)) - Decimal(str(got))), "lines": [],
                         "split_from": mid, "due": due_ or it.get("due"), "created_turn": turn_id, "history": []})
            _log(rest, f"拆自 {mid}（原 {whole}，收付了 {got}）", by, turn_id)
            data["items"].append(rest)
        it["status"], it["date"] = "done", day
        _cite(it)
        if got != whole:
            it["amount"] = got
        _log(it, f"status open → done（{day}，{got}）", by, turn_id)
        return (it, rest, None), True
    return _mutate(vault, turn_id, fn, check="card" if card else "write")


def set_status(vault, mid, status, turn_id, by="ai"):
    """cancel（cancelled）／reopen（open）。回筆。"""
    if status not in STATUSES:
        raise ValueError(status)

    def fn(data):
        it = _find(data, mid)
        old = it.get("status")
        want = status
        if want == "open":  # 重開：取消前收付了的（有收付日）回到已收付，否則回到還沒收付；已收付的重開＝改回還沒收付
            if old == "cancelled" and (it.get("date") or it.get("dir") == "none"):
                want = "done"
            elif old == "done":
                it["date"] = None
        if want == old:
            return it, False
        it["status"] = want
        _log(it, f"status {old} → {want}", by, turn_id)
        return it, True
    return _mutate(vault, turn_id, fn, check="write")


def attach(vault, mid, card, turn_id, by="ai"):
    """補出處（D-276：明顯是同一筆，讀到收據）：cards 多這張卡。回筆。"""
    from kb._lib import agenda
    agenda._card(vault, card, no_card="這份還沒有檔案卡，先寫卡再補出處")

    def fn(data):
        it = _find(data, mid)
        if card in (it.get("cards") or []) or (it.get("origin") or {}).get("card") == card:
            return it, False
        it["cards"] = list(it.get("cards") or []) + [card]
        _log(it, f"補出處 {card}", by, turn_id)
        return it, True
    return _mutate(vault, turn_id, fn, check="card")


def merge(vault, keep, drop, turn_id, by="ai"):
    """兩筆是同一筆：drop 改 cancelled（記併進哪筆），它的出處卡併進 keep。回 (keep, drop)。"""
    if keep == drop:
        raise MoneyRefused("要給兩筆不同的帳")

    def fn(data):
        a, b = _find(data, keep), _find(data, drop)
        if a.get("status") == "cancelled":
            raise MoneyRefused(MERGE_KEEP_CANCELLED)
        if b.get("status") == "cancelled":
            raise MoneyRefused("要併掉的那筆已經取消了")
        extra = list(b.get("cards") or []) + ([b["origin"]["card"]] if (b.get("origin") or {}).get("card") else [])
        have = set(a.get("cards") or []) | ({a["origin"]["card"]} if (a.get("origin") or {}).get("card") else set())
        add_cards = [c for c in dict.fromkeys(extra) if c not in have]
        if add_cards:
            a["cards"] = list(a.get("cards") or []) + add_cards
        _log(a, f"併進 {drop}", by, turn_id)
        old = b.get("status")
        b["status"] = "cancelled"
        _log(b, f"status {old} → cancelled（跟 {keep} 是同一筆）", by, turn_id)
        return (a, b), True
    return _mutate(vault, turn_id, fn, check="write")


COUNT_INEXACT = "算出來的差換不成整數的單位，沒有寫；照她講的單位再說一次實際數量"


def _exact(q):
    """這個數存得下（小數最多 4 位、除得盡）。"""
    return (q * 10000).denominator == 1


def count(vault, product, actual, turn_id, place=None, by="ai"):
    """盤點（小事預設）：照地點算出差多少，記一筆 dir=none（金額 0）不直接改庫存。實際數量可帶單位，照同一套換（D-344 補）：
    差存成她講的那個單位，換不成整數就存基本單位或以前用過的單位，都不行退回（不留小數誤差）；說明寫「盤點，實際 1 箱（24 瓶）」。
    對得上回 (None, 0)；否則 (筆, 差)，差是基本單位的數。"""
    from kb._lib import numbers, profile
    prof, ents = _profile(vault), _ents(vault)
    e = _entity(ents, product)
    m = re.match(r"^\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(\S*)\s*$", str(actual))
    if not m:
        raise MoneyRefused(numbers.BAD_NUMBER.format(actual))
    try:
        n = numbers.parse_number(m.group(1))
    except numbers.NumberRefused as e2:
        raise MoneyRefused(str(e2)) from None
    said = m.group(2) or ""
    where = _place(vault, prof, ents, place, profile.place_types(prof)) if place else None
    units = Units(prof, e)
    real, group = units.to_base(n, said)
    k = _key(e["name"])

    def fn(data):
        _check_units(prof, ents, data, [{"entity": e["name"], "qty": numbers.plain(n), "unit": said}])
        now, used = Fraction(0), []
        for it in _live(data):
            for ln in it.get("lines") or []:
                if _key(ln.get("entity") or "") == k and (not where or ln.get("place") == where):
                    now += units.to_base(ln.get("qty"), ln.get("unit"))[0]
                    used.append(ln.get("unit") or "")
        diff = real - now
        if diff == 0:
            return (None, 0), False
        for u in dict.fromkeys([said, group, *used]):
            f = units.to_base(1, u)
            q = diff / f[0] if f[1] == group else None
            if q is not None and _exact(q):
                break
        else:
            raise MoneyRefused(COUNT_INEXACT)
        said_text = _show_q(n, said) + (f"（{_show_q(real, group)}）" if said and said != group and group else "")
        it = {"id": _new_id(data), "dir": "none", "amount": 0, "status": "done", "date": _today(), "due": None, "entities": [],
              "lines": [{"entity": e["name"], "qty": _num(q), "unit": u, "unit_price": None, "place": where}],
              "advanced_by": None, "text": f"盤點，實際 {said_text}", "note": "", "split_from": None, "repeat": None,
              "repeat_of": None, "source": "confirmed", "origin": None, "cards": [], "created_turn": turn_id, "history": []}
        _log(it, f"盤點：{_show_q(now, group)} → {said_text}", by, turn_id)
        data["items"].append(it)
        return (it, _num(diff)), True
    return _mutate(vault, turn_id, fn, check="write")


# ---------- 算 ----------

def _live(data):
    return [i for i in data["items"] if i.get("status") != "cancelled"]


def _place_names(prof, ents):
    from kb._lib import profile
    types = {_key(t) for t in profile.place_types(prof)}
    if not types:
        return []
    return sorted(e["name"] for e in ents["entities"] if e.get("status") == "active" and _key(e.get("type")) in types)


def stock(vault, entity=None, place=None, data=None, prof=None, ents=None):
    """{"products": [{"name","unit","total","places": {地點: 數},"min","base","apart","text","places_text"}]}：所有沒取消的筆
    （不管收付了沒，新定 5）；每個品項照 Units 換成基本單位（D-344 補），換得了的加在 total、places（單位 unit），換不了的分開放
    apart（[{"unit","qty","places"}]），text 是「12 瓶＋2 箱（不知道一箱幾瓶）」、places_text 是各地點的同一套字；只有換不了的
    一組時 unit 就是那組的單位。places 列每個地點型別的實體（沒動靜的是 0）；entity 給了只列那個商品，place 給了只列在那裡有進出的、
    places 只留那一格。"""
    from kb._lib import entities
    data = load(vault) if data is None else data
    prof = _profile(vault) if prof is None else prof
    ents = _ents(vault) if ents is None else ents
    want = _entity(ents, entity)["name"] if entity else None
    at = _entity(ents, place)["name"] if place else None
    cache, per = {}, {}
    for it in _live(data):
        for ln in it.get("lines") or []:
            units = _units(prof, ents, ln.get("entity"), cache)
            q, g = units.to_base(ln.get("qty"), ln.get("unit"))
            rec = per.setdefault(ln.get("entity"), {})
            grp = rec.setdefault(g, {"total": Fraction(0), "places": {}})
            grp["total"] += q
            if ln.get("place"):
                grp["places"][ln["place"]] = grp["places"].get(ln["place"], Fraction(0)) + q
    names = _place_names(prof, ents)
    out = []
    for name in sorted(per):
        if want and _key(name) != _key(want):
            continue
        rec = per[name]
        if at and not any(at in g["places"] for g in rec.values()):
            continue
        units = _units(prof, ents, name, cache)
        main = _pick_main(rec, units.base)
        order = [main] + [g for g in rec if g != main]
        where = [at] if at else list(dict.fromkeys(names + [p for g in rec.values() for p in g["places"]]))
        cells = {g: {p: rec[g]["places"].get(p, Fraction(0)) if g in rec else Fraction(0) for p in where} for g in order}
        total = rec[main]["total"] if main in rec else Fraction(0)
        e = entities.find(ents, name)[0]
        out.append({"name": name, "unit": main, "total": _num(total),
                    "places": {p: _num(v) for p, v in cells[main].items()},
                    "min": entities.field_value(e, "安全庫存") if e else None, "base": units.base,
                    "apart": [{"unit": g, "qty": _num(rec[g]["total"]), "places": {p: _num(v) for p, v in cells[g].items()}}
                              for g in order[1:]],
                    "text": groups_text([(g, rec[g]["total"]) for g in order if g in rec], units.base),
                    "places_text": {p: groups_text([(g, cells[g][p]) for g in order if g == main or cells[g][p]], units.base)
                                    for p in where}})
    return {"products": out}


def low_stock(vault, names, data=None):
    """合計低於「安全庫存」的商品（D-282；只看合計，D-342 (4)）；沒有安全庫存欄的不列。只比換得到基本單位的那組
    （D-344 補；有換不了的一起帶在 text 裡讓她看到有分開）。"""
    out = []
    keys = {_key(n) for n in names}
    for p in stock(vault, data=data)["products"]:
        if _key(p["name"]) in keys and p["min"] is not None and p["unit"] == p["base"] \
                and Decimal(str(p["total"])) < Decimal(str(p["min"])):
            out.append({"entity": p["name"], "stock": p["total"], "min": p["min"], "unit": p["unit"], "text": p["text"]})
    return out


def _touches(it, k):
    return (any(_key(n) == k for n in it.get("entities") or [])
            or any(_key(ln.get("entity")) == k or _key(ln.get("place") or "") == k for ln in it.get("lines") or []))


def _in_range(day, frm, to):
    return bool(day) and (frm is None or day >= frm) and (to is None or day <= to)


def _price(ents, name, field):
    from kb._lib import entities
    e, _hit = entities.find(ents, name)
    return entities.field_value(e, field) if e else None


def _products(items, ents, prof=None):
    """賣出（收的那筆、數量是負的）：數量、金額（有單價照單價；一個品項的整筆就是它；多品項沒單價照售價分、標估的；沒售價只報數量）、
    毛利（估）＝賣出數量 ×（售價 − 進價），沒進價不算。數量照 Units 換成基本單位（D-344 補）：單價是她講那個單位的價（金額＝單價 ×
    她講的數），售價、進價是基本單位的；換不了的數量分開放 apart、不算毛利、不拿來分金額。"""
    prof = prof or {}
    cache, agg = {}, {}

    def base_qty(ln):
        units = _units(prof, ents, ln["entity"], cache)
        q, g = units.to_base(-_frac(ln["qty"]), ln.get("unit"))
        return q, g, units.base

    for it in items:
        if it.get("dir") != "in" or it.get("status") != "done":
            continue
        sold = [ln for ln in it.get("lines") or [] if Decimal(str(ln.get("qty") or 0)) < 0]
        if not sold:
            continue
        total = _frac(it.get("amount") or 0)
        priced = sum((_frac(ln["unit_price"]) * -_frac(ln["qty"]) for ln in sold if ln.get("unit_price") is not None), Fraction(0))
        rest = [ln for ln in sold if ln.get("unit_price") is None]
        weights = {}
        for ln in rest:
            p = _price(ents, ln["entity"], "售價")
            q, g, base = base_qty(ln)
            weights[id(ln)] = None if p is None or g != base else _frac(p) * q
        known = sum((w for w in weights.values() if w is not None), Fraction(0))
        for ln in sold:
            rec = agg.setdefault(ln["entity"], {"groups": {}, "amount": Fraction(0), "estimated": False, "unknown": False})
            q, g, _base = base_qty(ln)
            rec["groups"][g] = rec["groups"].get(g, Fraction(0)) + q
            if ln.get("unit_price") is not None:
                rec["amount"] += _frac(ln["unit_price"]) * -_frac(ln["qty"])
            elif len(sold) == 1:
                rec["amount"] += total
            elif weights.get(id(ln)) is not None and known and len(rest) == sum(1 for w in weights.values() if w is not None):
                rec["amount"] += (total - priced) * weights[id(ln)] / known
                rec["estimated"] = True
            else:
                rec["unknown"] = True
    out = []
    for name, rec in sorted(agg.items()):
        base = _units(prof, ents, name, cache).base
        main = _pick_main(rec["groups"], base)
        order = [main] + [g for g in rec["groups"] if g != main]
        sell, cost = _price(ents, name, "售價"), _price(ents, name, "進價")
        margin = (_num(rec["groups"][base] * (_frac(sell) - _frac(cost)))
                  if sell is not None and cost is not None and base in rec["groups"] else None)
        amount = None if rec["unknown"] else (_num(Fraction(round(rec["amount"]))) if rec["estimated"] else _num(rec["amount"]))
        out.append({"name": name, "qty": _num(rec["groups"].get(main, Fraction(0))), "unit": main,
                    "apart": [{"unit": g, "qty": _num(rec["groups"][g])} for g in order[1:]],
                    "text": groups_text([(g, rec["groups"][g]) for g in order], base),
                    "amount": amount, "estimated": rec["estimated"], "margin": margin})
    return out


def _pick(items, entity_key=None, advanced_by=None):
    out = items
    if entity_key:
        out = [i for i in out if _touches(i, entity_key)]
    if advanced_by:
        out = [i for i in out if _key(i.get("advanced_by") or "") == _key(advanced_by)]
    return out


def _sums(vault, items, frm, to, ents):
    from kb._lib import entities, numbers
    tot = {"in": Decimal(0), "out": Decimal(0), "open_in": Decimal(0), "open_out": Decimal(0)}
    by_type, rows = {}, []
    for it in items:
        amt = it.get("amount")
        if it.get("status") == "done" and _in_range(it.get("date"), frm, to) and it.get("dir") in ("in", "out"):
            tot[it["dir"]] += Decimal(str(amt or 0))
            rows.append(it)
            first = (it.get("entities") or [None])[0]
            e = entities.find(ents, first)[0] if first else None
            typ = e.get("type") if e else OTHER
            rec = by_type.setdefault(typ, {}).setdefault(first or OTHER, {"name": first or OTHER, "in": Decimal(0), "out": Decimal(0)})
            rec[it["dir"]] += Decimal(str(amt or 0))
        elif it.get("status") == "open" and it.get("dir") in ("in", "out") and (to is None or not it.get("due") or it["due"] <= to):
            tot["open_" + it["dir"]] += Decimal(str(amt or 0))
            rows.append(it)
    n = config.get(vault, "money_rank_n")
    ranked = {t: [{k: numbers.plain(v) if isinstance(v, Decimal) else v for k, v in r.items()}
                  for r in sorted(rs.values(), key=lambda r: -(r["in"] + r["out"]))[:n]] for t, rs in by_type.items()}
    got = {k: numbers.plain(v) for k, v in tot.items()}
    got["net"] = numbers.plain(tot["in"] - tot["out"])
    return got, ranked, rows


def _diff(a, b):
    out = {}
    for k in ("in", "out", "net"):
        x, y = Decimal(str(a[k])), Decimal(str(b[k]))
        from kb._lib import numbers
        out[k] = {"diff": numbers.plain(x - y), "pct": None if y == 0 else round(float((x - y) / abs(y) * 100), 1)}
    return out


def summary(vault, frm, to, entity=None, vs=None, advanced_by=None):
    """kb money sum（D-284 (4)）：照收付日算收、付、淨；未收、未付是到 to 為止到期（或沒到期日）還沒收付的；照型別前幾名；
    商品賣出；vs=(frm, to) 另算一段給差與百分比。帳關著時照標過的口述算（statements_summary）。"""
    if mode(vault) == "off":
        return statements_summary(vault, frm, to, entity=entity, vs=vs)
    ents = _ents(vault)
    k = _key(_entity(ents, entity)["name"]) if entity else None
    items = _pick(_live(load(vault)), k, advanced_by)
    got, ranked, rows = _sums(vault, items, frm, to, ents)
    out = {"from": frm, "to": to, "source": "money", **got, "by_type": ranked,
           "products": _products([i for i in items if _in_range(i.get("date"), frm, to)], ents, _profile(vault)), "vs": None, "diff": None,
           "items": sorted(rows, key=lambda i: (_ref_day(i) or "", i.get("id", "")))}
    if vs:
        other, _r, _rows = _sums(vault, items, vs[0], vs[1], ents)
        out["vs"] = {"from": vs[0], "to": vs[1], **other}
        out["diff"] = _diff(got, other)
    return out


def marked_statements(vault, frm=None, to=None, entity=None):
    """帳關著時標過錢的口述（D-343）：active、money 是物件；照口述的日期篩。"""
    from kb._lib import statements
    k = _key(_entity(_ents(vault), entity)["name"]) if entity else None
    out = []
    for s in statements.load(vault)["statements"]:
        if s.get("status") != "active" or not isinstance(s.get("money"), dict) or not _in_range(s.get("date"), frm, to):
            continue
        if k and not any(_key(n) == k for n in s.get("entities") or []):
            continue
        out.append(s)
    return out


def statements_summary(vault, frm, to, entity=None, vs=None):
    from kb._lib import numbers

    def sums(a, b):
        tot = {"in": Decimal(0), "out": Decimal(0)}
        rows = []
        for s in marked_statements(vault, a, b, entity):
            d = s["money"].get("dir")
            if d in tot:
                tot[d] += Decimal(str(s["money"].get("amount") or 0))
                rows.append({"id": s["id"], "text": s.get("text"), "date": s.get("date"), "dir": d,
                             "amount": s["money"].get("amount"), "entities": list(s.get("entities") or [])})
        got = {"in": numbers.plain(tot["in"]), "out": numbers.plain(tot["out"]), "net": numbers.plain(tot["in"] - tot["out"]),
               "open_in": 0, "open_out": 0}
        return got, rows
    got, rows = sums(frm, to)
    out = {"from": frm, "to": to, "source": "statements", **got, "by_type": {}, "products": [], "vs": None, "diff": None,
           "items": rows}
    if vs:
        other, _rows = sums(vs[0], vs[1])
        out["vs"] = {"from": vs[0], "to": vs[1], **other}
        out["diff"] = _diff(got, other)
    return out


def backfill(vault):
    """改開時補帳（D-343）：標過、還沒進帳（money.ledger 是空的）的口述。"""
    return [s for s in marked_statements(vault) if not s["money"].get("ledger")]


def open_items(vault, data=None):
    data = load(vault) if data is None else data
    return sorted((i for i in data["items"] if i.get("status") == "open"), key=lambda i: (i.get("due") or "9999", i.get("id", "")))


def for_entity(vault, name):
    """kb lookup 的 money（D-278 的內容）：合計（累計收、付，未收、未付）、未收付全部、最近 money_recent_n 筆已收付、庫存
    （商品是那個商品各地點與合計；地點型別的實體是那裡的各商品）。"""
    from kb._lib import numbers, profile
    ents, prof = _ents(vault), _profile(vault)
    e = _entity(ents, name)
    data = load(vault)
    k = _key(e["name"])
    items = [i for i in _live(data) if _touches(i, k)]
    tot = {"in": Decimal(0), "out": Decimal(0), "open_in": Decimal(0), "open_out": Decimal(0)}
    for it in items:
        if it.get("dir") not in ("in", "out"):
            continue
        key_ = it["dir"] if it.get("status") == "done" else "open_" + it["dir"]
        tot[key_] += Decimal(str(it.get("amount") or 0))
    done = sorted((i for i in items if i.get("status") == "done" and i.get("dir") in ("in", "out")),
                  key=lambda i: (i.get("date") or "", i.get("id", "")), reverse=True)
    out = {k2: numbers.plain(v) for k2, v in tot.items()}
    out.update(items=len(items), open=open_items(vault, {"items": items}), recent=done[:config.get(vault, "money_recent_n")],
               total_done=len(done))
    if _key(e.get("type")) in {_key(t) for t in profile.place_types(prof)}:
        out["stock"] = stock(vault, place=e["name"], data=data, prof=prof, ents=ents)["products"]
    else:
        rows = stock(vault, e["name"], data=data, prof=prof, ents=ents)["products"]
        out["stock"] = rows[0] if rows else None
    return out


def owed_to(vault, member, data=None):
    """墊的人還沒還的（D-338）：{"member","total","items"}。"""
    from kb._lib import numbers
    data = load(vault) if data is None else data
    rows = [i for i in data["items"] if i.get("status") == "open" and _key(i.get("advanced_by") or "") == _key(member)]
    total = sum((Decimal(str(i.get("amount") or 0)) for i in rows), Decimal(0))
    return {"member": member, "total": numbers.plain(total), "items": rows}


def related_by_date(vault, names, day, exclude=()):
    """D-273 (3)：同一個實體、到期日是那天、還沒收付的帳（日程改日期時列出來問）。"""
    if not day or not exists(vault):
        return []
    keys = {_key(n) for n in names or []}
    return [i for i in load(vault)["items"] if i.get("status") == "open" and i.get("due") == day and i.get("id") not in exclude
            and keys and any(_key(n) in keys for n in i.get("entities") or [])]


def related_agenda(vault, names, day):
    """D-273 (3)：同一個實體、日期是那天、還開著的日程（改帳的到期日時列出來問）。"""
    from kb._lib import agenda
    if not day:
        return []
    keys = {_key(n) for n in names or []}
    return [i for i in agenda.load(vault)["items"] if i.get("status") == "open" and i.get("date") == day
            and keys and any(_key(n) in keys for n in i.get("entities") or [])]


def related_line(it):
    """「信義王還有一筆 11/30 到期的尾款 120,000」。"""
    from kb._lib import agenda, numbers
    who = "、".join(it.get("entities") or []) or "帳裡"
    amt = numbers.show(it["amount"]) if it.get("amount") is not None else "金額未知"
    return f"{who}還有一筆 {agenda.md_of(it['due'])} 到期的{it.get('text') or DIR_TEXT.get(it.get('dir'), '')} {amt}"


# ---------- 成功句 ----------

def _qty_text(q, unit):
    q = _frac(q)
    return (MINUS if q < 0 else "+") + _show_q(abs(q), unit)


REMOVED_MARK = "（已拿掉）"


def _label(ents, name):
    """帳裡的名字；那個實體拿掉了加註「（已拿掉）」（記帳 2 要做的事 1：名字留著、錢不刪）。"""
    from kb._lib import entities
    e = entities.find(ents, name)[0] if name else None
    if e is not None and e.get("status") == "removed" and _key(e.get("name")) == _key(name):
        return f"{name}{REMOVED_MARK}"
    return name


def describe(vault, it, prof=None, ents=None):
    """「10/30 收 5,000 賣出（李小姐；精華液 −2 瓶、膠囊 −1 瓶，北店）」；列很多筆的呼叫端把 prof、ents 讀一次帶進來。
    品項的數量照 line_text（D-344 補：「精華液 +2 箱（48 瓶）」）。"""
    from kb._lib import agenda, numbers
    prof = _profile(vault) if prof is None else prof
    ents = _ents(vault) if ents is None else ents
    amt = numbers.show(it["amount"]) if it.get("amount") is not None else "金額未知"
    d = it.get("dir")
    if d == "none":
        head = f"{agenda.md_of(it['date'])} {it.get('text') or '數量'}"
    elif it.get("status") != "done" or not it.get("date"):
        head = f"{'未收' if d == 'in' else '未付'} {amt}" + (f"，{agenda.md_of(it['due'])} 到期" if it.get("due") else "")
        if it.get("text"):
            head += f" {it['text']}"
    else:
        head = f"{agenda.md_of(it['date'])} {DIR_TEXT[d]} {amt}" + (f" {it['text']}" if it.get("text") else "")
    parts = [_label(ents, n) for n in it.get("entities") or []]
    lines = it.get("lines") or []
    places = {ln.get("place") for ln in lines}
    one = len(places) == 1 and None not in places
    cache = {}
    shown = [f"{_label(ents, ln['entity'])} {line_text(prof, ents, ln, cache)}"
             + (f"（{_label(ents, ln['place'])}）" if ln.get("place") and not one else "") for ln in lines]
    inside = "；".join(x for x in ["、".join(parts), "、".join(shown) + (f"，{_label(ents, lines[0]['place'])}" if one else "")] if x)
    if it.get("advanced_by"):
        inside += f"{'；' if inside else ''}{it['advanced_by']}墊的"
    return head + (f"（{inside}）" if inside else "")


TELL_LISTED = 5


def tell_lines(vault, turn_id=None):
    """回答末尾說的（照 agenda.tell_lines）：這一回合從檔案記的帳。讀不到就沒有。"""
    from kb._lib import agenda
    turn_id = turn_id or agenda.current_turn(vault)
    if not turn_id or not exists(vault):
        return []
    try:
        items = load(vault)["items"]
    except ValueError:
        return []
    added = [i for i in items if i.get("created_turn") == turn_id and (i.get("origin") or {}).get("card")
             and i.get("status") != "cancelled"]
    if not added:
        return []
    if len(added) > TELL_LISTED:
        return [f"我從檔案記了 {len(added)} 筆帳，說「列帳」我念給你聽"]
    prof, ents = _profile(vault), _ents(vault)
    return [f"我從檔案記了 {len(added)} 筆帳：" + "、".join(describe(vault, i, prof, ents) for i in added)]


# ---------- 製卡抽錢（D-343、D-140 那套） ----------

def _scan_value(fp, on):
    return fp if on else fp + FIELDS_SUFFIX


def unscanned(vault, data=None, groups=None, entries=None, skip=()):
    """money_unscanned：active 的檔案卡、清冊的 money_fp 跟這次該有的不一樣。開著時要 fp 本身；不是開的時候只抽數字欄，
    fp 或 fp:fields 都算抽過（改成開時只抽過數字欄的重列）；不是開、又沒有數字欄的不列（零成本）。每項同 agenda.unscanned，
    existing 是出處是這張卡、沒取消的帳。"""
    from kb._lib import agenda, cards, inventory
    prof = _profile(vault)
    on = mode(vault, prof) == "on"
    if not on and not (prof.get("fields") or []):
        return {"money_unscanned": []}
    data = load(vault) if data is None else data
    groups = cards._scan_groups(vault)[0] if groups is None else groups
    entries = inventory.load(vault)["entries"] if entries is None else entries
    by_id = {e.get("id"): e for e in entries}
    out = []
    for cid, group in sorted(groups.items(), key=lambda kv: kv[1][0]["path"]):
        entry, card = by_id.get(cid), group[0]
        fp = agenda.card_fp(card["front"])
        if entry is None or entry.get("status") != "active" or not fp or cid in skip or entry.get("archived"):
            continue
        have = entry.get("money_fp")
        if have == fp or (not on and have == _scan_value(fp, False)):
            continue
        existing = [{"id": i["id"], "dir": i.get("dir"), "amount": i.get("amount"), "date": _ref_day(i), "text": i.get("text")}
                    for i in data["items"] if i.get("status") != "cancelled" and (i.get("origin") or {}).get("card") == cid]
        title = card["front"].get("標題")
        out.append({"id": cid, "card_path": card["path"], "title": title if isinstance(title, str) else "", "existing": existing})
    return {"money_unscanned": out}


def mark_scanned(vault, card_id, turn_id):
    """kb money scanned：這張卡的錢與數字欄抽過了，清冊記指紋（不是開的時候記 fp:fields）。"""
    from kb._lib import agenda, inventory
    try:
        card = agenda._card(vault, card_id, no_card="這份還沒有檔案卡，先寫卡再抽")
    except agenda.AgendaRefused as e:
        raise MoneyRefused(str(e)) from None
    fp = agenda.card_fp(card["front"])
    changed = inventory.set_money_fp(vault, card_id, _scan_value(fp, mode(vault) == "on"), turn_id)
    title = card["front"].get("標題")
    return {"id": card_id, "title": title if isinstance(title, str) else "", "fp": fp, "changed": changed}


# ---------- 跟著動（實體改名合併、purge；不看開關） ----------

def rename_entity(vault, mapping, turn_id, undo=None):
    """entities.rename／merge 呼叫：entities、lines.entity、lines.place 裡 key 在 mapping 的換成新名。沒有帳什麼都不做。
    拿掉的實體不叫這裡：帳裡的名字留著（錢不刪）。"""
    if not exists(vault):
        return []

    def swap(n):
        return mapping.get(_key(n), n) if n else n

    def fn(data):
        hits = []
        for it in data["items"]:
            names = it.get("entities") or []
            lines = it.get("lines") or []
            if not any(_key(n) in mapping for n in names) and not any(
                    _key(ln.get("entity") or "") in mapping or _key(ln.get("place") or "") in mapping for ln in lines):
                continue
            new = []
            for n in names:
                n = swap(n)
                if all(_key(x) != _key(n) for x in new):
                    new.append(n)
            it["entities"] = new
            for ln in lines:
                ln["entity"], ln["place"] = swap(ln.get("entity")), swap(ln.get("place"))
            hits.append(it)
        if hits and undo is not None:
            undo.file(MONEY_POSIX)
        return hits, bool(hits)
    return _mutate(vault, turn_id, fn)


def purge_cards(vault, card_ids, turn_id):
    """purge 清掉這些卡：出處是這些卡、來源推測的整筆拿掉；她說過的（confirmed、corrected）留著、出處清掉。回動到幾筆。"""
    if not card_ids or not exists(vault):
        return 0

    def fn(data):
        n = drop_cards(data, set(card_ids))
        return n, bool(n)
    return _mutate(vault, turn_id, fn)


def drop_cards(data, ids):
    """purge_cards 與回合夾舊版共用（purge.JSON_DROPS）：改 data，回動到幾筆；形狀不對回 0。"""
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return 0
    n, keep = 0, []
    for it in data["items"]:
        if not isinstance(it, dict):
            keep.append(it)
            continue
        card = (it.get("origin") or {}).get("card") if isinstance(it.get("origin"), dict) else None
        extra = [c for c in it.get("cards") or [] if c in ids]
        if card in ids and it.get("source") == "inferred":
            n += 1
            continue
        if card in ids:
            it["origin"] = None
        if extra:
            it["cards"] = [c for c in it.get("cards") or [] if c not in ids]
        if card in ids or extra:
            n += 1
        keep.append(it)
    data["items"] = keep
    return n
