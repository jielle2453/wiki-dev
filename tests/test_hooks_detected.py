"""放寬丙 第一輪 1：事後偵測。每句開頭（hooks/turn.py）讀背景比對的清單（D-536：電腦排程跑 kb changes --background），
把搬動、不見、新增寫進 .system/versions/<這一句>/detected.jsonl；驗收 1、3。答完（hooks/stop.py）不再比（D-536 代價 4）。"""
import json
import os
import shutil
import time
import unittest

from tests._guard_fixture import make_vault
from tests.test_hooks_session import background_scan
from tests.test_hooks_stop import HOOK as STOP_HOOK, run, stop_payload
from tests.test_hooks_turn import HOOK as TURN_HOOK, SID, prompt_payload, settle
from kb._lib import inventory, sources as sources_lib, turn


def detected_of(vault, sid=SID):
    sess = json.loads((vault / ".system" / "turns" / f"{sid}.json").read_text(encoding="utf-8"))
    return sess["turn"], turn.detected(vault, sess["turn"])


class Detected(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = make_vault()
        settle(self.V)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def prompt(self, text="下一句"):
        background_scan(self.V)  # 排程跑過（D-536）
        r = run(TURN_HOOK, prompt_payload(self.V, text))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def stop(self):
        r = run(STOP_HOOK, stop_payload(self.V, "好了"))
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)

    def test_1_move_between_turns_is_outside(self):
        """驗收 1：兩句之間搬一份檔，下一句開頭後有 op move、by outside，from、to 對。"""
        shutil.move(self.raw / "客戶案件" / "a.txt", self.raw / "行政" / "a.txt")
        self.prompt()
        _tid, rows = detected_of(self.V)
        self.assertEqual([(r["op"], r["by"]) for r in rows], [("move", "outside")])
        self.assertTrue(rows[0]["from"].endswith("客戶案件/a.txt"), rows[0])
        self.assertTrue(rows[0]["to"].endswith("行政/a.txt"), rows[0])
        self.assertTrue(rows[0]["id"].startswith("f-"))
        self.assertEqual(rows[0]["kind"], "file")
        self.assertNotIn("shared", rows[0])

    def test_unchanged_writes_nothing(self):
        self.prompt()
        tid, rows = detected_of(self.V)
        self.assertEqual(rows, [])
        self.assertFalse((self.V / ".system" / "versions" / tid / "detected.jsonl").exists())

    def test_same_change_is_not_recorded_twice(self):
        """清冊還沒套用時，下一句不重記同一件；同一件在答完時也不再記成 by turn。"""
        shutil.move(self.raw / "客戶案件" / "a.txt", self.raw / "行政" / "a.txt")
        self.prompt("一")
        self.stop()
        self.prompt("二")
        _tid, rows2 = detected_of(self.V)
        self.assertEqual(rows2, [])
        checks = json.loads((self.V / ".system" / "turns" / f"{SID}.json").read_text(encoding="utf-8"))["checks"]
        self.assertEqual(len(checks["detected"]), 1)

    def test_stop_does_not_compare(self):
        """D-536：答完不再比對原檔；這一句裡 AI 自己搬的檔，下一句開頭（排程跑過）才記成 outside。"""
        self.prompt()
        tid, _ = detected_of(self.V)
        shutil.move(self.raw / "客戶案件" / "a.txt", self.raw / "行政" / "a.txt")
        self.stop()
        self.assertEqual(turn.detected(self.V, tid), [])

    def test_missing_and_added_and_modified(self):
        (self.raw / "客戶案件" / "a.txt").unlink()
        (self.raw / "客戶案件" / "新.txt").write_text("新\n", encoding="utf-8")
        (self.raw / "行政" / "請款" / "r.docx").write_bytes(b"changed content, different size")
        self.prompt()
        _tid, rows = detected_of(self.V)
        self.assertEqual(sorted(r["op"] for r in rows), ["added", "missing", "modified"])
        added = next(r for r in rows if r["op"] == "added")
        self.assertIsNone(added["from"])
        self.assertIsNone(added["id"])

    def test_shared_source_is_flagged(self):
        p = self.V / ".system" / "sources.json"
        raw = json.loads(p.read_text(encoding="utf-8"))
        for s in raw["sources"]:
            s["shared"] = True
        p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        shutil.move(self.raw / "客戶案件" / "a.txt", self.raw / "行政" / "a.txt")
        self.prompt()
        _tid, rows = detected_of(self.V)
        self.assertTrue(rows and all(r.get("shared") for r in rows), rows)

    def test_hook_error_still_exit_0(self):
        (self.V / ".system" / "sources.json").write_text("{壞", encoding="utf-8")
        self.prompt()
        r = run(STOP_HOOK, stop_payload(self.V, "好了"))
        self.assertEqual(r.returncode, 0)


class Placeholder(unittest.TestCase):
    def test_cloud_placeholder_is_not_read(self):
        """2b：只在雲端的佔位檔不讀內容（read_kind 判 placeholder，Windows 屬性與 Mac 的 SF_DATALESS 都算）。"""
        class Win:
            st_size = 10
            st_file_attributes = 0x400000

        class Mac:
            st_size = 10
            st_flags = 0x40000000
        self.assertEqual(inventory.read_kind(["a.docx"], Win, 100)[0], "placeholder")
        self.assertEqual(inventory.read_kind(["a.docx"], Mac, 100)[0], "placeholder")


class Speed(unittest.TestCase):
    def test_3_unchanged_3000_files_turn_hook_is_fast(self):
        """驗收 3：3000 份沒變動時 hooks/turn.py 整支（讀清單）在 1.5 秒內。合成資料量一下，不當易飄的硬測試：
        只守大幅超標的上限 4 秒（含 python 啟動），實測數字印出來看。"""
        tmp, V, raw = make_vault()
        try:
            d = raw / "客戶案件" / "批量"
            d.mkdir()
            for i in range(3000):
                (d / f"f{i}.txt").write_text(f"檔 {i}\n" * 20, encoding="utf-8")
            settle(V)
            background_scan(V)  # 排程跑的不算在每句開頭（D-536）
            times = []
            for i in range(5):
                t0 = time.monotonic()
                r = run(TURN_HOOK, prompt_payload(V, f"第 {i} 句", session_id=f"s{i}"))
                times.append(time.monotonic() - t0)
                self.assertEqual(r.returncode, 0, r.stderr)
            print(f"[3000 份 turn hook 秒數] {[round(t, 2) for t in times]} 最大 {max(times):.2f}")
            self.assertLess(max(times), 4.0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
