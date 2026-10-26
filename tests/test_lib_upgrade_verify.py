"""換版前先驗新版（要做的事二，驗收 3～5、7）：upgrade.verify（抓 zip、核 sha256、zip slip、編譯、跑新版的 kb selftest）、
背景小修與對話裡的 kb upgrade 先驗、--check 的 verify_failed。下載（_download）一律替身；正常的那份真的跑新版的自我檢查。"""
import hashlib
import io
import json
import shutil
import sys
import tempfile
import time
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest import mock

from tests import _backup
from tests._guard_fixture import ROOT
from tests.test_lib_selftest import PLUGIN_PARTS
from tests.test_lib_upgrade import Base, MANIFEST_URL, ROLLOUT_URL, rollout
from kb._lib import backup, env, upgrade  # noqa: E402

PY = f"{sys.version_info[0]}.{sys.version_info[1]}"
URL = "https://example.invalid/wiki-with-willy.zip"
VERIFY_PREFIX = "wiki-with-willy-verify-"
REPO_VERSION = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
BAD_GUARD = {"hooks/guard.py": "x = 1\ndef (:\n    pass\n", "scripts/kb.py": "print('kb')\n"}


def zip_of(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, data in files.items():
            z.writestr(rel, data.encode("utf-8") if isinstance(data, str) else data)
    return buf.getvalue()


def repo_zip():
    """repo 裡會進 zip 的那幾個夾打成一份 zip（不帶 __pycache__），就是這一版。"""
    files = {}
    for part in PLUGIN_PARTS:
        for p in (ROOT / part).rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts:
                files[p.relative_to(ROOT).as_posix()] = p.read_bytes()
    return zip_of(files)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fake_kb(body):
    """一份只有 scripts/kb.py 的「新版」：kb.py 的內容是 body。"""
    return zip_of({".claude-plugin/plugin.json": "{}", "scripts/kb.py": body})


def leftovers(tmpdir):
    return {p.name for p in Path(tmpdir).iterdir() if p.name.startswith(VERIFY_PREFIX)}


class Verify(unittest.TestCase):
    def setUp(self):
        self.tmp, self.V, _raw = _backup.make_vault()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def verify(self, data, latest=REPO_VERSION, digest=None, source=True):
        src = {"url": URL, "sha256": digest or sha(data)} if source else None

        def download(url, dest, timeout):
            self.assertEqual(url, URL)
            Path(dest).write_bytes(data)
        with mock.patch.object(upgrade, "_download", side_effect=download) as dl:
            got = upgrade.verify(self.V, latest, src)
        self.downloads = dl.call_count
        return got

    def test_good_zip_passes_with_the_new_versions_own_selftest(self):
        own_tmp = self.tmp / "temp"  # 只看自己這份：別的對話同時在跑測試也會在系統暫存夾建同名開頭的夾
        own_tmp.mkdir()
        with mock.patch.object(tempfile, "tempdir", str(own_tmp)):
            got = self.verify(repo_zip())
        self.assertEqual(got, {"ok": True, "version": REPO_VERSION, "python": PY, "step": None, "file": None,
                               "line": None, "why": None, "transient": False})
        self.assertEqual(leftovers(own_tmp), set())

    def test_sha256_mismatch(self):
        got = self.verify(fake_kb("print(1)\n"), digest="0" * 64)
        self.assertEqual((got["ok"], got["step"]), (False, "download"))

    def test_download_failure(self):
        with mock.patch.object(upgrade, "_download", side_effect=OSError("連不上")):
            got = upgrade.verify(self.V, "0.23.1", {"url": URL, "sha256": "0" * 64})
        self.assertEqual((got["ok"], got["step"]), (False, "download"))

    def test_not_a_zip(self):
        got = self.verify(b"not a zip")
        self.assertEqual((got["ok"], got["step"]), (False, "download"))

    def test_zip_slip_writes_nothing_outside(self):
        name = f"kbverify-evil-{uuid.uuid4().hex}.txt"
        for evil in (f"../../{name}", f"/{name}", f"C:/{name}", f"..\\..\\{name}"):
            with self.subTest(evil=evil):
                got = self.verify(zip_of({"scripts/kb.py": "print(1)\n", evil: "壞"}))
                self.assertIs(got["ok"], False)
                self.assertFalse((Path(tempfile.gettempdir()) / name).exists())
                self.assertFalse(Path(f"C:/{name}").exists())

    def test_syntax_error_names_file_and_line(self):
        got = self.verify(zip_of(BAD_GUARD))
        self.assertEqual((got["ok"], got["step"], got["file"], got["line"]), (False, "compile", "hooks/guard.py", 2))
        self.assertTrue(got["why"].startswith("SyntaxError"), got["why"])
        self.assertEqual((got["version"], got["python"]), (REPO_VERSION, PY))

    def test_old_version_without_selftest(self):
        body = ("import sys\nsys.stderr.write(\"kb.py: error: argument <子命令>: invalid choice: 'selftest'\\n\")\n"
                "sys.exit(2)\n")
        got = self.verify(fake_kb(body))
        self.assertEqual((got["ok"], got["step"]), (False, "selftest"))

    def test_child_failure_passes_its_step_through(self):
        out = {"ok": False, "version": REPO_VERSION, "step": "hooks", "file": None, "line": None,
               "why": "守門（hooks/guard.py）該擋沒擋"}
        got = self.verify(fake_kb(f"print({json.dumps(json.dumps(out, ensure_ascii=False))})\nraise SystemExit(3)\n"))
        self.assertEqual((got["ok"], got["step"], got["why"]), (False, "hooks", "守門（hooks/guard.py）該擋沒擋"))

    def test_garbled_output(self):
        got = self.verify(fake_kb("print('不是 JSON')\n"))
        self.assertEqual((got["ok"], got["step"]), (False, "selftest"))

    def test_version_must_be_the_one_on_the_list(self):
        out = {"ok": True, "version": "0.0.1", "step": None, "file": None, "line": None, "why": None}
        got = self.verify(fake_kb(f"print({json.dumps(json.dumps(out))})\n"))
        self.assertEqual((got["ok"], got["step"]), (False, "selftest"))

    def test_source_none(self):
        got = self.verify(b"", source=False)
        self.assertEqual(got["ok"], False)
        self.assertEqual(got["why"], "清單沒有這一版的下載網址")
        self.assertEqual(self.downloads, 0)

    def test_too_slow_is_killed(self):
        (self.V / ".system" / "config.json").write_text(json.dumps({"update_verify_seconds": 3}), encoding="utf-8")
        beat = self.tmp / "心跳.txt"
        body = (f"import time\nn = 0\nwhile True:\n    n += 1\n"
                f"    open({str(beat)!r}, 'w', encoding='utf-8').write(str(n))\n    time.sleep(0.1)\n")
        start = time.monotonic()
        got = self.verify(fake_kb(body))
        self.assertLess(time.monotonic() - start, 30)
        self.assertEqual((got["ok"], got["step"]), (False, "selftest"))
        self.assertTrue(beat.exists(), "子行程有跑起來")
        time.sleep(0.5)
        first = beat.read_text(encoding="utf-8")
        time.sleep(1)
        self.assertEqual(beat.read_text(encoding="utf-8"), first, "子行程被殺掉了，不再寫")

    def test_runs_with_her_python(self):
        seen = []

        def call(argv, timeout, env=None, cwd=None):
            seen.append(list(argv))
            return 0, json.dumps({"ok": True, "version": "0.23.1", "step": None, "file": None, "line": None, "why": None})
        with mock.patch.object(upgrade, "_call", side_effect=call):
            got = self.verify(fake_kb("print(1)\n"), latest="0.23.1")
        self.assertTrue(got["ok"], got)
        self.assertEqual(seen[0][0], sys.executable)
        self.assertEqual(seen[0][2:], ["selftest", "--json"])
        self.assertTrue(seen[0][1].replace("\\", "/").endswith("/scripts/kb.py"))


    def test_transient_only_for_download_and_timeout(self):
        """裁定 11：下載不到、sha256 不對、逾時是 transient（隔天再試）；新版本身的問題不是。"""
        self.assertIs(self.verify(fake_kb("print(1)\n"), digest="0" * 64)["transient"], True)
        self.assertIs(self.verify(zip_of(BAD_GUARD))["transient"], False)
        self.assertIs(self.verify(fake_kb("print('不是 JSON')\n"))["transient"], False)
        with mock.patch.object(upgrade, "_download", side_effect=OSError("連不上")):
            self.assertIs(upgrade.verify(self.V, "0.23.1", {"url": URL, "sha256": "0" * 64})["transient"], True)

    def test_timeout_is_transient_and_cleans_the_selftest_temp(self):
        """裁定 11、14：逾時是 transient；子行程的 TMP／TEMP 指到 verify 自己的暫存夾，被殺之後它建的夾一起刪掉。"""
        (self.V / ".system" / "config.json").write_text(json.dumps({"update_verify_seconds": 3}), encoding="utf-8")
        mark = self.tmp / "暫存夾.txt"
        body = ("import tempfile, time\n"
                "d = tempfile.mkdtemp(prefix='wiki-with-willy-selftest-')\n"
                f"open({str(mark)!r}, 'w', encoding='utf-8').write(d)\n"
                "time.sleep(60)\n")
        got = self.verify(fake_kb(body))
        self.assertEqual((got["ok"], got["step"], got["transient"]), (False, "selftest", True))
        made = Path(mark.read_text(encoding="utf-8"))
        self.assertFalse(made.exists(), "被殺的自我檢查留下的暫存夾也刪掉了")
        self.assertNotEqual(made.parent.resolve(), Path(tempfile.gettempdir()).resolve())

    def test_child_file_and_why_are_cleaned_again(self):
        """裁定 17：新版回的 file 只收 plugin 根底下的相對路徑；why 再遮一次值、拿掉絕對路徑。"""
        for file in ("D:/私人/某人/x.py", "/etc/x.py", "../x.py", "a\\..\\..\\x.py"):
            with self.subTest(file=file):
                out = {"ok": False, "version": REPO_VERSION, "step": "hooks", "file": file, "line": 3,
                       "why": "壞在 D:\\私人\\某人\\私密\\x.py，密碼：hunter2abc"}
                got = self.verify(fake_kb(f"print({json.dumps(json.dumps(out, ensure_ascii=False))})\n"))
                self.assertIsNone(got["file"])
                self.assertIsNone(got["line"])
                self.assertNotIn("某人", got["why"])
                self.assertNotIn("hunter2abc", got["why"])
        out = {"ok": False, "version": REPO_VERSION, "step": "import", "file": "scripts/kb/_lib/x.py", "line": 3, "why": "x"}
        got = self.verify(fake_kb(f"print({json.dumps(json.dumps(out))})\n"))
        self.assertEqual((got["file"], got["line"]), ("scripts/kb/_lib/x.py", 3))


class Download(unittest.TestCase):
    """裁定 15：下載的逾時是總時間，不是每次讀。"""

    def test_slow_server_is_cut_at_the_total_time(self):
        class Slow:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n):
                time.sleep(0.3)
                return b"x" * 10

        class Opener:
            def open(self, req, timeout=None):
                return Slow()
        tmp = Path(tempfile.mkdtemp(prefix="kbdl-"))
        try:
            start = time.monotonic()
            with mock.patch.object(upgrade.urllib.request, "build_opener", return_value=Opener()):
                with self.assertRaises(OSError):
                    upgrade._download(URL, tmp / "x.zip", 1)
            self.assertLess(time.monotonic() - start, 3)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Where(unittest.TestCase):
    def test_file_and_line(self):
        self.assertEqual(upgrade.where({"step": "compile", "file": "hooks/guard.py", "line": 12,
                                        "why": "SyntaxError: invalid syntax"}), "hooks/guard.py 第 12 行：SyntaxError")

    def test_step_only(self):
        self.assertEqual(upgrade.where({"step": "hooks", "file": None, "line": None, "why": "守門（hooks/guard.py）該擋沒擋"}),
                         "跑 hook 那步：守門（hooks/guard.py）該擋沒擋")

    def test_every_step_name_is_chinese(self):
        """裁定 4：給人看的句子裡步驟名寫中文。"""
        names = {"download": "下載", "compile": "編譯", "selftest": "自我檢查", "import": "載入程式", "version": "版本號",
                 "vault": "建暫存知識庫", "hooks": "跑 hook", "upgrade": "背景更新"}
        for step, name in names.items():
            with self.subTest(step=step):
                sep = " " if step == "hooks" else ""
                self.assertEqual(upgrade.where({"step": step, "file": None, "line": None, "why": "原因"}), f"{name}{sep}那步：原因")

    def test_sentences_use_the_chinese_step_name(self):
        res = {"step": "download", "file": None, "line": None, "why": "清單沒有這一版的下載網址"}
        self.assertEqual(upgrade.VERIFY_REFUSED.format(version="0.23.1", where=upgrade.where(res)),
                         "新版 0.23.1 在這台電腦跑不起來（下載那步：清單沒有這一版的下載網址），先不換；什麼都沒動")


