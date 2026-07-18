from __future__ import annotations

import subprocess
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]


def test_frontend_behavior_contract() -> None:
    result = subprocess.run(
        ["node", str(APP_ROOT / "tests" / "frontend_behavior.test.js")],
        cwd=APP_ROOT.parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
