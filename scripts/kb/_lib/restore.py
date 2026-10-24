"""還原（備份還原與換電腦 要做的事 2，D-205、D-211）：AI 先演練（check，只讀）、客戶說好才動手（apply）。

check：比現在與那份，會不見的（現在有、那份沒有）與會回來的分開數：口述、裁示、日程、推算、實體、檔案卡、綜合卡
（內容不同也算會變回舊的）、AI 產出、工作日誌的回合；各舉最多 EXAMPLES_MAX 個白話標題（不印編號）。
擋：不是我們的備份、壞了、zip slip、備份版本比現在新、背景整理還在跑、這個資料夾不是空的也不是知識庫（apply 另擋鎖被占著）。
apply：先拍快照（現在是知識庫才拍，reason restore）→ 解到 .system/temp/restore-<時間>/ 並驗 → 現在的東西（除了保留的）移到
.system/temp/restore-old-<時間>/ → 解出來的移到位 → 成功後刪 restore-old；任何一步失敗全部移回去、什麼都沒動，那句帶第一個開著的檔名。
保留、不還原的（PRESERVED）：vault.json、env.json（現在有就留；空資料夾還原用備份的）、turns/、snapshots/、temp/、guard-status/、
ledger.tsv、hook-errors.log、鎖檔。之後：跑 kb init 同一支補骨架與遷移、現在有而那份沒有的 hidden 排除寫回並重清、
清冊快速比一次回「還原後有 N 份要重新整理」、記一段工作日誌（程式段，對話裡叫的併進回合）。
check 用 tempfile 解需要的檔到系統暫存，不寫知識庫。比對用各自的 load（舊備份的 schema 照現有遷移讀）。
"""
import argparse
import contextlib
import io
import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from kb._lib import backup, env, paths
from kb._lib import io as kio

EXAMPLES_MAX = 3
SYSTEM = ".system"
RESERVED_TOP = {".system", ".claude", "系統", "收件匣", "檔案索引", "AI 產出"}
# 保留、不還原的 .system 底下的項目（名字；鎖檔另判）
PRESERVED = {"vault.json", "env.json", "turns", "snapshots", "temp", "guard-status", "ledger.tsv", "hook-errors.log"}
# 現在有就留、空資料夾還原才用備份的
KEEP_IF_PRESENT = {"vault.json", "env.json"}
CLASSES = (("statements", "口述", "條"), ("rulings", "裁示", "條"), ("agenda", "日程", "條"), ("findings", "推算", "條"),
           ("entities", "實體", "個"), ("cards", "檔案卡", "張"), ("synthesis", "綜合卡", "張"),
           ("outputs", "AI 產出", "份"), ("journal_turns", "工作日誌", "個回合"))
NOT_EMPTY = "這個資料夾不是空的，也不是知識庫；換一個空資料夾"
NOT_FOUND = "找不到這份：{}"
FILE_OPEN = backup.FILE_OPEN
AFTER_SENTENCE = "已還原到 {when} 的備份；說「剛剛的還原不要了」可以回到還原前。還原後有 {n} 份要重新整理。"


def _rename(src, dst):
    """所有搬動都經這裡（測試換替身）。"""
    os.rename(paths.long_path(src), paths.long_path(dst))


# ---------- 目標與來源 ----------

def target_of(cwd):
    """(知識庫或 None, 目標資料夾)：cwd 在知識庫裡就是那個知識庫，否則 cwd 本身。"""
    from kb import guard
    found = guard.find_vault(str(cwd))
    if found is not None:
        v = Path(os.path.realpath(str(found)))
        return v, v
    return None, Path(os.path.realpath(str(cwd)))


def find_source(source, vault, cwd):
    """zip 路徑（相對 cwd 也行）、知識庫快照名、或備份夾裡的檔名 → 路徑；找不到丟 Refused。"""
    p = Path(source)
    if not p.is_absolute():
        p = Path(cwd) / p
    if p.is_file():
        return p
    if vault is not None:
        for s in backup.snapshots(vault):
            if s.name == source:
                return s
        d = env.backup_dir(vault)
        if d and (Path(d) / source).is_file():
            return Path(d) / source
    raise backup.Refused(NOT_FOUND.format(source))


def latest_snapshot(vault):
    """最新的快照（「剛剛的還原不要了」用）；沒有回 None。"""
    got = backup.snapshots(vault)
    return got[0] if got else None


