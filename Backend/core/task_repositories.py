from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.logger import get_logger


logger = get_logger("core.task_repositories")


class ServiceTaskRepository:
    """service_tasks repository for the BIGINT clean schema."""

    SERVICE_TYPE_ALIASES = {
        "reputation_query": "reputation_monitoring",
        "reputation_monitoring": "reputation_monitoring",
        "reputation": "reputation_monitoring",
        "風評查詢": "reputation_monitoring",
        "reservation": "reservation_management",
        "reservation_management": "reservation_management",
        "預約服務": "reservation_management",
        "business_insight": "business_insight",
    }
    SCHEDULE_TYPE_ALIASES = {
        "once": "once",
        "scheduled": "daily",
        "recurring": "daily",
        "hourly": "hourly",
        "daily": "daily",
        "weekly": "weekly",
    }

    def get_business_by_line_user_id(self, line_user_id: str) -> str | None:
        """Get the first business name registered under a LINE user ID."""
        from core.supabase import get_connection
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT b.name
                    FROM business b
                    JOIN clients c ON b.client_id = c.id
                    WHERE c.line_user_id = %s
                    ORDER BY b.created_at ASC
                    LIMIT 1
                    """,
                    (line_user_id,),
                )
                row = cur.fetchone()
                return row[0] if row else None
        except Exception as exc:
            logger.warning("Error fetching business by line_user_id: %s", exc)
            return None
        finally:
            if 'conn' in locals() and conn:
                conn.close()

    def find_reputation_job(
        self,
        *,
        line_user_id: str,
        source_message_id: str | None = None,
        active_only: bool = False,
    ) -> dict[str, Any] | None:
        """Find an idempotent or currently active LINE reputation task."""

        from core.supabase import get_connection

        conditions = [
            "c.line_user_id = %s",
            "st.service_type = 'reputation_monitoring'",
        ]
        params: list[Any] = [line_user_id]
        if source_message_id:
            conditions.append("st.config ->> 'source_message_id' = %s")
            params.append(source_message_id)
        elif active_only:
            conditions.append("st.status IN ('pending', 'running')")

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT st.id, st.status, st.config, st.created_at, st.updated_at,
                           b.name, c.line_user_id
                    FROM service_tasks st
                    JOIN business b ON b.id = st.business_id
                    JOIN clients c ON c.id = b.client_id
                    WHERE {' AND '.join(conditions)}
                    ORDER BY st.created_at DESC
                    LIMIT 1
                    """,
                    tuple(params),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        return self._job_request_row(row)

    def get_reputation_job(
        self,
        task_id: str,
        *,
        line_user_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Load one reputation task, optionally enforcing LINE ownership."""

        from core.supabase import get_connection

        conditions = ["st.id = %s", "st.service_type = 'reputation_monitoring'"]
        params: list[Any] = [task_id]
        if line_user_id:
            conditions.append("c.line_user_id = %s")
            params.append(line_user_id)

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT st.id, st.status, st.config, st.created_at, st.updated_at,
                           b.name, c.line_user_id
                    FROM service_tasks st
                    JOIN business b ON b.id = st.business_id
                    JOIN clients c ON c.id = b.client_id
                    WHERE {' AND '.join(conditions)}
                    LIMIT 1
                    """,
                    tuple(params),
                )
                row = cur.fetchone()
        finally:
            conn.close()
        return self._job_request_row(row)

    def get_reputation_job_status(
        self,
        task_id: str,
        *,
        line_user_id: str | None = None,
    ) -> dict[str, Any] | None:
        task = self.get_reputation_job(task_id, line_user_id=line_user_id)
        if task is None:
            return None

        from core.supabase import get_connection

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT platform, status, start_time, end_time, total_posts,
                           total_comments, error_message, execution_config
                    FROM crawl_jobs
                    WHERE service_task_id = %s
                    ORDER BY created_at ASC, id ASC
                    """,
                    (task_id,),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

        platform_results = []
        for row in rows:
            execution_config = row[7] if isinstance(row[7], dict) else {}
            result_summary = execution_config.get("result_summary") or {}
            error_message = row[6] or result_summary.get("error_message")
            error_type = result_summary.get("error_type")
            if not error_type and error_message and any(
                marker in error_message.casefold()
                for marker in ("deadline", "time budget", "timed out", "timeout", "exceeded")
            ):
                error_type = "timeout"
            platform_results.append(
                {
                    "platform": row[0],
                    "status": row[1],
                    "started_at": row[2].isoformat() if row[2] else None,
                    "finished_at": row[3].isoformat() if row[3] else None,
                    "articles_found": int(result_summary.get("cards_found") or row[4] or 0),
                    "comments_found": int(result_summary.get("comments_found") or row[5] or 0),
                    "canonical_posts_written": int(result_summary.get("canonical_posts_written") or row[4] or 0),
                    "canonical_comments_written": int(result_summary.get("canonical_comments_written") or row[5] or 0),
                    "outcome": result_summary.get("outcome"),
                    "error_type": error_type,
                    "error_message": error_message,
                }
            )

        successful = sum(1 for item in platform_results if item["status"] == "success")
        failed = sum(1 for item in platform_results if item["status"] == "failed")
        terminal = task["status"] in {"completed", "failed", "cancelled"}
        if terminal and successful and failed:
            public_status = "partial_success"
        elif terminal and failed and not successful:
            public_status = (
                "timeout"
                if platform_results and all(item["error_type"] == "timeout" for item in platform_results)
                else "failed"
            )
        elif terminal and task["status"] == "completed":
            public_status = "completed"
        else:
            public_status = task["status"]

        errors = [item["error_message"] for item in platform_results if item["error_message"]]
        config = task.get("config") or {}
        return {
            **task,
            "status": public_status,
            "ready": terminal,
            "started_at": min(
                (item["started_at"] for item in platform_results if item["started_at"]),
                default=None,
            ),
            "platform_results": platform_results,
            "articles_found": sum(item["articles_found"] for item in platform_results),
            "comments_found": sum(item["comments_found"] for item in platform_results),
            "error_message": "; ".join(errors) or config.get("last_error"),
        }

    @staticmethod
    def _job_request_row(row) -> dict[str, Any] | None:
        if not row:
            return None
        return {
            "task_id": str(row[0]),
            "status": row[1],
            "config": row[2] if isinstance(row[2], dict) else {},
            "created_at": row[3].isoformat() if row[3] else None,
            "updated_at": row[4].isoformat() if row[4] else None,
            "business_name": row[5],
            "line_user_id": row[6],
        }

    def create(
        self,
        *,
        service_type: str,
        schedule_type: str = "once",
        channel: str = "cli",
        client_id: str | None = None,
        business_id: str | None = None,
        client_name: str | None = None,
        business_name: str | None = None,
        line_user_id: str | None = None,
        source_message_id: str | None = None,
        request_payload: dict[str, Any] | None = None,
    ) -> str | None:
        service_type = self._normalize_service_type(service_type)
        schedule_type = self._normalize_schedule_type(schedule_type)
        try:
            created_task_id = self._create_with_database(
                service_type=service_type,
                schedule_type=schedule_type,
                client_id=client_id,
                business_id=business_id,
                client_name=client_name,
                business_name=business_name,
                line_user_id=line_user_id,
                config={
                    **(request_payload or {}),
                    "channel": channel,
                    "source_message_id": source_message_id,
                },
            )
            if created_task_id:
                return created_task_id
        except Exception as exc:
            logger.debug("service_tasks write skipped: %s", exc)
        return None

    def _create_with_database(
        self,
        *,
        service_type: str,
        schedule_type: str,
        client_id: str | None,
        business_id: str | None,
        client_name: str | None,
        business_name: str | None,
        line_user_id: str | None,
        config: dict[str, Any],
    ) -> str | None:
        from core.supabase import get_connection
        from psycopg2.extras import Json

        now = datetime.now(timezone.utc)
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                resolved_client_id = client_id or self._resolve_client_id(
                    cur,
                    display_name=client_name,
                    line_user_id=line_user_id,
                    now=now,
                )
                if not resolved_client_id and business_id:
                    resolved_client_id = self._client_id_for_business(cur, business_id=business_id)
                resolved_business_id = business_id or self._resolve_business_id(
                    cur,
                    client_id=resolved_client_id,
                    business_name=business_name,
                    now=now,
                )
                if not resolved_client_id or not resolved_business_id:
                    raise ValueError("client_id/client_name and business_id/business_name are required for service_tasks")
                cur.execute(
                    """
                    INSERT INTO service_tasks (
                        business_id, service_type, schedule_type, status,
                        config, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s
                    )
                    RETURNING id
                    """,
                    (
                        resolved_business_id,
                        service_type,
                        schedule_type,
                        "pending",
                        Json(config),
                        now,
                        now,
                    ),
                )
                row = cur.fetchone()
        conn.close()
        return str(row[0]) if row else None

    def _resolve_client_id(self, cur, *, display_name: str | None, line_user_id: str | None, now: datetime) -> str | None:
        if not line_user_id:
            line_user_id = "default-line-id"
        if not display_name:
            display_name = "default-line-id"
        if line_user_id:
            cur.execute(
                """
                INSERT INTO clients (line_user_id, name, created_at, updated_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (line_user_id) DO UPDATE SET
                    name = COALESCE(EXCLUDED.name, clients.name),
                    updated_at = EXCLUDED.updated_at
                RETURNING id
                """,
                (line_user_id, display_name or line_user_id, now, now),
            )
        else:
            cur.execute(
                """
                SELECT id
                FROM clients
                WHERE line_user_id IS NULL
                  AND lower(name) = lower(%s)
                """,
                (display_name,),
            )
            row = cur.fetchone()
            if row:
                cur.execute("UPDATE clients SET updated_at = %s WHERE id = %s", (now, row[0]))
                return str(row[0])
            cur.execute(
                """
                INSERT INTO clients (name, created_at, updated_at)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (display_name, now, now),
            )
        row = cur.fetchone()
        return str(row[0]) if row else None

    def _resolve_business_id(self, cur, *, client_id: str | None, business_name: str | None, now: datetime) -> str | None:
        if not business_name:
            return None
        cur.execute(
            """
            SELECT id
            FROM business
            WHERE lower(name) = lower(%s)
            """,
            (business_name,),
        )
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE business SET updated_at = %s WHERE id = %s", (now, row[0]))
            return str(row[0])
        if not client_id:
            return None
        cur.execute(
            """
            INSERT INTO business (client_id, name, created_at, updated_at)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (client_id, business_name, now, now),
        )
        row = cur.fetchone()
        return str(row[0]) if row else None

    def _client_id_for_business(self, cur, *, business_id: str) -> str | None:
        cur.execute("SELECT client_id FROM business WHERE id = %s", (business_id,))
        row = cur.fetchone()
        return str(row[0]) if row else None

    def _normalize_service_type(self, service_type: str) -> str:
        normalized = (service_type or "reputation_monitoring").strip()
        return self.SERVICE_TYPE_ALIASES.get(normalized, normalized)

    def _normalize_schedule_type(self, schedule_type: str) -> str:
        normalized = (schedule_type or "once").strip()
        return self.SCHEDULE_TYPE_ALIASES.get(normalized, normalized)

    def mark_running(self, task_id: str | None) -> None:
        if task_id is None:
            return
        self._execute(
            "UPDATE service_tasks SET status = %s, updated_at = %s WHERE id = %s",
            ("running", datetime.now(timezone.utc), task_id),
        )

    def claim_pending(self, task_id: str | None) -> bool:
        if task_id is None:
            return False
        try:
            from core.supabase import get_connection

            now = datetime.now(timezone.utc)
            conn = get_connection()
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE service_tasks
                        SET status = %s, updated_at = %s
                        WHERE id = %s AND status = %s
                        RETURNING id
                        """,
                        ("running", now, task_id, "pending"),
                    )
                    claimed = cur.fetchone() is not None
            conn.close()
            return claimed
        except Exception as exc:
            logger.debug("service_tasks atomic claim skipped: %s", exc)
            return False

    def mark_finished(self, task_id: str | None) -> None:
        if task_id is None:
            return
        self._execute(
            "UPDATE service_tasks SET status = %s, updated_at = %s WHERE id = %s",
            ("completed", datetime.now(timezone.utc), task_id),
        )

    def mark_failed(self, task_id: str | None, error_message: str) -> None:
        if task_id is None:
            return
        self._execute(
            """
            UPDATE service_tasks
            SET status = %s,
                config = config || %s::jsonb,
                updated_at = %s
            WHERE id = %s
            """,
            ("failed", {"last_error": error_message}, datetime.now(timezone.utc), task_id),
        )

    def _execute(self, query: str, params: tuple) -> None:
        try:
            from core.supabase import get_connection
            from psycopg2.extras import Json

            converted = tuple(Json(value) if isinstance(value, dict) else value for value in params)
            conn = get_connection()
            with conn:
                with conn.cursor() as cur:
                    cur.execute(query, converted)
            conn.close()
        except Exception as exc:
            logger.debug("service_tasks write skipped: %s", exc)