def failed(version="0.20.2", python=PY):
    return {"ok": False, "version": version, "python": python, "step": "compile", "file": "hooks/guard.py", "line": 12,
            "why": "SyntaxError: invalid syntax"}


class WithVerify(Base):
    """Base 的 verify 是替身（回過）；這裡要真的 verify 的，拿掉那個替身、換 _download。"""

    def setUp(self):
        super().setUp()
        self.zips = {}

        def download(url, dest, timeout):
            Path(dest).write_bytes(self.zips[url])
        self.dl = mock.patch.object(upgrade, "_download", side_effect=download)
        self.download = self.dl.start()

    def tearDown(self):
        self.dl.stop()
        super().tearDown()

    def real_verify(self):
        self.verify_patch.stop()
        self.patches.remove(self.verify_patch)

    def serve_zip(self, version, data, mine=True):
        url = f"https://example.invalid/{version}.zip"
        self.zips[url] = data
        self.fake.texts[MANIFEST_URL] = json.dumps({"name": "m", "owner": {"name": "w"}, "plugins": [
            {"name": "wiki-with-willy", "version": version, "source": {"source": "archive", "url": url, "sha256": sha(data)}}]})
        who = [self.vid] if mine else ["kb-00000000"]
        self.fake.texts[ROLLOUT_URL] = rollout(**{version: {"for": who, "note": "修好一個錯"}})
        self.fake.target = version


