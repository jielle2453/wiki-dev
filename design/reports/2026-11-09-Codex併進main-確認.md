# Codex併進main 確認報告

日期：2026-11-11
給誰看：設計 session（willy設計二）與使用者。
測的版本：分支 `spec/Codex併進main`，`c4c48824`（開工時 `git merge main`，無衝突，只動 design 文件）；之後設計 session 加的 `3f2cc3a1`（spec 確認裁定）、`af45da2c`（只改 `安裝-Codex.md`）沒動程式，情境 4 照 `af45da2c` 的文件回測。市集安裝用的是同一個 commit 在拋棄 clone（`第二組-56測試\確認\dev`）bump 成 0.37.0、`release.py build` 出的 zip。
做法：照 spec「確認情境」1～4。全部東西在 `C:\Users\user\.aaproject\LLM-Wiki\willy-測試\開發\第二組-56測試\確認\`（下稱 `確認\`）：
- 情境 1：`來源.zip` 還原成 `確認\來源`，worktree 的 `kb init 確認\總資料夾`、`folders add`。`claude -p "<客戶的話>" --plugin-dir <worktree> --add-dir <worktree> --setting-sources project,local --output-format stream-json --verbose`，權限模式預設（init 段 `permissionMode: default`，每段都載到 `wiki-with-willy` 0.36.0 inline）。判斷讀 `~/.claude/projects/` 的 transcript。`--add-dir` 照「記帳-確認」的前例（見 #1）。
- 情境 3：本機目錄市集 `willy-c56`（`確認\mp-c56`），local 範圍裝在 `確認\s3\知識庫`；使用者層 `~\.claude\settings.json` 前後 sha256 相同。
- 情境 2、4：自建假公開 repo `確認\fake-pub.git`，`codex` 分支兩個 commit：0.34.0（`848125cb` 的檔）、0.37.0（上面那份 zip＋`.gitattributes`＋README＝`安裝-Codex.md`，照 publish 的樣子手做）。用暫時的 `GIT_CONFIG_GLOBAL`（`確認\gitcfg-c56`）把 `https://github.com/fake-owner-c56/fake-public-c56.git` 改寫到本機 bare。`CODEX_HOME` 全在 `確認\` 底下，沒碰使用者的 `~\.codex`。測試用知識庫的 `.system/config.json` 把 `update_manifest_url`、`update_rollout_url` 設成空字串，不去查真的公開 repo（情境 1 的 `總資料夾` 沒設，開場背景查新版會讀真的公開清單，只讀）。

## 結論

**Claude 這邊可以過（情境 1、3）；Codex 這邊不能過（情境 2 不過）。** Codex 0.167.1 在這台的測試環境裡，hook 信任了也一個都不跑（#6，高，原因未查實，像是 Codex 端的行為），所以開場段、整理、報價都沒走到；AI 沒開場段就停、不改檔，保護是有效的。情境 4 的升級步驟原本照文件升不上去（#3），文件已補，回測過；信任後開場因 #6 沒驗到。其餘 #1、#2、#4、#5、#7、#8 都是低。

（情境 3 原定桌面版、情境 2／4 原定人眼，jacky 2026-11-11 改成一律終端機，見 spec 確認裁定 2。）

| 情境 | 結果 |
|---|---|
| 1 自動：「整理一下」 | 過（加 `--add-dir` 後）：派 3 批製卡助手、做到 `done`，回答形狀同 main 的 ingest 骨架 |
| 1 自動：「大安陳的報價多少」 | 過：620,000 在前、四份原檔都打開核對、每點有出處 |
| 2 Codex 實機（終端機，0.167.1） | **不過**：hook 已信任，exec 與 TUI 都沒跑 hook、沒有開場段，整理與報價 AI 照 `AGENTS.md` 停下（#6，原因未查實） |
| 3 Claude 從市集 0.34.0 升級（改用終端機） | 過：開場「已換到 0.37.0」、`--finish` 補上隱藏的 `AGENTS.md`，沒因為它問客戶 |
| 4 Codex 從 0.34.0 升級 | 原文件升不上去（#3，高）→ 文件已補（`af45da2c`），照新文件回測：升級步驟過、要求重新信任過；信任後開場沒驗到（#6） |

