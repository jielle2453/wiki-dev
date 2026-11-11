# git 保護 spike 報告

日期：2026-11-11
位置：原本在 `Desktoplm-wiki-testgit保護-spike報告.md`（量測程式與原始數字還在那個夾）
給誰看：討論 `design/reports/git保護-方案草稿.md` 的設計 session。只放量到的數字與做得到／做不到，不做決定。
對應草稿第九節 1～5。程式與原始結果都在這個夾：`gen_data.py`（假資料）、`spikelib.py`（共用）、`bench1_speed.py`、`spike1_crlf_attrs.py`、`spike1_d_split.py`、`spike1_textconv_mkdocx.py`、`spike2_multiuser.py`、`spike3_prune.py`、`spike3_shallow_fsck.py`；數字在 `results/*.json`。假資料與保護用 git dir 量完已刪。

## 環境

| 項目 | 值 |
|---|---|
| 電腦 | AMD Ryzen 9 7940HX（16 核 32 緒）、RAM 15.2 GB |
| 硬碟 | WD PC SN560 1 TB NVMe SSD；C: 953 GB、用了 19% |
| 系統 | Windows 11 Home 10.0.26200；Defender 即時保護**開著**（spike 夾沒加排除） |
| git | `git version 2.55.0.windows.5`；git-lfs 3.7.1 |
| Python | 3.14.7（任務寫 3.12，這台實際是 3.14.7） |
| 系統層 git 設定（Git for Windows 安裝時寫的） | `core.autocrlf=true`、`core.fscache=true`、`filter.lfs.*`（required=true）、`diff.astextplain.textconv`、`init.defaultbranch=master`；系統 `gitattributes` 對 doc/docx/pdf/rtf/od* 設 `diff=astextplain` |
| CPU% 備註 | 每次量之前取 0.5 秒的全機 CPU%，多半 9～15%，最低 5.3%、最高 18.7%。背景有其他幾個 Claude Code 與 VS Code 在跑，不是閒置機器 |
| 快取 | 都是熱快取（假資料剛寫完、沒辦法清檔案快取）；冷開機第一次會更慢，沒量 |
| 計時 | 從 Python `subprocess` 叫 git 量牆鐘時間，含每個 git 程序啟動（Windows 約 10～20 ms／個）；「add＋diff」是兩個程序 |

假資料：2,998 份、1,118.4 MB、147 個夾、3～5 層、中文檔名與夾名（含空白，例如 `01 進行中`）。文字檔 1,500 份（md 用 LF、txt 用 CRLF，中文）；Office／PDF 1,450 份亂數位元組（開頭放 PK／%PDF 檔頭），50 KB～2 MB；大檔 20～100 MB 共 7 份；一個 249.2 MB／43 份的「大型案」夾；一份 10 MB 的 xlsx。亂數內容壓不小，跟真的 Office（本身是 zip）接近。

保護用 git dir 一律在工作樹外（`gitdirs\prot.git`，跟資料同一顆碟），設定：`core.worktree` 指到資料夾、`core.autocrlf=false`、`core.quotepath=false`、`core.longpaths=true`、`gc.auto=0`、`maintenance.auto=false`。每個指令都用 `git --git-dir=<外面> --work-tree=<資料夾>`，工作目錄設在資料夾。

## 1. 速度（第九節第 1 題，Windows；Mac 沒測）

「照一次」＝ `add -A`、`diff --cached --quiet`、有變才 `commit`。每項 3 次、取中位數。

