"""SessionStart 開場注入入口（D-087、D-060）：對話一開始、resume、clear、摺疊後，把狀態行與 rules/core.md 全文帶進 additionalContext。

狀態行固定順序、回 None 的不印；第一行固定以「【wiki-with-willy】」開頭，知識庫 CLAUDE.md 的哨兵句認這個字串（D-088）。
輸出 ensure_ascii=True：純 ASCII 不碰 cp950（I-001）。不碰 guard-status、ledger、回合、日誌；
唯一寫的是 .system/env.json 的「找不到的來源已報過」記號（清冊題，D-094 補），清冊只讀（快速 scan，不 apply）；
客戶設定檔那行也只讀（profile.status，不寫 profile.json 與 md）；變動行的實體夾有變也只讀（entities.drift）；日程行只讀 agenda.json。
收件匣行（line_inbox，排在日程行之後，D-045）印了才寫 env.json 的 inbox_reminded（這台電腦每 inbox_remind_every_days 天最多一次）。
沒有新變動、但清冊還有沒做成卡的或要跟著原檔搬的卡（batches.opening_counts，只讀；讀不到記進待處理的、還沒清的排除夾裡的不算，
B-415）：變動行改印「還有 N 份沒整理完、M 張卡要跟著搬」（0 的那半不印），後面接整理指示（開頭不寫「有變動：」，answer 第 9b 點、
裁定 14，D-161）；算超過開場時限就這行不印、寫 log。
payload 的 session 在這個對話按過停止（session 檔記著 ingest_stopped，compact／resume 時）就不印整理指示（D-156、裁定 14）；
這一步只讀 session 檔。
換了位置、換了電腦（備份還原與換電腦，D-206、D-208）：line_moved 排在變動行前面；這台與別台都沒有位置紀錄（first）時默默寫 vault_path、補 vault.json、
不印（moved.note_place，測試 T-2：不記的話用了幾個月的知識庫永遠認不出搬家）；換了位置、換了電腦時只讀（不寫 vault_path，kb moved 做完才寫）；
印了這行時整理指示與「找不到來源」兩行都不印（先補位置：相對位置的來源會被當成不見，找不到來源那行還會把「已報過」記號寫掉，kb moved 會逐個列出來）。
升級打包（D-215、D-217）：line_version 排在 kb 行之後、line_moved 前面，只用上一次查的結果（env.json 的 update_check），不連網；
日期不是今天（且清單網址有填）就背景開一個 kb upgrade --background 的子行程、不等它；沒有 upgrade-history.json 就記成現在版本、不印；
換了版要 kb upgrade --finish 時整理指示不印（跟 line_moved 同一處判斷）。這支多寫 .system/upgrade-history.json（第一次）與 env.json 的 update_check（日期）。
背景健檢（lint 題，D-221、D-227）：.system/lint.json 的上次健檢超過 lint_background_days 天（或沒跑過）、今天還沒開過，就背景開
kb lint --background（同升級那支的做法，不等它；兩支互不等）；開場不另外印一行（line_health 照留空殼）。健檢標成要改寫的綜合卡
在同一行另講「K 張綜合卡要改寫」（「N 份沒整理完」只數檔，桌面版確認後 3a 定；D-161）。這支多寫 lint.json 的 last_spawn（今天開過了）。
core.md 之後接設定檔第六節的「客戶偏好（…照核心規則）：」一條一行（D-137，沒有不印；讀不到這段不印、寫 log；框住，測試後修正裁定 15）。
任何例外寫 .system/hook-errors.log（source session），永遠 exit 0。找到知識庫之後的例外另印一行出錯的 additionalContext
（失敗明講，開場注入測試後修正 D2）；找不到知識庫、stdin 壞掉不輸出。write／flush 也包住：pipe 斷掉照樣 exit 0。
hook 不是從 scripts/ 跑的，所以這裡動 sys.path（hooks/*.py 是唯一例外，CLAUDE.md 三）。
"""
import json
import os
import sys
import time

sys.dont_write_bytecode = True
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
_START = time.monotonic()  # 開場 hook 的時限從這裡算
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

