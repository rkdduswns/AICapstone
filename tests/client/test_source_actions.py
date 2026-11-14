"""외부 앱을 실제로 열지 않고 명시적 원본 출처 메뉴의 경계를 검증한다."""

import sys

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

import client.source_actions as module
from client.source_actions import SourceActionsButton


@pytest.fixture(scope="module")
def app():
    """하나의 Qt 앱에서 메뉴와 가상 자료의 클립보드 동작을 처리한다."""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def source(app, monkeypatch):
    """외부 열기를 기록하여 테스트가 브라우저·문서 프로그램을 실행하지 않게 한다."""
    button = SourceActionsButton()
    opened, messages = [], []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
    button.message.connect(messages.append)
    yield button, opened, messages
    button.close()
    button.deleteLater()


def test_unknown_and_cleared_selection_never_open_or_copy(source, app, monkeypatch):
    """선택 없음·조회 초기화에서 이전 출처가 외부 동작 대상으로 남지 않는다."""
    button, opened, messages = source
    copied = []
    monkeypatch.setattr(button, "_copy_url", lambda: copied.append(True))
    assert not button.isEnabled()
    button.set_source("https://example.test/original")
    assert button.isEnabled()
    button.clear()
    button.open_url_action.trigger()
    button.open_file_action.trigger()
    button.copy_url_action.trigger()
    assert not button.isEnabled()
    assert opened == messages == copied == []


def test_source_validation_has_no_file_access_or_external_side_effect(source, monkeypatch):
    """출처 설정만으로 파일 존재 검사나 URL 열기가 발생하지 않는다."""
    button, opened, messages = source
    monkeypatch.setattr(module.Path, "is_file", lambda *_: pytest.fail("implicit file check"))
    monkeypatch.setattr(module.Path, "is_dir", lambda *_: pytest.fail("implicit folder check"))
    button.set_source("https://example.test/a", r"C:\가상 자료\연구.pdf")
    assert button.isEnabled() and button.open_file_action.isEnabled()
    assert opened == messages == []


def test_http_url_opens_original_only_on_explicit_action(source):
    """정규화로 원본 경로를 바꾸지 않고 사용자가 누른 한 번만 연다."""
    button, opened, messages = source
    original = "https://Example.test/research?key=%23#section"
    button.set_source(original)
    assert opened == []
    button.open_url_action.trigger()
    assert opened == [QUrl(original)] and messages == []


def test_replacing_selection_uses_only_new_verified_source(source):
    """이전 출처를 다음 선택의 열기·복사 대상으로 남기지 않는다."""
    button, opened, messages = source
    button.set_source("https://example.test/first", r"C:\가상 자료\첫 문서.pdf")
    button.set_source("https://example.test/second")
    assert button.url == "https://example.test/second" and button.file_path is None
    assert not button.open_file_action.isVisible() and not button.copy_path_action.isEnabled()
    button.open_url_action.trigger()
    button.open_file_action.trigger()
    assert opened == [QUrl("https://example.test/second")] and messages == []
    button.clear()
    assert button.url is None and button.file_path is None


@pytest.mark.parametrize("url", [
    "file:///C:/a.pdf", "javascript:alert(1)", "data:text/plain,test", "ftp://example.test/a",
    "https://user:pass@example.test/a", "https://example.test/a\n", "https://example.test/a\x00",
    "https://example.test/space here", "https://example.test/\\host", "https://example.test/%ZZ",
    "https://", "//example.test/a", "",
])
def test_invalid_web_source_cannot_be_opened_or_copied(source, url):
    """인증 정보·다른 프로토콜·제어 문자를 외부 열기와 복사 대상으로 사용하지 않는다."""
    button, opened, messages = source
    button.set_source(url)
    assert not button.open_url_action.isEnabled() and not button.copy_url_action.isEnabled()
    button.open_url_action.trigger()
    assert opened == messages == []


