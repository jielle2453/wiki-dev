"""門檻與預設數字：config/defaults.json 是底，客戶端 .system/config.json 同鍵覆寫。
鍵一定要在 defaults.json 裡（每個鍵旁一個 _why_<鍵>），不在就 KeyError，客戶端檔加不了新鍵。
客戶端的值型別跟預設不同（例如 "十"）就用預設並寫一行 hook-errors.log，不讓守門因此 deny（第一輪 L5）。
"""
from pathlib import Path

from kb._lib import ledger
from kb._lib.io import read_json
from kb._lib.paths import plugin_root

DEFAULTS_REL = Path("config") / "defaults.json"
# 使用者說一句就改的門檻與頻率（kb config show／set／reset，放寬甲 D-322 第 2 件）；其他鍵是保護用的，不給改。
USER_KEYS = (
    "ingest_auto_max", "answer_verify_max", "agenda_window_days", "agenda_past_days", "lint_background_days",
    "pending_set_aside_days", "set_aside_wake_days", "lint_inferred_days", "preference_lint_days", "versions_keep_days",
    "versions_keep_turns", "backup_keep", "snapshots_keep", "home_timeline_days", "home_recent_max", "find_recent_days",
    "find_results_max", "card_parallel", "preference_max", "preference_max_chars", "ask_expire_days",
    "recard_idle_minutes", "card_section_map_min_chars", "card_section_map_min_pages", "index_icons", "index_order",
)
CLIENT_REL = Path(".system") / "config.json"


def defaults():
    return read_json(plugin_root() / DEFAULTS_REL, default={}) or {}


def get(vault, key):
    base = defaults()
    if key not in base or key.startswith("_why_"):
        raise KeyError(key)
    default = base[key]
    try:
        client = read_json(Path(vault) / CLIENT_REL, default={})
    except ValueError as e:
        ledger.log_error(vault, f"config.json 讀不了，{key} 用預設 {default!r}：{type(e).__name__}: {e}")
        return default
    if client is None:
        client = {}
    if not isinstance(client, dict):  # 整份不是物件（第二輪 L5 補）
        ledger.log_error(vault, f"config.json 不是物件（{type(client).__name__}），{key} 用預設 {default!r}")
        return default
    if key not in client:
        return default
    value = client[key]
    if type(value) is not type(default):  # bool 不當 int，"十" 不當 10
        ledger.log_error(vault, f"config.json 的 {key} 型別不對（{type(value).__name__}），用預設 {default!r}")
        return default
    return value
