"""型別夾編號（D-246～D-251）黑箱：驗收準則 1～14 各一個測試（第 15 條是收尾跑全套）。
新知識庫用 kb init 建、型別照 kb profile add 加（夾名有編號）；升級那兩條用「型別夾名就是型別名」的 schema 6 假知識庫。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests import _cards
from tests import _entities as E
from tests.test_hooks_output_log import post_payload, run_hook
from tests.test_hooks_session import payload, run as run_session
from tests.test_scripts_inventory_cli import run_kb
from tests._guard_fixture import ROOT
from kb._lib import cards, entities, inventory, migrate, profile, synthesis, turn  # noqa: E402
from kb._lib import sources as sources_lib  # noqa: E402

GUARD = ROOT / "hooks" / "guard.py"
SID = "test-sid"


def kb(V, *args, code=0):
    r = run_kb(*args, cwd=V)
    if code is not None and r.returncode != code:
        raise AssertionError(f"kb {' '.join(args)} exit {r.returncode}：{r.stdout}{r.stderr}")
    return r


def top_dirs(V):
    return sorted(p.name for p in Path(V).iterdir() if p.is_dir() and not p.name.startswith("."))


def uris(V):
    return {loc["uri"] for e in inventory.load(V)["entries"] if e["status"] == "active" for loc in e["locations"]}


def write_synthesis(V, name):
    """照 header_for 寫一張綜合卡到 card_rel（帶 vault，夾名照設定檔），記 card true。"""
    data = entities.load(V)
    e, _hit = entities.find(data, name)
    header = synthesis.header_for(V, e, entities.mounts(V, data).get(name, []), E.DAY, data=data)
    p = Path(V) / entities.card_rel(e, V)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(E.synthesis_text(header, name), encoding="utf-8", newline="\n")
    entities.set_card(V, e["id"], True, turn.start(V, None, "")["turn"])
    return p


class Base(unittest.TestCase):
    TYPES = (("案子", "事"), ("業主", "對象"))

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.V = self.tmp / "kb"
        kb(self.tmp, "init", str(self.V))
        for name, cat in self.TYPES:
            self.add_type(name, cat)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def add_type(self, name, cat, code=0):
        turn.start(self.V, None, "")
        return kb(self.V, "profile", "add", "型別", f"名稱={name}", f"大類={cat}", code=code)

    def dirs(self):
        return [t.get("dir") for t in profile.load(self.V)["types"]]

    def entity(self, type_, name, card=True):
        t = turn.start(self.V, None, "")["turn"]
        entities.add(self.V, type_, name, t)
        entities.confirm(self.V, name, t)
        if card:
            write_synthesis(self.V, name)

    def raw_with_card(self, rel, entity_name, title):
        """rel 是知識庫裡的相對路徑：放一份原檔、入冊、寫一張掛 entity_name 的檔案卡，重寫總目錄。回卡編號。"""
        raw = self.V / rel
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text(f"{title}的內容 12 萬\n", encoding="utf-8")
        _cards.scan_apply(self.V)
        item = E.new_item(self.V, f"知識庫/{rel}")
        p = _cards.card_path(self.V, item, title)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(E.with_entities(_cards.card_text(item, title, kind="報價"), [entity_name]), encoding="utf-8",
                     newline="\n")
        cards.render_index(self.V)
        _cards.mark_dates_scanned(self.V)
        return item["id"]

    def card_of(self, cid):
        return cards._scan_groups(self.V)[0][cid][0]["path"]

    def index(self):
        return (self.V / "總目錄.md").read_text(encoding="utf-8")


class NewVault(Base):
    def test_1_new_vault_numbered_dirs(self):
        top = top_dirs(self.V)
        self.assertIn("01 案子", top)
        self.assertIn("02 業主", top)
        self.assertNotIn("案子", top)
        self.assertNotIn("業主", top)
        data = profile.load(self.V)
        self.assertEqual(self.dirs(), ["01 案子", "02 業主"])
        self.assertEqual(json.loads((self.V / profile.PROFILE_POSIX).read_text(encoding="utf-8"))["schema_version"], 7)
        self.assertEqual([t["name"] for t in data["types"]], ["案子", "業主"])
        md = (self.V / profile.MD_POSIX).read_text(encoding="utf-8")
        self.assertIn("| 案子 | 事 |", md)
        self.assertNotIn("| 01 案子", md, "設定檔 md 的型別表不顯示 dir")
        self.assertIn("型別名前面會加上編號當資料夾名（例：01 案子）", md)

    def test_2_synthesis_path_and_postuse(self):
        (self.V / ".system" / "config.json").write_text('{"synthesis_min_cards": 0}', encoding="utf-8")
        self.entity("案子", "信義王", card=False)
        got = json.loads(kb(self.V, "cards", "todo", "--json").stdout)
        item = next(i for i in got["synthesis_new"] if i["name"] == "信義王")
        self.assertEqual(item["path"], "01 案子/信義王/信義王.md")
        path = self.V / item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        text = item["header"] + "# 信義王\n\n一句講這是什麼。\n\n## 現況\n- 剛開始\n"
        turn.start(self.V, SID, "寫綜合卡")
        pre = {"session_id": SID, "cwd": str(self.V), "hook_event_name": "PreToolUse", "tool_name": "Write",
               "tool_input": {"file_path": str(path), "content": text}}
        r = run_hook(pre, hook=GUARD)
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "allow", r.stdout)
        path.write_text(text, encoding="utf-8")
        r = run_hook(post_payload(self.V, "Write", path))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("block", r.stdout, r.stdout)
        ok, reason = synthesis.validate(self.V, item["path"])
        self.assertTrue(ok, reason)
        self.assertTrue(entities.find(entities.load(self.V), "信義王")[0]["card"], "PostToolUse 照常記 card")

    def test_3_no_numbers_in_conversation(self):
        self.entity("案子", "信義王")
        listed = kb(self.V, "entity", "list").stdout
        self.assertIn("案子", listed)
        self.assertNotIn("01 案子", listed)
        looked = kb(self.V, "lookup", "信義王").stdout.splitlines()
        self.assertTrue(looked[0].startswith("信義王（案子"), looked[0])  # 型別照型別名講；綜合卡那行是檔案路徑
        self.assertNotIn("01 案子", looked[0])
        front = cards.parse_front((self.V / "01 案子/信義王/信義王.md").read_text(encoding="utf-8"))
        self.assertEqual(front["型別"], "案子")
        self.assertEqual(entities.find(entities.load(self.V), "信義王")[0]["type"], "案子")


class Reorder(Base):
    def setUp(self):
        super().setUp()
        self.entity("案子", "信義王")
        self.entity("業主", "王先生")
        self.cid = self.raw_with_card("01 案子/信義王/報價.txt", "信義王", "信義王報價")

    def test_4_reorder_check_do_revert(self):
        before_dirs = top_dirs(self.V)
        before_profile = (self.V / profile.PROFILE_POSIX).read_bytes()
        got = json.loads(kb(self.V, "profile", "add", "型別", "名稱=業主", "序號=1", "--check", "--json").stdout)
        self.assertEqual(got["renames"], [{"from": "01 案子", "to": "02 案子"}, {"from": "02 業主", "to": "01 業主"}])
        self.assertTrue(got["question"])
        self.assertEqual([r["n"] for r in got["results"]], [1, 2])
        self.assertEqual(top_dirs(self.V), before_dirs, "--check 什麼都沒動")
        self.assertEqual((self.V / profile.PROFILE_POSIX).read_bytes(), before_profile)
        turn.start(self.V, None, "")
        r = kb(self.V, "profile", "add", "型別", "名稱=業主", "序號=1")
        self.assertEqual(r.stdout.strip(), "已把業主排到第 1 個：01 案子 → 02 案子、02 業主 → 01 業主；不對可以說退回")
        self.assertEqual(self.dirs(), ["01 業主", "02 案子"])
        self.assertEqual([t["name"] for t in profile.load(self.V)["types"]], ["業主", "案子"])
        self.assertTrue((self.V / "02 案子/信義王/信義王.md").is_file())
        self.assertTrue((self.V / "02 案子/信義王/報價.txt").is_file())
        self.assertTrue((self.V / "01 業主/王先生/王先生.md").is_file())
        self.assertFalse((self.V / "01 案子").exists())
        self.assertIn("file://知識庫/02 案子/信義王/報價.txt", uris(self.V))
        self.assertNotIn("file://知識庫/01 案子/信義王/報價.txt", uris(self.V))
        rel = self.card_of(self.cid)
        self.assertTrue(rel.startswith("檔案索引/知識庫/02 案子/信義王/"), rel)
        self.assertIn("檔案索引/知識庫/02%20案子/信義王/", self.index(), "總目錄的連結點得到新位置")
        self.assertNotIn("01%20案子", self.index())
        kb(self.V, "versions", "revert")
        self.assertEqual(top_dirs(self.V), before_dirs)
        self.assertEqual(self.dirs(), ["01 案子", "02 業主"])
        self.assertTrue((self.V / "01 案子/信義王/信義王.md").is_file())


class ReviewFixes(Base):
    """code-review 後補的：md 手改調順序 check 會講改名、她改成另一個預設樣子的名字照編號改回去、設定檔也有改時開場不說不用問。"""

    def test_md_reorder_is_a_change(self):
        md = self.V / profile.MD_POSIX
        text = md.read_text(encoding="utf-8")
        rows = [ln for ln in text.splitlines() if ln.startswith("| 案子 | 事 |") or ln.startswith("| 業主 | 對象 |")]
        md.write_text(text.replace(rows[0], "@@").replace(rows[1], rows[0]).replace("@@", rows[1]), encoding="utf-8")
        out = kb(self.V, "profile", "check").stdout.splitlines()
        self.assertEqual(out[0], "客戶設定檔有改：型別順序")
        self.assertIn("- 型別夾 01 案子 → 02 案子", out)
        turn.start(self.V, None, "")
        kb(self.V, "profile", "apply")
        self.assertEqual(self.dirs(), ["01 業主", "02 案子"])

    def test_default_style_rename_goes_back(self):
        self.entity("業主", "王先生")
        (self.V / "02 業主").rename(self.V / "05 業主")
        st = profile.status(self.V)
        self.assertEqual((st["renamed"], st["moves"]), ([], [("05 業主", "02 業主")]))
        turn.start(self.V, None, "")
        r = kb(self.V, "profile", "apply")
        self.assertNotIn("照你改的名字記下了", r.stdout)
        self.assertTrue((self.V / "02 業主/王先生/王先生.md").is_file())

    def test_renamed_with_md_edit_does_not_say_no_ask(self):
        self.entity("案子", "信義王")
        (self.V / "01 案子").rename(self.V / "工程案")
        md = self.V / profile.MD_POSIX
        md.write_text(md.read_text(encoding="utf-8").replace("| 業主 | 對象 |  |", "| 業主 | 對象 | 屋主 |"), encoding="utf-8")
        r = run_session(payload(self.V))
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        line = next(ln for ln in ctx.splitlines() if "你改名叫「工程案」了" in ln)
        self.assertNotIn("不用問", line)
        self.assertIn("客戶說好才 apply", line)


class Round1(Base):
    """測試第 1 輪 #2～#5（裁定 6～9）。"""
    TYPES = (("案子", "事"), ("業主", "對象"), ("工班", "對象"))

    def test_r6_type_named_like_another_types_folder_is_not_adopted(self):
        self.entity("案子", "信義王")
        (self.V / "01 案子").rename(self.V / "工程案")
        turn.start(self.V, None, "")
        kb(self.V, "profile", "apply")
        r = self.add_type("工程案", "物")
        self.assertNotIn("這個夾改叫", r.stdout)
        self.assertEqual(self.dirs(), ["工程案", "02 業主", "03 工班", "04 工程案"])
        self.assertTrue((self.V / "工程案/信義王/信義王.md").is_file())
        self.assertTrue((self.V / "04 工程案").is_dir())

    def test_r7_r11_number_dropped_is_her_rename(self):
        """裁定 11（收回裁定 7）：她把 01 案子 改回 案子，照舊認成她改名；句子講原本的夾名。"""
        self.entity("案子", "信義王")
        (self.V / "01 案子").rename(self.V / "案子")
        st = profile.status(self.V)
        self.assertEqual([(r["type"], r["to"]) for r in st["renamed"]], [("案子", "案子")])
        self.assertNotIn("案子", st["unlisted"])
        r = run_session(payload(self.V))
        ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("型別夾「01 案子」你改名叫「案子」了：跑 kb profile apply 記下來（不用問）。", ctx)
        self.assertNotIn("你改名叫「案子」了", ctx.replace("「01 案子」你改名叫「案子」了", ""))
        self.assertNotIn("不在型別表", ctx)

    def test_r11_apply_after_dropping_number(self):
        self.entity("案子", "信義王")
        (self.V / "01 案子").rename(self.V / "案子")
        turn.start(self.V, None, "")
        r = kb(self.V, "profile", "apply")
        self.assertIn("照你改的名字記下了：01 案子 → 案子", r.stdout)
        self.assertEqual(self.dirs()[0], "案子")
        self.assertFalse((self.V / "01 案子").exists(), "不建空的 01 案子")
        got = json.loads(kb(self.V, "cards", "todo", "--json").stdout)
        self.assertEqual(got["synthesis_broken"], [])

    def test_r12_rename_not_applied_then_same_name_type(self):
        """裁定 12：她改了夾名還沒 apply 就加同名型別，那個夾也不收編。"""
        self.entity("案子", "信義王")
        (self.V / "01 案子").rename(self.V / "工程案")
        r = self.add_type("工程案", "物")
        self.assertNotIn("這個夾改叫", r.stdout)
        self.assertTrue((self.V / "工程案/信義王/信義王.md").is_file())
        self.assertTrue((self.V / "04 工程案").is_dir())
        self.assertEqual(self.dirs(), ["工程案", "02 業主", "03 工班", "04 工程案"])

    def test_r8_check_says_the_rename(self):
        self.entity("案子", "信義王")
        (self.V / "01 案子").rename(self.V / "工程案")
        out = kb(self.V, "profile", "check").stdout
        self.assertIn("型別夾「案子」你改名叫「工程案」了：跑 kb profile apply 記下來（不用問）。", out)
        self.assertNotIn("客戶設定檔沒有改", out)

    def test_r9_order_number_must_be_ascii_positive(self):
        for raw in ("abc", "2.5", "-1", "１", "0", "4"):
            with self.subTest(raw=raw):
                r = kb(self.V, "profile", "add", "型別", "名稱=業主", f"序號={raw}", "--check", code=3)
                self.assertEqual(r.stdout.strip(), "序號要寫 1 到 3 的數字")
        self.assertEqual(self.dirs(), ["01 案子", "02 業主", "03 工班"])


