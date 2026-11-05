"""多人共用 2：是誰與誰的（design/specs/2026-11-01-多人共用2-是誰與誰的.md）。
這份測試不靠第 1 份的流水檔：「兩台」用換 env.json 的機器名（kb._lib.env.machine_name）模擬。"""
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests import _cards
from tests.test_lib_inventory_scan import make_inv_vault
from tests._guard_fixture import KB, ROOT
from kb._lib import env, people, profile, turn  # noqa: E402


def read_profile(V):
    return json.loads((Path(V) / ".system" / "profile.json").read_text(encoding="utf-8"))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_inv_vault()
        _cards.scan_apply(self.V)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kb(self, *args):
        # tmp 在 ~/AppData 底下（系統夾，來源登記會擋）：家目錄指到 tmp/home，同 test_scripts_folders_cli
        env_ = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT), USERPROFILE=str(Path(self.tmp) / "home"),
                    HOME=str(Path(self.tmp) / "home"))
        return subprocess.run([sys.executable, str(KB), *args], capture_output=True, text=True, encoding="utf-8",
                              cwd=str(self.V), env=env_)

    def as_machine(self, name):
        """程式內模擬另一台電腦（env.json 照機器名分）；kb 子行程用真的機器名。"""
        return mock.patch("platform.node", return_value=name)

    def multi(self, n=3):
        r = self.kb("profile", "set", "people", str(n))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class TestPeopleLib(Base):
    def test_single_by_default(self):
        self.assertEqual(people.count(self.V), 1)
        self.assertFalse(people.multi(self.V))
        self.assertIsNone(people.me(self.V))

    def test_visible(self):
        self.assertTrue(people.visible(["小王"], None))
        self.assertTrue(people.visible("team", "老闆"))
        self.assertTrue(people.visible(None, "老闆"))
        self.assertTrue(people.visible(["老闆", "小王"], "老闆"))
        self.assertFalse(people.visible(["小王"], "老闆"))
        self.assertFalse(people.visible("小王", "老闆"))

    def test_parse_whose(self):
        self.assertEqual(people.parse_whose("全隊"), "team")
        self.assertEqual(people.parse_whose("小王,老闆"), ["小王", "老闆"])
        self.assertEqual(people.parse_whose(""), "team")

    def test_default_name_git_then_login(self):
        class R:
            returncode, stdout = 0, "wang\n"
        with mock.patch("subprocess.run", return_value=R()):
            self.assertEqual(people.default_name(self.V), "wang")
        with mock.patch("subprocess.run", side_effect=OSError), mock.patch("getpass.getuser", return_value="winuser"):
            self.assertEqual(people.default_name(self.V), "winuser")


class TestProfilePeople(Base):
    def test_single_render_unchanged(self):
        text = (self.V / "系統" / "客戶設定檔.md").read_text(encoding="utf-8")
        self.assertIn("## 五、關於你\n", text.replace("\r\n", "\n"))
        self.assertNotIn("幾個人用", text)

    def test_set_people_renders_section5(self):
        self.multi(3)
        self.assertEqual(read_profile(self.V)["people"], 3)
        text = (self.V / "系統" / "客戶設定檔.md").read_text(encoding="utf-8")
        self.assertIn("## 五、關於你們（公司與團隊成員）", text)
        self.assertIn("幾個人用：3", text)
        self.assertTrue(people.multi(self.V))

    def test_set_people_bad(self):
        for bad in ("0", "abc", "-1"):
            self.assertEqual(self.kb("profile", "set", "people", bad).returncode, 3)

    def test_bad_people_line_in_md(self):
        self.multi(3)
        p = self.V / "系統" / "客戶設定檔.md"
        p.write_text(p.read_text(encoding="utf-8").replace("幾個人用：3", "幾個人用：很多"), encoding="utf-8", newline="\n")
        r = self.kb("profile", "check")
        self.assertEqual(r.returncode, 3, r.stdout)
        self.assertIn("第 5 節", r.stdout)

    def test_member_label_roundtrip(self):
        d = profile.defaults()
        d["people"] = 2
        d["about"] = [{"name": "小王", "kind": "person", "aliases": [], "source": "confirmed", "date": "2026-11-01"}]
        text = profile.render_text(d)
        self.assertIn("| 小王 | 成員 |", text)
        self.assertEqual(profile.parse_md(text)["about"][0]["kind"], "person")


class TestBuildPeople(Base):
    def test_people_number(self):
        from kb._lib.build import people_number
        self.assertEqual([people_number(x) for x in ("我們六個人", "3 個人", "十二人", "大家一起用")], [6, 3, 12, None])

    def test_build_set_people_without_profile_yet(self):
        """建置訪談時設定檔還沒建：只存原話、不出錯（設定檔建好後 AI 跑 kb profile set people）。"""
        d = Path(self.tmp) / "新知識庫"
        d.mkdir()
        env_ = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))

        def run(*args):
            return subprocess.run([sys.executable, str(KB), *args], capture_output=True, text=True, encoding="utf-8",
                                  cwd=str(d), env=env_)
        self.assertEqual(run("build", "start").returncode, 0)
        turn.start(d, "sid-x", "/wiki-with-willy:build")
        r = run("build", "set", "people", "我們六個人")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("六個人", r.stdout)


