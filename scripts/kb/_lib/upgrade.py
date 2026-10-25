"""升級（升級打包 要做的事 1，D-215～D-219、D-217）：kb upgrade 的本體，跟開場的背景查新版共用。

流程（D-215）：客戶說好 → kb upgrade：大升級先拍快照（backup.snapshot "upgrade"）、寫 upgrade-history.json 的 pending、
找桌面版內建的 Claude Code 跑 `plugin update wiki-with-willy@<市集> --scope <範圍>`（plugin 前面不加任何旗標，B-409 spike：--debug 會開出一個對話），
驗 installed_plugins.json 真的換了版（GitHub 快取還給舊清單時沒換到，說「新版剛出來」、pending 清掉、快照留著）→ 請她開新對話。
新對話開場（hooks/session.py）認出換了版 → kb upgrade --finish：補骨架、對帳、狀態檔遷移、卡檔頭、記歷史，幾秒內做完（D-054）。
小修（前兩位相同）：開場每天背景查一次（--background），有她可以拿的小修就在同一個子行程換版，不拍快照、不轉格式（D-217）。
退回（清單比現在舊）：先 --check 看升級前的快照與 restore check 的結果，她說好才 --downgrade：restore apply 還原快照、再換版。
名單（D-216）：rollout.json 的那一版 for 是 "all"、或含這個知識庫的 vault_id 才算她可以拿；其他當沒有新版。
抓不到清單、名單一律安靜（D-219）：只記進 env.json 的 update_check.error，不印、不出錯。
外部的東西都經 _get（網路）、_call（claude.exe）、_popen（背景子行程）、_which，測試換替身，不連網、不跑真的 Claude。
鎖：跟備份、還原同一把（.system/revert.lock，backup.acquire）；背景整理還有動靜時擋（backup.batch_running）。
只呼叫 backup、restore、vault 的函式，不改它們。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from kb._lib import backup, config, env, migrate, paths, skeleton
from kb._lib import vault as vault_lib
from kb._lib.io import FileLock, read_json, write_json_atomic

HISTORY_REL = ".system/upgrade-history.json"
HISTORY_SCHEMA = 1
PLUGIN_NAME = "wiki-with-willy"
FETCH_MAX_BYTES = 1_000_000
NOTE_MAX_CHARS = 200  # 遠端那句話的硬上限（--check、--json、env.json 都用這份）；開場另截 update_note_max
KINDS = ("patch", "minor", "major", "downgrade")

UP_TO_DATE = "目前是最新版（{version}）"
NOT_YET = "新版剛出來，幾分鐘後再說一次"
NO_CLAUDE = "這台找不到 Claude 的更新程式，請服務人員幫忙"
UPDATE_FAILED = "更新沒成功：{why}"
HISTORY_BROKEN = "更新沒成功：升級紀錄（.system/upgrade-history.json）讀不懂，請服務人員看一下；什麼都沒動"
NO_SNAPSHOT = "升級前的快照已經不在，不能退回；請服務人員幫忙"
OFFLINE_ASK = "現在連不上更新的地方，晚點再問。"
OFFLINE_RETRY = "現在連不上更新的地方，晚點再說一次"
SUCCESS = "好了，開一個新對話就是新版（{version}）。"
DOWNGRADED = "已回到 {version} 的知識庫，也換回 {version}；開一個新對話就好。"
USE_DOWNGRADE = "這一版（{version}）撤回了；要退回先用 kb upgrade --check 看會怎樣，她說好再 kb upgrade --downgrade"
DOWNGRADE_HALF = "知識庫已經還原回去了，只有外掛還沒換回舊版；請服務人員幫忙，不要再退回一次"  # 還原成功、換版才失敗（B-438）
LATEST_LINE = "目前是最新版（{version}）。"
NEWER_LINE = "現在 {plugin}；最新 {latest}（{note}），說「升級」就幫你升。"
NEWER_LINE_NO_NOTE = "現在 {plugin}；最新 {latest}，說「升級」就幫你升。"
VAULT_BEHIND_LINE = "知識庫還停在 {vault}，新對話開場會自動補轉格式。"
WITHDRAWN_LINE = "這一版 {plugin} 撤回了，清單指回 {latest}；要退回會先還原升級前的快照（{snapshot}），再換回舊版。"
WITHDRAWN_NO_SNAPSHOT = "這一版 {plugin} 撤回了，清單指回 {latest}；但升級前的快照已經不在，不能退回，請服務人員幫忙。"

FINISH_LINE = "已換到 {version}：先跑 kb upgrade --finish 再做別的。"
NEW_VERSION_LINE = "有新版 {version}：{note}；說「升級」我帶你做。"
NEW_VERSION_LINE_NO_NOTE = "有新版 {version}；說「升級」我帶你做。"
WITHDRAWN_OPENING = "這一版 {version} 撤回了；用起來有問題的話說「退回舊版」。"
PENDING_OPENING = "上次升級到 {version} 還沒換好；說「升級」我再試一次。"


class UpdateError(Exception):
    """換版這一步做不到：訊息是給人看的那句（一字不差）。"""


class Offline(Exception):
    """抓不到清單或名單（連不上、逾時、內容看不懂）：訊息是一句原因，只記不印（D-219）。"""


class NotConfigured(Offline):
    """清單網址還是空字串（第一次發行才填，D-171）：背景不查。"""


# ---------- 呼叫層（測試換掉） ----------

def _get(url, timeout):
    """抓一個 https 網址回文字（UTF-8）；連不上、逾時、不是 https 都丟 OSError／ValueError。"""
    if not str(url).startswith("https://"):
        raise ValueError("只收 https 網址")
    req = urllib.request.Request(url, headers={"User-Agent": "wiki-with-willy"})
    opener = urllib.request.build_opener(_HttpsOnlyRedirect())
    with opener.open(req, timeout=timeout) as r:
        return r.read(FETCH_MAX_BYTES).decode("utf-8")


class _HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    """轉址也只跟著 https（清單被轉到 http 的地方就當連不上）。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not str(newurl).startswith("https://"):
            raise urllib.error.URLError("只跟著 https 的轉址")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _call(argv, timeout, env=None, cwd=None):
    """跑外部程式，回 (結束碼, 輸出文字)；stdout 與 stderr 合併、一律用 UTF-8 解。找不到程式丟 FileNotFoundError，
    逾時殺整棵行程樹再丟 subprocess.TimeoutExpired（照 _lib/office 的做法）。不在對話的目錄跑。"""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, cwd=cwd or tempfile.gettempdir(),
                         creationflags=flags, stdin=subprocess.DEVNULL)
    try:
        out, _err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(p)
        p.communicate()
        raise
    return p.returncode, out.decode("utf-8", errors="replace")


