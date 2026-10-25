# lint（健檢）與待處理的問法 — 測試報告（第二輪）
日期：2026-10-25
給誰看：設計 session（決定哪些發現回實作修、哪些記 backlog；結案時填 spec「紀錄」的測試報告欄）。
何時更新：同一輪重跑時重寫該節；實作再修之後在文末加一節。

對象：第一輪報告 `design/reports/lint-測試.md`（c84a8bb）的修正，範圍 `c84a8bb..f6a8c10`（單一實作 commit）。
環境：Windows 11、Git Bash、Python 3.14、Claude Code 2.1.310。worktree `C:\Users\Jie\Desktop\llm-wiki-j-lint`，分支 `spec/lint`，HEAD `f6a8c10`。
做法：只執行與讀檔，不改程式。第一輪的重現步驟照原樣在新 HEAD 再跑一次（真的 `kb` 指令、暫存知識庫、真的 hook 與子行程），T-5、T-6、T-8 這輪做出端到端。code review（高強度）一個獨立子代理，範圍 `c84a8bb..f6a8c10`；它的發現我逐條自己重現後才列「已重現」。

## 結論

**第一輪要驗的每條都修好了**（T-1～T-9、T-10、11、13～16、19、20、22、24、UNC 不查、手改留下那份遮值），T-4 照 D-226 補的裁定做對。受影響的驗收 4、5、9、14、16、18、19、21、22 重跑全過。沒有擋發行的項目。

修正本身帶出新問題，應修 5 項（T-25～T-29），低優先 3 項（T-30～T-32）：

| # | 嚴重 | 問題（短） | 已重現 |
|---|---|---|---|
| T-25 | 應修 | purge 清不到 `pending.json` 裡 handedit 件夾帶的整行文字（檔名、夾路徑、卡標題） | 是 |
| T-26 | 應修 | 沒有 `items` 的健檢件（守門、備份夾、捷徑、綜合卡過長、升格、重做）她 dismiss 過後，條件消失再復發永遠不重開 | 是（`guard_stale`） |
| T-27 | 應修（低） | `kb pending set-aside <p-…>` 沒擋有時間性的件，成功句照說「先放著了」，那件其實照列、下次健檢拉回 | 是 |
| T-28 | 應修（低） | T-1 自動關件會被「檢查讀不到資料但沒丟例外」誤關（agenda.json 壞、skeleton.json 不見、日誌不見、profile.json 壞），而且該項仍算跑成功 | 是 |
| T-29 | 應修 | T-10 修法的副作用：存檔失敗那次進 JSON 沒進 md 的件，下一次存成功時被報成「她刪掉的」 | 是 |
| T-30 | 低 | UNC 防護可用混合斜線繞過（`file:///%5C/server/share/x.pdf`） | 是 |
| T-31 | 低 | purge 的兩個小洞：口述封存檔用卡標題遮，日後 `statement restore` 回來的原話會變壞句；`renders.json` 的遮罩失敗被吞掉、purge 照報清完 | 讀程式（code review），未重現 |
| T-32 | 低 | 升級上來的庫第一次會多開一點雜訊（舊版開的 lint 件沒 `fp`；`裁示.md` 表頭改字使手改過的檔多出一行） | 讀程式（code review），未重現 |

全套測試：3026 個、跳過 2、exit 0。`claude plugin validate .` exit 0（只有 ICON_MISSING 與 README 沒安裝句的建議，與第一輪相同）。

## 第一輪修正逐條

每條的步驟都是第一輪報告裡的原步驟，在新 HEAD 重跑。

