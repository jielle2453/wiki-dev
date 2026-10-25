"""lint 第三輪測試報告的修正（design/reports/lint-測試-3.md）：T-35、T-36、T-37（cleared 只在跑成功時記、壞掉的 bases 不擋）。
T-33、T-34、T-37 的 purge 部分在 test_lib_purge 的 LintDerived。"""
import json
import shutil
import types
import unittest
from unittest import mock

from tests import _lint as L
from kb._lib import pending, renders, skeleton, turn  # noqa: E402
from kb.lint import checks, runner  # noqa: E402
from kb.lint.checks import versions  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = L.make()
        self.t = turn.start(self.V, None, "")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class T35NoSkeletonRecord(Base):
    def test_old_vault_without_skeleton_json(self):
        (self.V / skeleton.SKELETON_JSON).unlink(missing_ok=True)
        found = versions.run(L.ctx(self.V))
        (num,) = [f for f in found if f["kind"] == "number"]
        self.assertIn("old_schema", num["data"])
        mods = [m for m in checks.CHECKS if m is versions]
        with mock.patch.object(checks, "CHECKS", mods):
            got = runner.run(self.V)
        self.assertEqual(got["failed_checks"], [])
        self.assertFalse((self.V / ".system" / "hook-errors.log").exists())
        self.assertIn("versions", got["numbers"])

    def test_broken_skeleton_json_is_failed(self):
        (self.V / skeleton.SKELETON_JSON).write_text("{壞", encoding="utf-8")
        with self.assertRaises(ValueError):
            versions.run(L.ctx(self.V))


class T36RemovedOnlyExisting(Base):
    def add(self, name):
        return pending.add(self.V, "unreadable", [f"f-{abs(hash(name)) % 10**8:08d}"], f"「{name}」讀不到", "檔案壞了", self.t)

    def test_reverted_items_not_reported_removed(self):
        for n in ("甲.pdf", "乙.pdf", "丙.pdf"):
            self.add(n)
        later = turn.start(self.V, None, "")["turn"]
        self.t = later
        gone = [self.add("丁.pdf"), self.add("戊.pdf")]
        data = pending.load(self.V)
        data["items"] = [i for i in data["items"] if i["id"] not in gone]  # 退回拿掉那兩件（JSON 回到三件、md 還是五件）
        (self.V / pending.PENDING_POSIX).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        md = self.V / pending.MD_POSIX
        md.write_text("\n".join(ln for ln in md.read_text(encoding="utf-8").splitlines() if "丁.pdf" not in ln and "戊.pdf" not in ln)
                      + "\n", encoding="utf-8")
        self.add("己.pdf")
        for item in [i for i in pending.load(self.V)["items"] if i["kind"] == "handedit"]:
            self.assertFalse(set(gone) & {c["id"] for c in item["data"]["diff"]["removed"]})


class T37ClearedOnlyWhenRan(Base):
    def test_failed_check_does_not_clear(self):
        ok = types.SimpleNamespace(NAME="守門", run=lambda ctx: [runner.finding("guard", "decide", "guard_stale", "守門沒在跑")])
        ok.__name__ = "kb.lint.checks.guard"
        with mock.patch.object(checks, "CHECKS", [ok]):
            runner.run(self.V)
        (item,) = [i for i in pending.load(self.V)["items"] if i.get("key") == "guard_stale"]
        pending.dismiss(self.V, item["id"], self.t)

        def boom(ctx):
            raise ValueError("讀不到")
        bad = types.SimpleNamespace(NAME="守門", run=boom)
        bad.__name__ = "kb.lint.checks.guard"
        with mock.patch.object(checks, "CHECKS", [bad]):
            runner.run(self.V)
        (item,) = [i for i in pending.load(self.V)["items"] if i.get("key") == "guard_stale"]
        self.assertFalse(item.get("cleared"))

    def test_malformed_bases_are_dropped(self):
        (self.V / renders.RENDERS_POSIX).write_text(json.dumps(
            {"schema_version": 1, "files": {}, "bases": {"系統/待處理.md": {"text": "x", "lines": [["a"], 5, ["b", "p-1"]]}}}),
            encoding="utf-8")
        self.assertEqual(renders.base(self.V, "系統/待處理.md"), ("x", [("b", "p-1")]))


if __name__ == "__main__":
    unittest.main()
