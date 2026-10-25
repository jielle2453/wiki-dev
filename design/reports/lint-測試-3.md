# lint（健檢）與待處理的問法 — 測試報告（第三輪）
> 代號說明（2026-10-25 補）：T-1～T-40 是 lint 測試的發現，五輪接續編號（第一輪 T-1～T-24，第二輪 T-25～T-32，第三輪 T-33～T-37，第四輪 T-38，第五輪 T-39、T-40）；後面幾輪的報告也會提到前面的 T 編號。驗收 N 指 lint spec。

日期：2026-10-25
給誰看：設計 session（決定哪些發現回實作修、哪些記 backlog；結案時填 spec「紀錄」的測試報告欄）。
何時更新：同一輪重跑時重寫該節；實作再修之後在文末加一節。

對象：第二輪報告 `design/reports/lint-測試-2.md`（51377fa）的修正，範圍 `51377fa..5a8ae8c`（單一實作 commit）。
環境：Windows 11、Git Bash、Python 3.14、Claude Code 2.1.310。worktree `C:\Users\Jie\Desktop\llm-wiki-j-lint`，分支 `spec/lint`，HEAD `5a8ae8c`。
做法：只執行與讀檔，不改程式。第二輪的重現步驟照原樣在新 HEAD 再跑；T-25 用真的 `folders exclude --kind hidden` 端到端。code review（高強度）一個獨立子代理；它的發現我逐條自己重現或標明讀程式。

## 結論

**T-26、T-27、T-28、T-29、T-30、T-31 修好；T-25 只修了一部分。** 另外修正本身帶出 4 個新問題（T-33～T-36）。沒有擋發行的項目，但有一項會影響幾乎每個舊知識庫（T-35），建議在進桌面版確認前修掉，所以**這一輪我不寫「可以進桌面版確認」**；T-33～T-35 修完、重驗這三條，就可以。

| # | 嚴重 | 問題（短） | 已重現 |
|---|---|---|---|
| T-33 | 應修 | purge 清不到 `pending.json` 的 handedit 件 `diff.other` 裡的**檔名**（她在那行後面加字就會變成 `other`） | 是 |
| T-34 | 應修 | purge 沒清到「衍生文字」的幾個副本：`.system/handedits/` 的那份、回合夾裡 `pending.json` 與 `待處理.md` 的舊版、健檢報告（推測日程原文、裸檔名）；`renders.json` 的 `asks` 同理（code review） | 是（前三處） |
| T-35 | 應修 | 沒有 `.system/skeleton.json` 的知識庫（0.21.0 之前建的、`kb init` 與 `kb upgrade --finish` 都不補它），健檢永遠說「版本與骨架這項這次沒查成」，一句話永遠帶「有 1 項這次沒查成」，`hook-errors.log` 每次一行，該項的數字（舊 schema、舊範本）也不報 | 是 |
| T-36 | 應修（低） | T-29 的 bases 在 `versions revert` 之後不對：退回後她再手改，被退掉的件被報成「她刪掉的」（編號已不存在） | 是 |
| T-37 | 低 | 讀程式（code review）：purge 的 `_derived` 沒存進 `purge-pending.json`，鎖逾時沒清完、重跑時衍生文字永遠清不到；`gone` 把留著的 confirmed 日程也算進去；`cleared` 讓「暫時讀不到」的項目把她答過的件記成消失；purge 套 `words` 改了 `bases` 但 md 沒變 | 否 |

全套測試：3038 個、跳過 2、exit 0。`claude plugin validate .` exit 0（只有 ICON_MISSING 與 README 沒安裝句的建議，與前兩輪相同）。

## 第二輪修正逐條