| 編號 | 結果 | 證據 |
|---|---|---|
| T-1 | 修好 | 同時開出 `redo_by_profile`、`guard_stale`、`inferred:entity`、`synthesis_big` 四件；`kb entity confirm`、guard-status 改成今天、`kb cards redo --ids`、綜合卡精簡後 `kb lint --json` → `done`「關掉 4 件已經不成立的待處理」，四件都 `done`、`how`「健檢確認已不成立」；再跑不重複 done。（`system_link`、`promote:*` 的關閉走同一支，`test_lint_round1` 守；我另驗了下面 T-28 的誤關面。） |
| T-2 | 修好 | `inferred:agenda` dismiss 後連跑兩次 `kb lint` 不重開；多一條推測日程後重開（fp 變）；兩條的 resolve 後把 agenda 順序反過來也不重開；`redo_by_profile` 說好、`kb cards redo --ids` 並 resolve 後不重開。殘留：沒有 `items` 的件見 T-26。 |
| T-3 | 修好 | 5 天前的推測日程 → `inferred:agenda` 件，`kb asks set-aside` 之後再 `kb lint`，`set_aside` 仍是 customer、`returned` 空；`kb asks --all` 只剩 `overdue` 那題 urgent，沒有這件。`data.dates` 明天的 → 健檢拉回（`returned` 今天）、十天後的與五天前的都留著。 |
| T-4 | 修好（asks 這條路） | 逾期日程 `kb asks set-aside <key>` → exit 3，第一行「這件已經過了日期，沒辦法先放著：做完了、不用了，還是改到哪一天？」接 1. 完成了 2. 不用了 3. 還沒，改到某天 4. 還沒，下次再問；`--json` 有 `refused` 與 `ask`（含 `results`）。`data.dates` 明天的 lint 件 → 「這件快到期了，沒辦法先放著：明天到期的事」接「1. 處理好了 2. 不用管」。非時間性的 `p-…` 與 `.system/set_aside.json` 的照舊可放著。`kb pending set-aside` 這條路沒擋，見 T-27。 |
| T-5 | 修好 | `unreadable` 件掛一張卡：卡的指紋行改成不是清冊現行的（舊卡等重做）→ 健檢後件仍 open；卡是現行的 → 關成「健檢確認已不成立」。（我造不出「真的換成有密碼的新版」讓清冊指紋改變，用改卡指紋行代替，走的是同一個 `card_state` 判斷。） |
| T-6 | 修好 | A 被 B 取代、B 收回，健檢把 A、B 封存（另一筆推算也封存）→ `kb entity rename 信義王 --to 信義王新名` → `statements-archive.json` 兩筆 `entities` 都換成新名；`kb statement restore A` → A 有效、`entities` 是新名。`merge` 同樣。推算封存檔的 `entities` 不改名：推算的實體名稱本來就靠 `entities.find` 轉成現在的名稱（`findings.py` 檔頭），現行檔也不改，不算缺陷。 |
| T-7 | 修好 | 同一個庫連跑三次 `kb lint --json`：`done` 第一次一句、第二、三次 `[]`；`month_done` 一條；`summary` 都是「這個月替你做了 1 件事」。 |
| T-8 | 修好（有一個洞，T-25） | 端到端：新增 `客戶案件/私人/日記本.txt`（內含獨特字串）、掛它的卡「王家心情」、一筆掛這張卡的推算被取代、一條提到那個路徑的口述收回，`kb lint` 把兩者封存、再手改待處理.md 觸發 handedit、`kb lint` 寫報告；`kb folders exclude 客戶案件/私人 --kind hidden`（會自己 purge）後整庫找：獨特字串 0 檔；夾路徑 `私人` 在允許清單（sources.json、journal、turns、versions/turn.json）以外 0 檔；推算封存檔 `findings: []`；口述封存檔的路徑換成「（已排除）」；`.system/handedits/` 那份的路徑與卡標題換成「（已排除）」；報告、`set_aside.json`、`lint.json` 沒殘留。**唯一還找得到的：`.system/pending.json` 的 handedit 件（T-25）。** |
| T-9 | 修好 | 名字 `x;calc` 的推測實體 → 件的 `do` 是 `kb entity confirm "x;calc"`（加了引號）。 |
| T-10 | 修好 | 把 `.system/handedits` 換成一個檔（`keep` 建不了夾）→ 手改的 `待處理.md` 沒被蓋掉、JSON 照寫、`hook-errors.log` 一行「她那份沒存成，這次不重寫」；移掉擋的檔後下一次寫入：handedits 存了她那份、`handedit` 件開了、md 重寫。日程.md 同樣不蓋。**但補對那次的差異不對，見 T-29。** |
| T-11 | 修好 | `待處理.md` 加 BOM + CRLF 另存不改字 → 下一次寫入不開 `handedit`。 |
| T-13 | 修好 | `.system/temp` 指到外面有 3 MB 檔的夾的 junction → 報告「知識庫 1 MB」（不再算外面的），`system_link` 照開。 |
| T-14 | 修好 | `renders.json` 的 `history` 型別錯（`{"系統/待處理.md": 5}`）→ `add_lint` 不丟例外；`lint.json` 的 `last_report: 5`、`last_counts: "x"` → 前台 `kb lint`、`kb lint --background` 都正常，log 沒東西。 |
| T-15 | 修好 | `last_background` 是 2099-01-01 → `runner.opening` 回 True 並開子行程。 |
| T-16 | 修好 | `rulings.json` 寫壞 → `summary`「有 4 項這次沒查成。」，不再說一切正常。 |
| T-19 | 修好 | `裁示.md` 表頭「怎麼用：要改跟我說，或在這裡刪掉一行。」「由程式產生；在這裡打勾或刪掉一行，我下次會照著做。」 |
| T-20 | 修好 | 補寫上個月報告：上上個月的 `report` 件已 `done`，報告「要你決定的」段不再列「…健檢報告出來了」，待處理 0 件。 |
| T-22 | 修好 | 預設庫把 19 列推測列日期改成 40 天前 → 沒有 `inferred:profile` 件；另加一列 AI 猜的卡型「尾款」、改過提示的「報價」卡型列、改過提示的第四節「案子」列 → 一件，`rows` 正好是這 3 列。判斷看內容不看標記，不會把她改過內容的列當預設；`profile.DEFAULT_SECTIONS` 等字串從 cdb4ae2 起沒改過，升級上來的庫的預設列內容一樣，不會被當成推測列誤報。 |
| T-24 | 修好 | 一件 `conflict`（卡不在）→ 同一輪 `done` 關掉它、`ingest.conflicts` 是 0。 |
| UNC 不查 | 修好（一般寫法） | 卡的 `開原檔: file://///evilhost/share/x.pdf` → `os.path.exists` 沒有被叫（spy 為證），不產生 finding；本機壞連結（`file:///C:/不存在的夾/x.pdf`）仍標「出處點不開」。混合斜線繞過見 T-30。 |
| 手改留下那份遮值 | 修好 | `待處理.md` 加兩行「銀行密碼: Abc12345secret」「api_key=sk-abcdef…」→ `.system/handedits/` 的那份、`pending.json`、`kb lint handedit --json` 的 `other` 都是 `███`，原字串 0 檔。 |

