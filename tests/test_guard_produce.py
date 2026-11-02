"""守門（produce 第 3 點、驗收 10；實作回報裁定 1、3）：
- 放寬甲：AI 產出（Z3）是使用者區，指令讀寫照使用者區規則（新檔放行，刪、蓋、改既有內容才擋），OUTPUT_SHELL 與附著 Office 的比對規則都拿掉；
- Z2、Z9 檔案工具寫放行（hook 先備份），指令刪或改既有檔才擋；Z10／Z10b 照舊「使用者說過不讀」；
- 檔案工具（Write／Edit）寫 .system/temp/office/ 底下放行（不備份）；指令寫照擋，.system 其他地方照擋，.. 跳出去照 Z7。"""
import os
import shutil
import unittest
import sys

from tests._guard_fixture import KB, ROOT, make_vault, payload
from kb import guard  # noqa: E402



class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp, cls.V, cls.raw = make_vault()
        os.environ["CLAUDE_PLUGIN_ROOT"] = str(ROOT)
        cls.ws = cls.V / ".system" / "temp" / "office" / "20261022-101010-test"
        cls.ws.mkdir(parents=True)
        (cls.V / "AI 產出" / "a.docx").write_bytes(b"x")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def decide(self, tool, value, cwd=None):
        return guard.decide(payload(tool, value, cwd or self.V))


class ShellOutput(Base):
    def test_scripts_touching_output_pass(self):
        """放寬甲：腳本與轉檔指令碰 AI 產出放行（腳本檔不存在或不在知識庫裡；沒有刪、蓋既有檔的寫法）。"""
        v = self.V.as_posix()
        for tool, cmd in (("Bash", f'node x.js "{v}/AI 產出/a.docx"'),
                          ("Bash", f'python x.py "{v}/AI 產出/a.xlsx"'),
                          ("Bash", 'node build.js "AI 產出/報告/進度報告.docx"'),
                          ("Bash", f'soffice --headless --convert-to pdf "{v}/AI 產出/a.docx"'),
                          ("Bash", 'cd "AI 產出" && node build.js out.docx'),
                          ("Bash", 'node build.js --out="AI 產出/新夾/x.docx"'),
                          ("Bash", "node build.js AI\\ 產出/新夾/x.docx"),
                          ("Bash", 'OUT="AI 產出/x.docx" node build.js'),
                          ("PowerShell", 'node build.js "AI 產出\\新夾\\x.docx"'),
                          ("Bash", f'python x.py "{v}/AI 產出/a.xlsx" && echo done'),
                          ("Bash", f'python "{KB}" output save "{v}/AI 產出/a.docx" --to "AI 產出/b.docx"; echo x')):
            with self.subTest(cmd=cmd):
                d = self.decide(tool, cmd)
                self.assertEqual(d.decision, "pass", d)
                self.assertEqual(d.ledger_rows, [])

    def test_known_read_only_commands_are_reads(self):
        """D-186 補：已知只讀指令（cat、ls、Get-Content）的參數當讀放行。"""
        v = self.V.as_posix()
        for tool, cmd in (("Bash", f'cat "{v}/AI 產出/a.docx"'), ("Bash", 'ls "AI 產出"'), ("Bash", 'cat "AI 產出"/*.docx'),
                          ("PowerShell", f'Get-Content "{v}/AI 產出/a.docx"'), ("PowerShell", f'Get-Content -Path:"{v}/AI 產出/a.docx"')):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.decide(tool, cmd).decision, "pass")

    def test_single_kb_call_still_allowed(self):
        v = self.V.as_posix()
        d = self.decide("Bash", f'python "{KB}" output save "{self.ws.as_posix()}/a.xlsx" --to "AI 產出/報價/a.xlsx"')
        self.assertEqual(d.decision, "allow")
        d = self.decide("Bash", f'python "{KB}" office pdf "{v}/AI 產出/a.docx"')
        self.assertEqual(d.decision, "allow")

    def test_read_tool_on_output_allowed(self):
        self.assertEqual(self.decide("Read", self.V / "AI 產出" / "a.docx").decision, "allow")
        d = self.decide("Write", self.V / "AI 產出" / "草稿（草稿）.md")
        self.assertEqual((d.decision, d.zone), ("allow", "Z3"))

    def test_other_shell_unaffected(self):
        self.assertEqual(self.decide("Bash", "node --version").decision, "pass")
        self.assertEqual(self.decide("Bash", f'python "{self.ws.as_posix()}/make.py"').decision, "pass")