def hidden(path):
    import os
    return bool(getattr(os.stat(path), "st_file_attributes", 0) & 0x2)


def set_hidden(path, on):
    """Windows 的隱藏屬性（測試準備用）；非 Windows 不做。"""
    import ctypes
    import os
    if os.name != "nt":
        return
    k = ctypes.windll.kernel32
    k.GetFileAttributesW.restype = ctypes.c_uint32
    attrs = k.GetFileAttributesW(str(path))
    k.SetFileAttributesW(str(path), (attrs | 0x2) if on else (attrs & ~0x2))


class RevertHiddenSkeleton(Base):
    """裁定 10（測試報告 #1）：備份時 CLAUDE.md 還沒隱藏、骨架換新之後設成隱藏（舊知識庫升級的樣子），說退回寫得回去、仍是隱藏，
    其他檔與夾名照退。copy2 在 Windows 會帶來源的屬性：備份本身是隱藏的寫得回去，不是隱藏的才會被拒。"""

    def test_revert_writes_back_hidden_claude_md(self):
        import os
        from kb._lib import skeleton
        md = self.V / "CLAUDE.md"
        set_hidden(md, False)
        md.write_text("舊的 CLAUDE.md\n", encoding="utf-8")
        t = turn.start(self.V, None, "")["turn"]
        turn.backup(self.V, "CLAUDE.md", t)
        skeleton._write_from_skeleton(self.V, "CLAUDE.md")
        kb(self.V, "profile", "add", "型別", "名稱=工班", "大類=對象")
        self.assertTrue((self.V / "03 工班").is_dir())
        self.assertNotEqual(md.read_text(encoding="utf-8"), "舊的 CLAUDE.md\n")
        if os.name == "nt":
            self.assertTrue(hidden(md), "前提：骨架換過之後是隱藏的")
            self.assertFalse(hidden(self.V / ".system" / "versions" / t / "files" / "CLAUDE.md"), "前提：備份不是隱藏的")
        kb(self.V, "versions", "revert")
        self.assertEqual(md.read_text(encoding="utf-8"), "舊的 CLAUDE.md\n")
        self.assertFalse((self.V / "03 工班").exists())
        self.assertEqual([t["name"] for t in profile.load(self.V)["types"]], ["案子", "業主"])
        if os.name == "nt":
            self.assertTrue(hidden(md), "退回後仍是隱藏")