| 項目 | 中位數 | 3 次 | 量前 CPU% | 其他 |
|---|---|---|---|---|
| a 第一次照（1,118 MB／2,998 份） | **34.4 s** | 30.3／34.4／35.6 | 11.7／11.1／12.2 | 拆開一次：add 34.0 s、commit 0.58 s（量前 18.7%）。約 33 MB/s |
| a 之後 git dir 大小 | 1,112.7 MB | | | 3,343 個檔（3,320 個鬆散物件）；工作樹 1,118.4 MB |
| b 沒變：`add -A`＋`diff --cached --quiet` | **0.046 s** | 0.043／0.055／0.046 | 10.8／14.8／14.4 | 預設設定 |
| b 沒變：`status --porcelain` | **0.027 s** | 0.023／0.027／0.028 | 11.0／9.7／12.1 | |
| b 沒變＋`core.untrackedCache=true` | 0.040 s／0.026 s | | 9～13 | add＋diff／status |
| b 沒變＋`core.fsmonitor=true`＋untrackedCache | 0.049 s／**0.019 s** | | 10～13 | add＋diff／status |
| b 沒變（gc pack 過之後） | 0.041 s／0.027 s | | 10～16 | |
| c 改 5 份小 md＋1 份 10 MB xlsx 後照 | **0.33 s** | 0.333／0.309／0.330 | 12.7／10.2／15.8 | git dir 每次多 10.05 MB（就是那份 10 MB 的整份） |
| d 搬 249 MB／43 份的夾後照 | **1.56 s** | 4.20／1.56／1.50 | 15.2／10.6／6.9 | 3 次搬動 git dir 共多 **2.8 KB** |
| d 拆開（另跑 4 次） | | | 5～12 | add 0.55～0.58 s（新路徑要重算雜湊、讀 250 MB）；`diff --cached --quiet` **0.86～0.95 s**、加 `--no-textconv` 只要 0.02～0.07 s；commit 0.04 s |
| e 還原一份 10 MB 檔（`restore --source=<第一張> -- 檔`） | **0.033 s** | 0.033／0.033／0.032 | 9～13 | sha256 對得上 |
| e 還原一個夾（刪掉後；55 份、16.0 MB） | **0.066 s** | 0.066／0.066／0.067 | 11～13 | 全部 sha256 對得上 |
| e 還原 249 MB 夾（刪掉後） | **0.334 s** | 0.339／0.334／0.334 | 11～14 | 全部 sha256 對得上 |
| gc（第一次把鬆散物件 pack 起來，約 1.14 GB） | 35.9 s | 1 次 | 10.6 | 1,142.9 MB／3,418 檔 → 1,142.7 MB／29 檔（亂數資料壓不小） |
| gc（已 pack 過再跑） | 4.1 s | 1 次 | 11.1 | |

做得到／做不到：

- **git dir 放在資料夾外可以正常照、還原、改名、中文檔名。** e 做完全部 2,998 份對 manifest 的 sha256 都對（c 改過的 4 份小檔除外，那是預期的）。
- **搬動有認出來**：最後一次搬動 `diff -M --name-status` 43 行全是 `R100`、沒有 A／D（不認搬動時是 86 行），算 0.017 s；內容相同的檔不會多存一份（3 次搬動共 +2.8 KB，只多了 tree 與 commit）。注意：搬動後的 `add -A` 還是要把 250 MB 讀一遍算雜湊（0.55 s）。
- **fsmonitor 在 git dir 在別處時能用**：`fsmonitor--daemon status` 回「watching '…/data/知識庫'」；改一份檔 status 看得到、改回後是空的；`fsmonitor--daemon stop` 後沒有留下 git.exe。開著時每個資料夾多一個常駐 git.exe（約 9 MB）。省下的時間很少（status 0.027 → 0.019 s；add＋diff 沒變快）。
- `untrackedCache`：`update-index --test-untracked-cache` 通過，但時間幾乎沒差（0.046 → 0.040 s）。
- **還原一個夾會刪掉「之後照進去」的檔**：舊版沒有、但後來照過（已追蹤）的新檔，`restore --source=舊 -- 夾` 會把它刪掉；從沒照過的檔留著。
- **Git for Windows 的 `diff=astextplain` 會讓「有沒有變」判錯**（系統 `gitattributes` 對 doc/docx/pdf/rtf/od* 設的）：
  - 真的 docx（`spike1_textconv_mkdocx.py` 做的，文字相同、zip 裡另一個檔不同）：位元組變了，`diff --cached --quiet` 回 **0（說沒變）**；加 `--no-textconv` 回 1。照「沒變就不 commit」的邏輯，這次會漏照。
  - 亂數內容的 docx／pdf：`diff --cached --quiet` 回 **128**（`E: unsupported filetype … fatal: unable to read files to diff`）。
  - 這台沒有 `docx2txt.exe`（stderr 有 `command not found`），單一份 docx 就 0.45 s。
  - `--no-textconv`，或保護 git 的 `info/attributes` 寫 `* -diff`，都回正確的 1。`status --porcelain` 不受影響。
