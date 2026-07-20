# 004 — LINE／LIFF Staging 外部設定計畫

## 目標

建立與 Production 完全分離的 LINE Staging Provider、Messaging API Channel、LINE Login Channel 與 LIFF App。


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


## Phase 1：建立 Staging Provider 與 Channels

建立：

1. Staging LINE Official Account
2. Staging Messaging API Channel
3. Staging LINE Login Channel
4. LIFF App

Messaging API 與 LINE Login 必須位於同一 Provider。

## Phase 2：設定公開 URL

```text
Webhook:
https://<STAGING_HOST>/webhook/line/events

LIFF Endpoint:
https://<STAGING_HOST>/register

LIFF Size:
Full

LIFF Scopes:
openid
profile
```

## Phase 3：取得並安全填入設定

填入遠端 runtime env：

```text
LINE_CHANNEL_ACCESS_TOKEN
LINE_CHANNEL_SECRET
LINE_LIFF_ID
LINE_LOGIN_CHANNEL_ID
BI_RMP_LINE_ALLOWED_USER_IDS
```

要求：

- 僅使用 Staging Channel
- 不得從 Production 複製 token
- allowlist 僅包含測試帳號
- 不得把 LINE user ID 寫入 Git 或文件

## Phase 4：設定驗證

只輸出 presence：

```text
LINE_CHANNEL_ACCESS_TOKEN=PRESENT
LINE_CHANNEL_SECRET=PRESENT
LINE_LIFF_ID=PRESENT
LINE_LOGIN_CHANNEL_ID=PRESENT
BI_RMP_LINE_ALLOWED_USER_IDS=PRESENT
```

驗證：

- LINE Login 已 publish
- LIFF scopes 正確
- Webhook enabled
- Webhook redelivery enabled
- Endpoint 使用 HTTPS
- Provider 關係正確

## Phase 5：未部署前安全檢查

在 Shared Staging 尚未啟動時，不執行真實 webhook Verify；先確認 URL 與設定格式。

## 完成條件

```text
RESULT: PASS
STAGING_PROVIDER_CREATED=YES
MESSAGING_CHANNEL_CREATED=YES
LINE_LOGIN_CHANNEL_CREATED=YES
LIFF_APP_CREATED=YES
SAME_PROVIDER=YES
WEBHOOK_URL_VALID=YES
LIFF_ENDPOINT_VALID=YES
ALLOWLIST_PRESENT=YES
PRODUCTION_CREDENTIALS_USED=NO
```
