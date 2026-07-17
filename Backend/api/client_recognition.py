from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Callable

try:
    import psycopg2
except ModuleNotFoundError:  # pragma: no cover - surfaced as configuration error at runtime
    psycopg2 = None

from pydantic import BaseModel, Field

from api.reputation import DatabaseConfigurationError


class ClientRecognitionRequest(BaseModel):
    line_user_id: str = Field(min_length=1, max_length=255)


@dataclass(frozen=True)
class ClientRecognitionResult:
    client_registered: bool
    client_created: bool
    client_found: bool
    client_id: int | None
    business_found: bool
    business_id: int | None
    business_name: str | None
    branch_name: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ClientRecognitionRepository:
    """Register a LINE client ID and resolve its first active business."""

    def __init__(self, connection_factory: Callable[[], Any] | None = None) -> None:
        self._connection_factory = connection_factory or self._default_connection

    @staticmethod
    def _default_connection():
        if psycopg2 is None:
            raise DatabaseConfigurationError(
                "psycopg2 is required for the client recognition API"
            )

        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise DatabaseConfigurationError(
                "DATABASE_URL is required for the client recognition API"
            )

        return psycopg2.connect(database_url, connect_timeout=10)

    def recognize(self, line_user_id: str) -> ClientRecognitionResult:
        conn = self._connection_factory()
        try:
            return self._recognize(conn, line_user_id=line_user_id)
        finally:
            conn.close()

    @staticmethod
    def _recognize(conn: Any, *, line_user_id: str) -> ClientRecognitionResult:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO clients (
                        line_user_id,
                        name,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, 'active', NOW(), NOW())
                    ON CONFLICT (line_user_id) DO UPDATE SET
                        name = COALESCE(NULLIF(clients.name, ''), EXCLUDED.name),
                        status = 'active',
                        updated_at = NOW()
                    RETURNING id, (xmax = 0) AS inserted
                    """,
                    (line_user_id, line_user_id),
                )
                client_row = cursor.fetchone()

                if not client_row:
                    raise DatabaseConfigurationError(
                        "Unable to register LINE client"
                    )

                client_id = int(client_row[0])
                client_created = bool(client_row[1])

                cursor.execute(
                    """
                    SELECT id, name, branch_name
                    FROM business
                    WHERE client_id = %s
                      AND status = 'active'
                    ORDER BY id
                    LIMIT 1
                    """,
                    (client_id,),
                )
                business_row = cursor.fetchone()

            conn.commit()
        except Exception:
            conn.rollback()
            raise

        if not business_row:
            return ClientRecognitionResult(
                client_registered=True,
                client_created=client_created,
                client_found=True,
                client_id=client_id,
                business_found=False,
                business_id=None,
                business_name=None,
                branch_name=None,
            )

        return ClientRecognitionResult(
            client_registered=True,
            client_created=client_created,
            client_found=True,
            client_id=client_id,
            business_found=True,
            business_id=int(business_row[0]),
            business_name=str(business_row[1]),
            branch_name=business_row[2],
        )
