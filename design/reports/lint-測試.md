# lint（健檢）與待處理的問法 — 測試報告
日期：2026-10-25（第一輪）
給誰看：設計 session（決定哪些發現回實作修、哪些改 spec；結案時填 spec「紀錄」的測試報告欄）。
何時更新：同一輪重跑時重寫該節；實作修正後的新一輪在文末加一節。

對象：`design/specs/2026-10-23-lint.md`「驗收準則」1–24，含 D-220～D-227 與 3a 裁定的 18 個疑義。
環境：Windows 11、Git Bash、Python 3.14、Claude Code 2.1.310。worktree `C:\Users\Jie\Desktop\llm-wiki-j-lint`，分支 `spec/lint`，HEAD `83f73c9`（底 `9aa6871`，八個實作 commit）。
做法：只執行與讀檔，不改程式。驗收每條用真的 `python scripts/kb.py …` 在系統暫存夾的知識庫（`tests/_entities` 的假庫複本）上動手跑；起點狀態（放一張壞引用的綜合卡、一條 40 天前的推測日程、一份 junction 之類）用函式庫或直接改 JSON 造，跟 spec 驗收準則「放一個…」同義。開場背景用真的 `hooks/session.py` 與真的 detached 子行程驗。注意 `tests/__init__.py` 會替整個測試程序設 `WIKI_WITH_WILLY_NO_BACKGROUND=1`，黑箱跑 hook 的腳本要先拿掉它，否則背景健檢不會開。
審查：code review（高強度，一個獨立子代理，範圍 `9aa6871..83f73c9`，每個高/中發現我再自己重現或標明未重現）、security review（另一個子代理，找可利用性）。`claude plugin validate .` 跑過；`plugin-dev:plugin-validator` 沒另外跑。

## 結論

**驗收 24 條：1–22、24 過；23 部分（run_eval 在 Windows 跑不了，依派工跳過；D-132 新舊版對照與觸發句實測延到桌面版確認）。** 沒有擋發行的項目，也沒有找到直接丟客戶資料的缺陷。

全套測試：`python -m unittest discover tests` 跑 2999 個、跳過 2、exit 0（710 秒），跟 3a 的結果一致。`claude plugin validate .` exit 0（只有 ICON_MISSING 與 README 沒安裝句的建議，不影響結果）。

但待處理這一塊（D-226）有一組互相關聯的設計缺口，客戶用幾週就會碰到，建議在發行前修：

| # | 嚴重 | 問題（短） |
|---|---|---|
| T-1 | 應修 | 健檢開的 `lint` 類待處理，條件消失了不會自動關 |
| T-2 | 應修 | 她處理過（完成／不用管）的 `lint` 件，下週健檢又重開；`redo_by_profile` 她說好、已標重做，整理沒做完前也會重開 |
| T-3 | 應修 | `inferred:agenda` 帶著已過去的日期：被當成「有時間性」，先放著無效、佔掉每個回答末尾的名額 |
| T-4 | 應修 | 「先放著」逾期日程題：成功句說先放著了，但那題每個回答都照列 |
| T-5 | 應修 | `_untrue` 把仍然讀不到的檔誤判成已不成立，自動關掉（code review 找到，我未重現） |
| T-6 | 應修 | 口述／推算封存後不跟實體改名、合併；`statement restore` 會把舊名帶回來（code review 找到，我未重現） |
| T-7 | 應修 | `kb lint` 連跑，「替你做了」同一句重複記，月摘要件數虛增 |
| T-8 | 應修 | 新增的封存檔、健檢報告、handedits 沒進 `folders purge`（「不想讓 AI 看到」的承諾） |
| T-9 | 應修（低） | `inferred:entity` 的 `do` 指令 `kb entity confirm <名>` 沒加引號，含 `; & ' ( )` 的名字會壞 |

其餘 T-10～T-24 是低優先或可留 backlog，見「發現」。

## 逐條

指令前綴 `kb` = `python <W>/scripts/kb.py`，`<V>` 是暫存知識庫。每條都是在乾淨的新庫跑。

