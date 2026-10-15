"""조건 검색의 입력/응답 검증과 비동기 GET. Client에서 기록을 직접 검색하지 않는다."""

import json
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode

from PySide6.QtCore import QObject, Signal

from client.json_request import JsonRequest
from client.records_client import read_context_records
from client.time_values import parse_timestamp
from shared.protocol import API_VERSION, DEFAULT_PORT, SERVICE_NAME
from shared.search import (
    MAX_SEARCH_KEYWORD,
    MAX_SEARCH_PROCESS,
    SEARCH_LIMIT,
    SEARCH_PATH,
    SearchRequest,
    SearchResults,
)


def local_date_range(first: date, last: date) -> tuple[str, str]:
    """PC 현지 날짜의 시작 포함/마지막 날짜 다음 자정 제외 경계를 시간대와 함께 만든다.

    각 자정을 별도로 현지화해 DST 전환일에도 하루를 고정 24시간으로 계산하지 않는다.
    """
    if first > last:
        raise ValueError("시작 날짜는 마지막 날짜보다 늦을 수 없습니다.")
    try:
        start = datetime.combine(first, time.min).astimezone()
        end = datetime.combine(last + timedelta(days=1), time.min).astimezone()
    except (ValueError, OverflowError, OSError) as error:
        raise ValueError("표시 가능한 날짜 범위를 선택해 주세요.") from error
    return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")


def read_search_request(raw: object) -> SearchRequest:
    """문자열/범위를 검증하고 제목 양끝 공백·프로세스 대소문자만 입력 기준으로 통일한다."""
    if not isinstance(raw, dict):
        raise ValueError("검색 조건을 확인해 주세요.")
    texts = []
    for field, maximum in (("keyword", MAX_SEARCH_KEYWORD), ("process_name", MAX_SEARCH_PROCESS)):
        value = raw.get(field)
        if (not isinstance(value, str) or len(value) > maximum
                or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            raise ValueError("검색어와 프로세스명의 길이·문자를 확인해 주세요.")
        texts.append(value.strip())
    source, order, limit = raw.get("source_type"), raw.get("sort"), raw.get("limit")
    if (source not in ("all", "web", "document", "pdf", "docx") or order not in ("recent", "oldest")
            or type(limit) is not int or not 1 <= limit <= SEARCH_LIMIT):
        raise ValueError("출처·정렬·조회 개수를 확인해 주세요.")
    first, before = raw.get("active_from"), raw.get("active_before")
    started = parse_timestamp(first) if first is not None else None
    ended = parse_timestamp(before) if before is not None else None
    if started is not None and ended is not None and started >= ended:
        raise ValueError("검색 시작은 종료보다 앞서야 합니다.")
    process = texts[1].casefold()
    if len(process) > MAX_SEARCH_PROCESS:
        raise ValueError("프로세스명이 너무 깁니다.")
    return SearchRequest(texts[0], process, source, first, before, order, limit)


def read_search_results(payload: bytes, expected: SearchRequest) -> SearchResults:
    """응답의 조건 확인·기록 구조·정렬 순서를 검사하고 한 행이라도 잘못되면 거부한다."""
    body = json.loads(payload)
    if (not isinstance(body, dict) or body.get("ok") is not True
            or "error" not in body or body["error"] is not None):
        raise ValueError("Invalid search envelope")
    data = body.get("data")
    if (not isinstance(data, dict) or data.get("service") != SERVICE_NAME
            or type(data.get("api_version")) is not int or data["api_version"] != API_VERSION):
        raise ValueError("Incompatible search response")
    # 제출한 조건 전체를 서버가 확인해야 한다. None/빈 문자열 필드도 생략하지 않는다.
    if data.get("request") != asdict(expected) or read_search_request(data["request"]) != expected:
        raise ValueError("Search request was not confirmed")
    records = read_context_records(data.get("records"), expected.limit)
    if any(record.browser is not None and record.document is not None for record in records):
        raise ValueError("Ambiguous search record source")
    more = data.get("has_more")
    if type(more) is not bool or (more and len(records) != expected.limit):
        raise ValueError("Invalid search result limit")
    ordered = sorted(records, key=lambda record: record.id)
    ordered.sort(key=lambda record: parse_timestamp(record.last_active_at),
                 reverse=expected.sort == "recent")
    if [record.id for record in ordered] != [record.id for record in records]:
        raise ValueError("Unexpected result order")
    return SearchResults(expected, records, more)


class SearchClient(JsonRequest):
    """현재 제출한 요청만 유지하며 새 입력/취소/재연결 시 이전 응답을 폐기한다."""

    results_received = Signal(object)
    search_failed = Signal(str)

    def __init__(self, port: int = DEFAULT_PORT, parent: QObject | None = None) -> None:
        """공통 loopback HTTP·timeout·리다이렉트 거부를 재사용한다."""
        super().__init__(port, parent)
        self.request: SearchRequest | None = None
        self.received.connect(self._received)
        self.failed.connect(self._failed)

    def search(self, request: SearchRequest) -> None:
        """정규화된 조건을 개별 쿼리 값으로 인코딩하고 GET으로 조회한다."""
        self.close()
        self.request = request
        query = {key: value for key, value in asdict(request).items() if value is not None}
        self.get(f"{SEARCH_PATH}?{urlencode(query)}")

    def _received(self, payload: bytes) -> None:
        """조건이 다른 응답과 계약 오류를 성공 결과처럼 표시하지 않는다."""
        if self.request is None:
            return
        try:
            results = read_search_results(payload, self.request)
        except (ValueError, UnicodeDecodeError):
            self._failed("content_type", 0)
            return
        self.results_received.emit(results)

    def _failed(self, reason: str, status: int) -> None:
        """빈 결과와 미지원·거부·오류를 구분하며 오류 원문은 노출하지 않는다."""
        if reason == "http" and status == 404:
            message = "기능 준비 중 — Backend가 조건 검색을 지원하지 않습니다."
        elif reason == "http" and status == 403:
            message = "검색이 허용되지 않았습니다. 개인정보 설정을 확인해 주세요."
        elif reason == "http" and status == 422:
            message = "검색 조건을 처리할 수 없습니다. 입력을 확인해 주세요."
        else:
            message = {
                "timeout": "검색 시간 초과 — 다시 검색해 주세요.",
                "http": "검색 실패 — 서버 오류입니다.",
                "network": "연결 안 됨 — Backend 실행 후 다시 검색해 주세요.",
                "content_type": "호환되지 않는 검색 응답 — 다시 검색해 주세요.",
            }[reason]
        self.search_failed.emit(message)

    def close(self) -> None:
        """취소한 요청의 조건과 콜백을 함께 제거한다."""
        super().close()
        self.request = None
