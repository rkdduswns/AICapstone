"""Run with python -m backend [--port 8765]."""

import argparse
from pathlib import Path

import uvicorn

from backend.activity_store import ActivityStore
from backend.app import create_app
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
    args = parser.parse_args()
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
    # Uvicorn logs startup/shutdown and exits nonzero on a bind failure.
    store = ActivityStore(args.db_path) if args.db_path is not None else None
    uvicorn.run(create_app(activity_store=store), host="127.0.0.1", port=args.port,
                access_log=False)


if __name__ == "__main__":
    main()