COMPACT_LINE = "對話剛摺疊，規則已重新帶入；做到一半的事以工作日誌為準。"
ERROR_LINE = "【wiki-with-willy】開場程式出錯（{}），詳見 .system/hook-errors.log；這個對話不改任何檔。"


def line_kb(vault):
    """永遠有值：kb 指令的完整呼叫前綴（D-013、D-019 不寫進檔，只在這裡印）。"""
    from kb._lib import paths

    return f'【wiki-with-willy】kb 指令：python "{paths.plugin_root().as_posix()}/scripts/kb.py" <子命令>'


_UPGRADE = {}  # vault → upgrade.opening 的結果或 None（出錯）；line_version 與整理指示讓位共用，log 只記一行


def _upgrade_state(vault):
    """升級打包第 7 點：upgrade.opening 不連網、不等背景（日期不是今天才開 kb upgrade --background 的子行程）；
    沒有 upgrade-history.json 就記成現在版本。歷史壞了或出任何錯回 None、記一行 log，其他行照印。"""
    key = str(vault)
    if key not in _UPGRADE:
        try:
            from kb._lib import upgrade

            _UPGRADE[key] = upgrade.opening(vault)
        except Exception as e:  # noqa: BLE001
            _UPGRADE[key] = None
            _log_vault(vault, e)
    return _UPGRADE[key]


def line_version(vault):
    """升級打包第 7 點（D-060、D-215、D-217）：(a) 換了版要 --finish、(b) 上次查到她可以拿的大升級、(c) 清單被指回舊版；其他不印。
    排在 kb 那行之後、變動那行之前。"""
    state = _upgrade_state(vault)
    return state["line"] if state else None


MOVED_LINE_TEXT = "知識庫換了位置：先跑 kb moved 補好再做別的。"
NEW_MACHINE_LINE = "這台電腦第一次開這個知識庫：先跑 kb moved 看要補什麼。"
_MOVED = {}  # vault → state（moved｜new_machine｜same｜first）或 None（出錯）；line_moved 與兩條讓位的行共用，log 只記一行


def _moved_state(vault):
    key = str(vault)
    if key not in _MOVED:
        try:
            from kb._lib import moved

            _MOVED[key] = moved.note_place(vault)  # first 時默默記位置、補 vault.json（測試 T-2），其他狀態只讀；回 state
        except Exception as e:  # noqa: BLE001
            _MOVED[key] = None
            _log_vault(vault, e)
    return _MOVED[key]


def line_moved(vault):
    """備份還原與換電腦第 4 點：env.json 這台電腦記的位置跟現在不同 → 換了位置；這台沒有紀錄、但有別台的 → 第一次開。只讀。"""
    state = _moved_state(vault)
    return {"moved": MOVED_LINE_TEXT, "new_machine": NEW_MACHINE_LINE}.get(state)


CHANGES_LINE = "變動：新增 {added}、修改 {modified}、不見 {missing}"
CHANGES_INCOMPLETE = "變動：來源很大還沒比完，說「有什麼變動」我再比"
MISSING_SOURCES_LINE = "這台電腦找不到來源{names}，其他照常；搬過的話跟我說。"
MISSING_SOURCES_SHOWN = 3
# D-156（note 改規則實作中裁定 1）：先整理、整理完再回答；門檻內開始前照 announce 說一句（D-100 修訂）。
# 怎麼派 card-maker 只寫在 ingest 的 SKILL.md，開場句不提（開場預算，card-maker 實作疑義 22 定）
HINT_HEAD = "有變動："
INGEST_HINT = ("有變動：先照 ingest skill 整理（開始前照 announce 說一句），整理完再完整回答客戶；"
               "超過 {n} 份不整理，先用現有資料答、末尾問要不要整理。")
_SCAN = {}  # vault → (sources, report) 或 None（scan 出錯）；兩行共用一次快速 scan（審閱裁定 9）


def _quick_scan(vault):
    """快速比對一次；出錯只在第一次記一行 log，之後兩行都回 None。"""
    key = str(vault)
    if key not in _SCAN:
        try:
            from kb._lib import inventory
            from kb._lib import sources as sources_lib

            sources = sources_lib.load(vault)
            _SCAN[key] = (sources, inventory.scan(vault, sources, quick=True))
        except Exception as e:  # noqa: BLE001
            _SCAN[key] = None
            _log_vault(vault, e)
    return _SCAN[key]


