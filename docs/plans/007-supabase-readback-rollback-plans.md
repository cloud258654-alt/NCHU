# 007 — Supabase Live Readback 與 Rollback Rehearsal 計畫

## 目標

確認 E2E 建立的資料鏈正確，並演練精準 rollback，最後必須 `ROLLBACK;`。


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


## Phase 1：定位測試資料

Selector 必須只匹配：

```text
C2-E2E-TEST-<UTC_TIMESTAMP>
```

不得使用模糊條件或刪除共享 client。

## Phase 2：Live Readback

驗證鏈：

```text
clients
→ business
→ service_tasks
→ crawl_jobs
→ crawl_posts
→ crawl_comments
→ analysis_results
```

只輸出：

- numeric IDs
- statuses
- row counts
- platforms
- timestamps

不得輸出 LINE user ID 或完整評論內容。

## Phase 3：資料一致性

驗證：

- exactly one intended test business
- task ownership 正確
- 無 orphan
- 無 cross-business
- 無 webhook redelivery duplicate
- report task ID 與 DB task ID 相同
- latest valid analysis 選取正確

## Phase 4：Rollback Rehearsal

使用：

```text
database/testdata/customer_validation_gate_c2_rollback_rehearsal.sql
```

執行前人工確認 selector。

必要流程：

```sql
BEGIN;
-- before count
-- precise delete rehearsal
-- after delete count
ROLLBACK;
-- verify restored count
```

不得使用 `COMMIT`。

## Phase 5：回復驗證

Rollback 後：

- 測試資料仍存在
- 共享歷史資料未變
- Production 資料未碰觸
- migration history 未變

## 完成條件

```text
RESULT: PASS
TEST_BUSINESS_MATCH_COUNT=1
TASK_OWNERSHIP=PASS
ORPHAN_ROWS=0
CROSS_BUSINESS_ROWS=0
REDELIVERY_DUPLICATES=0
ROLLBACK_FINAL_STATEMENT=ROLLBACK
DATA_RESTORED_AFTER_ROLLBACK=YES
PRODUCTION_DATA_CHANGED=NO
```
