"""kb refresh 的實作（多人共用 3 要做的事 2、5、7，D-293、D-295、D-301）：git pull 之後讓這台對上。

做的事：(a) git 合併做到一半 → 收拾衝突（卡留對方的、自己那版進 card_base 的 pending 照手改流程變知識、標重做；
其他檔留自己的、對方的另存「<名稱>（<對方名字>的版本）.<副檔名>」）；rebase 做到一半不動、回 rebase: true。
(b) 重畫這台的頁（日程、待處理、裁示、客戶設定檔、總目錄），不當成她手改。
(c) 知識庫 repo 裡的原檔：只對 git 這次 pull 動到的檔算指紋（pull 會把修改時間全更新）；雲端的原檔不在這裡比（交給每句開頭的檔案比對）。
(d) 大檔（超過 git_file_max_mb 還沒追蹤）加進 .git/info/exclude。
(e) 記這次的 HEAD（.system/local/last_head）與 pull 進來的檔（.system/local/pulled.json，手改基準用）。
git 不在或不是 repo：什麼都不做（回空結果）。
"""
import hashlib
import json
import os
from pathlib import Path

from kb._lib import git
from kb._lib.io import FileLock, read_json, write_json_atomic, write_text_atomic

LOCAL = ".system/local"
LAST_HEAD = LOCAL + "/last_head"
PULLED = LOCAL + "/pulled.json"
PULLED_KEEP = 200
SYSTEM_PREFIXES = (".system/", "系統/", ".obsidian/", "檔案索引/", ".git/")


def _log(vault, text):
    from kb._lib import ledger
    ledger.log_error(vault, text, source="refresh")


def empty():
    return {"rendered": [], "pulled": [], "changed": {"added": 0, "modified": 0, "missing": 0}, "unsure": 0,
            "conflicts": [], "big": [], "rebase": False}


def read_last_head(vault):
    try:
        return (Path(vault) / LAST_HEAD).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def head_changed(vault):
    """每句開頭用：HEAD 跟記下的不同才要叫 refresh。不是 git 回 False。"""
    now = git.head(vault)
    return bool(now) and now != read_last_head(vault)


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run(vault, turn_id=None):
    """回 kb refresh --json 的結構；多一個 "skipped": True 表示同時有別人在跑。"""
    out = empty()
    if not git.is_repo(vault):
        return out
    (Path(vault) / LOCAL).mkdir(parents=True, exist_ok=True)
    try:
        lock = FileLock(Path(vault) / LOCAL / "refresh", timeout=0.5)
        lock.__enter__()
    except TimeoutError:
        return dict(out, skipped=True)
    try:
        return _run(vault, turn_id, out)
    finally:
        lock.__exit__(None, None, None)


def _run(vault, turn_id, out):
    from kb._lib import turn
    if turn_id is None:
        turn_id = turn.current(vault)["turn"]
    if git.rebase_in_progress(vault):
        _log(vault, "同步卡住了（rebase 到一半），請聯絡服務人員")
        out["rebase"] = True
        return out
    if git.merge_in_progress(vault) and git.unmerged(vault):
        out["conflicts"] = resolve_conflicts(vault, turn_id)
    head = git.head(vault)
    old = read_last_head(vault)
    pulled = git.changed_since(vault, old, head) or []
    out["pulled"] = pulled
    out["rendered"] = _render_pages(vault, turn_id)
    _originals(vault, pulled, out)
    out["big"] = check_big(vault)
    if head:
        write_text_atomic(Path(vault) / LAST_HEAD, head + "\n")
    _remember_pulled(vault, pulled)
    return out


# ---------- (b) 重畫 ----------

def _render_pages(vault, turn_id):
    """日程、待處理、裁示照 purge.py 的做法在 renders.suppressed 裡、hand={} 重畫；設定檔 md 她改過就不蓋；總目錄重畫。"""
    from kb._lib import agenda, cards, pending, profile, renders, rulings
    done = []

    def step(rel, fn):
        try:
            with renders.suppressed(rel):
                fn()
            done.append(rel)
        except Exception as e:  # noqa: BLE001  一頁畫不出來不擋其他頁
            _log(vault, f"重畫 {rel} 失敗：{type(e).__name__}: {str(e)[:100]}")

    if (Path(vault) / agenda.MD_POSIX).exists():
        step(agenda.MD_POSIX, lambda: agenda.render(vault, turn_id, hand={}))
    if (Path(vault) / pending.MD_POSIX).exists():
        step(pending.MD_POSIX, lambda: pending.render(vault, turn_id=turn_id))
    if (Path(vault) / rulings.MD_POSIX).exists():
        step(rulings.MD_POSIX, lambda: rulings.render(vault, turn_id, hand={}))

    def prof():
        data = profile.load(vault)
        if data is None:
            raise LookupError("沒有設定檔")
        if data.get("md_sha256") and profile.md_sha256(vault) not in (None, data["md_sha256"]):
            raise LookupError("設定檔被她手改過，不蓋掉")  # 照現在先問
        with profile.lock(vault):
            profile.write_locked(vault, profile.load(vault), turn_id)
    if (Path(vault) / profile.MD_POSIX).exists():
        try:
            prof()
            done.append(profile.MD_POSIX)
        except LookupError:
            pass
        except Exception as e:  # noqa: BLE001
            _log(vault, f"重畫設定檔失敗：{type(e).__name__}: {str(e)[:100]}")
    try:
        cards.render_index(vault, turn_id)
        done.append(cards.INDEX_POSIX)
    except Exception as e:  # noqa: BLE001
        _log(vault, f"重畫總目錄失敗：{type(e).__name__}: {str(e)[:100]}")
    return done


