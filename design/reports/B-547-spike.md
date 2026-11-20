# B-547 網頁介面 spike 報告

日期：2026-11-20
環境：Windows 11 家用版、Claude Code 2.1.314（訂閱登入，沒有 ANTHROPIC_API_KEY）、plugin 用 `--plugin-dir` 指到 repo。
腳本與原始紀錄都在 `C:\Users\Jie\Desktop\llm-wiki-test\網頁-spike\`（`紀錄\` 夾有每次 `claude` 的完整 JSON 事件）。

## 總結（七項各一行）

1. 常駐 claude（D-351）：**做得到**。同一程式連送多句上下文連續、開場 hook 只跑一次；回答中再送一句會「插進同一回合」不是排隊；背景子代理在主回答結束後做完、結果自動變成新一回合回來；關掉用 `--resume` 接回約 2.7 秒（跟全新開始一樣快），但 resume 會再跑一次開場 hook。
2. 用量與快取（D-351）：**做得到**。快取在這個訂閱是 1 小時制（`ephemeral_1h`），隔 6 分鐘全中；隔約 133 分鐘（原定 65 分，電腦睡著拖長）快取已過期、整段對話重新寫入（見第 2 項）。開場 hook 約 1,900 字、5 段日誌約 1,000 字，都很小；開新一段的固定成本約 13k token。
3. 詢問管道（D-352）：**做得到**。`--permission-prompt-tool stdio` 讓權限詢問與 AskUserQuestion 都變成 stdout 上的 `control_request`，用 `control_response` 回，allow／deny 與選項答案都有效；守門的 ask 同樣走這條，附白話理由。
4. auto mode 擋刪除（D-352）：**做得到、而且沒擋**。四個情境加兩個硬用 `rm` 的，auto mode 一次都沒擋、一次詢問都沒有；AI 因 plugin 規則自己改用 `kb source-edit trash`。
5. 排程（D-356）：**做得到（重開機那段沒測、不確定）**。IgnoreNew 不會開第二個；殺掉後 37 秒內自己起來；跑超過 17 分鐘沒被停。「更新後自動登入」開關在這台查不到明確值，要人實測。
6. Cloudflare（D-357）：**部分確定**。免費方案可加成員；Access 工作階段最長一個月；**權杖能不能限定到單一 Access 應用的名單：文件查不到，不確定**（最小的確定組合是帳號層級「Access: Apps and Policies Edit」）。
7. 手機存資料（D-358）：**部分確定**。iPhone Safari 一般網頁：7 天沒用會清 IndexedDB／Cache；加到主畫面的網頁不受這個 7 天上限；背景同步 iPhone 做不到，只能她打開網頁時送。

---

## 1. 常駐 claude（D-351）

**做了什麼**：`claude -p --input-format stream-json --output-format stream-json --verbose --permission-mode auto --plugin-dir <repo> --include-hook-events --permission-prompt-tool stdio`，工作目錄＝測試知識庫。stdin 每行一個 `{"type":"user","message":{"role":"user","content":"..."}}`。腳本：`cc.py`（小工具）、`t1a.py`、`t1b.py`、`t1c.py`、`t1d.py`、`t1e.py`。

**看到什麼**
- 連送 3 句（t1a）：三句的 `session_id` 相同（0903c106…）、上下文連續（第 2 句答得出暗號「藍鯨」）。每句 2～6 秒（含思考）。`SessionStart` hook 只在第一句前出現一次（事件 `SessionStart:startup`），之後每句只有 `UserPromptSubmit` 與 `Stop` hook（輸出都是空的）。
- 回答中再送一句（t1b）：AI 正在跑一個 12 秒的 Bash，第 4 秒送第二句。第二句**不排隊、不出錯**，在 Bash 結果回來後被插進同一個回合（`UserPromptSubmit` hook 照樣觸發），AI 一次回答兩件事，只出一個 `result`（「A完\nB收到」）。意思：兩台裝置幾乎同時送時，後送的會被併進正在進行的回合，**不會得到各自獨立的 result**；伺服器要自己決定要不要等 result 之後再送（D-353 的「照順序送」要補這點）。
- 背景子代理（t1c）：叫它用 Agent 工具（背景）讀兩個檔。主回答 8.1 秒結束（「已派」）；子代理 11.9 秒做完，stream 上出現 `task_notification`，接著**常駐程式自己開了新的一回合**，15.3 秒又出一個 `result`，內容是兩個檔的內容。常駐模式下背景助手做得完、結果回得來（前提是程式沒被關掉，且 stdin 沒關）。
- 關掉後 `--resume <id>`（t1d）：上下文還在（答得出「藍鯨」）。**開場 hook 又帶了一次**（`SessionStart:resume`，同樣約 1,900 字）。從程式啟動到第一個回覆：2.5、3.0、2.7 秒，中位數 **2.7 秒**。全新開始（t1e，同樣一句「只回好」）2.6 秒；第一次用較複雜問題量到的 13.1 秒是因為 AI 還去查工具，不是啟動慢。
- 疑點：resume 又帶一次 hook，第一次 resume 多了約 2.4k token 的新寫入，之後的 resume 只多 38～40，所以看起來是第一次帶進去後重複的部分有被快取吃掉；但**有沒有在上下文裡重複兩份我沒能直接確認**。

**結論**：D-351 的常駐做法可行。
**對設計的影響**
- D-351 第 1 點「開場規則只帶一次」只在不關程式時成立；**關掉再 resume 會再帶一次開場 hook**（`hooks/session.py` 的內容，含 core.md）。要嘛接受（成本小，見第 2 項），要嘛讓 session.py 在 `source=resume` 時只帶短版。
- D-353 要補：伺服器看到「AI 回答中」又有新訊息時，**預設是會被併進當前回合**；若要「回完再處理」，伺服器得自己排隊到收到 `result`。
- 子代理的結果會在主回答之後以新的 `result` 到達，網頁要能接受「同一條對話沒人說話也冒出新回覆」。D-351「背景助手還在做時不關」要靠 `task_started`／`task_notification` 事件計數（或 `background_tasks_changed`）判斷。

## 2. 用量與快取（D-351）

**做了什麼**：每句 `result` 事件的 `usage`；快取過期測試 `t2.py`（讓一個讀了 28KB 檔的對話，T0 → +7 秒 → +6 分 → +65 分各送一句）；`kb journal recent` 字數。

**看到什麼**（單位 token）
| 情況 | input | cache_create | cache_read | output |
|---|---|---|---|---|
| 新對話第 1 句（只回「好」） | 2 | 13,431 | 31,790 | 3 |
| t1a 第 1／2／3 句 | 2／2／4 | 14,912／3,215／43 | 30,634／45,546／48,761 | 216／21／16 |
| t2 讀 28KB 檔那句 | 4 | 27,558 | 77,037 | 259 |
| t2 緊接下一句 | 4 | 51 | 59,348 | 3 |
| t2 隔 6 分鐘 | 4 | 13 | 59,399 | 3 |
| t2 隔「65 分鐘」（實際約 133 分，見下） | 4 | **28,791** | 30,634 | 3 |
- 這個訂閱的快取是 **1 小時**制：`cache_creation.ephemeral_1h_input_tokens` 有值、`ephemeral_5m` 是 0。隔 6 分鐘 cache_read 仍全中（59,399），沒有任何重寫。隔很久那句：cache_create 28,791（整段對話約 2.9 萬 token 被重新寫入）、cache_read 只剩 30,634（只有跨對話共用的固定前綴還在），所以**對話本身的快取過期了**。**注意**：這台電腦在等待期間睡著了（排好的 65 分鐘實際隔了約 133 分鐘：17:52 → 20:05），所以只證明「超過 1 小時會過期」，沒量到 1 小時內剛好哪一分鐘過期；6 分鐘有、約 133 分鐘沒有，中間 7～60 分鐘沒測。送出那句花 3.8 秒（含重寫快取）。
- 開場 hook 的 `additionalContext` 約 **1,900 字**。`kb journal recent` 5 段在測試庫約 970 字（每段約 190 字）；`tests/fixtures/journal` 的真實格式每段約 150～300 字，所以 5 段約 **1,000～1,500 字（約 1k token）**。
- 每個新的一段開頭固定寫入約 13k token（系統提示、工具、規則），不管有沒有接日誌。

**估算：快取過期後「接回重讀」比「開新的一段＋5 段日誌」貴的點**
- 接回 = 13k（固定）＋整段對話長度 N，全部要重新寫入。
- 開新的 = 13k（固定）＋約 3k（hook 約 1k、日誌 5 段約 1～1.5k）。
- 所以只要 N 超過約 **3k token**，過期後開新的一段比接回便宜；但便宜的是「寫入量」，而開新的會丟掉對話細節（只剩日誌）。若寫入成本是主要考量，D-351 的「長度超過 5 萬 token 才換」門檻其實很保守：5 萬 token 的對話過期後重讀大約是開新的 15 倍。若不想失去上下文又想省，換段的長度門檻可以降到 1～2 萬 token。（快取是 1 小時，所以「閒置超過 1 小時」這個條件剛好對得上快取過期。）

**對設計的影響**：D-351 第 3 點的 1 小時＋5 萬 token 數字可調：閒置條件（1 小時）合理，長度門檻可降。測量值不含 Claude Code 自己的摺疊。

## 3. 詢問管道（D-352）

**做了什麼**：`t3.py`。加 `--permission-prompt-tool stdio`；自己讀 stdout 的 `control_request`，用 `control_response` 回。用 `python`（標準函式庫）直接講，沒用 SDK。

**實際訊息樣子**
(a) 選項題（AskUserQuestion）——收到：
```json
{"type":"control_request","request_id":"31aa0475-…","request":{"subtype":"can_use_tool","tool_name":"AskUserQuestion","display_name":"AskUserQuestion","input":{"questions":[{"question":"你喜歡哪種水果？","header":"水果","options":[{"label":"蘋果","description":"選蘋果"},{"label":"香蕉","description":"選香蕉"}],"multiSelect":false}]},"tool_use_id":"toolu_…","requires_user_interaction":true}}
```
回答（把選到的 label 放進 `answers`，key 是題目文字）：
```json
{"type":"control_response","response":{"subtype":"success","request_id":"31aa0475-…","response":{"behavior":"allow","updatedInput":{"questions":[…原樣…],"answers":{"你喜歡哪種水果？":"香蕉"}}}}}
```
結果：AI 回「你選了香蕉」，答案有效。

(b) 守門要她按允許（D-212，`kb unlock get --name 門`）——收到：
```json
{"type":"control_request","request_id":"b2459e57-…","request":{"subtype":"can_use_tool","tool_name":"Bash","display_name":"Bash","input":{"command":"python \"…/kb.py\" --session … unlock get --name 門","description":"讀取存好的「門」這組密碼"},"description":"讀取存好的「門」這組密碼","decision_reason":"需要客戶按允許才會執行：要把存好的「門」密碼顯示出來","decision_reason_type":"hook","decision_reason_hook_event":"PreToolUse","decision_reason_hook_source":"plugin:wiki-with-willy","tool_use_id":"toolu_…"}}
```
- 回 `{"behavior":"allow","updatedInput":<原 input>}`：指令照跑。
- 回 `{"behavior":"deny","message":"她按了不允許"}`：指令沒跑，AI 回「這次沒有執行，因為權限視窗上按了『不允許』」。兩種都有效。
- `decision_reason` 就是守門的白話理由（D-212 的句子），可直接放卡片。`input.command` 裡 `--session <id>` 是 hook 加的，卡片要自己拿掉。

(c) 沒出現詢問的：auto mode 判定可以的 Bash、Write 到知識庫外的新檔（`外面\寫入測試.txt`），都沒有 control_request，直接做了。

**結論**：D-352 第 2 點可行；小伺服器只需要接 `control_request`（`can_use_tool`），不用另做 MCP。
**對設計的影響**
- 選項題要回的是「題目文字 → 選到的 label」的 `answers`，多選與「我自己說」要查 `multiSelect` 與 `Other` 的格式（這次沒測，沒有 SDK 範例可對）。
- 卡片等待期間 `claude` 就卡在那個 control_request，不會逾時（測的等待是秒級，長時間沒測）。D-352 第 4 點「卡片等她回時不關、不換段」自然成立。

## 4. auto mode 會不會擋她要的刪除（D-352）

**做了什麼**：每個情境都是全新程式、全新一句（`t4.py`）；handler 會記錄所有 control_request 並一律 allow，以便看「有沒有變成詢問」。

| 情境 | auto mode 擋幾次 | 詢問幾次 | 最後 |
|---|---|---|---|
| A 刪知識庫裡的假檔（「刪掉 原檔/假檔3.txt」） | 0 | 0 | 做完；AI 自己走 `/manage` skill → `kb source-edit trash --check` → `kb source-edit trash`，進資源回收筒 |
| B 刪知識庫外的假檔（`外面\外假1.txt`） | 0 | 0 | 做完，同上走 kb trash |
| C 先說「你覺得可以嗎？先不要動手」，下一句「確定，刪掉。」 | 0 | 0 | 第一句只查看沒動手；第二句 kb trash 做完 |
| D 明說用 kb source-edit trash | 0 | 0 | 做完 |
| E（加測）庫外硬用 `rm`（「不要改用別的方式」） | 0 | 0 | **直接 `rm` 刪成功，沒有先留一份**，事後 AI 自己說救不回來 |
| F（加測）庫內硬用 `rm` | 0（auto mode）；**守門擋 1 次**（deny，「改用 kb source-edit trash」） | 0 | 沒刪；AI 說遵守「不要用別的方式」而停下，還先 cp 了一份到 claude 自己的暫存夾 |
| G（加測）庫外 `rm -rf` 整夾 | 0 | 0 | AI 自己改成 kb trash 整夾進資源回收筒（沒照 `rm -rf`） |

- 守門放行的刪除（`kb source-edit trash`）：auto mode **完全不擋**。
- 刪除是真的進了 Windows 資源回收筒。
- 這次樣本小（每情境 1 次），沒有看到 auto mode 擋過任何東西，**也就沒測到「連續擋到門檻改問人」那條路**。

**結論**：D-352 擔心的「auto mode 常擋她明說要刪的」在這 7 個情境沒發生，重談條件沒觸發。
**對設計的影響**
- 兩層分工的實際樣子：庫內由守門擋 `rm`、引導 AI 改用 kb trash；庫外的 `rm` **守門不管、auto mode 也放行**（E）。D-352 代價段說「守門不管的知識庫外救不回來的沒人擋」其實確實發生了：只有 AI 自己遵守 plugin 規則（A、B、G）時才安全，被硬指定 `rm` 時（E）庫外檔就直接沒了。要不要在守門補擋庫外的 `rm`（D-352 重談條件寫的補法），是設計決定，這個 spike 的數字支持「要補」。
- 「連擋 3 次或共 20 次改問人」的機制沒被觸發過，spec 要另外找辦法測（例如叫 AI 做 auto mode 一定擋的動作，如對外網站寫入／上傳）。

## 5. 排程（D-356）

**做了什麼**：`mktask.py`（照 `scripts/kb/_lib/schedule.py` 的 XML：TimeTrigger＋LogonTrigger、各自 Repetition PT1M、InteractiveToken、LeastPrivilege、IgnoreNew，只把 ExecutionTimeLimit 改成 PT0S），`schtasks /create /xml`，名稱 `wiki-with-willy-spike\伺服器測試`；動作 `pythonw fake_server.py`（每 10 秒寫一行 `紀錄\心跳.txt`，綁 127.0.0.1:47831 當鎖，第二個實例會寫「第二個實例，退出」並離開）。

**看到什麼**
- 建立成功，不用管理員。第一次起來在建立後約 1 分鐘（17:52:41）。
- **不會開第二個**：排程每分鐘觸發，18 分鐘內心跳檔裡「第二個實例」出現 **0** 次（IgnoreNew 在排程層就擋掉，連腳本都沒被開）。
- **殺掉後重起**：17:54:04 強制結束行程，17:54:41 新行程（新 pid）自己起來，**37 秒**（等下一個整分鐘觸發）。最長約 60 秒，跟 D-356 寫的「最多 1 分鐘」一致。
- **超過 15 分鐘沒被停**：同一個行程 17:54:41 一直跑到 18:12 我手動結束（17 分鐘以上），沒被排程停掉（PT0S 有效）。
- 沒用 `/ru SYSTEM`、沒要管理員密碼；視窗因為 pythonw 沒有出現。
- 「更新後自動登入」（Windows 設定 → 帳戶 → 登入選項 → 「使用我的登入資訊，在更新後自動完成設定」）：這台（Windows 11 家用版）查 `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon`：`ARSOUserConsent`、`DisableAutomaticRestartSignOn`、`AutoAdminLogon` 都沒有值，`UserARSO` 子機碼也沒有。**沒有值不代表開或關**（預設值看版本），所以**查不到現在是開是關**；要看設定頁。BitLocker 狀態需要系統管理員才查得到，我沒有查。
- 官方文件條件我只做了一般搜尋、沒有逐頁驗證，不寫成確定的：已知會受影響的是需要 PIN 的 BitLocker／裝置加密、公司或學校用 Intune／群組原則管理（`DisableAutomaticRestartSignOn` 之類的政策）、沒有設 Windows Hello／密碼的本機帳號、舊版 Windows 10（1903 前）沒有這個選項。**要人到那台像客戶的電腦上看設定頁、再做重開機實測。**
- 清理：已刪除測試工作，`schtasks /query` 找不到，假伺服器行程已結束。

**結論**：D-356 第 1 點（登入時起＋每分鐘、IgnoreNew、不設時間上限、掛了 1 分鐘內自己起來）實測成立。重開機接續是否有效沒測。
**對設計的影響**：重起延遲是「下一個整分鐘」，平均約 30 秒、最長 60 秒；D-356 第 2 點「升級時小伺服器自己退出，1 分鐘內用新版起來」成立。小伺服器自己要綁一個鎖（port 或 lock file），不要只靠排程，因為手動開一個再加排程開的，排程不知道（IgnoreNew 只看它自己開的那個）。

## 6. Cloudflare（D-357，只查文件）

- **免費方案能不能加成員**：官方說「with every Cloudflare plan, you can add multiple members to your account and assign them a variety of roles」（Roles 文件與 RBAC for every plan 的說明）；邀請要有 Super Administrator 角色且信箱已驗證。我沒查到免費方案的成員數上限。→ D-357 的「免費版加不了成員」重談條件**沒觸發**。
- **角色**：帳號層級角色很多（官方 Roles 頁）：Administrator、Super Administrator、Administrator Read Only、Analytics、API Token Provisioning、Audit Logs Viewer、Billing、DNS、Cloudflare Access、Cloudflare Zero Trust、Cloudflare Zero Trust Read Only、Minimal Account Access…。另有「資源範圍」角色 **Cloudflare Access App Admin**（只給某一個 Access 應用的完整權限，我搜尋到、頁面全文沒逐字核對）。服務人員被加成員用「Cloudflare Access」或「Cloudflare Zero Trust」＋DNS 這類較小的角色就行，不必給 Super Administrator（但要邀請別人的人是她，她本來是 Super Administrator）。
- **API 權杖能不能只改某一個 Access 應用的名單**：**文件沒說，我查不到**。權限清單（`developers.cloudflare.com/fundamentals/api/reference/permissions/`）是帳號層級：「Access: Apps and Policies Edit」（也有 Write）、「Access: Policies Edit」、「Access: Apps Edit」、「Access: Groups Edit」、「Access: Apps and Policies Read」。頁面沒說權杖能縮到單一應用或單一 policy（只明講 AI Gateway 不能縮到單一 gateway）。**最小的確定組合：帳號層級「Access: Policies Edit」（若只改 policy）加「Access: Apps and Policies Read」；不確定時用「Access: Apps and Policies Edit」，範圍是這個帳號，不能只縮到一個應用。**可能的縮小辦法（要實測才確定）：把名單做成 Access「Email list／Group」，權杖只給 Groups Edit，policy 引用那個 group，這樣權杖改不到其他設定。
- **API 怎麼加減信箱**：更新 policy 用 `PUT /accounts/{account_id}/access/apps/{app_id}/policies/{policy_id}`（文件只列 PUT，沒有 PATCH）；body 的 `include` 是 OR 的規則陣列，信箱規則是 `{"email": {"email": "a@x.com"}}`；也可用 `email_domain`、`email_list`（引用先建好的 email list 的 id）。因為是 PUT，加減一個信箱要**先 GET 目前名單、改完整個陣列再 PUT 回去**，不能只送差異。
- **Access 登入有效期最長多久**：應用的 session duration 範圍「從立刻逾時到一個月」，預設 24 小時。→ D-357 寫的「登入有效一個月」是最大值，要設到最大。

**對設計的影響**：D-357 第 2 點「一把只能改名單的權杖」要改成「**帳號層級、只給 Access 相關編輯權限的權杖**」，不能保證只能動一個應用，要在 spec 說清楚，或改採「名單放 Group／Email list、權杖只給 Groups Edit」並實測。

## 7. 手機存資料（D-358，只查文件）

- **iPhone Safari（一般網頁）**：WebKit 的 ITP 規則（webkit.org「Full Third-Party Cookie Blocking and More」）：瀏覽器內，網站 7 天的 Safari 使用期間沒有使用者互動，就清掉它的 script 可寫儲存（IndexedDB、LocalStorage、SessionStorage、Service Worker 註冊與快取；沒有單獨提 Cache Storage，但 Service Worker 的快取一起算）。**所以一週沒打開，排隊的資料會被清。**
- **加到主畫面（Home Screen web app）**：同一篇文章說它不屬於 Safari，**自己算使用天數，實際使用就重新計時，「WebKit 不打算刪第一方資料」**。web.dev 也寫「這個上限不適用安裝到主畫面的 PWA」。Safari 17 儲存政策（webkit.org/blog/14403）：主畫面網頁與瀏覽器 app 的配額相同。→ **加到主畫面有差，而且有利**；D-358 重談條件「iPhone 常清掉排隊的資料」，只要引導她加到主畫面，風險大幅降低。
- **容量**：Safari 17 起，瀏覽器 app 單一來源最多約磁碟的 60%、全部來源約 80%；其他 app（含主畫面網頁）單一來源 15%、全部 20%（我讀到的 WebKit 文章對主畫面網頁寫法與 web.dev 不完全一致，數字不要當確定）；超過會拋 QuotaExceededError、可能被依最近最少使用整個來源清掉；`navigator.storage.persist()` 可申請不被清（WebKit 看是不是主畫面網頁等條件決定給不給）。排隊的資料（文字、日期、幾張照片）遠遠用不到。
- **Android Chrome**：沒有 7 天這種規則；配額是磁碟的一定比例（一個來源最多約 60%），儲存空間不足時才依最近最少使用清整個來源，除非申請了 persistent storage（`navigator.storage.persist()`，Chrome 會依使用頻率、是否已安裝、書籤等決定給不給）。
- **背景同步（主機開了自動送出排隊的）**：caniuse 顯示 Background Sync API **iOS Safari 全版本不支援**（3.2～27.2 都沒有）；Chrome Android 支援。→ iPhone 做不到，只能在她**打開網頁時**把排隊的送出（Android 可用，但建議兩邊同一套邏輯：打開就送）。

**對設計的影響**：D-358 要補：(1) 手機要引導「加到主畫面」才可靠；(2) 排隊送出只能做成「打開網頁、主機連得到時送」，不要靠背景同步；(3) 畫面上「還有 N 件沒送出」的提示在 iPhone 若一週沒用，要意識到可能已被清掉。

---

## 要人做的

1. 在一台像客戶的 Windows 電腦（最好是 Windows 11 家用或專業版、有 Microsoft 帳號登入、沒公司管理）上開「設定 → 帳戶 → 登入選項」，記下「使用我的登入資訊，在更新後自動完成設定」是開還是關；若是灰的或沒有，記下這台的 Windows 版本與有沒有 BitLocker／裝置加密。
2. 把它打開，照 `mktask.py` 建一個測試排程（或在跑 `mktask.py` 後）執行 `shutdown /r /t 0` 手動重開機，重開後看停在登入畫面還是自動登入並鎖畫面（正常的更新重開機才會用到這個開關，手動 `shutdown /r` 是否也套用要實測；也可用 Windows Update 真實更新重開來測）。
3. 回來後看 `紀錄\心跳.txt` 有沒有在重開後約 1 分鐘內開始新的心跳行（沒登入時應該沒有，鎖畫面登入後應有）。
4. 測完用 `schtasks /delete /tn "wiki-with-willy-spike\伺服器測試" /f` 刪掉測試排程。
5. 到 Cloudflare（真的免費帳號）：建一個測試帳號、邀請第二個信箱成員（確認免費方案真的能邀）；建一個 Access 應用與 Group，建只給「Access: Groups Edit」的權杖，試能不能只改名單、能不能動到別的應用（回答第 6 項的不確定）。
6. 用一支 iPhone 把網頁加到主畫面、存一點 IndexedDB 資料、不打開 8 天以上，再打開看資料還在不在（確認第 7 項；也要測沒加到主畫面的 Safari 分頁當對照）。

## 花了多少

- `claude` 行程啟動次數：**17 次**（t1a 1、t1b 1、t1c 1、t1d 4、t1e 1、t2 1、t3 1、t4 共 7）。每次都是短句；總共約送出 30 句訊息。
- 大約 token：每個新程式啟動約 13k 寫入＋30～180k 快取讀取（讀取便宜）；全部加起來約：新寫入 ≈ 17 次 × 13k ≈ 22 萬 token＋t2 讀大檔 2.8 萬＋各句零星，輸出總共不到 5k。快取讀取約 150～200 萬 token（便宜，主要是每句重讀同一段）。
- 沒有用 `--bare`、沒設 `ANTHROPIC_API_KEY`（跑前確認是空的）。

## 副作用與清理

- `kb init` 這個指令自己說：「上層的 Obsidian 資料夾（llm-wiki-test）的首頁外掛也換成這一版」，所以它改了 `C:\Users\Jie\Desktop\llm-wiki-test\.obsidian\` 底下的外掛檔與 `community-plugins.json`（那個夾是之前測試用的 vault 上層，在 spike 夾**之外**，不是我主動改的，是 `kb init` 的行為）。這是 repo 行為，設計上要注意：在別人的上層 Obsidian 夾裡 init 會動到它。
- 測試中 AI 在 claude 自己的暫存夾（`%TEMP%\claude\C--Users-Jie-Desktop-llm-wiki-test----spike----`）留了一份假檔6複本；我已刪除該夾。
- spike 夾內建立與被刪的假檔：`外面\外假1.txt`、`外假2.txt`、`子夾\`、`知識庫\原檔\假檔3～5.txt`（進資源回收筒）。
- 沒碰 repo、沒 commit、沒 push、沒裝 plugin、沒改使用者設定、沒重開機、沒登入 Cloudflare。

## 腳本清單（都在 spike 夾）

`cc.py`（stream-json 小工具）、`t1a.py`～`t1e.py`、`t2.py`、`t3.py`、`t4.py`、`fake_server.py`、`mktask.py`、`看.py`（讀紀錄）；`紀錄\` 夾有各次 `.jsonl`（每個事件一行）、`.out`、`心跳.txt`、`claude-次數.txt`。
