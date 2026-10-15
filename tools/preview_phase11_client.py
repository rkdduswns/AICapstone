"""조건 검색의 가상 HTTP 미리보기. 실제 파일·브라우저·작업 저장소를 읽지 않는다."""

import argparse
import json
import sys
import threading
from dataclasses import asdict
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from client.search_client import read_search_request
from client.time_values import parse_timestamp
from client.window import MainWindow, display_label
from shared.browser import BrowserPage
from shared.document import LocalDocument
from shared.protocol import HealthResponse, HealthStatus
from shared.records import ContextRecord
from shared.search import SearchRequest, SearchResponse, SearchResults


def sample_records() -> list[ContextRecord]:
    """현재 날짜 기준의 가상 출처만 만들어 날짜 프리셋을 직접 확인할 수 있게 한다."""
    now = datetime.now().astimezone().replace(microsecond=0)
    records = []
    examples = [
        ("chrome", "Google Chrome", "chrome.exe", "<b>기획 자료 조사</b>", 10,
         BrowserPage("chrome", "가상 기획 참고 자료", "https://example.com/research?q=sample#intro"),
         None),
        ("pdf", "가상 PDF 앱", "sample.exe", "가상 기획 보고서.pdf", 30,
         None, LocalDocument(r"C:\가상 자료\기획 보고서.pdf", "pdf")),
        ("docx", "Microsoft Word", "winword.exe", "가상 회의록.docx", 60,
         None, LocalDocument(r"C:\가상 자료\회의록.docx", "docx")),
        ("edge", "Microsoft Edge", "msedge.exe", "어제 가상 자료", 1440,
         BrowserPage("edge", "어제 참고 페이지", "https://example.org/notes"), None),
    ]
    for identifier, application, process, title, minutes, browser, document in examples:
        last = now - timedelta(minutes=minutes)
        records.append(ContextRecord(identifier, application, process, title,
                                      (last - timedelta(minutes=3)).isoformat(),
                                      last.isoformat(), 120000, 2, browser, document))
    return records


def synthetic_search(records: list[ContextRecord], request: SearchRequest) -> list[ContextRecord]:
    """미리보기 전용 가상 필터다. 실제 Backend 검색의 구현·검증 근거로 사용하지 않는다."""
    result = []
    for record in records:
        titles = record.window_title + (" " + record.browser.page_title if record.browser else "")
        if request.keyword.casefold() not in titles.casefold():
            continue
        if request.process_name and request.process_name != record.process_name.casefold():
            continue
        source = request.source_type
        if source == "web" and (record.browser is None or record.browser.url is None):
            continue
        if source in ("document", "pdf", "docx") and (
            record.document is None or source != "document" and record.document.file_type != source
        ):
            continue
        moment = parse_timestamp(record.last_active_at)
        if request.active_from and moment < parse_timestamp(request.active_from):
            continue
        if request.active_before and moment >= parse_timestamp(request.active_before):
            continue
        result.append(record)
    result.sort(key=lambda record: record.id)
    result.sort(key=lambda record: parse_timestamp(record.last_active_at),
                reverse=request.sort == "recent")
    return result


def main() -> int:
    """가상 검색 화면을 열고 선택적으로 첫 정상/오류 상태를 PNG로 저장한다."""
    parser = argparse.ArgumentParser(description="Phase 11 조건 검색 가상 미리보기")
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--state", choices=("ready", "empty", "unsupported", "denied"), default="ready")
    parser.add_argument("--source", choices=("all", "web", "document", "pdf", "docx"), default="all")
    args = parser.parse_args()
    records = sample_records()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            """가상 메모리 기록만 처리하며 실제 수집·저장 데이터에는 접근하지 않는다."""
            url = urlsplit(self.path)
            if url.path == "/health":
                response = HealthResponse(HealthStatus("search-preview"))
            elif url.path == "/records/search":
                if args.state in ("unsupported", "denied"):
                    self.send_error(404 if args.state == "unsupported" else 403)
                    return
                raw = asdict(SearchRequest())
                raw.update({key: values[0] for key, values in
                            parse_qs(url.query, keep_blank_values=True).items()})
                raw["limit"] = int(raw["limit"])
                request = read_search_request(raw)
                found = [] if args.state == "empty" else synthetic_search(records, request)
                response = SearchResponse(SearchResults(
                    request, found[:request.limit], len(found) > request.limit))
            else:
                self.send_error(404)
                return
            payload = json.dumps(asdict(response), ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return  # 입력 변경·취소·종료로 닫힌 가상 연결이다.

        def log_message(self, *args):
            """가상 검색어와 출처도 로그에 남기지 않는다."""
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    app = QApplication([sys.argv[0]])
    window = MainWindow(server.server_port)
    window.setWindowTitle("ContextTrace — Phase 11 가상 검색")
    window.layout().insertWidget(0, display_label("가상 검색 미리보기 · 실제 저장 기록은 조회하지 않습니다."))
    window.tabs.setCurrentWidget(window.search)
    window.search.source.setCurrentIndex(window.search.source.findData(args.source))
    window.backend.connection_changed.connect(
        lambda connected: window.search.search() if connected else None)
    signals = (window.search.client.results_received, window.search.client.search_failed)

    def received(*_args):
        """첫 검색 결과가 화면에 배치된 뒤 한 번만 저장한다."""
        for signal in signals:
            signal.disconnect(received)
        QTimer.singleShot(100, snapshot)

    def snapshot():
        """한글·목록·상세·오류를 확인할 앱 화면을 저장하고 종료한다."""
        saved = window.grab().save(str(args.snapshot), "PNG")
        app.exit(0 if saved else 1)

    if args.snapshot:
        for signal in signals:
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
