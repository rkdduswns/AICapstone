"""작은 검색 창의 전환과 가상 비동기 응답의 수명 경계를 검증한다."""

from dataclasses import replace

import pytest
from PySide6.QtCore import QMimeData, QPoint, QRect, Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from client.compact_search_window import CompactAnswer, CompactSearchWindow
from client.time_values import format_timestamp
from shared.browser import BrowserPage
from shared.document import LocalDocument
from shared.search_data import DocumentChunk, SourceMetadata

QUERY = "개인정보 저장 기준을 어디서 봤지?"
SHORT_ANSWER = "<b>저장 기준은 웹페이지와 PDF 두 곳에서 확인했습니다.</b>"
FULL_ANSWER = "웹페이지에서는 수집 제외 조건을 다룹니다.\n\nPDF는 일시정지 동작을 설명합니다."
STARTED = "2026-11-06T09:00:00+09:00"
ACTIVE = "2026-11-06T09:02:00+09:00"
CAPTURED = "2026-11-06T09:03:00+09:00"
URL = "https://example.com/Research?q=%EA%B0%80#Section"
FILE_PATH = r"C:\가상 자료\개인정보 처리 안내.PDF"
WEB_TEXT = "<b>민감한 내용은 수집에서 제외합니다.</b>"
PDF_TEXT = "일시정지 중에는 새로 수집하지 않습니다."


@pytest.fixture(scope="module")
def app():
    """Qt의 이벤트와 초점 상태를 테스트 간에 같은 애플리케이션에서 처리한다."""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def clipboard(monkeypatch):
    """시스템 클립보드 대신 메모리의 Qt 텍스트 객체에 복사 결과를 받는다."""
    data = QMimeData()
    monkeypatch.setattr(QApplication, "clipboard", staticmethod(lambda: data))
    return data


@pytest.fixture
def search(app):
    """요청과 취소 신호를 기록해 응답 순서를 테스트에서 직접 제어한다."""
    window = CompactSearchWindow()
    requests = []
    cancellations = []
    window.search_requested.connect(lambda identifier, query: requests.append((identifier, query)))
    window.search_cancelled.connect(cancellations.append)
    window.move(window.screen().availableGeometry().topLeft() + QPoint(20, 20))
    window.show()
    window.activateWindow()
    app.processEvents()
    return window, requests, cancellations


@pytest.fixture
def answer():
    """서로 다른 원본 유형의 근거를 공급자 순서로 전달한다."""
    return CompactAnswer(
        "answer", SHORT_ANSWER, FULL_ANSWER,
        (
            DocumentChunk(
                "web-chunk", "web-record", 1, WEB_TEXT,
                SourceMetadata(
                    "web", "가상 웹 앱", "chrome.exe", "브라우저 창",
                    STARTED, ACTIVE, CAPTURED, False,
                    browser=BrowserPage("chrome", "확보 당시 웹 제목", URL),
                ),
            ),
            DocumentChunk(
                "pdf-chunk", "pdf-record", 4, PDF_TEXT,
                SourceMetadata(
                    "document", "가상 문서 앱", "reader.exe", "가상 PDF 제목",
                    STARTED, ACTIVE, CAPTURED, True,
                    document=LocalDocument(FILE_PATH, "pdf"),
                ),
            ),
        ),
    )


def test_starts_compact_and_can_open_results_before_search(app, search):
    """첫 검색 전 빈 패널을 열고 닫을 때 조회를 시작하지 않는다."""
    window, requests, _ = search
    initial_size = window.size()
    initial_pos = window.frameGeometry().topLeft()
    assert initial_size.width() <= 480 and initial_size.height() <= 150
    assert window.query.hasFocus()
    assert window.results_button.isEnabled()
    assert window.empty_message.isHidden()
    assert window.detail_panel.isHidden()
    assert window.search_button.isEnabled() is False

    window.results_button.click()
    app.processEvents()
    assert window.empty_message.isVisible()
    assert window.height() > initial_size.height()
    assert window.frameGeometry().topLeft() == initial_pos
    assert requests == []

    QTest.keyClick(window.results_button, Qt.Key.Key_Escape)
    assert window.empty_message.isHidden()
    assert window.size() == initial_size
    assert window.results_button.hasFocus()