class RevertHideFails(Base):
    """裁定 13：退回後設回隱藏失敗不中斷退回：記一行 hook-errors.log，退回照常做完（用替身）。"""

    def test_set_hidden_failure_is_logged_not_fatal(self):
        import contextlib
        import io
        import os
        from unittest import mock
        from kb import cli, versions
        from kb._lib import skeleton
        md = self.V / "CLAUDE.md"
        set_hidden(md, False)
        md.write_text("舊的 CLAUDE.md\n", encoding="utf-8")
        t = turn.start(self.V, None, "")["turn"]
        turn.backup(self.V, "CLAUDE.md", t)
        skeleton._write_from_skeleton(self.V, "CLAUDE.md")
        if os.name != "nt":
            self.skipTest("隱藏屬性只在 Windows")
        real = versions._set_hidden

        def fake(path, on):
            if on:
                raise OSError(5, "存取被拒")
            return real(path, on)
        cwd, out = os.getcwd(), io.StringIO()
        try:
            os.chdir(self.V)
            with mock.patch.object(versions, "_set_hidden", fake), contextlib.redirect_stdout(out):
                code = cli.main(["versions", "revert"])
        finally:
            os.chdir(cwd)
        self.assertEqual(code, 0, out.getvalue())
        self.assertEqual(md.read_text(encoding="utf-8"), "舊的 CLAUDE.md\n")
        log = (self.V / ".system" / "hook-errors.log").read_text(encoding="utf-8")
        self.assertIn("CLAUDE.md", log)


