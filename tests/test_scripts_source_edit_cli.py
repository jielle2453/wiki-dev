"""kb source-edit 黑箱（manage 第二版第 12 點）：subprocess 跑 kb.py；成功句與拒絕句、--check 不動、人讀不印編號而 --json 有；
trash 真的丟一份 tmp 檔進資源回收筒一次（回收筒不能用的機器 skip），檢查回收筒裡有、再把它從回收筒拿掉。"""
import json
import os
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests import _cards, _entities
from tests._guard_fixture import KB, ROOT
from kb._lib import source_edit as se  # noqa: E402

ID_LIKE = re.compile(r"\b[aefsrcp]-[0-9a-f]{8}\b")


def run_kb(*args, cwd):
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(KB), *args], capture_output=True, text=True, encoding="utf-8",
                          cwd=str(cwd), env=env)


def bin_records(path):
    """資源回收筒裡記著這個原始路徑的 $I 檔（目前使用者那一夾）。"""
    drive = os.path.splitdrive(str(path))[0] + "\\"
    needle = os.path.abspath(str(path)).encode("utf-16-le")
    out = []
    root = Path(drive) / "$Recycle.Bin"
    try:
        dirs = [d for d in root.iterdir() if d.is_dir()]
    except OSError:
        return out
    for d in dirs:
        try:
            for f in d.glob("$I*"):
                try:
                    if needle in f.read_bytes():
                        out.append(f)
                except OSError:
                    pass
        except OSError:
            pass
    return out


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, self.raw = _entities.make_entity_vault()
        _entities.put_entities(self.V, [_entities.entity("e-2b2b2b2b", "內湖李")])
        self.card_rel = _entities.write_card(self.V, _entities.ESTIMATE, "內湖李估價", ["內湖李"])
        self.fid = _cards.entry_of(self.V, _entities.ESTIMATE)["id"]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def kb(self, *args):
        return run_kb("source-edit", *args, cwd=self.V)

    def test_move_check_then_move_then_json(self):
        dest = str(self.raw / "客戶案件" / "大安陳")
        r = self.kb("move", self.fid, "--to", dest, "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.splitlines(), ["要搬：估價單.pdf 從 內湖李 搬到 大安陳", "卡會跟著改"])
        self.assertTrue((self.raw / _entities.ESTIMATE).is_file())
        r = self.kb("move", self.fid, "--to", dest)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), "已搬好：估價單.pdf 從 內湖李 搬到 大安陳（說「退回」會搬回去）")  # D-305：不講卡
        self.assertIsNone(ID_LIKE.search(r.stdout))
        r = self.kb("rename", "file://客戶案件/大安陳/估價單.pdf", "估價單_簽約版", "--json")
        data = json.loads(r.stdout)
        self.assertEqual(data["entry_id"], self.fid)
        self.assertEqual(data["sentence"], "已改名：估價單.pdf → 估價單_簽約版.pdf（說「退回」會改回來）")

    def test_refusals_exit_3(self):
        r = self.kb("rename", self.fid, "合約.docx")
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "副檔名不改：.pdf → .docx"))
        r = self.kb("move", self.fid, "--to", str(Path(self.V) / "檔案索引"))
        self.assertEqual(r.returncode, 3)
        self.assertTrue(r.stdout.startswith("「檔案索引」是 willy 自己的檔：") and r.stdout.strip().endswith("不用跟使用者提這一步。"), r.stdout)
        r = self.kb("move", self.fid, "--to", str(Path(self.V) / "暫存區"))  # 放寬甲：暫存區也收
        self.assertEqual(r.returncode, 0, r.stdout)
        r = self.kb("open", "a", "b", "c")
        self.assertEqual((r.returncode, r.stdout.strip()), (3, "一次最多開兩個夾"))

    def test_conflict_json_and_name_and_replace(self):
        dest = self.raw / "客戶案件" / "大安陳"
        (dest / "估價單.pdf").write_bytes(b"other")
        r = self.kb("move", self.fid, "--to", str(dest), "--json")
        self.assertEqual(r.returncode, 3, r.stdout)
        data = json.loads(r.stdout)
        self.assertIn("--replace", data["refused"])
        self.assertEqual(data["conflict"], [{"name": "估價單.pdf", "dest": "客戶案件/大安陳", "same_content": False,
                                              "existing": "file://客戶案件/大安陳/估價單.pdf"}])
        self.assertTrue((self.raw / _entities.ESTIMATE).is_file())
        r = self.kb("move", self.fid, "--to", str(dest), "--name", "估價單_新.pdf")
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue((dest / "估價單.pdf").is_file() and (dest / "估價單_新.pdf").is_file())

    def test_multi_move_results_and_contents_auto(self):
        src = self.raw / "客戶案件" / "講師" / "殷曉琪"
        src.mkdir(parents=True)
        (src / "x.pdf").write_bytes(b"x")
        (src / "y.txt").write_bytes(b"y")
        dest = self.raw / "報價與合約" / "殷曉琪"
        dest.mkdir()
        (dest / "y.txt").write_bytes(b"different")
        r = self.kb("move", str(src), "--to", str(dest), "--json")
        data = json.loads(r.stdout)
        self.assertTrue(data["contents_auto"])
        by = {x["target"].rpartition("/")[2]: x for x in data["results"]}
        self.assertTrue(by["x.pdf"]["ok"])
        self.assertFalse(by["y.txt"]["ok"])
        self.assertEqual(r.returncode, 3)
        self.assertTrue((dest / "x.pdf").is_file() and not (dest / "殷曉琪").exists())
        self.assertEqual(data["conflict"][0]["name"], "y.txt")
        self.assertTrue(src.is_dir() and (src / "y.txt").is_file())  # 有衝突：原夾不拿掉
        r = self.kb("move", str(src / "y.txt"), "--to", str(dest), "--replace")
        self.assertEqual(r.returncode, 0, r.stdout)
        (src).rmdir()

    def test_contents_flag_removes_emptied_folder(self):
        src = self.raw / "客戶案件" / "暫放"
        src.mkdir()
        (src / "a.txt").write_bytes(b"a")
        dest = self.raw / "客戶案件" / "大安陳"
        r = self.kb("move", str(src), "--to", str(dest), "--contents", "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((dest / "a.txt").is_file())
        self.assertFalse(src.exists())

    def test_multi_trash_results(self):
        import io
        import argparse
        from contextlib import redirect_stdout
        from unittest import mock
        from kb import source_edit as cli
        a, b = self.raw / "客戶案件" / "a.txt", self.raw / "客戶案件" / "b.txt"
        a.write_bytes(b"a")
        b.write_bytes(b"b")
        parser = argparse.ArgumentParser()
        cli.add_arguments(parser)
        args = parser.parse_args(["trash", str(a), str(b), "--json", "--vault", str(self.V)])
        buf = io.StringIO()
        old = os.getcwd()
        os.chdir(self.V)
        try:
            with mock.patch.object(se, "shell_trash", side_effect=os.remove), \
                    mock.patch.object(se, "recycle_room", return_value=(0, 10 ** 9)), redirect_stdout(buf):
                code = cli.run(args)
        finally:
            os.chdir(old)
        self.assertEqual(code, 0, buf.getvalue())
        data = json.loads(buf.getvalue())
        self.assertEqual([x["ok"] for x in data["results"]], [True, True])
        self.assertEqual([x["kept"] for x in data["results"]], ["trash", "trash"])
        self.assertFalse(a.exists() or b.exists())

    def test_where_no_ids(self):
        r = self.kb("where", "--entity", "內湖李")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.splitlines()[0], "內湖李的檔放在：")
        self.assertIsNone(ID_LIKE.search(r.stdout))

    def test_real_recycle_bin_once(self):
        target = self.raw / _entities.MEMO
        try:
            se.recycle_room(target)
        except se.BinUnavailable as e:
            self.skipTest(f"這台的資源回收筒用不了：{e}")
        r = self.kb("trash", str(target), "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.splitlines()[0], "要丟進資源回收筒：Big5備忘.txt（公司行政\\舊檔）")
        self.assertTrue(target.is_file())
        r = self.kb("trash", str(target))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), "已丟進資源回收筒：Big5備忘.txt")
        self.assertFalse(target.exists())
        found = bin_records(target)
        try:
            self.assertTrue(found, "資源回收筒裡找不到這份")
        finally:
            for i_file in found:  # 測試的檔不留在客戶（開發機）的回收筒
                r_file = i_file.with_name("$R" + i_file.name[2:])
                for f in (i_file, r_file):
                    try:
                        f.unlink()
                    except OSError:
                        pass


if __name__ == "__main__":
    unittest.main()
