# 008 — Gate C2 驗收關閉計畫

## 目標

整合 002～007 的證據，將 Gate C2 正式判定為 PASS、FAIL 或 BLOCKED。


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


## Phase 1：彙整證據

必須收集：

- HTTPS/TLS
- Backend health
- n8n readiness
- LINE webhook Verify
- LIFF registration
- task creation
- crawler results
- Quick Reply
- canonical report
- tenant/task isolation
- Supabase readback
- rollback rehearsal
- Production isolation
- full regression

## Phase 2：更新 Gate C2 報告

更新：

```text
docs/integration/customer-validation-gate-c2-report.md
```

加入：

- deployed commit
- public host（可公開 hostname）
- E2E timestamp
- anonymized task/business IDs
- 實際測試結果
- remaining risks
- PASS／FAIL 結論

不得寫入 secret、LINE user ID、VM IP。

## Phase 3：重新執行完整測試

```bash
python -m compileall -q Backend
python -m pytest -q
python -m json.tool infra/n8n/workflows/reputation-optimization-flow.json
docker compose --env-file .env.staging.example   -f infra/n8n/docker-compose.yml   -f infra/n8n/docker-compose.staging.yml config
git diff --check
```

## Phase 4：Gate 判定

只有以下全數通過才可：

```text
RESULT: PASS
GATE: C2
```

任一實際 E2E 缺失則不得 PASS。

## Phase 5：Commit 與 PR

建議：

```text
docs(gate-c2): record shared staging and LINE E2E validation
```

必須經 review、PR、CI，再 merge main。

## 完成條件

```text
RESULT: PASS
GATE_C2=PASS
LIVE_STAGING=VERIFIED
LINE_LIFF_E2E=VERIFIED
SUPABASE_READBACK=VERIFIED
ROLLBACK_REHEARSAL=VERIFIED
PRODUCTION_ISOLATION=VERIFIED
FULL_REGRESSION=PASS
DOCUMENTATION_CURRENT=YES
```
