"""Run with python -m backend [--port 8765]."""

import argparse
import socket
import sys
from pathlib import Path

from shared.protocol import DEFAULT_PORT


def port_number(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer from 1 to 65535") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be an integer from 1 to 65535")
    return port


def main() -> None:
    """같은 loopback API를 실행하며 필요하면 검증용 DB 경로를 명시적으로 받는다."""
    parser = argparse.ArgumentParser(description="강써치 로컬 Backend")
    parser.add_argument("--port", type=port_number, default=DEFAULT_PORT)
    parser.add_argument("--db-path", type=Path,
                        help="사용할 SQLite 파일 경로. 생략하면 사용자 데이터 폴더를 사용합니다.")
    parser.add_argument("--check-embedding", action="store_true", help="배포 E5 실제 CPU 추론 점검")
    parser.add_argument("--backend-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--owner-pid", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--stop-event", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.backend_worker:
        from desktop.backend_worker import run_worker
        if not args.stop_event:
            parser.error("missing worker control")
        raise SystemExit(run_worker(args.port, args.db_path, args.owner_pid, args.stop_event))
    if args.check_embedding:
        from backend.embedding import EmbeddingService

        service = EmbeddingService()
        sample = "오늘의 회의 자료를 문서로 저장했습니다."
        chunks = service.split_passage(sample)
        query = service.embed_query(sample)
        relevant, other = service.embed_passages([chunks[0], "바나나 우유와 아이스크림 레시피"])
        if len(query) != 384 or sum(a*b for a, b in zip(query, relevant)) <= sum(a*b for a, b in zip(query, other)):
            raise RuntimeError("E5 embedding smoke check failed")
        print("E5 CPU OK: 384")
        return
    # 다른 인스턴스가 사용 중이면 DB나 수집기를 열기 전에 종료한다.
    with socket.socket() as listener:
        if sys.platform == "win32":
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            # POSIX에서는 종료 직후 TIME_WAIT가 남아도 같은 포트로 다시 시작할 수 있다.
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind(("127.0.0.1", args.port))
            listener.listen()
        except OSError:
            parser.exit(2, "포트를 사용할 수 없습니다 (bind). 기존 강써치 또는 포트 점유를 확인해 주세요.\n")
        import uvicorn

        from backend.activity_store import ActivityStore
        from backend.app import create_app

        store = ActivityStore(args.db_path) if args.db_path is not None else None
        server = uvicorn.Server(uvicorn.Config(create_app(activity_store=store),
                                host="127.0.0.1", port=args.port, access_log=False))
        server.run(sockets=[listener])
        if not server.started:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
