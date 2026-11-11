"""_lib/cmdparse：抽路徑、判寫入、判單一 kb.py 呼叫。"""
import shutil
import unittest

from tests._guard_fixture import ROOT, SCRIPTS, make_vault  # noqa: F401
from kb._lib import cmdparse, paths  # noqa: E402

CWD = "C:/x/vault"
PLUGIN = str(ROOT)


def n(p):
    return paths.normalize(p, CWD)


class ExtractPaths(unittest.TestCase):
    def test_quoted_chinese_path_with_space(self):
        got = cmdparse.extract_paths('cat "C:/x/vault/暫存區/報告 v1.md"', CWD)
        self.assertIn(n("C:/x/vault/暫存區/報告 v1.md"), got)

    def test_git_bash_path(self):
        got = cmdparse.extract_paths("cat /c/x/raw/行政/薪資/s.xlsx", CWD)
        self.assertIn(n("C:/x/raw/行政/薪資/s.xlsx"), got)

    def test_backslash_path(self):
        got = cmdparse.extract_paths("type C:\\x\\raw\\行政\\薪資\\s.xlsx", CWD)
        self.assertIn(n("C:/x/raw/行政/薪資/s.xlsx"), got)

    def test_dot_and_dotdot_are_paths(self):
        """骨架與來源登記第三輪 S1：不帶斜線的 . 與 .. 也當路徑抽出來，經區判斷（grep -r X .. 要走 Z10b）。"""
        tmp, V, _raw = make_vault()
        try:
            self.assertIn(paths.normalize(str(tmp), None), cmdparse.extract_paths("grep -r X ..", str(V)))
            self.assertIn(paths.normalize(str(V), None), cmdparse.extract_paths("ls .", str(V)))
            self.assertIn(paths.normalize(str(tmp), None), cmdparse.extract_paths("cd 暫存區 && cat ../..", str(V)))
            self.assertEqual(cmdparse.extract_paths("echo a.b", str(V)), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_write_words_round8_additions(self):
        """骨架與來源登記第八輪：find -delete、shred、unlink、Tee-Object 等是寫入。"""
        for cmd in ("find C:/x -delete", "shred C:/x/a.txt", "unlink C:/x/a.txt", "Get-Content a | Tee-Object -FilePath C:/x/a.txt",
                    "Set-Content C:/x/a.txt x", "Out-File -FilePath C:/x/a.txt", "robocopy a b", "xcopy a b /s", "rsync -a a b",
                    "Remove-Item a", "Move-Item a b", "Copy-Item a b", "cp.exe a b", "sed -E -i s/a/b/ x.md"):
            with self.subTest(cmd=cmd):
                self.assertTrue(cmdparse.is_write(cmd), cmd)
        for cmd in ("cat C:/x/a.txt", "find C:/x -name a", "git status", "echo unlinked"):
            with self.subTest(cmd=cmd):
                self.assertFalse(cmdparse.is_write(cmd), cmd)

    def test_bare_filename_token_is_a_path_when_command_writes(self):
        """第八輪驗收 73：cp /tmp/a 新檔.md 的 新檔.md 要抽成路徑（寫入指令裡像檔名的裸 token）。"""
        tmp, V, _raw = make_vault()
        try:
            self.assertIn(paths.normalize(str(V / "新檔.md"), None), cmdparse.extract_paths("cp /tmp/a 新檔.md", str(V)))
            self.assertIn(paths.normalize(str(V / "新檔.md"), None), cmdparse.extract_paths("echo x > 新檔.md", str(V)))
            self.assertNotIn(paths.normalize(str(V / "notes.txt"), None), cmdparse.extract_paths("grep x notes.txt", str(V)))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_bare_token_existing_under_cwd_or_known_extension(self):
        """第九輪 Z2／Z4：寫入指令裡效用 cwd 下存在的裸夾名或檔名（沒副檔名）算路徑；不存在的裸 token 要已知副檔名才算新檔。"""
        tmp, V, _raw = make_vault()
        try:
            v = str(V)
            self.assertIn(paths.normalize(str(V / "案子"), None), cmdparse.extract_paths("rm -rf 案子 /tmp/x", v))
            self.assertIn(paths.normalize(str(V / "暫存區"), None), cmdparse.extract_paths("mv 暫存區 /tmp/", v))
            self.assertIn(paths.normalize(str(V / "暫存區"), None), cmdparse.extract_paths("tar czf /tmp/b.tgz 暫存區", v))
            self.assertNotIn(paths.normalize(str(V / "czf"), None), cmdparse.extract_paths("tar czf /tmp/b.tgz 暫存區", v))
            self.assertNotIn(paths.normalize(str(V / "v1.2"), None), cmdparse.extract_paths("echo v1.2 > /tmp/ver.txt", v))
            self.assertNotIn(paths.normalize(str(V / "example.com"), None), cmdparse.extract_paths("wget example.com -O /tmp/x", v))
            self.assertIn(paths.normalize(str(V / "新檔.xlsx"), None), cmdparse.extract_paths("cp /tmp/a 新檔.xlsx", v))
            self.assertIn(paths.normalize(str(V / "report.PDF"), None), cmdparse.extract_paths("cp /tmp/a report.PDF", v))
            self.assertNotIn(paths.normalize(str(V / "案子"), None), cmdparse.extract_paths("ls 案子", v))  # 讀取指令照舊
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_unresolved_variable_paths(self):
        """第九輪 Z3（裁定 3）：帶 $變數／%變數% 展不開的 token 全部回報（含沒斜線的裸變數），呼叫端對寫入指令 deny unparsed。"""
        self.assertEqual(cmdparse.unresolved_paths('rm -rf "C:/raw/$X" /tmp/y'), ["C:/raw/$X"])
        self.assertEqual(cmdparse.unresolved_paths('rm -rf "%RAW%/a" '), ["%RAW%/a"])
        self.assertEqual(cmdparse.unresolved_paths("echo x > $OUT"), ["$OUT"])
        self.assertEqual(cmdparse.unresolved_paths('cd "$HOME/x" && rm a.txt'), ["$HOME/x"])
        self.assertEqual(cmdparse.unresolved_paths("Remove-Item $env:TEMP\\a.txt"), ["$env:TEMP\\a.txt"])
        self.assertEqual(cmdparse.unresolved_paths('rm -rf "$X" /tmp/y'), ["$X"])
        self.assertEqual(cmdparse.unresolved_paths("Remove-Item $f"), ["$f"])
        self.assertEqual(cmdparse.unresolved_paths("echo $PASSWORD > /tmp/x"), ["$PASSWORD"])
        self.assertEqual(cmdparse.unresolved_paths("rm -rf %X% /tmp/y"), ["%X%"])
        for cmd in ("rm -rf /tmp/y", "curl https://x/$id > /tmp/a", "ls 2>$null", "echo x > $null", "ls | Out-Null"):
            with self.subTest(cmd=cmd):
                self.assertEqual(cmdparse.unresolved_paths(cmd), [], cmd)

    def test_unresolved_paths_narrowed_round10(self):
        """第十輪 A5：裸變數只在整個 token 是 $X、${X}、$X/…、$X\\…（PowerShell 另加 %X%、%X%\\…）才算；
        單引號裡、格式字串（+%Y%m%d、--format=%H）、旗標黏值（-Confirm:$false）、PowerShell 自動變數都不算。"""
        u = cmdparse.unresolved_paths
        self.assertEqual(u("rm -rf ${X} /tmp/y"), ["${X}"])
        self.assertEqual(u("rm -rf $X\\a /tmp/y"), ["$X\\a"])
        self.assertEqual(u("Remove-Item %X%\\a", powershell=True), ["%X%\\a"])
        self.assertEqual(u('echo x > "out$Y"'), ["out$Y"])  # 導向目標裡有變數：還是看不出寫到哪
        for cmd in ("date +%Y%m%d > /tmp/d.txt", "awk '{print $1}' a.txt > /tmp/x", "printf '%s\\n' a > /tmp/p", "git log --format=%H > /tmp/g",
                    "echo '$HOME/x' > /tmp/q", "echo a$b > /tmp/r"):
            with self.subTest(cmd=cmd):
                self.assertEqual(u(cmd), [], cmd)
        for cmd in ("Remove-Item /tmp/x -Confirm:$false", "gci /tmp | ForEach-Object { $_ } | Out-File /tmp/o", "Remove-Item /tmp/x; $null",
                    "Remove-Item $true $false $PSItem $args $LASTEXITCODE $?"):
            with self.subTest(cmd=cmd):
                self.assertEqual(u(cmd, powershell=True), [], cmd)
        self.assertEqual(u("rm -rf $null /tmp/y"), ["$null"])  # Bash 沒有自動變數

    def test_brace_expand(self):
        """第十輪 A1：token 含 {a,b} 展開成各組合（上限 20 組）；沒逗號的大括號不展開。"""
        self.assertEqual(cmdparse.brace_expand("../raw/行政/{薪資,x}/s.xlsx"), ["../raw/行政/薪資/s.xlsx", "../raw/行政/x/s.xlsx"])
        self.assertEqual(cmdparse.brace_expand("../r{2,3}"), ["../r2", "../r3"])
        self.assertEqual(cmdparse.brace_expand("a{1,2}{x,y}"), ["a1x", "a1y", "a2x", "a2y"])
        self.assertEqual(cmdparse.brace_expand("{print $1}"), ["{print $1}"])
        self.assertEqual(cmdparse.brace_expand("plain"), ["plain"])
        self.assertEqual(len(cmdparse.brace_expand("{1,2,3,4,5}{1,2,3,4,5}")), 20)
        got = cmdparse.extract_paths("cat C:/x/raw/行政/{薪資,x}/s.xlsx", CWD)
        self.assertIn(n("C:/x/raw/行政/薪資/s.xlsx"), got)
        self.assertIn(n("C:/x/raw/行政/x/s.xlsx"), got)
        self.assertIn(n("C:/x/r3"), cmdparse.extract_paths("rm -rf C:/x/r{2,3}", CWD))

    def test_brace_head(self):
        """第十一輪保底：含 { 的 token 回 { 之前的資料夾（沒分隔符就是 .）；{ 在開頭或前面是 $／@ 的回 None。"""
        self.assertEqual(cmdparse.brace_head("../raw/行政/{薪資,x}/s.xlsx"), "../raw/行政")
        self.assertEqual(cmdparse.brace_head("../r{2..3}"), "..")
        self.assertEqual(cmdparse.brace_head("C:\\x\\r{2,3}"), "C:\\x")
        self.assertEqual(cmdparse.brace_head("r{2,3}"), ".")
        for text in ("{", "{a,b}", "${X}", "plain", ""):
            with self.subTest(text=text):
                self.assertIsNone(cmdparse.brace_head(text), text)
        # 第十二輪：@{ 只有 PowerShell 才跳過（雜湊表）；Bash 的 @{…} 照走保底
        self.assertIsNone(cmdparse.brace_head("@{a=1}", powershell=True))
        self.assertIsNone(cmdparse.brace_head("../raw/行政/@{a,b}/p.txt", powershell=True))
        self.assertEqual(cmdparse.brace_head("../raw/行政/@{a,b}/p.txt"), "../raw/行政")
        self.assertEqual(cmdparse.brace_head("@{a=1}"), ".")
        got = cmdparse.extract_paths("cat C:/x/raw/行政/{a,b,c,d,e,f,g,h,i,j,k,l,m,n,o,p,q,r,s,t,薪資}/s.xlsx", CWD)
        self.assertIn(n("C:/x/raw/行政"), got)
        self.assertIn(n("C:/x"), cmdparse.extract_paths("rm -rf C:/x/r{2..3}", CWD))

    def test_is_wildcard(self):
        """第十輪 A6：候選要含 *，或同時含 ?／[ 與路徑分隔符且不是網址。"""
        for text in ("*.md", "../客戶*", "a/?b", "../r[^x]", "C:\\x\\[a]", "薪?/"):
            with self.subTest(text=text):
                self.assertTrue(cmdparse.is_wildcard(text), text)
        for text in ("[", "]", "Is this ok?", "https://a.b/?x=1", "a?b", "{print $1}", "plain", ""):
            with self.subTest(text=text):
                self.assertFalse(cmdparse.is_wildcard(text), text)
        self.assertEqual(cmdparse.glob_prefixes("echo Is this ok? > /tmp/z", CWD), [])
        self.assertEqual(cmdparse.glob_tokens('curl https://a.b/?x=1 > /tmp/x', CWD), [])

    def test_single_letter_switch_is_not_a_path(self):
        """骨架與來源登記第六輪 V5：cmd /c、findstr /s 的單字母開關不是路徑（Git Bash 不會有人寫裸 /c）。"""
        self.assertEqual(cmdparse.extract_paths("cmd /c ver", CWD), [])
        self.assertEqual(cmdparse.extract_paths("findstr /s x", CWD), [])
        self.assertEqual(cmdparse.extract_paths("robocopy /e /s", CWD), [])
        self.assertEqual(cmdparse.extract_paths("ls; cmd /c dir", CWD), [])
        self.assertIn(n("C:/x/a.txt"), cmdparse.extract_paths("cat /c/x/a.txt", CWD))  # 真正的 Git Bash 路徑照抽
        # 第七輪 X3：只有開關式指令（cmd、findstr、robocopy、xcopy、dir、attrib、icacls）或 PowerShell 才把 /x 當旗標
        self.assertIn(n("C:/"), cmdparse.extract_paths("grep -r TODO /c", CWD))
        self.assertIn(n("C:/"), cmdparse.extract_paths('find /c -name "*.env"', CWD))
        self.assertEqual(cmdparse.extract_paths("foo a /e", CWD, powershell=True), [])
        self.assertIn(n("E:/"), cmdparse.extract_paths("foo a /e", CWD))

    def test_relative_path_joins_cwd(self):
        tmp, V, raw = make_vault()
        try:
            got = cmdparse.extract_paths("ls ../raw/客戶案件", str(V))
            self.assertIn(paths.normalize(str(raw / "客戶案件"), None), got)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_redirect_symbols_are_stripped(self):
        got = cmdparse.extract_paths("echo hi >C:/x/raw/客戶案件/a.txt", CWD)
        self.assertIn(n("C:/x/raw/客戶案件/a.txt"), got)
        got = cmdparse.extract_paths("cat C:/x/raw/客戶案件/a.txt|head", CWD)
        self.assertIn(n("C:/x/raw/客戶案件/a.txt"), got)

    def test_variables_and_discarded_output_are_not_paths(self):
        self.assertEqual(cmdparse.extract_paths("rm $X", CWD), [])
        self.assertEqual(cmdparse.extract_paths("ls 2>/dev/null", CWD), [])
        self.assertEqual(cmdparse.extract_paths("git status", CWD), [])


class IsWrite(unittest.TestCase):
    def test_read_commands_are_not_write(self):
        for cmd in ("cat a.txt", "type a.txt", "grep -rn foo .", "ls -la", "git status", "python x.py 2>/dev/null",
                    'git commit -m "copy of notes"', "cat a.txt 2>&1", "Get-Content a.txt | Out-Null"):
            with self.subTest(cmd=cmd):
                self.assertFalse(cmdparse.is_write(cmd))

    def test_write_commands(self):
        for cmd in ("echo hi > a.txt", "cat a >> b", "rm a.txt", "mv a b", "Set-Content a.txt 'x'",
                    "python -c \"open('x','w').write('1')\"", "sed -i s/a/b/ f.txt", "mkdir foo", "touch a",
                    "Out-File -FilePath a.txt", "New-Item a.txt"):
            with self.subTest(cmd=cmd):
                self.assertTrue(cmdparse.is_write(cmd))

    def test_redirect_inside_quotes_is_text(self):
        self.assertFalse(cmdparse.is_write('grep "<[^>]+>" a.html'))

    def test_unbalanced_quote_falls_back_to_whole_string(self):
        self.assertTrue(cmdparse.is_write('echo "x > a.txt'))


class SinglePluginCall(unittest.TestCase):
    KB = f'python "{PLUGIN}/scripts/kb.py" version'

    def test_single_call_true(self):
        self.assertTrue(cmdparse.is_single_plugin_call(self.KB, PLUGIN))
        fwd = PLUGIN.replace("\\", "/")
        self.assertTrue(cmdparse.is_single_plugin_call(f"python {fwd}/scripts/kb.py guard decide --tool Read --path x", PLUGIN))
        # N-a：引號外的反斜線一律不是單一呼叫，不加引號的 Windows 路徑要用 /
        self.assertFalse(cmdparse.is_single_plugin_call(f"python {fwd.replace('/', chr(92))}\\scripts\\kb.py version", PLUGIN))
        self.assertTrue(cmdparse.is_single_plugin_call(self.KB.replace("/", "\\"), PLUGIN))

    def test_chained_is_false(self):
        for cmd in (self.KB + " && rm -rf x", self.KB + "; echo 1", self.KB + " | tee out", self.KB + " > out",
                    "$(" + self.KB + ")", "`" + self.KB + "`", "echo 1\n" + self.KB):
            with self.subTest(cmd=cmd):
                self.assertFalse(cmdparse.is_single_plugin_call(cmd, PLUGIN))

    def test_other_script_is_false(self):
        self.assertFalse(cmdparse.is_single_plugin_call(f'python "{PLUGIN}/scripts/other.py"', PLUGIN))
        self.assertFalse(cmdparse.is_single_plugin_call(f'python "{PLUGIN}/scripts/../evil/scripts/kb.py"', PLUGIN))
        self.assertFalse(cmdparse.is_single_plugin_call('python "C:/elsewhere/scripts/kb.py"', PLUGIN))

    def test_outside_quotes(self):
        self.assertEqual(cmdparse.outside_quotes('a "b;c" d'), "a  d")
        self.assertIsNone(cmdparse.outside_quotes('a "b'))


class ReviewGaps(unittest.TestCase):
    """審閱發現的漏洞：引號裡的包裝指令、PowerShell 別名、cd 之後的相對路徑、token 裡夾的絕對路徑、萬用字元。"""

    def test_write_verb_inside_wrapper_quotes_counts(self):
        for cmd in ('bash -c "rm C:/x/a.txt"', "sh -c 'rm a'", 'cmd /c "del C:\\x\\a.txt"', 'powershell -c "Remove-Item C:\\x\\a.txt"',
                    'pwsh -Command "Set-Content C:\\x\\a.txt x"', 'eval "rm a"', 'bash -c "echo hi > C:/x/a.txt"'):
            with self.subTest(cmd=cmd):
                self.assertTrue(cmdparse.is_write(cmd))

    def test_commit_message_is_still_not_write(self):
        self.assertFalse(cmdparse.is_write('git commit -m "copy of notes, rm later"'))

    def test_powershell_aliases_and_other_tools(self):
        for cmd in ("ri C:\\x\\a.txt", "sc C:\\x\\a.txt x", "ac C:\\x\\a.txt x", "md C:\\x\\d", "rd C:\\x\\d", "ni C:\\x\\a.txt",
                    "sed --in-place s/a/b/ f", "perl -i -pe s/a/b/ f", "dd if=a of=C:/x/b", "find C:/x -delete", "curl -o C:/x/a http://h",
                    "tar -xf a.tar -C C:/x", "unzip a.zip -d C:/x", "ln -s a C:/x/b", "git clean -fd", "git checkout -- C:/x/a.txt",
                    "Export-Csv C:\\x\\a.csv", "Set-ItemProperty C:\\x\\a.txt"):
            with self.subTest(cmd=cmd):
                self.assertTrue(cmdparse.is_write(cmd))

    def test_cd_then_relative_resolves_against_cd_target(self):
        tmp, V, raw = make_vault()
        try:
            want = paths.normalize(str(raw / "行政" / "薪資" / "s.xlsx"), None)
            got = cmdparse.extract_paths(f"cd {raw}/行政 && cat 薪資/s.xlsx", str(V))
            self.assertIn(want, got)
            got = cmdparse.extract_paths("cd ../raw/行政; cat 薪資/s.xlsx", str(V))
            self.assertIn(want, got)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_absolute_path_embedded_in_token(self):
        got = cmdparse.extract_paths("python -c \"print(open('C:/x/raw/行政/薪資/s.xlsx','rb').read())\"", CWD)
        self.assertIn(n("C:/x/raw/行政/薪資/s.xlsx"), got)
        got = cmdparse.extract_paths("P=C:/x/raw/a.txt; rm $P", CWD)
        self.assertIn(n("C:/x/raw/a.txt"), got)
        got = cmdparse.extract_paths("cat file:///C:/x/raw/a.txt", CWD)
        self.assertIn(n("C:/x/raw/a.txt"), got)

    def test_glob_prefixes(self):
        globs = cmdparse.glob_prefixes("cat C:/x/raw/行政/*/s.xlsx; ls C:/x/raw/行政/薪?/", CWD)
        self.assertEqual(globs, [n("C:/x/raw/行政"), n("C:/x/raw/行政")])
        self.assertEqual(cmdparse.glob_prefixes("ls C:/x", CWD), [])



class Round1(unittest.TestCase):
    """第一輪測試後修正：S1 直譯器、S2 PowerShell 子運算式、B1 副檔名、B3 非路徑 token、萬用字元 token。"""

    KB = f'"{PLUGIN}/scripts/kb.py" version'

    def test_s1_interpreter_must_be_bare_or_safe_absolute(self):
        self.assertTrue(cmdparse.is_single_plugin_call("python " + self.KB, PLUGIN))
        self.assertTrue(cmdparse.is_single_plugin_call("python3 " + self.KB, PLUGIN))
        self.assertTrue(cmdparse.is_single_plugin_call("py " + self.KB, PLUGIN))
        self.assertTrue(cmdparse.is_single_plugin_call("python.exe " + self.KB, PLUGIN))
        for bad in ("檔案索引/python ", "./python ", "../python ", "AI\\ 產出/python ", "C:/x/vault/檔案索引/notpython.exe "):
            with self.subTest(interp=bad):
                self.assertFalse(cmdparse.is_single_plugin_call(bad + self.KB, PLUGIN))
        # 第二輪 S1 殘：任何含路徑分隔符的直譯器一律不算，連 vault 外的絕對路徑也不算
        for bad in ("C:/Python312/python.exe ", "C:/Temp/evil/python.exe ", "C:\\Temp\\evil\\python.exe ",
                    "C:/x/vault/檔案索引/python ", "C:/x/raw/客戶案件/python.exe ", "/usr/bin/python3 "):
            with self.subTest(interp=bad):
                self.assertFalse(cmdparse.is_single_plugin_call(bad + self.KB, PLUGIN))

    def test_s2_subexpressions_are_not_single_call(self):
        for tail in (" @(Remove-Item x)", " (rm x)", " $(rm x)", " `rm x`", "; rm x", " @('a')"):
            with self.subTest(tail=tail):
                self.assertFalse(cmdparse.is_single_plugin_call("python " + self.KB + tail, PLUGIN))
        self.assertTrue(cmdparse.is_single_plugin_call('python ' + self.KB + ' --path "a (b)"', PLUGIN))

    def test_b1_extension_is_not_a_write_verb(self):
        for cmd in ("cat CLAUDE.md", "head 系統/待處理.md", "grep TODO 暫存區/a.md", "type C:\\r\\行政\\請款\\notes.md",
                    "cat a.sc", "cat x.cp", "ls notes.ac", "cat README.md | head", "cat a.rm"):
            with self.subTest(cmd=cmd):
                self.assertFalse(cmdparse.is_write(cmd))
        for cmd in ("md x", "rd x", "rm x.md", "cp a.md b.md", "sc a.md x", "cat a.md > b.md"):
            with self.subTest(cmd=cmd):
                self.assertTrue(cmdparse.is_write(cmd))

    def test_b3_relative_token_must_resolve(self):
        tmp, V, raw = make_vault()
        try:
            cwd = str(V)
            self.assertEqual(cmdparse.extract_paths("sed -i s/a/b/ x", cwd), [])
            self.assertEqual(cmdparse.extract_paths("echo 2026/10/12", cwd), [])
            got = cmdparse.extract_paths('sed -i s/a/b/ "暫存區/x.md"', cwd)
            self.assertEqual(got, [paths.normalize(str(V / "暫存區" / "x.md"), None)])
            got = cmdparse.extract_paths("cat 案子/信義王/合約.docx", cwd)
            self.assertEqual(got, [paths.normalize(str(V / "案子" / "信義王" / "合約.docx"), None)])
            got = cmdparse.extract_paths("echo hi > 暫存區/x.txt", cwd)
            self.assertEqual(got, [paths.normalize(str(V / "暫存區" / "x.txt"), None)])
            got = cmdparse.extract_paths("mkdir 案子/新案", cwd)
            self.assertEqual(got, [paths.normalize(str(V / "案子" / "新案"), None)])
            self.assertEqual(cmdparse.extract_paths("echo 新案/新案/x.md", cwd), [])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_glob_tokens(self):
        tmp, V, raw = make_vault()
        try:
            r = str(raw).replace("\\", "/")
            got = cmdparse.glob_tokens(f"cat {r}/*/薪資/s.xlsx; ls {V}/AI\\ 產出", str(V))
            self.assertEqual(got, [paths.normalize(f"{r}/*/薪資/s.xlsx", None)])
            got = cmdparse.glob_tokens(f"cd {r}/行政 && cat */s.xlsx", str(V))
            self.assertEqual(got, [paths.normalize(f"{r}/行政/*/s.xlsx", None)])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)



