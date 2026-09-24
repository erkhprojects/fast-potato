from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CONTRACT = Path(__file__).parent / "typecheck" / "send_typing.py"


def test_send_typing_contract():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--warn-unused-ignores",
            "--no-incremental",
            str(CONTRACT),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
