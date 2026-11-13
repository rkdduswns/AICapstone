"""저장된 웹·문서 본문을 실제 검색 조각 계약으로 변환하는 경계를 검증한다."""

import json
import subprocess
import sys
from dataclasses import asdict

import pytest

from backend.activity_store import ActivityStore
from backend.privacy_settings import StoredPrivacySettings
from backend.search_text import prepare_search_chunks, prepare_search_texts
from client.search_data_values import read_document_chunk
from shared.activity import ActiveWindow
from shared.browser import BrowserPage
from shared.document import LocalDocument

STARTED = "2026-11-06T03:00:00+00:00"
CAPTURED = "2026-11-06T03:01:00+00:00"
ENDED = "2026-11-06T03:02:00+00:00"
URL = "https://example.test/자료"
DOCUMENT_PATH = r"C:\가상 자료\긴 문서.pdf"


@pytest.fixture
def saved_work(tmp_path):
    """가상 작업과 실제 저장 연결을 사용할 읽기 검증 DB를 만든다."""
    path = tmp_path / "검색 조각 #1.db"
    store = ActivityStore(path)
    record_id = store.save_record(
        ActiveWindow("Google Chrome", "chrome.exe", 42, "가상 작업"), STARTED, ENDED, 120000,
    )
    return path, store, record_id


def save_web(store, record_id, text, url=URL):
    """실제 작업과 웹 출처를 연결하고 본문 확보 시각을 저장한다."""
    source_id = store.save_browser_source_record("chrome", url, "가상 페이지", STARTED, record_id)
    store.save_browser_content_record(source_id, text, CAPTURED)
    return source_id


@pytest.mark.parametrize("kind", ["web", "document"])
def test_long_saved_body_splits_into_client_compatible_chunks(saved_work, kind):
    """긴 한글·보조 평면 문자 본문이 글자 수를 지키며 URL 또는 PDF 경로로 이어진다."""
    path, store, record_id = saved_work
    text = "가" * 1000 + "🙂" * 1000 + "끝"
    if kind == "web":
        save_web(store, record_id, text)
    else:
        store.save_document_record(DOCUMENT_PATH, text, CAPTURED, record_id)
    before = path.read_bytes()

    chunks = prepare_search_chunks(path, record_id)

    assert [len(chunk.text) for chunk in chunks] == [1000, 1000, 1]
    assert "".join(chunk.text for chunk in chunks) == text
    assert [chunk.chunk_index for chunk in chunks] == [0, 1, 2]
    assert len({chunk.id for chunk in chunks}) == 3
    for chunk in chunks:
        assert read_document_chunk(asdict(chunk), str(record_id)) == chunk
        assert chunk.source.kind == kind
        assert chunk.source.application == "Google Chrome"
        assert chunk.source.process_name == "chrome.exe"
        assert chunk.source.window_title == "가상 작업"
        assert chunk.source.started_at == STARTED
        assert chunk.source.last_active_at == ENDED
        assert chunk.source.captured_at == CAPTURED
        assert chunk.source.content_truncated is False
        if kind == "web":
            assert chunk.source.browser == BrowserPage("chrome", "가상 페이지", URL)
        else:
            assert chunk.source.document == LocalDocument(DOCUMENT_PATH, "pdf")
    assert path.read_bytes() == before


@pytest.mark.parametrize("separator", ["\n", " "])
def test_keeps_boundaries_short_tail_and_distinct_sources(saved_work, separator):
    """줄바꿈·공백 경계를 사용하고 같은 본문 안의 중복만 제거한다."""
    path, store, record_id = saved_work
    text = "가" * 600 + separator + "나" * 2000 + "끝"
    save_web(store, record_id, text)
    save_web(store, record_id, text, f"{URL}/다른-출처")

    chunks = prepare_search_chunks(path, record_id)
    assert len(chunks) == 6
    assert len({chunk.id for chunk in chunks}) == 6
    for url in (URL, f"{URL}/다른-출처"):
        matching = [chunk for chunk in chunks if chunk.source.browser.url == url]
        assert [chunk.text for chunk in matching] == ["가" * 600, "나" * 1000, "끝"]
        assert [chunk.chunk_index for chunk in matching] == [0, 1, 2]


