# BI-RMP 待進行模組計畫索引

依序執行：

1. `001-project-status-documentation-plans.md`
2. `002-staging-https-host-plans.md`
3. `003-supabase-runtime-configuration-plans.md`
4. `004-line-liff-staging-plans.md`
5. `005-shared-staging-deployment-plans.md`
6. `006-line-liff-e2e-validation-plans.md`
7. `007-supabase-readback-rollback-plans.md`
8. `008-gate-c2-closeout-plans.md`
9. `009-ai-analysis-pipeline-plans.md`
10. `010-alert-notification-plans.md`
11. `011-github-ci-security-hardening-plans.md`

## 執行原則

- 001～008：完成 Customer Validation Gate C2。
- 009～010：完成 AI 分析與警示功能。
- 011：完成 CI、主線治理與安全強化。
- 每個模組都必須留下 `RESULT`、測試結果、Production 隔離證據及 rollback 狀態。
- 前一模組未 PASS，不得直接跳到依賴它的後續模組。