class Round2(unittest.TestCase):
    """第二輪：N-a 反斜線跳脫引號、N-b lookbehind 退步、N-c 跳脫形態。"""

    KB = f'"{PLUGIN}/scripts/kb.py" version'

    def test_na_escaped_quote_is_not_a_quote_boundary(self):
        bare = cmdparse.outside_quotes('a \\"b; c')
        self.assertIsNotNone(bare)
        self.assertIn(";", bare)
        self.assertEqual(cmdparse.outside_quotes('a "b;c" d'), "a  d")
        self.assertIsNone(cmdparse.outside_quotes('a "b'))

    def test_na_escaped_quote_payload_is_not_single_call(self):
        evil = 'python ' + self.KB + ' \\"; rm -rf C:/x/raw/客戶案件; echo \\"'
        self.assertFalse(cmdparse.is_single_plugin_call(evil, PLUGIN))
        self.assertFalse(cmdparse.is_single_plugin_call('python ' + self.KB + " \\'; rm x; echo \\'", PLUGIN))
        self.assertFalse(cmdparse.is_single_plugin_call('python ' + self.KB + ' --x a\\b', PLUGIN))  # 引號外任何 \ 都不是單一呼叫
        self.assertTrue(cmdparse.is_single_plugin_call('python ' + self.KB.replace("/", "\\"), PLUGIN))  # 引號內的 \ 是路徑
        self.assertTrue(cmdparse.is_write(evil))

    def test_nb_verb_after_slash_or_backslash_counts(self):
        for cmd in ("\\rm -rf C:/x/a", "/bin/rm C:/x/a.txt", "/usr/bin/cp a b", "Microsoft.PowerShell.Management\\Remove-Item C:\\x\\a.txt",
                    "  rm x", "rm x"):
            with self.subTest(cmd=cmd):
                self.assertTrue(cmdparse.is_write(cmd))
        for cmd in ("cat x.md", "ls --rm", "cat x.cp", "cat README.md", "type notes.ac"):
            with self.subTest(cmd=cmd):
                self.assertFalse(cmdparse.is_write(cmd))

    def test_nc_escaped_non_ascii_variant_is_extracted(self):
        got = cmdparse.extract_paths("cat C:/x/raw/行政/薪\\資/s.xlsx", CWD)
        self.assertIn(n("C:/x/raw/行政/薪資/s.xlsx"), got)
        got = cmdparse.extract_paths("ls C:/x/vault/AI\\ 產出", CWD)
        self.assertIn(n("C:/x/vault/AI 產出"), got)  # 跳脫空白的寫法跟夾名無關，借舊名當含空白的非 ASCII 例子


