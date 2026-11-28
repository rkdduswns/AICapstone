"""검색 중심 창에서 Client를 실행하고 선택적으로 실제 Backend 연결을 진단한다."""

import argparse
import json
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from client.application_window import ApplicationWindow
from shared.protocol import DEFAULT_PORT


def main() -> int:
    """일반 실행은 창을 유지하며 진단 실행만 실제 연결 결과를 쓰고 자동 종료한다."""
    parser = argparse.ArgumentParser(description="강써치 데스크톱 클라이언트")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--smoke-test-result", type=Path,
                        help="실제 창·Backend 연결 진단 결과를 JSON으로 쓰고 종료합니다.")
    parser.add_argument("--smoke-owned-db", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.smoke_owned_db and (args.smoke_test_result is None or sys.platform != "win32"):
        parser.error("--smoke-owned-db requires Windows and --smoke-test-result")
    if not 1 <= args.port <= 65535:
        parser.error("port must be an integer from 1 to 65535")
    app = QApplication([sys.argv[0]])
    app.setApplicationName("강써치")
    app.setApplicationDisplayName("강써치")
    window = ApplicationWindow(args.port)
    window.show()
    supervisor = None
    if args.smoke_test_result is None:
        window.enable_background()
    if sys.platform == "win32" and (args.smoke_test_result is None or args.smoke_owned_db):
        from desktop.launcher import BackendSupervisor
        supervisor = BackendSupervisor(window, args.port, args.smoke_owned_db)
        QTimer.singleShot(0, supervisor.start)
    if args.smoke_test_result is not None:
        completed = False

        def finish(connected: bool) -> None:
            """기존 QtNetwork 연결 신호를 사용해 frozen 실행에서도 같은 화면/API 경로를 검증한다."""
            nonlocal completed
            if completed:
                return
            completed = True
            result = {"ok": connected and window.isVisible(),
                      "frozen": bool(getattr(sys, "frozen", False)),
                      "platform": app.platformName()}
            if supervisor is not None:
                owned = supervisor.state == "ready_owned"
                supervisor.stop()
                result["owned_backend_stopped"] = owned and supervisor.shutdown_clean
                result["ok"] = result["ok"] and result["owned_backend_stopped"]
            try:
                args.smoke_test_result.write_text(json.dumps(result), encoding="utf-8")
                exit_code = 0 if result["ok"] else 1
            except OSError:
                exit_code = 2
            window.close()
            app.exit(exit_code)

        window.management.backend.connection_changed.connect(finish)
        # 창이 표시되고 이벤트 루프가 시작된 뒤 요청한다. 일반 실행에는 자동 종료를 적용하지 않는다.
        if supervisor is None:
            QTimer.singleShot(0, window.management.check)
        QTimer.singleShot(90000 if supervisor else 10000, lambda: finish(False))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