## 每一步

### 情境 1（自動）

**1-1「整理一下」第一次**（session `adb21432…`，未加 `--add-dir`）
- 開場段有（SessionStart additionalContext 以「【wiki-with-willy】kb 指令：…」開頭）。
- AI：「目前沒有新的變動，但有 42 份檔還沒整理（公司行政、報價與合約等資料夾裡的檔）。整理大約要 5 分鐘，份數比較多，額度會用得比平常多。要現在整理嗎？1. 現在做 2. 之後再說」
- `--resume` 回「1」：`cards dispatch --json` 派 3 批（20、20、2），三批全失敗，AI：「42 份檔這次都沒整理成。原因是製卡助手被權限擋住，讀不到整理用的規則檔…請在下面的輸入框貼上這一行 `/add-dir "…/codex-merge-wt"`」。判定：環境問題（-p 沒人按允許、plugin 夾在知識庫外），見 #1；不判。

**1-2「整理一下」重跑**（新對話 `7dc2751a…`，加 `--add-dir`）
- 這次沒先問就直接派（見 #2），中間照 `say` 回報「做好 6 份了，還有 2 批在背景整理中」「42 份做好了，最後 1 批還在收尾」，`dispatch` 回 `done: true`，跑 `turn note`。
- 最後回答原文（節錄）：「整理完了，這次共處理 42 份檔，其中 39 份做好卡，另外 3 份讀不到。日程新加了兩件：11/15 營業稅（9-10 月）申報繳納期限；11/20 信義王宅預計驗收。讀不到的 3 份：舊合約.doc、舊報價單.doc（舊格式）、合約_加密.pdf（有密碼）…另外有些檔看起來屬於幾種分類（廠商 9、案子 24、業主 2、員工 5）…」
- 「同 main」：沒有另外在 main 跑一次（再跑一次約 3 美元）。改看 `git diff main HEAD -- skills/ agents/`：ingest 的 SKILL.md、carding.md、commands.md 只有措辭與「沒有派子代理的工具照 commands.md 自己做」這類 Codex 分岔，Claude 這條的步驟（拿計畫→dispatch→每次通知再 dispatch→`done`→重跑 todo→回答）沒變；實際回答也照這個順序。判定：過。
- 花費：1-1 兩段 0.37＋1.09 美元，1-2 2.98 美元。

**1-3「大安陳的報價多少」**（新對話 `fcde7fc4…`）
- 走 answer skill：`lookup`、`find`，讀 4 張卡，再 `convert` 四份原檔核對。
- 回答原文（節錄）：「大安陳宅最新的報價是 **NT$ 620,000**，這是 2026-08-24 的第二版報價單〔大安陳宅報價單第二版〕。四份原檔我都逐份打開對過，數字跟卡上寫的一樣。」附 v1／v2 表（590,000／620,000）、報價表 620,000、合約 651,000 含稅，「620,000 再加 5% 稅剛好是 651,000…這是我算出來的〔我算的〕」。
- 正解（直接讀原檔）：v1 590,000（2026-08-10）、v2 620,000（2026-08-24）、`報價.xlsx` 620,000。判定：過。
- 回答末尾多一句「自動檢查最近好像沒在跑」，是誤報，見 #4。花費 0.39 美元。

### 情境 2（人眼，Codex 實機）

