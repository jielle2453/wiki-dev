# 原始碼地圖：測試與 design/

日期：2026-10-30（自 CLAUDE.md 第一節拆出，原文照搬）
給誰看：改這個 repo 的 Claude 與人；要改、要查某個檔時才讀這份。
什麼時候更新：改到表裡某個檔的那個 commit 一起改那一列；新檔加一列。本清單會漂，以 `git ls-files` 為準。

| 路徑 | 用途 |
|---|---|
| `tests/` | `unittest`；`test_budget.py` 守常駐預算（D-070）、`test_version_sync.py` 守版號對齊、`test_repo_hygiene.py` 守編碼、行尾與 `sys.path`；`test_design_numbering.py` 守 decisions、backlog、incidents 的編號不重複（兩人協作、merge=union）；`_produce.py` 用標準函式庫組 LibreOffice 開得了的最小 docx、有公式的 xlsx、pptx（produce）；密碼與守門：`fixtures/guard_corpus.json` 守門語料（各輪報告與確認的繞過與誤擋，`test_guard_corpus` 全跑）、`_pdfcrypt.py`（標準函式庫做加密的 PDF）、`_pw.py`（驗收的 <V> 與 `leaks` 全庫找密碼）；升級打包：`test_lib_upgrade.py`、`test_lib_migrate.py`、`test_lib_skeleton.py`、`test_scripts_upgrade_cli.py`、`test_tools_release.py`（真的 git 加 bare 假公開 repo，gh 與抓清單替身）；`test_budget.py` 開場上限 8 行 550 字、kb 那行用客戶機最長路徑（99 字）量並把 `line_version` 三句的最壞情況算進去（B-060、D-070 補）；lint 題：`tests/__init__.py` 設 `WIKI_WITH_WILLY_NO_BACKGROUND`（有值時開場不開背景健檢的子行程：黑箱跑開場 hook 的知識庫是暫存夾，背景還在寫就被刪；子行程都繼承它，要測觸發的測試自己拿掉），`_lint.py`（合法綜合卡、Context），`test_lint_<項>.py` 每項一檔、`test_lint_runner.py`、`test_lint_report.py`、`test_scripts_lint_cli.py`、`test_lib_renders.py`、`test_scripts_asks_cli.py`、`test_skill_lint.py`；Obsidian首頁（#22）：`test_turn_obsidian.py`（`--via` 的回合、日誌抬頭、versions 分組、清理）、`test_guard_obsidian.py`（`.obsidian` Z7、模型帶 `--via` 被擋） |
| `tests/evals/` | skill 路由的觸發句（D-091）：`<skill>.json` 20 句、該觸發與不該各半，測試 session 用 skill-creator 的 `run_eval` 跑；`test_skill_manage.py`、`test_skill_ingest.py` 守形狀 |
| `tests/fixtures/` | 測試用範例檔；`cards/` 是兩張合法卡、一張檔頭壞的、`pending.json` 與期望的 `待處理.md`；`vault/` 與 `raw/` 是守門的假總資料夾與來源，測試時整包複製到 tmp；`journal/` 是渲染的範例輸入與期望輸出（D-067）；`inventory/` 是清冊的假總資料夾、三個來源與一份 schema 1 清冊；兩個假總資料夾都帶設定檔兩份（schema 2，型別表一列「案子」）；`profile/` 是 `kb init` 剛建完的設定檔 md 與 JSON（期望輸出）、一份改過的 `改過.md`、`schema1.json` 與它渲染的舊 md；`entities/` 是實體清單、兩張合法綜合卡、一張範本第一版的檔案卡；`knowledge/` 是一份口述清單、一份裁示（兩種加一條已收回）與它渲染的 `裁示.md`；`answer/` 是一份推算清單（有效、被取代）、含 conflict 的 `pending.json` 與它渲染的 `待處理.md`、一張第一版的卡；`guard_corpus.json` 多三條 `.obsidian`（#22：Write 外掛 main.js 擋、Bash 寫 app.json 擋、Read workspace.json 放） |
| `design/` | 流程、約定、架構、決策、spec。只有設計 session 寫；實作、測試、確認 session 的發現寫在回報或報告，不改 backlog（process 第三節步驟 7） |
| `tests/test_lib_home.py` `test_scripts_home_cli.py` `test_lib_find.py` `test_scripts_find_cli.py` | Obsidian 首頁（#22）：kb home 各區與件數、kb find 拆字與比對 |
| `tests/test_renders_apply.py` `test_purge_obsidian.py` | Obsidian 首頁（#22）：kb renders apply／drop 與重新產生時認出手改直接照做（日程、待處理、裁示）、carried 的題、purge 清 Obsidian 的痕跡（workspace、書籤、外掛最近）與 carried；沒事可做的 apply／drop 不開回合、認手改出錯只記 log（測試第 1 輪，裁定 14、15） |
| `tests/test_scripts_check.py` `test_init_obsidian.py` `test_scripts_obsidian_cli.py` `test_moved_obsidian.py` `test_selftest_obsidian.py` `test_release_obsidian.py` | Obsidian 首頁（#22）：--check 四支（什麼都沒寫）、kb init 放外掛、kb obsidian status／open（外部換替身）、kb moved 的 Obsidian 那行、selftest 的 obsidian 步、release 的 obsidian/ 檢查 |
| `tests/obsidian/*.test.js` `test_obsidian_js.py` | Obsidian 外掛的 JS 測試（#22，D-265；首頁畫面的結構照裁定 28 的新畫法：wwh-row 一塊、wwh-mark-line 一件一列、wwh-summary 收起的摘要）：node 內建 test，`obsidian` 模組用假的；`helpers/` 放假環境與假 DOM；跑法 `node --test "tests/obsidian/*.test.js"`（node v24 對資料夾形式報 MODULE_NOT_FOUND），`test_obsidian_js.py` 沒有 node 就 skip |
