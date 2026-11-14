"""서버에서 확인한 개인정보 설정과 미적용 입력의 화면 경계를 검증한다."""

import json
from dataclasses import asdict, replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from client.privacy_widget import PrivacyWidget
from shared.browser import UrlBlockRule
from shared.privacy import PrivacyResponse, PrivacySettings, PrivacyState, RecordingStatus


def verified_state(*, urls=None, clipboard=False, paused=False, reason="allowed"):
    """기록 판정과 각 설정을 분리한 가상 서버 확인값을 만든다."""
    return PrivacyState(
        PrivacySettings(paused, ["chrome.exe", "writer.exe"], clipboard, urls),
        RecordingStatus(reason == "allowed", reason),
    )


def receive(widget, state):
    """실제 Client의 응답 검증을 거쳐 화면에 서버 확인값을 전달한다."""
    widget.client._received(json.dumps(asdict(PrivacyResponse(state))).encode())


@pytest.fixture(scope="module")
def app():
    """같은 Qt 이벤트 루프에서 상태 전환과 키보드 초점을 처리한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


@pytest.fixture
def privacy(app, monkeypatch):
    """실제 전송 대신 요청을 기록하고 기존 Client의 확인·실패 흐름을 유지한다."""
    widget = PrivacyWidget(9)
    writes, reads = [], []
    monkeypatch.setattr(widget.client, "put", lambda path, payload:
                        writes.append((path, json.loads(payload))))
    monkeypatch.setattr(widget.client, "get", reads.append)
    widget.connected = True
    widget.client.active = True
    widget.client.poll_timer.setInterval(60_000)
    widget.show()
    app.processEvents()
    try:
        yield widget, writes, reads
    finally:
        widget.client.stop()
        widget.close()
        widget.deleteLater()
        app.processEvents()


def test_verified_snapshot_is_read_only_and_does_not_infer_recording_permission(app, privacy):
    """일시정지가 꺼져도 기록 차단 판정과 구분하고 확인된 목록은 읽기 전용으로 연다."""
    widget, writes, reads = privacy
    receive(widget, verified_state(reason="blocked_program"))
    assert "차단" in widget.summary.text()
    assert "기록 가능" not in widget.server_summary.text()
    assert widget.server_summary.textFormat() == Qt.TextFormat.PlainText
    assert widget.applied_programs.isReadOnly()
    assert widget.applied_programs.toPlainText() == "chrome.exe\nwriter.exe"
    assert not widget.applied_programs.isVisible()
    widget.applied_details_button.click()
    app.processEvents()
    assert widget.applied_programs.isVisible()
    assert writes == reads == []


@pytest.mark.parametrize("transition", ["error", "changing", "disconnect", "reconnect"])
def test_unconfirmed_states_clear_snapshot_and_keep_unapplied_program_draft(privacy, transition):
    """실패·적용 대기·연결 변경에서 옛 적용값을 현재 설정으로 표시하지 않는다."""
    widget, writes, _ = privacy
    receive(widget, verified_state())
    widget.editor.setPlainText("draft.exe")
    if transition == "error":
        widget.client._failed("network", 0)
    elif transition == "changing":
        widget.toggle.click()
        assert writes == [("/privacy/paused", {"paused": True})]
    else:
        widget.set_connected(transition == "reconnect")
    assert widget.state is None
    assert widget.applied_programs.toPlainText() == ""
    assert not widget.applied_details_button.isEnabled()
    assert widget.editor.toPlainText() == "draft.exe"
    assert not widget.apply_button.isEnabled() and not widget.toggle.isEnabled()
    assert any(word in widget.server_summary.text() for word in ("확인", "대기", "요청"))
    assert "미지원" not in widget.urls.availability_message.text()


def test_polling_preserves_draft_while_snapshot_tracks_only_confirmed_values(privacy):
    """입력과 다른 확인 목록을 함께 보며 폴링이 미적용 초안을 덮어쓰지 않는다."""
    widget, writes, reads = privacy
    state = verified_state()
    receive(widget, state)
    widget.editor.setPlainText("chrome.exe\ndraft.exe")
    assert widget.dirty and "미적용" in widget.draft_status.text()
    assert widget.applied_programs.toPlainText() == "chrome.exe\nwriter.exe"
    receive(widget, replace(state, settings=replace(state.settings, blocked_processes=["other.exe"])))
    assert widget.editor.toPlainText() == "chrome.exe\ndraft.exe"
    assert widget.applied_programs.toPlainText() == "other.exe"
    assert widget.dirty and "미적용" in widget.draft_status.text()
    assert writes == reads == []


def test_clipboard_put_is_independent_and_preserves_program_draft(privacy):
    """클립보드 설정만 한 번 전송하고 다른 미적용 목록을 섞지 않는다."""
    widget, writes, _ = privacy
    state = verified_state(urls=[])
    receive(widget, state)
    widget.editor.setPlainText("draft.exe")
    widget.clipboard_toggle.click()
    assert writes == [("/privacy/clipboard", {"clipboard_enabled": True})]
    assert widget.state is None and widget.applied_programs.toPlainText() == ""
    receive(widget, replace(state, settings=replace(state.settings, clipboard_enabled=True)))
    assert widget.state.settings.clipboard_enabled is True
    assert widget.editor.toPlainText() == "draft.exe" and widget.dirty
    assert widget.applied_programs.toPlainText() == "chrome.exe\nwriter.exe"
    assert len(writes) == 1


def test_program_reset_and_snapshot_peek_do_not_write_to_server(app, privacy):
    """되돌리기와 확인 목록 펼침은 로컬 보기·초안 복원만 수행한다."""
    widget, writes, reads = privacy
    receive(widget, verified_state())
    widget.editor.setPlainText("draft.exe")
    widget.applied_details_button.click()
    app.processEvents()
    assert widget.applied_programs.isVisible()
    widget.reset_button.click()
    assert widget.editor.toPlainText() == "chrome.exe\nwriter.exe"
    assert not widget.dirty
    widget.applied_details_button.click()
    assert not widget.applied_programs.isVisible()
    assert writes == reads == []


@pytest.mark.parametrize("rules,supported", [(None, False), ([], True)])
def test_confirmed_url_support_distinguishes_missing_from_supported_empty(app, privacy, rules, supported):
    """지원하는 빈 목록은 편집할 수 있고 확인된 미지원은 폼 대신 안내를 표시한다."""
    widget, writes, _ = privacy
    receive(widget, verified_state(urls=rules))
    widget.rule_tabs.setCurrentWidget(widget.urls)
    app.processEvents()
    assert widget.urls.editor_panel.isVisible() is supported
    assert widget.urls.add_button.isEnabled() is supported
    if supported:
        assert widget.state.settings.blocked_urls == []
    else:
        assert "미지원" in widget.urls.status.text()
        assert widget.urls.availability_message.text()
        assert widget.urls.availability_message.textFormat() == Qt.TextFormat.PlainText
    assert writes == []


def test_url_draft_and_typed_address_survive_unknown_unsupported_and_recovery(app, privacy):
    """숨긴 URL 입력을 잃지 않으면서 미확인과 미지원을 서로 다르게 안내한다."""
    widget, writes, _ = privacy
    receive(widget, verified_state(urls=[]))
    widget.rule_tabs.setCurrentWidget(widget.urls)
    widget.urls.value.setText("example.com")
    widget.urls.add_button.click()
    widget.urls.value.setText("unfinished.example.com")
    expected = [UrlBlockRule("domain", "example.com")]
    widget.client._failed("network", 0)
    app.processEvents()
    assert not widget.urls.editor_panel.isVisible()
    assert "미지원" not in widget.urls.availability_message.text()
    assert widget.urls.draft == expected and widget.urls.value.text() == "unfinished.example.com"
    assert widget.urls.dirty and not widget.urls.apply_button.isEnabled()
    widget.urls.apply_button.click()
    receive(widget, verified_state(urls=None))
    assert "미지원" in widget.urls.status.text()
    assert widget.urls.draft == expected and widget.urls.value.text() == "unfinished.example.com"
    receive(widget, verified_state(urls=[]))
    app.processEvents()
    assert widget.urls.editor_panel.isVisible() and widget.urls.apply_button.isEnabled()
    assert widget.urls.draft == expected and widget.urls.value.text() == "unfinished.example.com"
    assert writes == []


def test_empty_url_removal_draft_survives_unsupported_and_supported_roundtrip(app, privacy):
    """전체 해제라는 빈 초안도 미지원 응답 때문에 사라지거나 옛 규칙으로 복구되지 않는다."""
    widget, writes, _ = privacy
    rule = UrlBlockRule("domain", "example.com")
    receive(widget, verified_state(urls=[rule]))
    widget.rule_tabs.setCurrentWidget(widget.urls)
    widget.urls.table.selectRow(0)
    widget.urls.remove_button.click()
    assert widget.urls.draft == [] and widget.urls.dirty
    receive(widget, verified_state(urls=None))
    app.processEvents()
    assert not widget.urls.editor_panel.isVisible()
    assert widget.urls.draft == [] and widget.urls.dirty
    assert not widget.urls.apply_button.isEnabled()
    receive(widget, verified_state(urls=[rule]))
    app.processEvents()
    assert widget.urls.editor_panel.isVisible()
    assert widget.urls.draft == [] and widget.urls.dirty
    assert widget.urls.apply_button.isEnabled()
    # 실제 지원 서버가 빈 목록을 확인한 경우에는 더 이상 적용할 차이가 없다.
    receive(widget, verified_state(urls=[]))
    assert widget.urls.draft == [] and not widget.urls.dirty
    assert not widget.urls.apply_button.isEnabled()
    assert writes == []


def test_url_apply_uses_only_existing_url_request_and_preserves_program_draft(privacy):
    """지원된 URL 폼의 명시적 적용만 전송하고 프로그램 초안은 그대로 둔다."""
    widget, writes, _ = privacy
    state = verified_state(urls=[])
    receive(widget, state)
    widget.editor.setPlainText("draft.exe")
    widget.urls.value.setText("example.com")
    widget.urls.add_button.click()
    widget.urls.apply_button.click()
    assert writes == [("/privacy/blocked-urls", {
        "blocked_urls": [{"kind": "domain", "value": "example.com"}],
    })]
    assert widget.state is None and not widget.urls.editor_panel.isVisible()
    receive(widget, replace(state, settings=replace(
        state.settings, blocked_urls=[UrlBlockRule("domain", "example.com")],
    )))
    assert not widget.urls.dirty
    assert widget.editor.toPlainText() == "draft.exe" and widget.dirty
    assert len(writes) == 1


def test_unconfirmed_write_clears_snapshot_and_recovers_by_get_only(privacy):
    """잘못된 쓰기 확인 응답은 성공으로 보이지 않고 재확인은 GET만 보낸다."""
    widget, writes, reads = privacy
    state = verified_state()
    receive(widget, state)
    widget.toggle.click()
    receive(widget, state)
    assert widget.state is None and widget.applied_programs.toPlainText() == ""
    assert "적용 여부 미확인" in widget.notice.text()
    assert not widget.toggle.isEnabled()
    assert writes == [("/privacy/paused", {"paused": True})]
    widget.refresh_button.click()
    assert reads == ["/privacy"]
    receive(widget, replace(state, settings=replace(state.settings, paused=True),
                            recording=RecordingStatus(False, "paused")))
    assert widget.state.settings.paused is True
    assert widget.applied_programs.toPlainText() == "chrome.exe\nwriter.exe"
    assert len(writes) == 1


def test_incomplete_program_input_is_plain_and_never_replaces_verified_snapshot(privacy):
    """입력 중인 잘못된 형식·태그 모양 문자열은 초안이며 확인 목록을 바꾸지 않는다."""
    widget, writes, _ = privacy
    receive(widget, verified_state())
    raw = "<b>아직 입력 중</b>"
    widget.editor.setPlainText(raw)
    assert widget.editor.toPlainText() == raw
    assert widget.applied_programs.toPlainText() == "chrome.exe\nwriter.exe"
    assert widget.draft_status.textFormat() == Qt.TextFormat.PlainText
    widget.apply_button.click()
    assert widget.validation.text() and widget.dirty
    assert writes == []


def test_small_view_preserves_keyboard_navigation_without_editing_applied_values(app, privacy):
    """작은 화면에서 안내는 줄바꿈하고 Tab 이동은 프로그램 초안에 문자를 넣지 않는다."""
    widget, writes, _ = privacy
    receive(widget, verified_state())
    widget.resize(360, 540)
    widget.activateWindow()
    widget.editor.setFocus()
    app.processEvents()
    before = widget.editor.toPlainText()
    QTest.keyClick(widget.editor, Qt.Key.Key_Tab)
    app.processEvents()
    assert widget.editor.toPlainText() == before
    assert not widget.editor.hasFocus()
    assert widget.server_summary.wordWrap() and widget.urls.availability_message.wordWrap()
    assert widget.rect().contains(widget.applied_details_button.geometry())
    assert writes == []
