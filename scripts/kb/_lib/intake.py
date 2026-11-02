"""收件匣（issue #10，D-240～D-245）：kb intake 的本體。收件匣只有這裡能寫（D-046），守門照舊擋 AI 直接寫。

receive：拖進對話的檔、程式或 skill 交來的檔。照順序判斷（output.source_mode 的寫法，守門同一套 guard.classify、credential_hit）：
不存在 → 拒絕；在知識庫裡（收件匣的說已經在、其他區拒絕）；排除的（Z10、Z10b）、檔名像密碼或金鑰的拒絕；登記的來源裡（Z9）
不複製、說已經在讀；指紋等於清冊某個 active 條目的現行指紋不複製、說收過了（帶 --name 的不走這條）；其餘複製（原檔不動，D-240）。
檔名照原檔名，有 title 用它加原副檔名（D-245）；同名加 (2)。from 記來源名（D-242）；from 加 name 是定期同步的（D-241）：
存 收件匣/<來源>/<項目><原副檔名>，同來源同項目再交就覆蓋（內容一樣不動），那裡的同名檔不是那個來源交的拒絕。
receive_pasted：這一句（或 prev: 上一則）貼的圖與文字，從回合記的對話紀錄（transcript）取（D-243、裁定 8）：從檔尾往前找客戶訊息，
圖照 media_type 存、不轉檔，系統另存了原圖（inlined_image_paths，~/.claude/uploads/）且份數對得上就用原圖；
文字取 <pasted_content> 每一段的內文，沒有標記取整則訊息（系統提醒、IDE 帶的不算）。取不到一律丟 Refused（圖請她用檔案總管把原圖放進收件匣，文字請她存成檔再拖）。
寫入前 turn.backup（新收 create、覆蓋 modify），寫完 inventory.register_intake。拒絕丟 Refused，訊息就是給人看的那句（一字不差）。
"""
import base64
import json
import os
import re
import shutil
from pathlib import Path

from kb._lib import credentials, inventory, output, turn

INBOX = inventory.INBOX

NOT_FOUND = "找不到這個檔：{path}"
IN_INBOX = "這份已經在收件匣：{rel}"
IN_VAULT = "這份已經在知識庫裡：{rel}"
EXCLUDED = "這個位置你說過不讀"
CREDENTIAL = "這個檔名像密碼或金鑰，不收"
BAD_NAME = '檔名不能有 \\ / : * ? " < > | $ ` 這些字元'
HIDDEN_NAME = "這種名字知識庫不會讀，換個名字"
TOO_LONG = "檔名太長，換短一點的名字"
NAME_MAX = 255  # NTFS 一段名字的上限（UTF-16 字元）
DEVICE_NAME = "這種名字 Windows 不收，換個名字"
READING = "這份我已經在讀了：{where}"
HAVE = "這份收過了：{where}"
NO_IMAGE = ("這張圖拿不到原檔：先在使用者的下載、桌面找同名或同時間的圖，找到就 kb intake 那份；"
            "找不到才請使用者把原圖拖進來。")  # 桌面版拖圖片檔等於貼圖（裁定 8）；寫給 AI（放寬甲）
NO_TEXT = ("這段拿不到原文：先在使用者的下載、桌面找同名或同時間的檔，找到就 kb intake 那份；"
           "找不到才請使用者把內容存成檔再拖進來。")
NO_PREV = "找不到上一則；請把要存的再貼一次"
NAME_NEEDS_FROM = "--name 要配 --from"
PASTED_NEEDS_TITLE = "--pasted 要給 --title"
NEW = "收進收件匣了：{rel}（原檔沒動）"
NEW_TO = "收進「{place}」了：{rel}（原檔沒動）"
NEW_TITLED = "收進收件匣了：{rel}（原本叫 {orig}）"
NEW_PLAIN = "收進收件匣了：{rel}"
UPDATED = "更新了：{rel}"
SAME = "沒有變：{rel}"

IMAGE_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}  # 照原格式存、不轉檔（D-243）
UPLOAD_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
# 不是客戶說的話（同 hooks/turn.py 的 NOT_A_PROMPT）：背景通知、跨對話訊息
NOT_A_PROMPT = ("<task-notification", "<cross-session-message", "<agent-message", "[SYSTEM NOTIFICATION",
                # 按停止留下的、斜線指令與 ! 指令的紀錄：也不是她貼的（code review，裁定 8 的上一則）
                "[Request interrupted", "<command-name>", "<command-message>", "<command-args>", "<local-command-",
                "<bash-input>", "<bash-stdout>", "<bash-stderr>")
