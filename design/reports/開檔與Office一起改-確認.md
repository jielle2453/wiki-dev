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

## 第 2 輪（補驗：開 ingest 過的原檔，jacky 要求，spec 確認情境外）

- 說：「王大明 10/15 那份訪談紀錄的原檔打開給我看」
- 工具：先走 ingest（AI 產出那份 Word 又派製卡助手，同落差 #2 沒做成）；`Grep` 檔案索引、`Read` 檔案卡；PowerShell `$p = "<RAW>\訪談紀錄\2026-10-15-王大明.docx"; if (Test-Path -LiteralPath $p) { Start-Process -FilePath $p … }` → willy deny `unparsed`（「看不出這個指令會寫到哪……不要用 $(…)、反引號或變數」）；改成 `Start-Process -FilePath "<RAW>\訪談紀錄\2026-10-15-王大明.docx"` → 守門沒擋，卡在 Claude Code 的允許詢問
- ledger：`2026-10-30T23:47:58 PowerShell deny unparsed $p = …`（變數那條，照驗收 11 該擋）；完整路徑那條沒有 deny（改前是 Z9 `readonly_source`）
- 回答原文（節錄）：「我想用 Word 幫你打開王大明 10/15 的訪談紀錄原檔，但這個動作需要你同意，這次沒有打開。你可以自己點這個連結開檔……如果你要我直接幫你開檔，請說「可以」，我再開一次。」
- 判定：過
- 花費：0.68 美元（主回合 0.30＋背景製卡回來後 0.38）

| # | 嚴重 | 內容 |
|---|---|---|
| 6 | 低 | AI 開檔第一手寫成變數加 `Test-Path`，被 `unparsed` 擋後照守門提示改寫完整路徑再跑（照提示改寫，不算繞路）；每次開檔多一輪。可考慮 produce／answer 提示「開檔把完整路徑直接寫在 Start-Process 後面」 |
| 7 | 低 | spec 外：回答又問「原檔寫星期三、照日曆是星期四，哪個對」，但 2026-10-26 已有口述記錄說那是筆誤（`kb lookup` 列得到），R-02 該兩邊並陳而不是再問 |

合計花費（已知）更新為 1.68 美元。

## 第 3 輪（情境 3、4，jacky 要確認 session 代跑）

做法變動：`-p` 沒人按允許，這輪加 `--allowedTools "PowerShell"`（只免 Claude Code 對 PowerShell 的允許詢問；willy 的 PreToolUse 守門照跑，權限模式仍是預設，不是 auto 或 skip）。「畫面當場變」改用 COM 讀開著的文件內容驗。開跑前關掉落差 #1 那份暫存唯讀檔，Word 開著 `AI 產出\王大明訪談整理.docx`（標題＋五段）與 `<RAW>\訪談紀錄\2026-10-15-王大明.docx`（8 段）。基準：ledger 10 行、versions 24 夾。

### 情境 3：不過

- 說：「我 Word 開著王大明訪談整理那份，第二段最後加一句『下週三前回覆』」
- 工具：produce skill；`kb office check`、`kb lookup`、`Grep`、`Glob`、PowerShell `Get-ChildItem -Force`（看到 `~$大明訪談整理.docx`）；想 Grep `skills/produce` 找「開著」的做法被權限擋（同落差 #2）。沒有附著、沒有改檔
- ledger：沒有新行；versions 沒有為這句新增
- 回答原文（節錄）：「還沒改。這份檔現在正開在 Word 裡，我先停下來……檔被 Word 鎖著，程式可能存不進去，存進去了也做不了備份。麻煩你在 Word 按「儲存」，然後把這份檔關掉，再跟我說一聲。我會在第二段最後加上「下週三前回覆」，用修訂標記……這一步之後說「退回」可以退。」
- Word 內容：沒變
- 判定：不過（沒附著改、要她關 Word、提到備份）
- 花費：0.16 美元

### 情境 4：不過

- 說：「我 Word 開著王大明 10/15 那份訪談紀錄，下次拜訪那行最後加一句『改約 11/5』」
- 工具：`kb office copy` 原檔 → `kb office unpack` → Edit `document.xml` 加 `<w:ins>` 修訂 → `kb office pack --to … --like …` → `kb output save … --to "AI 產出/客戶/2026-10-15-王大明-改約.docx" --from <原檔>`
- ledger：沒有新行；versions 多 `20261030-235539-189e`（`kb output save` 的備份）
- 回答原文（節錄）：「已經加好了，不過是加在另一份新檔，**你 Word 裡開著的那份沒有動**。客戶的原檔我不直接改，所以先複製一份，在複製的那份加字。」
- Word 內容：原檔第 7 段不變、`Saved=True`、最後修改 23:15:01（測前）
- 判定：不過（正是情境要排除的「改走 `kb office copy`」）
- 花費：0.28 美元