class FetchSource(WithVerify):
    def test_source_from_the_list(self):
        self.serve_zip("0.20.2", b"x")
        got = upgrade.fetch(self.V)
        self.assertEqual(got["source"], {"url": "https://example.invalid/0.20.2.zip", "sha256": sha(b"x")})

    def test_source_none_when_not_archive_or_missing(self):
        for source in (None, {"source": "github", "repo": "a/b"}, {"source": "archive", "url": URL},
                       {"source": "archive", "sha256": "0" * 64}, "壞的"):
            with self.subTest(source=source):
                entry = {"name": "wiki-with-willy", "version": "0.20.2"}
                if source is not None:
                    entry["source"] = source
                self.fake.texts[MANIFEST_URL] = json.dumps({"plugins": [entry]})
                self.fake.texts[ROLLOUT_URL] = rollout()
                self.assertIsNone(upgrade.fetch(self.V)["source"])


class BackgroundVerify(WithVerify):
    """驗收 4：背景小修先驗。"""

    SENTENCE = "新版 {v} 在這台電腦跑不起來（hooks/guard.py 第 2 行：SyntaxError），沒有換"

    def test_failed_verify_does_not_update_and_is_not_redone_tomorrow(self):
        self.real_verify()
        self.serve_zip("0.20.2", zip_of(BAD_GUARD))
        upgrade.background(self.V)
        self.assertEqual(self.fake.calls, [], "run_update 沒被叫")
        saved = env.update_check(self.V)
        self.assertEqual(saved["error"], self.SENTENCE.format(v="0.20.2"))
        self.assertEqual((saved["verify_failed"]["step"], saved["verify_failed"]["version"], saved["verify_failed"]["python"]),
                         ("compile", "0.20.2", PY))
        self.assertIsNone(saved["auto_patched"])
        self.assertEqual(self.download.call_count, 1)
        with mock.patch.object(upgrade, "_today", return_value="2026-10-25"):
            upgrade.background(self.V)
        self.assertEqual(self.download.call_count, 1, "同一版、同一個 Python：不再抓")
        saved = env.update_check(self.V)
        self.assertEqual((saved["date"], saved["error"]), ("2026-10-25", self.SENTENCE.format(v="0.20.2")))
        self.assertEqual(saved["verify_failed"]["version"], "0.20.2")
        self.serve_zip("0.20.3", zip_of(BAD_GUARD))
        with mock.patch.object(upgrade, "_today", return_value="2026-10-26"):
            upgrade.background(self.V)
        self.assertEqual(self.download.call_count, 2, "清單換了新的一版：重新驗")
        self.assertEqual(env.update_check(self.V)["verify_failed"]["version"], "0.20.3")
        self.assertEqual(self.fake.calls, [])

    def test_another_python_verifies_again(self):
        self.real_verify()
        self.serve_zip("0.20.2", zip_of(BAD_GUARD))
        env.set_update_check(self.V, dict(upgrade.BLANK_CHECK, date="2026-10-23", verify_failed=failed(python="3.9")))
        upgrade.background(self.V)
        self.assertEqual(self.download.call_count, 1)
        self.assertEqual(env.update_check(self.V)["verify_failed"]["python"], PY)

    def test_passing_verify_updates_and_clears_the_old_failure(self):
        self.serve_zip("0.20.2", b"zip")
        env.set_update_check(self.V, dict(upgrade.BLANK_CHECK, date="2026-10-23", verify_failed=failed("0.20.1")))
        upgrade.background(self.V)
        self.assertEqual(len(self.fake.calls), 1)
        self.assertEqual(self.fake.verifies, [("0.20.2", {"url": "https://example.invalid/0.20.2.zip", "sha256": sha(b"zip")})])
        saved = env.update_check(self.V)
        self.assertEqual((saved["auto_patched"], saved["verify_failed"], saved["error"]), ("0.20.2", None, None))

    def test_big_upgrade_is_not_verified_in_background(self):
        self.serve_zip("0.21.0", b"zip")
        upgrade.background(self.V)
        self.assertEqual(self.fake.verifies, [])
        self.assertIsNone(env.update_check(self.V)["verify_failed"])

    def test_offline_keeps_the_failure(self):
        env.set_update_check(self.V, dict(upgrade.BLANK_CHECK, date="2026-10-23", latest="0.20.2", kind="patch",
                                          allowed=True, verify_failed=failed()))
        self.fake.texts[MANIFEST_URL] = OSError("連不上")
        upgrade.background(self.V)
        self.assertEqual(env.update_check(self.V)["verify_failed"], failed())

    def test_batch_running_does_not_verify(self):
        self.serve_zip("0.20.2", b"zip")
        _backup.put_batch(self.V, created_min_ago=1, seen_min_ago=0)
        upgrade.background(self.V)
        self.assertEqual(self.fake.verifies, [])


