"""최근 기록의 동일 시각 ID 정렬과 제한 적용을 실제 SQLite·API로 검증한다."""

import pytest
from fastapi.testclient import TestClient

from backend.activity_store import ActivityStore
from backend.app import create_app
from client.records_client import read_recent_records
from shared.activity import ActiveWindow


def save_record(store, last_active_at, number):
    """삽입 순서와 창 제목을 구분할 수 있는 개인정보 없는 작업을 저장한다."""
    return store.save_record(
        ActiveWindow("가상 프로그램", "example.exe", number, f"가상 기록 {number}"),
        "2026-10-26T02:58:00Z",
        last_active_at,
        1000,
    )


@pytest.fixture
def tied_records(tmp_path):
    """서로 다른 시간대 표현으로 같은 순간을 가리키는 기록 25건을 만든다."""
    store = ActivityStore(tmp_path / "activity.db")
    same_instant = (
        "2026-10-26T03:00:00Z",
        "2026-10-26T12:00:00+09:00",
        "2026-10-25T20:00:00-07:00",
        "2026-10-26T03:00:00+00:00",
    )
    identifiers = [
        str(save_record(store, same_instant[index % len(same_instant)], index + 1))
        for index in range(25)
    ]
    return store, identifiers


def test_equal_instants_use_string_ids_before_limit(tied_records):
    """동률 전체를 문자열 ID순으로 정렬한 뒤 20건을 골라야 누락이 생기지 않는다."""
    store, identifiers = tied_records
    expected = sorted(identifiers)[:20]

    records = store.get_recent_records(limit=20)

    assert [str(record.id) for record in records] == expected


def test_recent_api_and_client_preserve_limited_row_set_and_order(tied_records):
    """실제 API와 Client 파서 모두 계약상 같은 20건을 같은 순서로 전달한다."""
    store, identifiers = tied_records
    expected = sorted(identifiers)[:20]
    # 자동 수집과 네이티브 클립보드를 끄고 저장 기록 조회 경로만 실행한다.
    app = create_app(
        activity_store=store,
        collection_interval=None,
        clipboard_reader=lambda: None,
    )

    with TestClient(app) as client:
        response = client.get("/records/recent", params={"limit": 20})

    assert response.status_code == 200
    rows = response.json()["data"]["records"]
    parsed = read_recent_records(response.content)
    assert [row["id"] for row in rows] == expected
    assert [record.id for record in parsed] == expected
    assert [record.window_title for record in parsed] == [row["window_title"] for row in rows]


def test_actual_time_precedes_id_tiebreak_and_survives_reopen(tied_records):
    """최신 순간이 ID보다 우선하며 DB를 다시 열어도 같은 순서를 유지한다."""
    store, identifiers = tied_records
    newest = str(save_record(store, "2026-10-26T03:00:01Z", 26))
    oldest = str(save_record(store, "2026-10-26T02:59:59Z", 27))
    expected = [newest, *sorted(identifiers), oldest]

    before = store.get_recent_records(limit=200)
    reopened = ActivityStore(store._db_path)
    after = reopened.get_recent_records(limit=200)

    assert [str(record.id) for record in before] == expected
    assert [str(record.id) for record in after] == expected
    assert after == before


def save_microsecond_pair(store, newest_first, older_at="2026-10-26T03:00:00.000100Z"):
    """서로 다른 미세 시각을 저장해 ID 크기만으로 최신 기록을 고를 수 없게 한다."""
    moments = [("older", older_at), ("newest", "2026-10-26T12:00:00.000200+09:00")]
    if newest_first:
        moments.reverse()
    return {
        label: str(save_record(store, timestamp, index + 1))
        for index, (label, timestamp) in enumerate(moments)
    }


@pytest.mark.parametrize("newest_first", [False, True])
@pytest.mark.parametrize(
    "older_at",
    ["2026-10-26T03:00:00.000100Z", "2026-10-26T03:00:00.000100"],
    ids=["aware-offset", "legacy-naive-utc"],
)
def test_microsecond_order_precedes_limit_and_handles_legacy_utc(
    tmp_path, newest_first, older_at
):
    """밀리초보다 짧은 시각 차이와 기존 시간대 없는 UTC 기록도 제한 전에 비교한다."""
    store = ActivityStore(tmp_path / "microseconds.db")
    identifiers = save_microsecond_pair(store, newest_first, older_at)

    records = store.get_recent_records(limit=1)
    reopened = ActivityStore(store._db_path)

    assert [str(record.id) for record in records] == [identifiers["newest"]]
    assert reopened.get_recent_records(limit=1) == records


@pytest.mark.parametrize("newest_first", [False, True])
def test_recent_api_and_client_select_newest_microsecond_before_limit(tmp_path, newest_first):
    """API가 미세 시각의 최신 한 건을 골라야 Client 정렬 뒤에도 누락되지 않는다."""
    store = ActivityStore(tmp_path / "microsecond-api.db")
    identifiers = save_microsecond_pair(store, newest_first)
    app = create_app(
        activity_store=store,
        collection_interval=None,
        clipboard_reader=lambda: None,
    )

    with TestClient(app) as client:
        response = client.get("/records/recent", params={"limit": 1})

    assert response.status_code == 200
    expected = [identifiers["newest"]]
    rows = response.json()["data"]["records"]
    parsed = read_recent_records(response.content)
    assert [row["id"] for row in rows] == expected
    assert [record.id for record in parsed] == expected


def test_invalid_legacy_time_sorts_last_without_changing_raw_value(tied_records):
    """손상된 기존 시각은 유효 기록 뒤에 두고 저장된 원문을 임의로 고치지 않는다."""
    store, identifiers = tied_records
    invalid_time = "기존 기록의 잘못된 시각"
    invalid_id = str(save_record(store, invalid_time, 26))

    limited = store.get_recent_records(limit=20)
    all_records = store.get_recent_records(limit=200)

    assert [str(record.id) for record in limited] == sorted(identifiers)[:20]
    assert [str(record.id) for record in all_records] == [*sorted(identifiers), invalid_id]
    assert all_records[-1].ended_at == invalid_time