## 受影響的驗收重跑（新 HEAD）

| # | 結果 | 證據 |
|---|---|---|
| 4 | 過 | 40 天前的推測日程 + 推測實體 → 兩件、再跑不重複；10 天前的不列。 |
| 5 | 過 | 改過的 `CLAUDE.md` → 一件；resolve 後再跑不重開；又改一次才再開。 |
| 9 | 過 | 3 張報價卡、卡型那節日期新 → 一件 `redo_by_profile`（`data.ids` 對得上、`do` 是 `kb cards redo --ids …`）；跑它 → 「已標成要重做：3 張卡」「連帶要更新的綜合卡：信義王」、`stale` 3 張 `reason`「客戶說卡讀錯了」；第四節新 → `synthesis_fix`「設定檔改了」。 |
| 11（順帶） | 過 | 5 條裁示 → 升格件；4 條不列。 |
| 14 | 過 | 31 天 → `by: lint`；`kb pending set-aside` → `by: customer`、成功句；明天到期的拉回、十天後與五天前的留著；掛了清冊檔的件，檔改內容後 `kb inventory scan`、`kb lint` → 拉回；`待處理.md` 有「先放著的」段、處理完的不列、有逾期題時有「整理時要問你的」段。 |
| 16 | 過 | 2 件 about 信義王 + 4 件無關：`asks` 2、`others` 4、`others_line` 有句；同 session 再跑 null；新 session 又有；別名也認；明天到期的無關件進 `asks` 最前；`--all` 7 件、`set_aside` 件數、沒有 `others_line` 欄；`kb asks set-aside <key>` 成功、不存在 exit 3。 |
| 18 | 過 | 手改 `待處理.md`（打勾一條、刪一條）→ handedits 存她那份、`handedit` 件、`kb lint handedit --json` 分 `checked`／`removed`，`--done` 成功；裁示、日程、總目錄、工作日誌沿用第一輪結果不變（本輪手改遮值與 KEEP_FAILED 見上）。 |
| 19 | 過 | withdraw `--json` 有 `replaced`；`restore` 成功句；三種拒絕都是「這條沒有被取代，或取代它的那條還有效」exit 3。 |
| 21 | 過 | 報告格式、摺疊段、先放著超過一個月、沒內容的段不寫；同月只一個檔、重跑內容一致。 |
| 22 | 過 | 一項壞掉其他照跑，exit 0，`failed_checks` 四項，報告每項一句，log 一項一行；一句話現在是「有 4 項這次沒查成。」。 |

