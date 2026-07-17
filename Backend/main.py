"""Compatibility module for deployments that still run ``uvicorn main:app``.

The canonical integration API lives in :mod:`api.main`. Keeping this file as a
thin import prevents the old background crawler pipeline from overriding the
requested business name.
"""

from __future__ import annotations

import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from api.main import app  # noqa: E402,F401