class SourceReason(Base):
    def test_copy_original_into_vault_denied_with_office_copy(self):
        cmd = f'cp "{self.raw.as_posix()}/客戶案件/a.txt" "{self.V.as_posix()}/.system/temp/x.txt"'
        d = self.decide("Bash", cmd)  # 目的地在 .system（willy 自己的區）
        self.assertEqual((d.decision, d.zone, d.reason_code), ("deny", "Z7", "willy"))
        d = self.decide("Write", self.raw / "客戶案件" / "a.txt")  # 放寬甲：Z9 檔案工具寫放行（hook 先備份）
        self.assertEqual((d.decision, d.zone), ("allow", "Z9"))
        d = self.decide("Bash", f'cp "{self.V.as_posix()}/AI 產出/a.docx" "{self.raw.as_posix()}/客戶案件/a.txt"')
        self.assertEqual((d.decision, d.reason_code), ("deny", "overwrite"))

    def test_entity_file_content_edit_hint(self):
        d = self.decide("Write", self.V / "案子" / "信義王" / "合約.docx")  # 放寬甲：檔案工具寫放行
        self.assertEqual((d.decision, d.zone), ("allow", "Z2"))
        d = self.decide("Bash", f'echo x > "{self.V.as_posix()}/案子/信義王/合約.docx"')  # 指令改既有檔：content，教用 Edit 或 kb office
        self.assertEqual((d.decision, d.zone, d.reason_code), ("deny", "Z2", "content"))
        self.assertIn("kb office", d.reason)

    def test_excluded_keeps_its_reason(self):
        d = self.decide("Write", self.raw / "行政" / "舊檔" / "o.doc")
        self.assertEqual((d.decision, d.zone), ("deny", "Z10"))
        self.assertEqual(d.reason, guard.ZONES["Z10"]["write"][2].replace("{alias}", "行政"))
        self.assertIn("使用者說過不讀", d.reason)
        self.assertNotIn("office", d.reason)


class Workspace(Base):
    """實作回報裁定 1。"""

    def test_file_tools_write_workspace_allowed(self):
        for tool in ("Write", "Edit", "MultiEdit"):
            for target in (self.ws / "build.js", self.ws / "合約_unpacked" / "word" / "document.xml",
                           self.V / ".system" / "temp" / "office" / "x.py"):
                with self.subTest(tool=tool, target=target):
                    d = self.decide(tool, target)
                    self.assertEqual((d.decision, d.zone, d.ledger_rows), ("allow", "Z7", []))
                    self.assertNotIn(d.zone, ("Z1", "Z3", "Z5"), "不經回合備份")

    def test_relative_and_dotdot(self):
        d = self.decide("Write", ".system/temp/office/20261022-101010-test/a.py")
        self.assertEqual(d.decision, "allow")
        for target in (self.ws / ".." / ".." / ".." / "profile.json", self.ws / ".." / ".." / "x.py",
                       self.V / ".system" / "temp" / "officex" / "a.py", self.V / ".system" / "temp" / "office",
                       self.V / ".system" / "temp" / "a.py", self.V / ".system" / "inventory.json"):
            with self.subTest(target=target):
                d = self.decide("Write", target)
                self.assertEqual((d.decision, d.zone, d.reason_code), ("deny", "Z7", "willy"))

    def test_notebook_and_shell_still_denied(self):
        d = self.decide("NotebookEdit", self.ws / "a.ipynb")
        self.assertEqual((d.decision, d.zone), ("deny", "Z7"))
        for cmd in (f'echo x > "{self.ws.as_posix()}/a.py"', f'cp /tmp/a.py "{self.ws.as_posix()}/a.py"'):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.decide("Bash", cmd).decision, "deny")

    def test_read_workspace_allowed(self):
        self.assertEqual(self.decide("Read", self.ws / "a.png").decision, "allow")

    def test_junction_out_of_workspace_denied(self):
        if os.name != "nt":
            self.skipTest("junction 只在 Windows")
        import subprocess
        link = self.ws / "跳出去"
        target = self.tmp / "外面"
        target.mkdir(exist_ok=True)
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        if r.returncode != 0:
            self.skipTest("建不了 junction")
        try:
            d = self.decide("Write", link / "a.py")
            self.assertNotEqual(d.reason, "工作區", "連結跳出工作區的不算工作區（寫到知識庫外走一般流程）")
            self.assertFalse(guard.in_workspace(guard.normalize(str(link / "a.py"), None),
                                                guard.normalize(str(self.V), None)))
        finally:
            os.rmdir(link)



