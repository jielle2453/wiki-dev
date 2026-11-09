# Codex 版併進 main
日期：2026-11-09
狀態：定稿
版本：（發行後填）
來自：issue #56；併入 #55（發行工具支援 Codex 打包、路徑有 # 時擋下）；B 編號：無
區域：hooks、升級與發行、整理成卡、骨架


## 目的

Codex 版現在放在 wiki-dev 的長期分支 `codex`，main 每發一版都要手動併一次、在 Codex 實機測、再手動推到公開版的 `codex` 分支（jacky 11-09 定的甲）。兩條線並存，容易漏，也容易撞檔。

這一題把 Codex 用的部分改成「另外加的檔」，併進 main。之後一次發行就同時產出 Claude 版和 Codex 版，`codex` 長期分支不再維護（jacky 11-09 定的乙）。對客戶來說：
- Claude 版的客戶：行為一點都不變。知識庫裡多一個隱藏的 `AGENTS.md`。
- Codex 版的客戶：安裝的連結和指令不變（照舊 `--ref codex`）。升級到這一版之後，要在 `/hooks` 重新信任一次（hooks 檔改名了）。

## 決策

1. **兩份 hooks 檔並存。** `hooks/hooks.json` 是 Claude 版的，一字不改；Codex 的放 `hooks/codex.json`，由 `.codex-plugin/plugin.json` 的 `"hooks": "./hooks/codex.json"` 指過去。依據（2026-11-09 實測）：
   - Codex：官方文件寫「manifest 寫了 `hooks`，就用它、不讀預設的 `hooks/hooks.json`」。Codex 0.167.0 在空的 CODEX_HOME 實測，`codex app-server` 的 `hooks/list` 只列出 manifest 指到的那份。查證全文：`#待開-Codex版\文件\查證-Codex外掛能指定hooks檔.md`。
   - Claude Code 2.1.319：測試外掛同時放 `hooks/hooks.json` 和 `hooks/codex.json`，`claude -p --plugin-dir` 的 debug 紀錄只寫「Read hooks.json」，觸發的也只有 hooks.json 的 SessionStart、UserPromptSubmit，codex.json 的一個都沒跑。
   - 放棄的做法：一份 hooks.json 兩邊共用。兩邊的 matcher、環境變數、欄位不一樣（Codex 沒有 `onFailure`、`additionalContextLimit` 是 Codex 才有的），而且 Claude 版的行為不能變。
2. **派工的 prompt 看是哪一邊的對話。** Codex 的 UserPromptSubmit（payload 有 `turn_id`）在這個對話的 session 檔記 `client: "codex"`；`cards dispatch` 看這個對話的 session 檔，是 Codex 就用 Codex 的 prompt（先讀 card-maker.md、做完跑 `--done`），其他照 main 現在的 prompt。
   - 放棄的做法：兩邊共用 Codex 的 prompt。Claude 版的製卡助手會自己跑 `--done`，跟 SubagentStop 的 `agent_stop` 搶著收同一批，Claude 版的行為就變了。
   - 放棄的做法：看環境變數。Codex 執行指令時帶哪些環境變數沒有查證；`--session` 被插進指令已經實測過（`#待開-Codex版\文件\實機測紀錄.md` 第 6 條），session 檔比較可靠。
3. **AGENTS.md 每個知識庫都放。** `kb init` 不知道客戶用哪一邊，同一個知識庫也可能兩邊都開。實測（2026-11-09，Claude Code 2.1.319）：只有 AGENTS.md 時 Claude Code 會讀它；同一夾有 CLAUDE.md 時只讀 CLAUDE.md、不讀 AGENTS.md。willy 的知識庫一定有 CLAUDE.md，所以 Claude 版不受影響。
   - 已知代價：客戶把 CLAUDE.md 刪掉時，Claude Code 會改讀 AGENTS.md。兩份內容只差最後一段（開場段沒出現時怎麼自救），讀到 Codex 那段也不會做錯事。
4. **#55 併進來一起做。** 併完之後 Codex 版的內容就是 Claude 版 zip 的同一批檔，發行工具只要把同一批檔另外推到公開版的 `codex` 分支。如果先單獨做 #55，它打包的來源是 wiki-dev 的 `codex` 分支，這一題做完又得改一次。`#` 的檢查也在 `release.py` 同一個地方，一起做。
5. **Codex 照舊從公開版的 `codex` 分支裝。** Codex 的市集不認 zip，只認 git 的內容：Codex 文件寫的 plugin 來源只有本機路徑、`url`（repo 根）、`git-subdir` 三種，沒有 Claude 那種 `archive`。所以發行時把 zip 裡的同一批檔推到公開版的 `codex` 分支，用一般的 commit 接在後面，不 force push。客戶的安裝連結和指令都不變。
6. **wiki-dev 的 `codex` 長期分支**：這一題發行後不再併、不再推。要不要刪由主管決定，不在這一題做。

