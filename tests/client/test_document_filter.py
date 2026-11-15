"""받은 문서 목록의 빠른 필터가 원본 ID·선택·읽기·전송 경계를 보존하는지 검증한다."""

from pathlib import PureWindowsPath

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

import client.documents_widget as widget_module
from shared.document import ImportedDocument

STAMP = "2026-11-16T10:00:00+09:00"


class FakeClient(QObject):
    """서버 응답 시점을 직접 제어하고 숨은 조회·재전송이 없는지 기록한다."""

    documents_received = Signal(object)
    document_uploaded = Signal(object)
    documents_failed = Signal(str)
    upload_started = Signal(str, object)
    upload_progress = Signal(object, object)

    def __init__(self, _port, parent=None):
        """사용자 파일과 네트워크에 접근하지 않는 실제 UI 신호만 제공한다."""
        super().__init__(parent)
        self.reads = 0
        self.uploads = []

    def refresh(self):
        """GET 요청 횟수만 세고 응답은 각 검증에서 명시적으로 전달한다."""
        self.reads += 1

    def upload(self, path, record_id, source_path):
        """파일을 열지 않고 기존 전송 시작 신호를 전달한다."""
        self.uploads.append((path, record_id, source_path))
        self.upload_started.emit(PureWindowsPath(path).name, 123)

    def close(self):
        """가상 요청에는 정리할 외부 자원이 없다."""


