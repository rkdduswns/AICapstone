"""가상 검색 조각의 출처 복원·계약 검증. 실제 분할·임베딩·검색을 수행하는 테스트가 아니다."""

import json
from copy import deepcopy
from dataclasses import asdict

import pytest

from client.search_data_values import read_document_chunk, read_source_metadata
from shared.browser import BrowserPage
from shared.document import LocalDocument
from shared.search_data import DocumentChunk, SourceMetadata

CONTEXT_ID = "가상/작업?x=1&y=2#+%"
URL = "https://example.com/Research?q=%EA%B0%80#Section"
FILE_PATH = r"C:\가상 자료\참고 문서.PDF"
WEB = {
    "id": "chunk-web-001",
    "context_id": CONTEXT_ID,
    "chunk_index": 0,
    "text": "  <b>가상 문서 조각</b>\n첫 번째 문장🙂  ",
    "source": {
        "kind": "web",
        "application": "Google Chrome",
        "process_name": "chrome.exe",
        "window_title": "활성 창 제목",
        "started_at": "2026-10-14T02:00:00+09:00",
        "last_active_at": "2026-10-13T17:01:00Z",
        "captured_at": "2026-10-14T02:00:15+09:00",
        "content_truncated": False,
        "browser": {"browser": "chrome", "page_title": "<b>확보 당시 제목</b>", "url": URL},
    },
}


def decoded(raw):
    """실제 HTTP JSON 디코딩처럼 Unicode/선택 필드를 유지해 수신 경계를 확인한다."""
    return json.loads(json.dumps(raw, ensure_ascii=False))


def document_chunk(file_path=FILE_PATH, file_type="pdf"):
    """고정 가상 문서 조각을 준비한다. 본문을 분할하거나 실제 파일을 읽지 않는다."""
    raw = deepcopy(WEB)
    raw["id"] = "chunk-document-001"
    raw["source"].update(kind="document", application="가상 문서 앱", process_name="sample.exe",
                         document={"file_path": file_path, "file_type": file_type})
    del raw["source"]["browser"]
    return raw


def test_web_origin_round_trip_without_normalizing_text_or_url():
    """작업 ID·열람/확보 시각·제목·URL·본문을 원문 그대로 복원한다."""
    chunk = read_document_chunk(decoded(WEB), CONTEXT_ID)
    assert chunk.id == "chunk-web-001" and chunk.context_id == CONTEXT_ID
    assert chunk.chunk_index == 0 and chunk.semantic_data_id is None
    assert chunk.text == WEB["text"]
    assert chunk.source.browser == BrowserPage("chrome", "<b>확보 당시 제목</b>", URL)
    assert chunk.source.application == "Google Chrome" and chunk.source.document is None
    assert chunk.source.started_at == "2026-10-14T02:00:00+09:00"
    assert chunk.source.last_active_at == "2026-10-13T17:01:00Z"
    assert chunk.source.captured_at == "2026-10-14T02:00:15+09:00"
    # 같은 제목의 자료라도 원본 ID로 연결한다. URL 정규화나 제목 기반 ID 생성은 하지 않는다.
    assert read_document_chunk(decoded(asdict(chunk)), CONTEXT_ID) == chunk


@pytest.mark.parametrize("file_path,file_type", [
    (FILE_PATH, "pdf"), (r"\\example-server\share\가상 문서.docx", "docx"),
])
def test_document_origin_round_trip_and_semantic_reference(file_path, file_type):
    """PDF/DOCX 조각을 같은 구조로 읽고 파일 원문 경로와 의미 데이터 ID를 보존한다."""
    raw = document_chunk(file_path, file_type)
    raw.update(chunk_index=3, semantic_data_id="semantic-reference-003")
    raw["source"]["content_truncated"] = True
    chunk = read_document_chunk(decoded(raw), CONTEXT_ID)
    assert chunk.source.document == LocalDocument(file_path, file_type)
    assert chunk.source.browser is None and chunk.source.kind == "document"
    assert chunk.source.content_truncated is True and chunk.chunk_index == 3
    assert chunk.semantic_data_id == "semantic-reference-003"
    assert read_document_chunk(decoded(asdict(chunk)), CONTEXT_ID) == chunk


