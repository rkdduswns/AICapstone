"""검색 조각과 확보 당시 출처의 공통 데이터 계약. 분할·임베딩·저장 로직은 포함하지 않는다."""

from dataclasses import dataclass
from typing import Literal

from shared.browser import BrowserPage
from shared.document import LocalDocument

# 기존 웹/문서 저장 본문과 같은 전송 상한이며 분할 크기나 모델 토큰 수를 정하지 않는다.
MAX_CHUNK_TEXT_LENGTH = 50000
SourceKind = Literal["web", "document"]


@dataclass(frozen=True)
class SourceMetadata:
    """검색 조각의 원문을 확보한 시점의 출처. 현재 창이나 최신 경로로 덮어쓰지 않는다.

    kind에 맞는 browser/document 하나만 제공한다. started_at/last_active_at은
    원본 작업의 열람 시각이고 captured_at은 본문 확보 시각이라 서로 구분한다.
    원문 자체가 일부만 저장됐다면 content_truncated를 후속 검색·근거 표시까지 보존한다.
    """

    kind: SourceKind
    application: str
    process_name: str
    window_title: str
    started_at: str
    last_active_at: str
    captured_at: str
    content_truncated: bool
    browser: BrowserPage | None = None
    document: LocalDocument | None = None


@dataclass(frozen=True)
class DocumentChunk:
    """검색/근거 조회용 조각. context_id로 원본 작업과 연결하고 출처 스냅샷을 유지한다.

    chunk_index는 본문 스냅샷 안의 0부터 시작하는 순서다. id는 조각을 구분하는
    안정적인 식별자이며 제목/URL/경로만으로 작업 ID나 조각 ID를 추정하지 않는다.
    semantic_data_id가 None이면 의미 검색 데이터 연결이 아직 없음을 뜻한다.
    이 조회 구조는 Backend 저장소 스키마나 임베딩 모델·벡터 차원을 강제하지 않는다.
    """

    id: str
    context_id: str
    chunk_index: int
    text: str
    source: SourceMetadata
    semantic_data_id: str | None = None
