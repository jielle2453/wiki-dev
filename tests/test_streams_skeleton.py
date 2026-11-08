"""多人共用 1 驗收 12、12b：出貨 .gitignore／.gitattributes 的內容對齊常數，真的 git 裡該擋的擋、該看到的看得到，換行不轉換。"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from kb._lib import areas, credentials, skeleton, streams  # noqa: E402

GIT = shutil.which("git")
IGNORE = (ROOT / "skeleton" / ".gitignore").read_text(encoding="utf-8").splitlines()


class Content(unittest.TestCase):
    def test_ships_in_skeleton_files(self):
        self.assertIn(".gitignore", skeleton.files())
        self.assertIn(".gitattributes", skeleton.files())

    def test_gitattributes_is_no_text_conversion(self):
        self.assertEqual((ROOT / "skeleton" / ".gitattributes").read_text(encoding="utf-8"), "* -text\n")

    def test_credentials_patterns_aligned(self):
        for p in credentials.CREDENTIAL_PATTERNS + credentials.KEYFILE_PATTERNS:
            self.assertIn(p, IGNORE)

    def test_area_constants_aligned(self):
        self.assertIn(areas.HOLD_DIR + "/", IGNORE)
        self.assertNotIn("_個人/", IGNORE)  # #51：一般夾，跟型別夾一樣進 git

    def test_local_and_derived_aligned(self):
        for line in (".system/local/", ".system/legacy/", "系統/*", "/總目錄.md", ".system/asks_seen.json",
                     ".obsidian/plugins/wiki-with-willy/data.json"):
            self.assertIn(line, IGNORE)
        self.assertNotIn("!系統/客戶設定檔.md", IGNORE)  # 設定檔 md 不進 git（#42，jacky 2026-11-05 定）
        for spec in streams.KINDS.values():  # 衍生副本不進同步
            self.assertIn(spec[0], IGNORE)
        for _base, rel in streams.VIEWS.values():
            self.assertIn(rel, IGNORE)


@unittest.skipUnless(GIT, "沒有 git")
class RealGit(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def git(self, cwd, *args):
        r = subprocess.run([GIT, "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, capture_output=True,
                           text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, f"git {args}: {r.stdout}{r.stderr}")
        return r.stdout

    def put(self, root, rel, text="x\n"):
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text.encode("utf-8"))

    def test_status_hides_and_shows(self):
        v = self.tmp / "v"
        v.mkdir()
        self.git(v, "init", "-b", "main")
        shutil.copy(ROOT / "skeleton" / ".gitignore", v / ".gitignore")
        for rel in (".system/journal/a.jsonl", ".system/versions/t/x", "系統/日程.md", "總目錄.md", "暫存區/草稿.docx",
                    ".system/local/textcache/f.txt", ".system/agenda.json", ".system/asks_seen.json"):
            self.put(v, rel)
        for rel in ("檔案索引/客戶/報價-1234.md", ".system/streams/agenda/m-1.jsonl", "檔案索引/總目錄.md"):
            self.put(v, rel)
        out = self.git(v, "-c", "core.quotepath=false", "status", "--porcelain", "-uall")
        for hidden in ("journal", "versions", "系統", "暫存區", "textcache", "agenda.json", "asks_seen"):
            self.assertNotIn(hidden, out, hidden)
        self.assertNotIn("?? 總目錄.md", out)
        self.assertIn("檔案索引/客戶/報價-1234.md", out)
        self.assertIn("檔案索引/總目錄.md", out)  # 某個子夾也叫「總目錄.md」的不被擋
        self.assertIn(".system/streams/agenda/m-1.jsonl", out)

    def test_autocrlf_true_and_false_get_same_bytes(self):
        bare = self.tmp / "r.git"
        self.git(self.tmp, "init", "--bare", "-b", "main", str(bare))
        a, b = self.tmp / "a", self.tmp / "b"
        self.git(self.tmp, "clone", str(bare), str(a))
        self.git(a, "config", "core.autocrlf", "false")
        shutil.copy(ROOT / "skeleton" / ".gitattributes", a / ".gitattributes")
        self.put(a, "檔案索引/卡.md", "---\n名稱: 甲\n---\n內文\n")
        self.git(a, "add", "-A")
        self.git(a, "commit", "-m", "x")
        self.git(a, "push", "origin", "main")
        self.git(self.tmp, "clone", "-c", "core.autocrlf=true", str(bare), str(b))
        self.assertEqual((a / "檔案索引" / "卡.md").read_bytes(), (b / "檔案索引" / "卡.md").read_bytes())
        self.assertNotIn(b"\r", (b / "檔案索引" / "卡.md").read_bytes())


if __name__ == "__main__":
    unittest.main()