- **中文路徑**：`core.quotepath=true`（git 預設）輸出八進位跳脫（`\351\200\262…`）；`=false` 輸出原本的中文，但路徑有空白時整段仍包在雙引號裡；`--porcelain -z` 完全不跳脫、不加引號。
- **換行（CRLF）與屬性**（`spike1_crlf_attrs.py`；照完刪掉再從 HEAD 還原、比 sha256）：

| 情況 | 只有 LF 的 md | CRLF txt | 混合換行 md | docx／pdf | 長路徑 md（326 字元） |
|---|---|---|---|---|---|
| 1 保護 git 沒設 autocrlf（吃系統的 `true`） | **變了** | 同 | **變了** | 同 | **變了** |
| 2 `core.autocrlf=false` | 同 | 同 | 同 | 同 | 同 |
| 3 同 2，但資料夾裡有 `.gitattributes`：`* text=auto`（例如團隊 repo 放的） | **變了** | 同 | **變了** | 同 | **變了** |
| 4 同 3＋保護 git 的 `info/attributes`：`* -text` | 同 | 同 | 同 | 同 | 同 |
| 5 資料夾 `.gitattributes` 把 pdf 設成 LFS | 同 | 同 | 同 | 同（但見下） | 同 |
| 6 同 5＋`info/attributes`：`* -text -filter` | 同 | 同 | 同 | 同 | 同 |
| 7 `core.longpaths=false` | 同 | 同 | 同 | 同 | **沒照到** |

  - 所以 `core.autocrlf=false` **需要**（Git for Windows 系統預設是 true）；資料夾裡別人放的 `.gitattributes` 也會套到保護 git，要用保護 git 自己的 `info/attributes` 蓋掉。
  - 情況 5：保護 git 裡的 pdf 只存了 131 位元組的 LFS 指標、內容放在保護 git dir 的 `lfs/objects`；這台還原得回來，但等於多一套儲存。情況 6 之後是一般 blob（300,009 位元組）。
  - 情況 7：`add` 只印 `warning: could not open directory '…': Filename too long`、回傳 0，**那個檔就這樣沒照到**。`core.longpaths=true` 時 326 字元的路徑照、還原都正常。

## 2. 多人：保護 git 疊在團隊 repo 上（第九節第 3 題）

小資料夾：40 張卡（md）、20 份約 1.5 MB 的原檔、`_個人/`、`.obsidian/`；它本身是 `git init` 的團隊 repo（`.gitignore` 排除 `_個人/` 與 `.obsidian/workspace*.json`），團隊 objects 29.3 MB。外面兩個保護 git dir：P1 一般、P2 用 `objects/info/alternates` 指到團隊的 `.git/objects`。

| 檢查 | 結果 |
|---|---|
| 保護照的時候 `.git/` 會不會進去 | **不會**，連 `info/exclude` 不寫 `.git/` 也不會（git 本來就跳過叫 `.git` 的夾） |
| 一般 `add -A` 會不會照到團隊 `.gitignore` 排除的（`_個人/`） | **不會**——資料夾裡的 `.gitignore` 對保護 git 一樣有效，`_個人` 沒被保護 |
| 改用 `add -A -f -- . ":(exclude).obsidian/workspace*.json"` | `_個人/` 有進、`.gitignore` 本身有進、`workspace.json` 沒進。`-f` 也會無視 `info/exclude`，雜訊只能用 pathspec 排除 |
| 團隊忽略的夾裡新加一份檔，`status --porcelain` 看得到嗎 | **看不到**；`add -A -f …` 之後 `diff --cached --name-only` 看得到 |
| 保護照完，團隊 `git status` | 跟照之前一樣（空的），團隊 `.git/index` 的 sha256 沒變 |
| 團隊 commit、切到舊版、再切回來，保護照常照嗎 | 照常；`fsck` 正常；團隊 status 仍是空的。（切到舊版那次保護「沒變」，因為舊版內容剛好就是保護上一張的內容） |
| 團隊平常 `gc`（不改歷史）後 P2 | `fsck` 正常 |
| 工作樹裡有另一個 git repo 的子夾 | 保護 git 只記一筆 gitlink（mode 160000），**子夾的內容沒照**；印 `warning: adding embedded git repository` |

alternates 省多少（objects 大小，MB）：