def test_ids_track_body_snapshot_and_ignore_activity_end_updates(saved_work):
    """본문 내용 또는 확보 시각 갱신은 웹 ID만 바꾸고 작업 시각 갱신에는 안정적이다."""
    path, store, record_id = saved_work
    web_id = save_web(store, record_id, "같은 본문")
    doc_id = store.save_document_record(DOCUMENT_PATH, "같은 본문", CAPTURED, record_id)
    assert web_id == doc_id
    first_web, first_doc = prepare_search_chunks(path, record_id)
    assert first_web.id != first_doc.id

    store.update_record(record_id, "2026-11-06T03:03:00+00:00", 180000)
    timed_web, timed_doc = prepare_search_chunks(path, record_id)
    assert (timed_web.id, timed_doc.id) == (first_web.id, first_doc.id)
    assert timed_web.source.last_active_at == "2026-11-06T03:03:00+00:00"

    store.save_browser_content_record(web_id, "바뀐 본문", CAPTURED)
    changed_web, stable_doc = prepare_search_chunks(path, record_id)
    assert changed_web.id != first_web.id
    assert stable_doc.id == first_doc.id

    store.save_browser_content_record(web_id, "바뀐 본문", ENDED)
    recaptured_web, _ = prepare_search_chunks(path, record_id)
    assert recaptured_web.id != changed_web.id
    assert recaptured_web.source.captured_at == ENDED


def test_truncation_flag_uses_raw_detail_length(saved_work):
    """정규화 뒤 짧아진 본문에도 원래 저장 본문의 상세 표시 제한을 전달한다."""
    path, store, record_id = saved_work
    raw = " " * 50000 + "원문"
    source_id = save_web(store, record_id, raw)

    [chunk] = prepare_search_chunks(path, record_id)

    assert chunk.text == "원문"
    assert chunk.source.content_truncated is True
    assert store.get_browser_content_record(source_id).content_text == raw


def test_chunks_recheck_source_metadata_and_split_sensitive_text(saved_work):
    """기존 전처리 결과 중 잘못된 출처와 분할로 드러난 민감 패턴을 제외한다."""
    path, store, record_id = saved_work
    save_web(store, record_id, "허용할 본문")
    save_web(store, record_id, "주소 계약 위반 본문", "https://example.test/a b")
    save_web(store, record_id, "x" * 1000 + "password=fixture", f"{URL}/민감")
    assert len(prepare_search_texts(path, record_id)) == 3
    assert [chunk.text for chunk in prepare_search_chunks(path, record_id)] == ["허용할 본문"]

    sensitive_work = store.save_record(
        ActiveWindow("Google Chrome", "chrome.exe", 42, "password=fixture"),
        STARTED, ENDED, 120000,
    )
    save_web(store, sensitive_work, "본문은 일반 텍스트")
    assert prepare_search_chunks(path, sensitive_work) == []

    defaults = StoredPrivacySettings(paused=False, blocked_processes=[], clipboard_enabled=False)
    store.update_privacy_settings({"blocked_processes": ["chrome.exe"]}, defaults)
    assert prepare_search_chunks(path, record_id) == []


def test_cli_chunks_and_existing_text_output(saved_work):
    """옵션으로 실제 조각 JSON을 출력하며 기본 호출은 이전 본문 필드를 반환한다."""
    path, store, record_id = saved_work
    text = "문" * 1000 + "끝"
    store.save_document_record(DOCUMENT_PATH, text, CAPTURED, record_id)
    command = [
        sys.executable, "-m", "backend.search_text", "--db-path", str(path),
        "--record-id", str(record_id),
    ]

    result = subprocess.run([*command, "--chunks"], check=True, capture_output=True, timeout=10)
    chunks = [read_document_chunk(row, str(record_id)) for row in json.loads(result.stdout)]
    assert [chunk.text for chunk in chunks] == ["문" * 1000, "끝"]
    result = subprocess.run(command, check=True, capture_output=True, timeout=10)
    assert json.loads(result.stdout) == [asdict(row) for row in prepare_search_texts(path, record_id)]
