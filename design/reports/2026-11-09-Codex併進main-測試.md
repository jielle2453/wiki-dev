# Codex 版併進 main — 測試報告

日期：2026-11-10
給誰看：willy設計二（設計 session）、jacky
測的版本：分支 `spec/Codex併進main`，`6ef79f2b`（開跑前 `git merge main`，main＝`0997f4c0`，只帶進 design/；實作 `177d1132`、`653b8fb2`，review 修正 `8654d48f`、`e1dba56b`、`b5945609`）
做法：照 `design/specs/2026-11-09-Codex併進main.md` 驗收 1～17 逐條實跑；只跑相關測試；security-review、plugin-validator 走 `claude -p`；測試用的庫、CODEX_HOME、假公開 repo、拋棄 clone 都在 `C:\Users\user\.aaproject\LLM-Wiki\willy-測試\開發\第二組-56測試\`（主管 2026-11-10 改的位置，沒有 `#`）。

## 結論

**不能直接進確認。** 17 條：15 過、2 不過（1、11）、0 未驗。不過的兩條是同一個原因（發現 #1）：merge main 之後 `.claude-plugin` 是 0.36.0、`.codex-plugin` 還停在 0.34.0。改一行版號就好，改完回測只要跑 `test_codex_adapter.py` 加 `test_repo_hygiene.py`。其他相關測試的紅都在 main 上一樣會紅（負載），不是這題造成的（見驗收 1）。

## 驗收逐條