class MoveByTypeName(Base):
    """裁定 5：kb source-edit move --to 用型別名寫實體夾（案子/信義王），實際的夾（01 案子/信義王）在不在都認得。"""

    def put(self, name):
        f = self.V / "AI 產出" / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"{name}的內容\n", encoding="utf-8")
        _cards.scan_apply(self.V)

    def test_existing_entity_folder(self):
        self.entity("案子", "信義王")
        self.put("報價單.txt")
        turn.start(self.V, None, "")
        r = kb(self.V, "source-edit", "move", "AI 產出/報價單.txt", "--to", "案子/信義王")
        self.assertIn("已搬好", r.stdout)
        self.assertTrue((self.V / "01 案子/信義王/報價單.txt").is_file())
        self.assertFalse((self.V / "案子").exists())

    def test_missing_entity_folder_is_made(self):
        self.entity("業主", "王先生", card=False)
        self.put("名片.txt")
        turn.start(self.V, None, "")
        kb(self.V, "source-edit", "move", "AI 產出/名片.txt", "--to", "業主/王先生")
        self.assertTrue((self.V / "02 業主/王先生/名片.txt").is_file())
        self.assertFalse((self.V / "業主").exists())


class Remove(Base):
    TYPES = (("案子", "事"), ("業主", "對象"), ("工班", "對象"))

    def test_5_remove_renumbers(self):
        self.entity("工班", "陳師傅")
        cid = self.raw_with_card("03 工班/陳師傅/報價.txt", "陳師傅", "陳師傅報價")
        turn.start(self.V, None, "")
        kb(self.V, "profile", "type", "remove", "業主")
        self.assertEqual(self.dirs(), ["01 案子", "02 工班"])
        self.assertFalse((self.V / "02 業主").exists())
        self.assertFalse((self.V / "03 工班").exists())
        self.assertTrue((self.V / "02 工班/陳師傅/陳師傅.md").is_file())
        self.assertTrue((self.V / "02 工班/陳師傅/報價.txt").is_file())
        self.assertIn("file://知識庫/02 工班/陳師傅/報價.txt", uris(self.V))
        self.assertTrue(self.card_of(cid).startswith("檔案索引/知識庫/02 工班/陳師傅/"))