def _guard_target(vault, target):
    """不是知識庫、也不是空資料夾就丟 Refused。"""
    from kb._lib import build
    if vault is None and build.not_empty(target):
        raise backup.Refused(NOT_EMPTY)


# ---------- 比對 ----------

def _extract(zip_path, dest):
    """只解比對要用的小檔（.md、.json、.jsonl，不含回合備份）到 dest；回 zip 的檔名清單。"""
    with zipfile.ZipFile(str(zip_path)) as z:
        names = z.namelist()
        for info in z.infolist():
            n = info.filename
            if info.is_dir() or n.startswith(".system/versions/") or not n.lower().endswith((".md", ".json", ".jsonl")):
                continue
            target = Path(dest).joinpath(*n.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    return names


def _safe(fn, *a):
    try:
        return fn(*a)
    except (ValueError, OSError):
        return None


def _labels(root, names):
    """root（知識庫或解出來的資料夾）的比對材料：{類別: {鍵: 標題}}；synthesis 的值是 (標題, sha256)。
    names 是這一邊的檔名清單（AI 產出用，不必解檔）。"""
    from kb._lib import agenda, cards, entities, findings, rulings, statements
    out = {k: {} for k, *_ in CLASSES}
    root = Path(root)
    data = _safe(statements.load, root)
    out["statements"] = {s["id"]: str(s.get("text", "")) for s in (data or {}).get("statements", [])
                         if s.get("status") == "active" and s.get("id")}
    data = _safe(rulings.load, root)
    out["rulings"] = {r["id"]: str(r.get("text", "")) for r in (data or {}).get("rulings", [])
                      if r.get("id") and rulings.is_active(r)}
    data = _safe(agenda.load, root)
    out["agenda"] = {i["id"]: str(i.get("text", "")) for i in (data or {}).get("items", [])
                     if i.get("status") == "open" and i.get("id")}
    data = _safe(findings.load, root)
    out["findings"] = {c["id"]: str(c.get("text", "")) for c in (data or {}).get("findings", [])
                       if c.get("status") == "active" and c.get("id")}
    data = _safe(entities.load, root)
    out["entities"] = {e["id"]: str(e.get("name", "")) for e in (data or {}).get("entities", [])
                       if e.get("status") == "active" and e.get("id")}
    index = root / "檔案索引"
    if index.is_dir():
        for p in index.rglob("*.md"):
            front = _safe(lambda q=p: cards.parse_front(q.read_text(encoding="utf-8")))
            cid = str((front or {}).get("編號", ""))
            if cid.startswith("f-"):
                out["cards"][cid] = str(front.get("標題") or p.stem)
    for top in sorted(root.iterdir()) if root.is_dir() else []:
        if not top.is_dir() or top.name in RESERVED_TOP or top.name.startswith("."):
            continue
        for sub in top.iterdir():
            card = sub / f"{sub.name}.md"
            if sub.is_dir() and card.is_file():
                digest = _safe(lambda q=card: __import__("hashlib").sha256(q.read_bytes()).hexdigest())
                out["synthesis"][f"{top.name}/{sub.name}"] = (sub.name, digest)
    out["outputs"] = {n: Path(n).name for n in names if n.startswith("AI 產出/") and not n.endswith("/")}
    out["journal_turns"] = {t: t for t in _journal_turns(root)}
    return out


def _journal_turns(root):
    got = set()
    folder = Path(root) / SYSTEM / "journal"
    for f in sorted(folder.glob("*.jsonl")) if folder.is_dir() else []:
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    got.add(str(row.get("turn") or line))
        except (OSError, ValueError):
            continue
    return got


def _vault_names(vault):
    """知識庫現在的檔名清單（zip 內路徑的寫法），只為了數 AI 產出。"""
    root = Path(vault) / "AI 產出"
    if not root.is_dir():
        return []
    return [p.relative_to(vault).as_posix() for p in root.rglob("*") if p.is_file()]


def _hidden_keys(root):
    """sources.json 裡 hidden 排除的 (別名, spec)。讀不到當沒有。"""
    try:
        data = json.loads((Path(root) / SYSTEM / "sources.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {(s.get("alias"), ex.get("spec")) for s in data.get("sources", []) if isinstance(s, dict)
            for ex in s.get("excludes") or [] if isinstance(ex, dict) and ex.get("kind") == "hidden"}


def _build_step(root):
    try:
        data = json.loads((Path(root) / SYSTEM / "build.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    step = data.get("step") if isinstance(data, dict) else None
    return step if step and step != "done" else None


def _compare(vault, target, zip_path):
    tmp = Path(tempfile.mkdtemp(prefix="wwb-check-"))
    try:
        names = _extract(zip_path, tmp)
        theirs = _labels(tmp, names)
        ours = _labels(target, _vault_names(target)) if vault is not None else {k: {} for k, *_ in CLASSES}
        hidden_theirs = _hidden_keys(tmp)
        hidden_now = _hidden_keys(target) if vault is not None else set()
        build_step = _build_step(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    lose, back, examples, examples_back = {}, {}, {}, {}
    for key, _word, _unit in CLASSES:
        mine, other = ours[key], theirs[key]
        if key == "synthesis":
            gone = [k for k in mine if k not in other or mine[k][1] != other[k][1]]
            lose[key] = len(gone)
            back_keys = [k for k in other if k not in mine]
            if gone:
                examples[key] = [mine[k][0] for k in sorted(gone)[:EXAMPLES_MAX]]
            if back_keys:
                examples_back[key] = [other[k][0] for k in sorted(back_keys)[:EXAMPLES_MAX]]
            back[key] = len(back_keys)
            continue
        gone = [k for k in mine if k not in other]
        came = [k for k in other if k not in mine]
        lose[key] = len(gone)
        if key != "journal_turns":
            back[key] = len(came)
        if gone and key != "journal_turns":
            examples[key] = [mine[k] for k in sorted(gone)[:EXAMPLES_MAX]]
        if came and key != "journal_turns":
            examples_back[key] = [other[k] for k in sorted(came)[:EXAMPLES_MAX]]
    reapply = sorted(f"{a}/{s}" for a, s in hidden_now - hidden_theirs)
    return lose, back, examples, examples_back, reapply, build_step


def check(cwd, source):
    """演練：回 {"created","machine","kind","lose","back","examples","examples_back","hidden_reapply","build_step","refuse"}。
    只讀。擋的原因放 refuse（其他欄位盡量算、算不出來給空的）。"""
    vault, target = target_of(cwd)
    got = {"created": None, "machine": None, "kind": None, "lose": {}, "back": {}, "examples": {}, "examples_back": {},
           "hidden_reapply": [], "build_step": None, "refuse": None}
    try:
        zip_path = find_source(source, vault, cwd)
        meta = backup.verify(zip_path)
        got.update(created=meta.get("created"), machine=meta.get("machine"), kind=meta.get("kind"))
        _guard_target(vault, target)
        if vault is not None and backup.batch_running(vault):
            raise backup.Refused(backup.BATCH_RUNNING.format(what="還原"))
        lose, back, ex, exb, reapply, step = _compare(vault, target, zip_path)
        got.update(lose=lose, back=back, examples=ex, examples_back=exb, hidden_reapply=reapply, build_step=step)
    except backup.Refused as e:
        got["refuse"] = str(e)
    return got


def when_text(created):
    """meta 的 created → 「10-15 14:05」。"""
    try:
        return datetime.strptime(str(created), "%Y-%m-%dT%H:%M:%S").strftime("%m-%d %H:%M")
    except ValueError:
        return str(created)


def lines(result):
    """check 結果的人讀版（不印編號）：第一行「會回到 … 的樣子」，每類一行，最後「你原本的資料夾不會動」。"""
    if result.get("refuse"):
        return [result["refuse"]]
    out = [f"會回到 {when_text(result['created'])} 的樣子"]
    if result.get("machine"):
        out.append(f"這份是 {result['machine']} 做的{'快照' if result.get('kind') == 'snapshot' else '備份'}")
    for key, word, unit in CLASSES:
        n_lose, n_back = result["lose"].get(key, 0), result["back"].get(key, 0)
        parts = []
        if n_lose:
            ex = result["examples"].get(key)
            parts.append(f"會不見 {n_lose} {unit}" + (f"（{'、'.join('「' + e + '」' for e in ex)}）" if ex else ""))
        if n_back:
            ex = result["examples_back"].get(key)
            parts.append(f"會回來 {n_back} {unit}" + (f"（{'、'.join('「' + e + '」' for e in ex)}）" if ex else ""))
        if parts:
            out.append(f"{word}：" + "；".join(parts))
    if not any(result["lose"].values()) and not any(result["back"].values()):
        out.append("跟現在幾乎一樣，沒有會不見或回來的")
    for name in result.get("hidden_reapply") or []:
        out.append(f"你設成不想讓 AI 看到的「{name}」會留著，還原後再清一次")
    if result.get("build_step"):
        out.append(f"建置會回到做到一半的「{result['build_step']}」那一步，下次打 build 從那裡接著做")
    out.append("你原本的資料夾不會動")
    return out


# ---------- 動手 ----------

def _first_name(e):
    name = getattr(e, "filename", None) or getattr(e, "filename2", None) or ""
    return Path(str(name)).name or "某個檔案"


def _is_lock(name):
    return name.endswith(".lock")


def _keep_now(name, vault_exists, in_system):
    """in_system 的 name 是不是這次不動（保留）。vault.json、env.json 現在有才留。"""
    if _is_lock(name):
        return True
    if name in KEEP_IF_PRESENT:
        return vault_exists
    return name in PRESERVED


def _unpack(zip_path, dest, meta):
    """全部解到 dest 並驗（數量與大小）；失敗丟 Refused。"""
    with zipfile.ZipFile(str(zip_path)) as z:
        for info in z.infolist():
            n = info.filename
            if backup._unsafe_member(n):
                raise backup.Refused(backup.BROKEN.format(why="裡面有不安全的路徑"))
            target = Path(dest).joinpath(*[s for s in n.split("/") if s])
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(paths.long_path(target), "wb") as out:
                shutil.copyfileobj(src, out)
            if os.path.getsize(paths.long_path(target)) != info.file_size:
                raise backup.Refused(backup.BROKEN.format(why=f"{Path(n).name} 解出來的大小不對"))
    got = sum(1 for p in Path(dest).rglob("*") if p.is_file()) - 1  # 扣掉 meta
    if meta.get("files") is not None and got != meta["files"]:
        raise backup.Refused(backup.BROKEN.format(why="解出來的檔數對不上"))


def _top_moves(root, vault_exists):
    """root 底下要處理的項目：[(來源, 相對路徑 parts)]。.system 底下逐項看保留，其他頂層整個。"""
    items = []
    for entry in sorted(Path(root).iterdir()):
        if entry.name == SYSTEM:
            for sub in sorted(entry.iterdir()):
                if not _keep_now(sub.name, vault_exists, True):
                    items.append((sub, (SYSTEM, sub.name)))
        else:
            items.append((entry, (entry.name,)))
    return items


def _move_all(pairs, done):
    """依序搬 (src, dst)，每搬一個記進 done；碰到錯誤原樣丟。"""
    for src, dst in pairs:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        _rename(src, dst)
        done.append((src, dst))


def _undo(done):
    """倒著搬回去；倒不回的略過（不會比不倒更糟）。"""
    for src, dst in reversed(done):
        try:
            _rename(dst, src)
        except OSError:
            pass


def _swap_in(target, extracted, old_dir, vault_exists):
    """把現在的移到 old_dir、解出來的移到位；任何一步失敗全部移回丟 Refused。成功回 None（restore-old 由呼叫端刪）。"""
    moved_old, placed = [], []
    try:
        _move_all([(src, Path(old_dir).joinpath(*parts)) for src, parts in _top_moves(target, vault_exists)
                   if parts != (SYSTEM, "temp")], moved_old)
        _move_all([(src, Path(target).joinpath(*parts)) for src, parts in _top_moves(extracted, vault_exists)],
                  placed)
    except OSError as e:
        _undo(placed)
        _undo(moved_old)
        raise backup.Refused(FILE_OPEN.format(name=_first_name(e))) from None


def _reapply_hidden(vault, hidden_now):
    """現在有、還原後的 sources.json 沒有的 hidden 排除寫回去（purge 記待清）並重清。回 (寫回的 "別名/spec", 沒清完的說明或 None)。"""
    from kb._lib import purge, turn
    from kb._lib import sources as sources_lib
    path = Path(vault) / SYSTEM / "sources.json"
    with kio.FileLock(path):
        raw = sources_lib.load_raw(vault)
        have = {(s.get("alias"), ex.get("spec")) for s in raw["sources"] for ex in s.get("excludes") or []}
        added = []
        for alias, spec, row in hidden_now:
            if (alias, spec) in have:
                continue
            src = next((s for s in raw["sources"] if s.get("alias") == alias), None)
            if src is None:
                continue
            src.setdefault("excludes", []).append(dict(row, purge=sources_lib.PURGE_PENDING))
            added.append((alias, spec))
        if not added:
            return [], None
        kio.write_json_atomic(path, raw)
        sources = sources_lib.Sources(vault, raw)
        turn_id = turn.current(vault)["turn"]
        left = None
        for alias, spec in added:
            ex = next((e for s in sources.entries if s["alias"] == alias for e in s["excludes"] if e["spec"] == spec), None)
            if ex is None:
                continue
            try:
                got = purge.purge(vault, alias, spec, ex["root"], turn_id)
                if got["remaining"]:
                    left = purge.remaining_text(got["remaining"])
                else:
                    purge.mark_done(vault, alias, spec, turn_id)
            except purge.Blocked as b:
                left = "還有綜合卡引用那夾的卡：" + "、".join(b.args[0])
    return [f"{a}/{s}" for a, s in added], left


def _hidden_rows(vault):
    """現在 sources.json 的 hidden 排除原列：[(別名, spec, 列)]。"""
    try:
        data = json.loads((Path(vault) / SYSTEM / "sources.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [(s.get("alias"), ex.get("spec"), dict(ex)) for s in data.get("sources", []) if isinstance(s, dict)
            for ex in s.get("excludes") or [] if isinstance(ex, dict) and ex.get("kind") == "hidden"]


def _run_init(target):
    from kb import init
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        init.run(argparse.Namespace(path=str(target), check=False, json=False))


def _count_to_reorganize(vault):
    from kb._lib import inventory
    from kb._lib import sources as sources_lib
    try:
        report = inventory.scan(vault, sources_lib.load(vault), quick=True)
    except (ValueError, OSError):
        return 0
    return sum(len(report[k]) for k in ("added", "modified", "moved", "missing"))


def apply(cwd, source, conversation=False):
    """還原。回 {"sentence","snapshot","created","hidden_reapplied","hidden_left","to_reorganize","build_step"}；
    不過、做不到丟 backup.Refused（一句話）。呼叫端在 cwd 跑（cwd 在知識庫裡就還原那個知識庫）。"""
    vault, target = target_of(cwd)
    zip_path = find_source(source, vault, cwd)
    meta = backup.verify(zip_path)
    _guard_target(vault, target)
    if vault is not None and backup.batch_running(vault):
        raise backup.Refused(backup.BATCH_RUNNING.format(what="還原"))
    (target / SYSTEM).mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    temp = target / SYSTEM / "temp"
    extracted, old_dir = temp / f"restore-{stamp}", temp / f"restore-old-{stamp}"
    with backup.acquire(target):
        snapshot = None
        hidden_now = _hidden_rows(target) if vault is not None else []
        step = None
        try:
            if vault is not None:
                snapshot = backup.snapshot(vault, "restore")
            extracted.mkdir(parents=True)
            _unpack(zip_path, extracted, meta)
            (extracted / backup.META_NAME).unlink()
            step = _build_step(extracted)
            _swap_in(target, extracted, old_dir, vault is not None)
        except (OSError, zipfile.BadZipFile) as e:
            shutil.rmtree(paths.long_path(extracted), ignore_errors=True)
            shutil.rmtree(paths.long_path(old_dir), ignore_errors=True)
            raise backup.Refused(FILE_OPEN.format(name=_first_name(e))) from None
        except BaseException:
            shutil.rmtree(paths.long_path(extracted), ignore_errors=True)
            shutil.rmtree(paths.long_path(old_dir), ignore_errors=True)
            raise
        shutil.rmtree(paths.long_path(old_dir), ignore_errors=True)
        shutil.rmtree(paths.long_path(extracted), ignore_errors=True)
        from kb._lib import vault as vault_lib
        vault_lib.ensure_vault_id(target)
        _run_init(target)
    reapplied, left = (_reapply_hidden(target, hidden_now) if hidden_now else ([], None))
    if reapplied and snapshot is not None and not snapshot.exists():
        snapshot = None
    n = _count_to_reorganize(target)
    when = when_text(meta.get("created"))
    sentence = AFTER_SENTENCE.format(when=when, n=n)
    from kb import journal_cli
    journal_cli.record_program_or_warn(target, f"已還原到 {when} 的備份（{meta.get('machine') or '另一台電腦'} 做的）",
                                       [{"path": SYSTEM, "action": "modify"}], "restore apply", conversation)
    return {"sentence": sentence, "snapshot": snapshot.name if snapshot is not None else None,
            "created": meta.get("created"), "hidden_reapplied": reapplied, "hidden_left": left,
            "to_reorganize": n, "build_step": step}


def list_for(cwd, from_dir=None):
    """restore list 的材料：[{name, path, kind, created, machine, plugin_version, bytes, usable, why}]，新的在前。"""
    vault, _target = target_of(cwd)
    return backup.list_backups(vault, extra_dir=from_dir)
