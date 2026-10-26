"""kb intake 黑箱（issue #10 驗收 1～6、8、9、11）：subprocess 跑 kb.py，cwd 在知識庫。
沒登記資料夾的知識庫用 kb init 建；有登記的用 tests/fixtures/inventory 複本；排除夾用 tests/fixtures/vault（行政/舊檔 不讀）。
對話裡的那一句用 turn.start(V, SID, …) 模擬，終端機的用 turn.start(V, None, …)。"""
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import _cards
from tests._guard_fixture import make_vault
from tests.test_lib_inventory_scan import make_inv_vault
from tests.test_scripts_inventory_cli import KB, ROOT
from kb._lib import cards, entities, inventory, journal, turn  # noqa: E402
from kb._lib import sources as sources_lib  # noqa: E402

SID = "sid-intake"
FIX = Path(__file__).resolve().parent / "fixtures" / "intake"
ID_PATTERN = re.compile(r"[aefsrcp]-[0-9a-f]{8}")
NEXT = "接著整理：kb cards dispatch --json"
PASTE = "第一條 甲方委託乙方裝修。\n第二條 工期 30 天，逾期每日罰 1,000 元。\n\n  （以下空白）"


def run(*args, cwd, extra_env=None):
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT), **(extra_env or {}))
    return subprocess.run([sys.executable, str(KB), *args], capture_output=True, text=True, encoding="utf-8",
                          cwd=str(cwd), env=env)


class Base(unittest.TestCase):
    def kb(self, *args, **kw):
        return run("intake", *args, cwd=self.V, **kw)

    def ok(self, *args, **kw):
        r = self.kb(*args, **kw)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(ID_PATTERN.findall(r.stdout), [], "人讀輸出不印編號")
        return r.stdout.strip().splitlines()

    def refused(self, *args, **kw):
        r = self.kb(*args, **kw)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        return r.stdout.strip().splitlines()

    def entries(self, origin="intake"):
        return [e for e in inventory.load(self.V)["entries"] if e.get("origin") == origin and e.get("intake")]

    def inbox_files(self):
        root = self.V / "收件匣"
        return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and not p.name.startswith("."))

    def outside(self, name, data):
        p = self.tmp / "下載" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p


