# 流程

日期：2026-10-11
給誰看：你、設計 session、實作 session、測試 session、確認 session。
什麼時候更新：只在設計 session 改。

**一句話：討論與決策在設計 session，實作、測試、確認各開新 session，發行回到設計 session。**

只保留五個概念，不保留表單：驗收準則先於實作；驗證的人不是實作的人；驗證（測試綠）與確認（真實環境跑過）是兩件事；決定要有字和日期；發行要有明確授權，結案要查類似問題。

## 一、角色

| 角色 | 是誰 | 做什麼 | 看得到什麼 |
|---|---|---|---|
| 決策者 | 兩位：jielle2453 與 jacky（Q00jkf），權利相同；本檔的「你」指那一題的負責人（第八節） | 拍板、核可 spec、授權發行 | 全部 |
| 設計 session | 跟你討論的那個 session | 討論、寫決策、寫 spec、發行、結案 | 全部 |
| 實作 session | 新開，在 repo | 照 spec 改程式、補測試、commit | 只有 spec |
| 測試 session | 新開，在 repo | 對驗收準則逐條驗、跑測試 | 只有 spec，不看實作過程 |
| 確認 session | 新開，桌面版，在測試 vault 的總資料夾 | 用客戶會說的話實際操作 | 只有 spec 的確認情境 |

三個新 session 沒有設計 session 的記憶。**spec 是它們唯一的輸入，必須能單獨讀懂。**

## 二、位置

repo、舊程式、測試環境放哪見 conventions 第一節，設計文件有哪些見 conventions 第二節。

