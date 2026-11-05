"""多人共用 1 驗收 8：舊格式的庫跑遷移，每種都轉成這台的流水檔、讀回跟遷移前一樣；舊檔在 .system/legacy/<版本>/；
config.json 的 agenda_export_dir 搬到 env；退回（kb versions revert）退回設定檔，格式轉換本身不可退、講一句（#45-07）。"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests._guard_fixture import FIXTURES
from tests.test_scripts_inventory_cli import run_kb
from kb._lib import config, env, migrate, profile, streams, turn  # noqa: E402
from kb._lib.io import read_json  # noqa: E402

PROFILE_FIX = FIXTURES / "profile"

LEGACY = {
    "agenda.json": {"schema_version": 1, "items": [{"id": "a-1", "text": "11/25 開會", "status": "open", "date": "2026-11-25"}]},
    "statements.json": {"schema_version": 1, "statements": [{"id": "s-1", "text": "甲", "status": "active", "entities": []}]},
    "rulings.json": {"schema_version": 1, "rulings": [{"id": "r-1", "status": "active"}]},
    "findings.json": {"schema_version": 1, "findings": [{"id": "c-1", "text": "乙", "status": "active"}]},
    "set_aside.json": {"schema_version": 1, "keys": {"k1": {"at": "x", "by": "y", "question": "q"}}},
}


class MigrateStreams(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kbmigs-")).resolve()
        self.V = self.tmp / "vault"
        (self.V / ".system").mkdir(parents=True)
        (self.V / "系統").mkdir()
        shutil.copy2(PROFILE_FIX / "schema1.json", self.V / ".system" / "profile.json")
        shutil.copy2(PROFILE_FIX / "schema1.md", self.V / "系統" / "客戶設定檔.md")
        for name, doc in LEGACY.items():
            (self.V / ".system" / name).write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        (self.V / ".system" / "sources.json").write_text('{"schema_version": 1, "sources": []}', encoding="utf-8")
        (self.V / ".system" / "config.json").write_text(
            json.dumps({"schema_version": 1, "agenda_export_dir": "D:/匯出", "backup_keep": 5}), encoding="utf-8")
        self.turn = turn.start(self.V, None, "升級")["turn"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_every_kind_becomes_this_machines_stream_and_reads_back_the_same(self):
        got = migrate.apply(self.V, self.turn)
        self.assertTrue({"agenda", "statements", "rulings", "findings", "set_aside"} <= set(got["streams"]))
        for name, doc in LEGACY.items():
            self.assertEqual(read_json(self.V / ".system" / name), doc, name)  # 逐欄一樣
            kind = name.removesuffix(".json")
            files = list((self.V / ".system" / "streams" / kind).glob("*.jsonl"))
            self.assertEqual([f.stem for f in files], [streams.machine_id(self.V)], kind)  # 只有這台自己的檔
        data = read_json(self.V / ".system" / "profile.json")
        self.assertEqual(data["schema_version"], profile.SCHEMA_VERSION)
        legacy = [p.relative_to(self.V).as_posix() for p in (self.V / ".system" / "legacy").rglob("*.json")]
        self.assertIn(True, [p.endswith("/agenda.json") and p.startswith(".system/legacy/") for p in legacy])

    def test_export_dir_moves_from_config_to_env(self):
        migrate.apply(self.V, self.turn)
        self.assertEqual(env.agenda_export_dir(self.V), "D:/匯出")
        cfg = json.loads((self.V / ".system" / "config.json").read_text(encoding="utf-8"))
        self.assertNotIn("agenda_export_dir", cfg)
        self.assertEqual(cfg["backup_keep"], 5)
        self.assertEqual(config.get(self.V, "agenda_export_dir"), "D:/匯出")

    def test_revert_gets_the_old_profile_back_and_keeps_the_streams_readable(self):
        old = json.loads((self.V / ".system" / "profile.json").read_text(encoding="utf-8"))
        migrate.apply(self.V, self.turn)
        r = run_kb("versions", "revert", cwd=self.V)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(read_json(self.V / ".system" / "profile.json"), old)
        self.assertEqual(read_json(self.V / ".system" / "agenda.json"), LEGACY["agenda.json"])  # 其他種類沒被動
        self.assertIn("這一步退不回去", r.stdout)  # 格式轉換不可退，講一句（jacky 2026-11-05 定，#45-07）

    def test_conversion_turn_is_recorded_and_undo_says_it_cannot(self):
        migrate.apply(self.V, self.turn)
        self.assertTrue(migrate.converted_turn(self.V, self.turn))
        self.assertTrue(migrate.converted_turn(self.V, f"{self.turn}#1"))
        self.assertFalse(migrate.converted_turn(self.V, "t-沒有這句"))
        r = run_kb("versions", "undo", self.turn, cwd=self.V)
        self.assertIn(f"{self.turn} 那一句升級時把資料換成新的存法，這一步退不回去", r.stdout)
        self.assertIn(streams.machine_id(self.V), [f.stem for f in (self.V / ".system" / "streams" / "agenda").glob("*.jsonl")])
        r = run_kb("versions", "undo", "t-沒有這句", cwd=self.V)  # 不是轉換那一句照舊說找不到
        self.assertIn("找不到這個項目或回合", r.stdout)

    def test_only_conversion_in_the_turn_says_it_cannot(self):
        (self.V / ".system" / "legacy").mkdir(parents=True, exist_ok=True)
        (self.V / migrate.CONVERTED_REL).write_text(json.dumps({"turn": "t-only"}) + "\n", encoding="utf-8")
        for args in (("undo", "t-only"), ("items", "--turn", "t-only")):
            r = run_kb("versions", *args, cwd=self.V)
            self.assertIn("t-only 那一句升級時把資料換成新的存法，這一步退不回去", r.stdout, args)
            self.assertNotIn("找不到", r.stdout, args)


if __name__ == "__main__":
    unittest.main()
