# Obsidian 首頁 測試報告

日期：2026-10-30
給誰看：設計 session（llm-wiki-j-85）、使用者 jielle2453
測的版本：分支 spec/obsidian-home，commit 1f54c34（merge main 之後，已是最新）
做法：spike 庫（`llm-wiki-test/obsidian-spike`）複製到暫存夾，每條驗收在各自的新複本上跑真的 `kb.py`（不改程式、不碰原庫）；1000 張卡的庫用 `tools/testdata/big_vault.py` 產（1002 張卡檔）；速度 5 次取中位數；code-review 高等級加 security-review，子代理只讀碼列疑點，疑點由我自己重現；全套 pytest 跑了兩次。

## 結論

**可以進確認 session，但有 4 條「中」建議先決定要不要在這題修（#1～#4）。**

- 驗收 18 條：18 過、0 不過。
- 沒有「高」。
- 全套 `python -m pytest -n auto -q tests`：3759 passed、2 skipped（`test_build_round1.py:158` 建符號連結沒權限、`test_lib_paths.py:218` 非 Windows 才跑，都跟這題無關）、exit 0；跑兩次結果一樣。`node --test "tests/obsidian/*.test.js"` 92/92。
- 「中」四條：#1 守門在 PowerShell 擋不住 `--v"ia"` 這種拼接，模型仍能自己帶 `--via obsidian`；#2、#3 `kb find` 的標籤處理跟 spec 與 `find.md` 寫的「同種類或」不一樣，而且會把沒空白的詞切碎、找不到標題就有的卡；#4 對話「退回」碰到 Obsidian 動過同一份檔會拒絕，拒絕句卻叫她「到那個對話退回」。
- 需要真的 Obsidian 才看得到的（外掛畫面、`obsidian://` 拉起、信任提示、搜尋框互動）不在這輪，留給確認。

## 驗收逐條