| # | 判定 | 證據 |
|---|---|---|
| 1 | 不過 | 22 檔（spec 列的 17 檔＋`grep -l` 找到的 `test_lib_batches`、`test_lib_turn`、`test_guard_relax_a`、`test_memory_off`＋`test_repo_hygiene`）`python -m pytest -p xdist -n 4`：776 過、54 紅（1:48:17，開跑前後 HEAD 都是 `6ef79f2b`）。紅的分三類：①`test_codex_adapter::Config::test_codex_manifest_version_matches`：真的壞，見 #1。②53 條負載相關：序列重跑剩 20 條（15 條 `test_hooks_session`、4 條 `test_hooks_turn`、1 條 `test_lib_selftest`）；這 20 條在開發 repo main（`f09f8033`，design/ 以外與 `0997f4c0` 相同，只讀跑，跑前後 `git status` 一樣）交替各跑兩輪：worktree 15、14 紅，main 14、3 紅，同一批在兩邊都會紅、跟負載走（ops 記過的 `turn_scan_seconds` 1.5 秒）。③`test_hooks_turn::EachTurnChecks` 兩條在 worktree 一直紅、main 一直綠：根因是新 worktree 的 `scripts/kb` 沒有 `.pyc`（hooks 都設 `dont_write_bytecode`；開發 repo 有 42 個），每句開頭的檢查要邊編譯邊跑、超過 1.5 秒預算整段不印。驗法：拋棄 clone（程式同 `6ef79f2b`）`compileall` 之後，與 main 交替各 4 次，分支 2 紅／4、main 4 紅／4（當時 CPU 約 80%），同等條件下沒差。不是這題的程式造成 |
| 2 | 過 | `git diff origin/main -- tests/test_hooks_{guard,output_log,stop,turn,session,subagent}.py`：0 行（連新加的都沒有；Codex 的測試照實作疑義 2 寫在 `test_codex_adapter.py`） |
| 3 | 過 | `git diff origin/main -- hooks/hooks.json`：0 行 |
| 4 | 過 | 測試庫：`來源.zip` 還原、`kb init 第二組-56測試\庫`。`claude -p "hi" --plugin-dir <worktree> --debug-file … --setting-sources project,local`（預設權限）。debug 檔只有「Read hooks.json for plugin wiki-with-willy … hooks\hooks.json」，`codex.json` 出現 0 次；跑到的是 hooks.json 的 SessionStart、UserPromptSubmit、Stop。第二次跑 SessionStart「finished with status 0 (4277ms)」，additionalContext 1875 字以「【wiki-with-willy】」開頭，回答正常。第一次（pytest 同時在跑）SessionStart 13.8 秒逾時、開場段沒出現、AI 照 CLAUDE.md 自救；負載造成，見 #4 |
| 5 | 過 | 空 CODEX_HOME（`第二組-56測試\codex-home`），`codex plugin marketplace add <worktree>`、`codex plugin add wiki-with-willy@wiki-with-willy`，不用登入。`codex app-server` 的 `hooks/list`（cwds＝測試庫，腳本 `第二組-56測試\hookslist.py`）：6 個 key，全是 `wiki-with-willy@wiki-with-willy:hooks/codex.json:{pre_tool_use,post_tool_use,session_start,session_end,user_prompt_submit,stop}:0:0`，沒有 `hooks/hooks.json`，warnings、errors 都空 |
| 6 | 過 | `test_scripts_cards_dispatch.py`：新加 `test_codex_session_gets_codex_prompt`（標了 codex 的對話，prompt 逐字等於 spec 的 Codex 格式，含 `"<plugin_root>/agents/card-maker.md"` 與 `--done`）；沒標的對話由原有斷言（第 66 行，逐字等於 main 格式）守著；第 1 條的跑法都過 |
| 7 | 過 | `test_codex_adapter.py::Consent::test_codex_turn_marks_session`（實作疑義 1、2：記 `codex: true`）過。`scripts/kb/_lib/turn.py` 的 diff 只有 `MARK_FLAGS` 加 `"codex"` 一個字 |
| 8 | 過 | 交給製卡者的批次、`--failed` 只收這批：`test_codex_done_closes_batch_then_dispatch_continues`；停了／過期與 `--failed` 單獨（2）：`test_codex_done_refuses_expired_and_failed_alone`；self 的批次：`test_cardmaker_round1.py::…::test_self_line_and_done`（補跑，1 passed） |
| 9 | 過 | `kb init` 新庫有 `AGENTS.md`，`attrib` 顯示 `A H`；`test_scripts_init_cli`、`test_lib_skeleton` 過。`.codex`：直接呼叫 `guard.decide`，Write `庫\.codex\config.toml`→deny Z7、Read→allow Z7，跟 `.claude` 一樣。但沒有測試守著，見 #3 |
| 10 | 過 | ingest 本文（`split("\n---\n",1)[1].strip("\n")`）HEAD 4395 字、main 4476 字，上限 4400。上限測試在 `test_small_fixes_1026.py:111`，不在 spec 寫的 `test_skill_ingest.py`，見 #2 |
| 11 | 不過 | `test_codex_adapter.py::Config::test_codex_manifest_version_matches` 紅：`.codex-plugin/plugin.json` 0.34.0、`.claude-plugin/plugin.json` 0.36.0。見 #1 |
| 12 | 過 | `test_repo_hygiene.py` 在第 1 條的跑法裡全過 |
| 13 | 過 | 拋棄 clone（`第二組-56測試\dev`）bump 成 0.37.0、`build --prepare`、tag，`release.py build v0.37.0 --repo dev --out out`：「版本 0.37.0，203 個檔」。zip 裡有 `.codex-plugin/plugin.json`（`hooks`＝`./hooks/codex.json`）、`.agents/plugins/marketplace.json`、`hooks/codex.json`、`skeleton/AGENTS.md`、`安裝-Codex.md`；`design/`、`tests/` 0 個。自我檢查在高負載下有兩次 5 秒逾時，重跑就過 |
| 14 | 過 | 同一個 clone 只 bump `.claude-plugin` 時 build 停：「`.codex-plugin/plugin.json 的版本是 0.34.0，tag 是 0.37.0（要跟 .claude-plugin 同一版）`」，結束碼 1 |
| 15 | 過 | 假公開 repo：`public.git`（bare）＋`public`（clone，origin 抓取網址是不存在的 `github.com/fake-owner-zz56/…`、推送網址是 bare），`gh` 換成假的（`pubharness.py`：記呼叫、遇到 force 參數就中止）。①0.37.0：bare 的 codex 分支多「codex: 0.37.0」，檔案 204＝zip 203＋`.gitattributes`，README.md 等於 `安裝-Codex.md`；main 有「marketplace: 0.37.0」「rollout: 0.37.0」。②沒有 force push：所有 push 只有 `push -q origin HEAD` 兩次和 `push -q origin HEAD:refs/heads/codex`。③0.38.0（另外拿掉一個 template）讓 codex 推送失敗：結束碼 1、clone 回到 main、沒有殘留檔、遠端 codex 仍是 0.37.0；重跑：gh 走 `release upload --clobber`，codex 分支「codex: 0.38.0」的父 commit 是 0.37.0 那個（一般 commit 接在後面），拿掉的 template 也拿掉了 |
| 16 | 過 | `第二組-56測試\#hash` 當 `--out`、`--repo`（build）、`--public`、`--repo`（publish）四種：都印「路徑裡有 #：…」、結束碼 2，harness 記到的指令（含 gh、git）0 個 |
| 17 | 過 | 新的空 CODEX_HOME（`codex-home2`）。Codex 的 `marketplace add` 只認 https／ssh 的 git 網址（本機路徑會當 local、不收 `--ref`；`file://` 被拒），所以用暫時的 `GIT_CONFIG_GLOBAL` 把 `https://github.com/fake-owner-zz56/fake-public-zz56.git` 改寫到本機 bare。`marketplace add … --ref codex`、`plugin add` 裝到 0.38.0（github 上沒有這個 repo，所以確定是從本機 bare 拿的）；`hooks/list` 跟第 5 條一樣：6 個 `hooks/codex.json` key，warnings、errors 空 |

