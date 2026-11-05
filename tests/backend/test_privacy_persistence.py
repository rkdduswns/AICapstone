"""설정 영속화와 복원 순서·실패 경계를 실제 SQLite와 HTTP로 검증한다."""

import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.activity_store import ActivityStore
from backend.activity_tracker import ActivityTracker
from backend.app import create_app
from backend.privacy import PrivacyPolicy
from backend.privacy_settings import StoredPrivacySettings

HEADERS = {"X-ContextTrace-Client": "desktop"}
AUTH = {"Authorization": "Bearer persistence-test-token"}


def saved_values(settings):
    """저장 모델의 공개 필드만 비교하여 직렬화 구현 방식과 테스트를 분리한다."""
    return {
        "paused": settings.paused,
        "blocked_processes": settings.blocked_processes,
        "clipboard_enabled": settings.clipboard_enabled,
    }


def seed_settings(store, **changes):
    """기존 앱이 저장한 설정을 실제 저장 메서드로 준비한다."""
    defaults = StoredPrivacySettings(paused=False, blocked_processes=[], clipboard_enabled=False)
    return store.update_privacy_settings(changes, defaults)


def runtime(store, policy=None, collection_interval=None):
    """OS 감지와 복사 원문만 주입하고 추적기·API·저장소는 실제 구현을 쓴다."""
    policy = policy if policy is not None else PrivacyPolicy()
    state = SimpleNamespace(
        detector_calls=0, title_calls=0, tick=0.0,
        process="chrome.exe", sequence=1, text="재시작 이전 복사",
    )

    def handle():
        """설정 복원 전에 실제 감지가 실행되지 않았는지 관찰한다."""
        state.detector_calls += 1
        return 1

    def title(handle):
        """차단 프로그램의 제목 읽기 전 정책이 복원되는지 관찰한다."""
        state.title_calls += 1
        return "가상 영속화 검증 창"

    detector = SimpleNamespace(
        get_active_window_handle=handle,
        get_process_id=lambda handle: 42,
        get_process_name=lambda pid: state.process,
        normalize_app_name=lambda name: "Google Chrome" if name == "chrome.exe" else name,
        get_window_title=title,
    )
    tracker = ActivityTracker(
        detector=detector, store=store, privacy_policy=policy,
        clock=lambda: state.tick,
        now=lambda: datetime(2026, 11, 5, tzinfo=timezone.utc),
    )
    app = create_app(
        activity_tracker=tracker, activity_store=store, privacy_policy=policy,
        collection_interval=collection_interval, clipboard_reader=lambda: state.text,
        browser_token="persistence-test-token",
    )
    return SimpleNamespace(app=app, state=state, policy=policy)


def corrupt_settings(store, missing_paused=False):
    """타입 오류나 필수 필드 누락이 있는 기존 저장 행으로 복원 실패를 재현한다."""
    payload = '{"blocked_processes":[],"clipboard_enabled":false}' if missing_paused else (
        '{"paused":"private-invalid-value",'
        '"blocked_processes":[],"clipboard_enabled":false}'
    )
    with sqlite3.connect(store._db_path) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS privacy_settings ("
            "singleton INTEGER PRIMARY KEY CHECK(singleton = 1), payload TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT OR REPLACE INTO privacy_settings(singleton, payload) VALUES (1, ?)",
            (payload,),
        )


def assert_unavailable(response):
    """복원·저장 오류는 원문을 노출하지 않는 공통 실패 응답이어야 한다."""
    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert isinstance(body["error"]["message"], str)
    assert body["error"]["message"]
    assert "private-invalid-value" not in response.text
    assert "private-database-failure" not in response.text


def test_app_construction_does_not_open_database(monkeypatch):
    """앱 객체 생성이나 모듈 초기화만으로 사용자 DB를 열지 않는다."""
    def forbid_database(self):
        """생성 과정에서 저장소를 조회하면 즉시 실패시킨다."""
        raise AssertionError("앱 생성 전에 DB에 접근하면 안 됩니다.")

    monkeypatch.setattr(ActivityTracker, "_get_store", forbid_database)
    app = create_app(collection_interval=None, clipboard_reader=lambda: None)
    assert app.state.activity_store is None


