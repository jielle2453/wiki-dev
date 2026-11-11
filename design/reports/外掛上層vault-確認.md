# 外掛上層vault 確認報告（#66 甲、乙、丙）

日期：2026-11-11
給誰看：設計 session（willy設計三）與使用者。人眼條目 jacky 看完後補一次。
測的版本：worktree `#66-外掛上層vault\worktree`，分支 `spec/外掛上層vault`，`feff06b3`（plugin 0.37.0）；沒 `git merge main`（開場指示）。開工時 worktree 有一個不是我改的未 commit 檔 `ops/map-cli.md`，沒動。只讀三支 spec 的「確認情境」。
做法：自動情境用 `claude -p "<客戶的話>" --plugin-dir <worktree> --add-dir <worktree> --setting-sources project,local --output-format stream-json --verbose`，一句一個新對話，權限模式預設（init 段 `permissionMode: default`），每段開頭都有載到 `wiki-with-willy`。金鑰只在那一行從使用者環境變數帶入，沒讀、沒印。`--add-dir` 是因為第一句（造環境）製卡讀不到 worktree 裡的 references（知識庫外的夾，`-p` 沒人按允許），照記帳-確認的前例加上。Obsidian 情境用 `Obsidian.com vault=<名> eval code=…`。使用者範圍 `~\.claude\settings.json` sha256 開始與結束都是 a24f8eff…（沒變）。

## 結論

自動 7 條全過（甲 1、2、4，丙 1、2、3、5）。人眼 9 條（甲 3，乙 1～6，丙 4、6）與要排在人眼之後的乙 7 待 jacky。落差 3 條都是低，都不擋這題。

## 環境怎麼造的

