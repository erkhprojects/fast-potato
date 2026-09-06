from __future__ import annotations

from unittest.mock import MagicMock, patch

from fast_potato import Schedule, supervisor


class TestSupervisorInit:
    def test_supervisor_initialization(self):
        sup = supervisor.ProcessSupervisor(
            app_str="examples.basic_usage:app",
            queues=["default", "high"],
            concurrency=5,
            processes=3,
            log_level="WARNING",
        )
        assert sup.app_str == "examples.basic_usage:app"
        assert sup.queues == ["default", "high"]
        assert sup.concurrency == 5
        assert sup.processes == 3
        assert sup.log_level == "WARNING"


class TestSupervisorProcessSpawning:
    def test_supervisor_spawns_only_workers_when_no_schedules(self):
        sup = supervisor.ProcessSupervisor(
            app_str="examples.basic_usage:app",
            queues=["default"],
            concurrency=5,
            processes=2,
        )

        mock_process = MagicMock()
        mock_process.name = "mock_p"
        mock_process.pid = 9999
        mock_process.is_alive.return_value = False

        with patch.object(sup._ctx, "Process", return_value=mock_process) as mock_p_cls:
            sup.start()

            # 2 worker processes spawned, 0 scheduler
            assert mock_p_cls.call_count == 2
            worker_names = [call[1]["name"] for call in mock_p_cls.call_args_list]
            assert "fast_potato-scheduler" not in worker_names

    def test_supervisor_spawns_one_scheduler_when_schedules_present(self):
        mock_app = MagicMock()
        mock_app.schedules = [Schedule(task="my_app.task", cron="* * * * *")]

        sup = supervisor.ProcessSupervisor(
            app_str="examples.basic_usage:app",
            queues=["default"],
            concurrency=5,
            processes=2,
        )

        mock_process = MagicMock()
        mock_process.name = "mock_p"
        mock_process.pid = 9999
        mock_process.is_alive.return_value = False

        with patch("fast_potato.worker.import_app", return_value=mock_app):
            with patch.object(
                sup._ctx, "Process", return_value=mock_process
            ) as mock_p_cls:
                sup.start()

                # 2 workers + 1 scheduler = 3 processes spawned!
                assert mock_p_cls.call_count == 3
                names = [call[1]["name"] for call in mock_p_cls.call_args_list]
                assert "fast_potato-scheduler" in names
                assert "fast_potato-worker-1" in names
                assert "fast_potato-worker-2" in names

    def test_supervisor_terminates_all_processes_on_stop(self):
        sup = supervisor.ProcessSupervisor(
            app_str="examples.basic_usage:app",
            queues=["default"],
            processes=2,
        )
        p1 = MagicMock()
        p1.pid = 1001
        p1.is_alive.side_effect = [True, False]

        p2 = MagicMock()
        p2.pid = 1002
        p2.is_alive.side_effect = [True, False]

        sup._workers = [p1, p2]

        with patch("os.kill") as mock_kill:
            sup.stop()
            assert sup._stopping is True
            assert mock_kill.call_count == 2

        sup._cleanup()
        p1.join.assert_called_once_with(timeout=3.0)
        p2.join.assert_called_once_with(timeout=3.0)