plugin 在 CLI 與 VS Code 用 `claude --plugin-dir "<repo>"` 載入（代號見 conventions 第一節）；確認 session 用**桌面版**，plugin 由本機 marketplace 載入（做法見第六節確認 session 的開場訊息與 B-093）。確認 session 開在 `總資料夾\`。不放在同步資料夾底下，除非那一題就是要測占位檔。

## 三、步驟

1. **討論與決策**（設計）。每個抉擇當場寫進 `decisions.md`。你說「可以」才算定；只在對話裡講過的不算。
2. **寫 spec**（設計）。一題的大小以實作 session 一次對話做得完為準。**驗收準則沒寫完，spec 不算完。** 你看過說可以，狀態改「定稿」才交出去。從 issue 來的題，先看 `backlog.md` 索引同一區，相關的列進 spec 一起做、做完一起關。每一步換階段時，spec 的狀態與 issue 的狀態 label 一起改（開發中、測試中、確認中、發行中；issue 沒有「定稿」，spec 定稿時 issue 還是設計中）；發行後關 issue。
3. **實作**（新 session，在 repo）。只給 spec。只改「可以動」列的檔。有疑義停下來回報，不自己決定。寫的時候只跑 spec「相關測試」列的檔（`python -m pytest -q <檔>…`）；做完 commit，**commit 之後**才跑全套一次看 exit code（全套的跑法見 conventions 技術基線「測試」；`test_repo_hygiene` 只查已追蹤的檔，commit 前的綠不算，I-112），紅了修完再 commit。回報之前對自己的 diff 跑一次 `/code-review high`，修掉正確性的問題（風格的不用）再 commit。不 push。回報改了哪些檔、commit hash、測試結果、疑義，以及 spec 以外發現的問題（不寫進 backlog）。
4. **測試**（新 session，在實作的 worktree）。只給 spec。逐條驗，每條寫過或不過附證據。不改程式。報告存 worktree 的 `design/reports/<題目>-測試.md`，只 commit 這份報告。報告寫好後，照 spec 就修得好的發現（驗收不過、正確性的錯）直接 SendMessage 給實作 session 修，修完只驗那幾條加無退步，最多兩輪。要改 spec 或客戶看得到的發現回設計 session；兩輪後還沒過也回設計 session。設計 session 收到時才記裁定。派測試的設計 session 要在派工時把實作 session 的名字給它。
5. **確認**（新 session，在測試 vault；也可以你親自做）。先還原來源。照「確認情境」操作，記實際輸出與落差。不改程式。報告存實作 worktree 的 `design/reports/<題目>-確認.md`，只 commit 這份報告。確認情境分兩種，spec 裡各自標：
   - **自動**：客戶的話與預期結果。在 `<測試環境>` 的知識庫複本用 `claude -p --plugin-dir <worktree>`，一句一個新對話跑，判過或不過，附回答原文。權限模式用預設，不准 auto 或 `--dangerously-skip-permissions`（auto 會替守門擋掉，守門有洞也測不出）。守門的情境看 `.system/ledger.tsv` 有沒有那筆 deny、理由對不對，只看原檔沒變不算過。
   - **人眼**：開場訊息、桌面版畫面、甘特圖這類只有人看得到的；要客戶按「允許」的動作（`-p` 沒人按）；只有市集安裝才有的（升級換版、按停止、關對話，`--plugin-dir` 跟市集安裝不同，B-093）。只有這些請人看。
6. **發行**（設計）。測試與確認都過，**你說「發行」才做**：先照第八節第 4 條佔鎖，併回 main、bump、同 commit 寫 CHANGELOG（這段開頭要有「給客戶的一句話」，沒寫不准發行；這時才填該段的 commit 欄，寫實作 commit 的 hash；實作時寫「發行時填」）、`python tools/release.py build --prepare` 把這版骨架指紋加進同一個 commit、**bump 後重跑全套且以 exit code 為準**（v0.2.0 發行時 bump 讓寫死版號的測試紅了，指令鏈用 grep 看結果沒擋住，tag 已推出去才補修，I-105）、tag、push。
7. **結案**（設計）。把實作回報的 commit hash、測試與確認報告路徑填進 spec 紀錄節。回報與報告裡沒處理的發現記進 backlog（來自寫「報告檔名 #N」）；只有設計 session 給 B 編號，先 pull 再編。對 `incidents.md` 與舊程式碼查類似問題，有就進 backlog，沒有就在 spec 寫「已查，無」。spec 改「做完」附版號。

設計 session 在 main 上改了 spec（回疑義、加裁定）之後，實作、測試 session 開工前先 `git merge main`，讀到的 spec 才是新的。

### 小題走輕流程

一批小修（每條幾行、不改客戶資料格式、不用新的 D）走輕流程：spec 只寫三節，要做的事（一條一列：哪個檔、哪一句或函式、改成怎樣）、可以動／不可以動、驗收準則（一條一個指令或預期輸出）；實作加一輪測試，測試照步驟 4 直接回實作；只有客戶看得到的幾條要確認，優先自動；做著做著發現要決定的就拿出這批，另起一題。

### 各步驟用哪個 skill

| 步驟 | 用 |
|---|---|
| 討論與決策 | 一次一題、候選加推薦（設計 session 的做法）；定目錄時 `plugin-dev:plugin-structure`；寫或改 skill 前 `plugin-dev:skill-development` 與 `skill-creator:skill-creator` |
| 寫 spec | 本流程的範本。不用 `superpowers:writing-plans`，兩份會漂 |
| 實作 | 先寫測試、看它紅了再實作；寫的時候只跑相關測試，收尾 commit 之後實跑全套看 exit code 才回報（這兩條寫在開場訊息裡，不靠 superpowers）；碰到什麼用對應的 `plugin-dev:hook-development`／`skill-development`／`command-development`／`agent-development`；寫或改 skill 描述時再用 `anthropic-skills:skill-creator`（內建，不用裝）寫描述、建 `tests/evals/<skill>.json` 的 20 句（D-091），描述要守 D-070 的 150 字；測試紅了先找出原因再改，不猜著改 |
| 改寫既有 skill | 照 D-132：`skill-creator` 的新舊版對照（同幾個真實情境，舊版快照與新版各跑一次）；本文照 D-132 五條自查，再跑 agent `plugin-dev:skill-reviewer` |
| 實作收尾 | 回報前對自己的 diff 跑 `/code-review high`，修掉正確性的問題；動過 manifest、目錄、hooks.json 跑 agent `plugin-dev:plugin-validator`；動過 SKILL.md 跑 agent `plugin-dev:skill-reviewer` |
| 測試 | `code-review` 等級 high；碰守門、權限、路徑時加 `security-review`；改了 skill 描述時用 `anthropic-skills:skill-creator` 的 `run_eval` 跑 `tests/evals/<skill>.json`（門檻見 D-091），在同時裝著舊 `llm-wiki` 的機器上跑 |
| 確認、發行 | 無，照流程手動 |

plugin-dev 要先裝：`claude plugin install plugin-dev@claude-plugins-official`（使用者層，每台開發機各裝一次）。

superpowers 選用、預設停用（2026-10-20）：它在每個對話開頭注入一大段說明，多花用量、影響模型行為，啟用是整台電腦一起生效；它在這裡只提供先寫測試與收尾驗證，兩件都已寫進流程。

不用：`cowork-plugin-management:*`、`plugin-authoring`、`plugin-dev:mcp-integration`、`superpowers:subagent-driven-development`、`executing-plans`、`finishing-a-development-branch`。

## 四、不過關時

| 情況 | 怎麼走 |
|---|---|
| 測試不過 | 報告交給實作 session，只修報告列的項目，回步驟 4 |
| 確認不過 | 設計 session 判斷是 spec 錯還是實作錯。spec 錯回 1；實作錯回 3 |
| 實作中發現別的 bug | 不順手修，寫進回報；設計 session 記進 backlog，另起一題 |
| 實作 session 對 spec 有疑義 | 回設計 session 決定，更新 spec 再繼續 |
| 任何 session 想改 spec | 不行，只有設計 session 能改 |

## 五、spec 範本

```markdown
# <題目>
日期：
狀態：設計中 ｜ 定稿 ｜ 開發中 ｜ 測試中 ｜ 確認中 ｜ 發行中 ｜ 做完
版本：（發行後填）
來自：issue #n；併入 B-nnn、B-nnn（沒有寫「無」）
區域：（照 conventions 的區域，可以好幾個）