| 編號 | 結果 | 證據 |
|---|---|---|
| T-25 | **部分修好** | 端到端（`客戶案件/私人/日記本.txt`，掛卡「王家心情」，一個從那張卡推測的日程「寄機密合約給老王」，待處理有「日記本.txt 不見了」一件）：她在 `待處理.md` 把那行打勾（或刪掉），開出 handedit 件；`kb folders exclude 客戶案件/私人 --kind hidden` 之後：獨特字串、卡標題、夾路徑 `客戶案件/私人`、`私人` 都找不到（允許清單以外）；`pending.json` 的 handedit 件那行已整列拿掉（它指向被拿掉的條目）、`inferred:agenda` 件的 `text` 變「2026-11-14 （已排除）」、現行 `待處理.md` 與 `renders.json`（`bases`、`asks`、`saved`）找不到卡標題與夾路徑；`kb lint handedit --json` 回 `checked/removed/other` 全空。**但是：** ①她在那行後面加字（`other`）→ `pending.json` 仍存「「日記本.txt」（（已排除））不見了…這個我自己處理」，檔名還在，`kb lint handedit --json` 照唸（T-33）；②`.system/handedits/<時間>-待處理.md`（她那份的副本）、`.system/versions/<回合>/files/.system/pending.json`、`…/files/系統/待處理.md`、`系統/健檢報告/<月>.md` 仍找得到「寄機密合約給老王」，handedits 那份也留著裸檔名「日記本.txt」（T-34）。 |
| T-26 | 修好 | `guard_stale`：條件一直在、dismiss 後連跑 → 不重開；`guard_setup` 改成守門正常 → 該件記 `cleared`（日期）；守門又壞 → 開新的一件（`dismissed` 那件留著、新的 `open`）。項目沒跑成（刪 `.system/journal/`，`守門` 進 `failed_checks`）→ 沒記 `cleared`；日誌回來、條件一直在 → 仍不重開。 |
| T-27 | 修好 | `data.dates` 明天的 lint 件：`kb pending set-aside <p-…>` 與 `kb asks set-aside <p-…>` 輸出逐字相同（「這件快到期了，沒辦法先放著：明天到期的事」＋兩項答法，exit 3）；`--json` 同形狀（`refused`、`ask.results`）；非時間性的兩條都可放著、`kb pending back` 拿得回；`agenda.json` 寫壞時 `kb asks set-aside <非時間性 p-…>` 仍成功（不再跑 `cards.todo`）；不存在的 id：pending 那條「沒有這件待處理」、asks 那條「沒有這個問題」，與第一輪相同。 |
| T-28 | 修好（但見 T-35） | 四種各自在一個有四件 open 的庫裡弄壞：`agenda.json` 寫壞 → `failed_checks: ["推測放太久"]`；刪 `skeleton.json` → `["版本與骨架"]`；刪 `.system/journal/` → `["守門"]`；`profile.json` 寫壞 → `["設定檔改了之後的卡", "推測放太久"]`；四種都是「開著的件變化 []、open 數 4→4」（沒有被關）。全新 `kb init` 的庫（沒有任何對話、沒有 guard-status）第一次 `kb lint`、以及真的 `hooks/session.py` 開場觸發的背景健檢：`failed_checks: []`、`hook-errors.log` 不存在。 |
| T-29 | 修好（但見 T-36） | 甲件她打勾 → 存檔失敗（`renders.keep` 丟 `OSError`）時加乙件 → 恢復後加丙件：`kb lint handedit --json` 只有 `checked` 甲，`removed`、`other` 都空。`renders.json` 的 `bases` 只有 `待處理.md` 一份（217 字）。 |
| T-30 | 修好 | `file:///%5C/server/share/x.pdf`、`file:///%2F%5Cserver/share/x.pdf`、`file://///server/share/x.pdf` → `os.path.exists` 都沒被叫（spy）、不產生 finding；`file:///C:/不存在/x.pdf` 仍被查並標壞連結。 |
| T-31 | 修好 | 一條提到卡標題與夾路徑的口述收回後被健檢封存 → exclude hidden 後封存檔裡的原話是「王家心情那張卡寫的事要小心，日記在 （已排除）」（標題留著、路徑換掉，restore 回來是通順句）；強迫 `renders.json` 的鎖被占住 → `還沒清完：狀態檔 1 個；關掉開著的檔再跑一次 kb folders purge 客戶案件/私人`（`purge-pending.json` 還在），鎖放開再跑 `kb folders purge` → 「清好了」。（鎖逾時等待加起來 211 秒，只在這種故意卡鎖的情況。） |

## 受影響的驗收重跑（新 HEAD）

| # | 結果 | 證據 |
|---|---|---|
| 3 | 過 | 守門這週擋 3 次（上週 1）、最後一次跑 2026-10-21、`guard_stale` 一件，再跑不重複。 |
| 4 | 過 | 40 天前的推測日程與推測實體 → 兩件，再跑不重複；10 天前的不列。 |
| 5 | 過 | 改過的 `CLAUDE.md` → 一件；resolve 後不重開；又改才再開。（這個庫是 `skeleton.record` 過的。） |
| 14 | 過 | 31 天 → `by: lint`；`kb pending set-aside` → `by: customer`；`data.dates` 明天的有時間性不能放著，十天後與五天前的可放著且健檢不拉回；掛了清冊檔的件，檔改內容後 `kb inventory scan`、`kb lint` → 拉回。 |
| 18 | 過 | 手改 `待處理.md`（打勾、刪行）→ handedits 存她那份、`handedit` 件、`checked/removed` 正確；`kb lint handedit` 人讀「打勾 1 條、刪掉 1 條」。 |
| 21 | 過 | 報告格式、摺疊段、先放著超過一個月、同月只一個檔、重跑內容一致。 |
| 22 | 過 | `rulings.json` 寫壞 → exit 0、`failed_checks` 其他項照跑、報告每項一句、log 一項一行。（此夾具庫沒有 `skeleton.json`，所以多一項「版本與骨架」，見 T-35。） |