class SecurityReview(Base):
    """收尾 security-review 的修正：_lo_profile 不算工作區；路徑中間的段結尾有空白或點不算；PowerShell 的 -Param:值 與 /out:值；
    _touches_output 出錯一律擋。"""

    def test_lo_profile_not_writable(self):
        for target in (self.V / ".system/temp/office/_lo_profile/user/registrymodifications.xcu",
                       self.V / ".system/temp/office/_lo_profile/user/basic/Standard/Module1.xba"):
            with self.subTest(target=target):
                d = self.decide("Write", target)
                self.assertEqual((d.decision, d.zone), ("deny", "Z7"))

    def test_trailing_space_or_dot_segment_not_workspace(self):
        v = self.V.as_posix()
        for target in (f"{v}/.system /temp/office/t/x.js", f"{v}/.system/temp. /office/t/x.js",
                       f"{v}/.system/temp/office./t/x.js"):
            with self.subTest(target=target):
                self.assertNotEqual(self.decide("Write", target).reason, "工作區")

    def test_param_colon_forms(self):
        v = self.V.as_posix()
        for tool, cmd in (("PowerShell", 'node b.js -Out:"AI 產出/x.docx"'),
                          ("Bash", 'tool.exe /out:"AI 產出/x.docx"')):
            with self.subTest(cmd=cmd):
                d = self.decide(tool, cmd)
                self.assertEqual(d.decision, "pass", d)  # 放寬甲：-Out:值、/out:值是新檔或程式自己的事，不再因為碰 AI 產出就擋



