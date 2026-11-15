"""강써치 단일 EXE의 UI와 내부 Backend 작업 역할을 실행한다."""

import argparse
import sys
from pathlib import Path

from shared.protocol import DEFAULT_PORT


def main(argv: list[str] | None = None) -> int:
    """서버 역할을 Qt import 전에 구분하고 일반 실행은 기존 Client 화면을 사용한다."""
    parser = argparse.ArgumentParser(description="강써치")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--db-path", type=Path)
    parser.add_argument("--smoke-test-result", type=Path)
    parser.add_argument("--smoke-test-reading", action="store_true")
    parser.add_argument("--smoke-test-hold-ms", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--backend-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--owner-pid", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--stop-event", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be an integer from 1 to 65535")
    if args.backend_worker:
        if (args.owner_pid is None or not 1 <= args.owner_pid <= 0xFFFFFFFF or not args.stop_event
                or args.smoke_test_result is not None or args.smoke_test_reading
                or args.smoke_test_hold_ms):
            parser.error("invalid internal worker arguments")
        from desktop.backend_worker import run_worker

        return run_worker(args.port, args.db_path, args.owner_pid, args.stop_event)
    if args.owner_pid is not None or args.stop_event is not None:
        parser.error("worker arguments require internal worker mode")
    if args.smoke_test_reading and args.smoke_test_result is None:
        parser.error("--smoke-test-reading requires --smoke-test-result")
    if not 0 <= args.smoke_test_hold_ms <= 60_000 or (
            args.smoke_test_hold_ms and args.smoke_test_result is None):
        parser.error("invalid diagnostic hold")

    from client.__main__ import main as client_main
    from desktop.launcher import BackendSupervisor

    db_path = args.db_path.resolve() if args.db_path is not None else None

    def start_services(window) -> None:
        """창을 먼저 표시한 뒤 소유 서버의 준비 상태를 비동기로 확인한다."""
        supervisor = BackendSupervisor(window, args.port, db_path)
        window._desktop_backend = supervisor
        supervisor.start()

    client_arguments = [sys.argv[0], "--port", str(args.port)]
    if args.smoke_test_result is not None:
        client_arguments += ["--smoke-test-result", str(args.smoke_test_result)]
    if args.smoke_test_reading:
        client_arguments.append("--smoke-test-reading")
    if args.smoke_test_hold_ms:
        client_arguments += ["--smoke-test-hold-ms", str(args.smoke_test_hold_ms)]
    original_arguments = sys.argv
    try:
        sys.argv = client_arguments
        return client_main(startup_hook=start_services)
    finally:
        sys.argv = original_arguments


if __name__ == "__main__":
    raise SystemExit(main())