def _kill_tree(p):
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        p.kill()


def _popen(argv, **kw):
    """開背景子行程（不等它）；測試換掉它記下參數。"""
    return subprocess.Popen(argv, **kw)


def _which(name):
    """PATH 上找程式，跳過目前目錄與相對路徑的 PATH 項。Python 3.12 以前 shutil.which 在 Windows 一定先找目前目錄
    （傳 path= 也一樣），而 kb upgrade 的目前目錄是知識庫：放一個 claude.cmd 就會被當更新程式跑。所以自己走 PATH。"""
    here = os.path.normcase(os.path.abspath(os.getcwd()))
    exts = [""] if os.path.splitext(name)[1] or os.name != "nt" else \
        [e for e in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(os.pathsep) if e]
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if not d or not os.path.isabs(d) or os.path.normcase(os.path.abspath(d)) == here:
            continue
        for ext in exts:
            p = os.path.join(d, name + ext)
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
    return None


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def plugin_version():
    return str((paths.read_manifest() or {}).get("version", "0"))


def _plugin_root():
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return Path(root) if root else paths.plugin_root()


def installed_plugins_path():
    return Path(os.path.expanduser("~")) / ".claude" / "plugins" / "installed_plugins.json"


def _changelog():
    """這一版自己的 CHANGELOG.md（zip 裡有，D-213）；讀不到回空字串。"""
    try:
        return (paths.plugin_root() / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        return ""


# ---------- 版本 ----------

_VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", re.ASCII)


def parse_version(text):
    """"0.20.1" → (0, 20, 1)；不是剛好三段 ASCII 整數（沒有前導零、結尾不帶換行）回 None。
    整串比對：$ 會放過結尾換行（會帶進開場那行），\\d 會放過全形與阿拉伯數字，前導零跟安裝紀錄的版本字串永遠對不上。"""
    m = _VERSION.fullmatch(text) if isinstance(text, str) else None
    return tuple(int(x) for x in m.groups()) if m else None


def kind(current, latest):
    """patch｜minor｜major｜downgrade｜none（D-217）：前兩位相同、第三位較大是小修；前兩位較大是大升級（第一位變是 major，
    0.x 時第二位當大版本所以是 minor）；清單比現在舊是退回；同版或看不懂回 none。"""
    cur, new = parse_version(current), parse_version(latest)
    if cur is None or new is None or cur == new:
        return "none"
    if new < cur:
        return "downgrade"
    if new[:2] == cur[:2]:
        return "patch"
    return "major" if new[0] > cur[0] else "minor"


def note_of(changelog_text, version):
    """CHANGELOG 裡 `## <版本> — …` 那一段的「給客戶的一句話」；沒有那一版、沒有那行回 None。"""
    head = re.search(rf"^## {re.escape(str(version))} — .*$", changelog_text or "", re.MULTILINE)
    if not head:
        return None
    rest = changelog_text[head.end():]
    nxt = re.search(r"^## ", rest, re.MULTILINE)
    section = rest[:nxt.start()] if nxt else rest
    m = re.search(r"^- \*\*給客戶的一句話\*\*：(.+)$", section, re.MULTILINE)
    return m.group(1).strip() if m else None


# ---------- 清單與名單 ----------

def allowed(roster, version, vault_id):
    """名單那一版的 for：「all」、或清單含這個 vault_id 才算她可以拿；其他（none、沒那一版、看不懂）都不算。"""
    versions = roster.get("versions") if isinstance(roster, dict) else None
    entry = versions.get(version) if isinstance(versions, dict) else None
    who = entry.get("for") if isinstance(entry, dict) else None
    if who == "all":
        return True
    return bool(vault_id) and isinstance(who, list) and vault_id in [w for w in who if isinstance(w, str)]


def _json_get(url, seconds):
    try:
        return json.loads(_get(url, seconds))
    except (OSError, ValueError) as e:  # TimeoutError 與 URLError 都是 OSError
        raise Offline(f"{url} 讀不到（{type(e).__name__}）") from None


def clean_note(text):
    """會進開場與對話的那句話：壓成一行、去掉控制與方向字元（isprintable 不收 Cc、Cf），截 NOTE_MAX_CHARS；不是字串或空的回 None。
    抓下來時與開場印之前都過一次（env.json 是本機檔，也可能被改過或從別台帶來）。"""
    if not isinstance(text, str):
        return None
    words = "".join(c if c.isprintable() else " " for c in text).split()
    return " ".join(words)[:NOTE_MAX_CHARS].strip() or None


def fetch(vault):
    """抓清單與名單。回 {"latest", "allowed", "note"}；網址空丟 NotConfigured，抓不到或看不懂丟 Offline。"""
    manifest_url = config.get(vault, "update_manifest_url")
    rollout_url = config.get(vault, "update_rollout_url")
    if not manifest_url:
        raise NotConfigured("清單網址還沒設定")
    seconds = config.get(vault, "update_fetch_seconds")
    data = _json_get(manifest_url, seconds)
    plugins = data.get("plugins") if isinstance(data, dict) else None
    entry = next((p for p in plugins if isinstance(p, dict) and p.get("name") == PLUGIN_NAME), None) \
        if isinstance(plugins, list) else None
    latest = entry.get("version") if entry else None
    if parse_version(latest) is None:
        raise Offline("清單裡找不到 wiki-with-willy 的版本")
    roster = _json_get(rollout_url, seconds) if rollout_url else {}
    try:
        vid = vault_lib.vault_id(vault)
    except ValueError:
        vid = None
    note = None
    versions = roster.get("versions") if isinstance(roster, dict) else None
    row = versions.get(latest) if isinstance(versions, dict) else None
    if isinstance(row, dict):
        note = clean_note(row.get("note"))
    return {"latest": latest, "allowed": allowed(roster, latest, vid), "note": note}


# ---------- 歷史（.system/upgrade-history.json） ----------

def _history_path(vault):
    return Path(vault) / HISTORY_REL


def load_history(vault):
    """沒檔回 None；壞檔、形狀不對丟 ValueError（不覆寫，跟 vault.json 同一套）。"""
    try:
        data = read_json(_history_path(vault))
    except ValueError as e:
        raise ValueError(f"{HISTORY_REL}（JSON 壞了：{e}）") from e
    if data is None:
        return None
    if (not isinstance(data, dict) or not isinstance(data.get("current"), str)
            or not isinstance(data.get("history", []), list)):
        raise ValueError(f"{HISTORY_REL}（格式不對）")
    data.setdefault("pending", None)
    data.setdefault("history", [])
    return data


def write_history(vault, data):
    p = _history_path(vault)
    p.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(p):
        write_json_atomic(p, dict(data, schema_version=HISTORY_SCHEMA))


def ensure_history(vault):
    """沒有就照現在跑的版本記成目前版本（第一次跑這版的既有知識庫，I-113）；有就讀。壞檔不覆寫。"""
    got = load_history(vault)
    if got is not None:
        return got
    p = _history_path(vault)
    p.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(p):
        got = load_history(vault)
        if got is not None:
            return got
        got = {"schema_version": HISTORY_SCHEMA, "current": plugin_version(), "pending": None, "history": []}
        write_json_atomic(p, got)
    return got


def _snapshot_for_downgrade(vault, hist):
    """最近一筆升到現在這版的紀錄記的升級前快照（檔還在才算）；沒有回 None。"""
    plugin = plugin_version()
    for row in reversed((hist or {}).get("history") or []):
        if isinstance(row, dict) and row.get("to") == plugin and row.get("kind") != "downgrade":
            name = row.get("snapshot")
            if name and (Path(vault) / backup.SNAPSHOT_REL / name).is_file():
                return name
            return None
    return None


# ---------- 找內建 Claude Code、市集名與範圍 ----------

def find_claude():
    """桌面版內建的 claude.exe：%LOCALAPPDATA%\\Claude-Data\\claude_*\\claude-code\\<版本>\\<…>\\claude.exe，版本夾多個取版本號最大的
    （數字比大小，不是字串）；固定深度的萬用字元，不遞迴（spike：掃整個 Claude-Data 會很慢）；找不到用 PATH 上的 claude；都沒有回 None。"""
    base = os.environ.get("LOCALAPPDATA")
    found = []
    if base:
        found = list((Path(base) / "Claude-Data").glob("claude_*/claude-code/*/*/claude.exe"))

    def order(p):
        nums = re.findall(r"\d+", p.parent.parent.name)
        return (tuple(int(n) for n in nums), str(p))
    if found:
        return str(max(found, key=order))
    return _which("claude")


def _read_installed():
    try:
        data = json.loads(installed_plugins_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    plugins = data.get("plugins") if isinstance(data, dict) else None
    return plugins if isinstance(plugins, dict) else None


def _same_path(a, b):
    def norm(p):
        return os.path.normcase(os.path.realpath(str(p)))
    return norm(a) == norm(b)


def plugin_identity(vault=None):
    """從 CLAUDE_PLUGIN_ROOT（…/cache/<市集>/wiki-with-willy/<版本>）取市集名，範圍從 installed_plugins.json 裡
    installPath 等於目前 plugin 根的那筆取（客戶是 user；確認時是 local，local 還帶 projectPath）。不寫死。
    同一個版本夾可能有好幾筆（local 裝在好幾個夾，桌面版確認 B-3）：先挑 projectPath 是這個知識庫的，再挑 user 的，最後才是第一筆。"""
    root = Path(_plugin_root())
    if root.parent.name != PLUGIN_NAME or root.parent.parent.parent.name != "cache":
        raise UpdateError(UPDATE_FAILED.format(why="這個外掛不是從市集裝的"))
    market = root.parent.parent.name
    plugins = _read_installed()
    if plugins is None:
        raise UpdateError(UPDATE_FAILED.format(why="讀不到外掛的安裝紀錄"))
    if not re.fullmatch(r"[A-Za-z0-9._-]+", market, re.ASCII):
        raise UpdateError(UPDATE_FAILED.format(why="市集名稱看不懂"))
    found = []
    for rec in plugins.get(f"{PLUGIN_NAME}@{market}") or []:
        if isinstance(rec, dict) and rec.get("installPath") and _same_path(rec["installPath"], root):
            scope = rec.get("scope") or "user"
            if scope not in ("user", "project", "local"):
                raise UpdateError(UPDATE_FAILED.format(why="安裝紀錄的範圍看不懂"))
            found.append({"market": market, "scope": scope, "project": rec.get("projectPath")})
    if not found:
        raise UpdateError(UPDATE_FAILED.format(why="安裝紀錄裡找不到這個外掛"))
    if vault is not None:
        for f in found:
            if f["project"] and _same_path(f["project"], vault):
                return f
    return next((f for f in found if f["scope"] == "user"), found[0])


def installed_version(identity):
    """重讀 installed_plugins.json 同一筆（市集、範圍、projectPath 相同）的 version；沒有回 None。"""
    plugins = _read_installed() or {}
    for rec in plugins.get(f"{PLUGIN_NAME}@{identity['market']}") or []:
        if (isinstance(rec, dict) and rec.get("scope") == identity["scope"]
                and rec.get("projectPath") == identity.get("project")):
            return rec.get("version")
    return None


def _first_line(text, limit=120):
    for ln in str(text).splitlines():
        if ln.strip():
            return ln.strip()[:limit]
    return "沒有說明"


def run_update(identity, seconds=60):
    """叫內建 Claude Code 跑 plugin update。指令列：[exe, "plugin", "update", "wiki-with-willy@<市集>", "--scope", "<範圍>"]，
    plugin 前面不加任何旗標。失敗丟 UpdateError（一句話）。"""
    exe = find_claude()
    if not exe:
        raise UpdateError(NO_CLAUDE)
    argv = [exe, "plugin", "update", f"{PLUGIN_NAME}@{identity['market']}", "--scope", identity["scope"]]
    project = identity.get("project")
    cwd = project if identity["scope"] in ("local", "project") and project and os.path.isdir(project) else None
    try:
        code, out = _call(argv, seconds, cwd=cwd)
    except FileNotFoundError:
        raise UpdateError(NO_CLAUDE) from None
    except subprocess.TimeoutExpired:
        raise UpdateError(UPDATE_FAILED.format(why=f"等太久了（超過 {seconds} 秒）")) from None
    except OSError as e:
        raise UpdateError(UPDATE_FAILED.format(why=type(e).__name__)) from None
    if code != 0:
        raise UpdateError(UPDATE_FAILED.format(why=_first_line(out)))


# ---------- 查（--check） ----------

def check(vault):
    """當場查一次（不用背景結果、什麼都不寫）。回 spec 的 --check --json 那個物件；退回時多 restore（restore check 的結果）。"""
    plugin = plugin_version()
    try:
        hist = load_history(vault)
    except ValueError:
        hist = None
    out = {"plugin": plugin, "vault": hist["current"] if hist else plugin, "latest": None, "kind": None, "allowed": False,
           "note": None, "snapshot_for_downgrade": None, "error": None}
    try:
        got = fetch(vault)
    except Offline as e:
        out["error"] = str(e)
        return out
    out.update(latest=got["latest"], allowed=got["allowed"], note=got["note"], kind=kind(plugin, got["latest"]))
    if out["kind"] == "downgrade" and out["allowed"]:
        name = _snapshot_for_downgrade(vault, hist)
        out["snapshot_for_downgrade"] = name
        if name:
            from kb._lib import restore
            try:
                out["restore"] = restore.check(vault, name)
            except (backup.Refused, OSError, ValueError):
                pass
    return out


def check_lines(res):
    """--check 的人讀輸出；--json 才有的欄位（restore）AI 自己讀。"""
    if res["error"]:
        return [OFFLINE_ASK]
    lines = []
    if res["kind"] == "downgrade" and res["allowed"]:
        if res["snapshot_for_downgrade"]:
            lines.append(WITHDRAWN_LINE.format(plugin=res["plugin"], latest=res["latest"], snapshot=res["snapshot_for_downgrade"]))
            if res.get("restore"):
                from kb._lib import restore
                lines += restore.lines(res["restore"])
        else:
            lines.append(WITHDRAWN_NO_SNAPSHOT.format(plugin=res["plugin"], latest=res["latest"]))
    elif not res["allowed"] or res["kind"] in (None, "none", "downgrade"):
        lines.append(LATEST_LINE.format(version=res["plugin"]))
    elif res["note"]:
        lines.append(NEWER_LINE.format(plugin=res["plugin"], latest=res["latest"], note=res["note"]))
    else:
        lines.append(NEWER_LINE_NO_NOTE.format(plugin=res["plugin"], latest=res["latest"]))
    if res["vault"] != res["plugin"]:
        lines.append(VAULT_BEHIND_LINE.format(vault=res["vault"]))
    return lines


# ---------- 升級與退回 ----------

def _guard_ready(vault, what):
    """動手之前擋掉：背景整理還有動靜、找不到更新程式、不知道這個外掛怎麼裝的。回 identity。"""
    if backup.batch_running(vault):
        raise backup.Refused(backup.BATCH_RUNNING.format(what=what))
    if not find_claude():
        raise backup.Refused(NO_CLAUDE)
    try:
        return plugin_identity(vault)
    except UpdateError as e:
        raise backup.Refused(str(e)) from None


def _check_for_action(vault):
    """kb upgrade／--downgrade 開頭那次 --check；連不上、不在名單、沒新版各丟那句。回 check 的結果。"""
    info = check(vault)
    if info["error"]:
        raise backup.Refused(OFFLINE_RETRY)
    return info


def _clear_pending(vault):
    try:
        hist = load_history(vault)
        if hist is not None and hist.get("pending") is not None:
            hist["pending"] = None
            write_history(vault, hist)
    except (ValueError, OSError):
        pass


def _room_for_snapshot(vault):
    """拍升級前快照之前比空間（跟備份、還原同一套算法：未壓縮總大小對磁碟剩餘）；不夠丟 backup.Refused，什麼都還沒動。"""
    need = backup.collect(vault)[2]
    free = backup._free_bytes(vault)
    if need > free:
        raise backup.Refused(UPDATE_FAILED.format(why=backup.NO_SPACE.format(need=backup._mb_up(need), free=free // (1024 * 1024))))


def upgrade(vault):
    """kb upgrade：大升級先拍快照、記 pending、換版；小修直接換。回 {"sentence","kind","to","snapshot"}；不行丟 backup.Refused（那一句）。"""
    info = _check_for_action(vault)
    if info["kind"] == "downgrade" and info["allowed"]:
        raise backup.Refused(USE_DOWNGRADE.format(version=info["plugin"]))
    if not info["allowed"] or info["kind"] in (None, "none", "downgrade"):
        raise backup.Refused(UP_TO_DATE.format(version=info["plugin"]))
    k, latest = info["kind"], info["latest"]
    identity = _guard_ready(vault, "升級")
    seconds = config.get(vault, "update_run_seconds")
    snapshot = None
    with backup.acquire(vault):
        if k in ("minor", "major"):
            try:
                hist = ensure_history(vault)
            except (OSError, ValueError):
                raise backup.Refused(HISTORY_BROKEN) from None
            prev = hist.get("pending") or {}
            kept = Path(vault) / backup.SNAPSHOT_REL / str(prev.get("snapshot") or "")
            if prev.get("to") == latest and prev.get("snapshot") and kept.is_file():
                snapshot = kept  # 上次升級到同一版、快照還在：不再拍一份（確認 B-3）
            else:
                _room_for_snapshot(vault)
        try:
            if k in ("minor", "major"):
                snapshot = snapshot or backup.snapshot(vault, "upgrade")
                hist["pending"] = {"to": latest, "snapshot": snapshot.name, "started": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")}
                write_history(vault, hist)
        except backup.Refused:
            raise
        except (OSError, ValueError) as e:
            why = (backup.oserror_sentence(e) if isinstance(e, OSError) else None) or type(e).__name__
            raise backup.Refused(UPDATE_FAILED.format(why=f"快照沒拍成：{why}")) from None
        try:
            run_update(identity, seconds)
            got = installed_version(identity)
        except UpdateError as e:
            _clear_pending(vault)
            raise backup.Refused(str(e)) from None
        if got != latest:  # GitHub 快取還給舊清單：版本沒換到；快照留著
            _clear_pending(vault)
            raise backup.Refused(NOT_YET)
    return {"sentence": SUCCESS.format(version=latest), "kind": k, "to": latest,
            "snapshot": snapshot.name if snapshot else None}


def downgrade(vault, conversation=False):
    """kb upgrade --downgrade：restore apply 還原升級前的快照 → 換版（降版）。回 {"sentence","to","snapshot"}。
    快照不在、背景整理在跑、鎖被占、不是退回的狀態各丟那一句，什麼都沒動。"""
    info = _check_for_action(vault)
    if not (info["kind"] == "downgrade" and info["allowed"]):
        raise backup.Refused(UP_TO_DATE.format(version=info["plugin"]))
    name = info["snapshot_for_downgrade"]
    if not name:
        raise backup.Refused(NO_SNAPSHOT)
    identity = _guard_ready(vault, "升級")
    latest = info["latest"]
    from kb._lib import restore
    restore.apply(vault, name, conversation)  # 自己搶鎖；鎖被占丟 Refused（BUSY）
    try:
        run_update(identity, config.get(vault, "update_run_seconds"))
        got = installed_version(identity)
    except UpdateError as e:
        raise backup.Refused(f"{e}\n{DOWNGRADE_HALF}") from None
    if got != latest:
        raise backup.Refused(f"{NOT_YET}\n{DOWNGRADE_HALF}")
    hist = ensure_history(vault)
    hist["current"], hist["pending"] = latest, None
    hist["history"].append({"from": info["plugin"], "to": latest, "date": _today(), "kind": "downgrade",
                            "snapshot": name, "by": "customer"})
    write_history(vault, hist)
    return {"sentence": DOWNGRADED.format(version=latest), "to": latest, "snapshot": name}


# ---------- 新對話開場的轉格式（--finish） ----------

def _run_init(vault):
    """補骨架（kb init 同一支，只補缺的）。"""
    import argparse
    import contextlib
    import io
    from kb import init
    with contextlib.redirect_stdout(io.StringIO()):
        init.run(argparse.Namespace(path=str(vault), check=False, json=False))


def _pending_snapshot(vault, hist, plugin):
    """對得上這次換版（pending.to 等於現在版本）而且快照檔還在的 pending；回快照名，否則 None。"""
    pending = hist.get("pending")
    if isinstance(pending, dict) and pending.get("to") == plugin and pending.get("snapshot"):
        if (Path(vault) / backup.SNAPSHOT_REL / pending["snapshot"]).is_file():
            return pending["snapshot"]
    return None


def finish(vault, turn_id):
    """kb upgrade --finish。回 {"already": True, "to": X}（一樣版本、第一次記錄）或
    {"already": False, "from","to","kind","snapshot","migrated","migrate_skipped","cards_migrated",
    "skeleton_created","skeleton_replaced","skeleton_ask","note","by"}。鎖被占丟 backup.Refused，什麼都沒動。"""
    plugin = plugin_version()
    hist = load_history(vault)
    if hist is None:
        ensure_history(vault)
        return {"already": True, "to": plugin}
    cur = hist["current"]
    if cur == plugin:
        return {"already": True, "to": plugin}
    k = kind(cur, plugin)
    k = "major" if k == "none" else k  # 紀錄的版本看不懂：照大升級（先拍快照）處理
    with backup.acquire(vault):
        result = {"already": False, "from": cur, "to": plugin, "kind": k, "snapshot": None, "migrated": [],
                  "migrate_skipped": [], "cards_migrated": 0, "skeleton_created": [], "skeleton_replaced": [],
                  "skeleton_ask": []}
        snapshot = _pending_snapshot(vault, hist, plugin)
        by = "customer" if snapshot else "outside"
        if k in ("minor", "major") and snapshot is None:
            _room_for_snapshot(vault)
            try:
                snapshot = backup.snapshot(vault, "upgrade").name
            except (OSError, ValueError) as e:
                why = (backup.oserror_sentence(e) if isinstance(e, OSError) else None) or type(e).__name__
                raise backup.Refused(UPDATE_FAILED.format(why=f"快照沒拍成：{why}")) from None
        if k == "patch":
            snapshot = None
            chk = env.update_check(vault) or {}
            if chk.get("auto_patched") == plugin:
                by = "auto"
        if k != "downgrade":
            mig = migrate.apply(vault, turn_id)  # 先於 kb init：init 自己也會升設定檔 schema，但不備進回合（驗收 8 要退得回）
            had = {rel for rel in skeleton.files() if (Path(vault) / rel).exists()}
            _run_init(vault)
            sk = skeleton.reconcile(vault, turn_id, from_version=cur)
            created = sorted({rel for rel in skeleton.files() if rel not in had and (Path(vault) / rel).exists()}
                             | set(sk["created"]))  # 缺的骨架檔多半是 init 補的，reconcile 看到時已經在了
            result.update(migrated=mig["migrated"], migrate_skipped=mig["skipped"], cards_migrated=mig["cards"],
                          skeleton_created=created, skeleton_replaced=sk["replaced"], skeleton_ask=sk["ask"])
        result["snapshot"] = snapshot if k != "patch" else None
        hist["current"], hist["pending"] = plugin, None
        hist["history"].append({"from": cur, "to": plugin, "date": _today(), "kind": k,
                                "snapshot": result["snapshot"], "by": by})
        write_history(vault, hist)
    result["by"] = by
    result["note"] = note_of(_changelog(), plugin)
    return result


# ---------- 背景查新版與小修（開場叫的子行程） ----------

BLANK_CHECK = {"latest": None, "kind": None, "allowed": False, "note": None, "auto_patched": None, "error": None}


def _save_check(vault, **fields):
    env.set_update_check(vault, dict(BLANK_CHECK, date=_today(), **fields))


def _save_error(vault, e):
    """連不上：只記錯誤與日期，上一次查到的結果留著（開場只用上一次的）。"""
    prev = env.update_check(vault) or {}
    keep = {k: prev.get(k) for k in ("latest", "kind", "allowed", "note")}
    _save_check(vault, error=str(e) or type(e).__name__, **{k: v for k, v in keep.items() if v is not None})


def background(vault):
    """kb upgrade --background：查清單與名單、結果寫 env.json 的 update_check；有她可以拿的小修就接著換版（記 auto_patched）。
    清單網址空就不查（什麼都不寫）；任何出錯只記進 error、不丟（D-219）。"""
    try:
        got = fetch(vault)
    except NotConfigured:
        return
    except Offline as e:
        _save_error(vault, e)
        return
    except Exception as e:  # noqa: BLE001  背景程式不能出聲
        _save_error(vault, e)
        return
    try:
        plugin = plugin_version()
        k = kind(plugin, got["latest"])
        fields = {"latest": got["latest"], "kind": k, "allowed": got["allowed"], "note": got["note"]}
        if k == "patch" and got["allowed"]:
            fields.update(_auto_patch(vault, got["latest"]))
        _save_check(vault, **fields)
    except Exception as e:  # noqa: BLE001
        _save_error(vault, e)


def _auto_patch(vault, latest):
    """換小修：背景整理有動靜或鎖被占就這次不換（明天再說）；成功回 {"auto_patched": latest}，失敗回 {"error": 句子}。"""
    if backup.batch_running(vault):
        return {}
    try:
        with backup.acquire(vault):
            identity = plugin_identity(vault)
            run_update(identity, config.get(vault, "update_run_seconds"))
            if installed_version(identity) != latest:
                return {"error": NOT_YET}
    except backup.Refused:
        return {}
    except UpdateError as e:
        return {"error": str(e)}
    return {"auto_patched": latest}


# ---------- 開場（hooks/session.py 叫） ----------

def _spawn_background(vault):
    """背景開一個 kb upgrade --background（不等它、不拖慢開場）；Windows 脫離開場的行程與視窗。"""
    argv = [sys.executable, str(paths.plugin_root() / "scripts" / "kb.py"), "upgrade", "--background"]
    kw = {"cwd": str(vault), "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
          "close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = (getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
                               | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    else:
        kw["start_new_session"] = True
    _popen(argv, **kw)


def _maybe_spawn(vault, chk):
    """清單網址有填、日期不是今天才開；先記今天（另一個對話開場不重複叫），上一次的結果留著。出錯吞掉。"""
    if not config.get(vault, "update_manifest_url") or (chk or {}).get("date") == _today():
        return
    try:
        env.set_update_check(vault, dict(chk or BLANK_CHECK, date=_today()))
        _spawn_background(vault)
    except Exception:  # noqa: BLE001  起不來不影響開場
        pass


def opening(vault):
    """開場判斷，不連網、不等背景。回 {"finish": 要不要 --finish, "line": 開場那句或 None}。
    沒有 upgrade-history.json 就記成現在版本、不印換版那行（第一次跑這版的既有知識庫）；壞檔丟 ValueError（那行不印、寫 log）。
    優先序：換了版要 --finish > 升級記了卻還沒換成 > 有她可以拿的大升級 > 清單被指回舊版（撤回）。"""
    plugin = plugin_version()
    hist = ensure_history(vault)
    finish_needed = hist["current"] != plugin
    chk = env.update_check(vault)
    line = None
    pending_to = (hist.get("pending") or {}).get("to")
    if finish_needed:
        line = FINISH_LINE.format(version=plugin)
    elif pending_to and pending_to != plugin:
        line = PENDING_OPENING.format(version=pending_to)
    elif chk and chk.get("allowed") and isinstance(chk.get("latest"), str):
        k = kind(plugin, chk["latest"])
        if k in ("minor", "major"):
            note = clean_note(chk.get("note"))
            note = note[:config.get(vault, "update_note_max")].strip().rstrip("。.！!") or None if note else None
            line = (NEW_VERSION_LINE.format(version=chk["latest"], note=note) if note
                    else NEW_VERSION_LINE_NO_NOTE.format(version=chk["latest"]))
        elif k == "downgrade":
            line = WITHDRAWN_OPENING.format(version=plugin)
    _maybe_spawn(vault, chk)
    return {"finish": finish_needed, "line": line}