class NoFolders(Base):
    """驗收 1、2、4：沒登記任何夾的知識庫。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kbintake-")).resolve()
        self.V = self.tmp / "知識庫"
        r = run("init", str(self.V), cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.t = turn.start(self.V, SID, "這是王先生的合約")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_1_copy_into_inbox(self):
        src = self.outside("合約.pdf", b"%PDF-1.4 wang")
        out = self.ok(str(src))
        self.assertEqual(out, ["收進收件匣了：收件匣/合約.pdf（原檔沒動）", NEXT])
        self.assertEqual((self.V / "收件匣" / "合約.pdf").read_bytes(), b"%PDF-1.4 wang")
        self.assertTrue(src.is_file())
        (e,) = self.entries()
        self.assertEqual((e["origin"], e["status"], e["created_turn"]), ("intake", "active", self.t))
        self.assertTrue(e["intake"]["received"])
        self.assertNotIn("from", e["intake"])
        self.assertEqual({r["path"]: r["action"] for r in turn.entries(self.V, self.t)}["收件匣/合約.pdf"], "create")
        self.assertIn(e["id"], turn.touched(turn.current(self.V, SID))["files"])

    def test_2_same_content_again(self):
        src = self.outside("合約.pdf", b"%PDF-1.4 wang")
        self.ok(str(src))
        copy = self.outside("合約 - 複製.pdf", b"%PDF-1.4 wang")
        self.assertEqual(self.ok(str(copy)), ["這份收過了：收件匣/合約.pdf"])
        self.assertEqual(self.inbox_files(), ["合約.pdf"])
        self.assertEqual(len(self.entries()), 1)

    def test_4_title_and_same_name(self):
        src = self.outside("IMG_2034.jpg", b"\xff\xd8 photo one")
        self.assertEqual(self.ok(str(src), "--title", "王先生合約"),
                         ["收進收件匣了：收件匣/王先生合約.jpg（原本叫 IMG_2034.jpg）", NEXT])
        (e,) = self.entries()
        self.assertEqual(e["intake"]["original_name"], "IMG_2034.jpg")
        other = self.outside("IMG_2035.jpg", b"\xff\xd8 photo two")
        self.assertEqual(self.ok(str(other), "--title", "王先生合約")[0],
                         "收進收件匣了：收件匣/王先生合約 (2).jpg（原本叫 IMG_2035.jpg）")
        self.assertEqual(self.inbox_files(), ["王先生合約 (2).jpg", "王先生合約.jpg"])

    def test_already_in_inbox_and_in_vault(self):
        self.ok(str(self.outside("a.txt", b"a")))
        self.assertEqual(self.ok(str(self.V / "收件匣" / "a.txt")), ["這份已經在收件匣：收件匣/a.txt"])
        self.assertEqual(self.refused(str(self.V / "系統" / "客戶設定檔.md")), ["這份已經在知識庫裡：系統/客戶設定檔.md"])

    def test_refusals(self):
        self.assertEqual(self.refused(str(self.tmp / "沒有.pdf")), [f"找不到這個檔：{self.tmp / '沒有.pdf'}"])
        self.assertEqual(self.refused(str(self.outside("帳密.xlsx", b"x"))), ["這個檔名像密碼或金鑰，不收"])
        src = self.outside("a.pdf", b"a")
        self.assertEqual(self.refused(str(src), "--title", "a$b"), ['檔名不能有 \\ / : * ? " < > | $ ` 這些字元'])
        self.assertEqual(self.refused(str(src), "--name", "x"), ["--name 要配 --from"])
        self.assertEqual(self.refused("--pasted", "image:1"), ["--pasted 要給 --title"])
        self.assertEqual(self.inbox_files(), [])
        self.assertEqual(self.entries(), [])

    def test_many_paths_one_refused_others_kept(self):
        a, b = self.outside("a.pdf", b"a"), self.outside("帳密.xlsx", b"b")
        out = self.refused(str(a), str(b))
        self.assertEqual(out, ["收進收件匣了：收件匣/a.pdf（原檔沒動）", "帳密.xlsx：這個檔名像密碼或金鑰，不收", NEXT])
        self.assertEqual(self.inbox_files(), ["a.pdf"])

    def test_r6_2_deleted_file_is_received_again(self):
        """裁定 6 #2：收件匣那份在檔案總管被刪、清冊還沒掃，再拖同一份照新收。"""
        src = self.outside("合約.pdf", b"%PDF-1.4 wang")
        self.ok(str(src))
        (self.V / "收件匣" / "合約.pdf").unlink()
        self.assertEqual(self.ok(str(src))[0], "收進收件匣了：收件匣/合約.pdf（原檔沒動）")
        self.assertTrue((self.V / "收件匣" / "合約.pdf").is_file())

    def test_r6_5_name_too_long(self):
        src = self.outside("a.pdf", b"a")
        self.assertEqual(self.refused(str(src), "--title", "字" * 300), ["檔名太長，換短一點的名字"])
        self.assertEqual(self.inbox_files(), [])
        self.assertNotIn("收件匣/" + "字" * 300 + ".pdf", [e["path"] for e in turn.entries(self.V, self.t)])

    def test_r6_6_many_paths_refusals_carry_file_name(self):
        a, b, c = self.outside("m1.txt", b"1"), self.outside("帳密.xlsx", b"2"), self.tmp / "沒有.txt"
        out = self.refused(str(a), str(b), str(c))
        self.assertEqual(out, ["收進收件匣了：收件匣/m1.txt（原檔沒動）", "帳密.xlsx：這個檔名像密碼或金鑰，不收",
                               f"沒有.txt：找不到這個檔：{c}", NEXT])

    def test_json(self):
        r = self.kb(str(self.outside("a.pdf", b"a")), "--json")
        data = json.loads(r.stdout)
        (item,) = data["items"]
        self.assertEqual((item["path"], item["result"], item["said"]), ("收件匣/a.pdf", "new", "收進收件匣了：收件匣/a.pdf（原檔沒動）"))
        self.assertTrue(item["id"].startswith("f-"))
        self.assertEqual(data["next"], "kb cards dispatch --json")

    def test_terminal_run_writes_program_journal_and_no_next(self):
        turn.set_done(self.V, SID)
        turn.start(self.V, None, "")
        out = self.ok(str(self.outside("a.pdf", b"a")))
        self.assertEqual(out, ["收進收件匣了：收件匣/a.pdf（原檔沒動）"])
        rows = [r for m in journal.months(self.V) for r in journal.read_lines(self.V, m) if r.get("kind") == "program"]
        self.assertEqual(rows[-1]["command"], "intake")
        self.assertIn("收件匣/a.pdf", rows[-1]["note"])

    def test_13_outside_conversation_gets_its_own_0000_turn(self):
        """驗收 13（D-502）：current.json 是已答完的對話回合，沒帶 --session 跑 kb intake → 備份在自己的 0000 回合，
        不掛進那句對話；記一段程式段。"""
        turn.set_done(self.V, SID)
        r = run("intake", str(self.outside("合約.pdf", b"%PDF late")), cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(NEXT, r.stdout)
        self.assertEqual(turn.entries(self.V, self.t), [])
        (e,) = self.entries()
        self.assertTrue(e["created_turn"].endswith("-0000"), e["created_turn"])
        self.assertEqual({x["path"]: x["action"] for x in turn.entries(self.V, e["created_turn"])}["收件匣/合約.pdf"], "create")
        rows = [x for m in journal.months(self.V) for x in journal.read_lines(self.V, m) if x.get("kind") == "program"]
        self.assertEqual(rows[-1]["command"], "intake")

    def test_8_revert_removes_and_revert_of_revert_brings_back(self):
        self.ok(str(self.outside("合約.pdf", b"%PDF wang")))
        (e,) = self.entries()
        r = run("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.V / "收件匣" / "合約.pdf").exists())
        self.assertEqual(inventory.entry_for(self.V, "file://收件匣/合約.pdf", inventory.load(self.V)["entries"])["status"],
                         "turn_reverted")
        self.assertIn("成品 0 份", r.stdout)
        r = run("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.V / "收件匣" / "合約.pdf").read_bytes(), b"%PDF wang")
        got = next(x for x in inventory.load(self.V)["entries"] if x["id"] == e["id"])
        self.assertEqual(got["status"], "active")


class Periodic(Base):
    """驗收 5：程式定期交來的（--from --name）。"""

    def setUp(self):
        self.tmp, self.V, self.raw = _cards.make_card_vault()
        _cards.mark_dates_scanned(self.V)
        turn.start(self.V, None, "")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_5_new_same_updated_and_customer_file(self):
        a = self.outside("a.md", b"# v1\n")
        self.assertEqual(self.ok(str(a), "--from", "公司系統", "--name", "客戶王先生"),
                         ["收進收件匣了：收件匣/公司系統/客戶王先生.md"])
        (e,) = self.entries()
        self.assertEqual((e["intake"]["from"], e["intake"]["name"]), ("公司系統", "客戶王先生"))
        self.assertEqual(self.ok(str(a), "--from", "公司系統", "--name", "客戶王先生"), ["沒有變：收件匣/公司系統/客戶王先生.md"])
        # 做一張卡，內容變了要列 stale
        item = next(i for i in cards.todo(self.V, sources_lib.load(self.V))["new"] if i["id"] == e["id"])
        _cards.write_card(self.V, item, "客戶王先生", kind="資料")
        t2 = turn.start(self.V, None, "")["turn"]
        a.write_bytes(b"# v2 changed\n")
        self.assertEqual(self.ok(str(a), "--from", "公司系統", "--name", "客戶王先生"), ["更新了：收件匣/公司系統/客戶王先生.md"])
        self.assertEqual((self.V / "收件匣" / "公司系統" / "客戶王先生.md").read_bytes(), b"# v2 changed\n")
        backed = self.V / ".system" / "versions"
        olds = [p for p in backed.rglob("客戶王先生.md") if p.read_bytes() == b"# v1\n"]
        self.assertTrue(olds, "舊內容備進回合")
        (e2,) = self.entries()
        self.assertEqual((e2["id"], len(e2["fingerprints"])), (e["id"], 2))
        stale = {i["id"] for i in cards.todo(self.V, sources_lib.load(self.V))["stale"]}
        self.assertIn(e["id"], stale)
        self.assertNotEqual(t2, None)
        # 客戶自己放的同名檔
        mine = self.V / "收件匣" / "公司系統" / "客戶李小姐.md"
        mine.write_bytes(b"mine")
        _cards.scan_apply(self.V)
        self.assertEqual(self.refused(str(a), "--from", "公司系統", "--name", "客戶李小姐"),
                         ["收件匣/公司系統/ 裡已經有同名的檔，不是 公司系統 交的；請先改名或搬走"])
        self.assertEqual(mine.read_bytes(), b"mine")

    def test_from_without_name_goes_to_top_and_is_recorded(self):
        a = self.outside("價目表.pdf", b"%PDF price")
        self.assertEqual(self.ok(str(a), "--from", "某網站"), ["收進收件匣了：收件匣/價目表.pdf（原檔沒動）"])
        (e,) = self.entries()
        self.assertEqual(e["intake"]["from"], "某網站")
        self.assertNotIn("name", e["intake"])

    def test_bad_source_or_item_name(self):
        a = self.outside("a.md", b"x")
        for args in (("--from", "a/b", "--name", "x"), ("--from", "公司", "--name", "..")):
            with self.subTest(args=args):
                self.refused(str(a), *args)
        self.assertEqual(self.entries(), [])

    def test_revert_of_update_brings_old_content_back(self):
        a = self.outside("a.md", b"# v1\n")
        self.ok(str(a), "--from", "公司系統", "--name", "客戶王先生")
        turn.start(self.V, None, "")
        a.write_bytes(b"# v2\n")
        self.ok(str(a), "--from", "公司系統", "--name", "客戶王先生")
        r = run("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.V / "收件匣" / "公司系統" / "客戶王先生.md").read_bytes(), b"# v1\n")


class Registered(Base):
    """驗收 3：登記的夾裡的檔不複製；排除夾裡的、檔名像密碼的拒絕。"""

    def setUp(self):
        self.tmp, self.V, self.raw = make_inv_vault()
        turn.start(self.V, SID, "存起來")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_3_reading(self):
        src = self.raw / "客戶案件" / "大安陳" / "會議紀錄_1.docx"
        self.assertEqual(self.ok(str(src)), ["這份我已經在讀了：客戶案件/大安陳/會議紀錄_1.docx"])
        self.assertEqual(self.inbox_files(), ["貼文.txt"])

    def test_3_excluded(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp, self.V, self.raw = make_vault()
        turn.start(self.V, SID, "存起來")
        before = sorted(p.as_posix() for p in self.V.rglob("*"))
        self.assertEqual(self.refused(str(self.raw / "行政" / "舊檔" / "o.doc")), ["這個位置你說過不讀"])
        self.assertEqual(self.refused(str(self.raw / "行政" / "薪資" / "s.xlsx")), ["這個位置你說過不讀"])
        after = sorted(p.as_posix() for p in self.V.rglob("*") if "versions" not in p.parts and "turns" not in p.parts)
        self.assertEqual([p for p in after if "收件匣" in p], [p for p in before if "收件匣" in p])


class Pasted(Base):
    """驗收 6：從對話紀錄取這一句貼的圖與文字。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kbintake-")).resolve()
        self.V = self.tmp / "知識庫"
        run("init", str(self.V), cwd=self.tmp)
        self.cfg = self.tmp / "claude-config"
        (self.cfg / "uploads" / "sess").mkdir(parents=True)
        shutil.copy2(FIX / "原圖.png", self.cfg / "uploads" / "sess" / "c226210d-image.png")
        self.env = {"CLAUDE_CONFIG_DIR": str(self.cfg)}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kb(self, *args, **kw):
        """裁定 6 #1：主對話的 kb intake 守門會插 --session；--pasted 只認那個對話的回合。"""
        return run("--session", SID, "intake", *args, cwd=self.V, **kw)

    def use(self, name):
        text = (FIX / name).read_text(encoding="utf-8").replace("<UPLOADS>", (self.cfg / "uploads").as_posix())
        p = self.tmp / name
        p.write_text(text, encoding="utf-8")
        turn.start(self.V, SID, "存起來", transcript=str(p))

    def test_6_list_and_save_text_and_image(self):
        self.use("desktop.jsonl")
        png = (FIX / "名片.png").read_bytes()
        self.assertEqual(self.ok("--pasted", "list", extra_env=self.env),
                         [f"image:1（image/png，{len(png)} 位元組）", f"text:1（{len(PASTE)} 字）"])
        out = self.ok("--pasted", "text:1", "--title", "2026-10-26 王先生合約條文", extra_env=self.env)
        self.assertEqual(out, ["收進收件匣了：收件匣/2026-10-26 王先生合約條文.txt", NEXT])
        self.assertEqual((self.V / "收件匣" / "2026-10-26 王先生合約條文.txt").read_bytes(), PASTE.encode("utf-8"))
        out = self.ok("--pasted", "image:1", "--title", "2026-10-26 陳經理名片", extra_env=self.env)
        self.assertEqual(out[0], "收進收件匣了：收件匣/2026-10-26 陳經理名片.png")
        self.assertEqual((self.V / "收件匣" / "2026-10-26 陳經理名片.png").read_bytes(), png)
        img = inventory.entry_for(self.V, "file://收件匣/2026-10-26 陳經理名片.png")
        self.assertEqual((img["intake"]["pasted"], img["intake"]["copy"]), ("image", True))
        txt = inventory.entry_for(self.V, "file://收件匣/2026-10-26 王先生合約條文.txt")
        self.assertEqual(txt["intake"]["pasted"], "text")
        self.assertNotIn("copy", txt["intake"])

    def test_6_uploads_original_is_used(self):
        self.use("uploads.jsonl")
        self.ok("--pasted", "image:1", "--title", "名片", extra_env=self.env)
        self.assertEqual((self.V / "收件匣" / "名片.png").read_bytes(), (FIX / "原圖.png").read_bytes())
        e = inventory.entry_for(self.V, "file://收件匣/名片.png")
        self.assertNotIn("copy", e["intake"])

    def test_6_vscode_whole_message(self):
        self.use("vscode.jsonl")
        self.ok("--pasted", "text:1", "--title", "王先生合約", extra_env=self.env)
        self.assertEqual((self.V / "收件匣" / "王先生合約.txt").read_text(encoding="utf-8"),
                         "王先生合約\n第一條 甲方委託乙方裝修。\n第二條 工期 30 天。")

    def test_6_terminal_or_finished_turn_does_not_read_transcript(self):
        """code review：對話答完之後（或終端機）跑的不取紀錄，免得拿到別句貼的東西。"""
        self.use("desktop.jsonl")
        turn.set_done(self.V, SID)
        self.assertEqual(self.refused("--pasted", "text:1", "--title", "x", extra_env=self.env),
                         ["這段我拿不到原文；請把它存成檔，再拖進對話"])

    def test_r6_1_without_session_pasted_is_refused(self):
        self.use("desktop.jsonl")
        r = run("intake", "--pasted", "text:1", "--title", "x", cwd=self.V, extra_env=self.env)
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "這段我拿不到原文；請把它存成檔，再拖進對話"))

    def test_r6_1_two_conversations_each_read_their_own(self):
        """裁定 6 #1：兩個對話開同一個知識庫，A 的 --pasted 讀 A 的紀錄，不是 current.json 那個（B 最後說話）。"""
        a = self.tmp / "plain.jsonl"
        a.write_text((FIX / "plain.jsonl").read_text(encoding="utf-8"), encoding="utf-8")
        ta = turn.start(self.V, "sA", "存起來", transcript=str(a))["turn"]
        self.use("desktop.jsonl")  # SID（B）後說話，current.json 是 B
        r = run("--session", "sA", "intake", "--pasted", "list", cwd=self.V, extra_env=self.env)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "text:1（11 字）"))
        src = self.tmp / "x.pdf"
        src.write_bytes(b"%PDF a")
        r = run("--session", "sA", "intake", str(src), cwd=self.V, extra_env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("收件匣/x.pdf", [e["path"] for e in turn.entries(self.V, ta)])

    def test_6_no_transcript(self):
        turn.start(self.V, SID, "存起來")
        self.assertEqual(self.refused("--pasted", "image:1", "--title", "x", extra_env=self.env),
                         ["這張圖我拿不到檔；請把它存到電腦，再拖進對話"])
        self.assertEqual(self.refused("--pasted", "text:1", "--title", "x", extra_env=self.env),
                         ["這段我拿不到原文；請把它存成檔，再拖進對話"])
        self.use("vscode.jsonl")
        self.assertEqual(self.refused("--pasted", "image:1", "--title", "x", extra_env=self.env),
                         ["這張圖我拿不到檔；請把它存到電腦，再拖進對話"])
        self.assertEqual(self.refused("--pasted", "text:2", "--title", "x", extra_env=self.env),
                         ["這段我拿不到原文；請把它存成檔，再拖進對話"])
        self.assertEqual([p.name for p in (self.V / "收件匣").iterdir() if not p.name.startswith(".")], [])


class InboxPlace(Base):
    """驗收 9：整理完當場問要放哪（kb asks 的 inbox_place）。"""

    def setUp(self):
        self.tmp, self.V, self.raw = _cards.make_card_vault()
        _cards.mark_dates_scanned(self.V)
        t0 = turn.start(self.V, None, "")["turn"]
        entities.add(self.V, "案子", "大安陳", t0)
        # 大安陳既有的卡在 客戶案件/大安陳（會議紀錄）
        self.mount_existing("大安陳")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def mount_existing(self, name):
        for item in cards.todo(self.V, sources_lib.load(self.V))["new"]:
            if item["uri"].endswith("會議紀錄_1.docx"):
                p = _cards.write_card(self.V, item, "第一次會議")
                p.write_text(p.read_text(encoding="utf-8").replace("實體: []", f"實體: [{name}]"), encoding="utf-8",
                             newline="\n")

    def card_for(self, e, name, title):
        item = next(i for i in cards.todo(self.V, sources_lib.load(self.V))["new"] if i["id"] == e["id"])
        p = _cards.write_card(self.V, item, title, kind="合約")
        p.write_text(p.read_text(encoding="utf-8").replace("實體: []", f"實體: [{name}]"), encoding="utf-8", newline="\n")

    def asks(self, *args):
        r = run("asks", "--json", *args, cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout)

    def test_9_this_turn_intake_is_asked_with_folders(self):
        turn.start(self.V, SID, "這是大安陳的合約")
        self.ok(str(self.outside("合約.pdf", b"%PDF chen")))
        (e,) = self.entries()
        self.card_for(e, "大安陳", "大安陳合約")
        got = self.asks()
        ask = next(a for a in got["asks"] if a["kind"] == "inbox_place")
        self.assertEqual(ask["key"].split("@")[0], f"inbox:{e['id']}")
        self.assertEqual(ask["question"], "大安陳合約（收件匣）要放到哪裡？")
        labels = [r["label"] for r in ask["results"]]
        self.assertEqual(labels, ["放到 客戶案件/大安陳", "先放著"])
        self.assertEqual(ask["results"][0]["do"], ['kb source-edit move 收件匣/合約.pdf --to 客戶案件/大安陳'])
        self.assertEqual(ask["results"][-1]["do"], [])
        self.assertFalse(ask["urgent"])
        r = run("source-edit", "move", "收件匣/合約.pdf", "--to", "客戶案件/大安陳", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_9_earlier_intake_goes_to_others(self):
        turn.start(self.V, SID, "上一句")
        self.ok(str(self.outside("合約.pdf", b"%PDF chen")))
        (e,) = self.entries()
        self.card_for(e, "大安陳", "大安陳合約")
        turn.start(self.V, SID, "下一句講別的")
        got = self.asks()
        self.assertFalse([a for a in got["asks"] if a["kind"] == "inbox_place"])
        self.assertGreaterEqual(got["others"], 1)
        every = self.asks("--all")
        self.assertTrue([a for a in every["asks"] if a["kind"] == "inbox_place"])

    def test_9_no_folder_gives_entity_folder_and_subfolder_not_asked(self):
        t = turn.start(self.V, SID, "王先生的")["turn"]
        entities.add(self.V, "案子", "王先生", t)
        self.ok(str(self.outside("名片.png", b"png wang")))
        self.ok(str(self.outside("w.md", b"wang data")), "--from", "公司系統", "--name", "客戶王先生")
        for e in self.entries():
            self.card_for(e, "王先生", "王先生" + e["intake"].get("name", "名片"))
        got = self.asks("--all")
        asks = [a for a in got["asks"] if a["kind"] == "inbox_place"]
        self.assertEqual(len(asks), 1)
        self.assertEqual([r["label"] for r in asks[0]["results"]], ["放到 案子/王先生", "先放著"])
        self.assertEqual(asks[0]["results"][0]["do"], ["kb source-edit move 收件匣/名片.png --to 案子/王先生"])

    def test_ruling_1_move_creates_entity_folder_and_revert_removes_it(self):
        """裁定 1：實體登記了、夾不在 → move 先建那一層再搬，卡跟著搬；退回 → 檔回收件匣、夾拿掉。"""
        t = turn.start(self.V, SID, "王先生的合約")["turn"]
        entities.add(self.V, "案子", "王先生", t)
        self.ok(str(self.outside("合約.pdf", b"%PDF wang")))
        (e,) = self.entries()
        self.card_for(e, "王先生", "王先生合約")
        folder = self.V / "案子" / "王先生"
        self.assertFalse(folder.exists())
        r = run("source-edit", "move", "收件匣/合約.pdf", "--to", "案子/王先生", "--check", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("案子/王先生 還沒有夾，會先建一個", r.stdout.splitlines())
        self.assertFalse(folder.exists(), "--check 不建")
        turn.start(self.V, SID, "好，放進去")
        r = run("source-edit", "move", "收件匣/合約.pdf", "--to", "案子/王先生", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((folder / "合約.pdf").read_bytes(), b"%PDF wang")
        moved = inventory.entry_for(self.V, "file://知識庫/案子/王先生/合約.pdf")
        self.assertEqual(moved["id"], e["id"])
        card = cards._scan_groups(self.V)[0][e["id"]][0]["path"]
        self.assertTrue(card.startswith("檔案索引/知識庫/案子/王先生/"), card)
        r = run("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.V / "收件匣" / "合約.pdf").is_file())
        self.assertFalse(folder.exists())

    def test_ruling_1_other_missing_folders_still_refused(self):
        turn.start(self.V, SID, "x")
        self.ok(str(self.outside("合約.pdf", b"%PDF x")))
        for to, why in (("案子/沒登記的人", "找不到這個夾：案子/沒登記的人"), ("案子/大安陳/子夾", "找不到這個夾：案子/大安陳/子夾")):
            with self.subTest(to=to):
                r = run("source-edit", "move", "收件匣/合約.pdf", "--to", to, cwd=self.V)
                self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
                self.assertEqual(r.stdout.strip(), why)


class MoveCheck(Base):
    """驗收 11：從 收件匣/<來源>/ 搬出，--check 多一行。"""

    def setUp(self):
        self.tmp, self.V, self.raw = make_inv_vault()
        turn.start(self.V, None, "")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_11(self):
        self.ok(str(self.outside("a.md", b"x")), "--from", "公司系統", "--name", "客戶王先生")
        r = run("source-edit", "move", "收件匣/公司系統/客戶王先生.md", "--to", "客戶案件/大安陳", "--check", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("這份是 公司系統 定期交來的；搬走之後下次交來會在收件匣再收一份", r.stdout.splitlines())
        self.ok(str(self.outside("b.md", b"y")))
        r = run("source-edit", "move", "收件匣/b.md", "--to", "客戶案件/大安陳", "--check", cwd=self.V)
        self.assertNotIn("定期交來", r.stdout)


if __name__ == "__main__":
    unittest.main()
