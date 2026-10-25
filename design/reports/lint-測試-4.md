# lint（健檢）與待處理的問法 — 測試報告（第四輪）
> 代號說明（2026-10-25 補）：T-1～T-40 是 lint 測試的發現，五輪接續編號（第一輪 T-1～T-24，第二輪 T-25～T-32，第三輪 T-33～T-37，第四輪 T-38，第五輪 T-39、T-40）；後面幾輪的報告也會提到前面的 T 編號。驗收 N 指 lint spec。

日期：2026-10-25
給誰看：設計 session（結案時填 spec「紀錄」的測試報告欄）。
何時更新：同一輪重跑時重寫該節；實作再修之後在文末加一節。

對象：第三輪報告 `design/reports/lint-測試-3.md`（1a36400）的修正，範圍 `1a36400..2edfd74`（單一實作 commit，另動 `folders.py`、`_lib/restore.py` 各一行的 `record_derived`）。
環境：Windows 11、Git Bash、Python 3.14、Claude Code 2.1.310。worktree `C:\Users\Jie\Desktop\llm-wiki-j-lint`，分支 `spec/lint`，HEAD `2edfd74`。
做法：只執行與讀檔，不改程式。第三輪的重現步驟照原樣再跑（真的 `kb` 指令、暫存知識庫、真的 hook 與子行程）；T-33／T-34 端到端用真的 `folders exclude --kind hidden`；這輪的 diff 很小（約 100 行），code review 我自己逐行讀並用實驗驗證，沒另開子代理。

## 結論

**可以進桌面版確認。** T-33～T-37 全數修好，沒有擋發行、沒有外洩；本輪沒有新的應修項目，只有一項可留 backlog 的小事（T-38）。

全套測試：3044 個、跳過 2、exit 0。`claude plugin validate .` exit 0（只有 ICON_MISSING 與 README 沒安裝句的建議，與前幾輪相同）。

## 逐條

| 編號 | 結果 | 證據 |
|---|---|---|
| T-35 | 修好 | **沒有 `.system/skeleton.json` 的舊庫**（夾具庫就是）`kb lint --json`：`failed_checks: []`、一句話「一切正常。」、`hook-errors.log` 不存在；報告數字段照出「舊範本的卡 0、存的 schema 比現在舊 1」、沒有「沒查成」字樣；她改了 `CLAUDE.md`（沒紀錄）也不誤開骨架件。**壞掉的 `skeleton.json`（寫成 `{壞`）仍算沒查成**（`failed_checks: ["版本與骨架"]`）。真的 `hooks/session.py` 開場觸發的背景健檢（`last_background` 8 天前）跑完：`last_background` 是今天、`hook-errors.log` 不存在。 |
| T-33 | 修好 | 端到端（`客戶案件/私人/日記本.txt`，掛卡「王家心情」，從那張卡推測的日程「寄機密合約給老王」，待處理有「日記本.txt 不見了」一件，另有 `set_aside.json` 的問句、`renders.json` 的整理問題、健檢報告都帶這些字）。**兩種手改各做一次**：①她把那行打勾；②她在那行後面加「這個我自己處理」（`other`）。`kb folders exclude 客戶案件/私人 --kind hidden`（自己 purge）後，在整個知識庫找：獨特字串 0 檔、卡標題「王家心情」0 檔、檔名「日記本.txt」0 檔、`客戶案件/私人` 與 `私人` 0 檔、推測日程原文「寄機密合約給老王」0 檔（`.system/versions/` 與 journal、turns、`sources.json` 除外，回合夾備份照規則只換路徑，所以那裡還找得到推測日程原文 2 檔，不算缺陷）。涵蓋 `pending.json`、`待處理.md`、`.system/handedits/`、`系統/健檢報告/`、`renders.json`（`bases`、`asks`、`saved`）、`set_aside.json`、`lint.json`。`kb lint handedit --json` 的 `checked/removed/changed_date` 只剩遮過的字，沒有檔名、原文。`purge-pending.json` 清完後不存在、`sources.json` 的 `purge` 改成日期。 |
| T-34 | 修好 | 同上；`.system/handedits/<時間>-待處理.md`（她那份的副本）、`系統/健檢報告/2026-10.md`、`renders.json` 的 `asks` 與現行 `待處理.md`「整理時要問你的」段，檔名與推測日程原文都換成「（已排除）」。 |
| T-36 | 修好 | **待處理**：加甲乙丙（回合一）、加丁戊（回合二）→ `kb versions revert` → 她把甲打勾 → 再加己件：`kb lint handedit --json` 只有 `checked` 甲，`removed`、`other` 空。**日程**：同樣做法（甲承諾、乙承諾，退回乙，她把甲打勾，再加一條開會）→ `checked` 甲，沒有乙。 |
| T-37 ① | 修好 | 綜合卡還引用那張日記卡 → exclude 後不立刻 purge（「接著要重寫的綜合卡：信義王…寫完跑 kb folders purge 客戶案件/私人」），`purge-pending.json` 此時記著 `words: ["寄機密合約給老王", "日記本.txt"]`、`gone: [a-…, p-…]`（條目都已拿掉）；重寫綜合卡、`kb folders purge` 重跑 → 上面所有字串在整個知識庫（允許清單以外）0 檔，靠的是記下來的 words。 |
| T-37 ② | 修好 | 一條確認過（`agenda.edit` 成 corrected）、`origin.card` 是日記卡的日程，她在 `日程.md` 把它打勾 → handedit 件的 `checked` 有它；exclude + purge 之後 `kb lint handedit --json` 的 `checked` 仍有那一行，沒被整列拿掉。`gone` 只有推測的日程與指到那夾的待處理（`a-…`、`p-…`）。 |
| T-37 ③ | 沒動 | `cleared` 遇到「暫時讀不到」的情況，這輪 diff 沒碰（`pending.py` 只加了 `keep_known` 一行）。這是第三輪 code review 讀程式推的、我當時就沒重現，列為可留 backlog，不再追。 |
| T-37 ④ | 修好 | `renders.json` 的 `bases`：被遮過、對不上的拿掉（`待處理.md` 除外，它下一步照遮過的重寫重記），日程、裁示的 bases 沒被遮到的原樣留著；`renders.json` 手改壞成非二元組時 `load` 現在就濾掉，不會在 purge 拋 `TypeError`（讀程式；`load` 的過濾我看過）。 |