## 對修正做 code review 的重點（你問的幾條）

- **T-1 會不會關錯**：項目丟例外、或任何一個 finding 處理失敗，該項都不進 `ran`，所以不關（讀程式 + `test_lint_round1`）。**但「讀不到資料卻沒丟例外」的情況會關錯**（T-28，已重現）。
- **T-2 的 fp**：`items` 先 `sorted`，順序不影響（親測：agenda 反序後不重開）；件數變了會重開（親測：1 條變 2 條）；dismiss 過的在條件沒變時不重開。**沒有 `items` 的件 fp 恆定，答過就永遠不重開**（T-26，已重現）。`redo_by_profile` 排除已標 `redo` 的卡是對的（親測）。
- **T-8 purge**：新增那步全包在 `(OSError, ValueError)` 裡，失敗進 `left.state`，沿用既有的 pending／remaining 與冪等重跑；不備進回合的幾份（口述封存檔、lint.json、set_aside.json、handedits、報告）沒有把原文留進 versions；`word_titles` 已排除卡型名、實體名與兩字標題，沒看到新的誤遮；遮罩只用在 lint 自己的檔。漏的是 T-25（`pending.json` 裡的 handedit 件）與 T-31。
- **T-10 KEEP_FAILED**：下一次會補對（親測），但補對時的差異有誤（T-29）。
- **T-22 升級上來的庫**：見上表 T-22；判斷用內容比對，不依賴標記。

## 新發現

編號接 T-25。

### 應修

**T-25　purge 清不到 `pending.json` 裡 handedit 件夾帶的整行文字**
- 位置：`scripts/kb/_lib/purge.py` `_lint_files`／`_current_state` 的 `drop_pending`（只看 `file_ids`）；handedit 件沒有 `file_ids`。
- 重現：`客戶案件/私人/日記本.txt` 有張卡「王家心情」、待處理有一件「「日記本.txt」（客戶案件/私人）不見了…」；她在 `待處理.md` 把那行打勾，下一次寫入開出 handedit 件，`data.diff.checked[0].line` 存著整行（含檔名與夾路徑）；`kb folders exclude 客戶案件/私人 --kind hidden` 後，`.system/handedits/` 那份已換成「（已排除）」，但 `.system/pending.json` 的 handedit 件 `diff.checked[].line` 仍是原文：`pending.json after purge mentions diary/path: ['日記本.txt', '私人']`。`kb lint handedit --json` 會把這行唸給 AI。（`removed`、`other` 的行同。）
- 另外 code review：`inferred:agenda` 件的 `text` 列出推測日程文字，源自被排除的卡時，`drop_agenda` 拿掉日程本身但 lint 件副本留在 `pending.json` 與 `待處理.md`（讀程式，未重現）。
- 建議：`_lint_files` 加一步，handedit 件的 `data.diff.*.line`／`other` 與 lint 件的 `text`／`data.items` 照字詞遮。
- 嚴重度：應修（跟 T-8 同一個承諾）。

