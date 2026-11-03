# 製作中（D-525）實作 review

日期：2026-11-03
審的是：commit a633029（`git show a633029`），claude -p Sonnet、high，一次完整 review（D-524 第 5 點）；花費 US$0.26。
plugin 驗證：claude -p Sonnet，PASS、錯誤 0、警告 2（card-maker 沒 `<example>`、hooks 語法檢查被擋沒跑；hook 測試已跑過），US$0.21。

## 實作 session 的處理

| # | 處理 |
|---|---|
| 1 指路卡的檔改了也印製作中 | 沒改；回報設計（常變的檔照 D-331，spec 沒說每句開頭怎麼分） |
| 2 短別名誤掛、封存實體 | 沒改；比法照 spec「同 lookup.mentions」；回報設計 |
| 3 沒登記的名稱 in_progress 空的 | 不改：find.md 第十節叫看 kb cards wip |
| 4 line_wip 逾時當天不補 | 沒改；回報設計（取捨） |
| 5 同一份同一個對話第二次改不再提 | 照 spec「同一份同一個對話只講一次」 |
| 6 按過停止 md 不印也不記鍵 | 審查本身說對，不改 |
| 7 裁定 6 的 --synced 可能讓綜合卡看起來整理到最新 | 沒改；照裁定 6 原文，回報設計請再裁 |
| 附 guard 白名單加 cards wip 用不到 | spec 可以動那列明列，照做 |

測試 session 只要看這份沒看到的地方。

## review 原文

審查完成。我只讀了 diff 和相關原始碼，沒改檔、沒跑測試。有 7 條，沒有看到會直接壞掉的錯，多半是行為對不上或邊界問題。

1. **`WIP_LINE` 的數量跟 `cards wip` 對不上。**
   - 位置：`hooks/_checks.py` 的 `change_lines`，對照 `scripts/kb/_lib/cards.py` 的 `wip`（約 L985–1010）。
   - 問題：`change_lines` 是照 quick scan 的 added／modified 數，只要不是 md 就算。`cards.wip` 是看 todo 的 new＋stale，會漏掉指路卡的檔（`pointer_changed`）、封存的、讀不到的、被型別規則略過的。
   - 後果：一份指路卡的檔改了，開頭會說「有 1 份製作中…問到讀原檔答」，但 `kb cards wip`、daily 的 `line_wip` 和 lookup 的 `in_progress` 都是空的。
   - 建議：spec 若要兩邊一致，`wip` 要補 `pointer_changed`，或把 `WIP_LINE` 的措辭放寬。

2. **`_wip_entities` 可能把檔誤掛到實體上。**
   - 位置：`cards.py` 的 `_wip_entities`，比法是 `k in stem`。
   - 問題：實體名或別名太短（例如單字、兩字別名）會出現在很多檔名裡。
   - 後果：不相干的檔會掛到那個實體，lookup 的 `in_progress` 就多列。
   - 建議：加最短長度，或別名要整段比對。
   - 另外，`status == "active"` 的封存實體也會被掛。lookup 會對封存實體回 `in_progress`，而 answer 規則是封存的不拿來答「現在」。可以跳過 `e.get("archived")`。

3. **有一種兩邊定義不同的情況，我標為不確定。**
   - 位置：`lookup.py` 的 `name in r["entities"]`。
   - 這個判斷本身是對的：`entities.find` 會把合併掉的實體轉到目標，`wip` 又只放 active 的名稱，所以用別名或合併前的名字查也能對上。
   - 但沒登記或不是 active 的實體會提早 return，`in_progress` 固定是空的，不會去找名稱含這個字的製作中檔。answer 的 `find.md` 有叫它去看 `cards wip`，所以這點大致可以接受。

4. **`line_wip` 逾時時，當天不會再補。**
   - 位置：`hooks/_checks.py` 的 `line_wip` 與 `daily_lines`。
   - 問題：`daily_lines` 先記 `daily_done` 才跑各行。`line_wip` 逾時（`TimeoutError`）只回 `None`，沒有重試。
   - 後果：大庫那天第一句偶爾逾時，這天就永遠不會有「製作中 N 份」那行。
   - 建議：逾時時不要視為做完（不記今天），或接受這個取捨並在 spec 寫明。

