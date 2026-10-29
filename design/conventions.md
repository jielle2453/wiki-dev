# 約定

日期：2026-10-11
給誰看：你與所有 session。
什麼時候更新：只在設計 session 改。其他 session 覺得約定不夠用，寫進 backlog。

## 一、資料夾

| 代號 | 放什麼 | git |
|---|---|---|
| `<repo>` | repo：plugin 根目錄、程式、測試、設計文件 | 是 |
| `<worktree>` | 一題的實作與測試：`<repo>` 旁邊的 `<repo 夾名>-<題目>`，分支 `spec/<題目>`（第三節） | 是 |
| `<測試環境>` | 確認環境：假來源、各題確認用的總資料夾（結構見第六節） | 否 |
| `<repo>\design\reference\` | 舊程式：`plugin.zip`（舊 llm-wiki v0.13.1）、`llm-wiki-plugin-1.13.0.zip`（llm-wiki-plugin），加上 Karpathy 原文。唯讀，spec 的來源對照解壓到 repo 外再看，不解壓進 repo | 是 |
| `<repo>\tools\testdata\` | 假來源 `來源.zip` 與產生它的 `generate.py`（第六節） | 是 |

process 與本檔的路徑一律寫代號；開場訊息貼出去之前換成自己電腦的位置：

| 誰的電腦 | `<repo>` | `<測試環境>` |
|---|---|---|
| jielle2453 | `%USERPROFILE%\Desktop\llm-wiki-j` | `%USERPROFILE%\Desktop\llm-wiki-test` |
| jacky | （自己填） | （自己填） |

plugin 名稱 `wiki-with-willy`（D-069），指令前綴 `/wiki-with-willy:`；repo 資料夾在 jielle2453 的電腦叫 `llm-wiki-j`，從 GitHub clone 預設叫 `wiki-with-willy`，兩個都可以。不能叫 `llm-wiki`，會跟已安裝的撞。

## 二、文件

```
llm-wiki-j/
├─ README.md            給服務人員與使用者：裝、用、升級
├─ CLAUDE.md            給改 repo 的 Claude：改完要做的事、不准、ops 索引
├─ ops/                 原始碼地圖（map-*.md，按需讀）
├─ CHANGELOG.md         一版一段：改了什麼／為什麼／commit／spec
├─ LICENSE
└─ design/
   ├─ process.md        流程
   ├─ conventions.md    本檔
   ├─ architecture.md   架構
   ├─ decisions.md      決策 D-nnn，最前面有索引
   ├─ incidents.md      事故 I-nnn
   ├─ backlog.md        待辦與延後 B-nnn
   ├─ specs/            YYYY-MM-DD-題目.md
   ├─ reports/          題目-測試.md、題目-確認.md
   └─ reference/        舊程式的 zip 與 Karpathy 原文。唯讀