@pytest.mark.parametrize("path", [
    r"relative.pdf", r"C:relative.pdf", r"C:\data\run.exe", r"C:\data\run.bat",
    r"C:\data\run.pdf.exe", r'C:\data\bad".pdf', r"C:\data\a.pdf:stream",
    r"\\?\C:\data\a.pdf", r"\\.\C:\data\a.pdf", r"C:\data\..\a.pdf",
    r"C:\data\CON.pdf", r"C:\data\LPT1.docx",
])
def test_invalid_document_source_cannot_be_opened_or_copied(source, path):
    """상대·실행 파일·장치·ADS 경로는 검증된 원본 문서로 취급하지 않는다."""
    button, opened, messages = source
    button.set_source(file_path=path)
    assert not button.open_file_action.isEnabled() and not button.copy_path_action.isEnabled()
    assert not button.isEnabled()
    button.open_file_action.trigger()
    assert opened == messages == []


def test_unc_is_copy_only_and_never_probes_network_share(source, monkeypatch):
    """공유 경로를 확인하는 것만으로 서버에 접근하거나 파일 탐색기를 열지 않는다."""
    button, opened, messages = source
    monkeypatch.setattr(module.Path, "is_file", lambda *_: pytest.fail("UNC access"))
    monkeypatch.setattr(module.Path, "is_dir", lambda *_: pytest.fail("UNC access"))
    button.set_source(file_path=r"\\server\share\원본.pdf")
    assert button.copy_path_action.isEnabled()
    assert not button.open_file_action.isEnabled() and not button.open_folder_action.isEnabled()
    button._open_file()
    button._open_folder()
    assert opened == messages == []


def test_copy_preserves_source_and_does_not_open(source, app, monkeypatch):
    """가상 클립보드에만 원문을 복사하고 파일·브라우저를 실행하지 않는다."""
    button, opened, messages = source
    copied = []

    class Clipboard:
        """개인 클립보드를 읽거나 쓰지 않는 테스트 대역."""

        def setText(self, text):
            """명시적 복사값만 기록한다."""
            copied.append(text)

    monkeypatch.setattr(QApplication, "clipboard", lambda: Clipboard())
    url, path = "https://example.test/원문?x=1#part", r"C:\가상 자료\원본.docx"
    button.set_source(url, path)
    button.copy_url_action.trigger()
    button.copy_path_action.trigger()
    assert copied == [url, path]
    assert opened == messages == []


@pytest.mark.skipif(sys.platform != "win32", reason="실제 Windows 절대 경로 파일 검사")
def test_existing_local_document_and_folder_open_once_each(source, tmp_path):
    """가상 PDF의 존재만 검사한 뒤 QUrl로 기본 앱·폴더 열기를 요청한다."""
    button, opened, messages = source
    path = tmp_path / "가상 원본.pdf"
    path.write_bytes(b"synthetic document")
    button.set_source(file_path=str(path))
    assert opened == []
    button.open_file_action.trigger()
    button.open_folder_action.trigger()
    assert opened == [QUrl.fromLocalFile(str(path)), QUrl.fromLocalFile(str(tmp_path))]
    assert messages == []


@pytest.mark.skipif(sys.platform != "win32", reason="실제 Windows 절대 경로 파일 검사")
def test_missing_original_does_not_open_and_existing_parent_can_be_opened(source, tmp_path):
    """이동·삭제된 파일은 실패를 알리고 존재하는 원본 폴더는 별도로 열 수 있다."""
    button, opened, messages = source
    path = tmp_path / "사라진 원본.pdf"
    button.set_source(file_path=str(path))
    button.open_file_action.trigger()
    assert opened == [] and len(messages) == 1 and "찾을 수 없습니다" in messages[0]
    button.open_folder_action.trigger()
    assert opened == [QUrl.fromLocalFile(str(tmp_path))]


def test_missing_folder_and_desktop_open_failure_are_reported(source, monkeypatch):
    """파일·폴더·브라우저 열기 실패는 성공으로 처리하지 않는다."""
    button, opened, messages = source
    monkeypatch.setattr(module.Path, "is_dir", lambda *_: False)
    button.set_source("https://example.test/a", r"C:\missing\원본.pdf")
    button.open_folder_action.trigger()
    assert opened == [] and "폴더를 찾을 수 없습니다" in messages[-1]
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda _: False)
    button.open_url_action.trigger()
    assert "웹페이지를 열지 못했습니다" in messages[-1]
    monkeypatch.setattr(module.Path, "is_file", lambda *_: True)
    button.open_file_action.trigger()
    assert "원본 파일을 열지 못했습니다" in messages[-1]
