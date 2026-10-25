# lint（健檢）與待處理的問法 — 測試報告（第五輪，桌面版確認後的短驗）
日期：2026-10-25
給誰看：設計 session（結案時填 spec「紀錄」的測試報告欄）。
何時更新：同一輪重跑時重寫該節；實作再修之後在文末加一節。

對象：桌面版確認後實作修的六件（確認報告 `C:\Users\Jie\Desktop\llm-wiki-test\lint-check\確認報告.md`，只讀），範圍 `c1ea821..72d000c`（0debba5、72d000c；另動 `agenda_cli.py`、`journal_cli.py` 各一處）。
環境：Windows 11、Git Bash、Python 3.14、Claude Code 2.1.310。worktree `C:\Users\Jie\Desktop\llm-wiki-j-lint`，分支 `spec/lint`，HEAD `72d000c`。
做法：只執行與讀檔，不改程式。六件各自用真的 `kb` 指令與真的 `hooks/session.py` 在暫存知識庫上動手做一次；diff 約 260 行，code review 我自己逐行讀並用實驗驗證，沒另開子代理。

## 結論

**可以發行。** 六件都修好，沒有擋發行、沒有外洩；新發現只有兩項，都可留 backlog：客戶看得到的英文字（T-39）、新測試跨午夜會偶發失敗（T-40）。

全套測試：3056 個、跳過 2、exit 0（第一次跑橫跨午夜有 2 個測試失敗，是測試本身的問題，見 T-40；重跑全過）。`test_budget`、`test_lint_desktop` 單跑 26 個全過。`claude plugin validate .` exit 0（只有 ICON_MISSING 與 README 沒安裝句的建議，與前幾輪相同）。

## 逐件

| # | 結果 | 證據 |
|---|---|---|
| 1 升格指令 | 修好 | 5 條同卡型「口述為準」裁示 → `kb lint` 開出 `promote:spoken_wins:報價`；note 是「…她說好就 kb profile add 偏好 偏好=<那句>，再照 data.rulings 逐條 kb ruling remove」，我從 note 抽出欄名（`偏好`、`偏好`）原樣跑 `kb profile add 偏好 偏好=報價單的金額以我口頭說的為準` → 「已加偏好：報價單的金額以我口頭說的為準」，`profile.json` 的 `preferences` 有那一條（來源 corrected）；再逐條 `kb ruling remove` 5 次都成功。`skills/lint/references/report.md` 第四節同一句也是 `偏好=<那句>`。 |
| 2 推測日程記成確認 | 修好 | 兩條 `source: inferred` 的日程：①`kb agenda edit <a-…>`（不帶欄位）→「記成確認了：給報價0」；②`kb agenda edit <a-…> --date <原本的日期>`（原樣帶）→「記成確認了：給報價1」。兩條 `source` 都變 `confirmed`、`history` 各多一筆 `source inferred → confirmed`（by program，回合代號在）、`kb journal recent` 各多一段「做了：日程記成確認：…　改了：日程」。非推測的（`kb agenda add` 加的）不帶欄位 `kb agenda edit` → 「沒有給要改的欄位」exit 3，照舊。之後 `kb lint` 不再開 `inferred:agenda`（lint 後該 key 的件為空）。 |
| 3 開場變動行 | 修好 | 真的 `hooks/session.py` 開場。健檢標了 1 張綜合卡（出處點不開）、有 11 份檔沒整理：「還有 11 份沒整理完、1 張綜合卡要改寫」；再把一張卡的原檔在來源裡搬位置：「還有 11 份沒整理完、1 張綜合卡要改寫、1 張卡要跟著搬」（三半同一行）；沒有健檢標的：「還有 11 份沒整理完」（0 的那半不印）。`cards.unsorted` 是 11、`kb lookup 信義王` 的「還沒整理 11 份」也是 11，兩處都只數檔（不再 +1）。 |
| 4 健檢報告與 kb lint 人讀 | 修好 | 庫裡有 10 份沒整理、1 份原檔不見（真的刪掉原檔後 `kb inventory scan`）、1 條逾期日程：`kb lint` 人讀「整理還有：待整理 10 份」（沒有「原檔不見」）；報告數字段兩行「整理還有：待整理 10 份」「要你決定的另有：原檔不見 1 份、日期過了沒銷 1 條」，建議下一步有「整理還有沒做完的，說「整理」就好」。**沒有做得了的**（新 `kb init` 的庫，只有一條逾期日程）：報告只有「要你決定的另有：日期過了沒銷 1 條」，建議下一步只有備份那句，**沒有**「說「整理」就好」。 |
| 5 工作日誌 | 修好 | 工作日誌有一句卡了兩天沒記完的回合 → `kb lint --background`：`kb journal recent` 抬頭「每週健檢（自動）」（不是「你在終端機跑的」），「做了：健檢：補完 1 句沒記完的工作日誌」；`系統/工作日誌/2026-10.md` 月檔抬頭「## 2026-10-25 23:58:23　每週健檢（自動）」。她說「幫我檢查」的前台 `kb lint` 照舊是「程式 lint」／「你在終端機跑的：kb lint」（那是她叫的，語意對）。 |
| 6 重做候選不含排除夾 | 修好 | 3 張報價卡、卡型那節日期新；其中內湖李那夾 `kb folders exclude 客戶案件/內湖李 --kind unused`（卡 1 張被標不讀）→ `kb lint`：`redo_by_profile` 件寫「有 2 張卡是之前做的」，`data.ids` 只有另外兩張，排除夾那張不在；照 `do` 跑 `kb cards redo --ids …` 成功（「已標成要重做：2 張卡」），不再像確認報告那樣有一張標不了。 |

