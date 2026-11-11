"""守門（#22 Obsidian 首頁，D-261、D-255）：.obsidian 歸 Z7；模型自己帶 --via 照 SELF_FLAGS 擋。語料三條在 guard_corpus.json。"""
import shutil
import unittest

from tests._guard_fixture import ROOT, make_vault, payload
from tests.test_cardmaker_round2 import SELF_FLAGS, guard_out
from kb import guard  # noqa: E402

KB = f'python "{ROOT}/scripts/kb.py"'


class SelfVia(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, command, tool="Bash", agent=None):
        data = payload(tool, command, self.V)
        data["session_id"] = "sid-1"
        if agent:
            data.update(agent_id=agent, agent_type="wiki-with-willy:card-maker")
        return guard_out(data)

    def test_model_cannot_pass_via(self):
        for cmd in (f"{KB} --via obsidian agenda list", f"{KB} --vi=obsidian agenda list",
                    f"{KB} --via obsidian agenda done a-1"):
            for tool in ("Bash", "PowerShell"):
                with self.subTest(cmd=cmd, tool=tool):
                    out = self.call(cmd, tool)
                    self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]), ("deny", SELF_FLAGS))

    def test_other_flags_starting_with_v_still_pass(self):
        out = self.call(f"{KB} unlock save --name 甲 --kind 記下的密碼 --value x")  # --value 不是 --via 的前綴
        self.assertNotEqual(out.get("permissionDecisionReason"), SELF_FLAGS)


