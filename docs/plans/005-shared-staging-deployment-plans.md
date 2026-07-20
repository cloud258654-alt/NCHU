# 005 — Shared Staging 部署計畫

## 目標

啟動獨立 Shared Staging：

```text
Backend: 127.0.0.1:8101
n8n: 127.0.0.1:5679
Gateway: 8180
Systemd: bi-rmp-staging.service
Compose: bi-rmp-staging-n8n
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


## Phase 1：部署前檢查

必須全部成立：

```text
STAGING_HOST=PRESENT
DATABASE_URL=PRESENT
LINE_CHANNEL_ACCESS_TOKEN=PRESENT
LINE_CHANNEL_SECRET=PRESENT
LINE_LIFF_ID=PRESENT
LINE_LOGIN_CHANNEL_ID=PRESENT
BI_RMP_LINE_ALLOWED_USER_IDS=PRESENT
```

檢查：

```bash
git status --short
git rev-parse --short HEAD
bash -n scripts/deploy-staging.sh
bash scripts/verify-staging.sh
```

## Phase 2：執行部署

```bash
cd /home/harcker8119/BI-RMP-STAGING
TARGET_SHA="$(git rev-parse HEAD)"
export STAGING_PUBLIC_BASE_URL="https://<STAGING_HOST>"
bash scripts/deploy-staging.sh "$TARGET_SHA"
```

預期：

```text
RESULT: DEPLOYED_STAGING_PENDING_E2E
```

## Phase 3：服務驗證

```bash
systemctl is-active bi-rmp-staging.service
curl --fail http://127.0.0.1:8101/health
curl --fail http://127.0.0.1:8101/register
curl --fail http://127.0.0.1:8101/api/liff/config
curl --fail http://127.0.0.1:5679/healthz/readiness
docker ps
```

## Phase 4：公開路由驗證

```bash
curl --fail https://<STAGING_HOST>/health
curl --fail https://<STAGING_HOST>/register
curl --fail https://<STAGING_HOST>/api/liff/config
```

確認：

- `/docs`、`/openapi.json`、n8n editor 不公開
- invalid webhook signature 不建立資料
- `/api/liff/config` 不含 secret

## Phase 5：Production 隔離回查

確認前後：

```bash
systemctl is-active bi-rmp.service
curl --fail http://127.0.0.1:8001/health
docker ps --format '{.Names}'
```

## 完成條件

```text
RESULT: PASS
DEPLOYED_SHA:
BACKEND_SERVICE=ACTIVE
BACKEND_HEALTH=PASS
N8N_READINESS=PASS
PUBLIC_HEALTH=PASS
PUBLIC_REGISTER=PASS
PUBLIC_LIFF_CONFIG=PASS
INTERNAL_ROUTES_PUBLIC=NO
PRODUCTION_SERVICE=ACTIVE
PRODUCTION_N8N_UNCHANGED=YES
```
