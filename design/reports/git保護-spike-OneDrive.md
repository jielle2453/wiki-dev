# git 保護 spike：資料夾在 OneDrive 裡（草稿第九節第 2 題、八之二第 (3) 題）

位置：原本在 `Desktop\llm-wiki-test\git保護-spike\OneDrive報告.md`（量測程式在同夾 `onedrive\`）；2026-11-11 使用者同意在 OneDrive 放測試檔，測完已刪。

日期：2026-11-11
給誰看：討論 `design/reports/git保護-方案草稿.md` 的設計 session。只放量到的與做得到／做不到，不做設計決定。
程式在 `onedrive\`：`odlib.py`（共用，重用上一層 `spikelib.py`）、`s0_rootlist.py`、`s1_setup.py`、`s2_basic.py`、`s3_placeholder.py`、`s4_skip.py`、`s5_restore_flags.py`、`s6_racy.py`；原始輸出在 `onedrive\results\*.json`／`*.log`。測試夾與 git dir 量完已刪（第 4 節）。

## 環境

| 項目 | 值 |
|---|---|
| 系統 | Windows 11 Home 10.0.26200；Defender 開著 |
| OneDrive | 個人版（`%OneDrive%` = `C:\Users\Jie\OneDrive`），用戶端 26.198.1011.0006，「檔案隨選」開著（根目錄原本就有一份只在線上的 `開始使用 OneDrive.pdf`） |
| git | 2.55.0.windows.5（系統層 `core.autocrlf=true`、`diff=astextplain`、LFS filter，同上一份 spike） |
| Python | 3.14.7 |
| 測試夾 | `%OneDrive%\willy-spike-相簿\`，28 份、1.7 MB（後來加到 33 份、2.2 MB）：md（LF）、txt（CRLF）中文內容；docx／pdf 是 50～500 KB 亂數位元組；中文檔名與夾名，含空白（`01 進行中`、`林 美玲.md`、`說明 文件.txt`），3 層 |
| 保護 git dir | `Desktop\llm-wiki-test\git保護-spike\onedrive\prot.git`（OneDrive 外） |
| git 設定 | 同上一份 spike：`--git-dir`／`--work-tree` 分開、`core.worktree` 指到測試夾、`core.autocrlf=false`、`core.quotepath=false`、`core.longpaths=true`、`gc.auto=0`、`maintenance.auto=false`；`info/attributes` 寫 `* -text -diff -filter` |
| 同步狀態怎麼看 | `cldapi.CfGetPlaceholderInfo`（只開 `FILE_READ_ATTRIBUTES`，不讀內容）讀 InSyncState；新檔上傳前回 `0x80070178`（還不是雲端檔），上傳完是 `IN_SYNC`。28 份第一次上傳 9 秒內全部 `IN_SYNC`；之後每步改動 3～6 秒同步完 |
| 「只在線上」怎麼做 | `attrib +U -P "<檔>"`，等到 `st_file_attributes` 出現 `RECALL_ON_DATA_ACCESS`：每次 **2 秒內** |

## 1. 照、改、還原、改名（`s2_basic.py`）

每一步做完：等全部 `IN_SYNC` → 再等 20 秒 → 再確認 `IN_SYNC` → 列夾裡所有檔，跟預期清單比（找衝突副本，例如 `報價單-DESKTOP-2VL9ICT.docx`）→ `git status --porcelain`。

| 步驟 | 指令 | 秒 | 結果 | 多出的檔 | 同步後 `git status` |
|---|---|---|---|---|---|
| 1 第一次照（28 份） | `add -A`、`diff --cached --quiet --no-textconv`、`commit` | 0.153 | 28 份進去 | 無 | 空 |
| 2 改一份 md、整份換一份 docx 後照 | 同上 | 0.068 | `M 報價單.docx`、`M 卡片01.md` | 無 | 空 |
| 3 還原一份 docx | `restore --source=<第一張> -- "來源/01 進行中/報價單.docx"` | 0.020 | sha256 對 | 無 | ` M 報價單.docx`（預期：跟 HEAD 不同） |
| 4 還原一個夾（先改一份、刪一份、等同步） | `restore --source=<第一張> -- "來源/02 已結案"` | 0.023 | 夾內 4 份 sha256 全對，刪掉的回來了 | 無 | 同上 |
| 5 改名 `卡/人物/王小明.md` → `卡/人物/王 小明（改名）.md` 後照 | 照一次，`diff -M --name-status HEAD~1 HEAD` | 0.065 | **`R100 卡/人物/王小明.md → 卡/人物/王 小明（改名）.md`** | 無 | 空 |
| 6 舊名那份從第一張還原 | `restore --source=<第一張> -- 卡/人物/王小明.md` | 0.019 | sha256 對 | 無 | `?? 卡/人物/王小明.md`（預期） |

- 最後全部 sha256 對第一張的清單：只有第 2 步改過的 `卡片01.md` 不同（預期）。
- **還原的檔 OneDrive 當成一般改動**：git 是刪掉再寫新檔，還原後那一刻 `CfGetPlaceholderInfo` 回「不是雲端檔」，3 秒後變 `IN_SYNC`（上傳完）。整個 spike（含第 2、3 節的還原）**沒有出現任何衝突副本**：刪除前最後一次列檔是 33 份，全部是預期的檔名。
- OneDrive 處理完上傳（檔案變成雲端佔位、`IN_SYNC`）之後，`git status` 是空的，也沒有把檔讀一遍（見第 2 節 A3：OneDrive 這邊的處理不動 git 比的 stat 欄位）。
- OneDrive 會把夾設成 `READONLY|DIRECTORY`（測試夾 `attrib` 值 49），對 git 照、還原沒影響。

## 2. 「只在線上」的佔位檔（`s3_placeholder.py`）

### 屬性位元

| 狀態 | `st_file_attributes` | `CfGetPlaceholderInfo`（pin／sync） |
|---|---|---|
| 剛建、還沒上傳 | `0x20` ARCHIVE | 不是雲端檔（`0x80070178`） |
| 上傳完（在本機也在雲端） | `0x20` ARCHIVE | UNSPECIFIED／IN_SYNC |
| `attrib +U -P` 之後（只在線上） | `0x500020` ARCHIVE｜UNPINNED（0x100000）｜**RECALL_ON_DATA_ACCESS（0x400000）** | UNPINNED／IN_SYNC |
| OneDrive 根目錄原本的 `開始使用 OneDrive.pdf`（從沒下載過） | ARCHIVE｜RECALL_ON_DATA_ACCESS（**沒有** UNPINNED） | — |
| 被讀了內容（下載回來）之後 | `0x20` ARCHIVE（UNPINNED 也不見了） | UNSPECIFIED／IN_SYNC |

- 整個 spike **沒看過** `OFFLINE（0x1000）`、`RECALL_ON_OPEN（0x40000）`、`PINNED（0x80000）` 出現在檔案上。判斷「只在線上」要看 `RECALL_ON_DATA_ACCESS`；只看 UNPINNED 會漏掉從沒下載過的那種。
- 變成只在線上**不改** `mtime`、`ctime`、建立時間、大小（`A0`／`A1` 前後一模一樣），所以 git index 記的 stat 仍對得上。
- 被 git 讀過而下載回來的檔，UNPINNED 也被清掉，等於變成「保留在這台」——之後不會自己再變回只在線上。

### a. stat／走資料夾會不會下載

`os.stat()` 每份 ＋ `os.walk` ＋ 每個 `os.scandir` 的 `entry.stat()`：3 份都**仍是只在線上**（A2）。

### b. git 會不會下載

| 情況 | 指令 | 下載了嗎 |
|---|---|---|
| 已照過、變成只在線上、stat 沒變 | `git status --porcelain` | **沒有**（A3） |
| 同上 | `git add -A` | **沒有**（A3）；`diff --cached` 空的 |
| 已照過、變成只在線上、**stat 變了**（用 `os.utime` 把 mtime 加 5 秒模擬「別台改過、OneDrive 換成新的佔位」；`utime` 本身沒有下載它） | `git status --porcelain` | **下載了**（A4：git 要讀內容比對） |
| 同上 | `git add -A` | **下載了**（s4 第 1 種：2 份 stat 變了的都下載） |
| 同上，`add` 有用 pathspec 排除它，之後一般 `git commit` | `commit` | **下載了**（s4 第 3 種：`commit` 會 refresh 整個 index，不管 add 排除了什麼） |
| 沒照過、建完就只在線上（`新來源/` 3 份） | `git status --porcelain -uall` | **沒有**，列成 `??`（B2） |
| 同上 | `git add -A` | **下載了**（s4 第 1、7 種；3 份 0.5 MB 花 1.23 秒） |
| 已照過、**racy**（檔案時間跟上次寫 index 同一秒）、之後變成只在線上，stat 沒變 | 任何會寫 index 的指令（這裡用 `update-index --skip-worktree <別的檔>`） | **下載了**（`s6_racy.py`：git 寫 index 時要讀內容確認 racy 的檔有沒有變）。同一份檔再經過一次 index 寫入（時間已晚一秒以上、內容沒變）就不再 racy |

### c. 跳過：每種做法比較（`s4_skip.py`）

起點都一樣（同一份 git dir 副本）：已追蹤的 3 份只在線上（2 份 stat 變了、1 份沒變）、沒照過的 3 份只在線上、另外一般改動 1 份（`卡片03.md`）、一般新檔 1 份（`新卡.md`）。「排除清單」＝掃屬性有 `RECALL_ON_DATA_ACCESS` 或 `OFFLINE` 的檔（6 份）。

| # | 做法 | 下載了幾份 | 已追蹤佔位留住舊版（沒被記成刪除） | 沒照過的佔位進了嗎 | 一般改動、新檔照到 | 要另外記狀態 |
|---|---|---|---|---|---|---|
| 1 | 什麼都不做：`add -A`＋`commit` | **5**（2 份 stat 變了的＋3 份新的；2.7 秒） | 是（內容其實一樣） | 進了（下載後） | 是 | 否 |
| 2 | 只寫 `info/exclude`＋`add -A`＋`commit` | **2**（stat 變了的已追蹤檔；`info/exclude` 對已追蹤檔沒用） | 是 | 沒進 | 是 | 否 |
| 3 | `add -A -- . ":(exclude,literal)<路徑>"…`＋一般 `commit` | **2**（`commit` 那步下載的） | 是 | 沒進 | 是 | 否 |
| 4 | 同 3，但 commit 改用 `write-tree`＋`commit-tree -p HEAD`＋`update-ref HEAD` | **0** | **是**（`HEAD:<路徑>` 的 blob 跟之前一樣） | 沒進 | 是 | **否** |
| 4b | 同 4，排除清單用 `add -A --pathspec-from-file=<檔> --pathspec-file-nul`（第一行 `.`，其餘 `:(exclude,literal)<路徑>`，NUL 分隔） | **0** | 是 | 沒進 | 是 | 否 |
| 5 | 已追蹤的 `update-index --skip-worktree`、沒照過的寫 `info/exclude`，然後一般 `status`、`add -A`、`commit` | **0** | 是 | 沒進 | 是 | **是**（旗子要清） |
| 6 | 同 5 但用 `--assume-unchanged` | **0** | 是 | 沒進 | 是 | **是** |

第 4 種還多量了：帶同一份排除的 `status --porcelain -uall` 0.020 秒、`add` 0.020 秒、`diff --cached --quiet --no-textconv` 0.016 秒、`write-tree`＋`commit-tree`＋`update-ref` 0.056 秒，**整段都沒下載**。

第 5、6 種的副作用（`s5_restore_flags.py`）：

- 旗子沒清的後果：`assume-unchanged` 的檔之後在本機被改，`add -A` **照不到**（c1：`diff --cached` 空的）；清掉旗子（`--no-assume-unchanged`）後才照到 `M`（c2）。所以檔案下載回來後要記得清。
- `skip-worktree` 的檔還原：還原的版本跟 index 不同時 `restore --source=…` 照常寫（rc 0、sha256 對）；版本**相同**時回 rc 1、`error: pathspec '卡/卡片02.md' did not match any file(s) known to git`。加 `--ignore-skip-worktree-bits` 正常。`assume-unchanged` 的檔還原正常（b3：rc 0、sha256 對）。
- 第 4 種在 index 裡不留任何旗子，下次照時重新掃就好。

還原到只在線上的檔（`s5` a）：`卡片01.md` 只在線上時 `restore --source=<第一張>`（舊版內容不同）：rc 0、0.025 秒、sha256 對；寫完那一刻是一般檔（不是雲端檔），3 秒後 `IN_SYNC`，變成「在本機也在雲端」的一般檔（不再只在線上），沒有衝突副本。

**照事實看，最簡單、不下載又留住已追蹤佔位檔上一版的做法是第 4b 種**（不在 index 留狀態）：

```
掃：os.walk＋os.scandir，entry.stat().st_file_attributes & (0x400000 | 0x1000) 的檔 → 排除清單
寫 pathspec 檔（NUL 分隔）：".", ":(exclude,literal)<路徑1>", ":(exclude,literal)<路徑2>", …
git --git-dir=… --work-tree=… add -A --pathspec-from-file=<pathspec 檔> --pathspec-file-nul
git … diff --cached --quiet --no-textconv          （1＝有變）
git … write-tree  →  git … commit-tree <tree> -p HEAD -m …  →  git … update-ref HEAD <commit>
```

限制（都是量到的）：

- 這個保護 git 上**不能**跑沒帶排除的一般 `git status`、`git commit`、`git add -A`（還有會 refresh index 的 `reset`、`stash`、`checkout`），stat 變了的已追蹤佔位檔會被下載。第一次照（還沒有 HEAD）時 `commit-tree` 不加 `-p`。
- racy 的空窗（上表最後一列）：檔在「照的那一秒」剛被改、照完又在下一次寫 index 前被設成只在線上，下一次照的 `add` 寫 index 時會把它下載。排除清單擋不住這個（git 寫 index 時對 racy 的項目一律讀內容）。
- 被排除的已追蹤佔位檔，保護紀錄裡是「最後一次在本機時的版本」；它在別台被改過的新版，要等它下載回來（有人打開）後的下一次照才會進去。
- 「stat 變了」是用 `os.utime` 改 mtime 模擬的，**沒有真的從別台或網頁改**；OneDrive 換新佔位時會改 mtime／大小，git 的判斷相同，但沒實測。

### d. 掃屬性要多久（`s3` C0、`s5` d）

| 範圍 | 檔數 | 5 次（秒） |
|---|---|---|
| OneDrive 測試夾 | 32 | 0.0023／0.0020／0.0020／0.0026／0.0022 |
| OneDrive 測試夾（後來） | 33 | 0.0013／0.0012／0.0012／0.0011／0.0011 |
| 本機 `Desktop\llm-wiki-j`（含 `.git`，**不在** OneDrive，只讀） | 1,832 | 0.072／0.035／0.036／0.037／0.038 |
| 同上只跑 `os.walk`（不取屬性） | 1,832 | 0.020／0.018／0.019／0.019／0.019 |

- 屬性來自列目錄（`FindFirstFile`），不另外開檔、不下載。本機樹約每份 20 µs；**3,000 份約 0.06 秒是推算的**，OneDrive 夾裡沒有量到幾千份（只放 30 幾份）。

## 3. 沒測的

- 真的從另一台或 OneDrive 網頁改檔（用改 mtime 代替）；OneDrive 公司版；上傳中途照（每步都等 `IN_SYNC` 才照或才看）；大量檔或大檔在 OneDrive 裡的速度；Mac 的 OneDrive／iCloud／Dropbox。
- git dir 放在 `%LOCALAPPDATA%`：這次放在 `Desktop\llm-wiki-test\…`（也在 OneDrive 外、同一顆碟），git 的行為不因位置不同。

## 4. 清理

- `%OneDrive%\willy-spike-相簿\`（刪前 33 份、2.2 MB，含幾份只在線上的）整個刪掉：本機刪，雲端那份會進 **OneDrive 線上資源回收筒**（不是 Windows 的資源回收筒）。
- `onedrive\prot.git`、`onedrive\prot_base.git`（第 4 種比較用的副本）已刪；`__pycache__` 已刪。
- OneDrive 根目錄刪前刪後比對（`results\root_before.json`、`root_after.json`：名稱、是否資料夾、大小、修改時間、屬性）：10 項，**完全一樣**，沒有多、沒有少、沒有變。只列根目錄這一層，沒往下走（避免碰到其他資料夾）。