| # | 結果 | 證據（我跑的） |
|---|---|---|
| 1 | 過 | 綜合卡內文放〔f-00000000〕、一張不採用的卡、一條已收回的〔s-…〕（另放一個在「紀事」段）。`kb lint --json` → `done`「標了 1 張綜合卡要更新（出處點不開）」；`lint.json` 的 `synthesis_fix` 一筆、`ids` 三個（紀事段的不另標）；`kb cards todo --json` 的 `synthesis_stale` 有那張、`reason`「出處點不開、有空段」。把壞行拿掉改寫後 `todo` 不再列、`state.fixes` 空。（同張卡的原因與編號併成一筆，不是三筆，語意相符。） |
| 2 | 過 | 同一張卡加一個只有標題的段 → 原因併成「出處點不開、有空段」；單獨的空段在 `test_lint_empty_sections` 與同一輪實測都是「有空段」。 |
| 3 | 過 | `ledger.tsv` 本週 3 筆 deny、上週 1 筆、`guard-status` 比最近一段工作日誌舊 3 天 → 報告「守門這週擋 3 次（上週 1）」「守門最後一次跑是 …」；待處理一件 `guard_stale`；再跑一次不重複。guard-status 改成今天後該件仍 open（見 T-1）。 |
| 4 | 過 | 一條 40 天前的推測日程（另一條 10 天前）、一個推測實體（日期改 40 天前）→ 待處理兩件（`inferred:agenda` 只帶 40 天那條、`inferred:entity`）；再跑 `kb lint` 件數不變；10 天前的沒列。 |
| 5 | 過 | 骨架檔建好、`skeleton.record`，改 `CLAUDE.md` → 待處理一件 `skeleton:CLAUDE.md:<指紋>`；`kb pending resolve` 後再 `kb lint` 不重開；又改一次才再開一件。舊範本的卡數在報告數字段（「舊範本的卡 0」）。 |
| 6 | 過 | 230 個舊回合備份 + 收件匣 31 份 + 13000 字綜合卡：`.system/revert` 鎖被占時 `kb lint` 不清、報告一句「清理這次沒做：另一個備份、還原或退回正在跑，下週再清」；鎖放開再跑 `done`「清掉 211 個回合備份，空出 2 MB」、`versions` 夾剩 20（`versions_min_turns`）；報告數字「收件匣 31 份」；待處理 `synthesis_big:案子/信義王/信義王.md`。 |
| 7 | 過 | 沒有任何備份 → 報告建議下一步「還沒備份過，說「幫我備份」就好」。`versions` 不能寫用替身（`_writable` 回 False，spec 允許）→ 待處理 `versions_unwritable`。 |
| 8 | 過 | `mklink /J` 把 `.system/temp` 指到外面 → 待處理 `system_link`（「…捷徑（.system/temp）…」）；工作日誌一行 `done:false` 兩天前 → `done` 補完、`done: true`、note「沒有改動」。（`sizes` 順帶把 junction 外的檔算進知識庫大小，見 T-13。） |
| 9 | 過 | 3 張報價卡製卡日期 10-01、`card_types` 報價那列改成 2 天前 → 待處理一件 `redo_by_profile:報價:<日期>`（「有 3 張卡是之前做的」），`data.ids` 對得上、`do` 是 `kb cards redo --ids …`；跑它 → 「已標成要重做：3 張卡」「連帶要更新的綜合卡：信義王」，`cards todo` 的 `stale` 3 張 `reason`「客戶說卡讀錯了」；`--check` 只列。第四節（`synthesis_sections`）一列比綜合卡新 → `synthesis_fix`「設定檔改了」。（redo 後該件仍 open，見 T-2。） |
| 10 | 過 | 一張壞引用綜合卡 + 一張沒掛實體的卡：`kb lint --json` 的 `ingest` 四個數（unsorted 9、unlinked、synthesis_stale 1、missing）跟 `kb cards todo --json` 算出來的完全一樣。 |
| 11 | 過 | 5 條「口述為準」裁示掛 5 張同卡型（報價）的卡 → 待處理一件 `promote:spoken_wins:報價`（「你說過 5 次「報價」以你說的為準…」）；4 條不列。 |
| 12 | 過 | A 被 B 取代、C 收回、E 被 E2 取代且 E 被另一個實體的綜合卡引用、一筆推算被取代：`kb lint` → 封存檔 `statements-archive.json` 有 A、C（加 `archived` 日期），原檔剩 B、E、E2；被引用的 E 不動；`findings-archive.json` 一筆；`kb lookup 信義王 --json` 前後完全相同。`versions list` 看得到封存檔是這回合建的。 |
| 13 | 過 | 四種各一：`unreadable`（原檔刪了、掃描標不見）、`conflict`（卡不在）、`script_touched`（檔不在清冊）→ 健檢關成 `done`、`how`「健檢確認已不成立」；`close`（實體設結案）→ 由 `kb entity progress` 當場關（客戶回答的那條），健檢不重複關。「關掉 3 件已經不成立的待處理」進 `done`。（誤判另一面見 T-5。） |
| 14 | 過 | open 31 天的 → 健檢收進先放著 `by: lint`、`done` 一句；`kb pending set-aside <編號>` → 「先放著了：…；有變化或快到期會再拿出來」、`by: customer`；找不到 exit 3「沒有這件待處理」；掛了清冊檔的件放著後那份檔改內容、`kb inventory scan`、`kb lint` → `set_aside` 清掉、`returned` 有今天；`data.dates` 是明天的 → 回到前面，10 天後的留著；`待處理.md` 有「健檢查到的」「先放著的」段、處理完的不列；有逾期日程時多「整理時要問你的（1）」。（日期已過的情況不會留著放，見 T-3、T-4。） |
| 15 | 過 | 把 `tests/fixtures/cards/pending.json`（schema 1）放進庫：`migrate.pending` 列出 `.system/pending.json`；`migrate.apply` → `migrated`、檔變 schema 2、每件多 `set_aside`／`returned`、`待處理.md` 重渲染；`kb versions revert` 退回「migrate」那句 → 檔回 schema 1、欄位沒了。另直接跑 `kb lint`（不先遷移）也能讀 schema 1 並寫成 2。 |
| 16 | 過 | 2 件 close（about 信義王）+ 4 件無關：`kb asks --all --json` 6 件；session 1 `kb asks --about 信義王 --json` → `asks` 2、`others` 4、`others_line`「還有 4 件要你決定的事，有空說『看待處理』」；同 session 再跑 → `others_line` null；新 session → 又有；用別名「信義王宅」也認；加一件明天到期的無關件（`data.dates`）→ 排進 `asks` 最前（`urgent: true`）；`--all` 全部、有 `set_aside` 件數、沒有 `others_line` 欄；`kb asks set-aside <key>` → 成功句、再 `--all` 少一件且 `set_aside` 1；不存在的 key exit 3「沒有這個問題」；不住在 pending.json 的 key（`overdue:…@指紋`）寫進 `set_aside.json`。（key 對象指紋變了回來的路徑只讀程式確認：key 含問句指紋。） |
| 17 | 過 | 對話裡（`turn.start` 帶 session）跑 `kb lookup 信義王` → 回合檔 `touched.entities` 有信義王；不帶 `--about` 跑 `kb asks --json` → 信義王那件在 `asks`；下一句（新回合、沒查）→ `asks` 空、只剩 others。 |
| 18 | 過 | 改 `待處理.md`（一條改成 `- [x] …`、一條刪掉）後，另一個回合加一件待處理觸發重新產生 → `.system/handedits/<時間>-待處理.md` 存著她那份、待處理多一件 `handedit`、新檔寫了（含「你手改過的（1）」段）；`kb lint handedit --json` 分 `checked`（帶 `p-` 編號）與 `removed`；`裁示.md` 刪一行 → `removed`（`r-` 編號）；`日程.md` 改日期 → `changed_date` 且 `to` 是她寫的日期；`--done <編號>` → 「記下了：照你改的做完了」，重複再 `--done` exit 3；總目錄加一行字再 `kb cards index` → 只存 `.system/handedits/`、不開待處理、總目錄換回新的；工作日誌月檔手改再 `kb journal render` → 只存、報告「這個月你改過總目錄 0 次、工作日誌 1 次，你那份都留著」。退回（`kb versions revert`）把待處理.md 換回舊版 → 之後再寫不算手改。 |
| 19 | 過 | A 被 B 取代、`kb statement withdraw B` → 人讀多「它取代過：…（2026-10-25）」，`--json` 有 `replaced`；`kb statement restore A` → 「恢復了：…（說「退回」可以改回去）」；B 還有效、從沒被取代、不存在 → 三種都 exit 3「這條沒有被取代，或取代它的那條還有效」；封存檔裡的 A 也能 restore。（我造的綜合卡已經照 B 之前的 A 寫，restore 後剛好沒變，所以沒看到「列待更新」；程式面由 `test_scripts_statement_cli` 守。） |
| 20 | 過 | `lint.json` 的 `last_background` 8 天前：真的 `hooks/session.py` 跑 0.17 秒，輸出沒有多一行健檢，`last_spawn` 記今天，子行程自己跑完把 `last_background` 寫成今天；同一天第二次開場 0.15 秒、不再開。`last_report` 是上上個月 + 有上個月的 `month_done` → 背景寫出 `系統/健檢報告/<上個月>.md`、待處理多一件 `report`、更早那件自動 `done`；沒有寫這個月的報告；背景用自己的回合 `versions/<時間>-lint`；`hook-errors.log` 不存在。 |
| 21 | 過 | 報告：標題、三行「這是什麼」、一句話（「大致正常；要你決定的事比上個月少 2 件」，有 `last_counts` 才比）、「要你決定的」用 `> [!todo]-` 摺疊並寫「已放進待處理（3 件，這是當時的狀況…[[待處理]]）」、「先放著超過一個月的」（有才寫）、建議下一步、數字；沒內容的段（這個月替你做了什麼）整段不寫；程式沒印任何編號；`kb lint` 連跑兩次同月只有一個檔、內容一致。 |
| 22 | 過 | `rulings.json` 寫壞 → `kb lint --json` 照跑完、exit 0，`failed_checks`「出處、裁示升格、整理擱著的、整理時要問你的」，報告每項一句「X這項這次沒查成」，`hook-errors.log` 一項一行（source `lint`）。（但一句話仍寫「一切正常」，見 T-16。） |
| 23 | 部分 | `tests/evals/lint.json` 20 句、10 該觸發 10 不該（`test_skill_lint` 在全套內過）；描述長度與本文 3000 字上限由 `test_budget` 守（全套過）。run_eval 在 Windows 跑不了，依派工跳過；D-132 新舊版對照與觸發句實測延到桌面版確認。 |
| 24 | 過 | 全套 2999 個 exit 0；`claude plugin validate .` exit 0。 |