## 目的
解決什麼、對應哪個使用者時刻。

## 決策
引用 decisions.md 的編號，或列：選了什麼、為什麼、放棄了什麼。

## 要做的事
具體到檔案與函式。

## 來源程式對照
舊程式在 `design/reference/` 的兩個 zip（解壓到 repo 外再看）。列出這一題要參考的舊檔與函式，標：照搬、改介面、不要。沒有對照的寫「全新」。

## 資料與介面格式
這一題碰到的 JSON 欄位與狀態值、`kb.py` 子命令的參數與 `--json` 輸出、hook 的輸入輸出。寫到能直接當測試用。

## 可以動 / 不可以動
兩份檔案清單。另列「相關測試」：改到這些檔時要跑的測試檔（實作開發中只跑這些，第三節步驟 3）。

## 驗收準則
逐條、可打勾，每條寫怎麼驗：指令、預期輸出。

## 確認情境
在測試 vault 上的操作與預期結果，客戶視角。每條標「自動」或「人眼」（第三節步驟 5）。

## 不做
明確排除。

## 裁定（測試、確認之後才有）
編號整份接續。依時間分小節：### 實作疑義、### 測試第 N 輪後、### 確認後。

## 紀錄（設計 session 結案時填）
- 實作 commit：
- 測試報告：
- 確認報告：
- 發行版號：
- 類似問題查核：
```

## 六、開場訊息

貼出去之前把 `<repo>`、`<worktree>`、`<測試環境>` 換成自己電腦的位置（conventions 第一節），`<題目>` 換成題目名稱。

實作 session：

```
先在 <repo> 跑 git worktree add <worktree> -b spec/<題目>，之後全部在 <worktree> 做。讀 design/specs/<題目>.md 並照它實作。
- 只改 spec「可以動」列的檔。
- 怎麼做照 design/process.md 第三節「各步驟用哪個 skill」：先寫測試、看它紅了再實作；碰 hook／skill／command／agent 先讀對應的 plugin-dev 指引（改 skill 另讀 skill-creator 的寫法，照 D-132）；開工先確認這些 skill 載得到，載不到就讀磁碟上的 SKILL.md 並在回報寫明；收尾實跑全部測試看 exit code，動過 hooks.json 或 manifest 跑 claude plugin validate。
- spec 有疑義或做不到時停下來回報，不要自己決定。
- 寫的時候只跑 spec「相關測試」列的檔：python -m pytest -q <檔>…；commit 之後跑全套一次：python -m pytest -n auto -q tests（這台沒裝 pytest 就用 python -m unittest discover tests）。
- commit 訊息開頭寫 spec 題目。不要 push。
- 設計 session 說 spec 改過了，就先 git merge main 再繼續。
- spec 以外發現的問題寫進回報，不要改 backlog。
回報：改了哪些檔、commit hash、測試結果、疑義清單、spec 以外發現的問題。
```

測試 session：

```
你在 <worktree>（實作的 worktree，分支 spec/<題目>）。先 git merge main（拿最新的 spec），再讀 design/specs/<題目>.md。你的工作是驗證，不是修改。
- 怎麼做照 design/process.md 第三節「各步驟用哪個 skill」：code-review 等級 high，碰守門、權限、路徑時加 security-review。
- plugin-dev 審查：這題動到 hook／skill／command／agent 的話，先讀對應的 plugin-dev 指引當依據審那些檔；收尾跑 plugin-dev:plugin-validator 對整個 repo。結果寫報告一節「plugin-dev 審查」，沒問題也寫一句。
- 對「驗收準則」逐條執行，每條寫 過／不過 與證據。
- 跑全套：python -m pytest -n auto -q tests（這台沒裝 pytest 就用 python -m unittest discover tests）。
- 不改任何程式。不看 git log 以外的實作過程。
- 報告照 design/conventions.md「報告的寫法」：發現照順序編 #1、#2、#3，嚴重另一欄（高、中、低），不用字母代號；第二輪起在同一份檔往下加「第 N 輪」，編號接著上一輪。spec 以外的問題也寫在發現裡，不要改 backlog。
報告存成 design/reports/<題目>-測試.md，只 commit 這份：git -c user.name="<題目>測試" commit -- design/reports/<題目>-測試.md。最後給我一段結論。
```

確認 session：

```
你在 <測試環境>\總資料夾，plugin 由 --plugin-dir 載入。（CLI）。桌面版確認時 plugin 一律只裝在測試知識庫那個夾（B-093）：在知識庫夾裡跑 `claude plugin marketplace add "<worktree 的快照市集>" --scope local`、`claude plugin install <plugin>@<市集> --scope local`，確認 `~\.claude\settings.json` 沒有多東西；不要用畫面上的「為專案安裝」（裝到外掛頁資料夾鈕那個夾）；做完用 `claude plugin uninstall … --scope local` 與 `marketplace remove … --scope local` 清（畫面移除不清 `settings.local.json`，hook 會照跑）。local 範圍跟著工作目錄生效，cd 進知識庫就開始管。改了 worktree 的程式要重做快照、重裝。權限模式用預設（不是 auto），才看得到 kb 有沒有跳允許詢問。使用者範圍的 plugin 會跑進這台每個 Claude，不准用。
- 先確認「來源」已從 來源.zip 還原。確認環境先停用舊的 llm-wiki plugin：先試在測試 vault 的 `.claude/settings.json` 寫 `"enabledPlugins": {"llm-wiki@llm-wiki": false}`（project 層覆寫，未驗證）；沒效就 `claude plugin disable llm-wiki@llm-wiki` 全域停，跑 I-070 的路由 eval 時再 enable。plugin 啟用是使用者層的，資料夾本身沒有東西可關。
- 終端機畫面上的開場訊息、/plugin、/help 你看不到，這幾步請使用者看一眼補驗，報告標「人眼」。
- 讀 <worktree>\design\specs\<題目>.md（實作的 worktree，先在那裡 git merge main）的「確認情境」，用客戶會說的話實際操作，記每一步的實際輸出與落差。
- 不改 plugin 的程式。
- 報告照 design/conventions.md「報告的寫法」：落差照順序編 #1、#2、#3，嚴重另一欄（高、中、低），不用字母代號。spec 以外的問題也寫在落差裡，不要改 backlog。
報告存成 <worktree>\design\reports\<題目>-確認.md，只 commit 這份：在那個 worktree 跑 git -c user.name="<題目>確認" commit -- design/reports/<題目>-確認.md。最後給我一段結論。
```

## 七、硬規矩

1. 驗收準則先於實作。
2. 測試與確認 session 只看 spec。
3. 不 bump、不發行，除非你在設計 session 說「發行」。push 照第八節。
4. 發現別的 bug 另起一題。
5. 決策有字有日期，寫進檔案。
6. 只有設計 session 能改 spec。

## 八、兩人協作

兩位決策者各自開題、各自開 session。不用看板，也不走 PR review。

1. **一題一個 issue 認領。** 開工前在 issue 把自己設成負責人（assignee），狀態 label 改「設計中」；還沒有 issue 的先開（寫法見 conventions「issue 的寫法」）。
2. **誰認領誰拍板。** 那一題的決策由負責人定。
3. **這幾類要對方在 issue 留言同意才做：** 改架構原則、改 `rules/core.md`、放寬守門、改 process 或 conventions、修訂已定的決策（D-nnn）、會改客戶資料格式的大升級。
4. **發行用 issue 的狀態當鎖。** 先看有沒有別的 issue 是「發行中」，有就等它關；沒有就 pull、定版號，把要發的 issue 狀態改成「發行中」，發完關掉。鎖只鎖發行那幾步，平常開發不受影響。（2026-10-26 改：原本另開「發行 vX.Y.Z」issue）
5. **pull 與 push。** 開工先 pull，做完就 push，不准 force push；`design/` 改完當下就 push。實作 session 照舊不 push。
6. **編號只由設計 session 給，而且分段。** jielle2453：決策 D-229～D-499、待辦 B-432～B-599；jacky：決策從 D-500、待辦從 B-600 起。事故 I-nnn 不分段，寫之前先 pull。實作、測試、確認 session 不給編號，發現寫在回報或報告（步驟 7 由設計 session 記進 backlog）。`decisions.md`、`backlog.md` 用 `merge=union`（`.gitattributes`），兩邊同時加條目會都留下；同一條被兩邊改過會留新舊兩版，`tests/test_design_numbering.py` 看到重複編號就紅，合併後跑一次、留對的那版，索引也看一眼。
7. **意見不合就維持現狀。** 從 issue 來的題留言在 issue，其他記進 backlog「待決」，之後再談。
8. **改到同一塊時。** 認領時看兩題 issue 的區域，重疊就在 issue 留言講；spec 定稿前再比「可以動」，重疊時後認領的排在後面。發行前先 merge main；改版號後跑的那次全套就包含這次合併。
