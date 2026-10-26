"""kb intake（收件匣，issue #10，D-240～D-245）：對話裡給的、程式交來的東西存進收件匣的唯一入口，本體在 _lib/intake。
三種用法：kb intake <路徑>… [--title] [--from [--name]]（拖檔、程式交檔）；kb intake --pasted list（這一句貼了什麼）；
kb intake --pasted image:<n>|text:<n> --title <檔名>（存貼的圖或文字）。
人讀一份一行，有新收或更新、又是對話裡跑的，最後一行「接著整理：kb cards dispatch --json」；--json 回 {"items","next"}。
拒絕句一字不差；多份路徑各自判斷，有一份被拒其他照收、exit 3。人讀不印清冊編號。
總資料夾只從 cwd 往上找（不收 --vault，同 convert、output）。對話裡跑的把收到的條目記進回合的 touched（kb asks 當成跟這一句有關），
終端機跑的記一段工作日誌程式段（D-085）。回合：守門替主對話插的全域 --session 在時用那個對話的回合（.system/turns/<sid>.json，
兩個對話開同一個知識庫時不會記到別句，收件匣裁定 6），沒有就照 turn.current()（終端機、對話外跑的照 D-502 自己一個回合）。
--pasted 只認 --session 那個對話還沒答完的回合記的對話紀錄；沒有 --session 一律拿不到。多份路徑時被拒那行前面加「<原檔名>：」。
"""
import argparse
import json
import os
from pathlib import Path

from kb import journal_cli
from kb._lib import intake, inventory, turn
from kb._lib import io as kio
from kb.inventory_cli import NOT_IN_VAULT, find_vault

CLI_LOCK_TIMEOUT = 30
LOCK_BUSY = "等不到鎖，沒有寫入"
DISPATCH = "kb cards dispatch --json"
NEXT = "接著整理：" + DISPATCH
NOTHING = "要給檔的路徑，或 --pasted"
ONE_ONLY = "--title、--name 一次只收一份"
PASTED_WITH_PATHS = "--pasted 不跟檔的路徑一起用"
NO_PASTED = "這一句沒有貼圖或文字"
WROTE = ("new", "updated")


def add_arguments(sub):
    sub.add_argument("paths", nargs="*", metavar="路徑", help="要收的檔（拖進對話的、程式交來的）")
    sub.add_argument("--title", help="檔名（原檔名看不出內容、貼的東西沒有檔名時給；副檔名程式加）")
    sub.add_argument("--from", dest="source", help="程式或 skill 交來的：來源名（例：公司系統）")
    sub.add_argument("--name", help="定期同步的項目名（要配 --from）：存 收件匣/<來源>/<項目>，再交就覆蓋")
    sub.add_argument("--pasted", help="list 列這一句貼的圖與文字；image:<n> 或 text:<n> 存那一項（要給 --title）")
    sub.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="以 JSON 輸出")


def _out(as_json, lines, payload):
    print(json.dumps(payload, ensure_ascii=False) if as_json else "\n".join(lines))


def _refused(as_json, line):
    _out(as_json, [line], {"items": [{"path": None, "id": None, "result": "refused", "said": line}], "next": None})
    return 3


def _session_turn(vault):
    """--session 那個對話自己的回合檔（.system/turns/<sid>.json）；沒有 --session 或讀不到回 None，不退到 current.json。"""
    if not turn.SESSION:
        return None
    return turn._read_turn(turn._session_file(vault, turn.SESSION))


def _turn(vault):
    """這次呼叫算哪個回合：有 --session 用那個對話的回合檔；沒有 --session（終端機、對話外）或那份讀不到才照 turn.current()。"""
    return _session_turn(vault) or turn.current(vault)


def _transcript(vault):
    """這一句的對話紀錄：只認 --session 那個對話、還沒答完的回合（終端機、對話答完、別的對話的都不取，免得拿到別句貼的東西）。"""
    data = _session_turn(vault)
    if not data or data.get("done"):
        return None
    return data.get("transcript")