## 3a 裁定的 18 個疑義：做法有沒有漏洞

1. 測試開關：只關背景健檢，沒有提權面；`tests/__init__.py` 對所有測試程序預設設它（見上，黑箱 hook 測試要自己拿掉）。客戶環境不會設。無漏洞。
2. `renders.json` 不備進回合、記最近 20 個指紋：待處理、日程、裁示即使超過 20 次也因 `diff` 為空不誤開；**總目錄與工作日誌沒有 `diff` 把關**，一個回合寫超過 20 次再退回會被當手改（T-12）。
3. 工作日誌手改只存 handedits：實測過（驗收 18）。
4. 「整理時要問你的」是上次健檢算的：實測有逾期日程時出現；kb asks --all 另會寫入 `renders.json` 的 `asks`。可。
5. 背景健檢自己的回合：實測 `versions/<時間>-lint`、不碰對話的 current。副作用：它是最近一個可退回的回合（T-18）。
6. `last_report` 語意：實測一致；但本月第一次若先由前台 `kb lint` 跑，後台下個月不補通知（T-17）。
7. 守門沒在跑 ≥ 2 天：實測過；全新庫沒有 guard-status 但已有對話也會開（可接受）。
8. 紀事段以外標：實測過（紀事段裡的已收回不標，完全不存在才標）。
9. 封存要整理到與正文都沒引用：實測過（E 被引用不動）。
10. 骨架檔只開一次、又改才再問：實測過。
11. `set_aside_wake_days` 1 天：實測過；**但過去的日期一律算到期**（T-3、T-4）。
12. `kb asks` 會寫檔：寫 `asks_told`（回合檔）與 `set_aside.json`、`renders.json`；守門把「單一 kb 呼叫」一律放行，不受影響；`hooks/guard.py` 的 `AGENT_ALLOW` 沒加新子命令，card-maker 呼叫會被 deny。終端機跑 `kb asks` 讀的是 `current.json`（最後一個對話的），見 T-23。
13. `kb cards redo --ids`：實測有 `--check`、拒絕句「沒有寫好的卡可以重做」「給一張卡的編號，或用 --job 給整理的編號，擇一」；只收清冊 active 且卡寫好的。可。
14、15：句子已改，實測 `待處理.md`「由程式產生；在這裡打勾或刪掉一行，我下次會照著做」；`kb asks` 的 `tell` 不再帶兩份寫法不同的件數。**`裁示.md` 的表頭還留著「怎麼用：要改跟我說；直接改這個檔不會生效」，跟下一行矛盾（T-19）。**
16. note、produce 本文貼上限：`test_budget` 過。
17. carding.md 那句：已讀，沒意見。
18. 對話裡跑健檢算目前回合、退回一起退：實測 `kb lint` 在對話裡把口述封存，`kb versions revert` → 封存檔移除、口述回到原檔、`lint.json` 移除。