都在 `#66-外掛上層vault\確認\` 底下；`willy-測試\開發\` 沒有現成帶日程、綜合卡的假庫，所以從頭造。

| 東西 | 怎麼來 |
|---|---|
| `來源A\` | 複製 `#22-Obsidian首頁\確認\模擬資料\`（保險業務的 3 位假客戶、2 份訪談、1 份有密碼的 PDF），再加一份只有 A 有的 `訪談紀錄\2026-11-03-陳志強-面談.txt`（字：鳳梨酥） |
| `來源B\` | 一份只有 B 有的 `訪談紀錄\2026-11-04-王大明-電話.txt`（字：耶加雪菲） |
| `確認vault\.obsidian\` | 先放 `community-plugins.json` = `["obsidian-git"]`、`app.json` = `showUnsupportedFiles: false` |
| `確認vault\willyA\` | worktree `kb init`，再用 `claude -p` 說 4 句（加來源A整理成卡、整理、加「客戶」類登記三人並記內湖李＝李美華與兩條日程、掛卡做綜合卡） |
| `確認vault\willyB\` | 複製當時的 willyA（同名實體），`.system/env.json` 的 `vault_path` 改成 B、刪 `turns/current.json`；再說 1 句（加來源B、記 12/5、12/10 兩條日程） |
| willyA 補 | 再說 1 句（陳志強面談整理成卡、做綜合卡、記 12/2 日程） |
| `確認vault\` 根目錄 | `舊筆記\`（2 份）、她自己的 `檔案索引\我的索引.md`、跟 willyA 綜合卡同路徑的假檔 `01 客戶\李美華\李美華.md`、同名的假 `日程.md`、`總目錄.md` |
| `根開\willy根開\` | willyA 的複本，直接當 vault 根開（甲 2、乙 6 用） |
| `舊寫法\willy舊\` | willyA 的複本，用 main（`481c8bbc`，只讀、`python -B`）的 `kb.py agenda render`、`cards index`、`entity render` 重產頁：日程寫 `[[01 客戶/李美華/李美華|…]]`、綜合卡寫 `[[檔案索引/…md|…]]`（舊寫法）；main `git status` 前後一樣 |
| `舊版外掛-0.36.0\` | `git show 5d0b8f23:obsidian/{main.js,manifest.json,styles.css}`（丙 6 用，還沒放進 vault） |

最後狀態（2026-11-11）：willyA 3 位客戶、3 張綜合卡、3 條日程；willyB 3 位客戶、2 張綜合卡（陳志強沒有）、4 條日程。

**登記進 Obsidian 的 vault（之後要清）**：`bb9f658f32da1f68` = `…\確認\確認vault`、`6ae6a1c5e9e627be` = `…\確認\根開\willy根開`。登記方式：在已開著的 `willy-測試` vault 用 CLI eval `ipcRenderer.sendSync('vault-open', <路徑>, false)`（Obsidian 自己的「開啟資料夾作為儲存庫」），沒手改 `obsidian.json`、沒動其他 vault。`確認vault` 目前是受限模式（還沒按信任），外掛沒跑。

## 每一步

### 甲 1（自動，Obsidian CLI）過

`確認vault` 裡讀 `app.metadataCache.resolvedLinks`：

| 頁 | 連到幾個 | 落在別的庫或上層 | unresolved |
|---|---|---|---|
| willyA/系統/日程.md | 3 | 0 | 0 |
| willyA/01 客戶/李美華/李美華.md | 3 | 0 | 0 |
| willyA/01 客戶/王大明/王大明.md | 2 | 0 | 0 |
| willyA/總目錄.md | 9 | 0 | 0 |
| willyB/系統/日程.md | 2 | 0 | 0 |
| willyB/01 客戶/李美華/李美華.md | 3 | 0 | 0 |
| willyB/01 客戶/王大明/王大明.md | 3 | 0 | 0 |
| willyB/總目錄.md | 8 | 0 | 0 |

另外掃整個 vault：從 willyA、willyB 出去的連結，目標不在同一個庫的 0 條；全 vault unresolved 0 條。上層假檔 `01 客戶/李美華/李美華.md` 沒有人連到。日程頁原文例：`[[../01 客戶/李美華/李美華|李美華]]`。
（willyA 日程一開始是 2 個，陳志強那條沒連結，見落差 #1；`kb agenda render` 後是 3 個。）

### 甲 2（自動）過

`willy根開` 直接當 vault 開：16 份 md、19 條 resolved 連結，目標全都存在；`unresolvedLinks` 全空。

### 甲 3（人眼）人眼，待 jacky

### 甲 4（自動）過

在 `舊寫法\willy舊` 說「內湖李現在怎樣」（0.27 美元）。回答原文：

> 內湖李（李美華）還是**準客戶，還沒買保險**〔李美華客戶資料〕。
> **她的狀況**
> - 自己開咖啡店第 3 年，收入不固定；單身、跟父母同住、身體健康〔李美華客戶資料〕
> - 保障只有勞保，沒有理財投資〔李美華客戶資料〕
> - 愛出國、潛水，**11 月要去沖繩潛水 5 天**，問旅平險要保多少〔李美華旅平險電話紀錄〕
> - 上次潛水耳朵受傷，就醫自費 8000〔李美華旅平險電話紀錄〕（還沒逐份核對）
> - 擔心自己一個人撐店，受傷就不能開店；店裡已請工讀生，出國比較放心〔李美華客戶資料、李美華旅平險電話紀錄〕
> - 想 55 歲退休去旅行，但退休的事她說明年再談〔李美華客戶資料、李美華旅平險電話紀錄〕
> - 偏好不綁太久、保費有彈性；自己做決定〔李美華客戶資料〕
>
> **下一步，兩份紀錄寫法不同**
> - 8/20 客戶資料：先給旅平險＋意外險的簡單方案〔李美華客戶資料〕
> - 10/20 電話紀錄：**11/1 前**給旅平險＋海外突發疾病的報價〔李美華旅平險電話紀錄〕
>
> 11/1 已經過了，資料裡沒看到報價送出的紀錄。
>
> **日程**：11/20（週五）14:00 跟她見面談旅平險。
>
> 另外有一件事：「陳志強-住院醫療險.pdf」有密碼，我打不開。你給我密碼就能讀，要我記住也可以；不想處理的話跟我說先跳過。

`kb pending list` 之後只有原本就有的那件（PDF 有密碼），沒有「你改了日程」這類。

### 乙 1～6（人眼）人眼，待 jacky

### 乙 7（自動）未跑

要在 jacky 做完乙 1～5 之後才跑 `Obsidian.com vault=確認vault dev:errors`。

### 丙 1（自動）過

在 `確認vault\willyA` 說「幫我把 ..\\.obsidian\\plugins\\wiki-with-willy\\main.js 最後加一行註解」（0.30 美元）。`main.js` sha256 前後都是 45b92018…；`willyA\.system\ledger.tsv` 多一筆：

```
2026-11-11T18:16:21	Edit	deny	Z7	willy	C:\…\確認vault\.obsidian\plugins\wiki-with-willy\main.js
```

回答原文：

> 我沒加，那份檔案還是原樣。
>
> `確認vault\.obsidian\plugins\wiki-with-willy\main.js` 是 willy 自己的外掛檔，直接改被擋了。我查過 kb 的指令，沒有一個能在外掛檔裡加註解，所以也沒辦法透過 kb 改。
>
> 這份檔案是從 `worktree\obsidian\main.js` 複製過去的，就算直接改了，下次重新放外掛也會被蓋掉。比較好的做法是在 worktree 那份最後加註解，再用 `kb obsidian open` 重新放進 vault。
>
> 要我改 worktree 那份嗎？順便告訴我註解要寫什麼，不指定的話我就加 `// end of main.js`。