| # | 判定 | 證據 |
|---|---|---|
| 1 | 過 | `kb home --json`：spike 庫 5 次 0.318／0.303／0.305／0.302／0.297 秒，中位數 0.303、最慢 0.318；1000 張卡的庫 0.730／0.693／0.697／0.694／0.700，中位數 0.697、最慢 0.730。（`kb --help` 本身 0.15 秒。第一次量的時候背景正在跑全套測試，數字偏高 1.06／2.50 秒，作廢，全套結束後重量。）`schema` 是 `willy-home/1`、`version` 0.28.0（照裁定 3 跟 plugin.json）、`from` 10-23 = 今天 −7、`to` 12-29 = 今天 +60。`rows` 有 王宅、士林黃、松山張、中山林 與 `_other／其他`；沒有 open 條目也沒有期間在範圍的 內湖李（擱置）與 大安陳（removed）不列，符合裁定 5。 |
| 2 | 過 | spike 庫與 1000 張庫：開場那行（`hooks/session.line_agenda`）「逾期 1、今天 1、7 天內 1」、`agenda.counts` {1,1,1}、`kb home` counts {1,1,1} 與 `todo` 各組長度 {1,1,1}，三處一樣；逐件對 `kb agenda list`：逾期 10/28 確認燈具升級、今天 10/30 水電預計完成、這週 11/05 水電預計完成（士林黃），對得上。 |
| 3 | 過 | `kb find "王宅 報價 這個月" --json`：`parsed` 拆成 entity／type／time 三段（時間 10/1～10/31），4 筆都是掛王宅、卡型報價、日期 10/19～10/22，`hit` 全是 filter，也沒有漏（對照 `kb find 王宅` 的全部清單）。對話用法：`skills/answer` 本文與 `references/find.md` 第十節都叫先 `kb find`。1000 張庫 `find` 5 次 0.332／0.319／0.323／0.319／0.327（中位數 0.323、最慢 0.332）；spike 庫 0.19 秒。**注意**：spec 的例子「中山林 會議 上個月」在 spike 庫裡「會議」不是卡型（卡型叫「會議紀錄」），所以會被當成字，不是卡型；這是資料不是程式問題。另見 #2、#3。 |
| 4 | 過 | 在複本上登記 `abc`（廠商）並確認、`王師傅` 併進 `黃師傅`、王宅加別名 `阿宅`：`find "ＡＢＣ"` → 實體 abc（why 名稱）；`find "王師傅"` → 轉成 黃師傅（why 別名），13 張；`find "阿宅"` → 王宅，30 張；`find "水電"` → tag 工種=水電 17 張；`find "升級"` → 字，比標題與內文，王宅列進 entities（why 內文）；`find ""`／`"   "` 不當機（人讀印「沒有找到」、json 空）；`find "-5度"` 不被 argparse 吃掉。 |
| 5 | 過 | 對話 A（`turn.start`，`current.json` done false）進行中，`kb --via obsidian agenda done a-1c40cd39` → exit 0，新回合 `20261030-122619-obsd`（`source: obsidian`、done true），manifest 只有 `.system/agenda.json`、`系統/日程.md`；`current.json` 與 A 的回合檔內容沒變、A 沒有 manifest；工作日誌新一段抬頭「你在 Obsidian 按的」，「做了：日程完成：水電預計完成」。 |
| 6 | 過 | A 加提醒（`--session A`）、之後 Obsidian 加提醒：`versions list` 終端機兩筆都列（Obsidian 那筆標「（Obsidian）」）；`--session A versions list` 只列 A 的與舊的、沒有 Obsidian 的；`--via obsidian versions list` 只列 Obsidian 的，並印「另一個對話還有 148 次改動，不在這裡退」；`--via obsidian versions revert` 退的是 Obsidian 那筆（對話那條提醒還在）；終端機 `versions revert` 退最新一筆（Obsidian 的）。Obsidian 動的是別份檔時，`--session A versions revert` 順利退掉 A 自己的。Obsidian 動了同一份檔時對話退回被拒絕，見 #4。 |
| 7 | 過 | 造 250 個 Obsidian 回合＋30 個對話回合（都在 30 天內）：`versions clean --check` turns_removed 0；250＋230：移除 30（對話回合剩 200、Obsidian 250 一個沒動），實跑 `versions clean` 結果相同；20 個 Obsidian＋30 對話＋5 個 9/1 的舊 Obsidian：只清那 5 個。 |
| 8 | 過 | 日程.md 編輯：`- [x]` 水電預計完成、刪木作預計完成（松山張）、泥作預計進場 11/9 改 11/10、加一行「測試」→ `kb renders apply 系統/日程.md`：「照你改的做了：記成完成『水電預計完成』、取消『木作預計完成』、『泥作預計進場』改到 11/10（原本 11/9）／我看不懂、留在最下面「你加的」：測試」；日程.md 最底下有「## 你加的（還沒處理）」「- 測試」；`renders.json` carried 一筆 `c-14be8274`；`kb asks --all` 有「你在日程.md寫了「測試」，我看不懂：要怎麼處理？」，`results` 有「加成日程」（argv `agenda add --text 測試`）與「不用了」（`renders drop c-…`）；歷程 `by: hand` 三件；日誌「照你在日程.md改的：…、1 段字放進「你加的」」；再跑一次：「這頁沒有要照做的」。`--json` 回 `{page, applied[], carried[], dropped}`，跟外掛 `summarizeApply` 的假設一致。 |
| 9 | 過 | 同樣的編輯不叫 apply，直接 `kb agenda add` 別的：三件都照做（水電 done、木作 cancelled、泥作 11/10），「測試」在 carried 與頁面最底下「你加的」，handedits 也存了她那份。（`kb lint handedit` 仍會列出那份，B-512 已記。） |
| 10 | 過 | 整個知識庫夾的 sha256 前後比對，`entity progress 王宅 結案 --check [--json]`、`rename 王宅 --to 王大宅 --check --json`、`merge 王師傅 --into 黃師傅 --check --json`、`merge 王宅 --into 中山林 --check`、`agenda cancel a-8c77e2c0（期間）--check --json`、已完成的件 --check：每條都「changed files: none」。句子對：「王宅記成結案：『驗收』這段期間會在今天結束；還開著的 5 件日程照舊」「王宅改名叫王大宅：夾、綜合卡、30 張檔案卡跟著改，舊名記成別名」「王師傅併進黃師傅：…9 張檔案卡改掛黃師傅；合併之後要分開只能退回」「取消期間『驗收』：…同一件事還開著的 5 件日程照舊」。拒絕路徑 exit 3 且 `refuse` 有字：不存在的日程、併自己、不存在的實體、改名撞名、廠商沒有狀態；狀態亂寫是人讀一句 exit 3。（`agenda cancel` 收的是日程編號 a-…，不是期間名稱。） |
| 11 | 過 | `kb init .`（要給路徑）：`--check` 列「會換 manifest.json／main.js、會建 styles.css、會補 community-plugins.json」；實跑放了三個檔（跟 `obsidian/` 逐位元相同）、`community-plugins.json` 從 `["dataview","other"]` 變 `["dataview","other","wiki-with-willy"]`；舊版外掛（4 位元組的 main.js、舊 manifest）被換掉；`.obsidian/app.json` sha256 沒變；再跑一次不重寫（mtime 不變）、`--check` 不再列。沒有 `.obsidian/` 的庫建出 `["wiki-with-willy"]`；`community-plugins.json` 壞檔或不是清單時不動、印一句並記 log；`plugins` 是檔案時印「Obsidian 外掛沒放成」但 init 照完成。 |
| 12 | 過 | `kb guard decide`：Write `.obsidian/plugins/wiki-with-willy/main.js` → deny Z7；Bash `echo x > .obsidian/app.json` → deny Z7；Read `.obsidian/workspace.json` → allow。額外探 17 種：大小寫 `.OBSIDIAN`、`.obsidian.`、`..` 繞回、絕對路徑、`cp`／`Set-Content`（Bash 與 PowerShell）／`sed -i`／`rm -rf`／`mv` 都 deny；`python -c open(...)` 照舊「看不出會寫到哪」deny；Glob／Grep／Read 放行。語料三條在 `tests/fixtures/guard_corpus.json`。 |
| 13 | 過 | 在複本放 `workspace.json`（lastOpenFiles 與 main 樹裡各有「公司行政/薪資」兩張卡與一張士林黃的卡）、外掛 `data.json`（opened 三個編號＋一個不相干的）、`renders.json` carried 三筆，`kb folders exclude 公司行政/薪資 --kind hidden`、`kb folders purge 公司行政/薪資`：workspace.json 只剩士林黃的卡與日程.md（lastOpenFiles 和葉子都是）、data.json 只剩 `f-5dc269cf` 與 `f-deadbeef`、carried 裡含卡標題「員工資料名冊」「2026第三季薪資表」的兩筆拿掉、不相干那筆留著，日程.md 的「你加的」同步重寫；成功句有「Obsidian 自己的快取在知識庫外面，下次打開 Obsidian 會自己丟掉」。見 #10。 |
| 14 | 過 | 這台 Obsidian 真的裝了（登錄有 `obsidian` 協定、`%LOCALAPPDATA%\Programs\Obsidian\Obsidian.exe` 在）、也沒在跑，為了不動真的 `obsidian.json` 與不把 Obsidian 拉起來，用替身在行程內跑 `obsidian_cli.run`（`OBSIDIAN_CONFIG` 指暫存、`_running`／`installed`／`_startfile` 換掉）：未裝＋未登記 → `{"installed":false,"registered":false,"plugin":false}`；裝了 → installed true；Obsidian 在跑且沒登記 → exit 3「先關掉 Obsidian 再說一次…」、設定檔沒建、沒叫 startfile；沒在跑 → 寫入設定（16 碼 hex id、path、ts）並叫 `obsidian://open?path=<整串百分比編碼>`；登記後 status 三項都 true，再 open 不重寫；設定檔壞掉 status 當沒登記；路徑含空白、`&`、`#`、中文都被編碼。 |
| 15 | 過 | 新資料夾 `kb build start` → 無來源時跳過整理那幾步，訪談之後是「Obsidian」（做什麼：`kb obsidian status --json`、`kb obsidian open`；讀 `steps.md` Obsidian）；`kb build done obsidian`（不開 Obsidian）→「Obsidian 做完了，下一步 交付報告」。`STEPS` 順序 …tags、obsidian、finish。 |
| 16 | 過 | `node --test "tests/obsidian/*.test.js"`（node v24.20.0）：tests 92、pass 92、fail 0。測項名稱涵蓋：installed_plugins.json 多筆挑 projectPath／scope user／最後一筆、每個 kb 呼叫 `kb.py` 後緊接 `--via obsidian`、時間軸 bar 與點、日程第二題圖形（子項、連線、基準線、要徑）不報錯、不認得的 shape 不畫、各動作與復原的相反動作、合併復原叫 `kb versions revert`、離開那一行才叫 `renders apply`、注音選字中按 Enter 不搜。`tests/test_obsidian_js.py` 在全套裡跑過。（假 DOM，真的 Obsidian 留給確認。） |
| 17 | 過 | `kb selftest` →「自我檢查過了（0.28.0）」，`STEPS` 最後多 `obsidian`；在暫存 clone 把 tag v0.28.0 重指到這個 commit 後跑 `tools/release.py build v0.28.0`：170 個檔，zip 有 `obsidian/main.js`、`manifest.json`、`styles.css`，沒有 `tools/`；對舊 tag（沒有 obsidian/）跑 build 會失敗並列出三個「不在 zip 裡」。 |
| 18 | 過 | 全套 3759 passed、2 skipped、exit 0（兩次）。plugin-validator：見下面「plugin-dev 審查」。 |

