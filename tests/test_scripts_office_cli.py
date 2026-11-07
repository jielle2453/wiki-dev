"""kb office 黑箱（produce 第 1 點，驗收 1、3、4、6、13）：subprocess 跑 kb.py，cwd 在 vault。
check 不寫檔；copy 的副本在工作區、原檔指紋不變、排除／憑證名／Z11／不在清冊各拒絕一字不差；run 工作區外拒絕；
這台有 LibreOffice 時真的轉一份 docx 成 PDF、轉圖、重算一份有公式的 xlsx，沒有就 skip。"""
import hashlib
import json
import re
import shutil
import unittest
import zipfile
from pathlib import Path

from tests import _cards, _ooxml, _produce
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import office, turn  # noqa: E402

ID_PATTERN = re.compile(r"[aefsrcp]-[0-9a-f]{8}")
HAS_LO = office.find_soffice() is not None
HAS_PDFIUM = office.pdfium_ok()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _cards.make_card_vault()
        self.t = turn.start(self.V, "sid-office", "改合約")["turn"]
        self.ws = self.V / ".system" / "temp" / "office" / self.t

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kb(self, *args):
        return run_kb("office", *args, cwd=self.V)

    def ok(self, *args):
        r = self.kb(*args)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(ID_PATTERN.findall(r.stdout), [], "人讀輸出不印編號")
        return r.stdout.strip().splitlines()

    def refused(self, *args):
        r = self.kb(*args)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        return r.stdout.strip()

    def files(self):
        return {p.relative_to(self.V).as_posix(): p.stat().st_mtime_ns for p in self.V.rglob("*") if p.is_file()}


class Check(Base):
    def test_check_writes_nothing(self):
        before = self.files()
        lines = self.ok("check")
        self.assertTrue(lines[0].startswith("Office："))
        self.assertTrue(any(ln.startswith("可以：") for ln in lines))
        data = json.loads(self.kb("check", "--json").stdout)
        self.assertEqual(set(data["env"]), {"office", "soffice", "node", "node_version", "npm", "node_packages",
                                            "py_missing", "pdfium", "tools"})
        self.assertEqual(set(data["capabilities"]), {"can", "after_setup", "cannot", "setup"})
        self.assertEqual(data["workspace"], str(self.ws))
        self.assertEqual(lines[-1], f"工作區：{self.ws}（腳本與做出來的檔放這裡）")
        self.assertFalse(self.ws.exists(), "check 不建工作區")
        self.assertEqual(self.files(), before)


class Copy(Base):
    def entry_id(self, rel):
        return _cards.entry_of(self.V, rel)["id"]

    def test_copy_by_id(self):
        src = self.raw / _cards.MEETING
        before = sha(src)
        fid = self.entry_id("客戶案件/" + _cards.MEETING.split("/", 1)[1])
        lines = self.ok("copy", fid)
        copy = Path(lines[0][len("副本："):])
        self.assertEqual(copy, self.ws / "會議紀錄_1.docx")
        self.assertEqual(sha(copy), before)
        self.assertEqual(sha(src), before, "原檔不動")
        data = json.loads(self.kb("copy", fid, "--json").stdout)
        self.assertEqual((data["id"], Path(data["copy"]).name), (fid, "會議紀錄_1 (2).docx"))

    def test_refusals_exact(self):
        run_kb("folders", "exclude", str(self.raw / "公司行政" / "舊檔"), "--kind", "unused", cwd=self.V)
        self.assertEqual(self.refused("copy", str(self.raw / "公司行政" / "舊檔" / "Big5備忘.txt")),
                         "拿不到副本：這個位置你說過不讀")
        self.assertEqual(self.refused("copy", str(self.raw / "公司行政" / "薪資" / "網銀密碼.txt")),
                         "拿不到副本：檔名像密碼或金鑰，預設不讀")
        other = self.tmp / "外面.docx"
        other.write_bytes(b"x")
        self.assertEqual(self.refused("copy", str(other)), "拿不到副本：不在登記的資料夾裡")
        self.assertEqual(self.refused("copy", "f-00000000"), "拿不到副本：清冊沒有 f-00000000")
        self.assertFalse(self.ws.exists() and any(self.ws.iterdir()), "拒絕時不留副本")

    def test_copy_clears_read_only(self):
        """測試後修正裁定 20 L-9：唯讀的原檔，副本要能改、能清。"""
        import os
        import stat
        src = self.raw / _cards.MEETING
        os.chmod(src, stat.S_IREAD)
        try:
            fid = self.entry_id("客戶案件/" + _cards.MEETING.split("/", 1)[1])
            copy = Path(self.ok("copy", fid)[0][len("副本："):])
            self.assertTrue(os.access(copy, os.W_OK))
            self.assertFalse(os.access(src, os.W_OK), "原檔的屬性不動")
        finally:
            os.chmod(src, stat.S_IWRITE | stat.S_IREAD)

    def test_copy_takes_no_vault_flag(self):
        r = self.kb("copy", "f-00000000", "--vault", str(self.V))
        self.assertEqual(r.returncode, 2, "跟 convert 一樣不收 --vault（實作回報裁定 5）")