5. **同一份 md 或製作中的檔在同一個對話改第二次，不會再被提醒。**
   - 位置：`change_lines` 的 `told_files` 鍵（`wip|uri`、`md|uri`）。
   - 問題：鍵只記 uri，不含指紋或修改時間。
   - 後果：md 整理過後又改，同一對話不會再叫整理，卡就停在舊內容，直到她說整理。`missing|uri` 也一樣：不見、回來、又不見，第二次不報。
   - 這可能就是 spec 的「每份一個對話講一次」，標為不確定。
   - 另外，鍵是原樣的 uri 字串，沒做大小寫正規化。大小寫改名後會被當成新檔再講一次，影響很小。

6. **`MD_LINE` 在按過停止時整行不印，卻也不記鍵。**
   - 位置：`change_lines` 的 `_stopped` 判斷。
   - 這是對的：不記鍵，才不會把她按停後的 md 永遠吞掉。這條不用改。
   - 但 `_stopped` 是看 session 檔的 `ingest_stopped`。如果之後有別的路徑清掉這個旗標，md 會一次補印，這是預期內。

7. **裁定 6 的 `entity log … --synced`，我標為不確定。**
   - 位置：`skills/ingest/references/carding.md`。
   - 指令格式沒問題：`entity log <名稱> <行>… --synced` 和 `scripts/kb/entity.py` 的參數相符。
   - 但 `--synced` 會把綜合卡的「整理到、更新日」換成現行的。md 卡只加了一行紀事，其他新卡、改過的卡還沒併進綜合卡，這個標記會讓之後的過時判斷以為綜合卡已整理到最新。
   - 如果綜合卡的過時判斷看「整理到」，她之後說整理時，這張綜合卡可能不會被重寫。建議確認 `synthesis.mark_synced` 的前提，或這裡不加 `--synced`。
   - 還有一點：`mark_synced` 失敗時整條指令 exit 1，製卡助手可能當成錯誤重試。

其他確認過、沒問題的：
- **light 模式的重做判斷**：redo 判斷成立。`stale` 項的 `reason` 在 light 模式也照加（`cards.py` L848 是 `dict(item, reason=...)`，不看 light），所以 `reason == REDO_REASON` 可用。
- **`_sort_files` 拿掉 deferred 後**：pointer 卡與 redo 的分支順序沒變。
- **`is_open`**：和 `defer_why` 回 "open" 的條件一樣，`change_info` 的 `open` 不變。
- **`config.get`**：舊設定檔留著 `recard_idle_minutes` 不會報錯，因為只查 defaults 裡有的鍵。`kb config set` 設這個鍵會被擋，這是預期。
- **`_is_md`**：用了 `.lower()`，`.MD` 沒問題。
- **uri 形式**：report 的 added／modified／missing 都是 uri 字串（`inventory.py` L940–1100）。

附帶一點：`guard.py` 的 `AGENT_ALLOW` 加了 `("cards","wip")`，製卡助手用不到它（R-13 是主對話跑）。多開一個白名單項目，無害，但可以不加。

共 7 條

## 第二輪：只審 d0d20f3（裁定 7～9 的 diff）

claude -p Sonnet、high，US$0.19。

| # | 處理 |
|---|---|
| 1 not_wip 看讀取，跟 stale、可以讀的密碼檔不一致 | 改：not_wip 不看讀取 |
| 2 redo 的檔又改了 hook 仍印製作中；wip 沒共用 not_wip | 沒改，回報設計（判斷 redo 要讀卡算 sha；wip 照分桶本來就同條件） |
| 3 清冊讀檔 OSError 會讓變動行整個掛 | 改：接 ValueError、OSError，記一行 log |
| 4 清冊讀不到時不篩 | 照註解；file_compare 先讀過清冊，正常走不到 |
| 5 每句多讀一次清冊 | 改：沒有新增、修改就不讀 |
| 6～8 | 審查確認沒問題 |
| 9 實體的 archived 欄位在不在 | 在（lookup 的 archived 也讀它） |