## 對修正做 code review 的重點

- **T-29 bases**：沒漏進 purge（`renders.json` 的 `bases` 在 purge 時套 `words`，端到端驗過找不到標題與夾路徑）；不會長太大（只存 `待處理.md`、`日程.md`、`裁示.md` 三份，每份取代不累加；我造 400 件待處理：`待處理.md` 49 KB、`renders.json` 123 KB、每次新增 7 毫秒）；`renders.json` 被刪或壞掉會退回舊的重算路徑，不比以前差；**但跟磁碟上的 md 對不上的情況（退回）會誤判**（T-36）。
- **T-26 cleared**：三個條件我都驗了（見上）；`ctx.synthesis()`／`ctx.cards()` 略過讀不了的檔卻仍算跑成功的殘留見 T-37。
- **T-28**：新建庫與四種讀不到都對；**反向——合法缺檔——有一個漏**：沒有 `skeleton.json` 不是壞（T-35）。沒有 `agenda.json`、沒有 `profile.json` 是合法缺檔（用空的／預設），不會誤判沒查成。
- **T-27**：兩條 set-aside 同一句、p- 路徑不跑整理；`pending.json` 壞掉時由外層攔成「狀態檔讀不到」。

## 新發現

編號接 T-33。

### 應修

**T-33　purge 清不到 `pending.json` handedit 件 `other` 行裡的檔名**（已重現；code review 中 1）
- 位置：`scripts/kb/_lib/purge.py` `_derived`（檔名只從 `inventory.load()` 的 entries 取）。
- 原因：`folders exclude --kind hidden` 在 purge 開始前就已經把那些 entries 從清冊拿掉，`_derived` 跑到時是空的，檔名永遠進不了 `derived`。現在擋得住的只有打勾、刪行（那種 diff row 靠 `gone`＝待處理編號整列拿掉）。
- 重現：她在 `待處理.md` 的「「日記本.txt」（客戶案件/私人）不見了…」那行後面加「這個我自己處理」→ 開出 handedit 件，該行進 `diff.other`；`exclude --kind hidden` 後 `pending.json`：`'other': ['- 2026-10-25 「日記本.txt」（（已排除））不見了。…這個我自己處理']`，`kb lint handedit --json` 照樣回這行。（`file_label` 把檔名和夾名分開寫成「「名」（夾）」，路徑遮罩只換得到夾。）
- 建議：`derived` 也收被 drop 的 pending 條目 `text` 裡的檔名，或 exclude 前先記。
- 嚴重度：應修（同 T-8 的承諾）。

**T-34　purge 沒清到衍生文字的幾個副本**（已重現；code review 中 2）
- 位置：`purge.py` `_lint_files` 的 `texts()`（遮 `.system/handedits/*`、`系統/健檢報告/*` 只用 `words`）、`_scrub_row`（遮回合夾舊版只用路徑遮罩）；`derived`／`gone` 只用在目前的 `pending.json`（`_mask_pending`）。
- 重現（上面 T-25 的庫）：purge 後這幾處仍找得到「寄機密合約給老王」（從被排除的卡推測出來的日程原文）：`.system/handedits/<時間>-待處理.md`（她那份的副本，另外還留著裸檔名「日記本.txt」）、`.system/versions/<purge 回合>/files/.system/pending.json`、`.system/versions/<purge 回合>/files/系統/待處理.md`、`系統/健檢報告/2026-10.md`（「要你決定的」段）。code review 另用 `set_asks` 塞帶檔名的問句，`renders.json` 的 `asks` 與現行 `待處理.md`「整理時要問你的」段也留著（我沒另外重現這一個）。
- 違反 `test_lib_purge.test_whole_flow` 自己定的「檔名只准留在 prompt 位置」。
- 建議：`derived` 的字詞也套在 handedits 副本、健檢報告、回合夾裡 `pending.json`／`待處理.md` 的舊版。
- 嚴重度：應修。