def test_missing_settings_keep_initial_defaults(tmp_path):
    """설정 행이 없는 첫 실행은 수집 허용·빈 차단 목록·복사 꺼짐을 유지한다."""
    store = ActivityStore(tmp_path / "first-run.db")
    assert store.load_privacy_settings() is None
    execution = runtime(store)

    with closing(TestClient(execution.app)) as client:
        response = client.get("/privacy")

    assert response.status_code == 200
    settings = response.json()["data"]["settings"]
    assert settings["paused"] is False
    assert settings["blocked_processes"] == []
    assert settings["clipboard_enabled"] is False
    assert settings["blocked_urls"] is None


def test_saved_pause_overrides_injected_policy_before_first_detection(tmp_path):
    """저장된 일시정지는 주입 기본 정책보다 우선하며 첫 감지부터 차단한다."""
    store = ActivityStore(tmp_path / "paused.db")
    seed_settings(store, paused=True, blocked_processes=["winword.exe"], clipboard_enabled=True)
    execution = runtime(store, PrivacyPolicy(collection_paused=False))

    with closing(TestClient(execution.app)) as client:
        response = client.get("/activity/current")

    assert response.status_code == 200
    assert response.json()["data"]["collection_status"] == "paused"
    assert execution.state.detector_calls == 0
    assert execution.policy.collection_paused is True
    assert execution.policy.blocked_applications == {"winword.exe"}
    assert execution.app.state.clipboard_enabled is True
    assert store.get_recent_records() == []


def test_saved_block_list_is_restored_before_reading_window_title(tmp_path):
    """복원된 프로그램 차단은 첫 샘플의 제목 읽기와 저장 이전에 적용된다."""
    store = ActivityStore(tmp_path / "blocked.db")
    seed_settings(store, blocked_processes=["chrome.exe"])
    execution = runtime(store)

    with closing(TestClient(execution.app)) as client:
        response = client.get("/activity/current")

    assert response.json()["data"]["collection_status"] == "blocked"
    assert execution.state.detector_calls == 1
    assert execution.state.title_calls == 0
    assert store.get_recent_records() == []


def test_first_browser_ingestion_obeys_restored_pause_without_lifespan(tmp_path):
    """서버 시작 훅 없는 첫 수신 요청도 저장된 일시정지를 우회하지 못한다."""
    store = ActivityStore(tmp_path / "browser.db")
    seed_settings(store, paused=True)
    execution = runtime(store)

    with closing(TestClient(execution.app)) as client:
        response = client.post(
            "/browser/source", headers=AUTH,
            json={"browser": "chrome", "url": "https://example.test/page", "page_title": "가상"},
        )

    assert response.status_code == 403
    assert store.get_recent_browser_source_records() == []
    assert execution.state.detector_calls == 0


@pytest.mark.parametrize("clear", [False, True], ids=["retain-values", "clear-values"])
def test_successful_updates_survive_new_app_and_database_instance(tmp_path, clear):
    """설정 사용과 명시적인 해제 모두 정상 응답 후 실제 DB와 새 앱에 유지된다."""
    db_path = tmp_path / "restart.db"
    store = ActivityStore(db_path)
    execution = runtime(store)

    with TestClient(execution.app) as client:
        assert client.put("/privacy/paused", headers=HEADERS, json={"paused": True}).status_code == 200
        assert client.put(
            "/privacy/blocked-processes", headers=HEADERS,
            json={"blocked_processes": [" WINWORD.EXE ", "chrome.exe", "chrome.exe"]},
        ).status_code == 200
        assert client.put(
            "/privacy/clipboard", headers=HEADERS, json={"clipboard_enabled": True},
        ).status_code == 200
        if clear:
            assert client.put(
                "/privacy/paused", headers=HEADERS, json={"paused": False},
            ).status_code == 200
            assert client.put(
                "/privacy/blocked-processes", headers=HEADERS, json={"blocked_processes": []},
            ).status_code == 200
            assert client.put(
                "/privacy/clipboard", headers=HEADERS, json={"clipboard_enabled": False},
            ).status_code == 200

    expected = {
        "paused": not clear,
        "blocked_processes": [] if clear else ["chrome.exe", "winword.exe"],
        "clipboard_enabled": not clear,
    }
    reopened = ActivityStore(db_path)
    assert saved_values(reopened.load_privacy_settings()) == expected
    restarted = runtime(reopened)
    with TestClient(restarted.app) as client:
        settings = client.get("/privacy").json()["data"]["settings"]
    assert {name: settings[name] for name in expected} == expected
    if not clear:
        assert restarted.state.detector_calls == 0