class CrawlJobRepository:
    """crawl_jobs repository for the BIGINT clean schema."""

    def create(
        self,
        *,
        platform: str,
        keyword: str | None,
        query: str,
        service_task_id: str | None = None,
        target_url: str | None = None,
    ) -> str | None:
        if service_task_id is None:
            return None
        now = datetime.now(timezone.utc)
        return self._insert(
            """
            INSERT INTO crawl_jobs (
                service_task_id, platform, keyword, status, trigger_source, run_mode,
                execution_config, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s
            )
            RETURNING id
            """,
            (
                service_task_id,
                platform,
                keyword,
                "pending",
                "system",
                "manual",
                {"query": query, "target_url": target_url},
                now,
                now,
            ),
        )

    def mark_started(self, job_id: str | None) -> None:
        if job_id is None:
            return
        self._execute(
            "UPDATE crawl_jobs SET status = %s, start_time = %s, updated_at = %s WHERE id = %s",
            ("running", datetime.now(timezone.utc), datetime.now(timezone.utc), job_id),
        )

    def merge_execution_config(self, job_id: str | None, values: dict[str, Any]) -> None:
        if job_id is None or not values:
            return
        self._execute(
            """
            UPDATE crawl_jobs
            SET execution_config = COALESCE(execution_config, '{}'::jsonb) || %s::jsonb,
                updated_at = %s
            WHERE id = %s
            """,
            (values, datetime.now(timezone.utc), job_id),
        )

    def mark_finished(
        self,
        job_id: str | None,
        *,
        total_posts: int | None = None,
        total_comments: int | None = None,
        result_summary: dict[str, Any] | None = None,
    ) -> None:
        if job_id is None:
            return
        self._execute(
            """
            UPDATE crawl_jobs
            SET status = %s,
                end_time = %s,
                total_posts = COALESCE(%s, total_posts),
                total_comments = COALESCE(%s, total_comments),
                execution_config = COALESCE(execution_config, '{}'::jsonb) || %s::jsonb,
                updated_at = %s
            WHERE id = %s
            """,
            (
                "success",
                datetime.now(timezone.utc),
                total_posts,
                total_comments,
                {"result_summary": result_summary or {}},
                datetime.now(timezone.utc),
                job_id,
            ),
        )

    def mark_failed(self, job_id: str | None, error_message: str) -> None:
        if job_id is None:
            return
        self._execute(
            """
            UPDATE crawl_jobs
            SET status = %s, end_time = %s, error_message = %s, updated_at = %s
            WHERE id = %s
            """,
            ("failed", datetime.now(timezone.utc), error_message, datetime.now(timezone.utc), job_id),
        )

    def _insert(self, query: str, params: tuple) -> str | None:
        try:
            from core.supabase import get_connection
            from psycopg2.extras import Json

            converted = tuple(Json(value) if isinstance(value, dict) else value for value in params)
            conn = get_connection()
            with conn:
                with conn.cursor() as cur:
                    cur.execute(query, converted)
                    row = cur.fetchone()
            conn.close()
            return str(row[0]) if row else None
        except Exception as exc:
            logger.debug("crawl_jobs write skipped: %s", exc)
            return None

    def _execute(self, query: str, params: tuple) -> None:
        try:
            from core.supabase import get_connection
            from psycopg2.extras import Json

            converted = tuple(Json(value) if isinstance(value, dict) else value for value in params)
            conn = get_connection()
            with conn:
                with conn.cursor() as cur:
                    cur.execute(query, converted)
            conn.close()
        except Exception as exc:
            logger.debug("crawl_jobs write skipped: %s", exc)