## 發現

| # | 嚴重 | 內容 | 證據 |
|---|---|---|---|
| 1 | 高 | merge main 之後 `.codex-plugin/plugin.json` 是 0.34.0、`.claude-plugin` 是 0.36.0：驗收 1、11 紅，發行時 build 會擋。根因：實作之後 main 發了 0.35.0、0.35.1、0.36.0，合併不會動 Codex 那份。以後每次 bump 都要兩份一起改，process 第六節的發行步驟沒寫（build 會擋，所以不會發錯，只會發到一半停）。plugin-validator 也報同一條 | 驗收 11；`grep '"version"' .claude-plugin/plugin.json .codex-plugin/plugin.json` |
| 2 | 低 | spec 驗收 10 寫「`test_skill_ingest.py` 原有的上限測試」，4400 字上限其實在 `test_small_fixes_1026.py:111`，那個檔也不在相關測試清單裡 | 驗收 10 |
| 3 | 低 | 驗收 9 寫「`.codex` 在守門裡是 Z7（照搬的測試）」，但 tests 裡找不到檢查 `.codex` 保留區的測試；程式是對的（直接呼叫 `guard.decide` 驗過） | `grep -rn '\.codex' tests/*.py` 只有 `.codex-plugin` 相關 |
| 4 | 低 | spec 以外：新裝（沒有 `.pyc`）時第一次 SessionStart 與每句開頭的檢查容易超過預算，開場段或提示行不出現。main 一樣（用 `PYTHONPYCACHEPREFIX` 指到空夾跑 main，兩條都紅；這個做法連標準庫的快取也拿掉，條件比實際嚴），第一組的背景比對（裁定 22 compileall）在處理，這題不用改 | 驗收 1 第③類、驗收 4 第一次 |
| 5 | 低 | security-review G1：Codex 的對話 cwd 在知識庫外、指令寫 `cd $變數 && apply_patch …` 時，`CD_RE` 不展開變數，patch 裡的檔不會照 Write／Edit 判；cwd 在庫外整條殼指令也是不表態。要 AI 從庫外開、又用變數 cd，可能性低 | `hooks/_codex.py:110-119` |
| 6 | 低 | security-review C1：Codex 的密碼同意只綁指令 hash，不綁客戶被問了什麼；AI 可以先跑被擋、再問一句不相干的「要繼續嗎」，客戶回「好」就放行。這是 Codex 版 spec 裁定 8 的設計（照搬），不是這題新加的 | `hooks/_codex.py:155-185` |
| 7 | 低 | plugin-validator：`hooks/codex.json` 沒有對應 Claude 版 `onFailure: block` 的設定。Python 例外時 `guard.py` 自己在庫內 deny（有測試），但 Python 不見或逾時時 Codex 擋不擋沒有查證 | `hooks/codex.json` |
| 8 | 低 | security-review R1：公開 clone 裡有沒追蹤、跟「上一版有、這版拿掉」的檔同名的檔時，`checkout -f` 會蓋掉、收尾會刪掉（同名檢查只看這一版要寫的檔）。範圍在 clone 內 | `tools/release.py:658`、`:684-688` |