## 要做的事

### 甲：程式併進 main（實作第一支）

照搬的來源是 wiki-dev 的 `codex` 分支（`bb781585`，`git diff origin/main...codex` 共 39 個檔）。

1. `hooks/codex.json`（新）：內容照搬 codex 分支的 `hooks/hooks.json`，description 開頭改成「Codex 版：」。`hooks/hooks.json` 不動。
2. `.codex-plugin/plugin.json`（新）：照搬，加 `"hooks": "./hooks/codex.json"`，`version` 跟 `.claude-plugin/plugin.json` 同一個。
3. `.agents/plugins/marketplace.json`（新）：照搬（name、displayName 都是 `wiki-with-willy`，source `local` `./`）。
4. `hooks/_codex.py`（新）、`hooks/guard.py`、`hooks/output_log.py`、`hooks/stop.py`、`hooks/turn.py`：照搬 codex 分支的版本。Claude 那條路（payload 沒有 `turn_id`）的判斷要跟 main 現在逐行相同；跟 main 衝突的地方以 main 為準，再把 Codex 的分岔接上去。
5. `hooks/turn.py`：Codex 的 UserPromptSubmit 開回合時，session 檔記 `client: "codex"`（決策 2）。
6. `scripts/kb/_lib/batches.py`：
   - `PROMPT` 留 main 的；另加 `PROMPT_CODEX`，內容是 codex 分支的 `PROMPT`。
   - `maker()` 照搬。
   - `dispatch`、`dispatch_adopt` 看這個對話的 session 檔，`client` 是 `codex` 就用 `PROMPT_CODEX`。
   - `batch_done` 照搬。
7. `scripts/kb/cards.py`：`cards batch <批次> --done [--failed "<編號>：<原因>" …]` 照搬（`_batch_done`：先試 `self_done`，不是 self 的批次再走 `batch_done`；`--failed` 沒帶 `--done` 時報錯、回 2）。
8. `scripts/kb/guard.py` 的 `RESERVED` 加 `".codex": "Z7"`；`scripts/kb/init.py`、`scripts/kb/_lib/skeleton.py` 的 `HIDDEN_ITEMS` 加 `"AGENTS.md"`。
9. `skeleton/AGENTS.md`（新）：從 main 的 `skeleton/CLAUDE.md` 重做，只把「對話開頭應該有一段「【wiki-with-willy】」…」那段換成 codex 分支 AGENTS.md 的 Codex 版。`config/skeleton_history.json` 由發行時的 `release.py build --prepare` 加。
10. skill 改成兩邊都通的寫法，句子照搬 codex 分支：
    - `skills/ingest/SKILL.md`「讀派工結果」「客戶說停」兩行。
    - `skills/ingest/references/commands.md` 的 dispatch、stop 兩處。
    - `skills/build/SKILL.md` 第 45 行。
    - `skills/ingest/references/carding.md` 線上文件那句。
    - ingest 的本文要壓到上限 4400 字以內：main 現在是 4484 字，本來就超過。
11. `安裝-Codex.md`（新）：照搬公開版 `codex` 分支的。升級那節加一句：「升到 0.35 起的第一次，hooks 檔改名，要重新信任一次」。版號實作時寫「發行時填」。
12. `CLAUDE.md`（repo 的）：拿掉「這是 codex 長期分支」那段，改成一句：「Codex 版在同一份程式：`hooks/codex.json`、`.codex-plugin/`、`.agents/`、`hooks/_codex.py`，Claude 版的 `hooks/hooks.json` 不准為了 Codex 改。」
13. `ops/map-*.md`：新檔各加一列，改到的檔照實改。

### 乙：發行工具（#55，實作第二支，甲做完之後）

14. `tools/release.py`：
    - `ALLOW_DIRS` 加 `.codex-plugin`、`.agents`；`ALLOW_FILES` 加 `安裝-Codex.md`。
    - `build` 檢查 `.codex-plugin/plugin.json` 的 `version` 等於 `.claude-plugin/plugin.json` 的，不等就停。
    - `publish` 在 zip 上傳、`marketplace.json`／`rollout.json` 推完之後，把 zip 裡的同一批檔推到公開版的 `codex` 分支：
      - 先 checkout 公開 clone 的 `codex` 分支，刪掉上一版的檔，再放這一版的檔。另外補 `.gitattributes`（`* text=auto eol=lf`）和 README.md（內容同 `安裝-Codex.md`）。
      - commit 訊息寫「codex: <版號>」，push。不 force push。
      - 推完切回 main。
    - 這一段失敗時，重跑 `publish` 要接得上：release 已經有了就補傳 zip，`codex` 分支已經是這一版就跳過。