class Rename(Base):
    def test_6_rename_keeps_number(self):
        self.entity("案子", "信義王")
        (self.V / "AI 產出" / "案子").mkdir(parents=True)
        turn.start(self.V, None, "")
        kb(self.V, "profile", "type", "rename", "案子", "--to", "工程")
        self.assertEqual(self.dirs(), ["01 工程", "02 業主"])
        self.assertFalse((self.V / "01 案子").exists())
        self.assertTrue((self.V / "01 工程/信義王/信義王.md").is_file())
        self.assertTrue((self.V / "AI 產出" / "工程").is_dir(), "AI 產出底下照型別名、不編號（D-251）")
        self.assertFalse((self.V / "AI 產出" / "01 工程").exists())
        front = cards.parse_front((self.V / "01 工程/信義王/信義王.md").read_text(encoding="utf-8"))
        self.assertEqual(front["型別"], "工程")


class Merge(Base):
    TYPES = (("案子", "事"), ("業主", "對象"), ("工班", "對象"))

    def test_7_merge_renumbers(self):
        self.entity("業主", "王先生")
        self.entity("工班", "陳師傅")
        turn.start(self.V, None, "")
        kb(self.V, "profile", "type", "merge", "業主", "--into", "工班")
        self.assertEqual(self.dirs(), ["01 案子", "02 工班"])
        self.assertFalse((self.V / "02 業主").exists())
        self.assertFalse((self.V / "03 工班").exists())
        self.assertTrue((self.V / "02 工班/王先生/王先生.md").is_file())
        self.assertTrue((self.V / "02 工班/陳師傅/陳師傅.md").is_file())