class OpenFile(Base):
    """開檔與Office一起改（D-514、D-515）：開文件、資料夾、網址照讀判；導向照寫判；開程式照內層判；知識庫與來源裡的程式擋 run_file。"""

    def setUp(self):
        self.v, self.r = str(self.V), str(self.raw)

    def ps(self, cmd):
        return self.decide("PowerShell", cmd.replace("<V>", self.v).replace("<RAW>", self.r))

    def bash(self, cmd):
        return self.decide("Bash", cmd.replace("<V>", self.V.as_posix()).replace("<RAW>", self.raw.as_posix()))

    def test_open_documents_pass(self):
        for tool, cmd in (("PowerShell", "Start-Process '<V>\\AI 產出\\a.docx'"),
                          ("PowerShell", "Invoke-Item '<V>\\AI 產出\\a.docx'"),
                          ("PowerShell", "explorer '<V>\\AI 產出'"),
                          ("PowerShell", "Start-Process 'AI 產出\\x.xlsx'"),
                          ("PowerShell", "Start-Process '<V>\\系統\\客戶設定檔.md'"),
                          ("PowerShell", "Start-Process '<RAW>\\客戶案件\\a.txt'"),
                          ("PowerShell", "Start-Process 'https://example.com'"),
                          ("PowerShell", "Start-Process '<V>\\AI 產出\\a.docx' -Verb Print -Wait"),
                          ("Bash", 'cmd //c start "" "<V>/AI 產出/a.docx"'),
                          ("Bash", 'start "<V>/AI 產出/a.docx"'),
                          ("PowerShell", "explorer '<RAW>'")):
            with self.subTest(cmd=cmd):
                d = self.ps(cmd) if tool == "PowerShell" else self.bash(cmd)
                self.assertEqual((d.decision, d.ledger_rows), ("pass", []))

    def test_new_window_for_claude_pass(self):
        """#18：開新視窗跑 claude。"""
        for cmd in ("Start-Process powershell -ArgumentList '-NoExit','-Command','claude --name 問答測試 --plugin-dir C:\\x'",
                    "Start-Process powershell -ArgumentList '-NoExit','-Command','claude --name t' -WorkingDirectory '<V>'"):
            with self.subTest(cmd=cmd):
                self.assertEqual(self.ps(cmd).decision, "pass")

    def test_redirect_is_write(self):
        for cmd, zone, code in (
                ("Start-Process powershell -ArgumentList '-NoExit' -RedirectStandardOutput '<V>\\x.txt'", "", ""),  # 新檔：放行
                ("Start-Process powershell -ArgumentList '-NoExit' -RedirectStandardError '<V>\\AI 產出\\a.docx'", "Z3", "content"),
                ("Start-Process powershell -ArgumentList '-NoExit' -RedirectStandardOutput '<RAW>\\客戶案件\\a.txt'", "Z9",
                 "content")):
            with self.subTest(cmd=cmd):
                d = self.ps(cmd)
                self.assertEqual((d.decision, d.zone, d.reason_code), ("deny", zone, code) if code else ("pass", "", ""))

    def test_program_judged_like_direct(self):
        outer = self.ps("Start-Process powershell -ArgumentList '-Command','Remove-Item ''<V>\\系統\\x.md'''")
        direct = self.ps("powershell -Command \"Remove-Item '<V>\\系統\\x.md'\"")
        self.assertEqual(direct.decision, "deny")
        self.assertEqual((outer.decision, outer.zone, outer.reason_code), (direct.decision, direct.zone, direct.reason_code))
        self.assertEqual(self.ps("Start-Process cmd -ArgumentList '/c','del \"<V>\\AI 產出\\a.docx\"'").decision, "deny")
        self.assertEqual(self.bash('start "" powershell -Command "Remove-Item \'<V>/系統/x.md\'"').decision, "deny")

    def test_run_file_in_vault_or_source(self):
        for tool, cmd, zone in (("PowerShell", "Start-Process '<V>\\AI 產出\\x.bat'", "Z3"),
                                ("PowerShell", "Start-Process '<V>\\AI 產出\\x.ps1'", "Z3"),
                                ("PowerShell", "Start-Process '<V>\\x.cmd'", "Z8"),
                                ("PowerShell", "Start-Process '<V>\\AI 產出\\x.docm'", "Z3"),
                                ("PowerShell", "Start-Process '<RAW>\\客戶案件\\run.exe'", "Z9"),
                                ("PowerShell", "Invoke-Item '<V>\\AI 產出\\x.lnk'", "Z3"),
                                ("PowerShell", "start '<V>\\AI 產出\\x.bat'", "Z3"),
                                ("PowerShell", "ii '<V>\\AI 產出\\*'", "Z3"),
                                ("PowerShell", "Start-Process '<V>\\AI 產出\\a.docx' -Verb RunAs", "Z3"),
                                ("Bash", 'cmd //c start "" "<V>/AI 產出/x.bat"', "Z3")):
            with self.subTest(cmd=cmd):
                d = self.ps(cmd) if tool == "PowerShell" else self.bash(cmd)
                self.assertEqual((d.decision, d.zone, d.reason_code, d.reason),
                                 ("deny", zone, "run_file", guard.RUN_FILE[2]))
                self.assertEqual(len(d.ledger_rows), 1)

    def test_read_column_still_applies(self):
        d = self.ps("Start-Process '<RAW>\\行政\\薪資\\s.xlsx'")
        self.assertEqual((d.decision, d.zone, d.reason_code), ("deny", "Z10", "excluded"))
        pw = self.raw / "客戶案件" / "密碼.txt"
        pw.write_text("x", encoding="utf-8")
        try:
            self.assertEqual(self.ps("Start-Process '<RAW>\\客戶案件\\密碼.txt'").reason_code, "credential")
            self.assertEqual(self.ps("explorer '<RAW>'").decision, "pass", "開夾不是讀整夾")
            self.assertEqual(self.ps("explorer '<RAW>'; Get-ChildItem -Recurse '<RAW>' | Get-Content").decision, "deny",
                             "同一個夾另一段真的讀，照走訪")
        finally:
            pw.unlink()

    def test_unparsed_and_chains(self):
        for cmd in ("Start-Process $f", "Start-Process powershell -ArgumentList $a", "Start-Process (Get-Item x)"):
            with self.subTest(cmd=cmd):  # 放寬甲 U5：看不出開什麼、整句沒有刪或改的動詞 → 放行（不再一律 unparsed）
                self.assertEqual(self.ps(cmd).decision, "pass")
        d = self.ps("Start-Process '<V>\\AI 產出\\a.docx'; Remove-Item '<V>\\AI 產出\\a.docx'")
        self.assertEqual((d.decision, d.reason_code), ("deny", "delete"))
        d = self.ps("cmd /c start '<V>\\AI 產出\\a.docx' '&' del '<V>\\系統\\x.md'")
        self.assertEqual(d.decision, "deny")
        d = self.ps("Get-ChildItem '<V>\\AI 產出' | Invoke-Item")
        self.assertEqual(d.decision, "pass", "要開的從管線前面來：看不出會開什麼，但整句沒有刪或改的動詞")

    def test_review_bypasses_denied(self):
        """收尾 code-review high：殼字串裡的開檔、參數裡點名的腳本、cwd 推不出來、cmd 再認引號、open 的旗標。"""
        bat = self.raw / "客戶案件" / "evil.bat"
        bat.write_text("x", encoding="utf-8")
        try:
            for tool, cmd in (("PowerShell", "powershell -Command \"Start-Process '<RAW>\\客戶案件\\evil.bat'\""),
                              ("Bash", "powershell -c \"Start-Process '<RAW>/客戶案件/evil.bat'\""),
                              ("PowerShell", "pwsh -c \"saps '<RAW>\\客戶案件\\evil.bat'\""),
                              ("PowerShell", "Start-Process cmd '/c','<RAW>\\客戶案件\\evil.bat'"),
                              ("PowerShell", "Start-Process cmd -ArgumentList '/c <RAW>\\客戶案件\\evil.bat'"),
                              ("PowerShell", "Start-Process wscript -ArgumentList '<RAW>\\客戶案件\\evil.wsf'"),
                              ("PowerShell", "Start-Process powershell \"-c & '<RAW>\\客戶案件\\evil.bat'\""),
                              ("PowerShell", "cd $env:X; Start-Process .\\evil.bat"),
                              ):
                with self.subTest(cmd=cmd):
                    d = self.ps(cmd) if tool == "PowerShell" else self.bash(cmd)
                    self.assertEqual(d.decision, "deny")
        finally:
            bat.unlink()
        d = self.ps("Invoke-Item '<RAW>\\客戶案件\\a.txt','C:\\Windows\\notepad.exe'")
        self.assertNotEqual(d.reason_code, "run_file", "文件目標不算程式檔")

    def test_round1_fixes(self):
        """測試第 1 輪裁定 9、10、11。"""
        case = self.raw / "客戶案件"
        pw = case / "深" / "密碼.txt"  # 測試報告 #1：密碼檔在子夾，萬用字元展開到夾、走訪才找得到
        pw.parent.mkdir(exist_ok=True)
        pw.write_text("x", encoding="utf-8")
        self.addCleanup(shutil.rmtree, pw.parent, True)
        try:  # 9：同句別段讀到的夾不給開夾豁免
            for tool, cmd in (("Bash", "explorer <RAW>/客戶案件 ; grep -r x <RAW>/客戶案件/*"),
                              ("PowerShell", "explorer '<RAW>\\客戶案件'; Get-ChildItem -Recurse '<RAW>\\客戶案件\\*' | Get-Content")):
                with self.subTest(cmd=cmd):
                    d = self.ps(cmd) if tool == "PowerShell" else self.bash(cmd)
                    self.assertEqual((d.decision, d.reason_code), ("deny", "credential_inside"))
            self.assertEqual(self.bash("explorer <RAW>/客戶案件").decision, "pass")
            d = self.ps("explorer '<RAW>'; Get-Content '<RAW>\\客戶案件\\a.txt'")
            self.assertEqual(d.decision, "deny", "開的夾底下有別段讀的路徑：照一般規則（Z10b）")
        finally:
            pw.unlink()
        w = case / "onlyw.wsf"  # 10
        w.write_text("x", encoding="utf-8")
        try:
            d = self.ps("cd '<RAW>\\客戶案件'; Start-Process onlyw")
            self.assertEqual((d.decision, d.zone, d.reason_code), ("deny", "Z9", "run_file"))
        finally:
            w.unlink()
        for tool, cmd, zone in (("PowerShell", "C:\\Windows\\explorer.exe '<V>\\AI 產出\\x.bat'", "Z3"),  # 11
                                ("PowerShell", 'C:\\Windows\\System32\\cmd.exe /c start "" "<V>\\AI 產出\\x.bat"', "Z3"),
                                ("Bash", '/c/Windows/System32/cmd.exe //c start "" "<V>/AI 產出/x.bat"', "Z3"),
                                ("PowerShell", "& '<V>\\AI 產出\\explorer.exe' '<V>\\AI 產出\\a.docx'", "Z3")):
            with self.subTest(cmd=cmd):
                d = self.ps(cmd) if tool == "PowerShell" else self.bash(cmd)
                self.assertEqual((d.decision, d.zone, d.reason_code), ("deny", zone, "run_file"))
        self.assertEqual(self.ps("C:\\Windows\\explorer.exe '<V>\\AI 產出\\a.docx'").decision, "pass")
        self.assertEqual(self.ps('C:\\Windows\\System32\\cmd.exe /c start "" "<V>\\AI 產出\\a.docx"').decision, "pass")

    def test_com_open_still_denied(self):
        d = self.ps("$w=[Runtime.InteropServices.Marshal]::GetActiveObject('Word.Application'); "
                    "$w.Documents.Open('<V>\\AI 產出\\a.docx')")
        self.assertEqual(d.decision, "pass", d)  # 放寬甲：開文件不是寫（OUTPUT_SHELL 拿掉）

    def test_com_attach_pass(self):
        """D-515：附著到開著的 Office 改，守門不表態。"""
        for tool, cmd in (
                ("PowerShell", "$w=[Runtime.InteropServices.Marshal]::GetActiveObject('Word.Application'); "
                               "$d=$w.Documents | Where-Object { $_.Name -eq 'a.docx' }; $d.Content.InsertAfter('x'); $d.Save()"),
                ("PowerShell", "$x=[Runtime.InteropServices.Marshal]::GetActiveObject('Excel.Application'); "
                               "$b=$x.Workbooks | Where-Object { $_.FullName -eq '<RAW>\\客戶案件\\a.xlsx' }; "
                               "$b.Worksheets.Item(1).Range('A1').Value2 = '下週交'"),
                ("Bash", "python -c \"import win32com.client as c; w=c.GetActiveObject('Word.Application'); "
                         "d=[x for x in w.Documents if x.FullName==r'<V>\\AI 產出\\a.docx'][0]; d.Content.InsertAfter('x')\""),
                ("PowerShell", "$p=[Runtime.InteropServices.Marshal]::GetActiveObject('PowerPoint.Application'); "
                               "$p.ActivePresentation.Slides.Item(1).Shapes.Item(1).TextFrame.TextRange.Text = '下週交'")):
            with self.subTest(cmd=cmd):
                d = self.ps(cmd) if tool == "PowerShell" else self.bash(cmd)
                self.assertEqual(d.decision, "pass")

    def test_com_attach_fullname_compare(self):
        """裁定 29 的舊案例：放寬甲拿掉 OUTPUT_SHELL 與附著 Office 的比對規則後，AI 產出是使用者區，指令只擋刪（Remove-Item）、
        蓋、改既有檔；方法呼叫（.Delete()、.SaveAs 等）看不出是刪檔，放行（spec U2 只認動詞）。"""
        word = "$w=[Runtime.InteropServices.Marshal]::GetActiveObject('Word.Application'); "
        loop = word + "foreach ($x in $w.Documents) { if ($x.FullName -eq '<V>\\AI 產出\\a.docx') { $x.Content.InsertAfter('x'); $x.Save()"
        cases = (
            ("a", "PowerShell", loop + " } }", "pass"),
            ("b", "PowerShell", word + "$d=$w.Documents | Where-Object { $_.FullName -eq '<V>\\AI 產出\\a.docx' }; "
                                       "$d.Content.InsertAfter('x'); $d.Save()", "pass"),
            ("c", "PowerShell", "$e=[Runtime.InteropServices.Marshal]::GetActiveObject('Excel.Application'); "
                                "$b=$e.Workbooks | Where-Object { $_.FullName -ieq '<V>\\AI 產出\\a.xlsx' }; "
                                "$b.Worksheets.Item(1).Range('A1').Value2 = '下週交'; $b.Save()", "pass"),
            ("c", "PowerShell", "$p=[Runtime.InteropServices.Marshal]::GetActiveObject('PowerPoint.Application'); "
                                "$q=$p.Presentations | Where-Object { $_.FullName -like '<V>\\AI 產出\\a.pptx' }; "
                                "$q.Slides.Item(1).Shapes.Item(1).TextFrame.TextRange.Text = '下週交'; $q.Save()", "pass"),
            ("d", "PowerShell", "python -c \"import win32com.client as c; w=c.GetActiveObject('Word.Application'); "
                                "d=[x for x in w.Documents if x.FullName == r'<V>\\AI 產出\\a.docx'][0]; d.Content.InsertAfter('x'); d.Save()\"",
             "pass"),
            ("e", "PowerShell", loop + "; $x.SaveAs('<V>\\AI 產出\\y.docx') } }", "deny"),
            ("f", "PowerShell", loop + " } }; $w.Documents.Open('<V>\\AI 產出\\a.docx')", "deny"),
            ("g", "PowerShell", "if ('<V>\\AI 產出\\a.docx' -eq $a) { Remove-Item '<V>\\AI 產出\\a.docx' }", "deny"),
            ("沒附著", "PowerShell", "if ($x.FullName -eq '<V>\\AI 產出\\a.docx') { $x.Save() }", "deny"),
            ("左邊", "PowerShell", word + "foreach ($x in $w.Documents) { if ('<V>\\AI 產出\\a.docx' -eq $x.FullName) { $x.Save() } }", "deny"),
            ("比對外", "PowerShell", word + "$f='<V>\\AI 產出\\a.docx'; $d=$w.Documents | Where-Object { $_.FullName -eq $f }; $d.Save()", "deny"),
            ("SaveCopyAs", "PowerShell", "$e=[Runtime.InteropServices.Marshal]::GetActiveObject('Excel.Application'); "
                                         "$b=$e.Workbooks | Where-Object { $_.FullName -eq '<V>\\AI 產出\\a.xlsx' }; $b.SaveCopyAs('C:\\x\\b.xlsx')", "deny"),
            ("Export", "PowerShell", loop + "; $x.ExportAsFixedFormat('C:\\x\\a.pdf', 17) } }", "deny"),
            ("Add", "PowerShell", loop + " } }; $w.Documents.Add()", "deny"),
            ("寫入字", "PowerShell", loop + " } }; Copy-Item 'C:\\x\\b.docx' 'C:\\x\\c.docx'", "deny"),
            ("導向", "PowerShell", loop + " } } > 'C:\\x\\log.txt'", "deny"),
        )
        gci = word + "Get-ChildItem '<V>' -Recurse | Where-Object { $_.FullName -eq '<V>\\AI 產出\\a.docx' } | ForEach-Object { "
        loop2 = word + "foreach ($x in $w.Documents) { if ($x.FullName -eq '<V>\\AI 產出\\a.docx') { "
        cases += tuple(("review", "PowerShell", cmd, "deny") for cmd in (  # 收尾 API code review：比對拿到的物件拿去刪、搬、跑
            gci + "$_.Delete() }",
            gci + "$_.MoveTo('C:\\x\\a.docx') }",
            gci + "& $_.FullName }",
            gci + "$_.Attributes = 'Hidden' }",
            word + "$f = Get-ChildItem '<V>' -Recurse | Where-Object { $_.FullName -eq '<V>\\AI 產出\\a.ps1' }; . $f.FullName",
            loop2 + "$x.Close(); [System.IO.File]::Delete($x.FullName) } }",
            loop2 + "$x.Close(); [IO.FileInfo]::new($x.FullName).Delete() } }",
            loop2 + "$w.WordBasic.Kill($x.FullName) } }",
            loop2 + "$w.Run('Evil') } }",
            loop2 + "$w.Documents.OpenNoRepairDialog('<V>\\AI 產出\\b.docx') } }",
            word + "$q=$w.Documents | Where-Object { $_.FullName -eq '<V>\\AI 產出\\a.docx' }; $q.Range().ExportFragment('C:\\x\\f.docx', 0)",
            word + "Get-ChildItem '<V>' -Recurse | ? { $_.FullName -like '<V>\\AI 產出\\*' } | % { $_.Delete() }",
            word + "foreach ($x in $w.Documents) { if ($x.FullName -like '<V>\\AI 產出\\*') { $x.Save() } }",
            "# GetActiveObject('Word.Application')\nGet-ChildItem '<V>' -Recurse | Where-Object { $_.FullName -eq '<V>\\AI 產出\\a.docx' } | % { $_.Delete() }",
            "$null='GetActiveObject(\"Word.Application\")'; Get-ChildItem '<V>' -Recurse | Where-Object { $_.FullName -eq '<V>\\AI 產出\\a.docx' } | % { $_.Delete() }",
        ))
        cases += (  # 裁定 31：寫進文件的字不算寫入動詞；文件裡的 Add 不擋，開新檔的 Add 照擋
            ("引號內 copy", "PowerShell", loop2 + "$x.Content.InsertAfter('請 copy 這段'); $x.Save() } }", "pass"),
            ("引號內 zip", "PowerShell", loop2 + "$x.Content.InsertAfter('zip code'); $x.Save() } }", "pass"),
            ("Tables.Add", "PowerShell", loop2 + "[void]$x.Tables.Add($x.Range(0,0), 2, 2); $x.Save() } }", "pass"),
            ("Comments.Add", "PowerShell", loop2 + "[void]$x.Comments.Add($x.Paragraphs.Item(1).Range, '請確認'); $x.Save() } }", "pass"),
            ("Workbooks.Add", "PowerShell", "$e=[Runtime.InteropServices.Marshal]::GetActiveObject('Excel.Application'); "
                                            "$b=$e.Workbooks | Where-Object { $_.FullName -eq '<V>\\AI 產出\\a.xlsx' }; [void]$e.Workbooks.Add(); $b.Save()",
             "deny"),
            ("引號外 copy", "PowerShell", loop2 + "$x.Save() } }; copy 'C:\\x\\a' 'C:\\x\\b'", "deny"),
        )
        for name, tool, cmd, want in cases:
            with self.subTest(case=name, cmd=cmd):
                d = self.ps(cmd) if tool == "PowerShell" else self.bash(cmd)
                expect = "deny" if name == "g" or ". $f.FullName" in cmd else "pass"  # dot-source 變數：照看不出內容，擋
                self.assertEqual(d.decision, expect, d)
                if name == "g":
                    self.assertEqual((d.zone, d.reason_code), ("Z3", "delete"))


