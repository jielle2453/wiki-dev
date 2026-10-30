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


if __name__ == "__main__":
    unittest.main()
