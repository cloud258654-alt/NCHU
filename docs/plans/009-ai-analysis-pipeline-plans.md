# 009 — AI／ML 自動分析管線計畫

## 目標

將目前只記錄 log 的 `enqueue_post_crawl_analysis()`，升級為可實際執行、可重試、可追蹤的分析管線。

此模組在 Gate C2 通過後執行。


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