class HandRenamed(Base):
    TYPES = (("案子", "事"), ("業主", "對象"), ("工班", "對象"))

    def context(self):
        r = run_session(payload(self.V))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_8_she_renamed_a_type_folder(self):
        self.entity("案子", "信義王")
        (self.V / "01 案子").rename(self.V / "工程案")
        ctx = self.context()
        self.assertIn("型別夾「案子」你改名叫「工程案」了：跑 kb profile apply 記下來（不用問）。", ctx)
        self.assertNotIn("不在型別表", ctx)
        turn.start(self.V, None, "")
        r = kb(self.V, "profile", "apply")
        self.assertIn("照你改的名字記下了：案子 → 工程案", r.stdout)
        self.assertEqual(self.dirs()[0], "工程案")
        e = entities.find(entities.load(self.V), "信義王")[0]
        self.assertEqual(entities.card_rel(e, self.V), "工程案/信義王/信義王.md")
        ok, reason = synthesis.validate(self.V, "工程案/信義王/信義王.md")
        self.assertTrue(ok, reason)
        self.assertFalse((self.V / "01 案子").exists(), "不改回去、不補建")
        turn.start(self.V, None, "")
        kb(self.V, "profile", "type", "remove", "業主")
        self.assertEqual(self.dirs(), ["工程案", "02 工班"])
        turn.start(self.V, None, "")
        kb(self.V, "profile", "add", "型別", "名稱=工班", "序號=1")
        self.assertEqual(self.dirs(), ["01 工班", "工程案"])
        self.assertTrue((self.V / "工程案/信義王/信義王.md").is_file())

    def test_9_unrecognized_rename(self):
        (self.V / "02 業主").rename(self.V / "客戶")
        st = profile.status(self.V)
        self.assertIn("客戶", st["unlisted"])
        self.assertEqual(st["renamed"], [])
        turn.start(self.V, None, "")
        kb(self.V, "profile", "apply")
        self.assertTrue((self.V / "02 業主").is_dir())
        self.assertTrue((self.V / "客戶").is_dir())
        self.assertEqual(self.dirs()[1], "02 業主")