## 發現

編號 T-n；嚴重度：擋發行／應修／可留 backlog。「重現」欄的腳本在我的暫存夾，要的話可以給。

### 應修

**T-1　`lint` 類待處理條件消失後不會自動關（含 `report` 以外的所有健檢件）**
- 位置：`scripts/kb/lint/runner.py` `_untrue`（只認 unreadable／conflict／close／script_touched）、`pending.add_lint`。
- 重現：做一個 40 天前的推測實體 + 守門 6 天前才跑過的庫，`kb lint` 開出 `guard_stale`、`inferred:entity`；`kb entity confirm 王宅`、把 guard-status 改成今天；再 `kb lint` → 兩件仍 open，「要你決定的 2 件」不變。同理 `redo_by_profile`（重做完了）、`promote:*`（裁示拿掉了）、`synthesis_big:*`（精簡了）、`system_link`（捷徑移掉了）。
- 後果：她被問一件已不存在的事，件數虛高；只有 AI 記得 resolve 才會關。
- 建議：runner 把這次每項「有成功跑完」的檢查沒再回的 `lint` 類 key 關掉（`how` 寫健檢確認已不成立）。
- 嚴重度：應修。（code review 與我各自找到。）

**T-2　她處理過的 `lint` 件下週又重開**
- 位置：`scripts/kb/_lib/pending.py` `add_lint`（只認 `status == "open"`，只有 `once` 的算答過）。
- 重現：上面第 4 條的推測日程，`kb pending dismiss <編號>` → 再 `kb lint` → 狀態 `['dismissed', 'open']`，又一件新的。`resolve` 後也一樣。`redo_by_profile` 她說好、已 `kb cards redo --ids`，整理沒做完前舊卡的製卡日期還是舊的，下週又開一件同樣的（code review 的實驗）。
- 後果：「不用管」無效，條件還在就每週出一件；跟 T-1 是同一組缺口的兩面。
- 建議：dismiss／resolve 的 `lint` 件記下 key（連同當時的對象指紋），條件沒變不重開；`redo_by_profile` 排除清冊已標 `redo` 的卡。
- 嚴重度：應修。

