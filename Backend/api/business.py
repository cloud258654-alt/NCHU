from __future__ import annotations

import os
from typing import Any, Callable

try:
    import psycopg2
except ModuleNotFoundError:  # pragma: no cover
    psycopg2 = None

from pydantic import BaseModel, Field

from api.reputation import DatabaseConfigurationError


class BusinessCheckDuplicateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class BusinessRegisterRequest(BaseModel):
    line_user_id: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    branch_name: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=1000)
    client_name: str | None = Field(default=None, max_length=255)


class BusinessRepository:
    """Check duplicate business names and handle new store registrations."""

    def __init__(self, connection_factory: Callable[[], Any] | None = None) -> None:
        self._connection_factory = connection_factory or self._default_connection

    @staticmethod
    def _default_connection():
        if psycopg2 is None:
            raise DatabaseConfigurationError(
                "psycopg2 is required for the business API"
            )

        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise DatabaseConfigurationError(
                "DATABASE_URL is required for the business API"
            )

        return psycopg2.connect(database_url, connect_timeout=10)

    def check_duplicate(self, name: str) -> bool:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM business WHERE lower(name) = lower(%s) LIMIT 1",
                    (name.strip(),),
                )
                row = cursor.fetchone()
                return row is not None
        finally:
            conn.close()

    def register(
        self,
        line_user_id: str,
        name: str,
        branch_name: str | None = None,
        industry: str | None = None,
        address: str | None = None,
        client_name: str | None = None,
    ) -> dict[str, Any]:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cursor:
                # 1. Check for duplicate name
                cursor.execute(
                    "SELECT id FROM business WHERE lower(name) = lower(%s) LIMIT 1",
                    (name.strip(),),
                )
                dup_row = cursor.fetchone()
                if dup_row:
                    raise ValueError(f"店家名稱 '{name}' 已被註冊")

                # 2. Upsert client from line_user_id to ensure it exists and get client_id
                if client_name:
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
                            name = EXCLUDED.name,
                            status = 'active',
                            updated_at = NOW()
                        RETURNING id
                        """,
                        (line_user_id, client_name),
                    )
                else:
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
                            status = 'active',
                            updated_at = NOW()
                        RETURNING id
                        """,
                        (line_user_id, line_user_id),
                    )
                client_row = cursor.fetchone()
                if not client_row:
                    raise DatabaseConfigurationError("Unable to register LINE client")

                client_id = int(client_row[0])


                # 3. Insert business
                cursor.execute(
                    """
                    INSERT INTO business (
                        client_id,
                        name,
                        branch_name,
                        industry,
                        address,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, 'active', NOW(), NOW())
                    RETURNING id
                    """,
                    (client_id, name.strip(), branch_name, industry, address),
                )
                new_biz_row = cursor.fetchone()
                if not new_biz_row:
                    raise DatabaseConfigurationError("無法新增店家資料")

                business_id = int(new_biz_row[0])

            conn.commit()
            return {
                "success": True,
                "business_id": business_id,
                "client_id": client_id,
                "name": name.strip(),
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