class ConversationVerify(WithVerify):
    """驗收 5：對話裡的 kb upgrade 先驗（大升級與小修各一）。"""

    SENTENCE = "新版 {v} 在這台電腦跑不起來（hooks/guard.py 第 12 行：SyntaxError），先不換；什麼都沒動"

    def refused(self, version):
        self.serve_zip(version, b"zip")
        self.put_history("0.20.1")
        self.fake.verify_result = failed(version)
        with self.assertRaises(backup.Refused) as cm:
            upgrade.upgrade(self.V)
        self.assertEqual(str(cm.exception), self.SENTENCE.format(v=version))
        self.assertEqual(backup.snapshots(self.V), [])
        self.assertIsNone(self.history()["pending"])
        self.assertEqual(self.fake.calls, [])

    def test_major_refused(self):
        self.refused("0.21.0")

    def test_patch_refused(self):
        self.refused("0.20.2")

    def test_passing_verify_upgrades_as_before(self):
        self.serve_zip("0.21.0", b"zip")
        self.put_history("0.20.1")
        got = upgrade.upgrade(self.V)
        self.assertEqual(got["to"], "0.21.0")
        self.assertEqual(len(self.fake.verifies), 1)
        self.assertEqual(len(backup.snapshots(self.V)), 1)

    def test_verifies_every_time_even_after_a_recorded_failure(self):
        env.set_update_check(self.V, dict(upgrade.BLANK_CHECK, date="2026-10-24", verify_failed=failed("0.20.2")))
        self.serve_zip("0.20.2", b"zip")
        self.put_history("0.20.1")
        upgrade.upgrade(self.V)
        self.assertEqual(len(self.fake.verifies), 1)
        self.assertEqual(len(self.fake.calls), 1)

    def test_real_verify_failure_from_a_broken_zip(self):
        self.real_verify()
        self.serve_zip("0.20.2", zip_of(BAD_GUARD))
        self.put_history("0.20.1")
        with self.assertRaises(backup.Refused) as cm:
            upgrade.upgrade(self.V)
        self.assertEqual(str(cm.exception),
                         "新版 0.20.2 在這台電腦跑不起來（hooks/guard.py 第 2 行：SyntaxError），先不換；什麼都沒動")
        self.assertEqual(self.fake.calls, [])


