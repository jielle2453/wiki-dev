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
                    ".obsidian/plugins/wiki-with-willy2/main.js", ".obsidian/plugins"):
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


if __name__ == "__main__":
    unittest.main()