class OpenFileHook(unittest.TestCase):
    """驗收 15、16：hook 對附著改不印 deny、不備份；製卡助手開檔照 agent_scope 擋。"""

    SID = "sid-open"

    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        from kb._lib import batches, turn
        turn.start(self.V, self.SID, "第三段改成下週交")
        batches.agent_start(self.V, self.SID, "agent-1")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_hook(self, cmd, **extra):
        import json as _json
        import subprocess as _sp
        data = dict(payload("PowerShell", cmd, self.V), session_id=self.SID, **extra)
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))
        return _sp.run([sys.executable, str(ROOT / "hooks" / "guard.py")], input=_json.dumps(data, ensure_ascii=False),
                       capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT), env=env)

    def files_under(self, *parts):
        root = self.V.joinpath(*parts)
        return sorted(str(p) for p in root.rglob("*") if p.is_file()) if root.exists() else []

    def test_attach_no_deny_no_backup(self):
        before = (self.files_under(".system", "turns"), self.files_under(".system", "versions"))
        r = self.run_hook("$w=[Runtime.InteropServices.Marshal]::GetActiveObject('Word.Application'); "
                          "$d=$w.Documents | Where-Object { $_.Name -eq 'a.docx' }; $d.Content.InsertAfter('x'); $d.Save()")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn('"deny"', r.stdout)
        self.assertEqual((self.files_under(".system", "turns"), self.files_under(".system", "versions")), before)

    def test_card_maker_open_denied(self):
        from kb._lib import batches
        import json as _json
        r = self.run_hook(f"Start-Process '{self.V}\\AI 產出\\x.docx'", agent_id="agent-1", agent_type=batches.AGENT)
        out = _json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        rows = (self.V / ".system" / "ledger.tsv").read_text(encoding="utf-8")
        self.assertIn("agent_scope", rows)


