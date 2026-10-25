"""清單 10（B-106）：設定檔改了之後、之前做的卡。卡型那節的列比檔案卡的製卡日期新 → 那類的卡合成一件待處理
（她說好就 kb cards redo --ids 交 card-maker 重做）；第四節（每類最想知道什麼）的列比綜合卡的更新日新 → 綜合卡標要更新（設定檔改了）。"""
from kb._lib import cards as cards_lib
from kb._lib import entities
from kb.lint import runner
from kb.lint.checks import _synthesis

NAME = "設定檔改了之後的卡"
REASON = "設定檔改了"
REDO_SHOWN = 200  # 一件最多帶幾張的編號（一次重做太多交 card-maker 也要排很久）


def _old_cards(ctx, row):
    day = str(row.get("date") or "")
    if not day:
        return []
    return sorted(cid for cid, c in ctx.cards().items()
                  if entities.key(str(c["front"].get("卡型") or "")) == entities.key(row["name"])
                  and str(c["front"].get("製卡日期") or "9999") < day)


def run(ctx):
    prof = ctx.profile()
    out = []
    for row in prof.get("card_types") or []:
        ids = _old_cards(ctx, row)
        if not ids:
            continue
        ids = ids[:REDO_SHOWN]
        out.append(runner.finding(
            "stale_by_profile", "decide", f"redo_by_profile:{row['name']}:{row['date']}",
            f"設定檔的「{row['name']}」那類 {row['date']} 改過，有 {len(ids)} 張卡是之前做的；要不要照新的設定重做？",
            data={"card_type": row["name"], "date": row["date"], "ids": ids,
                  "results": [{"label": "好，重做", "do": [cards_lib_redo(ids)],
                               "note": "跑完照 ingest skill 整理（交製卡助手在背景做），跟她說幾張、大約多久"}]},
            file_ids=ids))
    hits = []
    for e, rel, text in ctx.synthesis():
        rows = [s for s in prof.get("synthesis_sections") or [] if entities.key(s.get("type")) == entities.key(e.get("type"))]
        try:
            updated = str(cards_lib.parse_front(text).get("更新日") or "")
        except ValueError:
            continue
        if any(str(s.get("date") or "") > updated for s in rows):
            hits.append({"path": rel, "name": e["name"]})
    if hits:
        out.append(_synthesis.fix_finding("stale_by_profile", "stale_by_profile", REASON, hits))
    return out


def cards_lib_redo(ids):
    return "kb cards redo --ids " + ",".join(ids)
