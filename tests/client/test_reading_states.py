"""읽기 화면의 빈 결과·조회 실패·복구 안내가 다른 작업이나 저장 재시도로 섞이지 않는지 검증한다."""

from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from client.clipboard_widget import ClipboardWidget
from client.document_content_widget import DocumentContentWidget
from client.documents_widget import DocumentsWidget
from client.recent_records import RecentRecordsWidget
from client.web_content_widget import WebContentWidget
from shared.browser import BrowserPage
from shared.clipboard import ClipboardEntry, RecordClipboard
from shared.document import (
    DocumentContent,
    ImportedDocument,
    LocalDocument,
    RecordDocumentContent,
)
from shared.records import ContextRecord
from shared.web_content import RecordWebContent, WebContent

STAMP = "2026-11-14T10:00:00+09:00"
PAGE = BrowserPage("chrome", "가상 웹 자료", "https://example.com/research")
DOCUMENT = LocalDocument(r"C:\가상 자료\보고서.pdf", "pdf")


@pytest.fixture(scope="module")
def app():
    """서버나 사용자 파일 없이 실제 Qt 위젯과 신호로 상태를 전환한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


def record():
    """본문 출처와 실제 선택 ID를 갖는 가상 기록을 준비한다."""
    return ContextRecord("7", "가상 편집기", "writer.exe", "가상 보고서", STAMP, STAMP,
                         1000, 1, PAGE, DOCUMENT)


@pytest.mark.parametrize("view", ["list", "timeline"])
def test_record_filter_empty_recovery_keeps_real_selection_without_requests(app, monkeypatch, view):
    """필터 0건은 저장 이력 없음과 구분하며 필터 해제는 조회 없이 같은 실제 작업을 복원한다."""
    widget = RecentRecordsWidget(9)
    requests = []
    monkeypatch.setattr(widget.client, "refresh", lambda: requests.append("list"))
    widget.set_connected(True)
    widget._show_records([record()])
    widget.view_selector.setCurrentIndex(widget.view_selector.findData(view))
    widget.filter_edit.setText("일치하지 않는 제목")
    assert "0건" in widget.status.text() and "없습니다" not in widget.status.text()
    assert "필터" in widget.guidance.text() and not widget.guidance.isHidden()
    assert not widget.attach_button.isEnabled() and not widget.detail.toPlainText()
    widget.filter_edit.clear()
    assert widget._selected_table_row() == 0
    assert widget.attach_button.isEnabled() and widget.guidance.isHidden()
    assert requests == []
    widget._show_records([])
    assert widget.status.text() == "저장된 작업 기록이 없습니다."
    assert "기록 상태" in widget.guidance.text() and widget.loaded
    assert widget.button.isEnabled() and not widget.attach_button.isEnabled()


def test_record_failure_keeps_reason_and_manual_read_recovery(app, monkeypatch):
    """실패의 원인은 빈 목록 안내로 바뀌지 않고 사용자의 새로고침만 조회를 만든다."""
    widget = RecentRecordsWidget(9)
    requests = []
    monkeypatch.setattr(widget.client, "refresh", lambda: requests.append("list"))
    widget.set_connected(True)
    widget._show_records([record()])
    widget._show_error("기능 준비 중 — 서버 미지원")
    assert widget.status.text() == "기능 준비 중 — 서버 미지원"
    assert widget.records == [] and not widget.loaded
    assert not widget.guidance.isHidden() and requests == []
    widget.filter_edit.setText("다른 필터")
    assert widget.status.text() == "기능 준비 중 — 서버 미지원"
    widget.button.click()
    assert requests == ["list"] and widget.guidance.isHidden()
    widget.filter_edit.clear()
    widget._show_records([record()])
    assert widget.loaded and widget.guidance.isHidden()


@pytest.mark.parametrize("kind", ["web", "document"])
def test_body_missing_source_empty_failure_and_recovery_are_distinct(app, monkeypatch, kind):
    """출처 없음은 조회하지 않고 정상 빈 본문·실패를 구분한 뒤 명시적인 읽기로 복구한다."""
    widget = WebContentWidget(9) if kind == "web" else DocumentContentWidget(9)
    requests = []
    monkeypatch.setattr(widget.client, "fetch", lambda *args: requests.append(args))
    widget.set_record(replace(record(), browser=None, document=None))
    widget.refresh()
    assert not widget.button.isEnabled() and not widget.guidance.isHidden() and requests == []
    widget.set_record(record())
    widget.refresh()
    assert len(requests) == 1 and widget.guidance.isHidden()
    empty = RecordWebContent("7", None) if kind == "web" else RecordDocumentContent("7", None)
    widget._show_content(empty)
    assert widget.loaded and "없습니다" in widget.status.text()
    assert not widget.guidance.isHidden() and not widget.text.toPlainText()
    widget._show_error("조회가 허용되지 않습니다.")
    assert not widget.loaded and "허용되지" in widget.status.text()
    assert "없습니다" not in widget.status.text() and len(requests) == 1
    assert widget.source.toPlainText() == widget.text.toPlainText() == ""
    widget.button.click()
    assert len(requests) == 2 and widget.guidance.isHidden()
    content = (WebContent(PAGE, STAMP, "가상 웹 본문", False) if kind == "web" else
               DocumentContent(DOCUMENT, STAMP, "가상 문서 본문", False))
    widget._show_content(replace(empty, content=content))
    assert widget.loaded and widget.guidance.isHidden()
    assert widget.text.toPlainText() == content.text
    assert widget.guidance.textFormat() == Qt.TextFormat.PlainText


def test_clipboard_empty_denied_and_recovered_without_new_collection(app, monkeypatch):
    """빈 복사 항목 안내와 거부를 구분하고 조회 버튼은 저장된 항목만 요청한다."""
    widget = ClipboardWidget(9)
    reads = []
    monkeypatch.setattr(widget.client, "fetch", reads.append)
    widget.set_record("7")
    widget._show_entries(RecordClipboard("7", [], False))
    assert widget.loaded and "없습니다" in widget.status.text()
    assert "개인정보 설정" in widget.guidance.text()
    widget._show_error("조회가 허용되지 않습니다.")
    assert not widget.loaded and "없습니다" not in widget.status.text() and reads == []
    widget.button.click()
    assert reads == ["7"] and widget.guidance.isHidden()
    widget._show_entries(RecordClipboard("7", [ClipboardEntry("1", STAMP, "가상 복사")], False))
    assert widget.guidance.isHidden() and widget.text.toPlainText() == "가상 복사"


def test_document_selection_clears_previous_partial_display_notice(app):
    """긴 문서에서 짧은 문서로 이동하면 과거 일부 표시 경고가 남지 않는다."""
    widget = DocumentsWidget(9)
    widget.set_connected(True)
    long = ImportedDocument(1, "long.pdf", "pdf", STAMP, "가" * 50_001)
    short = ImportedDocument(2, "short.pdf", "pdf", STAMP, "짧은 가상 본문")
    widget._show_rows([long, short])
    assert "50,000자" in widget.notice.text()
    widget.records.setCurrentRow(1)
    assert "50,000자" not in widget.notice.text()
    assert widget.content.toPlainText() == short.extracted_text
    assert widget.guidance.isHidden()


@pytest.mark.parametrize("uploading", [False, True])
def test_document_failure_preserves_reason_and_only_manual_list_read(app, monkeypatch, uploading):
    """거부·저장 미확인 안내가 자동 재전송을 유도하지 않고 조회 실패도 빈 목록과 구분한다."""
    widget = DocumentsWidget(9)
    requests, uploads = [], []
    monkeypatch.setattr(widget.client, "refresh", lambda: requests.append("list"))
    monkeypatch.setattr(widget.client, "upload", lambda *args: uploads.append(args))
    widget.set_connected(True)
    widget._show_rows([ImportedDocument(1, "old.pdf", "pdf", STAMP, "이전 본문")])
    widget._uploading = uploading
    widget._failed("문서 저장이 거부됐습니다." if uploading else "문서 목록 조회가 거부됐습니다.")
    assert "거부" in widget.notice.text() and not widget.loaded
    assert not widget.content.toPlainText() and widget.rows == []
    assert not widget.guidance.isHidden() and requests == uploads == []
    if uploading:
        assert "저장 여부" in widget.guidance.text()
    widget.refresh_button.click()
    assert requests == ["list"] and uploads == [] and widget.guidance.isHidden()
    widget._show_rows([])
    assert widget.loaded and "가져온 문서가 없습니다" in widget.guidance.text()
    assert "거부" not in widget.notice.text() and not widget.guidance.isHidden()