15. `tools/release.py`：`build`、`publish` 一開始就檢查 `--repo`、`--public`、zip 輸出夾這三個路徑，任一個有 `#` 就停，什麼都不上傳、不推。訊息：「路徑裡有 #：<路徑>。gh 會把 # 後面當成標籤、Codex 會把它當分支名，請換到沒有 # 的資料夾再跑。」

## 來源程式對照

不從舊程式來。照搬的來源是 wiki-dev 的 `codex` 分支（`bb781585`）；它自己的 spec 是 `design/specs/2026-11-07-Codex版.md`（只在 codex 分支），payload 怎麼轉接、同意流程、`--done` 都照那份的「資料與介面格式」與裁定 8，不改。

| codex 分支的檔 | 怎麼用 |
|---|---|
| `hooks/hooks.json` | 照搬成 `hooks/codex.json` |
| `hooks/_codex.py`、`tests/test_codex_adapter.py` | 照搬 |
| `hooks/guard.py`、`output_log.py`、`stop.py`、`turn.py` | 照搬；Claude 那條路以 main 為準 |
| `batches.py` 的 `PROMPT` | 改名成 `PROMPT_CODEX`（改介面） |
| `batches.batch_done`、`cards._batch_done` | 照搬 |
| `tests/test_hooks_*.py` 裡改成檢查 Codex 設定值的那幾條 | **不要**。main 的照舊檢查 `hooks.json`；檢查 `codex.json` 的另外加 |
| `design/specs/2026-11-07-Codex版.md` | 不搬，留在 codex 分支當紀錄 |

## 資料與介面格式

**session 檔**（`.system/turns/<sid>.json`）多一個欄位：

```json
{"client": "codex"}
```

只有 Codex 的對話才寫；沒有這個欄位就當 Claude。turn.py 每次 Codex 開回合都寫一次，冪等。

**`cards dispatch --json` 的 `batches[].prompt`**：
- Claude 的對話：跟 main 現在一字不差：`批次 {batch}：{what}。第一步跑 {prefix} cards batch {batch} --json，照它做，做完照你的說明回報。`
- Codex 的對話：`批次 {batch}：{what}。你是製卡者：先讀 {maker}，照它做；第一步跑 {prefix} cards batch {batch} --json。做完跑 {prefix} cards batch {batch} --done（沒做成的每份加一個 --failed "<編號>：<原因一句>"），最後一則照 card-maker.md 的回報格式。`（`{maker}` 是 `"<plugin_root>/agents/card-maker.md"`，執行時算、不存）
- 兩邊的 `agent`、`description`、`self` 批次的 `do` 都一樣。

**`kb cards batch <批次> --done [--failed "<編號>：<原因>" …] [--json]`**：

| 情況 | 結束碼 | 輸出 |
|---|---|---|
| self 的批次，是這個對話的 | 0 | 「批次 X 做完了；接著跑 kb cards dispatch --json」 |
| 交給製卡者的批次，還在認領中 | 0 | 「批次 X 記成做完：做好 N、沒做成 M（不是這批的編號沒記：…）；接著跑 kb cards dispatch --json」。`--json` 時是 `{"batch","done","failed","ignored"}` |
| 停了、做完了、放掉了、過期了 | 3 | 「這批已經停了或做完了」 |
| `--failed` 沒帶 `--done` | 2 | 錯誤訊息 |

**`.codex-plugin/plugin.json`**：照搬，再加一行 `"hooks": "./hooks/codex.json"`。

**release.py 的 `#` 檢查**：在 `build`、`publish` 參數解析完、還沒做任何事之前跑；路徑有 `#` 就印上面那句訊息，結束碼 2。

## 可以動 / 不可以動

可以動：
- 「要做的事」列的檔。
- `tests/test_codex_adapter.py`（新）、`tests/test_scripts_cards_dispatch.py`、`tests/test_skill_ingest.py`、`tests/test_scripts_init_cli.py`、`tests/test_lib_skeleton.py`、`tests/test_cardmaker_b_section.py`、`tests/test_tools_release.py`。
- `tests/test_hooks_*.py`：只准**加**檢查 `codex.json` 的測試，原有斷言不改。

