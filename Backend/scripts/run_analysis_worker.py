from __future__ import annotations

import argparse
import socket
import uuid

from core.analysis_pipeline import (
    DEFAULT_LEASE_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    PostgresAnalysisQueue,
    process_next,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one durable BI-RMP analysis queue job.")
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    parser.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)
    parser.add_argument("--worker-id", default=None)
    args = parser.parse_args()
    worker_id = args.worker_id or f"{socket.gethostname()}-{uuid.uuid4().hex}"
    result = process_next(
        PostgresAnalysisQueue(),
        max_attempts=args.max_attempts,
        worker_id=worker_id,
        lease_seconds=args.lease_seconds,
    )
    print(result.status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