## 發現

| # | 嚴重 | 內容 | 證據 |
|---|---|---|---|
| 1 | 中 | **守門在 PowerShell 擋不住拼接寫法的 `--via`**。`hooks/guard.py` 的 `_has_flag` 只看字面的 `--via`／`--via=…`／它的前綴；`kb_args` 在 PowerShell 只剝「整個 token 被引號包住」的引號。`--v"ia" obsidian` 字面不是旗標，守門 allow，但 PowerShell 實際交給 python 的是 `--via`，kb 就開了 Obsidian 回合（`source: obsidian`、`in_conversation` 回 False），模型做的事記成「你在 Obsidian 按的」、不併進對話、對話退回挑不到。同一個辦法對 `--turn`、`--agent`、`--session` 本來就成立（不是這題才有），但這題把 `--via` 加進「守門說它擋」的清單，語料與測試只有字面與前綴。Bash 的 `{--via,obsidian}`、`--via$X` 守門回 ask（要客戶按允許），不是靜默放行。 | 把 PreToolUse 的 JSON 直接餵 `hooks/guard.py`：PowerShell `--v"ia" obsidian agenda done a-1` 與 `--v"ia"=obsidian` → allow（updatedInput 只插了 `--session s1`）；PowerShell 實跑 `python -c "import sys;print(sys.argv[1:])" --v"ia" obsidian` → `['--via','obsidian']`。Bash `{--via,obsidian}`、`--via$X`、`--vi$X`、`{--turn,T}` → ask；`--via obsidian`、`--via=obsidian`、`--vi`、`--v`、引號包整個旗標 → deny。`--via` 放在子命令後面守門 allow，但 argparse 直接 exit 2（試過 `agenda --via obsidian done`、`agenda done … --via obsidian`、`--vi`），沒有影響。（子代理 security-review 的發現，我重現了 PowerShell 那一半。） |
| 2 | 中 | **`kb find` 同種類標籤是「而且」，不是「或」**。spec「比對：不同種類且、同種類或」與 `skills/answer/references/find.md` 第十節都寫同種類是或，但兩個標籤詞同時要中，結果少很多。 | spike 庫：`find "水電"` 17 張、`find "木作"` 6 張，`find "水電 木作"`（parsed 兩個 tag）只剩 3 張；對照 `find "王宅 中山林"`（兩個實體）是 50 張（是或）。（code-review 也指到 `_match` 裡 `any(not (mine & ids) for ids in tag_ids)`。） |
| 3 | 中 | **沒空白的詞被標籤詞切碎，找不到標題裡就有的卡**。拆字先在整串裡找標籤詞，剩下的才當字。「燈具升級」拆成「標籤 燈具」＋「字 升級」，且要同時成立，結果 0 筆。 | 有一張卡標題叫「信義王宅追加燈具升級」：`find "升級"` 找得到（第 1 筆）；`find "燈具升級"` 與 `find "追加燈具升級"`（把卡標題原樣貼上）都回 0 筆，parsed 是 `字 追加、標籤 燈具、字 升級`。她點掉「標籤 燈具」那個 chip 可以重搜，但 `find.md` 叫對話「整串字原樣交給它、不用先自己拆」，Claude 會直接答「沒有」。建議：結果是 0 的時候拿掉標籤條件再試一次，或標籤詞只認前後有空白／邊界的。 |
| 4 | 中 | **Obsidian 動過同一份檔之後，對話的「退回」被拒絕，而且拒絕句指錯地方**。Claude 在對話裡改日程、她在 Obsidian 又勾了一件，之後她對 Claude 說「退回」→ `.system/agenda.json`、`日程.md` 之後有別的回合改過 → 什麼都沒動。句子把 Obsidian 的回合叫「對話外」，還說「要退得先到那個對話退回它」，但那一筆是 Obsidian 的，要在 Obsidian 按「復原」或叫 `--via obsidian versions revert`。Obsidian 自己的復原也算一筆改動，所以退一次之後對話那邊更退不了。 | 複本上：`--session A agenda add`、之後 `--via obsidian agenda add`，`--session A versions revert` → exit 3「退不回去：這一句之後，有別的地方也改過同一份，什麼都沒動／- .system/agenda.json：10-30 12:26 那一次（對話外）／…／要退得先到那個對話退回它，或直接跟我說要改成什麼。」Obsidian 動別份檔時對話退回正常（驗收 6）。 |
| 5 | 低 | **沒做事的 `renders apply`／`drop` 也開一個空的 Obsidian 回合**。`renders_cli.run` 先 `turn.current(vault)` 才分派。外掛每次離開被改的那一行、切頁都叫一次，大多沒事可做，每次都留下一個只有 `turn.json` 的 `-obsd` 目錄，`versions list` 多一列「修改 0」。`revert` 會跳過空的（merge 後接一個空 apply，`--via obsidian versions revert` 照樣退掉 merge 的 23 份），所以只是雜訊與回合目錄增加，到 30 天才清。 | `--via obsidian renders apply 系統/日程.md` 三次（都「這頁沒有要照做的」）→ versions 目錄 157 → 160；`versions list` 出現「那一次（Obsidian）｜修改 0、新增 0、刪除 0」。`kb home`／`find` 不開回合（160 → 160）。 |
| 6 | 低 | **`.system/sources.json` 壞掉時 `kb home --json` 直接 traceback**。`sources_lib.load` 在 `safe()` 外面，spec「某一區壞了只那一區空白」不成立，外掛整頁空白（只印「kb 回的不是首頁資料」）。agenda、inventory、entities、pending 壞掉都正常（exit 0、仍有 JSON）。 | 複本上把 `sources.json` 改成 `{bad`：`kb home --json` exit 1、stdout 空、stderr `JSONDecodeError`；其他四個檔壞掉各自 exit 0 有輸出。 |
| 7 | 低 | **`kb obsidian open` 在拒絕之前就把外掛檔寫進知識庫**。順序是 `place()` → 檢查在不在跑／有沒有登記；Obsidian 在跑而且沒登記時 exit 3，但外掛三個檔與 `community-plugins.json` 已經寫了，沒有日誌也沒有回合。`place()` 的 `OSError`（唯讀、OneDrive 或防毒鎖住）沒接，直接 traceback（`init` 有接）。 | 替身跑法：第一次 `open`（running、未登記）exit 3，緊接著 `status` 的 `plugin` 就是 true，且第二次 `open` 的 `wrote` 是空（檔早就在了）。OSError 是讀碼（code-review）。 |
| 8 | 低 | **`kb obsidian` 模組的 docstring 有無效的跳脫序列 `\o`**（`%APPDATA%\obsidian\obsidian.json`）。Python 3.14 編譯時印 SyntaxWarning（pytest 的 warnings 有這一條）；`-W error` 下是 SyntaxError，以後的 Python 可能直接變錯誤。 | 全套輸出：`scripts/kb/obsidian_cli.py:4: SyntaxWarning: "\o" is an invalid escape sequence`；`python -W error` parse 同一檔 → SyntaxError。 |
| 9 | 低 | **外掛 JS 兩處競態與空值**（讀碼，沒有在真的 Obsidian 裡跑）：`doSearch` 沒有請求編號，先送的慢查詢回得比後送的晚，會蓋掉後面的結果，`ui.q` 與結果對不上；`renderTimeline` 在 `if (!home) return` 之前就把「全部展開／收起」按鈕畫出來，`kb home` 還沒回來或失敗時按下去 `setAllRows` 讀 `home.timeline` 丟 TypeError，handler 沒包 `safe()`。 | `obsidian/main.js` 的 `doSearch`（約 1406 行）、`renderTimeline`／`setAllRows`（約 1560～1597 行）。 |
| 10 | 低 | **purge 只清 workspace.json 和外掛 data.json**。Obsidian 的核心外掛「書籤」（`bookmarks.json`）等也可能存卡的檔名；spec 寫明只清這兩個，所以不算偏離，但成功句的說法「Obsidian 自己的快取在知識庫外面」沒提書籤。 | 讀碼：`purge._obsidian_traces` 只開 `OBSIDIAN_WORKSPACE`、`OBSIDIAN_DATA`；spike 庫的 workspace 裡有 `bookmarks` 分頁。我沒有真的建書籤驗證會殘留，列為待查。 |
| 11 | 低 | **小的文字與資料落差**：(a) `_lib/build.py` 檔頭 docstring 的步驟順序沒有 obsidian；(b) `ops/map-lib-platform.md` build 那一列前半的順序也沒有（後半有寫）；(c) `kb home` 的 `recent[].open.path` 是全小寫（`c:/users/jie/appdata/...`），Windows 開得了，但畫面上若顯示路徑會很怪（路徑來源是清冊裡存的值）；(d) `renders_cli._drop` 忽略 `apply_hand` 回的 `KEEP_FAILED`，再用 `hand={}` 重寫會蓋掉她那份沒存成的改動（讀碼，只有存 handedits 失敗時才發生，沒重現）；(e) `agenda._consume_hand` 沒有 try/except，若認手改時丟例外，之後每次 `agenda` 寫入都會失敗（讀碼；我用 24 種打勾、刪行、壞日期的手改試過沒觸發）。 | (a)(b) 讀碼；(c) `recent` 輸出；(d)(e) code-review 指出，我讀碼確認程式如描述，但沒有重現。 |
| 12 | 低 | **spec 與假資料的落差**：spec 說 spike 庫是 118 張卡、12 件 open 日程；卡數 118 對，但這份複本的日程有 45 件（`kb agenda list` 40 多行），不影響通過與否，確認 session 數日程時別照 12 件對。 | `kb agenda list`。 |

