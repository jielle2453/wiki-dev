"""發行程式（升級打包 要做的事 9，D-213、D-216、D-217、D-218）：從 tag 打 zip、傳到公開 repo、更新清單與名單。開發用，不進 zip。

  python tools/release.py build <tag> [--prepare] [--repo <開發 repo>] [--out <夾>]   （各子命令都收 --repo）
  python tools/release.py publish <tag> --public <公開 repo 的本機 clone> (--for <vault_id>… | --all | --none) [--wait 15]
  python tools/release.py rollout <版本> --public <clone> (--for <vault_id>… | --all | --none)

build：從 tag 用 git archive 取檔，照 D-213 要放的清單（含 agents/、obsidian/）打 zip 到 dist/（.gitignore 有），位元組可重現；最後檢查：
zip 裡只有清單上的、plugin.json 與 hooks/hooks.json 引用的路徑都在、版本號等於 tag、obsidian/ 三個檔都在且 manifest.json 的版號等於 tag、CHANGELOG 最新一段有「給客戶的一句話」、
config/skeleton_history.json 有這一版且跟 tag 裡的骨架一致；小修（D-217，前兩位跟上一個 tag 相同）不准動骨架檔、各 schema 版本常數、
_lib/migrate.py；每個 .py 照 Python 3.10 的語法 parse 得過；打好的 zip 解開跑它自己的 kb selftest --json（開發機的 Python，D-230）。
問題一次全列；zip 先寫暫存名，全部過了才改成正式名（有問題不留、也不動先前打好的同名 zip）。印 sha256。--prepare 在打 tag 之前的發行 commit 裡先把這一版的骨架指紋追加進 config/skeleton_history.json。
publish：build → gh release create 傳 zip → 更新公開 repo 的 marketplace.json（版本、網址、sha256）並推 → 每 30 秒從外面抓清單，
抓到新版（最多等 --wait 分鐘）才改 rollout.json 並推（D-218：名單不能比清單先更新）；超過停下來、名單沒改，清單與 zip 已經推了，之後用 rollout 補。
中途失敗（例如推清單時斷線）直接重跑 publish：release 已經有了就補傳同一個 zip，不重建。
rollout：只改名單（rollout.json 那一版的 for）並推；撤回就是 --none（D-217）。公開 repo 的 clone 要先是最新的，而且不能有沒 commit 的改動。
失敗印原因、exit 1。外部的東西都經 _run（git、gh）、_fetch（抓清單）、_selftest（跑 zip 裡的自我檢查）、_sleep、_clock，測試換替身。
只用標準函式庫，不 import plugin 的程式（自我檢查開子行程跑）。
"""
import argparse
import ast
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

ALLOW_DIRS = (".claude-plugin", ".codex-plugin", ".agents", "hooks", "scripts", "config", "rules", "skills", "templates", "skeleton", "agents", "obsidian")
ALLOW_FILES = ("README.md", "CHANGELOG.md", "LICENSE", "安裝-Codex.md")
CODEX_MANIFEST = ".codex-plugin/plugin.json"  # 有這個檔，publish 才另推公開 repo 的 codex 分支（#56）
CODEX_BRANCH = "codex"
PUBLIC_BRANCH = "main"  # 公開 repo 放清單與名單的分支
CODEX_README = "安裝-Codex.md"  # codex 分支的 README.md 用它
HASH_IN_PATH = ("路徑裡有 #：{}。gh 會把 # 後面當成標籤、Codex 會把它當分支名，請換到沒有 # 的資料夾再跑。")
PLUGIN_NAME = "wiki-with-willy"
POLL_SECONDS = 30
FETCH_SECONDS = 15
GITKEEP = ".gitkeep"
ZIP_STAMP = (1980, 1, 1, 0, 0, 0)  # 固定時間：同一個 tag 打兩次的 sha256 一樣
OBSIDIAN_FILES = ("manifest.json", "main.js", "styles.css")  # Obsidian 首頁外掛（#22，D-258）
MANIFEST_KEYS = ("commands", "agents", "skills", "hooks", "outputStyles", "mcpServers", "lspServers")
SCHEMA_LINE = re.compile(r"^\s*(\w*(?:SCHEMA|TEMPLATE_VERSION)\w*)\s*=\s*(.+?)\s*$", re.MULTILINE)
SCHEMA_LITERAL = re.compile(r"""["']schema_version["']\s*:\s*(\d+)""")  # 寫在字面裡的格式版本（env.py、turn.py…）
CHANGELOG_HEAD = re.compile(r"^## (\d+\.\d+\.\d+) — .*$", re.MULTILINE)
NOTE_LINE = re.compile(r"^- \*\*給客戶的一句話\*\*：(.+)$", re.MULTILINE)
VAULT_ID = re.compile(r"kb-[0-9a-f]{8}", re.ASCII)  # 整串比對（fullmatch）
_NUM = r"(?:0|[1-9]\d*)"
VERSION = re.compile(rf"({_NUM})\.({_NUM})\.({_NUM})", re.ASCII)  # 跟客戶端 _lib/upgrade.parse_version 同一套，整串比對
TAG = re.compile(rf"v?({_NUM}\.{_NUM}\.{_NUM})", re.ASCII)
PY_FLOOR = (3, 10)  # 客戶電腦上最舊會遇到的 Python（D-230）
SELFTEST_SECONDS = 180


