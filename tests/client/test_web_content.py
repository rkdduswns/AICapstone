"""가상 HTTP로 웹 본문 조회와 출처 일치를 검증한다. 실제 브라우저/웹사이트는 읽지 않는다."""

import json
import os
import sys
import threading
import time
from copy import deepcopy
from dataclasses import asdict, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from client.web_content_client import WebSourceChangedError, read_record_web_content
from client.window import MainWindow
from shared.browser import BrowserPage
from shared.protocol import HealthResponse, HealthStatus
from shared.records import ContextRecord, RecentRecords, RecentRecordsResponse
from shared.web_content import RecordWebContent, RecordWebContentResponse, WebContent

SPECIAL_ID = "가상/record?x=1&y=2#+%"
PAGE = BrowserPage("chrome", "<b>가상 자료</b>", "https://example.com/research?a=1#intro")
OTHER_PAGE = BrowserPage("edge", "다른 페이지", "https://example.org/other")
TEXT = "  첫 문장\n<b>태그도 글자로 표시합니다.</b>\n\n가상 웹페이지 본문입니다.  "
CONTENT = WebContent(PAGE, "2026-10-10T10:05:00+09:00", TEXT, False)
GOOD = asdict(RecordWebContentResponse(RecordWebContent("one", CONTENT)))