DRIFT_PART = "、實體夾有變 {n}"
DRIFT_LINE = "變動：實體夾有變 {n}"
_DRIFT = {}  # vault → 實體夾有變的筆數或 None（出錯）；line_changes 被叫兩次，log 只記一行


def _drift_count(vault):
    """實體與綜合卡第 7 點：entities.drift 只讀，跟快速 scan 各自 try；實體清單壞了回 None、記一行 log。"""
    key = str(vault)
    if key not in _DRIFT:
        try:
            from kb._lib import entities

            _DRIFT[key] = len(entities.drift(vault))
        except Exception as e:  # noqa: BLE001
            _DRIFT[key] = None
            _log_vault(vault, e)
    return _DRIFT[key]


UNSORTED_LINE = "還有 {n} 份沒整理完"
MOVED_LINE = "{n} 張卡要跟著搬"
FIX_LINE = "{n} 張綜合卡要改寫"  # 健檢標的（lint 題）：檔與綜合卡分開講，「份」只數檔
LEFT_HEAD = "還有 "
UNSORTED_BUDGET = 6  # 秒，從 hook 開始算；SessionStart 逾時 10 秒，留給讀 core.md 與其他行
_UNSORTED = {}  # vault → 還沒整理的份數或 None（出錯、超時）；line_changes 被叫兩次，log 只記一行


def _unsorted_count(vault, sources):
    """D-161、B-415：(還沒整理的份數, 要跟著搬的卡, 健檢標的要改寫綜合卡)（batches.opening_counts、synthesis.lint_fix_count，只讀）；
    超過時限丟 TimeoutError，跟其他錯一樣記一行 log、回 None。"""
    key = str(vault)
    if key not in _UNSORTED:
        try:
            from kb._lib import batches, synthesis

            left, moved = batches.opening_counts(vault, sources, deadline=_START + UNSORTED_BUDGET)
            _UNSORTED[key] = (left, moved, synthesis.lint_fix_count(vault))
        except Exception as e:  # noqa: BLE001
            _UNSORTED[key] = None
            _log_vault(vault, e)
    return _UNSORTED[key]


def line_changes(vault):
    """清冊題：新增、修改、不見三個數都 0 且比完 → None；走訪時間到 → 還沒比完。搬動、重複、之前就不見的不印。
    實體夾有變 N（D-057，客戶改了實體夾名、卡名、刪夾）接在後面；清冊沒變動但 N > 0 自己成一行。
    清冊沒變動、實體夾也沒變，但還有沒整理完的或要跟著搬的卡 → 「還有 N 份沒整理完、M 張卡要跟著搬」（D-161，0 的那半不印）。"""
    got = _quick_scan(vault)
    drift = _drift_count(vault) or 0
    if got is None:
        return DRIFT_LINE.format(n=drift) if drift else None
    report = got[1]
    if report["incomplete"]:
        return CHANGES_INCOMPLETE
    counts = {k: len(report[k]) for k in ("added", "modified", "missing")}
    if any(counts.values()):
        return CHANGES_LINE.format(**counts) + (DRIFT_PART.format(n=drift) if drift else "")
    if drift:
        return DRIFT_LINE.format(n=drift)
    counts = _unsorted_count(vault, got[0])
    if not counts or not any(counts):
        return None
    left, moved, fixes = counts
    parts = (([UNSORTED_LINE.format(n=left)] if left else []) + ([FIX_LINE.format(n=fixes)] if fixes else [])
             + ([MOVED_LINE.format(n=moved)] if moved else []))
    line = "、".join(parts)
    return line if line.startswith(LEFT_HEAD) else LEFT_HEAD + line


def _stopped(vault, session_id):
    """這個 session 按過停止嗎：session 檔記著 ingest_stopped（turn hook 記的，answer 第 9 點）。只讀；讀不到（壞 JSON、OSError）
    當沒按過，OSError 寫一行 log（answer 裁定 34），整理指示照印。"""
    if not session_id:
        return False
    from kb._lib import turn

    try:
        data = turn._read_turn(turn._session_file(vault, session_id))
    except OSError as e:
        _log_vault(vault, e)
        return False
    return bool(data and data.get("ingest_stopped"))


