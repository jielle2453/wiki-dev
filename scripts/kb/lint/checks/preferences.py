"""偏好月檢（D-504 決策 7、裁定 5）：距上次滿 preference_lint_days 天才跑（due），跑了記 lint.json 的 last_preference。
第六節 2 條以上開一件「偏好月檢」，附全表與字面相似過 preference_similar_ratio 的配對，意思上的重複、可合併、矛盾交給主對話 AI
照 note 的 preference.md 判斷（有才提議，沒有直接關、不提）；用在哪的 skill 不在、某組超過上限八成由程式判，各一件。"""
from kb._lib import profile
from kb.lint import runner, state

NAME = "偏好月檢"
NEAR = 0.8
REVIEW_NOTE = ("照 note 的 references/preference.md「偏好月檢」：看 data.rows 有沒有重複、可合併、矛盾的；有就擬好改法問她，"
               "她說好才 kb profile add 偏好 序號=<N> … 或 kb profile remove 偏好 序號=<N>；沒有就直接 kb pending resolve 這件、"
               "回答裡不提")


def due(ctx):
    last = state.load(ctx.vault).get("last_preference")
    n = ctx.days_since(last) if last else None
    return n is None or n >= ctx.config("preference_lint_days")


def _mark(ctx):
    def fn(data):
        data["last_preference"] = ctx.today
        return True
    state.change(ctx.vault, fn, ctx.turn_id)


def run(ctx):
    prefs = ctx.profile_strict().get("preferences") or []
    out = []
    rows = [{"序號": i, "偏好": p["text"], "用在哪": p.get("use") or profile.USE_ALL} for i, p in enumerate(prefs, 1)]
    if len(rows) >= 2:
        ratio = ctx.config("preference_similar_ratio")
        pairs = [[a["序號"], b["序號"], profile.similar(a["偏好"], b["偏好"])]
                 for k, a in enumerate(rows) for b in rows[k + 1:] if profile.same_group(a["用在哪"], b["用在哪"])]
        pairs = [x for x in pairs if x[2] >= ratio]
        text = f"每月看一次偏好：{len(rows)} 條有沒有重複、可以合併或互相矛盾的"
        if pairs:
            text += f"（字面很像的有 {len(pairs)} 對）"
        out.append(runner.finding(
            "preferences", "decide", "preference:review", text, items=[f"{r['用在哪']}:{r['偏好']}" for r in rows],
            data={"rows": rows, "similar": pairs,
                  "results": [{"label": "照偏好月檢看", "note": REVIEW_NOTE}]}))
    have = set(profile.use_choices(ctx.vault))
    gone = [r for r in rows if r["用在哪"] not in have]
    if gone:
        names = sorted({r["用在哪"] for r in gone})
        out.append(runner.finding(
            "preferences", "decide", "preference:skill_gone",
            f"有 {len(gone)} 條偏好用在 {'、'.join(names)}，這個功能已經不在了", items=[r["偏好"] for r in gone],
            data={"rows": gone, "results": [{"label": "一條一條問", "note": "問她這幾條要改成用在哪（kb profile add 偏好 序號=<N> 用在哪=<值>）"
                                                                    "或拿掉（kb profile remove 偏好 序號=<N>）"}]}))
    lim = profile.preference_limits(ctx.vault)
    near = []
    for group, label in (("opening", "整理成卡以外"), ("card", "整理成卡")):
        count, chars, _label = profile._limits_of(group, lim)
        mine = [p for p in prefs if profile._group(p.get("use") or profile.USE_ALL) == group]
        used = sum(len(p["text"]) for p in mine)
        if len(mine) > count * NEAR or used > chars * NEAR:
            near.append(f"{label}的偏好 {len(mine)}／{count} 條、{used}／{chars} 字")
    if near:
        out.append(runner.finding(
            "preferences", "decide", "preference:near_limit", "偏好快滿了：" + "；".join(near), items=near,
            data={"results": [{"label": "一起看要合併哪幾條", "note": "kb profile show --json 唸第六節，問她哪幾條可以合併或拿掉"}]}))
    _mark(ctx)
    return out
