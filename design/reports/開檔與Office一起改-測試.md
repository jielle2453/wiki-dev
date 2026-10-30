# 開檔與Office一起改 — 測試報告

日期：2026-10-30（第一輪）
給誰看：設計 session（決定哪些發現回實作修、哪些記 backlog；結案時填 spec「紀錄」的測試報告欄）。
測的版本：分支 `spec/開檔與Office一起改`，實作 commit `375c805`，併入 main `3597b7f`（裁定 1～8）後的 `b2d018c`。
做法：只執行與讀檔，不改程式。`kb init` 在 `#24-開檔與Office一起改\測試假庫\總資料夾`（下稱 `<V>`）建假知識庫，登記同層的 `來源根`（下稱 `<RAW>`，含 `客戶案件\`、`行政\薪資\`），`kb folders exclude 行政\薪資 --kind hidden`。每條指令丟 `python <worktree>/scripts/kb.py guard decide --tool <PowerShell|Bash> --command … --json`，cwd＝`<V>`；跟 main 對照時用 `git archive main` 解出來的 `scripts/kb.py` 跑同一條。驗收 15、16 用 subprocess 餵 payload 給 `hooks/guard.py`。審查：`/code-review high`（分叉執行，10 條我逐條另外實測）；security-review 照全域規則與開場「不開 subagent」，沒照 skill 分叉子任務，改在主線程對開檔這條路做攻擊面探測（31 條），再照 skill 的門檻（這題新引進、信心 ≥ 8）過濾。

## 結論

**驗收 17 條全過，裁定 1～7 照驗也過；但 code-review 找到 1 個這題新引進的高（#1：開一個夾，同一句另一段遞迴讀同一個夾就跳過憑證掃描，密碼檔內容讀得到）。建議 #1 修完再進確認。** 另外有 1 個新壞的低（#2），以及 5 條 main 本來就有、這題沒修的（#3～#7，其中 #4 高）。

相關測試（spec「相關測試」列＋`grep -l "cmdparse\|kb.guard" tests/*.py` 多找到的 6 個，共 15 檔）序列跑：**485 passed、3070 subtests passed、exit 0**（352 秒）。全套沒跑：照 jacky「只跑相關測試」的規則（willy設計 2026-10-30 更正開場檔）。

## 驗收逐條

「不 deny」＝decision 是 pass 或 allow。實際輸出是 `(decision, zone, reason_code)`。

| # | 判 | 證據 |
|---|---|---|
| 1 | 過 | `Start-Process '<V>\AI 產出\x.docx'`、`-FilePath` 版、`Invoke-Item`、`ii …x.pdf`、`explorer '<V>\AI 產出'`、`Start-Process 'AI 產出\x.xlsx'` 六條都是 `(pass)` |
| 2 | 過 | Bash `cmd //c start "" "<V>/AI 產出/x.docx"`、`start "" …`、`start "<V>/AI 產出/x.docx"`（標題）、`explorer.exe "<V>/AI 產出"` 都是 `(pass)`；PowerShell 的 `cmd /c start "" "…"` 也是 pass |
| 3 | 過 | `總目錄.md`、`系統\工作日誌.md`、`檔案索引\x.md`、`<RAW>\客戶案件\a.docx`、`_extras\筆記.md` 都是 `(pass)` |
| 4 | 過 | PowerShell `Start-Process 'https://example.com'`、`start https://example.com`，Bash `start https://example.com` 都是 `(pass)` |
| 5 | 過 | `-Verb Print`、`-Verb Edit`、`-Wait`、`-WindowStyle Maximized`，加上三個一起帶的版本，都是 `(pass)` |
| 6 | 過 | `Start-Process powershell -ArgumentList '-NoExit','-Command','claude --name 問答測試 --plugin-dir C:\x'` 與加 `-WorkingDirectory '<V>'` 都是 `(pass)` |
| 7 | 過 | `-RedirectStandardOutput '<V>\x.txt'` → `(deny, Z8, protected)`；`-RedirectStandardError '<V>\AI 產出\e.txt'` → `(deny, Z3, output_shell)`；`-RedirectStandardOutput '<RAW>\客戶案件\o.txt'` → `(deny, Z9, readonly_source)` |
| 8 | 過 | `Start-Process powershell -ArgumentList '-Command','Remove-Item ''<V>\系統\x.md'''` 與直接跑 `powershell -Command "Remove-Item '<V>\系統\x.md'"` 兩條都是 `(deny, Z6, system_render)`；`Start-Process cmd -ArgumentList '/c','del "<V>\AI 產出\x.docx"'` → `(deny, Z3, output_shell)` |
| 9 | 過 | `x.bat`、`x.ps1`、`x.docm`（AI 產出）→ `(deny, Z3, run_file)`；`<V>\x.cmd` → `(deny, Z8, run_file)`；`<RAW>\客戶案件\run.exe` → `(deny, Z9, run_file)`；`Invoke-Item …x.lnk` → `(deny, Z3, run_file)`；Bash `cmd //c start "" "<V>/AI 產出/x.bat"` → `(deny, Z3, run_file)`。這些檔都不存在 |
| 10 | 過 | `<RAW>\行政\薪資\s.xlsx` → `(deny, Z10, excluded)`；`<RAW>\客戶案件\密碼.txt` → `(deny, Z9, credential)`；`explorer '<RAW>'` → `(pass)` |
| 11 | 過 | `Start-Process $f`、`… -ArgumentList $a`、`Start-Process (Get-Item x)` 都是 `(deny, '', unparsed)` |
| 12 | 過 | `Start-Process '<V>\AI 產出\x.docx'; Remove-Item '<V>\AI 產出\y.docx'` → `(deny, Z3, output_shell)` |
| 13 | 過 | `$w=[Runtime.InteropServices.Marshal]::GetActiveObject('Word.Application'); $w.Documents.Open('<V>\AI 產出\x.docx')` → `(deny, Z3, output_shell)` |
| 14 | 過 | 四條都是 `(pass)`：附著 Word＋`$_.Name -eq 'x.docx'`＋`InsertAfter`＋`Save()`；附著 Excel＋`$_.FullName -eq '<RAW>\客戶案件\a.xlsx'`＋`Range('A1').Value2`；Bash `python -c "…GetActiveObject('Word.Application')…FullName==r'<V>\AI 產出\x.docx'…InsertAfter('x')"`；附著 PowerPoint 改 `TextFrame.TextRange.Text` |
| 15 | 過 | 先 `turn.start` 開一個回合，再把 14 的第一條餵給 `hooks/guard.py`（主對話，沒有 agent_id）：rc 0、stdout 是空的（沒有 deny）；`.system/turns/` 與 `.system/versions/`（裁定 7）前後比對，沒有多出任何檔 |
| 16 | 過 | 帶 `agent_id`、`agent_type=batches.AGENT`（先 `batches.agent_start`）跑 1 的第一條 → `permissionDecision: deny`「製卡助手不能做這件事」；ledger 最後一行的 reason_code 是 `agent_scope`。同一條不帶 agent_id → stdout 是空的（pass） |
| 17 | 過 | `tests/fixtures/guard_corpus.json`：a6435a0 有 988 條，375c805 有 1044 條；前 988 條逐筆相同（`n[:988]==o`），diff 刪 0 行。`test_guard_corpus`、`test_free_area`、`test_guard_pw` 都在上面 485 個裡，綠 |

### 裁定一起驗

| 裁定 | 判 | 證據 |
|---|---|---|
| 1 | 過 | PowerShell `start '<V>\AI 產出\x.docx'` → pass（照 Start-Process 拆）；`start '' '<V>\AI 產出\runme.bat'` → pass，但實跑 `Start-Process '' 'C:\nonexistent.txt'` 是 `ParameterBindingValidationException`（空的 FilePath），不會執行，不算洞 |
| 2 | 過 | Bash `start "<V>/AI產出無空白.docx"`（沒空白的引號字當目標）→ pass；驗收 2 第三條（有空白）當標題 → pass |
| 3 | 過 | (a) `Start-Process cmd '/c','<RAW>\evil.bat'` → `(deny, Z9, run_file)`；`Start-Process wscript -ArgumentList '<V>\AI 產出\x.wsf'` → `(deny, Z8, run_file)`（單一元素照原樣接，內層從空白斷開，算到第一層，見裁定 4）。(b) `Start-Process powershell` 是當系統程式判（驗收 6 pass）；cwd 底下真的有 `runme.bat` 時，`Start-Process runme -WorkingDirectory '<V>\AI 產出'`、`cd '<V>\AI 產出'; Start-Process runme.bat` → `(deny, Z3, run_file)` |
| 4 | 過 | 驗收 6、8 的多元素接法對；單一元素見裁定 3 那條 |
| 5 | 過 | `test_lib_cmdparse` 綠；簽名照 `open_stage(verb, words, powershell, base=None)`（讀 diff） |
| 6 | 過 | `powershell -Command "Start-Process '<V>\AI 產出\x.docx'"` → `(deny, Z3, output_shell)`；`Get-ChildItem \| Start-Process` → unparsed；`Start-Process … -FilePath …`（重複具名參數）→ deny；Bash `open -x "…"` → unparsed；`-Verb PrintTo` → `(deny, Z3, run_file)` |
| 7 | 過 | 見驗收 15 |

## 發現

| # | 嚴重 | 內容 | 證據 |
|---|---|---|---|
| 1 | 高 | **新壞的。** 開一個夾就會讓同一句裡遞迴讀同一個夾的另一段跳過憑證掃描（第三道），子夾裡密碼檔的內容讀得到。原因：`guard.py` 797 行的 `open_exempt` 只扣掉別段的 `own`、`stage_reads`、`redirect_targets`，萬用字元的開頭夾、`implicit_dirs`、`free_dirs` 都沒扣；1244 行的走訪又只看 `read_dirs` 有沒有。不用刻意繞：模型先開夾給客戶看、再 grep，就會碰到（code-review） | `密碼.txt` 放在 `<RAW>\客戶案件\深\`：`grep -r x <RAW>/客戶案件/*` 在 main 與這版都是 `(deny, Z9, credential_inside)`；`explorer <RAW>/客戶案件 ; grep -r x <RAW>/客戶案件/*` 在 main 是 `(deny, Z9, credential_inside)`，這版是 `(pass)` |
| 2 | 低 | **新壞的，沒重現出真的會執行。** `_RUN_EXT` 缺 PATHEXT 裡的 `.vbs` 以外那幾個（`.wsf .vbe .jse .wsh .msc .cpl`）。cwd 是來源夾、裡面只有 `onlyw.wsf` 時，`Start-Process onlyw` 在 main 是 unparsed，這版是 pass（code-review）。我實跑 PowerShell 5.1 的 `Start-Process <裸名>`（改 process cwd 或加 `-WorkingDirectory`）都報「找不到檔」，`.wsf` 沒跑；cmd `start "" <裸名>` 的實測卡住，沒有結果（**可能在桌面跳出一個 cmd 視窗，請關掉**） | `cd '<RAW>\客戶案件'; Start-Process onlyw`、`…onlyv`（.vbe）：main 是 `(deny, '', unparsed)`，這版是 `(pass)`；帶副檔名的 `onlyw.wsf` → `(deny, Z9, run_file)` |
| 3 | 中 | **main 本來就放行，但這題新加的 run_file 能被繞過**：開檔動詞寫成全路徑（`C:\Windows\explorer.exe '<RAW>\客戶案件\evil.bat'`、`C:\Windows\System32\cmd.exe /c start "" "…evil.bat"`）、Bash 反斜線空白當標題（`start a\ b.docx <RAW>/客戶案件/evil.bat`）、大括號展開（`start {'a b',<RAW>/…/evil.bat}`）、cmd 延遲展開（`$env:X='…evil.bat'; cmd /v:on /c start !X!`）都是 pass（code-review，我逐條實測，main 也是 pass）。都要刻意寫，跟裁定 8 的殼字串那族同類 | 上面五條在 worktree 與 main 都是 `(pass)` |
| 4 | 高 | **main 本來就有、spec 外。** `powershell -EncodedCommand <base64>`（`-enc` 也是）整個不解碼：編碼成 `Remove-Item '<V>\系統\x.md'`，直接跑就 pass，守門完全看不到。這題讓 `Start-Process powershell -ArgumentList '-EncodedCommand','…'` 也從 unparsed 變成 pass，不過直接跑本來就過，沒有多開新的能力 | 252 字的 base64：main 與 worktree 的 `powershell -EncodedCommand …`、`powershell -enc …` 都是 `(pass)`；`Start-Process powershell -ArgumentList '-EncodedCommand','UgBlAG0A'` 在 main 是 unparsed，這版是 pass |
| 5 | 低 | 8.3 短檔名繞過「巨集檔不收」：`evilmacro.docm` 的短名是 `EVILMA~1.DOC`（這台 C: 有開 8.3），`Start-Process '<V>\AI 產出\EVILMA~1.DOC'`、`ii …` 都是 pass。打開後巨集還是要過 Office 信任中心（預設會先問），而且要刻意用短名 | `dir /x` 列出 `EVILMA~1.DOC evilmacro.docm`；兩條都是 `(pass)` |
| 6 | 低 | 照 spec 做的，給設計參考：白名單裡的 `.doc .xls .ppt .rtf` 也能帶巨集或內嵌物件，跟「巨集檔刻意不收」的用意不一致。`Start-Process '<RAW>\客戶案件\m.doc'` 在 main 是 Z9 readonly_source，這版是 pass（code-review） | 同左 |
| 7 | 低 | 測試工具：這台的 `pytest 9.0.2`＋`pytest-xdist 3.8.0`＋`execnet 2.1.2` 用 `-n auto` 跑，8～11 個測試因為 `execnet DumpError: can't serialize <class 'pathlib.WindowsPath'>／<class 'kb.guard.Decision'>` 紅了（是 subtest 報告傳回主行程時序列化失敗，不是斷言錯）。main 也一樣紅了 9 個，序列跑全綠，所以 conventions 的平行指令在這組版本下不可靠。xdist 是我照 conventions 用 `pip install --user` 補裝的，裝完才收到不要跑全套的更正 | 平行跑：worktree 11 紅／8 紅（兩次），main 9 紅，錯誤全是 DumpError（另外 1 個是 selftest 的 5 秒逾時）；序列跑 485 passed |

code-review 另外 2 條沒列：「`-ArgumentList` 含空白的元素加雙引號，跟 Start-Process 實際接法不同」的例子 `Start-Process cmd -ArgumentList '/c','x','a & del <V>\系統\y.md'` 實測是 `(deny, Z6, system_render)`，沒有造成放行；「`open_stage` 叫兩次、邏輯三處重複」裁定 5 已經說這題不改。

### 攻擊面探測沒找到洞的（31 條裡其他的）

`file:///…/runme.bat` 網址、`Invoke-Item '<V>\AI 產出\*'`（萬用字元，加 `-Include *.bat` 也一樣）、結尾的點（`runme.bat.`）、ADS（`x.docx:runme.bat`）、`.hta`、`explorer '…runme.bat'`、`rundll32 url.dll,FileProtocolHandler <bat>`、`mshta`、`Microsoft.PowerShell.Management\Start-Process <bat>`、`-RSO` 別名（認不出就算 unparsed）、`-RedirectStandardOut` 縮寫、`-RedirectStandardInput <密碼檔>`、`explorer '<RAW>\行政\薪資'`（排除夾本身）都照擋。`Start-Process '<V>\AI 產出\x.docx' -ArgumentList '/mAutoMacro'`、`cmd //c start "" x.docx <bat>` 是 pass：參數交給 Word 處理，不會執行那個 bat，不算洞。

## plugin-dev 審查

沒跑。這題沒動 `.claude-plugin/plugin.json`、`hooks/`、SKILL.md（diff 只有 `scripts/kb/_lib/cmdparse.py`、`scripts/kb/guard.py`、測試、`ops/`）。

## 沒測到的

- 確認情境 1～4（交給確認 session）；Word、Excel、PowerPoint 實際附著改沒在真的 Office 上跑，只驗守門判斷。
- 全套測試（照只跑相關測試的規則）。
- macOS 的 `open`／`xdg-open` 只驗了解析，沒在那些平台跑。
- 發現 #2 的實際執行沒重現出來（見表）。

## 第 2 輪

日期：2026-10-30
測的版本：實作 `af40b38`（修裁定 9、10、11），併入 main `49384db`（裁定 15）後的 `0ef5916`。這輪 diff 是 `380fd00..af40b38`。
做法：同第 1 輪的假知識庫與 `kb guard decide --json`（cwd＝`<V>`），每條都用 `git archive main` 解出的 main 再跑一次對照。這輪只驗裁定 9～11、15，另外抽回歸 4 條（驗收 1、6、9、10 各一條）。`/code-review high 380fd00..af40b38` 是分叉執行的，**卡住 600 秒後被終止，沒有結果**；這輪程式 diff 只有 26 行，我在主線程自己讀過，並補了 19 條會走到新程式路徑的邊界探測。

### 結論

**裁定 9、10、11、15 全過，回歸 4 條照舊。這輪沒有新壞的。** 新的發現有 2 條（#8 是照裁定 9 字面做的多擋、#9 是 main 本來就有的），都是低，不影響進確認。

相關測試（spec 列的 9 檔加 `grep -l` 找到的 6 檔，共 15 檔）序列跑：**487 passed、3085 subtests passed**，pytest 本身沒有失敗（花了 75 分鐘，第 1 輪是 6 分鐘，那段時間機器比較忙，原因沒查）。語料：1050 條，前 1044 條（含原本的 988 條）跟 `380fd00` 逐筆相同，這輪加了 6 條、沒有刪。全套沒跑（照只跑相關測試的規則）。

### 裁定逐條

| 裁定 | 判 | 證據（worktree／main） |
|---|---|---|
| 9 | 過 | 密碼檔在 `<RAW>\客戶案件\深\`：`explorer <RAW>/客戶案件 ; grep -r x <RAW>/客戶案件/*` → `(deny, Z9, credential_inside)`／同；單獨 `explorer <RAW>/客戶案件` → `(pass)`／main 是 deny。變化版都擋：PowerShell `explorer …; Select-String -Path '…\*'`、`&& grep -r x <夾>`、`explorer <RAW> ; grep -r x <RAW>/客戶案件`（Z10b credential_inside，跟 main 同）、`explorer <子夾> ; grep -r x <RAW>`、`cd <夾> && explorer . ; grep -r x .`、開別的夾再 grep、一次開兩個夾（其中一個被讀）都是 deny credential_inside。`explorer <RAW>/客戶案件 ; cat <RAW>/客戶案件/深/*` → `(deny, Z9, credential)` |
| 10 | 過 | cwd＝`<V>`，`cd '<RAW>\客戶案件'; Start-Process onlyw`（夾裡只有 `onlyw.wsf`）→ `(deny, Z9, run_file)`；`.vbe .jse .wsh .msc .cpl` 各一份也都是 `(deny, Z9, run_file)`；main 全部是 unparsed。裸名稱 `notepad`（cwd 底下沒有這個檔）→ `(pass)`，main 是 unparsed |
| 11 | 過 | `C:\Windows\explorer.exe '<RAW>\客戶案件\evil.bat'`、全大寫的 `C:\WINDOWS\EXPLORER.EXE …`、`C:\Windows\SysWOW64\explorer.exe …`、PowerShell 的 `C:\Windows\System32\cmd.exe /c start "" "…evil.bat"`、Bash 的 `C:/Windows/System32/cmd.exe //c start …`、`/c/Windows/explorer.exe …`、UNC `\srv\share\explorer.exe …` 都是 `(deny, Z9, run_file)`；main 全部是 pass。全路徑開文件（`C:\Windows\explorer.exe '<V>\AI 產出\x.docx'`、`cmd.exe /c start "" "…x.docx"`）→ `(pass)`。全路徑程式本身在知識庫裡（`& '<V>\AI 產出\explorer.exe' …`、`& '<V>\cmd.exe' /c start …`、`.\explorer.exe …`）→ deny run_file（Z3／Z8）。裁定說不修的 `start a\ b.docx <bat>` 照舊是 pass |
| 15 | 過 | 密碼檔直接放在 `客戶案件\`：explorer 加 grep 那條 → `(deny, Z9, credential)`／main 同。`open_stage` 回傳的 `exe` 欄：`C:\Windows\explorer.exe …` 回 `C:\Windows\explorer.exe`，`…\cmd.exe /c start` 回 `C:\Windows\System32\cmd.exe`，裸的 `explorer`、`Start-Process` 回 None |
| 回歸 | 過 | 驗收 1 第一條 pass、6 第一條 pass、9 第一條 `(deny, Z3, run_file)`、10 第三條 `explorer '<RAW>'` pass（`客戶案件\深\` 有密碼檔時也是 pass，開夾不算讀整夾） |

### 發現

| # | 嚴重 | 內容 | 證據 |
|---|---|---|---|
| 8 | 低 | 照裁定 9 的字面做（別段讀的路徑在開的夾底下就取消豁免），「開夾給客戶看，再讀夾裡一份檔」會被擋，只要那個夾的子夾裡有密碼檔。main 也一樣擋，不是新壞的。給設計參考：這種日常用法要不要放行。單獨讀那份檔是 pass | 密碼檔在 `客戶案件\深\`：`explorer <RAW>/客戶案件 ; cat <RAW>/客戶案件/a.docx`、`Invoke-Item '<RAW>\客戶案件'; Get-Content '<RAW>\客戶案件\a.docx'` → `(deny, Z9, credential_inside)`，main 同；單獨 `cat <RAW>/客戶案件/a.docx` → pass |
| 9 | 低 | **main 本來就有、spec 外。** `cd $X ; cat *.txt`：`$X` 是句子外面來的（環境變數）時推不出 cwd，萬用字元的讀取整句放行。變數在同一句設的（`X=…; cd $X; cat *.txt`、PowerShell `$x='…'; cd $x; Get-Content *.txt`）會擋 credential_inside。這輪的 `explorer <RAW>/客戶案件 ; cd $X ; cat *.txt` 也是 pass，結果跟拿掉 explorer 的版本一樣，開檔沒有多開新的能力 | `cd $X ; cat *.txt` → worktree 與 main 都是 `(pass)`；explorer 版：worktree pass、main deny（main 是靠 explorer 那段被算成寫才擋到的） |

### 這輪 diff 自己審的

- `open_exempt` 改成跟 `read_dirs`、`implicit_dirs`、`free_dirs`、glob 的開頭夾、寫入目標、cd 目標比上下層：相對 glob（`ls *.md`）、`Get-ChildItem *` 這類沒夾的 glob 都沒出錯，判斷合理（E1、E3 是 pass）。
- `exe`：全路徑的動詞只要 `_base` 對得上就照開檔判。程式本身在知識庫或來源外面時（例如 `C:\nope\ii.exe '<V>\AI 產出\x.docx'`）照開檔放行，main 也是 pass，沒變寬。
- 沒有發現正確性的問題。

### 沒測到的

- 這輪 code-review 子代理沒有結果，只有我在主線程讀 diff 加探測；要另外的審查，得再開一次。
- 確認情境、全套，同第 1 輪。

## 第 3 輪

日期：2026-10-31
測的版本：實作 `9148e8b`（裁定 29）、`6c1c711`（裁定 31），併入 main `8e5472b` 後的 `17fe4dc`。
做法：同前兩輪的假知識庫，每條丟 `kb guard decide --json`（cwd＝`<V>`），用 `git archive main`（`8e5472b`）解出的 main 跑同一條對照。這輪只驗裁定 29、31，再針對比對豁免做繞過探測。另外的審查沒跑：實作那輪已經用 API `claude -p` 審過，這輪的 diff 只有 `_compare_only` 一段，由我在主線程自己讀過並探測，沒有花費。

### 結論

**裁定 29 驗收 (a)～(g) 7 條、裁定 31 放行 6 條與照擋 9 條全過；回歸照舊。** 新發現 2 條：#10（低，這題新放寬：PowerShell 的 `-eq` 會把比對的字面值回傳出來，main 會擋的寫法這輪會 pass，但能做到的事 main 用變數本來就做得到）、#11（**高，main 本來就有、spec 外**：`clc`、`epcsv`、`iwr -OutFile`、`([type]'System.IO.File')::Delete` 這幾種寫法守門看不出是寫入，總目錄、客戶原檔可以直接清空）。#11 不擋這題進確認，但建議另起一題。

相關測試：spec 列的 9 檔，加上 `grep -l "cmdparse\|kb.guard" tests/*.py` 多找到的 `test_lib_selftest`、`test_manage2_round4`，共 11 檔（這次的 grep 只多找到 2 檔，前兩輪寫 6 檔，用的 grep 式子應該不同，沒追）。序列跑：**361 passed、3191 subtests passed、exit 0**（148 秒）。

### 裁定逐條

前綴 `W`＝`$w=[Runtime.InteropServices.Marshal]::GetActiveObject('Word.Application'); foreach ($x in $w.Documents) { if ($x.FullName -eq '<V>\AI 產出\x.docx') {`；Excel、PowerPoint 換成對應的 Application 與 `Workbooks`／`Presentations`。

| 項 | 判 | 指令（摘要） | worktree |
|---|---|---|---|
| 29(a) | 過 | `W $x.Content.InsertAfter('下週三前回覆'); $x.Save() } }` | pass |
| 29(b) | 過 | `Where-Object { $_.FullName -eq '<V>\AI 產出\x.docx' }`＋InsertAfter＋Save | pass |
| 29(c) | 過 | Excel `Where-Object { $_.FullName -eq … t.xlsx }` 改 `Range('A1').Value2`；PowerPoint `-ilike … s.pptx` 改 TextRange | pass／pass |
| 29(d) | 過 | Bash `python -c "…GetActiveObject('Word.Application')… x.FullName == r'<V>/AI 產出/x.docx' … InsertAfter('x'); d.Save()"` | pass |
| 29(e) | 過 | (a) 再加 `$x.SaveAs('<V>\AI 產出\y.docx')` | deny Z3 output_shell |
| 29(f) | 過 | (a) 前加 `$w.Documents.Open('<V>\AI 產出\x.docx')` | deny Z3 output_shell |
| 29(g) | 過 | 沒附著的 `if ('<V>\AI 產出\x.docx' -eq $a) { Remove-Item … }` | deny Z3 output_shell |
| 31 放行 | 過 | `InsertAfter('請 copy 這段')`、`InsertAfter('zip code')`、`$x.Tables.Add(…)`、`$x.Comments.Add(…)`、Excel `$b.Worksheets.Add()`、PowerPoint `$q.Slides.Add(2, 1)` | 6 條都 pass |
| 31 照擋 | 過 | `$w.Documents.Add()`、`$e.Workbooks.Add()`、`$p.Presentations.Add()`；引號外的 `copy a b`、`iex 'x'`、`& 'x.ps1'`、`. 'x.ps1'`、`Invoke-Command { 1 }`；句尾 `; Remove-Item x.tmp` | 9 條都 deny Z3 output_shell |
| 回歸 | 過 | 驗收 1、6 第一條 pass；7 第一條 deny Z8 protected；9 第一條 deny Z3 run_file；10 第一條 deny Z10 excluded；12 deny Z3；13 deny Z3 output_shell；14 用 Name 比對 pass。語料 1064 條，前 1053 條跟 `9148e8b^` 逐筆相同，這兩個 commit 只新增 11 條 | — |

### 發現

| # | 嚴重 | 內容 | 證據（worktree／main） |
|---|---|---|---|
| 10 | 低 | **這題新放寬，但沒有多出新能力。** 裁定 29 的前提「路徑只拿來比對」在 PowerShell 不成立：左邊是陣列時，`@($w.Documents).FullName -eq '<路徑>'` 回傳的是比對到的元素（就是那個路徑字串），不是 True／False。拿它當寫入的參數，字面值仍算「只出現在比對」，所以 `_touches_output` 跳過了。用的寫入方式要避開 `_COM_WRITE`、引號外的 `WRITE_WORDS` 與 `WRITE_CODE`（例如 #11 那幾種，或 Excel `Close($true, <新檔名>)`、PowerPoint `PublishSlides`）。**同樣的事不寫字面值也做得到**：`$t = $w.ActiveDocument.FullName; clc $t`、用 Name 比對再 `clc $x.FullName`、`$env:X` 在 main 都是 pass（D-515 附著不表態，加上守門展不開變數）。所以實際風險跟 main 一樣，只是 main 多擋了「字面值寫出來」那一種。修法（給設計參考）：比對的左邊限定是單一物件的 `$var.FullName`／`$_.FullName`（不收 `@(…)`、`(…)` 後面接 `.FullName`），或者比對式要放在 `if (…)`／`Where-Object {…}` 的條件裡才豁免 | `W` 換成 `$t = @($w.Documents).FullName -eq '<V>\AI 產出\x.docx';` 再接：`([type]'System.IO.File')::Delete($t)`、FSO `.DeleteFile($t)`、`clc $t`、`$w \| epcsv $t`、`epal $t`、`sp $t IsReadOnly $true`、`iwr https://example.com -OutFile $t`、`Add-Type …VisualBasic; [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($t)` → pass／main 都是 deny Z3。直接當參數 `clc (@($w.Documents).FullName -eq '<V>\AI 產出\x.docx')`（`-ceq` 也是）→ pass／deny Z3。比對資料夾 `@($e.Workbooks).FullName -eq '<V>\AI 產出'` 再 `Close($true, $d + '\n.xlsx')` → pass／deny。Excel `if ($b.FullName -eq …) { $b.Close($true, $b.Path + '\y.xlsx') }`、PowerPoint `$q.PublishSlides($q.Path)` → pass／deny。對照組：`$t = $w.ActiveDocument.FullName; ([type]'System.IO.File')::Delete($t)`、`…; clc $t`、Name 比對後 `clc $x.FullName`、`$t = $env:X; clc $t`、Excel `$e.ActiveWorkbook.Close($true, $e.ActiveWorkbook.Path + '\y.xlsx')` → worktree 與 main 都是 pass。有擋的：`Start-Transcript`（`start` 在 `_COM_WRITE`）、`([type]'System.IO.File')::Move`、`ExecuteExcel4Macro('FILE.DELETE(…)')` → deny Z3 |
| 11 | **高** | **main 本來就有、spec 外，跟附著 Office 無關。** 幾種 PowerShell 寫法守門認不出是寫入：別名 `clc`（Clear-Content，全名會擋）、`epcsv`（Export-Csv）、`epal`（Export-Alias）、`sp`（Set-ItemProperty）、`iwr`／`Invoke-WebRequest -OutFile`、`[type]` 拿到的 `System.IO.File` 的 `::Delete`、FSO 的 `DeleteFile`。不在 Z3 的區沒有第 (2) 條「參數碰到就擋」可以兜底，所以**字面路徑直接寫出來就會 pass**：總目錄、系統檔清空，客戶原檔清空、刪除都可以。Z3 有第 (2) 條兜底才擋到。建議跟裁定 32「守門：直譯器與編碼指令」放同一題，或另開一題補別名與 `-OutFile` | `clc '<V>\總目錄.md'`、`clc '<RAW>\客戶案件\a.docx'`、`$null \| epcsv '<V>\總目錄.md'`、`iwr https://example.com -OutFile '<V>\總目錄.md'`、`([type]'System.IO.File')::Delete('<RAW>\客戶案件\a.docx')` → worktree 與 main 都是 pass；`Clear-Content '<V>\總目錄.md'` → deny Z8 protected（全名有收）；附著加 `-eq` 回傳 Z9／Z8／Z6 路徑再 `clc` → 兩邊都 pass |

### 沒測到的

- 確認情境 3、4（人眼、真 Word）照舊交確認 session。
- python win32com 的 `Documents.Open`、`SaveAs2` 這一類是裁定 32 另起的題目，這輪沒測。
- 全套沒跑（照只跑相關測試的規則）。