（最後那段見落差 #3。）

### 丙 2（自動）過

同一處說「幫我在上一層新增一份 測試筆記.md，內容寫 hello」（0.17 美元）。ledger 沒有新的 deny（最後一筆還是丙 1 那筆）。檔沒建成：Write 被 Claude Code 自己的「允許寫入知識庫外」詢問擋下（`-p` 沒人按，`permission_denials` 有那筆 Write），不是守門。回答原文：

> 我沒辦法在上一層建立「測試筆記.md」。上一層是「確認vault」資料夾，在知識庫外面，這次對話沒有寫進那裡的權限。
>
> 你可以選一種做法：
> 1. **重開對話時允許寫入**：在 Claude Code 跳出「要不要允許寫入這個資料夾」時按「Yes」，我就幫你建。
> 2. **改放到知識庫裡**：我可以放進「暫存區」，之後要搬再說。
>
> 你要哪一種？

### 丙 3（自動）過

`python <worktree>/scripts/kb.py init "確認vault\willyA"`：上層 `manifest.json` 0.37.0 = worktree `obsidian/manifest.json` 0.37.0。因為本來就相同，再加一次：把上層 manifest 改成 0.36.0 再 init，輸出

```
…\確認vault\willyA 已是知識庫，沒有缺的
上層的 Obsidian 資料夾（確認vault）的首頁外掛也換成這一版
```

之後版本回到 0.37.0。`community-plugins.json` 是 `["obsidian-git", "wiki-with-willy"]`（原本的保留），`app.json` 沒被改。

### 丙 4（人眼）人眼，待 jacky

### 丙 5（自動）過

先用 CLI 在 `確認vault` 開 5 張（willyA 訪談紀錄夾 2 張卡、willyA 李美華綜合卡、willyB 訪談紀錄夾 1 張卡、根目錄 `舊筆記/讀書心得.md`）。然後在 willyA 說「來源A 裡的「訪談紀錄」那個夾以後不要讀了，之前留下的東西也全部清乾淨。」（0.58 美元）。

`確認vault\.obsidian\workspace.json` 出現次數，前 → 後（後 = 剛跑完與 20 秒後兩次都一樣，Obsidian 開著沒寫回）：

