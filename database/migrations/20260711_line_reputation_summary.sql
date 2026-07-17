BEGIN;

ALTER TABLE analysis_results
  ADD COLUMN IF NOT EXISTS risk_score NUMERIC(5, 2),
  ADD COLUMN IF NOT EXISTS risk_points INTEGER;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'chk_analysis_results_risk_score'
  ) THEN
    ALTER TABLE analysis_results
      ADD CONSTRAINT chk_analysis_results_risk_score
      CHECK (risk_score IS NULL OR (risk_score >= 0 AND risk_score <= 100));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'chk_analysis_results_risk_points'
  ) THEN
    ALTER TABLE analysis_results
      ADD CONSTRAINT chk_analysis_results_risk_points
      CHECK (risk_points IS NULL OR risk_points >= 0);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_analysis_results_risk_score
  ON analysis_results(risk_score DESC, analyzed_at DESC);

COMMENT ON COLUMN analysis_results.risk_score IS
  'Normalized numeric risk score from 0 to 100.';
COMMENT ON COLUMN analysis_results.risk_points IS
  'Additive risk points produced by the analysis pipeline.';

COMMIT;
