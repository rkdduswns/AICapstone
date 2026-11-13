"""실제 사용자 설정과 분리한 INI에서 표시 설정의 허용 범위·손상 복원을 검증한다."""

import pytest
from PySide6.QtCore import QPoint, QSettings, QSize

from client.view_preferences import ViewPreferences


@pytest.fixture
def settings(tmp_path):
    """제품 기본 설정을 사용하지 않고 테스트별 파일에만 표시 값을 저장한다."""
    return QSettings(str(tmp_path / "view.ini"), QSettings.Format.IniFormat)


def test_roundtrip_reopens_only_allowlisted_view_values(settings):
    """새 실행에서 위치·크기·세 비율을 복원하고 내용 관련 키는 생성하지 않는다."""
    preferences = ViewPreferences(settings)
    assert preferences.read_position() is None
    assert preferences.read_management_size() is None
    assert preferences.read_ratio("recent") is None
    assert preferences.save_position(QPoint(-1600, 240))
    assert preferences.save_management_size(QSize(780, 880))
    for key, sizes in [("recent", [350, 650]), ("documents", [2, 3]), ("answer", [5, 3])]:
        assert preferences.save_ratio(key, sizes)
    reopened = ViewPreferences(QSettings(settings.fileName(), QSettings.Format.IniFormat))
    assert reopened.read_position() == QPoint(-1600, 240)
    assert reopened.read_management_size() == QSize(780, 880)
    assert reopened.read_ratio("recent") == 35
    assert reopened.read_ratio("documents") == 40
    assert reopened.read_ratio("answer") == 62
    assert set(settings.allKeys()) == {
        "ui/v1/window_position", "ui/v1/management_size",
        "ui/v1/ratios/recent", "ui/v1/ratios/documents", "ui/v1/ratios/answer",
    }


@pytest.mark.parametrize("value", [None, "C:/private/file.docx", [30, 40], QPoint(100001, 0)])
def test_invalid_position_does_not_replace_existing_value(settings, value):
    """위치 인수로 파일 경로나 화면 내용을 전달해도 기존 위치만 유지한다."""
    preferences = ViewPreferences(settings)
    assert preferences.save_position(QPoint(20, 30))
    assert not preferences.save_position(value)
    assert preferences.read_position() == QPoint(20, 30)
    settings.setValue("ui/v1/window_position", value)
    assert preferences.read_position() is None


@pytest.mark.parametrize("value,expected", [
    (QSize(10, 20), QSize(320, 240)),
    (QSize(100000, 50000), QSize(4096, 2160)),
    (QSize(640, 720), QSize(640, 720)),
])
def test_positive_management_size_is_bounded(settings, value, expected):
    """작거나 큰 저장 크기도 읽을 수 있는 범위로 보정한다."""
    preferences = ViewPreferences(settings)
    assert preferences.save_management_size(value)
    assert preferences.read_management_size() == expected


@pytest.mark.parametrize("value", [QSize(-1, 500), QSize(500, 0), "640x720", [640, 720], None])
def test_invalid_management_size_is_ignored(settings, value):
    """손상된 관리 크기는 저장하지 않고 로드 시에도 기본값을 사용하게 한다."""
    preferences = ViewPreferences(settings)
    assert not preferences.save_management_size(value)
    settings.setValue("ui/v1/management_size", value)
    assert preferences.read_management_size() is None


@pytest.mark.parametrize("value", [True, False, 0, 9, 91, 100, 50.5, "050", "50.0", " 50", "５０"])
def test_malformed_ratio_is_ignored(settings, value):
    """불리언·접힌 값·비정규 문자열을 읽기 비율로 바꾸지 않는다."""
    settings.setValue("ui/v1/ratios/recent", value)
    assert ViewPreferences(settings).read_ratio("recent") is None


@pytest.mark.parametrize("sizes", [[0, 400], [400, 0], [-1, 5], [True, 50], [1.5, 3],
                                    [1], [1, 2, 3], "private body", [2**40, 10]])
def test_hidden_or_invalid_panels_do_not_overwrite_ratio(settings, sizes):
    """접힌 근거 영역이나 임의 데이터를 받아도 마지막 유효한 배치 비율을 유지한다."""
    preferences = ViewPreferences(settings)
    assert preferences.save_ratio("answer", [600, 400])
    assert not preferences.save_ratio("answer", sizes)
    assert preferences.read_ratio("answer") == 60


def test_ratio_bounds_and_unknown_key_do_not_expand_storage_scope(settings):
    """비율 양끝을 읽을 수 있게 보정하고 다른 키를 조회·쓰기 경로로 사용하지 않는다."""
    preferences = ViewPreferences(settings)
    assert preferences.save_ratio("recent", [1, 999])
    assert preferences.read_ratio("recent") == 10
    assert preferences.save_ratio("documents", [999, 1])
    assert preferences.read_ratio("documents") == 90
    for key in ["query", "file_path", "recent/../../body", "", "filters", None, []]:
        assert preferences.read_ratio(key) is None
        assert not preferences.save_ratio(key, [3, 2])
    assert set(settings.allKeys()) == {"ui/v1/ratios/recent", "ui/v1/ratios/documents"}


def test_settings_failure_does_not_interrupt_client(settings, monkeypatch):
    """읽기·동기화 실패는 기본 배치와 저장 실패로 반환하며 앱에 예외를 전파하지 않는다."""
    preferences = ViewPreferences(settings)

    def fail(*args):
        """접근할 수 없는 사용자 설정 저장소를 재현한다."""
        raise OSError("unavailable settings")

    monkeypatch.setattr(settings, "value", fail)
    assert preferences.read_position() is None
    assert preferences.read_management_size() is None
    assert preferences.read_ratio("recent") is None
    monkeypatch.setattr(settings, "sync", fail)
    assert not preferences.save_position(QPoint(30, 40))
    assert not preferences.save_management_size(QSize(640, 720))
    assert not preferences.save_ratio("recent", [3, 2])


def test_reported_access_error_is_treated_as_optional_settings_failure(settings, monkeypatch):
    """예외 없이 Qt 상태 코드로만 보고하는 접근 오류도 복원·저장 성공으로 표시하지 않는다."""
    preferences = ViewPreferences(settings)
    settings.setValue("ui/v1/window_position", QPoint(10, 20))
    monkeypatch.setattr(settings, "status", lambda: QSettings.Status.AccessError)
    assert preferences.read_position() is None
    assert not preferences.save_position(QPoint(30, 40))
