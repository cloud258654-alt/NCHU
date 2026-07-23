BEGIN;

ALTER TABLE analysis_results
  ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR,
  ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS last_error TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_analysis_results_idempotency_key
  ON analysis_results(idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_analysis_results_queue
  ON analysis_results(analysis_status, next_attempt_at, created_at)
  WHERE idempotency_key IS NOT NULL;

COMMIT;