def test_answer_expands_from_summary_to_exact_ordered_sources(app, search, answer):
    """요약에서 전체 답변을 먼저 읽고 근거와 출처 세부 정보는 필요할 때 펼친다."""
    window, requests, _ = search
    initial_size = window.size()
    window.query.setText(f"  {QUERY}  ")
    QTest.keyClick(window.query, Qt.Key.Key_Return)
    assert len(requests) == 1
    identifier, query = requests[0]
    assert query == QUERY
    assert window.size() == initial_size

    window.receive_result(identifier, answer)
    app.processEvents()
    summary_size = window.size()
    assert summary_size.height() > initial_size.height()
    assert window.summary.isVisible()
    assert "".join(window.summary.text().split()) == "".join(SHORT_ANSWER.split())
    assert window.summary.textFormat() == Qt.TextFormat.PlainText
    assert window.detail_panel.isHidden()

    window.detail_button.click()
    app.processEvents()
    assert window.detail_panel.isVisible()
    assert window.height() > summary_size.height()
    assert window.detail_text.isReadOnly()
    assert window.detail_text.toPlainText() == FULL_ANSWER
    assert window.evidence_picker.count() == 2
    assert not window.evidence_body.isVisible()
    assert not window.copy_source_button.isVisible()
    window.evidence_toggle.click()
    assert window.evidence_body.isVisible()
    assert not window.source_details.isVisible()
    window.evidence_picker.setCurrentIndex(0)
    assert window.evidence_text.toPlainText() == WEB_TEXT
    assert "확보 당시 웹 제목" in window.source_summary.text()
    assert "웹" in window.source_summary.text()
    assert window.source_summary.textFormat() == Qt.TextFormat.PlainText
    window.source_details_button.click()
    assert window.source_details.isVisible()
    web = window.source_details.toPlainText()
    assert URL in web and FILE_PATH not in web
    for timestamp in (STARTED, ACTIVE, CAPTURED):
        assert format_timestamp(timestamp) in web
    window.evidence_picker.setCurrentIndex(1)
    pdf = window.source_details.toPlainText()
    assert window.detail_text.toPlainText() == FULL_ANSWER
    assert FILE_PATH in pdf and URL not in pdf
    assert window.evidence_text.toPlainText() == PDF_TEXT
    assert len(requests) == 1

    QTest.keyClick(window.collapse_button, Qt.Key.Key_Escape)
    assert window.detail_panel.isHidden()
    assert window.summary.isVisible()
    assert window.size() == summary_size
    QTest.keyClick(window.detail_button, Qt.Key.Key_Escape)
    assert not window.summary.isVisible()
    assert window.size() == initial_size
    assert window.results_button.hasFocus()


def test_sorting_evidence_keeps_citation_numbers_and_selected_source(search, answer):
    """시간대와 글자 수로 순서를 바꿔도 인용 번호와 선택한 출처를 보존한다."""
    window, requests, _ = search
    web, pdf = answer.evidence
    web = replace(
        web, text="🙂🙂🙂",
        source=replace(web.source, last_active_at="2026-11-06T09:30:00+09:00"),
    )
    pdf = replace(
        pdf, text="가나다라",
        source=replace(pdf.source, last_active_at="2026-11-06T01:00:00Z"),
    )
    tied = replace(
        web, id="tied-chunk", chunk_index=2, text="마바사아",
        source=replace(web.source, last_active_at="2026-11-06T10:00:00+09:00"),
    )
    full_answer = "웹과 PDF에서 확인했습니다. [1] [2]"

    window.query.setText(QUERY)
    window.submit()
    window.receive_result(requests[0][0], replace(
        answer, full_answer=full_answer, evidence=(web, pdf, tied),
    ))
    assert not window.evidence_order.isVisible()
    window.detail_button.click()
    assert not window.evidence_order.isVisible()
    window.evidence_toggle.click()
    assert window.evidence_order.isVisible()
    window.evidence_picker.setCurrentIndex(window.evidence_picker.findData(1))

    for key, order in (
        ("recent", [1, 2, 0]),
        ("oldest", [0, 1, 2]),
        ("longest", [1, 2, 0]),
        ("shortest", [0, 1, 2]),
        ("relevance", [0, 1, 2]),
    ):
        index = window.evidence_order.findData(key)
        assert index >= 0
        window.evidence_order.setCurrentIndex(index)
        assert [window.evidence_picker.itemData(row) for row in range(3)] == order
        for row, original in enumerate(order):
            number = original + 1
            assert window.evidence_picker.itemText(row).startswith((f"{number}.", f"[{number}]"))
        assert window.evidence_picker.currentData() == 1
        assert window.detail_text.toPlainText() == full_answer
        detail = window.source_details.toPlainText()
        assert FILE_PATH in detail and URL not in detail
        assert window.evidence_text.toPlainText() == pdf.text
    assert len(requests) == 1