# 系統或 IDE 附在客戶訊息裡的段（桌面版的系統提醒、VS Code 開著的檔與選取）：不算她貼的
INJECTED = ("<system-reminder", "<ide_")
_PASTED = re.compile(r"<pasted_content\b[^>]*>(.*?)</pasted_content\b[^>]*>", re.DOTALL)
_REF = re.compile(r"^(prev:)?(image|text):([1-9][0-9]{0,3})$")
PREV = "prev:"  # 上一則客戶訊息貼的（她被問「要不要存」之後才說存起來，裁定 8）
READ_CHUNK = 1 << 16


class Refused(Exception):
    """拒絕：訊息就是給人看的那句。"""


class Conflict(Refused):
    """同名：帶 conflict 列（name、dest、same_content、existing），--json 與 CLI 結果用（放寬甲）。"""

    def __init__(self, text, rows):
        super().__init__(text)
        self.rows = rows


class NotInTranscript(Exception):
    """對話紀錄裡拿不到：沒有紀錄、檔不在、這則訊息沒有那一項、格式認不得。"""


# ---------- 檔名 ----------

def check_name(name):
    """檔名、來源名、項目名的檢查（output 的不收字元與冒號，加 $、反引號；Windows 裝置名；. 與 ~$ 開頭知識庫不讀）。
    回去掉頭尾空白與結尾的點的名字。"""
    from kb._lib.source_edit import DEVICE_NAMES
    text = str(name or "").strip()
    clean = text.rstrip(" .")
    if not clean or output._UNSAFE.search(text):
        raise Refused(BAD_NAME)
    if clean.startswith(".") or clean.startswith("~$"):
        raise Refused(HIDDEN_NAME)
    if clean.split(".")[0].strip().upper() in DEVICE_NAMES:
        raise Refused(DEVICE_NAME)
    if len(clean.encode("utf-16-le")) // 2 > NAME_MAX:
        raise Refused(TOO_LONG)
    return clean


PATH_MAX = 260  # Windows 沒開長路徑時整條路徑的上限


def too_long(e):
    """寫檔的 OSError 是不是路徑太長：ENAMETOOLONG、Windows 的 ERROR_FILENAME_EXCED_RANGE（206），或整條路徑超過 260 字時
    Windows 回的「找不到路徑」（3）。"""
    import errno
    win = getattr(e, "winerror", None)
    names = [str(x) for x in (getattr(e, "filename", None), getattr(e, "filename2", None)) if x]
    return (getattr(e, "errno", None) == errno.ENAMETOOLONG or win == 206
            or (win == 3 and any(len(n) >= PATH_MAX for n in names)))


def titled(title, ext):
    """AI 取的名字加原副檔名；名字已經以原副檔名結尾就不重複加。"""
    text = str(title or "").strip()
    if ext and text.casefold().endswith(ext.casefold()):
        return text
    return text + (ext or "")


def _no_credential(rel):
    if credentials.match_segment(rel.split("/")[1:]) is not None:
        raise Refused(CREDENTIAL)


def _item(path, entry_id, result, said, in_vault=True):
    return {"path": path, "id": entry_id, "result": result, "said": said, "in_vault": in_vault}


def _where(uri):
    return uri[len("file://"):] if uri.startswith("file://") else uri


def _entry_at(vault, rel):
    e = inventory.entry_for(vault, "file://" + rel)
    return e if e and e.get("status") == "active" else None


def _same_content(vault, sources, digest):
    """現行指紋相同、而且至少一個位置在磁碟上真的有檔的 active 條目（檔在 kb 外被刪、清冊還沒掃的不算，收件匣裁定 6）。"""
    for e in inventory.load(vault)["entries"]:
        fps = e.get("fingerprints") or []
        if e.get("status") != "active" or not fps or fps[-1].get("sha256") != digest:
            continue
        for loc in e.get("locations") or []:
            path = inventory.path_of(vault, sources, loc.get("uri", ""))
            if path is not None and Path(path).is_file():
                return dict(e, locations=[loc])
    return None


def _hold_conflict(vault, place, same, rename="加 --title <新名>"):
    c = output.conflict(place, same, rename=rename)
    return Conflict(str(c), c.rows)