### review 原文

我已讀完 diff，也對照了 `_sort_files`、`wip()`、`uri_key`、`kb entity log` 的參數。以下是結果。

**1. `cards.py:968-972` `not_wip` 的 `read in SKIPPED_READS` 跟 `_sort_files` 不同**
- `_sort_files` 的 new 迴圈（870-873）有 `ok = read=="ok" or (read=="credential" and eid in readable)`。有「可以讀」裁示的 credential 會進 new。`not_wip` 沒看 `rulings.readable_ids`，直接當「讀不了」排除。
- 輸入：credential 檔有可以讀的裁示，使用者新放或改了它。`kb cards wip` 會列，每句開頭的變動行不會。裁定 8 要求兩邊同一套篩法，這裡不一致。
- stale 迴圈（833-848）完全不看 `read`。已有卡的條目，`read` 是 placeholder、too_large、error 或 credential，原檔改了就進 stale、`wip` 會列。`not_wip` 卻把它擋掉。
- 建議：`not_wip` 的 `read` 判斷只套用在「沒有卡」的新放檔上，或乾脆不看 `read`。有「可以讀」裁示的 credential 要放行。

**2. `not_wip` 沒擋 `wip()` 會擋的條目，兩邊也不是共用同一個函式**
- `wip()`（997-1000）排除 redo 的 stale（`reason == REDO_REASON`）。`not_wip` 沒看 `redo`。
- `wip()` 也排除 `kind == "link"`。link 的 uri 是網址，不會出現在 report，所以這條不會壞。
- 輸入：檔案被標了重做（`entry.redo` 有效），之後又被改。`wip` 不列，每句開頭仍印「製作中」。
- `wip()` 並沒有呼叫 `not_wip`，全專案只有 hook 在用它（grep 結果）。「同一套篩法」靠人手對齊，之後很容易再漂。
- 建議：讓 `wip()` 也用 `not_wip`，並把 redo 判斷放進去。判斷 redo 要 `card_sha`，需要讀卡，成本較高。
- 不確定：草稿（`is_draft`）、`unreadable_open` 的條目、`not_for_card` 在 hook 端也沒擋，`wip` 端有擋。草稿算不算製作中，我沒把握，請看裁定 8 的原意。

**3. `hooks/_checks.py:257-261` 例外處理太窄**
- 只接 `ValueError`。`inventory.load` 讀檔若丟 `OSError`（檔被鎖、權限），例外會往上衝出 `change_lines`，整個每句開頭掛掉。
- 同一檔的 `file_compare` 用 `except Exception` 並 `log_vault`，這裡不一致。
- 建議：改成 `except (ValueError, OSError) as e:`，並 `log_vault(vault, e)`。

**4. 清冊讀不到時的降級行為**
- `skip = set()` 的結果，是所有指路卡、封存、skip_kind 的檔又會被報成製作中。這跟註解「清冊讀不到就不篩」一致，行為沒壞。
- 但 `file_compare` 的 `inventory.scan` 必然已讀過清冊，正常不會走到這裡，這條是防禦用。
- 不確定：清冊損壞時，其實該跟 `file_compare` 一樣回 `[],[]`，而不是多印一堆。

**5. 時間預算**
- `inventory.load` 是整份 JSON 重讀、重解析。`file_compare` 內的 scan 已讀過一次，結果沒帶出來，所以每句開頭多讀一次。
- 大清冊下這筆成本會吃掉 `TURN_BUDGET`，而且 `change_lines` 在 `file_compare` 之後才算，預算已被 scan 用掉一部分。
- 沒量過實際耗時，我標「不確定」。
- 建議：讓 `file_compare` 把已載入的 entries 一起快取進 `_SCAN`，或至少在 `report["added"]` 與 `["modified"]` 都為空時跳過載入。現在是無條件載入。