def test_hiding_results_during_search_defers_reveal_and_reuses_answer(app, search, answer):
    """진행 중 결과를 닫으면 응답이 도착해도 사용자가 다시 펼칠 때까지 기다린다."""
    window, requests, cancellations = search
    initial_size = window.size()
    window.query.setText(QUERY)
    window.submit()
    assert len(requests) == 1
    window.results_button.click()
    window.results_button.click()
    window.receive_result(requests[0][0], answer)
    app.processEvents()
    assert window.size() == initial_size
    assert not window.summary.isVisible()
    assert cancellations == []

    window.results_button.click()
    assert window.summary.isVisible()
    assert "".join(window.summary.text().split()) == "".join(SHORT_ANSWER.split())
    assert len(requests) == 1


def test_edit_and_cancel_reject_late_responses(app, search, answer):
    """입력 수정과 취소 뒤 도착한 응답이 상태나 이전 답변을 복구하지 못한다."""
    window, requests, cancellations = search
    initial_size = window.size()
    window.query.setText(QUERY)
    window.submit()
    first_id = requests[-1][0]
    window.query.setText("다른 질문")
    assert cancellations == [first_id]
    window.submit()
    second_id = requests[-1][0]
    assert first_id != second_id
    pending_status = window.status.text()
    window.receive_result(first_id, answer)
    assert window.status.text() == pending_status
    assert not window.summary.isVisible()

    QTest.keyClick(window.query, Qt.Key.Key_Escape)
    assert cancellations == [first_id, second_id]
    assert window.query.hasFocus()
    cancelled_status = window.status.text()
    window.receive_result(second_id, answer)
    assert not window.summary.isVisible()
    assert window.size() == initial_size
    assert window.status.text() == cancelled_status
    app.processEvents()


def test_closing_cancels_pending_request_and_late_answer(search, answer):
    """창 종료 후 도착한 응답이 가려진 답변을 갱신하지 않는다."""
    window, requests, cancellations = search
    window.query.setText(QUERY)
    window.submit()
    identifier = requests[-1][0]
    window.close()
    assert cancellations == [identifier]
    window.receive_result(identifier, answer)
    assert window.isHidden()
    assert not window.summary.isVisible()
    assert window.summary.text() != SHORT_ANSWER


def test_empty_error_and_insufficient_look_distinct_and_only_evidence_expands(search, answer):
    """응답 종류별 안내를 구분하며 근거 부족에는 생성 답변 대신 검증된 출처를 연다."""
    window, requests, _ = search
    window.query.setText(QUERY)
    initial_size = window.size()
    statuses = []
    for response in (
        CompactAnswer("empty"),
        CompactAnswer("error"),
        CompactAnswer("insufficient", evidence=answer.evidence),
    ):
        window.submit()
        window.receive_result(requests[-1][0], response)
        statuses.append(window.status.text())
        assert not window.summary.isVisible()
        assert window.detail_panel.isHidden()
        assert window.size() == initial_size
        assert window.evidence_button.isVisible() == (response.status == "insufficient")
    assert all(statuses)
    assert len(set(statuses)) == 3

    window.evidence_button.click()
    assert window.detail_panel.isVisible()
    assert window.evidence_picker.count() == 2
    assert not window.answer_section.isVisible()
    assert window.evidence_body.isVisible()
    window.evidence_picker.setCurrentIndex(0)
    assert window.detail_text.toPlainText() == ""
    assert URL in window.source_details.toPlainText()
    assert window.evidence_text.toPlainText() == WEB_TEXT


