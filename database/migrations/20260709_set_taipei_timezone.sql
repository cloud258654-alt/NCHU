-- Configure BI-RMP Supabase/PostgreSQL sessions to display timestamptz values in Taiwan time.
-- This migration does not rewrite stored data. Existing timestamptz values remain the same absolute instants.
-- Run this in Supabase SQL Editor, then reconnect clients or refresh the Table Editor.

BEGIN;

-- Default Supabase database name is usually "postgres".
-- This affects new database sessions after reconnect.
ALTER DATABASE postgres SET timezone TO 'Asia/Taipei';

-- Apply the setting to common Supabase roles when they exist.
-- The role-level setting helps SQL Editor, PostgREST/API sessions, and service-role sessions display timestamptz consistently.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'postgres') THEN
    ALTER ROLE postgres SET timezone TO 'Asia/Taipei';
  END IF;

  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticator') THEN
    ALTER ROLE authenticator SET timezone TO 'Asia/Taipei';
  END IF;

  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    ALTER ROLE anon SET timezone TO 'Asia/Taipei';
  END IF;

  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    ALTER ROLE authenticated SET timezone TO 'Asia/Taipei';
  END IF;

  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    ALTER ROLE service_role SET timezone TO 'Asia/Taipei';
  END IF;
END $$;

-- Apply to this current SQL Editor session immediately.
SET TIME ZONE 'Asia/Taipei';

COMMIT;

-- Verification query. Expected timezone = Asia/Taipei and current_timestamp shows +08.
SELECT
  current_setting('TIMEZONE') AS timezone,
  current_timestamp AS current_timestamp_in_session,
  current_timestamp AT TIME ZONE 'Asia/Taipei' AS taipei_local_timestamp;