| # | 嚴重 | 內容 |
|---|---|---|
| 8 | 高 | 情境 3、4 不過的根因在 spec：D-515 只鎖守門（不擋、不問、不備份），但 skills 沒有任何一處教 AI「Word／Excel 開著時附著改」；反而 R-01（Word、Excel 用 `kb output save`）、produce（改原檔一律 `kb office copy`、改 Word 用修訂）、make.md（「檔案被別的程式開著」請她關掉）都把 AI 導向另存或請她關檔。spec 把 `skills/`、`rules/` 列為不可以動，所以這題做完 AI 也不會走附著。守門端沒問題（兩句 ledger 都沒有 deny） |
| 9 | 低 | 情境 3 的回答問「下週三是指 11/4 吧」，她說的就是「下週三前回覆」字面，多問一次 |

合計花費（已知）更新為 2.12 美元。

結論更新：4 條情境，自動 2 過；情境 3、4 由確認 session 代跑，2 條不過（#8，spec 缺 skill 端）。

## 第 4 輪（只重跑情境 3、4；實作 11b72ca，worktree 合 main db93083 → 79e4043）

做法同第 3 輪（`-p` 加 `--allowedTools "PowerShell"`、COM 讀開著的文件）。開跑前 Word 已關，用 `Start-Process` 重開兩份：`AI 產出\王大明訪談整理.docx`（31 段，含 jacky 要的「重點整理」表）、`<RAW>\訪談紀錄\2026-10-15-王大明.docx`（8 段）；沒有唯讀暫存檔。基準：ledger 10 行、versions 25 夾、AI 產出 3 檔。開場段報「已升到 0.29.0」（合 main 帶進的版號）。

### 情境 3：不過

- 說：「我 Word 開著王大明訪談整理那份，第二段最後加一句『下週三前回覆』」
- 工具：produce；Read `make.md` 兩次被權限擋（落差 #2）；`kb office check`、`kb lookup "王大明 訪談整理"`（「沒有登記這個名稱」）、`kb lookup 王大明`、`kb office copy --help`、`kb asks`。沒找 AI 產出、沒附著、沒改檔
- ledger：沒有新行；versions 沒有為這句新增
- 回答原文（節錄）：「我還沒加……知識庫裡沒有叫「王大明訪談整理」的檔。最接近的是「王大明第二次訪談紀錄」……**我改不到你 Word 裡開著的那份。你的原檔我只能讀、不能改。**我能做的是拿一份副本……存成新的一份放在「AI 產出」。」（沒提備份）
- Word 內容：沒變
- 判定：不過
- 花費：0.20 美元

### 情境 4：不過

- 說：「我 Word 開著王大明 10/15 那份訪談紀錄，下次拜訪那行最後加一句『改約 11/5』」
- 工具：先派製卡助手（又因落差 #2 沒做成）；`kb office copy "file://模擬資料/訪談紀錄/2026-10-15-王大明.docx"` → unpack → Edit `document.xml`（這次直接改字，沒用修訂）→ `kb office pack --to … --like …` → `kb output save … --to "AI 產出/客戶/2026-10-15-王大明-改約11-5.docx" --from f-322dfdd1`
- ledger：沒有新行；versions 多 `20261031-001945-12b5`；AI 產出多 `客戶/2026-10-15-王大明-改約11-5.docx`
- 回答原文（節錄）：「原檔不能直接改，所以我先複製一份正在改……你 Word 裡開著的那份我沒改，我另存了一份改好的……**為什麼另存**：你的原檔我只能讀，不能改。」
- Word 內容：原檔第 7 段不變、`Saved=True`、最後修改 2026-10-30 23:15:01（測前）
- 判定：不過（有 `kb office copy`、AI 產出多副本）
- 花費：0.63 美元

