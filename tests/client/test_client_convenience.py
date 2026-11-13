"""앱 진입·키보드·표시 설정의 실제 연결을 검증한다."""

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QRect, QSettings, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from client.application_window import ApplicationWindow
from client.view_preferences import ViewPreferences


@pytest.fixture(scope="module")
def app():
    """동일 Qt 앱에서 창 전환을 처리하며 테스트 종료로 앱이 끝나지 않게 한다."""
    instance = QApplication.instance() or QApplication([])
    instance.setQuitOnLastWindowClosed(False)
    return instance


@pytest.mark.parametrize("diagnostic", [False, True])
def test_entry_checks_once_and_diagnostic_does_not_use_preferences(monkeypatch, diagnostic):
    """일반 실행에도 한 번 연결하며 진단 실행은 실제 사용자 설정을 읽지 않는다."""
    import client.__main__ as entry

    timers, checks, preferences, windows = [], [], [], []
    marker = object()

    class Window:
        """진입점의 예약 순서만 관찰하고 실제 네트워크나 사용자 창을 만들지 않는다."""

        def __init__(self, port, **kwargs):
            self.management = SimpleNamespace(
                check=lambda: checks.append(port),
                backend=SimpleNamespace(connection_changed=SimpleNamespace(connect=lambda slot: None)),
            )
            windows.append(kwargs)

        def show(self):
            """연결 예약 전에 창을 표시하는 정상 경로를 제공한다."""

    application = SimpleNamespace(setApplicationName=lambda value: None,
                                  setApplicationDisplayName=lambda value: None, exec=lambda: 0)

    def view_preferences():
        """일반 실행에만 표시 설정이 주입되는지 확인한다."""
        preferences.append(True)
        return marker

    arguments = ["client", "--port", "9123"]
    if diagnostic:
        arguments += ["--smoke-test-result", "unused-result.json"]
    monkeypatch.setattr(entry.sys, "argv", arguments)
    monkeypatch.setattr(entry, "QApplication", lambda _args: application)
    monkeypatch.setattr(entry, "ApplicationWindow", Window)
    monkeypatch.setattr(entry, "ViewPreferences", view_preferences)
    monkeypatch.setattr(entry, "QTimer", SimpleNamespace(singleShot=lambda ms, slot: timers.append((ms, slot))))
    assert entry.main() == 0
    immediate = [slot for milliseconds, slot in timers if milliseconds == 0]
    assert len(immediate) == 1
    immediate[0]()
    assert checks == [9123]
    assert windows == [{"preferences": None if diagnostic else marker}]
    assert len(preferences) == (0 if diagnostic else 1)


def test_shortcuts_refresh_only_current_view_and_keep_search(app, monkeypatch):
    """F5는 조회만 실행하고 Ctrl+L은 검색 입력을 보존한 채 돌아온다."""
    window = ApplicationWindow()
    window.show()
    window.activateWindow()
    app.processEvents()
    calls = []
    monkeypatch.setattr(window.management, "check", lambda: calls.append("health"))
    monkeypatch.setattr(window.management.recent, "refresh", lambda: calls.append("recent"))
    monkeypatch.setattr(window.management.documents, "refresh", lambda: calls.append("documents"))
    window.management.privacy.refresh_button.clicked.connect(lambda: calls.append("privacy"))
    try:
        window.search.query.setText("유지할 검색 입력")
        QTest.keyClick(window, Qt.Key.Key_F5)
        app.processEvents()
        assert calls == ["health"]
        for widget, expected in [(window.management.recent, "recent"),
                                 (window.management.documents, "documents")]:
            window.show_management(window.management.tabs.indexOf(widget))
            app.processEvents()
            QTest.keyClick(window, Qt.Key.Key_F5)
            app.processEvents()
            assert calls[-1] == expected
        window.show_management(window.management.tabs.indexOf(window.management.privacy))
        window.management.privacy.refresh_button.setEnabled(False)
        before = list(calls)
        QTest.keyClick(window, Qt.Key.Key_F5)
        assert calls == before
        window.management.privacy.refresh_button.setEnabled(True)
        QTest.keyClick(window, Qt.Key.Key_F5)
        assert calls[-1] == "privacy"
        QTest.keyClick(window, Qt.Key.Key_L, Qt.KeyboardModifier.ControlModifier)
        app.processEvents()
        assert window.search.isVisible() and window.search.query.hasFocus()
        assert window.search.query.text() == "유지할 검색 입력"
        assert not window.management.tabs.isTabVisible(
            window.management.tabs.indexOf(window.management.search))
    finally:
        window.close()
        app.processEvents()