def _register(vault, place, turn_id, meta, fresh):
    if place["kind"] == "outside":  # 沒登記的地方清冊不管
        return None
    return inventory.register_intake(vault, place["rel"] or place["bkey"], turn_id, meta, fresh=fresh, uri=place["uri"],
                                     target=place["target"] if place["kind"] == "source" else None)


def _sha_of_put(vault, put):
    """貼的內容還沒落地：先寫到暫存檔算指紋，比同名檔用。"""
    import secrets
    tmp = Path(vault) / ".system" / "temp" / f"intake-{secrets.token_hex(4)}"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    try:
        put(tmp)
        return inventory.sha256_of(tmp)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def _write_new(vault, sources, place, turn_id, put, meta, replace=False, digest=None):
    """備份（新收 create、--replace 覆蓋 modify）→ 放 → 登記。同名不再加 (2)：內容一樣回 None（呼叫端說「收過了」），
    不一樣丟 Conflict；--replace 先備進回合再覆蓋。回 (place, 條目, 是不是覆蓋)。"""
    target = place["target"]
    existing = os.path.lexists(target)
    if existing and not replace:
        digest = digest or _sha_of_put(vault, put)
        same = target.is_file() and inventory.sha256_of(target) == digest
        if same:
            return place, None, None
        raise _hold_conflict(vault, place, False)
    output.backup_before(vault, sources, place, turn_id, "modify" if existing else "create")
    target.parent.mkdir(parents=True, exist_ok=True)
    put(target)
    return place, _register(vault, place, turn_id, meta, fresh=not existing), existing


def _place(vault, sources, to, cwd, from_, fname):
    """檔的落點：--to 的夾（任何准許的位置）；沒給放收件匣（from 是子夾）。"""
    try:
        if to:
            return output.place_at(vault, sources, output.resolve_dest(vault, sources, to, cwd), fname)
        base = Path(vault) / INBOX / from_ if from_ else Path(vault) / INBOX
        return output.place_at(vault, sources, base, fname)
    except output.Refused as e:
        raise Refused(str(e)) from None


def _said(place, rel_shown):
    if place["legacy"] and rel_shown.split("/")[0].casefold() == INBOX.casefold():
        return NEW.format(rel=rel_shown)
    return NEW_TO.format(place=place["dest_rel"].rpartition("/")[2] or place["dest_rel"], rel=rel_shown)


# ---------- 收檔 ----------

def receive(vault, src, turn_id, cwd, title=None, from_=None, name=None, to=None, replace=False):
    """收一份檔，回 {"path","id","result","said"}；拒絕丟 Refused，同名內容不一樣丟 Conflict。
    --to（放寬甲）：收進使用者的夾（准許的位置照 source-edit，不收 willy 的區）；沒給照舊收件匣。"""
    from kb import guard
    from kb._lib import sources as sources_lib
    from kb._lib.paths import normalize
    if name and not from_:
        raise Refused(NAME_NEEDS_FROM)
    path = output._abs(src, cwd)
    if not path.is_file():
        raise Refused(NOT_FOUND.format(path=src))
    if output._inside(path, vault):
        rel = os.path.relpath(os.path.realpath(str(path)), os.path.realpath(str(vault))).replace("\\", "/")
        if rel.split("/", 1)[0].casefold() == INBOX.casefold():
            rel = f"{INBOX}/{rel.split('/', 1)[1]}"
            e = _entry_at(vault, rel)
            return _item(rel, e["id"] if e else None, "already_inbox", IN_INBOX.format(rel=rel))
        raise Refused(IN_VAULT.format(rel=rel))
    sources = sources_lib.load(vault)
    path_n, vault_n = normalize(os.path.realpath(str(path)), None), normalize(str(vault), None)
    zone, _alias = guard.classify(path_n, vault_n, sources)
    if zone in ("Z10", "Z10b"):
        raise Refused(EXCLUDED)
    if guard.credential_hit(path_n, zone, vault_n, sources) is not None:
        raise Refused(CREDENTIAL)
    if zone == "Z9":
        uri = inventory.uri_of(vault, sources, path) or ""
        e = inventory.entry_for(vault, uri) if uri else None
        return _item(_where(uri), e["id"] if e else None, "reading", READING.format(where=_where(uri)), in_vault=False)
    ext = path.suffix
    meta = {}
    if from_:
        from_ = check_name(from_)
        meta["from"] = from_
    if name:
        meta["name"] = name = check_name(name)
        fname = check_name(titled(name, ext))
    elif title:
        fname = check_name(titled(check_name(title), ext))
    else:
        fname = check_name(path.name)
    place = _place(vault, sources, to, cwd, from_ if name else None, fname)
    if place["rel"]:
        _no_credential(place["rel"])
    digest = inventory.sha256_of(path)
    if name:
        return _periodic(vault, sources, path, place, digest, turn_id, meta, replace)
    have = _same_content(vault, sources, digest)
    if have is not None:
        where = _where(have["locations"][0].get("uri", ""))
        return _item(where, have["id"], "have", HAVE.format(where=where), in_vault=False)
    if title and fname != path.name:
        meta["original_name"] = path.name
    place, entry, was = _write_new(vault, sources, place, turn_id, lambda t: shutil.copy2(str(path), str(t)), meta,
                                   replace=replace, digest=digest)
    shown = output.shown_path(place)
    if was is None and entry is None and os.path.lexists(place["target"]) and not replace:
        return _item(shown, None, "have", HAVE.format(where=shown), in_vault=place["kind"] == "vault")
    if was:
        return _item(shown, entry["id"] if entry else None, "updated", UPDATED.format(rel=shown), in_vault=place["kind"] == "vault")
    said = (NEW_TITLED.format(rel=shown, orig=path.name) if meta.get("original_name") and place["legacy"]
            else _said(place, shown))
    return _item(shown, entry["id"] if entry else None, "new", said, in_vault=place["kind"] == "vault")