| # | 嚴重 | 內容 |
|---|---|---|
| 10 | 高 | 11b72ca 只**刪**句子，沒有**補**「開著就附著改」的正面做法，剩下的字照樣把 AI 帶去另存：知識庫骨架 `CLAUDE.md`「客戶的原始檔案在外面……**只讀**」（每個對話都載入）；R-01「Word、Excel 這類檔用 kb output save 放進去」；produce「成品一律 `kb output save`……不用指令直接寫 AI 產出」；make.md「改她原本的檔」一節仍是 unpack → pack → 放進 AI 產出，render 錯誤句仍寫「原檔先 `kb office copy`」。兩句回答都直接講「你的原檔我只能讀、不能改」。要過得在 rules 或 produce 寫明：她說 Word／Excel 開著（或 `~$` 鎖檔在）→ 用 `GetActiveObject` 附著那份、用完整路徑比對、直接改、`Save()`，不拿副本；骨架 CLAUDE.md 的「只讀」也要對齊 |
| 11 | 中 | 情境 3 找不到 AI 產出那份：`kb lookup` 只查卡，AI 產出的 Word 因落差 #2 沒做成卡；這輪 AI 沒像第 3 輪那樣 Glob `AI 產出`。部分是確認環境造成，但客戶端剛做好、還沒整理的成品也會碰到 |
| 12 | 低 | 情境 4 這輪改字沒用修訂標記（make.md 讀不到，第 3 輪有用）；落差 #2 讓 make.md 的指引在 `-p` 確認裡一直讀不到，結果不穩 |

合計花費（已知）更新為 2.95 美元。

結論更新：情境 1、2 過；情境 3、4 第 4 輪仍不過（#10）。

## 第 5 輪（只重跑情境 3、4；實作 b898e99，worktree 合 main 5ae1d26 → 1d3ced3）

準備：
- 總資料夾跑 `python "<worktree>/scripts/kb.py" upgrade skeleton CLAUDE.md --replace`（jacky 同意後跑）→ 輸出「好了，CLAUDE.md 換成新版了；你改的那份備在這一回合裡，說「退回」就回來。」exit 0；第 3 行換成裁定 25 那段（「……她開著的 Word、Excel、PowerPoint 要改（她說開著，或看到 ~$ 鎖檔），用 PowerShell 的 GetActiveObject 附著到開著的那份、用完整路徑（FullName）比對、直接改，文件原本沒有沒存的編輯（Saved 是 True）才替她存檔……不拿副本、不開修訂……」）；versions 多 `20261031-005427-0000`
- Word 開著 `AI 產出\王大明訪談整理.docx`（31 段）與 `<RAW>\訪談紀錄\2026-10-15-王大明.docx`（8 段），都 `Saved=True`，沒有唯讀暫存檔。基準：ledger 10 行、versions 27 夾、AI 產出 4 檔
- 做法同第 3、4 輪（`--allowedTools "PowerShell"`、COM 讀開著的文件）

### 情境 3a（Saved=True）：不過，守門擋

- 說：「我 Word 開著王大明訪談整理那份，第二段最後加一句『下週三前回覆』」
- 工具：PowerShell 附著列文件（過）；接著照骨架寫 `foreach ($x in $w.Documents) { if ($x.FullName -eq '<V>\AI 產出\王大明訪談整理.docx') { $d = $x } }` 再列段落 → **willy deny**
- ledger：`2026-10-31T00:55:28 PowerShell deny Z3 output_shell $w = [Runtime.InteropServices.Marshal]::GetActiveObject('Word.Application') $d = $null foreach ($x in $w.Documents) { if …`
- 回答原文（節錄）：「那句「下週三前回覆」我還沒加進去，你的 Word 檔沒有任何改動……我要附著上去改的時候，系統擋了下來，理由是 AI 產出的檔要經程式放進來，不能直接在開著的 Word 裡改。被擋我就停了，沒有換別的方法。」
- Word：沒變。判定：不過（行為照骨架，擋的是守門）
- 花費：0.38 美元

### 情境 3b（Saved=False）：沒跑

AI 產出那份在 3a 被 `output_shell` 擋，3b 必然同一條擋下，測不到「不替她存」；改在情境 4 的原檔上驗（4b）。

### 情境 4（Saved=True）：過