**T-3　`inferred:agenda` 的 `data.dates` 帶已過去的日期，先放著無效**
- 位置：`checks/inferred.py:47`、`_lib/plan.py` `_urgent`（`str(d) <= limit` 過去也算）與 `visible`（urgent 一律保留）、`_lib/pending.py` `due_back`（同一個比較）。
- 重現：一條 40 天前建立、日期 5 天前的推測日程 → `kb lint` 開出 `inferred:agenda`（`data.dates: [5 天前]`）；`kb pending set-aside <編號>` → `by: customer`；再 `kb lint` → `set_aside: None`、`returned` 是今天（被 `wake_due` 拉回）；`kb asks` 裡它是 `urgent`，每個回答末尾都佔名額。
- 後果：她說「先不要」沒用；日程逾期本來就有 `overdue` 題在問，這件只該在日期未到、還剩 ≤ 1 天時算有時間性。
- 建議：`_urgent` 與 `due_back` 的日期條件改成「今天 ≤ 日期 ≤ 今天 + wake_days」。
- 嚴重度：應修。

**T-4　對逾期日程題說「先放著」：成功句說放著了，那題照列**
- 位置：`asks_cli._set_aside`、`plan.visible`（urgent 保留）。
- 重現：agenda 有一條 3 天前到期的承諾 → `kb asks --all --json` 有 `overdue:a-…@指紋`（`urgent: true`）；`kb asks set-aside <key>` → 「先放著了：10/22 給報價…過了，完成了嗎？；有變化或快到期會再拿出來」；再 `--all` → 那題還在、`set_aside` 0。
- 後果：成功句騙人；她以為不會再問。這是 spec 的灰色地帶（D-225 時間性的照講 vs D-226 她說先不要），需要設計 session 裁定：逾期題要不要可以放著（放到什麼時候回來），或 set-aside 對 urgent 題直接拒絕並說「這件有期限，我還是會提醒」。
- 嚴重度：應修（待裁定）。