class Zone(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_obsidian_folder_is_z7(self):
        for rel in (".obsidian/plugins/wiki-with-willy/main.js", ".obsidian/community-plugins.json", ".obsidian/workspace.json"):
            d = guard.decide(payload("Read", self.V / rel, self.V))
            self.assertEqual(d.zone, "Z7", rel)
            self.assertEqual(d.decision, "allow", rel)
            d = guard.decide(payload("Write", self.V / rel, self.V))
            self.assertEqual((d.zone, d.decision), ("Z7", "deny"), rel)


class OuterPlugin(unittest.TestCase):
    """#66 丙 驗收 14～20：上層 vault（這裡是 self.tmp）那份外掛夾照 Z7 擋；上層 .obsidian 的其他檔、她的筆記照舊。"""

    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        self.plug = self.tmp / ".obsidian" / "plugins" / "wiki-with-willy"
        self.plug.mkdir(parents=True)
        self.main = self.plug / "main.js"
        self.main.write_text("// 外掛", encoding="utf-8")
        (self.tmp / ".obsidian" / "plugins" / "obsidian-git").mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def decide(self, tool, value, cwd=None):
        return guard.decide(payload(tool, value, cwd or self.V))

    def system_files(self):
        return {f.relative_to(self.V).as_posix(): (f.stat().st_mtime_ns, f.stat().st_size)
                for f in (self.V / ".system").rglob("*") if f.is_file() and f.name != "ledger.tsv"}

    def test_14_15_file_tools(self):
        inner = self.decide("Write", self.V / ".obsidian" / "plugins" / "wiki-with-willy" / "main.js")
        for tool in ("Write", "Edit"):
            for target in (self.main, self.plug / "data.json", self.plug):
                d = self.decide(tool, target)
                self.assertEqual((d.zone, d.decision, d.reason_code), ("Z7", "deny", inner.reason_code), f"{tool} {target.name}")
        d = self.decide("Write", self.main)
        self.assertEqual(d.reason, inner.reason, "理由句跟知識庫裡 .obsidian 被擋時一樣")
        self.assertEqual([r["zone"] for r in d.ledger_rows], ["Z7"])
        d = self.decide("Read", self.main)
        self.assertEqual((d.zone, d.decision), ("Z7", "allow"))

    def test_16_rest_of_outer_is_as_before(self):
        for rel in (".obsidian/app.json", ".obsidian/plugins/obsidian-git/data.json", "筆記.md",
                    ".obsidian/plugins/wiki-with-willy2/main.js", ".obsidian/plugins/obsidian-git", ".obsidian2", ".obsidian/plugins2"):
            d = self.decide("Write", self.tmp / rel)
            self.assertEqual((d.zone, d.decision), ("Z11", "pass"), rel)

    def test_17_shell_writes(self):
        main, plug = self.main.as_posix(), self.plug.as_posix()
        before = self.system_files()
        for cmd in (f'cp x "{main}"', f'echo x > "{main}"', f'rm -r "{plug}"', f'mv "{main}" "{main}.bak"',
                    "cp x ../.obsidian/plugins/wiki-with-willy/main.js", "echo x >> ../.obsidian/plugins/wiki-with-willy/main.js"):
            d = self.decide("Bash", cmd)
            self.assertEqual((d.decision, d.zone), ("deny", "Z7"), cmd)
        for cmd in (f'Set-Content -Path "{main}" -Value x', f'Copy-Item x -Destination "{main}"', f'Remove-Item "{plug}" -Recurse',
                    "Set-Content ../.obsidian/plugins/wiki-with-willy/main.js x"):
            d = self.decide("PowerShell", cmd)
            self.assertEqual((d.decision, d.zone), ("deny", "Z7"), cmd)
        self.assertEqual(self.system_files(), before, "驗收 20：找上層不寫任何狀態檔")

    def test_17_shell_reads_and_her_own_files_pass(self):
        self.assertNotEqual(self.decide("Bash", f'cat "{self.main.as_posix()}"').decision, "deny")
        self.assertNotEqual(self.decide("Bash", f'echo x > "{(self.tmp / "筆記.md").as_posix()}"').decision, "deny")
        self.assertNotEqual(self.decide("Bash", f'echo x > "{(self.tmp / ".obsidian" / "app.json").as_posix()}"').decision, "deny")

    def test_18_kb_commands_still_pass(self):
        for cmd in (f"{KB} init", f"{KB} upgrade --finish", f"{KB} obsidian open"):
            for tool in ("Bash", "PowerShell"):
                self.assertNotEqual(self.decide(tool, cmd).decision, "deny", f"{tool} {cmd}")

    def test_19_two_levels_up_nearest_and_none(self):
        deep = self.tmp / "a" / "b"
        shutil.copytree(self.V, deep)
        d = guard.decide(payload("Write", self.main, deep))
        self.assertEqual((d.zone, d.decision), ("Z7", "deny"))
        (self.tmp / "a" / ".obsidian").mkdir()  # 近的那個才是上層：遠的那份不歸這個知識庫
        self.assertEqual(guard.decide(payload("Write", self.main, deep)).zone, "Z11")
        d = guard.decide(payload("Write", self.tmp / "a" / ".obsidian" / "plugins" / "wiki-with-willy" / "main.js", deep))
        self.assertEqual((d.zone, d.decision), ("Z7", "deny"))
        shutil.rmtree(self.tmp / ".obsidian")
        self.assertEqual(self.decide("Write", self.main).zone, "Z11", "沒有上層 vault：照舊")


    def test_17b_folders_above_the_plugin_folder(self):
        """裁定 1：指令寫的目標是 <上>/.obsidian、<上>/.obsidian/plugins 這兩個夾本身也擋（整夾換掉或刪掉 main.js 就沒了）。"""
        obs, plugins = (self.tmp / ".obsidian").as_posix(), (self.tmp / ".obsidian" / "plugins").as_posix()
        inner = self.decide("Bash", f'rm -r "{self.plug.as_posix()}"')
        for cmd in (f'cp -r /tmp/evil/wiki-with-willy "{plugins}/"', f'rm -rf "{plugins}"', f'mv "{obs}" "{self.tmp.as_posix()}/x"',
                    f'cp x.json "{obs}/"', "rm -rf ../.obsidian/plugins"):
            d = self.decide("Bash", cmd)
            self.assertEqual((d.decision, d.zone, d.reason_code), ("deny", "Z7", inner.reason_code), cmd)
        for cmd in (f'Copy-Item -Recurse C:/evil/wiki-with-willy -Destination "{plugins}"', f'Remove-Item -Recurse "{obs}"'):
            d = self.decide("PowerShell", cmd)
            self.assertEqual((d.decision, d.zone), ("deny", "Z7"), cmd)
        # 寫明確檔名的照舊放行
        for cmd in (f'cp x.json "{obs}/app.json"', f'echo x > "{plugins}/obsidian-git/data.json"', f'rm "{obs}/workspace.json"',
                    f'rm -r "{plugins}/obsidian-git"'):
            self.assertNotEqual(self.decide("Bash", cmd).decision, "deny", cmd)

    def test_junction_in_the_vault_path(self):
        """裁定 2：知識庫路徑經過 junction／symlink 時，kb 用 realpath 放外掛；守門用 normalize 與 realpath 各找一次，任一個符合就認。"""
        import os
        import subprocess
        real_up = self.tmp / "real" / "我的筆記"
        (real_up / ".obsidian" / "plugins" / "wiki-with-willy").mkdir(parents=True)
        shutil.copytree(self.V, real_up / "willy")
        link = self.tmp / "side" / "link"
        link.parent.mkdir()
        try:
            if os.name == "nt":
                r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(real_up / "willy")], capture_output=True)
                if r.returncode != 0:
                    raise OSError(r.stderr.decode(errors="replace"))
            else:
                os.symlink(real_up / "willy", link, target_is_directory=True)
        except OSError as e:
            self.skipTest(f"這台建不了 junction／symlink：{e}")
        target = real_up / ".obsidian" / "plugins" / "wiki-with-willy" / "main.js"
        try:
            d = guard.decide(payload("Write", target, link))
            self.assertEqual((d.zone, d.decision), ("Z7", "deny"))
            d = guard.decide(payload("Bash", f'rm -rf "{(real_up / ".obsidian" / "plugins").as_posix()}"', link))
            self.assertEqual((d.zone, d.decision), ("Z7", "deny"))
            d = guard.decide(payload("Write", real_up / ".obsidian" / "app.json", link))
            self.assertEqual((d.zone, d.decision), ("Z11", "pass"))
        finally:
            if os.name == "nt":
                os.rmdir(link)  # 只拿掉 junction，不動它指到的夾
            else:
                os.unlink(link)


    def test_11_outer_is_looked_up_once_per_decision(self):
        """第 11 條：找上層在同一次判斷裡只算一次（一條指令有很多知識庫外的路徑也一樣）；下一次判斷重新找，不留到下一次。"""
        from unittest import mock
        outside = " ".join(f'"{(self.tmp / f"筆記{i}.md").as_posix()}"' for i in range(8))
        with mock.patch.object(guard, "_outer_plugin_of", wraps=guard._outer_plugin_of) as look:
            self.decide("Bash", f"cat {outside}")
            self.assertLessEqual(look.call_count, 2, "字面與 realpath 各一次")
            self.assertGreaterEqual(look.call_count, 1)
        self.assertEqual(self.decide("Write", self.main).zone, "Z7")
        shutil.rmtree(self.tmp / ".obsidian")
        self.assertEqual(self.decide("Write", self.main).zone, "Z11", "上層不見了，下一次判斷就不認")
        # 不經 decide 直接叫 classify 的（kb 自己的程式）永遠現找，不吃上一次判斷留下的
        from kb._lib.paths import normalize
        from kb._lib import sources as sources_lib
        vault_n, main_n = normalize(str(self.V), None), normalize(str(self.main), None)
        src = sources_lib.load(self.V)
        self.assertEqual(guard.classify(main_n, vault_n, src)[0], "Z11")
        self.plug.mkdir(parents=True)
        self.assertEqual(guard.classify(main_n, vault_n, src)[0], "Z7")
        self.assertIsNone(guard._OUTER_SEEN, "判斷結束就關掉")


    def source_edit(self, *args):
        import os
        import subprocess
        import sys
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT), PYTHONIOENCODING="utf-8")
        return subprocess.run([sys.executable, f"{ROOT}/scripts/kb.py", "source-edit", *args], capture_output=True, text=True,
                              encoding="utf-8", cwd=str(self.V), env=env)

    def tree(self):
        return sorted(f.relative_to(self.tmp).as_posix() for f in (self.tmp / ".obsidian").rglob("*"))

    def test_17c_classify_the_two_folders_themselves(self):
        """裁定 7：<上>/.obsidian、<上>/.obsidian/plugins 這兩個夾本身也歸 Z7（檔案工具、指令、source-edit 走同一個判斷）；讀放行。"""
        for rel in (".obsidian", ".obsidian/plugins"):
            d = self.decide("Write", self.tmp / rel)
            self.assertEqual((d.zone, d.decision), ("Z7", "deny"), rel)
            d = self.decide("Read", self.tmp / rel)
            self.assertEqual((d.zone, d.decision), ("Z7", "allow"), rel)
            self.assertNotEqual(self.decide("Bash", f'ls "{(self.tmp / rel).as_posix()}"').decision, "deny", rel)

    def test_17c_source_edit_cannot_remove_or_replace_the_plugin(self):
        evil = self.tmp / "別處" / "plugins" / "wiki-with-willy"
        evil.mkdir(parents=True)
        (evil / "main.js").write_text("// EVIL", encoding="utf-8")
        before = self.tree()
        for args in (("trash", "../.obsidian/plugins/wiki-with-willy", "--check"), ("trash", "../.obsidian/plugins", "--check"),
                     ("trash", "../.obsidian", "--check"), ("trash", "../.obsidian/plugins"),
                     ("rename", "../.obsidian/plugins", "plugins_old"), ("rename", "../.obsidian", "obs_old"),
                     ("rename", "../.obsidian/plugins/wiki-with-willy", "x"),
                     ("move", "../.obsidian/plugins", "--to", "../別處2"), ("move", "../.obsidian", "--to", "../別處2"),
                     ("move", "../別處/plugins", "--to", "../.obsidian"), ("move", "../別處/plugins/wiki-with-willy", "--to", "../.obsidian/plugins")):
            r = self.source_edit(*args)
            self.assertEqual(r.returncode, 3, f"{args}\n{r.stdout}{r.stderr}")
            self.assertIn("是 willy 自己的檔", r.stdout, args)
            self.assertEqual(self.tree(), before, args)
        self.assertEqual(self.main.read_text(encoding="utf-8"), "// 外掛")
        self.assertEqual((evil / "main.js").read_text(encoding="utf-8"), "// EVIL")

    def test_17c_source_edit_her_own_files_as_before(self):
        (self.tmp / ".obsidian" / "app.json").write_text("{}", encoding="utf-8")
        (self.tmp / "筆記.md").write_text("x", encoding="utf-8")
        for args in (("rename", "../.obsidian/app.json", "app2.json", "--check"), ("trash", "../筆記.md", "--check"),
                     ("trash", "../.obsidian/plugins/obsidian-git", "--check")):
            r = self.source_edit(*args)
            self.assertNotIn("willy 自己的檔", r.stdout, args)


    def test_17d_source_edit_cannot_take_the_folders_above_the_vault(self):
        """裁定 10：kb source-edit 的目標是知識庫（或上層外掛夾）的上層夾時拒絕——整夾丟掉或改名，知識庫與上層外掛都跟著走。
        有上層 vault、沒有上層 vault 都一樣。全部用 --check，另外不帶 --check 的改名也要被擋、夾還在。"""
        import os
        import subprocess
        import sys
        env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT), PYTHONIOENCODING="utf-8")

        def run(cwd, *args):
            return subprocess.run([sys.executable, f"{ROOT}/scripts/kb.py", "source-edit", *args], capture_output=True, text=True,
                                  encoding="utf-8", cwd=str(cwd), env=env)
        with_outer = self.tmp / "外" / "上層" / "willy"
        shutil.copytree(self.V, with_outer)
        (with_outer.parent / ".obsidian" / "plugins" / "wiki-with-willy").mkdir(parents=True)
        without = self.tmp / "無" / "夾" / "kb"
        shutil.copytree(self.V, without)
        (without.parent / "她的.md").write_text("x", encoding="utf-8")
        for kb_dir in (with_outer, without):
            for args in (("trash", "..", "--check"), ("rename", "..", "x", "--check"), ("trash", "../..", "--check"),
                         ("move", "..", "--to", "../../..", "--check"), ("rename", "..", "x")):
                r = run(kb_dir, *args)
                self.assertEqual(r.returncode, 3, f"{kb_dir.parent.name} {args}\n{r.stdout}{r.stderr}")
                self.assertIn("是 willy 自己的檔", r.stdout, args)
            self.assertTrue(kb_dir.is_dir(), kb_dir)
        # 上層夾裡她自己的檔照舊
        for args in (("trash", "../她的.md", "--check"), ("rename", "../她的.md", "改名.md", "--check")):
            r = run(without, *args)
            self.assertNotIn("willy 自己的檔", r.stdout, args)
            self.assertEqual(r.returncode, 0, f"{args}\n{r.stdout}{r.stderr}")


if __name__ == "__main__":
    unittest.main()
