"""偏好分用在哪（D-504，issue #12 第二階段）：schema 6 每條多 use；md 第六節「偏好｜用在哪｜來源｜日期」（舊表頭照全部讀）；
用在哪只收 全部／整理成卡／做文件／已裝的客製 skill；上限分開場那組與整理成卡兩組；--check 比對與字面相似度；序號= 改既有一條；
開場段分組、整理成卡不印；製卡材料只帶 全部＋整理成卡。"""
import json
import os
import shutil
import subprocess
import sys
import unittest

from tests._guard_fixture import ROOT, make_vault
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import profile  # noqa: E402

DAY = "2026-10-26"
HEAD6 = "| 偏好 | 用在哪 | 來源 | 日期 |"


def pref(text, use="全部", source="corrected", date=DAY):
    return {"text": text, "use": use, "source": source, "date": date}


def with_prefs(*prefs):
    d = profile.defaults(DAY)
    d["preferences"] = list(prefs)
    return d


def section6(text):
    return text[text.index("## 六、"):text.index("## 七、")]


class Schema6(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        self.p = self.V / ".system" / "profile.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_schema5_load_fills_use_all(self):
        """驗收 1：schema 5 load 後每條 use 是全部；寫回是 schema 6。"""
        data = profile.load(self.V)
        data["schema_version"] = 5
        data["preferences"] = [{"text": "回答先講結論", "source": "interview", "date": DAY}]
        self.p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        got = profile.load(self.V)
        self.assertEqual(got["preferences"], [pref("回答先講結論", source="interview")])
        self.assertEqual(got["schema_version"], 6)
        self.assertEqual(profile.SCHEMA_VERSION, 6)

    def test_render_and_parse_round_trip(self):
        d = with_prefs(pref("回答先講結論"), pref("報價單金額加千分位", "做文件"), pref("人名用連結", "整理成卡"))
        text = profile.render_text(d)
        sec = section6(text)
        self.assertIn(HEAD6 + "\n|---|---|---|---|\n", sec)
        self.assertIn("| 報價單金額加千分位 | 做文件 | 糾正 | 2026-10-26 |", sec)
        self.assertEqual(profile.parse_md(text)["preferences"], d["preferences"])

    def test_old_header_reads_as_all(self):
        """驗收 1：舊表頭（偏好｜來源｜日期，或只有偏好）照全部讀；用表頭的字判斷，3 欄的舊表也認得。"""
        text = profile.render_text(with_prefs(pref("回答先講結論")))
        old = text.replace(HEAD6 + "\n|---|---|---|---|\n| 回答先講結論 | 全部 | 糾正 | 2026-10-26 |",
                           "| 偏好 | 來源 | 日期 |\n|---|---|---|\n| 回答先講結論 | 糾正 | 2026-10-26 |\n| 日期帶星期 | | |")
        self.assertNotEqual(old, text)
        self.assertEqual(profile.parse_md(old)["preferences"],
                         [pref("回答先講結論"), {"text": "日期帶星期", "use": "全部", "source": None, "date": None}])

    def test_blank_use_is_all(self):
        text = profile.render_text(with_prefs(pref("回答先講結論"))).replace("| 回答先講結論 | 全部 |", "| 回答先講結論 |  |")
        self.assertEqual(profile.parse_md(text)["preferences"][0]["use"], "全部")

    def test_unknown_use_refused_with_choices(self):
        """驗收 2：不認識的用在哪擋，訊息列出能填的值（含已裝的客製 skill）。"""
        text = profile.render_text(with_prefs(pref("也找工商時報", "每日新聞")))
        with self.assertRaises(profile.ProfileError) as e:
            profile.parse_md(text, uses=["全部", "整理成卡", "做文件", "每日議題"])
        self.assertIn("全部、整理成卡、做文件、每日議題", e.exception.message)
        got = profile.parse_md(text.replace("每日新聞", "每日議題"), uses=["全部", "整理成卡", "做文件", "每日議題"])
        self.assertEqual(got["preferences"][0]["use"], "每日議題")

    def test_uses_lists_installed_skills(self):
        self.assertEqual(profile.use_choices(self.V), ["全部", "整理成卡", "做文件"])
        sk = self.V / ".claude" / "skills" / "每日議題"
        sk.mkdir(parents=True)
        (sk / "SKILL.md").write_text("---\nname: 每日議題\n---\n", encoding="utf-8")
        (self.V / ".claude" / "skills" / "空夾").mkdir()
        self.assertEqual(profile.use_choices(self.V), ["全部", "整理成卡", "做文件", "每日議題"])

    def test_skill_removed_load_does_not_refuse(self):
        """驗收 2：skill 被移除後 load 不擋。"""
        d = profile.load(self.V)
        d["preferences"] = [pref("也找工商時報", "每日議題")]
        self.p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(profile.load(self.V)["preferences"][0]["use"], "每日議題")


class Limits(unittest.TestCase):
    """驗收 5：開場那組（整理成卡以外）與整理成卡分開算、互不佔用。"""

    LIM = {"preference_max": 3, "preference_max_chars": 30, "preference_card_max": 2, "preference_card_max_chars": 10}

    def parse(self, *prefs):
        return profile.parse_md(profile.render_text(with_prefs(*prefs)), **self.LIM)

    def test_groups_count_separately(self):
        got = self.parse(pref("一一"), pref("二二", "做文件"), pref("三三", "每日議題"), pref("卡一", "整理成卡"),
                         pref("卡二", "整理成卡"))
        self.assertEqual(len(got["preferences"]), 5)

    def test_opening_group_over_count(self):
        with self.assertRaises(profile.ProfileError) as e:
            self.parse(pref("一一"), pref("二二", "做文件"), pref("三三"), pref("四四", "做文件"))
        self.assertIn("最多 3 條", e.exception.message)

    def test_card_group_over_count_and_chars(self):
        with self.assertRaises(profile.ProfileError) as e:
            self.parse(pref("卡一", "整理成卡"), pref("卡二", "整理成卡"), pref("卡三", "整理成卡"))
        self.assertIn("整理成卡", e.exception.message)
        with self.assertRaises(profile.ProfileError):
            self.parse(pref("卡" * 11, "整理成卡"))
        self.parse(pref("卡" * 10, "整理成卡"), pref("一" * 30))

    def test_defaults(self):
        from kb._lib import config
        base = config.defaults()
        self.assertEqual({k: base[k] for k in self.LIM},
                         {"preference_max": 20, "preference_max_chars": 1000, "preference_card_max": 5,
                          "preference_card_max_chars": 200})
        self.assertEqual(base["preference_similar_ratio"], 0.35)
        self.assertEqual(base["preference_lint_days"], 30)

    def test_edit_refuses_by_group(self):
        d = with_prefs(pref("卡一", "整理成卡"), pref("卡二", "整理成卡"))
        with self.assertRaises(profile.ProfileError) as e:
            profile.edited(d, "偏好", "add", {"偏好": "卡三", "用在哪": "整理成卡"}, today=DAY, **self.LIM)
        self.assertIn("整理成卡", e.exception.message)
        out, res = profile.edited(d, "偏好", "add", {"偏好": "回答先講結論"}, today=DAY, **self.LIM)
        self.assertTrue(res["changed"])
        self.assertEqual(out["preferences"][-1], pref("回答先講結論"))


class EditAndCheck(unittest.TestCase):
    def setUp(self):
        self.d = with_prefs(pref("回答先講結論"), pref("日期帶星期"), pref("報價單金額加千分位", "做文件"),
                            pref("人名用連結", "整理成卡"))

    def test_add_with_use_message_says_where(self):
        """決策 6：成功句講明用在哪。"""
        cases = {"全部": "記下了，每次都照做：", "做文件": "記下了，只在做文件時用：", "整理成卡": "記下了，只在整理成卡時用：",
                 "每日議題": "記下了，只在每日議題時用："}
        for use, head in cases.items():
            with self.subTest(use=use):
                _out, res = profile.edited(self.d, "偏好", "add", {"偏好": "新的一條", "用在哪": use}, today=DAY)
                self.assertEqual(res["message"], head + "新的一條")

    def test_add_without_use_is_all(self):
        out, _res = profile.edited(self.d, "偏好", "add", {"偏好": "新的一條"}, today=DAY)
        self.assertEqual(out["preferences"][-1]["use"], "全部")

    def test_same_text_in_another_group_is_duplicate(self):
        _out, res = profile.edited(self.d, "偏好", "add", {"偏好": "回答先講結論", "用在哪": "做文件"}, today=DAY)
        self.assertFalse(res["changed"])
        self.assertIn("已經有了", res["message"])

    def test_change_by_number(self):
        """驗收 7：序號=N 改第 N 條：句子與用在哪改了、來源 corrected、日期今天；N 不存在擋。"""
        out, res = profile.edited(self.d, "偏好", "add", {"序號": "1", "偏好": "回答先講結論、簡短不囉嗦"}, today="2026-11-01")
        self.assertTrue(res["changed"])
        self.assertEqual(out["preferences"][0], pref("回答先講結論、簡短不囉嗦", date="2026-11-01"))
        self.assertEqual(len(out["preferences"]), 4)
        out, _res = profile.edited(self.d, "偏好", "add", {"序號": "3", "用在哪": "全部"}, today="2026-11-01")
        self.assertEqual(out["preferences"][2], pref("報價單金額加千分位", date="2026-11-01"))
        for bad in ("9", "0", "x"):
            with self.subTest(n=bad), self.assertRaises(profile.ProfileError):
                profile.edited(self.d, "偏好", "add", {"序號": bad, "偏好": "x"}, today=DAY)

    def test_similar_ratio(self):
        """裁定 4：字元二元組 Jaccard（先拿掉空白與標點），門檻 0.35。"""
        sim = profile.similar
        self.assertGreaterEqual(sim("回答先講結論", "回答要先講結論"), 0.35)
        self.assertGreaterEqual(sim("日期帶星期", "日期不用帶星期了"), 0.35)
        self.assertLess(sim("講重點就好，不要囉嗦", "回答先講結論"), 0.35)
        self.assertEqual(sim("報價單金額加千分位", "回答先講結論"), 0.0)
        self.assertEqual(sim("回答先講結論", "回答，先講 結論"), 1.0)

    def test_check_compares_group_and_all(self):
        """驗收 6：回同組＋全部的每一條與相似度，過門檻的標出；意思像、字不像的不標但列在 compare。"""
        got = profile.preference_check(self.d, "回答要先講結論", "全部")
        self.assertEqual(got["would"], "add")
        self.assertEqual([c["序號"] for c in got["compare"]], [1, 2, 3, 4])  # 全部要跟每一組比
        self.assertEqual(got["similar"], [1])
        self.assertEqual((got["group_count"], got["group_max"], got["over_limit"]), (4, 20, False))
        got = profile.preference_check(self.d, "日期不用帶星期了", "做文件")
        self.assertEqual([c["序號"] for c in got["compare"]], [1, 2, 3])
        self.assertEqual(got["similar"], [2])
        got = profile.preference_check(self.d, "講重點就好，不要囉嗦", "全部")
        self.assertEqual(got["similar"], [])
        self.assertIn("回答先講結論", [c["偏好"] for c in got["compare"]])
        got = profile.preference_check(self.d, "卡上日期寫西元", "整理成卡")
        self.assertEqual([c["序號"] for c in got["compare"]], [1, 2, 4])
        self.assertEqual((got["group_count"], got["group_max"]), (2, 5))

    def test_check_over_limit(self):
        got = profile.preference_check(self.d, "卡" * 200, "整理成卡")
        self.assertTrue(got["over_limit"])

    def test_check_change_by_number_skips_itself(self):
        got = profile.preference_check(self.d, "回答先講結論、簡短不囉嗦", "全部", number=1)
        self.assertEqual(got["would"], "change")
        self.assertNotIn(1, [c["序號"] for c in got["compare"]])
        self.assertEqual(got["group_count"], 3)

    def test_card_material_only_all_and_card(self):
        """驗收 4：cards batch 的 profile.preferences 只有 全部＋整理成卡，順序照表。"""
        self.assertEqual(profile.card_types_for_todo(self.d)["preferences"], ["回答先講結論", "日期帶星期", "人名用連結"])

    def test_schema_show_has_use_choices(self):
        sec = profile.sections_schema(self.d, uses=["全部", "整理成卡", "做文件", "每日議題"])[5]
        cols = {c["name"]: c for c in sec["columns"]}
        self.assertEqual(cols["用在哪"]["choices"], ["全部", "整理成卡", "做文件", "每日議題"])
        self.assertEqual(sec["rows"][2], {"序號": 3, "偏好": "報價單金額加千分位", "用在哪": "做文件", "來源": "糾正", "日期": DAY})
        self.assertEqual(set(sec["limits"]), {"opening", "card"})
        self.assertEqual(sec["limits"]["card"]["used_count"], 1)


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kb(self, *args, code=0):
        r = run_kb(*args, cwd=self.V)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return r.stdout

    def test_add_use_and_refusal(self):
        self.assertEqual(self.kb("profile", "add", "偏好", "偏好=報價單金額加千分位", "用在哪=做文件").strip(),
                         "記下了，只在做文件時用：報價單金額加千分位")
        out = self.kb("profile", "add", "偏好", "偏好=也找工商時報", "用在哪=每日議題", code=3)
        self.assertIn("全部、整理成卡、做文件", out)
        sk = self.V / ".claude" / "skills" / "每日議題"
        sk.mkdir(parents=True)
        (sk / "SKILL.md").write_text("---\nname: 每日議題\n---\n", encoding="utf-8")
        self.kb("profile", "add", "偏好", "偏好=也找工商時報", "用在哪=每日議題")
        md = (self.V / "系統" / "客戶設定檔.md").read_text(encoding="utf-8")
        self.assertIn("| 也找工商時報 | 每日議題 | 糾正 |", md)
        self.assertEqual(profile.load(self.V)["schema_version"], 6)
        shutil.rmtree(sk)
        self.assertEqual(profile.load(self.V)["preferences"][-1]["use"], "每日議題")
        self.kb("profile", "show")

    def test_check_does_not_write(self):
        self.kb("profile", "add", "偏好", "偏好=回答先講結論")
        before = [(p, p.read_bytes()) for p in (self.V / ".system" / "profile.json", self.V / "系統" / "客戶設定檔.md")]
        got = json.loads(self.kb("profile", "add", "偏好", "偏好=回答要先講結論", "--check", "--json"))
        self.assertEqual((got["would"], got["use"], got["similar"]), ("add", "全部", [1]))
        self.assertEqual(got["compare"], [{"序號": 1, "偏好": "回答先講結論", "用在哪": "全部", "similar": got["compare"][0]["similar"]}])
        self.assertEqual([(p, p.read_bytes()) for p, _b in before], before)
        text = self.kb("profile", "add", "偏好", "偏好=回答要先講結論", "--check")
        self.assertIn("回答先講結論", text)

    def test_change_by_number_cli(self):
        self.kb("profile", "add", "偏好", "偏好=回答先講結論")
        self.kb("profile", "add", "偏好", "序號=1", "偏好=回答先講結論、簡短不囉嗦")
        self.assertEqual([p["text"] for p in profile.load(self.V)["preferences"]], ["回答先講結論、簡短不囉嗦"])
        self.kb("profile", "add", "偏好", "序號=5", "偏好=x", code=3)

    def test_apply_unknown_use_refused(self):
        self.kb("profile", "add", "偏好", "偏好=回答先講結論")
        md = self.V / "系統" / "客戶設定檔.md"
        md.write_text(md.read_text(encoding="utf-8").replace("| 回答先講結論 | 全部 |", "| 回答先講結論 | 每日新聞 |"),
                      encoding="utf-8")
        out = self.kb("profile", "apply", code=3)
        self.assertIn("全部、整理成卡、做文件", out)


class Opening(unittest.TestCase):
    """驗收 3：全部一條一行；做文件、客製 skill 各自分組加小標；整理成卡不出現；沒有偏好不印。"""

    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def context(self, *prefs):
        p = self.V / ".system" / "profile.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        data["preferences"] = list(prefs)
        data["schema_version"] = 3  # fixture 是舊版；load 遷移時保留每條的 use
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        payload = {"session_id": "s", "cwd": str(self.V), "hook_event_name": "SessionStart", "source": "startup"}
        r = subprocess.run([sys.executable, str(ROOT / "hooks" / "session.py")], input=json.dumps(payload),
                           capture_output=True, text=True, encoding="utf-8", cwd=str(self.V),
                           env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]

    def test_grouped(self):
        from hooks import session
        ctx = self.context(pref("回答先講結論"), pref("報價單金額加千分位", "做文件"), pref("人名用連結", "整理成卡"),
                           pref("也找工商時報的新聞", "每日議題"), pref("日期帶星期"), pref("附報價日期", "做文件"))
        self.assertTrue(ctx.endswith("\n" + session.PREFERENCES_HEAD + "\n- 回答先講結論\n- 日期帶星期\n做文件時：\n"
                                     "- 報價單金額加千分位\n- 附報價日期\n每日議題：\n- 也找工商時報的新聞"), ctx[-200:])
        self.assertNotIn("人名用連結", ctx)

    def test_only_card_prefs_prints_nothing(self):
        self.assertNotIn("客戶偏好", self.context(pref("人名用連結", "整理成卡")))
        self.assertNotIn("客戶偏好", self.context())


if __name__ == "__main__":
    unittest.main()
