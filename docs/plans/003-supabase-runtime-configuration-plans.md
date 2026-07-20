# 003 — Supabase Runtime 連線設定計畫

## 目標

安全設定 Staging Backend 連線至唯一允許的 Supabase：

```text
BI-RMP-V2-STAGING
qlhykeeyjaoikczoambe
```


## 共通執行規則

- 僅在功能分支執行；不得直接修改 `main`。
- 不得使用 force push。
- 不得修改或重啟 Production：
  - `/home/harcker8119/BI-RMP`
  - `bi-rmp.service`
  - Port `8001`、`5678`、`8080`
  - `bi-rmp-n8n`、`bi-rmp-n8n-postgres`
- 不得在聊天、Git、log 或文件中輸出：
  - `DATABASE_URL`
  - LINE token／secret
  - LIFF ID token
  - n8n encryption key
  - SSH private key
  - 真實 LINE user ID
- Supabase 唯一允許目標：
  - Project：`BI-RMP-V2-STAGING`
  - Ref：`qlhykeeyjaoikczoambe`
- 未通過驗證不得標示完成。
- 每一階段完成後必須留下可重現的驗證結果。

## 每階段必填驗證結果

```text
RESULT: PASS | FAIL | BLOCKED
MODULE:
PHASE:
BASELINE_SHA:
FINAL_SHA:
BRANCH:
FILES_CHANGED:
COMMANDS_EXECUTED:
TEST_RESULTS:
RUNTIME_CHECKS:
SECURITY_CHECKS:
PRODUCTION_ISOLATION:
ROLLBACK_STATUS:
EVIDENCE:
REMAINING_RISKS:
NEXT_ACTION:
```

`RESULT=PASS` 必須同時具備：
1. 所有必要測試通過。
2. `git diff --check` 通過。
3. 無 secret、Production 或非本模組修改。
4. 文件已更新實際結果。
5. 有明確 rollback 或 recovery 方法。


## Phase 1：取得正確連線字串

使用 Supabase Dashboard 的 Database connection string。

要求：

- Project ref 必須為 `qlhykeeyjaoikczoambe`
- GCP VM 若為 IPv4，優先使用 Session Pooler
- 不得使用 anon key、publishable key、service-role key 代替 PostgreSQL URL
- 不得重設資料庫密碼，除非確認無其他 Staging consumer

## Phase 2：安全寫入 Runtime Env

目標：

```text
/home/harcker8119/BI-RMP-STAGING/.env.staging.runtime
```

設定：

```text
DATABASE_URL=<secret>
APP_ENV=staging
SUPABASE_PROJECT_REF=qlhykeeyjaoikczoambe
ALLOW_DATABASE_WRITES=true
ALLOW_PRODUCTION_DB=false
```

不得顯示值，只輸出：

```text
DATABASE_URL=PRESENT
PROJECT_REF=VALID
APP_ENV=VALID
ALLOW_PRODUCTION_DB=VALID
```

## Phase 3：只讀連線驗證

執行只讀 SQL：

```sql
select current_database();
select count(*) from clients;
select count(*) from business;
select count(*) from service_tasks;
select count(*) from crawl_jobs;
select count(*) from crawl_posts;
select count(*) from crawl_comments;
```

再驗證 Project ref guard。

不得執行 migration 或寫入。

## Phase 4：完整性驗證

驗證 orphan count：

```sql
-- business without client
-- tasks without business
-- jobs without task
-- posts without job
-- comments without post
```

全部應為 `0`。

## Phase 5：安全驗證

確認：

- runtime env 權限 `600`
- Git 未追蹤 runtime env
- logs 不包含 connection string
- Backend 不回傳 DB host、user、password

## 完成條件

```text
RESULT: PASS
DATABASE_URL=PRESENT
SUPABASE_PROJECT_REF=VALID
READ_ONLY_CONNECTION=PASS
ORPHAN_BUSINESS=0
ORPHAN_TASKS=0
ORPHAN_JOBS=0
ORPHAN_POSTS=0
ORPHAN_COMMENTS=0
RUNTIME_ENV_PERMISSION=600
SECRET_LEAKAGE=NO
```