def _periodic(vault, sources, path, place, digest, turn_id, meta, replace=False):
    """定期同步的（D-241）：同來源同項目覆蓋；那裡的檔不是這個來源交的回 conflict（放寬甲）。"""
    target = place["target"]
    shown = output.shown_path(place)
    in_vault = place["kind"] == "vault"
    if os.path.lexists(target):
        e = inventory.entry_for(vault, place["uri"] or ("file://" + place["rel"])) if place["kind"] != "outside" else None
        e = e if e and e.get("status") == "active" else None
        info = (e or {}).get("intake") or {}
        mine = (target.is_file() and str(info.get("from", "")).casefold() == meta["from"].casefold()
                and str(info.get("name", "")).casefold() == meta["name"].casefold())
        if not mine and not replace:
            raise _hold_conflict(vault, place, target.is_file() and inventory.sha256_of(target) == digest, rename="換一個 --name")
        if inventory.sha256_of(target) == digest:
            return _item(shown, e["id"] if e else None, "same", SAME.format(rel=shown), in_vault=in_vault)
        output.backup_before(vault, sources, place, turn_id, "modify")
        shutil.copy2(str(path), str(target))
        entry = _register(vault, place, turn_id, meta, fresh=False)
        return _item(shown, entry["id"] if entry else None, "updated", UPDATED.format(rel=shown), in_vault=in_vault)
    output.backup_before(vault, sources, place, turn_id, "create")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(path), str(target))
    entry = _register(vault, place, turn_id, meta, fresh=True)
    return _item(shown, entry["id"] if entry else None, "new", NEW_PLAIN.format(rel=shown), in_vault=in_vault)


# ---------- 對話紀錄 ----------

def _lines_backwards(path):
    """從檔尾往前一行一行給（bytes）；紀錄可能很大，不整份讀。"""
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        pos, buf = f.tell(), b""
        while pos > 0:
            step = min(READ_CHUNK, pos)
            pos -= step
            f.seek(pos)
            buf = f.read(step) + buf
            parts = buf.split(b"\n")
            buf = parts[0]
            yield from reversed(parts[1:])
        yield buf


def _blocks(content):
    """訊息內容 → 段的清單（字串內容當一段文字）。"""
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    raise NotInTranscript("訊息內容認不得")


def _own_texts(blocks):
    """客戶自己的文字段：去掉系統或 IDE 附的。"""
    return [b.get("text") or "" for b in blocks
            if b.get("type") == "text" and not str(b.get("text") or "").lstrip().startswith(INJECTED)]