**T-26　沒有 `items` 的健檢件，她 dismiss／resolve 過後，條件消失再復發永遠不重開**（code review 中 2，`guard_stale` 親測）
- 位置：`pending.py` `_answered`、`runner.py` `_fp(f["items"])`。`guard_stale`、`versions_unwritable`、`system_link`、`synthesis_big:*`、`promote:*`、`redo_by_profile:*` 的 finding 沒給 `items`，fp 恆為 `_fp([])`；`close_lint_gone` 只關 open 的，答過的件沒有「已消失」記號。
- 重現：守門 6 天前才跑的庫 → `guard_stale` 開；`kb pending dismiss` → 守門好了（`kb lint`）→ 又壞了（`kb lint`）→ 件數仍是那一件 `dismissed`，沒有新的 open。服務人員看過一次、半年後守門再死，不會再提醒；`synthesis_big` 精簡後又長過上限、`system_link` 同。`redo_by_profile` 只帶前 200 張，她說好重做後超過 200 的那批 key 不變、fp 不變，永遠不再被提。
- 跟 `skills/lint/references/report.md` 新寫的「條件沒變下週不會再開，變了才會」不符。
- 建議：fp 納入 `file_ids`／`data` 的對象；或條件消失那一輪對已答過的件記「已消失」，復發算新事件。
- 嚴重度：應修。

**T-29　T-10 修法的副作用：存檔失敗那次進 JSON 沒進 md 的件，下一次存成功時被報成「她刪掉的」**（code review 中 1，親測）
- 位置：`pending.py:126`（`if handed != renders.KEEP_FAILED`）、同型 `agenda.py`、`rulings.py`。
- 重現：加甲件，她在 md 把甲打勾；`renders.keep` 改成丟 `OSError`，加乙件（md 保持她那份、JSON 有甲乙）；keep 恢復，加丙件 → `kb lint handedit --json`：`checked` 甲 ✓、**`removed` 乙**（`- 2026-10-25 乙件`，她從沒看過這行）、`other` 還多一行 `## 健檢查到的（1）`（標題件數對不上）。
- 後果：skill 叫 AI「照你改的處理」，會把她沒動過的乙件當成她刪掉的去 dismiss。
- 建議：KEEP_FAILED 那次把沒進 md 的件記起來（或下次比對用「上次實際寫進 md 的內容」當 base）；標題的件數行不比。
- 嚴重度：應修。

### 應修（低）

**T-27　`kb pending set-aside <p-…>` 沒擋有時間性的件**（親測；code review 低 4 同）
- 位置：`scripts/kb/pending_cli.py` `_aside`（沒有 urgent 檢查）；`kb asks set-aside p-…` 那條路有擋。
- 重現：`data.dates` 是明天的 lint 件：`kb pending set-aside p-…` → exit 0「先放著了：明天到期的事；有變化或快到期會再拿出來」；`kb asks set-aside p-…` → exit 3 拒絕。直接用 pending 那條，成功句騙人（`plan.visible` 對 urgent 照留、下次健檢 `due_back` 拉回）。skill 寫的是走 asks 這條，但兩條不一致。
- 另 code review：`asks_cli._set_aside` 把 `_collect`（跑 `cards.todo`）移到 `p-` 分支前，`p-` 路徑現在也會因任何一份狀態檔讀不到而回「狀態檔讀不到」exit 3，以前不依賴它。
- 嚴重度：應修（低）。

