"""가상 공급자로 자연어 검색 입력, 결과 표시와 출처 상세를 검증한다."""

from dataclasses import replace
from datetime import date

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from client.search_client import local_date_range
from client.semantic_search_widget import SemanticSearchInput, SemanticSearchWidget
from client.time_values import format_timestamp
from shared.browser import BrowserPage
from shared.document import LocalDocument
from shared.search_data import DocumentChunk, SourceMetadata

QUERY = "  <b>회의에서 검토한 & 계획을 찾아줘</b>  "
URL = "https://example.com/Research?q=%EA%B0%80#Section"
FILE_PATH = r"C:\가상 자료\회의.PDF"
STARTED = "2026-11-06T09:00:00+09:00"
ACTIVE = "2026-11-06T09:02:00+09:00"
CAPTURED = "2026-11-06T09:03:00+09:00"
WEB_TEXT = "<b>회의의 검토 내용</b>\n웹 본문 둘째 줄"
PDF_TEXT = "가상 PDF 문서 본문입니다."


@pytest.fixture(scope="module")
def app():
    """모든 검색 위젯이 같은 Qt 애플리케이션을 사용한다."""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def hits():
    """확보 시각과 원본 출처가 있는 웹 및 PDF 조각을 제공한다."""
    return [
        DocumentChunk(
            "pdf-chunk", "pdf-record", 4, PDF_TEXT,
            SourceMetadata(
                "document", "가상 문서 앱", "reader.exe", "PDF 검토 자료",
                STARTED, ACTIVE, CAPTURED, False, document=LocalDocument(FILE_PATH, "pdf"),
            ),
        ),
        DocumentChunk(
            "web-chunk", "web-record", 2, WEB_TEXT,
            SourceMetadata(
                "web", "가상 웹 앱", "chrome.exe", "가상 웹 창",
                STARTED, ACTIVE, CAPTURED, True,
                browser=BrowserPage("chrome", "<b>확보 당시 웹 제목</b>", URL),
            ),
        ),
    ]


def test_blank_input_never_submits_and_return_submits_once(app):
    """폼을 열거나 공백을 입력하는 동안 공급자를 호출하지 않고 Return으로 제출한다."""
    requests = []

    def provider(request):
        """호출된 입력을 확인할 수 있도록 저장한다."""
        requests.append(request)
        return []

    widget = SemanticSearchWidget(provider)
    widget.show()
    widget.query.setText("   ")
    widget.search()
    assert requests == []

    widget.query.setText(QUERY)
    assert requests == []
    QTest.keyClick(widget.query, Qt.Key.Key_Return)
    assert requests == [SemanticSearchInput(QUERY.strip(), "", "all", None, None)]


def test_submits_query_with_explicit_process_source_and_local_dates(app):
    """자연어 문장을 유지하고 프로그램, PDF, 현지 날짜 범위를 함께 전달한다."""
    requests = []

    def provider(request):
        """제출한 조건을 기록하고 빈 결과를 반환한다."""
        requests.append(request)
        return []

    widget = SemanticSearchWidget(provider)
    widget.query.setText(QUERY)
    widget.process_name.setText("  READER.EXE  ")
    widget.source.setCurrentIndex(widget.source.findData("pdf"))
    widget.use_dates.setChecked(True)
    widget.first_date.setDate(QDate(2026, 11, 3))
    widget.last_date.setDate(QDate(2026, 11, 6))
    widget.button.click()

    bounds = local_date_range(date(2026, 11, 3), date(2026, 11, 6))
    assert requests == [SemanticSearchInput(QUERY.strip(), "reader.exe", "pdf", *bounds)]


def test_preserves_result_rank_and_displays_exact_source_snapshot(app, hits):
    """공급자 순위를 유지하고 선택한 웹·PDF의 원본 출처와 전체 본문을 표시한다."""
    widget = SemanticSearchWidget(lambda _request: hits)
    widget.query.setText(QUERY)
    widget.button.click()
    assert widget.table.rowCount() == 2
    assert [widget.table.item(row, 0).text().removesuffix("위").strip() for row in range(2)] == ["1", "2"]
    assert widget.table.item(0, 2).text() == "PDF"
    assert "웹" in widget.table.item(1, 2).text()
    assert widget.table.item(0, 3).text() == PDF_TEXT
    assert WEB_TEXT.splitlines()[0] in widget.table.item(1, 3).text()

    widget.table.selectRow(0)
    assert FILE_PATH in widget.detail.toPlainText()
    assert PDF_TEXT in widget.detail.toPlainText()
    assert URL not in widget.detail.toPlainText()

    widget.table.selectRow(1)
    detail = widget.detail.toPlainText()
    assert URL in detail and FILE_PATH not in detail
    assert "<b>확보 당시 웹 제목</b>" in detail
    assert WEB_TEXT in detail
    for timestamp in (STARTED, ACTIVE, CAPTURED):
        assert format_timestamp(timestamp) in detail


