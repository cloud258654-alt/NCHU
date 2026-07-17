from __future__ import annotations
import os
from typing import Any, Callable
from pydantic import BaseModel, Field

try:
    import psycopg2
    from psycopg2.extras import Json
except ModuleNotFoundError:
    psycopg2 = None
    class Json:
        def __init__(self, val):
            self.value = val

from api.reputation import DatabaseConfigurationError

class MessageLogRequest(BaseModel):
    line_user_id: str = Field(min_length=1, max_length=255)
    message_text: str | None = None
    direction: str = Field(default="incoming")  # 'incoming' or 'outgoing'
    intent: str | None = None
    session_state: dict | None = None

class ClientMessagesLogRepository:
    def __init__(self, connection_factory: Callable[[], Any] | None = None) -> None:
        self._connection_factory = connection_factory or self._default_connection

    @staticmethod
    def _default_connection():
        if psycopg2 is None:
            raise DatabaseConfigurationError("psycopg2 is required for logging messages")
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            raise DatabaseConfigurationError("DATABASE_URL is required for logging messages")
        return psycopg2.connect(database_url, connect_timeout=10)

    def log_message(self, line_user_id: str, message_text: str | None, direction: str, intent: str | None, session_state: dict | None) -> dict[str, object]:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cur:
                # 1. Resolve client_id if client exists
                cur.execute("SELECT id FROM clients WHERE line_user_id = %s LIMIT 1", (line_user_id,))
                row = cur.fetchone()
                client_id = int(row[0]) if row else None

                # 2. Insert message log
                cur.execute(
                    """
                    INSERT INTO client_messages_log (
                        client_id, line_user_id, message_text, direction, intent, session_state, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, NOW()
                    ) RETURNING id
                    """,
                    (client_id, line_user_id, message_text, direction, intent, Json(session_state or {}))
                )
                log_id = cur.fetchone()[0]
            conn.commit()
            return {"logged": True, "id": log_id, "client_id": client_id}
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
