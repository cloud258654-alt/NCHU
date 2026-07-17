# Assistant Collaboration Guidelines

這份文件用來記錄 BI-RMP 專案中，使用 AI assistant 協作時的偏好與限制。

## GitHub commit 原則

使用者不希望 GitHub 上出現很多零碎的小開發 commit。

一次性、暫時性、尚未確定會採用的內容，應優先在對話中直接交付，例如臨時 SQL、排錯指令、prompt 草稿、設計想法、文件片段或小型 code snippet。

正式程式碼如果需要修改，仍然應該 commit 到 GitHub。重要且需要長期保存的文件，也應該 commit 到 GitHub。

當同一個對話中的需求需要修改多個檔案時，assistant 應先完成整體評估與必要修改，再盡可能整理成一個有意義、可追蹤的 commit，不要把同一個需求拆成很多小 commit。

## 適合直接在對話中交付的內容

以下內容通常不需要直接推送到 GitHub：

```text
一次性 SQL 查詢
臨時排錯指令
prompt 草稿
文件片段
小型 code snippet
概念說明
操作步驟
資料庫設計討論
尚未確定會採用的架構建議
```

## 適合修改 GitHub 的情況

以下情況適合直接修改 repo：

```text
需要修正正式程式碼或 schema
需要新增或更新重要文件
需要新增 migration、測試、README 或 dev-spec
使用者明確要求「幫我更新 GitHub」
使用者要求整理 legacy code 或專案結構
```

## 時區處理原則

BI-RMP 是台灣使用情境，資料庫 session 應設定為 `Asia/Taipei`，讓 `NOW()`、`CURRENT_TIMESTAMP` 與 Supabase SQL 查詢顯示符合台灣時間。

時間欄位仍應優先使用 `TIMESTAMPTZ` 儲存真實時間點，不要改成文字欄位，也不要新增 `*_taipei` 欄位來重複保存同一個時間。

後端寫入時間時應避免 naive datetime。若後端需要主動產生時間，應使用 timezone-aware datetime，例如 `datetime.now(timezone.utc)`，或交給資料庫 `NOW()`。不要使用 `datetime.utcnow().isoformat()` 這類沒有時區資訊的字串。

顯示給台灣使用者時，應在 SQL 查詢、API serializer 或前端顯示層統一轉成 `Asia/Taipei`。不要把既有資料直接加 8 小時覆蓋原欄位。
