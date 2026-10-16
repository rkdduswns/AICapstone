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

from client.url_values import read_url_rules
from client.window import MainWindow, display_label
from shared.activity import ActiveWindow, CurrentActivity, CurrentActivityResponse
from shared.browser import BrowserPage
from shared.clipboard import ClipboardEntry, RecordClipboard, RecordClipboardResponse
from shared.document import (
    MAX_DOCUMENT_CONTENT_LENGTH,
    DocumentContent,
    LocalDocument,
    RecordDocumentContent,
    RecordDocumentContentResponse,
)
from shared.privacy import PrivacyResponse, PrivacySettings, PrivacyState, RecordingStatus
from shared.protocol import HealthResponse, HealthStatus
from shared.records import ContextRecord, RecentRecords, RecentRecordsResponse
from shared.web_content import (
    MAX_WEB_CONTENT_LENGTH,
    RecordWebContent,
    RecordWebContentResponse,
    WebContent,
)


def main(clipboard: bool = False, browser: bool = False, web_content: bool = False,
         document_content: bool = False) -> int:
    """가상 설정·저장 본문 화면을 확인한다. 실제 브라우저나 로컬 파일은 읽지 않는다."""
    phase = 9 if document_content else 8 if web_content else 7 if browser else 6 if clipboard else 5
    parser = argparse.ArgumentParser(description=f"Phase {phase} Client 가상 미리보기")
    parser.add_argument("--snapshot", type=Path, help="선택 화면의 첫 결과를 저장하고 종료")
    parser.add_argument("--settings", action="store_true", help="개인정보 설정 탭으로 시작")
    if web_content:
        parser.add_argument("--web-state", default="ready",
                            choices=("ready", "empty", "truncated", "unsupported", "denied"),
                            help="가상 웹 본문의 정상/빈 결과/길이 제한/미지원/거부 상태")
    if document_content:
        parser.add_argument("--document-state", default="ready",
                            choices=("ready", "empty", "truncated", "unsupported", "denied", "gone"),
                            help="가상 문서의 정상/빈 결과/일부 저장/미지원/거부/출처 유실 상태")
        parser.add_argument("--file-type", default="pdf", choices=("pdf", "docx"),
                            help="표시할 가상 파일 유형")
    parser.add_argument("--reason", default="allowed", choices=(
        "allowed", "sensitive_content", "no_active_window", "unsupported", "error"),
        help="가상 판정 사유. 일시정지 및 chrome.exe 차단은 이 값보다 우선")
    args = parser.parse_args()
    settings = {"paused": False, "blocked_processes": [],
                "clipboard_enabled": False if clipboard else None,
                "blocked_urls": [] if browser else None}
    lock = threading.Lock()
    page = BrowserPage("chrome", "가상 페이지 — <b>원문 제목</b>",
                       "https://example.com/research?topic=sample#intro")
    document = (LocalDocument(r"C:\가상 자료\참고 문서." + args.file_type, args.file_type)
                if document_content else None)
    record_date = "2026-10-12" if document_content else "2026-10-08"

    class Handler(BaseHTTPRequestHandler):
        def privacy_response(self):
            """고정 가상 프로세스 chrome.exe에 대한 예시 상태만 반환한다."""
            reason = ("paused" if settings["paused"] else
                      "blocked_program" if "chrome.exe" in settings["blocked_processes"] else
                      args.reason)
            return PrivacyResponse(PrivacyState(
                PrivacySettings(settings["paused"], list(settings["blocked_processes"]),
                                settings["clipboard_enabled"], settings["blocked_urls"]),
                RecordingStatus(reason == "allowed", reason)))

        def do_GET(self):
            """저장 본문을 메모리의 가상 데이터로 제공하며 외부 페이지·파일에 접근하지 않는다."""
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
                    "sample-record", "가상 문서 앱" if document_content else "Google Chrome",
                    "sample.exe" if document_content else "chrome.exe",
                    "가상 문서 열람" if document_content else
                    "가상 웹 자료 조사" if web_content else "가상 클립보드 자료 조사",
                    f"{record_date}T10:00:00+09:00", f"{record_date}T10:20:00+09:00", 120000, 1,
                    page if browser and not document_content else None, document,
                )] if clipboard else []
                response = RecentRecordsResponse(RecentRecords(records))
            elif document_content and urlsplit(self.path).path == "/records/document-content":
                identifier = parse_qs(urlsplit(self.path).query).get("record_id", [""])[0]
                status = {"unsupported": 404, "denied": 403, "gone": 410}.get(args.document_state)
                if identifier != "sample-record" or status:
                    self.send_error(status or 404)
                    return
                text = ("가상 문서의 첫 페이지입니다. 실제 파일에서 추출하지 않았습니다.\n\n"
                        "<b>원문 태그도 일반 글자로 표시합니다.</b>\n\n"
                        "두 번째 페이지의 가상 내용입니다.\n파일 경로·유형·추출 시각을 확인합니다.")
                truncated = args.document_state == "truncated"
                if truncated:
                    text = ("가상 문서의 긴 문장입니다.\n" * 4000)[:MAX_DOCUMENT_CONTENT_LENGTH]
                content = (None if args.document_state == "empty" else DocumentContent(
                    document, "2026-10-12T10:10:00+09:00", text, truncated))
                response = RecordDocumentContentResponse(RecordDocumentContent(identifier, content))
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
            elif web_content and urlsplit(self.path).path == "/records/web-content":
                identifier = parse_qs(urlsplit(self.path).query).get("record_id", [""])[0]
                if identifier != "sample-record" or args.web_state == "unsupported":
                    self.send_error(404)
                    return
                if args.web_state == "denied":
                    self.send_error(403)
                    return
                text = ("가상 웹페이지 본문입니다. 실제 브라우저에서 수집하지 않았습니다.\n\n"
                        "<b>태그 형태의 내용도 일반 텍스트로 표시합니다.</b>\n"
                        "페이지 제목·URL·수집 시각과 연결된 저장 본문을 확인합니다.")
                truncated = args.web_state == "truncated"
                if truncated:
                    text = ("가상 페이지의 긴 문장입니다.\n" * 3000)[:MAX_WEB_CONTENT_LENGTH]
                content = (None if args.web_state == "empty" else
                           WebContent(page, "2026-10-08T10:10:00+09:00", text, truncated))
                response = RecordWebContentResponse(RecordWebContent(identifier, content))
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
                elif browser and self.path == "/privacy/blocked-urls":
                    if not isinstance(body, dict) or not isinstance(body.get("blocked_urls"), list):
                        raise ValueError("Invalid URL rules")
                    change = {"blocked_urls": read_url_rules(body["blocked_urls"])}
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
        "가상 설정 미리보기 · 실제 작업 정보는 수집하거나 저장하지 않습니다."
        + (" URL 차단 판정은 고정 예시입니다." if browser and not document_content else "")))
    show_records = clipboard and not args.settings
    show_clipboard = show_records and not browser
    show_document = show_records and document_content
    show_web = show_records and web_content and not show_document
    if show_records:
        window.tabs.setCurrentWidget(window.recent)
        if show_document:
            window.recent.detail_tabs.setCurrentWidget(window.recent.document_content)
        elif show_clipboard:
            window.recent.detail_tabs.setCurrentWidget(window.recent.clipboard)
        elif show_web:
            window.recent.detail_tabs.setCurrentWidget(window.recent.web_content)
    else:
        window.tabs.setCurrentWidget(window.privacy)
        if browser:
            window.privacy.rule_tabs.setCurrentWidget(window.privacy.urls)
    # 오류 화면도 캡처할 수 있도록 본문은 성공/실패 신호를 모두 기다린다.
    if show_document:
        snapshot_signals = (window.recent.document_content.client.content_received,
                            window.recent.document_content.client.content_failed)
    elif show_web:
        snapshot_signals = (window.recent.web_content.client.content_received,
                            window.recent.web_content.client.content_failed)
    else:
        snapshot_signals = (window.recent.clipboard.client.entries_received if show_clipboard
                            else window.recent.client.records_received if show_records
                            else window.privacy.client.state_received,)

    def save_snapshot():
        """첫 응답이 배치된 앱 위젯만 저장하고 서버를 종료한다."""
        saved = window.grab().save(str(args.snapshot), "PNG")
        app.exit(0 if saved else 1)

    def received(*_signal_args):
        """선택 화면의 첫 결과를 한 번만 캡처하고 다른 결과 신호는 연결 해제한다."""
        for signal in snapshot_signals:
            signal.disconnect(received)
        QTimer.singleShot(100, save_snapshot)

    if args.snapshot:
        for signal in snapshot_signals:
            signal.connect(received)
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