@pytest.fixture(scope="module")
def app():
    """Qt 이벤트 루프를 공유하고 테스트 창을 닫아도 다음 테스트를 실행할 수 있게 한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


def wait_for(app, predicate, timeout=4):
    """이벤트를 처리하면서 응답을 기다리되 무한 대기는 테스트 실패로 처리한다."""
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            pytest.fail("Web content UI timed out")
        time.sleep(0.005)
    app.processEvents()


@pytest.fixture
def server():
    """작업별 출처/본문과 지연 응답을 바꿀 수 있는 가상 서버를 제공한다."""
    settings = {"requests": [], "delay": {}, "status": 200, "override": None,
                "pages": {"one": PAGE, SPECIAL_ID: OTHER_PAGE, "plain": None,
                          "internal": BrowserPage("chrome", "새 탭", None)},
                "contents": {"one": CONTENT, SPECIAL_ID: WebContent(
                    OTHER_PAGE, "2026-10-10T10:01:00+09:00", "다른 작업의 웹 본문", False)}}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            """지연 전에 응답을 직렬화해 이전 페이지의 늦은 응답을 재현한다."""
            url = urlsplit(self.path)
            delay, status = 0, 200
            if url.path == "/health":
                body = asdict(HealthResponse(HealthStatus("web-content-test")))
            elif url.path == "/records/recent":
                records = [ContextRecord(
                    identifier, "가상 앱", "sample.exe", "가상 창 제목",
                    "2026-10-10T10:00:00+09:00", f"2026-10-10T10:{20-index:02d}:00+09:00",
                    10000, 1, page,
                ) for index, (identifier, page) in enumerate(settings["pages"].items())]
                body = asdict(RecentRecordsResponse(RecentRecords(records)))
            elif url.path == "/records/web-content":
                query = parse_qs(url.query)
                identifier = query["record_id"][0]
                settings["requests"].append(query)
                body = asdict(RecordWebContentResponse(RecordWebContent(
                    identifier, settings["contents"].get(identifier))))
                if settings["override"] is not None:
                    body = settings["override"]
                delay, status = settings["delay"].get(identifier, 0), settings["status"]
            else:
                self.send_error(404)
                return
            payload = body if isinstance(body, bytes) else json.dumps(body).encode()
            time.sleep(delay)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return  # 선택 전환/timeout/종료로 Client가 취소한 연결은 정상 정리한다.

        def log_message(self, *args):
            """가상 출처와 본문을 로그에 남기지 않는다."""
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_port, settings
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


@pytest.fixture
def window(app, server):
    """실제 최근 기록 탭에서 상세 조회까지 연결하고 종료 시 요청을 정리한다."""
    instance = MainWindow(server[0])
    instance.show()
    try:
        yield instance
    finally:
        instance.close()
        app.processEvents()


def open_records(app, window):
    """목록만 먼저 조회하여 웹 본문이 탭 진입 전에 요청되지 않는지도 검사한다."""
    window.check()
    wait_for(app, lambda: window.button.isEnabled())
    window.tabs.setCurrentWidget(window.recent)
    wait_for(app, lambda: window.recent.loaded)
    return window.recent.web_content


def select_record(window, identifier):
    """정렬 순서에 의존하지 않고 기록 ID로 선택 행을 찾는다."""
    row = next(i for i, record in enumerate(window.recent.records) if record.id == identifier)
    window.recent.table.selectRow(row)


@pytest.mark.parametrize("path,value", [
    (("ok",), 1), (("error",), "error"), (("data",), []),
    (("data", "service"), "other"), (("data", "api_version"), True),
    (("data", "record_id"), "other"), (("data", "content"), []),
    (("data", "content", "page"), None),
    (("data", "content", "page", "url"), None),
    (("data", "content", "page", "url"), "javascript:alert(1)"),
    (("data", "content", "text"), None), (("data", "content", "text"), " \n "),
    # 긴 원문을 테스트 ID에 넣으면 Windows의 환경 변수 길이 제한을 넘을 수 있다.
    pytest.param(("data", "content", "text"), "한" * 50001, id="text-too-long"),
    (("data", "content", "truncated"), 1),
    (("data", "content", "captured_at"), "2026-10-10T10:00:00"),
    (("data", "content", "captured_at"), "2026-02-30T10:00:00Z"),
])
def test_invalid_web_content_contract(path, value):
    """계약 위반·잘못된 출처·과도한 길이는 일부라도 표시하지 않는다."""
    body = deepcopy(GOOD)
    target = body
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        read_record_web_content(json.dumps(body).encode(), "one", PAGE)


@pytest.mark.parametrize("field", ["page", "captured_at", "text", "truncated"])
def test_missing_snapshot_fields(field):
    """필수 정보 누락을 빈 제목/미수집으로 오인하지 않는다."""
    body = deepcopy(GOOD)
    del body["data"]["content"][field]
    with pytest.raises(ValueError):
        read_record_web_content(json.dumps(body).encode(), "one", PAGE)


@pytest.mark.parametrize("field,value", [("url", "https://example.com/changed"), ("browser", "edge")])
def test_source_mismatch_requires_list_refresh(field, value):
    """같은 작업 ID라도 URL/브라우저가 다르면 목록을 다시 확인하도록 구분한다."""
    body = deepcopy(GOOD)
    body["data"]["content"]["page"][field] = value
    with pytest.raises(WebSourceChangedError):
        read_record_web_content(json.dumps(body).encode(), "one", PAGE)


def test_empty_snapshot_and_preserved_text_with_limit():
    """정상 빈 본문과 필드 누락을 구분하고 최대 길이·수집 당시 제목·원문을 유지한다."""
    body = deepcopy(GOOD)
    body["data"]["content"] = None
    assert read_record_web_content(json.dumps(body).encode(), "one", PAGE).content is None
    del body["data"]["content"]
    with pytest.raises(ValueError):
        read_record_web_content(json.dumps(body).encode(), "one", PAGE)
    body = deepcopy(GOOD)
    body["data"]["content"].update(text="한🙂" * 25000, truncated=True)
    body["data"]["content"]["page"]["page_title"] = "수집 시점 제목"
    result = read_record_web_content(json.dumps(body).encode(), "one", PAGE)
    assert len(result.content.text) == 50000 and result.content.truncated
    assert result.content.page.page_title == "수집 시점 제목"
    assert read_record_web_content(json.dumps(GOOD).encode(), "one", PAGE).content.text == TEXT


def test_lazy_plain_text_refresh_truncated_and_empty(app, window, server):
    """탭 진입 시만 요청하며 원문/수집 시각/일부 저장/빈 본문을 구분해 표시한다."""
    web = open_records(app, window)
    assert server[1]["requests"] == []
    window.recent.detail_tabs.setCurrentWidget(web)
    wait_for(app, lambda: web.loaded)
    assert web.text.toPlainText() == TEXT and web.text.isReadOnly()
    assert PAGE.url in web.source.toPlainText() and PAGE.page_title in web.source.toPlainText()
    assert "수집 시각:" in web.source.toPlainText() and window.width() == 620
    assert server[1]["requests"] == [{"record_id": ["one"]}]
    window.recent.detail_tabs.setCurrentIndex(0)
    window.recent.detail_tabs.setCurrentWidget(web)
    assert len(server[1]["requests"]) == 1
    server[1]["contents"]["one"] = replace(CONTENT, text="한" * 50000, truncated=True)
    web.button.click()
    assert not web.source.toPlainText() and not web.text.toPlainText()
    wait_for(app, lambda: web.loaded)
    assert "일부만 저장" in web.status.text() and len(web.text.toPlainText()) == 50000
    server[1]["contents"]["one"] = None
    web.button.click()
    wait_for(app, lambda: web.loaded)
    assert "없습니다" in web.status.text() and not web.source.toPlainText()
    assert not web.text.toPlainText()


@pytest.mark.parametrize("identifier", ["plain", "internal"])
def test_non_web_selection_clears_and_does_not_request(app, window, server, identifier):
    """일반 작업/새 탭은 출처가 없어 요청하지 않고 이전 웹 본문도 제거한다."""
    web = open_records(app, window)
    window.recent.detail_tabs.setCurrentWidget(web)
    wait_for(app, lambda: web.loaded)
    select_record(window, identifier)
    assert not web.button.isEnabled() and not web.text.toPlainText()
    assert not web.source.toPlainText() and len(server[1]["requests"]) == 1
    assert "URL이 없습니다" in web.status.text()


def test_selection_cancels_late_response_and_encodes_id(app, window, server):
    """늦은 A 응답이 B의 출처/본문을 덮지 않으며 특수문자 ID를 쿼리 하나로 전송한다."""
    web = open_records(app, window)
    server[1]["delay"]["one"] = 0.2
    window.recent.detail_tabs.setCurrentWidget(web)
    wait_for(app, lambda: len(server[1]["requests"]) == 1)
    select_record(window, SPECIAL_ID)
    assert not web.text.toPlainText()
    wait_for(app, lambda: web.loaded)
    done = []
    QTimer.singleShot(300, lambda: done.append(True))
    wait_for(app, lambda: done)
    assert web.record_id == SPECIAL_ID and web.text.toPlainText() == "다른 작업의 웹 본문"
    assert OTHER_PAGE.url in web.source.toPlainText()
    assert server[1]["requests"][-1] == {"record_id": [SPECIAL_ID]}


def test_same_record_url_change_recovers_after_list_refresh(app, window, server):
    """목록 이후의 페이지 이동은 출처 불일치로 막고 목록 갱신 후에만 새 본문을 표시한다."""
    web = open_records(app, window)
    window.recent.detail_tabs.setCurrentWidget(web)
    wait_for(app, lambda: web.loaded)
    moved_page = replace(PAGE, url="https://example.com/new-page")
    server[1]["contents"]["one"] = replace(CONTENT, page=moved_page, text="이동 후 새 본문")
    web.button.click()
    wait_for(app, lambda: web.button.isEnabled())
    assert "출처가 변경" in web.status.text() and not web.loaded
    assert not web.text.toPlainText() and not web.source.toPlainText()
    server[1]["pages"]["one"] = moved_page
    window.recent.refresh()
    wait_for(app, lambda: web.loaded)
    assert web.text.toPlainText() == "이동 후 새 본문"
    assert moved_page.url in web.source.toPlainText()


@pytest.mark.parametrize("status,body,message", [
    (403, None, "허용되지"), (404, None, "기능 미지원"), (500, None, "서버 오류"),
    (200, b"bad json", "호환되지"),
    (200, {**GOOD, "data": {**GOOD["data"], "record_id": "other"}}, "호환되지"),
])
def test_error_clears_content_and_manual_recovery(app, window, server, status, body, message):
    """조회 거부·미지원·오류는 빈 본문과 구분하고 이전 출처/본문 제거 후 재조회한다."""
    web = open_records(app, window)
    window.recent.detail_tabs.setCurrentWidget(web)
    wait_for(app, lambda: web.loaded)
    server[1].update(status=status, override=body)
    web.button.click()
    wait_for(app, lambda: web.button.isEnabled())
    assert message in web.status.text() and not web.loaded
    assert not web.text.toPlainText() and not web.source.toPlainText()
    server[1].update(status=200, override=None)
    web.button.click()
    wait_for(app, lambda: web.loaded)
    assert web.text.toPlainText() == TEXT


def test_timeout_single_flight_reconnect_and_close(app, window, server):
    """중복 요청·시간 초과·재연결·종료에서 요청과 텍스트의 수명을 함께 관리한다."""
    web = open_records(app, window)
    server[1]["delay"]["one"] = 0.2
    web.client.timer.setInterval(60)
    window.recent.detail_tabs.setCurrentWidget(web)
    reply = web.client.reply
    web.refresh()
    assert web.client.reply is reply
    wait_for(app, lambda: web.button.isEnabled())
    assert "시간 초과" in web.status.text()
    web.client.timer.setInterval(3000)
    web.refresh()
    window.check()
    assert web.record_id is None and web.client.reply is None
    assert not web.text.toPlainText() and not web.source.toPlainText()
    wait_for(app, lambda: web.loaded)
    web.refresh()
    window.close()
    done = []
    QTimer.singleShot(300, lambda: done.append(True))
    wait_for(app, lambda: done)
    assert web.record_id is None and web.client.reply is None and not web.client.timer.isActive()
    assert not web.text.toPlainText() and not web.source.toPlainText()