class Run(Base):
    def test_run(self):
        outside = self.tmp / "x.py"
        outside.write_text("print(1)\n", encoding="utf-8")
        self.assertTrue(self.refused("run", str(outside)).startswith("腳本要放在工作區裡"))
        self.ws.mkdir(parents=True)
        script = self.ws / "make.py"
        script.write_text("import os\nprint('OUT=' + os.environ['OUT_DIR'])\nraise SystemExit(int(os.sys.argv[1]))\n",
                          encoding="utf-8")
        lines = self.ok("run", str(script), "0")
        self.assertEqual(lines, [f"工作區：{self.ws}", f"OUT={self.ws}", "結束碼：0"])
        r = self.kb("run", str(script), "4")
        self.assertEqual((r.returncode, r.stdout.strip().splitlines()[-1]), (3, "結束碼：4"))


class NoVaultFlag(Base):
    """收尾 security-review：office 除了 check 都不收 --vault（同 copy 與 convert，只信 cwd 的知識庫）。"""

    def test_refused(self):
        self.assertEqual(self.kb("run", "--vault", str(self.V), "x.py").returncode, 2, "run 的腳本之後的參數交給腳本")
        for args in (("pdf", "x.docx"), ("render", "x.docx"), ("recalc", "x.xlsx"), ("unpack", "x.docx"),
                     ("pack", "d", "--to", "x.docx")):
            with self.subTest(args=args):
                self.assertEqual(self.kb(*args, "--vault", str(self.V)).returncode, 2)
        self.assertEqual(self.kb("check", "--vault", str(self.V)).returncode, 0)