## plugin-dev 審查

- 依據 `plugin-dev:hook-development`（0.1.1）審 `hooks/`：`hooks.json` 沒動；`codex.json` 6 個事件都是 command、路徑用 `${PLUGIN_ROOT}`（Codex 的變數，`安裝-Codex.md` 記實測可代換）、有 timeout；hook 程式的 Claude 那條（payload 沒有 `turn_id`）在 `guard.py` 是原 main 邏輯原樣搬進 `_judge`，`_codex` 載不進來時 Claude 照舊、Codex 擋（fail closed）；`stop.py` 只在 Codex 時多印 `{}`；`turn.py` 只在 Codex 時標 `codex`、記同意。沒有新問題。
- `claude plugin validate .`：通過，2 個警告都是本來就有的（repo 根目錄 CLAUDE.md、沒有 icon）。
- agent `plugin-dev:plugin-validator`：這個 session 的 Agent 工具沒有這個型別，改用 `claude -p --plugin-dir <plugin-dev 0.1.1> --agent plugin-dev:plugin-validator` 跑（0.71 美元）。結果：Claude 版可以載入，Codex 的檔不影響；錯誤 1 條＝#1；警告裡跟這題有關的是 #7，其他（`card-maker` 的寫法、`onFailure` 欄位）都是本來就有的。

## security-review

`claude -p --model sonnet`，指示照 `~/.claude/ops/API-claude-p.md`（先讀裁定段、已接受的不列），0.44 美元。使用者環境變數裡沒有 `ANTHROPIC_API_KEY`（只查有無），所以走的是本機登入，不是 API。結果：沒有高；中 2 條（G1、C1），讀碼後各評為低（#5、#6）；低若干，記進發現的只有 #7（validator）與 #8（R1），其餘是前提很強的（遠端 repo 被竄改、`rollout` 不檢查 `#`）。確認沒問題的：Claude payload 的判斷跟 origin/main 相同、`.codex` 只加進 RESERVED、兩份 `HIDDEN_ITEMS` 一致、release 沒有 force push、檔名照字面、所有 git 呼叫不經 shell。

## 沒測到的

- 確認情境（自動、人眼）：不在測試這一步。
- Codex 實機跑對話（開場段、整理、守門擋下）：只驗到 `hooks/list` 登記，沒有登入跑對話。
- #7：Codex 底下 Python 不見或 hook 逾時時是擋還是放。
- 驗收 15 的 `gh` 是假的、清單抓取改讀本機 bare repo：真的 GitHub Releases 與 raw 網址沒碰。
- 本機 `codex` 分支跟遠端分岔、公開 clone 停在 codex 分支：只靠 `test_tools_release.py` 的單元測試（過），沒有端對端再跑。

## 附：測試計畫（開跑前寫的，留著對照）

等主管「可以跑」才執行（第一組在量秒數）。開跑前先 `git merge main`（main 新 commit 只改 design/），有衝突停下回報。

位置（主管 2026-11-10 改）：測試庫、codex-home、假公開 repo、build 輸出一律放 `C:\Users\user\.aaproject\LLM-Wiki\willy-測試\開發\第二組-56測試\`（沒有 `#`）；開場寫的 `#52-56-第二組\測試-56\` 不用。下表的 `測試-56\` 都指這個資料夾。

