from __future__ import annotations

import pytest

from fast_potato import FastPotato, worker
from fast_potato import __main__ as cli


class TestImportApp:
    def test_import_with_module_and_attr(self):
        app = worker.import_app("examples.basic_usage:app")
        assert isinstance(app, FastPotato)
        assert app.name == "my_app"

    def test_import_with_module_only(self):
        app = worker.import_app("examples.basic_usage")
        assert isinstance(app, FastPotato)
        assert app.name == "my_app"

    def test_import_nonexistent_module_raises(self):
        with pytest.raises(ImportError, match="Could not import module"):
            worker.import_app("nonexistent_module_xyz:app")

    def test_import_nonexistent_attr_raises(self):
        with pytest.raises(AttributeError, match="has no attribute"):
            worker.import_app("examples.basic_usage:does_not_exist")

    def test_import_non_fastpotato_object_raises(self):
        with pytest.raises(TypeError, match="expected a FastPotato instance"):
            worker.import_app("examples.basic_usage:User")


class TestCLIParser:
    def test_default_arguments(self):
        parser = cli.build_parser()
        args = parser.parse_args(["-A", "my_module:app"])
        assert args.app == "my_module:app"
        assert args.processes == 1
        assert args.concurrency == 10
        assert args.queues == "default"
        assert args.log_level == "INFO"

    def test_custom_arguments(self):
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

    def test_missing_app_raises(self):
        parser = cli.build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])