def test_optional_semantic_reference_and_forward_fields():
    """임베딩 미연결의 생략/null과 향후 추가 필드를 호환한다."""
    raw = deepcopy(WEB)
    raw.update(semantic_data_id=None, future_chunk_field="ignored")
    raw["source"].update(document=None, future_source_field="ignored")
    raw["source"]["browser"]["future_page_field"] = "ignored"
    assert read_document_chunk(decoded(raw), CONTEXT_ID) == read_document_chunk(WEB, CONTEXT_ID)


@pytest.mark.parametrize("path,value", [
    (("id",), None), (("id",), " "),
    (("context_id",), None), (("context_id",), "다른 작업"),
    (("chunk_index",), True), (("chunk_index",), -1), (("chunk_index",), 1.5),
    (("text",), None), (("text",), " \n\t"),
    pytest.param(("text",), "한" * 50001, id="oversized-chunk"),
    (("semantic_data_id",), False), (("semantic_data_id",), " "),
    (("source",), None), (("source", "kind"), "clipboard"),
    (("source", "application"), " "), (("source", "process_name"), None),
    (("source", "window_title"), None), (("source", "content_truncated"), 1),
    (("source", "started_at"), "2026-10-14T02:00:00"),
    (("source", "last_active_at"), "2026-10-14T01:59:59+09:00"),
    (("source", "captured_at"), "2026-02-30T02:00:00+09:00"),
    (("source", "browser"), None), (("source", "browser", "url"), None),
    (("source", "browser", "url"), "file:///C:/example.pdf"),
    (("source", "browser", "url"), "javascript:alert(1)"),
    (("source", "browser", "url"), "https://user:password@example.com/"),
    (("source", "document"), {"file_path": FILE_PATH, "file_type": "pdf"}),
])
def test_invalid_identity_source_time_and_text(path, value):
    """출처가 없거나 잘못된 조각과 다른 작업의 본문을 정상 검색 근거로 쓰지 않는다."""
    raw = deepcopy(WEB)
    target = raw
    for field in path[:-1]:
        target = target[field]
    target[path[-1]] = value
    with pytest.raises(ValueError):
        read_document_chunk(decoded(raw), CONTEXT_ID)


@pytest.mark.parametrize("field", ["id", "context_id", "chunk_index", "text", "source"])
def test_required_chunk_fields(field):
    """필수 조각 정보를 생략하면 None/기본값으로 추정하지 않는다."""
    raw = deepcopy(WEB)
    del raw[field]
    with pytest.raises(ValueError):
        read_document_chunk(decoded(raw), CONTEXT_ID)


@pytest.mark.parametrize("field", [
    "kind", "application", "process_name", "window_title", "started_at",
    "last_active_at", "captured_at", "content_truncated", "browser",
])
def test_required_source_fields(field):
    """확보 시점 출처의 필수 필드를 누락하면 최신 작업이나 현재 시각으로 대체하지 않는다."""
    raw = deepcopy(WEB)
    del raw["source"][field]
    with pytest.raises(ValueError):
        read_document_chunk(decoded(raw), CONTEXT_ID)


@pytest.mark.parametrize("replacement", [
    None, {"file_path": "relative.pdf", "file_type": "pdf"},
    {"file_path": FILE_PATH, "file_type": "docx"},
])
def test_document_requires_valid_file_source(replacement):
    """출처 유형만 파일이라고 선언하거나 확장자와 다른 유형을 보내는 응답을 거부한다."""
    raw = document_chunk()
    raw["source"]["document"] = replacement
    with pytest.raises(ValueError):
        read_document_chunk(decoded(raw), CONTEXT_ID)


