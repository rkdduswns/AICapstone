"""검색 중심 창에서 Client를 실행하고 선택적으로 실제 Backend 연결을 진단한다."""

import argparse
import json
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from client.application_window import ApplicationWindow
from client.view_preferences import ViewPreferences
from shared.protocol import DEFAULT_PORT


def main() -> int:
    """일반 실행은 창을 유지하며 진단 실행만 실제 연결 결과를 쓰고 자동 종료한다."""
    parser = argparse.ArgumentParser(description="강써치 데스크톱 클라이언트")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--smoke-test-result", type=Path,
                        help="실제 창·Backend 연결 진단 결과를 JSON으로 쓰고 종료합니다.")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be an integer from 1 to 65535")
    app = QApplication([sys.argv[0]])
    app.setApplicationName("강써치")
    app.setApplicationDisplayName("강써치")
    # 자동 진단은 사용자의 표시 설정을 읽거나 덮어쓰지 않는다.
    preferences = None if args.smoke_test_result is not None else ViewPreferences()
    window = ApplicationWindow(args.port, preferences=preferences)
    window.show()
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
            try:
                args.smoke_test_result.write_text(json.dumps(result), encoding="utf-8")
                exit_code = 0 if result["ok"] else 1
            except OSError:
                exit_code = 2
            window.close()
            app.exit(exit_code)

        window.management.backend.connection_changed.connect(finish)
        # 창이 표시되고 이벤트 루프가 시작된 뒤 요청한다. 일반 실행에는 자동 종료를 적용하지 않는다.
        QTimer.singleShot(10000, lambda: finish(False))
    # 일반 실행과 진단 실행 모두 같은 읽기 전용 연결 확인을 한 번 예약한다.
    QTimer.singleShot(0, window.management.check)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
