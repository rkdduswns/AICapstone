"""Phase 14 session, deletion, and shutdown API coverage."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.activity_store import ActivityStore
from backend.activity_tracker import ActivityTracker
from backend.app import create_app
from shared.activity import ActiveWindow


class _Detector:
    def get_active_window_handle(self):
        return 1

    def get_process_id(self, handle):
        return 1234

    def get_process_name(self, process_id):
        return "Code.exe"

    def normalize_app_name(self, process_name):
        return "Visual Studio Code"

    def get_window_title(self, handle):
        return "phase14.py"


def _save_activity(store, start, end, title="phase14.py"):
    return store.save_record(
        ActiveWindow("Visual Studio Code", "Code.exe", 1234, title),
        start,
        end,
        60_000,
    )


def test_session_routes_return_timeline_and_materials(tmp_path):
    store = ActivityStore(tmp_path / "api.db")
    record_id = _save_activity(
        store,
        "2026-11-19T09:00:00+00:00",
        "2026-11-19T09:05:00+00:00",
    )
    app = create_app(
        activity_store=store,
        activity_tracker=ActivityTracker(store=store, detector=None),
        browser_token="test-token",
        document_storage_dir=tmp_path / "documents",
    )
    with TestClient(app) as client:
        sessions_response = client.get("/sessions")
        assert sessions_response.status_code == 200
        assert sessions_response.json()["data"]["sessions"][0]["activity_count"] == 1

        detail = client.get(f"/sessions/{store.get_recent_sessions()[0]['id']}")
        assert detail.status_code == 200
        assert detail.json()["data"]["activities"][0]["id"] == record_id
        assert detail.json()["data"]["activities_pagination"] == {
            "limit": 200, "offset": 0, "total": 1, "has_more": False
        }
        assert detail.json()["data"]["materials"] == {"documents": [], "web_pages": []}
        assert client.get("/sessions/99999").status_code == 404
        assert client.get("/sessions/0").status_code == 422


def test_delete_activity_and_delete_all_api_require_correct_target_and_confirmation(tmp_path):
    store = ActivityStore(tmp_path / "delete.db")
    document_dir = tmp_path / "documents"
    document_dir.mkdir()
    activity_id = _save_activity(
        store,
        "2026-11-19T09:00:00+00:00",
        "2026-11-19T09:05:00+00:00",
    )
    stored_copy = document_dir / "stored.pdf"
    stored_copy.write_text("app-owned copy", encoding="utf-8")
    document_id = store.save_document_record(
        stored_copy,
        "document text",
        "2026-11-19T09:03:00+00:00",
        context_id=activity_id,
    )
    app = create_app(
        activity_store=store,
        activity_tracker=ActivityTracker(store=store, detector=None),
        browser_token="test-token",
        document_storage_dir=document_dir,
    )
    with TestClient(app) as client:
        missing = client.delete("/records/99999")
        assert missing.status_code == 404

        deleted = client.delete(f"/records/{activity_id}")
        assert deleted.status_code == 200
        assert store.get_record(activity_id) is None
        assert store.get_document_file_path(document_id) is None
        assert not stored_copy.exists()

        second_id = _save_activity(
            store,
            "2026-11-19T10:00:00+00:00",
            "2026-11-19T10:05:00+00:00",
        )
        all_delete_copy = document_dir / "all-delete.docx"
        all_delete_copy.write_text("stored copy", encoding="utf-8")
        store.save_document_record(
            all_delete_copy,
            "document text",
            "2026-11-19T10:03:00+00:00",
            context_id=second_id,
        )
        confirm_required = client.delete("/records")
        assert confirm_required.status_code == 400
        assert store.get_record(second_id) is not None

        all_deleted = client.delete("/records?confirm=true")
        assert all_deleted.status_code == 200
        assert store.get_record(second_id) is None
        assert not all_delete_copy.exists()
        assert client.get("/sessions").json()["data"]["sessions"] == []


def test_app_shutdown_flushes_current_activity_once(tmp_path):
    store = ActivityStore(tmp_path / "shutdown.db")
    clock = [100.0]
    current_time = [datetime(2026, 11, 26, 8, 0, tzinfo=timezone.utc)]
    tracker = ActivityTracker(
        detector=_Detector(),
        clock=lambda: clock[0],
        now=lambda: current_time[0],
        store=store,
    )
    app = create_app(
        activity_store=store,
        activity_tracker=tracker,
        browser_token="test-token",
        document_storage_dir=tmp_path / "documents",
    )
    with TestClient(app) as client:
        response = client.get("/activity/current")
        assert response.status_code == 200
        clock[0] += 90.0
        current_time[0] = datetime(2026, 11, 26, 8, 1, 30, tzinfo=timezone.utc)

    records = store.get_recent_records()
    assert len(records) == 1
    assert records[0].active_duration_ms == 90_000
    tracker.finish()
    assert len(store.get_recent_records()) == 1


def test_individual_document_and_browser_deletion_routes(tmp_path):
    store = ActivityStore(tmp_path / "source-delete.db")
    activity_id = _save_activity(
        store,
        "2026-11-19T09:00:00+00:00",
        "2026-11-19T09:05:00+00:00",
    )
    external_file = tmp_path / "user-original.pdf"
    external_file.write_text("original file", encoding="utf-8")
    document_id = store.save_document_record(
        external_file,
        "document text",
        "2026-11-19T09:02:00+00:00",
        context_id=activity_id,
    )
    browser_id = store.save_browser_source_record(
        "chrome", "https://example.com", "Example", "2026-11-19T09:03:00+00:00"
    )
    content_id = store.save_browser_content_record(
        browser_id, "page content", "2026-11-19T09:04:00+00:00"
    )
    store.save_search_source_and_chunks(
        source_kind="web",
        captured_at="2026-11-19T09:04:00+00:00",
        chunks=["indexed page body"],
        browser_source_id=browser_id,
    )
    app = create_app(
        activity_store=store,
        activity_tracker=ActivityTracker(store=store, detector=None),
        browser_token="test-token",
        document_storage_dir=tmp_path / "managed-documents",
    )
    with TestClient(app) as client:
        assert client.delete(f"/documents/{document_id}").status_code == 200
        assert external_file.exists(), "a user-owned original file must never be removed"

        assert client.delete(f"/browser/content/{content_id}").status_code == 200
        assert store.get_browser_content_record(browser_id) is None
        assert store.get_browser_source_record(browser_id) is not None
        connection = store._connect()
        try:
            assert connection.execute("SELECT COUNT(*) FROM search_sources").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM search_chunks").fetchone()[0] == 0
        finally:
            connection.close()

        assert client.delete(f"/browser/source/{browser_id}").status_code == 200
        assert store.get_browser_source_record(browser_id) is None
        assert client.delete(f"/browser/source/{browser_id}").status_code == 404


def test_search_endpoint_response_time_with_hundreds_of_records(tmp_path):
    """Exercise indexed metadata search at a modest realistic history size."""
    import time

    store = ActivityStore(tmp_path / "search-latency.db")
    for index in range(300):
        minute = index
        hour = 9 + minute // 60
        minute %= 60
        day = 19 + (hour // 24)
        hour %= 24
        start = f"2026-11-{day:02d}T{hour:02d}:{minute:02d}:00+00:00"
        end = f"2026-11-{day:02d}T{hour:02d}:{minute:02d}:30+00:00"
        _save_activity(store, start, end, f"phase14 benchmark {index}.py")

    app = create_app(
        activity_store=store,
        activity_tracker=ActivityTracker(store=store, detector=None),
        browser_token="test-token",
        document_storage_dir=tmp_path / "documents",
    )
    with TestClient(app) as client:
        started = time.perf_counter()
        response = client.get("/records/search?keyword=phase14&limit=20")
        elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert len(response.json()["data"]["records"]) == 20
    assert elapsed < 2.0

    reopened = ActivityStore(tmp_path / "search-latency.db")
    persisted_sessions = reopened.get_recent_sessions()
    assert len(persisted_sessions) == 1
    assert persisted_sessions[0]["activity_count"] == 300
    assert len(reopened.get_session_records(persisted_sessions[0]["id"])) == 200

    restarted_app = create_app(
        activity_store=reopened,
        activity_tracker=ActivityTracker(store=reopened, detector=None),
        browser_token="test-token",
        document_storage_dir=tmp_path / "documents",
    )
    with TestClient(restarted_app) as restarted_client:
        page = restarted_client.get(
            f"/sessions/{persisted_sessions[0]['id']}?limit=100&offset=200"
        )
        assert page.status_code == 200
        assert len(page.json()["data"]["activities"]) == 100
        assert page.json()["data"]["activities_pagination"]["has_more"] is False


def test_app_default_tracker_uses_injected_store_and_privacy_policy(tmp_path):
    from backend.privacy import PrivacyPolicy

    store = ActivityStore(tmp_path / "injected.db")
    policy = PrivacyPolicy()
    app = create_app(
        activity_store=store,
        privacy_policy=policy,
        browser_token="test-token",
        document_storage_dir=tmp_path / "documents",
    )

    assert app.state.activity_tracker._get_store() is store
    assert app.state.activity_tracker._privacy_policy is policy
    assert app.state.browser_privacy_policy is policy