def test_document_cannot_include_web_origin_and_kind_cannot_be_swapped():
    """웹/파일 출처를 한 조각에 섞거나 종류만 바꿔서 해석하지 않는다."""
    raw = document_chunk()
    raw["source"]["browser"] = WEB["source"]["browser"]
    with pytest.raises(ValueError):
        read_document_chunk(decoded(raw), CONTEXT_ID)
    raw = deepcopy(WEB)
    raw["source"]["kind"] = "document"
    with pytest.raises(ValueError):
        read_document_chunk(decoded(raw), CONTEXT_ID)


@pytest.mark.parametrize("raw", [None, [], "chunk"])
def test_non_object_chunk(raw):
    """객체 이외의 최상위 값을 검색 조각으로 처리하지 않는다."""
    with pytest.raises(ValueError):
        read_document_chunk(raw, CONTEXT_ID)


@pytest.mark.parametrize("context", [None, "", " "])
def test_missing_expected_context(context):
    """호출자가 원본 작업을 확인하지 않은 상태에서 조각 ID만으로 연결을 추정하지 않는다."""
    with pytest.raises(ValueError):
        read_document_chunk(WEB, context)


def test_unicode_limit_short_text_and_independent_capture_time():
    """전송 상한은 토큰 수가 아니며 짧은 조각의 색인 여부·확보 시각을 Client가 추측하지 않는다."""
    raw = deepcopy(WEB)
    raw["text"] = "한🙂" * 25000
    raw["source"]["content_truncated"] = True
    chunk = read_document_chunk(decoded(raw), CONTEXT_ID)
    assert len(chunk.text) == 50000 and chunk.source.content_truncated
    raw["text"] = "짧음"
    raw["source"].update(window_title="", captured_at="2026-10-14T02:05:00+09:00")
    chunk = read_document_chunk(decoded(raw), CONTEXT_ID)
    assert chunk.text == "짧음" and chunk.source.window_title == ""
    # 본문 확보가 열람 종료 후 처리될 수도 있어 확보 시각을 마지막 활성 시각 안으로 강제하지 않는다.
    assert chunk.source.captured_at == "2026-10-14T02:05:00+09:00"


def test_fixed_snapshots_retain_their_own_origin_after_navigation():
    """후속 탐색으로 같은 작업의 페이지가 바뀌어도 과거 조각은 그 당시 출처를 유지한다."""
    first = read_document_chunk(decoded(WEB), CONTEXT_ID)
    second_raw = deepcopy(WEB)
    second_raw.update(id="chunk-new-snapshot", text="후속 페이지의 가상 조각")
    second_raw["source"].update(captured_at="2026-10-14T02:02:00+09:00")
    second_raw["source"]["browser"].update(url="https://example.org/later", page_title="후속 페이지")
    second = read_document_chunk(decoded(second_raw), CONTEXT_ID)
    assert first.context_id == second.context_id
    assert first.source.browser.url == URL and second.source.browser.url == "https://example.org/later"
    assert first.id != second.id and first.source.captured_at != second.source.captured_at


def test_shared_definitions_are_plain_serializable_data():
    """Backend도 Client/Qt 없이 생산할 수 있는 자료 구조가 수신 계약을 만족하는지 확인한다."""
    source = SourceMetadata(
        "document", "가상 문서 앱", "sample.exe", "가상 창",
        "2026-10-14T02:00:00+09:00", "2026-10-14T02:01:00+09:00",
        "2026-10-14T02:00:15+09:00", False, document=LocalDocument(FILE_PATH, "pdf"))
    chunk = DocumentChunk("shared-chunk", CONTEXT_ID, 0, "가상 본문", source)
    assert read_document_chunk(decoded(asdict(chunk)), CONTEXT_ID) == chunk
    assert read_source_metadata(decoded(asdict(source))) == source