```

遠端是私有 repo。研究報告、行銷文件、客戶資料在團隊 repo `wiki-studio`，不放這裡。

**一件事只住一個地方：**

| 內容 | 只放這裡 |
|---|---|
| 門檻與預設數字 | `config/defaults.json`，每個鍵旁一個 `_why_<鍵>` |
| 事故 | `incidents.md`；CHANGELOG 與 skill 只引用編號 |
| 決策與理由 | `decisions.md`；spec 與規則只引用編號 |
| 某版改了什麼 | `CHANGELOG.md` |
| 延後的想法、別的 session 發現的問題 | `backlog.md` |
| 怎麼改 repo | `CLAUDE.md`；某個檔做什麼看 `ops/map-*.md` |
| 怎麼用 plugin | `README.md` |
| 訪談要問什麼 | `系統/客戶設定檔.md` 每節的提示句，住 `scripts/kb/_lib/profile.py` 的渲染（D-052、D-067、D-111） |
| 給客戶看的說明（速查卡、資料去向） | `skeleton/` 或由 build 生成到 `系統/建置報告.md` 前半，不在 design |
| 執行規則 | `rules/`，每條有編號；理由不寫在規則裡 |

**每份文件：** 開頭三行寫日期、給誰看、什麼時候更新（報告另照下面「報告的寫法」）。引用不抄。能從程式推導的清單不手寫；手寫的標「本清單會漂，以 X 為準」。日期 `YYYY-MM-DD`。不新增上表以外的文件，真的需要先改上表。

**狀態詞固定：** 照下面「同一套詞」的狀態那一列。

**誰能寫什麼：**

| session | 能寫 | 不能寫 |
|---|---|---|
| 設計 | 全部 | — |
| 實作 | 程式、測試 | spec、decisions、architecture、README、backlog（發現寫在回報） |
| 測試 | `reports/<題目>-測試.md`（只 commit 這份） | 程式、spec、backlog（發現寫在報告） |
| 確認 | `reports/<題目>-確認.md`（只 commit 這份） | 程式、spec、backlog（發現寫在報告） |

**格式：** `decisions.md` 一條一段，編號 `D-nnn`，五行：日期、選了什麼、為什麼、放棄了什麼、重談條件。`incidents.md` 一條一段 `I-nnn`，四行：來源、發生過什麼、合併版會不會踩、客戶會不會遇到。`backlog.md` 一行一條 `B-nnn`，七欄：#、日期、狀態、嚴重、區域、事、來自；狀態只寫一個詞，說明寫進「事」；照狀態分四區：要處理的（要做、待決）、延後的、不做、做完的，狀態改了就換區。

**狀態與索引：** 決策被後來的決策改到時，在原條第一行加「狀態：作廢／部分修訂／有補充，見 D-nnn」，原文不刪；還沒定的事開成 backlog 的「待決」，不另設未決區、不再用 U 編號。`decisions.md`、`backlog.md`、`incidents.md` 最前面各有索引，新增一條時在對應的區加一行；backlog 換區時索引跟著改。編號不重編。

**同一套詞（索引、backlog、spec、issue、團隊 repo 的開發表都用這些）：**

| 詞 | 值 | 用在 |
|---|---|---|
| 區域 | 清冊與來源、整理成卡、設定與知識、日程、回答、做文件、守門與密碼、回合與日誌、建置、備份與搬家、升級與發行、健檢與待處理、hooks、核心規則與開場、狀態檔格式、skill 文字、架構與共通、流程與文件、延伸（可以寫好幾個；hooks、核心規則與開場、狀態檔格式、skill 文字是最容易撞的） | 索引的分類、backlog 的區域欄、spec 檔頭、issue 的 label |
| 狀態 | 想法、待決、延後、要做、設計中、定稿、開發中、測試中、確認中、發行中、做完、不做 | backlog 用：要做、待決、延後、不做、做完；spec 用：設計中、定稿、開發中、測試中、確認中、發行中、做完；issue 用：待決、設計中、開發中、測試中、確認中、發行中（做完或不做就關掉 issue）；團隊 repo 客製表用：想法、待決、延後、設計中、開發中、測試中、確認中、做完、不做 |
| 嚴重 | 高、中、低；不知道寫「－」 | backlog 的嚴重欄、測試與確認報告的發現表 |
| 急迫 | 高、中、低 | issue 的 label、團隊 repo 客製表 |
| 類型 | 補強、客製、bug | issue 的 label（補強、bug）、團隊 repo 開發表 |
| 引用 | 「報告檔名 #N」、「issue #n」、「B-nnn」、「D-nnn」 | spec、backlog、決策、程式註解、commit 提到時一律這樣寫，後面加一句說是什麼 |

**issue 與 backlog：** GitHub issue 放客戶或團隊要的功能（要排先後、要討論；開之前先給人看；不寫客戶名，哪位客戶要寫在團隊 repo `wiki-studio` 的 `開發/README.md` 補強表）；`backlog.md` 放開發過程自己發現的事（bug、測試低項、技術債、延後的小事），由設計 session 記、給編號（其他 session 的發現寫在回報或報告，見 process 第三節步驟 7）。一件事只住一個地方：backlog 的某條變成要做的功能時開 issue，那條改做完、說明寫「轉成 issue #n」；issue 寫成 spec 時，把同一區的相關 backlog 併進那題一起做、做完一起關。

**issue 的寫法：** 內文照這六段：一句話、為什麼（客戶會遇到什麼）、要的行為、驗收、需要決定的、相關（B-、D-、其他 issue）。label 四種：類型、急迫、狀態、區域（可以好幾個）。誰在做用負責人（assignee）、哪一版做用 milestone，不另設 label。兩個 issue 有同一個區域時，認領前比對各自 spec 的「可以動」，重疊就排先後。

**報告的寫法：** 檔頭四行：日期、給誰看、測的版本（分支與 commit）、做法。測試報告的章節：結論（能不能進下一步）、驗收逐條（過或不過附證據）、發現（表：#、嚴重、內容、證據）、plugin-dev 審查、沒測到的。確認報告的章節：結論、每一步（說了什麼、實際輸出、判定）、落差（表：#、嚴重、內容）。spike：結論、方法、結果、對設計的意思。多輪一律在同一份檔往下加「## 第 N 輪」，發現編號接著上一輪。發現照順序寫 #1、#2、#3，不用字母代號；2026-10-25 以前的報告照舊用字母代號，每份最上面有一行代號說明。

**要查什麼看哪裡（客戶端）：**

| 要查 | 看 |
|---|---|
| 某回合 AI 改了哪些檔、怎麼退 | `.system/versions/<回合>/` 回合帳 |
| 客戶問過什麼 | `系統/工作日誌/` |
| AI 對知識庫改了什麼（白話） | `系統/工作日誌/` 每段的「做了」行，或問「最近改了什麼」 |
| 守門腳本還活著嗎 | `.system/guard-status/<機器>.json` |
| 守門結果變好或變壞 | `.system/ledger.tsv` |
| hook 自己出錯 | `.system/hook-errors.log` |
| 升級過什麼 | `.system/upgrade-history.json` |

## 三、版本控制

| 項目 | 約定 |
|---|---|
| 初始化 | 第一個 commit 只有殼 |
| 分支 | `main` 的程式只在發行時動；設計 session 可隨時在 `main` commit 純 `design/` 的改動，訊息開頭「設計:」。一題一個分支 `spec/<題目>`，實作與測試都在分支上。**實作與測試 session 用 git worktree**：`git worktree add <worktree> -b spec/<題目>`，開在那個夾；主 checkout 永遠停在 `main` 給設計 session。發行 merge 後 `git worktree remove`（2026-10-12 改，I-093 實際踩到） |
| 發行 | 只在決策者說「發行」之後；步驟見 process 第三節第 6 步，一次只一個發行（process 第八節） |
| push | 開工先 pull，做完 push；`design/` 改完當下就 push；不准 force push。實作 session 不 push，分支在發行時併回 |
| 版號 | semver。首位客戶試跑前停在 `0.x`；功能加 minor，修 bug 加 patch |
| commit | 第一行 `<題目>: <一句話>`；結尾 `Spec: design/specs/<檔名>` 加各 session 自己的 Co-Authored-By；用 `git commit -- <檔>` 只提交自己改的檔，不 `-a`（I-093） |
| author | email 用這台機器的 global 設定（2026-10-12 已設）。實作 session `git -c user.name="實作:<題目>" commit`，設計 session `git -c user.name="設計" commit`，都只改 user.name。測試與確認 session 只 commit 自己的報告，user.name 用「<題目>測試」「<題目>確認」。另一台電腦 email 用自己的 |
| 行尾 | `.gitattributes`：`* text=auto eol=lf` |
| 不進 repo | `__pycache__/`、`*.pyc`、`.pytest_cache/`、`.claude/settings.local.json`、`*.tmp`、測試環境、任何客戶資料 |
| 版號對齊 | 測試檢查 `plugin.json` 與 CHANGELOG 最新一段一致 |

## 四、技術基線

| 項目 | 約定 |
|---|---|
| 目標環境 | 客戶用 Claude Code 桌面版，Windows；plugin 由公開清單網址的 marketplace 裝在整台電腦（D-171、D-172）。開發、實作、測試用 CLI 或 VS Code；確認 session 用桌面版，plugin 用本機快照市集只裝在測試知識庫（local 範圍，process 六、B-093） |
| Python | 3.10 以上 |
| 相依 | 核心只用標準函式庫。開發機另裝 `pytest`、`pytest-xdist`（`python -m pip install --user pytest pytest-xdist`），只用來平行跑測試，不進 plugin。唯一選配是 `pypdfium2`（PDF 抽文字與掃描頁轉圖，D-099 修訂），缺了降級並明講；不用 markitdown、pdfplumber、poppler |
| 編碼 | 我們自己的檔（JSON、md、設定、腳本輸出）一律 UTF-8，讀寫帶 `encoding=`；腳本開頭 `sys.stdout.reconfigure(encoding="utf-8")`。客戶原檔由 `kb convert` 偵測：整份試 UTF-8，再試 cp950，都不行標「讀不到：編碼」明講，不靜默取代字元（I-003）。另存的純文字一律 UTF-8，CSV 帶 BOM 給 Excel |
| 平台 | Windows 優先；`pathlib`；長路徑與 Git Bash 路徑都要認 |
| 腳本入口 | 唯一入口 `scripts/kb.py <子命令>`，呼叫寫 `python "${CLAUDE_PLUGIN_ROOT}/scripts/kb.py" <子命令>`。統一 `--json`、`--help`。不用 `python -m`。模型用 Bash 工具呼叫、一次一個指令、路徑加引號、不 cd |
| 門檻 | 全在 `config/defaults.json`；客戶端 `.system/config.json` 覆寫 |
| 狀態檔 | `.system/*.json` 每個帶 `schema_version`；升級含遷移 |
| 真相模式 | JSON 為真，`系統/*.md` 是渲染視圖，頂端三行：這是什麼、怎麼用、由程式產生改了會被覆蓋（D-067）；格式住程式，範例在 `tests/fixtures/` |
| 測試 | 用 `unittest` 寫，`tests/test_<模組>.py`。全套用 `python -m pytest -n auto -q tests` 平行跑（2026-10-26 實測 32 核心約 100 秒，原本 11～13 分鐘；issue #11），沒裝 pytest 的照舊 `python -m unittest discover tests`，結果一樣。開發中只跑 spec「相關測試」列的檔；全套在三個點跑：實作 commit 之後、測試、發行改版號後。全綠才算改完 |
| 預算 | 常駐字數、`rules/core.md` 行數、每個 `SKILL.md` 行數各有上限，`tests/test_budget.py` 守。初始值見 D-070 |
| 權限 | repo `.claude/settings.json` 放行測試與 `kb.py`；客戶端 settings 不放行任何路徑，讀取與 `kb.py` 由守門 hook allow（D-073），高風險子命令放 `permissions.ask` |

## 五、哪個步驟用哪個 skill

搬到 process 第三節「各步驟用哪個 skill」（2026-10-26，那是流程）。舊文件寫「conventions 五」的，看那裡。

## 六、測試資料

位置 `<測試環境>\來源\`，全假，程式生成。正本是 repo 的 `tools\testdata\來源.zip`：第一次把它複製到 `<測試環境>` 再解開，每次確認前用它還原。要改假資料才跑 `python tools/testdata/generate.py <測試環境>`（要 python-docx、openpyxl、reportlab、pikepdf、pillow 與 Windows 的標楷體），再把新的 `來源.zip` 放回 `tools\testdata\` commit。假客戶沿用接案流程演練的「林小姐，接案室內設計師」。

```
<測試環境>\
├─ 來源\            假客戶資料夾
├─ 來源.zip         乾淨備份，每次確認前還原
└─ 總資料夾\        由 plugin 建出來，名字建置時取
```

```
來源\
├─ 客戶案件\  信義王（平面圖說明、會議紀錄×3、進度.xlsx、圖片型 pdf）、大安陳（報價 v1、v2）、內湖李（兩份）
├─ 報價與合約\  信義王（報價 v1.pdf、v2.pdf、合約.docx）、大安陳（報價.xlsx、合約.docx）、範本\
├─ 廠商資料\  型錄×3.pdf（一份掃描型）、廠商聯絡表.xlsx（統編、電話）
└─ 公司行政\  薪資\（假身分證與帳號，要被排除）、請款\×4.docx、舊檔\（舊合約.doc、Big5 備忘.txt）
```

刻意放的情況：同一份報價兩版、完全相同的檔在兩處、掃描型 PDF、圖片型 PDF、`.doc`、Big5、薪資夾含假個資、統編電話、兩份合約付款條件矛盾、一份生成後搬到別夾、一份密碼 PDF。約 40 到 50 份。