class Adopt(Base):
    def test_10_own_folder_becomes_type(self):
        (self.V / "合約").mkdir()
        (self.V / "合約" / "租約.txt").write_text("租約\n", encoding="utf-8")
        r = self.add_type("合約", "物")
        self.assertIn("合約這個夾改叫 03 合約了，跟其他型別放一起", r.stdout)
        self.assertFalse((self.V / "合約").exists())
        self.assertTrue((self.V / "03 合約" / "租約.txt").is_file())
        self.assertEqual(self.dirs(), ["01 案子", "02 業主", "03 合約"])


def legacy_vault():
    """schema 6、型別夾名就是型別名（案子、業主），各一個實體與綜合卡、一份原檔與檔案卡入冊、總目錄有連結。"""
    tmp, V, _raw = E.make_entity_vault()
    t = turn.start(V, None, "")["turn"]
    for name, type_ in (("信義王", "案子"), ("王先生", "業主")):
        entities.add(V, type_, name, t)
        entities.confirm(V, name, t)
    raw = V / "案子" / "信義王" / "報價.txt"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("信義王的報價 12 萬\n", encoding="utf-8")
    _cards.scan_apply(V)
    item = E.new_item(V, "知識庫/案子/信義王/報價.txt")
    p = _cards.card_path(V, item, "信義王報價")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(E.with_entities(_cards.card_text(item, "信義王報價", kind="報價"), ["信義王"]), encoding="utf-8",
                 newline="\n")
    for name in ("信義王", "王先生"):
        write_synthesis(V, name)
    cards.render_index(V)
    _cards.mark_dates_scanned(V)
    pj = V / profile.PROFILE_POSIX
    data = json.loads(pj.read_text(encoding="utf-8"))
    data["schema_version"] = 6
    pj.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return tmp, V, item["id"]