**6. `uri_key` 比對（確認沒問題）**
- 兩邊都走 `inventory.uri_key`（正斜線、casefold），形狀一致。`_kb_keys` 也是同一套。
- 唯一風險：report 的 uri 如果是 `file://別名/相對路徑`，locations 的 uri 也是同一形式，我沒看到不一致。

**7. `POINTER` 順序（確認沒問題）**
- `POINTER` 在 `cards.py:534` 定義，`not_wip` 在 968，執行時已存在。沒有順序問題。

**8. `carding.md` 與 `entity.py`（確認沒問題）**
- `kb entity log <實體> '<行>'` 只收 `ref` 與 `lines`，`--synced` 是可選。去掉後的句子跟參數相符。
- 「`entity log` 只加紀事」跟 entity.py:62 的說明（「--synced 加完再標記整理到」）一致。
- 檔頭 15 行的 docstring 沒改，仍相容。

**9. `_wip_entities` 加 `e.get("archived")`（`cards.py:982`）**
- 實體 `archived` 欄位是否真的存在，我沒查證。`status != "active"` 已經涵蓋封存的情況嗎？若實體封存是用 `status`，這個條件是多餘但無害。若欄位名稱不同，就沒效果。
- 標「不確定」，請對照 `entities.py` 的封存欄位名。

共 3 條（第 1、2、3 條是確定的正確性問題；第 4、5、9 條是不確定項，不計入）

## 第三輪：只審 b868ed3（裁定 15～17 的 diff）

claude -p Sonnet、high，US$0.27。plugin 驗證 PASS、錯誤 0、警告 1（py_compile 被擋），US$0.10。

| # | 處理 |
|---|---|
| 1 同一批有一字不差已有的又有同日同卡的新條，已有的被刪卻回報已經有 | 改：跟這批某條一字不差的舊行不換 |
| 2 舊條掛多張卡，新條只沾一張就整條換掉 | 改：舊行的卡編號都在新行裡才換 |
| 3 只認 f- 編號 | 照裁定 16「卡編號」，docstring 寫明 |
| 不確定 1 回傳沒有「換掉」資訊 | 不改（換掉的新條算 added） |
| 不確定 2 --ids 的 job 多了日程重對、要等更久才關 | 不改，回報設計 |

### review 原文

審完了，我只讀程式碼，沒改檔也沒跑測試。有 3 條正確性問題，另外列 2 條不確定的。

**一、`scripts/kb/_lib/synthesis.py:1253-1271` `insert_events`：一批裡有「一字不差已有的」又有「同日同卡的新條」時，已有的那條會被刪掉，卻還回報為已有。**
- 輸入：同一批 events 是 `[A, B]`。A 跟舊條 X 一字不差，B 不同，但跟 X 同日、同一個 `f-` 編號。
- 怎麼壞：A 在 1256 行因為在 `have` 裡被歸進 `dup`（回報「已經有」）。B 進了 `todo`，1269 行的 `replace` 含 `(day, c)`，所以 1270-1271 行把 X 拿掉。結果 A 的內容不見了，輸出卻說它已經有。
- 建議修法：`replace` 排除跟 `dup` 同日同卡的條目，或 `dup` 的條目也算進 `todo` 當新條。更簡單的做法是先換掉，再用換掉後的 `sec` 去重（`have` 改在換掉後算）。

**二、`synthesis.py:1269-1271`：一條舊紀事有多個〔卡〕，新條只要沾到其中一個同日編號，整條舊的都被換掉。**
- 輸入：舊條是 `2026-11-03 …〔f-aaaaaaaa〕〔f-bbbbbbbb〕`，新條是 `2026-11-03 …〔f-aaaaaaaa〕`。
- 怎麼壞：`any(...)` 命中 a，舊條被拿掉，b 這份卡的出處和內容一起消失。裁定 16 說的是「同一個〔卡編號〕」，沒說多卡的條目可以整條丟。
- 建議修法：舊條的卡編號集合是新條卡編號集合的子集時才換，也就是 `_card_ids(old) <= _card_ids(new)`。若判斷是一條多卡就不換，就改成「全部相交才換」，並在規格寫明。