class FreshVault(unittest.TestCase):
    """測試後修正裁定 12（H-1）：還沒有 .system/temp/office/ 的新庫，第一次寫工作區也放行；officeX、.. 照擋。"""

    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        os.environ["CLAUDE_PLUGIN_ROOT"] = str(ROOT)
        self.assertFalse((self.V / ".system" / "temp").exists())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def decide(self, tool, value):
        return guard.decide(payload(tool, value, self.V))

    def test_first_write_allowed(self):
        for target in (self.V / ".system/temp/office/20261022-101010-test/build.js",
                       self.V / ".system/temp/office/20261022-101010-test/sub/a.py"):
            with self.subTest(target=target):
                d = self.decide("Write", target)
                self.assertEqual((d.decision, d.zone, d.reason), ("allow", "Z7", "工作區"))

    def test_lookalikes_still_denied(self):
        for target in (self.V / ".system/temp/officeX/a.js", self.V / ".system/temp/office/../x.js",
                       self.V / ".system/temp/office", self.V / ".system/temp/office/_lo_profile/x.xcu"):
            with self.subTest(target=target):
                self.assertEqual(self.decide("Write", target).decision, "deny")

    def test_kb_guard_decide_cli(self):
        import json as _json
        import subprocess as _sp
        r = _sp.run([sys.executable, str(KB), "guard", "decide", "--tool", "Write", "--path",
                     str(self.V / ".system/temp/office/20261022-101010-test/build.js"), "--json"],
                    capture_output=True, text=True, encoding="utf-8", cwd=str(self.V))
        self.assertEqual(_json.loads(r.stdout)["decision"], "allow")


if __name__ == "__main__":
    unittest.main()