## code review（只看這輪的 diff）

- **`record_derived` 在 `folders.py`（exclude）與 `restore.py`（還原後重新套用 hidden 排除）的位置**：兩處都在 `record(undo)` 回呼裡、跟 `record_titles`、`record(..."turns")` 同一組，用的是 `before_entries` 取的 `names`（清冊還沒拿掉條目的時候）與 `gone`，變數在兩處的作用域裡都有定義。
  - **exclude 失敗倒回**：我把 `folders._drop_cards` 換成丟 `OSError`，`kb folders exclude … --kind hidden` → exit 3「沒有動：OSError」、`sources.json` 逐字還原、`purge-pending.json` 不存在（沒有多記的 words／gone）、卡還在；接著不換替身再做一次，正常排除並清完。
  - **還原路徑**：先備份、再 exclude hidden、再 `kb restore apply <備份>`（備份裡沒有那條排除）→ 「你設成不想讓 AI 看到的「客戶案件/私人」留著、也再清了一次」，整庫（快照、回合夾、journal 除外）找不到獨特字串、卡標題、檔名、夾路徑、推測日程原文。
- **purge 重跑**：`derived`、`gone` 從 `purge-pending.json` 讀回來併進這次算的；清完 `mark_done` 把它們一起清掉（`purge-pending.json` 不存在）。
- **`keep_known`／`known_ids`（T-36）**：只留現在資料裡還有的編號；`handle_list`、`pending._hand_edit`、`agenda`、`rulings` 三處呼叫一致；`other` 不過濾（看不出對到哪一條的行照舊進來）。
- **`versions` 檢查**：沒紀錄且沒檔 → 跳過比對、數字照出；有檔但壞 → 丟例外（`failed_checks`）。判斷用 `exists()`，不會把「壞」誤當「沒有」。
- **新測試**：`tests/test_lint_round3.py`、`test_lib_purge.LintDerived` 碰真檔與真 purge；我用端到端交叉驗證過上面每一條。

## 新發現

沒有外洩、沒有擋發行。

**T-38　`derived_masker` 把所有出現的衍生字詞都換掉，包括無關的（可留 backlog，讀程式，未重現）**
- `purge.derived_masker` 對檔名與推測日程原文（長度 ≥ 3）做整串取代，套在 handedits 的副本、健檢報告、`renders.json` 等：若被排除的卡推測出的日程文字很普通（例如「給報價」），報告或副本裡其他不相干件的同樣三個字也會被換成「（已排除）」。報告是永久保留的，之後讀起來有幾個奇怪的洞。
- 影響是可讀性，不是外洩；機率低（要日程原文夠短、夠普通）。可留 backlog。

## 沒測到的
- 觸發句與 D-132 新舊版對照（延到桌面版確認）。
- 桌面版實際跑背景子行程；SMB／NTLM 實連；跨電腦同步。
- `plugin-dev:plugin-validator` agent（只跑了 `claude plugin validate`）。
- 前幾輪列為 backlog 的 T-12、17、18、21、23、T-32、T-37 ③ 與 code review #11、#12、#17。

## 全部測試
`python -m unittest discover tests`：3044 個、跳過 2、exit 0（709 秒），跟 3a 的結果一致。`claude plugin validate .` exit 0。