def test_sorting_results_keeps_supplier_rank_and_selection(app, hits):
    """받은 결과를 재요청 없이 정렬하고 기존 순위와 선택 상세를 유지한다."""
    requests = []
    pdf, web = hits
    pdf = replace(pdf, source=replace(pdf.source, last_active_at="2026-11-06T09:30:00+09:00"))
    web = replace(web, source=replace(web.source, last_active_at="2026-11-06T01:00:00Z"))

    def provider(request):
        """정렬이 새 질의를 제출하지 않는지 확인하기 위해 호출을 저장한다."""
        requests.append(request)
        return [pdf, web]

    widget = SemanticSearchWidget(provider)
    widget.query.setText(QUERY)
    widget.button.click()
    widget.table.selectRow(0)

    for key, ranks in (
        ("recent", ["2", "1"]),
        ("oldest", ["1", "2"]),
        ("longest", ["2", "1"]),
        ("shortest", ["1", "2"]),
        ("relevance", ["1", "2"]),
    ):
        index = widget.result_order.findData(key)
        assert index >= 0
        widget.result_order.setCurrentIndex(index)
        assert [
            widget.table.item(row, 0).text().removesuffix("위").strip() for row in range(2)
        ] == ranks
        assert widget.table.currentRow() == ranks.index("1")
        assert FILE_PATH in widget.detail.toPlainText()
    assert len(requests) == 1


def test_editing_draft_and_filters_clears_previous_results(app, hits):
    """결과를 선택한 뒤 질의나 출처가 바뀌면 목록과 상세를 함께 비운다."""
    widget = SemanticSearchWidget(lambda _request: hits)
    widget.query.setText(QUERY)

    for edit in (
        lambda: widget.query.setText("추가로 확인할 내용"),
        lambda: widget.source.setCurrentIndex(widget.source.findData("pdf")),
    ):
        widget.button.click()
        widget.table.selectRow(0)
        assert widget.table.rowCount() == len(hits)
        assert widget.detail.toPlainText()

        edit()
        assert widget.table.rowCount() == 0
        assert widget.detail.toPlainText() == ""


def test_empty_result_and_provider_error_are_distinct(app):
    """빈 결과와 공급자 오류를 구분하며 오류 원문을 표시하지 않는다."""
    sensitive_error = "가상 오류 원문 (https://example.com/private)"
    outcomes = iter(([], ValueError(sensitive_error)))

    def provider(_request):
        """정상 빈 목록 다음에 가상 오류를 반환한다."""
        result = next(outcomes)
        if isinstance(result, ValueError):
            raise result
        return result

    widget = SemanticSearchWidget(provider)
    widget.query.setText(QUERY)
    widget.button.click()
    empty_status = widget.status.text()
    assert "없" in empty_status
    assert widget.table.rowCount() == 0
    assert widget.detail.toPlainText() == ""

    widget.button.click()
    assert widget.status.text() != empty_status
    assert sensitive_error not in widget.status.text()
    assert widget.table.rowCount() == 0
    assert widget.detail.toPlainText() == ""


def test_reversed_dates_are_rejected_before_provider(app):
    """끝 날짜가 시작 날짜보다 앞서면 입력 안내만 표시한다."""
    def provider(_request):
        """잘못된 날짜가 제출되면 테스트를 실패시킨다."""
        pytest.fail("역전된 날짜가 공급자로 전달됐습니다.")

    widget = SemanticSearchWidget(provider)
    widget.query.setText(QUERY)
    widget.use_dates.setChecked(True)
    widget.first_date.setDate(QDate(2026, 11, 7))
    widget.last_date.setDate(QDate(2026, 11, 6))
    widget.button.click()

    assert "날짜" in widget.status.text()
    assert widget.table.rowCount() == 0