def _touch(vault, turn_id, ids):
    """收到的條目記進這次呼叫的回合 touched：turn.touch 只看 --turn 或 current.json，--session 的回合要借 OVERRIDE 指過去。"""
    saved = turn.OVERRIDE
    turn.OVERRIDE = turn_id
    try:
        turn.touch(vault, files=ids)
    finally:
        turn.OVERRIDE = saved


def _list(vault, as_json):
    try:
        items = intake.pasted_list(_transcript(vault))
    except intake.NotInTranscript:
        lines = [intake.NO_IMAGE, intake.NO_TEXT]
        _out(as_json, lines, {"items": [], "message": lines})
        return 3
    lines = [f"{i['ref']}（{i['media_type']}，{i['bytes']} 位元組）" if i["kind"] == "image" else f"{i['ref']}（{i['chars']} 字）"
             for i in items]
    _out(as_json, lines or [NO_PASTED], {"items": items})
    return 0


def _receive(vault, args, turn_id):
    if args.pasted:
        return [intake.receive_pasted(vault, args.pasted, args.title, turn_id, _transcript(vault))], False
    got, refused = [], False
    many = len(args.paths) > 1
    for raw in args.paths:  # 一份出錯不擋其他份：已經收好的照樣記日誌、touched
        try:
            got.append(intake.receive(vault, raw, turn_id, os.getcwd(), title=args.title, from_=args.source,
                                      name=args.name))
            continue
        except intake.Refused as e:
            why = str(e)
        except OSError as e:
            why = _os_error(vault, e)
        if many:  # 多份時 AI 不用靠順序對（收件匣裁定 6）
            why = f"{Path(raw).name}：{why}"
        got.append({"path": raw, "id": None, "result": "refused", "said": why})
        refused = True
    return got, refused


def _os_error(vault, e):
    if isinstance(e, TimeoutError):
        return LOCK_BUSY
    if intake.too_long(e):
        return intake.TOO_LONG
    from kb.finding_cli import rel_of
    return f"檔案被別的程式開著或沒有權限：{rel_of(vault, e)}"


def run(args):
    as_json = getattr(args, "json", False)
    vault = find_vault(args)
    if vault is None:
        print(NOT_IN_VAULT)
        return 3
    if args.name and not args.source:
        return _refused(as_json, intake.NAME_NEEDS_FROM)
    if args.pasted and args.paths:
        return _refused(as_json, PASTED_WITH_PATHS)
    if not args.pasted and not args.paths:
        return _refused(as_json, NOTHING)
    if args.pasted and args.pasted.strip() != "list" and not args.title:
        return _refused(as_json, intake.PASTED_NEEDS_TITLE)
    if len(args.paths) > 1 and (args.title or args.name):
        return _refused(as_json, ONE_ONLY)
    kio.LOCK_TIMEOUT = CLI_LOCK_TIMEOUT
    try:
        if args.pasted and args.pasted.strip() == "list":
            return _list(vault, as_json)
        conversation = journal_cli.in_conversation(vault)
        turn_id = _turn(vault)["turn"]
        items, refused = _receive(vault, args, turn_id)
    except intake.Refused as e:
        return _refused(as_json, str(e))
    except ValueError as e:
        return _refused(as_json, f"狀態檔讀不到：{e}")
    except OSError as e:
        return _refused(as_json, _os_error(vault, e))
    wrote = [i for i in items if i["result"] in WROTE]
    if wrote:
        if conversation:
            _touch(vault, turn_id, [i["id"] for i in wrote])
        journal_cli.record_program_or_warn(
            vault, "；".join(i["said"] for i in wrote),
            [{"path": i["path"], "action": "create" if i["result"] == "new" else "modify"} for i in wrote]
            + [{"path": inventory.INVENTORY_POSIX, "action": "modify"}], "intake", conversation)
    nxt = DISPATCH if wrote and conversation else None
    lines = [i["said"] for i in items] + ([NEXT] if nxt else [])
    _out(as_json, lines, {"items": items, "next": nxt})
    return 3 if refused else 0