# ---------- (c) 知識庫 repo 裡的原檔 ----------

def _originals(vault, pulled, out):
    """只看 pull 動到的檔、而且在知識庫別名底下的原檔：算指紋，指紋真的變了才算 modified。
    不 apply（寫清冊交給每句開頭的檔案比對）；來不及比的記 unsure。"""
    cand = {p for p in pulled if not p.startswith(SYSTEM_PREFIXES) and not p.endswith(".md")}
    if not cand:
        return
    from kb._lib import inventory
    from kb._lib import sources as sources_lib
    try:
        rep = inventory.scan(vault, sources_lib.load(vault), quick=False, only_roots=[inventory.KNOWLEDGE])
    except Exception as e:  # noqa: BLE001
        _log(vault, f"refresh 比原檔失敗：{type(e).__name__}: {str(e)[:100]}")
        return

    def mine(uris):
        return [u for u in uris if inventory.split_uri(u)[1] in cand]
    out["changed"] = {"added": len(mine(rep.get("added") or [])), "modified": len(mine(rep.get("modified") or [])),
                      "missing": len(mine(rep.get("missing") or []))}
    out["unsure"] = 1 if rep.get("incomplete") else 0


# ---------- (d) 大檔 ----------

def check_big(vault):
    from kb._lib import config
    limit = float(config.get(vault, "git_file_max_mb")) * 1024 * 1024
    cloud = _cloud_alias(vault)
    big = []
    for st, rel in git.status_untracked_and_modified(vault):
        if st.strip() != "??" or rel.startswith(SYSTEM_PREFIXES) or rel.startswith("暫存區/") or rel.startswith("_個人/"):
            continue
        try:
            size = (Path(vault) / rel).stat().st_size
        except OSError:
            continue
        if size > limit and not git.tracked(vault, rel):
            git.exclude_add(vault, rel)
            big.append({"path": rel, "mb": round(size / 1024 / 1024, 1), "cloud": cloud})
    return big


def _cloud_alias(vault):
    """sources 裡位置不在知識庫底下的來源別名（建置時登記的共用雲端夾），沒有回 None。"""
    try:
        from kb._lib import sources as sources_lib
        root = os.path.realpath(str(vault))
        for s in sources_lib.load(vault).entries:
            spec = str(s.get("spec") or "")
            if spec and not os.path.realpath(spec).startswith(root) and s.get("alias") not in ("暫存區", "知識庫"):
                return s["alias"]
    except Exception:  # noqa: BLE001
        pass
    return None


# ---------- (e) pulled ----------