def _is_customer(d):
    if d.get("type") != "user" or d.get("isMeta") or d.get("isSidechain") or d.get("isCompactSummary"):
        return False
    msg = d.get("message")
    if not isinstance(msg, dict) or msg.get("role") != "user":
        return False
    try:
        blocks = _blocks(msg.get("content"))
    except NotInTranscript:
        return False
    if any(b.get("type") == "tool_result" for b in blocks):
        return False
    texts = _own_texts(blocks)
    images = [b for b in blocks if b.get("type") == "image"]
    if not texts and not images:
        return False
    return not (texts[0].lstrip() if texts else "").startswith(NOT_A_PROMPT)


def read_message(path):
    """對話紀錄最後一則客戶訊息：{"uuid","blocks","uploads"}；uploads 是它後面 inlined_image_paths 附件給的原圖路徑（照順序）。
    沒有紀錄、讀不到、找不到客戶訊息丟 NotInTranscript。壞行（寫到一半的最後一行）跳過。"""
    return read_messages(path)[0]


def read_messages(path, prev=False):
    """[這一則]，prev 時 [這一則, 上一則]（沒有上一則就只有這一則）。上一則是緊接在這一則之前的那一則客戶訊息：紀錄有 parentUuid
    就順著這一則的 parentUuid 往上找（退回、編輯留在檔裡的另一支不算），沒有就照檔案順序；中間只隔 AI 回答、工具結果、附件這類，
    再往前不找，遇到摺疊的摘要就停（裁定 8）。上一則的原圖是它跟這一則之間的 inlined_image_paths 附件。只要這一則就不往前讀。
    找不到這一則丟 NotInTranscript。"""
    if not path:
        raise NotInTranscript("回合沒有記對話紀錄")
    found, groups = [], []
    chain, want = False, None
    try:
        for d in _records_backwards(path):
            if not found:
                if _upload_paths(d) is not None:
                    groups.append(_upload_paths(d))
                elif _is_customer(d):
                    found.append(_message(d, groups))
                    if not prev:
                        break
                    groups, chain, want = [], "parentUuid" in d, d.get("parentUuid")
                    if chain and not want:
                        break
                continue
            if chain:
                if d.get("uuid") != want:
                    continue
                want = d.get("parentUuid")
            if d.get("isCompactSummary"):
                break
            if _upload_paths(d) is not None:
                groups.append(_upload_paths(d))
            elif _is_customer(d):
                found.append(_message(d, groups))
                break
            if chain and not want:
                break
    except OSError as e:
        raise NotInTranscript(f"對話紀錄讀不到：{type(e).__name__}") from None
    if not found:
        raise NotInTranscript("找不到客戶的訊息")
    return found


def _records_backwards(path):
    """從檔尾往前一筆一筆給紀錄（dict）；壞行（寫到一半的最後一行）跳過。"""
    for raw in _lines_backwards(path):
        if not raw.strip():
            continue
        try:
            d = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(d, dict):
            yield d


def _upload_paths(d):
    """inlined_image_paths 附件 → 原圖路徑清單；不是這種附件回 None。"""
    att = d.get("attachment")
    if d.get("type") == "attachment" and isinstance(att, dict) and att.get("type") == "inlined_image_paths":
        return [str(p) for p in att.get("paths") or [] if isinstance(p, str)]
    return None


def _message(d, groups):
    return {"uuid": d.get("uuid"), "blocks": _blocks(d["message"]["content"]),
            "uploads": [p for g in reversed(groups) for p in g]}


def _images(msg):
    return [b for b in msg["blocks"] if b.get("type") == "image"]


def _texts(msg):
    own = _own_texts(msg["blocks"])
    found = [_unwrap(m.group(1)) for t in own for m in _PASTED.finditer(t)]
    if found:
        return found
    return ["\n".join(own)] if own else []


def _unwrap(inner):
    """標記後面與結尾標記前面的那個換行是包裝加的，不是她貼的；內文其他一字不動。"""
    if inner.startswith("\n"):
        inner = inner[1:]
    return inner[:-1] if inner.endswith("\n") else inner


def _decode(block):
    src = block.get("source") or {}
    media = src.get("media_type")
    if src.get("type") != "base64" or media not in IMAGE_EXT:
        raise NotInTranscript("圖的格式認不得")
    try:
        return base64.b64decode(src.get("data") or "", validate=True), media
    except ValueError:
        raise NotInTranscript("圖的資料認不得") from None


