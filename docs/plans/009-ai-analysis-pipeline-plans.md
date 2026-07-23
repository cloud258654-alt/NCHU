# 009 — AI／ML 自動分析管線計畫

## 目標

將目前只記錄 log 的 `enqueue_post_crawl_analysis()`，升級為可實際執行、可重試、可追蹤的分析管線。

此模組在 Gate C2 通過後執行。

## 本機實作與驗證狀態（2026-07-23）

```text
RESULT: LOCAL_VERIFICATION_PASS
MODULE: 009-ai-analysis-pipeline
BRANCH: feature/009-ai-analysis-pipeline

STATIC_CHECKS:
- git diff --check: PASS
- python compileall: PASS

TEST_RESULTS:
- focused tests: 36 passed
- lease/fencing and latest-valid direct tests: 53 passed
- staging bootstrap focused rerun: 1 passed
- full regression: 357 passed, 1 warning

WINDOWS_TEST_ENVIRONMENT:
- Git Bash executable: C:\Program Files\Git\bin\bash.exe
- cygpath dependency: C:\Program Files\Git\usr\bin
- 原失敗是 PATH／路徑轉換問題，不是 009 功能錯誤。

DATABASE_STATUS:
- migration 20260722_analysis_queue_pipeline.sql 已套用至 BI-RMP-V2-STAGING
- migration 20260723_analysis_queue_lease_fencing.sql: CREATED_NOT_APPLIED
- 本次工作未重新連線或驗證資料庫
- Production unchanged
- business data write 未在本次執行

RUNTIME_STATUS:
- rules baseline local tests: PASS
- lease heartbeat and claim-token fencing local tests: PASS
- stale attempt-3 recovery SQL contract test: PASS
- latest completed-only Dashboard read-path tests: PASS
- analysis queue live runtime: NOT_VERIFIED
- worker live execution: NOT_VERIFIED
- task-scoped staging readback: NOT_VERIFIED
- LLM analysis: NOT_VERIFIED
- LINE／LIFF／n8n: NOT_EXECUTED
- 006～008: BLOCKED
- Gate C2: NOT_PASS

ROLLBACK_STATUS:
- migration rollback rehearsal: NOT_EXECUTED
- 不得自行執行 rollback

NEXT_ACTION:
- 先審核本分支 diff
- 後續另行核准 Live Staging worker／queue 驗證
- 未完成 Live Staging、LLM 與 rollback 前，不得將 009 標示為最終 PASS
```

補充風險：Staging advisor 先前提示 `analysis_results` 已啟用 RLS 但未定義 policy；未在缺乏明確存取模型下新增政策。


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


## Phase 1：定義分析契約

明確定義：

- input target：`crawl_post`／`crawl_comment`
- analysis status
- model／rules method
- latest valid analysis 規則
- idempotency key
- retry policy
- timeout
- failure handling

## Phase 2：建立 worker／queue

不得在 Webhook request 內長時間執行 LLM。

建議：

```text
crawler completed
→ enqueue analysis job
→ worker processing
→ analysis_results
→ score snapshot
```

## Phase 3：模型與 baseline

先保留 rules baseline，再加入 LLM：

- sentiment
- topic
- risk level
- summary
- recommendation
- confidence

## Phase 4：測試

必須包含：

- duplicate enqueue 不重複分析
- pending/failed 不覆蓋 completed
- latest completed wins
- timeout/retry
- malformed model response
- secret leakage
- tenant/task isolation

## Phase 5：Live Staging 驗證

對 C2 測試 business 執行：

- post analysis
- comment analysis
- coverage
- task-scoped report readback

## 完成條件

```text
RESULT: PASS
ANALYSIS_QUEUE=ACTIVE
RULES_BASELINE=PASS
LLM_ANALYSIS=PASS
IDEMPOTENCY=PASS
RETRY=PASS
LATEST_VALID_SELECTION=PASS
TASK_SCOPE=PASS
SECRET_LEAKAGE=NO
```