**三、`synthesis.py:1232`：`_CARD_ID` 只認 `f-`，跟 `parse_event` 允許的 `[fscr]-` 不一致。**
- 輸入：同日、同一個 `s-`（口述）或 `r-`（推算）編號的新舊兩條。
- 怎麼壞：不會換，兩條並存。
- 這可能是刻意的，因為裁定寫「卡編號」。但規格和 docstring 都沒說 `s-`、`c-`、`r-` 不換，請補一句，或確認要不要一起換。

**不確定的：**
1. **`insert_events` 的回傳沒有「換掉」的資訊。** 換掉的新條在 `added` 裡，沒有 replaced 欄位，所以 `add_events` 的 `added` 和 `kb entity log` 的人讀輸出（加了 N 條）看不出舊條被拿掉。我沒讀到 `add_events` 後面和 CLI 的輸出段，不確定是否影響測試或她看到的說明。
2. **hook `MD_LINE` 和 `SKILL.md` 寫「她說了整理就照 ingest 整理全部、不帶 `--ids`」，但程式上 job 記著 ids。**
   - `batches.py:793-794`：`ids is None` 時沿用 `job["ids"]`，所以 `--ids` 的 job 還開著時，不帶 `--ids` 的 dispatch 仍然只派那幾份。
   - `SKILL.md` 有寫「這批還沒 `done` 時她說整理，等它做完」，說法一致。
   - 但這批現在多了日程重對，要等到 agenda 也做完才算 `done`，等的時間變長。若那時日程批失敗或一直沒再派，job 不會關，她說整理也一直被限在那幾份。這是文件與行為的落差，不算程式錯。

**確認過沒問題的：**
- `_only_ids` 的形狀正確。`split` 的項目是 `(bucket, key, item)`，agenda_recheck 的 `item["card"]` 就是出處卡編號，跟 `_entry_of_item` 一致。
- `known` 只看 cards 不會誤判，因為 `--ids` 給的是卡編號，不是日程編號。
- 順序正確：cards 有剩或還在跑時，迴圈 `break`，agenda 不會先派。
- 建置抽樣沒壞：`ids_running` 算 job 底下所有跑著的批次，`close_ids_job` 收掉 job。沒派出去的 agenda_recheck 留給之後的全量 job。

共 3 條

## 第四輪：只審 d940a0c（裁定 18 的 diff）

claude -p Sonnet、high，US$0.14。plugin 驗證 PASS、錯誤 0、警告 1（py_compile 被擋），US$0.11。

| # | 處理 |
|---|---|
| 1 舊格式鍵（沒帶指紋）升版後那個對話重講一次 | 不改：只在升版當下開著的對話、最多一次；第 5 條的修正順手把舊格式鍵拿掉 |
| 2 取不到大小、時間時鍵尾空的，下一句取到了多講一次 | 不改：偶發、最多一次 |
| 3 同一份 stat 兩次 | 改：每份只 stat 一次 |
| 4 missing 鍵只看這次新不見的 | 改：missing、still_missing 都算還不見（先紅後綠） |
| 5 又改了舊鍵不拿掉、佔 FILES_KEEP | 改：記新鍵時同一份的舊鍵拿掉（先紅後綠） |

### review 原文

我只讀了 `git show d940a0c`，再對照 `scripts/kb/_lib/inventory.py` 的 `path_of`、`abs_of_uri` 和 `scan`。沒有跑測試，也沒有改檔。結果有 3 條有把握的問題、2 條不確定。

**1. 舊格式鍵升版後全部重講一次**
- 位置：`hooks/_checks.py:279-283`（`key` 和 `fresh`）。
- 升版前留在 session 檔裡的舊鍵是「wip|uri」或「md|uri」，沒有 stamp。新鍵是「wip|uri|大小:時間」，兩者永遠對不上。
- 所以升版後的第一句，這個對話裡所有仍在變動清單的檔都會再講一次。不會報錯，因為鍵只拿來比字串。
- 舊鍵不會被清掉，只會佔 `FILES_KEEP`（1000 條）的名額，直到被截斷。
- 建議：`fresh` 比對時，也把「kind|uri」這個無 stamp 的舊鍵當成已講過；或者只認一次舊格式。