**T-28　T-1 自動關件會被「讀不到資料但沒丟例外」誤關，該項仍算跑成功**（親測；code review 中 3 同）
- 位置：`checks/inferred.py:51-52`（`agenda.load` 的 `ValueError` 當 `[]`）、`versions.py`（`skeleton.recorded` 回 None 就不判）、`guard.py`（日誌讀不到就沒有「最近的對話」）、`ctx.profile()`／`ctx.synthesis()`／`ctx.cards()` 略過讀不了的檔。
- 重現（各自在新庫）：①`inferred:agenda` 件 open → `agenda.json` 寫壞 → `kb lint` 的 `failed_checks` 是 `[]`、件變 `done`「健檢確認已不成立」；②骨架檔被改過開了 `skeleton:CLAUDE.md:…` → 刪 `.system/skeleton.json` → 件被關；③`guard_stale` 件 open → 刪 `.system/journal/` → 件被關。
- 後果：她對該件做過的先放著掉了、「替你做了」多記一句關件、資料修好後重開成全新的件，每次故障循環一次；不是丟資料。`profile.json` 壞時 `inferred:profile` 與全部 `redo_by_profile:*` 同理（code review）。
- 建議：這些讀不到的地方丟例外讓該項進 `failed`，或回「資料不可用」旗標讓 `_run_check` 不記入 `ran`。
- 嚴重度：應修（低）。

### 低優先

**T-30　UNC 防護可用混合斜線繞過**（親測；code review 低 6）
- `checks/citations.py:26` 只擋 `//`、`\\` 開頭。`file:///%5C/server/share/x.pdf` unquote 後是 `\/server/share/x.pdf`（`ntpath.splitdrive` 認成 UNC），`os.path.exists` 被叫了（spy 為證）；`file:///%2F%5Cserver/…` 同。先把 `\` 全換成 `/` 再判是否 `//` 開頭即可。
- 要 card-maker 被 prompt injection 寫出那種連結才碰得到。可留 backlog。

**T-31　purge 兩個小洞**（讀程式，未重現）
- `s_archive` 用卡標題當字詞遮被封存口述的原話；日後 `kb statement restore` 回來的就是帶「（已排除）」的壞句，跟「活的口述完全不遮」不一致。
- `purge.py` 的 `renders_json` 步驟：`renders._edit` 自己吞 `OSError`（只記 log），purge 看不到失敗，`renders.json` 的 asks 沒遮成時仍回報清完。
- 可留 backlog。

**T-32　升級上來的庫第一次會多開一點雜訊**（讀程式，未重現）
- 舊版開、她已 dismiss 的 lint 件沒有 `fp`，`_answered` 為假，會再開一次；`裁示.md` 表頭改字後，已安裝的庫若她手改過，`renders.diff` 的 base 是新表頭、她那份是舊表頭，`other` 多一行舊「怎麼用」，只改格式沒改條目也可能誤開 handedit。
- 影響是第一次升級那一輪，可留 backlog。

### 其他（供參考）
- code review：`statements.rename_entity` 失敗路徑沒收尾（封存檔壞時 `statements.json` 已改名、實體沒改，且封存檔改動沒進日誌「改了」）；`_refresh_asks` 與 `todo` 各跑一次 `ctx.collect()`（原本共用），大庫的健檢多一次全庫收集（`AFTER_UPKEEP` 的代價）。
- 第一輪列為 backlog 的 T-12、17、18、21、23 與 code review #11、#12、#17 這輪沒碰，沒重驗。
- 新測試 `tests/test_lint_round1.py`、`test_lib_purge.LintFiles` 多數碰真檔（`LintFiles` 是真的 `folders exclude` + `purge`）；沒測到的是 T-1 的吞錯誤情形（T-28）、T-2 的條件消失再復發（T-26）、T-10 的後續一致性（T-29）、`pending.json` 裡的衍生文字（T-25）。

## 沒測到的
- 觸發句與 D-132 新舊版對照（延到桌面版確認，同第一輪）。
- 桌面版實際跑背景子行程；SMB／NTLM 實連；跨電腦同步。
- `plugin-dev:plugin-validator` agent（只跑了 `claude plugin validate`）。

## 全部測試
`python -m unittest discover tests`：3026 個、跳過 2、exit 0（709 秒），跟 3a 的結果一致。`claude plugin validate .` exit 0。