class Round1(WithVerify):
    """測試第 1 輪後的裁定 11～13：暫時的失敗隔天再試、對話裡說「晚點再說」、換成功或已裝的版本不比它舊時清掉。"""

    def test_download_failure_is_not_cached_and_is_retried_tomorrow(self):
        self.real_verify()
        self.serve_zip("0.20.2", zip_of(BAD_GUARD))
        good = self.download.side_effect
        self.download.side_effect = OSError("network down")
        upgrade.background(self.V)
        saved = env.update_check(self.V)
        self.assertIsNone(saved["verify_failed"])
        self.assertTrue(saved["error"])
        self.assertNotIn("跑不起來", saved["error"])
        self.assertEqual(self.fake.calls, [])
        self.download.side_effect = good
        with mock.patch.object(upgrade, "_today", return_value="2026-10-25"):
            upgrade.background(self.V)
        self.assertEqual(self.download.call_count, 2, "隔天照常再抓")
        self.assertEqual(env.update_check(self.V)["verify_failed"]["step"], "compile")

    def test_sha_mismatch_is_not_cached(self):
        self.real_verify()
        self.serve_zip("0.20.2", b"zip")
        self.zips["https://example.invalid/0.20.2.zip"] = b"another zip"
        upgrade.background(self.V)
        self.assertIsNone(env.update_check(self.V)["verify_failed"])

    def test_timeout_is_not_cached(self):
        self.serve_zip("0.20.2", b"zip")
        self.fake.verify_result = dict(failed(), step="selftest", file=None, line=None, why="自我檢查超過 90 秒",
                                       transient=True)
        upgrade.background(self.V)
        saved = env.update_check(self.V)
        self.assertIsNone(saved["verify_failed"])
        self.assertTrue(saved["error"])
        self.assertEqual(self.fake.calls, [])

    def test_conversation_download_failure_says_try_later(self):
        self.real_verify()
        self.serve_zip("0.21.0", b"zip")
        self.download.side_effect = OSError("down")
        self.put_history("0.20.1")
        with self.assertRaises(backup.Refused) as cm:
            upgrade.upgrade(self.V)
        self.assertEqual(str(cm.exception), "現在下載不到新版，晚點再說一次；什麼都沒動")
        self.assertEqual((backup.snapshots(self.V), self.fake.calls), ([], []))
        self.assertIsNone(self.history()["pending"])

    def test_conversation_timeout_says_try_later(self):
        self.serve_zip("0.20.2", b"zip")
        self.put_history("0.20.1")
        self.fake.verify_result = dict(failed(), step="selftest", file=None, line=None, why="自我檢查超過 90 秒",
                                       transient=True)
        with self.assertRaises(backup.Refused) as cm:
            upgrade.upgrade(self.V)
        self.assertEqual(str(cm.exception), "現在下載不到新版，晚點再說一次；什麼都沒動")

    def test_upgrade_success_clears_verify_failed(self):
        env.set_update_check(self.V, dict(upgrade.BLANK_CHECK, date="2026-10-24", latest="0.20.2", kind="patch",
                                          allowed=True, verify_failed=failed("0.20.2")))
        self.serve_zip("0.20.2", b"zip")
        self.put_history("0.20.1")
        upgrade.upgrade(self.V)
        saved = env.update_check(self.V)
        self.assertIsNone(saved["verify_failed"])
        self.assertEqual(saved["latest"], "0.20.2", "其他欄留著")

    def test_check_never_says_latest_and_cannot_run_together(self):
        self.PLUGIN = "0.20.2"
        self.serve_zip("0.20.2", b"zip")
        env.set_update_check(self.V, dict(upgrade.BLANK_CHECK, date="2026-10-24", verify_failed=failed("0.20.2")))
        got = upgrade.check(self.V)
        self.assertIsNone(got["verify_failed"])
        self.assertEqual(upgrade.check_lines(got), ["目前是最新版（0.20.2）。"])

    def test_finish_clears_when_installed_is_not_older(self):
        self.PLUGIN = "0.20.2"
        self.put_history("0.20.1")
        env.set_update_check(self.V, dict(upgrade.BLANK_CHECK, date="2026-10-24", verify_failed=failed("0.20.2")))
        upgrade.finish(self.V, self.turn)
        self.assertIsNone(env.update_check(self.V)["verify_failed"])

    def test_finish_keeps_a_failure_for_a_newer_version(self):
        self.PLUGIN = "0.20.2"
        self.put_history("0.20.1")
        env.set_update_check(self.V, dict(upgrade.BLANK_CHECK, date="2026-10-24", verify_failed=failed("0.20.3")))
        upgrade.finish(self.V, self.turn)
        self.assertEqual(env.update_check(self.V)["verify_failed"]["version"], "0.20.3")


