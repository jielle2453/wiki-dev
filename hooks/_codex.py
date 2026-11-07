"""Codex 轉接（codex 分支，spec 2026-11-07-Codex版）：把 Codex 的 hook payload 轉成守門與寫後登記認得的格式，scripts/kb/ 不改。

認法：PreToolUse／PostToolUse／UserPromptSubmit 的 payload 有 turn_id（Codex 的 schema 必填，Claude Code 沒有）。
normalize：apply_patch 拆成逐檔的 Write（新增）／Edit（更新、刪除、搬出、搬入）；Windows 上的 Bash 改叫 PowerShell
（Codex 在 Windows 跑的是 PowerShell）；view_image 改叫 Read；拆不出檔名的 patch 回 None（守門在知識庫裡 deny）。
密碼動作（D-212）：Codex 的 PreToolUse 不支援 ask，改成 deny 並在 session 檔記 codex_consent_pending；客戶下一句是同意
（is_agreement，只看 UserPromptSubmit 的 prompt，AI 寫的字到不了這裡），turn.py 記 codex_consent，同一個指令再跑一次才放行，用一次就清掉。
"""
import hashlib
import os
import re
import sys

sys.dont_write_bytecode = True
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

WINDOWS = os.name == "nt"
PATCH_RE = re.compile(r"^\*\*\* (Add File|Update File|Delete File|Move to): (.+?)\s*$", re.M)
PATCH_TOOL = "apply_patch"
CONSENT_REASON = ("這個密碼動作要客戶同意：先用一句話跟客戶說要做什麼、問她可不可以；"
                  "她回同意之後，再跑一次一模一樣的指令。")
PATCH_REASON = "看不出這次改的是哪些檔，這次沒放行：改用一個檔一個 patch 再試一次。"
PENDING, GRANTED = "codex_consent_pending", "codex_consent"

AGREE = ("同意", "好", "可以", "ok", "okay", "yes", "是", "對", "確定", "允許", "沒問題", "行", "嗯", "去做", "做吧")
REFUSE = ("不", "別", "沒有", "等", "先", "再", "no", "取消", "停", "算了", "嗎", "?", "？", "但")
AGREE_MAX = 12  # 去掉標點後超過這個字數就不算一句單純的同意（交代別的事時不當同意）


def is_codex(payload):
    return isinstance(payload, dict) and "turn_id" in payload


def _command_text(command):
    """Codex 的指令可能是陣列（["powershell.exe", "-Command", "…"]）：取 -Command／-c／/c 後面那段，沒有就用空白接起來。"""
    if isinstance(command, list):
        parts = [str(x) for x in command]
        for i, p in enumerate(parts[:-1]):
            if p.lower() in ("-command", "-c", "/c"):
                return parts[i + 1]
        return " ".join(parts)
    return command if isinstance(command, str) else ""


def patch_text(tool_input):
    """apply_patch 的整段 patch：Codex 放 command（第三方也看過 patch、input、陣列），都收。"""
    for key in ("command", "patch", "input"):
        v = tool_input.get(key)
        if isinstance(v, list):
            v = next((x for x in reversed(v) if isinstance(x, str) and "*** Begin Patch" in x), None)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def patch_targets(text, cwd):
    """[(工具名, 絕對路徑)]：Add File→Write，Update／Delete File→Edit，Move to→Write（搬入的新位置）。拆不出回 []。"""
    out = []
    for kind, path in PATCH_RE.findall(text or ""):
        path = path.strip().strip('"')
        if not os.path.isabs(path):
            path = os.path.join(cwd, path)
        out.append(("Write" if kind in ("Add File", "Move to") else "Edit", os.path.normpath(path)))
    return out


def normalize(payload):
    """Codex payload → [現有格式的 payload]；apply_patch 拆不出檔回 None。其他工具原樣一份。"""
    tool = payload.get("tool_name") or ""
    ti = payload.get("tool_input") or {}
    ti = ti if isinstance(ti, dict) else {}
    cwd = payload.get("cwd") or os.getcwd()
    if tool == PATCH_TOOL:
        targets = patch_targets(patch_text(ti), cwd)
        if not targets:
            return None
        return [dict(payload, tool_name=name, tool_input={"file_path": path}) for name, path in targets]
    if tool == "Bash":
        name = "PowerShell" if WINDOWS else "Bash"
        return [dict(payload, tool_name=name, tool_input=dict(ti, command=_command_text(ti.get("command"))))]
    if tool == "view_image":
        return [dict(payload, tool_name="Read", tool_input={"file_path": str(ti.get("path") or ti.get("file_path") or "")})]
    return [payload]


def combine(results):
    """逐檔的 (decision, reason, updated) 併成一個：有 deny 就 deny；只有一份照它；全部 allow 才 allow；其他不表態。"""
    for r in results:
        if r[0] == "deny":
            return "deny", r[1], None
    if len(results) == 1:
        return results[0]
    if results and all(r[0] == "allow" for r in results):
        return "allow", results[0][1], None
    return None, "", None


def is_agreement(prompt):
    """客戶這一句是不是單純的同意：去掉空白標點後不超過 AGREE_MAX 字、有同意的字、沒有拒絕或保留的字。"""
    t = re.sub(r"[\s，。！!、,.~～…」「]", "", str(prompt or "")).casefold()
    t_check = t.replace("沒問題", "")
    return 0 < len(t) <= AGREE_MAX and any(a in t for a in AGREE) and not any(r in t_check for r in REFUSE)


def _hash(command):
    return hashlib.sha256(_command_text(command).strip().encode("utf-8")).hexdigest()[:16]


def take_consent(vault, session_id, command):
    """這個對話目前的回合有沒有客戶對這個指令的同意：有就用掉回 True；沒有就記成待同意回 False。"""
    from kb._lib import turn
    from kb._lib.io import FileLock

    if not session_id:
        return False
    h = _hash(command)
    with FileLock(turn._session_file(vault, session_id)):
        data = turn._read_turn(turn._session_file(vault, session_id))
        if data is None:
            return False
        if data.get(GRANTED) == h and not data.get("done"):
            turn._set(vault, session_id, **{GRANTED: None, PENDING: None})
            return True
        turn._set(vault, session_id, **{PENDING: h})
        return False


def grant(vault, session_id, previous, prompt):
    """UserPromptSubmit（turn.py 開完新回合後）：上一句有待同意的指令、這一句客戶說同意 → 新回合記 codex_consent。回有沒有記。"""
    from kb._lib import turn

    pending = (previous or {}).get(PENDING)
    if not (session_id and pending and is_agreement(prompt)):
        return False
    return turn._set(vault, session_id, **{GRANTED: pending}) is not None
