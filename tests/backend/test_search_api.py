"""Integration tests for explicit metadata search."""

from fastapi.testclient import TestClient

from backend.activity_store import ActivityStore
from backend.app import create_app
from backend.privacy import PrivacyPolicy
from shared.activity import ActiveWindow


def _save_activity(store: ActivityStore, *, title: str, ended_at: str) -> int:
    return store.save_record(
        window=ActiveWindow(
            application="Visual Studio Code",
            process_name="Code.exe",
            process_id=1234,
            window_title=title,
        ),
        started_at="2026-10-15T08:00:00+00:00",
        ended_at=ended_at,
        active_duration_ms=60_000,
    )


def _client(store: ActivityStore, policy: PrivacyPolicy | None = None) -> TestClient:
    return TestClient(
        create_app(
            activity_store=store,
            browser_token="test-browser-token",
            privacy_policy=policy,
        )
    )


def test_search_returns_activity_and_web_metadata(tmp_path):
    store = ActivityStore(tmp_path / "activity.db")
    _save_activity(
        store,
        title="Planning notes",
        ended_at="2026-10-15T08:02:00+00:00",
    )
    store.save_browser_source_record(
        browser="chrome",
        url="https://example.com/planning",
        page_title="Planning reference",
        captured_at="2026-10-15T08:03:00+00:00",
    )

    response = _client(store).get("/records/search")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["error"] is None
    assert payload["data"]["has_more"] is False
    assert {record["id"] for record in payload["data"]["records"]} == {
        "1",
        "web-1",
    }
    assert all("content" not in record for record in payload["data"]["records"])


def test_search_applies_keyword_process_and_time_as_and_filters(tmp_path):
    store = ActivityStore(tmp_path / "activity.db")
    _save_activity(
        store,
        title="Planning notes",
        ended_at="2026-10-15T08:02:00+00:00",
    )
    _save_activity(
        store,
        title="Planning archive",
        ended_at="2026-10-16T08:02:00+00:00",
    )

    response = _client(store).get(
        "/records/search",
        params={
            "keyword": "  PLAN  ",
            "process_name": "  CODE.EXE ",
            "active_from": "2026-10-15T08:01:00+00:00",
            "active_before": "2026-10-16T00:00:00+00:00",
            "sort": "oldest",
            "limit": 1,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["request"]["keyword"] == "PLAN"
    assert data["request"]["process_name"] == "code.exe"
    assert [record["id"] for record in data["records"]] == ["1"]
    assert data["has_more"] is False


def test_search_filters_pdf_and_docx_sources(tmp_path):
    store = ActivityStore(tmp_path / "activity.db")
    pdf_context = _save_activity(
        store,
        title="PDF context",
        ended_at="2026-10-15T08:02:00+00:00",
    )
    docx_context = _save_activity(
        store,
        title="DOCX context",
        ended_at="2026-10-15T09:02:00+00:00",
    )
    store.save_document_record(
        file_path=tmp_path / "report.pdf",
        file_name="report.pdf",
        extracted_text="private PDF body",
        captured_at="2026-10-15T08:03:00+00:00",
        context_id=pdf_context,
    )
    store.save_document_record(
        file_path=tmp_path / "notes.docx",
        file_name="notes.docx",
        extracted_text="private DOCX body",
        captured_at="2026-10-15T09:03:00+00:00",
        context_id=docx_context,
    )

    client = _client(store)
    pdf_response = client.get("/records/search", params={"source_type": "pdf"})
    document_response = client.get(
        "/records/search",
        params={"source_type": "document"},
    )

    assert [item["id"] for item in pdf_response.json()["data"]["records"]] == [
        str(pdf_context)
    ]
    assert {
        item["document"]["file_type"]
        for item in document_response.json()["data"]["records"]
    } == {"pdf", "docx"}
    assert "private PDF body" not in document_response.text
    assert "private DOCX body" not in document_response.text


def test_search_reports_more_only_when_an_extra_match_exists(tmp_path):
    store = ActivityStore(tmp_path / "activity.db")
    for day in (15, 16, 17):
        _save_activity(
            store,
            title="Repeated title",
            ended_at=f"2026-10-{day}T08:02:00+00:00",
        )

    response = _client(store).get("/records/search", params={"limit": 2})

    assert response.status_code == 200
    assert len(response.json()["data"]["records"]) == 2
    assert response.json()["data"]["has_more"] is True


def test_search_rejects_naive_or_reversed_time_boundaries(tmp_path):
    client = _client(ActivityStore(tmp_path / "activity.db"))

    naive = client.get(
        "/records/search",
        params={"active_from": "2026-10-15T08:00:00"},
    )
    reversed_bounds = client.get(
        "/records/search",
        params={
            "active_from": "2026-10-16T08:00:00+00:00",
            "active_before": "2026-10-15T08:00:00+00:00",
        },
    )

    assert naive.status_code == 422
    assert reversed_bounds.status_code == 422


def test_search_excludes_blocked_applications(tmp_path):
    store = ActivityStore(tmp_path / "activity.db")
    _save_activity(
        store,
        title="Private work",
        ended_at="2026-10-15T08:02:00+00:00",
    )
    policy = PrivacyPolicy(blocked_applications={"visual studio code"})

    response = _client(store, policy).get("/records/search")

    assert response.status_code == 200
    assert response.json()["data"]["records"] == []
    assert response.json()["data"]["has_more"] is False
