"""단일 배포 EXE의 별도 프로세스 역할로 기존 Backend를 조합하고 정상 종료한다."""

import os
import socket
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

from desktop.windows_control import WorkerLifetime


@contextmanager
def _worker_streams():
    """windowed EXE의 None 표준 출력을 제삼자 모듈 import 전에 안전한 버림 스트림으로 바꾼다."""
    previous, opened = {}, []
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            previous[name] = None
            stream = open(os.devnull, "w", encoding="utf-8")
            setattr(sys, name, stream)
            opened.append(stream)
    try:
        yield
    finally:
        for name, stream in previous.items():
            setattr(sys, name, stream)
        for stream in opened:
            stream.close()


def run_worker(port: int, db_path: Path | None, owner_pid: int, stop_event: str) -> int:
    """종료 권한을 확인하고 포트를 선점한 후에만 기존 HTTP 서버와 저장소를 시작한다."""
    if (type(port) is not int or not 1 <= port <= 65535
            or type(owner_pid) is not int or not 1 <= owner_pid <= 0xFFFFFFFF):
        return 3
    stop_requested = threading.Event()
    server = None
    lifetime = None
    publisher = None
    publishing_done = threading.Event()

    def request_stop() -> None:
        """정상 종료 요청은 Uvicorn lifespan을 통해 마지막 작업을 저장하도록 전달한다."""
        stop_requested.set()
        if server is not None:
            server.should_exit = True

    try:
        lifetime = WorkerLifetime(owner_pid, stop_event, request_stop)
        lifetime.start()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            if sys.platform == "win32":
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                listener.bind(("127.0.0.1", port))
            except OSError:
                return 2
            if stop_requested.is_set():
                return 0
            with _worker_streams():
                # 실행 조합 책임은 desktop에 두며 Client가 Backend 내부를 import하지 않는다.
                import uvicorn

                from backend.activity_store import ActivityStore
                from backend.app import create_app

                if stop_requested.is_set():
                    return 0
                store = ActivityStore(db_path) if db_path is not None else None
                app = create_app(activity_store=store)
                config = uvicorn.Config(
                    app, host="127.0.0.1", port=port, access_log=False, log_config=None,
                    use_colors=False, lifespan="on", loop="asyncio", timeout_graceful_shutdown=3,
                )
                server = uvicorn.Server(config)
                if stop_requested.is_set():
                    return 0

                def publish_ready() -> None:
                    """실제 본인 서버 시작 뒤에만 준비 신호를 보내 외부 health와 혼동하지 않는다."""
                    while not publishing_done.wait(0.02):
                        if server.started:
                            lifetime.mark_ready()
                            return

                publisher = threading.Thread(target=publish_ready, name="gangsearch-ready", daemon=True)
                publisher.start()
                server.run(sockets=[listener])
                return 0 if server.started else 3
    except Exception:
        # 내부 경로·본문을 UI나 표준 출력에 노출하지 않고 부모에게 시작 실패를 반환한다.
        return 3
    finally:
        # 준비 신호가 종료 후 늦게 다시 켜지지 않도록 게시 스레드를 먼저 완료한다.
        publishing_done.set()
        if publisher is not None:
            publisher.join(timeout=1.0)
        if lifetime is not None:
            lifetime.close()