| 驗收 | 做法 | 位置／注意 |
|---|---|---|
| 1、12 | `python -m pytest -q` spec「相關測試」15 檔＋`test_tools_release.py`、`test_release_obsidian.py`＋`test_repo_hygiene.py`；再加 `grep -l` 找到引用改動檔的測試（`_codex`、`batches`、`cards`、`skeleton`、`init`、`kb/guard`、`_lib/turn`、`release`、`codex.json`、`安裝-Codex`），去掉已列的 | worktree；紅的到開發 repo `wiki-with-willy` 的 main 只讀地跑同一檔，分新壞／本來就壞 |
| 2 | `git diff origin/main -- tests/test_hooks_{guard,output_log,stop,turn,session,subagent}.py`，看有沒有 `-` 行 | |
| 3 | `git diff origin/main -- hooks/hooks.json` 要空 | |
| 4 | `來源.zip` 還原成測試庫，`claude -p "hi" --plugin-dir <worktree> --debug-file <檔> --setting-sources project,local`（預設權限）；grep debug 檔的 hooks 來源與開場段 | `測試-56\庫\` |
| 5 | 空 `CODEX_HOME`＝`測試-56\codex-home\`；`codex plugin marketplace add <worktree>`、`codex plugin add`，`codex app-server` 送 `hooks/list`，數 key | 不登入；需登入就停下回報。不碰 `~\.codex` |
| 6、7、8、9、11 | 對應的測試案例在第 1 條的跑法裡，另外點名確認存在且過（6：`test_scripts_cards_dispatch.py` 兩條；7、11：`test_codex_adapter.py` 的 `Consent.test_codex_turn_marks_session`、`Config.test_codex_manifest_version_matches`，照實作疑義 2；8：`--done` 四種；9：`AGENTS.md` 隱藏、`.codex`＝Z7） | 7 照實作疑義 1 讀成 `codex: true` |
| 10 | `test_skill_ingest.py` 上限測試，另外直接算本文字數 | |
| 13 | `release.py build` 到 `測試-56\out\`，列 zip 內容 | 輸出夾不在 `#` 路徑底下（否則會被驗收 16 擋） |
| 14 | 暫改 worktree 外的複本（不改 worktree）讓兩個 version 不同跑 `build` | 用 `git worktree`／複本，不動實作檔 |
| 15、16 | 讀 `test_tools_release.py` 新測試覆蓋到哪些；另在 `測試-56\` 建 bare repo＋clone、假 `gh`（PATH 前置的 stub，記錄呼叫），實跑 publish 成功、中途失敗重跑、force push 檢查（bare repo 裝 `pre-receive`／比對 reflog）；16 用含 `#` 的路徑跑 build／publish 看結束碼 2、訊息、假 gh 呼叫數 0 | 絕不碰真的遠端 |
| 17 | 第 15 條的假公開 repo `codex` 分支，空 `CODEX_HOME` 跑 `marketplace add <假 repo> --ref codex`、`plugin add`，`hooks/list` 同 5 | 假 repo 在上面那個沒有 `#` 的資料夾 |
| security-review | `claude -p` Sonnet 審 diff（`hooks/guard.py`、`_codex.py`、`kb/guard.py` 保留區、`skeleton`／`init` 隱藏清單、`release.py` pathspec 與 `#`），記花費 | |
| plugin-dev | 先讀 `plugin-dev:hook-development` 審 `hooks/codex.json`、`hooks.json` 未變、hook 程式；收尾跑 agent `plugin-dev:plugin-validator` 對整個 repo | |

開跑前已注意到、要驗的點：
- 改動檔有 `scripts/kb/_lib/turn.py`（spec「可以動」沒列；實作疑義 1 用 `MARK_FLAGS` 帶出來的），確認只加 `codex` 旗標。
- `skeleton/AGENTS.md` 只有 11 行；spec 第 9 條說「從 main 的 `skeleton/CLAUDE.md` 重做，只換一段」，要比對兩份差多少。
- 驗收 17 的 `#` 路徑問題：主管改位置解決。