- 已備：`CODEX_HOME=確認\codex-home-s2`（`config.toml` 有 `[windows] sandbox = "unelevated"`），從假公開 repo `marketplace add … --ref codex`、`plugin add wiki-with-willy@wiki-with-willy` 裝到 0.37.0；知識庫 `確認\s2\知識庫`（用裝好那份的 `kb init`，有隱藏的 `AGENTS.md`），來源 44 份。
- `hooks/list`（cwds＝`s2\知識庫`）：6 個 key，全是 `wiki-with-willy@wiki-with-willy:hooks/codex.json:{pre_tool_use,post_tool_use,session_start,session_end,user_prompt_submit,stop}:0:0`，warnings、errors 空。
- `codex login status`：Not logged in。照開場停下回報；jacky 准、由 jacky 自己用 `!` 把 `~\.codex\auth.json` 複製到 `codex-home-s2`、`codex-home-s4`（我複製被 auto mode 判斷器擋下，沒繞）。
- 測試中途這台 Codex 自己 npm 更新成 **0.167.1**（09:03，spec 寫 0.167.0）；以下 Codex 結果都是 0.167.1。
- TUI 要加 `--no-daemon`：測試 `CODEX_HOME` 路徑太長，daemon 的 socket 報「path must be shorter than SUN_LEN」起不來（客戶用預設 `~\.codex` 不會）。
- 信任：jacky 在 TUI `/hooks` 信任後，`hooks/list` 6 個 `hooks/codex.json` 全 `trusted`；`config.toml` 有 6 條 `trusted_hash`＋`trusted_content_hash`。
- 2-1 `codex exec --skip-git-repo-check --json "整理一下"`（我跑）：回答「Python 正常，但這個對話沒有出現「【wiki-with-willy】」啟動訊息，目前還不能整理檔案。請到 Codex 的「設定 > Hooks」（或輸入 `/hooks`），將 wiki-with-willy 的 Hooks 都設為信任，再開一個新對話說「整理一下」…」。rollout 裡沒有任何 hook 事件；沒改檔。
- 2-2 診斷：Codex log 有「ERROR codex_app_server Project-local config, hooks, and exec policies are disabled in the following folders until the project is trusted, but skills still load. 1. C:\Users\user\.codex」。知識庫不在 git 裡，Codex 把含 `.codex` 的 `C:\Users\user` 當專案根。在 `確認\s2` 暫放空 `.git`、用 `-c` 只那一次信任 `s2` 再問「有沒有開場段」→「沒有」（`.git` 已刪）。想加 `--dangerously-bypass-hook-trust` 做對照被判斷器擋，沒做。
- 2-3 TUI（jacky 親打，`Codex 測試 s2 新`，0.167.1；三句一次貼成一則）：那時 `config.toml` 已有 6 條信任，**也有** jacky 回答資料夾信任寫進的 `[projects.'c:\users\user'] trust_level = "trusted"`（09:40:43，對話 09:41:43 開始），市集仍是假 repo 的 0.37.0。回答：「我沒有看到「【wiki-with-willy】」開頭的開場段。我先確認 Python 是否正常；依這個知識庫的規則，開場段恢復前不能整理或修改檔案。」→「Python 的檢查目前尚未回傳結果。整理尚未執行，大安陳的報價也尚未查證，我不會先猜金額。」rollout 沒有 hook 事件。
- 判定：**不過**（三件事都沒做到：開場段沒出現，整理、報價 AI 照 `AGENTS.md` 停下）。原因見 #6：信任了、專案也信任了，hook 還是一個都沒跑；原因未查實。保護行為（沒開場段就不改檔、照實講）是對的。
- 第 1 次 TUI 起動時 jacky 回答信任資料夾，`[projects.'c:\users\user']` 寫進測試設定；我兩次照主管指示從測試設定拿掉（`~\.codex` 沒碰）。見 #7。

### 情境 3（Claude 從市集 0.34.0 升級；原定桌面版，改終端機）