def test_view_restore_remembers_dimensions_and_never_content(app, tmp_path):
    """실제 창 왕복·종료·재실행에서 표시 값만 복원하고 검색어·필터를 저장하지 않는다."""
    settings = QSettings(str(tmp_path / "views.ini"), QSettings.Format.IniFormat)
    preferences = ViewPreferences(settings)
    preferences.save_management_size(QSize(700, 650))
    preferences.save_ratio("recent", [40, 60])
    preferences.save_ratio("answer", [55, 45])
    window = ApplicationWindow(preferences=preferences)
    window.show()
    app.processEvents()
    window.search.query.setText("저장하지 않을 검색어")
    recent = window.management.recent
    window.show_management(window.management.tabs.indexOf(recent))
    app.processEvents()
    assert window.size() == QSize(700, 650)
    sizes = recent.reading_splitter.sizes()
    assert abs(sizes[0] / sum(sizes) - 0.4) < 0.09
    assert window.search.reading_ratio == 55
    recent.filter_edit.setText("저장하지 않을 제목·경로")
    recent.reading_splitter.setSizes([180, 220])
    recent.reading_splitter.splitterMoved.emit(180, 1)
    expected = round(recent.reading_splitter.sizes()[0] * 100 / sum(recent.reading_splitter.sizes()))
    window.show_search()
    assert window.height() <= 150
    window.close()
    app.processEvents()
    assert preferences.read_management_size() == QSize(700, 650)
    assert preferences.read_ratio("recent") == expected
    assert all(key.startswith("ui/v1/") for key in settings.allKeys())
    assert not any("저장하지 않을" in str(settings.value(key)) for key in settings.allKeys())
    restored = ApplicationWindow(preferences=preferences)
    try:
        restored.show()
        app.processEvents()
        assert restored.search.query.text() == ""
        assert restored.management.recent.filter_edit.text() == ""
    finally:
        restored.close()
        app.processEvents()


def test_search_refresh_never_cancels_active_upload_or_privacy_write(app, monkeypatch):
    """쓰기 도중 검색으로 돌아와 F5·메뉴 재확인을 눌러도 요청 수명을 바꾸지 않는다."""
    window = ApplicationWindow()
    calls = []
    monkeypatch.setattr(window.management, "check", lambda: calls.append(True))
    document, privacy = window.management.documents.client, window.management.privacy.client
    try:
        document.operation, document.reply = "upload", object()
        window.refresh_current_view()
        window.recheck_action.trigger()
        assert calls == [] and document.reply is not None
        document.reply = None
        privacy.operation, privacy.reply = "pause", object()
        window.refresh_current_view()
        window.recheck_action.trigger()
        assert calls == [] and privacy.reply is not None
        privacy.reply = None
        window.refresh_current_view()
        assert calls == [True]
    finally:
        document.reply = privacy.reply = None
        window.close()
        app.processEvents()


def test_removed_monitor_position_is_clamped_to_available_screen(app, tmp_path):
    """연결 해제된 모니터의 저장 좌표 때문에 작은 검색창이 화면 밖에 남지 않는다."""
    preferences = ViewPreferences(QSettings(str(tmp_path / "position.ini"), QSettings.Format.IniFormat))
    preferences.save_position(QPoint(100_000, 100_000))
    window = ApplicationWindow(preferences=preferences)
    try:
        window.show()
        app.processEvents()
        assert window.screen().availableGeometry().contains(window.frameGeometry())
    finally:
        window.close()
        app.processEvents()


def test_restore_on_smaller_monitor_also_limits_window_size(app, monkeypatch):
    """더 작은 논리 해상도의 복원 대상에서는 창 테두리까지 화면 안으로 줄인다."""
    import client.window_geometry as geometry

    bounds = QRect(10, 20, 300, 400)
    monkeypatch.setattr(geometry.QGuiApplication, "screenAt",
                        lambda point: SimpleNamespace(availableGeometry=lambda: bounds))
    window = QWidget()
    try:
        window.resize(440, 112)
        window.show()
        app.processEvents()
        geometry.restore_position(window, QPoint(50, 50))
        assert bounds.contains(window.frameGeometry())
    finally:
        window.close()
        app.processEvents()