class TestNewerFormat(Base):
    def put_newer(self):
        d = Path(self.V) / ".system" / "streams" / "agenda"
        d.mkdir(parents=True, exist_ok=True)
        row = {"v": 99, "app": "0.99.0", "op": "create", "id": "a-99999999", "seq": 1, "base": 0, "by": "m-zzzzzzzz",
               "who": None, "at": "2026-11-01T10:00:00", "turn": "t", "set": {"kind": "meeting", "date": "2099-01-02",
               "text": "新版寫的", "status": "open", "新欄位": 1}}
        (d / "m-zzzzzzzz.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    def test_write_refused_read_ok(self):
        self.put_newer()
        r = self.kb("agenda", "add", "--kind", "提醒", "--date", "2099-01-03", "--text", "舊版想記")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("0.99.0", r.stdout)
        self.assertIn("新的對話", r.stdout.replace("開一個新對話", "新的對話"))
        r = self.kb("agenda", "list", "--all", "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("新版寫的", r.stdout)


class TestWho(Base):
    def test_single(self):
        r = self.kb("who", "--json")
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout)
        self.assertFalse(got["multi"])
        self.assertIsNone(got["me"])
        self.assertEqual(got["people"], 1)

    def test_set_single_refused(self):
        self.assertEqual(self.kb("who", "set", "小王").returncode, 3)

    def test_set_multi(self):
        self.multi(3)
        r = self.kb("who", "set", "小王")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(env.person(self.V), "小王")
        data = read_profile(self.V)
        self.assertIn({"name": "小王", "kind": "person"}, [{"name": a["name"], "kind": a["kind"]} for a in data["about"]])
        text = (self.V / "系統" / "客戶設定檔.md").read_text(encoding="utf-8")
        self.assertIn("| 小王 | 成員 |", text)
        got = json.loads(self.kb("who", "--json").stdout)
        self.assertEqual(got["me"], "小王")
        self.assertEqual(got["members"], ["小王"])
        self.assertEqual(self.kb("who", "set", "小王").returncode, 0)  # 重複不加第二列
        self.assertEqual(sum(1 for a in read_profile(self.V)["about"] if a["name"] == "小王"), 1)

    def test_md_not_rendered_yet(self):
        """#42 問題 12：新 clone 第一句 hook 畫 md 之前（設定檔在、md 不在），who set、profile show 先畫出 md 再做，不叫人跑 kb init。"""
        self.multi(3)
        md = self.V / "系統" / "客戶設定檔.md"
        md.unlink()
        r = self.kb("who", "set", "小王")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("| 小王 | 成員 |", md.read_text(encoding="utf-8"))
        self.assertEqual(profile.status(self.V)["state"], "ok")  # 畫出來的不當手改
        md.unlink()
        r = self.kb("profile", "show")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("kb init", r.stdout)
        self.assertEqual(profile.status(self.V)["state"], "ok")

    def test_no_profile_keeps_message(self):
        """真的沒有設定（profile.json 也不在）：照舊說還沒有設定檔、不畫 md。"""
        from kb import profile_cli
        (self.V / ".system" / "profile.json").unlink()
        (self.V / "系統" / "客戶設定檔.md").unlink(missing_ok=True)
        r = self.kb("profile", "show")
        self.assertEqual((r.returncode, r.stdout.strip()), (3, profile_cli.MISSING))
        self.assertFalse((self.V / "系統" / "客戶設定檔.md").exists())


class TestPreferencesWhose(Base):
    def test_single_has_no_whose(self):
        r = self.kb("profile", "add", "偏好", "偏好=回答短一點")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("whose", read_profile(self.V)["preferences"][0])

    def test_multi_default_mine_and_team(self):
        self.multi(3)
        self.kb("who", "set", "小王")
        self.assertEqual(self.kb("profile", "add", "偏好", "偏好=回答短一點").returncode, 0)
        self.assertEqual(self.kb("profile", "add", "偏好", "偏好=講金額都用萬元", "--whose", "全隊").returncode, 0)
        prefs = read_profile(self.V)["preferences"]
        self.assertEqual([p.get("whose") for p in prefs], ["小王", "team"])

    def test_whose_survives_md_apply(self):
        self.multi(3)
        self.kb("who", "set", "小王")
        self.kb("profile", "add", "偏好", "偏好=回答短一點")
        p = self.V / "系統" / "客戶設定檔.md"
        p.write_text(p.read_text(encoding="utf-8").replace("回答短一點", "回答短短的"), encoding="utf-8", newline="\n")
        r = self.kb("profile", "apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(read_profile(self.V)["preferences"][0]["text"], "回答短短的")


if __name__ == "__main__":
    unittest.main()