- 市集 `willy-c56` 先放 `v0.34.0` 的檔，在 `s3\知識庫` 跑 `marketplace add … --scope local`、`install wiki-with-willy@willy-c56 --scope local`；用 0.34.0 的 `kb init` 建庫（沒有 `AGENTS.md`）。
- 0.34.0 跑一句當升級前基準（`claude -p "你好，你是哪一版？"`）：init 段 `wiki-with-willy 0.34.0 @willy-c56`，開場段正常。花費 0.13 美元。
- 換成 0.37.0 快照：`marketplace update willy-c56`、`plugin update wiki-with-willy@willy-c56 --scope local` →「updated from 0.34.0 to 0.37.0 for scope local」。使用者層 settings.json 沒變。
- 真的客戶是 `kb upgrade` 從公開 repo 下載換版；這裡不碰真遠端，用 CLI update 代替，`kb upgrade --finish` 這段沒走到（見「沒確認到的」）。
- 主管 2026-11-11 轉 jacky 裁示：測試一律用終端機，情境 3 改由我在終端機驗，不用桌面版。
- 升級後第一個新對話：`claude -p "你好" --permission-mode default --setting-sources project,local`（session `07e22000…`），init 段 `wiki-with-willy 0.37.0 @willy-c56`。
  - 開場段（transcript 的 SessionStart hook_success）：「【wiki-with-willy】kb 指令：python "…/mp-c56/wiki-with-willy/scripts/kb.py" <子命令>／已換到 0.37.0：先跑 kb upgrade --finish 再做別的。」接著核心規則全文。
  - AI 只跑一個工具 `kb upgrade --finish`，原文：「已升到 0.37.0：確認用（拋棄 clone，不發行）。／轉成新格式：.system/profile.json／補上骨架：AGENTS.md／骨架換成新版：.gitignore」
  - 回答原文：「你好！新版已經裝好，可以用了。今天想做什麼？你可以問案子現在怎樣、找某份檔案，也可以叫我記事情、做文件。」沒問任何跟 `AGENTS.md`、骨架、升級有關的問題。
  - 磁碟：`s3\知識庫\AGENTS.md` 出現，`attrib` 是 `A H`（隱藏）；`upgrade-history.json` 記 `0.34.0 → 0.37.0 minor`、有升級前快照、`pending` null。
- 判定：過。「給客戶的一句話」AI 沒照念，見 #5。花費 0.16 美元。

### 情境 4（人眼，Codex 從 0.34.0 升級）

- 已備：`CODEX_HOME=確認\codex-home-s4` 從假公開 repo 裝 0.34.0（`hooks/list` 6 個 `hooks/hooks.json` key），知識庫 `確認\s4\知識庫`（0.34.0 的 `kb init`）。jacky 在 TUI 信任舊的 6 個 → `hooks/list` 6 個 `wiki-with-willy@wiki-with-willy-local:hooks/hooks.json:…` `trusted`。
- 照新文件（設計 session 依 #3 補的 `af45da2c`）升級：`plugin remove wiki-with-willy@wiki-with-willy-local`、`marketplace remove wiki-with-willy-local`、`marketplace add <網址> --ref codex`、`plugin add wiki-with-willy@wiki-with-willy`，四步都成功。
  - 第一次：快取 0.37.0 只有 37 個檔（s2 是 322），`hooks/list` 0 個 hook、警告「failed to fingerprint plugin contents: 系統找不到指定的檔案。 (os error 2)」；重裝一次變成 0.35.1，市集複本是**真的公開 repo**（`origin https://github.com/jielle2453/wiki-with-willy.git`、`06df890` Codex 版 0.35.1）。查到：`marketplace remove wiki-with-willy` 回「marketplace `wiki-with-willy` is configured in project (C:\Users\user\.codex/config.toml)」，`codex-home-s4\config.toml` 有 TUI 寫進的 `[projects.'c:\users\user'] trust_level = "trusted"`——Codex 把 jacky 自己的 `~\.codex\config.toml` 當專案設定讀進來，同名市集（真 repo）蓋過測試市集。見 #7。
  - 拿掉那條專案信任後重做：0.37.0、322 個檔、市集是假 repo；`hooks/list` 6 個 `wiki-with-willy@wiki-with-willy:hooks/codex.json:…` 全 `untrusted`、warnings 空。37 個檔那次沒再出現。