- 說：「我 Word 開著王大明 10/15 那份訪談紀錄，下次拜訪那行最後加一句『改約 11/5』」
- 工具：PowerShell `GetActiveObject('Word.Application')`、`$x.FullName -eq '<RAW>\訪談紀錄\2026-10-15-王大明.docx'` 找文件、`$wasSaved = $d.Saved`、第 7 段尾 `InsertAfter('，改約 11/5')`、`if ($wasSaved) { $d.Save() }`。沒有 `kb office copy`、unpack、pack、output save
- ledger：沒有新 deny；versions 多 `20261031-005704-3e98`，裡面只有 `.system/batches.json`、`.system/pending.json`、`系統/待處理.md`（整理用），沒有這份 docx
- Word：第 7 段「下次拜訪：2026-10-29（三）晚上，帶建議書，太太會一起來，改約 11/5」、`Saved=True`、修訂 0、檔案修改時間 2026-10-31 00:57:55；`Undo()` 退得掉、`Redo()` 回來
- AI 產出：仍 4 檔（沒多副本）；`.system/temp/office` 沒新增夾
- 回答原文（節錄）：「改好了，也替你存檔了……我改的是你 Word 開著的那份，沒有另外存副本，也沒有開修訂。檔案原本沒有沒存的編輯，所以我直接替你存了。要退回的話，在 Word 按復原就好。」（沒提備份）
- 判定：過
- 花費：0.32 美元

### 情境 4b（Saved=False，裁定 28）：過

- 第一次準備失敗不算：確認 session 用 `$d.Range($p.End-1,$p.End-1)` 插字，PowerShell 報「Argument: '1' should be a System.Management.Automation.PSReference」，字沒插進去、文件仍 `Saved=True`；AI 那次（「要準備那行最後加一句『先寄條款』」）照 Saved=True 替她存了，行為對但沒測到 4b。0.76 美元
- 重做準備：第 4 段尾插「（測）」不存 → `Saved=False`
- 說：「我 Word 開著王大明 10/15 那份訪談紀錄，客戶反應那行最後加一句『太太也同意』」
- 工具：附著列文件（看到 `Saved=False`）→ FullName 比對 → 第 6 段尾 `InsertAfter('太太也同意。')`（第一次 `Range(int,int)` 同樣報錯，改用 `Range.Duplicate` + `MoveEnd`）。沒有 `Save()`、沒有 office copy
- ledger：沒有新 deny（新增 2 行都是製卡助手 `agent_scope`）
- Word：第 6 段多「太太也同意。」，第 4 段「（測）」還在，`Saved=False`，檔案修改時間沒變（01:00:17）；`Undo()` 兩次先退 AI 那句、再退「（測）」，回到 `Saved=True`
- 回答原文（節錄）：「我已經在你開著的那份裡加好「太太也同意」了，但還沒存檔，要麻煩你自己在 Word 按一下儲存……這份檔在我動手前就有還沒存的修改，我不想把那些修改一起替你存掉……想退回：在 Word 按「復原」（Ctrl+Z）就可以。」
- 判定：過
- 花費：0.70 美元

| # | 嚴重 | 內容 |
|---|---|---|
| 13 | 高 | 守門洞：PowerShell 附著後用 `$x.FullName -eq '<V>\AI 產出\…docx'` 比對（不寫檔，只拿路徑比）被 deny Z3 `output_shell`。骨架第 3 行（裁定 25）正是叫 AI 用 FullName 比對，所以開著的 AI 產出檔一律附著不了；原檔路徑同寫法 pass（情境 4）。驗收 14 只驗了 AI 產出用 `$_.Name -eq 'x.docx'`、原檔用 FullName、Bash python 用 FullName，PowerShell＋FullName＋AI 產出這一格沒驗到。推測根因是 `_touches_output` 第 (2) 條：這一段不是只讀動詞、參數裡有 AI 產出路徑就擋（未用 `kb guard decide` 實測） |
| 14 | 低 | `Range(<int>,<int>)` 在 PowerShell 的 COM 會報 `PSReference` 錯，AI 兩次都先撞一次再改寫（`MoveEnd` 或 `Duplicate`）；骨架若附一行寫法範例可以省一輪 |
| 15 | 低 | 原檔 `2026-10-15-王大明.docx` 這輪已被 AI 存過兩次（第 7 段「，改約 11/5」、第 8 段「；先寄條款」），磁碟上不是演練原版；scratchpad 有測前備份，要還原請從 來源.zip 或交設計決定 |

合計花費（已知）更新為 5.11 美元。

結論更新：情境 1、2 過；情境 4、4b 過；情境 3 不過（#13 守門把 FullName＋AI 產出當寫），3b 待 #13 修好再跑。