**T-5　`_untrue` 把「仍然讀不到」誤判成已不成立**（code review #4，未親自重現）
- 位置：`runner.py` `_untrue` 的 unreadable 分支：`e["id"] in ctx.cards()` 當成「換版後讀得到」。
- 情境：檔被換成有密碼的新版，指紋變、舊卡還在等重做，`kb convert` 失敗開 `unreadable` → 下次健檢因為「id 在 cards 裡」關掉它，下次整理又開，每週循環。
- 建議：「讀得到」要看卡的指紋追上現在的檔，或檔不再 stale。
- 嚴重度：應修。

**T-6　封存的口述、推算不跟實體改名／合併**（code review #5，未親自重現）
- 位置：`_lib/statements.py` `rename_entity`、`_lib/findings.py` 同（只改現行檔）。
- 情境：A 被 B 取代、兩條都封存 → 實體「信義王」改名 → 收回 B（在封存檔裡）並 `restore A`：A 回到有效清單，`entities` 欄還是舊名，`active_for` 與綜合卡依據對不上。
- 建議：rename／merge 也換封存檔，或 restore 時照現在的清單轉一遍。
- 嚴重度：應修。

**T-7　`kb lint` 連跑，「替你做了」重複記**
- 位置：`checks/_synthesis.py` `fix_finding.apply` 每次都回「標了 N 張…」，即使 `state.add_fix` 早就標過。
- 重現：同一個庫連跑兩次 `kb lint --json`：第一次 `summary`「替你做了 1 件事」，第二次 2 件，`lint.json` 的 `month_done` 兩條一模一樣，報告「這個月替你做了什麼」重複；每週背景跑一次就每週加一條，月底報告和「跟上個月比」失真。
- 建議：`add_fix` 回有沒有新增，沒新增不記。
- 嚴重度：應修。

**T-8　新檔沒進 `folders purge`**（security review #1；程式面我用 grep 確認，端到端沒重現）
- 位置：`scripts/kb/_lib/purge.py` `_current_state`（只清 pending、agenda、rulings、findings），沒有 `statements-archive.json`、`findings-archive.json`、`.system/handedits/*`、`系統/健檢報告/*.md`、`lint.json` 的 `month_done`／`synthesis_fix`、`set_aside.json` 的 `question`、`renders.json` 的 `asks`／`saved`。
- 情境：某夾的卡被排成「不想讓 AI 看到」，這夾衍生的口述或推算原先已被健檢移到封存檔；`kb folders exclude … --kind hidden` 清完，封存檔裡的文字還在，AI 可以 Read。健檢報告「要你決定的」、handedits 存的待處理.md 也可能留著檔名與標題。我試著在 fixture 上做端到端，那次排除一張卡也沒匹配到（「卡拿掉 0 張」），所以只能確認「沒有任何 purge 程式碼碰這些檔」，沒有看到實際殘留。
- 建議：purge 掃這幾個檔（跟 findings.json 同一個 `drop_findings` 邏輯）、報告與 handedits 比照 `journal.scrub` 遮路徑。
- 嚴重度：應修（承諾面）。

