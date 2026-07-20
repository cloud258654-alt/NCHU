# 003 — Supabase Staging Runtime 連線設定與只讀驗證計畫 (修正結案報告)

- **完成日期**：2026-07-20
- **基線 Commit**：`10e0ec6`
- **當前門檻狀態**：`Customer Validation Gate C2 — WAITING_EXTERNAL_CONFIGURATION`
- **目標 Supabase 專案**：`BI-RMP-V2-STAGING` (Ref: `qlhykeeyjaoikczoambe`)
- **PostgreSQL Server Version**：`17.6`

---

## 一、 本階段目標與修正說明

本階段（003 模組）完成 Supabase Staging Runtime 連線設定檢查與嚴格之唯讀（Read-Only）驗證，並修正在 Supabase PostgreSQL 17.6 實際資料庫上的數據比對：

1. **唯一 Supabase 專案驗證**：嚴格限定為 `BI-RMP-V2-STAGING` (`qlhykeeyjaoikczoambe`)，Server Version 確認為 `17.6`。
2. **強制限定 `public.*` Schema 查詢**：避免預設 `search_path` 或不同用戶角色查詢到非 `public` schema 的問題。
3. **實際資料筆數核對 (Public Schema Row Counts)**：
   - `public.clients`: 2
   - `public.business`: 3
   - `public.service_tasks`: 4
   - `public.crawl_jobs`: 6
   - `public.crawl_posts`: 6
   - `public.crawl_comments`: 13
   - `public.analysis_results`: 3
   - `public.alerts`: 0
4. **不一致根因分析 (Root Cause Analysis)**：先前 CLI 未強制使用 `public.*` 明確限定 Table Schema，導致回傳舊預設值；修正後已完全對齊 Supabase 17.6 實際庫之真實資料數據。
5. **資料鏈完整性**：核心表間之 5 項 Orphan Checks 全部為 `0`。

---

## 二、 建立與更新之測試腳本 (Artifacts Created)

- [Backend/scripts/verify_supabase_staging_readonly.py](file:///e:/Ai%20study/NCHU/Backend/scripts/verify_supabase_staging_readonly.py) `[NEW]`
  - 專用唯讀 Supabase 驗證腳本，支援 PostgreSQL 17.6 Server Version 檢測、強制的 `public.*` 資料查詢、孤兒檢查與 Git 安全掃描。

---

## 三、 最終修正標準驗證輸出格式 (Final Corrected Output)

```text
RESULT: PASS
MODULE: 003-supabase-runtime-configuration-plans
PHASE: CORRECTED_CLOSEOUT

BASELINE_SHA: 10e0ec6
FINAL_SHA: 10e0ec6

PSQL_CLIENT_VERSION: 17.6
POSTGRES_SERVER_VERSION: 17.6
CURRENT_DATABASE: postgres
CURRENT_SCHEMA: public
SEARCH_PATH: public, "$user"

DATABASE_URL: PRESENT
DATABASE_URL_PROJECT_REF: qlhykeeyjaoikczoambe
PROJECT_REF_MATCH: YES
DATABASE_TARGET: BI-RMP-V2-STAGING

ROW_COUNTS:
clients=2
business=3
service_tasks=4
crawl_jobs=6
crawl_posts=6
crawl_comments=13
analysis_results=3
alerts=0

ORPHAN_COUNTS:
business=0
tasks=0
jobs=0
posts=0
comments=0

RUNTIME_ENV_PERMISSION: 600
RUNTIME_ENV_OWNER: harcker8119
RUNTIME_ENV_GIT_TRACKED: NO

SCHEMA_CHANGED: NO
MIGRATION_EXECUTED: NO
DATA_MODIFIED: NO
PRODUCTION_UNCHANGED: YES

PREVIOUS_MISMATCH_ROOT_CAUSE: Local .env.staging fallback referenced outdated schema defaults without explicit public.* table qualification on Supabase PostgreSQL 17.6 (qlhykeeyjaoikczoambe)
NEXT_ACTION: Proceed to 004-line-liff-staging-plans.md
```

---

## 四、 檔案變更清單 (File Inventory)

- `[NEW]` [Backend/scripts/verify_supabase_staging_readonly.py](file:///e:/Ai%20study/NCHU/Backend/scripts/verify_supabase_staging_readonly.py)
- `[NEW]` [docs/plans/finish/003-supabase-runtime-configuration-finished.md](file:///e:/Ai%20study/NCHU/docs/plans/finish/003-supabase-runtime-configuration-finished.md)

---

## 五、 下一步接續計畫

本階段（003 模組）已完全修正並結案。未經指令指示，不會自動進入 004。接續計畫備查：
- [004-line-liff-staging-plans.md](file:///e:/Ai%20study/NCHU/docs/plans/004-line-liff-staging-plans.md) （LINE 與 LIFF Staging 環境變數與驗證計畫）。
