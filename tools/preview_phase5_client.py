"""개인정보 제어와 복사 상세의 가상 미리보기. 실제 감지·필터·파일 저장은 하지 않는다."""

import argparse
import json
import sys
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from client.window import MainWindow, display_label
from shared.activity import ActiveWindow, CurrentActivity, CurrentActivityResponse
from shared.clipboard import ClipboardEntry, RecordClipboard, RecordClipboardResponse
from shared.privacy import PrivacyResponse, PrivacySettings, PrivacyState, RecordingStatus
from shared.protocol import HealthResponse, HealthStatus
from shared.records import ContextRecord, RecentRecords, RecentRecordsResponse


def main(clipboard: bool = False) -> int:
    """메모리의 가상 설정을 바꾸며 일시정지와 목록 적용 화면을 확인한다."""
    phase = 6 if clipboard else 5
    parser = argparse.ArgumentParser(description=f"Phase {phase} Client 가상 미리보기")
    parser.add_argument("--snapshot", type=Path, help="선택 화면의 첫 정상 응답을 저장하고 종료")
    parser.add_argument("--settings", action="store_true", help="개인정보 설정 탭으로 시작")
    parser.add_argument("--reason", default="allowed", choices=(
        "allowed", "sensitive_content", "no_active_window", "unsupported", "error"),
        help="가상 판정 사유. 일시정지 및 chrome.exe 차단은 이 값보다 우선")
    args = parser.parse_args()
    settings = {"paused": False, "blocked_processes": [],
                "clipboard_enabled": False if clipboard else None}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def privacy_response(self):
            """고정 가상 프로세스 chrome.exe에 대한 예시 상태만 반환한다."""
            reason = ("paused" if settings["paused"] else
                      "blocked_program" if "chrome.exe" in settings["blocked_processes"] else
                      args.reason)
            return PrivacyResponse(PrivacyState(
                PrivacySettings(settings["paused"], list(settings["blocked_processes"]),
                                settings["clipboard_enabled"]),
                RecordingStatus(reason == "allowed", reason)))

        def do_GET(self):
            """기존 화면도 사용할 수 있도록 가상의 상태/현재 창/빈 기록을 제공한다."""
            if self.path == "/privacy":
                with lock:
                    response = self.privacy_response()
            elif self.path == "/health":
                response = HealthResponse(HealthStatus("privacy-preview"))
            elif self.path == "/activity/current":
                response = CurrentActivityResponse(CurrentActivity("collecting", ActiveWindow(
                    "Google Chrome", "chrome.exe", 1234, "가상 자료 — 개인정보 설정 확인")))
            elif self.path == "/records/recent?limit=20":
                records = [ContextRecord(
                    "sample-record", "Google Chrome", "chrome.exe", "가상 클립보드 자료 조사",
                    "2026-10-08T10:00:00+09:00", "2026-10-08T10:20:00+09:00", 120000, 1,
                )] if clipboard else []
                response = RecentRecordsResponse(RecentRecords(records))
            elif clipboard and urlsplit(self.path).path == "/records/clipboard":
                identifier = parse_qs(urlsplit(self.path).query).get("record_id", [""])[0]
                if identifier != "sample-record":
                    self.send_error(404)
                    return
                response = RecordClipboardResponse(RecordClipboard(identifier, [
                    ClipboardEntry("copy-1", "2026-10-08T10:05:00+09:00", "가상 참고 문장입니다."),
                    ClipboardEntry("copy-2", "2026-10-08T10:10:00+09:00",
                                   "가상 복사 텍스트\n이 내용은 실제 클립보드에서 읽은 정보가 아닙니다.\n"
                                   "<b>일반 텍스트 그대로 표시합니다.</b>"),
                ], False))
            else:
                self.send_error(404)
                return
            self.send_json(response)

        def do_PUT(self):
            """Client가 보낸 개별 목표값을 메모리에만 적용한다. 실제 Backend 구현이 아니다."""
            if (self.headers.get("X-ContextTrace-Client") != "desktop"
                    or self.headers.get("Content-Type") != "application/json"):
                self.send_error(400)
                return
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                if self.path == "/privacy/paused":
                    if not isinstance(body, dict) or type(body.get("paused")) is not bool:
                        raise ValueError("Invalid paused setting")
                    change = {"paused": body["paused"]}
                elif self.path == "/privacy/blocked-processes":
                    if (not isinstance(body, dict) or not isinstance(body.get("blocked_processes"), list)
                            or not all(isinstance(name, str) for name in body["blocked_processes"])):
                        raise ValueError("Invalid list")
                    change = {"blocked_processes": body["blocked_processes"]}
                elif clipboard and self.path == "/privacy/clipboard":
                    if not isinstance(body, dict) or type(body.get("clipboard_enabled")) is not bool:
                        raise ValueError("Invalid clipboard setting")
                    change = {"clipboard_enabled": body["clipboard_enabled"]}
                else:
                    self.send_error(404)
                    return
            except (ValueError, UnicodeDecodeError):
                self.send_error(422)
                return
            with lock:
                settings.update(change)
                response = self.privacy_response()
            self.send_json(response)

        def send_json(self, response):
            """가상 값만 직렬화하며 창 종료로 취소된 전송을 정리한다."""
            payload = json.dumps(asdict(response), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return  # Client 창 종료에 따른 요청 취소다.

        def log_message(self, *args):
            """가상 입력도 로그에 저장하지 않는다."""
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    app = QApplication([sys.argv[0]])
    window = MainWindow(server.server_port)
    window.setWindowTitle(f"ContextTrace — Phase {phase} 미리보기 (가상 데이터)")
    window.layout().insertWidget(0, display_label(
        "가상 설정 미리보기 · 실제 작업 정보는 수집하거나 저장하지 않습니다."))
    show_clipboard = clipboard and not args.settings
    if show_clipboard:
        window.tabs.setCurrentWidget(window.recent)
        window.recent.detail_tabs.setCurrentWidget(window.recent.clipboard)
    else:
        window.tabs.setCurrentWidget(window.privacy)
    received_signal = (window.recent.clipboard.client.entries_received if show_clipboard
                       else window.privacy.client.state_received)

    def save_snapshot():
        """첫 응답이 배치된 앱 위젯만 저장하고 서버를 종료한다."""
        saved = window.grab().save(str(args.snapshot), "PNG")
        app.exit(0 if saved else 1)

    def received(*args):
        """선택 화면의 정상 응답을 한 번만 캡처한다."""
        received_signal.disconnect(received)
        QTimer.singleShot(100, save_snapshot)

    if args.snapshot:
        received_signal.connect(received)
        QTimer.singleShot(5000, lambda: app.exit(1))
    window.show()
    window.check()
    try:
        return app.exec()
    finally:
        window.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    sys.exit(main())
