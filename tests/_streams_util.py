"""多人共用 1 的測試共用：把某個狀態檔弄回「舊的整份 JSON」的樣子（沒有流水檔、沒有快取、沒有本機半份）。"""
import shutil
from pathlib import Path

from kb._lib import streams


def forget_state(V, name):
    """name 是 'inventory'、'pending'…：流水檔、快取、本機半份、舊路徑的副本都拿掉（等於這個狀態檔不存在）。"""
    V = Path(V)
    kind = streams.LEGACY.get(f"{name}.json", name)
    shutil.rmtree(streams.stream_dir(V, kind), ignore_errors=True)
    for p in [V / ".system" / "local" / f"{kind}.json", V / streams.legacy_rel(kind),
              *(V / ".system" / "local" / "cache").glob(f"{kind}.*")]:
        if p.is_file():
            p.unlink()


def break_state(V, name, text="{bad"):
    """這個狀態檔變成一份壞掉的整份 JSON。"""
    forget_state(V, name)
    p = Path(V) / ".system" / f"{name}.json"
    p.write_text(text, encoding="utf-8")
    return p
