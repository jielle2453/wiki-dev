"""kb asks [--about <名稱>…] [--all] [--json]、kb asks set-aside <key>（日程第 2 點，D-134、D-135；回答末尾的問法 lint 題，D-225、D-226）。

asks 跟 kb cards todo --json 裡的同一支（plan.build，跑一次 cards.todo）再加上 pending.json 裡沒有整理題的那幾種（plan.pending_asks）；
每題帶 key（穩定的鍵）、about（對象的實體與檔）、urgent（有時間性）。先放著的不列（有時間性的照列）。
沒帶 --all：只回跟這一句有關的（--about 給的實體，別名也認；加上這一回合碰過的：回合帳改到的卡與綜合卡、kb lookup／convert／cards
在對話裡記的 touched）與有時間性的，照急的排、最多 ASKS_MAX 題；others 是其餘的件數（不含先放著），others_line 是這個 session
還沒說過、others 大於 0 時給 AI 原樣貼的一句，印了就在回合記 asks_told（同一個對話之後都帶著，不再說）。
--all（「看待處理」「有沒有要我確認的」，answer）：全部照急的排，set_aside 是先放著的件數，沒有 others_line。
set-aside <key>：p- 開頭的交 kb pending set-aside；其他的（名字確認這類不住在 pending.json 的）記進 .system/set_aside.json
（{key: {at, by, question}}，寫前備進回合）；鍵含問句的指紋，對象變了鍵就變，自然回到前面。找不到「沒有這個問題」exit 3。
有時間性的（逾期、快到期）不收（D-226 補）：exit 3，第一行是改問的那句，接那題現成的答法；--json 帶 refused 與那題 ask。
tell 只帶這一回合做了什麼（D-141）。人讀照編號印問題與選項，沒有就印「沒有要問的」。
"""
import argparse
import json
from datetime import date
from pathlib import Path

from kb import journal_cli
from kb._lib import cards, entities, pending, plan, turn
from kb._lib import io as kio
from kb._lib import sources as sources_lib
from kb.inventory_cli import NOT_IN_VAULT, find_vault

NOTHING = "沒有要問的"
ASKS_MAX = 3  # 回答末尾一次最多幾題（D-135）
OTHERS_LINE = "還有 {n} 件要你決定的事，有空說『看待處理』"
SET_ASIDE_COUNT = "另外有 {n} 件先放著"
SET_ASIDE_LINE = "先放著了：{}；有變化或快到期會再拿出來"
NO_SUCH = "沒有這個問題"
OVERDUE_NO_ASIDE = "這件已經過了日期，沒辦法先放著：做完了、不用了，還是改到哪一天？"
URGENT_NO_ASIDE = "這件快到期了，沒辦法先放著：{question}"
CLI_LOCK_TIMEOUT = 30


def add_arguments(sub):
    sub.add_argument("action", nargs="?", choices=["set-aside"], help="set-aside <key>：這題先放著")
    sub.add_argument("key", nargs="?", help="題目的 key（kb asks --json 每題的 key）")
    sub.add_argument("--about", action="append", default=[], help="這一句講到的實體名稱（別名也認），可以重複")
    sub.add_argument("--all", action="store_true", help="全部列出（看待處理、有沒有要我確認的）")
    sub.add_argument("--vault", help="總資料夾；沒給就從目前目錄往上找")
    sub.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 輸出")


def _collect(vault):
    """(全部題（照急的排，先放著的不在裡面）, 藏了幾題, tell)。"""
    data = cards.todo(vault, sources_lib.load(vault), tell_all=False)
    extra, hidden = plan.pending_asks(vault)
    return plan.order(data["asks"] + extra), data.get("set_aside", 0) + hidden, data["tell"]


def _scope(vault, names):
    """這一句的範圍：--about 的實體（別名也認）、這一回合 touched 的實體與檔、回合帳改到的卡（編號）與綜合卡（實體）。"""
    ents, files = set(), set()
    data = entities.load(vault)
    for name in names:
        e, _hit = entities.find(data, name.strip())
        if e is not None:
            ents.add(e["id"])
    now = turn._read_turn(turn._current_file(vault))  # 只讀，不開回合
    if now:
        got = turn.touched(now)
        ents |= got["entities"]
        files |= got["files"]
        by_card = {entities.card_rel(e, vault).casefold(): e["id"] for e in data["entities"]
                   if e.get("type") and e.get("status") == "active"}
        for row in turn.entries(vault, now["turn"]):
            rel = row["path"]
            if rel.casefold() in by_card:
                ents.add(by_card[rel.casefold()])
            elif rel.startswith(cards.CARDS_DIR + "/") and rel.endswith(".md"):
                try:
                    fid = cards.parse_front((Path(vault) / rel).read_text(encoding="utf-8")).get("編號")
                except (OSError, UnicodeDecodeError, ValueError):
                    fid = None
                if isinstance(fid, str):
                    files.add(fid)
    return ents, files


def _related(ask, ents, files):
    about = ask.get("about") or {}
    return bool(ents & set(about.get("entities") or []) or files & set(about.get("files") or []))