**T-9　`inferred:entity` 的 `do` 沒加引號**
- 位置：`checks/inferred.py:57`：`f"kb entity confirm {n}"`，只擋名字含空白。
- 重現：`entities.name_problem` 對 `x;calc`、`a&b`、`o'neil`、`x(y)` 都回 None（我實測），所以這些名字合法；AI 照 `do` 原樣跑，shell 會當成別的指令或壞掉。其他地方都用 `plan.cmd`／`shell_arg`。
- 嚴重度：應修（低）。

### 低優先或可留 backlog

**T-10　手改備份失敗只記 log，之後照樣覆蓋她那份**（code review #10，未重現）
`pending._hand_edit`、`renders.handle_list`、`renders.keep_only` 的 `except` 吞掉 `keep` 失敗後仍重寫。跟 spec「她改的那份一定留得住」不符，至少 keep 失敗時應略過這次重寫。可留 backlog（磁碟滿才會碰到）。

**T-11　UTF-8 BOM 被當成手改**（我重現）
用記事本另存（加 BOM、CRLF）不改字的 `待處理.md`，下一次寫入 → 開出一件 `handedit`（`other` 是 `﻿# 待處理` 那行）。CRLF 本身不會，BOM 會。`renders.check` 讀檔時去掉 BOM 就好。可留 backlog。

**T-12　一個回合重寫超過 20 次再退回，總目錄／工作日誌被當成手改**（我重現總目錄）
`renders.record` 只留 20 個舊指紋；在一個回合裡手動寫 25 次總目錄（整批製卡每寫一張卡就重寫一次，>20 張很常見）再 `kb versions revert` → 下一次 `kb cards index` 把退回的那份存進 `.system/handedits/`，報告多一句「這個月你改過總目錄 1 次」。待處理、日程、裁示因為 `diff` 為空不受影響（我試過待處理）。不丟資料，只多一份複本和一句錯的報告。可留 backlog。

**T-13　`sizes._walk` 會走進 Windows junction**（我重現、code review 與 security review 也找到）
只用 `os.path.islink` 排除；Python 3.14 對 junction 回 False。`.system/temp` 指到外面有 3 MB 檔的夾 → 「知識庫 3 MB」（原本 1 MB）。junction 指回知識庫自己的情況我試了，2.2 秒就跑完（路徑太長自然中止），沒有卡住。`system_dir._is_link` 與 `backup._is_link` 已有處理 reparse point，這裡漏了。可留 backlog。

**T-14　狀態檔型別壞掉時不穩**（我重現）
- `renders.json` 是合法 JSON 但 `history` 內容型別錯（例如 `{"系統/待處理.md": 5}`）→ `renders.record` 丟 `TypeError`，`pending.add_lint` 往外丟；JSON 已寫、`待處理.md` 半套。
- `lint.json` 的 `last_counts` 是字串 → 前台 `kb lint` 印 Python traceback、exit 1；`last_report` 是數字 → 背景每次 `TypeError`，只有 `hook-errors.log` 一行，健檢永遠不跑。
檔頭寫「壞檔當空的」，但只驗了最外層。可留 backlog。

**T-15　`last_background` 是未來日期，背景健檢無聲停擺**（我重現）
`runner.opening` 的 `(today - last).days <= lint_background_days` 在負數時為真，`last_background=2099-01-01` 時永遠不開。電腦時鐘曾調到未來就會中。負數視為異常、照過期處理即可。可留 backlog。

**T-16　有項目沒查成時，一句話仍說「一切正常」**（我重現）
驗收 22 那個庫：`failed_checks` 四項，`summary`「一切正常。」。建議有 `failed_checks` 時不說「一切正常」。可留 backlog。

**T-17　本月第一次若是前台 `kb lint` 先跑，之後的背景不補上個月的報告通知**（code review #16，未重現）
`runner.py:208-218`：`last_report` 為空就直接設成 prev，不寫報告也不開 `report` 件。報告檔本身（前台寫的）還在，只是少了「報告出來了」那件。可留 backlog。

