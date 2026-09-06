from __future__ import annotations

import shutil
import subprocess
import sys
from unittest.mock import patch

import pytest

from fast_potato import __main__ as cli


def test_cli_help_stdout() -> None:
    """Verify that the entry point parser provides standard CLI documentation."""
    parser = cli.build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--help"])
    assert exc_info.value.code == 0


def test_cli_missing_required_app() -> None:
    """Verify that omitting -A / --app raises exit code 2."""
    parser = cli.build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args([])
    assert exc_info.value.code == 2


def test_cli_main_wires_supervisor_correctly() -> None:
    """Verify that main() parses arguments and initializes ProcessSupervisor with exact values."""
    with patch("fast_potato.supervisor.ProcessSupervisor") as mock_sup_cls:
        mock_sup = mock_sup_cls.return_value
        cli.main(
            [
                "-A",
                "examples.basic_usage:app",
                "-w",
                "3",
                "-c",
                "15",
                "-q",
                "default,urgent",
                "--log-level",
                "DEBUG",
            ]
        )
        mock_sup_cls.assert_called_once_with(
            app_str="examples.basic_usage:app",
            queues=["default", "urgent"],
            concurrency=15,
            processes=3,
            log_level="DEBUG",
        )
        mock_sup.start.assert_called_once()


def test_binary_entry_point_subprocess() -> None:
    """Verify that the installed 'fast-potato' binary entry point executes as a real OS process."""
    cmd = shutil.which("fast-potato")
    if cmd is None:
        # Run via python -m fast_potato
        result = subprocess.run(
            [sys.executable, "-m", "fast_potato", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
    else:
        result = subprocess.run(
            [cmd, "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

    assert result.returncode == 0
    assert "FastPotato" in result.stdout
    assert "--app APP" in result.stdout
    assert "-A" in result.stdout
    assert "--processes" in result.stdout
    assert "--concurrency" in result.stdout