def _pick(asks, ents, files):
    """有時間性的先、再來有關的，最多 ASKS_MAX 題；其餘的算件數。"""
    first = [a for a in asks if a.get("urgent")] + [a for a in asks if not a.get("urgent") and _related(a, ents, files)]
    chosen = first[:ASKS_MAX]
    return chosen, len(asks) - len(chosen)


def _others_line(vault, others):
    """這個 session 還沒說過、others > 0 才給；給了就記 asks_told（終端機記不了，每次都給）。"""
    if not others:
        return None
    now = turn._read_turn(turn._current_file(vault))
    if now and now.get(turn.SESSION_FLAG):
        return None
    try:
        turn.mark(vault, turn.SESSION_FLAG)
    except TimeoutError:
        pass  # 記不到只是下一句可能再說一次
    return OTHERS_LINE.format(n=others)


def _set_aside(vault, key, as_json):
    key = (key or "").strip()
    if not key:
        print(NO_SUCH)
        return 3
    if key.startswith("p-"):  # 住在 pending.json 的不用跑整理（第二輪 T-27：狀態檔壞了也收得了）
        hit = plan.urgent_pending_ask(vault, key)
    else:
        asks, _hidden, _tell = _collect(vault)
        hit = next((a for a in asks if a.get("key") == key), None)
    if hit is not None and hit.get("urgent"):
        return refuse_urgent(hit, as_json)
    turn_id = turn.current(vault)["turn"]
    conversation = journal_cli.in_conversation(vault)
    if key.startswith("p-"):
        try:
            item = pending.set_aside(vault, key, "customer", turn_id)
        except KeyError:
            print(NO_SUCH)
            return 3
        text = item.get("text", "") + (f"：{item['reason']}" if item.get("kind") == "unreadable" and item.get("reason") else "")
        changed = [{"path": pending.PENDING_POSIX, "action": "modify"}, {"path": pending.MD_POSIX, "action": "modify"}]
    else:
        stored = plan.set_aside_keys(vault)
        if hit is None and key not in stored:
            print(NO_SUCH)
            return 3
        text = hit["question"] if hit else stored[key].get("question", "")
        _write_key(vault, key, text, turn_id)
        changed = [{"path": plan.SET_ASIDE_POSIX, "action": "modify"}]
    journal_cli.record_program_or_warn(vault, f"先放著：{text}", changed, "asks set-aside", conversation)
    line = SET_ASIDE_LINE.format(text)
    print(json.dumps({"key": key, "line": line}, ensure_ascii=False) if as_json else line)
    return 0


def refuse_urgent(ask, as_json):
    """有時間性的不能先放著：回改問的那句與那題自己的答法（「還沒，下次再問」照舊只管這個對話）。exit 3。"""
    line = OVERDUE_NO_ASIDE if ask.get("kind") == "overdue" else URGENT_NO_ASIDE.format(question=ask["question"])
    plan.renumber([ask])
    if as_json:
        print(json.dumps({"key": ask["key"], "refused": line, "ask": ask}, ensure_ascii=False))
    else:
        print(line)
        print("\n".join(f"  {r['n']}. {r['label']}" for r in ask["results"]))
    return 3


def _write_key(vault, key, question, turn_id):
    p = Path(vault) / plan.SET_ASIDE_POSIX
    p.parent.mkdir(parents=True, exist_ok=True)
    with kio.FileLock(p):
        keys = plan.set_aside_keys(vault)
        if key in keys:
            return
        turn.backup(vault, plan.SET_ASIDE_POSIX, turn_id)
        keys[key] = {"at": date.today().isoformat(), "by": "customer", "question": question}
        kio.write_json_atomic(p, {"schema_version": 1, "keys": keys})


def _print(asks, tail):
    lines = []
    for ask in asks:
        lines.append(ask["question"])
        lines.extend(f"  {r['n']}. {r['label']}" for r in ask["results"])
    print("\n".join(lines or [NOTHING]))
    for line in tail:
        print(line)


def run(args):
    vault = find_vault(args)
    if vault is None:
        print(NOT_IN_VAULT)
        return 3
    kio.LOCK_TIMEOUT = CLI_LOCK_TIMEOUT
    as_json = getattr(args, "json", False)
    try:
        if args.action == "set-aside":
            return _set_aside(vault, args.key, as_json)
        asks, hidden, tell = _collect(vault)
        if args.all:
            plan.renumber(asks)
            out = {"asks": asks, "set_aside": hidden, "tell": tell}
            tail = [SET_ASIDE_COUNT.format(n=hidden)] if hidden else []
        else:
            ents, files = _scope(vault, args.about)
            chosen, others = _pick(asks, ents, files)
            plan.renumber(chosen)
            line = _others_line(vault, others)
            out = {"asks": chosen, "others": others, "others_line": line, "tell": tell}
            tail = [line] if line else []
    except ValueError as e:
        print(f"狀態檔讀不到：{e}")
        return 3
    except TimeoutError:
        print("等不到鎖（別的指令正在改），沒有寫入；請稍後再試")
        return 3
    except OSError as e:
        print(f"讀不到：{type(e).__name__}: {e}")
        return 3
    if as_json:
        print(json.dumps(out, ensure_ascii=False))
        return 0
    _print(out["asks"], tail)
    if out["tell"]:
        print("回答末尾要說：")
        print("\n".join(out["tell"]))
    return 0
