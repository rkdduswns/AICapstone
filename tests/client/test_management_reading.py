"""관리 화면의 공간 배분과 받은 최근 기록 안의 필터·선택 연결을 검증한다."""

from dataclasses import replace

import pytest
from PySide6.QtWidgets import QApplication

from client.recent_records import RecentRecordsWidget
from client.window import MainWindow
from shared.browser import BrowserPage
from shared.document import LocalDocument
from shared.records import ContextRecord


@pytest.fixture(scope="module")
def app():
    """네트워크를 시작하지 않고 같은 Qt 이벤트 루프에서 배치를 확인한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


@pytest.fixture
def records():
    """제목·프로그램·웹·문서 출처가 서로 다른 세 기록을 제공한다."""
    first = ContextRecord(
        "11", "문서 편집기", "writer.exe", "가상 초안",
        "2026-11-14T10:00:00+09:00", "2026-11-14T10:02:00+09:00", 1000, 1,
    )
    return [first, replace(first, id="12", application="Chrome", process_name="chrome.exe",
                           window_title="가상 조사", browser=BrowserPage(
                               "chrome", "연구 자료", "https://example.com/research")),
            replace(first, id="13", application="PDF 뷰어", process_name="reader.exe",
                    window_title="가상 보고서", document=LocalDocument(
                        r"C:\가상 자료\회의록.pdf", "pdf"))]


@pytest.fixture
def widget(app, records):
    """이미 받은 목록을 주입하고 종료 시 모든 상세 요청을 정리한다."""
    instance = RecentRecordsWidget(9)
    instance.set_connected(True)
    instance._show_records(records)
    instance.resize(620, 740)
    instance.show()
    app.processEvents()
    try:
        yield instance
    finally:
        instance.set_connected(False)
        instance.close()
        app.processEvents()


@pytest.mark.parametrize("query,expected", [
    ("초안", ["11"]), ("CHROME", ["12"]), ("writer.exe", ["11"]),
    ("연구 자료", ["12"]), ("example.com", ["12"]), ("회의록.pdf", ["13"]),
])
def test_filter_only_hides_received_rows_without_rewriting_identity(widget, query, expected):
    """필터는 표시만 바꾸며 서버 순서·실제 행 번호·기록 객체를 그대로 둔다."""
    original = list(widget.records)
    widget.filter_edit.setText(query)
    visible = [record.id for row, record in enumerate(widget.records)
               if not widget.table.isRowHidden(row)]
    assert visible == expected and widget.records == original
    assert widget.table.rowCount() == 3
    assert "불러온 3건 중 1건" in widget.status.text()
    assert "현재 목록" in widget.status.text()
    requested = []
    widget.document_requested.connect(requested.append)
    widget.attach_button.click()
    assert [record.id for record in requested] == expected


def test_no_match_clears_details_and_hidden_record_cannot_be_attached(widget):
    """일치 항목이 없거나 숨은 행을 강제로 선택해도 옛 본문·연결 동작이 남지 않는다."""
    widget.filter_edit.setText("없는 자료")
    assert "0건" in widget.status.text()
    assert not widget.detail.toPlainText() and not widget.attach_button.isEnabled()
    assert widget.web_content.record_id is None and widget.document_content.record_id is None
    requested = []
    widget.document_requested.connect(requested.append)
    widget.table.selectRow(0)
    widget._attach_document()
    assert requested == [] and not widget.attach_button.isEnabled()
    widget.filter_edit.clear()
    assert not widget.table.isRowHidden(0) and widget.attach_button.isEnabled()
    assert "초안" in widget.detail.toPlainText()


def test_refresh_restores_visible_selected_id_and_keeps_filter(widget, records, monkeypatch):
    """목록 갱신으로 행 순서가 달라져도 받은 기록의 ID로 선택과 필터를 복원한다."""
    widget.filter_edit.setText("가상")
    widget.table.selectRow(2)
    refreshed = []
    monkeypatch.setattr(widget.client, "refresh", lambda: refreshed.append(True))
    widget.refresh()
    widget._show_records([records[2], records[0], records[1]])
    assert refreshed == [True] and widget.filter_edit.text() == "가상"
    assert widget.records[widget.table.currentRow()].id == "13"
    assert "회의록.pdf" in widget.detail.toPlainText()


def test_filter_does_not_turn_failed_refresh_into_successful_empty_list(widget):
    """수신 실패 후 필터 편집이 실패 안내를 빈 결과의 정상 조회처럼 바꾸지 않는다."""
    widget._show_error("조회 실패 — 다시 확인해 주세요.")
    widget.filter_edit.setText("가상")
    assert widget.status.text() == "조회 실패 — 다시 확인해 주세요."
    assert not widget.loaded and not widget.attach_button.isEnabled()


def test_splitter_gives_body_more_space_and_narrow_view_keeps_source_in_detail(app, widget):
    """본문 높이는 옛 고정 상한을 넘고 좁은 목록의 원본 경로는 상세에 보존된다."""
    widget.resize(620, 900)
    app.processEvents()
    widget.reading_splitter.setSizes([140, 600])
    app.processEvents()
    assert widget.detail_tabs.height() > 260
    assert widget.table.isColumnHidden(4)
    widget.table.selectRow(2)
    assert widget.table.item(2, 4).text() == r"C:\가상 자료\회의록.pdf"
    assert r"C:\가상 자료\회의록.pdf" in widget.detail.toPlainText()
    widget.resize(840, 900)
    app.processEvents()
    assert not widget.table.isColumnHidden(4)


def test_connection_details_fold_without_hiding_status_or_privacy_and_tab_policy(app):
    """상태·일시정지는 상시 보이고 지원하지 않는 조건 탭은 실행 정책에 따라 숨긴다."""
    window = MainWindow(9, show_condition_search=False)
    window.show()
    app.processEvents()
    try:
        assert window.status.isVisible() and window.button.isVisible()
        assert window.privacy.summary.isVisible() and window.privacy.toggle.isVisible()
        assert not window.connection_details.isVisible()
        assert not window.tabs.isTabVisible(window.tabs.indexOf(window.search))
        window.connection_details_button.click()
        app.processEvents()
        assert window.checked_at.isVisible()
        window.connection_details_button.click()
        assert not window.connection_details.isVisible()
    finally:
        window.close()
        app.processEvents()
    preview = MainWindow(9)
    assert preview.tabs.isTabVisible(preview.tabs.indexOf(preview.search))
    preview.close()
