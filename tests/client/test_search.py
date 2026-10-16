"""조건 검색 Client의 계약·폼·통신 검증. 가상 필터는 실제 Backend 검색 검증이 아니다."""

import json
import os
import subprocess
import sys
import threading
import time
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import QApplication

from client.search_client import local_date_range, read_search_request, read_search_results
from client.time_values import parse_timestamp
from client.window import MainWindow
from shared.browser import BrowserPage
from shared.document import LocalDocument
from shared.protocol import HealthResponse, HealthStatus
from shared.records import ContextRecord
from shared.search import SearchRequest, SearchResponse, SearchResults

SPECIAL = "<b>가상 &+?#%</b>"
TODAY = datetime.now().astimezone().replace(hour=10, minute=0, second=0, microsecond=0)


def record(identifier, last, browser=None, document=None, process="sample.exe", title="가상 기획"):
    """서로 다른 프로그램·날짜·출처를 가진 고정 가상 기록을 만든다."""
    return ContextRecord(identifier, "가상 앱", process, title,
                         (last - timedelta(minutes=2)).isoformat(), last.isoformat(),
                         60000, 2, browser, document)


RECORDS = [
    record("web", TODAY, BrowserPage("chrome", SPECIAL, "https://example.com/a?q=1#intro"),
           process="chrome.exe"),
    record("pdf", TODAY - timedelta(hours=1),
           document=LocalDocument(r"C:\가상 자료\기획.pdf", "pdf")),
    record("docx", TODAY - timedelta(days=1),
           document=LocalDocument(r"\\example-server\share\회의.docx", "docx"), title="가상 회의"),
    record("plain", TODAY - timedelta(days=2), title="일반 창"),
]
GOOD = asdict(SearchResponse(SearchResults(SearchRequest(), RECORDS, False)))


