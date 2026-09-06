from __future__ import annotations

import shutil
import subprocess
import sys
from unittest.mock import patch

import pytest

from fast_potato import FastPotato, worker
from fast_potato import __main__ as cli


class TestImportApp:
    def test_import_with_module_and_attr(self) -> None:
        app = worker.import_app("examples.basic_usage:app")
        assert isinstance(app, FastPotato)
        assert app.name == "my_app"

    def test_import_with_module_only(self) -> None:
        app = worker.import_app("examples.basic_usage")
        assert isinstance(app, FastPotato)
        assert app.name == "my_app"

    def test_import_nonexistent_module_raises(self) -> None:
        with pytest.raises(ImportError, match="Could not import module"):
            worker.import_app("nonexistent_module_xyz:app")

    def test_import_nonexistent_attr_raises(self) -> None:
        with pytest.raises(AttributeError, match="has no attribute"):
            worker.import_app("examples.basic_usage:does_not_exist")

    def test_import_non_fastpotato_object_raises(self) -> None:
        with pytest.raises(TypeError, match="expected a FastPotato instance"):
            worker.import_app("examples.basic_usage:User")


class TestCLIParser:
    def test_default_arguments(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["-A", "my_module:app"])
        assert args.app == "my_module:app"
        assert args.processes == 1
        assert args.concurrency == 10
        assert args.queues == "default"
        assert args.log_level == "INFO"

    def test_custom_arguments(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(
            [
                "-A",
                "my_module:app",
                "-w",
                "4",
                "-c",
                "25",
                "-q",
                "urgent,default,low",
                "--log-level",
                "DEBUG",
            ]
        )
        assert args.app == "my_module:app"
        assert args.processes == 4
        assert args.concurrency == 25
        assert args.queues == "urgent,default,low"
        assert args.log_level == "DEBUG"

    def test_missing_app_raises(self) -> None:
        parser = cli.build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args([])
        assert exc_info.value.code == 2

    def test_help_stdout(self) -> None:
        parser = cli.build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0


class TestCLIMain:
    def test_cli_main_wires_supervisor_correctly(self) -> None:
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


class TestCLIBinary:
    def test_binary_entry_point_subprocess(self) -> None:
        cmd = shutil.which("fast-potato")
        if cmd is None:
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