class CodePaths(unittest.TestCase):
    """B-425 (b)：程式碼裡單獨的 / 與算式的 / 不抽成路徑；真的絕對路徑照抽。"""

    def test_lone_slash_and_arithmetic_not_paths(self):
        for text in ("s='/'", "print('/'.join(x))", 'print("/".join(x))', "print(540000/12)", "x=(1+2)/3; y=5 /c/ 2",
                     "print(a / b / c)", "print(len(x) /c/ (n))", "print(n /c/ 2)"):
            with self.subTest(text=text):
                self.assertEqual(cmdparse.code_paths(text), [])

    def test_real_absolute_paths_still_found(self):
        self.assertEqual(cmdparse.code_paths("open('C:/x/a.txt')"), ["C:/x/a.txt"])
        self.assertEqual(cmdparse.code_paths("open('/c/Users/x/a.txt')"), ["/c/Users/x/a.txt"])
        self.assertEqual(cmdparse.code_paths("open('//server/share/a.txt')"), ["//server/share/a.txt"])
        unc = "\\\\server\\share\\a.txt"
        self.assertEqual(cmdparse.code_paths("open('" + unc + "')"), [unc])
        self.assertEqual(cmdparse.code_paths("open(\"/c/\")"), ["/c/"])
        self.assertEqual(cmdparse.code_paths("p = C:/x/a.txt"), ["C:/x/a.txt"])