| 時間點 | P1（不共用） | P2（alternates） | 團隊 |
|---|---|---|---|
| 第一次照完 | 29.7 | **0.3** | 29.3 |
| AI 改 3 份共約 6 MB → 保護先照、團隊之後才 commit（外掛 5 分鐘一次的順序） | 35.5（+5.8） | 6.2（**+5.9**） | 35.2（+5.9） |
| 同事改的 3 份約 6 MB 先進團隊（模擬 pull 進來）→ 保護才照 | 41.4（+5.9） | 6.2（**+0**） | 41.0（+5.8） |

- alternates **做得到**，省的是「團隊 repo 已經有的內容」：第一次照、拉進來的。這台 AI 自己改的，保護先照、團隊後 commit，兩邊各存一份，沒省。
- **團隊改寫歷史會弄壞 P2**：團隊 commit 一份「機密」→ P2 照（沒自己存）→ 團隊 `reset --hard HEAD~1`、`reflog expire --expire=now --all`、`gc --prune=now` → P2 `fsck` 報 `missing tree`、`missing blob`，`restore` 那張回 `error: Could not read …`。更早、團隊還有的版本還原正常。P1 照常還原得回來。
- **alternates 檔要用 LF 換行**：第一次跑時用 Python `write_text` 寫（Windows 會寫成 CRLF），git 把路徑讀成 `…/objects\r`，只印 `error: object directory …/objects? does not exist`、照樣照，結果 P2 自己存了全部（29.7 MB），等於沒共用。改成 LF 後才是上表的 0.3 MB。

## 3. 清 30 天前的（第九節第 4 題）

在 1.1 GB 假資料上照 45 張（日期攤在 60 天內，`GIT_AUTHOR_DATE`／`GIT_COMMITTER_DATE`），每張改 3 份 md、整份換一份約 1 MB 的 docx，每 5 張加一份 2 MB pdf、每 7 張刪一份 pdf。

| 項目 | 數字 |
|---|---|
| 照 45 張（含第一次整個照） | 共 44.3 s（第一次約 34 s，之後每張約 0.2 s） |
| 清之前 | 鬆散 1,173.9 MB；`gc` pack 45.8 s（量前 9.1%）→ **1,172.8 MB** |
| 切點 | 30 天前或更早的最後一張（2026-10-12）留著當最舊的一張；它之前的 22 張清掉，剩 23 張 |

兩種清法（每種從同一份已 pack 的副本做 3 次）：

| | A：commit-tree 重接 | B：shallow 檔 |
|---|---|---|
| 做法 | 切點那張的 tree 用 `commit-tree` 做成新的根，之後 22 張依序 `commit-tree -p` 接回去（保留原日期），`update-ref` | 把切點那張的雜湊寫進 git dir 的 `shallow` 檔 |
| 之後都做 | `reflog expire --expire=now --all`＋`gc --prune=now` | 同左 |
| 時間中位數（3 次） | **5.01 s**（6.17／5.01／5.01；量前 9.9／14.0／10.9%） | **4.19 s**（4.07／4.22／4.19；量前 11.5／10.7／11.2%） |
| 清完大小 | **1,158.3 MB**（少 14.5 MB） | 1,158.3 MB（同） |
| 還原最新那張的檔 | 對 | 對 |
| 還原切點那張的檔 | 對 | 對 |
| 原本最舊那張還拿得到嗎 | 拿不到（真的清掉了） | 拿不到 |
| commit 雜湊 | **留下的 22 張全部變了** | 不變 |
| `git fsck` | 正常 | **回 16**：第一次 `gc` 寫的 `objects/info/commit-graph` 還列著被清掉的 commit，shallow 的 repo `gc` 不會重寫它。刪掉 `commit-graph` 後 `fsck` 回 0，之後再 `gc` 也不會再寫（`spike3_shallow_fsck.py` 小資料重現） |

- 少掉的 14.5 MB 就是「只在被清掉那 22 張裡」的內容（被蓋掉的 docx 舊版、被刪的 pdf、md 舊版）；目前還在的檔一份都不少。
- 這份資料 pack 好之後再清只要 4～5 秒，因為 `gc` 直接沿用已壓好的 pack；**第一次** pack 1.1 GB 要 36～46 秒。
- 實際 1.1 GB 有多少能清，看那 30 天裡改掉、刪掉多少，這裡是每張約 1 MB 的量。

## 4. OneDrive（第九節第 2 題，沒測）

