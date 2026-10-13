"""검색 문서 조각의 수신 계약을 검사한다. 검색·분할·출처 추정·파일/웹 접근은 하지 않는다."""

from client.document_values import read_document
from client.time_values import parse_timestamp
from client.url_values import read_browser
from shared.search_data import MAX_CHUNK_TEXT_LENGTH, DocumentChunk, SourceMetadata


def _identity(raw: object) -> str:
    """ID와 프로그램 정보는 공백뿐인 값을 허용하지 않고 원문 그대로 유지한다."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("Missing search data identity")
    return raw


def read_source_metadata(raw: object) -> SourceMetadata:
    """작업 시간·확보 시각과 종류에 맞는 단일 출처를 모두 검사한 뒤 반환한다.

    기존 브라우저/문서/시각 검증을 재사용한다. 확보 당시 출처가 기록의 현재
    출처와 다를 수 있으므로 최신 창 제목이나 현재 URL/파일 경로로 대체하지 않는다.
    """
    if not isinstance(raw, dict) or raw.get("kind") not in ("web", "document"):
        raise ValueError("Invalid search source kind")
    application = _identity(raw.get("application"))
    process_name = _identity(raw.get("process_name"))
    title = raw.get("window_title")
    if not isinstance(title, str) or type(raw.get("content_truncated")) is not bool:
        raise ValueError("Invalid search source metadata")
    started = parse_timestamp(raw.get("started_at"))
    last_active = parse_timestamp(raw.get("last_active_at"))
    if last_active < started:
        raise ValueError("Activity precedes source start")
    parse_timestamp(raw.get("captured_at"))
    browser = read_browser(raw.get("browser"))
    document = read_document(raw.get("document"))
    if raw["kind"] == "web":
        if browser is None or browser.url is None or document is not None:
            raise ValueError("Expected a single HTTP(S) web source")
    elif document is None or browser is not None:
        raise ValueError("Expected a single local document source")
    return SourceMetadata(
        raw["kind"], application, process_name, title,
        raw["started_at"], raw["last_active_at"], raw["captured_at"],
        raw["content_truncated"], browser, document,
    )


def read_document_chunk(raw: object, context_id: str) -> DocumentChunk:
    """JSON 디코딩이 끝난 검색 조각을 요청/결과의 원본 작업 ID와 대조해 검증한다.

    조각 순서는 bool을 제외한 0 이상 정수다. 비어 있거나 과도한 본문은
    잘라서 정상 처리하지 않는다. 정규화·분할·중복 제거는 Backend가 수행한다.
    """
    expected_context = _identity(context_id)
    if not isinstance(raw, dict):
        raise ValueError("Invalid document chunk")
    identifier = _identity(raw.get("id"))
    origin = _identity(raw.get("context_id"))
    if origin != expected_context:
        raise ValueError("Document chunk belongs to another context")
    index = raw.get("chunk_index")
    text = raw.get("text")
    if type(index) is not int or index < 0:
        raise ValueError("Invalid chunk index")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_CHUNK_TEXT_LENGTH:
        raise ValueError("Invalid chunk text")
    semantic_id = raw.get("semantic_data_id")
    if semantic_id is not None:
        semantic_id = _identity(semantic_id)
    return DocumentChunk(identifier, origin, index, text,
                         read_source_metadata(raw.get("source")), semantic_id)