def test_stale_apps_patch_latest_saved_row_without_losing_other_fields(tmp_path):
    """같은 DB를 먼저 읽은 두 앱도 서로 다른 필드의 최신 저장값을 덮어쓰지 않는다."""
    db_path = tmp_path / "shared.db"
    first = runtime(ActivityStore(db_path))
    second = runtime(ActivityStore(db_path))

    with closing(TestClient(first.app)) as first_client, closing(TestClient(second.app)) as second_client:
        assert first_client.get("/privacy").status_code == 200
        assert second_client.get("/privacy").status_code == 200
        assert first_client.put(
            "/privacy/paused", headers=HEADERS, json={"paused": True},
        ).status_code == 200
        response = second_client.put(
            "/privacy/blocked-processes", headers=HEADERS,
            json={"blocked_processes": ["chrome.exe"]},
        )
        assert response.status_code == 200
        assert response.json()["data"]["settings"]["paused"] is True
        response = first_client.put(
            "/privacy/clipboard", headers=HEADERS, json={"clipboard_enabled": True},
        )
        assert response.status_code == 200
        assert response.json()["data"]["settings"]["blocked_processes"] == ["chrome.exe"]

    assert saved_values(ActivityStore(db_path).load_privacy_settings()) == {
        "paused": True, "blocked_processes": ["chrome.exe"], "clipboard_enabled": True,
    }


def test_settings_initialization_preserves_existing_activity_rows(tmp_path):
    """설정 테이블 없는 구형 DB를 열고 설정을 저장해도 기존 활동 행은 보존한다."""
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "CREATE TABLE activity_records (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "application TEXT NOT NULL, process_name TEXT NOT NULL, process_id INTEGER NOT NULL, "
            "window_title TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT NOT NULL, "
            "active_duration_ms INTEGER NOT NULL)"
        )
        connection.execute(
            "INSERT INTO activity_records VALUES (7, ?, ?, ?, ?, ?, ?, ?)",
            ("기존 프로그램", "legacy.exe", 7, "기존 작업",
             "2026-10-26T03:00:00Z", "2026-10-26T03:00:01Z", 1000),
        )
    store = ActivityStore(db_path)
    original = store.get_record(7)
    assert store.load_privacy_settings() is None
    execution = runtime(store)

    with closing(TestClient(execution.app)) as client:
        assert client.put("/privacy/paused", headers=HEADERS, json={"paused": True}).status_code == 200

    reopened = ActivityStore(db_path)
    assert reopened.get_record(7) == original
    assert reopened.load_privacy_settings().paused is True


@pytest.mark.parametrize("missing_paused", [False, True], ids=["wrong-type", "missing-paused"])
def test_invalid_saved_settings_block_all_requests_without_lifespan(tmp_path, missing_paused):
    """잘못된 저장값은 상태 조회나 수신 전에 실패하고 기본 허용으로 돌아가지 않는다."""
    store = ActivityStore(tmp_path / "invalid-http.db")
    corrupt_settings(store, missing_paused)
    execution = runtime(store)

    with closing(TestClient(execution.app, raise_server_exceptions=False)) as client:
        assert_unavailable(client.get("/health"))
        assert_unavailable(client.get("/activity/current"))
        assert_unavailable(client.post(
            "/browser/source", headers=AUTH,
            json={"browser": "chrome", "url": "https://example.test/page", "page_title": "가상"},
        ))

    assert execution.state.detector_calls == 0
    assert store.get_recent_records() == []
    assert store.get_recent_browser_source_records() == []


