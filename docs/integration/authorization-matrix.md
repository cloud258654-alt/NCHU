# Authorization Matrix

Date: 2026-07-17
Status: Draft / not staging-verified

## Scope

This matrix records the intended authorization checks for BI-RMP Dashboard, LINE, and ML flows. It has not been validated against BI-RMP-V2-STAGING because Phase 6 did not pass and no migration was applied.

## Current Verification Status

- Staging migration applied: no
- Supabase project linked: no
- `supabase/.temp/project-ref`: absent
- Staging RLS policies verified: no
- Advisor checks verified: no
- Test data inserted: no
- Test data cleaned: not applicable

## Intended Access Matrix

| Actor | Resource | Same Business | Other Business | Expected |
|---|---|---:|---:|---|
| Unauthenticated request | Dashboard read API | n/a | n/a | 401 once auth is enforced |
| Authenticated business user | Own business dashboard summary | yes | no | 200 |
| Authenticated business user | Other business dashboard summary | no | yes | 403 |
| Authenticated business user | Own business reviews | yes | no | 200 |
| Authenticated business user | Other business reviews | no | yes | 403 |
| Authenticated business user | Own review detail | yes | no | 200 |
| Authenticated business user | Missing review detail | n/a | n/a | 404 |
| Authenticated business user | Other business review detail | no | yes | 403 |
| Internal n8n worker | Internal LINE/crawler endpoints | scoped by internal API key | n/a | 200 when key is valid |
| Missing internal API key | Internal LINE/crawler endpoints | n/a | n/a | 401 |
| ML worker | Write canonical `analysis_results` | scoped job/review | cross-business write denied | 200/201 or 403 by scope |

## ML Idempotency Target

Future staging validation should verify that ML writes are idempotent by:

- `review_id`
- `model_version`
- `analysis_type`

The canonical destination is `analysis_results`. New unmanaged result tables or duplicate write paths should not be introduced.

## RLS / Policy Requirements

Future migrations should satisfy these rules before remote application:

- Enable RLS on public tables exposed through Supabase APIs.
- Use explicit `TO authenticated` / `TO anon` policy roles instead of broad default policies.
- Do not rely on user-editable `raw_user_meta_data` / `user_metadata` for authorization.
- Use `raw_app_meta_data` or server-owned mapping tables for authorization claims.
- For UPDATE policies, define both `USING` and `WITH CHECK`.
- For exposed views, use `security_invoker=true` or keep the view unexposed.
- Avoid `SECURITY DEFINER`; when unavoidable, keep it outside `public`, restrict `search_path`, and revoke PUBLIC execute.
- Add indexes for policy columns such as `business_id`, `client_id`, and auth ownership keys.

## Blocker

This matrix is not an acceptance artifact until it is executed against BI-RMP-V2-STAGING after Phase 6 passes and the project ref is confirmed as `qlhykeeyjaoikczoambe`.
