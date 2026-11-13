"""이름 변경 시 기존 설치의 토큰·DB가 끊기지 않는 경계를 검증한다."""

from pathlib import Path

import pytest

from backend.activity_store import ActivityStore
from backend.app import create_app


@pytest.mark.parametrize("new,legacy,explicit,expected", [
    (None, "legacy", None, "legacy"),
    ("new", "legacy", None, "new"),
    ("", "legacy", None, ""),
    ("new", "legacy", "explicit", "explicit"),
    ("new", "legacy", "", ""),
    (None, None, None, ""),
])
def test_browser_token_precedence(monkeypatch, new, legacy, explicit, expected):
    """명시 인수·새 환경변수·구형 환경변수 순서를 따르고 빈 값도 보존한다."""
    for key, value in [("GANGSEARCH_BROWSER_TOKEN", new),
                       ("CONTEXTTRACE_BROWSER_TOKEN", legacy)]:
        monkeypatch.delenv(key, raising=False)
        if value is not None:
            monkeypatch.setenv(key, value)
    app = create_app(browser_token=explicit, collection_interval=None)
    assert app.state.browser_token == expected


def test_default_db_reuses_existing_privacy_settings(tmp_path, monkeypatch):
    """기존 기본 경로의 일시정지 설정을 새 이름으로 실행해도 복원한다."""
    from backend.privacy_settings import StoredPrivacySettings

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    legacy_path = tmp_path / ".contexttrace" / "activity.db"
    old = ActivityStore(legacy_path)
    settings = StoredPrivacySettings(paused=True, blocked_processes=[], clipboard_enabled=False)
    old.update_privacy_settings({}, settings)
    restored = ActivityStore()
    assert restored._db_path == legacy_path
    assert restored.load_privacy_settings() == settings