class CheckVerifyFailed(WithVerify):
    """驗收 7：--check 讀 update_check.verify_failed。"""

    LINE = "新版 0.20.2 在這台電腦跑不起來（hooks/guard.py 第 12 行：SyntaxError），先沒換"

    def test_same_version_adds_a_line(self):
        self.serve_zip("0.20.2", b"zip")
        env.set_update_check(self.V, dict(upgrade.BLANK_CHECK, date="2026-10-24", verify_failed=failed()))
        got = upgrade.check(self.V)
        self.assertEqual(got["verify_failed"], failed())
        self.assertIn(self.LINE, upgrade.check_lines(got))
        self.assertNotIn("source", got)

    def test_older_version_is_not_shown(self):
        self.serve_zip("0.20.3", b"zip")
        env.set_update_check(self.V, dict(upgrade.BLANK_CHECK, date="2026-10-24", verify_failed=failed()))
        got = upgrade.check(self.V)
        self.assertIsNone(got["verify_failed"])
        self.assertFalse(any("跑不起來" in ln for ln in upgrade.check_lines(got)))

    def test_check_writes_nothing_and_does_not_verify(self):
        self.serve_zip("0.20.2", b"zip")
        before = _backup.tree(self.V)
        upgrade.check(self.V)
        self.assertEqual(_backup.tree(self.V), before)
        self.assertEqual((self.fake.verifies, self.download.call_count), ([], 0))


if __name__ == "__main__":
    unittest.main()