def op(text, powershell=True, base=None):
    """跟 guard 一樣：動詞從去引號的字取，開檔段吃原樣的字。"""
    words = cmdparse.raw_words(text, powershell)
    return cmdparse.open_stage(cmdparse.verb_of([w.strip("'\"") for w in words]), words, powershell, base)


class OpenStage(unittest.TestCase):
    """開檔與Office一起改（D-514）：open_stage 抽要開的東西、分開檔與跑程式。"""

    def test_not_open_verb(self):
        for text, ps in (("Get-Content 'C:\\x\\a.docx'", True), ("cmd /c del x.docx", True), ('cmd /c "start x.docx"', True),
                         ("$w.Documents.Open('C:\\x\\a.docx')", True)):
            with self.subTest(text=text):
                self.assertIsNone(op(text, ps))

    def test_full_path_verb_same_verb(self):
        """裁定 11：完整路徑的 explorer.exe、cmd.exe /c start 照同一個動詞判，程式檔另回 exe 給 guard 查 run_file。"""
        for text, ps, targets, exe in (
                ("C:\\Windows\\explorer.exe 'C:\\x\\a.docx'", True, ["C:\\x\\a.docx"], "C:\\Windows\\explorer.exe"),
                ("& 'C:\\x\\暫存區\\explorer.exe' a.docx", True, ["a.docx"], "C:\\x\\暫存區\\explorer.exe"),
                ('C:\\Windows\\System32\\cmd.exe /c start "" C:\\x\\a.docx', True, ["C:\\x\\a.docx"],
                 "C:\\Windows\\System32\\cmd.exe"),
                ('"C:/x/start" a.docx', False, ["a.docx"], "C:/x/start"),
                ("explorer a.docx", True, ["a.docx"], None)):
            with self.subTest(text=text):
                got = op(text, ps)
                self.assertEqual((got["targets"], got["exe"]), (targets, exe))

    def test_start_process_targets(self):
        for text in ("Start-Process 'C:\\x\\暫存區\\a.docx'", "Start-Process -FilePath 'C:\\x\\暫存區\\a.docx'",
                     "Start-Process -FilePath:'C:\\x\\暫存區\\a.docx'", "saps -File 'C:\\x\\暫存區\\a.docx' -Wait",
                     "start 'C:\\x\\暫存區\\a.docx'",
                     "Start-Process 'C:\\x\\暫存區\\a.docx' -Verb Print -WindowStyle Maximized"):
            with self.subTest(text=text):
                got = op(text)
                self.assertEqual((got["targets"], got["kind"], got["writes"], got["opaque"]),
                                 (["C:\\x\\暫存區\\a.docx"], "open", [], False))

    def test_invoke_item_targets(self):
        self.assertEqual(op("Invoke-Item 'C:\\x\\a.docx', 'C:\\x\\b.pdf'")["targets"], ["C:\\x\\a.docx", "C:\\x\\b.pdf"])
        self.assertEqual(op("ii -LiteralPath 'C:\\x\\a b.pdf'")["targets"], ["C:\\x\\a b.pdf"])
        self.assertEqual(op("ii C:\\x\\a.xlsx")["kind"], "open")

    def test_cmd_start_skips_title(self):
        for text, ps, targets in (('start "" "C:/x/暫存區/a.docx"', False, ["C:/x/暫存區/a.docx"]),
                                  ('start "C:/x/my docs/a.docx"', False, []),
                                  ('start /b /wait /min "" C:/x/a.docx', False, ["C:/x/a.docx"]),
                                  ('cmd //c start "" "C:/x/暫存區/a.docx"', False, ["C:/x/暫存區/a.docx"]),
                                  ('cmd /c start "" "C:\\x\\暫存區\\a.docx"', True, ["C:\\x\\暫存區\\a.docx"]),
                                  ('cmd.exe /C start C:\\x\\a.bat', True, ["C:\\x\\a.bat"]),
                                  ('start "C:/x/a.bat"', False, ["C:/x/a.bat"])):  # 沒空白的引號傳給 cmd 時沒有引號，不是標題
            with self.subTest(text=text):
                self.assertEqual(op(text, ps)["targets"], targets)
        got = op('start /d "C:/w" "" a.docx', False)
        self.assertEqual((got["cwd"], got["targets"]), ("C:/w", ["a.docx"]))

    def test_explorer_open(self):
        self.assertEqual(op("explorer 'C:\\x\\暫存區'")["targets"], ["C:\\x\\暫存區"])
        self.assertEqual(op('explorer.exe /select,"C:\\x\\a.docx"')["targets"], ["C:\\x\\a.docx"])
        self.assertEqual(op("open /tmp/a.pdf", False)["targets"], ["/tmp/a.pdf"])
        self.assertEqual(op("xdg-open /tmp/a.pdf", False)["kind"], "open")

    def test_kind(self):
        tmp, V, _raw = make_vault()
        try:
            for target, kind in (("https://example.com", "open"), ("mailto:a@b.tw", "open"), ("C:\\x\\a.PDF", "open"),
                                 ("C:\\x\\a.bat", "run"), ("C:\\x\\a.docm", "run"), ("C:\\x\\a.lnk", "run"),
                                 ("C:\\x\\a.bat:.docx", "run"), ("C:\\x\\夾", "run"), (str(V / "暫存區"), "open"),
                                 ("暫存區", "open"), ("powershell", "run")):
                with self.subTest(target=target):
                    self.assertEqual(op(f"Start-Process '{target}'", base=str(V))["kind"], kind)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_verb_flag(self):
        for verb, kind in (("Print", "open"), ("edit", "open"), ("OpenAsReadOnly", "open"), ("Open", "open"), ("RunAs", "run")):
            with self.subTest(verb=verb):
                got = op(f"Start-Process 'C:\\x\\a.docx' -Verb {verb}")
                self.assertEqual((got["verb_flag"], got["kind"]), (verb, kind))

    def test_program_line(self):
        for text, program in (
                ("Start-Process powershell -ArgumentList '-NoExit','-Command','claude --name t'",
                 'powershell -NoExit -Command "claude --name t"'),
                ("Start-Process powershell -ArgumentList '-NoExit', '-Command', 'claude --name t'",
                 'powershell -NoExit -Command "claude --name t"'),
                ("Start-Process powershell '-NoExit','-Command','claude'", "powershell -NoExit -Command claude"),
                ("Start-Process powershell -ArgumentList '-Command','Remove-Item ''C:\\x\\a.md'''",
                 "powershell -Command \"Remove-Item 'C:\\x\\a.md'\""),
                ("Start-Process powershell -ArgumentList '-NoExit -Command x'", "powershell -NoExit -Command x"),
                ("Start-Process cmd -ArgumentList '/c','del \"C:\\x\\a b.docx\"'", 'cmd /c del "C:\\x\\a b.docx"'),
                ("Start-Process 'C:\\x\\a b.bat'", '"C:\\x\\a b.bat"')):
            with self.subTest(text=text):
                got = op(text)
                self.assertEqual((got["kind"], got["program"]), ("run", program))
        got = op('start "" powershell -Command "Remove-Item x"', False)
        self.assertEqual(got["program"], 'powershell -Command "Remove-Item x"')
        self.assertIsNone(op("Start-Process 'C:\\x\\a.docx'")["program"])

    def test_redirects_and_cwd(self):
        got = op("Start-Process powershell -ArgumentList '-NoExit' -RedirectStandardOutput 'C:\\x\\o.txt' "
                 "-RedirectStandardError C:\\x\\e.txt -RedirectStandardInput 'C:\\x\\i.txt' -WorkingDirectory 'C:\\w'")
        self.assertEqual((got["writes"], got["reads"], got["cwd"]), (["C:\\x\\o.txt", "C:\\x\\e.txt"], ["C:\\x\\i.txt"], "C:\\w"))
        self.assertIsNone(op("Start-Process 'C:\\x\\a.docx'")["cwd"])

    def test_opaque(self):
        for text, ps in (("Start-Process $f", True), ("Start-Process powershell -ArgumentList $a", True),
                         ("Start-Process (Get-Item x)", True), ('Start-Process "$env:TEMP\\x.docx"', True),
                         ("Start-Process -FilePath $f", True), ("Start-Process @a", True),
                         ("start %TEMP%\\x.docx", False), ('start "" "$HOME/x.docx"', False),
                         ("cmd /c start x.docx '&' del y", True), ('start "" "a|b.docx"', False),
                         ("Start-Process -Foo x.docx", True), ("Start-Process -Red x.txt powershell", True),
                         ("Start-Process powershell -RedirectStandardOutput $o", True),
                         ("Start-Process -FilePath a.txt -FilePath x.bat", True), ('cmd /c start \'"t"\' x.bat', True),
                         ("open -- sh -c 'rm -rf .'", False)):
            with self.subTest(text=text):
                self.assertTrue(op(text, ps)["opaque"])
        self.assertFalse(op("Start-Process 'https://x.tw/%E4%B8%AD'")["opaque"])
        self.assertFalse(op("Start-Process '$f.docx'")["opaque"])  # 單引號不展開

    def test_stage_kind_and_write_words(self):
        self.assertEqual(cmdparse.stage_kind("start-process", "Start-Process 'C:\\x\\a.docx'", powershell=True), "read")
        self.assertEqual(cmdparse.stage_kind("start-process", "Start-Process powershell -RedirectStandardOutput o.txt",
                                             powershell=True), "write")
        self.assertEqual(cmdparse.stage_kind("cmd", 'cmd //c start "" "C:/x/a.docx"'), "read")
        self.assertFalse(cmdparse.is_write("Start-Process 'C:\\x\\a.docx'", True))
        self.assertNotIn("start-process", cmdparse.SHELL_WRAPPERS)
        self.assertNotIn("start", cmdparse.SHELL_WRAPPERS)