class ReleaseError(Exception):
    """做不下去：訊息是原因（可能多行）。"""


# ---------- 外部（測試換掉） ----------

def _run(argv, cwd=None, **kw):
    """跑 git／gh，回 stdout 文字；結束碼不是 0 丟 ReleaseError（帶 stderr）。"""
    try:
        r = subprocess.run(argv, cwd=str(cwd) if cwd else None, capture_output=True, text=True, encoding="utf-8", **kw)
    except FileNotFoundError:
        raise ReleaseError(f"找不到 {argv[0]}") from None
    if r.returncode != 0:
        raise ReleaseError(f"{' '.join(str(a) for a in argv[:3])} 失敗：{(r.stderr or r.stdout).strip()}")
    return r.stdout


def _git_bytes(repo, *args):
    try:
        r = subprocess.run(["git", *args], cwd=str(repo), capture_output=True)
    except FileNotFoundError:
        raise ReleaseError("找不到 git") from None
    if r.returncode != 0:
        raise ReleaseError(f"git {args[0]} 失敗：{r.stderr.decode('utf-8', errors='replace').strip()}")
    return r.stdout


def _fetch(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "wiki-with-willy-release"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
        return r.read().decode("utf-8")


def _selftest(zip_path):
    """把 zip 解到暫存夾、跑它的 kb selftest --json（開發機的 Python）；回那個物件，跑不起來或輸出看不懂也回 ok false（不丟）。"""
    tmp = Path(tempfile.mkdtemp(prefix="wiki-with-willy-release-"))
    try:
        with zipfile.ZipFile(str(zip_path)) as z:
            z.extractall(str(tmp / "plugin"))
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        env.pop("CLAUDE_PLUGIN_ROOT", None)
        try:
            r = subprocess.run([sys.executable, str(tmp / "plugin" / "scripts" / "kb.py"), "selftest", "--json"],
                               cwd=str(tmp), env=env, capture_output=True, timeout=SELFTEST_SECONDS, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return {"ok": False, "step": "selftest", "why": f"超過 {SELFTEST_SECONDS} 秒"}
        except OSError as e:
            return {"ok": False, "step": "selftest", "why": f"起不來（{type(e).__name__}）"}
        for ln in reversed(r.stdout.decode("utf-8", errors="replace").splitlines()):
            try:
                data = json.loads(ln)
            except ValueError:
                continue
            if isinstance(data, dict):
                return data
        return {"ok": False, "step": "selftest", "why": f"輸出看不懂（結束碼 {r.returncode}）"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_sleep = time.sleep
_clock = time.monotonic


# ---------- 版本 ----------

def parse_version(text):
    m = VERSION.fullmatch(text) if isinstance(text, str) else None
    return tuple(int(x) for x in m.groups()) if m else None


def tag_version(tag):
    m = TAG.fullmatch(tag) if isinstance(tag, str) else None
    if not m:
        raise ReleaseError(f"tag 要像 v0.21.0：{tag!r}")
    return m.group(1)


def kind(current, latest):
    """跟客戶端 _lib/upgrade.kind 同一套規則（D-217）。"""
    cur, new = parse_version(current), parse_version(latest)
    if cur is None or new is None or cur == new:
        return "none"
    if new < cur:
        return "downgrade"
    if new[:2] == cur[:2]:
        return "patch"
    return "major" if new[0] > cur[0] else "minor"


def previous_tag(repo, version):
    """比 version 小的 X.Y.Z tag 裡最大的（回 tag 名）；沒有回 None。不是 X.Y.Z 的 tag 不看。"""
    best = None
    for name in _run(["git", "tag", "--list"], cwd=repo).split():
        m = TAG.fullmatch(name)
        v = parse_version(m.group(1)) if m else None
        if v and v < parse_version(version) and (best is None or v > best[0]):
            best = (v, name)
    return best[1] if best else None


# ---------- 取檔與檢查 ----------

def allowed(rel):
    top = rel.split("/", 1)[0]
    if "/" in rel:
        return top in ALLOW_DIRS
    return rel in ALLOW_FILES


def _archive(repo, tag):
    """tag 裡所有檔 {相對路徑: 位元組}（git archive，跳過資料夾）。"""
    _run(["git", "rev-parse", "--verify", f"{tag}^{{commit}}"], cwd=repo)
    data = _git_bytes(repo, "archive", "--format=tar", tag)
    out = {}
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        for m in tar.getmembers():
            if m.isfile():
                out[m.name] = tar.extractfile(m).read()
    return out


def collect(repo, tag):
    """tag 裡照要放清單挑出來的檔。"""
    return {rel: data for rel, data in _archive(repo, tag).items() if allowed(rel)}


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def _exists(files, rel):
    rel = rel.strip("/")
    return rel in files or any(name.startswith(rel + "/") for name in files)


def _json_of(files, rel, out):
    try:
        return json.loads(files[rel].decode("utf-8"))
    except KeyError:
        out.append(f"zip 裡沒有 {rel}")
    except ValueError:
        out.append(f"{rel} 不是合法的 JSON")
    return None


def skeleton_hashes(files):
    return {rel[len("skeleton/"):]: hashlib.sha256(data).hexdigest() for rel, data in sorted(files.items())
            if rel.startswith("skeleton/") and rel.rsplit("/", 1)[-1] != GITKEEP}


def _schema_constants(files):
    out = {}
    for rel, data in files.items():
        if rel.startswith("scripts/") and rel.endswith(".py"):
            text = data.decode("utf-8", errors="replace")
            for name, value in SCHEMA_LINE.findall(text):
                out[(rel, name)] = value
            literal = _schema_literals(text)
            if literal:
                out[(rel, '字面的 "schema_version"')] = ",".join(literal)
    return out


def _schema_literals(text):
    """程式裡真的寫出來的 schema_version 數字（B-448）：dict 字面的鍵 {"schema_version": N} 與呼叫參數 schema_version=N；
    docstring、註解、一般字串裡寫到的不算。讀不懂的檔退回舊的正規式（寧可多擋）。"""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return SCHEMA_LITERAL.findall(text)
    found = []
    for node in ast.walk(tree):
        pairs = []
        if isinstance(node, ast.Dict):
            pairs = [(k.value, v) for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)]
        elif isinstance(node, ast.Call):
            pairs = [(kw.arg, kw.value) for kw in node.keywords]
        for key, value in pairs:
            if key == "schema_version" and isinstance(value, ast.Constant) and type(value.value) is int:
                found.append(str(value.value))
    return found


def _patch_problems(files, previous):
    """小修不准動：骨架檔、各 schema 版本常數、_lib/migrate.py（D-217）。config/skeleton_history.json 不算（每版追加）。"""
    out = []
    sk_now = {r: d for r, d in files.items() if r.startswith("skeleton/")}
    sk_old = {r: d for r, d in previous.items() if r.startswith("skeleton/")}
    for rel in sorted(set(sk_now) | set(sk_old)):
        if sk_now.get(rel) != sk_old.get(rel):
            out.append(f"小修不能改骨架檔：{rel} 變了")
    now, old = _schema_constants(files), _schema_constants(previous)
    for key in sorted(set(now) | set(old)):
        if now.get(key) != old.get(key):
            out.append(f"小修不能改格式版本：{key[0]} 的 {key[1]} 變了（{old.get(key)} → {now.get(key)}）")
    mig = "scripts/kb/_lib/migrate.py"
    if files.get(mig) != previous.get(mig):
        out.append(f"小修不能改遷移表：{mig} 變了")
    return out


def problems(files, version, previous=None):
    """最後檢查：回問題清單（空的就是過了）。files 是要放進 zip 的檔，previous 是上一個 tag 的檔（只有小修才給，查小修規則）。"""
    out = [f"不在要放清單上：{rel}" for rel in sorted(files) if not allowed(rel)]
    manifest = _json_of(files, ".claude-plugin/plugin.json", out)
    if isinstance(manifest, dict):
        if manifest.get("version") != version:
            out.append(f".claude-plugin/plugin.json 的版本是 {manifest.get('version')}，tag 是 {version}")
        for key in MANIFEST_KEYS:
            value = manifest.get(key)
            for ref in ([value] if isinstance(value, str) else value if isinstance(value, list) else []):
                if isinstance(ref, str) and not _exists(files, ref[2:] if ref.startswith("./") else ref):
                    out.append(f"plugin.json 的 {key} 引用的路徑不在 zip 裡：{ref}")
    out += _obsidian_problems(files, version)
    out += _codex_problems(files, version)
    hooks = _json_of(files, "hooks/hooks.json", out)
    for text in _strings(hooks) if hooks is not None else []:
        for ref in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\s\"']+)", text):
            if not _exists(files, ref):
                out.append(f"hooks/hooks.json 引用的路徑不在 zip 裡：{ref}")
    out += _changelog_problems(files, version)
    out += _history_problems(files, version)
    if previous is not None:
        out += _patch_problems(files, previous)
    return out


def _codex_problems(files, version):
    """Codex 版（#56）：有 .codex-plugin/plugin.json 才查：版號等於 tag（跟 Claude 版同一版）、hooks 指到的檔在、
    那份 hooks 檔引用的 ${PLUGIN_ROOT}/… 都在。"""
    if CODEX_MANIFEST not in files:
        return []
    out = []
    manifest = _json_of(files, CODEX_MANIFEST, out)
    if not isinstance(manifest, dict):
        return out
    if manifest.get("version") != version:
        out.append(f"{CODEX_MANIFEST} 的版本是 {manifest.get('version')}，tag 是 {version}（要跟 .claude-plugin 同一版）")
    _json_of(files, ".agents/plugins/marketplace.json", out)  # Codex 從 codex 分支裝要這份市集
    ref = manifest.get("hooks")
    if not (isinstance(ref, str) and ref.startswith("./") and ".." not in ref.split("/")):
        out.append(f"{CODEX_MANIFEST} 的 hooks 要是 ./ 開頭、在外掛裡的路徑（現在是 {ref!r}）；沒有的話 Codex 會去讀 Claude 的 hooks/hooks.json")
    else:
        rel = ref[2:]
        hooks = _json_of(files, rel, out)
        for text in _strings(hooks) if hooks is not None else []:
            for sub in re.findall(r"\$\{PLUGIN_ROOT\}/([^\s\"']+)", text):
                if not _exists(files, sub):
                    out.append(f"{rel} 引用的路徑不在 zip 裡：{sub}")
    return out


def _obsidian_problems(files, version):
    """obsidian/ 的三個檔都在，manifest.json 是合法 JSON 而且版號等於 tag（外掛跟 plugin 同一版，D-258）。"""
    out = [f"obsidian/{name} 不在 zip 裡" for name in OBSIDIAN_FILES if f"obsidian/{name}" not in files]
    if "obsidian/manifest.json" in files:
        manifest = _json_of(files, "obsidian/manifest.json", out)
        if isinstance(manifest, dict) and manifest.get("version") != version:
            out.append(f"obsidian/manifest.json 的版本是 {manifest.get('version')}，tag 是 {version}")
    return out


def _changelog_problems(files, version):
    text = files.get("CHANGELOG.md", b"").decode("utf-8", errors="replace")
    head = CHANGELOG_HEAD.search(text)
    if not head:
        return ["CHANGELOG.md 找不到 `## X.Y.Z — ` 段落"]
    out = []
    if head.group(1) != version:
        out.append(f"CHANGELOG.md 最新一段是 {head.group(1)}，不是 {version}")
    rest = text[head.end():]
    nxt = re.search(r"^## ", rest, re.MULTILINE)
    if not NOTE_LINE.search(rest[:nxt.start()] if nxt else rest):
        out.append(f"CHANGELOG.md 的 {head.group(1)} 那一段沒有「給客戶的一句話」（沒寫不准發行）")
    return out


def _history_problems(files, version):
    out = []
    history = _json_of(files, "config/skeleton_history.json", out)
    if not isinstance(history, dict):
        return out
    if history.get(version) != skeleton_hashes(files):
        out.append(f"config/skeleton_history.json 沒有 {version} 的骨架指紋，或跟 zip 裡的骨架對不上；"
                   "先跑 build <tag> --prepare、commit 之後再打 tag")
    return out


def syntax_problems(files):
    """每個 .py 照 Python 3.10 的語法 parse（D-230：她的 Python 可能比開發機舊）；回問題清單。"""
    out = []
    for rel in sorted(files):
        if rel.endswith(".py"):
            try:
                ast.parse(files[rel], filename=rel, feature_version=PY_FLOOR)
            except SyntaxError as e:
                out.append(f"{rel} 第 {e.lineno} 行：Python 3.10 不認得這種寫法")
            except ValueError:
                out.append(f"{rel}：原始碼裡有 Python 讀不了的字元")
    return out


def selftest_problems(zip_path):
    got = _selftest(zip_path)
    if isinstance(got, dict) and got.get("ok") is True:
        return []
    got = got if isinstance(got, dict) else {}
    where = f"{got['file']} 第 {got['line']} 行：" if got.get("file") and got.get("line") else ""
    return [f"自我檢查沒過：{got.get('step') or 'selftest'}：{where}{got.get('why') or '沒有說明'}"]


def check_zip(path, version):
    """對一個現成的 zip 做最後檢查（不含小修規則，那要跟上一個 tag 比）。"""
    files = {}
    with zipfile.ZipFile(str(path)) as z:
        for name in z.namelist():
            if not name.endswith("/"):
                files[name] = z.read(name)
    return problems(files, version)


# ---------- build ----------

def _write_zip(files, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(dest), "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(files):
            info = zipfile.ZipInfo(rel, ZIP_STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, files[rel])


def build(repo, tag, out_dir=None):
    """回 {"zip", "sha256", "version", "files"}；檢查沒過丟 ReleaseError（問題一次全列）。"""
    repo = Path(repo).resolve()  # zip 路徑要是絕對的：publish 在公開 clone 裡跑 gh（確認時 --repo . 找不到 zip）
    version = tag_version(tag)
    archive = _archive(repo, tag)
    files = {rel: data for rel, data in archive.items() if allowed(rel)}
    skipped = sorted({rel.split("/", 1)[0] for rel in archive if not allowed(rel)})
    prev_tag = previous_tag(repo, version)
    previous = None
    if prev_tag and kind(tag_version(prev_tag), version) == "patch":
        previous = collect(repo, prev_tag)
    found = problems(files, version, previous) + syntax_problems(files)
    dest = Path(out_dir or repo / "dist").resolve() / f"{PLUGIN_NAME}-{version}.zip"
    tmp = dest.with_name(f".{dest.name}.tmp")  # 先寫暫存名，全部過了才改名（裁定 16：重打失敗不動先前打好的那份）
    _write_zip(files, tmp)
    try:
        found += selftest_problems(tmp)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    if found:
        tmp.unlink(missing_ok=True)
        raise ReleaseError("不能發行：\n" + "\n".join(f"- {p}" for p in found))
    os.replace(str(tmp), str(dest))
    return {"zip": dest, "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(), "version": version, "files": len(files),
            "skipped": skipped}


def prepare(repo, tag):
    """把這一版的骨架指紋追加（或換掉）進 config/skeleton_history.json（工作區，不是 tag）；回檔案路徑。"""
    repo = Path(repo)
    version = tag_version(tag)
    manifest = json.loads((repo / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    if manifest.get("version") != version:
        raise ReleaseError(f"plugin.json 的版本是 {manifest.get('version')}，tag 是 {version}；先改版號再 prepare")
    base = repo / "skeleton"
    files = {p.relative_to(repo).as_posix(): p.read_bytes() for p in base.rglob("*") if p.is_file()}
    path = repo / "config" / "skeleton_history.json"
    try:
        history = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        history = {}
    history = history if isinstance(history, dict) else {}
    history[version] = skeleton_hashes(files)
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


# ---------- publish、rollout ----------

def _git(public, *args):
    return _run(["git", *args], cwd=public)


def _require_clean(public):
    """公開 repo 的 clone 有沒 commit 的改動（已暫存、或改了追蹤的檔）就停：不然那些改動會跟清單或名單一起 commit 推出去。
    沒加進 git 的檔不算（git add 只加清單與名單）。本機還沒推的 commit 不算（上一次推失敗留下的，這次一起推）。"""
    branch = _git(public, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch != PUBLIC_BRANCH:  # 清單與名單只推 main（#56 review 5：上一次被中斷停在 codex 分支時，不把清單推進 codex）
        raise ReleaseError(f"公開 repo 的 clone 現在在 {branch}，不是 {PUBLIC_BRANCH}；先 git checkout {PUBLIC_BRANCH} 再跑")
    dirty = _git(public, "status", "--porcelain", "--untracked-files=no").strip()
    if dirty:
        raise ReleaseError(f"公開 repo 的 clone 有沒 commit 的改動，先清乾淨再跑：\n{dirty}")


def _commit_and_push(public, message, *paths):
    """有改動才 commit（只 commit 這幾個檔）；push 每次都跑：上一次 commit 了卻推失敗的，這次一起推上去。"""
    _git(public, "add", *paths)
    if _git(public, "status", "--porcelain", "--", *paths).strip():
        _git(public, "commit", "-q", "-m", message, "--", *paths)
    _git(public, "push", "-q", "origin", "HEAD")


def _read_json(path, default):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return data if isinstance(data, dict) else default


def _write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _release_base(public):
    """公開 repo 的網址（給 Releases 下載網址用）：從 origin 取，只認 github 的 ssh（git@github.com:o/r）與 https（https://github.com/o/r）。
    其他寫法一律拒絕、不原樣用：帶帳密的 https://<token>@github.com/… 會把 token 寫進公開的 marketplace.json。錯誤句不印網址。"""
    url = _git(public, "remote", "get-url", "origin").strip()
    m = re.fullmatch(r"(?:git@github\.com:|https://github\.com/)([A-Za-z0-9._-]+/[A-Za-z0-9._-]+?)(?:\.git)?/?", url)
    if not m:
        raise ReleaseError("公開 repo 的 clone 的 origin 不是 git@github.com:<擁有者>/<repo> 或 https://github.com/<擁有者>/<repo>"
                           "（網址裡不能帶帳號或 token）；改好 origin 再跑")
    return f"https://github.com/{m.group(1)}"


def changelog_note(repo, version):
    """工作區 CHANGELOG 裡那一版的一句話（rollout 找不到那一版的 tag 時用）。"""
    return note_in((Path(repo) / "CHANGELOG.md").read_text(encoding="utf-8"), version)


def note_in(text, version):
    for head in CHANGELOG_HEAD.finditer(text):
        if head.group(1) == version:
            rest = text[head.end():]
            nxt = re.search(r"^## ", rest, re.MULTILINE)
            m = NOTE_LINE.search(rest[:nxt.start()] if nxt else rest)
            return m.group(1).strip() if m else None
    return None


def _manifest_url(files):
    """tag 裡（要進 zip 的）config/defaults.json 的清單與名單網址都要填好、是 https；回清單網址。
    讀 tag 不讀工作區：客戶拿到的是 zip 裡的設定，工作區改了沒 commit 不算數。"""
    try:
        data = json.loads(files["config/defaults.json"].decode("utf-8"))
    except (KeyError, ValueError):
        data = None
    data = data if isinstance(data, dict) else {}
    for key in ("update_manifest_url", "update_rollout_url"):
        url = data.get(key)
        if not (isinstance(url, str) and url.startswith("https://")):
            raise ReleaseError(f"tag 裡 config/defaults.json 的 {key} 還是空的（或不是 https）；第一次發行要先定公開 repo 的清單與名單網址、"
                               "填進去 commit，再打 tag（D-171）")
    return data["update_manifest_url"]


def _check_who(who):
    if who in ("all", "none"):
        return who
    if isinstance(who, list) and who and all(isinstance(w, str) and VAULT_ID.fullmatch(w) for w in who):
        return list(who)
    raise ReleaseError("名單要是 all、none，或一串 kb-xxxxxxxx 知識庫編號")


def _update_marketplace(public, version, url, sha):
    path = Path(public) / "marketplace.json"
    data = _read_json(path, None) or {"name": PLUGIN_NAME, "owner": {"name": PLUGIN_NAME}, "plugins": []}
    plugins = data.setdefault("plugins", [])
    entry = next((p for p in plugins if isinstance(p, dict) and p.get("name") == PLUGIN_NAME), None)
    if entry is None:
        entry = {"name": PLUGIN_NAME}
        plugins.append(entry)
    entry["version"] = version
    entry["source"] = {"source": "archive", "url": url, "sha256": sha}
    _write_json(path, data)
    return path


def _wait_for_list(manifest_url, version, wait_minutes):
    start = _clock()
    while True:
        try:
            plugins = json.loads(_fetch(manifest_url, FETCH_SECONDS)).get("plugins") or []
            seen = next((p.get("version") for p in plugins if p.get("name") == PLUGIN_NAME), None)
        except (OSError, ValueError, AttributeError):
            seen = None
        if seen == version:
            return
        if _clock() - start >= wait_minutes * 60:
            raise ReleaseError(f"等了 {wait_minutes} 分鐘，外面抓到的清單還是 {seen or '抓不到'}，不是 {version}；名單沒改。"
                               f"清單與 zip 已經推了，等一下確認清單換了再跑 rollout {version}")
        _sleep(POLL_SECONDS)


def set_rollout(public, version, who, note):
    path = Path(public) / "rollout.json"
    data = _read_json(path, None) or {"schema_version": 1, "versions": {}}
    versions = data.setdefault("versions", {})
    versions[version] = {"for": who, "note": note}
    data.setdefault("schema_version", 1)
    _write_json(path, data)
    return path


def _release_exists(public, tag):
    """gh 那邊已經有這個 tag 的 release（上一次 publish 建好之後才失敗）；查不到（含沒登入、連不上）當沒有，
    接著 gh release create 會把真正的原因講出來。"""
    try:
        _run(["gh", "release", "view", tag, "--json", "tagName"], cwd=public)
    except ReleaseError:
        return False
    return True


def _push_codex(public, version, files):
    """Codex 版（#56 決策 5）：把 zip 的同一批檔推到公開 repo 的 codex 分支（Codex 的市集不認 zip，只認 git 的內容）。
    一般 commit 接在遠端那個後面、不 force push；README.md 換成安裝-Codex.md、補 .gitattributes。內容跟遠端一樣就不 commit。
    本機的 codex 分支由這裡管：遠端有就一律從遠端那個接（上一次 commit 了卻推失敗的丟掉、這次重做同一份；本機跟遠端分岔也不卡，
    #56 review 7）。做完（或失敗）切回 main，這裡寫出來、main 沒有的檔刪掉（review 6：不留下擋住下一次切換的檔）。
    回 codex 分支的 commit。"""
    remote = _git(public, "remote", "get-url", "--push", "origin").strip()  # 推的那個（平常跟抓的同一個）
    has_remote = bool(_git(public, "ls-remote", "--heads", remote, CODEX_BRANCH).strip())
    has_local = bool(_git(public, "branch", "--list", CODEX_BRANCH).strip())
    out = dict(files)
    if CODEX_README in out:
        out["README.md"] = out[CODEX_README]
    out[".gitattributes"] = b"* text=auto eol=lf\n"
    try:
        if has_remote:
            _git(public, "fetch", "-q", remote, CODEX_BRANCH)
            _git(public, "checkout", "-q", "-f", "-B", CODEX_BRANCH, "FETCH_HEAD")
        elif has_local:
            _git(public, "checkout", "-q", "-f", CODEX_BRANCH)
        else:
            _git(public, "checkout", "-q", "-f", "--orphan", CODEX_BRANCH)
        tracked = [x for x in _git(public, "ls-files", "-z").split(chr(0)) if x]
        if tracked:
            _git(public, "rm", "-q", "-r", "--cached", "--", ".")
            for rel in tracked:
                Path(public, rel).unlink(missing_ok=True)
        for rel, data in out.items():
            dest = Path(public) / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        # 路徑從 stdin 給（review 8：檔多、中文路徑長時不撞 Windows 指令列上限）；只加這批，clone 裡別的沒追蹤的檔不帶進去
        _run(["git", "add", "-f", "--pathspec-from-file=-", "--pathspec-file-nul"], cwd=public, input=chr(0).join(sorted(out)))
        if _git(public, "status", "--porcelain", "--untracked-files=no").strip():
            _git(public, "commit", "-q", "-m", f"codex: {version}")
        _git(public, "push", "-q", "origin", f"HEAD:refs/heads/{CODEX_BRANCH}")
        return _git(public, "rev-parse", "HEAD").strip()
    finally:
        _git(public, "checkout", "-q", "-f", PUBLIC_BRANCH)
        keep = {x for x in _git(public, "ls-files", "-z").split(chr(0)) if x}
        for rel in out:
            if rel not in keep:
                Path(public, rel).unlink(missing_ok=True)


def publish(repo, tag, public, who, wait=15):
    """build → gh release → 清單 → 等外面抓得到 → 名單 → Codex 版推 codex 分支（有 .codex-plugin 才推，#56）。回 build 的結果
    （多 "codex"：codex 分支的 commit，沒推是 None）。
    中途失敗可以直接重跑：release 已經有了就把同一個 zip 補傳上去（--clobber，zip 位元組可重現），上次沒推的清單 commit 這次一起推，
    codex 分支內容一樣就只補推。"""
    who = _check_who(who)
    _require_clean(public)
    files = collect(Path(repo), tag)
    manifest_url = _manifest_url(files)
    base = _release_base(public)
    got = build(repo, tag)
    version, zip_path = got["version"], Path(got["zip"])
    note = note_in(files.get("CHANGELOG.md", b"").decode("utf-8", errors="replace"), version) or ""
    if _release_exists(public, tag):
        _run(["gh", "release", "upload", tag, str(zip_path), "--clobber"], cwd=public)
    else:
        _run(["gh", "release", "create", tag, str(zip_path), "--title", tag, "--notes", note or tag], cwd=public)
    url = f"{base}/releases/download/{tag}/{zip_path.name}"
    market = _update_marketplace(public, version, url, got["sha256"])
    _commit_and_push(public, f"marketplace: {version}", market.name)
    _wait_for_list(manifest_url, version, wait)
    roster = set_rollout(public, version, who, note)
    _commit_and_push(public, f"rollout: {version}", roster.name)
    got["codex"] = _push_codex(public, version, files) if CODEX_MANIFEST in files else None
    return got


def rollout(repo, version, public, who):
    """只改名單那一版的 for 並推；那一版已有的 note 保留，沒有就從 CHANGELOG 取。"""
    who = _check_who(who)
    _require_clean(public)
    row = (_read_json(Path(public) / "rollout.json", {}).get("versions") or {}).get(version)
    note = row.get("note") if isinstance(row, dict) and row.get("note") else None
    if note is None:
        try:
            note = note_in(collect(Path(repo), f"v{version}").get("CHANGELOG.md", b"").decode("utf-8", errors="replace"), version)
        except ReleaseError:  # 沒有那一版的 tag：看工作區
            try:
                note = changelog_note(repo, version)
            except OSError:
                note = None
    if not note:
        raise ReleaseError(f"名單裡沒有 {version}，CHANGELOG 也找不到它的「給客戶的一句話」")
    path = set_rollout(public, version, who, note)
    _commit_and_push(public, f"rollout: {version}", path.name)


# ---------- 指令列 ----------

def build_parser():
    parser = argparse.ArgumentParser(prog="release.py", description="wiki-with-willy 發行程式（開發用，不進 zip）。")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]), help="開發 repo（預設是這支程式所在的 repo）")
    subs = parser.add_subparsers(dest="command", required=True)

    def who_group(p):
        group = p.add_mutually_exclusive_group(required=True)
        group.add_argument("--for", dest="who", nargs="+", metavar="VAULT_ID", help="只給這幾個知識庫編號")
        group.add_argument("--all", dest="who", action="store_const", const="all", help="全部")
        group.add_argument("--none", dest="who", action="store_const", const="none", help="沒有人（停止擴散）")
    b = subs.add_parser("build", help="從 tag 打 zip 到 dist/", parents=[common])
    b.add_argument("tag")
    b.add_argument("--prepare", action="store_true", help="只把這一版的骨架指紋追加進 config/skeleton_history.json")
    b.add_argument("--out", help="zip 放哪（預設 <repo>/dist）")
    pub = subs.add_parser("publish", help="zip 傳 Releases、更新清單、等生效再改名單", parents=[common])
    pub.add_argument("tag")
    pub.add_argument("--public", required=True, help="公開 repo 的本機 clone")
    pub.add_argument("--wait", type=int, default=15, help="最多等幾分鐘清單生效（預設 15）")
    who_group(pub)
    r = subs.add_parser("rollout", help="只改名單", parents=[common])
    r.add_argument("version")
    r.add_argument("--public", required=True, help="公開 repo 的本機 clone")
    who_group(r)
    return parser


def hash_paths(args):
    """--repo、--public、zip 輸出夾裡有 # 的（#55）：gh 把 path#label 的 # 後面當標籤、Codex 把它當分支名，發到一半才壞。"""
    paths = [args.repo, getattr(args, "public", None)]
    if args.command == "build" or args.command == "publish":
        paths.append(getattr(args, "out", None) or str(Path(args.repo) / "dist"))
    return [str(Path(p).resolve()) for p in paths if p and "#" in str(Path(p).resolve())]


def main(argv=None):
    args = build_parser().parse_args(argv)
    bad = hash_paths(args) if args.command in ("build", "publish") else []
    if bad:
        print("失敗：" + HASH_IN_PATH.format(bad[0]))
        return 2
    try:
        if args.command == "build":
            if args.prepare:
                print(f"已把 {tag_version(args.tag)} 的骨架指紋寫進 {prepare(args.repo, args.tag)}")
                return 0
            got = build(args.repo, args.tag, args.out)
            print(f"版本 {got['version']}，{got['files']} 個檔")
            if got["skipped"]:
                print("沒放進 zip（不在要放清單上）：" + "、".join(got["skipped"]) + "；有新的執行用資料夾要先加進 ALLOW_DIRS")
            print(f"zip：{got['zip']}")
            print(f"sha256: {got['sha256']}")
        elif args.command == "publish":
            got = publish(args.repo, args.tag, args.public, args.who, args.wait)
            print(f"已發行 {got['version']}；sha256: {got['sha256']}")
            print(f"Codex 版：已推到公開 repo 的 {CODEX_BRANCH} 分支（{got['codex'][:8]}）" if got.get("codex")
                  else "Codex 版：這一版沒有 .codex-plugin，沒推")
        else:
            rollout(args.repo, args.version, args.public, args.who)
            print(f"名單已改：{args.version}")
    except ReleaseError as e:
        print(f"失敗：{e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