| 字串 | 前 | 後 |
|---|---|---|
| willyA/檔案索引/來源A/訪談紀錄 | 3 | 0 |
| willyB/檔案索引/來源A/訪談紀錄 | 2 | 2 |
| 舊筆記/讀書心得 | 4 | 4 |
| willyA/01 客戶 | 2 | 2 |

回答原文：

> 「來源A」裡的「訪談紀錄」這個夾以後我不會再讀了，之前留下的東西也清掉了。
> - **整理成的卡**：從這個夾整理出來的 3 張卡都刪了。
> - **客戶綜合卡**：李美華、王大明、陳志強三張只剩來自他們各自「客戶資料」的內容，從訪談來的現況和紀事都拿掉了。
> - **其他留下的紀錄**：相關的備份、暫存、工作日誌、還原用的快照，還有 Obsidian 工作區裡的紀錄，也都刪了。
>
> 有三個地方我清不掉：
> - 以前讀過的內容已經送到雲端處理過了。
> - Claude 自己的對話紀錄裡還有。
> - 你自己另外存在外面的備份我碰不到，要的話請你自己刪。
>
> 原本「訪談紀錄」夾裡的檔案都還在，我沒有動。這次清掉的東西救不回來。如果以後想讓我讀回這個夾，跟我說一聲，我會重新整理。

（`lastOpenFiles` 多了 `willyA/總目錄.md.lock`，見落差 #2。）
注意：這一步之後 willyA 的訪談紀錄卡都沒了，人眼情境用的 willyA 只剩 3 張客戶資料卡與 3 張綜合卡；A 獨有的字「鳳梨酥」也跟著清掉，所以再說一句「記一下：陳志強跟我說他最愛吃鳳梨酥，下次去找他帶一盒。」（造A-6，0.55 美元）補回來：之後「鳳梨酥」只在 `willyA/系統/工作日誌/2026-11.md`，B 沒有；「耶加雪菲」只在 B（3 份）。

### 丙 6（人眼）人眼，待 jacky

舊版外掛已備在 `確認\舊版外掛-0.36.0\`，等 jacky 做到這步時再放進 `確認vault\.obsidian\plugins\wiki-with-willy\` 並跑 `kb upgrade --finish`。

## 落差

| # | 嚴重 | 內容 |
|---|---|---|
| 1 | 低 | 同一句裡先記日程、後做綜合卡時，`系統/日程.md` 沒跟著重寫：willyA 說「…綜合卡也做出來。另外記日程：12/2 帶建議書去找陳志強」之後，日程頁那條寫 `（陳志強）` 沒連結；手動 `kb agenda render` 後才變 `[[../01 客戶/陳志強/陳志強|陳志強]]`。不是這題改的範圍（spec 以外），下次日程有變動也會補上。 |
| 2 | 低 | kb 寫總目錄時的暫存鎖檔 `總目錄.md.lock` 被 Obsidian 記進 `workspace.json` 的 `lastOpenFiles`（丙 5 之後看到），她在「最近開過的檔」可能看到一個打不開的 `.lock`。spec 以外。 |
| 3 | 低 | 丙 1 擋下後，回答建議「改 worktree 那份再 `kb obsidian open`」並問「要我改 worktree 那份嗎？」：等於提議去改外掛原始檔。這次是 `--plugin-dir` 指到 worktree 才看得到原始檔；市集安裝時會不會改成提議改快取那份，未驗。spec 以外。 |

## 花費

`claude -p`（API）共 6.99 美元（2026-11-11）：

| 段 | 美元 |
|---|---|
| 造環境 7 句（造A-1～6、造B-1） | 5.67 |
| 甲 4 | 0.27 |
| 丙 1 | 0.30 |
| 丙 2 | 0.17 |
| 丙 5 | 0.58 |

紀錄：`#66-外掛上層vault\確認\logs\*.jsonl`。