class Upgrade(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.cid = legacy_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def dir_rows(self):
        return [p for p in migrate.pending(self.V) if p["rel"] == profile.PROFILE_POSIX and p["from"] == 6]

    def test_11_migrate_numbers_old_vault(self):
        self.assertTrue(self.dir_rows())
        t = turn.start(self.V, None, "")["turn"]
        got = migrate.apply(self.V, t)
        self.assertEqual(got["migrated"].count(profile.PROFILE_POSIX), 1, "同一個 rel 只列一次")
        self.assertEqual(got["notes"], ["型別夾補上編號：案子 → 01 案子、業主 → 02 業主"])
        self.assertEqual([x.get("dir") for x in profile.load(self.V)["types"]], ["01 案子", "02 業主"])
        self.assertTrue((self.V / "01 案子/信義王/信義王.md").is_file())
        self.assertTrue((self.V / "02 業主/王先生/王先生.md").is_file())
        self.assertFalse((self.V / "案子").exists())
        self.assertIn("file://知識庫/01 案子/信義王/報價.txt", uris(self.V))
        rel = cards._scan_groups(self.V)[0][self.cid][0]["path"]
        self.assertTrue(rel.startswith("檔案索引/知識庫/01 案子/信義王/"), rel)
        self.assertIn("檔案索引/知識庫/01%20案子/信義王/", (self.V / "總目錄.md").read_text(encoding="utf-8"))
        self.assertEqual([p for p in migrate.pending(self.V) if p["rel"] == profile.PROFILE_POSIX], [])
        kb(self.V, "versions", "revert")
        self.assertTrue((self.V / "案子/信義王/信義王.md").is_file())
        self.assertFalse((self.V / "01 案子").exists())
        self.assertTrue(all(not x.get("dir") for x in profile.load(self.V)["types"]))

    def test_11_hand_edited_md_skips(self):
        md = self.V / profile.MD_POSIX
        md.write_text(md.read_text(encoding="utf-8") + "\n<!-- 她改的 -->\n", encoding="utf-8")
        got = migrate.apply(self.V, turn.start(self.V, None, "")["turn"])
        self.assertIn(profile.PROFILE_POSIX, [s["rel"] for s in got["skipped"]])
        self.assertTrue((self.V / "案子").is_dir())
        self.assertFalse((self.V / "01 案子").exists())

    def test_12_init_does_not_touch_dirs(self):
        kb(self.V, "init", str(self.V))
        self.assertEqual(json.loads((self.V / profile.PROFILE_POSIX).read_text(encoding="utf-8"))["schema_version"], 7)
        self.assertTrue(all(not x.get("dir") for x in profile.load(self.V)["types"]))
        self.assertTrue((self.V / "案子").is_dir())
        self.assertFalse((self.V / "01 案子").exists())
        self.assertTrue(self.dir_rows(), "補編號那列還在")

    def test_13_legacy_dirs_still_work(self):
        e = entities.find(entities.load(self.V), "信義王")[0]
        self.assertEqual(entities.card_rel(e, self.V), "案子/信義王/信義王.md")
        self.assertEqual(profile.folder_of(self.V, "案子"), "案子")
        self.assertEqual(profile.type_of_folder(self.V, "案子"), "案子")
        st = profile.status(self.V)
        self.assertEqual((st["to_create"], st["unlisted"], st["moves"], st["renamed"]), ([], [], [], []))


class Guard(Base):
    def decision(self, path):
        pre = {"session_id": SID, "cwd": str(self.V), "hook_event_name": "PreToolUse", "tool_name": "Write",
               "tool_input": {"file_path": str(path), "content": "x"}}
        r = run_hook(pre, hook=GUARD)
        out = json.loads(r.stdout) if r.stdout.strip() else {}
        return (out.get("hookSpecificOutput") or {}).get("permissionDecision")

    def test_14_guard_unchanged(self):
        turn.start(self.V, SID, "寫卡")
        self.assertEqual(self.decision(self.V / "01 案子/信義王/信義王.md"), "allow")
        self.assertEqual(self.decision(self.V / "01 案子/亂放.md"), "allow")  # 放寬甲：型別夾根放檔是使用者區（Z8），檔案工具寫放行
        self.assertEqual(self.decision(self.V / "總目錄.md"), "deny")  # 知識庫根的總目錄是 willy 自己的檔


if __name__ == "__main__":
    unittest.main()