def test_no_summary_uses_a_labeled_preview_and_preserves_full_answer(search, answer):
    """요약이 비어 있으면 일부를 미리보기로 표시하고 상세에서 원문을 연다."""
    window, requests, _ = search
    full_answer = "전체 답변의 시작입니다.\n\n" + ("긴 한글 답변 " * 100) + "전체 답변의 끝입니다."
    window.query.setText(QUERY)
    window.submit()
    window.receive_result(
        requests[-1][0],
        CompactAnswer("answer", full_answer=full_answer, evidence=answer.evidence),
    )
    assert window.summary.isVisible()
    assert "전체 답변의 시작" in window.summary.text()
    assert any(
        "미리보기" in label.text()
        for label in window.findChildren(QLabel)
        if label.isVisible()
    )
    assert "일부 표시 중" in window.summary_heading.text()
    assert window.summary.text().endswith("…")
    window.detail_button.click()
    assert window.detail_text.isVisible()
    assert full_answer in window.detail_text.toPlainText()


def test_long_source_address_wraps_without_changing_original(app, search, answer):
    """공백 없는 긴 URL도 상세에서 줄을 나누고 복사할 원래 주소는 그대로 유지한다."""
    window, requests, _ = search
    long_url = "https://example.com/" + "x" * 1200
    web = answer.evidence[0]
    source = replace(web.source, browser=replace(web.source.browser, url=long_url))
    response = replace(answer, evidence=(replace(web, source=source),))

    window.query.setText(QUERY)
    window.submit()
    window.receive_result(requests[-1][0], response)
    window.detail_button.click()
    window.evidence_toggle.click()
    window.source_details_button.click()
    app.processEvents()
    document = window.source_details.document()
    match = document.find(long_url)
    assert not match.isNull()
    block = match.block()
    document.documentLayout().blockBoundingRect(block)
    assert block.layout().lineCount() > 2
    assert window.source_details.horizontalScrollBar().maximum() == 0


def test_long_source_summary_stays_two_lines_and_cleared_text_cannot_reappear(app, search, answer):
    """긴 출처는 개요에서 줄여도 원문을 보존하고 입력 편집 후 크기 변경으로 복구하지 않는다."""
    window, requests, _ = search
    title = "긴제목원문" * 100
    url = "https://example.test/" + "original-path-" * 120
    web = answer.evidence[0]
    source = replace(web.source, browser=replace(web.source.browser, page_title=title, url=url))
    window.query.setText(QUERY)
    window.submit()
    window.receive_result(requests[-1][0], replace(answer, evidence=(replace(web, source=source),)))
    window.detail_button.click()
    window.evidence_toggle.click()
    app.processEvents()

    summary = window.source_summary
    assert 1 <= len(summary.text().splitlines()) <= 2
    assert "…" in summary.text()
    assert title in summary.toolTip()
    assert title in window.source_details.toPlainText()
    assert url in window.source_details.toPlainText()
    for line in summary.text().splitlines():
        assert summary.fontMetrics().horizontalAdvance(line) <= summary.contentsRect().width() + 1

    window.query.setText("새 가상 검색 문장")
    assert summary.text() == "" and summary.toolTip() == ""
    assert window.source_details.toPlainText() == ""
    previous_size = summary.size()
    summary.resize(300, 50)
    # 숨은 위젯의 지연된 resizeEvent까지 전달해 이전 원문 캐시가 되살아나지 않게 확인한다.
    QApplication.sendEvent(summary, QResizeEvent(summary.size(), previous_size))
    app.processEvents()
    assert summary.text() == "" and summary.toolTip() == ""
    assert window.source_details.toPlainText() == ""


@pytest.mark.parametrize(
    "long_summary",
    ["요약의 핵심 내용을 확인합니다. " * 40, "x" * 800, "🙂" * 300],
    ids=["wrapped-sentences", "unbroken-word", "emoji"],
)
def test_clipped_summary_fits_visible_label_and_preserves_full_answer(
    app, search, answer, long_summary,
):
    """긴 문장·공백 없는 단어·이모지를 자른 요약이 실제 표시 영역 안에 들어간다."""
    window, requests, _ = search
    full = "전체 답변의 시작\n" + long_summary + "\n전체 답변의 끝"
    window.query.setText(QUERY)
    window.submit()
    window.receive_result(
        requests[-1][0], replace(answer, summary=long_summary, full_answer=full),
    )
    window.resize(320, window.height())
    app.processEvents()

    text = window.summary.text()
    assert text.endswith("…")
    assert "일부 표시 중" in window.summary_heading.text()
    assert window.summary.height() <= 110
    bounds = window.summary.contentsRect()
    measured = window.summary.fontMetrics().boundingRect(
        QRect(0, 0, bounds.width(), 10000), Qt.TextFlag.TextWordWrap, text,
    )
    assert measured.width() <= bounds.width() + 1
    assert measured.height() <= bounds.height() + 1
    assert not any(0xD800 <= ord(character) <= 0xDFFF for character in text)
    if long_summary.startswith("🙂"):
        assert long_summary.startswith(text.removesuffix("…").replace("\n", ""))

    window.detail_button.click()
    assert full in window.detail_text.toPlainText()