- 判定：升級步驟（新文件）**過**；「`/hooks` 要求重新信任」**過**（`hooks/list` 新的 6 個 key 都是 untrusted，舊的 `hooks/hooks.json` 信任不算）。「信任後開場正常」**沒驗到**：jacky 這次沒在 s4 按信任（09:5x `hooks/list` 仍 6 個 untrusted），TUI 對話回「沒有看到開場段…請先在 Codex 打 /hooks…」；而且 s2 已信任也不跑 hook（#6），信任了也看不到。
- 拋棄用的兩個 home 先實測升級指令（結果見 #3）：
  - `codex-home-s4dry`：0.34.0 從 git 網址裝；`codex-home-s4dryL`：0.34.0 從本機夾裝（當年 `848125cb` 的 `安裝-Codex.md` 寫的就是本機夾）。
  - 照新文件 `codex plugin marketplace upgrade wiki-with-willy`：兩個都「Error: marketplace `wiki-with-willy` is not configured as a Git marketplace」。
  - 改用舊名 `marketplace upgrade wiki-with-willy-local`：git 來源「Failed to upgrade marketplace `wiki-with-willy-local`: upgraded marketplace name `wiki-with-willy` does not match configured marketplace `wiki-with-willy-local`」；本機夾來源「not configured as a Git marketplace」。
  - 照新文件重裝 `plugin add wiki-with-willy@wiki-with-willy`：「plugin `wiki-with-willy` was not found in marketplace `wiki-with-willy`」；裝回 `@wiki-with-willy-local` 還是 0.34.0。
  - 繞法：`plugin remove wiki-with-willy@wiki-with-willy-local`、`marketplace remove wiki-with-willy-local`，再照新文件 `marketplace add <網址> --ref codex`、`plugin add wiki-with-willy@wiki-with-willy` → 兩個都裝上 0.37.0，`config.toml` 只剩 `[plugins."wiki-with-willy@wiki-with-willy"]` 一份。

## 落差

| # | 嚴重 | 內容 |
|---|---|---|
| 1 | 低 | 環境（不是這題）：`claude -p --plugin-dir` 沒加 `--add-dir <worktree>` 時，製卡助手讀 plugin 的 references 被權限擋（-p 沒人按允許），三批全失敗；AI 有照實講、沒改檔，還教客戶 `/add-dir`。同「記帳-確認」#12 的做法加 `--add-dir`。市集安裝（plugin 在 `~\.claude\plugins\cache`）會不會也被擋，這邊沒驗 |
| 2 | 低 | spec 以外：同一句「整理一下」、同樣 42 份，第一次先問「要現在整理嗎」，第二次沒問就派；第二次還把一句英文「Client explicitly said 整理, so continue.」當文字輸出（客戶看得到）。ingest skill 兩邊只差措辭，推測 main 一樣，沒在 main 實跑 |
| 3 | 高 | 情境 4：0.34.0 的 Codex 版市集名是 `wiki-with-willy-local`，這版改成 `wiki-with-willy`。照 `安裝-Codex.md` 第三節的升級步驟（`marketplace upgrade wiki-with-willy`＋重裝），git 來源與本機夾來源的 0.34.0 都升不上來，停在 0.34.0；文件沒寫要先移除舊市集。繞法實測可行（上面情境 4）。真的公開 repo 上 0.34.0 時的 codex 分支是哪個名字沒查（不碰真遠端）；`848125cb` 的安裝說明是本機夾裝。**已補文件、回測**：設計 session 照確認裁定 1 補 `安裝-Codex.md`（`af45da2c`，只改文件）；照新文件在 s4 回測，四步都成功、裝上 0.37.0、新 hook 要重新信任（情境 4） |
| 6 | 高 | 情境 2：Codex 0.167.1，hook 已信任（`hooks/list` 6 個 trusted、config 有 `trusted_hash`＋`trusted_content_hash`），`codex exec` 與 TUI 都**一個 hook 都沒跑**，開場段沒出現，整理與報價都沒做。TUI 那次專案根 `C:\Users\user` 也已信任，還是不跑。Codex 端：專案根被判成使用者家目錄時 plugin hook 不跑（未證實）；也可能是 0.167.1 的行為（`安裝-Codex.md` 第五節的實測是 0.167.0、在 jacky 自己的 `~\.codex`）。log 原文：「Project-local config, hooks, and exec policies are disabled in the following folders until the project is trusted, but skills still load. 1. C:\Users\user\.codex」。沒用 `--dangerously-bypass-hook-trust` 對照（判斷器擋）。客戶面：AI 沒開場段就不改檔、照實請客戶去 `/hooks`，保護有效 |
| 7 | 低 | 測試環境：知識庫不在 git 裡，Codex 把含 `.codex` 的 `C:\Users\user` 當專案根；TUI 起動回答「信任資料夾」就把 `[projects.'c:\users\user']` 寫進設定，之後 Codex 把 jacky 自己的 `~\.codex\config.toml` 當專案設定載入，同名市集 `wiki-with-willy`（真 repo）蓋過測試市集，s4 一度裝成 0.35.1（第一次還裝出只有 37 個檔、hook 指紋失敗的殘缺快取）。客戶的 `~\.codex` 就是他自己的設定，不影響客戶；以後在這台用假 repo 測，要先拿掉那條專案信任，或資料夾信任選「不信任」 |
| 8 | 低 | 測試環境：測試用 `CODEX_HOME` 路徑太長，TUI 的 daemon 報「path must be shorter than SUN_LEN」起不來，要加 `--no-daemon`；中途 Codex 自己更新到 0.167.1 |
| 4 | 低 | spec 以外：新建的知識庫，第一個對話開場的背景健檢就記一件「守門好像沒在跑（一直沒有跑的紀錄，最近的對話是 2026-11-10）」（`pending.json` 23:47:16 建）。那時這句的回合已記進日誌、守門還沒跑第一次（`guard-status` 還沒有），所以誤報；後來同一個庫守門有在跑（ledger 23:52 有 deny、`guard-status` 11-11），下一個對話仍把這件講給客戶。`scripts/kb/lint/checks/guard.py` 這支跟 main 一樣，推測 main 也會 |

