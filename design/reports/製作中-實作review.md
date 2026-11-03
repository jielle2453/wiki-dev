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
