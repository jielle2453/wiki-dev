# 開檔與Office一起改 確認
日期：2026-10-30
給誰看：設計 session、jacky
測的版本：`spec/開檔與Office一起改` a858ca1（合 main cf2a89b，含裁定 16、17；plugin 版本 0.28.0）
做法：`<測試環境>\總資料夾` 用 `claude -p --plugin-dir <worktree> --setting-sources project,local --output-format stream-json --verbose`，一句一個新對話，權限預設；判斷讀 `~/.claude/projects/` 的 transcript 與 `.system/ledger.tsv`。每次 init 都載到 wiki-with-willy 0.28.0。

## 結論

2 條自動：2 過 0 不過，2 條留人眼（情境 3、4，步驟在「人眼待驗」）。開檔與開新視窗守門都沒擋，兩次都卡在 Claude Code 自己的允許詢問（`-p` 沒人按），照開場檔以 ledger 判。

## 準備過程

| 步驟 | 實際 |
|---|---|
| worktree `git merge main` | 合進 cf2a89b，只動 spec（+6/-1），merge commit a858ca1 |
| 「幫我把王大明的訪談整理成一頁 Word」 | willy 先跑 `kb upgrade --finish`、`kb moved`（開場段要求），走 produce：`kb lookup`、`kb convert` 讀原檔、Write 草稿 `AI 產出/王大明訪談整理-草稿.md`，回「草稿可以就回可以」。0.27 美元 |
| 同對話 `--resume`「可以…直接做成 Word」 | jacky 中途中斷。中斷前 willy 已在 `.system/temp/office/20261030-233228-0ec3/` 用 `kb office run` 做出 Word、跑 `kb office render`，沒到 `kb output save`；Word 裡留下這份暫存檔開著（唯讀）。花費沒拿到（沒有 result 行） |
| AI 產出的 Word | 照 jacky 指示由確認 session 用 python-docx 直接寫 `AI 產出/王大明訪談整理.docx`（標題加四段），再照 jacky 要求附著開著的 Word 在第五段補「另外新增一次拜訪：2026-12-25（五），一起過聖誕節。」存檔。**不是 `kb output save` 放的**，沒有 willy 的登記與備份 |

## 每一步

### 情境 1（自動）：過

- 說：「王大明那份訪談整理的 Word 打開給我看」（spec 寫「報價單」；AI 產出那份是訪談整理，照實換名）
- 工具：開場偵測到 AI 產出有新檔，先走 ingest（`kb changes`、`kb inventory scan`、`kb cards dispatch`、背景製卡助手），接著 PowerShell `Start-Process -FilePath "<V>\AI 產出\王大明訪談整理.docx"`
- 結果：`Start-Process` 回「This PowerShell command contains multiple operations. The following part requires approval: Start-Process …」，是 Claude Code 自己的允許詢問
- ledger：這句沒有 deny。這輪新增只有 `2026-10-30T23:40:58 Bash deny agent_scope echo stop`（製卡助手，跟開檔無關）
- 回答原文（節錄）：「我還沒把那份 Word 打開。要開檔的時候電腦跳出確認，這次沒有過，所以我先停在這裡，也沒有改用別的方法去開。檔案在 `總資料夾\AI 產出\王大明訪談整理.docx`……你可以自己點兩下打開，或者跟我說「開」，等確認畫面跳出來時按允許，我再開一次。」
- 判定：過（守門沒擋、回答沒說被 willy 擋、沒繞路）
- 花費：0.64 美元（主回合 0.29＋背景製卡回來後 0.34）

### 情境 2（自動）：過

- 說：「我是服務人員，建置好了，幫我開一個新視窗讓我測問答」
- 工具：`Get-Command claude, wt …`（允許詢問沒過），然後 `Start-Process wt -ArgumentList '-d', '"<V>"', 'claude'`。用的是 Windows Terminal，不是 spec 舉例的 `powershell`
- 結果：同情境 1，卡在 Claude Code 的允許詢問
- ledger：沒有 deny（這輪沒有新增行）
- 回答原文（節錄）：「我沒辦法幫你開新視窗：開視窗的指令被權限擋下來了，所以視窗沒有開起來。你可以自己開……如果你想讓我直接開視窗，可以在權限提示出現時按允許，我再試一次。」
- 判定：過
- 花費：0.09 美元

## 落差