不可以動：
- `hooks/hooks.json`。
- `hooks/session.py`、`hooks/subagent.py`、`hooks/session_end.py` 的 Claude 行為。
- `scripts/kb/` 的守門判斷：只准加保留區與隱藏清單。
- `rules/`、`agents/`。
- 上面沒列的 skill。
- `config/skeleton_history.json`：發行時才由工具加。
- wiki-dev 的 `codex` 分支、公開 repo：實作時用本機的假公開 repo 測。

相關測試：`tests/test_codex_adapter.py`、`test_hooks_guard.py`、`test_hooks_output_log.py`、`test_hooks_stop.py`、`test_hooks_turn.py`、`test_hooks_session.py`、`test_hooks_subagent.py`、`test_scripts_cards_dispatch.py`、`test_cardmaker_b_section.py`、`test_skill_ingest.py`、`test_lib_skeleton.py`、`test_scripts_init_cli.py`、`test_guard_decide.py`、`test_guard_pw.py`、`test_lib_selftest.py`；乙另加 `test_tools_release.py`、`test_release_obsidian.py`；都加 `test_repo_hygiene.py`。

## 驗收準則

甲：
1. 相關測試全過：`python -m pytest -q <上面的檔>`，結束碼 0。
2. Claude 版的測試沒被改：`git diff origin/main -- tests/test_hooks_guard.py tests/test_hooks_output_log.py tests/test_hooks_stop.py tests/test_hooks_turn.py tests/test_hooks_session.py tests/test_hooks_subagent.py` 只有新加的行，沒有刪掉或改掉的斷言。
3. `git diff origin/main -- hooks/hooks.json` 是空的。
4. Claude Code 只讀 `hooks.json`：在測試庫跑 `claude -p "hi" --plugin-dir <worktree> --debug-file <檔>`，debug 檔裡登記的 willy hook 都來自 `hooks/hooks.json`，沒有 `codex.json`；SessionStart 的開場段照常出現。
5. Codex 只讀 `codex.json`：在空的 CODEX_HOME 從 worktree 加本機市集、裝外掛，用 `codex app-server` 的 `hooks/list` 查（腳本做法見決策 1 的查證文件）。willy 的 hook key 全部是 `wiki-with-willy@…:hooks/codex.json:…`，總共 6 個事件（session_start、user_prompt_submit、pre_tool_use、post_tool_use、stop、session_end），沒有 `hooks/hooks.json` 的 key。
6. 派工 prompt 分兩邊：在 `test_scripts_cards_dispatch.py` 加兩條。
   - session 檔沒有 `client` 時，`prompt` 等於 main 的格式。
   - session 檔有 `client: "codex"` 時，`prompt` 含 `card-maker.md` 的絕對路徑和 `--done`。
7. `hooks/turn.py`：Codex 的 payload（有 `turn_id`）開回合後 session 檔有 `client: "codex"`；Claude 的 payload 沒有這個欄位（`test_hooks_turn.py` 新加）。
8. `--done` 的四種情況照「資料與介面格式」那張表（照搬 codex 分支的測試）。
9. `kb init` 新建的知識庫有 `AGENTS.md`，而且是隱藏的；`.codex` 在守門裡是 Z7（照搬的測試）。
10. ingest 本文 ≤ 4400 字（`test_skill_ingest.py` 原有的上限測試過）。
11. `.codex-plugin/plugin.json` 和 `.claude-plugin/plugin.json` 的 `version` 一樣（`test_repo_hygiene.py` 加一條）。
12. `test_repo_hygiene.py` 過。

乙：
13. `release.py build` 產出的 zip 裡有 `.codex-plugin/plugin.json`（帶 `hooks` 欄位）、`.agents/plugins/marketplace.json`、`hooks/codex.json`、`skeleton/AGENTS.md`、`安裝-Codex.md`；沒有 `design/`、`tests/`。
14. 兩個 `plugin.json` 的 version 不同時，`build` 停下來、訊息講清楚。
15. `publish` 用本機的假公開 repo（bare repo 加一份 clone）、`gh` 換成假的，測三件事：
    - 公開 repo 的 `codex` 分支多一個 commit「codex: <版號>」，檔案清單等於 zip 的加 `.gitattributes`、README.md；main 照舊更新 `marketplace.json`、`rollout.json`。
    - 沒有用 force push。
    - 中途失敗後重跑接得上。
