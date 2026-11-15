"""health 이후의 상태 확인과 실제 문서 읽기를 기다리는 Client 진단 경계를 검증한다."""

from dataclasses import replace

import pytest
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from client.application_window import ApplicationWindow
from client.reading_diagnostic import ReadingDiagnostic
from shared.activity import CurrentActivity
from shared.document import ImportedDocument
from shared.privacy import PrivacySettings, PrivacyState, RecordingStatus

STAMP = "2026-11-16T10:00:00+09:00"
PAUSED = PrivacyState(PrivacySettings(True, [], False), RecordingStatus(False, "paused"))


@pytest.fixture(scope="module")
def app():
    """사용자 표시 설정을 사용하지 않는 같은 Qt 앱에서 진단 창만 처리한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


@pytest.fixture
def diagnostic(app, monkeypatch):
    """네트워크를 직접 시작하지 않고 실제 Client 신호·화면·찾기 동작을 사용한다."""
    window = ApplicationWindow(9)
    reads, results, writes = [], [], []
    management = window.management
    monkeypatch.setattr(management.activity, "start", lambda: None)
    monkeypatch.setattr(management.privacy.client, "start", lambda: None)
    monkeypatch.setattr(management.documents.client, "refresh", lambda: reads.append("documents"))
    monkeypatch.setattr(management.documents.client, "upload", lambda *args: writes.append("upload"))
    monkeypatch.setattr(management.privacy.client, "put", lambda *args: writes.append("privacy"))
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(
        lambda _url: pytest.fail("진단은 원본 파일이나 기본 브라우저를 열면 안 됩니다."),
    ))
    checker = ReadingDiagnostic(window, lambda success, checks: results.append((success, checks)))
    window.search.query.setText("진단 후에도 유지할 검색 입력")
    window.show()
    window.activateWindow()
    app.processEvents()
    yield window, checker, reads, results, writes
    checker.cancel()
    window.close()
    app.processEvents()


def confirm(window, *, order=("activity", "privacy")):
    """기록 허용으로 바꾸지 않고 실제 확인된 일시정지 상태를 전달한다."""
    management = window.management
    management.backend.connection_changed.emit(True)
    for name in order:
        if name == "activity":
            management.activity.activity_received.emit(CurrentActivity("paused", None))
        else:
            management.privacy.client.state_received.emit(PAUSED, "read")


def rows():
    """경로를 추정하면 안 되는 연결 없는 문서 두 개에 한글·이모지 원문을 넣는다."""
    return [ImportedDocument(1, "가상1.docx", "docx", STAMP, "😀 가상 진단 본문\n본문 그대로"),
            ImportedDocument(2, "가상2.docx", "docx", STAMP, "  둘째 문서 원문\n둘째 문서 원문")]


def test_health_success_alone_never_completes_or_opens_document_list(diagnostic):
    """예전 연결 진단의 성공 하나를 읽기·개인정보 확인 성공으로 확대하지 않는다."""
    window, checker, reads, results, writes = diagnostic
    window.management.backend.connection_changed.emit(True)
    assert results == reads == writes == []
    assert checker.checks["health_confirmed"]
    assert not checker.checks["activity_confirmed"] and not checker.checks["privacy_confirmed"]
    window.management.activity.activity_received.emit(CurrentActivity("paused", None))
    assert results == reads == []


@pytest.mark.parametrize("order", [("activity", "privacy"), ("privacy", "activity")])
def test_confirmed_paused_channels_then_real_document_widgets_complete_once(app, diagnostic, order):
    """응답 순서와 관계없이 GET 뒤 두 본문을 읽으며 일시정지·원문·사용자 입력을 유지한다."""
    window, checker, reads, results, writes = diagnostic
    confirm(window, order=order)
    assert reads == ["documents"] and results == []
    documents = window.management.documents
    documents.client.documents_received.emit(rows())
    app.processEvents()
    assert len(results) == 1 and results[0][0] is True
    assert all(type(value) is bool and value for value in results[0][1].values())
    assert set(results[0][1]) == {
        "health_confirmed", "activity_confirmed", "privacy_confirmed", "document_list",
        "document_find", "document_source_none", "management_return",
    }
    assert documents.content.toPlainText() == rows()[1].extracted_text
    assert documents.content.isReadOnly() and documents.find_bar.isHidden()
    assert window.search.isVisible() and not window.management_panel.isVisible()
    assert window.search.query.text() == "진단 후에도 유지할 검색 입력"
    assert window.management.privacy.state.settings.paused is True
    assert writes == [] and not checker.timer.isActive()
    # 정상 폴링의 늦은 상태 응답만 전달한다. 새 health 재연결 자체는 별도 조회를 시작할 수 있다.
    window.management.activity.activity_received.emit(CurrentActivity("paused", None))
    window.management.privacy.client.state_received.emit(PAUSED, "read")
    documents.client.documents_received.emit(rows())
    checker.timer.timeout.emit()
    app.processEvents()
    assert len(results) == 1 and reads == ["documents"]


@pytest.mark.parametrize("channel", ["health", "activity", "privacy", "documents"])
def test_unavailable_or_malformed_channel_cannot_report_success(app, diagnostic, channel):
    """실패 신호와 실제 응답 파서의 거부가 부분 확인 뒤에도 성공으로 이어지지 않는다."""
    window, checker, _, results, writes = diagnostic
    management = window.management
    if channel == "health":
        management.backend.connection_changed.emit(False)
    elif channel == "activity":
        management.activity._received(b"not-json")
    elif channel == "privacy":
        management.privacy.client._received(b"not-json")
    else:
        confirm(window)
        management.documents.client._received(b"not-json")
    app.processEvents()
    assert len(results) == 1 and results[0][0] is False
    assert not all(results[0][1].values()) and not checker.timer.isActive()
    assert writes == []


@pytest.mark.parametrize("finish", ["timeout", "cancel", "close"])
def test_timeout_cancel_and_close_ignore_scheduled_document_callback(app, diagnostic, finish):
    """늦은 문서 표시 콜백이 취소·시간 초과·닫힘 이후 다시 완료되거나 원문을 이동하지 않는다."""
    window, checker, reads, results, writes = diagnostic
    confirm(window)
    window.management.documents.client.documents_received.emit(rows())
    if finish == "timeout":
        checker.timer.timeout.emit()
    elif finish == "cancel":
        checker.cancel()
    else:
        window.close()
    app.processEvents()
    assert len(results) == 1 and results[0][0] is False
    assert not results[0][1]["document_find"] and not checker.timer.isActive()
    assert reads == ["documents"] and writes == []


@pytest.mark.parametrize("documents", [[], [rows()[0]], [replace(rows()[0], record_id="7",
                         file_path=r"C:\가상 자료\원본.docx"), rows()[1]]])
def test_unexpected_empty_or_linked_fixture_does_not_claim_unlinked_source_check(app, diagnostic,
                                                                              documents):
    """불완전한 검증 자료나 실제 원본 경로가 있는 자료를 미연결 출처 검증 성공으로 바꾸지 않는다."""
    window, _, _, results, writes = diagnostic
    confirm(window)
    window.management.documents.client.documents_received.emit(documents)
    app.processEvents()
    assert len(results) == 1 and results[0][0] is False
    assert not all(results[0][1].values()) and writes == []


def test_reading_option_requires_result_before_application_or_settings(monkeypatch):
    """읽기 진단 옵션만 전달하면 사용자 앱·표시 설정을 만들기 전에 명확히 거부한다."""
    import client.__main__ as entry

    monkeypatch.setattr(entry.sys, "argv", ["client", "--smoke-test-reading"])
    monkeypatch.setattr(entry, "QApplication", lambda _args: pytest.fail("앱을 만들면 안 됩니다."))
    monkeypatch.setattr(entry, "ViewPreferences", lambda: pytest.fail("사용자 설정을 읽으면 안 됩니다."))
    with pytest.raises(SystemExit) as error:
        entry.main()
    assert error.value.code == 2


def test_repeated_body_with_no_op_next_fails_reading_movement(app, diagnostic, monkeypatch):
    """일치 문자열만 남고 다음 이동이 동작하지 않는 회귀를 네이티브 진단 성공으로 숨기지 않는다."""
    window, _, _, results, writes = diagnostic
    confirm(window)
    documents = window.management.documents
    monkeypatch.setattr(documents.find_bar, "find_next", lambda: None)
    documents.client.documents_received.emit(rows())
    app.processEvents()
    assert len(results) == 1 and results[0][0] is False
    assert results[0][1]["document_list"] and not results[0][1]["document_find"]
    assert documents.content.isReadOnly() and documents.content.toPlainText() == rows()[1].extracted_text
    assert writes == []
