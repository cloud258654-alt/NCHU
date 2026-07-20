# 006 — LINE／LIFF 真實 E2E 驗證計畫

## 目標

使用 allowlisted 測試 LINE 帳號完成：

```text
加入 Staging OA
→ LIFF 註冊
→ 建立 business
→ 發起風評查詢
→ 建立 task
→ 爬蟲執行
→ Quick Reply 查詢進度
→ canonical report 回傳
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


## Phase 1：未註冊使用者

操作：

1. 加入 Staging LINE Official Account。
2. 傳送「風評查詢」。

驗證：

- LINE signature 通過
- n8n 收到 event
- 未註冊使用者收到 registration Flex Message
- 無 raw error
- 非 allowlisted 使用者不寫 DB

## Phase 2：LIFF 註冊

測試資料：

```text
聯絡人：C2 測試
店家：C2-E2E-TEST-<UTC_TIMESTAMP>
```

驗證：

- LIFF SDK 初始化
- ID token 向 LINE 驗證
- user ID 來自 verified `sub`
- 重複提交不產生不合理 duplicate
- client/business ownership 正確

## Phase 3：建立任務

再次傳送「風評查詢」。

驗證：

- 建立 durable `service_task`
- 立即回覆受理訊息
- Quick Reply 存在
- webhook redelivery 不重複建 task
- task 屬於正確 business/client

## Phase 4：爬蟲與狀態

驗證：

- PTT、Google Maps、Threads 均有明確 status
- 至少一個平台成功
- 最終為 `completed` 或 `partial_success`
- failed/timeout raw diagnostics 不進 LINE

## Phase 5：Quick Reply 與報告

點選「查詢進度」。

驗證：

```text
report_type=canonical_reputation_summary
report_scope=task
request.task_id=current_task
```

報告不得包含：

- 同 business 舊 task
- 其他 client
- global rows
- pending/failed analysis 覆蓋有效結果

## 完成條件

```text
RESULT: PASS
LINE_SIGNATURE=PASS
LIFF_LOGIN=PASS
REGISTRATION=PASS
TASK_CREATED=PASS
WEBHOOK_REDELIVERY_DEDUPE=PASS
CRAWLER_FINAL_STATUS=completed|partial_success
QUICK_REPLY=PASS
CANONICAL_REPORT=PASS
TASK_SCOPE_ISOLATION=PASS
RAW_ERROR_LEAKAGE=NO
```
