from __future__ import annotations

import os


STAGING_LINE_ALLOWLIST_ENV = "BI_RMP_LINE_ALLOWED_USER_IDS"
PUBLIC_STAGING_BLOCKED_MESSAGE = (
    "This staging environment is limited to configured test users."
)


class StagingLineUserNotAllowedError(PermissionError):
    """Raised when a LINE user is outside the staging test allowlist."""


def staging_line_user_allowlist() -> set[str]:
    raw_value = os.getenv(STAGING_LINE_ALLOWLIST_ENV, "")
    return {item.strip() for item in raw_value.split(",") if item.strip()}


def is_line_user_allowed_for_staging(line_user_id: str | None) -> bool:
    if os.getenv("APP_ENV", "").strip().lower() != "staging":
        return True

    allowed_user_ids = staging_line_user_allowlist()
    if not allowed_user_ids:
        return True

    return bool(line_user_id and line_user_id.strip() in allowed_user_ids)


def enforce_staging_line_user_allowed(line_user_id: str | None) -> None:
    if not is_line_user_allowed_for_staging(line_user_id):
        raise StagingLineUserNotAllowedError(PUBLIC_STAGING_BLOCKED_MESSAGE)