@pytest.fixture(scope="module")
def app():
    """읽기 전용 화면의 배치·초점·스크롤을 같은 Qt 이벤트 루프에서 확인한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


@pytest.fixture
def documents():
    """파일명이 같아도 작업·경로·실제 문서 ID가 서로 다른 자료를 만든다."""
    long_text = "본문에서만_나타나는_검색어\n" + "반복 가상 본문 · 원문을 보존합니다.\n" * 180
    return [
        ImportedDocument(11, "자료.PDF", "pdf", STAMP, long_text, "7",
                         r"C:\가상 자료\프로젝트A\자료.PDF"),
        ImportedDocument(12, "자료.PDF", "pdf", STAMP, long_text, "8",
                         r"D:\보관\자료.PDF"),
        ImportedDocument(13, "회의록.docx", "docx", STAMP, "연결 없는 회의록 본문"),
    ]


@pytest.fixture
def widget(app, documents, monkeypatch):
    """실제 문서 위젯만 사용하며 사용자 설정·원본 파일·기본 앱은 사용하지 않는다."""
    monkeypatch.setattr(widget_module, "DocumentsClient", FakeClient)
    instance = widget_module.DocumentsWidget(9)
    instance.resize(620, 680)
    instance.show()
    instance.set_connected(True)
    instance.client.documents_received.emit(documents)
    app.processEvents()
    yield instance
    instance.close()
    app.processEvents()


def visible_ids(widget):
    """숨김 상태만 읽어 서버 순서의 실제 문서 ID를 반환한다."""
    return [row.id for index, row in enumerate(widget.rows)
            if not widget.records.item(index).isHidden()]


def selected_id(widget):
    """현재 행 포인터가 아닌 실제 보이는 선택을 검증한다."""
    index = widget._selected_document_row()
    return widget.rows[index].id if index >= 0 else None


@pytest.mark.parametrize("query,expected", [
    ("자료.pdf", [11, 12]), ("프로젝트a", [11]), (r"d:\보관", [12]),
    ("#7", [11]), ("8", [12]), ("회의록", [13]), ("본문에서만_나타나는_검색어", []),
])
def test_filter_matches_received_metadata_only_without_requests(widget, documents, query, expected):
    """파일명·확인 경로·연결 ID만 찾고 본문이나 서버 전체 검색으로 확대하지 않는다."""
    widget.filter_edit.setText(query)
    assert visible_ids(widget) == expected
    assert widget.rows == documents and all(a is b for a, b in zip(widget.rows, documents, strict=True))
    assert widget.records.count() == len(documents)
    assert "20" in widget.filter_edit.placeholderText()
    assert widget.client.reads == 0 and widget.client.uploads == []


def test_file_type_and_text_conditions_preserve_server_order(widget, documents):
    """두 필터는 AND로 적용하며 같은 이름의 서로 다른 문서를 합치거나 다시 정렬하지 않는다."""
    widget.type_filter.setCurrentIndex(widget.type_filter.findData("pdf"))
    assert visible_ids(widget) == [11, 12]
    widget.filter_edit.setText("자료")
    widget.type_filter.setCurrentIndex(widget.type_filter.findData("docx"))
    assert visible_ids(widget) == [] and selected_id(widget) is None
    widget.filter_edit.clear()
    assert visible_ids(widget) == [13] and selected_id(widget) == 13
    widget.type_filter.setCurrentIndex(widget.type_filter.findData("all"))
    assert visible_ids(widget) == [11, 12, 13] and selected_id(widget) == 13
    assert widget.rows == documents and widget.client.reads == 0


def test_visible_selection_keeps_scroll_text_selection_and_find_state(app, widget, monkeypatch):
    """선택한 문서가 계속 보이면 필터 편집만으로 읽던 본문과 찾기 위치를 다시 그리지 않는다."""
    widget.records.setCurrentRow(1)
    widget.find_bar.open()
    widget.find_bar.query.setText("반복")
    widget.find_bar.find_next()
    app.processEvents()
    widget.content.verticalScrollBar().setValue(40)
    cursor = widget.content.textCursor()
    before = (widget.content.toPlainText(), cursor.selectionStart(), cursor.selectionEnd(),
              widget.content.verticalScrollBar().value(), widget.find_bar.result_label.text())
    rendered = []
    monkeypatch.setattr(widget_module, "set_reading_text", lambda *_args: rendered.append(True))
    widget.filter_edit.setText("자료")
    app.processEvents()
    cursor = widget.content.textCursor()
    after = (widget.content.toPlainText(), cursor.selectionStart(), cursor.selectionEnd(),
             widget.content.verticalScrollBar().value(), widget.find_bar.result_label.text())
    assert selected_id(widget) == 12 and before == after and rendered == []
    assert widget.source_actions.file_path == r"D:\보관\자료.PDF"
    assert widget.client.reads == 0 and widget.client.uploads == []


def test_zero_matches_clear_body_find_source_and_reject_forced_hidden_row(widget):
    """필터 밖의 currentRow를 강제로 바꿔도 옛 파일 메뉴와 본문이 부활하지 않는다."""
    widget.find_bar.open()
    widget.find_bar.query.setText("반복")
    assert widget.find_bar.next_button.isEnabled()
    widget.filter_edit.setText("없는 파일")
    assert visible_ids(widget) == [] and selected_id(widget) is None
    assert not widget.content.toPlainText() and not widget.source_actions.isEnabled()
    assert widget.find_bar.result_label.text() == "0/0"
    assert "필터" in widget.guidance.text() and not widget.guidance.isHidden()
    widget.records.setCurrentRow(0)
    widget._select(0)
    assert selected_id(widget) is None and not widget.content.toPlainText()
    assert widget.source_actions.file_path is None and not widget.source_actions.isEnabled()
    widget.filter_edit.clear()
    assert visible_ids(widget) == [11, 12, 13] and selected_id(widget) == 11
    assert widget.client.reads == 0 and widget.client.uploads == []


def test_selection_clear_invalidates_current_pointer_without_filter_change(widget):
    """선택 해제 뒤 남는 행 포인터만으로 원본 열기와 본문을 복구하지 않는다."""
    widget.records.setCurrentRow(1)
    pointer = widget.records.currentRow()
    widget.records.clearSelection()
    widget._select(pointer)
    assert selected_id(widget) is None
    assert widget.source_actions.file_path is None and not widget.content.toPlainText()


def test_refresh_restores_visible_document_id_across_reordering(widget, documents):
    """목록 갱신은 보이는 실제 문서 ID를 복원하며 사라지면 첫 보이는 문서로 이동한다."""
    widget.filter_edit.setText("자료")
    widget.records.setCurrentRow(1)
    widget.refresh()
    widget.client.documents_received.emit([documents[2], documents[1], documents[0]])
    assert selected_id(widget) == 12 and widget.filter_edit.text() == "자료"
    widget.refresh()
    widget.client.documents_received.emit([documents[2], documents[0]])
    assert selected_id(widget) == 11 and visible_ids(widget) == [11]
    assert widget.client.reads == 2 and widget.client.uploads == []


def test_uploaded_document_outside_filter_keeps_success_and_filters(widget, documents):
    """숨겨진 업로드 결과도 저장 성공을 유지하되 필터를 지우거나 숨은 문서를 선택하지 않는다."""
    widget.type_filter.setCurrentIndex(widget.type_filter.findData("pdf"))
    widget.upload("unused.docx")
    uploaded = ImportedDocument(14, "새 문서.docx", "docx", STAMP, "새 문서 본문")
    widget.client.document_uploaded.emit(uploaded)
    widget.client.documents_received.emit([uploaded, *documents])
    assert "가져오기 완료" in widget.completion.text() and not widget.completion.isHidden()
    explanation = " ".join(label.text() for label in (widget.completion, widget.guidance)
                           if not label.isHidden())
    assert "필터" in explanation and "숨" in explanation
    assert widget.type_filter.currentData() == "pdf" and visible_ids(widget) == [11, 12]
    assert selected_id(widget) == 11 and not widget.records.item(0).isSelected()
    assert widget.client.reads == 1 and len(widget.client.uploads) == 1
    widget.type_filter.setCurrentIndex(widget.type_filter.findData("all"))
    assert 14 in visible_ids(widget) and not widget.completion.isHidden()


def test_uploaded_document_matching_filter_is_selected_by_id(widget, documents):
    """완료 문서가 필터에 맞으면 다른 행 번호나 같은 파일명 대신 실제 완료 ID를 선택한다."""
    widget.type_filter.setCurrentIndex(widget.type_filter.findData("pdf"))
    widget.filter_edit.setText("새 문서")
    widget.upload("unused.pdf")
    uploaded = ImportedDocument(14, "새 문서.pdf", "pdf", STAMP, "완료 문서 본문")
    widget.client.document_uploaded.emit(uploaded)
    widget.client.documents_received.emit([*documents, uploaded])
    assert selected_id(widget) == 14 and widget.content.toPlainText() == uploaded.extracted_text
    assert widget.filter_edit.text() == "새 문서" and widget.type_filter.currentData() == "pdf"
    assert widget.client.reads == 1 and len(widget.client.uploads) == 1


@pytest.mark.parametrize("transition", ["read", "upload", "denied", "disconnect"])
def test_pending_or_failed_state_is_not_replaced_by_programmatic_filter_edits(widget, transition):
    """로딩·전송·403·연결 해제 중 필터 입력이 정상 빈 목록이나 새 쓰기 요청으로 바뀌지 않는다."""
    if transition == "read":
        widget.refresh()
    elif transition == "upload":
        widget.upload("unused.docx")
        widget.client.upload_progress.emit(100, 100)
    elif transition == "denied":
        widget.client.documents_failed.emit("문서 목록 조회가 거부됐습니다.")
    else:
        widget.set_connected(False)
    notice = widget.notice.text()
    counts = widget.client.reads, len(widget.client.uploads)
    widget.filter_edit.setText("없는 자료")
    widget.type_filter.setCurrentIndex(widget.type_filter.findData("docx"))
    assert widget.notice.text() == notice
    assert (widget.client.reads, len(widget.client.uploads)) == counts
    assert not widget.source_actions.isEnabled()
    if transition in {"read", "upload"}:
        assert widget.busy and not widget.filter_edit.isEnabled() and not widget.type_filter.isEnabled()


def test_filters_remain_memory_only_across_reconnect_and_new_widget(widget, documents):
    """같은 화면의 입력은 유지하지만 새 화면은 사용자의 파일명·경로 필터를 복원하지 않는다."""
    widget.filter_edit.setText("자료")
    widget.type_filter.setCurrentIndex(widget.type_filter.findData("pdf"))
    widget.set_connected(False)
    widget.set_connected(True)
    widget.client.documents_received.emit(documents)
    assert widget.filter_edit.text() == "자료" and widget.type_filter.currentData() == "pdf"
    assert visible_ids(widget) == [11, 12]
    fresh = widget_module.DocumentsWidget(9)
    try:
        assert fresh.filter_edit.text() == "" and fresh.type_filter.currentData() == "all"
    finally:
        fresh.close()