class DestructiveCodeOpenMode(unittest.TestCase):
    """open( 只有第二個位置參數是寫入模式才算，檔名第一個字母不是模式。"""

    def test_read_not_destructive(self):
        for code in ("open('x.md').read()", "open('a.txt', encoding='utf-8').read()",
                     "open('w1.md', 'r').read()", "open('AI.md', 'rb').read()",
                     "open(os.path.join(d, 'x.md')).read()", "fopen('x.txt', 'r')"):
            self.assertIsNone(cmdparse.DESTRUCTIVE_CODE.search(code), code)

    def test_write_is_destructive(self):
        for code in ("open('x.md', 'w').write('a')", "open(p, \"a\")", "open('a,b.md', 'x')",
                     "open(os.path.join(d, 'f'), 'w')", "open(p, 'r+')", "open(p, 'wb')",
                     "open(p, mode='w')", "fopen('x.txt', 'w')"):
            self.assertIsNotNone(cmdparse.DESTRUCTIVE_CODE.search(code), code)

    def test_holes25_open_modes(self):
        """守門補洞 #25 要做的事 5：r+b、rb+ 與 os.open 寫入旗標。"""
        for code in ("open(p, mode='r+b')", "Path(p).open('r+b')", "Path(p).open('rb+')", "open(p, mode=\"rb+\")",
                     "os.open(p, os.O_WRONLY | os.O_TRUNC)", "os.open(p, os.O_RDWR)", "os.open(p, O_TRUNC)"):
            self.assertIsNotNone(cmdparse.DESTRUCTIVE_CODE.search(code), code)
        for code in ("open(p, mode='rb')", "Path(p).open('rb')", "os.open(p, os.O_RDONLY)"):
            self.assertIsNone(cmdparse.DESTRUCTIVE_CODE.search(code), code)