## code review（c1ea821..72d000c）

- `agenda.edit`：`fields` 全空、來源 `inferred`、沒帶 `card` 才記成確認；帶了欄位但沒有實際變動（原樣帶）也走這條（親測）；有 `card`（重對）仍維持推測；`agenda_cli._edit` 先判「沒有給要改的欄位」才放行 inferred，非推測不受影響。
- `hooks/session.py`：`_unsorted_count` 回三元組，`line_changes` 的 `parts` 順序是「份、綜合卡、搬」，`any(counts)` 對 0 的那半不印；開頭沒有「還有」的才補（只有 K 的情況句首會補「還有 」，我沒另外造「只有 K」的庫，邏輯是 `startswith(LEFT_HEAD)`）。`cards.unsorted` 少一項 `lint_fix_count`，開場的第三個數字才是它。
- `lint/report.py`、`lint_cli.py`：`INGEST_TEXT`（做得了）與 `DECIDE_TEXT`（要她決定）拆開；`skills/lint/SKILL.md` 與 `references/report.md` 同步。
- `journal.AUTO_LABELS` 只有 `lint --background` 一項，月檔與 `journal recent` 兩處都套。
- `stale_by_profile._old_cards` 多濾 `status == active`。

## 新發現

沒有外洩、沒有擋發行。

**T-39　工作日誌的「改了」會對客戶寫英文字「lint」（可留 backlog，已重現）**
- 位置：`scripts/kb/_lib/journal.py` `SYSTEM_WORDS` 沒有 `.system/lint.json`（以及 `set_aside.json`、`renders.json`、`statements-archive.json`、`findings-archive.json`、`handedits` 等 lint 題新增的狀態檔）。
- 重現：`kb lint --background` 之後 `kb journal recent`：「每週健檢（自動）　做了：健檢：補完 1 句沒記完的工作日誌　**改了：lint**」；背景健檢每週都寫一段，客戶看工作日誌每週會看到「改了：lint」。其他狀態檔（日程、待處理、裁示…）都有白話字。
- 影響：只是字（工作日誌是她看得到的檔，spec 確認 10「給客戶看的字有沒有英文」）。可留 backlog：加一列 `.system/lint.json` → 「健檢紀錄」之類；其他幾個狀態檔也補白話或不列。

**T-40　新測試的「今天」在載入時就固定，橫跨午夜會失敗（可留 backlog，已重現）**
- 位置：`tests/test_lint_round1.py:19`、`tests/test_lint_round2.py:16` 的 `TODAY = dt.date.today()`（模組載入時算一次）。
- 重現：全套測試 10-25 23:5x 開始、跑到 10-26 00:0x 之間，`test_lint_round2.T26ForgetAnsweredWhenGone.test_redo_items_cover_every_card` 與 `test_lint_round1.T2AnsweredStaysClosed.test_redo_marked_cards_not_candidates` 失敗（`not enough values to unpack`、`0 != 1`）：測試用 `replace(f"製卡日期: {TODAY.isoformat()}", …)` 把卡的製卡日期改舊，但 `L.write_card` 在執行時才蓋今天的日期（已經是 10-26），replace 對不上，卡不算舊的、沒有候選。兩個測試單跑（10-26）都過，整套重跑也全過。
- 影響：只是測試在午夜前後 12 分鐘的跑法會偶發失敗；不是程式缺陷。可留 backlog：測試裡用寫卡後讀回來的製卡日期，或 `mock` 今天。

## 沒測到的
- 觸發句與 D-132 新舊版對照（確認報告第 10 項已在桌面版走過）。
- 桌面版以外的環境：跨電腦同步、SMB／NTLM 實連。
- `plugin-dev:plugin-validator` agent（只跑了 `claude plugin validate`）。
- 前幾輪列為 backlog 的 T-12、17、18、21、23、32、37③、38 與 code review #11、#12、#17。

## 全部測試
`python -m unittest discover tests`：3056 個、跳過 2、exit 0（667 秒），跟 3a 的結果一致。第一次跑（10-25 23:5x 開始）有 2 個失敗，原因見 T-40，不是程式問題；日期穩定後整套重跑全過。`claude plugin validate .` exit 0。