16. `--repo`、`--public`、輸出夾任一個路徑有 `#` 時，`build`、`publish` 結束碼 2、印出那句訊息，`gh` 一次都沒被叫到。
17. 從假公開 repo 的 `codex` 分支，用空的 CODEX_HOME 跑 `codex plugin marketplace add <假 repo> --ref codex`、`codex plugin add wiki-with-willy@wiki-with-willy`，裝得起來，`hooks/list` 跟第 5 條一樣。

## 確認情境

1. **自動**（Claude 版沒變）：在測試庫用 `claude -p --plugin-dir <worktree>`，一句一個新對話，跑兩句：
   - 「整理一下」：派製卡助手，做到 `done`，回答同 main。
   - 「<測試庫裡某個客戶> 的報價多少」：答案在前、附出處。
2. **人眼**（Codex 實機，這台裝了 Codex 0.167.0）：從假公開 repo 裝，重新信任 6 個 hook，在測試庫跑三件事：
   - 開場段出現。
   - 「整理一下」：子代理做完並跑 `--done`；或沒有子代理時自己做完。
   - 「X 報價多少」：答案對、有核對。
3. **人眼**（Claude 桌面版從市集升級）：從 0.34.0 升到這一版，開場正常；知識庫多一個隱藏的 `AGENTS.md`，升級沒有因為這個檔問客戶。
4. **人眼**（Codex 從 0.34.0 升級）：照 `安裝-Codex.md` 的升級步驟（`marketplace upgrade`、重裝），`/hooks` 要求重新信任；信任後開場正常。

## 不做

- Codex 的升級流程（`kb upgrade` 在 Codex 底下照舊回「做不到」）、製卡子代理的 TOML 定義、MCP 工具的守門、建置檢查改讀 Codex 設定、讀 Codex 對話紀錄的貼圖。這些都同 Codex 版 spec 的「不做」。
- Codex 桌面版的確認：等有人在新電腦試用。
- 刪 wiki-dev 的 `codex` 分支（決策 6）。
- 密碼指令後面接 ` #x` 能繞過 D-212（Codex 版 spec 裁定 1、6）：主管另開題，不在這一題。

## 裁定（測試、確認之後才有）

### 實作疑義

1. **session 檔記的是 `codex: true`，不是 `client: "codex"`**（決策 2、資料與介面格式、驗收 6、7 照這條讀）。原因：照現有的回合旗標做（`turn.MARK_FLAGS` 加 `codex`，用 `turn.mark_session` 標），「退回自己這句」開的新回合會照舊把旗標帶下去，不用另寫繼承。沒有這個鍵就當 Claude。
2. 驗收 7 寫在 `tests/test_codex_adapter.py`（`Consent.test_codex_turn_marks_session`），不在 `test_hooks_turn.py`；驗收 11 也寫在 `test_codex_adapter.py`（`Config.test_codex_manifest_version_matches`，codex 分支已經有），不在 `test_repo_hygiene.py`。
3. review（claude -p、Sonnet、0.56 美元，2026-11-09）10 條：
   - **修了**：
     - (1) `hooks/_codex.py` 載不進來時，Claude 的 payload 也被當守門出錯擋下。改成先看 `turn_id`，沒有就照 Claude 判，不碰 `_codex`。
     - (5) 公開 clone 不在 main 時，`publish`／`rollout` 會把清單推到別的分支。`_require_clean` 改成不在 main 就停。
     - (6) codex 那步失敗，會留下 main 沒有的檔，擋住下一次切換。切回 main 後刪掉這次寫出來、main 沒有的檔。
     - (7) 本機 codex 分支跟遠端分岔就卡住。改成遠端有，就一律從遠端那個接。
     - (8) 路徑全放指令列，日後可能撞 Windows 上限。改用 `--pathspec-from-file`。
     - (9) Codex manifest 沒有 `hooks`、或路徑出了外掛夾，都沒有擋。改成這兩種都報；`.agents/plugins/marketplace.json` 也要在。
     - 另外補測試：沒有 force push、新版拿掉的檔 codex 分支也拿掉、不在 main 就停。
   - **不修**：
     - (2) `hooks/` 進了 `sys.path`：main 的 `turn.py`、`stop.py` 本來就這樣做。
     - (3) `output_log` 打回改成最後併成一行印：Claude 的 payload 只有一份，客戶看到的一樣，只差印的時間點。
     - (10) 不是 bug。
     - 驗收 6 裡 `dispatch_adopt` 的 Codex prompt 沒有另外測：它跟 `dispatch` 用同一個 `_prompt`。

## 紀錄（設計 session 結案時填）
- 實作 commit：
- 測試報告：
- 確認報告：
- 發行版號：
- 類似問題查核：
