# Supabase 時區處理：Taiwan / Asia/Taipei

BI-RMP 是台灣使用情境，資料庫與後端都應該以「台灣業務時間」作為預設顯示與查詢語境。不過時間欄位仍應使用 `TIMESTAMPTZ`，因為它可以保存真實時間點，避免未來排程、API、報表與跨環境部署時發生時間語意混亂。

標準做法不是新增 `*_taipei` 欄位，也不是把同一個時間同時存 UTC 與台灣時間兩份。標準做法是：資料庫 session 設定為 `Asia/Taipei`，後端寫入時使用 timezone-aware datetime 或資料庫 `NOW()`，前端或 API 顯示時遵守同一個台灣時間顯示規則。

## 結論

這個問題應由「資料庫 session 設定」與「後端時間寫入規範」一起修正。

資料庫要做的事情是設定 PostgreSQL/Supabase session timezone 為 `Asia/Taipei`，讓 `NOW()`、`CURRENT_TIMESTAMP`、SQL Editor 與一般查詢結果符合台灣時間語境。

後端要做的事情不是把所有時間先加 8 小時再寫入，而是避免寫入沒有 timezone 資訊的 naive datetime 字串。若後端需要產生時間，應使用 `datetime.now(timezone.utc)` 這種 timezone-aware datetime，或乾脆讓資料庫欄位使用 `DEFAULT NOW()`。

## 建議執行的資料庫設定

到 Supabase Dashboard → SQL Editor，執行：

```sql
-- database/migrations/20260709_set_taipei_timezone.sql
```

這份 migration 會執行類似以下設定：

```sql
ALTER DATABASE postgres SET timezone TO 'Asia/Taipei';
SET TIME ZONE 'Asia/Taipei';
```

執行後請重新整理 Supabase Table Editor，或重新啟動後端服務，讓新的 DB session 套用設定。

## 驗證目前 session 時區

```sql
SELECT
  current_setting('TIMEZONE') AS timezone,
  current_timestamp AS current_timestamp_in_session,
  now() AS now_in_session;
```

理想結果是 `timezone = Asia/Taipei`，而 `current_timestamp_in_session` / `now_in_session` 顯示 `+08`。

## 後端寫法標準

推薦：

```python
from datetime import datetime, timezone

captured_at = datetime.now(timezone.utc).isoformat()
```

也推薦：

```sql
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

不推薦：

```python
captured_at = datetime.utcnow().isoformat()
```

`datetime.utcnow().isoformat()` 會產生沒有 timezone suffix 的 naive datetime 字串。當資料庫 session timezone 改成 `Asia/Taipei` 後，PostgreSQL 可能把這種字串當成本地時間解讀，導致時間偏移。

## 不採用的方案

不要新增 `created_at_taipei`, `updated_at_taipei`, `published_at_taipei` 這類欄位來重複保存台灣時間。

不要為了讓 Supabase Table Editor 看起來正確，就把既有資料全部加 8 小時覆蓋原欄位。

不要把 `TIMESTAMPTZ` 改成文字欄位。這會降低查詢、排序、排程與報表統計的可靠性。

## 實務判斷

如果是 `created_at`, `updated_at`, `first_seen_at`, `last_seen_at`, `collected_at`, `start_time`, `end_time` 這類系統紀錄時間，優先使用 DB `NOW()` 或 timezone-aware datetime。

如果是 `published_at` 或 `commented_at` 這類平台原始發文時間，應盡量保留平台能提供的時間資訊；如果平台只提供台灣本地時間字串，後端 parser 應明確指定 `Asia/Taipei` 後再轉成可寫入 `TIMESTAMPTZ` 的時間值。
