"""실제 추적기·정책·SQLite를 사용하여 Client용 API의 연결 경계를 검증한다."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.activity_store import ActivityStore
from backend.activity_tracker import ActivityTracker
from backend.app import create_app
from backend.clipboard_collector import ClipboardCollector

HEADERS = {"X-ContextTrace-Client": "desktop"}


@pytest.fixture
def runtime(tmp_path):
    """가상 창/시계/복사 원문만 주입하며 실제 API와 DB 구현은 교체하지 않는다."""
    clock = SimpleNamespace(tick=0.0, process="chrome.exe", title="가상 조사", reads=0,
                            text="가상 복사 내용")

    def process_name(pid):
        """차단·일시정지 경계에서 감지 호출 여부를 셀 수 있게 한다."""
        clock.reads += 1
        return clock.process

    detector = SimpleNamespace(
        get_active_window_handle=lambda: 1, get_process_id=lambda handle: 42,
        get_process_name=process_name, normalize_app_name=lambda name: name,
        get_window_title=lambda handle: clock.title,
    )
    store = ActivityStore(tmp_path / "activity.db")
    tracker = ActivityTracker(
        detector=detector, store=store, clock=lambda: clock.tick,
        now=lambda: datetime(2026, 10, 21, tzinfo=timezone.utc) + timedelta(seconds=clock.tick),
    )
    app = create_app(activity_tracker=tracker, activity_store=store, browser_token="test-token",
                     clipboard_reader=lambda: clock.text, collection_interval=None)
    return TestClient(app), clock, store, tracker


def test_settings_control_actual_collection_and_preserve_other_fields(runtime):
    """API에서 적용한 정책이 감지·저장에도 쓰이며 일시정지 시간은 작업 시간에 섞이지 않는다."""
    client, clock, store, tracker = runtime
    assert client.get("/activity/current").json()["data"]["collection_status"] == "collecting"
    clock.tick = 2
    response = client.put("/privacy/paused", json={"paused": True}, headers=HEADERS)
    assert response.json()["data"]["recording"] == {"allowed": False, "reason": "paused"}
    reads = clock.reads
    clock.tick = 100
    assert client.get("/activity/current").json()["data"]["window"] is None
    assert clock.reads == reads
    record = store.get_recent_records()[0]
    assert record.active_duration_ms == 2000
    assert len(store.get_recent_records()) == 1
    # 같은 목표값을 다시 보내도 새 기록을 만들지 않는다.
    client.put("/privacy/paused", json={"paused": True}, headers=HEADERS)
    assert len(store.get_recent_records()) == 1
    response = client.put("/privacy/blocked-processes",
                          json={"blocked_processes": [" CHROME.EXE ", "chrome.exe"]}, headers=HEADERS)
    assert response.json()["data"]["settings"]["blocked_processes"] == ["chrome.exe"]
    assert response.json()["data"]["settings"]["paused"] is True
    response = client.put("/privacy/paused", json={"paused": False}, headers=HEADERS)
    assert response.json()["data"]["recording"]["reason"] == "blocked_program"
    assert client.get("/activity/current").json()["data"]["collection_status"] == "blocked"
    assert len(store.get_recent_records()) == 1
    client.put("/privacy/blocked-processes", json={"blocked_processes": []}, headers=HEADERS)
    clock.tick = 101
    tracker.finish()
    assert store.get_recent_records()[0].active_duration_ms == 1000


@pytest.mark.parametrize("body", [{"paused": "false"}, {"paused": 1},
                                  {"paused": False, "clipboard_enabled": True}])
def test_invalid_settings_do_not_change_state(runtime, body):
    """형식이 잘못되거나 다른 설정을 섞은 요청은 원래 정책을 바꾸지 않는다."""
    client, _, _, _ = runtime
    assert client.put("/privacy/paused", json=body, headers=HEADERS).status_code == 422
    assert client.get("/privacy").json()["data"]["settings"]["paused"] is False


@pytest.mark.parametrize("names", [["C:/private/app.exe"], ["*.exe"], ["browser"], [42]])
def test_invalid_process_rules_are_rejected(runtime, names):
    """경로·패턴·잘못된 타입을 실행 파일 차단 규칙으로 저장하지 않는다."""
    client, _, _, _ = runtime
    assert client.put("/privacy/blocked-processes", json={"blocked_processes": names},
                      headers=HEADERS).status_code == 422


@pytest.mark.parametrize("headers", [{}, {**HEADERS, "Origin": "https://example.test"}])
def test_browser_style_writes_are_denied(runtime, headers):
    """JSON 전송만으로 웹 페이지가 데스크톱의 수집 설정을 변경할 수 없게 한다."""
    client, _, _, _ = runtime
    assert client.put("/privacy/paused", json={"paused": True}, headers=headers).status_code == 403


def test_clipboard_uses_same_store_and_session_only(runtime):
    """목록·추적·복사 조회가 같은 DB를 쓰며 다른 작업의 복사 내용은 섞이지 않는다."""
    client, clock, store, _ = runtime
    assert client.get("/privacy").json()["data"]["settings"]["clipboard_enabled"] is False
    client.put("/privacy/clipboard", json={"clipboard_enabled": True}, headers=HEADERS)
    clock.tick = 1
    client.get("/activity/current")
    clock.process, clock.tick = "word.exe", 2
    client.get("/activity/current")
    records = client.get("/records/recent").json()["data"]["records"]
    assert len(records) == 1
    record_id = records[0]["id"]
    assert store.get_recent_clipboard_records()[0].application == "word.exe"
    response = client.get("/records/clipboard", params={"record_id": record_id})
    assert response.status_code == 200
    assert [row["text"] for row in response.json()["data"]["entries"]] == ["가상 복사 내용"]
    client.put("/privacy/clipboard", json={"clipboard_enabled": False}, headers=HEADERS)
    count = len(store.get_recent_clipboard_records())
    clock.text = "꺼진 뒤 내용"
    client.get("/activity/current")
    assert len(store.get_recent_clipboard_records()) == count
    assert client.get("/records/clipboard?record_id=999999").status_code == 404


@pytest.mark.parametrize("content", ["password=never-store", "person@example.test", "x" * 10001])
def test_sensitive_or_oversized_clipboard_is_not_stored(runtime, content):
    """Backend의 보호 판정을 통과하지 못한 원문은 DB에 저장하지 않는다."""
    client, clock, store, _ = runtime
    client.put("/privacy/clipboard", json={"clipboard_enabled": True}, headers=HEADERS)
    clock.text = content
    client.get("/activity/current")
    assert store.get_recent_clipboard_records() == []


def test_clipboard_limit_and_missing_record_distinguish_empty(runtime):
    """초과 항목 표시와 빈 결과, 삭제된 작업을 서로 구분한다."""
    client, clock, store, tracker = runtime
    client.get("/activity/current")
    clock.tick = 1
    tracker.finish()
    record = store.get_recent_records()[0]
    assert client.get(f"/records/clipboard?record_id={record.id}").json()["data"]["entries"] == []
    for index in range(3):
        store.save_clipboard_record(record.application, record.started_at,
                                    f"2026-10-21T00:00:0{index}+00:00", str(index))
    data = client.get(f"/records/clipboard?record_id={record.id}&limit=2").json()["data"]
    assert data["has_more"] is True
    assert [row["text"] for row in data["entries"]] == ["2", "1"]
    assert client.get("/records/clipboard?record_id=-1").status_code == 422
    assert client.get("/records/recent?limit=21").status_code == 422


def test_shutdown_flushes_last_session(runtime):
    """창 전환이 없어도 Backend 정상 종료가 마지막 작업을 저장한다."""
    client, clock, store, _ = runtime
    with client:
        client.get("/activity/current")
        clock.tick = 3
    assert store.get_recent_records()[0].active_duration_ms == 3000


def test_pause_blocks_browser_ingestion(runtime):
    """Client의 일시정지가 브라우저 수신 API에도 동일하게 적용된다."""
    client, _, store, _ = runtime
    client.put("/privacy/paused", json={"paused": True}, headers=HEADERS)
    response = client.post("/browser/source", headers={"Authorization": "Bearer test-token"},
                           json={"browser": "chrome", "url": "https://example.test/page",
                                 "page_title": "가상 페이지"})
    assert response.status_code == 403
    assert store.get_recent_browser_source_records() == []


def test_clipboard_sequence_and_owner_prevent_stale_association(runtime):
    """네이티브 경로와 같은 변경 번호·소유자 검증을 주입하여 오래된 내용을 제외한다."""
    _, _, store, tracker = runtime
    stamp = SimpleNamespace(sequence=1, owner=42, text="가상 복사")
    collector = ClipboardCollector(tracker, clipboard_reader=lambda: stamp.text,
                                   clipboard_stamp=lambda: (stamp.sequence, stamp.owner))
    collector.set_enabled(True)
    assert collector.collect_once() is None
    stamp.sequence = 2
    assert collector.collect_once() is not None
    assert collector.collect_once() is None
    stamp.sequence, stamp.owner = 3, 999
    assert collector.collect_once() is None
    assert len(store.get_recent_clipboard_records()) == 1
    stamp.sequence, stamp.owner = 4, 42
    collector.reset_baseline()
    assert collector.collect_once() is None


def test_ambiguous_legacy_session_does_not_mix_clipboard(runtime):
    """과거 스키마의 세션 키가 충돌하면 다른 작업의 복사 내용을 추측해서 반환하지 않는다."""
    client, clock, store, tracker = runtime
    client.get("/activity/current")
    clock.tick = 1
    tracker.finish()
    first = store.get_recent_records()[0]
    from shared.activity import ActiveWindow

    store.save_record(ActiveWindow(first.application, first.process_name, first.process_id, "다른 창"),
                      first.started_at, first.ended_at, 1000)
    store.save_clipboard_record(first.application, first.started_at, first.ended_at, "모호한 원문")
    data = client.get(f"/records/clipboard?record_id={first.id}").json()["data"]
    assert data["entries"] == []


def test_reopened_backend_reads_persisted_records(runtime):
    """새 Backend와 저장소 인스턴스를 만들어도 같은 DB의 저장 기록을 조회한다."""
    client, clock, store, tracker = runtime
    client.get("/activity/current")
    clock.tick = 4
    tracker.finish()
    expected = client.get("/records/recent").json()["data"]["records"]
    reopened = ActivityStore(store._db_path)
    next_client = TestClient(create_app(activity_store=reopened, collection_interval=None))
    assert next_client.get("/records/recent").json()["data"]["records"] == expected


def test_sensitive_browser_content_is_denied(runtime):
    """기존 브라우저 수신 API도 공유 정책으로 저장 전에 민감 텍스트를 거부한다."""
    client, _, store, _ = runtime
    headers = {"Authorization": "Bearer test-token"}
    source = client.post("/browser/source", headers=headers,
                         json={"browser": "chrome", "url": "https://example.test/page",
                               "page_title": "가상 문서"}).json()["data"]["id"]
    response = client.post("/browser/content", headers=headers,
                           json={"browser_source_id": source, "content_text": "secret=do-not-save"})
    assert response.status_code == 403
    assert store.get_browser_content_record(source) is None
