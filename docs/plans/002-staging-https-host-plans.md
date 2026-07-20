# 002 — Staging 公開 HTTPS Host 計畫

## 目標

建立穩定的公開 HTTPS Host，安全轉發至：

```text
https://<STAGING_HOST>
→ 127.0.0.1:8180
→ Staging Nginx Gateway
```

不得直接公開 Backend `8101` 或 n8n `5679`。


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


## Phase 1：方案決策

依序檢查：

1. 既有 Staging 子網域。
2. 既有 Cloudflare Named Tunnel。
3. ngrok 固定 development domain。
4. 不可使用會在重啟後隨機變更 URL 的臨時 tunnel 作 LINE 長期設定。

輸出：

```text
HTTPS_PROVIDER:
STAGING_HOST:
HOST_STABILITY:
COST:
PRODUCTION_HOST_COLLISION:
```

## Phase 2：建立 Tunnel／DNS

必要條件：

- upstream 固定為 `http://127.0.0.1:8180`
- tunnel service 使用 `harcker8119`
- 不在 systemd unit 中硬編碼 token
- 不公開 dashboard/editor
- hostname 重啟後保持不變

## Phase 3：更新 Staging 設定

更新遠端 runtime env 的公開值：

```text
N8N_HOST=<STAGING_HOST>
N8N_WEBHOOK_URL=https://<STAGING_HOST>/
STAGING_PUBLIC_BASE_URL=https://<STAGING_HOST>
STAGING_HOSTNAME=<STAGING_HOST>
```

保持權限：

```bash
chmod 600 /home/harcker8119/BI-RMP-STAGING/.env.staging.runtime
```

## Phase 4：HTTPS 驗證

執行：

```bash
curl -I https://<STAGING_HOST>/
curl -I https://<STAGING_HOST>/health
curl -I https://<STAGING_HOST>/docs
curl -I https://<STAGING_HOST>/openapi.json
curl -I https://<STAGING_HOST>/api/v1
```

預期：

- TLS certificate valid
- `/` 回 `404`
- `/health` 在 Backend 未啟動前可回 `502`
- `/docs`、`/openapi.json`、`/api/v1` 不可公開
- 不得看到 Production 頁面

## Phase 5：重啟穩定性

重啟 tunnel service：

```bash
sudo systemctl restart bi-rmp-staging-tunnel.service
```

重新取得 hostname 並比較。

## 完成條件

```text
RESULT: PASS
STAGING_HOST:
TLS_VALID=YES
HOST_STABLE_AFTER_RESTART=YES
UPSTREAM=127.0.0.1:8180
N8N_EDITOR_PUBLIC=NO
BACKEND_INTERNAL_API_PUBLIC=NO
PRODUCTION_UNCHANGED=YES
```