class Holes25(unittest.TestCase):
    """守門補洞 #25（D-348）：-EncodedCommand、PowerShell 別名、.NET 檔案靜態呼叫、Office 帶路徑的另存。"""

    @staticmethod
    def enc(text):
        import base64
        return base64.b64encode(text.encode("utf-16-le")).decode()

    def test_encoded_command(self):
        b64 = self.enc("Remove-Item x.md")
        for words in (["powershell", "-EncodedCommand", b64], ["powershell", "-enc", b64], ["powershell", "-e", b64],
                      ["pwsh", "-ec", b64], ["powershell.exe", "-NoProfile", "/enc", b64], ["pwsh", "-En", b64],
                      ["powershell", "-ENCODEDCOMMAND", b64]):
            with self.subTest(words=words):
                self.assertEqual(cmdparse.encoded_command(words), "Remove-Item x.md")
        for words in (["powershell", "-Command", "Remove-Item x"], ["powershell", "-ExecutionPolicy", "Bypass", "-File", "a.ps1"],
                      ["node", "-e", b64], ["perl", "-e", b64]):
            with self.subTest(words=words):
                self.assertIsNone(cmdparse.encoded_command(words))
        for words in (["powershell", "-enc", "這不是base64###"], ["powershell", "-enc"], ["pwsh", "-e", "abc"]):
            with self.subTest(words=words), self.assertRaises(cmdparse.Unbalanced):
                cmdparse.encoded_command(words)

    def test_alias_write_words(self):
        for text in ("clc a.txt", "epcsv a.csv", "sp a.txt -Name IsReadOnly -Value $true",
                     "iwr https://x.tw/a -OutFile a.docx", "irm https://x.tw/a -OutFile:a.json",
                     "Invoke-WebRequest https://x.tw -OutFile a", "Invoke-RestMethod -Uri https://x.tw -OutF a",
                     "curl https://x.tw/a -OutFile a", "wget https://x.tw/a -OutFile a"):
            with self.subTest(text=text):
                self.assertTrue(cmdparse.WRITE_WORDS.search(text))
        for text in ("iwr https://x.tw/a", "Invoke-RestMethod https://x.tw/api", "irm https://x.tw/a | ConvertTo-Json"):
            with self.subTest(text=text):
                self.assertIsNone(cmdparse.WRITE_WORDS.search(text))
        self.assertIn("epcsv", cmdparse.CONTENT_SINKS)

    def test_file_calls(self):
        calls = cmdparse.file_calls
        self.assertEqual(calls("[System.IO.File]::Delete('C:/x/a.docx')"), [("delete", ["'C:/x/a.docx'"])])
        self.assertEqual(calls("([type]'System.IO.File')::Delete('C:/x/a.docx')"), [("delete", ["'C:/x/a.docx'"])])
        self.assertEqual(calls("([type]\"System.IO.File\")::Delete('C:/x/a.docx')"), [("delete", ["'C:/x/a.docx'"])])
        self.assertEqual(calls("[IO.Directory]::Delete('C:/x', $true)"), [("delete", ["'C:/x'", "$true"])])
        self.assertEqual(calls("[IO.FileInfo]::new('C:/x/a.docx').Delete()"), [("delete", ["'C:/x/a.docx'"])])
        self.assertEqual(calls("(Get-Item 'C:/x/a.docx').Delete()"), [("delete", ["'C:/x/a.docx'"])])
        for method in ("WriteAllText", "WriteAllBytes", "WriteAllLines", "AppendAllText", "AppendAllLines", "Create"):
            with self.subTest(method=method):
                self.assertEqual(calls(f"[IO.File]::{method}('C:/x/a.txt', 'y')")[0][0], "write")
        self.assertEqual(calls("[IO.File]::Replace('C:/x/a', 'C:/x/b', $null)"), [("replace", ["'C:/x/a'", "'C:/x/b'", "$null"])])
        self.assertEqual(calls("[IO.File]::Open('C:/x/a.txt', 'Truncate')")[0][0], "write")
        self.assertEqual(calls("[IO.File]::Open('C:/x/a.txt', [IO.FileMode]::Append)")[0][0], "write")
        self.assertEqual(calls("[IO.File]::Open('C:/x/a.txt', 'Open', 'Read')"), [])
        self.assertEqual(calls("[IO.File]::Copy('C:/x/a', 'C:/x/b', $true)"), [("copy", ["'C:/x/a'", "'C:/x/b'", "$true"])])
        self.assertEqual(calls("[System.IO.File]::Move('C:/x/a', 'C:/x/b')"), [("move", ["'C:/x/a'", "'C:/x/b'"])])
        for text in ("[regex]::Replace($s, 'a', 'b')", "[Array]::Copy($a, $b, 3)", "[string]::Copy('x')", "$f.Delete()",
                     "$d.Range(0, 5).Delete()", "[IO.File]::ReadAllText('C:/x/a.txt')", "[IO.Path]::Combine('a', 'b')"):
            with self.subTest(text=text):
                self.assertEqual(calls(text), [])

    def test_office_save_targets(self):
        targets = cmdparse.office_save_targets
        self.assertEqual(targets("$d.SaveAs2('C:\\x\\a.docx')"), ["C:\\x\\a.docx"])
        self.assertEqual(targets("$d.SaveAs(\"C:/x/a.docx\")"), ["C:/x/a.docx"])
        self.assertEqual(targets("$b.SaveCopyAs('C:/x/b.xlsx')"), ["C:/x/b.xlsx"])
        self.assertEqual(targets("$d.ExportAsFixedFormat('C:/x/a.pdf', 17)"), ["C:/x/a.pdf"])
        self.assertEqual(targets("d.SaveAs2(r'C:\\x\\a.docx')"), ["C:\\x\\a.docx"])
        for text in ("$d.Save()", "$d.SaveAs2($p)", "$w.Documents.Open('C:/x/a.docx')", "$d.Range().Delete()", "$d.Close()"):
            with self.subTest(text=text):
                self.assertEqual(targets(text), [])

    def test_stage_kind(self):
        for text in ("[System.IO.File]::Delete('C:/x/a.docx')", "([type]'System.IO.File')::Delete('C:/x/a')",
                     "[IO.Directory]::Delete('C:/x', $true)", "[IO.FileInfo]::new('C:/x/a').Delete()",
                     "(Get-Item 'C:/x/a').Delete()", "$d.SaveAs2('C:/x/a.docx')", "$b.SaveCopyAs('C:/x/a.xlsx')",
                     "$d.ExportAsFixedFormat('C:/x/a.pdf', 17)", "clc C:/x/a.txt", "iwr https://x.tw -OutFile C:/x/a"):
            with self.subTest(text=text):
                verb = cmdparse.verb_of(text.replace("(", " ").split())
                self.assertEqual(cmdparse.stage_kind(verb, text, powershell=True), "write")
        for text in ("$w.Documents.Open('C:/x/a.docx')", "$d.Range(0, 5).Delete()", "$f.Delete()", "iwr https://x.tw",
                     "[regex]::Replace($s, 'a', 'b')", "Get-Item 'C:/x/a'"):
            with self.subTest(text=text):
                verb = cmdparse.verb_of(text.replace("(", " ").split())
                self.assertEqual(cmdparse.stage_kind(verb, text, powershell=True), "read")


if __name__ == "__main__":
    unittest.main()
