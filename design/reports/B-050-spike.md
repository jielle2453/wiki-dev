# B-050 Obsidian spike 報告

日期：2026-10-29
跑的人：設計 session（jacky）備好假知識庫與 spike 外掛，使用者在桌面 Obsidian 照檢查清單點
給誰看：寫 Obsidian 外掛 spec 的設計 session
環境：Obsidian 1.14.5、Windows 11、Python 3.14.7；知識庫是 `llm-wiki-test/obsidian-spike/知識庫`（從 tags-check 複製、升到 0.27.0），118 張檔案卡、152 份 md；這台的 Claude Code 沒裝 wiki-with-willy，spike 外掛找 kb.py 用寫死的開發 repo 路徑

## 結論表

| # | 題目 | 結論 |
|---|---|---|
| 1 | 開庫 | 第一次開跳「信任作者、啟用外掛」，按一次就進來，外掛自動開首頁分頁。**第一輪使用者選到上一層 `obsidian-spike`**（含 `來源/`），外掛與設定全沒讀到、搜尋把原檔一起搜進去，客戶一樣會選錯：建置要替她把知識庫加進 Obsidian 並打開，不讓她自己挑資料夾 |
| 2 | 骨架出貨 `.obsidian/` | 第一次開時 Obsidian 改寫了 `app.json`、`appearance.json`（換成它的縮排，我們的值留著），沒動 `community-plugins.json`、外掛夾、CSS 片段，另建 `core-plugins.json`、`workspace.json`。之後她改設定 Obsidian 會再寫這些檔：升級不准整檔覆蓋，只補我們要的鍵 |
| 3 | 藏 `檔案索引/` | CSS 片段藏得掉樹上的夾；總目錄、檔頭連結、搜尋照常找得到卡 |
| 4 | 點 docx、xlsx | 「偵測所有副檔名」開著時樹上點 docx 直接用 Word 開。使用者記「docx 要開設定才有」，但 app.json 在開庫時已是 true，可能是第一輪的印象，寫 spec 前請她再看一眼 |
| 5 | 總目錄 | 連結開得了卡；3000 項三層清單摺疊、捲動都順 |
| 6 | 開原檔連結 | 閱讀、編輯模式結果一樣：`[文字](file:///…)` 全部編碼（卡上現在的寫法）、只編空白與 #、角括號包住都不編，三種都開得了；**直接貼網址（不包文字）開不了**；`\\localhost\C$` 網路路徑兩種寫法都開不了。檔頭 properties 裡的「開原檔」也點得開 |
| 7 | 網路路徑 | 外掛用 `shell.openPath` 開 `\\localhost\C$…` 也沒開起來（沒回錯誤）。第一版要當成限制：放在網路磁碟的原檔不能從 Obsidian 開，換成說明或「在檔案總管顯示」；對應成磁碟機代號（Z:）的沒測，要在客戶機確認 |
| 8 | 檔頭 `[[ ]]` | 「相關實體」寫成 `[[名稱]]`，反向連結有出現；使用者說點進綜合卡「好像點不回來」：總覽與綜合卡要有明顯的回上一頁 |
| 9 | 出處〔f-…〕變連結 | 沒成功。外掛索引到 118 張卡，兩個編號都對得到檔名，post-processor 寫法照文件；最可能是她在編輯模式（post-processor 只管閱讀模式）或那頁的閱讀畫面在外掛載入前就畫好了。沒定論，正式外掛要閱讀與編輯（Live Preview 要另寫 editor extension）都測 |
| 10 | 叫 kb 的速度 | 單次 python 起動加 kb 約 280～340 ms，`kb asks` 640～680 ms；首頁要的 6 個指令一個接一個 2.1 秒、同時叫 0.7 秒。沒有黑色視窗閃、中文正常（`windowsHide`、`PYTHONIOENCODING=utf-8`）。首頁要一支 `kb home --json` 一次給齊 |
| 11 | 從首頁打勾 | `kb agenda done` 約 350 ms；`fs.watch` 在 `.system/` 收到 agenda.json、pending.json 的 rename（每次兩筆），首頁接著重讀就更新了，watch 要去抖 |
| 12 | 她開著日程.md 時 kb 改寫它 | 她打在 `日程.md` 最後一行的「測試」從畫面上消失、沒有任何提示。資料沒丟：D-223 認出手改，她那份存進 `.system/handedits/20261029-220004-日程.md`（第 11 行有「測試」）、開了 handedit 待處理。外掛要在 kb 改寫她開著的檔時說一聲；首頁就能改日程，`日程.md` 宜當唯讀看 |
| 13 | 搜尋 | 外掛在 JS 裡全文搜 152 份 md：2～16 ms，壓力測試也在個位數 ms，不用叫 kb。**注音輸入時每按一個鍵都搜一次**（紀錄有「ㄧㄢ」「言ㄑㄧ」），要等選字完成（compositionend）才搜。Obsidian 自己的搜尋會列出檔案索引的卡（CSS 只藏樹） |
| 14 | 甘特圖 | `系統/日程.md` 的 Mermaid gantt 一樣難看（B-072），時間軸要外掛自己畫 |
| 15 | 找 kb.py | `installed_plugins.json` 讀得到，這台沒裝 wiki-with-willy 所以沒驗到；D-019 不准把 plugin 路徑寫進設定，外掛每次載入照 `installPath` 找，要在裝了 plugin 的機器驗 |

## 給 spec 的事

- 新指令 `kb home --json`：首頁一次要的（日程、待處理、要你確認的、事類實體、最近的檔）一支給齊，目標 400 ms 內。
- 建置的 Obsidian 那步替她登記並打開知識庫（`obsidian.json` 或 `obsidian://open?path=`），裝外掛、出貨 `.obsidian/` 照第 2 列只補鍵。
- 卡與綜合卡的連結寫法照第 6 列；網路路徑的原檔照第 7 列。
- 守門的 `RESERVED`（`scripts/kb/guard.py`）加 `.obsidian` 一列；`workspace.json` 會記最近開過的檔名，purge 要遮。
- 外掛寫入一律叫 kb（D-106），回合照 #20 帶 `--source obsidian` 之類的記法，不混進對話的退回。
- 搜尋在外掛裡做，等選字完成；她開著的檔被 kb 改寫要提示。
- 待驗：第 4 列 docx 要不要開設定、第 9 列出處連結、第 15 列找 kb.py、對應磁碟機代號的原檔。

## 檔案

- 假知識庫與 spike 外掛：`llm-wiki-test/obsidian-spike/知識庫/.obsidian/plugins/willy-spike/`（main.js、results.jsonl 是量到的數字）
- 檢查清單與使用者填的結果：`llm-wiki-test/obsidian-spike/知識庫/_spike/檢查清單.md`
