# wiki-with-willy — 給改 repo 的 Claude

日期：2026-10-30（原始碼地圖拆到 ops/）
給誰看：改這個 repo 的 Claude 與人。怎麼用 plugin 看 README.md，設計與決策看 design/。
什麼時候更新：目錄或流程變了的那個 commit 一起改。

Codex 版在同一份程式（#56）：`hooks/codex.json`、`.codex-plugin/`、`.agents/`、`hooks/_codex.py`、`skeleton/AGENTS.md`、`安裝-Codex.md`。Claude 版的 `hooks/hooks.json` 不准為了 Codex 改；Codex 的對話由 `turn.py` 標 `codex`，要分兩邊的行為看這個旗標。main 不能直接給 Codex 裝：Codex 只執行預設檔名 `hooks/hooks.json`，發行時 `release.py` 把 `hooks/codex.json` 改名寫進公開版 `codex` 分支（D-539）；要在 main 試 Codex 得自己改名。

## 一、原始碼地圖（按需讀，在 `ops/`）

本檔只放每次改 repo 都用得到的；每個檔做什麼、改過什麼在 `ops/map-*.md`，**要改、要查那個檔時才讀對應那份**，先 Grep 檔名、讀那一列就好，不整份讀。清單會漂，以 `git ls-files` 為準；「尚未」是 design/architecture.md 第九節計畫中、這版還沒有的目錄。

| 我要動… | 讀 |
|---|---|
| `.claude-plugin/`、`.claude/`、README／CHANGELOG、`.gitattributes`、`config/`、`tools/`（發行程式） | `ops/map-config.md` |
| `scripts/kb.py`、`scripts/kb/*.py`（kb 子命令、守門判斷）、`scripts/kb/lint/` | `ops/map-cli.md` |
| `_lib` 的清冊、指紋、抽字、卡、實體、整理介面（plan、batches）、綜合卡、口述、推算、查實體、裁示、日程、設定檔、待處理、手改比對 | `ops/map-lib-knowledge.md` |
| `_lib` 的路徑、讀寫、設定、回合、日誌、office、成品、收件匣、備份、還原、清理、搬家、密碼、升級、自我檢查、遷移、骨架、動原檔、purge、env、指令解析、來源、憑證、留痕 | `ops/map-lib-platform.md` |
| `hooks/` | `ops/map-hooks.md` |
| `rules/`、`skills/`、`agents/`、`templates/`、`skeleton/`、`commands/` | `ops/map-skills.md` |
| `tests/`、`design/` | `ops/map-tests.md` |

改到某個檔的那個 commit 一起改 `ops/` 裡那一列；新檔加一列。

## 二、改完要做的事

1. 只跑跟這次改動有關的測試檔，不跑全套：spec「相關測試」列的檔，加上 `grep -l` 找到引用改動檔、版號、CHANGELOG 的測試與 `test_repo_hygiene`；全綠才算改完（design/conventions.md 技術基線「測試」）（jacky 2026-10-30 定、jielle2453 同意）。
2. 動過 `.claude-plugin/plugin.json` 或 `hooks/` 要跑 plugin 驗證（agent `plugin-dev:plugin-validator`）。
3. bump 版號的那個 commit 要同時寫 `CHANGELOG.md`，不事後補。

## 三、不准

- 不寫 plugin 的絕對路徑進任何狀態檔或設定（D-019）；路徑一律從 `__file__` 或 `${CLAUDE_PLUGIN_ROOT}` 推。
- 核心只用標準函式庫。
- `hooks/*.py` 以外不動 `sys.path`（hook 不是從 `scripts/` 跑的，那是唯一例外；`test_repo_hygiene.py` 守著）。
- 不 bump、不發行，除非設計 session 說發行。push 照 `design/process.md` 第八節：開工先 pull、做完 push、不准 force push，實作 session 不 push；寫 D、B 編號前先 pull，照那節的分段。

## 四、設計

- **越簡單越好**：先找最少改動的做法，能在 skill 加一句就不寫新程式、能用現有指令就不加新的。簡單才不容易出錯，也不會把 AI 綁死、變得死板（jacky 2026-11-02，起因 #31：現有 `kb lookup`、`kb convert` 就做得到，answer 加一句就夠）。