**2. `_stamp` 取不到檔時鍵尾是空字串，同一份檔會被多講一次**
- 位置：`hooks/_checks.py:243-250`、`:279-280`。
- `path_of` 回 None（別名對不到）、檔剛好被刪、或 `os.stat` 暫時失敗，都會得到「kind|uri|」。
- 下一句如果 `stat` 成功，鍵變成「kind|uri|size:mtime」，會再講一次。
- `FILES_KEEP` 截斷也會讓舊鍵掉出去，造成類似的重講，但那是量的問題。
- `scan` 看得到、`stat` 卻失敗，常見於路徑超長或權限問題，這時每句都只會是「kind|uri|」，反而不會重講，所以這條只是偶發的多講一次。
- 建議：stamp 取不到時，改用 `scan` 已經拿到的值，或乾脆不記鍵。

**3. `key()` 對同一個 uri 呼叫兩次 `os.stat`，兩次之間檔又變就會漏講**
- 位置：`hooks/_checks.py:279-296`。
- `fresh` 裡先算一次 stamp 做過濾，最後 `keys += [key(kind, u) ...]` 又算一次。
- 兩次之間檔如果又被改，記下去的是「新 stamp」，而這次講的是舊內容。下一句的 stamp 相同，所以不再講，這次寫入就被吞掉了。
- 從 `file_compare` 比完到 `stat` 之間檔又變，也是同樣的情況。窗口很小，影響也輕。
- 建議：每個 uri 只算一次 stamp，用 dict 存起來，過濾和記鍵都用同一份。

**4. 不確定：missing 鍵的修剪只用「這次新不見」的清單**
- 位置：`hooks/_checks.py:266-267`。
- 我查過 `inventory.scan`（`inventory.py:1097-1106`）：`report["missing"]` 只放這次由 active 轉成 missing 的條目，之前就不見的放 `still_missing`。
- 如果 quick scan 不 apply，清冊裡的狀態不變，下一句同一份檔還是 active 轉 missing，鍵會留著，不會重講。
- 但只要有別的流程把清冊 apply 了，那份檔下一句就在 `still_missing` 裡、不在 `missing` 裡，鍵會被誤刪。
- 之後如果有人把 `still_missing` 也併進 `fresh("missing", …)`，或這份檔先被 apply 成 missing 又在別處被還原，就會重講。目前我沒找到會出錯的路徑，所以只列為不確定。
- 規格說的是「回來了才忘掉」。比較貼近的做法是：只保留「現在仍不見」的鍵，也就是 `missing` 加 `still_missing` 的聯集，而不是只看 `missing`。

**5. 不確定：`told_files[-FILES_KEEP:]` 截斷的負擔比以前重**
- 位置：`hooks/_checks.py:600`（`turn_lines` 最後一行）。
- 現在每改一次檔就多一個新鍵，舊 stamp 的鍵不會被拿掉。同一份檔在長對話裡反覆編輯，鍵數成長比以前快。
- 截斷是從舊的砍起，被砍掉的鍵對應的檔如果還在變動清單裡，會再講一次。
- 順序上，這次新加的鍵在尾端，不會先被砍。
- 建議：記新鍵時，順便移除同 kind、同 uri 的舊 stamp 鍵。

**已確認沒問題的部分**
- `os.stat(None)` 丟的是 `TypeError`，已被 `_stamp` 的 `except` 接住。
- `incomplete`、讓位（`yield_to_upgrade`）、`file_compare` 失敗這三條路徑，都回原樣的 `told`，沒有修剪。
- `turn_lines` 在 `guarded` 回 None 時，`told_files` 保持原樣，接法正確。
- `link`、來源找不到時，`path_of` 回 None 或不存在的路徑，`_stamp` 回空字串，不會拋出例外。

共 5 條
