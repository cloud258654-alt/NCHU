# 001 — 專案狀態與文件同步計畫

## 目標

讓 GitHub 文件與目前真實狀態一致，消除過時紀錄與斷鏈文件，建立後續 Agent 的單一交接入口。

目前應記錄的基線：

```text
GitHub main: 10e0ec6
Current Gate: C2 — Host Bootstrapped / Waiting External Configuration
Remote user: harcker8119
Production: ACTIVE and unchanged
Staging bootstrap: completed
Shared Staging deployment: not executed
HTTPS host: missing
LINE/LIFF: missing
DATABASE_URL: missing
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


## Phase 1：建立文件分支

建議分支：

```text
docs/gate-c2-status-sync
```

驗證：

```bash
git branch --show-current
git status --short
git rev-parse --short HEAD
```

## Phase 2：更新既有文件

更新：

- `docs/integration/customer-validation-gate-c2-report.md`
- `docs/deployment/staging-deployment-runbook.md`
- `docs/database_execution_runbook.md`
- `AGENTS.md`

要求：

1. 將 SSH context、remote user、Bootstrap 完成狀態改為真實結果。
2. 明確標示 Shared Staging、HTTPS、LINE E2E 尚未完成。
3. 將舊的 `crawl_posts.id=393` 改為 historical cutover note。
4. 更新測試數量時必須附日期、commit 與實際命令。
5. 不得寫入 VM IP、secret、LINE user ID 或 DATABASE_URL。

## Phase 3：新增斷鏈文件

新增：

- `docs/AGENT_HANDOFF.md`
- `docs/architecture_review.md`

`AGENT_HANDOFF.md` 至少包含：

- current commit
- current gate
- completed／pending／blocked
- Staging topology
- Production protection values
- 下一個精確動作
- 禁止事項

`architecture_review.md` 至少包含：

- 模組化 FastAPI＋n8n＋Supabase 架構
- 非完整 microservices 的說明
- 已完成／尚未完成能力
- AI analysis 與 alert pipeline 的真實狀態
- 主要風險與技術債

## Phase 4：文件驗證

執行：

```bash
test -f docs/AGENT_HANDOFF.md
test -f docs/architecture_review.md
grep -R "No SSH or remote staging runtime context" docs || true
grep -R "crawl_posts.id = 393" docs || true
git diff --check
git status --short
```

驗證標準：

- `AGENTS.md` 引用的三份文件全部存在。
- 不再將 SSH 視為缺少。
- 不再將歷史 `id=393` 當作現況 blocker。
- Gate C2 仍維持 `WAITING_EXTERNAL_CONFIGURATION`。
- 文件不得誤稱 AI／alert 已完整上線。

## 完成條件

```text
RESULT: PASS
DOCUMENT_LINKS_VALID=YES
GATE_C2_STATUS_CURRENT=YES
HISTORICAL_NOTES_SEPARATED=YES
SECRETS_IN_DOCS=NO
```