def line_ingest_hint(vault, session_id=None):
    """ingest 製卡第 7 點：變動行（含還沒比完）印出來時緊接著一行，叫 AI 先照 ingest skill 整理、整理完再回答（D-156）；n 讀 ingest_auto_max。
    接在「還有 N 份沒整理完」後面時開頭不寫「有變動：」；這個 session 按過停止就不印（answer 裁定 14）。"""
    line = line_changes(vault)
    state = _upgrade_state(vault)
    if (line is None or _stopped(vault, session_id) or line_moved(vault)  # 先補位置，免得相對位置的來源被當成不見
            or (state and state["finish"])):  # 先 kb upgrade --finish 轉格式，免得轉格式前就開始整理
        return None
    from kb._lib import config

    hint = INGEST_HINT.format(n=config.get(vault, "ingest_auto_max"))
    return hint[len(HINT_HEAD):] if line.startswith(LEFT_HEAD) else hint


def line_missing_sources(vault):
    """清冊題：這台電腦找不到的來源，每台電腦只報一次（env.json 記號）；又找得到就清掉記號，之後再失蹤再報。"""
    if line_moved(vault):  # kb moved 會列這台找不到的來源；這裡報了就把「已報過」記號寫掉
        return None
    got = _quick_scan(vault)
    if got is None:
        return None
    from kb._lib import env

    sources, report = got
    lost = {(m["id"] or m["alias"]): m["alias"] for m in report["missing_sources"]}
    env.clear_missing(vault, [s["id"] or s["alias"] for s in sources.entries if (s["id"] or s["alias"]) not in lost])
    new = {k: alias for k, alias in lost.items() if not env.missing_reported(vault, k)}
    if not new:
        return None
    env.mark_missing(vault, list(new))
    aliases = list(new.values())
    names = "、".join(f"「{alias}」" for alias in aliases[:MISSING_SOURCES_SHOWN])
    if len(aliases) > MISSING_SOURCES_SHOWN:
        names += f"等 {len(aliases)} 個"  # 最多列 3 個，整行守在開場預算裡（審閱裁定 32）
    return MISSING_SOURCES_LINE.format(names=names)


PROFILE_CHANGED = "設定檔有改（{summary}）：先 kb profile check 複述，客戶說好才 apply"
PROFILE_ERROR = "設定檔有改但讀不懂：{error}；改好下次再問"
PROFILE_UNLISTED = "第一層夾{names}不在型別表（請客戶補進設定檔）"
PROFILE_LINE_MAX = 120
PROFILE_UNLISTED_SHOWN = 2


def line_profile(vault):
    """客戶設定檔與型別第 7 點：profile.status 只讀、不寫 JSON 也不寫 md。有改（有內容差異）或讀不懂各一句；
    第一層有不在型別表的夾接在同一行後面，沒有前半時自己成一行（開頭「設定檔：」）；整行超過 120 字夾名只列 2 個。"""
    from kb._lib import profile

    st = profile.status(vault)
    head = None
    if st["state"] == "changed" and profile.has_diff(st["diff"]):
        head = PROFILE_CHANGED.format(summary=profile.summary_short(st["diff"]))
    elif st["state"] == "error":
        head = PROFILE_ERROR.format(error=st["error"])
    if not st["unlisted"]:
        return head

    def joined(names, more):
        text = "、".join(f"「{n}」" for n in names) + (f"等 {more} 個" if more else "")
        tail = PROFILE_UNLISTED.format(names=text)
        return f"{head}；{tail}" if head else f"設定檔：{tail}"
    line = joined(st["unlisted"], 0)
    if len(line) > PROFILE_LINE_MAX:
        line = joined(st["unlisted"][:PROFILE_UNLISTED_SHOWN], len(st["unlisted"]))
    return line


AGENDA_OVERDUE_HINT = "（回答末尾跑 kb asks 照著問）"


