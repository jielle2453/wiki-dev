"""偏好月檢（D-504 決策 7、裁定 2、5，驗收 8）：滿 preference_lint_days 天才跑、跑了記 last_preference；第六節 2 條以上開一題附全表
與字面相似過門檻的配對；skill 不在、某組超過八成各一題；不到 30 天不跑也不關它的件；AI 處理後（resolve）關題。"""
import shutil
import unittest
from unittest import mock

from tests import _lint as L
from kb._lib import pending, profile, turn  # noqa: E402
from kb.lint import checks, runner, state  # noqa: E402
from kb.lint.checks import preferences  # noqa: E402

DAY = "2026-10-27"


def pref(text, use="全部"):
    return {"text": text, "use": use, "source": "corrected", "date": DAY}


class Check(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def put(self, *prefs):
        d = profile.load(self.V) or profile.defaults(DAY)
        d["preferences"] = list(prefs)
        profile.write(self.V, d, turn.start(self.V, None, "")["turn"])

    def run_check(self, today=DAY):
        return {f["key"]: f for f in preferences.run(L.ctx(self.V, today=today))}

    def test_review_has_whole_table_and_similar_pairs(self):
        self.put(pref("回答先講結論"), pref("報價單金額加千分位", "做文件"), pref("回答要先講結論"), pref("講重點就好，不要囉嗦"))
        got = self.run_check()
        self.assertEqual(set(got), {"preference:review"})
        f = got["preference:review"]
        self.assertEqual(f["kind"], "decide")
        self.assertEqual([r["序號"] for r in f["data"]["rows"]], [1, 2, 3, 4])
        self.assertEqual(f["data"]["rows"][1], {"序號": 2, "偏好": "報價單金額加千分位", "用在哪": "做文件"})
        self.assertEqual([p[:2] for p in f["data"]["similar"]], [[1, 3]])
        self.assertIn("4 條", f["text"])
        self.assertIn("preference.md", f["data"]["results"][0]["note"])
        self.assertEqual(state.load(self.V)["last_preference"], DAY)

    def test_one_preference_no_review(self):
        self.put(pref("回答先講結論"))
        self.assertEqual(self.run_check(), {})
        self.assertEqual(state.load(self.V)["last_preference"], DAY, "跑過就記日子")

    def test_skill_gone(self):
        self.put(pref("也找工商時報的新聞", "每日議題"))
        f = self.run_check()["preference:skill_gone"]
        self.assertIn("每日議題", f["text"])
        sk = self.V / ".claude" / "skills" / "每日議題"
        sk.mkdir(parents=True)
        (sk / "SKILL.md").write_text("---\nname: 每日議題\n---\n", encoding="utf-8")
        self.assertNotIn("preference:skill_gone", self.run_check())

    def test_near_limit(self):
        self.put(*[pref(f"卡上第{i}條", "整理成卡") for i in range(5)])
        f = self.run_check()["preference:near_limit"]
        self.assertIn("整理成卡的偏好 5／5 條", f["text"])
        self.put(*[pref(f"卡上第{i}條", "整理成卡") for i in range(4)])
        self.assertNotIn("preference:near_limit", self.run_check(), "4／5 剛好八成不算超過")

    def test_due(self):
        c = L.ctx(self.V, today=DAY)
        self.assertTrue(preferences.due(c), "沒跑過就跑")
        state.change(self.V, lambda d: d.update(last_preference="2026-10-01") or True)
        self.assertFalse(preferences.due(c))
        state.change(self.V, lambda d: d.update(last_preference="2026-09-27") or True)
        self.assertTrue(preferences.due(c), "滿 30 天")

    def test_registered(self):
        self.assertIn(preferences, checks.CHECKS)
        self.assertLess(checks.CHECKS.index(preferences), checks.CHECKS.index(checks.todo))


class Monthly(unittest.TestCase):
    """驗收 8（裁定 5）：滿 30 天開一題附全表；不到 30 天不跑、件不關；AI 處理後關題；條件消失（剩 1 條）下次跑時關。"""

    def setUp(self):
        self.tmp, self.V, self.raw = L.make()
        d = profile.load(self.V) or profile.defaults(DAY)
        d["preferences"] = [pref("回答先講結論"), pref("回答要先講結論")]
        profile.write(self.V, d, turn.start(self.V, None, "")["turn"])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def items(self):
        return {i["key"]: i for i in pending.load(self.V)["items"] if i["kind"] == "lint" and i["key"].startswith("preference:")}

    def lint(self, today):
        with mock.patch.object(checks, "CHECKS", [preferences]):
            return runner.run(self.V, today=today)

    def test_monthly_cycle(self):
        self.lint("2026-10-27")
        item = self.items()["preference:review"]
        self.assertEqual((item["status"], len(item["data"]["rows"])), ("open", 2))
        self.assertEqual(state.load(self.V)["last_preference"], "2026-10-27")
        d = profile.load(self.V)
        d["preferences"] = d["preferences"][:1]
        profile.write(self.V, d, turn.start(self.V, None, "")["turn"])
        self.lint("2026-11-10")
        self.assertEqual(self.items()["preference:review"]["status"], "open", "不到 30 天不跑，也不關它的件")
        self.assertEqual(state.load(self.V)["last_preference"], "2026-10-27")
        self.lint("2026-11-26")
        self.assertEqual(self.items()["preference:review"]["status"], "done", "滿 30 天再跑：剩 1 條，題目不成立就關")

    def test_ai_resolves_then_closed(self):
        self.lint("2026-10-27")
        pid = self.items()["preference:review"]["id"]
        pending.resolve(self.V, pid, "偏好月檢：沒有要改的", turn.start(self.V, None, "")["turn"])
        self.assertEqual(self.items()["preference:review"]["status"], "done")
        self.lint("2026-11-27")
        self.assertEqual(self.items()["preference:review"]["status"], "done", "表沒變、答過不重開")


if __name__ == "__main__":
    unittest.main()
