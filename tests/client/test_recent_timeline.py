"""현재 받은 기록의 날짜별 표시와 실제 ID 기반 선택을 검증한다."""

from collections import OrderedDict
from dataclasses import replace
from datetime import datetime

import pytest
from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from client.recent_records import RecentRecordsWidget
from shared.browser import BrowserPage
from shared.document import LocalDocument
from shared.records import ContextRecord
from shared.web_content import RecordWebContent, WebContent

ROLE = Qt.ItemDataRole.UserRole
PAGE = BrowserPage("chrome", "가상 연구 자료", "https://example.com/research")


@pytest.fixture(scope="module")
def app():
    """실제 창을 제어하는 같은 Qt 이벤트 루프를 사용한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


@pytest.fixture
def records():
    """문자 날짜와 실제 현지 날짜가 다른 시각·동률·같은 제목의 기록을 준비한다."""
    first = ContextRecord(
        "12", "Chrome", "chrome.exe", "가상 같은 제목",
        "2026-11-12T00:00:00+00:00", "2026-11-13T23:30:00-12:00", 600_000, 1,
        browser=PAGE,
    )
    return [
        first,
        replace(first, id="2", application="문서 편집기", process_name="writer.exe",
                started_at="2026-11-14T20:20:00+09:00", last_active_at="2026-11-14T20:30:00+09:00",
                browser=None, document=LocalDocument(r"C:\가상 자료\회의록.pdf", "pdf")),
        replace(first, id="11", started_at="2026-11-14T00:10:00+14:00",
                last_active_at="2026-11-14T00:20:00+14:00", window_title="이전 가상 조사"),
        replace(first, id="14", started_at="2026-11-12T09:00:00+00:00",
                last_active_at="2026-11-12T10:00:00+00:00", window_title="오래된 가상 보고서"),
    ]


@pytest.fixture
def widget(app, records):
    """이미 받은 가상 기록만 표시하고 네트워크·OS 감지는 시작하지 않는다."""
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


def show_timeline(widget, app):
    """공개 보기 선택을 사용하고 배치가 완료된 트리를 반환한다."""
    index = widget.view_selector.findData("timeline")
    assert index >= 0
    widget.view_selector.setCurrentIndex(index)
    app.processEvents()
    assert widget.record_views.currentWidget() is widget.timeline
    return widget.timeline


def timeline_items(tree):
    """날짜 머리글 아래의 실제 기록 항목만 표시 순서대로 읽는다."""
    return [tree.topLevelItem(group).child(row)
            for group in range(tree.topLevelItemCount())
            for row in range(tree.topLevelItem(group).childCount())]


def timeline_ids(tree):
    """표시 문자열을 해석하지 않고 실제 저장 ID를 읽는다."""
    return [item.data(0, ROLE) for item in timeline_items(tree)]


def select_id(tree, identifier):
    """같은 제목이 반복돼도 실제 ID로 선택할 항목을 찾는다."""
    tree.setCurrentItem(next(item for item in timeline_items(tree)
                             if item.data(0, ROLE) == identifier))


def test_grouping_uses_last_active_local_date_and_keeps_received_order(app, widget, records):
    """시각의 오프셋을 반영하며 동률 기록의 서버 순서와 날짜별 제한된 건수를 유지한다."""
    tree = show_timeline(widget, app)
    expected = OrderedDict()
    for record in records:
        date = datetime.fromisoformat(record.last_active_at).astimezone().date().isoformat()
        expected.setdefault(date, []).append(record.id)
    assert tree.topLevelItemCount() == len(expected)
    for index, (date, identifiers) in enumerate(expected.items()):
        header = tree.topLevelItem(index)
        heading = " ".join(header.text(column) for column in range(tree.columnCount()))
        assert date in heading and str(len(identifiers)) in heading
        assert "현재" in heading
        assert header.data(0, ROLE) is None
        assert not header.flags() & Qt.ItemFlag.ItemIsSelectable
        assert header.isExpanded()
        assert [header.child(row).data(0, ROLE) for row in range(header.childCount())] == identifiers
    assert timeline_ids(tree) == [record.id for record in records]
    assert not tree.itemsExpandable() and not tree.rootIsDecorated()


def test_view_switch_preserves_selected_id_filter_and_loaded_body_without_refresh(
    app, widget, monkeypatch,
):
    """날짜별 보기 전환은 같은 본문을 다시 조회하거나 선택 작업을 바꾸지 않는다."""
    requests = []
    monkeypatch.setattr(widget.client, "refresh", lambda: requests.append("list"))
    monkeypatch.setattr(widget.web_content.client, "fetch", lambda *args: requests.append("body"))
    widget.filter_edit.setText("가상")
    widget.table.selectRow(0)
    widget.detail_tabs.setCurrentWidget(widget.web_content)
    widget.web_content._show_content(RecordWebContent(
        "12", WebContent(PAGE, "2026-11-14T12:00:00+00:00", "현재 선택의 저장 본문\n" * 150, False)))
    app.processEvents()
    editor = widget.web_content.text
    cursor = editor.textCursor()
    cursor.setPosition(8)
    cursor.setPosition(15, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    editor.verticalScrollBar().setValue(editor.verticalScrollBar().maximum() // 2)
    reading = (editor.textCursor().position(), editor.textCursor().anchor(),
               editor.verticalScrollBar().value())
    before = list(requests)
    tree = show_timeline(widget, app)
    assert tree.currentItem().data(0, ROLE) == "12"
    assert editor.toPlainText() == "현재 선택의 저장 본문\n" * 150
    widget.view_selector.setCurrentIndex(widget.view_selector.findData("list"))
    app.processEvents()
    assert widget.record_views.currentWidget() is widget.table
    assert widget.records[widget.table.currentRow()].id == "12"
    assert widget.filter_edit.text() == "가상" and widget.web_content.loaded
    assert requests == before
    assert (editor.textCursor().position(), editor.textCursor().anchor(),
            editor.verticalScrollBar().value()) == reading


def test_timeline_selection_uses_id_and_document_link_reuses_same_record(app, widget):
    """같은 제목의 다른 항목은 실제 기록 객체로 상세·문서 연결을 동기화한다."""
    tree = show_timeline(widget, app)
    select_id(tree, "2")
    assert widget.records[widget.table.currentRow()].id == "2"
    assert widget.document_content.record_id == "2"
    assert "회의록.pdf" in widget.detail.toPlainText()
    linked = []
    widget.document_requested.connect(linked.append)
    widget.attach_button.click()
    assert linked == [widget.records[1]]
    widget.view_selector.setCurrentIndex(widget.view_selector.findData("list"))
    widget.table.selectRow(2)
    show_timeline(widget, app)
    assert tree.currentItem().data(0, ROLE) == "11"


def test_filter_rebuilds_both_views_and_never_connects_hidden_record(app, widget):
    """날짜별 보기의 필터 결과는 표의 보이는 실제 행과 같고 숨은 출처는 연결되지 않는다."""
    tree = show_timeline(widget, app)
    select_id(tree, "12")
    widget.filter_edit.setText("회의록.pdf")
    assert timeline_ids(tree) == ["2"]
    assert widget.table.isRowHidden(0) and not widget.table.isRowHidden(1)
    assert tree.currentItem().data(0, ROLE) == "2"
    assert "불러온 4건 중 1건" in widget.status.text()
    widget.filter_edit.setText("없는 자료")
    assert tree.topLevelItemCount() == 0
    assert not widget.detail.toPlainText() and not widget.attach_button.isEnabled()
    linked = []
    widget.document_requested.connect(linked.append)
    widget.table.selectRow(0)
    widget._attach_document()
    assert linked == []
    widget.filter_edit.clear()
    assert timeline_ids(tree) == ["12", "2", "11", "14"]


def test_date_heading_is_not_a_record_or_document_target(app, widget):
    """머리글을 강제로 현재 항목으로 지정해도 이전 기록의 연결 동작이 실행되지 않는다."""
    tree = show_timeline(widget, app)
    linked = []
    widget.document_requested.connect(linked.append)
    tree.setCurrentItem(tree.topLevelItem(0))
    widget._attach_document()
    assert linked == [] and not widget.attach_button.isEnabled()
    assert widget.web_content.record_id is None and widget.document_content.record_id is None


def test_keyboard_recovers_from_date_heading_to_real_record(app, widget):
    """날짜 머리글의 현재 위치를 유지해 아래 방향키로 실제 기록을 다시 선택할 수 있다."""
    tree = show_timeline(widget, app)
    header = tree.topLevelItem(0)
    tree.setCurrentItem(header)
    linked = []
    widget.document_requested.connect(linked.append)
    widget._attach_document()
    assert linked == [] and not widget.attach_button.isEnabled()
    widget.activateWindow()
    tree.setFocus()
    app.processEvents()
    QTest.keyClick(tree, Qt.Key.Key_Down)
    app.processEvents()
    identifier = header.child(0).data(0, ROLE)
    assert tree.currentItem().data(0, ROLE) == identifier
    assert widget.records[widget.table.currentRow()].id == identifier
    assert widget.attach_button.isEnabled()


def test_cleared_timeline_selection_cannot_use_remaining_current_pointer(app, widget):
    """날짜별 선택 해제는 이전 기록의 상세·연결 대상을 함께 정리한다."""
    tree = show_timeline(widget, app)
    select_id(tree, "2")
    linked = []
    widget.document_requested.connect(linked.append)
    tree.clearSelection()
    widget._attach_document()
    assert linked == [] and not widget.attach_button.isEnabled()
    assert not widget.detail.toPlainText() and widget.document_content.record_id is None


def test_suppressed_selection_notification_cannot_attach_current_pointer(app, widget):
    """선택 알림이 누락돼 Qt 현재 포인터가 남아도 직접 연결은 실제 선택을 다시 검사한다."""
    tree = show_timeline(widget, app)
    select_id(tree, "2")
    previous = tree.currentItem()
    linked = []
    widget.document_requested.connect(linked.append)
    blocker = QSignalBlocker(tree)
    tree.clearSelection()
    blocker.unblock()
    assert tree.currentItem() is previous and not previous.isSelected()
    widget._attach_document()
    assert linked == []


def test_refresh_clears_both_views_and_restores_selection_by_id(app, widget, records, monkeypatch):
    """새 응답에서 행 순서가 바뀌어도 날짜별 선택과 표의 실제 ID가 함께 복원된다."""
    tree = show_timeline(widget, app)
    widget.filter_edit.setText("가상")
    select_id(tree, "2")
    calls = []
    monkeypatch.setattr(widget.client, "refresh", lambda: calls.append(True))
    widget.refresh()
    assert calls == [True]
    assert widget.table.rowCount() == 0 and tree.topLevelItemCount() == 0
    assert not widget.attach_button.isEnabled() and not widget.detail.toPlainText()
    widget._show_records([records[3], records[2], records[1], records[0]])
    assert widget.records[widget.table.currentRow()].id == "2"
    assert tree.currentItem().data(0, ROLE) == "2"
    assert widget.filter_edit.text() == "가상"


@pytest.mark.parametrize("reset", ["error", "disconnect", "reconnect"])
def test_reset_and_late_body_never_restore_old_timeline(app, widget, reset):
    """오류·재연결 뒤 늦은 상세가 도착해도 과거 항목·본문·연결 대상이 남지 않는다."""
    tree = show_timeline(widget, app)
    if reset == "error":
        widget._show_error("조회 실패 — 다시 확인해 주세요.")
    else:
        widget.set_connected(reset == "reconnect")
    widget.web_content._show_content(RecordWebContent(
        "12", WebContent(PAGE, "2026-11-14T12:00:00+00:00", "늦은 옛 본문", False)))
    assert widget.table.rowCount() == 0 and tree.topLevelItemCount() == 0
    assert not widget.detail.toPlainText() and not widget.web_content.text.toPlainText()
    assert not widget.attach_button.isEnabled() and not widget.loaded
    previous = widget.status.text()
    widget.filter_edit.setText("변경한 필터")
    assert widget.status.text() == previous


def test_empty_result_has_no_date_headers_or_previous_identity(app, widget):
    """정상 빈 결과는 머리글·이전 상세 없이 표시하고 서버 세션을 만들어내지 않는다."""
    tree = show_timeline(widget, app)
    widget._show_records([])
    assert tree.topLevelItemCount() == 0 and widget.table.rowCount() == 0
    assert "없습니다" in widget.status.text()
    assert not widget.attach_button.isEnabled() and widget.document_content.record_id is None


def test_keyboard_and_long_plain_title_remain_available_in_small_view(app, widget, records):
    """작은 읽기 영역에서도 키보드로 실제 항목을 고르고 긴 제목 원문을 확인한다."""
    title = "<b>실행하지 않는 가상 제목</b> " + "긴 제목 " * 50
    widget._show_records([replace(record, window_title=title) for record in records])
    widget.resize(360, 460)
    tree = show_timeline(widget, app)
    select_id(tree, "12")
    widget.activateWindow()
    tree.setFocus()
    app.processEvents()
    QTest.keyClick(tree, Qt.Key.Key_Down)
    app.processEvents()
    assert tree.currentItem().data(0, ROLE) == "2"
    assert widget.records[widget.table.currentRow()].id == "2"
    assert title in widget.detail.toPlainText()
    assert widget.view_selector.isVisible() and tree.viewport().height() > 0
