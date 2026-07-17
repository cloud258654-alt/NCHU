from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.supabase import get_connection


DEFAULT_PLATFORMS = ("ptt", "google_maps", "threads")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify latest MVP crawler rows against the minimal runtime schema.")
    parser.add_argument(
        "--platforms",
        default=",".join(DEFAULT_PLATFORMS),
        help="Comma-separated platform list to verify. Defaults to MVP platforms.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    platforms = tuple(platform.strip() for platform in args.platforms.split(",") if platform.strip())
    if not platforms:
        print("[FAIL] no platforms requested")
        return 1

    try:
        conn = get_connection()
    except Exception as exc:
        print(f"[FAIL] DATABASE_URL/connection unavailable: {exc}")
        return 1

    failures: list[str] = []
    with conn:
        with conn.cursor() as cur:
            for platform in platforms:
                report = _latest_platform_report(cur, platform)
                _print_report(report)
                if not report["job"]:
                    failures.append(f"{platform}: no crawl_jobs row")
                    continue
                if report["job"]["status"] != "success":
                    failures.append(f"{platform}: latest crawl_jobs.status is {report['job']['status']}")
                if _requires_data_yield(report["job"]):
                    if report["posts"] <= 0:
                        failures.append(f"{platform}: no crawl_posts linked to latest job")
                    if report["post_snapshots"] <= 0:
                        failures.append(f"{platform}: no post_metric_snapshots collected during latest job")
                elif report["job"]["total_posts"] not in (0, None) or report["job"]["total_comments"] not in (0, None):
                    failures.append(f"{platform}: zero-yield job has nonzero total counts")

    conn.close()
    if failures:
        print("Verification failed:")
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1

    print("[PASS] Latest MVP crawler jobs resolve through crawl_posts; child rows use canonical parent links.")
    return 0


def _latest_platform_report(cur, platform: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT id, service_task_id, platform, keyword, status, total_posts, total_comments,
               execution_config, created_at, start_time
        FROM crawl_jobs
        WHERE platform = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (platform,),
    )
    row = cur.fetchone()
    if not row:
        return {"platform": platform, "job": None, "posts": 0, "comments": 0, "post_snapshots": 0, "comment_snapshots": 0}

    job = {
        "id": row[0],
        "service_task_id": row[1],
        "platform": row[2],
        "keyword": row[3],
        "status": row[4],
        "total_posts": row[5],
        "total_comments": row[6],
        "execution_config": row[7],
        "created_at": row[8],
        "start_time": row[9],
    }
    job_id = job["id"]
    cur.execute("SELECT COUNT(*) FROM crawl_posts WHERE crawl_job_id = %s", (job_id,))
    posts = int(cur.fetchone()[0])
    cur.execute(
        """
        SELECT COUNT(*)
        FROM crawl_comments AS comment_row
        JOIN crawl_posts AS post ON post.id = comment_row.crawl_post_id
        WHERE post.crawl_job_id = %s
        """,
        (job_id,),
    )
    comments = int(cur.fetchone()[0])
    cur.execute(
        """
        SELECT COUNT(*)
        FROM post_metric_snapshots AS metric
        JOIN crawl_posts AS post ON post.id = metric.crawl_post_id
        JOIN crawl_jobs AS job ON job.id = post.crawl_job_id
        WHERE post.crawl_job_id = %s
          AND metric.collected_at >= COALESCE(job.start_time, job.created_at)
        """,
        (job_id,),
    )
    post_snapshots = int(cur.fetchone()[0])
    cur.execute(
        """
        SELECT COUNT(*)
        FROM comment_metric_snapshots AS metric
        JOIN crawl_comments AS comment_row ON comment_row.id = metric.crawl_comment_id
        JOIN crawl_posts AS post ON post.id = comment_row.crawl_post_id
        JOIN crawl_jobs AS job ON job.id = post.crawl_job_id
        WHERE post.crawl_job_id = %s
          AND metric.collected_at >= COALESCE(job.start_time, job.created_at)
        """,
        (job_id,),
    )
    comment_snapshots = int(cur.fetchone()[0])
    return {
        "platform": platform,
        "job": job,
        "posts": posts,
        "comments": comments,
        "post_snapshots": post_snapshots,
        "comment_snapshots": comment_snapshots,
    }


def _print_report(report: dict[str, Any]) -> None:
    platform = report["platform"]
    job = report["job"]
    if not job:
        print(f"[FAIL] {platform}: no crawl_jobs row")
        return
    summary = _result_summary(job)
    print(
        f"[{platform}] job={job['id']} status={job['status']} "
        f"outcome={summary.get('outcome')} data_yield={summary.get('data_yield_success')} "
        f"posts={report['posts']} comments={report['comments']} "
        f"post_snapshots={report['post_snapshots']} comment_snapshots={report['comment_snapshots']}"
    )


def _result_summary(job: dict[str, Any]) -> dict[str, Any]:
    config = job.get("execution_config")
    if not isinstance(config, dict):
        return {}
    summary = config.get("result_summary")
    return summary if isinstance(summary, dict) else {}


def _requires_data_yield(job: dict[str, Any]) -> bool:
    summary = _result_summary(job)
    if "data_yield_success" in summary:
        return bool(summary["data_yield_success"])
    return int(job.get("total_posts") or 0) > 0 or int(job.get("total_comments") or 0) > 0


if __name__ == "__main__":
    raise SystemExit(main())