## plugin-dev 審查

- 依據：`plugin-dev` 的 `skill-development`（SKILL.md 與 references 的寫法）、`hook-development`、`agents/plugin-validator.md` 檢查表（路徑在 `~/.claude/plugins/marketplaces/claude-plugins-official/plugins/plugin-dev/`）。這個 session 的可用代理清單裡沒有 `plugin-dev:plugin-validator`，所以我沒有派它，改跑 `claude plugin validate .`（2.1.312）對整個 repo。
- `claude plugin validate .`：「Validation passed with warnings」。兩條都跟這題無關：plugin.json 沒有 icon（`ICON_MISSING`），README 沒有 marketplace 安裝那一行。`plugin.json`、`hooks/hooks.json` 沒動（這題只動 `hooks/guard.py` 兩行：`SELF_FLAGS` 句子與 `GLOBAL_VALUE_FLAGS` 加 `--via`）。
- `hooks/guard.py`：改法小、跟既有 `--turn／--agent／--session` 同一套，語意沒問題；問題只有發現 #1（拼接寫法沒擋）。
- `skills/answer/SKILL.md`、`references/find.md`：frontmatter 沒動；第十節跟現有各節同樣的寫法（帶範例、分點、拒絕與找不到怎麼說），「`kb find`」前綴照該檔既有簡寫。內容上有一句跟程式不符：「同一種是『或』」（發現 #2），以及「整串字原樣交給它」會碰到發現 #3。
- `skills/build/references/steps.md`：步名對照加了 `obsidian Obsidian`，新增「## Obsidian」一節：先問她會不會用、沒裝請她到 obsidian.md、說好才 `kb obsidian open`、被擋怎麼說、做完 `kb build done obsidian`；跟 `kb build status` 的「做什麼」一致，沒有前提這點也跟程式一致。`skills/build/SKILL.md` 描述的步驟清單沒有列 Obsidian（描述文字，不影響觸發，可不改）。

