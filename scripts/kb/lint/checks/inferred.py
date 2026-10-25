"""清單 5（原 9）：推測放太久沒確認（lint_inferred_days 天）：AI 從檔案猜的日程（source inferred）、猜的實體名稱（inferred）、
設定檔來源是推測的列。各合成一件待處理（同一類一件）。日程那件帶各條的日期，快到期時先放著也會回到前面。"""
from kb._lib import agenda
from kb.lint import runner

NAME = "推測放太久"
PROFILE_SECTIONS = (("types", "name"), ("card_types", "name"), ("exclusions", "kind"), ("synthesis_sections", "type"),
                    ("about", "name"))
SHOWN = 5


def _since(it):
    hist = it.get("history") or []
    if hist and isinstance(hist[0], dict) and hist[0].get("date"):
        return hist[0]["date"]
    return str(it.get("created_turn") or "")[:8]


def _iso(day):
    day = str(day)
    return f"{day[:4]}-{day[4:6]}-{day[6:8]}" if len(day) == 8 and day.isdigit() else day


def _old(ctx, day, limit):
    n = ctx.days_since(_iso(day))
    return n is not None and n > limit


def _names(items):
    shown = "、".join(items[:SHOWN])
    return shown + ("…" if len(items) > SHOWN else "")


def run(ctx):
    limit = ctx.config("lint_inferred_days")
    out = []
    try:
        items = agenda.load(ctx.vault)["items"]
    except ValueError:
        items = []
    old = [it for it in items if it.get("status") == "open" and it.get("source") == "inferred" and _old(ctx, _since(it), limit)]
    if old:
        texts = [f"{it.get('date')} {it.get('text')}" for it in old]
        out.append(runner.finding(
            "inferred", "decide", "inferred:agenda",
            f"日程有 {len(old)} 條是我從檔案推測的，放了超過 {limit} 天還沒確認：{_names(texts)}",
            items=texts, data={"dates": sorted({it["date"] for it in old if it.get("date")}),
                               "results": [{"label": "一條一條看", "note": "kb agenda list 唸出推測的那幾條，對的照原樣 kb agenda edit "
                                                                         "（記成確認），不對的照她說的改"}]}))
    ents = [e for e in ctx.entities()["entities"] if e.get("status") == "active" and e.get("source") == "inferred"
            and _old(ctx, e.get("date") or "", limit)]
    if ents:
        names = [e["name"] for e in ents]
        out.append(runner.finding(
            "inferred", "decide", "inferred:entity",
            f"有 {len(ents)} 個名字是我猜的，放了超過 {limit} 天還沒確認：{_names(names)}", items=names,
            data={"names": names, "results": [{"label": "名字都對", "do": [f"kb entity confirm {n}" for n in names if " " not in n]}]},
            entity_ids=[e["id"] for e in ents]))
    prof = ctx.profile()
    rows = [f"{sec}:{row.get(key)}" for sec, key in PROFILE_SECTIONS for row in prof.get(sec) or []
            if isinstance(row, dict) and row.get("source") == "inferred" and _old(ctx, row.get("date") or "", limit)]
    if rows:
        out.append(runner.finding(
            "inferred", "decide", "inferred:profile",
            f"設定檔有 {len(rows)} 列是我推測的，放了超過 {limit} 天還沒確認",
            items=rows, data={"rows": rows, "results": [{"label": "一列一列看", "note": "kb profile show 唸出來源是推測的列，"
                                                                                     "她說對的請她在設定檔把來源改成確認，或照 note skill 改規則"}]}))
    return out