def pasted_items(msg):
    """這則訊息裡的圖與文字：[{"ref","kind","media_type","bytes"} 或 {"ref","kind","chars"}]。"""
    out = []
    for i, b in enumerate(_images(msg), 1):
        try:
            data, media = _decode(b)
        except NotInTranscript:
            continue
        out.append({"ref": f"image:{i}", "kind": "image", "media_type": media, "bytes": len(data)})
    out.extend({"ref": f"text:{i}", "kind": "text", "chars": len(t)} for i, t in enumerate(_texts(msg), 1))
    return out


def pasted_image(msg, n):
    """第 n 張圖：(位元組, media_type, 原圖路徑或 None)。原圖要份數跟圖對得上才照順序配。"""
    images = _images(msg)
    if not 1 <= n <= len(images):
        raise NotInTranscript("沒有這張圖")
    data, media = _decode(images[n - 1])
    uploads = msg.get("uploads") or []
    return data, media, (uploads[n - 1] if len(uploads) == len(images) else None)


def pasted_text(msg, n):
    texts = _texts(msg)
    if not 1 <= n <= len(texts):
        raise NotInTranscript("沒有這段文字")
    return texts[n - 1]


def uploads_root():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "uploads"


def _upload_ok(path):
    """原圖要在 Claude 的 uploads 夾裡、是認得的圖檔。"""
    if not path:
        return False
    p = Path(path)
    return (p.suffix.lower() in UPLOAD_EXTS and p.is_file()
            and output._inside(p, uploads_root()) and output._real(p) != output._real(uploads_root()))


def parse_ref(ref):
    """「image:2」「prev:text:1」→ (種類, 第幾個, 是不是上一則)；認不得回 (None, None, False)。"""
    m = _REF.match(str(ref or "").strip())
    return (m.group(2), int(m.group(3)), bool(m.group(1))) if m else (None, None, False)


def pasted_list(transcript):
    """--pasted list：這一則的圖與文字，接著上一則的（ref 加 prev: 前綴、"message" 是 this 或 prev）；拿不到這一則丟 NotInTranscript。"""
    msgs = read_messages(transcript, prev=True)
    out = [dict(i, message="this") for i in pasted_items(msgs[0])]
    if len(msgs) > 1:
        out += [dict(i, ref=PREV + i["ref"], message="prev") for i in pasted_items(msgs[1])]
    return out


def receive_pasted(vault, ref, title, turn_id, transcript, to=None, replace=False):
    """存這一句（或 prev: 上一則）貼的第幾張圖或第幾段文字，回 {"path","id","result","said"}；拿不到丟 Refused。"""
    kind, n, prev = parse_ref(ref)
    miss = NO_IMAGE if kind == "image" else NO_TEXT
    if not title:
        raise Refused(PASTED_NEEDS_TITLE)
    try:
        msgs = read_messages(transcript, prev=prev)
        if prev and len(msgs) < 2:
            raise Refused(NO_PREV)
        msg = msgs[-1]
        if kind == "image":
            data, media, upload = pasted_image(msg, n)
        elif kind == "text":
            text = pasted_text(msg, n)
        else:
            raise NotInTranscript("要寫 image:<第幾個> 或 text:<第幾個>")
    except NotInTranscript:
        raise Refused(miss) from None
    name = check_name(title)
    if kind == "image":
        if _upload_ok(upload):
            ext = Path(upload).suffix.lower()
            meta = {"pasted": "image"}
            put = lambda t: shutil.copy2(upload, str(t))  # noqa: E731
        else:
            ext = IMAGE_EXT[media]
            meta = {"pasted": "image", "copy": True}  # 紀錄裡的版本可能縮過（D-243）
            put = lambda t: t.write_bytes(data)  # noqa: E731
    else:
        ext = ".txt"
        meta = {"pasted": "text"}
        body = text.replace("\r\n", "\n").encode("utf-8")
        put = lambda t: t.write_bytes(body)  # noqa: E731
    from kb._lib import sources as sources_lib
    sources = sources_lib.load(vault)
    place = _place(vault, sources, to, os.getcwd(), None, check_name(titled(name, ext)))
    if place["rel"]:
        _no_credential(place["rel"])
    place, entry, was = _write_new(vault, sources, place, turn_id, put, meta, replace=replace)
    shown = output.shown_path(place)
    if entry is None and was is None:
        return _item(shown, None, "have", HAVE.format(where=shown), in_vault=place["kind"] == "vault")
    return _item(shown, entry["id"] if entry else None, "updated" if was else "new",
                 UPDATED.format(rel=shown) if was else NEW_PLAIN.format(rel=shown), in_vault=place["kind"] == "vault")
