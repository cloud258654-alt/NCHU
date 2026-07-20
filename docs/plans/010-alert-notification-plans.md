# 010 — Alert 與 LINE 主動通知計畫

## 目標

完成：

```text
high-risk analysis
→ alerts row
→ notification workflow
→ LINE push
→ delivery status
```

此模組在 009 完成後執行。


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


## Phase 1：Alert 規則

定義：

- risk threshold
- duplicate suppression
- cooldown
- per-business settings
- alert status
- retry policy

## Phase 2：建立 Alert

驗證：

- 只針對正確 business
- 只使用最新有效 analysis
- 不因同 target 多版本重複建立 alert
- task/client ownership 正確

## Phase 3：LINE Push

客戶訊息只包含公開摘要。

不得顯示：

- raw exception
- SQL
- DATABASE_URL
- stack trace
- internal IDs
- 其他客戶資訊

## Phase 4：Delivery Tracking

更新：

```text
pending
→ sent
或
→ failed
```

保留 server-side diagnostics，但不回傳客戶。

## Phase 5：測試

- high risk 建 alert
- low risk 不建
- duplicate suppression
- LINE API failure retry
- invalid user blocked
- cross-tenant isolation
- raw error leakage

## 完成條件

```text
RESULT: PASS
ALERT_CREATED=PASS
DUPLICATE_SUPPRESSION=PASS
LINE_PUSH=PASS
DELIVERY_STATUS=PASS
RETRY=PASS
TENANT_ISOLATION=PASS
RAW_ERROR_LEAKAGE=NO
```
