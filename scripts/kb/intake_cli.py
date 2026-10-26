"""kb intake（收件匣，issue #10，D-240～D-245）：對話裡給的、程式交來的東西存進收件匣的唯一入口，本體在 _lib/intake。
三種用法：kb intake <路徑>… [--title] [--from [--name]]（拖檔、程式交檔）；kb intake --pasted list（這一句貼了什麼）；
kb intake --pasted image:<n>|text:<n> --title <檔名>（存貼的圖或文字）。
人讀一份一行，有新收或更新、又是對話裡跑的，最後一行「接著整理：kb cards dispatch --json」；--json 回 {"items","next"}。
拒絕句一字不差；多份路徑各自判斷，有一份被拒其他照收、exit 3。人讀不印清冊編號。
總資料夾只從 cwd 往上找（不收 --vault，同 convert、output）。對話裡跑的把收到的條目記進回合的 touched（kb asks 當成跟這一句有關），
終端機跑的記一段工作日誌程式段（D-085）。回合照 turn.current()（對話外跑的照 D-502 自己一個回合）。
"""
import argparse
import json
import os

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


def _transcript(vault):
    """這一句的對話紀錄：只在對話裡、還沒答完的回合才有（對話結束後在終端機跑的、別的回合都不取，免得拿到別句貼的東西）。"""
    data = turn.current(vault)
    if not data.get("session_id") or data.get("done"):
        return None
    return data.get("transcript")


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
    for raw in args.paths:  # 一份出錯不擋其他份：已經收好的照樣記日誌、touched
        try:
            got.append(intake.receive(vault, raw, turn_id, os.getcwd(), title=args.title, from_=args.source,
                                      name=args.name))
            continue
        except intake.Refused as e:
            why = str(e)
        except TimeoutError:
            why = LOCK_BUSY
        except OSError as e:
            from kb.finding_cli import rel_of
            why = f"檔案被別的程式開著或沒有權限：{rel_of(vault, e)}"
        got.append({"path": raw, "id": None, "result": "refused", "said": why})
        refused = True
    return got, refused


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
        turn_id = turn.current(vault)["turn"]
        items, refused = _receive(vault, args, turn_id)
    except intake.Refused as e:
        return _refused(as_json, str(e))
    except TimeoutError:
        return _refused(as_json, LOCK_BUSY)
    except ValueError as e:
        return _refused(as_json, f"狀態檔讀不到：{e}")
    except OSError as e:
        from kb.finding_cli import rel_of
        return _refused(as_json, f"檔案被別的程式開著或沒有權限：{rel_of(vault, e)}")
    wrote = [i for i in items if i["result"] in WROTE]
    if wrote:
        if conversation:
            turn.touch(vault, files=[i["id"] for i in wrote])
        journal_cli.record_program_or_warn(
            vault, "；".join(i["said"] for i in wrote),
            [{"path": i["path"], "action": "create" if i["result"] == "new" else "modify"} for i in wrote]
            + [{"path": inventory.INVENTORY_POSIX, "action": "modify"}], "intake", conversation)
    nxt = DISPATCH if wrote and conversation else None
    lines = [i["said"] for i in items] + ([NEXT] if nxt else [])
    _out(as_json, lines, {"items": items, "next": nxt})
    return 3 if refused else 0