def test_summary_refits_on_resize_and_short_summary_keeps_original(app, search, answer):
    """같은 응답을 좁혔다 넓히면 요약 표시 범위를 다시 계산하고 짧은 답변은 보존한다."""
    window, requests, _ = search
    font = window.summary.font()
    font.setPointSize(13)
    window.summary.setFont(font)
    long_summary = "가" * 120
    window.query.setText(QUERY)
    window.submit()
    window.receive_result(requests[-1][0], replace(answer, summary=long_summary))

    window.resize(320, window.height())
    app.processEvents()
    narrow = window.summary.text()
    assert narrow.endswith("…")
    assert "일부 표시 중" in window.summary_heading.text()

    window.resize(760, window.height())
    app.processEvents()
    assert window.summary.text().replace("\n", "") == long_summary
    assert "일부 표시 중" not in window.summary_heading.text()
    assert len(window.summary.text()) > len(narrow)

    window.submit()
    window.receive_result(requests[-1][0], replace(answer, summary="짧은 답변"))
    app.processEvents()
    assert window.summary.text() == "짧은 답변"
    assert "일부 표시 중" not in window.summary_heading.text()


def test_detail_actions_copy_original_values_and_return_to_answer_start(app, search, answer, clipboard):
    """정렬 후 선택한 원본 주소와 전체 답변을 복사하고 긴 상세의 맨 위로 이동한다."""
    window, requests, _ = search
    full = "가상 전체 답변 첫 줄\n" + ("가상 답변의 긴 문장\n" * 100) + "마지막 줄"
    web, pdf = answer.evidence
    response = replace(
        answer, full_answer=full,
        evidence=(replace(web, text="짧은 근거"), replace(pdf, text="긴 문서 근거" * 20)),
    )
    clipboard.setText("synthetic-clipboard-start")
    try:
        window.query.setText(QUERY)
        window.submit()
        window.receive_result(requests[-1][0], response)
        window.detail_button.click()
        app.processEvents()
        assert window.answer_top_button.isVisible()
        assert window.copy_answer_button.isVisible()
        assert not window.copy_source_button.isVisible()
        window.evidence_toggle.click()
        assert window.copy_source_button.isVisible()
        window.copy_answer_button.click()
        assert clipboard.text() == full
        assert "복사" in window.detail_feedback.text()

        window.evidence_picker.setCurrentIndex(window.evidence_picker.findData(0))
        window.evidence_order.setCurrentIndex(window.evidence_order.findData("longest"))
        assert window.evidence_picker.currentData() == 0
        window.copy_source_button.click()
        assert clipboard.text() == URL
        window.evidence_picker.setCurrentIndex(window.evidence_picker.findData(1))
        assert window.detail_feedback.text() == ""
        window.copy_source_button.click()
        assert clipboard.text() == FILE_PATH

        scrollbar = window.detail_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        assert scrollbar.value() > 0
        window.answer_top_button.click()
        assert scrollbar.value() == 0

        window.query.setText("새 가상 질문")
        clipboard.setText("synthetic-after-edit")
        for button in (
            window.answer_top_button, window.copy_answer_button, window.copy_source_button,
        ):
            assert not button.isVisible()
        window.copy_answer_button.click()
        window.copy_source_button.click()
        assert clipboard.text() == "synthetic-after-edit"
        assert window.detail_text.toPlainText() == ""
        assert window.evidence_text.toPlainText() == ""
        assert window.source_details.toPlainText() == ""
        assert window.source_summary.text() == ""
        assert window.detail_feedback.text() == ""
    finally:
        clipboard.clear()