**T-18　背景健檢的回合是最近一個可退回的回合**（我重現）
`kb versions list` 第一行是「那句「（背景健檢）」」；開場後她第一句如果是「退回」，退的是健檢做的事（封存、關件）而不是上一次她做的事。R-05 規定先列出、客戶確認，所以不會悄悄退掉，但列表第一行會讓人一頭霧水。可留 backlog：背景回合在 `versions list` 排後面，或 `revert` 預設跳過 `*-lint`。

**T-19　`裁示.md` 表頭自相矛盾**（我看到）
「怎麼用：要改跟我說；直接改這個檔不會生效。」下一行「由程式產生；在這裡打勾或刪掉一行，我下次會照著做。」（疑義 14 改了第二句，沒改第一句。）應修（文字），很小。

**T-20　月報「要你決定的」會列出「上個月的健檢報告出來了」那件本身**（我重現）
補寫上個月報告時，舊的 `report` 件（`done` 之前）被算進「要你決定的 1 件」。報告和一句話的件數都多算。可留 backlog。

**T-21　`開原檔` 連結壞的卡，每週重複標它的綜合卡**（code review #13）
卡連結壞（來源碟拔掉）是檔案卡的屬性，重寫綜合卡修不了；整理照做、sha 變、`prune` 拿掉、下週又標。spec 清單 1 就是這個字面做法。可留 backlog。

**T-22　預設設定檔的列都是「推測」，滿 30 天每個客戶都會收到一件「設定檔有 N 列是我推測的」**（我重現，把日期改 40 天前：19 列 → 一件）
這是 spec 字面。客戶很可能永遠不去確認，30 天後自動進先放著。可留 backlog：init 時預設列不算推測，或只看她後來加的列。

**T-23　終端機跑 `kb asks` 讀的是最後一個對話的旗標與 `touched`**（code review #15，我也看到 `_others_line` 讀全庫唯一的 `current.json`）
最後一個對話已經說過 `others_line` 時，終端機永遠拿不到；`touched` 沿用別人的。兩個對話同時開在同一個庫時也會互相影響。可留 backlog。

**T-24　`ingest` 件數在關掉不成立的待處理之前算**（我重現）
`conflicts` 在同一輪被關掉那件之前算，輸出還寫 1。數字滯後一輪。很小。

### 其他（未驗證或影響很小，供參考）
- code review #11：`statements.restore` 從封存檔搬回時先寫封存檔、後寫 `statements.json`，中間出錯 A 兩邊都不在（封存檔已備進回合，`versions revert` 能救）。
- code review #12：`statement withdraw` 寫入成功後，`replaced_of` 讀到壞掉的封存檔丟 `ValueError`，CLI 說「狀態檔讀不到」exit 3，但收回其實生效了。
- code review #17：健檢報告檔沒備進回合，退回健檢回合時報告留著，與狀態不一致。
- security review（我沒驗證）：`citations._open_broken` 對卡檔頭的 `file://///主機/分享/x` 會對 UNC 路徑做 `os.path.exists`，惡意卡可能觸發對外 SMB／NTLM 連線（需要 card-maker 被 prompt injection）；每週背景 `clean.run` 可能清掉「升級前」快照（規則本來就是留 `snapshots_keep` 份）；handedits 與 `diff.other` 存她那份文字時沒 `mask_secrets`；開場「先記今天開過」在鎖外讀 `last_spawn`，兩個對話同時開場有極小的重複開窗口。
- security review 檢查過、沒問題：背景子行程用 argv list、沒有 shell、vault 路徑只進 `cwd`；`WIKI_WITH_WILLY_NO_BACKGROUND` 只能關掉健檢；`AGENT_ALLOW` 沒加新子命令；`kb asks set-aside <key>` 沒有注入面；報告月份與 handedits 檔名都來自程式常數與時間。

## 沒測到的
- 觸發句與 D-132 新舊版對照（延到桌面版確認）。
- 桌面版實際跑背景子行程（我用真的 hook 與 detached 子行程在 Windows 終端機環境跑，行為正常；桌面版 hook 時限與環境繼承沒驗）。
- SMB／NTLM、跨電腦（OneDrive 同步造成的 `lint.json` 衝突）。
- `plugin-dev:plugin-validator` agent（只跑了 `claude plugin validate`）。
