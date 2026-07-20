# Agent Handoff Document

Last Updated: 2026-07-20
Baseline Commit: `10e0ec6`
Current Gate: `Customer Validation Gate C2 — Host Bootstrapped / Waiting External Configuration`

---

## 1. Current System Status Summary

- **Repository Main Branch**: Commit `10e0ec6`.
- **Test Suite Verification**: 343 passed, 1 warning (pytest execution time ~14s).
- **Staging Host Bootstrap**: Script `scripts/bootstrap-staging-host.sh` and systemd/nginx configuration templates prepared. Host environment bootstrapped.
- **Shared Staging Deployment**: Pending external secrets and HTTPS hostname configuration.
- **Production Isolation**: Active production environment (`/home/harcker8119/BI-RMP`, service `bi-rmp.service`, ports `8001`, `5678`, `8080`) is isolated, protected, and untouched.

---

## 2. Gate C2 Status Breakdown

| Item | Status | Detail |
| :--- | :--- | :--- |
| **Local Code & Tests** | `COMPLETED` | All 343 unit and integration tests passing. |
| **Staging Topology & Guards** | `COMPLETED` | Ports `8101`, `5679`, `8180` and isolation guards verified. |
| **Host Bootstrap Script** | `COMPLETED` | `scripts/bootstrap-staging-host.sh` created and idempotent. |
| **Shared Staging Deployment** | `PENDING` | Awaiting runtime configuration file `/home/harcker8119/BI-RMP-STAGING/.env.staging.runtime`. |
| **Public HTTPS Domain / Tunnel** | `BLOCKED` | Awaiting external domain configuration for Webhook / LIFF endpoints. |
| **LINE Developers Staging Channel**| `BLOCKED` | Awaiting Messaging API Access Token, Secret, and LIFF App ID. |
| **Supabase Staging Database Target** | `PREPARED` | Project Ref: `qlhykeeyjaoikczoambe` (BI-RMP-V2-STAGING). |

---

## 3. Staging Topology & Isolation Rules

```text
Staging App Directory:    /home/harcker8119/BI-RMP-STAGING
Staging Runtime Env:      /home/harcker8119/BI-RMP-STAGING/.env.staging.runtime
Staging Systemd Service:  bi-rmp-staging.service
Staging Backend Port:     8101
Staging n8n Host Port:    5679
Staging Gateway Port:     8180
Staging Compose Project:  bi-rmp-staging-n8n
Staging Deployment Lock:  /tmp/bi-rmp-staging-deploy.lock
```

### Critical Protection Values (Must NOT be modified or targeted)
```text
Production App Dir:       /home/harcker8119/BI-RMP
Production Service:       bi-rmp.service
Production Ports:         8001, 5678, 8080
Production Compose:       bi-rmp-n8n
Production Containers:    bi-rmp-n8n, bi-rmp-n8n-postgres
```

---

## 4. Exact Next Actions

1. Provide real runtime credentials in `/home/harcker8119/BI-RMP-STAGING/.env.staging.runtime` on the Staging host (do not commit runtime secrets to Git).
2. Configure LINE Developers Console for the Staging Messaging API Channel & LIFF app.
3. Bind Public HTTPS hostname / reverse proxy to Staging Gateway port `8180`.
4. Execute `scripts/deploy-staging.sh <target-sha>` on the Staging host and run `scripts/verify-staging.sh`.

---

## 5. Prohibited Actions (Safety Checklist)

- **Do NOT** commit or expose secrets in chat, logs, commits, or documentation (`DATABASE_URL`, LINE Tokens/Secrets, n8n keys, SSH keys).
- **Do NOT** execute destructive database operations on Supabase without explicit user confirmation.
- **Do NOT** modify or restart Production processes (`/home/harcker8119/BI-RMP`, ports 8001/5678/8080).
- **Do NOT** force push to `main` branch.