@pytest.mark.parametrize("missing_paused", [False, True], ids=["wrong-type", "missing-paused"])
def test_invalid_saved_settings_fail_lifespan_before_any_detection(tmp_path, missing_paused):
    """복원 불가능한 정책으로 서버를 시작하거나 수집 루프를 예약하지 않는다."""
    store = ActivityStore(tmp_path / "invalid-startup.db")
    corrupt_settings(store, missing_paused)
    execution = runtime(store)

    with pytest.raises(RuntimeError):
        with TestClient(execution.app):
            pytest.fail("손상된 설정으로 서버가 시작되면 안 됩니다.")

    assert execution.state.detector_calls == 0


def test_failed_save_keeps_previous_database_and_memory_settings(tmp_path, monkeypatch):
    """저장 실패를 성공으로 응답하거나 아직 저장되지 않은 설정을 메모리에 적용하지 않는다."""
    store = ActivityStore(tmp_path / "save-failure.db")
    previous = seed_settings(store, blocked_processes=["winword.exe"], clipboard_enabled=True)
    execution = runtime(store)

    def fail_save(changes, defaults):
        """디스크 쓰기 오류를 저장 경계에서 재현한다."""
        raise sqlite3.OperationalError("private-database-failure")

    with closing(TestClient(execution.app, raise_server_exceptions=False)) as client:
        assert client.get("/privacy").status_code == 200
        monkeypatch.setattr(store, "update_privacy_settings", fail_save)
        response = client.put("/privacy/paused", headers=HEADERS, json={"paused": True})
        assert_unavailable(response)
        settings = client.get("/privacy").json()["data"]["settings"]

    assert execution.policy.collection_paused is False
    assert execution.policy.blocked_applications == {"winword.exe"}
    assert execution.app.state.clipboard_enabled is True
    assert {name: settings[name] for name in saved_values(previous)} == saved_values(previous)
    assert ActivityStore(store._db_path).load_privacy_settings() == previous


def test_memory_changes_only_after_database_commit(tmp_path, monkeypatch):
    """저장 메서드가 반환하기 전에 정책 메모리를 변경하지 않는 순서를 검증한다."""
    store = ActivityStore(tmp_path / "commit-order.db")
    seed_settings(store)
    execution = runtime(store)
    original_update = store.update_privacy_settings
    committed = []

    def observe_commit(changes, defaults):
        """실제 커밋 전후에 기존 메모리 정책이 유지되는지 확인한다."""
        assert execution.policy.collection_paused is False
        result = original_update(changes, defaults)
        committed.append(ActivityStore(store._db_path).load_privacy_settings().paused)
        assert execution.policy.collection_paused is False
        return result

    with closing(TestClient(execution.app)) as client:
        assert client.get("/privacy").status_code == 200
        monkeypatch.setattr(store, "update_privacy_settings", observe_commit)
        response = client.put("/privacy/paused", headers=HEADERS, json={"paused": True})

    assert response.status_code == 200
    assert committed == [True]
    assert execution.policy.collection_paused is True


def test_restored_clipboard_enable_resets_baseline_and_skips_old_copy(tmp_path):
    """클립보드 사용 복원은 재시작 이전 복사를 건너뛰고 이후 새 복사만 저장한다."""
    store = ActivityStore(tmp_path / "clipboard-baseline.db")
    seed_settings(store, clipboard_enabled=True)
    execution = runtime(store)
    collector = execution.app.state.clipboard_collector
    collector._stamp = lambda: (execution.state.sequence, 42)
    collector.reset_baseline()
    # 앱 객체 생성과 실제 복원 사이에 있던 복사도 이전 내용으로 취급한다.
    execution.state.sequence = 2

    with closing(TestClient(execution.app)) as client:
        assert client.get("/activity/current").status_code == 200
        assert store.get_recent_clipboard_records() == []
        execution.state.sequence = 3
        execution.state.text = "복원 이후 새 복사"
        assert client.get("/activity/current").status_code == 200

    assert [record.content for record in store.get_recent_clipboard_records()] == ["복원 이후 새 복사"]


