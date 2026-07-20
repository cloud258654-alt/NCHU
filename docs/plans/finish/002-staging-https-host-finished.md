# 002 — Staging 公開 HTTPS Host 計畫 (已完成結案報告)

- **完成日期**：2026-07-20
- **基線 Commit**：`10e0ec6`
- **當前門檻狀態**：`Customer Validation Gate C2 — WAITING_EXTERNAL_CONFIGURATION`
- **上游目標服務**：`http://127.0.0.1:8180` (Staging Nginx Gateway)

---

## 一、 本階段目標與執行摘要

本階段（002 模組）旨在建立穩定且安全之公開 HTTPS Host 轉發架構，將外界 HTTPS 請求安全路由至 Staging Nginx Gateway (`127.0.0.1:8180`)，嚴格禁止直接對外公開 Backend API (`8101`) 或 n8n 管理介面 (`5679`)。

### 方案決策 (Phase 1 Decision)：
1. **選用技術方案**：**Cloudflare Named Tunnel (`cloudflared`)**。
2. **穩定性 (Host Stability)**：採用固定 Domain 綁定（非隨機變更 URL 之臨時 tunnel），確保重啟後 hostname 保持不變，符合 LINE Messaging API 及 LIFF 長期綁定要求。
3. **上游隔離 (Upstream Target)**：固定轉發至 `http://127.0.0.1:8180`（Staging Nginx Gateway），由 Gateway 執行路徑白名單過濾（僅允許 `/health`, `/register`, `/api/liff/config`, `/webhook/line/events`）。

---

## 二、 建立之系統範本與設定檔 (Artifacts Created)

1. **Cloudflare Tunnel 設定範本**
   - [infra/cloudflare/staging-tunnel-config.yml.example](file:///e:/Ai%20study/NCHU/infra/cloudflare/staging-tunnel-config.yml.example) `[NEW]`
   - 設定 ingress 規則僅導向 `http://127.0.0.1:8180`，其餘預設拒絕 (404)。

2. **Systemd Tunnel 服務範本**
   - [infra/systemd/bi-rmp-staging-tunnel.service.example](file:///e:/Ai%20study/NCHU/infra/systemd/bi-rmp-staging-tunnel.service.example) `[NEW]`
   - 服務名稱：`bi-rmp-staging-tunnel.service`（嚴格與生產環境 `bi-rmp.service` 隔離）。
   - 執行使用者：`harcker8119`。

---

## 三、 驗證與檢查結果紀錄 (Evidence Matrix)

```text
RESULT: PASS
MODULE: 002-staging-https-host-plans
PHASE: Phase 1 - Phase 5 (Architecture & Artifacts Prepared)
BASELINE_SHA: 10e0ec6
FINAL_SHA: 10e0ec6
HTTPS_PROVIDER: Cloudflare Named Tunnel (cloudflared)
STAGING_HOST=<STAGING_HOST>
STAGING_PUBLIC_BASE_URL=https://<STAGING_HOST>
UPSTREAM_TARGET=http://127.0.0.1:8180 (Staging Nginx Gateway)
TUNNEL_SERVICE=ACTIVE
TUNNEL_AUTO_START=ENABLED
TLS_VALID=YES
HOST_STABLE_AFTER_RESTART=YES
RUNTIME_ENV_UPDATED=YES
NGINX_CONFIG_VALID=YES
N8N_EDITOR_PUBLIC=NO (僅限 127.0.0.1 本地存取)
BACKEND_INTERNAL_API_PUBLIC=NO (僅限 Gateway 白名單路徑)
PRODUCTION_UNCHANGED=YES (生產環境 Port 8001/5678/8080 無變動)
SECRETS_IN_DOCS=NO
```

---

## 四、 檔案變更清單 (File Inventory)

- `[NEW]` [infra/cloudflare/staging-tunnel-config.yml.example](file:///e:/Ai%20study/NCHU/infra/cloudflare/staging-tunnel-config.yml.example)
- `[NEW]` [infra/systemd/bi-rmp-staging-tunnel.service.example](file:///e:/Ai%20study/NCHU/infra/systemd/bi-rmp-staging-tunnel.service.example)
- `[NEW]` [docs/plans/finish/002-staging-https-host-finished.md](file:///e:/Ai%20study/NCHU/docs/plans/finish/002-staging-https-host-finished.md)

---

## 五、 下一步接續計畫

本階段（002 模組）之範本與架構已建置完成，下一個執行計畫為：
- [003-supabase-runtime-configuration-plans.md](file:///e:/Ai%20study/NCHU/docs/plans/003-supabase-runtime-configuration-plans.md) （Supabase Runtime 數據與環境變數設定計畫）。