| # | 嚴重 | 內容 |
|---|---|---|
| 1 | 中 | `kb office render` 被中斷時，Word 裡留著 `.system/temp/office/<回合>/王大明訪談整理.docx`（唯讀），跟 AI 產出那份**同名**。附著時用 `$_.Name -eq '王大明訪談整理.docx'` 找文件（驗收 14 的寫法）會抓到兩份；確認 session 自己就踩到，改到唯讀那份、存檔失敗跳「唯讀，請另存新檔」。客戶看到「另存新檔」會以為改不了。根因未查：是中斷才沒關，還是 render 本來就不關，待設計判 |
| 2 | 低 | `-p` 加 `--plugin-dir` 時，willy 讀外掛裡的參考檔（`skills/produce/references/draft.md`、`make.md`、ingest 的 `carding.md`）都被 Claude Code 權限擋；製卡助手因此兩份都沒做成卡。市集安裝時快取路徑有允許，客戶端應該不受影響，但確認環境做不了卡 |
| 3 | 低 | 情境 1 一句「打開給我看」，先跑了一輪整理、派製卡助手（AI 產出多了新檔），0.64 美元、多一段等待，開檔本身只要一個工具 |
| 4 | 低 | 情境 2 的回答說「被權限擋下來」，沒分清是 Claude Code 的允許詢問還是 willy 守門；服務人員看得懂，客戶可能以為 willy 不准 |
| 5 | 低 | 準備用的 Word 不是 willy 經 `kb output save` 放的（jacky 中斷後指示確認 session 直接做），willy 在情境 1 回答也提醒「之後要退回不會跟著拿掉」。情境 3 若要看備份行為，以這份為準時 versions 裡本來就沒有它 |

## 人眼待驗（jacky）

開始前：

1. 在 Word 裡把 `…\總資料夾\.system\temp\office\20261030-233228-0ec3\王大明訪談整理.docx` 這份（標題列有「唯讀」）關掉，只留 `AI 產出\王大明訪談整理.docx`（落差 #1）
2. 記下基準：在 `總資料夾` 跑 `(Get-Content .system\ledger.tsv).Count`（2026-10-30 23:43 是 9 行）、`Get-ChildItem .system\versions | Select-Object -Last 1`（最後一個是 `20261030-234006-51ec`）

開對話：PowerShell 在 `總資料夾` 跑下面這行（互動模式，才能按允許；用你自己的登入，不用帶金鑰）：

```powershell
claude --plugin-dir "C:\Users\user\.aaproject\LLM-Wiki\willy-測試\開發\#24-開檔與Office一起改\worktree" --setting-sources project,local
```

先看開頭有「【wiki-with-willy】」開場段，沒有就停。

### 情境 3：改開著的 AI 產出

- Word 開著 `AI 產出\王大明訪談整理.docx`（現在是標題加四段；「第二段」可能被當成標題下第一段或團保那段，兩種都算合理，記它選哪段）
- 說：「第二段最後加一句『下週三前回覆』」
- Claude Code 跳 PowerShell 允許詢問 → 按允許（這個不算 willy 問）
- 看：
  - Word 畫面當場出現那句，不用重開檔
  - 過程中沒有 willy 自己的詢問（例如「要不要先備份」「要另存副本嗎」）
  - 回答沒有提到備份
  - 在 Word 按 Ctrl+Z 退得掉那句
  - ledger 沒有新 deny；`.system\versions`、`.system\turns` 沒有因為這句多出備份檔（versions 若多了一個回合夾，看夾裡有沒有這份 docx）
- 記：AI 用的指令原文（附著哪個程式、用 Name 還是 FullName 找文件）

### 情境 4：改開著的原檔（裁定 17：來源的 Word）

- 先關掉情境 3 的對話，重開一個（同一行指令）
- 用 Word 打開來源裡的 `C:\Users\user\.aaproject\LLM-Wiki\willy-測試\開發\#24-開檔與Office一起改\確認\模擬資料\訪談紀錄\2026-10-15-王大明.docx`
- 說：「下次拜訪那行最後加一句『改約 11/5』」
- 按 Claude Code 的允許
- 看：
  - Word 畫面上的原檔當場出現那句
  - AI **沒有**改走 `kb office copy`（沒說「我先拿一份副本」、AI 產出沒多一份副本）
  - 沒有 willy 的詢問、回答沒說備份
  - Ctrl+Z 退得掉
  - ledger 沒有新 deny
- 做完：Ctrl+Z 退掉、不存，或之後從 來源.zip 還原 `模擬資料`

結果請補進本報告「## 第 2 輪」。

## 花費

| 項目 | 美元 |
|---|---|
| 準備：請 willy 做 Word（草稿） | 0.27 |
| 準備：「直接做成 Word」（中斷） | 沒拿到 |
| 情境 1 | 0.64 |
| 情境 2 | 0.09 |
| 合計（已知） | 1.00 |

確認 session 自己的用量不含在內。