@pytest.fixture(scope="module")
def app():
    """공유 이벤트 루프를 유지하고 실제 앱에서 검색 탭을 확인한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


def wait_for(app, predicate, timeout=4):
    """Qt 이벤트를 처리하며 비동기 결과를 기다리고 무한 대기를 실패로 처리한다."""
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        if time.monotonic() >= deadline:
            pytest.fail("Search UI timed out")
        time.sleep(0.005)
    app.processEvents()


@pytest.fixture
def server():
    """제출 조건을 기록하고 가상 기록·지연·오류를 제어하는 HTTP 경계를 제공한다."""
    settings = {"requests": [], "status": 200, "override": None, "delay": 0,
                "records": RECORDS, "more": False}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            """요청을 받는 시점의 가상 결과를 직렬화해 늦은 응답을 재현한다."""
            url = urlsplit(self.path)
            delay, status = 0, 200
            if url.path == "/health":
                body = asdict(HealthResponse(HealthStatus("search-test")))
            elif url.path == "/records/search":
                query = parse_qs(url.query, keep_blank_values=True)
                settings["requests"].append(query)
                raw = asdict(SearchRequest())
                raw.update({key: values[0] for key, values in query.items()})
                raw["limit"] = int(raw["limit"])
                request = read_search_request(raw)
                found = []
                for item in settings["records"]:
                    title = item.window_title + (" " + item.browser.page_title if item.browser else "")
                    if request.keyword.casefold() not in title.casefold():
                        continue
                    if request.process_name and item.process_name.casefold() != request.process_name:
                        continue
                    source = request.source_type
                    if source == "web" and (item.browser is None or item.browser.url is None):
                        continue
                    if source in ("document", "pdf", "docx") and (
                        item.document is None or source != "document" and item.document.file_type != source
                    ):
                        continue
                    moment = parse_timestamp(item.last_active_at)
                    if request.active_from and moment < parse_timestamp(request.active_from):
                        continue
                    if request.active_before and moment >= parse_timestamp(request.active_before):
                        continue
                    found.append(item)
                found.sort(key=lambda item: item.id)
                found.sort(key=lambda item: parse_timestamp(item.last_active_at),
                           reverse=request.sort == "recent")
                body = asdict(SearchResponse(SearchResults(
                    request, found[:request.limit], settings["more"] or len(found) > request.limit)))
                if settings["override"] is not None:
                    body = settings["override"]
                delay, status = settings["delay"], settings["status"]
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
                return  # 조건 변경·취소·종료로 Client가 닫은 연결이다.

        def log_message(self, *args):
            """검색어와 가상 출처를 로그에 남기지 않는다."""
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield httpd.server_port, settings
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


@pytest.fixture
def window(app, server):
    """검색 탭을 실제 메인 창에 연결하고 종료 시 요청을 정리한다."""
    instance = MainWindow(server[0])
    instance.show()
    try:
        yield instance
    finally:
        instance.close()
        app.processEvents()


def open_search(app, window):
    """연결 확인 후 검색 탭을 열되 자동 검색이 발생하지 않는지도 확인한다."""
    window.check()
    wait_for(app, lambda: window.button.isEnabled())
    window.tabs.setCurrentWidget(window.search)
    return window.search


def run_search(app, widget):
    """수동 제출하고 성공/오류 처리로 검색 버튼이 다시 열릴 때까지 기다린다."""
    widget.button.click()
    wait_for(app, lambda: widget.button.isEnabled())


@pytest.mark.parametrize("field,value", [
    ("keyword", None), ("keyword", "a" * 201), ("keyword", "title\n"),
    ("process_name", None), ("process_name", "a" * 101), ("process_name", "ß" * 100),
    ("source_type", "other"), ("sort", "score"), ("limit", True), ("limit", 0), ("limit", 21),
    ("active_from", "2026-10-15T00:00:00"), ("active_before", False),
])
def test_invalid_search_input(field, value):
    """잘못된 조건·과도한 길이·모호한 시각은 요청 전에 거부한다."""
    raw = asdict(SearchRequest())
    raw[field] = value
    with pytest.raises(ValueError):
        read_search_request(raw)


def test_input_normalization_and_explicit_time_boundaries():
    """제목 내부 특수문자와 시간대를 유지하고 역전/빈 구간을 거부한다."""
    raw = asdict(SearchRequest("  " + SPECIAL + "  ", " CHROME.EXE ", "web",
                               "2026-10-14T15:00:00Z", "2026-10-16T00:00:00+09:00"))
    query = read_search_request(raw)
    assert query.keyword == SPECIAL and query.process_name == "chrome.exe"
    for before in ("2026-10-15T00:00:00+09:00", "2026-10-14T23:59:59+09:00"):
        with pytest.raises(ValueError):
            read_search_request({**raw, "active_before": before})
    first, end = local_date_range(date.today(), date.today())
    assert parse_timestamp(first).date() == date.today()
    assert parse_timestamp(end).date() == date.today() + timedelta(days=1)
    with pytest.raises(ValueError):
        local_date_range(date.today(), date.today() - timedelta(days=1))


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="POSIX 시간대 전환 검증")
def test_local_date_range_respects_dst_in_isolated_process():
    """Qt 실행 중인 프로세스의 시간대는 바꾸지 않고 DST 날짜 경계를 별도로 검증한다."""
    script = (
        "import json,time;time.tzset();"
        "from datetime import date;"
        "from client.search_client import local_date_range;"
        "print(json.dumps(local_date_range(date(2026,3,8),date(2026,3,8))))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], env={**os.environ, "TZ": "America/New_York"},
        check=True, capture_output=True, text=True)
    first, end = json.loads(result.stdout)
    assert first.endswith("-05:00") and end.endswith("-04:00")
    assert parse_timestamp(end) - parse_timestamp(first) == timedelta(hours=23)


@pytest.mark.parametrize("path,value", [
    (("ok",), 1), (("error",), "error"), (("data",), []),
    (("data", "service"), "other"), (("data", "api_version"), True),
    (("data", "request"), {}), (("data", "request", "keyword"), "other"),
    (("data", "request", "limit"), True), (("data", "has_more"), 1),
    (("data", "has_more"), True), (("data", "records"), None),
    (("data", "records"), [asdict(RECORDS[0])] * 2),
    (("data", "records"), [asdict(item) for item in reversed(RECORDS)]),
    (("data", "records", 0, "window_title"), None),
    (("data", "records", 0, "document"), asdict(LocalDocument(r"C:\fake.pdf", "pdf"))),
])
def test_invalid_search_response(path, value):
    """확인되지 않은 조건·중복/잘못된 기록·정렬·출처 오류를 정상 결과로 표시하지 않는다."""
    body = deepcopy(GOOD)
    target = body
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        read_search_results(json.dumps(body).encode(), SearchRequest())


@pytest.mark.parametrize("field", ["request", "records", "has_more"])
def test_required_result_fields(field):
    """필수 응답 누락을 정상 빈 검색으로 처리하지 않는다."""
    body = deepcopy(GOOD)
    del body["data"][field]
    with pytest.raises(ValueError):
        read_search_results(json.dumps(body).encode(), SearchRequest())


def test_result_order_limit_and_legacy_origin_fields():
    """시간대 기준 정렬을 확인하고 구형 출처 누락과 최대 개수를 검증한다."""
    body = deepcopy(GOOD)
    del body["data"]["records"][-1]["browser"]
    del body["data"]["records"][-1]["document"]
    assert len(read_search_results(json.dumps(body).encode(), SearchRequest()).records) == 4
    body["data"]["request"]["sort"] = "oldest"
    body["data"]["records"].reverse()
    result = read_search_results(json.dumps(body).encode(), SearchRequest(sort="oldest"))
    assert result.records[0].id == "plain"
    body["data"]["request"]["limit"] = 1
    with pytest.raises(ValueError):
        read_search_results(json.dumps(body).encode(), SearchRequest(sort="oldest", limit=1))


@pytest.mark.parametrize("keyword,process,source,period,expected", [
    ("", "", "all", 1, ["web", "pdf"]),
    ("", " CHROME.EXE ", "all", 0, ["web"]),
    ("", "", "pdf", 0, ["pdf"]),
    ("", "", "docx", 0, ["docx"]),
    ("", "", "document", 0, ["pdf", "docx"]),
    ("", "", "web", 0, ["web"]),
    ("기획", "chrome.exe", "web", 1, ["web"]),
    ("없는 검색어", "", "all", 0, []),
])
def test_filters_sent_and_controlled_results_displayed(
    app, window, server, keyword, process, source, period, expected,
):
    """요청에 조건이 전달되고 가상 결과·전체 출처·열람 시각이 표시되는지 확인한다."""
    widget = open_search(app, window)
    assert not server[1]["requests"]
    widget.keyword.setText(keyword)
    widget.process_name.setText(process)
    widget.source.setCurrentIndex(widget.source.findData(source))
    widget.period.setCurrentIndex(period)
    run_search(app, widget)
    assert [record.id for record in widget.records] == expected
    query = server[1]["requests"][-1]
    assert query["keyword"] == [keyword] and query["process_name"] == [process.strip().casefold()]
    assert query["source_type"] == [source] and query["sort"] == ["recent"]
    assert ("active_from" in query) == (period == 1)
    if expected:
        assert "확인된 조건" in widget.applied.text()
        assert "열람 시작:" in widget.detail.toPlainText() and "마지막 활성:" in widget.detail.toPlainText()
        assert widget.detail.isReadOnly() and window.width() == 620
    else:
        assert "기록이 없습니다" in widget.status.text() and not widget.detail.toPlainText()


def test_custom_dates_oldest_order_selection_and_special_query(app, window, server):
    """기간 양끝·정렬·선택 상세·특수문자 키워드를 독립된 쿼리 값으로 전송한다."""
    widget = open_search(app, window)
    widget.period.setCurrentIndex(2)
    widget.first_date.setDate(QDate.currentDate().addDays(-1))
    widget.order.setCurrentIndex(1)
    run_search(app, widget)
    assert [r.id for r in widget.records] == ["docx", "pdf", "web"]
    widget.table.selectRow(0)
    assert RECORDS[2].document.file_path in widget.detail.toPlainText()
    widget.period.setCurrentIndex(0)
    widget.keyword.setText(SPECIAL)
    assert not widget.records and not widget.detail.toPlainText()
    run_search(app, widget)
    assert [r.id for r in widget.records] == ["web"]
    assert server[1]["requests"][-1]["keyword"] == [SPECIAL]
    assert widget.table.item(0, 0).text() == SPECIAL  # 태그 모양의 제목도 일반 텍스트로 보존한다.
    assert RECORDS[0].browser.url in widget.detail.toPlainText()


def test_bad_date_range_does_not_request(app, window, server):
    """역전된 날짜 입력을 폼에서 안내하고 네트워크로 보내지 않는다."""
    widget = open_search(app, window)
    widget.period.setCurrentIndex(2)
    widget.first_date.setDate(QDate.currentDate().addDays(1))
    widget.button.click()
    assert "시작 날짜" in widget.status.text() and not server[1]["requests"]


@pytest.mark.parametrize("status,override,message", [
    (404, None, "기능 준비 중"), (403, None, "허용되지"), (422, None, "검색 조건"),
    (500, None, "서버 오류"), (200, b"not json", "호환되지"),
    (200, {**GOOD, "data": {**GOOD["data"], "request": {}}}, "호환되지"),
])
def test_errors_clear_and_manual_retry(app, window, server, status, override, message):
    """미지원·거부·잘못된 응답을 빈 결과와 구분하고 수동 검색으로 복구한다."""
    widget = open_search(app, window)
    run_search(app, widget)
    server[1].update(status=status, override=override)
    run_search(app, widget)
    assert message in widget.status.text() and not widget.records
    assert not widget.detail.toPlainText() and "조건 없음" in widget.applied.text()
    server[1].update(status=200, override=None)
    run_search(app, widget)
    assert len(widget.records) == 4


def test_edit_cancels_late_results_and_new_query_survives(app, window, server):
    """옛 결과가 새 입력을 덮지 못하고 입력 변경 직후 재검색이 가능하다."""
    widget = open_search(app, window)
    server[1]["delay"] = 0.2
    widget.button.click()
    wait_for(app, lambda: len(server[1]["requests"]) == 1)
    widget.search()
    assert len(server[1]["requests"]) == 1
    widget.source.setCurrentIndex(widget.source.findData("pdf"))
    assert widget.client.reply is None and not widget.records
    server[1]["delay"] = 0
    run_search(app, widget)
    done = []
    QTimer.singleShot(300, lambda: done.append(True))
    wait_for(app, lambda: done)
    assert [r.id for r in widget.records] == ["pdf"] and len(server[1]["requests"]) == 2


def test_cancel_timeout_reconnect_and_close(app, window, server):
    """취소·timeout·재연결·종료에서 요청과 상세를 정리하고 입력 초안을 유지한다."""
    widget = open_search(app, window)
    widget.process_name.setText("chrome.exe")
    server[1]["delay"] = 0.2
    widget.button.click()
    wait_for(app, lambda: len(server[1]["requests"]) == 1)
    widget.cancel_button.click()
    assert widget.client.reply is None and "취소" in widget.status.text()
    widget.client.timer.setInterval(40)
    run_search(app, widget)
    assert "시간 초과" in widget.status.text() and not widget.records
    server[1]["delay"] = 0
    widget.client.timer.setInterval(3000)
    run_search(app, widget)
    window.check()
    assert not widget.records and widget.process_name.text() == "chrome.exe"
    wait_for(app, lambda: window.button.isEnabled())
    count = len(server[1]["requests"])
    assert widget.button.isEnabled()
    app.processEvents()
    assert len(server[1]["requests"]) == count  # 재연결은 사용자의 명시적 검색을 기다린다.
    server[1]["delay"] = 0.2
    widget.button.click()
    window.close()
    assert widget.client.reply is None and not widget.client.timer.isActive()
    assert not widget.records and not widget.detail.toPlainText()


def test_full_limit_notice(app, window, server):
    """전체 개수를 추정하지 않고 반환 상한과 더 있음 여부를 표시한다."""
    widget = open_search(app, window)
    server[1]["records"] = [replace(RECORDS[0], id=f"limit-{i:02}") for i in range(20)]
    server[1]["more"] = True
    run_search(app, widget)
    assert len(widget.records) == 20 and "더 많은 기록" in widget.status.text()
