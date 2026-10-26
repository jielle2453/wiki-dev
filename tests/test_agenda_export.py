"""日程匯出（D-229，spec 2026-10-26-日程匯出）：kb agenda export --set／--off／--status、每次寫日程就匯出 willy-agenda.json、
內容沒變不寫、失敗不擋日程（hook-errors.log、agenda_export.json）、開場不講。驗收準則一條一個測試。"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from tests import _entities as E
from tests.test_hooks_session import payload, run as run_hook
from tests.test_scripts_inventory_cli import KB, ROOT, run_kb
from kb._lib import agenda, config, turn
from kb._lib.io import FileLock

STATE = ".system/agenda_export.json"
CONFIG = ".system/config.json"
FP_KEYS = ("kind", "date", "start", "time", "text", "entities", "status", "lead_days")
FIELDS = {"id", "kind", "start", "date", "time", "text", "entities", "status", "source", "lead_days", "fp"}


def fp_of(it):
    """spec「資料與介面格式」那節的算法，獨立寫一次。"""
    body = json.dumps({k: it.get(k) for k in FP_KEYS}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = E.make_entity_vault(with_entities=True)
        self.out = Path(tempfile.mkdtemp(prefix="willy-export-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.out, ignore_errors=True)

    def kb(self, *args, code=0):
        r = run_kb("agenda", *args, cwd=self.V)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return r.stdout

    def add(self, text="交屋", date="2026-11-30", entity="信義王"):
        out = self.kb("add", "--kind", "到期", "--date", date, "--text", text, "--entity", entity, "--json")
        return json.loads(out)["item"]["id"]

    def set_dir(self, folder=None):
        return json.loads(self.kb("export", "--set", str(folder or self.out), "--json"))

    def exported(self):
        return json.loads((self.out / "willy-agenda.json").read_text(encoding="utf-8"))

    def row(self, aid):
        return next(i for i in self.exported()["items"] if i["id"] == aid)

    def state(self):
        p = self.V / STATE
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

    def client_config(self):
        p = self.V / CONFIG
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


class NotSet(Base):
    def test_add_without_setting_writes_nothing(self):
        """驗收 1：未設定 agenda_export_dir，kb agenda add 後資料夾沒有任何檔、agenda_export.json 不存在。"""
        self.assertEqual(config.get(self.V, "agenda_export_dir"), "")
        self.add()
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertFalse((self.V / STATE).exists())

    def test_export_without_setting_exit_1(self):
        r = run_kb("agenda", "export", "--json", cwd=self.V)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertFalse(json.loads(r.stdout)["ok"])


class Set(Base):
    def test_set_writes_config_and_file(self):
        """驗收 2：--set <暫存夾> 寫進 .system/config.json，暫存夾出現 willy-agenda.json，schema 是 willy-agenda/1。"""
        self.add()
        out = self.set_dir()
        self.assertEqual(out, {"dir": self.out.as_posix(), "written": True, "items": 1, "ok": True})
        self.assertEqual(self.client_config()["agenda_export_dir"], self.out.as_posix())
        data = self.exported()
        self.assertEqual(data["schema"], "willy-agenda/1")
        self.assertEqual(list(data), ["schema", "exported_at", "willy_version", "fp", "items", "entities"])
        self.assertRegex(data["exported_at"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")  # 帶時區
        self.assertEqual(set(data["items"][0]), FIELDS)
        names = {e["name"] for e in data["entities"]}
        self.assertIn("信義王", names)
        self.assertNotIn("林小姐室內設計", names)  # self 的不列
        self.assertTrue(all(set(e) == {"id", "name", "type"} for e in data["entities"]))
        self.assertEqual([f.name for f in self.out.iterdir()], ["willy-agenda.json"])  # 試寫的暫存檔刪掉了

    def test_set_missing_folder_refused(self):
        """驗收 3：--set 不存在的資料夾 exit 1、白話原因、設定不變。"""
        before = (self.V / CONFIG).read_bytes() if (self.V / CONFIG).is_file() else None
        r = run_kb("agenda", "export", "--set", str(self.out / "沒有這夾"), cwd=self.V)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("資料夾不存在", r.stdout)
        r = run_kb("agenda", "export", "--set", str(self.out / "沒有這夾"), "--json", cwd=self.V)
        self.assertEqual(json.loads(r.stdout), {"ok": False, "reason": "資料夾不存在"})
        after = (self.V / CONFIG).read_bytes() if (self.V / CONFIG).is_file() else None
        self.assertEqual(before, after)
        self.assertEqual(config.get(self.V, "agenda_export_dir"), "")

    def test_status_json(self):
        self.set_dir()
        out = json.loads(self.kb("export", "--status", "--json"))
        self.assertEqual(set(out), {"dir", "last_ok_at", "last_error_at", "last_error"})
        self.assertEqual(out["dir"], self.out.as_posix())
        self.assertTrue(out["last_ok_at"])
        self.assertIsNone(out["last_error"])


class Follows(Base):
    def test_add_done_edit_cancel_reflected_at_once(self):
        """驗收 4：設定後 add、done、edit（改日期）、cancel 各一次，指令結束時匯出檔已反映。"""
        self.set_dir()
        a = self.add("交屋")
        self.assertEqual(self.row(a)["status"], "open")
        self.kb("done", a)
        self.assertEqual(self.row(a)["status"], "done")
        b = self.add("驗收", "2026-12-01")
        self.kb("edit", b, "--date", "2026-12-03")
        self.assertEqual(self.row(b)["date"], "2026-12-03")
        self.kb("cancel", b)
        self.assertEqual(self.row(b)["status"], "cancelled")
        self.assertEqual(len(self.exported()["items"]), 2)  # 完成、取消的也在

    def test_entity_rename_follows(self):
        """驗收 5：kb entity rename 後匯出檔條目的 entities 換成新名。"""
        self.set_dir()
        a = self.add()
        r = run_kb("entity", "rename", "信義王", "--to", "信義王宅邸", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.row(a)["entities"], ["信義王宅邸"])
        self.assertIn("信義王宅邸", {e["name"] for e in self.exported()["entities"]})

    def test_item_fp_matches_spec(self):
        """驗收 6：條目 fp 逐條與 spec 的算法相符，整檔 fp 是條目 fp 串起來再 sha256 前 12 碼。"""
        self.set_dir()
        self.add("交屋")
        self.add("驗收", "2026-12-01")
        self.kb("add", "--kind", "會議", "--date", "2026-11-20", "--time", "14:00", "--text", "看磁磚", "--lead-days", "2")
        data = self.exported()
        source = {i["id"]: i for i in agenda.load(self.V)["items"]}
        self.assertEqual(len(data["items"]), 3)
        for row in data["items"]:
            with self.subTest(text=row["text"]):
                self.assertEqual(row["fp"], fp_of(source[row["id"]]))
                self.assertEqual(row["fp"], fp_of(row))
        whole = hashlib.sha256("".join(r["fp"] for r in data["items"]).encode("utf-8")).hexdigest()[:12]
        self.assertEqual(data["fp"], whole)

    def test_render_unchanged_keeps_mtime(self):
        """驗收 7：日程沒變再呼叫 render()，匯出檔的修改時間不變。"""
        self.set_dir()
        self.add()
        target = self.out / "willy-agenda.json"
        os.utime(target, (1_000_000_000, 1_000_000_000))
        agenda.render(self.V)
        self.kb("render")
        self.assertEqual(target.stat().st_mtime, 1_000_000_000)


class Failure(Base):
    def opening(self):
        r = run_hook(payload(self.V))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"].split("\n\n")[0].splitlines()

    def test_folder_gone_still_writes_agenda_opening_silent(self):
        """驗收 8：匯出夾被刪掉後 add 照常寫入 exit 0；hook-errors.log 多一行 agenda_export；agenda_export.json 有 last_error；
        開場不多任何一行。"""
        self.set_dir()
        quiet = self.opening()
        shutil.rmtree(self.out)
        log = self.V / ".system" / "hook-errors.log"
        before = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
        a = self.add()
        self.assertTrue(any(i["id"] == a for i in agenda.load(self.V)["items"]))
        new = log.read_text(encoding="utf-8").splitlines()[len(before):]
        self.assertTrue(any(line.split("	")[1] == "agenda_export" for line in new), new)
        state = self.state()
        self.assertEqual(set(state), {"schema_version", "last_ok_at", "last_error_at", "last_error"})
        self.assertEqual(state["last_error"], "資料夾不存在")
        self.assertGreater(state["last_error_at"], state["last_ok_at"])
        lines = self.opening()
        self.assertEqual(len(lines), len(quiet), lines)  # 開場不多任何一行（加的那條日期在 7 天外，日程行不變）
        self.assertFalse(any("日程放不到" in ln or self.out.as_posix() in ln for ln in lines), lines)

    def test_export_now_fails_exit_1(self):
        self.set_dir()
        shutil.rmtree(self.out)
        r = run_kb("agenda", "export", "--json", cwd=self.V)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout), {"ok": False, "reason": "資料夾不存在"})

    def test_render_return_unchanged_when_export_raises(self):
        """export 本身丟例外（不該發生）也不影響 render 的回傳。"""
        self.set_dir()
        self.add()
        real = agenda.export

        def boom(*a, **k):
            raise RuntimeError("x")
        agenda.export = boom
        try:
            self.assertFalse(agenda.render(self.V))
        finally:
            agenda.export = real


class Off(Base):
    def test_off_stops_updates_keeps_file(self):
        """驗收 9：--off 後再寫日程，匯出檔不再更新、原檔還在。"""
        self.set_dir()
        self.add()
        target = self.out / "willy-agenda.json"
        before = target.read_bytes()
        self.kb("export", "--off")
        self.assertNotIn("agenda_export_dir", self.client_config())
        self.add("驗收", "2026-12-01")
        self.assertEqual(target.read_bytes(), before)


class Concurrency(Base):
    """第二輪（T-1～T-3）：匯出在 agenda.json 的鎖外、自己一把鎖並在鎖裡重讀；實體存檔也匯出。"""

    def lib_add(self, text, date="2026-11-30"):
        return agenda.add(self.V, agenda.kind_of("到期"), date, text, ["信義王"], turn.current(self.V)["turn"])[0]["id"]

    def wait_for(self, cond, seconds=20):
        end = time.time() + seconds
        while time.time() < end:
            if cond():
                return True
            time.sleep(0.05)
        return False

    def ids_in_agenda(self):
        return {i["id"] for i in agenda.load(self.V)["items"]}

    def test_agenda_lock_released_while_export_hangs(self):
        """T-1：匯出卡住期間 agenda.json 的鎖已放開，另一個行程拿得到鎖、寫得進日程，不用等匯出。"""
        self.set_dir()
        entered, release = threading.Event(), threading.Event()
        real = agenda._export_locked

        def hang(vault, folder):
            entered.set()
            release.wait(30)
            return real(vault, folder)
        agenda._export_locked = hang
        try:
            first = threading.Thread(target=self.lib_add, args=("交屋",))
            first.start()
            self.assertTrue(entered.wait(10), "第一個寫入沒走到匯出")
            with FileLock(agenda._path(self.V), timeout=2):  # 匯出還卡著，鎖拿得到
                pass
            other = subprocess.Popen([sys.executable, str(KB), "agenda", "add", "--kind", "到期", "--date", "2026-12-01",
                                      "--text", "驗收", "--entity", "信義王"], cwd=str(self.V), stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT)))
            try:
                got = self.wait_for(lambda: any(i["text"] == "驗收" for i in agenda.load(self.V)["items"]))
                self.assertFalse(release.is_set())
                self.assertTrue(got, "另一個行程在匯出卡住時寫不進日程")
            finally:
                release.set()
                first.join(30)
                out, err = other.communicate(timeout=60)
            self.assertEqual(other.returncode, 0, out.decode("utf-8", "replace") + err.decode("utf-8", "replace"))
        finally:
            agenda._export_locked = real
        self.assertEqual({r["text"] for r in self.exported()["items"]}, {"交屋", "驗收"})  # 日程不掉條目、匯出也跟上

    def test_slow_first_export_last_file_is_latest(self):
        """T-3：兩個寫入幾乎同時、第一個的匯出被拖慢（讀完舊資料才停），兩個都結束後匯出檔等於最新的 agenda.json。"""
        self.set_dir()
        entered, release = threading.Event(), threading.Event()
        real = agenda.export_payload
        calls = []

        def slow(vault, data):
            payload = real(vault, data)
            calls.append(len(data["items"]))
            if len(calls) == 1:
                entered.set()
                release.wait(30)
            return payload
        agenda.export_payload = slow
        try:
            first = threading.Thread(target=self.lib_add, args=("交屋",))
            first.start()
            self.assertTrue(entered.wait(10))
            second = threading.Thread(target=self.lib_add, args=("驗收", "2026-12-01"))
            second.start()
            self.assertTrue(self.wait_for(lambda: len(self.ids_in_agenda()) == 2))
            time.sleep(0.3)  # 第二個的匯出在等匯出的鎖
            release.set()
            first.join(30)
            second.join(30)
        finally:
            agenda.export_payload = real
        self.assertEqual(calls, [1, 2])  # 第二個在鎖裡重讀，拿到的是兩條
        data = self.exported()
        latest = agenda.load(self.V)["items"]
        self.assertEqual([r["id"] for r in data["items"]], [i["id"] for i in latest])
        self.assertEqual([r["fp"] for r in data["items"]], [fp_of(i) for i in latest])

    def test_entity_add_remove_updates_names(self):
        """T-2：kb entity add／停用一個實體後，不寫日程，匯出檔的 entities 名單立刻跟上。"""
        self.set_dir()
        self.add()
        agenda_before = (self.V / agenda.AGENDA_POSIX).read_bytes()
        names = lambda: {e["name"] for e in self.exported()["entities"]}  # noqa: E731
        self.assertIn("王宅", names())
        r = run_kb("entity", "add", "--type", "案子", "--name", "新客戶甲", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("新客戶甲", names())
        r = run_kb("entity", "remove", "王宅", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("王宅", names())
        self.assertIn("新客戶甲", names())
        self.assertEqual((self.V / agenda.AGENDA_POSIX).read_bytes(), agenda_before)  # 日程沒寫


if __name__ == "__main__":
    unittest.main()
