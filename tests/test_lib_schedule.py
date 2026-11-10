"""背景比對（D-536）驗收 8、11：schedule.ensure 的五種結果，schtasks 換替身；failed 記一件待處理、之後設好了關掉。"""
import json
import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests._guard_fixture import ROOT, make_vault
from kb._lib import paths, pending, schedule


REAL_SCHTASKS = schedule._schtasks


class FakeSchtasks:
    """記著建過的工作 xml；fail 有值時 /create 失敗。"""

    def __init__(self):
        self.tasks, self.calls, self.fail = {}, [], None

    def __call__(self, argv):
        self.calls.append(argv[1])
        name = argv[argv.index("/tn") + 1]
        if argv[1] == "/query":
            return (0, self.tasks[name]) if name in self.tasks else (1, "錯誤: 系統找不到指定的檔案。")
        if argv[1] == "/delete":
            self.tasks.pop(name, None)
            return 0, ""
        if argv[1] == "/create":
            if self.fail:
                return 1, self.fail
            xml = Path(argv[argv.index("/xml") + 1]).read_text(encoding="utf-16")
            self.tasks[name] = xml
            return 0, ""
        raise AssertionError(argv)


class Ensure(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        self.fake = FakeSchtasks()
        for p in (mock.patch.object(schedule, "_schtasks", self.fake), mock.patch.object(schedule, "WINDOWS", True),
                  mock.patch.object(schedule, "_pythonw", lambda: r"C:\Python\pythonw.exe")):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def config(self, **kw):
        (self.V / ".system" / "config.json").write_text(json.dumps(kw), encoding="utf-8")

    def stale(self):
        return [i for i in pending.load(self.V)["items"] if i.get("key") == schedule.PENDING_KEY]

    def test_created_then_ok(self):
        self.assertEqual(schedule.ensure(self.V), "created")
        ((name, xml),) = self.fake.tasks.items()
        self.assertRegex(name, r"^wiki-with-willy\\變動比對-[0-9a-f]{8}$")
        self.assertIn(r"<Command>C:\Python\pythonw.exe</Command>", xml)
        kb = str(paths.plugin_root() / "scripts" / "kb.py")
        self.assertIn(f"&quot;{kb}&quot; changes --background --vault &quot;{self.V}&quot;", xml)
        self.assertIn(f"<WorkingDirectory>{self.V}</WorkingDirectory>", xml)
        self.assertIn(f"--vault &quot;{self.V}&quot; --task &quot;{name}&quot;</Arguments>", xml)  # 裁定 12a
        self.assertIn("<Interval>PT10M</Interval>", xml)
        self.assertIn("<LogonType>InteractiveToken</LogonType>", xml)
        self.assertIn("<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>", xml)
        self.assertEqual(schedule.ensure(self.V), "ok")
        self.assertEqual(self.fake.calls.count("/create"), 1)

    def test_updated_when_interval_or_root_differs(self):
        schedule.ensure(self.V)
        self.config(background_scan_minutes=15)
        self.assertEqual(schedule.ensure(self.V), "updated")
        self.assertIn("<Interval>PT15M</Interval>", next(iter(self.fake.tasks.values())))
        name = next(iter(self.fake.tasks))
        self.fake.tasks[name] = self.fake.tasks[name].replace("scripts", "別的版本\\scripts")
        self.assertEqual(schedule.ensure(self.V), "updated")
        self.assertEqual(schedule.ensure(self.V), "ok")

    def test_off_deletes_then_back_on_creates(self):
        """驗收 11。"""
        schedule.ensure(self.V)
        self.config(background_scan_minutes=0)
        self.assertEqual(schedule.ensure(self.V), "off")
        self.assertEqual(self.fake.tasks, {})
        self.assertEqual(schedule.ensure(self.V), "off")
        self.config(background_scan_minutes=10)
        self.assertEqual(schedule.ensure(self.V), "created")

    def test_failed_records_pending_once_then_closes(self):
        self.fake.fail = "錯誤: 存取被拒。"
        self.assertEqual(schedule.ensure(self.V), "failed")
        self.assertEqual(schedule.ensure(self.V), "failed")
        (item,) = self.stale()
        self.assertEqual(item["status"], "open")
        self.assertIn("背景比對的排程設不起來", item["text"])
        self.assertIn("存取被拒", item["text"])
        self.fake.fail = None
        self.assertEqual(schedule.ensure(self.V), "created")
        self.assertEqual([i["status"] for i in self.stale()], ["done"])

    def test_no_pythonw_is_failed(self):
        with mock.patch.object(schedule, "_pythonw", lambda: None):
            self.assertEqual(schedule.ensure(self.V), "failed")
        self.assertIn("pythonw", self.stale()[0]["text"])

    def test_no_schedule_env_never_calls_schtasks(self):
        """裁定 11：tests/__init__.py 設了不建排程的環境變數，真正那一層不叫 schtasks、ensure 回 unsupported、不記待處理。"""
        with mock.patch.object(schedule, "_schtasks", REAL_SCHTASKS), \
                mock.patch.object(schedule.subprocess, "run", side_effect=AssertionError("不該叫 schtasks")):
            self.assertEqual(schedule.ensure(self.V), "unsupported")
        self.assertEqual(self.stale(), [])

    def test_not_windows_unsupported(self):
        with mock.patch.object(schedule, "WINDOWS", False):
            self.assertEqual(schedule.ensure(self.V), "unsupported")
        self.assertEqual(self.fake.calls, [])

    def test_codepage_mangled_query_still_ok(self):
        """schtasks /query /xml 印系統碼頁：碼頁沒有的字變 ? 也認得是同一個（不會每天重建）。"""
        schedule.ensure(self.V)
        name = next(iter(self.fake.tasks))
        with mock.patch.object(schedule, "_codepage", lambda s: s.replace("測", "?")):
            self.fake.tasks[name] = self.fake.tasks[name].replace("測", "?")
            self.assertEqual(schedule.ensure(self.V), "ok")


class Orphan(unittest.TestCase):
    """驗收 15（裁定 12、12a）：庫刪了，排程跑 kb changes --background 照 --task 刪掉自己、exit 0；別人的工作不刪。"""

    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        self.fake = FakeSchtasks()
        self.log = Path(self.tmp) / "fallback-errors.log"
        from kb._lib import ledger
        for p in (mock.patch.object(schedule, "_schtasks", self.fake), mock.patch.object(schedule, "WINDOWS", True),
                  mock.patch.object(schedule, "_pythonw", lambda: r"C:\Python\pythonw.exe"),
                  mock.patch.object(ledger, "fallback_error_log", lambda: self.log)):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def background(self, vault, task):
        from kb import changes
        args = mock.Mock(background=True, vault=str(vault), task=task)
        with mock.patch("os.getcwd", lambda: self.tmp):
            return changes.run(args)

    def test_vault_deleted_deletes_own_task(self):
        schedule.ensure(self.V)
        (name,) = self.fake.tasks
        shutil.rmtree(self.V)
        self.assertEqual(self.background(self.V, name), 0)
        self.assertEqual(self.fake.tasks, {})
        self.assertIn("/delete", self.fake.calls)
        self.assertIn("找不到知識庫", self.log.read_text(encoding="utf-8"))

    def test_not_a_vault_deletes_own_task(self):
        """路徑還在但不是知識庫（.system 被刪）。"""
        schedule.ensure(self.V)
        (name,) = self.fake.tasks
        shutil.rmtree(self.V / ".system")
        self.assertEqual(self.background(self.V, name), 0)
        self.assertEqual(self.fake.tasks, {})

    def test_other_names_not_deleted(self):
        shutil.rmtree(self.V)
        for name in (None, "", r"Microsoft\Windows\Defrag\ScheduledDefrag", r"wiki-with-willy\別的工作"):
            with self.subTest(name=name):
                self.assertEqual(self.background(self.V, name), 0)
        self.assertNotIn("/delete", self.fake.calls)

    def test_vault_present_does_not_delete(self):
        schedule.ensure(self.V)
        (name,) = self.fake.tasks
        self.assertEqual(self.background(self.V, name), 0)
        self.assertNotIn("/delete", self.fake.calls)
        self.assertEqual(len(self.fake.tasks), 1)


class DailyLine(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        import importlib.util
        sys.path.insert(0, str(ROOT / "scripts"))
        spec = importlib.util.spec_from_file_location("hook_checks_sched", ROOT / "hooks" / "_checks.py")
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_line_only_when_created_or_updated(self):
        with mock.patch.dict(os.environ, {"WIKI_WITH_WILLY_NO_BACKGROUND": ""}):
            for got, want in (("created", True), ("updated", True), ("ok", False), ("off", False), ("failed", False),
                              ("unsupported", False)):
                with mock.patch.object(schedule, "ensure", lambda v, g=got: g):
                    line = self.m.line_schedule(self.V)
                self.assertEqual(line is not None, want, got)
            with mock.patch.object(schedule, "ensure", lambda v: "created"):
                self.assertEqual(self.m.line_schedule(self.V), self.m.SCHEDULE_LINE.format(n=10))

    def test_over_budget_does_not_touch(self):
        """review 1：每天第一句前面用掉太多時間就不查排程（turn.py 上限 5 秒），明天再查。"""
        import time
        self.m.START = time.monotonic() - 1000
        with mock.patch.dict(os.environ, {"WIKI_WITH_WILLY_NO_BACKGROUND": ""}), \
                mock.patch.object(schedule, "ensure", side_effect=AssertionError("不該碰排程")):
            self.assertIsNone(self.m.line_schedule(self.V))

    def test_no_background_env_does_not_touch(self):
        with mock.patch.dict(os.environ, {"WIKI_WITH_WILLY_NO_BACKGROUND": "1"}), \
                mock.patch.object(schedule, "ensure", side_effect=AssertionError("不該碰排程")):
            self.assertIsNone(self.m.line_schedule(self.V))


if __name__ == "__main__":
    unittest.main()
