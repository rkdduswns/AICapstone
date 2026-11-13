"""파일 전송과 저장 확인을 구분하고 목록 선택·진행 표시의 수명을 검증한다."""

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

import client.documents_widget as widget_module
from client.documents_client import DocumentsClient
from shared.document import ImportedDocument


def document(identifier: int, *, linked: bool = False) -> ImportedDocument:
    """저장 완료가 확인된 가상 문서만 만들어 서버나 원본 파일을 열지 않는다."""
    return ImportedDocument(
        identifier, f"문서{identifier}.docx", "docx", "2026-11-14T00:00:00+09:00",
        f"가상 문서 {identifier} 본문", "7" if linked else None,
        rf"C:\가상 자료\문서{identifier}.docx" if linked else None,
    )


@pytest.fixture(scope="module")
def app():
    """모든 문서 화면 검증에서 같은 Qt 이벤트 루프를 사용한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


class FakeClient(QObject):
    """UI에 필요한 실제 신호만 제공하고 전송·응답 시점을 시험에서 제어한다."""

    documents_received = Signal(object)
    document_uploaded = Signal(object)
    documents_failed = Signal(str)
    upload_started = Signal(str, object)
    upload_progress = Signal(object, object)

    def __init__(self, _port, parent=None):
        """요청 횟수로 숨은 재전송과 완료 전 목록 갱신을 탐지한다."""
        super().__init__(parent)
        self.uploads = []
        self.refreshes = 0
        self.closed = 0
        self.reject = False

    def upload(self, path, record_id, source_path):
        """초기 입력 거부와 실제 전송 시작을 각각 재현한다."""
        self.uploads.append((path, record_id, source_path))
        if self.reject:
            self.documents_failed.emit("선택한 파일을 읽을 수 없습니다.")
        else:
            self.upload_started.emit("선택한 문서.docx", 1234)

    def refresh(self):
        """응답은 자동 생성하지 않아 저장 확인과 목록 확인의 경계를 검사한다."""
        self.refreshes += 1

    def close(self):
        """화면 재설정과 종료가 기존 전송 취소를 요청하는지 기록한다."""
        self.closed += 1


@pytest.fixture
def widget(app, monkeypatch):
    """전송 엔진만 가상화하고 실제 문서 위젯과 Qt 신호를 사용한다."""
    monkeypatch.setattr(widget_module, "DocumentsClient", FakeClient)
    instance = widget_module.DocumentsWidget(9)
    instance.resize(620, 600)
    instance.show()
    instance.set_connected(True)
    app.processEvents()
    try:
        yield instance
    finally:
        instance.close()
        instance.deleteLater()
        app.processEvents()


def test_transfer_wait_and_verified_success_remain_distinct(widget):
    """전송 100%는 저장 완료가 아니며 서버 성공 뒤에만 결과·연결을 표시한다."""
    linked = []
    widget.record_linked.connect(linked.append)
    widget.set_target_record(SimpleNamespace(id="7", window_title="선택한 실제 작업"))
    widget.upload("unused.docx", r"C:\가상 자료\unused.docx")
    assert widget.busy and len(widget.client.uploads) == 1
    assert "선택한 문서.docx" in widget.transfer_summary.text()
    assert "1,234바이트" in widget.transfer_summary.text()
    assert "#7" in widget.transfer_summary.text()
    assert not widget.import_button.isEnabled() and not widget.clear_target_button.isEnabled()
    widget.client.upload_progress.emit(25, 100)
    assert widget.progress.value() == 25 and widget.progress.maximum() == 100
    widget.client.upload_progress.emit(100, 100)
    assert widget.progress.maximum() == 0
    assert "서버 처리 결과 확인 중" in widget.notice.text()
    assert widget.completion.isHidden() and linked == [] and widget.client.refreshes == 0
    widget.client.document_uploaded.emit(document(2, linked=True))
    assert linked == ["7"] and widget.client.refreshes == 1
    assert "가져오기 완료" in widget.completion.text() and "#7에 연결됨" in widget.completion.text()
    assert widget.progress.isHidden() and widget.target_record_id is None
    widget.client.documents_received.emit([document(1), document(2, linked=True)])
    assert widget.records.currentRow() == 1 and not widget.busy
    assert "문서 2 본문" in widget.content.toPlainText()
    assert not widget.completion.isHidden()


def test_unknown_transfer_length_does_not_claim_server_processing(widget):
    """전송 전체 크기를 모르면 서버 처리 단계나 가짜 백분율을 표시하지 않는다."""
    widget.upload("unused.docx")
    widget.client.upload_progress.emit(0, -1)
    assert widget.progress.maximum() == 0
    assert "전송량 확인 대기" in widget.notice.text()
    assert "서버 처리" not in widget.notice.text() and widget.completion.isHidden()


def test_manual_refresh_preserves_document_id_across_reordering(widget):
    """행 번호가 바뀌어도 사용자가 읽던 실제 문서 ID를 복원한다."""
    widget.client.documents_received.emit([document(1), document(2)])
    widget.records.setCurrentRow(1)
    widget.refresh()
    widget.client.documents_received.emit([document(3), document(2), document(1)])
    assert widget.rows[widget.records.currentRow()].id == 2
    widget.records.setCurrentRow(2)
    widget.refresh()
    widget.client.documents_received.emit([document(1), document(3)])
    assert widget.rows[widget.records.currentRow()].id == 1


@pytest.mark.parametrize("reset", ["denied", "disconnect", "close"])
def test_reset_clears_progress_and_ignores_late_upload_signals(widget, reset):
    """403·재연결·종료 뒤 옛 진행·성공 신호가 상태나 연결을 복원하지 않는다."""
    linked = []
    widget.record_linked.connect(linked.append)
    widget.upload("unused.docx")
    widget.client.upload_progress.emit(50, 100)
    if reset == "denied":
        widget.client.documents_failed.emit("문서 저장이 거부됐습니다.")
    elif reset == "disconnect":
        widget.set_connected(False)
    else:
        widget.close()
    old_notice = widget.notice.text()
    widget.client.upload_progress.emit(100, 100)
    widget.client.document_uploaded.emit(document(2, linked=True))
    assert not widget.busy and widget.progress.isHidden() and widget.transfer_summary.isHidden()
    assert widget.completion.isHidden() and widget.rows == [] and linked == []
    assert widget.notice.text() == old_notice and len(widget.client.uploads) == 1


def test_validation_failure_and_empty_list_clear_old_feedback(widget):
    """즉시 입력 오류와 빈 목록이 과거 완료 표시·본문을 현재 결과로 남기지 않는다."""
    widget.upload("unused.docx")
    widget.client.document_uploaded.emit(document(2))
    widget.client.documents_received.emit([document(2)])
    assert not widget.completion.isHidden()
    widget.client.reject = True
    widget.upload("bad.docx")
    assert not widget.busy and widget.progress.isHidden() and widget.completion.isHidden()
    assert widget.rows == [] and not widget.content.toPlainText()
    widget.client.reject = False
    widget.upload("unused.docx")
    widget.client.document_uploaded.emit(document(3))
    widget.client.documents_received.emit([])
    assert widget.rows == [] and widget.completion.isHidden()
    assert widget.records.currentRow() == -1 and not widget.content.toPlainText()


def test_client_progress_uses_reply_identity_and_preserves_large_values(app):
    """실제 Client의 진행 전달은 현재 reply에 한정하고 qint64 값을 손실 없이 보존한다."""
    client = DocumentsClient(9)
    first, second = QObject(), QObject()
    received = []
    client.upload_progress.connect(lambda sent, total: received.append((sent, total)))
    try:
        client.operation, client.reply = "upload", first
        client._forward_upload_progress(first, 2**40, 2**41)
        client.reply = second
        client._forward_upload_progress(first, 1, 2)
        client.operation = "list"
        client._forward_upload_progress(second, 1, 2)
        client.reply = None
        client._forward_upload_progress(first, 1, 2)
        assert received == [(2**40, 2**41)]
    finally:
        client.reply = None
        client.close()
        client.deleteLater()
        app.processEvents()
