from __future__ import annotations

import argparse

from fast_potato import supervisor


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="fast-potato",
        description="FastPotato: Async-first distributed task queue for Python.",
    )
    parser.add_argument(
        "-A",
        "--app",
        required=True,
        help="Application import path (e.g. 'my_module:app').",
    )
    parser.add_argument(
        "-w",
        "--processes",
        type=int,
        default=1,
        help="Number of worker OS processes to spawn (default: 1).",
    )
    parser.add_argument(
        "-c",
        "--concurrency",
        type=int,
        default=10,
        help="Maximum concurrent async tasks per worker process (default: 10).",
    )
    parser.add_argument(
        "-q",
        "--queues",
        type=str,
        default="default",
        help="Comma-separated queue names to listen to (default: 'default').",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO).",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for fast-potato."""
    parser = build_parser()
    args = parser.parse_args(argv)
    queues = [q.strip() for q in args.queues.split(",") if q.strip()]

    proc_supervisor = supervisor.ProcessSupervisor(
        app_str=args.app,
        queues=queues,
        concurrency=args.concurrency,
        processes=args.processes,
        log_level=args.log_level,
    )
    proc_supervisor.start()


if __name__ == "__main__":
    main()
