"""測試用的真 git：本機裸 repo＋兩份 clone，不連網（多人共用 3）。"""
import os
import shutil
import subprocess

from pathlib import Path

from tests import _guard_fixture  # noqa: F401  (sys.path)

ENV = dict(os.environ, GIT_AUTHOR_NAME="測試", GIT_AUTHOR_EMAIL="t@local", GIT_COMMITTER_NAME="測試",
           GIT_COMMITTER_EMAIL="t@local", GIT_TERMINAL_PROMPT="0")


def have_git():
    return shutil.which("git") is not None


def git(cwd, *args, who=None):
    env = dict(ENV)
    if who:
        env.update(GIT_AUTHOR_NAME=who, GIT_COMMITTER_NAME=who)
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8", env=env)
    return r


def must(cwd, *args, who=None):
    r = git(cwd, *args, who=who)
    assert r.returncode == 0, (args, r.stdout, r.stderr)
    return r.stdout


def write(root, rel, text):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def make_team(tmp):
    """回 (bare, a, b)：裸 repo 與兩份 clone，初始有一個 commit、分支 main。"""
    tmp = Path(tmp)
    bare, a, b = tmp / "origin.git", tmp / "a", tmp / "b"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True, env=ENV)
    subprocess.run(["git", "clone", str(bare), str(a)], check=True, capture_output=True, env=ENV)
    must(a, "checkout", "-b", "main")
    write(a, "README.md", "x\n")
    must(a, "add", "-A")
    must(a, "commit", "-m", "init", who="甲")
    must(a, "push", "-u", "origin", "main")
    subprocess.run(["git", "clone", str(bare), str(b)], check=True, capture_output=True, env=ENV)
    must(b, "config", "merge.conflictstyle", "merge")
    return bare, a, b