- 這台有 OneDrive：`%OneDrive%` = `%OneDriveConsumer%` = `C:\Users\Jie\OneDrive`；`%OneDriveCommercial%` 是空的。
- 照任務沒放任何東西進 OneDrive 或其他雲端夾，第九節第 2 題（知識庫在 OneDrive 夾裡）**沒測**，等使用者決定。草稿第八之二第 (3) 題（「只在線上」的佔位檔一讀就下載）也就沒量。

## 5. Mac 與 git 有沒有裝（第九節第 5 題）

- 這台：`git version 2.55.0.windows.5`。Mac 沒辦法測。
- **willy 現在不需要 git**：
  - `README.md` 沒提 git、Git for Windows、Git Bash。
  - `design/reports/B-093-官方文件.md`（2026-10-21 查官方文件）：「Windows：Git for Windows 選配，沒有就用 PowerShell 當指令工具」——Claude Code 在 Windows **不是一定要** Git for Windows；桌面版有沒有內建 Git 沒寫。
  - `design/decisions.md` D-023：「第一版不以 git 為前提……客戶電腦沒有 git」。D-345 的理由也寫「單人知識庫沒有 git（git 只在多人共用時由服務人員設，D-302）」。
  - `scripts/kb/_lib/git.py`：`git` 不在 PATH 時每個函式回「不適用」，呼叫端照單機走。
  - `design/conventions.md` 只要求「Git Bash 路徑都要認」（路徑寫法），不是要求裝 git。
- 所以單人也用保護 git，在 Windows 也是多一個要裝的東西。裝了 Git for Windows 的電腦，它的系統預設（`autocrlf=true`、`diff=astextplain`、LFS filter、預設分支 `master`）要在保護 git 自己的設定與 `info/attributes` 蓋掉（見第 1 節）。

## 影響草稿哪幾題

只列數字碰到的題，不做建議。

- **八-1 方向（個人的在本機、知識庫外）**：git dir 放在外面，照、還原、搬動、中文檔名都正常；團隊 repo 的 status 與 index 不受影響；`.git/` 本來就不會被照。要另外處理才對的：`core.autocrlf=false`、`info/attributes` 寫 `* -text -filter -diff`（或判斷有沒有變時加 `--no-textconv`）、`core.longpaths=true`、團隊 `.gitignore` 排除的要用 `add -f`＋pathspec 排除雜訊、資料夾裡的子 repo 只記一筆不照內容。git 本身在 Windows 也不是現有前提（第 5 節）。
- **八-2 照的時機（動檔前＋答完）**：沒變時「看一下」0.02～0.05 s；改幾份 0.33 s；搬 250 MB 約 0.6 s（判斷沒加 `--no-textconv` 時約 1.5 s）。**第一次照** 1.1 GB 要 30～36 s，比現在 hooks.json 裡 PreToolUse 的 timeout（10 s）長；每個資料夾只發生一次，但會落在某一句裡。
- **八-3 大檔界線**：大檔每改一次就多一整份（10 MB 檔每次 +10.05 MB）；搬動不多存（+2.8 KB）；還原 250 MB 夾 0.33 s。第一次照的速度約 33 MB/s（含壓縮與防毒）。
- **八-4 留多久、排程清**：45 張、1.1 GB，清到剩 30 天：已 pack 時 4～5 s，第一次 pack 36～46 s；清完還原最新與切點那張都對。A 會改掉留下的 commit 雜湊（日誌若記雜湊會對不上），B 不改但要多刪 `commit-graph`。
- **八-5 守門剩什麼**：團隊 repo 被改寫歷史＋`gc --prune=now` 會讓用 alternates 的保護紀錄壞掉（那幾張還原不了）；不用 alternates 就沒事。
- **八-7 對使用者怎麼說（「30 天內說一聲就能改回」）**：清完 30 天內的都還原得回來（第 3 節）；還原一個夾會刪掉之後才照進去的檔（第 1 節 e）。
- **八之二**：(1) 多人共用 git 物件——alternates 做得到，只省團隊已有的內容，AI 自己改的不省（第 2 節）；(2) 每句多等多少——見八-2；(3) 雲端佔位檔——沒測（第 4 節）；(4) Windows 長路徑——`core.longpaths=false` 時會不出錯地漏照，`true` 正常；防毒——這台 Defender 開著，數字已含它的影響，沒有對照組；(9) 保護壞了——alternates 的情況會壞（第 2 節）；(15) 刪掉的敏感檔單獨清——沒測，第 3 節的清法是整段清；(16) Mac——沒測。
