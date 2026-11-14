"""실제 읽기 화면에 연결한 찾기·출처 메뉴의 선택 수명과 키보드 이동을 검증한다."""

from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from client.application_window import ApplicationWindow
from client.documents_widget import DocumentsWidget
from client.recent_records import RecentRecordsWidget
from shared.browser import BrowserPage
from shared.clipboard import ClipboardEntry, RecordClipboard
from shared.document import DocumentContent, ImportedDocument, LocalDocument, RecordDocumentContent
from shared.records import ContextRecord
from shared.web_content import RecordWebContent, WebContent

STAMP = "2026-11-14T10:00:00+09:00"
PAGE = BrowserPage("chrome", "가상 자료", "https://example.com/research")
FILE = LocalDocument(r"C:\가상 자료\보고서.pdf", "pdf")


@pytest.fixture(scope="module")
def app():
    """사용자 설정과 실제 서버 없이 Qt의 초점·단축키를 처리한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


def sample_records():
    """제목이 같아도 원본 연결이 다른 실제 ID 세 개를 만든다."""
    first = ContextRecord("7", "Chrome", "chrome.exe", "가상 자료", STAMP, STAMP, 1000, 1,
                          PAGE, None)
    return [first, replace(first, id="8", browser=None, document=FILE),
            replace(first, id="9", browser=None)]


@pytest.fixture
def recent(app, monkeypatch):
    """현재 받은 목록을 주입하고 본문 조회 횟수만 기록한다."""
    widget = RecentRecordsWidget(9)
    requests = []
    for name in ("clipboard", "web_content", "document_content"):
        monkeypatch.setattr(getattr(widget, name).client, "fetch",
                            lambda *args, channel=name: requests.append((channel, args)))
    monkeypatch.setattr(widget.client, "refresh", lambda: requests.append(("list", ())))
    widget.set_connected(True)
    widget._show_records(sample_records())
    widget.resize(620, 740)
    widget.show()
    widget.activateWindow()
    app.processEvents()
    yield widget, requests
    widget.set_connected(False)


def test_find_follows_current_detail_and_does_not_fetch_or_change_text(app, recent):
    """목록 초점의 Ctrl+F와 상세 탭 전환이 현재 본문만 찾고 별도 조회는 만들지 않는다."""
    widget, requests = recent
    original = widget.detail.toPlainText()
    QTest.keyClick(widget.table, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert widget.find_bar.isVisible()
    widget.find_bar.query.setText("가상")
    assert widget.find_bar.result_label.text() == "1/2"
    assert widget.detail.toPlainText() == original and requests == []
    widget.detail_tabs.setCurrentWidget(widget.web_content)
    widget.web_content._show_content(RecordWebContent(
        "7", WebContent(PAGE, STAMP, "😀 반복\n반복 원문 <b>그대로</b>", False),
    ))
    widget.find_bar.query.setText("반복")
    assert widget.find_bar.target is widget.web_content.text
    assert widget.find_bar.result_label.text() == "1/2"
    widget.find_bar.find_next()
    assert widget.web_content.text.textCursor().selectedText() == "반복"
    assert widget.find_bar.result_label.text() == "2/2"
    assert [name for name, _ in requests] == ["web_content"]
    widget.web_content._show_error("조회가 거부됐습니다.")
    assert widget.find_bar.result_label.text() == "0/0"
    assert not widget.find_bar.next_button.isEnabled()


@pytest.mark.parametrize("view", ["list", "timeline"])
def test_source_menu_tracks_selected_id_and_filter_clear(app, recent, monkeypatch, view):
    """원본 메뉴는 실제 선택 ID와 일치하고 필터로 사라진 작업을 열지 않는다."""
    widget, requests = recent
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda url: opened.append(url) or True))
    widget.view_selector.setCurrentIndex(widget.view_selector.findData(view))
    assert widget.source_actions.url == PAGE.url and widget.source_actions.file_path is None
    widget.source_actions.open_url_action.trigger()
    assert len(opened) == 1 and opened[0].toString() == PAGE.url
    widget.filter_edit.setText("없는 자료")
    assert not widget.source_actions.isEnabled() and widget.source_actions.url is None
    widget.source_actions.open_url_action.trigger()
    assert len(opened) == 1
    widget.filter_edit.clear()
    widget.table.selectRow(1)
    assert widget.source_actions.url is None and widget.source_actions.file_path == FILE.file_path
    widget.table.selectRow(2)
    assert not widget.source_actions.isEnabled()
    assert requests == []


def test_refresh_failure_and_reconnect_clear_source_and_find_positions(recent):
    """이전 목록을 지우는 모든 경계에서 출처와 찾기 좌표도 사용할 수 없게 된다."""
    widget, requests = recent
    widget.find_bar.open()
    widget.find_bar.query.setText("가상")
    widget.refresh()
    assert widget.source_actions.url is None and not widget.source_actions.isEnabled()
    assert widget.find_bar.result_label.text() == "0/0" and requests == [("list", ())]
    widget._show_error("응답을 확인하지 못했습니다.")
    widget._show_records(sample_records())
    assert widget.source_actions.url == PAGE.url
    widget.set_connected(False)
    assert widget.source_actions.url is None and widget.find_bar.result_label.text() == "0/0"


def test_timeline_heading_clears_source_action_target(recent):
    """날짜 머리글은 원본 열기·문서 연결의 실제 기록 대상이 아니다."""
    widget, _ = recent
    widget.view_selector.setCurrentIndex(widget.view_selector.findData("timeline"))
    widget.timeline.setCurrentItem(widget.timeline.topLevelItem(0))
    assert not widget.source_actions.isEnabled() and widget.source_actions.url is None
    assert not widget.attach_button.isEnabled()


def test_documents_find_and_source_follow_linked_original_only(app, monkeypatch):
    """연결 없는 문서에서 경로를 추정하지 않으며 갱신/실패 중에는 옛 파일을 열지 않는다."""
    widget = DocumentsWidget(9)
    requests = []
    monkeypatch.setattr(widget.client, "refresh", lambda: requests.append("list"))
    widget.set_connected(True)
    widget._show_rows([
        ImportedDocument(1, "보고서.pdf", "pdf", STAMP, "반복\n반복", "8", FILE.file_path),
        ImportedDocument(2, "보고서.pdf", "pdf", STAMP, "다른 문서"),
    ])
    widget.show()
    app.processEvents()
    assert widget.source_actions.file_path == FILE.file_path
    widget.find_bar.open()
    widget.find_bar.query.setText("반복")
    assert widget.find_bar.result_label.text() == "1/2" and requests == []
    widget.records.setCurrentRow(1)
    assert not widget.source_actions.isEnabled() and widget.find_bar.result_label.text() == "0/0"
    widget.records.setCurrentRow(0)
    widget.refresh()
    assert not widget.source_actions.isEnabled() and widget.source_actions.file_path is None
    widget._failed("문서 응답을 확인하지 못했습니다.")
    assert widget.find_bar.result_label.text() == "0/0" and requests == ["list"]


def test_find_escape_closes_find_before_leaving_management(app):
    """열린 찾기의 Esc 한 번은 관리 화면을 유지하고 다음 Esc가 검색으로 돌아간다."""
    shell = ApplicationWindow(9)
    recent = shell.management.recent
    recent.set_connected(True)
    recent._show_records(sample_records())
    shell.show()
    shell.show_management(shell.management.tabs.indexOf(recent))
    shell.activateWindow()
    recent.table.setFocus()
    app.processEvents()
    QTest.keyClick(recent.table, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    app.processEvents()
    assert recent.find_bar.isVisible() and shell._management_open
    recent.detail.setFocus()
    QTest.keyClick(recent.detail, Qt.Key.Key_Escape)
    app.processEvents()
    assert not recent.find_bar.isVisible() and shell._management_open
    QTest.keyClick(recent.detail, Qt.Key.Key_Escape)
    app.processEvents()
    assert not shell._management_open
    shell.close()


def test_reading_style_keeps_web_document_and_clipboard_originals(app, recent):
    """공통 여백·행간을 적용해도 HTML 모양·이모지·공백을 포함한 원문은 같다."""
    widget, _ = recent
    record = replace(sample_records()[0], document=FILE)
    raw = "  😀 <b>원문</b>\n둘째 줄\n"
    widget._show_records([record])
    widget.web_content._show_content(RecordWebContent("7", WebContent(PAGE, STAMP, raw, True)))
    widget.document_content._show_content(RecordDocumentContent(
        "7", DocumentContent(FILE, STAMP, raw, True),
    ))
    widget.clipboard._show_entries(RecordClipboard("7", [ClipboardEntry("1", STAMP, raw)], False))
    for editor in (widget.web_content.text, widget.document_content.text, widget.clipboard.text):
        assert editor.toPlainText() == raw and editor.isReadOnly()
        assert editor.property("uiRole") == "reading"
        assert editor.document().documentMargin() == 8