## security-review

- 守門與 `--via`：見發現 #1。Bash 三種展開寫法都是 ask；只有 PowerShell 的引號拼接是靜默放行。
- `.obsidian` Z7：大小寫、尾端點、`..`、絕對路徑、Bash／PowerShell 寫入指令都 deny（驗收 12 的額外探測）；讀、Glob、Grep 放行是 spec 的設計。
- 外掛叫 kb：`execFile` 傳陣列（不經 shell），`--via obsidian` 緊接在 `kb.py` 後，查詢字以 `-` 開頭時用 `--` 隔開；使用者填的值放在單一 argv 元素裡，沒有注入。次要：實體名稱若以 `-` 開頭，`kb lookup <名>` 沒有加 `--`，會變成 argparse 錯誤（只是失敗，不是注入）。
- `shell.openExternal`：外掛本身不驗網址的 scheme，靠 `kb output link` 只收 `https://claude.ai/…` 才安全；`shell.openPath` 開清冊裡的本機原檔（點了才開，網路路徑拒絕）。這兩處是靠 kb 端把關，外掛端沒有第二道，列為觀察、不算發現。
- DOM：外掛沒有 `innerHTML`／`outerHTML`／`insertAdjacentHTML`，一律 `textContent`／文字節點；剪貼簿只寫「幫我找：<字>」。
- `kb init`／`kb obsidian open`：只複製 plugin 自己 `obsidian/` 的三個固定檔；`register` 只寫 `find_vault` 回來的知識庫路徑，URL 整串百分比編碼；Claude 無法透過 kb 把任意內容寫進 `.obsidian`。
- purge：只讀寫 `.obsidian/workspace.json` 與外掛 `data.json`，JSON 解析後剪枝，沒有路徑組合問題。
- 子代理（只讀）讀碼的結論跟我的探測一致：高信心只有 #1。

## 沒測到

- 真的在桌面版 Obsidian 裡：外掛載入與信任提示、首頁各區的畫面、時間軸／月曆、搜尋框（注音選字、下拉、chip）、點檔用 Excel 開、`obsidian://` 真的拉起 Obsidian、開著的頁被 `kb` 改寫時編輯器的行為、重新載入提示。→ 留給確認 session。
- `installed_plugins.json` 找 kb（待查 3）：這台沒裝 wiki-with-willy（只有舊的 llm-wiki@llm-wiki），沒辦法實測；檔案格式（`plugins.<名@市集>[]` 的 `scope`、`projectPath`、`installPath`）跟外掛假設的相符（對照這台別的外掛）。→ 留給確認。
- 對應成磁碟機代號（Z:）的原檔。→ 留給確認。
- 驗收 14「沒裝 Obsidian」只能用替身（這台真的裝了）。
- 驗收 17 的 `release.py build` 是在暫存 clone 重指 tag 跑的，沒有跑 `publish`。
- 沒有 Mac 可驗 `os.startfile` 不存在的路徑（讀碼：未接 AttributeError）。