@unittest.skipUnless(HAS_LO, "這台沒有 LibreOffice")
class RealLibreOffice(Base):
    """驗收 6：真的轉 PDF、轉圖；重算一份 openpyxl 風格（公式沒有快取值）的 xlsx。"""

    def setUp(self):
        super().setUp()
        self.ws.mkdir(parents=True)

    def test_pdf_and_render(self):
        _produce.docx(self.ws / "報告.docx", ["內湖李進度報告", "第一期完工"], [["期別", "金額"], ["一", "100"]])
        lines = self.ok("pdf", str(self.ws / "報告.docx"))
        self.assertEqual(lines, [f"PDF：{self.ws / '報告.pdf'}（用 LibreOffice 轉的）"])
        self.assertTrue((self.ws / "報告.pdf").read_bytes().startswith(b"%PDF"))
        if not HAS_PDFIUM:
            self.skipTest("這台沒有 pypdfium2")
        lines = self.ok("render", str(self.ws / "報告.docx"), "--pages", "1")
        self.assertEqual(len(lines), 1)
        png = Path(lines[0].split("：", 1)[1])
        self.assertTrue(lines[0].startswith("第 1 頁："))
        self.assertEqual(png.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(png.parent, self.ws)

    def test_recalc(self):
        xlsx = self.ws / "報價.xlsx"
        _produce.xlsx(xlsx, [["木作", 45000], ["油漆", 120000], ["合計", "=B1+B2"]])
        lines = self.ok("recalc", str(xlsx))
        self.assertEqual(lines[0], "重算好了（LibreOffice）：公式 1 個、錯誤 0 個")
        import zipfile
        with zipfile.ZipFile(xlsx) as z:
            sheet = next(n for n in z.namelist() if n.startswith("xl/worksheets/sheet"))
            self.assertIn("165000", z.read(sheet).decode("utf-8"))


class Places(Base):
    def test_pdf_only_workspace_or_output(self):
        raw_file = self.raw / _cards.MEETING
        self.assertEqual(self.refused("pdf", str(raw_file)), f"只收工作區或暫存區裡的檔：{raw_file}")
        self.assertTrue(self.refused("recalc", str(raw_file)).startswith("只收工作區裡的檔"))


class EditFolder(Base):
    """簡化一（jacky 2026-11-05 准）：copy 自己補記清冊、copy --unpack、output save <夾> 驗了蓋回原檔（D-529）。"""

    def unpack(self, target):
        lines = self.ok("copy", str(target), "--unpack")
        self.assertTrue(lines[1].startswith("解開到："), lines)
        return Path(lines[1][len("解開到："):].split("（")[0])

    def save(self, folder):
        return run_kb("output", "save", str(folder), cwd=self.V)

    def test_unlisted_file_copied_and_registered(self):
        fresh = self.raw / "客戶案件" / "大安陳" / "剛放的.docx"
        _ooxml.docx(fresh, [("p", "剛放")])
        lines = self.ok("copy", str(fresh))
        self.assertEqual(Path(lines[0][len("副本："):]).name, "剛放的.docx")
        self.assertIsNotNone(_cards.entry_of(self.V, "客戶案件/大安陳/剛放的.docx"))

    def edit_once(self, src, old, new):
        folder = self.unpack(src)
        doc = folder / "word" / "document.xml"
        doc.write_text(doc.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
        return folder

    def linked_backup(self, turn_id):
        """這一句原檔那行的回合備份（files/_src/…）與 manifest 那行。"""
        row = next(e for e in turn.entries(self.V, turn_id) if e.get("action") == "modify" and e.get("uri"))
        return turn.turn_dir(self.V, turn_id) / "files" / row["path"], row

    def test_two_edits_keep_versions_and_revert_restores(self):
        """D-529：每次蓋回原檔前舊的存成同夾「（版本一、二…）」；回合備份硬連結到版本檔；退回第二句只拿掉版本二。"""
        src = self.raw / _cards.MEETING
        before = src.read_bytes()
        rel = "客戶案件/" + _cards.MEETING.split("/", 1)[1]
        fid = _cards.entry_of(self.V, rel)["id"]
        folder = self.edit_once(src, "討論廚房動線", "討論浴室動線")
        self.assertTrue(Path(str(folder) + ".json").is_file())
        r = self.save(folder)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lines = r.stdout.strip().splitlines()
        self.assertEqual(lines[0], f"已改好 {_cards.MEETING.replace('/', chr(92))}，改之前那份存成"
                                   "「會議紀錄_1（版本一）.docx」（說「退回」可以換回來）")
        self.assertEqual(lines[-1], "回答最後問她一句要不要刪掉之前的版本；她說好才用 kb source-edit trash 刪")
        self.assertNotIn("部件", r.stdout)
        v1 = src.with_name("會議紀錄_1（版本一）.docx")
        self.assertEqual(v1.read_bytes(), before)
        backup, row = self.linked_backup(self.t)
        self.assertTrue(backup.samefile(v1), "回合備份就是版本檔，不多存一份")
        self.assertEqual(row["sha256"], sha(v1))
        first = src.read_bytes()
        with zipfile.ZipFile(src) as z:
            self.assertIn("浴室", z.read("word/document.xml").decode("utf-8"))
        entry = _cards.entry_of(self.V, rel)
        self.assertEqual(entry["id"], fid)
        self.assertNotIn("derived_from", entry)
        self.assertEqual(_cards.entry_of(self.V, rel.replace("會議紀錄_1.docx", v1.name)).get("skip_kind"), "AI 判斷")
        todo = run_kb("cards", "todo", cwd=self.V)
        self.assertNotIn("版本一", todo.stdout + todo.stderr)
        self.assertEqual(list(src.parent.glob(".~kb-*")), [])

        turn.start(self.V, "sid-office", "再改一次")
        r = self.save(self.edit_once(src, "討論浴室動線", "討論陽台動線"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("「會議紀錄_1（版本二）.docx」", r.stdout)
        v2 = src.with_name("會議紀錄_1（版本二）.docx")
        self.assertEqual(v2.read_bytes(), first)
        r = run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(src.read_bytes(), first, "退回第二句：原檔回到第一次改完")
        self.assertFalse(v2.exists())
        self.assertEqual(v1.read_bytes(), before)

    def test_same_turn_twice_reverts_to_before_turn(self):
        """同一句改兩次：版本一、二都是這一句新建的；回合備份只有第一次（改之前那份）；退回原檔回到這句之前、兩份版本檔都拿掉。"""
        src = self.raw / _cards.MEETING
        before = src.read_bytes()
        for old, new in (("討論廚房動線", "討論浴室動線"), ("討論浴室動線", "討論陽台動線")):
            r = self.save(self.edit_once(src, old, new))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        v1, v2 = (src.with_name(f"會議紀錄_1（版本{n}）.docx") for n in "一二")
        self.assertEqual(v1.read_bytes(), before)
        self.assertTrue(v2.is_file())
        backup, _row = self.linked_backup(self.t)
        self.assertTrue(backup.samefile(v1))
        r = run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(src.read_bytes(), before)
        self.assertFalse(v1.exists() or v2.exists())

    def test_version_copy_fails_leaves_nothing(self):
        """存版本檔那步失敗（夾唯讀、磁碟滿）：原檔不動、不留半份版本檔。"""
        import shutil as sh
        from unittest import mock
        from kb._lib import output
        src = self.raw / _cards.MEETING
        before = src.read_bytes()
        folder = self.edit_once(src, "討論廚房動線", "討論浴室動線")
        real = sh.copy2

        def copy2(a, b, *k, **kw):
            if "（版本" in str(b):
                Path(b).write_bytes(b"half")
                raise OSError(28, "磁碟滿")
            return real(a, b, *k, **kw)
        with mock.patch.object(output.shutil, "copy2", side_effect=copy2):
            with self.assertRaises(OSError):
                output.save(self.V, str(folder), None, self.t, str(self.V))
        self.assertEqual(src.read_bytes(), before)
        self.assertEqual(list(src.parent.glob("*（版本*")), [])

    def office_items(self, turn_id):
        r = run_kb("versions", "items", "--turn", turn_id, "--json", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return [it for it in json.loads(r.stdout)["items"] if "會議紀錄_1" in it["what"]]

    def test_items_fold_version_into_original_and_undo(self):
        """OBS 回測：版本檔不單獨列項，併在原檔那項（jacky 2026-11-05 修法一）；退那一項＝原檔換回＋版本檔拿掉。"""
        src = self.raw / _cards.MEETING
        before = src.read_bytes()
        r = self.save(self.edit_once(src, "討論廚房動線", "討論浴室動線"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        got = self.office_items(self.t)
        self.assertEqual(len(got), 1, got)
        self.assertEqual(got[0]["what"], "會議紀錄_1.docx")
        self.assertEqual([Path(v).name for v in got[0]["versions"]], ["會議紀錄_1（版本一）.docx"])
        r = run_kb("versions", "items", "--turn", self.t, cwd=self.V)
        self.assertIn("會議紀錄_1.docx：改了內容（舊的存成版本一）", r.stdout)
        self.assertNotIn("（版本一）.docx：新增", r.stdout)
        r = run_kb("versions", "undo", got[0]["item"], cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(src.read_bytes(), before)
        self.assertFalse(src.with_name("會議紀錄_1（版本一）.docx").exists())

    def test_items_same_turn_twice_one_item(self):
        src = self.raw / _cards.MEETING
        before = src.read_bytes()
        for old, new in (("討論廚房動線", "討論浴室動線"), ("討論浴室動線", "討論陽台動線")):
            r = self.save(self.edit_once(src, old, new))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        got = self.office_items(self.t)
        self.assertEqual(len(got), 1, got)
        r = run_kb("versions", "items", "--turn", self.t, cwd=self.V)
        self.assertIn("（舊的存成版本一、版本二）", r.stdout)
        r = run_kb("versions", "undo", got[0]["item"], cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(src.read_bytes(), before)
        self.assertEqual(list(src.parent.glob("*（版本*")), [])

    def test_version_number_continues_after_gap(self):
        from kb._lib import output
        src = self.raw / _cards.MEETING
        src.with_name("會議紀錄_1（版本二）.docx").write_bytes(b"x")
        self.assertEqual(output.version_name(src), "會議紀錄_1（版本三）.docx")
        self.assertEqual([output._cn(n) for n in (1, 10, 11, 20, 99, 100)], ["一", "十", "十一", "二十", "九十九", "100"])
        from kb._lib import items
        orig = "_src/客戶案件/大安陳/會議紀錄_1.docx"
        self.assertTrue(items._version_of("_src/客戶案件/大安陳/會議紀錄_1（版本十二）.docx", orig))
        for other in ("_src/客戶案件/大安陳/會議紀錄_1（版本控制）.docx", "_src/客戶案件/別的/會議紀錄_1（版本一）.docx",
                      "_src/客戶案件/大安陳/會議紀錄_1（版本一）.xlsx"):
            self.assertFalse(items._version_of(other, orig), other)

    def test_office_style_save_of_version_leaves_backup(self):
        """主管疑慮一之一：Office 存檔是寫新檔再整份換上，連結斷開，回合備份還是改之前那份，退回照常。"""
        import os
        src = self.raw / _cards.MEETING
        before = src.read_bytes()
        r = self.save(self.edit_once(src, "討論廚房動線", "討論浴室動線"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        v1 = src.with_name("會議紀錄_1（版本一）.docx")
        backup, _row = self.linked_backup(self.t)
        tmp = v1.with_name("~存檔中.tmp")
        tmp.write_bytes(b"office saved")
        os.replace(tmp, v1)
        self.assertFalse(backup.samefile(v1))
        self.assertEqual(backup.read_bytes(), before)
        r = run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("沒換回", r.stdout)
        self.assertEqual(src.read_bytes(), before)

    def test_inplace_edit_of_version_is_caught_at_revert(self):
        """主管疑慮一之二：版本檔被原地改寫，硬連結的回合備份跟著變 → 退回前驗 sha256，明講；原檔與版本檔都照留。"""
        src = self.raw / _cards.MEETING
        r = self.save(self.edit_once(src, "討論廚房動線", "討論浴室動線"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = src.read_bytes()
        v1 = src.with_name("會議紀錄_1（版本一）.docx")
        backup, row = self.linked_backup(self.t)
        with open(v1, "r+b") as f:
            f.write(b"PK-changed")
        self.assertNotEqual(sha(backup), row["sha256"], "原地改寫：連在一起的備份跟著變")
        r = run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("沒換回 1 檔：改之前那份（版本檔）之後被直接改過", r.stdout)
        self.assertEqual(src.read_bytes(), after, "備份不對就不拿來蓋")
        self.assertTrue(v1.is_file(), "被改過的版本檔不拿掉")

    def test_sync_folder_or_other_drive_copies(self):
        """主管疑慮二：原檔在 OneDrive 這類同步夾（雲端屬性）或別的磁碟（os.link 失敗）→ 照舊複製一份；退回一樣換得回。
        真的 OneDrive 沒測（會同步到雲端），用屬性判斷。"""
        from unittest import mock
        from kb._lib import output
        for name, patch in (("同步夾", mock.patch.object(turn, "_cloud", return_value=True)),
                            ("別的磁碟", mock.patch.object(turn.os, "link", side_effect=OSError(18, "跨磁碟")))):
            with self.subTest(name):
                t = turn.start(self.V, "sid-office", name)["turn"]
                src = self.raw / _cards.MEETING
                before = src.read_bytes()
                folder = self.edit_once(src, "討論", f"討論{name}")
                with patch:
                    res = output.save(self.V, str(folder), None, t, str(self.V))
                v = src.with_name(Path(res["version"]).name)
                backup, row = self.linked_backup(t)
                self.assertFalse(backup.samefile(v))
                self.assertNotIn("sha256", row)
                self.assertEqual(backup.read_bytes(), before)
                r = run_kb("versions", "revert", cwd=self.V)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(src.read_bytes(), before)
                self.assertFalse(v.exists())

    def test_refusals_leave_original(self):
        src = self.raw / _cards.MEETING
        before = src.read_bytes()
        folder = self.unpack(src)
        doc = folder / "word" / "document.xml"
        doc.write_text(doc.read_text(encoding="utf-8").replace("</w:body>", "<w:p>"), encoding="utf-8")
        r = self.save(folder)
        self.assertEqual(r.returncode, 3)
        self.assertTrue(r.stdout.startswith("改過的 word/document.xml 格式壞了"), r.stdout)
        self.assertEqual(src.read_bytes(), before)
        self.assertEqual(list(src.parent.glob("*（版本*")), [])
        plain = self.ws / "隨便的夾"
        plain.mkdir()
        r = self.save(plain)
        self.assertEqual(r.returncode, 3)
        self.assertTrue(r.stdout.startswith("這個夾不是 kb office copy --unpack 解開的"), r.stdout)
        self.assertEqual([p.name for p in self.ws.glob("*.docx") if "unpacked" in p.name], [], "沒過的不留打包檔")

    def test_open_file_fails_cleanly(self):
        """原檔開在 Word：換上時被擋 →「檔案正開著，改視窗裡那份」、原檔不動、不留版本檔與暫存檔（mock os.replace）。"""
        import os
        from unittest import mock
        from kb._lib import output
        src = self.raw / _cards.MEETING
        before = src.read_bytes()
        folder = self.edit_once(src, "討論廚房動線", "討論浴室動線")
        real = os.replace

        def replace(a, b):
            if Path(b) == src:
                raise PermissionError(13, "開著", str(src))
            return real(a, b)
        with mock.patch.object(os, "replace", side_effect=replace):
            with self.assertRaises(output.Refused) as cm:
                output.save(self.V, str(folder), None, self.t, str(self.V))
        self.assertEqual(str(cm.exception), "檔案正開著，改視窗裡那份")
        self.assertEqual(src.read_bytes(), before)
        self.assertEqual(list(src.parent.glob(".~kb-*")), [])
        self.assertEqual(list(src.parent.glob("*（版本*")), [])

    def test_password_protected_refused(self):
        locked = self.raw / "客戶案件" / "大安陳" / "加密.docx"
        _ooxml.cfb(locked)
        out = self.refused("copy", str(locked), "--unpack")
        self.assertEqual(out, "拿不到副本：這不是 Office 檔（解不開）")

    def excel_save(self, ext, recalc):
        """一份有公式的 Excel：改輸入格 → output.save（recalc 換成假的，不靠這台有沒有 Excel／LibreOffice）。"""
        from unittest import mock
        from kb._lib import output
        src = self.raw / "客戶案件" / "大安陳" / f"報價{ext}"
        _ooxml.xlsx(src, [("工作表", [[("n", "1"), ("f", "A1*2", "2")]])])
        folder = self.unpack(src)
        sheet = folder / "xl" / "worksheets" / "sheet1.xml"
        sheet.write_text(sheet.read_text(encoding="utf-8").replace("<v>1</v>", "<v>5</v>", 1), encoding="utf-8")
        with mock.patch.object(office, "recalc", side_effect=recalc) as fake:
            try:
                return src, output.save(self.V, str(folder), None, self.t, str(self.V)), fake
            except output.Refused as e:
                return src, e, fake

    def test_excel_recalc_errors_refused(self):

        def bad(_vault, _path):
            return {"used": "Excel", "formulas": 1, "errors": [("sheet1.xml", "B1", "#REF!")]}
        src, res, _fake = self.excel_save(".xlsx", bad)
        self.assertEqual(str(res), "重算後有 1 格是錯誤值，沒放：B1（#REF!）")
        with zipfile.ZipFile(src) as z:
            self.assertIn("<v>1</v>", z.read("xl/worksheets/sheet1.xml").decode("utf-8"))
        self.assertEqual(list(src.parent.glob("*（版本*")), [])

    def test_excel_no_tool_saves_with_note(self):
        def none(_vault, _path):
            raise office.Unavailable("這台沒有 Excel 也沒有 LibreOffice\n公式要她打開檔案才會更新")
        src, res, _fake = self.excel_save(".xlsx", none)
        self.assertEqual(res["checked"]["recalc_note"], "公式要她打開檔案才會更新")
        self.assertTrue(src.with_name("報價（版本一）.xlsx").is_file())

    def test_xlsm_not_recalculated(self):
        src, res, fake = self.excel_save(".xlsm", lambda *_a: self.fail("xlsm 不該重算"))
        fake.assert_not_called()
        self.assertEqual(res["checked"]["recalc_note"], office.MACRO_NO_RECALC)
        self.assertTrue(src.with_name("報價（版本一）.xlsm").is_file())

    def test_macro_part_kept(self):
        docm = self.raw / "客戶案件" / "大安陳" / "有巨集.docm"
        with zipfile.ZipFile(self.raw / _cards.MEETING) as z, zipfile.ZipFile(docm, "w") as w:
            for i in z.infolist():
                w.writestr(i, z.read(i.filename))
            w.writestr("word/vbaProject.bin", bytes(range(256)) * 4)
        folder = self.unpack(docm)
        doc = folder / "word" / "document.xml"
        doc.write_text(doc.read_text(encoding="utf-8").replace("討論廚房動線", "討論浴室動線"), encoding="utf-8")
        r = self.save(folder)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with zipfile.ZipFile(docm) as z:
            self.assertEqual(z.read("word/vbaProject.bin"), bytes(range(256)) * 4)


if __name__ == "__main__":
    unittest.main()