def line_agenda(vault):
    """日程題第 6 點（D-060、D-129）：逾期、今天、N 天內三個數字，0 的項不印、全 0 整行不印；有逾期時數字後面接一句，
    叫 AI 回答末尾跑 kb asks 照著問。N 讀 agenda_window_days。只讀（agenda.json 壞了丟例外，由 status_lines 記 log、其他行照印）。"""
    from kb._lib import agenda, config

    counts = agenda.counts(vault, agenda.load(vault))
    parts = []
    if counts["overdue"]:
        parts.append(f"逾期 {counts['overdue']}{AGENDA_OVERDUE_HINT}")
    if counts["today"]:
        parts.append(f"今天 {counts['today']}")
    if counts["upcoming"]:
        parts.append(f"{config.get(vault, 'agenda_window_days')} 天內 {counts['upcoming']}")
    return "日程：" + "、".join(parts) if parts else None


INBOX_LINE = "收件匣：{n} 份沒歸位、最久 {days} 天；回答末尾問她要不要一起看，說好再跑 kb asks --all"


def line_inbox(vault):
    """收件匣第 6 點（D-045）：收件匣最上層（不含子夾、跳過 . 開頭）的檔數到 inbox_remind_files，或最舊一份（清冊 first_seen，
    沒有用修改時間）超過 inbox_remind_days 天，而且這台電腦上次提醒是 inbox_remind_every_days 天前或沒提醒過，才印並記今天
    （env.json 的 inbox_reminded）；不成立不印、不記。版本那行（有新版、撤回、換了版）印了就不印也不記，下次開場再提醒
    （收件匣裁定 2：開場預算，收件匣不急）。出錯由 status_lines 記 log。"""
    from datetime import date, datetime
    from kb._lib import config, env, inventory

    if line_version(vault):
        return None
    root = os.path.join(str(vault), inventory.INBOX)
    if not os.path.isdir(root) or os.path.islink(root):
        return None
    with os.scandir(root) as it:  # 清冊走訪不讀的（. 開頭、~$ 這類、隱藏或系統屬性）不算
        files = [e for e in it if not e.name.startswith(".") and not inventory._skipped_name(e.name)
                 and e.is_file(follow_symlinks=False)
                 and not getattr(e.stat(follow_symlinks=False), "st_file_attributes", 0) & inventory.HIDDEN_OR_SYSTEM]
    if not files:
        return None
    today = date.today()
    last = env.inbox_reminded(vault)
    if last:
        try:
            if (today - date.fromisoformat(last)).days < config.get(vault, "inbox_remind_every_days"):
                return None
        except ValueError:
            pass
    seen = {}
    try:
        for e in inventory.load(vault)["entries"]:
            if e.get("status") != "active":
                continue
            for loc in e.get("locations") or []:
                seen.setdefault(inventory.uri_key(loc.get("uri", "")), str(e.get("first_seen") or ""))
    except ValueError:
        pass
    oldest = today
    for f in files:
        first = seen.get(inventory.uri_key(inventory.make_uri(inventory.INBOX, f.name)), "")
        try:
            day = date.fromisoformat(first[:10]) if first else datetime.fromtimestamp(f.stat().st_mtime).date()
        except ValueError:
            day = datetime.fromtimestamp(f.stat().st_mtime).date()
        oldest = min(oldest, day)
    days = (today - oldest).days
    if len(files) < config.get(vault, "inbox_remind_files") and days <= config.get(vault, "inbox_remind_days"):
        return None
    env.set_inbox_reminded(vault, today.isoformat())
    return INBOX_LINE.format(n=len(files), days=days)


def line_backup(vault):
    """等備份題。"""
    return None


def line_health(vault):
    """lint 題：健檢的事併進回答末尾的「還有 N 件」（D-225），開場不另外提醒（D-221 修訂）。"""
    return None


BACKGROUND_LINT_BUDGET = 7  # 秒，從 hook 開始算；前面的行用掉太多時間這次就不開（SessionStart 逾時 10 秒）