**T-35　沒有 `.system/skeleton.json` 的庫，健檢永遠「版本與骨架沒查成」**（已重現；code review 低 4）
- 位置：`scripts/kb/lint/checks/versions.py`：`if rec is None: raise ValueError(…讀不到)`（T-28 的修法，沒有紀錄也當讀不到）；`kb init` 只有「這次從骨架建出來的檔」非空才寫 `skeleton.json`，`skeleton.reconcile` 對「她改過、新版沒改」的檔不記指紋。
- 重現：一個沒有 `skeleton.json` 的庫（0.21.0 之前建的庫就是這樣，我的夾具庫也是）→ `kb lint --json`：`failed_checks: ["版本與骨架"]`、一句話「有 1 項這次沒查成。」、`hook-errors.log` 每次一行「出錯：ValueError: .system/skeleton.json 讀不到」；**`kb init <庫>`（「已是知識庫，補齊了 1 項」）與 `kb upgrade --finish`（「已經是 0.21.0」）跑完都沒建出 `skeleton.json`**，再 `kb lint` 一樣。該項同一輪的數字（`old_schema`、`old_template_cards`）整個不報。對照：全新 `kb init` 的庫有 `skeleton.json`，沒這個問題。
- 後果：幾乎所有 0.21.0 之前建的客戶知識庫，健檢永遠不會說「一切正常」、報告永遠有一行沒查成、log 每週一行，而且客戶端沒有任何修復動作。
- 建議：沒有 `skeleton.json` 時跳過骨架比對、後面的數字照出；只有 JSON 壞掉才丟例外。（或 `kb init`／`--finish` 沒紀錄時補寫一份空的。）
- 嚴重度：應修（影響面最大）。

### 應修（低）

**T-36　T-29 的 bases 在 `versions revert` 之後不對**（已重現；code review 低 3）
- 位置：`renders.py` `base`／`record`；呼叫端 `pending.py`、`agenda.py`、`rulings.py`。`renders.json` 不備進回合，所以 `kb versions revert` 把 `pending.json` 與 `待處理.md` 換回舊版時，`bases` 還是最新那份。
- 重現：加甲乙丙（回合一），再加丁戊（回合二）→ `kb versions revert`（md 回到三件）→ 她在 md 把甲打勾 → 再加己件 → `kb lint handedit --json`：`checked` 甲 ✓、**`removed` 丁、戊**（這兩個編號早已不在 `pending.json`）。第二輪（改前，用現行資料重算 base）沒有這個問題。
- 後果：AI 照單對不存在的編號下指令（得到「沒有這件待處理」，不會壞資料，但會困惑）。
- 建議：取 base 前核對它跟磁碟上 md（退回後是 history 裡的某一份）的關係，對不上就退回重算；或 revert 後重記。
- 嚴重度：應修（低）。

### 低優先

**T-37　讀程式發現（code review，未重現）**
- `purge._derived` 在 `purge()` 開頭、拿掉條目之前才算，沒像標題那樣存進 `purge-pending.json`：第一次 `pending_texts` 因鎖逾時失敗、回報沒清完，重跑時日程與待處理條目早已拿掉，`derived` 與 `gone` 是空的，handedit 與健檢件的衍生文字永遠清不到。
- `_derived` 的 `gone` 把 `origin.card ∈ ids` 的所有日程都算進去，包括 confirmed／corrected 的（`drop_agenda` 只清它們的 `origin`、條目留著）；她對這種條目在 `日程.md` 打勾產生的 handedit row 會被整列拿掉，她的指令就消失。
- `pending.close_lint_gone` 的 `cleared`：`ctx.synthesis()`／`ctx.cards()` 略過讀不了的檔卻仍算 `ran`，`synthesis_big:*` 等條件暫時消失時，她 dismiss 過的件也被記 `cleared`，檔案恢復讀得到就重開（原本只會誤關 open 的件；T-28 同一類殘留）。`guard_stale` 本身會因「那天的對話沒用到工具」來回，dismiss 後可能隔幾天又出現。
- purge 套 `words` 改了 `bases[日程.md]`、`bases[裁示.md]` 的文字，磁碟上的 md 沒變；命中詞時下次她手改會讓被遮的行變 `other`／`removed`（待處理那份後面有 `pending_texts` 重寫，不受影響）。`renders.json` 手改壞成非二元組時 `for ln, i in …` 會拋 `TypeError`，不在 `except (OSError, ValueError)` 內。
- 都可留 backlog。

### 新測試的覆蓋（code review）
- `LintPending`、`test_lint_round2` 多半是真檔真 CLI，不是只測 mock。
- 沒測到：`other` 行含檔名（T-33）、`.system/handedits/` 副本、回合夾舊版、`renders.json` 的 `asks` 帶檔名（T-34）、purge 重跑（T-37）、`versions revert` 後的 bases 與 `日程.md`／`裁示.md` 的 bases（T-36）、反向的「合法缺 `skeleton.json` 不該算失敗」（T-35）。

## 沒測到的
- 觸發句與 D-132 新舊版對照（延到桌面版確認，同前兩輪）。
- 桌面版實際跑背景子行程；SMB／NTLM 實連；跨電腦同步。
- `plugin-dev:plugin-validator` agent（只跑了 `claude plugin validate`）。
- 第二輪列為 backlog 的 T-12、17、18、21、23 與 code review #11、#12、#17。

## 全部測試
`python -m unittest discover tests`：3038 個、跳過 2、exit 0（712 秒），跟 3a 的結果一致。`claude plugin validate .` exit 0。
