"""실제 수집 없이 가상 창 전환으로 Phase 2 Client를 미리 확인하는 개발 도구."""

import argparse
import json
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from client.window import MainWindow, display_label
from shared.activity import ACTIVITY_PATH, ActiveWindow, CurrentActivity, CurrentActivityResponse
from shared.protocol import HealthResponse, HealthStatus

SAMPLES = (
    CurrentActivity("collecting", ActiveWindow(
        "Google Chrome", "chrome.exe", 1234, "가상 자료 — ContextTrace 소개")),
    CurrentActivity("collecting", ActiveWindow(
        "Visual Studio Code", "Code.exe", 2345, "가상 작업.py — Visual Studio Code")),
    CurrentActivity("collecting", ActiveWindow(
        "Microsoft Word", "WINWORD.EXE", 3456, "가상 보고서.docx — Word")),
    CurrentActivity("collecting", ActiveWindow(
        "Windows Explorer", "explorer.exe", 4567, "가상 프로젝트 폴더")),
    CurrentActivity("no_active_window", None),
    CurrentActivity("unsupported", None),
    CurrentActivity("error", None),
)


@contextmanager
def preview_server():
    """운영 Backend와 충돌하지 않는 임시 loopback 포트에서 가상 응답만 제공한다."""
    started = time.monotonic()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            """4초마다 예시를 바꾸되 클라이언트의 실제 HTTP 경로를 사용한다."""
            if self.path == "/health":
                response = HealthResponse(HealthStatus(version="preview"))
            elif self.path == ACTIVITY_PATH:
                index = int((time.monotonic() - started) / 4) % len(SAMPLES)
                response = CurrentActivityResponse(SAMPLES[index])
            else:
                self.send_error(404)
                return
            payload = json.dumps(asdict(response), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return  # 미리보기 창을 닫으면 진행 중 요청이 취소될 수 있다.

        def log_message(self, *args):
            """개발용 가상 데이터라도 반복 요청 로그를 남기지 않는다."""
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def main() -> int:
    """미리보기 또는 가상 데이터 화면 이미지 저장을 실행하고 서버를 함께 종료한다."""
    parser = argparse.ArgumentParser(description="Phase 2 Client 가상 데이터 미리보기")
    parser.add_argument("--snapshot", type=Path, help="화면을 PNG로 저장한 뒤 종료")
    args = parser.parse_args()
    app = QApplication([sys.argv[0]])
    with preview_server() as port:
        window = MainWindow(port)
        window.setWindowTitle("ContextTrace — Phase 2 미리보기 (가상 데이터)")
        window.layout().insertWidget(0, display_label(
            "가상 데이터 미리보기 · 4초마다 예시 전환 · 실제 작업 정보는 수집하지 않습니다."))
        if args.snapshot:
            def save_snapshot():
                """첫 응답을 화면에 배치한 뒤 이 앱의 위젯만 렌더링한다."""
                saved = window.grab().save(str(args.snapshot), "PNG")
                window.close()
                app.exit(0 if saved else 1)

            def received(activity):
                """연속 응답으로 여러 저장 작업이 예약되지 않도록 첫 신호만 사용한다."""
                window.activity.activity_received.disconnect(received)
                QTimer.singleShot(100, save_snapshot)

            window.activity.activity_received.connect(received)
            QTimer.singleShot(5000, lambda: app.exit(1))
        window.show()
        window.check()
        try:
            return app.exec()
        finally:
            window.close()


if __name__ == "__main__":
    sys.exit(main())
