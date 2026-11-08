# wiki-with-willy 安裝說明（OpenAI Codex 版）

日期：2026-11-07（codex 分支第一版，**還沒在 Codex 實機裝過**）
給誰看：替客戶安裝的服務人員。Claude Code 版的安裝看 README.md。
什麼時候更新：實機測過、Codex 改了外掛或 hook 的做法時。

## 一、事前確認

| 項目 | 怎麼確認 | 為什麼 |
|---|---|---|
| Windows 上的 Codex 桌面 App（或 Codex CLI） | 打得開、登入得了 | 官方只保證「桌面 App 手動安裝的外掛」會跑 hook；CLI 要實機確認；IDE 擴充不支援外掛 |
| **Python 3** | 命令列跑 `python --version` 有版本號 | 🔴 **沒有 Python 就完全沒有守門**：Codex 的 hook 起不來時會照樣讓 AI 改檔（Claude 版會擋下，Codex 不會） |
| 建議裝 OpenAI 的文件技能 | 在 Codex 打 `$skill-installer`，裝 Word、Excel、PowerPoint 的技能 | 做文件時 AI 才有現成的技能可用；沒裝也能做，只是比較慢 |

## 二、安裝

1. 把 `codex` 分支的檔案放在客戶電腦上一個固定的資料夾（以下叫 `<外掛夾>`），不要放在同步資料夾（OneDrive、Google 雲端硬碟）底下。🔴 **路徑裡不能有 `#`**：Codex 會把 `#` 後面當成 git 分支，加市集時報「--ref is only supported for git marketplace sources」（2026-11-08 Codex CLI 0.167.0 實測）；已經在這種夾裡就用 `mklink /J` 建一個不含 `#` 的目錄連結再加。
2. 把 `<外掛夾>` 加成本機市集：`codex plugin marketplace add <外掛夾>`（市集檔是 `<外掛夾>\.agents\plugins\marketplace.json`，名稱 `wiki-with-willy-local`）；桌面 App 用外掛目錄加本機市集。
3. 裝外掛：`codex plugin add wiki-with-willy@wiki-with-willy-local`，或在 Codex 打 `/plugins`（桌面 App 是「外掛」分頁）找到 wiki-with-willy 安裝、打開。🔴 **裝的時候會複製一份到 `%USERPROFILE%\.codex\plugins\cache\`，實際跑的是那份**：`<外掛夾>` 換了新版要再跑一次這步才生效。
4. 🔴 **信任 hook**：在 Codex 打 `/hooks`（桌面 App 是「設定 > Hooks」），把 wiki-with-willy 的每一個 hook 都按信任。沒按就整組不跑，等於沒守門。**外掛升級、換了 hook 程式之後要再按一次。**
5. 開客戶的知識庫資料夾當專案，**開一個新對話**（裝好外掛後要新對話才載入）。
6. 確認：新對話裡 AI 看得到一段「【wiki-with-willy】」開頭的開場段。問 AI「你有看到 wiki-with-willy 的開場段嗎」即可。

## 三、裝好之後的差別（跟 Claude 版比）

- 知識庫裡多一份 `AGENTS.md`（Codex 讀它，內容跟 `CLAUDE.md` 一樣）。舊知識庫沒有這份的話，跑一次 `kb init` 補骨架。
- 整理新檔由主對話自己做，一次最多 10 份，沒有背景的製卡助手，大量整理會比 Claude 版慢。
- 密碼相關的動作（顯示存好的密碼、用存好的密碼開檔、讓某一種檔自動用密碼）AI 會先問客戶，**客戶下一句回「好」「可以」「同意」才做**；回別的就不做。
- 升級（「升級」「有新版嗎」）這版不支援，由服務人員換外掛夾的檔案，再照第二節第 4 步重新信任 hook。
- 貼圖片、貼長文字給 AI 收進知識庫：這版可能收不到，AI 會照實說。
- claude.ai 的線上文件讀不到，會記成「線上文件打不開」。

## 四、守門跟 Claude 版不一樣的地方

| | 說明 |
|---|---|
| hook 出錯就放行 | Codex 的 hook 出錯、逾時、沒跑起來時，AI 的動作照樣執行。willy 的守門自己出錯會回「不准」，但 **Python 不在、hook 沒被信任時完全沒有守門**。知識庫的 `AGENTS.md` 有交代：沒看到開場段就先不改檔。 |
| 要先信任 | 第二節第 4 步。 |
| 密碼動作 | 第三節。 |
| 攔不到的 | Codex 的網路搜尋這類雲端工具（不碰本機檔）；客戶自己另外裝的 MCP 檔案工具（Claude 版也沒管）。 |

## 五、實機要測

1. CLI 跑不跑外掛的 hook（文件只保證桌面 App 手動裝的）；本機市集怎麼加。
2. hook 指令裡的 `${PLUGIN_ROOT}` 有沒有被代換成外掛夾。
3. Windows 上 `Bash` 的 `tool_input.command` 長怎樣（純 PowerShell 字串、包了 `powershell.exe -Command`、或陣列）。
4. AI 讀檔是不是都走 shell；`view_image` 的工具名與參數名（轉接假設是 `path`）。
5. `apply_patch` 的 patch 放在 `command` 還是 `patch`（轉接兩個都收）；patch 裡的路徑是絕對還是相對。
6. `updatedInput` 對 `Bash` 有沒有生效：kb 指令要被插 `--session`，沒生效的話「退回」會退到別的對話的。
7. 守門擋下時 Codex 會不會把整段指令或 patch 秀給客戶看（第三方回報有），密碼指令被擋時會不會露出密碼。
8. Stop hook 印 `{}` 有沒有被接受。
9. 開場段（`additionalContextLimit: 0`）整段進到模型，沒有被存成檔只給頭尾。
10. 信任 hook：第一次裝、升級後各要按幾次。
11. Codex 的 sandbox 裡 PowerShell 能不能附著到客戶開著的 Word、Excel、PowerPoint。
12. 對話紀錄（`transcript_path`）的格式：貼的圖、貼的長文字放在哪；之後補 `kb intake --pasted` 的解析。
13. Python 在 sandbox 裡能不能寫知識庫的 `.system\`、讀知識庫外面登記的客戶資料夾。
14. 密碼動作的同意流程：AI 被擋後會不會照理由去問客戶、客戶回「好」之後 AI 會不會重跑**同一個**指令。
15. `SessionEnd` 只給 3 秒，放掉整理批次來不來得及（Codex 版不派批次，應該沒事）。
16. 知識庫的 `.codex\config.toml` 要不要關 Codex 的記憶功能（鍵名待查）。
