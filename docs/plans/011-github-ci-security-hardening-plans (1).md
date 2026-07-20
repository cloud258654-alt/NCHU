# 011 — GitHub CI 與安全強化計畫

## 目標

將目前主要依賴本地 CLI 的測試，升級為 GitHub 強制 CI 與 main branch protection。


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


## Phase 1：CI Workflow

建立或修正：

```text
.github/workflows/ci.yml
```

至少執行：

- Python compile
- full pytest
- n8n workflow JSON／JS validation
- Docker Compose config
- shell syntax
- secret scan
- `git diff --check`

## Phase 2：Branch Protection

設定：

- main 禁止直接 push
- 禁止 force push
- PR required
- required status checks
- 至少一次 review
- branch up-to-date before merge

## Phase 3：Secret Scanning

啟用：

- GitHub secret scanning
- push protection
- dependency alerts

確認 public repository 無歷史 secret。

## Phase 4：Supabase 最小權限整理

另開 migration 計畫，評估撤銷 `anon`／`authenticated` 不需要的：

```text
REFERENCES
TRIGGER
TRUNCATE
```

並補：

- `alerts.analysis_result_id` index
- `client_messages_log.client_id` index

此步驟不得與 Gate C2 live deployment 混在同一 commit。

## Phase 5：驗證

- PR 沒有 CI 不可 merge
- 故意破壞測試會阻擋
- secret fixture 不被誤判，真 secret pattern 可阻擋
- main direct push 被拒絕

## 完成條件

```text
RESULT: PASS
CI_WORKFLOW=ACTIVE
FULL_TESTS_IN_CI=PASS
MAIN_DIRECT_PUSH=BLOCKED
FORCE_PUSH=BLOCKED
SECRET_SCANNING=ACTIVE
REQUIRED_CHECKS=ACTIVE
```