def _remember_pulled(vault, pulled):
    """這次 pull 進來的卡與它們現在的 sha（問 1 (a)）：line_card_edits 遇到內容跟這裡一樣的卡就跳過。"""
    if not pulled:
        return
    p = Path(vault) / PULLED
    cur = read_json(p, {}) or {}
    for rel in pulled:
        f = Path(vault) / rel
        if f.is_file() and rel.endswith(".md"):
            try:
                cur[rel] = _sha(f.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                pass
    keep = dict(list(cur.items())[-PULLED_KEEP:])
    write_json_atomic(p, keep)


def pulled_same(vault, rel, text):
    """這張卡現在的內文跟 pull 進來時一樣嗎（一樣就不是這台的人手改）。"""
    got = read_json(Path(vault) / PULLED, {}) or {}
    return got.get(rel) == _sha(text)


# ---------- 5. 衝突 ----------

def _is_card(vault, rel):
    from kb._lib import card_base
    try:
        return card_base.card_kind(vault, rel) is not None or rel.startswith("檔案索引/")
    except Exception:  # noqa: BLE001
        return rel.startswith("檔案索引/")


def _copy_name(rel, who):
    stem, ext = os.path.splitext(rel)
    return f"{stem}（{who}的版本）{ext}"


def resolve_conflicts(vault, turn_id):
    """回 conflicts 清單，全部處理完 commit_merge。"""
    from kb._lib import card_base
    got = []
    for rel in git.unmerged(vault):
        other = git.author_of(vault, "MERGE_HEAD", rel) or "同事"
        target = Path(vault) / rel
        if rel.startswith(".system/streams/"):
            _merge_streams(vault, rel)
            git.add(vault, [rel])
            _log(vault, f"流水檔衝突：{rel}，兩邊的行都留")
            continue
        if _is_card(vault, rel):
            mine = git.show_stage(vault, rel, 2)
            base = None
            try:
                base = card_base.load(vault).get(rel, {}).get("body")
            except Exception:  # noqa: BLE001
                pass
            theirs_ok = git.checkout_theirs(vault, rel)
            if mine is not None and theirs_ok:
                _record_pending(vault, rel, base, card_base.body_of(mine), turn_id)
            _mark_redo(vault, rel, turn_id)
            git.add(vault, [rel])
            got.append({"path": rel, "kind": "card", "other": other, "copy": None})
        else:
            from kb._lib import turn
            mine = git.show_stage_bytes(vault, rel, 2)
            theirs = git.show_stage_bytes(vault, rel, 3)
            copy_rel = _copy_name(rel, other)
            try:
                turn.backup(vault, rel, turn_id)
            except Exception:  # noqa: BLE001
                pass
            if mine is not None:
                target.write_bytes(mine)
            if theirs is not None:
                (Path(vault) / copy_rel).write_bytes(theirs)
            git.add(vault, [x for x in (rel, copy_rel) if (Path(vault) / x).exists()])
            got.append({"path": rel, "kind": "file", "other": other, "copy": copy_rel})
    if not git.unmerged(vault):
        # 標重做與 pending 改到的狀態檔一起進這個合併 commit（追蹤中的才加）
        git.add(vault, [x for x in (".system/card_base.json", ".system/inventory.json") if git.tracked(vault, x)])
        git.commit_merge(vault)
    return got


def _record_pending(vault, rel, base, mine_body, turn_id):
    """自己那版進 card_base 的 pending（before 是基準、after 是自己的），之後照手改流程變成知識。
    卡已換成對方的版本，基準也換成對方的（pending 另留）。"""
    from kb._lib import card_base

    def fn(recs):
        cur = recs.get(rel) or {}
        before = base if base is not None else cur.get("body")
        theirs_body = card_base._read_body(vault, rel)
        pending = None
        if before is not None and before != mine_body:
            old = cur.get("pending")
            pending = {"before": old["before"] if old else before, "after": mine_body}
        recs[rel] = card_base._entry(theirs_body, turn_id, pending)
    card_base._locked(vault, fn)


def _mark_redo(vault, rel, turn_id):
    """卡標重做：檔案卡用 cards.mark_redo；綜合卡把「整理到」每一行的指紋欄改成 redo。標不了只記 log。"""
    from kb._lib import cards, synthesis
    try:
        text = (Path(vault) / rel).read_text(encoding="utf-8")
        if rel.startswith(cards.CARDS_DIR + "/"):
            by_path = {c["path"]: fid for fid, grp in cards._scan_groups(vault)[0].items() for c in grp}
            fid = by_path.get(rel)
            if fid:
                cards.mark_redo(vault, fid, turn_id)
            return
        lines = cards.parse_front(text).get("整理到")
        if isinstance(lines, list):
            new = [f"{str(x).split(' ')[0]} {synthesis.REDO}" for x in lines]
            from kb._lib import turn
            turn.backup(vault, rel, turn_id, by="program")
            write_text_atomic(Path(vault) / rel, synthesis.replace_front(text, {"整理到": new}))
    except Exception as e:  # noqa: BLE001
        _log(vault, f"衝突的卡標不了重做 {rel}：{type(e).__name__}: {str(e)[:100]}")


def _merge_streams(vault, rel):
    """流水檔衝突（理論上不會）：兩邊的行都留、去掉重複的行。"""
    a = git.show_stage(vault, rel, 2) or ""
    b = git.show_stage(vault, rel, 3) or ""
    seen, lines = set(), []
    for ln in (a + "\n" + b).splitlines():
        if ln.strip() and ln not in seen:
            seen.add(ln)
            lines.append(ln)
    write_text_atomic(Path(vault) / rel, "\n".join(lines) + "\n")


def public(got):
    return json.loads(json.dumps(got, ensure_ascii=False))