def test_failed_clipboard_baseline_recovers_without_saving_old_copy(tmp_path):
    """커밋 뒤 기준점 갱신이 실패해도 복원 전 복사를 새 이벤트로 저장하지 않는다."""
    store = ActivityStore(tmp_path / "clipboard-baseline-recovery.db")
    execution = runtime(store)
    collector = execution.app.state.clipboard_collector
    collector._stamp = lambda: (execution.state.sequence, 42)
    collector.reset_baseline()

    def unavailable_stamp():
        """설정 커밋 직후 클립보드 변경 번호 조회 실패를 재현한다."""
        raise OSError("private-database-failure")

    with closing(TestClient(execution.app, raise_server_exceptions=False)) as client:
        assert client.get("/privacy").status_code == 200
        first_record = store.get_recent_records()[0]
        execution.state.tick = 2
        collector._stamp = unavailable_stamp
        response = client.put(
            "/privacy/clipboard", headers=HEADERS, json={"clipboard_enabled": True},
        )
        assert_unavailable(response)
        assert execution.policy.collection_paused is True
        assert store.load_privacy_settings().clipboard_enabled is True
        assert store.get_record(first_record.id).active_duration_ms == 2000

        collector._stamp = lambda: (execution.state.sequence, 42)
        execution.state.tick = 100
        execution.state.sequence = 2
        execution.state.text = "복원 전 오래된 복사"
        response = client.get("/activity/current")
        assert response.status_code == 200
        recovered = response.json()["data"]
        # 오류로 수집을 중단한 시간은 이전 기록이나 새 활성 구간에 누적하지 않는다.
        assert store.get_record(first_record.id).active_duration_ms == 2000
        assert recovered["record_id"] != str(first_record.id)
        assert recovered["timing"]["active_duration_ms"] == 0
        assert store.get_recent_clipboard_records() == []

        execution.state.sequence = 3
        execution.state.text = "기준점 복원 이후 새 복사"
        assert client.get("/activity/current").status_code == 200

    assert [record.content for record in store.get_recent_clipboard_records()] == [
        "기준점 복원 이후 새 복사",
    ]


def test_collection_loop_retries_settings_recovery_without_new_http_request(tmp_path):
    """수집 루프는 일시적인 설정 복원 실패 후 새 HTTP 요청 없이 복구를 재시도한다."""
    store = ActivityStore(tmp_path / "background-recovery.db")
    seed_settings(store, paused=True)
    execution = runtime(store, collection_interval=0.01)
    state = execution.state
    state.stamp_broken = False
    state.failed_stamp_calls = 0

    def stamp():
        """실제 OS 대신 복원 시도 횟수와 일시적인 변경 번호 조회 실패를 제공한다."""
        if state.stamp_broken:
            state.failed_stamp_calls += 1
            raise OSError("private-database-failure")
        return (state.sequence, 42)

    def wait_until(predicate):
        """별도 서버 스레드의 처리를 최대 2초만 기다리고 무한 대기를 피한다."""
        deadline = time.monotonic() + 2
        while not predicate() and time.monotonic() < deadline:
            time.sleep(0.01)
        return predicate()

    execution.app.state.clipboard_collector._stamp = stamp

    with TestClient(execution.app) as client:
        assert client.get("/health").status_code == 200
        state.stamp_broken = True
        response = client.put(
            "/privacy/clipboard", headers=HEADERS, json={"clipboard_enabled": True},
        )
        assert_unavailable(response)
        # 첫 설정 적용 실패 외에 백그라운드 루프의 복원 재시도가 있어야 한다.
        assert wait_until(lambda: state.failed_stamp_calls >= 2)

        state.stamp_broken = False
        # 추가 요청으로 복원을 유발하지 않고 서버 루프 자체의 회복만 기다린다.
        assert wait_until(lambda: execution.app.state.clipboard_enabled is True)
        assert execution.policy.collection_paused is True
        assert execution.state.detector_calls == 0
        assert store.get_recent_records() == []
        assert store.get_recent_clipboard_records() == []