| 5 | 低 | spec 以外：升級後第一句，`kb upgrade --finish` 印「已升到 0.37.0：<給客戶的一句話>」，AI 只說「新版已經裝好，可以用了」，沒照念那一句（CHANGELOG 開頭寫「`kb upgrade --finish` 唸給客戶」）。這次的一句話是確認用的假句，客戶版會不會照念沒驗 |

## 沒確認到的

- 情境 3 用 `claude plugin update` 代替客戶端的 `kb upgrade`（要真的公開 repo），`kb upgrade` 的下載走不到；`--finish` 有走到。
- 情境 2 的「整理（子代理做完跑 `--done`）」與「報價答對、有核對」：hook 沒跑，AI 停在開場段檢查，沒走到。
- 情境 4 的「信任後開場正常」：s4 沒信任，且 #6 未解。
- 假公開 repo 的 0.37.0 是手做的 codex 分支（zip＋`.gitattributes`＋README），不是 `release.py publish` 推的（publish 測試報告驗收 15 已驗）。

## 花費

`claude -p`（API）：1-1 0.37＋1.09、1-2 2.98、1-3 0.39、情境 3 基準 0.13＋升級後 0.16，共約 5.12 美元（2026-11-11）。Codex 用 jacky 的 ChatGPT 登入：我跑 2 次 `codex exec`（各約 3.6 萬 input tokens），jacky 在 s2、s4 TUI 各一段對話。

## 第 2 輪

日期：2026-11-11。範圍：只補情境 2 的對照（設計 session 懷疑 #6 是測試環境造成：自訂 `CODEX_HOME` 時，家目錄的 `~\.codex` 被當成專案層、要專案信任，連帶 plugin hook 停用）。

做法：把 `確認\s2` 的知識庫與來源複製到家目錄以外、上層沒有 `.codex`、不在 git 裡的 `C:\c56\知識庫`；`CODEX_HOME` 仍用 `codex-home-s2`（6 個 `hooks/codex.json` 已信任，jacky 重新複製 `auth.json`，`Logged in using ChatGPT`）；Codex 0.167.1。`codex exec --skip-git-repo-check --json "你有看到 wiki-with-willy 的開場段嗎"`。

結果：回答「沒有，我目前沒有看到以「【wiki-with-willy】」開頭的開場段，只有你提供的 AGENTS.md 指示。這表示程式可能還沒跑起來；在恢復前，我不會修改、刪除或搬動任何檔案。」rollout（cwd `C:\c56\知識庫`）沒有任何 hook 事件。

判定：對照下 hook 仍不跑，「專案根判成家目錄」這個解釋不成立；情境 2 維持**不過**，#6 不變（原因仍未查實；剩下可能：0.167.1 的 exec／TUI 行為、測試 `CODEX_HOME` 本身的其他差異）。依指示沒有再跑「整理一下」「大安陳的報價多少」。

收尾：`codex-home-s2\auth.json` 測完刪掉。`C:\c56` 留著，要清再說。
