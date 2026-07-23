BEGIN;

ALTER TABLE analysis_results
  ADD COLUMN IF NOT EXISTS worker_id VARCHAR,
  ADD COLUMN IF NOT EXISTS claim_token VARCHAR,
  ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS idx_analysis_results_lease
  ON analysis_results(lease_expires_at)
  WHERE idempotency_key IS NOT NULL AND analysis_status = 'processing';

COMMIT;