def test_insufficient_evidence_only_offers_source_copy(app, search, answer, clipboard):
    """근거 부족 상태에서는 원본 출처를 복사하며 생성 답변용 동작은 숨긴다."""
    window, requests, _ = search
    clipboard.setText("synthetic-insufficient-start")
    try:
        window.query.setText(QUERY)
        window.submit()
        window.receive_result(
            requests[-1][0],
            CompactAnswer("insufficient", full_answer="가상으로 무시할 답변", evidence=answer.evidence),
        )
        window.evidence_button.click()
        app.processEvents()
        assert not window.answer_top_button.isVisible()
        assert not window.copy_answer_button.isVisible()
        assert not window.answer_section.isVisible()
        assert window.evidence_body.isVisible()
        assert window.copy_source_button.isVisible()
        assert "가상으로 무시할 답변" not in window.detail_text.toPlainText()
        window.evidence_picker.setCurrentIndex(window.evidence_picker.findData(0))
        window.copy_source_button.click()
        assert clipboard.text() == URL
        window.copy_answer_button.click()
        assert clipboard.text() == URL
    finally:
        clipboard.clear()


def test_source_selection_keeps_answer_and_reading_position(app, search, answer):
    """여러 출처를 비교해도 답변과 인용 원문 및 답변을 읽던 위치를 유지한다."""
    window, requests, _ = search
    full = "답변의 첫 문단 [1]\n" + ("같은 답변을 읽고 있습니다.\n" * 100) + "끝 문단 [2]"
    window.query.setText(QUERY)
    window.submit()
    window.receive_result(requests[-1][0], replace(answer, full_answer=full))
    window.detail_button.click()
    window.evidence_toggle.click()
    app.processEvents()
    scrollbar = window.detail_text.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum() // 2)
    position = scrollbar.value()
    assert position > 0

    window.evidence_picker.setCurrentIndex(window.evidence_picker.findData(1))
    app.processEvents()
    assert window.detail_text.toPlainText() == full
    assert scrollbar.value() == position
    assert window.evidence_text.toPlainText() == PDF_TEXT
    assert FILE_PATH in window.source_details.toPlainText()
    assert len(requests) == 1


def test_folding_detail_preserves_selection_and_new_response_resets_sources(app, search, answer):
    """같은 결과를 접었다 펴면 선택을 유지하고 새 응답은 근거 접힘 상태부터 시작한다."""
    window, requests, _ = search
    window.query.setText(QUERY)
    window.submit()
    window.receive_result(requests[-1][0], answer)
    window.detail_button.click()
    window.evidence_toggle.click()
    window.evidence_picker.setCurrentIndex(window.evidence_picker.findData(1))
    window.source_details_button.click()
    assert window.source_details.isVisible()

    window.collapse_button.click()
    window.detail_button.click()
    app.processEvents()
    assert window.evidence_body.isVisible()
    assert window.evidence_picker.currentData() == 1
    assert window.source_details.isVisible()
    assert FILE_PATH in window.source_details.toPlainText()

    window.submit()
    window.receive_result(requests[-1][0], replace(answer, evidence=answer.evidence[:1]))
    window.detail_button.click()
    app.processEvents()
    assert not window.evidence_body.isVisible()
    assert not window.source_details.isVisible()
    assert window.evidence_picker.count() == 1
    assert window.evidence_picker.currentData() == 0
    assert FILE_PATH not in window.source_details.toPlainText()
    assert URL in window.source_details.toPlainText()
    window.close()
    assert window.evidence_text.toPlainText() == ""
    assert window.source_details.toPlainText() == ""
    assert window.source_summary.text() == ""


def test_answer_without_sources_does_not_offer_empty_evidence_controls(app, search):
    """출처가 없는 답변에는 빈 출처 선택이나 복사 동작을 제시하지 않는다."""
    window, requests, _ = search
    window.query.setText(QUERY)
    window.submit()
    window.receive_result(requests[-1][0], CompactAnswer("answer", "짧은 요약", "제공된 전체 답변"))
    window.detail_button.click()
    app.processEvents()
    assert window.answer_section.isVisible()
    assert window.detail_text.toPlainText() == "제공된 전체 답변"
    assert not window.evidence_section.isVisible()
    assert not window.evidence_toggle.isVisible()
    assert not window.copy_source_button.isVisible()


def test_unavailable_answer_guidance_only_names_available_management_actions(search):
    """답변 미지원 안내는 현재 사용할 수 있는 최근 기록·문서 가져오기로 연결한다."""
    window, requests, _ = search
    window.query.setText(QUERY)
    window.submit()
    window.receive_result(requests[-1][0], CompactAnswer("unavailable"))
    message = window.status.text()
    assert "준비 중" in message
    assert "최근 기록" in message
    assert "문서 가져오기" in message
    assert "조건 검색" not in message