def start_background_lint(vault):
    """背景健檢的觸發（D-221、D-227）：kb.lint.runner.opening 判斷要不要開、開了不等。出錯只記 log。
    開場叫她先補位置（line_moved）或先 kb upgrade --finish 時不開：搬了家還沒補，健檢會把出處點不開記成要她決定的事；
    跟整理指示讓位是同一處判斷。"""
    state = _upgrade_state(vault)
    if line_moved(vault) or (state and state["finish"]) or time.monotonic() - _START > BACKGROUND_LINT_BUDGET:
        return
    try:
        from kb.lint import runner

        runner.opening(vault)
    except Exception as e:  # noqa: BLE001  起不來不影響開場
        _log_vault(vault, e)


def line_compact(vault, source):
    """本題：只在摺疊後印。"""
    return COMPACT_LINE if source == "compact" else None


def status_lines(vault, source, session_id=None):
    """固定順序；每一行各自 try：出錯那行回 None、寫 hook-errors.log，其他行照印（I-046）。kb 行不包，它出錯走整段出錯。"""
    out = [line_kb(vault)]
    for fn in (line_version, line_moved, line_changes, lambda v: line_ingest_hint(v, session_id), line_missing_sources, line_profile, line_agenda, line_inbox,
               line_backup,
               line_health,
               lambda v: line_compact(v, source)):
        try:
            line = fn(vault)
        except Exception as e:  # noqa: BLE001
            _log_vault(vault, e)
            line = None
        if line is not None:
            out.append(line)
    start_background_lint(vault)
    return out


def read_core():
    from kb._lib import paths

    return (paths.plugin_root() / "rules" / "core.md").read_text(encoding="utf-8")


# 加框（測試後修正裁定 15）：偏好只管回答與成品，跟核心規則或守門衝突時照核心規則
PREFERENCES_HEAD = "客戶偏好（只管怎麼回答、怎麼做東西給客戶；跟上面的核心規則或守門衝突時，照核心規則）："


def preferences_block(vault):
    """note 改規則第 4 點（D-137）：設定檔第六節有條目就回「客戶偏好：」加一條一行，接在 core.md 之後；沒有回 None。
    profile.json 讀不到這段不印、寫 log，其他照印（I-046）。只讀。"""
    try:
        from kb._lib import profile

        prefs = (profile.load(vault) or {}).get("preferences") or []
    except Exception as e:  # noqa: BLE001
        _log_vault(vault, e)
        return None
    if not prefs:
        return None
    return "\n".join([PREFERENCES_HEAD] + [f"- {p.get('text', '')}" for p in prefs])


def emit(context):
    """印一行 SessionStart JSON；write／flush 出錯（pipe 斷掉）吞掉。
    沒送出的字還在緩衝，結束時 Python 會再 flush 一次、失敗就 exit 120，所以把 fd 1 指到 devnull。"""
    out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
    try:
        sys.stdout.write(json.dumps(out, ensure_ascii=True) + "\n")
        sys.stdout.flush()
    except BaseException:  # noqa: BLE001
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except BaseException:  # noqa: BLE001
            pass


def main():
    payload = {}
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        if not isinstance(payload, dict):
            payload = {}
        from kb import guard

        vault = guard.find_vault(payload.get("cwd") or os.getcwd())
    except BaseException as e:  # noqa: BLE001  stdin 壞掉、找知識庫出錯：只記 log，不輸出
        _log(e, payload)
        return
    if vault is None:
        return
    try:
        context = "\n".join(status_lines(vault, payload.get("source"), payload.get("session_id"))) + "\n\n" + read_core()
        block = preferences_block(vault)
        if block:
            context += "\n" + block
    except BaseException as e:  # noqa: BLE001  找到知識庫之後出錯：記 log，再明講一行
        _log(e, payload)
        emit(ERROR_LINE.format(type(e).__name__))
        return
    emit(context)


def _log_vault(vault, e):
    try:
        from kb._lib import ledger

        ledger.log_error(vault, f"{type(e).__name__}: {str(e)[:200]}", source="session")
    except Exception:  # noqa: BLE001
        pass


def _log(e, payload):
    try:
        from kb import guard
        from kb._lib import ledger

        payload = payload if isinstance(payload, dict) else {}
        vault = guard.find_vault(payload.get("cwd") or os.getcwd())
        ledger.log_error(vault, f"{type(e).__name__}: {str(e)[:200]}", source="session")
    except BaseException:  # noqa: BLE001
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
