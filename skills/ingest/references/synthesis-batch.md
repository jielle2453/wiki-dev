# 綜合卡批次（寫給製卡者）

- 項目帶 `existing_card`（目標已經有卡）一定先 Read，現況改寫、紀事只增，紀事少了會被打回。帶 `tag_only: true` 的是還沒有綜合卡、只補標籤的實體（`{"entity_id","name","type","tag_only","cards","tags","tags_said","reason"}`，`tags` 是現在標的）：只讀 `cards` 那幾張檔案卡（`path_abs`），照 `profile.tags` 那個型別的字典判斷每一欄，一個實體跑一次 `kb entity tag <名稱> 欄=詞[,詞] …`（看過、沒有寫 `欄=`；`tags_said` 裡的欄不寫），不寫綜合卡；字典外的照 S-33 回報。
- 待更新（`synthesis_stale`）的紀事照 S-22 用 `kb entity log` 加（`<行>` 是 S-14 去掉開頭「- 」），改完自己跑 `--synced`（S-24），主對話不補。
- 做完回報時，寫綜合卡遇到字典外、她明顯在意的條件（S-33），多回一行「字典外：<型別>的<欄>：<詞>」（還沒有那一欄的，條件寫在欄的位置；開頭不加「- 」，那是沒做成的寫法；只寫詞，不寫是誰），主對話照 D-231 問她要不要加。

## 材料的欄位

- `synthesis_new`：`{"entity_id","name","type","category","confirmed","path","cards":[{"id","path","title"}],"statements","rulings","sections","header","question"}`，`path` 相對總資料夾，`sections` 是 `[{"name","required","hint"}]`、已含現況、紀事、推算，`question` 只有沒確認的有。`synthesis_stale`：`{"entity_id","name","path","read_ranges","statements","rulings","findings","added","changed","removed","tags_said"}`（沒有 `header`：檔頭程式管；`read_ranges` 是 `[[起行, 行數], …]`，內文去掉 `## 紀事` 那段，照 S-21 只讀這幾段）；`statements` 是有效口述 `[{"id","text","date"}]`、`rulings` 是裁示 `[{"id","kind","text","cards":[{"id","title"}]}]`（`kind` 是 spoken_wins｜ruled_out），`added`／`changed`／`removed` 每項帶 `source`（card｜statement｜ruling；口述、裁示的內容在項目的 `text`），`changed` 可帶 `reason`「客戶說卡讀錯了」（卡照原檔重寫過，綜合卡裡照舊卡寫的句子要改）。項目本身可帶 `reason` 與 `ids`（健檢標的，lint 題）：「出處點不開」是內文的〔…〕指到不存在、不採用或已收回的（`ids` 是那幾個），照現有的依據改寫那幾句、紀事裡的舊紀錄留著；「有空段」是有段只剩標題，有內容就補、沒有就拿掉那段；「設定檔改了」是那類綜合卡要寫的段變了（照 `sections` 重排）；「補標籤（欄）」「補標籤（欄：詞／詞）」是字典加了欄或詞：原因只有補標籤、`added`／`changed`／`removed` 都空的，只 Read `path_abs` 那張綜合卡、只改括號裡那幾欄的標籤行（照 `profile.tags`；不換整個檔頭，檔頭其他行與內文一字不動，S-06、S-21、S-22、S-24 的例外）；混了別的原因照一般更新，標籤照 S-33 一起寫。added／changed／removed 可能都是空的，照原因改寫就好。
